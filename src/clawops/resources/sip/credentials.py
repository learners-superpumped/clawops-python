from __future__ import annotations

from ..._resource import AsyncAPIResource, SyncAPIResource
from ..._utils import strip_not_given
from ...types.sip.credential import SipCredential, SipCredentialListItem


class SipCredentials(SyncAPIResource):
    """SIP Credentials 리소스. 계정당 최대 10개."""

    def create(self, *, display_name: str | None = None, extra_headers: dict[str, str] | None = None,
               extra_query: dict[str, object] | None = None, timeout: float | None = None) -> SipCredential:
        """SIP Credential을 생성합니다.

        Asterisk PJSIP Realtime 테이블에 자동으로 등록됩니다.
        password는 이 응답에서만 반환됩니다.

        Args:
            display_name: 디스플레이 이름 (선택).
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            생성된 SipCredential 객체 (password 포함).

        Raises:
            UnprocessableEntityError: SIP credential 한도 초과 (최대 10개).
        """
        body = strip_not_given({"displayName": display_name})
        return self._client._post(
            f"{self._base_path}/sip/credentials", body=body if body else {}, cast_to=SipCredential,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    def list(self, *, extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
             timeout: float | None = None) -> list[SipCredentialListItem]:
        """SIP Credential 목록 조회. password 미포함.

        Args:
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            SipCredentialListItem 리스트.
        """
        from ..._models import BaseModel

        class _CredentialsResponse(BaseModel):
            credentials: list[SipCredentialListItem]

        result = self._client._get(
            f"{self._base_path}/sip/credentials", cast_to=_CredentialsResponse,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        return result.credentials

    def get(self, credential_id: str, *, extra_headers: dict[str, str] | None = None,
            extra_query: dict[str, object] | None = None, timeout: float | None = None) -> SipCredentialListItem:
        """특정 SIP Credential 조회. password 미포함.

        Args:
            credential_id: Credential ID.
            extra_headers: 추가 HTTP 헤더.
            extra_query: 추가 쿼리 파라미터.
            timeout: 이 요청의 타임아웃 (초).

        Returns:
            SipCredentialListItem 객체.

        Raises:
            NotFoundError: SIP credential을 찾을 수 없음.
        """
        return self._client._get(
            f"{self._base_path}/sip/credentials/{credential_id}", cast_to=SipCredentialListItem,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    def delete(self, credential_id: str, *, extra_headers: dict[str, str] | None = None,
               timeout: float | None = None) -> None:
        """SIP Credential 삭제. PJSIP Realtime에서도 자동 제거.

        Args:
            credential_id: 삭제할 Credential ID.
            extra_headers: 추가 HTTP 헤더.
            timeout: 이 요청의 타임아웃 (초).

        Raises:
            NotFoundError: SIP credential을 찾을 수 없음.
        """
        self._client._delete(f"{self._base_path}/sip/credentials/{credential_id}",
                             extra_headers=extra_headers, timeout=timeout)


class AsyncSipCredentials(AsyncAPIResource):
    """SIP Credentials 비동기 리소스."""

    async def create(self, *, display_name: str | None = None, extra_headers: dict[str, str] | None = None,
                     extra_query: dict[str, object] | None = None, timeout: float | None = None) -> SipCredential:
        """SIP Credential을 비동기로 생성합니다."""
        body = strip_not_given({"displayName": display_name})
        return await self._client._post(
            f"{self._base_path}/sip/credentials", body=body if body else {}, cast_to=SipCredential,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    async def list(self, *, extra_headers: dict[str, str] | None = None, extra_query: dict[str, object] | None = None,
                   timeout: float | None = None) -> list[SipCredentialListItem]:
        """SIP Credential 목록을 비동기로 조회합니다."""
        from ..._models import BaseModel

        class _CredentialsResponse(BaseModel):
            credentials: list[SipCredentialListItem]

        result = await self._client._get(
            f"{self._base_path}/sip/credentials", cast_to=_CredentialsResponse,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )
        return result.credentials

    async def get(self, credential_id: str, *, extra_headers: dict[str, str] | None = None,
                  extra_query: dict[str, object] | None = None, timeout: float | None = None) -> SipCredentialListItem:
        """특정 SIP Credential을 비동기로 조회합니다."""
        return await self._client._get(
            f"{self._base_path}/sip/credentials/{credential_id}", cast_to=SipCredentialListItem,
            extra_headers=extra_headers, extra_query=extra_query, timeout=timeout,
        )

    async def delete(self, credential_id: str, *, extra_headers: dict[str, str] | None = None,
                     timeout: float | None = None) -> None:
        """SIP Credential을 비동기로 삭제합니다."""
        await self._client._delete(f"{self._base_path}/sip/credentials/{credential_id}",
                                   extra_headers=extra_headers, timeout=timeout)
