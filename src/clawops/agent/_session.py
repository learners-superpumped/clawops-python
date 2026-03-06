"""CallSession: per-call 상태 관리 및 오디오 스트림."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Awaitable


class CallSession:
    def __init__(
        self,
        *,
        call_id: str,
        from_number: str,
        to_number: str,
        account_id: str,
    ) -> None:
        self.call_id = call_id
        self.from_number = from_number
        self.to_number = to_number
        self.account_id = account_id
        self.start_time = datetime.now()
        self.metadata: dict[str, Any] = {}

        self._send_audio_fn: Callable[[bytes], Awaitable[None]] | None = None
        self._send_clear_fn: Callable[[], Awaitable[None]] | None = None
        self._hangup_fn: Callable[[], Awaitable[None]] | None = None

        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._event_handlers: dict[str, list[Callable[..., Awaitable[None]]]] = {}

    @property
    def duration(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()

    async def send_audio(self, pcm16: bytes) -> None:
        if self._send_audio_fn:
            await self._send_audio_fn(pcm16)

    async def clear_audio(self) -> None:
        if self._send_clear_fn:
            await self._send_clear_fn()

    async def hangup(self) -> None:
        if self._hangup_fn:
            await self._hangup_fn()

    async def audio_stream(self) -> AsyncIterator[bytes]:
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                break
            yield chunk

    async def _push_audio(self, data: bytes) -> None:
        await self._audio_queue.put(data)

    def _audio_done(self) -> None:
        self._audio_queue.put_nowait(None)

    def on(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        self._event_handlers.setdefault(event, []).append(handler)

    async def _emit(self, event: str, *args: Any) -> None:
        for handler in self._event_handlers.get(event, []):
            await handler(self, *args)
