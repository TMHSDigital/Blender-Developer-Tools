"""Game-ready coconut palm on a beach — a showcase piece, not an example.

Asserts budget conformance of a procedural beach vignette after composing
shipped pipeline pieces: bmesh construction, UVs, eight materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

A raised disc of beach sand holds one coconut palm. Its trunk rises from a
swollen, lobed bole with a mat of roots flaring out of it into the sand,
leans away along a curve and comes back upright under the crown, tapering
as it goes, ringed with the scars of fallen leaf bases at an even pitch.
The crown is a fibrous boss of leaf bases carrying sixteen pinnate fronds
in a golden-angle spiral: each a curved rachis arching out and drooping,
with paired, folded, drooping leaflets along it, the young fronds high and
upright, the old ones low and hanging; two dead brown fronds hang against
the trunk and two unopened spear leaves stand at the centre. Bunches of
green and ripening coconuts sit on the boss under the frond bases. Two
fallen coconuts, a fallen frond, a bleached driftwood branch, seashells and
tufts of sea grass lie on the rippled sand.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--short-petioles`` every frond seated in the
crown, ``--drop-coconut`` every coconut attached under the crown,
``--short-roots`` the crown's mass over the root plate, ``--bunch-rings``
the leaf-scar rings at an even pitch, ``--perch-trunk`` the trunk and roots
bedded in the sand, ``--float-nuts`` the fallen coconuts resting in the
sand, ``--float-cover`` the beach litter joined to the sand.

Seeded, not random: ``random.Random(SEED)`` draws the plan before anything
is built, and per-leaflet draws come from a closed-form hash of the
leaflet's indices, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python palm_tree.py --
    blender --background --python palm_tree.py -- --skip-decimate
    blender --background --python palm_tree.py -- --output palm.png
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

SEED = 5147
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- Ground ------------------------------------------------------------------
DISC_A = (1.56, 1.40)     # sand disc semi-axes before its wobble, m
DISC_EDGE = 0.14          # the rim rolls down over this fraction of the radius
DISC_N = {"low": 42, "high": 80}
MOUND_Z = 0.110

# --- Trunk -------------------------------------------------------------------
TRUNK_XY = (-0.66, 0.26)
TRUNK_L = 4.60            # arc length of the axis from the sand at the foot to the top
LEAN_AZ = -21.0           # bearing of the lean, deg
LEAN_MAX = 34.0           # the tilt the curve is shaped from, deg
TRUNK_BED = 0.100         # the foot under the lowest sand round it
TRUNK_N = {"low": 46, "high": 70}
TRUNK_SIDES = {"low": 20, "high": 30}
# leaf-scar rings: arc-length station of the first, the pitch, the count
RING_S0 = 0.52
RING_STEP = 0.145
N_RINGS = 25
RING_BITE = 0.006         # every ring's inner face this far inside the bark
RING_PROUD = 0.0024       # and its crest this far proud of it
# roots
N_ROOTS = 24
ROOT_DIVE = 0.050         # every root's tip this far under the sand

# --- Crown -------------------------------------------------------------------
BOSS_UP = 0.10            # the boss centre past the trunk's top, along its axis
BOSS_RW = 0.215
BOSS_RL = 0.340
BOSS_TAPER = 0.14
N_FRONDS = 18
FROND_SEAT = 0.100        # every rachis starts this far inside the boss
LEAF_PAIRS = 36
LEAF_MAX = 0.80
N_DEAD = 2
NUT_RW = 0.080
NUT_RL = 0.136
NUT_BITE = 0.028          # every coconut's stem end this far inside the boss
NUT_BUNCHES = 4
NUT_PER_BUNCH = 3

# --- Beach -------------------------------------------------------------------
# fallen coconuts: x, y, bearing of the axis deg, roll deg
FALLEN_NUTS = ((0.30, -0.74, 158.0, 10.0), (0.62, -0.47, 345.0, -14.0))
NUT_SINK = 0.022          # the fallen nuts' lowest point this far into the sand
FALLEN_FROND = ((-1.18, -0.30), (-0.30, -0.78), (0.02, -1.02))
DRIFT = ((0.52, 0.64), (1.28, 0.06))
# scallops: x, y, radius, bearing deg; augers: x, y, length, bearing deg
SCALLOPS = ((-0.18, -0.52, 0.048, 30.0), (1.02, -0.40, 0.040, 200.0), (-1.02, 0.66, 0.044, 120.0),
            (0.12, 0.92, 0.036, 300.0))
AUGERS = ((0.86, -0.78, 0.085, 150.0), (-0.52, -0.98, 0.070, 60.0))
TUFTS = ((-1.14, 0.30, 0.95), (1.08, 0.60, 0.90), (1.02, -0.18, 0.70), (-0.40, 0.98, 0.80),
         (0.18, 0.40, 0.55))

# falsifiers
SHORT_PETIOLE = 0.080     # --short-petioles: every rachis starts this much nearer the boss's skin
DROP_BITE = 0.006         # --drop-coconut: one coconut slid out along its axis until only this is in the boss
SHORT_ROOT_REACH = 0.26   # --short-roots: every root dives into the sand this close to the axis
BUNCH_RINGS = (9, 10, 11)
BUNCH_SHIFT = 0.045       # --bunch-rings: three rings slid down the trunk
PERCH_BED = 0.012         # --perch-trunk: the foot this far under the sand, the roots unchanged
FLOAT_NUTS = 0.016        # --float-nuts: the fallen coconuts raised, still touching the sand
FLOAT_COVER = 0.050       # --float-cover: shells, driftwood, grass and the fallen frond lifted

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from the vertices.
OUTER_SIZE = (5.2645, 5.1503, 6.0258)
BASE_TRIS_MIN = 44600
BASE_TRIS_MAX = 45800
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 8
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 60
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# sand, bark, frond, dead frond, husk, shell, driftwood, grass
FACE_FLOORS = (3400, 4370, 13640, 1140, 1230, 780, 134, 1030)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Fronds: every rachis's deepest vertex inside the boss.
SEAT_MIN = 0.060
SEAT_MAX = 0.160
# Coconuts: every attached nut's deepest vertex inside the boss, its centre under the boss's.
NUT_BITE_MIN = 0.012
NUT_BITE_MAX = 0.045
# Trunk: height over the sand at the foot, the crown's offset, the tip-over margin.
TRUNK_H = 4.47
TRUNK_H_TOL = 0.05
CROWN_OFF_BAND = (0.60, 1.00)
TIP_MARGIN_MIN = 0.080
# Rings: the pitch between consecutive ring centres.
RING_PITCH_BAND = (0.135, 0.155)
RING_SPREAD_MAX = 0.006
# Bedding: the trunk's shallowest sector, every root tip, under the sand.
BED_MIN = 0.030
BED_MAX = 0.200
ROOT_BED_MIN = 0.020
ROOT_BED_MAX = 0.100
# Fallen coconuts: the lowest point under the sand straight above it.
REST_MIN = 0.010
REST_MAX = 0.050
HERO_YAW_DEG = 0.0
WALL_Y = 5.0

SAND_IDX = 0
BARK_IDX = 1
FROND_IDX = 2
DEAD_IDX = 3
HUSK_IDX = 4
SHELL_IDX = 5
DRIFT_IDX = 6
GRASS_IDX = 7
MAT_LABELS = ("sand", "bark", "frond", "dead frond", "husk", "shell", "driftwood", "grass")

# part labels (a face attribute): they name a shell, they never measure it
P_SAND, P_TRUNK, P_RING, P_ROOT, P_BOSS, P_RACHIS, P_LEAF, P_SPEAR = 1, 2, 3, 4, 5, 6, 7, 8
P_DEAD, P_DEAD_LEAF, P_NUT, P_FALLEN_NUT, P_FALLEN, P_FALLEN_LEAF = 9, 10, 11, 12, 13, 14
P_SHELL, P_DRIFT, P_GRASS = 15, 16, 17
FROND_PARTS = (P_RACHIS, P_SPEAR, P_DEAD)
CROWN_PARTS = (P_TRUNK, P_RING, P_BOSS, P_RACHIS, P_LEAF, P_SPEAR, P_DEAD, P_DEAD_LEAF, P_NUT)
COVER_PARTS = (P_FALLEN, P_FALLEN_LEAF, P_SHELL, P_DRIFT, P_GRASS)

FLAG_NAMES = ("short_petioles", "drop_coconut", "short_roots", "bunch_rings", "perch_trunk",
              "float_nuts", "float_cover")


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


def smoothstep(x, lo, hi):
    t = min(max((x - lo) / (hi - lo), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def perp_basis(d):
    ref = UP if abs(d.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = d.cross(ref).normalized()
    return e1, d.cross(e1).normalized()


def hash01(a, b, c):
    """A closed-form draw in [0, 1) from three indices: per-leaflet variety
    that no flag can shift."""
    x = math.sin(a * 12.9898 + b * 78.233 + c * 37.719 + SEED * 0.0137) * 43758.5453
    return x - math.floor(x)


def squircle(i, k, n):
    """A square grid mapped onto the unit disc (its border on the circle)."""
    uu = -1.0 + 2.0 * i / n
    vv = -1.0 + 2.0 * k / n
    return uu * math.sqrt(1.0 - vv * vv / 2.0), vv * math.sqrt(1.0 - uu * uu / 2.0)


def hor(v):
    return Vector((v.x, v.y, 0.0))


def heading(deg):
    a = math.radians(deg)
    return Vector((math.cos(a), math.sin(a), 0.0))


def rotate_about(v, axis, ang):
    return Matrix.Rotation(ang, 3, axis) @ v


# --------------------------------------------------------------------------
# The ground as a function of plan position
# --------------------------------------------------------------------------

def disc_wobble(th):
    return 1.0 + 0.040 * math.sin(3.0 * th + 0.7) + 0.028 * math.sin(5.0 * th + 2.1) \
        + 0.015 * math.sin(8.0 * th + 1.3)


def disc_radius(x, y):
    """Normalised disc radius: 1 on the sand's rim."""
    X, Y = x / DISC_A[0], y / DISC_A[1]
    return math.hypot(X, Y) / disc_wobble(math.atan2(Y, X))


HUMPS = ((TRUNK_XY[0], TRUNK_XY[1], 0.034, 0.55), (0.55, -0.60, -0.012, 0.40), (0.95, 0.35, 0.010, 0.35))


def sand_height(x, y):
    """A low drift of sand heaped round the palm's foot, rolled down to Z = 0
    at the disc's rim."""
    rn2 = (x / DISC_A[0]) ** 2 + (y / DISC_A[1]) ** 2
    z = MOUND_Z * (1.0 - 0.35 * rn2)
    z += 0.009 * math.sin(1.9 * x + 0.4) * math.cos(1.5 * y - 0.8) + 0.004 * math.sin(3.7 * x - 2.9 * y + 0.6)
    for hx, hy, amp, w in HUMPS:
        z += amp * math.exp(-((x - hx) ** 2 + (y - hy) ** 2) / (w * w))
    return z * smoothstep(1.0 - disc_radius(x, y), 0.0, DISC_EDGE)


def ground_min(cx, cy, r, n=24):
    return min(sand_height(cx + r * math.cos(TAU * k / n), cy + r * math.sin(TAU * k / n))
               for k in range(n))


# --------------------------------------------------------------------------
# The plan: every seeded draw happens here, before anything is built
# --------------------------------------------------------------------------

