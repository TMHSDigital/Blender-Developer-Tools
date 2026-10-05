"""Game-ready planetary science rover — a showcase piece, not an example.

Asserts budget conformance of a procedural six-wheeled rocker-bogie rover
standing on a patch of rocky regolith, after composing shipped pipeline
pieces: bmesh construction, UVs, nine materials, high-to-low normal bake, LOD
chain, convex collider, Unity glTF export.

A warm-electronics body box in cream paint with gold-foil quilted insulation
blankets on its sides and front, a deck plate carrying instrument boxes with
sample inlets, a remote-sensing mast, a high-gain dish on a two-axis gimbal,
a low-gain whip and a UHF can; a finned radioisotope power unit on struts at
the rear between two radiator fin banks. On each side a rocker pivots on a
boss in the body side and carries the rear wheel; a bogie pinned in a clevis
on the rocker's front end carries the middle and front wheels. The two
rockers are linked through a differential: a crank above each rocker pivot,
a link to each end of a bar pivoting on the deck, so the rockers turn equal
and opposite. Six cleated aluminium wheels, each a drum with 24 chevron
grousers, six curved titanium flexure spokes and a hub on a drive actuator;
the four corner wheels hang from steering actuators through C-brackets. The
mast carries an azimuth actuator, an elevation yoke and a camera head with a
laser telescope window, two camera barrels of different focal lengths and a
navigation camera pair; two weather booms on its shaft. A 5-DOF arm reaches
down from the body's front: shoulder azimuth and elevation, elbow, wrist and
a turret roll, the turret carrying a drill with stabiliser prongs over a
boulder, a contact spectrometer, a scoop and a hand-lens camera. Cable
harnesses run along every leg, the mast and the arm. The regolith is a
closed-form surface with wheel ruts trailing behind both wheel lines; its
surface is fitted so every wheel sinks into it; broken rocks lie scattered
and sealed into it.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--float-wheel`` every wheel sunk into the
regolith, ``--offset-pin`` the rocker and bogie pivot pins coaxial with their
bushings, ``--sink-grousers`` every grouser seated on its drum,
``--lean-mast`` the mast plumb and the rover's size, ``--jam-rocker`` the two
rockers equal and opposite through the differential, ``--offset-steer`` every
steering axis through its wheel's centre, ``--camber-wheel`` every axle
level and lateral, ``--bunch-grousers`` equal grouser pitch,
``--overload-turret`` the mass centre inside the support polygon with a
tip-over margin, ``--loose-dish`` one connected assembly.

The only RNG is a seeded ``random.Random`` for the rocks' shapes; the rest is
closed-form. DECIMATE COLLAPSE triangle counts are not byte-identical across
Blender versions — the LOD gate is a ratio band, not an exact count.

    blender --background --python planet_rover.py --
    blender --background --python planet_rover.py -- --skip-decimate
    blender --background --python planet_rover.py -- --output rover.png
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

# --- Layout (front at +X, the rover's left at +Y; G is the regolith datum) ---------
G = 0.11
R_SKIN = 0.2475             # wheel drum outer skin: a 0.50 m wheel
GR_H = 0.0075               # grouser height proud of the skin
GR_BITE = 0.0010            # grouser root inside the skin
GR_W = 0.0040               # grouser half width
R_TIP = R_SKIN + GR_H
SINK = 0.012                # design sink of the grouser tips into the regolith
WHEEL_Y = 1.15
W_HALF = 0.20               # drum half width: 0.40 m wheels
ZC0 = G + R_TIP - SINK      # wheel centre height in the rest pose
WHEEL_X = (1.05, 0.05, -1.00)   # front, middle, rear
N_GR = 24
CHEV = 0.12                 # grouser chevron sweep at the drum edge (rad)
DRUM_SEGS = 36
N_SPOKE = 6

PIV_X, PIV_Y, PIV_Z = -0.15, 0.715, G + 0.88     # rocker pivot (differential axis)
BOG_X, BOG_Z = 0.52, G + 0.56                     # bogie pivot on the rocker's front end
ROCKER_DEG = 4.0            # each rocker's deflection, equal and opposite
BOGIE_DEG = (-6.0, 5.0)     # left, right bogie angle on its rocker
CRANK_L = 0.30              # differential crank above the rocker pivot
LINK_Y = 0.6645             # link eye's mid-plane on the crank pin
BAR_Y = 0.46                # differential bar end radius
BAR_Z = G + 1.25

BODY_CX, BODY_HX, BODY_HY = 0.02, 0.80, 0.58
BODY_Z0, BODY_Z1 = G + 0.60, G + 1.10
DECK_Z = G + 1.115          # deck plate top
FOOT_Z = G + 1.102          # bottom of anything standing on the deck

MAST_X, MAST_Y = 0.58, -0.40
HEAD_AZ = math.radians(-32.0)
HEAD_PITCH = math.radians(-8.0)
MAST_AX_Z = G + 1.989       # mast head elevation axis

ARM_S = Vector((0.92, 0.18, G + 1.06))           # shoulder elevation axis
ARM_UP = (0.70, math.radians(15.0))              # upper arm length, elevation
ARM_FORE = (0.70, math.radians(-95.0))           # forearm length, elevation
TURRET_OFF = 0.21

HGA_X, HGA_Y = -0.50, 0.36
HGA_AZ = math.radians(-40.0)
HGA_EL = math.radians(45.0)
HGA_AX_Z = G + 1.42
DISH_R, DISH_F, DISH_W0 = 0.30, 0.19, 0.09

RTG_Q = Vector((-1.03, 0.0, G + 0.62))
RTG_D = Vector((-0.40, 0.0, 0.917)).normalized()

# Regolith patch: a superellipse (n = 4) with a wobbled outline.
PATCH_C = (-0.05, 0.0)
PATCH_A, PATCH_B = 2.30, 1.75
TERRAIN_NU, TERRAIN_NV = 52, 38
EDGE_DROP = 0.045
RUT_D = 0.018
BERM_H = 0.012
RBF_SIGMA = (0.42, 0.75)      # along, across the track

# --- Falsifier sizes -----------------------------------------------------------------
FLOAT_WHEEL = 0.030
OFFSET_PIN = 0.004
SINK_GROUSERS = 0.003
LEAN_MAST_DEG = 1.5
JAM_DEG = 1.5
OFFSET_STEER = 0.010
CAMBER_DEG = 1.0
BUNCH_DEG = 3.0
OVERLOAD = 40.0
LOOSE_DISH = 0.120
FALSIFY_WHEEL = 3           # right front
FLOAT_UNIT = 4              # right middle: its contact lies on the support polygon's edge

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (4.857, 3.709, 2.200)
BASE_TRIS_MIN = 45600
BASE_TRIS_MAX = 46600
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 9
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 1160
BAKE_RES = 1024
CAGE_EXTRUSION = 0.003
# per slot: paint, foil, alu, anodised, titanium, glass, harness, regolith, rock
FACE_FLOORS = (2260, 1140, 5820, 8390, 2150, 600, 870, 2260, 550)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Every wheel sunk into the regolith: the deepest wheel vertex below the surface.
SINK_MIN, SINK_MAX = 0.006, 0.025
# Pivot pins coaxial with their bushings.
PIN_OFF_TOL = 0.0005
PIN_TILT_MAX_DEG = 0.3
# Grousers seated on the drum skin and proud of it.
GR_BITE_MIN, GR_BITE_MAX = 0.0005, 0.0025
GR_PROUD_MIN = 0.0050
# Mast plumb; rover size.
MAST_TILT_MAX_DEG = 0.2
TRACK_WIDTH = 2.700
TRACK_TOL = 0.006
ROVER_HEIGHT = 2.100
ROVER_LENGTH = 3.351
SIZE_TOL = 0.010
# Differential: rockers equal and opposite, link eyes on their crank pins.
DIFF_TOL_DEG = 0.10
LINK_OFF_TOL = 0.0005
# Steering axes through the corner wheels' centres.
STEER_OFF_TOL = 0.0010
# Axles level and lateral.
AXLE_TOL_DEG = 0.20
# Grouser pitch.
PITCH_TOL_DEG = 0.30
# Stance: mass centre inside the contact polygon by the 30-degree tip margin.
TIP_DEG = 45.0

HERO_YAW_DEG = -2.0
WALL_Y = 4.2

(PAINT_IDX, FOIL_IDX, ALU_IDX, ANOD_IDX, TITAN_IDX, GLASS_IDX, HARNESS_IDX, REGOLITH_IDX,
 ROCK_IDX) = range(9)
# Densities (kg/m^3) per material slot for the stance audit: the body box and
# instrument boxes are modelled solid but are hollow shells full of
# electronics, so they carry an effective density; regolith and rock are
# ground, not rover (0).
DENSITY = (330.0, 330.0, 2700.0, 1600.0, 2400.0, 2500.0, 1400.0, 0.0, 0.0)

# Part tags: face attributes naming which part a face belongs to, so the
# audits can find the shells they measure. Every measured value is read from
# the vertices, never from these constants.
(T_NONE, T_TERRAIN, T_ROCK, T_DRUM, T_GROUSER, T_STEER, T_PIN, T_BUSH, T_CRANKPIN,
 T_LINKEYE, T_MAST, T_TURRET, T_DISH, T_HUB, T_SPOKE) = range(15)

ZAX = Vector((0.0, 0.0, 1.0))
YAX = Vector((0.0, 1.0, 0.0))
XAX = Vector((1.0, 0.0, 0.0))


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
# Construction helpers (copied from showcase/road-bicycle, not imported)
# --------------------------------------------------------------------------

class Build:
    """The bmesh under construction, its part-tag and unit layers and named
    vertex groups (for the pose and for the falsifiers that move one
    assembly)."""

    def __init__(self, bm):
        self.bm = bm
        self.tag = bm.faces.layers.int.new("part")
        self.unit = bm.faces.layers.int.new("unit")
        self.tone = bm.faces.layers.float.new("Tone")
        self.rut = bm.verts.layers.float.new("RutMask")
        self.groups = {}
        self.bevel = []

    def part(self, tag=T_NONE, unit=0, *groups, bevel=False, tone=0.5):
        return _Part(self, tag, unit, groups, bevel, tone)

    def verts(self, *names):
        out = set()
        for n in names:
            out.update(self.groups.get(n, []))
        return out


class _Part:
    def __init__(self, b, tag, unit, groups, bevel, tone):
        self.b, self.t, self.u, self.g, self.bevel, self.tone = b, tag, unit, groups, bevel, tone

    def __enter__(self):
        self.nf = len(self.b.bm.faces)
        self.nv = len(self.b.bm.verts)
        return self

    def __exit__(self, *exc):
        bm = self.b.bm
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        for i in range(self.nf, len(bm.faces)):
            f = bm.faces[i]
            f[self.b.tag] = self.t
            f[self.b.unit] = self.u
            f[self.b.tone] = self.tone
        vs = [bm.verts[i] for i in range(self.nv, len(bm.verts))]
        for g in self.g:
            self.b.groups.setdefault(g, []).extend(vs)
        if self.bevel:
            self.b.bevel.extend(vs)
        return False


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
              phase=0.0, solid=False, seg_mats=None):
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
        f0.material_index = mat_idx
        f1.material_index = mat_idx
    return [v for ring in rings for v in ring]


def lathe_on(bm, profile, segs, mat_idx, center, axis, ref=XAX, solid=True, phase=0.0,
             seg_mats=None):
    axis = Vector(axis).normalized()
    if abs(axis.dot(Vector(ref))) > 0.9:
        ref = ZAX if abs(axis.z) < 0.9 else YAX
    return add_lathe(bm, profile, segs, mat_idx, center=center, rot=frame(axis, ref),
                     solid=solid, phase=phase, seg_mats=seg_mats)


def add_sweep(bm, pts, radius, sides, mat_idx, phase=0.0, ref=None):
    """Capped tube swept along a polyline with parallel-transport frames."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    radii = list(radius) if isinstance(radius, (list, tuple)) else [radius] * n
    tans = []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        tans.append((b - a).normalized())
    if ref is None:
        ref = ZAX if abs(tans[0].z) < 0.9 else XAX
    nrm = (Vector(ref) - tans[0] * Vector(ref).dot(tans[0])).normalized()
    rings = []
    for i, (p, t) in enumerate(zip(pts, tans)):
        nrm = (nrm - t * nrm.dot(t)).normalized()
        bi = t.cross(nrm)
        ring = []
        for k in range(sides):
            a = phase + 2.0 * math.pi * k / sides
            ring.append(bm.verts.new(p + radii[i] * (nrm * math.cos(a) + bi * math.sin(a))))
        rings.append(ring)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def tube(bm, a, b, r, mat_idx, sides=12, phase=0.0):
    return add_sweep(bm, [a, b], r, sides, mat_idx, phase=phase)


def rrect(ha, hb, rc, n_corner=4):
    """Rounded rectangle loop (counter-clockwise)."""
    rc = max(min(rc, ha - 1e-4, hb - 1e-4), 0.0003)
    pts = []
    for k, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        cx, cy = sx * (ha - rc), sy * (hb - rc)
        a0 = 0.5 * math.pi * k
        for s in range(n_corner + 1):
            a = a0 + 0.5 * math.pi * s / n_corner
            pts.append((cx + rc * math.cos(a), cy + rc * math.sin(a)))
    return pts


def add_rbox(bm, ha, hb, rc, profile, origin, rot, mat_idx, n_corner=2):
    """Loft of rounded rectangles along local Z: profile [(inset, z)]."""
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


def box_profile(z0, z1, c):
    return [(c, z0), (0.0, z0 + c), (0.0, z1 - c), (c, z1)]


def add_box(bm, centre, half, rot, mat_idx, rc=0.006, c=0.003, n_corner=2):
    """Chamfered rounded box: ``half`` = (along local x, local y, local z)."""
    hx, hy, hz = half
    return add_rbox(bm, hx, hy, rc, box_profile(-hz, hz, c), centre, rot, mat_idx, n_corner)


