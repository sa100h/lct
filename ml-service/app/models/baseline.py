"""Baseline model trainer.

Hackathon-first: trains a HistGradientBoostingClassifier per category.
If ingested real data (data/<category>/*.parquet|csv) exists, it is used;
otherwise a synthetic baseline dataset is generated so the service has a
working model out of the box and the rest of the stack (app-service,
frontend) can integrate immediately.

Replace the synthetic branch with real feature pipelines as the SMVU xlsx
exports, ODS journals and equipment registers are ingested (see ingest/).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import precision_score, recall_score

from app.models.features import features_for
from app.models.registry import get_registry

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_ingested(category: str) -> pd.DataFrame | None:
    cat_dir = DATA_DIR / category
    if not cat_dir.exists():
        return None
    frames = []
    for path in sorted(cat_dir.iterdir()):
        if path.suffix in (".parquet", ".csv"):
            frames.append(
                pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
            )
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    if "label" not in df.columns:
        logger.warning("Ingested data for %s has no 'label' column — ignoring", category)
        return None
    return df


def _synthetic_baseline(category: str, n: int = 2000, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed + len(category))
    feature_names = features_for(category)
    X = rng.normal(0.0, 1.0, size=(n, len(feature_names)))
    # Skewed labels so the model has something to learn: risk driven by
    # the first two features, which mirrors how the real signal will behave.
    logit = 2.0 * X[:, 0] + 1.2 * X[:, 1] + 0.3 * X[:, 2] - 0.6
    p = 1.0 / (1.0 + np.exp(-logit))
    y = (rng.random(n) < p).astype(int)
    return X, y


class BaselineTrainer:
    """Trains + persists one model per category via the registry."""

    def fit(self, category: str) -> dict:
        feature_names = features_for(category)
        df = _load_ingested(category)
        if df is not None:
            X = df[feature_names].to_numpy(dtype=float)
            y = df["label"].to_numpy(dtype=int)
            source = "ingested"
        else:
            X, y = _synthetic_baseline(category)
            source = "synthetic-baseline"

        model = HistGradientBoostingClassifier(max_iter=200, random_state=42)
        model.fit(X, y)

        proba = model.predict_proba(X)[:, 1]
        pred = (proba >= 0.5).astype(int)
        metrics = {
            "source": source,
            "n_samples": int(len(y)),
            "positive_rate": round(float(y.mean()), 4),
            "train_precision": round(float(precision_score(y, pred, zero_division=0)), 4),
            "train_recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        }
        get_registry().save(category, model, feature_names, metrics)
        logger.info("Trained %s from %s: %s", category, source, metrics)
        return metrics
