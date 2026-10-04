"""Game-ready bowling pin deck — a showcase piece, not an example.

Asserts budget conformance of a procedural section of a ten-pin bowling
lane (the pin deck end, with its ten pins racked and a ball on the
approach) after composing shipped pipeline pieces: bmesh construction, an
exact Boolean, UVs, eleven materials, high-to-low normal bake, LOD chain,
convex collider, Unity glTF export.

The lane is one laminated slab of 39 maple boards, 41.5 in across, each
board's top edges chamfered into a V seam, crossed by a joint where the
approach meets the dark pin deck. Ten pin spots are inlaid in the deck on a
12 in equilateral triangle, the head spot 34 3/16 in from the pit edge. A
row of seven targeting arrows and ten range dots are inlaid at the near end.
Two gutters with a channel profile run the whole length; low cappings line
them on the approach and two kickbacks with sloped noses and aluminium caps
stand beside the deck; a steel bullnose finishes the pit edge. Five sleepers
carry it all.

Every pin is lathe-turned from the regulation profile table below (15 in
tall, 4.766 in belly), white with two red neck stripes and a crown band, and
stands on its spot. The ball is an 8.5 in sphere drilled by an exact Boolean
with a thumb hole and two finger holes, each countersunk at its rim, and
rests on the approach.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--float-sleeper`` every sleeper on the floor,
``--offset-pin`` every pin centred on its spot, ``--float-pin`` every pin
seated on the deck, ``--lean-pin`` every pin plumb, ``--wide-rack`` the
spots on an exact 12 in lattice, ``--fat-neck`` the turned profile,
``--float-ball`` the ball resting on the lane, ``--shallow-holes`` the
finger holes' depth, ``--proud-board`` the boards flush and parallel,
``--lift-arrows`` one connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts are
not byte-identical across Blender versions — the LOD gate is a ratio band,
not an exact count.

    blender --background --python bowling_pins.py --
    blender --background --python bowling_pins.py -- --skip-decimate
    blender --background --python bowling_pins.py -- --output pins.png
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

IN = 0.0254
# --- Lane (x across, y down the lane toward the pit, z up) --------------------
BOARD_N = 39
LANE_W = 41.5 * IN
LANE_HALF = 0.5 * LANE_W
BOARD_W = LANE_W / BOARD_N
SEAM_C = 0.0006             # each board's top edge chamfer, into a V seam
SEAM_G = 0.0006             # seam depth
EDGE_C = 0.0015             # the lane's outer long edges
JOINT_C = 0.0015            # approach / pin-deck joint
JOINT_G = 0.0008
SLEEPER_H = 0.050
LANE_BITE = 0.0005          # the lane bites its sleepers
LANE_Z0 = SLEEPER_H - LANE_BITE
LANE_T = 2.75 * IN
LANE_TOP = LANE_Z0 + LANE_T
Y_NEAR = -1.40              # near (approach) end of the section
DECK_Y = -0.16              # approach / pin-deck joint
PIN_S = 12.0 * IN           # pin spot pitch
ROW_H = PIN_S * math.sqrt(3.0) / 2.0
Y_PIT = 34.1875 * IN        # head spot to pit edge
# --- Inlays ----------------------------------------------------------------------
INLAY_PROUD = 0.00025
INLAY_BITE = 0.0005
SPOT_R = 1.125 * IN
SPOT_BITE = 0.0010
ARROW_BOARDS = (4, 9, 14, 19, 24, 29, 34)        # boards 5, 10 ... 35 counted from 1
ARROW_Y = -0.98             # base of the centre arrow; each pair out steps back
ARROW_STEP = 0.07
ARROW_L = 0.14
ARROW_W = 0.022
DOT_BOARDS = (2, 4, 7, 10, 13, 25, 28, 31, 34, 36)
DOT_Y = -1.30
DOT_R = 0.0095
DOT_STEP = 0.00013          # neighbouring dots on their own planes
# --- Gutters, cappings, kickbacks, pit edge -----------------------------------------
GUT_W = 9.25 * IN
GUT_XI = LANE_HALF - 0.0005             # the gutter bites the lane's side
GUT_XO = LANE_HALF + GUT_W
GUT_LIP = LANE_TOP - 0.0025
GUT_DEPTH = 1.875 * IN
GUT_Z0 = SLEEPER_H - 0.0008
CAP_XI = GUT_XO - 0.00045
CAP_XO = 0.803
CAP_TOP = LANE_TOP + 0.050
CAP_Z0 = SLEEPER_H - 0.0014
KB_XI = GUT_XO - 0.00085
KB_T = 0.0458
KB_Y0 = -0.45
KB_Y1 = Y_PIT + 0.030
KB_Z0 = SLEEPER_H - 0.0011
KB_ZF = LANE_TOP + 0.060                # top of the nose's vertical front
KB_ZT = LANE_TOP + 0.400
KB_NOSE = 0.300
KP_H = 0.140               # phenolic kick plate on each kickback's inner face
KP_T = 0.004
NOSE_Y1 = Y_PIT + 0.010                 # pit-edge bullnose, behind the deck
SLEEPER_X = 0.820
SLEEPER_HY = 0.045
SLEEPER_N = 5
# --- Pins --------------------------------------------------------------------------
# The regulation pin profile, (height, diameter) in inches from the base.
PIN_TABLE = (
    (0.000, 2.031), (0.750, 2.828), (2.250, 3.906), (3.375, 4.510), (4.500, 4.766),
    (5.875, 4.563), (7.250, 3.703), (8.625, 2.472), (9.375, 1.965), (10.000, 1.797),
    (10.875, 1.870), (11.750, 2.094), (12.625, 2.406), (13.500, 2.547), (14.375, 2.094),
)
PIN_H = 15.0 * IN
PIN_BELLY = 4.766 * IN
NECK_STATION = 9            # PIN_TABLE index of the neck (10 in)
PIN_TOP_R = 0.09 * IN
PIN_SEGS = 32
PIN_STEP = 0.48 * IN
STRIPES = ((9.45, 9.80), (10.30, 10.65))
CROWN = (11.95, 12.05, 12.45)           # base line, then a row of teeth
PIN_BITE = 0.0006           # each pin's base below the deck face (inside its spot)
# --- Ball --------------------------------------------------------------------------
BALL_D = 8.5 * IN
BALL_R = 0.5 * BALL_D
BALL_BITE = 0.0006
BALL_XY = (-0.110, -0.780)
BALL_SEGS = (48, 32)
GRIP_TILT = 52.0            # the grip turned up toward the bowler, degrees
GRIP_YAW = 15.0
THUMB_R = 0.5 * 1.000 * IN
FINGER_R = 0.5 * 0.800 * IN
THUMB_D = 2.50 * IN
FINGER_D = 2.00 * IN
SPAN = 4.40 * IN            # thumb to finger centres, along the surface
BRIDGE = 1.05 * IN          # finger to finger centres, along the surface
HOLE_BEVEL = 0.0015
HOLE_SEGS = 24

# --- Falsifier sizes ---------------------------------------------------------------
FLOAT_SLEEPER = 0.003
OFFSET_PIN = 0.006
FLOAT_PIN = 0.003
LEAN_PIN_DEG = 1.5
WIDE_RACK = 1.03
FAT_NECK = 0.0015
FLOAT_BALL = 0.004
SHALLOW_D = 0.030
PROUD_BOARD = 0.0012
PROUD_BOARD_IDX = 17
LIFT_ARROWS = 0.001

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (1.640, 2.301, 0.523)
BASE_TRIS_MIN = 36400
BASE_TRIS_MAX = 37700
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 11
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 300
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
# face floors per slot, in slot order (maple, deck, pin white, pin red, ball,
# bore, gutter, kickback, metal, inlay, sleeper)
FACE_FLOORS = (330, 330, 12800, 1190, 1450, 480, 235, 130, 160, 1110, 350)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Pins on their spots, seated and plumb, turned to the table.
PIN_COUNT = 10
SPOT_COUNT = 10
PIN_CENTRE_TOL = 0.0005
PIN_SEAT_MIN = 0.0003
PIN_SEAT_MAX = 0.0010
TILT_MAX_DEG = 0.05
SIZE_TOL = 0.0005
PROFILE_TOL = 0.0002
PROFILE_BAND = 0.00005      # a vertex belongs to a station within this, axially
# The spot lattice.
LATTICE_TOL = 0.0005
LATTICE_EDGES = 18
ROW_SIZES = (1, 2, 3, 4)
# Ball: resting on the lane at its radius, drilled to span.
BALL_REST_MIN = -0.0009
BALL_REST_MAX = -0.0003
BALL_D_TOL = 0.0003
HOLE_COUNT = 3
THUMB_DEPTH_BAND = (0.058, 0.068)
FINGER_DEPTH_BAND = (0.046, 0.056)
BORE_TOL = 0.0003
SPAN_TOL = 0.002
BRIDGE_TOL = 0.001
# Boards flush and parallel.
BOARD_FLUSH_MAX = 0.0002
BOARD_PARALLEL_MAX = 0.0001
BOARD_PITCH_TOL = 0.0001
COMPONENTS = 1
# Hero: the lane square to the wall; the camera looks down it from the approach.
HERO_YAW_DEG = 0.0
WALL_Y = 2.2
# The camera stands behind the approach, 15 degrees off the lane's axis:
# between the rack's 0 and 30 degree lines, so no pin hides behind another.
CAM_VIEW = (0.259, -0.966)  # from the aim, in plan
CAM_DIST = 3.75
CAM_RISE = 1.15
AIM_OFF = (-0.10, -0.14, -0.13)

MAPLE_IDX = 0
DECK_IDX = 1
PIN_WHITE_IDX = 2
PIN_RED_IDX = 3
BALL_IDX = 4
BORE_IDX = 5
GUTTER_IDX = 6
KICKBACK_IDX = 7
METAL_IDX = 8
INLAY_IDX = 9
SLEEPER_IDX = 10
LANE_IDXS = (MAPLE_IDX, DECK_IDX)
PIN_IDXS = (PIN_WHITE_IDX, PIN_RED_IDX)

ZAX = Vector((0.0, 0.0, 1.0))
XAX = Vector((1.0, 0.0, 0.0))
YAX = Vector((0.0, 1.0, 0.0))


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


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False):
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
    faces = []
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for j in range(last):
            k = (j + 1) % n
            faces.append(bm.faces.new((r0[j], r1[j], r1[k], r0[k])))
    if solid:
        faces.append(bm.faces.new([rings[i][0] for i in reversed(range(segs))]))
        faces.append(bm.faces.new([rings[i][n - 1] for i in range(segs)]))
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


def add_sweep(bm, pts, loop, side, mat_idx, voff=0.0):
    """A section loop [(u, v)] swept along a planar polyline, u along
    ``side`` (normal to the path's plane), v in the plane; interior
    stations are mitred. n-gon caps at both ends. One shell."""
    side = Vector(side).normalized()
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rings = []
    for i, p in enumerate(pts):
        if i == 0:
            t, s = (pts[1] - pts[0]).normalized(), 1.0
        elif i == n - 1:
            t, s = (pts[-1] - pts[-2]).normalized(), 1.0
        else:
            t0 = (p - pts[i - 1]).normalized()
            t1 = (pts[i + 1] - p).normalized()
            t = (t0 + t1).normalized()
            s = 1.0 / max(t0.dot(t), 0.2)
        nrm = side.cross(t).normalized()
        rings.append([bm.verts.new(p + side * u + nrm * ((v + voff) * s)) for u, v in loop])
    m = len(loop)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(m):
            q = (k + 1) % m
            faces.append(bm.faces.new((r0[k], r0[q], r1[q], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


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


# --------------------------------------------------------------------------
# Lane: one laminated slab of boards, V-seamed, with the deck joint
# --------------------------------------------------------------------------

def lane_section(proud_board=None):
    """Closed (x, z) section of the lane and the indices of its top points
    (board tops and seam roots), which the deck joint lowers."""
    H, zt, zb = LANE_HALF, LANE_TOP, LANE_Z0
    pts = [(-H, zb), (-H, zt - EDGE_C)]
    top = set()
    for i in range(BOARD_N):
        x0 = -H + i * BOARD_W
        x1 = x0 + BOARD_W
        dz = PROUD_BOARD if proud_board == i else 0.0
        left = x0 + (EDGE_C if i == 0 else SEAM_C)
        right = x1 - (EDGE_C if i == BOARD_N - 1 else SEAM_C)
        top.add(len(pts))
        pts.append((left, zt + dz))
        top.add(len(pts))
        pts.append((right, zt + dz))
        if i < BOARD_N - 1:
            top.add(len(pts))
            pts.append((x1, zt - SEAM_G))
    pts += [(H, zt - EDGE_C), (H, zb)]
    return pts, top


def add_lane(bm, proud_board):
    sec, top = lane_section(proud_board)
    ys = (Y_NEAR, DECK_Y - JOINT_C, DECK_Y, DECK_Y + JOINT_C, Y_PIT)
    rings = []
    for k, y in enumerate(ys):
        ring = []
        for j, (x, z) in enumerate(sec):
            if k == 2 and j in top:
                z = min(z, LANE_TOP - JOINT_G)
            ring.append(bm.verts.new((x, y, z)))
        rings.append(ring)
    n = len(sec)
    for k in range(len(ys) - 1):
        mat = MAPLE_IDX if k < 2 else DECK_IDX
        for j in range(n):
            m = (j + 1) % n
            bm.faces.new((rings[k][j], rings[k][m], rings[k + 1][m],
                          rings[k + 1][j])).material_index = mat
    bm.faces.new(tuple(reversed(rings[0]))).material_index = MAPLE_IDX
    bm.faces.new(tuple(rings[-1])).material_index = DECK_IDX


def spot_centres(wide):
    """The ten pin spots, head pin first, rows back toward the pit."""
    s = PIN_S * (WIDE_RACK if wide else 1.0)
    h = s * math.sqrt(3.0) / 2.0
    out = []
    for row in range(4):
        for k in range(row + 1):
            out.append(Vector(((k - 0.5 * row) * s, row * h, 0.0)))
    return out


def add_disc(bm, x, y, r, z0, z1, segs, mat_idx):
    add_lathe(bm, [(r, z0), (r, z1)], segs, mat_idx, center=(x, y, 0.0), solid=True)


def add_inlays(bm, wide, lift):
    for c in spot_centres(wide):
        add_disc(bm, c.x, c.y, SPOT_R, LANE_TOP - SPOT_BITE, LANE_TOP + INLAY_PROUD, 24, INLAY_IDX)
    z0 = LANE_TOP - INLAY_BITE + lift
    z1 = LANE_TOP + INLAY_PROUD + lift
    for b in ARROW_BOARDS:
        xc = -LANE_HALF + (b + 0.5) * BOARD_W
        step = abs(b - 19) // 5
        y0 = ARROW_Y - ARROW_STEP * step
        # a concave dart; five corners so its caps are n-gons and triangulate
        # on the right diagonal
        dart = [(0.0, ARROW_L), (-0.5 * ARROW_W, 0.0), (0.0, 0.26 * ARROW_L),
                (0.5 * ARROW_W, 0.0), (0.25 * ARROW_W, 0.5 * ARROW_L)]
        add_prism(bm, dart, z0, z1, (xc, y0, 0.0), Matrix.Identity(3), INLAY_IDX)
    for k, b in enumerate(DOT_BOARDS):
        xc = -LANE_HALF + (b + 0.5) * BOARD_W
        dz = DOT_STEP * (k % 2)
        add_disc(bm, xc, DOT_Y, DOT_R, LANE_TOP - INLAY_BITE + dz,
                 LANE_TOP + INLAY_PROUD + dz, 16, INLAY_IDX)


# --------------------------------------------------------------------------
# Gutters, cappings, kickbacks, pit edge, sleepers
# --------------------------------------------------------------------------

def gutter_section():
    """Closed (x, z) section of the right gutter: a solid body whose top is
    the channel, lipped at both edges."""
    lip = 0.008
    xa, xb = GUT_XI + lip, GUT_XO - lip
    xc, a = 0.5 * (xa + xb), 0.5 * (xb - xa)
    arc = []
    n = 18
    for k in range(n + 1):
        t = math.pi * k / n
        arc.append((xc - a * math.cos(t), GUT_LIP - GUT_DEPTH * math.sin(t)))
    pts = [(GUT_XI, GUT_Z0), (GUT_XO, GUT_Z0), (GUT_XO, GUT_LIP - 0.003),
           (GUT_XO - 0.003, GUT_LIP)]
    pts += list(reversed(arc))
    pts += [(GUT_XI + 0.002, GUT_LIP), (GUT_XI, GUT_LIP - 0.002)]
    return pts


def add_gutter(bm, side, bevel_verts):
    sec = gutter_section()
    y0, y1 = Y_NEAR + 0.003, Y_PIT + 0.012
    rings = [[bm.verts.new((side * x, y, z)) for x, z in sec] for y in (y0, y1)]
    n = len(sec)
    faces = [bm.faces.new((rings[0][j], rings[0][(j + 1) % n], rings[1][(j + 1) % n], rings[1][j]))
             for j in range(n)]
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[1])))
    _mark(faces, GUTTER_IDX)
    bevel_verts += rings[0] + rings[1]


def add_capping(bm, side):
    ha = 0.5 * (CAP_XO - CAP_XI)
    hb = 0.5 * (CAP_TOP - CAP_Z0)
    xc = side * 0.5 * (CAP_XI + CAP_XO)
    add_rbox(bm, ha, hb, 0.008, [(0.003, Y_NEAR + 0.006), (0.0, Y_NEAR + 0.009),
                                 (0.0, KB_Y0 + 0.002)],
             (xc, 0.0, CAP_Z0 + hb), frame(YAX, XAX), KICKBACK_IDX, n_corner=3)


def add_kickback(bm, side, bevel_verts):
    xi, xo = KB_XI, KB_XI + KB_T
    w0, w1 = (xi, xo) if side > 0 else (-xo, -xi)
    outline = [(KB_Y0, KB_Z0), (KB_Y1, KB_Z0), (KB_Y1, KB_ZT), (KB_Y0 + KB_NOSE, KB_ZT),
               (KB_Y0, KB_ZF)]
    rot = frame(XAX, YAX)       # local x along y, local y along z, local z along x
    bevel_verts += add_prism(bm, outline, w0, w1, (0.0, 0.0, 0.0), rot, KICKBACK_IDX)
    # aluminium cap over the nose and the top edge, one mitred sweep
    xc = 0.5 * (w0 + w1)
    p0 = Vector((xc, KB_Y0, KB_ZF))
    p1 = Vector((xc, KB_Y0 + KB_NOSE, KB_ZT))
    t0 = (p1 - p0).normalized()
    path = [p0 - t0 * 0.004, p1, Vector((xc, KB_Y1 + 0.003, KB_ZT))]
    loop = rrect(0.5 * KB_T + 0.003, 0.006, 0.003, 3)
    add_sweep(bm, path, loop, XAX, METAL_IDX, voff=-0.002)
    # phenolic kick plate on the inner face, biting it, clear of the gutter
    z0 = LANE_TOP + 0.004
    ya = KB_Y0 + KB_NOSE * (z0 + KP_H - KB_ZF) / (KB_ZT - KB_ZF) + 0.015
    yb = KB_Y1 - 0.010
    xc = side * (KB_XI - 0.5 * KP_T + 0.00025)
    add_rbox(bm, 0.5 * KP_T + 0.00025, 0.5 * KP_H, 0.0015,
             [(0.001, ya), (0.0, ya + 0.001), (0.0, yb - 0.001), (0.001, yb)],
             (xc, 0.0, z0 + 0.5 * KP_H), frame(YAX, XAX), GUTTER_IDX, n_corner=2)


def add_pit_edge(bm, bevel_verts):
    hy = 0.5 * (NOSE_Y1 - (Y_PIT - 0.0006))
    hz = 0.5 * 0.064
    yc = Y_PIT - 0.0006 + hy
    zc = LANE_TOP - 0.0009 - hz
    outline = rrect(hy, hz, 0.005, 4)
    bevel_verts += add_prism(bm, outline, -LANE_HALF + 0.0009, LANE_HALF - 0.0009,
                             (0.0, yc, zc), frame(XAX, YAX), METAL_IDX)


def sleeper_ys():
    y0, y1 = Y_NEAR + 0.08, Y_PIT - 0.08
    return [y0 + (y1 - y0) * k / (SLEEPER_N - 1) for k in range(SLEEPER_N)]


def add_sleepers(bm, float_sleeper):
    hz = 0.5 * SLEEPER_H
    for k, y in enumerate(sleeper_ys()):
        lift = FLOAT_SLEEPER if (float_sleeper and k == 2) else 0.0
        add_rbox(bm, SLEEPER_HY, hz, 0.004, [(0.003, -SLEEPER_X), (0.0, -SLEEPER_X + 0.003),
                                             (0.0, SLEEPER_X - 0.003), (0.003, SLEEPER_X)],
                 (0.0, y, hz + lift), frame(XAX, YAX), SLEEPER_IDX, n_corner=3)


# --------------------------------------------------------------------------
# Pins: lathe-turned from the table
# --------------------------------------------------------------------------

def pchip(xs, ys):
    """Monotone piecewise-cubic interpolant (Fritsch-Carlson): no overshoot at
    the belly or the neck, and it passes every table station exactly."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0.0:
            m[i] = 0.0
        else:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def f(x):
        i = max(0, min(n - 2, next((k for k in range(n - 1) if x <= xs[k + 1]), n - 2)))
        t = (x - xs[i]) / h[i]
        h00 = (1 + 2 * t) * (1 - t) ** 2
        h10 = t * (1 - t) ** 2
        h01 = t * t * (3 - 2 * t)
        h11 = t * t * (t - 1)
        return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]
    return f


