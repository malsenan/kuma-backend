"""Validate that an inbound webhook actually came from Meta.

Meta signs every webhook POST with an HMAC-SHA256 of the raw request body,
keyed by your App Secret, in the `X-Hub-Signature-256` header
(format: `sha256=<hex>`). We recompute it and compare in constant time.
"""

from __future__ import annotations

import hashlib
import hmac


def compute_signature(app_secret: str, body: bytes) -> str:
    """Return the expected header value, e.g. `sha256=ab12...`."""
    digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """Constant-time check of the `X-Hub-Signature-256` header.

    If `app_secret` is empty (local dev / not yet configured) verification is
    skipped and this returns True. In production always set WHATSAPP_APP_SECRET.
    """
    if not app_secret:
        return True
    if not header:
        return False
    expected = compute_signature(app_secret, body)
    return hmac.compare_digest(expected, header)
