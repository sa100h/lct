"""Stage 2: per-category feature matrix from per-(channel,day) aggregates.

One row per (channel, day) inside each channel's observed span per year:
  - features: trailing 7d/30d aggregates over days strictly BEFORE day t
    (events, alarms, numeric stats, state counts, activity density, days since
    last activity/alarm, state diversity) — no same-day information.
    Plus: calendar seasonality (month sin/cos, day of week) and static
    per-channel cabinet/object codes, and the intra-day hour profile
    (e7h_*/a7h_*: trailing 7d per-hour event/alarm counts from
    agg-hour-<year>.parquet; night_share7/peak_share7: shares of 00-05
    and 08-20 hours in the same window) — all strictly-before-t, same
    anti-leak horizon as the day-level features.
  - label: 1 if on day t the channel emits an alarm (тревожение=true) or any
    category-critical state (per vocab.json "critical").

Horizon: decision made at end of day t-1, outcome measured on day t (24h).
Negatives are downsampled per channel-span (~1:NEG_RATIO, seeded) to keep
RAM bounded on a ~4GB box; the trainer re-balances globally.
Memory: ONE year is read at a time and emitted rows go straight to temporary
parquet parts (FLUSH_ROWS each); the cross-year channel-day matrix is never
materialized. Channel spans are cut at year boundaries (up to 30d of warm-up
history is lost at each January 1 — negligible over 8 years).
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
W7, W14, W30 = 7, 14, 30
N_STATES = len(STATES)
FLUSH_ROWS = 300_000  # write parquet chunks, never one giant in-RAM frame


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
    # static per-channel references: channel id -> cabinet / object code, so the
    # model can learn cabinet- and object-level effects. Unmatched -> -1.
    sen_ch = sen.copy()
    sen_ch["ид_канала_данных"] = sen_ch["ид_канала_данных"].astype(str)
    sen_ch = sen_ch.set_index("ид_канала_данных")
    cab_enc = sen_ch["cabinet"].to_dict()
    obj_enc = sen_ch["ид_объект"].to_dict()
    t0 = time.time()

    _feat_cols = (
        ["e7", "a7", "e30", "a30", "n7", "m7", "s7", "n30", "m30", "s30",
         "act7", "act30", "ar7", "ar30", "since_act", "since_alar", "div30"]
        + (["rep_gap"] if new_incident else [])
        + ["month_sin", "month_cos", "dow", "cabinet", "object_code"]
        + [f"t7_{i}" for i in range(N_STATES)]
        + [f"t30_{i}" for i in range(N_STATES)]
        + ["e14", "a14", "n14", "m14", "s14", "act14", "ar14"]
        + [f"tr7_{i}" for i in range(N_STATES)]
        + [f"tr14_{i}" for i in range(N_STATES)]
        + ["ch_age"]
        + [f"e7h_{h}" for h in range(24)]
        + [f"a7h_{h}" for h in range(24)]
        + ["night_share7", "peak_share7"]
    )
    feat_cols = _feat_cols
    n_head = 18 if new_incident else 17

    tmp = FEAT / f".tmp-{cat}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    writer = ChunkWriter(tmp, feat_cols, rng)

    for year in years:
        f = AGG / f"agg-{year}.parquet"
        if not f.exists():
            print(f"  [warn] missing {f}", flush=True)
            continue
        df = pd.read_parquet(f, columns=["channel", "day", *base_cols, *s_cols])
        df = df[df["channel"].isin(chset)].sort_values(["channel", "day"])
        # Intra-day hour records for this year: channel -> ndarray(n,4)
        # [day_ord, hour, n_events, n_alarm]. Used to build the per-hour
        # trailing-7d features; EXCLUDE_SPANS/filters mirror the day agg.
        hour_by_chan: dict[str, np.ndarray] = {}
        hfile = AGG / f"agg-hour-{year}.parquet"
        if hfile.exists():
            h_df = pd.read_parquet(hfile, columns=["channel", "day", "hour", "n_events", "n_alarm"])
            h_df = h_df[h_df["channel"].isin(chset)]
            if len(h_df):
                h_ord = (pd.to_datetime(h_df["day"], format="%Y-%m-%d")
                         .astype("int64").to_numpy() // 10**9)
                h_df = h_df.assign(_ord=h_ord).sort_values("channel")
                for ch, grp in h_df.groupby("channel", sort=False):
                    hour_by_chan[str(ch)] = np.column_stack((
                        grp["_ord"], grp["hour"], grp["n_events"], grp["n_alarm"],
                    )).astype(np.int32)
                print(f"  {cat} {year}: hour-agg {len(h_df):,} rows, "
                      f"{len(hour_by_chan):,} channels", flush=True)
            del h_df
        else:
            print(f"  [warn] missing {hfile} — hour features will be zero", flush=True)
        for c in ("num_min", "num_max"):
            df[c] = df[c].fillna(0.0)
        mat = df[base_cols + s_cols].to_numpy(np.float32)
        day_ts = np.asarray(df["day"].to_numpy(), dtype="datetime64[D]")  # day-ordinals
        d_ord = day_ts.astype(np.int64)
        chan = df["channel"].to_numpy()
        n = len(d_ord)
        if n == 0:
            del df, mat, d_ord, chan
            continue
        print(f"  {cat} {year}: {n:,} channel-days, {len(np.unique(chan))} channels "
              f"elapsed={time.time()-t0:.0f}s", flush=True)

        change = np.flatnonzero(chan[:-1] != chan[1:]) + 1
        bounds = np.concatenate([[0], change, [n]])

        k = 0
        for s, e in zip(bounds[:-1], bounds[1:]):
            if (k + 1) % 2000 == 0:
                print(f"  {cat}: channels {k+1}/{len(bounds)-1} "
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
            e14, a14 = trail_sum(ev, W14), trail_sum(al, W14)
            cn7 = trail_sum(nn, W7); cs7 = trail_sum(nsum, W7); c27 = trail_sum(nsq, W7)
            cn14 = trail_sum(nn, W14); cs14 = trail_sum(nsum, W14); c214 = trail_sum(nsq, W14)
            cn30 = trail_sum(nn, W30); cs30 = trail_sum(nsum, W30); c230 = trail_sum(nsq, W30)
            m7 = np.where(cn7 > 0, cs7 / np.maximum(cn7, 1), 0.0)
            s7 = np.sqrt(np.clip(c27 / np.maximum(cn7, 1) - m7**2, 0, None))
            m14 = np.where(cn14 > 0, cs14 / np.maximum(cn14, 1), 0.0)
            s14 = np.sqrt(np.clip(c214 / np.maximum(cn14, 1) - m14**2, 0, None))
            m30 = np.where(cn30 > 0, cs30 / np.maximum(cn30, 1), 0.0)
            s30 = np.sqrt(np.clip(c230 / np.maximum(cn30, 1) - m30**2, 0, None))

            active = ev > 0
            act7 = trail_sum(active.astype(np.float32), W7) / W7
            act14 = trail_sum(active.astype(np.float32), W14) / W14
            act30 = trail_sum(active.astype(np.float32), W30) / W30
            ar7 = a7 / np.maximum(e7, 1)
            ar14 = a14 / np.maximum(e14, 1)
            ar30 = a30 / np.maximum(e30, 1)
            since_act = since_last(active.astype(np.int8)).astype(np.float32)
            since_alar = since_last(al).astype(np.float32)
            # calendar days since the channel was last REPORTED, as of end of
            # day t-1. side="left" takes the last report strictly BEFORE day t
            # (>=1 on a reported day, never 0): the previous side="right"
            # version returned 0 on day t itself and leaked "channel reported
            # today" into features (all 2026 positives had rep_gap==0, AUC
            # 0.94). Encodes reporting cadence, not the label.
            rep_gap = np.full(span, 999, np.float32)
            grid = dd[0] + np.arange(span)
            last_idx = np.searchsorted(dd, grid, side="left") - 1
            has = last_idx >= 0
            rep_gap[has] = np.minimum(grid[has] - dd[last_idx[has]], 999)

            crit_full = np.zeros(span, np.int8)
            for i in crit_idx:
                crit_full = np.maximum(crit_full, (full[:, i] > 0).astype(np.int8))
            if new_incident:
                # critical counts only when it began on day t: previous
                # calendar day (t-1) within the same span was not critical.
                # Gap days are zeros, so a state starting after a data gap
                # also counts.
                prev_crit = np.zeros(span, np.int8)
                prev_crit[1:] = crit_full[:-1]
                crit_full = ((crit_full > 0) & (prev_crit == 0)).astype(np.int8)
            label = np.maximum((al > 0).astype(np.int8), crit_full)

            st7 = np.stack([trail_sum(full[:, i], W7) for i in range(N_STATES)], axis=1)
            st30 = np.stack([trail_sum(full[:, i], W30) for i in range(N_STATES)], axis=1)
            div30 = (st30 > 0).sum(axis=1).astype(np.float32)

            # state transition counts: how many days within the window the
            # state BEGAN (day t-1 was not in that state, day t is). A bursty
            # state (many on/off flips) is a stronger anomaly signal than the
            # same total number of days. Same strict-before-t horizon via
            # trail_sum on the transition indicator.
            tr7 = np.empty((span, N_STATES), np.float32)
            tr14 = np.empty((span, N_STATES), np.float32)
            for i in range(N_STATES):
                x = full[:, i] > 0
                on = x.copy()
                on[1:] = x[1:] & ~x[:-1]
                onf = on.astype(np.float32)
                tr7[:, i] = trail_sum(onf, W7)
                tr14[:, i] = trail_sum(onf, W14)

            # channel age: calendar days since the channel's first report in
            # the data (as of end of t-1). Young channels have unreliable
            # state trails (fire detector rollout 1977->6830 over 8 years),
            # so the model can down-weight them. dd is the reported-day
            # positions, NOT the full span — first report = dd[0], strictly-
            # before-t via grid-1.
            first_dd = dd[0]
            age = np.full(span, 999, np.float32)
            had = grid - 1 >= first_dd
            age[had] = np.minimum(np.maximum((grid[had] - 1 - first_dd), 0), 999)

            feats = np.empty((span, len(feat_cols)), np.float32)
            feats[:, 0:17] = np.stack(
                [e7, a7, e30, a30, cn7, m7, s7, cn30, m30, s30,
                 act7, act30, ar7, ar30, since_act, since_alar, div30], axis=1
            )
            if new_incident:
                feats[:, 17] = rep_gap
                extra_start = 18
            else:
                extra_start = 17
            # seasonality (calendar, no leak: purely a function of day t) +
            # static per-channel cabinet/object codes (NaN -> -1)
            gdt = pd.to_datetime((dd[0] + np.arange(span)).astype(np.int64), unit="D")
            mnum = gdt.month.to_numpy()
            feats[:, extra_start:extra_start + 2] = np.stack(
                [np.sin(2 * np.pi * mnum / 12.0), np.cos(2 * np.pi * mnum / 12.0)],
                axis=1,
            ).astype(np.float32)
            feats[:, extra_start + 2] = gdt.dayofweek.to_numpy().astype(np.float32)
            ch_id = chan[s:e][0]
            feats[:, extra_start + 3] = cab_enc.get(str(ch_id), -1)
            feats[:, extra_start + 4] = obj_enc.get(str(ch_id), -1)
            st_start = extra_start + 5
            feats[:, st_start:st_start + N_STATES] = st7
            feats[:, st_start + N_STATES:st_start + 2 * N_STATES] = st30
            w14_start = st_start + 2 * N_STATES
            feats[:, w14_start:w14_start + 7] = np.stack(
                [e14, a14, cn14, m14, s14, act14, ar14], axis=1,
            ).astype(np.float32)
            tr_start = w14_start + 7
            feats[:, tr_start:tr_start + N_STATES] = tr7
            feats[:, tr_start + N_STATES:tr_start + 2 * N_STATES] = tr14
            feats[:, tr_start + 2 * N_STATES] = age

            # Intra-day hour profile: trailing 7d per-hour event/alarm counts
            # (strictly before t). Sparse (day,hour) records are scattered into
            # a span×24 grid, then trail_sum per hour. night/peak shares are
            # the 00:00-05:00 and 08:00-20:00 shares of the 7d event total.
            ho_start = tr_start + 2 * N_STATES + 1
            harr = hour_by_chan.get(str(ch_id))
            if harr is not None and len(harr):
                d_idx = harr[:, 0] - dd[0]
                ok = (d_idx >= 0) & (d_idx < span) & (harr[:, 1] >= 0) & (harr[:, 1] < 24)
                d_idx, hh = d_idx[ok], harr[ok, 1]
                hour_ev = np.zeros((span, 24), np.float32)
                hour_al = np.zeros((span, 24), np.float32)
                np.add.at(hour_ev, (d_idx, hh), harr[ok, 2].astype(np.float32))
                np.add.at(hour_al, (d_idx, hh), harr[ok, 3].astype(np.float32))
                e7h = np.empty((span, 24), np.float32)
                a7h = np.empty((span, 24), np.float32)
                for h in range(24):
                    e7h[:, h] = trail_sum(hour_ev[:, h], W7)
                    a7h[:, h] = trail_sum(hour_al[:, h], W7)
                ev_tot = np.maximum(e7h.sum(axis=1), 1.0)
                night_share7 = e7h[:, 0:6].sum(axis=1) / ev_tot
                peak_share7 = e7h[:, 8:20].sum(axis=1) / ev_tot
            else:
                e7h = np.zeros((span, 24), np.float32)
                a7h = np.zeros((span, 24), np.float32)
                night_share7 = np.zeros(span, np.float32)
                peak_share7 = np.zeros(span, np.float32)
            feats[:, ho_start:ho_start + 24] = e7h
            feats[:, ho_start + 24:ho_start + 48] = a7h
            feats[:, ho_start + 48] = night_share7
            feats[:, ho_start + 49] = peak_share7

            # emit rows: reported days only, after warmup; downsample
            # negatives (per-segment, keeps RAM low). Gap days are NOT
            # emitted: a new incident is only observable in a report, and
            # all-zero gap rows made the label a reporting-cadence predictor
            # (rep_gap leak, AUC 0.96).
            rep_days = np.zeros(span, np.bool_)
            rep_days[idx] = True
            keep_idx = np.flatnonzero(rep_days & (np.arange(span) >= W30))
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
            k += 1
        del df, mat, d_ord, chan, day_ts

    writer.flush()
    del writer

    # merge chunk parts into the final single parquet. Use a streaming
    # ParquetWriter (append parts one-by-one, no in-RAM concat): the dense
    # feature matrix at 135 cols is ~1.3GB for sensor-failure and an
    # in-RAM concat_tables + to_pandas frame overflowed 3.8GB (SIGKILL 137).
    parts = sorted(tmp.glob("part-*.parquet"))
    if not parts:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"[{cat}] EMPTY", flush=True)
        return
    out = FEAT / f"features-{cat}.parquet"
    first = pq.read_table(str(parts[0]))
    with pq.ParquetWriter(str(out), first.schema, compression="zstd") as w:
        for p in parts:
            w.write_table(pq.read_table(str(p)))
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
    sen["cabinet"] = sen["тег_инженерной_системы"].astype(str).str.extract(r"^(\d+)-")[0]
    vocab = json.loads((BASE / "vocab.json").read_text(encoding="utf-8"))
    cats = sys.argv[1:] if len(sys.argv) > 1 else list(CATS.keys())
    for cat in cats:
        build_category(cat, sen, years=[2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026],
                       crit_names=vocab[cat]["critical"])
    print("FEATURES DONE", flush=True)


if __name__ == "__main__":
    main()
