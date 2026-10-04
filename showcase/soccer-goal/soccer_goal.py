"""Game-ready freestanding youth soccer goal — a showcase piece, not an example.

Asserts budget conformance of a procedural 5 x 2 m freestanding goal after
composing shipped pipeline pieces: bmesh construction, UVs, ten materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

The goal stands on a patch of turf with a painted goal line. Two posts and a
crossbar are one white-painted aluminium extrusion: an oval section with a
net channel down its back, mitred and welded at the two top corners, a weld
bead standing round each mitre. A cast corner bracket bolted behind each
mitre carries a socket for a sloped rear net support, which runs down to a
cast corner hub on the ground. Each post stands in a cast foot connector: a
foot plate, a collar round the post and a socket for a side ground bar. Two
side bars and a back bar, dark powder-coated steel, close the ground frame
between the foot connectors and the hubs. The ground frame is pinned down by
four galvanised U-staples over the bars and a spike through each hub and
each foot plate.

The net is a woven diamond mesh of 120 mm cells, one back panel and two side
panels. Each panel is edged with a red head rope, and each head rope is
threaded through black nylon clips, a saddle on the member and a loop
standing off it, along the crossbar, the posts, the supports and the ground
bars. The back panel sags between its supports as a catenary in both
directions; the side panels belly outward and droop.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-bar`` every ground bar
bedded in the turf, ``--short-support`` every support seated in its sockets,
``--unclip-net`` the head rope threaded through every clip, ``--wide-mouth``
the goal mouth's clear size, ``--taut-net`` the back panel's sag.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python soccer_goal.py --
    blender --background --python soccer_goal.py -- --skip-decimate
    blender --background --python soccer_goal.py -- --output goal.png
"""
import argparse
import math
import os
import sys
import tempfile
import traceback

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

# Showcase lives at repo-root/showcase/, not under examples/. The framing
# helper is the repo's only shared import and lives next to the examples;
# resolve the repo root so we do not move gallery_framing.py.
_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402
import gallery_asset_quality  # noqa: E402

# --- Declared size: a 5 x 2 m youth (7-a-side) goal -------------------------
MOUTH_W = 5.000             # clear width, inner post face to inner post face
MOUTH_H = 2.000             # clear height, turf to crossbar underside
WIDE_MOUTH = 0.030          # --wide-mouth: the posts stand 15 mm further out each
DEPTH = 1.500               # goal line to the back bar's axis

# --- Turf patch --------------------------------------------------------------
TURF_T = 0.050              # turf top; its underside is the ground (z = 0)
TURF_X = 3.100
TURF_Y0 = -0.720
TURF_Y1 = 1.900
TURF_EDGE = 0.010           # rolled edge of the cut turf
LINE_HALF = 0.060           # goal line: as wide as the posts are deep

# --- Frame extrusion ---------------------------------------------------------
POST_HA = 0.050             # in the frame's plane
POST_HB = 0.060             # front to back
SEC_P = 2.3                 # section superellipse exponent
SEC_N = 44
SLOT_HW = 0.009             # net channel down the back
SLOT_D = 0.011
POST_FOOT = 0.020           # post bottom above the turf, inside its collar
POST_STEP = 0.21
BAR_STEP = 0.26
BEAD_R = 0.0028

# --- Ground frame and supports -----------------------------------------------
BAR_R = 0.020
BAR_BITE = 0.0025           # the bars bed this far into the turf
SUPPORT_R = 0.022
SUPPORT_TOP = 0.009         # the support runs this far past its rope corner into the bracket
                            # (the socket boss starts 5 mm past it: caps never share a plane)
TUBE_SIDES = 24
FLOAT_BAR = 0.008           # --float-bar lifts the back bar
SHORT_SUPPORT = 0.090       # --short-support stops the left support short of its hub

# --- Clips, rope and net -----------------------------------------------------
SADDLE_HL = 0.016
SADDLE_HW = 0.010
SADDLE_T = 0.009
SADDLE_BITE = 0.003
HOOK_R = 0.0095
HOOK_MINOR = 0.0022
HOOK_BITE = 0.001
ROPE_R = 0.0060
ROPE_SIDES = 8
CORD_R = 0.0032
CORD_SIDES = 4
CORD_LIFT = 0.4             # the two families pass over and under at each knot
MESH = 0.120                # diamond cell side
CLIP_PITCH = 0.42
SAG = 0.140                 # back panel, vertical, at mid-panel
SAG_K = 1.5                 # catenary shape factor
SIDE_BULGE = 0.050
SIDE_DROOP = 0.025
UNCLIP = 0.020              # --unclip-net drops the crossbar's head rope

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (6.220, 2.640, 2.153)
BASE_TRIS_MIN = 34000
BASE_TRIS_MAX = 35600
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 10
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 190
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
PAINT_FACES_MIN = 2300
CORD_FACES_MIN = 8300
ROPE_FACES_MIN = 150
STEEL_FACES_MIN = 310
CAST_FACES_MIN = 1350
NYLON_FACES_MIN = 3300
GALV_FACES_MIN = 920
TURF_FACES_MIN = 180
CHALK_FACES_MIN = 16
SOIL_FACES_MIN = 95

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Ground frame: every bar bedded into the turf top read off the mesh.
BAR_COUNT = 3
BED_MIN = 0.0015
BED_MAX = 0.0040
# Supports: both ends run this far inside a cast socket.
SUPPORT_COUNT = 2
INSERT_MIN = 0.040
# Clips: the head rope's axis passes through every loop without touching it.
CLIP_COUNT = 53
SEAT_MAX = 0.0012
# Mouth: clear opening, posts plumb, crossbar level.
SIZE_TOL = 0.003
PLUMB_MAX_DEG = 0.10
LEVEL_TOL = 0.001
# Sag: the back panel's deepest cord below the chord from crossbar rope to
# back-bar rope, in a 0.2 m strip down the middle.
SAG_STRIP = 0.10
SAG_MIN = 0.110
SAG_MAX = 0.180

HERO_YAW_DEG = 12.0
WALL_Y = 6.0

PAINT_IDX = 0
CORD_IDX = 1
ROPE_IDX = 2
STEEL_IDX = 3
CAST_IDX = 4
NYLON_IDX = 5
GALV_IDX = 6
TURF_IDX = 7
CHALK_IDX = 8
SOIL_IDX = 9

XAX = Vector((1.0, 0.0, 0.0))
YAX = Vector((0.0, 1.0, 0.0))
ZAX = Vector((0.0, 0.0, 1.0))


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


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

def _mark(faces, mat_idx):
    for f in faces:
        f.material_index = mat_idx


