"""Full lifecycle integration tests."""
import base64
import hashlib
import hmac

import httpx
import pytest
import respx

from clawops import ClawOps, AsyncClawOps, NotFoundError

BASE = "https://api.claw-ops.com"
ACCOUNT = "AC1a2b3c4d"

CALL_RESPONSE = {
    "callId": "CA0123456789abcdef0123456789abcdef",
    "status": "queued", "to": "01012345678", "from": "07052358010",
    "direction": "outbound", "duration": None, "accountId": ACCOUNT,
    "dateCreated": "2025-06-01T12:00:00Z", "dateUpdated": None,
}


class TestSyncIntegration:
    @respx.mock
    def test_full_call_lifecycle(self):
        call_id = CALL_RESPONSE["callId"]
        respx.post(f"{BASE}/v1/accounts/{ACCOUNT}/calls").mock(return_value=httpx.Response(201, json=CALL_RESPONSE))
        respx.get(f"{BASE}/v1/accounts/{ACCOUNT}/calls/{call_id}").mock(
            return_value=httpx.Response(200, json={**CALL_RESPONSE, "status": "in-progress"}))
        respx.post(f"{BASE}/v1/accounts/{ACCOUNT}/calls/{call_id}").mock(
            return_value=httpx.Response(200, json={"callId": call_id, "status": "completed"}))

        with ClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            call = client.calls.create(to="01012345678", from_="07052358010", url="https://t.com",
                                       status_callback="https://t.com/status")
            assert call.status == "queued"
            assert call.from_ == "07052358010"
            fetched = client.calls.get(call_id)
            assert fetched.status == "in-progress"
            result = client.calls.update(call_id)
            assert result.status == "completed"

    @respx.mock
    def test_full_number_lifecycle(self):
        respx.post(f"{BASE}/v1/accounts/{ACCOUNT}/numbers").mock(
            return_value=httpx.Response(201, json={"number": "1001", "source": "sip", "webhookUrl": None, "webhookMethod": "POST", "createdAt": "2025-06-01T12:00:00Z"}))
        respx.get(f"{BASE}/v1/accounts/{ACCOUNT}/numbers").mock(
            return_value=httpx.Response(200, json={"data": [
                {"number": "1001", "source": "sip", "webhookUrl": None, "webhookMethod": "POST", "createdAt": "2025-06-01T12:00:00Z"}]}))
        respx.put(f"{BASE}/v1/accounts/{ACCOUNT}/numbers/1001").mock(
            return_value=httpx.Response(200, json={"number": "1001", "source": "sip",
                                                    "webhookUrl": "https://new.com", "webhookMethod": "POST", "createdAt": "2025-06-01T12:00:00Z"}))
        respx.delete(f"{BASE}/v1/accounts/{ACCOUNT}/numbers/1001").mock(return_value=httpx.Response(204))

        with ClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            num = client.numbers.create(source="sip", number="1001")
            assert num.number == "1001"
            nums = client.numbers.list()
            assert len(nums) == 1
            updated = client.numbers.update("1001", webhook_url="https://new.com")
            assert updated.webhook_url == "https://new.com"
            client.numbers.delete("1001")

    @respx.mock
    def test_full_sip_credential_lifecycle(self):
        cred_id = "clu1abc2def3ghi"
        cred_json = {
            "id": cred_id, "username": "usr_aBcDeFgHiJkL", "password": "secret123",
            "displayName": "Office", "sipServer": "sip.claw-ops.com",
            "sipPort": 5060, "transport": "UDP", "createdAt": "2025-06-01T12:00:00Z",
        }
        respx.post(f"{BASE}/v1/accounts/{ACCOUNT}/sip/credentials").mock(return_value=httpx.Response(201, json=cred_json))
        respx.get(f"{BASE}/v1/accounts/{ACCOUNT}/sip/credentials").mock(
            return_value=httpx.Response(200, json={"data": [
                {"id": cred_id, "username": "usr_aBcDeFgHiJkL", "displayName": "Office",
                 "sipServer": "sip.claw-ops.com", "sipPort": 5060, "transport": "UDP", "createdAt": "2025-06-01T12:00:00Z"}]}))
        respx.get(f"{BASE}/v1/accounts/{ACCOUNT}/sip/credentials/{cred_id}").mock(
            return_value=httpx.Response(200, json={
                "id": cred_id, "username": "usr_aBcDeFgHiJkL", "displayName": "Office",
                 "sipServer": "sip.claw-ops.com", "sipPort": 5060, "transport": "UDP", "createdAt": "2025-06-01T12:00:00Z"}))
        respx.delete(f"{BASE}/v1/accounts/{ACCOUNT}/sip/credentials/{cred_id}").mock(return_value=httpx.Response(204))

        with ClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            cred = client.sip.credentials.create(display_name="Office")
            assert cred.password == "secret123"
            creds = client.sip.credentials.list()
            assert len(creds) == 1
            fetched = client.sip.credentials.get(cred_id)
            assert fetched.username == "usr_aBcDeFgHiJkL"
            client.sip.credentials.delete(cred_id)

    @respx.mock
    def test_multi_account(self):
        respx.get(f"{BASE}/v1/accounts/AC_other/numbers").mock(
            return_value=httpx.Response(200, json={"data": []}))
        with ClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            other = client.accounts("AC_other")
            nums = other.numbers.list()
            assert nums == []

    @respx.mock
    def test_error_handling(self):
        respx.get(f"{BASE}/v1/accounts/{ACCOUNT}/calls/CA_invalid").mock(
            return_value=httpx.Response(404, json={"error": "콜을 찾을 수 없습니다"}))
        with ClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.calls.get("CA_invalid")
            assert exc_info.value.status_code == 404

    def test_webhook_verification(self):
        with ClawOps(api_key="sk_test", account_id=ACCOUNT) as client:
            url = "https://my-app.com/webhook"
            params = {"CallId": "CA123", "CallStatus": "completed"}
            key = "sk_sign"
            sorted_p = "".join(f"{k}{v}" for k, v in sorted(params.items()))
            sig = base64.b64encode(hmac.new(key.encode(), (url + sorted_p).encode(), hashlib.sha256).digest()).decode()
            assert client.webhooks.verify(url=url, params=params, signature=sig, signing_key=key) is True


class TestAsyncIntegration:
    @respx.mock
    @pytest.mark.asyncio
    async def test_async_call_create(self):
        respx.post(f"{BASE}/v1/accounts/{ACCOUNT}/calls").mock(return_value=httpx.Response(201, json=CALL_RESPONSE))
        async with AsyncClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            call = await client.calls.create(to="01012345678", from_="07052358010", url="https://t.com")
            assert call.call_id == CALL_RESPONSE["callId"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_multi_account(self):
        respx.get(f"{BASE}/v1/accounts/AC_other/numbers").mock(
            return_value=httpx.Response(200, json={"data": []}))
        async with AsyncClawOps(api_key="sk_test", account_id=ACCOUNT, max_retries=0) as client:
            other = client.accounts("AC_other")
            nums = await other.numbers.list()
            assert nums == []
