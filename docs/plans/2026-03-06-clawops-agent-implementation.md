# ClawOps Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** ClawOps Python SDK에 AI Agent 모듈을 추가하여 `ClawOpsAgent.listen()` 한 줄로 인바운드 전화를 수신하고 AI로 처리

**Architecture:** aiohttp WebSocket 클라이언트가 ClawOps 서버에 역방향 연결(Control WS + per-call Media WS). 기존 `AsyncClawOps` 클라이언트 재사용. OpenAI Realtime API 내장 + 플러그인 파이프라인(STT/LLM/TTS) 지원.

**Tech Stack:** Python 3.9+, aiohttp (WebSocket), 기존 clawops SDK, pytest, pytest-asyncio

**Design Doc:** `docs/plans/2026-03-06-clawops-agent-design.md`

**Existing Code Reference:**
- REST SDK: `src/clawops/` (구현 완료)
- AI Agent 로직: `../ai-agent/session_manager.py` (참고용)
- Stream 프로토콜: `../clawops/app/src/stream-handler.js`
- G.711 코덱: `../ai-agent/g711.py`

---

### Task 1: pyproject.toml에 agent optional dependencies 추가

**Files:**
- Modify: `pyproject.toml`

**Step 1: pyproject.toml에 optional dependencies 추가**

`[project.optional-dependencies]` 섹션에 추가:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "respx>=0.20",
    "mypy>=1.0",
    "ruff>=0.1",
    "aiohttp>=3.9.0,<4",
]

# Agent
agent = ["aiohttp>=3.9.0,<4"]
openai-realtime = ["clawops[agent]"]
openai-llm = ["clawops[agent]", "openai>=1.0.0"]
deepgram = ["clawops[agent]", "deepgram-sdk>=3.0.0"]
elevenlabs = ["clawops[agent]", "elevenlabs>=1.0.0"]
google-tts = ["clawops[agent]", "google-cloud-texttospeech>=2.0.0"]
mcp = ["clawops[agent]", "mcp>=1.0.0"]
agent-all = [
    "clawops[openai-realtime]",
    "clawops[openai-llm]",
    "clawops[deepgram]",
    "clawops[elevenlabs]",
    "clawops[mcp]",
]
```

**Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add agent optional dependencies to pyproject.toml"
```

---

### Task 2: Agent 에러 클래스 추가

**Files:**
- Modify: `src/clawops/_exceptions.py`
- Test: `tests/test_agent_exceptions.py`

**Step 1: 테스트 작성**

```python
# tests/test_agent_exceptions.py
from clawops._exceptions import AgentError, AgentConnectionError


def test_agent_error_is_clawops_error():
    from clawops._exceptions import ClawOpsError
    err = AgentError("test")
    assert isinstance(err, ClawOpsError)


def test_agent_connection_error_is_agent_error():
    err = AgentConnectionError("ws failed")
    assert isinstance(err, AgentError)
    assert str(err) == "ws failed"
```

**Step 2: 테스트 실행하여 실패 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/test_agent_exceptions.py -v`
Expected: FAIL (ImportError)

**Step 3: 구현**

`src/clawops/_exceptions.py` 하단에 추가:

```python
class AgentError(ClawOpsError):
    """Agent 관련 에러의 베이스 클래스."""


class AgentConnectionError(AgentError):
    """Agent WebSocket 연결 실패."""
```

**Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_agent_exceptions.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clawops/_exceptions.py tests/test_agent_exceptions.py
git commit -m "feat: add AgentError and AgentConnectionError"
```

---

### Task 3: G.711 오디오 변환 모듈

`../ai-agent/g711.py`를 SDK에 포팅.

**Files:**
- Create: `src/clawops/agent/__init__.py`
- Create: `src/clawops/agent/_audio.py`
- Test: `tests/agent/__init__.py`
- Test: `tests/agent/test_audio.py`

**Step 1: 테스트 작성**

```python
# tests/agent/__init__.py
# (empty)
```

```python
# tests/agent/test_audio.py
import struct

from clawops.agent._audio import pcm16_to_ulaw, ulaw_to_pcm16


def test_roundtrip_silence():
    """무음(0x00)은 변환 후 근사적으로 유지."""
    silence = b"\x00\x00" * 160  # 160 samples = 20ms at 8kHz
    ulaw = pcm16_to_ulaw(silence)
    assert len(ulaw) == 160
    back = ulaw_to_pcm16(ulaw)
    assert len(back) == 320
    # 무음 근사 확인: 모든 샘플이 -8~8 범위
    samples = struct.unpack(f"<{len(back)//2}h", back)
    assert all(-8 <= s <= 8 for s in samples)


def test_roundtrip_tone():
    """사인파 유사 패턴의 왕복 변환 확인."""
    import math
    samples = [int(16000 * math.sin(2 * math.pi * 440 * i / 8000)) for i in range(160)]
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    ulaw = pcm16_to_ulaw(pcm)
    back = ulaw_to_pcm16(ulaw)
    back_samples = struct.unpack(f"<{len(back)//2}h", back)
    # ulaw 양자화 오차 허용 (원본 대비 5% 이내)
    for orig, decoded in zip(samples, back_samples):
        if abs(orig) > 100:
            assert abs(orig - decoded) / abs(orig) < 0.05


def test_empty_input():
    assert pcm16_to_ulaw(b"") == b""
    assert ulaw_to_pcm16(b"") == b""
```

**Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/agent/test_audio.py -v`
Expected: FAIL (ImportError)

**Step 3: 모듈 구조 생성 + 구현**

```python
# src/clawops/agent/__init__.py
"""ClawOps Agent - AI 음성 에이전트 프레임워크."""
```

```python
# src/clawops/agent/_audio.py
"""G.711 mu-law codec: PCM16 (signed 16-bit LE) <-> ulaw 변환.

ClawOps Stream 프로토콜은 PCM16 8kHz를 사용하고,
OpenAI Realtime API는 g711_ulaw 포맷을 사용한다.
"""
from __future__ import annotations

