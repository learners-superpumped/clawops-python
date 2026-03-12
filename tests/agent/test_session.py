# tests/agent/test_session.py
import asyncio
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


@pytest.mark.asyncio
async def test_send_dtmf_sequence_single():
    """단일 digit 전송."""
    session = CallSession(
        call_id="CA_test", from_number="010", to_number="070", account_id="AC",
    )
    sent = []
    mock_send = AsyncMock(side_effect=lambda d: sent.append(d))
    session._send_dtmf_fn = mock_send

    # is_connected를 True로 설정
    class FakeWs:
        is_connected = True
    session._media_ws = FakeWs()

    await session.send_dtmf_sequence("1")
    assert sent == ["1"]


@pytest.mark.asyncio
async def test_send_dtmf_sequence_with_wait():
    """w/W 대기 문자 처리."""
    session = CallSession(
        call_id="CA_test", from_number="010", to_number="070", account_id="AC",
    )
    sent = []
    mock_send = AsyncMock(side_effect=lambda d: sent.append(d))
    session._send_dtmf_fn = mock_send

    class FakeWs:
        is_connected = True
    session._media_ws = FakeWs()

    await session.send_dtmf_sequence("1w2")
    assert sent == ["1", "2"]


@pytest.mark.asyncio
async def test_send_dtmf_sequence_invalid():
    """유효하지 않은 문자에 대해 ValueError 발생."""
    session = CallSession(
        call_id="CA_test", from_number="010", to_number="070", account_id="AC",
    )
    session._send_dtmf_fn = AsyncMock()
    class FakeWs:
        is_connected = True
    session._media_ws = FakeWs()

    with pytest.raises(ValueError, match="유효하지 않은 DTMF 문자"):
        await session.send_dtmf_sequence("1A2")


@pytest.mark.asyncio
async def test_collect_dtmf_max_digits():
    """max_digits에 도달하면 수집 종료."""
    session = CallSession(
        call_id="CA_test", from_number="010", to_number="070", account_id="AC",
    )

    async def feed():
        await asyncio.sleep(0.05)
        session._route_dtmf("1")
        await asyncio.sleep(0.05)
        session._route_dtmf("2")
        await asyncio.sleep(0.05)
        session._route_dtmf("3")

    asyncio.create_task(feed())
    result = await session.collect_dtmf(max_digits=3, timeout=5)
    assert result == "123"


@pytest.mark.asyncio
async def test_collect_dtmf_finish_on_key():
    """finish_on_key 입력 시 수집 종료."""
    session = CallSession(
        call_id="CA_test", from_number="010", to_number="070", account_id="AC",
    )

    async def feed():
        await asyncio.sleep(0.05)
        session._route_dtmf("1")
        await asyncio.sleep(0.05)
        session._route_dtmf("2")
        await asyncio.sleep(0.05)
        session._route_dtmf("#")

    asyncio.create_task(feed())
    result = await session.collect_dtmf(max_digits=10, finish_on_key="#", timeout=5)
    assert result == "12"


@pytest.mark.asyncio
async def test_collect_dtmf_timeout():
    """타임아웃 시 빈 문자열 반환."""
    session = CallSession(
        call_id="CA_test", from_number="010", to_number="070", account_id="AC",
    )
    result = await session.collect_dtmf(max_digits=4, timeout=0.1)
    assert result == ""


@pytest.mark.asyncio
async def test_collect_dtmf_double_call():
    """collect_dtmf 중복 호출 시 에러."""
    session = CallSession(
        call_id="CA_test", from_number="010", to_number="070", account_id="AC",
    )

    async def first():
        return await session.collect_dtmf(max_digits=4, timeout=1)

    task = asyncio.create_task(first())
    await asyncio.sleep(0.05)

    with pytest.raises(RuntimeError, match="이미 DTMF 수집 중"):
        await session.collect_dtmf(max_digits=4, timeout=1)

    session._route_dtmf("1")
    session._route_dtmf("2")
    session._route_dtmf("3")
    session._route_dtmf("4")
    await task
