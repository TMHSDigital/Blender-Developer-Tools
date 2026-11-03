"""Regression tests for published falsifier commands (issue #517).

Run: python tests/test_published_falsifier_args.py
No Blender required.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_examples_index as index_builder  # noqa: E402


class PublishedFalsifierArgsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index, errors = index_builder.build_index()
        if errors:
            raise AssertionError(errors)

    def test_swatch_grid_falsifier_preserves_render_arguments(self):
        swatch = next(e for e in self.index if e["name"] == "swatch-grid")
        falsifier = next(f for f in swatch["falsifiers"] if "--same-base" in f["args"])
        self.assertEqual(
            falsifier["args"],
            [
                "--output", "$OUT/swatch.png", "--engine", "cycles",
                "--samples", "8", "--width", "640", "--same-base",
            ],
        )
        self.assertEqual(falsifier["expect_exit"], 6)

    def test_published_skill_command_is_copyable_without_smoke_environment(self):
        swatch = next(e for e in self.index if e["name"] == "swatch-grid")
        command = index_builder._flag(swatch["falsifiers"][0])
        self.assertIn("--output swatch.png", command)
        self.assertIn("--engine cycles", command)
        self.assertIn("--same-base", command)
        self.assertNotIn("$OUT", command)

    def test_vse_cut_list_retains_pixel_check_arguments(self):
        vse = next(e for e in self.index if e["name"] == "vse-cut-list")
        self.assertTrue(any(
            f["args"][:3] == ["--check-pixels", "--engine", "cycles"]
            and "--swap-inputs" in f["args"]
            for f in vse["falsifiers"]
        ))


if __name__ == "__main__":
    unittest.main()
