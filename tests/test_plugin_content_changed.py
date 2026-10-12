"""Tests for .github/scripts/plugin-content-changed.sh (#350). Needs bash + git.

Run: python tests/test_plugin_content_changed.py -v
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "plugin-content-changed.sh"
BASH = shutil.which("bash")


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@unittest.skipIf(BASH is None or shutil.which("git") is None, "bash/git not available")
class PluginContentChanged(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "skills" / "a").mkdir(parents=True)
        (self.repo / "skills" / "a" / "SKILL.md").write_text("one\n", encoding="utf-8")
        (self.repo / "README.md").write_text("readme\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "tag", "v1")

    def tearDown(self):
        self.tmp.cleanup()

    def changed(self):
        env = {**os.environ, "PYTHON": Path(sys.executable).as_posix()}
        return subprocess.run([BASH, SCRIPT.as_posix(), "v1"], cwd=self.repo, env=env).returncode == 0

    def commit(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "docs: change")

    def test_no_change(self):
        self.assertFalse(self.changed())

    def test_docs_outside_plugin_is_not_content(self):
        self.commit("README.md", "new readme\n")
        self.commit("docs/gallery/index.html", "<p>x</p>\n")
        self.assertFalse(self.changed())

    def test_skill_edit_is_content(self):
        self.commit("skills/a/SKILL.md", "two\n")
        self.assertTrue(self.changed())

    def test_mcp_config_manifests_and_license_count(self):
        # #494: v0.153.0 shipped the MCP registration as "no plugin changes".
        for rel in ("live-session/mcp.json", ".claude-plugin/plugin.json", "LICENSE"):
            with self.subTest(rel=rel):
                git(self.repo, "reset", "-q", "--hard", "v1")
                self.commit(rel, "{}\n")
                self.assertTrue(self.changed())

    def test_rule_and_snippet_dirs_count(self):
        self.commit("snippets/x.py", "print(1)\n")
        self.assertTrue(self.changed())


if __name__ == "__main__":
    unittest.main()
