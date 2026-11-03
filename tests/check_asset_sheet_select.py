#!/usr/bin/env python3
"""Every showcase piece and asset-sheet reference carries an assetSelect (#367, #530).

scripts/asset_sheet.py renders a candidate's hero asset by the regexes in its
gallery entry's ``assetSelect`` ({"include": ..., "exclude"?: ...}) and refuses
an entry without one, so a piece added without it leaves its committed asset
sheet impossible to regenerate. butter-churn shipped that way when the regexes
lived in a SELECT table in the script. This requires a compilable assetSelect
on:

- every piece in showcase/gallery.json, and
- every name in the asset-quality reference set (scripts/gallery_refs.py, the
  same tuple asset_sheet.reference_set() returns).

    python tests/check_asset_sheet_select.py      (exit 0 ok, 1 on a gap)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ("examples/gallery.json", "showcase/gallery.json")


def entries(root: Path) -> dict[str, dict]:
    out = {}
    for rel in SOURCES:
        data = json.loads((root / rel).read_text(encoding="utf-8"))
        for e in next(v for v in data.values() if isinstance(v, list)):
            out[e["name"]] = e
    return out


def reference_set(root: Path) -> list[str]:
    sys.path.insert(0, str(root / "scripts"))
    from gallery_refs import ASSET_SET
    return list(ASSET_SET)


def select_errors(name: str, entry: dict | None) -> list[str]:
    if entry is None:
        return [f"{name!r} has no gallery entry"]
    sel = entry.get("assetSelect")
    if not isinstance(sel, dict) or not isinstance(sel.get("include"), str):
        return [f"{name!r} has no assetSelect.include in its gallery entry"]
    errors = []
    if set(sel) - {"include", "exclude"}:
        errors.append(f"{name!r} assetSelect has unknown keys {sorted(set(sel) - {'include', 'exclude'})}")
    for key in ("include", "exclude"):
        pattern = sel.get(key)
        if pattern is None:
            continue
        try:
            re.compile(pattern)
        except (re.error, TypeError) as exc:
            errors.append(f"{name!r} assetSelect.{key} is not a regex: {exc}")
    return errors


def check(root: Path = ROOT) -> list[str]:
    by_name = entries(root)
    pieces = [p["name"] for p in json.loads(
        (root / "showcase" / "gallery.json").read_text(encoding="utf-8"))["pieces"]]
    refs = reference_set(root)
    errors = []
    for n in pieces:
        errors += select_errors(n, by_name.get(n))
    for n in refs:
        errors += [f"asset-sheet reference: {e}" for e in select_errors(n, by_name.get(n))]
    if not refs:
        errors.append("scripts/gallery_refs.py ASSET_SET is empty")
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if not errors:
        print("every showcase piece and asset-sheet reference has an assetSelect")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
