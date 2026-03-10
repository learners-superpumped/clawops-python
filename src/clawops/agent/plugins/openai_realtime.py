"""OpenAI Realtime API 플러그인. 하위 호환용 re-export."""
from __future__ import annotations

from ..pipeline._openai_realtime import OpenAIRealtime, OpenAIRealtimeConfig

# 하위 호환: 기존 RealtimeConfig, RealtimeSession 이름 유지
RealtimeConfig = OpenAIRealtimeConfig
RealtimeSession = OpenAIRealtime

__all__ = [
    "OpenAIRealtime",
    "OpenAIRealtimeConfig",
    "RealtimeConfig",
    "RealtimeSession",
]