def plan_beach():
    rng = random.Random(SEED)

    def u(a, b):
        return a + (b - a) * rng.random()

    plan = {"trunk_tone": rng.random(), "frond_az0": u(0.0, 360.0)}
    plan["fronds"] = [{"tone": rng.random(), "L": u(0.94, 1.06), "curl": u(-0.06, 0.06),
                       "droop": u(-6.0, 6.0), "el": u(-4.0, 4.0)} for _k in range(N_FRONDS)]
    # the dead fronds hang on the camera's side of the trunk, where they read
    plan["dead"] = [{"tone": rng.random(), "az": az + u(-6.0, 6.0), "curl": u(-0.05, 0.05)}
                    for az in (-150.0, 172.0)]
    plan["roots"] = [{"az": u(-8.0, 8.0), "h": u(0.0, 1.0), "reach": u(-0.05, 0.05), "r": u(0.85, 1.15),
                      "tone": rng.random()} for _k in range(N_ROOTS)]
    plan["nuts"] = [{"tone": rng.random(), "ph": u(0.0, TAU), "s": u(0.94, 1.06)}
                    for _k in range(NUT_BUNCHES * NUT_PER_BUNCH + len(FALLEN_NUTS))]
    plan["drift"] = {"wig": [u(-1, 1) for _k in range(9)], "tone": rng.random()}
    plan["fallen"] = {"tone": rng.random()}
    plan["tufts"] = [{"j": (u(-0.02, 0.02), u(-0.02, 0.02)), "tone": rng.random(),
                      "blades": [{"yaw": u(0.0, TAU), "h": u(0.50, 1.0), "lean": u(0.25, 0.70),
                                  "w": u(0.8, 1.2), "tw": u(-0.6, 0.6), "off": (u(-1, 1), u(-1, 1)),
                                  "tone": rng.random()} for _b in range(30)]}
                     for _t in TUFTS]
    plan["shells"] = [{"tone": rng.random(), "tilt": u(-0.15, 0.15)} for _s in SCALLOPS + AUGERS]
    return plan


# --------------------------------------------------------------------------
# The trunk's axis: a curve that leans out of the bole and comes back upright
# --------------------------------------------------------------------------

class Trunk:
    TABLE = 720

    def __init__(self, perch=False):
        x, y = TRUNK_XY
        self.zf = sand_height(x, y)
        bed = PERCH_BED if perch else TRUNK_BED
        bottom = ground_min(x, y, self.radius(0.0) * 1.1) - bed
        self.s_bot = bottom - self.zf
        self.lean = heading(LEAN_AZ)
        # integrate the axis and a parallel-transported frame on a fine table
        n = self.TABLE
        self.ss, self.ps, self.ts, self.e1s = [], [], [], []
        p = Vector((x, y, bottom))
        e1 = Vector((1.0, 0.0, 0.0))
        for k in range(n + 1):
            s = self.s_bot + (TRUNK_L - self.s_bot) * k / n
            t = self.tangent_of(s)
            e1 = (e1 - t * e1.dot(t)).normalized()
            self.ss.append(s)
            self.ps.append(p.copy())
            self.ts.append(t)
            self.e1s.append(e1.copy())
            if k < n:
                ds = (TRUNK_L - self.s_bot) / n
                p = p + self.tangent_of(s + 0.5 * ds) * ds

    def theta(self, s):
        return math.radians(LEAN_MAX) * smoothstep(s, 0.10, 1.10) * max(0.0, 1.0 - s / TRUNK_L) ** 1.25

    def tangent_of(self, s):
        th = self.theta(s)
        return (self.lean * math.sin(th) + UP * math.cos(th)).normalized()

    def _at(self, s):
        f = (s - self.s_bot) / (TRUNK_L - self.s_bot) * self.TABLE
        f = min(max(f, 0.0), self.TABLE - 1e-9)
        i = int(f)
        return i, f - i

    def axis(self, s):
        i, f = self._at(s)
        return self.ps[i].lerp(self.ps[i + 1], f)

    def frame(self, s):
        i, f = self._at(s)
        t = self.ts[i].lerp(self.ts[i + 1], f).normalized()
        e1 = self.e1s[i].lerp(self.e1s[i + 1], f)
        e1 = (e1 - t * e1.dot(t)).normalized()
        return t, e1, t.cross(e1)

    @staticmethod
    def radius(s):
        """The mean radius at arc length ``s``: a swollen bole, a slow taper,
        a slight swelling under the crown."""
        sc = max(s, -0.05)
        R = 0.148 * (1.0 - 0.20 * min(max(s, 0.0) / TRUNK_L, 1.0))
        R += 0.120 * math.exp(-sc / 0.20)
        R += 0.010 * math.exp(-((s - (TRUNK_L - 0.30)) / 0.22) ** 2)
        return R

    def r(self, s, th):
        """The bark's radius at arc length ``s`` and angle ``th`` round the
        axis: a little out of round, lobed at the bole where the roots leave."""
        lobes = 0.100 * math.exp(-max(s, 0.0) / 0.22) * (0.5 + 0.5 * math.cos(7.0 * th + 0.8))
        wob = 1.0 + 0.022 * math.sin(2.0 * th + 1.1 + 0.6 * s) + 0.010 * math.sin(3.0 * th + 2.0 * s + 0.4)
        return self.radius(s) * (wob + lobes)

    def surface(self, s, th, dr=0.0):
        t, e1, e2 = self.frame(s)
        return self.axis(s) + (e1 * math.cos(th) + e2 * math.sin(th)) * (self.r(s, th) + dr)


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

def new_face(bm, verts, mat, L, tone, zone, part):
    out = []
    for v in verts:
        if not out or out[-1] is not v:
            out.append(v)
    if len(out) > 1 and out[0] is out[-1]:
        out.pop()
    f = bm.faces.new(out)
    f.material_index = mat
    f[L["tone"]] = tone
    f[L["zone"]] = zone
    f[L["part"]] = part
    return f


def grid_faces(bm, grid, n, mat, L, tone, part):
    for i in range(n):
        for k in range(n):
            a, b, c, d = grid[i][k], grid[i + 1][k], grid[i + 1][k + 1], grid[i][k + 1]
            if (a.co - c.co).length <= (b.co - d.co).length:
                tris = ((a, b, c), (a, c, d))
            else:
                tris = ((a, b, d), (b, c, d))
            for tri in tris:
                new_face(bm, tri, mat, L, tone, 0.0, part)


def grid_rim(grid, n):
    return ([grid[i][0] for i in range(n)] + [grid[n][k] for k in range(n)]
            + [grid[i][n] for i in range(n, 0, -1)] + [grid[0][k] for k in range(n, 0, -1)])


def add_sand(bm, L, V, n):
    grid = []
    for i in range(n + 1):
        col = []
        for k in range(n + 1):
            X, Y = squircle(i, k, n)
            wob = disc_wobble(math.atan2(Y, X))
            x = DISC_A[0] * X * wob
            y = DISC_A[1] * Y * wob
            on_rim = i in (0, n) or k in (0, n)
            z = 0.0 if on_rim else sand_height(x, y)
            v = bm.verts.new((x, y, z))
            v[V["skirt"]] = smoothstep(disc_radius(x, y), 0.86, 0.93)
            col.append(v)
        grid.append(col)
    grid_faces(bm, grid, n, SAND_IDX, L, 0.5, P_SAND)
    new_face(bm, list(reversed(grid_rim(grid, n))), SAND_IDX, L, 0.5, 0.0, P_SAND)


def sand_hit(tree, x, y):
    loc, nrm, _i, _d = tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
    if loc is None:
        return Vector((x, y, 0.0)), Vector((0.0, 0.0, 1.0))
    if nrm.z < 0.0:
        nrm = -nrm
    return loc, nrm


