"""Analytic report: state distribution per sensor type.

Joins agg-<year>.parquet (per channel-day state counts s_*) with
справочник_каналов_датчиков.csv (тип_инж_системы, тип_датчика) and
vocab.json critical-state lists. Outputs:
  ml-data/analysis/state_report.md
  ml-data/analysis/state_report.csv  (long: year, system, sensor_type, state, events, affected_days, affected_channels)
  ml-data/analysis/state_chart.png   (top sensor types x critical events 2025)

Definition of "events" = journal state-count occurrences in s_* (raw counts).
"affected_days" = number of (channel, day) rows where s_i > 0.
"affected_channels" = number of distinct channels where s_i > 0.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

BASE = Path("/home/junai/lct/ml-data")
AGG = BASE / "agg"
OUT = BASE / "analysis"
OUT.mkdir(exist_ok=True)

from app.ingest.aggregate import STATES  # noqa: E402  (run from ml-service)

# s_* column index per state
S_COL = {s: f"s_{i}" for i, s in enumerate(STATES)}

CRIT = json.loads((BASE / "vocab.json").read_text(encoding="utf-8"))
CRIT = {k: v["critical"] for k, v in CRIT.items()}

# reference: channel -> (system, sensor_type)
ref = pd.read_csv(BASE / "справочник_каналов_датчиков.csv", encoding="utf-8")
ref = ref.rename(columns={
    "ид_канала_данных": "channel",
    "тип_инж_системы": "system",
    "тип_датчика": "sensor_type",
})
ref["channel"] = ref["channel"].astype(str)
refmap = ref.set_index("channel")[["system", "sensor_type"]].to_dict("index")

# union of all critical states (tracked); "Штаф" is in vocab but NOT in STATES
all_states = sorted({s for lst in CRIT.values() for s in lst if s in S_COL})
untracked = {s for lst in CRIT.values() for s in lst if s not in S_COL}
cols = ["channel", "day"] + [S_COL[s] for s in STATES]  # all tracked states

years = sorted(p.stem.split("-")[1] for p in AGG.glob("agg-*.parquet")
               if p.stem.split("-")[1].isdigit())
print("years:", years, "| states:", all_states, "| untracked:", untracked)

# long-format accumulator
long_rows = []          # (year, system, sensor_type, state, events, days, ch_count)
# sensor-type totals across ALL tracked states (general distribution)
gen_events = defaultdict(lambda: defaultdict(int))
gen_ch = defaultdict(set)
channel_seen = defaultdict(set)  # year -> set of channels in agg
year_channel_days = defaultdict(int)  # year -> (channel,day) count
n_unmatched = 0
n_total_ch = set()

for y in years:
    df = pd.read_parquet(AGG / f"agg-{y}.parquet", columns=cols)
    df["channel"] = df["channel"].astype(str)
    year_channel_days[y] = len(df)
    channel_seen[y] = set(df["channel"])

    syscol = df["channel"].map(lambda c: refmap.get(c, {}).get("system", "БЕЗ СПРАВОЧНИКА"))
    stcol = df["channel"].map(lambda c: refmap.get(c, {}).get("sensor_type", "БЕЗ СПРАВОЧНИКА"))
    n_unmatched += int((syscol == "БЕЗ СПРАВОЧНИКА").sum())

    grp = df.assign(system=syscol, stype=stcol).groupby(["system", "stype"], observed=True)
    for (system, stype), g in grp:
        gen_events[(system, stype)]["n_ch"] = g["channel"].nunique()
        gen_events[(system, stype)]["n_days"] = len(g)
        n_total_ch |= set(g["channel"].unique())
        for s in all_states:
            c = S_COL[s]
            ev = int(g[c].sum())
            if ev == 0:
                continue
            days = int((g[c] > 0).sum())
            ch = int((g[c].groupby(g["channel"]).max() > 0).sum())
            long_rows.append((y, system, stype, s, ev, days, ch))
            gen_events[(system, stype)][s] = ev
        # general: total tracked-state events per sensor type
        for s in STATES:
            c = S_COL[s]
            v = int(g[c].sum())
            if v:
                gen_events[(system, stype)][f"tot_{s}"] = gen_events[(system, stype)].get(f"tot_{s}", 0) + v

print("unmatched channel-rows:", n_unmatched)

# ---- markdown report ----
L = []
L.append("# Аналитический отчёт: распределение состояний по типам датчиков\n")
L.append(f"Данные: журналы SMVU {years[0]}–{years[-1]} (agg-<year>.parquet), справочник каналов "
         f"({ref.shape[0]} каналов), critical-списки из vocab.json.\n")
L.append("Метрики: **events** = число регистраций состояния в журнале; **days** = число (канал, день) с >=1 событием; "
         "**ch** = число уникальных каналов. Горизонт — все годы и отдельно 2025.\n")
if untracked:
    L.append(f"> ⚠️ Состояние(я) {untracked} есть в vocab.json, но НЕ в списке STATES агрегатора — "
             f"по нему нет с_* колонок, частота посчитана как 0 по ошибке отслеживания (в реальном agg оно может быть в n_events).\n")

# 0. sensor-type landscape
L.append("## 1. Ландшафт датчиков (справочник)\n")
ref_g = ref.groupby(["system", "sensor_type"]).agg(
    channels=("channel", "nunique"),
).sort_values("channels", ascending=False).reset_index()
tot_ch_ref = ref["channel"].nunique()
matched_in_agg = len(n_total_ch)
L.append(f"В справочнике {tot_ch_ref} каналов; в agg-данных появилось {matched_in_agg} уникальных каналов.\n")
L.append("| Инж. система | Тип датчика | Каналов | Доля |")
L.append("|---|---|---:|---:|")
for _, r in ref_g.iterrows():
    L.append(f"| {r['system']} | {r['sensor_type']} | {int(r['channels']):,} | "
             f"{100*r['channels']/tot_ch_ref:.1f}% |")

# 2. per-category critical states
for cat in ["sensor-failure", "fire-risk", "unauthorized-access", "infrastructure-wear"]:
    crit = [s for s in CRIT[cat] if s in S_COL]
    L.append(f"\n## Категория: {cat}\n")
    L.append(f"Critical-состояния: {', '.join(crit)}"
             + (f" (+ отследить не могу: {[s for s in CRIT[cat] if s not in S_COL]})"
                if any(s not in S_COL for s in CRIT[cat]) else "") + "\n")

    # aggregate long_rows by (state, sensor type) across years
    d = [r for r in long_rows if r[3] in set(crit)]
    if not d:
        L.append("Нет событий по отслеживаемым critical-состояниям.\n")
        continue
    tab = pd.DataFrame(d, columns=["year", "system", "stype", "state", "events", "days", "ch"])
    # overall by state
    by_state = tab.groupby("state").agg(events=("events", "sum"), days=("days", "sum"), ch=("ch", "sum"))
    by_state["share%"] = (100 * by_state["events"] / by_state["events"].sum()).round(1)
    L.append("### Состояния: всего по всем годам\n")
    L.append("| Состояние | Events | (канал,день) | Каналов | Доля |")
    L.append("|---|---:|---:|---:|---:|")
    for s, r in by_state.sort_values("events", ascending=False).iterrows():
        L.append(f"| {s} | {int(r['events']):,} | {int(r['days']):,} | {int(r['ch']):,} | {r['share%']} |")

    # per sensor type: 2025 detail
    t25 = tab[tab["year"] == "2025"]
    L.append(f"\n### По типам датчиков, {t25['year'].iloc[0] if len(t25) else 'нет данных'}\n")
    # pivot: sensor type x state events (2025); drop zero columns
    pv = t25.pivot_table(index=["system", "stype"], columns="state", values="events",
                         aggfunc="sum", fill_value=0)
    pv["ИТОГО"] = pv.sum(axis=1)
    pv = pv.sort_values("ИТОГО", ascending=False)
    if len(pv):
        L.append("| Система / датчик | " + " | ".join(pv.columns) + " |")
        L.append("|---" * (len(pv.columns) + 1) + "|")
        for (sys_, st_), r in pv.iterrows():
            if int(r["ИТОГО"]) == 0:
                continue
            cells = " | ".join(f"{int(v):,}" if v else "·" for v in r)
            L.append(f"| {sys_} / {st_} | {cells} |")
    else:
        L.append("Нет событий 2025.\n")

    # top channels by events (all years, this category)
    L.append(f"\n### Топ-10 типов датчиков по events (все годы)\n")
    ty = tab.groupby(["system", "stype"]).agg(events=("events", "sum"), days=("days", "sum"), ch=("ch", "sum"))
    ty = ty.sort_values("events", ascending=False).head(10)
    L.append("| Система / датчик | Events (все годы) | (канал,день) | Каналов |")
    L.append("|---|---:|---:|---:|")
    for (sys_, st_), r in ty.iterrows():
        L.append(f"| {sys_} / {st_} | {int(r['events']):,} | {int(r['days']):,} | {int(r['ch']):,} |")

# 3. general state distribution by sensor type (all tracked states, 2025)
L.append("\n## 2. Общее распределение ВСЕХ отслеживаемых состояний по типам датчиков (2025)\n")
gen25 = {k: v for k, v in gen_events.items()}
L.append("| Система / датчик | Каналов | Канал-дней | Событий (все state) | Топ-3 состояния |")
L.append("|---|---:|---:|---:|---|")
rows = []
for (sys_, st_), v in gen_events.items():
    # per-year not separated in gen_events; it's all-years. acceptable: label all years
    tot = sum(v.get(f"tot_{s}", 0) for s in STATES)
    top = sorted(((v.get(f"tot_{s}", 0), s) for s in STATES), reverse=True)[:3]
    rows.append((sys_, st_, v["n_ch"], v["n_days"], tot,
                 ", ".join(f"{s} ({n:,})" for n, s in top if n)))
rows.sort(key=lambda r: -r[4])
for sys_, st_, nch, nd, tot, top in rows:
    L.append(f"| {sys_} / {st_} | {nch:,} | {nd:,} | {tot:,} | {top} |")
L.append("\n_(агрегировано за все годы — датчики с нуля событий по крит-состояниям видны здесь же)_\n")

# ---- chart: top 12 sensor types by critical events (2025) as text bars ----
t25 = pd.DataFrame([r for r in long_rows if r[0] == "2025"],
                   columns=["year", "system", "stype", "state", "events", "days", "ch"])
if len(t25):
    lab = t25.groupby(["system", "stype"])["events"].sum().sort_values(ascending=False).head(12)
    L.append("\n## 3. Топ типов датчиков по critical-событиям (2025) — диаграмма\n")
    mx = max(lab.values) if len(lab) else 1
    for (sys_, st_), v in lab.items():
        bar = "#" * int(40 * v / mx) if mx else ""
        L.append(f"`{sys_} / {st_}`  {int(v):>8,}  {bar}")

md = "\n".join(L)
(OUT / "state_report.md").write_text(md, encoding="utf-8")

# CSV long
pd.DataFrame(long_rows, columns=["year", "system", "sensor_type", "state", "events", "affected_days", "affected_channels"]).to_csv(
    OUT / "state_report.csv", index=False, encoding="utf-8-sig")
print("wrote", OUT / "state_report.md", len(md), "chars;", len(long_rows), "long rows")
