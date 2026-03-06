from __future__ import annotations

import base64
import hashlib
import hmac

from ._exceptions import ClawOpsError


class WebhookVerificationError(ClawOpsError):
    """Webhook 서명 검증 실패."""


class Webhooks:
    """ClawOps webhook 서명 검증 유틸리티.

    ClawOps는 webhook 요청 시 X-Signature 헤더에
    HMAC-SHA1 서명을 포함합니다.

    Example::

        from clawops import ClawOps

        client = ClawOps(api_key="sk_...", account_id="AC...")

        @app.route("/webhook", methods=["POST"])
        def webhook():
            client.webhooks.verify(
                url="https://my-app.com/webhook",
                params=request.form.to_dict(),
                signature=request.headers["X-Signature"],
                signing_key="your_signing_key",
            )
    """

    def verify(self, *, url: str, params: dict[str, str], signature: str, signing_key: str) -> bool:
        """Webhook 요청의 서명을 검증합니다.

        Args:
            url: 원본 webhook URL.
            params: POST body 파라미터 (key-value).
            signature: X-Signature 헤더 값.
            signing_key: 계정의 signing key.

        Returns:
            True (검증 성공).

        Raises:
            WebhookVerificationError: 서명 불일치.
        """
        expected = self._compute_signature(url, params, signing_key)
        if not hmac.compare_digest(expected, signature):
            raise WebhookVerificationError("Webhook 서명이 일치하지 않습니다.")
        return True

    @staticmethod
    def _compute_signature(url: str, params: dict[str, str], signing_key: str) -> str:
        sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
        data_to_sign = url + sorted_params
        digest = hmac.new(signing_key.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha1).digest()
        return base64.b64encode(digest).decode("utf-8")
