"""Atomic file writes for model artifacts.

The models directory is a PERSISTENT volume, so a model written by a retrain
survives container restarts. That makes a half-written artifact worse than a
missing one: `booster.save_model()` interrupted mid-write leaves the category
unloadable until the next successful retrain — and a retrain is exactly the
place where the process can be killed (OOM on a small box, container stop,
broker-side timeout).

`atomic_write` writes a temporary sibling and then `os.replace`s it onto the
target. On POSIX that rename is atomic, so a concurrent reader sees either the
previous artifact or the complete new one, never a truncated file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

__all__ = ["atomic_write"]


def atomic_write(path: Path, write: Callable[[Path], None]) -> None:
    """Run ``write(tmp)``, then move ``tmp`` onto ``path`` in one rename.

    The temporary name carries the pid so two processes writing the same
    category cannot clobber each other's staging file; the last ``replace``
    wins, and both files are complete ones.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        write(tmp)
        with open(tmp, "rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():  # only left behind when write() raised
            tmp.unlink()
