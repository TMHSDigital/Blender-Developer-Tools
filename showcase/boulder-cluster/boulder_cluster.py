"""Game-ready glacial boulder cluster — a showcase piece, not an example.

Asserts budget conformance of a procedural boulder cluster after composing
shipped pipeline pieces: bmesh construction, UVs, eight materials,
high-to-low normal bake, LOD chain, convex cluster collider, Unity glTF
export.

Four erratic boulders of clearly different sizes lie part sunk in a soil
mound. Each is an ellipsoid cut by closed-form cleavage planes, the cuts
rounded off by a weathering bevel (a soft minimum in the radial field),
then roughened by a seeded sum of waves. The largest is a 1.7 m granite
block. A sandstone boulder has split in two along a crack; its halves
stand 75 mm apart with matching faces and matching bedding bands. A
0.95 m granite boulder in front carries a 0.6 m sandstone slab resting
flat on its top. Lichen crusts and moss cushions grow on the tops and
north faces; grass tufts, pebbles and wildflowers stand in the gaps and
round the bases, one tuft in the crack.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--perch-boulder`` every boulder
embedded in the soil, ``--float-slab`` the slab seated on its support,
``--perch-slab`` the slab's mass centre over its footprint,
``--skew-half`` the split halves matching across the crack,
``--sunny-lichen`` lichen and moss on up- and shade-facing surfaces,
``--float-cover`` the ground cover rooted in the soil.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python boulder_cluster.py --
    blender --background --python boulder_cluster.py -- --skip-decimate
    blender --background --python boulder_cluster.py -- --output cluster.png
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

SEED = 4127
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- Boulders ---------------------------------------------------------------
# Each boulder: an ellipsoid (semi-axes in its own frame, turned by yaw about
# Z) cut by cleavage planes (normal in the boulder frame, offset as a
# fraction of the ellipsoid's support along that normal, weathering bevel k).
BOULDERS = {
    "A": {"kind": "granite", "xy": (-0.80, 0.44), "yaw": 16.0, "axes": (1.12, 0.80, 0.86),
          "planes": (((0.10, -0.18, 1.0), 0.66, 0.08), ((0.05, -1.0, 0.22), 0.68, 0.07),
                     ((1.0, -0.15, 0.20), 0.66, 0.06), ((-1.0, 0.10, -0.10), 0.70, 0.08),
                     ((-0.20, 1.0, 0.35), 0.70, 0.08), ((0.70, 0.60, 0.50), 0.70, 0.07),
                     ((-0.60, -0.70, 0.45), 0.72, 0.07), ((0.0, 0.0, -1.0), 0.60, 0.08)),
          "chips": 6, "chip_f": (0.74, 0.84), "chip_k": 0.05,
          "amp": 0.030, "n": 22, "tone": 0.35},
    "B": {"kind": "sandstone", "xy": (1.10, 0.24), "yaw": -8.0, "axes": (0.78, 0.62, 0.60),
          "planes": (((-0.10, 0.05, 1.0), 0.74, 0.035), ((1.0, 0.10, -0.15), 0.72, 0.04),
                     ((-1.0, -0.10, 0.25), 0.74, 0.04), ((0.10, 1.0, 0.10), 0.76, 0.035),
                     ((0.0, -1.0, 0.15), 0.78, 0.04), ((0.0, 0.0, -1.0), 0.60, 0.05)),
          "chips": 5, "chip_f": (0.78, 0.88), "chip_k": 0.03,
          "amp": 0.020, "n": 16, "tone": 0.55},
    "C": {"kind": "granite", "xy": (0.02, -0.80), "yaw": 38.0, "axes": (0.56, 0.46, 0.44),
          "planes": (((0.12, -0.04, 1.0), 0.64, 0.05), ((1.0, 0.20, 0.10), 0.70, 0.06),
                     ((-0.30, -1.0, 0.20), 0.68, 0.06), ((-1.0, 0.30, 0.0), 0.72, 0.06),
                     ((0.40, -0.80, 0.60), 0.72, 0.05), ((0.10, 1.0, 0.30), 0.74, 0.06),
                     ((0.0, 0.0, -1.0), 0.60, 0.07)),
          "chips": 4, "chip_f": (0.76, 0.86), "chip_k": 0.04,
          "amp": 0.024, "n": 16, "tone": 0.70},
    "D": {"kind": "sandstone", "yaw": 24.0, "axes": (0.36, 0.26, 0.13),
          "planes": (((0.05, 0.10, 1.0), 0.72, 0.025), ((1.0, 0.0, 0.10), 0.80, 0.03),
                     ((-1.0, 0.15, 0.0), 0.80, 0.03), ((0.1, -1.0, 0.1), 0.84, 0.03)),
          "chips": 3, "chip_f": (0.82, 0.90), "chip_k": 0.02,
          "amp": 0.010, "n": 11, "tone": 0.25},
}
N_HIGH = 1.5              # the bake source's rock resolution factor
GROOVE = 0.008            # sandstone bedding undulation depth, m
STRATA_SPACING = 0.13
STRATA_AXIS = (0.16, 0.20, 1.0)
CRACK_N = (0.967, -0.268, 0.05)   # B's crack normal in B's frame
CRACK_K = 0.018           # the crack's fresh edge: barely rounded
CRACK_GAP = 0.075         # between the two halves
HALF_ORIGIN = 0.36        # each half's origin, as a fraction of B's support along the crack
SLAB_BOTTOM = 0.55        # D's flat underside, fraction of its support
SLAB_OFFSET = (0.03, 0.02)
SLAB_BITE = 0.010         # D's deepest vertex into C
EMBED = 0.070             # every boulder's shallowest flank this far under the soil
FLANK_R = 0.60            # flank vertices: at least this fraction of the sector's reach
SECTORS = 8
# falsifiers
PERCH_LIFT = 0.09         # --perch-boulder: C raised off its bed
FLOAT_SLAB = 0.020        # --float-slab: D lifted off C
PERCH_SLAB = 0.36         # --perch-slab: D slid south across C's top, then re-seated
SKEW_DEG = 6.0            # --skew-half: the east half turned about Z at its crack
FLOAT_COVER = 0.030       # --float-cover: every grass, pebble and flower lifted

# --- Ground -----------------------------------------------------------------
SOIL_A = (2.18, 1.58)
SOIL_Y0 = 0.08
SOIL_H0 = 0.20
SOIL_N = 36
SOIL_EDGE = 0.24
SOIL_FLOOR = 0.012
BERM_H = 0.090
BERM_W = 0.22
BERM_OFF = 0.07
N_TUFT_BASE = 26
N_TUFT_OPEN = 14
N_PEBBLES = 44
N_FLOWERS = 14
N_LICHEN = 26
N_MOSS = 8

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (4.4442, 3.2153, 1.3657)
BASE_TRIS_MIN = 39600
BASE_TRIS_MAX = 40900
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 8
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 320
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# granite, sandstone, lichen, moss, grass, soil, gravel, flower
FACE_FLOORS = (4000, 3400, 1960, 1580, 4700, 2460, 1750, 1260)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Embedding: per boulder, per 45-degree sector about its plan centroid, the
# deepest flank vertex under the soil straight above it.
FLANK_MIN = 0.030
DEEP_MAX = 0.30
# Slab seat: its deepest vertex inside C, straight down.
SEAT_MIN = 0.004
SEAT_MAX = 0.030
# Slab balance: its footprint is every vertex within FOOT_EPS of its lowest
# gap to C; its volume centroid must be inside the footprint's plan hull.
FOOT_EPS = 0.012
BALANCE_MIN = 0.03
# Split: crack faces are the faces of a half within CRACK_REACH of the other
# half and facing it.
CRACK_REACH = 0.15
CRACK_FACING = 0.85
PARALLEL_MAX_DEG = 3.0
GAP_MIN = 0.050
GAP_MAX = 0.100
SLIDE_MAX = 0.05
CRACK_AREA_MIN = 0.25
# Lichen and moss: top faces (facing away from the rock) that face up or north.
TOP_DOT = 0.3
UP_Z = 0.35
SHADE_Y = 0.5
GROWTH_FRAC_MIN = 0.85
HERO_YAW_DEG = 0.0
WALL_Y = 4.6

GRANITE_IDX = 0
SANDSTONE_IDX = 1
LICHEN_IDX = 2
MOSS_IDX = 3
GRASS_IDX = 4
SOIL_IDX = 5
GRAVEL_IDX = 6
FLOWER_IDX = 7
MAT_LABELS = ("granite", "sandstone", "lichen", "moss", "grass", "soil", "gravel", "flower")


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


def smin(a, b, k):
    """Polynomial soft minimum: the weathering bevel where two cuts meet."""
    if k <= 0.0:
        return min(a, b)
    h = max(k - abs(a - b), 0.0) / k
    return min(a, b) - h * h * k * 0.25


def rotz(deg):
    return Matrix.Rotation(math.radians(deg), 3, "Z")


def perp_basis(d):
    ref = UP if abs(d.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = d.cross(ref).normalized()
    return e1, d.cross(e1).normalized()


# --------------------------------------------------------------------------
# Boulder bodies: a star-shaped radial field about an interior origin
# --------------------------------------------------------------------------

class Body:
    """One rock in its own frame. ``radius(d)`` is the distance from the
    origin ``o`` to the surface along ``d``: the ellipsoid, cut by each plane
    through a soft minimum, then displaced by the seeded waves. ``M`` maps
    the frame to the world."""

    def __init__(self, name, spec, waves, origin=None, crack=None, strata=False, chips=()):
        self.name = name
        self.kind = spec["kind"]
        self.axes = Vector(spec["axes"])
        self.amp = spec["amp"]
        self.n = spec["n"]
        self.tone = spec["tone"]
        self.waves = waves
        self.o = Vector(origin) if origin is not None else Vector((0.0, 0.0, 0.0))
        self.planes = []
        for nrm, f, k in tuple(spec["planes"]) + tuple(chips):
            n = Vector(nrm).normalized()
            self.planes.append((n, f * self.support(n), k, False))
        if crack is not None:
            n, h = crack
            self.planes.append((n, h, CRACK_K, True))
        self.strata = Vector(STRATA_AXIS).normalized() if strata else None
        self.M = Matrix.Identity(4)

    def support(self, n):
        a = self.axes
        return math.sqrt((a.x * n.x) ** 2 + (a.y * n.y) ** 2 + (a.z * n.z) ** 2)

    def fbm(self, p):
        return sum(a * math.sin(w.dot(p) + ph) for w, ph, a in self.waves)

    def sample(self, d):
        """(radius, on the crack face, strata value) along unit ``d``."""
        a = self.axes
        qa = Vector((self.o.x / a.x, self.o.y / a.y, self.o.z / a.z))
        wa = Vector((d.x / a.x, d.y / a.y, d.z / a.z))
        A = wa.dot(wa)
        B = 2.0 * qa.dot(wa)
        C = qa.dot(qa) - 1.0
        te = (-B + math.sqrt(max(B * B - 4.0 * A * C, 0.0))) / (2.0 * A)
        r = te
        tmin = 9.0
        crack_t = 9.0
        other_t = 9.0
        for n, h, k, is_crack in self.planes:
            dn = n.dot(d)
            if dn <= 1e-6:
                continue
            t = (h - n.dot(self.o)) / dn
            if is_crack:
                crack_t = t
            else:
                other_t = min(other_t, t)
            tmin = min(tmin, t)
            r = smin(r, t, k)
        on_crack = crack_t < te - 0.01 and crack_t < other_t - 0.01
        flat = smoothstep(te - tmin, 0.0, 0.06)
        p = self.o + d * r
        if on_crack:
            disp = 0.15 * self.amp * self.fbm(p)
        else:
            disp = self.amp * self.fbm(p) * (1.0 - 0.70 * flat)
        g = 0.0
        if self.strata is not None:
            g = p.dot(self.strata) / STRATA_SPACING
            g += 0.30 * math.sin(1.7 * g + 0.4)   # beds of uneven thickness
            if not on_crack:
                # bedding weathers out as ledges on the flanks only; a
                # bedding-plane top stays smooth
                side = 1.0 - smoothstep(abs(d.dot(self.strata)), 0.55, 0.80)
                disp -= GROOVE * side * (0.5 + 0.5 * math.cos(TAU * g)) ** 2
        return r + disp, on_crack, g

    def local_point(self, d):
        return self.o + d * self.sample(d)[0]

    def world(self, p):
        return self.M @ p

    def point(self, d):
        return self.M @ self.local_point(d)

    def normal(self, d):
        e1, e2 = perp_basis(d)
        e = 0.01
        pa = self.local_point((d + e1 * e).normalized()) - self.local_point((d - e1 * e).normalized())
        pb = self.local_point((d + e2 * e).normalized()) - self.local_point((d - e2 * e).normalized())
        n = pa.cross(pb).normalized()
        if n.dot(d) < 0.0:
            n = -n
        return (self.M.to_3x3() @ n).normalized()


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
            for u in range(n):
                for v in range(n):
                    corners = []
                    for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                        key = [0, 0, 0]
                        key[ax] = side
                        key[b] = u + du
                        key[c] = v + dv
                        corners.append(vid(*key))
                    quads.append(corners if side else corners[::-1])
    _CUBE[n] = (dirs, quads)
    return _CUBE[n]


class RockMesh:
    """A body sampled on its cube-sphere: world vertices, crack flags and
    strata values, before it is written into the bmesh."""

    def __init__(self, body, n):
        self.body = body
        dirs, quads = cube_sphere(n)
        self.dirs = dirs
        self.quads = quads
        self.local = []
        self.crack = []
        self.strata = []
        for d in dirs:
            r, c, g = body.sample(d)
            self.local.append(body.o + d * r)
            self.crack.append(c)
            self.strata.append(g)

    def world(self):
        return [self.body.M @ p for p in self.local]

    def tree(self):
        return BVHTree.FromPolygons([tuple(p) for p in self.world()], self.quads)


# --------------------------------------------------------------------------
# The plan: every seeded draw happens here, before anything is built
# --------------------------------------------------------------------------

def draw_waves(rng, size):
    waves = []
    for freq, amp in ((1.9, 1.0), (2.9, 0.62), (4.3, 0.42), (6.1, 0.28), (8.7, 0.18),
                      (12.3, 0.11), (17.0, 0.07), (23.0, 0.045)):
        w = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized()
        waves.append((w * (freq / max(size, 0.4)), rng.uniform(0.0, TAU), amp))
    total = sum(a for _w, _p, a in waves)
    return [(w, p, a / total) for w, p, a in waves]


def plan_cluster():
    rng = random.Random(SEED)

    def u(a, b):
        return a + (b - a) * rng.random()

    plan = {"waves": {}, "chips": {}}
    for name in ("A", "B", "C", "D"):
        spec = BOULDERS[name]
        plan["waves"][name] = draw_waves(rng, max(spec["axes"]))
        # small broken facets at the corners, mostly facing out and up
        chips = []
        for _k in range(spec["chips"]):
            n = Vector((rng.gauss(0, 1), rng.gauss(0, 1), abs(rng.gauss(0, 0.8)) + 0.15))
            chips.append((tuple(n.normalized()), u(*spec["chip_f"]), spec["chip_k"]))
        plan["chips"][name] = chips

    def growth(n, up_frac):
        out = []
        for k in range(n):
            if rng.random() < up_frac:
                d = Vector((rng.gauss(0, 0.45), rng.gauss(0, 0.45), 1.0))
            else:
                d = Vector((rng.gauss(0, 0.35), 1.0, rng.gauss(0.25, 0.25)))
            out.append({"d": d.normalized(), "body": rng.random(), "size": rng.random(),
                        "ph": u(0.0, TAU), "tone": rng.random() ** 1.3,
                        "lobes": rng.choice((9, 11, 13))})
        return out

    plan["lichen"] = growth(420, 0.66)
    plan["moss"] = growth(60, 0.55)

    def spot():
        while True:
            x = u(-1.0, 1.0)
            y = u(-1.0, 1.0)
            if x * x + y * y <= 1.0:
                return x * SOIL_A[0] * 0.86, y * SOIL_A[1] * 0.86 + SOIL_Y0

    tufts = []
    for _k in range(420):
        x, y = spot()
        blades = [{"yaw": u(0.0, TAU), "h": u(0.55, 1.0), "lean": u(0.15, 0.55),
                   "w": u(0.8, 1.2), "tw": u(-0.5, 0.5), "off": (u(-1, 1), u(-1, 1)),
                   "tone": rng.random()} for _b in range(16)]
        tufts.append({"x": x, "y": y, "h": u(0.22, 0.42), "n": rng.choice((11, 13, 15, 16)),
                      "spread": u(0.035, 0.07), "blades": blades, "tone": rng.random()})
    plan["tufts"] = tufts
    plan["crack_blades"] = [{"yaw": u(-0.35, 0.35) + (0.0 if b % 2 else math.pi),
                             "h": u(0.55, 1.0), "lean": u(0.1, 0.35), "w": u(0.7, 1.0),
                             "tw": u(-0.3, 0.3), "off": (u(-1, 1), u(-0.3, 0.3)),
                             "tone": rng.random()} for b in range(6)]
    pebbles = []
    for _k in range(700):
        x, y = spot()
        pebbles.append({"x": x, "y": y, "r": 0.020 + 0.07 * rng.random() ** 2.2,
                        "flat": u(0.45, 0.75), "long": u(1.0, 1.5), "yaw": u(0.0, TAU),
                        "tilt": (u(-0.25, 0.25), u(-0.25, 0.25)), "tone": rng.random(),
                        "waves": draw_waves(rng, 0.1), "near": rng.random()})
    plan["pebbles"] = pebbles
    flowers = []
    for _k in range(80):
        x, y = spot()
        flowers.append({"x": x, "y": y, "h": u(0.18, 0.34), "lean": (u(-0.25, 0.25), u(-0.35, 0.05)),
                        "spin": u(0.0, TAU), "tone": rng.random(), "petal": u(0.030, 0.046),
                        "tilt": u(0.25, 0.55), "leaf": u(0.0, TAU)})
    plan["flowers"] = flowers
    return plan


# --------------------------------------------------------------------------
# Layout: bodies placed and bedded, independent of every flag
# --------------------------------------------------------------------------

def make_bodies(plan):
    bodies = {}
    for name in ("A", "C"):
        bodies[name] = Body(name, BOULDERS[name], plan["waves"][name], chips=plan["chips"][name])
    spec = BOULDERS["B"]
    nb = Vector(CRACK_N).normalized()
    probe = Body("B", spec, plan["waves"]["B"])
    e = HALF_ORIGIN * probe.support(nb)
    chips = plan["chips"]["B"]
    bodies["B1"] = Body("B1", spec, plan["waves"]["B"], origin=-nb * e, crack=(nb, 0.0),
                        strata=True, chips=chips)
    bodies["B2"] = Body("B2", spec, plan["waves"]["B"], origin=nb * e, crack=(-nb, 0.0),
                        strata=True, chips=chips)
    return bodies


def hull2d(pts):
    pts = sorted(set((round(p[0], 6), round(p[1], 6)) for p in pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def hull_margin(hull, x, y):
    """Signed distance of (x, y) inside a CCW hull (negative outside)."""
    if len(hull) < 3:
        return -9.0
    best = 9.0
    outside = 0.0
    for a, b in zip(hull, hull[1:] + hull[:1]):
        ex, ey = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ex, ey)
        d = (ex * (y - a[1]) - ey * (x - a[0])) / ln
        best = min(best, d)
        if d < 0.0:
            # distance to the edge segment, for points outside
            t = min(max(((x - a[0]) * ex + (y - a[1]) * ey) / (ln * ln), 0.0), 1.0)
            outside = max(outside, math.hypot(x - a[0] - t * ex, y - a[1] - t * ey))
    return best if best >= 0.0 else -outside


class Layout:
    """Where every boulder sits by default. Ground cover, soil berms and the
    slab's seat are all derived from this, so a flag that moves one boulder
    later cannot move anything else."""

    def __init__(self, plan):
        self.bodies = make_bodies(plan)
        for name, body in self.bodies.items():
            spec = BOULDERS["B" if name.startswith("B") else name]
            body.M = Matrix.Translation(Vector((spec["xy"][0], spec["xy"][1], 0.0))) @ \
                rotz(spec["yaw"]).to_4x4()
        self.crack_world = (self.bodies["B1"].M.to_3x3() @ Vector(CRACK_N)).normalized()
        for k, s in (("B1", -1.0), ("B2", 1.0)):
            self.bodies[k].M = Matrix.Translation(self.crack_world * (0.5 * CRACK_GAP * s)) @ self.bodies[k].M
        self.coarse = {k: RockMesh(b, 10) for k, b in self.bodies.items()}
        self.hulls = {k: hull2d([(p.x, p.y) for p in m.world()]) for k, m in self.coarse.items()}
        # bed each boulder (the split halves as one unit) in the soil
        for group in (("A",), ("B1", "B2"), ("C",)):
            meshes = [self.coarse[k] for k in group]
            dz = min(min(flank_bury(m.world(), lambda x, y: soil_height(x, y, self))) for m in meshes)
            for k in group:
                self.bodies[k].M = Matrix.Translation(Vector((0.0, 0.0, dz - EMBED))) @ self.bodies[k].M
        self.place_slab(plan)
        mats = {k: b.M for k, b in self.bodies.items()}
        self.bodies["D"].M = seat_slab(self, mats, BOULDERS["D"]["n"], BOULDERS["C"]["n"],
                                       False, False)

    def place_slab(self, plan):
        C = self.bodies["C"]
        top_n, top_h = C.planes[0][0], C.planes[0][1]
        n_world = (C.M.to_3x3() @ top_n).normalized()
        centre = C.M @ (top_n * top_h)
        spec = dict(BOULDERS["D"])
        n_local = (rotz(-spec["yaw"]) @ n_world).normalized()
        spec["planes"] = spec["planes"] + ((tuple(-n_local), SLAB_BOTTOM, 0.03),)
        D = Body("D", spec, plan["waves"]["D"], strata=True, chips=plan["chips"]["D"])
        D.M = Matrix.Translation(Vector((centre.x + SLAB_OFFSET[0], centre.y + SLAB_OFFSET[1], 0.0))) @ \
            rotz(spec["yaw"]).to_4x4()
        self.bodies["D"] = D
        self.slab_plane = n_world

    def cover_ok(self, x, y, lo, hi):
        """Plan distance outside every boulder hull, inside [lo, hi]."""
        m = max(hull_margin(h, x, y) for h in self.hulls.values())
        return -hi <= m <= -lo


def flank_bury(pts, ground):
    """Per sector about the plan centroid, the deepest flank vertex below
    the ground straight above it. Flank: at least FLANK_R of the sector's
    plan reach from the centroid."""
    cx = sum(p.x for p in pts) / len(pts)
    cy = sum(p.y for p in pts) / len(pts)
    reach = [0.0] * SECTORS
    polar = []
    for p in pts:
        a = math.atan2(p.y - cy, p.x - cx) % TAU
        s = min(SECTORS - 1, int(a / TAU * SECTORS))
        r = math.hypot(p.x - cx, p.y - cy)
        polar.append((s, r))
        reach[s] = max(reach[s], r)
    best = [-9.0] * SECTORS
    for p, (s, r) in zip(pts, polar):
        if r >= FLANK_R * reach[s]:
            g = ground(p.x, p.y)
            if g is not None:
                best[s] = max(best[s], g - p.z)
    return best


# --------------------------------------------------------------------------
# Ground
# --------------------------------------------------------------------------

def soil_height(x, y, layout):
    ambient = (SOIL_H0 + 0.035 * math.sin(1.3 * x + 0.2) * math.cos(1.7 * y + 0.5)
               + 0.018 * math.sin(2.9 * x - 2.1 * y + 1.0) + 0.006 * math.sin(5.3 * x + 3.7 * y))
    m = max(hull_margin(h, x, y) for h in layout.hulls.values())
    # soil drifted against the boulders' feet, peaking just outside them
    ambient += BERM_H * math.exp(-((m + BERM_OFF) / BERM_W) ** 2) if m < -BERM_OFF else BERM_H
    return max(SOIL_FLOOR, ambient)


def add_soil(bm, L, layout):
    """A soil mound: a squircle-mapped grid whose rim rolls down to a flat
    base at Z = 0. The base is one n-gon, triangulated later."""
    n = SOIL_N
    grid = []
    for i in range(n + 1):
        col = []
        for k in range(n + 1):
            uu = -1.0 + 2.0 * i / n
            vv = -1.0 + 2.0 * k / n
            X = uu * math.sqrt(1.0 - vv * vv / 2.0)
            Y = vv * math.sqrt(1.0 - uu * uu / 2.0)
            r = min(1.0, math.hypot(X, Y))
            th = math.atan2(Y, X)
            wob = (1.0 + 0.06 * math.sin(3.0 * th + 0.7) + 0.045 * math.sin(5.0 * th + 2.1)
                   + 0.025 * math.sin(8.0 * th + 0.3))
            x = SOIL_A[0] * X * wob
            y = SOIL_A[1] * Y * wob + SOIL_Y0
            on_rim = i in (0, n) or k in (0, n)
            z = 0.0 if on_rim else soil_height(x, y, layout) * smoothstep(1.0 - r, 0.0, SOIL_EDGE)
            col.append(bm.verts.new((x, y, z)))
        grid.append(col)
    # Each cell is split on its short diagonal here, not left as a quad: a
    # ray onto a non-planar quad lands on whichever diagonal the tree picks,
    # and on the berms the two differ by centimetres.
    for i in range(n):
        for k in range(n):
            a, b, c, d = grid[i][k], grid[i + 1][k], grid[i + 1][k + 1], grid[i][k + 1]
            if (a.co - c.co).length <= (b.co - d.co).length:
                tris = ((a, b, c), (a, c, d))
            else:
                tris = ((a, b, d), (b, c, d))
            for tri in tris:
                new_face(bm, tri, SOIL_IDX, L, 0.5)
    rim = ([grid[i][0] for i in range(n)] + [grid[n][k] for k in range(n)]
           + [grid[i][n] for i in range(n, 0, -1)] + [grid[0][k] for k in range(n, 0, -1)])
    new_face(bm, list(reversed(rim)), SOIL_IDX, L, 0.5)


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

def new_face(bm, verts, mat, L, tone, zone=0.0):
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
    return f


def add_rock(bm, rock, L, strata_layer):
    body = rock.body
    mat = GRANITE_IDX if body.kind == "granite" else SANDSTONE_IDX
    verts = []
    for p, g in zip(rock.world(), rock.strata):
        v = bm.verts.new(p)
        v[strata_layer] = g
        verts.append(v)
    for q in rock.quads:
        crack = all(rock.crack[i] for i in q)
        new_face(bm, [verts[i] for i in q], mat, L, body.tone, 1.0 if crack else 0.0)


def add_growth(bm, body, tree, g, L, mat, K, M, radius, thick, bite, edge_tuck, lobes, rot=None,
               crust=False):
    """A cushion or rosette laid on the rock: a lens over a patch of the
    surface, its rim tucked under the rock and its base inside it. Every
    point is snapped to the rock mesh as built (``tree``), so the offsets
    are from the shipped faces, not from the smooth field they chord."""
    d0 = g["d"] if rot is None else rot
    e1, e2 = perp_basis(d0)
    r0 = body.sample(d0)[0]
    ph = g["ph"]

    def lump(th, rho):
        return (0.72 + 0.18 * math.sin(3.0 * th + ph) * math.cos(5.0 * rho + ph)
                + 0.12 * math.sin(7.0 * th + 2.0 * ph) * math.sin(9.0 * rho + ph))

    top_rings = []
    bot_rings = []
    for k in range(1, K + 1):
        rho = k / K
        tr = []
        br = []
        for m in range(M):
            th = TAU * m / M
            edge = (1.0 + 0.16 * math.sin(2.0 * th + ph) + 0.12 * math.sin(3.0 * th + 2.0 * ph)
                    + lobes[0] * math.sin(lobes[1] * th + ph)
                    + 0.5 * lobes[0] * math.sin((2 * lobes[1] + 1) * th + 3.0 * ph))
            rr = rho * edge * radius / r0
            d = (d0 + e1 * (rr * math.cos(th)) + e2 * (rr * math.sin(th))).normalized()
            p = tree.find_nearest(body.point(d))[0]
            nrm = body.normal(d)
            if crust:
                # a crust: an even skin over the rock, so its faces run
                # parallel to the faces under them and a fixed height off
                # them (a tilted skin face can land on a rock face's plane)
                t = 0.0 if k == K else thick
                tv = bm.verts.new(p + nrm * (t - (edge_tuck if k == K else 0.0)))
                tr.append(tv)
                br.append(tv if k == K else bm.verts.new(p - nrm * bite))
            else:
                t = thick * max(0.0, 1.0 - rho * rho) ** 0.5 * lump(th, rho)
                tv = bm.verts.new(p + nrm * (t - edge_tuck))
                tr.append(tv)
                br.append(tv if k == K else bm.verts.new(p - nrm * (bite * (0.5 + 1.2 * (1.0 - rho)))))
        top_rings.append(tr)
        bot_rings.append(br)
    p0 = tree.find_nearest(body.point(d0))[0]
    n0 = body.normal(d0)
    if crust:
        ct = bm.verts.new(p0 + n0 * thick)
        cb = bm.verts.new(p0 - n0 * bite)
    else:
        # the crown stands a little proud, so the centre fan is never flat
        ct = bm.verts.new(p0 + n0 * (1.35 * thick * lump(0.0, 0.0) - edge_tuck))
        cb = bm.verts.new(p0 - n0 * (1.7 * bite))
    tone = g["tone"]
    for rings, centre, flip in ((top_rings, ct, False), (bot_rings, cb, True)):
        for m in range(M):
            q = (m + 1) % M
            tri = (rings[0][m], rings[0][q], centre)
            new_face(bm, tri[::-1] if flip else tri, mat, L, tone, 0.0 if not flip else 2.0)
        for kk, (r0_, r1_) in enumerate(zip(rings, rings[1:])):
            for m in range(M):
                q = (m + 1) % M
                quad = (r0_[m], r1_[m], r1_[q], r0_[q])
                zone = 2.0 if flip else (kk + 1.5) / K
                new_face(bm, quad[::-1] if flip else quad, mat, L, tone, zone)


def soil_hit(tree, x, y):
    loc, nrm, _i, _d = tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
    if loc is None:
        return Vector((x, y, 0.0)), Vector((0.0, 0.0, 1.0))
    if nrm.z < 0.0:
        nrm = -nrm
    return loc, nrm


def add_blade(bm, base, yaw, height, lean, width, twist, L, tone, mat=GRASS_IDX, segs=3,
              thick=0.0012):
    """One grass blade: a closed diamond-section strip that curves over and
    tapers to a point. Its root starts under the soil."""
    hd = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    pts = []
    for i in range(segs + 1):
        t = i / segs
        pts.append(base + UP * (height * (t - 0.35 * lean * t * t)) + hd * (height * lean * t * t))
    left, right, top, bot = [], [], [], []
    for i in range(segs):
        t = i / segs
        tan = (pts[i + 1] - pts[i]).normalized()
        side = tan.cross(hd).normalized()
        side = (side * math.cos(twist * t) + tan.cross(side) * math.sin(twist * t)).normalized()
        nrm = side.cross(tan).normalized()
        w = 0.5 * width * (1.0 - 0.85 * t ** 1.4)
        th = thick * (1.0 - 0.6 * t)
        left.append(bm.verts.new(pts[i] - side * w))
        right.append(bm.verts.new(pts[i] + side * w))
        top.append(bm.verts.new(pts[i] + nrm * th))
        bot.append(bm.verts.new(pts[i] - nrm * th))
    tip = bm.verts.new(pts[-1])
    new_face(bm, (left[0], bot[0], right[0], top[0]), mat, L, tone, 0.0)
    for i in range(segs - 1):
        z = (i + 0.5) / segs
        new_face(bm, (left[i], left[i + 1], top[i + 1], top[i]), mat, L, tone, z)
        new_face(bm, (top[i], top[i + 1], right[i + 1], right[i]), mat, L, tone, z)
        new_face(bm, (right[i], right[i + 1], bot[i + 1], bot[i]), mat, L, tone, z)
        new_face(bm, (bot[i], bot[i + 1], left[i + 1], left[i]), mat, L, tone, z)
    s = segs - 1
    for a, b in ((left[s], top[s]), (top[s], right[s]), (right[s], bot[s]), (bot[s], left[s])):
        new_face(bm, (a, tip, b), mat, L, tone, 1.0)


def add_tube(bm, pts, radii, sides, mat, L, tone, zone=0.0):
    pts = [Vector(p) for p in pts]
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    nrm = perp_basis(tans[0])[0]
    rings = []
    for p, t, r in zip(pts, tans, radii):
        nrm = (nrm - t * nrm.dot(t)).normalized()
        b = t.cross(nrm)
        rings.append([bm.verts.new(p + r * (nrm * math.cos(TAU * k / sides) + b * math.sin(TAU * k / sides)))
                      for k in range(sides)])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            new_face(bm, (r0[k], r0[m], r1[m], r1[k]), mat, L, tone, zone)
    new_face(bm, tuple(reversed(rings[0])), mat, L, tone, zone)
    new_face(bm, tuple(rings[-1]), mat, L, tone, zone)


def add_lens(bm, outline, top, bottom, mat, L, tone, zone=0.0):
    ring = [bm.verts.new(p) for p in outline]
    vt = bm.verts.new(top)
    vb = bm.verts.new(bottom)
    n = len(ring)
    for k in range(n):
        m = (k + 1) % n
        new_face(bm, (ring[k], ring[m], vt), mat, L, tone, zone)
        new_face(bm, (ring[m], ring[k], vb), mat, L, tone, zone)


def add_pebble(bm, tree, pb, L, lift):
    """A water-worn pebble: a flattened, seeded lump seated so its deepest
    vertex is under the soil."""
    dirs, quads = cube_sphere(3)
    yaw = rotz(math.degrees(pb["yaw"]))
    tilt = Matrix.Rotation(pb["tilt"][0], 3, "X") @ Matrix.Rotation(pb["tilt"][1], 3, "Y")
    r = pb["r"]
    ax = Vector((r * pb["long"], r, r * pb["flat"]))
    pts = []
    for d in dirs:
        q = Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z))
        q *= 1.0 + 0.12 * sum(a * math.sin(w.normalized().dot(d) * 3.0 + ph)
                              for w, ph, a in pb["waves"][:4])
        pts.append(yaw @ (tilt @ q) + Vector((pb["x"], pb["y"], 0.0)))
    gaps = []
    for p in pts:
        hit, _n = soil_hit(tree, p.x, p.y)
        gaps.append(p.z - hit.z)
    # sunk by a third of its height, but never swallowed by a slope and
    # never perched: the top stands clear, the deepest vertex is under
    dz = max(-0.7 * ax.z - min(gaps), ax.z - max(gaps))
    dz = min(dz, -0.003 - min(gaps)) + lift
    verts = [bm.verts.new(p + Vector((0.0, 0.0, dz))) for p in pts]
    for q in quads:
        new_face(bm, [verts[i] for i in q], GRAVEL_IDX, L, pb["tone"])


def add_flower(bm, tree, fl, L, lift):
    base, _n = soil_hit(tree, fl["x"], fl["y"])
    base = base - Vector((0.0, 0.0, 0.025)) + Vector((0.0, 0.0, lift))
    axis = Vector((fl["lean"][0], fl["lean"][1], 1.0)).normalized()
    h = fl["h"] + 0.025
    pts = []
    for k in range(6):
        t = k / 5.0
        pts.append(base + UP * (h * t) + (axis - UP) * (h * t * t))
    add_tube(bm, pts, [0.0034, 0.0030, 0.0027, 0.0025, 0.0023, 0.0022], 6, GRASS_IDX, L,
             0.3 + 0.2 * fl["tone"], 0.3)
    top = pts[-1]
    head_axis = (pts[-1] - pts[-2]).normalized()
    head_axis = (head_axis + Vector((0.0, -fl["tilt"], 0.0))).normalized()
    # disc florets: a flattened dome
    rc = 0.30 * fl["petal"] + 0.002
    e1, e2 = perp_basis(head_axis)
    ring = []
    for k in range(10):
        a = fl["spin"] + TAU * k / 10
        ring.append(bm.verts.new(top + head_axis * 0.002 + (e1 * math.cos(a) + e2 * math.sin(a)) * rc))
    crown = bm.verts.new(top + head_axis * (0.45 * rc + 0.002))
    under = bm.verts.new(top - head_axis * (0.50 * rc))
    for k in range(10):
        m = (k + 1) % 10
        new_face(bm, (ring[k], ring[m], crown), FLOWER_IDX, L, fl["tone"], 2.0)
        new_face(bm, (ring[m], ring[k], under), FLOWER_IDX, L, fl["tone"], 2.0)
    # five petals, each cupped up out of the disc
    P = fl["petal"]
    for k in range(5):
        a = fl["spin"] + TAU * (k + 0.5) / 5
        rd = e1 * math.cos(a) + e2 * math.sin(a)
        sd = head_axis.cross(rd)
        # every petal cups and twists by its own step: no two share a plane
        cup = 0.22 + 0.07 * k
        out = (rd * math.cos(cup) + head_axis * math.sin(cup)).normalized()
        nrm = sd.cross(out).normalized()
        tw = 0.12 * (k - 2)
        nrm = (nrm * math.cos(tw) + out.cross(nrm) * math.sin(tw)).normalized()
        sd = nrm.cross(out).normalized()
        root = top + rd * (0.55 * rc)
        outline = []
        for f, sg in ((0.0, 0.0), (0.15, 1.0), (0.45, 1.0), (0.80, 1.0), (1.0, 0.0),
                      (0.80, -1.0), (0.45, -1.0), (0.15, -1.0)):
            wid = 0.36 * P * math.sin(math.pi * min(f, 0.9) / 0.9 * 0.5 + 0.35) if 0.0 < f < 1.0 else 0.0
            outline.append(root + out * (f * P) + sd * (sg * wid * 0.5) + nrm * (0.18 * P * f * f))
        mid = root + out * (0.45 * P) + nrm * (0.04 * P)
        add_lens(bm, outline, mid + nrm * 0.0009, mid - nrm * 0.0009, FLOWER_IDX, L, fl["tone"],
                 0.2 + 0.1 * (k % 2))
    # two leaves at the foot
    for j in range(2):
        add_blade(bm, base + Vector((0.0, 0.0, 0.004 * j)), fl["leaf"] + math.pi * j + 0.3 * j,
                  0.08 + 0.02 * j, 0.9, 0.018, 0.2, L, 0.35 + 0.1 * j)


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

def body_frames(layout, perch_boulder=False, float_slab=False, perch_slab=False, skew_half=False):
    """World matrices for this run: the layout's, with the flag's one move."""
    mats = {k: b.M.copy() for k, b in layout.bodies.items()}
    if perch_boulder:
        mats["C"] = Matrix.Translation(Vector((0.0, 0.0, PERCH_LIFT))) @ mats["C"]
    if skew_half:
        rock = RockMesh(layout.bodies["B2"], 10)
        pts = [p for p, c in zip(rock.world(), rock.crack) if c]
        pivot = sum(pts, Vector()) / len(pts)
        mats["B2"] = (Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(SKEW_DEG), 4, "Z")
                      @ Matrix.Translation(-pivot) @ mats["B2"])
    return mats


def seat_slab(layout, mats, n_d, n_c, float_slab, perch_slab):
    """Drop D straight down onto C (as C stands in this run) until its
    deepest vertex bites SLAB_BITE into C."""
    D = layout.bodies["D"]
    C = layout.bodies["C"]
    saved_c = C.M
    C.M = mats["C"]
    c_tree = RockMesh(C, n_c).tree()
    C.M = saved_c
    M = mats["D"]
    if perch_slab:
        # slide south across C's top, along its top plane
        slide = Vector((0.0, -1.0, 0.0))
        slide = (slide - layout.slab_plane * slide.dot(layout.slab_plane)).normalized()
        M = Matrix.Translation(slide * PERCH_SLAB) @ M
    # lift the slab clear of C before measuring the drop
    M = Matrix.Translation(Vector((0.0, 0.0, 3.0))) @ M
    saved = D.M
    D.M = M
    rock = RockMesh(D, n_d)
    gaps = []
    for p in rock.world():
        loc, _n, _i, _d = c_tree.ray_cast(p, Vector((0.0, 0.0, -1.0)), 10.0)
        if loc is not None:
            gaps.append(p.z - loc.z)
    D.M = saved
    dz = -SLAB_BITE - min(gaps) + (FLOAT_SLAB if float_slab else 0.0)
    return Matrix.Translation(Vector((0.0, 0.0, dz))) @ M


def build_cluster_mesh(name, plan, layout, detail="low", perch_boulder=False, float_slab=False,
                       perch_slab=False, skew_half=False, sunny_lichen=False, float_cover=False):
    scale = N_HIGH if detail == "high" else 1.0
    mats = body_frames(layout, perch_boulder, float_slab, perch_slab, skew_half)

    def res(k):
        return int(round(BOULDERS["B" if k.startswith("B") else k]["n"] * scale))

    mats["D"] = seat_slab(layout, mats, res("D"), res("C"), float_slab, perch_slab)
    saved = {k: b.M for k, b in layout.bodies.items()}
    for k, b in layout.bodies.items():
        b.M = mats[k]
    bm = bmesh.new()
    try:
        L = {"tone": bm.faces.layers.float.new("Tone"),
             "zone": bm.faces.layers.float.new("Zone")}
        strata_layer = bm.verts.layers.float.new("Strata")
        cavity_layer = bm.verts.layers.float.new("Cavity")

        add_soil(bm, L, layout)
        bm.faces.ensure_lookup_table()
        bm.normal_update()   # FromBMesh reads the stored face normals
        soil_tree = BVHTree.FromBMesh(bm)

        trees = {}
        for k in ("A", "B1", "B2", "C", "D"):
            rock = RockMesh(layout.bodies[k], res(k))
            add_rock(bm, rock, L, strata_layer)
            trees[k] = rock.tree()

        for idx, g in enumerate(layout.lichen):
            body = layout.bodies[g["key"]]
            rot = sunny(g["d"], body) if sunny_lichen else None
            add_growth(bm, body, trees[g["key"]], g, L, LICHEN_IDX, 3, 14, g["radius"],
                       0.0022 + 0.0005 * (idx % 4), 0.0030 + 0.0005 * (idx % 5), 0.0006,
                       (0.11, g["lobes"]), rot, crust=True)
        for idx, g in enumerate(layout.moss):
            # the moss stays put under --sunny-lichen: a cushion on A's crown
            # is the top of the envelope, and moving it would move the box
            body = layout.bodies[g["key"]]
            add_growth(bm, body, trees[g["key"]], g, L, MOSS_IDX, 5, 22, g["radius"], 0.042,
                       0.007 + 0.0011 * idx, 0.003, (0.10, 5))

        lift = FLOAT_COVER if float_cover else 0.0
        for tf in layout.tufts:
            base0, _n = soil_hit(soil_tree, tf["x"], tf["y"])
            for bl in tf["blades"][:tf["n"]]:
                ox, oy = bl["off"]
                if tf.get("crack"):
                    off = tf["t"] * (ox * tf["spread"]) + tf["nrm"] * (oy * 0.01)
                    bx, by = tf["x"] + off.x, tf["y"] + off.y
                else:
                    bx, by = tf["x"] + ox * tf["spread"], tf["y"] + oy * tf["spread"]
                b, _n = soil_hit(soil_tree, bx, by)
                b = b - Vector((0.0, 0.0, 0.02)) + Vector((0.0, 0.0, lift))
                add_blade(bm, b, bl["yaw"] + tf.get("yaw0", 0.0), tf["h"] * bl["h"] + 0.02,
                          bl["lean"], 0.0140 * bl["w"], bl["tw"], L,
                          0.6 * tf["tone"] + 0.4 * bl["tone"])
        for pb in layout.pebbles:
            add_pebble(bm, soil_tree, pb, L, lift)
        for fl in layout.flowers:
            add_flower(bm, soil_tree, fl, L, lift)

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
        rock_mats = (GRANITE_IDX, SANDSTONE_IDX)
        for v in bm.verts:
            if not v.link_faces or v.link_faces[0].material_index not in rock_mats:
                continue
            acc = 0.0
            for e in v.link_edges:
                w = e.other_vert(v).co - v.co
                ln = w.length
                if ln > 1e-9:
                    acc += w.dot(v.normal) / ln
            v[cavity_layer] = max(-1.0, min(1.0, 4.0 * acc / max(1, len(v.link_edges))))
        # Rock and cushions smooth-shaded; the breaks read in the silhouette
        # and the bevels. Every material boundary and every fold sharper
        # than 60 degrees is a hard edge.
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats_ = {f.material_index for f in edge.link_faces}
            if len(mats_) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(60.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
        for k, b in layout.bodies.items():
            b.M = saved[k]
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


SUNNY = Matrix(((0.0, -math.sqrt(0.5), math.sqrt(0.5)),
                 (0.0, -math.sqrt(0.5), -math.sqrt(0.5)),
                 (1.0, 0.0, 0.0)))


def sunny(d, body):
    """--sunny-lichen: every rosette turned by one rigid rotation that takes
    up to south-east and north to south-west. One rotation for all, so
    rosettes that were apart stay apart."""
    R = body.M.to_3x3().normalized()
    return (R.transposed() @ (SUNNY @ (R @ d))).normalized()


def finish_layout(layout, plan):
    """Pick the growth patches and ground cover from the plan's candidates,
    against the default layout only."""
    ground = SoilProbe(layout)

    def patches(cands, count, r_lo, r_hi, spacing, avoid, keys):
        out = []
        for g in cands:
            key = keys[min(len(keys) - 1, int(g["body"] * len(keys)))]
            body = layout.bodies[key]
            p = body.point(g["d"])
            nrm = body.normal(g["d"])
            if not (nrm.z > UP_Z + 0.1 or nrm.y > SHADE_Y + 0.1):
                continue
            # the sandstone's ledged flanks take no growth: tops only
            if body.strata is not None and nrm.z < UP_Z + 0.2:
                continue
            if p.z < ground(p.x, p.y) + 0.10:
                continue
            radius = r_lo + (r_hi - r_lo) * g["size"]
            if any(o["key"] == key and (o["p"] - p).length < spacing * (o["radius"] + radius)
                   for o in out + avoid):
                continue
            dc = layout.bodies["D"].M.translation
            if key == "C" and math.hypot(p.x - dc.x, p.y - dc.y) < 0.42:
                continue
            gg = dict(g)
            gg.update({"key": key, "p": p, "radius": radius})
            out.append(gg)
            if len(out) >= count:
                break
        return out

    layout.moss = patches(plan["moss"], N_MOSS, 0.09, 0.19, 1.15, [],
                          ("A", "A", "A", "B1", "B2", "C", "C"))
    layout.lichen = patches(plan["lichen"], N_LICHEN, 0.035, 0.10, 1.10, layout.moss,
                            ("A", "A", "A", "B1", "B2", "C", "C", "D"))
    placed = []

    def free(x, y, r):
        return all(math.hypot(x - px, y - py) > r + pr for px, py, pr in placed)

    tufts = []
    for tf in plan["tufts"]:
        base = len([t for t in tufts if t.get("base")])
        opn = len(tufts) - base
        if base < N_TUFT_BASE and layout.cover_ok(tf["x"], tf["y"], 0.02, 0.26) \
                and free(tf["x"], tf["y"], 0.12):
            t = dict(tf)
            t["base"] = True
        elif opn < N_TUFT_OPEN and layout.cover_ok(tf["x"], tf["y"], 0.35, 9.0) \
                and free(tf["x"], tf["y"], 0.20):
            # out in the open the turf is grazed short
            t = dict(tf)
            t["h"] = 0.55 * tf["h"]
            t["n"] = 8
        else:
            continue
        tufts.append(t)
        placed.append((t["x"], t["y"], 0.10))
    # one tuft grows in the crack, at its south mouth
    rock = RockMesh(layout.bodies["B1"], 20)
    mouth = [p for p, c in zip(rock.world(), rock.crack) if c]
    lo = min(mouth, key=lambda p: p.y)
    n = layout.crack_world
    t = Vector((0.0, 0.0, 1.0)).cross(n).normalized()
    if t.y > 0.0:
        t = -t
    mouth = lo + n * (0.5 * CRACK_GAP) - t * 0.10
    tufts.append({"x": mouth.x, "y": mouth.y, "h": 0.20, "n": 6, "spread": 0.07,
                  "blades": plan["crack_blades"], "tone": 0.4, "crack": True, "t": t,
                  "nrm": n, "yaw0": math.atan2(t.y, t.x)})
    placed.append((mouth.x, mouth.y, 0.08))
    layout.tufts = tufts

    # flowers come up through the turf, so they may stand among the tufts
    flowers = []
    for fl in plan["flowers"]:
        if not layout.cover_ok(fl["x"], fl["y"], 0.10, 0.70) or not free(fl["x"], fl["y"], -0.06):
            continue
        if any(math.hypot(fl["x"] - o["x"], fl["y"] - o["y"]) < 0.12 for o in flowers):
            continue
        flowers.append(fl)
        if len(flowers) >= N_FLOWERS:
            break
    layout.flowers = flowers
    placed.extend((fl["x"], fl["y"], 0.05) for fl in flowers)
    pebbles = []
    for pb in plan["pebbles"]:
        near = pb["near"] < 0.8
        ok = layout.cover_ok(pb["x"], pb["y"], pb["r"] * 1.5 + 0.02, 0.30) if near \
            else layout.cover_ok(pb["x"], pb["y"], 0.30, 9.0)
        if not ok or not free(pb["x"], pb["y"], pb["r"] * 1.5 + 0.01):
            continue
        pebbles.append(pb)
        placed.append((pb["x"], pb["y"], pb["r"] * 1.5))
        if len(pebbles) >= N_PEBBLES:
            break
    layout.pebbles = pebbles


class SoilProbe:
    def __init__(self, layout):
        self.layout = layout

    def __call__(self, x, y):
        return soil_height(x, y, self.layout)


def build_collider_source(name, layout):
    """The boulders alone, coarse: players walk through grass."""
    bm = bmesh.new()
    try:
        for k in ("A", "B1", "B2", "C", "D"):
            for p in RockMesh(layout.bodies[k], 5).world():
                bm.verts.new(p)
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


def mapping(nt, vec, scale=(1.0, 1.0, 1.0)):
    node = nt.nodes.new("ShaderNodeMapping")
    node.inputs["Scale"].default_value = scale
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Vector"]


def noise(nt, vec, scale, detail, roughness):
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = roughness
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


def weather(nt, col, coord, dark, amount):
    """Crevices darken and the foot of every boulder is soil-stained; convex
    edges wear pale; rain streaks run down the faces."""
    cav = attr(nt, "Cavity")
    col = mix_color(nt, col, dark, remap(nt, cav, 0.05, 0.45, 0.0, 0.75))
    col = mix_color(nt, col, (0.62, 0.60, 0.56), remap(nt, cav, -0.10, -0.45, 0.0, 0.30))
    streak = noise(nt, mapping(nt, coord, scale=(9.0, 9.0, 0.9)), 1.0, 4.0, 0.55)
    col = mix_color(nt, col, dark, remap(nt, streak, 0.55, 0.72, 0.0, 0.35))
    fac = remap(nt, height(nt, coord), 0.10, 0.40, amount, 0.0)
    return mix_color(nt, col, (0.085, 0.066, 0.048), fac)


def granite_material():
    mat, nt, bsdf, coord = surface("Granite")
    tone = attr(nt, "Tone")
    mottle = noise(nt, coord, 2.4, 6.0, 0.6)
    col = ramp(nt, mottle, ((0.30, (0.20, 0.19, 0.18)), (0.50, (0.29, 0.27, 0.25)),
                            (0.70, (0.36, 0.32, 0.29))))
    # pink feldspar in some blocks, grey in others
    col = mix_color(nt, col, (0.38, 0.27, 0.23), remap(nt, tone, 0.3, 0.8, 0.0, 0.45))
    # crystals: black biotite and milky quartz in a fine cellular speckle
    r, g, dist = voronoi_color(nt, coord, 95.0)
    col = mix_color(nt, col, (0.025, 0.025, 0.028), remap(nt, r, 0.80, 0.86, 0.0, 0.9))
    col = mix_color(nt, col, (0.58, 0.57, 0.54), remap(nt, g, 0.86, 0.92, 0.0, 0.7))
    fine = noise(nt, coord, 180.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.10, 0.10, 0.10), remap(nt, fine, 0.35, 0.65, 0.35, 0.0))
    col = weather(nt, col, coord, (0.07, 0.068, 0.066), 0.55)
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, r, 0.8, 0.86, 0.82, 0.55), bsdf.inputs["Roughness"])
    bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "MULTIPLY", mottle, 0.6),
                             math_node(nt, "MULTIPLY", dist, 0.8)), 0.35, 0.01)
    return mat


def sandstone_material():
    mat, nt, bsdf, coord = surface("Sandstone")
    strata = attr(nt, "Strata")
    wob = noise(nt, coord, 3.0, 4.0, 0.55)
    s = math_node(nt, "ADD", strata, math_node(nt, "MULTIPLY", wob, 0.35))
    bands = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", s, 0.5), 0.0)
    col = ramp(nt, bands, ((0.00, (0.40, 0.28, 0.17)), (0.16, (0.50, 0.38, 0.24)),
                           (0.30, (0.29, 0.17, 0.09)), (0.40, (0.43, 0.30, 0.18)),
                           (0.52, (0.56, 0.46, 0.33)), (0.68, (0.45, 0.32, 0.19)),
                           (0.80, (0.25, 0.14, 0.08)), (0.90, (0.38, 0.26, 0.15)),
                           (1.00, (0.40, 0.28, 0.17))))
    fine = noise(nt, mapping(nt, coord, scale=(1.0, 1.0, 1.0)), 110.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.18, 0.12, 0.07), remap(nt, fine, 0.35, 0.65, 0.35, 0.0))
    # the crack faces are fresh: paler, cleaner, unweathered
    zone = attr(nt, "Zone")
    col = weather(nt, col, coord, (0.10, 0.065, 0.040), 0.5)
    fresh = ramp(nt, bands, ((0.0, (0.60, 0.46, 0.30)), (0.5, (0.68, 0.54, 0.36)),
                             (1.0, (0.60, 0.46, 0.30))))
    col = mix_color(nt, col, fresh, remap(nt, zone, 0.5, 1.0, 0.0, 0.85))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    bump(nt, bsdf, math_node(nt, "ADD", fine, math_node(nt, "MULTIPLY", bands, 0.6)), 0.4, 0.008)
    return mat


def lichen_material():
    mat, nt, bsdf, coord = surface("Lichen")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    # sage crustose, orange Xanthoria and pale grey rosettes
    col = ramp(nt, tone, ((0.00, (0.24, 0.27, 0.19)), (0.30, (0.31, 0.34, 0.25)),
                          (0.52, (0.38, 0.40, 0.33)), (0.62, (0.56, 0.31, 0.08)),
                          (0.80, (0.62, 0.40, 0.12)), (0.90, (0.40, 0.41, 0.36)),
                          (1.00, (0.46, 0.46, 0.42))))
    # a mottled crust, not a painted disc: the rock shows through in flecks
    fleck = noise(nt, coord, 70.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.20, 0.20, 0.19), remap(nt, fleck, 0.55, 0.70, 0.0, 0.55))
    # older centres darker, growing rims a shade paler
    col = mix_color(nt, col, (0.16, 0.16, 0.12), remap(nt, zone, 0.5, 0.2, 0.0, 0.40))
    col = mix_color(nt, col, (0.62, 0.62, 0.56), remap(nt, zone, 0.75, 0.95, 0.0, 0.15))
    dots = voronoi_color(nt, coord, 260.0)[2]
    col = mix_color(nt, col, (0.10, 0.07, 0.04), remap(nt, dots, 0.12, 0.06, 0.0, 0.55))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    bump(nt, bsdf, dots, 0.3, 0.002)
    return mat


def moss_material():
    mat, nt, bsdf, coord = surface("Moss")
    tone = attr(nt, "Tone")
    base = ramp(nt, tone, ((0.0, (0.050, 0.100, 0.016)), (0.5, (0.085, 0.160, 0.024)),
                           (1.0, (0.125, 0.210, 0.032))))
    fuzz = noise(nt, coord, 140.0, 4.0, 0.7)
    tufts = noise(nt, coord, 26.0, 4.0, 0.6)
    patchy = noise(nt, coord, 6.0, 3.0, 0.5)
    col = mix_color(nt, base, (0.065, 0.075, 0.022), remap(nt, patchy, 0.40, 0.65, 0.55, 0.0))
    col = mix_color(nt, col, (0.020, 0.042, 0.010), remap(nt, fuzz, 0.35, 0.65, 0.65, 0.0))
    col = mix_color(nt, col, (0.26, 0.34, 0.06), remap(nt, tufts, 0.52, 0.72, 0.0, 0.80))
    # dry brown tips where a cushion has browned off
    dry = noise(nt, coord, 11.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.20, 0.15, 0.06), remap(nt, dry, 0.62, 0.72, 0.0, 0.55))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    bump(nt, bsdf, math_node(nt, "ADD", fuzz, math_node(nt, "MULTIPLY", tufts, 1.6)), 0.9, 0.008)
    return mat


def grass_material():
    mat, nt, bsdf, coord = surface("Grass")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    col = ramp(nt, tone, ((0.0, (0.090, 0.200, 0.030)), (0.5, (0.160, 0.290, 0.050)),
                          (0.85, (0.240, 0.330, 0.070)), (1.0, (0.420, 0.380, 0.140))))
    # tips bleached to straw, roots dark
    col = mix_color(nt, col, (0.58, 0.50, 0.24), remap(nt, zone, 0.55, 1.0, 0.0, 0.75))
    col = mix_color(nt, col, (0.03, 0.05, 0.015), remap(nt, zone, 0.3, 0.0, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.6
    return mat


def soil_material():
    mat, nt, bsdf, coord = surface("Till")
    clods = noise(nt, coord, 6.0, 6.0, 0.62)
    crumbs = noise(nt, coord, 70.0, 3.0, 0.6)
    col = ramp(nt, clods, ((0.30, (0.040, 0.031, 0.022)), (0.55, (0.075, 0.058, 0.040)),
                           (0.80, (0.110, 0.088, 0.064))))
    col = mix_color(nt, col, (0.020, 0.015, 0.011), remap(nt, crumbs, 0.35, 0.55, 0.6, 0.0))
    # glacial till: pale grit
    grit = voronoi_color(nt, coord, 55.0)[0]
    col = mix_color(nt, col, (0.16, 0.145, 0.12), remap(nt, grit, 0.92, 0.95, 0.0, 0.45))
    # thin turf in the hollows
    film = noise(nt, coord, 2.0, 4.0, 0.55)
    col = mix_color(nt, col, (0.050, 0.080, 0.022), remap(nt, film, 0.48, 0.62, 0.0, 0.8))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.96
    bump(nt, bsdf, math_node(nt, "ADD", clods, math_node(nt, "MULTIPLY", crumbs, 0.6)),
         0.6, 0.01)
    return mat


def gravel_material():
    mat, nt, bsdf, coord = surface("Gravel")
    tone = attr(nt, "Tone")
    col = ramp(nt, tone, ((0.0, (0.10, 0.10, 0.10)), (0.30, (0.20, 0.19, 0.17)),
                          (0.55, (0.30, 0.22, 0.15)), (0.75, (0.34, 0.33, 0.30)),
                          (0.90, (0.16, 0.15, 0.16)), (1.0, (0.08, 0.08, 0.09))))
    speck = noise(nt, coord, 160.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.06, 0.06, 0.06), remap(nt, speck, 0.60, 0.72, 0.0, 0.6))
    fac = remap(nt, height(nt, coord), 0.10, 0.20, 0.45, 0.0)
    col = mix_color(nt, col, (0.08, 0.065, 0.05), fac)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.62
    bump(nt, bsdf, speck, 0.2, 0.002)
    return mat


def flower_material():
    mat, nt, bsdf, coord = surface("Flower")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    # white oxeye, yellow buttercup, violet harebell
    petal = ramp(nt, tone, ((0.00, (0.78, 0.76, 0.70)), (0.33, (0.80, 0.78, 0.72)),
                            (0.40, (0.85, 0.62, 0.04)), (0.66, (0.88, 0.66, 0.05)),
                            (0.72, (0.34, 0.16, 0.60)), (1.00, (0.40, 0.20, 0.66))))
    heart = (0.80, 0.46, 0.03)
    col = mix_color(nt, petal, heart, remap(nt, zone, 1.0, 1.5, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.5
    return mat


def cluster_materials():
    """Eight slots, in index order: shared by the check and the render."""
    return (granite_material(), sandstone_material(), lichen_material(), moss_material(),
            grass_material(), soil_material(), gravel_material(), flower_material())


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
        mats = {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        remap_ = {vi: n for n, vi in enumerate(verts)}
        self.tree = BVHTree.FromPolygons(
            [tuple(p) for p in pts], [[remap_[v] for v in p.vertices] for p in polys])
        self.polys = polys
        self.centre = sum(pts, Vector()) / len(pts)


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    rocks = [s for s in parts if s.mat in (GRANITE_IDX, SANDSTONE_IDX) and max(s.size) > 0.3]
    granite = sorted([s for s in rocks if s.mat == GRANITE_IDX], key=lambda s: -s.size.length)
    sand = sorted([s for s in rocks if s.mat == SANDSTONE_IDX], key=lambda s: -s.size.length)
    out["rocks"] = rocks
    out["A"] = granite[0] if granite else None
    out["C"] = granite[1] if len(granite) > 1 else None
    halves = sand[:2]
    out["D"] = sand[2] if len(sand) > 2 else None
    out["halves"] = sorted(halves, key=lambda s: s.centre.x)
    out["soil"] = [s for s in parts if s.mat == SOIL_IDX]
    out["lichen"] = [s for s in parts if s.mat == LICHEN_IDX]
    out["moss"] = [s for s in parts if s.mat == MOSS_IDX]
    out["cover"] = [s for s in parts if s.mat in (GRASS_IDX, GRAVEL_IDX, FLOWER_IDX)]
    return out


def embed_audit(rock, soil):
    """Per sector: the deepest flank vertex under the soil straight above it
    (a ray down onto the soil shell alone); and the deepest vertex of all."""
    down = Vector((0.0, 0.0, -1.0))

    def ground(x, y):
        loc, _n, _i, _d = soil.tree.ray_cast(Vector((x, y, 5.0)), down, 20.0)
        return loc.z if loc is not None else None

    flank = flank_bury(rock.pts, ground)
    deep = -9.0
    for p in rock.pts:
        g = ground(p.x, p.y)
        if g is not None:
            deep = max(deep, g - p.z)
    return flank, deep


def volume_centroid(me, shell):
    vol = 0.0
    acc = Vector((0.0, 0.0, 0.0))
    for poly in shell.polys:
        vs = [me.vertices[i].co for i in poly.vertices]
        for k in range(1, len(vs) - 1):
            a, b, c = vs[0], vs[k], vs[k + 1]
            v6 = a.dot(b.cross(c))
            vol += v6
            acc += v6 * (a + b + c)
    return acc / (4.0 * vol), vol / 6.0


def slab_audit(me, slab, support):
    """The slab's deepest vertex inside its support, straight down; its
    footprint (vertices within FOOT_EPS of its lowest gap) and how far its
    volume centroid lies inside the footprint's plan hull."""
    down = Vector((0.0, 0.0, -1.0))
    gaps = []
    for p in slab.pts:
        loc, _n, _i, _d = support.tree.ray_cast(p + Vector((0.0, 0.0, 2.0)), down, 10.0)
        # the first hit from above is the support's top, even for a vertex inside it
        if loc is not None:
            gaps.append((p, p.z - loc.z))
    if not gaps:
        return -9.0, -9.0, 0, Vector()
    low = min(g for _p, g in gaps)
    foot = [p for p, g in gaps if g <= low + FOOT_EPS]
    centroid, _vol = volume_centroid(me, slab)
    margin = hull_margin(hull2d([(p.x, p.y) for p in foot]), centroid.x, centroid.y)
    return -low, margin, len(foot), centroid


