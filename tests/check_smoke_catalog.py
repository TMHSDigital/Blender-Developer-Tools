#!/usr/bin/env python3
"""Fail when examples/showcase pieces and tests/smoke/catalog.json disagree.

Every examples/<name>/ and showcase/<name>/ directory must be the target of at
least one catalog row (the row's ``script`` path names the directory), and every
row that points into examples/ or showcase/ must name a directory that exists.
An empty catalog fails. Rows for harness code (tests/smoke/...) are allowed.

    python tests/check_smoke_catalog.py [--root PATH]

No Blender needed; runs in Validate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Directories that intentionally have no smoke row. Keep empty unless justified.
EXCLUDED: set[str] = set()


def check(root: Path) -> list[str]:
    catalog = json.loads((root / "tests/smoke/catalog.json").read_text(encoding="utf-8"))
    if not catalog:
        return ["tests/smoke/catalog.json is empty"]

    covered: set[str] = set()
    errors: list[str] = []
    for row in catalog:
        parts = Path(row["script"]).parts
        if len(parts) >= 2 and parts[0] in ("examples", "showcase"):
            key = f"{parts[0]}/{parts[1]}"
            covered.add(key)
            if not (root / key).is_dir():
                errors.append(f"catalog row {row['name']!r} points at missing directory {key}")

    for top in ("examples", "showcase"):
        for d in sorted((root / top).iterdir()):
            if not d.is_dir() or d.name == "__pycache__":
                continue
            key = f"{top}/{d.name}"
            if key not in covered and key not in EXCLUDED:
                errors.append(f"{key} has no row in tests/smoke/catalog.json (it would never run)")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    root = Path(ap.parse_args().root)
    errors = check(root)
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if errors:
        return 1
    print("smoke catalog covers every example and showcase directory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
