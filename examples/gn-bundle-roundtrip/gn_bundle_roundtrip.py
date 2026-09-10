"""Geometry Nodes bundle round-trip — a runnable example.

Witnesses Combine / Separate Bundle from ``skills/geometry-nodes-python``.
The load-bearing RNA on 5.x is ``NodeCombineBundle`` / ``NodeSeparateBundle``,
not ``GeometryNodeCombineBundle`` (that id is 4.5 experimental and
**undefined** on 5.2). Tree-structure checks are vacuous: the nodes can
exist and be linked while Separate looks up the wrong item names and
evaluates empty.

Closed form (1 m cube packed with Scale=2, Offset=(1.5, 0, 0), Mark=0.314159):

* verts / faces = 8 / 6
* x-extent [0.5, 2.5] (scale then translate)
* POINT attribute ``bundle_mark`` = 0.314159 on every vert

Count alone is not enough: a cube that never entered the bundle is still
8/6. Bbox from the unpacked Scale/Offset is the second axis; the named
attribute from the unpacked Float is the third.

5.0+ official. 4.5 LTS has the older RNA behind
``preferences.experimental.use_bundle_and_closure_nodes`` (default off);
this example skips there via catalog ``min_version`` 5.0. ``--force-run``
bypasses the skip and uses the 5.x RNA so 4.5 fails for that reason.

    blender --background --python gn_bundle_roundtrip.py --
"""
import argparse
import sys

import bpy

COMBINE_ID = "NodeCombineBundle"
SEPARATE_ID = "NodeSeparateBundle"

CUBE_VERTS = 8
CUBE_FACES = 6
PACK_SCALE = 2.0
PACK_OFFSET = (1.5, 0.0, 0.0)
PACK_MARK = 0.314159
XMIN = 0.5
XMAX = 2.5
EPS = 1e-4
MARK_EPS = 1e-6
ATTR = "bundle_mark"
SKIP_REASON = "Bundles require Blender 5.0+"


