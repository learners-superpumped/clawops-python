import struct

from clawops.agent._audio import ulaw_to_pcm16, pcm16_to_ulaw, resample_pcm16


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


def test_pcm16_to_ulaw_silence():
    """PCM16 무음(0x00)은 ulaw 무음(0xFF)으로 변환."""
    pcm = b'\x00\x00' * 160  # 160 samples
    ulaw = pcm16_to_ulaw(pcm)
    assert len(ulaw) == 160
    assert all(b == 0xFF for b in ulaw)


def test_pcm16_to_ulaw_roundtrip():
    """ulaw → PCM16 → ulaw 왕복 변환이 동일.

    Note: mu-law 0x7F (negative zero) and 0xFF (positive zero) both decode
    to PCM16 0, and encoding 0 always yields 0xFF. We use only the positive
    half (0x80-0xFF) to avoid this ambiguity.
    """
    original = bytes(range(128, 256)) + bytes(range(128, 160))  # 160 bytes, positive half only
    pcm = ulaw_to_pcm16(original)
    back = pcm16_to_ulaw(pcm)
    assert len(back) == 160
    assert back == original


def test_resample_8k_to_16k():
    """8kHz → 16kHz 리샘플링: 길이 2배."""
    pcm_8k = b'\x00\x80' * 80  # 80 samples at 8kHz
    pcm_16k = resample_pcm16(pcm_8k, from_rate=8000, to_rate=16000)
    assert len(pcm_16k) == 320  # 160 samples * 2 bytes


def test_resample_24k_to_8k():
    """24kHz → 8kHz 리샘플링: 길이 1/3."""
    pcm_24k = b'\x00\x80' * 240  # 240 samples
    pcm_8k = resample_pcm16(pcm_24k, from_rate=24000, to_rate=8000)
    assert len(pcm_8k) == 160  # 80 samples * 2 bytes
