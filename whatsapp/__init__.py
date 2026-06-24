"""WhatsApp Cloud API intake for Lumora.

Public surface:
    WhatsAppClient        — send messages / download media (whatsapp.client)
    MessageStore          — SQLite persistence (whatsapp.store)
    ConversationEngine    — runs the declarative intake flow (whatsapp.conversation)
    router                — FastAPI webhook router (whatsapp.webhook)
    parse_inbound         — flatten a raw webhook payload (whatsapp.models)
"""

from whatsapp.client import WhatsAppClient, WhatsAppError
from whatsapp.config import WhatsAppSettings, get_settings
from whatsapp.conversation import ConversationEngine
from whatsapp.models import InboundMessage, parse_inbound
from whatsapp.store import MessageStore

__all__ = [
    "WhatsAppClient",
    "WhatsAppError",
    "WhatsAppSettings",
    "get_settings",
    "ConversationEngine",
    "InboundMessage",
    "parse_inbound",
    "MessageStore",
]
