"""Game-ready balanced-arm desk lamp — a showcase piece, not an example.

Asserts budget conformance of a procedural architect's lamp after composing
shipped pipeline pieces: bmesh construction, UVs, six materials, high-to-low
normal bake, LOD chain, convex collider, Unity glTF export.

The lamp is the classic balanced-arm design. A three-tier cast base with
rounded corners carries a swivel turret on a bearing washer. A yoke on the
turret carries two parallelogram arm sections, each made of two parallel
rods. Each rod ends in an eye boss that is pinned between a pair of knuckle
cheeks. Knurled tension knobs sit on the base, elbow and shade pins. Three
close-wound tension springs hang by looped ends on cross bars: two on the
base section, one on the upper section. The shade is a domed bell of
enamelled sheet with a white reflector inside, a wired rolled rim, a
chrome band, a push switch and a lamp on a bakelite socket. A flex drapes from a gland on the
shade's back down both arm sections into the base's top tread, and a
rubber cable leaves the base through a grommet and ends in a plug on the
desk.


Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--offset-pin`` joint pins coaxial
through the parts they join, ``--unhook-spring`` spring ends seated on
their anchor bars, ``--hollow-base`` the mass centre over the base
footprint, ``--unscrew-bulb`` one connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python desk_lamp.py --
    blender --background --python desk_lamp.py -- --skip-decimate
    blender --background --python desk_lamp.py -- --output lamp.png
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

# --- Base: three tiers of rounded square, one lofted shell ----------------
BASE_HALF = 0.090           # 0.18 m square footprint
BASE_RC = 0.044             # outer corner radius; each tier's is offset from it
BASE_RC_MIN = 0.005
BASE_CORNER_SEGS = 8
# (inset from the outer edge, z): bottom chamfer, three risers with chamfered
# treads, top face at inset 0.036
BASE_PROFILE = [
    (0.003, 0.000), (0.000, 0.003), (0.000, 0.016), (0.004, 0.020),
    (0.014, 0.020), (0.016, 0.022), (0.016, 0.034), (0.020, 0.038),
    (0.030, 0.038), (0.032, 0.040), (0.032, 0.048), (0.036, 0.052),
]
BASE_TOP = 0.052
HOLLOW_WALL = 0.0015        # --hollow-base: a pressed-steel shell this thick

# --- Turret and yoke -------------------------------------------------------
WASHER_R = (0.020, 0.035)
WASHER_Z = (0.0515, 0.0545)
TURRET_PROFILE = [(0.032, 0.049), (0.032, 0.057), (0.029, 0.061), (0.024, 0.063),
                  (0.024, 0.071), (0.021, 0.074)]
TURRET_TOP = 0.074
CHEEK_IN = 0.0094           # knuckle cheeks: inner face |y|
CHEEK_OUT = 0.0124          # outer face |y|
CHEEK_LUG_R = 0.010         # cheek outline round each pin station
BOSS_R = 0.0065             # cast boss on each cheek at each pin
BOSS_PROUD = 0.0015
BOSS_BITE = 0.0003
# Stations on one knuckle sit within a few centimetres of each other, so
# their flat faces must not share planes: each station's boss stands a
# little prouder (and its pin head with it) and its eye a little narrower.
# The far cheek's lugs are cast a touch smaller than the knob-side cheek's,
# or the pair's rims would lie in the same planes.
STATION_STAGGER = 0.0003
FAR_CHEEK_TRIM = 0.0004

# --- Arm geometry (the lamp's plane is XZ at y = 0, reaching +X) ----------
PIVOT = (0.0, 0.100)        # base pin B1 (x, z)
ARM1_DEG = 72.0             # lower section, from horizontal
ARM1_LEN = 0.320
ARM2_DEG = -10.0            # upper section
ARM2_LEN = 0.360
LINK_DEG = 120.0            # parallelogram offset between each section's rods
LINK_LEN = 0.030
ROD_R = 0.0036
ROD_Y = 0.0048              # lower rods at -ROD_Y, upper rods at +ROD_Y
EYE_R = 0.0075
EYE_HALF = 0.0040
ROD_END = 0.0030            # rod ends stop this short of the pin, inside the eye
PIN_R = 0.0028
PIN_HEAD_R = 0.0046
PIN_HEAD_BITE = 0.0002
KNOB_R = 0.013
KNOB_W = 0.012
KNOB_BITE = 0.0010
KNOB_RIDGES = 16

# --- Springs and their anchor bars -----------------------------------------
BAR_R = 0.0025
BAR_HEAD_Y = 0.0355
SPRING_Y = 0.033
WIRE_R = 0.0010
COIL_R = 0.0055
PITCH = 0.0030
STEPS_PER_TURN = 8
HOOK_MINOR = 0.0011
HOOK_BITE = 0.0003
HOOK_MAJOR = BAR_R + HOOK_MINOR - HOOK_BITE
TAIL = 0.006
BASE_ANCHOR = (-0.030, -0.012)   # bar 0, from B1
ARM1_ANCHOR = 0.150              # bar 1, along lower rod A from B1
ELBOW_ANCHOR = (0.004, -0.030)   # bar 2, from E1
ARM2_ANCHOR = 0.170              # bar 3, along upper rod A from E1

# --- Shade -----------------------------------------------------------------
SHADE_PIVOT = (0.018, -0.030)    # shade pin S, from H1
SHADE_DEG = -50.0                # shade axis, from horizontal
SHADE_STEM_Z = 0.018             # stem station along the shade axis
SHADE_STEM_OUT = 0.048           # shade axis to S
SHADE_SEGS = 48
SHADE_T = 0.0012
# outer (r, z) along the shade axis: cowl, band step, domed shoulder, bell
SHADE_OUTER = [(0.026, 0.000), (0.030, 0.0015), (0.031, 0.004), (0.031, 0.030),
               (0.033, 0.034), (0.040, 0.040), (0.048, 0.048), (0.054, 0.058),
               (0.059, 0.072), (0.066, 0.100), (0.073, 0.126), (0.079, 0.146)]
RIM_BEAD_R = 0.0032
BAND_Z = (0.0275, 0.036)
SWITCH_Z = 0.016
STEM_R = 0.0038
STEM_BITE = 0.002
UNSCREW = 0.005             # --unscrew-bulb: lamp backed out of its socket

# --- Cable and plug --------------------------------------------------------
CABLE_R = 0.0028
CABLE_Z = CABLE_R + 0.0002
CABLE_PTS = [(-0.070, -0.030, 0.0095), (-0.092, -0.030, 0.0095), (-0.110, -0.034, 0.0070),
             (-0.126, -0.046, CABLE_Z), (-0.140, -0.075, CABLE_Z), (-0.141, -0.115, CABLE_Z),
             (-0.128, -0.158, CABLE_Z), (-0.118, -0.192, CABLE_Z), (-0.115, -0.210, 0.0100)]
# The lamp's flex: out of a gland on the shade's back, draped along the rod-B
# side of both sections on the knob side of the arm, into a grommet on the
# base's top tread.
FLEX_R = 0.0021
FLEX_Y = -0.020
FLEX_SAG = (0.008, 0.010)        # lower, upper section
FLEX_ENTRY = (-0.046, -0.020)
PLUG_SIZE = (0.040, 0.026, 0.020)
PRONG_STAGGER = 0.0005

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.725, 0.361, 0.442)
BASE_TRIS_MIN = 29000
BASE_TRIS_MAX = 31500
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 6
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 760
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
ENAMEL_FACES_MIN = 3600
STEEL_FACES_MIN = 8300
BULB_FACES_MIN = 310
RUBBER_FACES_MIN = 1350
REFLECTOR_FACES_MIN = 560
BAKELITE_FACES_MIN = 340


ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Joint pins: every pin's axis runs through the axis of every eye and boss
# it joins (offset in the XZ plane at the eye's own station), the pin spans
# each of them in Y, and it is square to the lamp's plane.
PIN_COUNT = 7
PIN_EYES = 23               # 3 + 3 + 4 + 4 + 3 + 3 + 3
PIN_SEARCH = 0.012
PIN_OFFSET_MAX = 0.0003
PIN_TILT_MAX_DEG = 0.5
OFFSET_PIN = 0.0025
# Springs: each looped end's centre on the axis of the bar it hangs on.
SPRING_COUNT = 3
HOOK_COUNT = 6
BAR_COUNT = 4
SPRING_SEAT_MAX = 0.0006
UNHOOK = 0.010
# Stance: the lamp's mass centre, from shell volumes and material
# densities, stands this far inside the base footprint on every side.
DENSITY = (7850.0, 7850.0, 300.0, 1200.0, 7850.0, 1400.0)
STANCE_MARGIN = 0.025
BASE_WIDTH_TOL = 0.003
ARM_LEN_TOL = 0.003
# Hero yaw: the reach points to the camera's right and 40 degrees toward it,
# so the parallelogram reads in depth and the shade's mouth shows its lamp.
HERO_YAW_DEG = -95.0
WALL_Y = 2.6

ENAMEL_IDX = 0
STEEL_IDX = 1
BULB_IDX = 2
RUBBER_IDX = 3
REFLECTOR_IDX = 4
BAKELITE_IDX = 5

Y_UP = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)))    # local Z -> +Y
Y_DOWN = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))  # local Z -> -Y
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

def _mark(faces, mat_idx):
    for f in faces:
        f.material_index = mat_idx


def v3(xz, y=0.0):
    return Vector((xz[0], y, xz[1]))


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
    is a closed polygon revolved into a ring shell. ``seg_mats`` gives a
    material per profile segment, ``cap_mats`` the (start, end) caps, and
    ``rmod(i, j)`` scales the radius of profile point ``j`` on ring ``i``."""
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
            bm.verts.new(c + r_minor * (radial * math.cos(2.0 * math.pi * k / sides)
                                        + axis * math.sin(2.0 * math.pi * k / sides)))
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
    """Hull of circles [(x, z, r)] plus loose points: a cast knuckle plate."""
    pts = list(extra)
    for x, z, r in circles:
        for k in range(n):
            a = 2.0 * math.pi * (k + 0.5) / n
            pts.append((x + r * math.cos(a), z + r * math.sin(a)))
    return hull2d(pts)


