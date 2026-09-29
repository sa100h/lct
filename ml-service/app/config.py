"""On-disk data locations — one env-driven source of truth.

Why this module exists
----------------------
The serving code used to hardcode the HOST absolute path
``/home/junai/lct/ml-data/features``. docker-compose mounts the same data at
``/app/data`` instead, so inside the container that path did not exist:

* ``LagStore`` loaded empty -> every subject scored the same NaN/zero vector;
* a ``/retrain`` found no parquet, fell back to the 6-feature synthetic
  baseline and OVERWROTE the real LightGBM models in the ``ml_models`` volume.

Result: ``/predict_all_batch`` returned one constant probability for every
sensor. The fix is to resolve the path from the environment, and set
``LCT_DATA_DIR`` in compose so container and host agree.

Environment
-----------
``LCT_DATA_DIR``
    Root data directory. Default ``/home/junai/lct/ml-data`` (the dev box).
    The container sets it to ``/app/data`` (the compose mount point).
``LCT_FEATURES_DIR``
    Optional override for the feature-parquet directory alone; defaults to
    ``$LCT_DATA_DIR/features``. Tests use it to point at a fixture dir.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATA_DIR = "/home/junai/lct/ml-data"


def _env_path(name: str) -> str | None:
    """Read an env path, treating empty/whitespace as unset."""
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


DATA_DIR = Path(_env_path("LCT_DATA_DIR") or DEFAULT_DATA_DIR)
FEATURES_DIR = Path(_env_path("LCT_FEATURES_DIR") or (DATA_DIR / "features"))
