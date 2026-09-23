#!/usr/bin/env python3
"""Build a gallery contact sheet and print the numbers its verdict reports.

Composites a candidate hero beside the pinned calibration set (canonical
membership: CLAUDE.md, Quality Gates) in the committed format: four 640x360
tiles, candidate first, captioned, on the dark sheet background, written to
``docs/gallery/contact-sheets/<name>-contact-sheet.webp``.

It also prints what the gate's verdict needs measured: mean luminance
(Rec. 709) of each tile, the stage (mean luminance of the frame border, where
the backdrop is), the wedge warmth (red minus blue over the brightest tenth
of the lower half, where the warm floor pool sits), and mean saturation. The
verdict itself - "is this sortable as the odd one out?" - stays a judgment
made by looking at the sheet; this only makes the numbers repeatable.

Authoring tool: host Python with Pillow and numpy.

Usage:
    python scripts/contact_sheet.py NAME [NAME ...]

Exit codes: 0 written, 2 usage.
"""
from __future__ import annotations

import sys

import numpy as np
from PIL import Image, ImageDraw

from measure_hero_drift import REPO, entries

CALIBRATION = ("armature-bend", "damped-track-aim", "bmesh-gear")
TILE = (640, 360)
GAP, CAPTION = 10, 32
BG = (22, 23, 26)
TEXT = (150, 152, 160)
OUT = REPO / "docs" / "gallery" / "contact-sheets"


def metrics(im: Image.Image) -> dict:
    a = np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0
    luma = a @ np.array([0.2126, 0.7152, 0.0722])
    h, w = luma.shape
    b = max(1, h // 12)
    border = np.concatenate([luma[:b].ravel(), luma[-b:].ravel(),
                             luma[:, :b].ravel(), luma[:, -b:].ravel()])
    lower = a[h // 2:].reshape(-1, 3)
    lower_l = luma[h // 2:].ravel()
    hot = lower[lower_l >= np.quantile(lower_l, 0.9)]
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    return {
        "luma": float(luma.mean()),
        "stage": float(border.mean()),
        "warmth": float((hot[:, 0] - hot[:, 2]).mean()),
        "sat": float(sat.mean()),
    }


def build(name: str, heroes: dict[str, str]) -> list[tuple[str, dict]]:
    names = [name] + [c for c in CALIBRATION if c != name]
    tw, th = TILE
    sheet = Image.new("RGB", (GAP + len(names) * (tw + GAP), GAP + th + CAPTION), BG)
    draw = ImageDraw.Draw(sheet)
    rows = []
    for i, n in enumerate(names):
        im = Image.open(REPO / heroes[n]).convert("RGB")
        x = GAP + i * (tw + GAP)
        sheet.paste(im.resize(TILE, Image.LANCZOS), (x, GAP))
        label = f"{n} <- candidate" if i == 0 else f"{n}  (calibration)"
        draw.text((x + 4, GAP + th + 10), label, fill=TEXT)
        rows.append((label, metrics(im)))
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT / f"{name}-contact-sheet.webp", "WEBP", quality=90)
    return rows


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__.split("Usage:")[1].strip(), file=sys.stderr)
        return 2
    heroes = {e["name"]: e["hero"] for e in entries()}
    unknown = [n for n in argv if n not in heroes]
    if unknown:
        print(f"unknown entries: {', '.join(unknown)}", file=sys.stderr)
        return 2
    for name in argv:
        rows = build(name, heroes)
        print(f"\n{name}  -> docs/gallery/contact-sheets/{name}-contact-sheet.webp")
        print(f"  {'tile':34} {'luma':>6} {'stage':>6} {'warmth':>7} {'sat':>6}")
        for label, m in rows:
            print(f"  {label:34} {m['luma']:6.4f} {m['stage']:6.4f} "
                  f"{m['warmth']:+7.4f} {m['sat']:6.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
