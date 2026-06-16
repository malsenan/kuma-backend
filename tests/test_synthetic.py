from scoring_engine.models import BorrowerFeatures
from scoring_engine.scorecard import score_borrower
from scoring_engine.synthetic import (
    LabeledBorrower,
    generate_batch,
    generate_borrower,
    generate_labeled,
    generate_labeled_batch,
)


class TestGenerateBorrower:
    def test_returns_borrower_features(self):
        b = generate_borrower()
        assert isinstance(b, BorrowerFeatures)

    def test_seed_is_deterministic(self):
        a = generate_borrower(seed=42)
        b = generate_borrower(seed=42)
        assert a == b

    def test_different_seeds_differ(self):
        a = generate_borrower(seed=1)
        b = generate_borrower(seed=2)
        assert a != b

    def test_custom_borrower_id(self):
        b = generate_borrower(borrower_id="ent_custom_99")
        assert b.borrower_id == "ent_custom_99"

    def test_field_ranges_valid(self):
        for seed in range(20):
            b = generate_borrower(seed=seed)
            assert b.avg_monthly_inflow_brl > 0
            assert 0.0 <= b.inflow_cv <= 1.0
            assert b.distinct_payers >= 1
            assert b.account_age_months >= 1
            assert b.neg_balance_days >= 0
            assert 0 <= b.verified_count <= 4
            assert 0.0 <= b.profile_completeness <= 1.0


class TestGenerateBatch:
    def test_returns_correct_count(self):
        batch = generate_batch(10)
        assert len(batch) == 10

    def test_all_items_are_borrower_features(self):
        for b in generate_batch(5):
            assert isinstance(b, BorrowerFeatures)

    def test_ids_are_unique(self):
        batch = generate_batch(50)
        ids = [b.borrower_id for b in batch]
        assert len(set(ids)) == len(ids)

    def test_seed_is_deterministic(self):
        a = generate_batch(5, seed=7)
        b = generate_batch(5, seed=7)
        assert a == b


class TestGenerateLabeled:
    def test_returns_labeled_borrower(self):
        lb = generate_labeled()
        assert isinstance(lb, LabeledBorrower)

    def test_outcome_is_valid(self):
        valid = {"repaid_on_time", "repaid_late", "defaulted"}
        for seed in range(30):
            lb = generate_labeled(seed=seed)
            assert lb.simulated_outcome in valid

    def test_features_are_scorable(self):
        lb = generate_labeled(seed=0)
        result = score_borrower(lb.features)
        assert 300 <= result.trust_score <= 850


class TestGenerateLabeledBatch:
    def test_returns_correct_count(self):
        batch = generate_labeled_batch(20)
        assert len(batch) == 20

    def test_all_three_outcomes_present_in_large_batch(self):
        batch = generate_labeled_batch(200, seed=99)
        outcomes = {lb.simulated_outcome for lb in batch}
        assert outcomes == {"repaid_on_time", "repaid_late", "defaulted"}

    def test_all_scorable(self):
        for lb in generate_labeled_batch(10, seed=5):
            result = score_borrower(lb.features)
            assert result.borrower_id == lb.features.borrower_id
