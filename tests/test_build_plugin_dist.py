"""Safety tests for scripts/build_plugin_dist.py --out. No Blender required.

build() replaces --out wholesale, so the script must refuse a target it
would destroy (the repo, a parent of it, a git checkout, or a non-empty
directory without --force) before touching anything. Run:
    python tests/test_build_plugin_dist.py -v
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_plugin_dist as b  # noqa: E402


def run(argv):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = b.main(argv)
    return code, err.getvalue()


class OutGuard(unittest.TestCase):
    # The repo and its parents are checked through unsafe_out() directly, never
    # through main(): if the guard regressed, main() would delete the checkout.
    def test_refuses_repo_root(self):
        self.assertIn("repository", b.unsafe_out(REPO, force=True) or "")

    def test_refuses_parent_of_repo(self):
        self.assertIn("repository", b.unsafe_out(REPO.parent, force=True) or "")

    def test_refuses_non_empty_dir_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            keep = Path(td) / "important.txt"
            keep.write_text("keep", encoding="utf-8")
            code, err = run(["--out", td])
            self.assertEqual(code, 2)
            self.assertIn("--force", err)
            self.assertTrue(keep.is_file())

    def test_refuses_git_checkout_even_with_force(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".git").mkdir()
            code, err = run(["--out", td, "--force"])
            self.assertEqual(code, 2)
            self.assertIn(".git", err)
            self.assertTrue((Path(td) / ".git").is_dir())

    def test_builds_into_missing_dir(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "dist"
            code, _ = run(["--out", str(out)])
            self.assertEqual(code, 0)
            self.assertTrue((out / ".claude-plugin" / "plugin.json").is_file())

    def test_force_replaces_previous_build(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "dist"
            self.assertEqual(run(["--out", str(out)])[0], 0)
            (out / "stale.txt").write_text("old", encoding="utf-8")
            self.assertEqual(run(["--out", str(out)])[0], 2)
            self.assertEqual(run(["--out", str(out), "--force"])[0], 0)
            self.assertFalse((out / "stale.txt").exists())


if __name__ == "__main__":
    unittest.main()