def crack_faces(me, half, other):
    towards = (other.centre - half.centre)
    towards.z = 0.0
    towards.normalize()
    faces = []
    for poly in half.polys:
        if poly.normal.dot(towards) < CRACK_FACING:
            continue
        loc, _n, _i, dist = other.tree.find_nearest(poly.center)
        if loc is not None and dist <= CRACK_REACH:
            faces.append(poly)
    area = sum(p.area for p in faces)
    if not faces:
        return None, None, 0.0
    n = sum((p.normal * p.area for p in faces), Vector()).normalized()
    c = sum((p.center * p.area for p in faces), Vector()) / area
    return n, c, area


def split_audit(me, halves):
    (h1, h2) = halves
    n1, c1, a1 = crack_faces(me, h1, h2)
    n2, c2, a2 = crack_faces(me, h2, h1)
    if n1 is None or n2 is None:
        return None
    ang = math.degrees(math.acos(max(-1.0, min(1.0, -n1.dot(n2)))))
    nm = (n1 - n2).normalized()
    gap = (c2 - c1).dot(nm)
    slide = ((c2 - c1) - nm * gap).length
    return {"angle": ang, "gap": gap, "slide": slide, "area": (a1, a2)}


def growth_audit(growth, rock_tree):
    """Area fraction of lichen and moss top faces (facing away from the rock
    under them) whose normal faces up or north, into the shade."""
    top = 0.0
    good = 0.0
    for m in growth:
        for poly in m.polys:
            loc, ln, _i, _d = rock_tree.find_nearest(poly.center)
            if loc is None or poly.normal.dot(ln) < TOP_DOT:
                continue
            a = poly.area
            top += a
            if poly.normal.z > UP_Z or poly.normal.y > SHADE_Y:
                good += a
    return (good / top if top else 0.0), top


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
    """Ground cover (grass blades, pebbles, flower stems, leaves, discs and
    petals) joined to the soil through BVH overlaps: how many shells are not."""
    soil = cls["soil"][0]
    cover = cls["cover"]
    parts = [soil] + cover
    roots = union_components(parts)
    loose = [p for p, r in zip(parts[1:], roots[1:]) if r != roots[0]]
    return len(cover), len(loose)


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
        # the source is a point cloud: a vertex can be both interior and unused
        unused = [v for v in unused if v.is_valid]
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
    img = bpy.data.images.new("ClusterNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = GRANITE_IDX
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


def check(skip_decimate, lift_z=False, stray_vert=False, perch_boulder=False, float_slab=False,
          perch_slab=False, skew_half=False, sunny_lichen=False, float_cover=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    plan = plan_cluster()
    layout = Layout(plan)
    finish_layout(layout, plan)
    flags = dict(perch_boulder=perch_boulder, float_slab=float_slab, perch_slab=perch_slab,
                 skew_half=skew_half, sunny_lichen=sunny_lichen, float_cover=float_cover)
    low = build_cluster_mesh("ClusterLow", plan, layout, "low", **flags)
    high = build_cluster_mesh("ClusterHigh", plan, layout, "high", **flags)
    mats = cluster_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    granite = mats[GRANITE_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none2 = (None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("cluster mesh did not build", 3),) + none2

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
    if (cls["A"] is None or cls["C"] is None or cls["D"] is None or len(cls["halves"]) != 2
            or len(cls["soil"]) != 1):
        return (fail(f"boulder or soil shells not found: rocks {len(cls['rocks'])}, "
                     f"soil {len(cls['soil'])}", 3),) + none2
    soil = cls["soil"][0]
    beds = {}
    for label, rock in (("A", cls["A"]), ("B1", cls["halves"][0]), ("B2", cls["halves"][1]),
                        ("C", cls["C"])):
        beds[label] = embed_audit(rock, soil)
    flank_min = min(min(f) for f, _d in beds.values())
    deep_max = max(d for _f, d in beds.values())
    seat, balance, nfoot, slab_c = slab_audit(low.data, cls["D"], cls["C"])
    split = split_audit(low.data, cls["halves"])
    rock_tree = BVHTree.FromPolygons(
        [tuple(v.co) for v in low.data.vertices],
        [tuple(p.vertices) for s in cls["rocks"] for p in s.polys])
    growth_frac, growth_top = growth_audit(cls["lichen"] + cls["moss"], rock_tree)
    ncover, nloose = cover_audit(cls)

    img, tex = setup_bake_image(low, granite)
    if img is None:
        return (fail("cluster has no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "ClusterLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "ClusterLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("ClusterColSrc", layout)
    collider = convex_hull_collider(collider_src, "ClusterCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_boulder_cluster_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    expected_growth = (len(layout.lichen), len(layout.moss))
    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
          f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}")
    print(f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
          f"overlap={overlap:.6f} nfaces={nfaces}")
    print(f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
          f"outer={OUTER_SIZE} zmin={bb[2]:.4f}")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured shells={len(cls['all'])} rocks={len(cls['rocks'])} "
          f"lichen={len(cls['lichen'])} moss={len(cls['moss'])} cover={len(cls['cover'])} "
          f"A={tuple(round(x, 3) for x in cls['A'].size)} "
          f"B1={tuple(round(x, 3) for x in cls['halves'][0].size)} "
          f"B2={tuple(round(x, 3) for x in cls['halves'][1].size)} "
          f"C={tuple(round(x, 3) for x in cls['C'].size)} "
          f"D={tuple(round(x, 3) for x in cls['D'].size)}")
    for label, (flank, deep) in beds.items():
        print(f"measured embed {label} flank min={min(flank):.4f} max={max(flank):.4f} "
              f"deepest={deep:.4f}")
    print(f"measured slab seat={seat:.4f} balance={balance:.4f} footprint={nfoot} "
          f"centroid=({slab_c.x:.4f},{slab_c.y:.4f},{slab_c.z:.4f})")
    if split:
        print(f"measured split angle={split['angle']:.3f} gap={split['gap']:.4f} "
              f"slide={split['slide']:.4f} area=({split['area'][0]:.3f},{split['area'][1]:.3f})")
    print(f"measured growth_up_shade={growth_frac:.4f} top_area={growth_top:.4f} "
          f"lichen={len(cls['lichen'])}/{expected_growth[0]} moss={len(cls['moss'])}/{expected_growth[1]}")
    print(f"measured cover={ncover} loose={nloose} tufts={len(layout.tufts)} "
          f"pebbles={len(layout.pebbles)} flowers={len(layout.flowers)}")

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
    if bb[2] > ZMIN_EPS:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none2
    if flank_min < FLANK_MIN or deep_max > DEEP_MAX:
        return (fail(f"embedding: shallowest flank sector {flank_min:.4f} (min {FLANK_MIN}), "
                     f"deepest vertex {deep_max:.4f} (max {DEEP_MAX})", 17),) + none2
    if not (SEAT_MIN <= seat <= SEAT_MAX):
        return (fail(f"slab seat: deepest vertex {seat:.4f} m into its support, not in "
                     f"[{SEAT_MIN}, {SEAT_MAX}]", 18),) + none2
    if balance < BALANCE_MIN:
        return (fail(f"slab balance: mass centre {balance:.4f} m inside its footprint "
                     f"(min {BALANCE_MIN}): it would topple", 19),) + none2
    if (split is None or split["angle"] > PARALLEL_MAX_DEG
            or not (GAP_MIN <= split["gap"] <= GAP_MAX) or split["slide"] > SLIDE_MAX
            or min(split["area"]) < CRACK_AREA_MIN):
        return (fail(f"split halves: {split} (parallel <= {PARALLEL_MAX_DEG} deg, gap "
                     f"[{GAP_MIN}, {GAP_MAX}], slide <= {SLIDE_MAX}, area >= {CRACK_AREA_MIN})",
                     20),) + none2
    if (len(cls["lichen"]) != expected_growth[0] or len(cls["moss"]) != expected_growth[1]
            or growth_frac < GROWTH_FRAC_MIN):
        return (fail(f"lichen and moss: {len(cls['lichen'])}/{expected_growth[0]} rosettes, "
                     f"{len(cls['moss'])}/{expected_growth[1]} cushions, {growth_frac:.4f} of "
                     f"top area facing up or north (min {GROWTH_FRAC_MIN})", 21),) + none2
    if nloose:
        return (fail(f"ground cover: {nloose} of {ncover} shells not rooted in the soil", 22),) + none2
    return 0, low, granite


def render_still(low, path, engine):
    scene = bpy.context.scene
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
    wall.location = (0.0, WALL_Y, 0.0)
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

    # Key, fill, rim and the warm wedge, scaled for a 4.8 m mound.
    light("Key", (-4.5, -5.5, 7.0), 265.0, 3.0, (1.0, 0.95, 0.88), spread=12.0)
    light("Fill", (7.0, -4.0, 1.5), 8.0, 8.0, (0.72, 0.82, 1.0))
    light("Rim", (-2.0, 4.5, 3.5), 170.0, 3.0, (0.62, 0.78, 1.0))
    light("Wedge", (4.5, 1.5, 3.0), 420.0, 4.0, (1.0, 0.68, 0.38),
          target=(2.5, WALL_Y - 1.5, 0.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.42, -0.91, 0.0)).normalized()
    cam.location = centre + view * 6.6 + Vector((0.0, 0.0, 2.5))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.36))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the lichen.
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
    p.add_argument("--perch-boulder", action="store_true")
    p.add_argument("--float-slab", action="store_true")
    p.add_argument("--perch-slab", action="store_true")
    p.add_argument("--skew-half", action="store_true")
    p.add_argument("--sunny-lichen", action="store_true")
    p.add_argument("--float-cover", action="store_true")
    args = p.parse_args(argv)

    code, low, _granite = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        perch_boulder=args.perch_boulder,
        float_slab=args.float_slab,
        perch_slab=args.perch_slab,
        skew_half=args.skew_half,
        sunny_lichen=args.sunny_lichen,
        float_cover=args.float_cover,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("boulder-cluster OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
