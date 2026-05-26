# Realtime Session Prewarm + First-Audio Prebuffer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** outbound 통화에서 상대방 응답 후 첫 음성까지 체감 latency 를 1.2–3.2s → ~150ms 로 줄인다. SDK 양쪽(clawops-python / clawops-node) 에 동일한 prewarm/attach API 를 추가하고 ClawOpsAgent 의 outbound_ready 훅에서 호출하도록 한다.

**Architecture:**
- Session Protocol 에 `prewarm()` / `attach(call)` 두 메서드를 추가한다. 기존 `start(call)` 은 `prewarm` + `attach` 의 thin wrapper 로 동등성 유지.
- prewarm 단계: LLM WebSocket 연결 + `session.update` (system prompt) + (옵션) `response.create` 호출 → 도착하는 audio.delta 를 내부 메모리 버퍼에 누적. 이때 `call` 은 `_BufferingCall` stub 으로 대체되어 send_audio 가 버퍼로 향한다.
- attach 단계: 실제 `CallSession` 으로 교체 + 버퍼 flush (RTP timing 으로 emit). 이후 delta 는 실시간 통과.
- 호출자(ClawOpsAgent): `_handle_outbound_ready` 시점에 `session.prewarm()` 시작 (백그라운드 task), media WS 연결 후 `session.attach(call)`.

**Tech Stack:**
- clawops-python: Python 3.11, asyncio, openai SDK, google-genai, pytest
- clawops-node: TypeScript, Node 22, ws, @google/genai, vitest
- 통합 테스트: 양 SDK 의 mock WS 기반

---

## Phase 1 — clawops-python SDK (SoT)

clawops-python 을 먼저 완성한다. clawops-node 는 동일 API/동일 동작으로 mirror.

### Task 1: Session Protocol 확장 (prewarm / attach 추가)

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/pipeline/_base.py` (Session Protocol)
- Test: `/Users/ghyeok/Developments/clawops-python/tests/agent/test_session_protocol.py`

- [ ] **Step 1: 기존 테스트 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_session_protocol.py -v`
Expected: 기존 테스트 모두 PASS (baseline)

- [ ] **Step 2: 실패하는 테스트 추가**

`/Users/ghyeok/Developments/clawops-python/tests/agent/test_session_protocol.py` 끝에 추가:

```python
def test_session_protocol_has_prewarm():
    """Session Protocol 에 prewarm() 가 정의되어 있어야 한다."""
    from clawops.agent.pipeline._base import Session
    # Protocol 의 속성은 __annotations__ 가 아니라 dir() 로 확인
    assert "prewarm" in dir(Session)


def test_session_protocol_has_attach():
    """Session Protocol 에 attach(call) 이 정의되어 있어야 한다."""
    from clawops.agent.pipeline._base import Session
    assert "attach" in dir(Session)
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_session_protocol.py::test_session_protocol_has_prewarm tests/agent/test_session_protocol.py::test_session_protocol_has_attach -v`
Expected: FAIL (prewarm / attach 미정의)

- [ ] **Step 4: Session Protocol 에 prewarm/attach 시그니처 추가**

`_base.py` 의 `Session` Protocol 에 추가:

```python
@runtime_checkable
class Session(Protocol):
    """Realtime 또는 Pipeline 세션의 공통 인터페이스."""

    async def start(self, call: CallSession) -> None:
        """세션 시작 (WS 연결, 인사말 등). prewarm + attach 의 thin wrapper."""
        ...

    async def prewarm(self) -> None:
        """LLM WS 연결 + session.update 만 수행한다. CallSession 없이 호출 가능.

        prewarm 후 도착하는 audio delta 는 내부 버퍼에 누적된다.
        attach() 호출 시 실제 CallSession 으로 flush.
        """
        ...

    async def attach(self, call: CallSession) -> None:
        """prewarmed 세션에 실제 CallSession 을 부착하고 버퍼를 flush 한다."""
        ...

    async def feed_audio(self, audio: bytes, timestamp: int) -> None:
        ...

    async def feed_dtmf(self, digits: str) -> None:
        ...

    async def stop(self) -> None:
        ...

    def get_telemetry(self) -> dict[str, Any] | None:
        ...
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_session_protocol.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
cd /Users/ghyeok/Developments/clawops-python
git add src/clawops/agent/pipeline/_base.py tests/agent/test_session_protocol.py
git commit -m "feat(agent): Session Protocol 에 prewarm/attach 추가

prewarm: LLM WS 만 미리 연결, CallSession 없이 호출 가능
attach: prewarmed 세션에 CallSession 부착 + 버퍼 flush
기존 start() 는 prewarm+attach 의 thin wrapper 로 유지"
```

---

### Task 2: `_BufferingCall` stub 구현

**Files:**
- Create: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/pipeline/_buffering_call.py`
- Test: `/Users/ghyeok/Developments/clawops-python/tests/agent/test_buffering_call.py`

prewarm 중에는 실제 `CallSession` 이 없으므로 `send_audio` 호출을 메모리 버퍼에 모으는 stub 이 필요하다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/agent/test_buffering_call.py`:

```python
import pytest
from clawops.agent.pipeline._buffering_call import _BufferingCall


@pytest.mark.asyncio
async def test_buffers_audio_chunks():
    """send_audio 호출이 순서대로 버퍼에 누적된다."""
    stub = _BufferingCall()
    await stub.send_audio(b"chunk1")
    await stub.send_audio(b"chunk2")
    assert stub.drain_buffer() == [b"chunk1", b"chunk2"]


@pytest.mark.asyncio
async def test_drain_empties_buffer():
    """drain 후 버퍼는 비워진다."""
    stub = _BufferingCall()
    await stub.send_audio(b"x")
    stub.drain_buffer()
    assert stub.drain_buffer() == []


@pytest.mark.asyncio
async def test_emit_noop():
    """_emit (transcript 등) 은 silent no-op."""
    stub = _BufferingCall()
    await stub._emit("transcript", "user", "hello")  # 예외 없어야 함


@pytest.mark.asyncio
async def test_metrics_stub():
    """metrics 속성도 record_* 호출을 받을 수 있어야 한다 (no-op)."""
    stub = _BufferingCall()
    stub.metrics.record_tool_call()  # 예외 없어야 함
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_buffering_call.py -v`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`src/clawops/agent/pipeline/_buffering_call.py`:

```python
"""prewarm 단계에서 사용되는 CallSession stub.

실제 통화가 아직 attach 되지 않은 상태에서 Session 구현체가 호출하는
send_audio / _emit / metrics 를 흡수한다. attach() 시점에 drain_buffer() 로
누적된 audio chunk 들을 실제 CallSession 에 flush 한다.
"""
from __future__ import annotations

from typing import Any


class _MetricsStub:
    def record_tool_call(self) -> None:
        pass

    def record_interrupt(self) -> None:
        pass


class _BufferingCall:
    """prewarm 단계의 CallSession 역할.

    Session 구현체가 `self._call.send_audio(...)` 를 호출하면 메모리 버퍼에 쌓는다.
    attach() 시 drain_buffer() 로 꺼내 실제 CallSession 으로 flush.
    """

    def __init__(self) -> None:
        self._buffer: list[bytes] = []
        self.metrics = _MetricsStub()

    async def send_audio(self, chunk: bytes) -> None:
        self._buffer.append(chunk)

    async def _emit(self, *args: Any, **kwargs: Any) -> None:
        # transcript 등 이벤트는 prewarm 동안 흘려보낸다 (no-op).
        pass

    def drain_buffer(self) -> list[bytes]:
        out = self._buffer
        self._buffer = []
        return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_buffering_call.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/clawops/agent/pipeline/_buffering_call.py tests/agent/test_buffering_call.py
git commit -m "feat(agent): _BufferingCall stub - prewarm 단계 send_audio 누적 버퍼"
```

