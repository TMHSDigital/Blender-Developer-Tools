"""Game-ready GN terrain scatter — a showcase piece, not an example.

Asserts budget conformance of a Geometry Nodes hill grid with instanced
rocks after composing shipped pipeline pieces: GN construction,
UVs, two materials, high-to-low normal bake, LOD chain, convex collider,
Unity glTF export.

GN still builds the sine hill and the Index-jittered instance grid.
Realized cubes are replaced with closed-form cleaved, faceted stones,
relaxed apart so no two interpenetrate, seated on sampled dirt Z, then
clamped above the slab floor.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` LOD, ``--stray-vert`` hygiene, ``--lift-z``
zmin, ``--poke-rock`` stone floor, ``--float-rocks`` seat, ``--box-rocks``
stone shell faces, ``--pile-rocks`` stone-to-stone interpenetration.

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
OUTER_SIZE = (1.800, 1.800, 0.584)
BASE_TRIS_MIN = 1400
BASE_TRIS_MAX = 2800
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

# Stones are kept apart by relaxing their centres to at least twice a
# bound on any stone's horizontal radius. The GN scatter jitters by up to
# 0.22 m on a 0.575 m grid, which pushed neighbours into each other: two
# pairs interpenetrated in the committed piece. The bound covers the
# largest ellipsoid semi-axis (0.135), the surface bump (0.016) and the
# lean tilt, so any two relaxed stones clear by construction.
# Stones are ROCK_SCALE times the base ellipsoid: cleaving takes a third of
# the volume off, and at 1.0 the cleaved stones read as pebbles on a slab.
ROCK_SCALE = 1.35
STONE_R_BOUND = ROCK_SCALE * (0.135 + 0.016 + 0.22 * 0.095)
STONE_CLEAR = 0.02
RELAX_ITERS = 40
PILE_PULL = 0.40
# Each rock is cleaved by a few planes through its ellipsoid, so it reads
# as broken stone with flat faces rather than a smooth egg.
N_CLEAVES = 5
CLEAVE_DEPTH = 0.62


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


def build_scatter_tree(verts, dirt, stone):
    tree = bpy.data.node_groups.new("TerrainScatter", "GeometryNodeTree")
    tree.interface.new_socket(
        name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry",
    )
    go = tree.nodes.new("NodeGroupOutput")

    hill = hill_z_socket(tree, FREQ, AMP)
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


def slabify(bm, floor_z=0.0):
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    boundary = [e for e in bm.edges if e.is_boundary]
    if not boundary:
        return
    ret = bmesh.ops.extrude_edge_only(bm, edges=boundary)
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


def add_seated_stone(bm, cx, cy, dirt_z, box_rocks, poke, float_up):
    sx = ROCK_SCALE * (0.11 + 0.025 * math.sin(cx * 8.1))
    sy = ROCK_SCALE * (0.10 + 0.022 * math.cos(cy * 6.4))
    sz = ROCK_SCALE * (0.075 + 0.020 * math.sin(cx * 4.2 + cy * 3.1))
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
        geo = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
        verts = geo["verts"]
        for v in verts:
            p = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz))
            if p.length > 1e-8:
                bump = ROCK_SCALE * 0.016 * math.sin(p.x * 26.0 + cx * 5.0) * math.cos(
                    p.y * 21.0 + cy * 4.0
                )
                p += p.normalized() * bump
            v.co = rot @ p
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
    for v in verts:
        v.co.x += cx
        v.co.y += cy
        v.co.z += dz
        if not poke and v.co.z < ROCK_ZMIN:
            v.co.z = ROCK_ZMIN


def relax_centres(specs, half_span):
    """Push stone centres apart to 2*STONE_R_BOUND + STONE_CLEAR, deterministically.

    Pairwise, symmetric, fixed iteration count, and clamped so every stone
    stays on the tile with its bound inside the edge.
    """
    pts = [Vector((x, y)) for x, y in specs]
    need = 2.0 * STONE_R_BOUND + STONE_CLEAR
    lim = half_span - STONE_R_BOUND - STONE_CLEAR
    for _ in range(RELAX_ITERS):
        moved = False
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
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
        for p in pts:
            p.x = max(-lim, min(lim, p.x))
            p.y = max(-lim, min(lim, p.y))
        if not moved:
            break
    return [(p.x, p.y) for p in pts]


def masonry_from_cubes(bm, box_rocks=False, poke=False, float_up=False, pile=False):
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
    if pile:
        # Falsifier: no relaxation, and the scatter drawn in toward the
        # middle so neighbours collide. Skipping relaxation alone proves
        # nothing once the stones are cleaved small enough to miss.
        local = [(x * PILE_PULL, y * PILE_PULL) for x, y in local]
    else:
        local = relax_centres(local, PATCH / 2.0)
    specs = [(x + span_c[0], y + span_c[1]) for x, y in local]
    for cx, cy in specs:
        dirt_z = nearest_dirt_z(bm, cx, cy)
        add_seated_stone(bm, cx, cy, dirt_z, box_rocks, poke, float_up)


def build_terrain_mesh(
    name,
    grid_verts,
    dirt,
    stone,
    box_rocks=False,
    poke=False,
    float_up=False,
    pile=False,
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
        slabify(bm, floor_z=0.0)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        masonry_from_cubes(bm, box_rocks=box_rocks, poke=poke, float_up=float_up, pile=pile)
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
        # Broken rock is faceted; smooth shading made the cleaved stones
        # read as eggs again. Nothing on this tile is smooth-shaded.
        for face in bm.faces:
            face.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        for poly in me.polygons:
            poly.use_smooth = False
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


def mottled(name, dark, light, rough_lo, rough_hi, scale, fine, bump):
    """Object-space mottle for colour, fine noise for roughness and bump."""
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
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
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
    )
    stone = mottled(
        "TerrainStone", (0.20, 0.195, 0.18, 1.0), (0.40, 0.38, 0.34, 1.0),
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
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        result = bmesh.ops.convex_hull(bm, input=list(bm.verts))
        interior = result.get("geom_interior") or []
        unused = result.get("geom_unused") or []
        if interior:
            bmesh.ops.delete(bm, geom=interior, context="VERTS")
        if unused:
            bmesh.ops.delete(bm, geom=unused, context="VERTS")
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
    deselect_all()
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=path,
        use_selection=True,
        export_yup=True,
        export_apply=True,
        export_draco_mesh_compression_enable=False,
        export_animations=False,
    )


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
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    dirt, stone = terrain_materials()
    kw = dict(box_rocks=box_rocks, poke=poke, float_up=float_up, pile=pile)
    low = build_terrain_mesh("TerrainLow", 21, dirt, stone, **kw)
    high = build_terrain_mesh("TerrainHigh", 25, dirt, stone, **kw)
    assign_slots(low, dirt, stone)
    assign_slots(high, dirt, stone)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
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

    collider_src = build_terrain_mesh(
        "TerrainColSrc", 21, dirt, stone, **kw
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


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, dirt, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(dirt, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(-28.0)
    low.rotation_euler.x = math.radians(0.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=14.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = bpy.data.materials.new("Floor")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 8.5, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02, 0.021, 0.025, 1.0,
    )
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", (-3.6, -5.0, 5.8), 680.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.6, 2.6), 48.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.4, 4.2, 4.1), 640.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.57, -3.51, 2.24)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.24)
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
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
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
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return fail("render produced no file", 14)
    return 0


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
    args = p.parse_args(argv)

    code, low, _high, dirt, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        poke=args.poke_rock,
        float_up=args.float_rocks,
        box_rocks=args.box_rocks,
        pile=args.pile_rocks,
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
