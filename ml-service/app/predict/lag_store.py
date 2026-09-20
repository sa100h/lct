"""Serve-time observation store -> the 11 lag values for a subject.

Train/serve parity (the whole point): the store is built from the SAME
features-<cat>.parquet the training lags were computed on (app/ingest/
lag_features.add_lag_features). So at serve time `lags_for` feeds the same
history rows (channel, day, label) through `lag_values_for_history` — the exact
inverse of what `compute_lags` saw during training. With history = the
channel's rows strictly before decision day t, the 11 values equal the row-t
training lags (locked by tests/test_lag_features.py::test_train_serve_parity).

Epoch-day origin: only DIFFERENCES are ever used (t - d_last, t - d[0], window
edges), so an epoch day is safe on both sides (see lag_features.day_ordinal).

Empty/unknown subject -> the documented NaN vector (since_last_* = MISSING
sentinel 9999), not an error — LightGBM handles NaN natively and the caller
must not 422 a subject that simply has no history yet.

Memory: sensor-failure is ~2.4M (channel, day, label) rows -> per-channel
int32 day + float32 label arrays total ~20 MB; lazily loaded per category and
cached. Batch refresh = rebuild the features parquet (feature_engine) then
call store.refresh(category).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import numpy as np
import pyarrow.parquet as pq

from app.ingest.lag_features import LAG_FEATURES, day_ordinal, lag_values_for_history

logger = logging.getLogger(__name__)

FEAT_DIR = Path("/home/junai/lct/ml-data/features")


def _feat_path(category: str) -> Path:
    return FEAT_DIR / f"features-{category}.parquet"


class LagStore:
    """Per-category, per-channel history -> 11 lag values at a decision day."""

    def __init__(self, feat_dir: str | Path = FEAT_DIR) -> None:
        self.feat_dir = Path(feat_dir)
        # category -> {channel: (d_ord int32 sorted, y float32)}
        self._hist: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] = {}
        self._meta: dict[str, dict] = {}

    def _read_history(self, category: str) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], dict]:
        """Stream (channel, day, label) -> per-channel arrays sorted by day."""
        path = self.feat_dir / f"features-{category}.parquet"
        pf = pq.ParquetFile(path)
        ch_p: list[np.ndarray] = []
        day_p: list[np.ndarray] = []
        lab_p: list[np.ndarray] = []
        try:
            for i in range(pf.metadata.num_row_groups):
                rg = pf.read_row_group(i, columns=["channel", "day", "label"])
                ch_p.append(rg.column("channel").to_numpy())
                day_p.append(rg.column("day").to_numpy())
                lab_p.append(rg.column("label").to_numpy())
        finally:
            pf.close()
        ch = np.concatenate(ch_p)
        day = np.concatenate(day_p)
        lab = np.concatenate(lab_p).astype(np.float32)

        # epoch days: day is a tz-naive ms timestamp array
        ts = day.astype("datetime64[ms]").astype("datetime64[s]")
        d_ord = (ts.astype("int64") // 86_400).astype(np.int32)

        hist: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        # group by channel (channel ids are strings)
        for cid, d, y in zip(ch, d_ord, lab):
            cur = hist.get(cid)
            if cur is None:
                hist[cid] = (np.array([d], dtype=np.int32), np.array([y], dtype=np.float32))
            else:
                hist[cid] = (np.append(cur[0], d), np.append(cur[1], y))

        # sort each channel by day, keep the arrays tight
        for cid in hist:
            d, y = hist[cid]
            order = np.argsort(d, kind="stable")
            hist[cid] = (d[order].astype(np.int32, copy=False), y[order].astype(np.float32, copy=False))

        meta = {"channel": ch, "day": day.astype("datetime64[ms]"), "label": lab.astype(np.float32)}
        return hist, meta

    def load(self, category: str) -> dict:
        """Load (and cache) one category's history from the features parquet."""
        if category in self._hist:
            return self._meta[category]
        path = self.feat_dir / f"features-{category}.parquet"
        if not path.exists():
            logger.warning("LagStore: no features parquet for %s (%s); lags -> NaN", category, path)
            self._hist[category] = {}
            self._meta[category] = {"status": "empty"}
            return self._meta[category]
        hist, meta = self._read_history(category)
        self._hist[category] = hist
        self._meta[category] = {
            "status": "ok",
            "n_channels": len(hist),
            "n_rows": int(len(meta["day"])),
            "min_day": str(np.min(meta["day"])) if len(meta["day"]) else None,
            "max_day": str(np.max(meta["day"])) if len(meta["day"]) else None,
        }
        logger.info("LagStore[%s]: %d channels, %d rows, day range %s..%s",
                    category, len(hist), self._meta[category]["n_rows"],
                    self._meta[category]["min_day"], self._meta[category]["max_day"])
        return self._meta[category]

    def load_all(self, categories) -> None:
        for c in categories:
            self.load(c)

    def refresh(self, category: str) -> dict:
        """Rebuild after a feature_engine pass (drops cache)."""
        self._hist.pop(category, None)
        self._meta.pop(category, None)
        return self.load(category)

    def lags_for(self, category: str, subject_id: str, as_of) -> dict[str, float]:
        """The 11 lag values for a subject at decision day `as_of` (timestamp/str).

        Unknown category/subject -> NaN vector (since_last_* = MISSING 9999).
        Never raises on missing history.
        """
        hist = self._hist.get(category)
        if hist is None:
            hist = self._hist.get(category, {})
            if not hist and category not in self._meta:
                self.load(category)
                hist = self._hist.get(category, {})
        pair = hist.get(subject_id) if hist else None
        if pair is None:
            return _empty_lags()
        t = int(day_ordinal(as_of))
        return lag_values_for_history(pair[0], pair[1], t)

    def subjects(self, category: str) -> list[str]:
        if category not in self._hist:
            self.load(category)
        return list(self._hist.get(category, {}).keys())


def _empty_lags() -> dict[str, float]:
    """NaN vector for a subject with no history (since_last_* = MISSING sentinel)."""
    nan = float("nan")
    out = {k: nan for k in LAG_FEATURES}
    from app.ingest.lag_features import MISSING

    out["since_last_fail"] = float(MISSING)
    out["since_last_ok"] = float(MISSING)
    return out


_store: LagStore | None = None


def get_store() -> LagStore:
    global _store
    if _store is None:
        _store = LagStore()
    return _store
