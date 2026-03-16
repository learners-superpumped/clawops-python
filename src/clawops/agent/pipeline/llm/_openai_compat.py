"""OpenAI 호환 API 공통 베이스 LLM."""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

log = logging.getLogger("clawops.agent.pipeline")


class OpenAICompatibleLLM:
    """OpenAI 호환 API를 사용하는 LLM Provider의 공통 베이스.

    Ollama, Groq, Mistral, Together AI 등 OpenAI Chat Completions 호환
    엔드포인트를 제공하는 서비스에서 상속하여 사용한다.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def provider(self) -> str:
        return "openai_compatible"

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """messages → 텍스트 스트림. tool_call 시 JSON 마커 반환."""
        try:
            import openai
        except ImportError:
            raise ImportError(
                f"openai is required for {type(self).__name__}. "
                f"Install it with: pip install clawops[{self.provider}]"
            ) from None

        client = openai.AsyncOpenAI(base_url=self._base_url, api_key=self._api_key)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            stream = await client.chat.completions.create(**kwargs)

            tool_calls_acc: dict[int, dict[str, Any]] = {}
            has_tool_calls = False

            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                if delta.content:
                    yield delta.content

                if delta.tool_calls:
                    has_tool_calls = True
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": getattr(tc, "id", None) or "",
                                "function": {"name": "", "arguments": ""},
                            }
                        acc = tool_calls_acc[idx]
                        if tc.id:
                            acc["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                acc["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                acc["function"]["arguments"] += tc.function.arguments

                if choice.finish_reason == "tool_calls" and has_tool_calls:
                    result = {
                        "type": "tool_calls",
                        "tool_calls": [tool_calls_acc[i] for i in sorted(tool_calls_acc)],
                    }
                    yield json.dumps(result)

        finally:
            await client.close()
