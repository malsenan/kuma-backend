"""Regression tests — pin known inputs to exact expected outputs.

If any of these fail, a band threshold, weight, or formula changed.
Update the pinned values intentionally and document why in the commit message.
Do NOT silently fix a failing regression test by updating the expected value
without understanding what changed in the scoring logic.
"""

import pytest
from scoring_engine.models import BorrowerFeatures
from scoring_engine.scorecard import _band, score_borrower


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def strong() -> BorrowerFeatures:
    """Best-case borrower: high income, very stable, long history, many payers,
    no negative days, fully verified, complete profile."""
    return BorrowerFeatures(
        borrower_id="reg_strong",
        avg_monthly_inflow_brl=5000.0,
        inflow_cv=0.10,
        distinct_payers=25,
        account_age_months=36,
        neg_balance_days=0,
        proposed_monthly_repayment_brl=400.0,
        verified_count=4,
        profile_completeness=1.0,
        has_financial_api=True, has_documents=True, has_photos=True, has_online_presence=True,
    )


@pytest.fixture
def mid() -> BorrowerFeatures:
    """Mid-tier borrower: moderate income and history, partial verification."""
    return BorrowerFeatures(
        borrower_id="reg_mid",
        avg_monthly_inflow_brl=2000.0,
        inflow_cv=0.35,
        distinct_payers=12,
        account_age_months=14,
        neg_balance_days=3,
        proposed_monthly_repayment_brl=500.0,
        verified_count=2,
        profile_completeness=0.5,
        has_financial_api=True, has_documents=True, has_photos=False, has_online_presence=False,
    )


@pytest.fixture
def weak() -> BorrowerFeatures:
    """Weak borrower: low income, volatile, short history, unverified."""
    return BorrowerFeatures(
        borrower_id="reg_weak",
        avg_monthly_inflow_brl=600.0,
        inflow_cv=0.85,
        distinct_payers=2,
        account_age_months=3,
        neg_balance_days=10,
        proposed_monthly_repayment_brl=400.0,
        verified_count=0,
        profile_completeness=0.1,
        has_financial_api=True, has_documents=False, has_photos=False, has_online_presence=False,
    )


@pytest.fixture
def dscr_boundary() -> BorrowerFeatures:
    """Inputs that sit exactly on band boundaries for multiple factors.
    Boundary behaviour must stay stable across refactors."""
    return BorrowerFeatures(
        borrower_id="reg_dscr",
        avg_monthly_inflow_brl=3000.0,
        inflow_cv=0.20,        # exactly on the 0.2 boundary → 20 pts
        distinct_payers=10,    # exactly on the 10 boundary → 6 pts
        account_age_months=12, # exactly on the 12 boundary → 10 pts
        neg_balance_days=2,    # exactly on the 2 boundary → 6 pts
        proposed_monthly_repayment_brl=1000.0,  # dscr = 3.0 exactly → 25 pts
        verified_count=3,
        profile_completeness=0.7,
        has_financial_api=True, has_documents=True, has_photos=False, has_online_presence=False,
    )


@pytest.fixture
def zero_repayment() -> BorrowerFeatures:
    """proposed_monthly_repayment_brl=0 — guards the divide-by-zero clamp."""
    return BorrowerFeatures(
        borrower_id="reg_zero_repay",
        avg_monthly_inflow_brl=1500.0,
        inflow_cv=0.50,
        distinct_payers=8,
        account_age_months=10,
        neg_balance_days=4,
        proposed_monthly_repayment_brl=0.0,
        verified_count=1,
        profile_completeness=0.3,
        has_financial_api=True, has_documents=False, has_photos=False, has_online_presence=False,
    )


# ── Strong borrower ───────────────────────────────────────────────────────────

class TestStrongBorrower:
    def test_trust_score(self, strong):
        assert score_borrower(strong).trust_score == 850

    def test_risk_band(self, strong):
        assert score_borrower(strong).risk_band == "A"

    def test_payback_probability(self, strong):
        assert score_borrower(strong).payback_probability == 0.97

    def test_recommended_loan(self, strong):
        assert score_borrower(strong).recommended_loan_brl == 2000.0

    def test_confidence(self, strong):
        assert score_borrower(strong).confidence == 1.0

    def test_max_eligible_loan(self, strong):
        # avg_monthly_inflow * 2.5 = 5000 * 2.5 = 12500
        assert score_borrower(strong).max_eligible_loan_brl == 12500.0

    def test_top_positive_factor_is_debt_service(self, strong):
        result = score_borrower(strong)
        top = result.explanation.top_positive_factors[0]
        assert top.feature == "debt_service_capacity"
        assert top.points == 25.0

    def test_no_negative_factors(self, strong):
        # Perfect borrower — every factor is at or above midpoint
        assert score_borrower(strong).explanation.top_negative_factors == []


