"""Stage 2: per-category feature matrix from per-(channel,day) aggregates.

One row per (channel, day) inside each channel's observed span per year:
  - features: trailing 7d/30d aggregates over days strictly BEFORE day t
    (events, alarms, numeric stats, state counts, activity density, days since
    last activity/alarm, state diversity) — no same-day information.
  - label: 1 if on day t the channel emits an alarm (тревожение=true) or any
    category-critical state (per vocab.json "critical").

Horizon: decision made at end of day t-1, outcome measured on day t (24h).
Negatives are downsampled per channel-span (~1:NEG_RATIO, seeded) to keep
RAM bounded on a 3GB box; the trainer re-balances globally.
Rows are written to temporary parquet chunks (FLUSH_ROWS each) and merged
into ml-data/features/features-<category>.parquet at the end, so the full
frame is never materialized in RAM.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pyarrow import concat_tables

from app.ingest.aggregate import STATES

BASE = Path("/home/junai/lct/ml-data")
AGG = BASE / "agg"
FEAT = BASE / "features"
FEAT.mkdir(parents=True, exist_ok=True)

CATS = {
    "sensor-failure": None,  # all channels
    "fire-risk": ["Пожарная охрана", "Температурная подсистема", "Газовая охрана"],
    "unauthorized-access": ["Охранная подсистема"],
    "infrastructure-wear": ["Диспетчерский контроль", "Диагностическая подсистема"],
}

NEG_RATIO = 3
W7, W30 = 7, 30
N_STATES = len(STATES)
FLUSH_ROWS = 800_000  # write parquet chunks, never one giant in-RAM frame


def cat_channels(subs, sen: pd.DataFrame) -> set:
    if subs is None:
        return set(sen["ид_канала_данных"].astype(str))
    return set(sen[sen["тип_инж_системы"].isin(subs)]["ид_канала_данных"].astype(str))


def trail_sum(x: np.ndarray, w: int) -> np.ndarray:
    """Sum over window [t-w, t-1] (strictly BEFORE t); from start when t<w."""
    c = np.concatenate([[0.0], np.cumsum(x)])
    hi = np.arange(0, len(x))
    lo = np.maximum(hi - w, 0)
    return (c[hi] - c[lo]).astype(np.float32)


def since_last(x: np.ndarray) -> np.ndarray:
    """Days since last positive day, as of end of day t-1 (same day EXCLUDED).

    The label is defined on day t (alarm/critical state on day t). A feature
    that reports 0 when day t itself is positive would directly encode the
    label (since_alar==0  <=>  alarm today  =>  label=1), inflating AUC to
    ~1.0. So we shift the same-day result right by one: feature[t] = days
    last positive day <= t-1. 0 = alarmed yesterday, 999 = never. This matches
    the 'decision at end of day t-1' horizon.
    """
    out = np.full(len(x), 999, np.int32)
    idx = np.flatnonzero(x)
    if len(idx):
        run = np.maximum.accumulate(np.where(x > 0, np.arange(len(x)) + 1, 0))
        has = run > 0
        out[has] = (np.arange(len(x))[has] - (run[has] - 1)).astype(np.int32)
    shifted = np.full_like(out, 999)
    shifted[1:] = out[:-1]  # feature at t uses history strictly before t
    return shifted


class ChunkWriter:
    """Accumulates emitted rows and flushes them to a parquet part file."""

    def __init__(self, tmp: Path, feat_cols: list[str], rng) -> None:
        self.tmp = tmp
        self.feat_cols = feat_cols
        self.rng = rng
        self.nfeat = len(feat_cols)
        self.chunk_id = 0
        self.total_rows = 0
        self.F: list[np.ndarray] = []
        self.D: list[np.ndarray] = []
        self.C: list[str] = []
        self.L: list[np.ndarray] = []

    def add(self, feats: np.ndarray, d0: np.int64, sel: np.ndarray,
            label: np.ndarray, channel_id) -> None:
        self.F.append(feats[sel])
        self.D.append(d0 + sel)
        self.C.append(channel_id)
        self.L.append(label[sel])

    @property
    def pending(self) -> int:
        return sum(len(x) for x in self.F)

    def flush(self) -> None:
        if not self.F:
            return
        f_cat = np.concatenate(self.F, axis=0)
        d_cat = np.concatenate(self.D)
        c_cat = np.repeat(self.C, [len(x) for x in self.F]).astype(object)
        l_cat = np.concatenate(self.L)
        days = pd.to_datetime(d_cat, unit="D", origin="1970-01-01")
        frame = pd.DataFrame(
            {
                "channel": c_cat,
                "day": days.to_numpy(),
                "year": days.year.to_numpy(),
                "label": l_cat.astype(np.int8),
            }
        )
        frame = pd.concat([frame, pd.DataFrame(f_cat, columns=self.feat_cols)], axis=1)
        frame.to_parquet(self.tmp / f"part-{self.chunk_id:03d}.parquet", index=False)
        self.total_rows += len(frame)
        self.chunk_id += 1
        self.F.clear()
        self.D.clear()
        self.C.clear()
        self.L.clear()


def build_category(cat: str, sen: pd.DataFrame, years: list[int],
                   crit_names: list[str]) -> None:
    chset = cat_channels(CATS[cat], sen)
    crit_idx = [i for i, s in enumerate(STATES) if s in crit_names]
    # fire-risk: label = new incident. A *critical state* only counts when it
    # BEGAN on day t (was not critical on t-1); an alarm always counts (alarms
    # are discrete events). Without this, 99.7% of fire-risk positives are
    # long-state continuations and the task degenerates to "was it critical
    # yesterday".
    new_incident = (cat == "fire-risk")

    rng = np.random.default_rng(12345)
    base_cols = ["n_events", "n_alarm", "n_num", "num_sum", "num_sumsq", "num_min", "num_max"]
    s_cols = [f"s_{i}" for i in range(N_STATES)]
    t0 = time.time()

    frames = []
    for year in years:
        f = AGG / f"agg-{year}.parquet"
        if not f.exists():
            print(f"  [warn] missing {f}", flush=True)
            continue
        df = pd.read_parquet(f, columns=["channel", "day", *base_cols, *s_cols])
        df = df[df["channel"].isin(chset)]
        for c in ("num_min", "num_max"):
            df[c] = df[c].fillna(0.0)
        df["year"] = year
        frames.append(df)
    df = pd.concat(frames, ignore_index=True).sort_values(["channel", "day"])
    del frames

    mat = df[base_cols + s_cols].to_numpy(np.float32)
    day_ts = pd.to_datetime(df["day"].to_numpy()).to_numpy()
    d_ord = (day_ts.astype("datetime64[D]").astype(np.int64)).astype(np.int64)
    chan = df["channel"].to_numpy()
    del df, day_ts
    n = len(d_ord)
    print(f"  {cat}: {n:,} channel-days, {len(np.unique(chan))} channels", flush=True)

    change = np.flatnonzero(chan[:-1] != chan[1:]) + 1
    bounds = np.concatenate([[0], change, [n]])

    feat_cols = (
        ["e7", "a7", "e30", "a30", "n7", "m7", "s7", "n30", "m30", "s30",
         "act7", "act30", "ar7", "ar30", "since_act", "since_alar", "div30"]
        + (["rep_gap"] if new_incident else [])
        + [f"t7_{i}" for i in range(N_STATES)]
        + [f"t30_{i}" for i in range(N_STATES)]
    )
    n_head = 18 if new_incident else 17

    tmp = FEAT / f".tmp-{cat}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    writer = ChunkWriter(tmp, feat_cols, rng)

    for k, (s, e) in enumerate(zip(bounds[:-1], bounds[1:])):
        if (k + 1) % 1000 == 0:
            print(f"  {cat}: channels {k+1}/{len(bounds)-1} elapsed={time.time()-t0:.0f}s "
                  f"rows={writer.total_rows:,}", flush=True)
        dd = d_ord[s:e]
        seg = mat[s:e]
        span = dd[-1] - dd[0] + 1
        if span > 4000:
            continue
        full = np.zeros((span, seg.shape[1]), np.float32)
        idx = np.searchsorted(np.arange(dd[0], dd[0] + span), dd)
        full[idx, :] = seg
        ev, al = full[:, 0], full[:, 1]
        nn, nsum, nsq = full[:, 2], full[:, 3], full[:, 4]

        e7, a7 = trail_sum(ev, W7), trail_sum(al, W7)
        e30, a30 = trail_sum(ev, W30), trail_sum(al, W30)
        cn7 = trail_sum(nn, W7); cs7 = trail_sum(nsum, W7); c27 = trail_sum(nsq, W7)
        cn30 = trail_sum(nn, W30); cs30 = trail_sum(nsum, W30); c230 = trail_sum(nsq, W30)
        m7 = np.where(cn7 > 0, cs7 / np.maximum(cn7, 1), 0.0)
        s7 = np.sqrt(np.clip(c27 / np.maximum(cn7, 1) - m7**2, 0, None))
        m30 = np.where(cn30 > 0, cs30 / np.maximum(cn30, 1), 0.0)
        s30 = np.sqrt(np.clip(c230 / np.maximum(cn30, 1) - m30**2, 0, None))

        active = ev > 0
        act7 = trail_sum(active.astype(np.float32), W7) / W7
        act30 = trail_sum(active.astype(np.float32), W30) / W30
        ar7 = a7 / np.maximum(e7, 1)
        ar30 = a30 / np.maximum(e30, 1)
        since_act = since_last(active.astype(np.int8)).astype(np.float32)
        since_alar = since_last(al).astype(np.float32)
        # calendar days since the channel was last REPORTED at all. Unlike
        # since_act/since_alar (event history) this encodes reporting cadence:
        # for fire channels 2026 reporting got much more sporadic (42% of rows
        # follow a consecutive day vs 58% in 2024), and a "new incident" on a
        # long-gap day is a different phenomenon than one on day N of a
        # continuous stream. feature[t] = days since the channel was last
        # reported (0 = reported on day t itself, i.e. every non-gap day).
        rep_gap = np.full(span, 999, np.float32)
        grid = dd[0] + np.arange(span)
        last_idx = np.searchsorted(dd, grid, side="right") - 1
        has = last_idx >= 0
        rep_gap[has] = np.minimum(grid[has] - dd[last_idx[has]], 999)

        crit_full = np.zeros(span, np.int8)
        for i in crit_idx:
            crit_full = np.maximum(crit_full, (full[:, i] > 0).astype(np.int8))
        if new_incident:
            # critical counts only when it began on day t: previous calendar
            # day (t-1) within the same span was not critical. Gap days are
            # zeros, so a state starting after a data gap also counts.
            prev_crit = np.zeros(span, np.int8)
            prev_crit[1:] = crit_full[:-1]
            crit_full = ((crit_full > 0) & (prev_crit == 0)).astype(np.int8)
        label = np.maximum((al > 0).astype(np.int8), crit_full)

        st7 = np.stack([trail_sum(full[:, i], W7) for i in range(N_STATES)], axis=1)
        st30 = np.stack([trail_sum(full[:, i], W30) for i in range(N_STATES)], axis=1)
        div30 = (st30 > 0).sum(axis=1).astype(np.float32)

        feats = np.empty((span, len(feat_cols)), np.float32)
        feats[:, 0:17] = np.stack(
            [e7, a7, e30, a30, cn7, m7, s7, cn30, m30, s30,
             act7, act30, ar7, ar30, since_act, since_alar, div30], axis=1
        )
        if new_incident:
            feats[:, 17] = rep_gap
            st_start = 18
        else:
            st_start = 17
        feats[:, st_start:st_start + N_STATES] = st7
        feats[:, st_start + N_STATES:] = st30

        # emit rows: drop warmup, downsample negatives (per-segment, keeps RAM low)
        keep_idx = np.arange(W30, span)
        lab = label[keep_idx]
        pos = keep_idx[lab == 1]
        neg = keep_idx[lab == 0]
        n_keep_neg = min(len(neg), max(len(pos) * NEG_RATIO, 1))
        if n_keep_neg < len(neg):
            neg = rng.choice(neg, size=n_keep_neg, replace=False)
        sel = np.concatenate([pos, neg])
        writer.add(feats, dd[0], sel, label, chan[s:e][0])

        if writer.pending >= FLUSH_ROWS:
            writer.flush()

    writer.flush()
    del mat, d_ord, chan, writer

    # merge chunk parts into the final single parquet
    parts = sorted(tmp.glob("part-*.parquet"))
    if not parts:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"[{cat}] EMPTY", flush=True)
        return
    table = concat_tables([pq.read_table(str(p)) for p in parts])
    out = FEAT / f"features-{cat}.parquet"
    pq.write_table(table, str(out), compression="zstd")
    shutil.rmtree(tmp, ignore_errors=True)

    # stats via a slim column scan (never holds the full frame in RAM)
    summary = pq.read_table(str(out), columns=["year", "label"]).to_pandas()
    vc = summary.groupby("year")["label"].agg(["count", "mean"])
    npos = int(summary["label"].sum())
    print(f"[{cat}] rows={len(summary):,} pos={npos:,} "
          f"pos_rate={summary['label'].mean():.4f} -> {out.stat().st_size/1e6:.1f}MB "
          f"({time.time()-t0:.0f}s)\n{vc.to_string()}", flush=True)


def main() -> None:
    sen = pd.read_csv(BASE / "справочник_каналов_датчиков.csv")
    vocab = json.loads((BASE / "vocab.json").read_text(encoding="utf-8"))
    cats = sys.argv[1:] if len(sys.argv) > 1 else list(CATS.keys())
    for cat in cats:
        build_category(cat, sen, years=[2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026],
                       crit_names=vocab[cat]["critical"])
    print("FEATURES DONE", flush=True)


if __name__ == "__main__":
    main()