def frame(ez, ex_hint):
    """Rotation whose local Z is ``ez`` and local X is ``ex_hint`` made
    orthogonal to it (columns ex, ey, ez; right-handed)."""
    ez = Vector(ez).normalized()
    ex = Vector(ex_hint)
    ex = (ex - ez * ex.dot(ez)).normalized()
    ey = ez.cross(ex)
    return Matrix((ex, ey, ez)).transposed()


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None, phase=0.0):
    """Revolve an open profile [(r, z), ...] about local Z, closed by n-gon
    caps at its two ends."""
    c = Vector(center)
    m = rot if rot is not None else Matrix.Identity(3)
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new(c + m @ Vector((r * ca, r * sa, z))) for r, z in profile])
    n = len(profile)
    faces = []
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for j in range(n - 1):
            faces.append(bm.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1])))
    faces.append(bm.faces.new([rings[i][0] for i in reversed(range(segs))]))
    faces.append(bm.faces.new([rings[i][n - 1] for i in range(segs)]))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_tube(bm, pts, radius, sides, mat_idx, phase=0.0):
    """Capped round bar swept along a polyline (parallel-transport frames)."""
    pts = [Vector(p) for p in pts]
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    ref = Vector((0.0, 0.0, 1.0)) if abs(tans[0].z) < 0.9 else Vector((1.0, 0.0, 0.0))
    nrm = (ref - tans[0] * ref.dot(tans[0])).normalized()
    rings = []
    for p, t in zip(pts, tans):
        nrm = (nrm - t * nrm.dot(t)).normalized()
        bi = t.cross(nrm)
        rings.append([
            bm.verts.new(p + radius * (nrm * math.cos(phase + 2.0 * math.pi * k / sides)
                                       + bi * math.sin(phase + 2.0 * math.pi * k / sides)))
            for k in range(sides)
        ])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_ring(bm, center, axis, r_major, r_minor, segs, sides, mat_idx, phase=0.0):
    """Closed torus about ``axis`` through ``center``."""
    center = Vector(center)
    axis = Vector(axis).normalized()
    ref = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    u = axis.cross(ref).normalized()
    w = axis.cross(u)
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        radial = u * math.cos(a) + w * math.sin(a)
        c = center + radial * r_major
        rings.append([
            bm.verts.new(c + r_minor * (radial * math.cos(2.0 * math.pi * (k + 0.5) / sides)
                                        + axis * math.sin(2.0 * math.pi * (k + 0.5) / sides)))
            for k in range(sides)
        ])
    faces = []
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for k in range(sides):
            m = (k + 1) % sides
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def rrect(ha, hb, rc, n_corner=4):
    """Rounded rectangle loop (counter-clockwise)."""
    rc = max(min(rc, ha - 1e-4, hb - 1e-4), 0.0006)
    pts = []
    for k, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        cx, cy = sx * (ha - rc), sy * (hb - rc)
        a0 = 0.5 * math.pi * k
        for s in range(n_corner + 1):
            a = a0 + 0.5 * math.pi * s / n_corner
            pts.append((cx + rc * math.cos(a), cy + rc * math.sin(a)))
    return pts


def add_rbox(bm, ha, hb, rc, profile, origin, rot, mat_idx, n_corner=4):
    """Loft of rounded rectangles along local Z: profile [(inset, z)], each
    loop inset from (ha, hb, rc); n-gon caps at both ends."""
    o = Vector(origin)
    rings = []
    for inset, z in profile:
        loop = rrect(ha - inset, hb - inset, rc - inset, n_corner)
        rings.append([bm.verts.new(o + rot @ Vector((x, y, z))) for x, y in loop])
    n = len(rings[0])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_loft(bm, loops, mat_idx):
    """Loft closed loops of world points (equal counts), capped."""
    rings = [[bm.verts.new(Vector(p)) for p in loop] for loop in loops]
    n = len(rings[0])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def superellipse(ha, hb, p, n, phase=0.0):
    pts = []
    for i in range(n):
        t = phase + 2.0 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        pts.append((ha * math.copysign(abs(c) ** (2.0 / p), c),
                    hb * math.copysign(abs(s) ** (2.0 / p), s)))
    return pts


def frame_section():
    """The extrusion's section (a in the frame's plane, positive toward the
    mouth; b front to back, positive to the rear), counter-clockwise, with
    the net channel notched into the back."""
    ts = math.acos((SLOT_HW / POST_HA) ** (SEC_P / 2.0))
    t0, t1 = math.pi - ts, 2.0 * math.pi + ts
    pts = []
    for i in range(SEC_N + 1):
        t = t0 + (t1 - t0) * i / SEC_N
        c, s = math.cos(t), math.sin(t)
        pts.append((POST_HA * math.copysign(abs(c) ** (2.0 / SEC_P), c),
                    POST_HB * math.copysign(abs(s) ** (2.0 / SEC_P), s)))
    b_s = pts[-1][1]
    pts += [(SLOT_HW, b_s - SLOT_D), (-SLOT_HW, b_s - SLOT_D)]
    return pts


def triangulate_ngons(bm):
    faces = [f for f in bm.faces if len(f.verts) > 4]
    if faces:
        bmesh.ops.triangulate(bm, faces=faces)


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
        ax, ay, az = abs(nrm.x), abs(nrm.y), abs(nrm.z)
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


def spaced(length, pitch, m0, m1):
    """Stations along a run of ``length``, ``m0``/``m1`` in from its ends,
    about ``pitch`` apart."""
    span = length - m0 - m1
    n = max(1, int(round(span / pitch)))
    return [m0 + span * i / n for i in range(n + 1)]


# --------------------------------------------------------------------------
# Layout, solved from the named constants
# --------------------------------------------------------------------------

def rope_offset(h):
    """Member axis to head-rope axis: the member's half-depth, the saddle
    (less its bite), and the loop standing on it (less its bite)."""
    return h - SADDLE_BITE + SADDLE_T + HOOK_R + HOOK_MINOR - HOOK_BITE


def layout(wide_mouth=False):
    L = {}
    w = MOUTH_W + (WIDE_MOUTH if wide_mouth else 0.0)
    x0 = 0.5 * w + POST_HA                  # post axis
    zc = TURF_T + MOUTH_H + POST_HA         # crossbar axis
    zg = TURF_T + BAR_R - BAR_BITE          # ground-bar axis
    yr = rope_offset(POST_HB)               # rope behind the posts and crossbar
    zb = zg + rope_offset(BAR_R)            # rope over the ground bars
    L.update(x0=x0, zc=zc, zg=zg, yr=yr, zb=zb)
    # Net corners (right side; the left mirrors in X)
    L["A"] = Vector((x0, yr, zc))           # top front: crossbar, post and support ropes
    L["C"] = Vector((x0, yr, zb))           # bottom front: post and side-bar ropes
    L["B"] = Vector((x0, DEPTH, zb))        # bottom rear: support, side-bar and back ropes
    s = (L["B"] - L["A"]).normalized()      # support direction, down and back
    n_s = Vector((0.0, -s.z, s.y))          # perpendicular in the side plane
    if n_s.z > 0.0:
        n_s = -n_s                          # toward the net: down and forward
    L["s"], L["n_s"] = s, n_s
    off_s = rope_offset(SUPPORT_R)
    L["off_s"] = off_s
    # support axis: the rope line moved off the net side
    L["F"] = L["A"] - n_s * off_s           # top end, in the corner bracket
    base = L["B"] - n_s * off_s
    lam = (base.z - (TURF_T + 0.030)) / -s.z
    L["E"] = base + s * lam                 # bottom end, in the corner hub
    return L


def mirror(p, sx):
    return Vector((sx * p.x, p.y, p.z))


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------