def add_tube(bm, pts, radii, sides, mat, L, V, tone, part, zone=0.0, tip=None, alongs=None,
             phase=0.0, shape=None):
    """A tube through ``pts`` with parallel-transported rings, a flat base
    cap, and either a flat top cap or a point at ``tip``. ``shape(i, a)``
    scales the radius round a ring."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tans = []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)] if tip is None or i < n - 1 else Vector(tip)
        tans.append((b - a).normalized())
    e1, e2 = perp_basis(tans[0])
    nrm = e1 * math.cos(phase) + e2 * math.sin(phase)
    rings = []
    for i, (p, t, r) in enumerate(zip(pts, tans, radii)):
        nrm = (nrm - t * nrm.dot(t)).normalized()
        b = t.cross(nrm)
        ring = []
        for k in range(sides):
            a = TAU * k / sides
            rr = r * (shape(i, a) if shape is not None else 1.0)
            v = bm.verts.new(p + rr * (nrm * math.cos(a) + b * math.sin(a)))
            if alongs is not None:
                v[V["along"]] = alongs[i]
            ring.append(v)
        rings.append(ring)
    for i, (r0, r1) in enumerate(zip(rings, rings[1:])):
        for k in range(sides):
            m = (k + 1) % sides
            new_face(bm, (r0[k], r0[m], r1[m], r1[k]), mat, L, tone, zone, part)
    new_face(bm, tuple(reversed(rings[0])), mat, L, tone, zone, part)
    if tip is None:
        new_face(bm, tuple(rings[-1]), mat, L, tone, zone, part)
    else:
        tv = bm.verts.new(tip)
        if alongs is not None:
            tv[V["along"]] = 1.0
        for k in range(sides):
            new_face(bm, (rings[-1][k], rings[-1][(k + 1) % sides], tv), mat, L, tone, zone, part)


_CUBE = {}


def cube_sphere(n):
    """Unit directions on a warped cube-sphere lattice and its quads."""
    if n in _CUBE:
        return _CUBE[n]
    index = {}
    dirs = []

    def vid(i, j, k):
        key = (i, j, k)
        if key not in index:
            q = [math.tan(math.pi / 4.0 * (2.0 * c / n - 1.0)) for c in key]
            index[key] = len(dirs)
            dirs.append(Vector(q).normalized())
        return index[key]

    quads = []
    for ax in range(3):
        b, c = (ax + 1) % 3, (ax + 2) % 3
        for side in (0, n):
            for uu in range(n):
                for vv in range(n):
                    corners = []
                    for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                        key = [0, 0, 0]
                        key[ax] = side
                        key[b] = uu + du
                        key[c] = vv + dv
                        corners.append(vid(*key))
                    quads.append(corners if side else corners[::-1])
    _CUBE[n] = (dirs, quads)
    return _CUBE[n]


def add_blade(bm, pts, sref, width, fold, th, twist, mat, L, V, tone, zone, part, up_ref):
    """A folded leaf blade along ``pts`` ending in a point: a V section, its
    two edges ``fold`` of the half width above the midrib, its width axis
    the part of ``sref`` square to the blade's run, turned by ``twist``
    toward the tip."""
    n = len(pts) - 1
    rings = []
    sign = None
    for i in range(n):
        s = i / n
        tan = (pts[i + 1] - pts[max(i - 1, 0)]).normalized()
        side = sref - tan * sref.dot(tan)
        if side.length < 1e-6:
            side = perp_basis(tan)[0]
        side.normalize()
        side = rotate_about(side, tan, twist * s)
        nrm = side.cross(tan).normalized()
        if sign is None:
            sign = 1.0 if nrm.dot(up_ref) >= 0.0 else -1.0
        nrm = nrm * sign
        w = 0.5 * width(s)
        ring = [bm.verts.new(pts[i] - side * w + nrm * (fold * w)),
                bm.verts.new(pts[i] + side * w + nrm * (fold * w)),
                bm.verts.new(pts[i] - nrm * th)]
        for v in ring:
            v[V["along"]] = s
        rings.append(ring)
    tip = bm.verts.new(pts[-1])
    tip[V["along"]] = 1.0
    new_face(bm, list(reversed(rings[0])), mat, L, tone, zone, part)
    for i in range(n - 1):
        r0, r1 = rings[i], rings[i + 1]
        for q in range(3):
            w = (q + 1) % 3
            new_face(bm, (r0[q], r1[q], r1[w], r0[w]), mat, L, tone, zone, part)
    last = rings[-1]
    for q in range(3):
        new_face(bm, (last[q], tip, last[(q + 1) % 3]), mat, L, tone, zone, part)


# --------------------------------------------------------------------------
# The palm
# --------------------------------------------------------------------------

def ring_stations(bunch):
    out = []
    for k in range(N_RINGS):
        s = RING_S0 + RING_STEP * k
        if bunch and k in BUNCH_RINGS:
            s -= BUNCH_SHIFT
        out.append(s)
    return out


def add_trunk(bm, L, V, tr, plan, detail, bunch):
    sides = TRUNK_SIDES[detail]
    n = TRUNK_N[detail]
    tone = plan["trunk_tone"]
    levels = [tr.s_bot] + [TRUNK_L * (k / n) ** 1.15 for k in range(n + 1)]
    rows = []
    for s in levels:
        row = []
        for j in range(sides):
            th = TAU * j / sides
            v = bm.verts.new(tr.surface(s, th))
            v[V["along"]] = max(s, 0.0) / TRUNK_L
            row.append(v)
        rows.append(row)
    for r0, r1 in zip(rows, rows[1:]):
        for j in range(sides):
            q = (j + 1) % sides
            new_face(bm, (r0[j], r0[q], r1[q], r1[j]), BARK_IDX, L, tone, 0.0, P_TRUNK)
    new_face(bm, list(reversed(rows[0])), BARK_IDX, L, tone, 0.0, P_TRUNK)
    new_face(bm, list(rows[-1]), BARK_IDX, L, tone, 0.0, P_TRUNK)

    # leaf-scar rings: a low rim on the bark, its inner face inside it
    prof = ((-0.030, -RING_BITE), (-0.010, 0.45), (0.010, 1.0), (0.022, -RING_BITE))
    for k, sr in enumerate(ring_stations(bunch)):
        rows = []
        for a, d in prof:
            row = []
            for j in range(sides):
                th = TAU * j / sides
                if d > 0.0:
                    lift = RING_PROUD * d * (0.60 + 0.40 * math.sin(3.0 * th + 1.7 * k))
                else:
                    lift = d
                # each scar a little out of square with the axis
                tilt = 0.010 * math.sin(th + 2.3 * k)
                v = bm.verts.new(tr.surface(sr + a + tilt, th, lift))
                v[V["along"]] = sr / TRUNK_L
                row.append(v)
            rows.append(row)
        rt = hash01(k, 3, 11)
        for i in range(len(prof)):
            r0, r1 = rows[i], rows[(i + 1) % len(prof)]
            for j in range(sides):
                q = (j + 1) % sides
                new_face(bm, (r0[j], r0[q], r1[q], r1[j]), BARK_IDX, L, rt, 1.0, P_RING)


def add_roots(bm, L, V, tr, plan, tree, short):
    for k, rp in enumerate(plan["roots"]):
        az = 360.0 * k / N_ROOTS + rp["az"]
        d = heading(az)
        lean_c = max(0.0, math.cos(math.radians(az - LEAN_AZ)))
        reach = SHORT_ROOT_REACH if short else (0.46 + 0.42 * lean_c ** 1.5) * (0.85 + 3.0 * rp["reach"])
        h0 = 0.04 + 0.34 * rp["h"]
        o = tr.axis(h0)
        r0 = 0.55 * tr.radius(h0)
        pts, radii, alongs = [], [], []
        nst = 8
        side = UP.cross(d)
        for i in range(nst):
            t = i / (nst - 1)
            rho = r0 + (reach - r0) * t
            rr = rp["r"] * (0.028 - 0.016 * t)
            # out of the bole and down onto the sand, then along it half
            # buried, snaking a little, and in under it at the tip
            q = Vector((o.x, o.y, 0.0)) + d * rho + side * (0.07 * math.sin(math.pi * 2.2 * t + 1.7 * k) * t)
            g = sand_hit(tree, q.x, q.y)[0].z
            run = g - 0.45 * rr - ROOT_DIVE * smoothstep(t, 0.72, 1.0)
            z = run + (o.z - run) * max(0.0, 1.0 - t / 0.32) ** 2
            pts.append(Vector((q.x, q.y, z)))
            radii.append(rr)
            alongs.append(t)
        tip = pts[-1] + (pts[-1] - pts[-2]).normalized() * 0.03
        add_tube(bm, pts, radii, 8, BARK_IDX, L, V, rp["tone"], P_ROOT, zone=2.0, tip=tip,
                 alongs=alongs, phase=0.3 * k)


class Crown:
    """The boss of leaf bases on the trunk's top, as a closed ovoid whose
    surface the fronds and coconuts are placed against by raycasting."""

    def __init__(self, tr, detail):
        t, e1, e2 = tr.frame(TRUNK_L)
        self.t, self.e1, self.e2 = t, e1, e2
        self.c = tr.axis(TRUNK_L) + t * BOSS_UP
        dirs, quads = cube_sphere(4 if detail == "low" else 6)
        self.pts = []
        for dd in dirs:
            s = 1.0 - BOSS_TAPER * dd.z
            self.pts.append(self.c + e1 * (dd.x * BOSS_RW * s) + e2 * (dd.y * BOSS_RW * s) + t * (dd.z * BOSS_RL))
        self.quads = quads
        self.dirs = dirs
        self.tree = BVHTree.FromPolygons([tuple(p) for p in self.pts], quads)

    def surface_dist(self, d):
        loc, _n, _i, dist = self.tree.ray_cast(self.c, d, 2.0)
        return dist if loc is not None else BOSS_RW

    def direction(self, az, beta):
        h = self.e1 * math.cos(math.radians(az)) + self.e2 * math.sin(math.radians(az))
        return (h * math.cos(math.radians(beta)) + self.t * math.sin(math.radians(beta))).normalized(), h

    def build(self, bm, L, V, tone):
        verts = []
        for p, dd in zip(self.pts, self.dirs):
            v = bm.verts.new(p)
            v[V["along"]] = 0.5 + 0.5 * dd.z
            verts.append(v)
        for q in self.quads:
            new_face(bm, [verts[i] for i in q], BARK_IDX, L, tone, 3.0, P_BOSS)


def path_along(J, h, lat, el0, droop, length, curl, n=64):
    """A rachis: arc-length samples of a curve out of ``J`` along heading
    ``h``, rising at ``el0`` and bending down by ``droop`` toward its tip."""
    pts = [J.copy()]
    p = J.copy()
    for i in range(n):
        s = (i + 0.5) / n
        el = el0 - droop * s ** 1.7
        d = (h * math.cos(el) + UP * math.sin(el) + lat * (curl * math.cos(math.pi * s))).normalized()
        p = p + d * (length / n)
        pts.append(p.copy())
    return pts


def sample_path(pts, length, s):
    n = len(pts) - 1
    f = min(max(s / length * n, 0.0), n - 1e-9)
    i = int(f)
    p = pts[i].lerp(pts[i + 1], f - i)
    t = (pts[i + 1] - pts[i]).normalized()
    return p, t


def rachis_radius(s, length, scale=1.0):
    return scale * (0.034 * (1.0 - 0.78 * min(s / length, 1.0) ** 0.8) + 0.030 * math.exp(-s / 0.18))


def add_frond(bm, L, V, pts, length, h, lat, trim, age, key, mat, part, leaf_part, tone, pairs,
              droop_leaf, fwd_leaf, leaf_len, missing=0.0, zone_leaf=0.0, zone_rachis=1.0, scale=1.0):
    """One pinnate frond on a sampled rachis: the rachis tube, then paired
    folded leaflets from a fifth of the way out to the tip."""
    nst = 16
    ss = [trim] + [trim + (length - trim) * k / nst for k in range(1, nst)]
    rp = [sample_path(pts, length, s)[0] for s in ss]
    radii = [rachis_radius(s, length, scale) for s in ss]
    add_tube(bm, rp, radii, 6, mat, L, V, tone, part, zone=zone_rachis, tip=pts[-1],
             alongs=[s / length for s in ss], phase=0.37 * key)
    for i in range(pairs):
        u = i / (pairs - 1)
        for side in (-1.0, 1.0):
            hh = hash01(key, i, 3 if side > 0 else 7)
            if hh < missing:
                continue
            s = length * (0.20 + 0.72 * (i + 0.5 + (0.25 if side > 0 else -0.05)) / pairs)
            p, t = sample_path(pts, length, s)
            u_r = lat.cross(t).normalized()
            if u_r.dot(UP) < 0.0:
                u_r = -u_r
            rr = rachis_radius(s, length, scale)
            fwd = math.radians(fwd_leaf - 8.0 * u + 7.0 * (hash01(key, i, 5) - 0.5))
            dr = math.radians(droop_leaf + 12.0 * (hash01(i, key, side) - 0.5)) + 0.20 * u
            ld = (t * math.cos(fwd) + (lat * (side * math.cos(dr)) - u_r * math.sin(dr)) * math.sin(fwd))
            ld.normalize()
            f = 0.35 + 0.65 * math.sin(math.pi * (0.25 + 0.75 * u))
            Lf = leaf_len * f * (0.90 + 0.20 * hash01(key, side, i))
            W = 0.058 * scale * (0.60 + 0.40 * f)
            B = p + lat * (side * 0.30 * rr)
            bend = 0.20 + 0.22 * age + 0.10 * hash01(side, i, key)
            seg = 3
            q = B.copy()
            d = ld.copy()
            lp = [q.copy()]
            for j in range(seg):
                q = q + d * (Lf / seg)
                lp.append(q.copy())
                d = (d - UP * bend).normalized()

            def width(sv, W=W):
                return W * (0.25 + 0.75 * smoothstep(sv, 0.0, 0.22)) * (1.0 - 0.55 * sv ** 1.5)

            tw = 0.8 * (hash01(i, side, key) - 0.5)
            add_blade(bm, lp, t, width, 0.30, 0.0012, tw, mat, L, V,
                      0.6 * tone + 0.4 * hash01(key, i, side + 2.0), zone_leaf, leaf_part, u_r)


def frond_specs(plan, crown):
    """Every live frond's placement: youngest first, high on the boss and
    upright; oldest last, low and hanging."""
    out = []
    golden = 137.508
    for k, fp in enumerate(plan["fronds"]):
        a = k / (N_FRONDS - 1)
        az = plan["frond_az0"] + golden * k
        beta = 50.0 - 70.0 * a
        el0 = math.radians(42.0 - 58.0 * a + fp["el"])
        droop = math.radians(52.0 + 50.0 * a + fp["droop"])
        length = (2.70 + 0.50 * a) * fp["L"]
        out.append({"az": az % 360.0, "beta": beta, "el0": el0, "droop": droop, "L": length, "age": a,
                    "fp": fp})
    return out


def add_crown(bm, L, V, tr, plan, crown, short_petioles, drop_coconut):
    crown.build(bm, L, V, 0.5)
    trim = SHORT_PETIOLE if short_petioles else 0.0
    specs = frond_specs(plan, crown)
    for k, sp in enumerate(specs):
        d0, h = crown.direction(sp["az"], sp["beta"])
        hh = hor(h).normalized()
        lat = UP.cross(hh).normalized()
        J = crown.c + d0 * (crown.surface_dist(d0) - FROND_SEAT)
        pts = path_along(J, hh, lat, sp["el0"], sp["droop"], sp["L"], sp["fp"]["curl"])
        add_frond(bm, L, V, pts, sp["L"], hh, lat, trim, sp["age"], k, FROND_IDX, P_RACHIS, P_LEAF,
                  sp["fp"]["tone"], LEAF_PAIRS, 46.0 + 22.0 * sp["age"], 56.0, LEAF_MAX * (0.85 + 0.2 * sp["age"]))

    # two dead fronds hanging against the trunk
    for k, dp in enumerate(plan["dead"]):
        d0, h = crown.direction(dp["az"], -28.0)
        hh = hor(h).normalized()
        lat = UP.cross(hh).normalized()
        J = crown.c + d0 * (crown.surface_dist(d0) - FROND_SEAT)
        length = 2.25 - 0.30 * k
        pts = path_along(J, hh, lat, math.radians(-38.0), math.radians(44.0), length, dp["curl"])
        add_frond(bm, L, V, pts, length, hh, lat, trim, 1.0, 40 + k, DEAD_IDX, P_DEAD, P_DEAD_LEAF,
                  dp["tone"], 22, 12.0, 26.0, 0.42, missing=0.30, zone_leaf=1.0, zone_rachis=1.0, scale=0.9)

    # two unopened spear leaves at the centre
    for k, (tilt, length) in enumerate(((4.0, 0.95), (14.0, 0.62))):
        d0, h = crown.direction(plan["frond_az0"] + 200.0 * k, 90.0 - tilt)
        J = crown.c + d0 * (crown.surface_dist(d0) - FROND_SEAT)
        s0 = SHORT_PETIOLE if short_petioles else 0.0
        pts = [J + d0 * (s0 + (length - s0) * f) + hor(h) * (0.06 * length * f * f)
               for f in (0.0, 0.25, 0.5, 0.72, 0.88)]
        tip = J + d0 * (length + 0.05) + hor(h) * (0.07 * length)
        add_tube(bm, pts, [0.036, 0.036, 0.030, 0.021, 0.012], 6, FROND_IDX, L, V, 0.3 + 0.4 * k, P_SPEAR,
                 zone=2.0, tip=tip, alongs=[0.0, 0.25, 0.5, 0.72, 0.88], phase=0.9 * k)

    # coconut bunches in the gaps between the old fronds' bases
    old = [sp["az"] for sp in specs if sp["age"] > 0.45] + [dp["az"] for dp in plan["dead"]]

    def gap(az):
        return min(abs((az - o + 180.0) % 360.0 - 180.0) for o in old)

    cands = sorted(range(0, 360, 5), key=lambda a: (-gap(a), a))
    picked = []
    for a in cands:
        if all(abs((a - p + 180.0) % 360.0 - 180.0) >= 70.0 for p in picked):
            picked.append(a)
        if len(picked) == NUT_BUNCHES:
            break
    nuts = []
    for b, az in enumerate(sorted(picked)):
        for j in range(NUT_PER_BUNCH):
            azj = az + 30.0 * (j - 0.5 * (NUT_PER_BUNCH - 1))
            beta = -8.0 - 14.0 * (j % 2)
            d0, h = crown.direction(azj, beta)
            Q = crown.c + d0 * crown.surface_dist(d0)
            ax = (hor(h).normalized() * 0.62 - UP * 0.78).normalized()
            nuts.append((Q, ax))
    for k, (Q, ax) in enumerate(nuts):
        np_ = plan["nuts"][k]
        rl = NUT_RL * np_["s"]
        rw = NUT_RW * np_["s"]
        # slide the nut out along its own axis until its deepest point in
        # the boss is NUT_BITE: the boss curves away under a hanging nut
        bite = DROP_BITE if drop_coconut and k == 0 else NUT_BITE
        t = rl - NUT_BITE - 0.04
        while t < 0.5 and nut_depth(crown, Q + ax * t, ax, rw, rl) > bite:
            t += 0.001
        centre = Q + ax * t
        zone = 0.0 if np_["tone"] < 0.62 else 1.0
        add_nut(bm, L, V, centre, ax, rw, rl, np_["tone"], zone, P_NUT, np_["ph"])
    return len(nuts)


def nut_profile(centre, ax, rw, rl, ph=0.0, samples=9):
    """The coconut's surface points as ``add_nut`` builds them."""
    e1, e2 = perp_basis(ax)
    out = []
    for u in (-0.93, -0.72, -0.42, -0.08, 0.28, 0.58, 0.82):
        rr = rw * math.sqrt(max(0.0, 1.0 - u * u)) * (1.0 - 0.20 * u)
        for j in range(samples):
            a = TAU * j / samples + ph
            r = rr * (1.0 + 0.10 * math.cos(3.0 * a - 3.0 * ph))
            out.append(centre + ax * (u * rl) + (e1 * math.cos(a) + e2 * math.sin(a)) * r)
    out.append(centre - ax * (0.97 * rl))
    return out


