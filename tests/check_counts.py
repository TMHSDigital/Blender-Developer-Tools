#!/usr/bin/env python3
"""Inventory counts in the docs must match the repo, every copy of them.

Counts skills, rules, templates, snippets, examples, showcase pieces and
gallery-rendered examples from the tree, then scans every user- or
agent-facing doc that states them (DOCS below) for each form they appear in:

  "16 skills", "76 showcase pieces"       prose and badge lines; up to two
  "29 small standalone snippets"           words may sit between number and noun
  "## Skills (16)"                         CLAUDE.md section headings
  "skills/<skill-name>/... 16 total"       CLAUDE.md architecture tree
  "56 of the 64 ship a render"             gallery-rendered vs all examples

Any stated number that disagrees is an error; the old substring check passed
as long as one copy anywhere was right. README must also state every count at
least once. Also enforces the documented 5-75 line snippet cap, every
"N to M lines" phrase that states it ("five to seventy-five lines" on the
landing page), and that ROADMAP's last shipped theme row equals the counts.

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
    "ROADMAP.md",
    "docs/new-example-prompt.md",
    "site.json",
    ".cursor-plugin/plugin.json",
    ".cursor-plugin/marketplace.json",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    "scripts/build_plugin_dist.py",  # the plugin-dist README text
)
# The landing and 404 templates: their counts are Jinja variables, so any
# literal number before an inventory noun is a stale copy.
DOC_GLOBS = ("scripts/site/*.j2",)

# Sections that record history ("The 8 skills" of v0.1.0, a dated survey of
# "the 42 examples that existed"), not the current inventory.
HISTORY = {
    "ROADMAP.md": re.compile(r"^## (v\d|Asset-quality survey)"),
}

# A word between the number and the noun that makes the phrase a subset, not
# the inventory: "4 new skills", "10 check-only examples", "56 rendered examples".
SUBSET_WORDS = {"new", "check-only", "rendered", "more", "other", "extra", "of",
                "remaining", "unbuilt", "below-floor", "gallery"}

# Phrases that match the count pattern but are not inventory counts.
NOT_COUNTS = {
    "404 templates",  # CLAUDE.md: "the landing and 404 templates"
}


PROSE = re.compile(
    r"\b(\d+) ((?:[\w-]+ ){0,2}?)(skills?|rules?|templates?|snippets?|examples?|showcase pieces?)\b"
)
LINE_RANGE = re.compile(r"\b([\w-]+) to ([\w-]+) lines\b", re.I)
THEME_ROW = re.compile(r"^\|[^|]+\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*Shipped")
SNIPPET_RANGE = (5, 75)
SNIPPET_LINE = re.compile(r"\bsnippets?\b|\bcanonical patterns,", re.I)

_ONES = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate(
    "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}


def number(word: str) -> int | None:
    """``75``, ``five``, ``seventy-five`` -> int; anything else -> None."""
    w = word.lower()
    if w.isdigit():
        return int(w)
    if w in _ONES:
        return _ONES[w]
    tens, _, ones = w.partition("-")
    if tens in _TENS and (not ones or (ones in _ONES and _ONES[ones] < 10)):
        return _TENS[tens] + (_ONES[ones] if ones else 0)
    return None
HEADING = re.compile(r"^#+ (Skills|Rules|Templates|Snippets|Examples) \((\d+)\)\s*$")
TREE = re.compile(r"^(skills|rules|templates|snippets|examples)/\S*\s+- .*?(\d+) total")
GALLERY = re.compile(r"\b(\d+) of the (\d+) ship a render")
# README overview table: "| **Snippets** | 29 small standalone Python files ..."
LAYER_ROW = re.compile(r"^\| \*\*(Skills|Rules|Templates|Snippets|Examples)\*\* \| (\d+)\b")

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

    docs = list(DOCS) + sorted(
        p.relative_to(root).as_posix() for g in DOC_GLOBS for p in root.glob(g))
    for doc in docs:
        path = root / doc
        if not path.exists():
            continue
        history = HISTORY.get(doc)
        in_history = False
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if history and line.startswith("## "):
                in_history = bool(history.match(line))
            if in_history:
                continue
            for m in PROSE.finditer(line):
                between = {w.lower() for w in m.group(2).split()}
                if m.group(0) in NOT_COUNTS or between & SUBSET_WORDS:
                    continue
                expect(doc, i, kind_of(m.group(3)), int(m.group(1)), m.group(0))
            # Rules and skills have size ranges of their own; only a line
            # about snippets ("Canonical patterns, ...") states the snippet cap.
            for m in LINE_RANGE.finditer(line) if SNIPPET_LINE.search(line) else ():
                lo, hi = number(m.group(1)), number(m.group(2))
                if lo is not None and hi is not None and (lo, hi) != SNIPPET_RANGE:
                    errors.append(f'{doc}:{i} says "{m.group(0)}" but snippets are '
                                  f"{SNIPPET_RANGE[0]} to {SNIPPET_RANGE[1]} lines")
            m = HEADING.match(line)
            if m:
                expect(doc, i, kind_of(m.group(1)), int(m.group(2)), m.group(0).strip())
            m = LAYER_ROW.match(line)
            if m:
                expect(doc, i, kind_of(m.group(1)), int(m.group(2)), m.group(0))
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
        if not SNIPPET_RANGE[0] <= n <= SNIPPET_RANGE[1]:
            errors.append(f"snippets/{f.name} is {n} lines (documented range is 5 to 75)")

    # ROADMAP's theme table: the newest shipped row is the current inventory.
    roadmap = root / "ROADMAP.md"
    if roadmap.exists():
        rows = [(i, m) for i, line in enumerate(roadmap.read_text(encoding="utf-8").splitlines(), 1)
                if (m := THEME_ROW.match(line))]
        if rows:
            i, m = rows[-1]
            stated = tuple(int(g) for g in m.groups())
            want = tuple(counts[k] for k in ("skills", "rules", "templates", "snippets"))
            if stated != want:
                errors.append(f"ROADMAP.md:{i} last shipped theme row is {stated} "
                              f"(skills, rules, templates, snippets) but the repo has {want}; "
                              "add a row for what shipped")

    return errors


def main() -> int:
    errors = check(ROOT)
    if errors:
        for e in errors:
            print(f"::error::{e}", file=sys.stderr)
        return 1
    c = actual_counts(ROOT)
    print(
        f"Counts verified in {len(DOCS)} docs and {len(DOC_GLOBS)} template set: {c['skills']} skills, {c['rules']} rules, "
        f"{c['templates']} templates, {c['snippets']} snippets, {c['examples']} examples "
        f"({c['gallery']} rendered), {c['showcase']} showcase pieces"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
