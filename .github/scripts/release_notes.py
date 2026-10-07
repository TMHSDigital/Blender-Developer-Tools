#!/usr/bin/env python3
"""Write release notes from the commits since the previous tag.

    python .github/scripts/release_notes.py --since v0.142.3 --version 0.143.0 \
        --notes "$RUNNER_TEMP/notes.md" --changelog CHANGELOG.md

Splits the commits in two (#455):

- **For agents and users**: commits that touched what the plugin ships
  (skills/, rules/, snippets/, templates/, claude/), grouped Features, Fixes,
  Other. This is what a plugin user gets from the update, so it leads.
- **Maintenance**: everything else (CI, tests, the site and gallery,
  showcase pieces, examples, docs), in a collapsed <details> block.

A release with no plugin change says so in one line above the collapsed
block. Skips the release bot's own "chore: bump version" commits, writes the
body to --notes (the GitHub release body) and, with --changelog, replaces the
version's "See release notes ... for details." placeholder that
release-doc-sync writes with the same body plus the link.
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
# What the plugin ships (scripts/build_plugin_dist.py DIRS): a change here is
# a change a plugin user receives.
USER_PATHS = ("skills/", "rules/", "snippets/", "templates/", "claude/")
NO_USER_CHANGES = ("No changes to the plugin content (skills, rules, snippets, templates) "
                   "in this release.")


def commits(since: str | None) -> list[tuple[str, str, list[str]]]:
    """(sha, subject, changed paths) per commit, newest first."""
    rng = f"{since}..HEAD" if since else "HEAD"
    out = subprocess.run(
        ["git", "log", rng, "--no-merges", "--name-only", "--format=%x00%H%x09%s"],
        capture_output=True, text=True, check=True,
    ).stdout
    rows = []
    for block in out.split("\0")[1:]:
        head, _, files = block.partition("\n")
        sha, _, subject = head.partition("\t")
        if subject and not SKIP.match(subject):
            rows.append((sha, subject.strip(), [f for f in files.splitlines() if f.strip()]))
    return rows


def is_user_facing(files: list[str]) -> bool:
    return any(f.startswith(USER_PATHS) for f in files)


def _line(sha: str, subject: str) -> str:
    return f"- {subject} ([`{sha[:7]}`]({REPO_URL}/commit/{sha}))"


def render(rows: list[tuple[str, str, list[str]]]) -> str:
    if not rows:
        return "No changes recorded."
    user = [r for r in rows if is_user_facing(r[2])]
    maint = [r for r in rows if not is_user_facing(r[2])]

    parts = []
    if user:
        buckets: dict[str, list[str]] = {name: [] for name, _ in GROUPS}
        buckets["Other"] = []
        for sha, subject, _ in user:
            name = next((n for n, rx in GROUPS if rx.match(subject)), "Other")
            buckets[name].append(_line(sha, subject))
        groups = [f"**{name}**\n\n" + "\n".join(lines) for name, lines in buckets.items() if lines]
        parts.append("### For agents and users\n\n" + "\n\n".join(groups))
    else:
        parts.append(NO_USER_CHANGES)
    if maint:
        parts.append(
            f"<details>\n<summary>Maintenance ({len(maint)} "
            f"commit{'s' if len(maint) != 1 else ''}): CI, tests, site, examples, showcase, docs"
            "</summary>\n\n"
            + "\n".join(_line(sha, subject) for sha, subject, _ in maint)
            + "\n\n</details>"
        )
    return "\n\n".join(parts)


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
