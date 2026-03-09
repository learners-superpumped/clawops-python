"""OpenTelemetry tracing 테스트."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestTracingConfig:
    def test_default_values(self):
        from clawops.agent.tracing import TracingConfig

        config = TracingConfig()
        assert config.enabled is True
        assert config.service_name == "clawops-agent"
        assert config.tracer_provider is None

    def test_custom_values(self):
        from clawops.agent.tracing import TracingConfig

        config = TracingConfig(enabled=False, service_name="my-agent")
        assert config.enabled is False
        assert config.service_name == "my-agent"


class TestAttributes:
    def test_call_attributes_exist(self):
        from clawops.agent.tracing._attributes import CALL_ID, CALL_FROM, CALL_TO

        assert CALL_ID == "call.id"
        assert CALL_FROM == "call.from"
        assert CALL_TO == "call.to"

    def test_gen_ai_attributes_exist(self):
        from clawops.agent.tracing._attributes import (
            GEN_AI_SYSTEM,
            GEN_AI_REQUEST_MODEL,
            GEN_AI_RESPONSE_ID,
        )

        assert GEN_AI_SYSTEM == "gen_ai.system"
        assert GEN_AI_REQUEST_MODEL == "gen_ai.request.model"
        assert GEN_AI_RESPONSE_ID == "gen_ai.response.id"

    def test_mcp_attributes_exist(self):
        from clawops.agent.tracing._attributes import (
            MCP_SERVER_TYPE,
            MCP_TOOL_NAME,
            MCP_TOOL_IS_ERROR,
        )

        assert MCP_SERVER_TYPE == "mcp.server.type"
        assert MCP_TOOL_NAME == "mcp.tool.name"
        assert MCP_TOOL_IS_ERROR == "mcp.tool.is_error"

    def test_tool_attributes_exist(self):
        from clawops.agent.tracing._attributes import TOOL_NAME, TOOL_SOURCE

        assert TOOL_NAME == "tool.name"
        assert TOOL_SOURCE == "tool.source"


class TestSpansNoOtel:
    """opentelemetry 미설치 시 no-op 동작 테스트."""

    def test_call_span_noop_without_otel(self):
        from clawops.agent.tracing._spans import call_span

        with patch("clawops.agent.tracing._spans._tracer", None):
            with call_span("test-call-id") as span:
                assert span is None

    def test_tool_span_noop_without_otel(self):
        from clawops.agent.tracing._spans import tool_call_span

        with patch("clawops.agent.tracing._spans._tracer", None):
            with tool_call_span("my_tool", "local") as span:
                assert span is None

    def test_mcp_connect_span_noop_without_otel(self):
        from clawops.agent.tracing._spans import mcp_connect_span

        with patch("clawops.agent.tracing._spans._tracer", None):
            with mcp_connect_span("stdio", command="npx") as span:
                assert span is None

    def test_mcp_call_tool_span_noop_without_otel(self):
        from clawops.agent.tracing._spans import mcp_call_tool_span

        with patch("clawops.agent.tracing._spans._tracer", None):
            with mcp_call_tool_span("get_weather") as span:
                assert span is None

    def test_llm_session_span_noop_without_otel(self):
        from clawops.agent.tracing._spans import llm_session_span

        with patch("clawops.agent.tracing._spans._tracer", None):
            with llm_session_span("gpt-realtime-mini") as span:
                assert span is None


class TestSpansWithMockTracer:
    """mock tracer로 span 생성 테스트."""

    def _make_mock_tracer(self):
        tracer = MagicMock()
        mock_span = MagicMock()
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=mock_span)
        cm.__exit__ = MagicMock(return_value=False)
        tracer.start_as_current_span.return_value = cm
        return tracer, mock_span

    def test_call_span_creates_span(self):
        from clawops.agent.tracing._spans import call_span

        tracer, mock_span = self._make_mock_tracer()
        with patch("clawops.agent.tracing._spans._tracer", tracer):
            with call_span("call-123", from_number="+8210") as span:
                assert span is mock_span

        tracer.start_as_current_span.assert_called_once()
        args, kwargs = tracer.start_as_current_span.call_args
        assert args[0] == "call"
        assert kwargs["attributes"]["call.id"] == "call-123"
        assert kwargs["attributes"]["call.from"] == "+8210"

    def test_tool_span_creates_span(self):
        from clawops.agent.tracing._spans import tool_call_span

        tracer, mock_span = self._make_mock_tracer()
        with patch("clawops.agent.tracing._spans._tracer", tracer):
            with tool_call_span("get_weather", "mcp") as span:
                assert span is mock_span

        args, kwargs = tracer.start_as_current_span.call_args
        assert args[0] == "tool.call"
        assert kwargs["attributes"]["tool.name"] == "get_weather"
        assert kwargs["attributes"]["tool.source"] == "mcp"

    def test_mcp_connect_span_creates_span(self):
        from clawops.agent.tracing._spans import mcp_connect_span

        tracer, mock_span = self._make_mock_tracer()
        with patch("clawops.agent.tracing._spans._tracer", tracer):
            with mcp_connect_span("stdio", command="npx") as span:
                assert span is mock_span

        args, kwargs = tracer.start_as_current_span.call_args
        assert args[0] == "mcp.connect"
        assert kwargs["attributes"]["mcp.server.type"] == "stdio"
        assert kwargs["attributes"]["mcp.server.command"] == "npx"

    def test_mcp_call_tool_span_creates_span(self):
        from clawops.agent.tracing._spans import mcp_call_tool_span

        tracer, mock_span = self._make_mock_tracer()
        with patch("clawops.agent.tracing._spans._tracer", tracer):
            with mcp_call_tool_span("search") as span:
                assert span is mock_span

        args, kwargs = tracer.start_as_current_span.call_args
        assert args[0] == "mcp.call_tool"
        assert kwargs["attributes"]["mcp.tool.name"] == "search"

    def test_llm_session_span_creates_span(self):
        from clawops.agent.tracing._spans import llm_session_span

        tracer, mock_span = self._make_mock_tracer()
        with patch("clawops.agent.tracing._spans._tracer", tracer):
            with llm_session_span("gpt-realtime-mini", voice="marin") as span:
                assert span is mock_span

        args, kwargs = tracer.start_as_current_span.call_args
        assert args[0] == "llm.session"
        assert kwargs["attributes"]["gen_ai.system"] == "openai"
        assert kwargs["attributes"]["gen_ai.request.model"] == "gpt-realtime-mini"
        assert kwargs["attributes"]["gen_ai.request.voice"] == "marin"


class TestTracingExtra:
    def test_tracing_extra_in_pyproject(self):
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).parents[2] / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        extras = data["project"]["optional-dependencies"]
        assert "tracing" in extras
        deps = extras["tracing"]
        assert any("opentelemetry-api" in d for d in deps)


class TestAgentTracingParam:
    def test_agent_accepts_tracing_config(self):
        from clawops.agent import ClawOpsAgent
        from clawops.agent.tracing import TracingConfig

        agent = ClawOpsAgent(
            api_key="test",
            account_id="acc",
            from_="+821000000000",
            tracing=TracingConfig(),
        )
        assert agent._tracing is not None
        assert agent._tracing.enabled is True

    def test_agent_tracing_default_none(self):
        from clawops.agent import ClawOpsAgent

        agent = ClawOpsAgent(
            api_key="test",
            account_id="acc",
            from_="+821000000000",
        )
        assert agent._tracing is None


class TestCallSpanInstrumentation:
    @pytest.mark.asyncio
    async def test_start_call_session_uses_call_span_when_tracing(self):
        """_start_call_session이 tracing 활성화 시 call_span을 호출하는지 확인."""
        from clawops.agent._agent import ClawOpsAgent
        from clawops.agent.tracing import TracingConfig

        agent = ClawOpsAgent(
            api_key="test",
            account_id="acc",
            from_="+821000000000",
            tracing=TracingConfig(),
        )

        mock_call = MagicMock()
        mock_call.call_id = "call-001"
        mock_call.from_number = "+821012345678"
        mock_call.to_number = "+821000000000"
        mock_call._emit = AsyncMock()
        mock_call._send_audio_fn = None
        mock_call._send_clear_fn = None
        mock_call._hangup_fn = None

        with patch("clawops.agent._agent.call_span") as mock_span, \
             patch("clawops.agent._agent.MediaWebSocket") as mock_mws, \
             patch("clawops.agent._agent.RealtimeSession") as mock_rt:
            mock_span.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_span.return_value.__exit__ = MagicMock(return_value=False)
            mock_mws.return_value.connect = AsyncMock()
            mock_mws.return_value.send_audio = AsyncMock()
            mock_mws.return_value.send_clear = AsyncMock()
            mock_mws.return_value.close = AsyncMock()
            mock_rt.return_value.start = AsyncMock()
            mock_rt.return_value.stop = AsyncMock()

            await agent._start_call_session(mock_call, "wss://media")

            mock_span.assert_called_once_with(
                "call-001",
                from_number="+821012345678",
                to_number="+821000000000",
            )

    @pytest.mark.asyncio
    async def test_start_call_session_no_span_without_tracing(self):
        """tracing 비활성화 시 call_span을 호출하지 않는지 확인."""
        from clawops.agent._agent import ClawOpsAgent

        agent = ClawOpsAgent(
            api_key="test",
            account_id="acc",
            from_="+821000000000",
        )

        mock_call = MagicMock()
        mock_call.call_id = "call-002"
        mock_call.from_number = "+82"
        mock_call.to_number = "+82"
        mock_call._emit = AsyncMock()
        mock_call._send_audio_fn = None
        mock_call._send_clear_fn = None
        mock_call._hangup_fn = None

        with patch("clawops.agent._agent.call_span") as mock_span, \
             patch("clawops.agent._agent.MediaWebSocket") as mock_mws, \
             patch("clawops.agent._agent.RealtimeSession") as mock_rt:
            mock_mws.return_value.connect = AsyncMock()
            mock_mws.return_value.send_audio = AsyncMock()
            mock_mws.return_value.send_clear = AsyncMock()
            mock_mws.return_value.close = AsyncMock()
            mock_rt.return_value.start = AsyncMock()
            mock_rt.return_value.stop = AsyncMock()

            await agent._start_call_session(mock_call, "wss://media")

            mock_span.assert_not_called()


class TestMCPConnectSpanInstrumentation:
    @pytest.mark.asyncio
    async def test_mcp_connect_uses_span(self):
        """MCP 서버 연결 시 mcp_connect_span이 호출되는지 확인."""
        from clawops.agent._agent import ClawOpsAgent
        from clawops.agent.tracing import TracingConfig
        from clawops.agent.mcp import MCPServerStdio

        agent = ClawOpsAgent(
            api_key="test",
            account_id="acc",
            from_="+821000000000",
            tracing=TracingConfig(),
            mcp_servers=[MCPServerStdio("npx", args=["@mcp/test"])],
        )

        mock_call = MagicMock()
        mock_call.call_id = "call-002"
        mock_call.from_number = "+82"
        mock_call.to_number = "+82"
        mock_call._emit = AsyncMock()
        mock_call._send_audio_fn = None
        mock_call._send_clear_fn = None
        mock_call._hangup_fn = None

        with patch("clawops.agent._agent.call_span") as mock_cs, \
             patch("clawops.agent._agent.mcp_connect_span") as mock_mcs, \
             patch("clawops.agent._agent.MCPClient") as mock_mcp, \
             patch("clawops.agent._agent.MediaWebSocket") as mock_mws, \
             patch("clawops.agent._agent.RealtimeSession") as mock_rt:
            mock_cs.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_cs.return_value.__exit__ = MagicMock(return_value=False)
            mock_mcs.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_mcs.return_value.__exit__ = MagicMock(return_value=False)
            mock_mcp_instance = AsyncMock()
            mock_mcp_instance.connect = AsyncMock()
            mock_mcp_instance.close = AsyncMock()
            mock_mcp_instance.tools = []
            mock_mcp.return_value = mock_mcp_instance
            mock_mws.return_value.connect = AsyncMock()
            mock_mws.return_value.send_audio = AsyncMock()
            mock_mws.return_value.send_clear = AsyncMock()
            mock_mws.return_value.close = AsyncMock()
            mock_rt.return_value.start = AsyncMock()
            mock_rt.return_value.stop = AsyncMock()

            await agent._start_call_session(mock_call, "wss://media")

            mock_mcs.assert_called_once_with("stdio", command="npx")


class TestMCPCallToolSpanInstrumentation:
    @pytest.mark.asyncio
    async def test_call_tool_uses_span(self):
        from clawops.agent.mcp._client import MCPClient
        from clawops.agent.mcp import MCPServerStdio

        server = MCPServerStdio("npx")
        client = MCPClient(server)

        mock_session = AsyncMock()
        block = MagicMock()
        block.type = "text"
        block.text = "result"
        result_mock = MagicMock()
        result_mock.isError = False
        result_mock.content = [block]
        mock_session.call_tool = AsyncMock(return_value=result_mock)
        client._session = mock_session

        with patch("clawops.agent.mcp._client.mcp_call_tool_span") as mock_span:
            mock_span.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_span.return_value.__exit__ = MagicMock(return_value=False)

            result = await client.call_tool("search", {"q": "test"})

            assert result == "result"
            mock_span.assert_called_once_with("search")


class TestToolCallSpanInstrumentation:
    @pytest.mark.asyncio
    async def test_handle_tool_call_uses_span(self):
        from clawops.agent.pipeline._realtime_session import RealtimeSession, RealtimeConfig
        from clawops.agent._tool import ToolRegistry

        registry = ToolRegistry()

        async def dummy_tool(city: str) -> str:
            """Get weather."""
            return "Sunny"

        registry.register(dummy_tool)

        config = RealtimeConfig(
            system_prompt="test",
            openai_api_key="sk-test",
        )
        session = RealtimeSession(config, registry)

        mock_call = MagicMock()
        mock_call.send_audio = AsyncMock()
        session._call = mock_call
        session._ws = MagicMock()
        session._ws.closed = False
        session._ws.send_str = AsyncMock()

        item = {
            "name": "dummy_tool",
            "call_id": "call_abc",
            "arguments": '{"city": "Seoul"}',
        }

        with patch("clawops.agent.pipeline._realtime_session.tool_call_span") as mock_span:
            mock_span.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_span.return_value.__exit__ = MagicMock(return_value=False)

            await session._handle_tool_call(item)

            mock_span.assert_called_once_with("dummy_tool", "local")


class TestLLMSessionSpanInstrumentation:
    @pytest.mark.asyncio
    async def test_start_creates_llm_session_span(self):
        from clawops.agent.pipeline._realtime_session import RealtimeSession, RealtimeConfig
        from clawops.agent._tool import ToolRegistry

        config = RealtimeConfig(
            system_prompt="test",
            openai_api_key="sk-test",
            model="gpt-realtime-mini",
            voice="marin",
        )
        registry = ToolRegistry()
        session = RealtimeSession(config, registry)

        mock_call = MagicMock()

        with patch("clawops.agent.pipeline._realtime_session.llm_session_span") as mock_span, \
             patch("aiohttp.ClientSession") as mock_http:
            mock_span_cm = MagicMock()
            mock_span_cm.__enter__ = MagicMock(return_value=MagicMock())
            mock_span_cm.__exit__ = MagicMock(return_value=False)
            mock_span.return_value = mock_span_cm

            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_ws.send_str = AsyncMock()
            mock_ws.__aiter__ = MagicMock(return_value=iter([]))
            mock_http_inst = AsyncMock()
            mock_http_inst.ws_connect = AsyncMock(return_value=mock_ws)
            mock_http_inst.close = AsyncMock()
            mock_http.return_value = mock_http_inst

            await session.start(mock_call)

            mock_span.assert_called_once_with("gpt-realtime-mini", voice="marin")

            # cleanup
            await session.stop()
