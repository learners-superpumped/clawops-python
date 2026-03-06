"""Provider Protocol 정의. 유저가 이 Protocol에 맞추면 아무 프로바이더나 사용 가능."""
from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class STT(Protocol):
    async def transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """오디오 스트림(PCM16 8kHz) -> 텍스트 스트림."""
        ...

@runtime_checkable
class LLM(Protocol):
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """메시지 -> 텍스트 응답 스트림."""
        ...

@runtime_checkable
class TTS(Protocol):
    async def synthesize(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """텍스트 스트림 -> 오디오(PCM16 8kHz) 스트림."""
        ...
