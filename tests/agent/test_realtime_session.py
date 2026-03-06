# tests/agent/test_realtime_session.py
from clawops.agent.pipeline._realtime_session import RealtimeConfig


def test_realtime_config_defaults():
    config = RealtimeConfig(
        system_prompt="test",
        openai_api_key="sk-test",
    )
    assert config.voice == "ash"
    assert config.model == "gpt-4o-realtime-preview"
    assert config.language == "ko"
    assert config.eagerness == "high"
    assert config.greeting is True


def test_realtime_config_custom():
    config = RealtimeConfig(
        system_prompt="custom",
        openai_api_key="sk-test",
        voice="nova",
        model="gpt-4o-mini-realtime",
        language="en",
        eagerness="low",
        greeting=False,
    )
    assert config.voice == "nova"
    assert config.language == "en"
    assert config.greeting is False
