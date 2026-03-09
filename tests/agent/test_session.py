# tests/agent/test_session.py
import pytest
from unittest.mock import AsyncMock
from clawops.agent._session import CallSession


def test_session_creation():
    session = CallSession(
        call_id="CA_test123",
        from_number="01012345678",
        to_number="07012341234",
        account_id="AC_test",
    )
    assert session.call_id == "CA_test123"
    assert session.from_number == "01012345678"
    assert session.to_number == "07012341234"
    assert session.metadata == {}


@pytest.mark.asyncio
async def test_session_send_audio():
    session = CallSession(
        call_id="CA_test",
        from_number="010",
        to_number="070",
        account_id="AC",
    )
    mock_sender = AsyncMock()
    session._send_audio_fn = mock_sender

    await session.send_audio(b"\x00\x00" * 160)
    mock_sender.assert_called_once_with(b"\x00\x00" * 160)



@pytest.mark.asyncio
async def test_session_events():
    session = CallSession(
        call_id="CA_test",
        from_number="010",
        to_number="070",
        account_id="AC",
    )
    received = []

    async def handler(call, role, text):
        received.append((role, text))

    session.on("transcript", handler)
    await session._emit("transcript", "user", "안녕하세요")
    assert received == [("user", "안녕하세요")]