def add_plate_xz(bm, outline, y0, y1, mat_idx):
    """A world-XZ outline [(x, z)] extruded along Y from y0 to y1."""
    a = [bm.verts.new((x, y0, z)) for x, z in outline]
    b = [bm.verts.new((x, y1, z)) for x, z in outline]
    n = len(outline)
    faces = [bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i])) for i in range(n)]
    faces.append(bm.faces.new(tuple(reversed(a))))
    faces.append(bm.faces.new(tuple(b)))
    _mark(faces, mat_idx)
    return a + b


def add_loft(bm, rings_pts, mat_idx):
    """Closed loops [[Vector]] lofted in order, n-gon caps at both ends."""
    rings = [[bm.verts.new(p) for p in loop] for loop in rings_pts]
    n = len(rings[0])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(n):
            m = (j + 1) % n
            faces.append(bm.faces.new((r0[j], r0[m], r1[m], r1[j])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_bar(bm, pts, wax, half_w, half_t, rc, mat_idx, fillet=0.008, filleted=False, steps=3):
    """Flat bar bent in the plane normal to ``wax``: width along ``wax``,
    thickness in the bending plane; rounded-rectangle section."""
    pts = [Vector(p) for p in pts] if filleted else fillet_path(pts, fillet, steps)
    wax = Vector(wax).normalized()
    sec = rrect(half_w, half_t, rc, 1)
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


def hull2d(pts):
    """Convex hull, counter-clockwise (monotone chain)."""
    pts = sorted(set((round(x, 9), round(y, 9)) for x, y in pts))

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


def circle_pts(cx, cz, r, n=16, phase=0.0):
    return [(cx + r * math.cos(phase + 2.0 * math.pi * k / n),
             cz + r * math.sin(phase + 2.0 * math.pi * k / n)) for k in range(n)]


def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def rot_y(p, c, ang):
    return Vector(c) + Matrix.Rotation(ang, 3, "Y") @ (Vector(p) - Vector(c))


def ymir(p, s):
    return Vector((p[0], s * p[1], p[2]))


# --------------------------------------------------------------------------
# Pose: the rocker and bogie angles and where they put each wheel
# --------------------------------------------------------------------------

def side_angles(s, jam=False):
    """(rocker angle, bogie angle) for side s; the rockers are equal and
    opposite through the differential; ``jam`` turns the right rocker past
    what the differential allows."""
    ar = math.radians(ROCKER_DEG) * s
    if jam and s < 0:
        ar += math.radians(JAM_DEG)
    ab = math.radians(BOGIE_DEG[0 if s > 0 else 1])
    return ar, ab


def pivots(s):
    return Vector((PIV_X, s * PIV_Y, PIV_Z)), Vector((BOG_X, s * PIV_Y, BOG_Z))


def pose_point(p, s, on_bogie, jam=False):
    ar, ab = side_angles(s, jam)
    piv, bog = pivots(s)
    q = Vector(p)
    if on_bogie:
        q = rot_y(q, bog, ab)
    return rot_y(q, piv, ar)


def wheel_centres(jam=False):
    """unit -> posed wheel centre; units 0..2 left front/middle/rear, 3..5 right."""
    out = {}
    for s in (1.0, -1.0):
        for k in range(3):
            u = k + (0 if s > 0 else 3)
            rest = Vector((WHEEL_X[k], s * WHEEL_Y, ZC0))
            out[u] = pose_point(rest, s, k < 2, jam)
    return out


# --------------------------------------------------------------------------
# Regolith
# --------------------------------------------------------------------------

def wob(th):
    return 1.0 + 0.035 * math.cos(3 * th + 0.7) + 0.025 * math.cos(5 * th + 2.1) \
        + 0.012 * math.cos(7 * th + 0.3)


def patch_m(x, y):
    lx = (x - PATCH_C[0]) / PATCH_A
    ly = (y - PATCH_C[1]) / PATCH_B
    th = math.atan2(ly, lx)
    return (lx ** 4 + ly ** 4) ** 0.25 / wob(th)


def patch_point(u, v):
    """Grid (u, v) in [-1, 1]^2 onto the wobbled superellipse: each square
    ring of the grid lands on one superellipse ring."""
    m = max(abs(u), abs(v))
    if m < 1e-12:
        return PATCH_C[0], PATCH_C[1]
    n4 = (u ** 4 + v ** 4) ** 0.25
    px, py = u * m / n4, v * m / n4
    w = wob(math.atan2(py, px))
    return PATCH_C[0] + PATCH_A * px * w, PATCH_C[1] + PATCH_B * py * w


class Regolith:
    """The regolith's surface: a closed-form field, two ruts trailing behind
    the wheel lines, and a sum of Gaussians fitted so the surface passes
    through each wheel's contact height (the grouser tips SINK into it)."""

    def __init__(self, centres):
        self.front_x = {1.0: centres[0].x, -1.0: centres[3].x}
        self.c = []
        rhs = []
        for u in sorted(centres):
            w = centres[u]
            self.c.append((w.x, w.y))
            rhs.append(w.z - R_TIP + SINK - self.raw(w.x, w.y))
        n = len(self.c)
        a = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                a[i, j] = self.g(self.c[i], self.c[j][0], self.c[j][1])
        self.w = [float(x) for x in np.linalg.solve(a, np.array(rhs))]

    @staticmethod
    def g(c, x, y):
        return math.exp(-((x - c[0]) ** 2 / (2.0 * RBF_SIGMA[0] ** 2)
                          + (y - c[1]) ** 2 / (2.0 * RBF_SIGMA[1] ** 2)))

    def rut_terms(self, x, y):
        mask, berm = 0.0, 0.0
        for s, xf in self.front_x.items():
            d = abs(y - s * WHEEL_Y)
            along = 1.0 - smoothstep(xf + 0.02, xf + 0.20, x)
            mask = max(mask, (1.0 - smoothstep(0.215, 0.265, d)) * along)
            berm = max(berm, math.exp(-((d - 0.300) / 0.035) ** 2) * along)
        return mask, berm

    @staticmethod
    def low(x, y):
        return (0.022 * math.cos(1.25 * x + 0.4) * math.cos(1.05 * y - 0.7)
                + 0.012 * math.sin(2.7 * x - 1.3 * y + 0.5))

    @staticmethod
    def fine(x, y):
        return (0.006 * math.cos(6.3 * x + 4.1 * y + 1.3)
                + 0.004 * math.sin(8.9 * y - 5.7 * x + 1.1)
                + 0.0025 * math.cos(13.1 * x - 11.3 * y))

    def raw(self, x, y):
        """The field, with a rut pressed in along each wheel line: the rut's
        floor is level across the track (compacted), at the height of the
        track's centre line."""
        mask, berm = self.rut_terms(x, y)
        z = G + self.low(x, y) + self.fine(x, y) * (1.0 - 0.8 * mask)
        if mask > 0.0:
            z += (G + self.low(x, math.copysign(WHEEL_Y, y)) - z) * mask
        return z - RUT_D * mask + BERM_H * berm

    def top(self, x, y):
        z = self.raw(x, y)
        for c, w in zip(self.c, self.w):
            z += w * self.g(c, x, y)
        return z - EDGE_DROP * smoothstep(0.80, 1.0, patch_m(x, y)) ** 1.5


def track_warp(n):
    """n + 1 grid values over [-1, 1], closer together across the two ruts
    (equal steps of a density that peaks on the wheel lines)."""
    vt = WHEEL_Y / PATCH_B
    k = 4000
    xs = [-1.0 + 2.0 * i / k for i in range(k + 1)]
    dens = [1.0 + 1.6 * math.exp(-((abs(x) - vt) / 0.10) ** 2) for x in xs]
    cum = [0.0]
    for i in range(1, k + 1):
        cum.append(cum[-1] + 0.5 * (dens[i] + dens[i - 1]) * (xs[i] - xs[i - 1]))
    out, i = [], 0
    for j in range(n + 1):
        target = cum[-1] * j / n
        while i < k - 1 and cum[i + 1] < target:
            i += 1
        t = (target - cum[i]) / max(cum[i + 1] - cum[i], 1e-12)
        out.append(xs[i] + (xs[i + 1] - xs[i]) * min(max(t, 0.0), 1.0))
    out[0], out[-1] = -1.0, 1.0
    return out


def add_regolith(b, field):
    bm = b.bm
    nu, nv = TERRAIN_NU, TERRAIN_NV
    vs = track_warp(nv)
    with b.part(T_TERRAIN, 0):
        grid = []
        for j in range(nv + 1):
            row = []
            for i in range(nu + 1):
                x, y = patch_point(-1.0 + 2.0 * i / nu, vs[j])
                vert = bm.verts.new((x, y, field.top(x, y)))
                vert[b.rut] = field.rut_terms(x, y)[0]
                row.append(vert)
            grid.append(row)
        faces = []
        for j in range(nv):
            for i in range(nu):
                faces.append(bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1],
                                           grid[j + 1][i])))
        ring = ([grid[0][i] for i in range(nu + 1)] + [grid[j][nu] for j in range(1, nv + 1)]
                + [grid[nv][i] for i in reversed(range(nu))]
                + [grid[j][0] for j in reversed(range(1, nv))])
        # a rolled skirt down to the floor
        rings = [ring]
        for push, frac in ((0.028, 0.45), (0.034, 0.0)):
            nr = []
            for v in ring:
                d = Vector((v.co.x - PATCH_C[0], v.co.y - PATCH_C[1], 0.0)).normalized()
                nr.append(bm.verts.new((v.co.x + d.x * push, v.co.y + d.y * push,
                                        v.co.z * frac)))
            rings.append(nr)
        n = len(ring)
        for r0, r1 in zip(rings, rings[1:]):
            for k in range(n):
                m = (k + 1) % n
                faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
        cen = bm.verts.new((PATCH_C[0], PATCH_C[1], 0.0))
        last = rings[-1]
        for k in range(n):
            faces.append(bm.faces.new((cen, last[(k + 1) % n], last[k])))
        _mark(faces, REGOLITH_IDX)


# (x, y, half sizes, yaw, subdivisions): broken rocks; the first sits under the drill
ROCKS = [
    (None, None, (0.22, 0.18, 0.19), 0.4, 2),
    (-1.70, 0.45, (0.20, 0.15, 0.13), 1.1, 2),
    (-0.55, -0.33, (0.11, 0.09, 0.07), 2.0, 1),
    (0.35, 1.52, (0.13, 0.10, 0.09), 0.3, 2),
    (1.30, -0.62, (0.14, 0.11, 0.10), 2.6, 2),
    (-0.95, -1.52, (0.12, 0.09, 0.08), 0.9, 1),
    (1.95, 0.95, (0.08, 0.07, 0.06), 1.7, 1),
    (0.28, -1.53, (0.09, 0.07, 0.06), 0.2, 1),
    (-1.95, -0.55, (0.11, 0.09, 0.07), 2.2, 1),
    (1.20, 0.52, (0.06, 0.05, 0.04), 1.2, 1),
    (-0.20, 0.50, (0.06, 0.05, 0.04), 0.5, 1),
    (0.90, -1.52, (0.07, 0.06, 0.05), 2.9, 1),
    (1.90, -0.25, (0.05, 0.04, 0.035), 0.8, 1),
    (-1.00, 0.05, (0.05, 0.045, 0.035), 1.9, 1),
    (0.55, -0.80, (0.045, 0.04, 0.03), 0.1, 1),
    (-0.40, 1.48, (0.05, 0.045, 0.035), 2.4, 1),
    (-1.75, 0.02, (0.07, 0.06, 0.05), 0.6, 1),
    (1.62, -0.95, (0.05, 0.04, 0.035), 1.4, 1),
    (-2.15, 0.90, (0.06, 0.05, 0.04), 2.7, 1),
]
ROCK_BITE = 0.012


def add_rocks(b, field, drill_xy):
    bm = b.bm
    rng = random.Random(1976)
    for idx, (x, y, half, yaw, sub) in enumerate(ROCKS):
        if x is None:
            x, y = drill_xy
        tmp = bmesh.new()
        try:
            bmesh.ops.create_icosphere(tmp, subdivisions=sub, radius=1.0)
            pts = [v.co.copy() for v in tmp.verts]
            tris = [[v.index for v in f.verts] for f in tmp.faces]
        finally:
            tmp.free()
        jit = [1.0 + rng.uniform(-0.10, 0.10) for _ in pts]
        planes = []
        for k in range(5):
            th = rng.uniform(0.0, 2.0 * math.pi)
            el = rng.uniform(-0.35, 0.9)
            planes.append((Vector((math.cos(th) * math.cos(el), math.sin(th) * math.cos(el),
                                   math.sin(el))), rng.uniform(0.62, 0.84)))
        if idx == 0:
            planes.append((Vector((0.05, -0.03, 1.0)).normalized(), 0.71))
        # a broad bed underneath: the rock is embedded, not a ball in a pit
        planes.append((Vector((0.0, 0.0, -1.0)), 0.50))
        rz = Matrix.Rotation(yaw, 3, "Z")
        world = []
        for p, j in zip(pts, jit):
            q = p * j
            for n, d in planes:
                e = q.dot(n)
                if e > d:
                    q = q - n * (e - d)
            world.append(rz @ Vector((q.x * half[0], q.y * half[1], q.z * half[2])))
        # seat: sink until every sector's lowest vertex is ROCK_BITE under the ground
        cx = sum(p.x for p in world) / len(world)
        cy = sum(p.y for p in world) / len(world)
        zmid = 0.5 * (min(p.z for p in world) + max(p.z for p in world))
        sectors = {}
        for p in world:
            if p.z > zmid:
                continue
            sec = int(((math.atan2(p.y - cy, p.x - cx) + math.pi) / (2 * math.pi)) * 6) % 6
            h = p.z - field.top(x + p.x, y + p.y)
            sectors[sec] = min(sectors.get(sec, 9.0), h)
        dz = -max(sectors.values()) - ROCK_BITE
        tone = rng.uniform(0.0, 1.0)
        with b.part(T_ROCK, idx, tone=tone):
            vs = [bm.verts.new((x + p.x, y + p.y, p.z + dz)) for p in world]
            faces = [bm.faces.new([vs[i] for i in t]) for t in tris]
            _mark(faces, ROCK_IDX)


