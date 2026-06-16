"""Synthetic borrower generator for testing and demo flows.

Uses Faker (pt_BR) to produce realistic-looking Brazilian borrower records.
Labels are simulated — clearly tagged, never used to claim model accuracy (§6 of spec).
"""

import random
from dataclasses import dataclass

from faker import Faker

from .models import BorrowerFeatures

_fake = Faker("pt_BR")


@dataclass
class LabeledBorrower:
    features: BorrowerFeatures
    simulated_outcome: str  # "repaid_on_time" | "repaid_late" | "defaulted"


def generate_borrower(
    borrower_id: str | None = None,
    seed: int | None = None,
) -> BorrowerFeatures:
    """Generate a single synthetic borrower feature row."""
    if seed is not None:
        random.seed(seed)
        Faker.seed(seed)

    bid = borrower_id or f"ent_demo_{_fake.uuid4()[:8]}"
    avg_inflow = round(random.uniform(600, 6000), 2)

    return BorrowerFeatures(
        borrower_id=bid,
        avg_monthly_inflow_brl=avg_inflow,
        inflow_cv=round(random.uniform(0.05, 0.95), 2),
        distinct_payers=random.randint(1, 60),
        account_age_months=random.randint(1, 72),
        neg_balance_days=random.randint(0, 20),
        proposed_monthly_repayment_brl=round(avg_inflow * random.uniform(0.08, 0.45), 2),
        verified_count=random.randint(0, 4),
        profile_completeness=round(random.uniform(0.0, 1.0), 2),
        has_financial_api=random.random() > 0.15,
        has_documents=random.random() > 0.40,
        has_photos=random.random() > 0.55,
        has_online_presence=random.random() > 0.65,
    )


def generate_labeled(
    borrower_id: str | None = None,
    seed: int | None = None,
) -> LabeledBorrower:
    """Generate a borrower + a simulated repayment outcome.

    Outcome probability is loosely correlated with financial health so the
    synthetic dataset is plausible for pipeline testing. Not calibrated —
    do not use to train or evaluate the real model.
    """
    features = generate_borrower(borrower_id=borrower_id, seed=seed)

    # Rough heuristic: higher income / lower volatility / more verified → more likely to repay
    score_proxy = (
        min(features.avg_monthly_inflow_brl / 3000, 1.0) * 0.4
        + max(0, 1 - features.inflow_cv) * 0.3
        + (features.verified_count / 4) * 0.2
        + features.profile_completeness * 0.1
    )
    roll = random.random()
    if roll < score_proxy * 0.75:
        outcome = "repaid_on_time"
    elif roll < score_proxy * 0.75 + 0.15:
        outcome = "repaid_late"
    else:
        outcome = "defaulted"

    return LabeledBorrower(features=features, simulated_outcome=outcome)


def generate_batch(n: int, seed: int | None = None) -> list[BorrowerFeatures]:
    """Generate n unlabeled borrower records."""
    if seed is not None:
        random.seed(seed)
        Faker.seed(seed)
    return [generate_borrower(borrower_id=f"ent_demo_{i:04d}") for i in range(n)]


def generate_labeled_batch(n: int, seed: int | None = None) -> list[LabeledBorrower]:
    """Generate n labeled borrower records for pipeline testing."""
    if seed is not None:
        random.seed(seed)
        Faker.seed(seed)
    return [generate_labeled(borrower_id=f"ent_demo_{i:04d}") for i in range(n)]
