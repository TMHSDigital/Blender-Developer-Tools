#!/usr/bin/env python3
"""Assemble the slim Claude Code plugin tree published on the `plugin-dist` branch.

The repo root is ~30 MB of gallery renders, showcase props and history; the
plugin needs ~1 MB of it. This copies only what the plugin uses into --out,
as a self-contained marketplace (its marketplace.json points at "./"):

    skills/  claude/  rules/  snippets/  templates/  LICENSE files
    .claude-plugin/ and .cursor-plugin/ manifests, and a short README

    python scripts/build_plugin_dist.py --out DIR     # build (DIR must be absent or empty)
    python scripts/build_plugin_dist.py --out DIR --force  # replace a previous build in DIR
    python scripts/build_plugin_dist.py --check       # build to a temp dir, verify, report size
    python scripts/build_plugin_dist.py --fingerprint DIR   # content hash, versions ignored

release.yml force-pushes the built tree as a single orphan commit to
`plugin-dist` on every release, so the branch never accumulates history.
Users add it with `/plugin marketplace add TMHSDigital/Blender-Developer-Tools@plugin-dist`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = ("skills", "claude", "rules", "snippets", "templates")
# The Cursor manifest ships too, so Cursor users can install the same slim
# tree as a local plugin (~/.cursor/plugins/local/) instead of the full repo.
FILES = ("LICENSE", ".claude-plugin/plugin.json",
         ".cursor-plugin/plugin.json", ".cursor-plugin/marketplace.json")
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

Cursor: clone this branch into `~/.cursor/plugins/local/blender-developer-tools`
and reload the window (Customize then lists the 18 skills and 9 rules).

Skills reference bundled files as `${CLAUDE_PLUGIN_ROOT}/snippets/...`, which
Claude Code expands to this plugin's install directory. In Cursor, read it as
the root of this clone. Other repo links are pinned to the release tag.
"""


REPO_URL = "https://github.com/TMHSDigital/Blender-Developer-Tools"
# Skills Claude Code loads get links into the installed plugin instead of main,
# so a pinned install reads the snippet it shipped with, offline (#394).
# Claude Code substitutes ${CLAUDE_PLUGIN_ROOT} in plugin skill content.
_LOCAL_LINK = re.compile(re.escape(REPO_URL) + r"/(?:blob|tree)/main/((?:snippets|templates|rules|claude|skills)(?:/[^\s)`\"'#]*)?)")
_MAIN_LINK = re.compile(re.escape(REPO_URL) + r"/(blob|tree)/main/")
_LOCAL_REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s)`\"'#]+)")
TEXT_SUFFIXES = {".md", ".mdc", ".py", ".toml"}

# The release rewrites only "version" values in the manifests and the release
# tag in pinned links, so a build whose fingerprint matches the published
# branch carries no new plugin content.
_VERSION = re.compile(rb'("version"\s*:\s*")[^"]*(")')
_TAG = re.compile(rb"(/(?:blob|tree)/)v\d+\.\d+\.\d+/")


def rewrite_links(text: str, tag: str, local: bool) -> str:
    """Point repo links at the installed plugin (`local`) or at the release tag."""
    if local:
        text = _LOCAL_LINK.sub(r"${CLAUDE_PLUGIN_ROOT}/\1", text)
    return _MAIN_LINK.sub(lambda m: f"{REPO_URL}/{m.group(1)}/{tag}/", text)


def fingerprint(tree: Path) -> str:
    """sha256 over every file's path and bytes, with manifest versions blanked
    and line endings normalized. Equal fingerprints mean a release would
    publish nothing new to plugin users (#350)."""
    h = hashlib.sha256()
    for p in sorted(q for q in tree.rglob("*") if q.is_file() and ".git" not in q.parts):
        data = p.read_bytes().replace(b"\r\n", b"\n")
        if p.suffix == ".json":
            data = _VERSION.sub(rb"\1\2", data)
        elif p.suffix in TEXT_SUFFIXES:
            data = _TAG.sub(rb"\1", data)
        h.update(p.relative_to(tree).as_posix().encode() + b"\0" + data + b"\0")
    return h.hexdigest()


def unsafe_out(out: Path, force: bool) -> str | None:
    """Why `out` must not be deleted, or None when building there is safe.

    build() replaces `out` wholesale, so refuse anything that is the repo,
    contains the repo, or is a git checkout, and only replace a non-empty
    directory when the caller asked for it with --force.
    """
    out = out.resolve()
    if out == ROOT or out in ROOT.parents:
        return f"{out} is the repository or one of its parents"
    if (out / ".git").exists():
        return f"{out} contains a .git directory"
    if out.exists() and not out.is_dir():
        return f"{out} exists and is not a directory"
    if out.is_dir() and any(out.iterdir()) and not force:
        return f"{out} is not empty; pass --force to replace it"
    return None


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
    tag = "v" + (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    for p in out.rglob("*"):
        if p.is_file() and p.suffix in TEXT_SUFFIXES:
            text = p.read_text(encoding="utf-8")
            new = rewrite_links(text, tag, local=p.name == "SKILL.md")
            if new != text:
                p.write_text(new, encoding="utf-8", newline="")
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
    cursor = json.loads((out / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
    for key in ("skills", "rules"):
        for rel in cursor.get(key, []):
            if not (out / rel).is_file():
                errors.append(f"Cursor manifest {key} path {rel} missing from the dist")
    for p in out.rglob("*"):
        if not (p.is_file() and p.suffix in TEXT_SUFFIXES):
            continue
        text = p.read_text(encoding="utf-8")
        rel = p.relative_to(out).as_posix()
        for target in _LOCAL_REF.findall(text):
            if not (out / target.rstrip(".,;:")).exists():
                errors.append(f"{rel} links ${{CLAUDE_PLUGIN_ROOT}}/{target}, which is not in the dist")
        if _MAIN_LINK.search(text):
            errors.append(f"{rel} still links the repo's main branch")
    if size > MAX_BYTES:
        errors.append(f"dist is {size} bytes, over the {MAX_BYTES} budget")
    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="replace a non-empty --out directory")
    ap.add_argument("--fingerprint", type=Path, metavar="DIR",
                    help="print the content fingerprint of a built tree and exit")
    a = ap.parse_args(argv)
    if a.fingerprint:
        print(fingerprint(a.fingerprint))
        return 0
    if not a.out and not a.check:
        ap.error("give --out DIR or --check")
    if a.out:
        reason = unsafe_out(a.out, a.force)
        if reason:
            print(f"::error::refusing to build into {reason}", file=sys.stderr)
            return 2
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
