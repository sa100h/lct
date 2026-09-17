"""Extract the organizer's ext-journal-*.7z archives into ml-data/extracted/<year>/."""
from __future__ import annotations
import sys
from pathlib import Path
import py7zr

SRC = Path("/home/junai/lct/ml-data")
OUT = SRC / "extracted"


def main() -> None:
    files = sorted(SRC.glob("ext-journal-*.7z"))
    print(f"Found {len(files)} archives")
    for f in files:
        year = f.stem.replace("ext-journal-", "")
        dest = OUT / year
        dest.mkdir(parents=True, exist_ok=True)
        print(f"Extracting {f.name} -> {dest}")
        with py7zr.SevenZipFile(f, mode="r") as z:
            z.extractall(path=dest)
        # report produced files
        prods = [p for p in dest.rglob("*") if p.is_file()]
        print(f"  {len(prods)} files, total {sum(p.stat().st_size for p in prods)/1e6:.1f} MB")
    print("DONE")


if __name__ == "__main__":
    main()
