"""Game-ready canyon and mesa map tile — a showcase piece, not an example.

Asserts budget conformance of a procedural strategy-game map tile after
composing shipped pipeline pieces: bmesh construction, UVs, eight
materials, high-to-low normal bake, LOD chain, convex hull colliders,
Unity glTF export.

A square desert tile 2.40 m on a side, of Colorado Plateau character. Two
mesas stand at the back with a canyon between them, a butte and a slender
spire in front. Every one of them is cut from the same layer cake: a
talus apron of shale and rubble at the angle of repose up to the cliffs'
foot, a cliff of five horizontally bedded sandstone beds, each its own
colour and weathered back into a parting at every bedding plane, a crumbling slope of darker shale over it, and a hard
caprock lid on top, flat and overhanging. The beds stand at one height on
every formation, so they read straight across the canyon. A dry wash
enters at the back edge, runs down the canyon and out across the valley,
falling the whole way, and leaves by the front edge. Fallen blocks lie on
the aprons, junipers and sage scrub dot the floor and the mesa tops, and
a few cottonwoods follow the wash.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--perch-butte`` the formations
sealed in their aprons, ``--tilt-beds`` the strata level and continuous
across the canyon, ``--dome-cap`` the caprock tops flat, ``--steep-talus``
the aprons inside the angle-of-repose band, ``--uphill-wash`` the wash
falling all the way and crossing the tile edge to edge, ``--perch-rock``
the blocks sealed in the ground, ``--pile-rocks`` the blocks apart,
``--float-plants`` the plants rooted.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python canyon_mesa_tile.py --
    blender --background --python canyon_mesa_tile.py -- --skip-decimate
    blender --background --python canyon_mesa_tile.py -- --output canyon.png
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

SEED = 5297
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- The tile: a square, its floor gently falling toward the front ----------
SIDE = 2.40
HALF = SIDE / 2.0
TILE_N = {"low": 160, "high": 230}   # lattice steps along a side
FLOOR_Z = 0.100           # the valley floor's mean level over the base
FLOOR_TILT = 0.010        # the floor stands this much higher at the back edge, lower at the front
DUNE = 0.0050             # low drifts on the floor
# a field of transverse dunes in the front corner: gentle stoss slopes, lee
# faces near the angle of repose, crests a little sinuous
DUNE_FIELD = (-0.60, -0.80, 0.20, 0.46)   # centre, full to this radius, gone by this one
DUNE_H = 0.014
DUNE_L = 0.16             # crest to crest
DUNE_WIND = math.radians(30.0)

# --- The layer cake, heights over FLOOR_Z ------------------------------------
# Monument Valley in section: Organ Rock shale slopes and talus to the cliffs'
# foot, De Chelly sandstone cliffs, a Moenkopi shale slope, the Shinarump
# caprock. Real proportions: the cliff about 2/3 of the relief, the slope a
# tenth, the cap a few percent; here 0.28 / 0.055 / 0.028 of 0.483 m.
APRON_TOP = 0.120         # the bench: top of the talus apron, the cliffs' foot
BURY = 0.035              # a formation's foot runs this far under the bench
DECHELLY = (0.120, 0.172, 0.236, 0.290, 0.346, 0.400)   # five beds, bottom to top
# each bed's face set back this far: most beds run on flush from the one
# under them (one face, its bedding plane a ring), and a ledge opens only
# where a strong bed sits on a weak one
BED_SB = (0.000, 0.006, 0.008, 0.010, 0.016)
BATTER = 0.002            # each bed's face leans back this much bottom to top
# each bedding plane weathers back into a parting this far behind the faces
# either side of it (a softer seam between harder beds), so every bed stands
# as its own rounded band; planes 1..5 (the cliff's top last)
PARTING = (0.0026, 0.0036, 0.0023, 0.0032, 0.0000)
BED_EDGE = 0.15           # a bed's face rounds into its partings over this share of its thickness
MOENKOPI = ((0.400, 0.013), (0.418, 0.022), (0.437, 0.034), (0.455, 0.049))   # (h, setback)
CAP_BASE = 0.455          # the caprock's underside, overhanging the slope
CAP_TOP = 0.483
CAP_SB = (0.037, 0.038, 0.042)   # underside, face top, the top's edge after its chamfer
CHAMFER_H = 0.004
SPIRE_TOP = 5             # the spire stands to the top of the cliff sandstone, its cap long gone
# and is worn to a totem: its girth (a share of its foot's) narrowing fast
# off the talus, then slowly up a slender shaft, its hardest bed left as a
# swelling knob under the top
SPIRE_GIRTH = ((0.00, 1.00), (0.08, 0.80), (0.22, 0.58), (0.45, 0.50), (0.62, 0.41), (0.74, 0.47),
               (0.84, 0.39), (0.93, 0.43), (1.00, 0.34))
# bedding planes: k -> height; 1..4 inside the cliff, 5 cliff top, 6 cap base, 7 cap top
BOUNDARY_H = {1: DECHELLY[1], 2: DECHELLY[2], 3: DECHELLY[3], 4: DECHELLY[4], 5: DECHELLY[5],
              6: CAP_BASE, 7: CAP_TOP}
WOBBLE = 0.0011           # each ring's erosion, at most this proud or sunk
JOINT_D = (0.004, 0.018)  # vertical joints cut into the cliffs this deep
JOINT_W = (0.012, 0.045)  # and this wide along the face

# --- The talus aprons ------------------------------------------------------------
TALUS_DEG = (35.0, 31.0)  # the apron's slope at the cliff foot and at its toe (repose 30-37)
D_LIN = 0.150             # the straight run of the apron, m
APRON_IN = 0.004          # the apron starts this far out from the cliff's foot
TOE_D = 0.035             # then eases over this
TOE_SLOPE = 0.12          # to the floor's own gentle fall
STEEP_TALUS = (46.0, 42.0)   # --steep-talus piles the aprons this steep
TALUS_IN = 0.012          # an apron vertex counts as talus this far inside its straight run

# --- The formations: name, centre, semi-axes, turn, squareness, plan harmonics,
# ring vertices, joints, setback scale, kind
FORMS = (
    ("MesaWest", (-0.52, 0.40), (0.34, 0.28), 20.0, 2.6,
     ((2, 0.050, 0.4), (3, 0.045, 1.9), (5, 0.022, 0.2), (7, 0.012, 2.6)), 300, 14, 1.0, "mesa"),
    ("MesaEast", (0.56, 0.46), (0.31, 0.26), -15.0, 2.4,
     ((2, 0.045, 2.2), (3, 0.050, 0.7), (4, 0.020, 1.4), (6, 0.014, 0.3)), 280, 13, 1.0, "mesa"),
    ("Butte", (-0.46, -0.46), (0.140, 0.105), 35.0, 2.2,
     ((2, 0.040, 1.0), (3, 0.035, 2.8), (5, 0.018, 0.6)), 128, 6, 0.65, "butte"),
    ("Spire", (0.50, -0.44), (0.072, 0.062), 25.0, 2.0,
     ((2, 0.050, 0.3), (3, 0.040, 1.5)), 64, 4, 0.55, "spire"),
)
PERCH_BUTTE = 0.008       # --perch-butte stands the butte's foot this far over its bench, not in it
TILT_BEDS = 0.040         # --tilt-beds dips the east mesa this much per metre
DOME_CAP = 0.012          # --dome-cap raises the caprocks' middles this far

# --- The wash ----------------------------------------------------------------------
WASH_CTRL = ((0.060, HALF - 0.004), (0.060, HALF - 0.12), (0.050, 0.86), (0.015, 0.52), (0.065, 0.18), (0.000, -0.10),
             (0.105, -0.32), (0.065, -0.56), (-0.055, -0.80), (0.015, -0.98), (0.100, -HALF + 0.12), (0.100, -HALF + 0.004))
WASH_STEP = 0.004
WASH_W = (0.026, 0.046)   # half-width at the back edge, at the front
BANK = 0.008              # the wash bed this far under the floor on its line
BED_GAP = 0.004           # its sand this far over the channel's floor
CH_D = 0.016              # the channel's banks
FLAT2 = 0.60              # its floor flat out to sqrt(this) of the half-width
WASH_ROW = 0.008
WASH_SLAB = 0.012
LANES = (-1.25, -0.6, 0.0, 0.6, 1.25)
UPHILL = 0.020            # --uphill-wash raises the wash mid-course by this

# --- Scatter ------------------------------------------------------------------------
N_BLOCK = 60
N_JUNIPER = (22, 18)      # on the floor, on the mesa tops
N_SCRUB = (84, 34)
N_COTTON = 6
ROOT_D = 0.010            # a trunk starts this far under the ground
FLOAT_PLANTS = 0.03
ROCK_GAP = 0.006
REST_SINK = 0.004
SECTORS = 8

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (2.4000, 2.4000, 0.6221)
BASE_TRIS_MIN = 127100
BASE_TRIS_MAX = 128300
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 8
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 280
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# per material: ground, sandstone, caprock, wash, blocks, bark, foliage, plinth
FACE_FLOORS = (49660, 33880, 10300, 4280, 6280, 850, 16200, 1240)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05

SEAL_MIN = 0.010          # every formation's foot this far under its apron
STRATA_EPS = 0.0005       # every bedding plane at one height on every formation
CAP_FLAT = 0.0005         # a caprock's top within this of level
CAP_TILT_MAX = 0.2        # degrees
TALUS_BAND = (30.0, 37.0)
TALUS_FACES_MIN = 1500
DRAIN_EPS = 1e-6
EXIT_TOL = 0.010          # the wash's ends within this of the back and front edges
WASH_ENCLOSE_MIN = 0.003
PERCH_BAND = 0.003
ROOT_BAND = (0.004, 0.050)

HERO_YAW_DEG = 0.0
WALL_Y = 4.2

GROUND_IDX = 0
SAND_IDX = 1
CAP_IDX = 2
WASH_IDX = 3
BLOCK_IDX = 4
BARK_IDX = 5
FOLIAGE_IDX = 6
PLINTH_IDX = 7
MAT_LABELS = ("ground", "sandstone", "caprock", "wash", "blocks", "bark", "foliage", "plinth")

# part tags, one per face, so the audits can name a shell's role
P_TILE, P_FORM, P_WASH, P_ROCK, P_TRUNK, P_CROWN, P_SCRUB = 1, 2, 3, 4, 5, 6, 7


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

def hash01(a, b, c):
    """A closed-form draw in [0, 1) from three indices."""
    x = math.sin(a * 12.9898 + b * 78.233 + c * 37.719 + SEED * 0.0137) * 43758.5453
    return x - math.floor(x)

def perp_basis(d):
    ref = UP if abs(d.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = d.cross(ref).normalized()
    return e1, d.cross(e1).normalized()


def wrap(a):
    return (a + math.pi) % TAU - math.pi


def spire_girth(h):
    """The spire's girth at height ``h`` over the floor, a share of its foot's:
    smooth through SPIRE_GIRTH's knots."""
    t = min(max((h - APRON_TOP) / (DECHELLY[SPIRE_TOP] - APRON_TOP), 0.0), 1.0)
    for (t0, g0), (t1, g1) in zip(SPIRE_GIRTH, SPIRE_GIRTH[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0)
            u = u * u * (3.0 - 2.0 * u)
            return g0 + (g1 - g0) * u
    return SPIRE_GIRTH[-1][1]


def talus_drop(d, angles):
    """How far the apron has fallen ``d`` out from its top: a straight run
    whose slope eases from the first angle to the second (concave, as scree
    lies), a toe easing to the floor's own fall, then that fall."""
    t0, t1 = math.radians(angles[0]), math.radians(angles[1])
    k = (t1 - t0) / D_LIN

    def lin(u):
        return (math.log(math.cos(t0)) - math.log(math.cos(t0 + k * u))) / k

    if d <= D_LIN:
        return lin(d)
    tb = math.tan(t1)
    u = d - D_LIN
    if u <= TOE_D:
        return lin(D_LIN) + tb * u + (TOE_SLOPE - tb) * u * u / (2.0 * TOE_D)
    return lin(D_LIN) + 0.5 * (tb + TOE_SLOPE) * TOE_D + TOE_SLOPE * (u - TOE_D)


def dune_field(x, y):
    """Transverse dunes: across the wind each crest rises over a long stoss
    slope and drops down a short lee face; the field fades out at its edge."""
    cx, cy, full, gone = DUNE_FIELD
    m = smoothstep(math.hypot(x - cx, y - cy), gone, full)
    if m <= 0.0:
        return 0.0
    u = x * math.cos(DUNE_WIND) + y * math.sin(DUNE_WIND)
    v = -x * math.sin(DUNE_WIND) + y * math.cos(DUNE_WIND)
    ph = (u + 0.025 * math.sin(9.0 * v + 0.7)) / DUNE_L
    ph -= math.floor(ph)
    h = smoothstep(ph, 0.0, 0.8) if ph < 0.8 else smoothstep(1.0 - ph, 0.0, 0.2)
    return DUNE_H * h * m


def dune(x, y):
    return (0.55 * math.sin(4.1 * x + 1.3 * y + 0.4) * math.cos(3.3 * y - 1.1 * x + 1.2)
            + 0.30 * math.sin(9.7 * x - 6.1 * y + 2.2)
            + 0.15 * math.sin(19.0 * x + 15.0 * y + 0.5))


def catmull_open(ctrl, step):
    """A Catmull-Rom curve through the control points, resampled every
    ``step`` metres: (x, y, s) rows."""
    P = [ctrl[0]] + list(ctrl) + [ctrl[-1]]
    dense = []
    for k in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[k - 1], P[k], P[k + 1], P[k + 2]
        for m in range(40):
            t = m / 40.0
            t2, t3 = t * t, t * t * t
            dense.append(tuple(0.5 * ((2 * p1[c]) + (-p0[c] + p2[c]) * t
                                      + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2
                                      + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3) for c in (0, 1)))
    dense.append(ctrl[-1])
    acc = [0.0]
    for a, b in zip(dense, dense[1:]):
        acc.append(acc[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = acc[-1]
    out = []
    j = 0
    n = int(total / step)
    for i in range(n + 1):
        s = i * step
        while j < len(dense) - 2 and acc[j + 1] < s:
            j += 1
        seg = max(acc[j + 1] - acc[j], 1e-9)
        f = (s - acc[j]) / seg
        out.append((dense[j][0] + (dense[j + 1][0] - dense[j][0]) * f,
                    dense[j][1] + (dense[j + 1][1] - dense[j][1]) * f, s))
    return out


class Formation:
    """One mesa, butte or spire: a plan outline in closed form (a turned
    superellipse with a few harmonics), vertical joints cut into it, and its
    apron's distance field off a dense polyline of that outline."""

    def __init__(self, spec, idx):
        (self.name, c, ab, rot, p, harm, M, n_joints, scale, kind) = spec
        self.c = c
        self.a, self.b = ab
        self.rot = math.radians(rot)
        self.p = p
        self.harm = harm
        self.M = M
        self.scale = scale
        self.kind = kind
        self.idx = idx
        rng = random.Random(SEED * 31 + idx)
        self.joints = []
        for _ in range(n_joints):
            th = rng.uniform(0.0, TAU)
            depth = rng.uniform(*JOINT_D) * scale ** 1.5
            width = rng.uniform(*JOINT_W) * (0.6 + 0.4 * scale)
            self.joints.append((th, depth, width / self.R(th)))
        self.wob = [(rng.uniform(0.0, TAU), rng.uniform(0.0, TAU)) for _ in range(64)]
        n = 720
        self.foot = [self.at(TAU * k / n, self.R(TAU * k / n)) for k in range(n)]
        kd = KDTree(n)
        for i, (x, y) in enumerate(self.foot):
            kd.insert((x, y, 0.0), i)
        kd.balance()
        self.kd = kd

    def R(self, th):
        phi = th - self.rot
        r = (abs(math.cos(phi) / self.a) ** self.p + abs(math.sin(phi) / self.b) ** self.p) ** (-1.0 / self.p)
        return r * (1.0 + sum(a * math.sin(k * th + ph) for k, a, ph in self.harm))

    def flute(self, th):
        return sum(d * math.exp(-(wrap(th - tj) / w) ** 2) for tj, d, w in self.joints)

    def joint_share(self, h):
        """How much of its joints' depth the face carries at height ``h``:
        between 0.45 and 1, rising and falling up the cliff."""
        ph = 1.7 * self.idx
        return 0.725 + 0.275 * math.sin(TAU * h / 0.13 + ph) * math.cos(TAU * h / 0.047 + 0.5 * ph)

    def at(self, th, r):
        return self.c[0] + r * math.cos(th), self.c[1] + r * math.sin(th)

    def dist(self, x, y):
        """Out from the outline (negative inside it)."""
        dx, dy = x - self.c[0], y - self.c[1]
        r = math.hypot(dx, dy)
        R = self.R(math.atan2(dy, dx))
        if r <= R:
            return r - R
        _co, _i, d = self.kd.find((x, y, 0.0))
        return d

    def apron(self, x, y, angles):
        """(height, distance into the apron's straight run)."""
        d = self.dist(x, y) - APRON_IN
        if d <= 0.0:
            return FLOOR_Z + APRON_TOP, d
        return FLOOR_Z + APRON_TOP - talus_drop(d, angles), d

    def wobble(self, row, j, th, amp):
        p1, p2 = self.wob[row % len(self.wob)]
        return amp * self.scale * (0.6 * math.sin((7 + row % 5) * th + p1) + 0.4 * math.sin((19 + row % 7) * th + p2)
                                   + 0.5 * (hash01(self.idx, row, j) - 0.5))

    def rows(self):
        """The section bottom to top: (height over the floor, setback, bedding
        plane or -1, erosion)."""
        s = self.scale
        out = [(APRON_TOP - BURY, 0.0, -1, 0.0)]
        top_bed = SPIRE_TOP if self.kind == "spire" else 5
        for i in range(top_bed):
            hb, ht = DECHELLY[i], DECHELLY[i + 1]
            sb = BED_SB[i] * s
            lo = PARTING[i - 1] * s if i else 0.0
            hi = PARTING[i] * s
            e = BED_EDGE * (ht - hb)
            # a bed flush with the one under it shares that bed's top ring
            if not (out[-1][0] == hb and abs(out[-1][1] - (sb + lo)) < 1e-9):
                out.append((hb, sb + lo, i if i else -1, 0.5 * WOBBLE))
            # the bed's face: rounded out of the parting under it, standing
            # proud, rounded back into the parting over it
            out.append((hb + e, sb + 0.2 * BATTER * s, -1, 1.4 * WOBBLE))
            out.append((ht - e, sb + 0.8 * BATTER * s, -1, 1.4 * WOBBLE))
            if self.kind == "spire" and i == top_bed - 1:
                # the spire's top: a rounded shoulder to a flat at the bedding plane
                out.append((ht - CHAMFER_H, sb + BATTER * s + 0.002, -1, 0.5 * WOBBLE))
                out.append((ht, sb + BATTER * s + 0.006, i + 1, 0.0))
                return out
            out.append((ht, sb + BATTER * s + hi, i + 1, 0.5 * WOBBLE))
        for n, (h, sb) in enumerate(MOENKOPI):
            out.append((h, sb * s, 5 if n == 0 else (6 if n == len(MOENKOPI) - 1 else -1), 2.5 * WOBBLE))
        out.append((CAP_BASE, CAP_SB[0] * s, 6, 0.6 * WOBBLE))
        out.append((CAP_TOP - CHAMFER_H, CAP_SB[1] * s, -1, 0.6 * WOBBLE))
        out.append((CAP_TOP, CAP_SB[2] * s, 7, 0.0))
        return out


class Terrain:
    """The tile's ground in closed form: the floor, every formation's apron,
    the wash's channel. The wash's bed is read off the floor along its line
    and held falling all the way across."""

    def __init__(self, flags):
        self.flags = flags
        self.angles = STEEP_TALUS if flags.get("steep_talus") else TALUS_DEG
        self.forms = [Formation(s, i) for i, s in enumerate(FORMS)]
        self.path = catmull_open(WASH_CTRL, WASH_STEP)
        self.length = self.path[-1][2]
        kd = KDTree(len(self.path))
        for i, (x, y, _s) in enumerate(self.path):
            kd.insert((x, y, 0.0), i)
        kd.balance()
        self.kd = kd
        z = 9.0
        self.wz = []
        for x, y, _s in self.path:
            z = min(z, self.base(x, y)[0] - BANK)
            self.wz.append(z)

    def floor(self, x, y):
        return FLOOR_Z + FLOOR_TILT * y / HALF + DUNE * dune(x, y) + dune_field(x, y)

    def base(self, x, y):
        """Ground without the wash: (z, talus) — talus where one apron alone
        holds the ground inside its straight run."""
        fl = self.floor(x, y)
        hs = sorted((f.apron(x, y, self.angles) for f in self.forms), reverse=True)
        h0, d0 = hs[0]
        h1 = hs[1][0]
        z = max(fl, h0)
        talus = (TALUS_IN <= d0 <= D_LIN - TALUS_IN and h0 > max(fl, h1) + 0.006)
        return z, talus

    def width(self, s):
        f = min(max(s / self.length, 0.0), 1.0)
        w = WASH_W[0] + (WASH_W[1] - WASH_W[0]) * f
        return w * (1.0 + 0.16 * math.sin(17.0 * s + 0.6) + 0.08 * math.sin(43.0 * s + 2.0))

    def near(self, x, y):
        _co, i, d = self.kd.find((x, y, 0.0))
        return i, d

    def sample(self, x, y):
        """(z, talus) with the wash's channel cut."""
        z, talus = self.base(x, y)
        i, d = self.near(x, y)
        w = self.width(self.path[i][2])
        ch = self.wz[i] - BED_GAP + CH_D * max(0.0, (d / w) ** 2 - FLAT2)
        if ch < z:
            z = ch
        if d < 2.4 * w + 0.02:
            talus = False
        return z, talus

    def slope(self, x, y, h=0.006):
        zx = self.sample(x + h, y)[0] - self.sample(x - h, y)[0]
        zy = self.sample(x, y + h)[0] - self.sample(x, y - h)[0]
        return math.hypot(zx, zy) / (2.0 * h)

    def form_at(self, x, y, pad=0.0):
        """The formation whose outline (grown by ``pad``) holds (x, y), if any."""
        for f in self.forms:
            if f.dist(x, y) < pad:
                return f
        return None

    def in_wash(self, x, y, pad):
        i, d = self.near(x, y)
        return d < self.width(self.path[i][2]) * 1.3 + pad


class Ground:
    """The built tile and formations, sampled by a ray straight down, so
    everything seated on them sits on the faces actually shipped."""

    def __init__(self, tree):
        self.tree = tree

    def z(self, x, y):
        loc, _n, _i, _d = self.tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
        return 0.0 if loc is None else loc.z


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------

def plan_scene(T):
    """Every seeded draw, before anything is built."""
    rng = random.Random(SEED)
    plan = {}
    taken = []   # (x, y, r): placed blocks and plants

    def clear(x, y, r):
        return all(math.hypot(x - a, y - b) >= r + c + ROCK_GAP for a, b, c in taken)

    def inside(x, y, pad):
        return abs(x) < HALF - pad and abs(y) < HALF - pad

    blocks = []
    areas = [f.a * f.b for f in T.forms]
    for _ in range(6000):
        if len(blocks) >= N_BLOCK:
            break
        pick = rng.uniform(0.0, sum(areas))
        k = 0
        while pick > areas[k] and k < len(areas) - 1:
            pick -= areas[k]
            k += 1
        f = T.forms[k]
        th = rng.uniform(0.0, TAU)
        out = rng.uniform(0.0, 1.0)
        big = rng.uniform(0.0, 1.0)
        draws = [rng.uniform(0.0, 1.0) for _ in range(8)]
        # the biggest blocks roll furthest, out to the toe
        r = 0.008 + 0.014 * big ** 1.7 + 0.014 * out * big
        R = f.R(th)
        x, y = f.at(th, R + APRON_IN + 1.8 * r + 0.010 + out * (D_LIN + TOE_D + 0.03))
        if not inside(x, y, 0.06) or T.in_wash(x, y, r + 0.02) or not clear(x, y, r * 1.4):
            continue
        if T.form_at(x, y, APRON_IN + 1.6 * r + 0.006) is not None:
            continue
        taken.append((x, y, r * 1.4))
        blocks.append({"x": x, "y": y, "r": r, "out": out, "long": 1.05 + 0.6 * draws[0], "flat": 0.55 + 0.35 * draws[1],
                       "yaw": TAU * draws[2], "tone": draws[3],
                       "waves": [(Vector((draws[4] - 0.5, draws[5] - 0.5, draws[6] - 0.3)), TAU * draws[7], 1.0),
                                 (Vector((draws[5] - 0.5, draws[7] - 0.5, draws[4] - 0.5)), TAU * draws[6], 0.6)]})
    plan["blocks"] = blocks

    plants = []

    def put(kind, x, y, r, size, tone, spin, top):
        taken.append((x, y, r))
        plants.append({"kind": kind, "x": x, "y": y, "r": r, "size": size, "tone": tone, "spin": spin, "top": top})

    # cottonwoods on the wash's banks, then junipers and scrub on the floor
    for kind, n, tries in (("cotton", N_COTTON, 6000), ("juniper", N_JUNIPER[0], 6000), ("scrub", N_SCRUB[0], 9000)):
        got = 0
        for _ in range(tries):
            if got >= n:
                break
            size = rng.uniform(0.0, 1.0)
            tone = rng.uniform(0.0, 1.0)
            spin = rng.uniform(0.0, TAU)
            keep = rng.uniform(0.0, 1.0)
            if kind == "cotton":
                s = rng.uniform(0.15, 0.95) * T.length
                side = rng.choice((-1.0, 1.0))
                i = min(int(s / WASH_STEP), len(T.path) - 2)
                px, py, _s = T.path[i]
                qx, qy, _s = T.path[i + 1]
                ln = math.hypot(qx - px, qy - py) or 1.0
                r = 0.034 + 0.010 * size
                off = T.width(s) * 1.7 + r * 0.6 + 0.016
                x, y = px - (qy - py) / ln * off * side, py + (qx - px) / ln * off * side
                if T.in_wash(x, y, 0.004):
                    continue
            else:
                x = rng.uniform(-HALF, HALF)
                y = rng.uniform(-HALF, HALF)
                r = 0.020 + 0.010 * size if kind == "juniper" else 0.010 + 0.008 * size
                if T.in_wash(x, y, r + 0.012):
                    continue
            if not inside(x, y, 0.05) or not clear(x, y, r):
                continue
            if T.form_at(x, y, APRON_IN + r + 0.012) is not None:
                continue
            sl = T.slope(x, y)
            if sl > (0.30 if kind != "scrub" else 0.45):
                continue
            # in loose clumps: a field in space
            clump = 0.5 + 0.5 * math.sin(6.0 * x + 2.0 * y + 0.7) * math.cos(4.5 * y - 3.0 * x + 1.1)
            if kind != "cotton" and keep > 0.25 + clump:
                continue
            put(kind, x, y, r, size, tone, spin, -1)
            got += 1
    # junipers and scrub on the mesa tops and the butte's
    capped = [f for f in T.forms if f.kind != "spire"]
    for kind, n in (("juniper", N_JUNIPER[1]), ("scrub", N_SCRUB[1])):
        got = 0
        for _ in range(4000):
            if got >= n:
                break
            f = capped[0] if rng.uniform(0.0, 1.0) < 0.5 else capped[1 if rng.uniform(0.0, 1.0) < 0.8 else 2]
            th = rng.uniform(0.0, TAU)
            u = math.sqrt(rng.uniform(0.0, 1.0))
            size = rng.uniform(0.0, 1.0)
            tone = rng.uniform(0.0, 1.0)
            spin = rng.uniform(0.0, TAU)
            r = (0.016 + 0.008 * size) if kind == "juniper" else (0.008 + 0.005 * size)
            edge = f.R(th) - f.flute(th) - CAP_SB[2] * f.scale - 1.5 * r - 0.012
            if edge <= 0.0:
                continue
            x, y = f.at(th, u * edge)
            if f.dist(x, y) > -(CAP_SB[2] * f.scale + 0.006 + r) or not clear(x, y, r):
                continue
            put(kind, x, y, r, size, tone, spin, f.idx)
            got += 1
    plan["plants"] = plants
    return plan


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

class Builder:
    """The bmesh plus its layers: Tone (shading variety), Zone (a caprock's
    or spire's top), Part (the shell's role), Ident (which formation, block
    or plant), Cap (1 on a shell's bottom, 3 on the tile's skirt), and per
    vertex Ring (a wash row), Lane (its place across), Bed (the bedding
    plane a formation's ring lies on), Talus (an apron vertex in its
    straight run), Flow (along the wash)."""

    def __init__(self, bm):
        self.bm = bm
        self.tone = bm.faces.layers.float.new("Tone")
        self.zone = bm.faces.layers.float.new("Zone")
        self.part = bm.faces.layers.int.new("Part")
        self.ident = bm.faces.layers.int.new("Ident")
        self.cap = bm.faces.layers.int.new("Cap")
        self.ring = bm.verts.layers.int.new("Ring")
        self.lane = bm.verts.layers.int.new("Lane")
        self.bed = bm.verts.layers.int.new("Bed")
        self.talus = bm.verts.layers.int.new("Talus")
        self.flow = bm.verts.layers.float.new("Flow")
        self.uv = bm.loops.layers.uv.new("UVMap")

    def vert(self, co, ring=-1, lane=-1):
        v = self.bm.verts.new(co)
        v[self.ring] = ring
        v[self.lane] = lane
        v[self.bed] = -1
        return v

    def face(self, verts, mat, tone, part, ident=0, cap=0, zone=0.0):
        f = self.bm.faces.new(verts)
        f.material_index = mat
        f[self.tone] = tone
        f[self.part] = part
        f[self.ident] = ident
        f[self.cap] = cap
        f[self.zone] = zone
        return f

    def quad(self, a, b, c, d, *args, **kw):
        """Split on the short diagonal, so a ray lands on the face shipped."""
        if (a.co - c.co).length <= (b.co - d.co).length:
            self.face((a, b, c), *args, **kw)
            self.face((a, c, d), *args, **kw)
        else:
            self.face((a, b, d), *args, **kw)
            self.face((b, c, d), *args, **kw)


def add_tile(B, T, n):
    """The tile: a square lattice carrying the floor, the aprons and the
    wash's channel, and a skirt straight down to a flat base at Z = 0."""
    step = SIDE / n
    grid = []
    for j in range(n + 1):
        row = []
        for i in range(n + 1):
            x, y = -HALF + i * step, -HALF + j * step
            z, talus = T.sample(x, y)
            v = B.vert((x, y, z))
            v[B.talus] = 1 if talus else 0
            row.append(v)
        grid.append(row)
    for j in range(n):
        for i in range(n):
            B.quad(grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i], GROUND_IDX, 0.5, P_TILE)
    rim = ([grid[0][i] for i in range(n)] + [grid[j][n] for j in range(n)]
           + [grid[n][i] for i in range(n, 0, -1)] + [grid[j][0] for j in range(n, 0, -1)])
    low = [B.vert((v.co.x, v.co.y, 0.0)) for v in rim]
    m = len(rim)
    for j in range(m):
        q = (j + 1) % m
        B.face((rim[q], rim[j], low[j], low[q]), PLINTH_IDX, 0.5, P_TILE, cap=3)
    mid = B.vert((0.0, 0.0, 0.0))
    for j in range(m):
        q = (j + 1) % m
        B.face((mid, low[q], low[j]), PLINTH_IDX, 0.5, P_TILE, cap=1)


def add_formation(B, f, detail_, flags):
    """A formation as one closed loft: rings round its outline bottom to
    top, stepped back at each bedding plane (two rings at one height make
    the ledge), the slope over the cliff, the caprock overhanging it; a
    flat top in concentric rings and a fan underneath."""
    M = f.M if detail_ == "low" else int(f.M * 1.5)
    rows = f.rows()
    if flags.get("perch_butte") and f.kind == "butte":
        # the foot set on the bench instead of run into it: the cliff and
        # everything over it stay where they were
        rows = [(APRON_TOP + PERCH_BUTTE, 0.0, -1, 0.0)] + rows[2:]
    ident = 10 + f.idx
    cx, cy = f.c
    tilt = TILT_BEDS if (flags.get("tilt_beds") and f.idx == 1) else 0.0

    def lifted(x, y, z):
        return z + tilt * (x - cx)

    ths = [TAU * j / M for j in range(M)]
    plan_r = [f.R(th) for th in ths]
    flutes = [f.flute(th) for th in ths]
    rings = []
    for ri, (h, sb, tag, amp) in enumerate(rows):
        ring = []
        # the joints open and close up the face (one value per height, so
        # two rings at a ledge agree), never quite shut
        jk = f.joint_share(h)
        for j, th in enumerate(ths):
            r = plan_r[j] - jk * flutes[j] - sb - (f.wobble(ri, j, th, amp) if amp else 0.0)
            if f.kind == "spire":
                r *= spire_girth(h)
            x, y = f.at(th, r)
            v = B.vert((x, y, lifted(x, y, FLOOR_Z + h)))
            v[B.bed] = tag
            ring.append(v)
        rings.append((h, ring))
    for (ha, a), (hb, b) in zip(rings, rings[1:]):
        mat = CAP_IDX if min(ha, hb) >= CAP_BASE - 1e-9 else SAND_IDX
        for j in range(M):
            q = (j + 1) % M
            B.quad(a[j], a[q], b[q], b[j], mat, 0.5, P_FORM, ident)
    # the top: concentric rings to a centre, flat (zone 1 on a caprock)
    top_h, top = rings[-1]
    zone = 2.0 if f.kind == "spire" else 1.0
    mat = SAND_IDX if f.kind == "spire" else CAP_IDX
    K = 4
    dome = DOME_CAP if (flags.get("dome_cap") and f.kind != "spire") else 0.0
    prev = top
    for k in range(1, K + 1):
        sc = 1.0 - k / (K + 1.0)
        cur = []
        for v in top:
            x = cx + (v.co.x - cx) * sc
            y = cy + (v.co.y - cy) * sc
            cur.append(B.vert((x, y, lifted(x, y, FLOOR_Z + top_h) + dome * k / (K + 1.0))))
        for j in range(M):
            q = (j + 1) % M
            B.quad(prev[j], prev[q], cur[q], cur[j], mat, 0.5, P_FORM, ident, zone=zone)
        prev = cur
    apex = B.vert((cx, cy, lifted(cx, cy, FLOOR_Z + top_h) + dome))
    for j in range(M):
        B.face((prev[j], prev[(j + 1) % M], apex), mat, 0.5, P_FORM, ident, zone=zone)
    _h0, bottom = rings[0]
    foot = B.vert((cx, cy, lifted(cx, cy, FLOOR_Z + rows[0][0])))
    for j in range(M):
        B.face((bottom[(j + 1) % M], bottom[j], foot), SAND_IDX, 0.5, P_FORM, ident, cap=1)


def wash_z(T, s, flags):
    i = min(max(int(round(s / WASH_STEP)), 0), len(T.path) - 1)
    z = T.wz[i]
    if flags.get("uphill_wash"):
        z += UPHILL * math.exp(-((s - 0.5 * T.length) / 0.08) ** 2)
    return z


def add_wash(B, T, flags):
    """The wash's bed: a ribbon of sand edge to edge across the tile, its
    surface flat across and falling along, its edges run under the banks.
    Section: five lanes on top, two corners under."""
    rows = []
    s = 0.0
    while s <= T.length + 1e-9:
        rows.append(s)
        s += WASH_ROW
    if T.length - rows[-1] > 1e-6:
        rows.append(T.length)
    sec = []
    for r, s in enumerate(rows):
        i = min(int(round(s / WASH_STEP)), len(T.path) - 2)
        x, y, _s = T.path[i]
        nx_, ny_, _ = T.path[i + 1]
        if i + 1 == len(T.path) - 1 and r == len(rows) - 1:
            x, y = nx_, ny_
            px, py, _ = T.path[i]
            tx, ty = x - px, y - py
        else:
            tx, ty = nx_ - x, ny_ - y
        ln = math.hypot(tx, ty) or 1.0
        lx, ly = -ty / ln, tx / ln
        w = T.width(s)
        z = wash_z(T, s, flags)
        ring = []
        for li, f in enumerate(LANES):
            v = B.vert((x + lx * f * w, y + ly * f * w, z), ring=r, lane=li)
            v[B.flow] = s / T.length
            ring.append(v)
        for f in (LANES[-1], LANES[0]):
            v = B.vert((x + lx * f * w, y + ly * f * w, z - WASH_SLAB), ring=r, lane=-1)
            v[B.flow] = s / T.length
            ring.append(v)
        sec.append(ring)
    L = len(LANES)
    m = len(sec[0])
    for a, b in zip(sec, sec[1:]):
        for k in range(m):
            q = (k + 1) % m
            zone = 1.0 if k < L - 1 else 0.0
            B.quad(a[k], b[k], b[q], a[q], WASH_IDX, 0.5, P_WASH, 3, zone=zone)
    for ring, cap, flip in ((sec[0], 1, False), (sec[-1], 2, True)):
        fan = [(ring[m - 1], ring[k], ring[k + 1]) for k in range(m - 2)]
        for tri in fan:
            B.face(tuple(reversed(tri)) if flip else tri, WASH_IDX, 0.5, P_WASH, 3, cap=cap)


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

def seat(points, G, sink, perch):
    """Sink until every sector's most-buried vertex is ``sink`` under the
    ground; ``perch`` seats the lowest vertex against the ground at the
    centre alone."""
    cx = sum(p.x for p in points) / len(points)
    cy = sum(p.y for p in points) / len(points)
    if perch:
        zmin = min(p.z for p in points)
        return G.z(cx, cy) - sink - zmin
    best = [None] * SECTORS
    for p in points:
        s = min(SECTORS - 1, int((math.atan2(p.y - cy, p.x - cx) % TAU) / TAU * SECTORS))
        d = G.z(p.x, p.y) - p.z
        best[s] = d if best[s] is None else max(best[s], d)
    return min(b for b in best if b is not None) - sink


CUT_DIRS = tuple(Vector(d).normalized() for d in ((0.05, 0.02, 1.0), (1.0, 0.1, 0.08), (-0.95, 0.2, 0.1),
                                                    (0.15, 1.0, -0.05), (-0.1, -1.0, 0.12), (0.6, -0.5, 0.62),
                                                    (-0.5, 0.6, -0.6)))


def add_rocks(B, plan, G, flags):
    """Fallen blocks: squared off by bedding and joint planes, rounded a
    little at the arrises, sunk into the talus they came to rest on."""
    perch = flags.get("perch_rock", False)
    items = [dict(it) for it in plan["blocks"]]
    if flags.get("pile_rocks"):
        # two more blocks dropped against the one lying furthest out
        a = max(range(len(items)), key=lambda i: items[i]["out"])
        for k, it in enumerate(it for i, it in enumerate(items) if i != a and i < 3):
            it["x"] = items[a]["x"] + (0.6 if k else -0.6) * items[a]["r"]
            it["y"] = items[a]["y"] + 0.3 * items[a]["r"]
    for n, it in enumerate(items):
        dirs, quads = cube_sphere(3)
        r = it["r"]
        ax = Vector((r * it["long"], r, r * it["flat"]))
        yaw = Matrix.Rotation(it["yaw"], 3, "Z")
        tip = Matrix.Rotation(0.35 * (it["tone"] - 0.5), 3, "X")
        pts = []
        for d in dirs:
            q = Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z))
            q *= 1.0 + 0.04 * sum(a * math.sin(w.normalized().dot(d) * 3.0 + ph) for w, ph, a in it["waves"])
            for k, cdir in enumerate(CUT_DIRS):
                lim = (0.56 + 0.14 * hash01(n, k, 5)) * (ax.x * abs(cdir.x) + ax.y * abs(cdir.y) + ax.z * abs(cdir.z))
                proj = q.dot(cdir)
                if proj > lim:
                    q -= cdir * (proj - lim)
            pts.append(yaw @ (tip @ q) + Vector((it["x"], it["y"], 0.0)))
        if perch:
            dz = seat(pts, G, REST_SINK, True)
        else:
            dz = min(seat(pts, G, REST_SINK, False), G.z(it["x"], it["y"]) - min(p.z for p in pts) - 0.30 * 2.0 * ax.z)
        verts = [B.vert(p + Vector((0.0, 0.0, dz))) for p in pts]
        for q in quads:
            B.quad(*[verts[i] for i in q], BLOCK_IDX, 0.1 + 0.8 * it["tone"], P_ROCK, 100 + n)


