import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from clawops.agent.pipeline._deepgram_stt import DeepgramSTT
from clawops.agent.pipeline._base import STT


def test_deepgram_stt_implements_protocol():
    stt = DeepgramSTT(api_key="test-key")
    assert isinstance(stt, STT)


@pytest.mark.asyncio
async def test_deepgram_stt_transcribe():
    """mock WebSocket으로 transcribe가 텍스트를 반환하는지 확인."""
    stt = DeepgramSTT(api_key="test-key")

    final_response = json.dumps({
        "type": "Results",
        "channel": {"alternatives": [{"transcript": "안녕하세요"}]},
        "is_final": True,
        "speech_final": True,
    })

    mock_ws = AsyncMock()
    mock_ws.closed = False
    mock_ws.send_bytes = AsyncMock()
    mock_ws.close = AsyncMock()

    # Use a proper async iterator for WS messages
    ws_messages = [MagicMock(type=aiohttp.WSMsgType.TEXT, data=final_response)]

    async def ws_aiter(self):
        for m in ws_messages:
            yield m

    mock_ws.__aiter__ = lambda self: ws_aiter(self)

    mock_session = AsyncMock()
    mock_session.ws_connect = AsyncMock(return_value=mock_ws)
    mock_session.close = AsyncMock()

    async def fake_audio():
        yield b'\x00' * 640

    with patch("clawops.agent.pipeline._deepgram_stt.aiohttp.ClientSession", return_value=mock_session):
        results = []
        async for text in stt.transcribe(fake_audio()):
            results.append(text)

    assert len(results) > 0
    final_events = [e for e in results if e.type == "final"]
    assert len(final_events) == 1
    assert final_events[0].transcript == "안녕하세요"
