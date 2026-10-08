"""Game-ready caldera island map tile — a showcase piece, not an example.

Asserts budget conformance of a procedural strategy-game map tile after
composing shipped pipeline pieces: bmesh construction, UVs, nine
materials, high-to-low normal bake, LOD chain, convex hull colliders,
Unity glTF export.

A round tile 2.40 m across. A stratovolcano stands in the middle of it,
its summit collapsed into a caldera, and the sea fills the disc out to its
rim on every side. A crater lake fills the caldera; a young cinder cone
stands in it as an island, its crater on its axis. Barrancos furrow the
outer flanks; two parasitic cones sit on them. From a breached spatter
cone on the front flank a dark aa lava flow runs down between its own
levees to the sea, where it has built out a small delta beside a black-sand
beach. The flanks are zoned by height: forest and meadow low down,
conifers above, then bare ash and red scoria to the rim, and the caldera's
inner walls show their stacked lava and tuff beds.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--warp-edge`` the tile's rim on the
circle at one canonical edge height, ``--breach-rim`` the caldera rim a
closed loop over the lake, ``--tilt-lake`` the lake flat at its level,
``--skew-crater`` the cinder cone's crater on its base's axis,
``--steep-cone`` its flanks inside the repose band, ``--uphill-flow`` the
lava falling all the way, ``--breach-levee`` its channel inside its
levees, ``--short-flow`` its toe under the sea, ``--flat-sea`` the sea's
level and swell, ``--short-sea`` the water contained, ``--lift-foam`` the
foam seated at the waterline, ``--perch-rock`` the rocks sealed in the
ground, ``--pile-rocks`` the rocks apart, ``--float-trees`` the trees
rooted.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python caldera_island_tile.py --
    blender --background --python caldera_island_tile.py -- --skip-decimate
    blender --background --python caldera_island_tile.py -- --output caldera.png
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

SEED = 5209
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))
SQ3 = math.sqrt(3.0)
# the unit hexagon a lattice is laid on before it is stretched onto the disc
EDGE_DIRS = tuple((math.cos(math.radians(30.0 + 60.0 * k)), math.sin(math.radians(30.0 + 60.0 * k)))
                  for k in range(6))

# --- The tile: a disc --------------------------------------------------------
TILE_R = 1.20             # m
TILE_N = {"low": 104, "high": 150}   # lattice steps from the centre to the rim
SEA_Z = 0.150             # the sea's declared level
RIM_Z = 0.168             # the rim's flat top, 18 mm over the water
CHAMFER = 0.005           # the rim's outer arris drops this far: the canonical edge height
LIP_W = 0.040             # the rim's flat band
LIP_R = 0.070             # the seabed climbs to the rim over this

# --- The island's shore ----------------------------------------------------------
ISLAND_C = (0.0, 0.05)
COAST_R = 0.86
COAST_H = ((2, 0.060, 0.5), (3, 0.055, 2.3), (5, 0.035, 1.1), (8, 0.018, 0.2))
COAST_FREE = 0.17         # the coast stays this far inside the tile's rim
BEACH_H, BEACH_L = 0.034, 0.22
CLIFF_TH, CLIFF_H, CLIFF_L = math.radians(150.0), 0.085, 0.050
SHELF_D, DEEP_D = 0.016, 0.068

# --- The volcano: a concave stratocone, its summit collapsed ----------------------
VOLC_C = (0.02, 0.11)
H_V = 0.67                # the cone's virtual summit over the sea, before the collapse
RV = 1.0                  # its virtual foot
P_V = 1.4                 # concavity: about 37 degrees under the rim, 26 on the lower flank
GULLIES = 15
CAL_R = 0.36              # the caldera's rim
CAL_WOB = ((2, 0.050, 0.4), (3, 0.025, 1.9), (11, 0.012, 0.7), (23, 0.008, 2.4), (37, 0.006, 1.2))
RIM_VAR = ((2, 0.026, 0.9), (5, 0.016, 2.2), (9, 0.009, 0.4))
WALL_W = 0.10             # the inner wall's run from the floor's edge to the rim
WALL_P = 1.8              # it steepens to the rim
LAKE_H = 0.220            # the crater lake's level over the sea
LAKE_D = 0.035            # the floor's edge this far under the lake
BOWL = 0.020              # the floor deepens this much to the middle
LAKE_Z = SEA_Z + LAKE_H
BREACH = (math.radians(95.0), 0.24, 0.14)   # --breach-rim: a notch this deep, this wide (rad)

# --- The cinder cone in the lake (Porter 1972: height 0.18 and crater 0.40 of
# the base width; Wizard Island stands 233 m over Crater Lake, crater 90 m across)
CONE_C = (VOLC_C[0] - 0.11, VOLC_C[1] + 0.02)
CONE_W = 0.27             # base width at the waterline
CONE_H = 0.18 * CONE_W    # its height over the lake
CRATER_R = 0.20 * CONE_W  # the crater's rim radius
CRATER_D = 0.024
SKEW = 0.030              # --skew-crater moves the crater off the base's axis by this
STEEP = 1.45              # --steep-cone raises the cone by this factor

# --- Parasitic cones and the vent ------------------------------------------------
PCONES = ((0.62, math.radians(150.0), 0.060, 0.026), (0.60, math.radians(32.0), 0.050, 0.020))
VENT_TH = math.radians(-50.0)
VENT_RV = 0.46
SPATTER = (0.040, 0.015, 0.020, 0.010)   # ring radius, ring width, ring height, crater dip

# --- The lava flow (Etna's channelled aa: 16 m channel in a 52 m flow, 7 m levees)
FLOW_R = (0.46, 0.53, 0.61, 0.70, 0.79, 0.88, 0.95, 1.01, 1.05)
FLOW_STEP = 0.004
FLOW_W = (0.036, 0.064)   # half-width at the vent, at the coast
FLOW_T = (0.007, 0.011)   # thickness over the ground, at the vent, at the coast
LEVEE = 0.0035            # the levee crests over the channel
EDGE_DROP = 0.0020        # the flow's top edge this far under the channel
CARVE = 0.006             # the ground under the flow held this far under its surface
LAVA_SINK = 0.006         # the flow's foot this far under the ground beside it
FLOW_ROW = 0.006
LANES = (-1.0, -0.82, -0.55, -0.25, 0.0, 0.25, 0.55, 0.82, 1.0)
LANE_DZ = (-EDGE_DROP, LEVEE, 0.45 * LEVEE, 0.0005, 0.0, 0.0005, 0.45 * LEVEE, LEVEE, -EDGE_DROP)
FOOT = 1.40               # the flow's foot this many half-widths out: a rubbly flank, not a wall
UPHILL = (0.03, 0.02)     # --uphill-flow humps the flow mid-course: this high, this wide (steeper than the flow falls)
SHORT = 0.06              # --short-flow stops the flow this far short of the coast

# --- Sea, foam ----------------------------------------------------------------------
SEA_N = 52
SEA_IN = 0.018            # the sea's outer edge this far inside the tile, under the rim
WET_H = 0.010             # water triangles reach ground this far over the water, under the shore
SHORT_PULL = 0.060        # --short-sea draws the sheet's shoreward rim this far out to sea
SEA_SLAB = 0.020
RIPPLE = ((0.0011, 23.0, 0.35), (0.0008, 37.0, 2.10), (0.0005, 61.0, 4.0))
LAKE_N = 40
LAKE_SLAB = 0.012
TILT_LAKE = 0.03          # --tilt-lake slopes the lake this much per metre
FOAM_N = 420
FOAM_IN = (0.070, 0.022)  # its land edge this far inside the coast: beach, cliff
FOAM_OUT = (0.014, 0.040)
FOAM_FALL_MAX = 0.040     # its fall to the sea edge never wider: steeper than 6 degrees
FOAM_T = 0.0050            # its crest this far over the calm sea: over every ripple by more than a face tilts
FOAM_EDGE = -0.0015
LIFT_FOAM = 0.020

# --- Scatter --------------------------------------------------------------------------
N_CONIFER = 34
N_BROAD = 52
N_CONE_TREES = 11        # Wizard Island is wooded: small conifers on the cone's flanks
CONE_TREE_SCALE = 0.33
ROOT_D = 0.012            # a trunk starts this far under the ground
FLOAT_TREES = 0.04
N_CRAG = 7
N_BOMB = 8
N_BOULDER = 14
ROCK_GAP = 0.008
REST_SINK = 0.005
SECTORS = 8

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (2.4000, 2.4000, 0.5500)
BASE_TRIS_MIN = 111500
BASE_TRIS_MAX = 114000
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
# face floors: terrain, lava, sea, foam, lake, rock, bark, foliage, plinth
FACE_FLOORS = (51800, 1500, 15100, 1890, 7200, 2810, 940, 7750, 7660)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Edge: rim on the circle at one canonical height
EDGE_TOL = 0.0005
WARP_EDGE = (-0.004, 0.004)  # --warp-edge pulls an arc of the rim in and lifts it by these
# Caldera: the rim closed over the lake, the lake flat
RIM_FREE = 0.040          # the rim's lowest pass at least this far over the lake
LAKE_FLAT = 0.0005
# Cinder cone
COAX_TOL = 0.004
REPOSE = (29.0, 34.0)     # degrees: loose scoria stands at 30-33
# Lava
DRAIN_EPS = 1e-6
TOE_MIN = 0.010           # the toe at least this far under the sea
LEVEE_MIN = 0.002         # each crest at least this far over the channel
# Water
LEVEL_EPS = 0.0015
RIPPLE_BAND = (0.0010, 0.0060)
ENCLOSE_MIN = 0.005
SEAT_MIN = 0.003
# Foam
FOAM_BAND = 0.007
FOAM_TUCK = 0.003
# Rocks, trees
PERCH_BAND = 0.003
ROOT_BAND = (0.004, 0.050)
# Hero yaw about Z only (level on the stage).
HERO_YAW_DEG = 0.0
WALL_Y = 4.2

TERRAIN_IDX = 0
LAVA_IDX = 1
SEA_IDX = 2
FOAM_IDX = 3
LAKE_IDX = 4
ROCK_IDX = 5
BARK_IDX = 6
FOLIAGE_IDX = 7
PLINTH_IDX = 8
MAT_LABELS = ("terrain", "lava", "sea", "foam", "lake", "rock", "bark", "foliage", "plinth")

# part tags, one per face, so the audits can name a shell's role
P_TILE, P_SEA, P_LAKE, P_LAVA, P_FOAM, P_ROCK, P_TRUNK, P_CROWN = 1, 2, 3, 4, 5, 6, 7, 8


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
    """A smooth minimum: rounds the crease where two surfaces meet."""
    h = min(max(0.5 + 0.5 * (b - a) / k, 0.0), 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def hash01(a, b, c):
    """A closed-form draw in [0, 1) from three indices."""
    x = math.sin(a * 12.9898 + b * 78.233 + c * 37.719 + SEED * 0.0137) * 43758.5453
    return x - math.floor(x)


def perp_basis(d):
    ref = UP if abs(d.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = d.cross(ref).normalized()
    return e1, d.cross(e1).normalized()


def ang_diff(a, b):
    return (a - b + math.pi) % TAU - math.pi


# --------------------------------------------------------------------------
# The disc
# --------------------------------------------------------------------------

def disc_in(x, y):
    """Distance inside the tile's rim (negative outside)."""
    return TILE_R - math.hypot(x, y)


