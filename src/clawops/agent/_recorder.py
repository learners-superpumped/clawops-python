"""AudioRecorder: per-call 실시간 녹음.

2개 파일을 동시에 실시간 기록:
- {call_id}_in.wav  — 발신자 음성 (수신, PCM16 8kHz mono)
- {call_id}_raw.ulaw — AI 음성 (송신, OpenAI 원본 G.711 ulaw)

수신 오디오가 타임라인 역할을 하므로 별도 시간 관리 불필요.
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


class AudioRecorder:
    """실시간 양방향 녹음기.

    사용법:
        recorder = AudioRecorder("./recordings", "CA_abc123")
        recorder.start()
        recorder.write_inbound(pcm16)        # 수신 오디오마다 호출
        recorder.write_raw_outbound(ulaw)     # 송신 오디오마다 호출
        recorder.stop()                       # 통화 종료 시 WAV 헤더 업데이트
    """

    def __init__(self, path: str | Path, call_id: str) -> None:
        self._dir = Path(path)
        self._call_id = call_id
        self._in_file = None
        self._raw_file = None
        self._in_size = 0
        self._started = False

    def start(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        base = self._dir / self._call_id

        self._in_file = open(f"{base}_in.wav", "wb")
        self._raw_file = open(f"{base}_raw.ulaw", "wb")

        self._in_file.write(_wav_header(0))

        self._started = True
        log.info(f"Recording started: {base}_in.wav, {base}_raw.ulaw")

    def write_inbound(self, pcm16: bytes) -> None:
        """수신 오디오 기록 (PCM16)."""
        if not self._started:
            return
        self._in_file.write(pcm16)
        self._in_size += len(pcm16)

    def write_raw_outbound(self, data: bytes) -> None:
        """OpenAI 원본 ulaw 바이트를 그대로 기록."""
        if not self._started or not self._raw_file:
            return
        self._raw_file.write(data)

    def stop(self) -> None:
        """녹음 종료. WAV 헤더를 최종 크기로 업데이트."""
        if not self._started:
            return
        self._started = False

        if self._raw_file and not self._raw_file.closed:
            self._raw_file.close()

        if self._in_file and not self._in_file.closed:
            self._in_file.seek(0)
            self._in_file.write(_wav_header(self._in_size))
            self._in_file.close()

        log.info(f"Recording stopped: {self._call_id} (in={self._in_size}B)")
