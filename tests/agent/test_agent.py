# tests/agent/test_agent.py
import asyncio
from unittest.mock import AsyncMock, MagicMock

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
        rx_gain=0.8,
        tx_gain=1.2,
    )
    assert agent._from_number == "07012341234"
    assert agent._session._config.system_prompt == "test prompt"
    assert agent._rx_gain == 0.8
    assert agent._tx_gain == 1.2


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


@pytest.mark.asyncio
async def test_outbound_ready_triggers_prewarm():
    """outbound_ready 이벤트 수신 시 session.prewarm() 이 백그라운드로 시작된다."""
    session_mock = MagicMock()
    session_mock.prewarm = AsyncMock()
    session_mock.attach = AsyncMock()
    session_mock.start = AsyncMock()
    session_mock.stop = AsyncMock()

    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        session=session_mock,
    )

    # 미리 active_session 등록 (call() 메서드 우회)
    from clawops.agent._session import CallSession

    call = CallSession(
        call_id="C1",
        from_number="07012341234",
        to_number="07099998888",
        account_id="AC_test",
        direction="outbound",
    )
    agent._active_sessions["C1"] = call

    # _safe_start_call_session 은 실제 media WS 연결을 시도하므로 stub 으로 대체.
    agent._safe_start_call_session = AsyncMock()  # type: ignore[method-assign]

    await agent._handle_outbound_ready({"callId": "C1", "mediaUrl": "wss://media/C1"})
    # prewarm task 가 등록되어야 함
    assert "C1" in agent._prewarm_tasks
    # event loop 한 번 돌려 task 시작 보장
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    session_mock.prewarm.assert_awaited_once()

    # cleanup
    task = agent._prewarm_tasks.get("C1")
    if task and not task.done():
        task.cancel()


@pytest.mark.asyncio
async def test_prewarm_disabled_skips_prewarm():
    """prewarm_enabled=False 면 outbound_ready 수신 시 prewarm task 가 등록되지 않는다."""
    session_mock = MagicMock()
    session_mock.prewarm = AsyncMock()

    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        session=session_mock,
        prewarm_enabled=False,
    )
    agent._safe_start_call_session = AsyncMock()  # type: ignore[method-assign]

    from clawops.agent._session import CallSession

    call = CallSession(
        call_id="C3",
        from_number="07012341234",
        to_number="07099998888",
        account_id="AC_test",
        direction="outbound",
    )
    agent._active_sessions["C3"] = call
    await agent._handle_outbound_ready({"callId": "C3", "mediaUrl": "wss://media/C3"})
    assert "C3" not in agent._prewarm_tasks
    session_mock.prewarm.assert_not_awaited()


@pytest.mark.asyncio
async def test_prewarm_failure_marks_call_failed():
    """prewarm 실패 시 _prewarm_failed 셋에 등록된다."""
    session_mock = MagicMock()
    session_mock.prewarm = AsyncMock(side_effect=RuntimeError("boom"))

    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        session=session_mock,
    )

    await agent._prewarm_session("C2")
    assert "C2" in agent._prewarm_failed


def test_agent_rejects_invalid_gain():
    with pytest.raises(ValueError, match="rx_gain"):
        ClawOpsAgent(
            api_key="sk_test",
            account_id="AC_test",
            from_="07012341234",
            session=_make_session(),
            rx_gain=-0.1,
        )
    with pytest.raises(ValueError, match="tx_gain"):
        ClawOpsAgent(
            api_key="sk_test",
            account_id="AC_test",
            from_="07012341234",
            session=_make_session(),
            tx_gain=float("inf"),
        )
