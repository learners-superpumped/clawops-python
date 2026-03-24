# tests/agent/test_transfer.py
"""Tests for transfer event handling in ControlWebSocket."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawops.agent._control_ws import ControlWebSocket


def _make_control_ws(**overrides) -> ControlWebSocket:
    defaults = dict(
        base_url="http://localhost:3000",
        api_key="test-key",
        account_id="AC123",
        number="07012341234",
        on_call_incoming=AsyncMock(),
        on_call_ended=AsyncMock(),
    )
    defaults.update(overrides)
    return ControlWebSocket(**defaults)


@pytest.mark.asyncio
async def test_request_transfer_sends_message_and_waits():
    """request_transfer sends the correct JSON and resolves on completed."""
    cws = _make_control_ws()
    mock_ws = MagicMock()
    mock_ws.send_str = AsyncMock()
    cws._ws = mock_ws

    call_id = "CALL-001"
    transfer_params = {"destination": "07099998888", "timeout": 20}

    # Start request_transfer in background
    task = asyncio.create_task(
        cws.request_transfer(call_id, transfer_params)
    )
    # Let the coroutine progress to the await point
    await asyncio.sleep(0)

    # Verify the message was sent
    mock_ws.send_str.assert_called_once()
    sent = json.loads(mock_ws.send_str.call_args[0][0])
    assert sent["event"] == "call.transfer"
    assert sent["callId"] == call_id
    assert sent["transfer"] == transfer_params

    # Simulate completed event
    cws._on_transfer_event({
        "event": "call.transfer.completed",
        "callId": call_id,
        "transfer": {"status": "completed"},
    })

    result = await task
    assert result == {"status": "completed"}
    assert call_id not in cws._transfer_futures


@pytest.mark.asyncio
async def test_on_transfer_event_completed_resolves_future():
    """_on_transfer_event with completed resolves the pending future."""
    cws = _make_control_ws()
    call_id = "CALL-002"
    future = asyncio.get_event_loop().create_future()
    cws._transfer_futures[call_id] = future

    cws._on_transfer_event({
        "event": "call.transfer.completed",
        "callId": call_id,
        "transfer": {"status": "completed", "duration": 5},
    })

    assert future.done()
    assert await future == {"status": "completed", "duration": 5}
    assert call_id not in cws._transfer_futures


@pytest.mark.asyncio
async def test_on_transfer_event_failed_resolves_future():
    """_on_transfer_event with failed resolves the pending future."""
    cws = _make_control_ws()
    call_id = "CALL-003"
    future = asyncio.get_event_loop().create_future()
    cws._transfer_futures[call_id] = future

    cws._on_transfer_event({
        "event": "call.transfer.failed",
        "callId": call_id,
        "transfer": {"status": "failed", "reason": "no-answer"},
    })

    assert future.done()
    assert await future == {"status": "failed", "reason": "no-answer"}
    assert call_id not in cws._transfer_futures


@pytest.mark.asyncio
async def test_on_transfer_event_ignores_unknown_call_id():
    """_on_transfer_event ignores events for unknown callIds."""
    cws = _make_control_ws()
    call_id = "CALL-KNOWN"
    future = asyncio.get_event_loop().create_future()
    cws._transfer_futures[call_id] = future

    # Event with unknown callId should be ignored
    cws._on_transfer_event({
        "event": "call.transfer.completed",
        "callId": "CALL-UNKNOWN",
        "transfer": {"status": "completed"},
    })

    assert not future.done()
    assert call_id in cws._transfer_futures


@pytest.mark.asyncio
async def test_on_transfer_event_ignores_started_event():
    """_on_transfer_event does not resolve future on started/connected events."""
    cws = _make_control_ws()
    call_id = "CALL-004"
    future = asyncio.get_event_loop().create_future()
    cws._transfer_futures[call_id] = future

    cws._on_transfer_event({
        "event": "call.transfer.started",
        "callId": call_id,
        "transfer": {"status": "started"},
    })

    assert not future.done()
    assert call_id in cws._transfer_futures


@pytest.mark.asyncio
async def test_close_cancels_pending_transfer_futures():
    """close() cancels all pending transfer futures."""
    cws = _make_control_ws()
    future = asyncio.get_event_loop().create_future()
    cws._transfer_futures["CALL-005"] = future

    await cws.close()

    assert future.cancelled()
    assert len(cws._transfer_futures) == 0
