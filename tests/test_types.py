from datetime import datetime

from clawops.types.call import Call, CallControlResponse
from clawops.types.number import PhoneNumber, NumberListItem
from clawops.types.sip.credential import SipCredential, SipCredentialListItem
from clawops.types.shared import PaginationMeta


def test_call_from_api_response():
    data = {
        "callId": "CAabcdef1234567890abcdef1234567890",
        "status": "queued",
        "to": "01012345678",
        "from": "07052358010",
        "direction": "outbound",
        "duration": None,
        "accountId": "AC1a2b3c4d",
        "dateCreated": "2025-06-01T12:00:00Z",
        "dateUpdated": None,
    }
    call = Call.model_validate(data)
    assert call.call_id == "CAabcdef1234567890abcdef1234567890"
    assert call.status == "queued"
    assert call.to == "01012345678"
    assert call.from_ == "07052358010"
    assert call.direction == "outbound"
    assert call.duration is None
    assert call.account_id == "AC1a2b3c4d"
    assert isinstance(call.date_created, datetime)
    assert call.date_updated is None


def test_call_control_response():
    data = {"callId": "CA123", "status": "completed"}
    resp = CallControlResponse.model_validate(data)
    assert resp.call_id == "CA123"
    assert resp.status == "completed"


def test_phone_number_from_api():
    data = {"number": "07012340001", "source": "pool"}
    num = PhoneNumber.model_validate(data)
    assert num.number == "07012340001"
    assert num.source == "pool"


def test_number_list_item():
    data = {
        "number": "07012340001",
        "source": "pool",
        "webhookUrl": "https://my-app.com/voice",
        "createdAt": "2025-06-01T12:00:00Z",
    }
    item = NumberListItem.model_validate(data)
    assert item.number == "07012340001"
    assert item.webhook_url == "https://my-app.com/voice"


def test_sip_credential_with_password():
    data = {
        "id": "clu1abc2def3ghi",
        "username": "usr_aBcDeFgHiJkL",
        "password": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        "displayName": "Office Phone",
        "sipServer": "sip.claw-ops.com",
        "sipPort": 5060,
        "transport": "UDP",
        "createdAt": "2025-06-01T12:00:00Z",
    }
    cred = SipCredential.model_validate(data)
    assert cred.id == "clu1abc2def3ghi"
    assert cred.username == "usr_aBcDeFgHiJkL"
    assert cred.password == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    assert cred.display_name == "Office Phone"
    assert cred.sip_server == "sip.claw-ops.com"
    assert cred.sip_port == 5060
    assert cred.transport == "UDP"


def test_sip_credential_list_item_no_password():
    data = {
        "id": "clu1abc2def3ghi",
        "username": "usr_aBcDeFgHiJkL",
        "displayName": None,
        "createdAt": "2025-06-01T12:00:00Z",
    }
    item = SipCredentialListItem.model_validate(data)
    assert item.id == "clu1abc2def3ghi"
    assert item.display_name is None


def test_pagination_meta():
    data = {"total": 100, "page": 2, "pageSize": 20}
    meta = PaginationMeta.model_validate(data)
    assert meta.total == 100
    assert meta.page == 2
    assert meta.page_size == 20
