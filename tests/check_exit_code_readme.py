"""Every nonzero product exit code must appear in that script's README table.

Product codes live in `return N` and literal `sys.exit(N)`, not in
`sys.exit(main())`. A regex over `sys.exit(` miscounts the tree (64 vs 58).

Detection (AST only):

- Integer literals on `return` in the file's own functions, plus literal
  `sys.exit(N)`.
- `sys.exit(main())` and `sys.exit(name)` where `name` is assigned from a
  local function call (both headless templates: `exit_code = main()`) are
  harness pass-through, not unanalyzable.
- `sys.exit(1)` inside an `except` handler is the FATAL wrapper documented
  in CONTRIBUTING.md — not a named check.
- Scope: examples/, templates/, showcase/. tests/ and scripts/ are excluded.
- Anything else at a `sys.exit(...)` site is unanalyzable and fails.

README check applies to entry-point files (`if __name__ == "__main__"`).
Helpers such as examples/gallery_framing.py are still scanned for
unanalyzable sys.exit sites but have no product table of their own.

No exemption list, allowlist, or skip file.
"""
from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCOPES = ("examples", "templates", "showcase")

TABLE_ROW_RE = re.compile(r"^\|\s*`?(\d+)`?\s*\|")
EXIT_HEADING_RE = re.compile(r"^#+\s+Exit codes\s*$", re.IGNORECASE)
HEADING_RE = re.compile(r"^#+\s+")


def relpath(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def is_dunder_main(node):
    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
        return False
    if not isinstance(node.ops[0], ast.Eq) or len(node.comparators) != 1:
        return False
    left, right = node.left, node.comparators[0]

    def is_name(n, ident):
        return isinstance(n, ast.Name) and n.id == ident

    def is_const(n, value):
        return isinstance(n, ast.Constant) and n.value == value

    return (
        (is_name(left, "__name__") and is_const(right, "__main__"))
        or (is_const(left, "__main__") and is_name(right, "__name__"))
    )


def int_literal(node):
    """Return an int if *node* is an integer literal, else None.

    ast.Constant(True) is a bool (subclass of int); skip it.
    """
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = int_literal(node.operand)
        return None if inner is None else -inner
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    return None


def module_function_names(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def is_passthrough_call(node, func_names):
    """sys.exit(main()) — Call of a function defined in this module."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in func_names
    )


class ExitVisitor(ast.NodeVisitor):
    def __init__(self, func_names):
        self.func_names = func_names
        self.stack = []
        self.scope_binds = [{}]
        self.literals = []  # (code, lineno)
        self.unanalyzable = []  # (lineno, snippet)

    def _push_scope(self):
        self.scope_binds.append({})

    def _pop_scope(self):
        self.scope_binds.pop()

    def _bind(self, name, from_func):
        self.scope_binds[-1][name] = from_func

    def _bound_func(self, name):
        for binds in reversed(self.scope_binds):
            if name in binds:
                return binds[name]
        return None

    def _in_except(self):
        return any(isinstance(n, ast.ExceptHandler) for n in self.stack)

    def generic_visit(self, node):
        self.stack.append(node)
        super().generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node):
        self._push_scope()
        self.generic_visit(node)
        self._pop_scope()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node):
        if is_passthrough_call(node.value, self.func_names):
            func_id = node.value.func.id
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._bind(target.id, func_id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if node.value is not None and is_passthrough_call(node.value, self.func_names):
            if isinstance(node.target, ast.Name):
                self._bind(node.target.id, node.value.func.id)
        self.generic_visit(node)

    def visit_Return(self, node):
        if node.value is not None:
            code = int_literal(node.value)
            if code is not None:
                self.literals.append((code, node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node):
        if not (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "exit"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "sys"
        ):
            self.generic_visit(node)
            return

        snippet = ast.unparse(node)
        lineno = node.lineno
        if len(node.args) != 1 or node.keywords:
            self.unanalyzable.append((lineno, snippet))
            self.generic_visit(node)
            return

        arg = node.args[0]
        code = int_literal(arg)
        if code is not None:
            if code == 1 and self._in_except():
                self.generic_visit(node)
                return
            self.literals.append((code, lineno))
            self.generic_visit(node)
            return

        if is_passthrough_call(arg, self.func_names):
            self.generic_visit(node)
            return

        if isinstance(arg, ast.Name) and self._bound_func(arg.id):
            self.generic_visit(node)
            return

        self.unanalyzable.append((lineno, snippet))
        self.generic_visit(node)


def has_dunder_main(tree):
    for node in tree.body:
        if isinstance(node, ast.If) and is_dunder_main(node.test):
            return True
    return False


def readme_table_codes(text):
    codes = set()
    in_section = False
    for line in text.splitlines():
        if EXIT_HEADING_RE.match(line):
            in_section = True
            continue
        if in_section and HEADING_RE.match(line):
            break
        if not in_section:
            continue
        match = TABLE_ROW_RE.match(line)
        if match:
            codes.add(int(match.group(1)))
    return codes


def iter_py():
    for scope in SCOPES:
        base = os.path.join(ROOT, scope)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


def check_file(path):
    errors = []
    rel = relpath(path)
    src = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src, filename=rel)
    except SyntaxError as exc:
        errors.append(f"{rel}: cannot parse: {exc}")
        return errors

    visitor = ExitVisitor(module_function_names(tree))
    visitor.visit(tree)

    for lineno, snippet in visitor.unanalyzable:
        errors.append(
            f"{rel}:{lineno}: unanalyzable exit code: {snippet}"
        )

    if not has_dunder_main(tree):
        return errors

    nonzero = {}
    for code, lineno in visitor.literals:
        if code == 0:
            continue
        nonzero.setdefault(code, lineno)

    if not nonzero:
        return errors

    readme = os.path.join(os.path.dirname(path), "README.md")
    if not os.path.isfile(readme):
        listed = ", ".join(f"{c} (line {nonzero[c]})" for c in sorted(nonzero))
        errors.append(
            f"{rel}: nonzero product codes {listed} but no sibling README.md"
        )
        return errors

    table = readme_table_codes(open(readme, encoding="utf-8").read())
    readme_rel = relpath(readme)
    if not table:
        errors.append(
            f"{rel}: {readme_rel} has no Exit codes table"
        )
        return errors

    for code, lineno in sorted(nonzero.items()):
        if code not in table:
            errors.append(
                f"{rel}:{lineno}: return/exit {code} is not in the {readme_rel} exit table"
            )
    return errors


def main(argv):
    extra = argv[1:]
    paths = list(iter_py())
    for item in extra:
        paths.append(item if os.path.isabs(item) else os.path.join(ROOT, item))

    errors = []
    seen = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if not os.path.isfile(path):
            errors.append(f"missing scan path {relpath(path)}")
            continue
        errors.extend(check_file(path))

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print("exit-code README checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
