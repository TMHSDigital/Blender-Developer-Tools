"""Game-ready sea stack and arch — a showcase piece, not an example.

Asserts budget conformance of a procedural coastal diorama tile after
composing shipped pipeline pieces: bmesh construction, UVs, eight
materials, high-to-low normal bake, LOD chain, convex hull colliders,
Unity glTF export.

A fragment of a bedded sandstone headland stands on a wave-cut rock
platform. Hard sandstone beds alternate with thin soft ones; the soft beds
are undercut, so every hard bed projects as a ledge, and vertical joints
split each bed into blocks that stand proud by their own amounts. The sea
has cut an arch through the fin: two legs of stepped beds carry a lintel of
hard beds whose lowest bed bites both of them, and the channel runs under
it. A smaller sea stack of the same beds stands on its own low island in
the bay. The sea is a rippled sheet at a declared level whose rim runs
under the platform all round, with a foam line seated at the waterline
round the bay and the island; two tide pools lie in the shelf. Fallen
blocks and rounded boulders rest on the platform, and the tops carry turf
with grass and sea thrift.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--gap-lintel`` every bed biting the
bed it lies on (the lintel on both legs), ``--lean-stack`` the stack's mass
over its footprint, ``--cut-pillar`` the legs and the stack sealed in the
platform, ``--close-arch`` the clear aperture, ``--tilt-beds`` the bedding
level and continuous, ``--flush-beds`` the soft beds recessed, ``--flat-sea``
the water level and ripple band, ``--short-sea`` the water contained,
``--lift-foam`` the foam seated at the waterline, ``--perch-talus`` the
loose rocks sealed on the platform, ``--pile-talus`` the loose rocks apart,
``--float-cover`` the cover rooted in the tops.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python sea_stack_arch.py --
    blender --background --python sea_stack_arch.py -- --skip-decimate
    blender --background --python sea_stack_arch.py -- --output arch.png
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

SEED = 5903
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- The tile: a wave-cut platform with a bay, a channel and an island --------
TILE_C = (0.02, -0.02)
TILE_A = (1.26, 0.96)     # half-axes before the wobble, m
TILE_N = {"low": 72, "high": 96}
TILE_EDGE = 0.10          # the rim rolls down over this fraction of the radius
WATER_LEVEL = 0.105
SHELF_Z = 0.172           # the platform's top, before its swells and rise
SEABED_Z = 0.032
ISLE_Z = 0.148            # the stack's island
RAMP_LAND = 0.16          # the shore climbs from the waterline to the shelf over this
RAMP_SEA = 0.14
RAMP_ISLE = 0.075
BAY_C = (0.10, -0.34)
BAY_A = (0.70, 0.38)
CHANNEL = ((-0.20, -0.34), (-0.20, 0.60), 0.115)   # under the arch: a capsule
SEA_K = 0.14              # the bay and the channel meet on this fillet
SEA_C = (-0.20, -0.30)    # the water sheet's polar centre (inside bay and channel)
ISLE_C = (0.42, -0.32)
ISLE_R = 0.22
# tide pools: centre, radius, depth
POOLS = (((-0.86, -0.30), 0.115, 0.034), ((0.84, 0.30), 0.095, 0.030))
POOL_RAMP = 0.05
POOL_FREE = 0.012         # a pool's level this far under the lowest point of its rim
WATER_MARGIN = 0.05       # the sea's rim runs this far past the shoreline, under the shelf
WATER_SLAB = 0.030
POOL_SLAB = 0.010
WATER_N = 44
POOL_N = 10
RIPPLE_AMP = 0.0024
CALM_W = 0.07             # ripples die out over this width off the shore
FOAM_N = 260
ISLE_FOAM_N = 110
FOAM_IN = 0.030           # the foam's land edge this far inland, under the rock
FOAM_OUT = (0.016, 0.050)
FOAM_T = 0.0035           # half its thickness

# --- The beds ---------------------------------------------------------------
# Bed boundaries (m) from the top of the lowest bed up; layer k lies between
# BOUNDS[k - 1] and BOUNDS[k]; layer 0 runs down into the platform. Hard beds
# of uneven thickness, thin soft beds between them.
BOUNDS = (0.270, 0.410, 0.465, 0.530, 0.552, 0.712, 0.758, 0.800, 0.842, 1.010, 1.030, 1.104,
          1.160, 1.300, 1.322, 1.392)
HARD = tuple(k % 2 for k in range(len(BOUNDS)))
CH = 0.0035               # a hard bed's weathered arris
# a hard bed's profile: (height fraction, arris fraction)
HARD_PROFILE = ((0.0, 1.0), (0.05, 0.3), (0.15, 0.0), (0.85, 0.0), (0.95, 0.3), (1.0, 1.0))
NOTCH = 0.030             # a soft bed recessed this far behind the hard beds either side
NOTCH_END = 0.022         # its end rings at least this far inside them
NOTCH_FOOT = 0.050        # the wave-cut notch at a leg's foot
BITE = 0.012              # a soft bed runs this far into the hard beds either side
EMBED = 0.030             # the lowest bed's foot this far under the platform all round
JW = 0.026                # a joint's V half-width at the face
FACETS = 7                # fracture planes round each hard bed
FALLEN_P = 0.14           # the chance a block has fallen out of a hard bed
# bodies: centre, half-extents, squareness, yaw, samples, layers, joints (x or
# offset along the long axis, angle deg)
# joints: a point and a bearing in plan (the stack's in its own frame)
BODIES = {
    "A": {"id": 1, "x": (-1.25, -0.33), "centre": (-0.66, 0.34), "M": 110,
          "layers": range(0, 9),
          "joints": ((-0.89, 0.34, 93.0), (-0.75, 0.34, 86.0), (-0.61, 0.34, 95.0), (-0.49, 0.34, 88.0),
                     (-0.66, 0.33, 2.0))},
    "B": {"id": 2, "x": (-0.07, 0.60), "centre": (0.19, 0.34), "M": 90,
          "layers": range(0, 9), "joints": ((0.04, 0.34, 92.0), (0.19, 0.34, 97.0), (0.13, 0.36, -3.0))},
    "L": {"id": 3, "x": (-1.25, 0.60), "centre": (-0.33, 0.34), "M": 170,
          "layers": range(9, 16),
          "joints": ((-0.86, 0.34, 88.0), (-0.66, 0.34, 93.0), (-0.46, 0.34, 86.0), (-0.21, 0.34, 91.0),
                     (0.02, 0.34, 94.0), (0.19, 0.34, 86.0))},
    "S": {"id": 4, "c": ISLE_C, "h": (0.185, 0.16), "p": 3.2, "yaw": 25.0, "M": 76,
          "layers": range(0, 12), "joints": ((-0.06, 0.0, 98.0), (0.07, 0.0, 84.0), (0.0, 0.01, 4.0))},
}
BODY_ORDER = ("A", "B", "L", "S")
# the fin's joint faces, shared by both legs and the lintel: outward bearing
# (deg) and a point on the face
FIN_FACES = ((-90.0, (-0.20, 0.115)), (-99.0, (-0.80, 0.122)), (-83.0, (0.20, 0.118)),
             (90.0, (-0.30, 0.565)), (97.0, (-0.75, 0.558)), (84.0, (0.15, 0.560)),
             (180.0, (-0.99, 0.34)), (213.0, (-0.93, 0.17)), (142.0, (-0.94, 0.52)),
             (0.0, (0.345, 0.34)), (-35.0, (0.29, 0.16)), (38.0, (0.30, 0.52)))
# per hard bed: a taper and cut planes (normal, limit): P . n <= limit. The
# legs step in toward the opening bed by bed; the lintel steps down seaward.
LAYER_SHAPE = {
    ("A", 1): (0.010, (((1.0, 0.0), -0.45),)),
    ("A", 3): (0.006, (((1.0, 0.0), -0.43),)),
    ("A", 5): (0.002, (((1.0, 0.0), -0.38),)),
    ("A", 7): (-0.004, ()),
    ("B", 1): (0.008, (((-1.0, 0.0), -0.05),)),
    ("B", 3): (0.004, (((-1.0, 0.0), -0.03),)),
    ("B", 5): (0.000, (((-1.0, 0.0), 0.02),)),
    ("B", 7): (-0.004, ()),
    ("L", 9): (0.004, ()),
    ("L", 11): (-0.002, ()),
    ("L", 13): (-0.008, (((1.0, 0.0), 0.22),)),
    ("L", 15): (-0.016, (((1.0, 0.0), 0.00), ((-1.0, 0.0), 0.95))),
    ("S", 1): (0.012, ()),
    ("S", 3): (0.006, ()),
    ("S", 5): (0.000, ()),
    ("S", 7): (-0.008, ()),
    ("S", 9): (-0.004, ()),
    ("S", 11): (-0.014, ()),
}
LINTEL_LAYER = 9
APER_X = -0.20            # the opening's design centre line
TILT_X0 = -0.33           # --tilt-beds turns the beds about this line

# --- Loose rock ---------------------------------------------------------------
# fallen blocks: plan centre, length, width, height
TALUS = ((-0.80, -0.04, 0.26, 0.17, 0.12), (-0.57, -0.02, 0.15, 0.12, 0.09),
         (0.57, 0.23, 0.20, 0.14, 0.10), (0.66, -0.20, 0.10, 0.08, 0.06),
         (-0.40, 0.73, 0.18, 0.13, 0.09))
TALUS_M = 28
# rounded boulders: plan centre, radius
BOULDERS = ((-0.47, -0.13, 0.050), (0.07, 0.01, 0.042), (0.78, -0.04, 0.048),
            (-0.97, -0.12, 0.040), (0.28, -0.20, 0.034), (-0.70, -0.47, 0.044),
            (0.30, -0.47, 0.030), (-0.30, 0.02, 0.036))
ROCK_GAP = 0.020          # loose rocks held apart by this beyond their radius bounds
REST_SINK = 0.005         # every sector's most-buried vertex this far under the platform

# --- Cover --------------------------------------------------------------------
TURF_IN = 0.030           # the turf's rim this far inside the top bed's edge
TURF_H = 0.030
TURF_RINGS = 7
TURF_BITE = 0.016
TUFTS = {"L": 30, "S": 7}
THRIFT = {"L": 10, "S": 3}
COVER_SPACING = {"L": 0.062, "S": 0.055}
COVER_F = {"L": (0.10, 0.72), "S": (0.10, 0.58)}   # a clump's reach toward the turf's rim
ROOT_D = 0.034            # a blade or stalk starts this far under the turf's top, in the stone

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (2.5440, 1.9225, 1.6184)
BASE_TRIS_MIN = 77600
BASE_TRIS_MAX = 78800
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 8
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 380
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# face floors: rock, shelf, water, foam, cobble, turf, grass, thrift
FACE_FLOORS = (43000, 10300, 4600, 1430, 830, 3800, 4990, 1200)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Beds bite: every soft bed's end ring inside the hard bed it runs into
BED_BITE = (0.002, 0.040)
GAP_LINTEL = 0.015        # --gap-lintel stops one leg's top bed this far under the lintel
# Stack: its mass centre inside its notch's footprint
TIP_MIN = 0.050
LEAN = 0.30               # --lean-stack shears the stack this far per metre of height
LEAN_DIR = (0.30, -0.954)
# Sealed: every sector's most-buried foot vertex under the platform
SECTORS = 8
FLANK_R = 0.90
SEAL_EPS = 0.020
CUT_PILLAR = 0.020        # --cut-pillar stops a leg's foot this far over the platform
# Aperture: rays through the opening along +Y
APER_W_MIN = 0.20
APER_H_MIN = 0.60
CLOSE_ARCH = 0.22         # --close-arch brings a leg this far into the opening
# Bedding: every hard bed's top level within a tilt band, each layer continuous
TILT_MAX_DEG = 0.8
LEVEL_TOL = 0.004
TILT_BEDS_DEG = 2.5
# Notch: the soft beds recessed behind the hard beds by a band
NOTCH_BAND = (0.008, 0.090)
FLUSH_NOTCH = 0.0055
# Water: level and ripple
LEVEL_EPS = 0.0015
RIPPLE_BAND = (0.0015, 0.0090)
POOL_FLAT = 0.0005
ENCLOSE_MIN = 0.008
SHORT_SEA = -0.05         # --short-sea stops the rim this far short of the shoreline
# Foam: at the waterline, its land edge under the rock
FOAM_BAND = 0.006
FOAM_TUCK = 0.004
LIFT_FOAM = 0.020
# Loose rock: sealed all round, and apart
PERCH_BAND = 0.003
# Cover: rooted in the turf or the top bed
ROOT_BAND = (0.004, 0.060)
FLOAT_COVER = 0.050
# Hero yaw about Z only (level on the stage).
HERO_YAW_DEG = 0.0
WALL_Y = 4.2

ROCK_IDX = 0
SHELF_IDX = 1
WATER_IDX = 2
FOAM_IDX = 3
COBBLE_IDX = 4
TURF_IDX = 5
GRASS_IDX = 6
THRIFT_IDX = 7
MAT_LABELS = ("rock", "shelf", "water", "foam", "cobble", "turf", "grass", "thrift")

# part tags, one per face, so the audits can name a shell's role
P_TILE, P_BED, P_SEA, P_POOL, P_FOAM, P_TALUS, P_BOULDER = 1, 2, 3, 4, 5, 6, 7
P_TURF, P_BLADE, P_STALK, P_HEAD = 8, 9, 10, 11
COVER_PARTS = (P_BLADE, P_STALK, P_HEAD)


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
    if k <= 0.0:
        return min(a, b)
    h = max(k - abs(a - b), 0.0) / k
    return min(a, b) - h * h * k * 0.25


def ease(t):
    t = min(max(t, 0.0), 1.0)
    return 1.0 - (1.0 - t) * (1.0 - t)


def hash01(a, b, c):
    """A closed-form draw in [0, 1) from three indices."""
    x = math.sin(a * 12.9898 + b * 78.233 + c * 37.719 + SEED * 0.0137) * 43758.5453
    return x - math.floor(x)


def perp_basis(d):
    ref = UP if abs(d.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = d.cross(ref).normalized()
    return e1, d.cross(e1).normalized()


def rotz(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


# --------------------------------------------------------------------------
# The ground as a function of plan position
# --------------------------------------------------------------------------

def disc_wobble(th):
    return (1.0 + 0.035 * math.sin(3.0 * th + 0.7) + 0.02 * math.sin(5.0 * th + 2.1)
            + 0.012 * math.sin(9.0 * th + 0.3))


def disc_frac(x, y):
    """How far out (x, y) lies on the tile, 1 at the rim."""
    x, y = x - TILE_C[0], y - TILE_C[1]
    th = math.atan2(y / TILE_A[1], x / TILE_A[0])
    return math.hypot(x / TILE_A[0], y / TILE_A[1]) / disc_wobble(th)


def ellipse_sdf(px, py, ax, ay):
    k0 = math.hypot(px / ax, py / ay)
    k1 = math.hypot(px / (ax * ax), py / (ay * ay))
    if k1 < 1e-9:
        return -min(ax, ay)
    return k0 * (k0 - 1.0) / k1


def capsule_sdf(px, py, a, b, r):
    bx, by = b[0] - a[0], b[1] - a[1]
    qx, qy = px - a[0], py - a[1]
    h = min(max((qx * bx + qy * by) / (bx * bx + by * by), 0.0), 1.0)
    return math.hypot(qx - bx * h, qy - by * h) - r


def sea_sdf(x, y):
    """Signed distance to the bay-and-channel shoreline, negative in the sea."""
    qx, qy = x - BAY_C[0], y - BAY_C[1]
    th = math.atan2(qy / BAY_A[1], qx / BAY_A[0])
    d1 = ellipse_sdf(qx, qy, BAY_A[0], BAY_A[1])
    d1 += 0.026 * math.sin(3.0 * th + 0.6) + 0.016 * math.sin(7.0 * th + 2.3) \
        + 0.008 * math.sin(13.0 * th + 1.1) + 0.004 * math.sin(23.0 * th + 0.4)
    a, b, r = CHANNEL
    d2 = capsule_sdf(x, y, a, b, r + 0.016 * math.sin(9.0 * y + 0.7) + 0.006 * math.sin(23.0 * y))
    return smin(d1, d2, SEA_K)


def isle_radius(phi):
    return ISLE_R * (1.0 + 0.07 * math.sin(3.0 * phi + 0.9) + 0.04 * math.sin(5.0 * phi + 2.6)
                     + 0.02 * math.sin(9.0 * phi + 0.4))


def isle_sdf(x, y):
    dx, dy = x - ISLE_C[0], y - ISLE_C[1]
    return math.hypot(dx, dy) - isle_radius(math.atan2(dy, dx))


def pool_radius(i, phi):
    (_c, r, _d) = POOLS[i]
    return r * (1.0 + 0.10 * math.sin(3.0 * phi + 1.3 + i) + 0.05 * math.sin(5.0 * phi + 0.2 * i))


def pool_sdf(i, x, y):
    (c, _r, _d) = POOLS[i]
    dx, dy = x - c[0], y - c[1]
    return math.hypot(dx, dy) - pool_radius(i, math.atan2(dy, dx))


def land_dist(x, y):
    """Signed distance to the waterline, positive on land (the island is land)."""
    return max(sea_sdf(x, y), -isle_sdf(x, y))


def shelf_height(x, y):
    return (SHELF_Z + 0.009 * math.sin(2.3 * x + 0.4) * math.cos(1.9 * y + 1.2)
            + 0.005 * math.sin(5.1 * x - 3.7 * y + 0.8) + 0.018 * smoothstep(y, -0.15, 0.35))


def raw_height(x, y):
    ds = sea_sdf(x, y)
    di = -isle_sdf(x, y)
    if di > 0.0 and di >= ds:
        top = ISLE_Z + 0.004 * math.sin(11.0 * x + 3.0 * y)
        return WATER_LEVEL + (top - WATER_LEVEL) * ease(di / RAMP_ISLE)
    if ds >= 0.0:
        h = WATER_LEVEL + (shelf_height(x, y) - WATER_LEVEL) * ease(ds / RAMP_LAND)
        for i, (_c, _r, depth) in enumerate(POOLS):
            pd = pool_sdf(i, x, y)
            if pd < 0.0:
                h -= depth * ease(-pd / POOL_RAMP)
        return h
    d = max(ds, di)
    bed = SEABED_Z + 0.008 * math.sin(3.1 * x + 1.3) * math.cos(2.7 * y)
    return WATER_LEVEL - (WATER_LEVEL - bed) * ease(-d / RAMP_SEA)


def ground_height(x, y):
    return raw_height(x, y) * smoothstep(1.0 - disc_frac(x, y), 0.0, TILE_EDGE)


def pool_level(i, G):
    """Each pool lies this far under the lowest point of its rim, read off
    the built platform."""
    (c, _r, _d) = POOLS[i]
    low = 9.0
    for k in range(180):
        phi = TAU * k / 180
        r = pool_radius(i, phi)
        low = min(low, G.z(c[0] + r * math.cos(phi), c[1] + r * math.sin(phi)))
    return low - POOL_FREE


def ray_table(centre, sdf, level, rmax=1.6, n=1440):
    """Radius from ``centre`` along each of ``n`` bearings to the first point
    where ``sdf`` reaches ``level``."""
    out = []
    for k in range(n):
        th = TAU * k / n
        c, s = math.cos(th), math.sin(th)
        r0, r = 0.0, 0.004
        while r < rmax and sdf(centre[0] + c * r, centre[1] + s * r) < level:
            r0, r = r, r + 0.004
        lo, hi = r0, r
        for _ in range(24):
            mid = 0.5 * (lo + hi)
            if sdf(centre[0] + c * mid, centre[1] + s * mid) < level:
                lo = mid
            else:
                hi = mid
        out.append(0.5 * (lo + hi))
    return out


def table_at(table, th):
    n = len(table)
    x = (th % TAU) / TAU * n
    i = int(x) % n
    f = x - math.floor(x)
    return table[i] * (1.0 - f) + table[(i + 1) % n] * f


def ripple(plan, x, y):
    return RIPPLE_AMP * sum(a * math.sin(kx * x + ky * y + ph) for kx, ky, ph, a in plan["waves"])


def calm(x, y):
    return smoothstep(-land_dist(x, y), 0.01, CALM_W)


class Ground:
    """The built platform, sampled by a ray straight down, so everything
    seated on it sits on the faces actually shipped."""

    def __init__(self, tree):
        self.tree = tree

    def z(self, x, y):
        loc, _n, _i, _d = self.tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
        return 0.0 if loc is None else loc.z


# --------------------------------------------------------------------------
# Plan outlines: a body's base curve and each bed's offsets from it
# --------------------------------------------------------------------------

def resample_closed(pts, m):
    n = len(pts)
    seg = [math.hypot(pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1])
           for i in range(n)]
    total = sum(seg)
    out = []
    j, acc = 0, 0.0
    for k in range(m):
        target = total * k / m
        while acc + seg[j] < target:
            acc += seg[j]
            j += 1
        f = (target - acc) / seg[j] if seg[j] > 1e-12 else 0.0
        a, b = pts[j], pts[(j + 1) % n]
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


def resample_ring(pts, m):
    """Clipping folds whole runs of a ring onto a plane's corner; spread
    the ring's points evenly along the clipped outline again."""
    clean = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    if math.hypot(clean[0][0] - clean[-1][0], clean[0][1] - clean[-1][1]) <= 1e-6:
        clean.pop()
    return resample_closed(clean, m)


