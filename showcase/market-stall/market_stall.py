"""Game-ready market stall — a showcase piece, not an example.

Asserts budget conformance of a procedural timber stall after composing
shipped pipeline pieces: bmesh construction, UVs, three materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-feet`` named post-foot
supports, ``--low-brace`` brace-vs-counter joint fit, ``--float-awning``
awning-on-header seat, ``--rake-posts`` post plumb, ``--short-brace``
brace-in-post seat.

Slat jitter is closed-form ``sin(i)``; the per-piece wood tone is drawn
from ``random.Random(TONE_SEED)``, so it is the same every run. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python market_stall.py --
    blender --background --python market_stall.py -- --skip-decimate
    blender --background --python market_stall.py -- --output stall.png
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

# Showcase lives at repo-root/showcase/, not under examples/. The framing
# helper is the repo's only shared import and lives next to the examples;
# resolve the repo root so we do not move gallery_framing.py.
_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

WIDTH = 1.36
DEPTH = 0.92
POST = 0.070
FRONT_H = 1.28
BACK_H = 1.72
N_STRIPES = 8
AWNING_T = 0.018
OVERHANG_F = 0.040
OVERHANG_B = 0.030
COUNTER_Z = 0.82
COUNTER_D = 0.34
COUNTER_T = 0.070
BRACE = 0.036
FOOT_H = 0.036
TENON = POST * 0.35
BBOX_TOL = 0.01
# Fitted to the generated AABB after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (1.389, 1.011, 1.740)

BASE_TRIS_MIN = 3900
BASE_TRIS_MAX = 5200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 80
BAKE_RES = 256
CAGE_EXTRUSION = 0.06
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.998
FOOT_ZMIN_MAX = 0.001
FOOT_COUNT = 4
AWNING_SEAT_MAX = 0.010
AWNING_SEAT_MIN = -0.002
BRACE_COUNTER_OVERLAP_MAX = 1e-6
POST_PLUMB_MAX = 0.008
FRAME_XY_TOL = 0.04
LIFT_Z = 0.05
# Small enough that the AABB still sits in BBOX_TOL; large enough that
# the front-eave seat drops below AWNING_SEAT_MIN.
FLOAT_AWNING = 0.008
RAKE = math.radians(2.0)
SHORT_FOOT_Z = 0.048
# Brace ends must sit inside the post they tenon into, at both ends: the
# depth each end reaches past the post's inner face, along Y. The first
# build stopped the front end at y = +0.04, 0.43 m short of the front post,
# so the brace hung in the air behind the counter.
BRACE_SEAT_MIN = 0.020
BRACE_COUNT = 2
# --short-brace stops the front end at that old mid-depth point.
SHORT_BRACE_Y = 0.04
PLANK_TONE_JITTER = 0.28
TONE_SEED = 31
WOOD_GRAIN_SCALE = 30.0

WOOD_IDX = 0
STRIPE_A_IDX = 1
STRIPE_B_IDX = 2


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


def add_wrap(bm, px, py, z, height, host, t, mat_idx):
    """Four plates around a square post. Y-facing plates cover the corners."""
    half = host / 2.0
    off = half + t / 2.0 + 0.002
    add_box(bm, (px + off, py, z), (t, host, height), mat_idx)
    add_box(bm, (px - off, py, z), (t, host, height), mat_idx)
    add_box(bm, (px, py + off, z), (host + 2.0 * t, t, height), mat_idx)
    add_box(bm, (px, py - off, z), (host + 2.0 * t, t, height), mat_idx)
    return []


def add_striped_slab(bm, loc, scale, euler, n_stripes, even_idx, odd_idx):
    """One slab split into n stripes that share vertices — no daylight gaps."""
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    sx, sy, sz = scale
    stations = []
    for i in range(n_stripes + 1):
        x = -0.5 * sx + sx * i / n_stripes
        row = []
        for y, z in (
            (-0.5 * sy, -0.5 * sz),
            (-0.5 * sy, 0.5 * sz),
            (0.5 * sy, -0.5 * sz),
            (0.5 * sy, 0.5 * sz),
        ):
            row.append(bm.verts.new(rot @ Vector((x, y, z)) + origin))
        stations.append(row)
    kept = []
    for i in range(n_stripes):
        a = stations[i]
        b = stations[i + 1]
        idx = even_idx if (i % 2 == 0) else odd_idx
        quads = (
            (a[0], b[0], b[2], a[2]),
            (a[1], a[3], b[3], b[1]),
            (a[0], a[1], b[1], b[0]),
            (a[2], b[2], b[3], a[3]),
        )
        for q in quads:
            face = bm.faces.new(q)
            face.material_index = idx
            kept.append(face)
    first = stations[0]
    last = stations[-1]
    cap_a = bm.faces.new((first[0], first[2], first[3], first[1]))
    cap_a.material_index = even_idx
    cap_b = bm.faces.new((last[0], last[1], last[3], last[2]))
    cap_b.material_index = even_idx if ((n_stripes - 1) % 2 == 0) else odd_idx
    kept.extend((cap_a, cap_b))
    return kept


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


def build_stall_mesh(
    name,
    bevel_offset,
    bevel_segments,
    low_brace=False,
    float_awning=False,
    rake_posts=False,
    short_feet=False,
    short_brace=False,
):
    bm = bmesh.new()
    wood_verts = []
    stripe_faces = []
    try:
        hx = WIDTH / 2.0
        hy = DEPTH / 2.0
        px = hx - POST / 2.0
        py_f = -(hy - POST / 2.0)
        py_b = hy - POST / 2.0
        post_h_f = FRONT_H - POST
        post_h_b = BACK_H - POST
        rake = (RAKE, 0.0, 0.0) if rake_posts else (0.0, 0.0, 0.0)
        posts = (
            (-px, py_f, post_h_f),
            (px, py_f, post_h_f),
            (-px, py_b, post_h_b),
            (px, py_b, post_h_b),
        )
        foot_z = SHORT_FOOT_Z if short_feet else FOOT_H / 2.0
        foot_h = 0.020 if short_feet else FOOT_H
        wrap_t = POST * 0.18
        for x, y, h in posts:
            wood_verts.extend(
                add_box(bm, (x, y, h / 2.0), (POST, POST, h), WOOD_IDX, euler=rake)
            )
            add_wrap(bm, x, y, foot_z, foot_h, POST, wrap_t, WOOD_IDX)

        header_len = WIDTH - POST + 2.0 * TENON
        wood_verts.extend(
            add_box(
                bm,
                (0.0, py_f, FRONT_H - POST / 2.0),
                (header_len, POST * 0.78, POST),
                WOOD_IDX,
            )
        )
        wood_verts.extend(
            add_box(
                bm,
                (0.0, py_b, BACK_H - POST / 2.0),
                (header_len, POST * 0.78, POST),
                WOOD_IDX,
            )
        )
        # Side plates sit on the header centres, spanning post to post.
        for sx in (-px, px):
            wood_verts.extend(
                add_oriented_box(
                    bm,
                    (sx, py_f, FRONT_H - POST / 2.0),
                    (sx, py_b, BACK_H - POST / 2.0),
                    (POST * 0.80, POST * 0.80),
                    WOOD_IDX,
                )
            )
        for i in range(3):
            rx = -hx + POST * 2.0 + (i + 1) * (WIDTH - 4.0 * POST) / 4.0
            wood_verts.extend(
                add_oriented_box(
                    bm,
                    (rx, py_f, FRONT_H - POST / 2.0),
                    (rx, py_b, BACK_H - POST / 2.0),
                    (POST * 0.42, POST * 0.42),
                    WOOD_IDX,
                )
            )

        wood_verts.extend(
            add_box(
                bm,
                (0.0, py_b, BACK_H * 0.48),
                (WIDTH - POST, POST * 0.65, POST * 0.65),
                WOOD_IDX,
            )
        )
        wood_verts.extend(
            add_box(
                bm,
                (0.0, py_f, 0.16),
                (WIDTH - 2.0 * POST, POST * 0.70, POST * 0.55),
                WOOD_IDX,
            )
        )

        for sign in (-1.0, 1.0):
            sx = sign * px
            if low_brace:
                a = Vector((sx, py_f, 0.28))
                b = Vector((sx, py_b, BACK_H * 0.58))
            else:
                # Post centre to post centre, so both ends tenon a post and
                # the side frame is triangulated. On the post centreline so it
                # does not read as a wing in the front elevation.
                fy = SHORT_BRACE_Y if short_brace else py_f
                a = Vector((sx, fy, COUNTER_Z + 0.17))
                b = Vector((sx, py_b, BACK_H - 0.22))
            wood_verts.extend(add_oriented_box(bm, a, b, (BRACE, BRACE), WOOD_IDX))

        inner_w = WIDTH - 2.0 * POST - 0.024
        y0 = py_f + POST / 2.0 + 0.016
        y1 = y0 + COUNTER_D
        n_slats = 6
        slat_gap = 0.008
        slat_d = (COUNTER_D - (n_slats - 1) * slat_gap) / n_slats
        for i in range(n_slats):
            jw = 0.018 * math.sin(i * 2.31 + 0.5)
            jt = 0.006 * math.sin(i * 1.87)
            y = y0 + slat_d / 2.0 + i * (slat_d + slat_gap)
            wood_verts.extend(
                add_box(
                    bm,
                    (0.0, y, COUNTER_Z),
                    (inner_w + jw, slat_d * 0.94, COUNTER_T * 0.62 + jt),
                    WOOD_IDX,
                )
            )
        wood_verts.extend(
            add_box(
                bm,
                (0.0, y0 + 0.016, COUNTER_Z - 0.08),
                (inner_w * 0.96, 0.032, 0.14),
                WOOD_IDX,
            )
        )
        shelf_z = 0.38
        n_shelf = 4
        shelf_d = COUNTER_D * 0.78
        shelf_gap = 0.008
        shelf_slat = (shelf_d - (n_shelf - 1) * shelf_gap) / n_shelf
        sy0 = y0 + 0.04 + shelf_slat / 2.0
        for i in range(n_shelf):
            jw = 0.014 * math.sin(i * 1.63 + 0.9)
            wood_verts.extend(
                add_box(
                    bm,
                    (0.0, sy0 + i * (shelf_slat + shelf_gap), shelf_z),
                    (inner_w - 0.08 + jw, shelf_slat * 0.94, 0.024),
                    WOOD_IDX,
                )
            )
        leg_h = COUNTER_Z - COUNTER_T * 0.32
        for lx in (-inner_w / 2.0 + 0.04, inner_w / 2.0 - 0.04):
            for ly in (y0 + 0.05, y1 - 0.05):
                wood_verts.extend(
                    add_box(bm, (lx, ly, leg_h / 2.0), (0.042, 0.042, leg_h), WOOD_IDX)
                )

        plank_y = py_b - POST / 2.0 - 0.014
        plank_len = WIDTH - POST
        for i in range(5):
            z = 0.30 + i * 0.148
            jw = 0.004 * math.sin(i * 2.11)
            wood_verts.extend(
                add_box(
                    bm,
                    (0.0, plank_y, z),
                    (plank_len + jw, 0.028, 0.118),
                    WOOD_IDX,
                )
            )

        fascia_y = -hy - OVERHANG_F
        wood_verts.extend(
            add_box(
                bm,
                (0.0, fascia_y, FRONT_H - 0.022),
                (WIDTH - POST * 0.2, 0.032, 0.044),
                WOOD_IDX,
            )
        )
        wood_verts.extend(
            add_box(
                bm,
                (0.0, fascia_y - 0.006, FRONT_H - 0.004),
                (WIDTH - POST * 0.05, 0.022, 0.022),
                WOOD_IDX,
            )
        )

        # Centreline sits above the header; thickness then hangs along the
        # roof normal so the front underside clears the fascia top.
        seat = 0.012
        front = Vector((0.0, -hy - OVERHANG_F, FRONT_H + seat))
        back = Vector((0.0, hy + OVERHANG_B, BACK_H + seat))
        dy = back.y - front.y
        dz = back.z - front.z
        awning_len = math.hypot(dy, dz)
        pitch = math.atan2(dz, dy)
        nrm = Vector((0.0, -math.sin(pitch), math.cos(pitch)))
        mid = (front + back) * 0.5
        if float_awning:
            mid = Vector((mid.x, mid.y, mid.z + FLOAT_AWNING))
        stripe_faces.extend(
            add_striped_slab(
                bm,
                mid,
                (WIDTH, awning_len, AWNING_T),
                (pitch, 0.0, 0.0),
                N_STRIPES,
                STRIPE_A_IDX,
                STRIPE_B_IDX,
            )
        )
        val_z = FRONT_H - 0.09 + (FLOAT_AWNING if float_awning else 0.0)
        stripe_faces.extend(
            add_striped_slab(
                bm,
                (0.0, fascia_y - 0.002, val_z),
                (WIDTH, 0.014, 0.15),
                (0.0, 0.0, 0.0),
                N_STRIPES,
                STRIPE_B_IDX,
                STRIPE_A_IDX,
            )
        )

        if bevel_offset > 0.0:
            # A set of BMEdges iterates in memory order, which varies run to
            # run and reorders the bevelled faces; sort by index.
            bm.edges.index_update()
            edges = sorted(
                {e for v in wood_verts for e in v.link_edges}, key=lambda e: e.index
            )
            bmesh.ops.bevel(
                bm,
                geom=edges,
                offset=bevel_offset,
                segments=bevel_segments,
                profile=0.5,
                affect="EDGES",
                clamp_overlap=True,
            )

        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z -= zmin
            if v.co.z < 0.002:
                v.co.z = 0.0

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = False
        for edge in bm.edges:
            edge.smooth = False
            if edge.is_manifold and len(edge.link_faces) == 2:
                if edge.calc_face_angle() < math.radians(25.0):
                    edge.smooth = True
        for face in stripe_faces:
            if face.is_valid:
                pass
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


def _long_axis(pts):
    """Principal axis of a point set, by power iteration on its covariance."""
    c = sum(pts, Vector()) / len(pts)
    cov = [[0.0] * 3 for _ in range(3)]
    for p in pts:
        d = p - c
        for i in range(3):
            for j in range(3):
                cov[i][j] += d[i] * d[j]
    v = Vector((1.0, 0.3, 0.1))
    for _ in range(30):
        w = Vector([sum(cov[i][j] * v[j] for j in range(3)) for i in range(3)])
        if w.length < 1e-12:
            break
        v = w.normalized()
    return v


def paint_planks(me):
    """Per-shell ``PlankTone`` and ``GrainDir`` face attributes for the wood shader.

    Every post, rail, slat and plank is its own shell, so each gets one
    tone and grain running along its own long axis. The awning shells take
    the attributes too; their materials never read them.
    """
    tone = [0.5] * len(me.polygons)
    grain = [(0.0, 0.0, 1.0)] * len(me.polygons)
    owner = {}
    rng = random.Random(TONE_SEED)
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        d = _long_axis(pts) if len(pts) > 2 else Vector((0.0, 0.0, 1.0))
        t = 0.5 + rng.uniform(-PLANK_TONE_JITTER, PLANK_TONE_JITTER)
        for i in g:
            owner[i] = (t, tuple(d))
    for poly in me.polygons:
        t, d = owner[poly.vertices[0]]
        tone[poly.index] = t
        grain[poly.index] = d
    a = me.attributes.new("PlankTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)
    b = me.attributes.new("GrainDir", "FLOAT_VECTOR", "FACE")
    b.data.foreach_set("vector", [c for v in grain for c in v])


def _sock(sockets, identifier):
    """A Mix-node socket by identifier; its A/B/Result names repeat per type."""
    return next(sk for sk in sockets if sk.identifier == identifier)


def wood_material(name):
    """Grain along each stave or board (``GrainDir``), tone per piece (``PlankTone``)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    gdir = nt.nodes.new("ShaderNodeAttribute")
    gdir.attribute_name = "GrainDir"
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "PlankTone"
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(coord.outputs["Object"], dot.inputs[0])
    nt.links.new(gdir.outputs["Vector"], dot.inputs[1])
    squash = nt.nodes.new("ShaderNodeMath")
    squash.operation = "MULTIPLY"
    squash.inputs[1].default_value = 0.94
    nt.links.new(dot.outputs["Value"], squash.inputs[0])
    along = nt.nodes.new("ShaderNodeVectorMath")
    along.operation = "SCALE"
    nt.links.new(gdir.outputs["Vector"], along.inputs[0])
    nt.links.new(squash.outputs["Value"], along.inputs["Scale"])
    grain_co = nt.nodes.new("ShaderNodeVectorMath")
    grain_co.operation = "SUBTRACT"
    nt.links.new(coord.outputs["Object"], grain_co.inputs[0])
    nt.links.new(along.outputs["Vector"], grain_co.inputs[1])
    shift = nt.nodes.new("ShaderNodeVectorMath")
    shift.operation = "ADD"
    nt.links.new(grain_co.outputs["Vector"], shift.inputs[0])
    nt.links.new(tone.outputs["Fac"], shift.inputs[1])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = WOOD_GRAIN_SCALE
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.62
    nt.links.new(shift.outputs["Vector"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.12, 0.052, 0.018, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.38, 0.18, 0.065, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 1.1
    gain.inputs[2].default_value = 0.45
    nt.links.new(tone.outputs["Fac"], gain.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(ramp.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(gain.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.72
    rough.inputs["To Max"].default_value = 0.52
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def stall_materials():
    """(wood, stripe_a, stripe_b): shared by the check, the render and inspection.

    The first build was one flat brown for every piece of timber and two
    flat stripe colours, so the frame read as a single moulding. Wood now
    carries grain and a tone per piece; the canvas carries faint dirt so
    the stripes read as cloth, not paint.
    """
    wood = wood_material("StallWood")
    stripe_a = principled(
        "StallStripeA", (0.62, 0.075, 0.055, 1.0), 0.0, 0.78,
        noise_scale=26.0, wear=(0.46, 0.07, 0.05, 1.0),
    )
    stripe_b = principled(
        "StallStripeB", (0.80, 0.72, 0.54, 1.0), 0.0, 0.80,
        noise_scale=26.0, wear=(0.62, 0.55, 0.40, 1.0),
    )
    return wood, stripe_a, stripe_b


def assign_slots(obj, wood, stripe_a, stripe_b):
    # Do not materials.clear() — that resets polygon material_index to 0
    # on this Blender, which would drop awning stripes onto wood.
    mats = obj.data.materials
    wanted = (wood, stripe_a, stripe_b)
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


def aabb_overlap(a, b):
    x = min(a[3], b[3]) - max(a[0], b[0])
    y = min(a[4], b[4]) - max(a[1], b[1])
    z = min(a[5], b[5]) - max(a[2], b[2])
    if x <= 0.0 or y <= 0.0 or z <= 0.0:
        return 0.0
    return x * y * z


def mat_of(me, group):
    member = set(group)
    for poly in me.polygons:
        if all(i in member for i in poly.vertices):
            return poly.material_index
    return None


def support_audit(me):
    """Post feet: wrap plates clustered at the four frame corners."""
    plates = []
    for group in shells(me):
        if mat_of(me, group) != WOOD_IDX:
            continue
        a = shell_aabb(me, group)
        dz = a[5] - a[2]
        dx = a[3] - a[0]
        dy = a[4] - a[1]
        cz = 0.5 * (a[2] + a[5])
        if cz > 0.10 or dz > 0.10:
            continue
        if max(dx, dy) < POST * 0.8:
            continue
        plates.append(a)
    corners = {}
    for a in plates:
        cx = 0.5 * (a[0] + a[3])
        cy = 0.5 * (a[1] + a[4])
        key = (1 if cx > 0.0 else -1, 1 if cy > 0.0 else -1)
        corners.setdefault(key, []).append(a)
    zmin = min((a[2] for a in plates), default=99.0)
    return {"feet": len(corners), "foot_z": zmin}


def joint_audit(me):
    """Braces must not occupy the counter volume. Headers bite the posts."""
    hx = WIDTH / 2.0
    groups = shells(me)
    boxes = [(g, shell_aabb(me, g), mat_of(me, g)) for g in groups]
    posts = []
    headers = []
    braces = []
    slats = []
    for _g, a, mat in boxes:
        if mat != WOOD_IDX:
            continue
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        cx = 0.5 * (a[0] + a[3])
        cy = 0.5 * (a[1] + a[4])
        cz = 0.5 * (a[2] + a[5])
        if dz > FRONT_H * 0.55 and dx < POST * 2.4 and dy < POST * 2.4:
            posts.append(a)
            continue
        if dx > WIDTH * 0.6 and dz < POST * 2.2 and dy < POST * 2.2 and cz > FRONT_H * 0.7:
            headers.append(a)
            continue
        if abs(cx) > hx - POST * 1.8 and dz > 0.35 and dy > 0.25 and dx < 0.20:
            braces.append(a)
            continue
        if abs(cz - COUNTER_Z) < 0.08 and dx > WIDTH * 0.4:
            slats.append(a)
    overlap = 0.0
    for brace in braces:
        for slat in slats:
            overlap = max(overlap, aabb_overlap(brace, slat))
    pairs = [
        min(h[3] - p[0], p[3] - h[0])
        for h in headers
        for p in posts
        if abs(0.5 * (h[1] + h[4]) - 0.5 * (p[1] + p[4])) < POST * 2.0
    ]
    engage = min(pairs) if pairs else 1.0
    frame_posts = [p for p in posts if abs(0.5 * (p[0] + p[3])) > hx - POST]
    # Side plates sit on the headers and pass the brace shape test too;
    # the braces proper are the ones below the front header.
    side_braces = [b for b in braces if b[2] < FRONT_H - 2.0 * POST]
    seats = []
    for brace in side_braces:
        bx = 0.5 * (brace[0] + brace[3])
        side = [p for p in frame_posts if abs(0.5 * (p[0] + p[3]) - bx) < POST]
        front = [p for p in side if 0.5 * (p[1] + p[4]) < 0.0]
        back = [p for p in side if 0.5 * (p[1] + p[4]) > 0.0]
        if not front or not back:
            seats.append(-1.0)
            continue
        seats.append(min(front[0][4] - brace[1], brace[4] - back[0][1]))
    return {
        "brace_seat": min(seats) if seats else -1.0,
        "side_braces": len(side_braces),
        "posts": len(posts),
        "headers": len(headers),
        "braces": len(braces),
        "slats": len(slats),
        "overlap": overlap,
        "engage": engage,
    }


def awning_seat(me):
    """Gap from front-header top to awning underside, at the front eave."""
    hy = DEPTH / 2.0
    wood_z = []
    stripe_z = []
    for poly in me.polygons:
        zs = [me.vertices[i].co.z for i in poly.vertices]
        ys = [me.vertices[i].co.y for i in poly.vertices]
        cy = sum(ys) / len(ys)
        if cy > -hy + 0.15:
            continue
        zmax = max(zs)
        zmin = min(zs)
        if poly.material_index == WOOD_IDX and zmax > FRONT_H - 0.12:
            if max(ys) - min(ys) > 0.028:
                wood_z.append(zmax)
        if poly.material_index in (STRIPE_A_IDX, STRIPE_B_IDX) and zmax > FRONT_H:
            stripe_z.append(zmin)
    if not wood_z or not stripe_z:
        return 99.0
    return min(stripe_z) - max(wood_z)


def plumb_audit(me):
    """XY centroid of each post's bottom slab vs top slab."""
    drifts = []
    for group in shells(me):
        if mat_of(me, group) != WOOD_IDX:
            continue
        a = shell_aabb(me, group)
        dz = a[5] - a[2]
        dx = a[3] - a[0]
        dy = a[4] - a[1]
        if dz < FRONT_H * 0.55 or dx > POST * 2.4 or dy > POST * 2.4:
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


def frame_size(me):
    """Post-foot envelope vs declared stall plan, not the awning AABB."""
    hx = WIDTH / 2.0
    hy = DEPTH / 2.0
    xs, ys, zs = [], [], []
    for group in shells(me):
        if mat_of(me, group) != WOOD_IDX:
            continue
        a = shell_aabb(me, group)
        dz = a[5] - a[2]
        dx = a[3] - a[0]
        dy = a[4] - a[1]
        cx = 0.5 * (a[0] + a[3])
        cy = 0.5 * (a[1] + a[4])
        if dz > FRONT_H * 0.55 and dx < POST * 2.4 and dy < POST * 2.4:
            xs.extend((a[0], a[3]))
            ys.extend((a[1], a[4]))
            zs.append(a[5])
            continue
        if dz < 0.08 and abs(cx) > hx - POST * 1.6 and abs(cy) > hy - POST * 1.6:
            zs.append(a[2])
    if not xs:
        return 0.0, 0.0, 0.0
    return max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, COUNTER_Z))
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
    img = bpy.data.images.new("StallNrm", size, size, alpha=True, float_buffer=False)
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


def check(
    skip_decimate,
    lift_z=False,
    stray_vert=False,
    short_feet=False,
    low_brace=False,
    float_awning=False,
    rake_posts=False,
    short_brace=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_stall_mesh(
        "StallLow",
        bevel_offset=0.006,
        bevel_segments=2,
        low_brace=low_brace,
        float_awning=float_awning,
        rake_posts=rake_posts,
        short_feet=short_feet,
        short_brace=short_brace,
    )
    high = build_stall_mesh(
        "StallHigh",
        bevel_offset=0.006,
        bevel_segments=4,
        low_brace=low_brace,
        float_awning=float_awning,
        rake_posts=rake_posts,
        short_feet=short_feet,
        short_brace=short_brace,
    )
    paint_planks(low.data)
    paint_planks(high.data)
    wood, stripe_a, stripe_b = stall_materials()
    assign_slots(low, wood, stripe_a, stripe_b)
    assign_slots(high, wood, stripe_a, stripe_b)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("stall mesh did not build", 3), None, None, None, None, None

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
    seat = awning_seat(low.data)
    plumb = plumb_audit(low.data)
    fx, fy, fz = frame_size(low.data)

    img, tex = setup_bake_image(low, wood)
    if img is None:
        return fail("stall has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "StallLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "StallLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_stall_mesh("StallColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "StallCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_market_stall_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender sets TMPDIR from its own preference, which resolves to the
    # working directory on a stock portable build, so every run left a .glb
    # in the repo root. The budget only needs the byte count.
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

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
        f"measured feet={sup['feet']} foot_z={sup['foot_z']:.5f} "
        f"brace_overlap={jnt['overlap']:.6f} brace_seat={jnt['brace_seat']:.4f} "
        f"side_braces={jnt['side_braces']} engage={jnt['engage']:.4f} "
        f"seat={seat:.5f} plumb={plumb:.5f} frame=({fx:.4f},{fy:.4f},{fz:.4f})"
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
    if idx_counts.get(STRIPE_A_IDX, 0) < 16:
        return fail(
            f"stripe A faces {idx_counts.get(STRIPE_A_IDX, 0)} < 16",
            5,
        ), None, None, None, None, None
    if idx_counts.get(STRIPE_B_IDX, 0) < 16:
        return fail(
            f"stripe B faces {idx_counts.get(STRIPE_B_IDX, 0)} < 16",
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
    if bb[2] > ZMIN_EPS or sup["feet"] != FOOT_COUNT or sup["foot_z"] > FOOT_ZMIN_MAX:
        return fail(
            f"grounded zmin={bb[2]:.5f} feet={sup['feet']} "
            f"foot_z={sup['foot_z']:.5f}",
            16,
        ), None, None, None, None, None
    if jnt["overlap"] > BRACE_COUNTER_OVERLAP_MAX or jnt["engage"] < TENON * 0.4:
        return fail(
            f"joint overlap={jnt['overlap']:.6f} engage={jnt['engage']:.4f} "
            f"posts={jnt['posts']} braces={jnt['braces']} slats={jnt['slats']}",
            17,
        ), None, None, None, None, None
    if jnt["side_braces"] != BRACE_COUNT or jnt["brace_seat"] < BRACE_SEAT_MIN:
        return fail(
            f"brace seat {jnt['brace_seat']:.4f} < {BRACE_SEAT_MIN} "
            f"side_braces={jnt['side_braces']} (want {BRACE_COUNT})",
            17,
        ), None, None, None, None, None
    if seat < AWNING_SEAT_MIN or seat > AWNING_SEAT_MAX:
        return fail(f"awning seat gap {seat:.5f} > {AWNING_SEAT_MAX}", 18), None, None, None, None, None
    if (
        plumb > POST_PLUMB_MAX
        or abs(fx - WIDTH) > FRAME_XY_TOL
        or abs(fy - DEPTH) > FRAME_XY_TOL
    ):
        return fail(
            f"plumb={plumb:.5f} frame=({fx:.4f},{fy:.4f},{fz:.4f}) "
            f"off {WIDTH}x{DEPTH}",
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

    low.rotation_euler.z = math.radians(-18.0)
    low.rotation_euler.x = math.radians(2.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
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

    light("Key", (-3.6, -5.0, 5.8), 680.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.6, 2.6), 48.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.4, 4.2, 4.1), 640.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    bb = world_bbox(low)
    span = max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], 0.2)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (span * 2.17, -span * 2.95, span * 1.12)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, -0.04 * span, 0.52 * (bb[2] + bb[5]))
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
    p.add_argument("--short-feet", action="store_true")
    p.add_argument("--low-brace", action="store_true")
    p.add_argument("--float-awning", action="store_true")
    p.add_argument("--rake-posts", action="store_true")
    p.add_argument("--short-brace", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_feet=args.short_feet,
        low_brace=args.low_brace,
        float_awning=args.float_awning,
        rake_posts=args.rake_posts,
        short_brace=args.short_brace,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("market-stall OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
