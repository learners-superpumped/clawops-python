import struct
import tempfile
from pathlib import Path

from clawops.agent._recorder import AudioRecorder, _wav_header, WAV_HEADER_SIZE


def test_wav_header_format():
    header = _wav_header(1000)
    assert len(header) == WAV_HEADER_SIZE
    assert header[:4] == b"RIFF"
    assert header[8:12] == b"WAVE"
    # data size
    data_size = struct.unpack_from("<I", header, 40)[0]
    assert data_size == 1000


def test_recorder_creates_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = AudioRecorder(tmpdir, "CA_test")
        rec.start()

        # 수신 오디오 (발신자, PCM16)
        inbound = struct.pack("<4h", 100, 200, 300, 400)
        rec.write_inbound(inbound)

        # 송신 오디오 (AI, raw ulaw)
        outbound = b"\x80\x90\xa0\xb0"
        rec.write_raw_outbound(outbound)

        rec.stop()

        base = Path(tmpdir)
        assert (base / "CA_test_in.wav").exists()
        assert (base / "CA_test_raw.ulaw").exists()

        # in 파일 크기: header + 1 chunk (8 bytes)
        in_size = (base / "CA_test_in.wav").stat().st_size
        assert in_size == WAV_HEADER_SIZE + 8

        # raw ulaw 파일 크기
        raw_size = (base / "CA_test_raw.ulaw").stat().st_size
        assert raw_size == 4


def test_recorder_multiple_inbound():
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = AudioRecorder(tmpdir, "CA_multi")
        rec.start()

        data = b"\x00" * 160  # 10ms at 8kHz 16-bit
        rec.write_inbound(data)
        rec.write_inbound(data)
        rec.stop()

        with open(Path(tmpdir) / "CA_multi_in.wav", "rb") as f:
            header = f.read(WAV_HEADER_SIZE)
            data_size = struct.unpack_from("<I", header, 40)[0]
            assert data_size == 320


def test_recorder_wav_header_updated():
    """stop() 후 WAV 헤더의 data size가 올바르게 업데이트되는지 확인."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = AudioRecorder(tmpdir, "CA_hdr")
        rec.start()

        data = b"\x00" * 160
        rec.write_inbound(data)
        rec.write_inbound(data)
        rec.stop()

        with open(Path(tmpdir) / "CA_hdr_in.wav", "rb") as f:
            header = f.read(WAV_HEADER_SIZE)
            data_size = struct.unpack_from("<I", header, 40)[0]
            assert data_size == 320


def test_recorder_no_write_before_start():
    """start() 전에 write해도 에러 없이 무시."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = AudioRecorder(tmpdir, "CA_nostart")
        rec.write_inbound(b"\x00" * 160)
        rec.write_raw_outbound(b"\x80" * 80)
        # 파일이 생성되지 않아야 함
        assert not (Path(tmpdir) / "CA_nostart_in.wav").exists()
