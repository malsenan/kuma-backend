"""Conversation engine — runs a declarative flow over WhatsApp.

The flow itself lives in `whatsapp/flows/*.json` so it can be edited without
touching code (hand this off to Sandra). This engine is the runtime that:

  * tracks each contact's current step in the message store,
  * downloads and saves any media the user sends,
  * records structured answers,
  * sends the next prompt (text / reply buttons / media request),
  * handles global interrupts ("atendente" → human handoff, "sair" → opt out).

The shipped flow (`intake_pt_BR.json`) is a PLACEHOLDER. When Sandra delivers
the approved script, only the JSON changes — this engine stays the same.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any, Optional

from whatsapp.client import WhatsAppClient, WhatsAppError
from whatsapp.models import InboundMessage
from whatsapp.store import MessageStore

logger = logging.getLogger(__name__)

DEFAULT_FLOW = Path(__file__).parent / "flows" / "intake_pt_BR.json"

# Words that interrupt the flow regardless of current step. Matched against the
# set of words in the message (not the whole string), so "falar com atendente"
# triggers handoff. Kept narrow to avoid false positives.
AGENT_KEYWORDS = {"atendente", "humano", "atendimento", "representante"}
STOP_KEYWORDS = {"sair", "parar", "cancelar", "stop", "descadastrar"}

_MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "video/mp4": ".mp4",
}


class _SafeDict(dict):
    """format_map helper: leave unknown {placeholders} blank instead of raising."""

    def __missing__(self, key: str) -> str:  # noqa: D401
        return ""


class ConversationEngine:
    def __init__(self, store: MessageStore, client: WhatsAppClient,
                 flow_path: Path | str = DEFAULT_FLOW):
        self.store = store
        self.client = client
        self.flow = json.loads(Path(flow_path).read_text(encoding="utf-8"))
        self.steps: dict[str, Any] = self.flow["steps"]
        self.start: str = self.flow["start"]

    # -- public entry point ---------------------------------------------------

    def handle(self, msg: InboundMessage) -> None:
        """Process one inbound message end-to-end. Never raises on flow logic."""
        wa_id = msg.wa_id
        self.store.upsert_contact(wa_id, msg.contact_name)

        # Capture the step the contact is on *before* processing, so media is
        # attributed to the question it answers (docs vs photos, etc.).
        current_step = self.store.get_step(wa_id) or ""
        media_path = self._save_media(msg) if msg.has_media else ""
        self.store.save_inbound(msg, media_path, step=current_step)

        contact = self.store.get_contact(wa_id)
        if contact and contact.get("opted_out"):
            return  # respect opt-out — stay silent

        # Global interrupts take priority over the current step.
        if msg.type == "text":
            words = set(re.findall(r"[a-zà-ÿ]+", msg.text.lower()))
            if words & STOP_KEYWORDS:
                self.store.set_opted_out(wa_id, True)
                self._send_text(wa_id, "Tudo bem, não vou mais te escrever. Quando quiser voltar, é só mandar uma mensagem. 💜")
                return
            if words & AGENT_KEYWORDS:
                self._enter_step(wa_id, "handoff", msg)
                return

        if not current_step:
            # First time we hear from this contact → greet.
            self._enter_step(wa_id, self.start, msg)
            return

        step = self.steps.get(current_step)
        if step is None:
            logger.warning("Contact %s on unknown step %s; restarting", wa_id, current_step)
            self._enter_step(wa_id, self.start, msg)
            return

        self._process_step(wa_id, current_step, step, msg)

    # -- step processing ------------------------------------------------------

    def _process_step(self, wa_id: str, step_id: str, step: dict[str, Any], msg: InboundMessage) -> None:
        stype = step.get("type")

        if stype == "buttons":
            self._handle_buttons(wa_id, step_id, step, msg)
        elif stype == "text_input":
            self._handle_text_input(wa_id, step_id, step, msg)
        elif stype == "collect_media":
            self._handle_collect_media(wa_id, step_id, step, msg)
        elif stype == "terminal":
            self._handle_terminal(wa_id, step_id, step, msg)
        else:
            logger.warning("Unknown step type %r at %s", stype, step_id)

    def _handle_buttons(self, wa_id: str, step_id: str, step: dict[str, Any], msg: InboundMessage) -> None:
        chosen = next((b for b in step["buttons"] if b["id"] == msg.reply_id), None)
        if chosen is None:
            # They typed something instead of tapping — re-offer the buttons.
            self._send_step_prompt(wa_id, step_id, step, msg)
            return
        self.store.save_answer(wa_id, step_id, answer_id=chosen["id"], answer_text=chosen.get("title", ""))
        self._enter_step(wa_id, chosen["next"], msg)

    def _handle_text_input(self, wa_id: str, step_id: str, step: dict[str, Any], msg: InboundMessage) -> None:
        if not msg.text.strip():
            self._send_step_prompt(wa_id, step_id, step, msg)
            return
        self.store.save_answer(wa_id, step_id, answer_text=msg.text.strip())
        self._enter_step(wa_id, step["next"], msg)

    def _handle_collect_media(self, wa_id: str, step_id: str, step: dict[str, Any], msg: InboundMessage) -> None:
        advance = step.get("advance_button", {})
        skip = step.get("skip_button", {})

        if msg.reply_id and msg.reply_id == skip.get("id"):
            self.store.save_answer(wa_id, step_id, answer_id="skipped")
            self._enter_step(wa_id, step["next"], msg)
            return

        if msg.reply_id and msg.reply_id == advance.get("id"):
            if self.store.get_media_count(wa_id, step_id) >= int(step.get("min_items", 1)):
                self._enter_step(wa_id, step["next"], msg)
            else:
                self._send_text(wa_id, "Ainda não recebi nenhum arquivo. Pode enviar pelo menos um, ou tocar em pular. 🙏")
            return

        if msg.has_media:
            self.store.save_answer(wa_id, step_id, media_increment=1)
            # Keep a tappable advance/skip button in front of the user.
            self._send_advance_buttons(wa_id, "Recebi 📎 Pode enviar mais ou seguir.", advance, skip)
            return

        # Free text while we expect media → gentle nudge with the buttons.
        self._send_step_prompt(wa_id, step_id, step, msg)

    def _handle_terminal(self, wa_id: str, step_id: str, step: dict[str, Any], msg: InboundMessage) -> None:
        # Conversation already ended. A greeting restarts it; anything else gets
        # a light acknowledgement so the user isn't left hanging.
        if msg.type == "text" and msg.text.strip().lower() in {"oi", "olá", "ola", "menu", "começar", "comecar"}:
            self._enter_step(wa_id, self.start, msg)
        else:
            self._send_text(wa_id, "Já recebemos suas informações e nossa equipe vai te retornar por aqui. 💜")

    # -- entering / sending ---------------------------------------------------

    def _enter_step(self, wa_id: str, step_id: str, msg: InboundMessage) -> None:
        step = self.steps.get(step_id)
        if step is None:
            logger.error("Flow points to missing step %s", step_id)
            return
        self.store.set_step(wa_id, step_id)
        self._send_step_prompt(wa_id, step_id, step, msg)
        if step.get("type") == "terminal" and step.get("flag") == "needs_agent":
            self.store.flag_agent(wa_id, True)

    def _send_step_prompt(self, wa_id: str, step_id: str, step: dict[str, Any], msg: InboundMessage) -> None:
        text = self._render(step.get("text", ""), msg)
        stype = step.get("type")

        if stype == "buttons":
            buttons = [(b["id"], b["title"]) for b in step["buttons"]]
            self._send_buttons(wa_id, text, buttons)
        elif stype == "collect_media":
            self._send_advance_buttons(wa_id, text, step.get("advance_button", {}), step.get("skip_button", {}))
        else:  # text_input, terminal
            self._send_text(wa_id, text)

    def _send_advance_buttons(self, wa_id: str, text: str, advance: dict, skip: dict) -> None:
        buttons = []
        if advance:
            buttons.append((advance["id"], advance["title"]))
        if skip:
            buttons.append((skip["id"], skip["title"]))
        if buttons:
            self._send_buttons(wa_id, text, buttons)
        else:
            self._send_text(wa_id, text)

    # -- thin client wrappers (also log outbound to the store) ----------------

    def _send_text(self, wa_id: str, text: str) -> None:
        mid = self._safe_send(lambda: self.client.send_text(wa_id, text))
        self.store.save_outbound(wa_id, "text", text, mid)

    def _send_buttons(self, wa_id: str, text: str, buttons: list[tuple[str, str]]) -> None:
        mid = self._safe_send(lambda: self.client.send_buttons(wa_id, text, buttons))
        self.store.save_outbound(wa_id, "interactive", text, mid)

    @staticmethod
    def _safe_send(fn) -> str:
        try:
            return fn() or ""
        except WhatsAppError as e:
            # Expected, handled condition (not configured, Graph API error) —
            # one concise line, no stack trace.
            logger.warning("WhatsApp send skipped: %s", e)
            return ""
        except Exception:  # noqa: BLE001 — never let a send failure crash the webhook
            logger.exception("Unexpected error sending WhatsApp message")
            return ""

    # -- helpers --------------------------------------------------------------

    def _render(self, text: str, msg: InboundMessage) -> str:
        first_name = (msg.contact_name or "").split(" ")[0] if msg.contact_name else ""
        return text.format_map(_SafeDict(first_name=first_name, name=msg.contact_name))

    def _save_media(self, msg: InboundMessage) -> str:
        """Download media bytes and write them under data/media/<wa_id>/. Best effort."""
        try:
            data = self.client.download_media(msg.media_id)
        except Exception:  # noqa: BLE001
            logger.exception("Could not download media %s", msg.media_id)
            return ""
        # Prefer the original filename for documents; otherwise derive an
        # extension from the mime type.
        if msg.filename:
            fname = f"{msg.message_id}_{msg.filename}"
        else:
            ext = ""
            if msg.mime_type:
                base = msg.mime_type.split(";")[0].strip()
                ext = _MIME_EXT.get(base) or mimetypes.guess_extension(base) or ""
            fname = f"{msg.message_id}{ext}"
        out_dir = self.store.db_path.parent / "media" / msg.wa_id
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / fname
        path.write_bytes(data)
        logger.info("Saved media %s (%d bytes)", path, len(data))
        return str(path)


_engine: Optional[ConversationEngine] = None


def get_engine() -> ConversationEngine:
    """Cached engine singleton wired to the configured store + client."""
    global _engine
    if _engine is None:
        from whatsapp.store import get_store
        _engine = ConversationEngine(get_store(), WhatsAppClient())
    return _engine
