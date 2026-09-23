#!/usr/bin/env python3
"""Regenerate gallery hero and preview webps from the code, one committed path.

For each named entry in ``examples/gallery.json`` / ``showcase/gallery.json``:

1. render the README's documented ``--output`` command to a lossless PNG,
   keeping every other documented flag (``--engine cycles`` ...);
2. write the hero, ``docs/gallery/assets/<name>-hero.webp`` at 1280x720;
3. write the preview at the entry's ``preview`` path, 1200x675 (Lanczos).

Both are webp quality 90, the setting every showcase script uses when it
writes webp itself. Before this file the PNG -> webp step lived in uncommitted
scratch scripts, so nobody could regenerate a still and get the committed
result (#200). The script's own ``--output`` render path runs the framing
(exit 10) and asset-quality (exit 11) gates before it writes, so a
non-zero exit here leaves the committed files untouched.

Authoring tool, not CI: host Python with Pillow; one full render per entry.

Usage:
    python scripts/render_hero.py --blender PATH --only NAME [--only NAME ...]

Exit codes: 0 all written, 2 usage, 3 at least one render failed.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from measure_hero_drift import REPO, entries, render_args

HERO_SIZE = (1280, 720)
PREVIEW_SIZE = (1200, 675)
QUALITY = 90


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--blender", required=True, help="Blender binary to render with")
    p.add_argument("--only", action="append", required=True,
                   help="entry to regenerate (repeatable)")
    args = p.parse_args(argv)

    blender = str(Path(args.blender).resolve())
    version = subprocess.run([blender, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout.splitlines()[0]
    print(f"# renderer: {blender}\n# version: {version}", flush=True)

    by_name = {e["name"]: e for e in entries()}
    unknown = [n for n in args.only if n not in by_name]
    if unknown:
        print(f"unknown entries: {', '.join(unknown)}", file=sys.stderr)
        return 2

    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in args.only:
            e = by_name[name]
            png = Path(tmp) / f"{name}.png"
            cmd = render_args(e, png)
            if cmd is None:
                print(f"{name}: no --output command in README", flush=True)
                failed.append(name)
                continue
            script = next((REPO / e["dir"]).glob("*.py"))
            proc = subprocess.run(
                [blender, "--background", "--factory-startup", "--python", str(script),
                 "--", *cmd],
                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO,
            )
            if proc.returncode != 0 or not png.is_file():
                tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
                print(f"{name}: render failed, exit {proc.returncode}: {' | '.join(tail)}",
                      flush=True)
                failed.append(name)
                continue
            im = Image.open(png).convert("RGB")
            if im.size != HERO_SIZE:
                print(f"{name}: render is {im.size[0]}x{im.size[1]}, expected "
                      f"{HERO_SIZE[0]}x{HERO_SIZE[1]}", flush=True)
                failed.append(name)
                continue
            hero, preview = REPO / e["hero"], REPO / e["preview"]
            im.save(hero, "WEBP", quality=QUALITY)
            im.resize(PREVIEW_SIZE, Image.LANCZOS).save(preview, "WEBP", quality=QUALITY)
            print(f"{name}: wrote {e['hero']} ({hero.stat().st_size} B) and "
                  f"{e['preview']} ({preview.stat().st_size} B)", flush=True)

    print(f"\n# {len(args.only) - len(failed)} regenerated, {len(failed)} failed")
    return 3 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
