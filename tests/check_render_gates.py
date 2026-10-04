#!/usr/bin/env python3
"""Every gallery still must pass through the shared render gates.

CLAUDE.md: framing "is measured, not eyeballed" — every render path that
produces a gallery still calls examples/gallery_framing.py (exit 10) before
writing it. This lint makes that structural: each directory listed in
examples/gallery.json or showcase/gallery.json must have a script that
imports gallery_framing and calls check_framing or measure_framing_deviation
(bleed compositions assert their own cap). Static only; the call itself
running is proven by rendering the hero.

    python tests/check_render_gates.py      (exit 0 ok, 1 on a missing gate)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IMPORT_FRAMING = re.compile(r"^\s*import gallery_framing\b", re.M)
CALL_FRAMING = re.compile(r"gallery_framing\.(check_framing|measure_framing_deviation)\(")


def gallery_dirs() -> list[str]:
    dirs = []
    ex = json.loads((ROOT / "examples" / "gallery.json").read_text(encoding="utf-8"))
    dirs += [e["dir"] for e in (ex["examples"] if isinstance(ex, dict) else ex)]
    sc = json.loads((ROOT / "showcase" / "gallery.json").read_text(encoding="utf-8"))
    dirs += [p["dir"] for p in sc["pieces"]]
    return dirs


def script_text(d: str) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / d).glob("*.py")))


def check() -> list[str]:
    errors = []
    for d in gallery_dirs():
        src = script_text(d)
        if not src:
            errors.append(f"{d}: listed in a gallery.json but has no script")
            continue
        if not (IMPORT_FRAMING.search(src) and CALL_FRAMING.search(src)):
            errors.append(f"{d}: gallery still is not gated by gallery_framing "
                          f"(import it and call check_framing before writing the still)")
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if errors:
        return 1
    print(f"render gates: {len(gallery_dirs())} gallery entries gate framing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
