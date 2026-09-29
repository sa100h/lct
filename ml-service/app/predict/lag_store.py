"""Serve-time observation store -> the 11 lag values for a subject AND the
subject's latest full feature row (auto-feature assembly for /predict).

Train/serve parity (the whole point): the store is built from the SAME
features-<cat>.parquet the training lags were computed on (app/ingest/
lag_features.add_lag_features). So at serve time `lags_for` feeds the same
history rows (channel, day, label) through `lag_values_for_history` — the exact
inverse of what `compute_lags` saw during training. With history = the
channel's rows strictly before decision day t, the 11 values equal the row-t
training lags (locked by tests/test_lag_features.py::test_train_serve_parity).

Auto features (`latest_features_for`): the features parquet is NOT sorted by
(channel, day) — a channel's rows are scattered across the whole file, so
"the channel's last row" = full file scan, per channel the row with max day
(the honest source of the last observed feature vector). The store streams
the file row-group by row-group, keeping per-channel (max day, row index) and
then the raw feature row of that index. The row is the channel's LAST
HISTORICAL observation — its 11 lag columns are that past day's lags, so the
engine overrides the 11 lag slots with freshly computed serve lags and uses
the row only for the base features (client > store > 0.0).

Epoch-day origin: only DIFFERENCES are ever used (t - d_last, t - d[0], window
edges), so an epoch day is safe on both sides (see lag_features.day_ordinal).

Empty/unknown subject -> the documented NaN vector (since_last_* = MISSING
sentinel 9999), not an error — LightGBM handles NaN natively and the caller
must not 422 a subject that simply has no history yet.

Memory: sensor-failure is ~2.4M (channel, day, label) rows -> per-channel
int32 day + float32 label arrays total ~20 MB; latest feature rows are
195 float32 per channel (~9 MB for 11.4k channels); lazily loaded per
category and cached. Batch refresh = rebuild the features parquet
(feature_engine) then call store.refresh(category).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import numpy as np
import pyarrow.parquet as pq

from app.config import FEATURES_DIR
from app.ingest.lag_features import LAG_FEATURES, day_ordinal, lag_values_for_history

logger = logging.getLogger(__name__)

# Resolved from LCT_DATA_DIR / LCT_FEATURES_DIR (see app/config.py). The
# container mounts the data at /app/data, so this must NOT be a hardcoded
# host path — that is what silently emptied the store (2026-09-29).
FEAT_DIR = FEATURES_DIR


def _feat_path(category: str) -> Path:
    return FEAT_DIR / f"features-{category}.parquet"


class LagStore:
    """Per-category, per-channel history -> 11 lag values at a decision day,
    plus the channel's latest full feature row for auto-feature assembly."""

    def __init__(self, feat_dir: str | Path = FEAT_DIR) -> None:
        self.feat_dir = Path(feat_dir)
        # category -> {channel: (d_ord int32 sorted, y float32)}
        self._hist: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] = {}
        # category -> {channel: {feature_name: float}} — last observed row (max day)
        self._latest: dict[str, dict[str, dict[str, float]]] = {}
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
        self._latest.pop(category, None)
        return self.load(category)

    # ---- auto-feature assembly: the channel's latest full feature row ----

    def _latest_sidecar_path(self, category: str) -> Path:
        return self.feat_dir / f"features-{category}-latest.parquet"

    def _build_latest_sidecar(self, category: str) -> None:
        """Build the one-row-per-channel sidecar (max day per channel).

        Two streaming passes over features-<cat>.parquet:
        pass 1 (channel, day only): vectorized per-channel argmax-day row index.
        pass 2: pull the winning feature rows per row group (fancy indexing).

        Persisted as a small parquet (one row per channel, ~11.5K rows for
        sensor-failure) so serve time stays fast. Rows are unique per
        (channel, day), so the max-day row is unique.
        """
        import pandas as pd

        path = self.feat_dir / f"features-{category}.parquet"
        pf = pq.ParquetFile(path)
        schema = pf.schema_arrow
        feature_cols = [
            schema.field(i).name
            for i in range(len(schema))
            if schema.field(i).name not in ("channel", "day", "year", "label")
        ]
        n_rg = pf.metadata.num_row_groups
        try:
            per_rg = [
                pf.read_row_group(i, columns=["channel", "day"]).to_pandas()
                for i in range(n_rg)
            ]
            ch = pd.concat([r["channel"] for r in per_rg], ignore_index=True)
            day = pd.concat([r["day"] for r in per_rg], ignore_index=True)
            grp = np.repeat(np.arange(n_rg, dtype=np.int64), [len(r) for r in per_rg])
            off = np.concatenate([np.arange(len(r), dtype=np.int64) for r in per_rg])

            # per channel: position of the max-day row (rows unique per channel-day)
            idx = day.groupby(ch, sort=False).idxmax().to_numpy()
            ch_w = ch.to_numpy()[idx]
            day_w = day.to_numpy()[idx]
            grp_w = grp[idx]
            off_w = off[idx]

            rows = np.empty((len(idx), len(feature_cols)), dtype=np.float32)
            for g in np.unique(grp_w):
                sel = grp_w == g
                table = pf.read_row_group(int(g), columns=feature_cols)
                chunk = np.column_stack(
                    [col.to_numpy(zero_copy_only=False) for col in table.columns]
                )
                rows[sel] = chunk[off_w[sel], :]
                del table, chunk
        finally:
            pf.close()

        out = pd.DataFrame(rows, columns=feature_cols)
        out.insert(0, "day", day_w)
        out.insert(0, "channel", ch_w)
        out.to_parquet(self._latest_sidecar_path(category))
        logger.info(
            "LagStore[%s]: latest-feature sidecar built (%d channels -> %s)",
            category, len(out), self._latest_sidecar_path(category),
        )

    def _read_latest(self, category: str) -> dict[str, dict[str, float]]:
        """Load the sidecar -> {channel: {feature_name: float}} (NaNs preserved)."""
        path = self._latest_sidecar_path(category)
        if not path.exists():
            self._build_latest_sidecar(category)
        pf = pq.ParquetFile(path)
        table = pf.read().to_pandas()
        pf.close()
        out: dict[str, dict[str, float]] = {}
        for row in table.itertuples(index=False):
            out[row[0]] = {
                name: (float(v) if v is not None else float("nan"))
                for name, v in zip(row._fields, row)
                if name != "day"
            }
        return out

    def _latest_ensure(self, category: str) -> None:
        if category not in self._latest:
            self._latest[category] = self._read_latest(category)

    def latest_features_for(self, category: str, subject_id: str) -> dict[str, float] | None:
        """The channel's last observed full feature row (all feature names, NaNs
        preserved — LightGBM handles them natively), or None when the channel
        has no history at all."""
        hist = self._hist.get(category)
        if hist is None:
            self.load(category)
            hist = self._hist.get(category, {})
        if not hist or subject_id not in hist:
            return None
        self._latest_ensure(category)
        row = self._latest[category].get(subject_id)
        return dict(row) if row is not None else None

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

    def has_subject(self, category: str, subject_id: str) -> bool:
        """True when the channel is in this category's training history.

        Proxy for category applicability: feature_engine builds each category's
        parquet from its subsystem's channels only (CATS), so membership here
        means the category's model has actually seen this channel's data.
        """
        hist = self._hist.get(category)
        if hist is None:
            self.load(category)
            hist = self._hist.get(category, {})
        return subject_id in (hist or {})

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
