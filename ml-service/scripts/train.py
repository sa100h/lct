"""CLI: train all (or one) category models.

Usage:
  python -m scripts.train                 # all categories
  python -m scripts.train --category fire-risk
"""

from __future__ import annotations

import argparse
import logging

from app.main import Category
from app.models.baseline import BaselineTrainer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("train")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train LCT ML models.")
    parser.add_argument("--category", type=str, default=None, choices=[c.value for c in Category])
    args = parser.parse_args()

    trainer = BaselineTrainer()
    targets = [args.category] if args.category else [c.value for c in Category]
    for category in targets:
        metrics = trainer.fit(category)
        logger.info("Trained %s: %s", category, metrics)


if __name__ == "__main__":
    main()
