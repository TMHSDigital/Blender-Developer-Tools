"""Game-ready home-gym weight rack — a showcase piece, not an example.

Asserts budget conformance of a procedural strength set (a half rack with a
loaded Olympic barbell on its J-hooks) after composing shipped pipeline
pieces: bmesh construction, UVs, twelve materials, high-to-low normal bake,
LOD chain, convex collider, Unity glTF export.

The rack stands on two floor feet, each a rectangular tube on rubber pads
with plastic end caps, tied at the back by a floor crossmember. Four square
uprights stand on bolted base plates. Their faces carry a row of punched
holes on a 2 in pitch, and the two front uprights number every hole. Two
side rails on bolted flanges, a rear top crossmember and a pull-up bar close
the top, and every upright wears a cap. On the front uprights, two J-hooks
and two spotter arms hang on pull pins seated in the holes; the J-hook
saddles and the spotter tops are lined with UHMW. Plate-storage horns on the
rear uprights carry more plates.

The barbell is one turned body: a knurled shaft with a centre knurl and
ring marks, two collars and two sleeves with a snap-ring groove and a
recessed end cap. Each sleeve carries a 20 kg and a 15 kg bumper (steel hub
insert, raised rim, raised weight numerals on the outer face) and a 5 kg
cast-iron change plate, closed by a coiled spring clip with rubber grips.
Two hex dumbbells lie on the floor in front of the rack.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-foot`` every pad and
dumbbell head on the floor, ``--offset-pin`` every pull pin coaxial with a
hole, ``--float-bar`` the bar seated in both J-hook saddles, ``--hook-high``
the bar level, ``--gap-plate`` the plates seated along their sleeve,
``--odd-load`` the load balanced left to right, ``--loose-horn`` one
connected rack assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python weight_rack.py --
    blender --background --python weight_rack.py -- --skip-decimate
    blender --background --python weight_rack.py -- --output rack.png
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

# --- Rack frame (x across, y front-to-back with the front at -y, z up) -------
UP_X = 0.55                 # upright centres at x = +-0.55
UP_Y = (0.0, 0.66)          # front and rear uprights
UP_HALF = 0.0375            # 3 in square tube
UP_RC = 0.005
UP_TOP = 2.080
CAP_TOP = 2.092
FOOT_HX = 0.050
FOOT_HZ = 0.025
FOOT_Y = (-0.40, 0.94)
FOOT_Z0 = 0.011             # foot underside; each pad bites 1 mm into it
PAD_T = 0.012
PAD_Y = ((-0.385, -0.285), (0.825, 0.925))
BASE_Z0 = FOOT_Z0 + 2.0 * FOOT_HZ - 0.0005
BASE_T = 0.010
UP_Z0 = BASE_Z0 + BASE_T - 0.002
RAIL_Z = 2.000
# punched holes: 1.0 in-ish holes on a 2 in pitch, numbered from the bottom
HOLE_R = 0.013
HOLE_DEPTH = 0.010
PITCH = 0.0508
HOLE_Z0 = 0.600             # centre of hole 1
N_HOLES = 23
HOLE_SEGS = 12
HOOK_HOLE = 16              # the J-hooks hang on hole 17
SPOT_HOLE = 6               # the spotter arms on hole 7
NUM_U = 0.0232              # numeral centre, across the face from the hole axis
NUM_CELL = 0.0024
DEC_PROUD = 0.0004
DEC_BITE = 0.0002
DEC_STEP = 0.00013          # every neighbouring numeral sits on its own plane
# J-hook: a J-section plate on a pull pin; the saddle is lined with UHMW
HOOK_T = 0.008
HOOK_W = 0.031              # half-width across x
SADDLE_W = 0.050
SADDLE_V = -0.070           # saddle floor below the pin
PLATE_BITE_UP = 0.0008      # hardware plates bite into the upright face
LINER_T = 0.004
LINER_BITE = 0.0003
PIN_R = 0.008
PIN_IN = 0.007              # pin depth inside its hole
# spotter arm
SPOT_LEN = 0.600
# --- Barbell ------------------------------------------------------------------
R_SHAFT = 0.014
R_SLEEVE = 0.025
COLLAR_S = 0.685            # collar face, from the bar centre
BAR_HALF = 1.100
BAR_BITE = 0.0002
BAR_SEGS = 32
R_HOLE = 0.0256             # plate bore on a 50 mm sleeve
SAG = R_HOLE - R_SLEEVE + 0.0002   # a plate hangs on the sleeve, bore resting on it
PLATE_BITE = 0.0005
PLATE_SEGS = 32
HUB_H = 0.002               # the steel hub stands proud of the rubber face
TEXT_R = 0.130
TEXT_CELL = 0.0065
TXT_PROUD = 0.0008
TXT_BITE = 0.0003
R_WIRE = 0.0022
CLIP_GRIP = 0.0006
CLIP_BITE = 0.0005
# (radius, thickness, material key, kind, numerals: kg on top, lb below)
PLATES = {
    "blue20": (0.225, 0.070, "blue", "bumper", ("20", "44")),
    "yellow15": (0.225, 0.055, "yellow", "bumper", ("15", "33")),
    "green10": (0.225, 0.042, "green", "bumper", ("10", "22")),
    "iron5": (0.114, 0.026, "iron", "iron", None),
    "iron25": (0.095, 0.018, "iron", "iron", None),
}
BAR_LOAD = ("blue20", "yellow15", "iron5")
ODD_LOAD = ("blue20", "yellow15", "iron25")
# --- Horns (on the rear uprights' outer faces) --------------------------------
HORN_L = 0.300
HORN_STOP = 0.016
WELD_T = 0.008
HORN_BOLT = 0.052
HORNS = (   # (side, z, plates)
    (-1, 0.300, ("blue20", "green10")),
    (1, 0.300, ("green10",)),
    (-1, 0.950, ("iron5", "iron25")),
    (1, 0.950, ("iron25",)),
)
# --- Dumbbells ------------------------------------------------------------------
DB_GAP = 0.135
DB_HEAD_R = 0.069           # hex head, to its corners
DB_HEAD_L = 0.100
DUMBBELLS = (((-0.24, -0.57), 10.0), ((0.14, -0.61), -4.0))

# --- Falsifier sizes ---------------------------------------------------------------
FLOAT_FOOT = 0.003
OFFSET_PIN = 0.012
FLOAT_BAR = 0.005
GAP_PLATE = 0.008
LOOSE_HORN = 0.010

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (2.200, 1.636, 2.092)
BASE_TRIS_MIN = 43500
BASE_TRIS_MAX = 45000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 12
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 640
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
# face floors per slot, in slot order (powder, bore, zinc, chrome, knurl,
# rubber, uhmw, decal, blue, yellow, green, iron)
FACE_FLOORS = (4420, 2820, 3900, 3110, 235, 1230, 96, 2890, 800, 530, 530, 2080)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
PAD_COUNT = 4
DB_HEAD_COUNT = 4
# Pins: every pull pin on the axis of a punched hole, inserted into it.
PIN_COUNT = 4
PIN_AXIS_TOL = 0.0005
PIN_DEPTH_MIN = 0.004
PIN_DEPTH_MAX = HOLE_DEPTH - 0.0005
# The bar rests in both saddles: shaft underside to liner top.
SEAT_MIN = -0.0008
SEAT_MAX = 0.0003
# Level and real-world size.
TILT_MAX_DEG = 0.05
BAR_LEN = 2.200
BUMPER_D = 0.450
RACK_H = UP_TOP
SIZE_TOL = 0.003
# Plates: coaxial with their sleeve, each bitten into the one inside it.
PLATE_COAX_TOL = 0.001
STACK_GAP_MIN = -0.0008
STACK_GAP_MAX = -0.0002
PLATE_COUNTS = (3, 3, 2, 1, 2, 1)   # bar left, bar right, the four horns
# Load balance: the loaded bar's mass centre on its own midpoint.
DENSITY = {"bumper": 1800.0, "iron": 7200.0, "steel": 7850.0}
BALANCE_TOL = 0.002
COMPONENTS = 1 + len(DUMBBELLS)
# Hero yaw: the left side and the loaded sleeve turned toward the camera.
HERO_YAW_DEG = 28.0
WALL_Y = 3.2

POWDER_IDX = 0
BORE_IDX = 1
ZINC_IDX = 2
CHROME_IDX = 3
KNURL_IDX = 4
RUBBER_IDX = 5
UHMW_IDX = 6
DECAL_IDX = 7
BLUE_IDX = 8
YELLOW_IDX = 9
GREEN_IDX = 10
IRON_IDX = 11
PLATE_MAT = {"blue": BLUE_IDX, "yellow": YELLOW_IDX, "green": GREEN_IDX, "iron": IRON_IDX}
PLATE_IDXS = (BLUE_IDX, YELLOW_IDX, GREEN_IDX, IRON_IDX)

ZAX = Vector((0.0, 0.0, 1.0))
XAX = Vector((1.0, 0.0, 0.0))
YAX = Vector((0.0, 1.0, 0.0))

# 3 x 5 numerals, top row first. No two cells touch only at a corner, so
# every numeral extrudes to a manifold shell.
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


# --------------------------------------------------------------------------
# Construction helpers (copied from showcase/hover-bike, not imported)
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
# Numerals, bolts
# --------------------------------------------------------------------------

def add_digit(bm, ch, origin, e_u, e_v, e_n, cell, proud, bite, mat_idx):
    """One raised numeral: the filled cells of a 3 x 5 grid extruded from
    ``bite`` inside the face to ``proud`` above it, one manifold shell."""
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


def add_number(bm, text, centre, e_u, e_v, e_n, cell, proud, bite, step, level0, mat_idx,
               dv=0.0003):
    """A numeral string centred on ``centre``; each digit on its own plane
    (and the second nudged ``dv`` up) so no two digits share a face plane."""
    n = len(text)
    width = (4 * n - 1) * cell
    for d, ch in enumerate(text):
        lv = level0 + d
        o = centre + e_u * (-0.5 * width + 4 * d * cell) + e_v * (-2.5 * cell + d * dv)
        add_digit(bm, ch, o, e_u, e_v, e_n, cell, proud + step * lv, bite + step * lv, mat_idx)


def add_bolt(bm, pos, axis, k, host_bite=0.0003):
    """Hex bolt head on a washer, seated on a face whose outward normal is
    ``axis``. ``k`` staggers each bolt of a group along its axis, so no two
    washers or heads of one group share a plane."""
    axis = Vector(axis).normalized()
    ref = ZAX if abs(axis.z) < 0.9 else XAX
    rot = frame(axis, ref)
    base = Vector(pos) - axis * (host_bite + 0.00012 * k)
    add_lathe(bm, [(0.0055, 0.0), (0.0110, 0.0), (0.0110, 0.0022), (0.0055, 0.0022)], 8,
              ZINC_IDX, center=base, rot=rot, phase=math.pi / 8.0)
    add_lathe(bm, [(0.0095, 0.0018), (0.0095, 0.0075), (0.0082, 0.0090), (0.0045, 0.0094)], 6,
              ZINC_IDX, center=base, rot=rot, solid=True, phase=math.pi / 6.0)


# --------------------------------------------------------------------------
# Uprights: square tube with punched, pocketed hole rows
# --------------------------------------------------------------------------

def upright_section(n=2):
    """Rounded-square section, counter-clockwise from +x; the front (-y) and
    back (+y) flats carry three interior points so hole cells can join them.
    Returns (points, front column indices, back column indices), columns
    ordered by x ascending."""
    h, rc = UP_HALF, UP_RC
    a = h - rc
    pts = []
    front = [0] * 5
    back = [0] * 5
    for k, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        cx, cy = sx * a, sy * a
        for s in range(n + 1):
            ang = 0.5 * math.pi * (k + s / n)
            pts.append((cx + rc * math.cos(ang), cy + rc * math.sin(ang)))
        if k == 0:
            back[4] = len(pts) - 1
            for q, u in enumerate((a / 2.0, 0.0, -a / 2.0)):
                pts.append((u, h))
                back[3 - q] = len(pts) - 1
            back[0] = len(pts)
        elif k == 2:
            front[0] = len(pts) - 1
            for q, u in enumerate((-a / 2.0, 0.0, a / 2.0)):
                pts.append((u, -h))
                front[1 + q] = len(pts) - 1
            front[4] = len(pts)
    return pts, front, back


def hole_z(k):
    return HOLE_Z0 + PITCH * k


def add_hole_cell(bm, bot, top, centre, e_u, inward):
    """One punched hole in a flat face: the face between the cell's boundary
    (five verts along its bottom and top edges, ordered along ``e_u``) and a
    12-gon, then a pocket ``HOLE_DEPTH`` deep in bore material."""
    circ, deep = [], []
    for j in range(HOLE_SEGS):
        t = 2.0 * math.pi * j / HOLE_SEGS
        p = centre + e_u * (HOLE_R * math.cos(t)) + ZAX * (HOLE_R * math.sin(t))
        circ.append(bm.verts.new(p))
        deep.append(bm.verts.new(p + inward * HOLE_DEPTH))
    c = circ
    BL, B1, B2, B3, BR = bot
    TL, T1, T2, T3, TR = top
    face = [
        (BR, TR, c[1], c[0], c[11]),
        (TR, T3, c[2], c[1]), (T3, T2, c[3], c[2]), (T2, T1, c[4], c[3]), (T1, TL, c[5], c[4]),
        (TL, BL, c[7], c[6], c[5]),
        (BL, B1, c[8], c[7]), (B1, B2, c[9], c[8]), (B2, B3, c[10], c[9]), (B3, BR, c[11], c[10]),
    ]
    _mark([bm.faces.new(f) for f in face], POWDER_IDX)
    walls = [bm.faces.new((circ[j], circ[(j + 1) % HOLE_SEGS], deep[(j + 1) % HOLE_SEGS], deep[j]))
             for j in range(HOLE_SEGS)]
    walls.append(bm.faces.new(tuple(reversed(deep))))
    _mark(walls, BORE_IDX)


def add_upright(bm, xc, yc, holes_front, holes_back, numbered, skip_numbers):
    sec, front, back = upright_section()
    zb = [hole_z(0) - 0.5 * PITCH + PITCH * i for i in range(N_HOLES + 1)]
    levels = [UP_Z0] + zb + [UP_TOP]
    rings = [[bm.verts.new((xc + x, yc + y, z)) for x, y in sec] for z in levels]
    n = len(sec)
    fset = set(range(front[0], front[0] + 4))
    bset = set(range(back[4], back[4] + 4))
    faces = []
    for g in range(len(levels) - 1):
        cell = 1 <= g <= N_HOLES
        for j in range(n):
            if cell and ((holes_front and j in fset) or (holes_back and j in bset)):
                continue
            m = (j + 1) % n
            faces.append(bm.faces.new((rings[g][j], rings[g][m], rings[g + 1][m], rings[g + 1][j])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, POWDER_IDX)
    for k in range(N_HOLES):
        r0, r1 = rings[k + 1], rings[k + 2]
        zc = hole_z(k)
        if holes_front:
            add_hole_cell(bm, [r0[i] for i in front], [r1[i] for i in front],
                          Vector((xc, yc - UP_HALF, zc)), XAX, YAX)
        if holes_back:
            add_hole_cell(bm, [r0[i] for i in reversed(back)], [r1[i] for i in reversed(back)],
                          Vector((xc, yc + UP_HALF, zc)), -XAX, -YAX)
        if numbered and k not in skip_numbers:
            par = k % 2
            centre = Vector((xc + NUM_U + 0.0003 * par, yc - UP_HALF, zc))
            add_number(bm, str(k + 1), centre, XAX, ZAX, -YAX, NUM_CELL, DEC_PROUD, DEC_BITE,
                       DEC_STEP, 2 * par, DECAL_IDX)
    # cap
    add_rbox(bm, UP_HALF + 0.002, UP_HALF + 0.002, 0.007,
             [(0.0, UP_TOP - 0.012), (0.0, CAP_TOP - 0.004), (0.004, CAP_TOP)],
             (xc, yc, 0.0), Matrix.Identity(3), RUBBER_IDX, n_corner=3)


# --------------------------------------------------------------------------
# Frame: feet, pads, base plates, rails, crossmembers, pull-up bar
# --------------------------------------------------------------------------

def add_frame(bm, bevel_verts, float_foot):
    rot_y = frame(YAX, XAX)       # local z along +y, local x along +x
    rot_x = frame(XAX, YAX)       # local z along +x, local x along +y
    zf = FOOT_Z0 + FOOT_HZ
    for side in (-1.0, 1.0):
        xc = side * UP_X
        add_rbox(bm, FOOT_HX, FOOT_HZ, 0.006, [(0.0, FOOT_Y[0]), (0.0, FOOT_Y[1])],
                 (xc, 0.0, zf), rot_y, POWDER_IDX, n_corner=3)
        # plastic end caps sleeved over both tube ends
        for y_end, d in ((FOOT_Y[0], -1.0), (FOOT_Y[1], 1.0)):
            add_rbox(bm, FOOT_HX + 0.0015, FOOT_HZ + 0.0015, 0.0075,
                     [(0.0, -0.012), (0.0, 0.003), (0.003, 0.0065)],
                     (xc, y_end, zf), frame((0.0, d, 0.0), XAX), RUBBER_IDX, n_corner=3)
        # rubber pads under both ends
        for pi, (y0, y1) in enumerate(PAD_Y):
            lift = FLOAT_FOOT if (float_foot and side < 0 and pi == 0) else 0.0
            add_rbox(bm, FOOT_HX - 0.004, 0.5 * (y1 - y0), 0.008,
                     [(0.002, 0.0), (0.0, 0.002), (0.0, PAD_T)],
                     (xc, 0.5 * (y0 + y1), lift), Matrix.Identity(3), RUBBER_IDX)
        # base plates, four bolts each
        for yc in UP_Y:
            bevel_verts += add_prism(bm, rrect(0.060, 0.075, 0.008), BASE_Z0, BASE_Z0 + BASE_T,
                                     (xc, yc, 0.0), Matrix.Identity(3), POWDER_IDX)
            for k, (bx, by) in enumerate(((-0.028, -0.057), (0.028, -0.057),
                                          (0.028, 0.057), (-0.028, 0.057))):
                add_bolt(bm, (xc + bx, yc + by, BASE_Z0 + BASE_T), ZAX, k)
        # side rail on bolted flanges between the front and rear uprights
        y_f = UP_Y[0] + UP_HALF
        y_r = UP_Y[1] - UP_HALF
        for y_face, d in ((y_f, 1.0), (y_r, -1.0)):
            rot = frame((0.0, d, 0.0), XAX)
            bevel_verts += add_prism(bm, rrect(0.036, 0.060, 0.008), -PLATE_BITE_UP, 0.008,
                                     (xc, y_face, RAIL_Z), rot, POWDER_IDX)
            for k, dz in enumerate((-0.045, 0.045)):
                add_bolt(bm, (xc, y_face + d * 0.008, RAIL_Z + dz), (0.0, d, 0.0), k)
        add_rbox(bm, 0.032, 0.025, 0.005, [(0.0, y_f + 0.007), (0.0, y_r - 0.007)],
                 (xc, 0.0, RAIL_Z), rot_y, POWDER_IDX, n_corner=3)
    # rear top crossmember and floor crossmember
    xi = UP_X - UP_HALF
    add_rbox(bm, 0.025, 0.0375, 0.005, [(0.0, -xi - 0.002), (0.0, xi + 0.002)],
             (0.0, UP_Y[1], 1.950), rot_x, POWDER_IDX, n_corner=3)
    xf = UP_X - FOOT_HX
    add_rbox(bm, 0.025, 0.020, 0.005, [(0.0, -xf - 0.002), (0.0, xf + 0.002)],
             (0.0, UP_Y[1], FOOT_Z0 + 0.025), rot_x, POWDER_IDX, n_corner=3)
    # pull-up bar between the front uprights, welded collars at both ends
    add_lathe(bm, [(0.0120, -xi - 0.003), (0.0165, -xi - 0.002), (0.0165, xi + 0.002),
                   (0.0120, xi + 0.003)], 24, ZINC_IDX, center=(0.0, UP_Y[0], 2.030),
              rot=frame(XAX, ZAX), solid=True)
    for s in (-1.0, 1.0):
        add_lathe(bm, [(0.0160, -0.002), (0.0235, -0.002), (0.0235, 0.002), (0.0200, 0.006),
                       (0.0160, 0.006)], 24, POWDER_IDX, center=(s * xi, UP_Y[0], 2.030),
                  rot=frame((-s, 0.0, 0.0), ZAX), phase=math.pi / 24.0)


# --------------------------------------------------------------------------
# J-hooks, spotter arms, pins
# --------------------------------------------------------------------------

HOOK_ROT = cols((0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0))   # u fwd, v up, w across


def add_pin(bm, xc, z, plate_front):
    """Pull pin on its hole's axis: a shank inserted PIN_IN into the hole,
    through the plate, and a knurled knob on the plate's front."""
    f = UP_Y[0] - UP_HALF
    w0 = plate_front - 0.0005
    add_lathe(bm, [(0.0055, -PIN_IN), (PIN_R, -PIN_IN + 0.0015), (PIN_R, w0),
                   (0.0130, w0 + 0.0005), (0.0160, w0 + 0.0030), (0.0160, w0 + 0.0180),
                   (0.0135, w0 + 0.0215), (0.0060, w0 + 0.0230)], 20, ZINC_IDX,
              center=(xc, f, z), rot=frame((0.0, -1.0, 0.0), ZAX), solid=True)


