"""Regression guards for the container data-path bug (2026-09-29).

The serving modules hardcoded the HOST absolute path
``/home/junai/lct/ml-data/features``. docker-compose mounts the same data at
``/app/data``, so inside the container the path did not exist: the LagStore
loaded empty, every subject got the NaN/zero vector, a retrain fell back to the
synthetic baseline and OVERWROTE the real models — serving then returned one
constant probability for every sensor.

These tests pin the two fixes that prevent a silent recurrence:
  * one env-driven source of truth for the data location (``app.config``);
  * ``LCT_ALLOW_SYNTHETIC=false`` refuses the synthetic fallback.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

HOST_FEATURES = "/home/junai/lct/ml-data/features"
SERVING_MODULES = (
    "app/predict/lag_store.py",
    "app/models/lgbm_model.py",
    "app/models/baseline.py",
)


def test_config_honours_env_overrides(monkeypatch):
    from app import config

    try:
        monkeypatch.setenv("LCT_DATA_DIR", "/srv/lct-data")
        monkeypatch.delenv("LCT_FEATURES_DIR", raising=False)
        importlib.reload(config)
        assert str(config.DATA_DIR) == "/srv/lct-data"
        assert str(config.FEATURES_DIR) == "/srv/lct-data/features"

        monkeypatch.setenv("LCT_FEATURES_DIR", "/mnt/feat")
        importlib.reload(config)
        assert str(config.FEATURES_DIR) == "/mnt/feat"
    finally:
        monkeypatch.delenv("LCT_DATA_DIR", raising=False)
        monkeypatch.delenv("LCT_FEATURES_DIR", raising=False)
        importlib.reload(config)
        assert str(config.FEATURES_DIR) == HOST_FEATURES, "default must stay the host path"


def test_serving_modules_take_features_dir_from_config():
    """Every serving module reads the SAME configured features dir.

    This is the regression guard: one module drifting back to a hardcoded
    literal is exactly what produced the empty LagStore in the container."""
    from app import config
    from app.models import baseline, lgbm_model
    from app.predict import lag_store

    assert lag_store.FEAT_DIR == config.FEATURES_DIR
    assert baseline.FEAT_DIR == config.FEATURES_DIR
    assert lgbm_model.FEAT_DIR == config.FEATURES_DIR


def test_no_hardcoded_features_path_left_in_serving_modules():
    root = Path(__file__).resolve().parent.parent
    offenders = [
        rel for rel in SERVING_MODULES if HOST_FEATURES in (root / rel).read_text(encoding="utf-8")
    ]
    assert not offenders, f"hardcoded data path still present in: {offenders}"


# --------------------------------------------------------------------------- #
# synthetic fallback must be refusable in the container
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("raw,expected", [("false", False), ("0", False), ("no", False),
                                          ("true", True), ("1", True), ("", True)])
def test_allow_synthetic_flag_parsing(monkeypatch, raw, expected):
    from app.models import baseline

    monkeypatch.setenv("LCT_ALLOW_SYNTHETIC", raw)
    assert baseline._allow_synthetic() is expected


def test_retrain_refuses_synthetic_when_disallowed(monkeypatch, tmp_path):
    """No parquet + LCT_ALLOW_SYNTHETIC=false -> raise, do NOT train a stub.

    Guards the incident path: a container retrain must never silently replace a
    real model with a 6-feature synthetic baseline.

    The registry is redirected into ``tmp_path`` FIRST. While this test's guard
    did not exist yet (RED state) it reached ``_train_synthetic`` and wrote a
    synthetic ``model.joblib`` over the production sensor-failure artifact. A
    test must never be able to touch the real models dir — not even while it is
    asserting that the write path is refused.
    """
    from app.models import baseline
    from app.models.registry import ModelRegistry

    monkeypatch.setattr(baseline, "get_registry", lambda: ModelRegistry(tmp_path / "models"))
    monkeypatch.setenv("LCT_ALLOW_SYNTHETIC", "false")
    monkeypatch.setattr(baseline, "FEAT_DIR", tmp_path / "empty-features")

    with pytest.raises(RuntimeError, match="LCT_ALLOW_SYNTHETIC"):
        baseline.BaselineTrainer().fit("sensor-failure")

    written = list((tmp_path / "models").rglob("*")) if (tmp_path / "models").exists() else []
    assert [p for p in written if p.is_file()] == [], "refusal must not write any artifact"


def test_synthetic_fallback_still_works_when_allowed(monkeypatch, tmp_path):
    """Default (unset) keeps the CI/demo fallback: trains into tmp, not prod."""
    from app.models import baseline
    from app.models.registry import ModelRegistry

    monkeypatch.setattr(baseline, "get_registry", lambda: ModelRegistry(tmp_path / "models"))
    monkeypatch.delenv("LCT_ALLOW_SYNTHETIC", raising=False)
    monkeypatch.setattr(baseline, "FEAT_DIR", tmp_path / "empty-features")

    metrics = baseline.BaselineTrainer().fit("sensor-failure")
    assert metrics["source"] == "synthetic-baseline"
    assert (tmp_path / "models" / "sensor-failure" / "model.joblib").exists()
