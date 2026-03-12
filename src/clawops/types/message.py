from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from .._models import BaseModel


class Message(BaseModel):
    """메시지 정보를 나타내는 모델.

    메시지 발송 후 반환되거나, 메시지 목록/단건 조회 시 반환됩니다.

    Attributes:
        message_id: 메시지 고유 식별자 (예: 'MG0123456789abcdef...').
        status: 메시지 상태.
        type: 메시지 유형. sms, lms, mms, rcs, kakao 중 하나.
        subject: 메시지 제목 (LMS/MMS 등에서 사용).
        to: 수신 번호.
        from_: 발신 번호.
        body: 메시지 본문.
        direction: 메시지 방향.
        account_id: 계정 ID.
        date_created: 생성 시각.
        date_updated: 수정 시각.
    """

    message_id: str
    status: Literal["queued", "sending", "sent", "failed", "received"]
    type: Literal["sms", "lms", "mms", "rcs", "kakao"]
    to: str
    from_: str
    subject: Optional[str] = None
    body: Optional[str] = None
    num_media: int = 0
    media_url: Optional[list[str]] = None
    direction: Literal["outbound", "inbound"]
    account_id: str
    date_created: datetime
    date_updated: Optional[datetime] = None