def tube(B, pts, radii, sides, mat, tone, part, ident, phase=0.0):
    pts = [Vector(p) for p in pts]
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    nrm = perp_basis(tans[0])[0]
    rings = []
    for i, (p, t, r) in enumerate(zip(pts, tans, radii)):
        nrm = (nrm - t * nrm.dot(t)).normalized()
        b = t.cross(nrm)
        rings.append([B.vert(p + r * (nrm * math.cos(TAU * k / sides + phase) + b * math.sin(TAU * k / sides + phase)),
                             ring=i) for k in range(sides)])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            B.face((r0[k], r0[m], r1[m], r1[k]), mat, tone, part, ident)
    B.face(tuple(reversed(rings[0])), mat, tone, part, ident, cap=1)
    B.face(tuple(rings[-1]), mat, tone, part, ident, cap=2)


def lump_ball(B, centre, ax, spin, tn, ident, part=P_CROWN, n=2, rough=0.12):
    dirs, quads = cube_sphere(n)
    hv = []
    for d in dirs:
        lump = 1.0 + rough * math.sin(9.0 * d.x + 5.0 * d.y + 7.0 * tn) * math.cos(8.0 * d.z + 2.0 * tn)
        q = spin @ Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z)) * lump
        hv.append(B.vert(centre + q))
    for q in quads:
        B.quad(*[hv[i] for i in q], FOLIAGE_IDX, tn, part, ident)
    return hv


