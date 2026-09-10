"""Unapplied non-uniform scale → glTF — a runnable example.

A 2 m cube (local verts at ±1) with object scale (2, 1, 0.5). Proves
the scale is unapplied *and* non-uniform before asserting the exporter
contract. ``export_apply`` applies **modifiers**, not object scale
(RNA description). Neighbor of ``gltf-export-roundtrip`` (identity
scale, node has no scale) and ``prop-origin-transform`` (data-API bake
to (1,1,1) in Blender, not on disk).

Closed form:

* ``obj.scale == (2, 1, 0.5)`` and local bbox ±1 on every axis
* glTF node.scale is Y-up permuted ``(sx, sz, sy) == (2, 0.5, 1)``
* POSITION accessor stays the local cube (±1)

Vert count is 8 with or without the scale. Node scale + local POSITION
are the second axis.

No gallery still. A stretched box is indistinguishable from modeled
non-uniform dimensions; the defect is unapplied vs baked.

    blender --background --python unapplied_scale_gltf.py --
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

SCALE = (2.0, 1.0, 0.5)
YUP_NODE_SCALE = (2.0, 0.5, 1.0)
LOCAL = 1.0
EPS = 1e-5

EXPORT_KWARGS = dict(
    export_format="GLTF_SEPARATE",
    export_apply=True,
    export_yup=True,
    export_texcoords=False,
    export_normals=False,
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


def local_extent(me):
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    return (
        (min(xs), max(xs)),
        (min(ys), max(ys)),
        (min(zs), max(zs)),
    )


def extents_unit(ext):
    return all(
        abs(lo + LOCAL) < EPS and abs(hi - LOCAL) < EPS for lo, hi in ext
    )


def bake_scale(ob):
    me = ob.data
    mw = ob.matrix_world.copy()
    me.transform(mw.to_3x3().to_4x4())
    me.update()
    ob.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()


def build(identity=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("UnitCube")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
    finally:
        bm.free()
    ob = bpy.data.objects.new("Scaled", me)
    bpy.context.scene.collection.objects.link(ob)
    if not identity:
        ob.scale = SCALE
    bpy.context.view_layer.update()
    return ob


def check(ob, bake):
    props = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    missing = [k for k in EXPORT_KWARGS if k not in props]
    if missing:
        print(f"ERROR: exporter RNA drifted, missing {missing}", file=sys.stderr)
        return 2
    me = ob.data
    got = tuple(float(c) for c in ob.scale)
    non_uniform = len({round(c, 6) for c in got}) > 1
    ext = local_extent(me)
    if got != SCALE or not non_uniform or not extents_unit(ext):
        print(
            f"ERROR: pathology missing: scale={got} non_uniform={non_uniform} "
            f"local={ext}",
            file=sys.stderr,
        )
        return 3
    if bake:
        bake_scale(ob)
    tmp = tempfile.mkdtemp(prefix="unapplied_scale_")
    path = os.path.join(tmp, "scaled.gltf").replace("\\", "/")
    bpy.ops.export_scene.gltf(filepath=path, **EXPORT_KWARGS)
    g, acc = read_gltf(path)
    node = g["nodes"][0]
    pos = acc(g["meshes"][0]["primitives"][0]["attributes"]["POSITION"], 3)
    xs, ys, zs = zip(*pos)
    node_scale = tuple(node["scale"]) if node.get("scale") is not None else None
    pos_ext = ((min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs)))
    if node_scale != YUP_NODE_SCALE or not extents_unit(pos_ext) or len(pos) != 8:
        print(
            f"ERROR: export handling failed node.scale={node_scale} "
            f"pos_ext={pos_ext} n={len(pos)}",
            file=sys.stderr,
        )
        return 4
    print(
        f"scale={got} yup_node_scale={node_scale} local=±{LOCAL} "
        f"pos_n={len(pos)} export_apply=modifiers-only"
    )
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument(
        "--identity",
        action="store_true",
        help="falsification: leave scale (1,1,1); pathology absent",
    )
    p.add_argument(
        "--bake",
        action="store_true",
        help="falsification: bake scale after the pre-assert; node.scale gone",
    )
    args = p.parse_args(argv)
    ob = build(identity=args.identity)
    code = check(ob, bake=args.bake)
    if code:
        return code
    print("unapplied-scale-gltf OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
