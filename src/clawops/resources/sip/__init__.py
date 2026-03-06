from __future__ import annotations

from ..._resource import AsyncAPIResource, SyncAPIResource
from .credentials import AsyncSipCredentials, SipCredentials

__all__ = ["AsyncSip", "AsyncSipCredentials", "Sip", "SipCredentials"]


class Sip(SyncAPIResource):
    """SIP 리소스 컨테이너. ``client.sip.credentials``로 접근."""

    @property
    def credentials(self) -> SipCredentials:
        return SipCredentials(client=self._client, account_id=self._account_id)


class AsyncSip(AsyncAPIResource):
    """SIP 비동기 리소스 컨테이너."""

    @property
    def credentials(self) -> AsyncSipCredentials:
        return AsyncSipCredentials(client=self._client, account_id=self._account_id)