def add_jhook(bm, xc, k, bevel_verts):
    """J-section hook plate on the upright's front face, pinned in hole k."""
    f = UP_Y[0] - UP_HALF
    z = hole_z(k)
    o = Vector((xc, f, z))
    t = HOOK_T
    sw = SADDLE_W
    outline = [(-PLATE_BITE_UP, 0.040), (t - 0.004, 0.040), (t, 0.036), (t, SADDLE_V),
               (t + sw, SADDLE_V), (t + sw, -0.048), (t + sw + 0.003, -0.041),
               (2 * t + sw - 0.002, -0.041), (2 * t + sw, -0.044), (2 * t + sw, -0.074),
               (2 * t + sw - 0.006, -0.080), (-PLATE_BITE_UP, -0.080)]
    bevel_verts += add_prism(bm, outline, -HOOK_W, HOOK_W, o, HOOK_ROT, POWDER_IDX)
    lo = SADDLE_V - LINER_BITE
    b = t - LINER_BITE
    fr = t + sw + LINER_BITE
    liner = [(b, -0.048), (b, lo), (fr, lo), (fr, -0.050), (fr - LINER_T, -0.050),
             (fr - LINER_T, lo + LINER_T), (b + LINER_T, lo + LINER_T), (b + LINER_T, -0.048)]
    bevel_verts += add_prism(bm, liner, -HOOK_W + 0.003, HOOK_W - 0.003, o, HOOK_ROT, UHMW_IDX)
    add_pin(bm, xc, z, t)


