"""Tests for scoring_engine/extractor.py.

Covers:
  - Unit: one feature at a time with minimal fixtures
  - Edge cases: empty inputs, single month, missing counterparty_doc, None balance_after
  - Regression: fixed full fixture → pinned extracted field values + pinned trust score
  - Integration: extract_features() → score_borrower() end-to-end
"""

from datetime import date

import pytest

from scoring_engine.extractor import (
    ProfileMeta,
    RawAccount,
    RawTransaction,
    extract_features,
)
from scoring_engine.scorecard import score_borrower

# ── Shared reference date (keeps account_age_months deterministic) ─────────────
REF = date(2026, 6, 1)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def inflow(tx_id: str, value_date: date, amount: float,
           counterparty_doc: str | None = "cpf_A",
           balance_after: float | None = 500.0) -> RawTransaction:
    return RawTransaction(
        id=tx_id, account_id="acc1", type="INFLOW",
        method="PIX", amount=amount, value_date=value_date,
        counterparty_doc=counterparty_doc, balance_after=balance_after,
    )


def outflow(tx_id: str, value_date: date, amount: float,
            balance_after: float | None = 500.0) -> RawTransaction:
    return RawTransaction(
        id=tx_id, account_id="acc1", type="OUTFLOW",
        method="PIX", amount=amount, value_date=value_date,
        balance_after=balance_after,
    )


def account(opened: date = date(2024, 6, 1)) -> RawAccount:
    return RawAccount(
        account_id="acc1", type="CHECKING",
        balance_available=500.0, balance_current=500.0,
        opened_date=opened,
    )


def profile(**overrides) -> ProfileMeta:
    defaults = dict(
        borrower_id="test_001",
        proposed_monthly_repayment_brl=300.0,
        verified_count=2,
        profile_completeness=0.6,
    )
    return ProfileMeta(**{**defaults, **overrides})


# ── Unit: avg_monthly_inflow_brl ─────────────────────────────────────────────

class TestAvgMonthlyInflow:
    def test_single_month(self):
        txns = [inflow("t1", date(2026,1,5), 1000.0), inflow("t2", date(2026,1,20), 500.0)]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.avg_monthly_inflow_brl == 1500.0

    def test_averages_across_months(self):
        txns = [
            inflow("t1", date(2026,1,5),  1500.0),
            inflow("t2", date(2026,2,5),  1500.0),
            inflow("t3", date(2026,3,5),  1500.0),
        ]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.avg_monthly_inflow_brl == 1500.0

    def test_outflows_not_counted(self):
        txns = [
            inflow("t1", date(2026,1,5),  1000.0),
            outflow("t2", date(2026,1,10), 800.0),
        ]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.avg_monthly_inflow_brl == 1000.0

    def test_multiple_inflows_same_month_summed(self):
        txns = [
            inflow("t1", date(2026,1,1),  300.0),
            inflow("t2", date(2026,1,15), 300.0),
            inflow("t3", date(2026,1,28), 400.0),
        ]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.avg_monthly_inflow_brl == 1000.0

    def test_no_transactions_gives_zero(self):
        f = extract_features([], [account()], profile(), REF)
        assert f.avg_monthly_inflow_brl == 0.0

    def test_only_outflows_gives_zero(self):
        txns = [outflow("t1", date(2026,1,5), 500.0)]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.avg_monthly_inflow_brl == 0.0


# ── Unit: inflow_cv ───────────────────────────────────────────────────────────

