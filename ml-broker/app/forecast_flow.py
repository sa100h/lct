"""Pure forecast-flow rules shared by the database worker and tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

ML_BROKER_UUID = "77d902da-9f82-40cf-9674-926d4c04243d"
HORIZON_HOURS = 24
# Machine-readable marker for categories a channel never trained on
# (feature_engine.CATS gate in ml-service). Consumers must key on this
# value, not on the absence of the channel.
UNPREDICTABLE = "unpredictable"

# sensor_types from 016_1_add_data_dictionary.sql. Keep this explicit until
# category applicability becomes data-driven.
SENSOR_TYPE_CATEGORIES: dict[int, tuple[str, ...]] = {
    1: ("sensor-failure", "unauthorized-access"),
    2: ("sensor-failure", "unauthorized-access"),
    3: ("sensor-failure", "unauthorized-access"),
    4: ("sensor-failure", "unauthorized-access"),
    5: ("sensor-failure", "unauthorized-access"),
    6: ("sensor-failure", "unauthorized-access"),
    7: ("sensor-failure", "fire-risk"),
    8: ("sensor-failure", "fire-risk"),
    9: ("sensor-failure", "fire-risk"),
    10: ("sensor-failure", "fire-risk"),
    11: ("sensor-failure", "fire-risk"),
    12: ("sensor-failure", "infrastructure-wear"),
    13: ("sensor-failure", "infrastructure-wear"),
    14: ("sensor-failure", "infrastructure-wear"),
    15: ("sensor-failure", "infrastructure-wear"),
    16: ("sensor-failure", "infrastructure-wear"),
    17: ("sensor-failure", "infrastructure-wear"),
    18: ("sensor-failure", "fire-risk"),
    19: ("sensor-failure", "infrastructure-wear"),
}


def categories_for_sensor_type(sensor_type_id: int) -> tuple[str, ...]:
    return SENSOR_TYPE_CATEGORIES.get(sensor_type_id, ("sensor-failure",))


def build_features(value: Any) -> dict[str, Any]:
    """Keep the app-service reading literal; ml-service decides its validity."""
    return {"value": value}


def _iso(value: datetime) -> str:
    value = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def build_result_description(predictions: list[dict[str, Any]], creation_time: datetime) -> dict[str, Any]:
    valid_from = _iso(creation_time)
    valid_to = _iso(creation_time + timedelta(hours=HORIZON_HOURS))
    channels: dict[str, dict[str, dict[str, Any]]] = {}
    for prediction in predictions:
        entry = (
            {"status_code": UNPREDICTABLE}
            if prediction.get("applicable") is False
            else {
                "value": float(prediction["risk_score"]),
                "valid_from": valid_from,
                "valid_to": valid_to,
            }
        )
        channels.setdefault(str(prediction["subject_id"]), {})[str(prediction["category"])] = entry
    return {"channels": channels}


@dataclass
class PredictChunk:
    """One /predict_all_batch call: subjects of a single journal + their rows."""

    journal_id: str | None
    as_of: datetime
    subjects: list[str] = field(default_factory=list)
    features: dict[str, dict[str, Any]] = field(default_factory=dict)
    rows: list[Any] = field(default_factory=list)  # QueueRow; Any avoids a db import cycle


def build_chunks(rows: list[Any], max_subjects: int) -> list[PredictChunk]:
    """Group queue rows into /predict_all_batch chunks.

    Invariants: input order is (forecast_journal_id, id) — claim_batch
    guarantees it; one chunk never spans two journals (each journal has its
    own as_of); a subject's category rows never split across chunks (a
    boundary-starting subject overflows the chunk by one instead).
    """
    chunks: list[PredictChunk] = []
    cur: PredictChunk | None = None
    for row in rows:
        boundary = (
            cur is None
            or cur.journal_id != row.forecast_journal_id
            or cur.as_of != row.as_of
            or (len(cur.subjects) >= max_subjects and row.subject_id not in cur.features)
        )
        if boundary:
            cur = PredictChunk(journal_id=row.forecast_journal_id, as_of=row.as_of)
            chunks.append(cur)
        assert cur is not None  # narrowed by the boundary check above
        if row.subject_id not in cur.features:
            cur.subjects.append(row.subject_id)
            cur.features[row.subject_id] = row.features
        cur.rows.append(row)
    return chunks
