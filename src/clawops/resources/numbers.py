from __future__ import annotations

from typing import Literal

from .._resource import AsyncAPIResource, SyncAPIResource
from .._utils import strip_not_given
from ..types.number import NumberListItem, NumberUpdateResponse, PhoneNumber


class Numbers(SyncAPIResource):
    """전화번호(Numbers) 리소스."""

    def create(self, *, webhook_url: str | None = None, extra_headers: dict[str, str] | None = None,
               extra_query: dict[str, object] | None = None, timeout: float | None = None) -> PhoneNumber:
        """PSTN 번호를 발급합니다.

        번호 풀에서 자동으로 번호를 발급합니다.

        Args:
            webhook_url: 수신 전화 처리용 Webhook URL.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            등록된 PhoneNumber 객체.

        Raises:
            UnprocessableEntityError: 번호 할당량 초과.
            ServiceUnavailableError: 발급 가능한 번호 없음.
        """
        body = strip_not_given({"webhookUrl": webhook_url})
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
            data: list[NumberListItem]

        result = self._client._get(
            f"{self._base_path}/numbers", cast_to=_NumbersResponse,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        return result.data

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
        """등록된 번호를 삭제합니다. 번호는 풀로 복귀됩니다.

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

    async def create(self, *, webhook_url: str | None = None, extra_headers: dict[str, str] | None = None,
                     extra_query: dict[str, object] | None = None, timeout: float | None = None) -> PhoneNumber:
        """번호를 비동기로 발급합니다."""
        body = strip_not_given({"webhookUrl": webhook_url})
        return await self._client._post(
            f"{self._base_path}/numbers", body=body if body else None, cast_to=PhoneNumber,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    async def list(self, *, extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                   timeout: float | None = None) -> list[NumberListItem]:
        """번호 목록을 비동기로 조회합니다."""
        from .._models import BaseModel

        class _NumbersResponse(BaseModel):
            data: list[NumberListItem]

        result = await self._client._get(
            f"{self._base_path}/numbers", cast_to=_NumbersResponse,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        return result.data

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
