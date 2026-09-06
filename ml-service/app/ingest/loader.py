"""Ingest helpers for the organizer's data formats.

Expected inputs (from the hackathon brief):
  - SMVU historical logs: .xlsx alarm event exports (sensor id, time, type,
    address, verification outcome), 12+ years
  - ODS journals: alarm journal, sensor fault journal, picket plans
  - OE equipment registers: funds by district (shafts, pumps, chambers,
    sensors, hatches) with commissioning dates + repair history
  - ARM-Kontrol: permit register and work applications (organization,
    dates, names, work type)

Pipeline:
  load_xlsx(path) -> DataFrame        (raw export)
  -> transform/<category>_features() -> feature rows (X + label)
  -> saved to data/<category>/<name>.parquet
  -> BaselineTrainer().fit(category)  re-learns on the ingested set
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_xlsx(path: str | Path, sheet_name: int | str = 0) -> pd.DataFrame:
    """Load one .xlsx export (openpyxl engine)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")


def save_features(category: str, df: pd.DataFrame, name: str) -> Path:
    """Persist a feature matrix (with 'label' column) for the trainer."""
    cat_dir = DATA_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    out = cat_dir / f"{name}.parquet"
    df.to_parquet(out, index=False)
    return out


# ---------------------------------------------------------------------------
# Category feature transforms — TODO(hackathon): implement on real exports.
# Signatures are fixed so the training entrypoint works uniformly.
# ---------------------------------------------------------------------------

def sensor_failure_features(df: pd.DataFrame) -> pd.DataFrame:
    """SMVU alarm log -> per-sensor features + failure label."""
    raise NotImplementedError("Implement on real SMVU .xlsx exports")


def fire_risk_features(df: pd.DataFrame) -> pd.DataFrame:
    """Temperature/smoke dynamics + ARM-Kontrol work permits -> features + label."""
    raise NotImplementedError("Implement on real SMVU + ARM-Kontrol exports")


def unauthorized_access_features(df: pd.DataFrame) -> pd.DataFrame:
    """Contact/volume sensor trips + access control + permits -> features + label."""
    raise NotImplementedError("Implement on real SMVU + SCADA exports")


def infrastructure_wear_features(df: pd.DataFrame) -> pd.DataFrame:
    """Visual inspection + age + usage intensity -> features + label."""
    raise NotImplementedError("Implement on real OE register exports")


TRANSFORMS = {
    "sensor-failure": sensor_failure_features,
    "fire-risk": fire_risk_features,
    "unauthorized-access": unauthorized_access_features,
    "infrastructure-wear": infrastructure_wear_features,
}
