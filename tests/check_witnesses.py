#!/usr/bin/env python3
"""Showcase witness callouts must quote the same triangle count as the README.

Each showcase gallery page carries a "witnesses" callout (`witnessesFix` in
showcase/gallery.json) that opens "Recomputed: N tris, ...". It is written by
hand, so a remodel that updates the README's measured budgets can leave the
published callout quoting the old model: nine pieces had drifted (one by
2.3x) before this check existed.

For every piece whose witness starts with a triangle count, the count must
equal every measured column of the README's "Base triangles" budget row.
The README rows are themselves recomputed by the script on each version, so
this pins the published claim to the measured one.

    python tests/check_witnesses.py      (exit 0 ok, 1 on a mismatch)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIT = re.compile(r"Recomputed: ([\d,]+) tris")
ROW = re.compile(r"^\| Base tri\w* \|[^|]*\|([^|]+)\|", re.M)


def check() -> list[str]:
    data = json.loads((ROOT / "showcase" / "gallery.json").read_text(encoding="utf-8"))
    errors = []
    for piece in data["pieces"]:
        m = WIT.search(piece.get("witnessesFix", ""))
        if not m:
            continue
        name = piece["name"]
        readme = (ROOT / "showcase" / name / "README.md").read_text(encoding="utf-8")
        row = ROW.search(readme)
        if not row:
            errors.append(f"{name}: witness quotes a triangle count but the README has no "
                          f"'Base triangles' budget row to check it against")
            continue
        measured = {int(x.replace(",", "")) for x in re.findall(r"[\d,]+", row.group(1))}
        claimed = int(m.group(1).replace(",", ""))
        if measured != {claimed}:
            errors.append(f"{name}: witness says {claimed} tris, README measures "
                          f"{sorted(measured)}; update showcase/gallery.json witnessesFix")
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if errors:
        return 1
    print("showcase witnesses: every quoted triangle count matches its README")
    return 0


if __name__ == "__main__":
    sys.exit(main())
