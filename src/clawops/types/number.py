from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from .._models import BaseModel


class PhoneNumber(BaseModel):
    """전화번호 모델. 모든 CRUD 엔드포인트에서 동일한 필드셋을 반환합니다.

    Attributes:
        number: 전화번호.
        source: 번호 유형. 'pool'은 PSTN 풀 발급, 'sip'은 SIP 내선번호.
        webhook_url: Webhook URL. 미설정 시 None.
        webhook_method: Webhook HTTP 메서드.
        created_at: 등록 시각.
    """

    number: str
    source: Literal["pool", "sip"]
    webhook_url: Optional[str] = None
    webhook_method: Optional[Literal["POST", "GET"]] = None
    created_at: Optional[datetime] = None


NumberListItem = PhoneNumber
NumberUpdateResponse = PhoneNumber
