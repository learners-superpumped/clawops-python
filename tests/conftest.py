import pytest


@pytest.fixture
def api_key() -> str:
    return "sk_test_0123456789abcdef0123456789abcdef"


@pytest.fixture
def account_id() -> str:
    return "AC1a2b3c4d"


@pytest.fixture
def base_url() -> str:
    return "https://api.claw-ops.com"