def add_plate_y(bm, outline, y0, y1, mat_idx):
    """Convex XZ outline extruded from y0 to y1; n-gon caps (triangulated
    after the chamfer pass)."""
    a = [bm.verts.new((x, y0, z)) for x, z in outline]
    b = [bm.verts.new((x, y1, z)) for x, z in outline]
    n = len(outline)
    faces = [bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n])) for i in range(n)]
    faces.append(bm.faces.new(tuple(reversed(a))))
    faces.append(bm.faces.new(tuple(b)))
    _mark(faces, mat_idx)
    return a + b


def rrect_loop(inset, n_corner):
    """Rounded-square loop at an inset from the base's outer edge."""
    h = BASE_HALF - inset
    r = max(BASE_RC - inset, BASE_RC_MIN)
    pts = []
    for k, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        cx, cy = sx * (h - r), sy * (h - r)
        a0 = 0.5 * math.pi * k
        for s in range(n_corner + 1):
            a = a0 + 0.5 * math.pi * s / n_corner
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


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


def add_base(bm, hollow):
    """The stepped base: one loft of rounded-square loops. Solid, it is a
    cast block. Hollow, it is a pressed-steel shell HOLLOW_WALL thick."""
    if hollow:
        # the top tread's continuation sets the miter at the last point
        ext = BASE_PROFILE + [(BASE_HALF, BASE_TOP)]
        inner = offset_polyline(ext, HOLLOW_WALL, 1.0)[:-1]
        # the first inner point slides down the bottom chamfer's offset to z = 0
        d0, z0 = inner[0]
        dx, dz = BASE_PROFILE[1][0] - BASE_PROFILE[0][0], BASE_PROFILE[1][1] - BASE_PROFILE[0][1]
        inner[0] = (d0 - dx * (z0 / dz), 0.0)
        profile = list(reversed(inner)) + BASE_PROFILE
    else:
        profile = list(BASE_PROFILE)
    loops = [(rrect_loop(d, BASE_CORNER_SEGS), z) for d, z in profile]
    rings = [[bm.verts.new((x, y, z)) for x, y in loop] for loop, z in loops]
    n = len(rings[0])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, ENAMEL_IDX)