def add_plants(B, plan, G, flags):
    """Utah junipers: a short twisted trunk under a few dense, lopsided
    clumps, dark blue-green. Sage scrub: low grey-green cushions sunk in the
    sand. Cottonwoods on the wash's banks: a forked trunk under a broad
    crown, turning gold."""
    for n, t in enumerate(plan["plants"]):
        # --float-plants lifts the plants on the floor (the mesa tops' would
        # lift the tile's envelope and steal the exit)
        lift = FLOAT_PLANTS if (flags.get("float_plants") and t["top"] < 0) else 0.0
        x, y = t["x"], t["y"]
        ident = 200 + n
        g = min(G.z(x + 0.006 * math.cos(a), y + 0.006 * math.sin(a)) for a in (0.0, 2.1, 4.2))
        g = min(g, G.z(x, y))
        spin = Matrix.Rotation(t["spin"], 3, "Z")
        if t["kind"] == "scrub":
            r = t["r"]
            # big sagebrush silver grey-green; on the floor about one cushion
            # in three rubber rabbitbrush, olive going to gold
            rabbit = t["top"] < 0 and hash01(n, 7, 3) < 0.33
            tone = 0.62 + 0.05 * t["tone"] if rabbit else 0.36 + 0.22 * t["tone"]
            hv = lump_ball(B, Vector((x, y, 0.0)), Vector((r, r * (0.75 + 0.2 * t["size"]), r * 0.50)),
                           spin, tone, ident, P_SCRUB, 2, 0.30)
            # sunk in every sector, like a block, however the ground slopes
            # (each a fraction of a millimetre deeper than the last, so two
            # cushions on the level caprock never share their buried plane)
            dz = seat([v.co for v in hv], G, REST_SINK, False) + lift - 0.0008 * hash01(n, 11, 2)
            for v in hv:
                v.co.z += dz
            continue
        foot = Vector((x, y, g - ROOT_D + lift))
        if t["kind"] == "juniper":
            # Utah juniper / pinyon: a short gnarled stem leaning out of the
            # ground under a low, broad, lopsided crown of a few dense clumps
            # that sweeps down nearly to the sand on one side
            h = 0.026 + 0.016 * t["size"]
            lean = spin @ Vector((0.30 * h, 0.0, 0.0))
            mid = foot + Vector((0.0, 0.0, ROOT_D + 0.22 * h)) + 0.4 * lean
            top = foot + Vector((0.0, 0.0, ROOT_D + 0.42 * h)) + lean
            tr = 0.0024 + 0.0010 * t["size"]
            tube(B, (foot, mid, top), (tr * 1.3, tr, tr * 0.7), 6, BARK_IDX, t["tone"], P_TRUNK, ident)
            tone = 0.04 + 0.24 * t["tone"]
            rc = t["r"] * 0.78
            for k, (ox, oy, oz, s) in enumerate(((0.0, 0.0, 0.55, 0.95), (0.85, 0.30, 0.05, 0.70),
                                                 (-0.60, 0.55, 0.20, 0.72), (-0.25, -0.75, 0.00, 0.62),
                                                 (0.40, -0.35, 0.85, 0.55))):
                c = top + spin @ Vector((ox * rc, oy * rc, oz * rc))
                lump_ball(B, c, Vector((rc * s * 1.15, rc * s, rc * s * 0.70)),
                          Matrix.Rotation(t["spin"] + 1.3 * k, 3, "Z"), tone, ident, P_CROWN, 2, 0.24)
        else:
            h = 0.070 + 0.025 * t["size"]
            tr = 0.0045 + 0.0012 * t["size"]
            fork = foot + Vector((0.0, 0.0, ROOT_D + 0.32 * h))
            tube(B, (foot, fork), (tr * 1.15, tr), 6, BARK_IDX, t["tone"], P_TRUNK, ident)
            tone = 0.72 + 0.26 * t["tone"]
            rc = t["r"]
            for k, (ox, oy, oz, s) in enumerate(((0.0, 0.0, 0.95, 1.0), (0.60, 0.20, 0.70, 0.78),
                                                 (-0.50, 0.40, 0.75, 0.74), (-0.10, -0.62, 0.65, 0.72),
                                                 (0.30, -0.30, 1.25, 0.62))):
                c = fork + spin @ Vector((ox * rc, oy * rc, oz * rc))
                lump_ball(B, c, Vector((rc * s, rc * s * 0.95, rc * s * 0.80)),
                          Matrix.Rotation(t["spin"] + k, 3, "Z"), tone, ident, P_CROWN, 2, 0.14)


