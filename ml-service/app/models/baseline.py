"""Baseline model trainer.

Trains a HistGradientBoostingClassifier per category from the REAL
feature files produced by app/ingest/feature_engine.py:

    $LCT_DATA_DIR/features/features-<category>.parquet

(see app/config.py; defaults to the dev-box path)

Temporal split: the whole year 2026 is held out as the test set (it is
the most recent year — closest to a live forecast); 2019..2025 train.
Feature names are stored in the model meta, so the prediction engine
uses exactly what the model was trained on.

Memory: the box has ~3GB RAM, so feature tables are read row-group by
row-group (one row group at a time), and the training set is subsampled
to <= 2M rows BEFORE any float64 materialization. HGB converges fine on
2M samples.

Fallback: if no feature file exists for a category, a small synthetic
dataset is generated so the service always has a working model (the
rest of the stack can integrate before the data pipeline lands). That
fallback is DISABLED when ``LCT_ALLOW_SYNTHETIC=false`` (set in
docker-compose): inside a container a missing parquet means a broken
data mount, and silently substituting a synthetic model overwrites the
trained artifact — serving then emits a constant for every sensor.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score

from app.config import FEATURES_DIR
from app.models.features import features_for
from app.models.registry import get_registry

logger = logging.getLogger(__name__)

# Env-driven (app/config.py): the container mounts the data at /app/data, so a
# hardcoded host path silently sent the trainer into the synthetic fallback and
# overwrote the trained models (2026-09-29).
FEAT_DIR = FEATURES_DIR
# train buffer in float32 (HGB fits on float32 directly): the 134-feature
# tables overflowed the 3.8GB box via a fit-time float64 copy (SIGKILL 137).
# 1.0M rows keeps the fit-time peak ~1.5GB — sensor-failure's 2.46M-row table
# needs the headroom; the sample is random so 1.0M vs 1.2M rows changes nothing.
MAX_TRAIN_ROWS = 1_000_000
MAX_ROW_GROUP = 2_000_000
META_COLS = {"channel", "day", "year", "label"}


def _feature_file(category: str) -> Path | None:
    path = FEAT_DIR / f"features-{category}.parquet"
    return path if path.exists() else None


def _synthetic_baseline(category: str, n: int = 2000, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed + len(category))
    X = rng.normal(0.0, 1.0, size=(n, len(features_for(category))))
    # Skewed labels so the model has something to learn: risk driven by
    # the first two features, which mirrors how the real signal will behave.
    logit = 2.0 * X[:, 0] + 1.2 * X[:, 1] + 0.3 * X[:, 2] - 0.6
    p = 1.0 / (1.0 + np.exp(-logit))
    y = (rng.random(n) < p).astype(int)
    return X, y


def _allow_synthetic() -> bool:
    """True unless ``LCT_ALLOW_SYNTHETIC`` is explicitly false-ish.

    Read at call time (not import time) so it stays testable and a container
    can flip it without a code change."""
    raw = (os.environ.get("LCT_ALLOW_SYNTHETIC") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _train_synthetic(category: str) -> dict:
    """Fallback path: no real data yet — fit a demonstrable model."""
    if not _allow_synthetic():
        raise RuntimeError(
            f"No feature file for '{category}' at {FEAT_DIR} and "
            "LCT_ALLOW_SYNTHETIC=false: refusing to replace a trained model with a "
            "synthetic baseline. Check the data mount / LCT_DATA_DIR."
        )
    X, y = _synthetic_baseline(category)
    model = HistGradientBoostingClassifier(max_iter=200, random_state=42)
    model.fit(X, y)
    proba = model.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)
    metrics = {
        "source": "synthetic-baseline",
        "n_samples": int(len(y)),
        "positive_rate": round(float(y.mean()), 4),
        "train_precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "train_recall": round(float(recall_score(y, pred, zero_division=0)), 4),
    }
    get_registry().save(category, model, list(features_for(category)), metrics)
    logger.info("Trained %s from synthetic baseline: %s", category, metrics)
    return metrics


def _train_real(category: str, test_year: int) -> dict:
    path = _feature_file(category)
    if path is None:
        raise FileNotFoundError(f"No feature file for {category}")

    pf = pq.ParquetFile(path)
    names = [c for c in pf.schema_arrow.names if c not in META_COLS]
    if not names:
        raise ValueError("Feature file has no feature columns")
    load_cols = names + ["year", "label"]

    n_rgs = pf.metadata.num_row_groups
    max_rgf = max((pf.metadata.row_group(i).num_rows for i in range(n_rgs)), default=0)
    if max_rgf > MAX_ROW_GROUP:
        raise MemoryError(f"Row group too big to stream ({max_rgf:,} rows)")

    # Pass 1: stream the year column RG by RG (a full pf.read materializes the
    # 1.32GB feature table just for one int32 column — unnecessary on a 3.8GB
    # box and the proximate cause of the 134-col OOM kills).
    year_parts: list[np.ndarray] = []
    for i in range(n_rgs):
        year_parts.append(
            pf.read_row_group(i, columns=["year"]).column(0).to_numpy()
        )
    years = np.concatenate(year_parts)
    del year_parts
    n = len(years)
    is_tr_global = years < test_year
    is_te_global = years == test_year
    tr_count = int(is_tr_global.sum())
    te_count = int(is_te_global.sum())
    if te_count == 0:
        raise ValueError(f"No {test_year} rows to hold out")
    subsample = MAX_TRAIN_ROWS / tr_count if tr_count > MAX_TRAIN_ROWS else 1.0
    rng = np.random.default_rng(42)
    keep = np.zeros(n, dtype=bool)
    keep[is_tr_global] = rng.random(tr_count) < subsample

    n_keep = int(keep.sum())
    n_feat = len(names)

    # fresh handle: the pass-1 file object still pins 1.3GB of buffers
    pf.close()
    pf = pq.ParquetFile(path)
    n_rgs = pf.metadata.num_row_groups

    # Pass 2: stream row groups; fill ONE preallocated float32 buffer.
    # (vstack of per-RG float64 frames kept two full-size copies in RAM and
    # OOM-killed the 134-col rebuild; prealloc + float32 halves both.)
    Xtr_buf = np.empty((n_keep, n_feat), dtype=np.float32)
    ytr_buf = np.empty(n_keep, dtype=np.int64)
    te_parts: list[np.ndarray] = []
    te_y_parts: list[np.ndarray] = []
    cur = 0
    pos = 0
    for i in range(n_rgs):
        rg = pf.read_row_group(i, columns=load_cols)
        size = rg.num_rows
        sl = slice(pos, pos + size)
        pos += size

        kmask = keep[sl]
        if kmask.any():
            ksub = rg.filter(pa.array(kmask))
            k = ksub.num_rows
            part = np.empty((k, n_feat), dtype=np.float32)
            for j, n in enumerate(names):
                part[:, j] = ksub.column(n).to_numpy()
            Xtr_buf[cur:cur + k] = part
            ytr_buf[cur:cur + k] = ksub.column("label").to_numpy()
            cur += k
            del part, ksub
        tmask = is_te_global[sl]
        if tmask.any():
            sub = rg.filter(pa.array(tmask))
            te_parts.append(
                np.empty((sub.num_rows, n_feat), dtype=np.float32)
            )
            tp = te_parts[-1]
            for j, n in enumerate(names):
                tp[:, j] = sub.column(n).to_numpy()
            te_y_parts.append(sub.column("label").to_numpy().astype(np.int64))
            del sub
        del rg
    del years, keep
    Xtr_buf = Xtr_buf[:cur]
    ytr = ytr_buf[:cur]
    del ytr_buf
    Xte = np.vstack(te_parts) if te_parts else np.empty((0, n_feat), dtype=np.float32)
    yte = np.concatenate(te_y_parts) if te_y_parts else np.empty(0, dtype=np.int64)
    del te_parts, te_y_parts

    model = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.08,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        class_weight="balanced",
        random_state=42,
    )
    # fit directly on float32 (HGB accepts it): the previous
    # .astype(float64) fit-time copy alone was a 1.3-1.6GB spike on the
    # 3.8GB box and OOM-killed infrastructure-wear mid-fit.
    model.fit(Xtr_buf, ytr)

    proba = model.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)

    metrics = {
        "source": f"real ({FEAT_DIR.name})",
        "split": f"train<2026={tr_count:,} (fit on {len(ytr):,}), test={test_year}={te_count:,}",
        "train_positive_rate": round(float(ytr.mean()), 4),
        "test_positive_rate": round(float(yte.mean()), 4),
        "test_auc": round(float(roc_auc_score(yte, proba)), 4),
        "test_average_precision": round(float(average_precision_score(yte, proba)), 4),
        "test_precision": round(float(precision_score(yte, pred, zero_division=0)), 4),
        "test_recall": round(float(recall_score(yte, pred, zero_division=0)), 4),
    }
    get_registry().save(category, model, names, metrics)
    logger.info("Trained %s from real data: %s", category, metrics)
    return metrics


class BaselineTrainer:
    """Trains + persists one model per category via the registry."""

    def fit(self, category: str, test_year: int = 2026) -> dict:
        if _feature_file(category) is None:
            return _train_synthetic(category)
        return _train_real(category, test_year)
