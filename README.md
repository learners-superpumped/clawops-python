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
from clawops.agent import ClawOpsAgent

agent = ClawOpsAgent(
    from_="07012341234",          # 수신 번호
    system_prompt="친절한 상담원입니다. 고객의 질문에 답변해주세요.",
    voice="ash",                  # OpenAI 음성
    language="ko",
)

@agent.tool
async def check_order(order_id: str) -> str:
    """주문 상태를 확인합니다."""
    return "배송 완료"

@agent.on("call_start")
async def on_start(call):
    print(f"통화 시작: {call.from_number} -> {call.to_number}")

agent.listen()  # WebSocket 연결 후 인바운드 대기
```

> 자세한 사용법은 **[Agent 문서](docs/agent.md)** 를 참고하세요.

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

### SIP 자격증명 (SIP Credentials)

```python
# SIP 자격증명 생성
cred = client.sip.credentials.create(display_name="Office Phone")
print(cred.credential_id, cred.sip_username)

# 자격증명 목록 조회
creds = client.sip.credentials.list()

# 특정 자격증명 조회
cred = client.sip.credentials.get("clu1abc2def3ghi")

# 자격증명 삭제
client.sip.credentials.delete("clu1abc2def3ghi")
```

### 멀티 계정 접근

```python
# 다른 계정의 리소스에 접근
other = client.accounts("AC_other_account_id")
other.calls.list()
other.numbers.list()
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
| `OPENAI_API_KEY`     | OpenAI API 키          | Agent 사용 시 (생성자에 전달하지 않은 경우) |

## 문서

- **[AI Agent 가이드](docs/agent.md)** — 음성 에이전트 상세 사용법, 파이프라인 모드, MCP 연동
- **[설계 문서](docs/plans/2026-03-06-clawops-agent-design.md)** — Agent 시스템 아키텍처 설계

## 요구사항

- Python 3.9+
- `httpx` >= 0.23.0
- `pydantic` >= 2.0.0
- `aiohttp` >= 3.9.0 (Agent 사용 시)

## 라이선스

Apache-2.0
