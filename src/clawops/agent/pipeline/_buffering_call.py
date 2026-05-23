"""prewarm 단계에서 사용되는 CallSession stub.

실제 통화가 아직 attach 되지 않은 상태에서 Session 구현체가 호출하는
send_audio / _emit / metrics 를 흡수한다. attach() 시점에 drain_buffer() 로
누적된 audio chunk 들을 실제 CallSession 에 flush 한다.
"""
from __future__ import annotations

from typing import Any


class _MetricsStub:
    def record_tool_call(self) -> None:
        pass

    def record_interrupt(self) -> None:
        pass


class _BufferingCall:
    """prewarm 단계의 CallSession 역할.

    Session 구현체가 `self._call.send_audio(...)` 를 호출하면 메모리 버퍼에 쌓는다.
    attach() 시 drain_buffer() 로 꺼내 실제 CallSession 으로 flush.
    """

    def __init__(self) -> None:
        self._buffer: list[bytes] = []
        self.metrics = _MetricsStub()

    async def send_audio(self, chunk: bytes) -> None:
        self._buffer.append(chunk)

    async def _emit(self, *args: Any, **kwargs: Any) -> None:
        # transcript 등 이벤트는 prewarm 동안 흘려보낸다 (no-op).
        pass

    def drain_buffer(self) -> list[bytes]:
        out = self._buffer
        self._buffer = []
        return out
