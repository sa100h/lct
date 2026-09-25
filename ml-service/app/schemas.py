"""Pydantic schemas for ml-service REST endpoints.

Kept in a separate module so the prediction engine and FastAPI app can share
them without a circular import (main -> engine -> main).
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum

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
    current_features: dict[str, float] = Field(
        default_factory=dict,
        description="Latest feature vector for the subject. Keys are category feature names.",
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


class AllCategoriesRequest(BaseModel):
    subject_id: str = Field(..., description="Sensor/channel id to score across all categories.")
    current_features: dict[str, float] = Field(
        default_factory=dict,
        description="Optional client-side feature overrides (same names as /predict).",
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
