"""Game-ready timber watchtower — a showcase piece, not an example.

Asserts budget conformance of a procedural lookout (posts, braces,
platform, hatch ladder, coursed shake roof) after composing shipped pipeline
pieces: bmesh construction, UVs, three materials, high-to-low normal
bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-shoes`` named shoe
supports, ``--short-rails`` rail-to-post joint fit, ``--float-band``
iron-collar seat, ``--rake-posts`` post plumb.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python watchtower.py --
    blender --background --python watchtower.py -- --skip-decimate
    blender --background --python watchtower.py -- --output tower.png
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

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

HALF = 0.52
POST = 0.090
POST_H = 2.42
PLAT_Z = 1.72
PLANK_T = 0.038
# Guardrails sit in the bay between the deck and the eave — a 0.90 m
# code rail would punch through the roof.
RAIL_CLEAR = 0.10
RAIL_H = POST_H - PLAT_Z - PLANK_T - RAIL_CLEAR
GIRT_Z = 0.86
GIRT_H = 0.075
SILL_H = 0.085
KICK_H = 0.20
BRACE_T = 0.042
IRON_T = 0.012
IRON_H = 0.028
IRON_STANDOFF = 0.002
SHOE_H = 0.040
EAVE_HALF = 0.78
ROOF_RISE = 0.55
SHINGLE_T = 0.016
N_SHINGLE = 5
N_PLANK = 6
HATCH_PLANKS = 2
LEAN = 0.18
RAIL_TENON = POST * 0.40

BBOX_TOL = 0.01
OUTER_SIZE = (1.594, 1.594, 2.973)
BASE_TRIS_MIN = 6200
BASE_TRIS_MAX = 8200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 180
BAKE_RES = 256
CAGE_EXTRUSION = 0.10
METAL_FACES_MIN = 80
ROOF_FACES_MIN = 40
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.998
SHOE_COUNT = 4
SHOE_ZMIN_MAX = 0.001
RAIL_ENGAGE_MIN = 0.012
BAND_SEAT_MAX = 0.010
POST_PLUMB_MAX = 0.010
PLAN_XY = 2.0 * EAVE_HALF
PLAN_Z = POST_H + ROOF_RISE
PLAN_TOL = 0.08
LIFT_Z = 0.05
RAKE = math.radians(2.0)
SHORT_SHOE_Z = 0.055
BAND_FLOAT = 0.040

WOOD_IDX = 0
ROOF_IDX = 1
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


def add_oriented_box(bm, a, b, scale_xy, mat_idx):
    a = Vector(a)
    b = Vector(b)
    delta = b - a
    length = delta.length
    if length < 1e-8:
        return []
    quat = Vector((0.0, 0.0, 1.0)).rotation_difference(delta.normalized())
    eul = quat.to_euler("XYZ")
    return add_box(
        bm,
        ((a + b) * 0.5),
        (scale_xy[0], scale_xy[1], length),
        mat_idx,
        euler=(eul.x, eul.y, eul.z),
    )


def add_cone(bm, loc, radius1, radius2, depth, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
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


def add_collar(bm, px, py, z, height, mat_idx, standoff=0.0):
    """Four plates on the post faces — a wrap, not a cube through the timber.

    X-facing plates cover the post face only. Y-facing plates cover the
    corners so the wrap meets at a butt instead of a coplanar overlap.
    """
    half = POST / 2.0
    t = IRON_T
    off = half + t / 2.0 + standoff
    add_box(bm, (px + off, py, z), (t, POST, height), mat_idx)
    add_box(bm, (px - off, py, z), (t, POST, height), mat_idx)
    add_box(bm, (px, py + off, z), (POST + 2.0 * t, t, height), mat_idx)
    add_box(bm, (px, py - off, z), (POST + 2.0 * t, t, height), mat_idx)


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


def add_shingle_roof(bm, eave_z, peak_z):
    """Coursed shakes on a solid square pyramid. Each course is offset along
    the face normal so overlapping shakes do not share vertex positions.
    """
    add_cone(
        bm,
        (0.0, 0.0, (eave_z + peak_z) / 2.0),
        EAVE_HALF * math.sqrt(2.0),
        0.03,
        ROOF_RISE,
        4,
        ROOF_IDX,
        euler=(0.0, 0.0, math.pi / 4.0),
    )
    nrm_local = Vector((0.0, ROOF_RISE, EAVE_HALF)).normalized()

    def add_course(yaw, t0, t1, row):
        rot = Euler((0.0, 0.0, yaw)).to_matrix()
        nrm = rot @ nrm_local

        def pt(t, s):
            w = EAVE_HALF * t
            y = t * EAVE_HALF
            z = peak_z - t * ROOF_RISE
            return rot @ Vector((s * w, y, z))

        inner = SHINGLE_T * (0.20 + 0.22 * row)
        outer = inner + SHINGLE_T * 0.90
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
            face.material_index = ROOF_IDX

    for side in range(4):
        yaw = side * (math.pi / 2.0)
        for row in range(N_SHINGLE):
            t0 = (row + 0.14) / N_SHINGLE
            t1 = min(0.96, (row + 1.0) / N_SHINGLE)
            add_course(yaw, t0, t1, row)


def build_tower_mesh(
    name,
    bevel_offset,
    bevel_segments,
    short_shoes=False,
    short_rails=False,
    float_band=False,
    rake_posts=False,
):
    bm = bmesh.new()
    try:
        wood = []
        posts = (
            (-HALF, -HALF),
            (HALF, -HALF),
            (-HALF, HALF),
            (HALF, HALF),
        )
        rake = (RAKE, 0.0, 0.0) if rake_posts else (0.0, 0.0, 0.0)
        for px, py in posts:
            wood.extend(
                add_box(
                    bm,
                    (px, py, POST_H / 2.0),
                    (POST, POST, POST_H),
                    WOOD_IDX,
                    euler=rake,
                )
            )

        bay = 2.0 * HALF - POST
        # Tenon into the posts; thickness under POST so side faces are not
        # coplanar with the post faces.
        member = bay + POST * 0.40
        section = POST * 0.70
        sill_z = SHOE_H + SILL_H / 2.0
        for sign in (-1.0, 1.0):
            wood.extend(
                add_box(
                    bm,
                    (0.0, sign * HALF, sill_z),
                    (member, section, SILL_H),
                    WOOD_IDX,
                )
            )
            wood.extend(
                add_box(
                    bm,
                    (sign * HALF, 0.0, sill_z),
                    (section, member, SILL_H),
                    WOOD_IDX,
                )
            )
            wood.extend(
                add_box(
                    bm,
                    (0.0, sign * HALF, GIRT_Z),
                    (member, section, GIRT_H),
                    WOOD_IDX,
                )
            )
            wood.extend(
                add_box(
                    bm,
                    (sign * HALF, 0.0, GIRT_Z),
                    (section, member, GIRT_H),
                    WOOD_IDX,
                )
            )

        # Kick sits on the sill, not on the same plane as the sill bottom.
        kick_z = SHOE_H + SILL_H + KICK_H / 2.0
        kick_span = bay * 0.88
        wood.extend(
            add_box(
                bm,
                (0.0, HALF - 0.020, kick_z),
                (kick_span, POST * 0.50, KICK_H),
                WOOD_IDX,
            )
        )
        for xsign in (-1.0, 1.0):
            wood.extend(
                add_box(
                    bm,
                    (xsign * (HALF - 0.020), 0.0, kick_z),
                    (POST * 0.50, kick_span, KICK_H),
                    WOOD_IDX,
                )
            )
        hatch_gap = 0.32
        kick_half = (bay * 0.92 - hatch_gap) / 2.0
        for xoff in (-(hatch_gap / 2.0 + kick_half / 2.0), hatch_gap / 2.0 + kick_half / 2.0):
            wood.extend(
                add_box(
                    bm,
                    (xoff, -HALF + 0.020, kick_z),
                    (kick_half, POST * 0.55, KICK_H),
                    WOOD_IDX,
                )
            )

        rise = GIRT_Z - (SHOE_H + SILL_H)
        run = bay
        blen = math.hypot(run, rise)
        bang = math.atan2(rise, run)
        brace_z = (SHOE_H + SILL_H + GIRT_Z) / 2.0
        # Lap the two diagonals by a brace thickness so they do not occupy
        # one plane (the black diamond in the old crossing).
        for ysign in (1.0,):
            for k, bang_sign in enumerate((-1.0, 1.0)):
                wood.extend(
                    add_box(
                        bm,
                        (0.0, ysign * HALF + ysign * k * (BRACE_T + 0.008), brace_z),
                        (blen, BRACE_T, BRACE_T),
                        WOOD_IDX,
                        euler=(0.0, bang_sign * bang, 0.0),
                    )
                )
        for xsign in (-1.0, 1.0):
            for k, bang_sign in enumerate((-1.0, 1.0)):
                wood.extend(
                    add_box(
                        bm,
                        (xsign * HALF + xsign * k * (BRACE_T + 0.008), 0.0, brace_z),
                        (BRACE_T, blen, BRACE_T),
                        WOOD_IDX,
                        euler=(bang_sign * bang, 0.0, 0.0),
                    )
                )
        for xsign in (-1.0, 1.0):
            wood.extend(
                add_oriented_box(
                    bm,
                    (xsign * (HALF - POST * 0.2), -HALF, SHOE_H + SILL_H),
                    (xsign * 0.22, -HALF, GIRT_Z),
                    (BRACE_T, BRACE_T),
                    WOOD_IDX,
                )
            )

        plank_span_x = 2.0 * HALF + POST * 0.15
        usable_y = 2.0 * HALF - 0.06
        plank_w = usable_y / N_PLANK
        y0 = -HALF + 0.03 + plank_w / 2.0
        hatch_y1 = y0 + (HATCH_PLANKS - 0.5) * plank_w
        for i in range(HATCH_PLANKS, N_PLANK):
            y = y0 + i * plank_w
            jw = 0.006 * math.sin(i * 1.7)
            wood.extend(
                add_box(
                    bm,
                    (0.0, y, PLAT_Z + PLANK_T / 2.0),
                    (plank_span_x + jw, plank_w * 0.90, PLANK_T),
                    WOOD_IDX,
                )
            )
        for xj in (-HALF * 0.42, HALF * 0.42):
            wood.extend(
                add_box(
                    bm,
                    (xj, 0.10, PLAT_Z - 0.022),
                    (POST * 0.62, 2.0 * HALF * 0.82, 0.044),
                    WOOD_IDX,
                )
            )
        # Hatch trim: three boards around the missing planks.
        wood.extend(
            add_box(
                bm,
                (0.0, hatch_y1, PLAT_Z + PLANK_T / 2.0),
                (0.46, 0.040, PLANK_T),
                WOOD_IDX,
            )
        )
        for xsign in (-1.0, 1.0):
            wood.extend(
                add_box(
                    bm,
                    (xsign * 0.23, -HALF + 0.12, PLAT_Z + PLANK_T / 2.0),
                    (0.040, hatch_y1 + HALF - 0.02, PLANK_T),
                    WOOD_IDX,
                )
            )

        rail_z_lo = PLAT_Z + PLANK_T + 0.14
        rail_z_hi = PLAT_Z + PLANK_T + RAIL_H - 0.05
        rail_t = POST * 0.42
        rail_len = bay * 0.70 if short_rails else bay + RAIL_TENON
        wood.extend(
            add_box(bm, (0.0, HALF, rail_z_lo), (rail_len, rail_t, 0.048), WOOD_IDX)
        )
        wood.extend(
            add_box(bm, (0.0, HALF, rail_z_hi), (rail_len, rail_t, 0.048), WOOD_IDX)
        )
        hatch_clear = 0.30
        side_y0 = -HALF + hatch_clear
        side_span = HALF - side_y0
        side_cy = (side_y0 + HALF) / 2.0
        side_len = side_span + (0.0 if short_rails else RAIL_TENON * 0.5)
        for xsign in (-1.0, 1.0):
            wood.extend(
                add_box(
                    bm,
                    (xsign * HALF, side_cy, rail_z_lo),
                    (rail_t, side_len, 0.048),
                    WOOD_IDX,
                )
            )
            wood.extend(
                add_box(
                    bm,
                    (xsign * HALF, side_cy, rail_z_hi),
                    (rail_t, side_len, 0.048),
                    WOOD_IDX,
                )
            )

        bot_y = -HALF - LEAN
        top_y = -HALF + 0.10
        top_z = PLAT_Z
        # Stiles plant at z=0. Separate foot cubes on the same plane as the
        # stile bottoms were coplanar z-fights; a chamfered stile end is the
        # foot.
        for sx in (-0.13, 0.13):
            wood.extend(
                add_oriented_box(
                    bm,
                    (sx, bot_y, 0.0),
                    (sx, top_y, top_z),
                    (0.044, 0.050),
                    WOOD_IDX,
                )
            )
        n_rung = 9
        for i in range(n_rung):
            t = (i + 0.6) / (n_rung + 0.2)
            z = 0.06 + t * (PLAT_Z - 0.14)
            y = bot_y + (top_y - bot_y) * (z / max(top_z, 1e-6))
            wood.extend(add_box(bm, (0.0, y, z), (0.28, 0.034, 0.032), WOOD_IDX))

        if bevel_offset > 0.0:
            edges = list({e for v in wood for e in v.link_edges})
            ret = bmesh.ops.bevel(
                bm,
                geom=edges,
                offset=bevel_offset,
                segments=bevel_segments,
                profile=0.5,
                affect="EDGES",
                clamp_overlap=True,
            )
            for f in ret.get("faces") or []:
                f.material_index = WOOD_IDX

        eave_z = POST_H
        peak_z = POST_H + ROOF_RISE
        add_shingle_roof(bm, eave_z, peak_z)
        fascia_h = 0.048
        fascia_t = 0.034
        fascia_span = 2.0 * EAVE_HALF - 0.10
        for side in range(4):
            yaw = side * (math.pi / 2.0)
            fx = EAVE_HALF * math.sin(yaw)
            fy = EAVE_HALF * math.cos(yaw)
            if side % 2 == 0:
                add_box(
                    bm,
                    (0.0, fy, eave_z - fascia_h / 2.0 - 0.008),
                    (fascia_span, fascia_t, fascia_h),
                    WOOD_IDX,
                )
            else:
                add_box(
                    bm,
                    (fx, 0.0, eave_z - fascia_h / 2.0 - 0.008),
                    (fascia_t, fascia_span, fascia_h),
                    WOOD_IDX,
                )

        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z -= zmin
            if v.co.z < 0.005:
                v.co.z = 0.0

        shoe_z = SHORT_SHOE_Z if short_shoes else SHOE_H / 2.0
        shoe_h = 0.018 if short_shoes else SHOE_H
        band_off = BAND_FLOAT if float_band else IRON_STANDOFF
        girt_band_z = GIRT_Z + GIRT_H / 2.0 + IRON_H / 2.0
        deck_band_z = PLAT_Z + PLANK_T + IRON_H / 2.0 + 0.006
        for px, py in posts:
            add_collar(bm, px, py, shoe_z, shoe_h, METAL_IDX, standoff=IRON_STANDOFF)
            add_collar(bm, px, py, girt_band_z, IRON_H, METAL_IDX, standoff=band_off)
            add_collar(
                bm, px, py, deck_band_z, IRON_H, METAL_IDX,
                standoff=band_off,
            )
        for sx in (-0.13, 0.13):
            add_box(
                bm,
                (sx, -HALF + 0.02, PLAT_Z + 0.02),
                (0.050, 0.055, IRON_T),
                METAL_IDX,
            )

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
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


def principled(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def assign_slots(obj, wood, roof, metal):
    mats = obj.data.materials
    wanted = (wood, roof, metal)
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
    nv, ne, nf = len(me.vertices), len(me.edges), len(me.polygons)
    ngons = sum(1 for p in me.polygons if len(p.vertices) > 4)
    zero_area = sum(1 for p in me.polygons if face_area(me, p) <= AREA_EPS)
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


def support_audit(me):
    plates = []
    for group in shells(me):
        if mat_of(me, group) != METAL_IDX:
            continue
        a = shell_aabb(me, group)
        cz = 0.5 * (a[2] + a[5])
        if cz > 0.12:
            continue
        plates.append(a)
    corners = {}
    for a in plates:
        cx = 0.5 * (a[0] + a[3])
        cy = 0.5 * (a[1] + a[4])
        key = (round(cx * 4.0) / 4.0, round(cy * 4.0) / 4.0)
        corners.setdefault(key, []).append(a)
    zmin = min((a[2] for a in plates), default=99.0)
    return {"shoes": len(corners), "shoe_z": zmin}


def joint_audit(me):
    """Guardrail bite into the +Y posts."""
    posts = []
    rails = []
    for group in shells(me):
        if mat_of(me, group) != WOOD_IDX:
            continue
        a = shell_aabb(me, group)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        cy = 0.5 * (a[1] + a[4])
        cz = 0.5 * (a[2] + a[5])
        if dz > POST_H * 0.55 and dx < POST * 2.2 and dy < POST * 2.2:
            posts.append(a)
            continue
        if (
            cz > PLAT_Z
            and dx > HALF
            and dy < POST
            and abs(cy - HALF) < POST
        ):
            rails.append(a)
    back_posts = [p for p in posts if 0.5 * (p[1] + p[4]) > 0.0]
    pairs = [
        min(r[3] - p[0], p[3] - r[0])
        for r in rails
        for p in back_posts
    ]
    engage = min(pairs) if pairs else 1.0
    return {"posts": len(posts), "rails": len(rails), "engage": engage}


def band_seat(me):
    """Standoff from each girt collar's inner face to the post outer face."""
    posts = []
    for group in shells(me):
        if mat_of(me, group) != WOOD_IDX:
            continue
        a = shell_aabb(me, group)
        dz = a[5] - a[2]
        dx = a[3] - a[0]
        dy = a[4] - a[1]
        if dz > POST_H * 0.55 and dx < POST * 2.2 and dy < POST * 2.2:
            posts.append(a)
    if not posts:
        return 99.0
    gaps = []
    for group in shells(me):
        if mat_of(me, group) != METAL_IDX:
            continue
        a = shell_aabb(me, group)
        cz = 0.5 * (a[2] + a[5])
        girt_band_z = GIRT_Z + GIRT_H / 2.0 + IRON_H / 2.0
        if abs(cz - girt_band_z) > IRON_H:
            continue
        cx = 0.5 * (a[0] + a[3])
        cy = 0.5 * (a[1] + a[4])
        dx = a[3] - a[0]
        dy = a[4] - a[1]
        nearest = min(
            posts,
            key=lambda p: abs(cx - 0.5 * (p[0] + p[3])) + abs(cy - 0.5 * (p[1] + p[4])),
        )
        px = 0.5 * (nearest[0] + nearest[3])
        py = 0.5 * (nearest[1] + nearest[4])
        if dx <= dy:
            inner = a[0] if cx > px else a[3]
            gaps.append(abs(inner - (px + (POST / 2.0 if cx > px else -POST / 2.0))))
        else:
            inner = a[1] if cy > py else a[4]
            gaps.append(abs(inner - (py + (POST / 2.0 if cy > py else -POST / 2.0))))
    if not gaps:
        return 99.0
    return max(gaps)


