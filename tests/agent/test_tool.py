# tests/agent/test_tool.py
import pytest
from clawops.agent._tool import ToolRegistry


def test_function_tool_decorator():
    registry = ToolRegistry()

    @registry.register
    async def get_weather(city: str, unit: str = "celsius") -> str:
        """도시의 날씨를 조회합니다."""
        return f"{city}: 20 {unit}"

    assert "get_weather" in registry
    tool = registry["get_weather"]
    assert tool.name == "get_weather"
    assert tool.description == "도시의 날씨를 조회합니다."


def test_tool_schema_generation():
    registry = ToolRegistry()

    @registry.register
    async def check_order(order_id: str) -> str:
        """주문 상태를 확인합니다."""
        return "delivered"

    schemas = registry.to_openai_tools()
    assert len(schemas) == 1
    schema = schemas[0]
    assert schema["type"] == "function"
    assert schema["name"] == "check_order"
    assert schema["description"] == "주문 상태를 확인합니다."
    params = schema["parameters"]
    assert params["type"] == "object"
    assert "order_id" in params["properties"]
    assert params["properties"]["order_id"]["type"] == "string"
    assert params["required"] == ["order_id"]


@pytest.mark.asyncio
async def test_tool_execution():
    registry = ToolRegistry()

    @registry.register
    async def add(a: int, b: int) -> str:
        """두 수를 더합니다."""
        return str(a + b)

    result = await registry.call("add", {"a": 3, "b": 5})
    assert result == "8"


@pytest.mark.asyncio
async def test_tool_not_found():
    registry = ToolRegistry()
    with pytest.raises(KeyError):
        await registry.call("nonexistent", {})


def test_tool_with_optional_params():
    registry = ToolRegistry()

    @registry.register
    async def search(query: str, limit: int = 10) -> str:
        """검색합니다."""
        return f"{query}:{limit}"

    schemas = registry.to_openai_tools()
    params = schemas[0]["parameters"]
    assert params["required"] == ["query"]
    assert "limit" in params["properties"]


# --- MCP Integration Tests ---

from unittest.mock import AsyncMock, MagicMock
from clawops._exceptions import AgentError


def _make_mock_client(tools=None):
    client = MagicMock()
    client.tools = tools or [
        {
            "type": "function",
            "name": "web_search",
            "description": "Search the web",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        }
    ]
    client.has_tool = MagicMock(return_value=True)
    client.call_tool = AsyncMock(return_value="result text")
    return client


def test_register_mcp_tools():
    registry = ToolRegistry()
    mock_client = _make_mock_client()

    registry.register_mcp_tools([mock_client])

    assert "web_search" in registry
    schemas = registry.to_openai_tools()
    names = [s["name"] for s in schemas]
    assert "web_search" in names


def test_name_conflict_raises_error():
    registry = ToolRegistry()

    @registry.register
    async def web_search(query: str) -> str:
        """Local search."""
        return query

    mock_client = _make_mock_client()

    with pytest.raises(AgentError, match="Tool name conflict: web_search"):
        registry.register_mcp_tools([mock_client])


@pytest.mark.asyncio
async def test_call_mcp_tool():
    registry = ToolRegistry()
    mock_client = _make_mock_client()
    registry.register_mcp_tools([mock_client])

    result = await registry.call("web_search", {"query": "hello"})

    assert result == "result text"
    mock_client.call_tool.assert_awaited_once_with("web_search", {"query": "hello"})


def test_clear_mcp_tools():
    registry = ToolRegistry()
    mock_client = _make_mock_client()
    registry.register_mcp_tools([mock_client])

    assert "web_search" in registry
    registry.clear_mcp_tools()
    assert "web_search" not in registry


def test_to_openai_tools_includes_mcp():
    registry = ToolRegistry()

    @registry.register
    async def local_tool(x: str) -> str:
        """A local tool."""
        return x

    mock_client = _make_mock_client()
    registry.register_mcp_tools([mock_client])

    schemas = registry.to_openai_tools()
    names = [s["name"] for s in schemas]
    assert "local_tool" in names
    assert "web_search" in names
    assert len(schemas) == 2