def circle_ray(ox, oy, th, radius=TILE_R):
    """Distance from (ox, oy), inside the circle, to it along bearing ``th``."""
    dx, dy = math.cos(th), math.sin(th)
    b = ox * dx + oy * dy
    c = ox * ox + oy * oy - radius * radius
    return -b + math.sqrt(max(b * b - c, 0.0))


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


def disc_lattice(n, radius, cx=0.0, cy=0.0):
    """The hexagon lattice stretched radially onto a disc of ``radius`` about
    (cx, cy): its outline ring lands on the circle."""
    pts, idx, tris, ring = hex_lattice(n, 1.0)
    out = []
    apo = SQ3 / 2.0
    for x, y in pts:
        r = math.hypot(x, y)
        if r < 1e-12:
            out.append((cx, cy))
            continue
        th = math.atan2(y, x)
        edge = min(apo / math.cos(th - math.atan2(s, c)) for c, s in EDGE_DIRS
                   if math.cos(th - math.atan2(s, c)) > 1e-9)
        f = radius / edge
        out.append((cx + x * f, cy + y * f))
    return out, idx, tris, ring


# --------------------------------------------------------------------------
# The ground as a function of plan position
# --------------------------------------------------------------------------

def coast_raw(th):
    return COAST_R * (1.0 + sum(a * math.sin(k * th + p) for k, a, p in COAST_H))


def detail(x, y):
    return (0.55 * math.sin(6.3 * x + 2.1 * y + 0.7) * math.cos(5.1 * y - 1.7 * x + 0.3)
            + 0.30 * math.sin(13.7 * x - 9.1 * y + 1.9)
            + 0.15 * math.sin(27.0 * x + 21.0 * y + 0.5) * math.cos(23.0 * y - 19.0 * x))


def cal_r(ph):
    return CAL_R * (1.0 + sum(a * math.sin(k * ph + p) for k, a, p in CAL_WOB))


def gully(rv, ph):
    """The barrancos: radial furrows cut down the outer flank below the
    rim, 0 on a spur, 1 in a gully's floor."""
    furrow = (0.5 + 0.5 * math.sin(GULLIES * ph + 6.0 * rv + 1.3 + 0.6 * math.sin(3.0 * ph))) ** 3
    return furrow * smoothstep(rv, CAL_R + 0.02, CAL_R + 0.16) * smoothstep(rv, 0.95, 0.70)


def rill(rv, ph):
    """Erosion rills in the loose ash under the rim: many, shallow, fading
    out down the flank."""
    r = (0.5 + 0.5 * math.sin(53.0 * ph + 11.0 * rv + 0.8 * math.sin(7.0 * ph + 2.0))) ** 4
    return r * smoothstep(rv, CAL_R + 0.01, CAL_R + 0.06) * smoothstep(rv, 0.72, 0.50)


def strato(rv, ph, x, y):
    """The stratocone's outer flank over the sea: concave, furrowed by
    barrancos below the rim."""
    st = H_V * max(0.0, 1.0 - rv / RV) ** P_V
    st *= 1.0 - 0.22 * gully(rv, ph) - 0.05 * rill(rv, ph)
    st *= 1.0 + 0.05 * detail(x, y)
    st += sum(a * math.sin(k * ph + p) for k, a, p in RIM_VAR) * smoothstep(rv, CAL_R + 0.24, CAL_R)
    return st


