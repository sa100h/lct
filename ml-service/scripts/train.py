"""Train LCT models for all (or one) category.

Engines:
    lgbm (default)  LightGBM — app/models/lgbm_model.py (production, the lag
                    experiment engine; 11 lag columns included unless --no-lags)
    hgb (fallback)  sklearn HistGradientBoostingClassifier — app/models/baseline.py

Usage:
    .venv/bin/python -m scripts.train                 # all 4 categories, lgbm + lags
    .venv/bin/python -m scripts.train --category sensor-failure
    .venv/bin/python -m scripts.train --engine hgb    # engine rollback
    .venv/bin/python -m scripts.train --no-lags sensor-failure   # per-category rollback
    .venv/bin/python -m scripts.train --tuned         # use tuned params (T3 output)

Train/valid/test (lgbm): train < 2026, early stopping on valid=2025, final fit
runs the best iteration count, report on test=2026. HGB path unchanged
(train < test_year, report on test_year).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from app.main import Category
from app.models.baseline import BaselineTrainer
from app.models.lgbm_model import (
    LGB_PARAMS_DEFAULT,
    apply_calibrator,
    choose_threshold,
    engine_tag,
    fit_calibrator,
    fit_lgbm,
    metrics,
    predict_proba,
    stream_split,
)
from app.models.registry import get_registry
from datetime import datetime, timezone

FEAT_DIR = Path("/home/junai/lct/ml-data/features")
TUNED_PATH = Path("/home/junai/lct/ml-data/lags/lgbm-tuned-results.json")

# Categories where the decision threshold is chosen as argmax F1 on the
# VALIDATION split (the sealed test year never influences the choice).
# Others keep the historical default 0.5.
THRESHOLD_CATEGORIES = {"sensor-failure", "unauthorized-access"}

logger = logging.getLogger(__name__)


def _tuned_params(category: str) -> dict | None:
    """T3 output: tuned hyper-params per category (None if not tuned yet)."""
    if not TUNED_PATH.exists():
        return None
    data = json.loads(TUNED_PATH.read_text(encoding="utf-8"))
    entry = data.get("per_category", {}).get(category)
    if not entry:
        return None
    return {"params": entry.get("params"), "rounds": entry.get("best_iteration") or entry.get("rounds")}


def _feature_file(category: str) -> Path | None:
    path = FEAT_DIR / f"features-{category}.parquet"
    return path if path.exists() else None


def train_lgbm(category: str, test_year: int = 2026, use_lags: bool = True,
               use_tuned: bool = False, valid_year: int = 2025) -> dict:
    path = _feature_file(category)
    if path is None:
        raise FileNotFoundError(f"No feature file for {category}")

    params = dict(LGB_PARAMS_DEFAULT)
    rounds = None
    if use_tuned:
        tuned = _tuned_params(category)
        if tuned:
            params.update(tuned.get("params") or {})
            rounds = tuned.get("rounds")

    ds = stream_split(path, train_max_year=test_year, valid_year=valid_year,
                      test_year=test_year, exclude_lags=not use_lags)
    n = len(ds["names"])
    logger.info("%s: %s rows total, %d features%s", category, f"{ds['n']:,}", n,
                " (no lags)" if not use_lags else f" incl. 11 lags")

    import lightgbm as lgb

    train_data = lgb.Dataset(ds["Xtr"], label=ds["ytr"])
    valid_data = lgb.Dataset(ds["Xva"], label=ds["yva"], reference=train_data) if ds["Xva"] is not None else None

    # Phase 1: early stopping on valid (tuning the round count; 2026 stays sealed).
    booster = fit_lgbm(train_data, params=params,
                       rounds=rounds or 300, valid=valid_data, early_stopping=50)
    final_rounds = rounds or booster.best_iteration or 300

    # Decision threshold: argmax F1 on the Phase-1 valid proba (2025 split —
    # the sealed test year never enters the choice). None = historical 0.5.
    threshold = None
    if category in THRESHOLD_CATEGORIES and valid_data is not None and ds["Xva"] is not None:
        valid_proba = predict_proba(booster, ds["Xva"])
        threshold = choose_threshold(ds["yva"], valid_proba)
        logger.info("%s: threshold=%.3f (valid F1-max)", category, threshold)

    # Phase 2: final fit, fixed rounds, no early stopping — same train rows.
    booster = fit_lgbm(train_data, params=params, rounds=final_rounds)

    proba = predict_proba(booster, ds["Xte"])
    m = metrics(ds["yte"], proba, threshold=threshold if threshold is not None else 0.5)
    n_train, n_valid, n_test = ds["Xtr"].shape[0], (ds["Xva"].shape[0] if ds["Xva"] is not None else 0), ds["Xte"].shape[0]
    m.update({
        "engine": engine_tag(),
        "source": f"real ({FEAT_DIR.name})",
        "split": f"train<{test_year}={n_train:,}, valid={valid_year}={n_valid:,}, test={test_year}={n_test:,}",
        "best_iteration": int(booster.best_iteration) if valid_data is not None else None,
        "final_rounds": int(final_rounds),
        "n_features": n,
        "lags": bool(use_lags),
        "tuned": bool(use_tuned),
        "test_positive_rate": round(float(ds["yte"].mean()), 4),
    })
    get_registry().save(category, booster, ds["names"], m, engine=engine_tag(),
                        threshold=threshold)
    logger.info("Trained %s (%s): %s%s", category, engine_tag(),
                {k: m[k] for k in ("auc", "ap", "precision", "recall") if k in m},
                f" threshold={threshold}" if threshold is not None else "")
    return m


def main() -> None:
    parser = argparse.ArgumentParser(description="Train LCT models.")
    parser.add_argument("--category", type=str, default=None, choices=[c.value for c in Category])
    parser.add_argument("--engine", choices=["lgbm", "hgb"], default="lgbm")
    parser.add_argument("--no-lags", nargs="+", default=[], metavar="CATEGORY",
                        help="categories to train WITHOUT the 11 lag columns (rollback)")
    parser.add_argument("--tuned", action="store_true",
                        help="lgbm only: use tuned hyper-params from lgbm-tuned-results.json")
    parser.add_argument("--test-year", type=int, default=2026)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    targets = [args.category] if args.category else [c.value for c in Category]
    registry = get_registry()
    for category in targets:
        if args.engine == "hgb" or _feature_file(category) is None:
            hgb = BaselineTrainer()
            m = hgb.fit(category, test_year=args.test_year)
            print(f"[{category}] hgb: {m.get('test_auc', m)}")
            continue
        m = train_lgbm(category, test_year=args.test_year,
                       use_lags=category not in args.no_lags, use_tuned=args.tuned)
        print(f"[{category}] lgbm: auc={m.get('auc')} ap={m.get('ap')} "
              f"precision={m.get('precision')} recall={m.get('recall')} "
              f"lags={m.get('lags')} rounds={m.get('final_rounds')} "
              f"version={registry.status(category).model_version}")
    print("Done.")


if __name__ == "__main__":
    main()
