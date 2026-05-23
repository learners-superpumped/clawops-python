from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline.realtime._gemini import GeminiRealtime


@pytest.mark.asyncio
async def test_gemini_prewarm_opens_live_session_without_call() -> None:
    sess = GeminiRealtime(api_key="g-test", greeting=False)
    mock_live = MagicMock()
    mock_live.send_realtime_input = AsyncMock()
    with patch.object(sess, "_open_live_session", new=AsyncMock(return_value=mock_live)):
        await sess.prewarm()
    assert sess._session is mock_live
    assert sess._call is not None
    await sess.stop()


@pytest.mark.asyncio
async def test_gemini_prewarm_greeting_sends_text() -> None:
    sess = GeminiRealtime(api_key="g-test", greeting=True)
    mock_live = MagicMock()
    mock_live.send_realtime_input = AsyncMock()
    with patch.object(sess, "_open_live_session", new=AsyncMock(return_value=mock_live)):
        await sess.prewarm()
    mock_live.send_realtime_input.assert_awaited_once()
    await sess.stop()


@pytest.mark.asyncio
async def test_gemini_attach_flushes_buffer() -> None:
    sess = GeminiRealtime(api_key="g-test", greeting=False)
    mock_live = MagicMock()
    mock_live.send_realtime_input = AsyncMock()
    with patch.object(sess, "_open_live_session", new=AsyncMock(return_value=mock_live)):
        await sess.prewarm()
    await sess._call.send_audio(b"x" * 160)

    real_call = MagicMock()
    real_call.send_audio = AsyncMock()
    real_call._emit = AsyncMock()
    real_call.metrics = MagicMock()
    await sess.attach(real_call)
    real_call.send_audio.assert_awaited_once_with(b"x" * 160)
    await sess.stop()


@pytest.mark.asyncio
async def test_gemini_start_calls_prewarm_then_attach() -> None:
    sess = GeminiRealtime(api_key="g-test", greeting=False)
    sess.prewarm = AsyncMock()
    sess.attach = AsyncMock()
    real_call = MagicMock()
    await sess.start(real_call)
    sess.prewarm.assert_awaited_once()
    sess.attach.assert_awaited_once_with(real_call)
