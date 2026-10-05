"""Tests for scripts/build_plugin_dist.py: --out safety and link rewriting. No Blender required.

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


class Links(unittest.TestCase):
    # #394: skills read the files the plugin installed, everything else pins
    # the release tag, and the tag never makes a release look like new content.
    URL = b.REPO_URL

    def test_skill_links_resolve_inside_the_plugin(self):
        text = f"[s]({self.URL}/blob/main/snippets/lod_chain.py) [t]({self.URL}/tree/main/templates)"
        self.assertEqual(b.rewrite_links(text, "v1.2.3", local=True),
                         "[s](${CLAUDE_PLUGIN_ROOT}/snippets/lod_chain.py) [t](${CLAUDE_PLUGIN_ROOT}/templates)")

    def test_other_links_pin_the_release_tag(self):
        text = f"[e]({self.URL}/tree/main/examples/bmesh-gear) [r]({self.URL}/blob/main/rules/x.mdc)"
        self.assertEqual(b.rewrite_links(text, "v1.2.3", local=False),
                         f"[e]({self.URL}/tree/v1.2.3/examples/bmesh-gear) [r]({self.URL}/blob/v1.2.3/rules/x.mdc)")

    def test_built_dist_has_no_main_links_and_every_local_link_resolves(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "dist"
            size = b.build(out)
            self.assertEqual(b.verify(out, size), [])
            skill = (out / "skills" / "ai-mesh-cleanup" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("${CLAUDE_PLUGIN_ROOT}/snippets/", skill)

    def test_verify_flags_a_missing_local_target_and_a_main_link(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "dist"
            size = b.build(out)
            skill = out / "skills" / "ai-mesh-cleanup" / "SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8")
                             + "\n${CLAUDE_PLUGIN_ROOT}/snippets/gone.py\n"
                             + f"{self.URL}/blob/main/README.md\n", encoding="utf-8")
            errors = "\n".join(b.verify(out, size))
            self.assertIn("snippets/gone.py", errors)
            self.assertIn("main branch", errors)

    def test_fingerprint_ignores_the_release_tag(self):
        with tempfile.TemporaryDirectory() as td:
            a, c = Path(td) / "a", Path(td) / "c"
            for d, tag in ((a, "v0.1.0"), (c, "v0.2.0")):
                d.mkdir()
                (d / "x.md").write_text(f"{self.URL}/blob/{tag}/docs/y.md\n", encoding="utf-8")
            self.assertEqual(b.fingerprint(a), b.fingerprint(c))
            (c / "x.md").write_text(f"{self.URL}/blob/v0.2.0/docs/z.md\n", encoding="utf-8")
            self.assertNotEqual(b.fingerprint(a), b.fingerprint(c))


if __name__ == "__main__":
    unittest.main()