def nut_depth(crown, centre, ax, rw, rl):
    return max(signed_depth(crown.tree, p) for p in nut_profile(centre, ax, rw, rl, 0.0, 12))


def add_nut(bm, L, V, centre, ax, rw, rl, tone, zone, part, ph, samples=12):
    """A coconut in its husk: an egg with three blunt ridges, broad at the
    stem end and drawn to a point at the other."""
    e1, e2 = perp_basis(ax)
    us = (-0.93, -0.72, -0.42, -0.08, 0.28, 0.58, 0.82)
    rows = []
    for u in us:
        row = []
        rr = rw * math.sqrt(max(0.0, 1.0 - u * u)) * (1.0 - 0.20 * u)
        for j in range(samples):
            a = TAU * j / samples + ph
            r = rr * (1.0 + 0.10 * math.cos(3.0 * a - 3.0 * ph))
            v = bm.verts.new(centre + ax * (u * rl) + (e1 * math.cos(a) + e2 * math.sin(a)) * r)
            v[V["along"]] = 0.5 + 0.5 * u
            row.append(v)
        rows.append(row)
    for r0, r1 in zip(rows, rows[1:]):
        for j in range(samples):
            q = (j + 1) % samples
            new_face(bm, (r0[j], r0[q], r1[q], r1[j]), HUSK_IDX, L, tone, zone, part)
    stem = bm.verts.new(centre - ax * (0.97 * rl))
    tipv = bm.verts.new(centre + ax * (1.10 * rl))
    stem[V["along"]] = 0.0
    tipv[V["along"]] = 1.0
    for j in range(samples):
        q = (j + 1) % samples
        new_face(bm, (rows[0][q], rows[0][j], stem), HUSK_IDX, L, tone, zone, part)
        new_face(bm, (rows[-1][j], rows[-1][q], tipv), HUSK_IDX, L, tone, zone, part)


# --------------------------------------------------------------------------
# The beach
# --------------------------------------------------------------------------

def add_fallen_nuts(bm, L, V, plan, tree, lift):
    base = NUT_BUNCHES * NUT_PER_BUNCH
    for k, (x, y, bearing, roll) in enumerate(FALLEN_NUTS):
        np_ = plan["nuts"][base + k]
        ax = (heading(bearing) + UP * math.sin(math.radians(roll))).normalized()
        rw, rl = NUT_RW * np_["s"], NUT_RL * np_["s"]
        # rest the nut: its lowest point NUT_SINK into the sand under it
        zlow = min(p.z for p in nut_profile(Vector(), ax, rw, rl, np_["ph"], 12))
        g = sand_hit(tree, x, y)[0].z
        centre = Vector((x, y, g - zlow - NUT_SINK + lift))
        # one fresh fall, still ripening yellow-brown, and one old and dry
        add_nut(bm, L, V, centre, ax, rw, rl, np_["tone"], 1.0 + k, P_FALLEN_NUT, np_["ph"])


def add_fallen_frond(bm, L, V, plan, tree, lift):
    """A dead frond lying on the sand, its leaflets splayed flat on it."""
    ctrl = [Vector((x, y, 0.0)) for x, y in FALLEN_FROND]
    pts = []
    n = 40
    for i in range(n + 1):
        t = i / n
        a = ctrl[0].lerp(ctrl[1], t)
        b = ctrl[1].lerp(ctrl[2], t)
        p = a.lerp(b, t)
        g = sand_hit(tree, p.x, p.y)[0].z
        pts.append(Vector((p.x, p.y, g + 0.010 * (1.0 - t) + lift)))
    length = sum((b - a).length for a, b in zip(pts, pts[1:]))
    # resample to equal arc length
    res = [pts[0]]
    acc, j = 0.0, 0
    seg = [(b - a).length for a, b in zip(pts, pts[1:])]
    for k in range(1, 64):
        s = length * k / 64
        while j < len(seg) - 1 and acc + seg[j] < s:
            acc += seg[j]
            j += 1
        res.append(pts[j].lerp(pts[j + 1], min(max((s - acc) / seg[j], 0.0), 1.0)))
    res.append(pts[-1])
    tone = plan["fallen"]["tone"]
    nst = 14
    ss = [length * k / nst for k in range(nst)]
    rp = [sample_path(res, length, s)[0] for s in ss]
    add_tube(bm, rp, [rachis_radius(s, length, 0.85) for s in ss], 6, DEAD_IDX, L, V, tone, P_FALLEN,
             zone=1.0, tip=res[-1], alongs=[s / length for s in ss], phase=0.2)
    pairs = 16
    for i in range(pairs):
        u = i / (pairs - 1)
        for side in (-1.0, 1.0):
            if hash01(90, i, side) < 0.22:
                continue
            s = length * (0.18 + 0.78 * (i + 0.5) / pairs)
            p, t = sample_path(res, length, s)
            lat = UP.cross(t).normalized()
            fwd = math.radians(48.0 + 10.0 * (hash01(i, 91, side) - 0.5))
            ld = (t * math.cos(fwd) + lat * (side * math.sin(fwd))).normalized()
            f = 0.35 + 0.65 * math.sin(math.pi * (0.25 + 0.75 * u))
            Lf = 0.50 * f * (0.85 + 0.3 * hash01(side, 92, i))
            B = p + lat * (side * 0.30 * rachis_radius(s, length, 0.85))
            lp = []
            for jj in range(5):
                q = B + ld * (Lf * jj / 4) + lat * (side * 0.03 * Lf * (jj / 4) ** 2)
                g = sand_hit(tree, q.x, q.y)[0].z
                z = B.z if jj == 0 else g + 0.0040 + 0.0011 * ((2 * i + (side > 0)) % 4) + lift
                lp.append(Vector((q.x, q.y, z)))

            def width(sv, W=0.042):
                return W * (0.25 + 0.75 * smoothstep(sv, 0.0, 0.22)) * (1.0 - 0.55 * sv ** 1.5)

            add_blade(bm, lp, t, width, 0.22, 0.0010, 0.3 * (hash01(i, 93, side) - 0.5), DEAD_IDX, L, V,
                      0.5 * tone + 0.5 * hash01(i, 94, side), 2.0, P_FALLEN_LEAF, UP)


