"""Game-ready hex island map tile — a showcase piece, not an example.

Asserts budget conformance of a procedural strategy-game map tile after
composing shipped pipeline pieces: bmesh construction, UVs, nine
materials, high-to-low normal bake, LOD chain, convex hull colliders,
Unity glTF export.

A flat-topped hexagon 2.60 m corner to corner. A mountain island stands in
the middle of it and the sea fills the hex out to its rim on every side, so
the tile's six edges share one profile and any neighbouring sea tile meets
it. Two peaks, furrowed by radial gullies, carry a forest of conifers on
their upper slopes and bare rock and crags on top. From a tarn in the saddle
between them a river runs down a valley it has cut to a sandy delta in the
front cove, falling the whole way. A hill on the right is terraced into
level fields of rice and grain behind stone risers. Broadleaf trees stand on
the lowland, boulders on the beaches, sea cliffs under the western peak, a
foam line at the waterline round the coast, and the sea darkens from
turquoise shallows to deep water.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--warp-edge`` the tile's rim on the
hexagon and its six edges on one canonical profile, ``--uphill-river`` the
river falling all the way to the sea, ``--tilt-terrace`` the terraces level
with their risers in band, ``--flat-sea`` the sea's level and swell,
``--short-sea`` the water contained, ``--lift-foam`` the foam seated at the
waterline, ``--perch-rock`` the rocks sealed in the ground, ``--pile-rocks``
the rocks apart, ``--float-trees`` the trees rooted.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python hex_island_tile.py --
    blender --background --python hex_island_tile.py -- --skip-decimate
    blender --background --python hex_island_tile.py -- --output island.png
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

SEED = 7411
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))
SQ3 = math.sqrt(3.0)

# --- The tile: a flat-topped hexagon, corners at 0, 60, ... degrees -----------
HEX_R = 1.30              # circumradius, m
HEX_A = HEX_R * SQ3 / 2.0  # apothem
EDGE_DIRS = tuple((math.cos(math.radians(30.0 + 60.0 * k)), math.sin(math.radians(30.0 + 60.0 * k)))
                  for k in range(6))
TILE_N = {"low": 104, "high": 150}   # lattice steps from the centre to a corner
SEA_Z = 0.150             # the sea's declared level
RIM_Z = 0.168             # the rim's flat top, 18 mm over the water
CHAMFER = 0.005           # the rim's outer arris drops this far: the canonical edge height
LIP_W = 0.040             # the rim's flat band
LIP_R = 0.070             # the seabed climbs to the rim over this

# --- The island ---------------------------------------------------------------
ISLAND_C = (-0.04, 0.06)
COAST_R = 0.87
COAST_H = ((2, 0.085, 1.1), (3, 0.075, 0.4), (5, 0.040, 2.0), (7, 0.022, 0.7))
COAST_FREE = 0.16         # the coast stays this far inside the hex's rim
BEACH_H, BEACH_L = 0.036, 0.25
CLIFF_TH, CLIFF_H, CLIFF_L = math.radians(172.0), 0.105, 0.055
SHELF_D, DEEP_D = 0.016, 0.068
# peaks: x, y, height, spread, gullies, phase
PEAKS = ((-0.31, 0.29, 0.36, 0.34, 9, 0.3), (0.31, 0.40, 0.27, 0.27, 7, 1.7),
         (-0.10, 0.44, 0.13, 0.18, 6, 1.0), (0.04, 0.52, 0.12, 0.20, 5, 2.9),
         (-0.47, -0.12, 0.07, 0.22, 6, 0.8))
TERRACE_HILL = (0.37, -0.17, 0.19, 0.44, 0.27, math.radians(-35.0))   # x, y, height, spreads, turn
VALLEY_D, VALLEY_S = 0.17, 0.13
RIDGE = 0.050
FINE = 0.016

# --- The river -----------------------------------------------------------------
RIVER_CTRL = ((0.035, 0.285), (0.02, 0.18), (-0.04, 0.06), (-0.11, -0.08), (-0.09, -0.24),
              (-0.13, -0.40), (-0.17, -0.56), (-0.20, -0.70), (-0.22, -0.84))
RIVER_STEP = 0.004
BANK = (0.006, 0.022)     # the water this far under the valley floor on its line: at the coast, inland
CHANNEL_D = 0.018
RIVER_W = (0.018, 0.046)  # half-width at the tarn, at the coast
MOUTH_FLARE = 0.9
MOUTH_Z = SEA_Z + 0.002   # the river at the estuary's head, 2 mm over the calm sea it runs out onto
RIVER_TAIL = 0.050        # the river runs this far on past the head, out over the sea
TAIL_Z = SEA_Z - 0.003    # sliding under the sea by its end
RIVER_SLAB = 0.012
RIVER_ROW = 0.008
LANES = (-1.25, -0.6, 0.0, 0.6, 1.25)
POOL_R, POOL_D, POOL_SLAB = 0.075, 0.026, 0.010
UPHILL = 0.04             # --uphill-river raises the river mid-course by this

# --- The terraces ----------------------------------------------------------------
TERR_C = (0.37, -0.17)
TERR_R = (0.38, 0.27)
TERR_ROT = math.radians(-35.0)
T0H = 0.030               # the lowest tread this far over the sea
DZ = 0.030                # riser height (real paddy risers 0.8-1.5 m, treads 2-6 m)
TERR_TOP = 6              # the hill's crown levelled at this step: one broad top field
RW = 0.18                 # the riser's share of each step
WALL_HW = 0.012           # a retaining wall's half-thickness, along each riser's contour
WALL_LIP = 0.0025         # its coping this far over the tread it holds up
WALL_FOOT = 0.008         # its foot this far under the tread below
TILT_TERRACE = 0.06       # --tilt-terrace slopes every tread this much

# --- Sea, foam ----------------------------------------------------------------------
SEA_N = 52
SEA_IN = 0.018            # the sea's outer edge this far inside the hex, under the rim
WET_H = 0.010             # sea triangles reach ground this far over the water, under the shore
SHORT_PULL = 0.060        # --short-sea draws the sheet's shoreward rim this far out to sea
SEA_SLAB = 0.020
RIPPLE = ((0.0011, 23.0, 0.35), (0.0008, 37.0, 2.10), (0.0005, 61.0, 4.0))
FOAM_N = 420
FOAM_IN = (0.070, 0.022)  # its land edge this far inside the coast: beach, cliff
FOAM_OUT = (0.014, 0.040)
FOAM_FALL_MAX = 0.040     # its fall to the sea edge never wider: steeper than 6 degrees
FOAM_T = 0.0035
FOAM_EDGE = -0.0015
LIFT_FOAM = 0.020

# --- Scatter --------------------------------------------------------------------------
N_CONIFER = 38
N_BROAD = 20
ROOT_D = 0.012            # a trunk starts this far under the ground
FLOAT_TREES = 0.04
N_CRAG = 9
N_BOULDER = 12
ROCK_GAP = 0.008
REST_SINK = 0.005
SECTORS = 8

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (2.6000, 2.2517, 0.7025)
BASE_TRIS_MIN = 103400
BASE_TRIS_MAX = 104500
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 9
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 360
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# face floors: terrain, fields, sea, foam, river, rock, bark, foliage, plinth
FACE_FLOORS = (51700, 5490, 15500, 2040, 2330, 2200, 690, 5830, 9160)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Edge: rim on the outline, six edges on one canonical profile
EDGE_TOL = 0.0005
WARP_EDGE = (0.015, 0.010)   # --warp-edge pushes one edge's middle out and up by these
# River: falls all the way, meets the sea
DRAIN_EPS = 1e-6
MOUTH_EPS = 0.004
# Terraces
TREAD_TILT_MAX = 0.5      # degrees
TREAD_SPREAD = 0.0015
RISER_BAND = (DZ - 0.0015, DZ + 0.0015)
TERRACES_MIN = 5
# Water
LEVEL_EPS = 0.0015
RIPPLE_BAND = (0.0010, 0.0060)
POOL_FLAT = 0.0005
ENCLOSE_MIN = 0.005
RIVER_ENCLOSE_MIN = 0.003
# Foam
FOAM_BAND = 0.006
FOAM_TUCK = 0.003
# Rocks, trees
PERCH_BAND = 0.003
ROOT_BAND = (0.004, 0.050)
# Hero yaw about Z only (level on the stage).
HERO_YAW_DEG = 0.0
WALL_Y = 4.2

TERRAIN_IDX = 0
FIELDS_IDX = 1
SEA_IDX = 2
FOAM_IDX = 3
RIVER_IDX = 4
ROCK_IDX = 5
BARK_IDX = 6
FOLIAGE_IDX = 7
PLINTH_IDX = 8
MAT_LABELS = ("terrain", "fields", "sea", "foam", "river", "rock", "bark", "foliage", "plinth")

# part tags, one per face, so the audits can name a shell's role
P_TILE, P_SEA, P_POOL, P_RIVER, P_FOAM, P_ROCK, P_TRUNK, P_CROWN, P_WALL = 1, 2, 3, 4, 5, 6, 7, 8, 9


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


# --------------------------------------------------------------------------
# The hexagon
# --------------------------------------------------------------------------

def hex_in(x, y):
    """Distance inside the hexagon's outline (negative outside)."""
    return min(HEX_A - (x * c + y * s) for c, s in EDGE_DIRS)


def hex_ray(ox, oy, th):
    """Distance from (ox, oy) to the outline along bearing ``th``."""
    dx, dy = math.cos(th), math.sin(th)
    best = 9.0
    for c, s in EDGE_DIRS:
        dn = dx * c + dy * s
        if dn > 1e-9:
            best = min(best, (HEX_A - (ox * c + oy * s)) / dn)
    return best


def hex_lattice(n, radius):
    """A triangle lattice filling the hexagon of ``radius``: points, their
    axial index, CCW triangles, and the outline ring in CCW order."""
    s = radius / n
    idx = {}
    pts = []
    for i in range(-n, n + 1):
        for j in range(max(-n, -n - i), min(n, n - i) + 1):
            idx[(i, j)] = len(pts)
            pts.append((i * s + 0.5 * j * s, j * s * SQ3 / 2.0))
    tris = []
    for i in range(-n - 1, n + 1):
        for j in range(-n - 1, n + 1):
            a, b, c, d = idx.get((i, j)), idx.get((i + 1, j)), idx.get((i, j + 1)), idx.get((i + 1, j + 1))
            if a is not None and b is not None and c is not None:
                tris.append((a, b, c))
            if b is not None and c is not None and d is not None:
                tris.append((b, d, c))
    ring = []
    steps = ((-1, 1), (-1, 0), (0, -1), (1, -1), (1, 0), (0, 1))
    i, j = n, 0
    for di, dj in steps:
        for _ in range(n):
            ring.append(idx[(i, j)])
            i += di
            j += dj
    return pts, idx, tris, ring


# --------------------------------------------------------------------------
# The ground as a function of plan position
# --------------------------------------------------------------------------

def coast_raw(th):
    return COAST_R * (1.0 + sum(a * math.sin(k * th + p) for k, a, p in COAST_H))


def coast(th):
    return min(coast_raw(th), hex_ray(ISLAND_C[0], ISLAND_C[1], th) - COAST_FREE)


def cliff_w(th):
    return smoothstep(math.cos(th - CLIFF_TH), math.cos(math.radians(50.0)), math.cos(math.radians(22.0)))


