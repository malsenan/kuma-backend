"""Build a BusinessPortfolio from a contact's WhatsApp intake.

Two layers:

1. Deterministic assembly (`build_portfolio`) — pulls the structured answers and
   media the conversation engine already captured and maps them onto the
   schema. No AI, fully testable, runs today.

2. AI enrichment (`extract_with_claude`) — STUB. Reads free-text messages, OCRs
   document/photo uploads, and fills the soft fields (sector, avg ticket,
   online presence, etc.). Wire this to the Claude API once the portfolio
   template is finalized. The intended prompt is in `CLAUDE_EXTRACTION_PROMPT`.

The deterministic layer is intentionally conservative: anything it has to guess
(revenue from a band, tenure from a bucket) is recorded as a review flag.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from portfolio.models import (
    BusinessInfo,
    BusinessPortfolio,
    Completeness,
    CreditNeed,
    DocumentRef,
    FinancialSnapshot,
    MediaRef,
    OwnerInfo,
    SourceData,
)
from whatsapp.store import MessageStore

# --- Flow-step → portfolio mapping -------------------------------------------
# These ids track whatsapp/flows/intake_pt_BR.json. If the flow's step ids
# change, update this map (it is the one coupling point between the two).

STEP_BUSINESS_DESC = "ask_business"
STEP_TENURE = "ask_time_active"
STEP_DOCS = "ask_docs"
STEP_PHOTOS = "ask_photos"
STEP_REVENUE = "ask_revenue"
STEP_CREDIT = "ask_amount"

# Bucket answers → rough numeric midpoints (flagged as inferred when used).
TENURE_MONTHS = {"time_lt1": 6, "time_1to3": 24, "time_gt3": 48}
REVENUE_MIDPOINT_BRL = {"rev_lt2k": 1000.0, "rev_2to5k": 3500.0, "rev_gt5k": 7000.0}


def build_portfolio(
    wa_id: str,
    store: MessageStore,
    lead: Optional[Any] = None,
    use_claude: bool = False,
) -> BusinessPortfolio:
    """Assemble a draft BusinessPortfolio for one contact from the store.

    `lead` (optional) is a leads.Lead — seeds owner/business fields known before
    the chat even started. `use_claude` toggles the (stubbed) AI enrichment.
    """
    contact = store.get_contact(wa_id) or {}
    answers = store.get_answers(wa_id)
    messages = store.inbound_messages(wa_id)

    portfolio = BusinessPortfolio(
        portfolio_id=f"pf_{wa_id}",
        owner=OwnerInfo(
            full_name=_lead_attr(lead, "full_name") or contact.get("name", ""),
            first_name=_lead_attr(lead, "first_name"),
        ),
        business=BusinessInfo(),
        source=SourceData(
            wa_id=wa_id,
            lead_id=contact.get("lead_id", "") or _lead_attr(lead, "lead_id"),
            raw_message_count=len(messages),
        ),
    )

    _apply_business(portfolio, answers, lead)
    _apply_financials(portfolio, answers)
    _apply_credit_need(portfolio, answers, lead)
    _apply_media(portfolio, messages)
    _apply_completeness(portfolio)

    if contact.get("needs_agent"):
        portfolio.review_flags.append("contact requested a human agent")

    if use_claude:
        context = assemble_context(portfolio, messages, answers)
        extract_with_claude(portfolio, context)  # stub — fills soft fields in place

    portfolio.status = "complete" if portfolio.completeness.fraction >= 0.6 else "draft"
    return portfolio


# --- deterministic field population ------------------------------------------

def _apply_business(p: BusinessPortfolio, answers: dict, lead: Optional[Any]) -> None:
    desc = answers.get(STEP_BUSINESS_DESC, {}).get("answer_text", "")
    p.business.description = desc or _lead_attr(lead, "business_type")

    tenure = answers.get(STEP_TENURE, {}).get("answer_id", "")
    if tenure in TENURE_MONTHS:
        p.business.months_active = TENURE_MONTHS[tenure]
        p.review_flags.append(f"tenure inferred from bucket '{tenure}'")


def _apply_financials(p: BusinessPortfolio, answers: dict) -> None:
    rev_id = answers.get(STEP_REVENUE, {}).get("answer_id", "")
    if rev_id:
        p.financials.monthly_revenue_band = rev_id
    if rev_id in REVENUE_MIDPOINT_BRL:
        p.financials.monthly_revenue_brl = REVENUE_MIDPOINT_BRL[rev_id]
        p.review_flags.append(f"revenue estimated from band '{rev_id}'")


def _apply_credit_need(p: BusinessPortfolio, answers: dict, lead: Optional[Any]) -> None:
    raw = answers.get(STEP_CREDIT, {}).get("answer_text", "")
    if raw:
        amount = _parse_brl(raw)
        if amount is not None:
            p.credit_need.amount_requested_brl = amount
        p.credit_need.purpose = raw
    elif lead is not None:
        p.credit_need.purpose = _lead_attr(lead, "money_use")


def _apply_media(p: BusinessPortfolio, messages: list[dict]) -> None:
    for m in messages:
        path = m.get("media_path") or ""
        if not path:
            continue
        step = m.get("step") or ""
        caption = m.get("text") or ""
        if step == STEP_DOCS:
            p.documents.append(DocumentRef(kind="other", file_path=path, extracted_text=""))
        elif step == STEP_PHOTOS:
            p.photos.append(MediaRef(kind="product", file_path=path, caption=caption))
        else:
            # Media sent outside a collection step — keep it, flag for triage.
            p.photos.append(MediaRef(kind="other", file_path=path, caption=caption))


def _apply_completeness(p: BusinessPortfolio) -> None:
    p.completeness = Completeness(
        has_business_description=bool(p.business.description),
        has_financials=p.financials.monthly_revenue_brl is not None
        or bool(p.financials.monthly_revenue_band),
        has_documents=bool(p.documents),
        has_photos=bool(p.photos),
        has_online_presence=bool(p.online.instagram_handle or p.online.website),
    )
    if not p.documents:
        p.review_flags.append("no documents received")
    if not p.photos:
        p.review_flags.append("no photos received")


# --- helpers -----------------------------------------------------------------

def _lead_attr(lead: Optional[Any], name: str) -> str:
    return str(getattr(lead, name, "") or "") if lead is not None else ""


def _parse_brl(text: str) -> Optional[float]:
    """Pull a BRL amount out of free text. '1.500', 'R$ 2.000,50', '800' → float."""
    match = re.search(r"(\d[\d.\s]*(?:,\d{1,2})?)", text)
    if not match:
        return None
    token = match.group(1).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(token)
    except ValueError:
        return None


# --- AI enrichment (STUB) ----------------------------------------------------

CLAUDE_EXTRACTION_PROMPT = """\
You are building a credit portfolio for an informal Brazilian entrepreneur from \
their WhatsApp messages. You receive: their free-text messages (Portuguese), and \
OCR text from any documents/photos they sent.

