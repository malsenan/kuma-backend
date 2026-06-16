# Lumora — Vendor Borrower Trust Model

A trust scoring system for informal women entrepreneurs in Brazil (MEI holders, autônomas, micro-business owners). Scores the probability that a borrower will repay a loan using alternative financial data (PIX / Open Finance) and qualitative signals, with a plain-language explanation for investors.

Full technical specification: [`Lumora_Spec_MD.md`](./Lumora_Spec_MD.md)

---

## What's been built

### Scoring engine (`scoring_engine/`)
Rules-based scorecard (Phase 0, §10 of spec). No training data required.

| File | What it does |
|------|-------------|
| `models.py` | Pydantic input/output types — `BorrowerFeatures`, `TrustScore` and supporting models |
| `scorecard.py` | `score_borrower(features) → TrustScore` — 7-factor weighted scorecard, 300–850 display scale |
| `extractor.py` | `extract_features(transactions, accounts, profile) → BorrowerFeatures` — turns raw Belvo-style transaction JSON into the flat feature row the scorer expects |
| `synthetic.py` | Faker (pt_BR) generators for borrower records and labeled outcomes — used for testing and demos |

### REST API (`api/`)
FastAPI wrapper around the scoring engine.

| Endpoint | What it does |
|----------|-------------|
| `GET /health` | Liveness check — returns `{"status": "ok", "model_version": "..."}` |
| `POST /score` | Accepts `BorrowerFeatures` JSON, returns `TrustScore` JSON (§5.1 of spec). Pydantic validation → 422 on bad input. |

Auto-generated Swagger UI at `/docs` when running locally.

---

## Pipeline

```
RawTransaction[] + RawAccount[]     ← Belvo / Pluggy API (or sandbox)
  + ProfileMeta                     ← onboarding form
      │
      ▼
  extract_features()                ← scoring_engine/extractor.py
      │
      ▼
  BorrowerFeatures (flat row)
      │
      ▼
  score_borrower()                  ← scoring_engine/scorecard.py
      │
      ▼
  TrustScore (JSON)                 ← §5.1 of spec
    payback_probability: 0.81
    trust_score: 718
    risk_band: "B"
    confidence: 0.75
    recommended_loan_brl: 1500
    explanation: { top_positive_factors, top_negative_factors }
```

---

## Scorecard factors (Phase 0)

| # | Factor | Weight | Source |
|---|--------|--------|--------|
| 1 | Debt-service capacity (income ÷ repayment) | 25% | Open Finance / PIX |
| 2 | Income stability (inflow CV) | 20% | Open Finance / PIX |
| 3 | Business / account tenure | 15% | Open Finance / PIX |
| 4 | Customer base breadth (distinct payers) | 10% | Open Finance / PIX |
| 5 | Cash management (negative-balance days) | 10% | Open Finance / PIX |
| 6 | Verification (ID, address, MEI, bank) | 10% | Documents |
| 7 | Profile completeness (photos, online presence) | 10% | Profile form |

Demographics (gender, location) are collected for bias monitoring only and never enter the scorer (LGPD compliance, §4-C of spec).

---

## Tests

153 tests, 0 failures.

| File | Type | Count |
|------|------|-------|
| `tests/test_smoke.py` | Smoke | 6 |
| `tests/test_scorecard.py` | Unit | 33 |
| `tests/test_synthetic.py` | Unit | 15 |
| `tests/test_regression.py` | Regression | 34 |
| `tests/test_api.py` | Smoke / Unit / Validation / Regression | 19 |
| `tests/test_extractor.py` | Unit / Edge / Regression / Integration | 46 |

---

## Getting started

```bash
# 1. Create and activate venv
python -m venv .venv
source .venv/bin/activate

# 2. Install (scoring engine + API + dev tools)
pip install -e ".[api,dev]"

# 3. Run tests
pytest tests/ -v

# 4. Start the API
uvicorn api.main:app --reload
# Swagger UI → http://localhost:8000/docs
```

---

## What's next (planned subproblems)

- [ ] Synthetic transaction generator — Faker-based Belvo-shaped JSON for demo flows
- [ ] Feature store — persist extracted feature rows to Postgres
- [ ] `POST /score/full` — accepts raw Belvo JSON + profile form, runs extractor then scorer in one call
- [ ] XGBoost pipeline — proven on Kaggle Home Credit dataset (scaffold for Phase 2 ML)
- [ ] Investor and entrepreneur portals (React PWA)
