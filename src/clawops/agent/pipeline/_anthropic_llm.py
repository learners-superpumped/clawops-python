"""Anthropic Claude 스트리밍 LLM."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator

log = logging.getLogger("clawops.agent.pipeline")


class AnthropicLLM:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """messages → 텍스트 스트림. tool_call 시 JSON 마커 반환."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._api_key)

        # OpenAI format → Anthropic format 변환
        system_text = ""
        converted: list[dict[str, Any]] = []
        for msg in messages:
            role = msg["role"]
            if role == "system":
                system_text = msg["content"]
            elif role == "tool":
                # tool result → user role + tool_result content block
                converted.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": msg["content"],
                        }
                    ],
                })
            elif role == "assistant" and msg.get("tool_calls"):
                # assistant with tool_calls → tool_use content blocks
                content: list[dict[str, Any]] = []
                if msg.get("content"):
                    content.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    func = tc["function"]
                    content.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": func["name"],
                        "input": json.loads(func["arguments"]) if isinstance(func["arguments"], str) else func["arguments"],
                    })
                converted.append({"role": "assistant", "content": content})
            else:
                converted.append({"role": role, "content": msg["content"]})

        # 도구 스키마 변환: OpenAI format → Anthropic format
        anthropic_tools = None
        if tools:
            anthropic_tools = []
            for tool in tools:
                func = tool["function"]
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })

        # Anthropic API는 빈 messages를 허용하지 않음 (greeting 등 system만 있는 경우)
        if not converted:
            converted.append({"role": "user", "content": "[통화 시작] 첫 인사를 해주세요."})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": converted,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if system_text:
            kwargs["system"] = system_text
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        try:
            tool_calls_acc: dict[int, dict[str, Any]] = {}
            tool_index = 0

            async with client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            tool_calls_acc[tool_index] = {
                                "id": block.id,
                                "function": {"name": block.name, "arguments": ""},
                            }
                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            yield delta.text
                        elif delta.type == "input_json_delta":
                            if tool_index in tool_calls_acc:
                                tool_calls_acc[tool_index]["function"]["arguments"] += delta.partial_json
                    elif event.type == "content_block_stop":
                        if tool_index in tool_calls_acc:
                            tool_index += 1

            if tool_calls_acc:
                result = {
                    "type": "tool_calls",
                    "tool_calls": [tool_calls_acc[i] for i in sorted(tool_calls_acc)],
                }
                yield json.dumps(result)

        finally:
            await client.close()
