"""Game-ready wooden ladder — a showcase piece, not an example.

Asserts budget conformance of a procedural timber ladder after composing
shipped pipeline pieces: bmesh construction, UVs, two materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates exactly one
named budget: ``--skip-decimate`` skips the LOD DECIMATE stage so the
LOD-ratio budget fails, ``--lift-z`` moves the mesh off the floor so the
grounded budget fails, ``--stray-vert`` adds one unconnected vertex so the
mesh-hygiene budget fails, and ``--fat-rungs`` widens the dowels to the
full stile depth so the rung-to-stile joint-fit budget fails.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python wooden_ladder.py --
    blender --background --python wooden_ladder.py -- --skip-decimate
    blender --background --python wooden_ladder.py -- --lift-z
    blender --background --python wooden_ladder.py -- --stray-vert
    blender --background --python wooden_ladder.py -- --fat-rungs
    blender --background --python wooden_ladder.py -- --output ladder.png
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

# Showcase lives at repo-root/showcase/, not under examples/. The framing
# helper is the repo's only shared import and lives next to the examples;
# resolve the repo root so we do not move gallery_framing.py.
_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

STILE_H = 1.48
STILE_W = 0.058
STILE_D = 0.034
SPAN = 0.34
N_RUNGS = 6
# A 26 mm dowel in a 34 mm stile. Sized so the widest rung still clears the
# stile's 2.5 mm chamfer by more than a millimetre; at 17 mm the dowel was as
# deep as the stile and broke through the front and back chamfers as a spike.
RUNG_R = 0.013
RUNG_SEGS = 12
RUNG_TENON = 0.012
RUNG_RADIUS_SCALE = (0.98, 1.02, 0.99, 1.03, 0.97, 1.01)
RUNG_Z_OFFSETS = (0.0, 0.0015, -0.0010, 0.0010, -0.0015, 0.0)
TOP_CAP_H = 0.025
SHOE_H = 0.065
SHOE_W = 0.074
SHOE_D = 0.070
RAKE = math.radians(12.0)
BBOX_TOL = 0.01
# 2 stiles + 6 rungs + 2 top caps + 2 shoes, each a closed shell.
PART_COUNT = 12
# Measured joint contract. Clearance exceeds the 2.5 mm chamfer so the dowel
# stays on the stile's flat face; engagement keeps the tenon seated; breakout
# keeps it from reaching the outer face.
RUNG_DEPTH_CLEARANCE = 0.003
TENON_ENGAGE_MIN = 0.006
TENON_BREAKOUT_MIN = 0.005
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
LIFT_Z = 0.05
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.472, 0.365, 1.460)

BASE_TRIS_MIN = 900
BASE_TRIS_MAX = 975
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
CAGE_EXTRUSION = 0.06
# The caps and shoes carry far more chamfer than body faces, so a floor above
# their 24 unbevelled box faces is what catches a bevel whose new faces fell
# back to the wood slot.
METAL_FACES_MIN = 180
WOOD_FACES_MIN = 280

WOOD_IDX = 0
METAL_IDX = 1


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def evaluated_triangle_count(obj):
    # Duplicated from snippets/lod_chain.py / decimate_to_budget.py (not a package).
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        eval_mesh.calc_loop_triangles()
        return len(eval_mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()


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


def add_cone(bm, loc, radius1, radius2, depth, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=True,
        segments=segments,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
    )
    verts = list(geo["verts"])
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


def add_cylinder(bm, loc, radius, depth, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    return add_cone(bm, loc, radius, radius, depth, segments, mat_idx, euler=euler)


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


def build_ladder_mesh(name, bevel_offset, bevel_segments, rung_radius=RUNG_R):
    bm = bmesh.new()
    stile_verts = []
    metal_faces = set()
    metal_verts = []
    try:
        half = SPAN / 2.0 + STILE_W / 2.0
        for sign in (-1.0, 1.0):
            stile_verts.extend(
                add_box(
                    bm,
                    (sign * half, 0.0, STILE_H / 2.0),
                    (STILE_W, STILE_D, STILE_H),
                    WOOD_IDX,
                )
            )

        z0 = 0.16
        z1 = STILE_H - 0.14
        for i in range(N_RUNGS):
            t = i / (N_RUNGS - 1)
            z = z0 + t * (z1 - z0) + RUNG_Z_OFFSETS[i]
            # Tenons stop inside the stile, so the rung rims never reach the
            # chamfered outer face. Rungs stay unbeveled: they are already
            # round, and beveling a cap rim spikes through that chamfer.
            add_cylinder(
                bm,
                (0.0, 0.0, z),
                rung_radius * RUNG_RADIUS_SCALE[i],
                SPAN + 2.0 * RUNG_TENON,
                RUNG_SEGS,
                WOOD_IDX,
                euler=(0.0, math.pi / 2.0, 0.0),
            )

        if bevel_offset > 0.0:
            edges = list(
                {
                    edge
                    for vertex in stile_verts
                    for edge in vertex.link_edges
                    if vertex.is_valid
                }
            )
            if edges:
                bmesh.ops.bevel(
                    bm,
                    geom=edges,
                    offset=bevel_offset,
                    segments=bevel_segments,
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
                )

        before = set(bm.faces)
        for sign in (-1.0, 1.0):
            hx = sign * half
            metal_verts.extend(
                add_box(
                    bm,
                    (hx, 0.0, STILE_H - TOP_CAP_H * 0.30),
                    (STILE_W + 0.010, STILE_D + 0.010, TOP_CAP_H),
                    METAL_IDX,
                )
            )
        metal_faces.update(set(bm.faces) - before)

        rake = Euler((RAKE, 0.0, 0.0)).to_matrix()
        for v in bm.verts:
            v.co = rake @ v.co
        zs = [v.co.z for v in bm.verts]
        zmin = min(zs)
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy
            v.co.z -= zmin

        before = set(bm.faces)
        for sign in (-1.0, 1.0):
            bottom = rake @ Vector((sign * half, 0.0, 0.0))
            bottom.x -= cx
            bottom.y -= cy
            bottom.z -= zmin
            metal_verts.extend(
                add_box(
                    bm,
                    (bottom.x, bottom.y, SHOE_H / 2.0),
                    (SHOE_W, SHOE_D, SHOE_H),
                    METAL_IDX,
                )
            )
        metal_faces.update(set(bm.faces) - before)

        if bevel_offset > 0.0:
            metal_edges = list(
                {
                    edge
                    for vertex in metal_verts
                    for edge in vertex.link_edges
                    if vertex.is_valid
                }
            )
            if metal_edges:
                # Bevel does not inherit material_index onto the faces it
                # creates, so claim them from the op's own return rather than
                # from a pre-bevel face snapshot. Without this every chamfer
                # on a cap or shoe falls back to slot 0 and renders as wood.
                bevelled = bmesh.ops.bevel(
                    bm,
                    geom=metal_edges,
                    offset=min(bevel_offset, 0.002),
                    segments=bevel_segments,
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
                )
                metal_faces.update(bevelled.get("faces") or [])

        ys = [v.co.y for v in bm.verts]
        final_cy = 0.5 * (min(ys) + max(ys))
        for v in bm.verts:
            v.co.y -= final_cy

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = True
            if edge.is_manifold and len(edge.link_faces) == 2:
                if edge.calc_face_angle() > math.radians(40.0):
                    edge.smooth = False
        for f in metal_faces:
            if f.is_valid:
                f.material_index = METAL_IDX
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def principled(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def assign_slots(obj, wood, metal):
    mats = obj.data.materials
    wanted = (wood, metal)
    for i, mat in enumerate(wanted):
        if i < len(mats):
            mats[i] = mat
        else:
            mats.append(mat)


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


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
    # Combinatorics match examples/mesh-hygiene-audit.audit (copied, not imported).
    nv, ne, nf = len(me.vertices), len(me.edges), len(me.polygons)
    ngons = sum(1 for p in me.polygons if len(p.vertices) > 4)
    areas = [face_area(me, p) for p in me.polygons]
    zero_area = sum(1 for area in areas if area <= AREA_EPS)
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        loose_v = sum(1 for v in bm.verts if len(v.link_edges) == 0)
        loose_e = sum(1 for e in bm.edges if len(e.link_faces) == 0)
        nonman = sum(1 for e in bm.edges if not e.is_manifold)
        ret = bmesh.ops.find_doubles(bm, verts=list(bm.verts), dist=DOUBLES_EPS)
        doubles = len(ret.get("targetmap") or {})
    finally:
        bm.free()
    return {
        "nv": nv,
        "ne": ne,
        "nf": nf,
        "ngons": ngons,
        "loose_v": loose_v,
        "loose_e": loose_e,
        "nonman": nonman,
        "zero_area": zero_area,
        "doubles": doubles,
        "euler": nv - ne + nf,
    }


def mesh_components(me):
    """Per-part AABBs in the construction frame, un-raked so the stiles read
    axis-aligned. The parts interpenetrate but share no vertices, so edge
    connectivity separates them."""
    neighbors = [[] for _ in range(len(me.vertices))]
    for edge in me.edges:
        a, b = edge.vertices
        neighbors[a].append(b)
        neighbors[b].append(a)
    unrake = Euler((-RAKE, 0.0, 0.0)).to_matrix()
    seen = [False] * len(me.vertices)
    parts = []
    for start in range(len(me.vertices)):
        if seen[start]:
            continue
        seen[start] = True
        stack = [start]
        points = []
        while stack:
            current = stack.pop()
            points.append(unrake @ me.vertices[current].co)
            for nxt in neighbors[current]:
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(nxt)
        lo = Vector(
            (
                min(p.x for p in points),
                min(p.y for p in points),
                min(p.z for p in points),
            )
        )
        hi = Vector(
            (
                max(p.x for p in points),
                max(p.y for p in points),
                max(p.z for p in points),
            )
        )
        parts.append((lo, hi))
    return parts


def joint_audit(me):
    """Worst-case rung-to-stile fit, recomputed from vertex positions."""
    parts = mesh_components(me)
    stiles = [p for p in parts if (p[1].z - p[0].z) > STILE_H * 0.8]
    rungs = [p for p in parts if (p[1].x - p[0].x) > SPAN]
    if len(stiles) != 2 or len(rungs) != N_RUNGS:
        return {
            "parts": len(parts),
            "stiles": len(stiles),
            "rungs": len(rungs),
            "clearance": -1.0,
            "engage": -1.0,
            "breakout": -1.0,
        }
    left = min(stiles, key=lambda p: p[0].x)
    right = max(stiles, key=lambda p: p[0].x)
    clearance = min(
        min(
            (stile[1].y - stile[0].y) - (rung[1].y - rung[0].y)
            for stile in (left, right)
        )
        * 0.5
        for rung in rungs
    )
    engage = min(
        min(left[1].x - rung[0].x, rung[1].x - right[0].x) for rung in rungs
    )
    breakout = min(
        min(rung[0].x - left[0].x, right[1].x - rung[1].x) for rung in rungs
    )
    return {
        "parts": len(parts),
        "stiles": len(stiles),
        "rungs": len(rungs),
        "clearance": clearance,
        "engage": engage,
        "breakout": breakout,
    }


def add_stray_vert(me):
    # Falsification only: one unconnected vertex, placed inside the existing
    # bounds so the bbox budget still passes and the hygiene budget is the
    # gate that fires.
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, STILE_H / 3.0))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


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
    # Duplicated from snippets/convex_hull_collider.py (not a package).
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
    # Adapted from snippets/setup_bake_target_image.py — do not replace slots.
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("LadderNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = WOOD_IDX
    return img, tex


def bake_normal(high, low):
    # Duplicated from snippets/bake_normal_high_to_low.py (not a package).
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
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
    # Duplicated from snippets/export_preset_unity.py (not a package).
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
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


def check(skip_decimate, lift_z=False, stray_vert=False, fat_rungs=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # Falsification: a dowel as deep as the stile, which is what used to break
    # through the front and back chamfers.
    rung_radius = STILE_D / 2.0 if fat_rungs else RUNG_R
    low = build_ladder_mesh(
        "LadderLow", bevel_offset=0.0025, bevel_segments=2, rung_radius=rung_radius
    )
    high = build_ladder_mesh(
        "LadderHigh", bevel_offset=0.0025, bevel_segments=4, rung_radius=rung_radius
    )
    if lift_z:
        low.location.z += LIFT_Z
    if stray_vert:
        add_stray_vert(low.data)
    # world_bbox reads matrix_world, which is evaluated data. Without this the
    # cached matrix hides a moved object and the grounded budget cannot fail.
    bpy.context.view_layer.update()
    wood = principled("LadderWood", (0.42, 0.24, 0.10, 1.0), 0.0, 0.55)
    metal = principled("LadderMetal", (0.48, 0.46, 0.42, 1.0), 1.0, 0.28)
    assign_slots(low, wood, metal)
    assign_slots(high, wood, metal)

    if low.data is None or len(low.data.polygons) < 6:
        return fail("ladder mesh did not build", 3), None, None, None, None, None

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

    img, tex = setup_bake_image(low, wood)
    if img is None:
        return fail("ladder has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "LadderLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "LadderLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_ladder_mesh("LadderColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "LadderCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_wooden_ladder_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0

    print(
        f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}"
    )
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
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} euler={hyg['euler']}"
    )
    joint = joint_audit(low.data)
    print(
        f"measured joints parts={joint['parts']} stiles={joint['stiles']} "
        f"rungs={joint['rungs']} clearance={joint['clearance']:.5f} "
        f"engage={joint['engage']:.5f} breakout={joint['breakout']:.5f}"
    )

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
    if idx_counts.get(WOOD_IDX, 0) < WOOD_FACES_MIN:
        return fail(
            f"wood faces {idx_counts.get(WOOD_IDX, 0)} < {WOOD_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(METAL_IDX, 0) < METAL_FACES_MIN:
        return fail(
            f"metal faces {idx_counts.get(METAL_IDX, 0)} < {METAL_FACES_MIN}",
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
        hyg["loose_v"]
        or hyg["loose_e"]
        or hyg["nonman"]
        or hyg["zero_area"]
        or hyg["doubles"]
        or hyg["ngons"]
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']}",
            15,
        ), None, None, None, None, None
    if abs(bb[2]) > ZMIN_EPS:
        return fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ), None, None, None, None, None
    if joint["parts"] != PART_COUNT:
        return fail(
            f"part count {joint['parts']} != {PART_COUNT} "
            f"(stiles={joint['stiles']} rungs={joint['rungs']})",
            17,
        ), None, None, None, None, None
    if joint["clearance"] < RUNG_DEPTH_CLEARANCE:
        return fail(
            f"rung-to-stile depth clearance {joint['clearance']:.5f} < "
            f"{RUNG_DEPTH_CLEARANCE} (--fat-rungs is the designed fail)",
            17,
        ), None, None, None, None, None
    if joint["engage"] < TENON_ENGAGE_MIN:
        return fail(
            f"tenon engagement {joint['engage']:.5f} < {TENON_ENGAGE_MIN}",
            17,
        ), None, None, None, None, None
    if joint["breakout"] < TENON_BREAKOUT_MIN:
        return fail(
            f"tenon breakout margin {joint['breakout']:.5f} < "
            f"{TENON_BREAKOUT_MIN}",
            17,
        ), None, None, None, None, None
    return 0, low, high, wood, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, wood, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(wood, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(-28.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        # Oversized so no edge of the set can enter frame; the committed hero
        # used to show the wall's left edge as a bright band in the corner.
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60.0)
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

    light("Key", (-3.6, -5.0, 5.4), 660.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.4, 2.4), 46.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.2, 4.0, 3.8), 600.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.55, -3.55, 1.38)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.74)
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
    p.add_argument(
        "--skip-decimate",
        action="store_true",
        help="falsification: skip the LOD DECIMATE stage",
    )
    p.add_argument(
        "--lift-z",
        action="store_true",
        help="falsification: lift the mesh so zmin fails the grounded budget",
    )
    p.add_argument(
        "--stray-vert",
        action="store_true",
        help="falsification: add a loose vertex so the hygiene budget fails",
    )
    p.add_argument(
        "--fat-rungs",
        action="store_true",
        help="falsification: dowels as deep as the stile, failing joint fit",
    )
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        fat_rungs=args.fat_rungs,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("wooden-ladder OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
