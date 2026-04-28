import httpx
import pytest
import respx

from clawops._base_client import SyncAPIClient
from clawops.resources.assignment_links import AssignmentLinks
from clawops.types.assignment_link import AssignmentLink, AssignmentLinkCreateResponse

BASE = "https://api.claw-ops.com"
ACCOUNT = "AC1a2b3c4d"
PATH = f"/v1/accounts/{ACCOUNT}/assignment-links"


@pytest.fixture
def client():
    c = SyncAPIClient(api_key="sk_test", base_url=BASE, max_retries=0)
    yield c
    c.close()


@pytest.fixture
def links(client):
    return AssignmentLinks(client=client, account_id=ACCOUNT)


class TestCreate:
    @respx.mock
    def test_create_minimal(self, links):
        respx.post(f"{BASE}{PATH}").mock(
            return_value=httpx.Response(
                201,
                json={
                    "token": "tok123",
                    "url": "https://app.claw-ops.com/assign/tok123",
                    "expiresAt": "2026-05-01T00:00:00Z",
                },
            )
        )
        res = links.create()
        assert isinstance(res, AssignmentLinkCreateResponse)
        assert res.token == "tok123"
        assert res.url.endswith("/tok123")

    @respx.mock
    def test_create_with_options(self, links):
        route = respx.post(f"{BASE}{PATH}").mock(
            return_value=httpx.Response(
                201,
                json={
                    "token": "t",
                    "url": "u",
                    "expiresAt": "2026-05-01T00:00:00Z",
                },
            )
        )
        links.create(webhook_url="https://x", webhook_method="GET", note="n")
        body = route.calls.last.request.content.decode()
        assert '"webhookUrl":"https://x"' in body
        assert '"webhookMethod":"GET"' in body
        assert '"note":"n"' in body


class TestList:
    @respx.mock
    def test_list_returns_page(self, links):
        respx.get(f"{BASE}{PATH}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "linkId": "lnk_1",
                            "url": "https://app.claw-ops.com/assign/lnk_1",
                            "status": "pending",
                            "createdAt": "2026-04-01T00:00:00Z",
                            "expiresAt": "2026-04-08T00:00:00Z",
                            "consumedAt": None,
                            "webhookUrl": None,
                            "webhookMethod": "POST",
                            "note": None,
                            "assignment": None,
                        }
                    ],
                    "meta": {"page": 0, "pageSize": 20, "total": 1},
                },
            )
        )
        page = links.list()
        assert page.meta.total == 1
        assert len(page.data) == 1
        assert isinstance(page.data[0], AssignmentLink)
        assert page.data[0].link_id == "lnk_1"
        assert page.data[0].status == "pending"

    @respx.mock
    def test_list_status_filter_in_query(self, links):
        route = respx.get(f"{BASE}{PATH}").mock(
            return_value=httpx.Response(
                200, json={"data": [], "meta": {"page": 0, "pageSize": 20, "total": 0}}
            )
        )
        links.list(status="consumed", page=2, page_size=50)
        url = str(route.calls.last.request.url)
        assert "status=consumed" in url
        assert "page=2" in url
        assert "pageSize=50" in url


class TestRetrieve:
    @respx.mock
    def test_retrieve(self, links):
        respx.get(f"{BASE}{PATH}/lnk_1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "linkId": "lnk_1",
                    "url": "u",
                    "status": "consumed",
                    "createdAt": "2026-04-01T00:00:00Z",
                    "expiresAt": "2026-04-08T00:00:00Z",
                    "consumedAt": "2026-04-02T00:00:00Z",
                    "webhookUrl": None,
                    "webhookMethod": "POST",
                    "note": None,
                    "assignment": {
                        "number": "07012340001",
                        "name": "홍길동",
                        "consumedAt": "2026-04-02T00:00:00Z",
                        "releasedAt": None,
                    },
                },
            )
        )
        link = links.retrieve("lnk_1")
        assert link.status == "consumed"
        assert link.assignment is not None
        assert link.assignment.number == "07012340001"
        assert link.assignment.released_at is None


class TestRevoke:
    @respx.mock
    def test_revoke(self, links):
        respx.delete(f"{BASE}{PATH}/lnk_1").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        result = links.revoke("lnk_1")
        assert result is None
