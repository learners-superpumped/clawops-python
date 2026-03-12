"""DTMF 라우팅 및 패시브 DTMF 테스트."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_passive_dtmf_debounce():
    """패시브 DTMF가 debounce 후 feed_dtmf를 호출하는지 확인."""
    from clawops.agent._agent import ClawOpsAgent
    from clawops.agent.pipeline._base import Session

    # 최소 Session mock
    mock_session = MagicMock(spec=Session)
    mock_session.feed_dtmf = AsyncMock()

    agent = ClawOpsAgent(
        api_key="test_key",
        account_id="AC_test",
        from_="01012345678",
        session=mock_session,
        passive_dtmf_debounce_ms=100,
    )

    # 패시브 DTMF 테스트를 위한 mock call
    from clawops.agent._session import CallSession
    mock_call = CallSession(
        call_id="CA_test", from_number="010", to_number="070", account_id="AC",
    )
    agent._call_sessions["CA_test"] = mock_session
    agent._active_sessions["CA_test"] = mock_call

    agent._on_dtmf_event(mock_call, "1")
    agent._on_dtmf_event(mock_call, "2")
    agent._on_dtmf_event(mock_call, "3")

    # debounce 대기 (100ms + 여유)
    await asyncio.sleep(0.2)

    mock_session.feed_dtmf.assert_awaited_once_with("123")


@pytest.mark.asyncio
async def test_passive_dtmf_routing_to_collector():
    """collect_dtmf 활성 시 패시브 DTMF가 아닌 collector 큐로 라우팅."""
    from clawops.agent._session import CallSession

    session = CallSession(
        call_id="CA_test", from_number="010", to_number="070", account_id="AC",
    )

    async def collect():
        return await session.collect_dtmf(max_digits=3, timeout=2)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.05)

    # collector가 활성화된 상태에서 digit 라우팅
    session._route_dtmf("4")
    session._route_dtmf("5")
    session._route_dtmf("6")

    result = await task
    assert result == "456"
