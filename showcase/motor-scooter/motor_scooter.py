"""Game-ready 1960s Italian motor scooter — a showcase piece, not an example.

Asserts budget conformance of a procedural step-through motor scooter,
parked upright on its centre stand, after composing shipped pipeline
pieces: bmesh construction, UVs, nine materials, high-to-low normal bake,
LOD chain, convex collider, Unity glTF export.

The body is pressed steel: a central tail lofted from superellipse sections
(a steep front face rising from the floorboard to the saddle, a flat back
under it, and a tail sloping down over the rear wheel), two bulbous side
cowls sunk into it (the right one, over the engine, carries six pressed
louvres), a floorboard with rubber runner strips and chrome edge trims, and
a leg shield curved back at its edges, rimmed in a chrome trim, with a horn
cast and grille on its front. A front mudguard with a chrome crest turns
with a single-sided fork: a steering column raked 22 degrees, a crown, a
fork leg on the left and a trailing link with a coil spring. The headset
carries the headlamp, the speedometer, grips, levers and two mirrors on
stalks. A two-tone dual saddle (cream top, oxblood sides) has piping round
its top panel and a grab strap across it. Both wheels are 10-inch split
rims (two pressed halves, five nuts, a hub cap) in block-tread tyres, with a
finned brake drum on the arm side. Under the right cowl an alloy engine
case with a finned cylinder feeds a header pipe and a black silencer with a
chrome tailpipe; a kick-start lever and a brake pedal sit on the right. A
chrome luggage rack, a tail lamp and a blank number plate finish the tail.
The centre stand's two rubber feet and both tyres stand on the ground.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-tyre`` both tyres and both
stand feet on the ground, ``--toe-wheel`` the wheel axes horizontal and
parallel, ``--steep-head`` the steering trail, ``--odd-body`` the body's
mirror symmetry, ``--short-wheelbase`` the wheelbase band,
``--narrow-stand`` the mass centre inside the support polygon,
``--pop-speedo`` one connected assembly, ``--lift-shield`` the leg
shield's foot seated in the floorboard.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python motor_scooter.py --
    blender --background --python motor_scooter.py -- --skip-decimate
    blender --background --python motor_scooter.py -- --output scooter.png
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

# --- Wheels and steering (nose at +X, rider's left at +Y) --------------------
R_TYRE = 0.215              # tyre radius over the centre rib (10-inch rim, 3.50 tyre)
AXLE_F = 0.600              # front axle x
AXLE_R = -0.600             # rear axle x: a 1.20 m wheelbase
TREAD_H = 0.0035            # tread block height
TREAD_CYCLES = 16           # block pitches per revolution (even: a ring points down)
TREAD_FRACS = (0.0, 0.06, 0.50, 0.56)
RIM_SEGS = 32
HUB_Y = 0.105               # the fork leg / link plane (front, +Y); engine arm (rear, -Y)
STEER_RAKE_DEG = 26.0       # steering axis from vertical
TRAIL_DESIGN = 0.075        # steering axis meets the ground this far ahead of the contact
CROWN_Z = 0.470             # fork crown on the column
COLUMN_TOP_Z = 0.985        # the column ends inside the headset

# --- Body -----------------------------------------------------------------------
SPINE_N = 2.6
SPINE_PART = 0.55
SPINE_SEGS = 36
SPINE_STATIONS = 30
SPINE_XE = (-0.905, -0.045)
SPINE_TOP_KEYS = [(-0.905, 0.470), (-0.880, 0.545), (-0.840, 0.605), (-0.780, 0.655),
                  (-0.700, 0.690), (-0.580, 0.705), (-0.400, 0.705), (-0.280, 0.690),
                  (-0.200, 0.640), (-0.140, 0.540), (-0.100, 0.420), (-0.070, 0.310),
                  (-0.045, 0.228)]
SPINE_BOT_KEYS = [(-0.905, 0.430), (-0.840, 0.455), (-0.720, 0.472), (-0.480, 0.472),
                  (-0.400, 0.440), (-0.340, 0.330), (-0.280, 0.215), (-0.045, 0.205)]
SPINE_W_KEYS = [(-0.905, 0.055), (-0.860, 0.088), (-0.760, 0.125), (-0.550, 0.150),
                (-0.300, 0.150), (-0.140, 0.140), (-0.045, 0.115)]
COWL_C = (-0.575, 0.178, 0.440)
COWL_AX = 0.270
COWL_AY = 0.132             # outboard half-width; inboard is COWL_AY_IN
COWL_AY_IN = 0.105
COWL_AZT = 0.225
COWL_AZB = 0.190
COWL_N = 2.5
COWL_TAPER = 0.35
COWL_RISE = 0.035
COWL_NU = 22
COWL_NV = 36
LOUVRES = 6
FLOOR_TOP = 0.232
SH_Z0 = 0.200               # leg shield foot (inside the floorboard)
SH_Z0_LIFTED = 0.236        # --lift-shield: the foot stood 4 mm above the floor
SH_X0 = 0.345
SH_Z1 = 0.935               # crown of the shield's top edge, inside the headset
SH_X1 = 0.248
SH_ARCH = 0.075             # the top edge falls this much to its corners
SH_HW0 = 0.205              # as wide as the floorboard at its foot
SH_HW1 = 0.185
SH_SWEEP0 = 0.075           # edges swept back behind the centre, at the foot ...
SH_SWEEP1 = 0.135           # ... and at the top: convex in plan
SH_BULGE = 0.020            # forward bulge at mid-height
SH_T = 0.010
FILLET_R = 0.045            # floorboard-to-shield and floorboard-to-tail radius
FLOOR_HW = 0.215
FLOOR_X = (-0.060, 0.360)
TIE_Z = (0.485, 0.925)     # horn cast: from the fork crown up into the headset
MG_R = 0.232                # mudguard edge radius about the front axle
MG_H = 0.040                # crown rise over the edge
MG_HW = 0.082
MG_T0 = -20.0
MG_T1 = 118.0

# --- Headset and saddle ------------------------------------------------------------
HS_N = 2.4
HS_Z = 0.985
HS_KEYS_A = [(0.0, 0.152), (0.07, 0.140), (0.13, 0.092), (0.19, 0.052), (0.25, 0.030)]
HS_KEYS_B = [(0.0, 0.080), (0.07, 0.075), (0.13, 0.055), (0.19, 0.037), (0.25, 0.026)]
HS_KEYS_X = [(0.0, 0.205), (0.12, 0.180), (0.25, 0.152)]
GRIP_Y = (0.240, 0.350)
SEAT_X0 = -0.740
SEAT_X1 = -0.190
SEAT_BITE = 0.012
SEAT_TOP_KEYS = [(-0.740, 0.782), (-0.700, 0.800), (-0.620, 0.808), (-0.540, 0.806),
                 (-0.480, 0.795), (-0.420, 0.790), (-0.300, 0.792), (-0.230, 0.780),
                 (-0.190, 0.745)]
SEAT_W_KEYS = [(-0.740, 0.100), (-0.660, 0.128), (-0.500, 0.132), (-0.350, 0.134),
               (-0.240, 0.120), (-0.190, 0.084)]
SEAT_PANEL = 0.95           # half-angle (rad) of the cream top panel in the section
STRAP_X = -0.470

# --- Stand -------------------------------------------------------------------------
STAND_X = (-0.220, -0.300)  # pivot x, foot x
STAND_PIVOT_Z = 0.198
STAND_PIVOT_Y = 0.100
STAND_FOOT_Y = 0.150
STAND_FOOT_Y_NARROW = 0.060  # --narrow-stand
STAND_R = 0.011

# --- Falsifier sizes -----------------------------------------------------------------
FLOAT_TYRE = 0.004
TOE_DEG = 2.5
STEEP_DEG = 6.0
ODD_BODY = 0.0035
SHORT_WB = 0.015
POP_SPEEDO = 0.030

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (1.790, 0.730, 1.244)
BASE_TRIS_MIN = 44400
BASE_TRIS_MAX = 45700
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 9
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 1850
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
PAINT_FACES_MIN = 6440
CHROME_FACES_MIN = 4350
RUBBER_FACES_MIN = 3250
SEAT_FACES_MIN = 1030
CREAM_FACES_MIN = 265
GLASS_FACES_MIN = 495
LAMP_FACES_MIN = 170
ALLOY_FACES_MIN = 3620
DARK_FACES_MIN = 2060

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
TYRE_COUNT = 2
PAD_COUNT = 2
CONTACT_BAND = 2e-5          # a support's sole: its lowest ring of vertices
# Wheel alignment: axles horizontal (camber) and parallel in plan (toe).
CAMBER_MAX_DEG = 0.3
TOE_MAX_DEG = 0.3
# Steering: the column's axis meets the ground ahead of the front contact.
TRAIL_MIN = 0.055
TRAIL_MAX = 0.090
TRAIL_Y_TOL = 0.002
# Body symmetry: every body vertex has a partner at its mirror position.
MIRROR_EPS = 0.0005
BODY_LEN = 0.862
SEAT_HEIGHT = 0.807
SIZE_TOL = 0.004
WHEELBASE = 1.200
WHEELBASE_TOL = 0.004
# Stance: the mass centre stands this far inside the support polygon.
DENSITY = (300.0, 2500.0, 700.0, 250.0, 250.0, 2500.0, 1200.0, 2200.0, 2600.0)
STANCE_MARGIN = 0.080
# Seam: the leg shield's foot stands this deep in the floorboard's pressing.
SEAM_MIN = 0.020
SEAM_MAX = 0.040
# Hero yaw: the nose turned toward the camera's right.
HERO_YAW_DEG = -58.0
WALL_Y = 2.6

PAINT_IDX = 0
CHROME_IDX = 1
RUBBER_IDX = 2
SEAT_IDX = 3
CREAM_IDX = 4
GLASS_IDX = 5
LAMP_IDX = 6
ALLOY_IDX = 7
DARK_IDX = 8

ZAX = Vector((0.0, 0.0, 1.0))
YAX = Vector((0.0, 1.0, 0.0))
XAX = Vector((1.0, 0.0, 0.0))
TAN_RAKE = math.tan(math.radians(STEER_RAKE_DEG))
STEER_X0 = AXLE_F + TRAIL_DESIGN
STEER_DIR = Vector((-math.sin(math.radians(STEER_RAKE_DEG)), 0.0,
                    math.cos(math.radians(STEER_RAKE_DEG))))


def col_x(z):
    """The steering axis's x at height z."""
    return STEER_X0 - z * TAN_RAKE


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


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False, seg_mats=None, cap_mats=None, rmod=None):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: the profile
    is an open polyline closed by n-gon caps at its two ends; otherwise it
    is a closed polygon revolved into a ring shell. ``rmod(i, j)`` scales the
    radius of profile point ``j`` on ring ``i``."""
    c = Vector(center)
    m = rot if rot is not None else Matrix.Identity(3)
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        ring = []
        for j, (r, z) in enumerate(profile):
            rr = r * (rmod(i, j) if rmod else 1.0)
            ring.append(bm.verts.new(c + m @ Vector((rr * ca, rr * sa, z))))
        rings.append(ring)
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


def fillet_path(pts, rf, steps=4):
    pts = [Vector(p) for p in pts]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, p, b = pts[i - 1], pts[i], pts[i + 1]
        r = min(rf, (a - p).length * 0.45, (b - p).length * 0.45)
        p0 = p + (a - p).normalized() * r
        p1 = p + (b - p).normalized() * r
        for k in range(steps + 1):
            t = k / steps
            out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * p + t * t * p1)
    out.append(pts[-1])
    return out


def fillet_corners(pts, rf, steps=4, min_deg=25.0):
    """Fillet only the vertices where the path turns by more than min_deg."""
    pts = [Vector(p) for p in pts]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, p, b = pts[i - 1], pts[i], pts[i + 1]
        if (p - a).angle(b - p, 0.0) < math.radians(min_deg):
            out.append(p)
            continue
        r = min(rf, (a - p).length * 0.45, (b - p).length * 0.45)
        p0 = p + (a - p).normalized() * r
        p1 = p + (b - p).normalized() * r
        for k in range(steps + 1):
            t = k / steps
            out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * p + t * t * p1)
    out.append(pts[-1])
    return out


def add_bar(bm, pts, wax, half_w, half_t, rc, mat_idx, fillet=0.008, filleted=False):
    """Flat bar bent in the plane normal to ``wax``: its width lies along
    ``wax``, its thickness in the bending plane; rounded-rectangle section."""
    pts = [Vector(p) for p in pts] if filleted else fillet_path(pts, fillet)
    wax = Vector(wax).normalized()
    sec = rrect(half_w, half_t, rc, 2)
    rings = []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        t = (b - a).normalized()
        w = (wax - t * wax.dot(t)).normalized()
        th = t.cross(w)
        rings.append([bm.verts.new(p + w * x + th * y) for x, y in sec])
    n = len(sec)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_sheet(bm, surf, nu, nv, thick, mat_idx):
    """A closed plate: ``surf(u, v) -> (point, normal)`` over the unit square,
    offset ``thick`` back along the normal, rims stitched round the edge."""
    front, back = [], []
    for j in range(nv + 1):
        rf, rb = [], []
        for i in range(nu + 1):
            p, n = surf(i / nu, j / nv)
            rf.append(bm.verts.new(p))
            rb.append(bm.verts.new(p - n * thick))
        front.append(rf)
        back.append(rb)
    faces = []
    for j in range(nv):
        for i in range(nu):
            faces.append(bm.faces.new((front[j][i], front[j][i + 1], front[j + 1][i + 1],
                                       front[j + 1][i])))
            faces.append(bm.faces.new((back[j][i], back[j + 1][i], back[j + 1][i + 1],
                                       back[j][i + 1])))
    rim = ([(0, i) for i in range(nu + 1)] + [(j, nu) for j in range(1, nv + 1)]
           + [(nv, i) for i in reversed(range(nu))] + [(j, 0) for j in reversed(range(1, nv))])
    for k in range(len(rim)):
        (ja, ia), (jb, ib) = rim[k], rim[(k + 1) % len(rim)]
        faces.append(bm.faces.new((front[jb][ib], front[ja][ia], back[ja][ia], back[jb][ib])))
    _mark(faces, mat_idx)
    return [v for row in front + back for v in row]


def add_loft(bm, rings_pts, mat_idx, seg_mats=None):
    """Closed loops [[Vector]] lofted in order, n-gon caps at both ends.
    ``seg_mats[k][j]`` is the material of the face between loop k and k+1
    at loop point j."""
    rings = [[bm.verts.new(p) for p in loop] for loop in rings_pts]
    n = len(rings[0])
    faces = []
    for k, (r0, r1) in enumerate(zip(rings, rings[1:])):
        for j in range(n):
            m = (j + 1) % n
            f = bm.faces.new((r0[j], r0[m], r1[m], r1[j]))
            f.material_index = seg_mats[k][j] if seg_mats else mat_idx
            faces.append(f)
    f0 = bm.faces.new(tuple(reversed(rings[0])))
    f1 = bm.faces.new(tuple(rings[-1]))
    f0.material_index = mat_idx
    f1.material_index = mat_idx
    return [v for ring in rings for v in ring]


def hull2d(pts):
    """Convex hull, counter-clockwise (monotone chain)."""
    pts = sorted(set((round(x, 9), round(z, 9)) for x, z in pts))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 1e-12:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 1e-12:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def comb_outline(half_len, base_lo, base_hi, ribs, rib_half, rib_top):
    """Grille section: a base strip with ``ribs`` teeth standing on it."""
    pts = [(-half_len, base_lo), (half_len, base_lo), (half_len, base_hi)]
    pitch = 2.0 * half_len / ribs
    for k in reversed(range(ribs)):
        c = -half_len + pitch * (k + 0.5)
        pts += [(c + rib_half, base_hi), (c + rib_half, rib_top),
                (c - rib_half, rib_top), (c - rib_half, base_hi)]
    pts.append((-half_len, base_hi))
    return pts


def thick_profile(centre, t):
    """A closed (r, z) polygon: the polyline ``centre`` offset t/2 either side."""
    pts = [Vector((r, z)) for r, z in centre]
    left, right = [], []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        d = (b - a).normalized()
        nrm = Vector((-d.y, d.x))
        left.append(p + nrm * (0.5 * t))
        right.append(p - nrm * (0.5 * t))
    return [(p.x, p.y) for p in left] + [(p.x, p.y) for p in reversed(right)]


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


def pchip(keys):
    """Monotone cubic through (x, y) keys (Fritsch-Carlson): no overshoot."""
    xs = [k[0] for k in keys]
    ys = [k[1] for k in keys]
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [d[0]] + [0.0] * (n - 2) + [d[-1]]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] > 0.0:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def f(x):
        x = min(max(x, xs[0]), xs[-1])
        i = 0
        while i < n - 2 and x > xs[i + 1]:
            i += 1
        t = (x - xs[i]) / h[i]
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1])
    return f


def _se(c, n):
    return math.copysign(abs(c) ** (2.0 / n), c)


_SP_TOP = pchip(SPINE_TOP_KEYS)
_SP_BOT = pchip(SPINE_BOT_KEYS)
_SP_W = pchip(SPINE_W_KEYS)
_SEAT_TOP = pchip(SEAT_TOP_KEYS)
_SEAT_W = pchip(SEAT_W_KEYS)
_HS_A = pchip(HS_KEYS_A)
_HS_B = pchip(HS_KEYS_B)
_HS_X = pchip(HS_KEYS_X)


# --------------------------------------------------------------------------
# The body's closed forms
# --------------------------------------------------------------------------

def spine_dims(x):
    """(parting-line height, half-width, crown height over it, belly depth)."""
    top, bot = _SP_TOP(x), _SP_BOT(x)
    zc = bot + SPINE_PART * (top - bot)
    return zc, _SP_W(x), top - zc, zc - bot


def spine_top(x, y):
    zc, w, ht, _hb = spine_dims(x)
    a = min(1.0, abs(y) / w)
    return zc + ht * (1.0 - a ** SPINE_N) ** (1.0 / SPINE_N)


def spine_F(p):
    zc, w, ht, hb = spine_dims(p.x)
    h = ht if p.z >= zc else hb
    return (abs(p.y) / w) ** SPINE_N + (abs(p.z - zc) / h) ** SPINE_N - 1.0


def spine_normal(p, eps=1e-5):
    g = Vector((
        spine_F(p + Vector((eps, 0, 0))) - spine_F(p - Vector((eps, 0, 0))),
        spine_F(p + Vector((0, eps, 0))) - spine_F(p - Vector((0, eps, 0))),
        spine_F(p + Vector((0, 0, eps))) - spine_F(p - Vector((0, 0, eps))),
    ))
    return g.normalized()


def add_spine(bm, odd_body):
    """The central tail: superellipse sections lofted along X, its parameter
    symmetric about the crown so the loop is its own mirror image."""
    x0, x1 = SPINE_XE
    xs = []
    for k in range(SPINE_STATIONS):
        s = k / (SPINE_STATIONS - 1)
        # denser at both ends, where the profile turns fastest
        xs.append(x0 + (x1 - x0) * (0.5 - 0.5 * math.cos(math.pi * s)))
    st = [(x0 - 0.0012, 0.0025)] + [(x, 0.0) for x in xs] + [(x1 + 0.0012, 0.0025)]
    loops = []
    for x, inset in st:
        zc, w, ht, hb = spine_dims(max(x0, min(x1, x)))
        loop = []
        for i in range(SPINE_SEGS):
            t = 2.0 * math.pi * i / SPINE_SEGS
            c, s = math.cos(t), math.sin(t)
            y = (w - inset) * _se(c, SPINE_N)
            z = zc + ((ht if s >= 0.0 else hb) - inset) * _se(s, SPINE_N)
            if odd_body:
                # a sideways bow, zero at both ends: an odd term in y
                y += ODD_BODY * math.sin(math.pi * (x - x0) / (x1 - x0)) ** 2
            loop.append(Vector((x, y, z)))
        loops.append(loop)
    return add_loft(bm, loops, PAINT_IDX)


def blob_point(c, ax, ay, azt, azb, n, taper, rise, u, v, side=1.0, ay_in=None):
    """A superquadric blob, narrowed and lifted toward its front (+X); its
    inboard half (toward y = 0) may be narrower than its outboard half."""
    cu, su = math.cos(u), math.sin(u)
    cv, sv = math.cos(v), math.sin(v)
    X = _se(cu, n) * _se(cv, n)
    Y = _se(cu, n) * _se(sv, n)
    Z = _se(su, n)
    tf = max(0.0, X)
    x = c[0] + ax * X
    wy = ay if (Y >= 0.0 or ay_in is None) else ay_in
    y = side * c[1] + side * wy * Y * (1.0 - taper * tf * tf)
    z = c[2] + (azt if Z > 0.0 else azb) * Z * (1.0 - 0.5 * taper * tf * tf) + rise * tf * tf
    return Vector((x, y, z))


def add_blob(bm, c, ax, ay, azt, azb, n, taper, rise, nu, nv, mat_idx, side=1.0, ay_in=None):
    loops = []
    d = 0.10
    for k in range(nu):
        u = -0.5 * math.pi + d + (math.pi - 2.0 * d) * k / (nu - 1)
        loop = [blob_point(c, ax, ay, azt, azb, n, taper, rise, u,
                           2.0 * math.pi * j / nv, side, ay_in) for j in range(nv)]
        if side < 0.0:
            loop.reverse()
        loops.append(loop)
    return add_loft(bm, loops, mat_idx)


def cowl_point(u, v, side):
    return blob_point(COWL_C, COWL_AX, COWL_AY, COWL_AZT, COWL_AZB, COWL_N, COWL_TAPER,
                      COWL_RISE, u, v, side, COWL_AY_IN)


def cowl_normal(u, v, side, eps=1e-4):
    du = cowl_point(u + eps, v, side) - cowl_point(u - eps, v, side)
    dv = cowl_point(u, v + eps, side) - cowl_point(u, v - eps, side)
    nrm = dv.cross(du).normalized()
    if nrm.y * side < 0.0:
        nrm = -nrm
    return nrm


_SHIELD = {"z0": SH_Z0}      # the foot height in force for this build


def shield_x(z):
    return SH_X0 + (SH_X1 - SH_X0) * (z - SH_Z0) / (SH_Z1 - SH_Z0)


def shield_point(u, v):
    """One pressed panel: its top edge arched up into the headset, its
    edges swept back round the rider's shins (convex in plan), a bulge
    forward at mid-height."""
    uu = 2.0 * u - 1.0
    z0 = _SHIELD["z0"]
    ztop = SH_Z1 - SH_ARCH * uu * uu
    z = z0 + (ztop - z0) * v
    hw = SH_HW0 + (SH_HW1 - SH_HW0) * v
    y = hw * uu
    sweep = SH_SWEEP0 + (SH_SWEEP1 - SH_SWEEP0) * v
    x = shield_x(z) - sweep * uu * uu + SH_BULGE * math.sin(math.pi * v)
    return Vector((x, y, z))


def shield_back(y, z):
    """The shield's rear face at (y, z), solved from its closed form."""
    z0 = SH_Z0
    u, v = 0.5, (z - z0) / (SH_Z1 - z0)
    for _ in range(8):
        hw = SH_HW0 + (SH_HW1 - SH_HW0) * v
        u = min(1.0, max(0.0, 0.5 * (y / hw + 1.0)))
        uu = 2.0 * u - 1.0
        v = (z - z0) / (SH_Z1 - SH_ARCH * uu * uu - z0)
    p, n = shield_surf(u, v)
    return p - n * SH_T


