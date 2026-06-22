from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from .._models import BaseModel


class PhoneNumber(BaseModel):
    """전화번호 모델.

    Attributes:
        number: 전화번호.
        source: 번호 소스.
        webhook_url: Webhook URL. 미설정 시 None.
        webhook_method: Webhook HTTP 메서드.
        routing_type: inbound 라우팅 모드 (webhook | sip | softphone).
        sip_endpoint_id: routing_type='sip' 일 때 라우팅할 SipEndpoint id.
        sip_credential_id: routing_type='softphone' 일 때 착신할 SIP credential(단말) id.
        created_at: 등록 시각.
    """

    number: str
    source: Optional[str] = None
    webhook_url: Optional[str] = None
    webhook_method: Optional[Literal["POST", "GET"]] = None
    routing_type: Optional[Literal["webhook", "sip", "softphone"]] = None
    sip_endpoint_id: Optional[str] = None
    sip_credential_id: Optional[str] = None
    created_at: Optional[datetime] = None


NumberListItem = PhoneNumber
NumberUpdateResponse = PhoneNumber
