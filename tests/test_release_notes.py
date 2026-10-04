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


class Render(unittest.TestCase):
    def test_groups_and_links(self):
        body = rn.render([("a" * 40, "feat(x): new"), ("b" * 40, "fix: bug"),
                          ("c" * 40, "docs: words")])
        self.assertLess(body.index("### Features"), body.index("### Fixes"))
        self.assertLess(body.index("### Fixes"), body.index("### Other"))
        self.assertIn("feat(x): new ([`aaaaaaa`](", body)

    def test_empty(self):
        self.assertEqual(rn.render([]), "No changes recorded.")

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
