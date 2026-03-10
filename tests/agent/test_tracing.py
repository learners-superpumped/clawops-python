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
            with llm_session_span("gpt-realtime-1.5") as span:
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
        with patch("clawops.agent.tracing._spans._tracer", tracer), \
             patch("clawops.agent.tracing._spans._enabled", True):
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
        with patch("clawops.agent.tracing._spans._tracer", tracer), \
             patch("clawops.agent.tracing._spans._enabled", True):
            with tool_call_span("get_weather", "mcp") as span:
                assert span is mock_span

        args, kwargs = tracer.start_as_current_span.call_args
        assert args[0] == "tool.call"
        assert kwargs["attributes"]["tool.name"] == "get_weather"
        assert kwargs["attributes"]["tool.source"] == "mcp"

    def test_mcp_connect_span_creates_span(self):
        from clawops.agent.tracing._spans import mcp_connect_span

        tracer, mock_span = self._make_mock_tracer()
        with patch("clawops.agent.tracing._spans._tracer", tracer), \
             patch("clawops.agent.tracing._spans._enabled", True):
            with mcp_connect_span("stdio", command="npx") as span:
                assert span is mock_span

        args, kwargs = tracer.start_as_current_span.call_args
        assert args[0] == "mcp.connect"
        assert kwargs["attributes"]["mcp.server.type"] == "stdio"
        assert kwargs["attributes"]["mcp.server.command"] == "npx"

    def test_mcp_call_tool_span_creates_span(self):
        from clawops.agent.tracing._spans import mcp_call_tool_span

        tracer, mock_span = self._make_mock_tracer()
        with patch("clawops.agent.tracing._spans._tracer", tracer), \
             patch("clawops.agent.tracing._spans._enabled", True):
            with mcp_call_tool_span("search") as span:
                assert span is mock_span

        args, kwargs = tracer.start_as_current_span.call_args
        assert args[0] == "mcp.call_tool"
        assert kwargs["attributes"]["mcp.tool.name"] == "search"

    def test_llm_session_span_creates_span(self):
        from clawops.agent.tracing._spans import llm_session_span

        tracer, mock_span = self._make_mock_tracer()
        with patch("clawops.agent.tracing._spans._tracer", tracer), \
             patch("clawops.agent.tracing._spans._enabled", True):
            with llm_session_span("gpt-realtime-1.5", voice="marin") as span:
                assert span is mock_span

        args, kwargs = tracer.start_as_current_span.call_args
        assert args[0] == "llm.session"
        assert kwargs["attributes"]["gen_ai.system"] == "openai"
        assert kwargs["attributes"]["gen_ai.request.model"] == "gpt-realtime-1.5"
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


def _make_session():
    from clawops.agent.pipeline._openai_realtime import OpenAIRealtime
    return OpenAIRealtime(api_key="sk-test")


class TestAgentTracingParam:
    def test_agent_accepts_tracing_config(self):
        from clawops.agent import ClawOpsAgent
        from clawops.agent.tracing import TracingConfig

        agent = ClawOpsAgent(
            api_key="test",
            account_id="acc",
            from_="+821000000000",
            session=_make_session(),
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
            session=_make_session(),
        )
        assert agent._tracing is None


