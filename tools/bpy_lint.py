#!/usr/bin/env python3
"""bpy_lint: flag the Blender Python anti-patterns this pack's rules describe.

    python bpy_lint.py PATH [PATH ...] [--json] [--rule NAME ...]

Scans .py files (directories recursively) and prints one line per finding:

    path:line: rule-name: what is wrong [skill: owning-skill]

Every rule in rules/*.mdc has a detector here (tests/test_bpy_lint.py keeps the
two in step). Detectors are static and deliberately narrow: each flags the
pattern its rule's "What this rule flags" section names, so a hit is worth
reading, and a clean run is not proof the code is right. Run the code on
Blender 4.5 LTS and 5.2 LTS for that.

Silence one finding with a comment on the flagged line or the line above:

    # bpy-lint: ignore[rule-name] <why>

Exit codes: 0 no findings, 1 findings, 2 usage error. Stdlib only (#534).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import asdict, dataclass

SKILL = {
    "always-free-bmesh": "mesh-editing-and-bmesh",
    "branch-eevee-engine-id": "procedural-materials-and-shaders",
    "no-bgl": "gpu-drawing-and-overlays",
    "no-legacy-action-fcurves": "slotted-actions-animation",
    "no-legacy-vse-sequences": "vse-python",
    "no-nodes-modifier-idprop-inputs": "geometry-nodes-python",
    "no-removed-normals-api": "mesh-editing-and-bmesh",
    "no-unapplied-modifiers-on-export": "engine-export-presets",
    "prefer-data-over-ops-in-loops": "mesh-editing-and-bmesh",
    "prefer-temp-override-over-context-copy": "headless-batch-scripting",
    "principled-v2-socket-names": "procedural-materials-and-shaders",
    "target-extensions-platform-format": "bl-info-migration",
    "type-annotate-props-and-defend-context": "custom-properties",
    "use-correct-axis-rna-per-exporter": "engine-export-presets",
    "use-foreach-set-for-bulk-data": "mesh-editing-and-bmesh",
    "validate-imported-mesh-scale": "ai-mesh-cleanup",
}
IGNORE = re.compile(r"#\s*bpy-lint:\s*ignore(?:\[([\w,\s-]+)\])?")
FOREACH_EXEMPT = "# foreach-exempt:"


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    message: str
    skill: str

    def text(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.message} [skill: {self.skill}]"


class File:
    def __init__(self, path: str, src: str):
        self.path, self.src = path, src
        self.lines = src.split("\n")
        self.tree = ast.parse(src)
        self.parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                self.parents[child] = node

    def ancestors(self, node):
        node = self.parents.get(node)
        while node is not None:
            yield node
            node = self.parents.get(node)

    def version_gated(self, node) -> bool:
        """Inside an if / conditional expression that tests bpy.app.version, or in
        a function that branches on it (`if version >= ...: return A` then `return B`)."""
        for a in self.ancestors(node):
            if isinstance(a, (ast.If, ast.IfExp)) and "app.version" in ast.unparse(a.test):
                return True
            if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return any(isinstance(n, (ast.If, ast.IfExp)) and "app.version" in ast.unparse(n.test)
                           for n in ast.walk(a))
        return False


def text(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001
        return ""


# --- detectors: each yields (line, message) -----------------------------------

def d_no_bgl(f: File):
    for n in ast.walk(f.tree):
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] == "bgl" for a in n.names):
            yield n.lineno, "imports bgl, which is gone in 5.x (the add-on fails to register); draw with gpu"
        elif isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "bgl":
            yield n.lineno, "imports from bgl, which is gone in 5.x; draw with gpu"
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "bgl":
            yield n.lineno, f"bgl.{n.attr} is gone in 5.x; use gpu.state / gpu_extras.batch"


def d_vse_sequences(f: File):
    for n in ast.walk(f.tree):
        if isinstance(n, ast.Attribute) and n.attr in ("sequences", "sequences_all"):
            parent = f.parents.get(n)
            # `se.strips if hasattr(se, "strips") else se.sequences` never
            # reaches .sequences on a supported version.
            if (isinstance(parent, ast.IfExp) and parent.orelse is n
                    and "hasattr" in text(parent.test) and "strips" in text(parent.test)):
                continue
            yield n.lineno, f".{n.attr} is removed in 5.x; .strips/.strips_all exist on 4.5 too"


NORMALS = {"use_auto_smooth", "auto_smooth_angle", "calc_normals_split",
           "free_normals_split", "create_normals_split"}


def d_normals(f: File):
    for n in ast.walk(f.tree):
        if isinstance(n, ast.Attribute) and n.attr in NORMALS:
            yield n.lineno, (f".{n.attr} was removed in 4.1 (AttributeError on 4.5 and 5.x); "
                             "use set_sharp_from_angle / corner_normals")


def d_context_copy(f: File):
    for n in ast.walk(f.tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "copy"
                and text(n.func.value).endswith("context")):
            yield n.lineno, "context.copy() overrides were removed in 4.0; use bpy.context.temp_override(...)"


def d_props_and_context(f: File):
    for n in ast.walk(f.tree):
        if isinstance(n, ast.ClassDef):
            for st in n.body:
                if (isinstance(st, ast.Assign) and isinstance(st.value, ast.Call)
                        and re.match(r"(bpy\.)?props\.\w+Property$", text(st.value.func))):
                    yield st.lineno, (f"{text(st.targets[0])} = {text(st.value.func)}(...) "
                                      "is the assignment form; annotate it with ':'")
        for field in ("body", "orelse", "finalbody"):
            stmts = getattr(n, field, None)
            if not isinstance(stmts, list):
                continue
            for i, st in enumerate(stmts):
                if (isinstance(st, ast.Assign) and len(st.targets) == 1
                        and isinstance(st.targets[0], ast.Name)
                        and text(st.value) in ("bpy.context.active_object", "context.active_object")):
                    name = st.targets[0].id
                    nxt = stmts[i + 1] if i + 1 < len(stmts) else None
                    guard = text(nxt.test) if isinstance(nxt, ast.If) else ""
                    if not re.search(rf"\b{name} is (not )?None\b|\bnot {name}\b|^{name}$", guard):
                        yield st.lineno, f"{name} = active_object is used without 'if {name} is None'"


def _writes(loop: ast.For) -> bool:
    var = loop.target.id
    for n in ast.walk(loop):
        targets = (n.targets if isinstance(n, ast.Assign)
                   else [n.target] if isinstance(n, ast.AugAssign) else [])
        for t in targets:
            while isinstance(t, (ast.Attribute, ast.Subscript)):
                t = t.value
            if isinstance(t, ast.Name) and t.id == var:
                return True
    return False


def d_foreach(f: File):
    for n in ast.walk(f.tree):
        if (isinstance(n, ast.For) and isinstance(n.iter, ast.Attribute)
                and n.iter.attr in ("vertices", "polygons") and isinstance(n.target, ast.Name)
                and _writes(n)):
            here = f.lines[n.lineno - 1]
            above = f.lines[n.lineno - 2] if n.lineno >= 2 else ""
            if FOREACH_EXEMPT in here or above.strip().startswith(FOREACH_EXEMPT):
                continue
            yield n.lineno, (f"per-element write in a loop over {text(n.iter)}; "
                             "use foreach_get / foreach_set")


def d_ops_in_loops(f: File):
    for n in ast.walk(f.tree):
        # an operator call is bpy.ops.<module>.<op>(...), not .get_rna_type() and co.
        if isinstance(n, ast.Call) and re.fullmatch(r"bpy\.ops\.\w+\.\w+", text(n.func)):
            if any(isinstance(a, (ast.For, ast.While, ast.comprehension, ast.ListComp))
                   for a in f.ancestors(n)):
                yield n.lineno, f"{text(n.func)}() inside a loop; act on bpy.data or bmesh in bulk"


def d_bmesh_free(f: File):
    for n in ast.walk(f.tree):
        if isinstance(n, ast.Call) and text(n.func) == "bmesh.new":
            scope = next((a for a in f.ancestors(n)
                          if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef))), f.tree)
            freed = any(isinstance(t, ast.Try) and any(
                isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "free"
                for st in t.finalbody for c in ast.walk(st)) for t in ast.walk(scope))
            if not freed:
                yield n.lineno, "bmesh.new() without bm.free() in a try/finally in the same function"


def d_bl_info_only(f: File):
    if os.path.basename(f.path) != "__init__.py":
        return
    has_bl_info = any(isinstance(st, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "bl_info" for t in st.targets) for st in f.tree.body)
    manifest = os.path.join(os.path.dirname(os.path.abspath(f.path)), "blender_manifest.toml")
    if has_bl_info and not os.path.isfile(manifest):
        line = next(st.lineno for st in f.tree.body if isinstance(st, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "bl_info" for t in st.targets))
        yield line, "bl_info with no blender_manifest.toml beside it; ship as an Extension"


def d_action_fcurves(f: File):
    for n in ast.walk(f.tree):
        if (isinstance(n, ast.Attribute) and n.attr in ("fcurves", "groups", "id_root")
                and "action" in text(n.value).split(".")[-1].lower()):
            yield n.lineno, (f"Action.{n.attr} was removed in 5.0; reach F-curves through the "
                             "slot's channelbag")


OLD_PRINCIPLED = {"Emission", "Specular", "Clearcoat", "Clearcoat Roughness", "Clearcoat Normal",
                  "Subsurface", "Subsurface Color", "Transmission", "Transmission Roughness",
                  "Sheen"}


def d_principled(f: File):
    for n in ast.walk(f.tree):
        if not (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute)
                and n.value.attr == "inputs" and isinstance(n.slice, ast.Constant)):
            continue
        owner = text(n.value.value).lower()
        key = n.slice.value
        if isinstance(key, str) and key in OLD_PRINCIPLED:
            yield n.lineno, f'inputs["{key}"] is a 3.x Principled BSDF name (KeyError on 4.5 and 5.x)'
        elif isinstance(key, int) and ("bsdf" in owner or "principled" in owner):
            yield n.lineno, f"{text(n)}: Principled inputs moved between releases; look them up by name"


SOCKET_KEY = re.compile(r"^(Socket|Input)_\d+$")


def d_nodes_idprop(f: File):
    for n in ast.walk(f.tree):
        if not isinstance(n, ast.Assign):
            continue
        for t in n.targets:
            if not isinstance(t, ast.Subscript):
                continue
            key = t.slice
            literal = isinstance(key, ast.Constant) and isinstance(key.value, str) and SOCKET_KEY.match(key.value)
            named = isinstance(key, ast.Name) and "mod" in text(t.value).lower() and "ident" in key.id.lower()
            if (literal or named) and not f.version_gated(n):
                yield n.lineno, (f"{text(t)} = ... writes a NodesModifier input as an ID property; "
                                 "5.2 removed it: branch on bpy.app.version >= (5, 2, 0)")


def d_eevee(f: File):
    for n in ast.walk(f.tree):
        if (isinstance(n, ast.Constant) and n.value in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT")
                and not f.version_gated(n)):
            yield n.lineno, (f"'{n.value}' without a version branch; the id is 'BLENDER_EEVEE_NEXT' "
                             "on 4.2-4.5 and 'BLENDER_EEVEE' on 5.0+")


def _calls(f: File, prefix: str):
    return [n for n in ast.walk(f.tree) if isinstance(n, ast.Call) and text(n.func) == prefix]


def _kw(call: ast.Call, name: str):
    return next((k.value for k in call.keywords if k.arg == name), None)


def d_import_scale(f: File):
    imports = _calls(f, "bpy.ops.import_scene.gltf") + _calls(f, "bpy.ops.import_scene.fbx")
    mesh_work = re.search(r"bmesh\.|modifiers\.new|from_pydata|foreach_set", f.src)
    unit = re.search(r"unit_settings|scale_length|global_scale", f.src)
    if imports and mesh_work and ("transform_apply" not in f.src or not unit):
        yield imports[0].lineno, ("glTF/FBX import then mesh work with no transform_apply and "
                                  "no unit-scale check")


def d_unapplied_export(f: File):
    if "modifiers.new" not in f.src or "modifier_apply" in f.src:
        return
    for c in _calls(f, "bpy.ops.export_scene.gltf"):
        v = _kw(c, "export_apply")
        if not (isinstance(v, ast.Constant) and v.value is True):
            yield c.lineno, "export_scene.gltf after modifiers.new without export_apply=True ships the cage"
    for c in _calls(f, "bpy.ops.export_scene.fbx"):
        v = _kw(c, "use_mesh_modifiers")
        if isinstance(v, ast.Constant) and v.value is False:
            yield c.lineno, "export_scene.fbx with use_mesh_modifiers=False ships the cage"


def d_axis_rna(f: File):
    for c in _calls(f, "bpy.ops.export_scene.gltf"):
        for k in ("axis_forward", "axis_up"):
            if _kw(c, k) is not None:
                yield c.lineno, f"export_scene.gltf takes export_yup, not the FBX {k}"
    for c in _calls(f, "bpy.ops.export_scene.fbx"):
        if _kw(c, "export_yup") is not None:
            yield c.lineno, "export_scene.fbx takes axis_forward/axis_up, not the glTF export_yup"


DETECTORS = {
    "always-free-bmesh": d_bmesh_free,
    "branch-eevee-engine-id": d_eevee,
    "no-bgl": d_no_bgl,
    "no-legacy-action-fcurves": d_action_fcurves,
    "no-legacy-vse-sequences": d_vse_sequences,
    "no-nodes-modifier-idprop-inputs": d_nodes_idprop,
    "no-removed-normals-api": d_normals,
    "no-unapplied-modifiers-on-export": d_unapplied_export,
    "prefer-data-over-ops-in-loops": d_ops_in_loops,
    "prefer-temp-override-over-context-copy": d_context_copy,
    "principled-v2-socket-names": d_principled,
    "target-extensions-platform-format": d_bl_info_only,
    "type-annotate-props-and-defend-context": d_props_and_context,
    "use-correct-axis-rna-per-exporter": d_axis_rna,
    "use-foreach-set-for-bulk-data": d_foreach,
    "validate-imported-mesh-scale": d_import_scale,
}


def ignored(f: File, line: int, rule: str) -> bool:
    for ln in (line, line - 1):
        if 1 <= ln <= len(f.lines):
            m = IGNORE.search(f.lines[ln - 1])
            if m and (m.group(1) is None or rule in {r.strip() for r in m.group(1).split(",")}):
                return True
    return False


def lint_source(path: str, src: str, rules=None) -> list[Finding]:
    try:
        f = File(path, src)
    except SyntaxError as exc:
        return [Finding(path, exc.lineno or 1, "syntax", f"could not parse: {exc.msg}", "-")]
    out = []
    for rule, detect in DETECTORS.items():
        if rules and rule not in rules:
            continue
        seen = set()
        for line, msg in detect(f):
            if (line, msg) in seen or ignored(f, line, rule):
                continue
            seen.add((line, msg))
            out.append(Finding(path, line, rule, msg, SKILL[rule]))
    return sorted(out, key=lambda x: (x.line, x.rule))


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if not d.startswith((".", "__pycache__")))
                for name in sorted(files):
                    if name.endswith(".py"):
                        yield os.path.join(root, name)
        else:
            yield p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true", help="print findings as a JSON list")
    ap.add_argument("--rule", action="append", choices=sorted(DETECTORS), help="only these rules")
    args = ap.parse_args(argv)
    findings = []
    for path in iter_files(args.paths):
        if not os.path.isfile(path):
            ap.error(f"no such file: {path}")
        with open(path, encoding="utf-8") as fh:
            findings += lint_source(path.replace("\\", "/"), fh.read(), args.rule)
    if args.json:
        print(json.dumps([asdict(x) for x in findings], indent=2))
    else:
        for x in findings:
            print(x.text())
        print(f"bpy_lint: {len(findings)} finding(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
