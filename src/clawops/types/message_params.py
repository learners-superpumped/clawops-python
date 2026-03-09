from __future__ import annotations

from typing import Annotated, Literal

from typing_extensions import Required, TypedDict

from .._utils import PropertyInfo


class MessageCreateParams(TypedDict, total=False):
    """메시지 발송 요청 파라미터."""

    to: Required[Annotated[str, PropertyInfo(alias="To")]]
    """수신 번호."""

    from_: Required[Annotated[str, PropertyInfo(alias="From")]]
    """발신 번호. 계정에 등록된 번호여야 합니다."""

    body: Required[Annotated[str, PropertyInfo(alias="Body")]]
    """메시지 본문."""

    type: Annotated[Literal["sms", "mms", "rcs", "kakao"], PropertyInfo(alias="Type")]
    """메시지 유형. 기본값 sms."""

    subject: Annotated[str, PropertyInfo(alias="Subject")]
    """제목 (MMS 등에서 사용)."""


class MessageListParams(TypedDict, total=False):
    """메시지 목록 조회 요청 파라미터."""

    type: Literal["sms", "mms", "rcs", "kakao"]
    """메시지 유형으로 필터링."""

    status: Literal["queued", "sending", "sent", "failed", "received"]
    """메시지 상태로 필터링."""

    page: int
    """페이지 번호 (0부터 시작)."""

    page_size: Annotated[int, PropertyInfo(alias="pageSize")]
    """페이지당 항목 수 (기본 20, 최대 100)."""
