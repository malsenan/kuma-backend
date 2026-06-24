"""BusinessPortfolio schema — the structured output of Deliverable 2.

This is the object an AI pass produces from everything a user sent over
WhatsApp (text, photos, documents). It is the input to the scoring step
(Deliverable 3).

The field set is PROVISIONAL — it is a sensible first draft drawn from the lead
data and the intake flow, to be reconciled with Sandra's portfolio template
when it arrives. Treat additions/renames as expected.

LGPD: demographic fields here (city, state, age) exist for display, contact, and
bias monitoring only. They must never be passed to a scoring function as features.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FieldConfidence(str, Enum):
    """How a field was populated — drives review and the scoring confidence."""

    stated = "stated"          # user said it directly
    inferred = "inferred"      # model inferred from context/images
    document = "document"      # read from an uploaded document
    missing = "missing"


class OwnerInfo(BaseModel):
    full_name: str = ""
    first_name: str = ""
    # Display / bias-monitoring only — never a scoring feature.
    city: str = ""
    state: str = ""
    age: Optional[int] = None


class BusinessInfo(BaseModel):
    name: str = ""
    description: str = ""               # free-text "what I sell/do"
    sector: str = ""                    # normalized: food, beauty, retail, services, crafts, ...
    is_mei: Optional[bool] = None
    months_active: Optional[int] = None
    channels: list[str] = Field(default_factory=list)   # ["physical","instagram","whatsapp",...]


class FinancialSnapshot(BaseModel):
    """Self-reported + document-derived financials. Loosely structured on purpose."""

    monthly_revenue_brl: Optional[float] = None
    monthly_revenue_band: str = ""      # e.g. "rev_2to5k" from the flow
    monthly_costs_brl: Optional[float] = None
    avg_ticket_brl: Optional[float] = None
    payment_methods: list[str] = Field(default_factory=list)   # ["pix","cash","card"]
    has_bank_account: Optional[bool] = None


class DocumentRef(BaseModel):
    kind: str                           # "id" | "mei_certificate" | "bank_statement" | "proof_address" | "other"
    file_path: str = ""
    status: str = "received"            # "received" | "verified" | "rejected"
    extracted_text: str = ""            # OCR result, if any


class MediaRef(BaseModel):
    kind: str                           # "storefront" | "product" | "owner" | "other"
    file_path: str = ""
    caption: str = ""


class OnlinePresence(BaseModel):
    instagram_handle: str = ""
    instagram_followers: Optional[int] = None
    google_maps_url: str = ""
    website: str = ""


class CreditNeed(BaseModel):
    amount_requested_brl: Optional[float] = None
    purpose: str = ""                   # "comprar estoque", "pagar dívidas", ...
    urgency: str = ""


class Completeness(BaseModel):
    has_business_description: bool = False
    has_financials: bool = False
    has_documents: bool = False
    has_photos: bool = False
    has_online_presence: bool = False

    @property
    def fraction(self) -> float:
        flags = [
            self.has_business_description, self.has_financials,
            self.has_documents, self.has_photos, self.has_online_presence,
        ]
        return round(sum(flags) / len(flags), 2)


class SourceData(BaseModel):
    """Provenance — where this portfolio came from."""

    wa_id: str = ""
    lead_id: str = ""
    raw_message_count: int = 0
    collected_via: str = "whatsapp"


class BusinessPortfolio(BaseModel):
    """The structured profile built from a user's WhatsApp intake."""

    portfolio_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "0.1"
    status: str = "draft"               # "draft" | "complete"

    owner: OwnerInfo = Field(default_factory=OwnerInfo)
    business: BusinessInfo = Field(default_factory=BusinessInfo)
    financials: FinancialSnapshot = Field(default_factory=FinancialSnapshot)
    documents: list[DocumentRef] = Field(default_factory=list)
    photos: list[MediaRef] = Field(default_factory=list)
    online: OnlinePresence = Field(default_factory=OnlinePresence)
    credit_need: CreditNeed = Field(default_factory=CreditNeed)

    completeness: Completeness = Field(default_factory=Completeness)
    source: SourceData = Field(default_factory=SourceData)

    # Free-form notes / flags from the build pass (e.g. "no documents received").
    review_flags: list[str] = Field(default_factory=list)
