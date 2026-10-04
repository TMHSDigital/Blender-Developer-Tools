#!/usr/bin/env python3
"""Skill and rules-summary file references must work outside a checkout.

An installed Claude Code plugin resolves a bare path such as
`snippets/lod_chain.py` against the user's project, where it does not exist.
So every reference from skills/*/SKILL.md, claude/blender-rules.md and
claude/skills/*/SKILL.md to a repo file must be an absolute link to this
repository, and that link must name a path that exists.

Fails on:
- a backticked bare repo path (`snippets/...`, `examples/...`,
  `templates/...`, `rules/...`) that is not the text of such a link;
- a github.com/TMHSDigital/Blender-Developer-Tools blob/tree URL whose path
  is missing from the tree.

    python tests/check_skill_refs.py      (exit 0 ok, 1 on a bad reference)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://github.com/TMHSDigital/Blender-Developer-Tools/"
LINK = re.compile(re.escape(URL) + r"(?:blob|tree)/main/([^)\s#]+)")
BARE = re.compile(r"(?<!\[)`((?:snippets|examples|templates|rules)/[^`]*)`(?!\]\()")


def files() -> list[Path]:
    return sorted([*ROOT.glob("skills/*/SKILL.md"), ROOT / "claude" / "blender-rules.md",
                   *ROOT.glob("claude/skills/*/SKILL.md")])


def check() -> list[str]:
    errors = []
    for f in files():
        rel = f.relative_to(ROOT).as_posix()
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in BARE.finditer(line):
                errors.append(f"{rel}:{i}: bare repo path `{m.group(1)}` (link it to {URL}...)")
            for m in LINK.finditer(line):
                if not (ROOT / m.group(1)).exists():
                    errors.append(f"{rel}:{i}: link to missing path {m.group(1)}")
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if errors:
        return 1
    print(f"skill references: {len(files())} files, every repo reference is a live absolute link")
    return 0


if __name__ == "__main__":
    sys.exit(main())
