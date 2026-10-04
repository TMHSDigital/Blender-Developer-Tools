#!/usr/bin/env python3
"""Write release notes from the commits since the previous tag.

    python .github/scripts/release_notes.py --since v0.142.3 --version 0.143.0 \
        --notes "$RUNNER_TEMP/notes.md" --changelog CHANGELOG.md

Groups conventional-commit subjects (Features, Fixes, Other) with links to
each commit, skips the release bot's own "chore: bump version" commits, writes
the list to --notes (the GitHub release body) and, with --changelog, replaces
the version's "See release notes ... for details." placeholder that
release-doc-sync writes with the same list plus the link. Without this, every
CHANGELOG entry and release body said nothing about what shipped.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

REPO_URL = "https://github.com/TMHSDigital/Blender-Developer-Tools"
GROUPS = (
    ("Features", re.compile(r"^(feat|feature)(\(.+?\))?!?:", re.I)),
    ("Fixes", re.compile(r"^fix(\(.+?\))?!?:", re.I)),
)
SKIP = re.compile(r"^chore: bump version to ", re.I)


def commits(since: str | None) -> list[tuple[str, str]]:
    rng = f"{since}..HEAD" if since else "HEAD"
    out = subprocess.run(
        ["git", "log", rng, "--no-merges", "--format=%H%x09%s"],
        capture_output=True, text=True, check=True,
    ).stdout
    rows = []
    for line in out.splitlines():
        sha, _, subject = line.partition("\t")
        if subject and not SKIP.match(subject):
            rows.append((sha, subject.strip()))
    return rows


def render(rows: list[tuple[str, str]]) -> str:
    buckets: dict[str, list[str]] = {name: [] for name, _ in GROUPS}
    buckets["Other"] = []
    for sha, subject in rows:
        name = next((n for n, rx in GROUPS if rx.match(subject)), "Other")
        buckets[name].append(f"- {subject} ([`{sha[:7]}`]({REPO_URL}/commit/{sha}))")
    parts = []
    for name, lines in buckets.items():
        if lines:
            parts.append(f"### {name}\n\n" + "\n".join(lines))
    return "\n\n".join(parts) if parts else "No changes recorded."


def patch_changelog(path: str, version: str, body: str) -> bool:
    text = open(path, encoding="utf-8").read()
    placeholder = re.compile(
        r"(## \[" + re.escape(version) + r"\][^\n]*\n\n)See \[release notes\]\(([^)]+)\) for details\.",
    )
    m = placeholder.search(text)
    if not m:
        return False
    repl = m.group(1) + body + f"\n\n[Release v{version}]({m.group(2)})"
    text = text[: m.start()] + repl + text[m.end():]
    open(path, "w", encoding="utf-8", newline="\n").write(text)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default=None, help="previous tag (omit for the first release)")
    ap.add_argument("--version", required=True)
    ap.add_argument("--notes", required=True, help="file to write the release body to")
    ap.add_argument("--changelog", default=None)
    a = ap.parse_args(argv)
    body = render(commits(a.since))
    open(a.notes, "w", encoding="utf-8", newline="\n").write(body + "\n")
    print(body)
    if a.changelog and not patch_changelog(a.changelog, a.version, body):
        print(f"::warning::no 'See release notes' placeholder for {a.version} in {a.changelog}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
