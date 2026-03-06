import struct
import tempfile
from pathlib import Path

from clawops.agent._recorder import AudioRecorder, _mix_samples, _wav_header, WAV_HEADER_SIZE


def test_wav_header_format():
    header = _wav_header(1000)
    assert len(header) == WAV_HEADER_SIZE
    assert header[:4] == b"RIFF"
    assert header[8:12] == b"WAVE"
    # data size
    data_size = struct.unpack_from("<I", header, 40)[0]
    assert data_size == 1000


def test_mix_samples_silence():
    a = struct.pack("<4h", 100, 200, -100, 0)
    b = b"\x00" * 8  # silence
    mixed = _mix_samples(a, b)
    assert mixed == a


def test_mix_samples_additive():
    a = struct.pack("<2h", 1000, -1000)
    b = struct.pack("<2h", 500, -500)
    mixed = _mix_samples(a, b)
    s1, s2 = struct.unpack("<2h", mixed)
    assert s1 == 1500
    assert s2 == -1500


def test_mix_samples_clipping():
    a = struct.pack("<h", 30000)
    b = struct.pack("<h", 30000)
    mixed = _mix_samples(a, b)
    s = struct.unpack("<h", mixed)[0]
    assert s == 32767  # clipped


def test_recorder_creates_three_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = AudioRecorder(tmpdir, "CA_test")
        rec.start()

        # 수신 오디오 (발신자)
        inbound = struct.pack("<4h", 100, 200, 300, 400)
        rec.write_inbound(inbound)

        # 송신 오디오 (AI)
        outbound = struct.pack("<4h", 50, 60, 70, 80)
        rec.write_outbound(outbound)

        # 두번째 수신 — 이 때 outbound가 믹스됨
        inbound2 = struct.pack("<4h", 10, 20, 30, 40)
        rec.write_inbound(inbound2)

        rec.stop()

        base = Path(tmpdir)
        assert (base / "CA_test_in.wav").exists()
        assert (base / "CA_test_out.wav").exists()
        assert (base / "CA_test_mix.wav").exists()

        # in 파일 크기: header + 2 chunks (8 bytes each)
        in_size = (base / "CA_test_in.wav").stat().st_size
        assert in_size == WAV_HEADER_SIZE + 16

        # out 파일 크기: header + 1 chunk
        out_size = (base / "CA_test_out.wav").stat().st_size
        assert out_size == WAV_HEADER_SIZE + 8


def test_recorder_mix_content():
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = AudioRecorder(tmpdir, "CA_mix")
        rec.start()

        # outbound 먼저 넣기 (버퍼에 대기)
        outbound = struct.pack("<2h", 500, 500)
        rec.write_outbound(outbound)

        # inbound 오면 믹스됨
        inbound = struct.pack("<2h", 100, 100)
        rec.write_inbound(inbound)

        rec.stop()

        mix_data = (Path(tmpdir) / "CA_mix_mix.wav").read_bytes()
        pcm = mix_data[WAV_HEADER_SIZE:]
        s1, s2 = struct.unpack("<2h", pcm)
        assert s1 == 600  # 100 + 500
        assert s2 == 600


def test_recorder_inbound_only_mix_is_silence_padded():
    """outbound 없이 inbound만 오면 mix = inbound (silence 패딩)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = AudioRecorder(tmpdir, "CA_inonly")
        rec.start()

        inbound = struct.pack("<2h", 300, -300)
        rec.write_inbound(inbound)
        rec.stop()

        mix_data = (Path(tmpdir) / "CA_inonly_mix.wav").read_bytes()
        pcm = mix_data[WAV_HEADER_SIZE:]
        s1, s2 = struct.unpack("<2h", pcm)
        assert s1 == 300
        assert s2 == -300


def test_recorder_wav_header_updated():
    """stop() 후 WAV 헤더의 data size가 올바르게 업데이트되는지 확인."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = AudioRecorder(tmpdir, "CA_hdr")
        rec.start()

        data = b"\x00" * 160  # 10ms at 8kHz 16-bit
        rec.write_inbound(data)
        rec.write_inbound(data)
        rec.stop()

        with open(Path(tmpdir) / "CA_hdr_in.wav", "rb") as f:
            header = f.read(WAV_HEADER_SIZE)
            data_size = struct.unpack_from("<I", header, 40)[0]
            assert data_size == 320
