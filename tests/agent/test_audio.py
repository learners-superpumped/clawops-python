import struct

from clawops.agent._audio import ulaw_to_pcm16


def test_decode_silence():
    """mu-law 무음(0xFF/0x7F)은 PCM16 근사 0."""
    # mu-law 0xFF = positive zero, 0x7F = negative zero
    ulaw = bytes([0xFF]) * 160
    pcm = ulaw_to_pcm16(ulaw)
    assert len(pcm) == 320
    samples = struct.unpack(f"<{len(pcm)//2}h", pcm)
    assert all(-8 <= s <= 8 for s in samples)


def test_decode_returns_correct_length():
    """ulaw 160 바이트 → PCM16 320 바이트."""
    ulaw = bytes(range(160))
    pcm = ulaw_to_pcm16(ulaw)
    assert len(pcm) == 320


def test_empty_input():
    assert ulaw_to_pcm16(b"") == b""
