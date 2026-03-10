import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline._gemini_llm import GeminiLLM
from clawops.agent.pipeline._base import LLM


def test_gemini_llm_implements_protocol():
    llm = GeminiLLM(api_key="test-key")
    assert isinstance(llm, LLM)


@pytest.mark.asyncio
async def test_gemini_llm_generate_text():
    """텍스트 응답을 스트리밍으로 반환."""
    chunk1 = MagicMock()
    chunk1.candidates = [MagicMock()]
    part1 = MagicMock()
    part1.text = "안녕"
    part1.function_call = None
    chunk1.candidates[0].content.parts = [part1]

    chunk2 = MagicMock()
    chunk2.candidates = [MagicMock()]
    part2 = MagicMock()
    part2.text = "하세요"
    part2.function_call = None
    chunk2.candidates[0].content.parts = [part2]

    async def mock_stream(*args, **kwargs):
        yield chunk1
        yield chunk2

    mock_types = MagicMock()
    mock_types.Content = MagicMock()
    mock_types.Part = MagicMock()
    mock_types.GenerateContentConfig = MagicMock(return_value=MagicMock())

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = mock_stream

    mock_genai = MagicMock()
    mock_genai.Client = MagicMock(return_value=mock_client)
    mock_genai.types = mock_types

    mock_google_genai = MagicMock()
    mock_google_genai.types = mock_types

    mock_google = MagicMock()
    mock_google.genai = mock_genai

    with patch.dict(sys.modules, {
        "google": mock_google,
        "google.genai": mock_genai,
        "google.genai.types": mock_types,
    }):
        llm = GeminiLLM(api_key="test-key")
        messages = [{"role": "user", "content": "인사해주세요"}]
        result = []
        async for token in llm.generate(messages):
            result.append(token)

    assert "".join(result) == "안녕하세요"


@pytest.mark.asyncio
async def test_gemini_llm_generate_tool_call():
    """tool_call 응답은 JSON으로 직렬화하여 반환."""
    chunk = MagicMock()
    chunk.candidates = [MagicMock()]
    part = MagicMock()
    part.text = None
    part.function_call = MagicMock()
    part.function_call.name = "get_weather"
    part.function_call.args = {"city": "서울"}
    chunk.candidates[0].content.parts = [part]

    async def mock_stream(*args, **kwargs):
        yield chunk

    mock_types = MagicMock()
    mock_types.Content = MagicMock()
    mock_types.Part = MagicMock()
    mock_types.GenerateContentConfig = MagicMock(return_value=MagicMock())
    mock_types.Tool = MagicMock()
    mock_types.FunctionDeclaration = MagicMock()

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = mock_stream

    mock_genai = MagicMock()
    mock_genai.Client = MagicMock(return_value=mock_client)
    mock_genai.types = mock_types

    mock_google_genai = MagicMock()
    mock_google_genai.types = mock_types

    mock_google = MagicMock()
    mock_google.genai = mock_genai

    with patch.dict(sys.modules, {
        "google": mock_google,
        "google.genai": mock_genai,
        "google.genai.types": mock_types,
    }):
        llm = GeminiLLM(api_key="test-key")
        messages = [{"role": "user", "content": "서울 날씨"}]
        tools = [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}]
        result = []
        async for token in llm.generate(messages, tools=tools):
            result.append(token)

    combined = "".join(result)
    parsed = json.loads(combined)
    assert parsed["type"] == "tool_calls"
    assert parsed["tool_calls"][0]["function"]["name"] == "get_weather"
    assert parsed["tool_calls"][0]["id"] == "call_get_weather_0"
