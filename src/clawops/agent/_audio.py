"""오디오 변환 유틸리티.

G.711 mu-law (ulaw) ↔ PCM16 코덱을 제공한다.
녹음 시 ulaw → PCM16 변환에만 사용된다.
"""
from __future__ import annotations

import struct

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


_BIAS = 0x84
_CLIP = 32635


def _encode_ulaw_sample(sample: int) -> int:
    """PCM16 signed sample → mu-law byte."""
    sign = 0
    if sample < 0:
        sign = 0x80
        sample = -sample
    if sample > _CLIP:
        sample = _CLIP
    sample += _BIAS
    exponent = 7
    for exp_val in (0x4000, 0x2000, 0x1000, 0x0800, 0x0400, 0x0200, 0x0100):
        if sample >= exp_val:
            break
        exponent -= 1
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


def pcm16_to_ulaw(pcm: bytes) -> bytes:
    """PCM16 signed 16-bit LE → mu-law 바이트 변환."""
    if not pcm:
        return b""
    n_samples = len(pcm) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm)
    return bytes(_encode_ulaw_sample(s) for s in samples)


def resample_pcm16(pcm: bytes, *, from_rate: int, to_rate: int) -> bytes:
    """PCM16 리샘플링 (선형 보간)."""
    if from_rate == to_rate or not pcm:
        return pcm
    n_samples = len(pcm) // 2
    samples = struct.unpack(f"<{n_samples}h", pcm)
    ratio = from_rate / to_rate
    out_len = int(n_samples / ratio)
    out = []
    for i in range(out_len):
        src_pos = i * ratio
        idx = int(src_pos)
        frac = src_pos - idx
        if idx + 1 < n_samples:
            val = samples[idx] * (1 - frac) + samples[idx + 1] * frac
        else:
            val = samples[idx]
        out.append(int(val))
    return struct.pack(f"<{len(out)}h", *out)


def ulaw_to_pcm16(ulaw: bytes) -> bytes:
    """mu-law 바이트를 PCM16 signed 16-bit little-endian 바이트로 변환."""
    if not ulaw:
        return b""
    samples = [_DECODE_TABLE[b] for b in ulaw]
    return struct.pack(f"<{len(samples)}h", *samples)
