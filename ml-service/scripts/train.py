"""Train the baseline models for all (or one) LCT categories.

Usage:
    .venv/bin/python -m scripts.train                 # all 4 categories
    .venv/bin/python -m scripts.train --category fire-risk
"""

from __future__ import annotations

import argparse
import logging

from app.main import Category
from app.models.baseline import BaselineTrainer


def main() -> None:
    parser = argparse.ArgumentParser(description="Train LCT baseline models.")
    parser.add_argument("--category", type=str, default=None, choices=[c.value for c in Category])
    parser.add_argument("--test-year", type=int, default=2026)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    trainer = BaselineTrainer()
    targets = [args.category] if args.category else [c.value for c in Category]
    for category in targets:
        trainer.fit(category, test_year=args.test_year)
    print("Done.")


if __name__ == "__main__":
    main()
