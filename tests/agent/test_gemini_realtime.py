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
async def test_gemini_setup_message_structure():
    """Setup 메시지에 VAD, transcription, compression 설정이 포함되는지 검증."""
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

    # 첫 번째 메시지가 setup
    assert len(sent_messages) >= 1
    setup_msg = json.loads(sent_messages[0])
    setup = setup_msg["setup"]

    # 1. VAD 세부 설정
    vad = setup["realtimeInputConfig"]["automaticActivityDetection"]
    assert vad["disabled"] is False
    assert vad["startOfSpeechSensitivity"] == "START_SENSITIVITY_HIGH"
    assert vad["endOfSpeechSensitivity"] == "END_SENSITIVITY_LOW"
    assert vad["prefixPaddingMs"] == 100
    assert vad["silenceDurationMs"] == 500

    # 2. Transcription 설정
    gen_config = setup["generationConfig"]
    assert "inputAudioTranscription" in gen_config
    assert "outputAudioTranscription" in gen_config

    # 3. Context window compression
    assert "contextWindowCompression" in setup
    assert "slidingWindow" in setup["contextWindowCompression"]
