from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._openai import OpenAIRealtime
    from ._gemini import GeminiRealtime

__all__ = ["OpenAIRealtime", "GeminiRealtime"]

_LAZY = {
    "OpenAIRealtime": "._openai",
    "GeminiRealtime": "._gemini",
}


def __getattr__(name: str):
    if name in _LAZY:
        mod = importlib.import_module(_LAZY[name], __name__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
