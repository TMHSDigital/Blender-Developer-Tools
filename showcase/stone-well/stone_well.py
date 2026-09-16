"""Game-ready stone well — a showcase piece, not an example.

Asserts budget conformance of a procedural well after composing shipped
pipeline pieces: bmesh construction, UVs, three materials, high-to-low
normal bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. ``--skip-decimate`` skips the LOD
DECIMATE stage so the LOD-ratio budget fails. ``--lift-z`` raises the
mesh so the grounded-zmin hygiene budget fails.

No RNG. Construction is closed-form (per-stone jitter is a deterministic
hash). DECIMATE COLLAPSE triangle counts are not byte-identical across
Blender versions — the LOD gate is a ratio band, not an exact count.

    blender --background --python stone_well.py --
    blender --background --python stone_well.py -- --skip-decimate
    blender --background --python stone_well.py -- --lift-z
    blender --background --python stone_well.py -- --output well.png
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

# Showcase lives at repo-root/showcase/, not under examples/. The framing
# helper is the repo's only shared import and lives next to the examples;
# resolve the repo root so we do not move gallery_framing.py.
_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

# Closed-form construction. OUTER_SIZE is the AABB of eaves + peak, compared
# against the measured world bbox — not assigned onto the mesh.
N_AROUND = 12
N_ROWS = 5
R_INNER = 0.40
STONE_D = 0.14
R_OUTER = R_INNER + STONE_D
R_MID = (R_INNER + R_OUTER) / 2.0
WALL_H = 0.72
STONE_H = WALL_H / N_ROWS
STONE_FACE_H = STONE_H * 0.90
# Top of the masonry is the top of the last course, not the nominal WALL_H:
# the curb seats on the measured course top so no daylight shows at the rim.
MASONRY_TOP = STONE_FACE_H + (N_ROWS - 1) * STONE_H
CURB_H = 0.065
CURB_OUT = 0.045
CURB_Z = MASONRY_TOP + CURB_H / 2.0
POST_S = 0.068
POST_R = 0.55
POST_H = 0.58
POST_BOTTOM = MASONRY_TOP + CURB_H
POST_TOP = POST_BOTTOM + POST_H
EAVE_OVERHANG = 0.22
EAVE_HALF = POST_R + POST_S / 2.0 + EAVE_OVERHANG
EAVE_Z = POST_TOP - 0.02
ROOF_RISE = 0.34
PEAK_Z = EAVE_Z + ROOF_RISE
SHINGLE_T = 0.016
WINDLASS_R = 0.045
# The windlass is the axle the posts are the bearings for: it passes through
# both posts and protrudes so the crank has something to attach to.
WINDLASS_END = POST_R + POST_S / 2.0 + 0.015
WINDLASS_LEN = 2.0 * WINDLASS_END
BUCKET_R_TOP = 0.105
BUCKET_R_BOT = 0.088
BUCKET_WALL_T = 0.008
BUCKET_H = 0.14
BUCKET_Z = 0.68
BUCKET_RIM_Z = BUCKET_Z + BUCKET_H / 2.0
HANDLE_BAR_Z = BUCKET_RIM_Z + 0.03
ROPE_R = 0.016
BBOX_TOL = 0.01
# Fitted to the generated AABB after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (1.640, 1.640, 1.761)

# Measured after locking geometry. DECIMATE COLLAPSE ratios diverge across
# series — bands, not exact counts. Tightened after the first 4.5/5.1/5.2 run.
BASE_TRIS_MIN = 8280
BASE_TRIS_MAX = 9500
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
GAP_MAX = 0.008
LIFT_Z = 0.05
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
STONE_FACES_MIN = 3000
WOOD_FACES_MIN = 600
METAL_FACES_MIN = 100
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 320
BAKE_RES = 256
CAGE_EXTRUSION = 0.06

STONE_IDX = 0
WOOD_IDX = 1
METAL_IDX = 2


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


def add_cone(
    bm, loc, radius1, radius2, depth, segments, mat_idx,
    euler=(0.0, 0.0, 0.0), cap_ends=True,
):
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=cap_ends,
        cap_tris=True,
        segments=segments,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
    )
    verts = geo["verts"]
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


def hash01(a, b, c):
    # Deterministic per-stone jitter. Closed-form, no RNG state.
    return math.sin(a * 127.1 + b * 311.7 + c * 74.7) * 43758.5453 % 1.0


def ring_verts(verts, z, eps=1e-6):
    return sorted(
        (v for v in verts if abs(v.co.z - z) < eps),
        key=lambda v: math.atan2(v.co.y, v.co.x),
    )


def add_open_bucket(bm, loc, r_bot, r_top, wall_t, depth, segments, mat_idx):
    """Open-topped tapered bucket: outer wall, inner wall, rim ring, floor.

    Manifold single shell. The bottom slab has real thickness: the inner
    floor sits FLOOR_T above the outer bottom disc, so every edge has
    exactly two faces.
    """
    floor_t = 0.012
    z0 = loc[2] - depth / 2.0
    z1 = loc[2] + depth / 2.0
    outer = add_cone(
        bm, loc, r_bot, r_top, depth, segments, mat_idx, cap_ends=False,
    )
    inner_loc = (loc[0], loc[1], loc[2] + floor_t / 2.0)
    inner = add_cone(
        bm, inner_loc, r_bot - wall_t, r_top - wall_t, depth - floor_t,
        segments, mat_idx, cap_ends=False,
    )
    ob = ring_verts(outer, z0)
    ot = ring_verts(outer, z1)
    ib = ring_verts(inner, z0 + floor_t)
    it = ring_verts(inner, z1)
    n = segments
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((ot[i], ot[j], it[j], it[i]))
        f.material_index = mat_idx
    # Inner floor faces up into the hollow; outer bottom disc faces down.
    ci = bm.verts.new((loc[0], loc[1], z0 + floor_t))
    co = bm.verts.new((loc[0], loc[1], z0))
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((ci, ib[i], ib[j]))
        f.material_index = mat_idx
        f = bm.faces.new((co, ob[j], ob[i]))
        f.material_index = mat_idx


def build_well_mesh(name, bevel_offset, bevel_segments):
    bm = bmesh.new()
    stone_verts = []
    wood_bevel_verts = []
    try:
        for row in range(N_ROWS):
            z = STONE_FACE_H / 2.0 + row * STONE_H
            rot_off = (row % 2) * (math.pi / N_AROUND)
            for i in range(N_AROUND):
                ang = 2.0 * math.pi * i / N_AROUND + rot_off
                # Seeded jitter: width and radial seat vary per stone, course
                # tops stay level so the curb seats flat.
                wj = 0.88 + 0.10 * (hash01(row, i, 0) - 0.5)
                rj = (hash01(row, i, 1) - 0.5) * 0.008
                stone_w = 2.0 * R_MID * math.tan(math.pi / N_AROUND) * wj
                loc = (
                    (R_MID + rj) * math.cos(ang),
                    (R_MID + rj) * math.sin(ang),
                    z,
                )
                stone_verts.extend(
                    add_box(
                        bm,
                        loc,
                        (STONE_D, stone_w, STONE_FACE_H),
                        STONE_IDX,
                        euler=(0.0, 0.0, ang),
                    )
                )

        curb_r = R_OUTER + CURB_OUT / 2.0
        curb_w = 2.0 * curb_r * math.tan(math.pi / N_AROUND) * 0.90
        for i in range(N_AROUND):
            ang = 2.0 * math.pi * i / N_AROUND
            loc = (curb_r * math.cos(ang), curb_r * math.sin(ang), CURB_Z)
            stone_verts.extend(
                add_box(
                    bm,
                    loc,
                    (STONE_D + CURB_OUT, curb_w, CURB_H),
                    STONE_IDX,
                    euler=(0.0, 0.0, ang),
                )
            )

        if bevel_offset > 0.0:
            edges = list({e for v in stone_verts for e in v.link_edges})
            bmesh.ops.bevel(
                bm,
                geom=edges,
                offset=bevel_offset,
                segments=bevel_segments,
                profile=0.5,
                affect="EDGES",
                clamp_overlap=True,
            )

        post_angles = (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0)
        for ang in post_angles:
            loc = (
                POST_R * math.cos(ang),
                POST_R * math.sin(ang),
                POST_BOTTOM + POST_H / 2.0,
            )
            wood_bevel_verts.extend(
                add_box(bm, loc, (POST_S, POST_S, POST_H), WOOD_IDX)
            )

        beam_z = POST_TOP - 0.05
        wood_bevel_verts.extend(
            add_box(
                bm,
                (0.0, 0.0, beam_z),
                (POST_R * 2.0 - POST_S, POST_S * 0.85, POST_S * 0.85),
                WOOD_IDX,
            )
        )
        add_cylinder(
            bm,
            (0.0, 0.0, beam_z),
            WINDLASS_R,
            WINDLASS_LEN,
            12,
            WOOD_IDX,
            euler=(0.0, math.pi / 2.0, 0.0),
        )
        # Crank: arm pinned to the protruding windlass end, grip parallel to
        # the windlass axis at the arm's lower end.
        add_box(
            bm,
            (WINDLASS_END + 0.004, 0.0, beam_z - 0.055),
            (0.020, 0.022, 0.13),
            METAL_IDX,
        )
        add_cylinder(
            bm,
            (WINDLASS_END + 0.055, 0.0, beam_z - 0.12),
            0.014,
            0.10,
            10,
            METAL_IDX,
            euler=(0.0, math.pi / 2.0, 0.0),
        )

        pitch = math.atan(ROOF_RISE / EAVE_HALF)
        r_base = EAVE_HALF * math.sqrt(2.0)
        add_cone(
            bm,
            (0.0, 0.0, (EAVE_Z + PEAK_Z) / 2.0),
            r_base,
            0.04,
            ROOF_RISE,
            4,
            WOOD_IDX,
            euler=(0.0, 0.0, math.pi / 4.0),
        )
        # Cap the open pit where the four shingle courses meet at the peak.
        add_cone(
            bm,
            (0.0, 0.0, PEAK_Z + 0.035),
            0.075,
            0.015,
            0.11,
            4,
            WOOD_IDX,
            euler=(0.0, 0.0, math.pi / 4.0),
        )
        nrm_local = Vector((0.0, ROOF_RISE, EAVE_HALF)).normalized()

        def add_course(yaw, t0, t1):
            rot = Euler((0.0, 0.0, yaw)).to_matrix()
            nrm = rot @ nrm_local

            def pt(t, s):
                w = EAVE_HALF * t
                y = t * EAVE_HALF
                z = PEAK_Z - t * ROOF_RISE
                return rot @ Vector((s * w, y, z))

            inner = SHINGLE_T * 0.12
            outer = SHINGLE_T * 1.05
            corners = (
                pt(t0, -1.0),
                pt(t0, 1.0),
                pt(t1, 1.0),
                pt(t1, -1.0),
            )
            vs = [bm.verts.new(c + nrm * inner) for c in corners]
            vs.extend(bm.verts.new(c + nrm * outer) for c in corners)
            idx = (
                (0, 1, 2, 3),
                (4, 7, 6, 5),
                (0, 4, 5, 1),
                (1, 5, 6, 2),
                (2, 6, 7, 3),
                (3, 7, 4, 0),
            )
            for a, b, c, d in idx:
                face = bm.faces.new((vs[a], vs[b], vs[c], vs[d]))
                face.material_index = WOOD_IDX

        n_rows = 5
        for side in range(4):
            yaw = side * (math.pi / 2.0)
            for row in range(n_rows):
                t0 = (row + 0.18) / n_rows
                t1 = (row + 1.08) / n_rows
                if t1 > 1.0:
                    t1 = 1.0
                add_course(yaw, t0, t1)
        fascia_h = 0.045
        fascia_t = 0.032
        # Butt joints: the X-running boards span the full eave; the Y-running
        # boards embed 2 mm into them. An exact flush butt lands board end
        # verts on the other board's corner verts (doubles at 1e-5).
        for side in range(4):
            yaw = side * (math.pi / 2.0)
            fx = EAVE_HALF * math.sin(yaw)
            fy = EAVE_HALF * math.cos(yaw)
            if side % 2 == 0:
                wood_bevel_verts.extend(
                    add_box(
                        bm,
                        (0.0, fy, EAVE_Z - fascia_h / 2.0),
                        (2.0 * EAVE_HALF + fascia_t, fascia_t, fascia_h),
                        WOOD_IDX,
                    )
                )
            else:
                wood_bevel_verts.extend(
                    add_box(
                        bm,
                        (fx, 0.0, EAVE_Z - fascia_h / 2.0),
                        (fascia_t, 2.0 * EAVE_HALF - fascia_t + 0.004, fascia_h),
                        WOOD_IDX,
                    )
                )

        if bevel_offset > 0.0:
            edges = list({e for v in wood_bevel_verts for e in v.link_edges})
            ret = bmesh.ops.bevel(
                bm,
                geom=edges,
                offset=min(bevel_offset, 0.006),
                segments=bevel_segments,
                profile=0.5,
                affect="EDGES",
                clamp_overlap=True,
            )
            for f in ret.get("faces") or []:
                f.material_index = WOOD_IDX

        # Rope ties off at the bail handle bar, not mid-air above the bucket.
        rope_top = beam_z - WINDLASS_R
        rope_bot = HANDLE_BAR_Z
        rope_h = rope_top - rope_bot
        add_cylinder(
            bm,
            (0.0, 0.0, (rope_top + rope_bot) / 2.0),
            ROPE_R,
            rope_h,
            8,
            WOOD_IDX,
        )
        add_open_bucket(
            bm,
            (0.0, 0.0, BUCKET_Z),
            BUCKET_R_BOT,
            BUCKET_R_TOP,
            BUCKET_WALL_T,
            BUCKET_H,
            12,
            WOOD_IDX,
        )

        def bucket_r_at(z):
            t = (z - (BUCKET_Z - BUCKET_H / 2.0)) / BUCKET_H
            return BUCKET_R_BOT + t * (BUCKET_R_TOP - BUCKET_R_BOT)

        for hz in (-BUCKET_H * 0.28, BUCKET_H * 0.28):
            add_cylinder(
                bm,
                (0.0, 0.0, BUCKET_Z + hz),
                bucket_r_at(BUCKET_Z + hz) + 0.004,
                0.018,
                12,
                METAL_IDX,
            )
        # Bail handle: legs pinned to the outside of the rim, bar across.
        for xs in (-1.0, 1.0):
            add_box(
                bm,
                (xs * (BUCKET_R_TOP + 0.006), 0.0, BUCKET_RIM_Z - 0.015),
                (0.014, 0.014, 0.09),
                METAL_IDX,
            )
        add_box(
            bm,
            (0.0, 0.0, HANDLE_BAR_Z),
            (2.0 * (BUCKET_R_TOP + 0.020), 0.014, 0.014),
            METAL_IDX,
        )

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = True
            if edge.is_manifold and len(edge.link_faces) == 2:
                if edge.calc_face_angle() > math.radians(35.0):
                    edge.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


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
        tex.inputs["Detail"].default_value = 8.0
        tex.inputs["Roughness"].default_value = 0.55
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = color
        mix.inputs["B"].default_value = wear
        fac = mix.inputs.get("Factor") or mix.inputs.get("Fac")
        nt.links.new(tex.outputs["Fac"], fac)
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
        rmix = nt.nodes.new("ShaderNodeMix")
        rmix.data_type = "FLOAT"
        rmix.inputs["A"].default_value = roughness
        rmix.inputs["B"].default_value = min(1.0, roughness + 0.18)
        rfac = rmix.inputs.get("Factor") or rmix.inputs.get("Fac")
        nt.links.new(tex.outputs["Fac"], rfac)
        nt.links.new(rmix.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def assign_slots(obj, stone, wood, metal):
    # Index-preserving: materials.clear() resets every polygon's
    # material_index to 0 (the piece would render all-stone). Assign by
    # slot position instead; the per-material face-count budgets in check()
    # prove the indices survive.
    mats = obj.data.materials
    wanted = (stone, wood, metal)
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
    zero_area = sum(1 for a in areas if a <= AREA_EPS)
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


def min_mat_distance(me, ia, ib):
    """Closest surface distance between two material islands via BVH.

    Vert-vert distance is the wrong metric for thin parts: a face interior
    can touch while its corner verts sit a radius apart.
    """
    bm_a = bmesh.new()
    bm_b = bmesh.new()
    try:
        bm_a.from_mesh(me)
        bm_b.from_mesh(me)
        bm_a.faces.ensure_lookup_table()
        bm_b.faces.ensure_lookup_table()
        drop_a = [f for f in bm_a.faces if f.material_index != ia]
        drop_b = [f for f in bm_b.faces if f.material_index != ib]
        if drop_a:
            bmesh.ops.delete(bm_a, geom=drop_a, context="FACES")
        if drop_b:
            bmesh.ops.delete(bm_b, geom=drop_b, context="FACES")
        if not bm_a.faces or not bm_b.faces:
            return 1e9
        tree = BVHTree.FromBMesh(bm_b)
        best = 1e9
        for src in list(bm_a.verts) + list(bm_a.faces):
            co = src.co if hasattr(src, "co") else src.calc_center_median()
            hit = tree.find_nearest(co)
            if hit[0] is None:
                continue
            best = min(best, hit[3])
        return best
    finally:
        bm_a.free()
        bm_b.free()


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
    img = bpy.data.images.new("WellNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = STONE_IDX
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


def check(skip_decimate, lift_z=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_well_mesh("WellLow", bevel_offset=0.010, bevel_segments=2)
    high = build_well_mesh("WellHigh", bevel_offset=0.010, bevel_segments=4)
    stone = principled(
        "WellStone", (0.40, 0.42, 0.46, 1.0), 0.0, 0.84,
        noise_scale=9.0, wear=(0.29, 0.30, 0.33, 1.0),
    )
    wood = principled(
        "WellWood", (0.48, 0.22, 0.07, 1.0), 0.0, 0.50,
        noise_scale=7.0, wear=(0.30, 0.13, 0.04, 1.0),
    )
    metal = principled(
        "WellMetal", (0.62, 0.58, 0.48, 1.0), 1.0, 0.30,
        noise_scale=5.0, wear=(0.34, 0.32, 0.27, 1.0),
    )
    assign_slots(low, stone, wood, metal)
    assign_slots(high, stone, wood, metal)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("well mesh did not build", 3), None, None, None, None, None

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

    img, tex = setup_bake_image(low, stone)
    if img is None:
        return fail("well has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "WellLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "WellLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(low, "WellCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_stone_well_{os.getpid()}.glb",
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
    gap_sw = min_mat_distance(low.data, STONE_IDX, WOOD_IDX)
    gap_mw = min_mat_distance(low.data, METAL_IDX, WOOD_IDX)
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} euler={hyg['euler']}"
    )
    print(f"measured gap_stone_wood={gap_sw:.5f} gap_metal_wood={gap_mw:.5f}")

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
    if gap_sw > GAP_MAX:
        return fail(
            f"stone-wood gap {gap_sw:.5f} > {GAP_MAX} "
            "(posts must seat on the curb)",
            17,
        ), None, None, None, None, None
    if gap_mw > GAP_MAX:
        return fail(
            f"metal-wood gap {gap_mw:.5f} > {GAP_MAX} "
            "(crank, hoops, and bail must touch the wood they mount to)",
            17,
        ), None, None, None, None, None
    return 0, low, high, stone, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, stone, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(stone, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(-28.0)
    low.rotation_euler.x = math.radians(2.0)

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
    cam.location = (3.10, -4.45, 2.12)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, OUTER_SIZE[2] / 2.0)
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
    args = p.parse_args(argv)

    code, low, _high, stone, tex, _col = check(
        args.skip_decimate, lift_z=args.lift_z
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, stone, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("stone-well OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
