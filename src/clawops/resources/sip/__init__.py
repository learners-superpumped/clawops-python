from __future__ import annotations

from typing import TYPE_CHECKING

from ..._resource import AsyncAPIResource, SyncAPIResource
from .credentials import AsyncSipCredentials, SipCredentials

if TYPE_CHECKING:
    from ..._base_client import AsyncAPIClient, SyncAPIClient

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
