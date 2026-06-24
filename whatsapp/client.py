"""Thin synchronous client over the WhatsApp Cloud API (Graph API).

Sync (httpx.Client) on purpose: the same client is used both from the webhook
handler (FastAPI runs sync route handlers in a threadpool) and from one-off
outreach scripts that message the pilot leads. At pilot volume (~20 contacts)
there is no need for async complexity.

Reference: https://developers.facebook.com/docs/whatsapp/cloud-api/reference
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from whatsapp.config import WhatsAppSettings, get_settings

logger = logging.getLogger(__name__)

# WhatsApp interactive reply buttons allow at most 3; list rows at most 10 total.
MAX_BUTTONS = 3
MAX_LIST_ROWS = 10
BUTTON_TITLE_LIMIT = 20  # characters


class WhatsAppError(RuntimeError):
    """Raised when the Graph API returns a non-2xx response."""


class WhatsAppClient:
    def __init__(self, settings: Optional[WhatsAppSettings] = None, timeout: float = 30.0):
        self.settings = settings or get_settings()
        self._timeout = timeout

    # -- internals ------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.token}",
            "Content-Type": "application/json",
        }

    def _require_credentials(self, need_phone_id: bool = True) -> None:
        """Fail fast with a clear error instead of firing a malformed request.

        Without this, an empty token produces a confusing low-level
        `Illegal header value b'Bearer '` from httpx. Guarding here also means a
        misconfigured deploy never makes a half-formed call to Meta.
        """
        missing = []
        if not self.settings.token:
            missing.append("WHATSAPP_TOKEN")
        if need_phone_id and not self.settings.phone_number_id:
            missing.append("WHATSAPP_PHONE_NUMBER_ID")
        if missing:
            raise WhatsAppError(
                "WhatsApp not configured: missing "
                + ", ".join(missing)
                + ". Set these in .env (see .env.example)."
            )

    def _post_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_credentials()
        payload = {"messaging_product": "whatsapp", **payload}
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(self.settings.messages_url, headers=self._headers(), json=payload)
        if resp.status_code >= 300:
            logger.error("WhatsApp send failed (%s): %s", resp.status_code, resp.text)
            raise WhatsAppError(f"{resp.status_code}: {resp.text}")
        return resp.json()

    @staticmethod
    def _sent_id(response: dict[str, Any]) -> str:
        try:
            return response["messages"][0]["id"]
        except (KeyError, IndexError):
            return ""

    # -- sending --------------------------------------------------------------

    def send_text(self, to: str, body: str, preview_url: bool = False) -> str:
        """Send a plain text message. Returns the sent message id."""
        resp = self._post_message({
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": preview_url, "body": body},
        })
        return self._sent_id(resp)

    def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]],
                     header: str = "", footer: str = "") -> str:
        """Send up to 3 reply buttons. `buttons` is a list of (id, title)."""
        if not 1 <= len(buttons) <= MAX_BUTTONS:
            raise ValueError(f"WhatsApp allows 1–{MAX_BUTTONS} buttons, got {len(buttons)}")
        action = {
            "buttons": [
                {"type": "reply", "reply": {"id": bid, "title": title[:BUTTON_TITLE_LIMIT]}}
                for bid, title in buttons
            ]
        }
        interactive: dict[str, Any] = {"type": "button", "body": {"text": body}, "action": action}
        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}
        resp = self._post_message({"to": to, "type": "interactive", "interactive": interactive})
        return self._sent_id(resp)

    def send_list(self, to: str, body: str, button_text: str,
                  rows: list[tuple[str, str, str]], header: str = "", footer: str = "") -> str:
        """Send a single-section interactive list (use when >3 options).

        `rows` is a list of (id, title, description). Max 10 rows total.
        """
        if not 1 <= len(rows) <= MAX_LIST_ROWS:
            raise ValueError(f"WhatsApp allows 1–{MAX_LIST_ROWS} list rows, got {len(rows)}")
        section = {
            "rows": [
                {"id": rid, "title": title[:24], "description": desc[:72]}
                for rid, title, desc in rows
            ]
        }
        interactive: dict[str, Any] = {
            "type": "list",
            "body": {"text": body},
            "action": {"button": button_text[:BUTTON_TITLE_LIMIT], "sections": [section]},
        }
        if header:
            interactive["header"] = {"type": "text", "text": header}
        if footer:
            interactive["footer"] = {"text": footer}
        resp = self._post_message({"to": to, "type": "interactive", "interactive": interactive})
        return self._sent_id(resp)

    def send_template(self, to: str, name: str, language: str = "pt_BR",
                      components: Optional[list[dict[str, Any]]] = None) -> str:
        """Send a pre-approved message template.

        Required for the *first* contact and any message sent outside the
        24-hour customer service window. Templates must be approved in the
        Meta Business Manager before use.
        """
        template: dict[str, Any] = {"name": name, "language": {"code": language}}
        if components:
            template["components"] = components
        resp = self._post_message({"to": to, "type": "template", "template": template})
        return self._sent_id(resp)

    def mark_read(self, message_id: str) -> None:
        """Send a read receipt (blue ticks) for an inbound message."""
        try:
            self._post_message({"status": "read", "message_id": message_id})
        except WhatsAppError:
            logger.warning("Could not mark message %s as read", message_id)

    # -- media ----------------------------------------------------------------

    def get_media_url(self, media_id: str) -> str:
        """Resolve a media id to a temporary, authenticated download URL."""
        self._require_credentials(need_phone_id=False)
        url = f"{self.settings.base_url}/{media_id}"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {self.settings.token}"})
        if resp.status_code >= 300:
            raise WhatsAppError(f"get_media_url {resp.status_code}: {resp.text}")
        return resp.json().get("url", "")

    def download_media(self, media_id: str) -> bytes:
        """Download the raw bytes for a media id (two-step: resolve then GET)."""
        media_url = self.get_media_url(media_id)
        if not media_url:
            raise WhatsAppError(f"No URL returned for media {media_id}")
        with httpx.Client(timeout=self._timeout) as client:
            # The media URL also requires the bearer token.
            resp = client.get(media_url, headers={"Authorization": f"Bearer {self.settings.token}"})
        if resp.status_code >= 300:
            raise WhatsAppError(f"download_media {resp.status_code}: {resp.text}")
        return resp.content
