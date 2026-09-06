"""Feature schemas per forecast category.

Each category lists the expected feature names. Real feature engineering
(from SMVU logs, ODS journals, equipment registers, ARM-Kontrol) lands in
ingest/transform.py; until then the baseline trainer uses these names so the
whole pipeline (train -> predict -> dashboard) runs end to end.
"""

from __future__ import annotations

FEATURE_SCHEMAS: dict[str, list[str]] = {
    "sensor-failure": [
        "false_alarm_rate_7d",
        "noise_frequency_7d",
        "signal_deviation_std",
        "days_since_last_repair",
        "repair_count_365d",
        "sensor_age_days",
    ],
    "fire-risk": [
        "temperature_delta_1h",
        "smoke_density_1h",
        "gas_ppm_1h",
        "hot_work_within_24h",
        "welding_permits_within_7d",
        "multi_sensor_correlation",
    ],
    "unauthorized-access": [
        "contact_zone_trips_7d",
        "volume_sensor_trips_7d",
        "access_outside_permits_7d",
        "ac_system_mismatches_7d",
        "night_trips_ratio",
        "permit_coverage_ratio",
    ],
    "infrastructure-wear": [
        "equipment_age_days",
        "usage_intensity_index",
        "visual_inspection_score",
        "repair_history_count_5y",
        "days_since_last_inspection",
        "weather_season_risk",
    ],
}


def features_for(category: str) -> list[str]:
    if category not in FEATURE_SCHEMAS:
        raise KeyError(f"Unknown category '{category}'. Expected one of: {sorted(FEATURE_SCHEMAS)}")
    return list(FEATURE_SCHEMAS[category])


def schema_default_vector(category: str) -> dict[str, float]:
    """Zero vector — used when a caller does not send features yet."""
    return {name: 0.0 for name in features_for(category)}
