from __future__ import annotations

from typing import Literal

from .._resource import AsyncAPIResource, SyncAPIResource
from .._utils import strip_not_given
from ..pagination import AsyncPage, SyncPage
from ..types.call import Call, CallControlResponse


class Calls(SyncAPIResource):
    """통화(Calls) 리소스. 아웃바운드 전화 발신, 통화 목록 조회, 단건 조회, 통화 제어(종료)."""

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

        PSTN 번호로 아웃바운드 전화를 발신합니다.
        From 번호는 계정에 등록된 번호여야 합니다.

        - 예: ``to="01012345678"``

        Args:
            to: 수신 전화번호.
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
            "To": to, "From": from_, "Url": url,
            "StatusCallback": status_callback,
            "StatusCallbackEvent": status_callback_event,
        })
        return self._client._post(
            f"{self._base_path}/calls", body=body, cast_to=Call,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
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
        query = strip_not_given({"status": status, "page": page, "pageSize": page_size})
        path = f"{self._base_path}/calls"
        result = self._client._get(
            path, cast_to=SyncPage[Call], query=query if query else None,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        result.data = [Call.model_validate(item) if isinstance(item, dict) else item for item in result.data]
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
            f"{self._base_path}/calls/{call_id}", cast_to=Call,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
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
        """
        return self._client._post(
            f"{self._base_path}/calls/{call_id}", body={"Status": status}, cast_to=CallControlResponse,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )


class AsyncCalls(AsyncAPIResource):
    """통화(Calls) 비동기 리소스. Calls의 async 버전."""

    async def create(self, *, to: str, from_: str, url: str,
                     status_callback: str | None = None, status_callback_event: str | None = None,
                     extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                     timeout: float | None = None) -> Call:
        """발신 전화를 비동기로 생성합니다. 자세한 내용은 Calls.create를 참고하세요."""
        body = strip_not_given({
            "To": to, "From": from_, "Url": url,
            "StatusCallback": status_callback, "StatusCallbackEvent": status_callback_event,
        })
        return await self._client._post(
            f"{self._base_path}/calls", body=body, cast_to=Call,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    async def list(self, *, status: Literal["queued", "ringing", "in-progress", "completed", "failed"] | None = None,
                   page: int | None = None, page_size: int | None = None,
                   extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                   timeout: float | None = None) -> AsyncPage[Call]:
        """통화 목록을 비동기로 조회합니다."""
        query = strip_not_given({"status": status, "page": page, "pageSize": page_size})
        path = f"{self._base_path}/calls"
        result = await self._client._get(
            path, cast_to=AsyncPage[Call], query=query if query else None,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        result.data = [Call.model_validate(item) if isinstance(item, dict) else item for item in result.data]
        result._set_client(client=self._client, path=path, cast_to=Call, query=query)
        return result

    async def get(self, call_id: str, *, extra_headers: dict[str, str] | None = None,
                  extra_query: dict[str, object] | None = None, timeout: float | None = None) -> Call:
        """특정 통화를 비동기로 조회합니다."""
        return await self._client._get(
            f"{self._base_path}/calls/{call_id}", cast_to=Call,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    async def update(self, call_id: str, *, status: Literal["completed"] = "completed",
                     extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                     timeout: float | None = None) -> CallControlResponse:
        """진행 중인 통화를 비동기로 종료합니다."""
        return await self._client._post(
            f"{self._base_path}/calls/{call_id}", body={"Status": status}, cast_to=CallControlResponse,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
