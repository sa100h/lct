"""Build/refresh the serve-time ``features-<cat>-latest.parquet`` sidecars.

Why this exists
---------------
``POST /predict`` needs, per channel, that channel's LAST observed feature row
(the "base features"). ``LagStore.latest_features_for`` reads it from a small
sidecar — one row per channel, the max-``day`` row — instead of scanning the
multi-MB feature parquet on every call.

That sidecar is a build artifact with two failure modes, so this script makes
its (re)build an explicit step instead of an implicit one:

* **Missing** — ``LagStore`` tries to BUILD it in place. In the container the
  data mount is read-only (``./ml-data:/app/data:ro``), so the write fails and
  serving breaks.
* **Stale** — serving silently feeds the model an old snapshot. A shipped pair
  of sidecars predated the feature rebuild by three days and was missing
  ``f7``/``f30`` entirely, so those slots fell back to ``0.0`` while the model
  had trained on real values. Predictions were wrong for the affected channels
  and nothing failed.

Run it after EVERY ``app.ingest.feature_engine`` rebuild::

    .venv/bin/python -m scripts.build_latest_sidecars            # all categories
    .venv/bin/python -m scripts.build_latest_sidecars --category sensor-failure
    .venv/bin/python -m scripts.build_latest_sidecars --check    # verify only

Exit status is non-zero if a sidecar is missing, does not cover its model's
feature set, or is older than the feature parquet. Finish with a ml-service
restart so a running container reloads the files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyarrow.parquet as pq

from app.config import FEATURES_DIR
from app.models.registry import CATEGORIES, get_registry
from app.predict.lag_store import LagStore


def _features_path(category: str) -> Path:
    return FEATURES_DIR / f"features-{category}.parquet"


def _sidecar_path(category: str) -> Path:
    return FEATURES_DIR / f"features-{category}-latest.parquet"


def _max_day(path: Path) -> str:
    return str(max(pq.read_table(path, columns=["day"]).column("day").to_pylist()))


def build(category: str, *, check_only: bool = False) -> list[str]:
    """(Re)build one sidecar. Returns problem strings; empty means OK."""
    feat = _features_path(category)
    if not feat.exists():
        return [f"missing features parquet: {feat}"]
    sidecar = _sidecar_path(category)

    if not check_only:
        LagStore().rebuild_latest_sidecar(category)
    if not sidecar.exists():
        return [f"sidecar was not created: {sidecar} (run without --check)"]

    want = get_registry().feature_names(category)
    got = set(pq.read_table(sidecar).schema.names) - {"channel", "day"}
    rows = pq.read_table(sidecar, columns=["channel"]).num_rows

    problems: list[str] = []
    missing = [n for n in want if n not in got]
    if missing:
        problems.append(
            f"does not cover the model: {len(missing)} feature(s) absent "
            f"(e.g. {', '.join(missing[:8])})")
    feat_day, side_day = _max_day(feat), _max_day(sidecar)
    stale = feat_day != side_day
    if stale:
        problems.append(f"stale: latest day {side_day} != features parquet {feat_day}")

    print(f"{category:22} rows={rows:6} sidecar_cols={len(got):4} "
          f"model_feat={len(want):4} latest_day={side_day} "
          f"{'STALE' if stale else 'fresh'}")
    return [f"{category}: {p}" for p in problems]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build/refresh the serve-time features-<cat>-latest.parquet sidecars")
    ap.add_argument("--category", action="append", choices=list(CATEGORIES),
                    help="limit to this category (repeatable); default: all")
    ap.add_argument("--check", action="store_true",
                    help="validate the existing sidecars without rebuilding")
    args = ap.parse_args(argv)

    categories = args.category or list(CATEGORIES)
    print(f"features dir: {FEATURES_DIR}")
    problems: list[str] = []
    for cat in categories:
        problems += build(cat, check_only=args.check)

    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    verb = "are consistent with their models" + (" (checked, not rebuilt)" if args.check else " (rebuilt)")
    print(f"\nOK: all sidecars {verb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
