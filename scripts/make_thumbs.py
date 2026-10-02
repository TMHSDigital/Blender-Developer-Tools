#!/usr/bin/env python3
"""Write the 640px card variant of every gallery hero.

For each entry in ``examples/gallery.json`` / ``showcase/gallery.json`` with a
hero at ``docs/gallery/assets/<name>-hero.webp`` (1280x720), write
``docs/gallery/assets/<name>-hero-640.webp`` (640x360, Lanczos). Gallery cards
and the landing grids list both in a ``srcset``, so a compact card or a 1x
screen fetches a quarter of the pixels. ``scripts/build_gallery.py`` fails when
a variant is missing.

``scripts/render_hero.py`` writes the variant alongside every hero it renders;
this script backfills, and is the fix when the gallery build reports one
missing. By default it only writes variants that do not exist yet, so a run
never churns committed files; ``--all`` rewrites every one (after a hero was
replaced by hand, say).

Authoring tool, not CI: host Python with Pillow.

Usage:
    python scripts/make_thumbs.py [--all] [--only NAME ...]

Exit codes: 0 done, 2 unknown entry or missing hero.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from measure_hero_drift import REPO, entries

THUMB_SIZE = (640, 360)
QUALITY = 85


def thumb_for(hero: Path) -> Path:
    return hero.with_name(hero.stem + "-640" + hero.suffix)


def write_thumb(hero: Path) -> Path:
    """Write *hero*'s 640 variant and return its path. Shared with render_hero."""
    out = thumb_for(hero)
    with Image.open(hero) as im:
        im.convert("RGB").resize(THUMB_SIZE, Image.LANCZOS).save(out, "WEBP", quality=QUALITY)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--all", action="store_true", help="rewrite variants that already exist")
    p.add_argument("--only", action="append", help="entry to process (repeatable)")
    args = p.parse_args(argv)

    todo = entries()
    if args.only:
        known = {e["name"] for e in todo}
        unknown = [n for n in args.only if n not in known]
        if unknown:
            print(f"unknown entries: {', '.join(unknown)}", file=sys.stderr)
            return 2
        todo = [e for e in todo if e["name"] in args.only]

    wrote = skipped = 0
    for e in todo:
        hero = REPO / e["hero"]
        if not hero.is_file():
            print(f"{e['name']}: hero missing: {e['hero']}", file=sys.stderr)
            return 2
        if thumb_for(hero).is_file() and not args.all:
            skipped += 1
            continue
        out = write_thumb(hero)
        wrote += 1
        print(f"{e['name']}: wrote {out.relative_to(REPO).as_posix()} ({out.stat().st_size} B)")
    print(f"{wrote} written, {skipped} already present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
