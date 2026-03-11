"""3-file call recording: in.wav, out.wav, mix.wav.

Wall-clock 동기화로 실시간 녹음. 세 파일 모두 동일한 길이로 유지된다.
recordings/{call_id}/in.wav   — 상대방 음성 (PCM16 8kHz mono)
recordings/{call_id}/out.wav  — AI 음성 (PCM16 8kHz mono)
recordings/{call_id}/mix.wav  — 양쪽 믹싱 (PCM16 8kHz mono)
"""
from __future__ import annotations

import logging
import os
import struct
import time

log = logging.getLogger(__name__)

SAMPLE_RATE = 8000
CHANNELS = 1
BITS_PER_SAMPLE = 16
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * (BITS_PER_SAMPLE // 8)  # 16000


def _wav_header(data_size: int = 0) -> bytes:
    """44-byte PCM WAV header."""
    byte_rate = SAMPLE_RATE * CHANNELS * (BITS_PER_SAMPLE // 8)
    block_align = CHANNELS * (BITS_PER_SAMPLE // 8)
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        CHANNELS,
        SAMPLE_RATE,
        byte_rate,
        block_align,
        BITS_PER_SAMPLE,
        b"data",
        data_size,
    )


def _mix_samples(a: bytes, b: bytes) -> bytes:
    """두 PCM16 버퍼를 sample-level 합산 (clipping 적용)."""
    n = min(len(a), len(b)) // 2
    samples_a = struct.unpack(f"<{n}h", a[: n * 2])
    samples_b = struct.unpack(f"<{n}h", b[: n * 2])
    mixed = struct.pack(
        f"<{n}h",
        *(max(-32768, min(32767, sa + sb)) for sa, sb in zip(samples_a, samples_b)),
    )
    return mixed


class AudioRecorder:
    """Wall-clock 동기화 3-file WAV recorder."""

    def __init__(self, path: str, call_id: str) -> None:
        self._dir = os.path.join(path, call_id)
        self._f_in = None
        self._f_out = None
        self._f_mix = None
        self._in_written = 0
        self._out_written = 0
        self._mix_written = 0
        self._start_time: float = 0.0
        self._started = False

    def start(self) -> None:
        os.makedirs(self._dir, exist_ok=True)
        header = _wav_header()
        self._f_in = open(os.path.join(self._dir, "in.wav"), "w+b")
        self._f_out = open(os.path.join(self._dir, "out.wav"), "w+b")
        self._f_mix = open(os.path.join(self._dir, "mix.wav"), "w+b")
        self._f_in.write(header)
        self._f_out.write(header)
        self._f_mix.write(header)
        self._f_in.flush()
        self._f_out.flush()
        self._f_mix.flush()
        self._start_time = time.monotonic()
        self._started = True
        log.info("Recording started: %s", self._dir)

    def _expected_bytes(self) -> int:
        elapsed = time.monotonic() - self._start_time
        return int(elapsed * BYTES_PER_SECOND) & ~1  # 2-byte align

    def _pad_silence(self, f, written: int) -> int:
        expected = self._expected_bytes()
        gap = expected - written
        if gap > 0:
            f.write(b"\x00" * gap)
            return written + gap
        return written

    def _write_to_mix(self, data: bytes, track_pos: int) -> None:
        if not self._f_mix:
            return
        mix_data_pos = track_pos
        file_pos = 44 + mix_data_pos

        if mix_data_pos < self._mix_written:
            # Overlap: read existing, mix, write back
            overlap = min(len(data), self._mix_written - mix_data_pos)
            self._f_mix.seek(file_pos)
            existing = self._f_mix.read(overlap)
            mixed = _mix_samples(existing, data[:overlap])
            self._f_mix.seek(file_pos)
            self._f_mix.write(mixed)
            if len(data) > overlap:
                self._f_mix.write(data[overlap:])
                self._mix_written = mix_data_pos + len(data)
        else:
            if mix_data_pos > self._mix_written:
                self._f_mix.seek(44 + self._mix_written)
                self._f_mix.write(b"\x00" * (mix_data_pos - self._mix_written))
            self._f_mix.seek(file_pos)
            self._f_mix.write(data)
            self._mix_written = mix_data_pos + len(data)

    def write_inbound(self, pcm16_8k: bytes) -> None:
        if not self._started or not self._f_in:
            return
        try:
            self._in_written = self._pad_silence(self._f_in, self._in_written)
            pos_before = self._in_written
            self._f_in.write(pcm16_8k)
            self._in_written += len(pcm16_8k)
            self._write_to_mix(pcm16_8k, pos_before)
        except Exception:
            log.exception("Error writing inbound audio")

    def write_outbound(self, pcm16_8k: bytes) -> None:
        if not self._started or not self._f_out:
            return
        try:
            self._out_written = self._pad_silence(self._f_out, self._out_written)
            pos_before = self._out_written
            self._f_out.write(pcm16_8k)
            self._out_written += len(pcm16_8k)
            self._write_to_mix(pcm16_8k, pos_before)
        except Exception:
            log.exception("Error writing outbound audio")

    def stop(self) -> None:
        if not self._started:
            return
        try:
            max_written = max(self._in_written, self._out_written, self._mix_written)
            max_written = max_written & ~1  # 2-byte align (round down)

            for f, written in [
                (self._f_in, self._in_written),
                (self._f_out, self._out_written),
                (self._f_mix, self._mix_written),
            ]:
                if f is None:
                    continue
                pad = max_written - written
                if pad > 0:
                    f.seek(44 + written)
                    f.write(b"\x00" * pad)
                f.seek(0)
                f.write(_wav_header(max_written))
                f.close()

            log.info(
                "Recording stopped: %s (%.1fs)",
                self._dir,
                max_written / BYTES_PER_SECOND if BYTES_PER_SECOND else 0,
            )
        except Exception:
            log.exception("Error stopping recorder")
        finally:
            self._f_in = None
            self._f_out = None
            self._f_mix = None
            self._started = False