def superellipse(hx, hy, p, n=2048):
    pts = []
    for i in range(n):
        t = TAU * i / n
        c, s = math.cos(t), math.sin(t)
        pts.append((hx * math.copysign(abs(c) ** (2.0 / p), c),
                    hy * math.copysign(abs(s) ** (2.0 / p), s)))
    return pts


def outward_normals(P):
    n = len(P)
    out = []
    for i in range(n):
        a, b = P[i - 1], P[(i + 1) % n]
        tx, ty = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, ty)
        out.append((ty / ln, -tx / ln))
    return out


def clip_poly(poly, planes, shift=0.0):
    """Sutherland-Hodgman: the part of a plan polygon on the inner side of
    every plane (P . m <= h - shift). Joint faces and cuts are flat."""
    out = list(poly)
    for (mx, my), h in planes:
        lim = h - shift
        src, out = out, []
        n = len(src)
        for k in range(n):
            a, b = src[k], src[(k + 1) % n]
            da = a[0] * mx + a[1] * my - lim
            db = b[0] * mx + b[1] * my - lim
            if da <= 0.0:
                out.append(a)
            if (da < 0.0 < db) or (db < 0.0 < da):
                t = da / (da - db)
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        if len(out) < 3:
            return out
    return out


def ring_from(poly, centre, bearing, m):
    """Resample a closed polygon to ``m`` points evenly along its length,
    starting where the ray from ``centre`` on ``bearing`` leaves it, so every
    ring of a bed starts at the same place."""
    clean = [poly[0]]
    for p in poly[1:]:
        if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-7:
            clean.append(p)
    if math.hypot(clean[0][0] - clean[-1][0], clean[0][1] - clean[-1][1]) <= 1e-7:
        clean.pop()
    dx, dy = math.cos(bearing), math.sin(bearing)
    n = len(clean)
    best, start = None, 0
    for k in range(n):
        a, b = clean[k], clean[(k + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        wx, wy = a[0] - centre[0], a[1] - centre[1]
        t = (wx * ey - wy * ex) / den
        u = (wx * dy - wy * dx) / den
        if t > 0.0 and -1e-9 <= u <= 1.0 + 1e-9 and (best is None or t > best[0]):
            best = (t, k, (a[0] + ex * u, a[1] + ey * u))
    if best is not None:
        _t, k, hit = best
        start = k + 1
        clean = [hit] + clean[start:] + clean[:start]
    return resample_closed(clean, m)


def poly_normals(P):
    n = len(P)
    out = []
    for i in range(n):
        a, b = P[i - 1], P[(i + 1) % n]
        tx, ty = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, ty) or 1.0
        out.append((ty / ln, -tx / ln))
    return out


def planes_through(faces):
    out = []
    for ang, (px, py) in faces:
        m = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        out.append((m, px * m[0] + py * m[1]))
    return out


class Body:
    """A column of beds. Each bed's outline is the column's base cut by its
    joint faces (vertical planes shared by every bed; the fin's faces are
    shared by both legs and the lintel), each face set back by the bed's own
    retreat, then its blocks set back between the joints, each joint opened
    as a V. A soft bed lies ``NOTCH`` inside the hard beds either side."""

    def __init__(self, key, plan, M, close=0.0):
        spec = BODIES[key]
        self.key = key
        self.id = spec["id"]
        self.M = M
        self.close = close
        self.layers = list(spec["layers"])
        self.lp = plan["layers"]
        if key == "S":
            yaw = math.radians(spec["yaw"])
            cs, sn = math.cos(yaw), math.sin(yaw)
            hx, hy = spec["h"]
            local = resample_closed(superellipse(hx + 0.04, hy + 0.04, 2.6), 96)
            self.base = [(ISLE_C[0] + cs * x - sn * y, ISLE_C[1] + sn * x + cs * y) for x, y in local]
            self.faces = [(m, max(px * m[0] + py * m[1] for px, py in self.base) - d)
                          for m, d in ((((math.cos(a), math.sin(a))), d) for a, d in plan["stack_faces"])]
            self.centre = ISLE_C
            self.retreat_key = "stack_retreat"
        else:
            x0, x1 = spec["x"]
            if close:
                x0 -= close
            self.base = [(x0, -0.2), (x1, -0.2), (x1, 0.9), (x0, 0.9)]
            self.faces = planes_through(FIN_FACES)
            self.centre = spec["centre"]
            self.retreat_key = "fin_retreat"
        self.bearing = -0.5 * math.pi
        self._polys = {}
        self.joints = []
        if key == "S":
            for jx, jy, ang in spec["joints"]:
                p0 = (ISLE_C[0] + cs * jx - sn * jy, ISLE_C[1] + sn * jx + cs * jy)
                a = math.radians(ang + spec["yaw"])
                self.joints.append((p0, (math.cos(a), math.sin(a))))
        else:
            for jx, jy, ang in spec["joints"]:
                a = math.radians(ang)
                self.joints.append(((jx, jy), (math.cos(a), math.sin(a))))
        self._planes = {}

    def block_of(self, x, y):
        b = 0
        for j, (p0, d) in enumerate(self.joints):
            if d[0] * (y - p0[1]) - d[1] * (x - p0[0]) < 0.0:
                b |= 1 << j
        return b

    def setback(self, layer, x, y, t=0.5):
        """A hard bed's own set-back at a point on its face: its block's, the
        joint V's, and a little grain."""
        lp = self.lp[(self.key, layer)]
        b = self.block_of(x, y)
        r = lp["blocks"][b] - lp["lean"][b] * (t - 0.5)
        for (p0, d), (active, jit, depth) in zip(self.joints, lp["joints"]):
            if not active:
                continue
            dist = abs(d[0] * (y - p0[1]) - d[1] * (x - p0[0]) + jit)
            if dist < JW:
                r += depth * (1.0 - dist / JW) ** 1.3
        r += 0.0015 * (1.0 + math.sin(17.0 * x + 11.0 * y + lp["rph"]))
        # the slender stack weathers in proportion
        return r * (0.65 if self.key in ("B", "S") else 1.0)

    def planes(self, layer):
        """The joint faces at this bed's retreats, its chips and its cuts."""
        if layer in self._planes:
            return self._planes[layer]
        lp = self.lp[(self.key, layer)]
        rt = self.lp[(self.retreat_key, layer)]
        out = [(m, h - r) for (m, h), r in zip(self.faces, rt)]
        cuts = LAYER_SHAPE[(self.key, layer)][1]
        if self.key == "B" and self.close:
            cuts = tuple((m, h + self.close) if m[0] < 0.0 else (m, h) for m, h in cuts)
        out += [((m[0], m[1]), h) for m, h in cuts]
        if lp["chips"]:
            poly = clip_poly(self.base, out)
            for ang, depth in lp["chips"]:
                m = (math.cos(ang), math.sin(ang))
                out.append((m, max(px * m[0] + py * m[1] for px, py in poly) - depth))
        self._planes[layer] = out
        return out

    def rays(self):
        """The column's fixed bearings: its first hard bed's outline,
        sampled evenly along its length. Every bed is sampled on these rays,
        so ring i of any bed lies on the same ray from the centre."""
        if "rays" not in self._polys:
            first = [k for k in self.layers if HARD[k]][0]
            ring = ring_from(clip_poly(self.base, self.planes(first)), self.centre, self.bearing, self.M)
            self._polys["rays"] = [math.atan2(y - self.centre[1], x - self.centre[0]) for x, y in ring]
            # the set-backs are read at these reference points, so every
            # ring of every bed takes the same one on a given ray
            self._polys["ref"] = ring
        return self._polys["rays"]

    def cast(self, layer, shift, i):
        """Where ray ``i`` leaves the bed's convex outline (its planes set in
        by ``shift``): the distance and the cosine to that face's normal."""
        if "base_planes" not in self._polys:
            bp = []
            n = len(self.base)
            for k in range(n):
                a, b = self.base[k], self.base[(k + 1) % n]
                ex, ey = b[0] - a[0], b[1] - a[1]
                ln = math.hypot(ex, ey)
                m = (ey / ln, -ex / ln)
                bp.append((m, a[0] * m[0] + a[1] * m[1]))
            self._polys["base_planes"] = bp
        th = self.rays()[i]
        dx, dy = math.cos(th), math.sin(th)
        cx, cy = self.centre
        best = (9.0, 1.0)
        # the outline is the intersection of half-planes: the ray leaves it
        # at the nearest plane it runs toward
        for planes, sh in ((self._polys["base_planes"], shift), (self.planes(layer), shift)):
            for (mx, my), h in planes:
                un = dx * mx + dy * my
                if un <= 1e-9:
                    continue
                t = (h - sh - (cx * mx + cy * my)) / un
                if t < best[0]:
                    best = (t, un)
        return max(best[0], 0.02), max(0.25, best[1])

    def hard_point(self, layer, i, shift, t):
        """The bed's outline on ray ``i``, set in by ``shift`` and its own
        set-back there: every face moved in square to itself, so corners
        stay true."""
        self.rays()
        x, y = self._polys["ref"][i]
        return self.cast(layer, shift + self.setback(layer, x, y, t), i)

    def hard_ring(self, layer, f, t):
        out = []
        for i, th in enumerate(self.rays()):
            # a grain of wear on each arris, ray by ray, so no run of arris
            # facets lies in one plane with another bed's faces
            wear = 0.0007 * f * (1.0 + math.sin(2.7 * i + 1.9 * layer))
            rho, _un = self.hard_point(layer, i, CH * f * (1.0 + 0.15 * (layer % 3)) + wear, t)
            out.append((self.centre[0] + rho * math.cos(th), self.centre[1] + rho * math.sin(th)))
        return out

    def soft_ring(self, layer, f, flush=None):
        """On each ray: the innermost of the hard beds either side, less the
        undercut, measured square to the face."""
        near = [k for k in (layer - 1, layer + 1) if k in self.layers and HARD[k]]
        out = []
        for i, th in enumerate(self.rays()):
            if flush is not None:
                d = flush
            else:
                # each bed's floor a little different, so no two soft beds'
                # walls land on one face across a thin hard bed
                d = max(self.notch(layer, i) * f, 0.005 + 0.0006 * (layer % 3))
                if f < 0.8:
                    d = max(d, NOTCH_END + 0.0017 * (layer % 5))
            d += 0.0008 * (1.0 + math.sin(3.1 * i + 1.3 * layer))
            rho, _un = min(self.hard_point(k, i, d, 0.5) for k in near)
            out.append((self.centre[0] + rho * math.cos(th), self.centre[1] + rho * math.sin(th)))
        return out

    def notch(self, layer, i):
        lp = self.lp[(self.key, layer)]
        s = i / self.M
        base = (NOTCH_FOOT if layer == 0 else NOTCH) * (0.75 if self.key in ("B", "S") else 1.0)
        # the undercut comes and goes: deep in places, all but flush in others
        w = 0.62 + 0.62 * math.sin(TAU * 2.0 * s + lp["nph"][0]) + 0.34 * math.sin(TAU * 5.0 * s + lp["nph"][1])
        return base * max(0.08, w)


def bound_z(k, x, tilt):
    """Boundary ``k`` (the top of layer k) at plan x; --tilt-beds turns the
    interior boundaries about a line across the fin."""
    z = BOUNDS[k]
    if tilt and 0 <= k < len(BOUNDS) - 1:
        z += math.tan(math.radians(TILT_BEDS_DEG)) * (x - TILT_X0)
    return z


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------

def draw_facets(rng, k, lo, hi, deep):
    """``k`` fracture planes spread round the compass, one cut deeper."""
    rot = rng.uniform(0.0, TAU)
    out = [(rot + TAU * j / k + rng.uniform(-0.35, 0.35), rng.uniform(lo, hi)) for j in range(k)]
    j = rng.randrange(k)
    out[j] = (out[j][0], rng.uniform(*deep))
    return out


def plan_scene():
    rng = random.Random(SEED)
    plan = {"layers": {}}
    # the joint faces: each face's set-back drifts with height, coherently
    # from bed to bed, so a face leans and bellies; now and then a bed's
    # face has broken back further
    plan["stack_faces"] = [(math.radians(BODIES["S"]["yaw"] + 45.0 * j + rng.uniform(-10.0, 10.0)),
                            rng.uniform(0.020, 0.045)) for j in range(8)]
    for name, n in (("fin_retreat", len(FIN_FACES)), ("stack_retreat", 8)):
        drift = [(rng.uniform(0.004, 0.012), rng.uniform(0.45, 0.95), rng.uniform(0.0, TAU)) for _ in range(n)]
        for layer in range(len(BOUNDS)):
            zm = 0.5 * (BOUNDS[layer - 1] + BOUNDS[layer]) if layer else BOUNDS[0] - 0.05
            rt = []
            for a, lam, ph in drift:
                r = a * (0.5 + 0.5 * math.sin(TAU * zm / lam + ph)) + rng.uniform(0.0, 0.002)
                # the upper beds have broken back more: a ragged skyline
                if rng.random() < (0.30 if layer >= 11 else 0.05):
                    r += rng.uniform(0.020, 0.045)
                rt.append(r)
            if name == "fin_retreat" and layer == LINTEL_LAYER:
                rt = [0.0] * n
            plan["layers"][(name, layer)] = rt
    for key in BODY_ORDER:
        spec = BODIES[key]
        nj = len(spec["joints"])
        for layer in spec["layers"]:
            nb = 1 << nj
            blocks = [rng.uniform(0.0, 0.008) for _ in range(nb)]
            # now and then a block has fallen out of a hard bed, leaving a gap
            fallen = [rng.random() for _ in range(nb)]
            depth = [rng.uniform(0.032, 0.055) for _ in range(nb)]
            if HARD[layer] and layer not in (LINTEL_LAYER, LINTEL_LAYER - 2):
                blocks = [d if f < FALLEN_P else b for b, f, d in zip(blocks, fallen, depth)]
            chips = [(rng.uniform(0.0, TAU), rng.uniform(0.025, 0.060)) for _ in range(rng.choice((1, 1, 2, 3)))]
            lp = {
                "blocks": blocks,
                "lean": [rng.uniform(-0.005, 0.005) for _ in range(nb)],
                "joints": [(rng.random() > 0.15, rng.uniform(-0.005, 0.005), rng.uniform(0.020, 0.038))
                           for _ in range(nj)],
                "nph": (rng.uniform(0.0, TAU), rng.uniform(0.0, TAU)),
                "rph": rng.uniform(0.0, TAU),
                "chips": chips if HARD[layer] and layer != LINTEL_LAYER else [],
            }
            # the crown joint runs through the lintel's lower beds only; the
            # roof bed is whole but for it, so it covers both legs
            if key == "L" and layer >= 13:
                lp["joints"][3] = (False, 0.0, 0.0)
            if key == "L" and layer == LINTEL_LAYER:
                lp["blocks"] = [0.0] * nb
                lp["joints"] = [jt if j == 3 else (False, 0.0, 0.0) for j, jt in enumerate(lp["joints"])]
            plan["layers"][(key, layer)] = lp
    plan["waves"] = [(rng.uniform(28.0, 40.0) * math.cos(a), rng.uniform(28.0, 40.0) * math.sin(a),
                      rng.uniform(0.0, TAU), amp)
                     for a, amp in ((rng.uniform(0.0, TAU), 0.55), (rng.uniform(0.0, TAU), 0.30),
                                    (rng.uniform(0.0, TAU), 0.15))]
    plan["foam"] = [rng.uniform(0.0, TAU) for _ in range(6)]
    # loose rock
    talus = []
    for i, (x, y, lx, ly, h) in enumerate(TALUS):
        talus.append({"x": x + rng.uniform(-0.02, 0.02), "y": y + rng.uniform(-0.02, 0.02),
                      "l": lx, "w": ly, "h": h, "yaw": rng.uniform(0.0, 180.0),
                      "tilt": (rng.uniform(4.0, 7.0) * rng.choice((-1, 1)),
                               rng.uniform(4.0, 7.0) * rng.choice((-1, 1))),
                      "facets": draw_facets(rng, 6, 0.004, 0.022, (0.02, 0.035)),
                      "wob": rng.uniform(0.0, TAU), "tone": rng.random(), "layer": rng.choice((1, 3, 5, 9))})
    boulders = []
    for i, (x, y, r) in enumerate(BOULDERS):
        boulders.append({"x": x + rng.uniform(-0.015, 0.015), "y": y + rng.uniform(-0.015, 0.015),
                         "r": r, "long": rng.uniform(1.05, 1.35), "flat": rng.uniform(0.55, 0.75),
                         "yaw": rng.uniform(0.0, TAU),
                         "waves": [(Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))),
                                    rng.uniform(0.0, TAU), a) for a in (0.5, 0.3, 0.2, 0.1)],
                         "tone": rng.random()})
    plan["talus"] = talus
    plan["boulders"] = boulders
    # cover: candidate clumps on each top, as a bearing and a reach across
    # its turf; the build takes them in order, keeping them apart
    cover = {}
    for key in ("L", "S"):
        n = TUFTS[key] + THRIFT[key]
        kinds = ["thrift" if (j * 7) % n < THRIFT[key] else "grass" for j in range(n)]
        cands = []
        for j in range(90):
            cands.append({"ang": rng.uniform(0.0, TAU),
                          "f": COVER_F[key][0] + (COVER_F[key][1] - COVER_F[key][0]) * math.sqrt(rng.random()),
                          "n": rng.randint(9, 13), "leaves": rng.randint(13, 17),
                          "stalks": rng.randint(3, 5), "h": rng.uniform(0.07, 0.14),
                          "spin": rng.uniform(0.0, TAU), "tone": rng.random(),
                          "blades": [(rng.uniform(-0.35, 0.35), rng.uniform(0.6, 1.0), rng.uniform(0.4, 1.1),
                                      rng.uniform(-0.8, 0.8), rng.random()) for _ in range(17)],
                          "wide": rng.uniform(0.8, 1.3),
                          "heads": [(rng.uniform(0.75, 1.0), rng.uniform(0.0, TAU), rng.uniform(0.15, 0.40),
                                     rng.random()) for _ in range(5)]})
        cover[key] = (kinds, cands)
    plan["cover"] = cover
    return plan


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

