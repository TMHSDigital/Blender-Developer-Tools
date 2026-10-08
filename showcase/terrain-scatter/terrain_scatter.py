"""Game-ready GN terrain scatter — a showcase piece, not an example.

Asserts budget conformance of a Geometry Nodes hill grid with instanced
rocks after composing shipped pipeline pieces: GN construction,
UVs, two materials, high-to-low normal bake, LOD chain, convex collider,
Unity glTF export.

GN still builds the sine hill, with closed-form micro-relief, and the
Index-jittered instance grid. The slab's rim is bevelled into its walls.
Realized cubes are replaced with closed-form glacier-worn boulders of
varied size (quad cube-sphere superellipsoids with lumps and a few shallow
fracture cleaves, smooth-shaded with sharp fracture edges), relaxed apart
so no two interpenetrate, sunk until the ground closes around each on
every side, then clamped above the slab floor.

The render path dresses the tile as a meadow diorama (turf, tall grass
round the stones, wildflowers, shrubs, a worn path, a stratified soil
section); that dressing is staging and is not part of the asset.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` LOD, ``--stray-vert`` hygiene, ``--lift-z``
zmin, ``--poke-rock`` stone floor, ``--float-rocks`` seat, ``--box-rocks``
stone shell faces, ``--pile-rocks`` stone-to-stone interpenetration,
``--perch-rocks`` sealed sectors, ``--uniform-rocks`` stone size spread,
``--sharp-rim`` rim tilt step.

No RNG. Hills are a closed-form sine product; scatter is an Index-jittered
instance grid. DECIMATE COLLAPSE triangle counts are not byte-identical
across Blender versions — the LOD gate is a ratio band, not an exact count.

    blender --background --python terrain_scatter.py --
    blender --background --python terrain_scatter.py -- --skip-decimate
    blender --background --python terrain_scatter.py -- --output terrain.png
"""
import argparse
import math
import os
import random
import sys
import tempfile
import traceback

import bmesh
import bpy
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402
import gallery_asset_quality  # noqa: E402

PATCH = 1.80
FREQ = 2.2
AMP = 0.16
ROCK_SIZE = (0.22, 0.17, 0.13)
ROCK_GRID = 3
ROCK_SPAN = 1.15
SLAB_LIFT = 0.10
ROCK_BITE = 0.035
ROCK_ZMIN = 0.012
N_ROCKS = 9

BBOX_TOL = 0.015
OUTER_SIZE = (1.800, 1.800, 0.609)
BASE_TRIS_MIN = 2000
BASE_TRIS_MAX = 3800
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 120
COLLIDER_GRID = 9              # hill grid resolution the collider is hulled from
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
STONE_FACES_MIN = 24
STONE_SHELL_FACES_MIN = 40
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.998
ROCK_SEAT_MAX = 0.02
FLOAT_LIFT = 0.12
POKE_BITE = 0.22
LIFT_Z = 0.05

DIRT_IDX = 0
STONE_IDX = 1

# Stones are kept apart by relaxing each pair of centres to at least the
# sum of their bounds; a stone's bound is STONE_R_BOUND times its size. The GN scatter jitters by up to
# 0.22 m on a 0.575 m grid, which pushed neighbours into each other: two
# pairs interpenetrated in the committed piece. The bound covers the
# largest ellipsoid semi-axis (0.135), the surface bump (0.016) and the
# lean tilt, so any two relaxed stones clear by construction.
# Stones are ROCK_SCALE times the base ellipsoid: cleaving takes a third of
# the volume off, and at 1.0 the cleaved stones read as pebbles on a slab.
ROCK_SCALE = 1.35
# Erratics are sub-rounded, blocky boulders: a superellipsoid of exponent
# BLOCK_EXP squares the ellipsoid's shoulders by up to SHAPE_BULGE in plan
# (2 ** (1/2 - 1/BLOCK_EXP)), and two closed-form lumps add up to LUMP_AMP.
BLOCK_EXP = 2.6
LUMP_AMP = 0.13
SHAPE_BULGE = 2.0 ** (0.5 - 1.0 / BLOCK_EXP)
STONE_R_BOUND = ROCK_SCALE * (0.135 * SHAPE_BULGE * (1.0 + LUMP_AMP) + 0.22 * 0.095)
STONE_CLEAR = 0.02
RELAX_ITERS = 40
PILE_PULL = 0.40
# Each rock is cleaved by a few shallow planes, the flat fracture and
# abrasion faces of a glacier-worn block, over its rounded body.
N_CLEAVES = 4
CLEAVE_DEPTH = 0.68
# Stones are quad cube-spheres: CUBE_N_BIG segments a side for the
# boulders (size factor >= CUBE_BIG_SIZE), CUBE_N_SMALL for the cobbles.
CUBE_N_BIG = 4
CUBE_N_SMALL = 3
CUBE_BIG_SIZE = 0.9
# Stones are smooth-shaded so the worn body reads round; edges folding more
# than STONE_SHARP_DEG stay sharp, so the fracture faces keep a crisp arris.
STONE_SHARP_DEG = 48.0

# Stone sizes, one factor per scatter point. A tile of nine stones that are
# all within 20% of each other reads as a planted grid; real scatter is a
# couple of boulders among cobbles. The relaxation spaces each stone by its
# own bound, so big and small stones clear by the same margin.
STONE_SIZES = (1.45, 0.62, 1.00, 0.55, 1.25, 0.78, 0.58, 1.12, 0.70)
SIZE_RATIO_MIN = 3.0           # largest / smallest stone footprint area
# Embedding: in every azimuth sector around a stone, some vertex is sunk
# below the terrain under it, so the ground closes around the stone on every
# side. Seating the lowest point on the centre's dirt height, the old rule,
# left daylight under the downhill side of every stone on a slope: no stone
# was sealed in more than 6 of 8 sectors, two in only 4.
EMBED_SINK = 0.006
SEAL_SECTORS = 8               # azimuth sectors that must each hold a buried vertex
SEAL_EPS = 0.002
# The slab's top-to-wall rim is rounded: a knife edge all round the tile
# made it read as a slice of cake. RIM_TIP_MAX bounds the step in normal
# elevation (degrees from horizontal) between any two adjacent dirt faces,
# so the ground turns into the wall gradually. It is an elevation step,
# not a dihedral, because at the four corners the two chamfer strips meet
# at a right angle in plan, which is a rounded corner, not a knife edge.
# Bevel gives the middle folds twice the end folds: at two segments a 90
# degree edge splits 22.5/45/22.5. Where the hill rises into the rim the fold
# is wider than 90 degrees, and three segments left a 40.5-degree step, so
# the rim takes four.
RIM_BEVEL = 0.035
RIM_SEGMENTS = 4
RIM_TIP_MAX = 40.0
WALL_NZ = 0.1                  # a dirt face with |normal.z| below this is a wall
# Micro-relief on the hill, closed form: (fx, fy, phase_x, phase_y, amplitude).
RELIEF = ((9.1, 7.3, 0.4, 1.3, 0.014), (17.9, 15.2, 2.1, 0.7, 0.007))


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def evaluated_triangle_count(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        eval_mesh.calc_loop_triangles()
        return len(eval_mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()


def deselect_all():
    for ob in list(bpy.context.view_layer.objects):
        if ob is None:
            continue
        ob.select_set(False)


def add_box(bm, loc, scale, mat_idx, euler=(0.0, 0.0, 0.0)):
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = geo["verts"]
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        p = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
        v.co = rot @ p + origin
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


def pack_uvs(bm, margin=0.08):
    uv = bm.loops.layers.uv.new("UVMap")
    faces = list(bm.faces)
    n = len(faces)
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))
    cell_w = 1.0 / cols
    cell_h = 1.0 / rows
    pad_u = margin * cell_w * 0.5
    pad_v = margin * cell_h * 0.5
    usable_w = cell_w - 2.0 * pad_u
    usable_h = cell_h - 2.0 * pad_v
    for i, face in enumerate(faces):
        col = i % cols
        row = i // cols
        nrm = face.normal
        ax = abs(nrm.x)
        ay = abs(nrm.y)
        az = abs(nrm.z)
        coords = []
        for loop in face.loops:
            co = loop.vert.co
            if az >= ax and az >= ay:
                coords.append((co.x, co.y))
            elif ax >= ay:
                coords.append((co.y, co.z))
            else:
                coords.append((co.x, co.z))
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        dx = max(maxx - minx, 1e-8)
        dy = max(maxy - miny, 1e-8)
        origin_u = col * cell_w + pad_u
        origin_v = row * cell_h + pad_v
        for loop, (x, y) in zip(face.loops, coords):
            loop[uv].uv = (
                origin_u + (x - minx) / dx * usable_w,
                origin_v + (y - miny) / dy * usable_h,
            )


def hill_z_socket(tree, freq, amp):
    pos = tree.nodes.new("GeometryNodeInputPosition")
    sep = tree.nodes.new("ShaderNodeSeparateXYZ")
    tree.links.new(pos.outputs["Position"], sep.inputs[0])
    mx = tree.nodes.new("ShaderNodeMath")
    mx.operation = "MULTIPLY"
    mx.inputs[1].default_value = freq
    my = tree.nodes.new("ShaderNodeMath")
    my.operation = "MULTIPLY"
    my.inputs[1].default_value = freq
    tree.links.new(sep.outputs["X"], mx.inputs[0])
    tree.links.new(sep.outputs["Y"], my.inputs[0])
    sine = tree.nodes.new("ShaderNodeMath")
    sine.operation = "SINE"
    cose = tree.nodes.new("ShaderNodeMath")
    cose.operation = "COSINE"
    tree.links.new(mx.outputs[0], sine.inputs[0])
    tree.links.new(my.outputs[0], cose.inputs[0])
    prod = tree.nodes.new("ShaderNodeMath")
    prod.operation = "MULTIPLY"
    tree.links.new(sine.outputs[0], prod.inputs[0])
    tree.links.new(cose.outputs[0], prod.inputs[1])
    add1 = tree.nodes.new("ShaderNodeMath")
    add1.operation = "ADD"
    add1.inputs[1].default_value = 1.0
    tree.links.new(prod.outputs[0], add1.inputs[0])
    sc = tree.nodes.new("ShaderNodeMath")
    sc.operation = "MULTIPLY"
    sc.inputs[1].default_value = amp
    tree.links.new(add1.outputs[0], sc.inputs[0])
    return sc.outputs[0]


def relief_z_socket(tree, base):
    """base + sum of amp*sin(fx*x + px)*cos(fy*y + py) over RELIEF."""
    out = base
    for fx, fy, px, py, amp in RELIEF:
        pos = tree.nodes.new("GeometryNodeInputPosition")
        sep = tree.nodes.new("ShaderNodeSeparateXYZ")
        tree.links.new(pos.outputs["Position"], sep.inputs[0])
        waves = []
        for axis, f, ph, op in (("X", fx, px, "SINE"), ("Y", fy, py, "COSINE")):
            mul = tree.nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY_ADD"
            mul.inputs[1].default_value = f
            mul.inputs[2].default_value = ph
            tree.links.new(sep.outputs[axis], mul.inputs[0])
            trig = tree.nodes.new("ShaderNodeMath")
            trig.operation = op
            tree.links.new(mul.outputs[0], trig.inputs[0])
            waves.append(trig.outputs[0])
        prod = tree.nodes.new("ShaderNodeMath")
        prod.operation = "MULTIPLY"
        tree.links.new(waves[0], prod.inputs[0])
        tree.links.new(waves[1], prod.inputs[1])
        acc = tree.nodes.new("ShaderNodeMath")
        acc.operation = "MULTIPLY_ADD"
        acc.inputs[1].default_value = amp
        tree.links.new(prod.outputs[0], acc.inputs[0])
        tree.links.new(out, acc.inputs[2])
        out = acc.outputs[0]
    return out


