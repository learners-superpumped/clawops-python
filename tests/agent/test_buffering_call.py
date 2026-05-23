import pytest
from clawops.agent.pipeline._buffering_call import _BufferingCall


@pytest.mark.asyncio
async def test_buffers_audio_chunks():
    """send_audio 호출이 순서대로 버퍼에 누적된다."""
    stub = _BufferingCall()
    await stub.send_audio(b"chunk1")
    await stub.send_audio(b"chunk2")
    assert stub.drain_buffer() == [b"chunk1", b"chunk2"]


@pytest.mark.asyncio
async def test_drain_empties_buffer():
    """drain 후 버퍼는 비워진다."""
    stub = _BufferingCall()
    await stub.send_audio(b"x")
    stub.drain_buffer()
    assert stub.drain_buffer() == []


@pytest.mark.asyncio
async def test_emit_noop():
    """_emit (transcript 등) 은 silent no-op."""
    stub = _BufferingCall()
    await stub._emit("transcript", "user", "hello")  # 예외 없어야 함


@pytest.mark.asyncio
async def test_emit_counts_dropped_events():
    """prewarm 단계에서 _emit 으로 들어온 이벤트는 event name 별로 카운트된다."""
    stub = _BufferingCall()
    await stub._emit("transcript", "user", "hello")
    await stub._emit("transcript", "assistant", "hi")
    await stub._emit("dtmf", "1")
    dropped = stub.drain_dropped_events()
    assert dropped == {"transcript": 2, "dtmf": 1}
    # drain 후 비워진다
    assert stub.drain_dropped_events() == {}


@pytest.mark.asyncio
async def test_drain_into_helper_flushes_and_logs(caplog):
    """drain_into 헬퍼는 buffer + dropped events 를 모두 처리한다."""
    import logging
    from clawops.agent.pipeline._buffering_call import drain_into

    stub = _BufferingCall()
    await stub.send_audio(b"a")
    await stub.send_audio(b"b")
    await stub._emit("transcript", "user", "x")

    class _FakeCall:
        call_id = "call-xyz"

        def __init__(self) -> None:
            self.received: list[bytes] = []

        async def send_audio(self, chunk: bytes) -> None:
            self.received.append(chunk)

    target = _FakeCall()
    with caplog.at_level(logging.INFO, logger="clawops.agent.prewarm"):
        await drain_into(stub, target)
    assert target.received == [b"a", b"b"]
    msgs = " ".join(r.message for r in caplog.records)
    assert "first-audio" in msgs
    assert "dropped events" in msgs


@pytest.mark.asyncio
async def test_drain_into_noop_for_real_call():
    """drain_into 의 첫 인자가 _BufferingCall 이 아니면 아무것도 안 한다."""
    from clawops.agent.pipeline._buffering_call import drain_into

    class _FakeCall:
        call_id = "x"

        def __init__(self) -> None:
            self.received: list[bytes] = []

        async def send_audio(self, chunk: bytes) -> None:
            self.received.append(chunk)

    real_prev = _FakeCall()
    real_prev.received.append(b"already")  # 이 chunk 가 leak 되어선 안 됨
    target = _FakeCall()
    await drain_into(real_prev, target)
    assert target.received == []


@pytest.mark.asyncio
async def test_metrics_stub():
    """metrics 속성도 record_* 호출을 받을 수 있어야 한다 (no-op)."""
    stub = _BufferingCall()
    stub.metrics.record_tool_call()  # 예외 없어야 함
