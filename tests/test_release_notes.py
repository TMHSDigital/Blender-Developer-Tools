"""Tests for .github/scripts/release_notes.py (release body + CHANGELOG entry).

Run: python tests/test_release_notes.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                                ".github", "scripts"))
import release_notes as rn  # noqa: E402

STUB = """# Changelog

## [1.2.0] - 2026-10-04

See [release notes](https://example.test/releases/tag/v1.2.0) for details.

## [1.1.0] - 2026-10-03

See [release notes](https://example.test/releases/tag/v1.1.0) for details.
"""


SKILL = ["skills/operators/SKILL.md"]
CI = [".github/workflows/validate.yml"]


class Render(unittest.TestCase):
    def test_groups_and_links(self):
        body = rn.render([("a" * 40, "feat(x): new", SKILL), ("b" * 40, "fix: bug", ["rules/x.mdc"]),
                          ("c" * 40, "docs: words", ["snippets/a.py"])])
        self.assertTrue(body.startswith("### For agents and users"))
        self.assertLess(body.index("**Features**"), body.index("**Fixes**"))
        self.assertLess(body.index("**Fixes**"), body.index("**Other**"))
        self.assertIn("feat(x): new ([`aaaaaaa`](", body)
        self.assertNotIn("<details>", body)

    def test_empty(self):
        self.assertEqual(rn.render([]), "No changes recorded.")

    def test_skill_leads_and_maintenance_is_collapsed(self):
        body = rn.render([("a" * 40, "fix(ci): pin action", CI),
                          ("b" * 40, "feat(skills): new skill", SKILL + ["examples/x/README.md"]),
                          ("c" * 40, "fix(site): hero copy", ["scripts/site/template.html.j2"])])
        user, _, rest = body.partition("<details>")
        self.assertIn("feat(skills): new skill", user)
        self.assertNotIn("fix(ci)", user)
        self.assertIn("<summary>Maintenance (2 commits", rest)
        self.assertIn("fix(ci): pin action", rest)
        self.assertIn("fix(site): hero copy", rest)
        self.assertTrue(rest.rstrip().endswith("</details>"))

    def test_maintenance_only_release_is_one_line_plus_collapsed_block(self):
        body = rn.render([("a" * 40, "fix(tests): cover helpers", ["tests/check_counts.py"])])
        self.assertTrue(body.startswith(rn.NO_USER_CHANGES))
        self.assertNotIn("For agents and users", body)
        self.assertIn("<summary>Maintenance (1 commit):", body)

    def test_plugin_paths(self):
        for path in ("skills/a/SKILL.md", "rules/a.mdc", "snippets/a.py", "templates/t/x.py",
                     "claude/blender-rules.md"):
            self.assertTrue(rn.is_user_facing([path]), path)
        for path in ("examples/a/a.py", "showcase/a/README.md", "docs/gallery/index.html",
                     "README.md", ".github/scripts/release_notes.py", "skillsfoo/x"):
            self.assertFalse(rn.is_user_facing([path]), path)

    def test_bump_commits_are_skipped(self):
        self.assertTrue(rn.SKIP.match("chore: bump version to 1.2.0 [skip ci]"))


class PatchChangelog(unittest.TestCase):
    def test_replaces_only_that_version(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "CHANGELOG.md")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(STUB)
            self.assertTrue(rn.patch_changelog(p, "1.2.0", "### Fixes\n\n- fix: x"))
            text = open(p, encoding="utf-8").read()
            self.assertIn("## [1.2.0] - 2026-10-04\n\n### Fixes\n\n- fix: x\n\n[Release v1.2.0]", text)
            self.assertIn("v1.1.0) for details.", text)  # other entries untouched

    def test_missing_placeholder_reports_false(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "CHANGELOG.md")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(STUB)
            self.assertFalse(rn.patch_changelog(p, "9.9.9", "x"))


if __name__ == "__main__":
    unittest.main()
