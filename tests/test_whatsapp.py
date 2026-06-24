"""Tests for WhatsApp webhook parsing, signature checks, and the flow engine."""

from __future__ import annotations

import pytest

from whatsapp.client import WhatsAppClient, WhatsAppError
from whatsapp.config import WhatsAppSettings
from whatsapp.models import parse_inbound, parse_statuses
from whatsapp.signature import compute_signature, verify_signature

from tests.conftest import button_msg, image_msg, text_msg


# --- payload parsing ---------------------------------------------------------

def _text_payload(wa_id="5511999990000", body="oi", mid="wamid.1"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "1555", "phone_number_id": "PNID"},
                    "contacts": [{"wa_id": wa_id, "profile": {"name": "Maria"}}],
                    "messages": [{
                        "from": wa_id, "id": mid, "timestamp": "1700000000",
                        "type": "text", "text": {"body": body},
                    }],
                },
            }],
        }],
    }


def test_parse_inbound_text():
    msgs = parse_inbound(_text_payload())
    assert len(msgs) == 1
    m = msgs[0]
    assert m.wa_id == "5511999990000"
    assert m.type == "text"
    assert m.text == "oi"
    assert m.contact_name == "Maria"


def test_parse_inbound_interactive_button():
    payload = _text_payload()
    payload["entry"][0]["changes"][0]["value"]["messages"][0] = {
        "from": "5511999990000", "id": "wamid.2", "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"id": "consent_yes", "title": "Sim"}},
    }
    m = parse_inbound(payload)[0]
    assert m.type == "interactive"
    assert m.reply_id == "consent_yes"
    assert m.text == "Sim"


def test_parse_inbound_image():
    payload = _text_payload()
    payload["entry"][0]["changes"][0]["value"]["messages"][0] = {
        "from": "5511999990000", "id": "wamid.3", "type": "image",
        "image": {"id": "MEDIA123", "mime_type": "image/jpeg", "caption": "minha loja"},
    }
    m = parse_inbound(payload)[0]
    assert m.type == "image"
    assert m.media_id == "MEDIA123"
    assert m.has_media
    assert m.text == "minha loja"


def test_status_only_payload_yields_no_messages():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"statuses": [
            {"id": "wamid.x", "status": "delivered", "recipient_id": "5511999990000"}
        ]}}]}],
    }
    assert parse_inbound(payload) == []
    statuses = parse_statuses(payload)
    assert len(statuses) == 1 and statuses[0].status == "delivered"


def test_malformed_payload_does_not_raise():
    assert parse_inbound({"object": "x", "entry": []}) == []
    assert parse_inbound({}) == []


# --- signature ---------------------------------------------------------------

def test_signature_roundtrip():
    secret, body = "s3cr3t", b'{"hello":"world"}'
    header = compute_signature(secret, body)
    assert header.startswith("sha256=")
    assert verify_signature(secret, body, header)
    assert not verify_signature(secret, body, "sha256=deadbeef")


def test_signature_skipped_when_no_secret():
    # Empty secret = local dev; verification is skipped (returns True).
    assert verify_signature("", b"anything", None)


# --- credentials guard -------------------------------------------------------

def test_client_refuses_to_send_when_unconfigured():
    # No token → a clean WhatsAppError, NOT a low-level httpx error, and no
    # network call is attempted.
    client = WhatsAppClient(WhatsAppSettings(token="", phone_number_id=""))
    with pytest.raises(WhatsAppError) as exc:
        client.send_text("5511999990000", "ola")
    assert "WHATSAPP_TOKEN" in str(exc.value)


def test_client_refuses_media_when_unconfigured():
    client = WhatsAppClient(WhatsAppSettings(token="", phone_number_id=""))
    with pytest.raises(WhatsAppError):
        client.download_media("MEDIA123")


# --- conversation engine -----------------------------------------------------