def pin_profile(y_neg, y_pos, shaft_r, head_r, neg_head=True, pos_head=True):
    """Solid Y-lathe profile of a pin or bar: dome heads whose undersides sit
    at y_neg / y_pos, or a plain chamfered end there."""
    p = []
    if neg_head:
        p += [(head_r * 0.33, y_neg - 0.0026), (head_r * 0.74, y_neg - 0.0020),
              (head_r * 0.96, y_neg - 0.0009), (head_r, y_neg), (shaft_r, y_neg)]
    else:
        p += [(shaft_r * 0.75, y_neg), (shaft_r, y_neg + 0.0004)]
    if pos_head:
        p += [(shaft_r, y_pos), (head_r, y_pos), (head_r * 0.96, y_pos + 0.0009),
              (head_r * 0.74, y_pos + 0.0020), (head_r * 0.33, y_pos + 0.0026)]
    else:
        p += [(shaft_r, y_pos - 0.0004), (shaft_r * 0.75, y_pos)]
    return p


def add_y_lathe(bm, xz, profile, segs, mat_idx, rot=Y_UP, phase=0.0, rmod=None):
    return add_lathe(bm, profile, segs, mat_idx, center=v3(xz), rot=rot, phase=phase,
                     solid=True, rmod=rmod)


def add_knob(bm, xz, side):
    """Knurled chrome tension knob on the ``side`` (-1 / +1) cheek face."""
    y0 = CHEEK_OUT - KNOB_BITE
    prof = [(0.0040, y0), (KNOB_R - 0.0010, y0), (KNOB_R, y0 + 0.0010),
            (KNOB_R, y0 + KNOB_W - 0.0015), (KNOB_R - 0.0012, y0 + KNOB_W),
            (0.0085, y0 + KNOB_W + 0.0004), (0.0050, y0 + KNOB_W + 0.0022),
            (0.0020, y0 + KNOB_W + 0.0028)]
    knurl = {2, 3}

    def rmod(i, j):
        return 0.92 if (j in knurl and i % 2) else 1.0

    rot = Y_UP if side > 0 else Y_DOWN
    return add_lathe(bm, prof, 2 * KNOB_RIDGES, STEEL_IDX, center=v3(xz), rot=rot,
                     solid=True, rmod=rmod)


def add_cheek_pair(bm, circles, extra, bosses, bevel_verts):
    """Two knuckle cheeks (one each side of the arm) with a cast boss at
    every pin station on each cheek's outer face; station k's boss stands
    STATION_STAGGER * k prouder."""
    for s in (-1.0, 1.0):
        trim = FAR_CHEEK_TRIM if s > 0 else 0.0
        outline = lug_outline([(x, z, r - trim) for x, z, r in circles],
                              [(x, z + trim) for x, z in extra])
        y0, y1 = sorted((s * CHEEK_IN, s * CHEEK_OUT))
        bevel_verts += add_plate_y(bm, outline, y0, y1, ENAMEL_IDX)
        for k, xz in enumerate(bosses):
            yb0 = CHEEK_OUT - BOSS_BITE - 0.5 * STATION_STAGGER * k
            yb1 = CHEEK_OUT + BOSS_PROUD + STATION_STAGGER * k
            prof = [(BOSS_R, yb0), (BOSS_R, yb1 - 0.0005), (BOSS_R - 0.0005, yb1)]
            add_y_lathe(bm, xz, prof, 16, ENAMEL_IDX, rot=Y_UP if s > 0 else Y_DOWN,
                        phase=math.pi / 20.0 if s > 0 else 0.0)



def add_eye(bm, xz, yc, k, half=EYE_HALF, phase=0.0):
    half -= STATION_STAGGER * k
    prof = [(EYE_R - 0.0008, yc - half), (EYE_R, yc - half + 0.0008),
            (EYE_R, yc + half - 0.0008), (EYE_R - 0.0008, yc + half)]
    add_y_lathe(bm, xz, prof, 16, ENAMEL_IDX, phase=phase)


def add_rod(bm, p, q, y, phase):
    u = (Vector(q) - Vector(p)).normalized()
    a = Vector(p) + u * ROD_END
    b = Vector(q) - u * ROD_END
    add_tube(bm, [v3(a, y), v3(b, y)], ROD_R, 12, ENAMEL_IDX, phase=phase)


def add_pin(bm, xz, k, knob_side=0, offset=0.0):
    """Rivet-style pin through both cheeks; a knob pin ends inside its knob.
    Its heads bear on station k's bosses."""
    y_head = CHEEK_OUT + BOSS_PROUD + STATION_STAGGER * k - PIN_HEAD_BITE
    x = (xz[0] + offset, xz[1])
    if knob_side < 0:
        prof = pin_profile(-(CHEEK_OUT + 0.006), y_head, PIN_R, PIN_HEAD_R,
                           neg_head=False, pos_head=True)
    else:
        prof = pin_profile(-y_head, y_head, PIN_R, PIN_HEAD_R)
    add_y_lathe(bm, x, prof, 12, STEEL_IDX)


def add_bar(bm, xz, y_neg, y_pos, neg_head=True, pos_head=True):
    prof = pin_profile(y_neg, y_pos, BAR_R, BAR_R + 0.0011, neg_head, pos_head)
    add_y_lathe(bm, xz, prof, 10, STEEL_IDX)