def saddle_axis(k):
    """(y, z) of a bar axis resting in the saddle of a hook on hole k."""
    liner_top = hole_z(k) + SADDLE_V - LINER_BITE + LINER_T
    u = 0.5 * ((HOOK_T - LINER_BITE + LINER_T) + (HOOK_T + SADDLE_W + LINER_BITE - LINER_T))
    return UP_Y[0] - UP_HALF - u, liner_top + R_SHAFT - BAR_BITE


def add_spotter(bm, xc, k, bevel_verts, lift=0.0):
    """Spotter arm on a mount plate pinned in hole k: rectangular tube with a
    gusset, a UHMW strip on its top and a rubber end cap."""
    f = UP_Y[0] - UP_HALF
    z = hole_z(k) + lift
    o = Vector((xc, f, z))
    rot = frame((0.0, -1.0, 0.0), XAX)     # local x across, y up, z forward
    pt = 0.012
    bevel_verts += add_prism(bm, [(x, y - 0.0575) for x, y in rrect(0.035, 0.0925, 0.008)],
                             -PLATE_BITE_UP, pt, o, rot, POWDER_IDX)
    zc = -0.030 - 0.0375
    add_rbox(bm, 0.025, 0.0375, 0.006, [(0.0, pt - 0.001), (0.0, SPOT_LEN)],
             o + ZAX * zc, rot, POWDER_IDX, n_corner=3)
    add_rbox(bm, 0.0265, 0.0390, 0.008,
             [(0.0, SPOT_LEN - 0.018), (0.0, SPOT_LEN + 0.004), (0.004, SPOT_LEN + 0.008)],
             o + ZAX * zc, rot, RUBBER_IDX, n_corner=3)
    add_rbox(bm, 0.019, 0.003, 0.0025, [(0.0, 0.030), (0.0, SPOT_LEN - 0.024)],
             o + ZAX * (-0.030 + 0.003 - LINER_BITE), rot, UHMW_IDX, n_corner=2)
    gusset = [(pt - 0.0005, -0.104), (0.150, -0.104), (pt - 0.0005, -0.148)]
    bevel_verts += add_prism(bm, gusset, -0.004, 0.004, o, HOOK_ROT, POWDER_IDX)
    add_pin(bm, xc, z, pt)


