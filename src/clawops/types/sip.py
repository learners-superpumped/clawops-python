from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from .._models import BaseModel


class SipCredential(BaseModel):
    """SIP 단말(digest credential) 모델.

    외부 SIP 단말이 우리 인프라에 인증할 때 쓰는 자격증명. 평문 password/ha1 은
    조회 응답에 포함되지 않는다(생성 시 1회만 노출). softphone 라우팅 설정 시
    이 모델의 ``id`` 를 number.update(sip_credential_id=...) 로 넘긴다.
    """

    id: str
    account_id: Optional[str] = None
    name: Optional[str] = None
    username: Optional[str] = None
    realm: Optional[str] = None
    enabled: Optional[bool] = None
    status: Optional[Literal["active", "disabled", "deleted"]] = None
    ip_acl_id: Optional[str] = None
    allowed_numbers: Optional[List[str]] = None
    last_used_at: Optional[datetime] = None
    date_created: Optional[datetime] = None
    date_updated: Optional[datetime] = None


class SipEndpoint(BaseModel):
    """SIP 엔드포인트(외부 PBX 트렁크) 모델.

    인바운드를 외부 PBX 로 전달(routing_type='sip')할 때 쓴다. sip 라우팅 설정 시
    이 모델의 ``id`` 를 number.update(sip_endpoint_id=...) 로 넘긴다.
    """

    id: str
    account_id: Optional[str] = None
    name: Optional[str] = None
    max_concurrent: Optional[int] = None
    status: Optional[Literal["active", "disabled"]] = None
    routes: Optional[List[Any]] = None
    date_created: Optional[datetime] = None
    date_updated: Optional[datetime] = None
