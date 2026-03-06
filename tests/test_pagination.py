import httpx
import respx

from clawops._base_client import SyncAPIClient
from clawops._models import BaseModel
from clawops.pagination import SyncPage
from clawops.types.shared import PaginationMeta


class Item(BaseModel):
    id: int
    name: str


def test_sync_page_iteration():
    meta = PaginationMeta(total=3, page=0, page_size=10)
    page = SyncPage[Item](data=[Item(id=1, name="a"), Item(id=2, name="b")], meta=meta)
    items = list(page)
    assert len(items) == 2
    assert items[0].id == 1


def test_sync_page_has_next_page_false():
    meta = PaginationMeta(total=2, page=0, page_size=10)
    page = SyncPage[Item](data=[Item(id=1, name="a"), Item(id=2, name="b")], meta=meta)
    assert page.has_next_page() is False


def test_sync_page_has_next_page_true():
    meta = PaginationMeta(total=30, page=0, page_size=10)
    page = SyncPage[Item](data=[Item(id=i, name=f"item{i}") for i in range(10)], meta=meta)
    assert page.has_next_page() is True


@respx.mock
def test_auto_paging_iter():
    respx.get("https://api.claw-ops.com/items").mock(
        return_value=httpx.Response(200, json={
            "data": [{"id": 3, "name": "c"}],
            "meta": {"total": 3, "page": 1, "pageSize": 2},
        }),
    )
    client = SyncAPIClient(api_key="sk_test", base_url="https://api.claw-ops.com", max_retries=0)
    meta = PaginationMeta(total=3, page=0, page_size=2)
    first_page = SyncPage[Item](data=[Item(id=1, name="a"), Item(id=2, name="b")], meta=meta)
    first_page._set_client(client=client, path="/items", cast_to=Item, query={})
    all_items = list(first_page.auto_paging_iter())
    assert len(all_items) == 3
    assert all_items[2].id == 3
    client.close()
