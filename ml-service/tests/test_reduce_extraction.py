"""The reducer is the single source of truth for classifying journal rows.

Both the CSV pipeline (``aggregate.py`` / ``hour_agg.py``) and the live
``events_log`` collector (ml-data-prep) must count a reading the same way —
alarm tokens, numeric values vs state names, ``01.01.1970`` date artifacts,
out-of-band gas codes — or freshly collected days would not look like the
history they get appended to.

These tests pin the counters on hand-built rows plus the chunk-merge property.
The previous implementation was additionally verified against this one on
169,993 real journal rows (``журнал_событий_пример.csv``): both the day and the
hour aggregate matched bit-for-bit, column order included.

Run from ml-service/:
    ./.venv/bin/python -m pytest tests -q
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ingest import reduce

COLUMNS = ["ид_канала_данных", "дата", "тревожное", "значение_датчика"]

# channel -> тип_датчика (what per_row_counts maps through before masking)
TYPES = pd.Series({"ch1": "Газовый датчик", "ch2": "Дымовой датчик"})

# ch1 = gas (327.68 is a coding artifact, >100 ppm), ch2 = ordinary sensor.
ROWS = [
    ("ch2", "2026-08-01", "false", "Норма"),          # state
    ("ch2", "2026-08-01", "true", "Неисправен"),      # state + alarm
    ("ch2", "2026-08-01", "false", "5"),              # numeric
    ("ch2", "2026-08-01", "maybe", "Неисправен"),     # unknown token -> dropped
    ("ch1", "2026-08-01", "false", "327.68"),         # gas artifact -> not numeric
    ("ch1", "2026-08-01", "false", "01.01.1970 03:00:01"),  # date fault
]


def journal(rows: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS)


def one_row(part: pd.DataFrame, channel: str) -> pd.Series:
    return part.set_index("channel").loc[channel]


# --- counters ---------------------------------------------------------------


def test_counters_are_counted_the_documented_way():
    part, stats = reduce.per_row_counts(journal(ROWS), TYPES)
    assert part is not None
    assert stats == {"raw": 6, "invalid": 2, "bad_hour": 0}  # 1 artifact + 1 date fault

    # ch2: three surviving rows (state, state+alarm, numeric 5)
    ch2 = one_row(part, "ch2")
    assert ch2["n_events"] == 3
    assert ch2["n_alarm"] == 1
    assert ch2["n_num"] == 1
    assert ch2["num_sum"] == pytest.approx(5.0)
    assert ch2["num_min"] == pytest.approx(5.0)
    assert ch2["num_max"] == pytest.approx(5.0)
    assert ch2["n_fault1970"] == 0
    assert ch2[f"s_{reduce.STATE_CODE['Норма']}"] == 1
    assert ch2[f"s_{reduce.STATE_CODE['Неисправен']}"] == 1

    # ch1: both rows survive as events, neither contributes a numeric value
    ch1 = one_row(part, "ch1")
    assert ch1["n_events"] == 2
    assert ch1["n_alarm"] == 0
    assert ch1["n_num"] == 0
    assert ch1["n_fault1970"] == 1
    assert np.isnan(ch1["num_min"]) and np.isnan(ch1["num_max"])
    assert ch1["num_sum"] == pytest.approx(0.0)


def test_unknown_alarm_token_drops_the_row():
    """Garbage rows (inline headers, unparsable flags) never reach the counters."""
    rows = [("ch2", "2026-08-01", "true", "5"), ("ch2", "2026-08-01", "header", "5")]
    part, stats = reduce.per_row_counts(journal(rows), TYPES)
    assert stats["raw"] == 2
    assert float(one_row(part, "ch2")["n_events"]) == 1


def test_row_without_channel_is_dropped():
    rows = [("ch2", "2026-08-01", "true", "5"), (None, "2026-08-01", "true", "5")]
    part, stats = reduce.per_row_counts(journal(rows), TYPES)
    assert stats["raw"] == 2
    assert float(one_row(part, "ch2")["n_events"]) == 1


def test_all_rows_filtered_returns_none():
    part, stats = reduce.per_row_counts(journal([("ch2", "2026-08-01", "?", "5")]), TYPES)
    assert part is None
    assert stats == {"raw": 1, "invalid": 0, "bad_hour": 0}


# --- chunking ---------------------------------------------------------------


def test_chunks_of_the_same_day_add_up():
    """A day split across chunks must give the same totals as one frame."""
    whole, _ = reduce.per_row_counts(journal(ROWS), TYPES)
    first, _ = reduce.per_row_counts(journal(ROWS[:2]), TYPES)
    second, _ = reduce.per_row_counts(journal(ROWS[2:]), TYPES)

    merged = reduce.reduce_parts([first, second], reduce.DAY_KEYS)
    assert len(merged) == len(whole)
    left = whole.sort_values("channel").reset_index(drop=True)
    right = merged.sort_values("channel").reset_index(drop=True)
    for col in left.columns:
        assert left[col].tolist() == pytest.approx(right[col].tolist()) or (
            left[col].astype(str).tolist() == right[col].astype(str).tolist()
        ), col


def test_reduce_parts_without_any_partial():
    empty = reduce.reduce_parts([None], reduce.DAY_KEYS)
    assert empty.empty
    assert list(empty.columns) == ["channel", "day", "n_events", "n_alarm", "n_num", "n_fault1970",
                                   "num_sum", "num_sumsq", "num_min", "num_max",
                                   *[f"s_{i}" for i in range(reduce.N_STATES)]]


# --- hour grain -------------------------------------------------------------


def test_hour_grain_uses_the_time_column():
    rows = [
        ("ch2", "2026-08-01", "06:15:00", "true", "5"),
        ("ch2", "2026-08-01", "06:45:00", "false", "Норма"),
        ("ch2", "2026-08-01", "", "false", "Норма"),  # missing time -> hour -1
    ]
    frame = pd.DataFrame(rows, columns=["ид_канала_данных", "дата", "время", "тревожное", "значение_датчика"])
    part, stats = reduce.per_row_counts(frame, TYPES, hour=True, fault1970=False)
    assert stats["bad_hour"] == 1
    assert "n_fault1970" not in part.columns
    hours = part.set_index("hour")["n_events"].to_dict()
    assert hours[6] == 2 and hours[-1] == 1


# --- finalize: dtypes, column order, artifact spans -------------------------


@pytest.fixture
def fake_ref(monkeypatch):
    """A two-channel channel reference, so no ml-data file is needed."""
    ref = pd.DataFrame(
        {
            "тип_датчика": ["Дымовой датчик", "Дымовой датчик"],
            "cabinet": pd.Categorical(["533", "847"]),
            "ид_объект": pd.Categorical(["obj-1", "obj-2"]),
        },
        index=pd.Index(["ch2", "ch3"], name="ид_канала_данных"),
    )
    monkeypatch.setattr(reduce, "channel_ref", lambda: ref)
    return ref


def test_finalize_column_order_and_dtypes(fake_ref):
    rows = [("ch2", "2026-08-01", "true", "5"), ("ch3", "2026-08-01", "false", "Норма")]
    part, _ = reduce.per_row_counts(journal(rows), TYPES)
    agg = reduce.finalize(reduce.reduce_parts([part], reduce.DAY_KEYS), 2026, reduce.DAY_KEYS)

    assert list(agg.columns) == [
        "channel", "day", "n_events", "n_alarm", "n_num", "n_fault1970",
        "num_sum", "num_sumsq", "num_min", "num_max",
        *[f"s_{i}" for i in range(reduce.N_STATES)],
        "cabinet", "ид_объект",
    ]  # exactly the historical agg-<year>.parquet layout
    assert agg["n_events"].dtype == np.int32
    assert agg["s_0"].dtype == np.int32
    assert agg["num_sum"].dtype == np.float32
    assert str(agg["cabinet"].dtype) == "category"
    assert str(agg["ид_объект"].dtype) == "category"


def test_finalize_drops_the_known_artifact_span(fake_ref):
    rows = [("ch3", "2021-05-15", "true", "5")]
    part, _ = reduce.per_row_counts(journal(rows), TYPES)
    span = reduce.reduce_parts([part], reduce.DAY_KEYS)

    dropped = reduce.finalize(span.copy(), 2021, reduce.DAY_KEYS)  # cabinet 847, in span
    kept = reduce.finalize(span.copy(), 2022, reduce.DAY_KEYS)  # other year -> kept
    assert dropped.empty
    assert len(kept) == 1