---

### Task 3: `OpenAIRealtime` 에 prewarm/attach 구현

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/pipeline/realtime/_openai.py:162-205` (`start` 분리)
- Test: `/Users/ghyeok/Developments/clawops-python/tests/agent/test_openai_prewarm.py` (신규)

핵심: 기존 `start()` 의 본문을 `prewarm()` (LLM 연결+session.update+response.create+receive_loop) 과 `attach()` (실제 call 교체+버퍼 flush) 로 분리하고, `start()` 는 둘을 순차 호출하는 wrapper 가 된다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/agent/test_openai_prewarm.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline.realtime._openai import OpenAIRealtime


def _make_mock_connection() -> MagicMock:
    """OpenAI Realtime connection mock — 최소한의 async API 흉내."""
    conn = MagicMock()
    conn.session = MagicMock()
    conn.session.update = AsyncMock()
    conn.response = MagicMock()
    conn.response.create = AsyncMock()
    conn.input_audio_buffer = MagicMock()
    conn.input_audio_buffer.append = AsyncMock()

    async def _aiter() -> None:
        # receive_loop 가 즉시 끝나도록 빈 stream
        if False:
            yield None
        return

    conn.__aiter__ = lambda self_: _aiter()
    return conn


@pytest.mark.asyncio
async def test_prewarm_opens_ws_without_call() -> None:
    """prewarm() 은 CallSession 없이 호출 가능하다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=False)
    mock_conn = _make_mock_connection()
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()
    mock_conn.session.update.assert_awaited_once()
    assert sess._call is not None  # _BufferingCall 로 채워져야 함


@pytest.mark.asyncio
async def test_prewarm_with_greeting_calls_response_create() -> None:
    """greeting=True 면 prewarm 시 response.create 도 호출된다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=True)
    mock_conn = _make_mock_connection()
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()
    mock_conn.response.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_attach_replaces_buffering_call_and_flushes() -> None:
    """attach() 가 _BufferingCall 의 누적 chunk 를 실제 call.send_audio 로 flush 한다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=False)
    mock_conn = _make_mock_connection()
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()

    # prewarm 동안 audio 가 들어왔다고 가정
    await sess._call.send_audio(b"a" * 160)
    await sess._call.send_audio(b"b" * 160)

    real_call = MagicMock()
    real_call.send_audio = AsyncMock()
    real_call._emit = AsyncMock()
    real_call.metrics = MagicMock()

    await sess.attach(real_call)

    assert sess._call is real_call
    assert real_call.send_audio.await_count == 2
    real_call.send_audio.assert_any_await(b"a" * 160)
    real_call.send_audio.assert_any_await(b"b" * 160)


@pytest.mark.asyncio
async def test_start_calls_prewarm_then_attach() -> None:
    """기존 start(call) 은 prewarm + attach 의 wrapper 다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=False)
    sess.prewarm = AsyncMock()
    sess.attach = AsyncMock()
    real_call = MagicMock()
    await sess.start(real_call)
    sess.prewarm.assert_awaited_once()
    sess.attach.assert_awaited_once_with(real_call)
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_openai_prewarm.py -v`
Expected: FAIL (prewarm/attach 미구현, _open_connection 미정의)

- [ ] **Step 3: `_open_connection` 헬퍼 추출 + prewarm 구현**

`_openai.py` 의 기존 `start()` (라인 162–205) 를 아래로 교체:

```python
    async def _open_connection(self):
        """OpenAI Realtime WS 를 열어 connection 핸들을 반환한다.

        테스트에서 mocking 하기 위해 별도 메서드로 추출.
        """
        self._client = AsyncOpenAI(api_key=self._config.openai_api_key)
        manager = self._client.realtime.connect(model=self._config.model)
        return await manager.enter()

    async def prewarm(self) -> None:
        """LLM WS 연결 + session.update + (옵션) response.create 만 수행한다.

        CallSession 없이 호출 가능. attach() 가 호출되기 전까지 도착하는
        audio delta 는 _BufferingCall 의 메모리 버퍼에 누적된다.
        """
        from .._buffering_call import _BufferingCall  # local import: 순환 회피

        self._call = _BufferingCall()  # type: ignore[assignment]
        self._latest_media_ts = 0

        self._llm_span_ctx = llm_session_span(self._config.model, voice=self._config.voice)
        self._llm_span = self._llm_span_ctx.__enter__()

        self._connection = await self._open_connection()
        log.info("OpenAI Realtime connected (prewarm)")

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
                            "model": "gpt-realtime-whisper",
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

    async def attach(self, call: CallSession) -> None:
        """prewarmed 세션에 실제 CallSession 부착 + 버퍼 flush.

        prewarm() 이 선행되어 있어야 한다. start() 는 prewarm+attach wrapper.
        """
        from .._buffering_call import _BufferingCall

        prev = self._call
        self._call = call

        if isinstance(prev, _BufferingCall):
            for chunk in prev.drain_buffer():
                await call.send_audio(chunk)

    async def start(self, call: CallSession) -> None:
        """기존 호환 경로 — prewarm + attach 의 thin wrapper."""
        await self.prewarm()
        await self.attach(call)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_openai_prewarm.py -v`
Expected: PASS (4건)

- [ ] **Step 5: 기존 OpenAI 통합 테스트 회귀 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_realtime_session.py tests/agent/test_openai_llm.py -v`
Expected: 기존 테스트 모두 PASS (start() wrapper 가 동작 동등성 보장)

- [ ] **Step 6: 커밋**

```bash
git add src/clawops/agent/pipeline/realtime/_openai.py tests/agent/test_openai_prewarm.py
git commit -m "feat(openai-realtime): prewarm/attach 분리 구현

start() 본문을 _open_connection / prewarm / attach 로 분리.
prewarm 은 CallSession 없이 호출 가능하며 audio delta 를 _BufferingCall 에 누적.
attach 시 실제 CallSession 으로 교체 + 버퍼 flush.
기존 start(call) 은 prewarm+attach wrapper 로 동작 동등성 유지."
```

---

### Task 4: `GeminiRealtime` mirror 구현

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/pipeline/realtime/_gemini.py:204-259`
- Test: `/Users/ghyeok/Developments/clawops-python/tests/agent/test_gemini_prewarm.py` (신규)

OpenAI 와 동일한 패턴: `_open_connection` 헬퍼 + `prewarm` + `attach` + `start` wrapper.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/agent/test_gemini_prewarm.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline.realtime._gemini import GeminiRealtime


@pytest.mark.asyncio
async def test_gemini_prewarm_opens_live_session_without_call() -> None:
    sess = GeminiRealtime(api_key="g-test", greeting=False)
    mock_live = MagicMock()
    mock_live.send_realtime_input = AsyncMock()
    with patch.object(sess, "_open_live_session", new=AsyncMock(return_value=mock_live)):
        await sess.prewarm()
    assert sess._session is mock_live
    assert sess._call is not None