# --------------------------------------------------------------------------
# Body, deck and power unit
# --------------------------------------------------------------------------

def add_quilt(bm, origin, eu, ev, en, size, grid, cells, t0, puff, thick, mat_idx):
    """A foil blanket: a grid puffed between stitch lines (``cells`` per
    side), a rim down to a back plane ``thick`` behind it, the back closed
    by a fan so it holds no n-gon."""
    o, eu, ev, en = Vector(origin), Vector(eu), Vector(ev), Vector(en)
    (uu, vv), (nu, nv), (cu, cv) = size, grid, cells
    front, back = [], []
    for j in range(nv + 1):
        rf, rb = [], []
        for i in range(nu + 1):
            fu = (i * cu / nu) % 1.0
            fv = (j * cv / nv) % 1.0
            off = t0 + puff * math.sin(math.pi * fu) * math.sin(math.pi * fv)
            base = o + eu * (uu * i / nu) + ev * (vv * j / nv)
            rf.append(bm.verts.new(base + en * off))
            rb.append(bm.verts.new(base + en * (t0 - thick)))
        front.append(rf)
        back.append(rb)
    faces = []
    for j in range(nv):
        for i in range(nu):
            faces.append(bm.faces.new((front[j][i], front[j][i + 1], front[j + 1][i + 1],
                                       front[j + 1][i])))
    rim = ([(0, i) for i in range(nu + 1)] + [(j, nu) for j in range(1, nv + 1)]
           + [(nv, i) for i in reversed(range(nu))] + [(j, 0) for j in reversed(range(1, nv))])
    for k in range(len(rim)):
        (ja, ia), (jb, ib) = rim[k], rim[(k + 1) % len(rim)]
        faces.append(bm.faces.new((front[jb][ib], front[ja][ia], back[ja][ia], back[jb][ib])))
    cen = bm.verts.new(o + eu * (uu * 0.5) + ev * (vv * 0.5) + en * (t0 - thick))
    for k in range(len(rim)):
        (ja, ia), (jb, ib) = rim[k], rim[(k + 1) % len(rim)]
        faces.append(bm.faces.new((cen, back[ja][ia], back[jb][ib])))
    # the back grid's interior vertices are unused: drop them
    used = {v for row in (back[0], back[nv]) for v in row}
    used |= {back[j][0] for j in range(nv + 1)} | {back[j][nu] for j in range(nv + 1)}
    for row in back:
        for v in row:
            if v not in used:
                bm.verts.remove(v)
    _mark(faces, mat_idx)


def add_body(b):
    bm = b.bm
    ident = Matrix.Identity(3)
    with b.part(T_NONE, 0, "body"):
        add_rbox(bm, BODY_HX, BODY_HY, 0.045,
                 [(0.012, BODY_Z0), (0.0, BODY_Z0 + 0.012), (0.0, BODY_Z1 - 0.012),
                  (0.012, BODY_Z1)], (BODY_CX, 0.0, 0.0), ident, PAINT_IDX, n_corner=3)
        add_rbox(bm, BODY_HX + 0.03, BODY_HY + 0.03, 0.06,
                 [(0.008, G + 1.085), (0.0, G + 1.093), (0.0, DECK_Z - 0.010), (0.008, DECK_Z - 0.002)],
                 (BODY_CX, 0.0, 0.0), ident, ANOD_IDX, n_corner=3)
    with b.part(T_NONE, 0, "body"):
        add_rbox(bm, BODY_HX + 0.005, BODY_HY + 0.005, 0.045,
                 [(0.0, DECK_Z - 0.006), (0.0, DECK_Z - 0.001), (0.004, DECK_Z + 0.001)],
                 (BODY_CX, 0.0, 0.0), ident, PAINT_IDX, n_corner=3)
    with b.part(T_NONE, 0, "body"):
        for sx in (1.0, -1.0):
            for sy in (1.0, -1.0):
                cx = BODY_CX + sx * (BODY_HX - 0.030)
                cy = sy * (BODY_HY - 0.030)
                add_rbox(bm, 0.034, 0.034, 0.016, box_profile(BODY_Z0 - 0.004, G + 1.090, 0.004),
                         (cx, cy, 0.0), ident, ANOD_IDX, n_corner=2)
    with b.part(T_NONE, 0, "body"):
        # foil blankets: both sides and the front
        for s in (1.0, -1.0):
            for x0, ln, nu, cu in ((-0.72, 0.66, 12, 3), (-0.02, 0.74, 12, 3)):
                add_quilt(bm, (BODY_CX + x0, s * (BODY_HY), G + 0.64), (1.0, 0.0, 0.0),
                          (0.0, 0.0, 1.0), (0.0, s, 0.0), (ln, 0.40), (nu, 8), (cu, 2),
                          0.004, 0.017, 0.014, FOIL_IDX)
        add_quilt(bm, (BODY_CX + BODY_HX, -0.50, G + 0.655), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
                  (1.0, 0.0, 0.0), (1.00, 0.38), (16, 8), (4, 2), 0.004, 0.015, 0.014, FOIL_IDX)
    # front hazard cameras
    fx = BODY_CX + BODY_HX
    for k, yc in enumerate((0.24, -0.24)):
        with b.part(T_NONE, 0, "body", bevel=True):
            add_box(bm, (fx + 0.038, yc, G + 0.705), (0.045, 0.078, 0.032),
                    frame(ZAX, XAX), PAINT_IDX, rc=0.012, c=0.004)
        for dy in (-0.042, 0.042):
            with b.part(T_NONE, 0, "body"):
                c = Vector((0.0, yc + dy, G + 0.705 + 0.002 * k))
                lathe_on(bm, [(0.015, fx + 0.072), (0.021, fx + 0.076), (0.021, fx + 0.089),
                              (0.017, fx + 0.092)], 16, ANOD_IDX, c, XAX)
                lathe_on(bm, [(0.012, fx + 0.086), (0.0145, fx + 0.093), (0.011, fx + 0.098),
                              (0.005, fx + 0.1005)], 12, GLASS_IDX, c, XAX)
    # radiator banks either side of the power unit
    rx = BODY_CX - BODY_HX
    for s in (1.0, -1.0):
        with b.part(T_NONE, 0, "body", bevel=True):
            add_box(bm, (rx - 0.004, s * 0.42, G + 0.85), (0.012, 0.145, 0.195),
                    frame(ZAX, XAX), ANOD_IDX, rc=0.008, c=0.003)
        for k in range(8):
            with b.part(T_NONE, 0, "body"):
                depth = 0.030 + 0.0015 * k
                z0, z1 = G + 0.675 + 0.0017 * k, G + 1.025 - 0.0023 * k
                add_rbox(bm, depth, 0.0026, 0.0018, box_profile(z0, z1, 0.0012),
                         (rx - 0.002 - 0.0011 * k - depth, s * (0.302 + 0.0335 * k), 0.0),
                         Matrix.Identity(3), PAINT_IDX, n_corner=1)
    add_rtg(b)
    add_deck(b)


def add_rtg(b):
    bm = b.bm
    q, d = RTG_Q, RTG_D
    e1 = (XAX - d * XAX.dot(d)).normalized()
    e2 = d.cross(e1)
    with b.part(T_NONE, 0, "body", bevel=True):
        lathe_on(bm, [(0.060, -0.020), (0.100, -0.012), (0.118, 0.0), (0.118, 0.030),
                      (0.130, 0.036), (0.130, 0.060), (0.124, 0.066), (0.124, 0.554),
                      (0.130, 0.560), (0.130, 0.584), (0.118, 0.590), (0.118, 0.620),
                      (0.100, 0.632), (0.060, 0.640)], 20, ANOD_IDX, q, d, ref=e1)
    for k in range(8):
        ang = math.radians(22.5 + 45.0 * k)
        ek = e1 * math.cos(ang) + e2 * math.sin(ang)
        with b.part(T_NONE, 0, "body"):
            add_rbox(bm, 0.082, 0.005, 0.004, [(0.004, 0.075), (0.0, 0.082), (0.0, 0.538),
                                                (0.004, 0.545)],
                     q + ek * 0.190, frame(d, ek), ANOD_IDX, n_corner=1)
    # two struts through the fins' gap to the body's rear face, a bearer below
    rx = BODY_CX - BODY_HX
    for w in (0.10, 0.30):
        a = q + d * w
        t = (rx + 0.012 - a.x) / e1.x
        with b.part(T_NONE, 0, "body"):
            tube(bm, a, a + e1 * t, 0.021, TITAN_IDX, sides=12)
        with b.part(T_NONE, 0, "body", bevel=True):
            end = a + e1 * t
            lathe_on(bm, [(0.030, -0.006), (0.036, -0.002), (0.036, 0.010), (0.030, 0.014)], 16,
                     ANOD_IDX, end - e1 * 0.0, -e1)
    # power cable from the unit's foot into the body
    with b.part(T_NONE, 0, "body"):
        p0 = q + d * 0.02 + e2 * 0.07
        add_sweep(bm, fillet_path([p0, p0 + Vector((0.10, 0.02, -0.08)),
                                   Vector((rx + 0.05, 0.12, G + 0.64))], 0.06, 4),
                  0.012, 8, HARNESS_IDX)


def add_deck(b):
    bm = b.bm
    ident = Matrix.Identity(3)
    # instrument boxes
    with b.part(T_NONE, 0, "body", bevel=True):
        add_rbox(bm, 0.19, 0.15, 0.025, box_profile(FOOT_Z + 0.001, G + 1.225, 0.006),
                 (0.16, 0.30, 0.0), ident, FOIL_IDX, n_corner=2)
        add_rbox(bm, 0.13, 0.11, 0.018, box_profile(FOOT_Z + 0.002, G + 1.192, 0.005),
                 (0.20, -0.20, 0.0), ident, PAINT_IDX, n_corner=2)
        add_rbox(bm, 0.10, 0.09, 0.018, box_profile(FOOT_Z + 0.003, G + 1.172, 0.005),
                 (-0.47, -0.20, 0.0), ident, FOIL_IDX, n_corner=2)
    with b.part(T_NONE, 0, "body", bevel=True):
        add_rbox(bm, 0.12, 0.13, 0.018, box_profile(FOOT_Z + 0.004, G + 1.198, 0.005),
                 (0.66, 0.33, 0.0), ident, PAINT_IDX, n_corner=2)
    for k, (dx, dy) in enumerate(((-0.05, -0.05), (0.05, 0.06))):
        with b.part(T_NONE, 0, "body"):
            add_rbox(bm, 0.040, 0.034, 0.008, box_profile(G + 1.194 + 0.001 * k,
                                                          G + 1.207 + 0.001 * k, 0.003),
                     (0.66 + dx, 0.33 + dy, 0.0), ident, ANOD_IDX, n_corner=1)
    # panel seams across the deck
    for k, xs in enumerate((0.44, -0.32)):
        with b.part(T_NONE, 0, "body"):
            add_rbox(bm, 0.006 + 0.0005 * k, BODY_HY + 0.004, 0.003,
                     box_profile(DECK_Z - 0.004, DECK_Z + 0.004 + 0.0004 * k, 0.002),
                     (xs, 0.0, 0.0), ident, ANOD_IDX, n_corner=1)
    # calibration target: a plate with a gnomon on a post
    ct = Vector((0.43, -0.54, 0.0))
    with b.part(T_NONE, 0, "body", bevel=True):
        lathe_on(bm, [(0.014, FOOT_Z + 0.0105), (0.016, G + 1.125), (0.012, G + 1.132),
                      (0.012, G + 1.203)], 12, ANOD_IDX, ct, ZAX)
    tilt = frame(Vector((0.25, -0.20, 1.0)), XAX)
    with b.part(T_NONE, 0, "body"):
        add_rbox(bm, 0.048, 0.048, 0.008, box_profile(-0.004, 0.004, 0.0015),
                 ct + ZAX * (G + 1.200), tilt, PAINT_IDX, n_corner=2)
    with b.part(T_NONE, 0, "body"):
        lathe_on(bm, [(0.032, 0.002), (0.036, 0.0035), (0.036, 0.006), (0.032, 0.0075)], 20,
                 ANOD_IDX, ct + ZAX * (G + 1.200), tilt @ ZAX, solid=False)
        lathe_on(bm, [(0.0035, 0.0), (0.0035, 0.034), (0.0015, 0.037)], 8, ALU_IDX,
                 ct + ZAX * (G + 1.200), tilt @ ZAX)
    # cables along the deck
    zc = DECK_Z + 0.006
    for pts in ([(0.53, -0.36, zc), (0.42, -0.30, zc), (0.33, -0.22, zc)],
                [(-0.44, 0.34, zc), (-0.30, 0.25, zc), (-0.08, 0.26, zc), (-0.02, 0.28, zc)],
                [(-0.58, -0.37, zc), (-0.56, -0.27, zc), (-0.52, -0.25, zc)]):
        with b.part(T_NONE, 0, "body"):
            add_sweep(bm, fillet_path([Vector(p) for p in pts], 0.06, 3), 0.008, 6,
                      HARNESS_IDX)
    # sample inlets with lids, a funnel
    for k, (x, y) in enumerate(((0.07, 0.36), (0.22, 0.36))):
        with b.part(T_NONE, 0, "body", bevel=True):
            lathe_on(bm, [(0.028, G + 1.215), (0.034, G + 1.219), (0.034, G + 1.244 + 0.002 * k),
                          (0.030, G + 1.248 + 0.002 * k)], 20, ANOD_IDX, (x, y, 0.0), ZAX)
        with b.part(T_NONE, 0, "body"):
            add_box(bm, (x - 0.012, y, G + 1.262 + 0.002 * k), (0.030, 0.038, 0.006),
                    frame(Vector((0.36, 0.0, 0.93)), XAX), PAINT_IDX, rc=0.006, c=0.002)
    with b.part(T_NONE, 0, "body"):
        lathe_on(bm, [(0.020, G + 1.180), (0.026, G + 1.186), (0.052, G + 1.232),
                      (0.056, G + 1.240), (0.050, G + 1.244), (0.024, G + 1.206)], 20,
                 ALU_IDX, (0.24, -0.22, 0.0), ZAX, solid=False)
    # differential pedestal
    with b.part(T_NONE, 0, "body", bevel=True):
        lathe_on(bm, [(0.075, FOOT_Z + 0.004), (0.075, G + 1.127), (0.052, G + 1.137),
                      (0.042, G + 1.200), (0.032, BAR_Z - 0.024)], 20, ANOD_IDX,
                 (PIV_X, 0.0, 0.0), ZAX)
    # UHF can, low-gain whip
    with b.part(T_NONE, 0, "body", bevel=True):
        lathe_on(bm, [(0.050, FOOT_Z + 0.005), (0.054, G + 1.126), (0.054, G + 1.198),
                      (0.046, G + 1.214), (0.022, G + 1.224)], 20, PAINT_IDX, (-0.66, 0.05, 0.0),
                 ZAX)
    with b.part(T_NONE, 0, "body", bevel=True):
        lathe_on(bm, [(0.036, FOOT_Z + 0.006), (0.036, G + 1.127), (0.023, G + 1.137),
                      (0.018, G + 1.190), (0.012, G + 1.196)], 16, ANOD_IDX, (-0.62, -0.40, 0.0),
                 ZAX)
    with b.part(T_NONE, 0, "body"):
        lathe_on(bm, [(0.0055, G + 1.186), (0.0065, G + 1.191), (0.0045, G + 1.690),
                      (0.0040, G + 1.695)], 8, ALU_IDX, (-0.62, -0.40, 0.0), ZAX)
        lathe_on(bm, [(0.004, G + 1.683), (0.010, G + 1.689), (0.011, G + 1.697),
                      (0.008, G + 1.705), (0.003, G + 1.709)], 10, ANOD_IDX, (-0.62, -0.40, 0.0),
                 ZAX)