def add_turf(bm):
    """Turf slab: a gridded top (goal-line strip painted), a rolled edge, and
    cut soil walls down to the ground."""
    xs = [-TURF_X + 2.0 * TURF_X * i / 16 for i in range(17)]
    ys = sorted({TURF_Y0, -LINE_HALF, LINE_HALF, TURF_Y1}
                | {TURF_Y0 + (-LINE_HALF - TURF_Y0) * i / 3 for i in range(1, 3)}
                | {LINE_HALF + (TURF_Y1 - LINE_HALF) * i / 6 for i in range(1, 6)})
    grid = [[bm.verts.new((x, y, TURF_T)) for x in xs] for y in ys]
    faces = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            f = bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            yc = 0.5 * (ys[j] + ys[j + 1])
            f.material_index = CHALK_IDX if abs(yc) < LINE_HALF else TURF_IDX
            faces.append(f)
    nx, ny = len(xs), len(ys)
    border = ([grid[0][i] for i in range(nx)] + [grid[j][nx - 1] for j in range(1, ny)]
              + [grid[ny - 1][i] for i in reversed(range(nx - 1))]
              + [grid[j][0] for j in reversed(range(1, ny - 1))])

    def outward(v):
        d = Vector((0.0, 0.0, 0.0))
        if abs(v.co.x - xs[0]) < 1e-6:
            d.x -= 1.0
        if abs(v.co.x - xs[-1]) < 1e-6:
            d.x += 1.0
        if abs(v.co.y - ys[0]) < 1e-6:
            d.y -= 1.0
        if abs(v.co.y - ys[-1]) < 1e-6:
            d.y += 1.0
        return d

    edge = [bm.verts.new(v.co + outward(v) * TURF_EDGE - ZAX * TURF_EDGE) for v in border]
    foot = [bm.verts.new(Vector((e.co.x, e.co.y, 0.0))) for e in edge]
    n = len(border)
    for k in range(n):
        m = (k + 1) % n
        f = bm.faces.new((border[k], edge[k], edge[m], border[m]))
        f.material_index = TURF_IDX
        f = bm.faces.new((edge[k], foot[k], foot[m], edge[m]))
        f.material_index = SOIL_IDX
    f = bm.faces.new(tuple(foot))
    f.material_index = SOIL_IDX


def add_frame(bm, L, bevel_verts):
    """Posts and crossbar: one extrusion with mitred top corners."""
    sec = frame_section()
    x0, zc = L["x0"], L["zc"]
    zb = TURF_T + POST_FOOT
    stations = []
    n_up = max(2, math.ceil((zc - zb) / POST_STEP))
    for i in range(n_up):
        stations.append((Vector((-x0, 0.0, zb + (zc - zb) * i / n_up)), XAX, 1.0))
    # a mitre ring: the section spread along the corner's bisector by sqrt 2
    stations.append((Vector((-x0, 0.0, zc)), (XAX - ZAX).normalized(), math.sqrt(2.0)))
    n_x = max(2, math.ceil(2.0 * x0 / BAR_STEP))
    for i in range(1, n_x):
        stations.append((Vector((-x0 + 2.0 * x0 * i / n_x, 0.0, zc)), -ZAX, 1.0))
    stations.append((Vector((x0, 0.0, zc)), (-ZAX - XAX).normalized(), math.sqrt(2.0)))
    for i in range(1, n_up + 1):
        stations.append((Vector((x0, 0.0, zc - (zc - zb) * i / n_up)), -XAX, 1.0))
    rings = [[bm.verts.new(p + da * (a * sc) + YAX * b) for a, b in sec]
             for p, da, sc in stations]
    n = len(sec)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, PAINT_IDX)
    bevel_verts.extend(v for ring in rings for v in ring)
    # weld bead round the outside of each mitre (the bracket hides the back)
    for idx in (n_up, n_up + n_x):
        p, da, sc = stations[idx]
        arc = [p + da * (a * sc) + YAX * b for a, b in sec[:SEC_N + 1]]
        add_tube(bm, arc, BEAD_R, 6, PAINT_IDX, phase=0.3)


def add_clip(bm, axis_pt, a, n, h, spin=0.0):
    """A nylon clip on a member: saddle on the member's net side, loop
    standing off it; returns the loop centre (the head rope's axis)."""
    a = a.normalized()
    n = n.normalized()
    rot = frame(n, a)
    base = axis_pt + n * (h - SADDLE_BITE)
    prof = [(0.0015, 0.0), (0.0, 0.0015), (0.0, SADDLE_T - 0.0015), (0.0015, SADDLE_T)]
    add_rbox(bm, SADDLE_HL, SADDLE_HW, 0.004, prof, base, rot, NYLON_IDX, n_corner=1)
    c = base + n * (SADDLE_T + HOOK_R + HOOK_MINOR - HOOK_BITE)
    add_ring(bm, c, a, HOOK_R, HOOK_MINOR, 8, 4, NYLON_IDX, phase=spin)
    return c


def add_bracket(bm, L, sx, bevel_verts):
    """Cast corner bracket behind the mitre, carrying the support socket."""
    x0, zc = L["x0"], L["zc"]
    prof = [(0.004, 0.0), (0.0, 0.004), (0.0, 0.074), (0.004, 0.078)]
    bevel_verts += add_rbox(bm, 0.045, 0.047, 0.012, prof, (sx * x0, 0.052, zc - 0.002),
                            frame(YAX, XAX), CAST_IDX, n_corner=3)
    s = L["s"]
    f = mirror(L["F"], sx)
    boss = [(0.030, 0.0), (0.030, 0.074), (0.027, 0.080)]
    bevel_verts += add_lathe(bm, boss, 20, CAST_IDX, center=f - s * 0.005,
                             rot=frame(s, XAX), phase=0.08)
    # two bolts through the bracket's inboard face
    # set 1.5 mm apart in depth, or their heads share a cap plane
    for dz, dy, bite in ((0.024, 0.092, 0.002), (-0.026, 0.088, 0.0035)):
        head = [(0.0085, 0.0), (0.0085, 0.0055), (0.0068, 0.0068)]
        c = Vector((sx * (x0 - 0.045 + bite), dy, zc + dz))
        add_lathe(bm, head, 6, GALV_IDX, center=c, rot=frame(-sx * XAX, YAX), phase=0.2)