def pin_table(fat_neck=False):
    """(z, r) in metres per table station; the fat-neck falsifier fattens
    the neck station alone."""
    out = []
    for k, (hgt, dia) in enumerate(PIN_TABLE):
        r = 0.5 * dia * IN + (FAT_NECK if (fat_neck and k == NECK_STATION) else 0.0)
        out.append((hgt * IN, r))
    return out


def pin_profile(fat_neck=False):
    """Stations [(r, z)] and a material per row: the table stations exactly,
    the stripe and crown bands as single rows, PCHIP between, and an
    elliptical crown above the last station."""
    table = pin_table(fat_neck)
    f = pchip([z for z, _ in table], [r for _, r in table])
    decal = [(a * IN, b * IN, PIN_RED_IDX) for a, b in STRIPES]
    decal.append((CROWN[0] * IN, CROWN[1] * IN, PIN_RED_IDX))
    decal.append((CROWN[1] * IN, CROWN[2] * IN, -1))           # teeth row
    hard = sorted({z for z, _ in table} | {a for a, _, _ in decal} | {b for _, b, _ in decal})
    zs = []
    rows = []
    for a, b in zip(hard, hard[1:]):
        band = next((m for lo, hi, m in decal if abs(lo - a) < 1e-9 and abs(hi - b) < 1e-9), None)
        nsub = 1 if band is not None else max(1, math.ceil((b - a) / PIN_STEP - 1e-9))
        for k in range(nsub):
            zs.append(a + (b - a) * k / nsub)
            rows.append(band if band is not None else PIN_WHITE_IDX)
    zs.append(hard[-1])
    stations = [(f(z), z) for z in zs]
    # crown: an ellipse centred on the head's widest station, through the last
    z_head, z_last = 13.5 * IN, hard[-1]
    r_last = stations[-1][0]
    semi = PIN_H - z_head
    a_e = r_last / math.sqrt(1.0 - ((z_last - z_head) / semi) ** 2)
    for zz in (14.62, 14.82, 14.93, 14.98):
        z = zz * IN
        rows.append(PIN_WHITE_IDX)
        stations.append((a_e * math.sqrt(1.0 - ((z - z_head) / semi) ** 2), z))
    rows.append(PIN_WHITE_IDX)
    stations.append((PIN_TOP_R, PIN_H))
    return stations, rows


