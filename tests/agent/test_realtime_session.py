# tests/agent/test_realtime_session.py
from clawops.agent.pipeline._openai_realtime import OpenAIRealtime, OpenAIRealtimeConfig


def test_openai_realtime_config_defaults():
    config = OpenAIRealtimeConfig(
        system_prompt="test",
        openai_api_key="sk-test",
    )
    assert config.voice == "marin"
    assert config.model == "gpt-realtime-mini"
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
        model="gpt-realtime-mini",
        voice="marin",
    )
    assert session._config.openai_api_key == "sk-test"
    assert session._config.system_prompt == "You are a helpful assistant."
    assert session._config.model == "gpt-realtime-mini"


def test_openai_realtime_defaults():
    session = OpenAIRealtime(api_key="sk-test")
    assert session._config.model == "gpt-realtime-mini"
    assert session._config.voice == "marin"
    assert session._config.language == "ko"
    assert session._config.greeting is True


# 하위 호환 테스트
def test_legacy_imports():
    from clawops.agent.plugins.openai_realtime import RealtimeConfig, RealtimeSession
    assert RealtimeConfig is OpenAIRealtimeConfig
    assert RealtimeSession is OpenAIRealtime
