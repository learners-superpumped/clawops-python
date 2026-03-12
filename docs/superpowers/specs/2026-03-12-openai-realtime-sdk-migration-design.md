# OpenAI Realtime SDK Migration Design

## Overview

`_openai_realtime.py`를 `aiohttp` 직접 WebSocket 관리에서 `openai` Python SDK(`AsyncOpenAI.realtime.connect()`)로 마이그레이션한다. 동시에 `openai-realtime`과 `openai-llm` optional dependency를 `openai`로 통합한다.

## Motivation

- `aiohttp`로 직접 WebSocket을 관리하면 연결/에러/직렬화를 모두 수동으로 처리해야 한다
- `openai` SDK가 Realtime API를 공식 지원하므로, SDK에 위임하면 코드가 단순해지고 타입 안전성이 확보된다
- `openai-realtime`과 `openai-llm`을 `openai` 하나로 통합하면 사용자 설치 경험이 개선된다

## Approach

SDK 전면 채택. `AsyncOpenAI().realtime.connect()`를 사용해 WebSocket 관리를 SDK에 완전 위임.

## Design

### 1. Connection Lifecycle

**현재:** `aiohttp.ClientSession` → `ws_connect()` → 수동 WebSocket + `_receive_loop` 태스크

**변경:**

```python
from openai import AsyncOpenAI

# start()
self._client = AsyncOpenAI(api_key=api_key)
manager = self._client.realtime.connect(model=model)
self._connection = await manager.enter()

# stop()
await self._connection.close()
```

SDK의 `AsyncRealtimeConnectionManager`는 `.enter()` 메서드를 공식 지원한다. `async with` 없이 수동 lifecycle 관리가 가능하며, 문서에도 명시되어 있다.

### 2. Event Sending (raw dict → SDK methods)

| 현재 (`_send` raw dict) | SDK 메서드 |
|---|---|
| `{"type": "session.update", "session": {...}}` | `connection.session.update(session={...})` |
| `{"type": "response.create"}` | `connection.response.create()` |
| `{"type": "input_audio_buffer.append", "audio": ...}` | `connection.input_audio_buffer.append(audio=...)` |
| `{"type": "conversation.item.create", "item": {...}}` | `connection.conversation.item.create(item={...})` |
| `{"type": "conversation.item.truncate", ...}` | `connection.conversation.item.truncate(item_id=..., content_index=..., audio_end_ms=...)` |

`_send()` 헬퍼 메서드는 제거된다.

### 3. Event Receiving (receive loop)

```python
# 현재
async for msg in self._ws:
    event = json.loads(msg.data)
    await self._handle_event(event)

# 변경
async for event in self._connection:
    await self._handle_event(event)
```

이벤트가 typed object로 전달되므로 `event.get("type")` → `event.type`, `event.get("delta")` → `event.delta` 등으로 변경.

### 4. Event Handling Mapping

| 이벤트 | 현재 (raw dict) | 변경 (typed event) |
|---|---|---|
| `response.audio.delta` | `event.get("delta")` → `base64.b64decode()` | `event.delta` → `base64.b64decode()` |
| | `event.get("item_id")` | `event.item_id` |
| `response.audio.done` | `event_type == "response.audio.done"` | `event.type == "response.audio.done"` |
| `input_audio_buffer.speech_started` | 동일 패턴 | 동일 패턴 |
| `response.output_item.done` | `event.get("item", {})` → dict access | `event.item` → attribute access |
| `transcription.completed` | `event.get("transcript", "")` | `event.transcript` |
| `response.audio_transcript.done` | `event.get("transcript", "")` | `event.transcript` |
| `error` | `event.get("error")` | `event.error` |

Tool call 핸들링: `item.get("arguments")` → `item.arguments`, `item.get("call_id")` → `item.call_id`.

### 5. Dependency Changes (pyproject.toml)

```toml
# 변경 전
openai-realtime = ["clawops[agent]"]
openai-llm = ["clawops[agent]", "openai>=1.0.0"]

# 변경 후
openai = ["clawops[agent]", "openai>=1.76.0"]
```

`agent-all`에서도 통합:
```toml
# 변경 전
"clawops[openai-realtime]",
"clawops[openai-llm]",

# 변경 후
"clawops[openai]",
```

다른 openai-compatible provider들 (`ollama`, `mistral`, `groq` 등)은 `openai>=1.0.0`을 그대로 유지.

### 6. Removed Code

- `aiohttp` import 및 `self._http: aiohttp.ClientSession` 관리
- `_send()` 헬퍼 메서드 전체
- `OPENAI_REALTIME_URL` 상수 (SDK가 URL 관리)
- `json.loads`/`json.dumps` (SDK가 직렬화 처리)
- `_cleanup()`에서 `aiohttp` 세션 정리 로직

### 7. Preserved Code

- `OpenAIRealtimeConfig` dataclass (하위 호환)
- 오디오 처리 로직 (160B 프레임 정렬, ulaw→pcm16 변환, silence 패딩)
- 진단 로깅 (delta 간격 측정)
- Tool call 핸들링 (hang_up, collect_dtmf, send_dtmf, custom tools)
- Tracing spans (`llm_session_span`, `tool_call_span`)
- `AudioRecorder` 연동
- Session Protocol 인터페이스 (`start`, `feed_audio`, `feed_dtmf`, `stop`)

### 8. Documentation Updates

`openai-realtime` + `openai-llm` → `openai` 통합에 따른 문서 변경:

**clawops-python:**

| 파일 | 변경 |
|---|---|
| `README.md` | `pip install clawops[agent,openai-llm,...]` → `clawops[agent,openai,...]` |
| `docs/agent/quickstart.md` | `openai-llm` → `openai`, realtime 설치도 `openai`로 통합 |

**clawops (메인 - 웹 문서):**

| 파일 | 변경 |
|---|---|
| `web/content/docs/voice-agent/index.mdx` | `OpenAIRealtime` 설치 안내, `openai-llm` 참조를 `openai`로 변경 |

**clawops-node:** Node SDK는 npm 패키지 구조가 다르므로 이번 Python SDK 마이그레이션과 무관. 변경 불필요.

## Changed Files

| 파일 | 변경 내용 |
|---|---|
| `src/clawops/agent/pipeline/_openai_realtime.py` | 핵심 마이그레이션 |
| `pyproject.toml` | dependency 통합 |
| `src/clawops/agent/pipeline/__init__.py` | export 확인 |
| `src/clawops/agent/plugins/openai_realtime.py` | backward compat 확인 |
| `README.md` | 설치 안내 업데이트 |
| `docs/agent/quickstart.md` | 설치 안내 업데이트 |
| `tests/agent/test_realtime_session.py` | SDK mock 방식 업데이트 |
| (clawops) `web/content/docs/voice-agent/index.mdx` | 설치 안내 업데이트 |
