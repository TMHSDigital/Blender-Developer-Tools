"""Tests for .github/scripts/bump-kind.sh (release.yml and pages.yml share it).

Run: python tests/test_bump_kind.py -v (needs bash).
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "bump-kind.sh"
# Resolve now: on Windows CreateProcess would find System32\bash.exe (WSL) first.
BASH = shutil.which("bash")


def kind(*messages: str) -> str:
    # git log --format='%B%x00' separates entries with "\n" after each NUL.
    stdin = "\n".join(m + "\0" for m in messages)
    # Bytes, not text mode: on Windows text mode rewrites LF as CRLF.
    out = subprocess.run(
        [BASH, SCRIPT.as_posix()], input=stdin.encode(), capture_output=True, check=True
    )
    return out.stdout.decode().strip()


@unittest.skipIf(BASH is None, "bash not available")
class BumpKind(unittest.TestCase):
    def test_docs_and_chore_do_not_release(self):
        self.assertEqual(kind("docs: tidy README\n", "chore: bump version to 1.2.3 [skip ci]\n"), "none")

    def test_fix_is_patch(self):
        self.assertEqual(kind("fix(snippets): x\n"), "patch")

    def test_feat_is_minor_and_beats_fix(self):
        self.assertEqual(kind("fix: a\n", "feat(showcase): b\n"), "minor")

    def test_bang_subject_is_major(self):
        self.assertEqual(kind("feat(api)!: drop 4.5\n"), "major")

    def test_breaking_footer_is_major(self):
        self.assertEqual(kind("refactor: x\n\nBREAKING CHANGE: removes y\n"), "major")

    def test_breaking_prose_in_subject_is_not_major(self):
        # Was major: the old grep matched "BREAKING[ -]CHANGE" anywhere, -i.
        self.assertEqual(kind("docs: explain breaking-change policy\n"), "none")
        self.assertEqual(kind("fix: note the breaking change in docs\n"), "patch")

    def test_lowercase_footer_is_not_major(self):
        self.assertEqual(kind("fix: x\n\nbreaking change: no\n"), "patch")

    def test_empty_input_is_none(self):
        self.assertEqual(kind(), "none")


if __name__ == "__main__":
    unittest.main()
