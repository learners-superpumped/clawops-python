# tests/agent/test_media_ws.py
import base64
from clawops.agent._media_ws import parse_media_event, build_media_response, parse_start_event


def test_parse_media_event():
    pcm = b"\x00\x01" * 80
    event = {
        "event": "media",
        "media": {
            "track": "inbound",
            "chunk": "1",
            "timestamp": "100",
            "payload": base64.b64encode(pcm).decode(),
        },
    }
    result = parse_media_event(event)
    assert result["pcm16"] == pcm
    assert result["timestamp"] == 100


def test_build_media_response():
    pcm = b"\x00\x01" * 80
    msg = build_media_response(pcm)
    assert msg["event"] == "media"
    decoded = base64.b64decode(msg["media"]["payload"])
    assert decoded == pcm


def test_parse_start_event():
    event = {
        "event": "start",
        "start": {
            "streamId": "MZ_abc",
            "callId": "CA_123",
            "accountId": "AC_test",
            "tracks": ["inbound"],
            "mediaFormat": {"encoding": "audio/x-l16", "sampleRate": 8000, "channels": 1},
        },
    }
    result = parse_start_event(event)
    assert result["stream_id"] == "MZ_abc"
    assert result["call_id"] == "CA_123"
    assert result["sample_rate"] == 8000
