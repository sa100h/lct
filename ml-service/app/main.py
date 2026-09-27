"""ML prediction service — LCT hackathon.

Exposes REST endpoints for the four forecast categories:
  - sensor-failure      (отказ датчика)
  - fire-risk           (пожарный риск)
  - unauthorized-access (несанкционированный доступ)
  - infrastructure-wear (износ инфраструктуры)
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

from fastapi import FastAPI, HTTPException

from app.models.baseline import BaselineTrainer
from app.models.registry import get_registry
from app.predict.engine import PredictEngine
from app.predict.lag_store import get_store
from app.schemas import (
    AllCategoriesRequest,
    AllCategoriesResponse,
    BatchPredictionRequest,
    BatchPredictionResponse,
    Category,
    Prediction,
    PredictionRequest,
    RetrainRequest,
    StatusResponse,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry = get_registry()
    # Train any category that has no persisted model yet (baseline for the hackathon
    # demo; replaced by real trained artifacts as data lands).
    for cat in Category:
        if registry.status(cat.value).state != "trained":
            BaselineTrainer().fit(cat.value)
    # Observation store: per-subject history for the 11 serve-time lag features.
    # Unavailable/failed -> lag values stay NaN (LightGBM-native), service runs on.
    store = get_store()
    for cat in Category:
        try:
            store.load(cat.value)
        except Exception:  # noqa: BLE001 — serving must not die on a stale store
            logger.exception("LagStore load failed for %s; lags -> NaN", cat.value)
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
    store = get_store()
    lags = {
        c.value: {
            "status": store._meta.get(c.value, {}).get("status", "not_loaded"),
            "n_channels": store._meta.get(c.value, {}).get("n_channels"),
            "n_rows": store._meta.get(c.value, {}).get("n_rows"),
            "max_day": store._meta.get(c.value, {}).get("max_day"),
        }
        for c in Category
    }
    return StatusResponse(
        service="ml-service",
        state="ready",
        models={c.value: asdict(registry.status(c.value)) for c in Category},
        lags=lags,
        now=datetime.now(timezone.utc),
    )


@app.post("/predict", response_model=Prediction)
def predict(req: PredictionRequest) -> Prediction:
    engine: PredictEngine = app.state.engine
    try:
        return engine.predict(req.category.value, req.subject_id, req.current_features, req.horizon_hours)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/predict_all", response_model=AllCategoriesResponse)
def predict_all(req: AllCategoriesRequest) -> AllCategoriesResponse:
    """All four categories for one incoming sensor signal in a single run."""
    engine: PredictEngine = app.state.engine
    try:
        return engine.predict_all(req.subject_id, req.current_features, req.horizon_hours)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/predict_all_batch", response_model=BatchPredictionResponse)
def predict_all_batch(req: BatchPredictionRequest) -> BatchPredictionResponse:
    """All four categories for a batch of channels (forecast_journal workloads)."""
    engine: PredictEngine = app.state.engine
    try:
        predictions = engine.predict_all_batch(
            req.subject_ids, req.current_features, req.horizon_hours, as_of=req.as_of
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BatchPredictionResponse(horizon_hours=req.horizon_hours, predictions=predictions)


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
        # Fresh serve-time lags after a retrain (lag_store reads the same parquet).
        try:
            get_store().refresh(cat.value)
        except Exception:  # noqa: BLE001
            logger.exception("LagStore refresh failed for %s", cat.value)
    return {"retrained": results}