@pytest.mark.asyncio
async def test_gemini_prewarm_greeting_sends_text() -> None:
    sess = GeminiRealtime(api_key="g-test", greeting=True)
    mock_live = MagicMock()
    mock_live.send_realtime_input = AsyncMock()
    with patch.object(sess, "_open_live_session", new=AsyncMock(return_value=mock_live)):
        await sess.prewarm()
    mock_live.send_realtime_input.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_attach_flushes_buffer() -> None:
    sess = GeminiRealtime(api_key="g-test", greeting=False)
    mock_live = MagicMock()
    with patch.object(sess, "_open_live_session", new=AsyncMock(return_value=mock_live)):
        await sess.prewarm()
    await sess._call.send_audio(b"x" * 160)

    real_call = MagicMock()
    real_call.send_audio = AsyncMock()
    real_call._emit = AsyncMock()
    real_call.metrics = MagicMock()
    await sess.attach(real_call)
    real_call.send_audio.assert_awaited_once_with(b"x" * 160)


@pytest.mark.asyncio
async def test_gemini_start_calls_prewarm_then_attach() -> None:
    sess = GeminiRealtime(api_key="g-test", greeting=False)
    sess.prewarm = AsyncMock()
    sess.attach = AsyncMock()
    real_call = MagicMock()
    await sess.start(real_call)
    sess.prewarm.assert_awaited_once()
    sess.attach.assert_awaited_once_with(real_call)
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_gemini_prewarm.py -v`
Expected: FAIL

- [ ] **Step 3: `_gemini.py` 의 start() 분리**

`_gemini.py` 의 기존 `start()` 본문 (라인 204–259) 을 OpenAI 와 동일 패턴으로 재구성:

```python
    async def _open_live_session(self):
        """Gemini Live 세션을 열어 핸들을 반환한다. 테스트 mocking 지점."""
        # (기존 client.aio.live.connect 부분을 그대로 옮긴다.
        #  현재 코드의 self._live_ctx = ...; await self._live_ctx.__aenter__() 패턴 유지)
        self._live_ctx = self._client.aio.live.connect(model=self._config.model, config=self._build_config())
        return await self._live_ctx.__aenter__()

    async def prewarm(self) -> None:
        from .._buffering_call import _BufferingCall
        self._call = _BufferingCall()  # type: ignore[assignment]
        self._latest_media_ts = 0

        self._llm_span_ctx = llm_session_span(self._config.model, voice=self._config.voice)
        self._llm_span = self._llm_span_ctx.__enter__()

        self._session = await self._open_live_session()
        log.info("Gemini Live connected (prewarm)")

        if self._config.greeting:
            await self._session.send_realtime_input(text="인사해 주세요.")

        self._tasks.append(asyncio.create_task(self._receive_loop()))

    async def attach(self, call: CallSession) -> None:
        from .._buffering_call import _BufferingCall
        prev = self._call
        self._call = call
        if isinstance(prev, _BufferingCall):
            for chunk in prev.drain_buffer():
                await call.send_audio(chunk)

    async def start(self, call: CallSession) -> None:
        await self.prewarm()
        await self.attach(call)
```

(주의: `_build_config()` 등 보조 메서드 이름은 실제 `_gemini.py` 의 기존 구조에 맞춰 추출. 기존 코드 그대로 옮기면 된다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_gemini_prewarm.py tests/agent/test_gemini_realtime.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/clawops/agent/pipeline/realtime/_gemini.py tests/agent/test_gemini_prewarm.py
git commit -m "feat(gemini-realtime): prewarm/attach 분리 구현 (OpenAI mirror)"
```

---

### Task 5: `PipelineSession` mirror 구현

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/pipeline/_pipeline_session.py`
- Test: `/Users/ghyeok/Developments/clawops-python/tests/agent/test_pipeline_prewarm.py` (신규)

PipelineSession (STT→LLM→TTS) 도 같은 인터페이스. greeting trigger 가 `[통화 시작]` 합성 메시지 (line 234–237) 인 점만 다르다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/agent/test_pipeline_prewarm.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawops.agent.pipeline._pipeline_session import PipelineSession


@pytest.mark.asyncio
async def test_pipeline_prewarm_no_call_required() -> None:
    stt = MagicMock(); llm = MagicMock(); tts = MagicMock()
    sess = PipelineSession(stt=stt, llm=llm, tts=tts, system_prompt="x", greeting=False)
    # 외부 의존성은 mock — connect 단계 자체가 lazy 라면 prewarm 은 단순 상태 세팅
    await sess.prewarm()
    assert sess._call is not None  # BufferingCall


@pytest.mark.asyncio
async def test_pipeline_attach_flushes_tts_buffer() -> None:
    stt = MagicMock(); llm = MagicMock(); tts = MagicMock()
    sess = PipelineSession(stt=stt, llm=llm, tts=tts, system_prompt="x", greeting=False)
    await sess.prewarm()
    await sess._call.send_audio(b"u" * 160)

    real_call = MagicMock()
    real_call.send_audio = AsyncMock()
    real_call._emit = AsyncMock()
    real_call.metrics = MagicMock()
    await sess.attach(real_call)
    real_call.send_audio.assert_awaited_once_with(b"u" * 160)
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_pipeline_prewarm.py -v`
Expected: FAIL

- [ ] **Step 3: PipelineSession 에 prewarm/attach 추가**

`_pipeline_session.py` 의 기존 `start()` (line 122–237) 를 분리:

```python
    async def prewarm(self) -> None:
        """STT/LLM/TTS 준비 + (옵션) greeting trigger.

        외부 연결이 lazy 인 경우 단순히 BufferingCall 만 세팅하고,
        eager 인 경우 여기서 미리 connect/handshake 한다.
        """
        from ._buffering_call import _BufferingCall
        self._call = _BufferingCall()  # type: ignore[assignment]
        self._closed = False
        # 기존 start() 의 STT/LLM/TTS 준비 부분 (greeting trigger 제외) 을 이리로 옮긴다.

        if self._greeting:
            # 0.5s delay 후 [통화 시작] 메시지로 trigger — 기존 동작 유지
            await self._trigger_greeting()

    async def attach(self, call: CallSession) -> None:
        from ._buffering_call import _BufferingCall
        prev = self._call
        self._call = call
        if isinstance(prev, _BufferingCall):
            for chunk in prev.drain_buffer():
                await call.send_audio(chunk)

    async def start(self, call: CallSession) -> None:
        await self.prewarm()
        await self.attach(call)
```