# --------------------------------------------------------------------------
# Barbell, plates, clips, horns
# --------------------------------------------------------------------------

def bar_profile():
    half = [(R_SHAFT, 0.000), (R_SHAFT, 0.080), (R_SHAFT, 0.215), (R_SHAFT, 0.4025),
            (R_SHAFT, 0.4075), (R_SHAFT, 0.640), (R_SHAFT, 0.6555),
            (0.0300, 0.6560), (0.0335, 0.6575), (0.0350, 0.6600), (0.0350, 0.6800),
            (0.0335, 0.6830), (0.0310, COLLAR_S), (R_SLEEVE, COLLAR_S),
            (R_SLEEVE, 1.0500), (0.0238, 1.0515), (0.0238, 1.0555), (R_SLEEVE, 1.0570),
            (R_SLEEVE, 1.0930), (0.0235, BAR_HALF), (0.0165, BAR_HALF), (0.0150, BAR_HALF - 0.0015)]
    knurl = {(0.000, 0.080), (0.215, 0.4025), (0.4075, 0.640)}
    hmats = []
    for j in range(len(half) - 1):
        span = (half[j][1], half[j + 1][1])
        hmats.append(KNURL_IDX if span in knurl else CHROME_IDX)
    prof = [(r, -z) for r, z in reversed(half[1:])] + half
    mats = list(reversed(hmats)) + hmats
    return prof, mats


def bumper_profile(R, T):
    H = HUB_H
    pts = [(R_HOLE, 0.0), (0.058, 0.0), (0.0605, H), (0.197, H), (0.200, 0.001), (0.219, 0.001),
           (R, 0.007), (R, T - 0.007), (0.219, T - 0.001), (0.200, T - 0.001), (0.197, T - H),
           (0.0605, T - H), (0.058, T), (R_HOLE, T)]
    hub = {0, 1, 11, 12, 13}
    return pts, hub


def iron_profile(R, T):
    k = R / 0.114
    hub, web0, web1, rim = 0.045 * k, 0.050 * k, 0.098 * k, 0.101 * k
    rec = 0.27 * T
    pts = [(R_HOLE, 0.0), (hub, 0.0), (web0, rec), (web1, rec), (rim, 0.0), (R - 0.002, 0.0),
           (R, 0.003), (R, T - 0.003), (R - 0.002, T), (rim, T), (web1, T - rec), (web0, T - rec),
           (hub, T), (R_HOLE, T)]
    return pts


def add_plate(bm, key, centre, rot, phase):
    R, T, mkey, kind, _num = PLATES[key]
    mat = PLATE_MAT[mkey]
    if kind == "bumper":
        pts, hub = bumper_profile(R, T)
        segm = [CHROME_IDX if j in hub else mat for j in range(len(pts))]
    else:
        pts = iron_profile(R, T)
        segm = [mat] * len(pts)
    add_lathe(bm, pts, PLATE_SEGS, mat, center=centre, rot=rot, seg_mats=segm, phase=phase)
    return T


