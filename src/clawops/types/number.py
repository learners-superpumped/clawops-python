from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from .._models import BaseModel


class PhoneNumber(BaseModel):
    """전화번호 모델.

    Attributes:
        number: 전화번호.
        webhook_url: Webhook URL. 미설정 시 None.
        webhook_method: Webhook HTTP 메서드.
        created_at: 등록 시각.
    """

    number: str
    webhook_url: Optional[str] = None
    webhook_method: Optional[Literal["POST", "GET"]] = None
    created_at: Optional[datetime] = None


NumberListItem = PhoneNumber
NumberUpdateResponse = PhoneNumber