def lying_path(tree, a, b, wig, amp, r0, r1, n, bed):
    a = Vector((a[0], a[1], 0.0))
    b = Vector((b[0], b[1], 0.0))
    side = Vector((-(b - a).y, (b - a).x, 0.0)).normalized()
    pts, radii = [], []
    for k in range(n):
        t = k / (n - 1)
        p = a.lerp(b, t) + side * (amp * wig[k % len(wig)] * math.sin(math.pi * t) + 0.03 * math.sin(2.7 * t))
        r = r0 + (r1 - r0) * t ** 0.8
        g, _nn = sand_hit(tree, p.x, p.y)
        p.z = g.z + (1.0 - bed) * r
        pts.append(p)
        radii.append(r)
    return pts, radii


def add_driftwood(bm, L, V, plan, tree, lift):
    dp = plan["drift"]
    pts, radii = lying_path(tree, DRIFT[0], DRIFT[1], dp["wig"], 0.05, 0.052, 0.026, 12, 0.35)
    pts = [p + UP * lift for p in pts]
    d = (pts[-1] - pts[-2]).normalized()

    def gnarl(i, a):
        return 1.0 + 0.10 * math.sin(3.0 * a + 1.3 * i) + 0.05 * math.sin(5.0 * a - 0.7 * i)

    add_tube(bm, pts, radii, 9, DRIFT_IDX, L, V, dp["tone"], P_DRIFT, tip=pts[-1] + d * 0.05 + UP * 0.004,
             alongs=[k / 11.0 for k in range(12)], shape=gnarl)
    # a snapped branch stub off the log
    p = pts[4]
    dd = (pts[5] - pts[3]).normalized()
    side = UP.cross(dd).normalized()
    tw = (dd * 0.45 + side * 0.80 + UP * 0.35).normalized()
    start = p - tw * (0.4 * radii[4])
    sp = [start + tw * (0.20 * f) + UP * (-0.02 * f * f) for f in (0.0, 0.4, 0.75, 1.0)]
    add_tube(bm, sp, [0.022, 0.018, 0.015, 0.012], 7, DRIFT_IDX, L, V, dp["tone"], P_DRIFT)


def add_scallop(bm, L, V, x, y, r, bearing, tone, tilt, tree, lift):
    """A scallop shell, domed and ribbed, lying cup down on the sand."""
    n = 24
    fwd = heading(bearing)
    side = UP.cross(fwd)
    g, nrm = sand_hit(tree, x, y)
    up = (nrm + side * tilt).normalized()
    hinge = Vector((x, y, g.z)) - fwd * (0.45 * r)
    top_rows, bot_rows = [], []
    for rn in (0.45, 0.80, 1.0):
        rt, rb = [], []
        for j in range(n):
            a = math.radians(-78.0 + 156.0 * j / (n - 1))
            wav = 1.0 + 0.05 * math.cos(16.0 * a)
            p = hinge + (fwd * math.cos(a) + side * math.sin(a)) * (r * rn * wav)
            dome = 0.30 * r * (1.0 - rn * rn) + 0.004 * max(0.0, math.cos(16.0 * a)) * rn
            rt.append(bm.verts.new(p + up * (dome + 0.002 - 0.006 + lift)))
            rb.append(bm.verts.new(p + up * (dome * 0.55 - 0.006 + lift) - up * 0.0015))
        top_rows.append(rt)
        bot_rows.append(rb)
    ht = bm.verts.new(hinge + up * (0.30 * r + 0.002 - 0.006 + lift))
    hb = bm.verts.new(hinge + up * (0.30 * r * 0.55 - 0.006 + lift) - up * 0.0015)
    for v in [ht, hb] + [v for row in top_rows + bot_rows for v in row]:
        v[V["along"]] = 0.0
    for rows, centre, flip in ((top_rows, ht, False), (bot_rows, hb, True)):
        for j in range(n - 1):
            tri = (centre, rows[0][j], rows[0][j + 1])
            new_face(bm, tri[::-1] if flip else tri, SHELL_IDX, L, tone, 0.0, P_SHELL)
        for r0, r1 in zip(rows, rows[1:]):
            for j in range(n - 1):
                quad = (r0[j], r1[j], r1[j + 1], r0[j + 1])
                new_face(bm, quad[::-1] if flip else quad, SHELL_IDX, L, tone, 0.0, P_SHELL)
    # close the rim and the two straight hinge edges
    rim_t = [ht] + top_rows[0][:1] + top_rows[1][:1] + top_rows[2]
    rim_t += [top_rows[1][-1], top_rows[0][-1]]
    rim_b = [hb] + bot_rows[0][:1] + bot_rows[1][:1] + bot_rows[2]
    rim_b += [bot_rows[1][-1], bot_rows[0][-1]]
    m = len(rim_t)
    for j in range(m):
        q = (j + 1) % m
        new_face(bm, (rim_t[q], rim_t[j], rim_b[j], rim_b[q]), SHELL_IDX, L, tone, 0.0, P_SHELL)


def add_auger(bm, L, V, x, y, length, bearing, tone, tree, lift):
    """A slender auger shell: a tapered cone of whorls lying on the sand."""
    d = heading(bearing)
    g0 = sand_hit(tree, x, y)[0].z
    g1 = sand_hit(tree, x + d.x * length, y + d.y * length)[0].z
    base = Vector((x, y, g0))
    rise = (g1 - g0) / length
    ax = (d + UP * rise).normalized()
    n = 12
    pts, radii = [], []
    for i in range(n):
        t = i / (n - 1) * 0.94
        r = 0.16 * length * (1.0 - t) ** 1.1 * (1.0 + 0.10 * math.sin(TAU * 6.0 * t))
        pts.append(base + ax * (length * t) + UP * (0.6 * 0.16 * length * (1.0 - t) - 0.004 + lift))
        radii.append(r)
    tip = base + ax * length + UP * (-0.002 + lift)
    add_tube(bm, pts, radii, 7, SHELL_IDX, L, V, tone, P_SHELL, zone=1.0, tip=tip,
             alongs=[i / (n - 1) for i in range(n)], phase=0.5)


def add_strap(bm, pts, width, thick, hd, twist, mat, L, V, tone, part, roll=0.0):
    """A V-section grass blade along ``pts`` ending in a point."""
    n = len(pts) - 1
    rings = []
    for i in range(n):
        s = i / n
        tan = (pts[i + 1] - pts[max(i - 1, 0)]).normalized()
        side = tan.cross(hd)
        if side.length < 1e-6:
            side = perp_basis(tan)[0]
        side.normalize()
        a = roll + twist * s
        side = (side * math.cos(a) + tan.cross(side) * math.sin(a)).normalized()
        nrm = side.cross(tan).normalized()
        w = 0.5 * width(s)
        th = thick(s)
        ring = [bm.verts.new(pts[i] - side * w + nrm * th), bm.verts.new(pts[i] + side * w + nrm * th),
                bm.verts.new(pts[i] - nrm * th)]
        for v in ring:
            v[V["along"]] = s
        rings.append(ring)
    tip = bm.verts.new(pts[-1])
    tip[V["along"]] = 1.0
    new_face(bm, list(reversed(rings[0])), mat, L, tone, 0.0, part)
    for i in range(n - 1):
        r0, r1 = rings[i], rings[i + 1]
        for q in range(3):
            w = (q + 1) % 3
            new_face(bm, (r0[q], r1[q], r1[w], r0[w]), mat, L, tone, 0.0, part)
    last = rings[-1]
    for q in range(3):
        new_face(bm, (last[q], tip, last[(q + 1) % 3]), mat, L, tone, 0.0, part)


def add_tuft(bm, L, V, x, y, size, tp, tree, lift):
    n = int(round(22 * size))
    h0 = 0.22 + 0.22 * size
    spread = 0.025 + 0.03 * size
    for k, bl in enumerate(tp["blades"][:n]):
        ox, oy = bl["off"]
        b, _n = sand_hit(tree, x + tp["j"][0] + ox * spread, y + tp["j"][1] + oy * spread)
        b = b - UP * (0.018 + 0.00053 * k) + UP * lift
        h = h0 * bl["h"] + 0.02
        hd = Vector((math.cos(bl["yaw"]), math.sin(bl["yaw"]), 0.0))
        pts = []
        for i in range(5):
            t = i / 4
            pts.append(b + UP * (h * (t - 0.45 * bl["lean"] * t * t))
                       + hd * (h * bl["lean"] * (0.12 * t + t * t)))
        W = 0.0080 * bl["w"]

        def width(s, W=W):
            return W * (1.0 - 0.75 * s ** 1.3)

        def thick(s):
            return 0.0010 * (1.0 - 0.6 * s)

        add_strap(bm, pts, width, thick, hd, bl["tw"], GRASS_IDX, L, V,
                  0.6 * tp["tone"] + 0.4 * bl["tone"], P_GRASS, roll=0.18 * math.sin(3.7 * k + bl["yaw"]))


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

def build_palm_mesh(name, plan, detail="low", short_petioles=False, drop_coconut=False, short_roots=False,
                    bunch_rings=False, perch_trunk=False, float_nuts=False, float_cover=False):
    bm = bmesh.new()
    try:
        L = {"tone": bm.faces.layers.float.new("Tone"),
             "zone": bm.faces.layers.float.new("Zone"),
             "part": bm.faces.layers.int.new("Part")}
        V = {"skirt": bm.verts.layers.float.new("Skirt"),
             "along": bm.verts.layers.float.new("Along")}

        add_sand(bm, L, V, DISC_N[detail])
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        tree = BVHTree.FromBMesh(bm)

        tr = Trunk(perch=perch_trunk)
        add_trunk(bm, L, V, tr, plan, detail, bunch_rings)
        add_roots(bm, L, V, tr, plan, tree, short_roots)
        crown = Crown(tr, detail)
        add_crown(bm, L, V, tr, plan, crown, short_petioles, drop_coconut)
        add_fallen_nuts(bm, L, V, plan, tree, FLOAT_NUTS if float_nuts else 0.0)
        cover = FLOAT_COVER if float_cover else 0.0
        add_fallen_frond(bm, L, V, plan, tree, cover)
        add_driftwood(bm, L, V, plan, tree, cover)
        shells = plan["shells"]
        for k, (x, y, r, b) in enumerate(SCALLOPS):
            add_scallop(bm, L, V, x, y, r, b, shells[k]["tone"], shells[k]["tilt"], tree, cover)
        for k, (x, y, ln, b) in enumerate(AUGERS):
            add_auger(bm, L, V, x, y, ln, b, shells[len(SCALLOPS) + k]["tone"], tree, cover)
        for (x, y, size), tp in zip(TUFTS, plan["tufts"]):
            add_tuft(bm, L, V, x, y, size, tp, tree, cover)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy
            v.co.z -= zmin

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        # Everything smooth-shaded; every material boundary and every fold
        # sharper than 62 degrees a hard edge, so a leaflet's edges and a
        # shell's rim stay crisp while a six-sided rachis stays round; 30 on
        # the coconuts, so the husk's three ridges read as facets.
        part = L["part"]
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats_ = {f.material_index for f in edge.link_faces}
            if len(mats_) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                nut = edge.link_faces[0][part] in (P_NUT, P_FALLEN_NUT)
                edge.smooth = edge.calc_face_angle() < math.radians(30.0 if nut else 62.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def build_collider_source(name, low):
    """The lower trunk, coarse: players walk the sand and brush through the
    fronds, but not through the bole."""
    tr = Trunk()
    bm = bmesh.new()
    try:
        for k in range(9):
            s = 2.4 * k / 8
            for j in range(10):
                bm.verts.new(tr.surface(s, TAU * j / 10))
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

def enabled_socket(sockets, name):
    """The one enabled socket called ``name`` (Mix / Map Range carry one per
    data type under one name; identifiers changed in 5.2)."""
    for sock in sockets:
        if sock.name == name and sock.enabled:
            return sock
    return sockets[name]


def surface(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = 0.0
    coord = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    return mat, nt, bsdf, coord


def mapping(nt, vec, scale=(1.0, 1.0, 1.0), rot=(0.0, 0.0, 0.0)):
    node = nt.nodes.new("ShaderNodeMapping")
    node.inputs["Scale"].default_value = scale
    node.inputs["Rotation"].default_value = rot
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Vector"]


def noise(nt, vec, scale, detail, roughness):
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = roughness
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]


def wave(nt, vec, scale, distortion, detail):
    node = nt.nodes.new("ShaderNodeTexWave")
    node.wave_type = "BANDS"
    node.bands_direction = "X"
    node.inputs["Scale"].default_value = scale
    node.inputs["Distortion"].default_value = distortion
    node.inputs["Detail"].default_value = detail
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]


