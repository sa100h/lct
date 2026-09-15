"""Registry of model artifacts per category.

Layout: models/<category>/model.joblib + meta.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import joblib
from typing import Literal

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"

CATEGORIES: tuple[str, ...] = (
    "sensor-failure",
    "fire-risk",
    "unauthorized-access",
    "infrastructure-wear",
)
Category = Literal["sensor-failure", "fire-risk", "unauthorized-access", "infrastructure-wear"]


@dataclass
class ModelState:
    category: str
    state: str = "untrained"  # untrained | trained
    model_version: str = "none"
    trained_at: datetime | None = None
    metrics: dict = field(default_factory=dict)


def _load_meta(category: str) -> dict:
    meta_path = MODELS_DIR / category / "meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


class ModelRegistry:
    def __init__(self, root: Path = MODELS_DIR) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, category: str, model, feature_names: list[str], metrics: dict, version: str | None = None) -> None:
        cat_dir = self.root / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        version = version or f"v-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
        joblib.dump(model, cat_dir / "model.joblib")
        meta = {
            "version": version,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "feature_names": feature_names,
            "metrics": metrics,
        }
        (cat_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, category: str):
        model_path = self.root / category / "model.joblib"
        if not model_path.exists():
            raise KeyError(f"No trained model for category '{category}'")
        return joblib.load(model_path)

    def feature_names(self, category: str) -> list[str]:
        return _load_meta(category).get("feature_names", [])

    def threshold(self, category: str) -> float:
        """Decision threshold chosen during evaluation (meta.json 'threshold', default 0.5)."""
        t = _load_meta(category).get("threshold", 0.5)
        try:
            return float(t)
        except (TypeError, ValueError):
            return 0.5

    def status(self, category: str) -> ModelState:
        meta = _load_meta(category)
        if not meta:
            return ModelState(category=category)
        trained_at = meta.get("trained_at")
        return ModelState(
            category=category,
            state="trained",
            model_version=meta.get("version", "unknown"),
            trained_at=datetime.fromisoformat(trained_at) if trained_at else None,
            metrics=meta.get("metrics", {}),
        )


_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