# --------------------------------------------------------------------------
# Suspension and wheels
# --------------------------------------------------------------------------

STEER_PROF = [(0.060, 0.290), (0.074, 0.292), (0.076, 0.300), (0.076, 0.312), (0.066, 0.316),
              (0.064, 0.462), (0.057, 0.476), (0.040, 0.484)]
ACT_PROF = [(0.050, 0.885), (0.058, 0.890), (0.058, 0.934), (0.064, 0.939), (0.064, 0.953),
            (0.052, 0.966), (0.052, 1.315)]
HUB_PROF = [(0.040, 1.300), (0.070, 1.302), (0.085, 1.310), (0.085, 1.338), (0.078, 1.3485),
            (0.060, 1.356), (0.030, 1.362)]
DRUM_PROF = [(0.2445, -0.186), (0.2445, 0.186), (0.2275, 0.190), (0.2275, 0.1985),
             (0.2475, 0.2000), (0.2475, -0.2000), (0.2275, -0.1985), (0.2275, -0.190)]


def add_wheel_station(b, s, k, grp):
    """A wheel on its drive actuator, and for a corner wheel the steering
    actuator and C-bracket above it, all in the rest pose."""
    bm = b.bm
    xw = WHEEL_X[k]
    u = k + (0 if s > 0 else 3)
    wg = f"wheel{u}"
    axis = Vector((0.0, s, 0.0))
    c_ax = Vector((xw, 0.0, ZC0))
    if k != 1:
        with b.part(T_STEER, u, grp, f"steer{u}", bevel=True):
            lathe_on(bm, [(r, ZC0 + z) for r, z in STEER_PROF], 16, ANOD_IDX,
                     (xw, s * WHEEL_Y, 0.0), ZAX)
        with b.part(T_NONE, 0, grp, bevel=True):
            zt = ZC0 + 0.283
            add_bar(bm, [(xw, s * WHEEL_Y, zt), (xw, s * 0.905, zt), (xw, s * 0.905, ZC0 - 0.04)],
                    XAX, 0.042, 0.011, 0.005, ANOD_IDX, fillet=0.05, steps=4)
        with b.part(T_NONE, 0, grp):
            # the steering actuator's connector
            add_box(bm, (xw - 0.070, s * (WHEEL_Y - 0.035), ZC0 + 0.41), (0.018, 0.026, 0.030),
                    frame(ZAX, XAX), PAINT_IDX, rc=0.006, c=0.002)
    else:
        with b.part(T_NONE, 0, grp, bevel=True):
            add_box(bm, (xw, s * 0.873, ZC0 + 0.035), (0.058, 0.029, 0.078), frame(ZAX, XAX),
                    ANOD_IDX, rc=0.012, c=0.004)
    with b.part(T_NONE, 0, grp, bevel=True):
        lathe_on(bm, ACT_PROF, 16, ANOD_IDX, c_ax, axis)
    with b.part(T_HUB, u, grp, wg, bevel=True):
        lathe_on(bm, HUB_PROF, 16, ALU_IDX, c_ax, axis)
    with b.part(T_DRUM, u, grp, wg):
        lathe_on(bm, [(r, WHEEL_Y + w) for r, w in DRUM_PROF], DRUM_SEGS, ALU_IDX, c_ax, axis,
                 solid=False)
    # curved flexure spokes, hub to the outer lip
    for n in range(N_SPOKE):
        th0 = 2.0 * math.pi * n / N_SPOKE + 0.30
        yc = s * (WHEEL_Y + 0.187 + 0.0002 * n)
        pts = []
        for i in range(4):
            t = i / 3.0
            rho = 0.070 + (0.238 - 0.070) * t
            th = th0 + 0.34 * math.sin(math.pi * t) + 0.10 * t
            pts.append(Vector((xw + rho * math.cos(th), yc, ZC0 + rho * math.sin(th))))
        with b.part(T_SPOKE, u, grp, wg):
            add_bar(bm, pts, YAX, 0.011, 0.0055, 0.003, TITAN_IDX, filleted=True)
    # chevron grousers on the skin
    ys = [-0.186, 0.0, 0.186]
    r0, r1, ch = R_SKIN - GR_BITE, R_TIP, 0.0015
    sec = [(-GR_W, r0), (GR_W, r0), (GR_W, r1 - ch), (GR_W - ch, r1), (-GR_W + ch, r1),
           (-GR_W, r1 - ch)]
    for n in range(N_GR):
        th_n = 2.0 * math.pi * n / N_GR
        stag = 0.0003 * (n % 3)
        rings = []
        for yy in ys:
            yv = yy + (math.copysign(stag, yy) if abs(yy) > 0.1 else 0.0)
            th = th_n + CHEV * abs(yv) / 0.186
            ring = []
            for tt, rr in sec:
                a = th + tt / R_SKIN
                ring.append(Vector((xw + rr * math.cos(a), s * (WHEEL_Y + yv),
                                    ZC0 + rr * math.sin(a))))
            rings.append(ring)
        with b.part(T_GROUSER, u, grp, wg, f"gr{u}", f"gr{u}_{n}"):
            add_loft(bm, rings, ALU_IDX)


def harness_along(bm, pts, r_host, r_h=0.009, bite=0.003):
    """A cable laid along the top of a tube path."""
    out = []
    n = len(pts)
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        c = pts[min(i + 1, n - 1)]
        t = (c - a).normalized()
        up = (ZAX - t * ZAX.dot(t)).normalized()
        out.append(p + up * (r_host + r_h - bite))
    out[0] = out[0] + (out[1] - out[0]).normalized() * 0.005
    out[-1] = out[-1] + (out[-2] - out[-1]).normalized() * 0.005
    add_sweep(bm, out, r_h, 6, HARNESS_IDX)
    return out


def add_clip(bm, p, t, up, r_host, r_h=0.009):
    """A P-clip strapping a cable to its tube."""
    c = p + up * (r_host + 0.5 * r_h)
    add_box(bm, c, (0.010, 0.016, r_h + 0.004), frame(up, t), ANOD_IDX, rc=0.005, c=0.002,
            n_corner=1)


def add_side(b, s):
    bm = b.bm
    piv, bog = pivots(s)
    rk, bg = f"rk{s:+.0f}", f"bg{s:+.0f}"
    ju_r = 1 if s > 0 else 2
    ju_b = 3 if s > 0 else 4
    ax = Vector((0.0, s, 0.0))
    pc = Vector((PIV_X, 0.0, PIV_Z))
    bc = Vector((BOG_X, 0.0, BOG_Z))
    # rocker pivot: a boss in the body side, the rocker's eye, a pin through both
    with b.part(T_BUSH, ju_r, "body", bevel=True):
        lathe_on(bm, [(0.050, 0.545), (0.070, 0.550), (0.075, 0.556), (0.075, 0.598),
                      (0.062, 0.604), (0.060, 0.652), (0.056, 0.658)], 16, ANOD_IDX, pc, ax)
    with b.part(T_BUSH, ju_r, rk, bevel=True):
        lathe_on(bm, [(0.056, 0.664), (0.064, 0.670), (0.064, 0.760), (0.056, 0.766)], 16,
                 ANOD_IDX, pc, ax)
    with b.part(T_PIN, ju_r, rk, f"pin{ju_r}"):
        lathe_on(bm, [(0.020, 0.560), (0.022, 0.564), (0.022, 0.762), (0.034, 0.762),
                      (0.036, 0.767), (0.036, 0.777), (0.030, 0.783)], 12, ALU_IDX, pc, ax)
    # differential crank above the pivot, its boss and pin
    with b.part(T_NONE, 0, rk, bevel=True):
        add_rbox(bm, 0.028, 0.020, 0.010, [(0.006, PIV_Z + 0.030), (0.0, PIV_Z + 0.040),
                                          (0.0, PIV_Z + 0.280), (0.006, PIV_Z + 0.290)],
                 (PIV_X, s * PIV_Y, 0.0), Matrix.Identity(3), TITAN_IDX, n_corner=2)
        lathe_on(bm, [(0.024, 0.690), (0.030, 0.694), (0.030, 0.736), (0.024, 0.740)], 16,
                 ANOD_IDX, pc + ZAX * CRANK_L, ax)
    with b.part(T_CRANKPIN, ju_r, rk):
        lathe_on(bm, [(0.020, 0.630), (0.024, 0.634), (0.024, 0.650), (0.013, 0.650),
                      (0.013, 0.733), (0.021, 0.733), (0.021, 0.748), (0.017, 0.752)], 12,
                 ALU_IDX, pc + ZAX * CRANK_L, ax)
    # rocker: rear leg to the rear steering actuator, front arm to the clevis
    rear = fillet_path([Vector((-0.17, s * 0.715, G + 0.862)), Vector((-0.50, s * 0.760, G + 0.740)),
                        Vector((-0.84, s * 0.980, G + 0.660)),
                        Vector((-0.975, s * 1.125, ZC0 + 0.370))], 0.12, 4)
    dirb = (bog - piv).normalized()
    front = [piv + dirb * 0.01, bog - dirb * 0.115]
    with b.part(T_NONE, 0, rk):
        add_sweep(bm, rear, 0.030, 10, TITAN_IDX)
        add_sweep(bm, front, 0.030, 10, TITAN_IDX, phase=0.13)
    perp = Vector((-dirb.z, 0.0, dirb.x))
    with b.part(T_NONE, 0, rk, bevel=True):
        add_box(bm, bog - dirb * 0.125, (0.075, 0.042, 0.045), frame(dirb, YAX), ANOD_IDX,
                rc=0.012, c=0.004)
        base = []
        for dd in (0.150, 0.095):
            for w in (-0.034, 0.034):
                q = bog - dirb * dd + perp * w
                base.append((q.x, q.z))
        outline = hull2d(circle_pts(bog.x, bog.z, 0.045, 12) + base)
        for y0, y1 in ((0.641, 0.672), (0.758, 0.789)):
            a, c = sorted((s * y0, s * y1))
            add_plate_xz(bm, outline, a, c, ANOD_IDX)
    for prof in ([(0.050, 0.638), (0.058, 0.642), (0.058, 0.675), (0.050, 0.679)],
                 [(0.050, 0.751), (0.058, 0.755), (0.058, 0.788), (0.050, 0.792)]):
        with b.part(T_BUSH, ju_b, rk, bevel=True):
            lathe_on(bm, prof, 16, ANOD_IDX, bc, ax)
    with b.part(T_PIN, ju_b, rk, f"pin{ju_b}"):
        lathe_on(bm, [(0.027, 0.620), (0.032, 0.625), (0.032, 0.644), (0.018, 0.644),
                      (0.018, 0.786), (0.032, 0.786), (0.032, 0.805), (0.027, 0.810)], 12,
                 ALU_IDX, bc, ax)
    # bogie: its eye, a rear leg to the middle wheel's mount, a front leg to
    # the front steering actuator
    with b.part(T_BUSH, ju_b, bg, bevel=True):
        lathe_on(bm, [(0.048, 0.685), (0.055, 0.689), (0.055, 0.741), (0.048, 0.745)], 16,
                 ANOD_IDX, bc, ax)
    brear = fillet_path([bog + Vector((-0.02, 0.0, -0.01)), Vector((0.34, s * 0.740, G + 0.500)),
                         Vector((0.14, s * 0.820, ZC0 + 0.200)),
                         Vector((0.06, s * 0.868, ZC0 + 0.090))], 0.10, 4)
    bfront = fillet_path([bog + Vector((0.02, 0.0, 0.0)), Vector((0.78, s * 0.800, G + 0.600)),
                          Vector((0.97, s * 1.060, ZC0 + 0.370)),
                          Vector((1.025, s * 1.125, ZC0 + 0.370))], 0.10, 4)
    with b.part(T_NONE, 0, bg):
        add_sweep(bm, brear, 0.027, 10, TITAN_IDX, phase=0.21)
        add_sweep(bm, bfront, 0.027, 10, TITAN_IDX, phase=0.07)
    # wheels
    add_wheel_station(b, s, 2, rk)
    add_wheel_station(b, s, 0, bg)
    add_wheel_station(b, s, 1, bg)
    # harnesses along every leg, strapped with clips
    for path, r_host, grp in ((rear, 0.030, rk), (brear, 0.027, bg), (bfront, 0.027, bg)):
        with b.part(T_NONE, 0, grp):
            harness_along(bm, path, r_host)
        for f in (0.35, 0.70):
            i = int(len(path) * f)
            t = (path[i + 1] - path[i - 1]).normalized()
            up = (ZAX - t * ZAX.dot(t)).normalized()
            with b.part(T_NONE, 0, grp):
                add_clip(bm, path[i], t, up, r_host)
    front_h = [piv + dirb * 0.02 + Vector((0.0, s * 0.0, 0.0)), bog - dirb * 0.12]
    with b.part(T_NONE, 0, rk):
        harness_along(bm, [front_h[0].lerp(front_h[1], t / 6.0) for t in range(7)], 0.030)


