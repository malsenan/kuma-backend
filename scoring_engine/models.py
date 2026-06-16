from datetime import datetime
from pydantic import BaseModel, Field


class BorrowerFeatures(BaseModel):
    """Flat feature row fed to the scorer. Derived from Open Finance / PIX + profile form.

    Matches §4-B of the spec. Demographic fields (gender, location, residential moves)
    are deliberately excluded — they live in the profile table but never enter the scorer
    (LGPD compliance + bias prevention, §4-C resolution).
    """

    borrower_id: str

    # --- Financial features (Open Finance / PIX) ---
    avg_monthly_inflow_brl: float = Field(ge=0, description="Average monthly PIX/bank inflow in BRL")
    inflow_cv: float = Field(ge=0, description="Coefficient of variation of monthly inflows (std/mean); lower = steadier")
    distinct_payers: int = Field(ge=0, description="Unique counterparties who sent money in the history window")
    account_age_months: int = Field(ge=0, description="Age of the oldest linked account in months")
    neg_balance_days: int = Field(ge=0, description="Days the account balance went negative in the history window")
    proposed_monthly_repayment_brl: float = Field(ge=0, description="Monthly repayment the borrower is requesting")

    # --- Verification signals (from documents, §4-D) ---
    verified_count: int = Field(ge=0, le=4, description="Count of verified items: ID, address, MEI registration, bank account")

    # --- Profile completeness (photos + online presence, §4-E,F) ---
    profile_completeness: float = Field(ge=0.0, le=1.0, description="Fraction of optional profile fields filled (0–1)")

    # --- Data availability flags (drive confidence score) ---
    has_financial_api: bool = True
    has_documents: bool = False
    has_photos: bool = False
    has_online_presence: bool = False


class FactorScore(BaseModel):
    feature: str
    points: float
    max_points: float
    plain: str
    impact: float = Field(description="Signed contribution to payback_probability; positive = helps, negative = hurts")


class Explanation(BaseModel):
    top_positive_factors: list[FactorScore]
    top_negative_factors: list[FactorScore]
    method: str = "rules-based scorecard v0 (§10 Lumora spec)"


class DataCompleteness(BaseModel):
    financial_api: bool
    documents: bool
    photos: bool
    online_presence: bool


class TrustScore(BaseModel):
    """Primary output object — §5.1 of the spec.

    payback_probability is the real model output; trust_score is only for display.
    Both portals render from this object without modification.
    """

    borrower_id: str
    model_version: str
    scored_at: datetime
    payback_probability: float = Field(ge=0.0, le=1.0)
    trust_score: int = Field(ge=300, le=850)
    risk_band: str = Field(pattern="^[ABCDE]$")
    confidence: float = Field(ge=0.0, le=1.0, description="Data completeness score; drives how much to trust the estimate")
    recommended_loan_brl: float
    max_eligible_loan_brl: float
    explanation: Explanation
    data_completeness: DataCompleteness
