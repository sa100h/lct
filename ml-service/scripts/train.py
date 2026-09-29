"""Train LCT models for all (or one) category.

Engines:
    lgbm (default)  LightGBM — app/models/lgbm_train.py (production; 11 lag
                    columns included unless --no-lags)
    hgb (fallback)  sklearn HistGradientBoostingClassifier — app/models/baseline.py

Usage:
    .venv/bin/python -m scripts.train                 # all 4 categories, lgbm + lags
    .venv/bin/python -m scripts.train --category sensor-failure
    .venv/bin/python -m scripts.train --engine hgb    # engine rollback
    .venv/bin/python -m scripts.train --no-lags sensor-failure   # per-category rollback
    .venv/bin/python -m scripts.train --tuned         # use tuned params (T3 output)

The recipe lives in ``app.models.lgbm_train`` so this CLI and ``POST /retrain``
share one implementation (the CLI used to hold its own copy with hardcoded host
paths, which the container could not use).
"""

from __future__ import annotations

import argparse
import logging

from app.models.baseline import BaselineTrainer
from app.models.lgbm_train import feature_file, train_lgbm
from app.models.registry import get_registry
from app.schemas import Category


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
        if args.engine == "hgb" or feature_file(category) is None:
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
