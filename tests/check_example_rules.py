#!/usr/bin/env python3
"""Examples and showcase scripts must follow the repo's own rules (#400).

Agents copy these scripts (bmesh-gear is the anatomy every new example
starts from), so a script that breaks a rule teaches the anti-pattern. Two
rules are checked statically over examples/, showcase/ and templates/
(templates also get prefer-data-over-ops-in-loops, see below):

- use-foreach-set-for-bulk-data: a `for x in <...>.polygons` or
  `for x in <...>.vertices` loop that assigns to an attribute of `x`. Those two
  collection names exist only on Mesh (BMesh uses faces/verts), so a hit is a
  per-element RNA write, never bmesh code. Use foreach_set instead.
- type-annotate-props-and-defend-context: `name = bpy.context.active_object`
  (or `context.active_object`) not followed directly by `if name is None`.

A deliberate exception carries a marker comment on the `for` line, or the
line just above it, that says why:

    # foreach-exempt: conditional per-face material ids on a 12-face cap

    python tests/check_example_rules.py      (exit 0 ok, 1 on a violation)
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MESH_ONLY = {"polygons", "vertices"}
MARKER = "# foreach-exempt:"


def scripts(root: Path) -> list[Path]:
    return sorted([*root.glob("examples/*/*.py"), *root.glob("showcase/*/*.py"),
                   *template_scripts(root)])


# --- templates/ scan and prefer-data-over-ops-in-loops (#468) ---------------
#
# Templates are copy-paste starters, so they get the two rules above plus
# prefer-data-over-ops-in-loops: a `for` loop whose body reaches a
# bpy.ops.object.* call, directly or through functions defined in the same
# file. The headless template applied a modifier per object that way. Examples
# are not held to it: some loop per part over operators with no data-API
# equivalent (uv.smart_project). Exempt a loop with a marker on the `for` line
# or the line above:
#
#     # ops-loop-exempt: one export per LOD file; export has no data API

OPS_MARKER = "# ops-loop-exempt:"
OBJECT_OPS = "bpy.ops.object."


def template_scripts(root: Path) -> list[Path]:
    return sorted(root.glob("templates/*/*.py"))


def _object_ops_calls(node: ast.AST) -> list[str]:
    return [ast.unparse(c.func) for c in ast.walk(node)
            if isinstance(c, ast.Call) and ast.unparse(c.func).startswith(OBJECT_OPS)]


def _reaches_object_ops(tree: ast.Module) -> dict[str, str]:
    """Same-file function name -> the bpy.ops.object call it reaches."""
    funcs = {f.name: f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)}
    reach: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for name, fn in funcs.items():
            if name in reach:
                continue
            direct = _object_ops_calls(fn)
            hit = direct[0] if direct else next(
                (reach[c.func.id] for c in ast.walk(fn) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Name) and c.func.id in reach), None)
            if hit:
                reach[name] = hit
                changed = True
    return reach


def check_ops_in_loops(path: Path, root: Path) -> list[str]:
    rel = path.relative_to(root).as_posix()
    src = path.read_text(encoding="utf-8")
    lines = src.split("\n")
    tree = ast.parse(src)
    reach = _reaches_object_ops(tree)
    errors = []
    for loop in ast.walk(tree):
        if not isinstance(loop, ast.For):
            continue
        here = lines[loop.lineno - 1]
        above = lines[loop.lineno - 2] if loop.lineno >= 2 else ""
        if OPS_MARKER in here or above.strip().startswith(OPS_MARKER):
            continue
        body = ast.Module(body=loop.body, type_ignores=[])
        hits = _object_ops_calls(body) + [
            f"{c.func.id}() -> {reach[c.func.id]}" for c in ast.walk(body)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in reach]
        if hits:
            errors.append(f"{rel}:{loop.lineno}: loop over {ast.unparse(loop.iter)} calls "
                          f"{hits[0]} per iteration; use bpy.data / bmesh or one "
                          f"operator call for the whole set (rule "
                          f"prefer-data-over-ops-in-loops) or mark '{OPS_MARKER} <why>'")
    return errors


def writes_loop_var(loop: ast.For) -> bool:
    name = loop.target.id
    for node in ast.walk(ast.Module(body=loop.body, type_ignores=[])):
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else [])
        for tgt in targets:
            base = tgt
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name) and base.id == name and tgt is not base:
                return True
    return False


def exempt(lines: list[str], lineno: int) -> bool:
    here = lines[lineno - 1]
    above = lines[lineno - 2] if lineno >= 2 else ""
    return MARKER in here or above.strip().startswith(MARKER)


def check_file(path: Path, root: Path) -> list[str]:
    rel = path.relative_to(root).as_posix()
    src = path.read_text(encoding="utf-8")
    lines = src.split("\n")
    tree = ast.parse(src)
    errors = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.For) and isinstance(node.iter, ast.Attribute)
                and node.iter.attr in MESH_ONLY and isinstance(node.target, ast.Name)
                and writes_loop_var(node) and not exempt(lines, node.lineno)):
            errors.append(f"{rel}:{node.lineno}: per-element write in a loop over "
                          f"{ast.unparse(node.iter)}; use foreach_set "
                          f"(rule use-foreach-set-for-bulk-data) or mark '{MARKER} <why>'")
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(node, field, None)
            if not isinstance(stmts, list):
                continue
            for i, st in enumerate(stmts):
                if (isinstance(st, ast.Assign) and len(st.targets) == 1
                        and isinstance(st.targets[0], ast.Name)
                        and ast.unparse(st.value) in ("bpy.context.active_object",
                                                      "context.active_object")):
                    name = st.targets[0].id
                    nxt = stmts[i + 1] if i + 1 < len(stmts) else None
                    if not (isinstance(nxt, ast.If) and f"{name} is None" in ast.unparse(nxt.test)):
                        errors.append(f"{rel}:{st.lineno}: {name} = active_object is used "
                                      f"without 'if {name} is None' "
                                      f"(rule type-annotate-props-and-defend-context)")
    return errors


def check(root: Path = ROOT) -> list[str]:
    errors = []
    for path in scripts(root):
        errors += check_file(path, root)
    for path in template_scripts(root):
        errors += check_ops_in_loops(path, root)
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(f"::error::{e}", file=sys.stderr)
    if not errors:
        print(f"example rules: {len(scripts(ROOT))} scripts follow use-foreach-set and "
              f"active_object guards; {len(template_scripts(ROOT))} templates have no "
              "object operator in a loop")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
