"""Shared pytest configuration for ml-broker tests.

All tests are pure unit tests (mocked DB, mocked httpx client) — no Docker,
no Postgres, no network. Run from the repo root:

    ~/venvs/lct-ml/bin/python -m pytest ml-broker/tests -q

The ``app`` package lives in ``ml-broker/``; tests are run from the repo
root, so make it importable here.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
