#!/usr/bin/env python3
"""Every showcase piece and asset-sheet reference has a SELECT row (#367).

scripts/asset_sheet.py renders a candidate's hero asset by the regexes in its
SELECT table and refuses any name without a row, so a piece added without one
leaves its committed asset sheet impossible to regenerate. butter-churn shipped
that way. This reads SELECT with ast (no Pillow needed) and requires a row for:

- every piece in showcase/gallery.json, and
- every name in the CLAUDE.md asset-quality reference set (read the same way
  asset_sheet.reference_set() reads it).

    python tests/check_asset_sheet_select.py      (exit 0 ok, 1 on a gap)
"""
from __future__ import annotations

import ast
import json
import re
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
    src = (root / "scripts" / "asset_sheet.py").read_text(encoding="utf-8")
    pattern = re.search(r'_REF_LINE = re\.compile\(r"(.+?)", re\.S\)', src).group(1)
    m = re.search(pattern, (root / "CLAUDE.md").read_text(encoding="utf-8"), re.S)
    return re.findall(r"`([a-z0-9-]+)`", m.group(1)) if m else []


def check(root: Path = ROOT) -> list[str]:
    keys = select_keys(root)
    pieces = [p["name"] for p in json.loads(
        (root / "showcase" / "gallery.json").read_text(encoding="utf-8"))["pieces"]]
    refs = reference_set(root)
    errors = [f"showcase piece {n!r} has no SELECT row in scripts/asset_sheet.py"
              for n in pieces if n not in keys]
    errors += [f"asset-sheet reference {n!r} (CLAUDE.md) has no SELECT row"
               for n in refs if n not in keys]
    if not refs:
        errors.append("could not read the asset-sheet reference set from CLAUDE.md")
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