def voronoi_color(nt, vec, scale):
    node = nt.nodes.new("ShaderNodeTexVoronoi")
    node.inputs["Scale"].default_value = scale
    nt.links.new(vec, node.inputs["Vector"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(node.outputs["Color"], sep.inputs["Color"])
    return sep.outputs[0], sep.outputs[1], node.outputs["Distance"]


def ramp(nt, fac, stops):
    node = nt.nodes.new("ShaderNodeValToRGB")
    els = node.color_ramp.elements
    els[0].position = stops[0][0]
    els[0].color = (*stops[0][1], 1.0)
    els[1].position = stops[-1][0]
    els[1].color = (*stops[-1][1], 1.0)
    for pos, rgb in stops[1:-1]:
        els.new(pos).color = (*rgb, 1.0)
    nt.links.new(fac, node.inputs["Fac"])
    return node.outputs["Color"]


def remap(nt, value, from_lo, from_hi, to_lo, to_hi):
    node = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(value, enabled_socket(node.inputs, "Value"))
    enabled_socket(node.inputs, "From Min").default_value = from_lo
    enabled_socket(node.inputs, "From Max").default_value = from_hi
    enabled_socket(node.inputs, "To Min").default_value = to_lo
    enabled_socket(node.inputs, "To Max").default_value = to_hi
    return enabled_socket(node.outputs, "Result")


def math_node(nt, op, a, b):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    for i, value in enumerate((a, b)):
        if isinstance(value, (int, float)):
            node.inputs[i].default_value = value
        else:
            nt.links.new(value, node.inputs[i])
    return node.outputs[0]


def mix_color(nt, a, b, fac):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    if isinstance(fac, (int, float)):
        enabled_socket(node.inputs, "Factor").default_value = fac
    else:
        nt.links.new(fac, enabled_socket(node.inputs, "Factor"))
    for nm, value in (("A", a), ("B", b)):
        sock = enabled_socket(node.inputs, nm)
        if isinstance(value, tuple):
            sock.default_value = (*value, 1.0)
        else:
            nt.links.new(value, sock)
    return enabled_socket(node.outputs, "Result")


def attr(nt, name):
    node = nt.nodes.new("ShaderNodeAttribute")
    node.attribute_type = "GEOMETRY"
    node.attribute_name = name
    return node.outputs["Fac"]


def height(nt, coord):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    return sep.outputs["Z"]


def bump(nt, bsdf, h, strength, distance):
    node = nt.nodes.new("ShaderNodeBump")
    node.inputs["Strength"].default_value = strength
    node.inputs["Distance"].default_value = distance
    nt.links.new(h, node.inputs["Height"])
    nt.links.new(node.outputs["Normal"], bsdf.inputs["Normal"])


def band(nt, value, lo, hi):
    """1 across [lo, hi] of ``value`` with soft shoulders, 0 elsewhere."""
    return math_node(nt, "MULTIPLY", remap(nt, value, lo - 0.45, lo - 0.05, 0.0, 1.0),
                     remap(nt, value, hi + 0.05, hi + 0.45, 1.0, 0.0))


def sand_material():
    mat, nt, bsdf, coord = surface("BeachSand")
    drift = noise(nt, coord, 1.3, 4.0, 0.55)
    col = ramp(nt, drift, ((0.30, (0.190, 0.152, 0.106)), (0.55, (0.228, 0.186, 0.132)),
                           (0.80, (0.250, 0.206, 0.148))))
    # wind ripples: low bands across the drift, their lee sides a shade darker
    rip = wave(nt, mapping(nt, coord, rot=(0.0, 0.0, 0.35)), 6.5, 5.0, 2.0)
    col = mix_color(nt, col, (0.150, 0.118, 0.080), remap(nt, rip, 0.0, 0.45, 0.40, 0.0))
    # shell grit and dark mineral grains
    g0, g1, _gd = voronoi_color(nt, coord, 80.0)
    col = mix_color(nt, col, (0.110, 0.095, 0.075), remap(nt, g0, 0.92, 0.95, 0.0, 0.45))
    col = mix_color(nt, col, (0.290, 0.260, 0.215), remap(nt, g1, 0.92, 0.95, 0.0, 0.30))
    # the disc's cut edge: damp darker sand under the dry crust
    wob = noise(nt, coord, 5.0, 3.0, 0.5)
    hz = math_node(nt, "ADD", remap(nt, height(nt, coord), 0.0, MOUND_Z * 0.7, 0.0, 1.0),
                   remap(nt, wob, 0.0, 1.0, -0.08, 0.08))
    prof = ramp(nt, hz, ((0.00, (0.085, 0.070, 0.055)), (0.35, (0.130, 0.100, 0.070)),
                         (0.70, (0.200, 0.165, 0.118)), (1.00, (0.228, 0.186, 0.132))))
    col = mix_color(nt, col, prof, attr(nt, "Skirt"))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.94
    bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "MULTIPLY", rip, 0.8),
                             remap(nt, g0, 0.92, 0.95, 0.0, 0.4)), 0.40, 0.005)
    return mat


def bark_material():
    """Palm bark, one substance: zone 0 the trunk, 1 a leaf-scar ring, 2 a
    root, 3 the fibrous boss of leaf bases."""
    mat, nt, bsdf, coord = surface("PalmBark")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    along = attr(nt, "Along")
    # vertical fissures: noise stretched along the trunk
    fis = noise(nt, mapping(nt, coord, scale=(26.0, 26.0, 1.2)), 2.5, 5.0, 0.6)
    col = ramp(nt, fis, ((0.30, (0.052, 0.045, 0.038)), (0.55, (0.120, 0.106, 0.090)),
                         (0.80, (0.165, 0.150, 0.130))))
    col = mix_color(nt, col, (0.10, 0.075, 0.055), remap(nt, tone, 0.0, 1.0, 0.0, 0.35))
    # weathered grey higher up, a darker, damper foot
    col = mix_color(nt, col, (0.150, 0.145, 0.135), remap(nt, along, 0.3, 0.9, 0.0, 0.35))
    col = mix_color(nt, col, (0.060, 0.048, 0.036), remap(nt, along, 0.06, 0.0, 0.0, 0.6))
    blot = noise(nt, coord, 4.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.080, 0.070, 0.060), remap(nt, blot, 0.55, 0.70, 0.0, 0.4))
    # rings: a dark scar line on a paler rim
    ring = mix_color(nt, (0.050, 0.040, 0.032), (0.140, 0.125, 0.105), remap(nt, tone, 0.0, 1.0, 0.2, 0.7))
    col = mix_color(nt, col, ring, math_node(nt, "MULTIPLY", band(nt, zone, 1.0, 1.0), 0.55))
    # roots: reddish brown, dusted with sand toward the tips
    root = mix_color(nt, (0.090, 0.058, 0.040), (0.170, 0.140, 0.100), remap(nt, along, 0.5, 1.0, 0.0, 0.8))
    col = mix_color(nt, col, root, band(nt, zone, 2.0, 2.0))
    # the boss: brown fibrous mat of leaf-base sheaths
    fib = noise(nt, mapping(nt, coord, scale=(60.0, 60.0, 8.0)), 2.0, 4.0, 0.6)
    boss = ramp(nt, fib, ((0.30, (0.040, 0.028, 0.018)), (0.60, (0.120, 0.085, 0.050)),
                          (0.85, (0.190, 0.150, 0.100))))
    col = mix_color(nt, col, boss, band(nt, zone, 3.0, 3.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    bump(nt, bsdf, math_node(nt, "ADD", fis, math_node(nt, "MULTIPLY", fib, 0.5)), 0.45, 0.004)
    return mat


def frond_material():
    """Live fronds: zone 0 a leaflet, 1 the rachis, 2 an unopened spear."""
    mat, nt, bsdf, coord = surface("PalmFrond")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    along = attr(nt, "Along")
    leaf = ramp(nt, tone, ((0.0, (0.050, 0.075, 0.030)), (0.5, (0.068, 0.092, 0.036)),
                           (0.93, (0.090, 0.105, 0.040)), (1.0, (0.150, 0.120, 0.050))))
    # a paler midrib base, sun-yellowed and brown-frayed tips
    leaf = mix_color(nt, leaf, (0.120, 0.120, 0.050), remap(nt, along, 0.15, 0.0, 0.0, 0.45))
    leaf = mix_color(nt, leaf, (0.140, 0.110, 0.050), remap(nt, along, 0.78, 1.0, 0.0, 0.6))
    streak = noise(nt, mapping(nt, coord, scale=(30.0, 30.0, 30.0)), 2.0, 3.0, 0.5)
    leaf = mix_color(nt, leaf, (0.040, 0.058, 0.026), remap(nt, streak, 0.45, 0.65, 0.0, 0.4))
    rachis = mix_color(nt, (0.160, 0.150, 0.070), (0.090, 0.110, 0.045), remap(nt, along, 0.0, 0.6, 0.0, 1.0))
    spear = (0.150, 0.160, 0.070)
    col = mix_color(nt, leaf, rachis, band(nt, zone, 1.0, 1.0))
    col = mix_color(nt, col, spear, band(nt, zone, 2.0, 2.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.62
    bsdf.inputs["Subsurface Weight"].default_value = 0.06
    bump(nt, bsdf, streak, 0.10, 0.002)
    return mat


def dead_material():
    """Dead fronds, hanging and fallen: straw to grey-brown."""
    mat, nt, bsdf, coord = surface("DeadFrond")
    tone = attr(nt, "Tone")
    along = attr(nt, "Along")
    col = ramp(nt, tone, ((0.0, (0.120, 0.085, 0.045)), (0.5, (0.200, 0.150, 0.085)),
                          (1.0, (0.170, 0.150, 0.120))))
    col = mix_color(nt, col, (0.070, 0.050, 0.032), remap(nt, along, 0.75, 1.0, 0.0, 0.6))
    streak = noise(nt, mapping(nt, coord, scale=(40.0, 40.0, 40.0)), 2.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.080, 0.060, 0.040), remap(nt, streak, 0.45, 0.65, 0.0, 0.5))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.80
    bump(nt, bsdf, streak, 0.15, 0.002)
    return mat


def husk_material():
    """Coconut husk: zone 0 green, 1 ripening yellow-brown, 2 fallen and dry."""
    mat, nt, bsdf, coord = surface("CoconutHusk")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    along = attr(nt, "Along")
    green = ramp(nt, tone, ((0.0, (0.070, 0.095, 0.030)), (1.0, (0.095, 0.110, 0.035))))
    ripe = ramp(nt, tone, ((0.0, (0.240, 0.150, 0.045)), (1.0, (0.200, 0.110, 0.035))))
    dry = ramp(nt, tone, ((0.0, (0.130, 0.080, 0.042)), (1.0, (0.175, 0.115, 0.065))))
    col = mix_color(nt, green, ripe, remap(nt, zone, 0.4, 0.6, 0.0, 1.0))
    col = mix_color(nt, col, dry, remap(nt, zone, 1.4, 1.6, 0.0, 1.0))
    # the stem end browned, the husk mottled
    col = mix_color(nt, col, (0.080, 0.055, 0.030), remap(nt, along, 0.12, 0.0, 0.0, 0.8))
    mot = noise(nt, mapping(nt, coord, scale=(40.0, 40.0, 12.0)), 2.0, 4.0, 0.6)
    col = mix_color(nt, col, (0.050, 0.045, 0.025), remap(nt, mot, 0.58, 0.72, 0.0, 0.35))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, zone, 0.0, 2.0, 0.42, 0.80), bsdf.inputs["Roughness"])
    bump(nt, bsdf, mot, 0.12, 0.002)
    return mat


def shell_material():
    """Seashells: zone 0 a scallop, 1 an auger."""
    mat, nt, bsdf, coord = surface("Seashell")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    col = ramp(nt, tone, ((0.0, (0.52, 0.44, 0.36)), (0.5, (0.58, 0.46, 0.40)), (1.0, (0.48, 0.40, 0.30))))
    bands_ = wave(nt, mapping(nt, coord, scale=(1.0, 1.0, 1.0)), 60.0, 2.0, 1.0)
    col = mix_color(nt, col, (0.36, 0.22, 0.16), remap(nt, bands_, 0.55, 0.85, 0.0, 0.45))
    col = mix_color(nt, col, (0.30, 0.24, 0.18), math_node(nt, "MULTIPLY", band(nt, zone, 1.0, 1.0), 0.5))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.40
    return mat


def driftwood_material():
    mat, nt, bsdf, coord = surface("Driftwood")
    tone = attr(nt, "Tone")
    ang = -math.atan2(DRIFT[1][1] - DRIFT[0][1], DRIFT[1][0] - DRIFT[0][0])
    g = mapping(nt, coord, scale=(3.0, 55.0, 55.0), rot=(0.0, 0.0, ang))
    grain = noise(nt, g, 1.5, 6.0, 0.6)
    col = ramp(nt, grain, ((0.30, (0.160, 0.150, 0.135)), (0.50, (0.255, 0.240, 0.215)),
                           (0.72, (0.320, 0.305, 0.275))))
    col = mix_color(nt, col, (0.22, 0.19, 0.15), remap(nt, tone, 0.0, 1.0, 0.0, 0.3))
    cracks = noise(nt, mapping(nt, g, scale=(0.7, 0.5, 0.5)), 3.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.050, 0.045, 0.040), remap(nt, cracks, 0.60, 0.68, 0.0, 0.8))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    bump(nt, bsdf, math_node(nt, "ADD", grain, cracks), 0.40, 0.003)
    return mat