def spine_front_x(y, z):
    """Where the tail's steep front face stands at (y, z)."""
    lo, hi = -0.22, SPINE_XE[1]
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        w = spine_dims(mid)[1]
        if abs(y) < w and spine_top(mid, y) > z:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def bezier_fillet(a, k, b):
    """Quadratic fillet from ``a`` (on the floor) through corner ``k`` to ``b``."""
    def pt(t):
        return (1 - t) ** 2 * a + 2 * (1 - t) * t * k + t * t * b
    return pt


def add_fillet(bm, ends, span, mat_idx, thick=0.010, nu=14, nv=6):
    """A pressed fillet sheet between the floor and a rising face.
    ``ends(y, r) -> (a, k, b)``; the radius tapers to a sliver at +-span."""
    def surf(u, v):
        y = span * (2.0 * u - 1.0)
        r = FILLET_R * max(0.12, (1.0 - abs(y / span) ** 4)) ** 0.5
        pt = bezier_fillet(*ends(y, r))
        p = pt(v)
        dv = pt(min(1.0, v + 1e-3)) - pt(max(0.0, v - 1e-3))
        n = Vector((0.0, 1.0, 0.0)).cross(dv).normalized()
        if n.z < 0.0:
            n = -n
        return p, n
    return add_sheet(bm, surf, nu, nv, thick, mat_idx)


