"""OpenAI 호환 LLM Provider 공통 테스트.

OllamaLLM, MistralLLM, GroqLLM, PerplexityLLM, TogetherLLM,
FireworksLLM, DeepSeekLLM, XaiLLM을 모두 테스트한다.
"""
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline._base import LLM
from clawops.agent.pipeline.llm._ollama import OllamaLLM
from clawops.agent.pipeline.llm._mistral import MistralLLM
from clawops.agent.pipeline.llm._groq import GroqLLM
from clawops.agent.pipeline.llm._perplexity import PerplexityLLM
from clawops.agent.pipeline.llm._together import TogetherLLM
from clawops.agent.pipeline.llm._fireworks import FireworksLLM
from clawops.agent.pipeline.llm._deepseek import DeepSeekLLM
from clawops.agent.pipeline.llm._xai import XaiLLM


PROVIDERS = [
    (OllamaLLM, {}, "http://localhost:11434/v1", "ollama"),
    (MistralLLM, {"api_key": "k"}, "https://api.mistral.ai/v1", "k"),
    (GroqLLM, {"api_key": "k"}, "https://api.groq.com/openai/v1", "k"),  # meta-llama/llama-4-scout-17b-16e-instruct
    (PerplexityLLM, {"api_key": "k"}, "https://api.perplexity.ai", "k"),
    (TogetherLLM, {"api_key": "k"}, "https://api.together.xyz/v1", "k"),
    (FireworksLLM, {"api_key": "k"}, "https://api.fireworks.ai/inference/v1", "k"),
    (DeepSeekLLM, {"api_key": "k"}, "https://api.deepseek.com", "k"),
    (XaiLLM, {"api_key": "k"}, "https://api.x.ai/v1", "k"),
]


@pytest.mark.parametrize("cls,kwargs,expected_url,expected_key", PROVIDERS, ids=lambda x: x.__name__ if isinstance(x, type) else "")
def test_implements_protocol(cls, kwargs, expected_url, expected_key):
    llm = cls(**kwargs)
    assert isinstance(llm, LLM)


@pytest.mark.parametrize("cls,kwargs,expected_url,expected_key", PROVIDERS, ids=lambda x: x.__name__ if isinstance(x, type) else "")
def test_base_url_and_api_key(cls, kwargs, expected_url, expected_key):
    llm = cls(**kwargs)
    assert llm._base_url == expected_url
    assert llm._api_key == expected_key


@pytest.mark.parametrize("cls,kwargs,expected_url,expected_key", PROVIDERS, ids=lambda x: x.__name__ if isinstance(x, type) else "")
@pytest.mark.asyncio
async def test_generate_text(cls, kwargs, expected_url, expected_key):
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
        llm = cls(**kwargs)
        result = []
        async for token in llm.generate([{"role": "user", "content": "인사"}]):
            result.append(token)

    assert "".join(result) == "안녕하세요"
    mock_openai.AsyncOpenAI.assert_called_once_with(base_url=expected_url, api_key=expected_key)


@pytest.mark.parametrize("cls,kwargs,expected_url,expected_key", PROVIDERS, ids=lambda x: x.__name__ if isinstance(x, type) else "")
@pytest.mark.asyncio
async def test_generate_tool_call(cls, kwargs, expected_url, expected_key):
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
        llm = cls(**kwargs)
        tools = [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}]
        result = []
        async for token in llm.generate([{"role": "user", "content": "날씨"}], tools=tools):
            result.append(token)

    parsed = json.loads("".join(result))
    assert parsed["type"] == "tool_calls"
    assert parsed["tool_calls"][0]["function"]["name"] == "get_weather"
