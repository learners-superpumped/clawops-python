import json
import httpx
import pytest
import respx

from clawops._base_client import SyncAPIClient
from clawops.resources.calls import Calls
from clawops.types.call import Call, CallControlResponse

BASE = "https://api.claw-ops.com"
ACCOUNT = "AC1a2b3c4d"
CALLS_PATH = f"/v1/accounts/{ACCOUNT}/calls"

CALL_JSON = {
    "callId": "CA0123456789abcdef0123456789abcdef",
    "status": "queued", "to": "01012345678", "from": "07052358010",
    "direction": "outbound", "duration": None, "accountId": "AC1a2b3c4d",
    "dateCreated": "2025-06-01T12:00:00Z", "dateUpdated": None,
}

@pytest.fixture
def client():
    c = SyncAPIClient(api_key="sk_test", base_url=BASE, max_retries=0)
    yield c
    c.close()

@pytest.fixture
def calls(client):
    return Calls(client=client, account_id=ACCOUNT)

class TestCallsCreate:
    @respx.mock
    def test_create_call(self, calls):
        respx.post(f"{BASE}{CALLS_PATH}").mock(return_value=httpx.Response(201, json=CALL_JSON))
        call = calls.create(to="01012345678", from_="07052358010", url="https://my-app.com/twiml")
        assert isinstance(call, Call)
        assert call.call_id == "CA0123456789abcdef0123456789abcdef"
        assert call.from_ == "07052358010"

    @respx.mock
    def test_create_with_callback(self, calls):
        route = respx.post(f"{BASE}{CALLS_PATH}").mock(return_value=httpx.Response(201, json=CALL_JSON))
        calls.create(to="010", from_="070", url="https://t.com",
                     status_callback="https://my-app.com/status", status_callback_event="initiated completed")
        parsed = json.loads(route.calls[0].request.content)
        assert parsed["StatusCallback"] == "https://my-app.com/status"

class TestCallsList:
    @respx.mock
    def test_list_calls(self, calls):
        respx.get(f"{BASE}{CALLS_PATH}").mock(return_value=httpx.Response(200, json={
            "data": [CALL_JSON], "meta": {"total": 1, "page": 0, "pageSize": 20},
        }))
        page = calls.list()
        items = list(page)
        assert len(items) == 1
        assert isinstance(items[0], Call)

    @respx.mock
    def test_list_with_filters(self, calls):
        route = respx.get(f"{BASE}{CALLS_PATH}").mock(return_value=httpx.Response(200, json={
            "data": [], "meta": {"total": 0, "page": 0, "pageSize": 10},
        }))
        calls.list(status="completed", page=0, page_size=10)
        url = str(route.calls[0].request.url)
        assert "status=completed" in url
        assert "pageSize=10" in url

class TestCallsGet:
    @respx.mock
    def test_get_call(self, calls):
        cid = "CA0123456789abcdef0123456789abcdef"
        respx.get(f"{BASE}{CALLS_PATH}/{cid}").mock(return_value=httpx.Response(200, json=CALL_JSON))
        call = calls.get(cid)
        assert call.call_id == cid

class TestCallsUpdate:
    @respx.mock
    def test_update_completed(self, calls):
        cid = "CA0123456789abcdef0123456789abcdef"
        respx.post(f"{BASE}{CALLS_PATH}/{cid}").mock(
            return_value=httpx.Response(200, json={"callId": cid, "status": "completed"}))
        result = calls.update(cid, status="completed")
        assert isinstance(result, CallControlResponse)
        assert result.status == "completed"
