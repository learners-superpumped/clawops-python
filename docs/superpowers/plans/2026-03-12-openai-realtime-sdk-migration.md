# OpenAI Realtime SDK Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_openai_realtime.py`를 `aiohttp` 직접 WebSocket에서 `openai` Python SDK의 `AsyncOpenAI.realtime.connect()`로 마이그레이션하고, `openai-realtime`/`openai-llm` dependency를 `openai`로 통합한다.

**Architecture:** `AsyncOpenAI` 클라이언트의 `realtime.connect()` → `.enter()` 패턴으로 연결을 수동 관리. SDK typed 이벤트로 송수신. `aiohttp` 의존은 `_openai_realtime.py`에서만 제거되며 `agent` base에는 유지.

**Tech Stack:** `openai>=1.76.0` (AsyncOpenAI, realtime.connect), Python asyncio

**Spec:** `docs/superpowers/specs/2026-03-12-openai-realtime-sdk-migration-design.md`

**Note:** Tasks 2-7은 하나의 atomic migration chunk로, 중간 커밋 상태에서 코드가 비정상일 수 있다. 반드시 Task 7까지 완료 후 통합 테스트를 수행할 것.

---

## Chunk 1: Dependencies & Core Migration

### Task 1: Update pyproject.toml dependencies

**Files:**
- Modify: `pyproject.toml:55-56,72-74`

- [ ] **Step 1: Replace openai-realtime and openai-llm with unified openai extra**

```toml
# Replace lines 55-56:
# openai-realtime = ["clawops[agent]"]
# openai-llm = ["clawops[agent]", "openai>=1.0.0"]
# With:
openai = ["clawops[agent]", "openai>=1.76.0"]
```

- [ ] **Step 2: Update agent-all to use unified openai extra**

```toml
# Replace in agent-all (lines 72-74):
# "clawops[openai-realtime]",
# "clawops[openai-llm]",
# With:
# "clawops[openai]",
```

- [ ] **Step 3: Verify dependency resolution**

Run: `cd /Users/ghyeok/Developments/clawops-python && pip install -e ".[openai]"`
Expected: Successfully installs openai>=1.76.0

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: consolidate openai-realtime and openai-llm into single openai extra"
```

---

### Task 2: Migrate _openai_realtime.py — imports and __init__

**Files:**
- Modify: `src/clawops/agent/pipeline/_openai_realtime.py:1-136`

- [ ] **Step 1: Write test for new init with AsyncOpenAI client**

Add to `tests/agent/test_realtime_session.py`:

```python
def test_openai_realtime_init_creates_client():
    """AsyncOpenAI 클라이언트가 올바르게 생성되는지 확인."""
    session = OpenAIRealtime(
        api_key="sk-test",
        system_prompt="test",
    )
    assert session._config.openai_api_key == "sk-test"
    # aiohttp 관련 속성이 없어야 함
    assert not hasattr(session, '_http')
    # connection은 start() 전이므로 None
    assert session._connection is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/test_realtime_session.py::test_openai_realtime_init_creates_client -v`
Expected: FAIL — `_connection` attribute not found

- [ ] **Step 3: Update imports and __init__**

Replace the imports section (lines 1-27) with:

```python
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
from openai.resources.realtime.realtime import AsyncRealtimeConnection

from .._audio import ulaw_to_pcm16
from .._builtin_tools import BuiltinTool
from .._recorder import AudioRecorder
from .._session import CallSession
from .._tool import ToolRegistry
from ..tracing._spans import tool_call_span, llm_session_span

log = logging.getLogger("clawops.agent")
```

Update `__init__` to replace `aiohttp` state with SDK state:

```python
# Remove these from __init__:
#   self._ws: aiohttp.ClientWebSocketResponse | None = None
#   self._http: aiohttp.ClientSession | None = None
# Add:
    self._client: AsyncOpenAI | None = None
    self._connection: AsyncRealtimeConnection | None = None
```

Remove `OPENAI_REALTIME_URL` constant.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/test_realtime_session.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/clawops/agent/pipeline/_openai_realtime.py tests/agent/test_realtime_session.py
git commit -m "refactor(openai-realtime): replace aiohttp imports with openai SDK"
```

---

### Task 3: Migrate start() method

**Files:**
- Modify: `src/clawops/agent/pipeline/_openai_realtime.py` — `start()` method

- [ ] **Step 1: Rewrite start() to use SDK connect**

Replace the current `start()` method (the WebSocket connection and session.update part) with:

```python
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
    _use_hangup = self._builtin_tools is None or BuiltinTool.HANG_UP in self._builtin_tools
    if _use_hangup:
        tool_schemas.append(HANG_UP_TOOL)
    if self._builtin_tools is None or BuiltinTool.COLLECT_DTMF in self._builtin_tools:
        tool_schemas.append(COLLECT_DTMF_TOOL)
    if self._builtin_tools is None or BuiltinTool.SEND_DTMF in self._builtin_tools:
        tool_schemas.append(SEND_DTMF_TOOL)

    await self._connection.session.update(
        session={
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
        }
    )

    if self._config.greeting:
        await self._connection.response.create()

    self._tasks.append(asyncio.create_task(self._receive_loop()))
```

- [ ] **Step 2: Verify no syntax errors**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -c "from clawops.agent.pipeline._openai_realtime import OpenAIRealtime; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/clawops/agent/pipeline/_openai_realtime.py
git commit -m "refactor(openai-realtime): migrate start() to SDK connect"
```

---

### Task 4: Migrate feed_audio() and feed_dtmf()

**Files:**
- Modify: `src/clawops/agent/pipeline/_openai_realtime.py` — `feed_audio()`, `feed_dtmf()`

- [ ] **Step 1: Rewrite feed_audio()**

```python
async def feed_audio(self, audio: bytes, timestamp: int) -> None:
    self._latest_media_ts = timestamp
    if self._connection:
        await self._connection.input_audio_buffer.append(
            audio=base64.b64encode(audio).decode(),
        )
```

- [ ] **Step 2: Rewrite feed_dtmf()**

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add src/clawops/agent/pipeline/_openai_realtime.py
git commit -m "refactor(openai-realtime): migrate feed_audio/feed_dtmf to SDK methods"
```

---

### Task 5: Migrate _receive_loop() and _handle_event()

**Files:**
- Modify: `src/clawops/agent/pipeline/_openai_realtime.py` — `_receive_loop()`, `_handle_event()`

- [ ] **Step 1: Rewrite _receive_loop()**

```python
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
```

- [ ] **Step 2: Rewrite _handle_event() to use typed events**

```python
async def _handle_event(self, event: Any) -> None:
    if not self._call:
        return
    event_type = event.type

    if event_type == "response.audio.delta":
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

    elif event_type == "response.audio.done":
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
            await self._handle_tool_call(item)

    elif event_type == "conversation.item.input_audio_transcription.completed":
        await self._call._emit("transcript", "user", event.transcript or "")

    elif event_type == "response.audio_transcript.done":
        await self._call._emit("transcript", "assistant", event.transcript or "")

    elif event_type == "error":
        log.error(f"OpenAI error: {event.error}")
```

- [ ] **Step 3: Commit**

```bash
git add src/clawops/agent/pipeline/_openai_realtime.py
git commit -m "refactor(openai-realtime): migrate receive loop and event handling to SDK typed events"
```

---

### Task 6: Migrate _handle_tool_call()

**Files:**
- Modify: `src/clawops/agent/pipeline/_openai_realtime.py` — `_handle_tool_call()`

- [ ] **Step 1: Rewrite _handle_tool_call() to use typed item and SDK methods**

```python
async def _handle_tool_call(self, item: Any) -> None:
    func_name = item.name or ""
    call_id = item.call_id or ""
    log.info(f"Tool call: {func_name}({item.arguments})")

    if func_name == "hang_up":
        if self._call:
            await self._call.hangup()
        return

    if func_name == "collect_dtmf":
        if self._call and self._connection:
            try:
                args = json.loads(item.arguments or "{}")
                result = await self._call.collect_dtmf(
                    max_digits=args.get("max_digits", 4),
                    finish_on_key=args.get("finish_on_key", "#"),
                    timeout=args.get("timeout", 5),
                )
            except Exception as e:
                result = f"Error: {e}"
            await self._connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result if result else "(타임아웃 - 입력 없음)",
                }
            )
            await self._connection.response.create()
        return

    if func_name == "send_dtmf":
        if self._call and self._connection:
            try:
                args = json.loads(item.arguments or "{}")
                await self._call.send_dtmf_sequence(args.get("digits", ""))
                result = "sent"
            except Exception as e:
                result = f"Error: {e}"
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

    source = "mcp" if func_name in self._tools._mcp_tools else "local"

    with tool_call_span(func_name, source):
        try:
            args = json.loads(item.arguments or "{}")
            result = await self._tools.call(func_name, args)
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
```

