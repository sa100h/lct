"""Merge a partial state-scan.json (resumed single-year run) into the base one.

state_scan.py's resume semantics: a resumed run only accumulates counters for
the years scanned in THAT run, and the final snapshot overwrites the json.
So: base = full-coverage json (years A), partial = json from the resumed run
(years B, disjoint). This script sums the counters, unifies per-type min/max,
and rewrites the *-not-in-dict / dict_never_seen lists from the merged sets.
"""
from __future__ import annotations
import json
import shutil
import sys
from collections import Counter


def _load(p: str) -> dict:
    return json.loads(open(p, encoding="utf-8").read())


def _add_counter(a: dict, b: dict) -> dict:
    for k, v in b.items():
        a[k] = a.get(k, 0) + v
    return a


def _add_num_stats(base: dict, part: dict) -> None:
    for ty, s in part.items():
        if ty not in base:
            base[ty] = dict(s)
            continue
        d = base[ty]
        d["n"] += s["n"]
        d["min"] = min(d["min"], s["min"])
        d["max"] = max(d["max"], s["max"])
        d["sum"] += s["sum"]


def main() -> None:
    base_p, part_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    base, part = _load(base_p), _load(part_p)

    assert not set(base["year_progress"]) & set(part["year_progress"]), "year overlap"

    base["n_raw"] += part["n_raw"]
    base["n_kept"] += part["n_kept"]
    base["year_progress"] = sorted(set(base["year_progress"]) | set(part["year_progress"]))
    base["state_total"] = _add_counter(base["state_total"], part["state_total"])
    base["state_alarm"] = _add_counter(base["state_alarm"], part["state_alarm"])
    base["state_type"] = _add_counter(base["state_type"], part["state_type"])
    base["n1970"] = _add_counter(base["n1970"], part["n1970"])
    base["n1970_type"] = _add_counter(base["n1970_type"], part["n1970_type"])
    _add_num_stats(base["num_stats"], part["num_stats"])
    base["gas_hist"] = [a + b for a, b in zip(base["gas_hist"], part["gas_hist"])]

    seen = set(base["state_total"])
    dict_states = set(base["dict_states"])
    base["state_not_in_dict"] = sorted(seen - dict_states)
    base["dict_state_never_seen"] = sorted(dict_states - seen)
    base["alarm_state_not_in_dict"] = sorted(set(base["state_alarm"]) - dict_states)

    shutil.copyfile(out_p, out_p + ".premerge.bak")
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=1)
    print(f"merged: years={base['year_progress']} n_raw={base['n_raw']:,}")
    print(f"states seen={len(seen)} in_dict={len(seen & dict_states)} "
          f"not_in_dict={len(seen - dict_states)} dict_never_seen={len(dict_states - seen)}")


if __name__ == "__main__":
    main()
