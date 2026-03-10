import json
import sys
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline._anthropic_llm import AnthropicLLM
from clawops.agent.pipeline._base import LLM


@dataclass
class FakeEvent:
    type: str
    content_block: Any = None
    delta: Any = None


@dataclass
class FakeBlock:
    type: str
    id: str = ""
    name: str = ""


@dataclass
class FakeDelta:
    type: str
    text: str = ""
    partial_json: str = ""


def test_anthropic_llm_implements_protocol():
    llm = AnthropicLLM(api_key="test-key")
    assert isinstance(llm, LLM)


@pytest.mark.asyncio
async def test_anthropic_llm_generate_text():
    """텍스트 응답을 스트리밍으로 반환."""
    event1 = FakeEvent(type="content_block_start", content_block=FakeBlock(type="text"))
    event2 = FakeEvent(type="content_block_delta", delta=FakeDelta(type="text_delta", text="안녕"))
    event3 = FakeEvent(type="content_block_delta", delta=FakeDelta(type="text_delta", text="하세요"))
    event4 = FakeEvent(type="message_stop")

    class MockStream:
        async def __aiter__(self):
            for e in [event1, event2, event3, event4]:
                yield e

        async def __aenter__(self):
            return self.__aiter__()

        async def __aexit__(self, *args):
            pass

    mock_stream_ctx = MockStream()

    mock_client = AsyncMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.close = AsyncMock()

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic = MagicMock(return_value=mock_client)

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        llm = AnthropicLLM(api_key="test-key")
        messages = [{"role": "user", "content": "인사해주세요"}]
        result = []
        async for token in llm.generate(messages):
            result.append(token)

    assert "".join(result) == "안녕하세요"


@pytest.mark.asyncio
async def test_anthropic_llm_generate_tool_call():
    """tool_call 응답은 JSON으로 직렬화하여 반환."""
    event1 = FakeEvent(type="content_block_start", content_block=FakeBlock(type="tool_use", id="toolu_123", name="get_weather"))
    event2 = FakeEvent(type="content_block_delta", delta=FakeDelta(type="input_json_delta", partial_json='{"city":"서울"}'))
    event3 = FakeEvent(type="content_block_stop")
    event4 = FakeEvent(type="message_stop")

    class MockStream:
        async def __aiter__(self):
            for e in [event1, event2, event3, event4]:
                yield e

        async def __aenter__(self):
            return self.__aiter__()

        async def __aexit__(self, *args):
            pass

    mock_stream_ctx = MockStream()

    mock_client = AsyncMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.close = AsyncMock()

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic = MagicMock(return_value=mock_client)

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        llm = AnthropicLLM(api_key="test-key")
        messages = [{"role": "user", "content": "서울 날씨"}]
        tools = [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}]
        result = []
        async for token in llm.generate(messages, tools=tools):
            result.append(token)

    combined = "".join(result)
    parsed = json.loads(combined)
    assert parsed["type"] == "tool_calls"
    assert parsed["tool_calls"][0]["function"]["name"] == "get_weather"
    assert parsed["tool_calls"][0]["id"] == "toolu_123"
