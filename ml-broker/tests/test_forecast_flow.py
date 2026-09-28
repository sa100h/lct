from __future__ import annotations

from datetime import datetime, timezone

from app.db import QueueRow
from app.forecast_flow import (
    ML_BROKER_UUID,
    build_chunks,
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


T = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def _row(i, subject, cat, journal, as_of, features=None):
    return QueueRow(
        id=i,
        category=cat,
        subject_id=subject,
        as_of=as_of,
        priority=1,
        attempts=0,
        features=features if features is not None else {"value": i},
        forecast_journal_id=journal,
    )


def test_chunks_never_span_journals():
    rows = [
        _row(1, "ch-1", "fire-risk", "j1", T),
        _row(2, "ch-1", "sensor-failure", "j2", T),
    ]
    chunks = build_chunks(rows, max_subjects=10)
    assert [c.journal_id for c in chunks] == ["j1", "j2"]
    assert chunks[0].subjects == ["ch-1"]
    assert chunks[0].as_of == T


def test_chunks_respect_subject_limit_and_merge_categories():
    rows = [
        _row(1, "ch-1", "fire-risk", "j1", T),
        _row(2, "ch-1", "sensor-failure", "j1", T),
        _row(3, "ch-2", "fire-risk", "j1", T),
        _row(4, "ch-3", "fire-risk", "j1", T),
    ]
    chunks = build_chunks(rows, max_subjects=2)
    assert len(chunks) == 2
    assert chunks[0].subjects == ["ch-1", "ch-2"]
    assert len(chunks[0].rows) == 3  # ch-1 принёс 2 строки (2 категории)
    assert chunks[0].features["ch-1"] == {"value": 1}
    assert [r.id for r in chunks[1].rows] == [4]


def test_subject_over_limit_stays_in_one_chunk():
    # ch-2 начинается ровно на границе лимита: открывается новый чанк,
    # но обе категории ch-2 остаются вместе (не режутся между чанками)
    rows = [
        _row(1, "ch-1", "fire-risk", "j1", T),
        _row(2, "ch-2", "fire-risk", "j1", T),
        _row(3, "ch-2", "sensor-failure", "j1", T),
    ]
    chunks = build_chunks(rows, max_subjects=1)
    assert len(chunks) == 2
    assert chunks[0].subjects == ["ch-1"]
    assert chunks[1].subjects == ["ch-2"]
    assert [r.category for r in chunks[1].rows] == ["fire-risk", "sensor-failure"]
