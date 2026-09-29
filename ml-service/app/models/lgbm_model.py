"""LightGBM training engine — production replacement for HGB (baseline.py).

This is the engine the lag experiment ran with (ml-data/lags/lag-model-results.json).
HGB stays available as the `--engine hgb` fallback in scripts/train.py; this module
never touches the HGB path.

Design notes
- Streaming split: pass 1 reads only `year` row-group by row-group and builds the
  train/valid/test bool masks (with a deterministic seed-42 subsample for train);
  pass 2 streams all feature columns into preallocated float32 buffers. Same
  OOM recipe as baseline._train_real (box has 3.8 GB), MAX_TRAIN_ROWS capped.
- Fit: low-level lgb.train (binary, metric=auc). Tuning uses early stopping on
  valid=2025 (scripts/tune_lgbm.py); the final fit runs a fixed number of rounds
  (best_iteration, no early stopping) so 2026 is opened exactly once.
- Artifact: booster.save_model(models/<cat>/model.lgb) — text, compact; loaded
  via lgb.Booster. Serving call is Booster.predict(row) -> P(fail) (the
  predict engine abstracts the predict_proba / predict difference).
- NaN policy: the store supplies NaN for subjects without history; LightGBM
  handles NaN natively, no imputation.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegressionCV
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.ingest.lag_features import LAG_SET
from app.config import FEATURES_DIR
from app.models.fsutil import atomic_write
from app.models.registry import CATEGORIES

META = ("channel", "day", "year", "label")
SEED = 42
# Env-driven (app/config.py) — a hardcoded host path breaks inside the container.
FEAT_DIR = FEATURES_DIR


def _env_int(name: str, default: int) -> int:
    """Positive int from the environment, else ``default`` (IGNORES junk)."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


# Memory knob. These two caps size the in-RAM train/valid matrices that
# stream_split materializes (float32, ~197 cols): 1M train rows is ~790 MB, and
# LightGBM's Dataset construction adds its own copy on top. On the 3.9 GB box a
# full-cap fit with little free RAM gets SIGKILLed (exit 137). Override for a
# tighter box WITHOUT editing code:
#     LCT_MAX_TRAIN_ROWS=400000 LCT_MAX_VALID_ROWS=150000 python -m scripts.train ...
# Defaults are unchanged, so production behaviour is identical unless set.
MAX_TRAIN_ROWS = _env_int("LCT_MAX_TRAIN_ROWS", 1_000_000)
MAX_VALID_ROWS = _env_int("LCT_MAX_VALID_ROWS", 500_000)

# Experiment params (scripts/_lag_model.py) — the known-good default.
LGB_PARAMS_DEFAULT: dict = dict(
    objective="binary",
    learning_rate=0.08,
    num_leaves=31,
    min_data_in_leaf=20,
    feature_fraction=0.9,
    bagging_fraction=0.9,
    bagging_freq=1,
    is_unbalance=True,
    seed=SEED,
    n_jobs=-1,
    verbose=-1,
)
DEFAULT_ROUNDS = 300


def engine_tag() -> str:
    return f"lightgbm-{lgb.__version__}"


def feature_columns(parquet_path, exclude_lags: bool = False) -> list[str]:
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(parquet_path)
    names = [c for c in pf.schema_arrow.names if c not in META]
    if exclude_lags:
        names = [c for c in names if c not in LAG_SET]
    return names


def _subsample(sel: np.ndarray, idx: np.ndarray, max_rows: int, rng) -> np.ndarray:
    """Seeded subsample mask (same idx order as flatnonzero)."""
    out = np.zeros(len(sel), dtype=bool)
    if len(idx) <= max_rows:
        sel[idx] = True
    else:
        ratio = max_rows / len(idx)
        sel[idx[rng.random(len(idx)) < ratio]] = True
    return out


