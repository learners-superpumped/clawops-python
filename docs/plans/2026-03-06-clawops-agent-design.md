# ClawOps Agent Design Document

**Date:** 2026-03-06
**Status:** Approved

## Overview

ClawOps Python SDK(`clawops`)에 AI Agent 모듈을 추가한다. 유저가 `.listen()` 한 줄로 인바운드 전화를 수신하고 AI로 처리할 수 있는 시스템.

```python
from clawops.agent import ClawOpsAgent, function_tool

agent = ClawOpsAgent(
    from_="07012341234",
    system_prompt="친절한 고객 상담원입니다.",
)

@agent.tool
async def check_order(order_id: str) -> str:
    """주문 상태를 확인합니다."""
    return f"주문 {order_id}은 배송 중입니다."

agent.listen()
```

## Key Decisions

| 항목 | 결정 |
|------|------|
| 연결 방향 | Agent -> ClawOps 서버 (역방향 WebSocket, ngrok 불필요) |
| WebSocket 구조 | Control WS (1개, 상시) + Media WS (통화당 1개) |
| AI 모드 | OpenAI Realtime (S2S) 내장 + Pipeline (STT/LLM/TTS 분리) |
| Provider 추상화 | 코어 인터페이스 + optional extras (`pip install clawops[agent,deepgram]`) |
| Tool 시스템 | `@agent.tool` 데코레이터 + MCP 서버 네이티브 (LiveKit Agents 스타일) |
| 인증 | Bearer token (기존 API key) + 번호 소유권 검증 |
| webhook signing | Agent Listen에서는 불필요 (TLS + Bearer로 양방향 인증 완료) |

## 1. Package Structure

기존 REST SDK(`src/clawops/`)에 `agent/` 모듈 추가.

```
src/clawops/
├── (기존 SDK 구조 그대로)
├── __init__.py
├── _client.py
├── _base_client.py
├── _resource.py
├── _exceptions.py               # + AgentError 추가
├── _constants.py                # + WS 관련 상수
├── resources/
├── types/
│
├── agent/
│   ├── __init__.py              # ClawOpsAgent, function_tool export
│   ├── _agent.py                # ClawOpsAgent 메인 클래스
│   ├── _session.py              # CallSession (per-call 상태 관리)
│   ├── _control_ws.py           # Control WebSocket 연결/재연결
│   ├── _media_ws.py             # Media WebSocket (per-call 오디오)
│   ├── _audio.py                # PCM16 <-> G.711 u-law 변환
│   ├── _tool.py                 # function_tool 데코레이터, ToolRegistry
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── _base.py             # STT, LLM, TTS Protocol 정의
│   │   ├── _pipeline_session.py # STT -> LLM -> TTS 파이프라인
│   │   └── _realtime_session.py # OpenAI Realtime (S2S) 통합
│   ├── plugins/
│   │   ├── openai_realtime.py   # OpenAI Realtime API
│   │   ├── openai_llm.py        # OpenAI Chat LLM
│   │   ├── deepgram_stt.py      # Deepgram STT
│   │   ├── elevenlabs_tts.py    # ElevenLabs TTS
│   │   ├── google_tts.py        # Google Cloud TTS
│   │   └── ...
│   └── mcp/
│       ├── __init__.py          # MCPServerHTTP, MCPServerStdio export
│       ├── _http.py             # HTTP/SSE MCP 클라이언트
│       └── _stdio.py            # Stdio MCP 클라이언트
│
└── py.typed
```

## 2. Dependencies (pyproject.toml)

```toml
[project.optional-dependencies]
# Agent 코어 (WebSocket 연결)
agent = ["aiohttp>=3.9.0,<4"]

# AI Provider plugins
openai-realtime = ["clawops[agent]", "aiohttp>=3.9.0,<4"]
openai-llm = ["clawops[agent]", "openai>=1.0.0"]
deepgram = ["clawops[agent]", "deepgram-sdk>=3.0.0"]
elevenlabs = ["clawops[agent]", "elevenlabs>=1.0.0"]
google-tts = ["clawops[agent]", "google-cloud-texttospeech>=2.0.0"]

# MCP
mcp = ["clawops[agent]", "mcp>=1.0.0"]

# 전부
all = [
    "clawops[agent]",
    "clawops[openai-realtime]",
    "clawops[openai-llm]",
    "clawops[deepgram]",
    "clawops[elevenlabs]",
    "clawops[mcp]",
]
```