class Builder:
    """The bmesh plus its layers: Tone (shading variety), Part (the shell's
    role), Ident (which body, bed or piece), Layer and Hard (a bed's place in
    the column), Cap (1 on a bed's bottom, 2 on its top), Zone (a water
    sheet's top), and per vertex Ring (a bed ring's index), Tip (along a
    blade or stalk), Depth (water over the bed), FoamX (across the foam)."""

    def __init__(self, bm):
        self.bm = bm
        self.tone = bm.faces.layers.float.new("Tone")
        self.zone = bm.faces.layers.float.new("Zone")
        self.part = bm.faces.layers.int.new("Part")
        self.ident = bm.faces.layers.int.new("Ident")
        self.layer = bm.faces.layers.int.new("Layer")
        self.hard = bm.faces.layers.int.new("Hard")
        self.cap = bm.faces.layers.int.new("Cap")
        self.shell = bm.faces.layers.int.new("Shell")
        self.shell_id = 0
        self.ring = bm.verts.layers.int.new("Ring")
        self.tip = bm.verts.layers.float.new("Tip")
        self.depth = bm.verts.layers.float.new("Depth")
        self.foamx = bm.verts.layers.float.new("FoamX")
        self.uv = bm.loops.layers.uv.new("UVMap")

    def vert(self, co, ring=-1, tip=0.0):
        v = self.bm.verts.new(co)
        v[self.ring] = ring
        v[self.tip] = tip
        return v

    def face(self, verts, mat, tone, part, ident=0, layer=-1, hard=0, cap=0, zone=0.0):
        f = self.bm.faces.new(verts)
        f.material_index = mat
        f[self.tone] = tone
        f[self.part] = part
        f[self.ident] = ident
        f[self.layer] = layer
        f[self.hard] = hard
        f[self.cap] = cap
        f[self.zone] = zone
        f[self.shell] = self.shell_id if part in COVER_PARTS else 0
        return f

    def quad(self, a, b, c, d, *args, **kw):
        """Split on the short diagonal: a flat facet, and a ray lands on the
        face actually shipped."""
        if (a.co - c.co).length <= (b.co - d.co).length:
            self.face((a, b, c), *args, **kw)
            self.face((a, c, d), *args, **kw)
        else:
            self.face((a, b, d), *args, **kw)
            self.face((b, c, d), *args, **kw)


def squircle(i, k, n):
    uu = -1.0 + 2.0 * i / n
    vv = -1.0 + 2.0 * k / n
    return uu * math.sqrt(1.0 - vv * vv / 2.0), vv * math.sqrt(1.0 - uu * uu / 2.0)


def grid_rim(grid, n):
    return ([grid[i][0] for i in range(n)] + [grid[n][k] for k in range(n)]
            + [grid[i][n] for i in range(n, 0, -1)] + [grid[0][k] for k in range(n, 0, -1)])


def add_tile(B, n):
    """The platform: a squircle grid over the tile whose rim rolls down to a
    flat base at Z = 0."""
    grid = []
    for i in range(n + 1):
        col = []
        for k in range(n + 1):
            X, Y = squircle(i, k, n)
            wob = disc_wobble(math.atan2(Y, X))
            x = TILE_C[0] + TILE_A[0] * X * wob
            y = TILE_C[1] + TILE_A[1] * Y * wob
            on_rim = i in (0, n) or k in (0, n)
            z = 0.0 if on_rim else ground_height(x, y)
            col.append(B.vert((x, y, z)))
        grid.append(col)
    for i in range(n):
        for k in range(n):
            B.quad(grid[i][k], grid[i + 1][k], grid[i + 1][k + 1], grid[i][k + 1],
                   SHELF_IDX, 0.5, P_TILE)
    B.face(list(reversed(grid_rim(grid, n))), SHELF_IDX, 0.5, P_TILE, cap=1)


def stack_shear(flags):
    """--lean-stack: a horizontal shear of the stack about its foot, which
    keeps every bed's footprint on the bed under it at each height."""
    if not flags.get("lean_stack"):
        return None
    z0 = ISLE_Z
    d = Vector((LEAN_DIR[0], LEAN_DIR[1], 0.0)).normalized()
    return lambda p: p + d * (LEAN * max(0.0, p.z - z0))


