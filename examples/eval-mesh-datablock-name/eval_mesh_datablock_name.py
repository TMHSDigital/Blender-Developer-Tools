"""Evaluated mesh datablock naming — a runnable example.

Witnesses that ``Object.evaluated_get(depsgraph).data.name`` is a generic
``Mesh`` on 4.5 LTS and 5.1, and equals the source mesh name on 5.2.
``to_mesh().name`` equals the source name on all three — it is not the
witness. Code that treats name inequality as "this is evaluated geometry"
is silently wrong on 5.2: nothing raises.

Pathology: no gallery still. A SUBSURF cube is enough to produce a
distinct evaluated datablock (8 source verts vs 26 Catmull-Clark).

The default path asserts the names that are correct for *this* Blender
and still exits 0 on all three. ``--assume-distinct-names`` is the naive
script: fail if the names match. That is red only on 5.2.

    blender --background --python eval_mesh_datablock_name.py --
    blender --background --python eval_mesh_datablock_name.py -- --assume-distinct-names
"""
import argparse
import sys

import bpy

SOURCE_NAME = "SourceMesh"
GENERIC_EVAL_NAME = "Mesh"
SOURCE_VERTS = 8
EVAL_VERTS = 26  # Catmull-Clark SUBSURF levels=1 on a cube
CHANGED_AT = (5, 2, 0)


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def cube_mesh(name):
    me = bpy.data.meshes.new(name)
    me.from_pydata(
        [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
         (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)],
        [],
        [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
         (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5)],
    )
    me.update()
    return me


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = cube_mesh(SOURCE_NAME)
    obj = bpy.data.objects.new("SourceObj", me)
    bpy.context.collection.objects.link(obj)
    mod = obj.modifiers.new("ss", "SUBSURF")
    mod.levels = 1
    bpy.context.view_layer.update()
    return obj


def check(obj, assume_distinct_names=False):
    ver = tuple(bpy.app.version)
    legacy_distinct = ver < CHANGED_AT
    require_distinct = assume_distinct_names or legacy_distinct
    print(
        f"blender={ver} assume_distinct_names={assume_distinct_names} "
        f"legacy_distinct={legacy_distinct} require_distinct={require_distinct}"
    )

    if obj is None or obj.data is None:
        return fail("source object/mesh missing", 3)

    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    if ev.data is None:
        return fail("evaluated_get().data is None", 3)

    src_name = obj.data.name
    eval_name = ev.data.name
    src_verts = len(obj.data.vertices)
    eval_verts = len(ev.data.vertices)
    tm = ev.to_mesh()
    try:
        tm_name = tm.name
        tm_verts = len(tm.vertices)
    finally:
        ev.to_mesh_clear()

    print(
        f"src_name={src_name!r} eval_data_name={eval_name!r} "
        f"to_mesh_name={tm_name!r}"
    )
    print(
        f"src_verts={src_verts} eval_verts={eval_verts} "
        f"to_mesh_verts={tm_verts} eval_is_src={ev.data is obj.data}"
    )

    if src_verts != SOURCE_VERTS:
        return fail(
            f"source verts {src_verts} != {SOURCE_VERTS} (cube build)",
            3,
        )
    if eval_verts != EVAL_VERTS or ev.data is obj.data:
        return fail(
            f"SUBSURF did not produce a distinct evaluated mesh "
            f"(eval_verts={eval_verts}, same_datablock={ev.data is obj.data})",
            4,
        )
    if src_name != SOURCE_NAME:
        return fail(f"source name {src_name!r} != {SOURCE_NAME!r}", 5)

    if require_distinct:
        if eval_name == src_name:
            return fail(
                f"evaluated datablock name {eval_name!r} equals source "
                f"{src_name!r} — naive name-inequality distinguisher is wrong",
                6,
            )
        if eval_name != GENERIC_EVAL_NAME:
            return fail(
                f"expected generic {GENERIC_EVAL_NAME!r} on {ver}, "
                f"got {eval_name!r}",
                6,
            )
    else:
        if eval_name != src_name:
            return fail(
                f"5.2+ evaluated datablock name {eval_name!r} != "
                f"source {src_name!r}",
                6,
            )
        if eval_name != SOURCE_NAME:
            return fail(
                f"expected source name {SOURCE_NAME!r} on {ver}, "
                f"got {eval_name!r}",
                6,
            )

    if tm_name != SOURCE_NAME:
        return fail(
            f"to_mesh().name {tm_name!r} != {SOURCE_NAME!r} "
            "(this accessor is not the witness; it must stay the source)",
            7,
        )
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument(
        "--assume-distinct-names",
        action="store_true",
        help="falsification: treat name inequality as the evaluated-mesh test",
    )
    args = p.parse_args(argv)

    obj = build()
    code = check(obj, assume_distinct_names=args.assume_distinct_names)
    if code:
        return code
    print("eval-mesh-datablock-name OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
