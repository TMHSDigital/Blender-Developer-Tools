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
#   - bpy.data.* for direct manipulation (no UI required), including the
#     modifier bake: Mesh.new_from_object on the evaluated object, not
#     bpy.ops.object.modifier_apply per object in a loop
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


def add_modifier(obj, modifier_type, subsurf_levels=2):
    """Append a modifier to the END of obj's stack, after any existing ones."""
    modifier = obj.modifiers.new(name=modifier_type, type=modifier_type)
    if modifier_type == "SUBSURF":
        modifier.levels = subsurf_levels
        modifier.render_levels = subsurf_levels
    return modifier


def bake_modifier_stack(objs):
    """Replace each object's mesh with its evaluated stack, in stack order.

    Not bpy.ops.object.modifier_apply: on a modifier that is not first in the
    stack it evaluates that modifier against the BASE mesh and leaves the
    earlier ones live ("Applied modifier was not first"), so export_apply then
    runs them afterwards and the order is reversed. new_from_object on the
    evaluated object bakes the whole stack in its real order, through the data
    API, with one depsgraph evaluation for every object (no operator per
    object in a loop). Each object gets its own new mesh, so shared mesh data
    is never rewritten under another user.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objs:
        baked = bpy.data.meshes.new_from_object(
            obj.evaluated_get(depsgraph),
            preserve_all_data_layers=True,
            depsgraph=depsgraph,
        )
        old = obj.data
        obj.modifiers.clear()
        obj.data = baked
        if old.users == 0:
            bpy.data.meshes.remove(old)


def main():
    args = parse_args(sys.argv)

    mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if not mesh_objects:
        print("ERROR: no mesh objects in the input .blend", file=sys.stderr)
        return 2

    print(f"Found {len(mesh_objects)} mesh object(s): {[o.name for o in mesh_objects]}")

    if args.apply_modifier:
        for obj in mesh_objects:
            add_modifier(obj, args.apply_modifier, args.subsurf_levels)
        try:
            bake_modifier_stack(mesh_objects)
        except RuntimeError as exc:
            print(
                f"ERROR: failed to apply {args.apply_modifier}: {exc}",
                file=sys.stderr,
            )
            return 3
        for obj in mesh_objects:
            print(
                f"Applied {args.apply_modifier} to {obj.name}: "
                f"{len(obj.data.vertices)} verts, {len(obj.data.polygons)} faces"
            )

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
