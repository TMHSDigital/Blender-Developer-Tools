"""Resolution tests for tests/check_exit_code_readme.py (#360). No Blender.

The gate is only as good as the exit codes it can see. These pin the shapes
showcase and example scripts actually use, so a refactor of the resolver
cannot quietly stop seeing them again. Run:
    python tests/test_exit_code_readme.py -v
"""
from __future__ import annotations

import ast
import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_exit_code_readme as c  # noqa: E402


def codes(src: str) -> set[int]:
    tree = ast.parse(textwrap.dedent(src))
    v = c.ExitVisitor(c.module_function_names(tree), c.module_int_constants(tree),
                      c.passthrough_helpers(tree))
    v.visit(tree)
    return {code for code, _ in v.literals if code}


class Resolution(unittest.TestCase):
    def test_literal_and_constant(self):
        self.assertEqual(codes("""
            EXIT_X = 7
            def main():
                if a: return 3
                return EXIT_X
        """), {3, 7})

    def test_fail_helper_positional_and_keyword(self):
        self.assertEqual(codes("""
            def fail(msg, code):
                print(msg)
                return code
            def check():
                if a: return fail("one", 15)
                return fail("two", code=16)
        """), {15, 16})

    def test_tuple_return_first_element(self):
        self.assertEqual(codes("""
            def fail(msg, code):
                return code
            def check():
                if a: return 9, objs, objs
                if b: return fail("x", 11), None, None
                return (fail("y", 12),) + none3
        """), {9, 11, 12})

    def test_helper_returning_a_non_parameter_is_not_passthrough(self):
        tree = ast.parse("def f(a, b):\n    x = a\n    return x\n")
        self.assertEqual(c.passthrough_helpers(tree), {})


class ReservedCodes(unittest.TestCase):
    """2 / 10 / 11 are argparse / framing / asset-quality in examples/ (#473)."""

    def rows(self, table):
        return c.readme_table_rows("## Exit codes\n\n| Code | Meaning |\n| --- | --- |\n"
                                   + textwrap.dedent(table))

    def test_overloaded_rows_rejected(self):
        bad = self.rows("""\
            | 2 | argparse / usage; also exporter RNA missing expected glTF kwargs |
            | 10 | X span off closed form; also gallery framing violation |
            | 11 | Evaluated bbox not symmetric about X |
        """)
        self.assertEqual(len(c.reserved_row_errors(bad, "R")), 3)

    def test_reserved_rows_accepted(self):
        good = self.rows("""\
            | 2 | argparse / usage |
            | 10 | Gallery framing violation (render path; `gallery_framing`) |
            | 11 | Asset-quality floor violation (`--output` only) |
        """)
        self.assertEqual(c.reserved_row_errors(good, "R"), [])

    def test_literal_reserved_sites(self):
        tree = ast.parse(textwrap.dedent("""
            def fail(msg, code):
                return code
            def check():
                if a: return 2
                if b: return fail("x", 11), None
                if c: return gallery_framing.EXIT_FRAMING
                if d: return gallery_framing.check_framing(s)
                return 12
        """))
        sites = c.literal_reserved_sites(tree, c.passthrough_helpers(tree))
        self.assertEqual(sorted(code for _, code in sites), [2, 11])


if __name__ == "__main__":
    unittest.main()
