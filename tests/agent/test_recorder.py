"""AudioRecorder 3-file recording tests."""
from __future__ import annotations

import struct
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from clawops.agent._recorder import AudioRecorder, _mix_samples, _wav_header


def test_wav_header_format():
    header = _wav_header(1000)
    assert len(header) == 44
    assert header[:4] == b"RIFF"
    assert header[8:12] == b"WAVE"
    assert header[12:16] == b"fmt "
    assert struct.unpack_from("<I", header, 16)[0] == 16
    assert struct.unpack_from("<H", header, 20)[0] == 1
    assert struct.unpack_from("<H", header, 22)[0] == 1
    assert struct.unpack_from("<I", header, 24)[0] == 8000
    assert struct.unpack_from("<H", header, 34)[0] == 16
    assert header[36:40] == b"data"
    assert struct.unpack_from("<I", header, 40)[0] == 1000


def test_start_creates_three_wav_files(tmp_path: Path):
    rec = AudioRecorder(str(tmp_path), "call-123")
    rec.start()
    call_dir = tmp_path / "call-123"
    assert (call_dir / "in.wav").exists()
    assert (call_dir / "out.wav").exists()
    assert (call_dir / "mix.wav").exists()
    for name in ("in.wav", "out.wav", "mix.wav"):
        with wave.open(str(call_dir / name), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 8000
    rec.stop()


def test_write_inbound_only(tmp_path: Path):
    rec = AudioRecorder(str(tmp_path), "call-in")
    rec.start()
    pcm = b"\x01\x00" * 80
    rec.write_inbound(pcm)
    rec.stop()
    call_dir = tmp_path / "call-in"
    with wave.open(str(call_dir / "in.wav"), "rb") as wf:
        assert wf.getnframes() >= 80


def test_write_outbound_only(tmp_path: Path):
    rec = AudioRecorder(str(tmp_path), "call-out")
    rec.start()
    pcm = b"\x02\x00" * 80
    rec.write_outbound(pcm)
    rec.stop()
    call_dir = tmp_path / "call-out"
    with wave.open(str(call_dir / "out.wav"), "rb") as wf:
        assert wf.getnframes() >= 80


def test_stop_equalizes_track_lengths(tmp_path: Path):
    rec = AudioRecorder(str(tmp_path), "call-eq")
    rec.start()
    rec.write_inbound(b"\x01\x00" * 160)
    rec.write_outbound(b"\x02\x00" * 80)
    rec.stop()
    call_dir = tmp_path / "call-eq"
    sizes = []
    for name in ("in.wav", "out.wav", "mix.wav"):
        sizes.append((call_dir / name).stat().st_size)
    assert sizes[0] == sizes[1] == sizes[2]


def test_write_before_start_is_noop(tmp_path: Path):
    rec = AudioRecorder(str(tmp_path), "call-noop")
    rec.write_inbound(b"\x01\x00" * 80)
    rec.write_outbound(b"\x02\x00" * 80)
    assert not (tmp_path / "call-noop").exists()


def test_mix_samples_basic():
    a = b"\x10\x00\x20\x00"
    b_buf = b"\x01\x00\x02\x00"
    result = _mix_samples(a, b_buf)
    vals = struct.unpack(f"<{len(result)//2}h", result)
    assert vals == (17, 34)


def test_mix_samples_clipping():
    a = struct.pack("<h", 32000)
    b_buf = struct.pack("<h", 32000)
    result = _mix_samples(a, b_buf)
    val = struct.unpack("<h", result)[0]
    assert val == 32767


def test_mix_file_contains_both_tracks(tmp_path: Path):
    rec = AudioRecorder(str(tmp_path), "call-mix")
    rec.start()
    in_pcm = struct.pack("<4h", 100, 200, 300, 400)
    out_pcm = struct.pack("<4h", 10, 20, 30, 40)
    rec.write_inbound(in_pcm)
    rec.write_outbound(out_pcm)
    rec.stop()
    call_dir = tmp_path / "call-mix"
    with wave.open(str(call_dir / "mix.wav"), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    samples = struct.unpack(f"<{len(frames)//2}h", frames)
    assert samples[0] == 110
    assert samples[1] == 220
    assert samples[2] == 330
    assert samples[3] == 440


def test_zero_length_call(tmp_path: Path):
    rec = AudioRecorder(str(tmp_path), "call-zero")
    rec.start()
    rec.stop()
    call_dir = tmp_path / "call-zero"
    for name in ("in.wav", "out.wav", "mix.wav"):
        with wave.open(str(call_dir / name), "rb") as wf:
            assert wf.getnframes() == 0


@patch("time.monotonic")
def test_wall_clock_gap_inserts_silence(mock_mono, tmp_path: Path):
    times = iter([0.0, 0.0, 1.0])
    mock_mono.side_effect = lambda: next(times)

    rec = AudioRecorder(str(tmp_path), "call-gap")
    rec.start()
    rec.write_inbound(b"\x01\x00" * 80)
    rec.write_inbound(b"\x02\x00" * 80)
    rec.stop()

    call_dir = tmp_path / "call-gap"
    in_size = (call_dir / "in.wav").stat().st_size - 44
    assert in_size >= 16000
