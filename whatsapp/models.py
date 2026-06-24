"""Pydantic models for inbound WhatsApp Cloud API webhook payloads.

Meta's payload is deeply nested and many fields are optional depending on the
message type. These models are intentionally lenient (`extra="ignore"`, most
fields optional) so a schema change on Meta's side degrades gracefully instead
of 500-ing the webhook. `parse_inbound()` flattens the nested structure into the
simple `InboundMessage` objects the rest of the app works with.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --- Raw Meta payload (only the parts we read) -------------------------------

class TextBody(_Lenient):
    body: str = ""


class MediaObject(_Lenient):
    id: str = ""
    mime_type: str = ""
    sha256: str = ""
    caption: str = ""
    filename: str = ""
    voice: bool = False


class InteractiveReply(_Lenient):
    id: str = ""
    title: str = ""
    description: str = ""


class Interactive(_Lenient):
    type: str = ""
    button_reply: Optional[InteractiveReply] = None
    list_reply: Optional[InteractiveReply] = None


class ButtonPayload(_Lenient):
    text: str = ""
    payload: str = ""


class Location(_Lenient):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    name: str = ""
    address: str = ""


class RawMessage(_Lenient):
    """A single message object from `value.messages[]`."""

    id: str = ""
    from_: str = Field(default="", alias="from")
    timestamp: str = ""
    type: str = ""
    text: Optional[TextBody] = None
    image: Optional[MediaObject] = None
    document: Optional[MediaObject] = None
    audio: Optional[MediaObject] = None
    video: Optional[MediaObject] = None
    sticker: Optional[MediaObject] = None
    interactive: Optional[Interactive] = None
    button: Optional[ButtonPayload] = None
    location: Optional[Location] = None


class Profile(_Lenient):
    name: str = ""


class Contact(_Lenient):
    wa_id: str = ""
    profile: Optional[Profile] = None


class Metadata(_Lenient):
    display_phone_number: str = ""
    phone_number_id: str = ""


class Status(_Lenient):
    """Delivery/read receipt from `value.statuses[]`."""

    id: str = ""
    status: str = ""
    timestamp: str = ""
    recipient_id: str = ""


class ChangeValue(_Lenient):
    messaging_product: str = ""
    metadata: Optional[Metadata] = None
    contacts: list[Contact] = Field(default_factory=list)
    messages: list[RawMessage] = Field(default_factory=list)
    statuses: list[Status] = Field(default_factory=list)


class Change(_Lenient):
    field: str = ""
    value: Optional[ChangeValue] = None


class Entry(_Lenient):
    id: str = ""
    changes: list[Change] = Field(default_factory=list)


class WebhookPayload(_Lenient):
    object: str = ""
    entry: list[Entry] = Field(default_factory=list)


# --- Normalized message we actually work with --------------------------------

MessageType = Literal[
    "text", "image", "document", "audio", "video", "sticker",
    "interactive", "button", "location", "unknown",
]

_KNOWN_TYPES: frozenset[str] = frozenset(
    {"text", "image", "document", "audio", "video", "sticker", "interactive", "button", "location"}
)


class InboundMessage(BaseModel):
    """Flattened, app-friendly view of one inbound WhatsApp message."""

    message_id: str
    wa_id: str                      # sender phone (E.164 without +)
    contact_name: str = ""
    timestamp: str = ""
    type: MessageType = "unknown"

    text: str = ""                  # text body, caption, or button/list title
    media_id: str = ""              # for image/document/audio/video
    mime_type: str = ""
    filename: str = ""
    is_voice: bool = False

    reply_id: str = ""              # interactive button/list reply id (maps to a flow option)

    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def has_media(self) -> bool:
        return bool(self.media_id)


def parse_inbound(payload: dict[str, Any]) -> list[InboundMessage]:
    """Flatten a raw webhook payload into a list of InboundMessage.

    Status-only callbacks (delivery/read receipts) produce an empty list.
    """
    parsed = WebhookPayload.model_validate(payload)
    out: list[InboundMessage] = []

    for entry in parsed.entry:
        for change in entry.changes:
            value = change.value
            if value is None:
                continue

            name_by_wa: dict[str, str] = {}
            for c in value.contacts:
                if c.wa_id:
                    name_by_wa[c.wa_id] = c.profile.name if c.profile else ""

            for m in value.messages:
                out.append(_flatten_message(m, name_by_wa.get(m.from_, ""), payload_for(m)))

    return out


def parse_statuses(payload: dict[str, Any]) -> list[Status]:
    """Extract delivery/read receipts from a webhook payload."""
    parsed = WebhookPayload.model_validate(payload)
    statuses: list[Status] = []
    for entry in parsed.entry:
        for change in entry.changes:
            if change.value:
                statuses.extend(change.value.statuses)
    return statuses


def payload_for(m: RawMessage) -> dict[str, Any]:
    return m.model_dump(by_alias=True, exclude_none=True)


def _flatten_message(m: RawMessage, contact_name: str, raw: dict[str, Any]) -> InboundMessage:
    msg = InboundMessage(
        message_id=m.id,
        wa_id=m.from_,
        contact_name=contact_name,
        timestamp=m.timestamp,
        type=m.type if m.type in _KNOWN_TYPES else "unknown",  # type: ignore[arg-type]
        raw=raw,
    )

    if m.type == "text" and m.text:
        msg.text = m.text.body
    elif m.type in ("image", "document", "audio", "video", "sticker"):
        media = getattr(m, m.type)
        if media:
            msg.media_id = media.id
            msg.mime_type = media.mime_type
            msg.filename = media.filename
            msg.is_voice = media.voice
            msg.text = media.caption
    elif m.type == "interactive" and m.interactive:
        reply = m.interactive.button_reply or m.interactive.list_reply
        if reply:
            msg.reply_id = reply.id
            msg.text = reply.title
    elif m.type == "button" and m.button:
        msg.reply_id = m.button.payload
        msg.text = m.button.text
    elif m.type == "location" and m.location:
        msg.text = m.location.address or m.location.name

    return msg