Extract and return ONLY this JSON (omit fields you cannot determine):
{
  "business": {"sector": "...", "is_mei": true/false, "channels": ["..."]},
  "financials": {"avg_ticket_brl": 0, "payment_methods": ["pix","cash","card"], "has_bank_account": true/false},
  "online": {"instagram_handle": "@...", "instagram_followers": 0},
  "documents": [{"kind": "id|mei_certificate|bank_statement|proof_address", "extracted_text": "..."}]
}

Rules:
- Never infer gender, race, or address as a scoring signal (LGPD).
- Sector must be one of: food, beauty, retail, services, crafts, other.
- If unsure, leave the field out rather than guessing.
"""


def assemble_context(p: BusinessPortfolio, messages: list[dict], answers: dict) -> str:
    """Concatenate everything we have on a contact into one prompt context."""
    lines: list[str] = []
    lines.append(f"# Contact {p.source.wa_id} ({p.owner.full_name})")
    lines.append("\n## Free-text messages")
    for m in messages:
        if m.get("type") == "text" and m.get("text"):
            lines.append(f"- {m['text']}")
    lines.append("\n## Structured answers")
    for step, a in answers.items():
        val = a.get("answer_text") or a.get("answer_id") or f"{a.get('media_count', 0)} files"
        lines.append(f"- {step}: {val}")
    lines.append("\n## Uploaded files (paths; OCR pending)")
    for d in p.documents:
        lines.append(f"- document: {d.file_path}")
    for ph in p.photos:
        lines.append(f"- photo: {ph.file_path}")
    return "\n".join(lines)


def extract_with_claude(portfolio: BusinessPortfolio, context: str) -> None:
    """STUB — enrich the portfolio's soft fields using Claude.

    Intended implementation:
      1. OCR each document/photo (Claude vision or a dedicated OCR pass) and set
         DocumentRef.extracted_text.
      2. Send CLAUDE_EXTRACTION_PROMPT + `context` (+ images) to the Claude API.
      3. Merge the returned JSON into `portfolio` without overwriting any
         user-stated value with an inferred one.

    Use the latest model (claude-opus-4-8 for quality, claude-haiku-4-5 for
    cheap/fast). Left unimplemented until the portfolio template is finalized.
    """
    portfolio.review_flags.append("AI enrichment skipped (extract_with_claude is a stub)")