def test_full_intake_flow(engine, store, client):
    wa = "5511999990000"

    engine.handle(text_msg(wa, "oi", "m1"))
    assert store.get_step(wa) == "welcome"
    assert client.last[0] == "buttons"

    engine.handle(button_msg(wa, "consent_yes", "Sim, vamos", "m2"))
    assert store.get_step(wa) == "ask_business"

    engine.handle(text_msg(wa, "Vendo marmitas e doces", "m3"))
    assert store.get_step(wa) == "ask_time_active"

    engine.handle(button_msg(wa, "time_1to3", "1 a 3 anos", "m4"))
    assert store.get_step(wa) == "ask_docs"

    engine.handle(image_msg(wa, "media1", "m5"))
    assert store.get_step(wa) == "ask_docs"          # still collecting
    assert store.get_media_count(wa, "ask_docs") == 1

    engine.handle(button_msg(wa, "docs_done", "Já enviei", "m6"))
    assert store.get_step(wa) == "ask_photos"

    engine.handle(image_msg(wa, "media2", "m7"))
    engine.handle(button_msg(wa, "photos_done", "Já enviei", "m8"))
    assert store.get_step(wa) == "ask_revenue"

    engine.handle(button_msg(wa, "rev_2to5k", "R$2 a 5 mil", "m9"))
    assert store.get_step(wa) == "ask_amount"

    engine.handle(text_msg(wa, "R$1.500 para estoque", "m10"))
    assert store.get_step(wa) == "thanks"

    answers = store.get_answers(wa)
    assert answers["ask_business"]["answer_text"] == "Vendo marmitas e doces"
    assert answers["ask_time_active"]["answer_id"] == "time_1to3"
    assert answers["ask_revenue"]["answer_id"] == "rev_2to5k"
    assert answers["ask_amount"]["answer_text"] == "R$1.500 para estoque"
    assert store.get_media_count(wa, "ask_docs") == 1
    assert store.get_media_count(wa, "ask_photos") == 1


def test_media_saved_to_disk(engine, store, client, tmp_path):
    wa = "5511999991111"
    engine.handle(text_msg(wa, "oi", "n1"))
    engine.handle(button_msg(wa, "consent_yes", "Sim", "n2"))
    engine.handle(text_msg(wa, "Salão", "n3"))
    engine.handle(button_msg(wa, "time_gt3", "Mais de 3 anos", "n4"))
    engine.handle(image_msg(wa, "mediaX", "n5"))

    media_dir = store.db_path.parent / "media" / wa
    files = list(media_dir.glob("*"))
    assert len(files) == 1
    assert files[0].read_bytes() == b"fake-media-bytes"


def test_agent_keyword_triggers_handoff(engine, store):
    wa = "5511888887777"
    engine.handle(text_msg(wa, "oi", "a1"))
    engine.handle(text_msg(wa, "quero falar com um atendente", "a2"))
    contact = store.get_contact(wa)
    assert contact["needs_agent"] == 1
    assert store.get_step(wa) == "handoff"
    assert store.contacts_needing_agent()


def test_stop_keyword_opts_out_and_silences(engine, store, client):
    wa = "5511777776666"
    engine.handle(text_msg(wa, "oi", "s1"))
    engine.handle(text_msg(wa, "sair", "s2"))
    assert store.get_contact(wa)["opted_out"] == 1

    before = len(client.sent)
    engine.handle(text_msg(wa, "oi de novo", "s3"))
    assert len(client.sent) == before          # stays silent after opt-out


def test_wrong_input_re_prompts_buttons(engine, store, client):
    wa = "5511666665555"
    engine.handle(text_msg(wa, "oi", "w1"))            # welcome buttons
    n = len(client.sent)
    engine.handle(text_msg(wa, "blah blah", "w2"))     # text instead of tapping
    assert store.get_step(wa) == "welcome"             # did not advance
    assert client.sent[-1][0] == "buttons"             # re-offered buttons
    assert len(client.sent) == n + 1