def add_clip(bm, origin, a_out, up, s_face):
    """Coiled spring clip gripping the sleeve, its coil bitten into the face
    at ``s_face``; two handle legs with rubber grips."""
    rot = frame(a_out, up)
    rc = R_SLEEVE - CLIP_GRIP + R_WIRE
    pitch = 2.0 * R_WIRE + 0.0006
    a0 = math.radians(22.0)
    h0 = a0 + math.radians(15.0)
    h1 = 4.0 * math.pi - h0
    steps = 44

    def loc(r, ang, z):
        return Vector((r * math.cos(ang), r * math.sin(ang), z))

    path = [loc(rc + 0.056, a0, 0.005), loc(rc + 0.034, a0, 0.005), loc(rc + 0.014, a0, 0.004),
            loc(rc + 0.004, a0 + math.radians(6.0), 0.002)]
    for i in range(steps + 1):
        ang = h0 + (h1 - h0) * i / steps
        path.append(loc(rc, ang, pitch * (ang - h0) / (2.0 * math.pi)))
    ze = pitch * (h1 - h0) / (2.0 * math.pi)
    path += [loc(rc + 0.004, -a0 - math.radians(6.0), ze + 0.002),
             loc(rc + 0.014, -a0, ze + 0.004), loc(rc + 0.034, -a0, ze + 0.005),
             loc(rc + 0.056, -a0, ze + 0.005)]
    wire = add_tube(bm, [origin + rot @ p for p in path], R_WIRE, 6, CHROME_IDX)
    grips = []
    for ang, z in ((a0, 0.005), (-a0, ze + 0.005)):
        d = rot @ Vector((math.cos(ang), math.sin(ang), 0.0))
        c = origin + rot @ loc(rc + 0.028, ang, z)
        grips += add_lathe(bm, [(0.0030, -0.001), (0.0045, 0.001), (0.0048, 0.024),
                                (0.0040, 0.030), (0.0020, 0.031)], 12, RUBBER_IDX,
                           center=c, rot=frame(d, a_out), solid=True)
    s_min = min((v.co - origin).dot(a_out) for v in wire)
    shift = a_out * (s_face - CLIP_BITE - s_min)
    for v in wire + grips:
        v.co += shift


def add_stack(bm, origin, a_out, up, s_stop, keys, gap_at=None, clip=False):
    """Plates hung on a sleeve from the stop face outward, each hub bitten
    PLATE_BITE into the one inside it; numerals on the outermost bumper."""
    rot = frame(a_out, up)
    s = s_stop - PLATE_BITE
    placed = []
    for i, key in enumerate(keys):
        if gap_at == i:
            s += GAP_PLATE
        centre = origin + a_out * s - up * SAG
        # bores turned a third and two thirds of a segment: no bore facet is
        # parallel to the sleeve's or to its neighbour's, so none share a plane
        T = add_plate(bm, key, centre, rot, (1 + i % 2) * 2.0 * math.pi / (3 * PLATE_SEGS))
        placed.append((key, centre, T))
        s += T - PLATE_BITE
    bumpers = [p for p in placed if PLATES[p[0]][3] == "bumper"]
    if bumpers:
        key, centre, T = bumpers[-1]
        face = centre + a_out * (T - HUB_H)
        e_u = (-a_out).cross(up).normalized()
        for q, (text, sgn) in enumerate(zip(PLATES[key][4], (1.0, -1.0))):
            add_number(bm, text, face + up * (sgn * TEXT_R), e_u * sgn, up * sgn, a_out,
                       TEXT_CELL, TXT_PROUD, TXT_BITE, DEC_STEP, 2 * q, DECAL_IDX)
    if clip:
        add_clip(bm, origin, a_out, up, s + PLATE_BITE)


def bar_pose(hook_high, float_bar):
    """Bar centre, axis and up from the two saddles it rests in."""
    yl, zl = saddle_axis(HOOK_HOLE)
    _yr, zr = saddle_axis(HOOK_HOLE + (1 if hook_high else 0))
    theta = math.atan2(zr - zl, 2.0 * UP_X)
    a = Vector((math.cos(theta), 0.0, math.sin(theta)))
    up = Vector((-math.sin(theta), 0.0, math.cos(theta)))
    c = Vector((0.0, yl, 0.5 * (zl + zr) + (FLOAT_BAR if float_bar else 0.0)))
    return c, a, up


def add_barbell(bm, hook_high, float_bar, gap_plate, odd_load):
    c, a, up = bar_pose(hook_high, float_bar)
    prof, mats = bar_profile()
    add_lathe(bm, prof, BAR_SEGS, CHROME_IDX, center=c, rot=frame(a, up), solid=True,
              seg_mats=mats)
    for side in (-1.0, 1.0):
        keys = ODD_LOAD if (odd_load and side < 0) else BAR_LOAD
        gap = 2 if (gap_plate and side > 0) else None
        add_stack(bm, c, a * side, up, COLLAR_S, keys, gap_at=gap, clip=True)


def horn_profile():
    L = HORN_L
    return [(0.018, -0.004), (R_SLEEVE, -0.004), (R_SLEEVE, 0.004), (0.036, 0.005), (0.038, 0.007),
            (0.038, 0.014), (0.036, HORN_STOP), (R_SLEEVE, HORN_STOP), (R_SLEEVE, L - 0.006),
            (0.0235, L), (0.016, L + 0.0015)]


def add_horn(bm, side, z, keys, bevel_verts, loose=False):
    face_x = side * (UP_X + UP_HALF) + (side * LOOSE_HORN if loose else 0.0)
    a_out = Vector((side, 0.0, 0.0))
    o_face = Vector((face_x, UP_Y[1], z))
    bevel_verts += add_prism(bm, rrect(0.034, 0.066, 0.008), -PLATE_BITE_UP, WELD_T, o_face,
                             frame(a_out, YAX), POWDER_IDX)
    origin = o_face + a_out * WELD_T
    add_lathe(bm, horn_profile(), PLATE_SEGS, ZINC_IDX, center=origin, rot=frame(a_out, ZAX),
              solid=True)
    for k, dz in enumerate((-HORN_BOLT, HORN_BOLT)):
        add_bolt(bm, origin + ZAX * dz, a_out, k)
    add_stack(bm, origin, a_out, ZAX, HORN_STOP, keys)


def add_dumbbell(bm, pos, yaw_deg):
    """Hex dumbbell lying on a flat of each head."""
    yaw = math.radians(yaw_deg)
    d = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    za = DB_HEAD_R * math.cos(math.pi / 6.0)
    c = Vector((pos[0], pos[1], za))
    for s in (-1.0, 1.0):
        add_lathe(bm, [(0.040, 0.000), (0.064, 0.003), (DB_HEAD_R, 0.009), (DB_HEAD_R, 0.091),
                       (0.064, 0.097), (0.040, DB_HEAD_L)], 6, RUBBER_IDX,
                  center=c + d * (s * 0.5 * DB_GAP), rot=frame(d * s, ZAX), solid=True,
                  phase=math.pi / 6.0)
    half = [(0.0165, 0.000), (0.0165, 0.052), (0.0170, 0.0545), (0.0215, 0.0560),
            (0.0215, 0.0660), (0.0180, 0.0700), (0.0140, 0.0860)]
    hm = [KNURL_IDX, CHROME_IDX, CHROME_IDX, CHROME_IDX, CHROME_IDX, CHROME_IDX]
    prof = [(r, -z) for r, z in reversed(half[1:])] + half
    mats = list(reversed(hm)) + hm
    add_lathe(bm, prof, 16, CHROME_IDX, center=c, rot=frame(d, ZAX), solid=True, seg_mats=mats)


