"""Google Gemini 스트리밍 LLM."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator

log = logging.getLogger("clawops.agent.pipeline")


class GeminiLLM:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("GOOGLE_API_KEY", "")
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
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key)

        # tool_call_id → function name 매핑 (tool result 변환용)
        tc_id_to_name: dict[str, str] = {}
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tc_id_to_name[tc["id"]] = tc["function"]["name"]

        # OpenAI format → Gemini Content format 변환
        system_instruction = None
        contents: list[types.Content] = []
        for msg in messages:
            role = msg["role"]
            if role == "system":
                system_instruction = msg["content"]
            elif role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=msg["content"])],
                ))
            elif role == "assistant":
                parts: list[types.Part] = []
                if msg.get("content"):
                    parts.append(types.Part.from_text(text=msg["content"]))
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        func = tc["function"]
                        args = json.loads(func["arguments"]) if isinstance(func["arguments"], str) else func["arguments"]
                        parts.append(types.Part.from_function_call(
                            name=func["name"],
                            args=args,
                        ))
                contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                # tool result → function response
                func_name = tc_id_to_name.get(msg.get("tool_call_id", ""), "unknown")
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=func_name,
                        response={"result": msg["content"]},
                    )],
                ))

        # 도구 스키마 변환
        gemini_tools = None
        if tools:
            declarations = []
            for tool in tools:
                func = tool["function"]
                declarations.append(types.FunctionDeclaration(
                    name=func["name"],
                    description=func.get("description", ""),
                    parameters=func.get("parameters"),
                ))
            gemini_tools = [types.Tool(function_declarations=declarations)]

        config_kwargs: dict[str, Any] = {
            "temperature": self._temperature,
            "max_output_tokens": self._max_tokens,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if gemini_tools:
            config_kwargs["tools"] = gemini_tools
        config = types.GenerateContentConfig(**config_kwargs)

        # Gemini API는 빈 contents를 허용하지 않음 (greeting 등 system만 있는 경우)
        if not contents:
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text="[통화 시작] 첫 인사를 해주세요.")],
            ))

        tool_calls: list[dict[str, Any]] = []

        stream = await client.aio.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=config,
        )
        async for chunk in stream:
            if not chunk.candidates:
                continue
            for part in chunk.candidates[0].content.parts:
                if part.text:
                    yield part.text
                elif part.function_call:
                    fc = part.function_call
                    idx = len(tool_calls)
                    tool_calls.append({
                        "id": f"call_{fc.name}_{idx}",
                        "function": {
                            "name": fc.name,
                            "arguments": json.dumps(dict(fc.args) if fc.args else {}),
                        },
                    })

        if tool_calls:
            result = {
                "type": "tool_calls",
                "tool_calls": tool_calls,
            }
            yield json.dumps(result)
