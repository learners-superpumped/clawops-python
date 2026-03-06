# ClawOps Python SDK Design Document

**Date:** 2026-03-06
**Status:** Approved

## Overview

ClawOps Voice API (`https://api.claw-ops.com`)의 공식 Python SDK.
OpenAI Python SDK의 핵심 아키텍처 패턴을 차용하되, ClawOps API 규모에 맞게 실용적으로 구성한다.

## Key Decisions

| 항목 | 결정 |
|------|------|
| 패키지명 | `clawops` (pip install clawops) |
| 빌드 시스템 | pyproject.toml + hatchling |
| Python 버전 | 3.9+ |
| HTTP 클라이언트 | httpx (sync/async) |
| 타입 시스템 | TypedDict (request) + Pydantic v2 (response) |
| 클라이언트 스타일 | Twilio 스타일 — `client.accounts("AC_other").calls.list()` |
| Sync/Async | 둘 다 제공 — `ClawOps`, `AsyncClawOps` |
| 디자인 접근 | OpenAI SDK 핵심 패턴 채택 (full mirror 아님) |

## 1. Package Structure

```
src/clawops/
├── __init__.py                  # ClawOps, AsyncClawOps, errors, types export
├── _client.py                   # ClawOps(SyncAPIClient), AsyncClawOps(AsyncAPIClient)
├── _base_client.py              # SyncAPIClient, AsyncAPIClient (httpx wrapping, retry, auth)
├── _resource.py                 # SyncAPIResource, AsyncAPIResource base classes
├── _exceptions.py               # Error hierarchy
├── _constants.py                # DEFAULT_TIMEOUT, DEFAULT_MAX_RETRIES, etc.
├── _utils.py                    # maybe_transform, to_camel_case, etc.
├── pagination.py                # SyncPage, AsyncPage
├── webhooks.py                  # Webhook signature verification
├── resources/
│   ├── __init__.py
│   ├── accounts.py              # Accounts resource (multi-account access)
│   ├── calls.py                 # Calls resource (CRUD)
│   ├── numbers.py               # Numbers resource (CRUD)
│   └── sip/
│       ├── __init__.py
│       └── credentials.py       # SipCredentials resource
├── types/
│   ├── __init__.py
│   ├── call.py                  # Call, CallCreateParams, CallListParams, etc.
│   ├── number.py                # PhoneNumber, NumberCreateParams, etc.
│   ├── sip/
│   │   ├── __init__.py
│   │   └── credential.py        # SipCredential, SipCredentialCreateParams, etc.
│   └── shared.py                # PaginationMeta, etc.
└── py.typed                     # PEP 561 marker
```

## 2. Client Initialization & Resource Access

```python
from clawops import ClawOps, AsyncClawOps

# Basic usage
client = ClawOps(
    api_key="sk_...",              # or CLAWOPS_API_KEY env var
    account_id="AC1a2b3c4d",       # or CLAWOPS_ACCOUNT_ID env var
    base_url="https://api.claw-ops.com",  # default
    timeout=30.0,                  # default 600s
    max_retries=2,                 # default 2
    http_client=None,              # custom httpx.Client injection
)

# Resource access — default account
client.calls.create(to="01012345678", from_="07052358010", url="https://...")
client.calls.list(status="completed", page=0, page_size=20)
client.calls.get("CAabcdef1234567890")
client.calls.update("CAabcdef1234567890", status="completed")

client.numbers.create(source="pool")
client.numbers.list()
client.numbers.update("07012340001", webhook_url="https://...")
client.numbers.delete("07012340001")

client.sip.credentials.create(display_name="Office Phone")
client.sip.credentials.list()
client.sip.credentials.get("clu1abc2def3ghi")
client.sip.credentials.delete("clu1abc2def3ghi")

# Multi-account access (Twilio style)
other = client.accounts("AC_other_id")
other.calls.list()
other.numbers.list()

# Async usage
async_client = AsyncClawOps(api_key="sk_...", account_id="AC...")
call = await async_client.calls.create(...)
await async_client.close()

# Context manager
async with AsyncClawOps(api_key="sk_...") as client:
    calls = await client.calls.list()
```