def break_coplanar(B, parts, passes=8):
    """Bough tiers, lumps and rocks are many small faces in every direction;
    now and then one lands in another shell's plane. Turn the shell's piece
    a few degrees about the vertical through its lowest point, and sink it
    a third of a millimetre, until none does."""
    bm = B.bm
    for _ in range(passes):
        bm.normal_update()
        bm.verts.index_update()
        faces = list(bm.faces)
        # shells by connectivity, cheaply: the ident of a part, else the tile
        key = [(f[B.part], f[B.ident]) for f in faces]
        cent = [f.calc_center_median() for f in faces]
        kd = KDTree(len(faces))
        for i, c in enumerate(cent):
            kd.insert(c, i)
        kd.balance()
        bad = set()
        for i, f in enumerate(faces):
            if key[i][0] not in parts:
                continue
            for _co, j, _d in kd.find_range(cent[i], COPLANAR_CENTRE_MAX):
                if key[j] == key[i]:
                    continue
                g = faces[j]
                if abs(abs(f.normal.dot(g.normal)) - 1.0) > 4.0 * COPLANAR_NORMAL_EPS:
                    continue
                if abs(f.normal.dot(cent[j] - cent[i])) > 4.0 * COPLANAR_PLANE_EPS:
                    continue
                # move one of the pair only: moving both alike keeps them coplanar
                bad.add(max(key[i], key[j]) if key[j][0] in parts else key[i])
        if not bad:
            return
        for k in sorted(bad):
            vs = {v for f, kk in zip(faces, key) if kk == k for v in f.verts}
            root = min(vs, key=lambda v: v.co.z).co.copy()
            R = Matrix.Rotation(math.radians(3.0), 3, "Z")
            # and a third of a millimetre down, which a turn about the
            # vertical cannot do for a level face
            for v in vs:
                v.co = root + R @ (v.co - root) - Vector((0.0, 0.0, 0.0003))