import struct

# ─── Encode: PCM16 -> ulaw (ITU-T G.711) ──────────────────────────────

_BIAS = 0x84
_CLIP = 32635
_EXP_TABLE = [
    0, 0, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3,
    4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
]


def _encode_sample(sample: int) -> int:
    sign = (sample >> 8) & 0x80
    if sign:
        sample = -sample
    if sample > _CLIP:
        sample = _CLIP
    sample += _BIAS
    exp = _EXP_TABLE[(sample >> 7) & 0xFF]
    mantissa = (sample >> (exp + 3)) & 0x0F
    return ~(sign | (exp << 4) | mantissa) & 0xFF


_ENCODE_TABLE = bytes(
    _encode_sample(i if i < 32768 else i - 65536) for i in range(65536)
)

_DECODE_TABLE = (
    -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
    -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
    -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
    -11900, -11388, -10876, -10364,  -9852,  -9340,  -8828,  -8316,
     -7932,  -7676,  -7420,  -7164,  -6908,  -6652,  -6396,  -6140,
     -5884,  -5628,  -5372,  -5116,  -4860,  -4604,  -4348,  -4092,
     -3900,  -3772,  -3644,  -3516,  -3388,  -3260,  -3132,  -3004,
     -2876,  -2748,  -2620,  -2492,  -2364,  -2236,  -2108,  -1980,
     -1884,  -1820,  -1756,  -1692,  -1628,  -1564,  -1500,  -1436,
     -1372,  -1308,  -1244,  -1180,  -1116,  -1052,   -988,   -924,
      -876,   -844,   -812,   -780,   -748,   -716,   -684,   -652,
      -620,   -588,   -556,   -524,   -492,   -460,   -428,   -396,
      -372,   -356,   -340,   -324,   -308,   -292,   -276,   -260,
      -244,   -228,   -212,   -196,   -180,   -164,   -148,   -132,
      -120,   -112,   -104,    -96,    -88,    -80,    -72,    -64,
       -56,    -48,    -40,    -32,    -24,    -16,     -8,      0,
     32124,  31100,  30076,  29052,  28028,  27004,  25980,  24956,
     23932,  22908,  21884,  20860,  19836,  18812,  17788,  16764,
     15996,  15484,  14972,  14460,  13948,  13436,  12924,  12412,
     11900,  11388,  10876,  10364,   9852,   9340,   8828,   8316,
      7932,   7676,   7420,   7164,   6908,   6652,   6396,   6140,
      5884,   5628,   5372,   5116,   4860,   4604,   4348,   4092,
      3900,   3772,   3644,   3516,   3388,   3260,   3132,   3004,
      2876,   2748,   2620,   2492,   2364,   2236,   2108,   1980,
      1884,   1820,   1756,   1692,   1628,   1564,   1500,   1436,
      1372,   1308,   1244,   1180,   1116,   1052,    988,    924,
       876,    844,    812,    780,    748,    716,    684,    652,
       620,    588,    556,    524,    492,    460,    428,    396,
       372,    356,    340,    324,    308,    292,    276,    260,
       244,    228,    212,    196,    180,    164,    148,    132,
       120,    112,    104,     96,     88,     80,     72,     64,
        56,     48,     40,     32,     24,     16,      8,      0,
)


def pcm16_to_ulaw(pcm16: bytes) -> bytes:
    if not pcm16:
        return b""
    n = len(pcm16) // 2
    samples = struct.unpack(f"<{n}h", pcm16)
    return bytes(_ENCODE_TABLE[s & 0xFFFF] for s in samples)


def ulaw_to_pcm16(ulaw: bytes) -> bytes:
    if not ulaw:
        return b""
    samples = [_DECODE_TABLE[b] for b in ulaw]
    return struct.pack(f"<{len(samples)}h", *samples)
```

**Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/agent/test_audio.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clawops/agent/__init__.py src/clawops/agent/_audio.py tests/agent/
git commit -m "feat: add G.711 mu-law audio codec for agent"
```

---

### Task 4: Tool Registry + function_tool 데코레이터

**Files:**
- Create: `src/clawops/agent/_tool.py`
- Test: `tests/agent/test_tool.py`

**Step 1: 테스트 작성**

```python
# tests/agent/test_tool.py
import pytest
from clawops.agent._tool import ToolRegistry


def test_function_tool_decorator():
    registry = ToolRegistry()

    @registry.register
    async def get_weather(city: str, unit: str = "celsius") -> str:
        """도시의 날씨를 조회합니다."""
        return f"{city}: 20 {unit}"

    assert "get_weather" in registry
    tool = registry["get_weather"]
    assert tool.name == "get_weather"
    assert tool.description == "도시의 날씨를 조회합니다."


def test_tool_schema_generation():
    registry = ToolRegistry()

    @registry.register
    async def check_order(order_id: str) -> str:
        """주문 상태를 확인합니다."""
        return "delivered"

    schemas = registry.to_openai_tools()
    assert len(schemas) == 1
    schema = schemas[0]
    assert schema["type"] == "function"
    assert schema["name"] == "check_order"
    assert schema["description"] == "주문 상태를 확인합니다."
    params = schema["parameters"]
    assert params["type"] == "object"
    assert "order_id" in params["properties"]
    assert params["properties"]["order_id"]["type"] == "string"
    assert params["required"] == ["order_id"]


@pytest.mark.asyncio
async def test_tool_execution():
    registry = ToolRegistry()

    @registry.register
    async def add(a: int, b: int) -> str:
        """두 수를 더합니다."""
        return str(a + b)

    result = await registry.call("add", {"a": 3, "b": 5})
    assert result == "8"


@pytest.mark.asyncio
async def test_tool_not_found():
    registry = ToolRegistry()
    with pytest.raises(KeyError):
        await registry.call("nonexistent", {})


def test_tool_with_optional_params():
    registry = ToolRegistry()

    @registry.register
    async def search(query: str, limit: int = 10) -> str:
        """검색합니다."""
        return f"{query}:{limit}"

    schemas = registry.to_openai_tools()
    params = schemas[0]["parameters"]
    assert params["required"] == ["query"]
    assert "limit" in params["properties"]
```

**Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/agent/test_tool.py -v`
Expected: FAIL

**Step 3: 구현**

```python
# src/clawops/agent/_tool.py
"""function_tool 데코레이터와 ToolRegistry.

OpenAI Realtime API의 tool 스키마를 자동 생성하고,
등록된 핸들러를 이름으로 호출한다.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Awaitable


_PY_TYPE_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


@dataclass
class FunctionTool:
    name: str
    description: str
    parameters: dict[str, Any]
    required: list[str]
    handler: Callable[..., Awaitable[str]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, FunctionTool] = {}

    def register(self, fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        sig = inspect.signature(fn)
        hints = {k: v for k, v in inspect.get_annotations(fn).items() if k != "return"}

        properties: dict[str, Any] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            py_type = hints.get(param_name, str)
            json_type = _PY_TYPE_TO_JSON.get(py_type, "string")
            properties[param_name] = {"type": json_type}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        tool = FunctionTool(
            name=fn.__name__,
            description=(fn.__doc__ or "").strip(),
            parameters=properties,
            required=required,
            handler=fn,
        )
        self._tools[fn.__name__] = tool
        return fn

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __getitem__(self, name: str) -> FunctionTool:
        return self._tools[name]

    def to_openai_tools(self) -> list[dict[str, Any]]:
        result = []
        for tool in self._tools.values():
            result.append({
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": tool.parameters,
                    "required": tool.required,
                },
            })
        return result

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        tool = self._tools[name]
        sig = inspect.signature(tool.handler)
        hints = {k: v for k, v in inspect.get_annotations(tool.handler).items() if k != "return"}
        converted = {}
        for k, v in arguments.items():
            target_type = hints.get(k, str)
            try:
                converted[k] = target_type(v)
            except (ValueError, TypeError):
                converted[k] = v
        return await tool.handler(**converted)


def function_tool(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
    """Standalone decorator (ClawOpsAgent 없이 사용 시). 실제로는 @agent.tool 권장."""
    return fn
```

**Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/agent/test_tool.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clawops/agent/_tool.py tests/agent/test_tool.py
git commit -m "feat: add ToolRegistry with function_tool decorator"
```

---

### Task 5: CallSession (per-call 상태 관리)

**Files:**
- Create: `src/clawops/agent/_session.py`
- Test: `tests/agent/test_session.py`

**Step 1: 테스트 작성**

```python
# tests/agent/test_session.py
import pytest
from unittest.mock import AsyncMock
from clawops.agent._session import CallSession


def test_session_creation():
    session = CallSession(
        call_id="CA_test123",
        from_number="01012345678",
        to_number="07012341234",
        account_id="AC_test",
    )
    assert session.call_id == "CA_test123"
    assert session.from_number == "01012345678"
    assert session.to_number == "07012341234"
    assert session.metadata == {}


@pytest.mark.asyncio
async def test_session_send_audio():
    session = CallSession(
        call_id="CA_test",
        from_number="010",
        to_number="070",
        account_id="AC",
    )
    mock_sender = AsyncMock()
    session._send_audio_fn = mock_sender

    await session.send_audio(b"\x00\x00" * 160)
    mock_sender.assert_called_once_with(b"\x00\x00" * 160)


@pytest.mark.asyncio
async def test_session_audio_stream():
    session = CallSession(
        call_id="CA_test",
        from_number="010",
        to_number="070",
        account_id="AC",
    )
    await session._push_audio(b"chunk1")
    await session._push_audio(b"chunk2")
    session._audio_done()

    chunks = []
    async for chunk in session.audio_stream():
        chunks.append(chunk)
    assert chunks == [b"chunk1", b"chunk2"]


@pytest.mark.asyncio
async def test_session_events():
    session = CallSession(
        call_id="CA_test",
        from_number="010",
        to_number="070",
        account_id="AC",
    )
    received = []

    async def handler(call, role, text):
        received.append((role, text))

    session.on("transcript", handler)
    await session._emit("transcript", "user", "안녕하세요")
    assert received == [("user", "안녕하세요")]
```

**Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/agent/test_session.py -v`
Expected: FAIL

**Step 3: 구현**

```python
# src/clawops/agent/_session.py
"""CallSession: per-call 상태 관리 및 오디오 스트림."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Awaitable