def shield_surf(u, v, eps=1e-4):
    p = shield_point(u, v)
    du = shield_point(min(1.0, u + eps), v) - shield_point(max(0.0, u - eps), v)
    dv = shield_point(u, min(1.0, v + eps)) - shield_point(u, max(0.0, v - eps))
    nrm = dv.cross(du).normalized()
    if nrm.x < 0.0:
        nrm = -nrm
    return p, nrm


def mudguard_point(u, v):
    th = math.radians(MG_T0 + (MG_T1 - MG_T0) * v)
    phi = math.radians(100.0) * (2.0 * u - 1.0)
    r = MG_R + MG_H * math.cos(phi)
    y = MG_HW * math.sin(phi)
    return Vector((AXLE_F + r * math.cos(th), y, R_TYRE + r * math.sin(th)))


def mudguard_surf(u, v, eps=1e-4):
    p = mudguard_point(u, v)
    du = mudguard_point(u + eps, v) - mudguard_point(u - eps, v)
    dv = mudguard_point(u, v + eps) - mudguard_point(u, v - eps)
    nrm = du.cross(dv).normalized()
    radial = Vector((p.x - AXLE_F, 0.0, p.z - R_TYRE))
    if nrm.dot(radial) < 0.0:
        nrm = -nrm
    return p, nrm


def headset_top(x, y):
    a, b, xc = _HS_A(abs(y)), _HS_B(abs(y)), _HS_X(abs(y))
    q = min(1.0, abs(x - xc) / a)
    return HS_Z + b * (1.0 - q ** HS_N) ** (1.0 / HS_N)


# --------------------------------------------------------------------------
# Assemblies
# --------------------------------------------------------------------------

TYRE_PROFILE = [
    (0.1250, -0.0330, "-"), (0.1360, -0.0400, "-"), (0.1600, -0.0468, "-"),
    (0.1830, -0.0455, "-"), (0.1980, -0.0390, "-"), (0.2045, -0.0310, "L"),
    (0.2085, -0.0200, "L"), (0.2105, -0.0095, "L"), (0.2115, -0.0030, "C"),
    (0.2115, 0.0030, "C"), (0.2105, 0.0095, "R"), (0.2085, 0.0200, "R"),
    (0.2045, 0.0310, "R"), (0.1980, 0.0390, "-"), (0.1830, 0.0455, "-"),
    (0.1600, 0.0468, "-"), (0.1360, 0.0400, "-"), (0.1250, 0.0330, "-"),
]
# pressed-steel rim half: the centreline of the sheet from the hub hole out
# over the dish, down the well and up the bead seat to the flange
RIM_CENTRE = [(0.030, 0.0006), (0.082, 0.0028), (0.102, 0.0110), (0.1140, 0.0280),
              (0.1260, 0.0350), (0.1380, 0.0395), (0.1430, 0.0460)]
RIM_T = 0.0036


def add_tyre(bm, centre):
    """Block-tread tyre: a continuous centre rib and staggered shoulder blocks,
    rings placed so the blocks' ends are near-vertical. A ring points straight
    down, so the centre rib's lowest vertices are exactly R_TYRE below the axle."""
    c = Vector(centre)
    rot = frame(YAX, ZAX)           # local x = +Z, local y = +X, local z = +Y
    rings = []
    for k in range(TREAD_CYCLES):
        for q, f in enumerate(TREAD_FRACS):
            a = 2.0 * math.pi * (k + f) / TREAD_CYCLES + math.pi
            ca, sa = math.cos(a), math.sin(a)
            ring = []
            for r, w, flag in TYRE_PROFILE:
                # left blocks stand on rings 1-2, right blocks on 3 and the
                # next cycle's 0: a ramp of 0.06 pitch at each block end
                up = (flag == "C" or (flag == "L" and q in (1, 2))
                      or (flag == "R" and q in (0, 3)))
                rr = r + (TREAD_H if up else 0.0)
                ring.append(bm.verts.new(c + rot @ Vector((rr * ca, rr * sa, w))))
            rings.append(ring)
    n = len(TYRE_PROFILE)
    faces = []
    for i in range(len(rings)):
        r0, r1 = rings[i], rings[(i + 1) % len(rings)]
        for j in range(n):
            k = (j + 1) % n
            faces.append(bm.faces.new((r0[j], r1[j], r1[k], r0[k])))
    _mark(faces, RUBBER_IDX)
    return [v for ring in rings for v in ring]


