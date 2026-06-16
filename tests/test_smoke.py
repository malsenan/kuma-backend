"""Smoke tests — verify the package imports and the critical path returns a result.

These run first (alphabetically) and should fail fast if something is broken at the
import or wiring level, before the rest of the suite attempts anything heavier.
"""

from scoring_engine import BorrowerFeatures, TrustScore, score_borrower
from scoring_engine.synthetic import generate_borrower, generate_labeled


def _minimal_features() -> BorrowerFeatures:
    return BorrowerFeatures(
        borrower_id="smoke_001",
        avg_monthly_inflow_brl=1000.0,
        inflow_cv=0.5,
        distinct_payers=5,
        account_age_months=6,
        neg_balance_days=2,
        proposed_monthly_repayment_brl=200.0,
        verified_count=1,
        profile_completeness=0.4,
    )


def test_package_imports():
    assert score_borrower is not None
    assert BorrowerFeatures is not None
    assert TrustScore is not None


def test_score_borrower_returns_trust_score():
    result = score_borrower(_minimal_features())
    assert isinstance(result, TrustScore)


def test_result_is_json_serialisable():
    result = score_borrower(_minimal_features())
    payload = result.model_dump_json()
    assert len(payload) > 0


def test_generate_borrower_smoke():
    b = generate_borrower()
    assert isinstance(b, BorrowerFeatures)


def test_generate_and_score_smoke():
    b = generate_borrower(seed=0)
    result = score_borrower(b)
    assert isinstance(result, TrustScore)


def test_generate_labeled_smoke():
    lb = generate_labeled(seed=0)
    assert lb.simulated_outcome in {"repaid_on_time", "repaid_late", "defaulted"}
