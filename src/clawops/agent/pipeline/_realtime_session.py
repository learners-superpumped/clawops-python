"""OpenAI Realtime API 세션 관리.

../ai-agent/session_manager.py의 핵심 로직을 SDK 구조로 포팅.
CallSession당 하나의 RealtimeSession이 생성된다.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

from .._audio import pcm16_to_ulaw, ulaw_to_pcm16
from .._recorder import AudioRecorder
from .._session import CallSession
from .._tool import ToolRegistry
from ..tracing._spans import tool_call_span, llm_session_span

log = logging.getLogger("clawops.agent")

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model={model}"

HANG_UP_TOOL = {
    "type": "function",
    "name": "hang_up",
    "description": "End the phone call. Use when the conversation is finished or the caller says goodbye.",
    "parameters": {"type": "object", "properties": {}},
}


@dataclass
class RealtimeConfig:
    system_prompt: str
    openai_api_key: str
    voice: str = "marin"
    model: str = "gpt-realtime-mini"
    language: str = "ko"
    eagerness: str = "high"
    greeting: bool = True


class RealtimeSession:
    def __init__(self, config: RealtimeConfig, tool_registry: ToolRegistry, *, recorder: AudioRecorder | None = None) -> None:
        self._config = config
        self._tools = tool_registry
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._http: aiohttp.ClientSession | None = None
        self._call: CallSession | None = None
        self._last_assistant_item: str | None = None
        self._response_start_ts: int | None = None
        self._latest_media_ts: int = 0
        self._recorder = recorder
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._tasks: list[asyncio.Task[Any]] = []
        self._llm_span_ctx: Any | None = None
        self._llm_span: Any | None = None

    async def start(self, call: CallSession) -> None:
        self._call = call

        # Start LLM session span
        self._llm_span_ctx = llm_session_span(
            self._config.model, voice=self._config.voice
        )
        self._llm_span = self._llm_span_ctx.__enter__()

        url = OPENAI_REALTIME_URL.format(model=self._config.model)

        self._http = aiohttp.ClientSession()
        self._ws = await self._http.ws_connect(
            url,
            headers={
                "Authorization": f"Bearer {self._config.openai_api_key}",
                "OpenAI-Beta": "realtime=v1",
            },
        )
        log.info("OpenAI Realtime connected")

        tool_schemas = self._tools.to_openai_tools() + [HANG_UP_TOOL]

        await self._send({
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "voice": self._config.voice,
                "instructions": self._config.system_prompt,
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "input_audio_transcription": {
                    "model": "gpt-4o-mini-transcribe",
                    "language": self._config.language,
                },
                "input_audio_noise_reduction": {"type": "far_field"},
                "turn_detection": {
                    "type": "semantic_vad",
                    "interrupt_response": True,
                    "eagerness": self._config.eagerness,
                },
                "tools": tool_schemas,
            },
        })

        if self._config.greeting:
            await self._send({"type": "response.create"})

        self._tasks.append(asyncio.create_task(self._receive_loop()))
        self._tasks.append(asyncio.create_task(self._audio_send_loop()))

    async def feed_audio(self, pcm16: bytes, timestamp: int) -> None:
        self._latest_media_ts = timestamp
        ulaw = pcm16_to_ulaw(pcm16)
        await self._send({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(ulaw).decode(),
        })

    async def _receive_loop(self) -> None:
        if not self._ws:
            return
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    event = json.loads(msg.data)
                    await self._handle_event(event)
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    break
        except Exception as e:
            log.error(f"Realtime receive error: {e}")
        finally:
            await self._cleanup()

    async def _handle_event(self, event: dict[str, Any]) -> None:
        if not self._call:
            return
        event_type = event.get("type")

        if event_type == "response.audio.delta":
            if self._response_start_ts is None:
                self._response_start_ts = self._latest_media_ts
            if event.get("item_id"):
                self._last_assistant_item = event["item_id"]

            ulaw = base64.b64decode(event["delta"])
            pcm16 = ulaw_to_pcm16(ulaw)
            chunk_size = 320  # 320B = 20ms at 8kHz 16-bit
            for off in range(0, len(pcm16), chunk_size):
                self._audio_queue.put_nowait(pcm16[off : off + chunk_size])

        elif event_type == "input_audio_buffer.speech_started":
            await self._handle_truncation()

        elif event_type == "response.output_item.done":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                await self._handle_tool_call(item)

        elif event_type == "conversation.item.input_audio_transcription.completed":
            await self._call._emit("transcript", "user", event.get("transcript", ""))

        elif event_type == "response.audio_transcript.done":
            await self._call._emit("transcript", "assistant", event.get("transcript", ""))

        elif event_type == "error":
            log.error(f"OpenAI error: {event.get('error')}")

    async def _handle_tool_call(self, item: dict[str, Any]) -> None:
        func_name = item.get("name", "")
        call_id = item.get("call_id", "")
        log.info(f"Tool call: {func_name}({item.get('arguments')})")

        if func_name == "hang_up":
            if self._call:
                await self._call.hangup()
            return

        # Determine source
        source = "mcp" if func_name in self._tools._mcp_tools else "local"

        with tool_call_span(func_name, source):
            try:
                args = json.loads(item.get("arguments", "{}"))
                result = await self._tools.call(func_name, args)
            except Exception as e:
                log.error(f"Tool call failed: {func_name}: {e}")
                result = f"Error: {e}"

        log.debug(f"Tool result: {func_name} -> {str(result)[:200]}")

        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": str(result),
            },
        })
        log.debug(f"Sent function_call_output for {func_name}, requesting response")
        await self._send({"type": "response.create"})

    async def _handle_truncation(self) -> None:
        if not self._last_assistant_item or self._response_start_ts is None:
            return

        elapsed = self._latest_media_ts - self._response_start_ts
        audio_end_ms = max(0, elapsed)

        await self._send({
            "type": "conversation.item.truncate",
            "item_id": self._last_assistant_item,
            "content_index": 0,
            "audio_end_ms": audio_end_ms,
        })

        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        if self._call:
            await self._call.clear_audio()

        self._last_assistant_item = None
        self._response_start_ts = None

    async def _audio_send_loop(self) -> None:
        try:
            while True:
                chunk = await self._audio_queue.get()
                if chunk is None:
                    break
                if self._call:
                    await self._call.send_audio(chunk)
                if self._recorder:
                    self._recorder.write_outbound(chunk)
                await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            pass

    async def _send(self, data: dict[str, Any]) -> None:
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_str(json.dumps(data))
            except Exception as e:
                log.error(f"WebSocket send failed ({data.get('type')}): {e}")

    async def stop(self) -> None:
        self._audio_queue.put_nowait(None)
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()
        await self._cleanup()

    async def _cleanup(self) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        if self._http:
            await self._http.close()
        self._http = None
        # Close LLM session span, propagating any active exception info
        if self._llm_span_ctx:
            import sys
            exc_info = sys.exc_info()
            self._llm_span_ctx.__exit__(*exc_info)
            self._llm_span_ctx = None
            self._llm_span = None
