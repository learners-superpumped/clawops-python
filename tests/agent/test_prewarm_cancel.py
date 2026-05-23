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
