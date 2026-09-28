"""Game-ready tilt-head stand mixer on a countertop — a showcase piece, not an example.

Asserts budget conformance of a procedural retro kitchen stand mixer after
composing shipped pipeline pieces: bmesh construction, UVs, eight materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

The mixer is the classic tilt-head pattern, generic and unbranded. A cast
enamel body in three lofted pieces — a pebble-shaped base foot on four
rubber feet, a neck that leans back as it rises, and a streamlined motor
head — hinged at the back on a pin through two knuckles cast on the neck.
The head carries a chrome trim band, a blank badge, a speed lever, a
planetary hub underneath and an attachment hub with its cap and thumb screw
on the nose; the neck carries the tilt-lock lever. A flat beater hangs from
the planetary socket into a polished stainless bowl with a rolled rim and a
strap handle, clamped by three bayonet lugs on a bowl plate. A cord leaves
the base's rear riser and runs over the counter to a plug. Beside it, on a
honed stone countertop section: a balloon whisk, a measuring cup and two
brown eggs in a glazed dish.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` / ``--float-foot`` grounded, ``--offset-hinge`` the
hinge pin coaxial through its knuckles, ``--offset-bowl`` the bowl seated
and concentric on its plate, ``--shallow-bowl`` the bowl's capacity,
``--offset-beater`` the beater coaxial with the planetary socket,
``--long-beater`` the beater's clearance to the bowl, ``--bunch-feet`` the
mass centre inside the feet, ``--loose-cap`` one connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python stand_mixer.py --
    blender --background --python stand_mixer.py -- --skip-decimate
    blender --background --python stand_mixer.py -- --output mixer.png
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

# --- Countertop section (the mixer faces +X, toward the counter's front) ---
CT = 0.030                   # slab thickness: the counter top is z = CT
COUNTER_X = (-0.225, 0.245)
COUNTER_Y = (-0.385, 0.185)
COUNTER_R = (0.002, 0.004, 0.011, 0.003)   # back-bottom, front-bottom, bullnose, back-top

# --- Base foot: a pebble plan (superellipse), lofted from inset loops ------
BASE_CX = -0.008
BASE_HX = 0.148
BASE_HY = 0.098
BASE_EXP = 3.0
BASE_SEGS = 72
FOOT_H = 0.008               # visible rubber foot height
BASE_Z0 = CT + FOOT_H        # base underside
# (inset from the plan outline, height above the underside)
BASE_PROFILE = [(0.006, 0.000), (0.0015, 0.0025), (0.000, 0.007), (0.000, 0.022),
                (0.002, 0.030), (0.007, 0.036), (0.015, 0.0395), (0.024, 0.041)]
BASE_TOP = BASE_Z0 + 0.041
FEET_XY = ((-0.118, -0.056), (-0.118, 0.056), (0.098, -0.056), (0.098, 0.056))
BUNCH_FEET_X = (-0.122, -0.092)            # --bunch-feet: all four under the neck
FOOT_R = 0.0122
# Each foot sinks a little further into the counter top, tucks a little
# further up into the base and is turned a quarter facet from the last, so
# no two feet share a plane even when --bunch-feet packs them 30 mm apart.
FOOT_BITES = (0.00025, 0.00040, 0.00055, 0.00070)
FOOT_TUCKS = (0.0015, 0.0017, 0.0019, 0.0021)
FLOAT_FOOT = 0.003           # --float-foot: one foot this far off the counter

# --- Neck: plan superellipse sections lofted up the back, leaning back -----
NECK_EXP = 2.6
NECK_SEGS = 40
# (height above the counter top, centre x, half-length x, half-width y)
NECK = [(0.045, -0.100, 0.046, 0.075), (0.051, -0.103, 0.043, 0.067),
        (0.060, -0.106, 0.041, 0.062), (0.078, -0.110, 0.040, 0.058),
        (0.115, -0.115, 0.039, 0.056), (0.160, -0.119, 0.039, 0.056),
        (0.200, -0.122, 0.040, 0.057), (0.228, -0.125, 0.041, 0.059),
        (0.240, -0.126, 0.042, 0.060)]
SEAM = 0.0015                # the neck's top ring follows the head's underside this far below

# --- Motor head: superellipse sections lofted along X ---------------------
XR = -0.172
XF = 0.168
REAR_ZONE = 0.040
FRONT_ZONE = 0.024
REAR_P, REAR_E = 2.2, 0.10   # rear end: nearly an ellipsoid, a 10% flat patch
FRONT_P, FRONT_E = 3.0, 0.55 # nose: a rounded edge onto a flat front face
N_TOP, N_BOT = 2.3, 3.4      # the crown is rounder than the belly
HEAD_SEGS = 56
HEAD_MID = 30
HEAD_ZONE_STEPS = 10
# (x, height above the counter top)
HEAD_TOP = [(XR, 0.318), (-0.140, 0.346), (-0.080, 0.358), (0.000, 0.357),
            (0.080, 0.349), (XF, 0.331)]
HEAD_BOT = [(XR, 0.262), (-0.140, 0.252), (-0.080, 0.250), (-0.020, 0.243),
            (0.060, 0.236), (XF, 0.237)]
HEAD_W = [(XR, 0.068), (-0.120, 0.076), (-0.040, 0.077), (0.060, 0.073), (XF, 0.066)]

# trim band, badge and speed lever on the head; lock lever on the neck
BAND_X = (0.074, 0.086)
BAND_PROUD = 0.0014
BAND_BITE = 0.0015
BADGE_X, BADGE_Z = 0.018, 0.300
BADGE_H = (0.030, 0.0100)
SPEED_X, SPEED_Z = -0.096, 0.306
LOCK_Z = 0.185

# --- Hinge: two knuckles on the neck, one on the head, a pin through all ---
HINGE_X, HINGE_Z = -0.132, 0.243
KNUCKLE_R = 0.0125
KNUCKLE_Y = (0.042, 0.064)
HEAD_KNUCKLE_R = 0.0110
HEAD_KNUCKLE_Y = 0.0405
PIN_R = 0.0042
PIN_HEAD_R = 0.0075
PIN_BITE = 0.0005
OFFSET_HINGE = 0.002         # --offset-hinge: pin this far off the knuckles' axis

# --- Bowl, plate and bayonet lugs -----------------------------------------
BOWL_X = 0.045
PLATE_R = 0.0700
PLATE_T = 0.006
PLATE_TOP = BASE_TOP + PLATE_T
BOWL_SEAT = 0.0005           # the bowl's foot sinks this far into the plate
BOWL_Z0 = PLATE_TOP - BOWL_SEAT
BOWL_H = 0.172
BOWL_SEGS = 64
BOWL_T = 0.0012
SHALLOW = 0.030              # --shallow-bowl: rim this much lower
OFFSET_BOWL = 0.001          # --offset-bowl: bowl slid this far off the plate
LUG_AZ = (90.0, 210.0, 330.0)
HANDLE_AZ = -58.0

# --- Planetary hub and flat beater ----------------------------------------
BEATER_AZ = 40.0             # beater plane, degrees from +X
BEATER_A = 0.0045            # beater frame: half-width in its plane
BEATER_B = 0.0030            # half-thickness across it
SPINE_A, SPINE_B = 0.0038, 0.0026
BEATER_CLEAR = 0.0025        # design clearance to the bowl's wall and floor
BEATER_TOP = 0.105           # frame's outer edge stops this far above the floor
BEATER_NECK = 0.128          # frame meets the shaft this far above the floor
SHAFT_R = 0.0066
OFFSET_BEATER = 0.0008       # --offset-beater
LONG_BEATER = 0.0020         # --long-beater: frame this much lower

# --- Attachment hub on the nose -------------------------------------------
HUB_X = XF - 0.004
LOOSE_CAP = 0.005            # --loose-cap: cap backed off the hub

# --- Cord and plug --------------------------------------------------------
CORD_R = 0.0030
CORD_BITE = 0.0002
CORD_PTS = [(-0.146, 0.032, 0.020), (-0.166, 0.032, 0.020), (-0.184, 0.040, 0.010),
            (-0.200, 0.066, 0.0), (-0.198, 0.112, 0.0), (-0.170, 0.150, 0.0),
            (-0.100, 0.172, 0.0), (-0.020, 0.170, 0.0), (0.060, 0.160, 0.0), (0.100, 0.158, 0.0)]
PLUG_SIZE = (0.034, 0.022, 0.017)
PLUG_BITE = 0.0005
PRONG_STAGGER = 0.0005

# --- Props on the counter -------------------------------------------------
DISH_XY = (0.150, -0.235)
DISH_BITE = 0.0003
EGG_BITE = 0.0003
CUP_XY = (-0.090, -0.200)
CUP_YAW = 250.0
CUP_BITE = 0.00045
WHISK_XY = (0.215, -0.365)
WHISK_YAW = 172.0
WHISK_BITE = 0.00025

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.470, 0.570, 0.389)
BASE_TRIS_MIN = 29000
BASE_TRIS_MAX = 30300
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 8
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 2450
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
# enamel, chrome, stainless, stone, rubber, ceramic, egg, beater
FACE_FLOORS = (3980, 2410, 5110, 84, 1080, 745, 700, 515)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Feet: every one sunk into the counter top by a band.
FEET_COUNT = 4
FOOT_SEAT = (0.0001, 0.0008)
# Hinge: the pin's axis runs through the axis of each knuckle it joins.
PIN_OFFSET_MAX = 0.0003
PIN_TILT_MAX_DEG = 0.5
# Bowl: seated in its plate by a band and concentric with it; each lug
# overlaps the bowl's foot.
BOWL_BITE = (0.0002, 0.0010)
BOWL_CONCENTRIC_MAX = 0.0003
LUG_COUNT = 3
# Size: the mixer's height above the counter and the bowl's capacity.
MIXER_H = 0.360
MIXER_H_TOL = 0.006
CAPACITY_L = 4.5
CAPACITY_TOL_L = 0.35
# Beater: coaxial with the planetary socket and plumb; clears the bowl's
# wall and floor inside a band (the "dime test").
BEATER_OFFSET_MAX = 0.0003
BEATER_TILT_MAX_DEG = 0.5
CLEAR_BAND = (0.0012, 0.0040)
# Stance: the mixer's mass centre, from shell volumes and densities, stands
# this far inside the feet's support polygon.
STANCE_MARGIN = 0.040

# Hero: the mixer's front faces the camera's right-front, its speed lever,
# badge and lock lever toward the camera; the props sit in the foreground.
HERO_YAW_DEG = 0.0
WALL_Y = 2.4

ENAMEL_IDX = 0
CHROME_IDX = 1
STEEL_IDX = 2
STONE_IDX = 3
RUBBER_IDX = 4
CERAMIC_IDX = 5
EGG_IDX = 6
BEATER_IDX = 7

# part tags (a face attribute): what each shell is, for the audits
P_COUNTER, P_FOOT, P_BASE, P_NECK, P_HEAD = 1, 2, 3, 4, 5
P_KNUCKLE, P_HEAD_KNUCKLE, P_PIN = 6, 7, 8
P_PLATE, P_LUG, P_BOWL, P_HANDLE = 9, 10, 11, 12
P_PLANET, P_SOCKET, P_SHAFT, P_BEATER = 13, 14, 15, 16
P_BAND, P_BADGE, P_HUB, P_CAP, P_KNOB = 17, 18, 19, 20, 21
P_SPEED, P_LOCK, P_CORD = 22, 23, 24
P_DISH, P_EGG, P_CUP, P_WHISK = 26, 27, 28, 29
# the counter and what rests on it; the cord and plug lie on the counter too
PROP_PARTS = {P_COUNTER, P_DISH, P_EGG, P_CUP, P_WHISK, P_CORD}
# densities, kg/m^3: per material, with the three castings overridden —
# the head is a shell round a motor and air, the neck and base hollow casts
DENSITY = (6600.0, 7900.0, 7900.0, 2700.0, 1200.0, 2300.0, 1100.0, 2700.0)
PART_DENSITY = {P_HEAD: 850.0, P_NECK: 1300.0, P_BASE: 1400.0}

Y_UP = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)))    # local Z -> +Y
Y_DOWN = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))  # local Z -> -Y
X_UP = Matrix(((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)))    # local Z -> +X
X_DOWN = Matrix(((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)))  # local Z -> -X


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

class Builder:
    """A bmesh plus the part tag written on every face it gains."""

    def __init__(self, bm):
        self.bm = bm
        self.tag = bm.faces.layers.int.new("part")

    def part(self, pid):
        for f in self.bm.faces:
            if f[self.tag] == 0:
                f[self.tag] = pid


def _mark(faces, mat_idx):
    for f in faces:
        f.material_index = mat_idx


def add_box(bm, loc, scale, mat_idx):
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = geo["verts"]
    origin = Vector(loc)
    for v in verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])) + origin
    _mark({f for v in verts for f in v.link_faces}, mat_idx)
    return list(verts)


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False, seg_mats=None, cap_mats=None, rmod=None):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: the profile
    is an open polyline closed by n-gon caps at its two ends; otherwise it
    is a closed polygon revolved into a ring shell. ``rmod(i, j)`` scales
    the radius of profile point ``j`` on ring ``i``."""
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
    ref = Vector((1.0, 0.0, 0.0)) if abs(tans[0].x) < 0.9 else Vector((0.0, 0.0, 1.0))
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


