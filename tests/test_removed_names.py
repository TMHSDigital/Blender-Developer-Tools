"""Tests for .github/scripts/removed_names.py (#498). Needs git.

Run: python tests/test_removed_names.py -v
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "removed_names.py"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@unittest.skipIf(shutil.which("git") is None, "git not available")
class RemovedNames(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        for rel in ("skills/a/SKILL.md", "skills/b/SKILL.md", "rules/r1.mdc",
                    "live-session/skills/live/SKILL.md", "snippets/s.py"):
            self.write(rel)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "tag", "v1")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text="x\n"):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "change")

    def removed(self):
        out = subprocess.run([sys.executable, str(SCRIPT), "v1"], cwd=self.repo,
                             capture_output=True, text=True, check=True).stdout
        return out.split()

    def test_nothing_removed(self):
        self.write("skills/c/SKILL.md")
        self.write("skills/a/SKILL.md", "edited\n")
        self.commit()
        self.assertEqual(self.removed(), [])

    def test_renamed_skill_and_removed_rule(self):
        git(self.repo, "mv", "skills/b", "skills/b2")
        git(self.repo, "rm", "-q", "rules/r1.mdc")
        self.commit()
        self.assertEqual(" ".join(self.removed()), "rule r1 skill b")

    def test_live_session_skill_counts(self):
        git(self.repo, "rm", "-q", "-r", "live-session/skills/live")
        self.commit()
        self.assertEqual(" ".join(self.removed()), "skill live")

    def test_snippet_removal_is_not_a_name_change(self):
        git(self.repo, "rm", "-q", "snippets/s.py")
        self.commit()
        self.assertEqual(self.removed(), [])


if __name__ == "__main__":
    unittest.main()
