"""Unit tests: build_vector priority (client > server-side value > 0.0) and
choose_threshold (argmax F1 on the validation grid).

No real models or data involved: the engine's registry and the LagStore are
replaced with fakes, so the tests pin the assembly CONTRACT, not the artifacts.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.ingest.lag_features import LAG_FEATURES
from app.models.lgbm_model import choose_threshold
from app.predict import engine as engine_mod
from app.predict.engine import PredictEngine


class FakeRegistry:
    """Minimal stand-in for ModelRegistry as seen by PredictEngine."""

    def __init__(self, names: list[str]) -> None:
        self._names = names

    def feature_names(self, category: str) -> list[str]:
        return self._names


class FakeStore:
    """Minimal stand-in for LagStore (lags_for / latest_features_for)."""

    def __init__(self, lags: dict[str, float], latest: dict[str, float] | None) -> None:
        self._lags = lags
        self._latest = latest or {}

    def lags_for(self, category: str, subject_id: str, as_of):
        if subject_id == "no-history":
            return {k: float("nan") for k in self._lags}
        return dict(self._lags)

    def latest_features_for(self, category: str, subject_id: str):
        if subject_id == "no-history":
            return None
        return dict(self._latest)


@pytest.fixture
def built(monkeypatch):
    """PredictEngine wired to fakes; (engine, vector) per build call is
    available via the returned builder. Feature names: 3 base + 1 lag."""
    lag_name = LAG_FEATURES[0]
    names = ["f_a", "f_b", "f_c", lag_name]
    store = FakeStore(
        lags={k: (11.0 if k == lag_name else float("nan")) for k in LAG_FEATURES},
        latest={"f_a": 1.0, "f_b": 2.0},  # f_c intentionally absent -> 0.0
    )
    monkeypatch.setattr(engine_mod, "get_store", lambda: store)
    eng = PredictEngine()
    eng._registry = FakeRegistry(names)  # type: ignore[assignment]
    return eng, names, store


def test_priority_client_over_everything(built):
    eng, names, _ = built
    vector = eng.build_vector("sensor-failure", "s1", {"f_a": 9.0, names[3]: 7.0}, as_of=None)  # type: ignore[arg-type]
    vector = [v if not (isinstance(v, float) and math.isnan(v)) else None for v in vector]
    assert vector[0] == 9.0, "client base feature must win"
    assert vector[names.index(names[3])] == 7.0, "client lag must win over store"


def test_lag_slot_uses_store_when_client_absent(built):
    eng, names, _ = built
    vector = eng.build_vector("sensor-failure", "s1", {}, as_of=None)  # type: ignore[arg-type]
    assert vector[names.index(names[3])] == 11.0, "lag slot: store value when client omits it"


def test_base_slot_latest_then_zero(built):
    eng, names, _ = built
    vector = eng.build_vector("sensor-failure", "s1", {}, as_of=None)  # type: ignore[arg-type]
    assert vector[0] == 1.0, "f_a: latest store row"
    assert vector[1] == 2.0, "f_b: latest store row"
    assert vector[2] == 0.0, "f_c: absent from client and store -> 0.0"


def test_unknown_subject_lags_nan_vector(built):
    eng, names, _ = built
    vector = eng.build_vector("sensor-failure", "no-history", {}, as_of=None)  # type: ignore[arg-type]
    lag_slot = vector[names.index(names[3])]
    assert isinstance(lag_slot, float) and math.isnan(lag_slot), "no-history subject -> NaN lag"
    assert vector[0] == 0.0, "no-history subject -> base falls through to 0.0"


# --------------------------------------------------------------------------- #
# choose_threshold
# --------------------------------------------------------------------------- #


def test_choose_threshold_argmax_f1():
    """Where the F1-max threshold is obvious (proba cleanly separated)."""
    y = np.array([0, 0, 0, 1, 1, 1])
    proba = np.array([0.10, 0.20, 0.40, 0.60, 0.80, 0.90])
    t = choose_threshold(y, proba)
    assert 0.30 <= t <= 0.70, t
    # any threshold in (0.4, 0.6] is F1=1.0; the choice must land there
    from sklearn.metrics import f1_score

    assert f1_score(y, (proba >= t).astype(int)) == 1.0


def test_choose_threshold_grid_values():
    """Result is always an actual grid point (0.05..0.95 step 0.005)."""
    y = np.array([0, 1, 1, 0, 1])
    proba = np.array([0.3, 0.7, 0.6, 0.4, 0.65])
    t = choose_threshold(y, proba)
    assert t in {round(x, 3) for x in np.arange(0.05, 0.951, 0.005)}


def test_choose_threshold_no_positives_defaults_05():
    y = np.zeros(10, dtype=int)
    proba = np.linspace(0.1, 0.9, 10)
    assert choose_threshold(y, proba) == 0.5