def grass_material():
    mat, nt, bsdf, coord = surface("SeaGrass")
    tone = attr(nt, "Tone")
    along = attr(nt, "Along")
    col = ramp(nt, tone, ((0.0, (0.080, 0.095, 0.040)), (0.5, (0.120, 0.120, 0.055)),
                          (1.0, (0.180, 0.160, 0.085))))
    col = mix_color(nt, col, (0.10, 0.09, 0.06), remap(nt, along, 0.25, 0.0, 0.0, 0.6))
    col = mix_color(nt, col, (0.24, 0.21, 0.14), remap(nt, along, 0.7, 1.0, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.70
    return mat


def palm_materials():
    """Eight slots, in index order: shared by the check and the render."""
    return (sand_material(), bark_material(), frond_material(), dead_material(), husk_material(),
            shell_material(), driftwood_material(), grass_material())


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

def vertex_bbox(me):
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
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
            if b[1] >= a[3] or a[1] >= b[3]:
                continue
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
            if report is not None and len(report) < 20:
                report.append((si, sj, tuple(round(c, 3) for c in ci)))
    return hits


class Shell:
    def __init__(self, me, idx, verts, polys, part):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.part = part
        remap_ = {vi: n for n, vi in enumerate(verts)}
        self.faces = [[remap_[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.faces)
        self.centre = sum(pts, Vector()) / len(pts)

    def volume(self):
        """Signed volume and volume centroid of the closed shell."""
        vol = 0.0
        acc = Vector()
        for f in self.faces:
            a = self.pts[f[0]]
            for i in range(1, len(f) - 1):
                b, c = self.pts[f[i]], self.pts[f[i + 1]]
                v6 = a.dot(b.cross(c))
                vol += v6
                acc += (a + b + c) * v6
        if abs(vol) < 1e-15:
            return 0.0, self.centre
        return vol / 6.0, acc / (4.0 * vol)


def classify(me):
    groups = shells(me)
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    part_attr = me.attributes.get("Part")
    pvals = [0] * len(me.polygons)
    if part_attr is not None:
        part_attr.data.foreach_get("value", pvals)
    polys = [[] for _ in groups]
    votes = [{} for _ in groups]
    for p, pv in zip(me.polygons, pvals):
        s = owner[p.vertices[0]]
        polys[s].append(p)
        votes[s][pv] = votes[s].get(pv, 0) + 1
    parts = []
    for i, g in enumerate(groups):
        part = max(votes[i], key=votes[i].get) if votes[i] else 0
        parts.append(Shell(me, i, g, polys[i], part))
    out = {"all": parts, "groups": groups}
    for pid in range(1, 18):
        out[pid] = [s for s in parts if s.part == pid]
    return out


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 8.0)), Vector((0.0, 0.0, -1.0)), 20.0)
    return None if loc is None else loc.z


PARITY_DIRS = (Vector((0.31, 0.47, 0.83)).normalized(), Vector((-0.62, 0.21, -0.75)).normalized(),
               Vector((0.55, -0.79, 0.27)).normalized())


def inside(tree, p):
    """Ray parity, by majority over three directions: an odd number of
    crossings out of a closed shell. One ray that grazes an edge counts it
    twice; three rays do not all graze."""
    votes = 0
    for d in PARITY_DIRS:
        count, o = 0, p.copy()
        for _ in range(64):
            loc, _n, _i, _d = tree.ray_cast(o, d, 20.0)
            if loc is None:
                break
            count += 1
            o = loc + d * 1e-6
        votes += count % 2
    return votes >= 2


def signed_depth(tree, p):
    """How far ``p`` lies inside the closed shell of ``tree`` (negative outside)."""
    loc, _nrm, _i, dist = tree.find_nearest(p)
    if loc is None:
        return -9.0
    return dist if inside(tree, p) else -dist


def near_box(s, lo, hi, pad):
    return not (s.hi.x < lo.x - pad or s.lo.x > hi.x + pad or s.hi.y < lo.y - pad or s.lo.y > hi.y + pad
                or s.hi.z < lo.z - pad or s.lo.z > hi.z + pad)


def seat_audit(fronds, boss):
    """Every frond's rachis (and spear): its deepest vertex inside the boss."""
    out = []
    for s in fronds:
        best = -9.0
        for p in s.pts:
            if (p - boss.centre).length > 0.6:
                continue
            best = max(best, signed_depth(boss.tree, p))
        out.append(best)
    return out


def nut_audit(nuts, boss):
    """Every attached coconut: its deepest vertex inside the boss, and its
    centre's height against the boss's centre."""
    bites, under = [], []
    for s in nuts:
        bites.append(max(signed_depth(boss.tree, p) for p in s.pts))
        under.append(boss.centre.z - s.centre.z)
    return bites, under


def slab_centroid(pts, z0, z1):
    sel = [p for p in pts if z0 <= p.z <= z1]
    if not sel:
        return None
    return sum(sel, Vector()) / len(sel)


def trunk_audit(trunk, sand):
    """The foot's centre (a slab over the sand), the top's centre, the
    height of the trunk over the sand at its foot and the crown's offset."""
    zlo = min(p.z for p in trunk.pts)
    zhi = max(p.z for p in trunk.pts)
    g = ray_down(sand.tree, trunk.centre.x, trunk.centre.y)
    probe = [p for p in trunk.pts if p.z < zlo + 0.4]
    foot_xy = sum(probe, Vector()) / len(probe)
    g = ray_down(sand.tree, foot_xy.x, foot_xy.y) or 0.0
    c0 = slab_centroid(trunk.pts, g + 0.55, g + 0.75)
    c1 = slab_centroid(trunk.pts, zhi - 0.40, zhi - 0.20)
    return c0, c1, zhi - g, hor(c1 - c0).length


def convex_hull_2d(points):
    pts = sorted(set((round(p[0], 9), round(p[1], 9)) for p in points))
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


def hull_margin(hull, q):
    """Signed distance from ``q`` to the edge of a CCW hull (positive inside)."""
    best = 9.0
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        ex, ey = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ex, ey)
        d = (ex * (q[1] - a[1]) - ey * (q[0] - a[0])) / ln
        best = min(best, d)
    return best


def tip_audit(cls, roots, sand, c0):
    """The crown's mass over the root plate. The mass centre is the volume
    centroid of every closed shell of trunk and crown (uniform density);
    the root plate is the hull, in plan, of where each root enters the
    sand — its farthest vertex from the foot that lies under the sand."""
    vol = 0.0
    acc = Vector()
    for s in cls["all"]:
        if s.part in CROWN_PARTS:
            v, c = s.volume()
            vol += v
            acc += c * v
    m = acc / vol
    entries, tips = [], []
    for s in roots:
        under = []
        for p in s.pts:
            g = ray_down(sand.tree, p.x, p.y)
            if g is not None and p.z < g:
                under.append((hor(p - c0).length, p, g - p.z))
        if not under:
            entries.append(None)
            tips.append(-9.0)
            continue
        far = max(under, key=lambda e: e[0])
        entries.append(far[1])
        tips.append(max(e[2] for e in under))
    hull = convex_hull_2d([(p.x, p.y) for p in entries if p is not None])
    margin = hull_margin(hull, (m.x, m.y)) if len(hull) >= 3 else -9.0
    reach = [hor(p - c0).length for p in entries if p is not None]
    return m, hor(m - c0).length, margin, reach, tips


def ring_audit(rings):
    cs = sorted((s.centre for s in rings), key=lambda c: c.z)
    gaps = [(b - a).length for a, b in zip(cs, cs[1:])]
    return gaps


def bed_audit(body, sand, sectors=8):
    """A body's most-buried vertex in each sector round its foot, under the
    sand straight above it: the shallowest sector."""
    zlo = min(p.z for p in body.pts)
    foot = [p for p in body.pts if p.z < zlo + 0.02]
    c = sum(foot, Vector()) / len(foot)
    best = [-9.0] * sectors
    for p in body.pts:
        if p.z > zlo + 0.30:
            continue
        g = ray_down(sand.tree, p.x, p.y)
        if g is None:
            continue
        k = int(((math.atan2(p.y - c.y, p.x - c.x) + math.pi) / TAU) * sectors) % sectors
        best[k] = max(best[k], g - p.z)
    return min(best)


def rest_audit(nuts, sand):
    out = []
    for s in nuts:
        low = min(s.pts, key=lambda p: p.z)
        g = ray_down(sand.tree, low.x, low.y)
        out.append(-9.0 if g is None else g - low.z)
    return out