def pose_side(b, s, jam=False):
    ar, ab = side_angles(s, jam)
    piv, bog = pivots(s)
    rk, bg = f"rk{s:+.0f}", f"bg{s:+.0f}"
    mb = Matrix.Rotation(ab, 3, "Y")
    for v in b.verts(bg):
        v.co = bog + mb @ (v.co - bog)
    mr = Matrix.Rotation(ar, 3, "Y")
    for v in b.verts(rk, bg):
        v.co = piv + mr @ (v.co - piv)


def add_differential(b):
    """The bar on the deck and a link from each end to its rocker's crank,
    built for the nominal equal-and-opposite deflection."""
    bm = b.bm
    a = math.radians(ROCKER_DEG)
    phi = -math.asin(CRANK_L * math.sin(a) / BAR_Y)
    bdir = Vector((-math.sin(phi), math.cos(phi), 0.0))
    with b.part(T_NONE, 0, "diff", bevel=True):
        lathe_on(bm, [(0.036, BAR_Z - 0.030), (0.045, BAR_Z - 0.026), (0.045, BAR_Z + 0.026),
                      (0.036, BAR_Z + 0.030)], 20, ANOD_IDX, (PIV_X, 0.0, 0.0), ZAX)
    with b.part(T_NONE, 0, "diff"):
        add_rbox(bm, 0.018, 0.022, 0.008, [(0.006, -0.470), (0.0, -0.462), (0.0, 0.462),
                                          (0.006, 0.470)],
                 (PIV_X, 0.0, BAR_Z), frame(bdir, ZAX), PAINT_IDX, n_corner=2)
        lathe_on(bm, [(0.018, BAR_Z + 0.026), (0.024, BAR_Z + 0.036), (0.012, BAR_Z + 0.044)],
                 16, ANOD_IDX, (PIV_X, 0.0, 0.0), ZAX)
    for s in (1.0, -1.0):
        ju = 1 if s > 0 else 2
        tip = rot_y(Vector((PIV_X, 0.0, PIV_Z + CRANK_L)), Vector((PIV_X, 0.0, PIV_Z)), s * a)
        end = Vector((PIV_X, 0.0, BAR_Z)) + bdir * (s * BAR_Y)
        with b.part(T_NONE, 0, "diff", bevel=True):
            lathe_on(bm, [(0.024, BAR_Z - 0.030), (0.031, BAR_Z - 0.026), (0.031, BAR_Z + 0.026),
                          (0.024, BAR_Z + 0.030)], 16, ANOD_IDX, (end.x, end.y, 0.0), ZAX)
        with b.part(T_LINKEYE, ju, "diff", bevel=True):
            lathe_on(bm, [(0.022, 0.645), (0.028, 0.649), (0.028, 0.680), (0.022, 0.684)], 16,
                     ANOD_IDX, tip, Vector((0.0, s, 0.0)))
        start = Vector((tip.x, s * LINK_Y, tip.z))
        ld = (end - start).normalized()
        with b.part(T_NONE, 0, "diff"):
            add_sweep(bm, [start, end], 0.012, 10, TITAN_IDX)
            lathe_on(bm, [(0.014, -0.075), (0.020, -0.068), (0.020, -0.012), (0.016, -0.004)],
                     12, ANOD_IDX, end, ld)


# --------------------------------------------------------------------------
# Mast, arm, antennas
# --------------------------------------------------------------------------

def mast_frame():
    look = Vector((math.cos(HEAD_AZ), math.sin(HEAD_AZ), 0.0))
    lat = ZAX.cross(look)
    lk = look * math.cos(HEAD_PITCH) + ZAX * math.sin(HEAD_PITCH)
    up = ZAX * math.cos(HEAD_PITCH) - look * math.sin(HEAD_PITCH)
    return look, lat, lk, up


def add_mast(b):
    bm = b.bm
    m = Vector((MAST_X, MAST_Y, 0.0))
    look, lat, lk, up = mast_frame()
    with b.part(T_NONE, 0, "body", bevel=True):
        lathe_on(bm, [(0.090, FOOT_Z + 0.007), (0.090, G + 1.126), (0.070, G + 1.136),
                      (0.066, G + 1.182), (0.058, G + 1.188)], 24, ANOD_IDX, m, ZAX)
    with b.part(T_MAST, 0, "mast"):
        lathe_on(bm, [(0.044, G + 1.150), (0.048, G + 1.156), (0.048, G + 1.835),
                      (0.044, G + 1.841)], 20, PAINT_IDX, m, ZAX)
    with b.part(T_NONE, 0, "mast", bevel=True):
        for z in (G + 1.40, G + 1.52, G + 1.66):
            lathe_on(bm, [(0.052, z - 0.013), (0.057, z - 0.009), (0.057, z + 0.009),
                          (0.052, z + 0.013)], 20, ANOD_IDX, m, ZAX)
        lathe_on(bm, [(0.060, G + 1.819), (0.074, G + 1.825), (0.078, G + 1.835),
                      (0.078, G + 1.892), (0.070, G + 1.901)], 24, ANOD_IDX, m, ZAX)
    # weather booms on the middle collar
    for k, (az, ln) in enumerate(((HEAD_AZ + math.radians(105.0), 0.20),
                                  (HEAD_AZ - math.radians(150.0), 0.17))):
        d = Vector((math.cos(az), math.sin(az), 0.0))
        zb = G + 1.52 + 0.002 * k
        with b.part(T_NONE, 0, "mast"):
            add_rbox(bm, 0.008 + 0.001 * k, 0.011, 0.004, [(0.002, 0.030), (0.0, 0.034),
                                                        (0.0, ln), (0.002, ln + 0.004)],
                     m + ZAX * zb, frame(d, ZAX), PAINT_IDX, n_corner=1)
            add_box(bm, m + ZAX * zb + d * (ln + 0.012), (0.018, 0.022, 0.016), frame(d, ZAX),
                    ANOD_IDX, rc=0.006, c=0.002)
    ax = m + ZAX * MAST_AX_Z
    with b.part(T_NONE, 0, "mast", bevel=True):
        add_bar(bm, [ax - lat * 0.20, ax - lat * 0.20 - ZAX * 0.087, ax + lat * 0.20 - ZAX * 0.087,
                     ax + lat * 0.20], look, 0.030, 0.010, 0.004, PAINT_IDX, fillet=0.03, steps=3)
    for sg in (1.0, -1.0):
        with b.part(T_NONE, 0, "mast", bevel=True):
            lathe_on(bm, [(0.026, 0.160), (0.031, 0.165), (0.031, 0.212 + 0.001 * sg),
                          (0.026, 0.217 + 0.001 * sg)], 16, ANOD_IDX, ax, lat * sg)
    hc = ax + lk * 0.02
    hrot = frame(up, lk)
    with b.part(T_NONE, 0, "mast", bevel=True):
        add_rbox(bm, 0.100, 0.170, 0.030, [(0.010, -0.085), (0.0, -0.075), (0.0, 0.075),
                                          (0.010, 0.085)], hc, hrot, PAINT_IDX, n_corner=3)
    with b.part(T_NONE, 0, "mast"):
        add_rbox(bm, 0.080, 0.145, 0.025, [(0.004, 0.078), (0.0, 0.082), (0.0, 0.090),
                                          (0.004, 0.094)], hc, hrot, FOIL_IDX, n_corner=3)

    def hp(w, l, h):
        return hc + lk * w + lat * l + up * h
    # laser telescope window
    with b.part(T_NONE, 0, "mast", bevel=True):
        lathe_on(bm, [(0.038, 0.094), (0.052, 0.096), (0.054, 0.108), (0.048, 0.114),
                      (0.038, 0.112)], 20, ANOD_IDX, hp(0.0, -0.055, 0.030), lk, ref=up,
                 solid=False)
    with b.part(T_NONE, 0, "mast"):
        lathe_on(bm, [(0.0395, 0.090), (0.0395, 0.105), (0.030, 0.1085), (0.012, 0.110)], 20,
                 GLASS_IDX, hp(0.0, -0.055, 0.030), lk, ref=up)
    # two camera barrels of different focal lengths
    for l, ln, rr, w0 in ((0.040, 0.062, 0.024, 0.088), (0.112, 0.094, 0.027, 0.091)):
        c = hp(0.0, l, -0.038)
        with b.part(T_NONE, 0, "mast", bevel=True):
            lathe_on(bm, [(rr - 0.004, w0), (rr, 0.094), (rr, 0.094 + ln),
                          (rr + 0.004, 0.098 + ln), (rr + 0.004, 0.108 + ln),
                          (rr, 0.111 + ln)], 20, ANOD_IDX, c, lk, ref=up)
        with b.part(T_NONE, 0, "mast"):
            lathe_on(bm, [(rr - 0.003, 0.104 + ln), (rr - 0.001, 0.112 + ln),
                          (rr - 0.008, 0.117 + ln)], 20, GLASS_IDX, c, lk, ref=up)
    # navigation camera pair on the head's lower corners
    for l in (-0.148, 0.148):
        c = hp(0.075, l, -0.060)
        with b.part(T_NONE, 0, "mast", bevel=True):
            add_box(bm, c, (0.032 + 0.001 * (l > 0), 0.024, 0.020), frame(up, lk), ANOD_IDX,
                    rc=0.006, c=0.002)
        with b.part(T_NONE, 0, "mast"):
            lathe_on(bm, [(0.010, 0.026), (0.013, 0.030), (0.013, 0.040), (0.008, 0.044)], 14,
                     GLASS_IDX, c, lk, ref=up)
    # cable up the back of the mast, clipped
    back = -look
    pts = [m + back * 0.062 + ZAX * (G + 1.098), m + back * 0.062 + ZAX * (G + 1.76),
           m + back * 0.040 + ZAX * (G + 1.859)]
    with b.part(T_NONE, 0, "mast"):
        add_sweep(bm, fillet_path(pts, 0.06, 4), 0.010, 8, HARNESS_IDX)
    for z in (G + 1.30, G + 1.75):
        with b.part(T_NONE, 0, "mast"):
            add_box(bm, m + back * 0.055 + ZAX * z, (0.014, 0.012, 0.010), frame(ZAX, back),
                    ANOD_IDX, rc=0.004, c=0.002)


def arm_points():
    s = ARM_S
    e = s + Vector((ARM_UP[0] * math.cos(ARM_UP[1]), 0.0, ARM_UP[0] * math.sin(ARM_UP[1])))
    w = e + Vector((ARM_FORE[0] * math.cos(ARM_FORE[1]), 0.0,
                    ARM_FORE[0] * math.sin(ARM_FORE[1])))
    t = w + Vector((TURRET_OFF, 0.0, 0.0))
    return s, e, w, t


