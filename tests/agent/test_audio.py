import struct

from clawops.agent._audio import pcm16_to_ulaw, ulaw_to_pcm16


def test_roundtrip_silence():
    """무음(0x00)은 변환 후 근사적으로 유지."""
    silence = b"\x00\x00" * 160  # 160 samples = 20ms at 8kHz
    ulaw = pcm16_to_ulaw(silence)
    assert len(ulaw) == 160
    back = ulaw_to_pcm16(ulaw)
    assert len(back) == 320
    # 무음 근사 확인: 모든 샘플이 -8~8 범위
    samples = struct.unpack(f"<{len(back)//2}h", back)
    assert all(-8 <= s <= 8 for s in samples)


def test_roundtrip_tone():
    """사인파 유사 패턴의 왕복 변환 확인."""
    import math
    samples = [int(16000 * math.sin(2 * math.pi * 440 * i / 8000)) for i in range(160)]
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    ulaw = pcm16_to_ulaw(pcm)
    back = ulaw_to_pcm16(ulaw)
    back_samples = struct.unpack(f"<{len(back)//2}h", back)
    # ulaw 양자화 오차 허용 (원본 대비 5% 이내)
    for orig, decoded in zip(samples, back_samples):
        if abs(orig) > 100:
            assert abs(orig - decoded) / abs(orig) < 0.05


def test_empty_input():
    assert pcm16_to_ulaw(b"") == b""
    assert ulaw_to_pcm16(b"") == b""
