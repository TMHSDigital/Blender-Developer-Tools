"""Exit-code tests for scripts/measure_hero_drift.py. No Blender required.

Needs numpy and Pillow (the script's own dependencies). Run:
    python tests/test_measure_hero_drift.py -v
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import measure_hero_drift as m  # noqa: E402

ENTRY = {"name": "demo", "dir": "examples/demo", "hero": "docs/gallery/assets/demo-hero.webp"}


def run(argv, *, entries=(ENTRY,), version="Blender 5.2.1 LTS", version_exit=0, size_match=True):
    """Call m.main with every external effect faked; return (exit code, stderr)."""
    td = Path(tempfile.mkdtemp())
    (td / "examples" / "demo").mkdir(parents=True)
    (td / "examples" / "demo" / "demo.py").write_text("", encoding="utf-8")

    def fake_run(command, **kw):
        if "--version" in command:
            return mock.Mock(stdout=(version + "\n") if version else "", returncode=version_exit)
        Path(command[command.index("--output") + 1]).write_bytes(b"png")
        return mock.Mock(returncode=0, stdout="", stderr="")

    def fake_compare(committed, fresh):
        if not size_match:
            return {"shape_committed": (16, 16), "shape_fresh": (8, 8)}
        return {"mean_abs": 0.0, "gt2pct": 0.0, "vs_q90": 0.0,
                "luma_committed": 0.1, "luma_fresh": 0.1, "bytes_committed": 1}

    err = io.StringIO()
    with mock.patch.object(m, "REPO", td), \
            mock.patch.object(m, "entries", lambda: list(entries)), \
            mock.patch.object(m, "render_args", lambda e, png: ["--output", str(png)]), \
            mock.patch.object(m.subprocess, "run", fake_run), \
            mock.patch.object(m, "compare", fake_compare), \
            contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        code = m.main(["--blender", "blender", "--out", str(td / "out"), *argv])
    return code, err.getvalue()


class ExitCodes(unittest.TestCase):
    def test_matching_sizes_exit_0(self):
        self.assertEqual(run([])[0], 0)

    def test_size_mismatch_is_a_failure(self):
        code, _ = run([], size_match=False)
        self.assertEqual(code, 3)

    def test_unknown_only_name_is_usage_error(self):
        code, err = run(["--only", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("nope", err)

    def test_nothing_measured_is_usage_error(self):
        self.assertEqual(run([], entries=())[0], 2)

    def test_blender_version_failure_is_clear_error(self):
        code, err = run([], version="", version_exit=1)
        self.assertEqual(code, 2)
        self.assertIn("--version", err)


class RenderArgs(unittest.TestCase):
    def test_bare_trailing_output_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "examples" / "demo"
            d.mkdir(parents=True)
            (d / "README.md").write_text(
                "blender --background --python demo.py -- --engine cycles --output\n",
                encoding="utf-8",
            )
            with mock.patch.object(m, "REPO", Path(td)):
                self.assertIsNone(m.render_args({"dir": "examples/demo"}, Path("p.png")))

    def test_output_path_is_retargeted(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "examples" / "demo"
            d.mkdir(parents=True)
            (d / "README.md").write_text(
                "blender --background --python demo.py -- --output out.png --engine cycles\n",
                encoding="utf-8",
            )
            with mock.patch.object(m, "REPO", Path(td)):
                args = m.render_args({"dir": "examples/demo"}, Path("fresh.png"))
        self.assertEqual(args[args.index("--output") + 1], "fresh.png")


if __name__ == "__main__":
    unittest.main()
