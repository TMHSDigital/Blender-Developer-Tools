"""Game-ready stone well — a showcase piece, not an example.

Asserts budget conformance of a procedural well after composing shipped
pipeline pieces: bmesh construction, UVs, three materials, high-to-low
normal bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier flag breaks one
stage so a named budget fails and the piece exits that budget's code:
``--skip-decimate`` (LOD ratio, 9), ``--lift-z`` (AABB grounded, 16),
``--float-stone`` (named supports, 16), ``--stand-posts`` (coplanar
cross-shell pairs, 15), ``--shallow-tenon`` (post tenon band, 18),
``--drop-bucket`` (bucket clearance, 18), ``--turn-posts`` (post under
hip corner, 19). See README.md for why two of them are aimed the way
they are.

No RNG. Construction is closed-form (per-stone jitter is a deterministic
hash). DECIMATE COLLAPSE triangle counts are not byte-identical across
Blender versions — the LOD gate is a ratio band, not an exact count.

    blender --background --python stone_well.py --
    blender --background --python stone_well.py -- --skip-decimate
    blender --background --python stone_well.py -- --stand-posts
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
# Posts land under the roof's four hip corners, not at the midpoint of each
# eave. A cone with 4 base verts rotated by pi/4 puts its corners on the
# diagonals, so the posts go on the diagonals too. At the axis-aligned
# angles the roof corners cantilevered 0.80 m unsupported and one post
# stood dead centre in the well mouth from every orthogonal view.
POST_ANGLES = tuple(math.pi / 4.0 + i * math.pi / 2.0 for i in range(4))
# Tenoned into the curb, not stood on it: a foot whose bottom face lands
# exactly on the curb's top face puts both on one plane (it measured 4
# coplanar cross-shell pairs, one per post). POST_TOP is held fixed so
# nothing above the posts moves.
POST_SEAT = 0.018
POST_SEAT_MIN = 0.015
POST_SEAT_MAX = 0.022
POST_CLEAR = 0.58
POST_BOTTOM = MASONRY_TOP + CURB_H - POST_SEAT
POST_TOP = MASONRY_TOP + CURB_H + POST_CLEAR
POST_H = POST_TOP - POST_BOTTOM
# The roof is sized to oversail the curb by a named clearance, measured on
# the flat of the eave. Deriving it from the post ring instead made the
# roof 1.61 m across a 1.08 m drum — an umbrella, not a well house.
EAVE_CLEAR = 0.055
EAVE_HALF = R_OUTER + CURB_OUT + EAVE_CLEAR
EAVE_OVERHANG = EAVE_HALF - (POST_R + POST_S / 2.0)
EAVE_Z = POST_TOP - 0.02
ROOF_RISE = 0.34
PEAK_Z = EAVE_Z + ROOF_RISE
SHINGLE_T = 0.016
WINDLASS_R = 0.045
# The windlass is the axle the posts are the bearings for: it passes through
# both posts and protrudes so the crank has something to attach to.
WINDLASS_END = POST_R + POST_S / 2.0 + 0.015
WINDLASS_LEN = 2.0 * WINDLASS_END
# The drum spans the first opposed pair of posts, so it shares their angle.
WINDLASS_AXIS = POST_ANGLES[0]
BUCKET_R_TOP = 0.105
BUCKET_R_BOT = 0.088
BUCKET_WALL_T = 0.008
BUCKET_H = 0.14
# The bucket is the piece's whole story, so it hangs in the open above the
# curb. At 0.68 it sat down the shaft with only its rim level with the
# coping: invisible in the hero and in every orthographic view.
CURB_TOP = MASONRY_TOP + CURB_H
BUCKET_CLEAR = 0.10
BUCKET_CLEAR_MIN = 0.085
BUCKET_CLEAR_MAX = 0.115
BUCKET_Z = CURB_TOP + BUCKET_CLEAR + BUCKET_H / 2.0
BUCKET_RIM_Z = BUCKET_Z + BUCKET_H / 2.0
HANDLE_BAR_Z = BUCKET_RIM_Z + 0.03
ROPE_R = 0.016
BBOX_TOL = 0.01
# Fitted to the generated AABB after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (1.312, 1.312, 1.761)

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
# Grew with the roof resize: the convex hull of a 1.31 m roof over the
# drum measures 346 where the 1.64 m roof measured 318. Budget raised to
# match a deliberate geometry change, with headroom for the falsifiers.
COLLIDER_TRIS_MAX = 380
# Z-fighting: two separate bodies landing on one plane. Cross-shell, with
# hay-bale's constants (copied, not imported).
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
ZFIGHT_PAIRS_MAX = 0
# Named supports: the AABB zmin is grounded by whichever bottom-course
# stone happens to be lowest, so every bottom stone carries its own floor
# contact. N_AROUND of them, one per bay.
SUPPORT_ZMIN_EPS = 1e-4
SUPPORT_COUNT = N_AROUND
# Posts stand under the roof's hip corners, measured in plan against the
# corners recomputed from the generated roof.
# Angular, in radians, wrapped into [-pi, pi]. 0.02 rad is 1.15 degrees.
POST_CORNER_EPS = 0.02
POST_COUNT = 4
# Falsifier magnitudes, each sized to trip its own budget and nothing
# earlier: the moves stay inside BBOX_TOL so the AABB gate cannot steal
# the failure.
STAND_POST_SEAT = 0.0
# --stand-posts must put the posts back where the shipped bug had them:
# on the axis, where a curb top face sits within COPLANAR_CENTRE_MAX of
# each foot. One facet over (15 degrees) is flush but too far from any
# coping top face to register, and falls through to the seat band.
# The crank no longer follows the post ring, so this rotation cannot
# swing it past the eave.
STAND_POST_TURN = math.pi / 4.0
SHALLOW_TENON_SEAT = 0.004
FLOAT_STONE_Z = 0.004
# Exactly one curb facet. Any other angle sets the post feet down on a
# different part of the 12-gon coping and the stone-wood gap gate (17)
# steals the failure; a full 45 degrees also swings the crank grip past
# the eave and fails the AABB gate (8). One facet is the only rotation
# whose local seat geometry is identical by symmetry, so nothing but the
# hip-alignment budget can see it. Same mis-aimed-falsifier trap as
# stone-archway's --flat-arch.
TURN_POSTS_ANGLE = 2.0 * math.pi / N_AROUND
DROP_BUCKET_Z = 0.26
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


def build_well_mesh(name, bevel_offset, bevel_segments,
                    post_seat=POST_SEAT, turn_posts=0.0):
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

        angles = tuple(a - turn_posts for a in POST_ANGLES)
        post_bottom = CURB_TOP - post_seat
        post_h = POST_TOP - post_bottom
        for ang in angles:
            loc = (
                POST_R * math.cos(ang),
                POST_R * math.sin(ang),
                post_bottom + post_h / 2.0,
            )
            wood_bevel_verts.extend(
                add_box(bm, loc, (POST_S, POST_S, post_h), WOOD_IDX,
                        euler=(0.0, 0.0, ang))
            )

        # The windlass is borne by two opposite posts, so it runs along the
        # post diagonal, not along X. Everything hung on it — beam, drum,
        # crank arm, grip — turns with it as one assembly.
        beam_z = POST_TOP - 0.05
        wax = WINDLASS_AXIS
        ca, sa = math.cos(wax), math.sin(wax)
        wood_bevel_verts.extend(
            add_box(
                bm,
                (0.0, 0.0, beam_z),
                (POST_R * 2.0 - POST_S, POST_S * 0.85, POST_S * 0.85),
                WOOD_IDX,
                euler=(0.0, 0.0, wax),
            )
        )
        add_cylinder(
            bm,
            (0.0, 0.0, beam_z),
            WINDLASS_R,
            WINDLASS_LEN,
            12,
            WOOD_IDX,
            euler=(0.0, math.pi / 2.0, wax),
        )
        # Crank: arm pinned to the protruding windlass end, grip parallel to
        # the windlass axis at the arm's lower end.
        arm_r = WINDLASS_END + 0.004
        add_box(
            bm,
            (arm_r * ca, arm_r * sa, beam_z - 0.055),
            (0.020, 0.022, 0.13),
            METAL_IDX,
            euler=(0.0, 0.0, wax),
        )
        grip_r = WINDLASS_END + 0.055
        add_cylinder(
            bm,
            (grip_r * ca, grip_r * sa, beam_z - 0.12),
            0.014,
            0.10,
            10,
            METAL_IDX,
            euler=(0.0, math.pi / 2.0, wax),
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


def shell_groups(me):
    """Vertex-index shells by edge connectivity (union-find), biggest first."""
    parent = list(range(len(me.vertices)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in me.edges:
        ra, rb = find(int(e.vertices[0])), find(int(e.vertices[1]))
        if ra != rb:
            parent[rb] = ra
    groups = {}
    for i in range(len(me.vertices)):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: -len(g))


def shell_box(me, idxs):
    co = [me.vertices[i].co for i in idxs]
    return {
        "xmin": min(c.x for c in co), "xmax": max(c.x for c in co),
        "ymin": min(c.y for c in co), "ymax": max(c.y for c in co),
        "zmin": min(c.z for c in co), "zmax": max(c.z for c in co),
    }


def coplanar_zfight_pairs(me, groups):
    """Coplanar face pairs from *different shells* — the z-fighting budget.

    Cross-shell, not merely share-no-vertex: two quads two steps apart on
    one flat cap share no vertex and are coplanar by construction, and
    counting those makes the budget unsatisfiable rather than meaningful.
    Z-fighting is two separate bodies landing on one plane, which is
    exactly a cross-shell pair. Combinatorics and constants copied from
    showcase/hay-bale (do not import across pieces).
    """
    owner = {}
    for si, comp in enumerate(groups):
        for vi in comp:
            owner[vi] = si
    faces = [(p.normal.copy(), p.center.copy(), owner.get(p.vertices[0], -1))
             for p in me.polygons]
    hits = 0
    for i in range(len(faces)):
        ni, ci, si = faces[i]
        for j in range(i + 1, len(faces)):
            nj, cj, sj = faces[j]
            if si == sj:
                continue
            if (ci - cj).length > COPLANAR_CENTRE_MAX:
                continue
            if abs(abs(ni.dot(nj)) - 1.0) > COPLANAR_NORMAL_EPS:
                continue
            if abs(ni.dot(cj - ci)) > COPLANAR_PLANE_EPS:
                continue
            hits += 1
    return hits


def post_shells(me, groups):
    """The four roof posts, found in the generated mesh by their geometry.

    A post is a wood shell that spans the curb line vertically and is
    square and slender in plan — never looked up by a construction index.
    """
    wood = set()
    for p in me.polygons:
        if p.material_index == WOOD_IDX:
            wood.add(int(p.vertices[0]))
    out = []
    for si, g in enumerate(groups):
        if not any(i in wood for i in g):
            continue
        b = shell_box(me, g)
        dz = b["zmax"] - b["zmin"]
        dx = b["xmax"] - b["xmin"]
        dy = b["ymax"] - b["ymin"]
        if not (0.4 <= dz <= 0.8) or max(dx, dy) > 0.25:
            continue
        out.append((si, b))
    return out


def measured_curb_top(me):
    """Top of the masonry, read off the generated mesh, not from CURB_TOP.

    An assertion that restates the constant the builder used witnesses
    nothing, so the post tenon is measured against the stone the post is
    actually tenoned into.
    """
    stone = {int(p.vertices[0]) for p in me.polygons
             if p.material_index == STONE_IDX}
    return max(me.vertices[i].co.z for i in stone)


def roof_corners(me, groups):
    """The roof's four hip corners, recomputed from the generated mesh.

    The corner verts of the widest wood shell above the eave: its four
    extreme XY points. Nothing here restates EAVE_HALF.
    """
    pts = [v.co for v in me.vertices if v.co.z >= EAVE_Z - 0.12]
    if not pts:
        return []
    zlo = min(p.z for p in pts)
    eave = [p for p in pts if p.z <= zlo + 0.05]
    if not eave:
        return []
    # The four extreme points of the pooled eave ring are the hip corners.
    # Taking them from a single shell picks one fascia board instead, whose
    # own extremes sit 90 degrees off the corners they are nailed to.
    corners = []
    for qx, qy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        corners.append(max(eave, key=lambda p: qx * p.x + qy * p.y))
    return corners


def drop_bucket(me, dz):
    """Falsifier surgery: lower the hung bucket assembly back down the shaft.

    Everything inside the mouth above the curb and under the windlass —
    which is the bucket, its hoops and its bail — moves as one body.
    """
    groups = shell_groups(me)
    for g in groups:
        b = shell_box(me, g)
        if b["zmin"] < CURB_TOP or b["zmax"] > POST_TOP - 0.10:
            continue
        if max(b["xmax"] - b["xmin"], b["ymax"] - b["ymin"]) > 2.5 * BUCKET_R_TOP:
            continue
        for i in g:
            me.vertices[i].co.z -= dz
    me.update()


def float_one_stone(me, dz):
    """Falsifier surgery: lift one bottom-course stone off the floor.

    The other bays stay down, so the AABB grounded gate still passes and
    only the named-support budget can catch it.
    """
    groups = shell_groups(me)
    floor_z = min(v.co.z for v in me.vertices)
    for g in groups:
        b = shell_box(me, g)
        if b["zmin"] > floor_z + 1e-5 or b["zmax"] > floor_z + STONE_H * 1.6:
            continue
        for i in g:
            me.vertices[i].co.z += dz
        break
    me.update()


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


def check(skip_decimate, lift_z=False, stand_posts=False, turn_posts=False,
          float_stone=False, drop_bucket_flag=False, shallow_tenon=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # --stand-posts reproduces the shipped bug exactly: posts on the axis
    # AND standing on the coping, which is the pair of choices that put a
    # foot and a curb top on one plane. Seating alone at 45 degrees leaves
    # no curb top face within COPLANAR_CENTRE_MAX of a foot, so it would
    # fall through to the seat band and witness the wrong budget.
    seat = POST_SEAT
    if stand_posts:
        seat = STAND_POST_SEAT
    elif shallow_tenon:
        seat = SHALLOW_TENON_SEAT
    turn = 0.0
    if stand_posts:
        turn = STAND_POST_TURN
    elif turn_posts:
        turn = TURN_POSTS_ANGLE
    low = build_well_mesh("WellLow", bevel_offset=0.010, bevel_segments=2,
                          post_seat=seat, turn_posts=turn)
    high = build_well_mesh("WellHigh", bevel_offset=0.010, bevel_segments=4,
                           post_seat=seat, turn_posts=turn)
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
    if float_stone:
        float_one_stone(low.data, FLOAT_STONE_Z)
    if drop_bucket_flag:
        drop_bucket(low.data, DROP_BUCKET_Z)

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
    # Blender sets TMPDIR from its own preference, which resolves to the
    # working directory on a stock portable build — so gettempdir() is the
    # repo root under CI and every run left a .glb behind. The budget only
    # needs the byte count, so drop the file once it is measured.
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

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

    groups = shell_groups(low.data)
    zfight = coplanar_zfight_pairs(low.data, groups)
    # Named supports: every bottom-course stone, not just the lowest one.
    floor_z = bb[2]
    supports = []
    for g in groups:
        b = shell_box(low.data, g)
        if b["zmin"] < floor_z + 0.02 and b["zmax"] < floor_z + STONE_H * 1.6:
            supports.append(b["zmin"] - floor_z)
    n_support = len(supports)
    support_worst = max((abs(z) for z in supports), default=1e9)
    # Post tenon depth, recomputed per post from the generated curb top.
    posts = post_shells(low.data, groups)
    n_posts = len(posts)
    curb_top = measured_curb_top(low.data)
    seats = [curb_top - b["zmin"] for _si, b in posts]
    seat_min = min(seats) if seats else -1.0
    seat_max = max(seats) if seats else 1e9
    # Each post stands under a hip corner of the roof, in plan.
    corners = roof_corners(low.data, groups)
    post_corner = 1e9
    if posts and corners:
        worst = 0.0
        for _si, b in posts:
            px = 0.5 * (b["xmin"] + b["xmax"])
            py = 0.5 * (b["ymin"] + b["ymax"])
            pa = math.atan2(py, px)
            best = min(
                abs((math.atan2(c.y, c.x) - pa + math.pi)
                    % (2.0 * math.pi) - math.pi)
                for c in corners
            )
            worst = max(worst, best)
        post_corner = worst
    # Bucket clearance above the curb.
    bucket_clear = -1.0
    metal_v = {int(p.vertices[0]) for p in low.data.polygons
               if p.material_index == METAL_IDX}
    for g in groups:
        b = shell_box(low.data, g)
        if b["zmin"] < curb_top or any(i in metal_v for i in g):
            continue
        if (b["xmax"] - b["xmin"]) > 2.5 * BUCKET_R_TOP:
            continue
        if b["zmax"] - b["zmin"] > BUCKET_H * 1.4:
            continue
        cand = b["zmin"] - curb_top
        if bucket_clear < 0 or cand < bucket_clear:
            bucket_clear = cand
    print(
        f"measured zfight_pairs={zfight} shells={len(groups)} "
        f"grounded_stones={n_support} support_worst={support_worst:.6f} "
        f"posts={n_posts} post_seat=[{seat_min:.5f},{seat_max:.5f}] "
        f"post_hip_offset={post_corner:.5f} bucket_clear={bucket_clear:.5f}"
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
    if zfight > ZFIGHT_PAIRS_MAX:
        return fail(
            f"coplanar cross-shell face pairs {zfight} > {ZFIGHT_PAIRS_MAX} "
            "(--stand-posts is the designed fail: a post foot standing on "
            "the coping's top face puts both on one plane)",
            15,
        ), None, None, None, None, None
    if abs(bb[2]) > ZMIN_EPS:
        return fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ), None, None, None, None, None
    if n_support != SUPPORT_COUNT or support_worst > SUPPORT_ZMIN_EPS:
        return fail(
            f"grounded bottom-course stones {n_support}/{SUPPORT_COUNT}, "
            f"worst zmin {support_worst:.6f} > {SUPPORT_ZMIN_EPS} "
            "(--float-stone is the designed fail: one bay lifted off the "
            "floor while the rest still ground the AABB)",
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
    if seat_min < POST_SEAT_MIN or seat_max > POST_SEAT_MAX:
        return fail(
            f"post tenon depth band [{seat_min:.5f}, {seat_max:.5f}] outside "
            f"[{POST_SEAT_MIN}, {POST_SEAT_MAX}] over {n_posts} posts "
            "(--shallow-tenon is the designed fail)",
            18,
        ), None, None, None, None, None
    if bucket_clear < BUCKET_CLEAR_MIN or bucket_clear > BUCKET_CLEAR_MAX:
        return fail(
            f"bucket clears the curb by {bucket_clear:.5f} outside "
            f"[{BUCKET_CLEAR_MIN}, {BUCKET_CLEAR_MAX}] "
            "(--drop-bucket is the designed fail: a bucket down the shaft "
            "shows only its rim and the piece loses its subject)",
            18,
        ), None, None, None, None, None
    if n_posts != POST_COUNT or post_corner > POST_CORNER_EPS:
        return fail(
            f"posts {n_posts}/{POST_COUNT}, worst post-to-hip-corner plan "
            f"offset {post_corner:.5f} > {POST_CORNER_EPS} "
            "(--turn-posts is the designed fail: posts at the midpoint of "
            "each eave leave the roof's corners cantilevered and stand one "
            "post in the well mouth)",
            19,
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
    p.add_argument(
        "--stand-posts",
        action="store_true",
        help="falsification: stand the posts on the curb instead of tenoning "
             "them in, so foot and coping land on one plane",
    )
    p.add_argument(
        "--shallow-tenon",
        action="store_true",
        help="falsification: tenon the posts only part way into the curb so "
             "the seat band fails without putting faces on one plane",
    )
    p.add_argument(
        "--turn-posts",
        action="store_true",
        help="falsification: rotate the post ring off the roof's hip corners "
             "to the midpoint of each eave",
    )
    p.add_argument(
        "--float-stone",
        action="store_true",
        help="falsification: lift one bottom-course stone while the rest "
             "still ground the AABB",
    )
    p.add_argument(
        "--drop-bucket",
        action="store_true",
        help="falsification: lower the bucket back down the shaft",
    )
    args = p.parse_args(argv)

    code, low, _high, stone, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stand_posts=args.stand_posts,
        turn_posts=args.turn_posts,
        float_stone=args.float_stone,
        drop_bucket_flag=args.drop_bucket,
        shallow_tenon=args.shallow_tenon,
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
