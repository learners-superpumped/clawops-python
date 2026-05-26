import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline.realtime._openai import OpenAIRealtime
from clawops.agent.pipeline.realtime._gemini import GeminiRealtime


def _make_openai_mock_conn() -> MagicMock:
    conn = MagicMock()
    conn.session = MagicMock()
    conn.session.update = AsyncMock()
    conn.response = MagicMock()
    conn.response.create = AsyncMock()
    conn.close = AsyncMock()

    async def _aiter():
        if False:
            yield None
        return

    conn.__aiter__ = lambda self_: _aiter()
    return conn


def _make_blocking_conn() -> MagicMock:
    """receive loop 의 async for 가 영원히 블록되는 mock connection.

    stop() 이 task 를 cancel 만 하고 수거(gather)하지 않으면, cancel 직후 task 는
    아직 done 이 아니다 (cancellation 이 event loop turn 을 필요로 함). gather 하면 done.
    """
    conn = MagicMock()
    conn.session = MagicMock()
    conn.session.update = AsyncMock()
    conn.response = MagicMock()
    conn.response.create = AsyncMock()
    conn.close = AsyncMock()

    async def _aiter():
        await asyncio.Event().wait()  # 영원히 블록 → receive loop 가 async for 에서 대기
        yield None  # pragma: no cover

    conn.__aiter__ = lambda self_: _aiter()
    return conn


@pytest.mark.asyncio
async def test_openai_stop_gathers_receive_loop_task() -> None:
    """stop() 은 receive loop task 를 cancel 후 수거하여 unretrieved exception 을 남기지 않는다."""
    import asyncio

    sess = OpenAIRealtime(api_key="sk-test", greeting=False)
    mock_conn = _make_blocking_conn()
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()
    # receive loop task 가 async for 에서 블록 중인지 확인
    await asyncio.sleep(0)
    task = sess._tasks[0]
    assert not task.done()

    await sess.stop()
    # stop() 이 cancel + gather 까지 했으면 task 는 done (수거됨)
    assert task.done()


@pytest.mark.asyncio
async def test_gemini_stop_gathers_receive_loop_task() -> None:
    """Gemini: stop() 은 receive loop task 를 cancel 후 수거하여 unretrieved exception 을 남기지 않는다."""

    class _BlockingAsyncIter:
        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Event().wait()  # 영원히 블록

    sess = GeminiRealtime(api_key="g-test", greeting=False)
    mock_live = MagicMock()
    mock_live.send_realtime_input = AsyncMock()
    mock_live.receive = MagicMock(return_value=_BlockingAsyncIter())
    with patch.object(sess, "_open_live_session", new=AsyncMock(return_value=mock_live)):
        await sess.prewarm()
    await asyncio.sleep(0)
    task = sess._tasks[0]
    assert not task.done()

    await sess.stop()
    assert task.done()


@pytest.mark.asyncio
async def test_openai_prewarm_then_stop_closes_connection() -> None:
    """OpenAI: prewarm 후 attach 없이 stop() 호출하면 WS 가 닫힌다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=False)
    mock_conn = _make_openai_mock_conn()
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()
    await sess.stop()
    assert sess._connection is None


@pytest.mark.asyncio
async def test_openai_stop_handles_close_timeout_gracefully() -> None:
    """OpenAI: connection.close() 가 hang 해도 stop() 이 무한 대기하지 않는다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=False)
    mock_conn = _make_openai_mock_conn()

    async def _slow_close():
        import asyncio as _a
        await _a.sleep(10)

    mock_conn.close = _slow_close
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()
    await sess.stop()  # 2s timeout 가 동작해야 함
    assert sess._connection is None


@pytest.mark.asyncio
async def test_gemini_prewarm_then_stop_closes_session() -> None:
    """Gemini: prewarm 후 stop() 시 live_ctx 가 닫힌다."""
    sess = GeminiRealtime(api_key="g-test", greeting=False)
    mock_live = MagicMock()
    mock_live.send_realtime_input = AsyncMock()

    # _open_live_session 이 _live_ctx 도 세팅하도록 wrap
    real_open = sess._open_live_session

    async def fake_open():
        sess._live_ctx = MagicMock()
        sess._live_ctx.__aexit__ = AsyncMock(return_value=None)
        return mock_live

    with patch.object(sess, "_open_live_session", new=fake_open):
        await sess.prewarm()
    await sess.stop()
    assert sess._live_ctx is None
