from __future__ import annotations

from typing import Annotated, Optional

from typing_extensions import TypedDict

from ..._utils import PropertyInfo


class SipCredentialCreateParams(TypedDict, total=False):
    """SIP Credential 생성 요청 파라미터. 계정당 최대 10개."""

    display_name: Annotated[Optional[str], PropertyInfo(alias="displayName")]
    """디스플레이 이름 (선택)."""
