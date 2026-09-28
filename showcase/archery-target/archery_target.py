"""Game-ready archery range target — a showcase piece, not an example.

Asserts budget conformance of a procedural archery range target after
composing shipped pipeline pieces: bmesh construction, UVs, sixteen
materials, high-to-low normal bake, LOD chain, convex collider, Unity glTF
export.

A 1.10 m compressed-straw boss, coiled from rope courses that show on its
back and round its edge and bound with doubled jute twine, carries an 80 cm
ten-zone paper face (gold, red, blue, black and white, with ring lines, an X
ring and a printed X) held by four target pins. The boss leans back 12
degrees on a timber easel: two front legs on toe skids, a ledge on a rail and
two gussets that the boss rests on, a numbered butt board, a head block, a
strap hinge pinned to a single rear leg with a steel ferrule and foot, and a
chain between two eye bolts that limits the splay. Five arrows stand in the
face, a sixth glances into the straw edge, a seventh is snapped off in the
black with its fletched half lying on the grass, and a leather quiver with
three arrows lies on the turf patch among grass tufts.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--float-foot`` every support bedded in the
turf, ``--offset-hinge`` the hinge pin coaxial with its knuckles,
``--lift-boss`` the boss resting on its ledge, ``--high-boss`` the
regulation gold height, ``--shallow-arrow`` every point buried in the straw,
``--short-arrow`` every fletching clear of the face, ``--skew-vane`` the
vanes at 120 degrees, ``--wide-gold`` the ring radii of the scoring table,
``--short-skids`` the forward tip angle, ``--loose-pin`` one connected
assembly.

No RNG beyond seeded ``random.Random`` streams. DECIMATE COLLAPSE triangle
counts are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python archery_target.py --
    blender --background --python archery_target.py -- --skip-decimate
    blender --background --python archery_target.py -- --output target.png
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

# --- Frame (x across, y from the shooting line (-y) back, z up) -----------------
TILT_DEG = 12.0             # the boss leans back this far
_T = math.radians(TILT_DEG)
XV = Vector((1.0, 0.0, 0.0))
YAX = Vector((0.0, 1.0, 0.0))
ZAX = Vector((0.0, 0.0, 1.0))
UVEC = Vector((0.0, math.sin(_T), math.cos(_T)))    # up the face
NV = Vector((0.0, -math.cos(_T), math.sin(_T)))     # face normal, toward the archer
BOSS_ROT = Matrix((XV, UVEC, NV)).transposed()      # lathe frame: local z along NV

# --- Turf patch ---------------------------------------------------------------------
TURF_TOP = 0.050
TURF_HX = 1.00
TURF_HY = 1.34
TURF_CY = 0.28
TURF_SEGS = 96
# --- Boss: coiled straw rope courses ----------------------------------------------
R_BOSS = 0.550              # to the crest of the edge courses
H_BOSS = 0.280              # back crests to front-annulus crests
COURSE_A = 0.007            # rope course relief
COURSE_P = 0.050            # rope course pitch (target; fitted to a whole number)
BOSS_SH = 0.035             # corner radius of the coil section
BOSS_R0 = 0.030
FLAT_R = 0.430              # the face is pressed flat inside this radius
FADE_R = 0.470
BOSS_SEGS = 64
GOLD_H = 1.300              # World Archery: centre of gold 130 cm above the ground
# twine bindings: doubled strands over the edge at 8 stations
TW_BANDS = 8
TW_R0 = 0.455               # where each binding dives into the face / back
TW_R_A = 0.0035
TW_R_B = 0.0031
TW_SEP = 0.0068
TW_BITE = 0.0008
# --- Paper face: 80 cm, ten zones 4 cm wide -------------------------------------------
PAPER_R = 0.400
PAPER_R0 = 0.006
PAPER_T = 0.0015
PAPER_BITE = 0.0003
LINE_W = 0.0016
LINE_RADII = (0.02, 0.04, 0.08, 0.12, 0.16, 0.20, 0.24, 0.28, 0.32, 0.36)
WIDE_GOLD_R = 0.09          # --wide-gold misprints the gold/red boundary here
X_ARM = 0.0060
X_HALF = 0.0008
PIN_RING = 0.385
W_FLAT = 0.5 * H_BOSS - COURSE_A
W_PB = W_FLAT - PAPER_BITE
W_PF = W_PB + PAPER_T
C_Z = TURF_TOP + GOLD_H - NV.z * W_PF
C0 = Vector((0.0, 0.0, C_Z))
# --- Easel: front legs, skids, ledge ------------------------------------------------------
LEAN_BITE = 0.002           # back crests into the legs' front faces
LEG_A = 0.330
LEG_HW = 0.035
LEG_HD = 0.0225
W_LF = -0.5 * H_BOSS + LEAN_BITE
W_LC = W_LF - LEG_HD
W_LB = W_LF - 2.0 * LEG_HD
APEX_Z = 2.050
SKID_BITE = 0.002
SKID_H = 0.070
SKID_HW = 0.042
SKID_FRONT = 0.320
SKID_BACK = 0.220
SHORT_SKID_FRONT = 0.050
SKID_TOP = TURF_TOP - SKID_BITE + SKID_H
LEG_TENON = 0.030
SEAT_BITE = 0.0025          # the lowest edge course presses into the ledge
SHELF_T = 0.030
B_ST = -R_BOSS + SEAT_BITE
B_SB = B_ST - SHELF_T
SHELF_HA = 0.500
SHELF_W0 = W_LF - 0.012
SHELF_W1 = 0.5 * H_BOSS + 0.035
RAIL_HA = 0.440
RAIL_H = 0.090
RAIL_D = 0.040
RAIL_IN = 0.002
RAIL_BITE = 0.002
B_RT = B_SB + RAIL_BITE
W_R0 = W_LF - RAIL_IN
W_RF = W_R0 + RAIL_D
GUSSET_A = 0.200
GUSSET_T = 0.028
LIP_H = 0.022
LIP_D = 0.022
BRACE_HW = 0.020
BRACE_HD = 0.016
BRACE_TOE = 0.230          # from the leg foot along the skid
BRACE_TOE_Z = 0.420        # where it meets the leg
BRACE_HEEL = 0.170
BRACE_HEEL_Z = 0.300
# number board, head, hinge
BD_HA = 0.400
BD_H = 0.130
BD_D = 0.018
B_BD0 = R_BOSS + 0.020
W_BD0 = W_LF - 0.002
BUTT_NO = "12"
HEAD_HA = 0.400
HEAD_H = 0.120
HEAD_D = 0.045
W_H0 = W_LB + 0.002
W_HB = W_H0 - HEAD_D
KR = 0.011                  # knuckle radius
PIN_R = 0.004
LEAF_T = 0.005
LEAF_A_L = 0.085
LEAF_B_L = 0.110
REAR_DEG = 28.0
_R = math.radians(REAR_DEG)
DR = Vector((0.0, math.sin(_R), -math.cos(_R)))     # down the rear leg
NR = Vector((0.0, -math.cos(_R), -math.sin(_R)))    # rear leg's front face normal
RL_HW = 0.030
RL_HD = 0.0225
RL_TOP_E = 0.020
RL_OFF = KR + 0.4 * LEAF_T + RL_HD
RL_FOOT_Z = TURF_TOP + 0.050
FER_GAP = 0.003
FER_DOWN = 0.035
FER_UP = 0.070
FOOT_BITE = 0.002
TREAD_H = 0.036
TREAD_HX = 0.048
TREAD_HY = 0.050
# stretcher, eye bolts, chain
STR_HA = 0.400
STR_H = 0.070
STR_D = 0.040
STR_Z = 0.400
EYE_Z = 0.440
EB_R = 0.0040
EB_STEM = 0.012
ER = 0.014
EW = 0.0032
CW = 0.0030
RL_LINK = 0.0070
CHAIN_BITE = 0.0006
CHAIN_SLRL = 0.019
# --- Arrows ---------------------------------------------------------------------------------
ARROW_L = 0.740
SHORT_ARROW_L = 0.400
R_SHAFT = 0.0030
ARROW_SEGS = 10
VANE_S1 = 0.105             # vane front, from the nock end
VANE_LEN = 0.065
VANE_H = 0.014
VANE_T = 0.0008
VANE_BITE = 0.0008
VANE_SKEW = 15.0
# (a, b on the face, yaw, pitch, penetration, roll)
FACE_ARROWS = (
    (0.030, 0.045, -8.0, -3.0, 0.140, 10.0),
    (-0.055, -0.020, -11.0, -4.5, 0.150, 50.0),
    (0.095, -0.085, -6.0, -2.0, 0.130, 95.0),
    (-0.020, 0.140, -9.5, -5.0, 0.145, 25.0),
    (0.175, 0.090, -5.0, -3.5, 0.135, 70.0),
)
SHALLOW_PEN = 0.030
STUB = (-0.215, 0.205, -2.0, -4.0, 0.120, 0.240)       # a, b, yaw, pitch, pen, length
EDGE_ARROW = (140.0, 0.030, 0.35, -3.0, 0.120, 40.0)   # phi, w, inward, pitch, pen, roll
HALF_ARROW = (0.60, -0.62, 200.0, 0.460)               # x, y, heading, length
QUIVER = (-0.64, -0.46, -38.0)                          # x, y, mouth heading
QL = 0.500
Q_BITE = 0.0015
Q_ARROWS = ((0.020, 0.010, 15.0), (0.022, -0.013, 55.0), (0.006, 0.001, 100.0))
TUFT_SEED = 11
TONE_SEED = 5

# --- Falsifier sizes -----------------------------------------------------------------------
FLOAT_FOOT = 0.006
OFFSET_HINGE = 0.0025
LIFT_BOSS = 0.006
HIGH_BOSS = 0.080
LOOSE_PIN = 0.075

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (2.0071, 2.6887, 2.0538)
BASE_TRIS_MIN = 42000
BASE_TRIS_MAX = 44000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 16
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 1150
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
# face floors per slot, in slot order (straw, twine, timber, steel, white, black,
# blue, red, gold, carbon, vane, cock vane, nock, grass, soil, leather)
FACE_FLOORS = (4490, 1760, 1030, 5970, 495, 775, 120, 120, 240, 310, 475, 285, 1020, 4960, 270, 730)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# supports: two skids and the rear tread bedded in the turf
SUPPORT_COUNT = 3
SUPPORT_BITE_MIN = 0.001
SUPPORT_BITE_MAX = 0.004
# hinge: one pin through three knuckles
KNUCKLE_COUNT = 3
HINGE_AXIS_TOL = 0.0003
# boss rests on the ledge and leans on both legs
SEAT_MIN = 0.001
SEAT_MAX = 0.004
LEAN_MIN = 0.001
LEAN_MAX = 0.004
# regulation and real-world size
GOLD_TOL = 0.050
BOSS_D = 2.0 * R_BOSS
BOSS_T = H_BOSS
FACE_D = 2.0 * PAPER_R
SIZE_TOL = 0.004
FACE_TOL = 0.002
TILT_MIN = 10.0
TILT_MAX = 15.0
# arrows
EMBEDDED_COUNT = 7
DEPTH_MIN = 0.080
DEPTH_MAX = 0.200
AHEAD_MIN = 0.010
VANE_CLEAR_MIN = 0.250
FLETCHED_COUNT = 10
VANE_ANG_TOL = 1.0
# scoring table
RING_TOL = 0.0005
# stability: centre of mass inside the supports, and the forward tip angle
DENSITY = {"straw": 160.0, "twine": 500.0, "timber": 500.0, "steel": 7850.0, "paper": 700.0}
TIP_FWD_MIN_DEG = 20.0
# Hero yaw: the face turned toward the camera, the left edge and its arrow in view.
HERO_YAW_DEG = 6.0
WALL_Y = 3.4

STRAW_IDX = 0
TWINE_IDX = 1
TIMBER_IDX = 2
STEEL_IDX = 3
WHITE_IDX = 4
BLACK_IDX = 5
BLUE_IDX = 6
RED_IDX = 7
GOLD_IDX = 8
CARBON_IDX = 9
VANE_IDX = 10
COCK_IDX = 11
NOCK_IDX = 12
GRASS_IDX = 13
SOIL_IDX = 14
LEATHER_IDX = 15
PAPER_IDXS = (WHITE_IDX, BLACK_IDX, BLUE_IDX, RED_IDX, GOLD_IDX)
ZONE_EDGES = (0.08, 0.16, 0.24, 0.32, 0.40)
ZONE_MATS = (GOLD_IDX, RED_IDX, BLUE_IDX, BLACK_IDX, WHITE_IDX)

# 3 x 5 numerals, top row first (copied from showcase/weight-rack).
FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
}


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


def hashf(k):
    x = math.sin(k * 12.9898 + 78.233) * 43758.5453
    return x - math.floor(x)


# --------------------------------------------------------------------------
# Construction helpers (copied from showcase/weight-rack, not imported)
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


def cols(ex, ey, ez):
    return Matrix((Vector(ex), Vector(ey), Vector(ez))).transposed()


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False, seg_mats=None, cap_mats=None):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: the profile
    is an open polyline closed by n-gon caps at its two ends; otherwise it
    is a closed polygon revolved into a ring shell."""
    c = Vector(center)
    m = rot if rot is not None else Matrix.Identity(3)
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new(c + m @ Vector((r * ca, r * sa, z))) for r, z in profile])
    n = len(profile)
    last = n - 1 if solid else n
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for j in range(last):
            k = (j + 1) % n
            f = bm.faces.new((r0[j], r1[j], r1[k], r0[k]))
            f.material_index = seg_mats[j] if seg_mats else mat_idx
    if solid:
        f0 = bm.faces.new([rings[i][0] for i in reversed(range(segs))])
        f1 = bm.faces.new([rings[i][n - 1] for i in range(segs)])
        f0.material_index = cap_mats[0] if cap_mats else mat_idx
        f1.material_index = cap_mats[1] if cap_mats else mat_idx
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


