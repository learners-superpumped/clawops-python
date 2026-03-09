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
        self._sent_audio_chunks: int = 0
        self._recorder = recorder
        self._tasks: list[asyncio.Task[Any]] = []
        self._llm_span_ctx: Any | None = None
        self._llm_span: Any | None = None
        self._audio_remainder: bytes = b""  # 160B 미만 잔여 오디오 버퍼

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

    async def feed_audio(self, audio: bytes, timestamp: int) -> None:
        self._latest_media_ts = timestamp
        # Agent 경로: 플랫폼에서 ulaw 직통으로 받으므로 변환 불필요
        await self._send({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio).decode(),
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
                self._sent_audio_chunks = 0
                self._diag_delta_count = 0
                self._diag_last_delta_time = asyncio.get_event_loop().time()
            if event.get("item_id"):
                self._last_assistant_item = event["item_id"]

            ulaw = base64.b64decode(event["delta"])
            # 진단: OpenAI delta 도착 간격 (50개마다)
            self._diag_delta_count = getattr(self, "_diag_delta_count", 0) + 1
            now = asyncio.get_event_loop().time()
            if self._diag_delta_count % 50 == 0:
                elapsed = now - getattr(self, "_diag_last_delta_time", now)
                log.info(
                    f"[OAI-DIAG] delta#{self._diag_delta_count} "
                    f"last50in={elapsed*1000:.0f}ms "
                    f"avg={elapsed*1000/50:.1f}ms/delta "
                    f"size={len(ulaw)}B "
                    f"totalChunks={self._sent_audio_chunks}"
                )
                self._diag_last_delta_time = now
            if self._recorder:
                self._recorder.write_raw_outbound(ulaw)
            # 잔여 바이트와 합쳐서 항상 160B(20ms) 정렬된 프레임만 전송
            ulaw = self._audio_remainder + ulaw
            chunk_size = 160  # 160B = 20ms at 8kHz ulaw
            full_end = (len(ulaw) // chunk_size) * chunk_size
            for off in range(0, full_end, chunk_size):
                await self._call.send_audio(ulaw[off : off + chunk_size])
                self._sent_audio_chunks += 1
            self._audio_remainder = ulaw[full_end:]

        elif event_type == "response.audio.done":
            # 응답 오디오 종료 — 잔여 바이트를 silence 패딩하여 flush
            if self._audio_remainder:
                padded = self._audio_remainder + b'\xff' * (160 - len(self._audio_remainder))
                await self._call.send_audio(padded)
                self._sent_audio_chunks += 1
                self._audio_remainder = b""

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

        # 실제 송신한 오디오 양 기반으로 계산 (160B = 20ms per ulaw chunk)
        audio_end_ms = max(0, self._sent_audio_chunks * 20)

        await self._send({
            "type": "conversation.item.truncate",
            "item_id": self._last_assistant_item,
            "content_index": 0,
            "audio_end_ms": audio_end_ms,
        })

        if self._call:
            await self._call.clear_audio()

        self._last_assistant_item = None
        self._response_start_ts = None
        self._sent_audio_chunks = 0
        self._audio_remainder = b""

    async def _send(self, data: dict[str, Any]) -> None:
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_str(json.dumps(data))
            except Exception as e:
                log.error(f"WebSocket send failed ({data.get('type')}): {e}")

    async def stop(self) -> None:
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