## 3. ClawOpsAgent API

### 3.1 OpenAI Realtime 모드 (기본)

```python
from clawops.agent import ClawOpsAgent, function_tool
from clawops.agent.mcp import MCPServerHTTP, MCPServerStdio

agent = ClawOpsAgent(
    # 인증 (생략 시 CLAWOPS_API_KEY, CLAWOPS_ACCOUNT_ID 환경변수)
    api_key="sk_...",
    account_id="AC...",

    # 수신 번호
    from_="07012341234",

    # OpenAI Realtime 설정
    system_prompt="친절한 고객 상담원입니다.",
    voice="ash",
    model="gpt-4o-realtime-preview",
    openai_api_key="sk-...",       # or OPENAI_API_KEY env
    language="ko",                  # transcription 언어
    eagerness="high",               # VAD 민감도: low, medium, high, auto
    greeting=True,                  # AI가 먼저 인사

    # MCP 서버 (선택)
    mcp_servers=[
        MCPServerHTTP("https://my-mcp-server.com"),
        MCPServerStdio("npx @modelcontextprotocol/server-google"),
    ],
)

# 로컬 tool 등록
@agent.tool
async def check_order(order_id: str) -> str:
    """주문 상태를 확인합니다."""
    return f"주문 {order_id}은 배송 중입니다."

@agent.tool
async def transfer_call(department: str) -> str:
    """다른 부서로 전화를 연결합니다."""
    return "전환 완료"

# 이벤트 훅 (선택)
@agent.on("call_start")
async def on_start(call):
    print(f"수신: {call.from_number} -> {call.to_number}")

@agent.on("call_end")
async def on_end(call):
    print(f"종료: {call.call_id}, {call.duration}초")

@agent.on("transcript")
async def on_transcript(call, role, text):
    print(f"[{role}] {text}")

agent.listen()  # 블로킹, Ctrl+C로 종료
```

### 3.2 Pipeline 모드 (STT/LLM/TTS 분리)

```python
from clawops.agent import ClawOpsAgent
from clawops.agent.plugins import DeepgramSTT, OpenAILLM, ElevenLabsTTS

agent = ClawOpsAgent(
    from_="07012341234",
    stt=DeepgramSTT(api_key="..."),
    llm=OpenAILLM(model="gpt-4o", system_prompt="..."),
    tts=ElevenLabsTTS(voice_id="..."),
)

@agent.tool
async def check_reservation(name: str, date: str) -> str:
    """예약을 확인합니다."""
    return f"{name}님 {date} 예약 확인됨"

agent.listen()
```

### 3.3 커스텀 핸들러 (완전 수동)

```python
from clawops.agent import ClawOpsAgent

agent = ClawOpsAgent(from_="07012341234")

@agent.on("call_start")
async def handle(call):
    async for audio_chunk in call.audio_stream():
        response_audio = await my_custom_pipeline(audio_chunk)
        await call.send_audio(response_audio)

agent.listen()
```

### 3.4 기존 REST 클라이언트 공유

```python
from clawops import AsyncClawOps
from clawops.agent import ClawOpsAgent

client = AsyncClawOps(api_key="sk_...", account_id="AC...")
agent = ClawOpsAgent(
    client=client,           # 인증/설정 공유
    from_="07012341234",
    system_prompt="...",
)

# agent 내부에서 REST API 호출 가능
agent.listen()
```

## 4. CallSession (per-call 객체)

```python
class CallSession:
    # 속성
    call_id: str            # "CA..."
    from_number: str        # 발신자 번호
    to_number: str          # 수신 번호 (agent의 from_)
    account_id: str
    start_time: datetime
    duration: float         # 초
    metadata: dict          # 유저가 자유롭게 사용

    # 오디오
    async def send_audio(self, pcm16: bytes): ...
    async def audio_stream(self) -> AsyncIterator[bytes]: ...
    async def clear_audio(self): ...          # 재생 큐 클리어

    # 통화 제어
    async def hangup(self): ...
    async def say(self, text: str): ...       # TTS로 즉시 말하기
    async def generate_reply(self, instructions: str): ...  # LLM에 지시
```

