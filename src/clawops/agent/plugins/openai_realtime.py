"""OpenAI Realtime API 플러그인. ClawOpsAgent에 내장, system_prompt 설정 시 자동 활성화."""
from __future__ import annotations

from ..pipeline._realtime_session import RealtimeConfig, RealtimeSession


class OpenAIRealtimePlugin:
    def __init__(self, config: RealtimeConfig) -> None:
        self.config = config