def detail(x, y):
    return (0.55 * math.sin(6.3 * x + 2.1 * y + 0.7) * math.cos(5.1 * y - 1.7 * x + 0.3)
            + 0.30 * math.sin(13.7 * x - 9.1 * y + 1.9)
            + 0.15 * math.sin(27.0 * x + 21.0 * y + 0.5) * math.cos(23.0 * y - 19.0 * x))


def elevation(x, y):
    """The relief over the shore's rise: peaks furrowed by radial gullies,
    the terrace hill, a foothill."""
    e = 0.0
    for px, py, amp, sig, k, ph in PEAKS:
        dx, dy = x - px, y - py
        r = math.hypot(dx, dy)
        g = amp * math.exp(-(r / sig) ** 2)
        if k:
            phi = math.atan2(dy, dx)
            furrow = (0.5 + 0.5 * math.sin(k * phi + 5.0 * r + ph)) ** 3
            g *= 1.0 - 0.20 * smoothstep(r, 0.04, 0.20) * furrow
        e += g
    tx, ty, amp, su, sv, rot = TERRACE_HILL
    u = (x - tx) * math.cos(rot) + (y - ty) * math.sin(rot)
    v = -(x - tx) * math.sin(rot) + (y - ty) * math.cos(rot)
    e += amp * math.exp(-(u / su) ** 2 - (v / sv) ** 2)
    e *= 1.0 + 0.14 * detail(x, y)
    # spurs and ravines on the high ground: ridged bands that wander
    rid = ((1.0 - abs(math.sin(14.0 * x + 5.0 * y + 1.3 * math.sin(7.0 * y - 3.0 * x)))) ** 2
           + 0.6 * (1.0 - abs(math.sin(23.0 * y - 9.0 * x + 0.8 * math.sin(11.0 * x + 2.0)))) ** 2)
    fine = ((1.0 - abs(math.sin(47.0 * x + 13.0 * y + 1.7 * math.sin(31.0 * y - 5.0 * x)))) ** 3
            + 0.7 * (1.0 - abs(math.sin(61.0 * y - 23.0 * x + 1.1 * math.sin(37.0 * x + 1.0)))) ** 3)
    high = smoothstep(e, 0.06, 0.32) * (rid - 0.55) * RIDGE + smoothstep(e, 0.14, 0.34) * (fine - 0.35) * FINE
    # not on the terrace hill, whose fields follow its smooth contours
    return e + high * (1.0 - terrace_mask(x, y))


def terrace_mask(x, y):
    dx, dy = x - TERR_C[0], y - TERR_C[1]
    u = dx * math.cos(TERR_ROT) + dy * math.sin(TERR_ROT)
    v = -dx * math.sin(TERR_ROT) + dy * math.cos(TERR_ROT)
    ell = math.hypot(u / TERR_R[0], v / TERR_R[1])
    return smoothstep(ell, 1.0, 0.72)


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


class Terrain:
    """The tile's ground in closed form: the island's shore and relief, the
    terraces, the valley, the river's channel and the tarn's basin, the
    seabed and the rim. The river's surface is read off the valley floor
    along its line and held falling all the way to the sea."""

    def __init__(self, flags):
        self.flags = flags
        self.path = catmull_open(RIVER_CTRL, RIVER_STEP)
        self.length = self.path[-1][2]
        kd = KDTree(len(self.path))
        for i, (x, y, _s) in enumerate(self.path):
            kd.insert((x, y, 0.0), i)
        kd.balance()
        self.kd = kd
        # the coast crossing, from the shore alone
        self.s_cross = self.length
        for x, y, s in self.path:
            if self.polar(x, y)[2] <= 0.0:
                self.s_cross = s
                break
        # the tarn: its level under the lowest ground round it
        sx, sy, _s = self.path[0]
        self.pool_c = (sx, sy)
        lows = []
        for f in (1.0, 1.15, 1.3):
            for k in range(48):
                th = TAU * k / 48
                lows.append(self.base(sx + f * POOL_R * math.cos(th), sy + f * POOL_R * math.sin(th))[0])
        self.pool_level = min(lows) - 0.010
        # the river's surface: under the valley floor on its line, never rising
        self.s0 = 0.6 * POOL_R
        z = self.pool_level - 0.003
        self.wz = []
        for x, y, s in self.path:
            if s >= self.s0:
                bank = BANK[0] + (BANK[1] - BANK[0]) * smoothstep(self.polar(x, y)[2], 0.02, 0.30)
                z = min(z, self.base(x, y)[0] - bank)
            self.wz.append(z)
        # the estuary's head: where the river has come down to the sea; the
        # sea runs up the channel to here
        self.s_coast = self.s_cross
        for i, (_x, _y, s) in enumerate(self.path):
            if self.wz[i] <= MOUTH_Z:
                self.s_coast = min(s, self.s_cross)
                break
        for i, (_x, _y, s) in enumerate(self.path):
            if s >= self.s_coast:
                self.wz[i] = MOUTH_Z
        self.mouth = self.at(self.s_coast)

    def at(self, s):
        i = min(max(int(round(s / RIVER_STEP)), 0), len(self.path) - 1)
        return self.path[i]

    def surface(self, s):
        i = min(max(int(round(s / RIVER_STEP)), 0), len(self.path) - 1)
        return self.wz[i]

    def width(self, s):
        f = min(max(s / self.s_coast, 0.0), 1.0)
        w = RIVER_W[0] + (RIVER_W[1] - RIVER_W[0]) * f
        w *= 1.0 + 0.18 * math.sin(19.0 * s + 0.6) + 0.10 * math.sin(41.0 * s + 2.0)
        return w * (1.0 + MOUTH_FLARE * smoothstep(s, self.s_coast - 0.16, self.s_coast + 0.02))

    def near(self, x, y):
        _co, i, d = self.kd.find((x, y, 0.0))
        return i, d

    def polar(self, x, y):
        dx, dy = x - ISLAND_C[0], y - ISLAND_C[1]
        th = math.atan2(dy, dx)
        r = math.hypot(dx, dy)
        c = coast(th)
        return th, r, c - r

    def raw(self, x, y):
        """Height over the sea before the terracing, on land only: (hz, mask)
        (None under the sea)."""
        th, _r, dr = self.polar(x, y)
        if dr < 0.0:
            return None, 0.0
        cw = cliff_w(th)
        beach = BEACH_H * (1.0 - math.exp(-dr / BEACH_L))
        cliff = CLIFF_H * smoothstep(dr, 0.0, CLIFF_L) + 0.5 * BEACH_H * smoothstep(dr, CLIFF_L, 0.3)
        hz = beach + (cliff - beach) * cw
        e = elevation(x, y)
        i, d = self.near(x, y)
        s = self.path[i][2]
        valley = VALLEY_D * math.exp(-(d / VALLEY_S) ** 2) * smoothstep(s, -0.08, 0.10)
        m = smoothstep(dr, 0.02, 0.32)
        return hz + max(e - valley, 0.0) * m, terrace_mask(x, y)

    def base(self, x, y):
        """Ground without the channel, the basin or the rim: (z, tread, mask)."""
        th, _r, dr = self.polar(x, y)
        cw = cliff_w(th)
        if dr < 0.0:
            out = -dr
            gentle = SHELF_D * (1.0 - math.exp(-out / 0.12)) + (DEEP_D - SHELF_D) * smoothstep(out, 0.16, 0.45)
            steep = DEEP_D * (1.0 - math.exp(-out / 0.05))
            depth = gentle + (steep - gentle) * cw
            depth += 0.004 * detail(1.7 * x, 1.7 * y) * smoothstep(out, 0.0, 0.10)
            return SEA_Z - depth, 0, 0.0
        hz, mask = self.raw(x, y)
        tread = 0
        if mask > 0.0 and hz > T0H:
            st = min((hz - T0H) / DZ, TERR_TOP + 0.5 * (1.0 - RW))
            k = math.floor(st)
            f = st - k
            # the steps soften to the natural slope through the mask's edge
            rw = RW + (1.0 - mask) * (0.95 - RW)
            ht = T0H + DZ * (k + smoothstep(f, 1.0 - rw, 1.0))
            hz += (ht - hz) * mask
            if mask >= 0.999 and f <= 1.0 - RW - 0.02:
                tread = k + 1
        return SEA_Z + hz, tread, mask

    def ground(self, x, y, rim=True):
        """(z, tread, mask) with the channel, the basin and (unless not
        ``rim``) the rim."""
        z, tread, mask = self.base(x, y)
        i, d = self.near(x, y)
        s = self.path[i][2]
        w = self.width(s)
        ch = self.wz[i] + CHANNEL_D * ((d / w) ** 2 - 1.0)
        if ch < z:
            z, tread = ch, 0
        rho = math.hypot(x - self.pool_c[0], y - self.pool_c[1])
        # a small cirque: the basin's sides steepen past its rim
        basin = self.pool_level + POOL_D * ((rho / POOL_R) ** 2 - 1.0) + 8.0 * max(0.0, rho - 1.3 * POOL_R)
        if basin < z:
            z, tread = basin, 0
        hin = hex_in(x, y)
        lip = smoothstep(hin, LIP_W + LIP_R, LIP_W) if rim else 0.0
        if lip > 0.0:
            z += (RIM_Z - z) * lip
            tread = 0
        return z, tread, mask

    def slope(self, x, y, h=0.006):
        zx = self.ground(x + h, y)[0] - self.ground(x - h, y)[0]
        zy = self.ground(x, y + h)[0] - self.ground(x, y - h)[0]
        return math.hypot(zx, zy) / (2.0 * h)

    def in_corridor(self, x, y, pad=1.1):
        """On the river, upstream of the coast: the sea stays out of it."""
        i, d = self.near(x, y)
        s = self.path[i][2]
        return s < self.s_coast and d < pad * self.width(s)


