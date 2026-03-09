import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawops.agent.pipeline._pipeline_session import PipelineSession
from clawops.agent._session import CallSession
from clawops.agent._tool import ToolRegistry


def _make_call() -> CallSession:
    call = CallSession(
        call_id="test-call",
        from_number="010",
        to_number="070",
        account_id="AC123",
    )
    call._send_audio_fn = AsyncMock()
    call._send_clear_fn = AsyncMock()
    call._hangup_fn = AsyncMock()
    return call


@pytest.mark.asyncio
async def test_pipeline_session_start_stop():
    stt = MagicMock()
    llm = MagicMock()
    tts = MagicMock()

    session = PipelineSession(
        stt=stt, llm=llm, tts=tts,
        system_prompt="테스트",
        tool_registry=ToolRegistry(),
        greeting=False,
    )

    call = _make_call()
    await session.start(call)
    assert session._running is True
    await session.stop()
    assert session._running is False


@pytest.mark.asyncio
async def test_pipeline_session_feed_audio():
    stt = MagicMock()
    llm = MagicMock()
    tts = MagicMock()

    session = PipelineSession(
        stt=stt, llm=llm, tts=tts,
        system_prompt="테스트",
        tool_registry=ToolRegistry(),
        greeting=False,
    )

    call = _make_call()
    await session.start(call)
    await session.feed_audio(b'\xff' * 160, 0)
    assert not session._audio_queue.empty()
    await session.stop()
