# Claude instructions for this project

## Environment

Always use the `.venv` at the project root. Never install packages on system Python.

```bash
# Install
.venv/bin/pip install -e ".[api,dev]"

# Test
.venv/bin/pytest tests/ -v

# Run API
.venv/bin/uvicorn api.main:app --reload
```

## Phase 0 scope

The current implementation is a **rules-based scorecard only**. Do not introduce XGBoost, LightGBM, or any ML model yet. The spec calls this Phase 2 — it requires real loan outcome labels that don't exist yet. The scorecard is the mechanism that generates those labels.

## Hard constraints (LGPD + bias)

Demographics — gender, location, residential moves — are **never** passed to `score_borrower()` or included in `BorrowerFeatures`. They live in the profile table for display and bias monitoring only. This is resolved in §4-C of the spec; don't reopen it.

## Regression tests

When you intentionally change a band threshold, weight, or the `payback_probability` formula in `scorecard.py`:

1. Recompute the affected pinned values by running the scorer against the fixture inputs directly in a Python snippet before editing the test.
2. Update `tests/test_regression.py` and `tests/test_extractor.py` with the new values.
3. Document what changed and why in the commit message.

Do **not** silently update a pinned value to make a test pass without understanding why it changed.

## Project structure

```
scoring_engine/   — core Python package (models, scorecard, extractor, synthetic data)
api/              — FastAPI wrapper (GET /health, POST /score)
tests/            — pytest suite (153 tests: smoke, unit, regression, integration)
Lumora_Spec_MD.md — full technical spec; read this for any ambiguity about inputs/outputs
```

## Spec is the source of truth

When in doubt about field names, feature definitions, output schema, or scoring weights, read `Lumora_Spec_MD.md` before making assumptions. Key sections: §4-B (features), §5.1 (TrustScore output), §10 (scorecard pseudocode).
