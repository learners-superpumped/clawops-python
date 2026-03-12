import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from clawops.agent.pipeline.tts._elevenlabs import ElevenLabsTTS
from clawops.agent.pipeline._base import TTS


def test_elevenlabs_tts_implements_protocol():
    tts = ElevenLabsTTS(api_key="test-key")
    assert isinstance(tts, TTS)


def test_elevenlabs_tts_sample_rate():
    tts = ElevenLabsTTS(api_key="test-key", output_format="pcm_24000")
    assert tts.sample_rate == 24000
    tts2 = ElevenLabsTTS(api_key="test-key", output_format="pcm_16000")
    assert tts2.sample_rate == 16000


@pytest.mark.asyncio
async def test_elevenlabs_tts_synthesize():
    """mock WebSocket으로 synthesize가 오디오를 반환하는지 확인."""
    tts = ElevenLabsTTS(api_key="test-key")

    fake_audio = b'\x00\x80' * 100
    audio_response = json.dumps({"audio": base64.b64encode(fake_audio).decode()})

    mock_ws = AsyncMock()
    mock_ws.closed = False
    mock_ws.send_str = AsyncMock()
    mock_ws.close = AsyncMock()

    async def ws_aiter(self):
        yield MagicMock(type=aiohttp.WSMsgType.TEXT, data=audio_response)
    mock_ws.__aiter__ = lambda self: ws_aiter(self)

    mock_session = AsyncMock()
    mock_session.ws_connect = AsyncMock(return_value=mock_ws)
    mock_session.close = AsyncMock()

    async def fake_text():
        yield "안녕하세요"

    with patch("clawops.agent.pipeline.tts._elevenlabs.aiohttp.ClientSession", return_value=mock_session):
        result = []
        async for audio_chunk in tts.synthesize(fake_text()):
            result.append(audio_chunk)

    assert len(result) > 0
    assert result[0] == fake_audio
