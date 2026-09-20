"""Regression tests for app/ingest/lag_features.py — the train/serve contract.

Locks (per plan T7):
- determinism: same panel -> identical lags on repeated runs;
- look-ahead: a row's lags depend only on STRICTLY previous rows of the
  channel (masking the future must not change them);
- train/serve parity: the 11 values `lag_values_for_history` produces at
  decision day t equal the training row-t values of `compute_lags`, both on
  a synthetic panel and through the real LagStore on the production parquet;
- empty history -> NaN vector with the 9999 sentinels (documented).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.ingest.lag_features import (
    LAG_FEATURES,
    MISSING,
    add_lag_features,
    compute_lags,
    day_ordinal,
    lag_values_for_history,
)
from app.predict.lag_store import LagStore

FEAT_DIR = "/home/junai/lct/ml-data/features"


def _make_panel(tmp_path, name: str, rows: list[tuple[str, str, int, int]]) -> "Path":
    """rows: (channel, day, year, label) -> features-<name>.parquet in tmp_path."""
    from pathlib import Path

    df = pd.DataFrame(
        {
            "channel": [r[0] for r in rows],
            "day": [pd.Timestamp(r[1]) for r in rows],
            "year": [r[2] for r in rows],
            "label": [r[3] for r in rows],
        }
    )
    path = tmp_path / f"features-{name}.parquet"
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    return path


# ---------------------------------------------------------------------------
# small synthetic panel: 2 channels, known gaps
# ---------------------------------------------------------------------------
def _synthetic_rows():
    return [
        # channel A: 4 obs, labels 0,1,0,1 (2024-01-01 .. 2024-03-01)
        ("A", "2024-01-01", 2024, 0),
        ("A", "2024-01-10", 2024, 1),
        ("A", "2024-02-01", 2024, 0),
        ("A", "2024-03-01", 2024, 1),
        # channel B: 2 obs, far apart
        ("B", "2023-06-01", 2023, 1),
        ("B", "2024-05-01", 2024, 0),
    ]


@pytest.fixture(scope="module")
def panel(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lags")
    return _make_panel(tmp, "synthetic", _synthetic_rows())


@pytest.fixture(scope="module")
def computed(panel):
    return compute_lags(panel)


def test_determinism(panel, computed):
    again = compute_lags(panel)
    for k in LAG_FEATURES:
        assert np.array_equal(computed[k], again[k], equal_nan=True), k


def test_no_future_leakage_masking(panel):
    """Lags at row t must not change when rows at/after t are perturbed."""
    base = compute_lags(panel)
    rows = list(_synthetic_rows())
    # perturb channel A's 4th obs (2024-03-01, row idx 3) label, add a future
    # obs for channel B — neither may affect rows 0..2 (channel A's first 3)
    perturbed = list(rows)
    perturbed[3] = ("A", "2024-03-01", 2024, 1 - rows[3][3])
    perturbed.append(("B", "2024-06-15", 2024, 1))
    tmp = panel.parent / "perturbed.parquet"
    _make_panel2(tmp, perturbed)
    p = compute_lags(tmp)
    # rows 0..2 of channel A must be identical in both files
    for k in LAG_FEATURES:
        a = base[k][:3]
        b = p[k][:3]
        assert np.array_equal(a, b, equal_nan=True), f"{k} changed under future perturbation"


def _make_panel2(path, rows):
    df = pd.DataFrame(
        {
            "channel": [r[0] for r in rows],
            "day": [pd.Timestamp(r[1]) for r in rows],
            "year": [r[2] for r in rows],
            "label": [r[3] for r in rows],
        }
    )
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def test_add_lag_features_idempotent(panel):
    """Re-running the rewrite must not duplicate lag columns."""
    from pathlib import Path

    src = Path(panel)
    ref = add_lag_features(panel)
    assert ref == src
    names1 = list(pq.read_schema(src).names)
    add_lag_features(panel)
    names2 = list(pq.read_schema(src).names)
    assert names1 == names2
    assert sum(1 for c in names1 if c in set(LAG_FEATURES)) == 11
    assert [n for n in names1 if n in set(LAG_FEATURES)] == list(LAG_FEATURES)


def test_train_serve_parity_synthetic(panel, computed):
    """lag_values_for_history(history rows 0..t-1, t) == training row-t values."""
    ch = ["A", "A", "A", "A", "B", "B"]
    days = ["2024-01-01", "2024-01-10", "2024-02-01", "2024-03-01", "2023-06-01", "2024-05-01"]
    labels = [0, 1, 0, 1, 1, 0]
    d_ord = np.array([day_ordinal(d) for d in days])
    for t in range(len(ch)):
        # training row values for this channel's rows so far
        own = [i for i in range(t) if ch[i] == ch[t]]
        d = d_ord[own].astype(np.int64)
        y = np.array([labels[i] for i in own], dtype=np.float64)
        served = lag_values_for_history(d, y, day_ordinal(days[t]))
        for k in LAG_FEATURES:
            train_val = float(computed[k][t])
            assert np.isclose(served[k], train_val, equal_nan=True), (
                f"row {t} ({ch[t]}): {k} served={served[k]} train={train_val}"
            )


def test_empty_history_vector():
    v = lag_values_for_history(np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64), 100)
    assert set(v) == set(LAG_FEATURES)
    for k in LAG_FEATURES:
        if k in ("since_last_fail", "since_last_ok"):
            assert v[k] == MISSING, k
        elif k.startswith("n_obs_prev"):
            assert v[k] == 0.0, k
        else:
            assert np.isnan(v[k]), k


def test_same_day_rows_excluded_from_history():
    """A row observed on day t must not leak into the t-decision lags."""
    d = np.array([10, 11, 12], dtype=np.int64)
    y = np.array([1.0, 1.0, 1.0])
    v = lag_values_for_history(d, y, 11)  # only day 10 is strictly before 11
    assert v["n_obs_prev365"] == 1.0
    assert v["label_lag1"] == 1.0


# ---------------------------------------------------------------------------
# real data: LagStore on the production sensor-failure parquet
# ---------------------------------------------------------------------------
def test_store_parity_real_data():
    """store.lags_for(channel, as_of=day_t) == training lags of row t (1 sample)."""
    store = LagStore(feat_dir=FEAT_DIR)
    meta = store.load("sensor-failure")
    assert meta["status"] == "ok" and meta["n_channels"] > 0

    pf = pq.ParquetFile(f"{FEAT_DIR}/features-sensor-failure.parquet")
    rg = pf.read_row_group(0, columns=["channel", "day", "label"])
    ch, day, lab = rg.column("channel").to_numpy(), rg.column("day").to_pandas(), rg.column("label").to_numpy()
    pf.close()
    # first channel in row group 0, its 3rd day (enough history for lag2)
    cid = ch[0]
    own = [i for i in range(len(ch)) if ch[i] == cid][:4]
    assert len(own) >= 3
    t_idx = own[2]
    t_day = pd.Timestamp(day[t_idx]).to_pydatetime()

    served = store.lags_for("sensor-failure", cid, t_day)
    tr = compute_lags(f"{FEAT_DIR}/features-sensor-failure.parquet")
    for k in LAG_FEATURES:
        train_val = float(tr[k][t_idx])
        assert np.isclose(served[k], train_val, equal_nan=True), (
            f"{k}: store={served[k]} train={train_val}"
        )


def test_store_unknown_subject_nan_vector():
    store = LagStore(feat_dir=FEAT_DIR)
    v = store.lags_for("sensor-failure", "no-such-channel", "2026-09-20")
    assert set(v) == set(LAG_FEATURES)
    assert v["since_last_fail"] == MISSING and v["since_last_ok"] == MISSING
    assert np.isnan(v["label_lag1"])