def add_arm(b):
    bm = b.bm
    s, e, w, t = arm_points()
    fx = BODY_CX + BODY_HX
    with b.part(T_NONE, 0, "arm", bevel=True):
        add_box(bm, (fx + 0.020, s.y, G + 0.945), (0.070, 0.068, 0.048), frame(ZAX, XAX),
                PAINT_IDX, rc=0.014, c=0.004)
        lathe_on(bm, [(0.060, G + 0.902), (0.068, G + 0.907), (0.068, G + 0.990),
                      (0.060, G + 0.996)], 24, ANOD_IDX, (s.x, s.y, 0.0), ZAX)
        add_box(bm, (s.x, s.y, G + 1.018), (0.050, 0.052, 0.036), frame(ZAX, XAX), ANOD_IDX,
                rc=0.012, c=0.004)
    for p, prof in ((s, [(0.052, -0.085), (0.062, -0.078), (0.062, 0.078), (0.052, 0.085)]),
                    (e, [(0.048, -0.075), (0.056, -0.068), (0.056, 0.068), (0.048, 0.075)]),
                    (w, [(0.042, -0.065), (0.050, -0.058), (0.050, 0.058), (0.042, 0.065)])):
        with b.part(T_NONE, 0, "arm", bevel=True):
            lathe_on(bm, prof, 24, ANOD_IDX, p, YAX)
    with b.part(T_NONE, 0, "arm"):
        add_sweep(bm, [s, e], 0.040, 16, PAINT_IDX)
        add_sweep(bm, [e, w], 0.034, 16, PAINT_IDX, phase=0.1)
    with b.part(T_NONE, 0, "arm", bevel=True):
        add_box(bm, w + XAX * 0.060, (0.060, 0.036, 0.034), frame(ZAX, XAX), ANOD_IDX,
                rc=0.012, c=0.004)
        lathe_on(bm, [(0.045, 0.100), (0.052, 0.106), (0.052, 0.165), (0.045, 0.170)], 20,
                 ANOD_IDX, w, XAX, ref=ZAX)
    # the turret and its instruments
    with b.part(T_TURRET, 0, "arm", bevel=True):
        lathe_on(bm, [(0.060, -0.045), (0.078, -0.035), (0.078, 0.035), (0.060, 0.045)], 24,
                 ANOD_IDX, t, XAX, ref=ZAX)
    down = -ZAX
    with b.part(T_TURRET, 0, "arm", bevel=True):
        add_box(bm, t + down * 0.125, (0.055, 0.055, 0.072), frame(ZAX, XAX), PAINT_IDX,
                rc=0.014, c=0.004)
    with b.part(T_TURRET, 0, "arm"):
        lathe_on(bm, [(0.030, 0.170), (0.036, 0.175), (0.036, 0.250), (0.024, 0.262),
                      (0.020, 0.300)], 20, ANOD_IDX, t, down)
        lathe_on(bm, [(0.009, 0.290), (0.011, 0.295), (0.011, 0.345), (0.004, 0.360)], 12,
                 ALU_IDX, t, down)
        for dy in (-0.052, 0.052):
            add_sweep(bm, [t + down * 0.180 + YAX * dy, t + down * 0.352 + YAX * dy], 0.0065, 8,
                      ALU_IDX)
            lathe_on(bm, [(0.006, 0.344), (0.011, 0.348), (0.011, 0.356), (0.007, 0.359)], 12,
                     ANOD_IDX, t + YAX * dy, down)
    with b.part(T_TURRET, 0, "arm", bevel=True):
        lathe_on(bm, [(0.028, 0.070), (0.034, 0.075), (0.034, 0.160), (0.040, 0.165),
                      (0.040, 0.190), (0.030, 0.196)], 20, ANOD_IDX, t, YAX)
    with b.part(T_TURRET, 0, "arm"):
        lathe_on(bm, [(0.030, 0.188), (0.036, 0.194), (0.036, 0.202), (0.020, 0.204)], 20,
                 ALU_IDX, t, YAX)
    with b.part(T_TURRET, 0, "arm", bevel=True):
        add_box(bm, t + ZAX * 0.128, (0.060, 0.050, 0.062), frame(ZAX, XAX), PAINT_IDX,
                rc=0.014, c=0.004)
        lathe_on(bm, [(0.030, -0.070), (0.036, -0.066), (0.036, 0.066), (0.030, 0.070)], 20,
                 ALU_IDX, t + ZAX * 0.150 + XAX * 0.0, YAX, ref=XAX)
    with b.part(T_TURRET, 0, "arm"):
        add_bar(bm, [t + ZAX * 0.19 + XAX * 0.03, t + ZAX * 0.24 + XAX * 0.06,
                     t + ZAX * 0.24 + XAX * 0.13], YAX, 0.045, 0.004, 0.003, ALU_IDX,
                fillet=0.03, steps=3)
    with b.part(T_TURRET, 0, "arm", bevel=True):
        add_box(bm, t - YAX * 0.118, (0.036, 0.050, 0.042), frame(ZAX, XAX), PAINT_IDX,
                rc=0.010, c=0.003)
    with b.part(T_TURRET, 0, "arm"):
        lathe_on(bm, [(0.018, 0.160), (0.023, 0.165), (0.023, 0.182), (0.018, 0.186)], 18,
                 ANOD_IDX, t, -YAX)
        lathe_on(bm, [(0.0155, 0.178), (0.0165, 0.186), (0.010, 0.190)], 18, GLASS_IDX, t, -YAX)
    # cable along the arm's side, with a service loop at the elbow
    side = YAX * 0.050
    pts = [s + side + XAX * 0.02, s.lerp(e, 0.5) + side + ZAX * 0.030, e + side + Vector((-0.07, 0, 0.06)),
           e + side + Vector((0.06, 0.0, 0.08)), e + side + Vector((0.07, 0.0, -0.06)),
           e.lerp(w, 0.5) + side + XAX * 0.030, w + side + Vector((-0.02, 0.0, 0.04))]
    with b.part(T_NONE, 0, "arm"):
        add_sweep(bm, fillet_path(pts, 0.05, 3), 0.009, 8, HARNESS_IDX)


def add_hga(b):
    bm = b.bm
    hx = Vector((HGA_X, HGA_Y, 0.0))
    az = Vector((math.cos(HGA_AZ), math.sin(HGA_AZ), 0.0))
    lat = ZAX.cross(az)
    n = az * math.cos(HGA_EL) + ZAX * math.sin(HGA_EL)
    ax = hx + ZAX * HGA_AX_Z
    with b.part(T_NONE, 0, "body", bevel=True):
        lathe_on(bm, [(0.070, FOOT_Z + 0.008), (0.070, G + 1.126), (0.050, G + 1.136),
                      (0.045, G + 1.200), (0.040, G + 1.206)], 20, ANOD_IDX, hx, ZAX)
        lathe_on(bm, [(0.052, G + 1.196), (0.064, G + 1.201), (0.066, G + 1.211),
                      (0.066, G + 1.271), (0.058, G + 1.279)], 24, ANOD_IDX, hx, ZAX)
        add_bar(bm, [ax - lat * 0.14, ax - lat * 0.14 - ZAX * 0.135, ax + lat * 0.14 - ZAX * 0.135,
                     ax + lat * 0.14], az, 0.028, 0.010, 0.004, PAINT_IDX, fillet=0.03, steps=3)
        lathe_on(bm, [(0.026, -0.158), (0.030, -0.154), (0.030, 0.154), (0.026, 0.158)], 16,
                 ANOD_IDX, ax, lat)
    # the dish: hub on the elevation axle, a paraboloid shell, three struts to the feed
    with b.part(T_DISH, 0, "dish", bevel=True):
        lathe_on(bm, [(0.035, -0.036), (0.048, -0.030), (0.050, 0.020), (0.074, 0.074),
                      (0.074, 0.096), (0.062, 0.101)], 24, ANOD_IDX, ax, n, ref=lat)
    prof, mats = [], []
    rs = [0.055, 0.11, 0.17, 0.225, 0.27, DISH_R]
    for r in rs:
        prof.append((r, DISH_W0 + r * r / (4.0 * DISH_F)))
        mats.append(PAINT_IDX)
    wr = DISH_W0 + DISH_R ** 2 / (4.0 * DISH_F)
    prof += [(DISH_R + 0.006, wr + 0.002), (DISH_R + 0.008, wr - 0.008)]
    mats += [PAINT_IDX, PAINT_IDX]
    for r in reversed(rs):
        prof.append((r, DISH_W0 + r * r / (4.0 * DISH_F) - 0.012 + 0.002 * (r / DISH_R)))
        mats.append(FOIL_IDX)
    mats[-1] = PAINT_IDX
    with b.part(T_DISH, 0, "dish"):
        lathe_on(bm, prof, 32, PAINT_IDX, ax, n, ref=lat, solid=False, seg_mats=mats)
    with b.part(T_DISH, 0, "dish"):
        lathe_on(bm, [(0.016, 0.228), (0.022, 0.233), (0.030, 0.262), (0.034, 0.276),
                      (0.034, 0.290), (0.026, 0.296)], 16, ANOD_IDX, ax, n, ref=lat)
    e1 = lat
    e2 = n.cross(e1)
    for k in range(3):
        ang = math.radians(90.0 + 120.0 * k)
        rad = e1 * math.cos(ang) + e2 * math.sin(ang)
        p0 = ax + n * (DISH_W0 + 0.287 ** 2 / (4.0 * DISH_F) + 0.002) + rad * 0.287
        p1 = ax + n * 0.250 + rad * 0.018
        with b.part(T_DISH, 0, "dish"):
            add_sweep(bm, [p0, p1], 0.0055, 8, TITAN_IDX)


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

FLAG_NAMES = ("float_wheel", "offset_pin", "sink_grousers", "lean_mast", "jam_rocker",
              "offset_steer", "camber_wheel", "bunch_grousers", "loose_dish")


def build_rover_mesh(name, bevel_offset, bevel_segments, float_wheel=False, offset_pin=False,
                     sink_grousers=False, lean_mast=False, jam_rocker=False, offset_steer=False,
                     camber_wheel=False, bunch_grousers=False, loose_dish=False):
    bm = bmesh.new()
    try:
        b = Build(bm)
        add_body(b)
        for s in (1.0, -1.0):
            add_side(b, s)
            pose_side(b, s, jam_rocker)
        add_differential(b)
        add_mast(b)
        add_arm(b)
        add_hga(b)
        centres = wheel_centres(jam_rocker)
        field = Regolith(centres)
        add_regolith(b, field)
        t = arm_points()[3]
        add_rocks(b, field, (t.x, t.y))

        # falsifiers that move one finished assembly
        fw = FALSIFY_WHEEL
        wc = centres[fw]
        if float_wheel:
            for v in b.verts(f"wheel{FLOAT_UNIT}"):
                v.co.z += FLOAT_WHEEL
        if offset_pin:
            for v in b.verts("pin4"):
                v.co.x += OFFSET_PIN
        if sink_grousers:
            for v in b.verts(f"gr{fw}"):
                r = Vector((v.co.x - wc.x, 0.0, v.co.z - wc.z))
                v.co -= r.normalized() * SINK_GROUSERS
        if lean_mast:
            m = Matrix.Rotation(math.radians(LEAN_MAST_DEG), 3, "X")
            foot = Vector((MAST_X, MAST_Y, G + 1.15))
            for v in b.verts("mast"):
                v.co = foot + m @ (v.co - foot)
        if offset_steer:
            for v in b.verts(f"steer{fw}"):
                v.co.x += OFFSET_STEER
        if camber_wheel:
            m = Matrix.Rotation(math.radians(CAMBER_DEG), 3, "X")
            for v in b.verts(f"wheel{fw}"):
                v.co = wc + m @ (v.co - wc)
        if bunch_grousers:
            m = Matrix.Rotation(math.radians(BUNCH_DEG), 3, "Y")
            for v in b.verts(f"gr{fw}_0"):
                v.co = wc + m @ (v.co - wc)
        if loose_dish:
            az = Vector((math.cos(HGA_AZ), math.sin(HGA_AZ), 0.0))
            n = az * math.cos(HGA_EL) + ZAX * math.sin(HGA_EL)
            for v in b.verts("dish"):
                v.co += n * LOOSE_DISH

        if bevel_offset > 0.0:
            for mat_idx in (ANOD_IDX, PAINT_IDX):
                bm.edges.index_update()
                edges = sorted(
                    {e for v in b.bevel if v.is_valid for e in v.link_edges
                     if len(e.link_faces) == 2
                     and all(f.material_index == mat_idx for f in e.link_faces)
                     and e.calc_face_angle() > math.radians(35.0)},
                    key=lambda e: e.index,
                )
                if edges:
                    bmesh.ops.bevel(bm, geom=edges, offset=bevel_offset,
                                    segments=bevel_segments, profile=0.5, affect="EDGES",
                                    clamp_overlap=True, material=mat_idx)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-7)
        triangulate_ngons(bm)
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z -= zmin
            if v.co.z < 0.0:
                v.co.z = 0.0

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = face.material_index != ROCK_IDX
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(50.0)
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
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = stretch
            nt.links.new(coord.outputs["Object"], mp.inputs["Vector"])
            nt.links.new(mp.outputs["Vector"], noise.inputs["Vector"])
        else:
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


