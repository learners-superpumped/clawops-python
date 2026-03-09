"""OpenTelemetry tracing 테스트."""
from __future__ import annotations


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
