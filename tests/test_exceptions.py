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
    response = httpx.Response(404, json={"error": "not found"}, request=request)
    err = NotFoundError(message="not found", response=response, body={"error": "not found"})
    assert err.status_code == 404
    assert err.body == {"error": "not found"}
    assert err.response is response
    assert err.request is request
    assert "not found" in str(err)


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
        assert isinstance(err, expected_cls), f"Expected {expected_cls} for {status_code}"


def test_api_connection_error():
    request = httpx.Request("GET", "https://api.claw-ops.com/test")
    err = APIConnectionError(message="Connection refused", request=request)
    assert "Connection refused" in str(err)


def test_api_timeout_error():
    request = httpx.Request("GET", "https://api.claw-ops.com/test")
    err = APITimeoutError(request=request)
    assert isinstance(err, APIConnectionError)
