#!/usr/bin/env python3
"""Measure how far each committed gallery hero is from what its script renders.

For every entry in ``examples/gallery.json`` and ``showcase/gallery.json``,
render the entry's README ``--output`` command to a lossless PNG with the
given Blender binary, then compare it with the committed
``docs/gallery/assets/<name>-hero.webp``:

* ``mean_abs`` - mean absolute per-channel difference, 0..1
* ``gt2pct``   - share of pixels whose mean channel difference exceeds 2%
* ``vs_q90``   - ``gt2pct`` against the fresh render re-encoded as webp q90
* ``luma``     - mean luminance (Rec. 709) of the committed and fresh image

This is the method from issue #200, with one correction. Renders are
deterministic (a re-render is pixel-identical), but the webp encode floor is
not a constant: re-encoding a frame at q90 alone moves 0.1-4% of pixels past
2%, depending on the image. ``gt2pct`` against the PNG therefore mixes drift
with encode noise. The verdict uses ``vs_q90``, which cancels the encode: on
the 2026-09-23 sweep every matching hero scored <= 1.8% and every drifted one
>= 3.8%, hence DRIFT_THRESHOLD.

Authoring tool, not a CI step: one full render per entry. Requires Pillow
and numpy on the host Python (not Blender's).

Usage:
    python scripts/measure_hero_drift.py --blender PATH [--only NAME ...]
        [--out DIR] [--json FILE]

Exit codes: 0 measured (drift is reported, not judged), 2 usage, 3 a render
failed for at least one entry.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
SOURCES = ("examples/gallery.json", "showcase/gallery.json")
DRIFT_THRESHOLD = 0.025  # vs_q90 share; the gap on the full sweep is 1.8% .. 3.8%

_RUN_LINE = re.compile(r"blender\s+--background\s+--python\s+\S+\.py\s+--\s+(.*--output\s.*)$")


def entries() -> list[dict]:
    out = []
    for rel in SOURCES:
        data = json.loads((REPO / rel).read_text(encoding="utf-8"))
        items = next(v for v in data.values() if isinstance(v, list))
        out.extend(items)
    return out


def render_args(entry: dict, png: Path) -> list[str] | None:
    """The README's documented ``--output`` invocation, retargeted at *png*.

    Returns None when the README documents no render command. Only the
    output path is replaced; every other documented flag (``--engine``,
    ``--samples`` ...) is kept, because the hero was rendered with them.
    """
    readme = REPO / entry["dir"] / "README.md"
    if not readme.is_file():
        return None
    for line in readme.read_text(encoding="utf-8").splitlines():
        m = _RUN_LINE.search(line.strip())
        if not m:
            continue
        args = shlex.split(m.group(1))
        i = args.index("--output")
        args[i + 1] = str(png)
        return args
    return None


def load(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0


def luma(a: np.ndarray) -> float:
    return float((a @ np.array([0.2126, 0.7152, 0.0722])).mean())


def gt2pct(a: np.ndarray, b: np.ndarray) -> float:
    # Mean over the channels, not any channel: the definition #200 used,
    # which reproduces its 22.45% (shipping-crate) and 0.50% (crate-stack).
    return round(float((np.abs(a - b).mean(axis=2) > 0.02).mean()), 5)


def webp_q90(path: Path) -> np.ndarray:
    buf = io.BytesIO()
    Image.open(path).convert("RGB").save(buf, "WEBP", quality=90)
    return np.asarray(Image.open(buf).convert("RGB"), dtype=np.float64) / 255.0


def compare(committed: Path, fresh: Path) -> dict:
    a, b = load(committed), load(fresh)
    if a.shape != b.shape:
        return {"shape_committed": a.shape[:2], "shape_fresh": b.shape[:2]}
    return {
        "mean_abs": round(float(np.abs(a - b).mean()), 5),
        "gt2pct": gt2pct(a, b),
        "vs_q90": gt2pct(a, webp_q90(fresh)),
        "luma_committed": round(luma(a), 5),
        "luma_fresh": round(luma(b), 5),
        "bytes_committed": committed.stat().st_size,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--blender", required=True, help="Blender binary to render with")
    p.add_argument("--only", action="append", help="measure only this entry (repeatable)")
    p.add_argument("--out", default=str(REPO / ".scratch" / "hero-drift"),
                   help="directory for fresh PNG renders (default: .scratch/hero-drift)")
    p.add_argument("--json", default=None, help="also write the results as JSON here")
    args = p.parse_args(argv)

    blender = str(Path(args.blender).resolve())
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    version = subprocess.run([blender, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout.splitlines()[0]
    print(f"# renderer: {blender}\n# version: {version}", flush=True)
    print(f"{'name':32} {'mean_abs':>9} {'gt2pct':>8} {'vs_q90':>8} {'luma c/f':>17} {'secs':>6}  verdict",
          flush=True)

    results, failed = [], []
    for e in entries():
        name = e["name"]
        if args.only and name not in args.only:
            continue
        png = out_dir / f"{name}.png"
        cmd = render_args(e, png)
        if cmd is None:
            print(f"{name:32} no --output command in README", flush=True)
            failed.append(name)
            continue
        script = next((REPO / e["dir"]).glob("*.py"))
        if png.exists():
            png.unlink()
        t0 = time.time()
        proc = subprocess.run(
            [blender, "--background", "--factory-startup", "--python", str(script), "--", *cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO,
        )
        secs = time.time() - t0
        if proc.returncode != 0 or not png.is_file():
            print(f"{name:32} render failed: exit {proc.returncode}", flush=True)
            failed.append(name)
            continue
        row = {"name": name, "args": cmd, "secs": round(secs, 1),
               **compare(REPO / e["hero"], png)}
        results.append(row)
        if "mean_abs" not in row:
            print(f"{name:32} size mismatch {row}", flush=True)
            continue
        verdict = "matches" if row["vs_q90"] <= DRIFT_THRESHOLD else "DRIFTED"
        row["verdict"] = verdict
        print(f"{name:32} {row['mean_abs']:9.5f} {row['gt2pct']:8.2%} {row['vs_q90']:8.2%} "
              f"{row['luma_committed']:.4f}/{row['luma_fresh']:.4f} {secs:6.1f}  {verdict}",
              flush=True)

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"renderer": version, "results": results, "failed": failed}, indent=2),
            encoding="utf-8")
    drifted = [r["name"] for r in results if r.get("verdict") == "DRIFTED"]
    print(f"\n# {len(results)} measured, {len(drifted)} drifted, {len(failed)} failed")
    return 3 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
