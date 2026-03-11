"""ClawOpsAgent: 메인 진입점.

Control WS 연결, per-call Media WS 생성, Session 관리를 조합한다.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any, Callable, Awaitable

from .._exceptions import AgentError
from ._control_ws import ControlWebSocket
from .mcp._client import MCPClient
from ._media_ws import MediaWebSocket
from ._session import CallSession
from ._recorder import AudioRecorder
from ._tool import ToolRegistry
from .pipeline._base import Session
from .tracing import TracingConfig
from .tracing._spans import call_span, mcp_connect_span, setup_tracing

log = logging.getLogger("clawops.agent")


class ClawOpsAgent:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
        from_: str,
        session: Session,
        mcp_servers: list[Any] | None = None,
        recording: bool = False,
        recording_path: str = "./recordings",
        tracing: TracingConfig | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("CLAWOPS_API_KEY")
        if api_key is None:
            raise AgentError("api_key를 지정하거나 CLAWOPS_API_KEY 환경변수를 설정하세요.")

        if account_id is None:
            account_id = os.environ.get("CLAWOPS_ACCOUNT_ID")
        if account_id is None:
            raise AgentError("account_id를 지정하거나 CLAWOPS_ACCOUNT_ID 환경변수를 설정하세요.")

        if base_url is None:
            base_url = os.environ.get("CLAWOPS_BASE_URL", "https://api.claw-ops.com")

        self._api_key = api_key
        self._account_id = account_id
        self._base_url = base_url
        self._from_number = from_

        self._session = session
        self._mcp_servers = mcp_servers or []
        self._recording = recording
        self._recording_path = recording_path
        self._tracing = tracing

        if self._tracing is not None:
            setup_tracing(self._tracing)

        self._tool_registry = ToolRegistry()
        self._event_handlers: dict[str, list[Callable[..., Awaitable[None]]]] = {}
        self._active_sessions: dict[str, CallSession] = {}
        self._control_ws: ControlWebSocket | None = None
        self._control_ws_task: asyncio.Task[Any] | None = None

    def tool(self, fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        return self._tool_registry.register(fn)

    def on(self, event: str) -> Callable:
        def decorator(fn: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
            self._event_handlers.setdefault(event, []).append(fn)
            return fn
        return decorator

    async def connect(self) -> None:
        """Control WS에 연결한다. 블로킹하지 않는다."""
        if self._control_ws is not None:
            return
        await self._ensure_control_ws()
        log.info(f"ClawOpsAgent connected on {self._from_number}")

    async def serve(self) -> None:
        """인바운드 서버 모드: SIGINT/SIGTERM까지 대기 후 자동으로 disconnect()를 호출한다.

        connect()가 호출되지 않은 상태면 자동으로 connect()를 먼저 수행한다.
        """
        await self.connect()
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        try:
            await stop_event.wait()
        finally:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(sig)
            await self.disconnect()

    async def disconnect(self) -> None:
        """Control WS 닫기 + 활성 세션 정리."""
        if self._control_ws:
            await self._control_ws.close()
            self._control_ws = None
        if self._control_ws_task and not self._control_ws_task.done():
            self._control_ws_task.cancel()
            self._control_ws_task = None
        self._active_sessions.clear()
        log.info("ClawOpsAgent disconnected")

    async def _ensure_control_ws(self) -> None:
        """Control WS가 없으면 연결한다."""
        if self._control_ws is not None:
            return
        self._control_ws = ControlWebSocket(
            base_url=self._base_url,
            api_key=self._api_key,
            account_id=self._account_id,
            number=self._from_number,
            on_call_incoming=self._handle_incoming,
            on_call_ended=self._handle_ended,
            on_call_outbound_ready=self._handle_outbound_ready,
            on_call_ringing=self._handle_ringing,
            on_call_failed=self._handle_failed,
        )
        self._control_ws_task = asyncio.create_task(self._control_ws.connect())
        await self._control_ws.wait_connected()

    async def call(self, to: str, *, timeout: int = 60) -> CallSession:
        """발신 전화를 건다. CallSession을 즉시 리턴 (queued 상태).

        connect()가 호출되지 않은 상태면 자동으로 connect()를 먼저 수행한다.
        """
        await self.connect()

        import aiohttp as _aiohttp
        url = f"{self._base_url}/v1/accounts/{self._account_id}/calls"
        body = {"To": to, "From": self._from_number, "Timeout": timeout}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with _aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                if resp.status != 201:
                    error = await resp.json()
                    err_msg = error.get("error", "")
                    err_code = error.get("code", "")
                    agent_err = AgentError(f"발신 실패 ({resp.status}): {err_msg}")
                    agent_err.status = resp.status
                    agent_err.code = err_code
                    raise agent_err
                data = await resp.json()

        call_session = CallSession(
            call_id=data["callId"],
            from_number=self._from_number,
            to_number=to,
            account_id=self._account_id,
            direction="outbound",
        )

        for event, handlers in self._event_handlers.items():
            for handler in handlers:
                call_session.on(event, handler)

        self._active_sessions[call_session.call_id] = call_session
        log.info(f"Outbound call initiated: {self._from_number} -> {to} ({call_session.call_id})")
        return call_session

    async def _handle_incoming(self, data: dict[str, Any]) -> None:
        call_id = data["callId"]
        from_number = data.get("from", "")
        media_url = data.get("mediaUrl", "")

        log.info(f"Incoming call: {from_number} -> {self._from_number} ({call_id})")

        call = CallSession(
            call_id=call_id,
            from_number=from_number,
            to_number=self._from_number,
            account_id=self._account_id,
            direction="inbound",
        )

        for event, handlers in self._event_handlers.items():
            for handler in handlers:
                call.on(event, handler)

        self._active_sessions[call_id] = call

        if self._control_ws:
            await self._control_ws.send({"event": "call.accept", "callId": call_id})

        asyncio.create_task(self._start_call_session(call, media_url))

    async def _start_call_session(self, call: CallSession, media_url: str) -> None:
        with call_span(
            call.call_id,
            from_number=call.from_number,
            to_number=call.to_number,
        ):
            recorder: AudioRecorder | None = None
            if self._recording:
                recorder = AudioRecorder(self._recording_path, call.call_id)
                recorder.start()

            # 콜별 독립 ToolRegistry (동시 통화 간 MCP tool 충돌 방지)
            call_tools = self._tool_registry.fork()

            mcp_clients: list[MCPClient] = []
            if self._mcp_servers:
                log.debug("Starting %d MCP server(s) for call %s", len(self._mcp_servers), call.call_id)
                for server_config in self._mcp_servers:
                    from .mcp._stdio import MCPServerStdio as _Stdio
                    if isinstance(server_config, _Stdio):
                        span_ctx = mcp_connect_span("stdio", command=server_config.command)
                    else:
                        span_ctx = mcp_connect_span("http", url=server_config.url)
                    with span_ctx:
                        client = MCPClient(server_config)
                        await client.connect()
                        mcp_clients.append(client)
                call_tools.register_mcp_tools(mcp_clients)

            session = self._session
            if hasattr(session, "set_tool_registry"):
                session.set_tool_registry(call_tools)
            if recorder and hasattr(session, "set_recorder"):
                session.set_recorder(recorder)

            async def on_audio(ulaw: bytes, ts: int) -> None:
                await session.feed_audio(ulaw, ts)
                if recorder:
                    from ._audio import ulaw_to_pcm16
                    recorder.write_inbound(ulaw_to_pcm16(ulaw))

            media_ws = MediaWebSocket(
                url=media_url,
                api_key=self._api_key,
                on_audio=on_audio,
                on_start=lambda info: self._on_media_start(call, info),
                on_stop=lambda: self._on_media_stop(call, session),
            )

            call._send_audio_fn = media_ws.send_audio
            call._send_clear_fn = media_ws.send_clear
            call._hangup_fn = lambda: media_ws.close()

            await call._emit("call_start")
            await session.start(call)

            try:
                await media_ws.connect()
            finally:
                await session.stop()
                if mcp_clients:
                    call_tools.clear_mcp_tools()
                    for c in mcp_clients:
                        await c.close()
                if recorder:
                    recorder.stop()
                await call._emit("call_end")
                call._mark_ended()
                self._active_sessions.pop(call.call_id, None)

    async def _on_media_start(self, call: CallSession, info: dict[str, Any]) -> None:
        log.info(f"Media stream started: {call.call_id}")

    async def _on_media_stop(self, call: CallSession, session: Session) -> None:
        log.info(f"Media stream stopped: {call.call_id}")
        await session.stop()

    async def _handle_outbound_ready(self, data: dict[str, Any]) -> None:
        call_id = data["callId"]
        media_url = data.get("mediaUrl", "")
        call = self._active_sessions.get(call_id)
        if not call:
            log.warning(f"Unknown outbound call: {call_id}")
            return
        call.status = "in-progress"
        log.info(f"Outbound call answered: {call.from_number} -> {call.to_number} ({call_id})")
        asyncio.create_task(self._start_call_session(call, media_url))

    async def _handle_ringing(self, data: dict[str, Any]) -> None:
        call_id = data.get("callId", "")
        call = self._active_sessions.get(call_id)
        if call:
            call.status = "ringing"
            log.info(f"Outbound call ringing: {call_id}")

    async def _handle_failed(self, data: dict[str, Any]) -> None:
        call_id = data.get("callId", "")
        reason = data.get("reason", "failed")
        call = self._active_sessions.get(call_id)
        if call:
            call.status = reason
            log.info(f"Outbound call failed: {call_id} ({reason})")
            await call._emit("call_failed", reason)
            call._mark_ended()
            self._active_sessions.pop(call_id, None)

    async def _handle_ended(self, data: dict[str, Any]) -> None:
        call_id = data.get("callId", "")
        call = self._active_sessions.get(call_id)
        log.info(f"Call ended (server): {call_id}")
        if call:
            call._mark_ended()
        self._active_sessions.pop(call_id, None)
