import base64
import hashlib
import hmac

import pytest

from clawops.webhooks import Webhooks, WebhookVerificationError


@pytest.fixture
def webhooks():
    return Webhooks()


def _compute_signature(url: str, params: dict[str, str], signing_key: str) -> str:
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    data = url + sorted_params
    digest = hmac.new(signing_key.encode(), data.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def test_verify_valid(webhooks):
    url = "https://my-app.com/webhook"
    params = {"CallId": "CA123", "CallStatus": "completed"}
    key = "test_key"
    sig = _compute_signature(url, params, key)
    assert webhooks.verify(url=url, params=params, signature=sig, signing_key=key) is True


def test_verify_invalid(webhooks):
    with pytest.raises(WebhookVerificationError, match="서명이 일치하지 않습니다"):
        webhooks.verify(url="https://test.com", params={"a": "b"}, signature="bad", signing_key="key")


def test_verify_tampered(webhooks):
    url = "https://my-app.com/webhook"
    key = "test_key"
    sig = _compute_signature(url, {"CallId": "CA123"}, key)
    with pytest.raises(WebhookVerificationError):
        webhooks.verify(url=url, params={"CallId": "CA999"}, signature=sig, signing_key=key)


def test_verify_empty_params(webhooks):
    url = "https://my-app.com/webhook"
    key = "test_key"
    sig = _compute_signature(url, {}, key)
    assert webhooks.verify(url=url, params={}, signature=sig, signing_key=key) is True
