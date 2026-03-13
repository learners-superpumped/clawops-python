"""OpenAI Realtime API 세션.

Session Protocol을 구현하며, OpenAI Realtime WebSocket API를 사용한다.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI
from openai.types.realtime.realtime_audio_input_turn_detection_param import (
    RealtimeAudioInputTurnDetectionParam,
)
from openai.resources.realtime.realtime import AsyncRealtimeConnection

from ..._audio import ulaw_to_pcm16
from ..._builtin_tools import BuiltinTool
from ..._recorder import AudioRecorder
from ..._session import CallSession
from ..._tool import ToolRegistry
from ...tracing._spans import tool_call_span, llm_session_span
from .._builtin_tool_schemas import get_builtin_tool_schemas, execute_builtin_tool, BUILTIN_TOOL_NAMES

log = logging.getLogger("clawops.agent")


@dataclass
class OpenAIRealtimeConfig:
    """OpenAIRealtime 내부 설정. 하위 호환용으로 유지."""

    system_prompt: str
    openai_api_key: str
    voice: str = "marin"
    model: str = "gpt-realtime-1.5"
    language: str = "ko"
    turn_detection: RealtimeAudioInputTurnDetectionParam | None = None
    greeting: bool = True


class OpenAIRealtime:
    """OpenAI Realtime API 기반 음성 세션.

    Session Protocol을 구현한다. ``gpt-realtime-1.5``, ``gpt-4o-mini-realtime``
    등 OpenAI의 realtime 모델을 사용한다.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        system_prompt: str = "",
        model: str = "gpt-realtime-1.5",
        voice: str = "marin",
        language: str = "ko",
        turn_detection: RealtimeAudioInputTurnDetectionParam | None = None,
        greeting: bool = True,
        tool_registry: ToolRegistry | None = None,
        recorder: AudioRecorder | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if turn_detection is None:
            turn_detection = {
                "type": "semantic_vad",
                "eagerness": "medium",
                "interrupt_response": True,
            }
        self._config = OpenAIRealtimeConfig(
            system_prompt=system_prompt,
            openai_api_key=api_key,
            voice=voice,
            model=model,
            language=language,
            turn_detection=turn_detection,
            greeting=greeting,
        )
        self._tools = tool_registry or ToolRegistry()
        self._builtin_tools: set[BuiltinTool] | None = None
        self._client: AsyncOpenAI | None = None
        self._connection: AsyncRealtimeConnection | None = None
        self._call: CallSession | None = None
        self._last_assistant_item: str | None = None
        self._response_start_ts: int | None = None
        self._latest_media_ts: int = 0
        self._sent_audio_chunks: int = 0
        self._recorder = recorder
        self._tasks: list[asyncio.Task[Any]] = []
        self._pending_tool_tasks: set[asyncio.Task[Any]] = set()
        self._llm_span_ctx: Any | None = None
        self._llm_span: Any | None = None
        self._audio_remainder: bytes = b""  # 160B 미만 잔여 오디오 버퍼

    def set_tool_registry(self, registry: ToolRegistry) -> None:
        """콜별로 fork된 ToolRegistry를 주입한다."""
        self._tools = registry

    def set_builtin_tools(self, tools: set[BuiltinTool]) -> None:
        """사용할 내장 도구 set을 지정."""
        self._builtin_tools = tools

    def set_recorder(self, recorder: AudioRecorder) -> None:
        """콜별로 생성된 AudioRecorder를 주입한다."""
        self._recorder = recorder

    async def start(self, call: CallSession) -> None:
        self._call = call

        # Start LLM session span
        self._llm_span_ctx = llm_session_span(self._config.model, voice=self._config.voice)
        self._llm_span = self._llm_span_ctx.__enter__()

        self._client = AsyncOpenAI(api_key=self._config.openai_api_key)
        manager = self._client.realtime.connect(model=self._config.model)
        self._connection = await manager.enter()
        log.info("OpenAI Realtime connected")

        tool_schemas = self._tools.to_openai_tools()
        tool_schemas.extend(get_builtin_tool_schemas(self._builtin_tools, fmt="realtime"))

        await self._connection.session.update(
            session={
                "type": "realtime",
                "output_modalities": ["audio"],
                "instructions": self._config.system_prompt,
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcmu"},
                        "noise_reduction": {"type": "far_field"},
                        "transcription": {
                            "model": "whisper-1",
                            "language": self._config.language,
                        },
                        "turn_detection": self._config.turn_detection,
                    },
                    "output": {
                        "format": {"type": "audio/pcmu"},
                        "voice": self._config.voice,
                    },
                },
                "tools": tool_schemas,
                "tracing": "auto",
            }
        )

        if self._config.greeting:
            await self._connection.response.create()

        self._tasks.append(asyncio.create_task(self._receive_loop()))

    async def feed_audio(self, audio: bytes, timestamp: int) -> None:
        self._latest_media_ts = timestamp
        if self._connection:
            await self._connection.input_audio_buffer.append(
                audio=base64.b64encode(audio).decode(),
            )

    async def feed_dtmf(self, digits: str) -> None:
        """DTMF digit을 LLM 컨텍스트에 주입하고 응답을 트리거한다."""
        if self._connection:
            await self._connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": f"[DTMF 입력: {digits}]"}],
                }
            )
            await self._connection.response.create()

    async def _receive_loop(self) -> None:
        if not self._connection:
            return
        try:
            async for event in self._connection:
                await self._handle_event(event)
        except Exception as e:
            log.error(f"Realtime receive error: {e}")
        finally:
            await self._cleanup()

    async def _handle_event(self, event: Any) -> None:
        if not self._call:
            return
        event_type = event.type

        if event_type == "response.output_audio.delta":
            if self._response_start_ts is None:
                self._response_start_ts = self._latest_media_ts
                self._sent_audio_chunks = 0
                self._diag_delta_count = 0
                self._diag_last_delta_time = asyncio.get_event_loop().time()
            if event.item_id:
                self._last_assistant_item = event.item_id

            ulaw = base64.b64decode(event.delta)
            self._diag_delta_count = getattr(self, "_diag_delta_count", 0) + 1
            now = asyncio.get_event_loop().time()
            if self._diag_delta_count % 50 == 0:
                elapsed = now - getattr(self, "_diag_last_delta_time", now)
                log.info(
                    f"[OAI-DIAG] delta#{self._diag_delta_count} "
                    f"last50in={elapsed * 1000:.0f}ms "
                    f"avg={elapsed * 1000 / 50:.1f}ms/delta "
                    f"size={len(ulaw)}B "
                    f"totalChunks={self._sent_audio_chunks}"
                )
                self._diag_last_delta_time = now
            if self._recorder:
                self._recorder.write_outbound(ulaw_to_pcm16(ulaw))
            ulaw = self._audio_remainder + ulaw
            chunk_size = 160
            full_end = (len(ulaw) // chunk_size) * chunk_size
            for off in range(0, full_end, chunk_size):
                await self._call.send_audio(ulaw[off : off + chunk_size])
                self._sent_audio_chunks += 1
            self._audio_remainder = ulaw[full_end:]

        elif event_type == "response.output_audio.done":
            if self._audio_remainder:
                padded = self._audio_remainder + b"\xff" * (160 - len(self._audio_remainder))
                await self._call.send_audio(padded)
                self._sent_audio_chunks += 1
                self._audio_remainder = b""

        elif event_type == "input_audio_buffer.speech_started":
            await self._handle_truncation()

        elif event_type == "response.output_item.done":
            item = event.item
            if item and item.type == "function_call":
                task = asyncio.create_task(self._handle_tool_call(item))
                self._pending_tool_tasks.add(task)
                task.add_done_callback(self._pending_tool_tasks.discard)
            # 응답이 자연스럽게 끝난 경우 truncation 상태 초기화
            # — 이후 speech_started에서 이미 완료된 item을 truncate하지 않도록 방지
            if item and item.id == self._last_assistant_item:
                self._last_assistant_item = None
                self._response_start_ts = None
                self._sent_audio_chunks = 0
                self._audio_remainder = b""

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = event.transcript or ""
            log.debug(f"[Transcript] user: {transcript}")
            await self._call._emit("transcript", "user", transcript)

        elif event_type == "response.output_audio_transcript.done":
            transcript = event.transcript or ""
            log.debug(f"[Transcript] assistant: {transcript}")
            await self._call._emit("transcript", "assistant", transcript)

        elif event_type == "error":
            log.error(f"OpenAI error: {event.error}")

    async def _handle_tool_call(self, item: Any) -> None:
        func_name = item.name or ""
        call_id = item.call_id or ""
        args = json.loads(item.arguments or "{}")
        log.info(f"Tool call: {func_name}({args})")

        try:
            # Builtin tool 처리
            if func_name in BUILTIN_TOOL_NAMES and self._call:
                result = await execute_builtin_tool(func_name, args, self._call)
                if result == "":  # hang_up
                    return
                if result is not None and self._connection:
                    await self._connection.conversation.item.create(
                        item={
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": result,
                        }
                    )
                    await self._connection.response.create()
                return

            if not self._connection:
                return

            # Custom / MCP tool 처리
            source = "mcp" if func_name in self._tools._mcp_tools else "local"

            with tool_call_span(func_name, source):
                try:
                    result = await self._tools.call(func_name, args)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.error(f"Tool call failed: {func_name}: {e}")
                    result = f"Error: {e}"

            log.debug(f"Tool result: {func_name} -> {str(result)[:200]}")

            await self._connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": str(result),
                }
            )
            log.debug(f"Sent function_call_output for {func_name}, requesting response")
            await self._connection.response.create()

        except asyncio.CancelledError:
            log.info(f"Tool call cancelled (user interrupted): {func_name}")
            return

    async def _handle_truncation(self) -> None:
        # 진행 중인 tool call을 모두 취소 — 사용자가 인터럽트했으므로
        # 완료되지 않은 tool 결과를 서버에 보내면 컨텍스트가 꼬인다.
        for task in list(self._pending_tool_tasks):
            if not task.done():
                task.cancel()
        self._pending_tool_tasks.clear()

        if not self._last_assistant_item or self._response_start_ts is None:
            return

        audio_end_ms = max(0, self._sent_audio_chunks * 20)

        if self._connection:
            await self._connection.conversation.item.truncate(
                item_id=self._last_assistant_item,
                content_index=0,
                audio_end_ms=audio_end_ms,
            )

        if self._call:
            await self._call.clear_audio()

        self._last_assistant_item = None
        self._response_start_ts = None
        self._sent_audio_chunks = 0
        self._audio_remainder = b""

    async def stop(self) -> None:
        # 1) 연결 닫기 → receive loop의 async for가 자연 종료
        if self._connection:
            await self._connection.close()
            self._connection = None
        # 2) 남은 태스크 정리
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()
        for task in self._pending_tool_tasks:
            if not task.done():
                task.cancel()
        self._pending_tool_tasks.clear()
        # 3) LLM span 종료
        self._close_llm_span()

    async def _cleanup(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
        self._close_llm_span()

    def _close_llm_span(self) -> None:
        if self._llm_span_ctx:
            exc_info = sys.exc_info()
            self._llm_span_ctx.__exit__(*exc_info)
            self._llm_span_ctx = None
            self._llm_span = None
