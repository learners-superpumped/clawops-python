import httpx
import pytest
import respx

from clawops._base_client import SyncAPIClient
from clawops.resources.sip.credentials import SipCredentials
from clawops.types.sip.credential import SipCredential, SipCredentialListItem

BASE = "https://api.claw-ops.com"
ACCOUNT = "AC1a2b3c4d"
CREDS_PATH = f"/v1/accounts/{ACCOUNT}/sip/credentials"

CRED_JSON = {
    "id": "clu1abc2def3ghi", "username": "usr_aBcDeFgHiJkL",
    "password": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4", "displayName": "Office Phone",
    "sipServer": "sip.claw-ops.com", "sipPort": 5060, "transport": "UDP",
    "createdAt": "2025-06-01T12:00:00Z",
}

@pytest.fixture
def client():
    c = SyncAPIClient(api_key="sk_test", base_url=BASE, max_retries=0)
    yield c
    c.close()

@pytest.fixture
def creds(client):
    return SipCredentials(client=client, account_id=ACCOUNT)

class TestCreate:
    @respx.mock
    def test_create(self, creds):
        respx.post(f"{BASE}{CREDS_PATH}").mock(return_value=httpx.Response(201, json=CRED_JSON))
        cred = creds.create(display_name="Office Phone")
        assert isinstance(cred, SipCredential)
        assert cred.password == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"

class TestList:
    @respx.mock
    def test_list(self, creds):
        respx.get(f"{BASE}{CREDS_PATH}").mock(return_value=httpx.Response(200, json={
            "credentials": [{"id": "clu1", "username": "usr_abc", "displayName": None, "createdAt": "2025-06-01T12:00:00Z"}]
        }))
        result = creds.list()
        assert len(result) == 1
        assert isinstance(result[0], SipCredentialListItem)

class TestGet:
    @respx.mock
    def test_get(self, creds):
        cid = "clu1abc2def3ghi"
        respx.get(f"{BASE}{CREDS_PATH}/{cid}").mock(return_value=httpx.Response(200, json={
            "id": cid, "username": "usr_aBcDeFgHiJkL", "displayName": "Office", "createdAt": "2025-06-01T12:00:00Z",
        }))
        result = creds.get(cid)
        assert isinstance(result, SipCredentialListItem)

class TestDelete:
    @respx.mock
    def test_delete(self, creds):
        cid = "clu1abc2def3ghi"
        respx.delete(f"{BASE}{CREDS_PATH}/{cid}").mock(return_value=httpx.Response(204))
        result = creds.delete(cid)
        assert result is None
