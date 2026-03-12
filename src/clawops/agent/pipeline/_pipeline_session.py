"""PipelineSession: STT -> LLM -> TTS 파이프라인 오케스트레이터."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator

from .._audio import ulaw_to_pcm16, pcm16_to_ulaw, resample_pcm16
from .._recorder import AudioRecorder
from .._session import CallSession
from .._tool import ToolRegistry
from ._base import STT, LLM, TTS, SpeechEvent

log = logging.getLogger("clawops.agent.pipeline")

_SENTENCE_END = re.compile(r'[.!?。！？]\s*$')

HANG_UP_TOOL = {
    "type": "function",
    "function": {
        "name": "hang_up",
        "description": "End the phone call.",
        "parameters": {"type": "object", "properties": {}},
    },
}

COLLECT_DTMF_TOOL = {
    "type": "function",
    "function": {
        "name": "collect_dtmf",
        "description": "사용자로부터 DTMF(전화 키패드) 입력을 수집합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "max_digits": {"type": "integer", "description": "수집할 최대 자릿수"},
                "finish_on_key": {"type": "string", "description": "입력 종료 키 (기본: #)"},
                "timeout": {"type": "integer", "description": "입력 대기 시간(초, 기본: 5)"},
            },
            "required": ["max_digits"],
        },
    },
}

SEND_DTMF_TOOL = {
    "type": "function",
    "function": {
        "name": "send_dtmf",
        "description": "DTMF 신호를 전송합니다. ARS 메뉴 탐색이나 내선번호 입력 시 사용합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "digits": {"type": "string", "description": "전송할 번호 (0-9, *, #). 'w'는 500ms 대기, 'W'는 1000ms 대기."},
            },
            "required": ["digits"],
        },
    },
}


def _to_chat_tools(realtime_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Realtime API 포맷 tool 스키마를 Chat Completions 포맷으로 변환.

    Realtime: {"type": "function", "name": ..., "description": ..., "parameters": ...}
    Chat:     {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    """
    result = []
    for tool in realtime_tools:
        if "function" in tool and isinstance(tool["function"], dict):
            result.append(tool)
        else:
            result.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            })
    return result


