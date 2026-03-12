"""Google Gemini Live API 세션 (google-genai SDK 기반).

Session Protocol을 구현하며, google-genai SDK의 Live API를 사용한다.
입력 오디오는 G.711 ulaw → PCM16 16kHz로, 출력은 PCM16 24kHz → G.711 ulaw로 변환한다.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

try:
    from google import genai
    from google.genai import types

    _HAS_GENAI = True
except ImportError:
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    _HAS_GENAI = False

from .._audio import ulaw_to_pcm16, pcm16_to_ulaw, resample_pcm16
from .._recorder import AudioRecorder
from .._session import CallSession
from .._tool import ToolRegistry
from ..tracing._spans import tool_call_span, llm_session_span

log = logging.getLogger("clawops.agent")

HANG_UP_TOOL = {
    "name": "hang_up",
    "description": "End the phone call. Use when the conversation is finished or the caller says goodbye.",
    "parameters": {"type": "object", "properties": {}},
}

COLLECT_DTMF_TOOL = {
    "name": "collect_dtmf",
    "description": "사용자로부터 DTMF(전화 키패드) 입력을 수집합니다. 반드시 사용자에게 무엇을 입력해야 하는지 안내한 후 호출하세요.",
    "parameters": {
        "type": "object",
        "properties": {
            "max_digits": {"type": "integer", "description": "수집할 최대 자릿수"},
            "finish_on_key": {"type": "string", "description": "입력 종료 키 (기본: #)"},
            "timeout": {"type": "integer", "description": "입력 대기 시간(초, 기본: 5)"},
        },
        "required": ["max_digits"],
    },
}

SEND_DTMF_TOOL = {
    "name": "send_dtmf",
    "description": "DTMF 신호를 전송합니다. ARS 메뉴 탐색이나 내선번호 입력 시 사용합니다.",
    "parameters": {
        "type": "object",
        "properties": {
            "digits": {
                "type": "string",
                "description": "전송할 번호 (0-9, *, #). 'w'는 500ms 대기, 'W'는 1000ms 대기.",
            },
        },
        "required": ["digits"],
    },
}


def _resolve_ref(ref: str, defs: dict[str, Any]) -> dict[str, Any]:
    """$ref 문자열을 $defs에서 찾아 반환한다."""
    parts = ref.lstrip("#/").split("/")
    result = defs
    for part in parts:
        if isinstance(result, dict):
            result = result.get(part, {})
        else:
            return {}
    return result if isinstance(result, dict) else {}


def _sanitize_schema_for_gemini(
    schema: dict[str, Any],
    defs: dict[str, Any] | None = None,
    _depth: int = 0,
) -> dict[str, Any]:
    """JSON Schema를 Gemini functionDeclarations 호환 형식으로 변환한다.

    - $ref를 인라인으로 resolve
    - oneOf/anyOf/allOf를 단순화 (첫 번째 object 타입 또는 첫 번째 항목 사용)
    - 지원되지 않는 키워드 제거
    - 재귀 깊이 제한으로 순환 참조 방지
    """
    if _depth > 15:
        return {"type": "object", "properties": {}}

    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    if defs is None:
        defs = schema.get("$defs", schema.get("definitions", {}))

    if "$ref" in schema:
        resolved = _resolve_ref(schema["$ref"], {"$defs": defs, "definitions": defs})
        if resolved:
            return _sanitize_schema_for_gemini(resolved, defs, _depth + 1)
        return {"type": "object", "properties": {}}

    for combo_key in ("oneOf", "anyOf", "allOf"):
        if combo_key in schema:
            variants = schema[combo_key]
            if isinstance(variants, list) and variants:
                for v in variants:
                    resolved_v = _sanitize_schema_for_gemini(v, defs, _depth + 1)
                    if resolved_v.get("type") == "object" and resolved_v.get("properties"):
                        return resolved_v
                return _sanitize_schema_for_gemini(variants[0], defs, _depth + 1)

    result: dict[str, Any] = {}

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        non_null = [t for t in schema_type if t != "null"]
        schema_type = non_null[0] if non_null else "string"

    if schema_type:
        result["type"] = schema_type

    if "description" in schema:
        result["description"] = schema["description"]

    if "enum" in schema:
        result["enum"] = schema["enum"]

    if "required" in schema:
        result["required"] = schema["required"]

    if "properties" in schema:
        props = {}
        for key, val in schema["properties"].items():
            if isinstance(val, dict):
                props[key] = _sanitize_schema_for_gemini(val, defs, _depth + 1)
        result["properties"] = props

    if "items" in schema:
        items = schema["items"]
        if isinstance(items, dict):
            result["items"] = _sanitize_schema_for_gemini(items, defs, _depth + 1)

    if "type" not in result and "properties" in result:
        result["type"] = "object"

    if result.get("type") == "object" and "properties" not in result:
        result["properties"] = {}

    return result


class GeminiRealtime:
    """Gemini Live API 기반 음성 세션 (google-genai SDK).

    Session Protocol을 구현한다.
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
        if not _HAS_GENAI:
            raise ImportError(
                "google-genai is required for GeminiRealtime. Install it with: pip install clawops[gemini-llm]"
            )
        if api_key is None:
            api_key = os.environ.get("GOOGLE_API_KEY", "")
        self._api_key = api_key
        self._system_prompt = system_prompt
        self._model = model
        self._voice = voice
        self._language = language
        self._greeting = greeting
        self._tools = tool_registry or ToolRegistry()
        self._dtmf_tools: bool = True
        self._recorder = recorder

        self._client = genai.Client(api_key=api_key)
        self._live_ctx: Any | None = None  # async context manager
        self._session: Any | None = None  # AsyncLiveSession
        self._call: CallSession | None = None
        self._sent_audio_chunks: int = 0
        self._tasks: list[asyncio.Task[Any]] = []
        self._llm_span_ctx: Any | None = None
        self._llm_span: Any | None = None
        self._audio_remainder: bytes = b""  # 160B 미만 잔여 ulaw 버퍼
        self._tool_call_in_progress: bool = False

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

        self._llm_span_ctx = llm_session_span(self._model, system="google", voice=self._voice)
        self._llm_span = self._llm_span_ctx.__enter__()

        # ── Config ──
        tool_schemas = self._build_tool_schemas()

        config: dict[str, Any] = {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": self._voice},
                },
            },
            "input_audio_transcription": {},
            "output_audio_transcription": {},
        }

        if self._system_prompt:
            config["system_instruction"] = self._system_prompt

        if tool_schemas:
            config["tools"] = [{"function_declarations": tool_schemas}]

        log.debug(f"Gemini SDK config: model={self._model}, voice={self._voice}")
        log.debug(f"Gemini SDK tool count: {len(tool_schemas)}")

        # SDK가 setup 메시지를 자동으로 처리
        self._live_ctx = self._client.aio.live.connect(
            model=self._model,
            config=config,
        )
        try:
            self._session = await self._live_ctx.__aenter__()
        except Exception:
            if self._llm_span_ctx:
                import sys

                self._llm_span_ctx.__exit__(*sys.exc_info())
                self._llm_span_ctx = None
            raise
        log.info("Gemini Live SDK session connected")

        if self._greeting:
            await self._session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text="인사해 주세요.")],
                ),
                turn_complete=True,
            )

        self._tasks.append(asyncio.create_task(self._receive_loop()))

    async def feed_audio(self, audio: bytes, timestamp: int) -> None:
        if not self._session or self._tool_call_in_progress:
            return

        # G.711 ulaw 8kHz → PCM16 8kHz → PCM16 16kHz
        pcm8k = ulaw_to_pcm16(audio)
        pcm16k = resample_pcm16(pcm8k, from_rate=8000, to_rate=16000)

        if self._recorder:
            self._recorder.write_inbound(pcm8k)

        self._sent_audio_chunks += 1

        try:
            await self._session.send_realtime_input(
                audio=types.Blob(data=pcm16k, mime_type="audio/pcm;rate=16000"),
            )
        except Exception as e:
            log.warning(f"Gemini audio send failed: {e}")

    async def feed_dtmf(self, digits: str) -> None:
        """DTMF digit을 LLM 컨텍스트에 주입하고 응답을 트리거한다."""
        if self._session:
            from google.genai import types

            await self._session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=f"[DTMF 입력: {digits}]")],
                ),
                turn_complete=True,
            )

    async def _receive_loop(self) -> None:
        if not self._session:
            return
        try:
            # SDK의 receive()는 turn_complete 시 iterator가 종료되므로
            # 매 턴마다 다시 호출해야 한다.
            while self._session:
                async for response in self._session.receive():
                    await self._handle_response(response)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Gemini receive error: {e}")
        finally:
            await self._cleanup()

    async def _handle_response(self, response: Any) -> None:
        if not self._call:
            return

        server_content = getattr(response, "server_content", None)
        if server_content:
            # ── 오디오 응답 ──
            model_turn = getattr(server_content, "model_turn", None)
            if model_turn:
                for part in getattr(model_turn, "parts", []):
                    inline = getattr(part, "inline_data", None)
                    if inline and "audio" in (getattr(inline, "mime_type", "") or ""):
                        await self._handle_audio_data(inline.data)

            # 턴 완료
            if getattr(server_content, "turn_complete", False):
                log.debug("Gemini turn complete")
                await self._flush_audio_remainder()

            # barge-in (인터럽트)
            if getattr(server_content, "interrupted", False):
                log.info("Gemini: barge-in detected")
                await self._call.clear_audio()
                self._sent_audio_chunks = 0
                self._audio_remainder = b""

            # ── 입력 트랜스크립트 ──
            input_transcription = getattr(server_content, "input_transcription", None)
            if input_transcription:
                text = getattr(input_transcription, "text", "")
                if text:
                    log.info(f"[TRANSCRIPT-USER] {text}")
                    await self._call._emit("transcript", "user", text)

            # ── 출력 트랜스크립트 ──
            output_transcription = getattr(server_content, "output_transcription", None)
            if output_transcription:
                text = getattr(output_transcription, "text", "")
                if text:
                    log.info(f"[TRANSCRIPT-ASSISTANT] {text}")
                    await self._call._emit("transcript", "assistant", text)

        # ── Tool call ──
        tool_call = getattr(response, "tool_call", None)
        if tool_call:
            await self._handle_tool_calls(tool_call)

        # ── Tool call cancellation ──
        tool_cancellation = getattr(response, "tool_call_cancellation", None)
        if tool_cancellation:
            ids = getattr(tool_cancellation, "ids", [])
            log.info(f"Gemini tool call cancelled: {ids}")

    async def _handle_audio_data(self, audio_data: bytes) -> None:
        """PCM16 24kHz raw bytes → G.711 ulaw 8kHz 변환 후 전송."""
        if not self._call:
            return

        pcm24k = audio_data
        if self._recorder:
            self._recorder.write_outbound(resample_pcm16(pcm24k, from_rate=24000, to_rate=8000))

        # PCM16 24kHz → PCM16 8kHz → ulaw
        pcm8k = resample_pcm16(pcm24k, from_rate=24000, to_rate=8000)
        ulaw = pcm16_to_ulaw(pcm8k)

        # 160B 프레임 정렬
        ulaw = self._audio_remainder + ulaw
        chunk_size = 160
        full_end = (len(ulaw) // chunk_size) * chunk_size
        for off in range(0, full_end, chunk_size):
            await self._call.send_audio(ulaw[off : off + chunk_size])
        self._audio_remainder = ulaw[full_end:]

    async def _flush_audio_remainder(self) -> None:
        """잔여 오디오를 silence 패딩하여 flush."""
        if self._audio_remainder and self._call:
            padded = self._audio_remainder + b"\xff" * (160 - len(self._audio_remainder))
            await self._call.send_audio(padded)
            self._audio_remainder = b""

    async def _handle_tool_calls(self, tool_call: Any) -> None:
        # 도구 호출 중에는 오디오 입력 중단 (Gemini가 tool call 상태에서 audio input 수신 시 1008 에러)
        self._tool_call_in_progress = True
        function_calls = getattr(tool_call, "function_calls", [])
        responses: list[types.FunctionResponse] = []

        for fc in function_calls:
            func_name = getattr(fc, "name", "")
            fc_id = getattr(fc, "id", "")
            args = getattr(fc, "args", {})
            log.info(f"Tool call: {func_name}({args})")

            if func_name == "hang_up":
                if self._call:
                    await self._call.hangup()
                return

            elif func_name == "collect_dtmf":
                if self._call:
                    try:
                        result = await self._call.collect_dtmf(
                            max_digits=args.get("max_digits", 4),
                            finish_on_key=args.get("finish_on_key", "#"),
                            timeout=args.get("timeout", 5),
                        )
                        dtmf_output = result if result else "(타임아웃 - 입력 없음)"
                    except Exception as e:
                        dtmf_output = f"Error: {e}"
                    responses.append(
                        types.FunctionResponse(
                            id=fc_id,
                            name=func_name,
                            response={"result": dtmf_output},
                        )
                    )
                continue

            elif func_name == "send_dtmf":
                if self._call:
                    try:
                        await self._call.send_dtmf_sequence(args.get("digits", ""))
                        dtmf_output = "sent"
                    except Exception as e:
                        dtmf_output = f"Error: {e}"
                    responses.append(
                        types.FunctionResponse(
                            id=fc_id,
                            name=func_name,
                            response={"result": dtmf_output},
                        )
                    )
                continue

            source = "mcp" if func_name in self._tools._mcp_tools else "local"
            with tool_call_span(func_name, source):
                try:
                    result = await self._tools.call(func_name, args)
                except Exception as e:
                    log.error(f"Tool call failed: {func_name}: {e}")
                    result = f"Error: {e}"

            responses.append(
                types.FunctionResponse(
                    id=fc_id,
                    name=func_name,
                    response={"result": str(result)},
                )
            )

        if responses:
            await self._session.send_tool_response(
                function_responses=responses,
            )
        self._tool_call_in_progress = False

    def _build_tool_schemas(self) -> list[dict[str, Any]]:
        """ToolRegistry의 스키마를 Gemini functionDeclarations 형식으로 변환."""
        openai_tools = self._tools.to_openai_tools()
        declarations = []
        for tool in openai_tools:
            params = tool.get("parameters", {"type": "object", "properties": {}})
            params = _sanitize_schema_for_gemini(params)
            declarations.append(
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": params,
                }
            )
        declarations.append(HANG_UP_TOOL)
        if self._dtmf_tools:
            declarations.append(COLLECT_DTMF_TOOL)
            declarations.append(SEND_DTMF_TOOL)
        return declarations

    async def stop(self) -> None:
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()
        await self._cleanup()

    async def _cleanup(self) -> None:
        if self._live_ctx:
            try:
                await self._live_ctx.__aexit__(None, None, None)
            except Exception as e:
                log.debug(f"Gemini SDK cleanup: {e}")
            self._live_ctx = None
            self._session = None
        if self._llm_span_ctx:
            import sys

            exc_info = sys.exc_info()
            self._llm_span_ctx.__exit__(*exc_info)
            self._llm_span_ctx = None
            self._llm_span = None
