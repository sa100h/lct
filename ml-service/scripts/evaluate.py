"""Evaluation harness for the hackathon acceptance metrics.

Target: Precision > 0.7 and Recall > 0.5 on the organizer's test set per
category. Once the real test export arrives, drop it into
data/<category>/test.csv (columns: feature names + label) and run:

  python -m scripts.evaluate --category sensor-failure
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score

from app.main import Category
from app.models.features import features_for
from app.models.registry import get_registry

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("evaluate")


def evaluate_category(category: str) -> dict:
    registry = get_registry()
    test_path = DATA_DIR / category / "test.csv"
    if not test_path.exists():
        raise FileNotFoundError(f"Test set not found: {test_path}")

    df = pd.read_csv(test_path)
    model = registry.load(category)
    X = df[features_for(category)].to_numpy(dtype=float)
    y = df["label"].to_numpy(dtype=int)

    proba = model.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)

    result = {
        "category": category,
        "n_samples": int(len(y)),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y, proba)), 4) if len(set(y)) > 1 else None,
    }
    ok = result["precision"] > 0.7 and result["recall"] > 0.5
    result["meets_target"] = ok
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate LCT models against organizer test sets.")
    parser.add_argument("--category", type=str, default=None, choices=[c.value for c in Category])
    args = parser.parse_args()

    targets = [args.category] if args.category else [c.value for c in Category]
    for category in targets:
        try:
            result = evaluate_category(category)
        except FileNotFoundError as exc:
            logger.warning("%s", exc)
            continue
        logger.info("%s", result)


if __name__ == "__main__":
    main()