class PipelineSession:
    def __init__(
        self,
        *,
        stt: STT,
        llm: LLM,
        tts: TTS,
        system_prompt: str = "",
        greeting: bool = True,
        language: str = "ko",
        tool_registry: ToolRegistry | None = None,
        recorder: AudioRecorder | None = None,
    ) -> None:
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._system_prompt = system_prompt
        self._tools = tool_registry or ToolRegistry()
        self._dtmf_tools: bool = True
        self._greeting = greeting
        self._language = language
        self._recorder = recorder

        self._call: CallSession | None = None
        self._messages: list[dict[str, Any]] = []
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._running = False
        self._tasks: list[asyncio.Task[Any]] = []
        self._current_response_task: asyncio.Task[Any] | None = None
        self._sent_audio_chunks = 0
        self._pending_respond_task: asyncio.Task[Any] | None = None

    def set_tool_registry(self, registry: ToolRegistry) -> None:
        """콜별로 fork된 ToolRegistry를 주입한다."""
        self._tools = registry

    def set_dtmf_tools(self, enabled: bool) -> None:
        """DTMF tool 등록 여부를 설정한다."""
        self._dtmf_tools = enabled

    def set_recorder(self, recorder: AudioRecorder) -> None:
        """콜별로 생성된 AudioRecorder를 주입한다."""
        self._recorder = recorder

    async def start(self, call: CallSession) -> None:
        self._call = call
        self._running = True
        self._messages = [{"role": "system", "content": self._system_prompt}]
        self._tasks.append(asyncio.create_task(self._stt_loop()))
        if self._greeting:
            self._tasks.append(asyncio.create_task(self._generate_greeting()))
        log.info("PipelineSession started")

    async def feed_audio(self, ulaw: bytes, timestamp: int) -> None:
        if not self._running:
            return
        await self._audio_queue.put(ulaw)

    async def feed_dtmf(self, digits: str) -> None:
        """DTMF digit을 LLM 컨텍스트에 주입하고 응답을 트리거한다."""
        self._messages.append({
            "role": "user",
            "content": f"[DTMF 입력: {digits}]",
        })
        await self._respond()

    async def stop(self) -> None:
        self._running = False
        await self._audio_queue.put(None)
        if self._pending_respond_task and not self._pending_respond_task.done():
            self._pending_respond_task.cancel()
        if self._current_response_task and not self._current_response_task.done():
            self._current_response_task.cancel()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()
        log.info("PipelineSession stopped")

    async def _audio_stream(self) -> AsyncIterator[bytes]:
        while self._running:
            chunk = await self._audio_queue.get()
            if chunk is None:
                break
            pcm8k = ulaw_to_pcm16(chunk)
            pcm16k = resample_pcm16(pcm8k, from_rate=8000, to_rate=16000)
            yield pcm16k

    # ── STT 이벤트 처리 ──────────────────────────────────────

    async def _stt_loop(self) -> None:
        try:
            async for event in self._stt.transcribe(self._audio_stream()):
                if event.type == "interim":
                    await self._handle_interim_speech(event)
                elif event.type == "final":
                    await self._handle_final_transcript(event)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"STT loop error: {e}")

    async def _handle_interim_speech(self, event: SpeechEvent) -> None:
        """사용자 발화 감지 (interim) → AI 오디오가 재생 중이면 즉시 중단."""
        if self._sent_audio_chunks > 0:
            log.info(f"Barge-in: \"{event.transcript[:30]}\" — clearing AI audio")
            # 응답 생성 중이면 취소
            if self._current_response_task and not self._current_response_task.done():
                self._current_response_task.cancel()
                try:
                    await self._current_response_task
                except asyncio.CancelledError:
                    pass
            # Twilio 버퍼에 남아있는 오디오 클리어
            if self._call:
                await self._call.clear_audio()
            self._sent_audio_chunks = 0

    async def _handle_final_transcript(self, event: SpeechEvent) -> None:
        """발화 완료 (final) → 메시지 추가 후 응답 생성."""
        transcript = event.transcript
        if not transcript.strip():
            return
        log.info(f"STT: {transcript}")
        if self._call:
            await self._call._emit("transcript", "user", transcript)

        self._messages.append({"role": "user", "content": transcript})

        if self._sent_audio_chunks > 0:
            # AI가 아직 말하고 있었다면 인터럽트 (interim에서 이미 중단했을 수도 있음)
            await self._interrupt()
            self._current_response_task = asyncio.create_task(self._respond())
        else:
            # AI가 아직 말하기 전 → 현재 응답 취소하고 debounce
            if self._current_response_task and not self._current_response_task.done():
                self._current_response_task.cancel()
                try:
                    await self._current_response_task
                except asyncio.CancelledError:
                    pass
                log.info("Response cancelled (no audio sent yet)")
            if self._pending_respond_task and not self._pending_respond_task.done():
                self._pending_respond_task.cancel()
            self._pending_respond_task = asyncio.create_task(
                self._debounced_respond(0.5)
            )

    # ── 응답 생성 ────────────────────────────────────────────

    async def _debounced_respond(self, delay: float) -> None:
        """delay 동안 추가 입력을 기다린 후 응답 시작."""
        await asyncio.sleep(delay)
        log.info("Debounce expired, starting response")
        self._current_response_task = asyncio.create_task(self._respond())

    async def _generate_greeting(self) -> None:
        await asyncio.sleep(0.5)
        self._current_response_task = asyncio.create_task(self._respond())

    async def _respond(self) -> None:
        if not self._call:
            return
        try:
            tool_schemas = _to_chat_tools(self._tools.to_openai_tools())
            tool_schemas.append(HANG_UP_TOOL)
            if self._dtmf_tools:
                tool_schemas += [COLLECT_DTMF_TOOL, SEND_DTMF_TOOL]

            async def text_stream() -> AsyncIterator[str]:
                buffer = ""
                async for token in self._llm.generate(self._messages, tools=tool_schemas):
                    if token.startswith('{"type":"tool_calls"') or token.startswith('{"type": "tool_calls"'):
                        if buffer.strip():
                            yield buffer
                            buffer = ""
                        await self._handle_tool_calls(json.loads(token))
                        return
                    buffer += token
                    if _SENTENCE_END.search(buffer):
                        log.info(f"LLM sentence: {buffer[:80]}")
                        yield buffer
                        buffer = ""
                if buffer.strip():
                    log.info(f"LLM final: {buffer[:80]}")
                    yield buffer

            text_chunks: list[str] = []

            async def tee_text() -> AsyncIterator[str]:
                async for chunk in text_stream():
                    text_chunks.append(chunk)
                    yield chunk

            tts_sample_rate = getattr(self._tts, "sample_rate", 24000)
            self._sent_audio_chunks = 0

            async for audio in self._tts.synthesize(tee_text()):
                if not self._running or not self._call:
                    log.warning("TTS audio received but session stopped")
                    break
                if self._recorder:
                    pcm16_8k = resample_pcm16(audio, from_rate=tts_sample_rate, to_rate=8000) if tts_sample_rate != 8000 else audio
                    self._recorder.write_outbound(pcm16_8k)
                pcm8k = resample_pcm16(audio, from_rate=tts_sample_rate, to_rate=8000)
                ulaw = pcm16_to_ulaw(pcm8k)
                for off in range(0, len(ulaw), 160):
                    chunk = ulaw[off:off + 160]
                    if len(chunk) < 160:
                        chunk = chunk + b'\xff' * (160 - len(chunk))
                    await self._call.send_audio(chunk)
                    self._sent_audio_chunks += 1

            assistant_text = "".join(text_chunks)
            if assistant_text.strip():
                log.info(f"Assistant: {assistant_text[:100]}")
                self._messages.append({"role": "assistant", "content": assistant_text})
                if self._call:
                    await self._call._emit("transcript", "assistant", assistant_text)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Response error: {e}")

    async def _handle_tool_calls(self, data: dict[str, Any]) -> None:
        tool_calls = data.get("tool_calls", [])
        self._messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            func_name = tc["function"]["name"]
            call_id = tc["id"]
            if func_name == "hang_up":
                if self._call:
                    await self._call.hangup()
                return
            elif func_name == "collect_dtmf":
                if self._call:
                    try:
                        args = json.loads(tc["function"]["arguments"])
                        result = await self._call.collect_dtmf(
                            max_digits=args.get("max_digits", 4),
                            finish_on_key=args.get("finish_on_key", "#"),
                            timeout=args.get("timeout", 5),
                        )
                        self._messages.append({
                            "role": "tool", "tool_call_id": call_id,
                            "content": result if result else "(타임아웃 - 입력 없음)",
                        })
                    except Exception as e:
                        self._messages.append({
                            "role": "tool", "tool_call_id": call_id,
                            "content": f"Error: {e}",
                        })
                continue
            elif func_name == "send_dtmf":
                if self._call:
                    try:
                        args = json.loads(tc["function"]["arguments"])
                        await self._call.send_dtmf_sequence(args.get("digits", ""))
                        self._messages.append({
                            "role": "tool", "tool_call_id": call_id,
                            "content": "sent",
                        })
                    except Exception as e:
                        self._messages.append({
                            "role": "tool", "tool_call_id": call_id,
                            "content": f"Error: {e}",
                        })
                continue
            try:
                args = json.loads(tc["function"]["arguments"])
                result = await self._tools.call(func_name, args)
            except Exception as e:
                log.error(f"Tool call failed: {func_name}: {e}")
                result = f"Error: {e}"
            self._messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": str(result),
            })

        await self._respond()

    async def _interrupt(self) -> None:
        if self._current_response_task and not self._current_response_task.done():
            self._current_response_task.cancel()
            try:
                await self._current_response_task
            except asyncio.CancelledError:
                pass
            if self._call:
                await self._call.clear_audio()
            self._sent_audio_chunks = 0
            log.info("Response interrupted")
