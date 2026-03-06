from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..._models import BaseModel


class SipCredential(BaseModel):
    """SIP Credential 생성 응답 모델.

    password는 생성 시에만 반환되며, 이후 조회 시에는 포함되지 않습니다.

    Attributes:
        id: Credential 고유 식별자.
        username: SIP 사용자명 (예: 'usr_aBcDeFgHiJkL').
        password: SIP 비밀번호. 생성 응답에서만 반환.
        display_name: 디스플레이 이름 (선택).
        sip_server: SIP 서버 주소.
        sip_port: SIP 포트 번호.
        transport: 전송 프로토콜.
        created_at: 생성 시각.
    """

    id: str
    username: str
    password: Optional[str] = None
    display_name: Optional[str] = None
    sip_server: Optional[str] = None
    sip_port: Optional[int] = None
    transport: Optional[str] = None
    created_at: Optional[datetime] = None


class SipCredentialListItem(BaseModel):
    """SIP Credential 목록/단건 조회 항목. password 미포함.

    Attributes:
        id: Credential 고유 식별자.
        username: SIP 사용자명.
        display_name: 디스플레이 이름.
        created_at: 생성 시각.
    """

    id: str
    username: str
    display_name: Optional[str] = None
    created_at: Optional[datetime] = None
