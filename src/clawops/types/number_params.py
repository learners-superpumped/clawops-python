from __future__ import annotations

from typing import Annotated, Literal, Optional

from typing_extensions import TypedDict

from .._utils import PropertyInfo


class NumberCreateParams(TypedDict, total=False):
    """번호 발급 요청 파라미터."""

    webhook_url: Annotated[Optional[str], PropertyInfo(alias="webhookUrl")]
    """수신 전화 처리용 Webhook URL."""


class NumberUpdateParams(TypedDict, total=False):
    """번호 설정 수정 요청 파라미터."""

    webhook_url: Annotated[Optional[str], PropertyInfo(alias="webhookUrl")]
    """수신 전화 처리용 Webhook URL."""

    webhook_method: Annotated[Literal["POST", "GET"], PropertyInfo(alias="webhookMethod")]
    """Webhook 호출 HTTP 메서드."""
