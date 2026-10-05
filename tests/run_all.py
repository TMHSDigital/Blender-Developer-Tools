#!/usr/bin/env python3
"""Run every Validate check locally in one command (#364). No Blender needed.

    pip install -r requirements-dev.txt
    python tests/run_all.py            # all checks, summary at the end
    python tests/run_all.py -k gallery # only checks whose name contains "gallery"

It runs every tests/check_*.py and tests/test_*.py, the smoke-harness tests,
the generator --check modes, and the Python heredoc checks that live inline in
.github/workflows/validate.yml (extracted from the workflow at run time, so
there is one copy of each). It does not run Blender, `gh`, or the site build.
Exit 0 only if everything passed.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def inline_checks() -> list[tuple[str, str]]:
    """(name, python source) for each `python3 << 'PYEOF'` step in validate.yml."""
    import yaml

    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8"))
    out = []
    for job in wf["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if "<< 'PYEOF'" in run:
                body = run.split("<< 'PYEOF'\n", 1)[1].rsplit("PYEOF", 1)[0]
                out.append((f"validate.yml: {step.get('name', '?')}", textwrap.dedent(body)))
    return out


GALLERY_DRIFT = """
import subprocess, sys
subprocess.run([sys.executable, "scripts/build_gallery.py"], check=True, capture_output=True)
diff = subprocess.run(["git", "status", "--porcelain", "docs/gallery"], capture_output=True, text=True).stdout
if diff.strip():
    sys.exit("docs/gallery/ is stale; commit the regenerated pages: " + diff)
"""

# check_site_links reads the built landing page, which is not committed.
SITE_BUILD = """
import subprocess, sys
subprocess.run([sys.executable, "scripts/site/build_site.py", "--repo-root", ".", "--out", "docs"],
               check=True)
"""


def commands() -> list[tuple[str, list[str] | str]]:
    py = sys.executable
    cmds: list[tuple[str, list[str] | str]] = [
        ("build landing page (for check_site_links)", SITE_BUILD),
        ("committed gallery matches its generator", GALLERY_DRIFT),
    ]
    for path in sorted((ROOT / "tests").glob("check_*.py")):
        cmds.append((path.name, [py, str(path)]))
    for path in [*sorted((ROOT / "tests").glob("test_*.py")), ROOT / "tests" / "smoke" / "test_harness.py"]:
        cmds.append((path.name, [py, str(path)]))
    cmds.append(("build_claude_rules --check", [py, str(ROOT / "scripts" / "build_claude_rules.py"), "--check"]))
    cmds.append(("build_plugin_dist --check", [py, str(ROOT / "scripts" / "build_plugin_dist.py"), "--check"]))
    cmds.append(("build_examples_index --check", [py, str(ROOT / "scripts" / "build_examples_index.py"), "--check"]))
    cmds += inline_checks()
    return cmds


def run(name: str, cmd: list[str] | str) -> bool:
    if isinstance(cmd, str):  # inline heredoc source
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
            fh.write(cmd)
        argv = [sys.executable, fh.name]
    else:
        argv = cmd
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    ok = proc.returncode == 0
    print(f"{'PASS' if ok else 'FAIL'}  {name}", flush=True)
    if not ok:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-15:]
        print("\n".join("      " + line for line in tail), flush=True)
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-k", default="", help="only run checks whose name contains this")
    args = ap.parse_args(argv)
    todo = [(n, c) for n, c in commands() if args.k.lower() in n.lower()]
    failed = [n for n, c in todo if not run(n, c)]
    print(f"\n{len(todo) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
