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
from ._base import STT, LLM, TTS

log = logging.getLogger("clawops.agent.pipeline")

_SENTENCE_END = re.compile(r'[.!?。！？]\s*$')


class PipelineSession:
    def __init__(
        self,
        *,
        stt: STT,
        llm: LLM,
        tts: TTS,
        system_prompt: str,
        tool_registry: ToolRegistry,
        greeting: bool = True,
        language: str = "ko",
        recorder: AudioRecorder | None = None,
    ) -> None:
        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._system_prompt = system_prompt
        self._tools = tool_registry
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

    async def stop(self) -> None:
        self._running = False
        await self._audio_queue.put(None)
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

    async def _stt_loop(self) -> None:
        try:
            async for transcript in self._stt.transcribe(self._audio_stream()):
                if not transcript.strip():
                    continue
                log.info(f"STT: {transcript}")
                if self._call:
                    await self._call._emit("transcript", "user", transcript)
                await self._interrupt()
                self._messages.append({"role": "user", "content": transcript})
                self._current_response_task = asyncio.create_task(self._respond())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"STT loop error: {e}")

    async def _generate_greeting(self) -> None:
        await asyncio.sleep(0.5)
        self._current_response_task = asyncio.create_task(self._respond())

    async def _respond(self) -> None:
        if not self._call:
            return
        try:
            tool_schemas = self._tools.to_openai_tools()
            tool_schemas.append({
                "type": "function",
                "function": {
                    "name": "hang_up",
                    "description": "End the phone call.",
                    "parameters": {"type": "object", "properties": {}},
                },
            })

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
                        yield buffer
                        buffer = ""
                if buffer.strip():
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
                    break
                if self._recorder:
                    self._recorder.write_raw_outbound(audio)
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
