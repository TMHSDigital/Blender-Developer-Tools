"""Exit-code tests for .github/scripts/release-gate.sh against a stubbed gh.

The gate must fail closed: any gh error, empty output, or unparseable output
blocks the release. Run: python tests/test_release_gate.py -v (needs bash).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / ".github" / "scripts" / "release-gate.sh"
# Resolve now: on Windows CreateProcess would find System32\bash.exe (WSL) first.
BASH = shutil.which("bash")

# Fake gh: behaviour comes from env vars so each test sets one scenario.
#   FAKE_RUN     "<status> <conclusion>" for `gh run list --workflow validate.yml`
#   FAKE_SMOKE   the same for `--workflow blender-smoke.yml`
#   FAKE_PR      PR number for `gh api .../pulls` (empty = direct push)
#   FAKE_FILES   changed files for `gh api .../commits/SHA` or `.../compare/...`
#   FAKE_CHECKS  stdout for `gh pr checks`; FAKE_CHECKS_RC its exit code
FAKE_GH = r"""#!/usr/bin/env bash
case "$1 $2" in
  "run list")
    case " $* " in
      *" blender-smoke.yml "*) echo "${FAKE_SMOKE:-completed success}" ;;
      *) echo "${FAKE_RUN:-completed success}" ;;
    esac ;;
  "api "*/pulls) echo "${FAKE_PR:-}" ;;
  "api "*) printf '%b\n' "${FAKE_FILES:-examples/a/a.py}" ;;
  "pr checks") printf '%s' "${FAKE_CHECKS:-}"; exit "${FAKE_CHECKS_RC:-0}" ;;
  *) echo "unexpected gh $*" >&2; exit 99 ;;
esac
"""


@unittest.skipIf(BASH is None, "bash not available")
class ReleaseGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        gh = Path(self.tmp.name) / "gh"
        gh.write_text(FAKE_GH, encoding="utf-8", newline="\n")
        gh.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def gate(self, **env):
        full = dict(os.environ)
        full.update(
            PATH=self.tmp.name + os.pathsep + full.get("PATH", ""),
            GITHUB_REPOSITORY="o/r",
            SHA="abc123",
            GATE_TIMEOUT="0",
            GATE_POLL="0",
        )
        full.update(env)
        proc = subprocess.run(
            [BASH, GATE.as_posix()], env=full, capture_output=True, text=True
        )
        return proc.returncode, proc.stdout + proc.stderr

    def test_direct_push_with_green_validate_and_smoke_passes(self):
        code, out = self.gate(FAKE_PR="")
        self.assertEqual(code, 0, out)
        self.assertIn("Blender Smoke: success", out)

    def test_direct_push_with_red_smoke_blocks(self):
        code, out = self.gate(FAKE_PR="", FAKE_SMOKE="completed failure")
        self.assertEqual(code, 1)
        self.assertIn("Blender Smoke concluded 'failure'", out)

    def test_direct_push_with_no_smoke_run_times_out(self):
        code, out = self.gate(FAKE_PR="", FAKE_SMOKE="none none", SMOKE_TIMEOUT="0")
        self.assertEqual(code, 1)
        self.assertIn("Blender Smoke did not finish", out)

    def test_docs_only_direct_push_skips_smoke(self):
        code, out = self.gate(
            FAKE_PR="", FAKE_SMOKE="none none", FAKE_FILES=r"README.md\ndocs/gallery/x.html"
        )
        self.assertEqual(code, 0, out)
        self.assertIn("only smoke-ignored paths", out)

    def test_truncated_file_list_waits_for_smoke(self):
        # 300 docs paths is the API's cap: a code change may sort after them.
        many = r"\n".join(f"docs/gallery/p{i:03d}.html" for i in range(300))
        code, out = self.gate(FAKE_PR="", FAKE_SMOKE="none none", SMOKE_TIMEOUT="0",
                              FAKE_FILES=many)
        self.assertEqual(code, 1)
        self.assertIn("Blender Smoke did not finish", out)

    def test_299_docs_files_still_skip_smoke(self):
        many = r"\n".join(f"docs/gallery/p{i:03d}.html" for i in range(299))
        code, out = self.gate(FAKE_PR="", FAKE_SMOKE="none none", FAKE_FILES=many)
        self.assertEqual(code, 0, out)
        self.assertIn("only smoke-ignored paths", out)

    def test_red_validate_blocks(self):
        code, out = self.gate(FAKE_RUN="completed failure")
        self.assertEqual(code, 1)
        self.assertIn("Validate concluded 'failure'", out)

    def test_all_checks_green_passes(self):
        code, out = self.gate(FAKE_PR="7", FAKE_CHECKS="3:")
        self.assertEqual(code, 0, out)
        self.assertIn("3 checks passed", out)

    def test_failing_check_blocks(self):
        code, out = self.gate(FAKE_PR="7", FAKE_CHECKS="3:smoke=fail", FAKE_CHECKS_RC="1")
        self.assertEqual(code, 1)
        self.assertIn("smoke=fail", out)

    def test_gh_error_with_no_output_blocks(self):
        code, out = self.gate(FAKE_PR="7", FAKE_CHECKS="", FAKE_CHECKS_RC="1")
        self.assertEqual(code, 1)
        self.assertIn("could not read checks", out)

    def test_garbage_output_blocks(self):
        code, _ = self.gate(FAKE_PR="7", FAKE_CHECKS="HTTP 502 Bad Gateway")
        self.assertEqual(code, 1)

    def test_zero_checks_blocks(self):
        self.assertEqual(self.gate(FAKE_PR="7", FAKE_CHECKS="0:")[0], 1)


if __name__ == "__main__":
    unittest.main()