class Ground:
    """The built tile, sampled by a ray straight down, so everything seated
    on it sits on the faces actually shipped."""

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
    plan = {"ripple": [rng.uniform(0.0, TAU) for _ in range(6)],
            "foam": [rng.uniform(0.0, TAU) for _ in range(8)]}

    taken = []   # (x, y, r): placed trees and rocks

    def clear(x, y, r):
        return all(math.hypot(x - a, y - b) >= r + c + ROCK_GAP for a, b, c in taken)

    def dry(x, y, pad):
        i, d = T.near(x, y)
        s = T.path[i][2]
        if d < T.width(s) + pad:
            return False
        if math.hypot(x - T.pool_c[0], y - T.pool_c[1]) < 1.6 * POOL_R + pad:
            return False
        return terrace_mask(x, y) < 0.02 and hex_in(x, y) > LIP_W + LIP_R + 0.05

    rocks = []
    # crags on the two summits, then boulders on the beaches and the lowland
    for kind, n, tries in (("crag", N_CRAG, 4000), ("boulder", N_BOULDER, 4000)):
        got = 0
        for _ in range(tries):
            if got >= n:
                break
            if kind == "crag":
                px, py, _a, _s, _k, _p = PEAKS[0] if got < 5 else PEAKS[1]
                ang, rad = rng.uniform(0.0, TAU), rng.uniform(0.06, 0.24)
                x, y = px + rad * math.cos(ang), py + rad * math.sin(ang)
                r = rng.uniform(0.030, 0.052)
            else:
                th = rng.uniform(-math.pi, math.pi)
                x = ISLAND_C[0] + (coast(th) - rng.uniform(0.02, 0.24)) * math.cos(th)
                y = ISLAND_C[1] + (coast(th) - rng.uniform(0.02, 0.24)) * math.sin(th)
                r = rng.uniform(0.014, 0.030)
            draws = [rng.uniform(0.0, 1.0) for _ in range(8)]
            if not dry(x, y, r + 0.02) or not clear(x, y, r * 1.5):
                continue
            z = T.ground(x, y)[0]
            if z < SEA_Z + 0.004:
                continue
            if kind == "crag" and (not (SEA_Z + 0.18 < z < SEA_Z + 0.36) or T.slope(x, y) > 0.75):
                continue
            taken.append((x, y, r * 1.5))
            rocks.append({"x": x, "y": y, "r": r, "kind": kind,
                          "long": 1.15 + 0.5 * draws[0], "flat": 0.55 + 0.25 * draws[1],
                          "yaw": TAU * draws[2], "tone": draws[3],
                          "waves": [(Vector((draws[4] - 0.5, draws[5] - 0.5, draws[6] - 0.3)), TAU * draws[7], 1.0),
                                    (Vector((draws[5] - 0.5, draws[7] - 0.5, draws[4] - 0.5)), TAU * draws[6], 0.6)]})
            got += 1
    plan["rocks"] = rocks

    trees = []
    for kind, n, tries in (("conifer", N_CONIFER, 6000), ("broad", N_BROAD, 6000)):
        got = 0
        for _ in range(tries):
            if got >= n:
                break
            x = rng.uniform(-HEX_A, HEX_A)
            y = rng.uniform(-HEX_A, HEX_A)
            size = rng.uniform(0.0, 1.0)
            tone = rng.uniform(0.0, 1.0)
            spin = rng.uniform(0.0, TAU)
            keep = rng.uniform(0.0, 1.0)
            th, _r, dr = T.polar(x, y)
            if dr < 0.08:
                continue
            r = 0.040 + 0.018 * size if kind == "conifer" else 0.050 + 0.016 * size
            if not dry(x, y, r + 0.01) or not clear(x, y, r):
                continue
            z = T.ground(x, y)[0] - SEA_Z
            sl = T.slope(x, y)
            # stands in clumps: a forest field in space
            forest = 0.5 + 0.5 * math.sin(7.0 * x + 3.0 * y + 1.2) * math.cos(5.0 * y - 4.0 * x + 0.4)
            if kind == "conifer":
                if not (0.09 < z < 0.30) or sl > 1.0 or keep > 0.25 + forest:
                    continue
            else:
                if not (0.02 < z < 0.16) or sl > 0.55 or keep > 0.15 + forest:
                    continue
            taken.append((x, y, r))
            trees.append({"x": x, "y": y, "kind": kind, "size": size, "tone": tone, "spin": spin, "r": r})
            got += 1
    plan["trees"] = trees
    return plan


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

class Builder:
    """The bmesh plus its layers: Tone (shading variety), Part (the shell's
    role), Ident (which tree, rock or sheet), Cap (1 on a shell's bottom, 3
    on the tile's skirt), Zone (a water sheet's top), and per vertex Ring (a
    river row), Lane (its place across), Tread (a terrace's level), Field
    (the terrace mask), Depth (water over the bed), FoamX (across the foam),
    Flow (along the river)."""

    def __init__(self, bm):
        self.bm = bm
        self.tone = bm.faces.layers.float.new("Tone")
        self.zone = bm.faces.layers.float.new("Zone")
        self.part = bm.faces.layers.int.new("Part")
        self.ident = bm.faces.layers.int.new("Ident")
        self.cap = bm.faces.layers.int.new("Cap")
        self.ring = bm.verts.layers.int.new("Ring")
        self.lane = bm.verts.layers.int.new("Lane")
        self.tread = bm.verts.layers.int.new("Tread")
        self.field = bm.verts.layers.float.new("Field")
        self.depth = bm.verts.layers.float.new("Depth")
        self.foamx = bm.verts.layers.float.new("FoamX")
        self.flow = bm.verts.layers.float.new("Flow")
        self.uv = bm.loops.layers.uv.new("UVMap")

    def vert(self, co, ring=-1, lane=-1):
        v = self.bm.verts.new(co)
        v[self.ring] = ring
        v[self.lane] = lane
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


