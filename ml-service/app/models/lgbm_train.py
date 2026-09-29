"""LightGBM training, callable from the service and from the CLI.

Why this module exists
----------------------
The training recipe lived in ``scripts/train.py``, which hardcoded the HOST
data paths (``/home/junai/lct/ml-data/features``). Inside the container that
path does not exist, so ``POST /retrain`` could never use it and silently
trained the sklearn HGB baseline instead — overwriting the production LightGBM
models (``model.lgb``) with a baseline (``model.joblib``).

Paths now come from :mod:`app.config`, so the same recipe runs on the host and
inside the container. ``scripts/train.py`` stays a thin CLI over this module.

Split (lightgbm): train ``year < test_year``, early stopping on
``valid_year``, final fit at the best iteration, report on ``test_year``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import DATA_DIR, FEATURES_DIR
from app.models.lgbm_model import (
    DEFAULT_ROUNDS,
    LGB_PARAMS_DEFAULT,
    choose_threshold,
    engine_tag,
    fit_lgbm,
    metrics,
    predict_proba,
    stream_split,
)
from app.models.registry import get_registry

logger = logging.getLogger(__name__)

# Tuning output (T3). Not tracked in git: absence means "untuned", not an error.
TUNED_PATH = DATA_DIR / "lags" / "lgbm-tuned-results.json"

# Categories whose decision threshold is argmax F1 on the VALIDATION split (the
# sealed test year never influences the choice). Others keep the default 0.5.
THRESHOLD_CATEGORIES = {"sensor-failure", "unauthorized-access"}

EARLY_STOPPING = 50


def tuned_params(category: str) -> dict | None:
    """Tuned hyper-params for a category, or ``None`` when there is no file."""
    if not TUNED_PATH.exists():
        return None
    data = json.loads(TUNED_PATH.read_text(encoding="utf-8"))
    entry = data.get("per_category", {}).get(category)
    if not entry:
        return None
    return {
        "params": entry.get("params"),
        "rounds": entry.get("best_iteration") or entry.get("rounds"),
    }


def feature_file(category: str) -> Path | None:
    """The feature parquet for a category, or ``None`` when it is missing."""
    path = FEATURES_DIR / f"features-{category}.parquet"
    return path if path.exists() else None


def train_lgbm(
    category: str,
    *,
    test_year: int = 2026,
    use_lags: bool = True,
    use_tuned: bool = False,
    valid_year: int = 2025,
) -> dict:
    """Train one category with LightGBM and save it to the registry.

    Returns the metrics dict that was stored next to the artifact.
    Raises ``FileNotFoundError`` when the category has no feature parquet —
    the caller reports it per category instead of falling back to a synthetic
    model, which is what used to destroy the real artifacts.
    """
    path = feature_file(category)
    if path is None:
        raise FileNotFoundError(f"No feature file for '{category}' in {FEATURES_DIR}")

    params = dict(LGB_PARAMS_DEFAULT)
    rounds = None
    if use_tuned:
        tuned = tuned_params(category)
        if tuned:
            params.update(tuned.get("params") or {})
            rounds = tuned.get("rounds")

    ds = stream_split(
        path,
        train_max_year=test_year,
        valid_year=valid_year,
        test_year=test_year,
        exclude_lags=not use_lags,
    )
    n = len(ds["names"])
    logger.info(
        "%s: %s rows total, %d features%s",
        category,
        f"{ds['n']:,}",
        n,
        " (no lags)" if not use_lags else " incl. 11 lags",
    )

    import lightgbm as lgb

    train_data = lgb.Dataset(ds["Xtr"], label=ds["ytr"])
    valid_data = (
        lgb.Dataset(ds["Xva"], label=ds["yva"], reference=train_data)
        if ds["Xva"] is not None
        else None
    )

    # Phase 1: early stopping on valid (tuning the round count; test stays sealed).
    booster = fit_lgbm(
        train_data,
        params=params,
        rounds=rounds or DEFAULT_ROUNDS,
        valid=valid_data,
        early_stopping=EARLY_STOPPING,
    )
    final_rounds = rounds or booster.best_iteration or DEFAULT_ROUNDS

    # Decision threshold: argmax F1 on the Phase-1 valid proba. None = 0.5.
    threshold = None
    if category in THRESHOLD_CATEGORIES and valid_data is not None and ds["Xva"] is not None:
        valid_proba = predict_proba(booster, ds["Xva"])
        threshold = choose_threshold(ds["yva"], valid_proba)
        logger.info("%s: threshold=%.3f (valid F1-max)", category, threshold)

    # Phase 2: final fit, fixed rounds, no early stopping — same train rows.
    booster = fit_lgbm(train_data, params=params, rounds=final_rounds)

    proba = predict_proba(booster, ds["Xte"])
    m = metrics(ds["yte"], proba, threshold=threshold if threshold is not None else 0.5)
    n_train = ds["Xtr"].shape[0]
    n_valid = ds["Xva"].shape[0] if ds["Xva"] is not None else 0
    n_test = ds["Xte"].shape[0]
    m.update(
        {
            "engine": engine_tag(),
            "source": f"real ({FEATURES_DIR.name})",
            "split": (
                f"train<{test_year}={n_train:,}, "
                f"valid={valid_year}={n_valid:,}, test={test_year}={n_test:,}"
            ),
            "best_iteration": int(booster.best_iteration) if valid_data is not None else None,
            "final_rounds": int(final_rounds),
            "n_features": n,
            "lags": bool(use_lags),
            "tuned": bool(use_tuned),
            "test_positive_rate": round(float(ds["yte"].mean()), 4),
        }
    )
    get_registry().save(
        category,
        booster,
        ds["names"],
        m,
        engine=engine_tag(),
        threshold=threshold,
    )
    logger.info(
        "Trained %s (%s): %s%s",
        category,
        engine_tag(),
        {k: m[k] for k in ("auc", "ap", "precision", "recall") if k in m},
        f" threshold={threshold}" if threshold is not None else "",
    )
    return m