class TestInflowCV:
    def test_single_month_gives_zero(self):
        txns = [inflow("t1", date(2026,1,5), 1000.0)]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.inflow_cv == 0.0

    def test_equal_months_gives_zero(self):
        txns = [
            inflow("t1", date(2026,1,5), 1000.0),
            inflow("t2", date(2026,2,5), 1000.0),
            inflow("t3", date(2026,3,5), 1000.0),
        ]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.inflow_cv == 0.0

    def test_volatile_months_gives_positive_cv(self):
        txns = [
            inflow("t1", date(2026,1,5), 2000.0),
            inflow("t2", date(2026,2,5), 500.0),
        ]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.inflow_cv > 0.0

    def test_no_inflows_gives_zero(self):
        f = extract_features([], [account()], profile(), REF)
        assert f.inflow_cv == 0.0

    def test_higher_variance_gives_higher_cv(self):
        stable_txns = [
            inflow("s1", date(2026,1,5), 1000.0),
            inflow("s2", date(2026,2,5), 1000.0),
            inflow("s3", date(2026,3,5), 1000.0),
        ]
        volatile_txns = [
            inflow("v1", date(2026,1,5), 2000.0),
            inflow("v2", date(2026,2,5), 100.0),
            inflow("v3", date(2026,3,5), 1900.0),
        ]
        stable = extract_features(stable_txns, [account()], profile(), REF)
        volatile = extract_features(volatile_txns, [account()], profile(), REF)
        assert volatile.inflow_cv > stable.inflow_cv


# ── Unit: distinct_payers ─────────────────────────────────────────────────────

class TestDistinctPayers:
    def test_counts_unique_docs(self):
        txns = [
            inflow("t1", date(2026,1,5),  100.0, counterparty_doc="cpf_A"),
            inflow("t2", date(2026,1,10), 100.0, counterparty_doc="cpf_B"),
            inflow("t3", date(2026,1,15), 100.0, counterparty_doc="cpf_A"),  # repeat
        ]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.distinct_payers == 2

    def test_none_counterparty_excluded(self):
        txns = [
            inflow("t1", date(2026,1,5),  100.0, counterparty_doc="cpf_A"),
            inflow("t2", date(2026,1,10), 100.0, counterparty_doc=None),
        ]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.distinct_payers == 1

    def test_all_none_gives_zero(self):
        txns = [inflow("t1", date(2026,1,5), 100.0, counterparty_doc=None)]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.distinct_payers == 0

    def test_outflows_not_counted(self):
        txns = [
            inflow( "t1", date(2026,1,5),  100.0, counterparty_doc="cpf_A"),
            outflow("t2", date(2026,1,10), 100.0),  # no counterparty_doc arg
        ]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.distinct_payers == 1


# ── Unit: account_age_months ──────────────────────────────────────────────────

class TestAccountAgeMonths:
    def test_uses_oldest_account(self):
        accounts = [
            RawAccount(account_id="a1", balance_available=0, balance_current=0, opened_date=date(2024,6,1)),
            RawAccount(account_id="a2", balance_available=0, balance_current=0, opened_date=date(2023,6,1)),  # older
        ]
        f = extract_features([], accounts, profile(), reference_date=date(2025,6,1))
        # oldest is 2023-06-01 → 2025-06-01 = 730 days → 24 months
        assert f.account_age_months == 24

    def test_no_accounts_gives_zero(self):
        f = extract_features([], [], profile(), REF)
        assert f.account_age_months == 0

    def test_same_day_gives_zero(self):
        f = extract_features([], [account(opened=REF)], profile(), REF)
        assert f.account_age_months == 0

    def test_30_days_gives_one_month(self):
        opened = date(2026, 5, 2)
        ref = date(2026, 6, 1)  # 30 days later
        f = extract_features([], [account(opened=opened)], profile(), ref)
        assert f.account_age_months == 1


# ── Unit: neg_balance_days ────────────────────────────────────────────────────

