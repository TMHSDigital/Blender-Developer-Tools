#!/usr/bin/env python3
"""Build the asset-sheet gate composite for one asset: candidate beside the references.

The asset-sheet gate (CLAUDE.md § Quality Gates for Example Runs) renders the
hero asset alone — neutral three-quarter view, plain studio lighting, no
staging, no labels — beside the pinned asset-quality reference set rendered
the same way, and asks one question: is the candidate identifiable as the
least-designed object in the lineup?

The reference set is read from CLAUDE.md, its canonical home, so this script
never disagrees with the gate it serves. Panel layout is 3x2 at 640x360:
candidate top-left, then the references in CLAUDE.md order.

For each name the Blender side (``scripts/asset_sheet_panel.py``) stages the
entry through the README's documented ``--output`` command, keeps only the
mesh objects matched by ``SELECT`` below, and re-renders them on a grey
sweep. Before this file the panel renderer lived in uncommitted scratch
scripts, so a sheet could not be reproduced (the same gap #200 closed for
heroes).

Authoring tool, not CI: host Python with Pillow; one full staging render
per panel.

Usage:
    python scripts/asset_sheet.py --blender PATH NAME [--out PATH] [--panels DIR]

Writes ``docs/gallery/asset-sheets/NAME.webp`` unless ``--out`` is given.
``--panels`` keeps the per-asset PNGs (and reuses any already there).

Exit codes: 0 written, 2 usage, 3 a panel failed.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from measure_hero_drift import REPO, entries, render_args

PANEL = (640, 360)
GUTTER = 8
QUALITY = 88

# Mesh objects that make up each entry's hero asset: (include, exclude)
# regexes on object names. Comparison props, placards and stage are left out
# by construction. A new asset-type entry adds its row here.
SELECT = {
    "collision-hull-proxy": (r"^(Body|Nut|PumperCap|Lug\d|SideCap\d)$", None),
    "custom-normals-shade": (r"_byangle$", None),
    "vertex-weight-limit": (r"^MechArm$", None),
    "lod-decimate-chain": (r"^Rocket$", None),
    "modular-kit-snap": (r"^Kit\.CorridorSeg\.", r"\.0\d\d$"),
    "lightmap-uv-channel": (r"^Cart\.", None),
    "socket-attach-points": (r"^Drone\.Survey\.", None),
    "vertex-color-ao": (r"^Well\.Stone\.", None),
    "wooden-yoke": (r"^YokeLow$", None),
    "apothecary-shelf": (r"^ShelfLow$", None),
    "brazier": (r"^BrazierLow$", None),
    "grain-sacks": (r"^SacksLow$", None),
    "rope-bridge": (r"^BridgeLow$", None),
    "wheelbarrow": (r"^BarrowLow$", None),
    "triangulate-tangents": (r"^Buckler(\.Rivets)?$", None),
    "car-mirror-symmetry": (r"^(CarBody|Wheel(Front|Rear)|Headlamp|Taillamp|Grille"
                            r"|DoorMirror|DoorHandle(Front|Rear))$", None),
    "export-preset-axis": (r"^RadioMast\.Unity$", None),
    "prop-origin-transform": (r"^(Pedestal|Conduit)\.Keep$", None),
    "gltf-skin-roundtrip": (r"^ScorpionAuthored$", None),
    "degenerate-bevel-weld": (r"^CaseSafe\.", None),
    "mesh-hygiene-audit": (r"^Valve\.", None),
    "gn-modifier-inputs": (r"^SpiralStair\.H3$", None),
}

_REF_LINE = re.compile(r"Asset-sheet gate.*?reference set — currently (.+?) — rendered", re.S)


def reference_set() -> list[str]:
    """The pinned reference set, parsed from its canonical home in CLAUDE.md."""
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    m = _REF_LINE.search(text)
    if not m:
        raise SystemExit("could not find the asset-sheet reference set in CLAUDE.md")
    return re.findall(r"`([a-z0-9-]+)`", m.group(1))


def render_panel(blender: str, entry: dict, png: Path) -> bool:
    inc, exc = SELECT[entry["name"]]
    with tempfile.TemporaryDirectory() as tmp:
        cmd = render_args(entry, Path(tmp) / "stage.png")
        if cmd is None:
            print(f"{entry['name']}: no --output command in README", flush=True)
            return False
        script = next((REPO / entry["dir"]).glob("*.py"))
        env = dict(os.environ, BDT_SHEET_SCRIPT=str(script), BDT_SHEET_SELECT=inc,
                   BDT_SHEET_EXCLUDE=exc or "", BDT_SHEET_OUT=str(png))
        proc = subprocess.run(
            [blender, "--background", "--factory-startup", "--python",
             str(REPO / "scripts" / "asset_sheet_panel.py"), "--", *cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=REPO, env=env,
        )
    for line in proc.stdout.splitlines():
        if line.startswith("sheet:"):
            print(f"{entry['name']}: {line}", flush=True)
    if proc.returncode != 0 or not png.is_file():
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        print(f"{entry['name']}: panel failed, exit {proc.returncode}: {' | '.join(tail)}",
              flush=True)
        return False
    return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--blender", required=True, help="Blender binary to render with")
    p.add_argument("name", help="candidate entry (examples/ or showcase/ gallery name)")
    p.add_argument("--out", help="composite path (default docs/gallery/asset-sheets/NAME.webp)")
    p.add_argument("--panels", help="directory to keep and reuse per-asset panel PNGs")
    args = p.parse_args(argv)

    by_name = {e["name"]: e for e in entries()}
    refs = reference_set()
    lineup = [args.name] + [r for r in refs if r != args.name]
    missing = [n for n in lineup if n not in by_name or n not in SELECT]
    if missing:
        print(f"no gallery entry or SELECT row for: {', '.join(missing)}", file=sys.stderr)
        return 2

    blender = str(Path(args.blender).resolve())
    version = subprocess.run([blender, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout.splitlines()[0]
    print(f"# renderer: {blender}\n# version: {version}\n# references: {', '.join(refs)}",
          flush=True)

    keep = Path(args.panels) if args.panels else None
    with tempfile.TemporaryDirectory() as tmp:
        pdir = keep or Path(tmp)
        pdir.mkdir(parents=True, exist_ok=True)
        panels = []
        for n in lineup:
            png = pdir / f"{n}.png"
            # the candidate is always re-rendered; references may be reused
            if not (keep and png.is_file() and n != args.name):
                if not render_panel(blender, by_name[n], png):
                    return 3
            panels.append(Image.open(png).convert("RGB").resize(PANEL, Image.LANCZOS))

        cols = 3
        rows = -(-len(panels) // cols)
        sheet = Image.new("RGB", (PANEL[0] * cols + GUTTER * (cols - 1),
                                  PANEL[1] * rows + GUTTER * (rows - 1)), (18, 18, 20))
        for i, im in enumerate(panels):
            sheet.paste(im, ((i % cols) * (PANEL[0] + GUTTER), (i // cols) * (PANEL[1] + GUTTER)))
        out = Path(args.out) if args.out else REPO / "docs/gallery/asset-sheets" / f"{args.name}.webp"
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out, "WEBP", quality=QUALITY)
    print(f"wrote {out.relative_to(REPO) if out.is_relative_to(REPO) else out} "
          f"({out.stat().st_size} B): {' | '.join(lineup)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