def add_tile(B, T, n, flags):
    """The tile: a triangle lattice over the hexagon carrying the island,
    the seabed and the rim, its outline chamfered down to the canonical edge
    height, and a skirt straight down to a flat base at Z = 0."""
    pts, _idx, tris, ring = hex_lattice(n, HEX_R)
    on_ring = set(ring)
    verts = []
    hins = []
    for k, (x, y) in enumerate(pts):
        if k in on_ring:
            z, tread, mask = RIM_Z - CHAMFER, 0, 0.0
        else:
            z, tread, mask = T.ground(x, y)
        v = B.vert((x, y, z))
        v[B.tread] = tread
        v[B.field] = mask
        v[B.depth] = max(0.0, SEA_Z - z)
        verts.append(v)
        hins.append(hex_in(x, y))
    if flags.get("tilt_terrace"):
        # every tread's vertices slope across the hill; the risers and walls stay
        for v in verts:
            if v[B.tread] > 0:
                v.co.z += TILT_TERRACE * (v.co.x - TERR_C[0])
    if flags.get("warp_edge"):
        # the middle of edge 0 (between the 0 and 60 degree corners) pushed out and up
        c, s = EDGE_DIRS[0]
        for k in ring[n // 3: 2 * n // 3]:
            v = verts[k]
            v.co += Vector((WARP_EDGE[0] * c, WARP_EDGE[0] * s, WARP_EDGE[1]))
    for a, b, c in tris:
        va, vb, vc = verts[a], verts[b], verts[c]
        if (min(hins[a], hins[b], hins[c]) < LIP_W + LIP_R + 0.01
                and max(v.co.z for v in (va, vb, vc)) > SEA_Z):
            mat = PLINTH_IDX
        elif min(va[B.field], vb[B.field], vc[B.field]) >= 0.5 and min(v.co.z for v in (va, vb, vc)) > SEA_Z:
            mat = FIELDS_IDX
        else:
            mat = TERRAIN_IDX
        B.face((va, vb, vc), mat, 0.5, P_TILE)
    rim = [verts[k] for k in ring]
    low = [B.vert((v.co.x, v.co.y, 0.0)) for v in rim]
    m = len(rim)
    for j in range(m):
        q = (j + 1) % m
        B.face((rim[q], rim[j], low[j], low[q]), PLINTH_IDX, 0.5, P_TILE, cap=3)
    B.face(list(reversed(low)), PLINTH_IDX, 0.5, P_TILE, cap=1)


def ripple(plan, x, y):
    ph = plan["ripple"]
    out = 0.0
    for k, (amp, freq, ang) in enumerate(RIPPLE):
        out += amp * math.sin(freq * (x * math.cos(ang) + y * math.sin(ang)) + ph[k])
    return out


def slab(B, top, faces, edges_dir, depth_of, mat, part, ident, thick, zone=1.0):
    """Close a top sheet into a slab: walls down along its boundary and a
    flat underside. ``faces`` are index triples into ``top`` (CCW from
    above); the boundary is the edges used once."""
    use = {}
    for f in faces:
        for k in range(3):
            a, b = f[k], f[(k + 1) % 3]
            key = (min(a, b), max(a, b))
            use[key] = use.get(key, 0) + 1
    lows = {}

    def low(i):
        if i not in lows:
            v = top[i]
            w = B.vert((v.co.x, v.co.y, edges_dir(v)), ring=v[B.ring], lane=-1)
            w[B.depth] = depth_of(v)
            lows[i] = w
        return lows[i]

    for f in faces:
        B.face(tuple(top[i] for i in f), mat, 0.5, part, ident, zone=zone)
        B.face(tuple(low(i) for i in reversed(f)), mat, 0.5, part, ident, cap=1)
        for k in range(3):
            a, b = f[k], f[(k + 1) % 3]
            if use[(min(a, b), max(a, b))] == 1:
                B.face((top[b], top[a], low(a), low(b)), mat, 0.5, part, ident)
    del thick


def add_sea(B, T, plan, flags):
    """The sea: a lattice sheet over every triangle that holds water, from
    the shore (its rim run under the ground) out to the hex's rim (under the
    rim's flat), never up the river."""
    pts, idx, tris, _ring = hex_lattice(SEA_N, HEX_R - SEA_IN * 2.0 / SQ3)
    gz = [T.ground(x, y)[0] for x, y in pts]
    wet = [gz[k] < SEA_Z + WET_H and not T.in_corridor(*pts[k]) for k in range(len(pts))]
    region = {t for t in tris if any(wet[i] for i in t)}
    region = {t for t in region if not any(T.in_corridor(*pts[i], pad=0.6) for i in t)}
    # a vertex the region touches in two fans would pinch the slab's walls:
    # fill round it until every boundary vertex has one fan
    by_vert = {}
    for t in tris:
        for i in t:
            by_vert.setdefault(i, []).append(t)
    for _ in range(12):
        bcount = {}
        use = {}
        for t in region:
            for k in range(3):
                a, b = t[k], t[(k + 1) % 3]
                key = (min(a, b), max(a, b))
                use[key] = use.get(key, 0) + 1
        for (a, b), c in use.items():
            if c == 1:
                bcount[a] = bcount.get(a, 0) + 1
                bcount[b] = bcount.get(b, 0) + 1
        pinch = [i for i, c in bcount.items() if c > 2]
        if not pinch:
            break
        for i in pinch:
            region.update(by_vert[i])
    del idx
    # one sheet: a low hollow cut off from the sea by the corridor stays dry
    nbr = {}
    for t in region:
        for k in range(3):
            a, b = t[k], t[(k + 1) % 3]
            key = (min(a, b), max(a, b))
            nbr.setdefault(key, []).append(t)
    comp = {}
    for t0 in sorted(region):
        if t0 in comp:
            continue
        comp[t0] = t0
        stack = [t0]
        while stack:
            t = stack.pop()
            for k in range(3):
                a, b = t[k], t[(k + 1) % 3]
                for u in nbr[(min(a, b), max(a, b))]:
                    if u not in comp:
                        comp[u] = t0
                        stack.append(u)
    sizes = {}
    for t, c in comp.items():
        sizes[c] = sizes.get(c, 0) + 1
    main = max(sizes, key=sizes.get)
    region = {t for t in region if comp[t] == main}
    flat = flags.get("flat_sea", False)
    shore = set()
    if flags.get("short_sea"):
        use = {}
        for t in region:
            for k in range(3):
                a, b = t[k], t[(k + 1) % 3]
                key = (min(a, b), max(a, b))
                use[key] = use.get(key, 0) + 1
        shore = {i for key, c in use.items() if c == 1 for i in key if hex_in(*pts[i]) > SEA_IN + 0.03}
    mx, my = T.mouth[0], T.mouth[1]
    top = {}
    for t in region:
        for i in t:
            if i not in top:
                x, y = pts[i]
                if i in shore:
                    # out from the island's centre, off the shore it ran under
                    dx, dy = x - ISLAND_C[0], y - ISLAND_C[1]
                    ln = math.hypot(dx, dy) or 1.0
                    x, y = x + dx / ln * SHORT_PULL, y + dy / ln * SHORT_PULL
                calm = smoothstep(math.hypot(x - mx, y - my), 0.06, 0.24)
                z = SEA_Z if flat else SEA_Z + ripple(plan, x, y) * calm
                v = B.vert((x, y, z))
                # the water's colour reads the open seabed, not the rim's climb
                v[B.depth] = max(0.0, SEA_Z - T.ground(x, y, rim=False)[0])
                top[i] = v
    keys = sorted(top)
    remap = {k: n for n, k in enumerate(keys)}
    tv = [top[k] for k in keys]
    faces = [tuple(remap[i] for i in t) for t in sorted(region)]
    slab(B, tv, faces, lambda v: SEA_Z - SEA_SLAB, lambda v: v[B.depth], SEA_IDX, P_SEA, 1, SEA_SLAB)


def add_pool(B, T):
    """The tarn: a flat disc over its basin, its rim under the ground."""
    cx, cy = T.pool_c
    K, M = 5, 28
    rr = 1.15 * POOL_R
    tv = [B.vert((cx, cy, T.pool_level))]
    for k in range(1, K + 1):
        for j in range(M):
            th = TAU * j / M
            tv.append(B.vert((cx + rr * k / K * math.cos(th), cy + rr * k / K * math.sin(th), T.pool_level)))
    for v in tv:
        v[B.depth] = max(0.0, T.pool_level - T.ground(v.co.x, v.co.y)[0])
    faces = []
    for j in range(M):
        faces.append((0, 1 + j, 1 + (j + 1) % M))
    for k in range(1, K):
        for j in range(M):
            a = 1 + (k - 1) * M + j
            b = 1 + (k - 1) * M + (j + 1) % M
            c = 1 + k * M + j
            d = 1 + k * M + (j + 1) % M
            faces.append((a, c, d))
            faces.append((a, d, b))
    slab(B, tv, faces, lambda v: T.pool_level - POOL_SLAB, lambda v: v[B.depth], RIVER_IDX, P_POOL, 2, POOL_SLAB)


def river_z(T, s, flags):
    z = T.surface(s)
    if s > T.s_coast:
        z = MOUTH_Z + (TAIL_Z - MOUTH_Z) * min(1.0, (s - T.s_coast) / RIVER_TAIL)
    if flags.get("uphill_river"):
        z += UPHILL * math.exp(-((s - 0.5 * T.s_coast) / 0.08) ** 2)
    return z


def add_river(B, T, flags):
    """The river: a ribbon from inside the tarn to just past the coast, its
    surface flat across and falling along, its edges run under the banks.
    Section: five lanes on top, two corners under."""
    s = T.s0
    rows = []
    end = T.s_coast + RIVER_TAIL
    while s <= end + 1e-9:
        rows.append(s)
        s += RIVER_ROW
    sec = []
    for r, s in enumerate(rows):
        i = min(int(round(s / RIVER_STEP)), len(T.path) - 2)
        x, y, _s = T.path[i]
        nx_, ny_, _ = T.path[i + 1]
        tx, ty = nx_ - x, ny_ - y
        ln = math.hypot(tx, ty) or 1.0
        lx, ly = -ty / ln, tx / ln
        w = T.width(s)
        z = river_z(T, s, flags)
        ring = []
        for li, f in enumerate(LANES):
            v = B.vert((x + lx * f * w, y + ly * f * w, z), ring=r, lane=li)
            v[B.flow] = s / end
            v[B.depth] = max(0.0, z - T.ground(v.co.x, v.co.y)[0])
            ring.append(v)
        for f in (LANES[-1], LANES[0]):
            v = B.vert((x + lx * f * w, y + ly * f * w, z - RIVER_SLAB), ring=r, lane=-1)
            v[B.flow] = s / end
            ring.append(v)
        sec.append(ring)
    L = len(LANES)
    m = len(sec[0])
    for a, b in zip(sec, sec[1:]):
        for k in range(m):
            q = (k + 1) % m
            zone = 1.0 if k < L - 1 else 0.0
            B.quad(a[k], b[k], b[q], a[q], RIVER_IDX, 0.5, P_RIVER, 3, zone=zone)
    # the end caps: the top lanes lie in a line, so fan from a bottom corner
    for ring, cap, flip in ((sec[0], 1, False), (sec[-1], 2, True)):
        fan = [(ring[m - 1], ring[k], ring[k + 1]) for k in range(m - 2)]
        for tri in fan:
            B.face(tuple(reversed(tri)) if flip else tri, RIVER_IDX, 0.5, P_RIVER, 3, cap=cap)


def terrace_contours(T, n=180, step=0.002, reach=0.5):
    """Each riser's middle, traced ray by ray out from the terrace hill's
    centre on the unterraced ground: (level, [(x, y) or None per ray])."""
    cx, cy = TERR_C
    rays = []
    for j in range(n):
        th = TAU * j / n
        c, s = math.cos(th), math.sin(th)
        col = []
        r = 0.0
        while r < reach:
            x, y = cx + r * c, cy + r * s
            hz, _mask = T.raw(x, y)
            col.append((x, y, None if hz is None else (hz - T0H) / DZ))
            r += step
        rays.append(col)
    top = max(st for col in rays for _x, _y, st in col if st is not None)
    out = []
    for k in range(min(int(math.floor(top)), TERR_TOP)):
        target = k + 1 - 0.5 * RW
        pts = []
        for col in rays:
            hit = None
            for (x0, y0, s0), (x1, y1, s1) in zip(col, col[1:]):
                if s0 is None or s1 is None:
                    break
                if s0 >= target > s1:
                    f = (s0 - target) / (s0 - s1)
                    hx, hy = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
                    if terrace_mask(hx, hy) >= 0.97:
                        hit = (hx, hy)
                    break
            pts.append(hit)
        out.append((k, pts))
    return out


def add_walls(B, T):
    """Dry-stone retaining walls along every riser where the terraces are
    whole: a coping just over the tread each holds up, a foot under the
    tread below, so the riser's band lies inside the wall."""
    cx, cy = TERR_C
    for k, pts in terrace_contours(T):
        n = len(pts)
        # a ray the tracer missed between two hits: bridge it
        for i in range(n):
            a, b = pts[i - 1], pts[(i + 1) % n]
            if pts[i] is None and a is not None and b is not None:
                pts[i] = (0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]))
        if all(p is not None for p in pts):
            runs = [(list(range(n)), True)]
        elif all(p is None for p in pts):
            runs = []
        else:
            start = next(i for i in range(n) if pts[i] is None)
            runs, cur = [], []
            for m in range(1, n + 1):
                i = (start + m) % n
                if pts[i] is None:
                    if len(cur) >= 5:
                        runs.append((cur, False))
                    cur = []
                else:
                    cur.append(i)
            if len(cur) >= 5:
                runs.append((cur, False))
        zt = SEA_Z + T0H + DZ * (k + 1) + WALL_LIP
        zb = SEA_Z + T0H + DZ * k - WALL_FOOT
        for run, (idxs, closed) in enumerate(runs):
            rows = []
            for i in idxs:
                x, y = pts[i]
                ux, uy = x - cx, y - cy
                ln = math.hypot(ux, uy) or 1.0
                ux, uy = ux / ln, uy / ln
                # each stretch a little proud or sunk along the wall
                hw = WALL_HW * (1.0 + 0.12 * math.sin(37.0 * TAU * i / n + k))
                ztop = zt + 0.0003 * run
                row = [B.vert((x - ux * hw, y - uy * hw, ztop)), B.vert((x + ux * hw, y + uy * hw, ztop)),
                       B.vert((x + ux * hw, y + uy * hw, zb)), B.vert((x - ux * hw, y - uy * hw, zb))]
                for v in row:
                    v[B.field] = -1.0
                    v[B.tread] = -1
                rows.append(row)
            m = len(rows)
            for a in range(m if closed else m - 1):
                r0, r1 = rows[a], rows[(a + 1) % m]
                for j in range(4):
                    q = (j + 1) % 4
                    B.face((r0[j], r0[q], r1[q], r1[j]), FIELDS_IDX, 0.5, P_WALL, 50 + k)
            if not closed:
                B.face(tuple(reversed(rows[0])), FIELDS_IDX, 0.5, P_WALL, 50 + k, cap=1)
                B.face(tuple(rows[-1]), FIELDS_IDX, 0.5, P_WALL, 50 + k, cap=2)


def foam_band(B, rows, closed, loop):
    n = len(rows)
    m = len(rows[0])
    for i in range(n if closed else n - 1):
        a, b = rows[i], rows[(i + 1) % n]
        for j in range(m):
            k = (j + 1) % m
            B.face((a[j], a[k], b[k], b[j]), FOAM_IDX, 0.5, P_FOAM, loop)
    if not closed:
        B.face(tuple(reversed(rows[0])), FOAM_IDX, 0.5, P_FOAM, loop)
        B.face(tuple(rows[-1]), FOAM_IDX, 0.5, P_FOAM, loop)


def foam_row(B, li, wl, so, s, ph, loop, lift, inner=0.0):
    """Across the foam: its land edge under the shore, a crest at the
    waterline, and a fall to its sea edge under the calm water. The fall is
    steeper than any ripple and the crest over every ripple's top, so no
    face of the foam can lie in the sea's plane."""
    zt = SEA_Z + FOAM_T + 0.0008 * math.sin(TAU * 17.0 * s + ph[4 + loop % 3]) + lift
    zb = SEA_Z - FOAM_T + lift
    zo = SEA_Z + FOAM_EDGE + lift
    row = [B.vert((li[0], li[1], zt)), B.vert((wl[0], wl[1], zt)), B.vert((so[0], so[1], zo)),
           B.vert((so[0], so[1], zb)), B.vert((li[0], li[1], zb))]
    # FoamX: 0 at the waterline, 1 at its sea edge, ``inner`` at its land edge
    for v, fx in zip(row, (inner, 0.0, 1.0, 1.0, inner)):
        v[B.foamx] = fx
    return row


def foam_width(s, ph, loop):
    return FOAM_OUT[0] + (FOAM_OUT[1] - FOAM_OUT[0]) * (
        0.5 + 0.30 * math.sin(TAU * 5.0 * s + ph[loop % 3]) + 0.20 * math.sin(TAU * 13.0 * s + ph[3 + loop % 3]))


def add_foam(B, T, plan, flags):
    """A foam line at the waterline round the coast, from one bank of the
    river's mouth round to the other, its land edge tucked under the shore."""
    lift = LIFT_FOAM if flags.get("lift_foam") else 0.0
    ph = plan["foam"]
    cross = T.at(T.s_cross)
    mth = math.atan2(cross[1] - ISLAND_C[1], cross[0] - ISLAND_C[0])
    gap = (T.width(T.s_cross) + 0.09) / coast(mth)
    rows = []
    for i in range(FOAM_N):
        s = i / (FOAM_N - 1)
        th = mth + gap + (TAU - 2.0 * gap) * s
        c = coast(th)
        cw = cliff_w(th)
        # the shore's normal from the coast's own slope in plan
        h = 1e-3
        dc = (coast(th + h) - coast(th - h)) / (2.0 * h)
        rx, ry = math.cos(th), math.sin(th)
        tx, ty = -math.sin(th) * c + rx * dc, math.cos(th) * c + ry * dc
        ln = math.hypot(tx, ty)
        nx, ny = ty / ln, -tx / ln
        px, py = ISLAND_C[0] + c * rx, ISLAND_C[1] + c * ry
        fin = FOAM_IN[0] + (FOAM_IN[1] - FOAM_IN[0]) * cw
        # it frays out to nothing toward the river's mouth
        w = foam_width(s, ph, 0) * (0.15 + 0.85 * smoothstep(s, 0.0, 0.05) * smoothstep(s, 1.0, 0.95))
        w = min(w, FOAM_FALL_MAX)
        rows.append(foam_row(B, (px - nx * fin, py - ny * fin), (px, py), (px + nx * w, py + ny * w), s, ph, 0,
                             lift, -fin / w))
    foam_band(B, rows, False, 1)


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


