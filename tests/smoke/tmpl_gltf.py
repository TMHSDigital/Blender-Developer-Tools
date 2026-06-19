# Headless batch script template.
#
# Run with:
#   blender --background <input.blend> --python script.py -- \
#       --output /path/to/out.glb \
#       --apply-modifier SUBSURF
#
# Everything after the `--` token is forwarded to this script as sys.argv.
# Anything before `--` is consumed by Blender itself.
#
# This template demonstrates the safe headless batch pattern:
#   - bpy.data.* for direct manipulation (no UI required)
#   - bpy.context.temp_override(...) only when an operator is genuinely needed
#   - explicit exit codes so a CI pipeline can detect failures
#
# References:
#   docs.blender.org/manual/en/latest/advanced/command_line/arguments.html
#   docs.blender.org/api/current/bpy.context.html (temp_override)

import argparse
import sys

import bpy


def parse_args(argv):
    """Parse args after the `--` separator that Blender passes through."""
    if "--" in argv:
        script_args = argv[argv.index("--") + 1:]
    else:
        script_args = []

    parser = argparse.ArgumentParser(
        description="Apply a modifier to every mesh and export to glTF.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the output .glb file.",
    )
    parser.add_argument(
        "--apply-modifier",
        choices=["SUBSURF", "BEVEL", "MIRROR", "TRIANGULATE"],
        default=None,
        help="If set, add and apply this modifier to every mesh before export.",
    )
    parser.add_argument(
        "--subsurf-levels",
        type=int,
        default=2,
        help="Subdivision levels when --apply-modifier=SUBSURF.",
    )
    return parser.parse_args(script_args)


def add_and_apply_modifier(obj, modifier_type, subsurf_levels=2):
    """Add a modifier to obj and apply it.

    Modifier application is one of the few cases where bpy.ops is the
    canonical path; bpy.data does not expose an apply method. We use
    temp_override to set the active object cleanly, instead of the
    deprecated context-dict-passing form.
    """
    modifier = obj.modifiers.new(name=modifier_type, type=modifier_type)
    if modifier_type == "SUBSURF":
        modifier.levels = subsurf_levels
        modifier.render_levels = subsurf_levels

    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_apply(modifier=modifier.name)


def main():
    args = parse_args(sys.argv)

    mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if not mesh_objects:
        print("ERROR: no mesh objects in the input .blend", file=sys.stderr)
        return 2

    print(f"Found {len(mesh_objects)} mesh object(s): {[o.name for o in mesh_objects]}")

    if args.apply_modifier:
        for obj in mesh_objects:
            try:
                add_and_apply_modifier(obj, args.apply_modifier, args.subsurf_levels)
                print(f"Applied {args.apply_modifier} to {obj.name}")
            except RuntimeError as exc:
                print(
                    f"ERROR: failed to apply {args.apply_modifier} to {obj.name}: {exc}",
                    file=sys.stderr,
                )
                return 3

    try:
        bpy.ops.export_scene.gltf(
            filepath=args.output,
            export_format="GLB",
            use_selection=False,
            export_apply=True,
        )
    except RuntimeError as exc:
        print(f"ERROR: glTF export failed: {exc}", file=sys.stderr)
        return 4

    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