def bed_rings(body, layer, G, flags, foot=None):
    """Rings of (x, y, z) for one bed, bottom to top, and whether it is hard."""
    tilt = flags.get("tilt_beds", False)
    if HARD[layer]:
        rings = []
        for t, f in HARD_PROFILE:
            ring = []
            for x, y in body.hard_ring(layer, f, t):
                b0, b1 = bound_z(layer - 1, x, tilt), bound_z(layer, x, tilt)
                ring.append((x, y, b0 + t * (b1 - b0)))
            rings.append(ring)
        return rings, True
    flush = flags.get("flush_beds", False)
    if layer == 0:
        # the foot: flared and buried, the wave-cut notch just above the platform
        zbot, zg = foot
        prof = [(None, 0.55), ("g", 0.62), (0.45, 1.0), (0.78, 0.90), ("top", 0.72)]
    else:
        e = 0.02 * (layer % 3)
        prof = [("bot", 0.72), (0.22 + e, 0.92), (0.50, 1.0), (0.78 - e, 0.92), ("top", 0.72)]
    gap = flags.get("gap_lintel") and body.key == "A" and layer == LINTEL_LAYER - 1
    rings = []
    for r, (tag, f) in enumerate(prof):
        mid = 0 < r < len(prof) - 1
        ring = []
        for x, y in body.soft_ring(layer, f, FLUSH_NOTCH if flush and mid else None):
            b0 = bound_z(layer - 1, x, tilt) if layer > 0 else None
            b1 = bound_z(layer, x, tilt)
            # each soft bed bites a slightly different depth, so no band of one
            # bed lands on the plane of another's arris
            bite = BITE * (1.0 + 0.09 * (layer % 4))
            top = b1 - GAP_LINTEL if gap else b1 + bite
            if layer == 0:
                lo = max(zg + 0.012, zbot + 0.010)
                if tag is None:
                    z = zbot
                elif tag == "g":
                    z = lo
                elif tag == "top":
                    z = top
                else:
                    z = lo + tag * (b1 - lo)
            else:
                lo = b0 - bite
                if tag == "bot":
                    z = lo
                elif tag == "top":
                    z = top
                elif gap:
                    z = lo + tag * (top - lo)
                else:
                    z = b0 + tag * (b1 - b0)
            ring.append((x, y, z))
        rings.append(ring)
    return rings, False


def foot_levels(body, G, flags):
    """The lowest bed's foot: EMBED under the lowest platform point beneath
    its widest ring, and the mean platform height there. The foot is kept
    off the sea sheet's planes."""
    zs = [G.z(x, y) for x, y in body.soft_ring(0, 0.55)]
    zg = sum(zs) / len(zs)
    if flags.get("cut_pillar") and body.key == "B":
        return max(zs) + CUT_PILLAR, zg
    zbot = min(zs) - EMBED
    for level in (WATER_LEVEL, WATER_LEVEL - WATER_SLAB):
        if abs(zbot - level) < 0.004:
            zbot = level - 0.004
    return zbot, zg


def add_bed(B, body, layer, rings, hard, xf=None):
    ident = body.id * 100 + layer
    # every bed's walls batter by their own degree or two, out at the foot
    # or out at the top, so no face of one bed lies in the plane of another's
    k = (0.020 if hard else 0.050) * (1.0 + 0.25 * ((layer // 2 + body.id) % 3)) * (1.0 if (layer // 2) % 2 else -1.0)
    zm = sum(p[2] for ring in rings for p in ring) / sum(len(ring) for ring in rings)
    cx, cy = body.centre
    verts = []
    for r, ring in enumerate(rings):
        row = []
        for (x, y, z) in ring:
            dx, dy = x - cx, y - cy
            ln = math.hypot(dx, dy) or 1.0
            # out along the ray and a little round it, so faces lying along a
            # ray (a joint's V) are turned too
            ux, uy = dx / ln, dy / ln
            w = k * (z - zm)
            p = Vector((x + (ux - 0.6 * uy) * w, y + (uy + 0.6 * ux) * w, z))
            if xf is not None:
                p = xf(p)
            row.append(B.vert(p, ring=r))
        verts.append(row)
    M = body.M
    tones = [0.1 + 0.8 * hash01(body.id, layer, body.block_of(x, y)) for x, y, _z in rings[0]]
    for r0, r1 in zip(verts, verts[1:]):
        for i in range(M):
            j = (i + 1) % M
            B.quad(r0[i], r0[j], r1[j], r1[i], ROCK_IDX, tones[i], P_BED, ident, layer, int(hard))
    B.face(list(reversed(verts[0])), ROCK_IDX, tones[0], P_BED, ident, layer, int(hard), cap=1)
    B.face(list(verts[-1]), ROCK_IDX, tones[0], P_BED, ident, layer, int(hard), cap=2)
    return verts


def sheet_grid(B, centre, radius_at, n, zfun, mat, tone, part, ident, slab, depth_fn):
    """A water sheet: a squircle grid out to ``radius_at(theta)``, a short
    wall down and a flat underside."""
    grid = []
    for i in range(n + 1):
        col = []
        for k in range(n + 1):
            X, Y = squircle(i, k, n)
            r = math.hypot(X, Y)
            th = math.atan2(Y, X)
            rho = r * radius_at(th)
            x = centre[0] + rho * math.cos(th)
            y = centre[1] + rho * math.sin(th)
            v = B.vert((x, y, zfun(x, y)))
            v[B.depth] = depth_fn(x, y)
            col.append(v)
        grid.append(col)
    for i in range(n):
        for k in range(n):
            B.quad(grid[i][k], grid[i + 1][k], grid[i + 1][k + 1], grid[i][k + 1],
                   mat, tone, part, ident, zone=1.0)
    rim = grid_rim(grid, n)
    m = len(rim)
    lows = []
    for v in rim:
        w = B.vert((v.co.x, v.co.y, v.co.z - slab))
        w[B.depth] = v[B.depth]
        lows.append(w)
    for j in range(m):
        q = (j + 1) % m
        B.face((rim[j], rim[q], lows[q], lows[j]), mat, tone, part, ident)
    B.face(list(reversed(lows)), mat, tone, part, ident, cap=1)


def add_sea(B, plan, G, flags):
    margin = SHORT_SEA if flags.get("short_sea") else WATER_MARGIN
    table = ray_table(SEA_C, sea_sdf, margin)
    flat = flags.get("flat_sea", False)

    def zfun(x, y):
        if flat:
            return WATER_LEVEL
        return WATER_LEVEL + ripple(plan, x, y) * calm(x, y)

    sheet_grid(B, SEA_C, lambda th: table_at(table, th), WATER_N, zfun, WATER_IDX, 0.5, P_SEA, 1,
               WATER_SLAB, lambda x, y: max(0.0, WATER_LEVEL - G.z(x, y)))


def add_pools(B, G):
    for i, ((cx, cy), _r, _d) in enumerate(POOLS):
        level = pool_level(i, G)
        sheet_grid(B, (cx, cy), lambda th, i=i: pool_radius(i, th), POOL_N,
                   lambda x, y, level=level: level, WATER_IDX, 0.8, P_POOL, 10 + i, POOL_SLAB,
                   lambda x, y, level=level: max(0.0, level - G.z(x, y)))


def shore_loop(n, island, plan):
    """The waterline: points on the shoreline, their landward normals."""
    if island:
        pts = []
        for k in range(720):
            phi = TAU * k / 720
            r = isle_radius(phi)
            pts.append((ISLE_C[0] + r * math.cos(phi), ISLE_C[1] + r * math.sin(phi)))
        pts = resample_closed(pts, n)
        nrm = [(-a, -b) for a, b in outward_normals(pts)]
    else:
        table = ray_table(SEA_C, sea_sdf, 0.0)
        pts = []
        for k, r in enumerate(table):
            th = TAU * k / len(table)
            pts.append((SEA_C[0] + r * math.cos(th), SEA_C[1] + r * math.sin(th)))
        pts = resample_closed(pts, n)
        nrm = outward_normals(pts)
    return pts, nrm


def add_foam(B, plan, flags):
    lift = LIFT_FOAM if flags.get("lift_foam") else 0.0
    ph = plan["foam"]
    for loop, (n, island) in enumerate(((FOAM_N, False), (ISLE_FOAM_N, True))):
        pts, nrm = shore_loop(n, island, plan)
        rows = []
        for i, ((px, py), (nx, ny)) in enumerate(zip(pts, nrm)):
            s = i / n
            w = FOAM_OUT[0] + (FOAM_OUT[1] - FOAM_OUT[0]) * (
                0.5 + 0.30 * math.sin(TAU * 5.0 * s + ph[0 + loop]) + 0.20 * math.sin(TAU * 13.0 * s + ph[2 + loop]))
            zt = WATER_LEVEL + FOAM_T + 0.0008 * math.sin(TAU * 17.0 * s + ph[4 + loop]) + lift
            zb = WATER_LEVEL - FOAM_T + lift
            li = (px + nx * FOAM_IN, py + ny * FOAM_IN)
            so = (px - nx * w, py - ny * w)
            row = [B.vert((li[0], li[1], zt)), B.vert((so[0], so[1], zt)),
                   B.vert((so[0], so[1], zb)), B.vert((li[0], li[1], zb))]
            for v, fx in zip(row, (0.0, 1.0, 1.0, 0.0)):
                v[B.foamx] = fx
            rows.append(row)
        for i in range(n):
            a, b = rows[i], rows[(i + 1) % n]
            for j in range(4):
                k = (j + 1) % 4
                B.face((a[j], a[k], b[k], b[j]), FOAM_IDX, 0.5, P_FOAM, loop + 1)


def talus_local(tb):
    """A fallen block in its own frame: a bed fragment cut by fracture
    planes, with a hard bed's arrises, centred on the origin."""
    M = TALUS_M
    local = resample_closed(superellipse(0.5 * tb["l"] + 0.02, 0.5 * tb["w"] + 0.02, 2.6), 64)
    planes = []
    for ang, depth in tb["facets"]:
        m = (math.cos(ang), math.sin(ang))
        planes.append((m, max(px * m[0] + py * m[1] for px, py in local) - depth - 0.02))
    ch = min(0.20 * tb["h"], CH)
    rings = []
    for t, f in HARD_PROFILE:
        ring = ring_from(clip_poly(local, planes, ch * f), (0.0, 0.0), -0.5 * math.pi, M)
        rings.append([Vector((x, y, (t - 0.5) * tb["h"])) for x, y in ring])
    return rings


def seat(points, G, sink, perch):
    """Sink until every sector's most-buried vertex is ``sink`` under the
    platform; ``perch`` seats the lowest vertex against the platform at the
    centre alone."""
    cx = sum(p.x for p in points) / len(points)
    cy = sum(p.y for p in points) / len(points)
    if perch:
        zmin = min(p.z for p in points)
        return G.z(cx, cy) - sink - zmin
    best = [-9.0] * SECTORS
    for p in points:
        s = min(SECTORS - 1, int((math.atan2(p.y - cy, p.x - cx) % TAU) / TAU * SECTORS))
        best[s] = max(best[s], G.z(p.x, p.y) - p.z)
    return min(best) - sink


def relax(items, radius, fixed=()):
    """Push pairs of plan centres apart to the sum of their radius bounds."""
    for _ in range(80):
        moved = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                d = math.hypot(dx, dy)
                need = radius(a) + radius(b) + ROCK_GAP
                if d < need and d > 1e-9:
                    push = 0.5 * (need - d) + 1e-4
                    a["x"] -= dx / d * push
                    a["y"] -= dy / d * push
                    b["x"] += dx / d * push
                    b["y"] += dy / d * push
                    moved = True
        if not moved:
            break


def rock_radius(it):
    if "l" in it:
        return 0.5 * math.hypot(it["l"], it["w"])
    return it["r"] * it["long"]


def loose_rocks(plan, flags):
    items = [dict(t) for t in plan["talus"]] + [dict(b) for b in plan["boulders"]]
    if flags.get("pile_talus"):
        cx = sum(it["x"] for it in items[:3]) / 3.0
        cy = sum(it["y"] for it in items[:3]) / 3.0
        for it in items[:3]:
            it["x"] = cx + 0.25 * (it["x"] - cx)
            it["y"] = cy + 0.25 * (it["y"] - cy)
    else:
        relax(items, rock_radius)
    return items


def add_loose(B, plan, G, flags):
    perch = flags.get("perch_talus", False)
    for n, it in enumerate(loose_rocks(plan, flags)):
        if "l" in it:
            rings = talus_local(it)
            R = (Matrix.Rotation(math.radians(it["yaw"]), 3, "Z")
                 @ Matrix.Rotation(math.radians(it["tilt"][0]), 3, "X")
                 @ Matrix.Rotation(math.radians(it["tilt"][1]), 3, "Y"))
            off = Vector((it["x"], it["y"], 0.0))
            rings = [[R @ p + off for p in ring] for ring in rings]
            dz = seat([p for ring in rings for p in ring], G, REST_SINK, perch)
            verts = [[B.vert(p + Vector((0.0, 0.0, dz)), ring=r) for p in ring] for r, ring in enumerate(rings)]
            tone = 0.15 + 0.7 * it["tone"]
            M = len(verts[0])
            for r0, r1 in zip(verts, verts[1:]):
                for i in range(M):
                    j = (i + 1) % M
                    B.quad(r0[i], r0[j], r1[j], r1[i], ROCK_IDX, tone, P_TALUS, 300 + n, it["layer"], 1)
            B.face(list(reversed(verts[0])), ROCK_IDX, tone, P_TALUS, 300 + n, it["layer"], 1, cap=1)
            B.face(list(verts[-1]), ROCK_IDX, tone, P_TALUS, 300 + n, it["layer"], 1, cap=2)
        else:
            dirs, quads = cube_sphere(3)
            r = it["r"]
            ax = Vector((r * it["long"], r, r * it["flat"]))
            yaw = Matrix.Rotation(it["yaw"], 3, "Z")
            pts = []
            for d in dirs:
                q = Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z))
                q *= 1.0 + 0.10 * sum(a * math.sin(w.normalized().dot(d) * 3.0 + ph)
                                      for w, ph, a in it["waves"])
                pts.append(yaw @ q + Vector((it["x"], it["y"], 0.0)))
            if perch:
                dz = seat(pts, G, REST_SINK, True)
            else:
                # a third of its height down, and never perched
                dz = min(seat(pts, G, REST_SINK, False), G.z(it["x"], it["y"]) - min(p.z for p in pts)
                         - 0.35 * 2.0 * ax.z)
            verts = [B.vert(p + Vector((0.0, 0.0, dz))) for p in pts]
            for q in quads:
                B.quad(*[verts[i] for i in q], COBBLE_IDX, 0.15 + 0.7 * it["tone"], P_BOULDER, 400 + n)


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


def add_turf(B, body, top_ring, xf, key):
    """A turf mat over a top bed: a domed lens whose rim tucks into the
    stone a little inside the bed's edge."""
    M = body.M
    cen = Vector((sum(p[0] for p in top_ring) / M, sum(p[1] for p in top_ring) / M, 0.0))

    def pull(p, d):
        q = Vector((p[0], p[1], 0.0))
        w = cen - q
        return q + w.normalized() * min(d, 0.5 * w.length)

    top = sum(p[2] for p in top_ring) / M
    rim = []
    for p in top_ring:
        q = pull(p, TURF_IN)
        rim.append(Vector((q.x, q.y, top)))
    cen.z = top
    rings = []
    for k in range(TURF_RINGS):
        f = 1.0 - (k / TURF_RINGS) ** 1.25
        h = TURF_H * math.sqrt(max(0.0, 1.0 - (1.0 - k / TURF_RINGS) ** 2)) if k else -0.003
        ring = []
        for p in rim:
            q = cen + (p - cen) * f
            lump = (0.006 * math.sin(31.0 * q.x + 7.0 * q.y) * math.cos(23.0 * q.y - 5.0 * q.x)
                    + 0.003 * math.sin(71.0 * q.x - 53.0 * q.y)) * min(1.0, k / 2.0) if k else 0.0
            ring.append(Vector((q.x, q.y, top + h + lump)))
        rings.append(ring)
    apex = cen + Vector((0.0, 0.0, TURF_H + 0.002))
    low = []
    for p in top_ring:
        q = pull(p, TURF_IN + 0.006)
        low.append(Vector((q.x, q.y, top - TURF_BITE)))

    def mk(p, r):
        if xf is not None:
            p = xf(p)
        return B.vert(p, ring=r)

    vr = [[mk(p, r) for p in ring] for r, ring in enumerate(rings)]
    va = mk(apex, TURF_RINGS)
    vl = [mk(p, -2) for p in low]
    ident = body.id
    for r0, r1 in zip(vr, vr[1:]):
        for i in range(M):
            j = (i + 1) % M
            B.quad(r0[i], r0[j], r1[j], r1[i], TURF_IDX, 0.5, P_TURF, ident)
    for i in range(M):
        j = (i + 1) % M
        B.face((vr[-1][i], vr[-1][j], va), TURF_IDX, 0.5, P_TURF, ident)
        B.quad(vl[i], vl[j], vr[0][j], vr[0][i], TURF_IDX, 0.5, P_TURF, ident)
    B.face(list(reversed(vl)), TURF_IDX, 0.5, P_TURF, ident, cap=1)
    # the turf's top in its own (unsheared) frame, for seating the cover
    pts = [tuple(p) for ring in rings for p in ring] + [tuple(apex)]
    tris = []
    for r in range(len(rings) - 1):
        for i in range(M):
            j = (i + 1) % M
            tris.append((r * M + i, r * M + j, (r + 1) * M + j, (r + 1) * M + i))
    last = (len(rings) - 1) * M
    for i in range(M):
        tris.append((last + i, last + (i + 1) % M, len(pts) - 1))
    return BVHTree.FromPolygons(pts, tris), cen, rim


def blade(B, base, tip, width, twist, tone, part, ident, mat=GRASS_IDX, segs=4, thick=None):
    """A closed diamond-section strip from ``base`` to ``tip``, arching over."""
    B.shell_id += 1
    d = tip - base
    if thick is None:
        # each blade its own thickness and roll, so no two blades' faces share a plane
        hb = hash01(base.x * 997.0, base.y * 991.0, tip.z * 983.0)
        thick = 0.0009 + 0.0005 * hb
        twist += 0.6 * (hb - 0.5)
    hd = Vector((d.x, d.y, 0.0))
    hd = hd.normalized() if hd.length > 1e-6 else Vector((1.0, 0.0, 0.0))
    ctrl = base + UP * (max(d.z, 0.02) * 0.75) + hd * (0.25 * Vector((d.x, d.y, 0.0)).length)
    pts = []
    for i in range(segs + 1):
        t = i / segs
        pts.append(base * (1 - t) ** 2 + ctrl * (2 * t * (1 - t)) + tip * t * t)
    left, right, top, bot = [], [], [], []
    for i in range(segs):
        t = i / segs
        tan = (pts[i + 1] - pts[i]).normalized()
        side = tan.cross(hd)
        side = side.normalized() if side.length > 1e-6 else perp_basis(tan)[0]
        side = (side * math.cos(twist * t) + tan.cross(side) * math.sin(twist * t)).normalized()
        nrm = side.cross(tan).normalized()
        w = 0.5 * width * (1.0 - 0.80 * t ** 1.4)
        th = thick * (1.0 - 0.6 * t)
        left.append(B.vert(pts[i] - side * w, ring=i, tip=t))
        right.append(B.vert(pts[i] + side * w, ring=i, tip=t))
        top.append(B.vert(pts[i] + nrm * th, ring=i, tip=t))
        bot.append(B.vert(pts[i] - nrm * th, ring=i, tip=t))
    tv = B.vert(pts[-1], ring=segs, tip=1.0)
    B.face((left[0], bot[0], right[0], top[0]), mat, tone, part, ident, cap=1)
    for i in range(segs - 1):
        for a, b in ((left, top), (top, right), (right, bot), (bot, left)):
            B.face((a[i], a[i + 1], b[i + 1], b[i]), mat, tone, part, ident)
    s = segs - 1
    for a, b in ((left[s], top[s]), (top[s], right[s]), (right[s], bot[s]), (bot[s], left[s])):
        B.face((a, tv, b), mat, tone, part, ident)


def tube(B, pts, radii, sides, mat, tone, part, ident, phase=0.0):
    B.shell_id += 1
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
                             ring=i, tip=i / (len(pts) - 1)) for k in range(sides)])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            B.face((r0[k], r0[m], r1[m], r1[k]), mat, tone, part, ident)
    B.face(tuple(reversed(rings[0])), mat, tone, part, ident, cap=1)
    B.face(tuple(rings[-1]), mat, tone, part, ident, cap=2)


