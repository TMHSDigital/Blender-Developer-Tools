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

AST, not regex. Every function that returns an EEVEE id is compiled and
*called* twice, against a stubbed ``bpy.app.version`` of (4, 5, 11) and
(5, 2, 1); every conditional expression that yields one is evaluated the
same way. Both forms — ternary and ``if``/``return`` — are handled by the
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


class _App:
    def __init__(self, version):
        self.version = version


class _Bpy:
    def __init__(self, version):
        self.app = _App(version)


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


def _namespace(version):
    return {
        "bpy": _Bpy(version),
        "IS_5X": version >= (5, 0, 0),
        "IS_5_X": version >= (5, 0, 0),
        "__builtins__": __builtins__,
    }


def _evaluate(node, version):
    """Return the id this node yields on *version*."""
    ns = _namespace(version)
    if isinstance(node, ast.FunctionDef):
        mod = ast.Module(body=[node], type_ignores=[])
        ast.fix_missing_locations(mod)
        exec(compile(mod, "<engine-id>", "exec"), ns)
        return ns[node.name]()
    expr = ast.Expression(body=node)
    ast.fix_missing_locations(expr)
    return eval(compile(expr, "<engine-id>", "eval"), ns)


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
