"""FastAPI router for the WhatsApp Cloud API webhook.

Mounted by `api/main.py` at the app root, exposing:

  GET  /webhook   — Meta verification handshake (echo hub.challenge)
  POST /webhook   — receive inbound messages / status callbacks

The POST handler validates Meta's signature, returns 200 immediately, and does
the actual conversation work in a background task so Meta never times out and
retries (its window is short).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from whatsapp.config import get_settings
from whatsapp.conversation import ConversationEngine, get_engine
from whatsapp.models import InboundMessage, parse_inbound, parse_statuses
from whatsapp.signature import verify_signature

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp"])


@router.get("/webhook")
def verify(request: Request) -> PlainTextResponse:
    """Meta calls this once when you register/verify the webhook URL."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    settings = get_settings()
    if mode == "subscribe" and token and token == settings.verify_token:
        logger.info("Webhook verified by Meta")
        return PlainTextResponse(challenge)
    logger.warning("Webhook verification failed (mode=%s)", mode)
    return PlainTextResponse("verification failed", status_code=403)


@router.post("/webhook")
async def receive(request: Request, background: BackgroundTasks) -> JSONResponse:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    settings = get_settings()
    if not verify_signature(settings.app_secret, body, signature):
        logger.warning("Rejected webhook: bad signature")
        return JSONResponse({"status": "forbidden"}, status_code=403)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return JSONResponse({"status": "ignored"}, status_code=200)

    # Log delivery/read receipts but take no action on them.
    for st in parse_statuses(payload):
        logger.debug("Status %s for %s", st.status, st.id)

    messages = parse_inbound(payload)
    if messages:
        engine = get_engine()
        for msg in messages:
            background.add_task(_process_one, engine, msg)

    # Always 200 so Meta does not retry.
    return JSONResponse({"status": "received", "messages": len(messages)}, status_code=200)


def _process_one(engine: ConversationEngine, msg: InboundMessage) -> None:
    """Runs in the background after the 200 is returned."""
    try:
        engine.client.mark_read(msg.message_id)
    except Exception:  # noqa: BLE001
        logger.debug("mark_read failed for %s", msg.message_id)
    try:
        engine.handle(msg)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to handle message %s from %s", msg.message_id, msg.wa_id)
