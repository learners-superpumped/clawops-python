# tests/agent/test_gemini_realtime.py
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
