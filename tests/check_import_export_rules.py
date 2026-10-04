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
MESH_WORK_RE = re.compile(r"bmesh\.|modifiers\.new|from_pydata|foreach_set")
UNIT_SCALE_RE = re.compile(r"unit_settings|scale_length|global_scale")
# Per-exporter "ships the modifier result" test, applied to each call's own
# arguments (measured on 4.5.11 and 5.2.1):
#   glTF  export_apply defaults to False -> must pass export_apply=True
#   FBX   use_mesh_modifiers defaults to True -> only an explicit False drops them
#   USD   modifiers are evaluated by default (evaluation_mode defaults to
#         RENDER), but SUBSURF ships as the cage under the default
#         export_subdivision='BEST_MATCH' -> needs export_subdivision='TESSELLATE'
GLTF_APPLY_RE = re.compile(r"export_apply\s*=\s*True")
FBX_NO_MODS_RE = re.compile(r"use_mesh_modifiers\s*=\s*False")
USD_TESSELLATE_RE = re.compile(r"export_subdivision\s*=\s*[\"']TESSELLATE[\"']")
SUBSURF_NEW_RE = re.compile(r"modifiers\.new\([^)]*[\"']SUBSURF[\"']")
USD_CALL_RE = re.compile(r"bpy\.ops\.wm\.usd_export\s*\(")
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
    if MODIFIER_NEW_RE.search(text) and not MODIFIER_APPLY_RE.search(text):
        for body in _call_bodies(text, GLTF_CALL_RE):
            if not GLTF_APPLY_RE.search(body):
                errors.append(
                    f"{rel}: export_scene.gltf after modifiers.new without "
                    "export_apply=True (or modifier_apply) ships the cage"
                )
        for body in _call_bodies(text, FBX_CALL_RE):
            if FBX_NO_MODS_RE.search(body):
                errors.append(
                    f"{rel}: export_scene.fbx with use_mesh_modifiers=False "
                    "after modifiers.new ships the cage"
                )
        if SUBSURF_NEW_RE.search(text):
            for body in _call_bodies(text, USD_CALL_RE):
                if not USD_TESSELLATE_RE.search(body):
                    errors.append(
                        f"{rel}: wm.usd_export after a SUBSURF modifier without "
                        "export_subdivision='TESSELLATE' writes the cage "
                        "(default BEST_MATCH; evaluation_mode does not change it)"
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
