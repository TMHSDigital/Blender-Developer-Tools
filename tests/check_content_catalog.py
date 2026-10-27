"""Static half of the #447 content smoke (no Blender).

- tests/smoke/snippet_checks.py has exactly one entry per snippets/*.py, each
  with a ``check`` and a ``falsify`` (old, new) whose ``old`` occurs in the
  snippet, so tests/smoke/run_content.py can never silently skip a snippet.
- Every ```python block in skills/*/SKILL.md compiles. Blocks tagged with a
  ``<!-- smoke: run -->`` line are also executed by run_content.py in Blender;
  this reports how many are tagged.

Exit 1 with one ::error:: line per problem.
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests", "smoke"))
sys.dont_write_bytecode = True
from snippet_checks import CASES  # noqa: E402

FENCE = re.compile(r"^```python[ \t]*\r?\n(.*?)\r?\n```", re.M | re.S)
TAG = re.compile(r"^<!-- smoke: run -->[ \t]*\r?\n```python", re.M)


def main():
    errors = []
    snippets = {os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "snippets", "*.py"))}
    for name in sorted(snippets - set(CASES)):
        errors.append(f"snippets/{name} has no entry in tests/smoke/snippet_checks.py")
    for name in sorted(set(CASES) - snippets):
        errors.append(f"tests/smoke/snippet_checks.py names snippets/{name}, which does not exist")
    for name in sorted(set(CASES) & snippets):
        case = CASES[name]
        unknown = set(case) - {"setup", "check", "falsify"}
        if unknown:
            errors.append(f"{name}: unknown keys {sorted(unknown)}")
        if not case.get("check"):
            errors.append(f"{name}: no check")
        fals = case.get("falsify")
        if not (isinstance(fals, tuple) and len(fals) == 2 and fals[0] != fals[1]):
            errors.append(f"{name}: falsify must be an (old, new) pair that changes something")
            continue
        with open(os.path.join(ROOT, "snippets", name), encoding="utf-8") as fh:
            if fals[0] not in fh.read():
                errors.append(f"{name}: falsify string {fals[0]!r} is not in the snippet")

    blocks = tagged = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))):
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        tagged += len(TAG.findall(text))
        for m in FENCE.finditer(text):
            blocks += 1
            start = text.count("\n", 0, m.start(1)) + 1
            try:
                compile(m.group(1), rel, "exec")
            except SyntaxError as e:
                errors.append(f"{rel}:{start + (e.lineno or 1) - 1}: python block does not compile: {e.msg}")

    for e in errors:
        print(f"::error::{e}")
    if errors:
        return 1
    print(f"{len(CASES)} snippets catalogued with falsifiers; {blocks} skill python blocks compile, "
          f"{tagged} tagged for execution")
    return 0


if __name__ == "__main__":
    sys.exit(main())