CUT_DIRS = tuple(Vector(d).normalized() for d in ((0.7, 0.2, 0.68), (-0.5, 0.6, 0.62), (0.1, -0.9, 0.4),
                                                    (-0.8, -0.3, 0.5), (0.4, 0.7, -0.2)))


def add_rocks(B, plan, G, flags):
    perch = flags.get("perch_rock", False)
    items = [dict(it) for it in plan["rocks"]]
    if flags.get("pile_rocks"):
        cx = sum(it["x"] for it in items[:3]) / 3.0
        cy = sum(it["y"] for it in items[:3]) / 3.0
        for it in items[:3]:
            it["x"] = cx + 0.25 * (it["x"] - cx)
            it["y"] = cy + 0.25 * (it["y"] - cy)
    for n, it in enumerate(items):
        dirs, quads = cube_sphere(3)
        r = it["r"]
        ax = Vector((r * it["long"], r, r * it["flat"]))
        if it["kind"] == "crag":
            ax = Vector((r * it["long"] * 1.2, r * 0.75, r * (it["flat"] + 0.35)))
        yaw = Matrix.Rotation(it["yaw"], 3, "Z")
        pts = []
        for d in dirs:
            q = Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z))
            q *= 1.0 + 0.12 * sum(a * math.sin(w.normalized().dot(d) * 3.0 + ph) for w, ph, a in it["waves"])
            # fractured faces: flattened where a plane cuts it
            for k, cdir in enumerate(CUT_DIRS[:5 if it["kind"] == "crag" else 2]):
                lim = (0.62 + 0.18 * hash01(n, k, 3)) * (ax.x * abs(cdir.x) + ax.y * abs(cdir.y) + ax.z * abs(cdir.z))
                proj = q.dot(cdir)
                if proj > lim:
                    q -= cdir * (proj - lim)
            pts.append(yaw @ q + Vector((it["x"], it["y"], 0.0)))
        if perch:
            dz = seat(pts, G, REST_SINK, True)
        else:
            sink = 0.50 if it["kind"] == "crag" else 0.35
            dz = min(seat(pts, G, REST_SINK, False), G.z(it["x"], it["y"]) - min(p.z for p in pts)
                     - sink * 2.0 * ax.z)
        verts = [B.vert(p + Vector((0.0, 0.0, dz))) for p in pts]
        for q in quads:
            B.quad(*[verts[i] for i in q], ROCK_IDX, 0.15 + 0.7 * it["tone"], P_ROCK, 100 + n)


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


def cone_tier(B, base, rb, h, spin, tone, ident, jag):
    """One tier of a conifer's crown: a drooping skirt of jagged boughs to a
    point, closed underneath."""
    M = 9
    rim, mid = [], []
    for k in range(M):
        th = spin + TAU * k / M
        rr = rb * (1.0 + jag * (0.5 if k % 2 else -0.4) + 0.08 * math.sin(3.0 * th + tone * 9.0))
        rim.append(B.vert(base + Vector((rr * math.cos(th), rr * math.sin(th), -0.10 * h))))
        th2 = th + math.pi / M
        mid.append(B.vert(base + Vector((0.55 * rb * math.cos(th2), 0.55 * rb * math.sin(th2), 0.42 * h))))
    apex = B.vert(base + Vector((0.0, 0.0, h)))
    for k in range(M):
        q = (k + 1) % M
        B.face((rim[k], rim[q], mid[k]), FOLIAGE_IDX, tone, P_CROWN, ident)
        B.face((rim[q], mid[q], mid[k]), FOLIAGE_IDX, tone, P_CROWN, ident)
        B.face((mid[k], mid[q], apex), FOLIAGE_IDX, tone, P_CROWN, ident)
    B.face(tuple(reversed(rim)), FOLIAGE_IDX, tone, P_CROWN, ident, cap=1)


def lump_ball(B, centre, ax, spin, tn, ident, n=2):
    dirs, quads = cube_sphere(n)
    hv = []
    for d in dirs:
        lump = 1.0 + 0.12 * math.sin(9.0 * d.x + 5.0 * d.y + 7.0 * tn) * math.cos(8.0 * d.z + 2.0 * tn)
        q = spin @ Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z)) * lump
        hv.append(B.vert(centre + q))
    for q in quads:
        B.quad(*[hv[i] for i in q], FOLIAGE_IDX, tn, P_CROWN, ident)


def add_trees(B, plan, G, flags):
    lift = FLOAT_TREES if flags.get("float_trees") else 0.0
    for n, t in enumerate(plan["trees"]):
        x, y = t["x"], t["y"]
        ident = 200 + n
        # the trunk's foot under the lowest ground round it
        g = min(G.z(x + 0.008 * math.cos(a), y + 0.008 * math.sin(a)) for a in (0.0, 2.1, 4.2)) + 0.0
        g = min(g, G.z(x, y))
        foot = Vector((x, y, g - ROOT_D + lift))
        if t["kind"] == "conifer":
            h = 0.13 + 0.07 * t["size"]
            trunk_r = 0.0055 + 0.002 * t["size"]
            top = foot + Vector((0.0, 0.0, ROOT_D + 0.30 * h))
            tube(B, (foot, top), (trunk_r, trunk_r * 0.8), 6, BARK_IDX, t["tone"], P_TRUNK, ident)
            tone = 0.05 + 0.40 * t["tone"]
            rb = 0.040 + 0.018 * t["size"]
            z0 = ROOT_D + 0.16 * h
            for k in range(3):
                tier_base = foot + Vector((0.0, 0.0, z0 + k * 0.26 * h))
                cone_tier(B, tier_base, rb * (1.0 - 0.24 * k), h * (0.42 - 0.04 * k), t["spin"] + 0.7 * k,
                          tone, ident, 0.22)
        else:
            h = 0.05 + 0.025 * t["size"]
            trunk_r = 0.0065 + 0.002 * t["size"]
            top = foot + Vector((0.0, 0.0, ROOT_D + h))
            tube(B, (foot, foot + Vector((0.0, 0.0, ROOT_D + 0.5 * h)), top),
                 (trunk_r, trunk_r * 0.85, trunk_r * 0.6), 6, BARK_IDX, t["tone"], P_TRUNK, ident)
            tone = 0.55 + 0.45 * t["tone"]
            rc = 0.038 + 0.014 * t["size"]
            spin = Matrix.Rotation(t["spin"], 3, "Z")
            for k, (ox, oy, oz, f) in enumerate(((0.0, 0.0, 0.9, 1.0), (0.55, 0.15, 0.55, 0.78),
                                                  (-0.35, 0.45, 0.6, 0.72), (-0.2, -0.5, 0.5, 0.70))):
                c = top + spin @ Vector((ox * rc, oy * rc, oz * rc))
                lump_ball(B, c, Vector((rc * f, rc * f * 0.95, rc * f * 0.82)),
                          Matrix.Rotation(t["spin"] + k, 3, "Z"), tone, ident)


def break_coplanar(B, parts, passes=8):
    """Bough tiers, lumps and rocks are many small faces in every direction;
    now and then one lands in another shell's plane. Turn the shell's piece
    a few degrees about the vertical through its lowest point until none
    does."""
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
                bad.add(key[i])
        if not bad:
            return
        for k in sorted(bad):
            vs = {v for f, kk in zip(faces, key) if kk == k for v in f.verts}
            root = min(vs, key=lambda v: v.co.z).co.copy()
            R = Matrix.Rotation(math.radians(3.0), 3, "Z")
            for v in vs:
                v.co = root + R @ (v.co - root)