def union_components(parts):
    n = len(parts)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(n), key=lambda i: parts[i].lo.x)
    for oi, i in enumerate(order):
        a = parts[i]
        for j in order[oi + 1:]:
            b = parts[j]
            if b.lo.x > a.hi.x:
                break
            if (a.lo.y > b.hi.y or b.lo.y > a.hi.y or a.lo.z > b.hi.z or b.lo.z > a.hi.z):
                continue
            if find(i) == find(j):
                continue
            if a.tree.overlap(b.tree):
                parent[find(i)] = find(j)
    return [find(i) for i in range(n)]


def cover_audit(cls):
    """Every shell joined to the sand through BVH overlaps: how many are not."""
    sand = cls[P_SAND][0]
    # a shell with no faces is a loose vertex: the hygiene budget's, not this one's
    others = [s for s in cls["all"] if s is not sand and s.faces]
    parts = [sand] + others
    roots = union_components(parts)
    loose = [p for p, r in zip(parts[1:], roots[1:]) if r != roots[0]]
    kinds = {}
    for p in loose:
        kinds[p.part] = kinds.get(p.part, 0) + 1
    return len(others), len(loose), kinds


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
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
    img = bpy.data.images.new("PalmNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = SAND_IDX
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


def rng_(vals):
    return f"[{min(vals):.4f},{max(vals):.4f}]" if vals else "[]"


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    plan = plan_beach()
    low = build_palm_mesh("PalmLow", plan, "low", **flags)
    high = build_palm_mesh("PalmHigh", plan, "high", **flags)
    mats = palm_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    sand_mat = mats[SAND_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none2 = (None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("palm mesh did not build", 3),) + none2

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat = len(slots)
    distinct_mats = len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    print(f"measured mat_index_counts={dict(sorted(idx_counts.items()))}")
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = vertex_bbox(low.data)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]
    hyg = hygiene_audit(low.data)
    cls = classify(low.data)
    zrep = []
    zf = zfight_pairs(low.data, cls["groups"], zrep)
    if len(cls[P_SAND]) != 1 or len(cls[P_TRUNK]) != 1 or len(cls[P_BOSS]) != 1:
        return (fail(f"sand, trunk or boss shell not found: {len(cls[P_SAND])}, {len(cls[P_TRUNK])}, "
                     f"{len(cls[P_BOSS])}", 3),) + none2
    sand, trunk, boss = cls[P_SAND][0], cls[P_TRUNK][0], cls[P_BOSS][0]
    fronds = cls[P_RACHIS] + cls[P_SPEAR] + cls[P_DEAD]
    seats = seat_audit(fronds, boss)
    nut_bites, nut_under = nut_audit(cls[P_NUT], boss)
    c0, c1, trunk_h, crown_off = trunk_audit(trunk, sand)
    mass, mass_off, margin, reach, root_tips = tip_audit(cls, cls[P_ROOT], sand, c0)
    gaps = ring_audit(cls[P_RING])
    pitch = sum(gaps) / len(gaps) if gaps else 0.0
    spread = (max(gaps) - min(gaps)) if gaps else 9.0
    trunk_bed = bed_audit(trunk, sand)
    rests = rest_audit(cls[P_FALLEN_NUT], sand)
    nshells, nloose, loose_kinds = cover_audit(cls)

    img, tex = setup_bake_image(low, sand_mat)
    if img is None:
        return (fail("palm has no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "PalmLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "PalmLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("PalmColSrc", low)
    collider = convex_hull_collider(collider_src, "PalmCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_palm_tree_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    n_fronds = N_FRONDS + N_DEAD + 2
    n_nuts = NUT_BUNCHES * NUT_PER_BUNCH
    # every piece-specific budget, pass or fail, so a falsifier run shows
    # that it breaks exactly one
    budgets = {
        "grounded": bb[2] <= ZMIN_EPS,
        "fronds": len(fronds) == n_fronds and bool(seats) and SEAT_MIN <= min(seats)
        and max(seats) <= SEAT_MAX,
        "coconuts": len(nut_bites) == n_nuts and bool(nut_bites) and NUT_BITE_MIN <= min(nut_bites)
        and max(nut_bites) <= NUT_BITE_MAX and min(nut_under) > 0.0,
        "trunk": abs(trunk_h - TRUNK_H) <= TRUNK_H_TOL
        and CROWN_OFF_BAND[0] <= crown_off <= CROWN_OFF_BAND[1] and margin >= TIP_MARGIN_MIN
        and len(reach) == N_ROOTS,
        "rings": len(cls[P_RING]) == N_RINGS and RING_PITCH_BAND[0] <= pitch <= RING_PITCH_BAND[1]
        and spread <= RING_SPREAD_MAX,
        "bedding": BED_MIN <= trunk_bed <= BED_MAX and len(root_tips) == N_ROOTS
        and ROOT_BED_MIN <= min(root_tips) and max(root_tips) <= ROOT_BED_MAX,
        "resting": len(rests) == len(FALLEN_NUTS) and REST_MIN <= min(rests) and max(rests) <= REST_MAX,
        "cover": nloose == 0,
    }

    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
          f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}")
    print(f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
          f"overlap={overlap:.6f} nfaces={nfaces}")
    print(f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
          f"outer={OUTER_SIZE} zmin={bb[2]:.5f}")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    zkinds = {}
    for si, sj, at in zrep:
        key = tuple(sorted((cls['all'][si].part, cls['all'][sj].part)))
        zkinds.setdefault(key, [0, at])[0] += 1
    for key, (n, at) in sorted(zkinds.items()):
        print(f"measured zfight_pairs parts={key} n={n} e.g. at {at}")
    print(f"measured shells={len(cls['all'])} fronds={len(cls[P_RACHIS])}+{len(cls[P_DEAD])} dead"
          f"+{len(cls[P_SPEAR])} spear leaflets={len(cls[P_LEAF]) + len(cls[P_DEAD_LEAF])} "
          f"rings={len(cls[P_RING])} roots={len(cls[P_ROOT])} nuts={len(cls[P_NUT])}"
          f"+{len(cls[P_FALLEN_NUT])} fallen")
    print(f"measured frond seats n={len(seats)} {rng_(seats)}")
    print(f"measured coconut bites n={len(nut_bites)} {rng_(nut_bites)} under={rng_(nut_under)}")
    print(f"measured trunk height={trunk_h:.4f} crown_off={crown_off:.4f} mass_off={mass_off:.4f} "
          f"margin={margin:.4f} root_reach={rng_(reach)} mass=({mass.x:.3f},{mass.y:.3f},{mass.z:.3f})")
    print(f"measured rings n={len(cls[P_RING])} pitch={pitch:.5f} spread={spread:.5f} gaps={rng_(gaps)}")
    print(f"measured bed trunk={trunk_bed:.4f} root_tips={rng_(root_tips)} fallen_nuts={rng_(rests)}")
    print(f"measured cover shells={nshells} loose={nloose} kinds={dict(sorted(loose_kinds.items()))}")
    print(f"measured budget_fails={[k for k, ok in budgets.items() if not ok]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none2
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none2
    for idx, (floor, label) in enumerate(zip(FACE_FLOORS, MAT_LABELS)):
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{label} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + none2
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + none2
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + none2
    if (abs(size_x - OUTER_SIZE[0]) > BBOX_TOL or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
            or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL):
        return (fail(f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8),) + none2
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
                     "(--skip-decimate is the designed fail)", 9),) + none2
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9),) + none2
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + none2
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + none2
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + none2
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf}", 15),) + none2
    if not budgets["grounded"]:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none2
    if not budgets["fronds"]:
        return (fail(f"fronds: {len(fronds)}/{n_fronds} rachises and spears, deepest vertex inside the "
                     f"boss {rng_(seats)} m, not all in [{SEAT_MIN}, {SEAT_MAX}]", 17),) + none2
    if not budgets["coconuts"]:
        return (fail(f"coconuts: {len(nut_bites)}/{n_nuts} on the crown, deepest vertex inside the boss "
                     f"{rng_(nut_bites)} m (band [{NUT_BITE_MIN}, {NUT_BITE_MAX}]), centre under the "
                     f"boss's by {rng_(nut_under)} m (must be > 0)", 18),) + none2
    if not budgets["trunk"]:
        return (fail(f"trunk: height {trunk_h:.4f} m ({TRUNK_H} +- {TRUNK_H_TOL}), crown offset "
                     f"{crown_off:.4f} m (band {CROWN_OFF_BAND}), mass centre {mass_off:.4f} m off the "
                     f"foot and {margin:.4f} m inside the root plate (min {TIP_MARGIN_MIN}), "
                     f"{len(reach)}/{N_ROOTS} roots reaching {rng_(reach)} m", 19),) + none2
    if not budgets["rings"]:
        return (fail(f"rings: {len(cls[P_RING])}/{N_RINGS}, pitch {pitch:.5f} m (band {RING_PITCH_BAND}), "
                     f"spread {spread:.5f} m (max {RING_SPREAD_MAX})", 20),) + none2
    if not budgets["bedding"]:
        return (fail(f"bedding: the trunk's shallowest sector {trunk_bed:.4f} m under the sand (band "
                     f"[{BED_MIN}, {BED_MAX}]); root tips {rng_(root_tips)} m (band [{ROOT_BED_MIN}, "
                     f"{ROOT_BED_MAX}])", 21),) + none2
    if not budgets["resting"]:
        return (fail(f"fallen coconuts: lowest point under the sand {rng_(rests)} m, not all in "
                     f"[{REST_MIN}, {REST_MAX}]", 22),) + none2
    if not budgets["cover"]:
        return (fail(f"cover: {nloose} of {nshells} shells not joined to the sand "
                     f"{dict(sorted(loose_kinds.items()))}", 23),) + none2
    return 0, low, sand_mat


def render_still(low, path, engine):
    scene = bpy.context.scene
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(HERO_YAW_DEG)
    bpy.context.view_layer.update()
    bb = vertex_bbox(low.data)
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
    floor.location.z = -0.0005
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, centre.y + WALL_Y, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.100, 0.102, 0.116, 1.0)
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

    # The house rig scaled to a 6 m palm: warm key upper left, cool fill low
    # right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-5.5, -7.0, 5.0), 720.0, 3.5, (1.0, 0.93, 0.83), spread=75.0)
    light("Fill", (8.0, -5.0, -0.5), 70.0, 8.0, (0.72, 0.82, 1.0))
    light("Rim", (-2.5, 3.2, 3.5), 400.0, 3.0, (0.62, 0.78, 1.0))
    light("Wedge", (6.0, 2.2, -0.2), 560.0, 3.5, (1.0, 0.70, 0.45),
          target=(centre.x + 5.0, centre.y + WALL_Y, 1.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.36, -0.93, 0.0)).normalized()
    cam.location = centre + view * 18.0 + Vector((0.0, 0.0, 1.5))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.25))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the fronds.
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
    p.add_argument("--short-petioles", action="store_true")
    p.add_argument("--drop-coconut", action="store_true")
    p.add_argument("--short-roots", action="store_true")
    p.add_argument("--bunch-rings", action="store_true")
    p.add_argument("--perch-trunk", action="store_true")
    p.add_argument("--float-nuts", action="store_true")
    p.add_argument("--float-cover", action="store_true")
    args = p.parse_args(argv)

    flags = {name: getattr(args, name) for name in FLAG_NAMES}
    code, low, _sand = check(args.skip_decimate, lift_z=args.lift_z, stray_vert=args.stray_vert, **flags)
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("palm-tree OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
