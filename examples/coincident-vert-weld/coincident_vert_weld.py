"""Coincident duplicate verts — a runnable example.

Two 2 m cubes occupying the same space, joined as one mesh: 16 verts,
8 unique positions, still manifold. Inverse of ``degenerate-bevel-weld``
(coincidences from bevel pinch) and ``mesh-hygiene-audit`` (manifold on
a clean solid). The authored duplicates cross the glTF boundary:
24 triangles, 48 loop-split positions, 8 unique.

``bmesh.ops.remove_doubles`` collapses to one cube (8/12/6, valence 2)
— not non-manifold. The export-crossing is the handling contract.

Vert count 16 alone is not enough (any 16-vert mesh). Unique positions
= 8 is the second axis. glTF tri count 24 vs 12 after weld is the
export axis.

No gallery still. Two coincident cubes look like one cube.

    blender --background --python coincident_vert_weld.py --
"""
import argparse
import json
import os
import struct
import sys
import tempfile

import bpy
import bmesh

sys.dont_write_bytecode = True

VERTS = 16
UNIQUE = 8
FACES = 12
EDGES = 24
GLTF_POS = 48
GLTF_TRIS = 24
ND = 6

EXPORT_KWARGS = dict(
    export_format="GLTF_SEPARATE",
    export_apply=True,
    export_yup=True,
    export_texcoords=False,
    export_normals=True,
    export_materials="NONE",
    export_animations=False,
    export_image_format="NONE",
)


def read_gltf(path):
    g = json.load(open(path, encoding="utf-8"))
    blob = open(
        os.path.join(os.path.dirname(path), g["buffers"][0]["uri"]), "rb"
    ).read()

    def accessor_floats(idx, ncomp):
        acc = g["accessors"][idx]
        bv = g["bufferViews"][acc["bufferView"]]
        off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = bv.get("byteStride", 4 * ncomp)
        return [
            struct.unpack_from(f"<{ncomp}f", blob, off + stride * i)
            for i in range(acc["count"])
        ]

    return g, accessor_floats


def unique_count(me):
    return len({
        (round(v.co.x, ND), round(v.co.y, ND), round(v.co.z, ND))
        for v in me.vertices
    })


def edge_valence(me):
    counts = {}
    for e in me.edges:
        n = len(e.link_faces) if hasattr(e, "link_faces") else None
        if n is None:
            break
        counts[n] = counts.get(n, 0) + 1
    if counts:
        return counts
    # MeshEdge has no link_faces; rebuild via bmesh.
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        for e in bm.edges:
            n = len(e.link_faces)
            counts[n] = counts.get(n, 0) + 1
    finally:
        bm.free()
    return counts


def weld_mesh(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-4)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.update()


def build(duplicate=True):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("CoincidentCubes")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=2.0)
        if duplicate:
            bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
    finally:
        bm.free()
    ob = bpy.data.objects.new("CoincidentCubes", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def check(ob, weld):
    props = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    missing = [k for k in EXPORT_KWARGS if k not in props]
    if missing:
        print(f"ERROR: exporter RNA drifted, missing {missing}", file=sys.stderr)
        return 2
    me = ob.data
    uniq = unique_count(me)
    valence = edge_valence(me)
    if (
        len(me.vertices) != VERTS
        or uniq != UNIQUE
        or len(me.polygons) != FACES
        or len(me.edges) != EDGES
        or valence != {2: EDGES}
    ):
        print(
            f"ERROR: pathology missing: V={len(me.vertices)} unique={uniq} "
            f"F={len(me.polygons)} E={len(me.edges)} valence={valence}",
            file=sys.stderr,
        )
        return 3
    if weld:
        weld_mesh(me)
    tmp = tempfile.mkdtemp(prefix="coincident_")
    path = os.path.join(tmp, "dup.gltf").replace("\\", "/")
    bpy.ops.export_scene.gltf(filepath=path, **EXPORT_KWARGS)
    g, acc = read_gltf(path)
    prim = g["meshes"][0]["primitives"][0]
    pos = acc(prim["attributes"]["POSITION"], 3)
    pos_u = {(round(p[0], 5), round(p[1], 5), round(p[2], 5)) for p in pos}
    nidx = g["accessors"][prim["indices"]]["count"]
    tris = nidx // 3
    if len(pos) != GLTF_POS or tris != GLTF_TRIS or len(pos_u) != UNIQUE:
        print(
            f"ERROR: export handling failed pos={len(pos)} unique={len(pos_u)} "
            f"tris={tris}",
            file=sys.stderr,
        )
        return 4
    print(
        f"V={VERTS} unique={UNIQUE} F={FACES} valence=2×{EDGES} "
        f"gltf_pos={len(pos)} gltf_tris={tris} gltf_unique={len(pos_u)}"
    )
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument(
        "--no-duplicate",
        action="store_true",
        help="falsification: one cube; unique == V",
    )
    p.add_argument(
        "--weld",
        action="store_true",
        help="falsification: remove_doubles after pre-assert; glTF tris 12",
    )
    args = p.parse_args(argv)
    ob = build(duplicate=not args.no_duplicate)
    code = check(ob, weld=args.weld)
    if code:
        return code
    print("coincident-vert-weld OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