def build_mesh(name, T, plan, detail_="low", **flags):
    bm = bmesh.new()
    try:
        B = Builder(bm)
        add_tile(B, T, TILE_N[detail_])
        for f in T.forms:
            add_formation(B, f, detail_, flags)
        bm.normal_update()
        G = Ground(BVHTree.FromBMesh(bm))
        add_wash(B, T, flags)
        add_rocks(B, plan, G, flags)
        add_plants(B, plan, G, flags)
        triangulate_ngons(bm)
        break_coplanar(B, (P_ROCK, P_TRUNK, P_CROWN, P_SCRUB))
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        # Everything smooth-shaded, with every material boundary and every
        # fold sharper than its crease a hard edge.
        crease = {GROUND_IDX: 50.0, SAND_IDX: 40.0, CAP_IDX: 40.0, BLOCK_IDX: 24.0, FOLIAGE_IDX: 70.0,
                  PLINTH_IDX: 30.0, BARK_IDX: 70.0, WASH_IDX: 40.0}
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(crease.get(mats.pop(), 60.0))
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        me.uv_layers.active = me.uv_layers["UVMap"]
        me.uv_layers["UVMap"].active_render = True
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def build_collider_source(T):
    """Point groups for one convex hull each: the tile's slab up to the
    floor, and each formation from its apron's toe to its top. Units walk
    the floor and climb the aprons; the cliffs stop them."""
    groups = [[Vector((sx * HALF, sy * HALF, z)) for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)
               for z in (0.0, FLOOR_Z - FLOOR_TILT)]]
    for f in T.forms:
        rows = f.rows()
        top_h, top_sb = rows[-1][0], rows[-1][1]
        pts = []
        for k in range(16):
            th = TAU * k / 16
            R = f.R(th)
            reach = APRON_IN + D_LIN + TOE_D
            for r, z in ((R + reach, FLOOR_Z - FLOOR_TILT), (R, FLOOR_Z + APRON_TOP),
                         (R - top_sb, FLOOR_Z + top_h)):
                x, y = f.at(th, r)
                pts.append(Vector((x, y, z)))
        groups.append(pts)
    return groups


def triangulate_ngons(bm):
    bm.faces.index_update()
    faces = sorted((f for f in bm.faces if len(f.verts) > 4), key=lambda f: f.index)
    if faces:
        bmesh.ops.triangulate(bm, faces=faces)

def pack_uvs(bm, margin=0.08):
    uv = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
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

def noise(nt, vec, scale, detail_, roughness):
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail_
    node.inputs["Roughness"].default_value = roughness
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]

def voronoi_node(nt, vec, scale, feature="F1"):
    node = nt.nodes.new("ShaderNodeTexVoronoi")
    node.feature = feature
    node.inputs["Scale"].default_value = scale
    nt.links.new(vec, node.inputs["Vector"])
    return node

def voronoi(nt, vec, scale, feature="F1"):
    return voronoi_node(nt, vec, scale, feature).outputs["Distance"]

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

def mul(nt, *vals):
    out = vals[0]
    for v in vals[1:]:
        out = math_node(nt, "MULTIPLY", out, v)
    return out

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

def coord_xyz(nt, coord):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    return sep.outputs

def normal_xyz(nt):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
    return sep.outputs

def add_bump(nt, bsdf, height, strength, distance):
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

def translucent(nt, bsdf, rgb, amount):
    out = nt.nodes["Material Output"]
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = (*rgb, 1.0)
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = amount
    nt.links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])


def ground_material():
    mat, nt, bsdf, coord = surface("DesertGround")
    # The valley floor: red sand in broad drifts and darker hardpan, pale
    # wind-blown sheets streaking downwind, black desert pavement in patches,
    # dark specks of scrub litter; the aprons Organ Rock shale under grey and
    # buff rubble, scored by rills down the fall line.
    xyz = coord_xyz(nt, coord)
    z = xyz["Z"]
    nz = normal_xyz(nt)["Z"]
    macro = noise(nt, coord, 1.3, 3.0, 0.5)
    patch = noise(nt, coord, 4.5, 4.0, 0.55)
    fine = noise(nt, coord, 80.0, 3.0, 0.6)
    sand = ramp(nt, patch, ((0.36, (0.24, 0.085, 0.042)), (0.47, (0.33, 0.130, 0.062)),
                            (0.56, (0.40, 0.175, 0.085)), (0.66, (0.46, 0.24, 0.13))))
    # hardpan: darker brick-red flats with a crazing of cracks
    hard = remap(nt, macro, 0.47, 0.41, 0.0, 1.0)
    craze = voronoi(nt, coord, 45.0, "DISTANCE_TO_EDGE")
    hp = mix_color(nt, (0.24, 0.070, 0.032), (0.11, 0.035, 0.020), remap(nt, craze, 0.02, 0.0, 0.0, 0.7))
    sand = mix_color(nt, sand, hp, mul(nt, hard, 0.85))
    # pale sheets of blown sand, long downwind
    sheet = noise(nt, mapping(nt, coord, scale=(2.2, 9.0, 1.0)), 2.0, 3.0, 0.5)
    sand = mix_color(nt, sand, (0.56, 0.31, 0.16), remap(nt, sheet, 0.52, 0.62, 0.0, 0.6))
    sand = mix_color(nt, sand, (0.20, 0.060, 0.025), remap(nt, fine, 0.30, 0.70, 0.30, 0.0))
    # broad swings of the sand's colour across the tile: deep terracotta in
    # the hollows, pale apricot where it is fresh-blown
    swing = noise(nt, coord, 0.9, 2.0, 0.5)
    sand = mix_color(nt, sand, (0.22, 0.060, 0.026), remap(nt, swing, 0.46, 0.36, 0.0, 0.55))
    sand = mix_color(nt, sand, (0.60, 0.34, 0.18), remap(nt, swing, 0.56, 0.68, 0.0, 0.45))
    # wind ripples on the flats
    rd = nt.nodes.new("ShaderNodeVectorMath")
    rd.operation = "DOT_PRODUCT"
    nt.links.new(coord, rd.inputs[0])
    rd.inputs[1].default_value = (0.35, 0.94, 0.0)
    ripples = math_node(nt, "SINE", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", rd.outputs["Value"], math_node(nt, "MULTIPLY", noise(nt, coord, 8.0, 2.0, 0.5), 0.02)), 520.0), 0.0)
    flat = remap(nt, nz, 0.96, 0.99, 0.0, 1.0)
    sand = mix_color(nt, sand, (0.58, 0.28, 0.12), mul(nt, remap(nt, ripples, 0.4, 1.0, 0.0, 0.12), flat,
                                                      remap(nt, hard, 0.5, 0.0, 0.0, 1.0)))
    # desert pavement: dark varnished pebbles in patches; scrub litter
    peb = voronoi(nt, coord, 170.0)
    pave = mul(nt, remap(nt, peb, 0.16, 0.06, 0.0, 1.0),
               remap(nt, noise(nt, coord, 2.6, 2.0, 0.5), 0.52, 0.60, 0.0, 1.0), flat)
    sand = mix_color(nt, sand, (0.07, 0.035, 0.024), mul(nt, pave, 0.9))
    litter = voronoi(nt, coord, 420.0)
    sand = mix_color(nt, sand, (0.06, 0.05, 0.03), mul(nt, remap(nt, litter, 0.10, 0.04, 0.0, 0.7),
                                                     remap(nt, noise(nt, coord, 6.0, 2.0, 0.5), 0.5, 0.6, 0.0, 1.0)))
    # the aprons: scree, the cliffs' own sandstone broken small, in the
    # cliffs' colours: angular fragments of every bed packed together with
    # dark gaps between them, coarser pieces among the fine, a few grey
    # caprock chips; chutes of finer, paler debris run down the fall line
    # and the Organ Rock's red-brown shale shows through near the top
    cells = voronoi_node(nt, coord, 130.0)
    ctone = coord_xyz(nt, cells.outputs["Color"])["X"]
    frag = ramp(nt, ctone, ((0.00, (0.30, 0.080, 0.030)), (0.30, (0.40, 0.11, 0.038)),
                            (0.55, (0.48, 0.15, 0.050)), (0.75, (0.52, 0.20, 0.080)), (0.88, (0.36, 0.10, 0.035)),
                            (0.95, (0.30, 0.24, 0.17)), (1.00, (0.46, 0.14, 0.045))))
    gaps = voronoi(nt, coord, 130.0, "DISTANCE_TO_EDGE")
    coarse = voronoi_node(nt, coord, 34.0)
    frag = mix_color(nt, frag, ramp(nt, coord_xyz(nt, coarse.outputs["Color"])["Y"],
                                    ((0.0, (0.36, 0.090, 0.032)), (0.5, (0.54, 0.19, 0.060)),
                                     (1.0, (0.52, 0.24, 0.10)))),
                     remap(nt, noise(nt, coord, 9.0, 2.0, 0.5), 0.50, 0.62, 0.0, 0.55))
    frag = mix_color(nt, frag, (0.12, 0.040, 0.022), remap(nt, gaps, 0.08, 0.0, 0.0, 0.40))
    chutes = noise(nt, mapping(nt, coord, scale=(34.0, 34.0, 1.5)), 3.0, 3.0, 0.5)
    frag = mix_color(nt, frag, (0.20, 0.055, 0.025), 0.28)
    apron = mix_color(nt, frag, (0.46, 0.17, 0.065), remap(nt, chutes, 0.56, 0.70, 0.0, 0.45))
    apron = mix_color(nt, apron, (0.16, 0.050, 0.026), remap(nt, chutes, 0.38, 0.28, 0.0, 0.45))
    bands = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", z, math_node(nt, "MULTIPLY", noise(nt, coord, 7.0, 2.0, 0.5), 0.006)), 70.0), 0.0)
    shale = ramp(nt, bands, ((0.0, (0.26, 0.070, 0.034)), (0.45, (0.32, 0.090, 0.040)),
                             (0.60, (0.22, 0.060, 0.030)), (0.85, (0.36, 0.13, 0.060)), (1.0, (0.26, 0.070, 0.034))))
    apron = mix_color(nt, apron, shale, mul(nt, remap(nt, z, FLOOR_Z + APRON_TOP - 0.035, FLOOR_Z + APRON_TOP - 0.005,
                                                       0.0, 0.75),
                                            remap(nt, noise(nt, coord, 12.0, 2.0, 0.5), 0.40, 0.55, 0.3, 1.0)))
    slope = remap(nt, nz, 0.94, 0.82, 0.0, 1.0)
    # only the aprons climb high enough to be scree; the wash's banks and
    # the dunes' lee faces stay sand, the banks a darker red
    rise = remap(nt, z, FLOOR_Z + 0.022, FLOOR_Z + 0.045, 0.0, 1.0)
    col = mix_color(nt, sand, (0.25, 0.080, 0.036), mul(nt, slope, 0.45))
    scree = mul(nt, remap(nt, nz, 0.97, 0.88, 0.0, 1.0), rise)
    col = mix_color(nt, col, apron, scree)
    # sand washed down onto the aprons' toes
    col = mix_color(nt, col, (0.45, 0.16, 0.06), mul(nt, remap(nt, nz, 0.80, 0.94, 0.0, 1.0),
                                                    remap(nt, z, FLOOR_Z + 0.045, FLOOR_Z + 0.015, 0.0, 0.5)))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    bsdf.inputs["Specular IOR Level"].default_value = 0.2
    # relief: wind ripples on the flats; on the scree every fragment a
    # little lump, the coarse pieces bigger ones
    frag_h = math_node(nt, "ADD", mul(nt, remap(nt, gaps, 0.0, 0.25, 0.0, 1.0), 0.5),
                       mul(nt, remap(nt, voronoi(nt, coord, 34.0, "DISTANCE_TO_EDGE"), 0.0, 0.2, 0.0, 1.0), 0.6))
    add_bump(nt, bsdf, math_node(nt, "ADD", mul(nt, ripples, flat, 0.12),
                                 mul(nt, math_node(nt, "ADD", frag_h, mul(nt, fine, 0.4)), scree)), 0.50, 0.004)
    return mat


def sandstone_material():
    mat, nt, bsdf, coord = surface("CliffSandstone")
    # De Chelly sandstone: deep red-orange, massive, faintly laminated and
    # cross-bedded, its bedding planes picked out only where they weather
    # into a seam; black desert varnish hanging down the faces in long
    # curtains; the Moenkopi slope over it chocolate shale.
    xyz = coord_xyz(nt, coord)
    z = xyz["Z"]
    nz = normal_xyz(nt)["Z"]
    tone = noise(nt, coord, 5.0, 4.0, 0.55)
    # the strata: level bands of varied thickness bottom to top, each bed its
    # own colour (maroon at the foot where it grades from the Organ Rock,
    # red-orange, salmon, a pale cream bed, deep red, orange, a bleached
    # top), a dark seam at every parting, a few thin pale laminae; the band
    # edges wander a millimetre or two with the rock
    zw = math_node(nt, "ADD", z, math_node(nt, "MULTIPLY", math_node(
        nt, "SUBTRACT", noise(nt, coord, 7.0, 3.0, 0.55), 0.5), 0.004))
    lo_z, hi_z = FLOOR_Z + APRON_TOP, FLOOR_Z + DECHELLY[-1]
    tz = remap(nt, zw, lo_z, hi_z, 0.0, 1.0)

    def at(h):
        return (h - APRON_TOP) / (DECHELLY[-1] - APRON_TOP)

    b1, b2, b3, b4 = (at(DECHELLY[k]) for k in (1, 2, 3, 4))
    seam = (0.28, 0.068, 0.028)
    strata = ramp(nt, tz, (
        (0.000, (0.30, 0.075, 0.032)), (0.060, (0.36, 0.090, 0.034)), (0.075, (0.46, 0.20, 0.090)),
        (0.090, (0.38, 0.095, 0.034)), (b1 - 0.012, (0.42, 0.110, 0.037)), (b1, seam),
        (b1 + 0.012, (0.54, 0.17, 0.055)), (b1 + 0.09, (0.58, 0.20, 0.065)), (b1 + 0.12, (0.58, 0.25, 0.10)),
        (b1 + 0.15, (0.53, 0.17, 0.055)), (b2 - 0.012, (0.50, 0.15, 0.048)), (b2, seam),
        (b2 + 0.012, (0.60, 0.32, 0.15)), (b2 + 0.08, (0.58, 0.29, 0.13)), (b2 + 0.12, (0.56, 0.22, 0.080)),
        (b3 - 0.012, (0.53, 0.19, 0.065)), (b3, seam), (b3 + 0.012, (0.44, 0.11, 0.036)),
        (b3 + 0.10, (0.48, 0.13, 0.042)), (b3 + 0.13, (0.52, 0.22, 0.10)), (b3 + 0.15, (0.46, 0.12, 0.040)),
        (b4 - 0.012, (0.43, 0.11, 0.036)), (b4, seam), (b4 + 0.012, (0.56, 0.19, 0.060)),
        (0.93, (0.60, 0.23, 0.075)), (0.975, (0.60, 0.30, 0.14)), (1.000, (0.56, 0.27, 0.12))))
    # the rock mottled within each bed, never so much as to blur the bands
    rock = mix_color(nt, strata, (0.30, 0.070, 0.028), remap(nt, tone, 0.50, 0.30, 0.0, 0.35))
    rock = mix_color(nt, rock, (0.60, 0.30, 0.14), remap(nt, tone, 0.58, 0.75, 0.0, 0.15))
    lam = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", zw, 260.0), 0.0)
    rock = mix_color(nt, rock, (0.22, 0.050, 0.020), remap(nt, lam, 0.85, 0.98, 0.0, 0.14))
    # desert varnish: a few thin dark streaks hanging from the rim and the
    # ledges, densest high on the cliff and fading down it
    streak = noise(nt, mapping(nt, coord, scale=(70.0, 70.0, 2.0)), 2.0, 2.0, 0.5)
    patchy = remap(nt, noise(nt, coord, 3.0, 2.0, 0.5), 0.45, 0.60, 0.0, 1.0)
    steep = remap(nt, nz, 0.55, 0.25, 0.0, 1.0)
    hang = remap(nt, z, FLOOR_Z + 0.17, FLOOR_Z + 0.39, 0.0, 1.0)
    var = mul(nt, remap(nt, streak, 0.60, 0.70, 0.0, 0.60), steep, hang, patchy)
    rock = mix_color(nt, rock, (0.075, 0.035, 0.022), var)
    # a pale bleached band at the cliff's foot, where the talus sheds
    rock = mix_color(nt, rock, (0.50, 0.24, 0.12), mul(nt, steep, remap(nt, z, FLOOR_Z + APRON_TOP + 0.02,
                                                                          FLOOR_Z + APRON_TOP, 0.0, 0.30)))
    # the Moenkopi slope: crumbling red-brown shale in thin beds, a few of
    # them grey-green
    mb = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", zw, 75.0), 0.0)
    moen = ramp(nt, mb, ((0.0, (0.22, 0.065, 0.034)), (0.40, (0.28, 0.085, 0.042)),
                         (0.60, (0.25, 0.078, 0.040)), (0.74, (0.30, 0.20, 0.13)), (0.82, (0.30, 0.10, 0.050)),
                         (1.0, (0.22, 0.065, 0.034))))
    moen = mix_color(nt, moen, (0.40, 0.20, 0.10), remap(nt, noise(nt, coord, 40.0, 3.0, 0.6), 0.60, 0.75, 0.0, 0.4))
    col = mix_color(nt, rock, moen, remap(nt, z, FLOOR_Z + DECHELLY[-1] + 0.002, FLOOR_Z + DECHELLY[-1] + 0.006,
                                          0.0, 1.0))
    # red dust on the ledges and the spire's top
    col = mix_color(nt, col, (0.24, 0.060, 0.024), mul(nt, remap(nt, nz, 0.70, 0.92, 0.0, 1.0),
                                                     remap(nt, noise(nt, coord, 30.0, 2.0, 0.5), 0.40, 0.60, 0.5, 0.9)))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, var, 0.0, 1.0, 0.86, 0.60), bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    # relief: the laminae as fine horizontal ribs, the rock's grain over them
    add_bump(nt, bsdf, math_node(nt, "ADD", mul(nt, lam, 0.35),
                                 mul(nt, noise(nt, mapping(nt, coord, scale=(1.0, 1.0, 4.0)), 18.0, 3.0, 0.55), 0.8)),
             0.40, 0.004)
    return mat


