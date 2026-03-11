# Gemini Realtime SDK Refactor Design

## Problem

`GeminiRealtime` 클래스가 raw WebSocket으로 Gemini Live API와 통신하지만, 프로토콜 호환성 문제로 음성 인식이 작동하지 않는다.

- `mediaChunks` 포맷: AUDIO 토큰 0개 (음성 미인식)
- `audio` 포맷: AUDIO 토큰 4~11개 (극히 부분적 인식)
- VAD 세부 설정 / contextWindowCompression: v1beta 엔드포인트에서 거부
- transcription 이벤트: 설정해도 수신되지 않음

동일한 system prompt와 오디오로 OpenAI Realtime은 정상 작동한다.

## Solution

`google-genai` SDK (최신 버전)의 `client.aio.live.connect()`를 사용하여 `_gemini_realtime.py`를 재작성한다. SDK가 WebSocket 프로토콜, setup 메시지 직렬화, 오디오 포맷을 처리하므로, 우리는 오디오 변환과 이벤트 핸들링에만 집중한다.

## Architecture

```
Phone (G.711 ulaw 8kHz)
  | feed_audio()
  v
ulaw_to_pcm16() -> resample_pcm16(8k -> 16k)
  |
  v
SDK session.send_realtime_input(audio=Blob(pcm16k))
  |
  v
Gemini Live API (WebSocket - SDK managed)
  |
  v
SDK session.receive() -> response objects
  |
  v
response.server_content.model_turn.parts[].inline_data.data (PCM24k bytes)
  |
  v
resample_pcm16(24k -> 8k) -> pcm16_to_ulaw()
  |
  v
call.send_audio(ulaw 160B frames)
```

## Scope

- 수정 파일: `src/clawops/agent/pipeline/_gemini_realtime.py` (재작성)
- 수정 파일: `tests/agent/test_gemini_realtime.py` (SDK mock 기반으로 업데이트)
- 기존 파일 유지: `_audio.py`, `_base.py`, `_session.py`, `_agent.py`

## Config Strategy

Stage 1+2만 포함. Stage 3(VAD 세부 튜닝, compression)은 제외한다.

**포함 (Stage 1 - 필수):**
```python
config = {
    "response_modalities": ["AUDIO"],
    "speech_config": {
        "voice_config": {
            "prebuilt_voice_config": {"voice_name": self._voice},
        },
    },
}

# 조건부
if self._system_prompt:
    config["system_instruction"] = self._system_prompt
if tool_schemas:
    config["tools"] = [{"function_declarations": tool_schemas}]
```

**포함 (Stage 2 - transcription):**
```python
config["input_audio_transcription"] = {}
config["output_audio_transcription"] = {}
```

**제외 (Stage 3):**
- `realtime_input_config.automatic_activity_detection` 세부 파라미터
- `context_window_compression`

## Event Handling

SDK `session.receive()`에서 yield되는 response 객체 처리:

| 이벤트 | 처리 |
|--------|------|
| `server_content.model_turn.parts[].inline_data` | PCM24k raw bytes -> ulaw 변환 후 `call.send_audio()` |
| `server_content.turn_complete` | 잔여 오디오 flush (silence padding) |
| `server_content.interrupted` | `call.clear_audio()`, 버퍼 리셋 |
| `server_content.input_transcription` | `call._emit("transcript", "user", text)` |
| `server_content.output_transcription` | `call._emit("transcript", "assistant", text)` |
| `tool_call.function_calls[]` | `_tools.call()` 실행 후 `session.send_tool_response()` |
| `tool_call_cancellation` | 로깅 |

Transcription 이벤트 위치가 SDK 버전에 따라 다를 수 있으므로 `server_content` 하위와 response 최상위 모두 체크한다.

## Key Implementation Details

### SDK 연결 관리

```python
# start()에서 context manager를 수동으로 enter
self._live_ctx = self._client.aio.live.connect(model=self._model, config=config)
self._session = await self._live_ctx.__aenter__()

# stop()에서 exit
await self._live_ctx.__aexit__(None, None, None)
```

### 오디오 입력 (feed_audio)

SDK의 `send_realtime_input()`에 `types.Blob`으로 전달. SDK가 base64 인코딩과 JSON 직렬화를 처리한다.

```python
await self._session.send_realtime_input(
    audio=types.Blob(data=pcm16k, mime_type="audio/pcm;rate=16000"),
)
```

### 오디오 출력

SDK response의 `inline_data.data`는 raw bytes (base64 디코딩 불필요). 160B ulaw 프레임 정렬 유지.

### Tool Response

SDK의 `send_tool_response()` 사용. `types.LiveFunctionResponse` 객체로 전달.

### 인사말 (Greeting)

SDK의 `send_client_content()` 사용.

```python
await self._session.send_client_content(
    turns=types.Content(role="user", parts=[types.Part(text="인사해 주세요.")]),
    turn_complete=True,
)
```

## Dependencies

- `google-genai>=1.60.0` (pyproject.toml의 gemini-llm extra에서 버전 상향)
- `websockets` (google-genai의 transitive dependency)
- `aiohttp` 제거 가능 (GeminiRealtime에서 더 이상 사용하지 않음, 단 다른 모듈에서 사용 중이면 유지)

## What We Keep

- `_sanitize_schema_for_gemini()`: tool schema 변환 함수 유지
- `_resolve_ref()`: $ref resolve 함수 유지
- `HANG_UP_TOOL`: 전화 종료 tool 유지
- Session Protocol 인터페이스: `start()`, `feed_audio()`, `stop()` 동일
- `set_tool_registry()`, `set_recorder()`: per-call injection 동일

## What We Remove

- Raw WebSocket 연결 코드 (`aiohttp.ClientSession`, `ws_connect`)
- 수동 setup 메시지 직렬화
- `_wait_setup_complete()` 메서드
- `_parse_ws_message()` 메서드
- `_send()` 메서드 (raw JSON 전송)
- 디버그 WAV 덤프 코드
- 디버그 오디오 레벨 로깅
