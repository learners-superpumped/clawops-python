from __future__ import annotations

from typing import Literal

from .._resource import AsyncAPIResource, SyncAPIResource
from .._utils import strip_not_given
from ..types.number import NumberListItem, NumberUpdateResponse, PhoneNumber


class Numbers(SyncAPIResource):
    """전화번호(Numbers) 리소스."""

    def create(self, *, source: Literal["pool", "sip"] | None = None, number: str | None = None,
               webhook_url: str | None = None, extra_headers: dict[str, str] | None = None,
               extra_query: dict[str, object] | None = None, timeout: float | None = None) -> PhoneNumber:
        """번호를 등록합니다.

        PSTN 번호 풀에서 자동 발급하거나, SIP 내선번호를 직접 등록합니다.
        source를 생략하거나 'pool'로 지정하면 번호 풀에서 자동 발급됩니다.
        'sip'으로 지정하면 number 파라미터에 원하는 번호를 직접 지정합니다.
        SIP 번호는 통신사 번호 형식(010, 070, 02 등)을 사용할 수 없습니다.

        Args:
            source: 'pool'=PSTN 풀 발급 (기본값), 'sip'=SIP 내선번호.
            number: SIP 내선번호 (source='sip'일 때 필수, 3~20자리).
            webhook_url: 수신 전화 처리용 Webhook URL.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            등록된 PhoneNumber 객체.

        Raises:
            BadRequestError: 번호 형식 오류, 통신사 번호 형식 사용 등.
            ConflictError: 번호 중복.
            UnprocessableEntityError: 번호 할당량 초과.
            ServiceUnavailableError: 발급 가능한 번호 없음.
        """
        body = strip_not_given({"source": source, "number": number, "webhookUrl": webhook_url})
        return self._client._post(
            f"{self._base_path}/numbers", body=body if body else None, cast_to=PhoneNumber,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    def list(self, *, extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
             timeout: float | None = None) -> list[NumberListItem]:
        """등록된 번호 목록을 조회합니다.

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

        result = self._client._get(
            f"{self._base_path}/numbers", cast_to=_NumbersResponse,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        return result.numbers

    def update(self, number: str, *, webhook_url: str | None = None,
               webhook_method: Literal["POST", "GET"] | None = None,
               extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
               timeout: float | None = None) -> NumberUpdateResponse:
        """등록된 번호의 설정을 수정합니다. webhookUrl과 webhookMethod만 수정 가능합니다.

        Args:
            number: 수정할 전화번호.
            webhook_url: Webhook URL.
            webhook_method: 'POST' 또는 'GET'.
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
        body = strip_not_given({"webhookUrl": webhook_url, "webhookMethod": webhook_method})
        return self._client._put(
            f"{self._base_path}/numbers/{number}", body=body, cast_to=NumberUpdateResponse,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    def delete(self, number: str, *, extra_headers: dict[str, str] | None = None,
               timeout: float | None = None) -> None:
        """등록된 번호를 삭제합니다.

        PSTN 번호는 풀로 복귀, SIP 번호는 단순 삭제됩니다.

        Args:
            number: 삭제할 전화번호.
            extra_headers: 추가 HTTP 헤더.
            timeout: 이 요청의 타임아웃 (초).

        Raises:
            NotFoundError: 번호를 찾을 수 없음.
            PermissionDeniedError: 번호 소유권 없음.
            ServiceUnavailableError: 번호 반납 기능 사용 불가.
        """
        self._client._delete(f"{self._base_path}/numbers/{number}", extra_headers=extra_headers, timeout=timeout)


class AsyncNumbers(AsyncAPIResource):
    """전화번호(Numbers) 비동기 리소스."""

    async def create(self, *, source: Literal["pool", "sip"] | None = None, number: str | None = None,
                     webhook_url: str | None = None, extra_headers: dict[str, str] | None = None,
                     extra_query: dict[str, object] | None = None, timeout: float | None = None) -> PhoneNumber:
        """번호를 비동기로 등록합니다."""
        body = strip_not_given({"source": source, "number": number, "webhookUrl": webhook_url})
        return await self._client._post(
            f"{self._base_path}/numbers", body=body if body else None, cast_to=PhoneNumber,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    async def list(self, *, extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                   timeout: float | None = None) -> list[NumberListItem]:
        """번호 목록을 비동기로 조회합니다."""
        from .._models import BaseModel

        class _NumbersResponse(BaseModel):
            numbers: list[NumberListItem]

        result = await self._client._get(
            f"{self._base_path}/numbers", cast_to=_NumbersResponse,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        return result.numbers

    async def update(self, number: str, *, webhook_url: str | None = None,
                     webhook_method: Literal["POST", "GET"] | None = None,
                     extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                     timeout: float | None = None) -> NumberUpdateResponse:
        """번호 설정을 비동기로 수정합니다."""
        body = strip_not_given({"webhookUrl": webhook_url, "webhookMethod": webhook_method})
        return await self._client._put(
            f"{self._base_path}/numbers/{number}", body=body, cast_to=NumberUpdateResponse,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    async def delete(self, number: str, *, extra_headers: dict[str, str] | None = None,
                     timeout: float | None = None) -> None:
        """번호를 비동기로 삭제합니다."""
        await self._client._delete(f"{self._base_path}/numbers/{number}", extra_headers=extra_headers, timeout=timeout)