def add_flat_sweep(bm, pts, a, b, normal, sides, mat_idx, closed=False):
    """A bar of elliptical section swept along a path lying in the plane
    whose normal is ``normal``: half-width ``a`` in that plane, half
    thickness ``b`` across it. A vertex, not a face, sits at each extreme,
    so no facet is parallel to the plane."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    nv = Vector(normal).normalized()
    rings = []
    for i, p in enumerate(pts):
        if closed:
            t = (pts[(i + 1) % n] - pts[(i - 1) % n]).normalized()
        else:
            t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        perp = nv.cross(t).normalized()
        rings.append([
            bm.verts.new(p + perp * (a * math.cos(2.0 * math.pi * k / sides))
                         + nv * (b * math.sin(2.0 * math.pi * k / sides)))
            for k in range(sides)
        ])
    faces = []
    pairs = list(zip(rings, rings[1:]))
    if closed:
        pairs.append((rings[-1], rings[0]))
    for r0, r1 in pairs:
        for k in range(sides):
            m = (k + 1) % sides
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    if not closed:
        faces.append(bm.faces.new(tuple(reversed(rings[0]))))
        faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_prism(bm, outline, origin, u, v, w, w0, w1, mat_idx):
    """Convex 2D outline in the (u, v) frame at ``origin``, extruded along
    ``w`` from w0 to w1; n-gon caps (triangulated after the chamfer pass)."""
    o, u, v, w = Vector(origin), Vector(u), Vector(v), Vector(w)
    a = [bm.verts.new(o + u * p + v * q + w * w0) for p, q in outline]
    b = [bm.verts.new(o + u * p + v * q + w * w1) for p, q in outline]
    n = len(outline)
    faces = [bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n])) for i in range(n)]
    faces.append(bm.faces.new(tuple(reversed(a))))
    faces.append(bm.faces.new(tuple(b)))
    _mark(faces, mat_idx)
    return a + b


def loft(bm, rings_co, mat_idx, caps=True):
    rings = [[bm.verts.new(p) for p in ring] for ring in rings_co]
    n = len(rings[0])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    if caps:
        faces.append(bm.faces.new(tuple(reversed(rings[0]))))
        faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for r in rings for v in r]


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


def lug_outline(circles, extra=(), n=20):
    """Hull of circles [(x, z, r)] plus loose points."""
    pts = list(extra)
    for x, z, r in circles:
        for k in range(n):
            a = 2.0 * math.pi * (k + 0.5) / n
            pts.append((x + r * math.cos(a), z + r * math.sin(a)))
    return hull2d(pts)


def offset_polyline(pts, t, sign):
    """Miter offset of a 2D polyline by ``t`` toward the side given by the
    segment normal ``sign * (dz, -dx)``."""
    def nrm(p, q):
        dx, dz = q[0] - p[0], q[1] - p[1]
        ln = math.hypot(dx, dz)
        return (sign * dz / ln, -sign * dx / ln)

    out = []
    for i, p in enumerate(pts):
        ns = []
        if i > 0:
            ns.append(nrm(pts[i - 1], p))
        if i < len(pts) - 1:
            ns.append(nrm(p, pts[i + 1]))
        nx = sum(n[0] for n in ns)
        nz = sum(n[1] for n in ns)
        ln = math.hypot(nx, nz)
        nx, nz = nx / ln, nz / ln
        k = t / max(nx * ns[0][0] + nz * ns[0][1], 0.2)
        out.append((p[0] + nx * k, p[1] + nz * k))
    return out


def catmull(pts, per=6, closed=False):
    pts = [Vector(p) for p in pts]
    if closed:
        ext = [pts[-1]] + pts + [pts[0], pts[1]]
        count = len(pts)
    else:
        ext = [pts[0] * 2.0 - pts[1]] + pts + [pts[-1] * 2.0 - pts[-2]]
        count = len(pts) - 1
    out = []
    for i in range(1, count + 1):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2.0 * p1) + (-p0 + p2) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                              + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t))
    if not closed:
        out.append(pts[-1])
    return out


def interp(knots, x):
    """Cubic Hermite through (x, y) knots with Catmull-Rom slopes, clamped."""
    xs = [k[0] for k in knots]
    ys = [k[1] for k in knots]
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = max(j for j in range(len(xs) - 1) if xs[j] <= x)

    def slope(j):
        if j == 0:
            return (ys[1] - ys[0]) / (xs[1] - xs[0])
        if j == len(xs) - 1:
            return (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        return (ys[j + 1] - ys[j - 1]) / (xs[j + 1] - xs[j - 1])

    h = xs[i + 1] - xs[i]
    t = (x - xs[i]) / h
    m0, m1 = slope(i) * h, slope(i + 1) * h
    return ((2 * t ** 3 - 3 * t ** 2 + 1) * ys[i] + (t ** 3 - 2 * t ** 2 + t) * m0
            + (-2 * t ** 3 + 3 * t ** 2) * ys[i + 1] + (t ** 3 - t ** 2) * m1)


def spow(v, e):
    return math.copysign(abs(v) ** e, v)


# --------------------------------------------------------------------------
# The body's closed-form surfaces
# --------------------------------------------------------------------------

def base_loop(inset, segs=BASE_SEGS):
    hx, hy = BASE_HX - inset, BASE_HY - inset
    out = []
    for k in range(segs):
        a = 2.0 * math.pi * k / segs
        out.append((BASE_CX + hx * spow(math.cos(a), 2.0 / BASE_EXP),
                    hy * spow(math.sin(a), 2.0 / BASE_EXP)))
    return out


def base_half_width(x, inset=0.0):
    hx, hy = BASE_HX - inset, BASE_HY - inset
    t = min(abs(x - BASE_CX) / hx, 1.0)
    return hy * (1.0 - t ** BASE_EXP) ** (1.0 / BASE_EXP)


def head_end(x):
    if x < XR + REAR_ZONE:
        d = min((XR + REAR_ZONE - x) / REAR_ZONE, 1.0)
        return REAR_E + (1.0 - REAR_E) * (1.0 - d ** REAR_P) ** (1.0 / REAR_P)
    if x > XF - FRONT_ZONE:
        d = min((x - (XF - FRONT_ZONE)) / FRONT_ZONE, 1.0)
        return FRONT_E + (1.0 - FRONT_E) * (1.0 - d ** FRONT_P) ** (1.0 / FRONT_P)
    return 1.0


def head_sec(x):
    """(centre z, half-height, half-width) of the head's section at x."""
    top = interp(HEAD_TOP, x)
    bot = interp(HEAD_BOT, x)
    e = head_end(x)
    return CT + 0.5 * (top + bot), 0.5 * (top - bot) * e, interp(HEAD_W, x) * e


