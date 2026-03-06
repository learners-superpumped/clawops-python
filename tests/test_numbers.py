import json
import httpx
import pytest
import respx

from clawops._base_client import SyncAPIClient
from clawops.resources.numbers import Numbers
from clawops.types.number import PhoneNumber, NumberListItem, NumberUpdateResponse

BASE = "https://api.claw-ops.com"
ACCOUNT = "AC1a2b3c4d"
NUMBERS_PATH = f"/v1/accounts/{ACCOUNT}/numbers"

@pytest.fixture
def client():
    c = SyncAPIClient(api_key="sk_test", base_url=BASE, max_retries=0)
    yield c
    c.close()

@pytest.fixture
def numbers(client):
    return Numbers(client=client, account_id=ACCOUNT)

class TestNumbersCreate:
    @respx.mock
    def test_create_pool(self, numbers):
        respx.post(f"{BASE}{NUMBERS_PATH}").mock(return_value=httpx.Response(201, json={"number": "07012340001", "source": "pool"}))
        num = numbers.create()
        assert isinstance(num, PhoneNumber)
        assert num.source == "pool"

    @respx.mock
    def test_create_sip(self, numbers):
        route = respx.post(f"{BASE}{NUMBERS_PATH}").mock(return_value=httpx.Response(201, json={"number": "1001", "source": "sip"}))
        num = numbers.create(source="sip", number="1001")
        assert num.source == "sip"
        body = json.loads(route.calls[0].request.content)
        assert body["source"] == "sip"
        assert body["number"] == "1001"

class TestNumbersList:
    @respx.mock
    def test_list(self, numbers):
        respx.get(f"{BASE}{NUMBERS_PATH}").mock(return_value=httpx.Response(200, json={
            "data": [
                {"number": "07012340001", "source": "pool", "webhookUrl": None, "webhookMethod": "POST", "createdAt": "2025-06-01T12:00:00Z"},
                {"number": "1001", "source": "sip", "webhookUrl": "https://my-app.com", "webhookMethod": "POST", "createdAt": "2025-06-01T12:00:00Z"},
            ]
        }))
        result = numbers.list()
        assert len(result) == 2
        assert isinstance(result[0], NumberListItem)

class TestNumbersUpdate:
    @respx.mock
    def test_update_webhook(self, numbers):
        respx.put(f"{BASE}{NUMBERS_PATH}/1001").mock(return_value=httpx.Response(200, json={
            "number": "1001", "source": "sip", "webhookUrl": "https://new.com", "webhookMethod": "POST", "createdAt": "2025-06-01T12:00:00Z",
        }))
        result = numbers.update("1001", webhook_url="https://new.com")
        assert isinstance(result, NumberUpdateResponse)
        assert result.webhook_url == "https://new.com"

class TestNumbersDelete:
    @respx.mock
    def test_delete(self, numbers):
        respx.delete(f"{BASE}{NUMBERS_PATH}/07012340001").mock(return_value=httpx.Response(204))
        result = numbers.delete("07012340001")
        assert result is None