def add_pin(bm, base, profile, lean_deg=0.0):
    """One pin turned about its axis through ``base``; ``lean_deg`` tips it
    about the lane's axis through the centre of its base."""
    stations, rows = profile
    rot = Matrix.Rotation(math.radians(lean_deg), 3, "Y")
    segs = PIN_SEGS
    rings = []
    for i in range(segs):
        a = 2.0 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new(base + rot @ Vector((r * ca, r * sa, z))) for r, z in stations])
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for j, mat in enumerate(rows):
            a0, a1, b1, b0 = r0[j], r1[j], r1[j + 1], r0[j + 1]
            if mat == -1:
                # crown teeth: one red tooth over every two segments
                if i % 2 == 0:
                    bm.faces.new((a0, a1, b1)).material_index = PIN_RED_IDX
                    bm.faces.new((a0, b1, b0)).material_index = PIN_WHITE_IDX
                else:
                    bm.faces.new((a0, a1, b0)).material_index = PIN_RED_IDX
                    bm.faces.new((a1, b1, b0)).material_index = PIN_WHITE_IDX
            else:
                bm.faces.new((a0, a1, b1, b0)).material_index = mat
    n = len(stations)
    bm.faces.new([rings[i][0] for i in reversed(range(segs))]).material_index = PIN_WHITE_IDX
    bm.faces.new([rings[i][n - 1] for i in range(segs)]).material_index = PIN_WHITE_IDX