def cover_spots(plan, key, cen, rim):
    """Take the candidates in order, each at its bearing and reach across
    the turf, keeping clumps a spacing apart, until every kind is placed."""
    kinds, cands = plan["cover"][key]
    spots = []
    want = list(kinds)
    for c in cands:
        if not want:
            break
        best, bi = 9.0, 0
        for i, p in enumerate(rim):
            a = math.atan2(p.y - cen.y, p.x - cen.x)
            d = abs((a - c["ang"] + math.pi) % TAU - math.pi)
            if d < best:
                best, bi = d, i
        p = cen + (rim[bi] - cen) * c["f"]
        if any((p - q).length < COVER_SPACING[key] for q, _k, _c in spots):
            continue
        spots.append((p, want.pop(0), c))
    return spots


def add_cover(B, plan, key, turf, xf, flags):
    tree, cen, rim = turf
    lift = FLOAT_COVER if flags.get("float_cover") else 0.0
    ident = BODIES[key]["id"]

    def surface(x, y):
        loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
        return None if loc is None else loc.z

    # the turf tree is built in the unsheared frame; everything placed here
    # is sheared with the stack afterwards
    for p, kind, it in cover_spots(plan, key, cen, rim):
        zt = surface(p.x, p.y)
        if zt is None:
            continue
        root = Vector((p.x, p.y, zt - ROOT_D))

        def place(b, t, *a, **k):
            b2 = b + Vector((0.0, 0.0, lift))
            if xf is not None:
                b2, t = xf(b2), xf(t)
            blade(B, b2, t, *a, **k)

        if kind == "grass":
            for j in range(it["n"]):
                yaw, lean, hf, tw, tn = it["blades"][j]
                a = it["spin"] + TAU * (j + 0.35 * yaw) / it["n"]
                h = it["h"] * (0.6 + 0.4 * hf)
                out = Vector((math.cos(a), math.sin(a), 0.0))
                b = root + out * 0.006 - UP * (0.0011 * (j % 5))
                t = Vector((p.x, p.y, zt)) + out * (h * 0.55 * lean) + UP * (h * (1.0 - 0.3 * lean))
                place(b, t, 0.0050 * it["wide"], tw, 0.1 + 0.7 * tn, P_BLADE, ident)
        else:
            # sea thrift: a cushion of narrow leaves and pink heads on stalks
            for j in range(it["leaves"]):
                yaw, lean, hf, tw, tn = it["blades"][j]
                a = it["spin"] + TAU * (j + 0.35 * yaw) / it["leaves"]
                h = 0.040 + 0.02 * hf
                out = Vector((math.cos(a), math.sin(a), 0.0))
                b = root + out * 0.004 - UP * (0.0011 * (j % 5))
                t = Vector((p.x, p.y, zt)) + out * (h * 0.9 * lean) + UP * (h * (0.9 - 0.4 * lean))
                place(b, t, 0.0030, tw, 0.82 + 0.18 * tn, P_BLADE, ident)
            for j in range(it["stalks"]):
                hf, a, lean, tn = it["heads"][j]
                h = it["h"] * (0.8 + 0.4 * hf) + 0.03
                out = Vector((math.cos(a), math.sin(a), 0.0))
                b = root + out * (0.003 + 0.0015 * j) + Vector((0.0, 0.0, lift - 0.0017 * j))
                top = Vector((p.x, p.y, zt)) + out * (h * 0.35 * lean) + UP * h
                pts = []
                for k in range(5):
                    t = k / 4.0
                    q = b.lerp(top, t) + out * (0.02 * lean * math.sin(math.pi * t))
                    pts.append(xf(q) if xf is not None else q)
                tube(B, pts, [0.0019, 0.0017, 0.0015, 0.0014, 0.0013], 5, GRASS_IDX, 0.85, P_STALK, ident,
                     phase=0.37 * j + 1.7 * tn)
                # the head: a lumpy pompom round the stalk's end
                ax = (pts[-1] - pts[-2]).normalized()
                hc = pts[-1] + ax * 0.009
                dirs, quads = cube_sphere(2)
                rh = 0.0165 + 0.003 * tn
                spin = Matrix.Rotation(0.9 * j + 2.3 * tn, 3, Vector((0.3, 0.5, 1.0)).normalized())
                hv = []
                B.shell_id += 1
                for d in dirs:
                    lump = 1.0 + 0.10 * math.sin(9.0 * d.x + 5.0 * d.y + 7.0 * tn) * math.cos(8.0 * d.z + a)
                    q = spin @ Vector((d.x, d.y, d.z * 0.85)) * (rh * lump)
                    hv.append(B.vert(hc + q, tip=1.0))
                for q in quads:
                    B.quad(*[hv[i] for i in q], THRIFT_IDX, tn, P_HEAD, ident)


def break_coplanar(B, passes=8):
    """Blades, stalks and heads are many small faces in every direction; now
    and then one lands in another shell's plane. Turn such a piece a few
    degrees about the vertical through its root until none does."""
    bm = B.bm
    for _ in range(passes):
        bm.normal_update()
        # only faces up among the cover can meet it
        zlow = min(v.co.z for f in bm.faces if f[B.shell] for v in f.verts) - COPLANAR_CENTRE_MAX
        faces = [f for f in bm.faces if f.verts[0].co.z > zlow]
        shell = [f[B.shell] for f in faces]
        cent = [f.calc_center_median() for f in faces]
        kd = KDTree(len(faces))
        for i, c in enumerate(cent):
            kd.insert(c, i)
        kd.balance()
        bad = set()
        for i, f in enumerate(faces):
            if not shell[i]:
                continue
            for _co, j, _d in kd.find_range(cent[i], COPLANAR_CENTRE_MAX):
                if shell[j] == shell[i]:
                    continue
                g = faces[j]
                if abs(abs(f.normal.dot(g.normal)) - 1.0) > 4.0 * COPLANAR_NORMAL_EPS:
                    continue
                if abs(f.normal.dot(cent[j] - cent[i])) > 4.0 * COPLANAR_PLANE_EPS:
                    continue
                bad.add(shell[i])
        if not bad:
            return
        for sid in sorted(bad):
            vs = {v for f, sh in zip(faces, shell) if sh == sid for v in f.verts}
            root = min(vs, key=lambda v: v.co.z).co.copy()
            R = Matrix.Rotation(math.radians(3.0), 3, "Z")
            for v in vs:
                v.co = root + R @ (v.co - root)