class TestNegBalanceDays:
    def test_counts_distinct_dates(self):
        txns = [
            outflow("t1", date(2026,1,10), 100.0, balance_after=-50.0),
            outflow("t2", date(2026,1,10), 100.0, balance_after=-80.0),  # same date
            outflow("t3", date(2026,2,15), 100.0, balance_after=-10.0),
        ]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.neg_balance_days == 2

    def test_positive_balance_not_counted(self):
        txns = [outflow("t1", date(2026,1,10), 100.0, balance_after=50.0)]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.neg_balance_days == 0

    def test_none_balance_after_ignored(self):
        txns = [outflow("t1", date(2026,1,10), 100.0, balance_after=None)]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.neg_balance_days == 0

    def test_zero_balance_not_negative(self):
        txns = [outflow("t1", date(2026,1,10), 100.0, balance_after=0.0)]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.neg_balance_days == 0

    def test_inflow_with_neg_balance_counted(self):
        # Balance can go negative even on an inflow if there's a fee
        txns = [inflow("t1", date(2026,1,5), 100.0, balance_after=-5.0)]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.neg_balance_days == 1


# ── Unit: has_financial_api ────────────────────────────────────────────────────

class TestHasFinancialApi:
    def test_true_when_transactions_present(self):
        txns = [inflow("t1", date(2026,1,5), 100.0)]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.has_financial_api is True

    def test_false_when_no_transactions(self):
        f = extract_features([], [account()], profile(), REF)
        assert f.has_financial_api is False


# ── Unit: profile fields pass through unchanged ───────────────────────────────

class TestProfilePassthrough:
    def test_borrower_id(self):
        f = extract_features([], [], profile(borrower_id="xyz_789"), REF)
        assert f.borrower_id == "xyz_789"

    def test_proposed_repayment(self):
        f = extract_features([], [], profile(proposed_monthly_repayment_brl=750.0), REF)
        assert f.proposed_monthly_repayment_brl == 750.0

    def test_verified_count(self):
        f = extract_features([], [], profile(verified_count=4), REF)
        assert f.verified_count == 4

    def test_profile_completeness(self):
        f = extract_features([], [], profile(profile_completeness=0.9), REF)
        assert f.profile_completeness == 0.9

    def test_data_flags(self):
        f = extract_features([], [], profile(has_documents=True, has_photos=True, has_online_presence=True), REF)
        assert f.has_documents is True
        assert f.has_photos is True
        assert f.has_online_presence is True


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_everything(self):
        f = extract_features([], [], profile(), REF)
        assert f.avg_monthly_inflow_brl == 0.0
        assert f.inflow_cv == 0.0
        assert f.distinct_payers == 0
        assert f.account_age_months == 0
        assert f.neg_balance_days == 0
        assert f.has_financial_api is False

    def test_output_is_valid_borrower_features(self):
        # Pydantic will raise if any field violates its constraint
        txns = [inflow("t1", date(2026,1,5), 1000.0)]
        f = extract_features(txns, [account()], profile(), REF)
        assert isinstance(f.avg_monthly_inflow_brl, float)
        assert isinstance(f.inflow_cv, float)
        assert isinstance(f.distinct_payers, int)
        assert isinstance(f.account_age_months, int)
        assert isinstance(f.neg_balance_days, int)

    def test_large_transaction_count(self):
        # 500 inflows across 12 months should not crash
        txns = [
            inflow(f"t{i}", date(2026, (i % 12) + 1, 1), 100.0, counterparty_doc=f"cpf_{i % 50}")
            for i in range(500)
        ]
        f = extract_features(txns, [account()], profile(), REF)
        assert f.avg_monthly_inflow_brl > 0
        assert f.distinct_payers == 50


# ── Regression: pinned full-fixture values ────────────────────────────────────

