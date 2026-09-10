"""N-gon topology pathology — a runnable example.

Dissolves one cube edge into a hexagon, then proves the n-gon exists
before asserting how Blender handles it. Hygiene's "no ngons" gate
(`mesh-hygiene-audit`) is the inverse: that example audits a clean
mesh. This one synthesizes the defect.

Closed form (cube size 2, dissolve the +X+Y edge):

* 5 faces, 1 n-gon, that face has 6 loops
* ``Mesh.calc_tangents`` aborts until triangulated
  (same abort ``triangulate-tangents`` documents)
* triangulate the n-gon → 4 tris + 4 quads, 28 loops, tangents succeed

glTF tri count is 12 either way (hexagon+quads or a cube) — not a
witness. Loop count of the n-gon is the second axis.

No gallery still. A hexagon on a cube does not read at thumbnail
without fake annotation (same call ``mesh-hygiene-audit`` made).

    blender --background --python ngon_triangulate.py --
"""
import argparse
import sys

import bpy
import bmesh

sys.dont_write_bytecode = True

NGON_COUNT = 1
NGON_LOOPS = 6
FACES_BEFORE = 5
TRIS_AFTER = 4
QUADS_AFTER = 4
LOOPS_AFTER = 28
TANGENT_ABORT = "tris/quads"


def ngons(me):
    return [p for p in me.polygons if len(p.vertices) > 4]


def build(dissolve=True):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("NgonCube")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=2.0)
        if dissolve:
            bm.edges.ensure_lookup_table()
            edge = None
            for e in bm.edges:
                mid = (e.verts[0].co + e.verts[1].co) / 2.0
                if abs(mid.x - 1.0) < 1e-8 and abs(mid.y - 1.0) < 1e-8:
                    edge = e
                    break
            if edge is None:
                raise RuntimeError("dissolve edge +X+Y not found")
            bmesh.ops.dissolve_edges(bm, edges=[edge])
        bm.to_mesh(me)
    finally:
        bm.free()
    ob = bpy.data.objects.new("NgonCube", me)
    bpy.context.scene.collection.objects.link(ob)
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    return ob


def triangulate_ngons(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        faces = [f for f in bm.faces if len(f.verts) > 4]
        if faces:
            bmesh.ops.triangulate(bm, faces=faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.update()


def tangents_aborted(me):
    try:
        me.calc_tangents()
    except RuntimeError as exc:
        return TANGENT_ABORT in str(exc)
    return False


def check(ob, skip_triangulate):
    me = ob.data
    found = ngons(me)
    if len(found) != NGON_COUNT:
        print(
            f"ERROR: pathology missing: ngon count {len(found)} != {NGON_COUNT}",
            file=sys.stderr,
        )
        return 3
    loops = len(found[0].vertices)
    if loops != NGON_LOOPS:
        print(
            f"ERROR: pathology missing: n-gon loops {loops} != {NGON_LOOPS}",
            file=sys.stderr,
        )
        return 3
    if len(me.polygons) != FACES_BEFORE:
        print(
            f"ERROR: pathology missing: faces {len(me.polygons)} != {FACES_BEFORE}",
            file=sys.stderr,
        )
        return 3
    if not tangents_aborted(me):
        print(
            "ERROR: calc_tangents did not abort on the constructed n-gon",
            file=sys.stderr,
        )
        return 4
    if skip_triangulate:
        print(
            "ERROR: skip-triangulate left the n-gon; handling unrepaired",
            file=sys.stderr,
        )
        return 4
    triangulate_ngons(me)
    leftover = ngons(me)
    tris = sum(1 for p in me.polygons if len(p.vertices) == 3)
    quads = sum(1 for p in me.polygons if len(p.vertices) == 4)
    if leftover or tris != TRIS_AFTER or quads != QUADS_AFTER:
        print(
            f"ERROR: triangulate handling failed ngons={len(leftover)} "
            f"tris={tris} quads={quads}",
            file=sys.stderr,
        )
        return 4
    if len(me.loops) != LOOPS_AFTER:
        print(
            f"ERROR: loop count {len(me.loops)} != {LOOPS_AFTER}",
            file=sys.stderr,
        )
        return 4
    if tangents_aborted(me):
        print("ERROR: calc_tangents still aborting after triangulate", file=sys.stderr)
        return 4
    print(
        f"ngons={NGON_COUNT} loops={NGON_LOOPS} faces_before={FACES_BEFORE} "
        f"tris={tris} quads={quads} loops_after={len(me.loops)} tangents=ok"
    )
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument(
        "--no-dissolve",
        action="store_true",
        help="falsification: skip the dissolve so the n-gon is absent",
    )
    p.add_argument(
        "--skip-triangulate",
        action="store_true",
        help="falsification: leave the n-gon; tangents stay aborted",
    )
    args = p.parse_args(argv)
    ob = build(dissolve=not args.no_dissolve)
    code = check(ob, skip_triangulate=args.skip_triangulate)
    if code:
        return code
    print("ngon-triangulate OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
