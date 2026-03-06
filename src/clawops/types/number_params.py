from __future__ import annotations

from typing import Annotated, Literal, Optional

from typing_extensions import TypedDict

from .._utils import PropertyInfo


class NumberCreateParams(TypedDict, total=False):
    """번호 등록 요청 파라미터."""

    source: Literal["pool", "sip"]
    """번호 유형. 'pool'=PSTN 풀, 'sip'=SIP 내선번호."""

    number: Optional[str]
    """SIP 내선번호 (source='sip'일 때 필수, 3~20자리)."""

    webhook_url: Annotated[Optional[str], PropertyInfo(alias="webhookUrl")]
    """수신 전화 처리용 Webhook URL."""


class NumberUpdateParams(TypedDict, total=False):
    """번호 설정 수정 요청 파라미터."""

    webhook_url: Annotated[Optional[str], PropertyInfo(alias="webhookUrl")]
    """수신 전화 처리용 Webhook URL."""

    webhook_method: Annotated[Literal["POST", "GET"], PropertyInfo(alias="webhookMethod")]
    """Webhook 호출 HTTP 메서드."""