def add_wheel(bm, centre, hub_side):
    """Tyre, two rim halves, finned drum on the ``hub_side`` (+1 / -1 in Y),
    hub cap and five nuts on the open side. Returns every vertex."""
    c = Vector(centre)
    vs = add_tyre(bm, c)
    rot = frame(YAX, ZAX)
    prof = thick_profile(RIM_CENTRE, RIM_T)
    for s in (1.0, -1.0):
        half = [(r, s * w) for r, w in prof]
        if s < 0.0:
            half.reverse()
        vs += add_lathe(bm, half, RIM_SEGS, ALLOY_IDX, center=c, rot=rot,
                        phase=math.pi / RIM_SEGS)
    h = hub_side

    def fins(i, j):
        return 1.06 if (4 <= j <= 9 and j % 2 == 0) else 1.0

    drum = [(0.026, -0.0020), (0.058, 0.0045), (0.066, 0.0110), (0.068, 0.0200),
            (0.068, 0.0300), (0.068, 0.0400), (0.068, 0.0500), (0.068, 0.0600),
            (0.068, 0.0700), (0.066, 0.0780), (0.058, 0.0840), (0.040, 0.0880),
            (0.026, 0.0960), (0.024, 0.1240)]
    vs += add_lathe(bm, [(r, h * w) for r, w in drum], 32, ALLOY_IDX, center=c, rot=rot,
                    solid=True, rmod=fins)
    # axle nut outside the arm
    vs += add_lathe(bm, [(0.0150, h * 0.1200), (0.0165, h * 0.1240), (0.0165, h * 0.1330),
                         (0.0120, h * 0.1370)], 6, CHROME_IDX, center=c, rot=rot, solid=True,
                    phase=math.pi / 6.0)
    # open side: domed hub cap and the five split-rim nuts
    o = -h
    vs += add_lathe(bm, [(0.0290, o * -0.0035), (0.0320, o * 0.0060), (0.0290, o * 0.0130),
                         (0.0190, o * 0.0180), (0.0060, o * 0.0200)], 32, CHROME_IDX,
                    center=c, rot=rot, solid=True, phase=math.pi / 32.0)
    for k in range(5):
        a = 2.0 * math.pi * k / 5.0 + math.pi / 5.0
        p = c + rot @ Vector((0.050 * math.cos(a), 0.050 * math.sin(a), 0.0))
        e = 0.0003 * k       # staggered, so no two nut faces share a plane
        vs += add_lathe(bm, [(0.0075, o * (-0.0005 - e)), (0.0080, o * (0.0060 + e)),
                             (0.0065, o * (0.0090 + e)), (0.0030, o * (0.0100 + e))], 6,
                        CHROME_IDX, center=p, rot=rot, solid=True, phase=a)
    return vs


def add_front_end(bm, bevel_verts, toe_wheel, steep_head):
    """Front wheel, mudguard and crest, column, crown, fork leg, trailing
    link and spring."""
    c = Vector((AXLE_F, 0.0, R_TYRE))
    vs = add_wheel(bm, c, 1.0)
    if toe_wheel:
        m = Matrix.Rotation(math.radians(TOE_DEG), 3, "Z")
        for v in vs:
            v.co = c + m @ (v.co - c)
    add_sheet(bm, mudguard_surf, 12, 30, 0.004, PAINT_IDX)
    # chrome crest along the mudguard's crown
    crest = []
    for k in range(9):
        th = math.radians(34.0 + 38.0 * k / 8.0)
        crest.append(Vector((AXLE_F + (MG_R + MG_H + 0.0035) * math.cos(th), 0.0,
                             R_TYRE + (MG_R + MG_H + 0.0035) * math.sin(th))))
    add_bar(bm, crest, YAX, 0.0055, 0.0060, 0.0035, CHROME_IDX, filleted=True)
    # steering column on the raked axis, from the crown into the headset
    base = Vector((col_x(CROWN_Z), 0.0, CROWN_Z))
    d = STEER_DIR.copy()
    if steep_head:
        d = Matrix.Rotation(math.radians(STEEP_DEG), 3, "Y") @ d
    length = (COLUMN_TOP_Z - CROWN_Z) / STEER_DIR.z
    add_tube(bm, [base - d * 0.02, base + d * length], 0.021, 16, DARK_IDX)
    rot = frame(STEER_DIR, XAX)
    add_lathe(bm, [(0.020, -0.030), (0.034, -0.026), (0.038, -0.016), (0.038, 0.012),
                   (0.032, 0.020), (0.020, 0.024)], 24, DARK_IDX, center=base, rot=rot,
              solid=True)
    # fork leg: out of the crown to the left, down beside the mudguard and
    # forward to the link pivot ahead of the axle
    pivot = Vector((AXLE_F + 0.100, HUB_Y, R_TYRE + 0.040))
    leg = fillet_path([base + Vector((0.004, 0.010, -0.004)),
                       Vector((base.x + 0.020, HUB_Y, CROWN_Z - 0.030)),
                       Vector((AXLE_F - 0.060, HUB_Y, R_TYRE + 0.150)),
                       pivot + Vector((-0.010, 0.0, 0.020))], 0.06, 6)
    add_tube(bm, leg, 0.019, 16, DARK_IDX)
    # pivot boss, link and axle boss
    add_lathe(bm, [(0.020, -0.018), (0.024, -0.014), (0.024, 0.014), (0.020, 0.018)], 20,
              DARK_IDX, center=pivot, rot=frame(YAX, ZAX), solid=True)
    axle = Vector((AXLE_F, HUB_Y, R_TYRE))
    add_bar(bm, [pivot + Vector((0.004, 0.0, 0.0)), axle + Vector((-0.004, 0.0, 0.0))], YAX,
            0.013, 0.017, 0.006, DARK_IDX)
    # coil spring from the link up to the leg, with a damper rod inside
    s0 = pivot + (axle - pivot) * 0.35 + Vector((0.0, 0.0, 0.012))
    s1 = Vector((AXLE_F - 0.030, HUB_Y, R_TYRE + 0.170))
    ax = (s1 - s0).normalized()
    add_tube(bm, [s0 - ax * 0.010, s1 + ax * 0.012], 0.0075, 12, CHROME_IDX)
    e1 = frame(ax, YAX)
    coil = []
    turns = 7.0
    for k in range(85):
        t = k / 84.0
        a = 2.0 * math.pi * turns * t
        coil.append(s0 + ax * ((s1 - s0).length * (0.06 + 0.88 * t))
                    + e1 @ Vector((0.020 * math.cos(a), 0.020 * math.sin(a), 0.0)))
    add_tube(bm, coil, 0.0034, 6, DARK_IDX)
    for p in (s0, s1):
        add_lathe(bm, [(0.010, -0.004), (0.025, -0.003), (0.026, 0.001), (0.010, 0.003)], 20,
                  DARK_IDX, center=p + ax * (0.010 if p is s0 else -0.010), rot=e1,
                  solid=True)


def add_rear_end(bm, float_tyre, short_wheelbase):
    """Rear wheel: its drum and arm on the engine side (-Y)."""
    c = Vector((AXLE_R + (SHORT_WB if short_wheelbase else 0.0), 0.0, R_TYRE))
    vs = add_wheel(bm, c, -1.0)
    if float_tyre:
        for v in vs:
            v.co.z += FLOAT_TYRE


