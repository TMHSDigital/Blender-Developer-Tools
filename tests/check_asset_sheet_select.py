#!/usr/bin/env python3
"""Every showcase piece and asset-sheet reference has a SELECT row (#367).

scripts/asset_sheet.py renders a candidate's hero asset by the regexes in its
SELECT table and refuses any name without a row, so a piece added without one
leaves its committed asset sheet impossible to regenerate. butter-churn shipped
that way. This reads SELECT with ast (no Pillow needed) and requires a row for:

- every piece in showcase/gallery.json, and
- every name in the asset-quality reference set (scripts/gallery_refs.py, the
  same tuple asset_sheet.reference_set() returns).

    python tests/check_asset_sheet_select.py      (exit 0 ok, 1 on a gap)
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def select_keys(root: Path) -> set[str]:
    tree = ast.parse((root / "scripts" / "asset_sheet.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SELECT" for t in node.targets):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    raise SystemExit("scripts/asset_sheet.py has no SELECT table")


def reference_set(root: Path) -> list[str]:
    sys.path.insert(0, str(root / "scripts"))
    from gallery_refs import ASSET_SET
    return list(ASSET_SET)


def check(root: Path = ROOT) -> list[str]:
    keys = select_keys(root)
    pieces = [p["name"] for p in json.loads(
        (root / "showcase" / "gallery.json").read_text(encoding="utf-8"))["pieces"]]
    refs = reference_set(root)
    errors = [f"showcase piece {n!r} has no SELECT row in scripts/asset_sheet.py"
              for n in pieces if n not in keys]
    errors += [f"asset-sheet reference {n!r} (scripts/gallery_refs.py) has no SELECT row"
               for n in refs if n not in keys]
    if not refs:
        errors.append("scripts/gallery_refs.py ASSET_SET is empty")
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if not errors:
        print("asset_sheet.py SELECT covers every showcase piece and reference")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