def add_foot(bm, L, sx, bevel_verts):
    """Cast foot connector: plate, collar round the post, bar socket."""
    x0, zg = L["x0"], L["zg"]
    prof = [(0.0, -0.003), (0.0, 0.009), (0.003, 0.012)]
    bevel_verts += add_rbox(bm, 0.070, 0.110, 0.022, prof, (sx * x0, 0.035, TURF_T),
                            Matrix.Identity(3), CAST_IDX, n_corner=3)
    loops = []
    for inset, z in ((0.0, TURF_T + 0.008), (0.0, TURF_T + 0.144), (0.004, TURF_T + 0.150)):
        loops.append([Vector((sx * x0 + a, b, z)) for a, b in
                      superellipse(POST_HA + 0.008 - inset, POST_HB + 0.008 - inset, SEC_P, 40,
                                   phase=0.04)])
    bevel_verts += add_loft(bm, loops, CAST_IDX)
    boss = [(0.027, 0.0), (0.027, 0.112), (0.024, 0.118)]
    bevel_verts += add_lathe(bm, boss, 20, CAST_IDX, center=(sx * x0, 0.032, zg),
                             rot=frame(YAX, XAX), phase=0.05)
    # clamp bolt through the collar's outboard side
    head = [(0.0085, 0.0), (0.0085, 0.0055), (0.0068, 0.0068)]
    add_lathe(bm, head, 6, GALV_IDX, center=(sx * (x0 + POST_HA + 0.004), 0.0, TURF_T + 0.095),
              rot=frame(sx * XAX, YAX), phase=0.1)
    add_spike(bm, Vector((sx * (x0 + 0.050), 0.105, TURF_T + 0.012)))


def add_spike(bm, top):
    """Ground spike: domed head on the part, shank into the turf."""
    head = [(0.0130, 0.0), (0.0130, 0.0035), (0.0095, 0.0060), (0.0040, 0.0070)]
    add_lathe(bm, head, 16, GALV_IDX, center=top - ZAX * 0.001, phase=0.11)
    shank = [(0.0045, -(top.z - 0.012)), (0.0045, 0.002)]
    add_lathe(bm, shank, 8, GALV_IDX, center=top - ZAX * 0.001, phase=0.2)


def add_hub(bm, L, sx, bevel_verts):
    """Cast rear corner hub: block, three sockets, a spike."""
    x0, zg = L["x0"], L["zg"]
    prof = [(0.0, -0.004), (0.0, 0.050), (0.005, 0.055)]
    bevel_verts += add_rbox(bm, 0.065, 0.072, 0.016, prof,
                            (sx * (x0 + 0.015), DEPTH + 0.020, TURF_T),
                            Matrix.Identity(3), CAST_IDX, n_corner=3)
    s = L["s"]
    e = mirror(L["E"], sx)
    boss = [(0.030, 0.0), (0.030, 0.070), (0.027, 0.076)]
    bevel_verts += add_lathe(bm, boss, 20, CAST_IDX, center=e + s * 0.006,
                             rot=frame(-s, XAX), phase=0.07)
    bb = [(0.027, 0.0), (0.027, 0.070), (0.024, 0.076)]
    bevel_verts += add_lathe(bm, bb, 20, CAST_IDX, center=(sx * x0, DEPTH - 0.030, zg),
                             rot=frame(-YAX, XAX), phase=0.06)
    bevel_verts += add_lathe(bm, bb, 20, CAST_IDX, center=(sx * (x0 - 0.030), DEPTH, zg),
                             rot=frame(-sx * XAX, YAX), phase=0.09)
    add_spike(bm, Vector((sx * (x0 + 0.055), DEPTH + 0.020, TURF_T + 0.055)))


def add_staple(bm, axis_pt, a, r_host):
    """Galvanised U-staple over a ground bar, legs into the turf."""
    a = a.normalized()
    side = ZAX.cross(a).normalized()
    rr = r_host + 0.0045 - 0.0008
    pts = [axis_pt + side * rr + ZAX * (TURF_T - 0.030 - axis_pt.z)]
    pts.append(axis_pt + side * rr)
    for k in range(1, 12):
        t = math.pi * k / 12
        pts.append(axis_pt + side * (rr * math.cos(t)) + ZAX * (rr * math.sin(t)))
    pts.append(axis_pt - side * rr)
    pts.append(axis_pt - side * rr + ZAX * (TURF_T - 0.030 - axis_pt.z))
    add_tube(bm, pts, 0.0045, 8, GALV_IDX, phase=0.2)


def sag_c(t):
    k = SAG_K
    return (math.cosh(0.5 * k) - math.cosh(k * (t - 0.5))) / (math.cosh(0.5 * k) - 1.0)


def clip_line(p0, d, poly):
    """Parameter interval of the line p0 + lam d inside a convex CCW polygon."""
    lo, hi = -1e9, 1e9
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        nx_, ny_ = -(by - ay), bx - ax              # inward normal (CCW)
        num = nx_ * (p0[0] - ax) + ny_ * (p0[1] - ay)
        den = nx_ * d[0] + ny_ * d[1]
        if abs(den) < 1e-12:
            if num < 0.0:
                return None
            continue
        lam = -num / den
        if den > 0.0:
            lo = max(lo, lam)
        else:
            hi = min(hi, lam)
    return (lo, hi) if hi - lo > 1e-9 else None


def diamond_strands(poly):
    """Strands of a diamond mesh over a convex (s, t) domain: two families at
    +-45 degrees, sampled at every knot and at both ends."""
    step = MESH * math.sqrt(2.0)
    r2 = 1.0 / math.sqrt(2.0)
    fams = (((r2, -r2), 1.0), ((r2, r2), -1.0))     # s + t = c, s - t = c
    cs = {}
    for f, (_d, sg) in enumerate(fams):
        vals = [p[0] + sg * p[1] for p in poly]
        k0 = math.floor(min(vals) / step - 0.5)
        k1 = math.ceil(max(vals) / step + 0.5)
        cs[f] = [(k + 0.5) * step for k in range(k0, k1 + 1)
                 if min(vals) + 0.02 < (k + 0.5) * step < max(vals) - 0.02]
    out = []
    for f, (d, sg) in enumerate(fams):
        for c in cs[f]:
            p0 = (0.5 * c, 0.5 * c * sg)
            iv = clip_line(p0, d, poly)
            if iv is None or iv[1] - iv[0] < 0.04:
                continue
            lo, hi = iv
            lams = [lo]
            for c2 in cs[1 - f]:
                # knot with the other family's line
                if f == 0:
                    s_, t_ = 0.5 * (c + c2), 0.5 * (c - c2)
                else:
                    s_, t_ = 0.5 * (c2 + c), 0.5 * (c2 - c)
                lam = (s_ - p0[0]) * d[0] + (t_ - p0[1]) * d[1]
                if lo + 0.012 < lam < hi - 0.012:
                    lams.append(lam)
            lams.append(hi)
            lams.sort()
            out.append((f, [(p0[0] + lam * d[0], p0[1] + lam * d[1]) for lam in lams]))
    return out