def add_pins(bm, wide, offset_pin, float_pin, lean_pin, fat_neck):
    profile = pin_profile(fat_neck)
    for k, c in enumerate(spot_centres(wide)):
        base = Vector((c.x, c.y, LANE_TOP - PIN_BITE))
        if offset_pin and k == 4:          # pin 5
            base.x += OFFSET_PIN
        if float_pin and k == 2:           # pin 3
            base.z += FLOAT_PIN
        add_pin(bm, base, profile, LEAN_PIN_DEG if (lean_pin and k == 5) else 0.0)


# --------------------------------------------------------------------------
# Ball: a sphere drilled by an exact Boolean
# --------------------------------------------------------------------------

def rot_toward(v, toward, ang):
    """Rotate unit ``v`` by ``ang`` radians toward ``toward``."""
    ax = v.cross(toward).normalized()
    return (Matrix.Rotation(ang, 3, ax) @ v).normalized()


def hole_axes():
    """(entry direction, drill direction, bore radius, depth) for the thumb
    and the two finger holes, in the ball's frame: the grip centre turned up
    toward the bowler, the thumb toward the bowler, the two fingers down the
    lane, split across it. The thumb is drilled toward the centre; the two
    fingers are drilled parallel, along their pair's mid-axis, as a real
    grip is, so their bores stay one bridge apart all the way down instead
    of converging into each other."""
    g = Matrix.Rotation(math.radians(GRIP_YAW), 3, "Z") @ (
        Matrix.Rotation(math.radians(GRIP_TILT), 3, "X") @ ZAX)
    g = g.normalized()
    fwd = (YAX - g * YAX.dot(g)).normalized()
    lat = g.cross(fwd).normalized()
    half = 0.5 * SPAN / BALL_R
    thumb = rot_toward(g, -fwd, half)
    mid = rot_toward(g, fwd, half)
    lat_a = 0.5 * BRIDGE / BALL_R
    fa = rot_toward(mid, lat, lat_a)
    fb = rot_toward(mid, -lat, lat_a)
    return [(thumb, thumb, THUMB_R, THUMB_D), (fa, mid, FINGER_R, FINGER_D),
            (fb, mid, FINGER_R, FINGER_D)]


def cutter_profile(r, depth):
    """(radius, depth) of a drill with a 45-degree countersink that meets the
    sphere HOLE_BEVEL outside the bore, and a chamfered flat bottom."""
    b = HOLE_BEVEL + (r + HOLE_BEVEL) ** 2 / (2.0 * BALL_R)
    pts = [(r + b + 0.02, -0.02), (r, b)]
    for k in range(1, 5):
        pts.append((r, b + (depth - 0.002 - b) * k / 4.0))
    pts.append((r - 0.002, depth))
    return pts


def build_ball_mesh(shallow):
    """The drilled ball as a temporary mesh, centred on the origin."""
    made = []
    try:
        bm = bmesh.new()
        try:
            bmesh.ops.create_uvsphere(bm, u_segments=BALL_SEGS[0], v_segments=BALL_SEGS[1],
                                      radius=BALL_R)
            for f in bm.faces:
                f.material_index = BALL_IDX
            me = bpy.data.meshes.new("BallCore")
            bm.to_mesh(me)
        finally:
            bm.free()
        ball = bpy.data.objects.new("BallCore", me)
        bpy.context.scene.collection.objects.link(ball)
        made.append(ball)
        for k, (e, a, r, depth) in enumerate(hole_axes()):
            if shallow and k > 0:
                depth = SHALLOW_D
            cbm = bmesh.new()
            try:
                add_lathe(cbm, cutter_profile(r, depth), HOLE_SEGS, BORE_IDX,
                          center=e * BALL_R, rot=frame(-a, ZAX if abs(a.z) < 0.9 else XAX),
                          solid=True)
                bmesh.ops.recalc_face_normals(cbm, faces=list(cbm.faces))
                cme = bpy.data.meshes.new(f"BallDrill{k}")
                cbm.to_mesh(cme)
            finally:
                cbm.free()
            cut = bpy.data.objects.new(f"BallDrill{k}", cme)
            bpy.context.scene.collection.objects.link(cut)
            cut.hide_render = True
            made.append(cut)
            mod = ball.modifiers.new(f"Drill{k}", "BOOLEAN")
            mod.operation = "DIFFERENCE"
            mod.solver = "EXACT"
            mod.object = cut
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        out = bpy.data.meshes.new_from_object(ball.evaluated_get(dg))
    finally:
        for ob in made:
            data = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.meshes.remove(data)
        bpy.context.view_layer.update()
    # Triangulate the Boolean's n-gons here and dissolve the slivers that
    # collinear cut vertices leave, before the ball joins the deck.
    bm = bmesh.new()
    try:
        bm.from_mesh(out)
        big = [f for f in bm.faces if len(f.verts) > 4]
        if big:
            bmesh.ops.triangulate(bm, faces=big)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=list(bm.edges))
        bm.to_mesh(out)
    finally:
        bm.free()
    # The Boolean does not carry material indices the same way on every
    # version, so classify its faces by geometry instead: a face of the shell
    # faces straight out from the centre and lies on the sphere; everything
    # else (countersink, bore, bottom) is the drilled bore.
    for p in out.polygons:
        c = p.center
        on = c.length > BALL_R - 0.002 and p.normal.dot(c.normalized()) > 0.9
        p.material_index = BALL_IDX if on else BORE_IDX
    return out


