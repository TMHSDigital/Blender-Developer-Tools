#!/usr/bin/env python3
"""Inventory counts in the docs must match the repo, every copy of them.

Counts skills, rules, templates, snippets, examples, showcase pieces and
gallery-rendered examples from the tree, then scans every user- or
agent-facing doc that states them (DOCS below) for each form they appear in:

  "16 skills", "76 showcase pieces"       prose and badge lines
  "## Skills (16)"                         CLAUDE.md section headings
  "skills/<skill-name>/... 16 total"       CLAUDE.md architecture tree
  "56 of the 64 ship a render"             gallery-rendered vs all examples

Any stated number that disagrees is an error; the old substring check passed
as long as one copy anywhere was right. README must also state every count at
least once. Also enforces the documented 5-75 line snippet cap.

Run: python tests/check_counts.py            (exit 0 ok, 1 on mismatch)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOCS = (
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "docs/new-example-prompt.md",
)

# Phrases that match the count pattern but are not inventory counts.
NOT_COUNTS = {
    "404 templates",  # CLAUDE.md: "the landing and 404 templates"
}

# README per-category <details> summaries ("— 7 examples") count a category,
# not the whole set.
CATEGORY_SUMMARY = re.compile(r"^<summary><strong>[^<]+</strong> — \d+ examples?</summary>$")

PROSE = re.compile(
    r"\b(\d+) (skills?|rules?|templates?|snippets?|examples?|showcase pieces?)\b"
)
HEADING = re.compile(r"^#+ (Skills|Rules|Templates|Snippets|Examples) \((\d+)\)\s*$")
TREE = re.compile(r"^(skills|rules|templates|snippets|examples)/\S*\s+- .*?(\d+) total")
GALLERY = re.compile(r"\b(\d+) of the (\d+) ship a render")

KIND = {
    "skill": "skills", "rule": "rules", "template": "templates",
    "snippet": "snippets", "example": "examples", "showcase piece": "showcase",
}


def actual_counts(root: Path) -> dict[str, int]:
    def dirs_with(parent: str, marker: str | None) -> int:
        p = root / parent
        if not p.is_dir():
            return 0
        return sum(
            1 for d in p.iterdir()
            if d.is_dir() and (marker is None or (d / marker).exists())
        )

    gallery = json.loads((root / "examples" / "gallery.json").read_text(encoding="utf-8"))
    entries = gallery["examples"] if isinstance(gallery, dict) else gallery
    return {
        "skills": dirs_with("skills", "SKILL.md"),
        "rules": len(list((root / "rules").glob("*.mdc"))),
        "templates": dirs_with("templates", None),
        "snippets": len(list((root / "snippets").glob("*.py"))),
        "examples": dirs_with("examples", "README.md"),
        "showcase": dirs_with("showcase", "README.md"),
        "gallery": len(entries),
    }


def kind_of(word: str) -> str:
    w = word.lower()
    return KIND[w[:-1] if w.endswith("s") else w]


def check(root: Path) -> list[str]:
    counts = actual_counts(root)
    errors: list[str] = []

    def expect(doc: str, line_no: int, kind: str, stated: int, phrase: str) -> None:
        if stated != counts[kind]:
            errors.append(f'{doc}:{line_no} says "{phrase}" but the repo has {counts[kind]}')

    for doc in DOCS:
        path = root / doc
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CATEGORY_SUMMARY.match(line.strip()):
                continue
            for m in PROSE.finditer(line):
                if m.group(0) in NOT_COUNTS:
                    continue
                expect(doc, i, kind_of(m.group(2)), int(m.group(1)), m.group(0))
            m = HEADING.match(line)
            if m:
                expect(doc, i, kind_of(m.group(1)), int(m.group(2)), m.group(0).strip())
            m = TREE.match(line)
            if m:
                expect(doc, i, m.group(1), int(m.group(2)), m.group(0).strip())
            for m in GALLERY.finditer(line):
                expect(doc, i, "gallery", int(m.group(1)), m.group(0))
                expect(doc, i, "examples", int(m.group(2)), m.group(0))

    readme = (root / "README.md").read_text(encoding="utf-8")
    plural = {"templates": "template", "showcase": "showcase piece"}
    for kind in ("skills", "rules", "templates", "snippets", "examples", "showcase"):
        n = counts[kind]
        word = {"showcase": "showcase pieces"}.get(kind, kind)
        if n == 1:
            word = plural.get(kind, kind[:-1])
        if not re.search(rf"\b{n} {word}\b", readme):
            errors.append(f'README.md never states "{n} {word}"')

    for f in sorted((root / "snippets").glob("*.py")):
        n = len(f.read_text(encoding="utf-8").splitlines())
        if not 5 <= n <= 75:
            errors.append(f"snippets/{f.name} is {n} lines (documented range is 5 to 75)")

    return errors


def main() -> int:
    errors = check(ROOT)
    if errors:
        for e in errors:
            print(f"::error::{e}", file=sys.stderr)
        return 1
    c = actual_counts(ROOT)
    print(
        f"Counts verified in {len(DOCS)} docs: {c['skills']} skills, {c['rules']} rules, "
        f"{c['templates']} templates, {c['snippets']} snippets, {c['examples']} examples "
        f"({c['gallery']} rendered), {c['showcase']} showcase pieces"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