def metal(name, color, roughness, env, stops, interp="EASE", roughness_var=0.04,
          noise_scale=40.0, stretch=None):
    """Metal with a studio carried in the material (copied from
    showcase/road-bicycle). On a dark stage a metal mirrors the dark stage
    and reads as grey plastic; here the world-space reflection vector looks
    up a soft studio — a bright horizon band, a dim ceiling, the floor dark
    only straight down, the key's side brighter — added as emission, so
    aluminium and foil read as metal in the hero and on the asset sheet."""
    mat = principled(name, color, 1.0, roughness, roughness_var=roughness_var,
                     noise_scale=noise_scale, stretch=stretch)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    out = nt.nodes["Material Output"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Reflection"], sep.inputs[0])
    mz = nt.nodes.new("ShaderNodeMapRange")
    mz.inputs["From Min"].default_value = -1.0
    mz.inputs["From Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], mz.inputs["Value"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = interp
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (stops[0][1],) * 3 + (1.0,)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (stops[-1][1],) * 3 + (1.0,)
    for pos, val in stops[1:-1]:
        e = cr.elements.new(pos)
        e.color = (val, val, val, 1.0)
    nt.links.new(mz.outputs["Result"], ramp.inputs["Fac"])
    mx = nt.nodes.new("ShaderNodeMapRange")
    mx.inputs["From Min"].default_value = -1.0
    mx.inputs["From Max"].default_value = 1.0
    mx.inputs["To Min"].default_value = 1.0
    mx.inputs["To Max"].default_value = 0.40
    nt.links.new(sep.outputs["X"], mx.inputs["Value"])
    side = nt.nodes.new("ShaderNodeMath")
    side.operation = "MULTIPLY"
    nt.links.new(mx.outputs["Result"], side.inputs[0])
    side.inputs[1].default_value = env
    tint = nt.nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1.0
    tint.inputs[2].default_value = color
    nt.links.new(ramp.outputs["Color"], tint.inputs[1])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tint.outputs[0], em.inputs["Color"])
    nt.links.new(side.outputs["Value"], em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(bsdf.outputs["BSDF"], add.inputs[0])
    nt.links.new(em.outputs["Emission"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
    return mat


def _math(nt, op, a, b):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    for i, v in enumerate((a, b)):
        if isinstance(v, (int, float)):
            node.inputs[i].default_value = v
        else:
            nt.links.new(v, node.inputs[i])
    return node.outputs[0]


def add_bump(nt, height, strength, distance):
    bsdf = nt.nodes["Principled BSDF"]
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def foil_material():
    mat = metal("GoldFoil", (0.95, 0.70, 0.33, 1.0), 0.22, 1.15,
                [(0.0, 0.02), (0.30, 0.06), (0.42, 0.55), (0.50, 0.85), (0.60, 0.35),
                 (0.80, 0.22), (1.0, 0.12)], roughness_var=0.10, noise_scale=30.0)
    nt = mat.node_tree
    coord = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 70.0
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    add_bump(nt, vor.outputs["Distance"], 0.45, 0.003)
    return mat


def regolith_material():
    mat = principled("Regolith", (0.33, 0.235, 0.18, 1.0), 0.0, 0.92, roughness_var=0.04,
                     mottle=0.24, noise_scale=3.5)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs[0])
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "RutMask"
    # tracks: the disturbed soil darker, and a chevron imprint every grouser pitch
    cur = bsdf.inputs["Base Color"].links[0].from_socket
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    nt.links.new(attr.outputs["Fac"], mix.inputs[0])
    nt.links.new(cur, mix.inputs[1])
    mix.inputs[2].default_value = (0.36, 0.35, 0.36, 1.0)
    # a finer mottle and a scatter of dark pebbles
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 13.0
    n2.inputs["Detail"].default_value = 3.0
    nt.links.new(coord.outputs["Object"], n2.inputs["Vector"])
    m2 = nt.nodes.new("ShaderNodeMapRange")
    m2.inputs["From Min"].default_value = 0.30
    m2.inputs["From Max"].default_value = 0.70
    m2.inputs["To Min"].default_value = 0.80
    m2.inputs["To Max"].default_value = 1.12
    nt.links.new(n2.outputs["Fac"], m2.inputs["Value"])
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 46.0
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    peb = nt.nodes.new("ShaderNodeMapRange")
    peb.inputs["From Min"].default_value = 0.0
    peb.inputs["From Max"].default_value = 0.20
    peb.inputs["To Min"].default_value = 1.0
    peb.inputs["To Max"].default_value = 0.0
    nt.links.new(vor.outputs["Distance"], peb.inputs["Value"])
    shade = _math(nt, "MULTIPLY", m2.outputs["Result"],
                  _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", peb.outputs["Result"], 0.40)))
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    for i in range(3):
        nt.links.new(shade, comb.inputs[i])
    mix2 = nt.nodes.new("ShaderNodeMixRGB")
    mix2.blend_type = "MULTIPLY"
    mix2.inputs[0].default_value = 1.0
    nt.links.new(mix.outputs[0], mix2.inputs[1])
    nt.links.new(comb.outputs[0], mix2.inputs[2])
    nt.links.new(mix2.outputs[0], bsdf.inputs["Base Color"])
    d = _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT", _math(nt, "ABSOLUTE", sep.outputs["Y"], 0.0),
                                    WHEEL_Y), 0.0)
    q = _math(nt, "DIVIDE", _math(nt, "ADD", sep.outputs["X"], _math(nt, "MULTIPLY", d, 0.16)),
              2.0 * math.pi * R_TIP / N_GR)
    fr = _math(nt, "FRACT", q, 0.0)
    ridge = _math(nt, "MINIMUM", _math(nt, "MULTIPLY", fr, 6.0),
                  _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 1.0, fr), 1.5))
    ridge = _math(nt, "MINIMUM", ridge, 1.0)
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 90.0
    grain.inputs["Detail"].default_value = 4.0
    nt.links.new(coord.outputs["Object"], grain.inputs["Vector"])
    h = _math(nt, "ADD", _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", ridge, attr.outputs["Fac"]),
                                1.0), _math(nt, "MULTIPLY", grain.outputs["Fac"], 0.35))
    h = _math(nt, "ADD", h, _math(nt, "MULTIPLY", peb.outputs["Result"], 0.5))
    add_bump(nt, h, 0.45, 0.008)
    return mat


def rock_material():
    mat = principled("Basalt", (0.19, 0.16, 0.145, 1.0), 0.0, 0.78, roughness_var=0.10,
                     mottle=0.35, noise_scale=26.0)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Tone"
    cur = bsdf.inputs["Base Color"].links[0].from_socket
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    tone = _math(nt, "ADD", _math(nt, "MULTIPLY", attr.outputs["Fac"], 0.45), 0.75)
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    for i in range(3):
        nt.links.new(tone, comb.inputs[i])
    nt.links.new(cur, mix.inputs[1])
    nt.links.new(comb.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], bsdf.inputs["Base Color"])
    coord = nt.nodes.new("ShaderNodeTexCoord")
    speck = nt.nodes.new("ShaderNodeTexNoise")
    speck.inputs["Scale"].default_value = 140.0
    nt.links.new(coord.outputs["Object"], speck.inputs["Vector"])
    add_bump(nt, speck.outputs["Fac"], 0.30, 0.004)
    return mat


def rover_materials():
    """Shared by the check and the render, in slot order."""
    paint = principled("CreamPaint", (0.70, 0.67, 0.60, 1.0), 0.0, 0.46, roughness_var=0.06,
                       mottle=0.05, noise_scale=30.0, coat=0.15)
    foil = foil_material()
    alu = metal("WheelAluminium", (0.74, 0.74, 0.76, 1.0), 0.42, 0.26,
                [(0.0, 0.03), (0.18, 0.05), (0.30, 0.20), (0.40, 0.60), (0.48, 1.0),
                 (0.60, 0.40), (0.80, 0.25), (1.0, 0.18)], roughness_var=0.06, noise_scale=60.0)
    anod = principled("DarkAnodised", (0.032, 0.033, 0.036, 1.0), 0.35, 0.36,
                      roughness_var=0.08, noise_scale=80.0, coat=0.25)
    titan = metal("Titanium", (0.52, 0.51, 0.49, 1.0), 0.44, 0.24,
                  [(0.0, 0.03), (0.30, 0.10), (0.42, 0.55), (0.50, 0.90), (0.62, 0.30),
                   (1.0, 0.15)], roughness_var=0.06, noise_scale=90.0)
    glass = metal("LensGlass", (0.16, 0.20, 0.34, 1.0), 0.05, 0.60,
                  [(0.0, 0.01), (0.40, 0.05), (0.50, 0.70), (0.58, 0.20), (1.0, 0.08)],
                  "LINEAR", roughness_var=0.01, noise_scale=90.0)
    harness = principled("HarnessWrap", (0.50, 0.42, 0.31, 1.0), 0.0, 0.66, roughness_var=0.08,
                         mottle=0.18, noise_scale=160.0, stretch=(1.0, 1.0, 8.0))
    regolith = regolith_material()
    rock = rock_material()
    return paint, foil, alu, anod, titan, glass, harness, regolith, rock


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


def zfight_pairs(me, groups, report=None):
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
            if report is not None:
                report.append((si, sj, tuple(round(x, 4) for x in ci), i, j))
    return hits


class Shell:
    def __init__(self, me, idx, verts, polys, tags, units):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.mean = sum(pts, Vector()) / len(pts)
        mats, tg = {}, {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
            key = (tags[p.index], units[p.index])
            tg[key] = tg.get(key, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        self.tag, self.unit = max(tg, key=tg.get) if tg else (T_NONE, 0)
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)


def pca(pts):
    """(mean, eigenvalues ascending, eigenvectors as columns)."""
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    w, vecs = np.linalg.eigh(q.T @ q / len(p))
    return Vector(c), w, vecs


def lathe_axis(pts):
    """A turned part's axis: the eigenvector whose eigenvalue stands apart
    from the other two (its radial pair is equal by symmetry)."""
    c, w, vecs = pca(pts)
    if (w[2] - w[1]) > (w[1] - w[0]):
        return c, Vector(vecs[:, 2]).normalized()
    return c, Vector(vecs[:, 0]).normalized()


def classify(me):
    groups = shells(me)
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(p)
    tags = [0] * len(me.polygons)
    units = [0] * len(me.polygons)
    if "part" in me.attributes:
        me.attributes["part"].data.foreach_get("value", tags)
        me.attributes["unit"].data.foreach_get("value", units)
    parts = [Shell(me, i, g, polys[i], tags, units) for i, g in enumerate(groups)]
    by = {}
    for s in parts:
        by.setdefault(s.tag, {}).setdefault(s.unit, []).append(s)
    return {"all": parts, "groups": groups, "by": by}


def tagged(cls, tag, unit=None):
    d = cls["by"].get(tag, {})
    if unit is None:
        return [s for u in sorted(d) for s in d[u]]
    return d.get(unit, [])


def line_dist(p, c, a):
    d = p - c
    return (d - a * d.dot(a)).length


def terrain_shell(cls):
    ts = tagged(cls, T_TERRAIN)
    return ts[0] if len(ts) == 1 else None


def ground_z(terrain, x, y):
    hit = terrain.tree.ray_cast(Vector((x, y, 50.0)), Vector((0.0, 0.0, -1.0)))
    return hit[0].z if hit[0] is not None else None


def sink_audit(cls):
    """Per wheel (drum and grousers): the deepest vertex below the regolith
    surface read off the terrain shell; and the vertices below it (the
    contact patch) for the stance audit."""
    ter = terrain_shell(cls)
    res = {"sink": [], "contacts": {}}
    if ter is None:
        return res
    for u in range(6):
        pts = [p for t in (T_DRUM, T_GROUSER) for s in tagged(cls, t, u) for p in s.pts]
        best, cont = -9.0, []
        for p in pts:
            if p.z > ter.hi.z:
                continue
            gz = ground_z(ter, p.x, p.y)
            if gz is None:
                continue
            d = gz - p.z
            best = max(best, d)
            if d > 0.0:
                cont.append(p)
        res["sink"].append(best if pts else -9.0)
        res["contacts"][u] = cont
    return res


def pin_audit(cls):
    """Every rocker and bogie pivot: one pin and its bushings (two at the
    rocker, three at the bogie), each bushing's centre on the pin's axis,
    its axis parallel to the pin's, and within the pin's span."""
    worst_off, worst_tilt, bad = 0.0, 0.0, []
    want = {1: 2, 2: 2, 3: 3, 4: 3}
    for u, nb in want.items():
        pins, bush = tagged(cls, T_PIN, u), tagged(cls, T_BUSH, u)
        if len(pins) != 1 or len(bush) != nb:
            bad.append((u, len(pins), len(bush)))
            continue
        pc, pa = lathe_axis(pins[0].pts)
        proj = [(p - pc).dot(pa) for p in pins[0].pts]
        lo, hi = min(proj), max(proj)
        for bsh in bush:
            bc, ba = lathe_axis(bsh.pts)
            r = bc - pc
            along = r.dot(pa)
            worst_off = max(worst_off, (r - pa * along).length)
            worst_tilt = max(worst_tilt, math.degrees(math.acos(min(1.0, abs(ba.dot(pa))))))
            if not (lo < along < hi):
                bad.append((u, "span", round(along, 4)))
    return {"offset": worst_off, "tilt": worst_tilt, "bad": bad}


def wheel_frame(cls, u):
    drums = tagged(cls, T_DRUM, u)
    if len(drums) != 1:
        return None
    c, a = lathe_axis(drums[0].pts)
    if a.y < 0.0:
        a = -a
    r_skin = max(line_dist(p, c, a) for p in drums[0].pts)
    e1 = (XAX - a * XAX.dot(a)).normalized()
    e2 = a.cross(e1)
    return c, a, r_skin, e1, e2, drums[0]


def grouser_audit(cls):
    """Every grouser's root inside the drum's skin (radius read off the
    drum) by a band, its crown proud of it; and the grousers' angular
    pitch round each wheel."""
    res = {"count": [], "bite": [9.0, -9.0], "proud": 9.0, "pitch": 0.0}
    for u in range(6):
        wf = wheel_frame(cls, u)
        grs = tagged(cls, T_GROUSER, u)
        res["count"].append(len(grs))
        if wf is None or not grs:
            res["bite"] = [-9.0, 9.0]
            res["pitch"] = 99.0
            continue
        c, a, r_skin, e1, e2, _d = wf
        angs = []
        for g in grs:
            rads = [line_dist(p, c, a) for p in g.pts]
            res["bite"][0] = min(res["bite"][0], r_skin - min(rads))
            res["bite"][1] = max(res["bite"][1], r_skin - min(rads))
            res["proud"] = min(res["proud"], max(rads) - r_skin)
            v = g.mean - c
            angs.append(math.atan2(v.dot(e2), v.dot(e1)))
        ts = sorted(angs)
        want = 360.0 / len(ts)
        for x, y in zip(ts, ts[1:] + [ts[0] + 2.0 * math.pi]):
            res["pitch"] = max(res["pitch"], abs(math.degrees(y - x) - want))
    return res


def mast_audit(cls):
    """Mast plumb (its tube's axis against vertical), and the rover's size:
    track width over the drums, length over every rover part, height from
    the wheels' contact plane (the mean of the six wheels' lowest points) to
    the top of the mast head."""
    res = {"tilt": 90.0, "track": 0.0, "length": 0.0, "height": 0.0}
    masts = tagged(cls, T_MAST)
    if len(masts) != 1:
        return res
    _c, a = lathe_axis(masts[0].pts)
    res["tilt"] = math.degrees(math.acos(min(1.0, abs(a.z))))
    drums = tagged(cls, T_DRUM)
    res["track"] = max(s.hi.y for s in drums) - min(s.lo.y for s in drums)
    rover = [s for s in cls["all"] if s.tag not in (T_TERRAIN, T_ROCK)]
    res["length"] = max(s.hi.x for s in rover) - min(s.lo.x for s in rover)
    bottoms = []
    for u in range(6):
        pts = [p.z for t in (T_DRUM, T_GROUSER) for s in tagged(cls, t, u) for p in s.pts]
        if pts:
            bottoms.append(min(pts))
    if len(bottoms) == 6:
        res["height"] = max(s.hi.z for s in rover) - sum(bottoms) / 6.0
    return res


def diff_audit(cls):
    """Each rocker's deflection, read off its crank pin's centre against its
    pivot pin's centre (the crank stands plumb when the rocker is neutral);
    equal and opposite; each link's eye on its crank pin's axis."""
    res = {"defl": [], "resid": 9.0, "link_off": 9.0}
    link_off = 0.0
    for u in (1, 2):
        pins, cps, eyes = tagged(cls, T_PIN, u), tagged(cls, T_CRANKPIN, u), tagged(cls,
                                                                                 T_LINKEYE, u)
        if len(pins) != 1 or len(cps) != 1 or len(eyes) != 1:
            return res
        pc, _pa = lathe_axis(pins[0].pts)
        cc, ca = lathe_axis(cps[0].pts)
        d = cc - pc
        res["defl"].append(math.degrees(math.atan2(d.x, d.z)))
        ec, _ea = lathe_axis(eyes[0].pts)
        link_off = max(link_off, line_dist(ec, cc, ca))
    res["resid"] = abs(res["defl"][0] + res["defl"][1])
    res["link_off"] = link_off
    return res


def steer_audit(cls):
    """Each corner wheel's steering actuator axis against its drum's centre."""
    worst, n = 0.0, 0
    for u in (0, 2, 3, 5):
        st = tagged(cls, T_STEER, u)
        wf = wheel_frame(cls, u)
        if len(st) != 1 or wf is None:
            return 9.0, n
        sc, sa = lathe_axis(st[0].pts)
        worst = max(worst, line_dist(wf[0], sc, sa))
        n += 1
    return worst, n


def axle_audit(cls):
    """Each drum's axis against the lateral axis (level and square)."""
    worst = 0.0
    for u in range(6):
        wf = wheel_frame(cls, u)
        if wf is None:
            return 90.0
        worst = max(worst, math.degrees(math.acos(min(1.0, abs(wf[1].dot(YAX))))))
    return worst


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


def stance_audit(cls, contacts, overload=False):
    """Mass centre of the rover (shell volumes x density per material)
    against the convex hull of the six wheels' contact patches; the floor
    is the margin that keeps it standing tilted TIP_DEG any way."""
    total = 0.0
    mom = Vector()
    turret = 0.0
    for s in cls["all"]:
        if s.mat is None or s.tag in (T_TERRAIN, T_ROCK):
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * DENSITY[s.mat]
        if s.tag == T_TURRET:
            if overload:
                m *= OVERLOAD
            turret += m
        total += m
        mom += m * cen
    com = mom / total
    pts = [p for u in contacts for p in contacts[u]]
    margin, need = -1.0, 9.0
    if len(pts) >= 3:
        cz = sum(p.z for p in pts) / len(pts)
        need = (com.z - cz) * math.tan(math.radians(TIP_DEG))
        hull = hull2d([(p.x, p.y) for p in pts])
        margin = 9.0
        for k in range(len(hull)):
            a, b = hull[k], hull[(k + 1) % len(hull)]
            ex, ey = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ex, ey)
            margin = min(margin, (ex * (com.y - a[1]) - ey * (com.x - a[0])) / ln)
    return {"mass": total, "turret": turret, "com": com, "margin": margin, "need": need}


