import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline._openai_llm import OpenAILLM
from clawops.agent.pipeline._base import LLM


def test_openai_llm_implements_protocol():
    llm = OpenAILLM(api_key="test-key")
    assert isinstance(llm, LLM)


@pytest.mark.asyncio
async def test_openai_llm_generate_text():
    """텍스트 응답을 스트리밍으로 반환."""
    mock_chunk_1 = MagicMock()
    mock_chunk_1.choices = [MagicMock(delta=MagicMock(content="안녕", tool_calls=None), finish_reason=None)]
    mock_chunk_2 = MagicMock()
    mock_chunk_2.choices = [MagicMock(delta=MagicMock(content="하세요", tool_calls=None), finish_reason="stop")]

    async def mock_stream():
        yield mock_chunk_1
        yield mock_chunk_2

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())
    mock_client.close = AsyncMock()

    mock_openai = MagicMock()
    mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)

    with patch.dict(sys.modules, {"openai": mock_openai}):
        llm = OpenAILLM(api_key="test-key")
        messages = [{"role": "user", "content": "인사해주세요"}]
        result = []
        async for token in llm.generate(messages):
            result.append(token)

    assert "".join(result) == "안녕하세요"


@pytest.mark.asyncio
async def test_openai_llm_generate_tool_call():
    """tool_call 응답은 JSON으로 직렬화하여 반환."""
    tool_call_mock = MagicMock()
    tool_call_mock.index = 0
    tool_call_mock.id = "call_123"
    tool_call_mock.function = MagicMock()
    tool_call_mock.function.name = "get_weather"
    tool_call_mock.function.arguments = '{"city":"서울"}'

    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock(
        delta=MagicMock(content=None, tool_calls=[tool_call_mock]),
        finish_reason="tool_calls",
    )]

    async def mock_stream():
        yield mock_chunk

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())
    mock_client.close = AsyncMock()

    mock_openai = MagicMock()
    mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)

    with patch.dict(sys.modules, {"openai": mock_openai}):
        llm = OpenAILLM(api_key="test-key")
        messages = [{"role": "user", "content": "서울 날씨"}]
        tools = [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}]
        result = []
        async for token in llm.generate(messages, tools=tools):
            result.append(token)

    combined = "".join(result)
    parsed = json.loads(combined)
    assert parsed["type"] == "tool_calls"
    assert parsed["tool_calls"][0]["function"]["name"] == "get_weather"