## 5. Provider Protocol (인터페이스)

```python
# agent/pipeline/_base.py

class STT(Protocol):
    async def transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """오디오 스트림 -> 텍스트 스트림"""
        ...

class LLM(Protocol):
    async def generate(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """메시지 -> 텍스트 응답 스트림"""
        ...

class TTS(Protocol):
    async def synthesize(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """텍스트 스트림 -> 오디오(PCM16) 스트림"""
        ...
```

유저가 이 Protocol에 맞추면 아무 프로바이더나 사용 가능.

## 6. WebSocket 프로토콜

### 6.1 Control WS

```
Endpoint: wss://api.claw-ops.com/v1/accounts/{accountId}/agent/listen
Auth: Authorization: Bearer sk_...
Query: ?number=07012341234
```

**서버 -> 클라이언트:**

```json
{ "event": "call.incoming", "callId": "CA...", "from": "01012345678",
  "mediaUrl": "wss://api.claw-ops.com/v1/agent/media/CA...?token=<1회용>" }

{ "event": "call.ended", "callId": "CA...", "duration": 45 }

{ "event": "error", "code": "NUMBER_OFFLINE", "message": "..." }
```

**클라이언트 -> 서버:**

```json
{ "event": "call.accept", "callId": "CA..." }

{ "event": "call.reject", "callId": "CA..." }

{ "event": "ping" }
```

### 6.2 Media WS

```
Endpoint: wss://api.claw-ops.com/v1/agent/media/{callId}
Auth: ?token=<1회용 토큰> (Control WS에서 발급, 30초 만료)
```

기존 stream-handler.js 프로토콜 재사용:

```json
// 서버 -> 클라이언트
{ "event": "connected", "protocol": "Call", "version": "1.0.0" }
{ "event": "start", "start": { "streamId": "MZ...", "callId": "CA...", "accountId": "...",
    "tracks": ["inbound"], "mediaFormat": { "encoding": "audio/x-l16", "sampleRate": 8000, "channels": 1 } } }
{ "event": "media", "media": { "track": "inbound", "chunk": "1", "timestamp": "0", "payload": "<base64 PCM16 8kHz>" } }
{ "event": "stop", "stop": { "accountId": "...", "callId": "..." } }

// 클라이언트 -> 서버
{ "event": "media", "media": { "payload": "<base64 PCM16 8kHz>" } }
{ "event": "clear" }
```

## 7. OpenAI Realtime 내부 흐름

```
ClawOps Server                    ClawOpsAgent (유저 로컬)
     |                                  |
  Control WS  <--(WSS/TLS)-->      _control_ws.py
     |                                  |
  call.incoming  ------------>      CallSession 생성
     |                                  |
  Media WS  <--(WSS/TLS)-->        _media_ws.py
     |                                  |
  media(PCM16 8kHz) ---------->     _audio.py (PCM16 -> u-law)
     |                                  |
     |                              OpenAI Realtime WS
     |                                  |
     |                              session.update {
     |                                modalities: ["text","audio"],
     |                                voice, instructions,
     |                                input_audio_format: "g711_ulaw",
     |                                output_audio_format: "g711_ulaw",
     |                                turn_detection: { type: "semantic_vad" },
     |                                tools: [registered + MCP],
     |                              }
     |                                  |
     |                              input_audio_buffer.append(u-law)
     |                                  |
     |                              response.audio.delta(u-law)
     |                                  |
  media(PCM16 8kHz) <-----------    _audio.py (u-law -> PCM16)
     |                                  |
  speech_started  ------------>     truncation 처리
     |                                  | conversation.item.truncate
  clear  <-------------------------  오디오 큐 클리어
```

### Tool Call 처리

```
OpenAI: response.output_item.done (type: "function_call")
  -> ToolRegistry에서 핸들러 조회
  -> hang_up인 경우: call.hangup() 호출
  -> 일반 tool: handler(**args) 실행
  -> conversation.item.create (function_call_output)
  -> response.create (AI가 결과 기반으로 응답)
```

## 8. Security

### 8.1 인증 모델