def add_spring(bm, pa, pb, y, unhook=0.0):
    """Close-wound extension spring: a looped end hung on each anchor bar
    (a torus threaded across the bar), and one swept wire from loop to loop."""
    a3 = v3(pa, y)
    b3 = v3(pb, y)
    d = (b3 - a3).normalized()
    b3 = b3 - d * unhook
    ax = Vector((0.0, 1.0, 0.0))
    for c in (a3, b3):
        add_ring(bm, c, ax, HOOK_MAJOR, HOOK_MINOR, 10, 4, STEEL_IDX, phase=0.1)
    e2 = d.cross(ax).normalized()
    length = (b3 - a3).length
    s0 = HOOK_MAJOR + TAIL
    s1 = length - HOOK_MAJOR - TAIL
    lead = 0.004
    turns = max(1, round((s1 - s0 - 2.0 * lead) / PITCH))
    pitch = (s1 - s0 - 2.0 * lead) / turns
    path = [a3 + d * (HOOK_MAJOR - 0.0008), a3 + d * s0]
    n = turns * STEPS_PER_TURN
    for i in range(n + 1):
        th = 2.0 * math.pi * i / STEPS_PER_TURN
        s = s0 + lead + pitch * i / STEPS_PER_TURN
        path.append(a3 + d * s + COIL_R * (ax * math.cos(th) + e2 * math.sin(th)))
    path += [a3 + d * s1, b3 - d * (HOOK_MAJOR - 0.0008)]
    add_tube(bm, path, WIRE_R, 5, STEEL_IDX)


def catmull(pts, per=6):
    pts = [Vector(p) for p in pts]
    ext = [pts[0] * 2.0 - pts[1]] + pts + [pts[-1] * 2.0 - pts[-2]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2.0 * p1) + (-p0 + p2) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                              + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t))
    out.append(pts[-1])
    return out


def arm_stations():
    """Every named station of the linkage in the XZ plane."""
    b1 = Vector(PIVOT)
    o = LINK_LEN * Vector((math.cos(math.radians(LINK_DEG)), math.sin(math.radians(LINK_DEG))))
    u1 = Vector((math.cos(math.radians(ARM1_DEG)), math.sin(math.radians(ARM1_DEG))))
    u2 = Vector((math.cos(math.radians(ARM2_DEG)), math.sin(math.radians(ARM2_DEG))))
    e1 = b1 + u1 * ARM1_LEN
    h1 = e1 + u2 * ARM2_LEN
    s = h1 + Vector(SHADE_PIVOT)
    a = Vector((math.cos(math.radians(SHADE_DEG)), math.sin(math.radians(SHADE_DEG))))
    p = Vector((-a.y, a.x))
    cb = s - a * SHADE_STEM_Z - p * SHADE_STEM_OUT
    return {
        "b1": b1, "b2": b1 + o, "e1": e1, "e2": e1 + o, "h1": h1, "h2": h1 + o, "s": s,
        "u1": u1, "u2": u2, "o": o, "a": a, "p": p, "cb": cb,
        "bar0": b1 + Vector(BASE_ANCHOR), "bar1": b1 + u1 * ARM1_ANCHOR,
        "bar2": e1 + Vector(ELBOW_ANCHOR), "bar3": e1 + u2 * ARM2_ANCHOR,
    }


def shade_frame(st):
    a3 = v3(st["a"])
    ey = Vector((0.0, 1.0, 0.0))
    ex = ey.cross(a3)
    return Matrix((ex, ey, a3)).transposed()


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
# The lamp
# --------------------------------------------------------------------------

