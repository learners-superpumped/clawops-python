import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline.realtime._openai import OpenAIRealtime


def _make_mock_connection() -> MagicMock:
    """OpenAI Realtime connection mock — 최소한의 async API 흉내."""
    conn = MagicMock()
    conn.session = MagicMock()
    conn.session.update = AsyncMock()
    conn.response = MagicMock()
    conn.response.create = AsyncMock()
    conn.input_audio_buffer = MagicMock()
    conn.input_audio_buffer.append = AsyncMock()
    conn.close = AsyncMock()

    async def _aiter():
        # receive_loop 가 즉시 끝나도록 빈 stream
        if False:
            yield None
        return

    conn.__aiter__ = lambda self_: _aiter()
    return conn


@pytest.mark.asyncio
async def test_prewarm_opens_ws_without_call() -> None:
    """prewarm() 은 CallSession 없이 호출 가능하다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=False)
    mock_conn = _make_mock_connection()
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()
    mock_conn.session.update.assert_awaited_once()
    assert sess._call is not None  # _BufferingCall 로 채워져야 함
    await sess.stop()


@pytest.mark.asyncio
async def test_prewarm_with_greeting_calls_response_create() -> None:
    """greeting=True 면 prewarm 시 response.create 도 호출된다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=True)
    mock_conn = _make_mock_connection()
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()
    mock_conn.response.create.assert_awaited_once()
    await sess.stop()


@pytest.mark.asyncio
async def test_attach_replaces_buffering_call_and_flushes() -> None:
    """attach() 가 _BufferingCall 의 누적 chunk 를 실제 call.send_audio 로 flush 한다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=False)
    mock_conn = _make_mock_connection()
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()

    # prewarm 동안 audio 가 들어왔다고 가정
    await sess._call.send_audio(b"a" * 160)
    await sess._call.send_audio(b"b" * 160)

    real_call = MagicMock()
    real_call.send_audio = AsyncMock()
    real_call._emit = AsyncMock()
    real_call.metrics = MagicMock()

    await sess.attach(real_call)

    assert sess._call is real_call
    assert real_call.send_audio.await_count == 2
    real_call.send_audio.assert_any_await(b"a" * 160)
    real_call.send_audio.assert_any_await(b"b" * 160)
    await sess.stop()


@pytest.mark.asyncio
async def test_start_calls_prewarm_then_attach() -> None:
    """기존 start(call) 은 prewarm + attach 의 wrapper 다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=False)
    sess.prewarm = AsyncMock()
    sess.attach = AsyncMock()
    real_call = MagicMock()
    await sess.start(real_call)
    sess.prewarm.assert_awaited_once()
    sess.attach.assert_awaited_once_with(real_call)