def break_bed_coplanar(B, passes=6):
    """A soft bed is built from the planes of the hard beds either side, so
    now and then one of its facets lands in the plane of theirs. Draw such
    a facet 1.5 mm further in toward its column's centre (further inside the
    beds it bites) until none does."""
    bm = B.bm
    centres = {BODIES[k]["id"]: (BODIES[k]["centre"] if k != "S" else ISLE_C) for k in BODY_ORDER}
    for _ in range(passes):
        bm.normal_update()
        faces = [f for f in bm.faces if f[B.part] == P_BED]
        ident = [f[B.ident] for f in faces]
        soft = [not f[B.hard] for f in faces]
        cent = [f.calc_center_median() for f in faces]
        kd = KDTree(len(faces))
        for i, c in enumerate(cent):
            kd.insert(c, i)
        kd.balance()
        bad = []
        for i, f in enumerate(faces):
            if not soft[i]:
                continue
            for _co, j, _d in kd.find_range(cent[i], COPLANAR_CENTRE_MAX):
                if ident[j] == ident[i]:
                    continue
                g = faces[j]
                if abs(abs(f.normal.dot(g.normal)) - 1.0) > 4.0 * COPLANAR_NORMAL_EPS:
                    continue
                if abs(f.normal.dot(cent[j] - cent[i])) > 4.0 * COPLANAR_PLANE_EPS:
                    continue
                bad.append(i)
                break
        if not bad:
            return
        moved = set()
        for i in bad:
            cx, cy = centres[ident[i] // 100]
            for v in faces[i].verts:
                if v in moved:
                    continue
                moved.add(v)
                d = Vector((cx - v.co.x, cy - v.co.y, 0.0))
                if d.length > 1e-6:
                    v.co += d.normalized() * 0.0015


def build_mesh(name, plan, detail="low", **flags):
    bm = bmesh.new()
    try:
        B = Builder(bm)
        add_tile(B, TILE_N[detail])
        # a temp tree for ray casts needs face normals first
        bm.normal_update()
        G = Ground(BVHTree.FromBMesh(bm))
        scale = 1.5 if detail == "high" else 1.0
        close = CLOSE_ARCH if flags.get("close_arch") else 0.0
        tops = {}
        shear = stack_shear(flags)
        for key in BODY_ORDER:
            body = Body(key, plan, int(BODIES[key]["M"] * scale), close if key == "B" else 0.0)
            xf = shear if key == "S" else None
            foot = foot_levels(body, G, flags) if 0 in body.layers else None
            for layer in body.layers:
                rings, hard = bed_rings(body, layer, G, flags, foot)
                add_bed(B, body, layer, rings, hard, xf)
                if layer == body.layers[-1] and key in ("L", "S"):
                    tops[key] = (body, rings[-1], xf)
        add_sea(B, plan, G, flags)
        add_pools(B, G)
        add_foam(B, plan, flags)
        add_loose(B, plan, G, flags)
        for key in ("L", "S"):
            body, ring, xf = tops[key]
            turf = add_turf(B, body, ring, xf, key)
            add_cover(B, plan, key, turf, xf, flags)

        triangulate_ngons(bm)
        break_bed_coplanar(B)
        break_coplanar(B)
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        # Everything smooth-shaded, with every material boundary and every
        # fold sharper than its crease a hard edge: a bed's joints and
        # chipped corners, a block's arrises.
        crease = {ROCK_IDX: 18.0, SHELF_IDX: 40.0, COBBLE_IDX: 70.0, GRASS_IDX: 70.0, THRIFT_IDX: 70.0}
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


def build_collider_source(plan):
    """Point groups for one convex hull each: the two legs, the lintel, the
    stack and the platform. Players pass under the arch."""
    groups = []
    for key in BODY_ORDER:
        body = Body(key, plan, BODIES[key]["M"])
        step = max(1, body.M // 10)
        pts = []
        for k in body.layers:
            if not HARD[k]:
                continue
            ring = body.hard_ring(k, 0.0, 0.5)
            lo = BOUNDS[k - 1]
            if k == body.layers[1]:
                lo = ISLE_Z - 0.02 if key == "S" else SHELF_Z
            for i in range(0, body.M, step):
                x, y = ring[i]
                pts += [Vector((x, y, lo)), Vector((x, y, BOUNDS[k]))]
        groups.append(pts)
    tile = []
    for k in range(16):
        th = TAU * k / 16
        w = disc_wobble(th)
        x = TILE_C[0] + TILE_A[0] * math.cos(th) * w
        y = TILE_C[1] + TILE_A[1] * math.sin(th) * w
        tile += [Vector((x, y, 0.0)), Vector((0.9 * x, 0.9 * y, SHELF_Z))]
    groups.append(tile)
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


def noise(nt, vec, scale, detail, roughness):
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = roughness
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]


def voronoi(nt, vec, scale, feature="F1"):
    node = nt.nodes.new("ShaderNodeTexVoronoi")
    node.feature = feature
    node.inputs["Scale"].default_value = scale
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Distance"]


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


def shore_zones(nt, col, coord, z, nz, flat=False):
    """The littoral bands on any rock: green weed at the waterline, barnacle
    crust over it, a black lichen band above, all with ragged edges. On the
    flat shelf the bands squeeze down to the water's edge."""
    wl = WATER_LEVEL
    rag = remap(nt, noise(nt, coord, 6.0, 4.0, 0.6), 0.3, 0.7, -0.05, 0.05)
    zz = math_node(nt, "ADD", z, math_node(nt, "MULTIPLY", rag, 0.25 if flat else 1.0))
    if not flat:
        black = math_node(nt, "MULTIPLY", remap(nt, zz, wl + 0.40, wl + 0.26, 0.0, 0.80),
                          remap(nt, zz, wl + 0.06, wl + 0.13, 0.0, 1.0))
        col = mix_color(nt, col, (0.030, 0.028, 0.026), black)
    barn = (remap(nt, zz, wl + 0.035, wl + 0.012, 0.0, 1.0) if flat
            else remap(nt, zz, wl + 0.16, wl + 0.08, 0.0, 1.0))
    dots = voronoi(nt, coord, 170.0)
    col = mix_color(nt, col, (0.050, 0.047, 0.042), math_node(nt, "MULTIPLY", barn, 0.75))
    col = mix_color(nt, col, (0.30, 0.29, 0.26),
                    math_node(nt, "MULTIPLY", barn, remap(nt, dots, 0.16, 0.08, 0.0, 0.6)))
    weed = (remap(nt, zz, wl + 0.02, wl + 0.005, 0.0, 1.0) if flat
            else remap(nt, zz, wl + 0.07, wl + 0.02, 0.0, 1.0))
    col = mix_color(nt, col, (0.045, 0.080, 0.022), math_node(nt, "MULTIPLY", weed, 0.9))
    return col, math_node(nt, "MAXIMUM", barn, weed)


def joint_lines(nt, coord, ang, spacing, width, warp):
    """Straight joint cracks across the shelf: a line every ``spacing``
    across bearing ``ang``, wandering by ``warp``."""
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(coord, dot.inputs[0])
    dot.inputs[1].default_value = (math.cos(ang), math.sin(ang), 0.0)
    u = math_node(nt, "ADD", dot.outputs["Value"], warp)
    s = math_node(nt, "ABSOLUTE", math_node(nt, "SINE", math_node(nt, "MULTIPLY", u, math.pi / spacing), 0.0), 0.0)
    return remap(nt, s, width, 0.0, 0.0, 1.0)


def rock_material():
    mat, nt, bsdf, coord = surface("Sandstone")
    # Bedded sandstone: warm buff hard beds, darker red-grey soft beds, a
    # seeded tone per block, fine laminae, isotropic mottling; the shore
    # zones low on every bed, orange and grey lichen on the upper faces and
    # bird lime streaking down from the tops.
    tone = attr(nt, "Tone")
    hard = attr(nt, "Hard")
    xyz = coord_xyz(nt, coord)
    nz = normal_xyz(nt)["Z"]
    hard_col = ramp(nt, tone, ((0.0, (0.30, 0.215, 0.14)), (0.25, (0.40, 0.29, 0.18)),
                               (0.50, (0.47, 0.32, 0.18)), (0.75, (0.52, 0.40, 0.27)),
                               (1.0, (0.42, 0.24, 0.13))))
    soft_col = ramp(nt, tone, ((0.0, (0.15, 0.10, 0.075)), (0.5, (0.20, 0.13, 0.095)),
                               (1.0, (0.24, 0.17, 0.13))))
    col = mix_color(nt, soft_col, hard_col, hard)
    # each bed its own cast: greyer, redder or paler
    tint = ramp(nt, math_node(nt, "FRACT", math_node(nt, "MULTIPLY", attr(nt, "Layer"), 0.37), 0.0),
                ((0.0, (0.80, 0.84, 0.90)), (0.3, (1.0, 1.0, 1.0)), (0.55, (1.10, 0.92, 0.80)),
                 (0.8, (1.12, 1.08, 1.02)), (1.0, (0.92, 0.88, 0.86))))
    mt = nt.nodes.new("ShaderNodeMix")
    mt.data_type = "RGBA"
    mt.blend_type = "MULTIPLY"
    enabled_socket(mt.inputs, "Factor").default_value = 1.0
    nt.links.new(col, enabled_socket(mt.inputs, "A"))
    nt.links.new(tint, enabled_socket(mt.inputs, "B"))
    col = enabled_socket(mt.outputs, "Result")
    mottle = noise(nt, coord, 3.0, 6.0, 0.62)
    col = mix_color(nt, col, (0.20, 0.13, 0.08), remap(nt, mottle, 0.35, 0.70, 0.40, 0.0))
    col = mix_color(nt, col, (0.62, 0.50, 0.36), remap(nt, mottle, 0.62, 0.78, 0.0, 0.25))
    # iron staining: rusty patches bleeding down from the joints
    rust = noise(nt, mapping(nt, coord, scale=(3.0, 3.0, 0.8)), 2.0, 4.0, 0.6)
    col = mix_color(nt, col, (0.36, 0.16, 0.06), remap(nt, rust, 0.58, 0.72, 0.0, 0.45))
    # laminae: faint bands across each bed, broken by a warp
    warp = noise(nt, coord, 4.0, 2.0, 0.5)
    lam = math_node(nt, "SINE", math_node(nt, "MULTIPLY", math_node(nt, "ADD", xyz["Z"],
                                                                     math_node(nt, "MULTIPLY", warp, 0.03)),
                                          TAU * 36.0), 0.0)
    col = mix_color(nt, col, (0.16, 0.10, 0.06), remap(nt, lam, 0.6, 1.0, 0.0, 0.10))
    grain = noise(nt, coord, 140.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.10, 0.07, 0.045), remap(nt, grain, 0.40, 0.70, 0.40, 0.0))
    # tafoni: the honeycomb pitting of sea-weathered sandstone on the walls
    pits = voronoi(nt, coord, 38.0)
    side = remap(nt, nz, 0.55, 0.25, 0.0, 1.0)
    pit = math_node(nt, "MULTIPLY", remap(nt, pits, 0.34, 0.16, 0.0, 1.0),
                    math_node(nt, "MULTIPLY", side, remap(nt, noise(nt, coord, 2.8, 2.0, 0.5), 0.55, 0.66, 0.0, 1.0)))
    col = mix_color(nt, col, (0.12, 0.08, 0.05), math_node(nt, "MULTIPLY", pit, 0.55))
    # overhung undersides stay dark and damp
    col = mix_color(nt, col, (0.07, 0.05, 0.035), remap(nt, nz, -0.3, -0.9, 0.0, 0.6))
    # runoff: dark streaks down the walls, and a green film low and in the shade
    side_n = remap(nt, nz, 0.6, 0.2, 0.0, 1.0)
    runoff = noise(nt, mapping(nt, coord, scale=(9.0, 9.0, 2.2)), 1.0, 3.0, 0.55)
    col = mix_color(nt, col, (0.12, 0.09, 0.065),
                    math_node(nt, "MULTIPLY", side_n, remap(nt, runoff, 0.50, 0.68, 0.0, 0.35)))
    film = noise(nt, coord, 2.4, 4.0, 0.55)
    greenz = math_node(nt, "MULTIPLY", remap(nt, xyz["Z"], 0.75, 0.30, 0.0, 1.0),
                       remap(nt, film, 0.50, 0.66, 0.0, 0.45))
    col = mix_color(nt, col, (0.10, 0.12, 0.05), math_node(nt, "MULTIPLY", greenz, side_n))
    # lichens on the upper faces, high up
    up = math_node(nt, "MULTIPLY", remap(nt, nz, 0.2, 0.7, 0.0, 1.0),
                   remap(nt, xyz["Z"], 0.55, 0.85, 0.0, 1.0))
    ros = voronoi(nt, coord, 9.0)
    ora = math_node(nt, "MULTIPLY", remap(nt, ros, 0.14, 0.07, 0.0, 0.9),
                    remap(nt, noise(nt, coord, 2.4, 2.0, 0.5), 0.52, 0.62, 0.0, 1.0))
    col = mix_color(nt, col, (0.62, 0.30, 0.05), math_node(nt, "MULTIPLY", ora, up))
    grey = math_node(nt, "MULTIPLY", remap(nt, voronoi(nt, coord, 6.0), 0.20, 0.10, 0.0, 0.8),
                     remap(nt, noise(nt, coord, 3.3, 2.0, 0.5), 0.55, 0.66, 0.0, 1.0))
    col = mix_color(nt, col, (0.42, 0.42, 0.37), math_node(nt, "MULTIPLY", grey,
                                                           remap(nt, xyz["Z"], 0.40, 0.70, 0.0, 1.0)))
    # bird lime: pale streaks down the upper walls
    streak = noise(nt, mapping(nt, coord, scale=(26.0, 26.0, 1.6)), 1.0, 3.0, 0.5)
    lime = math_node(nt, "MULTIPLY", remap(nt, streak, 0.60, 0.72, 0.0, 0.85),
                     math_node(nt, "MULTIPLY", remap(nt, xyz["Z"], 0.70, 1.00, 0.0, 1.0),
                               remap(nt, noise(nt, coord, 1.6, 2.0, 0.5), 0.50, 0.60, 0.0, 1.0)))
    col = mix_color(nt, col, (0.70, 0.69, 0.63), math_node(nt, "MULTIPLY", lime,
                                                           remap(nt, nz, 0.6, 0.2, 0.0, 1.0)))
    col, wet = shore_zones(nt, col, coord, xyz["Z"], nz)
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(math_node(nt, "SUBTRACT", remap(nt, grain, 0.3, 0.7, 0.80, 0.93),
                           math_node(nt, "MULTIPLY", wet, 0.40)), bsdf.inputs["Roughness"])
    add_bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "MULTIPLY", mottle, 0.6),
                                 math_node(nt, "ADD", math_node(nt, "MULTIPLY", grain, 0.35),
                                           math_node(nt, "MULTIPLY", pit, -0.8))), 0.45, 0.012)
    return mat


def shelf_material():
    mat, nt, bsdf, coord = surface("WaveCutShelf")
    # The wave-cut platform: the same sandstone scoured flat, dark and wet,
    # with a network of joints, weed films, barnacles near the water, and
    # the beds in section down the tile's edge.
    xyz = coord_xyz(nt, coord)
    nz = normal_xyz(nt)["Z"]
    mottle = noise(nt, coord, 3.5, 6.0, 0.6)
    col = ramp(nt, mottle, ((0.30, (0.066, 0.063, 0.058)), (0.55, (0.105, 0.098, 0.088)),
                            (0.80, (0.150, 0.138, 0.120))))
    # the beds in the tile's cut edge
    bands = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", xyz["Z"], math_node(nt, "MULTIPLY", noise(nt, coord, 5.0, 2.0, 0.5), 0.012)), 11.0), 0.0)
    edge = remap(nt, nz, 0.75, 0.35, 0.0, 1.0)
    band_col = ramp(nt, bands, ((0.0, (0.13, 0.095, 0.065)), (0.55, (0.15, 0.11, 0.075)),
                                (0.62, (0.10, 0.07, 0.05)), (1.0, (0.105, 0.075, 0.055))))
    col = mix_color(nt, col, band_col, edge)
    # the same two joint sets that split the headland, running on across the shelf
    warp = math_node(nt, "MULTIPLY", noise(nt, coord, 2.5, 3.0, 0.5), 0.06)
    crack = math_node(nt, "MAXIMUM", joint_lines(nt, coord, 0.0, 0.26, 0.05, warp),
                      math_node(nt, "MULTIPLY", joint_lines(nt, coord, math.pi / 2 + 0.08, 0.37, 0.04, warp),
                                remap(nt, noise(nt, coord, 1.7, 2.0, 0.5), 0.40, 0.55, 0.0, 1.0)))
    col = mix_color(nt, col, (0.030, 0.024, 0.018), math_node(nt, "MULTIPLY", crack,
                                                              remap(nt, nz, 0.6, 0.9, 0.0, 0.85)))
    film = noise(nt, coord, 2.2, 4.0, 0.55)
    top = remap(nt, nz, 0.75, 0.92, 0.0, 1.0)
    col = mix_color(nt, col, (0.050, 0.075, 0.026),
                    math_node(nt, "MULTIPLY", top, remap(nt, film, 0.52, 0.68, 0.0, 0.65)))
    col = mix_color(nt, col, (0.20, 0.15, 0.10),
                    math_node(nt, "MULTIPLY", top, remap(nt, film, 0.30, 0.18, 0.0, 0.35)))
    pools = remap(nt, noise(nt, coord, 9.0, 3.0, 0.6), 0.55, 0.75, 0.0, 1.0)
    col = mix_color(nt, col, (0.07, 0.05, 0.035), math_node(nt, "MULTIPLY", pools, 0.5))
    # the tile's cut edge stays out of the tide zones
    col, wet = shore_zones(nt, col, coord, math_node(nt, "ADD", xyz["Z"], remap(nt, nz, 0.6, 0.3, 0.0, 1.0)),
                           nz, flat=True)
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(math_node(nt, "SUBTRACT", 0.80, math_node(nt, "MULTIPLY", math_node(nt, "MAXIMUM", wet, pools),
                                                           0.40)), bsdf.inputs["Roughness"])
    add_bump(nt, bsdf, math_node(nt, "ADD", mottle, math_node(nt, "MULTIPLY", crack, -0.6)), 0.4, 0.01)
    return mat