## 3. Type System (OpenAI SDK Style)

### Request Parameters — TypedDict

```python
# types/call.py
from typing import Required, Annotated
from typing_extensions import TypedDict

class CallCreateParams(TypedDict, total=False):
    to: Required[str]
    """수신 전화번호 또는 SIP URI."""
    from_: Required[Annotated[str, PropertyInfo(alias="From")]]
    """발신 전화번호. 계정에 등록된 번호여야 합니다."""
    url: Required[Annotated[str, PropertyInfo(alias="Url")]]
    """통화 제어 TwiML을 반환하는 URL."""
    status_callback: Annotated[str, PropertyInfo(alias="StatusCallback")]
    """통화 상태 변경 시 호출되는 콜백 URL."""
    status_callback_event: Annotated[str, PropertyInfo(alias="StatusCallbackEvent")]
    """수신할 상태 이벤트 목록 (공백 구분)."""

class CallListParams(TypedDict, total=False):
    status: str
    """필터링할 통화 상태: queued, ringing, in-progress, completed, failed."""
    page: int
    """0-based 페이지 번호."""
    page_size: Annotated[int, PropertyInfo(alias="pageSize")]
    """페이지당 항목 수 (기본 20, 최대 100)."""

class CallUpdateParams(TypedDict, total=False):
    status: Required[str]
    """변경할 통화 상태. 현재 'completed'만 지원."""
```

### Response Models — Pydantic BaseModel

```python
from pydantic import ConfigDict
from .._models import BaseModel

class Call(BaseModel):
    """통화 정보를 나타내는 모델."""
    call_id: str
    status: str
    to: str
    from_: str  # alias="from" via alias_generator
    direction: str
    duration: Optional[int] = None
    account_id: str
    date_created: datetime
    date_updated: Optional[datetime] = None

# Custom BaseModel with auto camelCase
class BaseModel(pydantic.BaseModel):
    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel_case,
        populate_by_name=True,
    )
```

### Resource Method Signatures

```python
class Calls(SyncAPIResource):
    def create(
        self,
        *,
        to: str,
        from_: str,
        url: str,
        status_callback: str | None = None,
        status_callback_event: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> Call:
        """발신 전화를 생성합니다.

        Args:
            to: 수신 전화번호 (예: "01012345678") 또는 SIP URI.
            from_: 발신 전화번호. 계정에 등록된 번호여야 합니다.
            url: 통화 연결 시 TwiML 명령을 반환하는 URL.
            status_callback: 통화 상태 변경 시 POST 요청을 받을 URL.
            status_callback_event: 수신할 이벤트 (예: "initiated ringing answered completed").
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초). 클라이언트 기본값을 오버라이드.

        Returns:
            생성된 Call 객체.

        Raises:
            BadRequestError: From 번호가 계정에 등록되지 않았거나 필수 필드 누락.
            AuthenticationError: 유효하지 않은 API 키.
            PermissionDeniedError: accountId 불일치.
            ServiceUnavailableError: ARI 서비스 준비되지 않음.
        """
        return self._post(
            f"/v1/accounts/{self._account_id}/calls",
            body=maybe_transform({
                "To": to,
                "From": from_,
                "Url": url,
                "StatusCallback": status_callback,
                "StatusCallbackEvent": status_callback_event,
            }, CallCreateParams),
            cast_to=Call,
        )
```

## 4. Error Hierarchy

```
Exception
└── ClawOpsError
    ├── APIError
    │   ├── APIStatusError
    │   │   ├── BadRequestError (400)
    │   │   ├── AuthenticationError (401)
    │   │   ├── PermissionDeniedError (403)
    │   │   ├── NotFoundError (404)
    │   │   ├── ConflictError (409)
    │   │   ├── UnprocessableEntityError (422)
    │   │   ├── InternalServerError (500+)
    │   │   └── ServiceUnavailableError (503)
    │   ├── APIConnectionError
    │   │   └── APITimeoutError
    │   └── APIResponseValidationError
```

Each error exposes: `status_code`, `response` (httpx.Response), `body` (parsed JSON), `request` (httpx.Request).

## 5. Pagination

