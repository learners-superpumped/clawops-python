from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._base_client import AsyncAPIClient, SyncAPIClient


class SyncAPIResource:
    """동기 API 리소스의 베이스 클래스."""

    _client: SyncAPIClient
    _account_id: str

    def __init__(self, client: SyncAPIClient, account_id: str) -> None:
        self._client = client
        self._account_id = account_id

    @property
    def _base_path(self) -> str:
        return f"/v1/accounts/{self._account_id}"


class AsyncAPIResource:
    """비동기 API 리소스의 베이스 클래스."""

    _client: AsyncAPIClient
    _account_id: str

    def __init__(self, client: AsyncAPIClient, account_id: str) -> None:
        self._client = client
        self._account_id = account_id

    @property
    def _base_path(self) -> str:
        return f"/v1/accounts/{self._account_id}"
