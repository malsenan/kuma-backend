"""SQLite-backed store for WhatsApp conversations.

Everything inbound is persisted raw (the full Meta message JSON) plus a few
flattened columns for convenient querying. This satisfies the "load their
responses as raw data or some structured thing" requirement and gives the
portfolio builder a single place to read from.

Stdlib sqlite3 only — no ORM, no migration framework. For a pilot this is
plenty; swap for Postgres later behind the same method surface.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from whatsapp.models import InboundMessage

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    wa_id          TEXT PRIMARY KEY,
    name           TEXT,
    lead_id        TEXT,
    current_step   TEXT,
    needs_agent    INTEGER NOT NULL DEFAULT 0,
    opted_out      INTEGER NOT NULL DEFAULT 0,
    first_seen     TEXT,
    last_seen      TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    message_id   TEXT PRIMARY KEY,
    wa_id        TEXT NOT NULL,
    direction    TEXT NOT NULL,             -- 'in' | 'out'
    type         TEXT,
    text         TEXT,
    reply_id     TEXT,
    media_id     TEXT,
    media_path   TEXT,
    mime_type    TEXT,
    step         TEXT,                     -- flow step the contact was on when received
    timestamp    TEXT,
    created_at   TEXT NOT NULL,
    raw          TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_wa_id ON messages (wa_id);

CREATE TABLE IF NOT EXISTS answers (
    wa_id        TEXT NOT NULL,
    step         TEXT NOT NULL,
    answer_id    TEXT,                      -- button/list reply id, if any
    answer_text  TEXT,                      -- free text or button title
    media_count  INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (wa_id, step)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MessageStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + a lock: FastAPI may call from threadpool workers.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- contacts -------------------------------------------------------------

    def upsert_contact(self, wa_id: str, name: str = "", lead_id: str = "") -> None:
        now = _now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO contacts (wa_id, name, lead_id, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(wa_id) DO UPDATE SET
                    name      = COALESCE(NULLIF(excluded.name, ''), contacts.name),
                    lead_id   = COALESCE(NULLIF(excluded.lead_id, ''), contacts.lead_id),
                    last_seen = excluded.last_seen
                """,
                (wa_id, name, lead_id, now, now),
            )
            self._conn.commit()

    def get_contact(self, wa_id: str) -> Optional[dict[str, Any]]:
        cur = self._conn.execute("SELECT * FROM contacts WHERE wa_id = ?", (wa_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_step(self, wa_id: str) -> Optional[str]:
        contact = self.get_contact(wa_id)
        return contact.get("current_step") if contact else None

    def set_step(self, wa_id: str, step: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE contacts SET current_step = ?, last_seen = ? WHERE wa_id = ?",
                (step, _now(), wa_id),
            )
            self._conn.commit()

    def flag_agent(self, wa_id: str, needs: bool = True) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE contacts SET needs_agent = ? WHERE wa_id = ?",
                (1 if needs else 0, wa_id),
            )
            self._conn.commit()

    def set_opted_out(self, wa_id: str, opted_out: bool = True) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE contacts SET opted_out = ? WHERE wa_id = ?",
                (1 if opted_out else 0, wa_id),
            )
            self._conn.commit()

    def contacts_needing_agent(self) -> list[dict[str, Any]]:
        cur = self._conn.execute("SELECT * FROM contacts WHERE needs_agent = 1 ORDER BY last_seen DESC")
        return [dict(r) for r in cur.fetchall()]

    def all_contacts(self) -> list[dict[str, Any]]:
        cur = self._conn.execute("SELECT * FROM contacts ORDER BY last_seen DESC")
        return [dict(r) for r in cur.fetchall()]

    # -- messages -------------------------------------------------------------

    def save_inbound(self, msg: InboundMessage, media_path: str = "", step: str = "") -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO messages
                    (message_id, wa_id, direction, type, text, reply_id,
                     media_id, media_path, mime_type, step, timestamp, created_at, raw)
                VALUES (?, ?, 'in', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg.message_id, msg.wa_id, msg.type, msg.text, msg.reply_id,
                    msg.media_id, media_path, msg.mime_type, step, msg.timestamp,
                    _now(), json.dumps(msg.raw, ensure_ascii=False),
                ),
            )
            self._conn.commit()

    def save_outbound(self, wa_id: str, type_: str, text: str, message_id: str = "") -> None:
        # Outbound messages without an id (e.g. send failed) still get logged
        # with a synthetic key so nothing is silently dropped.
        key = message_id or f"out:{wa_id}:{_now()}"
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO messages
                    (message_id, wa_id, direction, type, text, created_at)
                VALUES (?, ?, 'out', ?, ?, ?)
                """,
                (key, wa_id, type_, text, _now()),
            )
            self._conn.commit()

    def conversation(self, wa_id: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM messages WHERE wa_id = ? ORDER BY created_at ASC", (wa_id,)
        )
        return [dict(r) for r in cur.fetchall()]

    def inbound_messages(self, wa_id: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM messages WHERE wa_id = ? AND direction = 'in' ORDER BY created_at ASC",
            (wa_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    # -- answers (structured flow responses) ----------------------------------

    def save_answer(self, wa_id: str, step: str, answer_id: str = "",
                    answer_text: str = "", media_increment: int = 0) -> None:
        """Record (or update) the answer a contact gave at a given flow step.

        `media_increment` adds to the running count of media uploaded at this
        step (used by collect_media steps).
        """
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO answers (wa_id, step, answer_id, answer_text, media_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(wa_id, step) DO UPDATE SET
                    answer_id   = COALESCE(NULLIF(excluded.answer_id, ''), answers.answer_id),
                    answer_text = COALESCE(NULLIF(excluded.answer_text, ''), answers.answer_text),
                    media_count = answers.media_count + excluded.media_count,
                    updated_at  = excluded.updated_at
                """,
                (wa_id, step, answer_id, answer_text, media_increment, _now()),
            )
            self._conn.commit()

    def get_answers(self, wa_id: str) -> dict[str, dict[str, Any]]:
        """Return {step: {answer_id, answer_text, media_count}} for a contact."""
        cur = self._conn.execute("SELECT * FROM answers WHERE wa_id = ?", (wa_id,))
        return {r["step"]: dict(r) for r in cur.fetchall()}

    def get_media_count(self, wa_id: str, step: str) -> int:
        cur = self._conn.execute(
            "SELECT media_count FROM answers WHERE wa_id = ? AND step = ?", (wa_id, step)
        )
        row = cur.fetchone()
        return row["media_count"] if row else 0


_store: Optional[MessageStore] = None


def get_store(db_path: Path | str | None = None) -> MessageStore:
    """Cached store singleton (used by the webhook)."""
    global _store
    if _store is None:
        from whatsapp.config import get_settings
        _store = MessageStore(db_path or get_settings().db_path)
    return _store
