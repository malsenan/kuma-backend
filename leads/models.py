"""Lead model — one row from the Meta lead-ad CSV exports, normalized."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Lead(BaseModel):
    """A single lead from the campaign CSVs, with a cleaned WhatsApp number.

    Survey fields keep the raw Portuguese answer values (snake_cased by Meta).
    Demographic-ish fields (date_of_birth) are retained for contact/display but
    must never be used as scoring features (LGPD).
    """

    lead_id: str = ""
    created_time: str = ""
    segment: str = ""                 # "negativados" | "taxa" (campaign segment)
    platform: str = ""                # "ig" | "fb"

    full_name: str = ""
    first_name: str = ""
    email: str = ""
    date_of_birth: str = ""

    # Phone
    whatsapp_raw: str = ""
    phone_e164: str = ""              # "+55DDXXXXXXXXX" when parseable, else ""
    phone_valid: bool = False
    phone_needs_review: bool = False  # parsed but low confidence (e.g. 9th digit inferred)

    # Business + survey answers (raw values)
    business_type: str = ""
    where_seek_money: str = ""        # quando precisa de dinheiro, onde busca
    amount_needed: str = ""           # quanto costuma precisar
    money_use: str = ""               # para o que mais usa
    biggest_difficulty: str = ""      # maior dificuldade ao pegar empréstimo
    app_likelihood: str = ""          # chance de usar um app de crédito via Pix

    notes: list[str] = Field(default_factory=list)  # parsing warnings
