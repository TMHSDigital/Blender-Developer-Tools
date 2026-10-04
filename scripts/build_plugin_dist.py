#!/usr/bin/env python3
"""Assemble the slim Claude Code plugin tree published on the `plugin-dist` branch.

The repo root is ~30 MB of gallery renders, showcase props and history; the
plugin needs ~1 MB of it. This copies only what the plugin uses into --out,
as a self-contained marketplace (its marketplace.json points at "./"):

    skills/  claude/  rules/  snippets/  templates/  LICENSE files
    .claude-plugin/plugin.json + marketplace.json, and a short README

    python scripts/build_plugin_dist.py --out DIR     # build
    python scripts/build_plugin_dist.py --check       # build to a temp dir, verify, report size

release.yml force-pushes the built tree as a single orphan commit to
`plugin-dist` on every release, so the branch never accumulates history.
Users add it with `/plugin marketplace add TMHSDigital/Blender-Developer-Tools@plugin-dist`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = ("skills", "claude", "rules", "snippets", "templates")
FILES = ("LICENSE", ".claude-plugin/plugin.json")
MAX_BYTES = 2_000_000
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")

DIST_README = """# Blender Developer Tools (Claude Code plugin build)

Generated from https://github.com/TMHSDigital/Blender-Developer-Tools by
`scripts/build_plugin_dist.py` on every release. Do not edit this branch; it
is force-pushed. It carries only what the plugin loads: skills, the
`blender-rules` skill generated from `rules/`, snippets, templates and licenses.
Examples, the showcase and the gallery live on `main`.

```text
/plugin marketplace add TMHSDigital/Blender-Developer-Tools@plugin-dist
/plugin install blender-developer-tools@blender-developer-tools
```
"""


def build(out: Path) -> int:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for d in DIRS:
        shutil.copytree(ROOT / d, out / d, ignore=IGNORE)
    for f in FILES:
        (out / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, out / f)
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    for entry in market["plugins"]:
        entry["source"] = "./"
    (out / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(market, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out / "README.md").write_text(DIST_README, encoding="utf-8", newline="\n")
    return sum(p.stat().st_size for p in out.rglob("*") if p.is_file())


def verify(out: Path, size: int) -> list[str]:
    errors = []
    plugin = json.loads((out / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    skill_dirs = [out / "skills"] + [out / s for s in plugin.get("skills", [])]
    for d in skill_dirs:
        if not any(d.glob("*/SKILL.md")):
            errors.append(f"{d.relative_to(out)} has no SKILL.md")
    if not (out / "claude" / "skills" / "blender-rules" / "SKILL.md").is_file():
        errors.append("blender-rules skill missing")
    if size > MAX_BYTES:
        errors.append(f"dist is {size} bytes, over the {MAX_BYTES} budget")
    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if not a.out and not a.check:
        ap.error("give --out DIR or --check")
    with tempfile.TemporaryDirectory() as td:
        out = a.out or Path(td) / "dist"
        size = build(out)
        errors = verify(out, size)
        n = sum(1 for p in out.rglob("*") if p.is_file())
        for e in errors:
            print(f"::error::{e}", file=sys.stderr)
        print(f"plugin dist: {n} files, {size / 1e6:.2f} MB" + ("" if errors else " ok"))
        return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