def add_ball(bm, shallow, float_ball):
    me = build_ball_mesh(shallow)
    try:
        z = LANE_TOP + BALL_R - BALL_BITE + (FLOAT_BALL if float_ball else 0.0)
        me.transform(Matrix.Translation((BALL_XY[0], BALL_XY[1], z)))
        bm.from_mesh(me)
    finally:
        bpy.data.meshes.remove(me)


def build_deck_mesh(name, bevel_offset, bevel_segments, float_sleeper=False, offset_pin=False,
                    float_pin=False, lean_pin=False, wide_rack=False, fat_neck=False,
                    float_ball=False, shallow_holes=False, proud_board=False,
                    lift_arrows=False):
    bm = bmesh.new()
    try:
        add_ball(bm, shallow_holes, float_ball)
        bevel_verts = []
        add_lane(bm, PROUD_BOARD_IDX if proud_board else None)
        add_inlays(bm, wide_rack, LIFT_ARROWS if lift_arrows else 0.0)
        add_pins(bm, wide_rack, offset_pin, float_pin, lean_pin, fat_neck)
        for side in (-1.0, 1.0):
            add_gutter(bm, side, bevel_verts)
            add_capping(bm, side)
            add_kickback(bm, side, bevel_verts)
        add_pit_edge(bm, bevel_verts)
        add_sleepers(bm, float_sleeper)

        if bevel_offset > 0.0:
            # Round the kickbacks', gutters' and pit edge's hard edges, one
            # pass per material with material= set, over sorted edges.
            for mat_idx in (KICKBACK_IDX, GUTTER_IDX, METAL_IDX):
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
        # Turned and round parts (pins, ball) are smooth; board seams, bores,
        # caps and chamfers stay crisp. A pin's stripes are print, not a
        # break in its surface, so they do not split its shading.
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            elif len(mats) > 1 and not mats <= set(PIN_IDXS):
                edge.smooth = False
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
               noise_scale=14.0, coat=0.0, coat_rough=0.08, bump=0.0, bump_scale=400.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if coat > 0.0 and "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = coat_rough
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
        bnode.inputs["Strength"].default_value = bump
        bnode.inputs["Distance"].default_value = 0.0004
        nt.links.new(tex.outputs["Fac"], bnode.inputs["Height"])
        nt.links.new(bnode.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def wood_material(name, light, dark, roughness, coat, grain=(320.0, 5.0, 320.0),
                  board=True, tone_amp=0.16, seam_dark=0.30):
    """Lacquered wood. With ``board``, each board of the lane takes its own
    tone and its own grain offset, from its index across the lane read off
    object-space x; grain runs along y. Faces that turn away from the top
    (the V seams, the joint, the end grain) are darkened, so the seams read."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = roughness
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.04
    coord = nt.nodes.new("ShaderNodeTexCoord")
    vec = coord.outputs["Object"]
    tone = None
    if board:
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(coord.outputs["Object"], sep.inputs[0])
        add = nt.nodes.new("ShaderNodeMath")
        add.operation = "ADD"
        add.inputs[1].default_value = LANE_HALF
        nt.links.new(sep.outputs["X"], add.inputs[0])
        div = nt.nodes.new("ShaderNodeMath")
        div.operation = "DIVIDE"
        div.inputs[1].default_value = BOARD_W
        nt.links.new(add.outputs[0], div.inputs[0])
        flo = nt.nodes.new("ShaderNodeMath")
        flo.operation = "FLOOR"
        nt.links.new(div.outputs[0], flo.inputs[0])
        wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
        wn.noise_dimensions = "1D"
        nt.links.new(flo.outputs[0], wn.inputs["W"])
        tone = nt.nodes.new("ShaderNodeMapRange")
        tone.inputs["To Min"].default_value = 1.0 - tone_amp
        tone.inputs["To Max"].default_value = 1.0 + tone_amp
        nt.links.new(wn.outputs["Value"], tone.inputs["Value"])
        off = nt.nodes.new("ShaderNodeCombineXYZ")
        off.inputs["Y"].default_value = 0.0
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = 3.7
        nt.links.new(flo.outputs[0], mul.inputs[0])
        nt.links.new(mul.outputs[0], off.inputs["Y"])
        nt.links.new(mul.outputs[0], off.inputs["Z"])
        vadd = nt.nodes.new("ShaderNodeVectorMath")
        vadd.operation = "ADD"
        nt.links.new(coord.outputs["Object"], vadd.inputs[0])
        nt.links.new(off.outputs[0], vadd.inputs[1])
        vec = vadd.outputs[0]
    scale = nt.nodes.new("ShaderNodeVectorMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = grain
    nt.links.new(vec, scale.inputs[0])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.0
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.62
    noise.inputs["Distortion"].default_value = 0.6
    nt.links.new(scale.outputs[0], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.36
    ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].position = 0.66
    ramp.color_ramp.elements[1].color = light
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    if tone is not None:
        sc = nt.nodes.new("ShaderNodeVectorMath")
        sc.operation = "SCALE"
        nt.links.new(col, sc.inputs[0])
        nt.links.new(tone.outputs[0], sc.inputs["Scale"])
        col = sc.outputs[0]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    gsep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], gsep.inputs[0])
    seam = nt.nodes.new("ShaderNodeMapRange")
    seam.inputs["From Min"].default_value = 0.90
    seam.inputs["From Max"].default_value = 0.999
    seam.inputs["To Min"].default_value = seam_dark
    seam.inputs["To Max"].default_value = 1.0
    nt.links.new(gsep.outputs["Z"], seam.inputs["Value"])
    sc2 = nt.nodes.new("ShaderNodeVectorMath")
    sc2.operation = "SCALE"
    nt.links.new(col, sc2.inputs[0])
    nt.links.new(seam.outputs[0], sc2.inputs["Scale"])
    nt.links.new(sc2.outputs[0], bsdf.inputs["Base Color"])
    return mat


def ball_material():
    """Reactive resin: deep violet and electric blue marbled by a distorted
    wave, with thin pale veins, under a high-gloss coat."""
    mat = bpy.data.materials.new("BallResin")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.18
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 1.0
        bsdf.inputs["Coat Roughness"].default_value = 0.03
    coord = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 5.0
    wave.inputs["Distortion"].default_value = 9.0
    wave.inputs["Detail"].default_value = 3.0
    wave.inputs["Detail Scale"].default_value = 1.2
    nt.links.new(coord.outputs["Object"], wave.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.elements[0].position = 0.10
    cr.elements[0].color = (0.050, 0.010, 0.080, 1.0)
    cr.elements[1].position = 0.50
    cr.elements[1].color = (0.018, 0.055, 0.240, 1.0)
    e = cr.elements.new(0.72)
    e.color = (0.120, 0.030, 0.190, 1.0)
    e = cr.elements.new(0.86)
    e.color = (0.060, 0.140, 0.380, 1.0)
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def deck_materials():
    """(maple, deck, pin white, pin red, ball, bore, gutter, kickback, metal,
    inlay, sleeper): shared by the check and the render.

    The approach is lacquered hard maple, board by board; the pin deck a
    dark lacquered walnut-toned hardwood; the pins glossy white lacquer with
    red neck stripes and crown; the ball a marbled violet resin with dark
    drilled bores; the gutters dark phenolic; the kickbacks and cappings a
    black-brown laminate under brushed aluminium caps and a steel pit edge;
    the arrows, dots and pin spots dark inlay; the sleepers black paint.
    """
    maple = wood_material("LaneMaple", (0.64, 0.52, 0.35, 1.0), (0.48, 0.37, 0.24, 1.0),
                          0.30, 1.0)
    deck = wood_material("PinDeck", (0.25, 0.115, 0.050, 1.0), (0.14, 0.060, 0.025, 1.0),
                         0.30, 1.0)
    white = principled("PinWhite", (0.84, 0.83, 0.80, 1.0), 0.0, 0.32, roughness_var=0.05,
                       noise_scale=60.0, coat=1.0, coat_rough=0.05)
    red = principled("PinRed", (0.62, 0.018, 0.020, 1.0), 0.0, 0.32, coat=1.0, coat_rough=0.05)
    ball = ball_material()
    bore = principled("BallBore", (0.018, 0.016, 0.022, 1.0), 0.0, 0.62)
    gutter = principled("GutterPhenolic", (0.040, 0.042, 0.046, 1.0), 0.25, 0.42,
                        roughness_var=0.08, noise_scale=40.0)
    kick = wood_material("KickbackLaminate", (0.115, 0.070, 0.046, 1.0),
                         (0.066, 0.040, 0.028, 1.0), 0.38, 0.4, grain=(90.0, 3.0, 90.0),
                         board=False, seam_dark=0.8)
    metal = principled("BrushedAluminium", (0.62, 0.62, 0.64, 1.0), 1.0, 0.28,
                       roughness_var=0.06, noise_scale=300.0)
    inlay = principled("LaneInlay", (0.040, 0.020, 0.014, 1.0), 0.0, 0.30, coat=1.0,
                       coat_rough=0.04)
    sleeper = principled("SleeperPaint", (0.030, 0.028, 0.027, 1.0), 0.0, 0.72,
                         roughness_var=0.08, noise_scale=30.0)
    return (maple, deck, white, red, ball, bore, gutter, kick, metal, inlay, sleeper)


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
    """World AABB read off the mesh's own vertices (``bound_box`` is a
    cached copy that an in-place vertex edit does not refresh)."""
    me = obj.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    w = co @ mw[:3, :3].T + mw[:3, 3]
    lo, hi = w.min(axis=0), w.max(axis=0)
    return (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])


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
    return Vector(c), Vector(vecs[:, -1 if largest else 0]).normalized()


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    lanes = [s for s in parts if MAPLE_IDX in s.mats and DECK_IDX in s.mats]
    out["lane"] = max(lanes, key=lambda s: len(s.verts)) if lanes else None
    out["pins"] = [s for s in parts if s.mat == PIN_WHITE_IDX]
    out["ball"] = next((s for s in parts if s.mat == BALL_IDX), None)
    out["sleepers"] = [s for s in parts if s.mat == SLEEPER_IDX and s.size.x > 1.0]
    inl = [s for s in parts if s.mat == INLAY_IDX]
    out["arrows"] = [s for s in inl if s.size.y > 0.10]
    out["round_inlays"] = [s for s in inl if s.size.y <= 0.10]
    return out


def lane_top_at(lane, x, y):
    """The lane's own surface under (x, y), by a ray straight down."""
    hit, _n, idx, _d = lane.tree.ray_cast(Vector((x, y, LANE_TOP + 0.5)), Vector((0.0, 0.0, -1.0)))
    if hit is None:
        return None, None
    return hit.z, lane.polys[idx].material_index


