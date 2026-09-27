"""Pure forecast-flow rules shared by the database worker and tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

ML_BROKER_UUID = "77d902da-9f82-40cf-9674-926d4c04243d"
HORIZON_HOURS = 24

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
        channels.setdefault(str(prediction["subject_id"]), {})[str(prediction["category"])] = {
            "value": float(prediction["risk_score"]),
            "valid_from": valid_from,
            "valid_to": valid_to,
        }
    return {"channels": channels}