def head_stations():
    xs = []
    for k in range(HEAD_ZONE_STEPS):
        phi = 0.5 * math.pi * k / HEAD_ZONE_STEPS
        d = math.cos(phi) ** (2.0 / REAR_P)
        xs.append(XR + REAR_ZONE * (1.0 - d))
    x0, x1 = XR + REAR_ZONE, XF - FRONT_ZONE
    for k in range(HEAD_MID):
        xs.append(x0 + (x1 - x0) * k / HEAD_MID)
    for k in range(HEAD_ZONE_STEPS + 1):
        phi = 0.5 * math.pi * (HEAD_ZONE_STEPS - k) / HEAD_ZONE_STEPS
        d = math.cos(phi) ** (2.0 / FRONT_P)
        xs.append(x1 + FRONT_ZONE * d)
    return xs


def head_ring(x, off=0.0, segs=HEAD_SEGS):
    """Section points at x, offset ``off`` along each point's in-section normal."""
    zc, h, w = head_sec(x)
    pts = []
    for k in range(segs):
        a = 2.0 * math.pi * k / segs
        c, s = math.cos(a), math.sin(a)
        n = N_TOP if s >= 0.0 else N_BOT
        pts.append((w * spow(c, 2.0 / n), zc + h * spow(s, 2.0 / n)))
    if off:
        out = []
        for k, (y, z) in enumerate(pts):
            y0, z0 = pts[k - 1]
            y1, z1 = pts[(k + 1) % segs]
            ty, tz = y1 - y0, z1 - z0
            ln = math.hypot(ty, tz)
            out.append((y + off * tz / ln, z - off * ty / ln))
        pts = out
    return [Vector((x, y, z)) for y, z in pts]


def head_y(x, z):
    """The head's side, |y|, at (x, z)."""
    zc, h, w = head_sec(x)
    t = (z - zc) / h
    n = N_TOP if t >= 0.0 else N_BOT
    if abs(t) >= 1.0:
        return 0.0
    return w * (1.0 - abs(t) ** n) ** (1.0 / n)


def head_zbot(x, y):
    zc, h, w = head_sec(x)
    t = min(abs(y) / w, 1.0)
    return zc - h * (1.0 - t ** N_BOT) ** (1.0 / N_BOT)


def neck_sec(z_rel):
    zs = [s[0] for s in NECK]
    z_rel = min(max(z_rel, zs[0]), zs[-1])
    i = max(j for j in range(len(zs) - 1) if zs[j] <= z_rel)
    t = (z_rel - zs[i]) / (zs[i + 1] - zs[i])
    a, b = NECK[i], NECK[i + 1]
    return tuple(a[k] + (b[k] - a[k]) * t for k in (1, 2, 3))


def neck_loop(cx, hx, hy):
    out = []
    for k in range(NECK_SEGS):
        a = 2.0 * math.pi * k / NECK_SEGS
        out.append((cx + hx * spow(math.cos(a), 2.0 / NECK_EXP),
                    hy * spow(math.sin(a), 2.0 / NECK_EXP)))
    return out


def bowl_wall_r(z):
    """Outer radius of the bowl's flared wall at height z above its foot."""
    dz = z - 0.032
    return 0.0858 + 0.180 * dz - 0.09 * dz * dz


def bowl_profiles(shallow=False):
    """(solid lathe profile, inner surface polyline from the axis up) of the
    bowl, heights above its foot."""
    top = BOWL_H - (SHALLOW if shallow else 0.0)
    body = [(0.0600, 0.0090), (0.0680, 0.0105), (0.0760, 0.0140), (0.0822, 0.0210)]
    # four wall stations spread up to the rim, so a shallower bowl keeps
    # the same topology
    for k in range(4):
        z = 0.032 + (top - 0.018 - 0.032) * k / 3.0
        body.append((bowl_wall_r(z), z))
    body.append((bowl_wall_r(top - 0.006), top - 0.006))
    inner = offset_polyline(body, BOWL_T, -1.0)
    rw = bowl_wall_r(top - 0.006)
    bead = [(rw + 0.0008, top - 0.0052), (rw + 0.0030, top - 0.0048), (rw + 0.0047, top - 0.0030),
            (rw + 0.0052, top - 0.0009), (rw + 0.0042, top - 0.0003 + 0.0003),
            (rw + 0.0021, top), (rw + 0.0001, top - 0.0008), (rw - 0.0009, top - 0.0026)]
    foot = [(0.044, 0.0080), (0.0495, 0.0080), (0.0510, 0.0060), (0.0515, 0.0000),
            (0.0600, 0.0000), (0.0628, 0.0010), (0.0630, 0.0028), (0.0605, 0.0040)]
    zf = inner[0][1]
    solid = foot + body + bead + list(reversed(inner)) + [(0.050, zf), (0.044, zf)]
    surface = [(0.0, zf)] + inner
    return solid, surface, top


# --------------------------------------------------------------------------
# The mixer
# --------------------------------------------------------------------------

def add_counter(bm, bevel_verts):
    x0, x1 = COUNTER_X
    rb, rf, rt, rk = COUNTER_R
    corners = [((x0 + rb, rb), rb, math.pi, 1.5 * math.pi),
               ((x1 - rf, rf), rf, 1.5 * math.pi, 2.0 * math.pi),
               ((x1 - rt, CT - rt), rt, 0.0, 0.5 * math.pi),
               ((x0 + rk, CT - rk), rk, 0.5 * math.pi, math.pi)]
    prof = []
    for (cx, cz), r, a0, a1 in corners:
        steps = 6 if r > 0.006 else 3
        for s in range(steps + 1):
            a = a0 + (a1 - a0) * s / steps
            prof.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    y0, y1 = COUNTER_Y
    rings = [[Vector((x, y, z)) for x, z in prof] for y in (y0, y1)]
    bevel_verts += loft(bm, rings, STONE_IDX)


def add_base(bm):
    loops = [(base_loop(d), BASE_Z0 + z) for d, z in BASE_PROFILE]
    rings = [[Vector((x, y, z)) for x, y in loop] for loop, z in loops]
    loft(bm, rings, ENAMEL_IDX)


def add_foot(bm, x, y, i, lift=0.0):
    zb = CT - FOOT_BITES[i] + lift
    zt = BASE_Z0 + FOOT_TUCKS[i]
    prof = [(FOOT_R - 0.0014, zb), (FOOT_R, zb + 0.0014), (FOOT_R, BASE_Z0 - 0.0010),
            (FOOT_R - 0.0006, BASE_Z0), (FOOT_R - 0.0010, zt)]
    add_lathe(bm, prof, 24, RUBBER_IDX, center=(x, y, 0.0), solid=True,
              phase=0.25 * i * 2.0 * math.pi / 24.0)


