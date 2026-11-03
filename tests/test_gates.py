"""Self-tests for the Validate gate scripts (#527). No Blender required.

A gate with a bug passes everything, and nothing would notice: Validate only
ever runs the gates against a repo that is (supposed to be) clean. Each test
here builds a small fixture that a gate must reject, so an inverted condition
or a typo in a key set turns this file red instead.

    python tests/test_gates.py -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS / "smoke"))

import check_content_catalog as ccc  # noqa: E402
import check_counts  # noqa: E402
import check_example_rules as cer  # noqa: E402
import check_falsifier_targets as cft  # noqa: E402
import check_smoke_catalog as csc  # noqa: E402


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


GOOD_FALSIFIER = {"args": ["--break"], "expect_exit": 3}


class SmokeCatalogSchema(unittest.TestCase):
    def errs(self, **row):
        base = {"name": "x", "script": "examples/x/x.py", "falsifiers": [GOOD_FALSIFIER]}
        base.update(row)
        return csc.check_schema({k: v for k, v in base.items() if v is not None})

    def test_good_row_passes(self):
        self.assertEqual(self.errs(), [])

    def test_unknown_row_key(self):
        self.assertTrue(any("unknown key 'falsifer'" in e for e in self.errs(falsifer=[])))

    def test_forbidden_exits(self):
        for bad in (0, 1, 2, 77, True):
            with self.subTest(bad=bad):
                e = self.errs(falsifiers=[{"args": ["--x"], "expect_exit": bad}])
                self.assertTrue(any("expect_exit" in m for m in e), e)

    def test_exactly_one_expectation(self):
        e = self.errs(expect_sidecar="o", falsifiers=[
            {"args": ["--x"], "expect_exit": 3, "expect_sidecar_fail": True}])
        self.assertTrue(any("exactly one" in m for m in e), e)

    def test_sidecar_fail_needs_a_sidecar(self):
        e = self.errs(falsifiers=[{"args": ["--x"], "expect_sidecar_fail": True}])
        self.assertTrue(any("no expect_sidecar" in m for m in e), e)

    def test_no_falsifiers(self):
        for fz in ([], None):
            with self.subTest(fz=fz):
                self.assertTrue(any("no falsifiers" in m for m in self.errs(falsifiers=fz)))

    def test_expect_output_needs_an_exit_and_text(self):
        ok = self.errs(falsifiers=[{"args": ["--x"], "expect_exit": 3, "expect_output": "ERROR: a"}])
        self.assertEqual(ok, [])
        for bad in ({"args": ["--x"], "expect_exit": 3, "expect_output": ""},
                    {"args": ["--x"], "expect_sidecar_fail": True, "expect_output": "x"}):
            with self.subTest(bad=bad):
                e = self.errs(expect_sidecar="o", falsifiers=[bad])
                self.assertTrue(any("expect_output" in m for m in e), e)

    def test_bad_falsifier_args(self):
        e = self.errs(falsifiers=[{"args": [], "expect_exit": 3}])
        self.assertTrue(any("'args'" in m for m in e), e)


class SmokeCatalogTree(unittest.TestCase):
    def run_check(self, rows, dirs=("examples/x",), scripts=("examples/x/x.py",)):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "showcase").mkdir()
            for d in dirs:
                (root / d).mkdir(parents=True)
            for s in scripts:
                write(root, s, "")
            write(root, "tests/smoke/catalog.json", json.dumps(rows))
            return csc.check(root)

    def row(self, **kw):
        r = {"name": "x", "script": "examples/x/x.py", "falsifiers": [GOOD_FALSIFIER]}
        r.update(kw)
        return r

    def test_clean_tree_passes(self):
        self.assertEqual(self.run_check([self.row()]), [])

    def test_empty_catalog(self):
        self.assertEqual(self.run_check([]), ["tests/smoke/catalog.json is empty"])

    def test_example_without_row(self):
        e = self.run_check([self.row()], dirs=("examples/x", "examples/y"))
        self.assertTrue(any("examples/y has no row" in m for m in e), e)

    def test_row_for_missing_directory(self):
        e = self.run_check([self.row(), self.row(name="z", script="examples/z/z.py")])
        self.assertTrue(any("missing directory examples/z" in m for m in e), e)

    def test_shared_exit_needs_expect_output(self):
        # #532: two checks return 4; the falsifier must name which one it breaks
        src = "def a():\n    return 4\n\ndef b():\n    return 4\n"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, "examples/x/x.py", src)
            bare = csc.check_shared_exits(root, self.row(falsifiers=[{"args": ["--b"], "expect_exit": 4}]))
            pinned = csc.check_shared_exits(root, self.row(falsifiers=[
                {"args": ["--b"], "expect_exit": 4, "expect_output": "ERROR: b"}]))
        self.assertTrue(any("returned from 2 places" in m for m in bare), bare)
        self.assertEqual(pinned, [])

    def test_row_for_missing_script(self):
        e = self.run_check([self.row(script="examples/x/renamed.py")])
        self.assertTrue(any("renamed.py does not exist" in m for m in e), e)


class ContentCatalog(unittest.TestCase):
    def run_check(self, cases, snippet="x = 1\n", skill=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, "snippets/s.py", snippet)
            if skill is not None:
                write(root, "skills/k/SKILL.md", skill)
            return ccc.check(str(root), cases)[0]

    def test_clean_passes(self):
        self.assertEqual(self.run_check({"s.py": {"check": "pass", "falsify": ("x = 1", "x = 2")}}), [])

    def test_snippet_without_case(self):
        self.assertTrue(any("no entry" in e for e in self.run_check({})))

    def test_falsify_old_not_in_source(self):
        e = self.run_check({"s.py": {"check": "pass", "falsify": ("y = 1", "y = 2")}})
        self.assertTrue(any("not in the snippet" in m for m in e), e)

    def test_falsify_that_changes_nothing(self):
        e = self.run_check({"s.py": {"check": "pass", "falsify": ("x = 1", "x = 1")}})
        self.assertTrue(any("changes something" in m for m in e), e)

    def test_skill_block_that_does_not_compile_reports_its_line(self):
        skill = "# K\n\ntext\n\n```python\nok = 1\nif True\n    pass\n```\n"
        e = self.run_check({"s.py": {"check": "pass", "falsify": ("x = 1", "x = 2")}}, skill=skill)
        self.assertTrue(any("skills/k/SKILL.md:7" in m for m in e), e)


class Counts(unittest.TestCase):
    def tree(self, readme: str) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root, "skills/a/SKILL.md", "x")
            write(root, "skills/b/SKILL.md", "x")
            write(root, "rules/r.mdc", "x")
            (root / "templates" / "t").mkdir(parents=True)
            write(root, "snippets/s.py", "a\nb\nc\nd\ne\n")
            write(root, "examples/e/README.md", "x")
            write(root, "examples/gallery.json", json.dumps({"examples": []}))
            (root / "showcase").mkdir()
            write(root, "README.md", readme)
            return check_counts.check(root)

    GOOD = ("2 skills, 1 rule, 1 template, 1 snippet, 1 example, 0 showcase pieces. "
            "Rules: `r`.\n")

    def test_good_readme_passes(self):
        self.assertEqual(self.tree(self.GOOD), [])

    def test_stale_count_fails(self):
        e = self.tree(self.GOOD + "The pack has 3 skills.\n")
        self.assertTrue(any('"3 skills"' in m for m in e), e)

    def test_unnamed_rule_fails(self):
        e = self.tree(self.GOOD.replace("Rules: `r`.", ""))
        self.assertTrue(any("never names rule `r`" in m for m in e), e)

    def test_snippet_over_the_cap_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel, text in (("skills/a/SKILL.md", "x"), ("skills/b/SKILL.md", "x"),
                              ("rules/r.mdc", "x"), ("snippets/s.py", "x\n" * 76),
                              ("examples/e/README.md", "x"),
                              ("examples/gallery.json", json.dumps({"examples": []})),
                              ("README.md", self.GOOD)):
                write(root, rel, text)
            (root / "templates" / "t").mkdir(parents=True)
            (root / "showcase").mkdir()
            e = check_counts.check(root)
        self.assertTrue(any("snippets/s.py is 76 lines" in m for m in e), e)


class ExampleRules(unittest.TestCase):
    def file_errors(self, src: str) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = write(root, "examples/x/x.py", src)
            return cer.check_file(p, root) + cer.check_use_nodes_gated(p, root)

    def test_per_vertex_loop_is_flagged(self):
        e = self.file_errors("for v in me.vertices:\n    v.co = (0, 0, 0)\n")
        self.assertTrue(any("foreach_set" in m for m in e), e)

    def test_exempt_marker_passes(self):
        src = f"for v in me.vertices:  {cer.MARKER} twelve verts\n    v.co = (0, 0, 0)\n"
        self.assertEqual(self.file_errors(src), [])

    def test_unguarded_active_object_is_flagged(self):
        e = self.file_errors("import bpy\nobj = bpy.context.active_object\nobj.name = 'x'\n")
        self.assertTrue(any("is None" in m for m in e), e)

    def test_guarded_active_object_passes(self):
        src = ("import bpy\nobj = bpy.context.active_object\n"
               "if obj is None:\n    raise SystemExit(3)\n")
        self.assertEqual(self.file_errors(src), [])

    def test_ungated_use_nodes_is_flagged(self):
        e = self.file_errors("mat.use_nodes = True\n")
        self.assertTrue(any("not gated" in m for m in e), e)

    def test_gated_use_nodes_passes(self):
        src = "import bpy\nif bpy.app.version < (5, 0, 0):\n    mat.use_nodes = True\n"
        self.assertEqual(self.file_errors(src), [])


class FalsifierTargets(unittest.TestCase):
    SCRIPT = ("import argparse\np = argparse.ArgumentParser()\n"
              "p.add_argument('--skip-decimate', action='store_true')\n")
    EXITS = "| Code | Meaning |\n| --- | --- |\n| 0 | ok |\n| 9 | LOD ratio |\n\n"

    def static(self, falsifier_table: str, script: str | None = None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            readme = write(root, "p/README.md", self.EXITS + falsifier_table)
            py = write(root, "p/p.py", self.SCRIPT if script is None else script)
            with mock.patch.object(cft, "piece_paths",
                                   lambda: iter([("p", str(readme), str(py))])):
                return cft.check_static()[0]

    TABLE = "| Flag | Budget violated | Exit |\n| --- | --- | --- |\n| `--skip-decimate` | {t} | {c} |\n"

    def test_good_table_passes(self):
        self.assertEqual(self.static(self.TABLE.format(t="LOD1 ratio band", c=9)), [])

    def test_flag_not_in_argparse(self):
        e = self.static(self.TABLE.format(t="LOD1", c=9), script="import argparse\n")
        self.assertTrue(any("not an argparse flag" in m for _, m in e), e)

    def test_exit_missing_from_exit_table(self):
        e = self.static(self.TABLE.format(t="LOD1", c=12))
        self.assertTrue(any("absent from the exit-code table" in m for _, m in e), e)

    def test_forbidden_exit(self):
        e = self.static(self.TABLE.format(t="LOD1", c=2))
        self.assertTrue(any("names no check" in m for _, m in e), e)

    def test_missing_budget(self):
        e = self.static(self.TABLE.format(t="", c=9))
        self.assertTrue(any("names no target budget" in m for _, m in e), e)

    def test_no_falsifier_table(self):
        e = self.static("")
        self.assertTrue(any("no falsifier table" in m for _, m in e), e)


if __name__ == "__main__":
    unittest.main()
