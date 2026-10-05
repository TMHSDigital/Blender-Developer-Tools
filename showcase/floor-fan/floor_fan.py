"""Game-ready vintage oscillating pedestal fan — a showcase piece, not an example.

Asserts budget conformance of a procedural 1950s-style floor fan after
composing shipped pipeline pieces: bmesh construction, UVs, six materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

A round cast base in two tiers, hollow underneath and standing on a rubber
gasket, carries a rotary speed switch on its sloped top and a maker's badge
on its riser. A telescoping column rises from a ferrule in the base's boss:
an enamelled lower tube, a knurled height-lock collar with a thumb screw,
and a chrome upper tube into a neck fitting. A strap yoke on the neck holds
the head on a tilt pivot, with a knurled tilt knob on one side and a cap nut
on the other. The head is a motor housing with a chrome trim band, a ring
of cooling slots and a gearbox carrying the oscillation knob, and a wire
guard in two halves: radial spokes and concentric rings, each half welded
to its own rim ring, the two rims clipped together, a badge at the front
centre. Inside, four broad swept brass blades on a hub with a spinner nut.
A cord leaves a grommet in the base's riser and ends in a plug on the floor.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--offset-hub`` the rotor coaxial
with the guard, ``--short-spoke`` guard wires seated on their rim rings,
``--lean-column`` the column plumb and coaxial with the base,
``--long-blades`` the blade-tip clearance band, ``--skew-blade`` equal blade
spacing, ``--hollow-base`` the tip-over angle, ``--loose-spinner`` one
connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python floor_fan.py --
    blender --background --python floor_fan.py -- --skip-decimate
    blender --background --python floor_fan.py -- --output fan.png
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

# --- Base: a hollow cast shell of two tiers, on a rubber gasket ------------
BASE_SEGS = 80
# outer (r, z) from the bottom edge up and in to the column hole
BASE_OUTER = [
    (0.1935, 0.0040), (0.1985, 0.0062), (0.2000, 0.0100), (0.2000, 0.0280),
    (0.1985, 0.0322), (0.1950, 0.0345), (0.1625, 0.0368), (0.1590, 0.0392),
    (0.1565, 0.0450), (0.1500, 0.0540), (0.1350, 0.0640), (0.1150, 0.0730),
    (0.0900, 0.0810), (0.0650, 0.0880), (0.0485, 0.0950), (0.0425, 0.1010),
    (0.0405, 0.1120), (0.0385, 0.1172), (0.0350, 0.1200), (0.0225, 0.1210),
]
# a smoothed copy of the outer line, offset inward by the wall for the inside
BASE_INNER_GUIDE = [
    (0.1935, 0.0040), (0.2000, 0.0110), (0.2000, 0.0280), (0.1625, 0.0370),
    (0.1500, 0.0540), (0.1150, 0.0730), (0.0650, 0.0880), (0.0425, 0.1010),
    (0.0405, 0.1120), (0.0225, 0.1210),
]
BASE_WALL = 0.009           # cast iron
HOLLOW_WALL = 0.0012        # --hollow-base: pressed from thin sheet
HOLE_R = 0.0225
GASKET = [(0.1860, 0.0), (0.1968, 0.0), (0.1975, 0.0012), (0.1975, 0.0050),
          (0.1860, 0.0050)]
SWITCH_RHO = 0.1245         # speed switch on the sloped top, at the front
BADGE_Z = 0.0190

# --- Column ----------------------------------------------------------------
TUBE_R = 0.0240             # lower tube, enamel
TUBE_Z = (0.035, 0.640)
UTUBE_R = 0.0165            # upper tube, chrome
UTUBE_Z = (0.560, 0.818)
COLLAR_Z = (0.612, 0.662)
COLLAR_R = 0.0310
GRIP = 0.0008               # a hooped ring's inner face inside its host
LEAN_DEG = 1.0              # --lean-column

# --- Head frame --------------------------------------------------------------
# Head-local: x right, y forward (the blowing direction), z up; origin at
# the centre of the guard's rim plane. The head turns OSC_DEG on the
# column (it is oscillating) and tilts TILT_DEG up about the pivot.
PIVOT_Z = 0.985
PIVOT_BACK = 0.155          # pivot axis behind the rim plane
OSC_DEG = 28.0
TILT_DEG = 7.0

# --- Guard -------------------------------------------------------------------
RIM_F = (0.2225, 0.0036, 0.0032)   # (major, minor, y) front rim ring
RIM_R = (0.2215, 0.0033, -0.0030)  # rear rim ring: the pair overlap 0.7 mm
RIM_SEGS = 128
DOME_F = (0.066, 2.6)       # front dome height and exponent
DOME_R = (0.095, 3.0)       # rear dome depth and exponent
SPOKES_F = 24
SPOKES_R = 24
SPOKE_R = 0.0015
SPOKE_PTS = 14
SPOKE_START_F = 0.030       # inside the badge bezel
SPOKE_START_R = 0.058       # inside the rear mount ring
RINGS_F = (0.068, 0.110, 0.150, 0.188)
RINGS_R = (0.095, 0.140, 0.182)
RING_WIRE = 0.0019
RING_SEGS = 80
CLIPS = 6
SHORT_SPOKE = 0.012         # --short-spoke: one spoke stops this far short

# --- Rotor -------------------------------------------------------------------
BLADES = 4
Y_BLADE = -0.010
HUB_R = 0.044
SPINNER_R = 0.026
# (r, chord, pitch deg): a narrow neck in the hub, a broad paddle, a rounded tip
BLADE_STATIONS = [
    (0.030, 0.034, 30.0), (0.042, 0.036, 30.0), (0.055, 0.050, 29.0),
    (0.070, 0.072, 27.0), (0.090, 0.095, 25.0), (0.110, 0.112, 23.5),
    (0.130, 0.122, 22.0), (0.150, 0.125, 21.0), (0.165, 0.118, 20.0),
    (0.177, 0.104, 19.5), (0.186, 0.086, 19.0), (0.192, 0.066, 18.5),
    (0.196, 0.046, 18.0), (0.199, 0.024, 18.0),
]
AIRFOIL_X = (1.0, 0.80, 0.55, 0.30, 0.10, 0.0, 0.10, 0.30, 0.55, 0.80)
BLADE_T = 0.0024
BLADE_CAMBER = 0.05
BLADE_SWEEP = 0.032         # leading edge carried forward toward the tip
OFFSET_HUB = 0.003          # --offset-hub
LONG_BLADES = 0.012         # --long-blades
SKEW_DEG = 5.0              # --skew-blade
LOOSE_SPINNER = 0.006       # --loose-spinner

# --- Motor -------------------------------------------------------------------
MOTOR = [
    (0.030, -0.0840), (0.054, -0.0880), (0.066, -0.0980), (0.078, -0.1100),
    (0.088, -0.1220), (0.0935, -0.1340), (0.0940, -0.1450), (0.0940, -0.2000),
    (0.0940, -0.2050), (0.0940, -0.2400), (0.0940, -0.2450), (0.0915, -0.2600),
    (0.0850, -0.2760), (0.0740, -0.2910), (0.0580, -0.3030), (0.0380, -0.3110),
    (0.0180, -0.3150),
]
SLOT_ROWS = (8, 9)
MOTOR_SEGS = 64

# --- Cord and plug ------------------------------------------------------------
CORD_R = 0.0034
CORD_PTS = [(0.0, -0.186, 0.019), (0.0, -0.214, 0.019), (0.006, -0.238, 0.011),
            (0.030, -0.262, CORD_R), (0.120, -0.300, CORD_R), (0.260, -0.290, CORD_R),
            (0.400, -0.200, CORD_R), (0.470, -0.050, CORD_R), (0.480, 0.110, CORD_R),
            (0.440, 0.240, CORD_R), (0.405, 0.330, 0.0110)]
PLUG_SIZE = (0.046, 0.032, 0.024)
PRONG_STAGGER = 0.0005

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.761, 0.704, 1.230)
BASE_TRIS_MIN = 40600
BASE_TRIS_MAX = 41900
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 6
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 2200
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
ENAMEL_FACES_MIN = 4350
CHROME_FACES_MIN = 12800
BRASS_FACES_MIN = 540
RUBBER_FACES_MIN = 1120
BAKELITE_FACES_MIN = 740
BADGE_FACES_MIN = 400

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Rotor coaxial with the guard: every turned part of the head on the axis
# the rim rings define.
AXIS_TOL = 0.0005
AXIS_TILT_MAX_DEG = 0.2
# Guard wires: every spoke's outer end inside its rim ring's tube.
SEAT_MAX = 0.0026
# Column: plumb, and on the base's axis where it enters the boss.
PLUMB_MAX_DEG = 0.2
COAX_MAX = 0.001
GUARD_DIA = 0.452
BASE_DIA = 0.400
SIZE_TOL = 0.004
# Blades: radial tip clearance to the rim rings' inner face, and the
# nearest approach of any blade vertex to any guard wire.
TIP_CLEAR = (0.012, 0.030)
WIRE_CLEAR_MIN = 0.006
SPACING_TOL_DEG = 0.3
# Stance: a floor fan must not tip on a named incline.
DENSITY = (7850.0, 7850.0, 8500.0, 1200.0, 1400.0, 2500.0)
MOTOR_DENSITY = 700.0       # a pressed housing round windings and air
TUBE_DENSITY = 1100.0       # the column tubes are drawn tube, not bar
TIP_MIN_DEG = 16.0

HERO_YAW_DEG = 164.0
WALL_Y = 3.0

ENAMEL_IDX = 0
CHROME_IDX = 1
BRASS_IDX = 2
RUBBER_IDX = 3
BAKELITE_IDX = 4
BADGE_IDX = 5

Y_UP = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)))    # local Z -> +Y
X_UP = Matrix(((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)))    # local Z -> +X
X_DOWN = Matrix(((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)))  # local Z -> -X
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
# Frames
# --------------------------------------------------------------------------

C_ROT = Matrix.Rotation(math.radians(OSC_DEG), 3, "Z")                 # column frame
H_ROT = C_ROT @ Matrix.Rotation(math.radians(TILT_DEG), 3, "X")         # head frame
PIVOT_W = Vector((0.0, 0.0, PIVOT_Z))
PIVOT_L = Vector((0.0, -PIVOT_BACK, 0.0))
FWD = H_ROT @ Vector((0.0, 1.0, 0.0))
H_AXIS = H_ROT @ Y_UP       # lathe local Z -> head forward


def hw(p):
    """Head-local point to world."""
    return PIVOT_W + H_ROT @ (Vector(p) - PIVOT_L)


def cw(p):
    """Column-frame point (turned with the head, not tilted) to world."""
    return C_ROT @ Vector(p)


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

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


def add_tube(bm, pts, radius, sides, mat_idx, phase=0.0, side=None, flat=1.0):
    """Capped bar swept along a polyline (parallel-transport frames). With
    ``side`` the section's first axis is held on that vector instead, and
    ``flat`` scales the section across it (a strap)."""
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
        if side is not None:
            nrm = (Vector(side) - t * Vector(side).dot(t)).normalized()
        else:
            nrm = (nrm - t * nrm.dot(t)).normalized()
        bi = t.cross(nrm)
        rings.append([
            bm.verts.new(p + radius * (nrm * math.cos(phase + 2.0 * math.pi * k / sides)
                                       + bi * flat * math.sin(phase + 2.0 * math.pi * k / sides)))
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


def add_ring(bm, center, axis, r_major, r_minor, segs, sides, mat_idx, phase=0.0,
             tube_phase=0.0, u=None, ra=None, rb=None):
    """Closed torus about ``axis`` through ``center``. With ``u`` the
    centreline is an ellipse of radii ``ra`` (along u) and ``rb``."""
    center = Vector(center)
    axis = Vector(axis).normalized()
    if u is None:
        ref = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.9 else Vector((1.0, 0.0, 0.0))
        u = axis.cross(ref).normalized()
    else:
        u = (Vector(u) - axis * Vector(u).dot(axis)).normalized()
    w = axis.cross(u)
    ra = r_major if ra is None else ra
    rb = r_major if rb is None else rb
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        c = center + u * (ra * math.cos(a)) + w * (rb * math.sin(a))
        tangent = (-u * ra * math.sin(a) + w * rb * math.cos(a)).normalized()
        radial = tangent.cross(axis).normalized()
        rings.append([
            bm.verts.new(c + r_minor * (radial * math.cos(tube_phase + 2.0 * math.pi * k / sides)
                                        + axis * math.sin(tube_phase + 2.0 * math.pi * k / sides)))
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
# The fan
# --------------------------------------------------------------------------

def dome_f(rho):
    h, p = DOME_F
    return RIM_F[2] + h * (1.0 - (rho / RIM_F[0]) ** p)


def dome_r(rho):
    h, p = DOME_R
    return RIM_R[2] - h * (1.0 - (rho / RIM_R[0]) ** p)


def spoke_path(a, r0, r1, dome, ring_y, short=0.0):
    """A guard wire from r0 on the dome out to r1, ending on the rim ring's
    centreline; ``short`` stops it that far inside the ring."""
    d = (math.cos(a), 0.0, math.sin(a))
    pts = []
    for i in range(SPOKE_PTS):
        s = 1.0 - (1.0 - i / (SPOKE_PTS - 1)) ** 1.35
        rho = r0 + (r1 - short - r0) * s
        y = ring_y if (i == SPOKE_PTS - 1 and not short) else dome(rho)
        pts.append(hw((rho * d[0], y, rho * d[2])))
    return pts


def add_base(bm, wall):
    guide = offset_polyline(BASE_INNER_GUIDE, wall, -1.0)
    guide[0] = (guide[0][0], BASE_OUTER[0][1])
    guide[-1] = (HOLE_R, guide[-1][1])
    profile = BASE_OUTER + list(reversed(guide))
    add_lathe(bm, profile, BASE_SEGS, ENAMEL_IDX)


def add_blade(bm, a, spin, tip_extra, center):
    """One lofted blade, every section wrapped onto its own cylinder about
    the rotor axis: pitched, cambered, swept forward toward a rounded tip."""
    e_r = Vector((math.cos(a), 0.0, math.sin(a)))
    e_t = Vector((0.0, 1.0, 0.0)).cross(e_r) * spin
    r_first, r_last = BLADE_STATIONS[0][0], BLADE_STATIONS[-1][0]
    secs = []
    for r, chord, beta_deg in BLADE_STATIONS:
        if tip_extra and r > 0.10:
            r = r + tip_extra * (r - 0.10) / (r_last - 0.10)
        beta = math.radians(beta_deg)
        sweep = BLADE_SWEEP * ((r - r_first) / (r_last - r_first)) ** 2
        ring = []
        for k, xc in enumerate(AIRFOIL_X):
            upper = k < 5
            camber = BLADE_CAMBER * chord * 4.0 * xc * (1.0 - xc)
            yt = 0.5 * BLADE_T * (4.0 * xc * (1.0 - xc)) ** 0.35
            yy = camber + (yt if upper else -yt)
            s = (xc - 0.42) * chord - sweep
            t_off = -math.cos(beta) * s - math.sin(beta) * yy
            z_off = -math.sin(beta) * s + math.cos(beta) * yy
            ang = t_off / r
            p = center + Vector((0.0, Y_BLADE + z_off, 0.0)) \
                + r * (e_r * math.cos(ang) + e_t * math.sin(ang))
            ring.append(bm.verts.new(hw(p)))
        secs.append(ring)
    n = len(AIRFOIL_X)
    faces = []
    for r0, r1 in zip(secs, secs[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(secs[0]))))
    faces.append(bm.faces.new(tuple(secs[-1])))
    _mark(faces, BRASS_IDX)


def build_fan_mesh(name, bevel_offset, bevel_segments, offset_hub=False, short_spoke=False,
                   lean_column=False, long_blades=False, skew_blade=False,
                   hollow_base=False, loose_spinner=False):
    bm = bmesh.new()
    try:
        bevel_verts = []

        # ---- base, gasket, trim ring, speed switch, badge
        add_base(bm, HOLLOW_WALL if hollow_base else BASE_WALL)
        add_lathe(bm, GASKET, BASE_SEGS, RUBBER_IDX, phase=math.pi / BASE_SEGS)
        # a chrome bead run round the tread step, hooped into the riser's shoulder
        add_ring(bm, (0.0, 0.0, 0.0372), ZAX, 0.1612, 0.0026, BASE_SEGS, 6, CHROME_IDX,
                 phase=math.pi / BASE_SEGS)
        # switch: escutcheon, knob with a pointer lobe, three detent studs
        dz = (BASE_OUTER[11][1] - BASE_OUTER[10][1])
        dr = (BASE_OUTER[11][0] - BASE_OUTER[10][0])
        t = (SWITCH_RHO - BASE_OUTER[10][0]) / dr
        sz = BASE_OUTER[10][1] + dz * t
        # the slope's outward normal in (radial, z), carried to the +Y azimuth
        nrm = Vector((0.0, dz, -dr)).normalized()
        sw = Vector((0.0, SWITCH_RHO, sz))
        srot = Matrix((Vector((1.0, 0.0, 0.0)), nrm.cross(Vector((1.0, 0.0, 0.0))), nrm)).transposed()
        add_lathe(bm, [(0.0240, -0.0030), (0.0250, 0.0010), (0.0236, 0.0026), (0.0180, 0.0030)],
                  40, CHROME_IDX, center=sw, rot=srot, solid=True)

        def pointer(i, j):
            if j in (1, 2, 3):
                if i == 0:
                    return 1.30
                return 0.93 if i % 2 else 1.0
            return 1.0

        add_lathe(bm, [(0.0150, 0.0020), (0.0160, 0.0050), (0.0160, 0.0150), (0.0140, 0.0185),
                       (0.0080, 0.0205), (0.0030, 0.0210)], 32, BAKELITE_IDX, center=sw,
                  rot=srot, solid=True, rmod=pointer, phase=math.pi / 2.0)
        for k in range(3):
            a = math.radians(150.0 + 45.0 * k)
            loc = sw + srot @ Vector((0.0205 * math.cos(a), 0.0205 * math.sin(a), 0.0))
            # each stud a touch prouder and turned, or their facets share planes
            st = 0.0003 * k
            add_lathe(bm, [(0.0017, 0.0015 - st), (0.0017, 0.0038 + st), (0.0008, 0.0046 + st)], 10,
                      CHROME_IDX, center=loc, rot=srot, solid=True, phase=0.21 * k)
        # maker's badge on the riser, an oval plaque with a bezel
        brot = Y_UP
        bc = Vector((0.0, BASE_OUTER[3][0] - 0.0006, BADGE_Z))
        plaque = add_lathe(bm, [(0.0105, -0.0022), (0.0105, 0.0006), (0.0096, 0.0014),
                                (0.0080, 0.0017)], 32, BADGE_IDX, center=bc, rot=brot, solid=True)
        bezel = add_lathe(bm, [(0.0101, -0.0024), (0.0122, -0.0024), (0.0124, 0.0009),
                               (0.0114, 0.0016), (0.0101, 0.0010)], 32, CHROME_IDX,
                          center=bc, rot=brot, phase=math.pi / 32.0)
        for v in plaque + bezel:
            v.co.x *= 2.1
            v.co.z = BADGE_Z + (v.co.z - BADGE_Z) * 0.62

        # ---- column: ferrule, lower tube, collar with thumb screw, upper tube, neck
        add_lathe(bm, [(TUBE_R - GRIP, 0.112), (0.0280, 0.112), (0.0296, 0.1150),
                       (0.0296, 0.1340), (0.0280, 0.1370), (TUBE_R - GRIP, 0.1370)],
                  48, CHROME_IDX)
        lean = Matrix.Rotation(math.radians(LEAN_DEG), 3, "X") if lean_column else None
        z0, z1 = TUBE_Z
        add_lathe(bm, [(0.020, 0.0), (TUBE_R, 0.004), (TUBE_R, z1 - z0 - 0.004),
                       (0.0205, z1 - z0)], 48, ENAMEL_IDX, center=(0.0, 0.0, z0), rot=lean,
                  solid=True)

        def knurl(i, j):
            return 0.965 if (j in (2, 3) and i % 2) else 1.0

        c0, c1 = COLLAR_Z
        add_lathe(bm, [(TUBE_R - GRIP, c0), (COLLAR_R - 0.002, c0), (COLLAR_R, c0 + 0.003),
                       (COLLAR_R, c1 - 0.003), (COLLAR_R - 0.002, c1), (TUBE_R - GRIP, c1)],
                  56, CHROME_IDX, rmod=knurl)
        ta = math.radians(-150.0)
        tdir = Vector((math.cos(ta), math.sin(ta), 0.0))
        trot = Matrix((ZAX.cross(tdir), ZAX, tdir)).transposed()
        tc = Vector((0.0, 0.0, 0.5 * (c0 + c1)))
        add_lathe(bm, [(0.0036, COLLAR_R - 0.004), (0.0036, 0.047)], 12, CHROME_IDX,
                  center=tc, rot=trot, solid=True)
        wing = add_lathe(bm, [(0.0060, 0.0440), (0.0105, 0.0455), (0.0110, 0.0500),
                              (0.0105, 0.0575), (0.0070, 0.0590)], 20, BAKELITE_IDX,
                         center=tc, rot=trot, solid=True)
        for v in wing:
            loc = v.co - tc
            along = loc.dot(tdir)
            lat = loc - tdir * along
            v.co = tc + tdir * along + lat.dot(ZAX) * ZAX * 1.35 + (lat - lat.dot(ZAX) * ZAX) * 0.55
        u0, u1 = UTUBE_Z
        add_lathe(bm, [(0.0130, u0), (UTUBE_R, u0 + 0.003), (UTUBE_R, u1 - 0.003),
                       (0.0150, u1)], 40, CHROME_IDX, solid=True, phase=math.pi / 40.0)
        yoke_z = PIVOT_Z - 0.126
        add_lathe(bm, [(0.0120, 0.800), (0.0190, 0.804), (0.0190, 0.826), (0.0245, 0.836),
                       (0.0300, 0.846), (0.0300, yoke_z - 0.003), (0.0270, yoke_z + 0.0005)],
                  40, CHROME_IDX, solid=True)

        # ---- yoke: a strap bent into a U under the head, eyes on the pivot
        half_w = 0.113
        r_c = 0.030
        path = [(-half_w, 0.0, PIVOT_Z), (-half_w, 0.0, yoke_z + r_c + 0.03)]
        for k in range(1, 6):
            th = math.pi + 0.5 * math.pi * k / 6.0
            path.append((-half_w + r_c + r_c * math.cos(th), 0.0, yoke_z + r_c + r_c * math.sin(th)))
        path += [(-half_w + r_c, 0.0, yoke_z), (half_w - r_c, 0.0, yoke_z)]
        for k in range(1, 6):
            th = 1.5 * math.pi + 0.5 * math.pi * k / 6.0
            path.append((half_w - r_c + r_c * math.cos(th), 0.0, yoke_z + r_c + r_c * math.sin(th)))
        path += [(half_w, 0.0, yoke_z + r_c + 0.03), (half_w, 0.0, PIVOT_Z)]
        add_tube(bm, [cw(p) for p in path], 0.0130, 12, ENAMEL_IDX,
                 side=C_ROT @ Vector((0.0, 1.0, 0.0)), flat=0.36)
        for s in (-1.0, 1.0):
            add_lathe(bm, [(0.0200, -0.0046), (0.0212, -0.0034), (0.0212, 0.0034),
                           (0.0200, 0.0046)], 32, ENAMEL_IDX,
                      center=cw((s * half_w, 0.0, PIVOT_Z)), rot=C_ROT @ X_UP, solid=True,
                      phase=math.pi / 32.0 if s > 0 else 0.0)
        # pivot bolt, tilt knob (+x) and cap nut (-x)
        add_lathe(bm, [(0.0050, -0.1240), (0.0060, -0.1230), (0.0060, 0.1190), (0.0050, 0.1200)],
                  16, CHROME_IDX, center=PIVOT_W, rot=C_ROT @ X_UP, solid=True)

        def ribs(i, j):
            return 0.93 if (j in (2, 3) and i % 2) else 1.0

        add_lathe(bm, [(0.0120, 0.1165), (0.0200, 0.1175), (0.0225, 0.1215), (0.0225, 0.1355),
                       (0.0200, 0.1400), (0.0130, 0.1440), (0.0060, 0.1455)], 36, BAKELITE_IDX,
                  center=PIVOT_W, rot=C_ROT @ X_UP, solid=True, rmod=ribs)
        add_lathe(bm, [(0.0110, 0.1165), (0.0125, 0.1175), (0.0125, 0.1235), (0.0095, 0.1285),
                       (0.0040, 0.1305)], 6, CHROME_IDX, center=PIVOT_W, rot=C_ROT @ X_DOWN,
                  solid=True)

        # ---- motor housing: slots, trim band, pivot bosses, gearbox and knob
        def slots(i, j):
            return 0.955 if (j in SLOT_ROWS and (i % 4) in (1, 2)) else 1.0

        add_lathe(bm, MOTOR, MOTOR_SEGS, ENAMEL_IDX, center=hw((0.0, 0.0, 0.0)), rot=H_AXIS,
                  solid=True, rmod=slots)
        add_lathe(bm, [(0.0940 - GRIP, -0.1985), (0.0962, -0.1985), (0.0975, -0.1970),
                       (0.0975, -0.1885), (0.0962, -0.1870), (0.0940 - GRIP, -0.1870)],
                  MOTOR_SEGS, CHROME_IDX, center=hw((0.0, 0.0, 0.0)), rot=H_AXIS,
                  phase=math.pi / MOTOR_SEGS)
        for s in (-1.0, 1.0):
            add_lathe(bm, [(0.0240, 0.0800), (0.0240, 0.1048), (0.0200, 0.1088)], 32, ENAMEL_IDX,
                      center=hw(PIVOT_L), rot=H_ROT @ (X_UP if s > 0 else X_DOWN), solid=True,
                      phase=math.pi / 32.0)
        gb = hw((0.0, -0.268, 0.078))
        add_lathe(bm, [(0.0300, -0.0060), (0.0320, 0.0060), (0.0300, 0.0170), (0.0230, 0.0250),
                       (0.0120, 0.0290)], 32, ENAMEL_IDX, center=gb, rot=H_ROT, solid=True)
        add_lathe(bm, [(0.0040, 0.0240), (0.0040, 0.0600)], 12, CHROME_IDX, center=gb,
                  rot=H_ROT, solid=True)
        add_lathe(bm, [(0.0060, 0.0550), (0.0120, 0.0560), (0.0135, 0.0590), (0.0135, 0.0680),
                       (0.0110, 0.0720), (0.0050, 0.0740)], 24, BAKELITE_IDX, center=gb,
                  rot=H_ROT, solid=True, rmod=ribs)

        # ---- rotor: shaft, hub, spinner nut, four blades
        add_lathe(bm, [(0.0065, -0.0900), (0.0065, Y_BLADE - 0.018)], 16, CHROME_IDX,
                  center=hw((0.0, 0.0, 0.0)), rot=H_AXIS, solid=True)
        rotor = Vector((OFFSET_HUB, 0.0, 0.0)) if offset_hub else Vector()
        yb = Y_BLADE
        add_lathe(bm, [(0.0200, yb - 0.024), (0.0400, yb - 0.0225), (HUB_R, yb - 0.0185),
                       (HUB_R, yb + 0.0120), (0.0405, yb + 0.0165), (0.0300, yb + 0.0180)],
                  48, CHROME_IDX, center=hw(rotor), rot=H_AXIS, solid=True)

        def hexnut(i, j):
            if j in (0, 1, 2):
                a = 2.0 * math.pi * i / 36
                return 1.0 / math.cos(((a + math.pi / 6.0) % (math.pi / 3.0)) - math.pi / 6.0) * 0.92
            return 1.0

        spin_y = rotor + Vector((0.0, LOOSE_SPINNER if loose_spinner else 0.0, 0.0))
        add_lathe(bm, [(0.0180, yb + 0.0150), (SPINNER_R - 0.0015, yb + 0.0160),
                       (SPINNER_R - 0.0015, yb + 0.0250), (0.0215, yb + 0.0300),
                       (0.0200, yb + 0.0360), (0.0150, yb + 0.0430), (0.0080, yb + 0.0475),
                       (0.0020, yb + 0.0490)], 36, CHROME_IDX, center=hw(spin_y), rot=H_AXIS,
                  solid=True, rmod=hexnut)
        for b in range(BLADES):
            a = math.radians(20.0) + 2.0 * math.pi * b / BLADES
            if skew_blade and b == 0:
                a += math.radians(SKEW_DEG)
            add_blade(bm, a, 1.0, LONG_BLADES if long_blades else 0.0, rotor)

        # ---- guard: rim rings, clips, badge, rear mount, rings, spokes
        for (maj, mnr, y), tp in ((RIM_F, 0.0), (RIM_R, math.pi / 8.0)):
            add_ring(bm, hw((0.0, y, 0.0)), FWD, maj, mnr, RIM_SEGS, 8, CHROME_IDX,
                     phase=math.pi / RIM_SEGS, tube_phase=tp)
        r_mid = 0.5 * (RIM_F[0] + RIM_R[0])
        for k in range(CLIPS):
            a = math.radians(60.0 * k + 3.75)
            radial = H_ROT @ Vector((math.cos(a), 0.0, math.sin(a)))
            tang = H_ROT @ Vector((-math.sin(a), 0.0, math.cos(a)))
            add_ring(bm, hw((r_mid * math.cos(a), 0.5 * (RIM_F[2] + RIM_R[2]), r_mid * math.sin(a))),
                     tang, 0.0, 0.0012, 16, 5, CHROME_IDX, u=radial, ra=0.0049, rb=0.0077)
        yb0 = dome_f(SPOKE_START_F)
        add_lathe(bm, [(0.0300, yb0 - 0.0050), (0.0350, yb0 - 0.0040), (0.0362, yb0 + 0.0010),
                       (0.0342, yb0 + 0.0055), (0.0300, yb0 + 0.0065)], 48, CHROME_IDX,
                  center=hw((0.0, 0.0, 0.0)), rot=H_AXIS, solid=True)

        def rays(i, j):
            return 0.97 if (j in (2,) and i % 3 == 0) else 1.0

        add_lathe(bm, [(0.0292, yb0 + 0.0055), (0.0292, yb0 + 0.0082), (0.0250, yb0 + 0.0102),
                       (0.0150, yb0 + 0.0116), (0.0050, yb0 + 0.0121)], 48, BADGE_IDX,
                  center=hw((0.0, 0.0, 0.0)), rot=H_AXIS, solid=True, rmod=rays,
                  phase=math.pi / 48.0)
        yr0 = dome_r(SPOKE_START_R)
        add_lathe(bm, [(0.0500, yr0 - 0.0070), (0.0640, yr0 - 0.0070), (0.0660, yr0 - 0.0045),
                       (0.0660, yr0 + 0.0045), (0.0640, yr0 + 0.0070), (0.0500, yr0 + 0.0070)],
                  48, CHROME_IDX, center=hw((0.0, 0.0, 0.0)), rot=H_AXIS)
        for i, rho in enumerate(RINGS_F):
            add_ring(bm, hw((0.0, dome_f(rho), 0.0)), FWD, rho, RING_WIRE, RING_SEGS, 6,
                     CHROME_IDX, phase=math.pi * (i % 2) / RING_SEGS, tube_phase=math.pi / 6.0)
        for i, rho in enumerate(RINGS_R):
            add_ring(bm, hw((0.0, dome_r(rho), 0.0)), FWD, rho, RING_WIRE, RING_SEGS, 6,
                     CHROME_IDX, phase=math.pi * (i % 2) / RING_SEGS)
        for k in range(SPOKES_F):
            a = 2.0 * math.pi * k / SPOKES_F
            sh = SHORT_SPOKE if (short_spoke and k == 3) else 0.0
            # every wire's facets turned its own amount, so no two share a plane
            add_tube(bm, spoke_path(a, SPOKE_START_F, RIM_F[0], dome_f, RIM_F[2], sh),
                     SPOKE_R, 6, CHROME_IDX, phase=(0.618 * k) % (math.pi / 3.0))
        for k in range(SPOKES_R):
            a = 2.0 * math.pi * (k + 0.5) / SPOKES_R
            add_tube(bm, spoke_path(a, SPOKE_START_R, RIM_R[0], dome_r, RIM_R[2]),
                     SPOKE_R, 6, CHROME_IDX, phase=(0.618 * k + 0.31) % (math.pi / 3.0))

        # ---- cord: grommet in the rear riser, over the floor, to a plug
        add_lathe(bm, [(CORD_R - 0.0002, -0.0030), (0.0062, -0.0030), (0.0068, 0.0010),
                       (0.0058, 0.0040), (CORD_R - 0.0002, 0.0040)], 20, RUBBER_IDX,
                  center=(0.0, -BASE_OUTER[3][0], CORD_PTS[0][2]),
                  rot=Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))))
        cpts = catmull(CORD_PTS, per=6)
        for p in cpts:
            p.z = max(p.z, CORD_R + 0.0002)
        add_tube(bm, cpts, CORD_R, 10, RUBBER_IDX)
        end = cpts[-1]
        dirn = (cpts[-1] - cpts[-3])
        dirn.z = 0.0
        dirn.normalize()
        yaw = math.atan2(dirn.y, dirn.x)
        rz = Matrix.Rotation(yaw, 3, "Z")
        srot2 = rz @ Matrix(((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)))
        add_lathe(bm, [(CORD_R - 0.0002, -0.0110), (0.0048, -0.0065), (0.0072, 0.0000),
                       (0.0072, 0.0055), (CORD_R - 0.0002, 0.0055)], 20, RUBBER_IDX,
                  center=end, rot=srot2)
        lx, ly, lz = PLUG_SIZE
        pc = end + dirn * (0.0045 + lx / 2.0)
        pc.z = lz / 2.0
        body = add_box(bm, (0.0, 0.0, 0.0), (lx, ly, lz), BAKELITE_IDX)
        for v in body:
            v.co = pc + rz @ v.co
        bevel_verts += body
        for side in (-1.0, 1.0):
            st_ = PRONG_STAGGER if side > 0 else 0.0
            q0 = pc + rz @ Vector((lx / 2.0 - 0.004 - st_, side * 0.0080, 0.0))
            q1 = pc + rz @ Vector((lx / 2.0 + 0.018 + st_, side * 0.0080, 0.0))
            add_tube(bm, [q0, q1], 0.0024, 8, CHROME_IDX,
                     phase=math.pi / 8.0 if side > 0 else 0.0)

        if bevel_offset > 0.0:
            bm.edges.index_update()
            edges = sorted(
                {e for v in bevel_verts if v.is_valid for e in v.link_edges
                 if len(e.link_faces) == 2
                 and all(f.material_index == BAKELITE_IDX for f in e.link_faces)
                 and e.calc_face_angle() > math.radians(60.0)},
                key=lambda e: e.index,
            )
            if edges:
                bmesh.ops.bevel(bm, geom=edges, offset=bevel_offset, segments=bevel_segments,
                                profile=0.5, affect="EDGES", clamp_overlap=True,
                                material=BAKELITE_IDX)

            # the chamfer pass leaves the plug's sole below the floor: set the
            # plug, its prongs and strain relief back down on it
            near = [v for v in bm.verts if (v.co - pc).length < 0.06]
            sole = min(v.co.z for v in near if any(f.material_index == BAKELITE_IDX
                                                   for f in v.link_faces))
            for v in near:
                v.co.z -= sole

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
        # Turned and swept stock is smooth-shaded; chamfers, knurls and
        # treads stay crisp. Thin wire (6-sided) smooths across its facets.
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                lim = 62.0 if mats <= {CHROME_IDX, BRASS_IDX} else 35.0
                edge.smooth = edge.calc_face_angle() < math.radians(lim)
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
            lo = max(0.04, roughness - roughness_var)
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


def fan_materials():
    """(enamel, chrome, brass, rubber, bakelite, badge): shared by the check
    and the render.

    The castings, tubes and housing are a muted sage stove enamel under a
    clear coat; the guard, trim and fittings bright chrome plate, rough
    enough to catch the key rather than mirror a black stage; the blades
    polished brass; cord, grommet and gasket black rubber; the knobs and
    plug brown bakelite; the badges cream vitreous enamel.
    """
    enamel = principled("FanEnamel", (0.155, 0.215, 0.180, 1.0), 0.0, 0.30,
                        roughness_var=0.08, mottle=0.08, noise_scale=36.0, coat=0.45)
    chrome = principled("FanChrome", (0.88, 0.88, 0.90, 1.0), 1.0, 0.27,
                        roughness_var=0.06, noise_scale=70.0)
    brass = principled("FanBrass", (0.76, 0.58, 0.34, 1.0), 1.0, 0.36,
                       roughness_var=0.08, mottle=0.10, noise_scale=45.0)
    rubber = principled("FanRubber", (0.018, 0.018, 0.020, 1.0), 0.0, 0.62,
                        roughness_var=0.08, noise_scale=80.0)
    bakelite = principled("FanBakelite", (0.060, 0.030, 0.018, 1.0), 0.0, 0.28,
                          roughness_var=0.06, mottle=0.25, noise_scale=90.0)
    badge = principled("FanBadge", (0.70, 0.62, 0.46, 1.0), 0.0, 0.25,
                       roughness_var=0.05, mottle=0.06, noise_scale=120.0, coat=0.6)
    return enamel, chrome, brass, rubber, bakelite, badge


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
        self.mean = sum(pts, Vector()) / len(pts)
        mats = {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)


def pca_axis(pts, largest=True):
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    _w, vecs = np.linalg.eigh(q.T @ q)
    axis = vecs[:, -1] if largest else vecs[:, 0]
    if axis[2] < 0.0:
        axis = -axis
    return Vector(c), Vector(axis)


class Axis:
    """A line through ``c`` along unit ``n``: lateral and axial coordinates."""

    def __init__(self, c, n):
        self.c = Vector(c)
        self.n = Vector(n).normalized()

    def t(self, p):
        return (p - self.c).dot(self.n)

    def lat(self, p):
        d = p - self.c
        return d - self.n * d.dot(self.n)


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups, "axis": None}
    chrome = [s for s in parts if s.mat == CHROME_IDX]
    # the guard: its two rim rings are the only chrome shells 0.4 m across
    rims = [s for s in chrome if max(s.size) > 0.40]
    out["rims"] = rims
    out["blades"] = [s for s in parts if s.mat == BRASS_IDX]
    out["base"] = next((s for s in parts if s.mat == ENAMEL_IDX and s.size.x > 0.35), None)
    out["gasket"] = next((s for s in parts if s.mat == RUBBER_IDX and s.size.x > 0.35
                          and s.size.y > 0.35 and s.size.z < 0.008), None)
    col = [s for s in parts if s.size.z > 0.2 and s.size.x < 0.07 and s.size.y < 0.07]
    out["tube"] = next((s for s in col if s.mat == ENAMEL_IDX), None)
    out["utube"] = next((s for s in col if s.mat == CHROME_IDX), None)
    if len(rims) != 2:
        return out
    c, n = pca_axis(rims[0].pts, largest=False)
    ax = Axis(c, n)
    head_enamel = [s for s in parts if s.mat == ENAMEL_IDX and ax.lat(s.mean).length < 0.02
                   and max(s.size) > 0.15 and s is not out["base"]]
    out["motor"] = head_enamel[0] if len(head_enamel) == 1 else None
    if out["motor"] is not None and ax.t(out["motor"].mean) > 0.0:
        ax = Axis(c, -n)
    rims.sort(key=lambda s: -ax.t(s.mean))       # front first
    out["axis"] = ax

    def own(s):
        """Lateral radius range of a shell about the guard axis through its own mean."""
        rs = [ax.lat(p - s.mean + ax.c).length for p in s.pts]
        return min(rs), max(rs)

    turned = {"shaft": [], "spinner": [], "bezel": [], "hub": [], "mount": [], "rings": []}
    spokes_f, spokes_r, clips = [], [], []
    for s in chrome:
        if s in rims or (s.mean - ax.c).length > 0.30:
            continue
        rho = [ax.lat(p).length for p in s.pts]
        if max(rho) > 0.20 and max(rho) - min(rho) > 0.10:
            (spokes_f if ax.t(s.mean) > 0.0 else spokes_r).append(s)
            continue
        if min(rho) > 0.20:
            clips.append(s)
            continue
        if ax.lat(s.mean).length > 0.02 or abs(ax.t(s.mean)) > 0.35:
            continue
        r0, r1 = own(s)
        span = max(abs(ax.t(p - s.mean + ax.c)) for p in s.pts)
        if r0 > 0.9 * r1 and 0.06 < r1 < 0.21 and span < 0.004:
            turned["rings"].append(s)
        elif r1 < 0.010:
            turned["shaft"].append(s)
        elif 0.020 < r1 < 0.031:
            turned["spinner"].append(s)
        elif 0.033 < r1 < 0.040:
            turned["bezel"].append(s)
        elif 0.041 < r1 < 0.050:
            turned["hub"].append(s)
        elif 0.060 < r1 < 0.072:
            turned["mount"].append(s)
    out.update(turned)
    out["spokes_f"], out["spokes_r"], out["clips"] = spokes_f, spokes_r, clips
    return out


def coaxial_audit(cls):
    """Every turned part of the head against the axis the front rim ring
    defines: the rear rim's centre and normal, and the centres of the hub,
    spinner, shaft, badge bezel, rear mount and motor housing."""
    ax = cls["axis"]
    res = {"offset": 9.0, "tilt": 90.0, "worst": "none", "found": 0}
    if ax is None:
        return res
    _c, n2 = pca_axis(cls["rims"][1].pts, largest=False)
    res["tilt"] = math.degrees(math.acos(min(1.0, abs(n2.dot(ax.n)))))
    parts = [("rear rim", cls["rims"][1])]
    for key in ("hub", "spinner", "shaft", "bezel", "mount"):
        parts += [(key, s) for s in cls[key]]
    if cls.get("motor") is not None:
        parts.append(("motor", cls["motor"]))
    res["found"] = len(parts)
    worst, name = 0.0, "none"
    for label, s in parts:
        d = ax.lat(s.mean).length
        if d > worst:
            worst, name = d, label
    res["offset"], res["worst"] = worst, name
    return res


def ring_centre_dist(ring, ax, p):
    c = ring.mean
    h = (p - c).dot(ax.n)
    lat = (p - c) - ax.n * h
    rm = ring.major
    return math.hypot(lat.length - rm, h)


def seat_audit(cls):
    """Per spoke: the nearest approach of its vertices to its own rim
    ring's centreline circle; per concentric ring: the spokes of its half it
    crosses; per spoke: whether its inner end is in the badge or mount."""
    ax = cls["axis"]
    res = {"front": len(cls.get("spokes_f", [])), "rear": len(cls.get("spokes_r", [])),
           "seat": 9.0, "worst_spoke": -1, "ring_hits": [], "rings": len(cls.get("rings", [])),
           "inner_loose": 0}
    if ax is None:
        return res
    for r in cls["rims"]:
        r.major = sum(ax.lat(p - r.mean + ax.c).length for p in r.pts) / len(r.pts)
    worst, wi = 0.0, -1
    for half, rim in ((cls["spokes_f"], cls["rims"][0]), (cls["spokes_r"], cls["rims"][1])):
        for s in half:
            d = min(ring_centre_dist(rim, ax, p) for p in s.pts)
            if d > worst:
                worst, wi = d, s.idx
    res["seat"], res["worst_spoke"] = worst, wi
    for ring in cls["rings"]:
        half = cls["spokes_f"] if ax.t(ring.mean) > 0.0 else cls["spokes_r"]
        res["ring_hits"].append(sum(1 for s in half if ring.tree.overlap(s.tree)))
    for half, key in ((cls["spokes_f"], "bezel"), (cls["spokes_r"], "mount")):
        hosts = cls[key]
        for s in half:
            if not any(h.tree.overlap(s.tree) for h in hosts):
                res["inner_loose"] += 1
    return res


def column_audit(cls):
    """Both column tubes plumb (PCA axis against Z), each axis through the
    base's centre where it enters the boss, and the guard and base
    diameters read off the mesh."""
    res = {"tilt": 90.0, "coax": 9.0, "guard_dia": 0.0, "base_dia": 0.0}
    base = cls["base"]
    if base is None or cls["tube"] is None or cls["utube"] is None:
        return res
    bc = base.mean
    z_boss = base.hi.z
    tilts, offs = [], []
    for s in (cls["tube"], cls["utube"]):
        c, a = pca_axis(s.pts)
        tilts.append(math.degrees(math.acos(min(1.0, abs(a.z)))))
        k = (z_boss - c.z) / a.z
        offs.append(math.hypot(c.x + a.x * k - bc.x, c.y + a.y * k - bc.y))
    res["tilt"], res["coax"] = max(tilts), max(offs)
    res["base_dia"] = 2.0 * max(math.hypot(p.x - bc.x, p.y - bc.y) for p in base.pts)
    ax = cls["axis"]
    if ax is not None:
        rim = cls["rims"][0]
        res["guard_dia"] = 2.0 * max(ax.lat(p - rim.mean + ax.c).length for p in rim.pts)
    return res


def blade_audit(cls):
    """Radial tip clearance (rim rings' inner face minus the farthest blade
    vertex, about the guard axis); the nearest approach of any blade vertex
    to any guard wire; blade count and angular gaps about the hub's own
    axis; every blade seated in the hub."""
    ax = cls["axis"]
    res = {"blades": len(cls["blades"]), "tip": -1.0, "wire": -1.0, "gap_err": 90.0,
           "angles": [], "unseated": 0}
    if ax is None or not cls["hub"]:
        return res
    inner = min(min(ax.lat(p).length for p in r.pts) for r in cls["rims"])
    tip = max(ax.lat(p).length for b in cls["blades"] for p in b.pts)
    res["tip"] = inner - tip
    wires = cls["rims"] + cls["rings"] + cls["spokes_f"] + cls["spokes_r"] + cls["clips"]
    pts, tris = [], []
    for s in wires:
        base_i = len(pts)
        pts += [tuple(p) for p in s.pts]
        tris += [[base_i + i for i in t] for t in s.tri_idx]
    tree = BVHTree.FromPolygons(pts, tris)
    near = 9.0
    for b in cls["blades"]:
        for p in b.pts:
            hit = tree.find_nearest(p)
            if hit[0] is not None:
                near = min(near, hit[3])
    res["wire"] = near
    hub = cls["hub"][0]
    hub_ax = Axis(hub.mean, ax.n)
    ref = hub_ax.lat(cls["rims"][0].pts[0]).normalized()
    ref2 = ax.n.cross(ref)
    angs = []
    for b in cls["blades"]:
        v = hub_ax.lat(b.mean)
        angs.append(math.degrees(math.atan2(v.dot(ref2), v.dot(ref))) % 360.0)
        if not b.tree.overlap(hub.tree):
            res["unseated"] += 1
    angs.sort()
    nb = len(angs)
    gaps = [((angs[(q + 1) % nb] - angs[q]) % 360.0) for q in range(nb)] if nb else []
    res["gap_err"] = max((abs(g - 360.0 / BLADES) for g in gaps), default=90.0)
    res["angles"] = [round(a, 3) for a in angs]
    return res


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
    """Mass centre (shell volumes x densities) against the gasket's
    footprint: the steepest incline, in the worst direction, the fan stands
    on before its mass centre passes the footprint's edge."""
    gasket = cls["gasket"]
    if gasket is None:
        return None
    total = 0.0
    mom = Vector()
    for s in cls["all"]:
        if s.mat is None:
            continue
        vol, cen = shell_mass(s)
        if s is cls.get("motor"):
            rho = MOTOR_DENSITY
        elif s is cls["tube"] or s is cls["utube"]:
            rho = TUBE_DENSITY
        else:
            rho = DENSITY[s.mat]
        m = abs(vol) * rho
        total += m
        mom += m * cen
    com = mom / total
    gc = gasket.mean
    r_foot = max(math.hypot(p.x - gc.x, p.y - gc.y) for p in gasket.pts
                 if p.z < gasket.lo.z + 1e-4)
    margin = r_foot - math.hypot(com.x - gc.x, com.y - gc.y)
    base_mass = abs(shell_mass(cls["base"])[0]) * DENSITY[ENAMEL_IDX] if cls["base"] else 0.0
    return {"mass": total, "base_mass": base_mass, "com": com, "margin": margin, "r_foot": r_foot,
            "angle": math.degrees(math.atan2(margin, com.z - gasket.lo.z))}


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
        bm.verts.new((0.0, 0.0, 0.3))
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
    img = bpy.data.images.new("FanNrm", size, size, alpha=True, float_buffer=False)
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


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_fan_mesh("FanLow", bevel_offset=0.0012, bevel_segments=1, **flags)
    high = build_fan_mesh("FanHigh", bevel_offset=0.0012, bevel_segments=3, **flags)
    mats = fan_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the bakelite: the plug body is where the high mesh's
    # rounder chamfer differs most from the low.
    target = mats[BAKELITE_IDX]

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
        return (fail("fan mesh did not build", 3),) + none3

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
    coax = coaxial_audit(cls)
    seat = seat_audit(cls)
    column = column_audit(cls)
    blades = blade_audit(cls)
    stance = stance_audit(cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("fan has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "FanLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "FanLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_fan_mesh("FanColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "FanCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_floor_fan_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} rims={len(cls['rims'])} "
          f"spokes=({seat['front']},{seat['rear']}) rings={seat['rings']} "
          f"clips={len(cls.get('clips', []))} blades={blades['blades']}")
    print(f"measured coaxial offset={coax['offset']:.6f} worst={coax['worst']} "
          f"parts={coax['found']} rim_tilt_deg={coax['tilt']:.4f}")
    print(f"measured seat spoke_to_rim={seat['seat']:.6f} ring_hits={seat['ring_hits']} "
          f"inner_loose={seat['inner_loose']}")
    print(f"measured column tilt_deg={column['tilt']:.4f} coax={column['coax']:.6f} "
          f"guard_dia={column['guard_dia']:.4f} base_dia={column['base_dia']:.4f}")
    print(f"measured blades tip_clear={blades['tip']:.5f} wire_clear={blades['wire']:.5f} "
          f"gap_err_deg={blades['gap_err']:.4f} angles={blades['angles']} "
          f"unseated={blades['unseated']}")
    if stance:
        print(f"measured mass={stance['mass']:.3f}kg base={stance['base_mass']:.3f}kg com=({stance['com'].x:.4f},"
              f"{stance['com'].y:.4f},{stance['com'].z:.4f}) margin={stance['margin']:.4f} "
              f"foot_r={stance['r_foot']:.4f} tip_angle_deg={stance['angle']:.3f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    floors = ((ENAMEL_IDX, ENAMEL_FACES_MIN, "enamel"), (CHROME_IDX, CHROME_FACES_MIN, "chrome"),
              (BRASS_IDX, BRASS_FACES_MIN, "brass"), (RUBBER_IDX, RUBBER_FACES_MIN, "rubber"),
              (BAKELITE_IDX, BAKELITE_FACES_MIN, "bakelite"), (BADGE_IDX, BADGE_FACES_MIN, "badge"))
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
    if bb[2] > ZMIN_EPS or cls["gasket"] is None or cls["gasket"].lo.z > ZMIN_EPS:
        return (fail(f"grounded zmin={bb[2]:.5f} gasket zmin="
                     f"{cls['gasket'] and cls['gasket'].lo.z:.5f}", 16),) + none3
    if coax["found"] != 7 or coax["offset"] > AXIS_TOL or coax["tilt"] > AXIS_TILT_MAX_DEG:
        return (fail(f"rotor and head not coaxial with the guard: {coax}", 17),) + none3
    if (seat["front"] != SPOKES_F or seat["rear"] != SPOKES_R or seat["seat"] > SEAT_MAX
            or seat["rings"] != len(RINGS_F) + len(RINGS_R) or seat["inner_loose"]
            or len(cls["clips"]) != CLIPS
            or any(h != (SPOKES_F if i < len(RINGS_F) else SPOKES_R)
                   for i, h in enumerate(sorted(seat["ring_hits"], reverse=True)))):
        return (fail(f"guard wires not seated: {seat}", 18),) + none3
    if (column["tilt"] > PLUMB_MAX_DEG or column["coax"] > COAX_MAX
            or abs(column["guard_dia"] - GUARD_DIA) > SIZE_TOL
            or abs(column["base_dia"] - BASE_DIA) > SIZE_TOL):
        return (fail(f"column plumb / size: {column}", 19),) + none3
    if (blades["blades"] != BLADES or blades["unseated"]
            or not (TIP_CLEAR[0] <= blades["tip"] <= TIP_CLEAR[1])
            or blades["wire"] < WIRE_CLEAR_MIN):
        return (fail(f"blade clearance: tip {blades['tip']:.5f} not in {TIP_CLEAR} or wire "
                     f"{blades['wire']:.5f} < {WIRE_CLEAR_MIN}", 20),) + none3
    if blades["gap_err"] > SPACING_TOL_DEG:
        return (fail(f"blade spacing off by {blades['gap_err']:.3f} deg", 21),) + none3
    if stance is None or stance["angle"] < TIP_MIN_DEG:
        return (fail(f"tips over: {stance and round(stance['angle'], 3)} deg < {TIP_MIN_DEG}", 22),) + none3
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

    # The house rig scaled to a 1.25 m prop: warm key upper left, cool fill
    # low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-2.0, -2.4, 2.2), 92.0, 1.3, (1.0, 0.94, 0.86), spread=26.0)
    light("Fill", (2.6, -1.8, 0.4), 9.0, 3.0, (0.72, 0.82, 1.0))
    light("Rim", (-0.9, 1.6, 1.4), 60.0, 1.1, (0.62, 0.78, 1.0))
    light("Wedge", (2.2, 2.3, 0.9), 125.0, 1.8, (1.0, 0.68, 0.38),
          target=(centre.x + 2.4, centre.y + WALL_Y, 0.55))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.55, -0.83, 0.0)).normalized()
    cam.location = centre + view * 3.95 + Vector((0.0, 0.0, 0.42))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.01))
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
    # Standard, not AgX: AgX washes the enamel and brass toward pastel
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
    p.add_argument("--offset-hub", action="store_true")
    p.add_argument("--short-spoke", action="store_true")
    p.add_argument("--lean-column", action="store_true")
    p.add_argument("--long-blades", action="store_true")
    p.add_argument("--skew-blade", action="store_true")
    p.add_argument("--hollow-base", action="store_true")
    p.add_argument("--loose-spinner", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        offset_hub=args.offset_hub,
        short_spoke=args.short_spoke,
        lean_column=args.lean_column,
        long_blades=args.long_blades,
        skew_blade=args.skew_blade,
        hollow_base=args.hollow_base,
        loose_spinner=args.loose_spinner,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("floor-fan OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