def add_neck(bm):
    rings = []
    for z_rel, cx, hx, hy in NECK:
        rings.append([Vector((x, y, CT + z_rel)) for x, y in neck_loop(cx, hx, hy)])
    # the top ring follows the head's underside, SEAM below it
    cx, hx, hy = NECK[-1][1:]
    rings.append([Vector((x, y, head_zbot(x, y) - SEAM)) for x, y in neck_loop(cx, hx, hy)])
    loft(bm, rings, ENAMEL_IDX)


def add_head(bm):
    rings = [head_ring(x) for x in head_stations()]
    loft(bm, rings, ENAMEL_IDX)


def add_band(bm):
    """Chrome trim band wrapped round the head on the head's own sections:
    inner face BAND_BITE inside the enamel, outer face BAND_PROUD proud."""
    x0, x1 = BAND_X
    ch = 0.0008
    prof = [(x0, -BAND_BITE), (x0, BAND_PROUD - 0.0006), (x0 + ch, BAND_PROUD),
            (x1 - ch, BAND_PROUD), (x1, BAND_PROUD - 0.0006), (x1, -BAND_BITE)]
    rings = [head_ring(x, off) for x, off in prof]
    segs = len(rings[0])
    n = len(rings)
    vs = [[bm.verts.new(p) for p in ring] for ring in rings]
    faces = []
    for j in range(n):
        a, b = vs[j], vs[(j + 1) % n]
        for k in range(segs):
            m = (k + 1) % segs
            faces.append(bm.faces.new((a[k], a[m], b[m], b[k])))
    _mark(faces, CHROME_IDX)


def head_frame(x0, z0, side=-1.0):
    """Point, outward normal and in-plane axes of the head's side at (x0, z0)."""
    e = 1e-4
    p0 = Vector((x0, side * head_y(x0, z0), z0))
    dx = (head_y(x0 + e, z0) - head_y(x0 - e, z0)) / (2 * e)
    dz = (head_y(x0, z0 + e) - head_y(x0, z0 - e)) / (2 * e)
    n = Vector((-dx * side, side, -dz * side)).normalized()
    n = -n if n.y * side < 0.0 else n
    u = (Vector((1.0, 0.0, 0.0)) - n * n.x).normalized()
    v = n.cross(u)
    if v.z < 0.0:
        v = -v
    return p0, n, u, v


def flat_plate(bm, x0, z0, hx, hz, front, mat_idx, n=28, side=-1.0, bite=0.0008):
    """An oval plate lying in the head's tangent plane at (x0, z0), its face
    ``front`` out from that plane. Its back is buried by the surface's
    measured drop under the outline plus ``bite``, so no edge floats."""
    p0, nrm, u, v = head_frame(x0, z0, side)
    outline = []
    for k in range(n):
        a = 2.0 * math.pi * k / n
        outline.append(p0 + u * (hx * spow(math.cos(a), 0.8)) + v * (hz * spow(math.sin(a), 0.8)))
    drop = 0.0
    for q in outline:
        s = Vector((q.x, side * head_y(q.x, q.z), q.z))
        drop = max(drop, nrm.dot(q - s))
    back = -(drop + bite)
    a_ring = [bm.verts.new(q + nrm * back) for q in outline]
    b_ring = [bm.verts.new(q + nrm * front) for q in outline]
    faces = [bm.faces.new((a_ring[i], b_ring[i], b_ring[(i + 1) % n], a_ring[(i + 1) % n]))
             for i in range(n)]
    faces.append(bm.faces.new(tuple(reversed(a_ring))))
    faces.append(bm.faces.new(tuple(b_ring)))
    _mark(faces, mat_idx)
    return a_ring + b_ring


def pin_profile(y_neg, y_pos, shaft_r, head_r):
    """Solid Y-lathe profile of a pin with dome heads whose undersides sit
    at y_neg / y_pos."""
    return [(head_r * 0.33, y_neg - 0.0030), (head_r * 0.74, y_neg - 0.0023),
            (head_r * 0.96, y_neg - 0.0010), (head_r, y_neg), (shaft_r, y_neg),
            (shaft_r, y_pos), (head_r, y_pos), (head_r * 0.96, y_pos + 0.0010),
            (head_r * 0.74, y_pos + 0.0023), (head_r * 0.33, y_pos + 0.0030)]


