"""AudioRecorder: per-call 실시간 녹음.

3개 파일을 동시에 실시간 기록:
- {call_id}_in.wav  — 발신자 음성 (수신)
- {call_id}_out.wav — AI 음성 (송신)
- {call_id}_mix.wav — 양방향 믹스

수신 오디오가 타임라인 역할을 하므로 별도 시간 관리 불필요.
PCM16 8kHz mono.
"""
from __future__ import annotations

import os
import struct
import logging
from pathlib import Path

log = logging.getLogger("clawops.agent")

WAV_SAMPLE_RATE = 8000
WAV_CHANNELS = 1
WAV_BITS_PER_SAMPLE = 16
WAV_HEADER_SIZE = 44


def _wav_header(data_size: int = 0) -> bytes:
    """PCM16 8kHz mono WAV 헤더 생성."""
    byte_rate = WAV_SAMPLE_RATE * WAV_CHANNELS * WAV_BITS_PER_SAMPLE // 8
    block_align = WAV_CHANNELS * WAV_BITS_PER_SAMPLE // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,         # file size - 8
        b"WAVE",
        b"fmt ",
        16,                     # fmt chunk size
        1,                      # PCM
        WAV_CHANNELS,
        WAV_SAMPLE_RATE,
        byte_rate,
        block_align,
        WAV_BITS_PER_SAMPLE,
        b"data",
        data_size,
    )


def _mix_samples(a: bytes, b: bytes) -> bytes:
    """두 PCM16 버퍼를 샘플 단위로 더해 클리핑."""
    n = min(len(a), len(b))
    # 2바이트 단위
    samples = n // 2
    out = bytearray(samples * 2)
    for i in range(samples):
        sa = struct.unpack_from("<h", a, i * 2)[0]
        sb = struct.unpack_from("<h", b, i * 2)[0]
        mixed = max(-32768, min(32767, sa + sb))
        struct.pack_into("<h", out, i * 2, mixed)
    return bytes(out)


class AudioRecorder:
    """실시간 양방향 녹음기.

    사용법:
        recorder = AudioRecorder("./recordings", "CA_abc123")
        recorder.start()
        recorder.write_inbound(pcm16)   # 수신 오디오마다 호출
        recorder.write_outbound(pcm16)  # 송신 오디오마다 호출
        recorder.stop()                 # 통화 종료 시 WAV 헤더 업데이트
    """

    def __init__(self, path: str | Path, call_id: str) -> None:
        self._dir = Path(path)
        self._call_id = call_id
        self._in_file = None
        self._out_file = None
        self._mix_file = None
        self._in_size = 0
        self._out_size = 0
        self._mix_size = 0
        self._out_buffer = bytearray()
        self._started = False

    def start(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        base = self._dir / self._call_id

        self._in_file = open(f"{base}_in.wav", "wb")
        self._out_file = open(f"{base}_out.wav", "wb")
        self._mix_file = open(f"{base}_mix.wav", "wb")

        # placeholder 헤더 (나중에 업데이트)
        for f in (self._in_file, self._out_file, self._mix_file):
            f.write(_wav_header(0))

        self._started = True
        log.info(f"Recording started: {base}_*.wav")

    def write_inbound(self, pcm16: bytes) -> None:
        """수신 오디오 기록. 이 호출이 믹스 타임라인을 구동한다."""
        if not self._started:
            return

        # in 트랙
        self._in_file.write(pcm16)
        self._in_size += len(pcm16)

        # mix: inbound + outbound 버퍼에서 같은 길이만큼 꺼내서 믹스
        out_chunk = self._drain_outbound(len(pcm16))
        mixed = _mix_samples(pcm16, out_chunk)
        self._mix_file.write(mixed)
        self._mix_size += len(mixed)

    def write_outbound(self, pcm16: bytes) -> None:
        """송신 오디오 기록. 버퍼에 넣고 다음 inbound에서 믹스된다."""
        if not self._started:
            return

        # out 트랙
        self._out_file.write(pcm16)
        self._out_size += len(pcm16)

        # 믹스용 버퍼에 추가
        self._out_buffer.extend(pcm16)

    def stop(self) -> None:
        """녹음 종료. WAV 헤더를 최종 크기로 업데이트."""
        if not self._started:
            return
        self._started = False

        # 남은 outbound 버퍼를 믹스에 flush (silence inbound)
        if self._out_buffer:
            remaining = bytes(self._out_buffer)
            self._mix_file.write(remaining)
            self._mix_size += len(remaining)
            self._out_buffer.clear()

        # WAV 헤더 업데이트
        for f, size in [
            (self._in_file, self._in_size),
            (self._out_file, self._out_size),
            (self._mix_file, self._mix_size),
        ]:
            if f and not f.closed:
                f.seek(0)
                f.write(_wav_header(size))
                f.close()

        log.info(f"Recording stopped: {self._call_id} "
                 f"(in={self._in_size}B, out={self._out_size}B, mix={self._mix_size}B)")

    def _drain_outbound(self, length: int) -> bytes:
        """outbound 버퍼에서 length만큼 꺼냄. 부족하면 silence로 채움."""
        if len(self._out_buffer) >= length:
            chunk = bytes(self._out_buffer[:length])
            del self._out_buffer[:length]
            return chunk
        chunk = bytes(self._out_buffer) + b"\x00" * (length - len(self._out_buffer))
        self._out_buffer.clear()
        return chunk