```python
class SyncPage(BaseModel, Generic[_T]):
    data: list[_T]
    meta: PaginationMeta

    def has_next_page(self) -> bool: ...
    def next_page(self) -> "SyncPage[_T]": ...
    def __iter__(self) -> Iterator[_T]: ...
    def auto_paging_iter(self) -> Iterator[_T]:
        """모든 페이지의 항목을 자동으로 순회합니다."""

class AsyncPage(BaseModel, Generic[_T]):
    # async mirror
    async def next_page(self) -> "AsyncPage[_T]": ...
    async def auto_paging_iter(self) -> AsyncIterator[_T]: ...
```

Pagination applies to `GET /calls` only. Other list endpoints return plain `list[Model]`.

## 6. Webhook Signature Verification

```python
client.webhooks.verify(
    url="https://my-app.com/webhook",
    params={"CallId": "CA...", "CallStatus": "completed"},
    signature=request.headers["X-Signature"],
    signing_key="account_signing_key",
)
```

HMAC-SHA1 with Base64 encoding. Parameters sorted alphabetically, concatenated as `key1value1key2value2...`.

Raises `WebhookVerificationError` on failure.

## 7. BaseClient (httpx Wrapper)

### Features
- **Authentication:** Bearer token in Authorization header
- **User-Agent:** `clawops-python/{version}`
- **Retry:** Exponential backoff with jitter (0.5s, 1s, 2s, 4s, max 8s)
  - Retries on: 408, 409, 429, 500+
  - Default 2 retries
- **Timeout:** Default 600s total, 5s connect
- **Error Mapping:** HTTP status code -> typed exception
- **Per-request overrides:** `extra_headers`, `extra_query`, `timeout`
- **Custom httpx.Client injection**
- **Context manager support** (sync and async)

### Convenience Methods
- `_get(path, *, cast_to, **kwargs)`
- `_post(path, *, body, cast_to, **kwargs)`
- `_put(path, *, body, cast_to, **kwargs)`
- `_delete(path, **kwargs)`

## 8. API Endpoints Mapping

| SDK Method | HTTP | Path | Request | Response |
|-----------|------|------|---------|----------|
| `calls.create()` | POST | `/v1/accounts/{id}/calls` | CallCreateParams | Call |
| `calls.list()` | GET | `/v1/accounts/{id}/calls` | CallListParams | SyncPage[Call] |
| `calls.get(call_id)` | GET | `/v1/accounts/{id}/calls/{callId}` | - | Call |
| `calls.update(call_id)` | POST | `/v1/accounts/{id}/calls/{callId}` | CallUpdateParams | Call |
| `numbers.create()` | POST | `/v1/accounts/{id}/numbers` | NumberCreateParams | PhoneNumber |
| `numbers.list()` | GET | `/v1/accounts/{id}/numbers` | - | NumberListResponse |
| `numbers.update(number)` | PUT | `/v1/accounts/{id}/numbers/{num}` | NumberUpdateParams | PhoneNumber |
| `numbers.delete(number)` | DELETE | `/v1/accounts/{id}/numbers/{num}` | - | None |
| `sip.credentials.create()` | POST | `/v1/accounts/{id}/sip/credentials` | SipCredentialCreateParams | SipCredential |
| `sip.credentials.list()` | GET | `/v1/accounts/{id}/sip/credentials` | - | SipCredentialListResponse |
| `sip.credentials.get(id)` | GET | `/v1/accounts/{id}/sip/credentials/{cid}` | - | SipCredential |
| `sip.credentials.delete(id)` | DELETE | `/v1/accounts/{id}/sip/credentials/{cid}` | - | None |

## 9. Dependencies

```toml
[project]
requires-python = ">=3.9"
dependencies = [
    "httpx>=0.23.0,<1",
    "pydantic>=2.0.0,<3",
    "typing-extensions>=4.7.0",
]
```

## 10. Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `CLAWOPS_API_KEY` | API key (sk_...) | Yes (if not passed) |
| `CLAWOPS_ACCOUNT_ID` | Default account ID (AC...) | Yes (if not passed) |
| `CLAWOPS_BASE_URL` | API base URL | No (default: https://api.claw-ops.com) |