class CallSession:
    def __init__(
        self,
        *,
        call_id: str,
        from_number: str,
        to_number: str,
        account_id: str,
    ) -> None:
        self.call_id = call_id
        self.from_number = from_number
        self.to_number = to_number
        self.account_id = account_id
        self.start_time = datetime.now()
        self.metadata: dict[str, Any] = {}

        self._send_audio_fn: Callable[[bytes], Awaitable[None]] | None = None
        self._send_clear_fn: Callable[[], Awaitable[None]] | None = None
        self._hangup_fn: Callable[[], Awaitable[None]] | None = None

        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._event_handlers: dict[str, list[Callable[..., Awaitable[None]]]] = {}

    @property
    def duration(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()

    async def send_audio(self, pcm16: bytes) -> None:
        if self._send_audio_fn:
            await self._send_audio_fn(pcm16)

    async def clear_audio(self) -> None:
        if self._send_clear_fn:
            await self._send_clear_fn()

    async def hangup(self) -> None:
        if self._hangup_fn:
            await self._hangup_fn()

    async def audio_stream(self) -> AsyncIterator[bytes]:
        while True:
            chunk = await self._audio_queue.get()
            if chunk is None:
                break
            yield chunk

    async def _push_audio(self, data: bytes) -> None:
        await self._audio_queue.put(data)

    def _audio_done(self) -> None:
        self._audio_queue.put_nowait(None)

    def on(self, event: str, handler: Callable[..., Awaitable[None]]) -> None:
        self._event_handlers.setdefault(event, []).append(handler)

    async def _emit(self, event: str, *args: Any) -> None:
        for handler in self._event_handlers.get(event, []):
            await handler(self, *args)
```

**Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/agent/test_session.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clawops/agent/_session.py tests/agent/test_session.py
git commit -m "feat: add CallSession for per-call state management"
```

---

### Task 6: Control WebSocket 클라이언트

**Files:**
- Create: `src/clawops/agent/_control_ws.py`
- Test: `tests/agent/test_control_ws.py`

**Step 1: 테스트 작성**

```python
# tests/agent/test_control_ws.py
from clawops.agent._control_ws import build_control_ws_url


def test_build_url_https():
    url = build_control_ws_url(
        base_url="https://api.claw-ops.com",
        account_id="AC123",
        number="07012341234",
    )
    assert url == "wss://api.claw-ops.com/v1/accounts/AC123/agent/listen?number=07012341234"


def test_build_url_http():
    url = build_control_ws_url(
        base_url="http://localhost:3000",
        account_id="AC123",
        number="07012341234",
    )
    assert url == "ws://localhost:3000/v1/accounts/AC123/agent/listen?number=07012341234"
```

**Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/agent/test_control_ws.py -v`
Expected: FAIL

**Step 3: 구현**

```python
# src/clawops/agent/_control_ws.py
"""Control WebSocket: ClawOps 서버에 대한 상시 연결 관리.

Agent가 서버에 역방향으로 연결하여 인바운드 콜 알림을 수신한다.
자동 재연결(exponential backoff) 포함.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Awaitable
from urllib.parse import quote

import aiohttp

log = logging.getLogger("clawops.agent")

INITIAL_RECONNECT_DELAY = 1.0
MAX_RECONNECT_DELAY = 30.0


def build_control_ws_url(*, base_url: str, account_id: str, number: str) -> str:
    scheme = "wss" if base_url.startswith("https") else "ws"
    host = base_url.replace("https://", "").replace("http://", "").rstrip("/")
    return f"{scheme}://{host}/v1/accounts/{account_id}/agent/listen?number={quote(number)}"


class ControlWebSocket:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        account_id: str,
        number: str,
        on_call_incoming: Callable[[dict[str, Any]], Awaitable[None]],
        on_call_ended: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._url = build_control_ws_url(base_url=base_url, account_id=account_id, number=number)
        self._api_key = api_key
        self._on_call_incoming = on_call_incoming
        self._on_call_ended = on_call_ended
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False

    async def connect(self) -> None:
        self._running = True
        delay = INITIAL_RECONNECT_DELAY

        while self._running:
            try:
                self._session = aiohttp.ClientSession()
                self._ws = await self._session.ws_connect(
                    self._url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    heartbeat=30.0,
                )
                log.info(f"Control WS connected: {self._url}")
                delay = INITIAL_RECONNECT_DELAY

                async for msg in self._ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        event = data.get("event")
                        if event == "call.incoming":
                            await self._on_call_incoming(data)
                        elif event == "call.ended":
                            await self._on_call_ended(data)
                    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                        break

            except (aiohttp.ClientError, OSError) as e:
                log.warning(f"Control WS error: {e}")
            finally:
                if self._ws and not self._ws.closed:
                    await self._ws.close()
                if self._session:
                    await self._session.close()
                self._ws = None
                self._session = None

            if self._running:
                log.info(f"Control WS reconnecting in {delay:.1f}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY)

    async def send(self, data: dict[str, Any]) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_str(json.dumps(data))

    async def close(self) -> None:
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session:
            await self._session.close()
```

**Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/agent/test_control_ws.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clawops/agent/_control_ws.py tests/agent/test_control_ws.py
git commit -m "feat: add Control WebSocket client with auto-reconnect"
```

---

### Task 7: Media WebSocket 클라이언트

**Files:**
- Create: `src/clawops/agent/_media_ws.py`
- Test: `tests/agent/test_media_ws.py`

**Step 1: 테스트 작성**

```python
# tests/agent/test_media_ws.py
import base64
from clawops.agent._media_ws import parse_media_event, build_media_response, parse_start_event


def test_parse_media_event():
    pcm = b"\x00\x01" * 80
    event = {
        "event": "media",
        "media": {
            "track": "inbound",
            "chunk": "1",
            "timestamp": "100",
            "payload": base64.b64encode(pcm).decode(),
        },
    }
    result = parse_media_event(event)
    assert result["pcm16"] == pcm
    assert result["timestamp"] == 100


def test_build_media_response():
    pcm = b"\x00\x01" * 80
    msg = build_media_response(pcm)
    assert msg["event"] == "media"
    decoded = base64.b64decode(msg["media"]["payload"])
    assert decoded == pcm


def test_parse_start_event():
    event = {
        "event": "start",
        "start": {
            "streamId": "MZ_abc",
            "callId": "CA_123",
            "accountId": "AC_test",
            "tracks": ["inbound"],
            "mediaFormat": {"encoding": "audio/x-l16", "sampleRate": 8000, "channels": 1},
        },
    }
    result = parse_start_event(event)
    assert result["stream_id"] == "MZ_abc"
    assert result["call_id"] == "CA_123"
    assert result["sample_rate"] == 8000
```

**Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/agent/test_media_ws.py -v`
Expected: FAIL

**Step 3: 구현**

```python
# src/clawops/agent/_media_ws.py
"""Media WebSocket: per-call 오디오 스트림.

ClawOps stream-handler.js 프로토콜을 구현한다:
connected -> start -> media (PCM16 8kHz base64) -> stop
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, Callable, Awaitable

import aiohttp

log = logging.getLogger("clawops.agent")


def parse_start_event(data: dict[str, Any]) -> dict[str, Any]:
    start = data["start"]
    fmt = start.get("mediaFormat", {})
    return {
        "stream_id": start["streamId"],
        "call_id": start["callId"],
        "account_id": start.get("accountId", ""),
        "sample_rate": fmt.get("sampleRate", 8000),
    }


def parse_media_event(data: dict[str, Any]) -> dict[str, Any]:
    media = data["media"]
    return {
        "pcm16": base64.b64decode(media["payload"]),
        "timestamp": int(media.get("timestamp", 0)),
    }


def build_media_response(pcm16: bytes) -> dict[str, Any]:
    return {
        "event": "media",
        "media": {
            "payload": base64.b64encode(pcm16).decode(),
        },
    }


class MediaWebSocket:
    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        on_audio: Callable[[bytes, int], Awaitable[None]],
        on_start: Callable[[dict[str, Any]], Awaitable[None]],
        on_stop: Callable[[], Awaitable[None]],
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._on_audio = on_audio
        self._on_start = on_start
        self._on_stop = on_stop
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._send_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        log.info(f"Media WS connected: {self._url}")
        self._send_task = asyncio.create_task(self._send_loop())

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    event = data.get("event")

                    if event == "start":
                        await self._on_start(parse_start_event(data))
                    elif event == "media":
                        parsed = parse_media_event(data)
                        await self._on_audio(parsed["pcm16"], parsed["timestamp"])
                    elif event == "stop":
                        await self._on_stop()
                        break
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    break
        finally:
            await self.close()

    async def send_audio(self, pcm16: bytes) -> None:
        self._audio_queue.put_nowait(pcm16)

    async def send_clear(self) -> None:
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self._ws and not self._ws.closed:
            await self._ws.send_str(json.dumps({"event": "clear"}))

    async def _send_loop(self) -> None:
        """오디오 청크를 20ms 간격으로 전송."""
        try:
            while True:
                chunk = await self._audio_queue.get()
                if chunk is None:
                    break
                if self._ws and not self._ws.closed:
                    msg = build_media_response(chunk)
                    await self._ws.send_str(json.dumps(msg))
                    await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        self._audio_queue.put_nowait(None)
        if self._send_task and not self._send_task.done():
            self._send_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session:
            await self._session.close()
```

**Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/agent/test_media_ws.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clawops/agent/_media_ws.py tests/agent/test_media_ws.py
git commit -m "feat: add Media WebSocket client with stream protocol"
```

---

### Task 8: Pipeline Protocol (STT, LLM, TTS 인터페이스)

**Files:**
- Create: `src/clawops/agent/pipeline/__init__.py`
- Create: `src/clawops/agent/pipeline/_base.py`
- Test: `tests/agent/test_pipeline_base.py`

**Step 1: 테스트 작성**

```python
# tests/agent/test_pipeline_base.py
import pytest
from typing import AsyncIterator
from clawops.agent.pipeline._base import STT, TTS


@pytest.mark.asyncio
async def test_stt_protocol():
    class MySTT:
        async def transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
            async for chunk in audio_stream:
                yield f"text:{len(chunk)}"

    stt: STT = MySTT()

    async def audio_gen() -> AsyncIterator[bytes]:
        yield b"\x00" * 320
        yield b"\x01" * 320

    results = []
    async for text in stt.transcribe(audio_gen()):
        results.append(text)
    assert results == ["text:320", "text:320"]


@pytest.mark.asyncio
async def test_tts_protocol():
    class MyTTS:
        async def synthesize(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
            async for text in text_stream:
                yield text.encode()

    tts: TTS = MyTTS()

    async def text_gen() -> AsyncIterator[str]:
        yield "hello"

    results = []
    async for chunk in tts.synthesize(text_gen()):
        results.append(chunk)
    assert results == [b"hello"]
```

**Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/agent/test_pipeline_base.py -v`
Expected: FAIL

**Step 3: 구현**

```python
# src/clawops/agent/pipeline/__init__.py
from ._base import STT, LLM, TTS

__all__ = ["STT", "LLM", "TTS"]
```

```python
# src/clawops/agent/pipeline/_base.py
"""Provider Protocol 정의. 유저가 이 Protocol에 맞추면 아무 프로바이더나 사용 가능."""
from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class STT(Protocol):
    async def transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """오디오 스트림(PCM16 8kHz) -> 텍스트 스트림."""
        ...

@runtime_checkable
class LLM(Protocol):
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """메시지 -> 텍스트 응답 스트림."""
        ...

@runtime_checkable
class TTS(Protocol):
    async def synthesize(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """텍스트 스트림 -> 오디오(PCM16 8kHz) 스트림."""
        ...
```

**Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/agent/test_pipeline_base.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clawops/agent/pipeline/ tests/agent/test_pipeline_base.py
git commit -m "feat: add STT, LLM, TTS Protocol interfaces"
```

---

### Task 9: OpenAI Realtime Session

`../ai-agent/session_manager.py`의 핵심 로직을 SDK 구조로 포팅.

**Files:**
- Create: `src/clawops/agent/pipeline/_realtime_session.py`
- Test: `tests/agent/test_realtime_session.py`

**Step 1: 테스트 작성**

```python
# tests/agent/test_realtime_session.py
from clawops.agent.pipeline._realtime_session import RealtimeConfig


def test_realtime_config_defaults():
    config = RealtimeConfig(
        system_prompt="test",
        openai_api_key="sk-test",
    )
    assert config.voice == "ash"
    assert config.model == "gpt-4o-realtime-preview"
    assert config.language == "ko"
    assert config.eagerness == "high"
    assert config.greeting is True


def test_realtime_config_custom():
    config = RealtimeConfig(
        system_prompt="custom",
        openai_api_key="sk-test",
        voice="nova",
        model="gpt-4o-mini-realtime",
        language="en",
        eagerness="low",
        greeting=False,
    )
    assert config.voice == "nova"
    assert config.language == "en"
    assert config.greeting is False
```

**Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/agent/test_realtime_session.py -v`
Expected: FAIL

**Step 3: 구현**

```python
# src/clawops/agent/pipeline/_realtime_session.py
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

from .._audio import pcm16_to_ulaw, ulaw_to_pcm16
from .._session import CallSession
from .._tool import ToolRegistry

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
    voice: str = "ash"
    model: str = "gpt-4o-realtime-preview"
    language: str = "ko"
    eagerness: str = "high"
    greeting: bool = True


class RealtimeSession:
    def __init__(self, config: RealtimeConfig, tool_registry: ToolRegistry) -> None:
        self._config = config
        self._tools = tool_registry
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._http: aiohttp.ClientSession | None = None
        self._call: CallSession | None = None
        self._last_assistant_item: str | None = None
        self._response_start_ts: int | None = None
        self._latest_media_ts: int = 0
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._tasks: list[asyncio.Task[Any]] = []

    async def start(self, call: CallSession) -> None:
        self._call = call
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
        self._tasks.append(asyncio.create_task(self._audio_send_loop()))

    async def feed_audio(self, pcm16: bytes, timestamp: int) -> None:
        self._latest_media_ts = timestamp
        ulaw = pcm16_to_ulaw(pcm16)
        await self._send({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(ulaw).decode(),
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
            if event.get("item_id"):
                self._last_assistant_item = event["item_id"]

            ulaw = base64.b64decode(event["delta"])
            pcm16 = ulaw_to_pcm16(ulaw)
            chunk_size = 320  # 320B = 20ms at 8kHz 16-bit
            for off in range(0, len(pcm16), chunk_size):
                self._audio_queue.put_nowait(pcm16[off : off + chunk_size])

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

        try:
            args = json.loads(item.get("arguments", "{}"))
            result = await self._tools.call(func_name, args)
        except Exception as e:
            result = f"Error: {e}"

        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": str(result),
            },
        })
        await self._send({"type": "response.create"})

    async def _handle_truncation(self) -> None:
        if not self._last_assistant_item or self._response_start_ts is None:
            return

        elapsed = self._latest_media_ts - self._response_start_ts
        audio_end_ms = max(0, elapsed)

        await self._send({
            "type": "conversation.item.truncate",
            "item_id": self._last_assistant_item,
            "content_index": 0,
            "audio_end_ms": audio_end_ms,
        })

        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        if self._call:
            await self._call.clear_audio()

        self._last_assistant_item = None
        self._response_start_ts = None

    async def _audio_send_loop(self) -> None:
        try:
            while True:
                chunk = await self._audio_queue.get()
                if chunk is None:
                    break
                if self._call:
                    await self._call.send_audio(chunk)
                await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            pass

    async def _send(self, data: dict[str, Any]) -> None:
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send_str(json.dumps(data))
            except Exception:
                pass

    async def stop(self) -> None:
        self._audio_queue.put_nowait(None)
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
```

**Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/agent/test_realtime_session.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/clawops/agent/pipeline/_realtime_session.py tests/agent/test_realtime_session.py
git commit -m "feat: add OpenAI Realtime session with tool call and truncation"
```

---

### Task 10: ClawOpsAgent 메인 클래스

**Files:**
- Create: `src/clawops/agent/_agent.py`
- Modify: `src/clawops/agent/__init__.py`
- Test: `tests/agent/test_agent.py`

**Step 1: 테스트 작성**

```python
# tests/agent/test_agent.py
import pytest
from clawops.agent import ClawOpsAgent


def test_agent_creation():
    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        system_prompt="test prompt",
        openai_api_key="sk-openai-test",
    )
    assert agent._from_number == "07012341234"
    assert agent._config.system_prompt == "test prompt"


def test_agent_tool_decorator():
    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        system_prompt="test",
        openai_api_key="sk-openai-test",
    )

    @agent.tool
    async def greet(name: str) -> str:
        """인사합니다."""
        return f"안녕 {name}"

    assert "greet" in agent._tool_registry
    schemas = agent._tool_registry.to_openai_tools()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "greet"


def test_agent_event_decorator():
    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        system_prompt="test",
        openai_api_key="sk-openai-test",
    )

    @agent.on("call_start")
    async def on_start(call):
        pass

    assert len(agent._event_handlers["call_start"]) == 1


def test_agent_from_env(monkeypatch):
    monkeypatch.setenv("CLAWOPS_API_KEY", "sk_env")
    monkeypatch.setenv("CLAWOPS_ACCOUNT_ID", "AC_env")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-env")

    agent = ClawOpsAgent(
        from_="07012341234",
        system_prompt="test",
    )
    assert agent._api_key == "sk_env"
    assert agent._account_id == "AC_env"
    assert agent._config.openai_api_key == "sk-openai-env"


def test_agent_missing_api_key():
    from clawops._exceptions import AgentError
    with pytest.raises(AgentError, match="api_key"):
        ClawOpsAgent(
            from_="07012341234",
            system_prompt="test",
            openai_api_key="sk-test",
        )
```

**Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/agent/test_agent.py -v`
Expected: FAIL

**Step 3: 구현**

```python
# src/clawops/agent/_agent.py
"""ClawOpsAgent: 메인 진입점.

Control WS 연결, per-call Media WS 생성, RealtimeSession 관리를 조합한다.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Awaitable

from .._exceptions import AgentError
from ._control_ws import ControlWebSocket
from ._media_ws import MediaWebSocket
from ._session import CallSession
from ._tool import ToolRegistry
from .pipeline._base import STT, LLM, TTS
from .pipeline._realtime_session import RealtimeConfig, RealtimeSession

log = logging.getLogger("clawops.agent")


class ClawOpsAgent:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
        from_: str,
        system_prompt: str = "",
        voice: str = "ash",
        model: str = "gpt-4o-realtime-preview",
        openai_api_key: str | None = None,
        language: str = "ko",
        eagerness: str = "high",
        greeting: bool = True,
        stt: STT | None = None,
        llm: LLM | None = None,
        tts: TTS | None = None,
        mcp_servers: list[Any] | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("CLAWOPS_API_KEY")
        if api_key is None:
            raise AgentError("api_key를 지정하거나 CLAWOPS_API_KEY 환경변수를 설정하세요.")

        if account_id is None:
            account_id = os.environ.get("CLAWOPS_ACCOUNT_ID")
        if account_id is None:
            raise AgentError("account_id를 지정하거나 CLAWOPS_ACCOUNT_ID 환경변수를 설정하세요.")

        if openai_api_key is None:
            openai_api_key = os.environ.get("OPENAI_API_KEY", "")

        if base_url is None:
            base_url = os.environ.get("CLAWOPS_BASE_URL", "https://api.claw-ops.com")

        self._api_key = api_key
        self._account_id = account_id
        self._base_url = base_url
        self._from_number = from_

        self._config = RealtimeConfig(
            system_prompt=system_prompt,
            openai_api_key=openai_api_key,
            voice=voice,
            model=model,
            language=language,
            eagerness=eagerness,
            greeting=greeting,
        )

        self._stt = stt
        self._llm = llm
        self._tts = tts
        self._mcp_servers = mcp_servers or []

        self._tool_registry = ToolRegistry()
        self._event_handlers: dict[str, list[Callable[..., Awaitable[None]]]] = {}
        self._active_sessions: dict[str, CallSession] = {}
        self._control_ws: ControlWebSocket | None = None

    def tool(self, fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        return self._tool_registry.register(fn)

    def on(self, event: str) -> Callable:
        def decorator(fn: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
            self._event_handlers.setdefault(event, []).append(fn)
            return fn
        return decorator

    def listen(self) -> None:
        log.info(f"ClawOpsAgent listening on {self._from_number}")
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            log.info("Agent stopped by user")

    async def _run(self) -> None:
        self._control_ws = ControlWebSocket(
            base_url=self._base_url,
            api_key=self._api_key,
            account_id=self._account_id,
            number=self._from_number,
            on_call_incoming=self._handle_incoming,
            on_call_ended=self._handle_ended,
        )
        await self._control_ws.connect()

    async def _handle_incoming(self, data: dict[str, Any]) -> None:
        call_id = data["callId"]
        from_number = data.get("from", "")
        media_url = data.get("mediaUrl", "")

        log.info(f"Incoming call: {from_number} -> {self._from_number} ({call_id})")

        call = CallSession(
            call_id=call_id,
            from_number=from_number,
            to_number=self._from_number,
            account_id=self._account_id,
        )

        for event, handlers in self._event_handlers.items():
            for handler in handlers:
                call.on(event, handler)

        self._active_sessions[call_id] = call

        if self._control_ws:
            await self._control_ws.send({"event": "call.accept", "callId": call_id})

        asyncio.create_task(self._start_call_session(call, media_url))

    async def _start_call_session(self, call: CallSession, media_url: str) -> None:
        realtime = RealtimeSession(self._config, self._tool_registry)

        media_ws = MediaWebSocket(
            url=media_url,
            api_key=self._api_key,
            on_audio=lambda pcm, ts: realtime.feed_audio(pcm, ts),
            on_start=lambda info: self._on_media_start(call, info),
            on_stop=lambda: self._on_media_stop(call, realtime),
        )

        call._send_audio_fn = media_ws.send_audio
        call._send_clear_fn = media_ws.send_clear
        call._hangup_fn = lambda: media_ws.close()

        await call._emit("call_start")
        await realtime.start(call)

        try:
            await media_ws.connect()
        finally:
            await realtime.stop()
            await call._emit("call_end")
            self._active_sessions.pop(call.call_id, None)

    async def _on_media_start(self, call: CallSession, info: dict[str, Any]) -> None:
        log.info(f"Media stream started: {call.call_id}")

    async def _on_media_stop(self, call: CallSession, realtime: RealtimeSession) -> None:
        log.info(f"Media stream stopped: {call.call_id}")
        await realtime.stop()

    async def _handle_ended(self, data: dict[str, Any]) -> None:
        call_id = data.get("callId", "")
        log.info(f"Call ended (server): {call_id}")
        self._active_sessions.pop(call_id, None)
```

**Step 4: __init__.py 업데이트**

```python
# src/clawops/agent/__init__.py
"""ClawOps Agent - AI 음성 에이전트 프레임워크."""

from ._agent import ClawOpsAgent
from ._tool import ToolRegistry, function_tool

__all__ = ["ClawOpsAgent", "ToolRegistry", "function_tool"]
```

**Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/agent/test_agent.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/clawops/agent/ tests/agent/test_agent.py
git commit -m "feat: add ClawOpsAgent main class"
```

---

### Task 11: MCP 설정 클래스

**Files:**
- Create: `src/clawops/agent/mcp/__init__.py`
- Create: `src/clawops/agent/mcp/_http.py`
- Create: `src/clawops/agent/mcp/_stdio.py`
- Test: `tests/agent/test_mcp.py`

**Step 1: 테스트 작성**

```python
# tests/agent/test_mcp.py
from clawops.agent.mcp import MCPServerHTTP, MCPServerStdio


def test_mcp_http_creation():
    server = MCPServerHTTP("https://my-mcp-server.com")
    assert server.url == "https://my-mcp-server.com"


def test_mcp_stdio_creation():
    server = MCPServerStdio("npx @modelcontextprotocol/server-google")
    assert server.command == "npx @modelcontextprotocol/server-google"
```

**Step 2: 구현**

```python
# src/clawops/agent/mcp/__init__.py
from ._http import MCPServerHTTP
from ._stdio import MCPServerStdio

__all__ = ["MCPServerHTTP", "MCPServerStdio"]
```

```python
# src/clawops/agent/mcp/_http.py
"""HTTP/SSE 기반 MCP 서버 설정. 실제 프로토콜은 pip install clawops[mcp] 시 활성화."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCPServerHTTP:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
```

```python
# src/clawops/agent/mcp/_stdio.py
"""Stdio 기반 MCP 서버 설정."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCPServerStdio:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
```

**Step 3: 테스트 통과 확인**

Run: `python -m pytest tests/agent/test_mcp.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/clawops/agent/mcp/ tests/agent/test_mcp.py
git commit -m "feat: add MCP server config classes"
```

---

### Task 12: Plugins stub + 통합 테스트

**Files:**
- Create: `src/clawops/agent/plugins/__init__.py`
- Create: `src/clawops/agent/plugins/openai_realtime.py`
- Test: `tests/agent/test_integration.py`

**Step 1: Plugin stub 생성**

```python
# src/clawops/agent/plugins/__init__.py
"""AI 프로바이더 플러그인. pip install clawops[deepgram] 등으로 개별 설치."""
```

```python
# src/clawops/agent/plugins/openai_realtime.py
"""OpenAI Realtime API 플러그인. ClawOpsAgent에 내장, system_prompt 설정 시 자동 활성화."""
from __future__ import annotations

from ..pipeline._realtime_session import RealtimeConfig, RealtimeSession


class OpenAIRealtimePlugin:
    def __init__(self, config: RealtimeConfig) -> None:
        self.config = config
```

**Step 2: 통합 테스트 작성**

```python
# tests/agent/test_integration.py
"""전체 Agent 컴포넌트 통합 테스트 (실제 서버 연결 없이)."""
import pytest
from clawops.agent import ClawOpsAgent
from clawops.agent._session import CallSession
from clawops.agent._tool import ToolRegistry


def test_full_agent_setup():
    agent = ClawOpsAgent(
        api_key="sk_test",
        account_id="AC_test",
        from_="07012341234",
        system_prompt="테스트 상담원입니다.",
        openai_api_key="sk-openai-test",
        voice="nova",
        language="ko",
    )

    @agent.tool
    async def get_info(query: str) -> str:
        """정보를 조회합니다."""
        return f"결과: {query}"

    events_received = []

    @agent.on("call_start")
    async def on_start(call):
        events_received.append("start")

    @agent.on("call_end")
    async def on_end(call):
        events_received.append("end")

    assert "get_info" in agent._tool_registry
    schemas = agent._tool_registry.to_openai_tools()
    assert any(t["name"] == "get_info" for t in schemas)
    assert "call_start" in agent._event_handlers
    assert "call_end" in agent._event_handlers
    assert agent._config.voice == "nova"


@pytest.mark.asyncio
async def test_tool_execution_integration():
    registry = ToolRegistry()

    @registry.register
    async def add_numbers(a: int, b: int) -> str:
        """두 수를 더합니다."""
        return str(a + b)

    result = await registry.call("add_numbers", {"a": 2, "b": 3})
    assert result == "5"

    schemas = registry.to_openai_tools()
    assert schemas[0]["parameters"]["required"] == ["a", "b"]


@pytest.mark.asyncio
async def test_call_session_lifecycle():
    session = CallSession(
        call_id="CA_integ",
        from_number="01012345678",
        to_number="07012341234",
        account_id="AC_test",
    )

    events = []

    async def on_transcript(call, role, text):
        events.append(f"{role}:{text}")

    session.on("transcript", on_transcript)

    await session._emit("transcript", "user", "안녕하세요")
    await session._emit("transcript", "assistant", "네, 반갑습니다")

    assert events == ["user:안녕하세요", "assistant:네, 반갑습니다"]
    assert session.duration > 0


def test_all_imports():
    from clawops.agent import ClawOpsAgent
    from clawops.agent._tool import ToolRegistry
    from clawops.agent._session import CallSession
    from clawops.agent._audio import pcm16_to_ulaw, ulaw_to_pcm16
    from clawops.agent._control_ws import ControlWebSocket
    from clawops.agent._media_ws import MediaWebSocket
    from clawops.agent.pipeline import STT, LLM, TTS
    from clawops.agent.pipeline._realtime_session import RealtimeSession, RealtimeConfig
    from clawops.agent.mcp import MCPServerHTTP, MCPServerStdio
    from clawops.agent.plugins.openai_realtime import OpenAIRealtimePlugin
    # All imports successful
```

**Step 3: 전체 테스트 실행**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/clawops/agent/plugins/ tests/agent/test_integration.py
git commit -m "feat: complete clawops agent module v1"
```