class Terrain:
    """The tile's ground in closed form: the island's shore and relief, the
    stratocone and its caldera, the lake's basin, the cinder cone, the
    parasitic cones and the vent, the bed the lava flow lies in, the seabed
    and the rim. The flow's surface is read off the ground along its line
    and held falling all the way to the sea."""

    def __init__(self, flags):
        self.flags = flags
        self.cone_h = CONE_H * (STEEP if flags.get("steep_cone") else 1.0)
        self.bowl_c = (CONE_C[0] + (SKEW if flags.get("skew_crater") else 0.0), CONE_C[1])
        ctrl = []
        for k, r in enumerate(FLOW_R):
            th = VENT_TH + 0.13 * math.sin(7.0 * r + 0.4) * smoothstep(r, VENT_RV, VENT_RV + 0.12)
            ctrl.append((VOLC_C[0] + r * math.cos(th), VOLC_C[1] + r * math.sin(th)))
        self.vent = ctrl[0]
        self.path = catmull_open(ctrl, FLOW_STEP)
        self.length = self.path[-1][2]
        kd = KDTree(len(self.path))
        for i, (x, y, _s) in enumerate(self.path):
            kd.insert((x, y, 0.0), i)
        kd.balance()
        self.kd = kd
        self.s_cross = self.length
        for x, y, s in self.path:
            if self.polar(x, y)[2] <= 0.0:
                self.s_cross = s
                break
        cx, cy, _s = self.at(self.s_cross)
        self.entry_th = math.atan2(cy - ISLAND_C[1], cx - ISLAND_C[0])
        # the flow's surface: over the ground on its line, never rising
        z = 9.0
        self.wz = []
        for x, y, s in self.path:
            z = min(z, self.base(x, y) + self.thick(s))
            self.wz.append(z)
        self.end_s = self.length - (self.length - self.s_cross + SHORT if flags.get("short_flow") else 0.0)

    # -- the flow's line ---------------------------------------------------
    def at(self, s):
        i = min(max(int(round(s / FLOW_STEP)), 0), len(self.path) - 1)
        return self.path[i]

    def surface(self, s):
        i = min(max(int(round(s / FLOW_STEP)), 0), len(self.path) - 1)
        return self.wz[i]

    def thick(self, s):
        return FLOW_T[0] + (FLOW_T[1] - FLOW_T[0]) * min(max(s / self.s_cross, 0.0), 1.0)

    def width(self, s):
        f = min(max(s / self.s_cross, 0.0), 1.0)
        w = FLOW_W[0] + (FLOW_W[1] - FLOW_W[0]) * f
        w *= 1.0 + 0.10 * math.sin(23.0 * s + 0.6) + 0.06 * math.sin(51.0 * s + 2.0)
        w *= 0.55 + 0.45 * smoothstep(s, 0.0, 0.035)
        # it fans out over its delta where it reaches the shore
        w *= 1.0 + 0.55 * smoothstep(s, self.s_cross - 0.10, self.s_cross + 0.02)
        tail = self.length - s
        if tail < 0.035:
            w *= 0.4 + 0.6 * math.sqrt(max(0.0, 1.0 - ((0.035 - tail) / 0.035) ** 2))
        return w

    def near(self, x, y):
        _co, i, d = self.kd.find((x, y, 0.0))
        return i, d

    # -- the island --------------------------------------------------------
    def coast(self, th):
        c = coast_raw(th)
        # the lava delta: the flow has built the shore out where it entered
        c += 0.07 * math.exp(-(ang_diff(th, math.radians(-46.0)) / 0.16) ** 2)
        return min(c, circle_ray(ISLAND_C[0], ISLAND_C[1], th) - COAST_FREE)

    def cliff_w(self, th):
        """The sea cliffs under the back-left flank."""
        return smoothstep(math.cos(th - CLIFF_TH), math.cos(math.radians(45.0)), math.cos(math.radians(20.0)))

    def steep_w(self, th):
        """Where the seabed falls away steeply: under the cliffs, and off the
        lava delta's front."""
        delta = smoothstep(math.cos(th - math.radians(-46.0)), math.cos(math.radians(16.0)),
                           math.cos(math.radians(6.0)))
        return max(self.cliff_w(th), delta)

    def polar(self, x, y):
        dx, dy = x - ISLAND_C[0], y - ISLAND_C[1]
        th = math.atan2(dy, dx)
        r = math.hypot(dx, dy)
        return th, r, self.coast(th) - r

    def volcano(self, x, y):
        """The relief over the sea: the stratocone cut by the caldera, the
        cinder cone in it, the parasitic cones and the vent."""
        dx, dy = x - VOLC_C[0], y - VOLC_C[1]
        rv = math.hypot(dx, dy)
        ph = math.atan2(dy, dx)
        out = strato(rv, ph, x, y)
        for pr, pth, rb, h in PCONES:
            px = VOLC_C[0] + pr * math.cos(pth)
            py = VOLC_C[1] + pr * math.sin(pth)
            rho = math.hypot(x - px, y - py)
            if rho < rb:
                out += h * smoothstep(rho, rb, 0.30 * rb) - 0.45 * h * smoothstep(rho, 0.36 * rb, 0.0)
        vx, vy = self.vent
        rho = math.hypot(x - vx, y - vy)
        if rho < 0.09:
            ox, oy = math.cos(VENT_TH), math.sin(VENT_TH)
            facing = ((x - vx) * ox + (y - vy) * oy) / max(rho, 1e-6)
            ring = SPATTER[2] * math.exp(-((rho - SPATTER[0]) / SPATTER[1]) ** 2) * smoothstep(facing, 0.55, -0.15)
            out += ring - SPATTER[3] * max(0.0, 1.0 - (rho / (0.85 * SPATTER[0])) ** 2)
        if self.flags.get("breach_rim"):
            th0, depth, wid = BREACH
            out -= depth * math.exp(-(ang_diff(ph, th0) / wid) ** 2) * smoothstep(rv, CAL_R + 0.18, CAL_R - 0.02)
        # the caldera: an inner wall from the floor's edge steepening to the rim
        rc = cal_r(ph)
        rfl = rc - WALL_W
        rx, ry = VOLC_C[0] + rc * math.cos(ph), VOLC_C[1] + rc * math.sin(ph)
        rim = strato(rc, ph, rx, ry)
        if self.flags.get("breach_rim"):
            th0, depth, wid = BREACH
            rim -= depth * math.exp(-(ang_diff(ph, th0) / wid) ** 2)
        floor = LAKE_H - LAKE_D
        t = (rv - rfl) / WALL_W
        if t >= 0.0:
            inner = floor + (rim - floor) * t ** WALL_P
        else:
            inner = floor - BOWL * smoothstep(-t * WALL_W, 0.0, rfl)
        z = smin(out, inner, 0.020)
        # the cinder cone: straight flanks to a crater on its axis
        rho = math.hypot(x - CONE_C[0], y - CONE_C[1])
        rb = 0.5 * CONE_W
        if rho < rb + 0.12:
            flank = LAKE_H + self.cone_h * (rb - rho) / (rb - CRATER_R)
            rho2 = math.hypot(x - self.bowl_c[0], y - self.bowl_c[1])
            bowl = LAKE_H + self.cone_h - CRATER_D * (1.0 - (rho2 / CRATER_R) ** 2)
            z = max(z, smin(flank, bowl, 0.003))
        return z

    def base(self, x, y):
        """Ground without the flow's bed or the rim: z."""
        th, _r, dr = self.polar(x, y)
        cw = self.cliff_w(th)
        if dr < 0.0:
            cw = self.steep_w(th)
            out = -dr
            gentle = SHELF_D * (1.0 - math.exp(-out / 0.08)) + (DEEP_D - SHELF_D) * smoothstep(out, 0.07, 0.24)
            steep = DEEP_D * (1.0 - math.exp(-out / 0.05))
            depth = gentle + (steep - gentle) * cw
            depth += 0.003 * detail(1.7 * x, 1.7 * y) * smoothstep(out, 0.0, 0.10)
            return SEA_Z - depth
        beach = BEACH_H * (1.0 - math.exp(-dr / BEACH_L))
        cliff = CLIFF_H * smoothstep(dr, 0.0, CLIFF_L) + 0.5 * BEACH_H * smoothstep(dr, CLIFF_L, 0.3)
        hz = beach + (cliff - beach) * cw
        # the volcano rises out of the shore's plateau, not on top of it
        far = BEACH_H + (CLIFF_H - 0.5 * BEACH_H) * cw
        m = smoothstep(dr, 0.02, 0.30)
        return SEA_Z + hz + max(self.volcano(x, y) - far, 0.0) * m

    def ground(self, x, y, rim=True):
        """z with the flow's bed and (unless not ``rim``) the rim."""
        z = self.base(x, y)
        i, d = self.near(x, y)
        s = self.path[i][2]
        w = self.width(s)
        if d < 0.96 * w:
            target = self.wz[i] - CARVE
            if target < z:
                z += (target - z) * smoothstep(d, 0.96 * w, 0.84 * w)
        lip = smoothstep(disc_in(x, y), LIP_W + LIP_R, LIP_W) if rim else 0.0
        if lip > 0.0:
            z += (RIM_Z - z) * lip
        return z

    def slope(self, x, y, h=0.006):
        zx = self.ground(x + h, y) - self.ground(x - h, y)
        zy = self.ground(x, y + h) - self.ground(x, y - h)
        return math.hypot(zx, zy) / (2.0 * h)

    def marks(self, x, y):
        """Per point, for the shading: how deep in a barranco, how far
        inside the caldera's rim, how much on a cinder cone."""
        dx, dy = x - VOLC_C[0], y - VOLC_C[1]
        rv, ph = math.hypot(dx, dy), math.atan2(dy, dx)
        inner = smoothstep(rv - cal_r(ph), 0.015, -0.01)
        # chutes down the inner wall
        chute = inner * (0.5 + 0.5 * math.sin(37.0 * ph + 1.2 + 0.5 * math.sin(5.0 * ph))) ** 4
        rho = math.hypot(x - CONE_C[0], y - CONE_C[1])
        cinder = smoothstep(rho, 0.5 * CONE_W + 0.03, 0.5 * CONE_W - 0.01)
        phc = math.atan2(y - CONE_C[1], x - CONE_C[0])
        cone_gul = cinder * smoothstep(rho, CRATER_R, CRATER_R + 0.02) * (
            0.5 + 0.5 * math.sin(19.0 * phc + 1.7 + 0.6 * math.sin(4.0 * phc))) ** 3
        crater = smoothstep(math.hypot(x - self.bowl_c[0], y - self.bowl_c[1]), CRATER_R, 0.55 * CRATER_R)
        for pr, pth, rb, _h in PCONES:
            px = VOLC_C[0] + pr * math.cos(pth)
            py = VOLC_C[1] + pr * math.sin(pth)
            d = math.hypot(x - px, y - py)
            cinder = max(cinder, smoothstep(d, rb, 0.6 * rb))
            crater = max(crater, smoothstep(d, 0.36 * rb, 0.15 * rb))
        dv = math.hypot(x - self.vent[0], y - self.vent[1])
        cinder = max(cinder, smoothstep(dv, 0.07, 0.04))
        return max(gully(rv, ph), 0.6 * rill(rv, ph), chute, cone_gul), inner, cinder, crater

    def in_caldera(self, x, y, pad=0.0):
        dx, dy = x - VOLC_C[0], y - VOLC_C[1]
        return math.hypot(dx, dy) < cal_r(math.atan2(dy, dx)) + pad


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

    def dry(x, y, pad, cal_pad=None):
        i, d = T.near(x, y)
        s = T.path[i][2]
        if d < 1.15 * T.width(s) + pad:
            return False
        if math.hypot(x - T.vent[0], y - T.vent[1]) < 0.075 + pad:
            return False
        if T.in_caldera(x, y, pad if cal_pad is None else cal_pad):
            return False
        return disc_in(x, y) > LIP_W + LIP_R + 0.05

    rocks = []
    # crags on the caldera's rim, bombs on the ash, boulders on the shore
    for kind, n, tries in (("crag", N_CRAG, 4000), ("bomb", N_BOMB, 4000), ("boulder", N_BOULDER, 4000)):
        got = 0
        for _ in range(tries):
            if got >= n:
                break
            ang = rng.uniform(-math.pi, math.pi)
            u = rng.uniform(0.0, 1.0)
            r = rng.uniform(0.0, 1.0)
            if kind == "crag":
                rad = cal_r(ang) + 0.015 + 0.055 * u
                x, y = VOLC_C[0] + rad * math.cos(ang), VOLC_C[1] + rad * math.sin(ang)
                r = 0.020 + 0.014 * r
            elif kind == "bomb":
                rad = 0.42 + 0.20 * u
                x, y = VOLC_C[0] + rad * math.cos(ang), VOLC_C[1] + rad * math.sin(ang)
                r = 0.012 + 0.010 * r
            else:
                # half on the black beach beside the delta
                th = T.entry_th + 0.55 * (2.0 * u - 1.0) if got % 2 == 0 else ang
                c = T.coast(th) - rng.uniform(0.02, 0.20)
                x, y = ISLAND_C[0] + c * math.cos(th), ISLAND_C[1] + c * math.sin(th)
                r = 0.013 + 0.016 * r
            draws = [rng.uniform(0.0, 1.0) for _ in range(8)]
            if not dry(x, y, r + 0.02, cal_pad=0.0 if kind == "crag" else None) or not clear(x, y, r * 1.5):
                continue
            hz = T.ground(x, y) - SEA_Z
            if hz < 0.012:
                continue
            if kind == "crag" and (hz < LAKE_H + 0.06 or T.slope(x, y) > 1.1):
                continue
            if kind == "bomb" and (hz < 0.20 or T.slope(x, y) > 0.8):
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
    for kind, n, tries in (("conifer", N_CONIFER, 20000), ("broad", N_BROAD, 20000)):
        got = 0
        for _ in range(tries):
            if got >= n:
                break
            x = rng.uniform(-TILE_R, TILE_R)
            y = rng.uniform(-TILE_R, TILE_R)
            size = rng.uniform(0.0, 1.0)
            tone = rng.uniform(0.0, 1.0)
            spin = rng.uniform(0.0, TAU)
            keep = rng.uniform(0.0, 1.0)
            if disc_in(x, y) < 0.1:
                continue
            _th, _r, dr = T.polar(x, y)
            if dr < 0.08:
                continue
            r = 0.040 + 0.018 * size if kind == "conifer" else 0.048 + 0.016 * size
            if not dry(x, y, r + 0.01) or not clear(x, y, r):
                continue
            z = T.ground(x, y) - SEA_Z
            sl = T.slope(x, y)
            # stands in clumps: a forest field in space
            forest = 0.5 + 0.5 * math.sin(7.0 * x + 3.0 * y + 1.2) * math.cos(5.0 * y - 4.0 * x + 0.4)
            if kind == "conifer":
                if not (0.11 < z < 0.24) or sl > 1.25 or keep > 0.45 + forest:
                    continue
            else:
                if not (0.02 < z < 0.15) or sl > 0.95 or keep > 0.40 + forest:
                    continue
            taken.append((x, y, r))
            trees.append({"x": x, "y": y, "kind": kind, "size": size, "tone": tone, "spin": spin, "r": r,
                          "scale": 1.0})
            got += 1
    got = 0
    rb = 0.5 * CONE_W
    for _ in range(4000):
        if got >= N_CONE_TREES:
            break
        ang = rng.uniform(-math.pi, math.pi)
        f = rng.uniform(0.0, 1.0)
        size = rng.uniform(0.0, 1.0)
        tone = rng.uniform(0.0, 1.0)
        spin = rng.uniform(0.0, TAU)
        rho = rb * (0.50 + 0.38 * f)
        x, y = CONE_C[0] + rho * math.cos(ang), CONE_C[1] + rho * math.sin(ang)
        r = CONE_TREE_SCALE * (0.040 + 0.018 * size)
        if not clear(x, y, r) or T.ground(x, y) < LAKE_Z + 0.006:
            continue
        taken.append((x, y, r))
        trees.append({"x": x, "y": y, "kind": "conifer", "size": size, "tone": tone, "spin": spin, "r": r,
                      "scale": CONE_TREE_SCALE})
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
    flow row), Lane (its place across), Black (black sand), Depth (water
    over the bed), FoamX (across the foam), Flow (along the lava), Chan (the
    lava's channel)."""

    def __init__(self, bm):
        self.bm = bm
        self.tone = bm.faces.layers.float.new("Tone")
        self.zone = bm.faces.layers.float.new("Zone")
        self.part = bm.faces.layers.int.new("Part")
        self.ident = bm.faces.layers.int.new("Ident")
        self.cap = bm.faces.layers.int.new("Cap")
        self.ring = bm.verts.layers.int.new("Ring")
        self.lane = bm.verts.layers.int.new("Lane")
        self.black = bm.verts.layers.float.new("Black")
        self.depth = bm.verts.layers.float.new("Depth")
        self.foamx = bm.verts.layers.float.new("FoamX")
        self.flow = bm.verts.layers.float.new("Flow")
        self.chan = bm.verts.layers.float.new("Chan")
        self.gully = bm.verts.layers.float.new("Gully")
        self.inner = bm.verts.layers.float.new("Inner")
        self.crater = bm.verts.layers.float.new("Crater")
        self.cinder = bm.verts.layers.float.new("Cinder")
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
    """The tile: a triangle lattice over the disc carrying the island, the
    seabed and the rim, its outline chamfered down to the canonical edge
    height, and a skirt straight down to a flat base at Z = 0."""
    pts, _idx, tris, ring = disc_lattice(n, TILE_R)
    on_ring = set(ring)
    verts = []
    dins = []
    for k, (x, y) in enumerate(pts):
        z = RIM_Z - CHAMFER if k in on_ring else T.ground(x, y)
        v = B.vert((x, y, z))
        th, _r, dr = T.polar(x, y)
        near = smoothstep(math.cos(ang_diff(th, T.entry_th)), math.cos(0.85), math.cos(0.40))
        v[B.black] = near * smoothstep(dr, 0.26, 0.06)
        v[B.gully], v[B.inner], v[B.cinder], v[B.crater] = T.marks(x, y)
        v[B.depth] = max(0.0, SEA_Z - z)
        verts.append(v)
        dins.append(disc_in(x, y))
    if flags.get("warp_edge"):
        # an arc of the rim at the back pulled in and lifted
        for k in ring[n: 2 * n]:
            v = verts[k]
            ln = math.hypot(v.co.x, v.co.y)
            v.co += Vector((WARP_EDGE[0] * v.co.x / ln, WARP_EDGE[0] * v.co.y / ln, WARP_EDGE[1]))
    for a, b, c in tris:
        va, vb, vc = verts[a], verts[b], verts[c]
        if (min(dins[a], dins[b], dins[c]) < LIP_W + LIP_R + 0.01
                and max(v.co.z for v in (va, vb, vc)) > SEA_Z):
            mat = PLINTH_IDX
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


def water_region(pts, tris, wet):
    """The lattice triangles touching a wet point, filled round any pinch,
    the largest connected sheet only."""
    region = {t for t in tris if any(wet[i] for i in t)}
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
    del pts
    return {t for t in region if comp[t] == main}


def add_sea(B, T, plan, flags):
    """The sea: a lattice sheet over every triangle that holds water, from
    the shore (its rim run under the ground) out to the tile's rim (under
    the rim's flat). Where the lava runs into it the sheet runs in under the
    flow until the bed carved under the lava closes its rim."""
    pts, _idx, tris, _ring = disc_lattice(SEA_N, TILE_R - SEA_IN)
    gz = [T.ground(x, y) for x, y in pts]
    wet = [g < SEA_Z + WET_H for g in gz]
    region = water_region(pts, tris, wet)
    flat = flags.get("flat_sea", False)
    shore = set()
    if flags.get("short_sea"):
        use = {}
        for t in region:
            for k in range(3):
                a, b = t[k], t[(k + 1) % 3]
                key = (min(a, b), max(a, b))
                use[key] = use.get(key, 0) + 1
        shore = {i for key, c in use.items() if c == 1 for i in key if disc_in(*pts[i]) > SEA_IN + 0.03}
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
                z = SEA_Z if flat else SEA_Z + ripple(plan, x, y)
                v = B.vert((x, y, z))
                # the water's colour reads the open seabed, not the rim's climb
                v[B.depth] = max(0.0, SEA_Z - T.ground(x, y, rim=False))
                top[i] = v
    keys = sorted(top)
    remap_ = {k: n for n, k in enumerate(keys)}
    tv = [top[k] for k in keys]
    faces = [tuple(remap_[i] for i in t) for t in sorted(region)]
    slab(B, tv, faces, lambda v: SEA_Z - SEA_SLAB, lambda v: v[B.depth], SEA_IDX, P_SEA, 1, SEA_SLAB)


def add_lake(B, T, flags):
    """The crater lake: a flat sheet over every lattice triangle in the
    caldera that holds water, its rim run under the walls and round the
    cinder cone's foot."""
    pts, _idx, tris, _ring = disc_lattice(LAKE_N, CAL_R * 1.25, VOLC_C[0], VOLC_C[1])
    gz = [T.ground(x, y) for x, y in pts]
    wet = [gz[k] < LAKE_Z + WET_H and T.in_caldera(*pts[k]) for k in range(len(pts))]
    region = water_region(pts, tris, wet)
    tilt = TILT_LAKE if flags.get("tilt_lake") else 0.0
    top = {}
    for t in region:
        for i in t:
            if i not in top:
                x, y = pts[i]
                v = B.vert((x, y, LAKE_Z + tilt * (x - VOLC_C[0])))
                v[B.depth] = max(0.0, LAKE_Z - gz[i])
                top[i] = v
    keys = sorted(top)
    remap_ = {k: n for n, k in enumerate(keys)}
    tv = [top[k] for k in keys]
    faces = [tuple(remap_[i] for i in t) for t in sorted(region)]
    slab(B, tv, faces, lambda v: LAKE_Z - LAKE_SLAB - abs(tilt) * 0.5, lambda v: v[B.depth],
         LAKE_IDX, P_LAKE, 2, LAKE_SLAB)


def flow_z(T, s, flags):
    z = T.surface(s)
    if flags.get("uphill_flow"):
        z += UPHILL[0] * math.exp(-((s - 0.45 * T.s_cross) / UPHILL[1]) ** 2)
    return z


def add_lava(B, T, flags):
    """The lava flow: from the vent's hollow down the flank and out under
    the sea, flat-bottomed channel between two levees on top, its top edges
    dropping to a foot sunk in the ground beside it. Section: nine lanes on
    top, two corners under."""
    rows = []
    s = 0.0
    while s <= T.end_s + 1e-9:
        rows.append(s)
        s += FLOW_ROW
    breach = flags.get("breach_levee")
    sec = []
    for r, s in enumerate(rows):
        i = min(int(round(s / FLOW_STEP)), len(T.path) - 2)
        x, y, _s = T.path[i]
        nx_, ny_, _ = T.path[i + 1]
        tx, ty = nx_ - x, ny_ - y
        ln = math.hypot(tx, ty) or 1.0
        lx, ly = -ty / ln, tx / ln
        w = T.width(s)
        z = flow_z(T, s, flags)
        ring = []
        for li, (f, dz) in enumerate(zip(LANES, LANE_DZ)):
            # the crests and channel walls wander a little, like real levees
            jit = 0.0 if li in (0, len(LANES) - 1, 4) else 0.0007 * math.sin(47.0 * s + 3.0 * li)
            if breach and li == 7 and 0.35 * T.s_cross < s < 0.55 * T.s_cross:
                dz = -0.002
            v = B.vert((x + lx * f * w, y + ly * f * w, z + dz + jit), ring=r, lane=li)
            v[B.flow] = s / T.length
            v[B.chan] = 1.0 - smoothstep(abs(f), 0.30, 0.60)
            ring.append(v)
        for f in (FOOT, -FOOT):
            cx, cy = x + lx * f * w, y + ly * f * w
            v = B.vert((cx, cy, min(T.ground(cx, cy), z - T.thick(s)) - LAVA_SINK), ring=r, lane=-1)
            v[B.flow] = s / T.length
            ring.append(v)
        sec.append(ring)
    m = len(sec[0])
    L = len(LANES)
    for a, b in zip(sec, sec[1:]):
        for k in range(m):
            q = (k + 1) % m
            zone = 1.0 if k < L - 1 else 0.0
            B.quad(a[k], b[k], b[q], a[q], LAVA_IDX, 0.5, P_LAVA, 3, zone=zone)
    # the end caps: fan from the bottom left corner
    for ring, cap, flip in ((sec[0], 1, False), (sec[-1], 2, True)):
        fan = [(ring[m - 1], ring[k], ring[k + 1]) for k in range(m - 2)]
        for tri in fan:
            B.face(tuple(reversed(tri)) if flip else tri, LAVA_IDX, 0.5, P_LAVA, 3, cap=cap)


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
    # the land edge leans inland, so it never stands parallel to the sea's
    # walls under the shore
    dx, dy = li[0] - wl[0], li[1] - wl[1]
    ln = math.hypot(dx, dy) or 1.0
    lb = (li[0] + 0.004 * dx / ln, li[1] + 0.004 * dy / ln)
    row = [B.vert((li[0], li[1], zt)), B.vert((wl[0], wl[1], zt)), B.vert((so[0], so[1], zo)),
           B.vert((so[0], so[1], zb)), B.vert((lb[0], lb[1], zb))]
    # FoamX: 0 at the waterline, 1 at its sea edge, ``inner`` at its land edge
    for v, fx in zip(row, (inner, 0.0, 1.0, 1.0, inner)):
        v[B.foamx] = fx
    return row


def foam_width(s, ph, loop):
    return FOAM_OUT[0] + (FOAM_OUT[1] - FOAM_OUT[0]) * (
        0.5 + 0.30 * math.sin(TAU * 5.0 * s + ph[loop % 3]) + 0.20 * math.sin(TAU * 13.0 * s + ph[3 + loop % 3]))


def add_foam(B, T, plan, flags):
    """A foam line at the waterline round the coast, from one side of the
    lava's delta round to the other, its land edge tucked under the shore."""
    lift = LIFT_FOAM if flags.get("lift_foam") else 0.0
    ph = plan["foam"]
    mth = T.entry_th
    gap = (T.width(T.s_cross) * FOOT + 0.07) / T.coast(mth)
    rows = []
    for i in range(FOAM_N):
        s = i / (FOAM_N - 1)
        th = mth + gap + (TAU - 2.0 * gap) * s
        c = T.coast(th)
        cw = T.cliff_w(th)
        # the shore's normal from the coast's own slope in plan
        h = 1e-3
        dc = (T.coast(th + h) - T.coast(th - h)) / (2.0 * h)
        rx, ry = math.cos(th), math.sin(th)
        tx, ty = -math.sin(th) * c + rx * dc, math.cos(th) * c + ry * dc
        ln = math.hypot(tx, ty)
        nx, ny = ty / ln, -tx / ln
        px, py = ISLAND_C[0] + c * rx, ISLAND_C[1] + c * ry
        fin = FOAM_IN[0] + (FOAM_IN[1] - FOAM_IN[0]) * cw
        # it frays out to nothing toward the delta
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
                                                    (-0.8, -0.3, 0.5), (0.4, 0.7, -0.2), (0.05, 0.1, 1.0),
                                                    (0.9, -0.4, 0.1), (-0.3, -0.8, -0.1)))