def split_inlays(cls):
    """Round inlays over the deck are pin spots; over the maple, range dots."""
    spots, dots = [], []
    lane = cls["lane"]
    for s in cls["round_inlays"]:
        _z, mat = lane_top_at(lane, s.mean.x, s.mean.y)
        (spots if mat == DECK_IDX else dots).append(s)
    return spots, dots


def pin_axes(me, pin):
    """(base centre, top centre) from the pin's bottom and top caps."""
    bot, top = set(), set()
    for p in pin.polys:
        if p.normal.z < -0.99:
            bot.update(p.vertices)
        elif p.normal.z > 0.99:
            top.update(p.vertices)
    b = sum((me.vertices[i].co for i in bot), Vector()) / max(1, len(bot))
    t = sum((me.vertices[i].co for i in top), Vector()) / max(1, len(top))
    return b, t


def radial(p, c, a):
    d = p - c
    return (d - a * d.dot(a)).length


def pin_audit(me, cls, spots):
    """Per pin: offset of its base centre from the nearest spot centre, its
    seat below the deck face under it, tilt, height, belly and its radius at
    every table station."""
    lane = cls["lane"]
    table = pin_table()
    offs, seats, tilts, heights, bellies, prof = [], [], [], [], [], []
    for pin in cls["pins"]:
        b, t = pin_axes(me, pin)
        a = (t - b).normalized()
        offs.append(min((math.hypot(b.x - s.mean.x, b.y - s.mean.y) for s in spots), default=9.0))
        zdeck, _m = lane_top_at(lane, b.x, b.y)
        seats.append((zdeck - b.z) if zdeck is not None else 9.0)
        tilts.append(math.degrees(math.acos(max(-1.0, min(1.0, a.z)))))
        heights.append((t - b).length)
        bellies.append(2.0 * max(radial(p, b, a) for p in pin.pts))
        worst = 0.0
        for z, r in table:
            rs = [radial(p, b, a) for p in pin.pts if abs((p - b).dot(a) - z) < PROFILE_BAND]
            got = sum(rs) / len(rs) if rs else 9.0
            worst = max(worst, abs(got - r))
        prof.append(worst)
    return {"offs": offs, "seats": seats, "tilts": tilts, "heights": heights,
            "bellies": bellies, "profile": prof}


def lattice_audit(cls, spots):
    """The spots' nearest-neighbour edges, rows and head spot on the lane's
    centre line."""
    cs = [s.mean for s in spots]
    s = PIN_S
    edges = []
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            d = math.hypot(cs[i].x - cs[j].x, cs[i].y - cs[j].y)
            if d < 1.2 * s:
                edges.append(d)
    ys = sorted(c.y for c in cs)
    rows = [[ys[0]]]
    for y in ys[1:]:
        if y - rows[-1][-1] > 0.25 * s:
            rows.append([y])
        else:
            rows[-1].append(y)
    spread = max((max(r) - min(r) for r in rows), default=9.0)
    means = [sum(r) / len(r) for r in rows]
    pitch = [b - a for a, b in zip(means, means[1:])]
    lane = cls["lane"]
    mid = 0.5 * (lane.lo.x + lane.hi.x)
    head = min(cs, key=lambda c: c.y) if cs else Vector((9.0, 9.0, 9.0))
    return {"edges": edges, "rows": [len(r) for r in rows], "spread": spread,
            "pitch": pitch, "head_x": head.x - mid}


def sphere_fit(pts):
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    a = np.hstack([2.0 * p, np.ones((len(p), 1))])
    b = (p * p).sum(axis=1)
    sol, *_ = np.linalg.lstsq(a, b, rcond=None)
    c = sol[:3]
    r = math.sqrt(sol[3] + c.dot(c))
    return Vector(c), r


def exit_t(m, a, c, r):
    """Where the line m + t a leaves the sphere (c, r), outward."""
    d = m - c
    bq = d.dot(a)
    disc = bq * bq - (d.dot(d) - r * r)
    return -bq + math.sqrt(max(0.0, disc))


