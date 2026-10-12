#!/usr/bin/env python3
"""Print the skill and rule names that existed at BASE and are gone at HEAD.

    python .github/scripts/removed_names.py v0.153.0

A skill is a directory with a SKILL.md under skills/ or live-session/skills/;
a rule is rules/<name>.mdc. Agents and docs cite these names, so after 1.0
removing or renaming one is a breaking change (ROADMAP "Stable (1.0)", #498).
release.yml fails a release that drops a name without a breaking-change
marker once VERSION is 1.0 or later, and warns before that.

Exit codes: 0 always when git works (the list may be empty), 2 when git
cannot read BASE.
"""
from __future__ import annotations

import subprocess
import sys

ROOTS = ("skills/", "live-session/skills/")


def names(paths: list[str]) -> set[str]:
    out = set()
    for p in paths:
        for root in ROOTS:
            rest = p[len(root):] if p.startswith(root) else None
            if rest and rest.count("/") == 1 and rest.endswith("/SKILL.md"):
                out.add("skill " + rest.split("/")[0])
        if p.startswith("rules/") and p.endswith(".mdc") and p.count("/") == 1:
            out.add("rule " + p[len("rules/"):-len(".mdc")])
    return out


def tree(ref: str) -> list[str]:
    return subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, "--", "skills", "rules",
                           "live-session/skills"],
                          capture_output=True, text=True, check=True).stdout.splitlines()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: removed_names.py BASE", file=sys.stderr)
        return 2
    try:
        before, after = names(tree(argv[1])), names(tree("HEAD"))
    except subprocess.CalledProcessError as e:
        print(f"git could not read {argv[1]}: {e.stderr.strip()}", file=sys.stderr)
        return 2
    for name in sorted(before - after):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
