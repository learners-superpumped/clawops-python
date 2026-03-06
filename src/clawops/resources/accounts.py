from __future__ import annotations

from typing import TYPE_CHECKING

from .calls import AsyncCalls, Calls
from .numbers import AsyncNumbers, Numbers
from .sip import AsyncSip, Sip

if TYPE_CHECKING:
    from .._base_client import AsyncAPIClient, SyncAPIClient


class AccountContext:
    """특정 계정에 바인딩된 리소스 컨텍스트.

    Example::

        other = client.accounts("AC_other_id")
        other.calls.list()
        other.numbers.create(source="sip", number="1001")
    """

    def __init__(self, client: SyncAPIClient, account_id: str) -> None:
        self._client = client
        self._account_id = account_id

    @property
    def calls(self) -> Calls:
        return Calls(client=self._client, account_id=self._account_id)

    @property
    def numbers(self) -> Numbers:
        return Numbers(client=self._client, account_id=self._account_id)

    @property
    def sip(self) -> Sip:
        return Sip(client=self._client, account_id=self._account_id)


class AsyncAccountContext:
    """비동기 계정 컨텍스트."""

    def __init__(self, client: AsyncAPIClient, account_id: str) -> None:
        self._client = client
        self._account_id = account_id

    @property
    def calls(self) -> AsyncCalls:
        return AsyncCalls(client=self._client, account_id=self._account_id)

    @property
    def numbers(self) -> AsyncNumbers:
        return AsyncNumbers(client=self._client, account_id=self._account_id)

    @property
    def sip(self) -> AsyncSip:
        return AsyncSip(client=self._client, account_id=self._account_id)
