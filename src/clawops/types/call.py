from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from .._models import BaseModel


class Call(BaseModel):
    """통화 정보를 나타내는 모델.

    아웃바운드 전화 발신 후 반환되거나, 통화 목록/단건 조회 시 반환됩니다.

    Attributes:
        call_id: 통화 고유 식별자 (예: 'CAabcdef1234567890').
        status: 통화 상태. queued, ringing, in-progress, completed, failed 중 하나.
        to: 수신 전화번호 또는 SIP URI.
        from_: 발신 전화번호 (계정에 등록된 번호).
        direction: 통화 방향. outbound 또는 inbound.
        duration: 통화 시간 (초). 통화 중이거나 미연결인 경우 None.
        account_id: 계정 ID.
        date_created: 통화 생성 시각.
        date_updated: 통화 종료 시각. 종료 전이면 None.
    """

    call_id: str
    status: Literal["queued", "ringing", "in-progress", "completed", "failed"]
    to: str
    from_: str
    direction: Literal["outbound", "inbound"]
    duration: Optional[int] = None
    account_id: str
    date_created: datetime
    date_updated: Optional[datetime] = None


class CallControlResponse(BaseModel):
    """통화 제어 (종료) 응답.

    Attributes:
        call_id: 제어된 통화의 ID.
        status: 변경된 상태 (현재 'completed'만 지원).
    """

    call_id: str
    status: str
