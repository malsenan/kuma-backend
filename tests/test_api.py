import pytest
from fastapi.testclient import TestClient
from api.main import app
from scoring_engine.scorecard import MODEL_VERSION

client = TestClient(app)

# Shared valid payload
VALID_BODY = dict(
    borrower_id="api_test_001",
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

STRONG_BODY = dict(
    borrower_id="api_strong",
    avg_monthly_inflow_brl=5000.0,
    inflow_cv=0.10,
    distinct_payers=25,
    account_age_months=36,
    neg_balance_days=0,
    proposed_monthly_repayment_brl=400.0,
    verified_count=4,
    profile_completeness=1.0,
    has_financial_api=True,
    has_documents=True,
    has_photos=True,
    has_online_presence=True,
)

WEAK_BODY = dict(
    borrower_id="api_weak",
    avg_monthly_inflow_brl=600.0,
    inflow_cv=0.85,
    distinct_payers=2,
    account_age_months=3,
    neg_balance_days=10,
    proposed_monthly_repayment_brl=400.0,
    verified_count=0,
    profile_completeness=0.1,
    has_financial_api=True,
    has_documents=False,
    has_photos=False,
    has_online_presence=False,
)


# ── Smoke ─────────────────────────────────────────────────────────────────────

def test_health_returns_200():
    r = client.get("/health")
    assert r.status_code == 200

def test_health_body():
    r = client.get("/health")
    assert r.json() == {"status": "ok", "model_version": MODEL_VERSION}

def test_score_returns_200():
    r = client.post("/score", json=VALID_BODY)
    assert r.status_code == 200


# ── Unit ──────────────────────────────────────────────────────────────────────

def test_score_borrower_id_round_trips():
    r = client.post("/score", json=VALID_BODY)
    assert r.json()["borrower_id"] == "api_test_001"

def test_score_trust_score_in_range():
    r = client.post("/score", json=VALID_BODY)
    ts = r.json()["trust_score"]
    assert 300 <= ts <= 850

def test_score_risk_band_valid():
    r = client.post("/score", json=VALID_BODY)
    assert r.json()["risk_band"] in ("A", "B", "C", "D", "E")

def test_score_payback_probability_in_range():
    r = client.post("/score", json=VALID_BODY)
    p = r.json()["payback_probability"]
    assert 0.0 <= p <= 1.0

def test_score_response_has_explanation():
    r = client.post("/score", json=VALID_BODY)
    body = r.json()
    assert "explanation" in body
    assert "top_positive_factors" in body["explanation"]

def test_score_response_has_data_completeness():
    r = client.post("/score", json=VALID_BODY)
    assert "data_completeness" in r.json()

def test_score_model_version_present():
    r = client.post("/score", json=VALID_BODY)
    assert r.json()["model_version"] == MODEL_VERSION


# ── Validation ────────────────────────────────────────────────────────────────

def test_missing_required_field_returns_422():
    body = {k: v for k, v in VALID_BODY.items() if k != "borrower_id"}
    r = client.post("/score", json=body)
    assert r.status_code == 422

def test_wrong_type_returns_422():
    body = {**VALID_BODY, "avg_monthly_inflow_brl": "not_a_number"}
    r = client.post("/score", json=body)
    assert r.status_code == 422

def test_negative_inflow_returns_422():
    body = {**VALID_BODY, "avg_monthly_inflow_brl": -100.0}
    r = client.post("/score", json=body)
    assert r.status_code == 422

def test_verified_count_above_max_returns_422():
    body = {**VALID_BODY, "verified_count": 5}
    r = client.post("/score", json=body)
    assert r.status_code == 422

def test_empty_body_returns_422():
    r = client.post("/score", json={})
    assert r.status_code == 422


# ── Regression ────────────────────────────────────────────────────────────────

def test_strong_borrower_pinned_trust_score():
    r = client.post("/score", json=STRONG_BODY)
    assert r.json()["trust_score"] == 850

def test_strong_borrower_pinned_risk_band():
    r = client.post("/score", json=STRONG_BODY)
    assert r.json()["risk_band"] == "A"

def test_weak_borrower_pinned_trust_score():
    r = client.post("/score", json=WEAK_BODY)
    assert r.json()["trust_score"] == 377

def test_weak_borrower_pinned_risk_band():
    r = client.post("/score", json=WEAK_BODY)
    assert r.json()["risk_band"] == "E"