def water_material():
    mat, nt, bsdf, coord = surface("SeaWater")
    depth = remap(nt, attr(nt, "Depth"), 0.0, 0.08, 0.0, 1.0)
    col = ramp(nt, depth, ((0.00, (0.10, 0.20, 0.16)), (0.25, (0.045, 0.16, 0.15)),
                           (0.60, (0.018, 0.085, 0.095)), (1.00, (0.008, 0.040, 0.055))))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.08
    bsdf.inputs["IOR"].default_value = 1.33
    try:
        bsdf.inputs["Specular IOR Level"].default_value = 0.45
    except KeyError:
        pass
    ruffle = noise(nt, mapping(nt, coord, scale=(1.0, 1.8, 1.0)), 30.0, 3.0, 0.5)
    add_bump(nt, bsdf, ruffle, 0.10, 0.002)
    return mat


def foam_material():
    mat, nt, bsdf, coord = surface("Foam")
    # lacy foam: white where it piles against the rock, breaking into
    # cells and streaks out over the water
    fx = attr(nt, "FoamX")
    cells = voronoi(nt, mapping(nt, coord, scale=(1.0, 1.0, 1.0)), 55.0, "DISTANCE_TO_EDGE")
    lace = remap(nt, cells, 0.004, 0.030, 1.0, 0.0)
    body = remap(nt, fx, 0.05, 0.55, 0.95, 0.0)
    amount = math_node(nt, "MAXIMUM", body, math_node(nt, "MULTIPLY", lace,
                                                      remap(nt, fx, 0.3, 1.0, 0.85, 0.25)))
    amount = math_node(nt, "MULTIPLY", amount, remap(nt, noise(nt, coord, 18.0, 3.0, 0.6), 0.30, 0.55, 0.45, 1.0))
    col = mix_color(nt, (0.035, 0.12, 0.12), (0.72, 0.76, 0.74), amount)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    add_bump(nt, bsdf, lace, 0.3, 0.002)
    return mat


def cobble_material():
    mat, nt, bsdf, coord = surface("Cobble")
    # rounded beach boulders of a darker, harder stone: grey-blue dolerite
    # and pale quartzite, speckled, with barnacles low down
    tone = attr(nt, "Tone")
    xyz = coord_xyz(nt, coord)
    nz = normal_xyz(nt)["Z"]
    col = ramp(nt, tone, ((0.0, (0.10, 0.10, 0.11)), (0.45, (0.17, 0.17, 0.18)),
                          (0.70, (0.30, 0.27, 0.23)), (1.0, (0.42, 0.38, 0.33))))
    speck = noise(nt, coord, 150.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.05, 0.05, 0.055), remap(nt, speck, 0.60, 0.72, 0.0, 0.6))
    col, wet = shore_zones(nt, col, coord, xyz["Z"], nz)
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(math_node(nt, "SUBTRACT", 0.60, math_node(nt, "MULTIPLY", wet, 0.30)),
                 bsdf.inputs["Roughness"])
    add_bump(nt, bsdf, speck, 0.2, 0.002)
    return mat


def turf_material():
    mat, nt, bsdf, coord = surface("ClifftopTurf")
    # close-cropped sea turf: tussocky, yellowing in patches, dark between
    # the tussocks, bare soil showing at the frayed edge
    fuzz = noise(nt, coord, 260.0, 3.0, 0.7)
    tuss = voronoi(nt, mapping(nt, coord, scale=(1.0, 1.0, 1.0)), 30.0, "DISTANCE_TO_EDGE")
    patch = noise(nt, coord, 7.0, 3.0, 0.5)
    col = ramp(nt, patch, ((0.3, (0.040, 0.075, 0.016)), (0.55, (0.070, 0.115, 0.024)),
                           (0.80, (0.13, 0.14, 0.045))))
    col = mix_color(nt, col, (0.20, 0.17, 0.07), remap(nt, patch, 0.66, 0.80, 0.0, 0.55))
    col = mix_color(nt, col, (0.012, 0.022, 0.006), remap(nt, tuss, 0.0, 0.10, 0.75, 0.0))
    col = mix_color(nt, col, (0.015, 0.025, 0.008), remap(nt, fuzz, 0.30, 0.70, 0.6, 0.0))
    nz = normal_xyz(nt)["Z"]
    col = mix_color(nt, col, (0.09, 0.06, 0.035), remap(nt, nz, 0.75, 0.35, 0.0, 0.8))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    add_bump(nt, bsdf, math_node(nt, "ADD", fuzz, remap(nt, tuss, 0.0, 0.15, 0.0, 1.2)), 1.0, 0.006)
    return mat


def grass_material():
    mat, nt, bsdf, coord = surface("SeaGrass")
    tone = attr(nt, "Tone")
    tip = attr(nt, "Tip")
    col = ramp(nt, tone, ((0.0, (0.090, 0.190, 0.035)), (0.45, (0.150, 0.270, 0.055)),
                          (0.70, (0.230, 0.310, 0.075)), (0.80, (0.060, 0.120, 0.050)),
                          (1.0, (0.080, 0.150, 0.070))))
    col = mix_color(nt, col, (0.55, 0.47, 0.24), remap(nt, tip, 0.55, 1.0, 0.0, 0.6))
    col = mix_color(nt, col, (0.03, 0.05, 0.015), remap(nt, tip, 0.25, 0.0, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.6
    translucent(nt, bsdf, (0.12, 0.22, 0.05), 0.2)
    return mat


def thrift_material():
    mat, nt, bsdf, coord = surface("SeaThrift")
    # sea-pink heads: papery florets from pale pink to deep rose
    tone = attr(nt, "Tone")
    florets = voronoi(nt, coord, 420.0)
    col = ramp(nt, tone, ((0.0, (0.75, 0.30, 0.46)), (0.5, (0.85, 0.42, 0.58)),
                          (1.0, (0.92, 0.60, 0.72))))
    col = mix_color(nt, col, (0.45, 0.10, 0.25), remap(nt, florets, 0.30, 0.10, 0.0, 0.55))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    add_bump(nt, bsdf, florets, 0.5, 0.002)
    return mat


def piece_materials():
    """Eight slots, in index order: shared by the check and the render."""
    return (rock_material(), shelf_material(), water_material(), foam_material(), cobble_material(),
            turf_material(), grass_material(), thrift_material())


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
    def __init__(self, me, verts, polys, part_of, ident_of, layer_of, hard_of):
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
        self.layer = layer_of[polys[0].index] if polys else -1
        self.hard = hard_of[polys[0].index] if polys else 0
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
    layer = face_vals(me, "Layer")
    hard = face_vals(me, "Hard")
    all_ = [Shell(me, g, by_shell[si], part, ident, layer, hard) for si, g in enumerate(groups)]

    def of(*kinds):
        return [s for s in all_ if s.part in kinds]

    beds = {}
    for s in of(P_BED):
        beds.setdefault(s.ident // 100, {})[s.ident % 100] = s
    return {"groups": groups, "all": all_, "tile": of(P_TILE), "beds": beds,
            "sea": of(P_SEA), "pools": of(P_POOL), "foam": of(P_FOAM), "talus": of(P_TALUS),
            "boulders": of(P_BOULDER), "turf": of(P_TURF), "cover": of(*COVER_PARTS)}


PARITY_DIRS = (Vector((0.31, 0.22, 0.925)).normalized(), Vector((-0.57, 0.61, -0.55)).normalized(),
               Vector((0.72, -0.44, 0.53)).normalized())


def inside(tree, p):
    """Ray parity, by majority over three directions."""
    votes = 0
    for d in PARITY_DIRS:
        count, o = 0, p.copy()
        for _ in range(64):
            loc, _n, _i, _d = tree.ray_cast(o, d, 30.0)
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


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 12.0)), Vector((0.0, 0.0, -1.0)), 30.0)
    return None if loc is None else loc.z


def ring_pts(me, shell, ring_of, r):
    return [me.vertices[v].co.copy() for v in shell.verts if ring_of[v] == r]


def bite_audit(me, cls):
    """Every soft bed's end rings: the shallowest vertex inside the hard bed
    it runs into (the lintel's lowest bed over each leg)."""
    ring_of = vert_vals(me, "Ring")
    out = []
    lintel = []
    for bid, column in cls["beds"].items():
        key = [k for k in BODY_ORDER if BODIES[k]["id"] == bid][0]
        for layer, s in column.items():
            if s.hard:
                continue
            nr = max(ring_of[v] for v in s.verts)
            for other, ring in ((layer - 1, 0), (layer + 1, nr)):
                host = column.get(other)
                if host is None and other == LINTEL_LAYER and key in ("A", "B"):
                    host = cls["beds"].get(BODIES["L"]["id"], {}).get(LINTEL_LAYER)
                if host is None or not host.hard:
                    continue
                depth = min(signed_depth(host.tree, p) for p in ring_pts(me, s, ring_of, ring))
                out.append(depth)
                if other == LINTEL_LAYER and key in ("A", "B"):
                    lintel.append((key, depth))
    return out, lintel


def flank_bury(pts, ground):
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


def sector_bury(pts, ground):
    """Per sector about the plan centroid, the most-buried vertex under the
    ground straight above it."""
    cx = sum(p.x for p in pts) / len(pts)
    cy = sum(p.y for p in pts) / len(pts)
    best = [-9.0] * SECTORS
    for p in pts:
        k = min(SECTORS - 1, int((math.atan2(p.y - cy, p.x - cx) % TAU) / TAU * SECTORS))
        g = ground(p.x, p.y)
        if g is not None:
            best[k] = max(best[k], g - p.z)
    return best


def seal_audit(cls):
    """The legs' and the stack's feet: per sector the most-buried flank vertex."""
    tile = cls["tile"][0]
    out = {}
    for key in ("A", "B", "S"):
        s = cls["beds"].get(BODIES[key]["id"], {}).get(0)
        if s is None:
            out[key] = [-9.0] * SECTORS
            continue
        out[key] = sector_bury(s.pts, lambda x, y: ray_down(tile.tree, x, y))
    return out


def rock_tree(me, shells_):
    pts, polys, base = [], [], 0
    for s in shells_:
        remap_ = {vi: base + n for n, vi in enumerate(s.verts)}
        pts += [tuple(p) for p in s.pts]
        polys += [[remap_[v] for v in p.vertices] for p in s.polys]
        base += len(s.verts)
    return BVHTree.FromPolygons(pts, polys)


def aperture_audit(me, cls):
    """Rays along +Y through the opening: the clear height up the centre
    line from the water, and the narrowest clear width over that height."""
    beds = [s for col in cls["beds"].values() for s in col.values()]
    tree = rock_tree(me, beds)
    tile = cls["tile"][0]

    def clear(x, z):
        loc, _n, _i, _d = tree.ray_cast(Vector((x, -3.0, z)), Vector((0.0, 1.0, 0.0)), 6.0)
        return loc is None

    floor = max(WATER_LEVEL, ray_down(tile.tree, APER_X, 0.34) or 0.0)
    z = floor + 0.005
    while z < 2.0 and clear(APER_X, z):
        z += 0.004
    height = z - floor
    width = 9.0
    zz = floor + 0.03
    while zz <= floor + 0.03 + APER_H_MIN:
        if not clear(APER_X, zz):
            width = 0.0
            break
        lo = hi = APER_X
        while clear(lo - 0.004, zz) and lo > APER_X - 1.0:
            lo -= 0.004
        while clear(hi + 0.004, zz) and hi < APER_X + 1.0:
            hi += 0.004
        width = min(width, hi - lo)
        zz += 0.02
    return width, height


def level_audit(me, cls):
    """Every hard bed's top: a least-squares plane through its top-cap
    vertices, its tilt, and per layer the spread of its height across the
    columns at a common point."""
    cap = face_vals(me, "Cap")
    tilts = []
    per_layer = {}
    for bid, column in cls["beds"].items():
        for layer, s in column.items():
            if not s.hard:
                continue
            vs = set()
            for p in s.polys:
                if cap[p.index] == 2:
                    vs.update(p.vertices)
            pts = [me.vertices[v].co for v in vs]
            n = len(pts)
            if n < 3:
                continue
            mx = sum(p.x for p in pts) / n
            my = sum(p.y for p in pts) / n
            mz = sum(p.z for p in pts) / n
            sxx = sum((p.x - mx) ** 2 for p in pts)
            syy = sum((p.y - my) ** 2 for p in pts)
            sxy = sum((p.x - mx) * (p.y - my) for p in pts)
            sxz = sum((p.x - mx) * (p.z - mz) for p in pts)
            syz = sum((p.y - my) * (p.z - mz) for p in pts)
            det = sxx * syy - sxy * sxy
            a = (sxz * syy - syz * sxy) / det
            b = (syz * sxx - sxz * sxy) / det
            tilts.append(math.degrees(math.atan(math.hypot(a, b))))
            # the fitted height at a common point on the fin's centre line
            per_layer.setdefault(layer, []).append(mz + a * (APER_X - mx) + b * (0.34 - my))
    spread = max((max(v) - min(v)) for v in per_layer.values() if len(v) > 1)
    return tilts, spread, per_layer


