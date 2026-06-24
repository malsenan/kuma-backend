"""Shared test fixtures for the WhatsApp intake + portfolio tests."""

from __future__ import annotations

import pytest

from whatsapp.conversation import ConversationEngine
from whatsapp.models import InboundMessage
from whatsapp.store import MessageStore


class FakeClient:
    """Records outbound calls instead of hitting the Graph API."""

    def __init__(self):
        self.sent: list[tuple] = []
        self.read: list[str] = []

    def send_text(self, to, body, preview_url=False):
        self.sent.append(("text", to, body, None))
        return f"mid-{len(self.sent)}"

    def send_buttons(self, to, body, buttons, header="", footer=""):
        self.sent.append(("buttons", to, body, list(buttons)))
        return f"mid-{len(self.sent)}"

    def send_list(self, to, body, button_text, rows, header="", footer=""):
        self.sent.append(("list", to, body, list(rows)))
        return f"mid-{len(self.sent)}"

    def send_template(self, to, name, language="pt_BR", components=None):
        self.sent.append(("template", to, name, None))
        return f"mid-{len(self.sent)}"

    def mark_read(self, message_id):
        self.read.append(message_id)

    def download_media(self, media_id):
        return b"fake-media-bytes"

    def get_media_url(self, media_id):
        return "https://example.test/media"

    # convenience
    @property
    def kinds(self):
        return [s[0] for s in self.sent]

    @property
    def last(self):
        return self.sent[-1]


@pytest.fixture
def store(tmp_path):
    s = MessageStore(tmp_path / "messages.db")
    yield s
    s.close()


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def engine(store, client):
    return ConversationEngine(store, client)


# --- inbound message factories ----------------------------------------------

def text_msg(wa_id, body, mid, name="Maria Silva"):
    return InboundMessage(message_id=mid, wa_id=wa_id, contact_name=name, type="text", text=body)


def button_msg(wa_id, reply_id, title, mid, name="Maria Silva"):
    return InboundMessage(
        message_id=mid, wa_id=wa_id, contact_name=name,
        type="interactive", reply_id=reply_id, text=title,
    )


def image_msg(wa_id, media_id, mid, name="Maria Silva"):
    return InboundMessage(
        message_id=mid, wa_id=wa_id, contact_name=name,
        type="image", media_id=media_id, mime_type="image/jpeg",
    )
