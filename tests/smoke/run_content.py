"""Run the shipped snippets and the tagged SKILL.md blocks in place (#447).

    blender --background --factory-startup --python tests/smoke/run_content.py -- [--only NAME] [--no-falsify]

Unlike run_smoke.py, nothing here is a copy: every snippet is read from
snippets/ and every block from skills/*/SKILL.md, so editing either is what
gets tested.

- Snippets: each entry in tests/smoke/snippet_checks.py runs the snippet, then
  its check, in a fresh factory scene (PASS), then reruns it with the entry's
  ``falsify`` edit applied, which must make the check fail (FALSIFIED).
- Skill blocks: a ```python fence directly under a ``<!-- smoke: run -->``
  line is exec'd as-is in a fresh factory scene; it carries its own asserts.

Prints one line per case and a summary; exits 1 on any failure.
"""
import argparse
import glob
import json
import os
import re
import struct
import sys
import tempfile
import traceback

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
from snippet_checks import CASES  # noqa: E402

TAG = re.compile(r"^<!-- smoke: run -->[ \t]*\r?\n```python[ \t]*\r?\n(.*?)\r?\n```", re.M | re.S)
SCRATCH = tempfile.mkdtemp(prefix="bdt-content-")


def tmp(name):
    return os.path.join(SCRATCH, name)


def glb_json(path):
    with open(path, "rb") as fh:
        magic, _version, _length = struct.unpack("<4sII", fh.read(12))
        assert magic == b"glTF", f"{path} is not a GLB"
        chunk_len, chunk_type = struct.unpack("<I4s", fh.read(8))
        assert chunk_type == b"JSON", chunk_type
        return json.loads(fh.read(chunk_len))


def fresh_scene():
    bpy.ops.wm.read_factory_settings()
    # Driver expressions that call registered functions need trusted Python;
    # factory settings reset this to off.
    bpy.context.preferences.filepaths.use_scripts_auto_execute = True


def run_snippet(name, source, case):
    """Exec the snippet then its check; return None on pass, else the error line."""
    fresh_scene()
    path = os.path.join(REPO, "snippets", name)
    ns = {"__name__": "snippet_" + name[:-3].replace("-", "_"), "__file__": path,
          "__package__": "bl_ext.user_default.bdt_content_smoke",
          "bpy": bpy, "np": np, "tmp": tmp, "glb_json": glb_json}
    try:
        if case.get("setup"):
            exec(compile(case["setup"], f"{name}:setup", "exec"), ns)
        exec(compile(source, path, "exec"), ns)
        exec(compile(case["check"], f"{name}:check", "exec"), ns)
    except Exception as e:  # noqa: BLE001 -- any failure is the result
        tb = traceback.extract_tb(e.__traceback__)[-1]
        return f"{type(e).__name__}: {e} ({os.path.basename(tb.filename)}:{tb.lineno})"
    return None


def run_block(label, code):
    fresh_scene()
    try:
        exec(compile(code, label, "exec"), {"__name__": "__main__"})
    except Exception as e:  # noqa: BLE001
        tb = traceback.extract_tb(e.__traceback__)[-1]
        return f"{type(e).__name__}: {e} (line {tb.lineno})"
    return None


def skill_blocks():
    for path in sorted(glob.glob(os.path.join(REPO, "skills", "*", "SKILL.md"))):
        text = open(path, encoding="utf-8").read()
        skill = os.path.basename(os.path.dirname(path))
        for i, m in enumerate(TAG.finditer(text), 1):
            line = text.count("\n", 0, m.start(1)) + 1
            yield f"{skill}#{i} (SKILL.md:{line})", m.group(1)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run only cases whose name contains this")
    ap.add_argument("--no-falsify", action="store_true")
    args = ap.parse_args(argv)
    print(f"run_content on Blender {bpy.app.version_string}")

    results = []  # (kind, name, outcome, detail)
    for name in sorted(CASES):
        if args.only and args.only not in name:
            continue
        case = CASES[name]
        source = open(os.path.join(REPO, "snippets", name), encoding="utf-8").read()
        err = run_snippet(name, source, case)
        results.append(("snippet", name, "FAIL" if err else "PASS", err or ""))
        if args.no_falsify or err:
            continue
        old, new = case["falsify"]
        if old not in source:
            results.append(("falsifier", name, "FAIL", f"{old!r} not in source"))
            continue
        err = run_snippet(name, source.replace(old, new), case)
        results.append(("falsifier", name, "FALSIFIED" if err else "FAIL",
                        err or f"check still passed with {old!r} -> {new!r}"))

    for label, code in skill_blocks():
        if args.only and args.only not in label:
            continue
        err = run_block(label, code)
        results.append(("skill-block", label, "FAIL" if err else "PASS", err or ""))

    for kind, name, outcome, detail in results:
        print(f"{outcome:9}  {kind:11}  {name}" + (f"  -- {detail}" if detail else ""))
    failed = [r for r in results if r[2] == "FAIL"]
    count = lambda k: sum(1 for r in results if r[0] == k)  # noqa: E731
    print(f"run_content: {count('snippet')} snippets, {count('falsifier')} falsifiers, "
          f"{count('skill-block')} skill blocks; {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