def cap_material():
    mat, nt, bsdf, coord = surface("Caprock")
    # Shinarump conglomerate: grey-brown grit packed with pebbles, its face
    # varnished near black, its top weathered red-brown under a skin of
    # blown sand, spotted with black lichen.
    nz = normal_xyz(nt)["Z"]
    z = coord_xyz(nt, coord)["Z"]
    tone = noise(nt, coord, 8.0, 4.0, 0.55)
    # the ledge: a dark grey-brown band of hard grit, thinly bedded, its
    # varnish in short streaks under the lip
    grit = ramp(nt, tone, ((0.30, (0.13, 0.085, 0.055)), (0.55, (0.21, 0.145, 0.095)), (0.80, (0.28, 0.21, 0.14))))
    lam = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", z, math_node(nt, "MULTIPLY", noise(nt, coord, 12.0, 2.0, 0.5), 0.0015)), 330.0), 0.0)
    grit = mix_color(nt, grit, (0.07, 0.048, 0.034), remap(nt, lam, 0.70, 0.95, 0.0, 0.45))
    face = remap(nt, nz, 0.45, 0.20, 0.0, 1.0)
    streak = noise(nt, mapping(nt, coord, scale=(60.0, 60.0, 3.0)), 2.0, 2.0, 0.5)
    grit = mix_color(nt, grit, (0.05, 0.035, 0.025), mul(nt, face, remap(nt, streak, 0.55, 0.68, 0.0, 0.7)))
    top = remap(nt, nz, 0.80, 0.95, 0.0, 1.0)
    # the top: weathered slickrock, pale grey-buff where it lies bare, a
    # skin of red sand blown over most of it in soft-edged drifts, darker
    # pans where rain stands, a fine grit over all of it
    broad = noise(nt, coord, 3.2, 4.0, 0.60)
    bare = remap(nt, broad, 0.46, 0.58, 0.0, 1.0)
    rock = ramp(nt, noise(nt, coord, 14.0, 4.0, 0.6), ((0.30, (0.13, 0.095, 0.065)), (0.50, (0.21, 0.16, 0.11)),
                                                      (0.70, (0.29, 0.23, 0.16))))
    sand = ramp(nt, noise(nt, coord, 7.0, 3.0, 0.55), ((0.35, (0.34, 0.13, 0.055)), (0.55, (0.42, 0.18, 0.080)),
                                                     (0.75, (0.48, 0.25, 0.12))))
    topc = mix_color(nt, sand, rock, bare)
    pans = remap(nt, noise(nt, coord, 11.0, 2.0, 0.5), 0.62, 0.70, 0.0, 0.45)
    topc = mix_color(nt, topc, (0.13, 0.075, 0.045), mul(nt, pans, bare))
    fine = noise(nt, coord, 160.0, 2.0, 0.6)
    topc = mix_color(nt, topc, (0.16, 0.08, 0.045), remap(nt, fine, 0.55, 0.75, 0.0, 0.35))
    grit = mix_color(nt, grit, topc, top)
    nt.links.new(grit, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    # relief: the bare rock standing a little proud of the sand, pitted
    add_bump(nt, bsdf, math_node(nt, "ADD", mul(nt, broad, 1.2),
                                 math_node(nt, "ADD", mul(nt, lam, mul(nt, face, 0.4)), mul(nt, fine, 0.25))),
             0.55, 0.006)
    return mat


def wash_material():
    mat, nt, bsdf, coord = surface("WashSand")
    # the wash's bed: buff-pink sand rippled across the flow, gravel bars
    # mid-channel, a crust of cracked mud in the low spots, darker at its
    # edges where the banks shade it and the last flood left its silt
    lane = attr(nt, "Lane")
    edge = remap(nt, math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", lane, 2.0), 0.0), 1.0, 2.0, 0.0, 1.0)
    tone = noise(nt, coord, 10.0, 3.0, 0.55)
    col = ramp(nt, tone, ((0.3, (0.44, 0.21, 0.10)), (0.6, (0.52, 0.27, 0.14)), (0.85, (0.58, 0.33, 0.18))))
    flow = attr(nt, "Flow")
    rip = math_node(nt, "SINE", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", flow, math_node(nt, "MULTIPLY", noise(nt, coord, 30.0, 2.0, 0.5), 0.004)), 1400.0), 0.0)
    col = mix_color(nt, col, (0.32, 0.14, 0.07), remap(nt, rip, 0.3, 1.0, 0.0, 0.35))
    gravel = voronoi_node(nt, coord, 320.0)
    gt = coord_xyz(nt, gravel.outputs["Color"])["X"]
    bar = mul(nt, remap(nt, noise(nt, coord, 6.0, 2.0, 0.5), 0.52, 0.64, 0.0, 1.0),
              remap(nt, gravel.outputs["Distance"], 0.38, 0.20, 0.0, 1.0))
    col = mix_color(nt, col, ramp(nt, gt, ((0.0, (0.10, 0.06, 0.045)), (0.5, (0.36, 0.31, 0.26)),
                                           (1.0, (0.30, 0.13, 0.06)))), bar)
    cracks = voronoi(nt, coord, 90.0, "DISTANCE_TO_EDGE")
    mud = remap(nt, noise(nt, coord, 4.0, 2.0, 0.5), 0.40, 0.30, 0.0, 1.0)
    col = mix_color(nt, col, (0.30, 0.17, 0.10), mul(nt, mud, 0.7))
    col = mix_color(nt, col, (0.10, 0.05, 0.03), mul(nt, mud, remap(nt, cracks, 0.03, 0.0, 0.0, 1.0)))
    col = mix_color(nt, col, (0.20, 0.08, 0.04), mul(nt, edge, 0.65))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.94
    add_bump(nt, bsdf, math_node(nt, "ADD", mul(nt, rip, 0.3), mul(nt, bar, 1.2)), 0.35, 0.002)
    return mat


def block_material():
    mat, nt, bsdf, coord = surface("FallenBlocks")
    # fallen sandstone: fresh orange on the broken faces, varnished dark on
    # the old ones, a few buff caprock blocks among them
    tone = attr(nt, "Tone")
    nz = normal_xyz(nt)["Z"]
    col = ramp(nt, tone, ((0.0, (0.40, 0.08, 0.025)), (0.40, (0.56, 0.15, 0.045)),
                          (0.75, (0.62, 0.24, 0.09)), (0.86, (0.36, 0.27, 0.17)), (1.0, (0.42, 0.33, 0.22))))
    lam = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", coord_xyz(nt, coord)["Z"], math_node(nt, "MULTIPLY", noise(nt, coord, 12.0, 2.0, 0.5), 0.002)),
        300.0), 0.0)
    col = mix_color(nt, col, (0.26, 0.05, 0.02), remap(nt, lam, 0.75, 0.98, 0.0, 0.30))
    var = remap(nt, noise(nt, coord, 14.0, 3.0, 0.6), 0.48, 0.66, 0.0, 0.85)
    col = mix_color(nt, col, (0.06, 0.03, 0.02), mul(nt, var, remap(nt, nz, 0.2, 0.8, 0.0, 1.0)))
    col = mix_color(nt, col, (0.05, 0.025, 0.015), remap(nt, nz, -0.2, -0.8, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.84
    add_bump(nt, bsdf, math_node(nt, "ADD", mul(nt, lam, 0.4), noise(nt, coord, 40.0, 3.0, 0.6)), 0.4, 0.002)
    return mat


def bark_material():
    mat, nt, bsdf, coord = surface("Bark")
    # juniper's shreddy grey-brown bark, the cottonwoods' furrowed grey
    tone = attr(nt, "Tone")
    col = ramp(nt, tone, ((0.0, (0.10, 0.075, 0.055)), (1.0, (0.22, 0.17, 0.13))))
    ridges = noise(nt, mapping(nt, coord, scale=(60.0, 60.0, 4.0)), 6.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.05, 0.035, 0.025), remap(nt, ridges, 0.4, 0.7, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    add_bump(nt, bsdf, ridges, 0.5, 0.002)
    return mat


def foliage_material():
    mat, nt, bsdf, coord = surface("Foliage")
    # junipers (tone under 0.3) dark blue-green, sage scrub (0.36-0.58)
    # silvery grey-green, rabbitbrush (0.62-0.67) olive-gold, cottonwoods
    # (over 0.7) turning yellow and gold; leafy clumps by Voronoi
    tone = attr(nt, "Tone")
    nz = normal_xyz(nt)["Z"]
    col = ramp(nt, tone, ((0.00, (0.018, 0.040, 0.028)), (0.15, (0.030, 0.058, 0.036)),
                          (0.28, (0.050, 0.075, 0.042)), (0.36, (0.16, 0.17, 0.10)),
                          (0.48, (0.21, 0.22, 0.13)), (0.59, (0.25, 0.24, 0.14)),
                          (0.62, (0.30, 0.27, 0.075)), (0.67, (0.42, 0.33, 0.060)),
                          (0.72, (0.28, 0.34, 0.035)), (0.85, (0.50, 0.42, 0.040)), (1.0, (0.62, 0.36, 0.035))))
    leaves = voronoi(nt, coord, 260.0)
    col = mix_color(nt, col, (0.010, 0.016, 0.010), remap(nt, leaves, 0.25, 0.55, 0.0, 0.55))
    col = mix_color(nt, col, (0.40, 0.42, 0.28), mul(nt, remap(nt, nz, 0.4, 0.9, 0.0, 0.22),
                                                     remap(nt, leaves, 0.25, 0.05, 0.0, 1.0)))
    col = mix_color(nt, col, (0.01, 0.015, 0.01), remap(nt, nz, -0.1, -0.7, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    add_bump(nt, bsdf, leaves, 0.6, 0.003)
    translucent(nt, bsdf, (0.25, 0.22, 0.04), 0.12)
    return mat


def plinth_material():
    mat, nt, bsdf, coord = surface("TilePlinth")
    # the tile's skirt: the valley's rock in section, red beds over darker
    # ones, a band of sand on top
    z = coord_xyz(nt, coord)["Z"]
    nz = normal_xyz(nt)["Z"]
    bands = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", z, math_node(nt, "MULTIPLY", noise(nt, coord, 6.0, 2.0, 0.5), 0.010)), 22.0), 0.0)
    rock = ramp(nt, bands, ((0.0, (0.22, 0.050, 0.022)), (0.40, (0.36, 0.090, 0.035)),
                            (0.55, (0.16, 0.045, 0.024)), (0.80, (0.44, 0.17, 0.07)), (1.0, (0.26, 0.06, 0.025))))
    pebbles = voronoi_node(nt, coord, 70.0)
    rock = mix_color(nt, rock, (0.42, 0.30, 0.20), remap(nt, pebbles.outputs["Distance"], 0.16, 0.08, 0.0, 0.6))
    rock = mix_color(nt, rock, (0.56, 0.20, 0.065), remap(nt, z, FLOOR_Z - 0.035, FLOOR_Z - 0.012, 0.0, 1.0))
    rock = mix_color(nt, rock, (0.06, 0.03, 0.02), remap(nt, z, 0.025, 0.0, 0.0, 0.7))
    col = mix_color(nt, rock, (0.05, 0.035, 0.03), remap(nt, nz, -0.5, -0.9, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    add_bump(nt, bsdf, pebbles.outputs["Distance"], 0.3, 0.003)
    return mat


def piece_materials():
    """Eight slots, in index order: shared by the check and the render."""
    return (ground_material(), sandstone_material(), cap_material(), wash_material(), block_material(),
            bark_material(), foliage_material(), plinth_material())


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

def face_vals(me, name, kind=int):
    vals = [kind(0)] * len(me.polygons)
    me.attributes[name].data.foreach_get("value", vals)
    return vals

def vert_vals(me, name, kind=int):
    vals = [kind(0)] * len(me.vertices)
    me.attributes[name].data.foreach_get("value", vals)
    return vals

class Shell:
    def __init__(self, me, verts, polys, part_of, ident_of):
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        parts = {}
        for p in polys:
            parts[part_of[p.index]] = parts.get(part_of[p.index], 0) + 1
        self.part = max(parts, key=parts.get) if parts else 0
        self.ident = ident_of[polys[0].index] if polys else -1
        remap_ = {vi: n for n, vi in enumerate(verts)}
        self.tree = BVHTree.FromPolygons(
            [tuple(p) for p in pts], [[remap_[v] for v in p.vertices] for p in polys])
        self.polys = polys


def classify(me):
    groups = shells(me)
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    by_shell = [[] for _ in groups]
    for p in me.polygons:
        by_shell[owner[p.vertices[0]]].append(p)
    part = face_vals(me, "Part")
    ident = face_vals(me, "Ident")
    all_ = [Shell(me, g, by_shell[si], part, ident) for si, g in enumerate(groups)]

    def of(*kinds):
        return [s for s in all_ if s.part in kinds]

    forms = sorted(of(P_FORM), key=lambda s: s.ident)
    cls = {"groups": groups, "all": all_, "tile": of(P_TILE), "forms": forms, "wash": of(P_WASH),
           "rocks": of(P_ROCK), "trunks": of(P_TRUNK), "crowns": of(P_CROWN), "scrub": of(P_SCRUB)}
    # the ground anything stands on: the tile and the formations together
    if cls["tile"]:
        polys = [p for s in [cls["tile"][0]] + forms for p in s.polys]
        verts = sorted({v for s in [cls["tile"][0]] + forms for v in s.verts})
        cls["land"] = Shell(me, verts, polys, part, ident)
    return cls


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 12.0)), Vector((0.0, 0.0, -1.0)), 30.0)
    return None if loc is None else loc.z


def seal_audit(me, cls):
    """Every formation's foot (its bottom fan's rim): the shallowest of its
    vertices under the tile straight above it."""
    tile = cls["tile"][0]
    cap = face_vals(me, "Cap")
    out = []
    for s in cls["forms"]:
        vs = {v for p in s.polys if cap[p.index] == 1 for v in p.vertices}
        d = min((ray_down(tile.tree, me.vertices[v].co.x, me.vertices[v].co.y) or -9.0) - me.vertices[v].co.z
                for v in vs)
        out.append(d)
    return out


def strata_audit(me, cls):
    """Per bedding plane, the heights of every formation's rings on it:
    the spread across all of them, which formations carry it, and its mean
    height; both canyon walls (the two mesas) must carry every plane."""
    bed = vert_vals(me, "Bed")
    planes = {}
    for s in cls["forms"]:
        for v in s.verts:
            k = bed[v]
            if k > 0:
                planes.setdefault(k, {}).setdefault(s.ident, []).append(me.vertices[v].co.z)
    worst, worst_k = 0.0, 0
    report = {}
    for k in sorted(planes):
        zs = [z for lst in planes[k].values() for z in lst]
        spread = max(zs) - min(zs)
        if spread > worst:
            worst, worst_k = spread, k
        report[k] = (round(sum(zs) / len(zs) - FLOOR_Z, 4), sorted(i - 10 for i in planes[k]))
    canyon = all(10 in planes.get(k, {}) and 11 in planes.get(k, {}) for k in BOUNDARY_H)
    return worst, worst_k, canyon, report


def cap_audit(me, cls):
    """Each caprock's top (zone 1): its heights' spread and its faces' worst
    tilt off level."""
    zone = face_vals(me, "Zone", float)
    flat, tilt, n = 0.0, 0.0, 0
    for s in cls["forms"]:
        top = [p for p in s.polys if zone[p.index] == 1.0]
        if not top:
            continue
        n += 1
        zs = [me.vertices[v].co.z for p in top for v in p.vertices]
        flat = max(flat, max(zs) - min(zs))
        tilt = max(tilt, max(math.degrees(math.acos(min(1.0, abs(p.normal.z)))) for p in top))
    return flat, tilt, n


def talus_audit(me, cls):
    """Every tile face whose three corners lie in an apron's straight run:
    its slope in degrees."""
    talus = vert_vals(me, "Talus")
    tile = cls["tile"][0]
    angs = sorted(math.degrees(math.acos(min(1.0, abs(p.normal.z)))) for p in tile.polys
                  if all(talus[v] for v in p.vertices))
    if not angs:
        return 0, 0.0, 0.0, 0.0
    return len(angs), angs[0], angs[-1], angs[len(angs) // 2]


def wash_audit(me, cls, T):
    """Along the wash's centre lane, its bed row by row: the largest rise
    from one row to the next, its whole fall, and how far its two ends lie
    from the back and front edges; beside its banks, the ground over its
    side lanes."""
    ring = vert_vals(me, "Ring")
    lane = vert_vals(me, "Lane")
    wash = cls["wash"][0]
    tile = cls["tile"][0]
    centre = sorted((ring[v], me.vertices[v].co.copy()) for v in wash.verts if lane[v] == len(LANES) // 2)
    zs = [co.z for _r, co in centre]
    rise = max(b - a for a, b in zip(zs, zs[1:]))
    drop = zs[0] - zs[-1]
    ends = (HALF - centre[0][1].y, centre[-1][1].y + HALF)
    last = centre[-1][0]
    worst = 9.0
    for v in wash.verts:
        if lane[v] not in (0, len(LANES) - 1) or ring[v] < 3 or ring[v] > last - 3:
            continue
        p = me.vertices[v].co
        g = ray_down(tile.tree, p.x, p.y)
        worst = min(worst, -9.0 if g is None else g - p.z)
    return rise, drop, ends, worst, len(zs)


def sector_bury(pts, ground):
    """Per sector about the plan centroid (every sector that holds a
    vertex), the most-buried vertex under the ground straight above it."""
    cx = sum(p.x for p in pts) / len(pts)
    cy = sum(p.y for p in pts) / len(pts)
    best = [None] * SECTORS
    for p in pts:
        k = min(SECTORS - 1, int((math.atan2(p.y - cy, p.x - cx) % TAU) / TAU * SECTORS))
        g = ground(p.x, p.y)
        d = -9.0 if g is None else g - p.z
        best[k] = d if best[k] is None else max(best[k], d)
    return [b for b in best if b is not None]


def rock_audit(cls):
    """Per block, per sector, its most-buried vertex under the ground; and
    every pair of blocks that overlap."""
    tile = cls["tile"][0]
    rocks = cls["rocks"]
    seals = [min(sector_bury(s.pts, lambda x, y: ray_down(tile.tree, x, y))) for s in rocks]
    pairs = 0
    for i in range(len(rocks)):
        for j in range(i + 1, len(rocks)):
            a, b = rocks[i], rocks[j]
            if (a.lo.x > b.hi.x or b.lo.x > a.hi.x or a.lo.y > b.hi.y or b.lo.y > a.hi.y):
                continue
            if a.tree.overlap(b.tree):
                pairs += 1
    return seals, pairs, len(rocks)


def plant_audit(me, cls):
    """Every trunk's foot (its bottom cap): the shallowest of its corners
    under the ground straight above it; every scrub cushion, per sector, its
    most-buried vertex under the ground."""
    land = cls["land"]
    cap = face_vals(me, "Cap")
    roots = []
    for s in cls["trunks"]:
        vs = {v for p in s.polys if cap[p.index] == 1 for v in p.vertices}
        if not vs:
            roots.append(-9.0)
            continue
        roots.append(min((ray_down(land.tree, me.vertices[v].co.x, me.vertices[v].co.y) or -9.0)
                         - me.vertices[v].co.z for v in vs))
    scrub = [min(sector_bury(s.pts, lambda x, y: ray_down(land.tree, x, y))) for s in cls["scrub"]]
    return roots, scrub


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

def convex_hull_collider(groups, name):
    # Adapted from snippets/convex_hull_collider.py (not a package): one hull
    # per point group, joined into one collider mesh.
    mesh = bpy.data.meshes.new(name)
    out = bmesh.new()
    try:
        for pts in groups:
            bm = bmesh.new()
            try:
                for p in pts:
                    bm.verts.new(p)
                result = bmesh.ops.convex_hull(bm, input=list(bm.verts))
                interior = [g for g in (result.get("geom_interior") or []) if g.is_valid]
                if interior:
                    bmesh.ops.delete(bm, geom=interior, context="VERTS")
                unused = [g for g in (result.get("geom_unused") or []) if g.is_valid]
                if unused:
                    bmesh.ops.delete(bm, geom=unused, context="VERTS")
                vmap = {v: out.verts.new(v.co) for v in bm.verts}
                for f in bm.faces:
                    out.faces.new([vmap[v] for v in f.verts])
            finally:
                bm.free()
        triangulate_ngons(out)
        out.to_mesh(mesh)
        mesh.update()
    finally:
        out.free()
    collider = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(collider)
    return collider


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    # Adapted from snippets/setup_bake_target_image.py — do not replace slots.
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("CanyonNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = GROUND_IDX
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
    T = Terrain(flags)
    plan = plan_scene(Terrain({}))
    low = build_mesh("CanyonMesaLow", T, plan, "low", **flags)
    high = build_mesh("CanyonMesaHigh", T, plan, "high", **flags)
    mats = piece_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    bake_mat = mats[GROUND_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        _co = [0.0] * (len(low.data.vertices) * 3)
        low.data.vertices.foreach_get("co", _co)
        _co[2::3] = [z + LIFT_Z for z in _co[2::3]]
        low.data.vertices.foreach_set("co", _co)
        low.data.update()

    none2 = (None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("mesh did not build", 3),) + none2

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
    if len(cls["tile"]) != 1 or len(cls["forms"]) != len(FORMS) or len(cls["wash"]) != 1:
        return (fail(f"tile/formations/wash not found: {len(cls['tile'])}/{len(cls['forms'])}/"
                     f"{len(cls['wash'])}", 3),) + none2
    seals = seal_audit(low.data, cls)
    s_worst, s_k, s_canyon, s_report = strata_audit(low.data, cls)
    c_flat, c_tilt, n_caps = cap_audit(low.data, cls)
    n_talus, t_min, t_max, t_med = talus_audit(low.data, cls)
    w_rise, w_drop, w_ends, w_bank, w_rows = wash_audit(low.data, cls, T)
    rest, pairs, n_rocks = rock_audit(cls)
    roots, scrub = plant_audit(low.data, cls)

    img, tex = setup_bake_image(low, bake_mat)
    if img is None:
        return (fail("no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "CanyonMesaLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "CanyonMesaLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(build_collider_source(T), "CanyonMesaCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_canyon_mesa_tile_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    n_trunks = len(cls["trunks"])
    n_want_trunks = sum(1 for p in plan["plants"] if p["kind"] != "scrub")
    n_want_scrub = sum(1 for p in plan["plants"] if p["kind"] == "scrub")
    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
          f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}")
    print(f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
          f"overlap={overlap:.6f} nfaces={nfaces}")
    print(f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
          f"outer={OUTER_SIZE} zmin={bb[2]:.4f} lo=({bb[0]:.3f},{bb[1]:.3f}) hi=({bb[3]:.3f},{bb[4]:.3f},{bb[5]:.3f})")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured shells={len(cls['all'])} forms={len(cls['forms'])} blocks={n_rocks} "
          f"trunks={n_trunks} crowns={len(cls['crowns'])} scrub={len(cls['scrub'])}")
    print(f"measured seal={[round(s, 4) for s in seals]}")
    print(f"measured strata worst={s_worst:.6f} at plane {s_k} canyon={s_canyon} planes={s_report}")
    print(f"measured caps n={n_caps} flat={c_flat:.6f} tilt={c_tilt:.4f}deg")
    print(f"measured talus faces={n_talus} min={t_min:.3f} max={t_max:.3f} median={t_med:.3f}deg")
    print(f"measured wash rise={w_rise:.7f} drop={w_drop:.4f} ends={tuple(round(e, 4) for e in w_ends)} "
          f"bank={w_bank:.4f} rows={w_rows} len={T.length:.3f}")
    print(f"measured blocks rest min={min(rest):.4f} max={max(rest):.4f} n={n_rocks} overlaps={pairs}")
    print(f"measured plants roots min={min(roots):.4f} max={max(roots):.4f} n={len(roots)} "
          f"scrub min={min(scrub):.4f} n={len(scrub)}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none2
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none2
    for idx, floor in enumerate(FACE_FLOORS):
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{MAT_LABELS[idx]} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + none2
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
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + none2
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + none2
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf}", 15),) + none2
    if bb[2] > ZMIN_EPS:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none2
    if min(seals) < SEAL_MIN:
        return (fail(f"formations: a foot {min(seals):.4f} m under its apron (min {SEAL_MIN}): "
                     f"{[round(s, 4) for s in seals]}", 17),) + none2
    if s_worst > STRATA_EPS or not s_canyon or len(s_report) != len(BOUNDARY_H):
        return (fail(f"strata: bedding plane {s_k} spread {s_worst:.5f} m across the formations (max "
                     f"{STRATA_EPS}), both canyon walls carry every plane {s_canyon}, planes {len(s_report)}/"
                     f"{len(BOUNDARY_H)}", 18),) + none2
    n_capped = sum(1 for f in FORMS if f[-1] != "spire")
    if n_caps != n_capped or c_flat > CAP_FLAT or c_tilt > CAP_TILT_MAX:
        return (fail(f"caprock: {n_caps}/{n_capped} tops, heights spread {c_flat:.5f} m (max {CAP_FLAT}), "
                     f"tilt {c_tilt:.3f} deg (max {CAP_TILT_MAX})", 19),) + none2
    if n_talus < TALUS_FACES_MIN or t_min < TALUS_BAND[0] or t_max > TALUS_BAND[1]:
        return (fail(f"talus: {n_talus} faces (min {TALUS_FACES_MIN}), slopes {t_min:.2f}..{t_max:.2f} deg "
                     f"(angle of repose {TALUS_BAND})", 20),) + none2
    if (w_rise > DRAIN_EPS or w_drop <= 0.0 or max(w_ends) > EXIT_TOL or min(w_ends) < 0.0
            or w_bank < WASH_ENCLOSE_MIN):
        return (fail(f"wash: rises {w_rise:.6f} m between rows (max {DRAIN_EPS}), falls {w_drop:.4f} m, ends "
                     f"{w_ends[0]:.4f}/{w_ends[1]:.4f} m in from the back and front edges (max {EXIT_TOL}), banks "
                     f"{w_bank:.4f} m over its edges (min {WASH_ENCLOSE_MIN})", 21),) + none2
    n_want = len(plan["blocks"])
    if n_rocks != n_want or min(rest) < PERCH_BAND:
        return (fail(f"blocks: {n_rocks}/{n_want}, worst sector {min(rest):.4f} m under the ground "
                     f"(min {PERCH_BAND})", 22),) + none2
    if pairs:
        return (fail(f"blocks: {pairs} pairs overlap", 23),) + none2
    if (n_trunks != n_want_trunks or len(scrub) != n_want_scrub or min(roots) < ROOT_BAND[0]
            or max(roots) > ROOT_BAND[1] or min(scrub) < PERCH_BAND):
        return (fail(f"plants: {n_trunks}/{n_want_trunks} trunks, feet {min(roots):.4f}..{max(roots):.4f} m under "
                     f"the ground (band {ROOT_BAND}); {len(scrub)}/{n_want_scrub} scrub, worst sector "
                     f"{min(scrub):.4f} m (min {PERCH_BAND})", 24),) + none2
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 26),) + none2
    return 0, low, bake_mat


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
    fb.inputs["Base Color"].default_value = (0.013, 0.014, 0.017, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    floor.location.z = -0.0005
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

    # A low warm key from the left, late in the day, so the cliffs on that
    # side glow and each formation throws its shadow across the floor; a
    # cool fill from the sky's side, a rim, and the warm wedge on the floor.
    light("Key", (-3.9, -1.6, 2.2), 350.0, 0.7, (1.0, 0.88, 0.74), spread=30.0)
    light("Fill", (4.2, -3.2, 1.8), 22.0, 8.0, (0.70, 0.80, 1.0))
    light("Rim", (0.8, 3.2, 2.6), 70.0, 3.0, (0.95, 0.85, 0.75))
    light("Wedge", (-2.3, 2.1, 2.4), 260.0, 1.5, (1.0, 0.68, 0.40),
          target=(-2.5, 2.4, 0.0), spread=38.0)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.20, -0.98, 0.0)).normalized()
    cam.location = centre + view * 4.7 + Vector((0.0, 0.0, 3.05))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, -0.05, -0.20))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the rock.
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    qcode = gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall])
    if qcode:
        return qcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return fail("render produced no file", 14)
    return 0


FLAG_NAMES = ("perch_butte", "tilt_beds", "dome_cap", "steep_talus", "uphill_wash", "perch_rock",
              "pile_rocks", "float_plants")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--perch-butte", action="store_true")
    p.add_argument("--tilt-beds", action="store_true")
    p.add_argument("--dome-cap", action="store_true")
    p.add_argument("--steep-talus", action="store_true")
    p.add_argument("--uphill-wash", action="store_true")
    p.add_argument("--perch-rock", action="store_true")
    p.add_argument("--pile-rocks", action="store_true")
    p.add_argument("--float-plants", action="store_true")
    args = p.parse_args(argv)

    code, low, _mat = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        **{k: getattr(args, k) for k in FLAG_NAMES},
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("canyon-mesa-tile OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