def plumb_audit(me):
    drifts = []
    for group in shells(me):
        if mat_of(me, group) != WOOD_IDX:
            continue
        a = shell_aabb(me, group)
        dz = a[5] - a[2]
        dx = a[3] - a[0]
        dy = a[4] - a[1]
        if dz < POST_H * 0.55 or dx > POST * 2.2 or dy > POST * 2.2:
            continue
        pts = [me.vertices[i].co for i in group]
        zcut_lo = a[2] + 0.08 * dz
        zcut_hi = a[5] - 0.08 * dz
        lo = [p for p in pts if p.z <= zcut_lo]
        hi = [p for p in pts if p.z >= zcut_hi]
        if len(lo) < 3 or len(hi) < 3:
            continue
        c_lo = Vector((sum(p.x for p in lo) / len(lo), sum(p.y for p in lo) / len(lo)))
        c_hi = Vector((sum(p.x for p in hi) / len(hi), sum(p.y for p in hi) / len(hi)))
        drifts.append((c_hi - c_lo).length)
    return max(drifts) if drifts else 99.0


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, PLAT_Z))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


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
    img = bpy.data.images.new("TowerNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = WOOD_IDX
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


def check(
    skip_decimate,
    lift_z=False,
    stray_vert=False,
    short_shoes=False,
    short_rails=False,
    float_band=False,
    rake_posts=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_tower_mesh(
        "TowerLow",
        bevel_offset=0.006,
        bevel_segments=2,
        short_shoes=short_shoes,
        short_rails=short_rails,
        float_band=float_band,
        rake_posts=rake_posts,
    )
    high = build_tower_mesh(
        "TowerHigh",
        bevel_offset=0.006,
        bevel_segments=4,
        short_shoes=short_shoes,
        short_rails=short_rails,
        float_band=float_band,
        rake_posts=rake_posts,
    )
    wood = principled("TowerWood", (0.42, 0.22, 0.08, 1.0), 0.0, 0.56)
    roof = principled("TowerShake", (0.30, 0.28, 0.26, 1.0), 0.0, 0.74)
    metal = principled("TowerIron", (0.12, 0.125, 0.14, 1.0), 1.0, 0.30)
    assign_slots(low, wood, roof, metal)
    assign_slots(high, wood, roof, metal)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("tower mesh did not build", 3), None, None, None, None, None

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
    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    sup = support_audit(low.data)
    jnt = joint_audit(low.data)
    seat = band_seat(low.data)
    plumb = plumb_audit(low.data)

    img, tex = setup_bake_image(low, wood)
    if img is None:
        return fail("tower has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "TowerLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "TowerLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_tower_mesh("TowerColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "TowerCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_watchtower_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0

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
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}"
    )
    print(
        f"measured shoes={sup['shoes']} shoe_z={sup['shoe_z']:.5f} "
        f"rail_engage={jnt['engage']:.4f} band_seat={seat:.5f} "
        f"plumb={plumb:.5f}"
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
    if idx_counts.get(METAL_IDX, 0) < METAL_FACES_MIN:
        return fail(
            f"metal faces {idx_counts.get(METAL_IDX, 0)} < {METAL_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(ROOF_IDX, 0) < ROOF_FACES_MIN:
        return fail(
            f"roof faces {idx_counts.get(ROOF_IDX, 0)} < {ROOF_FACES_MIN}",
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
        hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
        or hyg["doubles"] or hyg["ngons"] or zf
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}",
            15,
        ), None, None, None, None, None
    if bb[2] > ZMIN_EPS or sup["shoes"] != SHOE_COUNT or sup["shoe_z"] > SHOE_ZMIN_MAX:
        return fail(
            f"grounded zmin={bb[2]:.5f} shoes={sup['shoes']} "
            f"shoe_z={sup['shoe_z']:.5f}",
            16,
        ), None, None, None, None, None
    if jnt["engage"] < RAIL_ENGAGE_MIN:
        return fail(
            f"rail engage {jnt['engage']:.4f} < {RAIL_ENGAGE_MIN} "
            f"posts={jnt['posts']} rails={jnt['rails']}",
            17,
        ), None, None, None, None, None
    if seat > BAND_SEAT_MAX:
        return fail(f"band seat {seat:.5f} > {BAND_SEAT_MAX}", 18), None, None, None, None, None
    if (
        plumb > POST_PLUMB_MAX
        or abs(size_z - PLAN_Z) > PLAN_TOL
        or abs(size_x - PLAN_XY) > PLAN_TOL + 0.20
    ):
        return fail(
            f"plumb={plumb:.5f} size=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
            f"plan={PLAN_XY:.3f}x{PLAN_Z:.3f}",
            19,
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

    bb = world_bbox(low)
    span = max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], 0.2)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (span * 1.98, -span * 2.75, span * 1.13)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (
        0.5 * (bb[0] + bb[3]),
        0.5 * (bb[1] + bb[4]),
        0.42 * (bb[2] + bb[5]),
    )
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
    p.add_argument("--short-shoes", action="store_true")
    p.add_argument("--short-rails", action="store_true")
    p.add_argument("--float-band", action="store_true")
    p.add_argument("--rake-posts", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_shoes=args.short_shoes,
        short_rails=args.short_rails,
        float_band=args.float_band,
        rake_posts=args.rake_posts,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("watchtower OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
