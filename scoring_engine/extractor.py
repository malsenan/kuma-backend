"""Feature extractor — turns raw Belvo-style JSON (§4-A) into a BorrowerFeatures row (§4-B).

The pipeline is:
    raw transactions + accounts (Belvo API) + profile form
        → extract_features()
            → BorrowerFeatures (flat row)
                → score_borrower()
                    → TrustScore

Nothing here touches the scoring logic. This layer is purely data transformation.
"""

from collections import defaultdict
from datetime import date
from statistics import mean, pstdev
from typing import Literal

from pydantic import BaseModel, Field

from .models import BorrowerFeatures


# ── Raw input models (Belvo-style, §4-A) ─────────────────────────────────────

class RawTransaction(BaseModel):
    """One transaction entry as returned by the Belvo / Pluggy API."""

    id: str
    account_id: str
    type: Literal["INFLOW", "OUTFLOW"]
    method: str = ""  # PIX | TED | BOLETO | CARD | CASH_DEPOSIT | ...
    amount: float = Field(ge=0)
    currency: str = "BRL"
    value_date: date
    description: str = ""
    counterparty_doc: str | None = None  # masked CPF/CNPJ; None if unavailable
    category: str | None = None
    balance_after: float | None = None   # None if the API doesn't return it


class RawAccount(BaseModel):
    """One account entry as returned by the Belvo / Pluggy API."""

    account_id: str
    type: str = ""  # CHECKING | SAVINGS | PREPAID
    balance_available: float = 0.0
    balance_current: float = 0.0
    currency: str = "BRL"
    institution: str = ""
    opened_date: date


class ProfileMeta(BaseModel):
    """Non-financial inputs from the entrepreneur's profile form.

    These never come from the bank API — they're collected once during onboarding.
    Demographic fields (gender, location) are deliberately absent; they live in the
    profile table but are excluded here per §4-C (LGPD / bias prevention).
    """

    borrower_id: str
    proposed_monthly_repayment_brl: float = Field(ge=0)
    verified_count: int = Field(ge=0, le=4, description="ID, address, MEI, bank — 1 pt each")
    profile_completeness: float = Field(ge=0.0, le=1.0)
    has_documents: bool = False
    has_photos: bool = False
    has_online_presence: bool = False


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_features(
    transactions: list[RawTransaction],
    accounts: list[RawAccount],
    profile: ProfileMeta,
    reference_date: date | None = None,
) -> BorrowerFeatures:
    """Derive a flat BorrowerFeatures row from raw Belvo inputs + profile metadata.

    Args:
        transactions: All transactions returned by the Belvo API for this borrower.
        accounts:     All accounts returned by the Belvo API for this borrower.
        profile:      Non-financial profile fields collected from the onboarding form.
        reference_date: The "today" used for account-age calculations. Pass a fixed
                        date in tests; leave None in production (defaults to today).

    Returns:
        BorrowerFeatures ready to pass directly to score_borrower().
    """
    today = reference_date or date.today()
    inflows = [t for t in transactions if t.type == "INFLOW"]

    # ── avg_monthly_inflow_brl ────────────────────────────────────────────────
    # Sum inflows per calendar month, then average across months.
    monthly_inflows: dict[tuple[int, int], float] = defaultdict(float)
    for t in inflows:
        monthly_inflows[(t.value_date.year, t.value_date.month)] += t.amount

    avg_monthly_inflow = mean(monthly_inflows.values()) if monthly_inflows else 0.0

    # ── inflow_cv ─────────────────────────────────────────────────────────────
    # Coefficient of variation = population std / mean.
    # Needs >= 2 months to be meaningful; 0.0 otherwise (no variation observable).
    if len(monthly_inflows) >= 2 and avg_monthly_inflow > 0:
        inflow_cv = pstdev(monthly_inflows.values()) / avg_monthly_inflow
    else:
        inflow_cv = 0.0

    # ── distinct_payers ───────────────────────────────────────────────────────
    # Unique non-null counterparty_doc values on inflow transactions.
    payer_docs = {t.counterparty_doc for t in inflows if t.counterparty_doc}
    distinct_payers = len(payer_docs)

    # ── account_age_months ────────────────────────────────────────────────────
    # Age of the oldest linked account, floored to whole months.
    if accounts:
        oldest_opened = min(a.opened_date for a in accounts)
        account_age_months = max((today - oldest_opened).days // 30, 0)
    else:
        account_age_months = 0

    # ── neg_balance_days ──────────────────────────────────────────────────────
    # Distinct calendar dates on which any transaction left balance_after < 0.
    neg_days = {
        t.value_date
        for t in transactions
        if t.balance_after is not None and t.balance_after < 0
    }
    neg_balance_days = len(neg_days)

    return BorrowerFeatures(
        borrower_id=profile.borrower_id,
        avg_monthly_inflow_brl=round(avg_monthly_inflow, 2),
        inflow_cv=round(inflow_cv, 4),
        distinct_payers=distinct_payers,
        account_age_months=account_age_months,
        neg_balance_days=neg_balance_days,
        proposed_monthly_repayment_brl=profile.proposed_monthly_repayment_brl,
        verified_count=profile.verified_count,
        profile_completeness=profile.profile_completeness,
        has_financial_api=len(transactions) > 0,
        has_documents=profile.has_documents,
        has_photos=profile.has_photos,
        has_online_presence=profile.has_online_presence,
    )
