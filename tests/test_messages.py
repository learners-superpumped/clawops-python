import json
import httpx
import pytest
import respx

from clawops._base_client import SyncAPIClient
from clawops.resources.messages import Messages
from clawops.types.message import Message

BASE = "https://api.claw-ops.com"
ACCOUNT = "AC1a2b3c4d"
MESSAGES_PATH = f"/v1/accounts/{ACCOUNT}/messages"

MESSAGE_JSON = {
    "messageId": "MG0123456789abcdef0123456789abcdef",
    "status": "queued", "type": "sms",
    "to": "01012345678", "from": "07052358010",
    "body": "안녕하세요", "direction": "outbound",
    "accountId": "AC1a2b3c4d",
    "dateCreated": "2025-06-01T12:00:00Z", "dateUpdated": None,
}


@pytest.fixture
def client():
    c = SyncAPIClient(api_key="sk_test", base_url=BASE, max_retries=0)
    yield c
    c.close()


@pytest.fixture
def messages(client):
    return Messages(client=client, account_id=ACCOUNT)


class TestMessagesCreate:
    @respx.mock
    def test_create_sms(self, messages):
        respx.post(f"{BASE}{MESSAGES_PATH}").mock(return_value=httpx.Response(201, json=MESSAGE_JSON))
        msg = messages.create(to="01012345678", from_="07052358010", body="안녕하세요")
        assert isinstance(msg, Message)
        assert msg.message_id == "MG0123456789abcdef0123456789abcdef"
        assert msg.from_ == "07052358010"
        assert msg.type == "sms"

    @respx.mock
    def test_create_mms(self, messages):
        mms_json = {**MESSAGE_JSON, "type": "mms"}
        route = respx.post(f"{BASE}{MESSAGES_PATH}").mock(return_value=httpx.Response(201, json=mms_json))
        messages.create(to="010", from_="070", body="사진", type="mms", subject="제목")
        parsed = json.loads(route.calls[0].request.content)
        assert parsed["Type"] == "mms"
        assert parsed["Subject"] == "제목"


class TestMessagesList:
    @respx.mock
    def test_list_messages(self, messages):
        respx.get(f"{BASE}{MESSAGES_PATH}").mock(return_value=httpx.Response(200, json={
            "data": [MESSAGE_JSON], "meta": {"total": 1, "page": 0, "pageSize": 20},
        }))
        page = messages.list()
        items = list(page)
        assert len(items) == 1
        assert isinstance(items[0], Message)

    @respx.mock
    def test_list_with_filters(self, messages):
        route = respx.get(f"{BASE}{MESSAGES_PATH}").mock(return_value=httpx.Response(200, json={
            "data": [], "meta": {"total": 0, "page": 0, "pageSize": 10},
        }))
        messages.list(type="sms", status="sent", page=0, page_size=10)
        url = str(route.calls[0].request.url)
        assert "type=sms" in url
        assert "status=sent" in url
        assert "pageSize=10" in url


class TestMessagesGet:
    @respx.mock
    def test_get_message(self, messages):
        mid = "MG0123456789abcdef0123456789abcdef"
        respx.get(f"{BASE}{MESSAGES_PATH}/{mid}").mock(return_value=httpx.Response(200, json=MESSAGE_JSON))
        msg = messages.get(mid)
        assert msg.message_id == mid
        assert msg.body == "안녕하세요"


# --- Async Tests ---

from clawops._base_client import AsyncAPIClient
from clawops.resources.messages import AsyncMessages


@pytest.fixture
def async_client():
    c = AsyncAPIClient(api_key="sk_test", base_url=BASE, max_retries=0)
    yield c


@pytest.fixture
def async_messages(async_client):
    return AsyncMessages(client=async_client, account_id=ACCOUNT)


class TestAsyncMessagesCreate:
    @respx.mock
    @pytest.mark.asyncio
    async def test_create_sms(self, async_messages):
        respx.post(f"{BASE}{MESSAGES_PATH}").mock(return_value=httpx.Response(201, json=MESSAGE_JSON))
        msg = await async_messages.create(to="01012345678", from_="07052358010", body="안녕하세요")
        assert isinstance(msg, Message)
        assert msg.message_id == "MG0123456789abcdef0123456789abcdef"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_mms(self, async_messages):
        mms_json = {**MESSAGE_JSON, "type": "mms"}
        route = respx.post(f"{BASE}{MESSAGES_PATH}").mock(return_value=httpx.Response(201, json=mms_json))
        await async_messages.create(to="010", from_="070", body="사진", type="mms", subject="제목")
        parsed = json.loads(route.calls[0].request.content)
        assert parsed["Type"] == "mms"


class TestAsyncMessagesList:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_messages(self, async_messages):
        respx.get(f"{BASE}{MESSAGES_PATH}").mock(return_value=httpx.Response(200, json={
            "data": [MESSAGE_JSON], "meta": {"total": 1, "page": 0, "pageSize": 20},
        }))
        page = await async_messages.list()
        items = list(page)
        assert len(items) == 1
        assert isinstance(items[0], Message)

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_with_filters(self, async_messages):
        route = respx.get(f"{BASE}{MESSAGES_PATH}").mock(return_value=httpx.Response(200, json={
            "data": [], "meta": {"total": 0, "page": 0, "pageSize": 10},
        }))
        await async_messages.list(type="sms", status="sent", page=0, page_size=10)
        url = str(route.calls[0].request.url)
        assert "type=sms" in url
        assert "status=sent" in url


class TestAsyncMessagesGet:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_message(self, async_messages):
        mid = "MG0123456789abcdef0123456789abcdef"
        respx.get(f"{BASE}{MESSAGES_PATH}/{mid}").mock(return_value=httpx.Response(200, json=MESSAGE_JSON))
        msg = await async_messages.get(mid)
        assert msg.message_id == mid
