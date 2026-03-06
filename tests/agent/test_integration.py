"""전체 Agent 컴포넌트 통합 테스트 (실제 서버 연결 없이)."""
import pytest
from clawops.agent import ClawOpsAgent
from clawops.agent._session import CallSession
from clawops.agent._tool import ToolRegistry


def test_full_agent_setup():
    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        system_prompt="테스트 상담원입니다.",
        openai_api_key="sk-openai-test",
        voice="nova",
        language="ko",
    )

    @agent.tool
    async def get_info(query: str) -> str:
        """정보를 조회합니다."""
        return f"결과: {query}"

    events_received = []

    @agent.on("call_start")
    async def on_start(call):
        events_received.append("start")

    @agent.on("call_end")
    async def on_end(call):
        events_received.append("end")

    assert "get_info" in agent._tool_registry
    schemas = agent._tool_registry.to_openai_tools()
    assert any(t["name"] == "get_info" for t in schemas)
    assert "call_start" in agent._event_handlers
    assert "call_end" in agent._event_handlers
    assert agent._config.voice == "nova"


@pytest.mark.asyncio
async def test_tool_execution_integration():
    registry = ToolRegistry()

    @registry.register
    async def add_numbers(a: int, b: int) -> str:
        """두 수를 더합니다."""
        return str(a + b)

    result = await registry.call("add_numbers", {"a": 2, "b": 3})
    assert result == "5"

    schemas = registry.to_openai_tools()
    assert schemas[0]["parameters"]["required"] == ["a", "b"]


@pytest.mark.asyncio
async def test_call_session_lifecycle():
    session = CallSession(
        call_id="CA_integ",
        from_number="01012345678",
        to_number="07012341234",
        account_id="AC_test",
    )

    events = []

    async def on_transcript(call, role, text):
        events.append(f"{role}:{text}")

    session.on("transcript", on_transcript)

    await session._emit("transcript", "user", "안녕하세요")
    await session._emit("transcript", "assistant", "네, 반갑습니다")

    assert events == ["user:안녕하세요", "assistant:네, 반갑습니다"]
    assert session.duration > 0


def test_all_imports():
    from clawops.agent import ClawOpsAgent
    from clawops.agent._tool import ToolRegistry
    from clawops.agent._session import CallSession
    from clawops.agent._audio import pcm16_to_ulaw, ulaw_to_pcm16
    from clawops.agent._control_ws import ControlWebSocket
    from clawops.agent._media_ws import MediaWebSocket
    from clawops.agent.pipeline import STT, LLM, TTS
    from clawops.agent.pipeline._realtime_session import RealtimeSession, RealtimeConfig
    from clawops.agent.mcp import MCPServerHTTP, MCPServerStdio
    from clawops.agent.plugins.openai_realtime import OpenAIRealtimePlugin
    # All imports successful