def eval_mesh(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        coords = [(v.co.x, v.co.y, v.co.z) for v in me.vertices]
        faces = len(me.polygons)
        marks = None
        if ATTR in me.attributes:
            data = me.attributes[ATTR].data
            marks = [data[i].value for i in range(len(me.vertices))]
    finally:
        ev.to_mesh_clear()
    return coords, faces, marks


def build_tree(pair=True, match_names=True, pack_scale=PACK_SCALE):
    tree = bpy.data.node_groups.new("BundleRoundTrip", "GeometryNodeTree")
    tree.interface.new_socket(
        name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry",
    )
    go = tree.nodes.new("NodeGroupOutput")
    cube = tree.nodes.new("GeometryNodeMeshCube")
    cube.inputs["Size"].default_value = (1.0, 1.0, 1.0)

    if not pair:
        tree.links.new(cube.outputs["Mesh"], go.inputs["Geometry"])
        return tree

    comb = tree.nodes.new(COMBINE_ID)
    sep = tree.nodes.new(SEPARATE_ID)
    comb.bundle_items.new("GEOMETRY", "Mesh")
    comb.bundle_items.new("FLOAT", "Scale")
    comb.bundle_items.new("VECTOR", "Offset")
    comb.bundle_items.new("FLOAT", "Mark")
    sep_mesh = "Mesh" if match_names else "Geom"
    sep.bundle_items.new("GEOMETRY", sep_mesh)
    sep.bundle_items.new("FLOAT", "Scale")
    sep.bundle_items.new("VECTOR", "Offset")
    sep.bundle_items.new("FLOAT", "Mark")

    tree.links.new(cube.outputs["Mesh"], comb.inputs["Mesh"])
    comb.inputs["Scale"].default_value = pack_scale
    comb.inputs["Offset"].default_value = PACK_OFFSET
    comb.inputs["Mark"].default_value = PACK_MARK
    tree.links.new(comb.outputs["Bundle"], sep.inputs["Bundle"])

    xf = tree.nodes.new("GeometryNodeTransform")
    xyz = tree.nodes.new("ShaderNodeCombineXYZ")
    store = tree.nodes.new("GeometryNodeStoreNamedAttribute")
    store.data_type = "FLOAT"
    store.domain = "POINT"
    store.inputs["Name"].default_value = ATTR

    tree.links.new(sep.outputs[sep_mesh], xf.inputs["Geometry"])
    tree.links.new(sep.outputs["Scale"], xyz.inputs["X"])
    tree.links.new(sep.outputs["Scale"], xyz.inputs["Y"])
    tree.links.new(sep.outputs["Scale"], xyz.inputs["Z"])
    tree.links.new(xyz.outputs["Vector"], xf.inputs["Scale"])
    tree.links.new(sep.outputs["Offset"], xf.inputs["Translation"])
    tree.links.new(xf.outputs["Geometry"], store.inputs["Geometry"])
    tree.links.new(sep.outputs["Mark"], store.inputs["Value"])
    tree.links.new(store.outputs["Geometry"], go.inputs["Geometry"])
    return tree


def build(pair, match_names, pack_scale):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("Carrier")
    me.vertices.add(1)
    ob = bpy.data.objects.new("Carrier", me)
    bpy.context.collection.objects.link(ob)
    mod = ob.modifiers.new("GN", "NODES")
    mod.node_group = build_tree(pair=pair, match_names=match_names, pack_scale=pack_scale)
    bpy.context.view_layer.update()
    return ob


def check(ob):
    if len(ob.data.vertices) != 1:
        print("ERROR: carrier mesh was rewritten", file=sys.stderr)
        return 2

    coords, faces, marks = eval_mesh(ob)
    xs = [c[0] for c in coords]
    print(
        f"verts={len(coords)} faces={faces} "
        f"xmin={min(xs) if xs else None} xmax={max(xs) if xs else None} "
        f"mark={marks[0] if marks else None} nmark={len(marks) if marks else 0} "
        f"expect verts={CUBE_VERTS}/{CUBE_FACES} x=[{XMIN},{XMAX}] mark={PACK_MARK}"
    )

    if len(coords) != CUBE_VERTS or faces != CUBE_FACES:
        print(
            f"ERROR: evaluated {len(coords)}/{faces}, closed form {CUBE_VERTS}/{CUBE_FACES}",
            file=sys.stderr,
        )
        return 3
    if abs(min(xs) - XMIN) > EPS or abs(max(xs) - XMAX) > EPS:
        print(
            f"ERROR: x-extent [{min(xs):.4f}, {max(xs):.4f}] "
            f"closed form [{XMIN}, {XMAX}] from Scale={PACK_SCALE} Offset={PACK_OFFSET}",
            file=sys.stderr,
        )
        return 4
    if marks is None or len(marks) != CUBE_VERTS:
        print("ERROR: missing POINT attribute bundle_mark", file=sys.stderr)
        return 5
    worst = max(abs(m - PACK_MARK) for m in marks)
    if worst > MARK_EPS:
        print(
            f"ERROR: bundle_mark worst={worst:.3e} expected {PACK_MARK}",
            file=sys.stderr,
        )
        return 5
    print(
        f"scale={PACK_SCALE} offset={PACK_OFFSET} mark={PACK_MARK} "
        f"xmin={min(xs):.4f} xmax={max(xs):.4f} pairing=ok"
    )
    return 0


def maybe_skip(force_run):
    if bpy.app.version >= (5, 0, 0):
        return 0
    if force_run:
        return 0
    print(f"SMOKE_SKIP: {SKIP_REASON}", flush=True)
    return 77


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument(
        "--force-run",
        action="store_true",
        help="bypass the 5.0 skip; 4.5 fails creating NodeCombineBundle",
    )
    p.add_argument(
        "--bypass",
        action="store_true",
        help="falsification: Group Output reads the cube, no bundle",
    )
    p.add_argument(
        "--mismatch",
        action="store_true",
        help="falsification: Separate item name Geom vs Combine Mesh",
    )
    p.add_argument("--pack-scale", type=float, default=PACK_SCALE)
    p.add_argument(
        "--legacy-rna",
        action="store_true",
        help="falsification: create GeometryNodeCombineBundle (undefined on 5.x)",
    )
    args = p.parse_args(argv)

    skipped = maybe_skip(args.force_run)
    if skipped:
        return skipped

    if args.legacy_rna:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        tree = bpy.data.node_groups.new("Legacy", "GeometryNodeTree")
        try:
            tree.nodes.new("GeometryNodeCombineBundle")
        except RuntimeError as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        print(
            "ERROR: GeometryNodeCombineBundle existed; 5.x RNA should reject it",
            file=sys.stderr,
        )
        return 2

    ob = build(
        pair=not args.bypass,
        match_names=not args.mismatch,
        pack_scale=args.pack_scale,
    )
    code = check(ob)
    if code:
        return code
    print("gn-bundle-roundtrip OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
