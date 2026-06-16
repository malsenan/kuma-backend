"""Rules-based scorecard — Phase 0 scorer described in §10 of the Lumora spec.

No training data required. Every factor keeps its raw points so the
§5.1 explanation falls out for free (no SHAP needed at this stage).
When the XGBoost model replaces this in Phase 2, SHAP will produce the
same FactorScore shape, so the investor-facing UI stays unchanged.
"""

from datetime import datetime, timezone

from .models import BorrowerFeatures, DataCompleteness, Explanation, FactorScore, TrustScore

MODEL_VERSION = "0.1.0"

# Band → base loan (BRL). Progressive lending: start small, grow with repayment history.
_BAND_LOAN: dict[str, float] = {"A": 2000, "B": 1500, "C": 1000, "D": 600, "E": 300}


def _band(
    value: float,
    thresholds: list[tuple[float, float]],
    default: float = 0,
    reverse: bool = False,
) -> float:
    """Return the point value for the first threshold the value clears.

    reverse=False (default): higher value is better — iterate thresholds high→low.
    reverse=True: lower value is better (e.g. volatility, negative-balance days) — iterate low→high.
    """
    if reverse:
        for threshold, points in sorted(thresholds, key=lambda x: x[0]):
            if value <= threshold:
                return points
    else:
        for threshold, points in sorted(thresholds, key=lambda x: x[0], reverse=True):
            if value >= threshold:
                return points
    return default


def score_borrower(features: BorrowerFeatures) -> TrustScore:
    """Score a single borrower and return a fully populated TrustScore.

    Factor weights and bands are taken verbatim from §10 of the Lumora spec.
    Refine thresholds as MFI interview data and early loan outcomes arrive.
    """

    # ── Factor 1: Debt-service capacity (max 25 pts) ────────────────────────
    # Core MFI test: can the cash flow cover the loan? Proposed repayment=0 → max score.
    dscr = features.avg_monthly_inflow_brl / max(features.proposed_monthly_repayment_brl, 1.0)
    pts_1 = _band(dscr, [(3.0, 25), (2.0, 18), (1.5, 10), (1.0, 4)], default=0)

    # ── Factor 2: Income stability (max 20 pts) ──────────────────────────────
    # Lower coefficient of variation = steadier income = better.
    pts_2 = _band(features.inflow_cv, [(0.2, 20), (0.4, 14), (0.6, 7)], default=2, reverse=True)

    # ── Factor 3: Business/account tenure (max 15 pts) ──────────────────────
    pts_3 = _band(features.account_age_months, [(24, 15), (12, 10), (6, 5)], default=1)

    # ── Factor 4: Customer base breadth (max 10 pts) ─────────────────────────
    pts_4 = _band(features.distinct_payers, [(20, 10), (10, 6), (5, 3)], default=0)

    # ── Factor 5: Cash management (max 10 pts) ──────────────────────────────
    # Fewer negative-balance days = better discipline.
    pts_5 = _band(features.neg_balance_days, [(0, 10), (2, 6), (5, 3)], default=0, reverse=True)

    # ── Factor 6: Verification / trust (max 10 pts, 3 pts per verified item) ─
    pts_6 = min(features.verified_count * 3, 10)

    # ── Factor 7: Profile completeness (max 10 pts) ──────────────────────────
    pts_7 = round(features.profile_completeness * 10)

    raw = min(pts_1 + pts_2 + pts_3 + pts_4 + pts_5 + pts_6 + pts_7, 100)

    # ── Display mappings ─────────────────────────────────────────────────────
    trust_score = 300 + round(raw / 100 * 550)  # → 300–850
    # Linear calibration: raw=0 → 0.30, raw=100 → 0.97.
    # Replace with a calibrated sigmoid once real loan outcomes exist.
    payback_probability = round(0.30 + (raw / 100) * 0.67, 3)

    risk_band = (
        "A" if raw >= 80 else
        "B" if raw >= 65 else
        "C" if raw >= 50 else
        "D" if raw >= 35 else
        "E"
    )

    recommended_loan = _BAND_LOAN[risk_band]
    max_loan = round(features.avg_monthly_inflow_brl * 2.5)

    # ── Explanation ──────────────────────────────────────────────────────────
    # impact = signed distance from the midpoint of each factor's range,
    # normalised to [−0.5, +0.5] of the overall 100-pt scale.
    factor_rows = [
        FactorScore(
            feature="debt_service_capacity",
            points=pts_1, max_points=25,
            plain=f"Income covers repayment {dscr:.1f}× (DSCR)",
            impact=round((pts_1 - 12.5) / 100, 3),
        ),
        FactorScore(
            feature="income_stability",
            points=pts_2, max_points=20,
            plain=f"Monthly income variation (CV) = {features.inflow_cv:.2f}",
            impact=round((pts_2 - 10.0) / 100, 3),
        ),
        FactorScore(
            feature="account_tenure",
            points=pts_3, max_points=15,
            plain=f"{features.account_age_months} months of account history",
            impact=round((pts_3 - 7.5) / 100, 3),
        ),
        FactorScore(
            feature="customer_breadth",
            points=pts_4, max_points=10,
            plain=f"{features.distinct_payers} distinct paying customers",
            impact=round((pts_4 - 5.0) / 100, 3),
        ),
        FactorScore(
            feature="cash_management",
            points=pts_5, max_points=10,
            plain=f"{features.neg_balance_days} days with negative balance",
            impact=round((pts_5 - 5.0) / 100, 3),
        ),
        FactorScore(
            feature="verification",
            points=pts_6, max_points=10,
            plain=f"{features.verified_count}/4 items verified (ID, address, MEI, bank)",
            impact=round((pts_6 - 5.0) / 100, 3),
        ),
        FactorScore(
            feature="profile_completeness",
            points=pts_7, max_points=10,
            plain=f"Profile {int(features.profile_completeness * 100)}% complete",
            impact=round((pts_7 - 5.0) / 100, 3),
        ),
    ]
    ranked = sorted(factor_rows, key=lambda f: f.impact, reverse=True)
    positives = [f for f in ranked if f.impact >= 0][:3]
    negatives = [f for f in ranked if f.impact < 0]

    # ── Confidence / data completeness ───────────────────────────────────────
    completeness = DataCompleteness(
        financial_api=features.has_financial_api,
        documents=features.has_documents,
        photos=features.has_photos,
        online_presence=features.has_online_presence,
    )
    flags = [features.has_financial_api, features.has_documents, features.has_photos, features.has_online_presence]
    confidence = round(sum(flags) / len(flags), 2)

    return TrustScore(
        borrower_id=features.borrower_id,
        model_version=MODEL_VERSION,
        scored_at=datetime.now(timezone.utc),
        payback_probability=payback_probability,
        trust_score=trust_score,
        risk_band=risk_band,
        confidence=confidence,
        recommended_loan_brl=recommended_loan,
        max_eligible_loan_brl=float(max_loan),
        explanation=Explanation(
            top_positive_factors=positives,
            top_negative_factors=negatives,
        ),
        data_completeness=completeness,
    )