def number_skip():
    """Holes whose numerals a J-hook or spotter plate covers."""
    covered = [(hole_z(HOOK_HOLE) - 0.080, hole_z(HOOK_HOLE) + 0.040),
               (hole_z(SPOT_HOLE) - 0.150, hole_z(SPOT_HOLE) + 0.035)]
    out = set()
    for k in range(N_HOLES):
        z = hole_z(k)
        for lo, hi in covered:
            if z + 0.007 > lo - 0.003 and z - 0.007 < hi + 0.003:
                out.add(k)
    return out


def build_rack_mesh(name, bevel_offset, bevel_segments, float_foot=False, offset_pin=False,
                    float_bar=False, hook_high=False, gap_plate=False, odd_load=False,
                    loose_horn=False):
    bm = bmesh.new()
    try:
        bevel_verts = []
        skip = number_skip()
        for side in (-1.0, 1.0):
            xc = side * UP_X
            add_upright(bm, xc, UP_Y[0], True, True, True, skip)
            add_upright(bm, xc, UP_Y[1], True, False, False, skip)
        add_frame(bm, bevel_verts, float_foot)
        for side in (-1.0, 1.0):
            xc = side * UP_X
            add_jhook(bm, xc, HOOK_HOLE + (1 if (hook_high and side > 0) else 0), bevel_verts)
            add_spotter(bm, xc, SPOT_HOLE, bevel_verts,
                        lift=OFFSET_PIN if (offset_pin and side < 0) else 0.0)
        add_barbell(bm, hook_high, float_bar, gap_plate, odd_load)
        for hi, (side, z, keys) in enumerate(HORNS):
            add_horn(bm, side, z, keys, bevel_verts, loose=loose_horn and hi == 2)
        for pos, yaw in DUMBBELLS:
            add_dumbbell(bm, pos, yaw)

        if bevel_offset > 0.0:
            # Chamfer the plates' rims, one pass per material with material=
            # set, over sorted edges.
            for mat_idx in (POWDER_IDX, UHMW_IDX):
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
        # Turned parts (bar, plates, pins, horns, clip) are smooth-shaded;
        # tube corners, hex heads, holes and chamfers stay crisp.
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
        bnode.inputs["Strength"].default_value = bump
        bnode.inputs["Distance"].default_value = 0.0004
        nt.links.new(tex.outputs["Fac"], bnode.inputs["Height"])
        nt.links.new(bnode.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def knurl_material():
    """Diamond knurl: a fine 3D checker in object space drives a bump, so the
    knurled zones read against the polished chrome beside them."""
    mat = principled("BarKnurl", (0.62, 0.62, 0.64, 1.0), 0.85, 0.50)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    chk = nt.nodes.new("ShaderNodeTexChecker")
    chk.inputs["Scale"].default_value = 320.0
    nt.links.new(coord.outputs["Object"], chk.inputs["Vector"])
    bnode = nt.nodes.new("ShaderNodeBump")
    bnode.inputs["Strength"].default_value = 0.8
    bnode.inputs["Distance"].default_value = 0.0006
    nt.links.new(chk.outputs["Fac"], bnode.inputs["Height"])
    nt.links.new(bnode.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def rack_materials():
    """(powder, bore, zinc, chrome, knurl, rubber, uhmw, decal, blue, yellow,
    green, iron): shared by the check and the render.

    The frame is an oxblood textured powder coat; the hole bores are the dark
    tube interior; pins, bolts, horns and the pull-up bar bright zinc; the
    bar's sleeves, collars and the clips polished chrome with a knurled
    shaft; pads, caps, grips and dumbbell heads black rubber; the saddle and
    spotter liners off-white UHMW; the hole and plate numerals white; the
    bumpers flecked blue, yellow and green rubber; the change plates black
    cast iron.
    """
    powder = principled("RackPowderCoat", (0.30, 0.030, 0.024, 1.0), 0.0, 0.44,
                        roughness_var=0.08, mottle=0.10, noise_scale=180.0, bump=0.25,
                        bump_scale=900.0)
    bore = principled("RackBore", (0.012, 0.012, 0.013, 1.0), 0.3, 0.75)
    zinc = principled("RackZinc", (0.62, 0.63, 0.66, 1.0), 1.0, 0.30,
                      roughness_var=0.06, noise_scale=120.0)
    chrome = principled("BarChrome", (0.86, 0.86, 0.88, 1.0), 1.0, 0.20,
                        roughness_var=0.04, noise_scale=90.0)
    knurl = knurl_material()
    rubber = principled("RackRubber", (0.022, 0.022, 0.024, 1.0), 0.0, 0.78,
                        roughness_var=0.08, noise_scale=80.0, bump=0.15, bump_scale=600.0)
    uhmw = principled("RackUHMW", (0.72, 0.71, 0.66, 1.0), 0.0, 0.50,
                      roughness_var=0.08, noise_scale=60.0)
    decal = principled("RackDecal", (0.86, 0.86, 0.83, 1.0), 0.0, 0.55)
    blue = principled("BumperBlue", (0.020, 0.075, 0.33, 1.0), 0.0, 0.72,
                      roughness_var=0.10, mottle=0.25, noise_scale=260.0, bump=0.2,
                      bump_scale=700.0)
    yellow = principled("BumperYellow", (0.70, 0.46, 0.020, 1.0), 0.0, 0.70,
                        roughness_var=0.10, mottle=0.20, noise_scale=260.0, bump=0.2,
                        bump_scale=700.0)
    green = principled("BumperGreen", (0.030, 0.26, 0.070, 1.0), 0.0, 0.72,
                       roughness_var=0.10, mottle=0.25, noise_scale=260.0, bump=0.2,
                       bump_scale=700.0)
    iron = principled("PlateCastIron", (0.045, 0.045, 0.050, 1.0), 0.7, 0.52,
                      roughness_var=0.10, mottle=0.25, noise_scale=150.0, bump=0.3,
                      bump_scale=500.0)
    return (powder, bore, zinc, chrome, knurl, rubber, uhmw, decal, blue, yellow, green, iron)


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
    return Vector(c), Vector(vecs[:, -1 if largest else 0]).normalized()


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    out["uprights"] = [s for s in parts if POWDER_IDX in s.mats and BORE_IDX in s.mats
                       and s.size.z > 1.5]
    out["bar"] = next((s for s in parts if KNURL_IDX in s.mats and s.size.x > 2.0), None)
    out["pads"] = [s for s in parts if s.mat == RUBBER_IDX and s.hi.z < 0.03]
    out["heads"] = [s for s in parts if s.mat == RUBBER_IDX and 0.10 < s.hi.z < 0.14
                    and s.lo.z < 0.05]
    out["pins"] = [s for s in parts if s.mat == ZINC_IDX and s.size.y > 0.025
                   and s.size.y > s.size.x and s.size.y > s.size.z]
    out["liners"] = [s for s in parts if s.mat == UHMW_IDX and s.size.y < 0.15]
    out["plates"] = [s for s in parts if s.mat in PLATE_IDXS]
    out["horns"] = [s for s in parts if s.mat == ZINC_IDX and 0.25 < s.size.x < 0.40]
    out["clips"] = [s for s in parts if s.mat == CHROME_IDX and KNURL_IDX not in s.mats]
    return out


def radial(p, c, a):
    d = p - c
    return (d - a * d.dot(a)).length


def hole_centres(me, cls):
    """Every punched hole's centre, from its pocket floor (bore faces facing
    along y), grouped per upright face and hole."""
    ups = cls["uprights"]
    owner = {}
    for ui, s in enumerate(ups):
        for vi in s.verts:
            owner[vi] = ui
    groups = {}
    for p in me.polygons:
        if p.material_index != BORE_IDX or abs(p.normal.y) < 0.99:
            continue
        ui = owner.get(p.vertices[0])
        if ui is None:
            continue
        key = (ui, 1 if p.normal.y > 0 else -1, round((p.center.z - HOLE_Z0) / PITCH))
        groups.setdefault(key, set()).update(p.vertices)
    out = []
    for key, vs in groups.items():
        pts = [me.vertices[i].co for i in vs]
        out.append(sum(pts, Vector()) / len(pts))
    return out


def pin_audit(me, cls):
    holes = hole_centres(me, cls)
    offs, depths = [], []
    for pin in cls["pins"]:
        tip_y = pin.hi.y
        cx, cz = pin.mean.x, pin.mean.z
        best = None
        for h in holes:
            if abs(h.y - tip_y) > 0.02:
                continue
            d = math.hypot(h.x - cx, h.z - cz)
            if best is None or d < best[0]:
                best = (d, h)
        if best is None:
            offs.append(9.0)
            depths.append(0.0)
            continue
        offs.append(best[0])
        face_y = best[1].y - HOLE_DEPTH     # front faces: the pocket runs to +y
        depths.append(tip_y - face_y)
    return {"holes": len(holes), "offs": offs, "depths": depths}


def bar_frame(cls):
    bar = cls["bar"]
    c, a = pca_axis(bar.pts)
    if a.x < 0.0:
        a = -a
    return c, a


def seat_audit(cls):
    """Shaft underside to each J-hook liner, by a ray straight down from the
    bar axis at the liner's centre; the shaft radius read off the bar there."""
    bar = cls["bar"]
    c, a = bar_frame(cls)
    down = Vector((0.0, 0.0, -1.0))
    gaps = []
    for ln in cls["liners"]:
        xm = ln.centre.x
        o = c + a * ((xm - c.x) / a.x)
        hit, _n, _i, dist = ln.tree.ray_cast(o, down)
        bhit, _bn, _bi, bdist = bar.tree.ray_cast(o, down)
        gaps.append((dist - bdist) if (hit is not None and bhit is not None) else 9.0)
    tilt = math.degrees(math.asin(min(1.0, abs(a.z))))
    ts = [(p - c).dot(a) for p in bar.pts]
    return {"gaps": gaps, "tilt": tilt, "bar_len": max(ts) - min(ts)}


def stack_audit(cls):
    """Plates on the bar and the horns: each plate's axis against its sleeve's
    axis, and along it the gap from the stop face (collar or horn flange) to
    the first plate, plate to plate, and last plate to clip."""
    bar = cls["bar"]
    c, a = bar_frame(cls)
    axes = []
    # the bar: one stack per side, the stop at its collar face
    ts = [((p - c).dot(a), radial(p, c, a)) for p in bar.pts]
    for side in (-1.0, 1.0):
        stop = max(t * side for t, r in ts if r > R_SLEEVE + 0.004 and t * side > 0.0)
        axes.append(("bar", c, a * side, stop))
    for h in sorted(cls["horns"], key=lambda s: (s.mean.z, s.mean.x)):
        hc, ha = pca_axis(h.pts)
        if ha.dot(Vector((h.mean.x, 0.0, 0.0))) < 0.0:
            ha = -ha
        base = min((p - hc).dot(ha) for p in h.pts)
        o = hc + ha * base
        stop = max((p - o).dot(ha) for p in h.pts if radial(p, hc, ha) > R_SLEEVE + 0.004)
        axes.append(("horn", o, ha, stop))
    stacks = [[] for _ in axes]
    unassigned = 0
    coax = []
    for pl in cls["plates"]:
        best = None
        for k, (_kind, o, ax, _stop) in enumerate(axes):
            if (pl.mean - o).dot(ax) <= 0.0:
                continue
            d = radial(pl.mean, o, ax)
            if best is None or d < best[0]:
                best = (d, k)
        if best is None or best[0] > 0.01:
            unassigned += 1
            continue
        coax.append(best[0])
        stacks[best[1]].append(pl)
    gaps = []
    counts = []
    for k, (_kind, o, ax, stop) in enumerate(axes):
        seq = sorted(stacks[k], key=lambda s: (s.mean - o).dot(ax))
        counts.append(len(seq))
        prev = stop
        for pl in seq:
            ss = [(p - o).dot(ax) for p in pl.pts]
            gaps.append(min(ss) - prev)
            prev = max(ss)
        if _kind == "bar":
            clip = [cl for cl in cls["clips"] if (cl.mean - o).dot(ax) > 0.0]
            if len(clip) == 1:
                gaps.append(min((p - o).dot(ax) for p in clip[0].pts) - prev)
            else:
                gaps.append(9.0)
    return {"coax": coax, "gaps": gaps, "counts": counts, "unassigned": unassigned}


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


def balance_audit(cls):
    """The loaded bar's mass centre along its axis, from its midpoint."""
    c, a = bar_frame(cls)
    load = [cls["bar"]]
    load += [p for p in cls["plates"] if radial(p.mean, c, a) < 0.01]
    load += [cl for cl in cls["clips"] if radial(cl.mean, c, a) < 0.05]
    total = 0.0
    mom = 0.0
    sides = [0.0, 0.0]
    for s in load:
        vol, cen = shell_mass(s)
        if s.mat == IRON_IDX:
            rho = DENSITY["iron"]
        elif s.mat in PLATE_IDXS:
            rho = DENSITY["bumper"]
        else:
            rho = DENSITY["steel"]
        m = abs(vol) * rho
        t = (cen - c).dot(a)
        total += m
        mom += m * t
        if s is not cls["bar"]:
            sides[1 if t > 0.0 else 0] += m
    return {"mass": total, "offset": mom / total if total else 9.0, "sides": sides}


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
    img = bpy.data.images.new("RackNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = POWDER_IDX
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


FLOOR_NAMES = ("powder", "bore", "zinc", "chrome", "knurl", "rubber", "uhmw", "decal",
               "blue", "yellow", "green", "iron")


def check(skip_decimate, lift_z=False, stray_vert=False, float_foot=False, offset_pin=False,
          float_bar=False, hook_high=False, gap_plate=False, odd_load=False, loose_horn=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(float_foot=float_foot, offset_pin=offset_pin, float_bar=float_bar,
                 hook_high=hook_high, gap_plate=gap_plate, odd_load=odd_load,
                 loose_horn=loose_horn)
    low = build_rack_mesh("RackLow", bevel_offset=0.0006, bevel_segments=1, **flags)
    high = build_rack_mesh("RackHigh", bevel_offset=0.0006, bevel_segments=3, **flags)
    mats = rack_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the powder coat: the hook, spotter and base plates are
    # where the high mesh's rounder chamfer differs from the low.
    target = mats[POWDER_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("rack mesh did not build", 3),) + none3

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
    pads = [s.lo.z for s in cls["pads"]]
    heads = [s.lo.z for s in cls["heads"]]
    pins = pin_audit(low.data, cls)
    seat = seat_audit(cls) if cls["bar"] else {"gaps": [], "tilt": 90.0, "bar_len": 0.0}
    stacks = stack_audit(cls) if cls["bar"] else {"coax": [], "gaps": [9.0], "counts": [],
                                                  "unassigned": 99}
    bumper_d = [2.0 * max(radial(p, *pca_axis(s.pts, largest=False)) for p in s.pts)
                for s in cls["plates"] if s.mat != IRON_IDX]
    rack_h = max((s.hi.z for s in cls["uprights"]), default=0.0)
    bal = balance_audit(cls) if cls["bar"] else {"mass": 0.0, "offset": 9.0, "sides": [0, 0]}
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("rack has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "RackLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "RackLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_rack_mesh("RackColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "RackCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_weight_rack_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} pads={[round(z, 5) for z in pads]} "
          f"heads={[round(z, 5) for z in heads]}")
    print(f"measured holes={pins['holes']} pins={len(cls['pins'])} "
          f"pin_off={[round(o, 6) for o in pins['offs']]} "
          f"pin_depth={[round(d, 5) for d in pins['depths']]}")
    print(f"measured liners={len(cls['liners'])} seat={[round(g, 6) for g in seat['gaps']]} "
          f"tilt={seat['tilt']:.4f} bar_len={seat['bar_len']:.5f} rack_h={rack_h:.4f} "
          f"bumper_d={[round(d, 4) for d in bumper_d]}")
    print(f"measured stacks counts={stacks['counts']} unassigned={stacks['unassigned']} "
          f"coax_max={max(stacks['coax'], default=9.0):.6f} "
          f"gaps={[round(g, 5) for g in stacks['gaps']]}")
    print(f"measured load={bal['mass']:.3f}kg sides=({bal['sides'][0]:.3f},{bal['sides'][1]:.3f}) "
          f"offset={bal['offset']:.6f}")
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
    if (len(pads) != PAD_COUNT or max(pads) > ZMIN_EPS or len(heads) != DB_HEAD_COUNT
            or max(heads) > ZMIN_EPS):
        return (fail(f"supports: {len(pads)} pads (want {PAD_COUNT}) zmin "
                     f"{[round(z, 5) for z in pads]}, {len(heads)} dumbbell heads (want "
                     f"{DB_HEAD_COUNT}) zmin {[round(z, 5) for z in heads]} (each within "
                     f"{ZMIN_EPS} of 0)", 16),) + none3
    if (len(cls["pins"]) != PIN_COUNT or max(pins["offs"], default=9.0) > PIN_AXIS_TOL
            or any(not (PIN_DEPTH_MIN <= d <= PIN_DEPTH_MAX) for d in pins["depths"])):
        return (fail(f"pins: {len(cls['pins'])} (want {PIN_COUNT}), off their hole axes "
                     f"{[round(o, 5) for o in pins['offs']]} m (tol {PIN_AXIS_TOL}), depth "
                     f"{[round(d, 4) for d in pins['depths']]} (band {PIN_DEPTH_MIN}-"
                     f"{PIN_DEPTH_MAX})", 17),) + none3
    if (len(seat["gaps"]) != 2 or any(not (SEAT_MIN <= g <= SEAT_MAX) for g in seat["gaps"])):
        return (fail(f"bar not seated in both saddles: shaft-to-liner "
                     f"{[round(g, 5) for g in seat['gaps']]} m (band {SEAT_MIN} to {SEAT_MAX})",
                     18),) + none3
    if (seat["tilt"] > TILT_MAX_DEG or abs(seat["bar_len"] - BAR_LEN) > SIZE_TOL
            or abs(rack_h - RACK_H) > SIZE_TOL
            or any(abs(d - BUMPER_D) > SIZE_TOL for d in bumper_d)):
        return (fail(f"bar tilt {seat['tilt']:.3f} deg (max {TILT_MAX_DEG}), or size off: bar "
                     f"{seat['bar_len']:.4f}, rack {rack_h:.4f}, bumpers "
                     f"{[round(d, 4) for d in bumper_d]}", 19),) + none3
    if (stacks["unassigned"] or tuple(stacks["counts"]) != PLATE_COUNTS
            or max(stacks["coax"], default=9.0) > PLATE_COAX_TOL
            or any(not (STACK_GAP_MIN <= g <= STACK_GAP_MAX) for g in stacks["gaps"])):
        return (fail(f"plates not seated: counts {stacks['counts']} (want {list(PLATE_COUNTS)}), "
                     f"{stacks['unassigned']} off every sleeve, coax "
                     f"{max(stacks['coax'], default=9.0):.5f} (tol {PLATE_COAX_TOL}), gaps "
                     f"{[round(g, 5) for g in stacks['gaps']]} (band {STACK_GAP_MIN} to "
                     f"{STACK_GAP_MAX})", 20),) + none3
    if abs(bal["offset"]) > BALANCE_TOL:
        return (fail(f"load unbalanced: mass centre {bal['offset']:.5f} m off the bar's midpoint "
                     f"(tol {BALANCE_TOL}); sides {bal['sides'][0]:.2f} / {bal['sides'][1]:.2f} kg",
                     21),) + none3
    if ncomp != COMPONENTS:
        return (fail(f"assembly splits into {ncomp} components (want {COMPONENTS}: the rack "
                     f"and {len(DUMBBELLS)} dumbbells) {comp_sizes}", 22),) + none3
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

    # The house rig scaled to a 2.1 m rack: warm key upper left, cool fill
    # low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-2.6, -3.0, 2.4), 190.0, 1.8, (1.0, 0.93, 0.84), spread=35.0)
    light("Fill", (3.2, -2.4, 0.2), 32.0, 3.5, (0.72, 0.82, 1.0))
    light("Rim", (-1.4, 2.0, 1.6), 110.0, 1.5, (0.62, 0.78, 1.0))
    light("Wedge", (1.6, 2.2, 0.3), 210.0, 2.4, (1.0, 0.68, 0.38),
          target=(centre.x + 2.2, centre.y + WALL_Y, 0.9))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.45, -0.89, 0.0)).normalized()
    cam.location = centre + view * 6.5 + Vector((0.0, 0.0, 0.85))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.04))
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
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "WEBP" if path.lower().endswith(".webp") else "PNG"
    if path.lower().endswith(".webp"):
        scene.render.image_settings.quality = 90
    scene.render.filepath = path
    # Standard, not AgX: AgX washes the red powder coat and the bumpers toward pastel
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 23
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
    p.add_argument("--float-foot", action="store_true")
    p.add_argument("--offset-pin", action="store_true")
    p.add_argument("--float-bar", action="store_true")
    p.add_argument("--hook-high", action="store_true")
    p.add_argument("--gap-plate", action="store_true")
    p.add_argument("--odd-load", action="store_true")
    p.add_argument("--loose-horn", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_foot=args.float_foot,
        offset_pin=args.offset_pin,
        float_bar=args.float_bar,
        hook_high=args.hook_high,
        gap_plate=args.gap_plate,
        odd_load=args.odd_load,
        loose_horn=args.loose_horn,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("weight-rack OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