def add_net(bm, L, taut):
    sag = 0.0 if taut else SAG
    A, B, C = L["A"], L["B"], L["C"]
    Am, Bm = mirror(A, -1), mirror(B, -1)
    # back panel: bilinear between the four rope corners, sagging in -Z
    lu = (B - Bm).length
    lv = (Am - Bm).length
    e_u = (B - Bm) / lu
    e_v = (Am - Bm) / lv
    nb = e_u.cross(e_v).normalized()
    poly = [(0.0, 0.0), (lu, 0.0), (lu, lv), (0.0, lv)]
    for f, pts in diamond_strands(poly):
        lift = (1.0 if f == 0 else -1.0) * CORD_LIFT * CORD_R
        path = []
        for s_, t_ in pts:
            u, v = s_ / lu, t_ / lv
            p = Bm + e_u * s_ + e_v * t_ + nb * lift
            p.z -= sag * sag_c(u) * sag_c(v)
            path.append(p)
        add_tube(bm, path, CORD_R, CORD_SIDES, CORD_IDX, phase=0.25 * math.pi)
    # side panels: right triangle C (front bottom), B (rear bottom), A (top)
    ls = B.y - C.y
    lt = A.z - C.z
    tri = [(0.0, 0.0), (ls, 0.0), (0.0, lt)]
    for sx in (-1.0, 1.0):
        for f, pts in diamond_strands(tri):
            lift = (1.0 if f == 0 else -1.0) * CORD_LIFT * CORD_R
            path = []
            for s_, t_ in pts:
                lb, la = s_ / ls, t_ / lt
                bub = 27.0 * lb * la * max(0.0, 1.0 - lb - la)
                path.append(Vector((sx * (C.x + SIDE_BULGE * bub + lift), C.y + s_,
                                    C.z + t_ - SIDE_DROOP * bub)))
            add_tube(bm, path, CORD_R, CORD_SIDES, CORD_IDX, phase=0.25 * math.pi)


