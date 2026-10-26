"""Every EEVEE engine-id mapping in the tree must match the canonical one.

Legacy EEVEE was removed in Blender 4.2. EEVEE Next used the id
``BLENDER_EEVEE_NEXT`` on 4.2 through 4.5 LTS, then reclaimed the plain
``BLENDER_EEVEE`` id in 5.0. So:

    BLENDER_EEVEE      on 5.0 and above
    BLENDER_EEVEE_NEXT on 4.2 through 4.5

Why this file exists
--------------------

`tests/smoke/run_smoke.py` already asserts the mapping against the running
build, which catches a wrong *canonical* mapping. It cannot catch a wrong
*copy*: showcase and example scripts are standalone by convention, so each
one carries its own `eevee_engine_id()`. Eighty-five files in this tree
mention the id.

That is how an inverted ternary keyed on ``>= (4, 2, 0)`` — which returns
``BLENDER_EEVEE_NEXT`` on 5.x, where that id does not exist — survived in
`showcase/shipping-crate` and propagated to `showcase/iron-cauldron`. Both
raised ``TypeError`` on the ``--output`` path on 5.1 and 5.2. Smoke never
passes ``--output``, so nothing went red.

A render canary would not have caught it either. Blender's EEVEE aborts on
GPU-less runners without EGL, which is why every render in
`blender-smoke.yml` uses Cycles — and Cycles never touches the EEVEE id.

Method
------

AST, not regex. Every function that returns an EEVEE id is interpreted
twice, against a stubbed ``bpy.app.version`` of (4, 5, 11) and (5, 2, 1);
every conditional expression that yields one is evaluated the same way. The
interpreter walks the AST and never runs the repo's code (no eval or exec). Both forms — ternary and ``if``/``return`` — are handled by the
same code path, because a regex over either one misreads the other.

A deliberately inverted mapping (``examples/swatch-grid`` witnesses the
inversion by asserting the wrong-era id is rejected) must carry
``# engine-id-exempt: <reason>`` on its own line.

Exit codes: 0 clean, 1 a mapping disagrees, 2 usage.
"""
from __future__ import annotations

import ast
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOPES = ("examples", "showcase", "templates", "snippets", "scripts", "tests")
SKIP_DIRS = {".git", "__pycache__", ".scratch", "node_modules", "docs"}
# The checker states the canonical mapping itself; judging it would be circular.
SKIP_FILES = {"tests/check_engine_id.py"}

