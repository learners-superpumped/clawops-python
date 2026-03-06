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
    """HTTP 상태 코드 에러 (4xx/5xx)."""

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
    """HTTP 401 Unauthorized."""
    status_code: int = 401


class PermissionDeniedError(APIStatusError):
    """HTTP 403 Forbidden."""
    status_code: int = 403


class NotFoundError(APIStatusError):
    """HTTP 404 Not Found."""
    status_code: int = 404


class ConflictError(APIStatusError):
    """HTTP 409 Conflict."""
    status_code: int = 409


class UnprocessableEntityError(APIStatusError):
    """HTTP 422 Unprocessable Entity."""
    status_code: int = 422


class InternalServerError(APIStatusError):
    """HTTP 500+ Internal Server Error."""
    status_code: int = 500


class ServiceUnavailableError(APIStatusError):
    """HTTP 503 Service Unavailable."""
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


class AgentError(ClawOpsError):
    """Agent 관련 에러의 베이스 클래스."""


class AgentConnectionError(AgentError):
    """Agent WebSocket 연결 실패."""
