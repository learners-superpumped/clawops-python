# ClawOps Python SDK Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** OpenAI Python SDK 패턴을 따르는 ClawOps Voice API의 공식 Python SDK 구현

**Architecture:** httpx 기반 sync/async 클라이언트, TypedDict request params, Pydantic v2 response models, 리소스 계층 구조, Twilio 스타일 multi-account 접근

**Tech Stack:** Python 3.9+, httpx, Pydantic v2, hatchling, pytest, respx (httpx mocking)

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/clawops/__init__.py` (stub)
- Create: `src/clawops/py.typed`
- Create: `src/clawops/_version.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "clawops"
dynamic = ["version"]
description = "The official Python library for the ClawOps Voice API"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.9"
authors = [{ name = "ClawOps", email = "support@claw-ops.com" }]
classifiers = [
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Typing :: Typed",
]
dependencies = [
    "httpx>=0.23.0,<1",
    "pydantic>=2.0.0,<3",
    "typing-extensions>=4.7.0",
]

[project.urls]
Homepage = "https://github.com/clawops/clawops-python"
Documentation = "https://docs.claw-ops.com"
Repository = "https://github.com/clawops/clawops-python"

[tool.hatch.version]
path = "src/clawops/_version.py"

[tool.hatch.build.targets.wheel]
packages = ["src/clawops"]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "respx>=0.20",
    "mypy>=1.0",
    "ruff>=0.1",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
strict = true

[tool.ruff]
target-version = "py39"
line-length = 120
```

**Step 2: Create version file and stubs**

```python
# src/clawops/_version.py
__version__ = "0.1.0"
```

```python
# src/clawops/__init__.py
from ._version import __version__

__all__ = ["__version__"]
```

```
# src/clawops/py.typed
(empty file - PEP 561 marker)
```

```python
# tests/__init__.py
(empty)
```

```python
# tests/conftest.py
import pytest


@pytest.fixture
def api_key() -> str:
    return "sk_test_0123456789abcdef0123456789abcdef"


@pytest.fixture
def account_id() -> str:
    return "AC1a2b3c4d"


@pytest.fixture
def base_url() -> str:
    return "https://api.claw-ops.com"
```

**Step 3: Verify project builds**

Run: `cd /Users/ghyeok/Developments/clawops-python && pip install -e ".[dev]"`
Expected: Successfully installed clawops-0.1.0

**Step 4: Commit**

```bash
git init
git add -A
git commit -m "chore: initial project scaffolding with pyproject.toml"
```

---

### Task 2: Constants & Utilities

**Files:**
- Create: `src/clawops/_constants.py`
- Create: `src/clawops/_utils.py`
- Test: `tests/test_utils.py`

**Step 1: Write tests for utilities**

```python
# tests/test_utils.py
from clawops._utils import to_camel_case, strip_not_given, PropertyInfo


def test_to_camel_case_simple():
    assert to_camel_case("account_id") == "accountId"


def test_to_camel_case_single_word():
    assert to_camel_case("status") == "status"


def test_to_camel_case_multiple_underscores():
    assert to_camel_case("date_created_at") == "dateCreatedAt"


def test_to_camel_case_trailing_underscore():
    """Python 예약어 회피용 trailing underscore (from_) 처리."""
    assert to_camel_case("from_") == "from"


def test_strip_not_given_removes_none():
    data = {"a": 1, "b": None, "c": "hello"}
    assert strip_not_given(data) == {"a": 1, "c": "hello"}


def test_strip_not_given_empty():
    assert strip_not_given({}) == {}


def test_property_info():
    info = PropertyInfo(alias="From")
    assert info.alias == "From"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_utils.py -v`
Expected: FAIL (module not found)

**Step 3: Implement constants**

```python
# src/clawops/_constants.py
from __future__ import annotations

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(timeout=600.0, connect=5.0)
DEFAULT_MAX_RETRIES = 2
DEFAULT_BASE_URL = "https://api.claw-ops.com"
INITIAL_RETRY_DELAY = 0.5
MAX_RETRY_DELAY = 8.0
DEFAULT_CONNECTION_LIMITS = httpx.Limits(
    max_connections=1000,
    max_keepalive_connections=100,
)
```

**Step 4: Implement utilities**

```python
# src/clawops/_utils.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def to_camel_case(snake: str) -> str:
    """snake_case를 camelCase로 변환합니다.

    trailing underscore(Python 예약어 회피용)는 제거합니다.
    예: 'from_' -> 'from', 'account_id' -> 'accountId'
    """
    # trailing underscore 제거 (from_, type_ 등)
    if snake.endswith("_"):
        snake = snake[:-1]
    parts = snake.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


def strip_not_given(data: dict[str, Any]) -> dict[str, Any]:
    """None인 값을 제거하여 API에 불필요한 필드를 보내지 않습니다."""
    return {k: v for k, v in data.items() if v is not None}


@dataclass
class PropertyInfo:
    """TypedDict 필드에 alias 정보를 부여하기 위한 메타데이터.

    사용 예:
        class CallCreateParams(TypedDict, total=False):
            from_: Required[Annotated[str, PropertyInfo(alias="From")]]
    """

    alias: str
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_utils.py -v`
Expected: 7 passed

**Step 6: Commit**

```bash
git add src/clawops/_constants.py src/clawops/_utils.py tests/test_utils.py
git commit -m "feat: add constants and utility functions"
```

---

### Task 3: Error Hierarchy

**Files:**
- Create: `src/clawops/_exceptions.py`
- Test: `tests/test_exceptions.py`

**Step 1: Write tests**

```python
# tests/test_exceptions.py
import httpx
import pytest

from clawops._exceptions import (
    ClawOpsError,
    APIError,
    APIStatusError,
    APIConnectionError,
    APITimeoutError,
    APIResponseValidationError,
    BadRequestError,
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError,
    ConflictError,
    UnprocessableEntityError,
    InternalServerError,
    ServiceUnavailableError,
    _make_status_error,
)


def test_error_hierarchy():
    assert issubclass(APIError, ClawOpsError)
    assert issubclass(APIStatusError, APIError)
    assert issubclass(APIConnectionError, APIError)
    assert issubclass(APITimeoutError, APIConnectionError)
    assert issubclass(APIResponseValidationError, APIError)
    assert issubclass(BadRequestError, APIStatusError)
    assert issubclass(AuthenticationError, APIStatusError)
    assert issubclass(PermissionDeniedError, APIStatusError)
    assert issubclass(NotFoundError, APIStatusError)
    assert issubclass(ConflictError, APIStatusError)
    assert issubclass(UnprocessableEntityError, APIStatusError)
    assert issubclass(InternalServerError, APIStatusError)
    assert issubclass(ServiceUnavailableError, APIStatusError)


def test_api_status_error_attributes():
    request = httpx.Request("GET", "https://api.claw-ops.com/v1/accounts/AC123/calls")
    response = httpx.Response(
        404,
        json={"error": "콜을 찾을 수 없습니다"},
        request=request,
    )
    err = NotFoundError(
        message="콜을 찾을 수 없습니다",
        response=response,
        body={"error": "콜을 찾을 수 없습니다"},
    )
    assert err.status_code == 404
    assert err.body == {"error": "콜을 찾을 수 없습니다"}
    assert err.response is response
    assert err.request is request
    assert "콜을 찾을 수 없습니다" in str(err)


def test_make_status_error_mapping():
    request = httpx.Request("GET", "https://api.claw-ops.com/test")
    cases = [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ConflictError),
        (422, UnprocessableEntityError),
        (500, InternalServerError),
        (502, InternalServerError),
        (503, ServiceUnavailableError),
    ]
    for status_code, expected_cls in cases:
        response = httpx.Response(status_code, json={"error": "test"}, request=request)
        err = _make_status_error(response=response)
        assert isinstance(err, expected_cls), f"Expected {expected_cls} for {status_code}, got {type(err)}"


def test_api_connection_error():
    request = httpx.Request("GET", "https://api.claw-ops.com/test")
    err = APIConnectionError(message="Connection refused", request=request)
    assert "Connection refused" in str(err)
    assert err.request is request


def test_api_timeout_error():
    request = httpx.Request("GET", "https://api.claw-ops.com/test")
    err = APITimeoutError(request=request)
    assert err.request is request
    assert isinstance(err, APIConnectionError)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_exceptions.py -v`
Expected: FAIL

**Step 3: Implement exceptions**

```python
# src/clawops/_exceptions.py
from __future__ import annotations

from typing import Any

import httpx


class ClawOpsError(Exception):
    """ClawOps SDK의 모든 에러의 베이스 클래스."""


class APIError(ClawOpsError):
    """API 호출 관련 에러의 베이스 클래스."""

    message: str
    request: httpx.Request

    def __init__(self, message: str, *, request: httpx.Request) -> None:
        super().__init__(message)
        self.message = message
        self.request = request


class APIStatusError(APIError):
    """HTTP 상태 코드 에러 (4xx/5xx).

    Attributes:
        status_code: HTTP 상태 코드.
        response: 원본 httpx.Response 객체.
        body: 파싱된 JSON 응답 바디. 파싱 실패 시 None.
    """

    status_code: int
    response: httpx.Response
    body: Any | None

    def __init__(
        self,
        message: str,
        *,
        response: httpx.Response,
        body: Any | None,
    ) -> None:
        super().__init__(message, request=response.request)
        self.status_code = response.status_code
        self.response = response
        self.body = body


class BadRequestError(APIStatusError):
    """HTTP 400 Bad Request."""

    status_code: int = 400


class AuthenticationError(APIStatusError):
    """HTTP 401 Unauthorized. API 키가 유효하지 않습니다."""

    status_code: int = 401


class PermissionDeniedError(APIStatusError):
    """HTTP 403 Forbidden. accountId가 일치하지 않거나 권한이 없습니다."""

    status_code: int = 403


class NotFoundError(APIStatusError):
    """HTTP 404 Not Found. 요청한 리소스를 찾을 수 없습니다."""

    status_code: int = 404


class ConflictError(APIStatusError):
    """HTTP 409 Conflict. 리소스가 이미 존재합니다."""

    status_code: int = 409


class UnprocessableEntityError(APIStatusError):
    """HTTP 422 Unprocessable Entity. 할당량 초과 등."""

    status_code: int = 422


class InternalServerError(APIStatusError):
    """HTTP 500+ Internal Server Error."""

    status_code: int = 500


class ServiceUnavailableError(APIStatusError):
    """HTTP 503 Service Unavailable. ARI 서비스 또는 번호 풀 사용 불가."""

    status_code: int = 503


class APIConnectionError(APIError):
    """네트워크 연결 실패."""

    def __init__(self, *, message: str = "Connection error.", request: httpx.Request) -> None:
        super().__init__(message, request=request)


class APITimeoutError(APIConnectionError):
    """요청 타임아웃."""

    def __init__(self, *, request: httpx.Request) -> None:
        super().__init__(message="Request timed out.", request=request)


class APIResponseValidationError(APIError):
    """API 응답이 예상된 스키마와 일치하지 않습니다."""

    status_code: int
    response: httpx.Response

    def __init__(
        self,
        *,
        response: httpx.Response,
        message: str = "API response validation failed.",
    ) -> None:
        super().__init__(message, request=response.request)
        self.status_code = response.status_code
        self.response = response


