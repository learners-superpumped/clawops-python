from clawops.types.call_params import CallCreateParams, CallListParams, CallUpdateParams
from clawops.types.number_params import NumberCreateParams, NumberUpdateParams
from clawops.types.sip.credential_params import SipCredentialCreateParams


def test_call_create_params_structure():
    params: CallCreateParams = {"to": "01012345678", "from_": "07052358010", "url": "https://example.com/twiml"}
    assert params["to"] == "01012345678"


def test_call_list_params_structure():
    params: CallListParams = {"status": "completed", "page": 0, "page_size": 20}
    assert params["status"] == "completed"


def test_call_update_params_structure():
    params: CallUpdateParams = {"status": "completed"}
    assert params["status"] == "completed"


def test_number_create_params_structure():
    params: NumberCreateParams = {"source": "sip", "number": "1001"}
    assert params["source"] == "sip"


def test_number_update_params_structure():
    params: NumberUpdateParams = {"webhook_url": "https://example.com", "webhook_method": "POST"}
    assert params["webhook_url"] == "https://example.com"


def test_sip_credential_create_params_structure():
    params: SipCredentialCreateParams = {"display_name": "Office Phone"}
    assert params["display_name"] == "Office Phone"
