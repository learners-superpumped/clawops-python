# tests/agent/test_agent.py
import pytest
from clawops.agent import ClawOpsAgent
from clawops.agent.pipeline.realtime._openai import OpenAIRealtime


def _make_session(**kwargs):
    return OpenAIRealtime(api_key="sk-openai-test", **kwargs)


def test_agent_creation():
    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        session=_make_session(system_prompt="test prompt"),
    )
    assert agent._from_number == "07012341234"
    assert agent._session._config.system_prompt == "test prompt"


def test_agent_tool_decorator():
    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        session=_make_session(),
    )

    @agent.tool
    async def greet(name: str) -> str:
        """인사합니다."""
        return f"안녕 {name}"

    assert "greet" in agent._tool_registry
    schemas = agent._tool_registry.to_openai_tools()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "greet"


def test_agent_event_decorator():
    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        session=_make_session(),
    )

    @agent.on("call_start")
    async def on_start(call):
        pass

    assert len(agent._event_handlers["call_start"]) == 1


def test_agent_from_env(monkeypatch):
    monkeypatch.setenv("CLAWOPS_API_KEY", "sk_env")
    monkeypatch.setenv("CLAWOPS_ACCOUNT_ID", "AC_env")

    agent = ClawOpsAgent(
        from_="07012341234",
        session=_make_session(),
    )
    assert agent._api_key == "sk_env"
    assert agent._account_id == "AC_env"


def test_agent_missing_api_key():
    from clawops._exceptions import AgentError
    with pytest.raises(AgentError, match="api_key"):
        ClawOpsAgent(
            from_="07012341234",
            session=_make_session(),
        )


def test_agent_missing_session():
    with pytest.raises(TypeError, match="session"):
        ClawOpsAgent(
            api_key="sk_test",
            account_id="AC_test",
            from_="07012341234",
        )
