"""Fetch Moscow daily weather for the LCT data window (2019-01-01 .. 2026-09-19)
from Open-Meteo archive API (free, no key). One request per year, verified.

Output: /home/junai/lct/ml-data/weather/weather-moscow-daily.parquet (+ .csv)
Grain: 1 row per Moscow-local calendar day. `day` = 'YYYY-MM-DD' (matches agg).
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

LAT, LON = 55.7558, 37.6173  # central Moscow proxy (no per-station coords in data)
BASE = "https://archive-api.open-meteo.com/v1/archive"

# Rich daily set that is plausibly linked to sensor breakage in utility collectors:
# temperature (mean/min/max + apparent), precipitation (total/rain/snow/hours),
# wind (mean/max + gusts), pressure, humidity, radiation, day length, weather code.
DAILY = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "apparent_temperature_max", "apparent_temperature_min",
    "precipitation_sum", "rain_sum", "snowfall_sum", "precipitation_hours",
    "wind_speed_10m_mean", "wind_speed_10m_max", "wind_gusts_10m_max",
    "pressure_msl_mean", "relative_humidity_2m_mean",
    "shortwave_radiation_sum",
    "weather_code",
]

YEARS = list(range(2019, 2027))
OUT = "/home/junai/lct/ml-data/weather/weather-moscow-daily.parquet"


def fetch_range(start, end):
    params = {
        "latitude": LAT, "longitude": LON,
        "start_date": start, "end_date": end,
        "daily": ",".join(DAILY),
        "timezone": "Europe/Moscow",
    }
    url = BASE + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed for {start}..{end}: {last}")


def main():
    frames = []
    for y in YEARS:
        if y == 2026:
            end = "2026-09-19"
        else:
            end = f"{y}-12-31"
        start = f"{y}-01-01"
        d = fetch_range(start, end)
        daily = d.get("daily", {})
        n = len(daily.get("time", []))
        # expected days in this range
        exp = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
        status = "OK" if n == exp else f"WANT {exp} got {n}"
        print(f"{y}: {start}..{end}  days={n}  [{status}]")
        if n != exp:
            sys.exit(1)
        rec = {"day": daily["time"]}
        for k in DAILY:
            rec[k] = daily.get(k)
        frames.append(pd.DataFrame(rec))

    df = pd.concat(frames, ignore_index=True)
    df["day"] = df["day"].str[:10]
    df = df.reset_index(drop=True)
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    # integrity: no gaps, unique, sorted
    assert df["day"].is_unique, "duplicate days"
    assert len(df) == df["day"].nunique()
    span = (pd.Timestamp(df["day"].max()) - pd.Timestamp(df["day"].min())).days + 1
    assert len(df) == span, f"gap in series: {len(df)} != {span}"
    df.to_parquet(OUT)
    df.to_csv(OUT.replace(".parquet", ".csv"), index=False)
    na = int(df[DAILY].isna().sum().sum())
    print(f"\nSaved {len(df)} days  {df['day'].min()} .. {df['day'].max()}  -> {OUT}")
    print(f"Total NaN cells across weather vars: {na}")
    print("\nHead:\n", df.head(3).to_string(index=False))
    print("\nTail:\n", df.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
