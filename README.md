# ClawOps Python SDK

[ClawOps Voice API](https://api.claw-ops.com/docs)의 공식 Python 라이브러리입니다.

[![PyPI version](https://img.shields.io/pypi/v/clawops.svg)](https://pypi.org/project/clawops/)
[![Python 3.9+](https://img.shields.io/pypi/pyversions/clawops.svg)](https://pypi.org/project/clawops/)

## 설치

```bash
# REST API SDK만 사용
pip install clawops

# AI Agent 포함
pip install clawops[agent]

# 특정 프로바이더 포함
pip install clawops[agent,openai-llm,deepgram,elevenlabs,mcp]

# 전체 설치
pip install clawops[agent-all]
```

## AI Agent (음성 에이전트)

`ClawOpsAgent`를 사용하면 한 줄로 인바운드 전화를 AI로 처리할 수 있습니다. ngrok 없이 WebSocket 역방향 연결로 동작합니다.

```python
from clawops.agent import ClawOpsAgent, OpenAIRealtime
import asyncio

agent = ClawOpsAgent(
    from_="07012341234",
    session=OpenAIRealtime(
        system_prompt="친절한 상담원입니다. 고객의 질문에 답변해주세요.",
        voice="marin",
        language="ko",
    ),
)

@agent.tool
async def check_order(order_id: str) -> str:
    """주문 상태를 확인합니다."""
    return "배송 완료"

@agent.on("call_start")
async def on_start(call):
    print(f"통화 시작: {call.from_number} -> {call.to_number}")

asyncio.run(agent.serve())  # Ctrl+C로 종료
```

### MCP 서버 연동

MCP 서버를 연결하여 AI에게 외부 도구를 제공할 수 있습니다.

```bash
pip install clawops[mcp]
```

```python
from clawops.agent import ClawOpsAgent, OpenAIRealtime
from clawops.agent.mcp import MCPServerStdio, MCPServerHTTP
import asyncio

agent = ClawOpsAgent(
    from_="07012341234",
    session=OpenAIRealtime(
        system_prompt="상담원입니다.",
    ),
    mcp_servers=[
        MCPServerStdio("npx", args=["@modelcontextprotocol/server-google"], env={"GOOGLE_API_KEY": "..."}),
        MCPServerHTTP("https://my-mcp-server.com", headers={"Authorization": "Bearer token"}),
    ],
)

asyncio.run(agent.serve())  # Ctrl+C로 종료
```

MCP 서버는 전화가 올 때마다 자동으로 시작되고, 통화 종료 시 정리됩니다. MCP 서버가 제공하는 도구는 `@agent.tool`로 등록한 도구와 함께 세션에 자동 등록됩니다.

### 디버그 로깅

Agent의 내부 동작 (MCP 연결, 도구 등록, 도구 호출 등)을 확인하려면 로깅 레벨을 `DEBUG`로 설정하세요.

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 또는 clawops.agent 로거만 DEBUG로:
logging.getLogger("clawops.agent").setLevel(logging.DEBUG)
```

### OpenTelemetry Tracing

통화 흐름, MCP 도구 호출, LLM 세션을 OpenTelemetry로 추적할 수 있습니다.

```bash
pip install clawops[tracing]
# + 원하는 exporter
pip install opentelemetry-sdk opentelemetry-exporter-otlp
```

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

from clawops.agent.tracing import TracingConfig

agent = ClawOpsAgent(
    ...,
    tracing=TracingConfig(),
)
```

**Span 계층:**
- `call` → `mcp.connect` → `llm.session` → `tool.call` → `mcp.call_tool`

> 자세한 사용법은 **[Agent 문서](docs/agent/)** 를 참고하세요. (Tool, 이벤트, 통화 녹음, 파이프라인 모드, 커스텀 제공자, MCP 연동, Tracing 등)

## REST API 사용법

```python
from clawops import ClawOps

client = ClawOps(
    api_key="sk_...",          # 또는 CLAWOPS_API_KEY 환경변수 사용
    account_id="AC1a2b3c4d",   # 또는 CLAWOPS_ACCOUNT_ID 환경변수 사용
)
```

### 통화 (Calls)

```python
# 발신 전화 생성
call = client.calls.create(
    to="01012345678",
    from_="07052358010",
    url="https://my-app.com/twiml",
    status_callback="https://my-app.com/status",
    status_callback_event="initiated ringing answered completed",
)
print(call.call_id)

# 통화 목록 조회 (페이지네이션)
page = client.calls.list(status="completed", page=0, page_size=20)
for call in page:
    print(call.call_id, call.status)

# 모든 통화를 자동으로 순회
for call in client.calls.list().auto_paging_iter():
    print(call.call_id)

# 특정 통화 조회
call = client.calls.get("CAabcdef1234567890")

# 통화 종료
call = client.calls.update("CAabcdef1234567890", status="completed")
```

### 전화번호 (Numbers)

```python
# 번호 구매
number = client.numbers.create(source="pool")
print(number.phone_number)

# 번호 목록 조회
numbers = client.numbers.list()

# 웹훅 URL 변경
number = client.numbers.update("07012340001", webhook_url="https://my-app.com/webhook")

# 번호 해제
client.numbers.delete("07012340001")
```

### 메시지 (Messages)

```python
# SMS 발송
msg = client.messages.create(
    to="01012345678",
    from_="07052358010",
    body="안녕하세요",
)
print(msg.message_id)

# MMS 발송
msg = client.messages.create(
    to="01012345678",
    from_="07052358010",
    body="사진 첨부",
    type="mms",
    subject="제목",
)

# LMS (장문 문자) 발송
message = client.messages.create(
    to="01012345678",
    from_="07052358010",
    body="긴 내용의 메시지입니다...",
    type="lms",
    subject="알림",
)

# 메시지 목록 조회 (필터링)
page = client.messages.list(type="sms", status="sent", page=0, page_size=20)
for msg in page:
    print(msg.message_id, msg.status)

# 모든 메시지를 자동으로 순회
for msg in client.messages.list().auto_paging_iter():
    print(msg.message_id)

# 특정 메시지 조회
msg = client.messages.get("MG0123456789abcdef")
```

### 멀티 계정 접근

```python
# 다른 계정의 리소스에 접근
other = client.accounts("AC_other_account_id")
other.calls.list()
other.numbers.list()
other.messages.list()
```

## 비동기 사용법

```python
from clawops import AsyncClawOps

# async context manager 사용
async with AsyncClawOps(api_key="sk_...", account_id="AC1a2b3c4d") as client:
    call = await client.calls.create(
        to="01012345678",
        from_="07052358010",
        url="https://my-app.com/twiml",
    )
    print(call.call_id)

    # 모든 리소스 메서드는 비동기 버전을 제공합니다
    page = await client.calls.list(status="completed")
    async for call in page.auto_paging_iter():
        print(call.call_id)

    # 메시지 발송
    msg = await client.messages.create(
        to="01012345678", from_="07052358010", body="안녕하세요",
    )
```

## 웹훅 서명 검증

```python
client.webhooks.verify(
    url="https://my-app.com/webhook",
    params={"CallId": "CA...", "CallStatus": "completed"},
    signature=request.headers["X-Signature"],
    signing_key="your_account_signing_key",
)
```

서명이 유효하지 않으면 `WebhookVerificationError`가 발생합니다.

## 에러 처리

```python
from clawops import ClawOps, BadRequestError, AuthenticationError, NotFoundError

client = ClawOps()

try:
    call = client.calls.create(to="01012345678", from_="07052358010", url="https://...")
except BadRequestError as e:
    print(f"잘못된 요청: {e.status_code} - {e.body}")
except AuthenticationError as e:
    print(f"유효하지 않은 API 키: {e.status_code}")
except NotFoundError as e:
    print(f"리소스를 찾을 수 없음: {e.status_code}")
```

모든 에러는 `ClawOpsError`를 상속합니다. HTTP 에러는 `status_code`, `response`, `body`, `request` 속성을 제공합니다.

| 에러                       | 상태 코드 |
| -------------------------- | --------- |
| `BadRequestError`          | 400       |
| `AuthenticationError`      | 401       |
| `PermissionDeniedError`    | 403       |
| `NotFoundError`            | 404       |
| `ConflictError`            | 409       |
| `UnprocessableEntityError` | 422       |
| `InternalServerError`      | 500+      |
| `ServiceUnavailableError`  | 503       |

## 설정

### 재시도

기본적으로 `408`, `409`, `429`, `500+` 에러 시 지수 백오프로 최대 2회 재시도합니다.

```python
client = ClawOps(max_retries=5)

# 재시도 비활성화
client = ClawOps(max_retries=0)
```

### 타임아웃

기본 타임아웃은 600초 (연결 타임아웃 5초)입니다. 클라이언트 또는 요청 단위로 변경할 수 있습니다:

```python
# 클라이언트 단위
client = ClawOps(timeout=30.0)

# 요청 단위
call = client.calls.create(..., timeout=10.0)
```

### 커스텀 HTTP 클라이언트

프록시, 커스텀 인증서 등 고급 설정이 필요한 경우 `httpx.Client`를 직접 주입할 수 있습니다:

```python
import httpx

client = ClawOps(
    http_client=httpx.Client(proxies="http://proxy.example.com:8080"),
)
```

## 환경변수

| 변수                 | 설명                   | 필수 여부                                   |
| -------------------- | ---------------------- | ------------------------------------------- |
| `CLAWOPS_API_KEY`    | API 키 (`sk_...`)      | 예 (생성자에 전달하지 않은 경우)            |
| `CLAWOPS_ACCOUNT_ID` | 기본 계정 ID (`AC...`) | 예 (생성자에 전달하지 않은 경우)            |
| `CLAWOPS_BASE_URL`   | API 기본 URL           | 아니오 (기본값: `https://api.claw-ops.com`) |
| `OPENAI_API_KEY`     | OpenAI API 키          | OpenAI Realtime 사용 시                     |
| `GOOGLE_API_KEY`     | Google API 키          | Gemini Realtime 사용 시                     |

## 문서

- **[AI Agent 가이드](docs/agent/)** — 음성 에이전트 상세 사용법, 파이프라인 모드, 커스텀 제공자, MCP 연동

## 다른 언어

| 언어 | 패키지 | 저장소 |
|------|--------|--------|
| Node.js / TypeScript | [`@teamlearners/clawops`](https://www.npmjs.com/package/@teamlearners/clawops) | [clawops-node](https://github.com/learners-superpumped/clawops-node) |

## 요구사항

- Python 3.9+
- `httpx` >= 0.23.0
- `pydantic` >= 2.0.0
- `aiohttp` >= 3.9.0 (Agent 사용 시)

## 라이선스

Apache-2.0
