# tests/agent/test_gemini_realtime.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline._gemini_realtime import GeminiRealtime


def test_gemini_realtime_init():
    session = GeminiRealtime(
        api_key="AIza-test",
        system_prompt="You are a helpful assistant.",
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        voice="Kore",
    )
    assert session._api_key == "AIza-test"
    assert session._system_prompt == "You are a helpful assistant."
    assert session._model == "gemini-2.5-flash-native-audio-preview-12-2025"
    assert session._voice == "Kore"


def test_gemini_realtime_defaults():
    session = GeminiRealtime(api_key="AIza-test")
    assert session._model == "gemini-2.5-flash-native-audio-preview-12-2025"
    assert session._voice == "Kore"
    assert session._language == "ko"
    assert session._greeting is True


def test_gemini_realtime_tool_schemas():
    session = GeminiRealtime(api_key="AIza-test")
    schemas = session._build_tool_schemas()
    # hang_up tool은 항상 포함
    assert any(t["name"] == "hang_up" for t in schemas)


@pytest.mark.asyncio
async def test_gemini_config_message_structure():
    """Config 메시지가 공식 WebSocket 포맷을 따르는지 검증."""
    session = GeminiRealtime(
        api_key="AIza-test",
        system_prompt="Test prompt",
        voice="Kore",
    )

    sent_messages: list[str] = []

    async def capture_send(data: str):
        sent_messages.append(data)

    mock_ws = AsyncMock()
    mock_ws.closed = False
    mock_ws.send_str = capture_send

    mock_http = AsyncMock()
    mock_http.ws_connect = AsyncMock(return_value=mock_ws)

    with patch("aiohttp.ClientSession", return_value=mock_http), \
         patch.object(session, "_wait_setup_complete", new_callable=AsyncMock), \
         patch.object(session, "_receive_loop", new_callable=AsyncMock):
        mock_call = MagicMock()
        mock_call._emit = AsyncMock()
        await session.start(mock_call)

    # 첫 번째 메시지가 config (setup이 아님)
    assert len(sent_messages) >= 1
    msg = json.loads(sent_messages[0])
    assert "config" in msg, "Top-level key must be 'config', not 'setup'"
    config = msg["config"]

    # responseModalities는 config 직속 (generationConfig 아님)
    assert config["responseModalities"] == ["AUDIO"]

    # speechConfig도 config 직속
    assert config["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"

    # systemInstruction도 config 직속
    assert config["systemInstruction"]["parts"][0]["text"] == "Test prompt"

    # VAD 세부 설정
    vad = config["realtimeInputConfig"]["automaticActivityDetection"]
    assert vad["disabled"] is False
    assert vad["startOfSpeechSensitivity"] == "START_SENSITIVITY_HIGH"
    assert vad["endOfSpeechSensitivity"] == "END_SENSITIVITY_LOW"
    assert vad["prefixPaddingMs"] == 100
    assert vad["silenceDurationMs"] == 500

    # Context window compression
    assert "contextWindowCompression" in config
    assert "slidingWindow" in config["contextWindowCompression"]


@pytest.mark.asyncio
async def test_gemini_audio_input_format():
    """오디오 입력이 공식 WebSocket 포맷(audio 키)을 사용하는지 검증."""
    session = GeminiRealtime(api_key="AIza-test")

    sent_messages: list[str] = []

    async def capture_send(data: str):
        sent_messages.append(data)

    mock_ws = AsyncMock()
    mock_ws.closed = False
    mock_ws.send_str = capture_send
    session._ws = mock_ws
    session._call = MagicMock()

    # G.711 ulaw 160 bytes (20ms at 8kHz)
    ulaw_chunk = b'\xff' * 160
    await session.feed_audio(ulaw_chunk, timestamp=0)

    assert len(sent_messages) == 1
    msg = json.loads(sent_messages[0])
    audio = msg["realtimeInput"]["audio"]
    assert "data" in audio
    assert audio["mimeType"] == "audio/pcm;rate=16000"
    # mediaChunks가 아닌 audio 키를 사용해야 함
    assert "mediaChunks" not in msg["realtimeInput"]