def add_body(bm, bevel_verts, odd_body):
    """Spine, cowls with louvres and trims, floorboard, leg shield, horn cast."""
    add_spine(bm, odd_body)
    for side in (1.0, -1.0):
        add_blob(bm, COWL_C, COWL_AX, COWL_AY, COWL_AZT, COWL_AZB, COWL_N, COWL_TAPER,
                 COWL_RISE, COWL_NU, COWL_NV, PAINT_IDX, side, COWL_AY_IN)
        # chrome belt trim along the cowl's widest line
        pts = []
        for k in range(15):
            # v = pi/2 is the cowl's outboard face on either side; smaller v
            # runs toward the nose
            v = 0.5 * math.pi + 0.55 - 1.30 * k / 14.0
            u = 0.06
            p = cowl_point(u, v, side)
            pts.append(p + cowl_normal(u, v, side) * 0.0010)
        add_bar(bm, pts, ZAX, 0.0045, 0.0030, 0.0018, CHROME_IDX, filleted=True)
    # louvres pressed into the engine-side (right, -Y) cowl
    side = -1.0
    for k in range(LOUVRES):
        u = -0.40 + 0.065 * k
        # graduated: the middle slats longest, so no two slats end in one plane
        c = abs(k - 0.5 * (LOUVRES - 1))
        v0, span = 0.18 + 0.030 * c, 0.58 - 0.045 * c
        pts = []
        for j in range(9):
            v = 0.5 * math.pi - v0 - span * j / 8.0
            p = cowl_point(u, v, side)
            pts.append(p + cowl_normal(u, v, side) * 0.0012)
        # the slat's width runs up the cowl, its thickness along the normal
        vm = 0.5 * math.pi - v0 - 0.5 * span
        wax = cowl_point(u + 1e-3, vm, side) - cowl_point(u - 1e-3, vm, side)
        bevel_verts += add_bar(bm, pts, wax, 0.0060, 0.0036, 0.0020, PAINT_IDX, filleted=True)
    # floorboard, as wide as the shield's foot and running back under the
    # tail's front face; runner strips and edge trims
    fx0, fx1 = FLOOR_X
    add_rbox(bm, 0.5 * (fx1 - fx0), FLOOR_HW, 0.060,
             [(0.004, FLOOR_TOP - 0.037), (0.0, FLOOR_TOP - 0.033), (0.0, FLOOR_TOP - 0.004),
              (0.004, FLOOR_TOP)], (0.5 * (fx0 + fx1), 0.0, 0.0), Matrix.Identity(3),
             PAINT_IDX, n_corner=6)
    for k in range(7):
        y = -0.150 + 0.050 * k
        e = 0.0003 * k           # staggered, so no two strips' faces share a plane
        add_rbox(bm, 0.120 + e, 0.0065, 0.004,
                 [(0.0, FLOOR_TOP - 0.0015 - e), (0.0, FLOOR_TOP + 0.0035 + e),
                  (0.0022, FLOOR_TOP + 0.0055 + e)], (0.130, y, 0.0), Matrix.Identity(3),
                 RUBBER_IDX, n_corner=2)
    for s in (1.0, -1.0):
        add_tube(bm, [(fx0 + 0.040, s * (FLOOR_HW + 0.0015), FLOOR_TOP - 0.006),
                      (0.265, s * (FLOOR_HW + 0.0015), FLOOR_TOP - 0.006)],
                 0.0070, 12, CHROME_IDX)
    # fillets pressed into the floor: up into the shield's back ...
    def to_shield(y, r):
        k = shield_back(y, FLOOR_TOP)
        b = shield_back(y, FLOOR_TOP + r)
        return (Vector((k.x - r, y, FLOOR_TOP - 0.004)), Vector((k.x, y, FLOOR_TOP - 0.004)),
                b + Vector((0.004, 0.0, 0.0)))
    add_fillet(bm, to_shield, 0.190, PAINT_IDX)

    # ... and up into the tail's front face, so floor and body read as one
    def to_tail(y, r):
        xk = spine_front_x(y, FLOOR_TOP)
        xb = spine_front_x(y, FLOOR_TOP + r)
        return (Vector((xk + r, y, FLOOR_TOP - 0.004)), Vector((xk, y, FLOOR_TOP - 0.004)),
                Vector((xb - 0.004, y, FLOOR_TOP + r)))
    add_fillet(bm, to_tail, 0.105, PAINT_IDX)
    # leg shield and its rolled chrome edge trim
    add_sheet(bm, shield_surf, 20, 20, SH_T, PAINT_IDX)
    edge = []
    for k in range(11):
        edge.append((0.0, k / 10.0))
    for k in range(1, 18):
        edge.append((k / 18.0, 1.0))
    for k in range(10, -1, -1):
        edge.append((1.0, k / 10.0))
    path = []
    for u, v in edge:
        p, n = shield_surf(u, v)
        path.append(p - n * (0.5 * SH_T))
    path[0] = path[0] - ZAX * 0.004
    path[-1] = path[-1] - ZAX * 0.004
    add_tube(bm, fillet_corners(path, 0.03, 4), 0.0080, 10, CHROME_IDX)
    # horn cast: a fairing on the shield's front round the column's top
    loops = []
    z0, z1 = TIE_Z
    zs = [z0 - 0.004, z0 - 0.0015] + [z0 + (z1 - z0) * k / 16.0 for k in range(17)] \
        + [z1 + 0.0015, z1 + 0.004]
    insets = [0.010, 0.004] + [0.0] * 17 + [0.004, 0.010]
    for z, inset in zip(zs, insets):
        zz = max(z0, min(z1, z))
        f = (zz - z0) / (z1 - z0)
        xf = col_x(zz) + 0.034
        xb = shield_x(zz) - 0.030
        xc, dd = 0.5 * (xf + xb), 0.5 * (xf - xb) - inset
        ww = 0.050 + 0.014 * math.sin(math.pi * min(1.0, 0.25 + f)) - inset
        loop = []
        for i in range(28):
            t = 2.0 * math.pi * i / 28
            loop.append(Vector((xc + dd * _se(math.cos(t), 3.2), ww * _se(math.sin(t), 3.2), z)))
        loops.append(loop)
    add_loft(bm, loops, PAINT_IDX)
    # horn grille on its front face
    zg = 0.800
    up = Vector((-TAN_RAKE, 0.0, 1.0)).normalized()
    out = Vector((1.0, 0.0, TAN_RAKE)).normalized()
    rot = Matrix((up, out, up.cross(out))).transposed()
    g = Vector((col_x(zg) + 0.034, 0.0, zg))
    bevel_verts += add_prism(bm, comb_outline(0.034, -0.008, 0.0008, 6, 0.0021, 0.0042),
                             -0.024, 0.024, g, rot, CHROME_IDX)


def add_headset(bm, bevel_verts, pop_speedo):
    """Headset loft across the bars, headlamp, speedometer, collar, grips,
    bar-end caps, levers and mirrors."""
    ys = []
    for k in range(23):
        s = -1.0 + 2.0 * k / 22.0
        ys.append(0.250 * (0.55 * s + 0.45 * math.copysign(abs(s) ** 0.6, s)))
    st = [(-0.2515, 0.004), (-0.2505, 0.0015)] + [(y, 0.0) for y in ys] \
        + [(0.2505, 0.0015), (0.2515, 0.004)]
    loops = []
    for y, inset in st:
        yy = min(0.25, abs(y))
        a, b, xc = _HS_A(yy) - inset, _HS_B(yy) - inset, _HS_X(yy)
        zc = HS_Z + 0.020 * yy
        loop = []
        for i in range(28):
            t = 2.0 * math.pi * i / 28
            loop.append(Vector((xc + a * _se(math.cos(t), HS_N), y, zc + b * _se(math.sin(t), HS_N))))
        loops.append(loop)
    add_loft(bm, loops, PAINT_IDX)
    # headlamp: chrome bezel ring and a domed lens on the headset's nose
    lc = Vector((_HS_X(0.0) + _HS_A(0.0) - 0.012, 0.0, HS_Z - 0.004))
    rot = frame(XAX, ZAX)
    add_lathe(bm, [(0.0500, -0.030), (0.0580, -0.012), (0.0625, 0.004), (0.0610, 0.013),
                   (0.0550, 0.016), (0.0515, 0.010), (0.0490, -0.030)], 48, CHROME_IDX,
              center=lc, rot=rot, phase=math.pi / 48.0)
    add_lathe(bm, [(0.0525, 0.004), (0.0525, 0.011), (0.0470, 0.020), (0.0340, 0.027),
                   (0.0160, 0.031), (0.0040, 0.032)], 48, GLASS_IDX, center=lc, rot=rot,
              solid=True)
    # speedometer on the headset's crown, facing the rider
    xs = _HS_X(0.0) - 0.062
    ns = Vector((-0.45, 0.0, 1.0)).normalized()
    sc = Vector((xs, 0.0, headset_top(xs, 0.0) - 0.004))
    if pop_speedo:
        sc = sc + ns * POP_SPEEDO
    add_lathe(bm, [(0.0400, -0.014), (0.0440, -0.004), (0.0460, 0.004), (0.0440, 0.010),
                   (0.0385, 0.012), (0.0360, 0.008), (0.0300, 0.0090), (0.0150, 0.0100),
                   (0.0040, 0.0105)], 40, CHROME_IDX, center=sc, rot=frame(ns, XAX), solid=True,
              seg_mats=[CHROME_IDX] * 5 + [GLASS_IDX] * 3, cap_mats=(CHROME_IDX, GLASS_IDX))
    # chrome collar where the column enters the headset
    cz = 0.925
    add_lathe(bm, [(0.0240, -0.012), (0.0330, -0.010), (0.0350, -0.004), (0.0350, 0.006),
                   (0.0300, 0.012), (0.0240, 0.013)], 24, CHROME_IDX,
              center=(col_x(cz), 0.0, cz), rot=frame(STEER_DIR, XAX), solid=True)
    for s in (1.0, -1.0):
        gx, gz = _HS_X(0.25), HS_Z + 0.020 * 0.25
        rot = frame((0.0, s, 0.0), ZAX)

        def rib(i, j):
            return 0.92 if (2 <= j <= 10 and i % 2) else 1.0

        gprof = [(0.0120, 0.000), (0.0160, 0.004)]
        for k in range(9):
            gprof.append((0.0170, 0.012 + 0.011 * k))
        gprof += [(0.0180, 0.106), (0.0175, 0.110)]
        add_lathe(bm, gprof, 20, RUBBER_IDX, center=(gx, s * GRIP_Y[0], gz), rot=rot,
                  solid=True, rmod=rib)
        add_lathe(bm, [(0.0110, -0.002), (0.0165, 0.001), (0.0180, 0.008), (0.0150, 0.014),
                       (0.0060, 0.017)], 20, CHROME_IDX,
                  center=(gx, s * (GRIP_Y[0] + 0.108), gz), rot=rot, solid=True,
                  phase=math.pi / 20.0)
        # lever: pivots on the headset's end and runs out ahead of the grip
        p0 = Vector((gx + 0.020, s * 0.222, gz - 0.004))
        p1 = Vector((gx + 0.046, s * 0.258, gz - 0.010))
        p2 = Vector((gx + 0.040, s * 0.338, gz - 0.016))
        bevel_verts += add_bar(bm, [p0, p1, p2], ZAX, 0.0065, 0.0030, 0.0020, CHROME_IDX,
                               fillet=0.020)
        # mirror on a stalk
        yb = 0.160
        xb = _HS_X(yb)
        base = Vector((xb, s * yb, headset_top(xb, yb) - 0.010))
        head = Vector((xb - 0.022, s * 0.285, 1.195))
        stalk = fillet_path([base, base + Vector((0.0, s * 0.020, 0.050)),
                             head + Vector((0.004, 0.0, -0.030))], 0.03, 5)
        add_tube(bm, stalk, 0.0060, 10, CHROME_IDX)
        mn = Vector((-1.0, 0.0, 0.15)).normalized()
        add_lathe(bm, [(0.012, -0.024), (0.034, -0.019), (0.046, -0.009), (0.0490, 0.000),
                       (0.0470, 0.006), (0.0430, 0.0070)], 32, CHROME_IDX, center=head,
                  rot=frame(mn, ZAX), solid=True, cap_mats=(CHROME_IDX, GLASS_IDX))


