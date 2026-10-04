#!/usr/bin/env python3
"""Stage the public Pages tree: copy docs/ and drop what is not published.

    python scripts/site/stage_public.py --src docs --out _site

Everything stays in the repo; only the Pages artifact shrinks. The internal
docs (docs/*.md, gallery/DESIGN_NOTES.md) and the unlinked contact/asset sheets
are left out. pages.yml deploys this tree and validate-site checks it, and
tests/check_site_links.py runs against it, so a published link to a stripped
file fails CI instead of 404ing in production. Keep EXCLUDE the single list.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Paths relative to --src; top-level *.md files are dropped too (see stage()).
EXCLUDE_DIRS = ("gallery/contact-sheets", "gallery/asset-sheets")
EXCLUDE_FILES = ("gallery/DESIGN_NOTES.md",)


def stage(src: Path, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)
    for d in EXCLUDE_DIRS:
        shutil.rmtree(out / d, ignore_errors=True)
    for f in EXCLUDE_FILES:
        (out / f).unlink(missing_ok=True)
    for md in out.glob("*.md"):
        md.unlink()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=Path("docs"))
    ap.add_argument("--out", type=Path, default=Path("_site"))
    a = ap.parse_args(argv)
    if not (a.src / "index.html").is_file():
        print(f"ERROR: {a.src / 'index.html'} missing; build the site first", file=sys.stderr)
        return 2
    stage(a.src, a.out)
    print(f"staged {a.src} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
