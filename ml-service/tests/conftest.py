"""Shared pytest configuration for ml-service tests.

A few tests exercise the PRODUCTION data path: they read the real feature
parquets (``ml-data/features/features-<cat>.parquet``) and/or the models
trained from them (the 195-feature LightGBM artifacts under
``ml-service/models/``). Both of those locations are gitignored and live on a
data box, so they cannot be reproduced on a CI runner.

Tests that depend on that data are marked ``@pytest.mark.requires_real_data``.
On a machine where the production parquet is present they run as usual; on a
CI runner (or any clone without the data) they are SKIPPED. CI therefore still
runs the synthetic parity, engine and smoke coverage that needs no data, and
the real-data parity checks still run locally where the data exists.

The data location can be overridden with ``LCT_FEATURES_DIR`` (the app itself
uses /home/junai/lct/ml-data/features by default).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REAL_FEAT_DIR = Path(os.environ.get("LCT_FEATURES_DIR", "/home/junai/lct/ml-data/features"))
_PROBE_PARQUET = REAL_FEAT_DIR / "features-sensor-failure.parquet"
_MODELS_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / ".." / "models"


def real_data_present() -> bool:
    """True when the production data *and* trained models are available locally.

    Both artifacts are required: feature parquets (for LagStore parity) and
    at least one trained model artifact (``models/<cat>/meta.json``), since
    the real-data tests also load persisted models.
    """
    if not _PROBE_PARQUET.exists():
        return False
    return any(_MODELS_DIR.glob("*/meta.json")) if _MODELS_DIR.is_dir() else False


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_real_data: skip unless the production feature parquets are present locally",
    )


def pytest_runtest_setup(item):
    """Skip ``requires_real_data`` tests when the production data is absent."""
    if item.get_closest_marker("requires_real_data") is not None and not real_data_present():
        pytest.skip(
            f"production data not present at {REAL_FEAT_DIR} "
            "(requires_real_data only runs on a data box)",
            allow_module_level=False,
        )