def notch_audit(me, cls):
    """Each soft bed's middle ring: how far the hard beds either side stand
    out past it, along its own outward normal at their mid-height. The
    median over the ring, per bed."""
    ring_of = vert_vals(me, "Ring")
    out = []
    for bid, column in cls["beds"].items():
        key = [k for k in BODY_ORDER if BODIES[k]["id"] == bid][0]
        for layer, s in column.items():
            if s.hard:
                continue
            ring = [me.vertices[v] for v in s.verts if ring_of[v] == 2]
            ring.sort(key=lambda v: v.index)
            hosts = []
            for other in (layer - 1, layer + 1):
                h = column.get(other)
                if h is None and other == LINTEL_LAYER and key in ("A", "B"):
                    continue
                if h is not None and h.hard:
                    hosts.append(h)
            if not hosts:
                continue
            n = len(ring)
            recess = []
            for i in range(n):
                a, b = ring[i - 1].co, ring[(i + 1) % n].co
                t = b - a
                nrm = Vector((t.y, -t.x, 0.0))
                if nrm.length < 1e-9:
                    continue
                nrm.normalize()
                p = ring[i].co
                ds = []
                for h in hosts:
                    zmid = 0.5 * (h.lo.z + h.hi.z)
                    q = Vector((p.x, p.y, zmid))
                    loc, _n, _i, d = h.tree.ray_cast(q, nrm, 1.0)
                    ds.append(d if loc is not None else 0.0)
                recess.append(min(ds))
            recess.sort()
            out.append((key, layer, recess[len(recess) // 2]))
    return out


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
    """The sea's top: median height and largest excursion from it. Each
    pool: its top's spread."""
    sea = cls["sea"][0]
    _top, verts, _rim = water_top(me, sea)
    zs = sorted(me.vertices[v].co.z for v in verts)
    med = zs[len(zs) // 2]
    exc = max(abs(z - med) for z in zs)
    pools = []
    for s in cls["pools"]:
        _t, pv, _r = water_top(me, s)
        pz = [me.vertices[v].co.z for v in pv]
        pools.append(max(pz) - min(pz))
    return med, exc, pools


def enclose_audit(me, cls):
    """The platform over every rim vertex and rim-edge midpoint of every
    water sheet's top."""
    tile = cls["tile"][0]
    worst = 9.0
    n = 0
    for s in cls["sea"] + cls["pools"]:
        _t, _v, rim = water_top(me, s)
        for a, b in rim:
            pa, pb = me.vertices[a].co, me.vertices[b].co
            for p in (pa, (pa + pb) * 0.5):
                g = ray_down(tile.tree, p.x, p.y)
                worst = min(worst, -9.0 if g is None else g - p.z)
                n += 1
    return worst, n


def foam_audit(me, cls):
    """Every foam vertex within a band of the sea's level, and every vertex
    of its land edge's top under the platform."""
    tile = cls["tile"][0]
    fx = vert_vals(me, "FoamX", float)
    dev = 0.0
    tuck = 9.0
    for s in cls["foam"]:
        top = max(p.z for p in s.pts)
        for v in s.verts:
            co = me.vertices[v].co
            dev = max(dev, abs(co.z - WATER_LEVEL))
            if fx[v] < 0.5 and co.z > WATER_LEVEL:
                g = ray_down(tile.tree, co.x, co.y)
                tuck = min(tuck, -9.0 if g is None else g - co.z)
        _ = top
    return dev, tuck, len(cls["foam"])


def volume_centroid(me, shells_):
    vol = 0.0
    acc = Vector((0.0, 0.0, 0.0))
    for s in shells_:
        for poly in s.polys:
            vs = [me.vertices[i].co for i in poly.vertices]
            for k in range(1, len(vs) - 1):
                a, b, c = vs[0], vs[k], vs[k + 1]
                v6 = a.dot(b.cross(c))
                vol += v6
                acc += v6 * (a + b + c)
    return acc / (4.0 * vol), vol / 6.0


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
    best = 9.0
    outside = 0.0
    for a, b in zip(hull, hull[1:] + hull[:1]):
        ex, ey = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ex, ey)
        d = (ex * (y - a[1]) - ey * (x - a[0])) / ln
        best = min(best, d)
        if d < 0.0:
            t = min(max(((x - a[0]) * ex + (y - a[1]) * ey) / (ln * ln), 0.0), 1.0)
            outside = max(outside, math.hypot(x - a[0] - t * ex, y - a[1] - t * ey))
    return best if best >= 0.0 else -outside


def stack_audit(me, cls):
    """The stack's mass centre (every bed) against the footprint of its
    narrowest section, the notch at its foot."""
    ring_of = vert_vals(me, "Ring")
    column = cls["beds"].get(BODIES["S"]["id"], {})
    c, vol = volume_centroid(me, list(column.values()))
    foot = column[0]
    hull = hull2d([(me.vertices[v].co.x, me.vertices[v].co.y) for v in foot.verts if ring_of[v] == 2])
    return hull_margin(hull, c.x, c.y), c, vol


def loose_audit(cls):
    """Per loose rock, per sector, its most-buried vertex under the
    platform; and every pair of loose rocks that overlap."""
    tile = cls["tile"][0]
    rocks = cls["talus"] + cls["boulders"]
    seals = []
    for s in rocks:
        cx = sum(p.x for p in s.pts) / len(s.pts)
        cy = sum(p.y for p in s.pts) / len(s.pts)
        best = [-9.0] * SECTORS
        for p in s.pts:
            k = min(SECTORS - 1, int((math.atan2(p.y - cy, p.x - cx) % TAU) / TAU * SECTORS))
            g = ray_down(tile.tree, p.x, p.y)
            if g is not None:
                best[k] = max(best[k], g - p.z)
        seals.append(min(best))
    pairs = 0
    for i in range(len(rocks)):
        for j in range(i + 1, len(rocks)):
            a, b = rocks[i], rocks[j]
            if (a.lo.x > b.hi.x or b.lo.x > a.hi.x or a.lo.y > b.hi.y or b.lo.y > a.hi.y):
                continue
            if a.tree.overlap(b.tree):
                pairs += 1
    return seals, pairs, len(rocks)


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


def cover_audit(me, cls):
    """Every blade's and stalk's root (its base cap) inside the turf or the
    top bed under it; every head, blade and stalk joined to its top."""
    cap = face_vals(me, "Cap")
    depths = []
    loose = 0
    for key in ("L", "S"):
        bid = BODIES[key]["id"]
        top_layer = max(cls["beds"][bid])
        host_bed = cls["beds"][bid][top_layer]
        turf = [s for s in cls["turf"] if s.ident == bid]
        hosts = turf + [host_bed]
        mine = [s for s in cls["cover"] if s.ident == bid]
        for s in mine:
            if s.part == P_HEAD:
                continue
            vs = set()
            for p in s.polys:
                if cap[p.index] == 1:
                    vs.update(p.vertices)
            d = min(max(signed_depth(h.tree, me.vertices[v].co) for h in hosts) for v in vs)
            depths.append(d)
        roots = union_components(hosts + mine)
        loose += sum(1 for r in roots[len(hosts):] if r not in roots[:len(hosts)])
    return depths, loose


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
    img = bpy.data.images.new("RockNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = ROCK_IDX
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


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    plan = plan_scene()
    low = build_mesh("SeaStackLow", plan, "low", **flags)
    high = build_mesh("SeaStackHigh", plan, "high", **flags)
    mats = piece_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    rock_mat = mats[ROCK_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
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
    n_beds = sum(len(BODIES[k]["layers"]) for k in BODY_ORDER)
    got_beds = sum(len(c) for c in cls["beds"].values())
    if len(cls["tile"]) != 1 or len(cls["sea"]) != 1 or got_beds != n_beds:
        return (fail(f"tile/sea/beds not found: {len(cls['tile'])}/{len(cls['sea'])}/{got_beds} of "
                     f"{n_beds} beds", 3),) + none2
    bites, lintel = bite_audit(low.data, cls)
    seals = seal_audit(cls)
    ap_w, ap_h = aperture_audit(low.data, cls)
    tilts, spread, per_layer = level_audit(low.data, cls)
    notches = notch_audit(low.data, cls)
    w_med, w_exc, pool_flat = water_audit(low.data, cls)
    enclose, n_rim = enclose_audit(low.data, cls)
    foam_dev, foam_tuck, n_foam = foam_audit(low.data, cls)
    tip, s_c, s_vol = stack_audit(low.data, cls)
    rest, pairs, n_rocks = loose_audit(cls)
    roots, loose = cover_audit(low.data, cls)

    img, tex = setup_bake_image(low, rock_mat)
    if img is None:
        return (fail("no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "SeaStackLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "SeaStackLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(build_collider_source(plan), "SeaStackCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_sea_stack_arch_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} beds={got_beds} talus={len(cls['talus'])} "
          f"boulders={len(cls['boulders'])} foam={n_foam} pools={len(cls['pools'])} "
          f"turf={len(cls['turf'])} cover={len(cls['cover'])}")
    print(f"measured bites min={min(bites):.4f} max={max(bites):.4f} n={len(bites)} "
          f"lintel={[(k, round(d, 4)) for k, d in lintel]}")
    print("measured seal " + " ".join(f"{k}:{min(v):.4f}/{sum(1 for b in v if b >= SEAL_EPS)}"
                                      for k, v in seals.items()))
    print(f"measured aperture width={ap_w:.4f} height={ap_h:.4f}")
    print(f"measured level tilt max={max(tilts):.4f}deg n={len(tilts)} spread={spread:.5f} "
          + " ".join(f"L{k}:{min(v):.4f}..{max(v):.4f}" for k, v in sorted(per_layer.items())))
    print("measured notch " + " ".join(f"{k}{layer}:{d:.4f}" for k, layer, d in notches))
    print(f"measured water median={w_med:.5f} excursion={w_exc:.5f} pools_flat="
          f"{[round(p, 5) for p in pool_flat]} enclose={enclose:.5f} n={n_rim}")
    print(f"measured foam dev={foam_dev:.5f} tuck={foam_tuck:.5f} loops={n_foam}")
    print(f"measured stack tip_margin={tip:.4f} centre=({s_c.x:.3f},{s_c.y:.3f},{s_c.z:.3f}) vol={s_vol:.4f}")
    print(f"measured loose rest min={min(rest):.4f} max={max(rest):.4f} n={n_rocks} overlaps={pairs}")
    print(f"measured cover roots min={min(roots):.4f} max={max(roots):.4f} n={len(roots)} loose={loose}")

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
    n_pairs = sum(1 for k in BODY_ORDER for layer in BODIES[k]["layers"] if not HARD[layer]
                  for o in (layer - 1, layer + 1) if o in BODIES[k]["layers"]
                  or (o == LINTEL_LAYER and k in ("A", "B")))
    if (len(bites) != n_pairs or len(lintel) != 2 or min(bites) < BED_BITE[0]
            or max(bites) > BED_BITE[1]):
        return (fail(f"beds bite: {len(bites)}/{n_pairs} joints, shallowest {min(bites):.4f} m, "
                     f"deepest {max(bites):.4f} m (band {BED_BITE}); lintel on the legs "
                     f"{[(k, round(d, 4)) for k, d in lintel]}", 17),) + none2
    if tip < TIP_MIN:
        return (fail(f"stack: mass centre {tip:.4f} m inside its footprint (min {TIP_MIN})", 19),) + none2
    worst = min(min(v) for v in seals.values())
    if worst < SEAL_EPS:
        return (fail(f"feet sealed: worst sector {worst:.4f} m under the platform (min {SEAL_EPS}); "
                     + ", ".join(f"{k} {sum(1 for b in v if b >= SEAL_EPS)}/{SECTORS}"
                                 for k, v in seals.items()), 20),) + none2
    if ap_w < APER_W_MIN or ap_h < APER_H_MIN:
        return (fail(f"aperture: clear width {ap_w:.4f} m (min {APER_W_MIN}), clear height "
                     f"{ap_h:.4f} m (min {APER_H_MIN})", 21),) + none2
    n_hard = sum(1 for k in BODY_ORDER for layer in BODIES[k]["layers"] if HARD[layer])
    if len(tilts) != n_hard or max(tilts) > TILT_MAX_DEG or spread > LEVEL_TOL:
        return (fail(f"bedding: {len(tilts)}/{n_hard} bed tops, steepest {max(tilts):.3f} deg "
                     f"(max {TILT_MAX_DEG}), layer spread {spread:.5f} m (max {LEVEL_TOL})", 22),) + none2
    n_soft = sum(1 for k in BODY_ORDER for layer in BODIES[k]["layers"] if not HARD[layer])
    bad = [(k, layer, round(d, 4)) for k, layer, d in notches
           if not (NOTCH_BAND[0] <= d <= NOTCH_BAND[1])]
    if len(notches) != n_soft or bad:
        return (fail(f"notch: {len(notches)}/{n_soft} soft beds, out of band {NOTCH_BAND}: {bad[:6]}",
                     23),) + none2
    if (abs(w_med - WATER_LEVEL) > LEVEL_EPS or not (RIPPLE_BAND[0] <= w_exc <= RIPPLE_BAND[1])
            or len(pool_flat) != len(POOLS) or max(pool_flat) > POOL_FLAT):
        return (fail(f"water: median {w_med:.5f} m (level {WATER_LEVEL} +- {LEVEL_EPS}), ripple "
                     f"{w_exc:.5f} m (band {RIPPLE_BAND}), pools {pool_flat} (flat within "
                     f"{POOL_FLAT})", 24),) + none2
    if enclose < ENCLOSE_MIN:
        return (fail(f"water not contained: the platform over its rim {enclose:.5f} m "
                     f"(min {ENCLOSE_MIN})", 25),) + none2
    if n_foam != 2 or foam_dev > FOAM_BAND or foam_tuck < FOAM_TUCK:
        return (fail(f"foam: {n_foam}/2 loops, {foam_dev:.5f} m off the waterline (max {FOAM_BAND}),"
                     f" land edge {foam_tuck:.5f} m under the rock (min {FOAM_TUCK})", 26),) + none2
    n_loose = len(TALUS) + len(BOULDERS)
    if n_rocks != n_loose or min(rest) < PERCH_BAND:
        return (fail(f"loose rock: {n_rocks}/{n_loose}, worst sector {min(rest):.4f} m under the "
                     f"platform (min {PERCH_BAND})", 27),) + none2
    if pairs:
        return (fail(f"loose rock: {pairs} pairs overlap", 28),) + none2
    if min(roots) < ROOT_BAND[0] or max(roots) > ROOT_BAND[1] or loose:
        return (fail(f"cover: roots {min(roots):.4f}..{max(roots):.4f} m in the turf (band "
                     f"{ROOT_BAND}), {loose} pieces not joined to their top", 29),) + none2
    return 0, low, rock_mat


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

    # Key, fill, rim and the warm wedge. The wedge pools behind the arch so
    # the opening reads against it.
    light("Key", (-3.2, -4.0, 4.6), 248.0, 4.0, (1.0, 0.97, 0.93), spread=40.0)
    light("Fill", (4.6, -3.0, 0.8), 36.0, 8.0, (0.72, 0.82, 1.0))
    light("Rim", (-1.2, 3.0, 2.8), 130.0, 3.0, (0.62, 0.78, 1.0))
    light("Wedge", (0.9, 2.5, 1.7), 240.0, 5.0, (1.0, 0.72, 0.44),
          target=(-0.3, WALL_Y - 0.1, 1.1))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.22, -0.975, 0.0)).normalized()
    cam.location = centre + view * 5.4 + Vector((0.0, 0.0, 0.60))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.05))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the stone.
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 30
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return fail("render produced no file", 14)
    return 0


FLAG_NAMES = ("gap_lintel", "lean_stack", "cut_pillar", "close_arch", "tilt_beds", "flush_beds",
              "flat_sea", "short_sea", "lift_foam", "perch_talus", "pile_talus", "float_cover")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--gap-lintel", action="store_true")
    p.add_argument("--lean-stack", action="store_true")
    p.add_argument("--cut-pillar", action="store_true")
    p.add_argument("--close-arch", action="store_true")
    p.add_argument("--tilt-beds", action="store_true")
    p.add_argument("--flush-beds", action="store_true")
    p.add_argument("--flat-sea", action="store_true")
    p.add_argument("--short-sea", action="store_true")
    p.add_argument("--lift-foam", action="store_true")
    p.add_argument("--perch-talus", action="store_true")
    p.add_argument("--pile-talus", action="store_true")
    p.add_argument("--float-cover", action="store_true")
    args = p.parse_args(argv)

    code, low, _rock = check(
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
    print("sea-stack-arch OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