class TestCallSpanInstrumentation:
    @pytest.mark.asyncio
    async def test_start_call_session_uses_call_span_when_tracing(self):
        """_start_call_session이 tracing 활성화 시 call_span을 호출하는지 확인."""
        from clawops.agent._agent import ClawOpsAgent
        from clawops.agent.tracing import TracingConfig

        mock_session = AsyncMock()
        mock_session.start = AsyncMock()
        mock_session.stop = AsyncMock()
        mock_session.feed_audio = AsyncMock()
        mock_session.set_tool_registry = MagicMock()

        agent = ClawOpsAgent(
            api_key="test",
            account_id="acc",
            from_="+821000000000",
            session=mock_session,
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
             patch("clawops.agent._agent.MediaWebSocket") as mock_mws:
            mock_span.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_span.return_value.__exit__ = MagicMock(return_value=False)
            mock_mws.return_value.connect = AsyncMock()
            mock_mws.return_value.send_audio = AsyncMock()
            mock_mws.return_value.send_clear = AsyncMock()
            mock_mws.return_value.close = AsyncMock()

            await agent._start_call_session(mock_call, "wss://media")

            mock_span.assert_called_once_with(
                "call-001",
                from_number="+821012345678",
                to_number="+821000000000",
            )

    @pytest.mark.asyncio
    async def test_start_call_session_always_calls_call_span(self):
        """tracing 미설정 시에도 call_span은 항상 호출되지만 no-op으로 동작."""
        from clawops.agent._agent import ClawOpsAgent

        mock_session = AsyncMock()
        mock_session.start = AsyncMock()
        mock_session.stop = AsyncMock()
        mock_session.feed_audio = AsyncMock()
        mock_session.set_tool_registry = MagicMock()

        agent = ClawOpsAgent(
            api_key="test",
            account_id="acc",
            from_="+821000000000",
            session=mock_session,
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
             patch("clawops.agent._agent.MediaWebSocket") as mock_mws:
            mock_span.return_value.__enter__ = MagicMock(return_value=None)
            mock_span.return_value.__exit__ = MagicMock(return_value=False)
            mock_mws.return_value.connect = AsyncMock()
            mock_mws.return_value.send_audio = AsyncMock()
            mock_mws.return_value.send_clear = AsyncMock()
            mock_mws.return_value.close = AsyncMock()

            await agent._start_call_session(mock_call, "wss://media")

            mock_span.assert_called_once()


class TestMCPConnectSpanInstrumentation:
    @pytest.mark.asyncio
    async def test_mcp_connect_uses_span(self):
        """MCP 서버 연결 시 mcp_connect_span이 호출되는지 확인."""
        from clawops.agent._agent import ClawOpsAgent
        from clawops.agent.tracing import TracingConfig
        from clawops.agent.mcp import MCPServerStdio

        mock_session = AsyncMock()
        mock_session.start = AsyncMock()
        mock_session.stop = AsyncMock()
        mock_session.feed_audio = AsyncMock()
        mock_session.set_tool_registry = MagicMock()

        agent = ClawOpsAgent(
            api_key="test",
            account_id="acc",
            from_="+821000000000",
            session=mock_session,
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
             patch("clawops.agent._agent.MediaWebSocket") as mock_mws:
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
        from clawops.agent.pipeline._openai_realtime import OpenAIRealtime
        from clawops.agent._tool import ToolRegistry

        registry = ToolRegistry()

        async def dummy_tool(city: str) -> str:
            """Get weather."""
            return "Sunny"

        registry.register(dummy_tool)

        session = OpenAIRealtime(
            api_key="sk-test",
            system_prompt="test",
            tool_registry=registry,
        )

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

        with patch("clawops.agent.pipeline._openai_realtime.tool_call_span") as mock_span:
            mock_span.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_span.return_value.__exit__ = MagicMock(return_value=False)

            await session._handle_tool_call(item)

            mock_span.assert_called_once_with("dummy_tool", "local")


class TestLLMSessionSpanInstrumentation:
    @pytest.mark.asyncio
    async def test_start_creates_llm_session_span(self):
        from clawops.agent.pipeline._openai_realtime import OpenAIRealtime
        from clawops.agent._tool import ToolRegistry

        registry = ToolRegistry()
        session = OpenAIRealtime(
            api_key="sk-test",
            system_prompt="test",
            model="gpt-realtime-1.5",
            voice="marin",
            tool_registry=registry,
        )

        mock_call = MagicMock()

        with patch("clawops.agent.pipeline._openai_realtime.llm_session_span") as mock_span, \
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

            mock_span.assert_called_once_with("gpt-realtime-1.5", voice="marin")

            # cleanup
            await session.stop()


class TestSetupTracing:
    """setup_tracing이 _enabled / _tracer를 올바르게 설정하는지 확인."""

    def test_tracing_disabled_by_default(self):
        """TracingConfig 없이 Agent 생성 시 _enabled=False."""
        import clawops.agent.tracing._spans as spans_mod
        # Reset state
        spans_mod._enabled = False
        spans_mod._tracer = None

        assert spans_mod._enabled is False

        # Span helpers yield None when disabled
        with spans_mod.call_span("x") as s:
            assert s is None

    def test_setup_tracing_enables(self):
        """setup_tracing(TracingConfig(enabled=True))이 _enabled=True로 설정."""
        import clawops.agent.tracing._spans as spans_mod
        from clawops.agent.tracing._config import TracingConfig

        # Ensure clean state
        spans_mod._enabled = False
        spans_mod._tracer = None

        config = TracingConfig(enabled=True)
        with patch.object(spans_mod, "_has_otel", True), \
             patch.object(spans_mod, "_otel_trace") as mock_otel:
            mock_tracer = MagicMock()
            mock_otel.get_tracer.return_value = mock_tracer
            spans_mod.setup_tracing(config)

            assert spans_mod._enabled is True
            assert spans_mod._tracer is mock_tracer
            mock_otel.get_tracer.assert_called_once_with("clawops.agent")

        # Cleanup
        spans_mod._enabled = False
        spans_mod._tracer = None

    def test_setup_tracing_disabled_config(self):
        """TracingConfig(enabled=False)이면 _enabled=False."""
        import clawops.agent.tracing._spans as spans_mod
        from clawops.agent.tracing._config import TracingConfig

        spans_mod._enabled = True
        spans_mod._tracer = MagicMock()

        config = TracingConfig(enabled=False)
        spans_mod.setup_tracing(config)

        assert spans_mod._enabled is False
        assert spans_mod._tracer is None

    def test_setup_tracing_with_custom_tracer_provider(self):
        """tracer_provider가 지정되면 해당 provider에서 tracer를 가져온다."""
        import clawops.agent.tracing._spans as spans_mod
        from clawops.agent.tracing._config import TracingConfig

        spans_mod._enabled = False
        spans_mod._tracer = None

        mock_provider = MagicMock()
        mock_tracer = MagicMock()
        mock_provider.get_tracer.return_value = mock_tracer

        config = TracingConfig(enabled=True, tracer_provider=mock_provider)
        with patch.object(spans_mod, "_has_otel", True):
            spans_mod.setup_tracing(config)

        assert spans_mod._enabled is True
        assert spans_mod._tracer is mock_tracer
        mock_provider.get_tracer.assert_called_once_with("clawops.agent")

        # Cleanup
        spans_mod._enabled = False
        spans_mod._tracer = None

    def test_setup_tracing_no_otel_installed(self):
        """opentelemetry 미설치 시 enabled=True여도 _enabled=False."""
        import clawops.agent.tracing._spans as spans_mod
        from clawops.agent.tracing._config import TracingConfig

        spans_mod._enabled = False
        spans_mod._tracer = None

        config = TracingConfig(enabled=True)
        with patch.object(spans_mod, "_has_otel", False):
            spans_mod.setup_tracing(config)

        assert spans_mod._enabled is False
        assert spans_mod._tracer is None

    def test_span_noop_when_enabled_false(self):
        """_enabled=False일 때 tracer가 있어도 span은 no-op."""
        import clawops.agent.tracing._spans as spans_mod

        spans_mod._enabled = False
        spans_mod._tracer = MagicMock()

        with spans_mod.call_span("x") as s:
            assert s is None

        # tracer.start_as_current_span should NOT have been called
        spans_mod._tracer.start_as_current_span.assert_not_called()

        # Cleanup
        spans_mod._tracer = None


class TestAgentCallsSetupTracing:
    def test_agent_init_calls_setup_tracing(self):
        """Agent에 TracingConfig을 전달하면 setup_tracing이 호출된다."""
        from clawops.agent._agent import ClawOpsAgent
        from clawops.agent.tracing import TracingConfig

        config = TracingConfig(enabled=True)
        with patch("clawops.agent._agent.setup_tracing") as mock_setup:
            ClawOpsAgent(
                api_key="test",
                account_id="acc",
                from_="+821000000000",
                session=_make_session(),
                tracing=config,
            )
            mock_setup.assert_called_once_with(config)

    def test_agent_init_no_setup_tracing_without_config(self):
        """TracingConfig 미전달 시 setup_tracing이 호출되지 않는다."""
        with patch("clawops.agent._agent.setup_tracing") as mock_setup:
            from clawops.agent._agent import ClawOpsAgent
            ClawOpsAgent(
                api_key="test",
                account_id="acc",
                from_="+821000000000",
                session=_make_session(),
            )
            mock_setup.assert_not_called()


class TestLLMSpanExceptionPropagation:
    @pytest.mark.asyncio
    async def test_cleanup_passes_exception_info_to_span_exit(self):
        """_cleanup이 활성 예외 정보를 span __exit__에 전달하는지 확인."""
        from clawops.agent.pipeline._openai_realtime import OpenAIRealtime
        from clawops.agent._tool import ToolRegistry

        registry = ToolRegistry()
        session = OpenAIRealtime(
            api_key="sk-test",
            system_prompt="test",
            tool_registry=registry,
        )

        mock_span_ctx = MagicMock()
        mock_span_ctx.__exit__ = MagicMock(return_value=False)
        session._llm_span_ctx = mock_span_ctx
        session._llm_span = MagicMock()

        # Simulate calling _cleanup during exception handling
        exc = RuntimeError("test error")
        try:
            raise exc
        except RuntimeError:
            await session._cleanup()

        # Verify __exit__ was called with exception info, not (None, None, None)
        mock_span_ctx.__exit__.assert_called_once()
        call_args = mock_span_ctx.__exit__.call_args[0]
        assert call_args[0] is RuntimeError
        assert call_args[1] is exc
        assert call_args[2] is not None  # traceback