def _overlap(a, b):
    if (a.lo.x > b.hi.x or b.lo.x > a.hi.x or a.lo.y > b.hi.y or b.lo.y > a.hi.y
            or a.lo.z > b.hi.z or b.lo.z > a.hi.z):
        return False
    return bool(a.tree.overlap(b.tree))


def connected_components(cls):
    # a vertex with no face is a hygiene defect, not a part
    parts = [s for s in cls["all"] if s.tri_idx]
    n = len(parts)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(n), key=lambda i: parts[i].lo.x)
    for ii, i in enumerate(order):
        a = parts[i]
        for j in order[ii + 1:]:
            b = parts[j]
            if b.lo.x > a.hi.x:
                break
            if find(i) == find(j):
                continue
            if _overlap(a, b):
                parent[find(i)] = find(j)
    roots = {find(i) for i in range(n)}
    sizes = {}
    for i in range(n):
        sizes[find(i)] = sizes.get(find(i), 0) + 1
    small = [parts[i].mean for i in range(n) if sizes[find(i)] < max(sizes.values())]
    return len(roots), sorted(sizes.values()), small[:3]


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, 1.0))
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
    img = bpy.data.images.new("RoverNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = ANOD_IDX
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


def _rng(vals, nd=4):
    return f"[{min(vals):.{nd}f},{max(vals):.{nd}f}]" if vals else "[]"


def check(skip_decimate, lift_z=False, stray_vert=False, overload_turret=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_rover_mesh("RoverLow", bevel_offset=0.0, bevel_segments=1, **flags)
    high = build_rover_mesh("RoverHigh", bevel_offset=0.0020, bevel_segments=3, **flags)
    mats = rover_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the anodised parts: actuators, bushings and brackets
    # are where the high mesh's rounder chamfer differs from the low.
    target = mats[ANOD_IDX]

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
        return (fail("rover mesh did not build", 3),) + none3

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
    zrep = []
    zf = zfight_pairs(low.data, cls["groups"], zrep)
    snk = sink_audit(cls)
    pins = pin_audit(cls)
    grs = grouser_audit(cls)
    mst = mast_audit(cls)
    dif = diff_audit(cls)
    steer, nsteer = steer_audit(cls)
    axle = axle_audit(cls)
    stance = stance_audit(cls, snk["contacts"], overload_turret)
    ncomp, comp_sizes, loose = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("rover has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "RoverLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "RoverLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(low, "RoverCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_planet_rover_{os.getpid()}.glb")
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
    if zrep:
        print(f"measured zfight_first_pairs at {[r[2] for r in zrep[:6]]}")
    print(f"measured shells={len(cls['all'])} wheel_sink={[round(x, 5) for x in snk['sink']]}")
    print(f"measured pins offset={pins['offset']:.6f} tilt={pins['tilt']:.4f} bad={pins['bad']}")
    print(f"measured grousers count={grs['count']} bite=[{grs['bite'][0]:.5f},"
          f"{grs['bite'][1]:.5f}] proud={grs['proud']:.5f} pitch_dev={grs['pitch']:.4f}")
    print(f"measured mast tilt={mst['tilt']:.4f} track={mst['track']:.4f} "
          f"length={mst['length']:.4f} height={mst['height']:.4f}")
    print(f"measured differential defl={[round(x, 4) for x in dif['defl']]} "
          f"resid={dif['resid']:.4f} link_off={dif['link_off']:.6f}")
    print(f"measured steering offset={steer:.6f} ({nsteer} corners) axle_dev={axle:.4f}")
    print(f"measured mass={stance['mass']:.1f}kg turret={stance['turret']:.1f}kg "
          f"com=({stance['com'].x:.4f},{stance['com'].y:.4f},{stance['com'].z:.4f}) "
          f"margin={stance['margin']:.4f} need={stance['need']:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[:6]} loose={loose}")

    labels = ("paint", "foil", "aluminium", "anodised", "titanium", "glass", "harness",
              "regolith", "rock")
    budgets = {
        "tris": BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX,
        "materials": nmat == MATERIAL_COUNT and distinct_mats == MATERIAL_COUNT
        and all(idx_counts.get(i, 0) >= f for i, f in enumerate(FACE_FLOORS)),
        "uv": not (u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS)
        and overlap <= UV_OVERLAP_MAX,
        "bbox": all(abs(sz - o) <= BBOX_TOL for sz, o in zip((size_x, size_y, size_z),
                                                              OUTER_SIZE)),
        "lod": LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX and LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX,
        "collider": col_tris <= COLLIDER_TRIS_MAX,
        "hygiene": not (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
                        or hyg["doubles"] or hyg["ngons"] or zf),
        "grounded": bb[2] <= ZMIN_EPS and len(snk["sink"]) == 6
        and all(SINK_MIN <= x <= SINK_MAX for x in snk["sink"]),
        "pins": not pins["bad"] and pins["offset"] <= PIN_OFF_TOL
        and pins["tilt"] <= PIN_TILT_MAX_DEG,
        "grouser_seat": grs["count"] == [N_GR] * 6 and GR_BITE_MIN <= grs["bite"][0]
        and grs["bite"][1] <= GR_BITE_MAX and grs["proud"] >= GR_PROUD_MIN,
        "mast_size": mst["tilt"] <= MAST_TILT_MAX_DEG
        and abs(mst["track"] - TRACK_WIDTH) <= TRACK_TOL
        and abs(mst["length"] - ROVER_LENGTH) <= SIZE_TOL
        and abs(mst["height"] - ROVER_HEIGHT) <= SIZE_TOL,
        "differential": len(dif["defl"]) == 2 and dif["resid"] <= DIFF_TOL_DEG
        and dif["link_off"] <= LINK_OFF_TOL,
        "steering": nsteer == 4 and steer <= STEER_OFF_TOL,
        "axles": axle <= AXLE_TOL_DEG,
        "grouser_pitch": grs["pitch"] <= PITCH_TOL_DEG,
        "stance": stance["margin"] >= stance["need"],
        "assembly": ncomp == 1,
    }
    print(f"measured budget_fails={[k for k, ok in budgets.items() if not ok]}")

    if not budgets["tris"]:
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    for idx, (floor, label) in enumerate(zip(FACE_FLOORS, labels)):
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{label} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + none3
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + none3
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + none3
    if not budgets["bbox"]:
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
    if not budgets["hygiene"]:
        return (fail(f"hygiene {hyg} zfight={zf}", 15),) + none3
    if bb[2] > ZMIN_EPS:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none3
    if not budgets["grounded"]:
        return (fail(f"wheels: sink into the regolith {[round(x, 5) for x in snk['sink']]} m, "
                     f"each must be in [{SINK_MIN}, {SINK_MAX}]", 16),) + none3
    if not budgets["pins"]:
        return (fail(f"pivot pins: a bushing {pins['offset']:.5f} m off its pin's axis (tol "
                     f"{PIN_OFF_TOL}), tilted {pins['tilt']:.4f} deg (cap {PIN_TILT_MAX_DEG}), "
                     f"or joint counts/spans {pins['bad']}", 17),) + none3
    if not budgets["grouser_seat"]:
        return (fail(f"grousers: counts {grs['count']}, root inside the skin "
                     f"[{grs['bite'][0]:.5f}, {grs['bite'][1]:.5f}] not in "
                     f"[{GR_BITE_MIN}, {GR_BITE_MAX}], or crown {grs['proud']:.5f} m proud "
                     f"(min {GR_PROUD_MIN})", 18),) + none3
    if not budgets["mast_size"]:
        return (fail(f"mast {mst['tilt']:.4f} deg off plumb (cap {MAST_TILT_MAX_DEG}), or size "
                     f"off: track {mst['track']:.4f} ({TRACK_WIDTH} +-{TRACK_TOL}), length "
                     f"{mst['length']:.4f} ({ROVER_LENGTH}), height {mst['height']:.4f} "
                     f"({ROVER_HEIGHT}) +-{SIZE_TOL}", 19),) + none3
    if not budgets["differential"]:
        return (fail(f"differential: rocker deflections {[round(x, 4) for x in dif['defl']]} "
                     f"deg not equal and opposite (residual {dif['resid']:.4f}, tol "
                     f"{DIFF_TOL_DEG}), or a link eye {dif['link_off']:.5f} m off its crank "
                     f"pin (tol {LINK_OFF_TOL})", 20),) + none3
    if not budgets["steering"]:
        return (fail(f"steering: an actuator axis {steer:.5f} m off its wheel's centre (tol "
                     f"{STEER_OFF_TOL}), {nsteer} corners", 21),) + none3
    if not budgets["axles"]:
        return (fail(f"axles: a drum axis {axle:.4f} deg off the lateral (tol {AXLE_TOL_DEG})",
                     22),) + none3
    if not budgets["grouser_pitch"]:
        return (fail(f"grouser pitch off by {grs['pitch']:.4f} deg (tol {PITCH_TOL_DEG})", 23),) + none3
    if not budgets["stance"]:
        return (fail(f"stance: mass centre {stance['margin']:.4f} m inside the contact polygon "
                     f"< {stance['need']:.4f} (the {TIP_DEG:.0f} deg tip margin)", 24),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes[:6]}", 25),) + none3
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

    # The house rig scaled to a 4.5 m set piece: warm key upper left, cool
    # fill low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-4.6, -5.2, 5.4), 322.0, 3.0, (1.0, 0.95, 0.90), spread=40.0)
    light("Fill", (5.6, -3.8, 1.4), 50.0, 6.0, (0.72, 0.82, 1.0))
    light("Rim", (-2.2, 3.4, 3.4), 210.0, 2.4, (0.62, 0.78, 1.0))
    light("Wedge", (4.4, 3.6, 1.8), 655.0, 3.2, (1.0, 0.64, 0.34),
          target=(centre.x + 4.6, centre.y + WALL_Y, 1.1))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((0.30, -0.95, 0.0)).normalized()
    cam.location = centre + view * 8.7 + Vector((0.0, 0.0, 3.1))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.70))
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
    # Standard, not AgX: AgX washes the foil and the regolith grey
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
    p.add_argument("--float-wheel", action="store_true")
    p.add_argument("--offset-pin", action="store_true")
    p.add_argument("--sink-grousers", action="store_true")
    p.add_argument("--lean-mast", action="store_true")
    p.add_argument("--jam-rocker", action="store_true")
    p.add_argument("--offset-steer", action="store_true")
    p.add_argument("--camber-wheel", action="store_true")
    p.add_argument("--bunch-grousers", action="store_true")
    p.add_argument("--overload-turret", action="store_true")
    p.add_argument("--loose-dish", action="store_true")
    args = p.parse_args(argv)

    flags = {name: getattr(args, name) for name in FLAG_NAMES}
    code, low, target, tex = check(args.skip_decimate, lift_z=args.lift_z,
                                   stray_vert=args.stray_vert,
                                   overload_turret=args.overload_turret, **flags)
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("planet-rover OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