def add_seat(bm):
    """Dual saddle: underside a bite inside the spine's crown, cream top
    panel, oxblood sides, piping round the panel, a grab strap across it."""
    xs = []
    n_st = 30
    for k in range(n_st):
        s = k / (n_st - 1)
        xs.append(SEAT_X0 + (SEAT_X1 - SEAT_X0) * (0.5 - 0.5 * math.cos(math.pi * s)))
    st = [(SEAT_X0 - 0.004, 0.010), (SEAT_X0 - 0.0015, 0.003)] + [(x, 0.0) for x in xs] \
        + [(SEAT_X1 + 0.0015, 0.003), (SEAT_X1 + 0.004, 0.010)]
    m = 28

    def section(x, inset=0.0):
        xc = max(SEAT_X0, min(SEAT_X1, x))
        hw = _SEAT_W(xc) - inset
        top = _SEAT_TOP(xc) - inset
        _zc, w, _ht, _hb = spine_dims(xc)
        pts = []
        for i in range(m):
            t = 2.0 * math.pi * (i + 0.5) / m
            a = _se(math.cos(t), 4.0)
            b = _se(math.sin(t), 4.0)
            y = hw * a
            zb = spine_top(xc, min(abs(y), 0.97 * w)) - SEAT_BITE
            zt = top - 0.026 * abs(a) ** 3
            pts.append(Vector((x, y, zb + (zt - zb) * 0.5 * (b + 1.0))))
        return pts

    loops = [section(x, inset) for x, inset in st]
    ts = [2.0 * math.pi * (i + 0.5) / m for i in range(m)]
    panel = [abs(0.5 * (ts[j] + ts[(j + 1) % m]) - 0.5 * math.pi) < SEAT_PANEL
             and j != m - 1 for j in range(m)]
    seg = [[CREAM_IDX if panel[j] else SEAT_IDX for j in range(m)] for _ in loops]
    add_loft(bm, loops, SEAT_IDX, seg_mats=seg)
    # piping round the panel: forward along one edge, across the nose, back
    # along the other; a second run closes it across the tail
    j0 = next(j for j in range(m) if panel[j])
    j1 = max(j for j in range(m) if panel[j]) + 1
    ks = list(range(3, len(loops) - 3, 2))
    if ks[-1] != len(loops) - 4:
        ks.append(len(loops) - 4)
    rear, front = loops[ks[0]], loops[ks[-1]]
    edge0 = [loops[k][j0] for k in ks]
    edge1 = [loops[k][j1] for k in ks]
    u_path = edge0 + [front[jj] for jj in range(j0 + 1, j1)] + list(reversed(edge1))
    add_tube(bm, fillet_corners(u_path, 0.012, 3), 0.0042, 6, SEAT_IDX)
    add_tube(bm, fillet_corners([rear[jj] for jj in range(j1, j0 - 1, -1)], 0.012, 3), 0.0042,
             6, SEAT_IDX)
    # grab strap over the panel: an oxblood band a hair proud of the vinyl
    sec = section(STRAP_X)
    zmid = 0.5 * (min(p.z for p in sec) + max(p.z for p in sec))
    band = []
    for j in range(2, m // 2 - 1):
        p = sec[j]
        nrm = Vector((0.0, p.y, p.z - zmid)).normalized()
        band.append(p + nrm * 0.0015)
    add_bar(bm, band, XAX, 0.016, 0.0030, 0.0018, SEAT_IDX, filleted=True)


def add_rear_details(bm, bevel_verts):
    """Engine case with finned cylinder, header pipe and silencer, kick-start,
    brake pedal, luggage rack, tail lamp and number plate."""
    # engine case under the right cowl, carrying the rear drum
    add_blob(bm, (-0.405, 0.135, 0.238), 0.225, 0.064, 0.090, 0.086, 2.6, 0.15, 0.0, 18, 32,
             ALLOY_IDX, side=-1.0)
    rot = frame(XAX, ZAX)
    cyl = [(0.020, -0.060), (0.040, -0.056)]
    for k in range(6):
        z = -0.046 + 0.0150 * k
        cyl += [(0.042, z), (0.056, z + 0.003), (0.056, z + 0.0065), (0.042, z + 0.0095)]
    cyl += [(0.040, 0.046), (0.028, 0.052)]
    add_lathe(bm, cyl, 20, ALLOY_IDX, center=(-0.215, -0.118, 0.208), rot=rot, solid=True)
    # exhaust: header from the cylinder, silencer, chrome tailpipe
    head = [(-0.160, -0.118, 0.196), (-0.140, -0.130, 0.150), (-0.250, -0.160, 0.120),
            (-0.450, -0.168, 0.140)]
    add_tube(bm, fillet_path(head, 0.05, 6), 0.0165, 14, DARK_IDX)
    s0 = Vector((-0.460, -0.168, 0.150))
    s1 = Vector((-0.800, -0.172, 0.178))
    ax = (s1 - s0).normalized()
    ln = (s1 - s0).length
    sil = [(0.016, -0.010), (0.040, 0.004), (0.054, 0.030), (0.058, 0.070), (0.058, ln - 0.060),
           (0.054, ln - 0.020), (0.036, ln), (0.016, ln + 0.004)]
    add_lathe(bm, sil, 36, DARK_IDX, center=s0, rot=frame(ax, ZAX), solid=True)
    add_lathe(bm, [(0.018, -0.030), (0.0195, 0.000), (0.0195, 0.060), (0.0215, 0.066),
                   (0.0215, 0.074), (0.0160, 0.076)], 20, CHROME_IDX, center=s1,
              rot=frame(ax, ZAX), solid=True)
    # silencer bracket to the engine case
    add_tube(bm, [(-0.560, -0.168, 0.200), (-0.560, -0.160, 0.250)], 0.010, 10, DARK_IDX)
    # kick-start lever with a rubber pedal
    k0 = Vector((-0.300, -0.192, 0.262))
    k1 = Vector((-0.380, -0.212, 0.300))
    k2 = Vector((-0.440, -0.232, 0.300))
    bevel_verts += add_bar(bm, [k0 + Vector((0.0, 0.012, 0.0)), k0, k1, k2], ZAX, 0.0090,
                           0.0045, 0.0025, CHROME_IDX, fillet=0.02)
    add_lathe(bm, [(0.010, -0.004), (0.0130, 0.000), (0.0130, 0.040), (0.0100, 0.044)], 16,
              RUBBER_IDX, center=k2 + Vector((0.005, -0.004, 0.0)), rot=frame((0.0, -1.0, 0.0), ZAX),
              solid=True)
    # rear brake pedal on the right of the floorboard
    b0 = Vector((0.195, -0.110, FLOOR_TOP - 0.004))
    b1 = Vector((0.285, -0.110, FLOOR_TOP + 0.032))
    bevel_verts += add_bar(bm, [b0, b1], YAX, 0.009, 0.004, 0.0025, CHROME_IDX)
    add_rbox(bm, 0.024, 0.020, 0.006, [(0.0015, -0.002), (0.0, 0.001), (0.0, 0.008),
                                       (0.0015, 0.010)],
             b1 + Vector((0.004, 0.0, 0.0)), frame(Vector((-0.4, 0.0, 1.0)), XAX), RUBBER_IDX)
    # luggage rack over the tail
    def rz(x, y):
        # over the crown, never past the tail's shoulder
        return spine_top(x, min(abs(y), 0.80 * spine_dims(x)[1])) + 0.040

    xr0, xr1, yr = -0.752, -0.872, 0.078
    xs = [xr0 + (xr1 - xr0) * k / 6.0 for k in range(7)]
    rail = ([Vector((xr0, yr, rz(xr0, yr) - 0.050))]
            + [Vector((x, yr, rz(x, yr))) for x in xs]
            + [Vector((xr1 - 0.010, 0.0, rz(xr1, yr)))]
            + [Vector((x, -yr, rz(x, yr))) for x in reversed(xs)]
            + [Vector((xr0, -yr, rz(xr0, yr) - 0.050))])
    add_tube(bm, fillet_corners(rail, 0.035, 5, 12.0), 0.0080, 10, CHROME_IDX)
    for k in range(3):
        x = xr0 - 0.030 - 0.030 * k
        z = rz(x, yr) - 0.002
        e = 0.0004 * k
        add_tube(bm, [(x, -yr - 0.004 - e, z), (x, yr + 0.004 + e, z)], 0.0055, 10, CHROME_IDX,
                 phase=math.pi / 10.0)
    for s in (1.0, -1.0):
        x = xr1 + 0.028
        add_tube(bm, [(x, s * yr * 0.85, rz(x, yr) + 0.002), (x + 0.008, s * yr * 0.70,
                                                              spine_top(x, yr * 0.7) - 0.02)],
                 0.0060, 10, CHROME_IDX)
    # tail lamp on the tail's rear slope, along the body's normal there
    xt = -0.884
    p = Vector((xt, 0.0, spine_top(xt, 0.0) - 0.006))
    rot = frame(spine_normal(p), ZAX)
    add_lathe(bm, [(0.030, -0.030), (0.043, -0.010), (0.047, 0.004), (0.045, 0.012),
                   (0.040, 0.014), (0.038, 0.008), (0.030, 0.008)], 32, CHROME_IDX, center=p,
              rot=rot)
    add_lathe(bm, [(0.0395, 0.004), (0.0395, 0.012), (0.0340, 0.022), (0.0220, 0.028),
                   (0.0080, 0.030)], 32, LAMP_IDX, center=p, rot=rot, solid=True,
              phase=math.pi / 32.0)
    # blank number plate under the tail, on a bracket
    add_rbox(bm, 0.050, 0.082, 0.010, [(0.0015, -0.003), (0.0, 0.000), (0.0, 0.004),
                                       (0.0015, 0.006)],
             (-0.905, 0.0, 0.395), frame(Vector((-1.0, 0.0, 0.10)), ZAX), ALLOY_IDX)
    add_tube(bm, [(-0.900, 0.0, 0.410), (-0.880, 0.0, 0.452)], 0.009, 10, DARK_IDX)


def add_stand(bm, narrow):
    """Centre stand: one bent bar from foot to foot over the pivot, a brace,
    rubber feet flat on the ground."""
    fy = STAND_FOOT_Y_NARROW if narrow else STAND_FOOT_Y
    xp, xf = STAND_X
    pts = [Vector((xf, fy, 0.012)), Vector((xp, STAND_PIVOT_Y, STAND_PIVOT_Z)),
           Vector((xp, -STAND_PIVOT_Y, STAND_PIVOT_Z)), Vector((xf, -fy, 0.012))]
    add_tube(bm, fillet_path(pts, 0.03, 6), STAND_R, 12, DARK_IDX)
    t = 0.30
    a = pts[0] + (pts[1] - pts[0]) * t
    b = pts[3] + (pts[2] - pts[3]) * t
    add_tube(bm, [a + (a - b).normalized() * -0.004, b + (b - a).normalized() * -0.004], 0.0075,
             10, DARK_IDX, phase=math.pi / 10.0)
    for s in (1.0, -1.0):
        add_lathe(bm, [(0.020, 0.000), (0.0235, 0.0025), (0.0240, 0.012), (0.0200, 0.018),
                       (0.0140, 0.024), (0.0130, 0.028)], 20, RUBBER_IDX,
                  center=(xf, s * fy, 0.0), solid=True)
    # pivot brackets: the pivot bar's ends in the body and the engine case
    for s in (1.0, -1.0):
        add_lathe(bm, [(0.012, -0.020), (0.018, -0.016), (0.018, 0.016), (0.012, 0.020)], 16,
                  DARK_IDX, center=(xp, s * (STAND_PIVOT_Y - 0.016), STAND_PIVOT_Z),
                  rot=frame(YAX, ZAX), solid=True, phase=math.pi / 16.0)


def build_scooter_mesh(name, bevel_offset, bevel_segments, float_tyre=False, toe_wheel=False,
                       steep_head=False, odd_body=False, short_wheelbase=False,
                       narrow_stand=False, pop_speedo=False, lift_shield=False):
    bm = bmesh.new()
    _SHIELD["z0"] = SH_Z0_LIFTED if lift_shield else SH_Z0
    try:
        bevel_verts = []
        add_body(bm, bevel_verts, odd_body)
        add_front_end(bm, bevel_verts, toe_wheel, steep_head)
        add_rear_end(bm, float_tyre, short_wheelbase)
        add_headset(bm, bevel_verts, pop_speedo)
        add_seat(bm)
        add_rear_details(bm, bevel_verts)
        add_stand(bm, narrow_stand)

        if bevel_offset > 0.0:
            # Chamfer the grille, louvres, levers and pedals, one pass per
            # material with material= set, over sorted edges.
            for mat_idx in (PAINT_IDX, CHROME_IDX):
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
        # Pressed panels, tyres, lathes and tubes are smooth-shaded; grille
        # ribs, tread block ends and chamfers stay crisp through sharp edges.
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
        _SHIELD["z0"] = SH_Z0
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
        bsdf.inputs["Coat Roughness"].default_value = 0.06
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


def _emission(bsdf, color, strength):
    for key in ("Emission Color", "Emission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = color
            break
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = strength


def scooter_materials():
    """(paint, chrome, rubber, seat, cream, glass, lamp, alloy, dark): shared
    by the check and the render.

    The paint is a pastel sea-green enamel under a clear coat; chrome is
    bright but not mirror-perfect, so it catches the key; tyres, grips,
    runner strips and stand feet rubber; the saddle's sides and piping
    oxblood vinyl and its top panel cream vinyl; the headlamp lens, mirror
    faces and speedometer glass; the tail lamp a red lens with a faint glow;
    the rims, drums, engine case and plate painted alloy; the column, fork,
    link, spring, stand and silencer black enamel.
    """
    paint = principled("ScooterPaint", (0.35, 0.57, 0.50, 1.0), 0.0, 0.26,
                       roughness_var=0.05, noise_scale=30.0, coat=0.6)
    chrome = principled("ScooterChrome", (0.86, 0.86, 0.87, 1.0), 1.0, 0.16,
                        roughness_var=0.04, noise_scale=120.0)
    rubber = principled("ScooterRubber", (0.024, 0.024, 0.026, 1.0), 0.0, 0.78,
                        roughness_var=0.08, noise_scale=90.0)
    seat = principled("ScooterSeatVinyl", (0.19, 0.045, 0.035, 1.0), 0.0, 0.40,
                      roughness_var=0.10, mottle=0.18, noise_scale=160.0)
    cream = principled("ScooterSeatCream", (0.62, 0.55, 0.42, 1.0), 0.0, 0.42,
                       roughness_var=0.10, mottle=0.10, noise_scale=160.0)
    glass = principled("ScooterGlass", (0.62, 0.66, 0.68, 1.0), 0.0, 0.05, coat=1.0)
    lamp = principled("ScooterTailLens", (0.55, 0.025, 0.02, 1.0), 0.0, 0.14, coat=1.0)
    _emission(lamp.node_tree.nodes["Principled BSDF"], (1.0, 0.05, 0.03, 1.0), 0.35)
    alloy = principled("ScooterAlloy", (0.55, 0.56, 0.57, 1.0), 0.8, 0.36,
                       roughness_var=0.08, noise_scale=70.0)
    dark = principled("ScooterBlackEnamel", (0.030, 0.030, 0.033, 1.0), 0.0, 0.34,
                      roughness_var=0.06, noise_scale=80.0, coat=0.3)
    return paint, chrome, rubber, seat, cream, glass, lamp, alloy, dark


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


def pca(pts):
    """(mean, eigenvalues ascending, eigenvectors as columns)."""
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    w, vecs = np.linalg.eigh(q.T @ q / len(p))
    return Vector(c), w, vecs


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    out["tyres"] = sorted((s for s in parts if s.mat == RUBBER_IDX and s.size.x > 0.40),
                          key=lambda s: -s.mean.x)
    out["pads"] = [s for s in parts if s.mat == RUBBER_IDX and s.hi.z < 0.04]
    # the steering column: the one long, straight black bar
    cols = []
    for s in parts:
        if s.mat != DARK_IDX or s.size.z < 0.30:
            continue
        _c, w, _v = pca(s.pts)
        if math.sqrt(max(w[1], 0.0) / w[2]) < 0.10:
            cols.append(s)
    out["columns"] = cols
    paint = [s for s in parts if s.mat == PAINT_IDX]
    out["spine"] = next((s for s in paint if s.size.x > 0.75), None)
    # the body the mirror audit reads: every paint shell but the louvres,
    # which are pressed into the engine-side cowl alone (declared exclusion)
    out["body"] = [s for s in paint if max(s.size) > 0.15]
    out["louvres"] = [s for s in paint if max(s.size) <= 0.15]
    out["shield"] = next((s for s in paint if s.size.y > 0.35 and s.size.x < 0.35
                          and s.hi.z > 0.8 and s.lo.z < 0.3), None)
    out["floor"] = next((s for s in paint if s.size.z < 0.06 and s.size.x > 0.35), None)
    out["seat"] = next((s for s in parts if CREAM_IDX in s.mats and SEAT_IDX in s.mats), None)
    return out


def contact(s):
    pts = [p for p in s.pts if p.z < s.lo.z + CONTACT_BAND]
    return Vector((sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts), s.lo.z))


def wheel_audit(cls):
    """Axle axis of each tyre (least-variance PCA axis), camber (tilt from
    horizontal), toe (angle between the two axles in plan), wheelbase."""
    res = {"camber": [], "toe": 90.0, "wheelbase": 0.0, "centres": []}
    if len(cls["tyres"]) != TYRE_COUNT:
        return res
    axes = []
    for s in cls["tyres"]:
        c, _w, vecs = pca(s.pts)
        a = Vector(vecs[:, 0])
        if a.y < 0.0:
            a = -a
        axes.append(a)
        res["camber"].append(math.degrees(math.asin(min(1.0, abs(a.z)))))
        res["centres"].append(c)
    p0 = Vector((axes[0].x, axes[0].y)).normalized()
    p1 = Vector((axes[1].x, axes[1].y)).normalized()
    res["toe"] = math.degrees(math.acos(max(-1.0, min(1.0, p0.dot(p1)))))
    c0, c1 = res["centres"]
    res["wheelbase"] = math.hypot(c0.x - c1.x, c0.y - c1.y)
    return res


def steering_audit(cls):
    """The column's axis (principal PCA axis) against the front tyre's
    contact patch: trail along X, offset across Y."""
    res = {"trail": 9.0, "offset": 9.0, "rake": 0.0}
    if len(cls["columns"]) != 1 or len(cls["tyres"]) != TYRE_COUNT:
        return res
    col = cls["columns"][0]
    c, _w, vecs = pca(col.pts)
    a = Vector(vecs[:, 2])
    if a.z < 0.0:
        a = -a
    hit = c - a * (c.z / a.z)
    cp = contact(cls["tyres"][0])
    res["trail"] = hit.x - cp.x
    res["offset"] = abs(hit.y - cp.y)
    res["rake"] = math.degrees(math.acos(min(1.0, a.z)))
    return res


def mirror_audit(cls):
    """Every body vertex against its mirror partner across y = 0."""
    pts = [p for s in cls["body"] for p in s.pts]
    if not pts:
        return 9.0
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    worst = 0.0
    for p in pts:
        _co, _i, d = kd.find(Vector((p.x, -p.y, p.z)))
        worst = max(worst, d)
    return worst


def seam_audit(cls):
    """How deep the shield's foot (its lowest ring) stands in the
    floorboard, below the floor's top read off the mesh."""
    sh, fl = cls["shield"], cls["floor"]
    if sh is None or fl is None:
        return -9.0
    foot = max(p.z for p in sh.pts if p.z < sh.lo.z + 0.002)
    return fl.hi.z - foot


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


def stance_audit(cls):
    """Mass centre against the convex hull of the tyres' contact patches and
    the stand feet's soles."""
    total = 0.0
    mom = Vector()
    for s in cls["all"]:
        if s.mat is None:
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * DENSITY[s.mat]
        total += m
        mom += m * cen
    com = mom / total
    # every support's own sole, grounded or not: grounding is exit 16's job
    contact_pts = [(p.x, p.y) for sk in cls["tyres"] + cls["pads"] for p in sk.pts
                   if p.z < sk.lo.z + CONTACT_BAND]
    margin = -1.0
    if len(contact_pts) >= 3:
        hull = hull2d(contact_pts)
        margin = 9.0
        for k in range(len(hull)):
            a, b = hull[k], hull[(k + 1) % len(hull)]
            ex, ey = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ex, ey)
            margin = min(margin, (ex * (com.y - a[1]) - ey * (com.x - a[0])) / ln)
    return {"mass": total, "com": com, "margin": margin}


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
        bm.verts.new((0.0, 0.0, 0.5))
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
        # Hull the points, not the surface: convex_hull keeps source faces
        # lying on the hull, which made colliders non-manifold (#386).
        for edge in list(bm.edges):
            bm.edges.remove(edge)
        result = bmesh.ops.convex_hull(bm, input=list(bm.verts))
        interior = [g for g in result.get("geom_interior") or [] if g.is_valid]
        if interior:
            bmesh.ops.delete(bm, geom=interior, context="VERTS")
        unused = [g for g in result.get("geom_unused") or [] if g.is_valid]
        if unused:
            bmesh.ops.delete(bm, geom=unused, context="VERTS")
        loose = [v for v in bm.verts if v.is_valid and not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
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
    img = bpy.data.images.new("ScooterNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = CHROME_IDX
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


def check(skip_decimate, lift_z=False, stray_vert=False, float_tyre=False, toe_wheel=False,
          steep_head=False, odd_body=False, short_wheelbase=False, narrow_stand=False,
          pop_speedo=False, lift_shield=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(float_tyre=float_tyre, toe_wheel=toe_wheel, steep_head=steep_head,
                 odd_body=odd_body, short_wheelbase=short_wheelbase,
                 narrow_stand=narrow_stand, pop_speedo=pop_speedo, lift_shield=lift_shield)
    low = build_scooter_mesh("ScooterLow", bevel_offset=0.0006, bevel_segments=1, **flags)
    high = build_scooter_mesh("ScooterHigh", bevel_offset=0.0006, bevel_segments=3, **flags)
    mats = scooter_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the chrome: the grille, levers and pedals are where
    # the high mesh's rounder chamfer differs from the low.
    target = mats[CHROME_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("scooter mesh did not build", 3),) + none3

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
    tyre_z = [s.lo.z for s in cls["tyres"]]
    pad_z = [s.lo.z for s in cls["pads"]]
    wheel = wheel_audit(cls)
    steer = steering_audit(cls)
    mirror = mirror_audit(cls)
    spine = cls["spine"]
    body_len = spine.size.x if spine else 0.0
    seat_z = cls["seat"].hi.z if cls["seat"] else 0.0
    stance = stance_audit(cls)
    ncomp, comp_sizes = connected_components(cls)
    seam = seam_audit(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("scooter has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "ScooterLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "ScooterLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_scooter_mesh("ScooterColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "ScooterCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_motor_scooter_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} tyres={len(tyre_z)} pads={len(pad_z)} "
          f"tyre_zmin={[round(z, 5) for z in tyre_z]} pad_zmin={[round(z, 5) for z in pad_z]}")
    print(f"measured camber={[round(c, 4) for c in wheel['camber']]} toe={wheel['toe']:.4f} "
          f"wheelbase={wheel['wheelbase']:.5f}")
    print(f"measured columns={len(cls['columns'])} rake={steer['rake']:.3f} "
          f"trail={steer['trail']:.5f} offset={steer['offset']:.6f}")
    print(f"measured mirror={mirror:.6f} body_shells={len(cls['body'])} "
          f"louvres={len(cls['louvres'])} body_len={body_len:.4f} seat_z={seat_z:.4f}")
    print(f"measured mass={stance['mass']:.3f}kg com=({stance['com'].x:.4f},"
          f"{stance['com'].y:.4f},{stance['com'].z:.4f}) margin={stance['margin']:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")
    print(f"measured shield_seat={seam:.5f}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    floors = ((PAINT_IDX, PAINT_FACES_MIN, "paint"), (CHROME_IDX, CHROME_FACES_MIN, "chrome"),
              (RUBBER_IDX, RUBBER_FACES_MIN, "rubber"), (SEAT_IDX, SEAT_FACES_MIN, "seat vinyl"),
              (CREAM_IDX, CREAM_FACES_MIN, "cream vinyl"), (GLASS_IDX, GLASS_FACES_MIN, "glass"),
              (LAMP_IDX, LAMP_FACES_MIN, "tail lens"), (ALLOY_IDX, ALLOY_FACES_MIN, "alloy"),
              (DARK_IDX, DARK_FACES_MIN, "black enamel"))
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
    if (len(tyre_z) != TYRE_COUNT or len(pad_z) != PAD_COUNT
            or max(tyre_z + pad_z) > ZMIN_EPS):
        return (fail(f"supports: {len(tyre_z)} tyres (want {TYRE_COUNT}), {len(pad_z)} stand "
                     f"feet (want {PAD_COUNT}), zmin per tyre {[round(z, 5) for z in tyre_z]}, "
                     f"per foot {[round(z, 5) for z in pad_z]} (each within {ZMIN_EPS} of 0)", 16),) + none3
    if (len(wheel["camber"]) != TYRE_COUNT or max(wheel["camber"]) > CAMBER_MAX_DEG
            or wheel["toe"] > TOE_MAX_DEG):
        return (fail(f"wheel alignment: camber {[round(c, 4) for c in wheel['camber']]} deg "
                     f"(max {CAMBER_MAX_DEG}), toe {wheel['toe']:.4f} deg (max {TOE_MAX_DEG})", 17),) + none3
    if (len(cls["columns"]) != 1 or not (TRAIL_MIN <= steer["trail"] <= TRAIL_MAX)
            or steer["offset"] > TRAIL_Y_TOL):
        return (fail(f"steering: {len(cls['columns'])} columns, trail {steer['trail']:.5f} m not "
                     f"in [{TRAIL_MIN}, {TRAIL_MAX}] or axis {steer['offset']:.5f} m off the "
                     f"contact's line (tol {TRAIL_Y_TOL}); rake {steer['rake']:.3f} deg", 18),) + none3
    if (mirror > MIRROR_EPS or abs(body_len - BODY_LEN) > SIZE_TOL
            or abs(seat_z - SEAT_HEIGHT) > SIZE_TOL):
        return (fail(f"body mirror deviation {mirror:.5f} m (eps {MIRROR_EPS}), or size off: "
                     f"body {body_len:.4f} m, seat {seat_z:.4f} m", 19),) + none3
    if abs(wheel["wheelbase"] - WHEELBASE) > WHEELBASE_TOL:
        return (fail(f"wheelbase {wheel['wheelbase']:.5f} m off {WHEELBASE} +- {WHEELBASE_TOL}", 20),) + none3
    if stance["margin"] < STANCE_MARGIN:
        return (fail(f"stance: mass centre {stance['margin']:.4f} m inside the support "
                     f"polygon < {STANCE_MARGIN}", 21),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 22),) + none3
    if not (SEAM_MIN <= seam <= SEAM_MAX):
        return (fail(f"leg shield's foot {seam:.5f} m into the floorboard, not in "
                     f"[{SEAM_MIN}, {SEAM_MAX}]", 23),) + none3
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

    # The house rig scaled to a 1.8 m vehicle: warm key upper left, cool
    # fill low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-2.1, -2.5, 2.4), 57.0, 1.4, (1.0, 0.92, 0.82), spread=30.0)
    light("Fill", (2.6, -1.8, 0.6), 7.0, 3.0, (0.72, 0.82, 1.0))
    light("Rim", (-1.0, 1.7, 1.6), 60.0, 1.2, (0.62, 0.78, 1.0))
    light("Wedge", (2.3, 2.3, 1.0), 180.0, 1.8, (1.0, 0.62, 0.30),
          target=(centre.x + 2.4, centre.y + WALL_Y, 0.55))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.55, -0.83, 0.0)).normalized()
    cam.location = centre + view * 3.72 + Vector((0.0, 0.0, 1.02))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, 0.0))
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
    # Standard, not AgX: AgX washes the pastel paint and the oxblood vinyl grey
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 24
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
    p.add_argument("--float-tyre", action="store_true")
    p.add_argument("--toe-wheel", action="store_true")
    p.add_argument("--steep-head", action="store_true")
    p.add_argument("--odd-body", action="store_true")
    p.add_argument("--short-wheelbase", action="store_true")
    p.add_argument("--narrow-stand", action="store_true")
    p.add_argument("--pop-speedo", action="store_true")
    p.add_argument("--lift-shield", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_tyre=args.float_tyre,
        toe_wheel=args.toe_wheel,
        steep_head=args.steep_head,
        odd_body=args.odd_body,
        short_wheelbase=args.short_wheelbase,
        narrow_stand=args.narrow_stand,
        pop_speedo=args.pop_speedo,
        lift_shield=args.lift_shield,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("motor-scooter OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
