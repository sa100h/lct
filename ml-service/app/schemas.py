"""Pydantic schemas for ml-service REST endpoints.

Kept in a separate module so the prediction engine and FastAPI app can share
them without a circular import (main -> engine -> main).
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

PREDICTION_HORIZON_HOURS = int(os.environ.get("ML_HORIZON_HOURS", "24"))


class Category(str, Enum):
    """Public category names (hyphenated slugs, used in URLs and payloads)."""

    SENSOR_FAILURE = "sensor-failure"
    FIRE_RISK = "fire-risk"
    UNAUTHORIZED_ACCESS = "unauthorized-access"
    INFRASTRUCTURE_WEAR = "infrastructure-wear"


class PredictionRequest(BaseModel):
    category: Category
    subject_id: str = Field(..., description="Identifier of the forecast subject (sensor id, cell, shaft, hatch, ...).")
    current_features: dict[str, float | str] = Field(
        default_factory=dict,
        description="Latest feature vector; sensor readings may be numeric or textual.",
    )
    horizon_hours: int = Field(PREDICTION_HORIZON_HOURS, ge=1, le=168)


class Prediction(BaseModel):
    category: Category
    subject_id: str
    risk_score: float = Field(..., ge=0.0, le=1.0, description="P(failure within horizon).")
    probability: float = Field(..., ge=0.0, le=1.0, description="Model output before calibration/clipping.")
    predicted_label: bool
    horizon_hours: int
    predicted_at: datetime
    model_version: str
    feature_importance: dict[str, float] = Field(default_factory=dict)


class BatchPredictionRequest(BaseModel):
    """Score many channels across all four categories in one call.

    Used by ml-broker for forecast_journal batches (thousands of channels):
    one HTTP round-trip instead of thousands of /predict_all calls.
    `current_features` is PER-CHANNEL: ``{"<subject_id>": {"value": 0.42}}`` —
    keys that do not match a batch member are ignored. The legacy
    global-dict format is NOT supported (ml-broker is the only caller).
    """

    subject_ids: list[str] = Field(..., min_length=1, description="Channels to score (ml-service channel ids).")
    current_features: dict[str, dict[str, float | str]] = Field(
        default_factory=dict,
        description="Per-channel feature overrides: subject_id -> feature map.",
    )
    horizon_hours: int = Field(PREDICTION_HORIZON_HOURS, ge=1, le=168)
    as_of: datetime | None = Field(
        None,
        description="One as_of for the whole batch (forecast_journal.creation_time).",
    )


class BatchPredictionResponse(BaseModel):
    horizon_hours: int
    predictions: list[AllCategoriesResponse]


class AllCategoriesRequest(BaseModel):
    subject_id: str = Field(..., description="Sensor/channel id to score across all categories.")
    current_features: dict[str, float | str] = Field(
        default_factory=dict,
        description="Optional client-side feature overrides; sensor readings may be textual.",
    )
    horizon_hours: int = Field(PREDICTION_HORIZON_HOURS, ge=1, le=168)


class AllPrediction(BaseModel):
    category: Category
    applicable: bool = Field(
        ...,
        description="False when the channel never trained this category (wrong subsystem).",
    )
    prediction: Prediction | None = None


class AllCategoriesResponse(BaseModel):
    subject_id: str
    horizon_hours: int
    predictions: list[AllPrediction]


class StatusResponse(BaseModel):
    service: str
    state: str
    models: dict[str, dict]
    lags: dict[str, dict] = Field(default_factory=dict, description="Observation-store freshness per category.")
    now: datetime


class RetrainRequest(BaseModel):
    category: Category | None = Field(None, description="None = all categories.")
    engine: Literal["lgbm", "hgb"] = Field(
        "lgbm",
        description="Training engine: 'lgbm' = production LightGBM (model.lgb), 'hgb' = sklearn baseline fallback.",
    )