def stream_split(
    parquet_path,
    train_max_year: int = 2026,
    valid_year: int | None = None,
    test_year: int = 2026,
    max_train_rows: int = MAX_TRAIN_ROWS,
    max_valid_rows: int = MAX_VALID_ROWS,
    seed: int = SEED,
    exclude_lags: bool = False,
    spatial_path=None,
) -> dict:
    """Stream parquet twice -> train/valid/test arrays (memory-safe).

    train: years < train_max_year (seeded subsample when over max_train_rows)
    valid: years == valid_year (seeded subsample when over max_valid_rows) or None
    test:  years == test_year (always full — opened once at the end)
    Feature order = file column order minus META (lags included unless
    exclude_lags), plus spatial columns appended when spatial_path is set.
    spatial_path: parquet with channel + day keys (spatial.parquet); left-joined
    row-group by row-group, NaN where no match (LightGBM handles NaN).
    Returns: names, Xtr, ytr, Xva|None, yva|None, Xte, yte, n, spatial.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(parquet_path)
    names = feature_columns(parquet_path, exclude_lags=exclude_lags)

    # Spatial join: sorted composite keys + float32 column arrays, built once.
    sp_names: list[str] = []
    sp_keys: np.ndarray | None = None
    sp_cols: dict | None = None
    if spatial_path is not None:
        import pandas as pd

        sp_schema = [c for c in pq.ParquetFile(spatial_path).schema_arrow.names]
        sp_names = [c for c in sp_schema if c not in ("channel", "day", "year")]
        sdf = pd.read_parquet(spatial_path)
        keys = np.array(
            [f"{c}|{str(d)[:10]}" for c, d in zip(sdf["channel"], sdf["day"])],
            dtype=object,
        )
        order = np.argsort(keys, kind="stable")
        sp_keys = keys[order]
        sp_cols = {c: np.asarray(sdf[c][order], dtype=np.float32) for c in sp_names}
        del sdf, keys, order

    ncol = len(names) + len(sp_names)
    n = pf.metadata.num_rows

    # pass 1: years only -> masks
    yr = np.empty(n, dtype=np.int32)
    tr_sel = np.zeros(n, dtype=bool)
    va_sel = np.zeros(n, dtype=bool)
    te_sel = np.zeros(n, dtype=bool)
    off = 0
    for i in range(pf.metadata.num_row_groups):
        rg = pf.read_row_group(i, columns=["year"])
        y = rg.column("year").to_numpy()
        yr[off : off + len(y)] = y
        off += len(y)
        del rg
    tr_idx = np.flatnonzero(yr < train_max_year)
    te_idx = np.flatnonzero(yr == test_year)
    va_idx = np.flatnonzero(yr == valid_year) if valid_year is not None else np.empty(0, dtype=np.int64)

    rng = np.random.default_rng(seed)
    _subsample(tr_sel, tr_idx, max_train_rows, rng)
    _subsample(va_sel, va_idx, max_valid_rows, rng)
    te_sel[te_idx] = True
    del yr

    # pass 2: features into preallocated buffers
    tr_n, va_n, te_n = int(tr_sel.sum()), int(va_sel.sum()), int(te_sel.sum())
    tr_X = np.empty((tr_n, ncol), dtype=np.float32)
    va_X = np.empty((va_n, ncol), dtype=np.float32) if va_n else None
    te_X = np.empty((te_n, ncol), dtype=np.float32)
    tr_y = np.empty(tr_n, dtype=np.float64)
    va_y = np.empty(va_n, dtype=np.float64) if va_n else None
    te_y = np.empty(te_n, dtype=np.float64)
    ti = vi = ei = 0
    off = 0
    for i in range(pf.metadata.num_row_groups):
        rg = pf.read_row_group(i)
        gn = rg.num_rows
        start, end = off, off + gn
        off = end
        tmask = tr_sel[start:end]
        vmask = va_sel[start:end]
        emask = te_sel[start:end]
        take = tmask | vmask | emask
        if not take.any():
            del rg
            continue
        sub = rg.filter(pa.array(take))
        lab = sub.column("label").to_numpy().astype(np.float64)
        tn = int(tmask.sum())
        vn = int(vmask.sum())
        en = int(emask.sum())
        for j, nm in enumerate(names):
            col = sub.column(nm).to_numpy()
            if tn:
                tr_X[ti : ti + tn, j] = col[tmask[take]]
            if vn and va_X is not None:
                va_X[vi : vi + vn, j] = col[vmask[take]]
            if en:
                te_X[ei : ei + en, j] = col[emask[take]]
        if sp_names and sp_keys is not None and sp_cols is not None:
            fch = sub.column("channel").to_pylist()
            fdy = sub.column("day").to_pylist()
            kkt = np.array([f"{c}|{str(d)[:10]}" for c, d in zip(fch, fdy)], dtype=object)
            segs = (
                (tr_X, ti, tmask[take], tn),
                (va_X, vi, vmask[take], vn),
                (te_X, ei, emask[take], en),
            )
            for buf, pos, sel, cnt in segs:
                if buf is None or not cnt:
                    continue
                ks = kkt[sel]
                idx = np.searchsorted(sp_keys, ks)
                idx = np.minimum(idx, len(sp_keys) - 1)
                hit = sp_keys[idx] == ks
                for j, cn in enumerate(sp_names):
                    vals = sp_cols[cn][idx]  # fancy index -> copy
                    vals[~hit] = np.nan
                    buf[pos : pos + cnt, len(names) + j] = vals
        if tn:
            tr_y[ti : ti + tn] = lab[tmask[take]]
        if vn and va_y is not None:
            va_y[vi : vi + vn] = lab[vmask[take]]
        if en:
            te_y[ei : ei + en] = lab[emask[take]]
        ti += tn
        vi += vn
        ei += en
        del rg, sub

    all_names = names + sp_names
    return {
        "names": all_names,
        "Xtr": tr_X, "ytr": tr_y,
        "Xva": va_X, "yva": va_y,
        "Xte": te_X, "yte": te_y,
        "n": int(n),
        "spatial": bool(sp_names),
    }


def metrics(y_true: np.ndarray, proba: np.ndarray, threshold: float = 0.5) -> dict:
    pred = (proba >= threshold).astype(int)
    return {
        "auc": round(float(roc_auc_score(y_true, proba)), 4),
        "ap": round(float(average_precision_score(y_true, proba)), 4),
        "brier": round(float(brier_score_loss(y_true, proba)), 4),
        "precision": round(float(precision_score(y_true, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, pred, zero_division=0)), 4),
    }


def fit_lgbm(
    dataset: lgb.Dataset,
    params: dict | None = None,
    rounds: int = DEFAULT_ROUNDS,
    valid: lgb.Dataset | None = None,
    early_stopping: int | None = None,
) -> lgb.Booster:
    """lgb.train wrapper. With valid+early_stopping -> best_iteration is chosen
    on valid (used by tuning); otherwise a fixed number of rounds (final fit)."""
    p = dict(LGB_PARAMS_DEFAULT)
    if params:
        p.update(params)
    callbacks = []
    if valid is not None and early_stopping:
        callbacks.append(lgb.early_stopping(early_stopping, verbose=False))
    booster = lgb.train(
        p, dataset, num_boost_round=rounds, valid_sets=[valid] if valid is not None else None,
        valid_names=["valid"] if valid is not None else None, callbacks=callbacks,
    )
    return booster


def predict_proba(booster: lgb.Booster, X: np.ndarray) -> np.ndarray:
    """P(fail) — the one predict call the serving engine must use."""
    return np.asarray(booster.predict(X), dtype=np.float64)


def save_artifact(booster: lgb.Booster, path) -> None:
    """models/<cat>/model.lgb — text, compact, loadable via lgb.Booster(model_file=...).

    Written via a temp file + rename: the models directory is a persistent
    volume, so an interrupted retrain must not leave a truncated artifact.
    """
    atomic_write(Path(path), lambda tmp: booster.save_model(str(tmp)))


# --------------------------------------------------------------------------- #
# Threshold selection + calibration (valid split, never the sealed test year)
# --------------------------------------------------------------------------- #
THRESHOLD_GRID = tuple(round(t, 3) for t in np.arange(0.05, 0.951, 0.005))


def choose_threshold(y_true: np.ndarray, proba: np.ndarray, grid=THRESHOLD_GRID) -> float:
    """Decision threshold = argmax F1 on the VALIDATION split.

    The grid is 0.05..0.95 step 0.005 (181 points) — sub-cent precision is
    not meaningful for a probability model, and this keeps the choice
    robust to the validation subsample. Returns 0.5 when F1 is undefined
    (no positives in the split) so behaviour degrades to the historical
    default instead of crashing.
    """
    y_true = np.asarray(y_true).astype(int)
    proba = np.asarray(proba, dtype=np.float64)
    best_t, best_f1 = 0.5, -1.0
    for t in grid:
        pred = (proba >= t).astype(int)
        f1 = f1_score(y_true, pred, zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = f1, t
    if best_f1 <= 0.0:
        # F1 never positive on the grid (e.g. no positives in the split) —
        # degrade to the historical default instead of a spurious 0.05.
        return 0.5
    return float(best_t)


def fit_calibrator(y_true: np.ndarray, proba: np.ndarray) -> dict | None:
    """Isotonic calibrator on the validation split (returns None if it
    cannot be fit — e.g. only one class present).

    Returns a JSON-serialisable blob: {"kind": "isotonic", "x": [...],
    "y": [...]}. Serving side: np.interp(p, x, y, left=y[0], right=y[-1])
    (monotone by construction — isotonic regression output).
    """
    y_true = np.asarray(y_true).astype(int)
    proba = np.asarray(proba, dtype=np.float64)
    if len(np.unique(y_true)) < 2:
        return None
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(proba, y_true)
    x = iso.X_thresholds_.astype(np.float64).tolist()
    y = iso.y_.astype(np.float64).tolist()
    if not x or not y:
        return None
    return {"kind": "isotonic", "x": x, "y": y}


def apply_calibrator(blob: dict | None, proba: np.ndarray | float) -> np.ndarray | float:
    """Map raw model output through a stored isotonic blob (identity if None)."""
    if blob is None:
        return proba
    x = np.asarray(blob["x"], dtype=np.float64)
    y = np.asarray(blob["y"], dtype=np.float64)
    if isinstance(proba, (int, float)):
        return float(np.interp(proba, x, y, left=y[0], right=y[-1]))
    return np.interp(np.asarray(proba, dtype=np.float64), x, y, left=y[0], right=y[-1])
