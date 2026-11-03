"""Static half of the #447 content smoke (no Blender).

- tests/smoke/snippet_checks.py has exactly one entry per snippets/*.py, each
  with a ``check`` and a ``falsify`` (old, new) whose ``old`` occurs in the
  snippet, so tests/smoke/run_content.py can never silently skip a snippet.
- Every ```python block in skills/*/SKILL.md compiles. Blocks tagged with a
  ``<!-- smoke: run -->`` line are also executed by run_content.py in Blender.
- Ratchet (#525, tests/smoke/skill_blocks.json): at least ``floor`` blocks are
  tagged, and every skill has a tagged block or a ``compile_only`` entry saying
  why its blocks cannot run standalone and which example proves it instead.

Exit 1 with one ::error:: line per problem.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests", "smoke"))
sys.dont_write_bytecode = True
from snippet_checks import CASES  # noqa: E402

FENCE = re.compile(r"^```python[ \t]*\r?\n(.*?)\r?\n```", re.M | re.S)
TAG = re.compile(r"^<!-- smoke: run -->[ \t]*\r?\n```python", re.M)


def check(root=ROOT, cases=None):
    """(errors, skill python blocks, tagged blocks) for a repo root."""
    cases = CASES if cases is None else cases
    errors = []
    snippets = {os.path.basename(p) for p in glob.glob(os.path.join(root, "snippets", "*.py"))}
    for name in sorted(snippets - set(cases)):
        errors.append(f"snippets/{name} has no entry in tests/smoke/snippet_checks.py")
    for name in sorted(set(cases) - snippets):
        errors.append(f"tests/smoke/snippet_checks.py names snippets/{name}, which does not exist")
    for name in sorted(set(cases) & snippets):
        case = cases[name]
        unknown = set(case) - {"setup", "check", "falsify"}
        if unknown:
            errors.append(f"{name}: unknown keys {sorted(unknown)}")
        if not case.get("check"):
            errors.append(f"{name}: no check")
        fals = case.get("falsify")
        if not (isinstance(fals, tuple) and len(fals) == 2 and fals[0] != fals[1]):
            errors.append(f"{name}: falsify must be an (old, new) pair that changes something")
            continue
        with open(os.path.join(root, "snippets", name), encoding="utf-8") as fh:
            if fals[0] not in fh.read():
                errors.append(f"{name}: falsify string {fals[0]!r} is not in the snippet")

    blocks = tagged = 0
    per_skill = {}
    for path in sorted(glob.glob(os.path.join(root, "skills", "*", "SKILL.md"))):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        n_tagged = len(TAG.findall(text))
        tagged += n_tagged
        per_skill[os.path.basename(os.path.dirname(path))] = n_tagged
        for m in FENCE.finditer(text):
            blocks += 1
            start = text.count("\n", 0, m.start(1)) + 1
            try:
                compile(m.group(1), rel, "exec")
            except SyntaxError as e:
                errors.append(f"{rel}:{start + (e.lineno or 1) - 1}: python block does not compile: {e.msg}")
    errors += check_ratchet(root, per_skill, tagged)
    return errors, blocks, tagged


def check_ratchet(root, per_skill, tagged):
    path = os.path.join(root, "tests", "smoke", "skill_blocks.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    floor, allow = cfg["floor"], cfg.get("compile_only", {})
    errors = []
    if tagged < floor:
        errors.append(f"only {tagged} SKILL.md blocks are tagged <!-- smoke: run -->, below the "
                      f"floor of {floor} in tests/smoke/skill_blocks.json")
    for skill, n in sorted(per_skill.items()):
        if n == 0 and not allow.get(skill, "").strip():
            errors.append(f"skills/{skill}: no block is tagged <!-- smoke: run --> and "
                          "tests/smoke/skill_blocks.json gives no compile_only reason")
        if n and skill in allow:
            errors.append(f"skills/{skill} has a tagged block; drop its compile_only entry "
                          "in tests/smoke/skill_blocks.json")
    for skill in sorted(set(allow) - set(per_skill)):
        errors.append(f"tests/smoke/skill_blocks.json: compile_only names unknown skill {skill!r}")
    return errors


def main():
    errors, blocks, tagged = check()
    for e in errors:
        print(f"::error::{e}")
    if errors:
        return 1
    print(f"{len(CASES)} snippets catalogued with falsifiers; {blocks} skill python blocks compile, "
          f"{tagged} tagged for execution (ratchet in tests/smoke/skill_blocks.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
