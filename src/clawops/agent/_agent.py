"""ClawOpsAgent: 메인 진입점.

Control WS 연결, per-call Media WS 생성, RealtimeSession 관리를 조합한다.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Awaitable

from .._exceptions import AgentError
from ._control_ws import ControlWebSocket
from .mcp._client import MCPClient
from ._media_ws import MediaWebSocket
from ._session import CallSession
from ._recorder import AudioRecorder
from ._tool import ToolRegistry
from .pipeline._base import STT, LLM, TTS
from .pipeline._realtime_session import RealtimeConfig, RealtimeSession

log = logging.getLogger("clawops.agent")


class ClawOpsAgent:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
        from_: str,
        system_prompt: str = "",
        voice: str = "marin",
        model: str = "gpt-realtime-mini",
        openai_api_key: str | None = None,
        language: str = "ko",
        eagerness: str = "high",
        greeting: bool = True,
        stt: STT | None = None,
        llm: LLM | None = None,
        tts: TTS | None = None,
        mcp_servers: list[Any] | None = None,
        recording: bool = False,
        recording_path: str = "./recordings",
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("CLAWOPS_API_KEY")
        if api_key is None:
            raise AgentError("api_key를 지정하거나 CLAWOPS_API_KEY 환경변수를 설정하세요.")

        if account_id is None:
            account_id = os.environ.get("CLAWOPS_ACCOUNT_ID")
        if account_id is None:
            raise AgentError("account_id를 지정하거나 CLAWOPS_ACCOUNT_ID 환경변수를 설정하세요.")

        if openai_api_key is None:
            openai_api_key = os.environ.get("OPENAI_API_KEY", "")

        if base_url is None:
            base_url = os.environ.get("CLAWOPS_BASE_URL", "https://api.claw-ops.com")

        self._api_key = api_key
        self._account_id = account_id
        self._base_url = base_url
        self._from_number = from_

        self._config = RealtimeConfig(
            system_prompt=system_prompt,
            openai_api_key=openai_api_key,
            voice=voice,
            model=model,
            language=language,
            eagerness=eagerness,
            greeting=greeting,
        )

        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._mcp_servers = mcp_servers or []
        self._recording = recording
        self._recording_path = recording_path

        self._tool_registry = ToolRegistry()
        self._event_handlers: dict[str, list[Callable[..., Awaitable[None]]]] = {}
        self._active_sessions: dict[str, CallSession] = {}
        self._control_ws: ControlWebSocket | None = None

    def tool(self, fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        return self._tool_registry.register(fn)

    def on(self, event: str) -> Callable:
        def decorator(fn: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
            self._event_handlers.setdefault(event, []).append(fn)
            return fn
        return decorator

    def listen(self) -> None:
        log.info(f"ClawOpsAgent listening on {self._from_number}")
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            log.info("Agent stopped by user")

    async def _run(self) -> None:
        self._control_ws = ControlWebSocket(
            base_url=self._base_url,
            api_key=self._api_key,
            account_id=self._account_id,
            number=self._from_number,
            on_call_incoming=self._handle_incoming,
            on_call_ended=self._handle_ended,
        )
        await self._control_ws.connect()

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
        )

        for event, handlers in self._event_handlers.items():
            for handler in handlers:
                call.on(event, handler)

        self._active_sessions[call_id] = call

        if self._control_ws:
            await self._control_ws.send({"event": "call.accept", "callId": call_id})

        asyncio.create_task(self._start_call_session(call, media_url))

    async def _start_call_session(self, call: CallSession, media_url: str) -> None:
        recorder: AudioRecorder | None = None
        if self._recording:
            recorder = AudioRecorder(self._recording_path, call.call_id)
            recorder.start()

        mcp_clients: list[MCPClient] = []
        if self._mcp_servers:
            log.debug("Starting %d MCP server(s) for call %s", len(self._mcp_servers), call.call_id)
            for server_config in self._mcp_servers:
                client = MCPClient(server_config)
                await client.connect()
                mcp_clients.append(client)
            self._tool_registry.register_mcp_tools(mcp_clients)

        realtime = RealtimeSession(self._config, self._tool_registry, recorder=recorder)

        async def on_audio(pcm: bytes, ts: int) -> None:
            if recorder:
                recorder.write_inbound(pcm)
            await realtime.feed_audio(pcm, ts)

        media_ws = MediaWebSocket(
            url=media_url,
            api_key=self._api_key,
            on_audio=on_audio,
            on_start=lambda info: self._on_media_start(call, info),
            on_stop=lambda: self._on_media_stop(call, realtime),
        )

        call._send_audio_fn = media_ws.send_audio
        call._send_clear_fn = media_ws.send_clear
        call._hangup_fn = lambda: media_ws.close()

        await call._emit("call_start")
        await realtime.start(call)

        try:
            await media_ws.connect()
        finally:
            await realtime.stop()
            if mcp_clients:
                self._tool_registry.clear_mcp_tools()
                for c in mcp_clients:
                    await c.close()
            if recorder:
                recorder.stop()
            await call._emit("call_end")
            self._active_sessions.pop(call.call_id, None)

    async def _on_media_start(self, call: CallSession, info: dict[str, Any]) -> None:
        log.info(f"Media stream started: {call.call_id}")

    async def _on_media_stop(self, call: CallSession, realtime: RealtimeSession) -> None:
        log.info(f"Media stream stopped: {call.call_id}")
        await realtime.stop()

    async def _handle_ended(self, data: dict[str, Any]) -> None:
        call_id = data.get("callId", "")
        log.info(f"Call ended (server): {call_id}")
        self._active_sessions.pop(call_id, None)
