"""Mesh normals after 4.1 — a runnable example.

Witnesses the normals API that replaced auto smooth in Blender 4.1, on both
4.5 LTS and 5.x:

- ``Mesh.use_auto_smooth``, ``auto_smooth_angle``, ``calc_normals_split()``,
  ``free_normals_split()`` and ``create_normals_split()`` are gone. Code
  that sets or calls them raises ``AttributeError``, and that code is still
  what most training data contains.
- ``Mesh.set_sharp_from_angle(angle=...)`` is the replacement for auto
  smooth. It marks edges sharper than the angle *and* sets every face smooth.
  On a flat-shaded 16-sided cylinder at 30 degrees, that is the 32 cap-rim
  edges, not the 16 side seams (22.5 degrees apart), and all 18 faces smooth.
- ``Mesh.corner_normals`` is always up to date: no ``calc_normals_split()``
  first. With smooth faces and sharp rims, a rim vertex has exactly two
  corner normals, one for the smooth side and one for the cap. Flatten the
  faces afterwards and the same read gives three, with no recompute call.

Pathology: no gallery still; the witness is attribute presence and normal
vectors, not pixels.

    blender --background --python mesh_normals_after_41.py --
    blender --background --python mesh_normals_after_41.py -- --legacy-api      # 3
    blender --background --python mesh_normals_after_41.py -- --sharp-angle 10  # 4
    blender --background --python mesh_normals_after_41.py -- --flatten-after   # 5
    blender --background --python mesh_normals_after_41.py -- --skip-set-sharp  # 6
"""
import argparse
import math
import sys

import bpy

SIDES = 16
RIM_EDGES = 2 * SIDES        # top and bottom cap rims
SHARP_ANGLE_DEG = 30.0       # side seams are 360/16 = 22.5 degrees apart
REMOVED = ("use_auto_smooth", "auto_smooth_angle", "calc_normals_split",
           "free_normals_split", "create_normals_split")


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def build():
    """A 16-sided cylinder, flat-shaded as primitive_cylinder_add makes it."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cylinder_add(vertices=SIDES)
    return bpy.context.active_object


def smooth_flags(me):
    flags = [False] * len(me.polygons)
    me.polygons.foreach_get("use_smooth", flags)
    return flags


def legacy_auto_smooth(me):
    """What pre-4.1 code (and most training data) does."""
    me.use_auto_smooth = True
    me.auto_smooth_angle = math.radians(SHARP_ANGLE_DEG)
    me.calc_normals_split()


def check_removed(me, legacy_api):
    present = [name for name in REMOVED if hasattr(me, name)]
    print(f"removed API present: {present or 'none'}")
    if present:
        return fail(f"{present} still exist; the 4.1 removal this example witnesses is gone", 3)
    if legacy_api:
        try:
            legacy_auto_smooth(me)
        except AttributeError as e:
            return fail(f"pre-4.1 auto smooth code raises: {e}", 3)
    return 0


def check_sharp(me, angle_deg, skip_set_sharp):
    flat_before = not any(smooth_flags(me))
    if not skip_set_sharp:
        me.set_sharp_from_angle(angle=math.radians(angle_deg))
    smooth_after = all(smooth_flags(me))
    print(f"faces flat before: {flat_before}, all smooth after set_sharp_from_angle: {smooth_after}")
    if not (flat_before and smooth_after):
        return fail("set_sharp_from_angle did not turn the flat cylinder's faces smooth", 6)
    attr = me.attributes.get("sharp_edge")
    sharp = 0
    if attr is not None:
        flags = [False] * len(me.edges)
        attr.data.foreach_get("value", flags)
        sharp = sum(flags)
    print(f"set_sharp_from_angle({angle_deg} deg): {sharp} of {len(me.edges)} edges sharp, "
          f"normals_domain={me.normals_domain}")
    if sharp != RIM_EDGES:
        return fail(f"{sharp} sharp edges at {angle_deg} deg, expected the {RIM_EDGES} cap rims", 4)
    return 0


def check_corner_normals(me, flatten_after):
    if flatten_after:  # no recompute call: corner_normals must follow on its own
        me.polygons.foreach_set("use_smooth", [False] * len(me.polygons))
        me.update()
    rim_vertex = 0  # bottom rim of primitive_cylinder_add
    dirs = set()
    for loop in me.loops:
        if loop.vertex_index == rim_vertex:
            n = me.corner_normals[loop.index].vector
            dirs.add(tuple(round(c, 4) for c in n))
    print(f"corner normals at rim vertex {rim_vertex}: {len(dirs)} distinct {sorted(dirs)}")
    if len(dirs) != 2:
        return fail(f"rim vertex has {len(dirs)} distinct corner normals; expected 2 "
                    "(smooth side + cap). Flat side faces give 3", 5)
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--legacy-api", action="store_true",
                   help="falsification: run the pre-4.1 use_auto_smooth / calc_normals_split code")
    p.add_argument("--sharp-angle", type=float, default=SHARP_ANGLE_DEG,
                   help="angle for set_sharp_from_angle (10 also marks the side seams)")
    p.add_argument("--skip-set-sharp", action="store_true",
                   help="falsification: never call set_sharp_from_angle (faces stay flat)")
    p.add_argument("--flatten-after", action="store_true",
                   help="falsification: flatten the faces after set_sharp_from_angle")
    args = p.parse_args(argv)

    me = build().data
    for code in (check_removed(me, args.legacy_api), check_sharp(me, args.sharp_angle, args.skip_set_sharp),
                 check_corner_normals(me, args.flatten_after)):
        if code:
            return code
    print("mesh-normals-after-41 OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