def beam(bm, p0, p1, ex_hint, hx, hy, rc, mat_idx, ch=0.004, ch0=None, n_corner=3):
    """Chamfered timber (or steel) member from ``p0`` to ``p1``; section
    half-sizes ``hx`` along ``ex_hint`` and ``hy`` across it."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    length = d.length
    c0 = ch if ch0 is None else ch0
    prof = [(c0, 0.0), (0.0, c0), (0.0, length - ch), (ch, length)]
    return add_rbox(bm, hx, hy, rc, prof, p0, frame(d, ex_hint), mat_idx, n_corner)


def add_prism(bm, outline, w0, w1, origin, rot, mat_idx):
    """Planar outline [(u, v)] extruded along local Z from w0 to w1."""
    o = Vector(origin)
    a = [bm.verts.new(o + rot @ Vector((u, v, w0))) for u, v in outline]
    b = [bm.verts.new(o + rot @ Vector((u, v, w1))) for u, v in outline]
    n = len(outline)
    faces = [bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i])) for i in range(n)]
    faces.append(bm.faces.new(tuple(reversed(a))))
    faces.append(bm.faces.new(tuple(b)))
    _mark(faces, mat_idx)
    return a + b


def add_loop_tube(bm, pts, plane_n, radius, sides, mat_idx):
    """Closed tube along a planar closed centreline loop."""
    pn = Vector(plane_n).normalized()
    n = len(pts)
    rings = []
    for i in range(n):
        t = (pts[(i + 1) % n] - pts[i - 1]).normalized()
        nn = pn.cross(t).normalized()
        rings.append([bm.verts.new(pts[i] + nn * (radius * math.cos(2.0 * math.pi * k / sides))
                                   + pn * (radius * math.sin(2.0 * math.pi * k / sides)))
                      for k in range(sides)])
    faces = []
    for i in range(n):
        r0, r1 = rings[i], rings[(i + 1) % n]
        for k in range(sides):
            m = (k + 1) % sides
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    _mark(faces, mat_idx)


def triangulate_ngons(bm):
    faces = [f for f in bm.faces if len(f.verts) > 4]
    if faces:
        bmesh.ops.triangulate(bm, faces=faces)


def pack_uvs(bm, margin=0.08):
    uv = bm.loops.layers.uv.new("UVMap")
    faces = list(bm.faces)
    n = len(faces)
    ncol = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / ncol))
    cell_w = 1.0 / ncol
    cell_h = 1.0 / rows
    pad_u = margin * cell_w * 0.5
    pad_v = margin * cell_h * 0.5
    usable_w = cell_w - 2.0 * pad_u
    usable_h = cell_h - 2.0 * pad_v
    for i, face in enumerate(faces):
        col = i % ncol
        row = i // ncol
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


def add_digit(bm, ch, origin, e_u, e_v, e_n, cell, proud, bite, mat_idx):
    """One raised numeral: the filled cells of a 3 x 5 grid, one manifold shell."""
    filled = {(c, 4 - r) for r, row in enumerate(FONT[ch]) for c, x in enumerate(row) if x == "1"}
    top, bot = {}, {}

    def vt(i, j):
        if (i, j) not in top:
            top[(i, j)] = bm.verts.new(origin + e_u * (i * cell) + e_v * (j * cell) + e_n * proud)
        return top[(i, j)]

    def vb(i, j):
        if (i, j) not in bot:
            bot[(i, j)] = bm.verts.new(origin + e_u * (i * cell) + e_v * (j * cell) - e_n * bite)
        return bot[(i, j)]

    faces = []
    for i, j in sorted(filled):
        faces.append(bm.faces.new((vt(i, j), vt(i + 1, j), vt(i + 1, j + 1), vt(i, j + 1))))
        faces.append(bm.faces.new((vb(i, j + 1), vb(i + 1, j + 1), vb(i + 1, j), vb(i, j))))
        for (di, dj), (a, b) in (((0, -1), ((i, j), (i + 1, j))),
                                 ((1, 0), ((i + 1, j), (i + 1, j + 1))),
                                 ((0, 1), ((i + 1, j + 1), (i, j + 1))),
                                 ((-1, 0), ((i, j + 1), (i, j)))):
            if (i + di, j + dj) not in filled:
                faces.append(bm.faces.new((vt(*a), vb(*a), vb(*b), vt(*b))))
    _mark(faces, mat_idx)


def add_number(bm, text, centre, e_u, e_v, e_n, cell, proud, bite, step, mat_idx):
    """A numeral string centred on ``centre``; each digit on its own plane."""
    n = len(text)
    width = (4 * n - 1) * cell
    for d, ch in enumerate(text):
        o = centre + e_u * (-0.5 * width + 4 * d * cell) + e_v * (-2.5 * cell + d * 0.0003)
        add_digit(bm, ch, o, e_u, e_v, e_n, cell, proud + step * d, bite + step * d, mat_idx)


def add_dome(bm, pos, axis, k, r=0.0105, segs=12):
    """Domed bolt or screw head seated on a face whose outward normal is
    ``axis``; ``k`` staggers heads of one group along the axis. Turned a
    quarter segment, so no facet normal is square to the head's frame and
    two heads side by side never put facets on one plane."""
    axis = Vector(axis).normalized()
    ref = ZAX if abs(axis.z) < 0.9 else XV
    base = Vector(pos) - axis * (0.0003 + 0.00012 * k)
    add_lathe(bm, [(0.0035, 0.0), (r, 0.0), (r, 0.0015), (0.8 * r, 0.0040), (0.45 * r, 0.0056),
                   (0.0015, 0.0062)], segs, STEEL_IDX, center=base, rot=frame(axis, ref),
              solid=True, phase=0.5 * math.pi / segs)


def move_verts(verts, mat=None, pivot=None, shift=None):
    piv = Vector(pivot) if pivot is not None else Vector()
    for v in verts:
        co = v.co.copy()
        if mat is not None:
            co = piv + mat @ (co - piv)
        if shift is not None:
            co = co + Vector(shift)
        v.co = co


# --------------------------------------------------------------------------
# Boss: coiled rope courses, twine bindings
# --------------------------------------------------------------------------

def boss_profile():
    """(points, arclengths, normals) of the boss section, back centre to
    front centre. A rounded rectangle carries a cosine rope-course relief
    whose crests sit on the back plane, the edge radius and the front
    annulus; inside FLAT_R the face is pressed flat for the paper."""
    A = COURSE_A
    rb = R_BOSS - A
    wb = -0.5 * H_BOSS + A
    wf = 0.5 * H_BOSS - A
    sh = BOSS_SH
    l1 = (rb - sh) - BOSS_R0
    lc = 0.5 * math.pi * sh
    le = (wf - sh) - (wb + sh)

    def base(s):
        if s <= l1:
            return (BOSS_R0 + s, wb), (0.0, -1.0)
        s -= l1
        if s <= lc:
            a = -0.5 * math.pi + s / sh
            return (rb - sh + sh * math.cos(a), wb + sh + sh * math.sin(a)), (math.cos(a), math.sin(a))
        s -= lc
        if s <= le:
            return (rb, wb + sh + s), (1.0, 0.0)
        s -= le
        if s <= lc:
            a = s / sh
            return (rb - sh + sh * math.cos(a), wf - sh + sh * math.sin(a)), (math.cos(a), math.sin(a))
        s -= lc
        return (rb - sh - s, wf), (0.0, 1.0)

    s_front = l1 + 2.0 * lc + le
    s_flat = s_front + (rb - sh - FLAT_R)
    n_c = max(1, round(s_flat / COURSE_P))
    period = s_flat / n_c
    pts, svals, crest = [], [], []
    for k in range(4 * n_c + 1):
        s = k * period / 4.0
        (r, w), (nr, nw) = base(s)
        env = 1.0
        if s > s_front:
            t = min(max((r - FLAT_R) / (FADE_R - FLAT_R), 0.0), 1.0)
            env = t * t * (3.0 - 2.0 * t)
        bump = A * env * 0.5 * (1.0 + math.cos(2.0 * math.pi * s / period))
        pts.append((r + nr * bump, w + nw * bump))
        svals.append(s)
        # the envelope over the crests, with the base section's normal
        crest.append(((r + nr * A * env, w + nw * A * env), (nr, nw)))
    for r in (0.405, 0.300, 0.160, BOSS_R0):
        pts.append((r, wf))
        svals.append(None)
    normals = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tx, tw = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, tw)
        normals.append((tw / ln, -tx / ln))
    tw_s0 = l1 - (rb - sh - TW_R0)
    tw_s1 = s_front + (rb - sh - TW_R0)
    return pts, svals, crest, (tw_s0, tw_s1), period


def add_boss(bm, C):
    prof, svals, crest, tw_span, _period = boss_profile()
    add_lathe(bm, prof, BOSS_SEGS, STRAW_IDX, center=C, rot=BOSS_ROT, solid=True)
    # Bindings are drawn tight over the courses: they lie on the envelope
    # over the crests (biting them) and bridge the grooves between.
    idx = [i for i, s in enumerate(svals)
           if s is not None and tw_span[0] <= s <= tw_span[1] and i % 2 == 0]
    step = BOSS_SEGS // TW_BANDS
    for band in range(TW_BANDS):
        phi = 2.0 * math.pi * (step // 2 + band * step) / BOSS_SEGS
        e_r = XV * math.cos(phi) + UVEC * math.sin(phi)
        e_t = -XV * math.sin(phi) + UVEC * math.cos(phi)
        for strand, (off, rad) in enumerate(((0.5 * TW_SEP, TW_R_A), (-0.5 * TW_SEP, TW_R_B))):
            path = []
            for i in idx:
                (r, w), (nr, nw) = crest[i]
                n3 = e_r * nr + NV * nw
                path.append((C + e_r * r + NV * w + e_t * off + n3 * (rad - TW_BITE), n3))
            for end in (0, -1):
                p, n3 = path[end]
                q = path[1][0] if end == 0 else path[-2][0]
                t = (p - q).normalized()
                # the two strands dive to different depths, so their buried
                # end caps never share a plane
                ext = (p + t * (0.004 + 0.002 * strand) - n3 * (rad + 0.006 + 0.002 * strand), n3)
                if end == 0:
                    path.insert(0, ext)
                else:
                    path.append(ext)
            rings = []
            for p, n3 in path:
                rings.append([bm.verts.new(p + n3 * (rad * math.cos(math.pi * k / 3.0))
                                           + e_t * (rad * math.sin(math.pi * k / 3.0)))
                              for k in range(6)])
            faces = []
            for r0, r1 in zip(rings, rings[1:]):
                for k in range(6):
                    m = (k + 1) % 6
                    faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
            faces.append(bm.faces.new(tuple(reversed(rings[0]))))
            faces.append(bm.faces.new(tuple(rings[-1])))
            _mark(faces, TWINE_IDX)


def face_lines(wide_gold):
    return tuple(WIDE_GOLD_R if (wide_gold and r == 0.08) else r for r in LINE_RADII)


def face_zone_edges(wide_gold):
    return (WIDE_GOLD_R if wide_gold else ZONE_EDGES[0],) + ZONE_EDGES[1:]


def zone_mat(r, edges):
    for edge, mat in zip(edges, ZONE_MATS):
        if r < edge:
            return mat
    return WHITE_IDX


def line_mat(r, edges):
    """Ring lines are black, except the one inside the black zone."""
    return WHITE_IDX if edges[2] + 0.01 < r < edges[3] - 0.01 else BLACK_IDX


def add_face(bm, C, wide_gold, pin_lift):
    lines = face_lines(wide_gold)
    edges = face_zone_edges(wide_gold)
    rs = sorted({PAPER_R0, PAPER_R - 0.0008}
                | {round(r + s * 0.5 * LINE_W, 6) for r in lines for s in (-1.0, 1.0)})
    prof = [(r, W_PF) for r in rs] + [(PAPER_R, W_PF - 0.0005), (PAPER_R, W_PB), (PAPER_R0, W_PB)]
    mats = []
    for j in range(len(prof) - 1):
        if j < len(rs) - 1:
            rm = 0.5 * (rs[j] + rs[j + 1])
            line = next((r for r in lines if abs(rm - r) < 0.5 * LINE_W), None)
            mats.append(line_mat(line, edges) if line is not None else zone_mat(rm, edges))
        else:
            mats.append(WHITE_IDX)
    add_lathe(bm, prof, BOSS_SEGS, WHITE_IDX, center=C, rot=BOSS_ROT, solid=True, seg_mats=mats,
              cap_mats=(GOLD_IDX, WHITE_IDX))
    # the printed X in the centre of the X ring
    base = [(X_HALF, X_HALF), (X_ARM, X_HALF), (X_ARM, -X_HALF), (X_HALF, -X_HALF),
            (X_HALF, -X_ARM), (-X_HALF, -X_ARM), (-X_HALF, -X_HALF), (-X_ARM, -X_HALF),
            (-X_ARM, X_HALF), (-X_HALF, X_HALF), (-X_HALF, X_ARM), (X_HALF, X_ARM)]
    c = math.cos(math.pi / 4.0)
    outline = [(c * (x - y), c * (x + y)) for x, y in base]
    add_prism(bm, outline, W_PF - 0.0002, W_PF + 0.00025, C, BOSS_ROT, BLACK_IDX)
    # target pins through the white
    for k in range(4):
        ang = math.pi / 4.0 + 0.5 * math.pi * k
        lift = pin_lift if k == 0 else 0.0
        o = C + XV * (PIN_RING * math.cos(ang)) + UVEC * (PIN_RING * math.sin(ang)) + NV * (W_PF + lift)
        add_lathe(bm, [(0.0014, -0.0003), (0.0072, -0.0003), (0.0080, 0.0006), (0.0080, 0.0028),
                       (0.0068, 0.0046), (0.0036, 0.0058), (0.0014, 0.0060)], 16, NOCK_IDX,
                  center=o, rot=BOSS_ROT, solid=True)
        add_lathe(bm, [(0.0003, -0.060), (0.0012, -0.055), (0.0012, 0.0035)], 6, STEEL_IDX,
                  center=o, rot=BOSS_ROT, solid=True)


# --------------------------------------------------------------------------
# Arrows
# --------------------------------------------------------------------------

# The rear edge is raked, so the three vanes' rear faces do not share the
# plane square to the shaft.
VANE_OUTLINE = [(0.0, -VANE_BITE), (VANE_LEN, -VANE_BITE), (VANE_LEN - 0.0015, 0.0040),
                (VANE_LEN - 0.004, 0.0125), (VANE_LEN - 0.012, VANE_H),
                (0.55 * VANE_LEN, 0.0115), (0.25 * VANE_LEN, 0.0055), (0.004, 0.0012)]


def arrow_profile(L, point, nock):
    pts, mats = [], []

    def seg(p, m):
        pts.append(p)
        if len(pts) > 1:
            mats.append(m)

    if point:
        for p in ((0.0005, 0.0), (0.0016, 0.004), (0.0027, 0.013), (0.0033, 0.019),
                  (0.0033, 0.023), (R_SHAFT, 0.0255)):
            seg(p, STEEL_IDX)
    else:
        seg((R_SHAFT, 0.0), CARBON_IDX)
    if nock:
        seg((R_SHAFT, L - 0.150), CARBON_IDX)
        seg((R_SHAFT, L - 0.135), VANE_IDX)
        seg((R_SHAFT, L - 0.130), CARBON_IDX)
        seg((R_SHAFT, L - 0.124), COCK_IDX)
        seg((R_SHAFT, L - 0.022), CARBON_IDX)
        for p in ((0.0033, L - 0.0205), (0.0036, L - 0.010), (0.0036, L - 0.004), (0.0030, L - 0.001),
                  (0.0017, L)):
            seg(p, NOCK_IDX)
    else:
        seg((R_SHAFT, L), CARBON_IDX)
    return pts, mats


def add_arrow(bm, tip, travel, L, roll_deg, point=True, nock=True, fletch=True, skew=0.0,
              jag=None):
    """Arrow from its tip (or broken front) back along ``-travel``: a
    turned point, carbon shaft with cresting and a nock in one lathe, and
    three vanes at 120 degrees, the cock vane first."""
    tip = Vector(tip)
    ah = (-Vector(travel)).normalized()
    rot = frame(ah, ZAX if abs(ah.z) < 0.9 else XV)
    prof, mats = arrow_profile(L, point, nock)
    # each arrow's lathe turned by its roll, so the facets of neighbouring
    # parallel arrows (the quiver) are never parallel planes
    verts = add_lathe(bm, prof, ARROW_SEGS, CARBON_IDX, center=tip, rot=rot, solid=True,
                      phase=math.radians(roll_deg), seg_mats=mats, cap_mats=(STEEL_IDX if point else CARBON_IDX,
                                               NOCK_IDX if nock else CARBON_IDX))
    n = len(prof)
    if jag is not None:
        j = 0 if jag == "front" else n - 1
        sgn = -1.0 if jag == "front" else 1.0
        for i in range(ARROW_SEGS):
            d = 0.0045 * (0.5 + 0.5 * math.sin(2.7 * i + 0.9))
            verts[i * n + j].co += ah * (sgn * d)
    vane_verts = []
    if fletch:
        e1, e2 = rot.col[0].copy(), rot.col[1].copy()
        for k in range(3):
            th = math.radians(roll_deg + 120.0 * k + (skew if k == 2 else 0.0))
            rd = e1 * math.cos(th) + e2 * math.sin(th)
            tau = ah.cross(rd)
            o = tip + ah * (L - VANE_S1) + rd * R_SHAFT
            vane_verts += add_prism(bm, VANE_OUTLINE, -0.5 * VANE_T, 0.5 * VANE_T, o,
                                    cols(ah, rd, tau), COCK_IDX if k == 0 else VANE_IDX)
    return verts, vane_verts


def travel_dir(yaw_deg, pitch_deg):
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    return Vector((math.sin(y) * math.cos(p), math.cos(y) * math.cos(p), math.sin(p)))


def add_boss_arrows(bm, C, shallow, short, skew):
    for i, (a, b, yaw, pitch, pen, roll) in enumerate(FACE_ARROWS):
        d = travel_dir(yaw, pitch)
        if shallow and i == 2:
            pen = SHALLOW_PEN
        hit = C + XV * a + UVEC * b + NV * W_PF
        add_arrow(bm, hit + d * pen, d, SHORT_ARROW_L if (short and i == 1) else ARROW_L, roll,
                  skew=VANE_SKEW if (skew and i == 0) else 0.0)
    a, b, yaw, pitch, pen, length = STUB
    d = travel_dir(yaw, pitch)
    hit = C + XV * a + UVEC * b + NV * W_PF
    add_arrow(bm, hit + d * pen, d, length, 0.0, nock=False, fletch=False, jag="back")
    phi, w, inward, pitch, pen, roll = EDGE_ARROW
    ph = math.radians(phi)
    e_r = XV * math.cos(ph) + UVEC * math.sin(ph)
    hit = C + e_r * (R_BOSS - 0.5 * COURSE_A) + NV * w
    d = (-e_r * inward + YAX + ZAX * math.sin(math.radians(pitch))).normalized()
    add_arrow(bm, hit + d * pen, d, ARROW_L, roll)


def add_half_arrow(bm):
    """The fletched half of the snapped arrow, lying on the grass: resting on
    two vanes at the back and on its broken end at the front."""
    x, y, heading, length = HALF_ARROW
    hd = math.radians(heading)
    fwd = Vector((math.cos(hd), math.sin(hd), 0.0))
    front = Vector((x, y, TURF_TOP + 0.05)) + fwd * (0.5 * length)
    shaft, vanes = add_arrow(bm, front, fwd, length, 0.0, point=False, jag="front")
    allv = shaft + vanes
    vlow = min(vanes, key=lambda v: v.co.z).co.copy()
    near = [v for v in shaft if (v.co - front).dot(-fwd) < 0.02]
    flow = min(near, key=lambda v: v.co.z).co.copy()
    axis = fwd.cross(ZAX).normalized()
    best = None
    dh = abs((flow - vlow).dot(fwd))
    for sgn in (1.0, -1.0):
        ang = sgn * math.atan2(flow.z - vlow.z, dh)
        m = Matrix.Rotation(ang, 3, axis)
        fz = (vlow + m @ (flow - vlow)).z
        if best is None or abs(fz - vlow.z) < best[0]:
            best = (abs(fz - vlow.z), m)
    move_verts(allv, best[1], vlow)
    zmin = min(v.co.z for v in allv)
    move_verts(allv, shift=(0.0, 0.0, TURF_TOP - 0.001 - zmin))


# --------------------------------------------------------------------------
# Quiver
# --------------------------------------------------------------------------

Q_FLOOR = 0.0085
Q_PROF = [(0.004, 0.0), (0.036, 0.0), (0.041, 0.004), (0.043, 0.012), (0.052, 0.6 * QL),
          (0.056, QL - 0.012), (0.0595, QL - 0.009), (0.0612, QL - 0.004), (0.0600, QL - 0.0005),
          (0.0572, QL), (0.0535, QL - 0.004), (0.0525, QL - 0.012), (0.0485, 0.6 * QL),
          (0.0395, 0.014), (0.0360, Q_FLOOR), (0.004, Q_FLOOR)]


def quiver_r(z):
    """Outer radius of the quiver body at height ``z`` (local)."""
    outer = [(0.043, 0.012), (0.052, 0.6 * QL), (0.056, QL - 0.012)]
    for (r0, z0), (r1, z1) in zip(outer, outer[1:]):
        if z0 <= z <= z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return outer[-1][0]


def add_quiver(bm):
    """Leather quiver lying on the turf, mouth toward the front-right, three
    arrows inside with their tips on its floor."""
    x, y, heading = QUIVER
    hd = math.radians(heading)
    q = Vector((math.cos(hd), math.sin(hd), 0.0))
    base = Vector((x, y, TURF_TOP + 0.06))
    rot = frame(q, -ZAX)            # local x = world down, local z = the mouth heading
    body = add_lathe(bm, Q_PROF, 24, LEATHER_IDX, center=base, rot=rot, solid=True)
    allv = list(body)
    for z0, z1 in ((0.022, 0.046), (0.150, 0.175), (0.360, 0.385)):
        r0, r1 = quiver_r(z0), quiver_r(z1)
        allv += add_lathe(bm, [(r0 - 0.0008, z0), (r0 + 0.0022, z0 + 0.0008),
                               (r1 + 0.0022, z1 - 0.0008), (r1 - 0.0008, z1)], 24, LEATHER_IDX,
                          center=base, rot=rot, phase=math.pi / 24.0)
    # belt loop along the top of the lying quiver, under the two upper bands
    z0, z1 = 0.130, 0.395
    t = 0.004
    p0 = base + rot @ Vector((-(quiver_r(z0) + 0.5 * t - 0.0008), 0.0, z0))
    p1 = base + rot @ Vector((-(quiver_r(z1) + 0.5 * t - 0.0008), 0.0, z1))
    allv += beam(bm, p0, p1, rot @ Vector((1.0, 0.0, 0.0)), 0.5 * t, 0.018, 0.0015, LEATHER_IDX,
                 ch=0.001)
    for k, (ox, oy, roll) in enumerate(Q_ARROWS):
        # each tip bites the floor a different depth, so the three nocks'
        # end caps stand on different planes
        tip = base + rot @ Vector((ox, oy, Q_FLOOR - 0.0008 * (k + 1)))
        d = rot @ Vector((-0.10 * ox, -0.10 * oy, -1.0))
        sh, vn = add_arrow(bm, tip, d, ARROW_L, roll)
        allv += sh + vn
    lo = [v for v in body if (v.co - base).dot(q) < 0.3 * QL]
    hi = [v for v in body if (v.co - base).dot(q) > 0.7 * QL]
    v1 = min(lo, key=lambda v: v.co.z).co.copy()
    v2 = min(hi, key=lambda v: v.co.z).co.copy()
    axis = q.cross(ZAX).normalized()
    dh = abs((v2 - v1).dot(q))
    best = None
    for sgn in (1.0, -1.0):
        m = Matrix.Rotation(sgn * math.atan2(v2.z - v1.z, dh), 3, axis)
        fz = (v1 + m @ (v2 - v1)).z
        if best is None or abs(fz - v1.z) < best[0]:
            best = (abs(fz - v1.z), m)
    move_verts(allv, best[1], v1)
    zmin = min(v.co.z for v in body)
    move_verts(allv, shift=(0.0, 0.0, TURF_TOP - Q_BITE - zmin))


# --------------------------------------------------------------------------
# Easel stand
# --------------------------------------------------------------------------

def bpt(a, b, w, shift=0.0):
    return C0 + XV * a + UVEC * (b + shift) + NV * w


def leg_b_at_z(z, w):
    return (z - C_Z - NV.z * w) / UVEC.z


B_LEG_BOT = leg_b_at_z(SKID_TOP - LEG_TENON, W_LC)
B_LEG_TOP = leg_b_at_z(APEX_Z, W_LC)
B_HEAD1 = B_LEG_TOP - 0.020
B_HEAD0 = B_HEAD1 - HEAD_H
B_K = B_HEAD1 - 0.012
W_K = W_HB - KR
K0 = bpt(0.0, B_K, W_K)
Q0 = K0 - NR * RL_OFF
T_BOT = (RL_FOOT_Z - Q0.z) / DR.z
B_STR = leg_b_at_z(STR_Z, W_LC)
W_S0 = W_LB + 0.002
W_S1 = W_S0 - STR_D


def eye_centres():
    f1 = bpt(0.0, B_STR, W_S1)
    n1 = -NV
    t_e = (EYE_Z - Q0.z) / DR.z
    f2 = Q0 + DR * t_e + NR * RL_HD
    n2 = NR.copy()
    return (f1, n1, f1 + n1 * (EB_STEM + ER)), (f2, n2, f2 + n2 * (EB_STEM + ER))


def add_eyebolt(bm, face_pt, n):
    add_lathe(bm, [(0.0006, -0.022), (EB_R, -0.020), (EB_R, EB_STEM + 0.3 * EW)], 8, STEEL_IDX,
              center=face_pt, rot=frame(n, XV), solid=True)
    add_lathe(bm, [(EB_R - 0.0003, -0.0004), (0.0085, -0.0004), (0.0085, 0.0014),
                   (0.0070, 0.0022), (EB_R - 0.0003, 0.0022)], 12, STEEL_IDX, center=face_pt,
              rot=frame(n, XV), phase=math.pi / 12.0)
    e = face_pt + n * (EB_STEM + ER)
    circ = [(ER + EW * math.cos(2.0 * math.pi * k / 8), EW * math.sin(2.0 * math.pi * k / 8))
            for k in range(8)]
    add_lathe(bm, circ, 16, STEEL_IDX, center=e, rot=frame(XV, n))


def add_link(bm, c, d, q, sl, rl):
    pts = []
    for s in range(7):
        a = -0.5 * math.pi + math.pi * s / 6.0
        pts.append(c + d * (sl + rl * math.cos(a)) + q * (rl * math.sin(a)))
    for s in range(7):
        a = 0.5 * math.pi + math.pi * s / 6.0
        pts.append(c + d * (-sl + rl * math.cos(a)) + q * (rl * math.sin(a)))
    add_loop_tube(bm, pts, d.cross(q), CW, 6, STEEL_IDX)


def add_chain(bm, e1, e2):
    d = e2 - e1
    dist = d.length
    d.normalize()
    q2 = d.cross(XV).normalized()
    total = dist - 2.0 * (ER - CW - EW + CHAIN_BITE)
    n = int(round((total - (2.0 * CW - CHAIN_BITE)) / (2.0 * CHAIN_SLRL - 2.0 * CW + CHAIN_BITE)))
    if n % 2 == 0:
        n += 1
    slrl = (total + (n - 1) * (2.0 * CW - CHAIN_BITE)) / (2.0 * n)
    pitch = 2.0 * slrl - 2.0 * CW + CHAIN_BITE
    c1 = e1 + d * (ER - (CW + EW) + CHAIN_BITE + slrl)
    for k in range(n):
        ang = (0.5 * math.pi if k % 2 else 0.0) + math.radians(3.0) * ((k // 2) % 2)
        q = XV * math.cos(ang) + q2 * math.sin(ang)
        add_link(bm, c1 + d * (pitch * k), d, q, slrl - RL_LINK, RL_LINK)
    return n


def add_stand(bm, bevel_verts, ledge_shift, float_foot, offset_hinge, short_skids):
    ls = ledge_shift
    for side in (-1.0, 1.0):
        a = side * LEG_A
        p_bot = bpt(a, B_LEG_BOT, W_LC)
        beam(bm, p_bot, bpt(a, B_LEG_TOP, W_LC), XV, LEG_HW, LEG_HD, 0.006, TIMBER_IDX)
        # toe skid under the leg, the leg tenoned into it
        front = p_bot.y - (SHORT_SKID_FRONT if short_skids else SKID_FRONT)
        back = p_bot.y + SKID_BACK
        zc = TURF_TOP - SKID_BITE + 0.5 * SKID_H
        beam(bm, (a, front, zc), (a, back, zc), XV, SKID_HW, 0.5 * SKID_H, 0.006, TIMBER_IDX,
             ch=0.006, ch0=0.018)
        for k, dy in enumerate((-0.020, 0.020)):
            add_dome(bm, (a + side * SKID_HW, p_bot.y + dy, zc + 0.005 * (1 - 2 * k)),
                     (side, 0.0, 0.0), k)
        # knee braces: toe and heel of the skid up into the leg, each end
        # buried in its member (the leg's centre plane, below the skid top)
        for y_off, z_leg in ((-BRACE_TOE, BRACE_TOE_Z), (BRACE_HEEL, BRACE_HEEL_Z)):
            lo = Vector((a, p_bot.y + y_off, SKID_TOP - 0.020))
            hi = bpt(a, leg_b_at_z(z_leg, W_LC), W_LC)
            beam(bm, lo, hi, XV, BRACE_HW, BRACE_HD, 0.004, TIMBER_IDX)
        # carriage bolts: rail, board, head, stretcher
        for k, db in enumerate((-0.022, 0.022)):
            add_dome(bm, bpt(a, B_RT - 0.5 * RAIL_H + db, W_RF, ls), NV, k)
        add_dome(bm, bpt(a, B_BD0 + 0.5 * BD_H, W_BD0 + BD_D), NV, 0, r=0.008)
        add_dome(bm, bpt(a, 0.5 * (B_HEAD0 + B_HEAD1), W_HB), -NV, 0)
        add_dome(bm, bpt(a, B_STR, W_S1), -NV, 1)
    # ledge: rail on the legs' front faces, shelf on the rail, two gussets
    b_rc = B_RT - 0.5 * RAIL_H
    w_rc = W_R0 + 0.5 * RAIL_D
    beam(bm, bpt(-RAIL_HA, b_rc, w_rc, ls), bpt(RAIL_HA, b_rc, w_rc, ls), UVEC, 0.5 * RAIL_H,
         0.5 * RAIL_D, 0.005, TIMBER_IDX)
    w_sc = 0.5 * (SHELF_W0 + SHELF_W1)
    beam(bm, bpt(-SHELF_HA, B_SB + 0.5 * SHELF_T, w_sc, ls),
         bpt(SHELF_HA, B_SB + 0.5 * SHELF_T, w_sc, ls), UVEC, 0.5 * SHELF_T,
         0.5 * (SHELF_W1 - SHELF_W0), 0.006, TIMBER_IDX)
    # stop lip along the ledge's front edge, clear of the boss's front face
    b_lc = B_ST + LIP_H * 0.5 - 0.002
    w_lc = SHELF_W1 - 0.001 - LIP_D * 0.5
    beam(bm, bpt(-SHELF_HA + 0.012, b_lc, w_lc, ls), bpt(SHELF_HA - 0.012, b_lc, w_lc, ls), UVEC,
         0.5 * LIP_H, 0.5 * LIP_D, 0.004, TIMBER_IDX)
    gusset = [(W_RF - 0.002, B_SB + 0.0015), (W_RF + 0.200, B_SB + 0.0015),
              (W_RF + 0.200, B_SB - 0.014), (W_RF + 0.030, B_SB - 0.084),
              (W_RF - 0.002, B_SB - 0.084)]
    for side in (-1.0, 1.0):
        a = side * GUSSET_A
        bevel_verts += add_prism(bm, gusset, a - 0.5 * GUSSET_T, a + 0.5 * GUSSET_T,
                                 C0 + UVEC * ls, cols(NV, UVEC, XV), TIMBER_IDX)
    # numbered butt board above the boss
    b_bc = B_BD0 + 0.5 * BD_H
    beam(bm, bpt(-BD_HA, b_bc, W_BD0 + 0.5 * BD_D), bpt(BD_HA, b_bc, W_BD0 + 0.5 * BD_D), UVEC,
         0.5 * BD_H, 0.5 * BD_D, 0.005, WHITE_IDX)
    add_number(bm, BUTT_NO, bpt(0.0, b_bc, W_BD0 + BD_D), XV, UVEC, NV, 0.015, 0.0005, 0.0003,
               0.00013, BLACK_IDX)
    # head block behind the leg tops, stretcher low
    beam(bm, bpt(-HEAD_HA, 0.5 * (B_HEAD0 + B_HEAD1), W_H0 - 0.5 * HEAD_D),
         bpt(HEAD_HA, 0.5 * (B_HEAD0 + B_HEAD1), W_H0 - 0.5 * HEAD_D), UVEC, 0.5 * HEAD_H,
         0.5 * HEAD_D, 0.006, TIMBER_IDX)
    beam(bm, bpt(-STR_HA, B_STR, W_S0 - 0.5 * STR_D), bpt(STR_HA, B_STR, W_S0 - 0.5 * STR_D),
         UVEC, 0.5 * STR_H, 0.5 * STR_D, 0.006, TIMBER_IDX)
    # strap hinge: leaf A on the head with the two outer knuckles, leaf B on
    # the rear leg with the middle one, a riveted pin through all three
    add_rbox(bm, 0.048, 0.5 * LEAF_A_L, 0.006,
             [(0.0, 0.0), (0.0, LEAF_T - 0.0003), (0.0008, LEAF_T + 0.0005)],
             bpt(0.0, B_K - 0.5 * LEAF_A_L, W_HB + 0.0005), frame(-NV, XV), STEEL_IDX)
    for k, (da, db) in enumerate(((-0.032, -0.030), (0.032, -0.030), (-0.032, -0.068),
                                  (0.032, -0.068))):
        add_dome(bm, bpt(da, B_K + db, W_HB - LEAF_T), -NV, k, r=0.0065, segs=10)
    krot = frame(XV, UVEC)
    for (a0, a1), ph in (((-0.050, -0.0175), 0.0), ((0.0175, 0.050), 0.0),
                         ((-0.0155, 0.0155), math.pi / 16.0)):
        add_lathe(bm, [(PIN_R - 0.0002, a0), (KR - 0.0012, a0), (KR, a0 + 0.0012),
                       (KR, a1 - 0.0012), (KR - 0.0012, a1), (PIN_R - 0.0002, a1)], 16, STEEL_IDX,
                  center=K0, rot=krot, phase=ph)
    pin_c = K0 + (UVEC * OFFSET_HINGE if offset_hinge else Vector())
    add_lathe(bm, [(0.0015, -0.056), (0.0062, -0.0555), (0.0068, -0.0530), (0.0068, -0.0505),
                   (PIN_R, -0.0500), (PIN_R, 0.0500), (0.0068, 0.0505), (0.0068, 0.0530),
                   (0.0062, 0.0555), (0.0015, 0.056)], 12, STEEL_IDX, center=pin_c, rot=krot,
              solid=True)
    add_rbox(bm, 0.015, 0.5 * LEAF_B_L, 0.005,
             [(0.0, 0.0), (0.0, LEAF_T - 0.0003), (0.0008, LEAF_T + 0.0005)],
             K0 - NR * (KR + 0.4 * LEAF_T + 0.0005) + DR * (0.5 * LEAF_B_L - 0.006),
             frame(NR, XV), STEEL_IDX)
    for k, t in enumerate((0.040, 0.080)):
        add_dome(bm, K0 - NR * (KR - 0.6 * LEAF_T) + DR * t, NR, k, r=0.0065, segs=10)
    # rear leg, ferrule and tread
    beam(bm, Q0 + DR * (-RL_TOP_E), Q0 + DR * T_BOT, XV, RL_HW, RL_HD, 0.006, TIMBER_IDX)
    lift = Vector((0.0, 0.0, FLOAT_FOOT if float_foot else 0.0))
    fb = Q0 + DR * (T_BOT + FER_DOWN)
    fer = beam(bm, fb, Q0 + DR * (T_BOT - FER_UP), XV, RL_HW + FER_GAP, RL_HD + FER_GAP, 0.007,
               STEEL_IDX, ch=0.003)
    tread = add_rbox(bm, TREAD_HX, TREAD_HY, 0.010,
                     [(0.004, 0.0), (0.0, 0.004), (0.0, TREAD_H - 0.004), (0.004, TREAD_H)],
                     (fb.x, fb.y + 0.006, TURF_TOP - FOOT_BITE), Matrix.Identity(3), STEEL_IDX)
    move_verts(fer + tread, shift=lift)
    # splay chain between two eye bolts
    (f1, n1, e1), (f2, n2, e2) = eye_centres()
    add_eyebolt(bm, f1, n1)
    add_eyebolt(bm, f2, n2)
    return add_chain(bm, e1, e2)


# --------------------------------------------------------------------------
# Turf and grass
# --------------------------------------------------------------------------

def turf_outline(inset):
    pts = []
    for i in range(TURF_SEGS):
        th = 2.0 * math.pi * i / TURF_SEGS
        c, s = math.cos(th), math.sin(th)
        x = TURF_HX * math.copysign(abs(c) ** 0.5, c)
        y = TURF_HY * math.copysign(abs(s) ** 0.5, s)
        k = 1.0 + 0.020 * math.cos(3.0 * th + 0.4) + 0.012 * math.sin(5.0 * th + 1.1) \
            + 0.008 * math.cos(7.0 * th)
        r = math.hypot(x, y) * k
        rr = max(r - inset, 0.01) / max(r, 1e-6)
        pts.append((x * k * rr, TURF_CY + y * k * rr))
    return pts


def add_turf(bm):
    rings = []
    for inset, z in ((0.020, 0.0), (0.004, 0.010), (0.0, TURF_TOP - 0.014), (0.012, TURF_TOP)):
        rings.append([bm.verts.new((x, y, z)) for x, y in turf_outline(inset)])
    n = TURF_SEGS
    for j, (r0, r1) in enumerate(zip(rings, rings[1:])):
        for k in range(n):
            m = (k + 1) % n
            f = bm.faces.new((r0[k], r0[m], r1[m], r1[k]))
            f.material_index = GRASS_IDX if j == 2 else SOIL_IDX
    bm.faces.new(tuple(reversed(rings[0]))).material_index = SOIL_IDX
    bm.faces.new(tuple(rings[-1])).material_index = GRASS_IDX


def tuft_sites():
    """Tuft centres: tucked against the feet, the quiver and the half arrow,
    then scattered over the patch clear of every footprint."""
    rng = random.Random(TUFT_SEED)
    y_lb = bpt(LEG_A, B_LEG_BOT, W_LC).y
    fb = Q0 + DR * (T_BOT + FER_DOWN)
    keep = []
    for side in (-1.0, 1.0):
        a = side * LEG_A
        keep += [(a + side * 0.070, y_lb - 0.20), (a - side * 0.075, y_lb - 0.05),
                 (a + side * 0.068, y_lb + 0.16), (a, y_lb - SKID_FRONT - 0.05)]
    keep += [(fb.x + 0.075, fb.y), (fb.x - 0.07, fb.y + 0.05), (fb.x, fb.y - 0.08)]
    keep += [(QUIVER[0] - 0.07, QUIVER[1] + 0.09), (QUIVER[0] + 0.12, QUIVER[1] - 0.14),
             (HALF_ARROW[0] + 0.05, HALF_ARROW[1] + 0.07), (HALF_ARROW[0] - 0.20, HALF_ARROW[1] - 0.05)]

    def clear(x, y):
        for side in (-1.0, 1.0):
            if abs(x - side * LEG_A) < SKID_HW + 0.03 and y_lb - SKID_FRONT - 0.03 < y < y_lb + SKID_BACK + 0.03:
                return False
        if abs(x - fb.x) < TREAD_HX + 0.03 and abs(y - fb.y) < TREAD_HY + 0.04:
            return False
        if math.hypot(x - QUIVER[0], y - QUIVER[1]) < 0.30:
            return False
        if math.hypot(x - HALF_ARROW[0], y - HALF_ARROW[1]) < 0.26:
            return False
        if abs(x) < 0.12 and 0.2 < y < fb.y:
            return False
        return True

    sites = [p for p in keep if clear(*p)]
    tries = 0
    while len(sites) < 62 and tries < 6000:
        tries += 1
        u, v = rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)
        if u * u * u * u + v * v * v * v > 0.62:
            continue
        x, y = u * TURF_HX, TURF_CY + v * TURF_HY
        if clear(x, y) and all(math.hypot(x - p[0], y - p[1]) > 0.10 for p in sites):
            sites.append((x, y))
    return sites


def add_tufts(bm):
    rng = random.Random(TUFT_SEED + 1)
    for cx, cy in tuft_sites():
        for _b in range(rng.randint(7, 11)):
            bx = cx + rng.uniform(-0.026, 0.026)
            by = cy + rng.uniform(-0.026, 0.026)
            h = rng.uniform(0.050, 0.120)
            az = rng.uniform(0.0, 2.0 * math.pi)
            lean = math.radians(rng.uniform(8.0, 38.0))
            yaw = rng.uniform(0.0, 2.0 * math.pi)
            ld = Vector((math.cos(az), math.sin(az), 0.0))
            wv = Vector((math.cos(yaw), math.sin(yaw), 0.0))
            tv = ZAX.cross(wv)
            w, t = rng.uniform(0.0030, 0.0048), 0.0011

            def ring(z, sc, off):
                c = Vector((bx, by, z)) + ld * off
                return [bm.verts.new(c + wv * (sc * w * 0.5)), bm.verts.new(c + tv * (sc * t)),
                        bm.verts.new(c - wv * (sc * w * 0.5))]

            bot = bm.verts.new((bx, by, TURF_TOP - 0.008))
            r0 = ring(TURF_TOP - 0.0025 - rng.uniform(0.0, 0.002), 1.0, 0.0)
            r1 = ring(TURF_TOP + 0.5 * h * math.cos(0.5 * lean), 0.8, 0.5 * h * math.sin(0.5 * lean) * 0.6)
            tip = bm.verts.new(Vector((bx, by, TURF_TOP + h * math.cos(lean))) + ld * (h * math.sin(lean)))
            faces = []
            for k in range(3):
                m = (k + 1) % 3
                faces.append(bm.faces.new((bot, r0[m], r0[k])))
                faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
                faces.append(bm.faces.new((r1[k], r1[m], tip)))
            _mark(faces, GRASS_IDX)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def set_grain(me, C):
    """Face attributes for the grain shaders: straw fibres run round the
    coil (tangent to the boss's circles), each rope course its own tone;
    every timber member takes its own long axis and tone."""
    groups = shells(me)
    polys = shell_polys(me, groups)
    tone = [0.5] * len(me.polygons)
    grain = [(0.0, 0.0, 1.0)] * len(me.polygons)
    rng = random.Random(TONE_SEED)
    for g, ps in zip(groups, polys):
        if not ps:
            continue
        mats = {}
        for p in ps:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
        dom = max(mats, key=mats.get)
        if dom == TIMBER_IDX:
            pts = [me.vertices[i].co for i in g]
            _c, ax = pca_axis(pts)
            t = 0.5 + rng.uniform(-0.16, 0.16)
            for p in ps:
                tone[p.index] = t
                grain[p.index] = tuple(ax)
        elif dom == LEATHER_IDX:
            # the quiver body is tan; its bands and belt loop darker hide
            t = 0.55 if len(g) > 300 else 0.12
            for p in ps:
                tone[p.index] = t
        elif dom == STRAW_IDX:
            for p in ps:
                d = p.center - C
                w = d.dot(NV)
                r = (d - NV * w).length
                tone[p.index] = 0.5 + 0.34 * (hashf(math.floor((r - w + 1.0) / COURSE_P)) - 0.5)
    a = me.attributes.new("PlankTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)
    b = me.attributes.new("GrainDir", "FLOAT_VECTOR", "FACE")
    b.data.foreach_set("vector", [c for v in grain for c in v])
    # Straw fibres run round the coil: a continuous per-vertex coordinate
    # (cos, sin of the angle round the boss axis, and distance along the
    # section) that the straw shader stretches round the circle, seam-free.
    coil = []
    for v in me.vertices:
        d = v.co - C
        w = d.dot(NV)
        rad = d - NV * w
        r = rad.length
        phi = math.atan2(rad.dot(UVEC), rad.dot(XV)) if r > 1e-9 else 0.0
        coil.extend((math.cos(phi), math.sin(phi), r - w))
    c = me.attributes.new("CoilCoord", "FLOAT_VECTOR", "POINT")
    c.data.foreach_set("vector", coil)


def build_target_mesh(name, bevel_offset, bevel_segments, float_foot=False, offset_hinge=False,
                      lift_boss=False, high_boss=False, shallow_arrow=False, short_arrow=False,
                      skew_vane=False, wide_gold=False, short_skids=False, loose_pin=False):
    bm = bmesh.new()
    try:
        bevel_verts = []
        boss_shift = LIFT_BOSS if lift_boss else (HIGH_BOSS if high_boss else 0.0)
        C = C0 + UVEC * boss_shift
        add_turf(bm)
        add_boss(bm, C)
        add_face(bm, C, wide_gold, LOOSE_PIN if loose_pin else 0.0)
        add_boss_arrows(bm, C, shallow_arrow, short_arrow, skew_vane)
        add_stand(bm, bevel_verts, HIGH_BOSS if high_boss else 0.0, float_foot, offset_hinge,
                  short_skids)
        add_half_arrow(bm)
        add_quiver(bm)
        add_tufts(bm)

        if bevel_offset > 0.0:
            bm.edges.index_update()
            edges = sorted(
                {e for v in bevel_verts if v.is_valid for e in v.link_edges
                 if len(e.link_faces) == 2
                 and all(f.material_index == TIMBER_IDX for f in e.link_faces)
                 and e.calc_face_angle() > math.radians(60.0)},
                key=lambda e: e.index,
            )
            if edges:
                bmesh.ops.bevel(bm, geom=edges, offset=bevel_offset, segments=bevel_segments,
                                profile=0.5, affect="EDGES", clamp_overlap=True,
                                material=TIMBER_IDX)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(35.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    set_grain(me, C)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def principled(name, color, metallic, roughness, roughness_var=0.0, mottle=0.0,
               noise_scale=14.0, coat=0.0, bump=0.0, bump_scale=400.0):
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
    coord = None
    if roughness_var > 0.0 or mottle > 0.0 or bump > 0.0:
        coord = nt.nodes.new("ShaderNodeTexCoord")
    if roughness_var > 0.0 or mottle > 0.0:
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
    if bump > 0.0:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = bump_scale
        tex.inputs["Detail"].default_value = 2.0
        nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
        bnode = nt.nodes.new("ShaderNodeBump")
        bnode.name = "SurfBump"
        bnode.inputs["Strength"].default_value = bump
        bnode.inputs["Distance"].default_value = 0.0004
        nt.links.new(tex.outputs["Fac"], bnode.inputs["Height"])
        nt.links.new(bnode.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def tone_by_attribute(mat, gain=(1.2, 0.4)):
    """Multiply the material's base colour by ``PlankTone`` (a per-shell tone)."""
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    sock = bsdf.inputs["Base Color"]
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "PlankTone"
    g = nt.nodes.new("ShaderNodeMath")
    g.operation = "MULTIPLY_ADD"
    g.inputs[1].default_value = gain[0]
    g.inputs[2].default_value = gain[1]
    nt.links.new(tone.outputs["Fac"], g.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    if sock.is_linked:
        nt.links.new(sock.links[0].from_socket, _sock(mix.inputs, "A_Color"))
    else:
        _sock(mix.inputs, "A_Color").default_value = sock.default_value
    nt.links.new(g.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), sock)
    return mat


def _sock(sockets, identifier):
    """A Mix-node socket by identifier; its A/B/Result names repeat per type."""
    return next(sk for sk in sockets if sk.identifier == identifier)


def grain_material(name, dark, light, scale, squash, rough_lo, rough_hi, bump, gain=(1.1, 0.45),
                   detail=6.0):
    """Noise stretched along each face's ``GrainDir`` and toned by its
    ``PlankTone`` (copied from showcase/anvil's wood material): wood grain
    along a member, straw fibres round the coil."""
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
    sq = nt.nodes.new("ShaderNodeMath")
    sq.operation = "MULTIPLY"
    sq.inputs[1].default_value = squash
    nt.links.new(dot.outputs["Value"], sq.inputs[0])
    along = nt.nodes.new("ShaderNodeVectorMath")
    along.operation = "SCALE"
    nt.links.new(gdir.outputs["Vector"], along.inputs[0])
    nt.links.new(sq.outputs["Value"], along.inputs["Scale"])
    gco = nt.nodes.new("ShaderNodeVectorMath")
    gco.operation = "SUBTRACT"
    nt.links.new(coord.outputs["Object"], gco.inputs[0])
    nt.links.new(along.outputs["Vector"], gco.inputs[1])
    shift = nt.nodes.new("ShaderNodeVectorMath")
    shift.operation = "ADD"
    nt.links.new(gco.outputs["Vector"], shift.inputs[0])
    nt.links.new(tone.outputs["Fac"], shift.inputs[1])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    noise.inputs["Roughness"].default_value = 0.62
    nt.links.new(shift.outputs["Vector"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = light
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    g = nt.nodes.new("ShaderNodeMath")
    g.operation = "MULTIPLY_ADD"
    g.inputs[1].default_value = gain[0]
    g.inputs[2].default_value = gain[1]
    nt.links.new(tone.outputs["Fac"], g.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(ramp.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(g.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = rough_hi
    rough.inputs["To Max"].default_value = rough_lo
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    bnode = nt.nodes.new("ShaderNodeBump")
    bnode.name = "SurfBump"
    bnode.inputs["Strength"].default_value = bump
    bnode.inputs["Distance"].default_value = 0.0006
    nt.links.new(noise.outputs["Fac"], bnode.inputs["Height"])
    nt.links.new(bnode.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def straw_material():
    """Golden straw: fibres streaked round the coil from ``CoilCoord`` (few
    features round the circle, many across the section), toned per rope
    course by ``PlankTone``, with a fibre bump."""
    mat = bpy.data.materials.new("BossStraw")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "CoilCoord"
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "PlankTone"
    scale = nt.nodes.new("ShaderNodeVectorMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = (0.9, 0.9, 38.0)
    nt.links.new(attr.outputs["Vector"], scale.inputs[0])
    fib = nt.nodes.new("ShaderNodeTexNoise")
    fib.inputs["Scale"].default_value = 11.0
    fib.inputs["Detail"].default_value = 7.0
    fib.inputs["Roughness"].default_value = 0.65
    nt.links.new(scale.outputs["Vector"], fib.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.32
    ramp.color_ramp.elements[0].color = (0.25, 0.165, 0.060, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.58, 0.44, 0.19, 1.0)
    nt.links.new(fib.outputs["Fac"], ramp.inputs["Fac"])
    g = nt.nodes.new("ShaderNodeMath")
    g.operation = "MULTIPLY_ADD"
    g.inputs[1].default_value = 1.0
    g.inputs[2].default_value = 0.5
    nt.links.new(tone.outputs["Fac"], g.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(ramp.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(g.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.92
    rough.inputs["To Max"].default_value = 0.66
    nt.links.new(fib.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    bnode = nt.nodes.new("ShaderNodeBump")
    bnode.name = "SurfBump"
    bnode.inputs["Strength"].default_value = 0.55
    bnode.inputs["Distance"].default_value = 0.0010
    nt.links.new(fib.outputs["Fac"], bnode.inputs["Height"])
    nt.links.new(bnode.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def carbon_material():
    mat = principled("ArrowCarbon", (0.030, 0.030, 0.034, 1.0), 0.3, 0.32)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    chk = nt.nodes.new("ShaderNodeTexChecker")
    chk.inputs["Scale"].default_value = 900.0
    nt.links.new(coord.outputs["Object"], chk.inputs["Vector"])
    bnode = nt.nodes.new("ShaderNodeBump")
    bnode.name = "SurfBump"
    bnode.inputs["Strength"].default_value = 0.25
    bnode.inputs["Distance"].default_value = 0.0002
    nt.links.new(chk.outputs["Fac"], bnode.inputs["Height"])
    nt.links.new(bnode.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def target_materials():
    """(straw, twine, timber, steel, white, black, blue, red, gold, carbon,
    vane, cock vane, nock, grass, soil, leather): shared by check and render.

    The boss is golden straw with fibres running round the coil and a tone
    per rope course; the bindings darker jute; the easel weathered pine with
    grain along each member; the hardware dark galvanised steel. The face is
    printed paper in slightly aged, muted inks. Shafts are carbon, the vanes
    a muted orange with an off-white cock vane, the nocks and pin heads green
    plastic. The patch is olive turf over dark soil; the quiver brown leather.
    """
    straw = straw_material()
    twine = principled("BossTwine", (0.23, 0.15, 0.070, 1.0), 0.0, 0.85, roughness_var=0.06,
                       mottle=0.30, noise_scale=320.0, bump=0.35, bump_scale=900.0)
    timber = grain_material("StandPine", (0.15, 0.095, 0.050, 1.0), (0.40, 0.28, 0.15, 1.0), 9.0,
                            0.94, 0.55, 0.80, 0.12)
    steel = principled("StandSteel", (0.22, 0.22, 0.23, 1.0), 0.85, 0.48, roughness_var=0.10,
                       mottle=0.30, noise_scale=140.0, bump=0.15, bump_scale=500.0)
    white = principled("FaceWhite", (0.64, 0.62, 0.56, 1.0), 0.0, 0.82, roughness_var=0.05,
                       mottle=0.08, noise_scale=60.0)
    black = principled("FaceBlack", (0.028, 0.028, 0.030, 1.0), 0.0, 0.78, roughness_var=0.05,
                       mottle=0.10, noise_scale=60.0)
    blue = principled("FaceBlue", (0.075, 0.19, 0.34, 1.0), 0.0, 0.80, roughness_var=0.05,
                      mottle=0.10, noise_scale=60.0)
    red = principled("FaceRed", (0.42, 0.075, 0.055, 1.0), 0.0, 0.80, roughness_var=0.05,
                     mottle=0.10, noise_scale=60.0)
    gold = principled("FaceGold", (0.62, 0.46, 0.11, 1.0), 0.0, 0.78, roughness_var=0.05,
                      mottle=0.10, noise_scale=60.0)
    carbon = carbon_material()
    vane = principled("ArrowVane", (0.56, 0.22, 0.060, 1.0), 0.0, 0.42)
    cock = principled("ArrowCockVane", (0.70, 0.69, 0.64, 1.0), 0.0, 0.42)
    nock = principled("ArrowNock", (0.10, 0.34, 0.14, 1.0), 0.0, 0.30)
    grass = principled("TurfGrass", (0.100, 0.125, 0.045, 1.0), 0.0, 0.88, roughness_var=0.05,
                       mottle=0.50, noise_scale=18.0, bump=0.55, bump_scale=240.0)
    soil = principled("TurfSoil", (0.075, 0.050, 0.032, 1.0), 0.0, 0.94, mottle=0.35,
                      noise_scale=40.0, bump=0.3, bump_scale=300.0)
    leather = tone_by_attribute(principled("QuiverLeather", (0.26, 0.12, 0.052, 1.0), 0.0, 0.58,
                                           roughness_var=0.10, mottle=0.28, noise_scale=90.0,
                                           bump=0.22, bump_scale=700.0))
    return (straw, twine, timber, steel, white, black, blue, red, gold, carbon, vane, cock, nock,
            grass, soil, leather)


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


def shell_polys(me, groups):
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(p)
    return polys


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
    return Vector(c), Vector(vecs[:, -1 if largest else 0]).normalized()


def radial(p, c, a):
    d = p - c
    return (d - a * d.dot(a)).length


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    out["turf"] = max((s for s in parts if SOIL_IDX in s.mats), key=lambda s: s.size.x, default=None)
    out["boss"] = max((s for s in parts if s.mat == STRAW_IDX), key=lambda s: s.size.x, default=None)
    out["paper"] = next((s for s in parts if GOLD_IDX in s.mats), None)
    timber = [s for s in parts if s.mat == TIMBER_IDX]
    out["shelf"] = max(timber, key=lambda s: s.size.x, default=None)
    legs = [s for s in timber if s.size.z > 1.5]
    out["front_legs"] = []
    out["rear_legs"] = []
    for s in legs:
        _c, ax = pca_axis(s.pts)
        (out["front_legs"] if abs(ax.dot(UVEC)) > 0.999 else out["rear_legs"]).append(s)
    out["skids"] = [s for s in timber if s.hi.z < 0.15 and s.size.y > 0.2]
    out["treads"] = [s for s in parts if s.mat == STEEL_IDX and CARBON_IDX not in s.mats
                     and s.hi.z < 0.12 and s.size.x > 0.08 and s.size.y > 0.08]
    out["pin"] = next((s for s in parts if s.mat == STEEL_IDX and 0.09 < s.size.x < 0.15
                       and s.size.y < 0.03 and s.size.z < 0.03 and s.mean.z > 1.5), None)
    out["shafts"] = [s for s in parts if CARBON_IDX in s.mats and s.size.length > 0.15]
    out["vanes"] = [s for s in parts if s.mat in (VANE_IDX, COCK_IDX)]
    return out


def hinge_audit(cls):
    pin = cls["pin"]
    if pin is None:
        return {"knuckles": 0, "offs": [9.0]}
    c, a = pca_axis(pin.pts)
    knuckles = [s for s in cls["all"] if s.mat == STEEL_IDX and s is not pin
                and s.size.x < 0.04 and radial(s.mean, c, a) < 0.01
                and abs((s.mean - c).dot(a)) < 0.06 and max(s.size.y, s.size.z) > 0.018]
    return {"knuckles": len(knuckles), "offs": [radial(s.mean, c, a) for s in knuckles]}


def face_frame(cls):
    paper = cls["paper"]
    _c, n = pca_axis(paper.pts, largest=False)
    if n.y > 0.0:
        n = -n
    u = n.cross(XV).normalized()
    return n, u


def seat_audit(cls):
    """Bite of the boss's lowest course into the ledge (along the face's up
    axis) and of its back crests into each front leg (along its normal)."""
    n, u = face_frame(cls)
    boss = cls["boss"]
    shelf = cls["shelf"]
    shelf_top = max(p.dot(u) for p in shelf.pts)
    low = min(boss.pts, key=lambda p: p.dot(u))
    over = (shelf.lo.x < low.x < shelf.hi.x
            and min(p.dot(n) for p in shelf.pts) < low.dot(n) < max(p.dot(n) for p in shelf.pts))
    seat = shelf_top - low.dot(u)
    leans = []
    for leg in cls["front_legs"]:
        lf = max(p.dot(n) for p in leg.pts)
        near = [p.dot(n) for p in boss.pts if leg.lo.x < p.x < leg.hi.x]
        leans.append(lf - min(near) if near else -9.0)
    return {"seat": seat, "over": over, "leans": leans}


def size_audit(cls, turf_top):
    n, u = face_frame(cls)
    paper = cls["paper"]
    boss = cls["boss"]
    pc = paper.mean
    front = [p for p in paper.pts if (p - pc).dot(n) > 0.0]
    fcen = sum(front, Vector()) / len(front)
    bc = boss.mean
    boss_d = 2.0 * max(radial(p, bc, n) for p in boss.pts)
    boss_t = max(p.dot(n) for p in boss.pts) - min(p.dot(n) for p in boss.pts)
    face_d = 2.0 * max(radial(p, pc, n) for p in paper.pts)
    tilt = math.degrees(math.asin(max(-1.0, min(1.0, n.z))))
    return {"gold_h": fcen.z - turf_top, "boss_d": boss_d, "boss_t": boss_t, "face_d": face_d,
            "tilt": tilt}


def arrow_audit(cls):
    """Every shaft: its axis (PCA), and for a pointed one its tip. Arrows
    whose tip is in the boss: depth back along the shaft to where it leaves
    the straw, and straw left ahead of the tip. Every vane: its clearance
    from the boss surface, and its angle round the shaft it is assigned to."""
    boss = cls["boss"]
    bc = boss.mean
    shafts = []
    for s in cls["shafts"]:
        c, a = pca_axis(s.pts)
        steel = [s.pts[i] for p, tri in zip(s.polys, s.tri_idx) if p.material_index == STEEL_IDX
                 for i in tri]
        tip = None
        if steel:
            sm = sum(steel, Vector()) / len(steel)
            if (sm - c).dot(a) < 0.0:
                a = -a
            tip = max(s.pts, key=lambda p: (p - c).dot(a))
        shafts.append((s, c, a, tip))
    depths, aheads = [], []
    for s, c, a, tip in shafts:
        if tip is None or (tip - bc).length > R_BOSS + 0.02:
            continue
        hit = boss.tree.ray_cast(tip, -a)
        depths.append(hit[3] if hit[0] is not None else 0.0)
        fwd = boss.tree.ray_cast(tip, a)
        aheads.append(fwd[3] if fwd[0] is not None else 0.0)
    clears = []
    assign = {}
    for v in cls["vanes"]:
        worst = 9.0
        for p in v.pts:
            loc, nrm, _i, dist = boss.tree.find_nearest(p)
            if loc is None:
                continue
            sd = dist if (p - loc).dot(nrm) >= 0.0 else -dist
            worst = min(worst, sd)
        clears.append(worst)
        best = None
        for k, (s, c, a, _tip) in enumerate(shafts):
            t = (v.mean - c).dot(a)
            if abs(t) > 0.5 * max(s.size.length, 0.01) + 0.02:
                continue
            d = radial(v.mean, c, a)
            if d < 0.03 and (best is None or d < best[0]):
                best = (d, k)
        if best is not None:
            assign.setdefault(best[1], []).append(v)
    spacing = []
    counts = []
    for k, vs in sorted(assign.items()):
        s, c, a, _tip = shafts[k]
        counts.append(len(vs))
        e1 = (ZAX - a * a.dot(ZAX)) if abs(a.z) < 0.9 else (XV - a * a.x)
        e1.normalize()
        e2 = a.cross(e1)
        angs = []
        for v in vs:
            d = v.mean - c
            d = d - a * d.dot(a)
            angs.append(math.degrees(math.atan2(d.dot(e2), d.dot(e1))) % 360.0)
        angs.sort()
        gaps = [(angs[(i + 1) % len(angs)] - angs[i]) % 360.0 for i in range(len(angs))]
        spacing.append(max(abs(g - 120.0) for g in gaps) if len(angs) == 3 else 99.0)
    return {"embedded": len(depths), "depths": depths, "aheads": aheads, "clears": clears,
            "fletched": len(counts), "vane_counts": counts, "spacing": spacing,
            "unassigned": len(cls["vanes"]) - sum(counts)}


def ring_audit(cls):
    """Annuli of the paper's front surface, read off the mesh: each ring
    line's centre radius against the scoring table, and each zone's ink."""
    n, _u = face_frame(cls)
    paper = cls["paper"]
    front = [p for p in paper.pts if (p - paper.mean).dot(n) > 0.0]
    pc = sum(front, Vector()) / len(front)
    annuli = {}
    for poly, tri in zip(paper.polys, paper.tri_idx):
        if poly.normal.dot(n) < 0.999:
            continue
        rs = [radial(paper.pts[i], pc, n) for i in tri]
        key = (round(min(rs), 5), round(max(rs), 5))
        annuli.setdefault(key, set()).add(poly.material_index)
    lines, wrong = [], 0
    for (r0, r1), mats in sorted(annuli.items()):
        w = r1 - r0
        if w < 1e-4:
            continue
        mid = 0.5 * (r0 + r1)
        if len(mats) != 1:
            wrong += 1
            continue
        m = next(iter(mats))
        if w < 0.003:
            lines.append(mid)
            if m != line_mat(mid, ZONE_EDGES):
                wrong += 1
        elif m != zone_mat(mid, ZONE_EDGES):
            wrong += 1
    offs = [abs(a - b) for a, b in zip(sorted(lines), LINE_RADII)] if len(lines) == len(LINE_RADII) \
        else [9.0]
    return {"lines": sorted(lines), "offs": offs, "wrong": wrong}


def shell_mass(s):
    vol = 0.0
    mom = Vector()
    for tri in s.tri_idx:
        a = s.pts[tri[0]]
        for k in range(1, len(tri) - 1):
            b, c = s.pts[tri[k]], s.pts[tri[k + 1]]
            v = a.dot(b.cross(c)) / 6.0
            vol += v
            mom += v * (a + b + c) / 4.0
    return vol, (mom / vol if abs(vol) > 1e-15 else s.mean)


def convex_hull_2d(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def stability_audit(cls, turf_top):
    """Mass centre of boss, face, bindings, stand and hardware (shell volume
    x density) against the convex hull of the supports' contact points:
    its margin inside, and the forward tip angle over the front edge."""
    dens = {STRAW_IDX: DENSITY["straw"], TWINE_IDX: DENSITY["twine"],
            TIMBER_IDX: DENSITY["timber"], STEEL_IDX: DENSITY["steel"]}
    for m in PAPER_IDXS:
        dens[m] = DENSITY["paper"]
    total = 0.0
    mom = Vector()
    for s in cls["all"]:
        if s.mat not in dens:
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * dens[s.mat]
        total += m
        mom += cen * m
    com = mom / total if total else Vector()
    pts = []
    for s in cls["skids"] + cls["treads"]:
        pts += [(round(p.x, 6), round(p.y, 6)) for p in s.pts if p.z < turf_top - 0.0005]
    hull = convex_hull_2d(pts)
    margin, fwd = 9.0, None
    for i in range(len(hull)):
        ax, ay = hull[i]
        bx, by = hull[(i + 1) % len(hull)]
        ex, ey = bx - ax, by - ay
        ln = math.hypot(ex, ey)
        if ln < 1e-9:
            continue
        nx, ny = ey / ln, -ex / ln          # outward for a counter-clockwise hull
        dist = -((com.x - ax) * nx + (com.y - ay) * ny)
        margin = min(margin, dist)
        if fwd is None or ny < fwd[0]:
            fwd = (ny, dist)
    h = com.z - turf_top
    tip = math.degrees(math.atan2(fwd[1], h)) if fwd else 0.0
    return {"mass": total, "com": com, "margin": margin, "fwd": fwd[1] if fwd else 0.0,
            "tip": tip, "hull": len(hull)}


def connected_components(cls):
    parts = cls["all"]
    n = len(parts)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        a = parts[i]
        for j in range(i + 1, n):
            b = parts[j]
            if (a.lo.x > b.hi.x or b.lo.x > a.hi.x or a.lo.y > b.hi.y or b.lo.y > a.hi.y
                    or a.lo.z > b.hi.z or b.lo.z > a.hi.z):
                continue
            if find(i) == find(j):
                continue
            if a.tree.overlap(b.tree):
                parent[find(i)] = find(j)
    roots = {find(i) for i in range(n)}
    sizes = {}
    for i in range(n):
        sizes[find(i)] = sizes.get(find(i), 0) + 1
    return len(roots), sorted(sizes.values())


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        # inside the envelope, so only the hygiene budget can see it
        bm.verts.new((0.0, 0.3, 1.0))
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
    img = bpy.data.images.new("TargetNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = TIMBER_IDX
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


FLOOR_NAMES = ("straw", "twine", "timber", "steel", "white", "black", "blue", "red", "gold",
               "carbon", "vane", "cock vane", "nock", "grass", "soil", "leather")


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_target_mesh("TargetLow", bevel_offset=0.0015, bevel_segments=1, **flags)
    high = build_target_mesh("TargetHigh", bevel_offset=0.0015, bevel_segments=3, **flags)
    mats = target_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the pine: the gussets are where the high mesh's
    # rounder chamfer differs from the low.
    target = mats[TIMBER_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("target mesh did not build", 3),) + none3

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
    turf_top = max(p.z for p in cls["turf"].pts) if cls["turf"] else 9.0
    sup = [turf_top - s.lo.z for s in cls["skids"] + cls["treads"]]
    hinge = hinge_audit(cls)
    ok_face = cls["paper"] is not None and cls["boss"] is not None and cls["shelf"] is not None
    seat = seat_audit(cls) if ok_face else {"seat": -9.0, "over": False, "leans": []}
    size = size_audit(cls, turf_top) if ok_face else None
    arrows = arrow_audit(cls) if cls["boss"] else None
    rings = ring_audit(cls) if cls["paper"] else {"lines": [], "offs": [9.0], "wrong": 99}
    stab = stability_audit(cls, turf_top)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("target has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "TargetLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "TargetLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_target_mesh("TargetColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "TargetCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_archery_target_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} turf_top={turf_top:.4f} "
          f"supports={[round(b, 5) for b in sup]}")
    print(f"measured hinge knuckles={hinge['knuckles']} off={[round(o, 6) for o in hinge['offs']]}")
    print(f"measured seat={seat['seat']:.5f} over={seat['over']} "
          f"leans={[round(x, 5) for x in seat['leans']]}")
    if size:
        print(f"measured gold_h={size['gold_h']:.4f} boss_d={size['boss_d']:.4f} "
              f"boss_t={size['boss_t']:.4f} face_d={size['face_d']:.4f} tilt={size['tilt']:.3f}")
    if arrows:
        print(f"measured embedded={arrows['embedded']} depths={[round(d, 4) for d in arrows['depths']]} "
              f"ahead={[round(d, 4) for d in arrows['aheads']]}")
        print(f"measured vanes={len(cls['vanes'])} clear_min={min(arrows['clears'], default=9.0):.4f} "
              f"fletched={arrows['fletched']} counts={arrows['vane_counts']} "
              f"unassigned={arrows['unassigned']} spacing_max={max(arrows['spacing'], default=99):.4f}")
    print(f"measured rings lines={[round(x, 5) for x in rings['lines']]} "
          f"off_max={max(rings['offs']):.6f} wrong={rings['wrong']}")
    print(f"measured mass={stab['mass']:.2f}kg com=({stab['com'].x:.4f},{stab['com'].y:.4f},"
          f"{stab['com'].z:.4f}) hull={stab['hull']} margin={stab['margin']:.4f} "
          f"fwd={stab['fwd']:.4f} tip={stab['tip']:.3f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    for idx, (floor, label) in enumerate(zip(FACE_FLOORS, FLOOR_NAMES)):
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
    if len(sup) != SUPPORT_COUNT or any(not (SUPPORT_BITE_MIN <= b <= SUPPORT_BITE_MAX) for b in sup):
        return (fail(f"supports: {len(sup)} (want {SUPPORT_COUNT}: two skids and the rear tread), "
                     f"bedded {[round(b, 5) for b in sup]} m into the turf (band "
                     f"{SUPPORT_BITE_MIN}-{SUPPORT_BITE_MAX})", 16),) + none3
    if hinge["knuckles"] != KNUCKLE_COUNT or max(hinge["offs"], default=9.0) > HINGE_AXIS_TOL:
        return (fail(f"hinge: {hinge['knuckles']} knuckles (want {KNUCKLE_COUNT}), off the pin axis "
                     f"{[round(o, 6) for o in hinge['offs']]} m (tol {HINGE_AXIS_TOL})", 17),) + none3
    if (not seat["over"] or not (SEAT_MIN <= seat["seat"] <= SEAT_MAX) or len(seat["leans"]) != 2
            or any(not (LEAN_MIN <= x <= LEAN_MAX) for x in seat["leans"])):
        return (fail(f"boss not resting on its ledge: seat {seat['seat']:.5f} m (band {SEAT_MIN}-"
                     f"{SEAT_MAX}, over the ledge {seat['over']}), leaning on the legs "
                     f"{[round(x, 5) for x in seat['leans']]} (band {LEAN_MIN}-{LEAN_MAX})", 18),) + none3
    if (abs(size["gold_h"] - GOLD_H) > GOLD_TOL or abs(size["boss_d"] - BOSS_D) > SIZE_TOL
            or abs(size["boss_t"] - BOSS_T) > SIZE_TOL or abs(size["face_d"] - FACE_D) > FACE_TOL
            or not (TILT_MIN <= size["tilt"] <= TILT_MAX)):
        return (fail(f"regulation: gold centre {size['gold_h']:.4f} m above the turf (want {GOLD_H} "
                     f"+- {GOLD_TOL}), boss {size['boss_d']:.4f} x {size['boss_t']:.4f} m, face "
                     f"{size['face_d']:.4f} m, tilt {size['tilt']:.3f} deg", 19),) + none3
    if (arrows["embedded"] != EMBEDDED_COUNT
            or any(not (DEPTH_MIN <= d <= DEPTH_MAX) for d in arrows["depths"])
            or any(x < AHEAD_MIN for x in arrows["aheads"])):
        return (fail(f"arrow points: {arrows['embedded']} in the boss (want {EMBEDDED_COUNT}), buried "
                     f"{[round(d, 4) for d in arrows['depths']]} m (band {DEPTH_MIN}-{DEPTH_MAX}), "
                     f"straw ahead {[round(d, 4) for d in arrows['aheads']]} (min {AHEAD_MIN})",
                     20),) + none3
    if min(arrows["clears"], default=-9.0) < VANE_CLEAR_MIN:
        return (fail(f"fletching: a vane {min(arrows['clears']):.4f} m from the boss surface "
                     f"(min {VANE_CLEAR_MIN})", 21),) + none3
    if (arrows["fletched"] != FLETCHED_COUNT or arrows["unassigned"]
            or any(c != 3 for c in arrows["vane_counts"])
            or max(arrows["spacing"], default=99.0) > VANE_ANG_TOL):
        return (fail(f"vanes: {arrows['fletched']} fletched shafts (want {FLETCHED_COUNT}), counts "
                     f"{arrows['vane_counts']}, {arrows['unassigned']} unassigned, spacing off 120 "
                     f"by {max(arrows['spacing'], default=99.0):.3f} deg (tol {VANE_ANG_TOL})",
                     22),) + none3
    if rings["wrong"] or max(rings["offs"]) > RING_TOL:
        return (fail(f"scoring rings: lines at {[round(x, 4) for x in rings['lines']]} m (table "
                     f"{list(LINE_RADII)}, tol {RING_TOL}), {rings['wrong']} zones in the wrong ink",
                     23),) + none3
    if stab["margin"] <= 0.0 or stab["tip"] < TIP_FWD_MIN_DEG:
        return (fail(f"stability: mass centre {stab['margin']:.4f} m inside the supports, forward "
                     f"tip angle {stab['tip']:.2f} deg (min {TIP_FWD_MIN_DEG})", 24),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components (want 1) {comp_sizes}", 25),) + none3
    return 0, low, target, tex


def wire_normal(mat, tex):
    nt = mat.node_tree
    bnode = nt.nodes.get("SurfBump")
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    if bnode is not None:
        nt.links.new(nrm.outputs["Normal"], bnode.inputs["Normal"])
    else:
        nt.links.new(nrm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])


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

    # The house rig scaled to a 2 m target: warm key upper left, cool fill
    # low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-2.8, -3.2, 2.6), 192.0, 1.9, (1.0, 0.93, 0.84), spread=35.0)
    light("Fill", (3.4, -2.6, 0.4), 30.0, 3.6, (0.72, 0.82, 1.0))
    light("Rim", (-1.5, 2.2, 1.8), 120.0, 1.6, (0.62, 0.78, 1.0))
    light("Wedge", (1.7, 2.4, 0.4), 185.0, 2.5, (1.0, 0.68, 0.38),
          target=(centre.x + 2.3, centre.y + WALL_Y, 0.9))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.45, -0.89, 0.0)).normalized()
    cam.location = centre + view * 7.2 + Vector((0.0, 0.0, 0.95))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.10))
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
    # Standard, not AgX: AgX washes the face's inks toward pastel
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 26
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return fail("render produced no file", 14)
    return 0


FLAGS = ("float_foot", "offset_hinge", "lift_boss", "high_boss", "shallow_arrow", "short_arrow",
         "skew_vane", "wide_gold", "short_skids", "loose_pin")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--float-foot", action="store_true")
    p.add_argument("--offset-hinge", action="store_true")
    p.add_argument("--lift-boss", action="store_true")
    p.add_argument("--high-boss", action="store_true")
    p.add_argument("--shallow-arrow", action="store_true")
    p.add_argument("--short-arrow", action="store_true")
    p.add_argument("--skew-vane", action="store_true")
    p.add_argument("--wide-gold", action="store_true")
    p.add_argument("--short-skids", action="store_true")
    p.add_argument("--loose-pin", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        **{f: getattr(args, f) for f in FLAGS},
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("archery-target OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
