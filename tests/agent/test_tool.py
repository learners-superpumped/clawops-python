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
