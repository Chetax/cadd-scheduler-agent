"""
SlackSignatureVerifier — verifies that incoming Slack requests are
authentic before any downstream handler (e.g. /slack/commands) acts
on them.

Slack signs every request using HMAC-SHA256 keyed with the app's
signing secret. Without this check, anyone who knows the payload
shape of a slash command could forge a request claiming to be an
already-onboarded user, triggering actions using that user's live
Google Calendar credentials with no involvement from Slack at all.
"""

import time
import hmac
import hashlib


class StaleSlackRequestError(Exception):
    """Raised when a Slack request's timestamp is outside the allowed
    freshness window (more than 5 minutes old or in the future),
    indicating a possible replay attack."""
    pass


class InvalidSlackSignatureError(Exception):
    """Raised when a Slack request's HMAC-SHA256 signature does not
    match the signature computed from the raw body and signing secret,
    indicating the request did not originate from Slack."""
    pass

class SlackSignatureVerifier:
    """Verifies that an incoming HTTP request genuinely originated from
    Slack, by recomputing Slack's HMAC-SHA256 signature over the raw
    request body and comparing it against the X-Slack-Signature header.

    This is a security primitive: it prevents anyone who is not Slack
    from forging requests to endpoints like /slack/commands (e.g. to
    trigger actions on behalf of an already-onboarded user).
    """

    def __init__(self, signing_secret: str):
        self.signing_secret = signing_secret

    def verify(self, timestamp: str, signature: str, raw_body: bytes) -> bool:
        """Verify a Slack request's signature.

        Args:
            timestamp: value of the X-Slack-Request-Timestamp header.
            signature: value of the X-Slack-Signature header (e.g. "v0=...").
            raw_body: the raw, unparsed request body bytes.

        Returns:
            True if the signature is valid and the request is fresh.

        Raises:
            StaleSlackRequestError: if the timestamp is more than 5
                minutes old or in the future (possible replay attack).
            InvalidSlackSignatureError: if the computed signature does
                not match the provided signature.
        """
        if abs(time.time() - int(timestamp)) > 300:
            raise StaleSlackRequestError(
                f"Slack request timestamp {timestamp} is outside the 5-minute freshness window."
            )

        basestring = f"v0:{timestamp}:{raw_body.decode('utf-8')}"

        computed_signature = "v0=" + hmac.new(
            key=self.signing_secret.encode("utf-8"),
            msg=basestring.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(computed_signature, signature):
            raise InvalidSlackSignatureError(
                "Computed Slack signature does not match the provided signature."
            )

        return True

