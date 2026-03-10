"""xAI Grok LLM (OpenAI 호환 API)."""
from __future__ import annotations

import os

from ._openai_compat_llm import OpenAICompatibleLLM


class XaiLLM(OpenAICompatibleLLM):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "grok-4-1-fast",
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("XAI_API_KEY", "")
        super().__init__(
            api_key=api_key,
            base_url="https://api.x.ai/v1",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
