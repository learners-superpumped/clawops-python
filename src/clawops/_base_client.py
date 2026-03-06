from __future__ import annotations

import time
from random import random
from typing import Any, TypeVar

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
    """동기 HTTP 클라이언트 베이스. httpx.Client를 래핑하며 인증, 재시도, 타임아웃, 에러 매핑을 처리합니다."""

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
                raise APITimeoutError(request=httpx.Request(method, self._base_url + path)) from e
            except httpx.ConnectError as e:
                if retries_left > 0:
                    retries_left -= 1
                    time.sleep(self._retry_delay(self._max_retries - retries_left))
                    continue
                raise APIConnectionError(request=httpx.Request(method, self._base_url + path)) from e

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

    def _get(self, path: str, *, cast_to: type[_T], query: dict[str, Any] | None = None,
             extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
             timeout: float | httpx.Timeout | None = None) -> _T:
        result = self._request("GET", path, cast_to=cast_to, query=query,
                               extra_headers=extra_headers, extra_query=extra_query, timeout=timeout)
        assert result is not None
        return result

    def _post(self, path: str, *, body: dict[str, Any] | None = None, cast_to: type[_T],
              extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
              timeout: float | httpx.Timeout | None = None) -> _T:
        result = self._request("POST", path, body=body, cast_to=cast_to,
                               extra_headers=extra_headers, extra_query=extra_query, timeout=timeout)
        assert result is not None
        return result

    def _put(self, path: str, *, body: dict[str, Any] | None = None, cast_to: type[_T],
             extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
             timeout: float | httpx.Timeout | None = None) -> _T:
        result = self._request("PUT", path, body=body, cast_to=cast_to,
                               extra_headers=extra_headers, extra_query=extra_query, timeout=timeout)
        assert result is not None
        return result

    def _delete(self, path: str, *, extra_headers: dict[str, str] | None = None,
                timeout: float | httpx.Timeout | None = None) -> None:
        self._request("DELETE", path, cast_to=None, extra_headers=extra_headers, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SyncAPIClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class AsyncAPIClient:
    """비동기 HTTP 클라이언트 베이스. SyncAPIClient의 async 버전."""

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
        import asyncio

        headers = self._build_headers(extra_headers)
        params = query.copy() if query else {}
        if extra_query:
            params.update(extra_query)

        req_timeout = timeout if timeout is not None else self._timeout
        if isinstance(req_timeout, (int, float)):
            req_timeout = httpx.Timeout(req_timeout)

        retries_left = self._max_retries

        while True:
            try:
                response = await self._client.request(
                    method=method, url=path, json=body,
                    params=params if params else None,
                    headers=headers, timeout=req_timeout,
                )
            except httpx.TimeoutException as e:
                if retries_left > 0:
                    retries_left -= 1
                    await asyncio.sleep(self._retry_delay(self._max_retries - retries_left))
                    continue
                raise APITimeoutError(request=httpx.Request(method, self._base_url + path)) from e
            except httpx.ConnectError as e:
                if retries_left > 0:
                    retries_left -= 1
                    await asyncio.sleep(self._retry_delay(self._max_retries - retries_left))
                    continue
                raise APIConnectionError(request=httpx.Request(method, self._base_url + path)) from e

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

    async def _get(self, path: str, *, cast_to: type[_T], query: dict[str, Any] | None = None,
                   extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                   timeout: float | httpx.Timeout | None = None) -> _T:
        result = await self._request("GET", path, cast_to=cast_to, query=query,
                                     extra_headers=extra_headers, extra_query=extra_query, timeout=timeout)
        assert result is not None
        return result

    async def _post(self, path: str, *, body: dict[str, Any] | None = None, cast_to: type[_T],
                    extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                    timeout: float | httpx.Timeout | None = None) -> _T:
        result = await self._request("POST", path, body=body, cast_to=cast_to,
                                     extra_headers=extra_headers, extra_query=extra_query, timeout=timeout)
        assert result is not None
        return result

    async def _put(self, path: str, *, body: dict[str, Any] | None = None, cast_to: type[_T],
                   extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                   timeout: float | httpx.Timeout | None = None) -> _T:
        result = await self._request("PUT", path, body=body, cast_to=cast_to,
                                     extra_headers=extra_headers, extra_query=extra_query, timeout=timeout)
        assert result is not None
        return result

    async def _delete(self, path: str, *, extra_headers: dict[str, str] | None = None,
                      timeout: float | httpx.Timeout | None = None) -> None:
        await self._request("DELETE", path, cast_to=None, extra_headers=extra_headers, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncAPIClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
