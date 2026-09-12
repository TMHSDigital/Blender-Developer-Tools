"""Static checks for validate-imported-mesh-scale,
no-unapplied-modifiers-on-export, and use-correct-axis-rna-per-exporter.

Scans snippets/ and templates/**/*.py. examples/ is excluded because several
examples are intentional pathology witnesses (unapplied-scale-gltf).
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_RULES = (
    "rules/validate-imported-mesh-scale.mdc",
    "rules/no-unapplied-modifiers-on-export.mdc",
    "rules/use-correct-axis-rna-per-exporter.mdc",
)

IMPORT_RE = re.compile(r"bpy\.ops\.import_scene\.(gltf|fbx)\s*\(")
EXPORT_RE = re.compile(
    r"bpy\.ops\.(export_scene\.gltf|export_scene\.fbx|wm\.usd_export)\s*\("
)
MESH_WORK_RE = re.compile(r"bmesh\.|modifiers\.new|from_pydata|foreach_set")
UNIT_SCALE_RE = re.compile(r"unit_settings|scale_length|global_scale")
EXPORT_EVAL_RE = re.compile(
    r"export_apply\s*=\s*True|evaluation_mode\s*=|use_mesh_modifiers\s*=\s*True"
)
MODIFIER_NEW_RE = re.compile(r"modifiers\.new")
MODIFIER_APPLY_RE = re.compile(r"modifier_apply")
GLTF_CALL_RE = re.compile(r"bpy\.ops\.export_scene\.gltf\s*\(")
FBX_CALL_RE = re.compile(r"bpy\.ops\.export_scene\.fbx\s*\(")
AXIS_FORWARD_RE = re.compile(r"\baxis_forward\b")
AXIS_UP_RE = re.compile(r"\baxis_up\b")
EXPORT_YUP_RE = re.compile(r"\bexport_yup\b")


def scan_paths(extra):
    paths = []
    paths.extend(glob.glob(os.path.join(ROOT, "snippets", "*.py")))
    paths.extend(
        glob.glob(os.path.join(ROOT, "templates", "**", "*.py"), recursive=True)
    )
    for item in extra:
        paths.append(item if os.path.isabs(item) else os.path.join(ROOT, item))
    return paths


def _call_bodies(text, opener_re):
    """Extract argument text of each matching call, paren-matched.

    Whole-file scans false-positive a file that correctly calls both
    exporters (Unreal glTF plus Unreal FBX). Per-call bodies keep those
    legal.
    """
    bodies = []
    for match in opener_re.finditer(text):
        i = match.end()
        depth = 1
        start = i
        while i < len(text) and depth:
            char = text[i]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            i += 1
        if depth != 0:
            continue
        bodies.append(text[start : i - 1])
    return bodies


def check_text(rel, text):
    errors = []
    if IMPORT_RE.search(text) and MESH_WORK_RE.search(text):
        if "transform_apply" not in text or not UNIT_SCALE_RE.search(text):
            errors.append(
                f"{rel}: import_scene gltf/fbx plus mesh work without "
                "transform_apply and a unit-scale check "
                "(unit_settings, scale_length, or global_scale)"
            )
    if EXPORT_RE.search(text) and MODIFIER_NEW_RE.search(text):
        if not EXPORT_EVAL_RE.search(text) and not MODIFIER_APPLY_RE.search(text):
            errors.append(
                f"{rel}: export with modifiers.new but no export_apply=True, "
                "evaluation_mode, or modifier_apply"
            )
    for body in _call_bodies(text, GLTF_CALL_RE):
        if AXIS_FORWARD_RE.search(body) or AXIS_UP_RE.search(body):
            errors.append(
                f"{rel}: export_scene.gltf call passes axis_forward or "
                "axis_up (FBX RNA; glTF uses export_yup)"
            )
    for body in _call_bodies(text, FBX_CALL_RE):
        if EXPORT_YUP_RE.search(body):
            errors.append(
                f"{rel}: export_scene.fbx call passes export_yup "
                "(glTF RNA; FBX uses axis_forward / axis_up)"
            )
    return errors


def main(argv):
    errors = []
    for rule in REQUIRED_RULES:
        path = os.path.join(ROOT, rule)
        if not os.path.isfile(path):
            errors.append(f"missing rule file {rule}")

    extra = argv[1:]
    for path in scan_paths(extra):
        if not os.path.isfile(path):
            errors.append(f"missing scan path {path}")
            continue
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        text = open(path, encoding="utf-8").read()
        errors.extend(check_text(rel, text))

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print("import/export anti-pattern checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