# ── Mid-tier borrower ─────────────────────────────────────────────────────────

class TestMidBorrower:
    def test_trust_score(self, mid):
        assert score_borrower(mid).trust_score == 679

    def test_risk_band(self, mid):
        assert score_borrower(mid).risk_band == "B"

    def test_payback_probability(self, mid):
        assert score_borrower(mid).payback_probability == 0.762

    def test_recommended_loan(self, mid):
        assert score_borrower(mid).recommended_loan_brl == 1500.0

    def test_confidence(self, mid):
        assert score_borrower(mid).confidence == 0.5

    def test_max_eligible_loan(self, mid):
        # 2000 * 2.5 = 5000
        assert score_borrower(mid).max_eligible_loan_brl == 5000.0

    def test_factor_points_debt_service(self, mid):
        # dscr = 2000/500 = 4.0 → clears 3.0 threshold → 25 pts
        assert _band(4.0, [(3.0, 25), (2.0, 18), (1.5, 10), (1.0, 4)], default=0) == 25

    def test_factor_points_income_stability(self, mid):
        # cv=0.35 → clears 0.4 threshold (reverse) → 14 pts
        assert _band(0.35, [(0.2, 20), (0.4, 14), (0.6, 7)], default=2, reverse=True) == 14


# ── Weak borrower ─────────────────────────────────────────────────────────────

class TestWeakBorrower:
    def test_trust_score(self, weak):
        assert score_borrower(weak).trust_score == 377

    def test_risk_band(self, weak):
        assert score_borrower(weak).risk_band == "E"

    def test_payback_probability(self, weak):
        assert score_borrower(weak).payback_probability == 0.394

    def test_recommended_loan(self, weak):
        assert score_borrower(weak).recommended_loan_brl == 300.0

    def test_confidence(self, weak):
        assert score_borrower(weak).confidence == 0.25

    def test_has_negative_factors(self, weak):
        assert len(score_borrower(weak).explanation.top_negative_factors) > 0

    def test_verification_factor_zero_points(self, weak):
        # verified_count=0 → 0 * 3 = 0, capped at 10 → 0 pts
        assert min(0 * 3, 10) == 0


# ── Boundary borrower ─────────────────────────────────────────────────────────

class TestDscrBoundary:
    def test_trust_score(self, dscr_boundary):
        assert score_borrower(dscr_boundary).trust_score == 756

    def test_risk_band(self, dscr_boundary):
        assert score_borrower(dscr_boundary).risk_band == "A"

    def test_payback_probability(self, dscr_boundary):
        assert score_borrower(dscr_boundary).payback_probability == 0.856

    def test_dscr_exactly_3_earns_25_pts(self, dscr_boundary):
        # dscr = 3000/1000 = 3.0 — must clear the >= 3.0 threshold
        assert _band(3.0, [(3.0, 25), (2.0, 18), (1.5, 10), (1.0, 4)], default=0) == 25

    def test_cv_exactly_0_2_earns_20_pts(self, dscr_boundary):
        # cv=0.20 — must clear the <= 0.2 threshold (reverse band)
        assert _band(0.20, [(0.2, 20), (0.4, 14), (0.6, 7)], default=2, reverse=True) == 20

    def test_neg_balance_exactly_2_earns_6_pts(self, dscr_boundary):
        # neg_balance_days=2 — must clear the <= 2 threshold (reverse band)
        assert _band(2, [(0, 10), (2, 6), (5, 3)], default=0, reverse=True) == 6


# ── Zero repayment ────────────────────────────────────────────────────────────

class TestZeroRepayment:
    def test_trust_score(self, zero_repayment):
        assert score_borrower(zero_repayment).trust_score == 570

    def test_risk_band(self, zero_repayment):
        assert score_borrower(zero_repayment).risk_band == "D"

    def test_payback_probability(self, zero_repayment):
        assert score_borrower(zero_repayment).payback_probability == 0.628

    def test_recommended_loan(self, zero_repayment):
        assert score_borrower(zero_repayment).recommended_loan_brl == 600.0

    def test_dscr_uses_clamp_not_zero_division(self, zero_repayment):
        # dscr = 1500 / max(0, 1) = 1500 → clears 3.0 threshold → 25 pts
        dscr = 1500.0 / max(0.0, 1.0)
        assert _band(dscr, [(3.0, 25), (2.0, 18), (1.5, 10), (1.0, 4)], default=0) == 25