def build_mesh(name, T, plan, detail_="low", **flags):
    bm = bmesh.new()
    try:
        B = Builder(bm)
        add_tile(B, T, TILE_N[detail_], flags)
        bm.normal_update()
        G = Ground(BVHTree.FromBMesh(bm))
        add_sea(B, T, plan, flags)
        add_pool(B, T)
        add_walls(B, T)
        add_river(B, T, flags)
        add_foam(B, T, plan, flags)
        add_rocks(B, plan, G, flags)
        add_trees(B, plan, G, flags)
        triangulate_ngons(bm)
        break_coplanar(B, (P_ROCK, P_TRUNK, P_CROWN))
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        # Everything smooth-shaded, with every material boundary and every
        # fold sharper than its crease a hard edge.
        crease = {TERRAIN_IDX: 55.0, FIELDS_IDX: 32.0, ROCK_IDX: 40.0, FOLIAGE_IDX: 70.0,
                  PLINTH_IDX: 30.0, BARK_IDX: 70.0}
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
    """Point groups for one convex hull each: the plinth up to the water,
    and the island in six sectors round its centre, each from the shore to
    the ground over it. Ships sail the sea; units walk the land."""
    pts, _i, _t, ring = hex_lattice(6, HEX_R)
    groups = [[Vector((pts[k][0], pts[k][1], z)) for k in ring for z in (0.0, SEA_Z)]]
    sectors = [[] for _ in range(6)]
    for k in range(6 * 9):
        # nine rays per sector, its two edges shared with its neighbours
        th = TAU * (k // 9 + (k % 9) / 8.0) / 6.0
        c = coast(th)
        for f in (1.0, 0.7, 0.4):
            x = ISLAND_C[0] + f * c * math.cos(th)
            y = ISLAND_C[1] + f * c * math.sin(th)
            z = T.ground(x, y)[0]
            sec = sectors[k // 9]
            sec.append(Vector((x, y, SEA_Z)))
            sec.append(Vector((x, y, max(z, SEA_Z + 0.002))))
    sectors_c = [Vector((ISLAND_C[0], ISLAND_C[1], SEA_Z)),
                 Vector((ISLAND_C[0], ISLAND_C[1], T.ground(*ISLAND_C)[0]))]
    for sec in sectors:
        groups.append(sec + sectors_c)
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


def terrain_material():
    mat, nt, bsdf, coord = surface("IslandGround")
    # The island's skin by height and slope: wet and dry sand at the shore,
    # lush meadow over the lowland in patches, darker forest floor and olive
    # upland higher, then bare grey rock on the steep faces and the summits
    # with a little old snow lying in the hollows of the highest.
    xyz = coord_xyz(nt, coord)
    z = xyz["Z"]
    nz = normal_xyz(nt)["Z"]
    patch = noise(nt, coord, 5.0, 4.0, 0.55)
    fine = noise(nt, coord, 60.0, 3.0, 0.6)
    meadow = ramp(nt, patch, ((0.30, (0.105, 0.245, 0.030)), (0.50, (0.160, 0.330, 0.045)),
                              (0.68, (0.235, 0.380, 0.060)), (0.80, (0.30, 0.37, 0.09))))
    upland = ramp(nt, patch, ((0.30, (0.075, 0.150, 0.035)), (0.55, (0.115, 0.180, 0.045)),
                              (0.80, (0.20, 0.21, 0.08))))
    col = mix_color(nt, meadow, upland, remap(nt, z, SEA_Z + 0.12, SEA_Z + 0.30, 0.0, 1.0))
    col = mix_color(nt, col, (0.05, 0.10, 0.025), remap(nt, fine, 0.35, 0.65, 0.35, 0.0))
    # wildflower speckle in the meadow
    flowers = voronoi(nt, coord, 90.0)
    fl = mul(nt, remap(nt, flowers, 0.10, 0.03, 0.0, 1.0), remap(nt, noise(nt, coord, 3.0, 2.0, 0.5), 0.55, 0.65, 0.0, 1.0),
             remap(nt, z, SEA_Z + 0.16, SEA_Z + 0.08, 0.0, 1.0))
    col = mix_color(nt, col, (0.70, 0.62, 0.18), mul(nt, fl, 0.7))
    # rock on the steep faces and the summits
    strata = math_node(nt, "SINE", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", z, math_node(nt, "MULTIPLY", noise(nt, coord, 4.0, 2.0, 0.5), 0.045)), 95.0), 0.0)
    rock = ramp(nt, noise(nt, coord, 9.0, 5.0, 0.6), ((0.25, (0.17, 0.155, 0.14)), (0.55, (0.29, 0.27, 0.245)),
                                                         (0.80, (0.40, 0.38, 0.34))))
    rock = mix_color(nt, rock, (0.11, 0.10, 0.09), remap(nt, strata, 0.6, 1.0, 0.0, 0.18))
    blocks = voronoi_node(nt, mapping(nt, coord, scale=(1.0, 1.0, 0.45)), 9.0)
    btone = coord_xyz(nt, blocks.outputs["Color"])["X"]
    rock = mix_color(nt, rock, (0.46, 0.43, 0.39), remap(nt, btone, 0.55, 1.0, 0.0, 0.45))
    rock = mix_color(nt, rock, (0.12, 0.11, 0.10), remap(nt, btone, 0.35, 0.0, 0.0, 0.45))
    cracks = voronoi(nt, mapping(nt, coord, scale=(1.0, 1.0, 0.45)), 9.0, "DISTANCE_TO_EDGE")
    # joints: thin, and open only here and there
    crack = mul(nt, remap(nt, cracks, 0.014, 0.0, 0.0, 1.0),
                remap(nt, noise(nt, coord, 7.0, 2.0, 0.5), 0.48, 0.60, 0.0, 1.0))
    rock = mix_color(nt, rock, (0.05, 0.045, 0.04), mul(nt, crack, 0.75))
    streak = noise(nt, mapping(nt, coord, scale=(14.0, 14.0, 1.5)), 3.0, 3.0, 0.5)
    rock = mix_color(nt, rock, (0.13, 0.12, 0.10), remap(nt, streak, 0.50, 0.66, 0.0, 0.40))
    steep = remap(nt, math_node(nt, "ADD", nz, math_node(nt, "MULTIPLY", patch, 0.12)), 0.86, 0.70, 0.0, 1.0)
    summit = remap(nt, math_node(nt, "ADD", z, math_node(nt, "MULTIPLY", patch, 0.06)),
                   SEA_Z + 0.33, SEA_Z + 0.39, 0.0, 1.0)
    col = mix_color(nt, col, rock, math_node(nt, "MAXIMUM", steep, summit))
    snow_z = math_node(nt, "ADD", z, math_node(nt, "MULTIPLY", noise(nt, coord, 6.0, 3.0, 0.6), 0.06))
    snow = mul(nt, remap(nt, snow_z, SEA_Z + 0.40, SEA_Z + 0.45, 0.0, 1.0), remap(nt, nz, 0.45, 0.70, 0.0, 1.0),
               remap(nt, noise(nt, coord, 14.0, 3.0, 0.6), 0.30, 0.50, 0.0, 1.0))
    col = mix_color(nt, col, (0.80, 0.82, 0.84), snow)
    # sand at the shore: dry and pale above, darker where wet, a wrack line
    sand_t = math_node(nt, "ADD", z, math_node(nt, "MULTIPLY", noise(nt, coord, 7.0, 2.0, 0.5), 0.010))
    sand = remap(nt, sand_t, SEA_Z + 0.030, SEA_Z + 0.016, 0.0, 1.0)
    sand_col = ramp(nt, fine, ((0.3, (0.56, 0.44, 0.25)), (0.7, (0.70, 0.58, 0.36))))
    sand_col = mix_color(nt, sand_col, (0.30, 0.23, 0.13), remap(nt, z, SEA_Z + 0.007, SEA_Z + 0.001, 0.0, 0.9))
    col = mix_color(nt, col, sand_col, mul(nt, sand, remap(nt, nz, 0.75, 0.90, 0.0, 1.0)))
    # under the water: pale sand shoaling into weed
    col = mix_color(nt, col, (0.30, 0.30, 0.20), remap(nt, z, SEA_Z, SEA_Z - 0.004, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, sand, 0.0, 1.0, 0.92, 0.75), bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    add_bump(nt, bsdf, math_node(nt, "ADD", mul(nt, fine, 0.6),
                                 mul(nt, math_node(nt, "SUBTRACT", strata, mul(nt, crack, 2.0)),
                                     math_node(nt, "MAXIMUM", steep, summit), 0.5)), 0.45, 0.004)
    return mat


def fields_material():
    mat, nt, bsdf, coord = surface("TerraceFields")
    # Each terrace its own crop: young rice, ripening grain, a flooded
    # paddy that takes the sky, barley gold, each sown in rows; the risers
    # dry-stone walls of grey-brown field stones.
    xyz = coord_xyz(nt, coord)
    nz = normal_xyz(nt)["Z"]
    level = attr(nt, "Tread")
    pick = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", level, 0.29), 0.0)
    crop = ramp(nt, pick, ((0.00, (0.17, 0.44, 0.05)), (0.24, (0.33, 0.50, 0.07)),
                           (0.45, (0.07, 0.17, 0.16)), (0.66, (0.62, 0.48, 0.12)),
                           (0.85, (0.24, 0.42, 0.06)), (1.0, (0.50, 0.46, 0.10))))
    flooded = remap(nt, pick, 0.40, 0.44, 0.0, 1.0)
    flooded = math_node(nt, "MULTIPLY", flooded, remap(nt, pick, 0.50, 0.46, 0.0, 1.0))
    # rows across each terrace
    rowd = nt.nodes.new("ShaderNodeVectorMath")
    rowd.operation = "DOT_PRODUCT"
    nt.links.new(coord, rowd.inputs[0])
    rowd.inputs[1].default_value = (0.86, 0.50, 0.0)
    rows = math_node(nt, "SINE", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", rowd.outputs["Value"], math_node(nt, "MULTIPLY", level, 0.013)), TAU * 70.0), 0.0)
    rowmask = remap(nt, rows, 0.2, 0.9, 0.0, 1.0)
    col = mix_color(nt, crop, (0.10, 0.08, 0.04), mul(nt, rowmask, math_node(nt, "SUBTRACT", 0.45,
                                                                             mul(nt, flooded, 0.45))))
    fine = noise(nt, coord, 70.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.06, 0.09, 0.03), remap(nt, fine, 0.3, 0.7, 0.30, 0.0))
    # the risers: field stones
    cells = voronoi_node(nt, mapping(nt, coord, scale=(1.0, 1.0, 1.6)), 120.0)
    stone = ramp(nt, coord_xyz(nt, cells.outputs["Color"])["X"],
                 ((0.0, (0.20, 0.18, 0.15)), (0.5, (0.33, 0.30, 0.25)), (1.0, (0.45, 0.41, 0.34))))
    edge = voronoi(nt, mapping(nt, coord, scale=(1.0, 1.0, 1.6)), 120.0, "DISTANCE_TO_EDGE")
    stone = mix_color(nt, stone, (0.06, 0.05, 0.04), remap(nt, edge, 0.06, 0.0, 0.0, 1.0))
    built = remap(nt, attr(nt, "Field"), -0.2, -0.8, 0.0, 1.0)
    # a wall's face is stone, its coping turfed over like the bank it holds
    wall = remap(nt, nz, 0.93, 0.80, 0.0, 1.0)
    bank = ramp(nt, noise(nt, coord, 40.0, 3.0, 0.6), ((0.3, (0.06, 0.15, 0.03)), (0.7, (0.12, 0.24, 0.05))))
    stones = remap(nt, noise(nt, coord, 9.0, 3.0, 0.6), 0.42, 0.58, 0.0, 1.0)
    col = mix_color(nt, col, mix_color(nt, bank, stone, math_node(nt, "MAXIMUM", stones, built)), wall)
    col = mix_color(nt, col, bank, mul(nt, built, remap(nt, nz, 0.80, 0.93, 0.0, 1.0)))
    del xyz
    nt.links.new(col, bsdf.inputs["Base Color"])
    rough = math_node(nt, "SUBTRACT", 0.85, mul(nt, flooded, math_node(nt, "SUBTRACT", 1.0, wall), 0.75))
    nt.links.new(rough, bsdf.inputs["Roughness"])
    add_bump(nt, bsdf, math_node(nt, "ADD", mul(nt, rowmask, 0.5), mul(nt, wall, edge, -3.0)), 0.4, 0.003)
    return mat


def sea_material():
    mat, nt, bsdf, coord = surface("SeaWater")
    depth = remap(nt, attr(nt, "Depth"), 0.0, 0.060, 0.0, 1.0)
    col = ramp(nt, depth, ((0.00, (0.20, 0.62, 0.55)), (0.12, (0.07, 0.46, 0.48)),
                           (0.35, (0.022, 0.25, 0.36)), (0.70, (0.010, 0.11, 0.24)),
                           (1.00, (0.006, 0.060, 0.15))))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.06
    bsdf.inputs["IOR"].default_value = 1.33
    bsdf.inputs["Specular IOR Level"].default_value = 0.45
    ruffle = noise(nt, mapping(nt, coord, scale=(1.0, 1.6, 1.0)), 28.0, 3.0, 0.5)
    add_bump(nt, bsdf, ruffle, 0.10, 0.002)
    return mat


def foam_material():
    mat, nt, bsdf, coord = surface("Foam")
    # lacy foam: white where it breaks on the shore, into cells and streaks
    # out over the water
    fx = attr(nt, "FoamX")
    cells = voronoi(nt, coord, 70.0, "DISTANCE_TO_EDGE")
    lace = remap(nt, cells, 0.006, 0.022, 1.0, 0.0)
    body = remap(nt, fx, 0.05, 0.55, 1.0, 0.0)
    amount = math_node(nt, "MAXIMUM", body, mul(nt, lace, remap(nt, fx, 0.3, 1.0, 1.0, 0.30)))
    amount = math_node(nt, "MULTIPLY", amount, remap(nt, noise(nt, coord, 16.0, 3.0, 0.6), 0.30, 0.55, 0.55, 1.0))
    col = mix_color(nt, (0.20, 0.60, 0.54), (0.88, 0.91, 0.89), amount)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    add_bump(nt, bsdf, lace, 0.3, 0.002)
    return mat


def river_material():
    mat, nt, bsdf, coord = surface("RiverWater")
    # clear fresh water over a stony bed, white where it falls steeply, the
    # tarn deep and still
    nz = normal_xyz(nt)["Z"]
    depth = remap(nt, attr(nt, "Depth"), 0.0, 0.025, 0.0, 1.0)
    col = ramp(nt, depth, ((0.0, (0.22, 0.55, 0.50)), (0.45, (0.08, 0.38, 0.42)), (1.0, (0.03, 0.20, 0.30))))
    streak = noise(nt, mapping(nt, coord, scale=(6.0, 6.0, 1.0)), 18.0, 3.0, 0.6)
    white = mul(nt, remap(nt, nz, 0.995, 0.96, 0.0, 1.0), remap(nt, streak, 0.35, 0.60, 0.4, 1.0))
    col = mix_color(nt, col, (0.70, 0.78, 0.78), white)
    # into the sea's shallows over the estuary
    col = mix_color(nt, col, (0.20, 0.62, 0.55), remap(nt, attr(nt, "Flow"), 0.80, 0.97, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, white, 0.0, 1.0, 0.05, 0.45), bsdf.inputs["Roughness"])
    bsdf.inputs["IOR"].default_value = 1.33
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    add_bump(nt, bsdf, streak, 0.15, 0.002)
    return mat


def rock_material():
    mat, nt, bsdf, coord = surface("Granite")
    # weathered granite: a grey per stone, feldspar speckle, lichen on the
    # tops, dark in the cracks
    tone = attr(nt, "Tone")
    nz = normal_xyz(nt)["Z"]
    col = ramp(nt, tone, ((0.0, (0.20, 0.19, 0.18)), (0.45, (0.33, 0.31, 0.28)),
                          (0.75, (0.42, 0.39, 0.35)), (1.0, (0.36, 0.30, 0.25))))
    speck = noise(nt, coord, 180.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.08, 0.075, 0.07), remap(nt, speck, 0.60, 0.72, 0.0, 0.7))
    col = mix_color(nt, col, (0.62, 0.58, 0.52), remap(nt, speck, 0.30, 0.20, 0.0, 0.4))
    lich = mul(nt, remap(nt, voronoi(nt, coord, 30.0), 0.18, 0.08, 0.0, 1.0), remap(nt, nz, 0.3, 0.8, 0.0, 1.0),
               remap(nt, noise(nt, coord, 5.0, 2.0, 0.5), 0.50, 0.60, 0.0, 1.0))
    col = mix_color(nt, col, (0.42, 0.45, 0.20), mul(nt, lich, 0.8))
    col = mix_color(nt, col, (0.05, 0.05, 0.045), remap(nt, nz, -0.2, -0.8, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.82
    add_bump(nt, bsdf, math_node(nt, "ADD", speck, mul(nt, noise(nt, coord, 12.0, 4.0, 0.6), 1.5)), 0.4, 0.003)
    return mat


def bark_material():
    mat, nt, bsdf, coord = surface("Bark")
    tone = attr(nt, "Tone")
    col = ramp(nt, tone, ((0.0, (0.10, 0.060, 0.035)), (1.0, (0.20, 0.13, 0.075))))
    ridges = noise(nt, mapping(nt, coord, scale=(40.0, 40.0, 3.0)), 6.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.05, 0.035, 0.02), remap(nt, ridges, 0.4, 0.7, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    add_bump(nt, bsdf, ridges, 0.5, 0.002)
    return mat


def foliage_material():
    mat, nt, bsdf, coord = surface("Foliage")
    # conifers (tone under 0.5) dark blue-green, broadleaf bright and
    # yellow-green, a few already turning; leafy clumps by Voronoi
    tone = attr(nt, "Tone")
    nz = normal_xyz(nt)["Z"]
    col = ramp(nt, tone, ((0.00, (0.020, 0.075, 0.040)), (0.25, (0.030, 0.105, 0.050)),
                          (0.45, (0.045, 0.125, 0.060)), (0.55, (0.13, 0.30, 0.04)),
                          (0.78, (0.22, 0.40, 0.05)), (0.90, (0.36, 0.42, 0.06)),
                          (0.96, (0.62, 0.30, 0.04)), (1.0, (0.70, 0.22, 0.04))))
    leaves = voronoi(nt, coord, 140.0)
    col = mix_color(nt, col, (0.01, 0.03, 0.01), remap(nt, leaves, 0.25, 0.55, 0.0, 0.55))
    col = mix_color(nt, col, (0.38, 0.52, 0.18), mul(nt, remap(nt, nz, 0.4, 0.9, 0.0, 0.25),
                                                     remap(nt, leaves, 0.25, 0.05, 0.0, 1.0)))
    col = mix_color(nt, col, (0.01, 0.025, 0.01), remap(nt, nz, -0.1, -0.7, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.78
    add_bump(nt, bsdf, leaves, 0.6, 0.004)
    translucent(nt, bsdf, (0.10, 0.25, 0.04), 0.15)
    return mat


def plinth_material():
    mat, nt, bsdf, coord = surface("TilePlinth")
    # the tile's frame: a dark slate band round the top, and the skirt the
    # island's ground in section, topsoil over banded clays and stone
    xyz = coord_xyz(nt, coord)
    z = xyz["Z"]
    nz = normal_xyz(nt)["Z"]
    bands = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", z, math_node(nt, "MULTIPLY", noise(nt, coord, 6.0, 2.0, 0.5), 0.012)), 18.0), 0.0)
    soil = ramp(nt, bands, ((0.0, (0.20, 0.13, 0.075)), (0.40, (0.27, 0.18, 0.10)),
                            (0.55, (0.15, 0.10, 0.065)), (0.80, (0.33, 0.25, 0.16)), (1.0, (0.22, 0.15, 0.09))))
    pebbles = voronoi_node(nt, coord, 60.0)
    soil = mix_color(nt, soil, (0.36, 0.33, 0.29), remap(nt, pebbles.outputs["Distance"], 0.18, 0.10, 0.0, 0.8))
    soil = mix_color(nt, soil, (0.07, 0.10, 0.03), remap(nt, z, RIM_Z - 0.030, RIM_Z - 0.008, 0.0, 1.0))
    soil = mix_color(nt, soil, (0.07, 0.05, 0.035), remap(nt, z, 0.030, 0.0, 0.0, 0.7))
    slate = ramp(nt, noise(nt, coord, 30.0, 3.0, 0.5), ((0.3, (0.050, 0.055, 0.060)), (0.7, (0.10, 0.105, 0.11))))
    col = mix_color(nt, soil, slate, remap(nt, nz, 0.30, 0.60, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, nz, 0.3, 0.6, 0.90, 0.55), bsdf.inputs["Roughness"])
    add_bump(nt, bsdf, pebbles.outputs["Distance"], 0.3, 0.003)
    return mat


def piece_materials():
    """Nine slots, in index order: shared by the check and the render."""
    return (terrain_material(), fields_material(), sea_material(), foam_material(), river_material(),
            rock_material(), bark_material(), foliage_material(), plinth_material())


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

    return {"groups": groups, "all": all_, "tile": of(P_TILE), "sea": of(P_SEA), "pool": of(P_POOL),
            "river": of(P_RIVER), "foam": of(P_FOAM), "rocks": of(P_ROCK), "trunks": of(P_TRUNK),
            "crowns": of(P_CROWN)}


PARITY_DIRS = (Vector((0.31, 0.22, 0.925)).normalized(), Vector((-0.57, 0.61, -0.55)).normalized(),
               Vector((0.72, -0.44, 0.53)).normalized(), Vector((-0.13, -0.83, 0.54)).normalized(),
               Vector((0.47, 0.81, -0.35)).normalized(), Vector((-0.88, -0.21, -0.43)).normalized(),
               Vector((0.05, 0.37, -0.93)).normalized())


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 12.0)), Vector((0.0, 0.0, -1.0)), 30.0)
    return None if loc is None else loc.z


def edge_audit(me, cls):
    """The skirt's top vertices: their distance off the hexagon's outline,
    and per edge the heights in order along it, against the canonical edge
    height and against every other edge."""
    tile = cls["tile"][0]
    cap = face_vals(me, "Cap")
    rim = set()
    for p in tile.polys:
        if cap[p.index] == 3:
            rim.update(v for v in p.vertices if me.vertices[v].co.z > 1e-4)
    off = 0.0
    edges = [[] for _ in range(6)]
    for v in rim:
        co = me.vertices[v].co
        off = max(off, abs(hex_in(co.x, co.y)))
        ang = math.degrees(math.atan2(co.y, co.x)) % 360.0
        k = int((ang + 1e-3) // 60.0) % 6
        edges[k].append(((ang - 60.0 * k) % 360.0, co.z))
    prof = [[z for _a, z in sorted(e)] for e in edges]
    counts = [len(p) for p in prof]
    canon = max(abs(z - (RIM_Z - CHAMFER)) for p in prof for z in p)
    mismatch = 0.0
    if len(set(counts)) == 1:
        for p in prof[1:]:
            mismatch = max(mismatch, max(abs(a - b) for a, b in zip(prof[0], p)))
    else:
        mismatch = 9.0
    return off, canon, mismatch, counts


def river_audit(me, cls):
    """Along the river's centre lane, its surface row by row: the largest
    rise from one row to the next, and how far its last row stands over the
    sea's level; the tarn's top and the river's first row under it."""
    ring = vert_vals(me, "Ring")
    lane = vert_vals(me, "Lane")
    river = cls["river"][0]
    centre = sorted((ring[v], me.vertices[v].co.z) for v in river.verts if lane[v] == len(LANES) // 2)
    zs = [z for _r, z in centre]
    rise = max(b - a for a, b in zip(zs, zs[1:]))
    drop = zs[0] - zs[-1]
    pool = cls["pool"][0]
    zone = face_vals(me, "Zone", float)
    ptop = [me.vertices[v].co.z for p in pool.polys if zone[p.index] > 0.5 for v in p.vertices]
    return rise, zs[-1] - SEA_Z, drop, len(zs), max(ptop) - min(ptop), zs[0] - max(ptop)


def terrace_audit(me, cls):
    """Every tile face whose three corners lie on one terrace's tread: its
    tilt off level; per terrace the spread of its tread's heights; the
    rise from each terrace to the next."""
    tread = vert_vals(me, "Tread")
    tile = cls["tile"][0]
    tilt = 0.0
    levels = {}
    n = 0
    for p in tile.polys:
        ks = {tread[v] for v in p.vertices}
        if len(ks) != 1:
            continue
        k = ks.pop()
        if k <= 0:
            continue
        n += 1
        tilt = max(tilt, math.degrees(math.acos(min(1.0, abs(p.normal.z)))))
        for v in p.vertices:
            levels.setdefault(k, []).append(me.vertices[v].co.z)
    spread = max((max(z) - min(z)) for z in levels.values()) if levels else 9.0
    ks = sorted(levels)
    med = [sorted(levels[k])[len(levels[k]) // 2] for k in ks]
    risers = [b - a for a, b in zip(med, med[1:])]
    consecutive = all(b - a == 1 for a, b in zip(ks, ks[1:]))
    return tilt, spread, risers, len(ks), n, consecutive


def water_top(me, shell):
    zone = face_vals(me, "Zone", float)
    top = [p for p in shell.polys if zone[p.index] > 0.5]
    verts = set()
    edges = {}
    for p in top:
        verts.update(p.vertices)
        for k in range(len(p.vertices)):
            e = tuple(sorted((p.vertices[k], p.vertices[(k + 1) % len(p.vertices)])))
            edges[e] = edges.get(e, 0) + 1
    rim = [e for e, c in edges.items() if c == 1]
    return top, verts, rim


def water_audit(me, cls):
    """The sea's top: median height and largest excursion from it."""
    sea = cls["sea"][0]
    _top, verts, _rim = water_top(me, sea)
    zs = sorted(me.vertices[v].co.z for v in verts)
    med = zs[len(zs) // 2]
    exc = max(abs(z - med) for z in zs)
    return med, exc


def enclose_audit(me, cls, T):
    """Over every rim vertex and rim-edge midpoint of the sea's top, the
    ground (or the river running over the sea's end in its mouth); over the
    tarn's, the ground (or, at its outlet, the river falling out under it);
    beside the river's banks, the ground (or the tarn) over its side lanes."""
    tile = cls["tile"][0]
    river = cls["river"][0]
    pool = cls["pool"][0]
    worst = {"sea": 9.0, "pool": 9.0, "river": 9.0}
    n = 0
    covered = 0
    for key in ("sea", "pool"):
        for s in cls[key]:
            _t, _v, rim = water_top(me, s)
            for a, b in rim:
                pa, pb = me.vertices[a].co, me.vertices[b].co
                for p in (pa, (pa + pb) * 0.5):
                    n += 1
                    g = ray_down(tile.tree, p.x, p.y)
                    d = -9.0 if g is None else g - p.z
                    if d < ENCLOSE_MIN:
                        rz = ray_down(river.tree, p.x, p.y)
                        if rz is not None and ((key == "sea" and rz > p.z)
                                               or (key == "pool" and p.z - 0.04 < rz < p.z)):
                            covered += 1
                            continue
                    worst[key] = min(worst[key], d)
    ring = vert_vals(me, "Ring")
    lane = vert_vals(me, "Lane")
    last = max(ring[v] for v in river.verts)
    for v in river.verts:
        if lane[v] not in (0, len(LANES) - 1) or ring[v] < 3:
            continue
        p = me.vertices[v].co
        i, _d = T.near(p.x, p.y)
        if T.path[i][2] >= T.s_coast - 0.01 or ring[v] == last:
            continue
        n += 1
        g = ray_down(tile.tree, p.x, p.y)
        d = -9.0 if g is None else g - p.z
        if d < RIVER_ENCLOSE_MIN:
            # where it leaves the tarn, the tarn's water lies over it
            pz = ray_down(pool.tree, p.x, p.y)
            if pz is not None and pz > p.z:
                covered += 1
                continue
        worst["river"] = min(worst["river"], d)
    return worst, n, covered


def foam_audit(me, cls):
    """Every foam vertex within a band of the sea's level, and every vertex
    of its land edge's top under the shore."""
    tile = cls["tile"][0]
    fx = vert_vals(me, "FoamX", float)
    dev = 0.0
    tuck = 9.0
    for s in cls["foam"]:
        for v in s.verts:
            co = me.vertices[v].co
            dev = max(dev, abs(co.z - SEA_Z))
            if fx[v] < 0.0 and co.z > SEA_Z:
                g = ray_down(tile.tree, co.x, co.y)
                tuck = min(tuck, -9.0 if g is None else g - co.z)
    return dev, tuck, len(cls["foam"])


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
    """Per rock, per sector, its most-buried vertex under the ground; and
    every pair of rocks that overlap."""
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


def tree_audit(me, cls):
    """Every trunk's foot (its bottom cap): the shallowest of its corners
    under the ground straight above it."""
    tile = cls["tile"][0]
    cap = face_vals(me, "Cap")
    depths = []
    for s in cls["trunks"]:
        vs = {v for p in s.polys if cap[p.index] == 1 for v in p.vertices}
        if not vs:
            depths.append(-9.0)
            continue
        d = min((ray_down(tile.tree, me.vertices[v].co.x, me.vertices[v].co.y) or -9.0)
                - me.vertices[v].co.z for v in vs)
        depths.append(d)
    return depths


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
    img = bpy.data.images.new("IslandNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = TERRAIN_IDX
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
    low = build_mesh("HexIslandLow", T, plan, "low", **flags)
    high = build_mesh("HexIslandHigh", T, plan, "high", **flags)
    mats = piece_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    bake_mat = mats[TERRAIN_IDX]

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
    if (len(cls["tile"]) != 1 or len(cls["sea"]) != 1 or len(cls["river"]) != 1
            or len(cls["pool"]) != 1 or len(cls["foam"]) != 1):
        return (fail(f"tile/sea/river/pool/foam not found: {len(cls['tile'])}/{len(cls['sea'])}/"
                     f"{len(cls['river'])}/{len(cls['pool'])}/{len(cls['foam'])}", 3),) + none2
    e_off, e_canon, e_mis, e_counts = edge_audit(low.data, cls)
    r_rise, r_mouth, r_drop, r_rows, p_flat, r_start = river_audit(low.data, cls)
    t_tilt, t_spread, risers, n_terr, n_tread, t_consec = terrace_audit(low.data, cls)
    w_med, w_exc = water_audit(low.data, cls)
    enclose, n_rim, n_cov = enclose_audit(low.data, cls, T)
    foam_dev, foam_tuck, n_foam = foam_audit(low.data, cls)
    rest, pairs, n_rocks = rock_audit(cls)
    roots = tree_audit(low.data, cls)

    img, tex = setup_bake_image(low, bake_mat)
    if img is None:
        return (fail("no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "HexIslandLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "HexIslandLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(build_collider_source(T), "HexIslandCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_hex_island_tile_{os.getpid()}.glb")
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
          f"outer={OUTER_SIZE} zmin={bb[2]:.4f} lo=({bb[0]:.3f},{bb[1]:.3f}) hi=({bb[3]:.3f},{bb[4]:.3f},{bb[5]:.3f})")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured shells={len(cls['all'])} rocks={n_rocks} trunks={len(cls['trunks'])} "
          f"crowns={len(cls['crowns'])} foam={n_foam}")
    print(f"measured edge off={e_off:.6f} canon={e_canon:.6f} mismatch={e_mis:.6f} counts={e_counts}")
    print(f"measured river rise={r_rise:.6f} mouth={r_mouth:.5f} drop={r_drop:.4f} rows={r_rows} "
          f"pool_flat={p_flat:.6f} start_under_pool={r_start:.4f} s_coast={T.s_coast:.3f} len={T.length:.3f}")
    print(f"measured terraces n={n_terr} faces={n_tread} tilt={t_tilt:.4f}deg spread={t_spread:.5f} "
          f"risers={[round(r, 4) for r in risers]} consecutive={t_consec}")
    print(f"measured water median={w_med:.5f} excursion={w_exc:.5f} enclose="
          f"{ {k: round(v, 5) for k, v in enclose.items()} } n={n_rim} under_other_water={n_cov}")
    print(f"measured foam dev={foam_dev:.5f} tuck={foam_tuck:.5f}")
    print(f"measured rocks rest min={min(rest):.4f} max={max(rest):.4f} n={n_rocks} overlaps={pairs}")
    print(f"measured trees roots min={min(roots):.4f} max={max(roots):.4f} n={len(roots)}")

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
    if e_off > EDGE_TOL or e_canon > EDGE_TOL or e_mis > EDGE_TOL:
        return (fail(f"edge: rim {e_off:.5f} m off the hexagon, {e_canon:.5f} m off the canonical "
                     f"edge height {RIM_Z - CHAMFER:.3f}, edges differ by {e_mis:.5f} m (max {EDGE_TOL}); "
                     f"vertices per edge {e_counts}", 17),) + none2
    if r_rise > DRAIN_EPS or abs(r_mouth) > MOUTH_EPS or r_start > 0.0:
        return (fail(f"river: rises {r_rise:.5f} m between rows (max {DRAIN_EPS}), mouth {r_mouth:.5f} m "
                     f"off the sea's level (max {MOUTH_EPS}), source {r_start:.4f} m against the tarn",
                     18),) + none2
    bad_r = [round(r, 4) for r in risers if not (RISER_BAND[0] <= r <= RISER_BAND[1])]
    if (n_terr < TERRACES_MIN or not t_consec or t_tilt > TREAD_TILT_MAX or t_spread > TREAD_SPREAD
            or bad_r):
        return (fail(f"terraces: {n_terr} levels (min {TERRACES_MIN}, consecutive {t_consec}), tread tilt "
                     f"{t_tilt:.3f} deg (max {TREAD_TILT_MAX}), spread {t_spread:.5f} m (max {TREAD_SPREAD}), "
                     f"risers out of band {RISER_BAND}: {bad_r}", 19),) + none2
    if abs(w_med - SEA_Z) > LEVEL_EPS or not (RIPPLE_BAND[0] <= w_exc <= RIPPLE_BAND[1]) or p_flat > POOL_FLAT:
        return (fail(f"water: median {w_med:.5f} m (level {SEA_Z} +- {LEVEL_EPS}), ripple {w_exc:.5f} m "
                     f"(band {RIPPLE_BAND}), tarn {p_flat:.5f} m (flat within {POOL_FLAT})", 20),) + none2
    if enclose["sea"] < ENCLOSE_MIN or enclose["pool"] < ENCLOSE_MIN or enclose["river"] < RIVER_ENCLOSE_MIN:
        return (fail(f"water not contained: ground over the rims {enclose} (min {ENCLOSE_MIN}, river "
                     f"{RIVER_ENCLOSE_MIN})", 21),) + none2
    if n_foam != 1 or foam_dev > FOAM_BAND or foam_tuck < FOAM_TUCK:
        return (fail(f"foam: {n_foam}/1 lines, {foam_dev:.5f} m off the waterline (max {FOAM_BAND}), "
                     f"land edge {foam_tuck:.5f} m under the shore (min {FOAM_TUCK})", 22),) + none2
    n_want = len(plan["rocks"])
    if n_rocks != n_want or min(rest) < PERCH_BAND:
        return (fail(f"rocks: {n_rocks}/{n_want}, worst sector {min(rest):.4f} m under the ground "
                     f"(min {PERCH_BAND})", 23),) + none2
    if pairs:
        return (fail(f"rocks: {pairs} pairs overlap", 24),) + none2
    if len(roots) != len(plan["trees"]) or min(roots) < ROOT_BAND[0] or max(roots) > ROOT_BAND[1]:
        return (fail(f"trees: {len(roots)}/{len(plan['trees'])} trunks, feet {min(roots):.4f}..{max(roots):.4f} "
                     f"m under the ground (band {ROOT_BAND})", 25),) + none2
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

    # Key high on the left so the peaks throw their shadows down the right
    # slopes and the terrace risers catch it; fill, rim, and the warm wedge.
    # The camera looks down on the tile as on a game board, so the floor
    # behind it is the backdrop: the wedge drops a warm pool on it, off to
    # the left where it reaches no water to glare off.
    light("Key", (-3.4, -2.6, 4.8), 260.0, 3.0, (1.0, 0.96, 0.90), spread=28.0)
    light("Fill", (4.2, -3.2, 1.6), 45.0, 8.0, (0.72, 0.82, 1.0))
    light("Rim", (0.8, 3.2, 2.6), 140.0, 3.0, (0.65, 0.80, 1.0))
    light("Wedge", (-2.3, 2.1, 2.4), 260.0, 1.5, (1.0, 0.68, 0.40),
          target=(-2.5, 2.4, 0.0), spread=38.0)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.20, -0.98, 0.0)).normalized()
    cam.location = centre + view * 4.0 + Vector((0.0, 0.0, 2.55))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, -0.14, -0.30))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the island.
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


FLAG_NAMES = ("warp_edge", "uphill_river", "tilt_terrace", "flat_sea", "short_sea", "lift_foam",
              "perch_rock", "pile_rocks", "float_trees")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--warp-edge", action="store_true")
    p.add_argument("--uphill-river", action="store_true")
    p.add_argument("--tilt-terrace", action="store_true")
    p.add_argument("--flat-sea", action="store_true")
    p.add_argument("--short-sea", action="store_true")
    p.add_argument("--lift-foam", action="store_true")
    p.add_argument("--perch-rock", action="store_true")
    p.add_argument("--pile-rocks", action="store_true")
    p.add_argument("--float-trees", action="store_true")
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
    print("hex-island-tile OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