def add_rocks(B, plan, G, flags):
    perch = flags.get("perch_rock", False)
    items = [dict(it) for it in plan["rocks"]]
    if flags.get("pile_rocks"):
        # two crags dropped against the first
        for k, it in enumerate(items[1:3]):
            it["x"] = items[0]["x"] + (0.6 if k else -0.6) * items[0]["r"]
            it["y"] = items[0]["y"] + 0.3 * items[0]["r"]
    for n, it in enumerate(items):
        dirs, quads = cube_sphere(3)
        r = it["r"]
        ax = Vector((r * it["long"], r, r * it["flat"]))
        if it["kind"] == "crag":
            ax = Vector((r * it["long"] * 1.25, r * 0.85, r * (it["flat"] + 0.15)))
        yaw = Matrix.Rotation(it["yaw"], 3, "Z")
        pts = []
        for d in dirs:
            q = Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z))
            q *= 1.0 + 0.12 * sum(a * math.sin(w.normalized().dot(d) * 3.0 + ph) for w, ph, a in it["waves"])
            # fractured faces: flattened where a plane cuts it
            for k, cdir in enumerate(CUT_DIRS[:8 if it["kind"] == "crag" else 3]):
                lim = (0.56 + 0.18 * hash01(n, k, 3)) * (ax.x * abs(cdir.x) + ax.y * abs(cdir.y) + ax.z * abs(cdir.z))
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
    for n, t in enumerate(plan["trees"]):
        # --float-trees lifts the lowland broadleaves, under the island's top
        lift = FLOAT_TREES if flags.get("float_trees") and t["kind"] == "broad" else 0.0
        x, y = t["x"], t["y"]
        ident = 200 + n
        # the trunk's foot under the lowest ground round it
        g = min(G.z(x + 0.008 * math.cos(a), y + 0.008 * math.sin(a)) for a in (0.0, 2.1, 4.2))
        g = min(g, G.z(x, y))
        foot = Vector((x, y, g - ROOT_D + lift))
        sc = t["scale"]
        if t["kind"] == "conifer":
            h = sc * (0.13 + 0.07 * t["size"])
            trunk_r = sc * (0.0055 + 0.002 * t["size"])
            top = foot + Vector((0.0, 0.0, ROOT_D + 0.30 * h))
            tube(B, (foot, top), (trunk_r, trunk_r * 0.8), 6, BARK_IDX, t["tone"], P_TRUNK, ident)
            tone = 0.05 + 0.40 * t["tone"]
            rb = sc * (0.040 + 0.018 * t["size"])
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
            rc = 0.036 + 0.014 * t["size"]
            spin = Matrix.Rotation(t["spin"], 3, "Z")
            for k, (ox, oy, oz, f) in enumerate(((0.0, 0.0, 0.9, 1.0), (0.55, 0.15, 0.55, 0.78),
                                                  (-0.35, 0.45, 0.6, 0.72), (-0.2, -0.5, 0.5, 0.70))):
                c = top + spin @ Vector((ox * rc, oy * rc, oz * rc))
                lump_ball(B, c, Vector((rc * f, rc * f * 0.95, rc * f * 0.82)),
                          Matrix.Rotation(t["spin"] + k, 3, "Z"), tone, ident)


