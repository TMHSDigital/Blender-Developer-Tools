"""The extension template's shipped CI workflow keeps its contract (#531). No Blender.

GitHub never runs templates/extension-addon-template/.github/workflows/blender.yml
from inside this repository, so a broken edit would only surface in a user's
copy. blender-smoke.yml runs the workflow's build and register steps against the
template; this pins the workflow file itself: both LTS series, the build and
register steps, a verified download, and actions pinned to the same commit SHAs
this repository uses.

    python tests/test_template_ci.py -v
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "templates" / "extension-addon-template"
WORKFLOW = TEMPLATE / ".github" / "workflows" / "blender.yml"
USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)@(\S+)", re.M)


class TemplateWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.wf = yaml.safe_load(cls.text)
        cls.job = cls.wf["jobs"]["blender"]
        cls.runs = "\n".join(s.get("run", "") for s in cls.job["steps"])

    def test_covers_both_lts_series(self):
        self.assertEqual(set(self.job["strategy"]["matrix"]["series"]), {"4.5", "5.2"})

    def test_builds_and_runs_the_register_check(self):
        self.assertIn("--command extension build", self.runs)
        self.assertIn("tests/check_register.py", self.runs)
        self.assertTrue((TEMPLATE / "tests" / "check_register.py").is_file())

    def test_download_is_verified(self):
        self.assertIn("sha256sum -c", self.runs)

    def test_read_only_token(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read"})

    def test_actions_pinned_to_the_repo_shas(self):
        repo_pins = {}
        for p in (REPO / ".github" / "workflows").glob("*.yml"):
            for action, ref in USES.findall(p.read_text(encoding="utf-8")):
                repo_pins.setdefault(action, set()).add(ref)
        uses = USES.findall(self.text)
        self.assertTrue(uses)
        for action, ref in uses:
            with self.subTest(action=action):
                self.assertRegex(ref, r"^[0-9a-f]{40}$")
                self.assertIn(ref, repo_pins.get(action, set()),
                              f"{action}@{ref} differs from this repo's pin")

    def test_manifest_keeps_ci_files_out_of_the_package(self):
        import tomllib
        with open(TEMPLATE / "blender_manifest.toml", "rb") as fh:
            excl = tomllib.load(fh)["build"]["paths_exclude_pattern"]
        for pattern in ("/.github/", "/tests/"):
            self.assertIn(pattern, excl)


if __name__ == "__main__":
    unittest.main()