_STATUS_CODE_TO_ERROR: dict[int, type[APIStatusError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableEntityError,
    500: InternalServerError,
    503: ServiceUnavailableError,
}


def _make_status_error(*, response: httpx.Response) -> APIStatusError:
    """HTTP 응답 상태 코드를 적절한 예외 클래스로 매핑합니다."""
    try:
        body = response.json()
    except Exception:
        body = None

    message = ""
    if isinstance(body, dict) and "error" in body:
        message = body["error"]
    else:
        message = f"HTTP {response.status_code}"

    err_cls = _STATUS_CODE_TO_ERROR.get(response.status_code)
    if err_cls is None:
        if response.status_code >= 500:
            err_cls = InternalServerError
        else:
            err_cls = APIStatusError

    return err_cls(message=message, response=response, body=body)
```

**Step 4: Run tests**

Run: `pytest tests/test_exceptions.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/clawops/_exceptions.py tests/test_exceptions.py
git commit -m "feat: add error hierarchy with HTTP status code mapping"
```

---

### Task 4: Base Models (Pydantic)

**Files:**
- Create: `src/clawops/_models.py`
- Test: `tests/test_models.py`

**Step 1: Write tests**

```python
# tests/test_models.py
from datetime import datetime
from typing import Optional

from clawops._models import BaseModel


class SampleModel(BaseModel):
    user_name: str
    created_at: datetime
    display_name: Optional[str] = None
    from_: Optional[str] = None


def test_camel_case_alias_deserialization():
    """API가 camelCase JSON을 반환할 때 snake_case 필드로 매핑."""
    data = {
        "userName": "john",
        "createdAt": "2025-01-01T00:00:00Z",
        "displayName": "John Doe",
    }
    obj = SampleModel.model_validate(data)
    assert obj.user_name == "john"
    assert obj.display_name == "John Doe"


def test_snake_case_access():
    """populate_by_name=True로 snake_case로도 생성 가능."""
    obj = SampleModel(
        user_name="john",
        created_at=datetime(2025, 1, 1),
    )
    assert obj.user_name == "john"


def test_camel_case_serialization():
    """모델을 JSON으로 직렬화할 때 camelCase 사용."""
    obj = SampleModel(
        user_name="john",
        created_at=datetime(2025, 1, 1),
    )
    dumped = obj.model_dump(by_alias=True)
    assert "userName" in dumped
    assert "createdAt" in dumped


def test_extra_fields_allowed():
    """API가 새 필드를 추가해도 에러 없이 수용."""
    data = {
        "userName": "john",
        "createdAt": "2025-01-01T00:00:00Z",
        "newField": "should not break",
    }
    obj = SampleModel.model_validate(data)
    assert obj.user_name == "john"


def test_trailing_underscore_alias():
    """from_ -> from으로 alias 변환."""
    data = {
        "userName": "john",
        "createdAt": "2025-01-01T00:00:00Z",
        "from": "07012345678",
    }
    obj = SampleModel.model_validate(data)
    assert obj.from_ == "07012345678"

    dumped = obj.model_dump(by_alias=True)
    assert "from" in dumped
    assert dumped["from"] == "07012345678"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL

**Step 3: Implement BaseModel**

```python
# src/clawops/_models.py
from __future__ import annotations

import pydantic
from pydantic import ConfigDict

from ._utils import to_camel_case


class BaseModel(pydantic.BaseModel):
    """ClawOps SDK의 모든 응답 모델의 베이스 클래스.

    - snake_case 필드 → camelCase JSON alias 자동 생성
    - extra="allow"로 미래 API 필드 호환
    - populate_by_name=True로 snake_case/camelCase 양방향 접근
    """

    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel_case,
        populate_by_name=True,
    )
```

**Step 4: Run tests**

Run: `pytest tests/test_models.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/clawops/_models.py tests/test_models.py
git commit -m "feat: add Pydantic BaseModel with camelCase alias generator"
```

---

### Task 5: Response Type Definitions

**Files:**
- Create: `src/clawops/types/__init__.py`
- Create: `src/clawops/types/shared.py`
- Create: `src/clawops/types/call.py`
- Create: `src/clawops/types/number.py`
- Create: `src/clawops/types/sip/__init__.py`
- Create: `src/clawops/types/sip/credential.py`
- Test: `tests/test_types.py`

**Step 1: Write tests**

```python
# tests/test_types.py
from datetime import datetime

from clawops.types.call import Call, CallControlResponse
from clawops.types.number import PhoneNumber, NumberListItem
from clawops.types.sip.credential import SipCredential, SipCredentialListItem
from clawops.types.shared import PaginationMeta


def test_call_from_api_response():
    data = {
        "callId": "CAabcdef1234567890abcdef1234567890",
        "status": "queued",
        "to": "01012345678",
        "from": "07052358010",
        "direction": "outbound",
        "duration": None,
        "accountId": "AC1a2b3c4d",
        "dateCreated": "2025-06-01T12:00:00Z",
        "dateUpdated": None,
    }
    call = Call.model_validate(data)
    assert call.call_id == "CAabcdef1234567890abcdef1234567890"
    assert call.status == "queued"
    assert call.to == "01012345678"
    assert call.from_ == "07052358010"
    assert call.direction == "outbound"
    assert call.duration is None
    assert call.account_id == "AC1a2b3c4d"
    assert isinstance(call.date_created, datetime)
    assert call.date_updated is None


def test_call_control_response():
    data = {"callId": "CA123", "status": "completed"}
    resp = CallControlResponse.model_validate(data)
    assert resp.call_id == "CA123"
    assert resp.status == "completed"


def test_phone_number_from_api():
    data = {"number": "07012340001", "source": "pool"}
    num = PhoneNumber.model_validate(data)
    assert num.number == "07012340001"
    assert num.source == "pool"


def test_number_list_item():
    data = {
        "number": "07012340001",
        "source": "pool",
        "webhookUrl": "https://my-app.com/voice",
        "createdAt": "2025-06-01T12:00:00Z",
    }
    item = NumberListItem.model_validate(data)
    assert item.number == "07012340001"
    assert item.webhook_url == "https://my-app.com/voice"


def test_sip_credential_with_password():
    data = {
        "id": "clu1abc2def3ghi",
        "username": "usr_aBcDeFgHiJkL",
        "password": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        "displayName": "Office Phone",
        "sipServer": "sip.claw-ops.com",
        "sipPort": 5060,
        "transport": "UDP",
        "createdAt": "2025-06-01T12:00:00Z",
    }
    cred = SipCredential.model_validate(data)
    assert cred.id == "clu1abc2def3ghi"
    assert cred.username == "usr_aBcDeFgHiJkL"
    assert cred.password == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    assert cred.display_name == "Office Phone"
    assert cred.sip_server == "sip.claw-ops.com"
    assert cred.sip_port == 5060
    assert cred.transport == "UDP"


def test_sip_credential_list_item_no_password():
    data = {
        "id": "clu1abc2def3ghi",
        "username": "usr_aBcDeFgHiJkL",
        "displayName": None,
        "createdAt": "2025-06-01T12:00:00Z",
    }
    item = SipCredentialListItem.model_validate(data)
    assert item.id == "clu1abc2def3ghi"
    assert item.display_name is None


def test_pagination_meta():
    data = {"total": 100, "page": 2, "pageSize": 20}
    meta = PaginationMeta.model_validate(data)
    assert meta.total == 100
    assert meta.page == 2
    assert meta.page_size == 20
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_types.py -v`
Expected: FAIL

**Step 3: Implement shared types**

```python
# src/clawops/types/__init__.py
from .call import Call, CallControlResponse
from .number import PhoneNumber, NumberListItem, NumberUpdateResponse
from .shared import PaginationMeta
from .sip.credential import SipCredential, SipCredentialListItem

__all__ = [
    "Call",
    "CallControlResponse",
    "NumberListItem",
    "NumberUpdateResponse",
    "PaginationMeta",
    "PhoneNumber",
    "SipCredential",
    "SipCredentialListItem",
]
```

```python
# src/clawops/types/shared.py
from __future__ import annotations

from .._models import BaseModel


class PaginationMeta(BaseModel):
    """페이지네이션 메타데이터.

    Attributes:
        total: 전체 항목 수.
        page: 현재 페이지 번호 (0부터 시작).
        page_size: 페이지당 항목 수.
    """

    total: int
    page: int
    page_size: int
```

**Step 4: Implement Call types**

```python
# src/clawops/types/call.py
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from .._models import BaseModel


class Call(BaseModel):
    """통화 정보를 나타내는 모델.

    아웃바운드 전화 발신 후 반환되거나, 통화 목록/단건 조회 시 반환됩니다.

    Attributes:
        call_id: 통화 고유 식별자 (예: 'CAabcdef1234567890').
        status: 통화 상태. queued, ringing, in-progress, completed, failed 중 하나.
        to: 수신 전화번호 또는 SIP URI.
        from_: 발신 전화번호 (계정에 등록된 번호).
        direction: 통화 방향. outbound 또는 inbound.
        duration: 통화 시간 (초). 통화 중이거나 미연결인 경우 None.
        account_id: 계정 ID.
        date_created: 통화 생성 시각.
        date_updated: 통화 종료 시각. 종료 전이면 None.
    """

    call_id: str
    status: Literal["queued", "ringing", "in-progress", "completed", "failed"]
    to: str
    from_: str
    direction: Literal["outbound", "inbound"]
    duration: Optional[int] = None
    account_id: str
    date_created: datetime
    date_updated: Optional[datetime] = None


class CallControlResponse(BaseModel):
    """통화 제어 (종료) 응답.

    Attributes:
        call_id: 제어된 통화의 ID.
        status: 변경된 상태 (현재 'completed'만 지원).
    """

    call_id: str
    status: str
```

**Step 5: Implement Number types**

```python
# src/clawops/types/number.py
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from .._models import BaseModel


class PhoneNumber(BaseModel):
    """번호 등록 응답 모델.

    PSTN 풀 발급 또는 SIP 내선번호 등록 후 반환됩니다.

    Attributes:
        number: 등록된 전화번호 (예: '07012340001' 또는 SIP 내선번호).
        source: 번호 유형. 'pool'은 PSTN 풀 발급, 'sip'은 SIP 내선번호.
    """

    number: str
    source: Literal["pool", "sip"]


class NumberListItem(BaseModel):
    """번호 목록 항목.

    계정에 등록된 전화번호의 상세 정보를 포함합니다.

    Attributes:
        number: 전화번호.
        source: 번호 유형. 'pool' 또는 'sip'.
        webhook_url: 수신 전화 처리용 Webhook URL. 미설정 시 None.
        created_at: 등록 시각.
    """

    number: str
    source: Literal["pool", "sip"]
    webhook_url: Optional[str] = None
    created_at: Optional[datetime] = None


class NumberUpdateResponse(BaseModel):
    """번호 설정 수정 응답.

    Attributes:
        number: 전화번호.
        source: 번호 유형.
        webhook_url: 수정된 Webhook URL.
        webhook_method: Webhook HTTP 메서드 (POST 또는 GET).
    """

    number: str
    source: Literal["pool", "sip"]
    webhook_url: Optional[str] = None
    webhook_method: Optional[Literal["POST", "GET"]] = None
```

**Step 6: Implement SIP Credential types**

```python
# src/clawops/types/sip/__init__.py
from .credential import SipCredential, SipCredentialListItem

__all__ = ["SipCredential", "SipCredentialListItem"]
```

```python
# src/clawops/types/sip/credential.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..._models import BaseModel


class SipCredential(BaseModel):
    """SIP Credential 생성 응답 모델.

    SIP 클라이언트(Linphone 등) 등록에 필요한 자격증명입니다.
    password는 생성 시에만 반환되며, 이후 조회 시에는 포함되지 않습니다.

    Attributes:
        id: Credential 고유 식별자.
        username: SIP 사용자명 (예: 'usr_aBcDeFgHiJkL').
        password: SIP 비밀번호. 생성 응답에서만 반환.
        display_name: 디스플레이 이름 (선택).
        sip_server: SIP 서버 주소 (예: 'sip.claw-ops.com').
        sip_port: SIP 포트 번호 (기본 5060).
        transport: 전송 프로토콜 (기본 'UDP').
        created_at: 생성 시각.
    """

    id: str
    username: str
    password: Optional[str] = None
    display_name: Optional[str] = None
    sip_server: Optional[str] = None
    sip_port: Optional[int] = None
    transport: Optional[str] = None
    created_at: Optional[datetime] = None


class SipCredentialListItem(BaseModel):
    """SIP Credential 목록/단건 조회 항목.

    password는 포함되지 않습니다.

    Attributes:
        id: Credential 고유 식별자.
        username: SIP 사용자명.
        display_name: 디스플레이 이름.
        created_at: 생성 시각.
    """

    id: str
    username: str
    display_name: Optional[str] = None
    created_at: Optional[datetime] = None
```

**Step 7: Run tests**

Run: `pytest tests/test_types.py -v`
Expected: 8 passed

**Step 8: Commit**

```bash
git add src/clawops/types/ src/clawops/_models.py tests/test_types.py
git commit -m "feat: add Pydantic response models for all API resources"
```

---

### Task 6: Request Parameter TypedDicts

**Files:**
- Create: `src/clawops/types/call_params.py`
- Create: `src/clawops/types/number_params.py`
- Create: `src/clawops/types/sip/credential_params.py`
- Test: `tests/test_params.py`

**Step 1: Write tests**

```python
# tests/test_params.py
"""Request parameter TypedDict는 런타임이 아닌 타입 체크 시점에 검증됩니다.
여기서는 TypedDict가 올바르게 정의되었는지 기본 구조만 확인합니다."""
from clawops.types.call_params import CallCreateParams, CallListParams, CallUpdateParams
from clawops.types.number_params import NumberCreateParams, NumberUpdateParams
from clawops.types.sip.credential_params import SipCredentialCreateParams


def test_call_create_params_structure():
    params: CallCreateParams = {"to": "01012345678", "from_": "07052358010", "url": "https://example.com/twiml"}
    assert params["to"] == "01012345678"


def test_call_list_params_structure():
    params: CallListParams = {"status": "completed", "page": 0, "page_size": 20}
    assert params["status"] == "completed"


def test_call_update_params_structure():
    params: CallUpdateParams = {"status": "completed"}
    assert params["status"] == "completed"


def test_number_create_params_structure():
    params: NumberCreateParams = {"source": "sip", "number": "1001"}
    assert params["source"] == "sip"


def test_number_update_params_structure():
    params: NumberUpdateParams = {"webhook_url": "https://example.com", "webhook_method": "POST"}
    assert params["webhook_url"] == "https://example.com"


def test_sip_credential_create_params_structure():
    params: SipCredentialCreateParams = {"display_name": "Office Phone"}
    assert params["display_name"] == "Office Phone"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_params.py -v`
Expected: FAIL

**Step 3: Implement Call params**

```python
# src/clawops/types/call_params.py
from __future__ import annotations

from typing import Annotated, Literal

from typing_extensions import Required, TypedDict

from .._utils import PropertyInfo


class CallCreateParams(TypedDict, total=False):
    """발신 전화 생성 요청 파라미터.

    아웃바운드 전화를 발신합니다. PSTN 번호 또는 SIP URI로 발신 가능합니다.
    """

    to: Required[Annotated[str, PropertyInfo(alias="To")]]
    """수신 대상. 전화번호(PSTN 발신, 예: '01012345678') 또는
    sip: URI(내선 발신, 예: 'sip:usr_aBcDeFgHiJkL@sip.claw-ops.com')."""

    from_: Required[Annotated[str, PropertyInfo(alias="From")]]
    """발신 번호. 계정에 등록된 번호여야 합니다 (예: '07052358010')."""

    url: Required[Annotated[str, PropertyInfo(alias="Url")]]
    """통화 연결 시 TwiML 명령을 반환할 URL."""

    status_callback: Annotated[str, PropertyInfo(alias="StatusCallback")]
    """통화 상태 변경 시 POST 요청을 받을 콜백 URL."""

    status_callback_event: Annotated[str, PropertyInfo(alias="StatusCallbackEvent")]
    """수신할 상태 이벤트 목록 (공백 구분).
    기본값: 'initiated ringing answered completed'.
    사용 가능한 이벤트: initiated, ringing, answered, completed."""


class CallListParams(TypedDict, total=False):
    """통화 목록 조회 요청 파라미터."""

    status: Literal["queued", "ringing", "in-progress", "completed", "failed"]
    """통화 상태로 필터링."""

    page: int
    """페이지 번호 (0부터 시작, 기본값 0)."""

    page_size: Annotated[int, PropertyInfo(alias="pageSize")]
    """페이지당 항목 수 (기본 20, 최대 100)."""


class CallUpdateParams(TypedDict, total=False):
    """통화 제어 (종료) 요청 파라미터."""

    status: Required[Annotated[Literal["completed"], PropertyInfo(alias="Status")]]
    """변경할 통화 상태. 현재 'completed'(통화 종료)만 지원합니다."""
```

**Step 4: Implement Number params**

```python
# src/clawops/types/number_params.py
from __future__ import annotations

from typing import Annotated, Literal, Optional

from typing_extensions import TypedDict

from .._utils import PropertyInfo


class NumberCreateParams(TypedDict, total=False):
    """번호 등록 요청 파라미터.

    source를 생략하거나 'pool'로 지정하면 PSTN 번호 풀에서 자동 발급됩니다.
    'sip'으로 지정하면 원하는 번호를 직접 등록합니다.
    """

    source: Literal["pool", "sip"]
    """번호 유형. 'pool'=PSTN 풀 발급 (기본값), 'sip'=SIP 내선번호 직접 등록."""

    number: Optional[str]
    """SIP 내선번호 (source='sip'일 때 필수, 3~20자리 숫자).
    통신사 번호 형식(010, 070, 02 등)은 사용할 수 없습니다."""

    webhook_url: Annotated[Optional[str], PropertyInfo(alias="webhookUrl")]
    """수신 전화 처리용 Webhook URL (선택)."""


class NumberUpdateParams(TypedDict, total=False):
    """번호 설정 수정 요청 파라미터.

    번호 자체는 변경할 수 없으며, webhookUrl과 webhookMethod만 수정 가능합니다.
    """

    webhook_url: Annotated[Optional[str], PropertyInfo(alias="webhookUrl")]
    """수신 전화 처리용 Webhook URL."""

    webhook_method: Annotated[Literal["POST", "GET"], PropertyInfo(alias="webhookMethod")]
    """Webhook 호출 HTTP 메서드. POST 또는 GET."""
```

**Step 5: Implement SIP Credential params**

```python
# src/clawops/types/sip/credential_params.py
from __future__ import annotations

from typing import Annotated, Optional

from typing_extensions import TypedDict

from ..._utils import PropertyInfo


class SipCredentialCreateParams(TypedDict, total=False):
    """SIP Credential 생성 요청 파라미터.

    Linphone 등 SIP 클라이언트 등록에 사용할 자격증명을 생성합니다.
    계정당 최대 10개까지 생성할 수 있습니다.
    """

    display_name: Annotated[Optional[str], PropertyInfo(alias="displayName")]
    """디스플레이 이름 (선택). SIP 클라이언트에 표시되는 이름입니다."""
```

**Step 6: Update types/__init__.py exports**

```python
# src/clawops/types/__init__.py 에 추가
from .call import Call, CallControlResponse
from .call_params import CallCreateParams, CallListParams, CallUpdateParams
from .number import NumberListItem, NumberUpdateResponse, PhoneNumber
from .number_params import NumberCreateParams, NumberUpdateParams
from .shared import PaginationMeta
from .sip.credential import SipCredential, SipCredentialListItem
from .sip.credential_params import SipCredentialCreateParams

__all__ = [
    "Call",
    "CallControlResponse",
    "CallCreateParams",
    "CallListParams",
    "CallUpdateParams",
    "NumberCreateParams",
    "NumberListItem",
    "NumberUpdateParams",
    "NumberUpdateResponse",
    "PaginationMeta",
    "PhoneNumber",
    "SipCredential",
    "SipCredentialCreateParams",
    "SipCredentialListItem",
]
```

**Step 7: Run tests**

Run: `pytest tests/test_params.py -v`
Expected: 6 passed

**Step 8: Commit**

```bash
git add src/clawops/types/ tests/test_params.py
git commit -m "feat: add TypedDict request parameter types for all endpoints"
```

---

### Task 7: Base Client (httpx Wrapper)

**Files:**
- Create: `src/clawops/_base_client.py`
- Test: `tests/test_base_client.py`

**Step 1: Write tests**

```python
# tests/test_base_client.py
import httpx
import pytest
import respx

from clawops._base_client import SyncAPIClient, AsyncAPIClient
from clawops._constants import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, DEFAULT_MAX_RETRIES
from clawops._exceptions import (
    AuthenticationError,
    NotFoundError,
    APIConnectionError,
    APITimeoutError,
)
from clawops._models import BaseModel


class DummyResponse(BaseModel):
    message: str


class TestSyncAPIClient:
    def _make_client(self, **kwargs) -> SyncAPIClient:
        return SyncAPIClient(
            api_key=kwargs.get("api_key", "sk_test_key"),
            base_url=kwargs.get("base_url", DEFAULT_BASE_URL),
            timeout=kwargs.get("timeout", DEFAULT_TIMEOUT),
            max_retries=kwargs.get("max_retries", 0),  # 테스트에서는 재시도 비활성화
        )

    def test_default_headers(self):
        client = self._make_client()
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer sk_test_key"
        assert "clawops-python/" in headers["User-Agent"]
        assert headers["Content-Type"] == "application/json"

    @respx.mock
    def test_get_success(self):
        respx.get("https://api.claw-ops.com/test").mock(
            return_value=httpx.Response(200, json={"message": "ok"})
        )
        client = self._make_client()
        result = client._get("/test", cast_to=DummyResponse)
        assert isinstance(result, DummyResponse)
        assert result.message == "ok"
        client.close()

    @respx.mock
    def test_post_success(self):
        respx.post("https://api.claw-ops.com/test").mock(
            return_value=httpx.Response(201, json={"message": "created"})
        )
        client = self._make_client()
        result = client._post("/test", body={"key": "val"}, cast_to=DummyResponse)
        assert result.message == "created"
        client.close()

    @respx.mock
    def test_404_raises_not_found(self):
        respx.get("https://api.claw-ops.com/test").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        client = self._make_client()
        with pytest.raises(NotFoundError) as exc_info:
            client._get("/test", cast_to=DummyResponse)
        assert exc_info.value.status_code == 404
        assert exc_info.value.body == {"error": "not found"}
        client.close()

    @respx.mock
    def test_401_raises_authentication_error(self):
        respx.get("https://api.claw-ops.com/test").mock(
            return_value=httpx.Response(401, json={"error": "invalid key"})
        )
        client = self._make_client()
        with pytest.raises(AuthenticationError):
            client._get("/test", cast_to=DummyResponse)
        client.close()

    @respx.mock
    def test_retry_on_500(self):
        route = respx.get("https://api.claw-ops.com/test")
        route.side_effect = [
            httpx.Response(500, json={"error": "server error"}),
            httpx.Response(200, json={"message": "ok"}),
        ]
        client = self._make_client(max_retries=1)
        result = client._get("/test", cast_to=DummyResponse)
        assert result.message == "ok"
        assert route.call_count == 2
        client.close()

    @respx.mock
    def test_delete_returns_none(self):
        respx.delete("https://api.claw-ops.com/test").mock(
            return_value=httpx.Response(204)
        )
        client = self._make_client()
        result = client._delete("/test")
        assert result is None
        client.close()

    def test_context_manager(self):
        with self._make_client() as client:
            assert client is not None

    @respx.mock
    def test_extra_headers_override(self):
        route = respx.get("https://api.claw-ops.com/test").mock(
            return_value=httpx.Response(200, json={"message": "ok"})
        )
        client = self._make_client()
        client._get(
            "/test",
            cast_to=DummyResponse,
            extra_headers={"X-Custom": "value"},
        )
        assert route.calls[0].request.headers["X-Custom"] == "value"
        client.close()

    @respx.mock
    def test_extra_query_params(self):
        route = respx.get("https://api.claw-ops.com/test").mock(
            return_value=httpx.Response(200, json={"message": "ok"})
        )
        client = self._make_client()
        client._get(
            "/test",
            cast_to=DummyResponse,
            extra_query={"foo": "bar"},
        )
        assert "foo=bar" in str(route.calls[0].request.url)
        client.close()


class TestAsyncAPIClient:
    def _make_client(self, **kwargs) -> AsyncAPIClient:
        return AsyncAPIClient(
            api_key=kwargs.get("api_key", "sk_test_key"),
            base_url=kwargs.get("base_url", DEFAULT_BASE_URL),
            timeout=kwargs.get("timeout", DEFAULT_TIMEOUT),
            max_retries=kwargs.get("max_retries", 0),
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_success(self):
        respx.get("https://api.claw-ops.com/test").mock(
            return_value=httpx.Response(200, json={"message": "ok"})
        )
        client = self._make_client()
        result = await client._get("/test", cast_to=DummyResponse)
        assert result.message == "ok"
        await client.close()

    @respx.mock
    @pytest.mark.asyncio
    async def test_404_raises_not_found(self):
        respx.get("https://api.claw-ops.com/test").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        client = self._make_client()
        with pytest.raises(NotFoundError):
            await client._get("/test", cast_to=DummyResponse)
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with self._make_client() as client:
            assert client is not None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_base_client.py -v`
Expected: FAIL

**Step 3: Implement base client**

```python
# src/clawops/_base_client.py
from __future__ import annotations

import time
from random import random
from typing import Any, TypeVar, overload

import httpx
import pydantic

from ._constants import (
    DEFAULT_BASE_URL,
    DEFAULT_CONNECTION_LIMITS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    INITIAL_RETRY_DELAY,
    MAX_RETRY_DELAY,
)
from ._exceptions import (
    APIConnectionError,
    APIResponseValidationError,
    APITimeoutError,
    _make_status_error,
)
from ._version import __version__

_T = TypeVar("_T", bound=pydantic.BaseModel)


class SyncAPIClient:
    """동기 HTTP 클라이언트 베이스.

    httpx.Client를 래핑하며 인증, 재시도, 타임아웃, 에러 매핑을 처리합니다.
    """

    _client: httpx.Client
    _api_key: str
    _base_url: str
    _max_retries: int
    _timeout: httpx.Timeout

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries

        if isinstance(timeout, (int, float)):
            self._timeout = httpx.Timeout(timeout)
        else:
            self._timeout = timeout

        if http_client is not None:
            self._client = http_client
        else:
            self._client = httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                limits=DEFAULT_CONNECTION_LIMITS,
            )

    def _build_headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"clawops-python/{__version__}",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> _T | None:
        headers = self._build_headers(extra_headers)

        params = query.copy() if query else {}
        if extra_query:
            params.update(extra_query)

        req_timeout = timeout if timeout is not None else self._timeout
        if isinstance(req_timeout, (int, float)):
            req_timeout = httpx.Timeout(req_timeout)

        retries_left = self._max_retries
        last_err: Exception | None = None

        while True:
            try:
                response = self._client.request(
                    method=method,
                    url=path,
                    json=body,
                    params=params if params else None,
                    headers=headers,
                    timeout=req_timeout,
                )
            except httpx.TimeoutException as e:
                if retries_left > 0:
                    retries_left -= 1
                    time.sleep(self._retry_delay(self._max_retries - retries_left))
                    continue
                raise APITimeoutError(
                    request=httpx.Request(method, self._base_url + path),
                ) from e
            except httpx.ConnectError as e:
                if retries_left > 0:
                    retries_left -= 1
                    time.sleep(self._retry_delay(self._max_retries - retries_left))
                    continue
                raise APIConnectionError(
                    request=httpx.Request(method, self._base_url + path),
                ) from e

            if response.is_success:
                if response.status_code == 204 or cast_to is None:
                    return None
                try:
                    return cast_to.model_validate(response.json())
                except pydantic.ValidationError as e:
                    raise APIResponseValidationError(response=response) from e

            if retries_left > 0 and self._should_retry(response):
                retries_left -= 1
                time.sleep(self._retry_delay(self._max_retries - retries_left))
                continue

            raise _make_status_error(response=response)

    def _should_retry(self, response: httpx.Response) -> bool:
        if response.status_code in (408, 409, 429):
            return True
        if response.status_code >= 500:
            return True
        return False

    def _retry_delay(self, retries_taken: int) -> float:
        delay = min(INITIAL_RETRY_DELAY * (2 ** retries_taken), MAX_RETRY_DELAY)
        return delay * (1 + random())

    def _get(
        self,
        path: str,
        *,
        cast_to: type[_T],
        query: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> _T:
        result = self._request(
            "GET", path, cast_to=cast_to, query=query,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        assert result is not None
        return result

    def _post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T],
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> _T:
        result = self._request(
            "POST", path, body=body, cast_to=cast_to,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        assert result is not None
        return result

    def _put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T],
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> _T:
        result = self._request(
            "PUT", path, body=body, cast_to=cast_to,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        assert result is not None
        return result

    def _delete(
        self,
        path: str,
        *,
        extra_headers: dict[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> None:
        self._request(
            "DELETE", path, cast_to=None,
            extra_headers=extra_headers, timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SyncAPIClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class AsyncAPIClient:
    """비동기 HTTP 클라이언트 베이스.

    SyncAPIClient와 동일한 인터페이스의 async 버전입니다.
    """

    _client: httpx.AsyncClient
    _api_key: str
    _base_url: str
    _max_retries: int
    _timeout: httpx.Timeout

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.AsyncClient | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries

        if isinstance(timeout, (int, float)):
            self._timeout = httpx.Timeout(timeout)
        else:
            self._timeout = timeout

        if http_client is not None:
            self._client = http_client
        else:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                limits=DEFAULT_CONNECTION_LIMITS,
            )

    def _build_headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"clawops-python/{__version__}",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        cast_to: type[_T] | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> _T | None:
        headers = self._build_headers(extra_headers)

        params = query.copy() if query else {}
        if extra_query:
            params.update(extra_query)

        req_timeout = timeout if timeout is not None else self._timeout
        if isinstance(req_timeout, (int, float)):
            req_timeout = httpx.Timeout(req_timeout)

        import asyncio

        retries_left = self._max_retries
        while True:
            try:
                response = await self._client.request(
                    method=method,
                    url=path,
                    json=body,
                    params=params if params else None,
                    headers=headers,
                    timeout=req_timeout,
                )
            except httpx.TimeoutException as e:
                if retries_left > 0:
                    retries_left -= 1
                    await asyncio.sleep(self._retry_delay(self._max_retries - retries_left))
                    continue
                raise APITimeoutError(
                    request=httpx.Request(method, self._base_url + path),
                ) from e
            except httpx.ConnectError as e:
                if retries_left > 0:
                    retries_left -= 1
                    await asyncio.sleep(self._retry_delay(self._max_retries - retries_left))
                    continue
                raise APIConnectionError(
                    request=httpx.Request(method, self._base_url + path),
                ) from e

            if response.is_success:
                if response.status_code == 204 or cast_to is None:
                    return None
                try:
                    return cast_to.model_validate(response.json())
                except pydantic.ValidationError as e:
                    raise APIResponseValidationError(response=response) from e

            if retries_left > 0 and self._should_retry(response):
                retries_left -= 1
                await asyncio.sleep(self._retry_delay(self._max_retries - retries_left))
                continue

            raise _make_status_error(response=response)

    def _should_retry(self, response: httpx.Response) -> bool:
        if response.status_code in (408, 409, 429):
            return True
        if response.status_code >= 500:
            return True
        return False

    def _retry_delay(self, retries_taken: int) -> float:
        delay = min(INITIAL_RETRY_DELAY * (2 ** retries_taken), MAX_RETRY_DELAY)
        return delay * (1 + random())

    async def _get(
        self,
        path: str,
        *,
        cast_to: type[_T],
        query: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> _T:
        result = await self._request(
            "GET", path, cast_to=cast_to, query=query,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        assert result is not None
        return result

    async def _post(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T],
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> _T:
        result = await self._request(
            "POST", path, body=body, cast_to=cast_to,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        assert result is not None
        return result

    async def _put(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        cast_to: type[_T],
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> _T:
        result = await self._request(
            "PUT", path, body=body, cast_to=cast_to,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        assert result is not None
        return result

    async def _delete(
        self,
        path: str,
        *,
        extra_headers: dict[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> None:
        await self._request(
            "DELETE", path, cast_to=None,
            extra_headers=extra_headers, timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncAPIClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
```

**Step 4: Run tests**

Run: `pytest tests/test_base_client.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add src/clawops/_base_client.py tests/test_base_client.py
git commit -m "feat: add sync/async base HTTP clients with retry and error mapping"
```

---

### Task 8: Resource Base Classes

**Files:**
- Create: `src/clawops/_resource.py`

**Step 1: Implement resource base**

```python
# src/clawops/_resource.py
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._base_client import AsyncAPIClient, SyncAPIClient


class SyncAPIResource:
    """동기 API 리소스의 베이스 클래스.

    모든 리소스(Calls, Numbers 등)는 이 클래스를 상속받습니다.
    부모 클라이언트의 HTTP 메서드에 대한 프록시를 제공합니다.
    """

    _client: SyncAPIClient
    _account_id: str

    def __init__(self, client: SyncAPIClient, account_id: str) -> None:
        self._client = client
        self._account_id = account_id

    @property
    def _base_path(self) -> str:
        return f"/v1/accounts/{self._account_id}"


class AsyncAPIResource:
    """비동기 API 리소스의 베이스 클래스."""

    _client: AsyncAPIClient
    _account_id: str

    def __init__(self, client: AsyncAPIClient, account_id: str) -> None:
        self._client = client
        self._account_id = account_id

    @property
    def _base_path(self) -> str:
        return f"/v1/accounts/{self._account_id}"
```

**Step 2: Commit**

```bash
git add src/clawops/_resource.py
git commit -m "feat: add sync/async API resource base classes"
```

---

### Task 9: Pagination

**Files:**
- Create: `src/clawops/pagination.py`
- Test: `tests/test_pagination.py`

**Step 1: Write tests**

```python
# tests/test_pagination.py
import httpx
import pytest
import respx

from clawops._base_client import SyncAPIClient
from clawops._models import BaseModel
from clawops.pagination import SyncPage
from clawops.types.shared import PaginationMeta


class Item(BaseModel):
    id: int
    name: str


def test_sync_page_iteration():
    meta = PaginationMeta(total=3, page=0, page_size=10)
    page = SyncPage[Item](
        data=[Item(id=1, name="a"), Item(id=2, name="b")],
        meta=meta,
    )
    items = list(page)
    assert len(items) == 2
    assert items[0].id == 1


def test_sync_page_has_next_page_false():
    meta = PaginationMeta(total=2, page=0, page_size=10)
    page = SyncPage[Item](
        data=[Item(id=1, name="a"), Item(id=2, name="b")],
        meta=meta,
    )
    assert page.has_next_page() is False


def test_sync_page_has_next_page_true():
    meta = PaginationMeta(total=30, page=0, page_size=10)
    page = SyncPage[Item](
        data=[Item(id=i, name=f"item{i}") for i in range(10)],
        meta=meta,
    )
    assert page.has_next_page() is True


@respx.mock
def test_auto_paging_iter():
    """auto_paging_iter가 모든 페이지를 자동으로 순회하는지 확인."""
    route = respx.get("https://api.claw-ops.com/items")
    route.side_effect = [
        httpx.Response(200, json={
            "data": [{"id": 3, "name": "c"}],
            "meta": {"total": 3, "page": 1, "pageSize": 2},
        }),
    ]

    client = SyncAPIClient(
        api_key="sk_test",
        base_url="https://api.claw-ops.com",
        max_retries=0,
    )

    meta = PaginationMeta(total=3, page=0, page_size=2)
    first_page = SyncPage[Item](
        data=[Item(id=1, name="a"), Item(id=2, name="b")],
        meta=meta,
    )
    first_page._set_client(client=client, path="/items", cast_to=Item, query={})

    all_items = list(first_page.auto_paging_iter())
    assert len(all_items) == 3
    assert all_items[2].id == 3
    client.close()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pagination.py -v`
Expected: FAIL

**Step 3: Implement pagination**

```python
# src/clawops/pagination.py
from __future__ import annotations

from typing import Any, Generic, Iterator, AsyncIterator, TypeVar, TYPE_CHECKING

import pydantic

from ._models import BaseModel
from .types.shared import PaginationMeta

if TYPE_CHECKING:
    from ._base_client import AsyncAPIClient, SyncAPIClient

_T = TypeVar("_T", bound=pydantic.BaseModel)


class SyncPage(BaseModel, Generic[_T]):
    """동기 페이지네이션 컨테이너.

    API가 반환하는 페이지네이션 응답을 래핑하며,
    자동으로 다음 페이지를 가져와 모든 항목을 순회할 수 있습니다.

    Example::

        # 첫 페이지 항목만 순회
        page = client.calls.list(page_size=20)
        for call in page:
            print(call.call_id)

        # 모든 페이지 자동 순회
        for call in client.calls.list(page_size=50).auto_paging_iter():
            print(call.call_id)
    """

    data: list[Any]
    meta: PaginationMeta

    # 내부 상태 (직렬화 대상 아님)
    _client: SyncAPIClient | None = pydantic.PrivateAttr(default=None)
    _path: str = pydantic.PrivateAttr(default="")
    _cast_to: type[_T] | None = pydantic.PrivateAttr(default=None)
    _query: dict[str, Any] = pydantic.PrivateAttr(default_factory=dict)

    def _set_client(
        self,
        *,
        client: SyncAPIClient,
        path: str,
        cast_to: type[_T],
        query: dict[str, Any],
    ) -> None:
        self._client = client
        self._path = path
        self._cast_to = cast_to
        self._query = query

    def has_next_page(self) -> bool:
        """다음 페이지가 있는지 확인합니다."""
        return (self.meta.page + 1) * self.meta.page_size < self.meta.total

    def next_page(self) -> SyncPage[_T]:
        """다음 페이지를 가져옵니다.

        Returns:
            다음 페이지의 SyncPage 객체.

        Raises:
            RuntimeError: 클라이언트가 설정되지 않은 경우.
            StopIteration: 다음 페이지가 없는 경우.
        """
        if self._client is None:
            raise RuntimeError("Page client is not set")
        if not self.has_next_page():
            raise StopIteration("No more pages")

        next_query = self._query.copy()
        next_query["page"] = self.meta.page + 1

        result = self._client._get(
            self._path,
            cast_to=SyncPage[self._cast_to],  # type: ignore
            query=next_query,
        )
        result._set_client(
            client=self._client,
            path=self._path,
            cast_to=self._cast_to,  # type: ignore
            query=self._query,
        )
        # data를 올바른 타입으로 변환
        if self._cast_to is not None:
            result.data = [
                self._cast_to.model_validate(item) if isinstance(item, dict) else item
                for item in result.data
            ]
        return result  # type: ignore

    def __iter__(self) -> Iterator[_T]:
        return iter(self.data)

    def auto_paging_iter(self) -> Iterator[_T]:
        """모든 페이지의 항목을 자동으로 순회합니다.

        Yields:
            각 페이지의 모든 항목을 순서대로 반환합니다.
        """
        page: SyncPage[_T] = self
        while True:
            yield from page.data
            if not page.has_next_page():
                break
            page = page.next_page()


class AsyncPage(BaseModel, Generic[_T]):
    """비동기 페이지네이션 컨테이너.

    SyncPage의 async 버전입니다.

    Example::

        async for call in (await client.calls.list(page_size=50)).auto_paging_iter():
            print(call.call_id)
    """

    data: list[Any]
    meta: PaginationMeta

    _client: AsyncAPIClient | None = pydantic.PrivateAttr(default=None)
    _path: str = pydantic.PrivateAttr(default="")
    _cast_to: type[_T] | None = pydantic.PrivateAttr(default=None)
    _query: dict[str, Any] = pydantic.PrivateAttr(default_factory=dict)

    def _set_client(
        self,
        *,
        client: AsyncAPIClient,
        path: str,
        cast_to: type[_T],
        query: dict[str, Any],
    ) -> None:
        self._client = client
        self._path = path
        self._cast_to = cast_to
        self._query = query

    def has_next_page(self) -> bool:
        """다음 페이지가 있는지 확인합니다."""
        return (self.meta.page + 1) * self.meta.page_size < self.meta.total

    async def next_page(self) -> AsyncPage[_T]:
        """다음 페이지를 비동기로 가져옵니다."""
        if self._client is None:
            raise RuntimeError("Page client is not set")
        if not self.has_next_page():
            raise StopAsyncIteration("No more pages")

        next_query = self._query.copy()
        next_query["page"] = self.meta.page + 1

        result = await self._client._get(
            self._path,
            cast_to=AsyncPage[self._cast_to],  # type: ignore
            query=next_query,
        )
        result._set_client(
            client=self._client,
            path=self._path,
            cast_to=self._cast_to,  # type: ignore
            query=self._query,
        )
        if self._cast_to is not None:
            result.data = [
                self._cast_to.model_validate(item) if isinstance(item, dict) else item
                for item in result.data
            ]
        return result  # type: ignore

    def __iter__(self) -> Iterator[_T]:
        return iter(self.data)

    async def auto_paging_iter(self) -> AsyncIterator[_T]:
        """모든 페이지의 항목을 비동기로 자동 순회합니다."""
        page: AsyncPage[_T] = self
        while True:
            for item in page.data:
                yield item
            if not page.has_next_page():
                break
            page = await page.next_page()
```

**Step 4: Run tests**

Run: `pytest tests/test_pagination.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add src/clawops/pagination.py tests/test_pagination.py
git commit -m "feat: add sync/async pagination with auto-paging iterator"
```

---

### Task 10: Calls Resource

**Files:**
- Create: `src/clawops/resources/__init__.py`
- Create: `src/clawops/resources/calls.py`
- Test: `tests/test_calls.py`

**Step 1: Write tests**

```python
# tests/test_calls.py
import httpx
import pytest
import respx

from clawops._base_client import SyncAPIClient
from clawops.resources.calls import Calls
from clawops.types.call import Call, CallControlResponse


BASE = "https://api.claw-ops.com"
ACCOUNT = "AC1a2b3c4d"
CALLS_PATH = f"/v1/accounts/{ACCOUNT}/calls"


@pytest.fixture
def client():
    c = SyncAPIClient(api_key="sk_test", base_url=BASE, max_retries=0)
    yield c
    c.close()


@pytest.fixture
def calls(client):
    return Calls(client=client, account_id=ACCOUNT)


CALL_JSON = {
    "callId": "CA0123456789abcdef0123456789abcdef",
    "status": "queued",
    "to": "01012345678",
    "from": "07052358010",
    "direction": "outbound",
    "duration": None,
    "accountId": "AC1a2b3c4d",
    "dateCreated": "2025-06-01T12:00:00Z",
    "dateUpdated": None,
}


class TestCallsCreate:
    @respx.mock
    def test_create_call(self, calls):
        respx.post(f"{BASE}{CALLS_PATH}").mock(
            return_value=httpx.Response(201, json=CALL_JSON)
        )
        call = calls.create(
            to="01012345678",
            from_="07052358010",
            url="https://my-app.com/twiml",
        )
        assert isinstance(call, Call)
        assert call.call_id == "CA0123456789abcdef0123456789abcdef"
        assert call.status == "queued"
        assert call.from_ == "07052358010"

    @respx.mock
    def test_create_call_with_status_callback(self, calls):
        route = respx.post(f"{BASE}{CALLS_PATH}").mock(
            return_value=httpx.Response(201, json=CALL_JSON)
        )
        calls.create(
            to="01012345678",
            from_="07052358010",
            url="https://my-app.com/twiml",
            status_callback="https://my-app.com/status",
            status_callback_event="initiated ringing answered completed",
        )
        body = route.calls[0].request.content
        import json
        parsed = json.loads(body)
        assert parsed["StatusCallback"] == "https://my-app.com/status"

    @respx.mock
    def test_create_call_sip_uri(self, calls):
        respx.post(f"{BASE}{CALLS_PATH}").mock(
            return_value=httpx.Response(201, json={**CALL_JSON, "to": "sip:usr_abc@sip.claw-ops.com"})
        )
        call = calls.create(
            to="sip:usr_abc@sip.claw-ops.com",
            from_="07052358010",
            url="https://my-app.com/twiml",
        )
        assert call.to == "sip:usr_abc@sip.claw-ops.com"


class TestCallsList:
    @respx.mock
    def test_list_calls(self, calls):
        respx.get(f"{BASE}{CALLS_PATH}").mock(
            return_value=httpx.Response(200, json={
                "data": [CALL_JSON],
                "meta": {"total": 1, "page": 0, "pageSize": 20},
            })
        )
        page = calls.list()
        items = list(page)
        assert len(items) == 1
        assert isinstance(items[0], Call)

    @respx.mock
    def test_list_calls_with_filters(self, calls):
        route = respx.get(f"{BASE}{CALLS_PATH}").mock(
            return_value=httpx.Response(200, json={
                "data": [],
                "meta": {"total": 0, "page": 0, "pageSize": 10},
            })
        )
        calls.list(status="completed", page=0, page_size=10)
        request_url = str(route.calls[0].request.url)
        assert "status=completed" in request_url
        assert "pageSize=10" in request_url


class TestCallsGet:
    @respx.mock
    def test_get_call(self, calls):
        call_id = "CA0123456789abcdef0123456789abcdef"
        respx.get(f"{BASE}{CALLS_PATH}/{call_id}").mock(
            return_value=httpx.Response(200, json=CALL_JSON)
        )
        call = calls.get(call_id)
        assert isinstance(call, Call)
        assert call.call_id == call_id


class TestCallsUpdate:
    @respx.mock
    def test_update_call_completed(self, calls):
        call_id = "CA0123456789abcdef0123456789abcdef"
        respx.post(f"{BASE}{CALLS_PATH}/{call_id}").mock(
            return_value=httpx.Response(200, json={"callId": call_id, "status": "completed"})
        )
        result = calls.update(call_id, status="completed")
        assert isinstance(result, CallControlResponse)
        assert result.status == "completed"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_calls.py -v`
Expected: FAIL

**Step 3: Implement Calls resource**

```python
# src/clawops/resources/__init__.py
from .calls import AsyncCalls, Calls
from .numbers import AsyncNumbers, Numbers

__all__ = [
    "AsyncCalls",
    "AsyncNumbers",
    "Calls",
    "Numbers",
]
```

```python
# src/clawops/resources/calls.py
from __future__ import annotations

from typing import Literal

from .._resource import AsyncAPIResource, SyncAPIResource
from .._utils import strip_not_given
from ..pagination import AsyncPage, SyncPage
from ..types.call import Call, CallControlResponse


class Calls(SyncAPIResource):
    """통화(Calls) 리소스.

    아웃바운드 전화 발신, 통화 목록 조회, 단건 조회, 통화 제어(종료)를 수행합니다.
    """

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

        PSTN 번호 또는 SIP URI로 아웃바운드 전화를 발신합니다.
        From 번호는 계정에 등록된 번호여야 합니다.

        **PSTN 발신**: to에 전화번호를 입력하면 통신사 트렁크를 통해 일반 전화로 발신됩니다.
        - 예: ``to="01012345678"``

        **SIP 내선 발신**: to에 ``sip:`` URI를 입력하면 등록된 SIP 클라이언트로 직접 발신됩니다.
        - 예: ``to="sip:usr_aBcDeFgHiJkL@sip.claw-ops.com"``
        - SIP username은 SIP Credential 생성 시 발급된 username을 사용합니다.

        Args:
            to: 수신 대상. 전화번호(PSTN 발신) 또는 sip: URI(내선 발신).
            from_: 발신 번호. 계정에 등록된 번호여야 합니다 (예: '07052358010').
            url: 통화 연결 시 TwiML 명령을 반환할 URL.
            status_callback: 통화 상태 변경 시 POST 요청을 받을 콜백 URL.
            status_callback_event: 수신할 상태 이벤트 목록 (공백 구분).
                기본값: 'initiated ringing answered completed'.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초). 클라이언트 기본값을 오버라이드.

        Returns:
            생성된 Call 객체.

        Raises:
            BadRequestError: From 번호가 계정에 등록되지 않았거나 필수 필드 누락.
            AuthenticationError: 유효하지 않은 API 키.
            PermissionDeniedError: accountId 불일치.
            InternalServerError: 발신 실패.
            ServiceUnavailableError: ARI 서비스가 준비되지 않음.
        """
        body = strip_not_given({
            "To": to,
            "From": from_,
            "Url": url,
            "StatusCallback": status_callback,
            "StatusCallbackEvent": status_callback_event,
        })
        return self._client._post(
            f"{self._base_path}/calls",
            body=body,
            cast_to=Call,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    def list(
        self,
        *,
        status: Literal["queued", "ringing", "in-progress", "completed", "failed"] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> SyncPage[Call]:
        """통화 목록을 조회합니다.

        계정의 통화 로그를 페이지네이션으로 조회합니다.
        ``auto_paging_iter()``를 사용하면 모든 페이지를 자동으로 순회할 수 있습니다.

        Args:
            status: 통화 상태로 필터링. queued, ringing, in-progress, completed, failed.
            page: 페이지 번호 (0부터 시작, 기본값 0).
            page_size: 페이지당 항목 수 (기본 20, 최대 100).
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            Call 객체의 페이지. ``auto_paging_iter()``로 전체 순회 가능.

        Raises:
            BadRequestError: pageSize 또는 page가 정수가 아닌 경우.
            AuthenticationError: 유효하지 않은 API 키.
            PermissionDeniedError: accountId 불일치.
        """
        query = strip_not_given({
            "status": status,
            "page": page,
            "pageSize": page_size,
        })
        path = f"{self._base_path}/calls"
        result = self._client._get(
            path,
            cast_to=SyncPage[Call],
            query=query if query else None,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )
        # data를 Call 모델로 변환
        result.data = [
            Call.model_validate(item) if isinstance(item, dict) else item
            for item in result.data
        ]
        result._set_client(client=self._client, path=path, cast_to=Call, query=query)
        return result

    def get(
        self,
        call_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> Call:
        """특정 통화의 상세 정보를 조회합니다.

        Args:
            call_id: 통화 ID (예: 'CAabcdef1234567890').
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            Call 객체.

        Raises:
            NotFoundError: 해당 통화를 찾을 수 없음.
            AuthenticationError: 유효하지 않은 API 키.
            PermissionDeniedError: accountId 불일치.
        """
        return self._client._get(
            f"{self._base_path}/calls/{call_id}",
            cast_to=Call,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    def update(
        self,
        call_id: str,
        *,
        status: Literal["completed"] = "completed",
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> CallControlResponse:
        """진행 중인 통화를 제어(종료)합니다.

        현재 Status='completed'(통화 종료)만 지원합니다.

        Args:
            call_id: 종료할 통화의 ID.
            status: 변경할 상태. 현재 'completed'만 지원.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            CallControlResponse 객체.

        Raises:
            BadRequestError: 지원되지 않는 Status 값.
            NotFoundError: 해당 통화를 찾을 수 없음.
            AuthenticationError: 유효하지 않은 API 키.
            PermissionDeniedError: accountId 불일치.
        """
        return self._client._post(
            f"{self._base_path}/calls/{call_id}",
            body={"Status": status},
            cast_to=CallControlResponse,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )


class AsyncCalls(AsyncAPIResource):
    """통화(Calls) 비동기 리소스.

    Calls의 async 버전입니다. 모든 메서드가 async/await를 사용합니다.
    """

    async def create(
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

        PSTN 번호 또는 SIP URI로 아웃바운드 전화를 발신합니다.
        From 번호는 계정에 등록된 번호여야 합니다.

        **PSTN 발신**: to에 전화번호를 입력하면 통신사 트렁크를 통해 일반 전화로 발신됩니다.
        - 예: ``to="01012345678"``

        **SIP 내선 발신**: to에 ``sip:`` URI를 입력하면 등록된 SIP 클라이언트로 직접 발신됩니다.
        - 예: ``to="sip:usr_aBcDeFgHiJkL@sip.claw-ops.com"``

        Args:
            to: 수신 대상. 전화번호(PSTN 발신) 또는 sip: URI(내선 발신).
            from_: 발신 번호. 계정에 등록된 번호여야 합니다.
            url: 통화 연결 시 TwiML 명령을 반환할 URL.
            status_callback: 통화 상태 변경 시 POST 요청을 받을 콜백 URL.
            status_callback_event: 수신할 상태 이벤트 목록 (공백 구분).
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            생성된 Call 객체.
        """
        body = strip_not_given({
            "To": to,
            "From": from_,
            "Url": url,
            "StatusCallback": status_callback,
            "StatusCallbackEvent": status_callback_event,
        })
        return await self._client._post(
            f"{self._base_path}/calls",
            body=body,
            cast_to=Call,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    async def list(
        self,
        *,
        status: Literal["queued", "ringing", "in-progress", "completed", "failed"] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> AsyncPage[Call]:
        """통화 목록을 비동기로 조회합니다.

        Args:
            status: 통화 상태로 필터링.
            page: 페이지 번호 (0부터 시작).
            page_size: 페이지당 항목 수 (기본 20, 최대 100).
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            Call 객체의 AsyncPage.
        """
        query = strip_not_given({
            "status": status,
            "page": page,
            "pageSize": page_size,
        })
        path = f"{self._base_path}/calls"
        result = await self._client._get(
            path,
            cast_to=AsyncPage[Call],
            query=query if query else None,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )
        result.data = [
            Call.model_validate(item) if isinstance(item, dict) else item
            for item in result.data
        ]
        result._set_client(client=self._client, path=path, cast_to=Call, query=query)
        return result

    async def get(
        self,
        call_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> Call:
        """특정 통화의 상세 정보를 비동기로 조회합니다.

        Args:
            call_id: 통화 ID.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            Call 객체.
        """
        return await self._client._get(
            f"{self._base_path}/calls/{call_id}",
            cast_to=Call,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    async def update(
        self,
        call_id: str,
        *,
        status: Literal["completed"] = "completed",
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> CallControlResponse:
        """진행 중인 통화를 비동기로 제어(종료)합니다.

        Args:
            call_id: 종료할 통화의 ID.
            status: 변경할 상태. 현재 'completed'만 지원.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            CallControlResponse 객체.
        """
        return await self._client._post(
            f"{self._base_path}/calls/{call_id}",
            body={"Status": status},
            cast_to=CallControlResponse,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )
```

**Step 4: Run tests**

Run: `pytest tests/test_calls.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add src/clawops/resources/ tests/test_calls.py
git commit -m "feat: add Calls resource with create, list, get, update"
```

---

### Task 11: Numbers Resource

**Files:**
- Create: `src/clawops/resources/numbers.py`
- Test: `tests/test_numbers.py`

**Step 1: Write tests**

```python
# tests/test_numbers.py
import httpx
import pytest
import respx

from clawops._base_client import SyncAPIClient
from clawops.resources.numbers import Numbers
from clawops.types.number import PhoneNumber, NumberListItem, NumberUpdateResponse


BASE = "https://api.claw-ops.com"
ACCOUNT = "AC1a2b3c4d"
NUMBERS_PATH = f"/v1/accounts/{ACCOUNT}/numbers"


@pytest.fixture
def client():
    c = SyncAPIClient(api_key="sk_test", base_url=BASE, max_retries=0)
    yield c
    c.close()


@pytest.fixture
def numbers(client):
    return Numbers(client=client, account_id=ACCOUNT)


class TestNumbersCreate:
    @respx.mock
    def test_create_pool_number(self, numbers):
        respx.post(f"{BASE}{NUMBERS_PATH}").mock(
            return_value=httpx.Response(201, json={"number": "07012340001", "source": "pool"})
        )
        num = numbers.create()
        assert isinstance(num, PhoneNumber)
        assert num.number == "07012340001"
        assert num.source == "pool"

    @respx.mock
    def test_create_sip_number(self, numbers):
        route = respx.post(f"{BASE}{NUMBERS_PATH}").mock(
            return_value=httpx.Response(201, json={"number": "1001", "source": "sip"})
        )
        num = numbers.create(source="sip", number="1001")
        assert num.source == "sip"
        assert num.number == "1001"
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["source"] == "sip"
        assert body["number"] == "1001"

    @respx.mock
    def test_create_with_webhook(self, numbers):
        route = respx.post(f"{BASE}{NUMBERS_PATH}").mock(
            return_value=httpx.Response(201, json={"number": "07012340001", "source": "pool"})
        )
        numbers.create(webhook_url="https://my-app.com/voice")
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["webhookUrl"] == "https://my-app.com/voice"


class TestNumbersList:
    @respx.mock
    def test_list_numbers(self, numbers):
        respx.get(f"{BASE}{NUMBERS_PATH}").mock(
            return_value=httpx.Response(200, json={
                "numbers": [
                    {"number": "07012340001", "source": "pool", "webhookUrl": None, "createdAt": "2025-06-01T12:00:00Z"},
                    {"number": "1001", "source": "sip", "webhookUrl": "https://my-app.com", "createdAt": "2025-06-01T12:00:00Z"},
                ]
            })
        )
        result = numbers.list()
        assert len(result) == 2
        assert isinstance(result[0], NumberListItem)
        assert result[1].source == "sip"


class TestNumbersUpdate:
    @respx.mock
    def test_update_webhook(self, numbers):
        respx.put(f"{BASE}{NUMBERS_PATH}/1001").mock(
            return_value=httpx.Response(200, json={
                "number": "1001", "source": "sip",
                "webhookUrl": "https://new-url.com", "webhookMethod": "POST",
            })
        )
        result = numbers.update("1001", webhook_url="https://new-url.com")
        assert isinstance(result, NumberUpdateResponse)
        assert result.webhook_url == "https://new-url.com"

    @respx.mock
    def test_update_method(self, numbers):
        respx.put(f"{BASE}{NUMBERS_PATH}/1001").mock(
            return_value=httpx.Response(200, json={
                "number": "1001", "source": "sip",
                "webhookUrl": None, "webhookMethod": "GET",
            })
        )
        result = numbers.update("1001", webhook_method="GET")
        assert result.webhook_method == "GET"


class TestNumbersDelete:
    @respx.mock
    def test_delete_number(self, numbers):
        respx.delete(f"{BASE}{NUMBERS_PATH}/07012340001").mock(
            return_value=httpx.Response(204)
        )
        result = numbers.delete("07012340001")
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_numbers.py -v`
Expected: FAIL

**Step 3: Implement Numbers resource**

```python
# src/clawops/resources/numbers.py
from __future__ import annotations

from typing import Literal

from .._resource import AsyncAPIResource, SyncAPIResource
from .._utils import strip_not_given
from ..types.number import NumberListItem, NumberUpdateResponse, PhoneNumber


class _NumbersListResponse:
    """번호 목록 응답을 파싱하기 위한 내부 헬퍼."""

    def __init__(self, numbers: list[NumberListItem]) -> None:
        self.numbers = numbers


class Numbers(SyncAPIResource):
    """전화번호(Numbers) 리소스.

    PSTN 번호 발급, SIP 내선번호 등록, 번호 목록 조회, 설정 수정, 삭제를 수행합니다.
    """

    def create(
        self,
        *,
        source: Literal["pool", "sip"] | None = None,
        number: str | None = None,
        webhook_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> PhoneNumber:
        """번호를 등록합니다.

        PSTN 번호 풀에서 자동 발급하거나, SIP 내선번호를 직접 등록합니다.

        source를 생략하거나 'pool'로 지정하면 번호 풀에서 자동 발급됩니다.
        'sip'으로 지정하면 number 파라미터에 원하는 번호를 직접 지정합니다.
        SIP 번호는 통신사 번호 형식(010, 070, 02 등)을 사용할 수 없습니다.

        계정별 번호 할당량(quota)이 설정되어 있으며, 한도 초과 시 422 에러가 반환됩니다.

        Args:
            source: 번호 유형. 'pool'=PSTN 풀 발급 (기본값), 'sip'=SIP 내선번호 직접 등록.
            number: SIP 내선번호 (source='sip'일 때 필수, 3~20자리 숫자).
                통신사 번호 형식(010, 070, 02 등)은 사용할 수 없습니다.
            webhook_url: 수신 전화 처리용 Webhook URL (선택).
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            등록된 PhoneNumber 객체.

        Raises:
            BadRequestError: 번호 형식 오류, 통신사 번호 형식 사용 등.
            ConflictError: 번호 중복 (이미 등록되었거나 풀에 예약된 번호).
            UnprocessableEntityError: 번호 할당량 초과.
            ServiceUnavailableError: 발급 가능한 번호 없음 또는 서비스 불가.
        """
        body = strip_not_given({
            "source": source,
            "number": number,
            "webhookUrl": webhook_url,
        })
        return self._client._post(
            f"{self._base_path}/numbers",
            body=body if body else None,
            cast_to=PhoneNumber,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    def list(
        self,
        *,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> list[NumberListItem]:
        """등록된 번호 목록을 조회합니다.

        계정에 등록된 전화번호 목록을 반환합니다.
        source='pool'은 PSTN 풀에서 발급된 번호, source='sip'은 SIP 내선번호입니다.

        Args:
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            NumberListItem 리스트.

        Raises:
            AuthenticationError: 유효하지 않은 API 키.
            PermissionDeniedError: accountId 불일치.
        """
        from .._models import BaseModel

        class _NumbersResponse(BaseModel):
            numbers: list[NumberListItem]

        result = self._client._get(
            f"{self._base_path}/numbers",
            cast_to=_NumbersResponse,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )
        return result.numbers

    def update(
        self,
        number: str,
        *,
        webhook_url: str | None = None,
        webhook_method: Literal["POST", "GET"] | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> NumberUpdateResponse:
        """등록된 번호의 설정을 수정합니다.

        번호 자체는 변경할 수 없으며, webhookUrl과 webhookMethod만 수정 가능합니다.

        Args:
            number: 수정할 전화번호 (예: '1001' 또는 '07012340001').
            webhook_url: 수신 전화 처리용 Webhook URL.
            webhook_method: Webhook 호출 HTTP 메서드. 'POST' 또는 'GET'.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            수정된 NumberUpdateResponse 객체.

        Raises:
            BadRequestError: 수정할 필드 없음 또는 잘못된 webhookMethod.
            NotFoundError: 번호를 찾을 수 없음.
            PermissionDeniedError: 번호 소유권 없음.
        """
        body = strip_not_given({
            "webhookUrl": webhook_url,
            "webhookMethod": webhook_method,
        })
        return self._client._put(
            f"{self._base_path}/numbers/{number}",
            body=body,
            cast_to=NumberUpdateResponse,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    def delete(
        self,
        number: str,
        *,
        extra_headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> None:
        """등록된 번호를 삭제합니다.

        PSTN 번호(source=pool)는 풀로 복귀되고,
        SIP 번호(source=sip)는 단순 삭제됩니다.

        Args:
            number: 삭제할 전화번호 (예: '07012340001').
            extra_headers: 추가 HTTP 헤더.
            timeout: 이 요청의 타임아웃 (초).

        Raises:
            NotFoundError: 번호를 찾을 수 없음.
            PermissionDeniedError: 번호 소유권 없음.
            ServiceUnavailableError: 번호 반납 기능 사용 불가.
        """
        self._client._delete(
            f"{self._base_path}/numbers/{number}",
            extra_headers=extra_headers,
            timeout=timeout,
        )


class AsyncNumbers(AsyncAPIResource):
    """전화번호(Numbers) 비동기 리소스."""

    async def create(
        self,
        *,
        source: Literal["pool", "sip"] | None = None,
        number: str | None = None,
        webhook_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> PhoneNumber:
        """번호를 비동기로 등록합니다.

        Args:
            source: 번호 유형. 'pool' 또는 'sip'.
            number: SIP 내선번호 (source='sip'일 때 필수).
            webhook_url: Webhook URL (선택).
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            등록된 PhoneNumber 객체.
        """
        body = strip_not_given({
            "source": source,
            "number": number,
            "webhookUrl": webhook_url,
        })
        return await self._client._post(
            f"{self._base_path}/numbers",
            body=body if body else None,
            cast_to=PhoneNumber,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    async def list(
        self,
        *,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> list[NumberListItem]:
        """등록된 번호 목록을 비동기로 조회합니다.

        Args:
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            NumberListItem 리스트.
        """
        from .._models import BaseModel

        class _NumbersResponse(BaseModel):
            numbers: list[NumberListItem]

        result = await self._client._get(
            f"{self._base_path}/numbers",
            cast_to=_NumbersResponse,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )
        return result.numbers

    async def update(
        self,
        number: str,
        *,
        webhook_url: str | None = None,
        webhook_method: Literal["POST", "GET"] | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> NumberUpdateResponse:
        """등록된 번호의 설정을 비동기로 수정합니다.

        Args:
            number: 수정할 전화번호.
            webhook_url: Webhook URL.
            webhook_method: 'POST' 또는 'GET'.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            수정된 NumberUpdateResponse 객체.
        """
        body = strip_not_given({
            "webhookUrl": webhook_url,
            "webhookMethod": webhook_method,
        })
        return await self._client._put(
            f"{self._base_path}/numbers/{number}",
            body=body,
            cast_to=NumberUpdateResponse,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    async def delete(
        self,
        number: str,
        *,
        extra_headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> None:
        """등록된 번호를 비동기로 삭제합니다.

        Args:
            number: 삭제할 전화번호.
            extra_headers: 추가 HTTP 헤더.
            timeout: 이 요청의 타임아웃 (초).
        """
        await self._client._delete(
            f"{self._base_path}/numbers/{number}",
            extra_headers=extra_headers,
            timeout=timeout,
        )
```

**Step 4: Run tests**

Run: `pytest tests/test_numbers.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add src/clawops/resources/numbers.py tests/test_numbers.py
git commit -m "feat: add Numbers resource with create, list, update, delete"
```

---

### Task 12: SIP Credentials Resource

**Files:**
- Create: `src/clawops/resources/sip/__init__.py`
- Create: `src/clawops/resources/sip/credentials.py`
- Test: `tests/test_sip_credentials.py`

**Step 1: Write tests**

```python
# tests/test_sip_credentials.py
import httpx
import pytest
import respx

from clawops._base_client import SyncAPIClient
from clawops.resources.sip.credentials import SipCredentials
from clawops.types.sip.credential import SipCredential, SipCredentialListItem


BASE = "https://api.claw-ops.com"
ACCOUNT = "AC1a2b3c4d"
CREDS_PATH = f"/v1/accounts/{ACCOUNT}/sip/credentials"


@pytest.fixture
def client():
    c = SyncAPIClient(api_key="sk_test", base_url=BASE, max_retries=0)
    yield c
    c.close()


@pytest.fixture
def creds(client):
    return SipCredentials(client=client, account_id=ACCOUNT)


CRED_JSON = {
    "id": "clu1abc2def3ghi",
    "username": "usr_aBcDeFgHiJkL",
    "password": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    "displayName": "Office Phone",
    "sipServer": "sip.claw-ops.com",
    "sipPort": 5060,
    "transport": "UDP",
    "createdAt": "2025-06-01T12:00:00Z",
}


class TestSipCredentialsCreate:
    @respx.mock
    def test_create(self, creds):
        respx.post(f"{BASE}{CREDS_PATH}").mock(
            return_value=httpx.Response(201, json=CRED_JSON)
        )
        cred = creds.create(display_name="Office Phone")
        assert isinstance(cred, SipCredential)
        assert cred.username == "usr_aBcDeFgHiJkL"
        assert cred.password == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        assert cred.sip_server == "sip.claw-ops.com"

    @respx.mock
    def test_create_without_display_name(self, creds):
        respx.post(f"{BASE}{CREDS_PATH}").mock(
            return_value=httpx.Response(201, json={**CRED_JSON, "displayName": None})
        )
        cred = creds.create()
        assert cred.display_name is None


class TestSipCredentialsList:
    @respx.mock
    def test_list(self, creds):
        respx.get(f"{BASE}{CREDS_PATH}").mock(
            return_value=httpx.Response(200, json={
                "credentials": [
                    {"id": "clu1", "username": "usr_abc", "displayName": None, "createdAt": "2025-06-01T12:00:00Z"},
                    {"id": "clu2", "username": "usr_def", "displayName": "Phone 2", "createdAt": "2025-06-01T12:00:00Z"},
                ]
            })
        )
        result = creds.list()
        assert len(result) == 2
        assert isinstance(result[0], SipCredentialListItem)


class TestSipCredentialsGet:
    @respx.mock
    def test_get(self, creds):
        cred_id = "clu1abc2def3ghi"
        respx.get(f"{BASE}{CREDS_PATH}/{cred_id}").mock(
            return_value=httpx.Response(200, json={
                "id": cred_id, "username": "usr_aBcDeFgHiJkL",
                "displayName": "Office Phone", "createdAt": "2025-06-01T12:00:00Z",
            })
        )
        result = creds.get(cred_id)
        assert isinstance(result, SipCredentialListItem)
        assert result.id == cred_id


class TestSipCredentialsDelete:
    @respx.mock
    def test_delete(self, creds):
        cred_id = "clu1abc2def3ghi"
        respx.delete(f"{BASE}{CREDS_PATH}/{cred_id}").mock(
            return_value=httpx.Response(204)
        )
        result = creds.delete(cred_id)
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sip_credentials.py -v`
Expected: FAIL

**Step 3: Implement SIP Credentials resource**

```python
# src/clawops/resources/sip/__init__.py
from __future__ import annotations

from typing import TYPE_CHECKING

from ..._resource import AsyncAPIResource, SyncAPIResource
from .credentials import AsyncSipCredentials, SipCredentials

if TYPE_CHECKING:
    from ..._base_client import AsyncAPIClient, SyncAPIClient

__all__ = ["AsyncSip", "AsyncSipCredentials", "Sip", "SipCredentials"]


class Sip(SyncAPIResource):
    """SIP 리소스 컨테이너.

    ``client.sip.credentials`` 로 SIP Credential 리소스에 접근합니다.
    """

    @property
    def credentials(self) -> SipCredentials:
        return SipCredentials(client=self._client, account_id=self._account_id)


class AsyncSip(AsyncAPIResource):
    """SIP 비동기 리소스 컨테이너."""

    @property
    def credentials(self) -> AsyncSipCredentials:
        return AsyncSipCredentials(client=self._client, account_id=self._account_id)
```

```python
# src/clawops/resources/sip/credentials.py
from __future__ import annotations

from ..._resource import AsyncAPIResource, SyncAPIResource
from ..._utils import strip_not_given
from ...types.sip.credential import SipCredential, SipCredentialListItem


class SipCredentials(SyncAPIResource):
    """SIP Credentials 리소스.

    Linphone 등 SIP 클라이언트 등록에 사용할 자격증명을 관리합니다.
    계정당 최대 10개까지 생성할 수 있습니다.
    """

    def create(
        self,
        *,
        display_name: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> SipCredential:
        """SIP Credential을 생성합니다.

        Asterisk PJSIP Realtime 테이블에 자동으로 등록됩니다.
        password는 이 응답에서만 반환되며, 이후 조회 시에는 포함되지 않습니다.

        Args:
            display_name: 디스플레이 이름 (선택). SIP 클라이언트에 표시되는 이름입니다.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            생성된 SipCredential 객체 (password 포함).

        Raises:
            UnprocessableEntityError: SIP credential 한도 초과 (최대 10개).
            AuthenticationError: 유효하지 않은 API 키.
            PermissionDeniedError: accountId 불일치.
        """
        body = strip_not_given({"displayName": display_name})
        return self._client._post(
            f"{self._base_path}/sip/credentials",
            body=body if body else {},
            cast_to=SipCredential,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    def list(
        self,
        *,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> list[SipCredentialListItem]:
        """SIP Credential 목록을 조회합니다.

        password는 반환되지 않습니다.

        Args:
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            SipCredentialListItem 리스트.

        Raises:
            AuthenticationError: 유효하지 않은 API 키.
            PermissionDeniedError: accountId 불일치.
        """
        from ..._models import BaseModel

        class _CredentialsResponse(BaseModel):
            credentials: list[SipCredentialListItem]

        result = self._client._get(
            f"{self._base_path}/sip/credentials",
            cast_to=_CredentialsResponse,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )
        return result.credentials

    def get(
        self,
        credential_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> SipCredentialListItem:
        """특정 SIP Credential의 상세 정보를 조회합니다.

        password는 반환되지 않습니다.

        Args:
            credential_id: Credential ID.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            SipCredentialListItem 객체.

        Raises:
            NotFoundError: SIP credential을 찾을 수 없음.
        """
        return self._client._get(
            f"{self._base_path}/sip/credentials/{credential_id}",
            cast_to=SipCredentialListItem,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    def delete(
        self,
        credential_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> None:
        """SIP Credential을 삭제합니다.

        Asterisk PJSIP Realtime 테이블에서도 자동으로 제거됩니다.
        이 credential을 사용하는 SIP 클라이언트의 등록이 즉시 해제됩니다.

        Args:
            credential_id: 삭제할 Credential ID.
            extra_headers: 추가 HTTP 헤더.
            timeout: 이 요청의 타임아웃 (초).

        Raises:
            NotFoundError: SIP credential을 찾을 수 없음.
        """
        self._client._delete(
            f"{self._base_path}/sip/credentials/{credential_id}",
            extra_headers=extra_headers,
            timeout=timeout,
        )


class AsyncSipCredentials(AsyncAPIResource):
    """SIP Credentials 비동기 리소스."""

    async def create(
        self,
        *,
        display_name: str | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> SipCredential:
        """SIP Credential을 비동기로 생성합니다.

        Args:
            display_name: 디스플레이 이름 (선택).
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            생성된 SipCredential 객체 (password 포함).
        """
        body = strip_not_given({"displayName": display_name})
        return await self._client._post(
            f"{self._base_path}/sip/credentials",
            body=body if body else {},
            cast_to=SipCredential,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    async def list(
        self,
        *,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> list[SipCredentialListItem]:
        """SIP Credential 목록을 비동기로 조회합니다.

        Args:
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            SipCredentialListItem 리스트.
        """
        from ..._models import BaseModel

        class _CredentialsResponse(BaseModel):
            credentials: list[SipCredentialListItem]

        result = await self._client._get(
            f"{self._base_path}/sip/credentials",
            cast_to=_CredentialsResponse,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )
        return result.credentials

    async def get(
        self,
        credential_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> SipCredentialListItem:
        """특정 SIP Credential을 비동기로 조회합니다.

        Args:
            credential_id: Credential ID.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            SipCredentialListItem 객체.
        """
        return await self._client._get(
            f"{self._base_path}/sip/credentials/{credential_id}",
            cast_to=SipCredentialListItem,
            extra_headers=extra_headers,
            extra_query=extra_query,
            timeout=timeout,
        )

    async def delete(
        self,
        credential_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> None:
        """SIP Credential을 비동기로 삭제합니다.

        Args:
            credential_id: 삭제할 Credential ID.
            extra_headers: 추가 HTTP 헤더.
            timeout: 이 요청의 타임아웃 (초).
        """
        await self._client._delete(
            f"{self._base_path}/sip/credentials/{credential_id}",
            extra_headers=extra_headers,
            timeout=timeout,
        )
```

**Step 4: Run tests**

Run: `pytest tests/test_sip_credentials.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add src/clawops/resources/sip/ tests/test_sip_credentials.py
git commit -m "feat: add SIP Credentials resource with create, list, get, delete"
```

---

### Task 13: Client Classes & Accounts Resource

**Files:**
- Create: `src/clawops/_client.py`
- Create: `src/clawops/resources/accounts.py`
- Test: `tests/test_client.py`

**Step 1: Write tests**

```python
# tests/test_client.py
import os
import httpx
import pytest
import respx

from clawops import ClawOps, AsyncClawOps
from clawops.resources.calls import Calls, AsyncCalls
from clawops.resources.numbers import Numbers, AsyncNumbers
from clawops.resources.sip import Sip, AsyncSip
from clawops._exceptions import ClawOpsError


BASE = "https://api.claw-ops.com"


class TestClawOpsClient:
    def test_basic_init(self):
        client = ClawOps(api_key="sk_test_key", account_id="AC123")
        assert isinstance(client.calls, Calls)
        assert isinstance(client.numbers, Numbers)
        assert isinstance(client.sip, Sip)
        client.close()

    def test_env_var_init(self, monkeypatch):
        monkeypatch.setenv("CLAWOPS_API_KEY", "sk_env_key")
        monkeypatch.setenv("CLAWOPS_ACCOUNT_ID", "AC_env")
        client = ClawOps()
        assert client._api_key == "sk_env_key"
        assert client._default_account_id == "AC_env"
        client.close()

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("CLAWOPS_API_KEY", raising=False)
        with pytest.raises(ClawOpsError, match="api_key"):
            ClawOps(account_id="AC123")

    def test_missing_account_id_raises(self, monkeypatch):
        monkeypatch.delenv("CLAWOPS_ACCOUNT_ID", raising=False)
        with pytest.raises(ClawOpsError, match="account_id"):
            ClawOps(api_key="sk_test")

    def test_accounts_returns_new_context(self):
        client = ClawOps(api_key="sk_test", account_id="AC_main")
        other = client.accounts("AC_other")
        assert isinstance(other.calls, Calls)
        # 원래 클라이언트의 account는 변하지 않음
        assert client.calls._account_id == "AC_main"
        assert other.calls._account_id == "AC_other"
        client.close()

    def test_context_manager(self):
        with ClawOps(api_key="sk_test", account_id="AC123") as client:
            assert isinstance(client.calls, Calls)

    def test_custom_base_url(self):
        client = ClawOps(api_key="sk_test", account_id="AC123", base_url="https://custom.api.com")
        assert client._base_url == "https://custom.api.com"
        client.close()

    @respx.mock
    def test_end_to_end_call_create(self):
        respx.post(f"{BASE}/v1/accounts/AC123/calls").mock(
            return_value=httpx.Response(201, json={
                "callId": "CA_test", "status": "queued",
                "to": "010", "from": "070", "direction": "outbound",
                "accountId": "AC123", "dateCreated": "2025-01-01T00:00:00Z",
            })
        )
        with ClawOps(api_key="sk_test", account_id="AC123", max_retries=0) as client:
            call = client.calls.create(to="010", from_="070", url="https://twiml.com")
            assert call.call_id == "CA_test"


class TestAsyncClawOpsClient:
    @pytest.mark.asyncio
    async def test_basic_init(self):
        client = AsyncClawOps(api_key="sk_test", account_id="AC123")
        assert isinstance(client.calls, AsyncCalls)
        assert isinstance(client.numbers, AsyncNumbers)
        assert isinstance(client.sip, AsyncSip)
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with AsyncClawOps(api_key="sk_test", account_id="AC123") as client:
            assert isinstance(client.calls, AsyncCalls)

    @pytest.mark.asyncio
    async def test_accounts(self):
        async with AsyncClawOps(api_key="sk_test", account_id="AC_main") as client:
            other = client.accounts("AC_other")
            assert other.calls._account_id == "AC_other"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client.py -v`
Expected: FAIL

**Step 3: Implement Accounts resource**

```python
# src/clawops/resources/accounts.py
from __future__ import annotations

from typing import TYPE_CHECKING

from .calls import AsyncCalls, Calls
from .numbers import AsyncNumbers, Numbers
from .sip import AsyncSip, Sip

if TYPE_CHECKING:
    from .._base_client import AsyncAPIClient, SyncAPIClient


class AccountContext:
    """특정 계정에 바인딩된 리소스 컨텍스트.

    ``client.accounts("AC_other")`` 로 생성되며,
    해당 계정의 리소스에 접근할 수 있습니다.

    Example::

        other = client.accounts("AC_other_id")
        other.calls.list()
        other.numbers.create(source="sip", number="1001")
    """

    def __init__(self, client: SyncAPIClient, account_id: str) -> None:
        self._client = client
        self._account_id = account_id

    @property
    def calls(self) -> Calls:
        """통화 리소스에 접근합니다."""
        return Calls(client=self._client, account_id=self._account_id)

    @property
    def numbers(self) -> Numbers:
        """번호 리소스에 접근합니다."""
        return Numbers(client=self._client, account_id=self._account_id)

    @property
    def sip(self) -> Sip:
        """SIP 리소스에 접근합니다."""
        return Sip(client=self._client, account_id=self._account_id)


class AsyncAccountContext:
    """비동기 계정 컨텍스트."""

    def __init__(self, client: AsyncAPIClient, account_id: str) -> None:
        self._client = client
        self._account_id = account_id

    @property
    def calls(self) -> AsyncCalls:
        return AsyncCalls(client=self._client, account_id=self._account_id)

    @property
    def numbers(self) -> AsyncNumbers:
        return AsyncNumbers(client=self._client, account_id=self._account_id)

    @property
    def sip(self) -> AsyncSip:
        return AsyncSip(client=self._client, account_id=self._account_id)
```

**Step 4: Implement Client classes**

```python
# src/clawops/_client.py
from __future__ import annotations

import os
from typing import Any

import httpx

from ._base_client import AsyncAPIClient, SyncAPIClient
from ._constants import DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT
from ._exceptions import ClawOpsError
from .resources.accounts import AccountContext, AsyncAccountContext
from .resources.calls import AsyncCalls, Calls
from .resources.numbers import AsyncNumbers, Numbers
from .resources.sip import AsyncSip, Sip
from .webhooks import Webhooks


class ClawOps(SyncAPIClient):
    """ClawOps Voice API의 동기 클라이언트.

    모든 API 리소스에 대한 진입점입니다.

    Example::

        from clawops import ClawOps

        client = ClawOps(
            api_key="sk_...",
            account_id="AC1a2b3c4d",
        )

        # 발신 전화 생성
        call = client.calls.create(
            to="01012345678",
            from_="07052358010",
            url="https://my-app.com/twiml",
        )

        # 다른 계정 접근
        other = client.accounts("AC_other")
        other.calls.list()

    Args:
        api_key: API 키 (sk_...). 생략 시 CLAWOPS_API_KEY 환경변수 사용.
        account_id: 기본 계정 ID (AC...). 생략 시 CLAWOPS_ACCOUNT_ID 환경변수 사용.
        base_url: API 기본 URL. 기본값: https://api.claw-ops.com
        timeout: 요청 타임아웃 (초 또는 httpx.Timeout). 기본값: 600초.
        max_retries: 최대 재시도 횟수. 기본값: 2.
        http_client: 커스텀 httpx.Client 인스턴스.
        default_headers: 모든 요청에 포함할 기본 HTTP 헤더.
    """

    _default_account_id: str

    def __init__(
        self,
        *,
        api_key: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("CLAWOPS_API_KEY")
        if api_key is None:
            raise ClawOpsError(
                "api_key를 지정하거나 CLAWOPS_API_KEY 환경변수를 설정하세요."
            )

        if account_id is None:
            account_id = os.environ.get("CLAWOPS_ACCOUNT_ID")
        if account_id is None:
            raise ClawOpsError(
                "account_id를 지정하거나 CLAWOPS_ACCOUNT_ID 환경변수를 설정하세요."
            )

        if base_url is None:
            base_url = os.environ.get("CLAWOPS_BASE_URL", DEFAULT_BASE_URL)

        self._default_account_id = account_id

        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            default_headers=default_headers,
        )

    @property
    def calls(self) -> Calls:
        """통화(Calls) 리소스에 접근합니다."""
        return Calls(client=self, account_id=self._default_account_id)

    @property
    def numbers(self) -> Numbers:
        """전화번호(Numbers) 리소스에 접근합니다."""
        return Numbers(client=self, account_id=self._default_account_id)

    @property
    def sip(self) -> Sip:
        """SIP 리소스에 접근합니다."""
        return Sip(client=self, account_id=self._default_account_id)

    @property
    def webhooks(self) -> Webhooks:
        """Webhook 서명 검증 유틸리티에 접근합니다."""
        return Webhooks()

    def accounts(self, account_id: str) -> AccountContext:
        """다른 계정의 리소스에 접근합니다.

        Args:
            account_id: 접근할 계정 ID.

        Returns:
            해당 계정에 바인딩된 AccountContext 객체.

        Example::

            other = client.accounts("AC_other_id")
            other.calls.list()
        """
        return AccountContext(client=self, account_id=account_id)


class AsyncClawOps(AsyncAPIClient):
    """ClawOps Voice API의 비동기 클라이언트.

    ClawOps의 async 버전입니다. 모든 리소스 메서드가 async/await를 사용합니다.

    Example::

        from clawops import AsyncClawOps

        async with AsyncClawOps(api_key="sk_...", account_id="AC...") as client:
            call = await client.calls.create(
                to="01012345678",
                from_="07052358010",
                url="https://my-app.com/twiml",
            )

    Args:
        api_key: API 키. 생략 시 CLAWOPS_API_KEY 환경변수 사용.
        account_id: 기본 계정 ID. 생략 시 CLAWOPS_ACCOUNT_ID 환경변수 사용.
        base_url: API 기본 URL.
        timeout: 요청 타임아웃.
        max_retries: 최대 재시도 횟수.
        http_client: 커스텀 httpx.AsyncClient 인스턴스.
        default_headers: 기본 HTTP 헤더.
    """

    _default_account_id: str

    def __init__(
        self,
        *,
        api_key: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.AsyncClient | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("CLAWOPS_API_KEY")
        if api_key is None:
            raise ClawOpsError(
                "api_key를 지정하거나 CLAWOPS_API_KEY 환경변수를 설정하세요."
            )

        if account_id is None:
            account_id = os.environ.get("CLAWOPS_ACCOUNT_ID")
        if account_id is None:
            raise ClawOpsError(
                "account_id를 지정하거나 CLAWOPS_ACCOUNT_ID 환경변수를 설정하세요."
            )

        if base_url is None:
            base_url = os.environ.get("CLAWOPS_BASE_URL", DEFAULT_BASE_URL)

        self._default_account_id = account_id

        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            default_headers=default_headers,
        )

    @property
    def calls(self) -> AsyncCalls:
        """통화(Calls) 비동기 리소스에 접근합니다."""
        return AsyncCalls(client=self, account_id=self._default_account_id)

    @property
    def numbers(self) -> AsyncNumbers:
        """전화번호(Numbers) 비동기 리소스에 접근합니다."""
        return AsyncNumbers(client=self, account_id=self._default_account_id)

    @property
    def sip(self) -> AsyncSip:
        """SIP 비동기 리소스에 접근합니다."""
        return AsyncSip(client=self, account_id=self._default_account_id)

    @property
    def webhooks(self) -> Webhooks:
        """Webhook 서명 검증 유틸리티에 접근합니다."""
        return Webhooks()

    def accounts(self, account_id: str) -> AsyncAccountContext:
        """다른 계정의 비동기 리소스에 접근합니다.

        Args:
            account_id: 접근할 계정 ID.

        Returns:
            해당 계정에 바인딩된 AsyncAccountContext 객체.
        """
        return AsyncAccountContext(client=self, account_id=account_id)
```

**Step 5: Run tests**

Run: `pytest tests/test_client.py -v`
Expected: All passed

**Step 6: Commit**

```bash
git add src/clawops/_client.py src/clawops/resources/accounts.py tests/test_client.py
git commit -m "feat: add ClawOps and AsyncClawOps client classes with Twilio-style accounts"
```

---

### Task 14: Webhook Signature Verification

**Files:**
- Create: `src/clawops/webhooks.py`
- Test: `tests/test_webhooks.py`

**Step 1: Write tests**

```python
# tests/test_webhooks.py
import base64
import hashlib
import hmac

import pytest

from clawops.webhooks import Webhooks, WebhookVerificationError


@pytest.fixture
def webhooks():
    return Webhooks()


def _compute_signature(url: str, params: dict[str, str], signing_key: str) -> str:
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    data_to_sign = url + sorted_params
    digest = hmac.new(
        signing_key.encode("utf-8"),
        data_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def test_verify_valid_signature(webhooks):
    url = "https://my-app.com/webhook"
    params = {"CallId": "CA123", "CallStatus": "completed"}
    signing_key = "test_signing_key_1234"
    signature = _compute_signature(url, params, signing_key)

    result = webhooks.verify(
        url=url, params=params, signature=signature, signing_key=signing_key,
    )
    assert result is True


def test_verify_invalid_signature(webhooks):
    url = "https://my-app.com/webhook"
    params = {"CallId": "CA123", "CallStatus": "completed"}
    signing_key = "test_signing_key_1234"

    with pytest.raises(WebhookVerificationError, match="서명이 일치하지 않습니다"):
        webhooks.verify(
            url=url, params=params, signature="invalid_signature", signing_key=signing_key,
        )


def test_verify_tampered_params(webhooks):
    url = "https://my-app.com/webhook"
    original_params = {"CallId": "CA123", "CallStatus": "completed"}
    signing_key = "test_signing_key_1234"
    signature = _compute_signature(url, original_params, signing_key)

    tampered_params = {"CallId": "CA999", "CallStatus": "completed"}
    with pytest.raises(WebhookVerificationError):
        webhooks.verify(
            url=url, params=tampered_params, signature=signature, signing_key=signing_key,
        )


def test_verify_empty_params(webhooks):
    url = "https://my-app.com/webhook"
    params: dict[str, str] = {}
    signing_key = "test_key"
    signature = _compute_signature(url, params, signing_key)

    result = webhooks.verify(
        url=url, params=params, signature=signature, signing_key=signing_key,
    )
    assert result is True
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_webhooks.py -v`
Expected: FAIL

**Step 3: Implement webhooks**

```python
# src/clawops/webhooks.py
from __future__ import annotations

import base64
import hashlib
import hmac

from ._exceptions import ClawOpsError


class WebhookVerificationError(ClawOpsError):
    """Webhook 서명 검증 실패."""


class Webhooks:
    """ClawOps webhook 서명 검증 유틸리티.

    ClawOps는 webhook 요청 시 X-Signature 헤더에
    HMAC-SHA1 서명을 포함합니다. 이 클래스를 사용하여
    요청의 무결성을 검증할 수 있습니다.

    Example::

        from clawops import ClawOps

        client = ClawOps(api_key="sk_...", account_id="AC...")

        # Flask 예시
        @app.route("/webhook", methods=["POST"])
        def webhook():
            signature = request.headers["X-Signature"]
            client.webhooks.verify(
                url="https://my-app.com/webhook",
                params=request.form.to_dict(),
                signature=signature,
                signing_key="your_signing_key",
            )
            # 검증 통과 -- 안전하게 처리
    """

    def verify(
        self,
        *,
        url: str,
        params: dict[str, str],
        signature: str,
        signing_key: str,
    ) -> bool:
        """Webhook 요청의 서명을 검증합니다.

        ClawOps 서명 알고리즘:
        1. URL + 파라미터(키 알파벳순 정렬)를 연결
        2. HMAC-SHA1으로 서명
        3. Base64로 인코딩

        Args:
            url: 원본 webhook URL (등록 시 설정한 URL과 동일해야 합니다).
            params: POST body 파라미터 (key-value 딕셔너리).
            signature: X-Signature 헤더 값.
            signing_key: 계정의 signing key.

        Returns:
            True (검증 성공 시).

        Raises:
            WebhookVerificationError: 서명이 일치하지 않을 때.
        """
        expected = self._compute_signature(url, params, signing_key)
        if not hmac.compare_digest(expected, signature):
            raise WebhookVerificationError(
                "Webhook 서명이 일치하지 않습니다."
            )
        return True

    @staticmethod
    def _compute_signature(
        url: str,
        params: dict[str, str],
        signing_key: str,
    ) -> str:
        sorted_params = "".join(
            f"{k}{v}" for k, v in sorted(params.items())
        )
        data_to_sign = url + sorted_params
        digest = hmac.new(
            signing_key.encode("utf-8"),
            data_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")
```

**Step 4: Run tests**

Run: `pytest tests/test_webhooks.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/clawops/webhooks.py tests/test_webhooks.py
git commit -m "feat: add webhook signature verification utility"
```

---

### Task 15: Package Exports (__init__.py)

**Files:**
- Modify: `src/clawops/__init__.py`

**Step 1: Update __init__.py**

```python
# src/clawops/__init__.py
"""ClawOps Voice API의 공식 Python SDK.

Example::

    from clawops import ClawOps

    client = ClawOps(
        api_key="sk_...",
        account_id="AC1a2b3c4d",
    )

    # 발신 전화 생성
    call = client.calls.create(
        to="01012345678",
        from_="07052358010",
        url="https://my-app.com/twiml",
    )
    print(call.call_id)

    # 번호 목록 조회
    numbers = client.numbers.list()

    # 다른 계정 접근
    other = client.accounts("AC_other")
    other.calls.list()
"""

from ._client import AsyncClawOps, ClawOps
from ._exceptions import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ClawOpsError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from ._version import __version__
from .webhooks import WebhookVerificationError

__all__ = [
    # Clients
    "ClawOps",
    "AsyncClawOps",
    # Errors
    "ClawOpsError",
    "APIError",
    "APIStatusError",
    "APIConnectionError",
    "APITimeoutError",
    "APIResponseValidationError",
    "BadRequestError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "UnprocessableEntityError",
    "InternalServerError",
    "ServiceUnavailableError",
    "WebhookVerificationError",
    # Version
    "__version__",
]

# Rewrite __module__ so errors show as "clawops.NotFoundError" not "clawops._exceptions.NotFoundError"
_locals = locals()
for _name in __all__:
    if not _name.startswith("__"):
        try:
            _locals[_name].__module__ = "clawops"
        except (TypeError, AttributeError):
            pass
```

**Step 2: Run all tests**

Run: `pytest -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add src/clawops/__init__.py
git commit -m "feat: finalize package exports with all clients, errors, and types"
```

---

### Task 16: Update resources/__init__.py

**Files:**
- Modify: `src/clawops/resources/__init__.py`

**Step 1: Update exports**

```python
# src/clawops/resources/__init__.py
from .accounts import AccountContext, AsyncAccountContext
from .calls import AsyncCalls, Calls
from .numbers import AsyncNumbers, Numbers
from .sip import AsyncSip, AsyncSipCredentials, Sip, SipCredentials

__all__ = [
    "AccountContext",
    "AsyncAccountContext",
    "AsyncCalls",
    "AsyncNumbers",
    "AsyncSip",
    "AsyncSipCredentials",
    "Calls",
    "Numbers",
    "Sip",
    "SipCredentials",
]
```

**Step 2: Commit**

```bash
git add src/clawops/resources/__init__.py
git commit -m "chore: update resources exports"
```

---

### Task 17: Full Integration Test

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write end-to-end integration tests**

```python
# tests/test_integration.py
"""End-to-end integration tests using mocked HTTP responses.

Tests the full SDK usage pattern from client initialization through resource operations.
"""
import httpx
import pytest
import respx

from clawops import ClawOps, AsyncClawOps, NotFoundError, AuthenticationError


BASE = "https://api.claw-ops.com"
ACCOUNT = "AC1a2b3c4d"


CALL_RESPONSE = {
    "callId": "CA0123456789abcdef0123456789abcdef",
    "status": "queued",
    "to": "01012345678",
    "from": "07052358010",
    "direction": "outbound",
    "duration": None,
    "accountId": ACCOUNT,
    "dateCreated": "2025-06-01T12:00:00Z",
    "dateUpdated": None,
}


class TestSyncIntegration:
    """동기 클라이언트 통합 테스트."""

    @respx.mock
    def test_full_call_lifecycle(self):
        """발신 -> 조회 -> 종료 전체 생명주기 테스트."""
        call_id = CALL_RESPONSE["callId"]

        # 1. 발신
        respx.post(f"{BASE}/v1/accounts/{ACCOUNT}/calls").mock(
            return_value=httpx.Response(201, json=CALL_RESPONSE)
        )
        # 2. 조회
        respx.get(f"{BASE}/v1/accounts/{ACCOUNT}/calls/{call_id}").mock(
            return_value=httpx.Response(200, json={**CALL_RESPONSE, "status": "in-progress"})
        )
        # 3. 종료
        respx.post(f"{BASE}/v1/accounts/{ACCOUNT}/calls/{call_id}").mock(
            return_value=httpx.Response(200, json={"callId": call_id, "status": "completed"})
        )

        with ClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            # 발신
            call = client.calls.create(
                to="01012345678",
                from_="07052358010",
                url="https://my-app.com/twiml",
                status_callback="https://my-app.com/status",
            )
            assert call.status == "queued"
            assert call.from_ == "07052358010"

            # 조회
            fetched = client.calls.get(call_id)
            assert fetched.status == "in-progress"

            # 종료
            result = client.calls.update(call_id, status="completed")
            assert result.status == "completed"

    @respx.mock
    def test_full_number_lifecycle(self):
        """번호 등록 -> 목록 -> 수정 -> 삭제 생명주기 테스트."""
        # 1. 등록
        respx.post(f"{BASE}/v1/accounts/{ACCOUNT}/numbers").mock(
            return_value=httpx.Response(201, json={"number": "1001", "source": "sip"})
        )
        # 2. 목록
        respx.get(f"{BASE}/v1/accounts/{ACCOUNT}/numbers").mock(
            return_value=httpx.Response(200, json={
                "numbers": [{"number": "1001", "source": "sip", "webhookUrl": None, "createdAt": "2025-06-01T12:00:00Z"}]
            })
        )
        # 3. 수정
        respx.put(f"{BASE}/v1/accounts/{ACCOUNT}/numbers/1001").mock(
            return_value=httpx.Response(200, json={
                "number": "1001", "source": "sip", "webhookUrl": "https://new.com", "webhookMethod": "POST"
            })
        )
        # 4. 삭제
        respx.delete(f"{BASE}/v1/accounts/{ACCOUNT}/numbers/1001").mock(
            return_value=httpx.Response(204)
        )

        with ClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            num = client.numbers.create(source="sip", number="1001")
            assert num.number == "1001"

            nums = client.numbers.list()
            assert len(nums) == 1

            updated = client.numbers.update("1001", webhook_url="https://new.com")
            assert updated.webhook_url == "https://new.com"

            client.numbers.delete("1001")

    @respx.mock
    def test_full_sip_credential_lifecycle(self):
        """SIP credential 생성 -> 목록 -> 조회 -> 삭제 테스트."""
        cred_id = "clu1abc2def3ghi"
        cred_json = {
            "id": cred_id, "username": "usr_aBcDeFgHiJkL",
            "password": "secret123", "displayName": "Office",
            "sipServer": "sip.claw-ops.com", "sipPort": 5060,
            "transport": "UDP", "createdAt": "2025-06-01T12:00:00Z",
        }

        respx.post(f"{BASE}/v1/accounts/{ACCOUNT}/sip/credentials").mock(
            return_value=httpx.Response(201, json=cred_json)
        )
        respx.get(f"{BASE}/v1/accounts/{ACCOUNT}/sip/credentials").mock(
            return_value=httpx.Response(200, json={
                "credentials": [{"id": cred_id, "username": "usr_aBcDeFgHiJkL", "displayName": "Office", "createdAt": "2025-06-01T12:00:00Z"}]
            })
        )
        respx.get(f"{BASE}/v1/accounts/{ACCOUNT}/sip/credentials/{cred_id}").mock(
            return_value=httpx.Response(200, json={
                "id": cred_id, "username": "usr_aBcDeFgHiJkL", "displayName": "Office", "createdAt": "2025-06-01T12:00:00Z"
            })
        )
        respx.delete(f"{BASE}/v1/accounts/{ACCOUNT}/sip/credentials/{cred_id}").mock(
            return_value=httpx.Response(204)
        )

        with ClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            cred = client.sip.credentials.create(display_name="Office")
            assert cred.password == "secret123"

            creds = client.sip.credentials.list()
            assert len(creds) == 1

            fetched = client.sip.credentials.get(cred_id)
            assert fetched.username == "usr_aBcDeFgHiJkL"

            client.sip.credentials.delete(cred_id)

    @respx.mock
    def test_multi_account_access(self):
        """Twilio 스타일 multi-account 접근 테스트."""
        other_account = "AC_other"

        respx.get(f"{BASE}/v1/accounts/{other_account}/numbers").mock(
            return_value=httpx.Response(200, json={"numbers": []})
        )

        with ClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            other = client.accounts(other_account)
            nums = other.numbers.list()
            assert nums == []

    @respx.mock
    def test_error_handling(self):
        """에러 응답 시 적절한 예외가 발생하는지 테스트."""
        respx.get(f"{BASE}/v1/accounts/{ACCOUNT}/calls/CA_invalid").mock(
            return_value=httpx.Response(404, json={"error": "콜을 찾을 수 없습니다"})
        )

        with ClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.calls.get("CA_invalid")
            assert exc_info.value.status_code == 404
            assert "찾을 수 없습니다" in str(exc_info.value)

    def test_webhook_verification(self):
        """Webhook 서명 검증 테스트."""
        with ClawOps(api_key="sk_test", account_id=ACCOUNT) as client:
            import base64, hashlib, hmac

            url = "https://my-app.com/webhook"
            params = {"CallId": "CA123", "CallStatus": "completed"}
            signing_key = "sk_sign_test"

            sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
            data = url + sorted_params
            sig = base64.b64encode(
                hmac.new(signing_key.encode(), data.encode(), hashlib.sha1).digest()
            ).decode()

            result = client.webhooks.verify(
                url=url, params=params, signature=sig, signing_key=signing_key,
            )
            assert result is True


class TestAsyncIntegration:
    """비동기 클라이언트 통합 테스트."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_call_create(self):
        respx.post(f"{BASE}/v1/accounts/{ACCOUNT}/calls").mock(
            return_value=httpx.Response(201, json=CALL_RESPONSE)
        )

        async with AsyncClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            call = await client.calls.create(
                to="01012345678", from_="07052358010", url="https://twiml.com",
            )
            assert call.call_id == CALL_RESPONSE["callId"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_multi_account(self):
        respx.get(f"{BASE}/v1/accounts/AC_other/numbers").mock(
            return_value=httpx.Response(200, json={"numbers": []})
        )

        async with AsyncClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            other = client.accounts("AC_other")
            nums = await other.numbers.list()
            assert nums == []
```

**Step 2: Run all tests**

Run: `pytest -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add full integration tests for all resources and error handling"
```

---

### Task 18: Final Verification

**Step 1: Run full test suite**

Run: `pytest -v --tb=short`
Expected: All tests pass

**Step 2: Type check**

Run: `mypy src/clawops/ --ignore-missing-imports`
Expected: No errors (or acceptable warnings)

**Step 3: Lint**

Run: `ruff check src/clawops/`
Expected: No errors

**Step 4: Verify package installs**

Run: `pip install -e . && python -c "from clawops import ClawOps; print('OK')"`
Expected: `OK`

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: finalize ClawOps Python SDK v0.1.0"
```