EEVEE_IDS = {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
PROBES = ((4, 5, 11), (5, 2, 1))
EXEMPT = "engine-id-exempt:"


def canonical(version):
    return "BLENDER_EEVEE" if version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def _mentions_id(node):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and sub.value in EEVEE_IDS:
            return True
    return False


def _yields_id(node):
    """True when *node* evaluates to an EEVEE id constant (possibly branching)."""
    if isinstance(node, ast.Constant):
        return node.value in EEVEE_IDS
    if isinstance(node, ast.IfExp):
        return _yields_id(node.body) and _yields_id(node.orelse)
    return False


def _is_resolver(fn):
    """True when *fn* does nothing but resolve an id from the version.

    Deliberately narrow. A ``main()`` that happens to mention the id
    somewhere is not a resolver, and compiling and calling it would need
    the whole module's imports. Only a body of returns and version
    branches qualifies, which is the shape every copy in the tree uses.
    """
    returns = []

    def walk(stmts):
        for st in stmts:
            if isinstance(st, ast.Return):
                if st.value is None or not _yields_id(st.value):
                    return False
                returns.append(st)
            elif isinstance(st, ast.If):
                if not walk(st.body) or not walk(st.orelse):
                    return False
            elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
                continue  # docstring
            elif isinstance(st, ast.Pass):
                continue
            else:
                return False
        return True

    return walk(fn.body) and bool(returns) and not fn.args.args


# Names a resolver may branch on, as functions of the stubbed version.
_NAMES = {
    "IS_5X": lambda version: version >= (5, 0, 0),
    "IS_5_X": lambda version: version >= (5, 0, 0),
}
_COMPARE = {
    ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
}


def _value(node, version):
    """Interpret the small expression language resolvers use.

    Constants, tuples, ``bpy.app.version`` (indexed or sliced), the IS_5X
    flags, comparisons, and/or/not, and conditional expressions. Anything
    else raises ValueError, which the caller reports as "not resolvable".
    The repo's own code is walked, never executed, so the check needs no
    eval/exec (HOL's plugin scanner rejects dynamic execution, #510).
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(_value(e, version) for e in node.elts)
    if isinstance(node, ast.Name) and node.id in _NAMES:
        return _NAMES[node.id](version)
    if (isinstance(node, ast.Attribute) and node.attr == "version"
            and isinstance(node.value, ast.Attribute) and node.value.attr == "app"
            and isinstance(node.value.value, ast.Name) and node.value.value.id == "bpy"):
        return version
    if isinstance(node, ast.Subscript):
        seq = _value(node.value, version)
        if isinstance(node.slice, ast.Slice):
            lo, hi, step = (None if p is None else _value(p, version)
                            for p in (node.slice.lower, node.slice.upper, node.slice.step))
            return seq[lo:hi:step]
        return seq[_value(node.slice, version)]
    if isinstance(node, ast.Compare):
        left = _value(node.left, version)
        for op, comp in zip(node.ops, node.comparators):
            right = _value(comp, version)
            if type(op) not in _COMPARE:
                raise ValueError(f"unsupported comparison {type(op).__name__}")
            if not _COMPARE[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        vals = (_value(v, version) for v in node.values)
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _value(node.operand, version)
    if isinstance(node, ast.IfExp):
        branch = node.body if _value(node.test, version) else node.orelse
        return _value(branch, version)
    raise ValueError(f"unsupported expression {ast.unparse(node)!r}")


def _run(stmts, version):
    """Interpret a resolver body (returns, version branches, docstrings)."""
    for st in stmts:
        if isinstance(st, ast.Return):
            return True, _value(st.value, version)
        if isinstance(st, ast.If):
            done, val = _run(st.body if _value(st.test, version) else st.orelse, version)
            if done:
                return True, val
    return False, None


def _evaluate(node, version):
    """Return the id this node yields on *version*."""
    if isinstance(node, ast.FunctionDef):
        done, val = _run(node.body, version)
        if not done:
            raise ValueError(f"{node.name}() falls off the end without returning")
        return val
    return _value(node, version)


def _exempt_reason(lines, lineno):
    line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
    if EXEMPT in line:
        return line.split(EXEMPT, 1)[1].strip() or "(no reason given)"
    return None


def check_file(path):
    """(checked, exempted, failures) for one file."""
    src = io.open(path, encoding="utf-8", errors="ignore").read()
    if not any(i in src for i in EEVEE_IDS):
        return 0, 0, []
    lines = src.split("\n")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return 0, 0, [(path, getattr(exc, "lineno", 0), f"unparseable: {exc}")]

    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    checked = exempted = 0
    failures = []
    seen = set()

    # Functions first, so a ternary inside one is not also judged alone.
    covered_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and _mentions_id(node) and _is_resolver(node):
            for sub in ast.walk(node):
                if hasattr(sub, "lineno"):
                    covered_lines.add(sub.lineno)
            reason = _exempt_reason(lines, node.lineno)
            if reason:
                exempted += 1
                print(f"  exempt  {rel}:{node.lineno} {node.name}() - {reason}")
                continue
            try:
                got = {v: _evaluate(node, v) for v in PROBES}
            except Exception as exc:
                failures.append(
                    (rel, node.lineno, f"{node.name}() not resolvable: {exc}")
                )
                continue
            checked += 1
            bad = {v: got[v] for v in PROBES if got[v] != canonical(v)}
            if bad:
                detail = " ".join(
                    f"{'.'.join(map(str, v))}->{got[v]} (want {canonical(v)})"
                    for v in bad
                )
                failures.append((rel, node.lineno, f"{node.name}() {detail}"))
            seen.add(node.lineno)

    for node in ast.walk(tree):
        if not isinstance(node, ast.IfExp) or not _mentions_id(node):
            continue
        if node.lineno in covered_lines:
            continue
        reason = _exempt_reason(lines, node.lineno)
        if reason:
            exempted += 1
            print(f"  exempt  {rel}:{node.lineno} conditional - {reason}")
            continue
        try:
            got = {v: _evaluate(node, v) for v in PROBES}
        except Exception as exc:
            failures.append((rel, node.lineno, f"conditional not resolvable: {exc}"))
            continue
        checked += 1
        bad = {v: got[v] for v in PROBES if got[v] != canonical(v)}
        if bad:
            detail = " ".join(
                f"{'.'.join(map(str, v))}->{got[v]} (want {canonical(v)})"
                for v in bad
            )
            failures.append((rel, node.lineno, f"conditional {detail}"))
    return checked, exempted, failures


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        print(__doc__.strip().split("\n")[0], file=sys.stderr)
        print("usage: python tests/check_engine_id.py", file=sys.stderr)
        return 2

    total = exempt_total = 0
    failures = []
    files = 0
    for scope in SCOPES:
        base = os.path.join(ROOT, scope)
        if not os.path.isdir(base):
            continue
        for root, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in sorted(names):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                if os.path.relpath(path, ROOT).replace("\\", "/") in SKIP_FILES:
                    continue
                checked, exempted, fails = check_file(path)
                if checked or exempted or fails:
                    files += 1
                total += checked
                exempt_total += exempted
                failures.extend(fails)

    if failures:
        print(
            f"\n{len(failures)} engine-id mapping(s) disagree with the canonical one "
            "(BLENDER_EEVEE on 5.0+, BLENDER_EEVEE_NEXT on 4.2-4.5):",
            file=sys.stderr,
        )
        for rel, line, detail in failures:
            print(f"  ERROR: {rel}:{line} {detail}", file=sys.stderr)
        print(
            "\nA deliberately inverted mapping must carry "
            f"'# {EXEMPT} <reason>' on its own line.",
            file=sys.stderr,
        )
        return 1

    print(
        f"engine-id checks passed: {total} mapping(s) across {files} file(s), "
        f"{exempt_total} exempt."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