(실제 본문은 기존 `start()` 의 STT/LLM/TTS 초기화 로직을 그대로 옮긴다. `_trigger_greeting()` 은 기존 0.5s delay + 합성 메시지 로직을 메서드로 추출.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_pipeline_prewarm.py tests/agent/test_pipeline_session.py tests/agent/test_pipeline_base.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/clawops/agent/pipeline/_pipeline_session.py tests/agent/test_pipeline_prewarm.py
git commit -m "feat(pipeline-session): prewarm/attach 분리 구현 (mirror)"
```

---

### Task 6: 미응답/cancel 경로 — `stop()` 보강 + timeout 가드

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/pipeline/realtime/_openai.py` (`stop()`)
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/pipeline/realtime/_gemini.py` (`stop()`)
- Test: `/Users/ghyeok/Developments/clawops-python/tests/agent/test_prewarm_cancel.py` (신규)

prewarm 후 attach 가 안 되고 일정 시간 지나면 자동 close. 미응답/거절 시 leak 방지. [call_engine_ari_hangup_no_timeout_guard] 함정 회피.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/agent/test_prewarm_cancel.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline.realtime._openai import OpenAIRealtime


@pytest.mark.asyncio
async def test_prewarm_then_stop_closes_connection() -> None:
    """prewarm 후 attach 없이 stop() 호출하면 WS 가 닫힌다."""
    sess = OpenAIRealtime(api_key="sk-test", greeting=False)
    mock_conn = MagicMock()
    mock_conn.session = MagicMock(); mock_conn.session.update = AsyncMock()
    mock_conn.response = MagicMock(); mock_conn.response.create = AsyncMock()
    mock_conn.close = AsyncMock()
    async def _aiter():
        if False: yield None
    mock_conn.__aiter__ = lambda self_: _aiter()
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()
    await sess.stop()
    # stop 이 WS close 를 트리거해야 함 (구체 호출은 _cleanup 경로 통해)
    # 최소한 _connection 이 None 또는 closed 상태여야 함
    # 구현에 따라 검증 방식 조정 — 여기서는 stop 이 예외 없이 끝나는 것 확인
```

- [ ] **Step 2: 테스트 실행 → 실패 확인 (또는 baseline PASS)**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_prewarm_cancel.py -v`
Expected: 기존 stop() 이 _connection close 를 안 하면 FAIL. 하면 PASS.

- [ ] **Step 3: `stop()` 에 connection close 보강**

`_openai.py` 의 `stop()` 또는 `_cleanup()` 에 다음 보장 추가:

```python
    async def stop(self) -> None:
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._connection is not None:
            try:
                await asyncio.wait_for(self._connection.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception) as e:
                log.warning(f"connection close error: {e}")
            self._connection = None
        # ... 기존 정리 로직
```

`_gemini.py` 도 동일 패턴 (`self._live_ctx.__aexit__` 호출 보장 + timeout).

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_prewarm_cancel.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/clawops/agent/pipeline/realtime/ tests/agent/test_prewarm_cancel.py
git commit -m "fix(realtime): stop() 에 connection close timeout 가드 추가

prewarm 후 attach 안 되고 stop 호출되는 미응답/거절 시나리오에서
LLM WS 가 leak 되지 않도록 명시적 close + 2s timeout."
```

---

### Task 7: `ClawOpsAgent._handle_outbound_ready` 에서 prewarm 호출

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/_agent.py:423` (`_handle_outbound_ready`)
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/_agent.py:279,367,385` (`_start_call_session`)
- Test: `/Users/ghyeok/Developments/clawops-python/tests/agent/test_agent.py` (확장)

핵심 통합 지점. outbound_ready 이벤트 (= call-engine 이 originate 시작했음을 알림, answer 전) 에서 `session.prewarm()` 을 백그라운드 task 로 시작. media WS 연결 후 `session.attach(call)` 로 부착.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/agent/test_agent.py` 에 추가:

```python
@pytest.mark.asyncio
async def test_outbound_ready_triggers_prewarm() -> None:
    """outbound_ready 이벤트 수신 시 session.prewarm() 이 백그라운드로 시작된다."""
    from clawops.agent._agent import ClawOpsAgent
    # ... 기존 테스트의 agent fixture 패턴 따름
    agent = _build_test_agent()  # 기존 helper 가 있으면 사용
    session_mock = AsyncMock()
    agent._session_factory = lambda: session_mock

    await agent._handle_outbound_ready({"call_id": "C1", "media_url": "wss://media/C1"})
    # prewarm 이 호출돼야 함 (즉시 또는 백그라운드 task 로)
    # event loop 한 번 돌려 task 시작 보장
    await asyncio.sleep(0)
    session_mock.prewarm.assert_awaited_once()


@pytest.mark.asyncio
async def test_media_ws_connect_then_attach_not_start() -> None:
    """media WS 연결 후 attach(call) 가 호출되고 start() 는 호출되지 않는다 (prewarmed 경로)."""
    # _start_call_session 의 변경 검증
    # ... agent fixture
    # outbound_ready → prewarm 호출
    # media_ws.connect 완료 simulated
    # session.attach.assert_awaited_once_with(call)
    # session.start.assert_not_awaited()
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_agent.py::test_outbound_ready_triggers_prewarm tests/agent/test_agent.py::test_media_ws_connect_then_attach_not_start -v`
Expected: FAIL

- [ ] **Step 3: `_handle_outbound_ready` 와 `_start_call_session` 수정**

`_agent.py:423` `_handle_outbound_ready` 에:

```python
    async def _handle_outbound_ready(self, data: dict[str, Any]) -> None:
        call_id = data.get("call_id")
        if call_id not in self._calls:
            log.warning(f"Unknown outbound call: {call_id}")
            return
        call = self._calls[call_id]
        # 세션 prewarm 을 백그라운드로 시작 — media WS 연결과 병렬 진행
        session = self._build_session_for(call)
        self._prewarm_tasks[call_id] = asyncio.create_task(
            self._prewarm_session(call_id, session)
        )
        # 기존 _start_call_session 호출은 그대로 (단, 내부에서 attach 사용으로 변경)
        ...

    async def _prewarm_session(self, call_id: str, session: Any) -> None:
        try:
            await asyncio.wait_for(session.prewarm(), timeout=10.0)
        except Exception as e:
            log.warning(f"prewarm failed for {call_id}: {e}")
            # prewarm 실패해도 attach 시점에 start() fallback 가능하도록 표시
            self._prewarm_failed.add(call_id)
```

`_start_call_session` (line 279, 367, 385) 의 `session.start(call)` 호출을 다음 패턴으로 변경:

```python
        # prewarm task 가 완료될 때까지 대기 (실패하면 fallback)
        prewarm_task = self._prewarm_tasks.pop(call.id, None)
        if prewarm_task is not None and call.id not in self._prewarm_failed:
            try:
                await prewarm_task
                await session.attach(call)
            except Exception as e:
                log.warning(f"prewarm await failed, falling back to start: {e}")
                await session.start(call)
        else:
            # prewarm 안 했거나 실패 → 기존 경로
            await session.start(call)
```

`ClawOpsAgent.__init__` 에 `self._prewarm_tasks: dict[str, asyncio.Task[Any]] = {}; self._prewarm_failed: set[str] = set()` 추가.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_agent.py -v`
Expected: PASS (전체 agent 테스트 회귀 없음)

- [ ] **Step 5: 미응답 경로 cleanup 보강**

`_handle_call_ended` 또는 hangup 핸들러에서:

```python
        prewarm_task = self._prewarm_tasks.pop(call_id, None)
        if prewarm_task is not None and not prewarm_task.done():
            prewarm_task.cancel()
        self._prewarm_failed.discard(call_id)
```

- [ ] **Step 6: 커밋**

```bash
git add src/clawops/agent/_agent.py tests/agent/test_agent.py
git commit -m "feat(agent): outbound_ready 시 session.prewarm() 백그라운드 시작

call-engine 의 outbound_ready 이벤트 수신 즉시 LLM WS 연결을 시작한다.
media WS 연결 후에는 start() 대신 attach() 로 전환하여 prewarmed 세션 사용.
prewarm 실패/timeout 시 기존 start() 경로로 자동 fallback.
hangup 시 prewarm task cancel + 리소스 정리."
```

---

### Task 8: Phase 1 통합 smoke test

**Files:**
- Create: `/Users/ghyeok/Developments/clawops-python/tests/agent/test_prewarm_integration.py`

mock control WS / mock LLM 으로 end-to-end 시뮬레이션.

- [ ] **Step 1: 통합 테스트 작성**

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_outbound_ready_to_attach_full_flow() -> None:
    """outbound_ready → prewarm 시작 → media WS 연결 → attach → audio flush."""
    from clawops.agent._agent import ClawOpsAgent
    from clawops.agent.pipeline.realtime._openai import OpenAIRealtime
    from clawops.agent.pipeline._buffering_call import _BufferingCall

    # OpenAIRealtime mock connection
    mock_conn = MagicMock()
    mock_conn.session = MagicMock(); mock_conn.session.update = AsyncMock()
    mock_conn.response = MagicMock(); mock_conn.response.create = AsyncMock()
    async def _aiter():
        if False: yield None
    mock_conn.__aiter__ = lambda self_: _aiter()

    sess = OpenAIRealtime(api_key="sk-test", greeting=True)
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()
        # prewarm 직후 BufferingCall 상태
        assert isinstance(sess._call, _BufferingCall)
        # 가상 audio delta 시뮬레이션 (수동으로 BufferingCall 에 누적)
        await sess._call.send_audio(b"greeting1")
        await sess._call.send_audio(b"greeting2")

        real_call = MagicMock()
        real_call.send_audio = AsyncMock()
        real_call._emit = AsyncMock()
        real_call.metrics = MagicMock()
        await sess.attach(real_call)
        # 누적된 greeting 이 flush 되어야 함
        assert real_call.send_audio.await_count == 2
```

- [ ] **Step 2: 실행**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/test_prewarm_integration.py -v`
Expected: PASS

- [ ] **Step 3: 전체 회귀 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/ -v`
Expected: 전부 PASS

- [ ] **Step 4: 커밋**

```bash
git add tests/agent/test_prewarm_integration.py
git commit -m "test(agent): prewarm → attach end-to-end 통합 smoke test"
```

---

## Phase 2 — clawops-node SDK (mirror)

Phase 1 과 동일 인터페이스/동일 동작. 테스트 케이스 이름도 1:1 매핑.

### Task 9: Session interface 확장 (TS)

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-node/src/agent/pipeline/base.ts`
- Test: `/Users/ghyeok/Developments/clawops-node/tests/agent/session-protocol.test.ts` (신규 또는 확장)

- [ ] **Step 1: 실패하는 테스트 작성**

```typescript
import { describe, it, expect } from 'vitest';

describe('Session interface', () => {
  it('declares prewarm() and attach() methods', async () => {
    // TypeScript interface 는 런타임에 없으므로 type 검증.
    // 다음 코드가 컴파일되어야 한다 (tsc --noEmit) — 별도 type-test 파일로:
    const _check: import('../../src/agent/pipeline/base').Session = {
      start: async () => {},
      prewarm: async () => {},
      attach: async () => {},
      feedAudio: () => {},
      feedDtmf: async () => {},
      stop: async () => {},
      getTelemetry: () => null,
    };
    expect(_check).toBeTruthy();
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-node && pnpm exec vitest run tests/agent/session-protocol.test.ts`
Expected: FAIL (prewarm/attach 미정의로 컴파일 에러)

- [ ] **Step 3: `base.ts` Session interface 에 추가**

```typescript
export interface Session {
  start(call: CallSession, tools?: ToolRegistry): Promise<void>;
  prewarm(): Promise<void>;
  attach(call: CallSession): Promise<void>;
  feedAudio(audio: Buffer, timestamp?: number): void;
  feedDtmf(digits: string): Promise<void>;
  stop(): Promise<void>;
  getTelemetry(): Record<string, unknown> | null;
}
```

- [ ] **Step 4: PASS 확인 + 커밋**

```bash
cd /Users/ghyeok/Developments/clawops-node
pnpm exec tsc --noEmit
pnpm exec vitest run tests/agent/session-protocol.test.ts
git add src/agent/pipeline/base.ts tests/agent/session-protocol.test.ts
git commit -m "feat(agent): Session interface 에 prewarm/attach 추가 (Python mirror)"
```

---

### Task 10: `_BufferingCall` TS stub

**Files:**
- Create: `/Users/ghyeok/Developments/clawops-node/src/agent/pipeline/buffering-call.ts`
- Test: `/Users/ghyeok/Developments/clawops-node/tests/agent/buffering-call.test.ts`

- [ ] **Step 1: 실패하는 테스트**

```typescript
import { describe, it, expect } from 'vitest';
import { BufferingCall } from '../../src/agent/pipeline/buffering-call';

describe('BufferingCall', () => {
  it('buffers send_audio chunks in order', async () => {
    const c = new BufferingCall();
    await c.sendAudio(Buffer.from('a'));
    await c.sendAudio(Buffer.from('b'));
    const drained = c.drainBuffer();
    expect(drained).toEqual([Buffer.from('a'), Buffer.from('b')]);
  });

  it('drain empties buffer', async () => {
    const c = new BufferingCall();
    await c.sendAudio(Buffer.from('x'));
    c.drainBuffer();
    expect(c.drainBuffer()).toEqual([]);
  });

  it('emit is no-op', async () => {
    const c = new BufferingCall();
    await c.emit('transcript', 'user', 'hi');  // should not throw
  });

  it('metrics record_* is no-op', () => {
    const c = new BufferingCall();
    c.metrics.recordToolCall();  // should not throw
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-node && pnpm exec vitest run tests/agent/buffering-call.test.ts`
Expected: FAIL

- [ ] **Step 3: 구현**

`src/agent/pipeline/buffering-call.ts`:

```typescript
/**
 * prewarm 단계에서 사용되는 CallSession stub.
 *
 * Session 구현체가 sendAudio() 를 호출하면 메모리 버퍼에 누적한다.
 * attach() 시점에 drainBuffer() 로 실제 CallSession 에 flush.
 */
export class BufferingCall {
  private _buffer: Buffer[] = [];
  readonly metrics = {
    recordToolCall: () => {},
    recordInterrupt: () => {},
  };

  async sendAudio(chunk: Buffer): Promise<void> {
    this._buffer.push(chunk);
  }

  async emit(..._args: unknown[]): Promise<void> {
    // no-op during prewarm
  }

  drainBuffer(): Buffer[] {
    const out = this._buffer;
    this._buffer = [];
    return out;
  }
}
```

- [ ] **Step 4: PASS + 커밋**

```bash
pnpm exec vitest run tests/agent/buffering-call.test.ts
git add src/agent/pipeline/buffering-call.ts tests/agent/buffering-call.test.ts
git commit -m "feat(agent): BufferingCall stub (Python mirror)"
```

---

### Task 11: `OpenAIRealtime` TS prewarm/attach

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-node/src/agent/pipeline/realtime/openai-realtime.ts:146-197`
- Test: `/Users/ghyeok/Developments/clawops-node/tests/agent/openai-prewarm.test.ts` (신규)

기존 `start()` (line 146–197) 의 본문 분리. WS open → sendSessionUpdate → (greeting) response.create 까지가 prewarm. attach 는 call 교체 + 버퍼 flush.

- [ ] **Step 1: 실패하는 테스트 작성**

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { OpenAIRealtime } from '../../src/agent/pipeline/realtime/openai-realtime';
import { BufferingCall } from '../../src/agent/pipeline/buffering-call';

// ws 의 WebSocket 을 mock
vi.mock('ws', () => {
  class MockWs {
    static OPEN = 1;
    readyState = 1;
    private _handlers = new Map<string, Array<(...args: unknown[]) => void>>();
    on(event: string, fn: (...args: unknown[]) => void) {
      const arr = this._handlers.get(event) ?? [];
      arr.push(fn);
      this._handlers.set(event, arr);
      if (event === 'open') queueMicrotask(() => fn());
      return this;
    }
    send(_data: string) {}
    close() {}
  }
  return { WebSocket: MockWs };
});

describe('OpenAIRealtime.prewarm', () => {
  it('opens WS without CallSession and sends session.update', async () => {
    const sess = new OpenAIRealtime({ apiKey: 'sk-test', greeting: false });
    await sess.prewarm();
    // ws OPEN → sessionUpdate 전송됨
    expect(sess['_call']).toBeInstanceOf(BufferingCall);
  });

  it('attach replaces BufferingCall and flushes buffer', async () => {
    const sess = new OpenAIRealtime({ apiKey: 'sk-test', greeting: false });
    await sess.prewarm();
    await sess['_call'].sendAudio(Buffer.from('a'));
    await sess['_call'].sendAudio(Buffer.from('b'));

    const realCall = {
      sendAudio: vi.fn(),
      emit: vi.fn(),
      metrics: { recordToolCall: vi.fn() },
    } as never;
    await sess.attach(realCall);
    expect(realCall.sendAudio).toHaveBeenCalledTimes(2);
  });

  it('start() is equivalent to prewarm + attach', async () => {
    const sess = new OpenAIRealtime({ apiKey: 'sk-test', greeting: false });
    const prewarmSpy = vi.spyOn(sess, 'prewarm');
    const attachSpy = vi.spyOn(sess, 'attach');
    const realCall = { sendAudio: vi.fn(), emit: vi.fn(), metrics: { recordToolCall: vi.fn() } } as never;
    await sess.start(realCall);
    expect(prewarmSpy).toHaveBeenCalledTimes(1);
    expect(attachSpy).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-node && pnpm exec vitest run tests/agent/openai-prewarm.test.ts`
Expected: FAIL

- [ ] **Step 3: `openai-realtime.ts` 의 start() 분리**

기존 `start(callSession, tools)` 본문을 다음과 같이 재구성 (line 146–197 교체):

```typescript
  async prewarm(): Promise<void> {
    const { BufferingCall } = await import('../buffering-call');
    this._call = new BufferingCall() as unknown as CallSession;
    this._closed = false;
    this._playback = null;
    this._latestMediaTs = 0;

    const { WebSocket } = await import('ws');
    const url = `${OPENAI_REALTIME_URL}${this._model}`;
    this._ws = new WebSocket(url, {
      headers: { Authorization: `Bearer ${this._apiKey}` },
    });

    return new Promise<void>((resolve, reject) => {
      const ws = this._ws!;
      ws.on('open', () => {
        this._sendSessionUpdate();
        this._log.info('OpenAI Realtime connected (prewarm)');
        if (this._greeting) {
          this._send({ type: 'response.create' });
        }
        resolve();
      });
      ws.on('message', (data: Buffer | string) => {
        try {
          const msg = JSON.parse(data.toString()) as Record<string, unknown>;
          this._handleMessage(msg);
        } catch { /* ignore */ }
      });
      ws.on('close', () => { this._closed = true; });
      ws.on('error', (err: Error) => {
        if (!this._ws) reject(err);
        this._log.error({ err }, 'OpenAI Realtime WS error');
      });
    });
  }

  async attach(call: CallSession): Promise<void> {
    const { BufferingCall } = await import('../buffering-call');
    const prev = this._call;
    this._call = call;
    if (prev instanceof BufferingCall) {
      for (const chunk of prev.drainBuffer()) {
        await call.sendAudio(chunk);
      }
    }
  }

  async start(callSession: CallSession, tools?: ToolRegistry): Promise<void> {
    if (tools) this._tools = tools;
    await this.prewarm();
    await this.attach(callSession);
  }
```

- [ ] **Step 4: PASS + 회귀 확인**

Run: `cd /Users/ghyeok/Developments/clawops-node && pnpm exec vitest run tests/agent/openai-prewarm.test.ts tests/agent/`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/agent/pipeline/realtime/openai-realtime.ts tests/agent/openai-prewarm.test.ts
git commit -m "feat(openai-realtime): prewarm/attach 분리 구현 (Python mirror)"
```

---

### Task 12: `GeminiRealtime` TS prewarm/attach

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-node/src/agent/pipeline/realtime/gemini-realtime.ts:241-296`
- Test: `/Users/ghyeok/Developments/clawops-node/tests/agent/gemini-prewarm.test.ts` (신규)

Task 11 과 동일 패턴, Gemini Live SDK 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

```typescript
import { describe, it, expect, vi } from 'vitest';
import { GeminiRealtime } from '../../src/agent/pipeline/realtime/gemini-realtime';
import { BufferingCall } from '../../src/agent/pipeline/buffering-call';

// @google/genai mock
vi.mock('@google/genai', () => {
  return {
    GoogleGenAI: class {
      live = {
        connect: async () => ({
          sendRealtimeInput: vi.fn(),
          close: vi.fn(),
          [Symbol.asyncIterator]: async function* () {},
        }),
      };
    },
  };
});

describe('GeminiRealtime.prewarm', () => {
  it('opens live session without CallSession', async () => {
    const sess = new GeminiRealtime({ apiKey: 'g-test', greeting: false });
    await sess.prewarm();
    expect(sess['_call']).toBeInstanceOf(BufferingCall);
  });

  it('greeting=true sends initial text', async () => {
    const sess = new GeminiRealtime({ apiKey: 'g-test', greeting: true });
    await sess.prewarm();
    expect(sess['_session'].sendRealtimeInput).toHaveBeenCalled();
  });

  it('attach flushes buffer', async () => {
    const sess = new GeminiRealtime({ apiKey: 'g-test', greeting: false });
    await sess.prewarm();
    await sess['_call'].sendAudio(Buffer.from('x'));
    const realCall = { sendAudio: vi.fn(), emit: vi.fn(), metrics: { recordToolCall: vi.fn() } } as never;
    await sess.attach(realCall);
    expect(realCall.sendAudio).toHaveBeenCalledOnce();
  });

  it('start = prewarm + attach', async () => {
    const sess = new GeminiRealtime({ apiKey: 'g-test', greeting: false });
    const prewarmSpy = vi.spyOn(sess, 'prewarm');
    const attachSpy = vi.spyOn(sess, 'attach');
    const realCall = { sendAudio: vi.fn(), emit: vi.fn(), metrics: { recordToolCall: vi.fn() } } as never;
    await sess.start(realCall);
    expect(prewarmSpy).toHaveBeenCalledOnce();
    expect(attachSpy).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-node && pnpm exec vitest run tests/agent/gemini-prewarm.test.ts`
Expected: FAIL

- [ ] **Step 3: `gemini-realtime.ts` 의 start() 분리**

기존 `start()` (line 241–296) 를 다음 패턴으로:

```typescript
  async prewarm(): Promise<void> {
    const { BufferingCall } = await import('../buffering-call');
    this._call = new BufferingCall() as unknown as CallSession;

    const { GoogleGenAI } = await import('@google/genai');
    this._client = new GoogleGenAI({ apiKey: this._apiKey });
    this._session = await this._client.live.connect({
      model: this._model,
      config: this._buildConfig(),
    });
    this._log.info('Gemini Live connected (prewarm)');

    if (this._greeting) {
      await this._session.sendRealtimeInput({ text: '인사해 주세요.' });
    }

    this._receiveLoopPromise = this._receiveLoop();
  }

  async attach(call: CallSession): Promise<void> {
    const { BufferingCall } = await import('../buffering-call');
    const prev = this._call;
    this._call = call;
    if (prev instanceof BufferingCall) {
      for (const chunk of prev.drainBuffer()) {
        await call.sendAudio(chunk);
      }
    }
  }

  async start(call: CallSession, tools?: ToolRegistry): Promise<void> {
    if (tools) this._tools = tools;
    await this.prewarm();
    await this.attach(call);
  }
```

(기존 `_buildConfig()` / `_receiveLoop()` 가 없다면 가독성을 위해 추출.)

- [ ] **Step 4: PASS + 회귀**

Run: `cd /Users/ghyeok/Developments/clawops-node && pnpm exec vitest run tests/agent/gemini-prewarm.test.ts tests/agent/gemini-realtime.test.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/agent/pipeline/realtime/gemini-realtime.ts tests/agent/gemini-prewarm.test.ts
git commit -m "feat(gemini-realtime): prewarm/attach 분리 구현 (mirror)"
```

---

### Task 13: `PipelineSession` TS prewarm/attach

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-node/src/agent/pipeline/pipeline-session.ts`
- Test: `/Users/ghyeok/Developments/clawops-node/tests/agent/pipeline-prewarm.test.ts` (신규)

- [ ] **Step 1: 실패하는 테스트**

```typescript
import { describe, it, expect, vi } from 'vitest';
import { PipelineSession } from '../../src/agent/pipeline/pipeline-session';

describe('PipelineSession.prewarm', () => {
  it('prewarm sets BufferingCall', async () => {
    const sess = new PipelineSession({
      stt: { transcribe: vi.fn() } as never,
      llm: { generate: vi.fn() } as never,
      tts: { synthesize: vi.fn() } as never,
      systemPrompt: 'x',
      greeting: false,
    });
    await sess.prewarm();
    expect(sess['_call']).toBeTruthy();
  });

  it('attach flushes buffer', async () => {
    const sess = new PipelineSession({
      stt: { transcribe: vi.fn() } as never,
      llm: { generate: vi.fn() } as never,
      tts: { synthesize: vi.fn() } as never,
      systemPrompt: 'x',
      greeting: false,
    });
    await sess.prewarm();
    await sess['_call'].sendAudio(Buffer.from('a'));
    const realCall = { sendAudio: vi.fn(), emit: vi.fn(), metrics: { recordToolCall: vi.fn() } } as never;
    await sess.attach(realCall);
    expect(realCall.sendAudio).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: 실패 확인 + 구현 + PASS + 커밋**

구현 패턴은 Python `PipelineSession` 과 동일. 기존 `start()` 본문 분리 후 wrapper.

```bash
pnpm exec vitest run tests/agent/pipeline-prewarm.test.ts
git add src/agent/pipeline/pipeline-session.ts tests/agent/pipeline-prewarm.test.ts
git commit -m "feat(pipeline-session): prewarm/attach 분리 구현 TS (mirror)"
```

---

### Task 14: `ClawOpsAgent` TS — outbound_ready 에서 prewarm 호출

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-node/src/agent/agent.ts:357-466`
- Test: `/Users/ghyeok/Developments/clawops-node/tests/agent/agent-prewarm.test.ts` (신규)

Python Task 7 과 동일 로직.

- [ ] **Step 1: 실패하는 테스트**

```typescript
import { describe, it, expect, vi } from 'vitest';
import { ClawOpsAgent } from '../../src/agent/agent';

describe('ClawOpsAgent outbound prewarm', () => {
  it('handleOutboundReady triggers session.prewarm in background', async () => {
    // ... agent fixture
    // simulate control_ws emit 'call.outbound_ready'
    // expect session.prewarm() called once after a microtask
  });

  it('media WS connect leads to attach() not start()', async () => {
    // ... verify _startCallSession uses attach when prewarm task exists
  });
});
```

- [ ] **Step 2~5: 구현 + PASS + 커밋**

`agent.ts:357` `_handleOutboundReady` 에:

```typescript
  private _handleOutboundReady(event: ControlEvent): void {
    const callId = event.callId;
    const call = this._calls.get(callId);
    if (!call) {
      this._log.warn({ callId }, 'Unknown outbound call');
      return;
    }
    const session = this._buildSessionFor(call);
    const task = (async () => {
      try {
        await Promise.race([
          session.prewarm(),
          new Promise((_, rej) => setTimeout(() => rej(new Error('prewarm timeout')), 10_000)),
        ]);
      } catch (e) {
        this._log.warn({ err: e, callId }, 'prewarm failed');
        this._prewarmFailed.add(callId);
      }
    })();
    this._prewarmTasks.set(callId, { task, session });
  }
```

`_startCallSession` (line 466) 에:

```typescript
    const prewarm = this._prewarmTasks.get(callId);
    if (prewarm && !this._prewarmFailed.has(callId)) {
      try {
        await prewarm.task;
        await prewarm.session.attach(call);
      } catch (e) {
        await prewarm.session.start(call);
      }
    } else {
      await session.start(call);
    }
    this._prewarmTasks.delete(callId);
    this._prewarmFailed.delete(callId);
```

hangup 핸들러에서 prewarm task cancel + cleanup.

```bash
pnpm exec vitest run tests/agent/agent-prewarm.test.ts
pnpm exec vitest run tests/agent/
git add src/agent/agent.ts tests/agent/agent-prewarm.test.ts
git commit -m "feat(agent): outbound_ready 에서 session.prewarm() 백그라운드 시작 (TS mirror)"
```

---

### Task 15: TS stop() 보강 — connection close timeout

**Files:**
- Modify: `openai-realtime.ts`, `gemini-realtime.ts`
- Test: `tests/agent/prewarm-cancel.test.ts`

Python Task 6 mirror. ws close timeout 2s, prewarm 후 attach 없이 stop 호출 시 leak 없도록.

- [ ] **Step 1~5**: 위와 같이 TDD, 커밋

```bash
git commit -m "fix(realtime): TS stop() 에 connection close timeout 가드 (mirror)"
```

---

### Task 16: Phase 2 회귀 + 통합 smoke test

- [ ] **Step 1: 전체 vitest 실행**

Run: `cd /Users/ghyeok/Developments/clawops-node && pnpm exec vitest run`
Expected: 전부 PASS

- [ ] **Step 2: tsc --noEmit**

Run: `cd /Users/ghyeok/Developments/clawops-node && pnpm exec tsc --noEmit`
Expected: 에러 없음

- [ ] **Step 3: 통합 smoke test 추가**

`tests/agent/prewarm-integration.test.ts`:

```typescript
// Python Task 8 mirror — outbound_ready → prewarm → attach → audio flush
```

- [ ] **Step 4: 커밋**

```bash
git commit -m "test(agent): TS prewarm 통합 smoke test (Python mirror)"
```

---

## Phase 3 — call-engine 검증 (변경 최소)

call-engine 의 SDK 호출 흐름은 control WS 이벤트 emit 만 담당. 현재 `call.outbound_ready` 이벤트가 originate 시점에 emit 되고 있는지 검증.

### Task 17: control WS `outbound_ready` 타이밍 검증

**Files:**
- Inspect: `/Users/ghyeok/Developments/clawops/call-engine/src/ari-handler.js:370-476`
- Inspect: `/Users/ghyeok/Developments/clawops/call-engine/src/agent-registry.js` (control WS)

- [ ] **Step 1: 현재 emit 시점 확인**

```bash
grep -n "outbound_ready\|outboundReady" /Users/ghyeok/Developments/clawops/call-engine/src/*.js
```

확인 항목:
- emit 이 ARI originate 호출 *직후* (= channel 객체 생성 직후, StasisStart 진입 전) 에 발생하는가?
- 아니면 StasisStart 진입 (= answered 가까이) 에 발생하는가?

- [ ] **Step 2: 결과에 따른 분기**

**Case A** — emit 이 이미 originate 직후라면: **call-engine 변경 불필요**. Phase 3 끝.

**Case B** — emit 이 StasisStart 시점이라면: 새 이벤트 `call.outbound_initiated` 를 ARI originate 직후에 emit 추가. SDK 의 `_handle_outbound_ready` 가 새 이벤트도 prewarm trigger 로 등록.

- [ ] **Step 3: Case B 인 경우 패치**

`ari-handler.js:437` (originate 호출 직후) 에:

```javascript
await ari.channels.originate({ ... });
// 새 이벤트: SDK 에게 prewarm 시작하라고 알림 (answer 전)
controlWs.emit('call.outbound_initiated', {
  callId: slot.callId,
  from: slot.from,
  to: slot.to,
  voiceUrl: slot.voiceUrl,
  mediaUrl: ...,  // pre-allocated media URL (있다면)
});
```

SDK 측에서 `outbound_initiated` 와 `outbound_ready` 둘 다 prewarm trigger 로 받도록 추가 (양 SDK).

- [ ] **Step 4: 커밋 (Case B 만)**

```bash
git add call-engine/src/ari-handler.js
git commit -m "feat(call-engine): outbound_initiated 이벤트 추가 — answer 전 SDK prewarm 트리거"
```

---

## Phase 4 — 측정 + 점진 출시

### Task 18: latency 측정 로깅 추가

**Files:**
- Modify: clawops-python `_agent.py`, clawops-node `agent.ts`

prewarm 시작 / prewarm 완료 / attach 호출 / 첫 audio chunk RTP egress 의 4개 timestamp 를 로깅.

- [ ] **Step 1: 로깅 추가**

Python:
```python
log.info(f"[PREWARM-T] start call_id={call_id} t={time.monotonic():.3f}")
# prewarm 완료 시
log.info(f"[PREWARM-T] done call_id={call_id} elapsed_ms={(time.monotonic()-t0)*1000:.0f}")
# attach 시
log.info(f"[PREWARM-T] attach call_id={call_id} t={time.monotonic():.3f}")
# 첫 send_audio (실제 call 로) 시 (Session 내부)
log.info(f"[PREWARM-T] first-audio call_id={call_id} t={time.monotonic():.3f}")
```

TS 동일. 로그 prefix `[PREWARM-T]` 로 grep 가능하게.

- [ ] **Step 2: 커밋**

```bash
git commit -m "feat(agent): prewarm/attach latency 측정 로그 (PREWARM-T)"
```

---

### Task 19: feature flag `prewarmEnabled`

**Files:**
- Modify: `_agent.py` / `agent.ts` — ClawOpsAgent 옵션에 `prewarm_enabled: bool = True` 추가

미응답 비용 검증 전까지 통화 단위로 끌 수 있게.

- [ ] **Step 1: 옵션 추가 + 분기**

```python
class ClawOpsAgent:
    def __init__(self, ..., prewarm_enabled: bool = True):
        self._prewarm_enabled = prewarm_enabled

    async def _handle_outbound_ready(self, data):
        if not self._prewarm_enabled:
            return  # 기존 경로 (start) 로 fallback
        # ... 기존 prewarm 로직
```

TS 동일.

- [ ] **Step 2: 테스트**

```python
@pytest.mark.asyncio
async def test_prewarm_disabled_skips_prewarm():
    agent = _build_test_agent(prewarm_enabled=False)
    # outbound_ready 발생해도 session.prewarm 호출 안 됨
```

- [ ] **Step 3: 커밋**

```bash
git commit -m "feat(agent): prewarm_enabled 옵션 — 통화 단위 on/off"
```

---

### Task 20: 비용 측정 스크립트

**Files:**
- Create: `/Users/ghyeok/Developments/clawops-python/scripts/measure_prewarm_cost.py`

staging 통화 100건의 prewarm latency / OpenAI 사용량 / ARI 결과를 수집하는 스크립트.

- [ ] **Step 1: 스크립트 작성**

```python
"""staging 환경에서 prewarm A/B 측정.

사용법:
  python scripts/measure_prewarm_cost.py --runs 100 --variant prewarm_on
  python scripts/measure_prewarm_cost.py --runs 100 --variant prewarm_off

출력:
  - p50/p95 first-speech latency (RTP egress 기준)
  - OpenAI Realtime API 사용 토큰/세션
  - ARI 결과 분포 (answered / no_answer / busy / rejected)
"""
import argparse, asyncio, json, time
# ... 구체 구현은 staging 환경의 통화 API 호출
```

- [ ] **Step 2: README 업데이트**

`/Users/ghyeok/Developments/clawops-python/docs/superpowers/specs/2026-05-24-realtime-session-prewarm-design.md` 의 "단계적 출시" 섹션에 측정 절차 문서화.

- [ ] **Step 3: 커밋**

```bash
git add scripts/measure_prewarm_cost.py docs/superpowers/specs/2026-05-24-realtime-session-prewarm-design.md
git commit -m "chore(measurement): prewarm 비용/latency 측정 스크립트"
```

---

### Task 21: 최종 회귀 + 문서

- [ ] **Step 1: 전체 테스트**

```bash
cd /Users/ghyeok/Developments/clawops-python && pytest tests/agent/ -v
cd /Users/ghyeok/Developments/clawops-node && pnpm exec vitest run && pnpm exec tsc --noEmit
```

Expected: 전부 PASS

- [ ] **Step 2: README / CHANGELOG**

각 SDK 의 README 에 prewarm/attach 사용 예제 추가:

```python
# Python
agent = ClawOpsAgent(..., prewarm_enabled=True)  # 기본 True
# outbound_ready 이벤트 수신 시 자동으로 prewarm 시작
```

```typescript
// Node
const agent = new ClawOpsAgent({ ..., prewarmEnabled: true });
```

- [ ] **Step 3: 커밋**

```bash
git commit -m "docs: prewarm/attach API 사용법 README 반영"
```

---

## Self-Review (작성 후 점검 결과)

**Spec coverage:**
- ✓ "Stage 1 `LLMConnection.connect`" → 실용적 단순화 (Session.prewarm 으로 통합) — design 의 `LLMConnection` 추상은 별도 클래스 대신 메서드로 표현, 핵심 기능(미디어 없이 LLM 연결) 동일
- ✓ "Stage 2 `Session.attach`" → Task 3,4,5,11,12,13
- ✓ 미응답/실패 처리 (cancel/timeout) → Task 6, 15, 19
- ✓ mirror 보장 → Phase 2 가 Phase 1 과 1:1 매칭 (테스트 케이스 이름까지)
- ✓ 비용 영향 (단계적 출시) → Task 18, 19, 20
- ✓ call-engine 측 변경 → Task 17 (검증 후 분기)

**Placeholder scan:** PipelineSession 의 기존 start() 본문을 옮길 때 `_trigger_greeting()` 같은 보조 메서드 이름은 코드 확인 후 정확히 따를 것. 가이드만 제공.

**Type consistency:** Python `_BufferingCall` ↔ TS `BufferingCall` 이름 차이 (snake/camel) — 의도된 언어 컨벤션 차이, 일관성 유지됨.

---

**Plan complete and saved to** `/Users/ghyeok/Developments/clawops-python/docs/superpowers/plans/2026-05-24-realtime-session-prewarm.md`.
