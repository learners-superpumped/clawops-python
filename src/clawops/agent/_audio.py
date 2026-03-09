"""오디오 변환 유틸리티.

ClawOps Stream 프로토콜은 PCM16 8kHz를 사용하고,
OpenAI Realtime API는 pcm16 24kHz 포맷을 사용한다.
리샘플링(8kHz↔24kHz)과 G.711 mu-law 코덱을 제공한다.
"""
from __future__ import annotations

import struct

# ─── Encode: PCM16 -> ulaw (ITU-T G.711) ──────────────────────────────

_BIAS = 0x84
_CLIP = 32635
_EXP_TABLE = [
    0, 0, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3,
    4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
]


def _encode_sample(sample: int) -> int:
    sign = (sample >> 8) & 0x80
    if sign:
        sample = -sample
    if sample > _CLIP:
        sample = _CLIP
    sample += _BIAS
    exp = _EXP_TABLE[(sample >> 7) & 0xFF]
    mantissa = (sample >> (exp + 3)) & 0x0F
    return ~(sign | (exp << 4) | mantissa) & 0xFF


_ENCODE_TABLE = bytes(
    _encode_sample(i if i < 32768 else i - 65536) for i in range(65536)
)

_DECODE_TABLE = (
    -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
    -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
    -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
    -11900, -11388, -10876, -10364,  -9852,  -9340,  -8828,  -8316,
     -7932,  -7676,  -7420,  -7164,  -6908,  -6652,  -6396,  -6140,
     -5884,  -5628,  -5372,  -5116,  -4860,  -4604,  -4348,  -4092,
     -3900,  -3772,  -3644,  -3516,  -3388,  -3260,  -3132,  -3004,
     -2876,  -2748,  -2620,  -2492,  -2364,  -2236,  -2108,  -1980,
     -1884,  -1820,  -1756,  -1692,  -1628,  -1564,  -1500,  -1436,
     -1372,  -1308,  -1244,  -1180,  -1116,  -1052,   -988,   -924,
      -876,   -844,   -812,   -780,   -748,   -716,   -684,   -652,
      -620,   -588,   -556,   -524,   -492,   -460,   -428,   -396,
      -372,   -356,   -340,   -324,   -308,   -292,   -276,   -260,
      -244,   -228,   -212,   -196,   -180,   -164,   -148,   -132,
      -120,   -112,   -104,    -96,    -88,    -80,    -72,    -64,
       -56,    -48,    -40,    -32,    -24,    -16,     -8,      0,
     32124,  31100,  30076,  29052,  28028,  27004,  25980,  24956,
     23932,  22908,  21884,  20860,  19836,  18812,  17788,  16764,
     15996,  15484,  14972,  14460,  13948,  13436,  12924,  12412,
     11900,  11388,  10876,  10364,   9852,   9340,   8828,   8316,
      7932,   7676,   7420,   7164,   6908,   6652,   6396,   6140,
      5884,   5628,   5372,   5116,   4860,   4604,   4348,   4092,
      3900,   3772,   3644,   3516,   3388,   3260,   3132,   3004,
      2876,   2748,   2620,   2492,   2364,   2236,   2108,   1980,
      1884,   1820,   1756,   1692,   1628,   1564,   1500,   1436,
      1372,   1308,   1244,   1180,   1116,   1052,    988,    924,
       876,    844,    812,    780,    748,    716,    684,    652,
       620,    588,    556,    524,    492,    460,    428,    396,
       372,    356,    340,    324,    308,    292,    276,    260,
       244,    228,    212,    196,    180,    164,    148,    132,
       120,    112,    104,     96,     88,     80,     72,     64,
        56,     48,     40,     32,     24,     16,      8,      0,
)


def pcm16_to_ulaw(pcm16: bytes) -> bytes:
    """PCM16 signed 16-bit little-endian 바이트를 mu-law 바이트로 변환."""
    if not pcm16:
        return b""
    n = len(pcm16) // 2
    samples = struct.unpack(f"<{n}h", pcm16)
    return bytes(_ENCODE_TABLE[s & 0xFFFF] for s in samples)


def ulaw_to_pcm16(ulaw: bytes) -> bytes:
    """mu-law 바이트를 PCM16 signed 16-bit little-endian 바이트로 변환."""
    if not ulaw:
        return b""
    samples = [_DECODE_TABLE[b] for b in ulaw]
    return struct.pack(f"<{len(samples)}h", *samples)


# ─── Resample: 8kHz <-> 24kHz ──────────────────────────────────────────

def resample_8k_to_24k(pcm16_8k: bytes) -> bytes:
    """8kHz PCM16를 24kHz PCM16로 업샘플링 (선형 보간)."""
    if not pcm16_8k:
        return b""
    n = len(pcm16_8k) // 2
    samples = struct.unpack(f"<{n}h", pcm16_8k)
    out = []
    for i in range(n - 1):
        s0, s1 = samples[i], samples[i + 1]
        out.append(s0)
        out.append((s0 * 2 + s1) // 3)
        out.append((s0 + s1 * 2) // 3)
    out.append(samples[-1])
    out.append(samples[-1])
    out.append(samples[-1])
    return struct.pack(f"<{len(out)}h", *out)


# 24kHz→8kHz 안티앨리어싱 FIR 로우패스 필터 (cutoff ≈ 3.5kHz)
# 15-tap windowed sinc (Hamming), 정수 계수 (합=256, 8-bit 정밀도)
_LP_KERNEL = (1, 2, 5, 12, 23, 36, 44, 50, 44, 36, 23, 12, 5, 2, 1)
_LP_KERNEL_SUM = sum(_LP_KERNEL)  # 296
_LP_HALF = len(_LP_KERNEL) // 2   # 7


def resample_24k_to_8k(pcm16_24k: bytes) -> bytes:
    """24kHz PCM16를 8kHz PCM16로 다운샘플링 (FIR 안티앨리어싱 + 3:1 데시메이션)."""
    if not pcm16_24k:
        return b""
    n = len(pcm16_24k) // 2
    samples = struct.unpack(f"<{n}h", pcm16_24k)
    out = []
    for i in range(0, n, 3):
        acc = 0
        for k, c in enumerate(_LP_KERNEL):
            j = i + k - _LP_HALF
            if 0 <= j < n:
                acc += samples[j] * c
            # 경계 밖은 0으로 처리 (자연 감쇠)
        s = acc // _LP_KERNEL_SUM
        out.append(max(-32768, min(32767, s)))
    return struct.pack(f"<{len(out)}h", *out)