def build_lamp_mesh(name, bevel_offset, bevel_segments, offset_pin=False,
                    unhook_spring=False, hollow_base=False, unscrew_bulb=False):
    st = arm_stations()
    bm = bmesh.new()
    try:
        bevel_verts = []

        # base, bearing washer, swivel turret, maker's badge
        add_base(bm, hollow_base)
        add_lathe(bm, [(WASHER_R[0], WASHER_Z[0]), (WASHER_R[1] - 0.0008, WASHER_Z[0]),
                       (WASHER_R[1], WASHER_Z[0] + 0.0008), (WASHER_R[1], WASHER_Z[1]),
                       (WASHER_R[0], WASHER_Z[1])], 40, STEEL_IDX)
        add_lathe(bm, TURRET_PROFILE, 40, ENAMEL_IDX, solid=True)
        badge = add_lathe(bm, [(0.0110, -0.0006), (0.0110, 0.0005), (0.0098, 0.0012)], 24,
                          STEEL_IDX, center=(0.0, -(BASE_HALF - 0.016), 0.028), rot=Y_DOWN,
                          solid=True)
        for v in badge:
            v.co.x *= 1.35
            v.co.z = 0.028 + (v.co.z - 0.028) * 0.52

        # base knuckle: yoke cheeks rising out of the turret
        b1, b2, bar0 = st["b1"], st["b2"], st["bar0"]
        add_cheek_pair(bm, [(b1.x, b1.y, CHEEK_LUG_R), (b2.x, b2.y, CHEEK_LUG_R),
                            (bar0.x, bar0.y, 0.008)],
                       [(-0.013, TURRET_TOP - 0.005), (0.013, TURRET_TOP - 0.005)],
                       [b1, b2], bevel_verts)

        # lower section: two rods, parallel by the link offset
        e1, e2, bar2 = st["e1"], st["e2"], st["bar2"]
        # (rod B's facets turned half a step so the parallel pair's never
        # share a plane)
        for k, (p, q) in enumerate(((b1, e1), (b2, e2))):
            add_eye(bm, p, -ROD_Y, k)
            add_eye(bm, q, -ROD_Y, k)
            add_rod(bm, p, q, -ROD_Y, math.pi / 12.0 * (1 - k))

        # elbow knuckle
        add_cheek_pair(bm, [(e1.x, e1.y, CHEEK_LUG_R), (e2.x, e2.y, CHEEK_LUG_R),
                            (bar2.x, bar2.y, 0.008)], [], [e1, e2], bevel_verts)

        # upper section
        h1, h2, s = st["h1"], st["h2"], st["s"]
        for k, (p, q) in enumerate(((e1, h1), (e2, h2))):
            add_eye(bm, p, ROD_Y, k, phase=math.pi / 16.0)
            add_eye(bm, q, ROD_Y, k)
            add_rod(bm, p, q, ROD_Y, math.pi / 12.0 * (1 - k))

        # head knuckle, carrying the shade
        add_cheek_pair(bm, [(h1.x, h1.y, CHEEK_LUG_R), (h2.x, h2.y, CHEEK_LUG_R),
                            (s.x, s.y, CHEEK_LUG_R)], [], [h1, h2, s], bevel_verts)

        # pins: knobs on the base, elbow and shade pins, rivets elsewhere
        for xz, k, knob in ((b1, 0, -1), (b2, 1, 0), (e1, 0, -1), (e2, 1, 0), (h1, 0, 0),
                            (h2, 1, 0), (s, 2, -1)):
            off = OFFSET_PIN if (offset_pin and xz is e1) else 0.0
            add_pin(bm, xz, k, knob_side=knob, offset=off)
            if knob:
                add_knob(bm, xz, knob)

        # spring bars: through the yoke, through lower rod A, through the
        # elbow cheeks, into upper rod A
        bar1, bar3 = st["bar1"], st["bar3"]
        add_bar(bm, bar0, -BAR_HEAD_Y, BAR_HEAD_Y)
        add_bar(bm, bar1, -BAR_HEAD_Y, BAR_HEAD_Y)
        add_bar(bm, bar2, -BAR_HEAD_Y, CHEEK_IN + 0.0015, pos_head=False)
        add_bar(bm, bar3, -BAR_HEAD_Y, ROD_Y + 0.0022, pos_head=False)

        # springs: a pair on the base section, one on the upper section
        add_spring(bm, bar0, bar1, -SPRING_Y, unhook=UNHOOK if unhook_spring else 0.0)
        add_spring(bm, bar0, bar1, SPRING_Y)
        add_spring(bm, bar2, bar3, -SPRING_Y)

        # --- the shade (its own frame: local Z down the shade axis)
        a3 = v3(st["a"])
        p3 = v3(st["p"])
        cb = v3(st["cb"])
        rot = shade_frame(st)
        inner = offset_polyline(SHADE_OUTER, SHADE_T, -1.0)
        prof = SHADE_OUTER + list(reversed(inner))
        n_out = len(SHADE_OUTER)
        seg_mats = [ENAMEL_IDX] * (n_out - 1) + [REFLECTOR_IDX] * (len(prof) - n_out)
        add_lathe(bm, prof, SHADE_SEGS, ENAMEL_IDX, center=cb, rot=rot, solid=True,
                  seg_mats=seg_mats, cap_mats=(ENAMEL_IDX, REFLECTOR_IDX))
        lip_r = 0.5 * (SHADE_OUTER[-1][0] + inner[-1][0])
        lip_z = 0.5 * (SHADE_OUTER[-1][1] + inner[-1][1])
        add_ring(bm, cb + a3 * lip_z, a3, lip_r, RIM_BEAD_R, SHADE_SEGS, 8, ENAMEL_IDX)
        # chrome band over the cowl step
        z0, z1 = BAND_Z
        add_lathe(bm, [(0.0300, z0), (0.0340, z0), (0.0352, z0 + 0.0012),
                       (0.0356, z1 - 0.0012), (0.0346, z1), (0.0300, z1)],
                  SHADE_SEGS, STEEL_IDX, center=cb, rot=rot)
        # bakelite socket, ribbed screw cap, lamp
        add_lathe(bm, [(0.0150, 0.0006), (0.0165, 0.0020), (0.0165, 0.0280),
                       (0.0150, 0.0300)], 32, BAKELITE_IDX, center=cb, rot=rot, solid=True)
        screw = [(0.0118, 0.0270)]
        for k in range(6):
            z = 0.0290 + 0.0025 * k
            screw += [(0.0132, z), (0.0124, z + 0.0012)]
        screw += [(0.0120, 0.0445)]
        lamp_c = cb + a3 * (UNSCREW if unscrew_bulb else 0.0)
        add_lathe(bm, screw, 32, STEEL_IDX, center=lamp_c, rot=rot, solid=True)
        glass = [(0.0112, 0.0430), (0.0120, 0.0460), (0.0135, 0.0520), (0.0200, 0.0660),
                 (0.0268, 0.0820), (0.0298, 0.0980), (0.0292, 0.1120), (0.0245, 0.1260),
                 (0.0160, 0.1340), (0.0060, 0.1375)]
        add_lathe(bm, glass, 32, BULB_IDX, center=lamp_c, rot=rot, solid=True)
        # push switch on the cowl, facing the knob side
        sw = cb + a3 * SWITCH_Z + Vector((0.0, -0.031, 0.0))
        add_lathe(bm, [(0.0080, -0.0020), (0.0085, 0.0000), (0.0085, 0.0080),
                       (0.0075, 0.0092)], 22, BAKELITE_IDX, center=sw, rot=Y_DOWN, solid=True)
        add_lathe(bm, [(0.0045, 0.0080), (0.0045, 0.0118), (0.0034, 0.0128),
                       (0.0015, 0.0132)], 20, BAKELITE_IDX, center=sw, rot=Y_DOWN, solid=True)
        # the shade eye between the head cheeks, on a stem from the cowl
        add_eye(bm, s, 0.0, 2, half=CHEEK_IN - 0.0006)
        foot = cb + a3 * SHADE_STEM_Z + p3 * (SHADE_OUTER[3][0] - STEM_BITE)
        # the stem bites the cowl by STEM_BITE
        add_tube(bm, [foot, v3(s)], STEM_R, 12, STEEL_IDX)

        # the flex: gland on the shade's back cap, draped down rod B of each
        # section (sagging under its own weight), into a grommet on the base
        add_lathe(bm, [(FLEX_R - 0.0002, -0.0004), (0.0055, -0.0004), (0.0058, 0.0030),

                       (0.0042, 0.0075), (FLEX_R - 0.0002, 0.0075)], 16, RUBBER_IDX,
                  center=cb, rot=shade_frame(st) @ Matrix.Rotation(math.pi, 3, "X"))
        fe = Vector((FLEX_ENTRY[0], FLEX_Y, BASE_TOP))
        add_lathe(bm, [(FLEX_R - 0.0002, -0.0020), (0.0050, -0.0020), (0.0054, 0.0012),
                       (0.0044, 0.0034), (FLEX_R - 0.0002, 0.0034)], 16, RUBBER_IDX,
                  center=fe)

        def sagged(p, q, sag, n=5):
            u = (q - p).normalized()
            g = Vector((0.0, -1.0)) - u * u.dot(Vector((0.0, -1.0)))
            g = g.normalized() if g.length > 1e-6 else Vector((0.0, -1.0))
            out = []
            for i in range(n):
                t = 0.08 + 0.84 * i / (n - 1)
                w = p + (q - p) * t + g * (sag * math.sin(math.pi * t))
                out.append(Vector((w.x, FLEX_Y, w.y)))
            return out

        fpts = [cb + a3 * 0.0004, cb - a3 * 0.012,
                cb - a3 * 0.022 + Vector((0.0, 0.6 * FLEX_Y, 0.0)),
                Vector((h2.x + 0.004, FLEX_Y, h2.y - 0.004))]
        fpts += sagged(h2, e2, FLEX_SAG[1])
        fpts += [Vector((e2.x - 0.006, FLEX_Y, e2.y + 0.010))]
        fpts += sagged(e2, b2, FLEX_SAG[0])
        fpts += [Vector((b2.x - 0.012, FLEX_Y, b2.y + 0.002)),
                 Vector((-0.052, FLEX_Y, 0.100)), Vector((-0.056, FLEX_Y, 0.075)),
                 Vector((FLEX_ENTRY[0] - 0.003, FLEX_Y, BASE_TOP + 0.012)),
                 fe + Vector((0.0, 0.0, 0.003)), fe - Vector((0.0, 0.0, 0.003))]
        add_tube(bm, catmull(fpts, per=4), FLEX_R, 8, RUBBER_IDX)

        # the cable: through a grommet in the rear riser, over the desk, to a plug
        cpts = catmull(CABLE_PTS, per=6)
        # the spline overshoots between floor points; the cable rests on the desk
        for p in cpts:
            p.z = max(p.z, CABLE_Z)

        add_tube(bm, cpts, CABLE_R, 10, RUBBER_IDX)
        g = Vector(CABLE_PTS[1])
        add_lathe(bm, [(CABLE_R - 0.0002, -0.0020), (0.0056, -0.0020), (0.0060, 0.0012),
                       (0.0050, 0.0042), (CABLE_R - 0.0002, 0.0042)], 20, RUBBER_IDX,
                  center=(-BASE_HALF, g.y, g.z), rot=X_DOWN)
        end = cpts[-1]
        dirn = (cpts[-1] - cpts[-3])
        dirn.z = 0.0
        dirn.normalize()
        yaw = math.atan2(dirn.y, dirn.x)
        rz = Matrix.Rotation(yaw, 3, "Z")
        # strain relief along the cable's last run
        srot = rz @ Matrix(((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)))
        add_lathe(bm, [(CABLE_R - 0.0002, -0.0100), (0.0040, -0.0060), (0.0062, 0.0000),
                       (0.0062, 0.0050), (CABLE_R - 0.0002, 0.0050)], 20, RUBBER_IDX,
                  center=end, rot=srot)
        lx, ly, lz = PLUG_SIZE
        pc = end + dirn * (0.0040 + lx / 2.0)
        pc.z = lz / 2.0
        body = add_box(bm, (0.0, 0.0, 0.0), (lx, ly, lz), BAKELITE_IDX)
        for v in body:
            v.co = pc + rz @ v.co
        bevel_verts += body
        for side in (-1.0, 1.0):
            # one prong 0.5 mm longer at both ends, or their caps share planes
            st_ = PRONG_STAGGER if side > 0 else 0.0
            q0 = pc + rz @ Vector((lx / 2.0 - 0.004 - st_, side * 0.0065, 0.0))
            q1 = pc + rz @ Vector((lx / 2.0 + 0.016 + st_, side * 0.0065, 0.0))
            add_tube(bm, [q0, q1], 0.0022, 8, STEEL_IDX,
                     phase=math.pi / 8.0 if side > 0 else 0.0)

        if bevel_offset > 0.0:
            # Chamfer the cheek plates' and the plug's cap rims, one pass per
            # material with material= set, over sorted edges (a set of BMEdges
            # iterates in memory order).
            for mat_idx, off in ((ENAMEL_IDX, bevel_offset), (BAKELITE_IDX, 2.5 * bevel_offset)):
                bm.edges.index_update()
                edges = sorted(
                    {e for v in bevel_verts if v.is_valid for e in v.link_edges
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
        # Round stock (rods, springs, cable, shade, lamp) is smooth-shaded;
        # chamfers, knurls and treads stay crisp through sharp edges.
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


def lamp_materials():
    """(enamel, steel, bulb, rubber, reflector, bakelite): shared by the
    check and the render.

    Stove enamel is a deep glossy red with a clear coat; the springs, pins
    and knobs are bright plated steel; the reflector is white enamel; the
    lamp glows warm; cable and grommet are matte black rubber; the socket,
    switch and plug are near-black bakelite.
    """
    enamel = principled("LampEnamel", (0.42, 0.030, 0.026, 1.0), 0.0, 0.30,
                        roughness_var=0.10, mottle=0.10, noise_scale=40.0, coat=0.35)
    steel = principled("LampSteel", (0.80, 0.80, 0.82, 1.0), 1.0, 0.34,
                       roughness_var=0.08, noise_scale=60.0)
    bulb = principled("LampBulb", (0.95, 0.92, 0.84, 1.0), 0.0, 0.18)
    b = bulb.node_tree.nodes["Principled BSDF"]
    for key in ("Emission Color", "Emission"):
        if key in b.inputs:
            b.inputs[key].default_value = (1.0, 0.80, 0.52, 1.0)
            break
    if "Emission Strength" in b.inputs:
        b.inputs["Emission Strength"].default_value = 2.5

    rubber = principled("LampRubber", (0.016, 0.016, 0.018, 1.0), 0.0, 0.58,
                        roughness_var=0.08, noise_scale=80.0)
    reflector = principled("LampReflector", (0.80, 0.78, 0.72, 1.0), 0.0, 0.38,
                           roughness_var=0.06, mottle=0.04, noise_scale=30.0)
    bakelite = principled("LampBakelite", (0.030, 0.019, 0.013, 1.0), 0.0, 0.26,
                          roughness_var=0.06, mottle=0.2, noise_scale=90.0)
    return enamel, steel, bulb, rubber, reflector, bakelite


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
    # sweep along u: only pairs whose u spans overlap are compared
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
    if axis[1] < 0.0:
        axis = -axis
    return c, axis


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    steel = [s for s in parts if s.mat == STEEL_IDX]
    out["coils"] = [s for s in steel if len(s.verts) > 1000]
    out["hooks"] = [s for s in steel if s.size.y < 0.003 and max(s.size) < 0.012]
    out["bars"] = [s for s in steel if s.size.y > 0.042 and max(s.size.x, s.size.z) < 0.008]
    # above the turret: a plug prong is also a short steel rod
    out["pins"] = sorted([s for s in steel if 0.020 < s.size.y < 0.038
                          and max(s.size.x, s.size.z) < 0.011 and s.lo.z > TURRET_TOP],
                         key=lambda s: s.mean.x)
    out["eyes"] = [s for s in parts if s.mat == ENAMEL_IDX
                   and abs(s.size.x - s.size.z) < 0.0015
                   and 0.010 < max(s.size.x, s.size.z) < 0.020 and s.size.y < 0.020]
    enamel = [s for s in parts if s.mat == ENAMEL_IDX and s.lo.z < ZMIN_EPS]
    out["base"] = sorted(enamel, key=lambda s: -s.size.x * s.size.y)[:1]
    return out


def pin_audit(cls):
    """Per pin: the XZ offset between its axis and the axis of every eye or
    boss it passes through, at that eye's own station; whether it spans each
    one in Y; its tilt off the lamp's normal."""
    worst, worst_tilt, matched, not_through = 0.0, 0.0, 0, 0
    counts = []
    for pin in cls["pins"]:
        c, axis = pca_axis(pin.pts)
        tilt = math.degrees(math.acos(min(1.0, abs(float(axis[1])))))
        worst_tilt = max(worst_tilt, tilt)
        n = 0
        for e in cls["eyes"]:
            if math.hypot(e.mean.x - c[0], e.mean.z - c[2]) > PIN_SEARCH:
                continue
            n += 1
            t = (e.mean.y - c[1]) / axis[1]
            px, pz = c[0] + axis[0] * t, c[2] + axis[2] * t
            worst = max(worst, math.hypot(e.mean.x - px, e.mean.z - pz))
            if e.lo.y < pin.lo.y - 1e-6 or e.hi.y > pin.hi.y + 1e-6:
                not_through += 1
        counts.append(n)
        matched += n
    return {"pins": len(cls["pins"]), "eyes": matched, "counts": counts,
            "offset": worst, "tilt": worst_tilt, "not_through": not_through}


def spring_audit(cls):
    """Per looped end: distance from its fitted centre to the nearest bar's
    axis, and whether it sits within that bar's length; per coil, the loops
    its wire runs into."""
    bars = []
    for b in cls["bars"]:
        c, axis = pca_axis(b.pts)
        bars.append((b, np.asarray(c), np.asarray(axis)))
    worst = 0.0
    off_bar = 0
    for h in cls["hooks"]:
        hc, _ax = pca_axis(h.pts)
        best, best_bar = 9.0, None
        for b, c, axis in bars:
            d = hc - c
            dist = float(np.linalg.norm(d - (d @ axis) * axis))
            if dist < best:
                best, best_bar = dist, b
        worst = max(worst, best)
        if best_bar is None or not (best_bar.lo.y <= hc[1] <= best_bar.hi.y):
            off_bar += 1
    ends = [sum(1 for h in cls["hooks"] if c.tree.overlap(h.tree)) for c in cls["coils"]]
    return {"coils": len(cls["coils"]), "hooks": len(cls["hooks"]), "bars": len(cls["bars"]),
            "seat": worst, "off_bar": off_bar, "ends": ends}


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
    """Mass centre against the base footprint, base width, and the two arm
    sections' pin-to-pin lengths, all read off the mesh."""
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
    if not cls["base"]:
        return None
    base = cls["base"][0]
    margin = min(base.hi.x - com.x, com.x - base.lo.x, base.hi.y - com.y, com.y - base.lo.y)
    pins = [pca_axis(p.pts)[0] for p in cls["pins"]]
    lens = []
    if len(pins) == PIN_COUNT:
        b2, b1, e2, e1, h2, h1 = pins[:6]

        def d(p, q):
            return math.hypot(p[0] - q[0], p[2] - q[2])

        lens = [d(e1, b1), d(e2, b2), d(h1, e1), d(h2, e2)]
    return {"mass": total, "com": com, "margin": margin, "width": (base.size.x, base.size.y),
            "lens": lens}


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
    img = bpy.data.images.new("LampNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = BAKELITE_IDX

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


def check(skip_decimate, lift_z=False, stray_vert=False, offset_pin=False,
          unhook_spring=False, hollow_base=False, unscrew_bulb=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(offset_pin=offset_pin, unhook_spring=unhook_spring,
                 hollow_base=hollow_base, unscrew_bulb=unscrew_bulb)
    low = build_lamp_mesh("LampLow", bevel_offset=0.0006, bevel_segments=1, **flags)
    high = build_lamp_mesh("LampHigh", bevel_offset=0.0006, bevel_segments=3, **flags)
    mats = lamp_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the bakelite: the plug body is where the high mesh's
    # rounder chamfer differs most from the low. Baked into the enamel, the
    # thin cheek plates' 1-px UV cells bled a bright arc onto the head knuckle.
    enamel = mats[BAKELITE_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        _co = [0.0] * (len(low.data.vertices) * 3)
        low.data.vertices.foreach_get("co", _co)
        _co[2::3] = [z + LIFT_Z for z in _co[2::3]]
        low.data.vertices.foreach_set("co", _co)
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("lamp mesh did not build", 3),) + none3

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
    pins = pin_audit(cls)
    springs = spring_audit(cls)
    stance = stance_audit(cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, enamel)
    if img is None:
        return (fail("lamp has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "LampLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "LampLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_lamp_mesh("LampColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "LampCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_desk_lamp_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} pins={pins['pins']} eyes={pins['eyes']} "
          f"per_pin={pins['counts']} pin_offset={pins['offset']:.6f} "
          f"pin_tilt_deg={pins['tilt']:.4f} not_through={pins['not_through']}")
    print(f"measured coils={springs['coils']} hooks={springs['hooks']} bars={springs['bars']} "
          f"spring_seat={springs['seat']:.6f} off_bar={springs['off_bar']} "
          f"coil_ends={springs['ends']}")
    if stance:
        print(f"measured mass={stance['mass']:.3f}kg com=({stance['com'].x:.4f},"
              f"{stance['com'].y:.4f},{stance['com'].z:.4f}) margin={stance['margin']:.4f} "
              f"base_width=({stance['width'][0]:.4f},{stance['width'][1]:.4f}) "
              f"arm_lens={[round(v, 4) for v in stance['lens']]}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    floors = ((ENAMEL_IDX, ENAMEL_FACES_MIN, "enamel"), (STEEL_IDX, STEEL_FACES_MIN, "steel"),
              (BULB_IDX, BULB_FACES_MIN, "bulb"), (RUBBER_IDX, RUBBER_FACES_MIN, "rubber"),
              (REFLECTOR_IDX, REFLECTOR_FACES_MIN, "reflector"),
              (BAKELITE_IDX, BAKELITE_FACES_MIN, "bakelite"))
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
    if (pins["pins"] != PIN_COUNT or pins["eyes"] != PIN_EYES or min(pins["counts"] or [0]) < 3
            or pins["offset"] > PIN_OFFSET_MAX or pins["tilt"] > PIN_TILT_MAX_DEG
            or pins["not_through"]):
        return (fail(f"joint pins: {pins['pins']} pins (want {PIN_COUNT}), {pins['eyes']} eyes "
                     f"(want {PIN_EYES}), worst axis offset {pins['offset']:.5f} > "
                     f"{PIN_OFFSET_MAX} or tilt {pins['tilt']:.3f} or "
                     f"{pins['not_through']} not through", 17),) + none3
    if (springs["coils"] != SPRING_COUNT or springs["hooks"] != HOOK_COUNT
            or springs["bars"] != BAR_COUNT or springs["seat"] > SPRING_SEAT_MAX
            or springs["off_bar"] or any(n != 2 for n in springs["ends"])):
        return (fail(f"spring seat: {springs}", 18),) + none3
    if (stance is None or stance["margin"] < STANCE_MARGIN
            or any(abs(w - 2.0 * BASE_HALF) > BASE_WIDTH_TOL for w in stance["width"])
            or len(stance["lens"]) != 4
            or any(abs(v - ARM1_LEN) > ARM_LEN_TOL for v in stance["lens"][:2])
            or any(abs(v - ARM2_LEN) > ARM_LEN_TOL for v in stance["lens"][2:])):
        return (fail(f"stance: mass centre margin {stance and stance['margin']} < "
                     f"{STANCE_MARGIN} or base/arm size off: {stance}", 19),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 20),) + none3
    return 0, low, enamel, tex


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, enamel, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(enamel, tex)
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

    # The house rig scaled to a 0.9 m prop: warm key upper left, cool fill
    # low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-1.3, -1.7, 1.5), 30.0, 0.9, (1.0, 0.95, 0.90), spread=18.0)
    light("Fill", (1.8, -1.2, 0.3), 5.0, 2.4, (0.72, 0.82, 1.0))
    light("Rim", (-0.5, 0.9, 0.8), 22.0, 0.7, (0.62, 0.78, 1.0))
    light("Wedge", (1.7, 2.1, 0.8), 40.0, 1.2, (1.0, 0.68, 0.38),
          target=(centre.x + 2.1, centre.y + WALL_Y, 0.35))



    # the lamp's own light, in front of the lamp inside the shade: it lights
    # the reflector's mouth and throws the pool on the desk
    st = arm_stations()
    bulb_local = v3(st["cb"]) + v3(st["a"]) * 0.142
    pl =bpy.data.lights.new("LampGlow", "POINT")
    pl.energy = 0.1

    pl.color = (1.0, 0.80, 0.55)
    try:
        pl.shadow_soft_size = 0.008
    except AttributeError:
        pass
    plo = bpy.data.objects.new("LampGlow", pl)
    plo.location = low.matrix_world @ bulb_local
    scene.collection.objects.link(plo)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.55, -0.77, 0.0)).normalized()
    cam.location = centre + view * 1.15 + Vector((0.0, 0.0, 0.13))


    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    # a touch right of and above the box centre: the shade is the heavy end
    aim.location = centre + Vector((0.030, -0.021, 0.012))

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
    # Standard, not AgX: AgX washes the enamel toward pastel
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
    p.add_argument("--offset-pin", action="store_true")
    p.add_argument("--unhook-spring", action="store_true")
    p.add_argument("--hollow-base", action="store_true")
    p.add_argument("--unscrew-bulb", action="store_true")
    args = p.parse_args(argv)

    code, low, enamel, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        offset_pin=args.offset_pin,
        unhook_spring=args.unhook_spring,
        hollow_base=args.hollow_base,
        unscrew_bulb=args.unscrew_bulb,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, enamel, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("desk-lamp OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
