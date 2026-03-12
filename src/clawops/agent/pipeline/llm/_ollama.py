"""Ollama 로컬 LLM (OpenAI 호환 API)."""
from __future__ import annotations

import os

from ._openai_compat import OpenAICompatibleLLM


class OllamaLLM(OpenAICompatibleLLM):
    def __init__(
        self,
        *,
        model: str = "llama3.2",
        base_url: str | None = None,
        temperature: float = 0.8,
        max_tokens: int = 4096,
    ) -> None:
        if base_url is None:
            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        super().__init__(
            api_key="ollama",
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
