from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from .._models import BaseModel


class PhoneNumber(BaseModel):
    """번호 등록 응답 모델.

    Attributes:
        number: 등록된 전화번호.
        source: 번호 유형. 'pool'은 PSTN 풀 발급, 'sip'은 SIP 내선번호.
    """

    number: str
    source: Literal["pool", "sip"]


class NumberListItem(BaseModel):
    """번호 목록 항목.

    Attributes:
        number: 전화번호.
        source: 번호 유형.
        webhook_url: Webhook URL. 미설정 시 None.
        created_at: 등록 시각.
    """

    number: str
    source: Literal["pool", "sip"]
    webhook_url: Optional[str] = None
    created_at: Optional[datetime] = None


class NumberUpdateResponse(BaseModel):
    """번호 설정 수정 응답.

    Attributes:
        number: 전화번호.
        source: 번호 유형.
        webhook_url: 수정된 Webhook URL.
        webhook_method: Webhook HTTP 메서드.
    """

    number: str
    source: Literal["pool", "sip"]
    webhook_url: Optional[str] = None
    webhook_method: Optional[Literal["POST", "GET"]] = None