def ball_audit(me, cls):
    """Sphere fit to the ball's shell (refitted on the vertices lying on the
    sphere), its rest above the lane, and each drilled hole's axis, depth,
    bore and angular position."""
    ball = cls["ball"]
    surf = set()
    bore_polys = []
    for p in ball.polys:
        if p.material_index == BALL_IDX:
            surf.update(p.vertices)
        elif p.material_index == BORE_IDX:
            bore_polys.append(p)
    pts = [me.vertices[i].co.copy() for i in surf]
    c, r = sphere_fit(pts)
    on = [p for p in pts if abs((p - c).length - r) < 2e-5]
    c, r = sphere_fit(on)
    zl, _m = lane_top_at(cls["lane"], c.x, c.y)
    rest = (c.z - r - zl) if zl is not None else 9.0
    # holes: bore faces grouped by shared vertices
    vert_faces = {}
    for k, p in enumerate(bore_polys):
        for v in p.vertices:
            vert_faces.setdefault(v, []).append(k)
    seen = [False] * len(bore_polys)
    holes = []
    for k0 in range(len(bore_polys)):
        if seen[k0]:
            continue
        seen[k0] = True
        stack, vs, fs = [k0], set(), [k0]
        while stack:
            k = stack.pop()
            for v in bore_polys[k].vertices:
                vs.add(v)
                for q in vert_faces[v]:
                    if not seen[q]:
                        seen[q] = True
                        stack.append(q)
                        fs.append(q)
        hp = [me.vertices[i].co.copy() for i in vs]
        # the drill's flat bottom: the largest set of the hole's faces that
        # share one normal. That normal is the hole's axis, pointing out of
        # it, and the centre of the bottom lies on the axis.
        group = [bore_polys[k] for k in fs]
        bottom = max(group, key=lambda p: sum(1 for q in group if q.normal.dot(p.normal) > 0.99999))
        cap = [q for q in group if q.normal.dot(bottom.normal) > 0.99999]
        cap_v = {v for q in cap for v in q.vertices}
        m = sum((me.vertices[i].co for i in cap_v), Vector()) / len(cap_v)
        a = bottom.normal.copy()
        t_exit = exit_t(m, a, c, r)
        t_bot = 0.0
        mids = [radial(p, m, a) for p in hp if t_bot + 0.005 < (p - m).dot(a) < t_exit - 0.008]
        bore = 2.0 * (sum(mids) / len(mids)) if mids else 0.0
        holes.append({"entry": (m + a * t_exit - c).normalized(), "depth": t_exit - t_bot,
                      "bore": bore})
    holes.sort(key=lambda h: -h["bore"])
    span = []
    bridge = 9.0
    if len(holes) == 3:
        th = holes[0]["entry"]
        span = [r * math.acos(max(-1.0, min(1.0, th.dot(h["entry"])))) for h in holes[1:]]
        bridge = r * math.acos(max(-1.0, min(1.0, holes[1]["entry"].dot(holes[2]["entry"]))))
    return {"centre": c, "d": 2.0 * r, "rest": rest, "holes": holes, "span": span,
            "bridge": bridge}


