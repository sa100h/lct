"""ML prediction service — LCT hackathon.

Exposes REST endpoints for the four forecast categories:
  - sensor-failure      (отказ датчика)
  - fire-risk           (пожарный риск)
  - unauthorized-access (несанкционированный доступ)
  - infrastructure-wear (износ инфраструктуры)
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from app.models.baseline import BaselineTrainer
from app.models.registry import get_registry
from app.predict.engine import PredictEngine
from app.schemas import Category, Prediction, PredictionRequest, RetrainRequest, StatusResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry = get_registry()
    # Train any category that has no persisted model yet (baseline for the hackathon
    # demo; replaced by real trained artifacts as data lands).
    for cat in Category:
        if registry.status(cat.value).state != "trained":
            BaselineTrainer().fit(cat.value)
    app.state.engine = PredictEngine()
    yield


app = FastAPI(
    title="lct-ml-service",
    description="Predictive forecasting for Moskollektor engineering collectors (4 categories).",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    from dataclasses import asdict

    registry = get_registry()
    return StatusResponse(
        service="ml-service",
        state="ready",
        models={c.value: asdict(registry.status(c.value)) for c in Category},
        now=datetime.now(timezone.utc),
    )


@app.post("/predict", response_model=Prediction)
def predict(req: PredictionRequest) -> Prediction:
    engine: PredictEngine = app.state.engine
    try:
        return engine.predict(req.category.value, req.subject_id, req.current_features, req.horizon_hours)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/retrain")
def retrain(req: RetrainRequest) -> dict:
    """Retrain from ingested data (data/<category>/*.parquet|csv). Hackathon hook:
    feed it with real historical data after ingest/transform."""
    registry = get_registry()
    trainer = BaselineTrainer()
    results = {}
    targets = [req.category] if req.category else list(Category)
    for cat in targets:
        try:
            metrics = trainer.fit(cat.value)
        except Exception as exc:  # noqa: BLE001 — report per-category, don't fail the batch
            metrics = {"state": "failed", "error": str(exc)}
        results[cat.value] = registry.status(cat.value).state if "state" not in metrics else metrics
    return {"retrained": results}
