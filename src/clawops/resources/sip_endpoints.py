from __future__ import annotations

from typing import Literal

from .._models import BaseModel
from .._resource import AsyncAPIResource, SyncAPIResource
from .._utils import strip_not_given
from ..types.sip import SipEndpoint


class _SipEndpointListResponse(BaseModel):
    data: list[SipEndpoint]


class SipEndpoints(SyncAPIResource):
    """SIP 엔드포인트(외부 PBX 트렁크) 리소스 — 조회 전용.

    생성/수정/삭제는 대시보드 또는 REST API 를 사용. 본 SDK 는 sip 라우팅 설정에
    필요한 endpoint id 를 확인하기 위한 list/get 만 제공한다.
    """

    def list(self, *, status: Literal["active", "disabled"] | None = None,
             page: int | None = None, page_size: int | None = None,
             extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
             timeout: float | None = None) -> list[SipEndpoint]:
        """등록된 SIP 엔드포인트 목록을 조회합니다.

        Args:
            status: 'active' | 'disabled' 필터.
            page: 0-기반 페이지 번호.
            page_size: 페이지 크기 (1~100).

        Returns:
            SipEndpoint 리스트.
        """
        query = strip_not_given({"status": status, "page": page, "pageSize": page_size})
        merged_query = {**query, **(extra_query or {})}
        result = self._client._get(
            f"{self._base_path}/sip-endpoints", cast_to=_SipEndpointListResponse,
            extra_headers=extra_headers, extra_query=merged_query or None, timeout=timeout,
        )
        return result.data

    def get(self, endpoint_id: str, *, extra_headers: dict[str, str] | None = None,
            timeout: float | None = None) -> SipEndpoint:
        """SIP 엔드포인트 단건을 id 로 조회합니다."""
        return self._client._get(
            f"{self._base_path}/sip-endpoints/{endpoint_id}", cast_to=SipEndpoint,
            extra_headers=extra_headers, timeout=timeout,
        )


class AsyncSipEndpoints(AsyncAPIResource):
    """SIP 엔드포인트 리소스 (비동기) — 조회 전용."""

    async def list(self, *, status: Literal["active", "disabled"] | None = None,
                   page: int | None = None, page_size: int | None = None,
                   extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                   timeout: float | None = None) -> list[SipEndpoint]:
        """등록된 SIP 엔드포인트 목록을 비동기로 조회합니다."""
        query = strip_not_given({"status": status, "page": page, "pageSize": page_size})
        merged_query = {**query, **(extra_query or {})}
        result = await self._client._get(
            f"{self._base_path}/sip-endpoints", cast_to=_SipEndpointListResponse,
            extra_headers=extra_headers, extra_query=merged_query or None, timeout=timeout,
        )
        return result.data

    async def get(self, endpoint_id: str, *, extra_headers: dict[str, str] | None = None,
                  timeout: float | None = None) -> SipEndpoint:
        """SIP 엔드포인트 단건을 비동기로 조회합니다."""
        return await self._client._get(
            f"{self._base_path}/sip-endpoints/{endpoint_id}", cast_to=SipEndpoint,
            extra_headers=extra_headers, timeout=timeout,
        )