@pytest.fixture
def regression_inputs():
    """Fixed 3-month transaction history used to pin exact feature values."""
    txns = [
        # Jan 2026: total inflow = 1500
        inflow("t1", date(2026, 1, 5),  1000.0, counterparty_doc="cpf_A", balance_after=1000.0),
        inflow("t2", date(2026, 1, 20),  500.0, counterparty_doc="cpf_B", balance_after=1500.0),
        outflow("t3", date(2026, 1, 28), 800.0, balance_after=700.0),
        # Feb 2026: total inflow = 1200
        inflow("t4", date(2026, 2, 3),   800.0, counterparty_doc="cpf_A", balance_after=1500.0),
        inflow("t5", date(2026, 2, 18),  400.0, counterparty_doc="cpf_C", balance_after=1900.0),
        outflow("t6", date(2026, 2, 25), 2000.0, balance_after=-100.0),  # neg balance
        # Mar 2026: total inflow = 900
        inflow("t7", date(2026, 3, 8),   600.0, counterparty_doc="cpf_B", balance_after=500.0),
        inflow("t8", date(2026, 3, 22),  300.0, counterparty_doc="cpf_D", balance_after=800.0),
        outflow("t9", date(2026, 3, 29), 900.0, balance_after=-50.0),    # neg balance
    ]
    accts = [
        RawAccount(account_id="acc1", type="CHECKING",
                   balance_available=200.0, balance_current=200.0,
                   opened_date=date(2024, 6, 1)),
    ]
    prof = ProfileMeta(
        borrower_id="reg_extractor_001",
        proposed_monthly_repayment_brl=400.0,
        verified_count=3,
        profile_completeness=0.7,
        has_documents=True,
        has_photos=False,
        has_online_presence=False,
    )
    return txns, accts, prof


class TestRegression:
    def test_avg_monthly_inflow(self, regression_inputs):
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        assert f.avg_monthly_inflow_brl == 1200.0

    def test_inflow_cv(self, regression_inputs):
        # monthly=[1500,1200,900], mean=1200, pstdev≈244.949, CV≈0.2041
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        assert f.inflow_cv == 0.2041

    def test_distinct_payers(self, regression_inputs):
        # cpf_A, cpf_B, cpf_C, cpf_D
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        assert f.distinct_payers == 4

    def test_account_age_months(self, regression_inputs):
        # opened 2024-06-01, ref 2026-06-01 → 730 days → 24 months
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        assert f.account_age_months == 24

    def test_neg_balance_days(self, regression_inputs):
        # 2026-02-25 and 2026-03-29
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        assert f.neg_balance_days == 2

    def test_has_financial_api(self, regression_inputs):
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        assert f.has_financial_api is True

    def test_profile_fields(self, regression_inputs):
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        assert f.borrower_id == "reg_extractor_001"
        assert f.proposed_monthly_repayment_brl == 400.0
        assert f.verified_count == 3
        assert f.profile_completeness == 0.7
        assert f.has_documents is True
        assert f.has_photos is False
        assert f.has_online_presence is False


# ── Integration: extract → score end-to-end ───────────────────────────────────

class TestIntegration:
    def test_extract_then_score_returns_trust_score(self, regression_inputs):
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        result = score_borrower(f)
        assert 300 <= result.trust_score <= 850

    def test_pinned_trust_score(self, regression_inputs):
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        result = score_borrower(f)
        assert result.trust_score == 718

    def test_pinned_risk_band(self, regression_inputs):
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        result = score_borrower(f)
        assert result.risk_band == "B"

    def test_pinned_payback_probability(self, regression_inputs):
        txns, accts, prof = regression_inputs
        f = extract_features(txns, accts, prof, REF)
        result = score_borrower(f)
        assert result.payback_probability == 0.809

    def test_more_stable_income_scores_better(self):
        """Extractor + scorer: replacing volatile months with flat income raises score."""
        volatile_txns = [
            inflow("v1", date(2026,1,5), 3000.0),
            inflow("v2", date(2026,2,5),  100.0),
            inflow("v3", date(2026,3,5), 2900.0),
        ]
        stable_txns = [
            inflow("s1", date(2026,1,5), 1000.0),
            inflow("s2", date(2026,2,5), 1000.0),
            inflow("s3", date(2026,3,5), 1000.0),
        ]
        accts = [account()]
        prof = profile()
        f_volatile = extract_features(volatile_txns, accts, prof, REF)
        f_stable   = extract_features(stable_txns,   accts, prof, REF)
        assert score_borrower(f_stable).trust_score > score_borrower(f_volatile).trust_score
