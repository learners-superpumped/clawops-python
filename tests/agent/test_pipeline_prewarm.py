from unittest.mock import AsyncMock, MagicMock

import pytest

from clawops.agent.pipeline._pipeline_session import PipelineSession


@pytest.mark.asyncio
async def test_pipeline_prewarm_no_call_required() -> None:
    stt = MagicMock()
    llm = MagicMock()
    tts = MagicMock()
    sess = PipelineSession(stt=stt, llm=llm, tts=tts, system_prompt="x", greeting=False)
    await sess.prewarm()
    assert sess._call is not None  # BufferingCall
    await sess.stop()


@pytest.mark.asyncio
async def test_pipeline_attach_flushes_tts_buffer() -> None:
    stt = MagicMock()
    llm = MagicMock()
    tts = MagicMock()
    sess = PipelineSession(stt=stt, llm=llm, tts=tts, system_prompt="x", greeting=False)
    await sess.prewarm()
    await sess._call.send_audio(b"u" * 160)

    real_call = MagicMock()
    real_call.send_audio = AsyncMock()
    real_call._emit = AsyncMock()
    real_call.metrics = MagicMock()
    await sess.attach(real_call)
    real_call.send_audio.assert_awaited_once_with(b"u" * 160)
    await sess.stop()


@pytest.mark.asyncio
async def test_pipeline_start_calls_prewarm_then_attach() -> None:
    stt = MagicMock()
    llm = MagicMock()
    tts = MagicMock()
    sess = PipelineSession(stt=stt, llm=llm, tts=tts, system_prompt="x", greeting=False)
    sess.prewarm = AsyncMock()
    sess.attach = AsyncMock()
    real_call = MagicMock()
    await sess.start(real_call)
    sess.prewarm.assert_awaited_once()
    sess.attach.assert_awaited_once_with(real_call)
