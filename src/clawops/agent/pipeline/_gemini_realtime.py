"""Google Gemini Live API 세션.

Session Protocol을 구현하며, Gemini Live WebSocket API를 사용한다.
입력 오디오는 G.711 ulaw → PCM16 16kHz로, 출력은 PCM16 24kHz → G.711 ulaw로 변환한다.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any

import aiohttp

from .._audio import ulaw_to_pcm16, pcm16_to_ulaw, resample_pcm16
from .._recorder import AudioRecorder
from .._session import CallSession
from .._tool import ToolRegistry
from ..tracing._spans import tool_call_span, llm_session_span

log = logging.getLogger("clawops.agent")

GEMINI_LIVE_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    "?key={api_key}"
)

HANG_UP_TOOL = {
    "name": "hang_up",
    "description": "End the phone call. Use when the conversation is finished or the caller says goodbye.",
    "parameters": {"type": "object", "properties": {}},
}


class GeminiRealtime:
    """Gemini Live API 기반 음성 세션.

    Session Protocol을 구현한다. ``gemini-2.0-flash-live-001`` 등
    Google의 realtime 모델을 사용한다.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        system_prompt: str = "",
        model: str = "gemini-2.5-flash-native-audio-preview-12-2025",
        voice: str = "Kore",
        language: str = "ko",
        greeting: bool = True,
        tool_registry: ToolRegistry | None = None,
        recorder: AudioRecorder | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("GOOGLE_API_KEY", "")
        self._api_key = api_key
        self._system_prompt = system_prompt
        self._model = model
        self._voice = voice
        self._language = language
        self._greeting = greeting
        self._tools = tool_registry or ToolRegistry()
        self._recorder = recorder

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._http: aiohttp.ClientSession | None = None
        self._call: CallSession | None = None
        self._sent_audio_chunks: int = 0
        self._tasks: list[asyncio.Task[Any]] = []
        self._llm_span_ctx: Any | None = None
        self._llm_span: Any | None = None
        self._audio_remainder: bytes = b""  # 160B 미만 잔여 ulaw 버퍼

    def set_tool_registry(self, registry: ToolRegistry) -> None:
        """콜별로 fork된 ToolRegistry를 주입한다."""
        self._tools = registry

    def set_recorder(self, recorder: AudioRecorder) -> None:
        """콜별로 생성된 AudioRecorder를 주입한다."""
        self._recorder = recorder

    async def start(self, call: CallSession) -> None:
        self._call = call

        self._llm_span_ctx = llm_session_span(
            self._model, system="google", voice=self._voice
        )
        self._llm_span = self._llm_span_ctx.__enter__()

        url = GEMINI_LIVE_URL.format(api_key=self._api_key)

        self._http = aiohttp.ClientSession()
        self._ws = await self._http.ws_connect(url)
        log.info("Gemini Live WS connected")

        # ── Setup 메시지 ──
        tool_schemas = self._build_tool_schemas()

        setup_msg: dict[str, Any] = {
            "setup": {
                "model": f"models/{self._model}",
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": self._voice},
                        },
                    },
                },
                "realtimeInputConfig": {
                    "automaticActivityDetection": {
                        "disabled": False,
                    },
                },
            },
        }

        if self._system_prompt:
            setup_msg["setup"]["systemInstruction"] = {
                "parts": [{"text": self._system_prompt}],
            }

        if tool_schemas:
            setup_msg["setup"]["tools"] = [{"functionDeclarations": tool_schemas}]

        log.debug(f"Gemini setup: model={self._model}, voice={self._voice}")
        await self._send(setup_msg)

        # setupComplete 대기
        await self._wait_setup_complete()

        if self._greeting:
            await self._send({
                "clientContent": {
                    "turns": [
                        {
                            "role": "user",
                            "parts": [{"text": "인사해 주세요."}],
                        }
                    ],
                    "turnComplete": True,
                }
            })

        self._tasks.append(asyncio.create_task(self._receive_loop()))

    async def feed_audio(self, audio: bytes, timestamp: int) -> None:
        # G.711 ulaw 8kHz → PCM16 8kHz → PCM16 16kHz
        pcm8k = ulaw_to_pcm16(audio)
        pcm16k = resample_pcm16(pcm8k, from_rate=8000, to_rate=16000)

        await self._send({
            "realtimeInput": {
                "mediaChunks": [{
                    "mimeType": "audio/pcm;rate=16000",
                    "data": base64.b64encode(pcm16k).decode(),
                }],
            },
        })

    @staticmethod
    def _parse_ws_message(msg: aiohttp.WSMessage) -> dict[str, Any] | None:
        """TEXT 또는 BINARY WS 메시지를 JSON dict로 파싱한다."""
        if msg.type == aiohttp.WSMsgType.TEXT:
            return json.loads(msg.data)
        if msg.type == aiohttp.WSMsgType.BINARY:
            try:
                return json.loads(msg.data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
        return None

    async def _wait_setup_complete(self) -> None:
        """서버로부터 setupComplete 메시지를 대기한다."""
        if not self._ws:
            return
        async for msg in self._ws:
            data = self._parse_ws_message(msg)
            if data is not None:
                log.debug(f"Gemini setup recv: {list(data.keys())}")
                if "setupComplete" in data:
                    log.info("Gemini Live setup complete")
                    return
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                log.error(f"Gemini WS closed during setup: {msg.type}")
                raise ConnectionError("Gemini Live WS closed during setup")

    async def _receive_loop(self) -> None:
        if not self._ws:
            return
        try:
            async for msg in self._ws:
                event = self._parse_ws_message(msg)
                if event is not None:
                    log.debug(f"Gemini recv: {list(event.keys())}")
                    await self._handle_event(event)
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    log.warning(f"Gemini WS closed: {msg.type}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Gemini receive error: {e}")
        finally:
            await self._cleanup()

    async def _handle_event(self, event: dict[str, Any]) -> None:
        if not self._call:
            return

        # ── 오디오 응답 ──
        server_content = event.get("serverContent")
        if server_content:
            model_turn = server_content.get("modelTurn")
            if model_turn:
                for part in model_turn.get("parts", []):
                    inline = part.get("inlineData")
                    if inline and "audio" in inline.get("mimeType", ""):
                        await self._handle_audio_data(inline["data"])

                    # 텍스트 트랜스크립트
                    text = part.get("text")
                    if text:
                        await self._call._emit("transcript", "assistant", text)

            # 턴 완료
            if server_content.get("turnComplete"):
                log.debug("Gemini turn complete")
                await self._flush_audio_remainder()

            # barge-in (인터럽트)
            if server_content.get("interrupted"):
                log.info("Gemini: barge-in detected")
                if self._call:
                    await self._call.clear_audio()
                self._sent_audio_chunks = 0
                self._audio_remainder = b""

        # ── 입력 트랜스크립트 (서버 최상위 필드) ──
        input_transcription = event.get("inputTranscription")
        if input_transcription:
            text = input_transcription.get("text", "")
            if text:
                await self._call._emit("transcript", "user", text)

        # ── 출력 트랜스크립트 (서버 최상위 필드) ──
        output_transcription = event.get("outputTranscription")
        if output_transcription:
            text = output_transcription.get("text", "")
            if text:
                await self._call._emit("transcript", "assistant", text)

        # ── Tool call ──
        tool_call = event.get("toolCall")
        if tool_call:
            await self._handle_tool_calls(tool_call)

        # ── Tool call cancellation (barge-in 시) ──
        tool_cancellation = event.get("toolCallCancellation")
        if tool_cancellation:
            log.info(f"Gemini tool call cancelled: {tool_cancellation.get('ids', [])}")

    async def _handle_audio_data(self, b64_data: str) -> None:
        """PCM16 24kHz → G.711 ulaw 8kHz 변환 후 전송."""
        if not self._call:
            return

        pcm24k = base64.b64decode(b64_data)
        if self._recorder:
            self._recorder.write_raw_outbound(pcm24k)

        # PCM16 24kHz → PCM16 8kHz → ulaw
        pcm8k = resample_pcm16(pcm24k, from_rate=24000, to_rate=8000)
        ulaw = pcm16_to_ulaw(pcm8k)

        # 160B 프레임 정렬
        ulaw = self._audio_remainder + ulaw
        chunk_size = 160
        full_end = (len(ulaw) // chunk_size) * chunk_size
        for off in range(0, full_end, chunk_size):
            await self._call.send_audio(ulaw[off : off + chunk_size])
            self._sent_audio_chunks += 1
        self._audio_remainder = ulaw[full_end:]

    async def _flush_audio_remainder(self) -> None:
        """잔여 오디오를 silence 패딩하여 flush."""
        if self._audio_remainder and self._call:
            padded = self._audio_remainder + b'\xff' * (160 - len(self._audio_remainder))
            await self._call.send_audio(padded)
            self._sent_audio_chunks += 1
            self._audio_remainder = b""

    async def _handle_tool_calls(self, tool_call: dict[str, Any]) -> None:
        function_calls = tool_call.get("functionCalls", [])
        responses: list[dict[str, Any]] = []

        for fc in function_calls:
            func_name = fc.get("name", "")
            fc_id = fc.get("id", "")
            args = fc.get("args", {})
            log.info(f"Tool call: {func_name}({args})")

            if func_name == "hang_up":
                if self._call:
                    await self._call.hangup()
                return

            source = "mcp" if func_name in self._tools._mcp_tools else "local"
            with tool_call_span(func_name, source):
                try:
                    result = await self._tools.call(func_name, args)
                except Exception as e:
                    log.error(f"Tool call failed: {func_name}: {e}")
                    result = f"Error: {e}"

            responses.append({
                "id": fc_id,
                "name": func_name,
                "response": {"result": str(result)},
            })

        if responses:
            await self._send({
                "toolResponse": {"functionResponses": responses},
            })

    def _build_tool_schemas(self) -> list[dict[str, Any]]:
        """ToolRegistry의 스키마를 Gemini functionDeclarations 형식으로 변환."""
        openai_tools = self._tools.to_openai_tools()
        declarations = []
        for tool in openai_tools:
            declarations.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
            })
        declarations.append(HANG_UP_TOOL)
        return declarations

    async def _send(self, data: dict[str, Any]) -> None:
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_str(json.dumps(data))
            except Exception as e:
                log.error(f"Gemini WS send failed: {e}")

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
        if self._llm_span_ctx:
            import sys
            exc_info = sys.exc_info()
            self._llm_span_ctx.__exit__(*exc_info)
            self._llm_span_ctx = None
            self._llm_span = None