def break_coplanar(B, parts, passes=8):
    """Bough tiers, lumps and rocks are many small faces in every direction;
    now and then one lands in another shell's plane. Turn the shell's piece
    a few degrees about the vertical through its lowest point, and sink it
    half a millimetre (two trees on one contour carry level caps a turn
    leaves level), until none does."""
    bm = B.bm
    for _ in range(passes):
        bm.normal_update()
        bm.verts.index_update()
        faces = list(bm.faces)
        # a tree's trunk and crown move together
        key = [(P_TRUNK if f[B.part] == P_CROWN else f[B.part], f[B.ident]) for f in faces]
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
                # of two movable shells, move one
                if key[j][0] in parts and key[j] > key[i]:
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
                v.co = root + R @ (v.co - root) - Vector((0.0, 0.0, 0.0005))


def build_mesh(name, T, plan, detail_="low", **flags):
    bm = bmesh.new()
    try:
        B = Builder(bm)
        add_tile(B, T, TILE_N[detail_], flags)
        bm.normal_update()
        G = Ground(BVHTree.FromBMesh(bm))
        add_sea(B, T, plan, flags)
        add_lake(B, T, flags)
        add_lava(B, T, flags)
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
        crease = {TERRAIN_IDX: 55.0, LAVA_IDX: 40.0, ROCK_IDX: 40.0, FOLIAGE_IDX: 70.0,
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
    groups = [[Vector((TILE_R * math.cos(TAU * k / 24), TILE_R * math.sin(TAU * k / 24), z))
               for k in range(24) for z in (0.0, SEA_Z)]]
    sectors = [[] for _ in range(6)]
    for k in range(6 * 9):
        # nine rays per sector, its two edges shared with its neighbours
        th = TAU * (k // 9 + (k % 9) / 8.0) / 6.0
        c = T.coast(th)
        for f in (1.0, 0.7, 0.4):
            x = ISLAND_C[0] + f * c * math.cos(th)
            y = ISLAND_C[1] + f * c * math.sin(th)
            z = T.ground(x, y)
            sec = sectors[k // 9]
            sec.append(Vector((x, y, SEA_Z)))
            sec.append(Vector((x, y, max(z, SEA_Z + 0.002))))
    sectors_c = [Vector((ISLAND_C[0], ISLAND_C[1], SEA_Z)),
                 Vector((ISLAND_C[0], ISLAND_C[1], T.ground(*ISLAND_C)))]
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
    mat, nt, bsdf, coord = surface("VolcanicGround")
    # The island's skin zoned by height the way a wet volcanic island is:
    # forest and meadow low down, darker conifer floor above, heath, then
    # bare ash to the rim, streaked down the barrancos (ochre on the spurs,
    # red-brown scoria in the gullies). Only the caldera's inner walls and
    # the sea cliffs show the stacked lava and tuff beds. The cinder cones
    # are dark red-black scoria; sand at the shore turns black beside the
    # delta.
    xyz = coord_xyz(nt, coord)
    z = xyz["Z"]
    nz = normal_xyz(nt)["Z"]
    gul = attr(nt, "Gully")
    inner = attr(nt, "Inner")
    cinder = attr(nt, "Cinder")
    patch = noise(nt, coord, 5.0, 4.0, 0.55)
    fine = noise(nt, coord, 60.0, 3.0, 0.6)
    zz = math_node(nt, "ADD", z, math_node(nt, "MULTIPLY", patch, 0.05))
    lush = ramp(nt, patch, ((0.30, (0.060, 0.200, 0.028)), (0.50, (0.100, 0.270, 0.035)),
                            (0.70, (0.170, 0.330, 0.050)), (0.82, (0.24, 0.32, 0.07))))
    forest = ramp(nt, patch, ((0.30, (0.035, 0.095, 0.028)), (0.60, (0.065, 0.135, 0.038)),
                              (0.85, (0.13, 0.15, 0.055))))
    heath = ramp(nt, patch, ((0.30, (0.17, 0.16, 0.075)), (0.60, (0.24, 0.20, 0.10)), (0.85, (0.30, 0.24, 0.13))))
    ash = ramp(nt, noise(nt, coord, 8.0, 4.0, 0.6), ((0.25, (0.15, 0.13, 0.12)), (0.50, (0.22, 0.19, 0.17)),
                                                     (0.75, (0.28, 0.24, 0.20)), (0.92, (0.33, 0.27, 0.21))))
    # down the barrancos: pale ochre on the spurs, red-brown scoria in the floors
    ash = mix_color(nt, ash, (0.40, 0.30, 0.17), remap(nt, gul, 0.08, 0.0, 0.0, 0.60))
    ash = mix_color(nt, ash, (0.15, 0.065, 0.042), remap(nt, gul, 0.20, 0.70, 0.0, 0.85))
    grain = noise(nt, coord, 140.0, 2.0, 0.6)
    ash = mix_color(nt, ash, (0.10, 0.085, 0.08), remap(nt, grain, 0.55, 0.70, 0.0, 0.45))
    lapilli = voronoi_node(nt, coord, 70.0)
    ash = mix_color(nt, ash, (0.09, 0.06, 0.05), mul(nt, remap(nt, lapilli.outputs["Distance"], 0.16, 0.08, 0.0, 1.0),
                                                   remap(nt, coord_xyz(nt, lapilli.outputs["Color"])["X"],
                                                         0.6, 0.8, 0.0, 0.8)))
    col = mix_color(nt, lush, forest, remap(nt, zz, SEA_Z + 0.075, SEA_Z + 0.125, 0.0, 1.0))
    col = mix_color(nt, col, heath, remap(nt, zz, SEA_Z + 0.175, SEA_Z + 0.205, 0.0, 1.0))
    col = mix_color(nt, col, ash, remap(nt, zz, SEA_Z + 0.205, SEA_Z + 0.240, 0.0, 1.0))
    col = mix_color(nt, col, (0.04, 0.08, 0.02), remap(nt, fine, 0.35, 0.65, 0.30, 0.0))
    # the beds: lava, scoria, pale tuff and ash stacked level through the
    # cone, thick and thin by turns
    bed_t = math_node(nt, "ADD", z, math_node(nt, "MULTIPLY", noise(nt, coord, 3.0, 3.0, 0.6), 0.030))
    beds = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", bed_t, math_node(nt, "MULTIPLY", math_node(nt, "SINE", math_node(nt, "MULTIPLY", bed_t, 61.0), 0.0),
                                    0.006)), 34.0), 0.0)
    strata = ramp(nt, beds, ((0.00, (0.11, 0.095, 0.09)), (0.20, (0.17, 0.15, 0.14)),
                             (0.32, (0.27, 0.13, 0.08)), (0.45, (0.21, 0.18, 0.16)),
                             (0.60, (0.36, 0.31, 0.24)), (0.74, (0.19, 0.16, 0.14)), (1.00, (0.11, 0.10, 0.09))))
    blocks = voronoi_node(nt, mapping(nt, coord, scale=(1.0, 1.0, 0.5)), 26.0)
    btone = coord_xyz(nt, blocks.outputs["Color"])["X"]
    strata = mix_color(nt, strata, (0.07, 0.06, 0.055), remap(nt, btone, 0.35, 0.0, 0.0, 0.40))
    cracks = voronoi(nt, mapping(nt, coord, scale=(1.0, 1.0, 0.5)), 26.0, "DISTANCE_TO_EDGE")
    crack = mul(nt, remap(nt, cracks, 0.012, 0.0, 0.0, 1.0),
                remap(nt, noise(nt, coord, 7.0, 2.0, 0.5), 0.45, 0.58, 0.0, 1.0))
    strata = mix_color(nt, strata, (0.04, 0.035, 0.035), mul(nt, crack, 0.45))
    # weathered back toward one grey-brown: the beds read, they do not stripe
    strata = mix_color(nt, strata, ramp(nt, noise(nt, coord, 9.0, 4.0, 0.6),
                                        ((0.3, (0.14, 0.12, 0.11)), (0.7, (0.24, 0.20, 0.17)))), 0.45)
    # talus fans of fallen ash at the walls' feet
    strata = mix_color(nt, strata, (0.20, 0.17, 0.15),
                       remap(nt, noise(nt, coord, 18.0, 3.0, 0.6), 0.55, 0.70, 0.0, 0.5))
    steep = remap(nt, math_node(nt, "ADD", nz, math_node(nt, "MULTIPLY", patch, 0.10)), 0.80, 0.60, 0.0, 1.0)
    cliffs = math_node(nt, "MAXIMUM", inner, remap(nt, z, SEA_Z + 0.13, SEA_Z + 0.09, 0.0, 1.0))
    # chutes: scree streaks down the walls
    strata = mix_color(nt, strata, (0.07, 0.06, 0.055), mul(nt, remap(nt, gul, 0.15, 0.8, 0.0, 0.7), inner))
    col = mix_color(nt, col, strata, mul(nt, steep, cliffs))
    col = mix_color(nt, col, mix_color(nt, (0.16, 0.14, 0.13), strata, 0.35),
                    mul(nt, inner, math_node(nt, "SUBTRACT", 1.0, steep)))
    # cinder cones: red-black scoria, rusted where the gas came through
    scoria = ramp(nt, noise(nt, coord, 25.0, 4.0, 0.6), ((0.25, (0.045, 0.032, 0.030)), (0.50, (0.085, 0.045, 0.036)),
                                                         (0.75, (0.15, 0.065, 0.045)), (0.92, (0.21, 0.10, 0.06))))
    scoria = mix_color(nt, scoria, (0.26, 0.12, 0.07), remap(nt, gul, 0.05, 0.0, 0.0, 0.35))
    scoria = mix_color(nt, scoria, (0.035, 0.025, 0.022), remap(nt, gul, 0.30, 0.80, 0.0, 0.6))
    scoria = mix_color(nt, scoria, (0.06, 0.05, 0.045), remap(nt, grain, 0.55, 0.72, 0.0, 0.5))
    scoria = mix_color(nt, scoria, (0.035, 0.022, 0.020), mul(nt, attr(nt, "Crater"), 0.85))
    col = mix_color(nt, col, scoria, mul(nt, cinder, remap(nt, z, LAKE_Z - 0.003, LAKE_Z + 0.001, 0.0, 1.0)))
    # sulphur stains low on the inner walls, where the fumaroles were
    sul = mul(nt, remap(nt, voronoi(nt, coord, 18.0), 0.20, 0.08, 0.0, 1.0), inner,
              remap(nt, z, LAKE_Z + 0.05, LAKE_Z + 0.010, 0.0, 1.0),
              remap(nt, z, LAKE_Z - 0.004, LAKE_Z + 0.002, 0.0, 1.0),
              remap(nt, noise(nt, coord, 3.0, 2.0, 0.5), 0.52, 0.62, 0.0, 1.0))
    col = mix_color(nt, col, (0.62, 0.52, 0.10), mul(nt, sul, 0.85))
    # the lake's floor: dark, mineral
    col = mix_color(nt, col, (0.08, 0.12, 0.10),
                    mul(nt, inner, remap(nt, z, LAKE_Z - 0.002, LAKE_Z - 0.010, 0.0, 1.0)))
    # sand at the shore, black beside the delta
    black = attr(nt, "Black")
    sand_t = math_node(nt, "ADD", z, math_node(nt, "MULTIPLY", noise(nt, coord, 7.0, 2.0, 0.5), 0.010))
    sand = remap(nt, sand_t, SEA_Z + 0.026, SEA_Z + 0.013, 0.0, 1.0)
    sand_col = ramp(nt, fine, ((0.3, (0.38, 0.32, 0.24)), (0.7, (0.49, 0.42, 0.31))))
    sand_col = mix_color(nt, sand_col, ramp(nt, fine, ((0.3, (0.020, 0.019, 0.021)), (0.7, (0.050, 0.047, 0.050)))),
                         remap(nt, black, 0.0, 0.6, 0.0, 1.0))
    sand_col = mix_color(nt, sand_col, (0.10, 0.08, 0.06), remap(nt, z, SEA_Z + 0.007, SEA_Z + 0.001, 0.0, 0.6))
    sand_w = math_node(nt, "MAXIMUM", mul(nt, sand, remap(nt, nz, 0.72, 0.88, 0.0, 1.0)),
                       mul(nt, remap(nt, black, 0.2, 0.7, 0.0, 1.0),
                           remap(nt, z, SEA_Z + 0.05, SEA_Z + 0.025, 0.0, 1.0)))
    col = mix_color(nt, col, sand_col, sand_w)
    # under the sea: sand shoaling into weed, dark off the black beach
    col = mix_color(nt, col, mix_color(nt, (0.30, 0.30, 0.20), (0.06, 0.07, 0.06), black),
                    mul(nt, remap(nt, z, SEA_Z, SEA_Z - 0.004, 0.0, 1.0), math_node(nt, "SUBTRACT", 1.0, inner)))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, sand_w, 0.0, 1.0, 0.92, 0.70), bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    rough_rock = noise(nt, mapping(nt, coord, scale=(1.0, 1.0, 2.5)), 22.0, 4.0, 0.65)
    add_bump(nt, bsdf, math_node(nt, "ADD", mul(nt, fine, 0.6),
                                 mul(nt, math_node(nt, "SUBTRACT", rough_rock, mul(nt, crack, 1.5)), steep, cliffs, 0.8)),
             0.45, 0.004)
    return mat


