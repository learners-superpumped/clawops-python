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
async def test_metrics_stub():
    """metrics 속성도 record_* 호출을 받을 수 있어야 한다 (no-op)."""
    stub = _BufferingCall()
    stub.metrics.record_tool_call()  # 예외 없어야 함
