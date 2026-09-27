from __future__ import annotations

from datetime import datetime, timezone

from app.forecast_flow import (
    ML_BROKER_UUID,
    build_features,
    categories_for_sensor_type,
    build_result_description,
)


def test_sensor_type_mapping_is_hardcoded_to_applicable_categories():
    assert categories_for_sensor_type(7) == ("sensor-failure", "fire-risk")
    assert categories_for_sensor_type(2) == ("sensor-failure", "unauthorized-access")
    assert categories_for_sensor_type(19) == ("sensor-failure", "infrastructure-wear")
    assert categories_for_sensor_type(999) == ("sensor-failure",)


def test_forecast_channel_values_keep_numeric_and_non_numeric_values():
    assert build_features("23.5") == {"value": "23.5"}
    assert build_features("open") == {"value": "open"}
    assert build_features(None) == {"value": None}


def test_result_description_is_nested_by_channel_and_contains_validity_window():
    start = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
    description = build_result_description(
        [
            {"subject_id": "120578", "category": "fire-risk", "risk_score": 0.81},
            {"subject_id": "120579", "category": "sensor-failure", "risk_score": 0.12},
        ],
        start,
    )
    assert description["channels"]["120578"]["fire-risk"]["value"] == 0.81
    assert description["channels"]["120578"]["fire-risk"]["valid_from"] == "2026-09-27T18:00:00Z"
    assert description["channels"]["120578"]["fire-risk"]["valid_to"] == "2026-09-28T18:00:00Z"
    assert ML_BROKER_UUID == "77d902da-9f82-40cf-9674-926d4c04243d"
