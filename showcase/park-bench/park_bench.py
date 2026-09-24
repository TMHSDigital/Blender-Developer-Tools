"""Game-ready park bench — a showcase piece, not an example.

Asserts budget conformance of a procedural wrought-iron bench after
composing shipped pipeline pieces: bmesh construction, UVs, two
materials, high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

Every leg is one round bar swept along one path: a quarter-circle toe
scroll about (hy ± R, R), the post, and at the back a bend into the
reclined upright that carries the back slats. Seat slats bear on the side
rails, back slats on the uprights, armrests on the arm bar and the front
leg's tenon, each by a named bite. Stations are shared (HX, HY, SEAT_Z,
ARM_Z, SCROLL_R, BACK_TOP).

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` LOD, ``--stray-vert`` hygiene, ``--lift-z``
zmin, ``--short-feet`` named toes, ``--float-stretcher`` stretcher seat,
``--gap-slats`` slat-to-leg, ``--narrow-seat`` sitting width,
``--float-slats`` bearing bite (20), ``--split-feet`` legs in one piece
(21), ``--upright-back`` back recline (19).

Slat widths use closed-form ``sin(i)``; plank tones use a seeded RNG. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python park_bench.py --
    blender --background --python park_bench.py -- --skip-decimate
    blender --background --python park_bench.py -- --output bench.png
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

SEAT_W = 1.40
SEAT_D = 0.50
SEAT_Z = 0.43
N_SEAT = 7
N_BACK = 5
SLAT_T = 0.030
BACK_H = 0.38
IRON_T = 0.024
SCROLL_R = 0.11
SCROLL_N = 12
ARM_Z = 0.64
ARM_SCROLL_R = 0.055
STRETCHER_Z = 0.16
POST_INSET_X = 0.07
POST_INSET_Y = 0.045
BAR_R = IRON_T / 2.0
TUBE_SEGS = 8
RECLINE_DEG = 12.0
BEND_R = 0.10
BEND_N = 4
UPRIGHT_N = 4
TOP_RAIL_R = BAR_R * 1.25
BACK_TOP = SEAT_Z + SLAT_T + BACK_H + 0.02
BACK_CLEAR = 0.012
SLAT_BITE = 0.003
ARM_OVER = 0.075
ARM_TENON = 0.004
LEG_TENON = 0.012
BRACKET_R = 0.05
BRACKET_N = 8
BRACKET_BITE = 0.008
HX = SEAT_W / 2.0 - POST_INSET_X
HY = SEAT_D / 2.0 - POST_INSET_Y
SEAT_SPAN = 2.0 * HX
SEAT_SPAN_TOL = 0.08

BBOX_TOL = 0.015
OUTER_SIZE = (1.295, 0.632, 0.887)
BASE_TRIS_MIN = 2900
BASE_TRIS_MAX = 3700
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 180
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
METAL_FACES_MIN = 48
WOOD_FACES_MIN = 24
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.998
STRETCHER_GAP_MAX = 0.008
SLAT_GAP_MAX = 0.008
TOE_COUNT = 4
TOE_ZMIN_MAX = 0.002
FLOAT_STRETCHER = 0.10
GAP_SLAT = 0.10
SHORT_FOOT = 0.16
LIFT_Z = 0.05
NARROW_SEAT = 0.55
LEG_COUNT = 4
BITE_MIN = 0.0015
FLOAT_SLATS = 0.006
RECLINE_MIN_DEG = 9.0
RECLINE_MAX_DEG = 16.0
PLANK_TONE_JITTER = 0.28
TONE_SEED = 23
WOOD_GRAIN_SCALE = 30.0

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


def add_sweep(bm, pts, radius, mat_idx, segs=None):
    """Round bar along a polyline, parallel-transported frames, fan caps.

    Every leg is one sweep: the toe scroll, the post and (at the back) the
    reclined upright are a single bar, the way a smith bends it. A foot
    built as its own arc under a separate post leaves daylight at the join.
    """
    segs = segs or TUBE_SEGS
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tangents = []
    for i in range(n):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = (pts[i + 1] - pts[i]).normalized() + (pts[i] - pts[i - 1]).normalized()
        tangents.append(t.normalized())
    t0 = tangents[0]
    ref = Vector((1.0, 0.0, 0.0)) if abs(t0.x) < 0.9 else Vector((0.0, 0.0, 1.0))
    side = t0.cross(ref).normalized()
    rings = []
    for i, p in enumerate(pts):
        t = tangents[i]
        if i > 0:
            side = tangents[i - 1].rotation_difference(t) @ side
            side = (side - t * side.dot(t)).normalized()
        up = t.cross(side).normalized()
        ring = []
        for k in range(segs):
            a = 2.0 * math.pi * k / segs
            ring.append(bm.verts.new(p + (side * math.cos(a) + up * math.sin(a)) * radius))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for k in range(segs):
            k2 = (k + 1) % segs
            bm.faces.new((a[k], a[k2], b[k2], b[k])).material_index = mat_idx
    for ring, p, flip in ((rings[0], pts[0], True), (rings[-1], pts[-1], False)):
        c = bm.verts.new(p)
        for k in range(segs):
            k2 = (k + 1) % segs
            f = bm.faces.new((c, ring[k2], ring[k]) if flip else (c, ring[k], ring[k2]))
            f.material_index = mat_idx
    return [v for ring in rings for v in ring]


def toe_arc(y_post, outward):
    """Quarter circle from the toe (on the floor) up to the post at z=R.

    Centre ``(y_post + outward*R, R)``: horizontal at the toe, tangent to
    the post where it meets it. Returned toe first.
    """
    cy = y_post + outward * SCROLL_R
    pts = []
    for i in range(SCROLL_N + 1):
        a = -0.5 * math.pi * (1.0 - i / SCROLL_N)
        pts.append((cy - outward * SCROLL_R * math.cos(a), SCROLL_R + SCROLL_R * math.sin(a)))
    return pts


def rear_leg_path(recline):
    """(y, z) centreline of a rear leg: toe, post, bend, reclined upright."""
    pts = toe_arc(HY, 1.0)
    pts.append((HY, SEAT_Z))
    # No bend at zero recline: its points would all land on one spot.
    for i in range(1, BEND_N + 1 if recline > 0.0 else 1):
        ph = recline * i / BEND_N
        pts.append((HY + BEND_R * (1.0 - math.cos(ph)), SEAT_Z + BEND_R * math.sin(ph)))
    y_f, z_f = pts[-1]
    y_t = y_f + (BACK_TOP - z_f) * math.tan(recline)
    for i in range(1, UPRIGHT_N + 1):
        f = i / UPRIGHT_N
        pts.append((y_f + (y_t - y_f) * f, z_f + (BACK_TOP - z_f) * f))
    return pts


def path_y_at(path, z):
    """y of a (y, z) path where it first crosses height z."""
    for (y0, z0), (y1, z1) in zip(path, path[1:]):
        if (z0 - z) * (z1 - z) <= 0.0 and abs(z1 - z0) > 1e-9:
            return y0 + (y1 - y0) * (z - z0) / (z1 - z0)
    return path[-1][0]


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


def build_bench_mesh(
    name,
    bevel_offset,
    bevel_segments,
    float_stretcher=False,
    gap_slats=False,
    short_feet=False,
    narrow_seat=False,
    float_slats=False,
    split_feet=False,
    upright_back=False,
):
    bm = bmesh.new()
    try:
        wood = []
        t = IRON_T
        r = BAR_R
        hx, hy = HX, HY
        recline = 0.0 if upright_back else math.radians(RECLINE_DEG)
        rear = rear_leg_path(recline)
        slat_span = SEAT_SPAN + t * 0.50
        if gap_slats:
            slat_span = SEAT_SPAN - IRON_T - 0.024
        if narrow_seat:
            slat_span = SEAT_SPAN * NARROW_SEAT

        # Seat slats bear on the side rails: the bottom face sits a named
        # bite below the rail's top line, so each slat is carried.
        rail_z = SEAT_Z - t * 0.35
        slat_z0 = rail_z + r - SLAT_BITE + (FLOAT_SLATS if float_slats else 0.0)
        usable = 2.0 * hy - 0.06
        gap = 0.010
        widths = []
        for i in range(N_SEAT):
            widths.append(1.0 + 0.10 * math.sin(i * 1.7 + 0.3))
        scale = (usable - gap * (N_SEAT - 1)) / sum(widths)
        y_cursor = -hy + 0.03
        for i, w in enumerate(widths):
            slat_w = w * scale
            y = y_cursor + slat_w * 0.5
            wood.extend(
                add_box(
                    bm,
                    (0.0, y, slat_z0 + SLAT_T / 2.0),
                    (slat_span, slat_w * 0.92, SLAT_T),
                    WOOD_IDX,
                )
            )
            y_cursor += slat_w + gap

        # Back slats are screwed to the front of the reclined uprights.
        y_f, z_f = rear[-1 - UPRIGHT_N]
        y_top, z_top = rear[-1]
        u = Vector((0.0, y_top - y_f, z_top - z_f))
        run = u.length
        u.normalize()
        fwd = Vector((0.0, -u.z, u.y))
        base = Vector((0.0, y_f, z_f))
        d0 = max(0.0, (SEAT_Z + SLAT_T + 0.04 - z_f) / max(u.z, 1e-6))
        d1 = run - r - BACK_CLEAR
        bwidths = [1.0 + 0.08 * math.sin(i * 1.4 + 0.8) for i in range(N_BACK)]
        bscale = ((d1 - d0) - gap * (N_BACK - 1)) / sum(bwidths)
        d_cursor = d0
        off = r + SLAT_T / 2.0 - SLAT_BITE
        for w in bwidths:
            slat_h = w * bscale
            c = base + u * (d_cursor + slat_h * 0.5) + fwd * off
            wood.extend(
                add_box(
                    bm,
                    tuple(c),
                    (slat_span, SLAT_T, slat_h * 0.90),
                    WOOD_IDX,
                    euler=(-recline, 0.0, 0.0),
                )
            )
            d_cursor += slat_h + gap

        # Armrests sit on the arm bar, overhang the front leg, and stop a
        # named tenon inside the reclined upright at their top edge.
        arm_bot = ARM_Z + r * 0.95 - SLAT_BITE
        arm_top = arm_bot + SLAT_T
        y_arm_end = path_y_at(rear, arm_top) - r / math.cos(recline) + ARM_TENON
        y_arm_0 = -hy - ARM_OVER
        for xsign in (-1.0, 1.0):
            wood.extend(
                add_box(
                    bm,
                    (xsign * hx, 0.5 * (y_arm_0 + y_arm_end), arm_bot + SLAT_T * 0.5),
                    (SLAT_T * 1.15, y_arm_end - y_arm_0, SLAT_T),
                    WOOD_IDX,
                )
            )

        if bevel_offset > 0.0:
            # A set of BMEdges iterates in memory order; sort by index so the
            # bevel lays its faces down in the same order every run.
            bm.edges.index_update()
            edges = sorted({e for v in wood for e in v.link_edges}, key=lambda e: e.index)
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

        leg_top = arm_bot + LEG_TENON
        for xsign in (-1.0, 1.0):
            x = xsign * hx
            front = toe_arc(-hy, -1.0)
            if split_feet:
                # The first build: foot arcs that stop short of the posts,
                # and posts that start at z=R, as separate shells.
                add_sweep(bm, [(x, y, z) for y, z in front[:-1]], r, METAL_IDX)
                add_sweep(bm, [(x, -hy, SCROLL_R), (x, -hy, leg_top)], r, METAL_IDX)
                add_sweep(bm, [(x, y, z) for y, z in rear[:SCROLL_N]], r, METAL_IDX)
                add_sweep(bm, [(x, y, z) for y, z in rear[SCROLL_N:]], r, METAL_IDX)
            else:
                front.append((-hy, leg_top))
                add_sweep(bm, [(x, y, z) for y, z in front], r, METAL_IDX)
                add_sweep(bm, [(x, y, z) for y, z in rear], r, METAL_IDX)
            add_sweep(
                bm,
                [(x, -hy, ARM_Z), (x, path_y_at(rear, ARM_Z), ARM_Z)],
                r * 0.95,
                METAL_IDX,
            )
            # Quarter-round bracket under the armrest's overhang: one end in
            # the leg, the other up inside the armrest.
            zc = arm_bot + BRACKET_BITE
            br = []
            for i in range(BRACKET_N + 1):
                a = 1.5 * math.pi - 0.5 * math.pi * i / BRACKET_N
                br.append((x, -hy + BRACKET_R * math.cos(a), zc + BRACKET_R * math.sin(a)))
            add_sweep(bm, br, r * 0.85, METAL_IDX)
            # Side seat rail, leg axis to leg axis.
            add_sweep(bm, [(x, -hy, rail_z), (x, hy, rail_z)], r, METAL_IDX)

        # Front and back rails stop half a bar inside the legs: ending on the
        # leg axis puts their end rings on the side rails' end rings.
        rx = hx - 0.5 * r
        add_sweep(bm, [(-rx, -hy, rail_z), (rx, -hy, rail_z)], r, METAL_IDX)
        add_sweep(bm, [(-rx, hy, rail_z), (rx, hy, rail_z)], r, METAL_IDX)
        # The top rail runs through the upright tops, a heavier bar that
        # swallows their end caps, out to the armrests' outer faces.
        tx = hx + SLAT_T * 1.15 * 0.5
        add_sweep(bm, [(-tx, y_top, z_top), (tx, y_top, z_top)], TOP_RAIL_R, METAL_IDX)

        st_trim = FLOAT_STRETCHER if float_stretcher else 0.0
        yx = hx - st_trim
        for xsign in (-1.0, 1.0):
            add_sweep(
                bm,
                [(xsign * yx, -hy, STRETCHER_Z), (xsign * yx, hy, STRETCHER_Z)],
                r * 0.9,
                METAL_IDX,
            )
        add_sweep(
            bm, [(-yx, 0.0, STRETCHER_Z), (yx, 0.0, STRETCHER_Z)], r * 0.9, METAL_IDX
        )

        if short_feet:
            for v in bm.verts:
                if v.co.z < SCROLL_R * 0.55 and abs(v.co.y) > hy + SCROLL_R * 0.35:
                    v.co.z += SHORT_FOOT

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
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        # Round bar is smooth-shaded; sawn slats keep their chamfer facets.
        for poly in me.polygons:
            poly.use_smooth = poly.material_index == METAL_IDX and len(poly.vertices) == 4
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

    Every slat and armrest is its own shell, so each gets one tone and
    grain along its own long axis. Iron shells get a tone too; the iron
    shader ignores it.
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
    """Grain along each slat (``GrainDir``), tone per slat (``PlankTone``)."""
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


def bench_materials():
    """(wood, metal): shared by the check, the render and inspection.

    The first build was one flat brown on every slat and satin iron
    (metallic 1.0, roughness 0.32) that read as chrome.
    """
    wood = wood_material("BenchWood")
    metal = principled(
        "BenchIron", (0.040, 0.042, 0.045, 1.0), 0.60, 0.55,
        noise_scale=18.0, wear=(0.11, 0.055, 0.028, 1.0),
    )
    return wood, metal


def assign_slots(obj, wood, metal):
    mats = obj.data.materials
    wanted = (wood, metal)
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


def shell_bvh_gap(me, ga, gb):
    bm_a = bmesh.new()
    bm_b = bmesh.new()
    try:
        bm_a.from_mesh(me)
        bm_b.from_mesh(me)
        keep_a, keep_b = set(ga), set(gb)
        drop_a = [f for f in bm_a.faces if not all(v.index in keep_a for v in f.verts)]
        drop_b = [f for f in bm_b.faces if not all(v.index in keep_b for v in f.verts)]
        if drop_a:
            bmesh.ops.delete(bm_a, geom=drop_a, context="FACES")
        if drop_b:
            bmesh.ops.delete(bm_b, geom=drop_b, context="FACES")
        if not bm_a.faces or not bm_b.faces:
            return 1e9
        tree = BVHTree.FromBMesh(bm_b)
        best = 1e9
        for v in bm_a.verts:
            hit = tree.find_nearest(v.co)
            if hit[0] is not None:
                best = min(best, hit[3])
        for f in bm_a.faces:
            hit = tree.find_nearest(f.calc_center_median())
            if hit[0] is not None:
                best = min(best, hit[3])
        return best
    finally:
        bm_a.free()
        bm_b.free()


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, SEAT_Z + 0.12))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def shell_bite(me, ga, gb):
    """Deepest vertex of shell ``ga`` inside closed shell ``gb`` (m); negative if none is."""
    bm_b = bmesh.new()
    try:
        bm_b.from_mesh(me)
        keep_b = set(gb)
        drop_b = [f for f in bm_b.faces if not all(v.index in keep_b for v in f.verts)]
        if drop_b:
            bmesh.ops.delete(bm_b, geom=drop_b, context="FACES")
        if not bm_b.faces:
            return -1e9
        bmesh.ops.recalc_face_normals(bm_b, faces=list(bm_b.faces))
        tree = BVHTree.FromBMesh(bm_b)
        best = -1e9
        for i in ga:
            co = me.vertices[i].co
            loc, nrm, _idx, dist = tree.find_nearest(co)
            if loc is None:
                continue
            depth = dist if (co - loc).dot(nrm) < 0.0 else -dist
            best = max(best, depth)
        return best
    finally:
        bm_b.free()


def joint_audit(me):
    groups = shells(me)
    owner = {}
    for gi, g in enumerate(groups):
        for i in g:
            owner[i] = gi
    rail_z = SEAT_Z - IRON_T * 0.35 + BAR_R
    arm_z = ARM_Z + BAR_R
    posts = []
    stretchers = []
    slats = []
    seat_slats = []
    back_slats = []
    side_rails = []
    arm_bars = []
    armrests = []
    for gi, g in enumerate(groups):
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        cz = 0.5 * (a[2] + a[5])
        mat = mat_of(me, g)
        # A leg is one bar from toe to arm (front) or back top (rear); it is
        # thin across the bench and tall, whatever its depth in plan.
        if mat == METAL_IDX and dz > 0.28 and dx < 0.08:
            posts.append((g, a, gi))
        if mat == METAL_IDX and abs(cz - STRETCHER_Z) < 0.05 and max(dx, dy) > 0.25:
            stretchers.append((g, a))
        if mat == METAL_IDX and dx < 0.08 and dy > 0.30 and dz < 0.05:
            if abs(cz - rail_z) < 0.02:
                side_rails.append((g, a))
            elif abs(cz - arm_z) < 0.02:
                arm_bars.append((g, a))
        if mat == WOOD_IDX and dz < 0.08 and dx > SEAT_SPAN * 0.4:
            slats.append((g, a))
            (seat_slats if cz < SEAT_Z + 0.10 else back_slats).append((g, a))
        if mat == WOOD_IDX and dx < 0.08 and dy > 0.20:
            armrests.append((g, a))
    metal_verts = []
    for poly in me.polygons:
        if poly.material_index != METAL_IDX:
            continue
        for i in poly.vertices:
            metal_verts.append(i)
    stations = (
        (HX, HY + SCROLL_R, 0.0),
        (HX, -HY - SCROLL_R, 0.0),
        (-HX, HY + SCROLL_R, 0.0),
        (-HX, -HY - SCROLL_R, 0.0),
    )
    toes = 0
    toe_z = 99.0
    leg_ids = {gi for _g, _a, gi in posts}
    tall = {gi for _g, a, gi in posts if a[5] >= SEAT_Z}
    continuous = set()
    for sx, sy, sz in stations:
        nearby = []
        for i in metal_verts:
            co = me.vertices[i].co
            d = ((co.x - sx) ** 2 + (co.y - sy) ** 2) ** 0.5
            if d < SCROLL_R * 0.55:
                nearby.append(i)
        if nearby:
            toes += 1
            toe_z = min(toe_z, min(me.vertices[i].co.z for i in nearby))
            # The toe's own shell must be a leg that reaches the seat: a
            # foot that is a separate arc under its post fails here.
            low = min(nearby, key=lambda i: me.vertices[i].co.z)
            gi = owner[low]
            if gi in leg_ids and gi in tall:
                continuous.add(gi)
    st_gap = 99.0
    if stretchers and posts:
        st_gap = min(shell_bvh_gap(me, s[0], p[0]) for s in stretchers for p in posts)
    slat_gap = 99.0
    if slats and posts:
        slat_gap = min(shell_bvh_gap(me, s[0], p[0]) for s in slats for p in posts)
    seat_x = 0.0
    if slats:
        xs = [v for _g, a in slats for v in (a[0], a[3])]
        seat_x = max(xs) - min(xs)

    # Bearing bites: every seat slat is carried by both side rails, every
    # back slat by both reclined uprights, every armrest by its front leg
    # and its arm bar. Deepest carrier vertex inside the carried shell.
    rear = [(g, a) for g, a, _gi in posts if a[5] > ARM_Z + 0.10]
    front = [(g, a) for g, a, _gi in posts if a[5] <= ARM_Z + 0.10]
    bites = []
    # Overlap depth either way round: a rail has vertices only at its ends,
    # so under a mid-span slat it is the slat's corner that sits in the rail.
    def overlap(ga, gb):
        return max(shell_bite(me, ga, gb), shell_bite(me, gb, ga))

    for s, _a in seat_slats:
        for rl, _b in side_rails:
            bites.append(("seat", overlap(rl, s)))
    for s, _a in back_slats:
        for up, _b in rear:
            bites.append(("back", overlap(up, s)))
    for s, a in armrests:
        side = 0.5 * (a[0] + a[3])
        for host, b in front + arm_bars:
            if abs(0.5 * (b[0] + b[3]) - side) < 0.05:
                bites.append(("arm", overlap(host, s)))
    bite_min = min((b for _k, b in bites), default=-1.0)
    bite_kind = min(bites, key=lambda kb: kb[1])[0] if bites else "none"

    # Recline of each rear upright: centroids of a low and a high slab.
    recl = []
    for g, a in rear:
        lo_s = [me.vertices[i].co for i in g if SEAT_Z + 0.16 <= me.vertices[i].co.z <= SEAT_Z + 0.26]
        hi_s = [me.vertices[i].co for i in g if a[5] - 0.16 <= me.vertices[i].co.z <= a[5] - 0.06]
        if lo_s and hi_s:
            c0 = sum(lo_s, Vector()) / len(lo_s)
            c1 = sum(hi_s, Vector()) / len(hi_s)
            recl.append(math.degrees(math.atan2(abs(c1.y - c0.y), c1.z - c0.z)))
    return {
        "toes": toes,
        "toe_z": toe_z,
        "posts": len(posts),
        "stretchers": len(stretchers),
        "st_gap": st_gap,
        "slat_gap": slat_gap,
        "seat_x": seat_x,
        "slats": len(slats),
        "legs_whole": len(continuous),
        "seat_slats": len(seat_slats),
        "back_slats": len(back_slats),
        "side_rails": len(side_rails),
        "arm_bars": len(arm_bars),
        "armrests": len(armrests),
        "bites": len(bites),
        "bite_min": bite_min,
        "bite_kind": bite_kind,
        "recline": recl,
    }


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("BenchNrm", size, size, alpha=True, float_buffer=False)
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
    float_stretcher=False,
    gap_slats=False,
    short_feet=False,
    narrow_seat=False,
    float_slats=False,
    split_feet=False,
    upright_back=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    kw = dict(
        float_stretcher=float_stretcher,
        gap_slats=gap_slats,
        short_feet=short_feet,
        narrow_seat=narrow_seat,
        float_slats=float_slats,
        split_feet=split_feet,
        upright_back=upright_back,
    )
    low = build_bench_mesh("BenchLow", bevel_offset=0.004, bevel_segments=2, **kw)
    high = build_bench_mesh("BenchHigh", bevel_offset=0.004, bevel_segments=4, **kw)
    paint_planks(low.data)
    paint_planks(high.data)
    wood, metal = bench_materials()
    assign_slots(low, wood, metal)
    assign_slots(high, wood, metal)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("bench mesh did not build", 3), None, None, None, None, None

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
        return fail("bench has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BenchLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BenchLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_bench_mesh(
        "BenchColSrc", bevel_offset=0.0, bevel_segments=1, **kw
    )
    collider = convex_hull_collider(collider_src, "BenchCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_park_bench_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        # Measured; do not leave a .glb per run in the temp directory.
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
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}"
    )
    print(
        f"measured toes={jnt['toes']} toe_z={jnt['toe_z']:.5f} "
        f"posts={jnt['posts']} stretchers={jnt['stretchers']} "
        f"st_gap={jnt['st_gap']:.5f} slat_gap={jnt['slat_gap']:.5f} "
        f"seat_x={jnt['seat_x']:.4f} slats={jnt['slats']}"
    )
    recl = jnt["recline"]
    print(
        f"measured legs_whole={jnt['legs_whole']} seat_slats={jnt['seat_slats']} "
        f"back_slats={jnt['back_slats']} side_rails={jnt['side_rails']} "
        f"arm_bars={jnt['arm_bars']} armrests={jnt['armrests']} "
        f"bites={jnt['bites']} bite_min={jnt['bite_min']:.5f} ({jnt['bite_kind']}) "
        f"recline={[round(v, 2) for v in recl]}"
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
    if idx_counts.get(WOOD_IDX, 0) < WOOD_FACES_MIN:
        return fail(
            f"wood faces {idx_counts.get(WOOD_IDX, 0)} < {WOOD_FACES_MIN}",
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
    if abs(jnt["seat_x"] - SEAT_SPAN) > SEAT_SPAN_TOL:
        return fail(
            f"seat span {jnt['seat_x']:.4f} off {SEAT_SPAN}",
            19,
        ), None, None, None, None, None
    if bb[2] > ZMIN_EPS or jnt["toes"] != TOE_COUNT or jnt["toe_z"] > TOE_ZMIN_MAX:
        return fail(
            f"grounded zmin={bb[2]:.5f} toes={jnt['toes']} toe_z={jnt['toe_z']:.5f}",
            16,
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
    if jnt["stretchers"] < 2 or jnt["st_gap"] > STRETCHER_GAP_MAX:
        return fail(
            f"stretcher gap {jnt['st_gap']:.5f} stretchers={jnt['stretchers']}",
            17,
        ), None, None, None, None, None
    if jnt["slats"] < 4 or jnt["slat_gap"] > SLAT_GAP_MAX:
        return fail(
            f"slat gap {jnt['slat_gap']:.5f} slats={jnt['slats']}",
            18,
        ), None, None, None, None, None
    want_bites = 2 * N_SEAT + 2 * N_BACK + 4
    if (
        jnt["seat_slats"] != N_SEAT or jnt["back_slats"] != N_BACK
        or jnt["side_rails"] != 2 or jnt["arm_bars"] != 2 or jnt["armrests"] != 2
        or jnt["bites"] != want_bites or jnt["bite_min"] < BITE_MIN
    ):
        return fail(
            f"bearing bite {jnt['bite_min']:.5f} ({jnt['bite_kind']}) < {BITE_MIN} "
            f"or members seat={jnt['seat_slats']} back={jnt['back_slats']} "
            f"rails={jnt['side_rails']} bars={jnt['arm_bars']} "
            f"arms={jnt['armrests']} bites={jnt['bites']}/{want_bites}",
            20,
        ), None, None, None, None, None
    if jnt["legs_whole"] != LEG_COUNT:
        return fail(
            f"legs bent in one piece toe to seat {jnt['legs_whole']} != {LEG_COUNT}",
            21,
        ), None, None, None, None, None
    if len(recl) != 2 or not all(RECLINE_MIN_DEG <= v <= RECLINE_MAX_DEG for v in recl):
        return fail(
            f"back recline {recl} not in [{RECLINE_MIN_DEG}, {RECLINE_MAX_DEG}] deg",
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

    # Level on the floor: an X tilt sinks the front toes and lifts the back.
    low.rotation_euler.z = math.radians(-14.0)

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

    light("Key", (-3.6, -5.0, 5.4), 660.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.4, 2.4), 46.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.2, 4.0, 3.8), 600.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.22, -2.90, 1.34)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.42)
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
    p.add_argument("--float-stretcher", action="store_true")
    p.add_argument("--gap-slats", action="store_true")
    p.add_argument("--narrow-seat", action="store_true")
    p.add_argument("--float-slats", action="store_true")
    p.add_argument("--split-feet", action="store_true")
    p.add_argument("--upright-back", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_stretcher=args.float_stretcher,
        gap_slats=args.gap_slats,
        short_feet=args.short_feet,
        narrow_seat=args.narrow_seat,
        float_slats=args.float_slats,
        split_feet=args.split_feet,
        upright_back=args.upright_back,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("park-bench OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