Agent Listen 방식은 agent가 서버에 연결하므로 양방향 인증이 자동 완료됨.
기존 webhook signing(`signing_key`)은 불필요.

| | Webhook 방식 | Agent Listen 방식 |
|--|--|--|
| 연결 방향 | 서버 -> 유저 (서버가 유저 URL 호출) | 유저 -> 서버 (유저가 서버에 연결) |
| 공격 표면 | webhook URL이 공개됨 | 공개된 엔드포인트 없음 |
| 서버 신뢰 | 유저가 서명으로 확인해야 함 | TLS 인증서로 자동 확인 |
| 유저 신뢰 | 서명에 포함 안 됨 | Bearer token으로 확인 |
| signing_key | 필수 | 불필요 |

### 8.2 번호 소유권 검증 (서버 측)

Control WS 연결 시:
1. Bearer 토큰 -> account 인증
2. `db.findByNumber(number)` -> 번호 존재 확인
3. `numRecord.account_id === account.id` -> 소유권 확인
4. `agentRegistry.has(number)` -> 중복 연결 방지

본인 계정에 등록된 번호만 listen 가능. 타인의 번호는 `4003 Number not owned` 거부.

### 8.3 Media WS 보안

- Control WS에서 `call.incoming` 시 1회용 토큰 발급 (30초 만료)
- Media WS 연결 시 토큰 검증 후 즉시 삭제 (replay 방지)
- 토큰 없이는 Media WS 연결 불가

### 8.4 위협 및 대응

| 위협 | 대응 |
|------|------|
| 번호 갈취 | API key + 번호 소유권 검증 |
| 도청 (Media WS) | 1회용 토큰 + TLS 암호화 |
| 세션 하이재킹 | 번호당 agent 1개 제한, 중복 연결 거부 |
| 서비스 거부 | 계정당 rate limit, 동시 WS 수 제한 |
| Replay 공격 | Media 토큰 1회용, 30초 만료 |

## 9. ClawOps Server 변경 사항

### 9.1 새 WebSocket 엔드포인트 (cpaas-app)

- `GET /v1/accounts/:accountId/agent/listen` - Control WS
- `GET /v1/agent/media/:callId` - Media WS

### 9.2 call-handler.js 변경

```
handleInboundCall() 현재:
  db.findByNumber(to) -> webhookUrl -> callWebhook -> TwiML -> execute

handleInboundCall() 변경 후:
  db.findByNumber(to) -> agentWs = agentRegistry.get(to)
  if (agentWs) {
    // Agent Listen 모드: WebSocket으로 직접 라우팅
    agentWs.send({ event: "call.incoming", callId, from })
    // accept 응답 대기 -> Media WS 브릿지 생성
  } else {
    // 기존 TwiML webhook 방식 (fallback)
    callWebhook(webhookUrl) -> TwiML -> execute
  }
```

### 9.3 NGINX 변경

WebSocket 프록시 설정 추가 (`/v1/accounts/*/agent/*`, `/v1/agent/media/*`).

### 9.4 기존 시스템과의 공존

- Agent Listen이 연결되어 있으면 -> WS 라우팅
- 연결되어 있지 않으면 -> 기존 webhookUrl TwiML 방식 (fallback)
- 두 방식 완전 독립, 번호 단위로 결정

## 10. Environment Variables

기존 SDK 환경변수에 추가:

| Variable | Description | Required |
|----------|-------------|----------|
| `CLAWOPS_API_KEY` | ClawOps API key (기존) | Yes |
| `CLAWOPS_ACCOUNT_ID` | Account ID (기존) | Yes |
| `CLAWOPS_BASE_URL` | API base URL (기존) | No |
| `OPENAI_API_KEY` | OpenAI API key (Realtime 모드) | Realtime 모드 시 |

## 11. 기존 SDK와의 통합

| 항목 | 공유 방식 |
|------|----------|
| 인증 (api_key, account_id) | `AsyncClawOps` 클라이언트 인스턴스 공유 |
| base_url | REST: `https://` -> WS: `wss://` 자동 변환 |
| 에러 | `_exceptions.py`에 `AgentError`, `AgentConnectionError` 추가 |
| 타입 | `types/`에 agent 관련 타입 추가 |
| 환경변수 | 기존 `CLAWOPS_*` 그대로 사용 |
