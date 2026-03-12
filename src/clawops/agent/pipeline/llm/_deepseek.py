"""DeepSeek LLM (OpenAI 호환 API)."""
from __future__ import annotations

import os

from ._openai_compat import OpenAICompatibleLLM


class DeepSeekLLM(OpenAICompatibleLLM):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "deepseek-chat",
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        super().__init__(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