def lava_material():
    mat, nt, bsdf, coord = surface("BasaltFlow")
    # Fresh aa: clinkery black basalt, a little blue-grey where the crust
    # catches the light, rust on the levees' older crust; the channel still
    # incandescent in a few thin cracks near the vent, black before the sea.
    chan = attr(nt, "Chan")
    flow = attr(nt, "Flow")
    clink = voronoi_node(nt, coord, 220.0)
    ctone = coord_xyz(nt, clink.outputs["Color"])["X"]
    col = ramp(nt, ctone, ((0.0, (0.016, 0.015, 0.017)), (0.6, (0.036, 0.034, 0.038)),
                           (1.0, (0.070, 0.066, 0.072))))
    col = mix_color(nt, col, (0.09, 0.09, 0.10), remap(nt, noise(nt, coord, 30.0, 3.0, 0.6), 0.60, 0.75, 0.0, 0.6))
    col = mix_color(nt, col, (0.14, 0.055, 0.03), mul(nt, remap(nt, chan, 0.4, 0.0, 0.0, 1.0),
                                                    remap(nt, noise(nt, coord, 12.0, 3.0, 0.6), 0.56, 0.70, 0.0, 0.55)))
    nt.links.new(col, bsdf.inputs["Base Color"])
    rough = remap(nt, clink.outputs["Distance"], 0.0, 0.5, 0.50, 0.90)
    nt.links.new(rough, bsdf.inputs["Roughness"])
    # the cracks: a Voronoi network warped by noise, so none run straight
    vec = nt.nodes.new("ShaderNodeVectorMath")
    vec.operation = "ADD"
    nt.links.new(coord, vec.inputs[0])
    nt.links.new(mul(nt, noise(nt, coord, 9.0, 4.0, 0.65), 0.10), vec.inputs[1])
    cracks = voronoi(nt, vec.outputs["Vector"], 55.0, "DISTANCE_TO_EDGE")
    # each crack open only here and there, wider where it is open
    open_ = remap(nt, noise(nt, coord, 22.0, 3.0, 0.6), 0.50, 0.66, 0.0, 1.0)
    glow = mul(nt, remap(nt, cracks, 0.030, 0.004, 0.0, 1.0), open_, remap(nt, chan, 0.45, 0.95, 0.0, 1.0),
               remap(nt, flow, 0.42, 0.06, 0.0, 1.0))
    nt.links.new(ramp(nt, glow, ((0.0, (0.0, 0.0, 0.0)), (0.45, (0.70, 0.07, 0.005)), (1.0, (1.0, 0.30, 0.03)))),
                 bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 5.0
    add_bump(nt, bsdf, math_node(nt, "ADD", clink.outputs["Distance"],
                                 mul(nt, noise(nt, coord, 70.0, 4.0, 0.7), 0.8)), 0.8, 0.003)
    return mat


def sea_material():
    mat, nt, bsdf, coord = surface("SeaWater")
    depth = remap(nt, attr(nt, "Depth"), 0.0, 0.060, 0.0, 1.0)
    col = ramp(nt, depth, ((0.00, (0.17, 0.52, 0.52)), (0.12, (0.06, 0.40, 0.46)),
                           (0.35, (0.020, 0.22, 0.34)), (0.70, (0.010, 0.10, 0.23)),
                           (1.00, (0.006, 0.055, 0.15))))
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
    col = mix_color(nt, (0.17, 0.52, 0.52), (0.88, 0.91, 0.89), amount)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    add_bump(nt, bsdf, lace, 0.3, 0.002)
    return mat


def lake_material():
    mat, nt, bsdf, coord = surface("CraterLake")
    # a deep crater lake: green-teal over the shelf at its edge, deep blue
    # within a few metres of the shore
    depth = remap(nt, attr(nt, "Depth"), 0.0, 0.030, 0.0, 1.0)
    col = ramp(nt, depth, ((0.00, (0.040, 0.16, 0.18)), (0.18, (0.020, 0.12, 0.19)),
                           (0.50, (0.008, 0.075, 0.17)), (1.00, (0.004, 0.040, 0.12))))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.22
    bsdf.inputs["IOR"].default_value = 1.33
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    add_bump(nt, bsdf, noise(nt, mapping(nt, coord, scale=(1.0, 1.4, 1.0)), 34.0, 3.0, 0.5), 0.08, 0.002)
    return mat


def rock_material():
    mat, nt, bsdf, coord = surface("Basalt")
    # vesicular basalt: near-black per stone, some rusted red, pale lichen
    # on the tops, dark in the cracks
    tone = attr(nt, "Tone")
    nz = normal_xyz(nt)["Z"]
    col = ramp(nt, tone, ((0.0, (0.06, 0.055, 0.055)), (0.45, (0.12, 0.11, 0.105)),
                          (0.75, (0.20, 0.18, 0.165)), (1.0, (0.28, 0.12, 0.07))))
    speck = noise(nt, coord, 180.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.025, 0.022, 0.022), remap(nt, speck, 0.58, 0.70, 0.0, 0.8))
    lich = mul(nt, remap(nt, voronoi(nt, coord, 30.0), 0.18, 0.08, 0.0, 1.0), remap(nt, nz, 0.3, 0.8, 0.0, 1.0),
               remap(nt, noise(nt, coord, 5.0, 2.0, 0.5), 0.52, 0.62, 0.0, 1.0))
    col = mix_color(nt, col, (0.50, 0.50, 0.40), mul(nt, lich, 0.7))
    col = mix_color(nt, col, (0.02, 0.02, 0.02), remap(nt, nz, -0.2, -0.8, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.80
    add_bump(nt, bsdf, math_node(nt, "ADD", speck, mul(nt, noise(nt, coord, 12.0, 4.0, 0.6), 1.5)), 0.5, 0.003)
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
    # conifers (tone under 0.5) dark blue-green, broadleaf lush and bright,
    # a few in flower; leafy clumps by Voronoi
    tone = attr(nt, "Tone")
    nz = normal_xyz(nt)["Z"]
    col = ramp(nt, tone, ((0.00, (0.020, 0.075, 0.040)), (0.25, (0.030, 0.105, 0.050)),
                          (0.45, (0.045, 0.125, 0.060)), (0.55, (0.08, 0.26, 0.04)),
                          (0.78, (0.16, 0.36, 0.05)), (0.92, (0.26, 0.42, 0.06)),
                          (0.96, (0.60, 0.20, 0.10)), (1.0, (0.70, 0.30, 0.12))))
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
    # island's ground in section, beds of ash, tuff and basalt
    xyz = coord_xyz(nt, coord)
    z = xyz["Z"]
    nz = normal_xyz(nt)["Z"]
    bands = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", z, math_node(nt, "MULTIPLY", noise(nt, coord, 6.0, 2.0, 0.5), 0.012)), 18.0), 0.0)
    soil = ramp(nt, bands, ((0.0, (0.10, 0.09, 0.085)), (0.35, (0.24, 0.20, 0.16)),
                            (0.55, (0.08, 0.07, 0.07)), (0.80, (0.36, 0.30, 0.22)), (1.0, (0.16, 0.10, 0.07))))
    pebbles = voronoi_node(nt, coord, 60.0)
    soil = mix_color(nt, soil, (0.05, 0.045, 0.045), remap(nt, pebbles.outputs["Distance"], 0.18, 0.10, 0.0, 0.8))
    soil = mix_color(nt, soil, (0.06, 0.09, 0.03), remap(nt, z, RIM_Z - 0.030, RIM_Z - 0.008, 0.0, 1.0))
    soil = mix_color(nt, soil, (0.05, 0.04, 0.035), remap(nt, z, 0.030, 0.0, 0.0, 0.7))
    slate = ramp(nt, noise(nt, coord, 30.0, 3.0, 0.5), ((0.3, (0.050, 0.055, 0.060)), (0.7, (0.10, 0.105, 0.11))))
    col = mix_color(nt, soil, slate, remap(nt, nz, 0.30, 0.60, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, nz, 0.3, 0.6, 0.90, 0.55), bsdf.inputs["Roughness"])
    add_bump(nt, bsdf, pebbles.outputs["Distance"], 0.3, 0.003)
    return mat


def piece_materials():
    """Nine slots, in index order: shared by the check and the render."""
    return (terrain_material(), lava_material(), sea_material(), foam_material(), lake_material(),
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

    return {"groups": groups, "all": all_, "tile": of(P_TILE), "sea": of(P_SEA), "lake": of(P_LAKE),
            "lava": of(P_LAVA), "foam": of(P_FOAM), "rocks": of(P_ROCK), "trunks": of(P_TRUNK),
            "crowns": of(P_CROWN)}


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 12.0)), Vector((0.0, 0.0, -1.0)), 30.0)
    return None if loc is None else loc.z