def build_goal_mesh(name, bevel_offset, bevel_segments, wide_mouth=False, taut_net=False,
                    unclip_net=False, float_bar=False, short_support=False):
    L = layout(wide_mouth)
    x0, zc, zg = L["x0"], L["zc"], L["zg"]
    A, B, C = L["A"], L["B"], L["C"]
    s, n_s = L["s"], L["n_s"]
    bm = bmesh.new()
    try:
        bevel_verts = []
        add_turf(bm)
        add_frame(bm, L, bevel_verts)
        for sx in (-1.0, 1.0):
            add_bracket(bm, L, sx, bevel_verts)
            add_foot(bm, L, sx, bevel_verts)
            add_hub(bm, L, sx, bevel_verts)
            # sloped rear support
            # the tube starts 5 mm up its own axis past F: F is the rope's
            # corner moved square off it, so a cap at F shares the rope cap's plane
            f, e = mirror(L["F"], sx) - s * SUPPORT_TOP, mirror(L["E"], sx)
            if short_support and sx < 0.0:
                e = e - s * SHORT_SUPPORT
            bevel_verts += add_tube(bm, [f, e], SUPPORT_R, TUBE_SIDES, STEEL_IDX)
            # side ground bar
            bevel_verts += add_tube(bm, [Vector((sx * x0, 0.070, zg)), Vector((sx * x0, DEPTH, zg))],
                                    BAR_R, TUBE_SIDES, STEEL_IDX)
        back = add_tube(bm, [Vector((-(x0 - 0.005), DEPTH, zg)), Vector((x0 - 0.005, DEPTH, zg))],
                        BAR_R, TUBE_SIDES, STEEL_IDX)
        bevel_verts += back
        if float_bar:
            for v in back:
                v.co.z += FLOAT_BAR

        # head ropes and their clips: (start, end, member offset dir, member
        # half-depth, extend at start, extend at end)
        runs = []
        top = [mirror(A, -1), A]
        runs.append(("crossbar", top[0], top[1], YAX, POST_HB, 0.12, 0.12, 0.0, 0.0))
        for sx in (-1.0, 1.0):
            a_, b_, c_ = mirror(A, sx), mirror(B, sx), mirror(C, sx)
            runs.append(("post", c_, a_, YAX, POST_HB, 0.20, 0.12, 0.012, 0.0))
            runs.append(("support", a_, b_, n_s, SUPPORT_R, 0.20, 0.26, 0.0, 0.006))
            runs.append(("side", c_, b_, ZAX, BAR_R, 0.22, 0.22, 0.006, 0.006))
        runs.append(("back", mirror(B, -1), B, ZAX, BAR_R, 0.22, 0.22, 0.006, 0.006))
        staples = []
        for k, (kind, p0, p1, n, h, m0, m1, x_a, x_b) in enumerate(runs):
            d = (p1 - p0)
            length = d.length
            d = d / length
            ya = p0 - d * x_a
            yb = p1 + d * x_b
            if unclip_net and kind == "crossbar":
                ya = ya - ZAX * UNCLIP
                yb = yb - ZAX * UNCLIP
            add_tube(bm, [ya, yb], ROPE_R, ROPE_SIDES, ROPE_IDX, phase=0.1 + 0.07 * k)
            off = rope_offset(h)
            st = spaced(length, CLIP_PITCH, m0, m1)
            for j, t in enumerate(st):
                c = p0 + d * t
                add_clip(bm, c - n * off, d, n, h, spin=0.05 * ((k + j) % 3))
            if kind in ("side", "back"):
                # staples between the two middle clips
                mid = len(st) // 2
                t = 0.5 * (st[mid - 1] + st[mid]) if len(st) > 1 else 0.5 * length
                if kind == "back":
                    for tt in (0.5 * (st[1] + st[2]), 0.5 * (st[-2] + st[-3])):
                        staples.append((p0 + d * tt - n * off, d, BAR_R))
                else:
                    staples.append((p0 + d * t - n * off, d, BAR_R))
        for pt, a_, r_ in staples:
            add_staple(bm, pt, a_, r_)
        add_net(bm, L, taut_net)

        if bevel_offset > 0.0:
            # Chamfer the frame, castings and tube ends: one pass per
            # material with material= set, over sorted edges.
            for mat_idx in (PAINT_IDX, CAST_IDX, STEEL_IDX):
                bm.edges.index_update()
                edges = sorted(
                    {e for v in bevel_verts if v.is_valid for e in v.link_edges
                     if len(e.link_faces) == 2
                     and all(f.material_index == mat_idx for f in e.link_faces)
                     and e.calc_face_angle() > math.radians(60.0)},
                    key=lambda e: e.index,
                )
                if edges:
                    bmesh.ops.bevel(bm, geom=edges, offset=bevel_offset,
                                    segments=bevel_segments, profile=0.5, affect="EDGES",
                                    clamp_overlap=True, material=mat_idx)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z -= zmin
            if v.co.z < 0.0:
                v.co.z = 0.0

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # Extrusion, tubes, cords and castings smooth; chamfers, the mitre
        # and the channel crisp through sharp edges; the cords and ropes
        # are round, so their four- and eight-sided sections stay smooth.
        soft = {CORD_IDX, ROPE_IDX, NYLON_IDX}
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            elif mats <= soft:
                edge.smooth = edge.calc_face_angle() < math.radians(95.0)
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(35.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def principled(name, color, metallic, roughness, roughness_var=0.0, mottle=0.0,
               noise_scale=14.0, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if coat > 0.0 and "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.08
    if roughness_var > 0.0 or mottle > 0.0:
        coord = nt.nodes.new("ShaderNodeTexCoord")
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = noise_scale
        noise.inputs["Detail"].default_value = 6.0
        nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
        if roughness_var > 0.0:
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            lo = max(0.03, roughness - roughness_var)
            hi = min(0.95, roughness + roughness_var)
            ramp.color_ramp.elements[0].position = 0.30
            ramp.color_ramp.elements[0].color = (lo, lo, lo, 1.0)
            ramp.color_ramp.elements[1].position = 0.70
            ramp.color_ramp.elements[1].color = (hi, hi, hi, 1.0)
            nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
        if mottle > 0.0:
            cramp = nt.nodes.new("ShaderNodeValToRGB")
            dark = tuple(c * (1.0 - mottle) for c in color[:3]) + (1.0,)
            cramp.color_ramp.elements[0].position = 0.35
            cramp.color_ramp.elements[0].color = dark
            cramp.color_ramp.elements[1].position = 0.75
            cramp.color_ramp.elements[1].color = color
            nt.links.new(noise.outputs["Fac"], cramp.inputs["Fac"])
            nt.links.new(cramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def turf_material():
    """Mown turf: bands parallel to the goal line, light and dark, with a
    fine blade mottle and a bump."""
    mat = bpy.data.materials.new("GoalTurf")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.88
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
    band = nt.nodes.new("ShaderNodeMath")
    band.operation = "SINE"
    scale = nt.nodes.new("ShaderNodeMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = math.pi / 0.9
    nt.links.new(sep.outputs["Y"], scale.inputs[0])
    nt.links.new(scale.outputs["Value"], band.inputs[0])
    stripe = nt.nodes.new("ShaderNodeMapRange")
    stripe.inputs["From Min"].default_value = -0.15
    stripe.inputs["From Max"].default_value = 0.15
    nt.links.new(band.outputs["Value"], stripe.inputs["Value"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 90.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.020, 0.075, 0.014, 1.0)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.055, 0.170, 0.030, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    # the lighter mown band: the same grass scaled up
    light = nt.nodes.new("ShaderNodeMix")
    light.data_type = "RGBA"
    light.blend_type = "MULTIPLY"
    light.inputs[0].default_value = 1.0
    nt.links.new(ramp.outputs["Color"], light.inputs[6])
    light.inputs[7].default_value = (1.45, 1.40, 1.30, 1.0)
    # stripe = 0: plain band; stripe = 1: mown band
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MIX"
    nt.links.new(stripe.outputs["Result"], mix.inputs[0])
    nt.links.new(ramp.outputs["Color"], mix.inputs[6])
    nt.links.new(light.outputs[2], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.004
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def goal_materials():
    """(paint, cord, rope, steel, cast, nylon, galv, turf, chalk, soil):
    shared by the check and the render."""
    paint = principled("GoalPaint", (0.80, 0.80, 0.78, 1.0), 0.0, 0.30,
                       roughness_var=0.05, mottle=0.03, noise_scale=12.0, coat=0.35)
    cord = principled("GoalNetCord", (0.70, 0.70, 0.67, 1.0), 0.0, 0.70,
                      roughness_var=0.06, mottle=0.08, noise_scale=40.0)
    rope = principled("GoalHeadRope", (0.52, 0.035, 0.028, 1.0), 0.0, 0.62,
                      roughness_var=0.08, mottle=0.18, noise_scale=220.0)
    steel = principled("GoalSteel", (0.032, 0.036, 0.040, 1.0), 0.55, 0.48,
                       roughness_var=0.08, mottle=0.12, noise_scale=30.0)
    cast = principled("GoalCastAlu", (0.58, 0.59, 0.60, 1.0), 1.0, 0.40,
                      roughness_var=0.10, mottle=0.12, noise_scale=120.0)
    nylon = principled("GoalNylonClip", (0.020, 0.020, 0.022, 1.0), 0.0, 0.45,
                       roughness_var=0.05, noise_scale=80.0)
    galv = principled("GoalGalv", (0.50, 0.51, 0.53, 1.0), 1.0, 0.32,
                      roughness_var=0.12, mottle=0.15, noise_scale=150.0)
    turf = turf_material()
    chalk = principled("GoalLinePaint", (0.86, 0.86, 0.83, 1.0), 0.0, 0.92,
                       roughness_var=0.04, mottle=0.10, noise_scale=60.0)
    soil = principled("GoalSoil", (0.095, 0.060, 0.035, 1.0), 0.0, 0.95,
                      mottle=0.35, noise_scale=45.0)
    return paint, cord, rope, steel, cast, nylon, galv, turf, chalk, soil


def assign_slots(obj, wanted):
    # Do not materials.clear() — that resets polygon material_index to 0.
    mats = obj.data.materials
    for i, mat in enumerate(wanted):
        if i < len(mats):
            mats[i] = mat
        else:
            mats.append(mat)


# --------------------------------------------------------------------------
# Audits
# --------------------------------------------------------------------------

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
    aabbs.sort()
    overlap = 0.0
    for i, a in enumerate(aabbs):
        for j in range(i + 1, len(aabbs)):
            b = aabbs[j]
            if b[0] >= a[2]:
                break
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
    return {"ngons": ngons, "loose_v": loose_v, "loose_e": loose_e, "nonman": nonman,
            "zero_area": zero_area, "doubles": doubles}


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
            cur = stack.pop()
            group.append(cur)
            for nxt in neighbors[cur]:
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(nxt)
        groups.append(group)
    return groups


def zfight_pairs(me, groups):
    """Coplanar face pairs from *different shells* (copied from showcase/grindstone)."""
    owner = {}
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    faces = [(p.normal.copy(), p.center.copy(), owner.get(p.vertices[0], -1))
             for p in me.polygons]
    kd = KDTree(len(faces))
    for i, (_n, c, _s) in enumerate(faces):
        kd.insert(c, i)
    kd.balance()
    hits = 0
    for i, (ni, ci, si) in enumerate(faces):
        for _co, j, _d in kd.find_range(ci, COPLANAR_CENTRE_MAX):
            if j <= i:
                continue
            nj, cj, sj = faces[j]
            if si == sj:
                continue
            if abs(abs(ni.dot(nj)) - 1.0) > COPLANAR_NORMAL_EPS:
                continue
            if abs(ni.dot(cj - ci)) > COPLANAR_PLANE_EPS:
                continue
            hits += 1
    return hits


def shell_polys(me, groups):
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(p)
    return polys


class Shell:
    def __init__(self, me, idx, verts, polys):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.centre = (self.lo + self.hi) * 0.5
        self.mean = sum(pts, Vector()) / len(pts)
        mats = {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        self.mats = set(mats)
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)
        self.polys = polys


def pca_axis(pts, largest=True):
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    _w, vecs = np.linalg.eigh(q.T @ q)
    axis = vecs[:, -1] if largest else vecs[:, 0]
    return Vector(c), Vector(axis).normalized()


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    turfs = [s for s in parts if TURF_IDX in s.mats]
    out["turf"] = max(turfs, key=lambda s: len(s.verts)) if turfs else None
    out["turf_top"] = max(p.z for p in out["turf"].pts) if out["turf"] else 0.0
    paints = [s for s in parts if s.mat == PAINT_IDX]
    out["frame"] = max(paints, key=lambda s: len(s.verts)) if paints else None
    steel = [s for s in parts if s.mat == STEEL_IDX]
    out["bars"] = [s for s in steel if s.hi.z < out["turf_top"] + 0.10]
    out["supports"] = [s for s in steel if s.size.z > 1.0]
    out["casts"] = [s for s in parts if s.mat == CAST_IDX]
    nylon = [s for s in parts if s.mat == NYLON_IDX]
    out["hooks"] = [s for s in nylon if max(s.size) < 0.026]
    out["saddles"] = [s for s in nylon if max(s.size) >= 0.026]
    out["ropes"] = [s for s in parts if s.mat == ROPE_IDX]
    out["cords"] = [s for s in parts if s.mat == CORD_IDX]
    return out


def ground_audit(cls):
    """Every ground bar bedded into the turf top read off the turf."""
    top = cls["turf_top"]
    return [top - b.lo.z for b in cls["bars"]]


def _inside(tree, p):
    hit = tree.find_nearest(p)
    if hit[0] is None:
        return False
    loc, nrm, _i, _d = hit
    return (p - loc).dot(nrm) < 0.0


def support_audit(cls):
    """For each end of each support: how far the tube runs inside a cast
    socket, sampled round its own section at 5 mm stations."""
    res = []
    trees = [c.tree for c in cls["casts"]]
    for s in cls["supports"]:
        c, ax = pca_axis(s.pts)
        lams = [(p - c).dot(ax) for p in s.pts]
        rad = sum(((p - c) - ax * lam).length for p, lam in zip(s.pts, lams)) / len(lams)
        u = ax.orthogonal().normalized()
        w = ax.cross(u)
        ends = []
        for lam_end, sign in ((min(lams), 1.0), (max(lams), -1.0)):
            ins = 0.0
            k = 1
            while k * 0.005 < 0.25:
                st = lam_end + sign * k * 0.005
                q = c + ax * st
                ok = True
                for j in range(6):
                    a = 2.0 * math.pi * j / 6
                    p = q + (u * math.cos(a) + w * math.sin(a)) * (rad * 0.9)
                    if not any(_inside(t, p) for t in trees):
                        ok = False
                        break
                if not ok:
                    break
                ins = k * 0.005
                k += 1
            ends.append(ins)
        res.append(ends)
    return res


def clip_audit(cls):
    """Each clip loop's centre against the nearest head-rope axis; each
    loop on a saddle; each saddle on a member."""
    axes = [pca_axis(r.pts) for r in cls["ropes"]]
    worst = 0.0
    for h in cls["hooks"]:
        best = 9.0
        for c, ax in axes:
            d = h.mean - c
            best = min(best, (d - ax * d.dot(ax)).length)
        worst = max(worst, best)
    members = [cls["frame"]] + cls["bars"] + cls["supports"]
    members = [m for m in members if m is not None]
    loose_hooks = sum(1 for h in cls["hooks"]
                      if not any(h.tree.overlap(s.tree) for s in cls["saddles"]))
    loose_saddles = sum(1 for s in cls["saddles"]
                        if not any(s.tree.overlap(m.tree) for m in members))
    return {"hooks": len(cls["hooks"]), "saddles": len(cls["saddles"]),
            "ropes": len(cls["ropes"]), "seat": worst,
            "loose_hooks": loose_hooks, "loose_saddles": loose_saddles}


def mouth_audit(cls):
    """Clear opening from the inner post faces and the crossbar underside;
    each post's tilt from two slabs; the crossbar's level."""
    fr = cls["frame"]
    top = cls["turf_top"]
    res = {"width": 0.0, "height": 0.0, "tilt": [9.0, 9.0], "level": 9.0}
    if fr is None:
        return res
    z_lo, z_hi = top + 0.30, top + MOUTH_H - 0.30
    left = [p for p in fr.pts if p.x < 0.0 and z_lo < p.z < z_hi]
    right = [p for p in fr.pts if p.x > 0.0 and z_lo < p.z < z_hi]
    xmax = max(p.x for p in fr.pts)
    under = [p for p in fr.pts if abs(p.x) < xmax - 0.40]
    if not (left and right and under):
        return res
    res["width"] = min(p.x for p in right) - max(p.x for p in left)
    res["height"] = min(p.z for p in under) - top
    tilts = []
    for side in (left, right):
        lo = [p for p in fr.pts if (p.x < 0.0) == (side is left)
              and top + 0.25 < p.z < top + 0.50]
        hi = [p for p in fr.pts if (p.x < 0.0) == (side is left)
              and top + MOUTH_H - 0.50 < p.z < top + MOUTH_H - 0.25]
        if not lo or not hi:
            tilts.append(9.0)
            continue
        a = sum(lo, Vector()) / len(lo)
        b = sum(hi, Vector()) / len(hi)
        tilts.append(math.degrees(math.atan2(math.hypot(b.x - a.x, b.y - a.y), b.z - a.z)))
    res["tilt"] = tilts
    ul = [p.z for p in under if -xmax + 0.40 < p.x < -xmax + 0.90]
    ur = [p.z for p in under if xmax - 0.90 < p.x < xmax - 0.40]
    if ul and ur:
        res["level"] = abs(min(ul) - min(ur))
    return res


def sag_audit(cls):
    """Deepest back-panel cord below the chord from the crossbar rope to the
    back-bar rope, in a strip down the middle."""
    ropes = [r for r in cls["ropes"] if r.size.x > 4.0]
    if len(ropes) != 2:
        return {"sag": 0.0, "n": 0}
    hi_r = max(ropes, key=lambda r: r.mean.z)
    lo_r = min(ropes, key=lambda r: r.mean.z)
    y0, z0 = hi_r.mean.y, hi_r.mean.z
    y1, z1 = lo_r.mean.y, lo_r.mean.z
    sag = 0.0
    n = 0
    for c in cls["cords"]:
        if c.lo.x > SAG_STRIP or c.hi.x < -SAG_STRIP:
            continue
        for p in c.pts:
            if abs(p.x) < SAG_STRIP and y0 + 0.05 < p.y < y1 - 0.05:
                zc = z0 + (z1 - z0) * (p.y - y0) / (y1 - y0)
                sag = max(sag, zc - p.z)
                n += 1
    return {"sag": sag, "n": n}


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        # inside the envelope, so only the hygiene budget can see it
        bm.verts.new((0.0, 0.6, 1.0))
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
    # bmesh.ops.convex_hull can list the same element in geom_interior and
    # geom_unused; once deleted it is invalid and a second delete raises
    # ReferenceError. Filter on is_valid before each delete.
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        result = bmesh.ops.convex_hull(bm, input=list(bm.verts))
        interior = [g for g in result.get("geom_interior") or [] if g.is_valid]
        if interior:
            bmesh.ops.delete(bm, geom=interior, context="VERTS")
        unused = [g for g in result.get("geom_unused") or [] if g.is_valid]
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
    img = bpy.data.images.new("GoalNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = CAST_IDX
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
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_yup=True,
                              export_apply=True, export_draco_mesh_compression_enable=False,
                              export_animations=False)


def check(skip_decimate, lift_z=False, stray_vert=False, float_bar=False, short_support=False,
          unclip_net=False, wide_mouth=False, taut_net=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(wide_mouth=wide_mouth, taut_net=taut_net, unclip_net=unclip_net,
                 float_bar=float_bar, short_support=short_support)
    low = build_goal_mesh("GoalLow", bevel_offset=0.0015, bevel_segments=1, **flags)
    high = build_goal_mesh("GoalHigh", bevel_offset=0.0015, bevel_segments=3, **flags)
    mats = goal_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the castings: brackets, hubs and foot connectors are
    # where the high mesh's rounder chamfer differs from the low.
    target = mats[CAST_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("goal mesh did not build", 3),) + none3

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat = len(slots)
    distinct_mats = len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    print(f"measured mat_index_counts={dict(sorted(idx_counts.items()))}")
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]
    hyg = hygiene_audit(low.data)
    cls = classify(low.data)
    zf = zfight_pairs(low.data, cls["groups"])
    beds = ground_audit(cls)
    sup = support_audit(cls)
    clp = clip_audit(cls)
    mouth = mouth_audit(cls)
    sg = sag_audit(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("goal has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "GoalLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "GoalLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_goal_mesh("GoalColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "GoalCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_soccer_goal_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
          f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}")
    print(f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
          f"overlap={overlap:.6f} nfaces={nfaces}")
    print(f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
          f"outer={OUTER_SIZE} zmin={bb[2]:.4f} min=({bb[0]:.4f},{bb[1]:.4f})")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured shells={len(cls['all'])} turf_top={cls['turf_top']:.5f} "
          f"bars={len(beds)} beds={[round(b, 5) for b in beds]}")
    print(f"measured supports={len(sup)} insertion={[[round(e, 4) for e in s] for s in sup]}")
    print(f"measured clips hooks={clp['hooks']} saddles={clp['saddles']} ropes={clp['ropes']} "
          f"seat={clp['seat']:.6f} loose_hooks={clp['loose_hooks']} "
          f"loose_saddles={clp['loose_saddles']}")
    print(f"measured mouth width={mouth['width']:.5f} height={mouth['height']:.5f} "
          f"tilt={[round(t, 4) for t in mouth['tilt']]} level={mouth['level']:.6f}")
    print(f"measured sag={sg['sag']:.5f} samples={sg['n']} cords={len(cls['cords'])}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    floors = ((PAINT_IDX, PAINT_FACES_MIN, "paint"), (CORD_IDX, CORD_FACES_MIN, "cord"),
              (ROPE_IDX, ROPE_FACES_MIN, "rope"), (STEEL_IDX, STEEL_FACES_MIN, "steel"),
              (CAST_IDX, CAST_FACES_MIN, "cast"), (NYLON_IDX, NYLON_FACES_MIN, "nylon"),
              (GALV_IDX, GALV_FACES_MIN, "galv"), (TURF_IDX, TURF_FACES_MIN, "turf"),
              (CHALK_IDX, CHALK_FACES_MIN, "chalk"), (SOIL_IDX, SOIL_FACES_MIN, "soil"))
    for idx, floor, label in floors:
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{label} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + none3
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + none3
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + none3
    if (abs(size_x - OUTER_SIZE[0]) > BBOX_TOL or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
            or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL):
        return (fail(f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8),) + none3
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
                     "(--skip-decimate is the designed fail)", 9),) + none3
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9),) + none3
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + none3
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + none3
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + none3
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf}", 15),) + none3
    if bb[2] > ZMIN_EPS:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none3
    if len(beds) != BAR_COUNT or any(not (BED_MIN <= b <= BED_MAX) for b in beds):
        return (fail(f"ground frame: {len(beds)} bars (want {BAR_COUNT}), bedded "
                     f"{[round(b, 5) for b in beds]} (band [{BED_MIN}, {BED_MAX}] "
                     "into the turf top)", 16),) + none3
    if len(sup) != SUPPORT_COUNT or any(e < INSERT_MIN for s in sup for e in s):
        return (fail(f"supports: {len(sup)} (want {SUPPORT_COUNT}), socket insertion "
                     f"{[[round(e, 4) for e in s] for s in sup]} (each end >= {INSERT_MIN})",
                     17),) + none3
    if (clp["hooks"] != CLIP_COUNT or clp["saddles"] != CLIP_COUNT or clp["seat"] > SEAT_MAX
            or clp["loose_hooks"] or clp["loose_saddles"]):
        return (fail(f"clips: {clp} (want {CLIP_COUNT} clips, rope axis within {SEAT_MAX} "
                     "of every loop centre, every loop on a saddle, every saddle on a member)",
                     18),) + none3
    if (abs(mouth["width"] - MOUTH_W) > SIZE_TOL or abs(mouth["height"] - MOUTH_H) > SIZE_TOL
            or max(mouth["tilt"]) > PLUMB_MAX_DEG or mouth["level"] > LEVEL_TOL):
        return (fail(f"mouth: {mouth} (want {MOUTH_W} x {MOUTH_H} m +- {SIZE_TOL}, posts "
                     f"plumb within {PLUMB_MAX_DEG} deg, crossbar level within {LEVEL_TOL})",
                     19),) + none3
    if not (SAG_MIN <= sg["sag"] <= SAG_MAX):
        return (fail(f"net sag {sg['sag']:.4f} not in [{SAG_MIN}, {SAG_MAX}]", 20),) + none3
    return 0, low, target, tex


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, target, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(target, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(HERO_YAW_DEG)
    bpy.context.view_layer.update()
    bb = world_bbox(low)
    centre = Vector((0.5 * (bb[0] + bb[3]), 0.5 * (bb[1] + bb[4]), 0.5 * (bb[2] + bb[5])))

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
    wall.location = (0.0, centre.y + WALL_Y, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

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

    # The house rig scaled to a 6 m prop: warm key upper left, cool fill low
    # right, cool rim behind to trace the net, warm wedge pooled on the wall.
    light("Key", (-9.0, -11.0, 9.0), 620.0, 3.0, (1.0, 0.95, 0.90), spread=11.0)
    light("Fill", (12.0, -8.0, 2.0), 20.0, 16.0, (0.72, 0.82, 1.0))
    light("Rim", (-4.0, 6.0, 5.0), 320.0, 4.0, (0.62, 0.78, 1.0))
    light("Wedge", (8.0, 3.5, 5.0), 1500.0, 6.0, (1.0, 0.68, 0.38),
          target=(centre.x + 4.0, centre.y + WALL_Y - 0.8, 0.4))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.50, -0.87, 0.0)).normalized()
    cam.location = centre + view * 10.4 + Vector((0.0, 0.0, 2.5))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((-0.12, 0.07, -0.55))
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
    scene.render.image_settings.file_format = "WEBP" if path.lower().endswith(".webp") else "PNG"
    if path.lower().endswith(".webp"):
        scene.render.image_settings.quality = 90
    scene.render.filepath = path
    # Standard, not AgX: AgX washes the red head rope and the turf toward pastel
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 21
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
    p.add_argument("--float-bar", action="store_true")
    p.add_argument("--short-support", action="store_true")
    p.add_argument("--unclip-net", action="store_true")
    p.add_argument("--wide-mouth", action="store_true")
    p.add_argument("--taut-net", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_bar=args.float_bar,
        short_support=args.short_support,
        unclip_net=args.unclip_net,
        wide_mouth=args.wide_mouth,
        taut_net=args.taut_net,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("soccer-goal OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
