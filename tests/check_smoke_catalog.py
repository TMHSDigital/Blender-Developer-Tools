#!/usr/bin/env python3
"""Fail when examples/showcase pieces and tests/smoke/catalog.json disagree.

Every examples/<name>/ and showcase/<name>/ directory must be the target of at
least one catalog row (the row's ``script`` path names the directory), and every
row that points into examples/ or showcase/ must name a directory that exists.
An empty catalog fails. Rows for harness code (tests/smoke/...) are allowed.

Schema: only the known row keys are accepted (a typo such as "falsifer" would
otherwise be ignored and the falsifier silently never run), and every row
carries at least one falsifier: {"args": [...], "expect_exit": N} with N not
0, 1, 2 (argparse usage) or 77, or {"args": [...], "expect_sidecar_fail": true} on a row that
declares expect_sidecar.

    python tests/check_smoke_catalog.py [--root PATH]

No Blender needed; runs in Validate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Directories that intentionally have no smoke row. Keep empty unless justified.
EXCLUDED: set[str] = set()

ROW_KEYS = {"name", "script", "args", "min_version", "expect_file",
            "expect_sidecar", "sidecar_contains", "falsifiers", "timeout"}
FALSIFIER_KEYS = {"args", "expect_exit", "expect_sidecar_fail", "min_version"}
# 2 is argparse's usage-error exit: an unknown or deleted flag also exits 2,
# so a falsifier expecting 2 passes even when its flag no longer exists.
FORBIDDEN_EXITS = {0, 1, 2, 77}


def check_schema(row: dict) -> list[str]:
    name = row.get("name", "?")
    errors = [f"catalog row {name!r}: unknown key {k!r}" for k in sorted(set(row) - ROW_KEYS)]
    for k in ("name", "script"):
        if not isinstance(row.get(k), str):
            errors.append(f"catalog row {name!r}: {k!r} missing or not a string")
    t = row.get("timeout")
    if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float)) or t <= 0):
        errors.append(f"catalog row {name!r}: timeout {t!r} must be a positive number of seconds")
    fz = row.get("falsifiers")
    if not isinstance(fz, list) or not fz:
        errors.append(f"catalog row {name!r} has no falsifiers: nothing proves its "
                      f"checks can still fail")
        return errors
    for i, f in enumerate(fz):
        where = f"catalog row {name!r} falsifier {i}"
        if not isinstance(f, dict):
            errors.append(f"{where}: not an object")
            continue
        errors += [f"{where}: unknown key {k!r}" for k in sorted(set(f) - FALSIFIER_KEYS)]
        args = f.get("args")
        if not (isinstance(args, list) and args and all(isinstance(a, str) for a in args)):
            errors.append(f"{where}: 'args' must be a non-empty list of strings")
        has_exit = "expect_exit" in f
        if has_exit == bool(f.get("expect_sidecar_fail")):
            errors.append(f"{where}: give exactly one of expect_exit or expect_sidecar_fail")
        elif has_exit:
            code = f["expect_exit"]
            if not isinstance(code, int) or isinstance(code, bool) or code in FORBIDDEN_EXITS:
                errors.append(f"{where}: expect_exit {code!r} must be an int other than 0, 1, 2, 77")
        elif not row.get("expect_sidecar"):
            errors.append(f"{where}: expect_sidecar_fail on a row with no expect_sidecar")
        mv = f.get("min_version")
        if mv is not None and not (isinstance(mv, str) and re.fullmatch(r"[0-9]+[.][0-9]+", mv)):
            errors.append(f"{where}: min_version {mv!r} must look like '5.2'")
    return errors


def check(root: Path) -> list[str]:
    catalog = json.loads((root / "tests/smoke/catalog.json").read_text(encoding="utf-8"))
    if not catalog:
        return ["tests/smoke/catalog.json is empty"]

    covered: set[str] = set()
    errors: list[str] = []
    for row in catalog:
        errors += check_schema(row)
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
