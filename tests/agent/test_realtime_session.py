# tests/agent/test_realtime_session.py
from clawops.agent.pipeline.realtime._openai import OpenAIRealtime, OpenAIRealtimeConfig


def test_openai_realtime_config_defaults():
    config = OpenAIRealtimeConfig(
        system_prompt="test",
        openai_api_key="sk-test",
    )
    assert config.voice == "marin"
    assert config.model == "gpt-realtime-1.5"
    assert config.language == "ko"
    assert config.eagerness == "high"
    assert config.greeting is True


def test_openai_realtime_config_custom():
    config = OpenAIRealtimeConfig(
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


def test_openai_realtime_init():
    session = OpenAIRealtime(
        api_key="sk-test",
        system_prompt="You are a helpful assistant.",
        model="gpt-realtime-1.5",
        voice="marin",
    )
    assert session._config.openai_api_key == "sk-test"
    assert session._config.system_prompt == "You are a helpful assistant."
    assert session._config.model == "gpt-realtime-1.5"


def test_openai_realtime_defaults():
    session = OpenAIRealtime(api_key="sk-test")
    assert session._config.model == "gpt-realtime-1.5"
    assert session._config.voice == "marin"
    assert session._config.language == "ko"
    assert session._config.greeting is True


def test_openai_realtime_init_creates_client():
    """AsyncOpenAI 클라이언트가 올바르게 생성되는지 확인."""
    session = OpenAIRealtime(
        api_key="sk-test",
        system_prompt="test",
    )
    assert session._config.openai_api_key == "sk-test"
    assert not hasattr(session, "_http")
    assert session._connection is None