def build_scatter_tree(verts, dirt, stone):
    tree = bpy.data.node_groups.new("TerrainScatter", "GeometryNodeTree")
    tree.interface.new_socket(
        name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry",
    )
    go = tree.nodes.new("NodeGroupOutput")

    hill = relief_z_socket(tree, hill_z_socket(tree, FREQ, AMP))
    off = tree.nodes.new("ShaderNodeCombineXYZ")
    tree.links.new(hill, off.inputs["Z"])

    grid = tree.nodes.new("GeometryNodeMeshGrid")
    grid.inputs["Size X"].default_value = PATCH
    grid.inputs["Size Y"].default_value = PATCH
    grid.inputs["Vertices X"].default_value = verts
    grid.inputs["Vertices Y"].default_value = verts
    set_pos = tree.nodes.new("GeometryNodeSetPosition")
    tree.links.new(grid.outputs["Mesh"], set_pos.inputs["Geometry"])
    tree.links.new(off.outputs["Vector"], set_pos.inputs["Offset"])
    lift = tree.nodes.new("GeometryNodeTransform")
    lift.inputs["Translation"].default_value = (0.0, 0.0, SLAB_LIFT)
    tree.links.new(set_pos.outputs["Geometry"], lift.inputs["Geometry"])
    shade_t = tree.nodes.new("GeometryNodeSetShadeSmooth")
    shade_t.inputs["Shade Smooth"].default_value = False
    tree.links.new(lift.outputs["Geometry"], shade_t.inputs["Geometry"])
    sm_d = tree.nodes.new("GeometryNodeSetMaterial")
    sm_d.inputs["Material"].default_value = dirt
    tree.links.new(shade_t.outputs["Geometry"], sm_d.inputs["Geometry"])

    pts = tree.nodes.new("GeometryNodeMeshGrid")
    pts.inputs["Size X"].default_value = ROCK_SPAN
    pts.inputs["Size Y"].default_value = ROCK_SPAN
    pts.inputs["Vertices X"].default_value = ROCK_GRID
    pts.inputs["Vertices Y"].default_value = ROCK_GRID
    idx = tree.nodes.new("GeometryNodeInputIndex")
    jx = tree.nodes.new("ShaderNodeMath")
    jx.operation = "MULTIPLY"
    jx.inputs[1].default_value = 1.73
    tree.links.new(idx.outputs["Index"], jx.inputs[0])
    jxs = tree.nodes.new("ShaderNodeMath")
    jxs.operation = "SINE"
    tree.links.new(jx.outputs[0], jxs.inputs[0])
    jxm = tree.nodes.new("ShaderNodeMath")
    jxm.operation = "MULTIPLY"
    jxm.inputs[1].default_value = 0.22
    tree.links.new(jxs.outputs[0], jxm.inputs[0])
    jy = tree.nodes.new("ShaderNodeMath")
    jy.operation = "MULTIPLY"
    jy.inputs[1].default_value = 2.19
    tree.links.new(idx.outputs["Index"], jy.inputs[0])
    jyc = tree.nodes.new("ShaderNodeMath")
    jyc.operation = "COSINE"
    tree.links.new(jy.outputs[0], jyc.inputs[0])
    jym = tree.nodes.new("ShaderNodeMath")
    jym.operation = "MULTIPLY"
    jym.inputs[1].default_value = 0.22
    tree.links.new(jyc.outputs[0], jym.inputs[0])
    extra = tree.nodes.new("ShaderNodeMath")
    extra.operation = "ADD"
    extra.inputs[1].default_value = SLAB_LIFT
    tree.links.new(hill, extra.inputs[0])
    jitter = tree.nodes.new("ShaderNodeCombineXYZ")
    tree.links.new(jxm.outputs[0], jitter.inputs["X"])
    tree.links.new(jym.outputs[0], jitter.inputs["Y"])
    tree.links.new(extra.outputs[0], jitter.inputs["Z"])
    set_pts = tree.nodes.new("GeometryNodeSetPosition")
    tree.links.new(pts.outputs["Mesh"], set_pts.inputs["Geometry"])
    tree.links.new(jitter.outputs["Vector"], set_pts.inputs["Offset"])

    cube = tree.nodes.new("GeometryNodeMeshCube")
    cube.inputs["Size"].default_value = ROCK_SIZE
    iop = tree.nodes.new("GeometryNodeInstanceOnPoints")
    tree.links.new(set_pts.outputs["Geometry"], iop.inputs["Points"])
    tree.links.new(cube.outputs["Mesh"], iop.inputs["Instance"])

    ang = tree.nodes.new("ShaderNodeMath")
    ang.operation = "MULTIPLY"
    ang.inputs[1].default_value = 0.67
    tree.links.new(idx.outputs["Index"], ang.inputs[0])
    rot = tree.nodes.new("ShaderNodeCombineXYZ")
    tree.links.new(ang.outputs[0], rot.inputs["Z"])
    tree.links.new(rot.outputs["Vector"], iop.inputs["Rotation"])

    mod = tree.nodes.new("ShaderNodeMath")
    mod.operation = "MODULO"
    mod.inputs[1].default_value = 3.0
    tree.links.new(idx.outputs["Index"], mod.inputs[0])
    div = tree.nodes.new("ShaderNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = 3.0
    tree.links.new(mod.outputs[0], div.inputs[0])
    mul_s = tree.nodes.new("ShaderNodeMath")
    mul_s.operation = "MULTIPLY"
    mul_s.inputs[1].default_value = 0.22
    tree.links.new(div.outputs[0], mul_s.inputs[0])
    add_s = tree.nodes.new("ShaderNodeMath")
    add_s.operation = "ADD"
    add_s.inputs[1].default_value = 0.84
    tree.links.new(mul_s.outputs[0], add_s.inputs[0])
    scl = tree.nodes.new("ShaderNodeCombineXYZ")
    tree.links.new(add_s.outputs[0], scl.inputs["X"])
    tree.links.new(add_s.outputs[0], scl.inputs["Y"])
    tree.links.new(add_s.outputs[0], scl.inputs["Z"])
    tree.links.new(scl.outputs["Vector"], iop.inputs["Scale"])

    realize = tree.nodes.new("GeometryNodeRealizeInstances")
    tree.links.new(iop.outputs["Instances"], realize.inputs["Geometry"])
    sm_s = tree.nodes.new("GeometryNodeSetMaterial")
    sm_s.inputs["Material"].default_value = stone
    tree.links.new(realize.outputs["Geometry"], sm_s.inputs["Geometry"])

    join = tree.nodes.new("GeometryNodeJoinGeometry")
    tree.links.new(sm_d.outputs["Geometry"], join.inputs[0])
    tree.links.new(sm_s.outputs["Geometry"], join.inputs[0])
    shade = tree.nodes.new("GeometryNodeSetShadeSmooth")
    shade.inputs["Shade Smooth"].default_value = False
    tree.links.new(join.outputs["Geometry"], shade.inputs["Geometry"])
    tree.links.new(shade.outputs["Geometry"], go.inputs["Geometry"])
    return tree


def eval_to_mesh(obj, name):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    em = ev.to_mesh()
    try:
        me = bpy.data.meshes.new(name)
        me.from_pydata(
            [tuple(v.co) for v in em.vertices],
            [],
            [tuple(p.vertices) for p in em.polygons],
        )
        src_idx = [p.material_index for p in em.polygons]
        me.update()
        for poly, idx in zip(me.polygons, src_idx):
            poly.material_index = idx
    finally:
        ev.to_mesh_clear()
    return me


def slabify(bm, floor_z=0.0, sharp_rim=False):
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    boundary = [e for e in bm.edges if e.is_boundary]
    if not boundary:
        return
    ret = bmesh.ops.extrude_edge_only(bm, edges=boundary)
    rim = list(boundary)
    verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    for v in verts:
        v.co.z = floor_z
    bottom = [
        e for e in bm.edges
        if e.is_boundary
        and abs(e.verts[0].co.z - floor_z) < 1e-5
        and abs(e.verts[1].co.z - floor_z) < 1e-5
    ]
    if bottom:
        try:
            bmesh.ops.edgeloop_fill(bm, edges=bottom)
        except Exception:
            bmesh.ops.contextual_create(bm, geom=bottom)
    if not sharp_rim:
        # Chamfer the top-to-wall fold (the original boundary edges, now
        # shared by the hill and the new wall faces), so the tile edge
        # catches light instead of cutting like a knife.
        bmesh.ops.bevel(
            bm, geom=rim, offset=RIM_BEVEL, offset_type="OFFSET",
            segments=RIM_SEGMENTS, profile=0.5, affect="EDGES",
            clamp_overlap=True,
        )
    for f in bm.faces:
        if f.material_index not in (DIRT_IDX, STONE_IDX):
            f.material_index = DIRT_IDX


def nearest_dirt_z(bm, x, y):
    best_z = None
    best_d = 1e9
    for v in bm.verts:
        if not v.link_faces:
            continue
        if not any(f.material_index == DIRT_IDX for f in v.link_faces):
            continue
        dx = v.co.x - x
        dy = v.co.y - y
        d = dx * dx + dy * dy
        if d < best_d:
            best_d = d
            best_z = v.co.z
    return 0.0 if best_z is None else best_z


_CUBE = {}


def cube_sphere(n):
    """Unit directions on a warped cube-sphere lattice and its quads
    (outward winding): even quads, no poles, unlike a UV or ico sphere."""
    if n in _CUBE:
        return _CUBE[n]
    index = {}
    dirs = []

    def vid(i, j, k):
        key = (i, j, k)
        if key not in index:
            q = [math.tan(math.pi / 4.0 * (2.0 * c / n - 1.0)) for c in key]
            index[key] = len(dirs)
            dirs.append(Vector(q).normalized())
        return index[key]

    quads = []
    for ax in range(3):
        b, c = (ax + 1) % 3, (ax + 2) % 3
        for side in (0, n):
            for uu in range(n):
                for vv in range(n):
                    corners = []
                    for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                        key = [0, 0, 0]
                        key[ax] = side
                        key[b] = uu + du
                        key[c] = vv + dv
                        corners.append(vid(*key))
                    quads.append(corners if side else corners[::-1])
    _CUBE[n] = (dirs, quads)
    return _CUBE[n]


def add_seated_stone(bm, cx, cy, dirt_z, box_rocks, poke, float_up,
                     size=1.0, ground=None, perch=False):
    k = ROCK_SCALE * size
    sx = k * (0.11 + 0.025 * math.sin(cx * 8.1))
    sy = k * (0.10 + 0.022 * math.cos(cy * 6.4))
    sz = k * (0.075 + 0.020 * math.sin(cx * 4.2 + cy * 3.1))
    bite = POKE_BITE if poke else ROCK_BITE
    seat = dirt_z + FLOAT_LIFT if float_up else dirt_z - bite
    rot = Euler(
        (
            0.22 * math.sin(cx * 3.1),
            0.18 * math.cos(cy * 2.7),
            cx * 2.4 + cy * 1.6,
        )
    ).to_matrix()
    if box_rocks:
        verts = add_box(bm, (0.0, 0.0, 0.0), (sx * 2.0, sy * 2.0, sz * 2.0), STONE_IDX)
        for v in verts:
            v.co = rot @ v.co
    else:
        dirs, quads = cube_sphere(CUBE_N_BIG if size >= CUBE_BIG_SIZE else CUBE_N_SMALL)
        verts = []
        # Two low-frequency lumps per stone, directions and phases from its
        # centre, closed form: a worn block, not an egg.
        w1 = Vector((math.sin(cx * 4.3 + 1.0), math.cos(cy * 3.7), 0.6)).normalized()
        w2 = Vector((math.cos(cy * 5.1), 0.5, math.sin(cx * 2.9 + 0.4))).normalized()
        ph1 = cx * 7.0 + cy * 3.0
        ph2 = cy * 6.0 - cx * 2.0
        for d in dirs:
            sup = (abs(d.x) ** BLOCK_EXP + abs(d.y) ** BLOCK_EXP
                   + abs(d.z) ** BLOCK_EXP) ** (-1.0 / BLOCK_EXP)
            lump = 1.0 + LUMP_AMP * (0.65 * math.sin(2.6 * w1.dot(d) + ph1)
                                     + 0.35 * math.sin(5.3 * w2.dot(d) + ph2))
            p = Vector((d.x * sx, d.y * sy, d.z * sz)) * (sup * lump)
            verts.append(bm.verts.new(rot @ p))
        for q in quads:
            bm.faces.new([verts[i] for i in q])
        # Cleave: project everything beyond each plane onto it. Plane
        # normals and depths come from the stone's own centre, closed form,
        # so every stone breaks differently but reproducibly.
        for k in range(N_CLEAVES):
            a = cx * (3.7 + k) + cy * (2.3 + 1.7 * k) + 0.9 * k
            b = 0.35 + 0.9 * (0.5 + 0.5 * math.sin(cx * 5.3 + k * 1.3 + cy))
            n = Vector((math.cos(a) * math.sin(b), math.sin(a) * math.sin(b), math.cos(b)))
            reach = max(abs(n.x) * sx, abs(n.y) * sy, abs(n.z) * sz)
            d = CLEAVE_DEPTH * reach + 0.15 * reach * math.sin(cy * 7.1 + k)
            for v in verts:
                over = v.co.dot(n) - d
                if over > 0.0:
                    v.co -= n * over
        for f in {face for v in verts for face in v.link_faces}:
            f.material_index = STONE_IDX
    zmin = min(v.co.z for v in verts)
    dz = seat - zmin
    if ground is not None and not (poke or float_up or perch):
        # Embed: around the stone's centroid, each of SEAL_SECTORS azimuth
        # sectors gets its most-buried vertex EMBED_SINK below the terrain
        # directly under it, so the ground closes around the stone on every
        # side, uphill and down, however the stone is tilted.
        mx = sum(v.co.x for v in verts) / len(verts)
        my = sum(v.co.y for v in verts) / len(verts)
        depth = {}
        for v in verts:
            a = math.atan2(v.co.y - my, v.co.x - mx) + math.pi
            s = int(a / (2.0 * math.pi) * SEAL_SECTORS) % SEAL_SECTORS
            h = v.co.z - ground(cx + v.co.x, cy + v.co.y)
            depth[s] = min(depth.get(s, h), h)
        dz = -EMBED_SINK - max(depth.values())
    for v in verts:
        v.co.x += cx
        v.co.y += cy
        v.co.z += dz
        if not poke and v.co.z < ROCK_ZMIN:
            v.co.z = ROCK_ZMIN


def relax_centres(specs, half_span, sizes):
    """Push stone centres apart until each pair clears by STONE_CLEAR, deterministically.

    Each stone's bound is STONE_R_BOUND times its size factor. Pairwise,
    symmetric, fixed iteration count, and clamped so every stone stays on
    the tile with its own bound inside the edge.
    """
    pts = [Vector((x, y)) for x, y in specs]
    bounds = [STONE_R_BOUND * s for s in sizes]
    for _ in range(RELAX_ITERS):
        moved = False
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                need = bounds[i] + bounds[j] + STONE_CLEAR
                d = pts[j] - pts[i]
                dist = d.length
                if dist >= need:
                    continue
                if dist < 1e-9:
                    d = Vector((1.0, 0.0))
                    dist = 1e-9
                push = d / dist * (0.5 * (need - dist))
                pts[i] -= push
                pts[j] += push
                moved = True
        for p, b in zip(pts, bounds):
            lim = half_span - b - STONE_CLEAR
            p.x = max(-lim, min(lim, p.x))
            p.y = max(-lim, min(lim, p.y))
        if not moved:
            break
    return [(p.x, p.y) for p in pts]


def masonry_from_cubes(bm, box_rocks=False, poke=False, float_up=False, pile=False,
                       perch=False, uniform=False):
    stone_faces = [f for f in bm.faces if f.material_index == STONE_IDX]
    visited = set()
    islands = []
    for face in stone_faces:
        if face in visited:
            continue
        stack = [face]
        island = []
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            island.append(cur)
            for edge in cur.edges:
                for other in edge.link_faces:
                    if other.material_index == STONE_IDX and other not in visited:
                        stack.append(other)
        islands.append(island)

    specs = []
    for island in islands:
        verts = {v for f in island for v in f.verts}
        xs = [v.co.x for v in verts]
        ys = [v.co.y for v in verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        specs.append((cx, cy))

    if stone_faces:
        bmesh.ops.delete(bm, geom=stone_faces, context="FACES")
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")

    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    dirt_xy = [v.co for v in bm.verts]
    span_c = (
        0.5 * (min(c.x for c in dirt_xy) + max(c.x for c in dirt_xy)),
        0.5 * (min(c.y for c in dirt_xy) + max(c.y for c in dirt_xy)),
    )
    local = [(x - span_c[0], y - span_c[1]) for x, y in specs]
    sizes = [1.0 if uniform else STONE_SIZES[i % len(STONE_SIZES)]
             for i in range(len(local))]
    if pile:
        # Falsifier: no relaxation, and the scatter drawn in toward the
        # middle so neighbours collide. Skipping relaxation alone proves
        # nothing once the stones are cleaved small enough to miss.
        local = [(x * PILE_PULL, y * PILE_PULL) for x, y in local]
    else:
        local = relax_centres(local, PATCH / 2.0, sizes)
    specs = [(x + span_c[0], y + span_c[1]) for x, y in local]
    # The terrain height under any point: a ray down onto the dirt-only
    # mesh, captured before any stone is added.
    dirt_bvh = BVHTree.FromBMesh(bm)

    def ground(x, y):
        hit = dirt_bvh.ray_cast((x, y, 10.0), (0.0, 0.0, -1.0))[0]
        return hit.z if hit is not None else nearest_dirt_z(bm, x, y)

    for (cx, cy), size in zip(specs, sizes):
        dirt_z = nearest_dirt_z(bm, cx, cy)
        add_seated_stone(bm, cx, cy, dirt_z, box_rocks, poke, float_up,
                         size=size, ground=ground, perch=perch)


def build_terrain_mesh(
    name,
    grid_verts,
    dirt,
    stone,
    box_rocks=False,
    poke=False,
    float_up=False,
    pile=False,
    perch=False,
    uniform=False,
    sharp_rim=False,
):
    carrier = bpy.data.meshes.new(name + "Carrier")
    carrier.vertices.add(1)
    obj = bpy.data.objects.new(name + "GN", carrier)
    bpy.context.collection.objects.link(obj)
    tree = build_scatter_tree(grid_verts, dirt, stone)
    mod = obj.modifiers.new("terrain_scatter", "NODES")
    mod.node_group = tree
    realized = eval_to_mesh(obj, name + "Eval")
    bpy.data.objects.remove(obj, do_unlink=True)

    bm = bmesh.new()
    try:
        bm.from_mesh(realized)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        slabify(bm, floor_z=0.0, sharp_rim=sharp_rim)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        masonry_from_cubes(bm, box_rocks=box_rocks, poke=poke, float_up=float_up,
                           pile=pile, perch=perch, uniform=uniform)
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        zmin = min(zs)
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy
            v.co.z -= zmin
            if v.co.z < 0.0:
                v.co.z = 0.0
        ngons = [f for f in bm.faces if len(f.verts) > 4]
        if ngons:
            bmesh.ops.triangulate(bm, faces=ngons)
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # The hill and its rim chamfer are ground, and flat shading printed
        # the 21x21 grid on them; they are smooth. The walls and underside
        # stay flat (an edge is only smoothed when both of its faces are
        # smooth). Stones are smooth over their worn body, with the folds
        # into the cleaved fracture faces kept sharp: flat-shaded, the
        # cube-sphere stones read as faceted low-poly placeholders.
        smooth = [
            f.material_index == STONE_IDX
            or (f.material_index == DIRT_IDX and f.normal.z > WALL_NZ)
            for f in bm.faces
        ]
        for face, s in zip(bm.faces, smooth):
            face.smooth = s
        sharp_ang = math.radians(STONE_SHARP_DEG)
        for e in bm.edges:
            lf = e.link_faces
            if (len(lf) == 2 and lf[0].material_index == STONE_IDX
                    and lf[1].material_index == STONE_IDX
                    and e.calc_face_angle(0.0) > sharp_ang):
                e.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        for poly, s in zip(me.polygons, smooth):
            poly.use_smooth = s
    finally:
        bm.free()
    out = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(out)
    return out


def principled(name, color, metallic, roughness, noise_scale=0.0, wear=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if noise_scale > 0.0 and wear is not None:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = noise_scale
        tex.inputs["Detail"].default_value = 6.0
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = color
        mix.inputs["B"].default_value = wear
        fac = mix.inputs.get("Factor") or mix.inputs.get("Fac")
        nt.links.new(tex.outputs["Fac"], fac)
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    return mat


def _sock(sockets, identifier):
    """A Mix-node socket by identifier; its A/B/Result names repeat per type."""
    return next(sk for sk in sockets if sk.identifier == identifier)


def mottled(name, dark, light, rough_lo, rough_hi, scale, fine, bump, subsoil=None):
    """Object-space mottle for colour, fine noise for roughness and bump.

    subsoil: (colour, z_low, z_high) darkens the colour toward `colour`
    below z_high in object space, fully at z_low, so a cut face reads as
    topsoil over subsoil instead of repeating the surface mottle.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    big = nt.nodes.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = scale
    big.inputs["Detail"].default_value = 5.0
    big.inputs["Roughness"].default_value = 0.6
    nt.links.new(coord.outputs["Object"], big.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = light
    nt.links.new(big.outputs["Fac"], ramp.inputs["Fac"])
    colour = ramp.outputs["Color"]
    if subsoil is not None:
        deep, z_low, z_high = subsoil
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(coord.outputs["Object"], sep.inputs[0])
        depth = nt.nodes.new("ShaderNodeMapRange")
        depth.inputs["From Min"].default_value = z_high
        depth.inputs["From Max"].default_value = z_low
        nt.links.new(sep.outputs["Z"], depth.inputs["Value"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(depth.outputs["Result"], mix.inputs["Factor"])
        nt.links.new(colour, _sock(mix.inputs, "A_Color"))
        _sock(mix.inputs, "B_Color").default_value = deep
        colour = _sock(mix.outputs, "Result_Color")
    nt.links.new(colour, bsdf.inputs["Base Color"])
    small = nt.nodes.new("ShaderNodeTexNoise")
    small.inputs["Scale"].default_value = fine
    small.inputs["Detail"].default_value = 3.0
    nt.links.new(coord.outputs["Object"], small.inputs["Vector"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = rough_lo
    rough.inputs["To Max"].default_value = rough_hi
    nt.links.new(small.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    if bump > 0.0:
        bmp = nt.nodes.new("ShaderNodeBump")
        bmp.inputs["Strength"].default_value = bump
        bmp.inputs["Distance"].default_value = 0.003
        nt.links.new(small.outputs["Fac"], bmp.inputs["Height"])
        nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def terrain_materials():
    """(dirt, stone): shared by the check, the render and inspection.

    The old pale tan dirt and near-white stone read as a clay slab with
    marshmallows on it. Dark mottled soil and grey weathered stone give
    the value contrast the other way round: stones lighter than the ground
    but not white, the ground earth rather than clay.
    """
    dirt = mottled(
        "TerrainDirt", (0.075, 0.048, 0.026, 1.0), (0.20, 0.135, 0.075, 1.0),
        0.82, 0.98, scale=6.0, fine=90.0, bump=0.35,
        subsoil=((0.035, 0.024, 0.016, 1.0), 0.0, SLAB_LIFT + 0.02),
    )
    # Stones mid-grey, not near-white: at 0.40 the lit faces clipped toward
    # white in the hero and the stones read as sugar lumps on the soil.
    stone = mottled(
        "TerrainStone", (0.12, 0.118, 0.11, 1.0), (0.27, 0.26, 0.235, 1.0),
        0.62, 0.86, scale=9.0, fine=160.0, bump=0.20,
    )
    return dirt, stone


def assign_slots(obj, dirt, stone):
    # Do not materials.clear() — that resets polygon material_index to 0
    # on this Blender, which would drop stone faces onto dirt.
    mats = obj.data.materials
    wanted = (dirt, stone)
    for i, mat in enumerate(wanted):
        if i < len(mats):
            mats[i] = mat
        else:
            mats.append(mat)


def world_bbox(obj):
    mat = obj.matrix_world
    pts = [mat @ v.co for v in obj.data.vertices]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def uv_stats(mesh):
    uv = mesh.uv_layers.active
    if uv is None:
        return 0.0, 0.0, 1.0, 1.0, 0, 1.0
    data = uv.data
    us = [loop.uv[0] for loop in data]
    vs = [loop.uv[1] for loop in data]
    aabbs = []
    for poly in mesh.polygons:
        pu = [data[i].uv[0] for i in poly.loop_indices]
        pv = [data[i].uv[1] for i in poly.loop_indices]
        aabbs.append((min(pu), min(pv), max(pu), max(pv)))
    overlap = 0.0
    for i in range(len(aabbs)):
        a = aabbs[i]
        for j in range(i + 1, len(aabbs)):
            b = aabbs[j]
            x0 = max(a[0], b[0])
            y0 = max(a[1], b[1])
            x1 = min(a[2], b[2])
            y1 = min(a[3], b[3])
            overlap += max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return min(us), min(vs), max(us), max(vs), overlap, len(aabbs)


def make_lod(obj, name, ratio, skip_decimate):
    mesh = obj.data.copy()
    lod = bpy.data.objects.new(name, mesh)
    lod.matrix_world = obj.matrix_world.copy()
    bpy.context.scene.collection.objects.link(lod)
    if not skip_decimate and 0.0 < ratio < 1.0:
        mod = lod.modifiers.new("DecimateBudget", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = ratio
    return lod


def convex_hull_collider(obj, name):
    # bmesh.ops.convex_hull can list the same element in geom_interior and
    # geom_unused; once deleted it is invalid and a second delete raises
    # ReferenceError. Filter on is_valid before each delete.
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        # Hull the points, not the surface: convex_hull keeps source faces
        # lying on the hull, which made colliders non-manifold (#386).
        for edge in list(bm.edges):
            bm.edges.remove(edge)
        result = bmesh.ops.convex_hull(bm, input=list(bm.verts))
        interior = [g for g in result.get("geom_interior") or [] if g.is_valid]
        if interior:
            bmesh.ops.delete(bm, geom=interior, context="VERTS")
        unused = [g for g in result.get("geom_unused") or [] if g.is_valid]
        if unused:
            bmesh.ops.delete(bm, geom=unused, context="VERTS")
        loose = [v for v in bm.verts if v.is_valid and not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    collider = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(collider)
    collider.matrix_world = obj.matrix_world.copy()
    return collider


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("TerrainNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = DIRT_IDX
    return img, tex


def bake_normal(high, low):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    deselect_all()
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    return bpy.ops.object.bake(
        type="NORMAL",
        use_selected_to_active=True,
        cage_extrusion=CAGE_EXTRUSION,
        use_cage=False,
        normal_space="TANGENT",
        margin=4,
        margin_type="ADJACENT_FACES",
        use_clear=True,
        target="IMAGE_TEXTURES",
    )


def export_unity(path, objects):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_yup=True,
                              export_apply=True, export_draco_mesh_compression_enable=False,
                              export_animations=False)


def face_area(me, poly):
    vs = [me.vertices[i].co for i in poly.vertices]
    if len(vs) < 3:
        return 0.0
    v0 = vs[0]
    area = 0.0
    for i in range(1, len(vs) - 1):
        area += (vs[i] - v0).cross(vs[i + 1] - v0).length * 0.5
    return area


def hygiene_audit(me):
    nv, ne, nf = len(me.vertices), len(me.edges), len(me.polygons)
    ngons = sum(1 for p in me.polygons if len(p.vertices) > 4)
    zero_area = sum(1 for p in me.polygons if face_area(me, p) <= AREA_EPS)
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        loose_v = sum(1 for v in bm.verts if len(v.link_edges) == 0)
        loose_e = sum(1 for e in bm.edges if len(e.link_faces) == 0)
        nonman = sum(1 for e in bm.edges if not e.is_manifold)
        ret = bmesh.ops.find_doubles(bm, verts=list(bm.verts), dist=DOUBLES_EPS)
        doubles = len(ret.get("targetmap") or {})
    finally:
        bm.free()
    return {
        "nv": nv, "ne": ne, "nf": nf, "ngons": ngons,
        "loose_v": loose_v, "loose_e": loose_e, "nonman": nonman,
        "zero_area": zero_area, "doubles": doubles, "euler": nv - ne + nf,
    }


def zfight_pairs(me):
    data = [
        (p.center.copy(), p.normal.copy(), frozenset(p.vertices))
        for p in me.polygons
    ]
    eps2 = ZFIGHT_EPS * ZFIGHT_EPS
    count = 0
    for i in range(len(data)):
        ci, ni, vi = data[i]
        for j in range(i + 1, len(data)):
            cj, nj, vj = data[j]
            if (cj - ci).length_squared > eps2:
                continue
            if abs(ni.dot(nj)) <= ZFIGHT_COS:
                continue
            if vi & vj:
                continue
            count += 1
    return count


def shells(me):
    neighbors = [[] for _ in range(len(me.vertices))]
    for edge in me.edges:
        a, b = edge.vertices
        neighbors[a].append(b)
        neighbors[b].append(a)
    seen = [False] * len(me.vertices)
    groups = []
    for start in range(len(me.vertices)):
        if seen[start]:
            continue
        seen[start] = True
        stack = [start]
        group = []
        while stack:
            current = stack.pop()
            group.append(current)
            for nxt in neighbors[current]:
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(nxt)
        groups.append(group)
    return groups


def shell_aabb(me, group):
    pts = [me.vertices[i].co for i in group]
    return (
        min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts),
        max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts),
    )


def mat_of(me, group):
    member = set(group)
    for poly in me.polygons:
        if all(i in member for i in poly.vertices):
            return poly.material_index
    return None


def shell_faces(me, group):
    member = set(group)
    return sum(1 for p in me.polygons if all(i in member for i in p.vertices))


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, 0.55))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def nearest_mesh_dirt_z(me, x, y, dirt_verts):
    best_z = 0.0
    best_d = 1e9
    for co in dirt_verts:
        d = (co.x - x) ** 2 + (co.y - y) ** 2
        if d < best_d:
            best_d = d
            best_z = co.z
    return best_z


def joint_audit(me):
    groups = shells(me)
    stones = []
    dirt_verts = []
    for poly in me.polygons:
        if poly.material_index != DIRT_IDX:
            continue
        for i in poly.vertices:
            dirt_verts.append(me.vertices[i].co)
    for g in groups:
        if mat_of(me, g) != STONE_IDX:
            continue
        a = shell_aabb(me, g)
        nfaces = shell_faces(me, g)
        cx = 0.5 * (a[0] + a[3])
        cy = 0.5 * (a[1] + a[4])
        dirt_z = nearest_mesh_dirt_z(me, cx, cy, dirt_verts)
        stones.append((a[2], nfaces, a[2] - dirt_z))
    n_stones = len(stones)
    min_faces = min((s[1] for s in stones), default=0)
    poke_z = min((s[0] for s in stones), default=99.0)
    float_off = max((s[2] for s in stones), default=0.0)
    return {
        "n_stones": n_stones,
        "min_faces": min_faces,
        "poke_z": poke_z,
        "float_off": float_off,
    }


def ground_audit(me):
    """Stone embedding, stone size spread and rim fold, from the final mesh.

    min_sealed: fewest azimuth sectors (of SEAL_SECTORS, around each stone's
    centroid) holding a stone vertex at least SEAL_EPS below the terrain
    straight under it. A sector with none is daylight under the stone.
    size_ratio: largest over smallest stone footprint (XY AABB) area.
    rim_tip: largest step in normal elevation, in degrees, between adjacent
    dirt faces, the underside excluded (it sits on the floor).
    """
    verts = [v.co.copy() for v in me.vertices]
    dirt = [p for p in me.polygons if p.material_index == DIRT_IDX]
    bvh = BVHTree.FromPolygons(verts, [tuple(p.vertices) for p in dirt])
    min_sealed = SEAL_SECTORS
    areas = []
    for g in shells(me):
        if mat_of(me, g) != STONE_IDX:
            continue
        pts = [verts[i] for i in g]
        cx = sum(p.x for p in pts) / len(pts)
        cy = sum(p.y for p in pts) / len(pts)
        sealed = set()
        for p in pts:
            hit = bvh.ray_cast((p.x, p.y, 10.0), (0.0, 0.0, -1.0))[0]
            if hit is not None and p.z - hit.z < -SEAL_EPS:
                a = math.atan2(p.y - cy, p.x - cx) + math.pi
                sealed.add(int(a / (2.0 * math.pi) * SEAL_SECTORS) % SEAL_SECTORS)
        min_sealed = min(min_sealed, len(sealed))
        a = shell_aabb(me, g)
        areas.append((a[3] - a[0]) * (a[4] - a[1]))
    size_ratio = max(areas) / min(areas) if areas else 0.0
    face_of = {}
    for p in dirt:
        for ek in p.edge_keys:
            face_of.setdefault(ek, []).append(p.normal)
    rim_tip = 0.0
    for ns in face_of.values():
        if len(ns) != 2 or min(ns[0].z, ns[1].z) < -0.5:
            continue  # the underside-to-wall fold sits on the floor
        e0, e1 = (math.asin(max(-1.0, min(1.0, n.z))) for n in ns)
        rim_tip = max(rim_tip, math.degrees(abs(e0 - e1)))
    return {"min_sealed": min_sealed, "size_ratio": size_ratio, "rim_tip": rim_tip}


def stone_overlap_audit(me):
    """Pairs of stone shells whose surfaces interpenetrate (BVH overlap)."""
    trees = []
    for g in shells(me):
        if mat_of(me, g) != STONE_IDX:
            continue
        bm = bmesh.new()
        try:
            bm.from_mesh(me)
            keep = set(g)
            drop = [f for f in bm.faces if not all(v.index in keep for v in f.verts)]
            bmesh.ops.delete(bm, geom=drop, context="FACES")
            trees.append(BVHTree.FromBMesh(bm))
        finally:
            bm.free()
    pairs = 0
    for i in range(len(trees)):
        for j in range(i + 1, len(trees)):
            if trees[i].overlap(trees[j]):
                pairs += 1
    return pairs


def check(
    skip_decimate,
    lift_z=False,
    stray_vert=False,
    poke=False,
    float_up=False,
    box_rocks=False,
    pile=False,
    perch=False,
    uniform=False,
    sharp_rim=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    dirt, stone = terrain_materials()
    kw = dict(box_rocks=box_rocks, poke=poke, float_up=float_up, pile=pile,
              perch=perch, uniform=uniform, sharp_rim=sharp_rim)
    low = build_terrain_mesh("TerrainLow", 21, dirt, stone, **kw)
    high = build_terrain_mesh("TerrainHigh", 25, dirt, stone, **kw)
    assign_slots(low, dirt, stone)
    assign_slots(high, dirt, stone)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        _co = [0.0] * (len(low.data.vertices) * 3)
        low.data.vertices.foreach_get("co", _co)
        _co[2::3] = [z + LIFT_Z for z in _co[2::3]]
        low.data.vertices.foreach_set("co", _co)
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("terrain mesh did not build", 3), None, None, None, None, None

    base_tris = triangle_count(low.data)
    mats = [s for s in low.data.materials if s is not None]
    nmat = len(mats)
    distinct_mats = len({id(s) for s in mats})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    print(f"measured mat_index_counts={idx_counts}")
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x = bb[3] - bb[0]
    size_y = bb[4] - bb[1]
    size_z = bb[5] - bb[2]

    img, tex = setup_bake_image(low, dirt)
    if img is None:
        return fail("terrain has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "TerrainLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "TerrainLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    # The collider hulls a coarse, unchamfered tile: the rim rounding and
    # the micro-relief are visual, and each adds hull vertices a physics
    # proxy has no use for.
    collider_src = build_terrain_mesh(
        "TerrainColSrc", COLLIDER_GRID, dirt, stone, **dict(kw, sharp_rim=True)
    )
    collider = convex_hull_collider(collider_src, "TerrainCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_terrain_scatter_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender points TMPDIR at its own temp preference, which on a portable
    # build is the working directory, so the export must not outlive this.
    if os.path.isfile(export_path):
        os.remove(export_path)

    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(
        f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
        f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}"
    )
    print(
        f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
        f"overlap={overlap:.6f} nfaces={nfaces}"
    )
    print(
        f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
        f"outer={OUTER_SIZE} zmin={bb[2]:.4f}"
    )
    print(
        f"measured collider_tris={col_tris} bake={bake_result} "
        f"bake_has_data={img.has_data} export_bytes={export_size}"
    )
    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    jnt = joint_audit(low.data)
    overlaps = stone_overlap_audit(low.data)
    gnd = ground_audit(low.data)
    print(
        f"measured sealed_min={gnd['min_sealed']}/{SEAL_SECTORS} "
        f"size_ratio={gnd['size_ratio']:.3f} rim_tip={gnd['rim_tip']:.2f}"
    )
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}"
    )
    print(
        f"measured stones={jnt['n_stones']} min_faces={jnt['min_faces']} "
        f"poke_z={jnt['poke_z']:.5f} float_off={jnt['float_off']:.5f} "
        f"stone_overlaps={overlaps}"
    )

    if jnt["min_faces"] < STONE_SHELL_FACES_MIN:
        return fail(
            f"stone shell faces {jnt['min_faces']} < {STONE_SHELL_FACES_MIN}",
            19,
        ), None, None, None, None, None
    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return fail(
            f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]",
            4,
        ), None, None, None, None, None
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return fail(
            f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(STONE_IDX, 0) < STONE_FACES_MIN:
        return fail(
            f"stone faces {idx_counts.get(STONE_IDX, 0)} < {STONE_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return fail(
            f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})",
            6,
        ), None, None, None, None, None
    if overlap > UV_OVERLAP_MAX:
        return fail(
            f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}",
            7,
        ), None, None, None, None, None
    if jnt["n_stones"] != N_ROCKS or jnt["poke_z"] < ROCK_ZMIN:
        return fail(
            f"poke stones={jnt['n_stones']} poke_z={jnt['poke_z']:.5f}",
            17,
        ), None, None, None, None, None
    if jnt["float_off"] > ROCK_SEAT_MAX:
        return fail(
            f"float_off {jnt['float_off']:.5f} > {ROCK_SEAT_MAX}",
            18,
        ), None, None, None, None, None
    if overlaps:
        return fail(
            f"{overlaps} stone pairs interpenetrate (--pile-rocks is the designed fail)",
            20,
        ), None, None, None, None, None
    if gnd["min_sealed"] < SEAL_SECTORS:
        return fail(
            f"a stone is sealed in only {gnd['min_sealed']}/{SEAL_SECTORS} sectors "
            "(--perch-rocks is the designed fail)",
            21,
        ), None, None, None, None, None
    if gnd["size_ratio"] < SIZE_RATIO_MIN:
        return fail(
            f"stone footprint ratio {gnd['size_ratio']:.3f} < {SIZE_RATIO_MIN} "
            "(--uniform-rocks is the designed fail)",
            22,
        ), None, None, None, None, None
    if gnd["rim_tip"] > RIM_TIP_MAX:
        return fail(
            f"rim tip {gnd['rim_tip']:.2f} deg > {RIM_TIP_MAX} "
            "(--sharp-rim is the designed fail)",
            23,
        ), None, None, None, None, None
    if bb[2] > ZMIN_EPS:
        return fail(f"grounded zmin={bb[2]:.5f}", 16), None, None, None, None, None
    if (
        abs(size_x - OUTER_SIZE[0]) > BBOX_TOL
        or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
        or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL
    ):
        return fail(
            f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
            f"off outer {OUTER_SIZE}",
            8,
        ), None, None, None, None, None
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return fail(
            f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
            "(--skip-decimate is the designed fail)",
            9,
        ), None, None, None, None, None
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return fail(
            f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]",
            9,
        ), None, None, None, None, None
    if col_tris > COLLIDER_TRIS_MAX:
        return fail(
            f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}",
            11,
        ), None, None, None, None, None
    if bake_result != {"FINISHED"} or not img.has_data:
        return fail(
            f"bake failed result={bake_result} has_data={img.has_data}",
            12,
        ), None, None, None, None, None
    if export_size <= 0:
        return fail("export file missing or empty", 13), None, None, None, None, None
    if (
        hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
        or hyg["doubles"] or hyg["ngons"] or zf
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}",
            15,
        ), None, None, None, None, None
    return 0, low, high, dirt, tex, collider


# ---------------------------------------------------------------------------
# Render path. Everything below dresses the hero still: the check has already
# measured and exported the asset, and nothing here feeds a budget.
# ---------------------------------------------------------------------------

# A worn foot path across the hillside, in the tile's object space. It runs
# along the axis at PATH_ANGLE (u) and meanders across it (v):
#     v = a + b * sin(PATH_FREQ * u + p) + PATH_WOBBLE * sin(2.7 * u + 1.3)
# with a, b, p chosen at render time to thread between the stones.
PATH_ANGLE_DEG = 38.0
PATH_FREQ = 2.4
PATH_WOBBLE = 0.035
PATH_HALF = 0.085
TURF_CLUMPS = 4200
FLOWERS = 380
PEBBLES = 70
BUSHES = 3


def enabled_socket(sockets, name):
    """The one enabled socket called ``name`` (Mix / Map Range carry one per
    data type under one name; identifiers changed in 5.2)."""
    for sock in sockets:
        if sock.name == name and sock.enabled:
            return sock
    return sockets[name]


def mapping(nt, vec, scale=(1.0, 1.0, 1.0)):
    node = nt.nodes.new("ShaderNodeMapping")
    node.inputs["Scale"].default_value = scale
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Vector"]


def noise(nt, vec, scale, detail_, roughness):
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail_
    node.inputs["Roughness"].default_value = roughness
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]


def voronoi_node(nt, vec, scale, feature="F1"):
    node = nt.nodes.new("ShaderNodeTexVoronoi")
    node.feature = feature
    node.inputs["Scale"].default_value = scale
    nt.links.new(vec, node.inputs["Vector"])
    return node


def voronoi(nt, vec, scale, feature="F1"):
    return voronoi_node(nt, vec, scale, feature).outputs["Distance"]


def ramp(nt, fac, stops, constant=False):
    node = nt.nodes.new("ShaderNodeValToRGB")
    if constant:
        node.color_ramp.interpolation = "CONSTANT"
    els = node.color_ramp.elements
    els[0].position = stops[0][0]
    els[0].color = (*stops[0][1], 1.0)
    els[1].position = stops[-1][0]
    els[1].color = (*stops[-1][1], 1.0)
    for pos, rgb in stops[1:-1]:
        els.new(pos).color = (*rgb, 1.0)
    nt.links.new(fac, node.inputs["Fac"])
    return node.outputs["Color"]


def remap(nt, value, from_lo, from_hi, to_lo, to_hi):
    node = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(value, enabled_socket(node.inputs, "Value"))
    enabled_socket(node.inputs, "From Min").default_value = from_lo
    enabled_socket(node.inputs, "From Max").default_value = from_hi
    enabled_socket(node.inputs, "To Min").default_value = to_lo
    enabled_socket(node.inputs, "To Max").default_value = to_hi
    return enabled_socket(node.outputs, "Result")


def math_node(nt, op, a, b=0.0):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    for i, value in enumerate((a, b)):
        if isinstance(value, (int, float)):
            node.inputs[i].default_value = value
        else:
            nt.links.new(value, node.inputs[i])
    return node.outputs[0]


def mul(nt, *vals):
    out = vals[0]
    for v in vals[1:]:
        out = math_node(nt, "MULTIPLY", out, v)
    return out


def add(nt, *vals):
    out = vals[0]
    for v in vals[1:]:
        out = math_node(nt, "ADD", out, v)
    return out


def mix_color(nt, a, b, fac):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    if isinstance(fac, (int, float)):
        enabled_socket(node.inputs, "Factor").default_value = fac
    else:
        nt.links.new(fac, enabled_socket(node.inputs, "Factor"))
    for nm, value in (("A", a), ("B", b)):
        sock = enabled_socket(node.inputs, nm)
        if isinstance(value, tuple):
            sock.default_value = (*value, 1.0)
        else:
            nt.links.new(value, sock)
    return enabled_socket(node.outputs, "Result")


def attr(nt, name):
    node = nt.nodes.new("ShaderNodeAttribute")
    node.attribute_type = "GEOMETRY"
    node.attribute_name = name
    return node.outputs["Fac"]


def coord_xyz(nt, coord):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    return sep.outputs


def normal_xyz(nt):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
    return sep.outputs


def add_bump(nt, bsdf, height, strength, distance, normal=None):
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    nt.links.new(height, bump.inputs["Height"])
    if normal is not None:
        nt.links.new(normal, bump.inputs["Normal"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def translucent(nt, bsdf, rgb, amount):
    out = nt.nodes["Material Output"]
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = (*rgb, 1.0)
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = amount
    nt.links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])


def warp(nt, vec, scale, amount):
    """``vec`` pushed about by a noise field, so Voronoi cells come out as
    irregular stones rather than discs."""
    nn = nt.nodes.new("ShaderNodeTexNoise")
    nn.inputs["Scale"].default_value = scale
    nn.inputs["Detail"].default_value = 2.0
    nt.links.new(vec, nn.inputs["Vector"])
    sub = nt.nodes.new("ShaderNodeVectorMath")
    sub.operation = "SUBTRACT"
    nt.links.new(nn.outputs["Color"], sub.inputs[0])
    sub.inputs[1].default_value = (0.5, 0.5, 0.5)
    sc = nt.nodes.new("ShaderNodeVectorMath")
    sc.operation = "SCALE"
    nt.links.new(sub.outputs["Vector"], sc.inputs[0])
    sc.inputs["Scale"].default_value = amount
    out = nt.nodes.new("ShaderNodeVectorMath")
    out.operation = "ADD"
    nt.links.new(vec, out.inputs[0])
    nt.links.new(sc.outputs["Vector"], out.inputs[1])
    return out.outputs["Vector"]


def fresh_nodes(mat, keep=()):
    """Clear a material down to its output and Principled BSDF (and any
    node in ``keep``); returns (tree, bsdf, object-space coordinate)."""
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.type in ("OUTPUT_MATERIAL", "BSDF_PRINCIPLED") or n in keep:
            continue
        nt.nodes.remove(n)
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = 0.0
    coord = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    return nt, bsdf, coord


def new_surface(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return (mat,) + fresh_nodes(mat)


class FootPath:
    """The worn path's centre line and half width, mirrored in the soil
    shader so blades, flowers and bushes keep off what the shader paints."""

    def __init__(self, a, b, p):
        th = math.radians(PATH_ANGLE_DEG)
        self.c, self.s = math.cos(th), math.sin(th)
        self.a, self.b, self.p = a, b, p

    def uv(self, x, y):
        return x * self.c + y * self.s, -x * self.s + y * self.c

    def centre(self, u):
        return (self.a + self.b * math.sin(PATH_FREQ * u + self.p)
                + PATH_WOBBLE * math.sin(2.7 * u + 1.3))

    def half(self, u):
        return PATH_HALF + 0.018 * math.sin(9.0 * u + 0.7)

    def margin(self, x, y):
        """Signed distance outside the path edge (negative on the path)."""
        u, v = self.uv(x, y)
        return abs(v - self.centre(u)) - self.half(u)


def choose_path(stones):
    """Thread the path between the stones: the candidate whose nearest stone
    clears the path edge by the most, ties to the straighter, central one."""
    best = None
    for ai in range(-6, 7):
        a = 0.05 * ai
        for b in (0.08, 0.12, 0.16, 0.20):
            for pi_ in range(12):
                p = pi_ * math.pi / 6.0
                fp = FootPath(a, b, p)
                clear = min(fp.margin(cx, cy) - r for cx, cy, r, _top in stones)
                # The path must actually cross the tile: its centre stays
                # on the tile at both ends of the u range.
                ends = [fp.centre(u) for u in (-0.85, 0.0, 0.85)]
                if max(abs(e) for e in ends) > 0.55:
                    continue
                score = (round(clear, 3), -abs(a) - 0.2 * b)
                if best is None or score > best[0]:
                    best = (score, fp)
    return best[1]


def render_attributes(low):
    """Render-only point attributes on the tile, for the shaders:
    Depth (soil verts: metres below the ground surface over them, so the
    cut sides layer turf, humus and subsoil down from the hill's own top),
    Lift (stone verts: metres above the ground under them) and Tone (one
    value per stone). Returns stones (cx, cy, r, top) and two samplers."""
    me = low.data
    verts = [v.co.copy() for v in me.vertices]
    polys = list(me.polygons)
    mat_idx = [p.material_index for p in polys]
    top_faces = [tuple(p.vertices) for p in polys
                 if p.material_index == DIRT_IDX and p.normal.z > WALL_NZ]
    top = BVHTree.FromPolygons(verts, top_faces)
    full = BVHTree.FromPolygons(verts, [tuple(p.vertices) for p in polys])
    inner = PATCH / 2.0 - RIM_BEVEL - 0.01

    def ground(x, y):
        loc, nrm, _i, _d = top.ray_cast((x, y, 10.0), (0.0, 0.0, -1.0))
        return (loc.z, nrm) if loc is not None else (None, None)

    def ground_in(x, y):
        z, _n = ground(max(-inner, min(inner, x)), max(-inner, min(inner, y)))
        return 0.0 if z is None else z

    def on_stone(x, y):
        loc, _n, i, _d = full.ray_cast((x, y, 10.0), (0.0, 0.0, -1.0))
        return loc is not None and mat_idx[i] == STONE_IDX

    n = len(verts)
    depth, lift, tone = [0.0] * n, [0.0] * n, [0.0] * n
    stones = []
    k = 0
    for g in shells(me):
        if mat_of(me, g) != STONE_IDX:
            for i in g:
                depth[i] = max(0.0, ground_in(verts[i].x, verts[i].y) - verts[i].z)
            continue
        t = 0.5 + 0.5 * math.sin(k * 2.39 + 0.7)
        k += 1
        cx = sum(verts[i].x for i in g) / len(g)
        cy = sum(verts[i].y for i in g) / len(g)
        r = max(math.hypot(verts[i].x - cx, verts[i].y - cy) for i in g)
        stones.append((cx, cy, r, max(verts[i].z for i in g)))
        for i in g:
            lift[i] = max(0.0, verts[i].z - ground_in(verts[i].x, verts[i].y))
            tone[i] = t
    for name, vals in (("Depth", depth), ("Lift", lift), ("Tone", tone)):
        a = me.attributes.new(name, "FLOAT", "POINT")
        a.data.foreach_set("value", vals)
    me.update()
    return stones, ground, on_stone


class Dress:
    """A render-only mesh: verts with per-vertex float attributes."""

    def __init__(self, names):
        self.names = names
        self.v, self.f, self.a = [], [], []

    def vert(self, co, *vals):
        self.v.append(tuple(co))
        self.a.append(vals)
        return len(self.v) - 1

    def face(self, *ids):
        self.f.append(ids)

    def build(self, name, mat, smooth=False):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        me.update()
        for k, nm in enumerate(self.names):
            at = me.attributes.new(nm, "FLOAT", "POINT")
            at.data.foreach_set("value", [vals[k] for vals in self.a])
        me.materials.append(mat)
        if smooth:
            me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        me.update()
        return bpy.data.objects.new(name, me)


def blade(D, root, ang, h, lean, w, tone, droop=0.0, twist=0.0):
    """One curved, tapering grass blade: three rows and a tip, bowed along
    ``ang`` by ``lean`` of its height, its tip dropping by ``droop``."""
    d = Vector((math.cos(ang), math.sin(ang), 0.0))
    sa = ang + math.pi / 2.0 + twist
    side = Vector((math.cos(sa), math.sin(sa), 0.0))
    rows = []
    for t in (0.0, 0.38, 0.72):
        c = root + d * (lean * h * t * t) + Vector((0.0, 0.0, h * t - droop * h * t * t))
        hw = w * (1.0 - 0.7 * t)
        rows.append((D.vert(c - side * hw, tone, t), D.vert(c + side * hw, tone, t)))
    tip = D.vert(root + d * (lean * h) + Vector((0.0, 0.0, h * (1.0 - droop))), tone, 1.0)
    for (a0, b0), (a1, b1) in zip(rows, rows[1:]):
        D.face(a0, b0, b1, a1)
    D.face(rows[-1][0], rows[-1][1], tip)
    return root + d * (lean * h) + Vector((0.0, 0.0, h * (1.0 - droop)))


def grass_material():
    mat, nt, bsdf, coord = new_surface("MeadowGrass")
    tone = attr(nt, "Tone")
    tip = attr(nt, "Tip")
    col = ramp(nt, tone, ((0.00, (0.030, 0.070, 0.016)), (0.30, (0.050, 0.120, 0.022)),
                          (0.55, (0.090, 0.175, 0.030)), (0.75, (0.165, 0.230, 0.045)),
                          (0.88, (0.28, 0.27, 0.085)), (1.00, (0.46, 0.38, 0.18))))
    col = mix_color(nt, col, (0.022, 0.040, 0.012), remap(nt, tip, 0.0, 0.45, 0.55, 0.0))
    col = mix_color(nt, col, (0.34, 0.36, 0.12), remap(nt, tip, 0.65, 1.0, 0.0, 0.30))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.62
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    translucent(nt, bsdf, (0.16, 0.30, 0.05), 0.22)
    return mat


def flower_material():
    mat, nt, bsdf, coord = new_surface("Wildflowers")
    # four meadow flowers by Tone: ox-eye daisy white, buttercup yellow,
    # knapweed purple and clover pink, each with its own coloured eye
    tone = attr(nt, "Tone")
    core = attr(nt, "Core")
    petal = ramp(nt, tone, ((0.0, (0.80, 0.80, 0.74)), (0.25, (0.80, 0.56, 0.03)),
                            (0.50, (0.36, 0.14, 0.50)), (0.75, (0.72, 0.30, 0.42))), constant=True)
    eye = ramp(nt, tone, ((0.0, (0.85, 0.55, 0.03)), (0.25, (0.55, 0.40, 0.02)),
                          (0.50, (0.25, 0.08, 0.30)), (0.75, (0.60, 0.22, 0.32))), constant=True)
    col = mix_color(nt, petal, eye, remap(nt, core, 0.55, 0.75, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    translucent(nt, bsdf, (0.6, 0.5, 0.3), 0.2)
    return mat


def foliage_material():
    mat, nt, bsdf, coord = new_surface("ShrubFoliage")
    # juniper (Tone < 0.4) blue-green and fine; hazel/bramble (0.4-0.8)
    # yellow-green; gorse (> 0.8) dark with yellow bloom; leaf clumps by
    # Voronoi, light on the tops, dark underneath
    tone = attr(nt, "Tone")
    nz = normal_xyz(nt)["Z"]
    col = ramp(nt, tone, ((0.00, (0.022, 0.065, 0.045)), (0.38, (0.035, 0.090, 0.055)),
                          (0.42, (0.075, 0.170, 0.030)), (0.78, (0.130, 0.240, 0.040)),
                          (0.82, (0.040, 0.085, 0.022)), (1.00, (0.050, 0.100, 0.025))))
    leaves = voronoi(nt, coord, 95.0)
    col = mix_color(nt, col, (0.008, 0.022, 0.008), remap(nt, leaves, 0.25, 0.55, 0.0, 0.6))
    col = mix_color(nt, col, (0.30, 0.42, 0.14), mul(nt, remap(nt, nz, 0.4, 0.9, 0.0, 0.3),
                                                     remap(nt, leaves, 0.15, 0.02, 0.0, 0.6)))
    bloom = mul(nt, remap(nt, voronoi(nt, coord, 60.0), 0.30, 0.16, 0.0, 1.0),
                remap(nt, tone, 0.80, 0.84, 0.0, 1.0),
                remap(nt, noise(nt, coord, 9.0, 2.0, 0.5), 0.40, 0.55, 0.3, 1.0))
    col = mix_color(nt, col, (0.85, 0.62, 0.04), bloom)
    col = mix_color(nt, col, (0.006, 0.016, 0.006), remap(nt, nz, -0.1, -0.7, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.78
    add_bump(nt, bsdf, leaves, 0.6, 0.006)
    translucent(nt, bsdf, (0.10, 0.25, 0.04), 0.15)
    return mat


def soil_material_render(dirt, tex, path):
    """The tile's ground, rebuilt on the render path: turf on top with a
    worn path, and on the cut sides a soil section by Depth below the
    hill's own surface (a turf lip, dark humus, roots) over horizons laid
    level in object Z (banded clay subsoil, a gravel bed, stony base)."""
    nt, bsdf, coord = fresh_nodes(dirt, keep=(tex,))
    nrm_map = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm_map.inputs["Color"])
    xyz = coord_xyz(nt, coord)
    z = xyz["Z"]
    nz = normal_xyz(nt)["Z"]
    depth = attr(nt, "Depth")

    # --- the section, bottom up, on wobbled level boundaries
    zb = add(nt, z, mul(nt, noise(nt, coord, 3.0, 2.0, 0.5), 0.03))
    bands = math_node(nt, "FRACT", add(nt, mul(nt, zb, 9.0),
                                       mul(nt, noise(nt, coord, 7.0, 2.0, 0.5), 0.35)))
    # subsoil: an ochre clay below, a paler loam above, faintly bedded
    clay = ramp(nt, bands, ((0.00, (0.30, 0.165, 0.065)), (0.45, (0.38, 0.215, 0.085)),
                            (0.60, (0.28, 0.150, 0.060)), (1.00, (0.33, 0.180, 0.070))))
    loam = ramp(nt, bands, ((0.00, (0.20, 0.135, 0.080)), (0.50, (0.255, 0.175, 0.105)),
                            (1.00, (0.21, 0.140, 0.082))))
    sub = mix_color(nt, clay, loam, remap(nt, zb, 0.19, 0.24, 0.0, 1.0))
    sub = mix_color(nt, sub, (0.15, 0.10, 0.06), remap(nt, noise(nt, coord, 18.0, 4.0, 0.6), 0.55, 0.75, 0.0, 0.5))
    # the odd pebble in the subsoil; a cobble bed under it
    cells = voronoi_node(nt, mapping(nt, warp(nt, coord, 30.0, 0.025), scale=(1.0, 1.0, 1.6)), 28.0)
    cell_x = coord_xyz(nt, cells.outputs["Color"])["X"]
    stone_pt = remap(nt, cells.outputs["Distance"], 0.36, 0.26, 0.0, 1.0)
    pebble = ramp(nt, cell_x, ((0.0, (0.13, 0.115, 0.10)), (0.5, (0.23, 0.205, 0.175)),
                               (1.0, (0.31, 0.28, 0.24))))
    pebble = mix_color(nt, pebble, (0.08, 0.07, 0.06), remap(nt, cells.outputs["Distance"], 0.30, 0.36, 0.0, 0.7))
    sparse = mul(nt, stone_pt, remap(nt, cell_x, 0.90, 0.93, 0.0, 1.0))
    sub = mix_color(nt, sub, pebble, sparse)
    gravel = mix_color(nt, (0.12, 0.085, 0.052), pebble, stone_pt)
    rock = ramp(nt, noise(nt, coord, 6.0, 4.0, 0.6), ((0.3, (0.12, 0.115, 0.11)), (0.7, (0.22, 0.21, 0.195))))
    joints = voronoi(nt, mapping(nt, coord, scale=(1.0, 1.0, 2.2)), 8.0, "DISTANCE_TO_EDGE")
    rock = mix_color(nt, rock, (0.04, 0.038, 0.035), remap(nt, joints, 0.025, 0.0, 0.0, 0.85))
    gravel_band = mul(nt, remap(nt, zb, 0.034, 0.044, 0.0, 1.0), remap(nt, zb, 0.095, 0.080, 0.0, 1.0))
    strata = mix_color(nt, sub, gravel, gravel_band)
    bed = remap(nt, zb, 0.042, 0.030, 0.0, 1.0)
    strata = mix_color(nt, strata, rock, bed)
    # humus and roots down from the top of the cut
    humus = ramp(nt, noise(nt, coord, 26.0, 3.0, 0.6), ((0.3, (0.040, 0.026, 0.015)),
                                                        (0.7, (0.085, 0.056, 0.030))))
    roots = noise(nt, mapping(nt, coord, scale=(30.0, 30.0, 3.0)), 6.0, 3.0, 0.6)
    humus = mix_color(nt, humus, (0.17, 0.12, 0.07), remap(nt, roots, 0.62, 0.72, 0.0, 0.6))
    dj = add(nt, depth, mul(nt, noise(nt, coord, 8.0, 2.0, 0.5), 0.03))
    strata = mix_color(nt, strata, (0.12, 0.075, 0.040), remap(nt, dj, 0.13, 0.085, 0.0, 0.85))
    wall = mix_color(nt, strata, humus, remap(nt, dj, 0.085, 0.060, 0.0, 1.0))

    # --- the turf on top
    patch = noise(nt, coord, 2.6, 4.0, 0.55)
    fine = noise(nt, coord, 70.0, 3.0, 0.6)
    turf = ramp(nt, patch, ((0.30, (0.032, 0.052, 0.016)), (0.50, (0.048, 0.078, 0.022)),
                            (0.68, (0.075, 0.100, 0.030)), (0.84, (0.13, 0.13, 0.050))))
    turf = mix_color(nt, turf, (0.060, 0.042, 0.024), remap(nt, fine, 0.60, 0.74, 0.0, 0.65))
    # the path: u along it, v across, the same closed form as FootPath
    vm_u = nt.nodes.new("ShaderNodeVectorMath")
    vm_u.operation = "DOT_PRODUCT"
    nt.links.new(coord, vm_u.inputs[0])
    vm_u.inputs[1].default_value = (path.c, path.s, 0.0)
    vm_v = nt.nodes.new("ShaderNodeVectorMath")
    vm_v.operation = "DOT_PRODUCT"
    nt.links.new(coord, vm_v.inputs[0])
    vm_v.inputs[1].default_value = (-path.s, path.c, 0.0)
    u = vm_u.outputs["Value"]
    v = vm_v.outputs["Value"]
    centre = add(nt, path.a,
                 mul(nt, math_node(nt, "SINE", add(nt, mul(nt, u, PATH_FREQ), path.p)), path.b),
                 mul(nt, math_node(nt, "SINE", add(nt, mul(nt, u, 2.7), 1.3)), PATH_WOBBLE))
    half = add(nt, PATH_HALF, mul(nt, math_node(nt, "SINE", add(nt, mul(nt, u, 9.0), 0.7)), 0.018))
    ragged = mul(nt, math_node(nt, "SUBTRACT", noise(nt, coord, 11.0, 3.0, 0.6), 0.5), 0.07)
    margin = math_node(nt, "SUBTRACT", add(nt, math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", v, centre)),
                                           ragged), half)
    on_path = remap(nt, margin, 0.0, -0.03, 0.0, 1.0)
    worn = remap(nt, margin, 0.06, 0.0, 0.0, 1.0)
    earth = ramp(nt, noise(nt, coord, 13.0, 4.0, 0.6), ((0.3, (0.130, 0.090, 0.052)),
                                                        (0.7, (0.215, 0.155, 0.092))))
    grit = voronoi_node(nt, coord, 120.0)
    grit_m = remap(nt, grit.outputs["Distance"], 0.22, 0.10, 0.0, 1.0)
    earth = mix_color(nt, earth, ramp(nt, coord_xyz(nt, grit.outputs["Color"])["X"],
                                      ((0.0, (0.22, 0.20, 0.18)), (1.0, (0.45, 0.42, 0.37)))),
                      mul(nt, grit_m, 0.8))
    top = mix_color(nt, turf, (0.085, 0.062, 0.036), mul(nt, worn, 0.55))
    top = mix_color(nt, top, earth, on_path)

    grassy = math_node(nt, "MAXIMUM", remap(nt, nz, 0.35, 0.65, 0.0, 1.0),
                       remap(nt, depth, 0.018, 0.008, 0.0, 1.0))
    col = mix_color(nt, wall, top, grassy)
    col = mix_color(nt, col, (0.03, 0.024, 0.018), remap(nt, nz, -0.5, -0.8, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    rough = add(nt, 0.80, mul(nt, math_node(nt, "SUBTRACT", 1.0, grassy), 0.15),
                mul(nt, on_path, grassy, -0.08))
    nt.links.new(rough, bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    wall_h = add(nt, mul(nt, math_node(nt, "MAXIMUM", sparse, mul(nt, stone_pt, gravel_band)), 0.8),
                 mul(nt, bands, 0.2), mul(nt, roots, 0.3), mul(nt, joints, bed, -3.0))
    top_h = add(nt, mul(nt, fine, 0.5), mul(nt, grit_m, on_path, 0.6))
    height = add(nt, mul(nt, wall_h, math_node(nt, "SUBTRACT", 1.0, grassy)), mul(nt, top_h, grassy))
    add_bump(nt, bsdf, height, 0.5, 0.006, normal=nrm_map.outputs["Normal"])


def stone_material_render(stone):
    """Weathered granite erratics: a grey per stone, three scales of noise,
    feldspar and mica speckle, crustose lichen on the lit tops, moss and a
    soil stain where the stone goes into the ground."""
    nt, bsdf, coord = fresh_nodes(stone)
    tone = attr(nt, "Tone")
    lift = attr(nt, "Lift")
    nz = normal_xyz(nt)["Z"]
    col = ramp(nt, tone, ((0.0, (0.155, 0.150, 0.142)), (0.40, (0.215, 0.205, 0.190)),
                          (0.75, (0.255, 0.235, 0.210)), (1.0, (0.190, 0.178, 0.168))))
    big = noise(nt, coord, 2.4, 4.0, 0.55)
    midn = noise(nt, coord, 9.0, 5.0, 0.6)
    speck = noise(nt, coord, 210.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.085, 0.082, 0.078), remap(nt, big, 0.42, 0.66, 0.0, 0.65))
    col = mix_color(nt, col, (0.33, 0.315, 0.29), remap(nt, midn, 0.52, 0.70, 0.0, 0.55))
    col = mix_color(nt, col, (0.045, 0.043, 0.04), remap(nt, speck, 0.60, 0.70, 0.0, 0.6))
    col = mix_color(nt, col, (0.46, 0.44, 0.41), remap(nt, speck, 0.34, 0.24, 0.0, 0.6))
    # rain streaks down the flanks
    streak = noise(nt, mapping(nt, coord, scale=(16.0, 16.0, 1.2)), 4.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.06, 0.058, 0.052), mul(nt, remap(nt, streak, 0.52, 0.68, 0.0, 0.55),
                                                         remap(nt, nz, 0.6, 0.2, 0.0, 1.0)))
    # crustose lichen: irregular blotches, pale grey-green and sulphur
    # yellow-green, on the up-facing stone; sparse orange spots
    up = remap(nt, nz, 0.05, 0.6, 0.0, 1.0)
    blot = noise(nt, coord, 16.0, 6.0, 0.7)
    where = remap(nt, noise(nt, coord, 3.5, 3.0, 0.55), 0.42, 0.56, 0.0, 1.0)
    lich = mul(nt, remap(nt, blot, 0.52, 0.58, 0.0, 1.0), where, up)
    lich_col = ramp(nt, noise(nt, coord, 6.0, 2.0, 0.5), ((0.35, (0.40, 0.43, 0.33)), (0.65, (0.46, 0.47, 0.20))))
    lich_col = mix_color(nt, lich_col, (0.26, 0.28, 0.20), remap(nt, blot, 0.58, 0.66, 0.0, 0.6))
    col = mix_color(nt, col, lich_col, mul(nt, lich, 0.9))
    gold = mul(nt, remap(nt, noise(nt, coord, 40.0, 4.0, 0.7), 0.60, 0.66, 0.0, 1.0),
               remap(nt, noise(nt, coord, 5.0, 2.0, 0.5), 0.56, 0.64, 0.0, 1.0), up)
    col = mix_color(nt, col, (0.55, 0.30, 0.06), mul(nt, gold, 0.85))
    # moss creeping up from the ground, highest in the shaded hollows
    creep = add(nt, lift, mul(nt, math_node(nt, "SUBTRACT", noise(nt, coord, 8.0, 4.0, 0.6), 0.5), 0.10),
                mul(nt, nz, 0.03))
    moss = remap(nt, creep, 0.07, 0.035, 0.0, 1.0)
    moss_col = ramp(nt, noise(nt, coord, 45.0, 3.0, 0.6), ((0.3, (0.045, 0.075, 0.016)),
                                                           (0.7, (0.12, 0.16, 0.035))))
    col = mix_color(nt, col, moss_col, moss)
    col = mix_color(nt, col, (0.05, 0.038, 0.026), remap(nt, lift, 0.022, 0.0, 0.0, 0.85))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, moss, 0.0, 1.0, 0.78, 0.95), bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    height = add(nt, mul(nt, big, 1.4), mul(nt, midn, 0.7), mul(nt, speck, 0.12), mul(nt, lich, 0.2),
                 mul(nt, moss, 0.3))
    add_bump(nt, bsdf, height, 0.45, 0.02)


def meadow_dressing(low, stones, ground, on_stone, path, stone_mat, seed=11):
    """Render-only meadow on the tile's up-facing ground: short turf in
    clumps of varied height and hue, taller grass ringing each stone where
    grazing cannot reach, a turf lip combed over the cut edge, drifts of
    wildflowers, three shrubs and pebbles along the path. Fixed seed;
    staging parented to the tile, never part of its budgets or export."""
    rng = random.Random(seed)
    lim = PATCH / 2.0 - 0.012
    G = Dress(("Tone", "Tip"))
    H = Dress(("Tone", "Core"))

    def site(x, y):
        if abs(x) > lim or abs(y) > lim or on_stone(x, y):
            return None
        z, _n = ground(x, y)
        return None if z is None else Vector((x, y, z - 0.004))

    def near_stone(x, y):
        return min(math.hypot(x - cx, y - cy) - r for cx, cy, r, _t in stones)

    def clump(root, n, h0, h1, tone, lean=(0.15, 0.55), spread=0.016, w=(0.0020, 0.0036)):
        for _ in range(n):
            ang = rng.uniform(0.0, 2.0 * math.pi)
            off = rng.uniform(0.0, spread)
            base = root + Vector((math.cos(ang) * off, math.sin(ang) * off, 0.0))
            tn = min(1.0, max(0.0, tone + rng.uniform(-0.12, 0.12)))
            if rng.random() < 0.07:
                tn = rng.uniform(0.9, 1.0)
            blade(G, base, ang + rng.uniform(-0.6, 0.6), rng.uniform(h0, h1), rng.uniform(*lean),
                  rng.uniform(*w), tn, twist=rng.uniform(-0.5, 0.5))

    # short turf, everywhere off the path; tone drifts in broad patches
    for _ in range(TURF_CLUMPS):
        x, y = rng.uniform(-lim, lim), rng.uniform(-lim, lim)
        m = path.margin(x, y)
        if m < -0.02 + rng.uniform(-0.02, 0.02):
            continue
        root = site(x, y)
        if root is None:
            continue
        patch = 0.5 + 0.5 * math.sin(3.1 * x + 0.7) * math.cos(2.6 * y - 0.4)
        sparse = m < 0.04
        clump(root, rng.randint(3, 6) if sparse else rng.randint(8, 14),
              0.020, 0.040 if sparse else 0.065, 0.25 + 0.55 * patch)

    # taller grass ringing every stone, where grazing and mowing miss
    for cx, cy, r, _top in stones:
        for _ in range(int(14 + 70 * r)):
            ang = rng.uniform(0.0, 2.0 * math.pi)
            rr = r * rng.uniform(0.80, 1.25)
            x, y = cx + rr * math.cos(ang), cy + rr * math.sin(ang)
            if path.margin(x, y) < 0.0:
                continue
            root = site(x, y)
            if root is None:
                continue
            clump(root, rng.randint(5, 10), 0.05, 0.13, rng.uniform(0.35, 0.85),
                  lean=(0.25, 0.6), spread=0.012, w=(0.0030, 0.0055))
            if rng.random() < 0.25:  # a seed stalk
                blade(G, root, ang, rng.uniform(0.12, 0.18), 0.12, 0.0016, 0.97)

    # the turf lip: blades rooted on the rounded rim, combed out and down
    # over the cut
    edge = PATCH / 2.0
    for sx, sy, ox, oy in ((1, 0, 0, -1), (1, 0, 0, 1), (0, 1, -1, 0), (0, 1, 1, 0)):
        s = -edge + 0.01
        while s < edge - 0.01:
            s += rng.uniform(0.006, 0.014)
            inset = rng.uniform(0.004, 0.030)
            x = sx * s + ox * (edge - inset)
            y = sy * s + oy * (edge - inset)
            if path.margin(x, y) < -0.01:
                continue
            z, _n = ground(x, y)
            if z is None:
                continue
            ang = math.atan2(oy, ox) + rng.uniform(-0.5, 0.5)
            tn = rng.uniform(0.2, 0.8) if rng.random() > 0.06 else 0.95
            blade(G, Vector((x, y, z - 0.003)), ang, rng.uniform(0.025, 0.060), rng.uniform(0.5, 1.0),
                  rng.uniform(0.0028, 0.0045), tn, droop=rng.uniform(0.2, 0.7),
                  twist=rng.uniform(-0.4, 0.4))

    # wildflower drifts: one kind per drift, a few strays
    placed = 0
    tries = 0
    while placed < FLOWERS and tries < FLOWERS * 30:
        tries += 1
        x, y = rng.uniform(-lim, lim), rng.uniform(-lim, lim)
        drift = math.sin(5.1 * x + 0.3) * math.cos(4.3 * y + 1.1) + 0.5 * math.sin(9.0 * x - 7.0 * y)
        if drift < 0.55 or path.margin(x, y) < 0.02 or near_stone(x, y) < 0.01:
            continue
        root = site(x, y)
        if root is None:
            continue
        kind = int(2.0 + 2.0 * math.sin(2.3 * x - 1.7 * y + 0.5)) % 4
        if rng.random() < 0.15:
            kind = rng.randrange(4)
        tone = 0.125 + 0.25 * kind
        h = rng.uniform(0.05, 0.11)
        head = blade(G, root, rng.uniform(0.0, 2.0 * math.pi), h, 0.12, 0.0016, 0.35)
        r = rng.uniform(0.009, 0.014) * (1.25 if kind == 0 else 1.0)
        tilt = Vector((rng.uniform(-0.35, 0.35), rng.uniform(-0.35, 0.35), 1.0)).normalized()
        a_ax = tilt.orthogonal().normalized()
        b_ax = tilt.cross(a_ax)
        c = H.vert(head + tilt * 0.002, tone, 1.0)
        petals = 10 if kind == 0 else 6
        ring = []
        for k in range(petals * 2):
            th = math.pi * k / petals
            rad = r if k % 2 == 0 else r * 0.45
            p = head + (a_ax * math.cos(th) + b_ax * math.sin(th)) * rad
            ring.append(H.vert(p, tone, 0.0 if k % 2 == 0 else 0.5))
        for k in range(len(ring)):
            H.face(c, ring[k], ring[(k + 1) % len(ring)])
        placed += 1

    # shrubs: three, where they clear the stones, the path and each other
    S = Dress(("Tone",))
    bushes = []
    cands = [(rng.uniform(-0.70, 0.70), rng.uniform(-0.70, 0.70)) for _ in range(400)]
    for _ in range(BUSHES):
        best = None
        for x, y in cands:
            clear = min(near_stone(x, y), path.margin(x, y),
                        min((math.hypot(x - bx, y - by) - 0.30 for bx, by in bushes), default=1.0))
            if best is None or clear > best[0]:
                best = (clear, x, y)
        bushes.append((best[1], best[2]))
    for n, (bx, by) in enumerate(bushes):
        tone = (0.2, 0.6, 0.92)[n % 3]
        R = 0.115 + 0.025 * n
        zs = [ground(bx + R * math.cos(a), by + R * math.sin(a))[0] for a in (0.0, 2.1, 4.2)]
        gz = min([z for z in zs if z is not None] + [ground(bx, by)[0]])
        dirs, quads = cube_sphere(3)
        # a dome of small leafy lumps, thinning toward the top
        for k in range(30):
            az = rng.uniform(0.0, 2.0 * math.pi)
            el = math.asin(rng.uniform(0.05, 0.95))
            d = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
            cen = Vector((bx, by, gz + R * 0.30)) + Vector((d.x * R * 0.80, d.y * R * 0.80, d.z * R * 0.85))
            ax = R * rng.uniform(0.28, 0.42)
            ph = rng.uniform(0.0, 6.0)
            tk = min(1.0, max(0.0, tone + rng.uniform(-0.04, 0.04)))
            ids = []
            for q in dirs:
                lump = (1.0 + 0.16 * math.sin(9.0 * q.x + 5.0 * q.y + ph) * math.cos(8.0 * q.z + ph)
                        + 0.08 * math.sin(17.0 * q.y - 13.0 * q.z + 2.0 * ph))
                ids.append(S.vert(cen + Vector((q.x * ax, q.y * ax, q.z * ax * 0.85)) * lump, tk))
            for q in quads:
                S.face(*[ids[i] for i in q])
        # a ring of tall grass round the shrub's foot
        for _ in range(16):
            a = rng.uniform(0.0, 2.0 * math.pi)
            root = site(bx + R * 1.15 * math.cos(a), by + R * 1.15 * math.sin(a))
            if root is not None:
                clump(root, rng.randint(4, 8), 0.05, 0.11, rng.uniform(0.3, 0.8))

    # pebbles: most on and beside the path, some in the grass
    P = Dress(("Tone", "Lift"))
    for k in range(PEBBLES):
        for _try in range(40):
            x, y = rng.uniform(-lim, lim), rng.uniform(-lim, lim)
            if k < PEBBLES * 0.7 and path.margin(x, y) > 0.015:
                continue
            root = site(x, y)
            if root is not None:
                break
        else:
            continue
        r = rng.uniform(0.007, 0.022)
        sx, sy, sz = r * rng.uniform(0.8, 1.3), r * rng.uniform(0.8, 1.2), r * rng.uniform(0.45, 0.7)
        rot = rng.uniform(0.0, 2 * math.pi)
        c, s = math.cos(rot), math.sin(rot)
        tn = rng.random()
        dirs, quads = cube_sphere(2)
        ids = []
        for d in dirs:
            px, py, pz = d.x * sx, d.y * sy, d.z * sz
            ids.append(P.vert(Vector((c * px - s * py, s * px + c * py, pz)) + root
                              + Vector((0.0, 0.0, 0.004 - sz * 0.35)), tn, 0.05))
        for q in quads:
            P.face(*[ids[i] for i in q])

    out = [G.build("MeadowGrass", grass_material()),
           H.build("Wildflowers", flower_material()),
           S.build("Shrubs", foliage_material(), smooth=True),
           P.build("Pebbles", stone_mat, smooth=True)]
    for ob in out:
        ob.parent = low
    return out


def render_still(low, dirt, tex, path, engine):
    scene = bpy.context.scene
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    stones, ground, on_stone = render_attributes(low)
    foot = choose_path(stones)
    print(f"render path a={foot.a:.3f} b={foot.b:.3f} p={foot.p:.3f} "
          f"clear={min(foot.margin(cx, cy) - r for cx, cy, r, _t in stones):.3f}")
    soil_material_render(dirt, tex, foot)
    stone_mat = low.data.materials[STONE_IDX]
    stone_material_render(stone_mat)
    dressing = meadow_dressing(low, stones, ground, on_stone, foot, stone_mat)
    for ob in dressing:
        scene.collection.objects.link(ob)
    print("render dressing " + " ".join(f"{ob.name}={len(ob.data.polygons)}f" for ob in dressing))
    low.rotation_euler.z = math.radians(HERO_YAW_DEG)
    bpy.context.view_layer.update()

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = bpy.data.materials.new("Floor")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.016, 0.017, 0.020, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    floor.location.z = -0.0005
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 8.5, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world
    centre = Vector((0.0, 0.0, 0.18))

    def light(name, offset, energy, size, col, target=None, spread=None):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        if spread is not None:
            ld.spread = math.radians(spread)
        ob = bpy.data.objects.new(name, ld)
        ob.location = centre + Vector(offset)
        aim_at = centre if target is None else Vector(target)
        ob.rotation_euler = (aim_at - ob.location).normalized().to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(ob)

    # Late-afternoon key from camera-left, low enough that the boulders and
    # grass throw shadows across the slope; cool fill from the right so no
    # stone face goes black; a back rim to separate the grass tips and the
    # turf lip; and the warm wedge on the backdrop behind.
    light("Key", (-2.2, -2.9, 3.4), 430.0, 2.5, (1.0, 0.93, 0.80), spread=35.0)
    light("Fill", (4.0, -2.2, 1.8), 130.0, 6.0, (0.72, 0.82, 1.0))
    light("Rim", (-0.6, 3.4, 2.4), 220.0, 3.0, (0.80, 0.88, 1.0))
    light("Wedge", (2.6, 3.6, 2.6), 420.0, 2.0, (1.0, 0.68, 0.40),
          target=(3.2, 5.5, 0.0), spread=40.0)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = HERO_CAM
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = HERO_AIM
    scene.collection.objects.link(aim)
    con = cam.constraints.new("TRACK_TO")
    con.target = aim
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    scene.camera = cam

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 32
        scene.cycles.device = "CPU"
    else:
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = (
        "WEBP" if path.lower().endswith(".webp") else "PNG"
    )
    if path.lower().endswith(".webp"):
        scene.render.image_settings.quality = 90
    scene.render.filepath = path
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(
        scene, cam, hero=[low], elements=[low], stage=[floor, wall],
    )
    if fcode:
        return fcode
    # asset-quality floors (examples/gallery_asset_quality.py) return 11,
    # which this piece's numbering already spends; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 26
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return fail("render produced no file", 14)
    return 0


HERO_YAW_DEG = -28.0
HERO_CAM = (2.33, -3.19, 2.42)
HERO_AIM = (0.0, 0.0, 0.05)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--poke-rock", action="store_true")
    p.add_argument("--float-rocks", action="store_true")
    p.add_argument("--box-rocks", action="store_true")
    p.add_argument("--pile-rocks", action="store_true")
    p.add_argument("--perch-rocks", action="store_true")
    p.add_argument("--uniform-rocks", action="store_true")
    p.add_argument("--sharp-rim", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, dirt, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        poke=args.poke_rock,
        float_up=args.float_rocks,
        box_rocks=args.box_rocks,
        pile=args.pile_rocks,
        perch=args.perch_rocks,
        uniform=args.uniform_rocks,
        sharp_rim=args.sharp_rim,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, dirt, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("terrain-scatter OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
