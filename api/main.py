from fastapi import FastAPI
from scoring_engine import BorrowerFeatures, TrustScore, score_borrower
from scoring_engine.scorecard import MODEL_VERSION

app = FastAPI(
    title="Lumora Scoring API",
    description="Trust scoring for informal entrepreneurs (§8 of Lumora spec). POST /score → §5.1 TrustScore.",
    version=MODEL_VERSION,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_version": MODEL_VERSION}


@app.post("/score", response_model=TrustScore)
def score(features: BorrowerFeatures) -> TrustScore:
    return score_borrower(features)