- [ ] **Step 2: Commit**

```bash
git add src/clawops/agent/pipeline/_openai_realtime.py
git commit -m "refactor(openai-realtime): migrate _handle_tool_call to SDK methods"
```

---

### Task 7: Migrate _handle_truncation(), stop(), _cleanup()

**Files:**
- Modify: `src/clawops/agent/pipeline/_openai_realtime.py` — `_handle_truncation()`, `stop()`, `_cleanup()`, remove `_send()`

- [ ] **Step 1: Rewrite _handle_truncation()**

```python
async def _handle_truncation(self) -> None:
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
```

- [ ] **Step 2: Rewrite stop() and _cleanup(), add _close_llm_span(), remove _send()**

```python
async def stop(self) -> None:
    # 1) 연결 닫기 → receive loop의 async for가 자연 종료
    if self._connection:
        await self._connection.close()
    # 2) 남은 태스크 정리
    for task in self._tasks:
        if not task.done():
            task.cancel()
    self._tasks.clear()
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
```

Remove the `_send()` method entirely.

- [ ] **Step 3: Verify no syntax errors**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -c "from clawops.agent.pipeline._openai_realtime import OpenAIRealtime; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Run all existing tests**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/test_realtime_session.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/clawops/agent/pipeline/_openai_realtime.py
git commit -m "refactor(openai-realtime): migrate truncation/stop/cleanup, remove _send()"
```

---

## Chunk 2: Documentation Updates

### Task 8: Update clawops-python README.md

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/README.md:18`

- [ ] **Step 1: Update pip install line**

```markdown
# Change line 18 from:
pip install clawops[agent,openai-llm,deepgram,elevenlabs,mcp]
# To:
pip install clawops[agent,openai,deepgram,elevenlabs,mcp]
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README install instructions for unified openai extra"
```

---

### Task 9: Update clawops-python quickstart.md

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/docs/agent/quickstart.md:7-10`

- [ ] **Step 1: Update install instructions**

```markdown
# Change line 7 from:
# 기본 (OpenAI Realtime 모드)
pip install clawops[agent]
# To:
# 기본 (OpenAI Realtime 모드)
pip install clawops[agent,openai]

# Change line 10 from:
pip install clawops[agent,deepgram,elevenlabs,openai-llm]    # OpenAI LLM
# To:
pip install clawops[agent,deepgram,elevenlabs,openai]    # OpenAI LLM
```

- [ ] **Step 2: Commit**

```bash
git add docs/agent/quickstart.md
git commit -m "docs: update quickstart install instructions for unified openai extra"
```

---

### Task 10: Update clawops web docs (voice-agent/index.mdx)

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops/web/content/docs/voice-agent/index.mdx:38,44`

- [ ] **Step 1: Update install instructions**

```markdown
# Line 38: Change from:
# OpenAIRealtime — OpenAI Realtime API 기반
pip install clawops[agent]
# To:
# OpenAIRealtime — OpenAI Realtime API 기반
pip install clawops[agent,openai]

# Line 44: Change from:
pip install clawops[agent,deepgram,elevenlabs,openai-llm]
# To:
pip install clawops[agent,deepgram,elevenlabs,openai]
```

- [ ] **Step 2: Commit**

```bash
cd /Users/ghyeok/Developments/clawops
git add web/content/docs/voice-agent/index.mdx
git commit -m "docs: update voice agent install instructions for unified openai extra"
```

---

### Task 11: Final verification

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/ -v`
Expected: ALL PASS

- [ ] **Step 2: Verify imports work end-to-end**

Run:
```bash
cd /Users/ghyeok/Developments/clawops-python && python -c "
from clawops.agent.pipeline._openai_realtime import OpenAIRealtime, OpenAIRealtimeConfig
from clawops.agent.plugins.openai_realtime import RealtimeSession, RealtimeConfig
from clawops.agent.pipeline import OpenAIRealtime as OR2
assert RealtimeSession is OpenAIRealtime
assert RealtimeConfig is OpenAIRealtimeConfig
assert OR2 is OpenAIRealtime
print('All imports OK')
"
```
Expected: `All imports OK`

- [ ] **Step 3: Verify no aiohttp references remain in _openai_realtime.py**

Run: `grep -n 'aiohttp' /Users/ghyeok/Developments/clawops-python/src/clawops/agent/pipeline/_openai_realtime.py`
Expected: No output (no matches)
