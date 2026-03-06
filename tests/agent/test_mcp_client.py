# tests/agent/test_mcp_client.py
"""MCPClient 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops._exceptions import AgentError
from clawops.agent.mcp import MCPServerHTTP, MCPServerStdio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_tool(name: str, description: str, input_schema: dict) -> MagicMock:
    """MCP Tool 객체를 모방하는 mock 생성."""
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.inputSchema = input_schema
    return tool


def _make_mock_call_result(text: str, *, is_error: bool = False) -> MagicMock:
    """MCP CallToolResult 객체를 모방하는 mock 생성."""
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = text

    result = MagicMock()
    result.isError = is_error
    result.content = [content_block]
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMCPClientInit:
    """MCPClient 초기화 테스트."""

    def test_init_with_stdio_server(self):
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerStdio("npx", args=["@mcp/server"])
        client = MCPClient(server)
        assert client._server is server
        assert client._session is None
        assert client.tools == []

    def test_init_with_http_server(self):
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerHTTP("https://example.com/mcp")
        client = MCPClient(server)
        assert client._server is server
        assert client._session is None
        assert client.tools == []


class TestMCPClientConnect:
    """MCPClient.connect() 테스트."""

    @pytest.mark.asyncio
    async def test_connect_stdio(self):
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerStdio("npx", args=["@mcp/server"])
        client = MCPClient(server)

        mock_session = AsyncMock()
        mock_tools = [
            _make_mock_tool("get_weather", "Get weather info", {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            }),
        ]
        mock_session.list_tools.return_value = MagicMock(tools=mock_tools)

        with patch("clawops.agent.mcp._client._HAS_MCP", True), patch(
            "clawops.agent.mcp._client._connect_stdio",
            new_callable=AsyncMock,
            return_value=(mock_session, []),
        ):
            await client.connect()

        assert client._session is mock_session
        assert len(client.tools) == 1
        tool = client.tools[0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "get_weather"
        assert tool["function"]["description"] == "Get weather info"
        assert tool["function"]["parameters"] == {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        }

    @pytest.mark.asyncio
    async def test_connect_http(self):
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerHTTP("https://example.com/mcp")
        client = MCPClient(server)

        mock_session = AsyncMock()
        mock_tools = [
            _make_mock_tool("search", "Search the web", {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            }),
        ]
        mock_session.list_tools.return_value = MagicMock(tools=mock_tools)

        with patch("clawops.agent.mcp._client._HAS_MCP", True), patch(
            "clawops.agent.mcp._client._connect_http",
            new_callable=AsyncMock,
            return_value=(mock_session, []),
        ):
            await client.connect()

        assert client._session is mock_session
        assert len(client.tools) == 1
        assert client.tools[0]["function"]["name"] == "search"

    @pytest.mark.asyncio
    async def test_connect_lists_multiple_tools(self):
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerStdio("npx")
        client = MCPClient(server)

        mock_session = AsyncMock()
        mock_tools = [
            _make_mock_tool("tool_a", "Tool A", {"type": "object", "properties": {}}),
            _make_mock_tool("tool_b", "Tool B", {"type": "object", "properties": {}}),
        ]
        mock_session.list_tools.return_value = MagicMock(tools=mock_tools)

        with patch("clawops.agent.mcp._client._HAS_MCP", True), patch(
            "clawops.agent.mcp._client._connect_stdio",
            new_callable=AsyncMock,
            return_value=(mock_session, []),
        ):
            await client.connect()

        assert len(client.tools) == 2
        assert client.has_tool("tool_a")
        assert client.has_tool("tool_b")
        assert not client.has_tool("tool_c")


class TestMCPClientCallTool:
    """MCPClient.call_tool() 테스트."""

    @pytest.mark.asyncio
    async def test_call_tool_normal(self):
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerStdio("npx")
        client = MCPClient(server)

        mock_session = AsyncMock()
        mock_tools = [
            _make_mock_tool("get_weather", "Get weather", {"type": "object", "properties": {}}),
        ]
        mock_session.list_tools.return_value = MagicMock(tools=mock_tools)
        mock_session.call_tool.return_value = _make_mock_call_result("Sunny, 25C")

        with patch("clawops.agent.mcp._client._HAS_MCP", True), patch(
            "clawops.agent.mcp._client._connect_stdio",
            new_callable=AsyncMock,
            return_value=(mock_session, []),
        ):
            await client.connect()

        result = await client.call_tool("get_weather", {"city": "Seoul"})
        assert result == "Sunny, 25C"
        mock_session.call_tool.assert_awaited_once_with("get_weather", {"city": "Seoul"})

    @pytest.mark.asyncio
    async def test_call_tool_error_result(self):
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerStdio("npx")
        client = MCPClient(server)

        mock_session = AsyncMock()
        mock_tools = [
            _make_mock_tool("fail_tool", "Will fail", {"type": "object", "properties": {}}),
        ]
        mock_session.list_tools.return_value = MagicMock(tools=mock_tools)
        mock_session.call_tool.return_value = _make_mock_call_result(
            "something went wrong", is_error=True
        )

        with patch("clawops.agent.mcp._client._HAS_MCP", True), patch(
            "clawops.agent.mcp._client._connect_stdio",
            new_callable=AsyncMock,
            return_value=(mock_session, []),
        ):
            await client.connect()

        result = await client.call_tool("fail_tool", {})
        assert result == "MCP Error: something went wrong"

    @pytest.mark.asyncio
    async def test_call_tool_multiple_content_blocks(self):
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerStdio("npx")
        client = MCPClient(server)

        mock_session = AsyncMock()
        mock_tools = [
            _make_mock_tool("multi", "Multi result", {"type": "object", "properties": {}}),
        ]
        mock_session.list_tools.return_value = MagicMock(tools=mock_tools)

        # Create result with multiple content blocks
        block1 = MagicMock()
        block1.type = "text"
        block1.text = "line1"
        block2 = MagicMock()
        block2.type = "text"
        block2.text = "line2"
        result_mock = MagicMock()
        result_mock.isError = False
        result_mock.content = [block1, block2]
        mock_session.call_tool.return_value = result_mock

        with patch("clawops.agent.mcp._client._HAS_MCP", True), patch(
            "clawops.agent.mcp._client._connect_stdio",
            new_callable=AsyncMock,
            return_value=(mock_session, []),
        ):
            await client.connect()

        result = await client.call_tool("multi", {})
        assert result == "line1\nline2"


class TestMCPClientClose:
    """MCPClient.close() 테스트."""

    @pytest.mark.asyncio
    async def test_close_cleans_up(self):
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerStdio("npx")
        client = MCPClient(server)

        mock_session = AsyncMock()
        mock_tools = [
            _make_mock_tool("tool_a", "Tool A", {"type": "object", "properties": {}}),
        ]
        mock_session.list_tools.return_value = MagicMock(tools=mock_tools)

        # Create mock cleanup context managers
        mock_cm1 = AsyncMock()
        mock_cm2 = AsyncMock()

        with patch("clawops.agent.mcp._client._HAS_MCP", True), patch(
            "clawops.agent.mcp._client._connect_stdio",
            new_callable=AsyncMock,
            return_value=(mock_session, [mock_cm1, mock_cm2]),
        ):
            await client.connect()

        assert client._session is not None
        assert len(client.tools) == 1
        assert client.has_tool("tool_a")

        await client.close()

        assert client._session is None
        assert client.tools == []
        assert not client.has_tool("tool_a")
        # Verify context managers were exited
        mock_cm1.__aexit__.assert_awaited_once()
        mock_cm2.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_without_connect(self):
        """close() should be safe to call even without connect()."""
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerStdio("npx")
        client = MCPClient(server)
        # Should not raise
        await client.close()


class TestMCPClientMissingPackage:
    """mcp 패키지 미설치 시 에러 테스트."""

    @pytest.mark.asyncio
    async def test_missing_mcp_package_raises_agent_error(self):
        from clawops.agent.mcp._client import MCPClient

        server = MCPServerStdio("npx")
        client = MCPClient(server)

        with patch("clawops.agent.mcp._client._HAS_MCP", False):
            with pytest.raises(AgentError, match="pip install clawops\\[mcp\\]"):
                await client.connect()
