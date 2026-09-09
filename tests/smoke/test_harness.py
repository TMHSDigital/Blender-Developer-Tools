"""Stdlib tests for skip / sidecar classification. No Blender required.

These are the red-path proofs for the harness itself: unexpected skip is
FAIL, vacuous skip (marker + exit 0) is FAIL, missing sidecar is FAIL,
all-skip summary is not green.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import FAIL, PASS, SKIP, SKIP_EXIT, classify, summarize_records


class ClassifySkip(unittest.TestCase):
    def test_pass_exit_0(self):
        st, _ = classify(proc_exit=0, output="ok\n")
        self.assertEqual(st, PASS)

    def test_expected_skip_below_floor(self):
        st, detail = classify(
            proc_exit=SKIP_EXIT,
            output="SMOKE_SKIP: Bundles require Blender 5.0+\n",
            min_version="5.0",
            blender_version="4.5",
        )
        self.assertEqual(st, SKIP)
        self.assertIn("Bundles", detail)

    def test_unexpected_skip_on_supported_version_is_fail(self):
        st, detail = classify(
            proc_exit=SKIP_EXIT,
            output="SMOKE_SKIP: Bundles require Blender 5.0+\n",
            min_version="5.0",
            blender_version="5.2",
        )
        self.assertEqual(st, FAIL)
        self.assertIn("should run", detail)

    def test_skip_without_min_version_is_fail(self):
        st, _ = classify(
            proc_exit=SKIP_EXIT,
            output="SMOKE_SKIP: because I felt like it\n",
        )
        self.assertEqual(st, FAIL)

    def test_forbid_skip_is_fail(self):
        st, _ = classify(
            proc_exit=SKIP_EXIT,
            output="SMOKE_SKIP: no\n",
            min_version="99.0",
            blender_version="4.5",
            forbid_skip=True,
        )
        self.assertEqual(st, FAIL)

    def test_vacuous_skip_exit_0_with_marker_is_fail(self):
        st, detail = classify(
            proc_exit=0,
            output="SMOKE_SKIP: pretending\n",
            min_version="5.0",
            blender_version="4.5",
        )
        self.assertEqual(st, FAIL)
        self.assertIn("vacuous", detail)

    def test_skip_exit_without_reason_is_fail(self):
        st, _ = classify(proc_exit=SKIP_EXIT, output="no marker\n")
        self.assertEqual(st, FAIL)

    def test_blender_nonzero_is_fail(self):
        st, detail = classify(proc_exit=12, output="ERROR\n")
        self.assertEqual(st, FAIL)
        self.assertIn("12", detail)


class ClassifySidecar(unittest.TestCase):
    def test_missing_sidecar_is_fail(self):
        st, detail = classify(
            proc_exit=0,
            output="ok\n",
            expect_sidecar=True,
            sidecar_path=os.path.join(tempfile.gettempdir(), "no-such-sidecar-bdt"),
        )
        self.assertEqual(st, FAIL)
        self.assertIn("missing", detail)

    def test_sidecar_present_is_pass(self):
        fd, path = tempfile.mkstemp(prefix="bdt-sidecar-")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("sidecar-ok\n")
            st, _ = classify(
                proc_exit=0,
                output="ok\n",
                expect_sidecar=True,
                sidecar_path=path,
                sidecar_contains="sidecar-ok",
            )
            self.assertEqual(st, PASS)
        finally:
            os.remove(path)

    def test_sidecar_wrong_contents_is_fail(self):
        fd, path = tempfile.mkstemp(prefix="bdt-sidecar-")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("nope\n")
            st, _ = classify(
                proc_exit=0,
                output="ok\n",
                expect_sidecar=True,
                sidecar_path=path,
                sidecar_contains="sidecar-ok",
            )
            self.assertEqual(st, FAIL)
        finally:
            os.remove(path)

    def test_expected_skip_does_not_require_sidecar(self):
        st, _ = classify(
            proc_exit=SKIP_EXIT,
            output="SMOKE_SKIP: not on 4.5\n",
            min_version="5.1",
            blender_version="4.5",
            expect_sidecar=True,
            sidecar_path="/nonexistent",
        )
        self.assertEqual(st, SKIP)


class Summarize(unittest.TestCase):
    def test_pass_and_skip_is_green(self):
        p, s, f, code = summarize_records(
            [{"status": PASS}, {"status": SKIP, "detail": "x"}]
        )
        self.assertEqual((p, s, f, code), (1, 1, 0, 0))

    def test_any_fail_is_red(self):
        _, _, _, code = summarize_records(
            [{"status": PASS}, {"status": FAIL, "detail": "x"}]
        )
        self.assertEqual(code, 1)

    def test_all_skip_is_not_green(self):
        p, s, f, code = summarize_records(
            [{"status": SKIP, "detail": "a"}, {"status": SKIP, "detail": "b"}]
        )
        self.assertEqual((p, s, f), (0, 2, 0))
        self.assertEqual(code, 2)

    def test_empty_is_not_green(self):
        _, _, _, code = summarize_records([])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
