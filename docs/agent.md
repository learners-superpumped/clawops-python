# ClawOps Agent - AI 음성 에이전트 가이드

`ClawOpsAgent`는 인바운드 전화를 AI로 자동 처리하는 프레임워크입니다. WebSocket 역방향 연결 방식으로 ngrok 없이 로컬에서 바로 실행할 수 있습니다.

## 목차

- [설치](#설치)
- [빠른 시작](#빠른-시작)
- [동작 원리](#동작-원리)
- [설정 옵션](#설정-옵션)
- [Tool (함수 호출)](#tool-함수-호출)
- [이벤트 핸들러](#이벤트-핸들러)
- [통화 녹음](#통화-녹음)
- [파이프라인 모드 (커스텀 STT/LLM/TTS)](#파이프라인-모드-커스텀-sttllmtts)
- [MCP 서버 연동](#mcp-서버-연동)
- [CallSession](#callsession)
- [환경변수](#환경변수)
- [에러 처리](#에러-처리)
- [아키텍처](#아키텍처)

---

## 설치

```bash
# 기본 (OpenAI Realtime 모드)
pip install clawops[agent]

# 특정 프로바이더 포함
pip install clawops[agent,deepgram,elevenlabs,openai-llm]

# MCP 서버 지원 포함
pip install clawops[agent,mcp]

# 전체 설치
pip install clawops[agent-all]
```

## 빠른 시작

```python
from clawops.agent import ClawOpsAgent

agent = ClawOpsAgent(
    from_="07012341234",
    system_prompt="친절한 고객센터 상담원입니다. 고객의 질문에 답변해주세요.",
)

agent.listen()
```

이것만으로 `07012341234` 번호로 걸려오는 전화를 OpenAI Realtime API가 처리합니다.

### 환경변수 설정

```bash
export CLAWOPS_API_KEY="sk_..."
export CLAWOPS_ACCOUNT_ID="AC..."
export OPENAI_API_KEY="sk-..."
```

## 동작 원리

```
┌──────────────┐    Control WS     ┌──────────────┐
│  ClawOpsAgent │◄─────────────────►│ ClawOps 서버  │
│  (로컬 실행)  │    Media WS (콜별) │              │
│              │◄─────────────────►│              │
└──────┬───────┘                   └──────────────┘
       │
       ▼
┌──────────────┐
│ OpenAI       │
│ Realtime API │
└──────────────┘
```

1. **Agent가 서버에 연결** — Control WebSocket으로 역방향 연결 (ngrok 불필요)
2. **전화 수신 알림** — 서버가 `call.incoming` 이벤트 전송
3. **미디어 스트림 연결** — 콜별 Media WebSocket으로 오디오 스트리밍
4. **AI 처리** — OpenAI Realtime API로 음성 대화 (Speech-to-Speech)
5. **Tool 호출** — AI가 필요 시 등록된 함수 자동 호출

## 설정 옵션

```python
agent = ClawOpsAgent(
    # 필수
    from_="07012341234",              # 수신 번호

    # 인증 (환경변수 대체 가능)
    api_key="sk_...",                 # CLAWOPS_API_KEY
    account_id="AC...",               # CLAWOPS_ACCOUNT_ID
    openai_api_key="sk-...",          # OPENAI_API_KEY

    # AI 설정
    system_prompt="상담원입니다.",      # AI 시스템 프롬프트
    voice="marin",                    # 음성: marin, ash, ballad, coral, sage, verse 등
    model="gpt-realtime-mini",        # OpenAI 모델
    language="ko",                    # 언어 (음성 인식용)
    eagerness="high",                 # 응답 적극성: low, medium, high, auto
    greeting=True,                    # 첫 인사 자동 생성 여부

    # 녹음
    recording=True,                       # 통화 녹음 활성화
    recording_path="./recordings",        # 저장 경로 (기본값: ./recordings)

    # 고급
    base_url="https://api.claw-ops.com",  # API 엔드포인트
)
```

### 음성 옵션

| 음성 | 특징 |
|------|------|
| `marin` | 기본값, 자연스러운 여성 음성 |
| `ash` | 자연스러운 남성 음성 |
| `ballad` | 부드러운 남성 음성 |
| `coral` | 밝은 여성 음성 |
| `sage` | 차분한 여성 음성 |
| `verse` | 중성적 음성 |

## Tool (함수 호출)

`@agent.tool` 데코레이터로 AI가 호출할 수 있는 함수를 등록합니다. LiveKit Agents 스타일의 API입니다.

```python
@agent.tool
async def check_order(order_id: str) -> str:
    """주문 상태를 확인합니다.

    고객이 주문 번호를 말하면 이 함수를 호출하세요.
    """
    order = await db.get_order(order_id)
    return f"주문 {order_id}는 {order.status} 상태입니다."


@agent.tool
async def transfer_to_agent(department: str) -> str:
    """상담원에게 연결합니다."""
    return f"{department} 부서로 연결합니다."


@agent.tool
async def get_business_hours() -> str:
    """영업시간을 안내합니다."""
    return "평일 09:00-18:00, 주말 휴무입니다."
```

### Tool 작성 규칙

- 함수는 반드시 `async`여야 합니다
- 반환 타입은 `str`이어야 합니다
- **docstring이 AI에게 함수 설명으로 전달됩니다** — 상세하게 작성하세요
- 파라미터 타입 힌트(`str`, `int`, `float`, `bool`)가 자동으로 JSON Schema로 변환됩니다
- 기본값이 있는 파라미터는 optional로 처리됩니다

```python
@agent.tool
async def search_products(
    query: str,            # required
    category: str = "",    # optional
    limit: int = 10,       # optional
) -> str:
    """상품을 검색합니다. 고객이 상품을 찾을 때 사용하세요."""
    results = await product_api.search(query, category, limit)
    return "\n".join(f"- {r.name}: {r.price}원" for r in results)
```

### 내장 Tool: hang_up

`hang_up`은 자동으로 등록되는 내장 Tool입니다. AI가 대화가 끝났다고 판단하면 자동으로 전화를 종료합니다.

## 이벤트 핸들러

`@agent.on()` 데코레이터로 통화 이벤트를 수신합니다.

```python
@agent.on("call_start")
async def on_call_start(call):
    """통화가 시작될 때 호출됩니다."""
    print(f"통화 시작: {call.from_number} -> {call.to_number}")
    print(f"통화 ID: {call.call_id}")

@agent.on("call_end")
async def on_call_end(call):
    """통화가 종료될 때 호출됩니다."""
    print(f"통화 종료: {call.call_id} (총 {call.duration:.1f}초)")

@agent.on("transcript")
async def on_transcript(call, role, text):
    """음성 인식/합성 텍스트가 생성될 때 호출됩니다."""
    print(f"[{role}] {text}")
    # role: "user" (고객 음성 인식) 또는 "assistant" (AI 응답)
```

### 이벤트 목록

| 이벤트 | 파라미터 | 설명 |
|--------|----------|------|
| `call_start` | `(call)` | 통화 시작 |
| `call_end` | `(call)` | 통화 종료 |
| `transcript` | `(call, role, text)` | 음성 텍스트 생성 |

## 통화 녹음

`recording=True`로 통화를 실시간 녹음할 수 있습니다. 통화마다 3개 WAV 파일(PCM16 8kHz mono)이 생성됩니다.

```python
agent = ClawOpsAgent(
    from_="07012341234",
    system_prompt="상담원입니다.",
    recording=True,
    recording_path="./recordings",  # 기본값
)
```

### 생성되는 파일

| 파일 | 내용 |
|------|------|
| `{call_id}_in.wav` | 발신자 음성 (수신 오디오) |
| `{call_id}_out.wav` | AI 응답 (송신 오디오) |
| `{call_id}_mix.wav` | 양방향 믹스 |

### 동작 원리

- 수신 오디오(발신자)가 타임라인 역할을 합니다
- 송신 오디오(AI 응답)는 버퍼에 쌓이고, 수신 청크가 올 때마다 같은 길이만큼 꺼내서 샘플 단위로 믹스합니다
- 별도 시간 관리 없이 자연스럽게 정렬됩니다
- 파일은 실시간으로 기록되므로 통화 중 디스크에 바로 저장됩니다
- 통화 종료 시 WAV 헤더가 최종 크기로 업데이트됩니다

## 파이프라인 모드 (커스텀 STT/LLM/TTS)

OpenAI Realtime 대신 직접 STT, LLM, TTS 프로바이더를 조합할 수 있습니다.

### Protocol 인터페이스

```python
from clawops.agent.pipeline import STT, LLM, TTS
```

각 프로바이더는 다음 Protocol을 구현하면 됩니다:

```python
class STT(Protocol):
    async def transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """오디오 스트림(PCM16 8kHz) -> 텍스트 스트림."""
        ...

class LLM(Protocol):
    async def generate(
        self, messages: list[dict], tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """메시지 -> 텍스트 응답 스트림."""
        ...

class TTS(Protocol):
    async def synthesize(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """텍스트 스트림 -> 오디오(PCM16 8kHz) 스트림."""
        ...
```

### 커스텀 프로바이더 예시

```python
class MySTT:
    async def transcribe(self, audio_stream):
        # Deepgram, Whisper 등으로 구현
        async for chunk in audio_stream:
            text = await my_stt_api.recognize(chunk)
            if text:
                yield text

class MyLLM:
    async def generate(self, messages, tools=None):
        # OpenAI, Claude 등으로 구현
        async for token in my_llm_api.stream(messages):
            yield token

class MyTTS:
    async def synthesize(self, text_stream):
        # ElevenLabs, Google TTS 등으로 구현
        async for text in text_stream:
            audio = await my_tts_api.speak(text)
            yield audio

agent = ClawOpsAgent(
    from_="07012341234",
    stt=MySTT(),
    llm=MyLLM(),
    tts=MyTTS(),
)
```

## MCP 서버 연동

MCP 서버를 연결하여 AI에게 외부 도구를 제공할 수 있습니다.

### 설치

MCP 연동을 사용하려면 `mcp` extra를 설치해야 합니다:

```bash
pip install clawops[mcp]

# 또는 agent와 함께
pip install clawops[agent,mcp]

# 전체 설치 시 mcp 포함
pip install clawops[agent-all]
```

> `mcp` 패키지 없이 `mcp_servers`를 설정하면 `AgentError: MCP 서버를 사용하려면 pip install clawops[mcp] 를 실행하세요.` 에러가 발생합니다.

### 사용법

```python
from clawops.agent.mcp import MCPServerHTTP, MCPServerStdio

agent = ClawOpsAgent(
    from_="07012341234",
    system_prompt="상담원입니다.",
    mcp_servers=[
        # HTTP/SSE 기반 MCP 서버
        MCPServerHTTP(
            "https://my-mcp-server.com",
            headers={"Authorization": "Bearer token"},
        ),
        # Stdio 기반 MCP 서버 (subprocess로 실행)
        MCPServerStdio(
            "npx",
            args=["@modelcontextprotocol/server-google"],
            env={"GOOGLE_API_KEY": "..."},
        ),
    ],
)
```

### 동작 방식

MCP 서버는 **전화가 올 때마다** 자동으로 시작되고, **통화 종료 시** 정리됩니다:

1. 전화 수신 → MCP 서버 프로세스 시작 (Stdio) 또는 HTTP 연결
2. MCP 프로토콜로 `tools/list` 호출 → 사용 가능한 도구 목록 수집
3. `@agent.tool`로 등록한 도구와 함께 OpenAI Realtime에 자동 등록
4. AI가 MCP 도구를 호출하면 → MCP 프로토콜로 `tools/call` 전달
5. 통화 종료 → MCP 서버 연결 종료 및 도구 정리

### 주의사항

- `@agent.tool`과 MCP 도구의 이름이 충돌하면 `AgentError`가 발생합니다
- MCP 서버 연결이 실패하면 해당 통화의 AI 처리가 시작되지 않습니다

## 디버그 로깅

Agent의 내부 동작을 확인하려면 로깅 레벨을 `DEBUG`로 설정하세요:

```python
import logging
logging.getLogger("clawops.agent").setLevel(logging.DEBUG)
```

MCP 연결, 도구 등록/호출, WebSocket 연결 등의 상세 로그를 확인할 수 있습니다.

## CallSession

`CallSession`은 개별 통화의 상태를 관리합니다. 이벤트 핸들러의 `call` 파라미터로 전달됩니다.

### 속성

| 속성 | 타입 | 설명 |
|------|------|------|
| `call_id` | `str` | 통화 ID |
| `from_number` | `str` | 발신 번호 |
| `to_number` | `str` | 수신 번호 |
| `account_id` | `str` | 계정 ID |
| `start_time` | `datetime` | 통화 시작 시간 |
| `duration` | `float` | 통화 경과 시간 (초) |
| `metadata` | `dict` | 사용자 정의 메타데이터 |

### 메서드

```python
@agent.on("call_start")
async def on_start(call):
    # 사용자 정의 메타데이터 저장
    call.metadata["customer_id"] = "CUST_123"

    # 오디오 전송
    await call.send_audio(pcm16_bytes)

    # 오디오 큐 초기화 (인터럽트 시)
    await call.clear_audio()

    # 통화 종료
    await call.hangup()
```

## 환경변수

| 변수 | 설명 | 필수 여부 |
|------|------|-----------|
| `CLAWOPS_API_KEY` | ClawOps API 키 (`sk_...`) | 예 |
| `CLAWOPS_ACCOUNT_ID` | 계정 ID (`AC...`) | 예 |
| `OPENAI_API_KEY` | OpenAI API 키 | Realtime 모드 사용 시 |
| `CLAWOPS_BASE_URL` | API 기본 URL | 아니오 (기본값: `https://api.claw-ops.com`) |

## 에러 처리

```python
from clawops._exceptions import AgentError, AgentConnectionError

try:
    agent.listen()
except AgentConnectionError as e:
    print(f"서버 연결 실패: {e}")
except AgentError as e:
    print(f"에이전트 에러: {e}")
except KeyboardInterrupt:
    print("에이전트 종료")
```

| 에러 | 설명 |
|------|------|
| `AgentError` | Agent 관련 에러의 베이스 클래스 |
| `AgentConnectionError` | WebSocket 연결 실패 |

## 아키텍처

```
ClawOpsAgent
├── ControlWebSocket        # 서버 연결 (상시, auto-reconnect)
│   ├── call.incoming       # 인바운드 콜 알림 수신
│   └── call.ended          # 콜 종료 알림 수신
│
├── MediaWebSocket (콜별)   # 오디오 스트리밍
│   ├── start               # 미디어 스트림 시작
│   ├── media               # PCM16 8kHz base64 오디오
│   └── stop                # 미디어 스트림 종료
│
├── RealtimeSession (콜별)  # OpenAI Realtime API
│   ├── session.update      # 세션 설정 (음성, 도구 등)
│   ├── audio bridging      # PCM16 ↔ G.711 μ-law 변환
│   ├── tool calls          # 등록된 함수 자동 호출
│   └── truncation          # 인터럽트 처리
│
├── ToolRegistry            # @agent.tool 함수 관리
│   ├── register            # 데코레이터로 함수 등록
│   ├── to_openai_tools()   # JSON Schema 자동 생성
│   └── call()              # 이름으로 함수 호출
│
├── AudioRecorder (콜별)    # 실시간 녹음 (recording=True 시)
│   ├── write_inbound()     # 수신 오디오 → _in.wav + _mix.wav
│   ├── write_outbound()    # 송신 오디오 → _out.wav + mix 버퍼
│   └── stop()              # WAV 헤더 업데이트
│
├── CallSession (콜별)      # 통화 상태 관리
│   ├── audio_stream()      # 수신 오디오 스트림
│   ├── send_audio()        # 응답 오디오 전송
│   └── hangup()            # 통화 종료
│
└── Pipeline (선택)         # 커스텀 STT/LLM/TTS
    ├── STT Protocol        # 음성 → 텍스트
    ├── LLM Protocol        # 텍스트 → 응답
    └── TTS Protocol        # 텍스트 → 음성
```

### 보안 모델

- **인증**: Bearer 토큰 (API 키) + TLS 암호화
- **번호 소유권 검증**: API 키 → 계정 → 번호 소유 확인
- **미디어 토큰**: 1회용 토큰 (30초 만료), Control WS를 통해 발급
- **Webhook 서명 불필요**: Agent가 서버에 직접 연결하므로 별도 서명 검증 없음

---

> REST API 사용법은 [README.md](../README.md)를 참고하세요.