def build_mixer_mesh(name, bevel_offset, bevel_segments, flags=None):
    fl = dict(flags or {})
    bm = bmesh.new()
    try:
        B = Builder(bm)
        bevel_verts = []
        chrome_bevel = []

        # --- counter
        add_counter(bm, bevel_verts)
        B.part(P_COUNTER)

        # --- feet, base, neck, head
        for i, (fx, fy) in enumerate(FEET_XY):
            if fl.get("bunch_feet"):
                fx = BUNCH_FEET_X[0] if fx < 0.0 else BUNCH_FEET_X[1]
            lift = FLOAT_FOOT if (fl.get("float_foot") and i == 3) else 0.0
            add_foot(bm, fx, fy, i, lift)
            B.part(P_FOOT)
        add_base(bm)
        B.part(P_BASE)
        add_neck(bm)
        B.part(P_NECK)
        add_head(bm)
        B.part(P_HEAD)
        add_band(bm)
        B.part(P_BAND)

        # --- hinge: knuckles cast on the neck, one on the head, a pin through
        hc = Vector((HINGE_X, 0.0, CT + HINGE_Z))
        for s, rot in ((1.0, Y_UP), (-1.0, Y_DOWN)):
            y0, y1 = KNUCKLE_Y
            prof = [(KNUCKLE_R - 0.0010, y0), (KNUCKLE_R, y0 + 0.0010), (KNUCKLE_R, y1 - 0.0012),
                    (KNUCKLE_R - 0.0012, y1)]
            add_lathe(bm, prof, 28, ENAMEL_IDX, center=hc, rot=rot, solid=True,
                      phase=0.0 if s > 0 else math.pi / 28.0)
            B.part(P_KNUCKLE)
        add_lathe(bm, [(HEAD_KNUCKLE_R, -HEAD_KNUCKLE_Y), (HEAD_KNUCKLE_R, HEAD_KNUCKLE_Y)], 24,
                  ENAMEL_IDX, center=hc, rot=Y_UP, solid=True, phase=math.pi / 24.0)
        B.part(P_HEAD_KNUCKLE)
        pc = hc + Vector((OFFSET_HINGE if fl.get("offset_hinge") else 0.0, 0.0, 0.0))
        add_lathe(bm, pin_profile(-(KNUCKLE_Y[1] - PIN_BITE), KNUCKLE_Y[1] - PIN_BITE, PIN_R,
                                  PIN_HEAD_R), 20, CHROME_IDX, center=pc, rot=Y_UP, solid=True)
        B.part(P_PIN)

        # --- bowl plate and bayonet lugs
        pl = Vector((BOWL_X, 0.0, 0.0))
        add_lathe(bm, [(PLATE_R - 0.0020, BASE_TOP - 0.0020), (PLATE_R, BASE_TOP),
                       (PLATE_R, PLATE_TOP - 0.0012), (PLATE_R - 0.0012, PLATE_TOP)],
                  BOWL_SEGS, CHROME_IDX, center=pl, solid=True)
        B.part(P_PLATE)
        lug = [(0.0615, PLATE_TOP - 0.0030), (0.0692, PLATE_TOP - 0.0030),
               (0.0692, PLATE_TOP + 0.0050), (0.0674, PLATE_TOP + 0.0070),
               (0.0625, PLATE_TOP + 0.0070), (0.0610, PLATE_TOP + 0.0055)]
        for k, az in enumerate(LUG_AZ):
            a = math.radians(az)
            u = Vector((math.cos(a), math.sin(a), 0.0))
            w = Vector((-math.sin(a), math.cos(a), 0.0))
            # each lug a touch narrower than the last, so no two share a plane
            half = 0.0070 - 0.0002 * k
            chrome_bevel += add_prism(bm, lug, pl, u, Vector((0.0, 0.0, 1.0)), w, -half, half,
                                      CHROME_IDX)
            B.part(P_LUG)

        # --- bowl, rolled rim, strap handle
        bx = BOWL_X + (OFFSET_BOWL if fl.get("offset_bowl") else 0.0)
        solid, surface, top = bowl_profiles(fl.get("shallow_bowl"))
        bc = Vector((bx, 0.0, BOWL_Z0))
        add_lathe(bm, solid, BOWL_SEGS, STEEL_IDX, center=bc, solid=True)
        B.part(P_BOWL)
        ha = math.radians(HANDLE_AZ)
        hr = Vector((math.cos(ha), math.sin(ha), 0.0))
        hn = Vector((-math.sin(ha), math.cos(ha), 0.0))
        ht = 0.0022                      # strap half-thickness, radially

        def wall(z, out):
            return bc + hr * (bowl_wall_r(z) + out) + Vector((0.0, 0.0, z))

        z_up, z_lo = top - 0.022, top - 0.098
        hp = [wall(z_up + 0.012, ht - 0.0008), wall(z_up + 0.004, ht - 0.0008),
              wall(z_up - 0.003, 0.010), wall(z_up - 0.014, 0.024), wall(z_up - 0.034, 0.031),
              wall(z_lo + 0.034, 0.030), wall(z_lo + 0.014, 0.020), wall(z_lo + 0.004, 0.008),
              wall(z_lo - 0.002, ht - 0.0008), wall(z_lo - 0.010, ht - 0.0008)]
        add_flat_sweep(bm, catmull(hp, per=4), ht, 0.0075, hn, 10, STEEL_IDX)
        B.part(P_HANDLE)

        # --- planetary housing, socket, beater
        hb = head_zbot(BOWL_X, 0.0)
        pz = Vector((BOWL_X, 0.0, 0.0))
        add_lathe(bm, [(0.0410, hb + 0.0080), (0.0410, hb - 0.0120), (0.0385, hb - 0.0165),
                       (0.0320, hb - 0.0192), (0.0200, hb - 0.0200)],
                  48, CHROME_IDX, center=pz, solid=True)
        B.part(P_PLANET)
        add_lathe(bm, [(0.0098, hb - 0.0180), (0.0105, hb - 0.0310), (0.0092, hb - 0.0340)],
                  24, CHROME_IDX, center=pz, solid=True, phase=math.pi / 24.0)
        B.part(P_SOCKET)
        zf = BOWL_Z0 + surface[0][1]     # the bowl's inner floor
        drop = LONG_BEATER if fl.get("long_beater") else 0.0
        boff = OFFSET_BEATER if fl.get("offset_beater") else 0.0
        bax = Vector((BOWL_X + boff, 0.0, 0.0))
        phi = math.radians(BEATER_AZ)
        rd = Vector((math.cos(phi), math.sin(phi), 0.0))
        nv = Vector((-math.sin(phi), math.cos(phi), 0.0))
        z_neck = zf + BEATER_NECK - drop
        add_tube(bm, [bax + Vector((0.0, 0.0, hb - 0.0240)), bax + Vector((0.0, 0.0, z_neck + 0.0035))],
                 SHAFT_R, 16, BEATER_IDX)
        # cross pin that engages the socket's bayonet slot
        cp = bax + Vector((0.0, 0.0, hb - 0.0375))
        add_tube(bm, [cp - nv * 0.0115, cp + nv * 0.0115], 0.0021, 10, BEATER_IDX)
        B.part(P_SHAFT)
        # the frame: the bowl's inner surface offset inward by clearance + half-width
        # it follows the full-height bowl's wall: the same r(z) as a shallower
        # bowl's, so --shallow-bowl leaves the beater untouched
        fsurf = bowl_profiles(False)[1]
        off = offset_polyline(fsurf, BEATER_CLEAR + BEATER_A, -1.0)
        z_edge = BEATER_TOP + surface[0][1]
        right = []
        for (r0, z0), (r1, z1) in zip(off, off[1:]):
            # straight between the offset profile's vertices, as the bowl's
            # own lathe is: a spline through them would bulge toward the wall
            for k in range(3):
                t = k / 3.0
                r, z = r0 + (r1 - r0) * t, z0 + (z1 - z0) * t
                if z <= z_edge:
                    right.append((r, z))
        right[0] = (0.0, right[0][1])
        rt, zt = right[-1]
        zn = BEATER_NECK + surface[0][1]
        # shoulder: a quadratic arc from the outer edge in to the shaft
        c1 = (rt + 0.002, zn - 0.002)
        for k in range(1, 9):
            t = k / 8.0
            right.append(((1 - t) ** 2 * rt + 2 * (1 - t) * t * c1[0] + t * t * 0.0115,
                          (1 - t) ** 2 * zt + 2 * (1 - t) * t * c1[1] + t * t * zn))

        def to3(r, z):
            return bax + rd * r + Vector((0.0, 0.0, BOWL_Z0 + z - drop))

        path = ([to3(r, z) for r, z in right]
                + [to3(-r, z) for r, z in reversed(right[1:])])
        add_flat_sweep(bm, path, BEATER_A, BEATER_B, nv, 8, BEATER_IDX, closed=True)
        add_flat_sweep(bm, [to3(0.0, zn), to3(0.0, right[0][1])],
                       SPINE_A, SPINE_B, nv, 8, BEATER_IDX)
        B.part(P_BEATER)

        # --- nose: attachment hub, cap, thumb screw
        hub_zc = head_sec(XF)[0]
        hcen = Vector((HUB_X, 0.0, hub_zc))
        add_lathe(bm, [(0.0270, -0.0120), (0.0270, 0.0035), (0.0284, 0.0055), (0.0284, 0.0130),
                       (0.0262, 0.0155)], 48, CHROME_IDX, center=hcen, rot=X_UP, solid=True)
        B.part(P_HUB)
        capc = hcen + Vector((LOOSE_CAP if fl.get("loose_cap") else 0.0, 0.0, 0.0))
        add_lathe(bm, [(0.0246, 0.0150), (0.0250, 0.0172), (0.0238, 0.0212), (0.0204, 0.0242),
                       (0.0130, 0.0262), (0.0040, 0.0267)], 48, CHROME_IDX, center=capc, rot=X_UP,
                  solid=True, phase=math.pi / 48.0)
        B.part(P_CAP)
        kc = hcen + Vector((0.0090, 0.0, 0.0))

        def knurl(i, j):
            return 0.90 if (j in (2, 3) and i % 2) else 1.0

        add_lathe(bm, [(0.0042, 0.0240), (0.0042, 0.0318), (0.0092, 0.0322), (0.0098, 0.0334),
                       (0.0098, 0.0418), (0.0086, 0.0434), (0.0040, 0.0442)], 32, CHROME_IDX,
                  center=kc, solid=True, rmod=knurl)
        B.part(P_KNOB)

        # --- badge and speed lever on the head's -Y side
        flat_plate(bm, BADGE_X, CT + BADGE_Z, BADGE_H[0], BADGE_H[1], 0.0020, CHROME_IDX)
        flat_plate(bm, BADGE_X, CT + BADGE_Z, BADGE_H[0] - 0.0045, BADGE_H[1] - 0.0030, 0.0029,
                   STEEL_IDX, n=24, bite=0.0012)
        B.part(P_BADGE)
        sz = CT + SPEED_Z
        flat_plate(bm, SPEED_X, sz, 0.018, 0.0058, 0.0016, CHROME_IDX, n=24)
        ys = head_y(SPEED_X, sz)
        s0 = Vector((SPEED_X, -(ys - 0.004), sz))
        s1 = Vector((SPEED_X + 0.005, -(ys + 0.017), sz + 0.006))
        add_tube(bm, [s0, s1], 0.0026, 12, CHROME_IDX)
        d = (s1 - s0).normalized()
        q = d.to_track_quat("Z", "X").to_matrix()
        add_lathe(bm, [(0.0030, -0.0020), (0.0056, 0.0006), (0.0064, 0.0050), (0.0054, 0.0100),
                       (0.0030, 0.0122)], 20, RUBBER_IDX, center=s1, rot=q, solid=True)
        B.part(P_SPEED)

        # --- tilt-lock lever on the neck's -Y side
        lz = CT + LOCK_Z
        lcx, _lhx, lhy = neck_sec(LOCK_Z)
        lc = Vector((lcx, 0.0, lz))
        add_lathe(bm, [(0.0086, lhy - 0.0030), (0.0086, lhy + 0.0028), (0.0076, lhy + 0.0040)],
                  24, CHROME_IDX, center=lc, rot=Y_DOWN, solid=True)
        la = math.radians(-32.0)
        tip = (0.027 * math.cos(la), 0.027 * math.sin(la))
        outline = lug_outline([(0.0, 0.0, 0.0072), (tip[0], tip[1], 0.0046)])
        chrome_bevel += add_prism(bm, outline, lc, Vector((1.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)),
                                  Vector((0.0, -1.0, 0.0)), lhy + 0.0035, lhy + 0.0066, CHROME_IDX)
        B.part(P_LOCK)

        # --- cord: through a strain relief in the base's rear riser, over
        # the counter, to a plug
        cz = CT + CORD_R - CORD_BITE
        pts = [Vector((x, y, (BASE_Z0 + z) if z > 0.0 else cz)) for x, y, z in CORD_PTS]
        cpts = catmull(pts, per=5)
        for p in cpts:
            p.z = max(p.z, cz)
        add_tube(bm, cpts, CORD_R, 8, RUBBER_IDX)
        g = Vector(CORD_PTS[1])
        add_lathe(bm, [(CORD_R - 0.0002, -0.0070), (0.0060, -0.0070), (0.0062, 0.0030),
                       (0.0050, 0.0120), (CORD_R + 0.0004, 0.0165)], 20, RUBBER_IDX,
                  center=(-0.1515, g.y, BASE_Z0 + g.z), rot=X_DOWN)
        end = cpts[-1]
        dirn = cpts[-1] - cpts[-3]
        dirn.z = 0.0
        dirn.normalize()
        rz = Matrix.Rotation(math.atan2(dirn.y, dirn.x), 3, "Z")
        lx, ly, lz_ = PLUG_SIZE
        plc = end + dirn * (lx / 2.0 - 0.0040)
        plc.z = CT - PLUG_BITE + lz_ / 2.0
        body = add_box(bm, (0.0, 0.0, 0.0), (lx, ly, lz_), RUBBER_IDX)
        for v in body:
            v.co = plc + rz @ v.co
        bevel_verts += body
        for side in (-1.0, 1.0):
            st = PRONG_STAGGER if side > 0 else 0.0
            q0 = plc + rz @ Vector((lx / 2.0 - 0.004 - st, side * 0.0065, 0.0))
            q1 = plc + rz @ Vector((lx / 2.0 + 0.016 + st, side * 0.0065, 0.0))
            add_tube(bm, [q0, q1], 0.0020, 8, CHROME_IDX, phase=math.pi / 8.0 if side > 0 else 0.0)
        B.part(P_CORD)

        # --- props: a glazed dish with two eggs, a measuring cup, a whisk
        dz0 = CT - DISH_BITE
        dc = Vector((DISH_XY[0], DISH_XY[1], dz0))
        dish = [(0.030, 0.0030), (0.0335, 0.0), (0.0385, 0.0), (0.0410, 0.0035), (0.0470, 0.0060),
                (0.0560, 0.0110), (0.0630, 0.0190), (0.0668, 0.0280), (0.0676, 0.0335),
                (0.0660, 0.0352), (0.0638, 0.0340), (0.0612, 0.0270), (0.0555, 0.0170),
                (0.0480, 0.0110), (0.0380, 0.0082), (0.0300, 0.0080)]
        add_lathe(bm, dish, 48, CERAMIC_IDX, center=dc, solid=True)
        B.part(P_DISH)
        floor_z = dz0 + 0.0080
        for k, (ex, ey, yaw) in enumerate(((0.004, -0.0235, 12.0), (-0.004, 0.0235, -8.0))):
            eprof = []
            L, D = 0.0570, 0.0438
            for j in range(15):
                t = -1.0 + 2.0 * (j + 0.5) / 15.0
                t = math.copysign(abs(t) ** 0.8, t)
                x = 0.5 * L * t
                r = 0.5 * D * math.sqrt(max(1.0 - t * t, 0.0)) * (1.0 + 0.10 * t)
                eprof.append((max(r, 0.0015), x))
            rmax = max(r for r, _ in eprof)
            er = Matrix.Rotation(math.radians(yaw), 3, "Z") @ X_UP
            ec = Vector((DISH_XY[0] + ex, DISH_XY[1] + ey, floor_z - EGG_BITE + rmax))
            # a vertex, not a facet, at each egg's lowest point
            add_lathe(bm, eprof, 24, EGG_IDX, center=ec, rot=er, solid=True)
        B.part(P_EGG)

        cz0 = CT - CUP_BITE
        cc = Vector((CUP_XY[0], CUP_XY[1], cz0))
        cup = [(0.0270, 0.0000), (0.0318, 0.0006), (0.0340, 0.0030), (0.0368, 0.0200),
               (0.0400, 0.0480), (0.0408, 0.0515), (0.0426, 0.0522), (0.0436, 0.0540),
               (0.0428, 0.0556), (0.0410, 0.0560), (0.0392, 0.0548), (0.0386, 0.0490),
               (0.0354, 0.0205), (0.0326, 0.0040), (0.0300, 0.0026), (0.0260, 0.0026)]
        add_lathe(bm, cup, 48, STEEL_IDX, center=cc, solid=True)
        cy = math.radians(CUP_YAW)
        cu = Vector((math.cos(cy), math.sin(cy), 0.0))
        cw = Vector((-math.sin(cy), math.cos(cy), 0.0))
        r_root = 0.0400 - 0.0010
        outl = lug_outline([(r_root + 0.074, 0.0, 0.0085)],
                           [(r_root, -0.0090), (r_root, 0.0090), (r_root + 0.020, -0.0110),
                            (r_root + 0.020, 0.0110)])
        chrome_bevel += add_prism(bm, outl, cc, cu, cw, Vector((0.0, 0.0, 1.0)), 0.0470, 0.0492,
                                  STEEL_IDX)
        B.part(P_CUP)

        # whisk: built along +X from the handle's end, then laid on the counter
        start = len(bm.verts)
        add_lathe(bm, [(0.0040, 0.0000), (0.0086, 0.0012), (0.0104, 0.0060), (0.0108, 0.0350),
                       (0.0098, 0.0850), (0.0088, 0.1080), (0.0082, 0.1110)], 24, STEEL_IDX,
                  rot=X_UP, solid=True)
        add_lathe(bm, [(0.0080, 0.1060), (0.0094, 0.1080), (0.0094, 0.1230), (0.0080, 0.1260),
                       (0.0040, 0.1275)], 24, STEEL_IDX, rot=X_UP, solid=True, phase=math.pi / 24.0)
        handle_n = len(bm.verts)
        for k in range(5):
            psi = math.radians(18.0 + 36.0 * k)
            dk = Vector((0.0, math.cos(psi), math.sin(psi)))
            tip_u = 0.2870 + 0.0014 * k
            scale = 1.0 + 0.015 * k

            def rad(s):
                if s < 0.72:
                    return 0.0030 + (0.0368 * scale - 0.0030) * math.sin(0.5 * math.pi * s / 0.72) ** 1.25
                return 0.0368 * scale * math.sqrt(max(1.0 - ((s - 0.72) / 0.28) ** 2, 0.0))

            side = []
            for j in range(26):
                s = j / 25.0
                s = 1.0 - (1.0 - s) ** 1.15
                u = 0.1160 + (tip_u - 0.1160) * s
                side.append((u, rad(s)))
            wpts = [Vector((u, 0.0, 0.0)) + dk * r for u, r in side]
            wpts += [Vector((u, 0.0, 0.0)) - dk * r for u, r in reversed(side[:-1])]
            add_tube(bm, wpts, 0.00115, 6, STEEL_IDX, phase=0.3 * k)
        bm.verts.ensure_lookup_table()
        hverts = list(bm.verts[start:handle_n])
        wverts = list(bm.verts[handle_n:])

        def lowest(alpha):
            m = Matrix.Rotation(-alpha, 3, "Y")
            return (min((m @ v.co).z for v in hverts), min((m @ v.co).z for v in wverts))

        lo_a, hi_a = 0.0, 0.4
        for _ in range(50):
            mid = 0.5 * (lo_a + hi_a)
            h_z, w_z = lowest(mid)
            if h_z < w_z:
                hi_a = mid
            else:
                lo_a = mid
        alpha = 0.5 * (lo_a + hi_a)
        m = Matrix.Rotation(math.radians(WHISK_YAW), 3, "Z") @ Matrix.Rotation(-alpha, 3, "Y")
        zlow = min((m @ v.co).z for v in hverts + wverts)
        shift = Vector((WHISK_XY[0], WHISK_XY[1], CT - WHISK_BITE - zlow))
        for v in hverts + wverts:
            v.co = m @ v.co + shift
        B.part(P_WHISK)

        if bevel_offset > 0.0:
            # Chamfer the counter's cut ends, the plug and the chrome tabs,
            # one pass per material with material= set, over sorted edges (a
            # set of BMEdges iterates in memory order).
            for verts, mat_idx, off in ((bevel_verts, STONE_IDX, 2.5 * bevel_offset),
                                        (bevel_verts, RUBBER_IDX, 2.0 * bevel_offset),
                                        (chrome_bevel, CHROME_IDX, 0.5 * bevel_offset),
                                        (chrome_bevel, STEEL_IDX, 0.4 * bevel_offset)):
                bm.edges.index_update()
                edges = sorted(
                    {e for v in verts if v.is_valid for e in v.link_edges
                     if len(e.link_faces) == 2
                     and all(f.material_index == mat_idx for f in e.link_faces)
                     and e.calc_face_angle() > math.radians(60.0)},
                    key=lambda e: e.index,
                )
                if edges:
                    bmesh.ops.bevel(bm, geom=edges, offset=off, segments=bevel_segments,
                                    profile=0.5, affect="EDGES", clamp_overlap=True,
                                    material=mat_idx)

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


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def principled(name, color, metallic, roughness, roughness_var=0.0, mottle=0.0,
               noise_scale=14.0, coat=0.0, stretch=None):
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
        if stretch:
            # brushed: the noise is squeezed along one axis into fine streaks
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = stretch
            nt.links.new(coord.outputs["Object"], mp.inputs["Vector"])
            nt.links.new(mp.outputs["Vector"], noise.inputs["Vector"])
        else:
            nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
        if roughness_var > 0.0:
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            lo = max(0.05, roughness - roughness_var)
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


