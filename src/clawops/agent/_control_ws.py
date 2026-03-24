"""Control WebSocket: ClawOps 서버에 대한 상시 연결 관리.

Agent가 서버에 역방향으로 연결하여 인바운드 콜 알림을 수신한다.
자동 재연결(exponential backoff) 포함.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Awaitable
from urllib.parse import quote

import aiohttp

log = logging.getLogger("clawops.agent")

INITIAL_RECONNECT_DELAY = 1.0
MAX_RECONNECT_DELAY = 30.0


def build_control_ws_url(*, base_url: str, account_id: str, number: str) -> str:
    scheme = "wss" if base_url.startswith("https") else "ws"
    host = base_url.replace("https://", "").replace("http://", "").rstrip("/")
    return f"{scheme}://{host}/v1/accounts/{account_id}/agent/listen?number={quote(number)}"


class ControlWebSocket:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        account_id: str,
        number: str,
        on_call_incoming: Callable[[dict[str, Any]], Awaitable[None]],
        on_call_ended: Callable[[dict[str, Any]], Awaitable[None]],
        on_call_outbound_ready: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_call_ringing: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_call_failed: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._url = build_control_ws_url(base_url=base_url, account_id=account_id, number=number)
        self._api_key = api_key
        self._on_call_incoming = on_call_incoming
        self._on_call_ended = on_call_ended
        self._on_call_outbound_ready = on_call_outbound_ready
        self._on_call_ringing = on_call_ringing
        self._on_call_failed = on_call_failed
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._connected = asyncio.Event()
        self._transfer_futures: dict[str, asyncio.Future] = {}

    async def wait_connected(self, timeout: float = 10.0) -> None:
        """Control WS 연결이 완료될 때까지 대기한다."""
        await asyncio.wait_for(self._connected.wait(), timeout)

    async def connect(self) -> None:
        self._running = True
        delay = INITIAL_RECONNECT_DELAY

        while self._running:
            try:
                self._connected.clear()
                self._session = aiohttp.ClientSession()
                self._ws = await self._session.ws_connect(
                    self._url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    heartbeat=30.0,
                )
                self._connected.set()
                log.info(f"Control WS connected: {self._url}")
                delay = INITIAL_RECONNECT_DELAY

                async for msg in self._ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        event = data.get("event")
                        if event == "call.incoming":
                            await self._on_call_incoming(data)
                        elif event == "call.ended":
                            await self._on_call_ended(data)
                        elif event == "call.outbound_ready" and self._on_call_outbound_ready:
                            await self._on_call_outbound_ready(data)
                        elif event == "call.ringing" and self._on_call_ringing:
                            await self._on_call_ringing(data)
                        elif event == "call.failed" and self._on_call_failed:
                            await self._on_call_failed(data)
                        elif event in (
                            "call.transfer.started",
                            "call.transfer.connected",
                            "call.transfer.completed",
                            "call.transfer.failed",
                        ):
                            self._on_transfer_event(data)
                    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                        break

            except (aiohttp.ClientError, OSError) as e:
                if "CERTIFICATE_VERIFY_FAILED" in str(e):
                    log.error(
                        "SSL 인증서 검증에 실패했습니다. "
                        "'pip install --upgrade certifi'를 실행해 보세요. "
                        "자세한 해결 방법: "
                        "https://github.com/learners-superpumped/clawops-python/blob/main/docs/agent/troubleshooting.md#ssl-인증서-에러-sslcertverificationerror"
                    )
                log.warning(f"Control WS error: {e}")
            finally:
                if self._ws and not self._ws.closed:
                    await self._ws.close()
                if self._session:
                    await self._session.close()
                self._ws = None
                self._session = None

            if self._running:
                log.info(f"Control WS reconnecting in {delay:.1f}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY)

    async def request_transfer(self, call_id: str, transfer_params: dict) -> dict:
        """콜 전환을 요청하고 완료/실패 응답을 기다린다."""
        future = asyncio.get_event_loop().create_future()
        self._transfer_futures[call_id] = future
        await self._ws.send_str(json.dumps({
            "event": "call.transfer",
            "callId": call_id,
            "transfer": transfer_params,
        }))
        timeout = transfer_params.get("timeout", 30) + 10
        return await asyncio.wait_for(future, timeout=timeout)

    def _on_transfer_event(self, data: dict) -> None:
        """전환 관련 이벤트를 처리하여 대기 중인 Future를 resolve한다."""
        call_id = data.get("callId")
        event = data.get("event")
        if not call_id or call_id not in self._transfer_futures:
            return
        if event in ("call.transfer.completed", "call.transfer.failed"):
            self._transfer_futures.pop(call_id).set_result(data.get("transfer", {}))

    async def send(self, data: dict[str, Any]) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_str(json.dumps(data))

    async def close(self) -> None:
        self._running = False
        for fut in self._transfer_futures.values():
            if not fut.done():
                fut.cancel()
        self._transfer_futures.clear()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session:
            await self._session.close()
