#!/usr/bin/env python3
"""Every committed contact sheet shows the hero that ships now.

A contact sheet's first tile is the candidate's hero webp, resized to 640x360
(scripts/contact_sheet.py). When a quality pass re-renders a hero but not its
sheet, the committed gate evidence shows the old model (#487: four terrain
pieces after the 2026-10-08 passes). This compares that tile with the current
hero, resized the same way, by mean absolute difference per channel (0-255).
It is content-based, so it works in a shallow CI checkout.

Measured when written: current sheets 0.6-1.9 (webp re-encoding), the four
stale terrain sheets 4.0-34.2. The threshold sits between.

    python tests/check_contact_sheets.py

Exit codes: 0 all fresh, 1 a sheet is stale (regenerate it with
scripts/contact_sheet.py NAME and re-judge it).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from contact_sheet import GAP, OUT, TILE  # noqa: E402
from measure_hero_drift import entries  # noqa: E402

THRESHOLD = 3.0


def tile_diff(sheet: Path, hero: Path) -> float:
    tw, th = TILE
    tile = Image.open(sheet).convert("RGB").crop((GAP, GAP, GAP + tw, GAP + th))
    ref = Image.open(hero).convert("RGB").resize(TILE, Image.LANCZOS)
    return float(np.abs(np.asarray(tile, dtype=np.float64) - np.asarray(ref, dtype=np.float64)).mean())


def main() -> int:
    heroes = {e["name"]: ROOT / e["hero"] for e in entries()}
    errors, checked = [], 0
    for sheet in sorted(OUT.glob("*-contact-sheet.webp")):
        name = sheet.name[: -len("-contact-sheet.webp")]
        hero = heroes.get(name)
        if hero is None or not hero.is_file():
            continue  # a sheet for a retired or check-only entry: nothing ships to compare
        checked += 1
        d = tile_diff(sheet, hero)
        if d > THRESHOLD:
            errors.append(f"{sheet.relative_to(ROOT).as_posix()}: candidate tile differs from "
                          f"the current hero by {d:.2f} (> {THRESHOLD}); the hero changed after "
                          f"the sheet. Run python scripts/contact_sheet.py {name} and re-judge it")
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if errors:
        return 1
    print(f"contact sheets: {checked} match the hero that ships")
    return 0


if __name__ == "__main__":
    sys.exit(main())
