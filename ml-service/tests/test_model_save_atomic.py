"""Model artifacts must never end up truncated in the persistent volume.

`models/` (the `/app/models` volume) survives restarts, so an interrupted
retrain — OOM kill, container stop, broker-side timeout — has to leave the
PREVIOUS artifact intact rather than a half-written file that no longer loads.

Run from ml-service/:
    ./.venv/bin/python -m pytest tests -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import pytest

from app.models.fsutil import atomic_write
from app.models.lgbm_model import save_artifact
from app.models.registry import ModelRegistry


class FakeBooster:
    """Minimal lgb.Booster stand-in: `save_model` writes text, or dies trying."""

    def __init__(self, payload: str = "new-model", fail_after: int | None = None) -> None:
        self.payload = payload
        self.fail_after = fail_after

    def save_model(self, path) -> None:
        text = self.payload if self.fail_after is None else self.payload[: self.fail_after]
        Path(path).write_text(text, encoding="utf-8")
        if self.fail_after is not None:
            raise RuntimeError("killed mid-write")


class DummyModel:
    """A picklable object without `save_model` -> takes the joblib branch."""

    def __init__(self) -> None:
        self.value = 42


def _temps(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if ".tmp-" in p.name)


def _text(payload: str):
    """A writer that drops ``payload`` into the staging file."""

    def write(tmp: Path) -> None:
        tmp.write_text(payload, encoding="utf-8")

    return write


def test_atomic_write_replaces_the_target(tmp_path):
    target = tmp_path / "model.lgb"
    atomic_write(target, _text("ok"))
    assert target.read_text(encoding="utf-8") == "ok"
    assert _temps(tmp_path) == []


def test_atomic_write_keeps_the_previous_file_when_the_writer_fails(tmp_path):
    target = tmp_path / "model.lgb"
    target.write_text("previous", encoding="utf-8")

    def boom(tmp: Path) -> None:
        tmp.write_text("partial", encoding="utf-8")
        raise RuntimeError("killed mid-write")

    with pytest.raises(RuntimeError):
        atomic_write(target, boom)
    assert target.read_text(encoding="utf-8") == "previous", "old artifact must survive"
    assert _temps(tmp_path) == [], "no staging file may be left behind"


def test_save_artifact_keeps_the_old_model_on_interrupt(tmp_path):
    target = tmp_path / "sensor-failure" / "model.lgb"
    target.parent.mkdir(parents=True)
    target.write_text("trained-v1", encoding="utf-8")

    with pytest.raises(RuntimeError):
        save_artifact(FakeBooster(payload="v2-new", fail_after=2), target)  # type: ignore[arg-type]
    assert target.read_text(encoding="utf-8") == "trained-v1"
    assert _temps(target.parent) == []


def test_save_artifact_writes_and_creates_the_directory(tmp_path):
    target = tmp_path / "fresh-category" / "model.lgb"
    save_artifact(FakeBooster(payload="trained-v2"), target)  # type: ignore[arg-type]
    assert target.read_text(encoding="utf-8") == "trained-v2"
    assert _temps(target.parent) == []


def test_registry_save_keeps_model_and_meta_on_interrupt(tmp_path):
    registry = ModelRegistry(root=tmp_path)
    category = "sensor-failure"
    cat_dir = tmp_path / category
    cat_dir.mkdir()
    (cat_dir / "model.lgb").write_text("trained-v1", encoding="utf-8")
    (cat_dir / "meta.json").write_text(
        json.dumps({"version": "v1", "artifact": "model.lgb"}), encoding="utf-8"
    )

    with pytest.raises(RuntimeError):
        registry.save(
            category, FakeBooster(payload="v2", fail_after=1), ["f1"], {"auc": 0.9}, version="v2"
        )

    assert (cat_dir / "model.lgb").read_text(encoding="utf-8") == "trained-v1"
    assert json.loads((cat_dir / "meta.json").read_text(encoding="utf-8"))["version"] == "v1"
    assert _temps(cat_dir) == []


def test_registry_save_writes_both_files_and_drops_the_stale_engine(tmp_path):
    registry = ModelRegistry(root=tmp_path)
    category = "fire-risk"
    cat_dir = tmp_path / category
    cat_dir.mkdir()
    (cat_dir / "model.joblib").write_bytes(b"stale-sklearn-artifact")

    registry.save(
        category, FakeBooster(payload="lgb-artifact"), ["f1", "f2"], {"auc": 0.88}, version="v9"
    )

    assert (cat_dir / "model.lgb").read_text(encoding="utf-8") == "lgb-artifact"
    assert not (cat_dir / "model.joblib").exists(), "stale engine artifact must be dropped"
    meta = json.loads((cat_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["artifact"] == "model.lgb"
    assert meta["version"] == "v9"
    assert meta["feature_names"] == ["f1", "f2"]
    assert _temps(cat_dir) == []
    assert registry.status(category).state == "trained"


def test_registry_save_joblib_path_still_round_trips(tmp_path):
    """The sklearn/HGB fallback stays loadable through the temp-file write."""
    registry = ModelRegistry(root=tmp_path)
    category = "infrastructure-wear"

    registry.save(category, DummyModel(), ["f1"], {"auc": 0.5})

    meta = json.loads((tmp_path / category / "meta.json").read_text(encoding="utf-8"))
    assert meta["artifact"] == "model.joblib"
    assert joblib.load(tmp_path / category / "model.joblib").value == 42
    assert _temps(tmp_path / category) == []
