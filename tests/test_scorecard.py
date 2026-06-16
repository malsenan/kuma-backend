import pytest
from scoring_engine.models import BorrowerFeatures
from scoring_engine.scorecard import MODEL_VERSION, _band, score_borrower


def make_features(**overrides) -> BorrowerFeatures:
    defaults = dict(
        borrower_id="test_001",
        avg_monthly_inflow_brl=2000.0,
        inflow_cv=0.30,
        distinct_payers=15,
        account_age_months=18,
        neg_balance_days=1,
        proposed_monthly_repayment_brl=500.0,
        verified_count=3,
        profile_completeness=0.8,
        has_financial_api=True,
        has_documents=True,
        has_photos=False,
        has_online_presence=False,
    )
    return BorrowerFeatures(**{**defaults, **overrides})


# ── _band helper ─────────────────────────────────────────────────────────────

class TestBand:
    def test_clears_highest_threshold(self):
        assert _band(3.5, [(3.0, 25), (2.0, 18), (1.5, 10), (1.0, 4)]) == 25

    def test_clears_middle_threshold(self):
        assert _band(2.2, [(3.0, 25), (2.0, 18), (1.5, 10), (1.0, 4)]) == 18

    def test_clears_lowest_threshold(self):
        assert _band(1.1, [(3.0, 25), (2.0, 18), (1.5, 10), (1.0, 4)]) == 4

    def test_below_all_thresholds_returns_default(self):
        assert _band(0.5, [(3.0, 25), (2.0, 18), (1.5, 10), (1.0, 4)], default=0) == 0

    def test_reverse_low_value_gets_top_points(self):
        # CV=0.1, lower is better → should earn 20 pts
        assert _band(0.1, [(0.2, 20), (0.4, 14), (0.6, 7)], default=2, reverse=True) == 20

    def test_reverse_mid_value(self):
        assert _band(0.35, [(0.2, 20), (0.4, 14), (0.6, 7)], default=2, reverse=True) == 14

    def test_reverse_above_all_returns_default(self):
        assert _band(0.8, [(0.2, 20), (0.4, 14), (0.6, 7)], default=2, reverse=True) == 2

    def test_exact_threshold_boundary_normal(self):
        # value == threshold should clear it
        assert _band(2.0, [(3.0, 25), (2.0, 18), (1.5, 10), (1.0, 4)]) == 18

    def test_exact_threshold_boundary_reverse(self):
        assert _band(0.2, [(0.2, 20), (0.4, 14), (0.6, 7)], default=2, reverse=True) == 20


# ── score_borrower outputs ────────────────────────────────────────────────────

class TestScoreBorrower:
    def test_trust_score_in_range(self):
        result = score_borrower(make_features())
        assert 300 <= result.trust_score <= 850

    def test_payback_probability_in_range(self):
        result = score_borrower(make_features())
        assert 0.0 <= result.payback_probability <= 1.0

    def test_risk_band_valid(self):
        result = score_borrower(make_features())
        assert result.risk_band in ("A", "B", "C", "D", "E")

    def test_borrower_id_preserved(self):
        result = score_borrower(make_features(borrower_id="abc123"))
        assert result.borrower_id == "abc123"

    def test_model_version_present(self):
        result = score_borrower(make_features())
        assert result.model_version == MODEL_VERSION

    def test_scored_at_is_set(self):
        result = score_borrower(make_features())
        assert result.scored_at is not None

    def test_strong_borrower_gets_high_band(self):
        result = score_borrower(make_features(
            avg_monthly_inflow_brl=5000.0,
            inflow_cv=0.10,
            distinct_payers=25,
            account_age_months=36,
            neg_balance_days=0,
            verified_count=4,
            profile_completeness=1.0,
            proposed_monthly_repayment_brl=400.0,
        ))
        assert result.risk_band in ("A", "B")
        assert result.payback_probability > 0.75

    def test_weak_borrower_gets_low_band(self):
        result = score_borrower(make_features(
            avg_monthly_inflow_brl=500.0,
            inflow_cv=0.90,
            distinct_payers=1,
            account_age_months=2,
            neg_balance_days=12,
            verified_count=0,
            profile_completeness=0.05,
            proposed_monthly_repayment_brl=400.0,
        ))
        assert result.risk_band in ("D", "E")
        assert result.payback_probability < 0.55

    def test_zero_repayment_does_not_crash(self):
        # proposed_monthly_repayment_brl=0 must not divide by zero
        result = score_borrower(make_features(proposed_monthly_repayment_brl=0.0))
        assert 300 <= result.trust_score <= 850

    def test_recommended_loan_matches_band(self):
        expected = {"A": 2000.0, "B": 1500.0, "C": 1000.0, "D": 600.0, "E": 300.0}
        result = score_borrower(make_features())
        assert result.recommended_loan_brl == expected[result.risk_band]

    def test_max_eligible_loan_proportional_to_income(self):
        low = score_borrower(make_features(avg_monthly_inflow_brl=1000.0))
        high = score_borrower(make_features(avg_monthly_inflow_brl=4000.0))
        assert high.max_eligible_loan_brl > low.max_eligible_loan_brl

    def test_explanation_has_positive_factors(self):
        result = score_borrower(make_features())
        assert len(result.explanation.top_positive_factors) >= 1

    def test_explanation_positive_factors_have_non_negative_impact(self):
        result = score_borrower(make_features())
        for f in result.explanation.top_positive_factors:
            assert f.impact >= 0

    def test_explanation_negative_factors_have_negative_impact(self):
        result = score_borrower(make_features())
        for f in result.explanation.top_negative_factors:
            assert f.impact < 0

    def test_confidence_full_data(self):
        result = score_borrower(make_features(
            has_financial_api=True, has_documents=True,
            has_photos=True, has_online_presence=True,
        ))
        assert result.confidence == 1.0

    def test_confidence_no_data(self):
        result = score_borrower(make_features(
            has_financial_api=False, has_documents=False,
            has_photos=False, has_online_presence=False,
        ))
        assert result.confidence == 0.0

    def test_confidence_partial_data(self):
        full = score_borrower(make_features(has_financial_api=True, has_documents=True, has_photos=True, has_online_presence=True))
        partial = score_borrower(make_features(has_financial_api=True, has_documents=False, has_photos=False, has_online_presence=False))
        assert full.confidence > partial.confidence

    def test_data_completeness_flags_match_input(self):
        result = score_borrower(make_features(
            has_financial_api=True, has_documents=False,
            has_photos=True, has_online_presence=False,
        ))
        assert result.data_completeness.financial_api is True
        assert result.data_completeness.documents is False
        assert result.data_completeness.photos is True
        assert result.data_completeness.online_presence is False

    @pytest.mark.parametrize("inflow", [600.0, 1500.0, 3000.0, 6000.0])
    def test_trust_score_always_in_range(self, inflow):
        result = score_borrower(make_features(avg_monthly_inflow_brl=inflow))
        assert 300 <= result.trust_score <= 850

    def test_higher_income_stability_improves_score(self):
        stable = score_borrower(make_features(inflow_cv=0.1))
        volatile = score_borrower(make_features(inflow_cv=0.9))
        assert stable.trust_score > volatile.trust_score

    def test_more_verified_items_improves_score(self):
        verified = score_borrower(make_features(verified_count=4))
        unverified = score_borrower(make_features(verified_count=0))
        assert verified.trust_score > unverified.trust_score
