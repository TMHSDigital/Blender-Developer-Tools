"""Stdlib tests for skip / sidecar classification. No Blender required.

These are the red-path proofs for the harness itself: unexpected skip is
FAIL, vacuous skip (marker + exit 0) is FAIL, missing sidecar is FAIL,
all-skip summary is not green.
"""
from __future__ import annotations

import json
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


class CatalogWiring(unittest.TestCase):
    def test_exit_pre_row_has_sidecar_and_floor(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "catalog.json"), encoding="utf-8") as fh:
            catalog = json.load(fh)
        row = next(i for i in catalog if i["name"] == "exit-pre-sidecar")
        self.assertEqual(row["min_version"], "5.1")
        self.assertIn("$OUT", row["expect_sidecar"])
        self.assertEqual(row["sidecar_contains"], "exit_pre-ok")


class Falsifier(unittest.TestCase):
    """A falsifier passes only by failing exactly as declared."""

    def c(self, code, **kw):
        return classify(proc_exit=code, output="", **kw)[0]

    def test_exact_exit_passes(self):
        self.assertEqual(self.c(7, expect_exit=7), PASS)

    def test_exit_0_is_fail(self):
        # the check did not fire: the falsifier witnesses nothing
        self.assertEqual(self.c(0, expect_exit=7), FAIL)

    def test_other_check_is_fail(self):
        # an earlier check fired: the target check is unproven
        self.assertEqual(self.c(3, expect_exit=7), FAIL)

    def test_crash_is_fail(self):
        self.assertEqual(self.c(1, expect_exit=7), FAIL)

    def test_cannot_expect_0_1_or_77(self):
        for bad in (0, 1, SKIP_EXIT):
            self.assertEqual(self.c(bad, expect_exit=bad), FAIL)

    def test_legal_skip_stays_skip(self):
        out = "SMOKE_SKIP: needs 5.1\n"
        st, _ = classify(proc_exit=SKIP_EXIT, output=out, min_version="5.1",
                         blender_version="4.5", expect_exit=3)
        self.assertEqual(st, SKIP)

    def test_sidecar_falsifier(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "s.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("atexit-ok")
            kw = dict(expect_sidecar=True, sidecar_path=path,
                      sidecar_contains="exit_pre-ok", expect_sidecar_fail=True)
            self.assertEqual(self.c(0, **kw), PASS)  # wrong contents caught
            self.assertEqual(self.c(2, **kw), FAIL)  # script itself failed
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("exit_pre-ok")
            self.assertEqual(self.c(0, **kw), FAIL)  # sidecar check not broken


class BuildCmd(unittest.TestCase):
    """Blender exits 0 on an uncaught exception unless --python-exit-code is set."""

    def _cmd(self, xvfb=False):
        import argparse

        import run_example

        ns = argparse.Namespace(blender="bl", script="s.py", script_args=["--x"], xvfb=xvfb)
        return run_example.build_cmd(ns)

    def test_exit_code_flag_precedes_python(self):
        cmd = self._cmd()
        i = cmd.index("--python-exit-code")
        self.assertEqual(cmd[i + 1], "1")
        self.assertLess(i, cmd.index("--python"))

    def test_xvfb_keeps_exit_code_flag(self):
        self.assertIn("--python-exit-code", self._cmd(xvfb=True))


class Stream(unittest.TestCase):
    """run_example.stream: a hung run is killed and reported, output is UTF-8."""

    def _stream(self, code, timeout=30):
        import contextlib
        import io

        import run_example

        with contextlib.redirect_stdout(io.StringIO()):
            return run_example.stream([sys.executable, "-c", code], timeout=timeout)

    def test_exit_code_is_returned(self):
        self.assertEqual(self._stream("import sys; sys.exit(3)")[0], 3)

    def test_hang_is_killed_and_returns_none(self):
        import time

        t0 = time.monotonic()
        code, out = self._stream(
            "import time; print('started', flush=True); time.sleep(120)", timeout=2)
        self.assertIsNone(code)
        self.assertIn("started", out)
        self.assertLess(time.monotonic() - t0, 30)

    @unittest.skipUnless(os.name == "posix", "process groups (xvfb-run case) are POSIX")
    def test_hang_kills_grandchild(self):
        import time

        with tempfile.TemporaryDirectory() as td:
            pidfile = os.path.join(td, "pid")
            child = ("import subprocess, sys, time; "
                     "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']); "
                     f"open({pidfile!r}, 'w').write(str(p.pid)); time.sleep(120)")
            self.assertIsNone(self._stream(child, timeout=2)[0])
            pid = int(open(pidfile).read())
            for _ in range(50):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
            else:
                self.fail("grandchild survived the timeout kill")

    def test_utf8_output_survives_any_locale(self):
        # U+201D contains byte 0x9D, which a strict cp1252 decode rejects.
        code, out = self._stream(
            r"import sys; sys.stdout.buffer.write(b'\xe2\x80\x9d\n'); sys.stdout.flush()")
        self.assertEqual(code, 0)
        self.assertIn("”", out)


class RunCatalog(unittest.TestCase):
    """run_catalog runs every row and reports all failures; empty is red."""

    def _run(self, rows, codes, extra=()):
        import contextlib
        import io
        from unittest import mock

        import run_catalog

        seen = []

        def fake_call(cmd):
            name = cmd[cmd.index("--name") + 1]
            seen.append(name)
            if "--expect-exit" in cmd:
                want = cmd[cmd.index("--expect-exit") + 1]
                seen.append(f"expect {want}")
            return codes.get(name, 0)

        with tempfile.TemporaryDirectory() as td:
            cat = os.path.join(td, "catalog.json")
            with open(cat, "w", encoding="utf-8") as fh:
                json.dump(rows, fh)
            err = io.StringIO()
            with mock.patch.object(run_catalog.subprocess, "call", fake_call),                     contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = run_catalog.main(
                    ["--blender", "x", "--series", "5.2", "--out", td, "--catalog", cat, *extra]
                )
        return code, seen, err.getvalue()

    def test_two_broken_examples_are_both_reported(self):
        rows = [{"name": n, "script": f"{n}.py"} for n in ("a", "b", "c", "d")]
        code, seen, err = self._run(rows, {"b": 1, "d": 3})
        self.assertEqual(code, 1)
        self.assertEqual(seen, ["a", "b", "c", "d"])
        self.assertIn("b (exit 1)", err)
        self.assertIn("d (exit 3)", err)

    def test_fail_fast_is_opt_in(self):
        rows = [{"name": n, "script": f"{n}.py"} for n in ("a", "b", "c")]
        code, seen, _ = self._run(rows, {"a": 1}, extra=("--fail-fast",))
        self.assertEqual((code, seen), (1, ["a"]))

    def test_all_pass_is_green(self):
        rows = [{"name": "a", "script": "a.py"}]
        self.assertEqual(self._run(rows, {})[0], 0)

    def test_falsifiers_run_after_each_row(self):
        rows = [{"name": "a", "script": "a.py",
                 "falsifiers": [{"args": ["--break"], "expect_exit": 4}]}]
        code, seen, _ = self._run(rows, {})
        self.assertEqual(code, 0)
        self.assertEqual(seen, ["a", "a [falsifier --break]", "expect 4"])

    def test_row_timeout_is_forwarded(self):
        from unittest import mock

        import run_catalog

        got = []

        def fake_call(cmd):
            got.append(cmd[cmd.index("--timeout") + 1] if "--timeout" in cmd else None)
            return 0

        with tempfile.TemporaryDirectory() as td:
            cat = os.path.join(td, "catalog.json")
            with open(cat, "w", encoding="utf-8") as fh:
                json.dump([{"name": "a", "script": "a.py", "timeout": 1800}], fh)
            import contextlib
            import io
            with mock.patch.object(run_catalog.subprocess, "call", fake_call),                     contextlib.redirect_stdout(io.StringIO()):
                run_catalog.main(["--blender", "x", "--series", "5.2", "--out", td,
                                  "--catalog", cat])
        self.assertEqual(got, ["1800"])

    def test_stale_expect_file_does_not_satisfy_row(self):
        import contextlib
        import io
        from unittest import mock

        import run_catalog

        with tempfile.TemporaryDirectory() as td:
            stale = os.path.join(td, "still.png")
            with open(stale, "wb") as fh:
                fh.write(b"old render")
            cat = os.path.join(td, "catalog.json")
            with open(cat, "w", encoding="utf-8") as fh:
                json.dump([{"name": "a", "script": "a.py",
                            "expect_file": "$OUT/still.png"}], fh)
            err = io.StringIO()
            with mock.patch.object(run_catalog.subprocess, "call", lambda cmd: 0),                     contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = run_catalog.main(["--blender", "x", "--series", "5.2", "--out", td,
                                         "--catalog", cat])
        self.assertEqual(code, 1)
        self.assertIn("missing", err.getvalue())

    def test_failing_falsifier_is_red(self):
        rows = [{"name": "a", "script": "a.py",
                 "falsifiers": [{"args": ["--break"], "expect_exit": 4}]}]
        code, _, err = self._run(rows, {"a [falsifier --break]": 1})
        self.assertEqual(code, 1)
        self.assertIn("a [falsifier --break]", err)

    def test_falsifier_below_its_min_version_is_skipped(self):
        rows = [{"name": "a", "script": "a.py",
                 "falsifiers": [{"args": ["--new-api"], "expect_exit": 4,
                                 "min_version": "5.2"}]}]
        code, seen, _ = self._run(rows, {})  # _run uses --series 5.2: runs
        self.assertEqual(seen, ["a", "a [falsifier --new-api]", "expect 4"])
        rows[0]["falsifiers"][0]["min_version"] = "9.9"
        code, seen, _ = self._run(rows, {})
        self.assertEqual((code, seen), (0, ["a"]))

    def test_no_falsifiers_flag(self):
        rows = [{"name": "a", "script": "a.py",
                 "falsifiers": [{"args": ["--break"], "expect_exit": 4}]}]
        _, seen, _ = self._run(rows, {}, extra=("--no-falsifiers",))
        self.assertEqual(seen, ["a"])

    def test_empty_catalog_is_red(self):
        code, seen, err = self._run([], {})
        self.assertEqual((code, seen), (1, []))
        self.assertIn("catalog is empty", err)


if __name__ == "__main__":
    unittest.main()