def stone_material():
    """Honed limestone: isotropic object-space mottling in two octaves, fine
    dark fossil speckle, and the speckle again in the roughness and a faint
    bump. No veins: at hero scale a vein band read as a wet smear."""
    mat = bpy.data.materials.new("CounterStone")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = 0.0
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mott = nt.nodes.new("ShaderNodeTexNoise")
    mott.inputs["Scale"].default_value = 7.0
    mott.inputs["Detail"].default_value = 8.0
    mott.inputs["Roughness"].default_value = 0.62
    nt.links.new(coord.outputs["Object"], mott.inputs["Vector"])
    base = nt.nodes.new("ShaderNodeValToRGB")
    base.color_ramp.elements[0].position = 0.34
    base.color_ramp.elements[0].color = (0.150, 0.136, 0.116, 1.0)
    base.color_ramp.elements[1].position = 0.70
    base.color_ramp.elements[1].color = (0.228, 0.210, 0.182, 1.0)
    nt.links.new(mott.outputs["Fac"], base.inputs["Fac"])
    dots = nt.nodes.new("ShaderNodeTexVoronoi")
    dots.inputs["Scale"].default_value = 140.0
    nt.links.new(coord.outputs["Object"], dots.inputs["Vector"])
    dramp = nt.nodes.new("ShaderNodeValToRGB")
    dramp.color_ramp.elements[0].position = 0.0
    dramp.color_ramp.elements[0].color = (0.55, 0.55, 0.55, 1.0)
    dramp.color_ramp.elements[1].position = 0.12
    dramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(dots.outputs["Distance"], dramp.inputs["Fac"])
    mult = nt.nodes.new("ShaderNodeVectorMath")
    mult.operation = "MULTIPLY"
    nt.links.new(base.outputs["Color"], mult.inputs[0])
    nt.links.new(dramp.outputs["Color"], mult.inputs[1])
    nt.links.new(mult.outputs["Vector"], bsdf.inputs["Base Color"])
    speck = nt.nodes.new("ShaderNodeTexNoise")
    speck.inputs["Scale"].default_value = 260.0
    speck.inputs["Detail"].default_value = 2.0
    nt.links.new(coord.outputs["Object"], speck.inputs["Vector"])
    rr = nt.nodes.new("ShaderNodeValToRGB")
    rr.color_ramp.elements[0].position = 0.35
    rr.color_ramp.elements[0].color = (0.42, 0.42, 0.42, 1.0)
    rr.color_ramp.elements[1].position = 0.70
    rr.color_ramp.elements[1].color = (0.62, 0.62, 0.62, 1.0)
    nt.links.new(speck.outputs["Fac"], rr.inputs["Fac"])
    nt.links.new(rr.outputs["Color"], bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    bump.inputs["Distance"].default_value = 0.0005
    nt.links.new(speck.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def mixer_materials():
    """(enamel, chrome, stainless, stone, rubber, ceramic, egg, beater):
    shared by the check and the render.

    The body is a muted slate-blue enamel under a clear coat; trim, plate,
    hub and hinge pin are chrome, rough enough to catch the key rather than
    mirror a black stage; bowl, cup and whisk are brushed stainless; the
    counter is honed limestone; feet, cord and plug are matte rubber; the
    dish a glazed terracotta; the eggs brown; the beater white-coated.
    """
    enamel = principled("MixerEnamel", (0.070, 0.135, 0.190, 1.0), 0.0, 0.26,
                        roughness_var=0.08, mottle=0.06, noise_scale=40.0, coat=0.45)
    chrome = principled("MixerChrome", (0.86, 0.86, 0.88, 1.0), 1.0, 0.24,
                        roughness_var=0.05, noise_scale=70.0)
    steel = principled("MixerStainless", (0.80, 0.80, 0.81, 1.0), 1.0, 0.40,
                       roughness_var=0.06, noise_scale=9.0, stretch=(1.0, 1.0, 140.0))
    stone = stone_material()
    rubber = principled("MixerRubber", (0.018, 0.018, 0.020, 1.0), 0.0, 0.58,
                        roughness_var=0.08, noise_scale=80.0)
    ceramic = principled("DishGlaze", (0.330, 0.105, 0.052, 1.0), 0.0, 0.18,
                         roughness_var=0.05, mottle=0.12, noise_scale=30.0, coat=0.3)
    egg = principled("EggShell", (0.470, 0.290, 0.170, 1.0), 0.0, 0.52,
                     roughness_var=0.06, mottle=0.14, noise_scale=180.0)
    beater = principled("BeaterCoat", (0.640, 0.630, 0.600, 1.0), 0.0, 0.34,
                        roughness_var=0.05, noise_scale=60.0)
    return enamel, chrome, steel, stone, rubber, ceramic, egg, beater


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


class Shell:
    def __init__(self, me, idx, verts, polys, tags):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.mean = sum(pts, Vector()) / len(pts)
        mats, parts = {}, {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
            t = tags[p.index]
            if t:
                parts[t] = parts.get(t, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        self.part = max(parts, key=parts.get) if parts else 0
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)


def pca_axis(pts, largest=True):
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    _w, vecs = np.linalg.eigh(q.T @ q)
    axis = vecs[:, -1] if largest else vecs[:, 0]
    return c, axis


def classify(me):
    groups = shells(me)
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(p)
    attr = me.attributes.get("part")
    tags = [0] * len(me.polygons)
    if attr is not None:
        attr.data.foreach_get("value", tags)
    parts = [Shell(me, i, g, polys[i], tags) for i, g in enumerate(groups)]
    by = {}
    for s in parts:
        by.setdefault(s.part, []).append(s)
    return {"all": parts, "groups": groups, "by": by}


def one(cls, pid):
    got = cls["by"].get(pid, [])
    return got[0] if len(got) == 1 else None


def feet_audit(cls):
    counter = one(cls, P_COUNTER)
    feet = cls["by"].get(P_FOOT, [])
    if counter is None:
        return None
    top = counter.hi.z
    seats = [top - f.lo.z for f in feet]
    return {"count": len(feet), "top": top, "seats": seats}


def hinge_audit(cls):
    pin = one(cls, P_PIN)
    knuckles = cls["by"].get(P_KNUCKLE, []) + cls["by"].get(P_HEAD_KNUCKLE, [])
    if pin is None:
        return None
    c, axis = pca_axis(pin.pts)
    tilt = math.degrees(math.acos(min(1.0, abs(float(axis[1])))))
    worst, not_through = 0.0, 0
    for k in knuckles:
        t = (k.mean.y - c[1]) / axis[1]
        px, pz = c[0] + axis[0] * t, c[2] + axis[2] * t
        worst = max(worst, math.hypot(k.mean.x - px, k.mean.z - pz))
        if k.lo.y < pin.lo.y - 1e-6 or k.hi.y > pin.hi.y + 1e-6:
            not_through += 1
    return {"body": len(cls["by"].get(P_KNUCKLE, [])),
            "head": len(cls["by"].get(P_HEAD_KNUCKLE, [])),
            "offset": worst, "tilt": tilt, "not_through": not_through}


def bowl_audit(cls):
    bowl = one(cls, P_BOWL)
    plate = one(cls, P_PLATE)
    if bowl is None or plate is None:
        return None
    lugs = cls["by"].get(P_LUG, [])
    engaged = sum(1 for g in lugs if g.tree.overlap(bowl.tree))
    handle = one(cls, P_HANDLE)
    return {"bite": plate.hi.z - bowl.lo.z,
            "offset": math.hypot(bowl.mean.x - plate.mean.x, bowl.mean.y - plate.mean.y),
            "lugs": len(lugs), "engaged": engaged,
            "handle": bool(handle and handle.tree.overlap(bowl.tree))}


def capacity_audit(cls):
    """Brim capacity: from the bowl's own axis, rays out to its inner wall
    in 1 mm slices from the floor (a ray down the axis) to the rim."""
    bowl = one(cls, P_BOWL)
    if bowl is None:
        return None
    ax, ay = bowl.mean.x, bowl.mean.y
    hit = bowl.tree.ray_cast(Vector((ax, ay, bowl.hi.z - 0.001)), Vector((0.0, 0.0, -1.0)))
    if hit[0] is None:
        return None
    floor = hit[0].z
    vol = 0.0
    dz = 0.001
    z = floor + 0.5 * dz
    d = Vector((math.cos(1.1), math.sin(1.1), 0.0))
    while z < bowl.hi.z:
        h = bowl.tree.ray_cast(Vector((ax, ay, z)), d)
        if h[0] is None:
            break
        r = math.hypot(h[0].x - ax, h[0].y - ay)
        vol += math.pi * r * r * dz
        z += dz
    return {"floor": floor, "litres": vol * 1000.0}


def beater_audit(cls, floor):
    socket = one(cls, P_SOCKET)
    # the shaft is the tallest shell of its part; the other is its cross pin
    shaft = max(cls["by"].get(P_SHAFT, []), key=lambda s: s.size.z, default=None)
    bowl = one(cls, P_BOWL)
    frame = cls["by"].get(P_BEATER, [])
    if socket is None or shaft is None or bowl is None or not frame:
        return None
    # the shaft's own axis: the round tube, not its cross pin
    tube = [p for p in shaft.pts if math.hypot(p.x - shaft.mean.x, p.y - shaft.mean.y) < SHAFT_R + 1e-4]
    c, axis = pca_axis(tube)
    tilt = math.degrees(math.acos(min(1.0, abs(float(axis[2])))))
    offset = math.hypot(c[0] - socket.mean.x, c[1] - socket.mean.y)
    wall = 9.0
    for s in frame:
        for p in s.pts:
            hit = bowl.tree.find_nearest(p)
            if hit[0] is not None:
                wall = min(wall, hit[3])
    low = min(s.lo.z for s in frame)
    return {"offset": offset, "tilt": tilt, "wall": wall, "floor": low - floor,
            "frames": len(frame)}


def shell_mass(s):
    """Volume and centroid of one closed shell (divergence theorem over a
    fan triangulation of its faces)."""
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
    """The mixer's mass centre against the convex polygon of its feet's
    contact faces; the height above the counter; the base's plan size."""
    total = 0.0
    mom = Vector()
    for s in cls["all"]:
        if s.mat is None or s.part in PROP_PARTS:
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * PART_DENSITY.get(s.part, DENSITY[s.mat])
        total += m
        mom += m * cen
    com = mom / total
    pts = []
    for f in cls["by"].get(P_FOOT, []):
        pts += [(p.x, p.y) for p in f.pts if p.z < f.lo.z + 1e-4]
    if len(pts) < 3:
        return None
    hull = hull2d(pts)
    margin = 9.0
    for i in range(len(hull)):
        (x0, y0), (x1, y1) = hull[i], hull[(i + 1) % len(hull)]
        ln = math.hypot(x1 - x0, y1 - y0)
        margin = min(margin, ((x1 - x0) * (com.y - y0) - (y1 - y0) * (com.x - x0)) / ln)
    return {"mass": total, "com": com, "margin": margin}


def mixer_height(cls):
    counter = one(cls, P_COUNTER)
    if counter is None:
        return None
    top = max(s.hi.z for s in cls["all"] if s.part not in PROP_PARTS)
    return top - counter.hi.z


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
        bm.verts.new((0.0, 0.0, 0.2))
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
    img = bpy.data.images.new("MixerNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = RUBBER_IDX
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


FLAG_NAMES = ("float_foot", "offset_hinge", "offset_bowl", "shallow_bowl", "offset_beater",
              "long_beater", "bunch_feet", "loose_cap")


def check(skip_decimate, lift_z=False, stray_vert=False, flags=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(flags or {})
    low = build_mixer_mesh("MixerLow", bevel_offset=0.0006, bevel_segments=1, flags=flags)
    high = build_mixer_mesh("MixerHigh", bevel_offset=0.0006, bevel_segments=3, flags=flags)
    mats = mixer_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the rubber: the plug body is where the high mesh's
    # rounder chamfer differs most from the low.
    target = mats[RUBBER_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("mixer mesh did not build", 3),) + none3

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
    feet = feet_audit(cls)
    hinge = hinge_audit(cls)
    bowl = bowl_audit(cls)
    cap = capacity_audit(cls)
    beat = beater_audit(cls, cap["floor"]) if cap else None
    stance = stance_audit(cls)
    height = mixer_height(cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("mixer has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "MixerLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "MixerLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_mixer_mesh("MixerColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "MixerCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_stand_mixer_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} parts="
          f"{ {k: len(v) for k, v in sorted(cls['by'].items())} }")
    if feet:
        print(f"measured feet={feet['count']} counter_top={feet['top']:.5f} "
              f"seats={[round(s, 5) for s in feet['seats']]}")
    if hinge:
        print(f"measured hinge knuckles={hinge['body']}+{hinge['head']} "
              f"offset={hinge['offset']:.6f} tilt_deg={hinge['tilt']:.4f} "
              f"not_through={hinge['not_through']}")
    if bowl:
        print(f"measured bowl bite={bowl['bite']:.5f} offset={bowl['offset']:.6f} "
              f"lugs={bowl['lugs']} engaged={bowl['engaged']} handle={bowl['handle']}")
    if cap:
        print(f"measured capacity={cap['litres']:.4f}L floor={cap['floor']:.5f} "
              f"height={height:.5f}")
    if beat:
        print(f"measured beater offset={beat['offset']:.6f} tilt_deg={beat['tilt']:.4f} "
              f"wall={beat['wall']:.5f} floor={beat['floor']:.5f} frames={beat['frames']}")
    if stance:
        print(f"measured mass={stance['mass']:.3f}kg com=({stance['com'].x:.4f},"
              f"{stance['com'].y:.4f},{stance['com'].z:.4f}) margin={stance['margin']:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    labels = ("enamel", "chrome", "stainless", "stone", "rubber", "ceramic", "egg", "beater")
    for idx, (floor, label) in enumerate(zip(FACE_FLOORS, labels)):
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
    if (feet is None or feet["count"] != FEET_COUNT
            or any(not (FOOT_SEAT[0] <= s <= FOOT_SEAT[1]) for s in feet["seats"])):
        return (fail(f"feet on the counter: {feet}", 16),) + none3
    if (hinge is None or hinge["body"] != 2 or hinge["head"] != 1
            or hinge["offset"] > PIN_OFFSET_MAX or hinge["tilt"] > PIN_TILT_MAX_DEG
            or hinge["not_through"]):
        return (fail(f"hinge pin: {hinge}", 17),) + none3
    if (bowl is None or not (BOWL_BITE[0] <= bowl["bite"] <= BOWL_BITE[1])
            or bowl["offset"] > BOWL_CONCENTRIC_MAX or bowl["lugs"] != LUG_COUNT
            or bowl["engaged"] != LUG_COUNT or not bowl["handle"]):
        return (fail(f"bowl seat: {bowl}", 18),) + none3
    if (cap is None or height is None or abs(height - MIXER_H) > MIXER_H_TOL
            or abs(cap["litres"] - CAPACITY_L) > CAPACITY_TOL_L):
        return (fail(f"size: height {height} capacity {cap}", 19),) + none3
    if (beat is None or beat["offset"] > BEATER_OFFSET_MAX
            or beat["tilt"] > BEATER_TILT_MAX_DEG):
        return (fail(f"beater coaxial: {beat}", 20),) + none3
    if (not (CLEAR_BAND[0] <= beat["wall"] <= CLEAR_BAND[1])
            or not (CLEAR_BAND[0] <= beat["floor"] <= CLEAR_BAND[1])):
        return (fail(f"beater clearance: {beat}", 21),) + none3
    if stance is None or stance["margin"] < STANCE_MARGIN:
        return (fail(f"stance: {stance}", 22),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 23),) + none3
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

    # The house rig scaled to a 0.6 m prop: warm key upper left, cool fill
    # low right, cool rim behind, warm wedge pooled on the back wall.
    # The camera looks along (-0.72, 0.69), so the wall behind the mixer in
    # frame is 2.5 m to its -X; the wedge pools there.
    light("Key", (-0.25, -1.8, 1.5), 35.0, 0.8, (1.0, 0.95, 0.90), spread=18.0)
    light("Fill", (1.9, 0.4, 0.3), 5.5, 2.2, (0.72, 0.82, 1.0))
    light("Rim", (-0.9, 0.5, 0.8), 18.0, 0.7, (0.62, 0.78, 1.0))
    light("Wedge", (-1.3, 1.4, 0.6), 41.0, 1.2, (1.0, 0.68, 0.38),
          target=(centre.x - 2.5, centre.y + WALL_Y, 0.35))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((0.72, -0.69, 0.0)).normalized()
    cam.location = centre + view * 1.47 + Vector((0.0, 0.0, 0.27))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.065))
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
    # Standard, not AgX: AgX washes the enamel toward pastel
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
    p.add_argument("--float-foot", action="store_true")
    p.add_argument("--offset-hinge", action="store_true")
    p.add_argument("--offset-bowl", action="store_true")
    p.add_argument("--shallow-bowl", action="store_true")
    p.add_argument("--offset-beater", action="store_true")
    p.add_argument("--long-beater", action="store_true")
    p.add_argument("--bunch-feet", action="store_true")
    p.add_argument("--loose-cap", action="store_true")
    args = p.parse_args(argv)

    flags = {k: getattr(args, k) for k in FLAG_NAMES}
    code, low, target, tex = check(args.skip_decimate, lift_z=args.lift_z,
                                   stray_vert=args.stray_vert, flags=flags)
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("stand-mixer OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
