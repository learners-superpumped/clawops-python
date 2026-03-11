from __future__ import annotations

from typing import Literal

from .._resource import AsyncAPIResource, SyncAPIResource
from .._utils import strip_not_given
from ..pagination import AsyncPage, SyncPage
from ..types.message import Message


class Messages(SyncAPIResource):
    """메시지(Messages) 리소스. 메시지 발송, 목록 조회, 단건 조회."""

    def create(
        self,
        *,
        to: str,
        from_: str,
        body: str,
        type: Literal["sms", "mms", "rcs", "kakao"] | None = None,
        subject: str | None = None,
        media_url: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> Message:
        """메시지를 발송합니다.

        Args:
            to: 수신 번호.
            from_: 발신 번호. 계정에 등록된 번호여야 합니다.
            body: 메시지 본문.
            type: 메시지 유형. sms, mms, rcs, kakao. 기본값 sms.
            subject: 제목 (MMS 등에서 사용).
            media_url: 첨부 미디어 URL 목록 (MMS 등에서 사용).
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            생성된 Message 객체.
        """
        req_body = strip_not_given({
            "To": to, "From": from_, "Body": body,
            "Type": type, "Subject": subject, "MediaUrl": media_url,
        })
        return self._client._post(
            f"{self._base_path}/messages", body=req_body, cast_to=Message,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    def list(
        self,
        *,
        type: Literal["sms", "mms", "rcs", "kakao"] | None = None,
        status: Literal["queued", "sending", "sent", "failed", "received"] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> SyncPage[Message]:
        """메시지 목록을 조회합니다.

        Args:
            type: 메시지 유형으로 필터링.
            status: 메시지 상태로 필터링.
            page: 페이지 번호 (0부터 시작, 기본값 0).
            page_size: 페이지당 항목 수 (기본 20, 최대 100).
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            Message 객체의 페이지.
        """
        query = strip_not_given({"type": type, "status": status, "page": page, "pageSize": page_size})
        path = f"{self._base_path}/messages"
        result = self._client._get(
            path, cast_to=SyncPage[Message], query=query if query else None,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        result.data = [Message.model_validate(item) if isinstance(item, dict) else item for item in result.data]
        result._set_client(client=self._client, path=path, cast_to=Message, query=query)
        return result

    def get(
        self,
        message_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
        extra_query: dict[str, object] | None = None,
        timeout: float | None = None,
    ) -> Message:
        """특정 메시지의 상세 정보를 조회합니다.

        Args:
            message_id: 메시지 ID (예: 'MG0123456789abcdef...').
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            Message 객체.
        """
        return self._client._get(
            f"{self._base_path}/messages/{message_id}", cast_to=Message,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )


class AsyncMessages(AsyncAPIResource):
    """메시지(Messages) 비동기 리소스. Messages의 async 버전."""

    async def create(self, *, to: str, from_: str, body: str,
                     type: Literal["sms", "mms", "rcs", "kakao"] | None = None,
                     subject: str | None = None,
                     media_url: list[str] | None = None,
                     extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                     timeout: float | None = None) -> Message:
        """메시지를 비동기로 발송합니다. 자세한 내용은 Messages.create를 참고하세요."""
        req_body = strip_not_given({
            "To": to, "From": from_, "Body": body,
            "Type": type, "Subject": subject, "MediaUrl": media_url,
        })
        return await self._client._post(
            f"{self._base_path}/messages", body=req_body, cast_to=Message,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    async def list(self, *, type: Literal["sms", "mms", "rcs", "kakao"] | None = None,
                   status: Literal["queued", "sending", "sent", "failed", "received"] | None = None,
                   page: int | None = None, page_size: int | None = None,
                   extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                   timeout: float | None = None) -> AsyncPage[Message]:
        """메시지 목록을 비동기로 조회합니다."""
        query = strip_not_given({"type": type, "status": status, "page": page, "pageSize": page_size})
        path = f"{self._base_path}/messages"
        result = await self._client._get(
            path, cast_to=AsyncPage[Message], query=query if query else None,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        result.data = [Message.model_validate(item) if isinstance(item, dict) else item for item in result.data]
        result._set_client(client=self._client, path=path, cast_to=Message, query=query)
        return result

    async def get(self, message_id: str, *, extra_headers: dict[str, str] | None = None,
                  extra_query: dict[str, object] | None = None, timeout: float | None = None) -> Message:
        """특정 메시지를 비동기로 조회합니다."""
        return await self._client._get(
            f"{self._base_path}/messages/{message_id}", cast_to=Message,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
