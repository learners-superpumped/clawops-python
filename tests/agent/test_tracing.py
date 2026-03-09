"""OpenTelemetry tracing 테스트."""
from __future__ import annotations

from unittest.mock import patch, MagicMock


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
