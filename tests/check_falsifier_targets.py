"""A falsifier must fail the budget it targets, not an earlier check.

A falsifier that exits non-zero on some *earlier* budget proves nothing
about the budget it was built for. The exit code is right there to catch
it, so this makes the flag -> budget -> exit-code mapping machine-checked
instead of prose.

Worked example, from the run that motivated this file: `stone-archway`'s
arch falsifier began as ``--flat-arch``, laying the voussoirs as a flat
lintel. A lintel is 0.62 m shorter than the arch, so it tripped the
bounding-box budget (exit 8) and never reached the intrados circle fit
(exit 19) it existed to break. It was replaced by ``--off-circle``, which
keeps the angles, joints, materials, triangle count and envelope
identical and wanders only the intrados radius. Four other falsifiers
needed the same treatment in the same run.

The fix is always to change the model or the falsifier. Never widen a
band so an ill-aimed falsifier lands.

Two modes
---------

**Static (default, no Blender).** Reads each piece's README and script and
asserts they agree:

1. every falsifier flag in the README table is a real argparse flag;
2. every declared exit code appears in that README's exit-code table;
3. every falsifier row names the budget it targets, in its own column;
4. every falsifier-shaped flag in the script is documented.

**Runtime (``--run BLENDER``).** Executes each falsifier and asserts the
*observed* exit equals the declared one. This is the mode that catches a
falsifier tripping an earlier check. It costs one Blender launch per
falsifier: measured at 276 s for the whole showcase tree on one version
(160 falsifiers, 25 pieces, Blender 5.2.1). That is an authoring and cron
tool, not a per-PR smoke step.

Exit codes: 0 clean, 1 a mapping disagrees, 2 usage.
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOWCASE = os.path.join(ROOT, "showcase")

# Pieces that predate the falsifier-table convention. Tracked for backfill;
# a NEW piece without a table is an error, not an entry here. Empty since
# cart, hay-bale and stone-well gained tables (#203): a piece left listed
# here after its table lands would be skipped silently if the table were
# later deleted.
KNOWN_UNDOCUMENTED: set[str] = set()

# Flags that select a code path rather than break a contract. Per
# CONTRIBUTING.md these are explicitly not falsifiers.
NOT_FALSIFIERS = {
    "--output", "--engine", "--api", "--check-pixels", "--obj",
    "--samples", "--width", "--height", "--force-run", "--expect-sidecar",
    "--seed", "--quality", "--verbose", "--no-render",
}

FLAG_RE = re.compile(r"`?(--[a-z0-9][a-z0-9-]*)`?")


def _tables(text):
    """Every markdown table as (headers, rows-of-cells)."""
    out = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|") and i + 1 < len(lines) and re.match(
            r"^\|[\s:|-]+\|$", lines[i + 1].strip()
        ):
            headers = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            out.append((headers, rows))
            i = j
        else:
            i += 1
    return out


def _column(headers, *patterns):
    for idx, h in enumerate(headers):
        low = h.lower()
        if any(re.search(p, low) for p in patterns):
            return idx
    return None


def parse_readme(path):
    """(falsifiers {flag: (exit, target)}, exit_table {code: meaning})."""
    text = io.open(path, encoding="utf-8").read()
    falsifiers, exits = {}, {}
    for headers, rows in _tables(text):
        code_col = _column(headers, r"^exit$", r"exit code", r"^code$")
        if code_col is None:
            continue
        flag_col = _column(headers, r"falsifier", r"^flag$")
        if flag_col is not None:
            # The remaining column is the declared target budget. Every
            # falsifier has to say what it aims at; that is the whole point.
            target_col = next(
                (i for i in range(len(headers)) if i not in (flag_col, code_col)),
                None,
            )
            for r in rows:
                if len(r) <= max(flag_col, code_col):
                    continue
                m = FLAG_RE.search(r[flag_col])
                if not m or not r[code_col].strip().strip("`").isdigit():
                    continue
                target = ""
                if target_col is not None and len(r) > target_col:
                    target = r[target_col].strip()
                falsifiers[m.group(1)] = (
                    int(r[code_col].strip().strip("`")), target
                )
            continue
        # exit-code table: code column plus a meaning column
        mean_col = _column(headers, r"meaning", r"description")
        if mean_col is None:
            mean_col = 1 if len(headers) > 1 else None
        if mean_col is None:
            continue
        for r in rows:
            if len(r) <= max(code_col, mean_col):
                continue
            c = r[code_col].strip().strip("`")
            if c.isdigit():
                exits[int(c)] = r[mean_col]
    return falsifiers, exits


def script_flags(path):
    """store_true argparse flags declared in the script."""
    src = io.open(path, encoding="utf-8").read()
    flags = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return flags
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "add_argument"):
            continue
        store_true = any(
            kw.arg == "action"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value == "store_true"
            for kw in node.keywords
        )
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value.startswith("--") and store_true:
                    flags.add(arg.value)
    return flags


def piece_paths():
    for name in sorted(os.listdir(SHOWCASE)):
        d = os.path.join(SHOWCASE, name)
        if not os.path.isdir(d):
            continue
        readme = os.path.join(d, "README.md")
        script = os.path.join(d, name.replace("-", "_") + ".py")
        if os.path.isfile(readme) and os.path.isfile(script):
            yield name, readme, script


def check_static():
    failures, checked, pieces = [], 0, 0
    undocumented_only = []
    undocumented_pieces = []
    for name, readme, script in piece_paths():
        falsifiers, exits = parse_readme(readme)
        if not falsifiers:
            if name in KNOWN_UNDOCUMENTED:
                undocumented_pieces.append(name)
                continue
            failures.append(
                (name, "no falsifier table mapping flag to target budget to "
                       "exit code")
            )
            continue
        pieces += 1
        flags = script_flags(script)
        for flag, (code, target) in sorted(falsifiers.items()):
            checked += 1
            if flag not in flags:
                failures.append(
                    (name, f"{flag} documented but not an argparse flag")
                )
                continue
            if code not in exits:
                failures.append(
                    (name, f"{flag} declares exit {code}, absent from the "
                           "exit-code table")
                )
                continue
            if not target:
                failures.append(
                    (name, f"{flag} names no target budget in its row")
                )
        for flag in sorted(flags - set(falsifiers) - NOT_FALSIFIERS):
            undocumented_only.append((name, flag))
    return failures, undocumented_only, checked, pieces, undocumented_pieces


def check_runtime(blender, only=None):
    failures, checked = [], 0
    for name, readme, script in piece_paths():
        if only and name not in only:
            continue
        falsifiers, _exits = parse_readme(readme)
        for flag, (want, _target) in sorted(falsifiers.items()):
            checked += 1
            proc = subprocess.run(
                [blender, "--background", "--python", script, "--", flag],
                capture_output=True,
            )
            got = proc.returncode
            status = "ok" if got == want else "MISMATCH"
            print(f"  {status:9} {name} {flag}: want {want}, got {got}")
            if got != want:
                failures.append(
                    (name, f"{flag} declared exit {want} but exited {got}")
                )
    return failures, checked


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--run", metavar="BLENDER", default=None,
                   help="also execute each falsifier with this Blender binary")
    p.add_argument("--only", action="append", default=None,
                   help="limit the runtime mode to these piece names")
    args = p.parse_args(argv)

    failures, undocumented, checked, pieces, skipped = check_static()
    for name, flag in undocumented:
        failures.append((name, f"{flag} looks like a falsifier but is not in "
                               "the falsifier table"))

    if skipped:
        print(
            f"note: {len(skipped)} piece(s) predate the falsifier table and are "
            f"tracked for backfill: {', '.join(sorted(skipped))}"
        )

    if args.run:
        print(f"runtime falsifier sweep with {args.run}")
        rt_failures, rt_checked = check_runtime(args.run, set(args.only or []) or None)
        failures.extend(rt_failures)
        checked += rt_checked

    if failures:
        print(f"\n{len(failures)} falsifier mapping problem(s):", file=sys.stderr)
        for name, detail in failures:
            print(f"  ERROR: showcase/{name}: {detail}", file=sys.stderr)
        print(
            "\nA falsifier must fail the budget it targets. Fix a collision by "
            "changing the model or the falsifier, never by widening a band.",
            file=sys.stderr,
        )
        return 1

    print(
        f"falsifier-target checks passed: {checked} falsifier(s) across "
        f"{pieces} showcase piece(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