def board_audit(me, cls):
    """The lane's flat board tops clustered across the lane: count, pitch,
    every top at one height, every board's edges straight down the lane."""
    lane = cls["lane"]
    tops = [p for p in lane.polys if p.material_index in LANE_IDXS and p.normal.z > 0.99999]
    tops.sort(key=lambda p: p.center.x)
    boards = []
    for p in tops:
        if boards and p.center.x - boards[-1][-1].center.x < 0.002:
            boards[-1].append(p)
        else:
            boards.append([p])
    zs, par, centres = [], 0.0, []
    for b in boards:
        vs = {v for p in b for v in p.vertices}
        xs = [me.vertices[v].co.x for v in vs]
        zs += [me.vertices[v].co.z for v in vs]
        xmid = 0.5 * (min(xs) + max(xs))
        left = [x for x in xs if x < xmid]
        right = [x for x in xs if x >= xmid]
        par = max(par, max(left) - min(left), max(right) - min(right))
        centres.append(xmid)
    # the two edge boards carry the lane's wider edge chamfer, so their flat
    # tops sit off-centre; the pitch is read between interior boards
    inner = centres[1:-1]
    pitch = [b - a for a, b in zip(inner, inner[1:])]
    return {"n": len(boards), "flush": (max(zs) - min(zs)) if zs else 9.0, "parallel": par,
            "pitch_dev": max((abs(p - BOARD_W) for p in pitch), default=9.0)}


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
        bm.verts.new((0.0, -1.0, 0.3))
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
    img = bpy.data.images.new("DeckNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = KICKBACK_IDX
    return img, tex


def bake_normal(high, low):
    # Duplicated from snippets/bake_normal_high_to_low.py (not a package).
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    for ob in bpy.context.view_layer.objects:
        if ob is not None:
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


FLOOR_NAMES = ("maple", "deck", "pin white", "pin red", "ball", "bore", "gutter", "kickback",
               "metal", "inlay", "sleeper")


def r5(xs):
    return [round(x, 5) for x in xs]


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_deck_mesh("PinDeckLow", bevel_offset=0.0015, bevel_segments=1, **flags)
    high = build_deck_mesh("PinDeckHigh", bevel_offset=0.0015, bevel_segments=3, **flags)
    mats = deck_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the kickback laminate: its nose, top and ends are
    # where the high mesh's rounder bevel differs from the low.
    target = mats[KICKBACK_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("deck mesh did not build", 3),) + none3

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
    sleepers = [s.lo.z for s in cls["sleepers"]]
    spots, dots = split_inlays(cls)
    pins = pin_audit(low.data, cls, spots)
    lat = lattice_audit(cls, spots)
    ball = ball_audit(low.data, cls) if cls["ball"] else None
    boards = board_audit(low.data, cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("deck has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "PinDeckLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "PinDeckLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_deck_mesh("PinDeckColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "PinDeckCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_bowling_pins_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} sleepers={r5(sleepers)} spots={len(spots)} "
          f"dots={len(dots)} arrows={len(cls['arrows'])} pins={len(cls['pins'])}")
    print(f"measured pin_off={[round(o, 6) for o in pins['offs']]}")
    print(f"measured pin_seat={[round(s, 6) for s in pins['seats']]}")
    print(f"measured pin_tilt={[round(t, 4) for t in pins['tilts']]} "
          f"pin_h={r5(pins['heights'])} belly={r5(pins['bellies'])}")
    print(f"measured profile_dev={[round(p, 6) for p in pins['profile']]}")
    print(f"measured lattice edges={len(lat['edges'])} "
          f"dev={max((abs(e - PIN_S) for e in lat['edges']), default=9.0):.6f} "
          f"rows={lat['rows']} spread={lat['spread']:.6f} "
          f"pitch={r5(lat['pitch'])} head_x={lat['head_x']:.6f}")
    if ball:
        print(f"measured ball d={ball['d']:.5f} rest={ball['rest']:.6f} "
              f"holes={len(ball['holes'])} depth={r5([h['depth'] for h in ball['holes']])} "
              f"bore={r5([h['bore'] for h in ball['holes']])} span={r5(ball['span'])} "
              f"bridge={ball['bridge']:.5f}")
    print(f"measured boards n={boards['n']} flush={boards['flush']:.6f} "
          f"parallel={boards['parallel']:.6f} pitch_dev={boards['pitch_dev']:.6f}")
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
    if len(sleepers) != SLEEPER_N or max(sleepers) > ZMIN_EPS:
        return (fail(f"supports: {len(sleepers)} sleepers (want {SLEEPER_N}) zmin "
                     f"{r5(sleepers)} (each within {ZMIN_EPS} of 0)", 16),) + none3
    if (len(cls["pins"]) != PIN_COUNT or len(spots) != SPOT_COUNT
            or max(pins["offs"], default=9.0) > PIN_CENTRE_TOL):
        return (fail(f"pins on spots: {len(cls['pins'])} pins (want {PIN_COUNT}), {len(spots)} "
                     f"spots (want {SPOT_COUNT}), base centre off its spot "
                     f"{[round(o, 5) for o in pins['offs']]} m (tol {PIN_CENTRE_TOL})", 17),) + none3
    if any(not (PIN_SEAT_MIN <= s <= PIN_SEAT_MAX) for s in pins["seats"]):
        return (fail(f"pins not seated: base below the deck face {r5(pins['seats'])} m "
                     f"(band {PIN_SEAT_MIN} to {PIN_SEAT_MAX})", 18),) + none3
    if (max(pins["tilts"]) > TILT_MAX_DEG
            or any(abs(h - PIN_H) > SIZE_TOL for h in pins["heights"])
            or any(abs(d - PIN_BELLY) > SIZE_TOL for d in pins["bellies"])):
        return (fail(f"pins not plumb or not to size: tilt {[round(t, 3) for t in pins['tilts']]} "
                     f"deg (max {TILT_MAX_DEG}), height {r5(pins['heights'])} (want {PIN_H:.5f}), "
                     f"belly {r5(pins['bellies'])} (want {PIN_BELLY:.5f}, tol {SIZE_TOL})", 19),) + none3
    edge_dev = max((abs(e - PIN_S) for e in lat["edges"]), default=9.0)
    pitch_dev = max((abs(p - ROW_H) for p in lat["pitch"]), default=9.0)
    if (len(lat["edges"]) != LATTICE_EDGES or edge_dev > LATTICE_TOL
            or tuple(lat["rows"]) != ROW_SIZES or lat["spread"] > LATTICE_TOL
            or pitch_dev > LATTICE_TOL or abs(lat["head_x"]) > LATTICE_TOL):
        return (fail(f"spots off the 12 in lattice: {len(lat['edges'])} edges (want "
                     f"{LATTICE_EDGES}) off pitch by {edge_dev:.5f}, rows {lat['rows']}, row "
                     f"spread {lat['spread']:.5f}, row pitch off by {pitch_dev:.5f}, head spot "
                     f"{lat['head_x']:.5f} off the centre line (tol {LATTICE_TOL})", 20),) + none3
    if max(pins["profile"]) > PROFILE_TOL:
        return (fail(f"pin profile off the table: worst station "
                     f"{[round(p, 5) for p in pins['profile']]} m (tol {PROFILE_TOL})", 21),) + none3
    if (ball is None or not (BALL_REST_MIN <= ball["rest"] <= BALL_REST_MAX)
            or abs(ball["d"] - BALL_D) > BALL_D_TOL):
        got = (f"rest {ball['rest']:.5f}, diameter {ball['d']:.5f}") if ball else "no ball"
        return (fail(f"ball not resting on the lane at its radius: {got} (rest band "
                     f"{BALL_REST_MIN} to {BALL_REST_MAX}, diameter {BALL_D:.5f} +- "
                     f"{BALL_D_TOL})", 22),) + none3
    holes = ball["holes"]
    hole_ok = len(holes) == HOLE_COUNT
    if hole_ok:
        th, fa, fb = holes
        hole_ok = (THUMB_DEPTH_BAND[0] <= th["depth"] <= THUMB_DEPTH_BAND[1]
                   and all(FINGER_DEPTH_BAND[0] <= f["depth"] <= FINGER_DEPTH_BAND[1]
                           for f in (fa, fb))
                   and abs(th["bore"] - 2.0 * THUMB_R) <= BORE_TOL
                   and all(abs(f["bore"] - 2.0 * FINGER_R) <= BORE_TOL for f in (fa, fb))
                   and all(abs(s - SPAN) <= SPAN_TOL for s in ball["span"])
                   and abs(ball["bridge"] - BRIDGE) <= BRIDGE_TOL)
    if not hole_ok:
        return (fail(f"finger holes: {len(holes)} (want {HOLE_COUNT}), depth "
                     f"{r5([h['depth'] for h in holes])} (thumb {THUMB_DEPTH_BAND}, fingers "
                     f"{FINGER_DEPTH_BAND}), bore {r5([h['bore'] for h in holes])}, span "
                     f"{r5(ball['span'])} (want {SPAN:.4f}), bridge {ball['bridge']:.4f} "
                     f"(want {BRIDGE:.4f})", 23),) + none3
    if (boards["n"] != BOARD_N or boards["flush"] > BOARD_FLUSH_MAX
            or boards["parallel"] > BOARD_PARALLEL_MAX
            or boards["pitch_dev"] > BOARD_PITCH_TOL):
        return (fail(f"boards: {boards['n']} (want {BOARD_N}), tops spread "
                     f"{boards['flush']:.5f} m (max {BOARD_FLUSH_MAX}), edges off straight "
                     f"{boards['parallel']:.5f} (max {BOARD_PARALLEL_MAX}), pitch off "
                     f"{boards['pitch_dev']:.5f}", 24),) + none3
    if ncomp != COMPONENTS:
        return (fail(f"assembly splits into {ncomp} components (want {COMPONENTS}) "
                     f"{comp_sizes}", 25),) + none3
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
    pins = low.matrix_world @ Vector((0.0, 0.40, LANE_TOP + 0.18))

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
        aim_at = pins if target is None else Vector(target)
        ob.rotation_euler = (aim_at - ob.location).normalized().to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(ob)

    # The house rig scaled to a 2.6 m lane section: warm key upper left, cool
    # fill low right, cool rim behind the pins, warm wedge pooled on the wall.
    light("Key", (-2.2, -2.0, 2.3), 128.0, 1.6, (1.0, 0.97, 0.93), spread=40.0)
    light("Fill", (2.6, -2.2, 0.7), 12.0, 3.0, (0.72, 0.82, 1.0))
    light("Rim", (-0.8, 2.4, 1.4), 90.0, 1.4, (0.62, 0.78, 1.0))
    light("Wedge", (2.2, 2.0, 0.9), 200.0, 1.8, (1.0, 0.62, 0.30),
          target=(centre.x + 2.2, centre.y + WALL_Y, 0.55))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((CAM_VIEW[0], CAM_VIEW[1], 0.0)).normalized()
    cam.location = centre + view * CAM_DIST + Vector((0.0, 0.0, CAM_RISE))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector(AIM_OFF)
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
        # the lacquered lane reflects the pins
        try:
            scene.eevee.use_raytracing = True
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "WEBP" if path.lower().endswith(".webp") else "PNG"
    if path.lower().endswith(".webp"):
        scene.render.image_settings.quality = 90
    scene.render.filepath = path
    # Standard, not AgX: AgX washes the maple and the red stripes toward grey
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


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--float-sleeper", action="store_true")
    p.add_argument("--offset-pin", action="store_true")
    p.add_argument("--float-pin", action="store_true")
    p.add_argument("--lean-pin", action="store_true")
    p.add_argument("--wide-rack", action="store_true")
    p.add_argument("--fat-neck", action="store_true")
    p.add_argument("--float-ball", action="store_true")
    p.add_argument("--shallow-holes", action="store_true")
    p.add_argument("--proud-board", action="store_true")
    p.add_argument("--lift-arrows", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_sleeper=args.float_sleeper,
        offset_pin=args.offset_pin,
        float_pin=args.float_pin,
        lean_pin=args.lean_pin,
        wide_rack=args.wide_rack,
        fat_neck=args.fat_neck,
        float_ball=args.float_ball,
        shallow_holes=args.shallow_holes,
        proud_board=args.proud_board,
        lift_arrows=args.lift_arrows,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("bowling-pins OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