def edge_audit(me, cls):
    """The skirt's top vertices: their distance off the tile's circle and
    off the canonical edge height."""
    tile = cls["tile"][0]
    cap = face_vals(me, "Cap")
    rim = set()
    for p in tile.polys:
        if cap[p.index] == 3:
            rim.update(v for v in p.vertices if me.vertices[v].co.z > 1e-4)
    off = max(abs(math.hypot(me.vertices[v].co.x, me.vertices[v].co.y) - TILE_R) for v in rim)
    canon = max(abs(me.vertices[v].co.z - (RIM_Z - CHAMFER)) for v in rim)
    return off, canon, len(rim)


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


def rim_audit(me, cls, n=180):
    """Round the caldera, the ground's crest on every bearing out from its
    centre: the lowest of those crests (the pass the lake would spill
    through) against the lake's surface; and the lake's surface's spread
    and median."""
    tile = cls["tile"][0]
    lake = cls["lake"][0]
    _t, verts, _r = water_top(me, lake)
    zs = sorted(me.vertices[v].co.z for v in verts)
    med = zs[len(zs) // 2]
    spread = zs[-1] - zs[0]
    crests = []
    for k in range(n):
        th = TAU * k / n
        best = -9.0
        r = 0.12
        while r < 0.62:
            g = ray_down(tile.tree, VOLC_C[0] + r * math.cos(th), VOLC_C[1] + r * math.sin(th))
            if g is not None:
                best = max(best, g)
            r += 0.003
        crests.append((best, math.degrees(th)))
    saddle = min(crests)
    return saddle[0] - zs[-1], saddle[1], spread, med


def cone_audit(me, cls, n=36):
    """The cinder cone off the shipped ground: per bearing out from its
    nominal centre, the crater's crest (the highest point) and the base
    (where the flank comes down to the lake); the offset between the two
    rings' centres; and per bearing the flank's slope between a quarter and
    seven eighths of the way from the crest to the base."""
    tile = cls["tile"][0]
    lake_z = LAKE_Z
    crest, foot, slopes = [], [], []
    rb = 0.5 * CONE_W
    for k in range(n):
        th = TAU * k / n
        c, s = math.cos(th), math.sin(th)
        prof = []
        r = 0.0
        while r < rb + 0.05:
            g = ray_down(tile.tree, CONE_C[0] + r * c, CONE_C[1] + r * s)
            prof.append((r, -9.0 if g is None else g))
            r += 0.0015
        rc, zc = max(prof, key=lambda q: q[1])
        crest.append((CONE_C[0] + rc * c, CONE_C[1] + rc * s))
        rf = None
        for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
            if r0 > rc and z0 >= lake_z > z1:
                rf = r0 + (r1 - r0) * (z0 - lake_z) / (z0 - z1)
                break
        if rf is None:
            rf = rb + 0.05
        foot.append((CONE_C[0] + rf * c, CONE_C[1] + rf * s))
        r1 = CRATER_R + 0.25 * (rb - CRATER_R)
        r2 = CRATER_R + 0.875 * (rb - CRATER_R)
        z1 = ray_down(tile.tree, CONE_C[0] + r1 * c, CONE_C[1] + r1 * s) or 0.0
        z2 = ray_down(tile.tree, CONE_C[0] + r2 * c, CONE_C[1] + r2 * s) or 0.0
        slopes.append(math.degrees(math.atan2(z1 - z2, r2 - r1)))
    cx = sum(p[0] for p in crest) / n
    cy = sum(p[1] for p in crest) / n
    fx = sum(p[0] for p in foot) / n
    fy = sum(p[1] for p in foot) / n
    return math.hypot(cx - fx, cy - fy), min(slopes), max(slopes), slopes


def flow_audit(me, cls):
    """Along the flow's centre lane, its surface row by row: the largest
    rise from one row to the next, and how far its last row lies under the
    sea; across each row, the lower of its two levee crests over the
    channel's centre."""
    ring = vert_vals(me, "Ring")
    lane = vert_vals(me, "Lane")
    lava = cls["lava"][0]
    rows = {}
    for v in lava.verts:
        if lane[v] in (1, 4, 7):
            rows.setdefault(ring[v], {})[lane[v]] = me.vertices[v].co.z
    keys = sorted(rows)
    zs = [rows[k][4] for k in keys]
    rise = max(b - a for a, b in zip(zs, zs[1:]))
    levee = min(min(rows[k][1], rows[k][7]) - rows[k][4] for k in keys)
    return rise, zs[-1] - SEA_Z, levee, len(zs), zs[0] - zs[-1]


def water_audit(me, cls):
    """The sea's top: median height and largest excursion from it."""
    sea = cls["sea"][0]
    _top, verts, _rim = water_top(me, sea)
    zs = sorted(me.vertices[v].co.z for v in verts)
    med = zs[len(zs) // 2]
    exc = max(abs(z - med) for z in zs)
    return med, exc


def enclose_audit(me, cls):
    """Over every rim vertex and rim-edge midpoint of the sea's and the
    lake's tops, the ground (or, for the sea, the lava over its shoreward
    rim beside the delta); under every corner of the flow's foot, the
    ground over it."""
    tile = cls["tile"][0]
    lava = cls["lava"][0]
    worst = {"sea": 9.0, "lake": 9.0, "lava": 9.0}
    n = 0
    covered = 0
    for key in ("sea", "lake"):
        for s in cls[key]:
            _t, _v, rim = water_top(me, s)
            for a, b in rim:
                pa, pb = me.vertices[a].co, me.vertices[b].co
                for p in (pa, (pa + pb) * 0.5):
                    n += 1
                    g = ray_down(tile.tree, p.x, p.y)
                    d = -9.0 if g is None else g - p.z
                    if d < ENCLOSE_MIN and key == "sea":
                        rz = ray_down(lava.tree, p.x, p.y)
                        if rz is not None and rz > p.z + ENCLOSE_MIN:
                            covered += 1
                            continue
                    worst[key] = min(worst[key], d)
    lane = vert_vals(me, "Lane")
    for v in lava.verts:
        if lane[v] != -1:
            continue
        p = me.vertices[v].co
        n += 1
        g = ray_down(tile.tree, p.x, p.y)
        worst["lava"] = min(worst["lava"], -9.0 if g is None else g - p.z)
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
    img = bpy.data.images.new("CalderaNrm", size, size, alpha=True, float_buffer=False)
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
    low = build_mesh("CalderaIslandLow", T, plan, "low", **flags)
    high = build_mesh("CalderaIslandHigh", T, plan, "high", **flags)
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
    if (len(cls["tile"]) != 1 or len(cls["sea"]) != 1 or len(cls["lava"]) != 1
            or len(cls["lake"]) != 1 or len(cls["foam"]) != 1):
        return (fail(f"tile/sea/lava/lake/foam not found: {len(cls['tile'])}/{len(cls['sea'])}/"
                     f"{len(cls['lava'])}/{len(cls['lake'])}/{len(cls['foam'])}", 3),) + none2
    e_off, e_canon, e_n = edge_audit(low.data, cls)
    r_free, r_th, l_spread, l_med = rim_audit(low.data, cls)
    c_off, c_lo, c_hi, _slopes = cone_audit(low.data, cls)
    f_rise, f_toe, f_levee, f_rows, f_drop = flow_audit(low.data, cls)
    w_med, w_exc = water_audit(low.data, cls)
    enclose, n_rim, n_cov = enclose_audit(low.data, cls)
    foam_dev, foam_tuck, n_foam = foam_audit(low.data, cls)
    rest, pairs, n_rocks = rock_audit(cls)
    roots = tree_audit(low.data, cls)

    img, tex = setup_bake_image(low, bake_mat)
    if img is None:
        return (fail("no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "CalderaIslandLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "CalderaIslandLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(build_collider_source(T), "CalderaIslandCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_caldera_island_tile_{os.getpid()}.glb")
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
    print(f"measured edge off={e_off:.6f} canon={e_canon:.6f} n={e_n}")
    print(f"measured caldera saddle_over_lake={r_free:.4f} at={r_th:.1f}deg lake_spread={l_spread:.6f} "
          f"lake_median={l_med:.5f} lake_level={LAKE_Z:.3f}")
    print(f"measured cone coax={c_off:.5f} slope={c_lo:.2f}..{c_hi:.2f}deg")
    print(f"measured flow rise={f_rise:.6f} toe={f_toe:.5f} levee_min={f_levee:.5f} rows={f_rows} "
          f"drop={f_drop:.4f} s_cross={T.s_cross:.3f} len={T.length:.3f}")
    print(f"measured water median={w_med:.5f} excursion={w_exc:.5f} enclose="
          f"{ {k: round(v, 5) for k, v in enclose.items()} } n={n_rim} under_lava={n_cov}")
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
    if e_off > EDGE_TOL or e_canon > EDGE_TOL:
        return (fail(f"edge: rim {e_off:.5f} m off the circle, {e_canon:.5f} m off the canonical "
                     f"edge height {RIM_Z - CHAMFER:.3f} (max {EDGE_TOL})", 17),) + none2
    if r_free < RIM_FREE:
        return (fail(f"caldera: its rim's lowest pass ({r_th:.0f} deg) only {r_free:.4f} m over the lake "
                     f"(min {RIM_FREE}): the lake would spill", 18),) + none2
    if l_spread > LAKE_FLAT or abs(l_med - LAKE_Z) > LEVEL_EPS:
        return (fail(f"lake: surface spread {l_spread:.5f} m (flat within {LAKE_FLAT}), median {l_med:.5f} "
                     f"(level {LAKE_Z:.3f})", 19),) + none2
    if c_off > COAX_TOL:
        return (fail(f"cinder cone: crater crest {c_off:.4f} m off its base's axis (max {COAX_TOL})", 20),) + none2
    if c_lo < REPOSE[0] or c_hi > REPOSE[1]:
        return (fail(f"cinder cone: flanks {c_lo:.1f}..{c_hi:.1f} deg outside the repose band {REPOSE}",
                     21),) + none2
    if f_rise > DRAIN_EPS:
        return (fail(f"lava: rises {f_rise:.5f} m between rows (max {DRAIN_EPS})", 22),) + none2
    if f_levee < LEVEE_MIN:
        return (fail(f"lava: a levee crest only {f_levee:.4f} m over the channel (min {LEVEE_MIN}): "
                     f"it would spill", 23),) + none2
    if f_toe > -TOE_MIN:
        return (fail(f"lava: its toe {f_toe:.4f} m against the sea (at least {TOE_MIN} under)", 24),) + none2
    if abs(w_med - SEA_Z) > LEVEL_EPS or not (RIPPLE_BAND[0] <= w_exc <= RIPPLE_BAND[1]):
        return (fail(f"sea: median {w_med:.5f} m (level {SEA_Z} +- {LEVEL_EPS}), ripple {w_exc:.5f} m "
                     f"(band {RIPPLE_BAND})", 25),) + none2
    if enclose["sea"] < ENCLOSE_MIN or enclose["lake"] < ENCLOSE_MIN or enclose["lava"] < SEAT_MIN:
        return (fail(f"water not contained or lava not seated: ground over the rims and the flow's foot "
                     f"{enclose} (min {ENCLOSE_MIN}, lava {SEAT_MIN})", 26),) + none2
    if n_foam != 1 or foam_dev > FOAM_BAND or foam_tuck < FOAM_TUCK:
        return (fail(f"foam: {n_foam}/1 lines, {foam_dev:.5f} m off the waterline (max {FOAM_BAND}), "
                     f"land edge {foam_tuck:.5f} m under the shore (min {FOAM_TUCK})", 27),) + none2
    n_want = len(plan["rocks"])
    if n_rocks != n_want or min(rest) < PERCH_BAND:
        return (fail(f"rocks: {n_rocks}/{n_want}, worst sector {min(rest):.4f} m under the ground "
                     f"(min {PERCH_BAND})", 28),) + none2
    if pairs:
        return (fail(f"rocks: {pairs} pairs overlap", 29),) + none2
    if len(roots) != len(plan["trees"]) or min(roots) < ROOT_BAND[0] or max(roots) > ROOT_BAND[1]:
        return (fail(f"trees: {len(roots)}/{len(plan['trees'])} trunks, feet {min(roots):.4f}..{max(roots):.4f} "
                     f"m under the ground (band {ROOT_BAND})", 30),) + none2
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 31),) + none2
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

    # Key high on the left so the cone throws its shadow down the right
    # flank and the caldera's far wall is lit; fill, rim, and the warm
    # wedge. The camera looks down on the tile as on a game board, so the
    # floor behind it is the backdrop: the wedge drops a warm pool on it,
    # off to the left where it reaches no water to glare off.
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


FLAG_NAMES = ("warp_edge", "breach_rim", "tilt_lake", "skew_crater", "steep_cone", "uphill_flow",
              "breach_levee", "short_flow", "flat_sea", "short_sea", "lift_foam", "perch_rock",
              "pile_rocks", "float_trees")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--warp-edge", action="store_true")
    p.add_argument("--breach-rim", action="store_true")
    p.add_argument("--tilt-lake", action="store_true")
    p.add_argument("--skew-crater", action="store_true")
    p.add_argument("--steep-cone", action="store_true")
    p.add_argument("--uphill-flow", action="store_true")
    p.add_argument("--breach-levee", action="store_true")
    p.add_argument("--short-flow", action="store_true")
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
    print("caldera-island-tile OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
