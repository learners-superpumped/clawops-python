from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from .._models import BaseModel


class AssignmentLinkAssignment(BaseModel):
    """링크가 소비되어 발급된 번호 정보."""

    number: str
    name: Optional[str] = None
    consumed_at: datetime
    released_at: Optional[datetime] = None


class AssignmentLink(BaseModel):
    """관리번호 발급 링크 모델.

    Attributes:
        link_id: 링크 ID (생성 시 token과 동일).
        url: 엔드유저용 공개 URL.
        status: 'pending' | 'consumed' | 'expired' | 'revoked'.
        created_at: 생성 시각.
        expires_at: 만료 시각.
        consumed_at: 소비 시각 (consumed 상태일 때).
        webhook_url: 발급된 번호로 인입되는 통화/메시지를 받을 webhook URL.
        webhook_method: 'POST' | 'GET'.
        note: 내부 메모.
        assignment: consumed 상태일 때 발급된 번호 정보.
    """

    link_id: str
    url: str
    status: Literal["pending", "consumed", "expired", "revoked"]
    created_at: datetime
    expires_at: datetime
    consumed_at: Optional[datetime] = None
    webhook_url: Optional[str] = None
    webhook_method: Optional[Literal["POST", "GET"]] = None
    note: Optional[str] = None
    assignment: Optional[AssignmentLinkAssignment] = None


class AssignmentLinkCreateResponse(BaseModel):
    """링크 생성 응답."""

    token: str
    url: str
    expires_at: datetime
