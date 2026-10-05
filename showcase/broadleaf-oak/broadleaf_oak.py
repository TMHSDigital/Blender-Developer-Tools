"""Game-ready English oak — a showcase piece, not an example.

Asserts budget conformance of a procedural mature, open-grown English oak
(Quercus robur) after composing shipped pipeline pieces: bmesh construction,
UVs, nine materials, high-to-low normal bake, LOD chain, convex trunk
collider, Unity glTF export.

The trunk is one massive lathe from a buttressed, fluted, deeply plated
foot bedded in a grassy mound to a low fork. Seven surface roots leave the
buttresses and dive into the soil. Five heavy, zig-zag scaffold limbs rise
out of the fork, the low ones reaching out sideways nearly level, and
divide three more times; every branch is a tapered tube that starts inside
its parent, and a parent narrows past each junction by the area of the
child it gives off (da Vinci's rule). The crown is built of cushions: on
every live branch end, and along the outer part of every branch that
carries twigs, a small hidden core holds the carrier, a ring of faceted
leaf clusters bites into the core, and the outer clusters carry small
lobed oak leaves. Cluster shading follows its cushion (custom normals), so
the dome reads as lit billows over dark gaps. A few twigs are dead. Acorns
hang on stalks under the crown, and more lie in the grass among fallen
leaves, twigs and tufts.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-branches`` every branch
seated in its parent, ``--pop-nuts`` every nut seated in its cup,
``--lean-crown`` trunk plumb, ``--fat-twigs`` the taper and area rule,
``--perch-trunk`` / ``--arch-roots`` the trunk and roots sealed in the
soil, ``--orphan-clump`` / ``--scatter-clusters`` / ``--shed-leaves``
every cushion on its carrier, every cluster in its core and every leaf in
its cluster, ``--drop-acorns`` the hanging acorns on their stalks,
``--float-cover`` the ground cover bedded in the soil.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python broadleaf_oak.py --
    blender --background --python broadleaf_oak.py -- --skip-decimate
    blender --background --python broadleaf_oak.py -- --output oak.png
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
from mathutils.geometry import intersect_line_line, intersect_ray_tri
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

SEED = 1802
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- Ground ------------------------------------------------------------------
SOIL_A = (4.40, 4.10)   # soil disc half-axes before the wobble, m
SOIL_N = 36
SOIL_H0 = 0.34          # the mound's crown, at the trunk
SOIL_RIM_H = 0.06       # the mound's height where the rim starts to roll off
SLOPE = 0.030           # and it rises a little toward the back (+Y), m per m
FLARE_HEAP = 0.12       # soil heaped over the root flare round the bole
FLARE_HEAP_R = 1.40
SOIL_EDGE = 0.09        # the rim rolls down over this fraction of the radius
SOIL_FLOOR = 0.02

# --- Trunk -------------------------------------------------------------------
FORK_Z = 2.15           # the fork, above the soil at the axis
TRUNK_R0 = 0.600        # nominal radius at the soil (above the flare)
TRUNK_RF = 0.500        # and at the fork
TRUNK_SIDES = 84
TRUNK_SIDES_HIGH = 144
COLLIDER_SIDES = 14
FLUTES = 8              # broad flutes round the bole
FLUTE_AMP = 0.085
RIDGES = 21             # bark plates between deep furrows
RIDGE_AMP = 0.034
FLARE_R = 0.72          # buttress reach at the soil, on a root's bearing
FLARE_H = 0.42
FLARE_W = 0.27          # buttress half-width, rad
FOOT_OFFS = (-0.045, 0.030)   # foot rings, off the soil under each vertex
UPPER_Z0 = 0.17         # the first level ring above the soil at the axis
UPPER_STEP = 0.15
DOME = ((0.10, 0.94), (0.20, 0.80), (0.29, 0.58), (0.35, 0.30))  # (dz, r factor)
SWAY = (0.016, 0.012)

# --- Roots -------------------------------------------------------------------
ROOTS = 7
ROOT_SIDES = 8
ROOT_RINGS = 18
ROOT_REACH = (1.90, 2.80)
ROOT_R = (0.300, 0.045)

# --- Crown -------------------------------------------------------------------
CROWN_C = Vector((0.0, 0.10, 5.20))   # the crown's envelope centre (absolute)
CROWN_RX = 6.30
CROWN_RY = 5.70
CROWN_RZ = (3.80, 3.50)              # above and below the centre
SCAFFOLDS = 5
SCAFFOLD_ELEV = (8.0, 22.0, 38.0, 55.0, 76.0)
SCAFFOLD_YAW0 = 190.0   # the first (lowest) scaffold's bearing: the low limbs reach out sideways to the hero
SCAFFOLD_AREA = 0.92    # sum of scaffold areas over the trunk's area at the fork
SCAFFOLD_F = (0.52, 0.66)
# per generation: rings, sides, children, child segments (lo), length
# fraction of the envelope, child radius ratio, crook
GEN_RINGS = (11, 8, 6, 4)
GEN_SIDES = (12, 8, 5, 4)
GEN_SIDES_HIGH = (20, 12, 8, 4)
GEN_KIDS = (3, 3, 2, 0)
GEN_SEG_LO = (2, 1, 1, 0)
GEN_F = (None, (0.66, 0.84), (0.70, 0.92), None)
GEN_LMIN = (None, 0.90, 0.60, None)
KEEP = 0.30             # area a parent keeps for its own tip, past its last child
GEN_SHARE = (1.0, 1.0, 0.70)   # of the rest, the share its children take (twigs stay thin)
GEN_CROOK = (0.30, 0.34, 0.34, 0.24)
TWIG_L = (0.38, 0.62)
TAPER = 0.10            # natural thinning along a branch, as area
R_TIP = 0.008
DEAD_TWIGS = 5

# --- Foliage -------------------------------------------------------------------
# Every live branch end carries a clump: a dark, lumpy leaf-mass core
# flattened toward the light, with small lobed leaves set in it.
# Half an oak leaf, petiole to apex: (x along, y across) as fractions of
# its length, lobe tips and sinuses alternating.
LEAF_SIDE = ((0.16, 0.100), (0.29, 0.080), (0.44, 0.180), (0.60, 0.100), (0.77, 0.170))
LEAF_WID = 1.0
LEAF_C = 0.50           # the blade's centre (top and bottom apex), along it
LEAF_WOB = 0.08         # per-lobe width jitter; the rim stays star-shaped from LEAF_C
LEAF_L = (0.24, 0.32)
CORE_R = (0.28, 0.40)   # core radius, interior to outer clumps
CORE_FLAT = 0.62        # along its axis (out of the crown and up)
CORE_JIT = 0.18
BULGE_MIX = 0.60        # a lump's shading normal: out of its cushion, the rest out of the crown
CORE_N = 1              # a core is a jittered cube, hidden in its clusters
SAT_N = (5, 11)         # clusters round a core, interior to outer
SAT_R = (0.25, 0.36)
SAT_OUT = -0.25         # a cluster's centre this many of its radii outside the core's skin
LEAF_P = (0.1, 0.8, 0.5)   # leaves per cluster: int(a + b * exposure + c * hash)
FILLERS = {0: ((6, 1.00), (8, 0.90)), 1: ((2, 1.00), (4, 0.85), (6, 0.90)),
           2: ((2, 0.75), (4, 0.85))}
FILLER_RMAX = 0.36      # a filler core is at least this many times as wide as its branch there
CORE_SEAT = 0.0         # the carrier's tip this many core radii behind its centre
CLUMP_LEAVES = (5, 12)  # interior to outer
LEAF_DEPTH = 0.030      # a leaf's petiole this far under its core's skin
LEAF_LIFT = 1.60        # a blade rises out of the skin this steeply (tan)
CLUMP_ZMIN = -0.50      # leaves cover the core from its pole down to this cos


# --- Acorns ------------------------------------------------------------------
ACORN_S = 1.00
CUP_PROF = ((0.010, 0.000), (0.026, 0.010), (0.032, 0.024), (0.029, 0.032), (0.014, 0.027))
NUT_PROF = ((0.012, 0.000), (0.024, 0.010), (0.026, 0.030), (0.022, 0.052), (0.013, 0.066),
            (0.005, 0.074))
NUT_APEX = 0.080
NUT_SEAT = 0.018        # the nut's foot this far along the axis from the cup's base
ACORN_SIDES = 8
ACORN_CLUSTERS = 6
STALK_L = (0.17, 0.26)

# --- Ground cover --------------------------------------------------------------
TUFTS = 20
LITTER = 70
FALLEN_ACORNS = 12
# fallen twigs: (from, to, radius); a fork is (index of its stick, station, to, radius)
STICKS = (((1.75, -1.55), (2.75, -0.85), 0.024), ((-2.55, -0.70), (-1.60, -1.70), 0.020),
          ((0.55, -2.70), (1.55, -2.95), 0.016), ((-1.30, 2.10), (-0.35, 2.75), 0.018))
STICK_FORKS = ((0, 0.45, (2.05, -0.55), 0.012), (1, 0.55, (-1.70, -1.05), 0.011))
REST_SINK = 0.008       # a lying body's most-buried vertex this far under the soil
TUFT_BURY = 0.020

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (11.529, 11.716, 8.958)
BASE_TRIS_MIN = 86250
BASE_TRIS_MAX = 87150
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 9
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 60
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# face floors: bark, leaf, deadwood, nut, cup, soil, grass, litter, canopy
FACE_FLOORS = (7110, 14090, 240, 1480, 1210, 2600, 2730, 1590, 41100)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Branch seat: every vertex of a branch's base cap inside its parent, the
# shallowest at least SEAT_MIN of the parent's local radius under its skin.
SEAT_MIN = 0.10
FLOAT_BRANCHES = 1.30   # --float-branches starts each tube this many parent radii out
# Taper: at every junction (r_after^2 + r_child^2) / r_before^2 in band,
# every child no wider than CHILD_MAX of its parent there; at the fork the
# scaffolds' summed area over the trunk's.
AREA_BAND = (0.94, 1.02)
FORK_BAND = (0.78, 0.90)
CHILD_MAX = 0.72
FAT_TWIGS = 1.80
# Nut in cup: the nut's deepest vertex inside its cup.
NUT_BITE = (0.005, 0.013)
POP_NUTS = 0.035
# Plumb and balance.
LEAN_MAX_DEG = 1.0
BALANCE_MAX = 0.30
DBH = 1.110
DBH_TOL = 0.020
LEAN_BEND = 0.040       # --lean-crown bends the bole x += k (z - z0)^2, z0 <= z <= zc
LEAN_Z0 = 0.55          # above the soil at the axis
LEAN_ZC = 1.95
# Sealed: in each sector round the trunk some trunk vertex SEAL_EPS under the
# soil; every root station's most-buried vertex ROOT_BED_MIN under it.
SEAL_SECTORS = 8
SEAL_EPS = 0.005
ROOT_STATION = 0.25
ROOT_BED_MIN = 0.020
ARCH_LIFT = 0.060
# Leaf clumps: every core's carrier this deep inside the core, and every
# leaf's petiole this deep inside its own core.
CORE_BITE_MIN = 0.040
LUMP_BITE_MIN = 0.010
LEAF_BITE_MIN = 0.010
ORPHAN_DROP = 0.55
SHED_Q = 0.85           # --shed-leaves slides in the leaves inside this crown_q
SCATTER_Q = 0.70        # --scatter-clusters pushes out the clusters of clumps inside this crown_q
SHED_IN = 0.90
SCATTER_OUT = 0.25      # --scatter-clusters pushes those clusters this far out along their bearing
# Hanging acorns: stalk in branch, pedicel in stalk and in cup.
STALK_BITE_MIN = 0.010
PEDICEL_BITE_MIN = 0.002
CUP_BITE_MIN = 0.006
DROP_ACORNS = 0.060
# Ground cover: most-buried vertex under the soil straight above it.
REST_BAND = (0.003, 0.030)
TUFT_BAND = (0.045, 0.080)
FLOAT_COVER = 0.060
# Hero yaw about Z only (level on the stage).
HERO_YAW_DEG = 0.0
WALL_Y = 10.5
CAM_DIST = 29.0
CAM_DZ = -1.2


BARK_IDX = 0
LEAF_IDX = 1
DEAD_IDX = 2
NUT_IDX = 3
CUP_IDX = 4
SOIL_IDX = 5
GRASS_IDX = 6
LITTER_IDX = 7
CANOPY_IDX = 8
MAT_LABELS = ("bark", "leaf", "deadwood", "nut", "cup", "soil", "grass", "litter", "canopy")

# part tags, one per face, so the audits can name a shell's role
P_TRUNK, P_ROOT, P_LIMB, P_TWIG, P_DEAD, P_LEAF = 1, 2, 3, 4, 5, 6
P_STALK, P_PEDICEL, P_CUP, P_NUT = 7, 8, 9, 10
P_SOIL, P_TUFT, P_LITTER, P_FCUP, P_FNUT, P_STICK = 11, 12, 13, 14, 15, 16
P_CORE = 17
P_LUMP = 18
WOOD_PARTS = (P_TRUNK, P_LIMB, P_TWIG, P_DEAD)
BRANCH_PARTS = (P_LIMB, P_TWIG, P_DEAD)
TREE_PARTS = (P_TRUNK, P_LIMB, P_TWIG, P_DEAD, P_LEAF, P_CORE, P_LUMP, P_STALK, P_PEDICEL, P_CUP,
              P_NUT)
COVER_PARTS = (P_TUFT, P_LITTER, P_FCUP, P_FNUT, P_STICK)


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
    """A closed-form draw in [0, 1) from three indices: per-part variety
    that no flag can shift."""
    x = math.sin(a * 12.9898 + b * 78.233 + c * 37.719 + SEED * 0.0137) * 43758.5453
    return x - math.floor(x)


def wrap(a):
    return (a + math.pi) % TAU - math.pi


def hor(v):
    return Vector((v.x, v.y, 0.0))


def perp(d):
    s = d.cross(UP)
    if s.length < 1e-4:
        s = d.cross(Vector((1.0, 0.0, 0.0)))
    return s.normalized()


# --------------------------------------------------------------------------
# The ground as a function of plan position
# --------------------------------------------------------------------------

def disc_wobble(th):
    return (1.0 + 0.05 * math.sin(3.0 * th + 0.7) + 0.03 * math.sin(5.0 * th + 2.1)
            + 0.02 * math.sin(8.0 * th + 0.3))


def soil_height(x, y):
    """A grassy mound, highest round the trunk where the roots have lifted
    it, rising a little toward the back, with low swells."""
    q = min(1.0, (x / SOIL_A[0]) ** 2 + (y / SOIL_A[1]) ** 2)
    h = (SOIL_RIM_H + (SOIL_H0 - SOIL_RIM_H) * (1.0 - q) ** 1.6 + SLOPE * y
         + FLARE_HEAP * math.exp(-(x * x + y * y) / FLARE_HEAP_R ** 2)
         + 0.030 * math.sin(1.1 * x + 0.3) * math.cos(1.4 * y + 0.9)
         + 0.012 * math.sin(2.7 * x - 2.1 * y + 1.2) + 0.005 * math.sin(6.3 * x + 4.9 * y))
    return max(SOIL_FLOOR, h)


class Ground:
    """The built soil, sampled by a ray straight down, so everything seated
    on it sits on the faces actually shipped (the rim roll-off included)."""

    def __init__(self, tree):
        self.tree = tree

    def hit(self, x, y):
        loc, nrm, _i, _d = self.tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
        if loc is None:
            return Vector((x, y, 0.0)), Vector((0.0, 0.0, 1.0))
        if nrm.z < 0.0:
            nrm = -nrm
        return loc, nrm

    def z(self, x, y):
        return self.hit(x, y)[0].z


# --------------------------------------------------------------------------
# Trunk shape
# --------------------------------------------------------------------------

def trunk_radius(zrel):
    t = min(max(zrel / FORK_Z, 0.0), 1.0)
    return TRUNK_RF + (TRUNK_R0 - TRUNK_RF) * (1.0 - t) ** 1.4


def axis_at(zrel, lean=0.0):
    """Trunk axis offset at height zrel above the soil: a closed-form sway,
    zero at the ground."""
    x = SWAY[0] * (math.sin(1.1 * zrel + 0.3) - math.sin(0.3))
    y = SWAY[1] * (math.sin(0.8 * zrel + 1.9) - math.sin(1.9))
    return Vector((x + bend(zrel, lean), y, 0.0))


def bend(zrel, lean):
    if not lean:
        return 0.0
    return lean * (min(max(zrel, LEAN_Z0), LEAN_ZC) - LEAN_Z0) ** 2


def buttress(a, yaws):
    return sum(math.exp(-(wrap(a - y) / FLARE_W) ** 2) for y in yaws)


def trunk_r(zrel, a, yaws, collider=False):
    r = trunk_radius(zrel)
    flare = math.exp(-max(zrel, 0.0) / FLARE_H)
    r += FLARE_R * flare * (0.18 + 0.82 * min(1.0, buttress(a, yaws)))
    if not collider:
        r *= 1.0 + FLUTE_AMP * math.cos(FLUTES * a + 0.35 * math.sin(1.3 * zrel + 0.4)) \
            * (0.4 + 0.6 * smoothstep(zrel, 0.0, 0.8))
        c2 = math.cos(34.0 * a - 1.3 * math.sin(2.7 * zrel + a))
        r *= 1.0 + RIDGE_AMP * (2.0 * bark_plate(zrel, a) - 1.0 + 0.25 * c2)
    return r


def bark_plate(zrel, a):
    """Rugged plates round the bole: 1 on a plate's broad flat top, 0 down
    a narrow deep furrow; the furrows wander and fork up the bole."""
    c = math.cos(RIDGES * a + 0.9 * math.sin(1.9 * zrel + 2.0 * a)
                 + 0.45 * math.sin(4.3 * zrel - 3.0 * a))
    return ((1.0 + c) * 0.5) ** 0.35


# --------------------------------------------------------------------------
# Crown envelope
# --------------------------------------------------------------------------

def crown_q(p):
    d = p - CROWN_C
    rz = CROWN_RZ[0] if d.z >= 0.0 else CROWN_RZ[1]
    return math.sqrt((d.x / CROWN_RX) ** 2 + (d.y / CROWN_RY) ** 2 + (d.z / rz) ** 2)


def env_dist(p, d):
    """Distance from ``p`` along unit ``d`` to the crown envelope."""
    if crown_q(p) >= 1.0:
        return 0.0
    lo, hi = 0.0, 20.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if crown_q(p + d * mid) < 1.0:
            lo = mid
        else:
            hi = mid
    return lo


def core_shape(cl):
    """A clump core's points and triangles: a lumpy cube-sphere ``r``
    across, flattened along its axis toward the light. A closed-form hash
    jitters each point, so the plan knows the built skin exactly."""
    dirs, quads = lump_mesh(cl["n"])
    a = cl["axis"]
    e1 = perp(a)
    e2 = a.cross(e1)
    r = cl["r"]
    pts = []
    for i, d in enumerate(dirs):
        j = 1.0 + CORE_JIT * (2.0 * hash01(cl["key"], i, 9) - 1.0)
        pts.append(cl["c"] + (e1 * (d.x * r) + e2 * (d.y * r) + a * (d.z * r * CORE_FLAT)) * j)
    tris = []
    for q in quads:
        if len(q) == 3:
            tris.append(tuple(q))
            continue
        # both diagonals of every quad: the built skin lies between them
        tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3]), (q[1], q[2], q[3]), (q[3], q[0], q[1])]
    return pts, tris


def core_skin(cl, d):
    """Distance from a lump's centre along unit ``d`` to its skin (the
    nearer of either split of each quad)."""
    best = 9.0
    pts = cl["pts"]
    for tri in cl["tris"]:
        hit = intersect_ray_tri(pts[tri[0]], pts[tri[1]], pts[tri[2]], d, cl["c"], True)
        if hit is not None and (hit - cl["c"]).dot(d) > 0.0:
            best = min(best, (hit - cl["c"]).length)
    return best


def leaf_frame(host, d, lk):
    """A leaf set in lump ``host`` toward unit ``d``: its petiole LEAF_DEPTH
    under the lump's built skin, the blade rising out of it and turned out
    of it, rolled a hashed way and a little to the light."""
    c = host["c"]
    base = c + d * (core_skin(host, d) - LEAF_DEPTH)
    swing = perp(d)
    swing = (swing * math.cos(TAU * hash01(lk, 1, 2))
             + d.cross(swing) * math.sin(TAU * hash01(lk, 1, 2)))
    away = d * d.dot(host["axis"]) - host["axis"]
    tan = (away.normalized() * 0.5 if away.length > 0.2 else Vector()) + swing
    tan = (tan - d * tan.dot(d)).normalized()
    e1 = (tan + d * LEAF_LIFT).normalized()
    e3 = d - e1 * d.dot(e1)
    e3.normalize()
    roll = math.radians(70.0) * (hash01(lk, 1, 3) - 0.5)
    e3 = e3 * math.cos(roll) + e1.cross(e3) * math.sin(roll)
    e3 = e3 + UP * 0.30
    e3 = (e3 - e1 * e3.dot(e1)).normalized()
    return {"base": base, "d": d, "e1": e1, "e3": e3,
            "L": LEAF_L[0] + (LEAF_L[1] - LEAF_L[0]) * hash01(lk, 3, 1), "key": lk}


# --------------------------------------------------------------------------
# The plan: every seeded draw happens here, before anything is built
# --------------------------------------------------------------------------

def frames(pts):
    """Parallel-transported (tangent, normal, binormal) along a polyline."""
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    ref = Vector((0.0, 0.0, 1.0)) if abs(tans[0].z) < 0.9 else Vector((1.0, 0.0, 0.0))
    nrm = (ref - tans[0] * ref.dot(tans[0])).normalized()
    out = []
    for t in tans:
        nrm = (nrm - t * nrm.dot(t)).normalized()
        out.append((t, nrm, t.cross(nrm)))
    return out


def branch_path(base, d, L, steps, crook, rise, droop, ph):
    """A crooked centreline: out along ``d``, lifting early (``rise``) and
    sagging late (``droop``), kinked side to side and up and down."""
    side = perp(d)
    up2 = side.cross(d).normalized()
    pts = [base.copy()]
    p = base.copy()
    step = L / (steps - 1)
    for i in range(1, steps):
        s = (i - 0.5) / (steps - 1)
        # the oak's zig-zag: each segment kinks the other way from the last
        alt = (1.0 if i % 2 else -1.0) * (0.55 + 0.45 * hash01(ph * 31.0, i, 5))
        alt2 = (1.0 if (i // 2) % 2 else -1.0) * (0.4 + 0.6 * hash01(ph * 31.0, i, 6))
        dirv = (d + side * (crook * (0.5 * math.sin(TAU * 1.2 * s + ph) + 0.7 * alt))
                + up2 * (crook * (0.4 * math.sin(TAU * 0.9 * s + 2.0 * ph) + 0.35 * alt2))
                + UP * (rise * (1.0 - s) - droop * s))
        p = p + dirv.normalized() * step
        pts.append(p)
    return pts


def plan_tree():
    rng = random.Random(SEED)

    def u(a, b):
        return a + (b - a) * rng.random()

    soil0 = soil_height(0.0, 0.0)
    root_yaws = []
    a0 = u(0.0, TAU)
    for k in range(ROOTS):
        root_yaws.append(a0 + TAU * k / ROOTS + u(-0.22, 0.22))
    roots = [{"yaw": y, "reach": u(*ROOT_REACH), "tone": rng.random(), "wig": u(-1.0, 1.0)}
             for y in root_yaws]

    branches = []

    def new_branch(gen, parent, seg, base, d, L, r0, crook, rise, droop):
        br = {"id": len(branches) + 1, "gen": gen, "parent": parent, "seg": seg,
              "tone": rng.random(), "ph": u(0.0, TAU), "dead": False, "kids": []}
        br["pts"] = branch_path(base, d, L, GEN_RINGS[gen], crook, rise, droop, br["ph"])
        br["r0"] = r0
        br["L"] = L
        branches.append(br)
        return br

    rf = trunk_radius(FORK_Z)
    ws = [u(0.7, 1.3) for _ in range(SCAFFOLDS)]
    # low, long limbs alternate with steep ones round the bole, so the
    # crown stands balanced over it
    elevs = [SCAFFOLD_ELEV[i] for i in (0, 3, 1, 4, 2)]
    yaw0 = math.radians(SCAFFOLD_YAW0)
    scaff = []
    for k in range(SCAFFOLDS):
        yaw = yaw0 + TAU * k / SCAFFOLDS + u(-0.22, 0.22)
        e = math.radians(elevs[k] + u(-4.0, 4.0))
        d = Vector((math.cos(e) * math.cos(yaw), math.cos(e) * math.sin(yaw), math.sin(e)))
        r0 = rf * math.sqrt(SCAFFOLD_AREA * ws[k] / sum(ws))
        zrel = FORK_Z - 0.30 + 0.20 * (elevs[k] - SCAFFOLD_ELEV[0]) / (SCAFFOLD_ELEV[-1] - SCAFFOLD_ELEV[0])
        base = Vector((0.0, 0.0, soil0 + zrel)) + axis_at(zrel)
        L = u(*SCAFFOLD_F) * env_dist(base, d)
        low = 1.0 - (elevs[k] - SCAFFOLD_ELEV[0]) / (SCAFFOLD_ELEV[-1] - SCAFFOLD_ELEV[0])
        br = new_branch(0, 0, -1, base, d, L, r0, GEN_CROOK[0], 0.16 + 0.22 * (1.0 - low),
                        0.10 + 0.42 * low)
        br["zrel"] = zrel
        scaff.append(br)

    def radii_of(br, kids):
        """Ring radii: natural taper as area, less each child's area past
        its junction; the last ring is the tip."""
        n = GEN_RINGS[br["gen"]]
        r0 = br["r0"]
        out = []
        for j in range(n):
            a2 = r0 * r0 * (1.0 - TAPER * j / (n - 1))
            for seg, rc in kids:
                if seg < j:
                    a2 -= rc * rc
            out.append(math.sqrt(max(a2, R_TIP * R_TIP)))
        out[-1] = R_TIP
        return out

    queue = list(scaff)
    while queue:
        br = queue.pop(0)
        g = br["gen"]
        n = GEN_RINGS[g]
        nk = GEN_KIDS[g]
        if nk == 0:
            br["radii"] = [br["r0"] * (1.0 - (1.0 - R_TIP / br["r0"] * 0.8) * j / (n - 1))
                           for j in range(n)]
            continue
        segs = sorted(rng.sample(range(GEN_SEG_LO[g], n - 2), nk))
        # da Vinci: the children share the parent's area, less what it keeps
        # for its own tip and its natural thinning
        ws = [u(0.7, 1.3) for _ in segs]
        share = GEN_SHARE[g] * (1.0 - KEEP - TAPER) * br["r0"] * br["r0"]
        phi0 = u(0.0, TAU)
        kids = [(seg, math.sqrt(share * w / sum(ws))) for seg, w in zip(segs, ws)]
        br["radii"] = radii_of(br, kids)
        fr = frames(br["pts"])
        for m, (seg, rc) in enumerate(kids):
            c0, c1 = br["pts"][seg], br["pts"][seg + 1]
            p = c0.lerp(c1, 0.5)
            t = (c1 - c0).normalized()
            _t, nn, bb = fr[seg]
            phi = phi0 + m * 2.40 + u(-0.3, 0.3)
            w = nn * math.cos(phi) + bb * math.sin(phi)
            al = math.radians(u(44.0, 68.0))
            d = t * math.cos(al) + w * math.sin(al)
            # out of the crown and up into it: the lower the branch the more
            # it spreads, the higher the more it climbs
            hf = min(1.0, max(0.0, (p.z - CROWN_C.z + CROWN_RZ[1]) / (CROWN_RZ[0] + CROWN_RZ[1])))
            out_h = hor(p)
            if out_h.length > 1e-4:
                d = d + out_h.normalized() * (0.30 - 0.18 * hf)
            d = (d + UP * (0.10 + 0.35 * hf)).normalized()
            if d.z < -0.30:
                d.z = -0.30
                d.normalize()
            cg = g + 1
            if cg == 3:
                L = u(*TWIG_L)
                rise, droop = 0.10, 0.10
            else:
                L = max(GEN_LMIN[cg], u(*GEN_F[cg]) * env_dist(p, d))
                rise, droop = 0.12, 0.18
            child = new_branch(cg, br["id"], seg, p, d, L, rc, GEN_CROOK[cg], rise, droop)
            br["kids"].append(child["id"])
            queue.append(child)

    by_id = {b["id"]: b for b in branches}
    twigs = [b for b in branches if b["gen"] == 3]
    # the lowest twigs are dead: shaded out under the crown
    for b in sorted(twigs, key=lambda b: b["pts"][-1].z)[:DEAD_TWIGS]:
        b["dead"] = True

    # clumps: a leaf-mass core on the end of every live branch, flattened
    # toward the light, with lobed leaves set in it and turned out of it
    clumps = []
    sats = []
    leaves = []
    carriers = []
    stations = []
    for b in branches:
        if b["dead"]:
            continue
        pts = b["pts"]
        stations.append((b, len(pts) - 1, 1.0))
        # the lumps of a cushion: more cores along the outer part of every
        # branch that carries twigs, so the tips' lumps run together
        for j, f in FILLERS.get(b["gen"], ()):
            stations.append((b, j, f))
    for b, j, rfac in stations:
        pts = b["pts"]
        tip = pts[j]
        t = (pts[j] - pts[j - 1]).normalized()
        out = tip - CROWN_C
        out = out.normalized() if out.length > 1e-4 else UP.copy()
        # exposure: 0 deep in the crown, 1 on its skin
        ex = min(1.0, max(0.0, (crown_q(tip) - 0.55) / 0.40))
        key = b["id"] * 17.0 + j * 0.37
        axis = (out * 0.6 + UP + perp(out) * (0.5 * hash01(key, 8, 2) - 0.25)).normalized()
        r = rfac * (CORE_R[0] + (CORE_R[1] - CORE_R[0]) * ex) * (0.80 + 0.40 * hash01(key, 8, 1))
        # a filler round a thick limb is widened to hold it
        r = max(r, b["radii"][j] / FILLER_RMAX)
        # a tip's core sits past the tip; a filler's is centred on its ring,
        # lifted a little above the branch
        c = tip + t * (CORE_SEAT * r) if j == len(pts) - 1 else tip.copy()
        cl = {"id": len(clumps), "carrier": b["id"], "c": c, "axis": axis, "r": r, "n": CORE_N,
              "key": key, "ex": ex, "tone": b["tone"], "sats": []}
        cl["pts"], cl["tris"] = core_shape(cl)
        clumps.append(cl)
        carriers.append(b["id"])
        # the cushion: small faceted leaf clusters set round the core, each
        # biting into it, most on the side out of the crown and up
        e1a = perp(axis)
        e2a = axis.cross(e1a)
        n = max(2, int(round((SAT_N[0] + (SAT_N[1] - SAT_N[0]) * ex) * rfac * rfac)))
        for i in range(n):
            sk = key + i + 1.0
            z = 1.0 - (1.0 - CLUMP_ZMIN) * (i + 0.5) / n
            phi = i * 2.39996 + b["ph"] + 0.5 * (hash01(sk, 1, 1) - 0.5)
            d = (axis * z + (e1a * math.cos(phi) + e2a * math.sin(phi))
                 * math.sqrt(max(0.0, 1.0 - z * z))).normalized()
            rs = (SAT_R[0] + (SAT_R[1] - SAT_R[0]) * hash01(sk, 2, 1)) * (0.85 + 0.3 * ex)
            # its centre SAT_BITE of its radius outside the core's built skin
            # (read by a ray from the core's centre), so it bites into it
            sc = c + d * (core_skin(cl, d) + SAT_OUT * rs)
            sax = (d + UP * 0.6).normalized()
            sat = {"id": len(sats), "clump": cl["id"], "c": sc, "axis": sax, "r": rs, "n": 0,
                   "key": sk * 3.1, "ex": ex, "tone": b["tone"], "d": d, "leaves": []}
            sat["pts"], sat["tris"] = core_shape(sat)
            sats.append(sat)
            cl["sats"].append(sat)
            nl = int(LEAF_P[0] + LEAF_P[1] * ex + LEAF_P[2] * hash01(sk, 2, 2))
            for m in range(nl):
                lk = sk * 7.0 + m
                # out of the cluster, away from the core
                dl = (d * 1.0 + perp(d) * (1.2 * hash01(lk, 1, 4) - 0.6)
                      + d.cross(perp(d)) * (1.2 * hash01(lk, 1, 5) - 0.6)).normalized()
                lf = leaf_frame(sat, dl, lk)
                lf.update({"sat": sat["id"], "carrier": b["id"], "tone": b["tone"], "ex": ex})
                sat["leaves"].append(lf)
                leaves.append(lf)

    # hanging acorns: under low, outer second-order branches, spread round
    # the crown
    cands = [b for b in branches if b["gen"] == 2]
    picked = []
    for k in range(ACORN_CLUSTERS):
        lo_a = -math.pi + TAU * k / ACORN_CLUSTERS
        hi_a = lo_a + TAU / ACORN_CLUSTERS
        pool = [b for b in cands
                if lo_a <= math.atan2(b["pts"][2].y, b["pts"][2].x) < hi_a
                and hor(b["pts"][2]).length > 1.6]
        if pool:
            picked.append(min(pool, key=lambda b: b["pts"][2].z))
    acorns = []
    for b in picked:
        seg = 2
        p = b["pts"][seg].lerp(b["pts"][seg + 1], 0.5)
        n_ac = 2 + (1 if rng.random() < 0.5 else 0)
        acorns.append({"branch": b["id"], "p": p, "L": u(*STALK_L), "n": n_ac,
                       "spin": u(0.0, TAU), "tone": [rng.random() for _ in range(3)],
                       "sway": u(-1.0, 1.0)})

    # ground cover, rejection-sampled on the disc away from the trunk and
    # the roots
    def root_clear(x, y, clear):
        for rt in roots:
            h = Vector((math.cos(rt["yaw"]), math.sin(rt["yaw"]), 0.0))
            q = Vector((x, y, 0.0))
            s = max(0.0, min(rt["reach"], q.dot(h)))
            if (q - h * s).length < clear:
                return False
        return True

    def scatter(count, rlo, rhi, spacing, clear, taken):
        out = []
        tries = 0
        while len(out) < count and tries < 20000:
            tries += 1
            a = u(0.0, TAU)
            r = math.sqrt(u((rlo / rhi) ** 2, 1.0)) * rhi
            x, y = r * math.cos(a), r * math.sin(a) * SOIL_A[1] / SOIL_A[0]
            if not root_clear(x, y, clear):
                continue
            if any(math.hypot(x - px, y - py) < spacing for px, py, _s in taken + out):
                continue
            out.append((x, y, spacing * 0.5))
        return out

    taken = []
    tufts = scatter(TUFTS, 1.30, 3.30, 0.46, 0.20, taken)
    taken += tufts
    litter = scatter(LITTER, 1.00, 3.20, 0.22, 0.14, [])
    fallen = scatter(FALLEN_ACORNS, 1.05, 2.90, 0.24, 0.16, taken)
    cover = {
        "tufts": [(x, y, u(0.24, 0.46), rng.random(), u(0.0, TAU)) for x, y, _s in tufts],
        "litter": [(x, y, u(0.0, TAU), u(0.20, 0.27), rng.random(), u(-0.12, 0.12)) for x, y, _s in litter],
        "fallen": [(x, y, u(0.0, TAU), rng.random(), u(-0.25, 0.25)) for x, y, _s in fallen],
        "sticks": [rng.random() for _s in STICKS + STICK_FORKS],
    }
    return {"soil0": soil0, "roots": roots, "root_yaws": root_yaws, "branches": branches,
            "by_id": by_id, "leaves": leaves, "clumps": clumps, "sats": sats, "carriers": carriers,
            "acorns": acorns, "cover": cover}


def orphan_clump(plan):
    """The clump on the live twig whose tip is nearest the crown's centre."""
    by_id = plan["by_id"]
    twig = [cl for cl in plan["clumps"] if by_id[cl["carrier"]]["gen"] == 3]
    return min(twig, key=lambda cl: (cl["c"] - CROWN_C).length)["id"]


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

class Builder:
    """The bmesh plus its layers: Tone (shading variety), Part (the shell's
    role), Ident and Parent (who is carried by whom), Cap (1 on a tube's
    base cap, 2 on its end cap), Ring (a tube vertex's ring) and Tip (0 at a
    leaf's petiole, 1 at its apex)."""

    def __init__(self, bm):
        self.bm = bm
        self.tone = bm.faces.layers.float.new("Tone")
        self.part = bm.faces.layers.int.new("Part")
        self.ident = bm.faces.layers.int.new("Ident")
        self.parent = bm.faces.layers.int.new("Parent")
        self.cap = bm.faces.layers.int.new("Cap")
        self.ring = bm.verts.layers.int.new("Ring")
        self.tip = bm.verts.layers.float.new("Tip")
        self.grain = bm.verts.layers.float_vector.new("Grain")
        self.furrow = bm.verts.layers.float.new("Furrow")
        self.bulge = bm.verts.layers.float_vector.new("Bulge")
        # the packed UVMap first, so it stays the active (baked, exported) map;
        # LeafUV runs across (x) and along (y) each leaf for its veins
        self.uv = bm.loops.layers.uv.new("UVMap")
        self.luv = bm.loops.layers.uv.new("LeafUV")
        self.leaf_uv = {}

    def vert(self, co, ring=-1, tip=0.0, grain=UP, furrow=0.35):
        v = self.bm.verts.new(co)
        v[self.ring] = ring
        v[self.tip] = tip
        v[self.grain] = grain
        v[self.furrow] = furrow
        return v

    def face(self, verts, mat, tone, part, ident=0, parent=-1, cap=0, smooth=None):
        f = self.bm.faces.new(verts)
        f.material_index = mat
        f[self.tone] = tone
        f[self.part] = part
        f[self.ident] = ident
        f[self.parent] = parent
        f[self.cap] = cap
        if smooth is not None:
            f.smooth = smooth
        return f


def add_tube(B, pts, radii, sides, mat, tone, part, ident=0, parent=-1, phase=0.0, jag=None,
             squash=1.0):
    """Capped round bar swept along a polyline with a radius per point.
    ``jag``: per-vertex (radial factor, axial offset) for the last ring."""
    pts = [Vector(p) for p in pts]
    rings = []
    for idx, (p, (t, n, b)) in enumerate(zip(pts, frames(pts))):
        ring = []
        for k in range(sides):
            a = phase + TAU * k / sides
            r = radii[idx]
            off = Vector((0.0, 0.0, 0.0))
            if jag is not None and idx == len(pts) - 1:
                r *= jag[k % len(jag)][0]
                off = t * jag[k % len(jag)][1]
            ring.append(B.vert(p + off + r * (n * (squash * math.cos(a)) + b * math.sin(a)),
                               ring=idx, grain=t))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            B.face((r0[k], r0[m], r1[m], r1[k]), mat, tone, part, ident, parent)
    B.face(tuple(reversed(rings[0])), mat, tone, part, ident, parent, cap=1)
    B.face(tuple(rings[-1]), mat, tone, part, ident, parent, cap=2)
    return [v for ring in rings for v in ring]


def lathe(B, origin, axis, prof, sides, spin, mat, tone, part, ident, parent, apex=None):
    """Closed body of revolution from ``origin`` along ``axis``: profile
    (r, h) rings, an n-gon base, and an n-gon top or an apex point."""
    axis = axis.normalized()
    ref = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = axis.cross(ref).normalized()
    e2 = axis.cross(e1)
    rings = []
    for k, (r, h) in enumerate(prof):
        ring = []
        for j in range(sides):
            a = spin + TAU * j / sides
            ring.append(B.vert(origin + axis * (h * ACORN_S) + (r * ACORN_S) * (e1 * math.cos(a) + e2 * math.sin(a))))
        rings.append(ring)
    verts = [v for r in rings for v in r]
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(sides):
            m = (j + 1) % sides
            B.face((r0[j], r0[m], r1[m], r1[j]), mat, tone, part, ident, parent)
    B.face(tuple(reversed(rings[0])), mat, tone, part, ident, parent, cap=1)
    if apex is None:
        B.face(tuple(rings[-1]), mat, tone, part, ident, parent, cap=2)
    else:
        top = B.vert(origin + axis * (apex * ACORN_S))
        verts.append(top)
        for j in range(sides):
            m = (j + 1) % sides
            B.face((rings[-1][j], rings[-1][m], top), mat, tone, part, ident, parent, cap=2)
    return verts


def zipper(A, M, xa, xm):
    """Triangles between a rim run ``A`` and a midrib run ``M`` that share
    their first and last vertex, advancing whichever is behind in x."""
    tris = [(A[0], A[1], M[1])]
    i, j = 1, 1
    na, nm = len(A) - 2, len(M) - 2
    while i < na or j < nm:
        if j >= nm or (i < na and xa[i + 1] <= xm[j + 1]):
            tris.append((A[i], A[i + 1], M[j]))
            i += 1
        else:
            tris.append((A[i], M[j + 1], M[j]))
            j += 1
    tris.append((A[na], A[na + 1], M[nm]))
    return tris


def add_leaf(B, base, e1, e3, L, tone, part, parent, key, mat, droop=0.10, fold=0.22,
             bottom=0.006, ident=0):
    """A lobed oak leaf: one closed, thin shell of 24 triangles. The rim
    (petiole, three lobes a side, the terminal lobe) is fanned to a
    top and a bottom centre over the same point of the blade, so every rim
    edge has one face above and one below and the two never cross. The
    blade folds up from its midrib and droops toward its apex."""
    e2 = e3.cross(e1)
    wob = [1.0 + LEAF_WOB * (2.0 * hash01(key, 7, k) - 1.0) for k in range(10)]

    def P(x, y, lift=0.0):
        return base + e1 * (x * L) + e2 * (y * L) + e3 * ((fold * abs(y) - droop * x * x + lift) * L)

    ymax = max(y for _x, y in LEAF_SIDE) * LEAF_WID
    vb = B.vert(base, tip=0.0)
    va = B.vert(P(1.0, 0.0), tip=1.0)
    B.leaf_uv[vb] = (0.5, 0.0)
    B.leaf_uv[va] = (0.5, 1.0)
    sides = []
    for sg, off in ((1.0, 0), (-1.0, 5)):
        run = []
        for k, (x, y) in enumerate(LEAF_SIDE):
            yy = sg * y * LEAF_WID * wob[k + off]
            v = B.vert(P(x, yy), tip=x)
            B.leaf_uv[v] = (0.5 + 0.5 * yy / ymax, x)
            run.append(v)
        sides.append(run)
    rim = [vb] + sides[0] + [va] + list(reversed(sides[1]))
    top = B.vert(P(LEAF_C, 0.0, 0.014), tip=LEAF_C)
    bot = B.vert(P(LEAF_C, 0.0, -bottom), tip=LEAF_C)
    B.leaf_uv[top] = (0.5, LEAF_C)
    B.leaf_uv[bot] = (0.5, LEAF_C)
    faces = []
    n = len(rim)
    for k in range(n):
        a, b = rim[k], rim[(k + 1) % n]
        faces.append(B.face((a, b, top), mat, tone, part, ident, parent, smooth=False))
        faces.append(B.face((b, a, bot), mat, tone, part, ident, parent, smooth=False))
    for f in faces:
        for loop in f.loops:
            loop[B.luv].uv = B.leaf_uv.get(loop.vert, (0.5, 0.5))
    return rim + [top, bot]


def add_core(B, cl, shift, tone, ident, parent, part, mass_c):
    """A leaf-mass lump: one closed, jittered cube-sphere ``r`` across and
    flattened along its axis toward the light, from its planned points."""
    _dirs, quads = lump_mesh(cl["n"])
    verts = []
    for p in cl["pts"]:
        v = B.vert(p + shift)
        a = p - mass_c
        b = p - CROWN_C
        v[B.bulge] = (a.normalized() * BULGE_MIX + b.normalized() * (1.0 - BULGE_MIX)).normalized()
        verts.append(v)
    for q in quads:
        B.face([verts[i] for i in q], CANOPY_IDX, tone, part, ident, parent)
    return verts


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


_ICO = []


def icosahedron():
    """Unit directions of an icosahedron's 12 points and its 20 triangles,
    wound outward."""
    if _ICO:
        return _ICO[0]
    g = (1.0 + math.sqrt(5.0)) / 2.0
    raw = [(-1, g, 0), (1, g, 0), (-1, -g, 0), (1, -g, 0), (0, -1, g), (0, 1, g), (0, -1, -g),
           (0, 1, -g), (g, 0, -1), (g, 0, 1), (-g, 0, -1), (-g, 0, 1)]
    dirs = [Vector(p).normalized() for p in raw]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4),
             (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8),
             (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    _ICO.append((dirs, faces))
    return _ICO[0]


def lump_mesh(n):
    """A lump's unit directions and faces: an icosahedron (``n`` = 0) or a
    cube-sphere ``n`` quads a side."""
    return icosahedron() if n == 0 else cube_sphere(n)


def add_tuft(B, G, x, y, h, tone, yaw, key, lift):
    """A grass tuft: one closed shell. A small squat core buried in the soil
    has every facet split in two, and each half drawn out into one tapered
    blade — up and splaying from the upper facets, a short spur into the
    soil from the lower ones."""
    c = Vector((x, y, G.z(x, y) - TUFT_BURY + lift))
    dirs, quads = cube_sphere(2)
    rot = Matrix.Rotation(yaw, 3, "Z")
    core = []
    for i, d in enumerate(dirs):
        s = 1.0 + 0.25 * (hash01(key, i, 1) - 0.5)
        core.append(B.vert(c + rot @ Vector((d.x * 0.034, d.y * 0.034, d.z * 0.024)) * s))
    verts = list(core)

    def blade(corners, k):
        ctr = sum((v.co for v in corners), Vector()) / 3.0
        o = (ctr - c).normalized()
        if o.z > -0.25:
            sc = Vector((hash01(key, k, 3) - 0.5, hash01(key, k, 4) - 0.5, 0.0)) * 1.1
            d = (o * 0.70 + UP * 1.0 + sc).normalized()
            ln = h * (0.45 + 0.55 * hash01(key, k, 6))
        else:
            d = o
            ln = 0.025
        apex = B.vert(ctr + d * ln, tip=1.0)
        verts.append(apex)
        for e in range(3):
            B.face((corners[e], corners[(e + 1) % 3], apex), GRASS_IDX, tone, P_TUFT, int(key), -1,
                   smooth=False)

    for k, q in enumerate(quads):
        o = k % 2
        qv = [core[i] for i in q]
        blade((qv[o], qv[o + 1], qv[(o + 2) % 4]), 2 * k)
        blade((qv[o], qv[(o + 2) % 4], qv[(o + 3) % 4]), 2 * k + 1)
    return verts


def settle(verts, G, sink):
    """Drop a lying body so its most-buried vertex is ``sink`` under the soil."""
    lift = min(v.co.z - G.z(v.co.x, v.co.y) for v in verts)
    for v in verts:
        v.co.z -= lift + sink


def add_soil(B):
    """A soil disc: a squircle-mapped grid whose rim rolls down to a flat
    base at Z = 0, each cell split on its short diagonal."""
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
            wob = disc_wobble(math.atan2(Y, X))
            x = SOIL_A[0] * X * wob
            y = SOIL_A[1] * Y * wob
            on_rim = i in (0, n) or k in (0, n)
            z = 0.0 if on_rim else soil_height(x, y) * smoothstep(1.0 - r, 0.0, SOIL_EDGE)
            col.append(B.vert((x, y, z)))
        grid.append(col)
    for i in range(n):
        for k in range(n):
            a, b, c, d = grid[i][k], grid[i + 1][k], grid[i + 1][k + 1], grid[i][k + 1]
            tris = ((a, b, c), (a, c, d)) if (a.co - c.co).length <= (b.co - d.co).length \
                else ((a, b, d), (b, c, d))
            for tri in tris:
                B.face(tri, SOIL_IDX, 0.5, P_SOIL)
    rim = ([grid[i][0] for i in range(n)] + [grid[n][k] for k in range(n)]
           + [grid[i][n] for i in range(n, 0, -1)] + [grid[0][k] for k in range(n, 0, -1)])
    B.face(list(reversed(rim)), SOIL_IDX, 0.5, P_SOIL)


def trunk_levels():
    """Level ring heights (above the soil at the axis): a fixed count, so a
    falsifier that moves the foot keeps the topology."""
    n_up = int(math.ceil((FORK_Z - UPPER_Z0) / UPPER_STEP))
    zs = [UPPER_Z0 + (FORK_Z - UPPER_Z0) * i / n_up for i in range(n_up + 1)]
    return zs


def add_trunk(B, plan, G, sides, lean, perch, collider=False):
    """One lathe from the bedded foot to a dome over the fork. The foot rings
    follow the soil under each vertex (``perch``: from the soil at the axis
    alone, which leaves the downhill side open)."""
    soil0 = G.z(0.0, 0.0)
    yaws = plan["root_yaws"]
    angles = [TAU * j / sides for j in range(sides)]
    grid = []
    for off in FOOT_OFFS:
        ring = []
        for a in angles:
            r = trunk_r(0.0, a, yaws, collider)
            x, y = r * math.cos(a), r * math.sin(a)
            z = (soil0 if perch else G.z(x, y)) + off
            ring.append(Vector((x, y, z)))
        grid.append(ring)
    for zrel in trunk_levels():
        c = axis_at(zrel, lean)
        ring = []
        for a in angles:
            r = trunk_r(zrel, a, yaws, collider)
            ring.append(Vector((c.x + r * math.cos(a), c.y + r * math.sin(a), soil0 + zrel)))
        grid.append(ring)
    for dz, f in DOME:
        zrel = FORK_Z + dz
        c = axis_at(zrel, lean)
        ring = []
        for a in angles:
            r = trunk_r(FORK_Z, a, yaws, collider) * f
            ring.append(Vector((c.x + r * math.cos(a), c.y + r * math.sin(a), soil0 + zrel)))
        grid.append(ring)
    zrels = [0.0] * len(FOOT_OFFS) + trunk_levels() + [FORK_Z] * len(DOME)
    verts = [[B.vert(p, ring=i, furrow=1.0 - bark_plate(zrels[i], a)) for p, a in zip(ring, angles)]
             for i, ring in enumerate(grid)]
    for r0, r1 in zip(verts, verts[1:]):
        for j in range(sides):
            m = (j + 1) % sides
            B.face((r0[j], r0[m], r1[m], r1[j]), BARK_IDX, 0.2, P_TRUNK, 0)
    B.face(tuple(reversed(verts[0])), BARK_IDX, 0.2, P_TRUNK, 0, cap=1)
    B.face(tuple(verts[-1]), BARK_IDX, 0.2, P_TRUNK, 0, cap=2)
    return [v for ring in verts for v in ring]


def add_roots(B, plan, G, arch):
    """Surface roots: from inside a buttress, out along the soil and down
    into it; ``arch`` lifts the middle of each clear of the ground."""
    for k, rt in enumerate(plan["roots"]):
        h = Vector((math.cos(rt["yaw"]), math.sin(rt["yaw"]), 0.0))
        s = Vector((-h.y, h.x, 0.0))
        reach = rt["reach"]
        pts, radii = [], []
        for i in range(ROOT_RINGS):
            t = i / (ROOT_RINGS - 1)
            q = h * (0.22 + (reach - 0.22) * t) + s * (0.10 * rt["wig"] * math.sin(math.pi * t))
            r = ROOT_R[0] + (ROOT_R[1] - ROOT_R[0]) * t ** 0.8
            dz = 0.22 * (1.0 - t) ** 3 + 0.36 * r - 0.06 * t * t
            if arch:
                dz += (r + ARCH_LIFT) * math.sin(math.pi * min(1.0, max(0.0, (t - 0.30) / 0.45))) ** 2
            pts.append(Vector((q.x, q.y, G.z(q.x, q.y) + dz)))
            radii.append(r)
        # a surface root is wider than it is deep
        add_tube(B, pts, radii, ROOT_SIDES, BARK_IDX, 0.3 + 0.4 * rt["tone"], P_ROOT, 900 + k,
                 squash=0.70)


def build_tree(B, plan, G, detail, flags, tree_verts):
    lean = LEAN_BEND if flags["lean_crown"] else 0.0
    by_id = plan["by_id"]
    orphan = orphan_clump(plan) if flags["orphan_clump"] else None
    for br in plan["branches"]:
        g = br["gen"]
        sides = (GEN_SIDES_HIGH if detail == "high" else GEN_SIDES)[g]
        pts = [p.copy() for p in br["pts"]]
        radii = list(br["radii"])
        if g == 3 and flags["fat_twigs"]:
            radii = [r * FAT_TWIGS for r in radii]
        if flags["float_branches"]:
            # the tube starts outside its parent; the path, and so the tip
            # and everything hung on it, is unchanged
            if br["parent"] == 0:
                r_p = trunk_radius(br["zrel"])
            else:
                par = by_id[br["parent"]]
                r_p = par["radii"][br["seg"]]
            d0 = (pts[1] - pts[0])
            k = min(0.85 * d0.length, FLOAT_BRANCHES * r_p + radii[0])
            pts[0] = pts[0] + d0.normalized() * k
        dead = br["dead"]
        jag = None
        if dead:
            jag = [(0.85, 0.010), (1.0, -0.006), (0.70, 0.016), (0.95, -0.008), (0.80, 0.012)]
        part = P_DEAD if dead else (P_TWIG if g == 3 else P_LIMB)
        tone = 0.35 + 0.5 * br["tone"]
        tree_verts += add_tube(B, pts, radii, sides, DEAD_IDX if dead else BARK_IDX, tone, part,
                               br["id"], br["parent"], phase=br["ph"], jag=jag)
    for cl in plan["clumps"]:
        shift = -UP * ORPHAN_DROP if cl["id"] == orphan else Vector()
        cid = 20000 + cl["id"]
        high = min(1.0, max(0.0, (cl["c"].z - CROWN_C.z + CROWN_RZ[1]) / (CROWN_RZ[0] + CROWN_RZ[1])))
        # outer and higher lumps and leaves are lighter; the crown's heart
        # is shaded
        tone = min(1.0, 0.10 + 0.45 * cl["ex"] + 0.25 * high + 0.15 * cl["tone"])
        tree_verts += add_core(B, cl, shift, tone, cid, cl["carrier"], P_CORE, cl["c"])
        shed = flags["shed_leaves"]
        for sat in cl["sats"]:
            sid_ = 40000 + sat["id"]
            stone = min(1.0, tone + 0.25 * (hash01(sat["key"], 4, 2) - 0.4) + 0.15 * sat["d"].z)
            # --scatter-clusters: an interior cushion's clusters (and their
            # leaves) pushed out of its core
            sshift = shift + (sat["d"] * SCATTER_OUT if flags["scatter_clusters"]
                              and crown_q(cl["c"]) < SCATTER_Q else Vector())
            tree_verts += add_core(B, sat, sshift, max(0.0, stone), sid_, cid, P_LUMP, cl["c"])
            for lf in sat["leaves"]:
                base = lf["base"] + sshift
                if shed and crown_q(base) < SHED_Q:
                    # --shed-leaves: an inner leaf slid in toward the crown's
                    # centre, clear through and out of its cluster
                    base = base + (CROWN_C - base).normalized() * SHED_IN
                ltone = min(1.0, 0.05 + 0.30 * hash01(lf["key"], 4, 1) + 0.35 * lf["ex"]
                            + 0.25 * high + 0.05 * lf["tone"])
                tree_verts += add_leaf(B, base, lf["e1"], lf["e3"], lf["L"], ltone, P_LEAF, sid_,
                                       lf["key"], LEAF_IDX,
                                       droop=0.06 + 0.10 * hash01(lf["key"], 5, 1),
                                       fold=0.12 + 0.16 * hash01(lf["key"], 5, 2))
    # hanging acorns: a stalk from inside the branch, two or three pedicels
    # from inside its end, a cup on each and a nut seated in each cup
    sid = 3000
    aid = 4000
    for ac in plan["acorns"]:
        br = by_id[ac["branch"]]
        p = ac["p"]
        out = hor(p).normalized()
        L = ac["L"]
        spts = [p, p - UP * (0.35 * L) + out * (0.04 * ac["sway"]),
                p - UP * (0.70 * L) + out * (0.07 * ac["sway"] + 0.02), p - UP * L + out * 0.05]
        tree_verts += add_tube(B, spts, [0.010, 0.0095, 0.009, 0.0088], 5, BARK_IDX, 0.6, P_STALK,
                               sid, br["id"])
        end = spts[-1]
        axis_s = (spts[-1] - spts[-2]).normalized()
        for m in range(ac["n"]):
            a = ac["spin"] + TAU * m / ac["n"]
            side = perp(axis_s) * math.cos(a) + perp(axis_s).cross(axis_s) * math.sin(a)
            hang = (side * 0.75 - UP * 0.65).normalized()
            cup0 = end + hang * (0.050 + 0.008 * m)
            ax = (hang * 0.35 - UP).normalized()
            ppts = [end - axis_s * 0.010, end + hang * 0.025, cup0 + ax * (0.010 * ACORN_S)]
            tree_verts += add_tube(B, ppts, [0.0042, 0.0040, 0.0038], 4, BARK_IDX, 0.6, P_PEDICEL,
                                   aid, sid)
            drop = -UP * DROP_ACORNS if flags["drop_acorns"] else Vector()
            nut0 = cup0 + ax * (NUT_SEAT * ACORN_S)
            if flags["pop_nuts"]:
                nut0 = nut0 + ax * POP_NUTS
            tone = ac["tone"][m]
            tree_verts += lathe(B, cup0 + drop, ax, CUP_PROF, ACORN_SIDES, a, CUP_IDX, tone, P_CUP,
                                aid, sid)
            tree_verts += lathe(B, nut0 + drop, ax, NUT_PROF, ACORN_SIDES, a + 0.3, NUT_IDX, tone,
                                P_NUT, aid, sid, apex=NUT_APEX)
            aid += 1
        sid += 1
    if lean:
        soil0 = plan["soil0"]
        # the bole bends; the crown above it is carried over rigidly, so the
        # envelope keeps its size and only the plumb budget can see it
        for v in tree_verts:
            v.co.x += bend(v.co.z - soil0, lean)


def build_cover(B, plan, G, flags):
    cov = plan["cover"]
    lift = FLOAT_COVER if flags["float_cover"] else 0.0
    for k, (x, y, h, tone, yaw) in enumerate(cov["tufts"]):
        add_tuft(B, G, x, y, h, tone, yaw, 5000 + k, lift)
    for k, (x, y, yaw, L, tone, tilt) in enumerate(cov["litter"]):
        c, nrm = G.hit(x, y)
        e1 = Vector((math.cos(yaw), math.sin(yaw), 0.0))
        e1 = (e1 - nrm * e1.dot(nrm)).normalized()
        # a leaf never lies dead flat: it rolls a few degrees about its midrib
        e3 = (nrm * math.cos(tilt) + nrm.cross(e1) * math.sin(tilt)).normalized()
        base = c - e1 * (0.45 * L) + e3 * 0.002
        vs = add_leaf(B, base, e1, e3, L, tone, P_LITTER, -1, 6000.0 + k, LITTER_IDX,
                      droop=-0.16, fold=0.30, bottom=0.012)
        # bed it: the most-buried vertex REST_SINK under the soil
        settle(vs, G, REST_SINK - lift)
    for k, (x, y, yaw, tone, tilt) in enumerate(cov["fallen"]):
        c, nrm = G.hit(x, y)
        ax = Vector((math.cos(yaw), math.sin(yaw), tilt)).normalized()
        cup0 = c + UP * 0.05 - ax * (0.045 * ACORN_S)
        vs = lathe(B, cup0, ax, CUP_PROF, ACORN_SIDES, yaw, CUP_IDX, tone, P_FCUP, 7000 + k, -1)
        vs += lathe(B, cup0 + ax * (NUT_SEAT * ACORN_S), ax, NUT_PROF, ACORN_SIDES, yaw + 0.3,
                    NUT_IDX, tone, P_FNUT, 7000 + k, -1, apex=NUT_APEX)
        settle(vs, G, REST_SINK - lift)
    def stick_path(a, b, r, tone):
        pts = []
        for i in range(6):
            t = i / 5.0
            p = a.lerp(b, t)
            side = Vector((-(b - a).y, (b - a).x, 0.0)).normalized()
            p += side * (0.03 * math.sin(2.8 * t * math.pi + tone * 6.0))
            pts.append(Vector((p.x, p.y, G.z(p.x, p.y) + r * 0.6)))
        return pts

    tones = cov["sticks"]
    paths = []
    for k, ((ax_, ay), (bx, by), r) in enumerate(STICKS):
        pts = stick_path(Vector((ax_, ay, 0.0)), Vector((bx, by, 0.0)), r, tones[k])
        paths.append(pts)
        vs = add_tube(B, pts, [r * (1.0 - 0.45 * i / 5.0) for i in range(6)], 5, DEAD_IDX,
                      0.4 + 0.4 * tones[k], P_STICK, 8000 + k)
        settle(vs, G, REST_SINK - lift)
    # a side twig forks off two of the sticks, from inside them
    for m, (si, st, (bx, by), r) in enumerate(STICK_FORKS):
        k = len(STICKS) + m
        src = paths[si]
        x = st * 5.0
        j = int(x)
        p0 = src[j].lerp(src[j + 1], x - j)
        pts = stick_path(Vector((p0.x, p0.y, 0.0)), Vector((bx, by, 0.0)), r, tones[k])
        vs = add_tube(B, pts, [r * (1.0 - 0.5 * i / 5.0) for i in range(6)], 5, DEAD_IDX,
                      0.4 + 0.4 * tones[k], P_STICK, 8000 + k)
        settle(vs, G, REST_SINK - lift)


def build_oak_mesh(name, plan, detail="low", **flags):
    bm = bmesh.new()
    try:
        B = Builder(bm)
        add_soil(B)
        # a temp tree for ray casts needs face normals first
        bm.normal_update()
        G = Ground(BVHTree.FromBMesh(bm))
        sides = TRUNK_SIDES_HIGH if detail == "high" else TRUNK_SIDES
        add_trunk(B, plan, G, sides, LEAN_BEND if flags["lean_crown"] else 0.0,
                               flags["perch_trunk"])
        add_roots(B, plan, G, flags["arch_roots"])
        build_tree(B, plan, G, detail, flags, [])
        build_cover(B, plan, G, flags)

        triangulate_ngons(bm)
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # Wood, soil, acorns and clump cores are smooth-shaded (their facets
        # carry in the silhouette); leaves and grass stay faceted, and every material
        # boundary is a hard edge.
        soft = {BARK_IDX, DEAD_IDX, SOIL_IDX, NUT_IDX, CUP_IDX, CANOPY_IDX}
        for face in bm.faces:
            if face.material_index in soft:
                face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            elif mats <= soft:
                edge.smooth = edge.calc_face_angle() < math.radians(62.0)
            else:
                edge.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        me.uv_layers.active = me.uv_layers["UVMap"]
        me.uv_layers["UVMap"].active_render = True
    finally:
        bm.free()
    mass_normals(me)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def mass_normals(me):
    """Leaf-mass lumps shade as part of their cushion, not as balls of
    their own: every canopy corner takes the vertex's Bulge (out of the
    cushion's centre and out of the crown) as a custom normal. Every other
    corner keeps the normal it has. Bulge is dropped once used."""
    n_loops = len(me.loops)
    normals = [0.0] * (3 * n_loops)
    me.corner_normals.foreach_get("vector", normals)
    bulge = [0.0] * (3 * len(me.vertices))
    me.attributes["Bulge"].data.foreach_get("vector", bulge)
    loop_vert = [0] * n_loops
    me.loops.foreach_get("vertex_index", loop_vert)
    for poly in me.polygons:
        if poly.material_index != CANOPY_IDX:
            continue
        for li in poly.loop_indices:
            vi = loop_vert[li]
            normals[3 * li:3 * li + 3] = bulge[3 * vi:3 * vi + 3]
    me.normals_split_custom_set([normals[3 * i:3 * i + 3] for i in range(n_loops)])
    me.attributes.remove(me.attributes["Bulge"])


def add_collider_trunk(B, G):
    """A frustum from under the soil to the fork and a point over the dome:
    the bole's girth without its flutes, buttresses or ridges."""
    soil0 = G.z(0.0, 0.0)
    rings = [(-0.10, TRUNK_R0 + 0.24), (FORK_Z, TRUNK_RF)]
    verts = []
    for zrel, r in rings:
        c = axis_at(max(zrel, 0.0))
        verts.append([B.vert(Vector((c.x + r * math.cos(TAU * j / COLLIDER_SIDES),
                                     c.y + r * math.sin(TAU * j / COLLIDER_SIDES), soil0 + zrel)))
                      for j in range(COLLIDER_SIDES)])
    B.vert(axis_at(FORK_Z) + Vector((0.0, 0.0, soil0 + FORK_Z + DOME[-1][0])))


def build_collider_source(name, plan):
    """The trunk alone, without flutes or ridges: players walk under the
    crown."""
    bm = bmesh.new()
    try:
        soil = bmesh.new()
        try:
            add_soil(Builder(soil))
            soil.normal_update()
            G = Ground(BVHTree.FromBMesh(soil))
            add_collider_trunk(Builder(bm), G)
        finally:
            soil.free()
        triangulate_ngons(bm)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


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


def voronoi_edge(nt, vec, scale):
    node = nt.nodes.new("ShaderNodeTexVoronoi")
    node.feature = "DISTANCE_TO_EDGE"
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


def normal_xyz(nt):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
    return sep.outputs


def coord_z(nt, coord):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    return sep.outputs["Z"]


def add_bump(nt, bsdf, height, strength, distance):
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def along(nt, coord, across, length):
    """Object coordinates scaled by ``across`` everywhere except along the
    Grain vector, which is scaled by ``length``: p*A + g (p.g) (L - A)."""
    g = nt.nodes.new("ShaderNodeAttribute")
    g.attribute_type = "GEOMETRY"
    g.attribute_name = "Grain"
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(coord, dot.inputs[0])
    nt.links.new(g.outputs["Vector"], dot.inputs[1])
    k = math_node(nt, "MULTIPLY", dot.outputs["Value"], length - across)
    sg = nt.nodes.new("ShaderNodeVectorMath")
    sg.operation = "SCALE"
    nt.links.new(g.outputs["Vector"], sg.inputs[0])
    nt.links.new(k, sg.inputs["Scale"])
    sp = nt.nodes.new("ShaderNodeVectorMath")
    sp.operation = "SCALE"
    nt.links.new(coord, sp.inputs[0])
    sp.inputs["Scale"].default_value = across
    add = nt.nodes.new("ShaderNodeVectorMath")
    add.operation = "ADD"
    nt.links.new(sp.outputs["Vector"], add.inputs[0])
    nt.links.new(sg.outputs["Vector"], add.inputs[1])
    return add.outputs["Vector"]


def bark_material():
    mat, nt, bsdf, coord = surface("OakBark")
    # Oak bark: grey-brown ridges cut into long blocks by deep vertical
    # fissures. Voronoi cells stretched up the stem give the blocks; their
    # edges are the fissures. Moss greens the foot on the shaded (north, +Y)
    # side and on upward faces.
    # the pattern runs along each tube: object coordinates squeezed along
    # the Grain point attribute (the tube's own tangent; up the trunk)
    ridge = noise(nt, along(nt, coord, 24.0, 1.4), 1.0, 4.0, 0.55)
    cells = voronoi_edge(nt, along(nt, coord, 13.0, 1.7), 1.0)
    grain = noise(nt, along(nt, coord, 30.0, 7.0), 1.0, 6.0, 0.6)
    fiss = math_node(nt, "MINIMUM", remap(nt, cells, 0.0, 0.035, 0.30, 1.0),
                     remap(nt, ridge, 0.40, 0.53, 0.0, 1.0))
    col = ramp(nt, grain, ((0.25, (0.050, 0.044, 0.037)), (0.55, (0.112, 0.098, 0.082)),
                           (0.85, (0.180, 0.160, 0.135))))
    col = mix_color(nt, (0.018, 0.014, 0.011), col, fiss)
    # the bole's own furrows (Furrow: 0 on a plate, 1 down a furrow) dark
    # and deep between the grey plates
    furrow = attr(nt, "Furrow")
    col = mix_color(nt, col, (0.012, 0.010, 0.008), remap(nt, furrow, 0.30, 0.85, 0.0, 0.92))
    tone = attr(nt, "Tone")
    col = mix_color(nt, col, (0.070, 0.055, 0.040), remap(nt, tone, 0.0, 1.0, 0.0, 0.35))
    nx = normal_xyz(nt)
    patch = noise(nt, coord, 3.5, 4.0, 0.6)
    low = remap(nt, coord_z(nt, coord), 0.55, 1.45, 1.0, 0.0)
    face = remap(nt, nx["Y"], 0.05, 0.75, 0.0, 1.0)
    moss_m = math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", low, face),
                       remap(nt, patch, 0.38, 0.58, 0.0, 1.0))
    moss = ramp(nt, grain, ((0.3, (0.030, 0.055, 0.012)), (0.8, (0.075, 0.115, 0.022))))
    col = mix_color(nt, col, moss, math_node(nt, "MINIMUM", moss_m, 0.9))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    add_bump(nt, bsdf, math_node(nt, "SUBTRACT", math_node(nt, "ADD", fiss,
             math_node(nt, "MULTIPLY", grain, 0.3)), furrow), 0.9, 0.03)
    return mat


def leaf_material():
    mat, nt, bsdf, coord = surface("OakLeaf")
    # Deep oak green: each leaf takes its own tone (lighter outside and
    # high, shaded in the crown's heart); a pale midrib and lateral veins
    # run from LeafUV; the upper faces carry a faint sheen.
    tone = attr(nt, "Tone")
    base = ramp(nt, tone, ((0.0, (0.016, 0.038, 0.010)), (0.45, (0.040, 0.085, 0.018)),
                           (1.0, (0.095, 0.160, 0.032))))
    speck = noise(nt, coord, 40.0, 3.0, 0.6)
    col = mix_color(nt, base, (0.030, 0.055, 0.012), remap(nt, speck, 0.3, 0.7, 0.0, 0.35))
    luv = nt.nodes.new("ShaderNodeUVMap")
    luv.uv_map = "LeafUV"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(luv.outputs["UV"], sep.inputs["Vector"])
    across = math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", sep.outputs["X"], 0.5), 0.0)
    mid = remap(nt, across, 0.0, 0.035, 1.0, 0.0)
    lat = math_node(nt, "SINE", math_node(nt, "MULTIPLY",
                    math_node(nt, "SUBTRACT", sep.outputs["Y"], math_node(nt, "MULTIPLY", across, 1.1)),
                    TAU * 4.5), 0.0)
    vein = math_node(nt, "MAXIMUM", mid, remap(nt, lat, 0.82, 1.0, 0.0, 0.55))
    col = mix_color(nt, col, (0.120, 0.170, 0.050), math_node(nt, "MULTIPLY", vein, 0.55))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.62
    bsdf.inputs["Specular IOR Level"].default_value = 0.20
    add_bump(nt, bsdf, vein, 0.25, 0.01)
    return mat


def deadwood_material():
    mat, nt, bsdf, coord = surface("OakDeadwood")
    # Weathered, barkless: silver-grey with dark checks along the grain.
    streak = noise(nt, along(nt, coord, 30.0, 4.0), 2.0, 6.0, 0.6)
    col = ramp(nt, streak, ((0.35, (0.065, 0.058, 0.052)), (0.55, (0.170, 0.160, 0.142)),
                            (0.80, (0.260, 0.245, 0.220))))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    return mat


def nut_material():
    mat, nt, bsdf, coord = surface("AcornNut")
    # A glossy nut, green-brown to chestnut, with faint streaks down it.
    tone = attr(nt, "Tone")
    base = ramp(nt, tone, ((0.0, (0.120, 0.090, 0.030)), (0.5, (0.200, 0.120, 0.040)),
                           (1.0, (0.240, 0.140, 0.050))))
    streak = noise(nt, mapping(nt, coord, scale=(90.0, 90.0, 12.0)), 1.0, 3.0, 0.5)
    col = mix_color(nt, base, (0.090, 0.055, 0.020), remap(nt, streak, 0.45, 0.7, 0.0, 0.5))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.32
    return mat


def cup_material():
    mat, nt, bsdf, coord = surface("AcornCup")
    # A scaly grey-brown cupule: small overlapping scales from Voronoi cells.
    cells = voronoi_edge(nt, coord, 160.0)
    col = ramp(nt, remap(nt, cells, 0.0, 0.25, 0.0, 1.0),
               ((0.0, (0.035, 0.028, 0.020)), (0.6, (0.120, 0.100, 0.070)), (1.0, (0.170, 0.145, 0.105))))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    add_bump(nt, bsdf, cells, 0.8, 0.01)
    return mat


def soil_material():
    mat, nt, bsdf, coord = surface("OakTurf")
    # Dark soil under a short sward: green on the upward faces broken by
    # bare earth, and a fringe of fine grass streaks.
    dirt = noise(nt, coord, 6.0, 6.0, 0.6)
    earth = ramp(nt, dirt, ((0.30, (0.020, 0.014, 0.010)), (0.70, (0.050, 0.036, 0.024))))
    sward = noise(nt, coord, 2.2, 5.0, 0.62)
    fine = noise(nt, mapping(nt, coord, scale=(140.0, 140.0, 20.0)), 1.0, 2.0, 0.5)
    grass = ramp(nt, fine, ((0.30, (0.022, 0.042, 0.010)), (0.70, (0.060, 0.098, 0.022))))
    nx = normal_xyz(nt)
    mask = math_node(nt, "MULTIPLY", remap(nt, sward, 0.36, 0.52, 0.0, 1.0),
                     remap(nt, nx["Z"], 0.5, 0.9, 0.0, 1.0))
    col = mix_color(nt, earth, grass, mask)
    # last year's leaves drift thick under the crown near the bole: leaf-
    # sized cells, each its own brown, thinning out into the grass
    lit = nt.nodes.new("ShaderNodeTexVoronoi")
    lit.inputs["Scale"].default_value = 9.0
    nt.links.new(noise_warp(nt, coord), lit.inputs["Vector"])
    lcell = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(lit.outputs["Color"], lcell.inputs["Color"])
    brown = ramp(nt, lcell.outputs[0], ((0.0, (0.045, 0.026, 0.012)), (0.5, (0.110, 0.066, 0.028)),
                                        (0.8, (0.095, 0.078, 0.034)), (1.0, (0.150, 0.098, 0.044))))
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    rad = math_node(nt, "SQRT", math_node(nt, "ADD", math_node(nt, "MULTIPLY", sep.outputs["X"],
                                                                sep.outputs["X"]),
                                          math_node(nt, "MULTIPLY", sep.outputs["Y"], sep.outputs["Y"])),
                    0.0)
    drift = math_node(nt, "MULTIPLY", remap(nt, rad, 1.0, 3.2, 1.0, 0.0),
                      remap(nt, noise(nt, coord, 1.6, 3.0, 0.6), 0.30, 0.60, 0.35, 1.0))
    drift = math_node(nt, "MULTIPLY", drift, remap(nt, lcell.outputs[1], 0.15, 0.35, 0.0, 1.0))
    col = mix_color(nt, col, brown, drift)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.93
    add_bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "ADD", dirt,
             math_node(nt, "MULTIPLY", fine, 0.5)), math_node(nt, "MULTIPLY", drift, 0.4)), 0.4, 0.02)
    return mat


def grass_material():
    mat, nt, bsdf, coord = surface("OakGrass")
    tone = attr(nt, "Tone")
    base = ramp(nt, tone, ((0.0, (0.030, 0.060, 0.012)), (1.0, (0.070, 0.115, 0.025))))
    tip = attr(nt, "Tip")
    col = mix_color(nt, (0.012, 0.022, 0.006), base, remap(nt, tip, 0.0, 0.5, 0.2, 1.0))
    col = mix_color(nt, col, (0.130, 0.140, 0.055), remap(nt, tip, 0.6, 1.0, 0.0, 0.5))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.7
    return mat


def litter_material():
    mat, nt, bsdf, coord = surface("OakLitter")
    # Last year's leaves: dull brown to olive, darker where they are rotting.
    tone = attr(nt, "Tone")
    base = ramp(nt, tone, ((0.0, (0.040, 0.026, 0.014)), (0.5, (0.078, 0.048, 0.022)),
                           (0.8, (0.070, 0.060, 0.028)), (1.0, (0.100, 0.065, 0.030))))
    blot = noise(nt, coord, 25.0, 3.0, 0.6)
    col = mix_color(nt, base, (0.030, 0.022, 0.014), remap(nt, blot, 0.55, 0.75, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    return mat


def canopy_material():
    mat, nt, bsdf, coord = surface("OakCanopy")
    # The leaf mass inside a clump: small leaf-sized cells, each its own
    # green, with dark gaps between them; darker in the crown's heart and
    # on the clump's underside, lighter where it faces the sky.
    tone = attr(nt, "Tone")
    # leaf-sized cells, each its own green and each turned its own way (a
    # hashed tilt of the shading normal per cell), with dark gaps between
    wv = noise_warp(nt, coord)
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 18.0
    vor.inputs["Randomness"].default_value = 1.0
    nt.links.new(wv, vor.inputs["Vector"])
    cell = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(vor.outputs["Color"], cell.inputs["Color"])
    gap = remap(nt, voronoi_edge(nt, wv, 18.0), 0.0, 0.07, 1.0, 0.0)
    patch = noise(nt, coord, 3.0, 3.0, 0.6)
    fac = math_node(nt, "ADD", math_node(nt, "MULTIPLY", tone, 0.60),
                    math_node(nt, "ADD", math_node(nt, "MULTIPLY", cell.outputs[0], 0.28),
                              remap(nt, patch, 0.35, 0.65, -0.10, 0.12)))
    col = ramp(nt, fac, ((0.0, (0.006, 0.015, 0.004)), (0.40, (0.018, 0.042, 0.009)),
                         (0.75, (0.040, 0.080, 0.016)), (1.0, (0.075, 0.125, 0.026))))
    col = mix_color(nt, col, (0.003, 0.007, 0.002), math_node(nt, "MULTIPLY", gap, 0.8))
    # the lit top of a lump against its dark underside, and dark crevices
    # where lumps crowd each other
    nx = normal_xyz(nt)
    sky = remap(nt, nx["Z"], -0.6, 0.8, 0.25, 1.0)
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.6
    shade = math_node(nt, "MULTIPLY", sky, remap(nt, ao.outputs["AO"], 0.2, 1.0, 0.25, 1.0))
    col = mix_color(nt, (0.002, 0.005, 0.002), col, shade)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    bsdf.inputs["Specular IOR Level"].default_value = 0.10
    tilt = nt.nodes.new("ShaderNodeVectorMath")
    tilt.operation = "MULTIPLY_ADD"
    nt.links.new(vor.outputs["Color"], tilt.inputs[0])
    tilt.inputs[1].default_value = (1.2, 1.2, 1.2)
    tilt.inputs[2].default_value = (-0.6, -0.6, -0.6)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nsum = nt.nodes.new("ShaderNodeVectorMath")
    nsum.operation = "ADD"
    nt.links.new(tilt.outputs["Vector"], nsum.inputs[0])
    nt.links.new(geo.outputs["Normal"], nsum.inputs[1])
    nrm = nt.nodes.new("ShaderNodeVectorMath")
    nrm.operation = "NORMALIZE"
    nt.links.new(nsum.outputs["Vector"], nrm.inputs[0])
    nt.links.new(nrm.outputs["Vector"], bsdf.inputs["Normal"])
    return mat


def noise_warp(nt, coord):
    """Object coordinates nudged by a low noise, so leaf cells are not
    laid out on a lattice."""
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = 2.0
    node.inputs["Detail"].default_value = 2.0
    nt.links.new(coord, node.inputs["Vector"])
    add = nt.nodes.new("ShaderNodeVectorMath")
    add.operation = "MULTIPLY_ADD"
    nt.links.new(node.outputs["Color"], add.inputs[0])
    add.inputs[1].default_value = (0.15, 0.15, 0.15)
    nt.links.new(coord, add.inputs[2])
    return add.outputs["Vector"]


def oak_materials():
    """(bark, leaf, deadwood, nut, cup, soil, grass, litter, canopy): shared
    by the check and the render."""
    return (bark_material(), leaf_material(), deadwood_material(), nut_material(),
            cup_material(), soil_material(), grass_material(), litter_material(),
            canopy_material())


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


def face_ints(me, name):
    vals = [0] * len(me.polygons)
    me.attributes[name].data.foreach_get("value", vals)
    return vals


def vert_vals(me, name, kind=int):
    vals = [kind(0)] * len(me.vertices)
    me.attributes[name].data.foreach_get("value", vals)
    return vals


class Shell:
    def __init__(self, me, verts, polys, part_of, ident_of, parent_of):
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
        self.parent = parent_of[polys[0].index] if polys else -1
        remap_ = {vi: n for n, vi in enumerate(verts)}
        self.tree = BVHTree.FromPolygons(
            [tuple(p) for p in pts], [[remap_[v] for v in p.vertices] for p in polys])
        self.polys = polys

    def holds(self, q, pad=0.0):
        return (self.lo.x - pad <= q.x <= self.hi.x + pad and self.lo.y - pad <= q.y <= self.hi.y + pad
                and self.lo.z - pad <= q.z <= self.hi.z + pad)


class TrunkAxis:
    """Trunk ring centroids read off the mesh: every level lathe ring shares
    one z (the foot rings follow the soil and are left out)."""

    def __init__(self, trunk):
        rings = {}
        for p in trunk.pts:
            rings.setdefault(round(p.z, 5), []).append(p)
        full = max(len(v) for v in rings.values())
        self.rings = []
        for z in sorted(rings):
            ps = rings[z]
            if len(ps) != full:
                continue
            c = sum(ps, Vector()) / len(ps)
            r = sum(((q - c).to_2d().length for q in ps)) / len(ps)
            self.rings.append((z, c, r))

    def radius(self, z):
        rs = self.rings
        if z <= rs[0][0]:
            return rs[0][2]
        for (z0, _c0, r0), (z1, _c1, r1) in zip(rs, rs[1:]):
            if z <= z1:
                return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
        return rs[-1][2]

    def centre(self, z):
        rs = self.rings
        if z <= rs[0][0]:
            return rs[0][1].copy()
        for (z0, c0, _r0), (z1, c1, _r1) in zip(rs, rs[1:]):
            if z <= z1:
                return c0.lerp(c1, (z - z0) / (z1 - z0))
        return rs[-1][1].copy()


def classify(me):
    groups = shells(me)
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(p)
    part_of = face_ints(me, "Part")
    ident_of = face_ints(me, "Ident")
    parent_of = face_ints(me, "Parent")
    cap_of = face_ints(me, "Cap")
    parts = [Shell(me, g, polys[i], part_of, ident_of, parent_of) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups, "cap_of": cap_of}

    def of(*kinds):
        return [s for s in parts if s.part in kinds]

    for key, kinds in (("trunk", (P_TRUNK,)), ("roots", (P_ROOT,)), ("branches", BRANCH_PARTS),
                       ("leaves", (P_LEAF,)), ("cores", (P_CORE,)), ("lumps", (P_LUMP,)), ("stalks", (P_STALK,)), ("pedicels", (P_PEDICEL,)),
                       ("cups", (P_CUP,)), ("nuts", (P_NUT,)), ("soil", (P_SOIL,)),
                       ("cover", COVER_PARTS)):
        out[key] = of(*kinds)
    out["wood"] = {s.ident: s for s in out["trunk"] + out["branches"]}
    if len(out["trunk"]) == 1:
        out["axis"] = TrunkAxis(out["trunk"][0])
    return out


def cap_verts(me, s, cap_of, which=1):
    ids = set()
    for p in s.polys:
        if cap_of[p.index] == which:
            ids.update(p.vertices)
    return [me.vertices[i].co.copy() for i in ids]


class Rings:
    """A tube's ring centroids and radii, read off the mesh by its Ring tag."""

    def __init__(self, me, s, ring_of):
        by = {}
        for vi in s.verts:
            by.setdefault(ring_of[vi], []).append(me.vertices[vi].co)
        self.c, self.r = [], []
        for k in sorted(by):
            ps = by[k]
            c = sum(ps, Vector()) / len(ps)
            self.c.append(c)
            self.r.append(sum((q - c).length for q in ps) / len(ps))

    def junction(self, p0, p1):
        """Index of the ring pair whose segment passes nearest the line
        through ``p0`` and ``p1`` (a child's first two ring centres): where
        the child's axis meets this one."""
        best, bi = 9e9, 0
        for i in range(len(self.c) - 1):
            a, b = self.c[i], self.c[i + 1]
            hit = intersect_line_line(a, b, p0, p1)
            if hit is None:
                continue
            ab = b - a
            t = min(max((hit[0] - a).dot(ab) / max(ab.length_squared, 1e-12), 0.0), 1.0)
            q = a + ab * t
            d1 = p1 - p0
            s = (q - p0).dot(d1) / max(d1.length_squared, 1e-12)
            d = (p0 + d1 * s - q).length
            if d < best:
                best, bi = d, i
        return bi


PARITY_DIRS = (Vector((0.31, 0.47, 0.83)).normalized(), Vector((-0.62, 0.21, -0.75)).normalized(),
               Vector((0.55, -0.79, 0.27)).normalized())


def inside(tree, p):
    """Ray parity, by majority over three directions: an odd number of
    crossings out of a closed shell."""
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


def deepest(host, pts):
    """The deepest of ``pts`` inside the closed shell ``host`` (negative:
    the nearest one's distance outside)."""
    return max(signed_depth(host.tree, q) for q in pts)


def branch_audits(me, cls):
    """Seat: per branch, the shallowest base-cap vertex inside its parent
    over the parent's local radius. Taper: per junction the area ratio and
    the child's radius over the parent's; at the fork the scaffolds' summed
    area over the trunk's."""
    ring_of = vert_vals(me, "Ring")
    cap_of = cls["cap_of"]
    wood = cls["wood"]
    ax = cls["axis"]
    rings = {s.ident: Rings(me, s, ring_of) for s in cls["branches"]}
    seats, missing = [], 0
    junctions = {}
    scaffold_a = 0.0
    scaffold_zmin = 9.0
    widths = []
    for s in cls["branches"]:
        par = wood.get(s.parent)
        cap = cap_verts(me, s, cap_of, 1)
        if par is None or not cap:
            missing += 1
            continue
        bc = sum(cap, Vector()) / len(cap)
        rc = sum((q - bc).length for q in cap) / len(cap)
        if par.part == P_TRUNK:
            r_local = ax.radius(bc.z)
            scaffold_a += rc * rc
            scaffold_zmin = min(scaffold_zmin, bc.z)
        else:
            pr = rings[par.ident]
            own = rings[s.ident]
            i = pr.junction(own.c[0], own.c[1])
            r_local = min(pr.r[i], pr.r[i + 1])
            junctions.setdefault((par.ident, i), []).append(rc)
            widths.append(rc / pr.r[i])
        seats.append(min(signed_depth(par.tree, q) for q in cap) / r_local)
    areas = []
    for (pid, i), rcs in junctions.items():
        pr = rings[pid]
        areas.append((pr.r[i + 1] ** 2 + sum(r * r for r in rcs)) / pr.r[i] ** 2)
    below = [r for z, _c, r in ax.rings if z < scaffold_zmin]
    fork = scaffold_a / (below[-1] ** 2) if below else 0.0
    return seats, missing, areas, widths, fork


def plumb_audit(me, cls, soil0):
    """Trunk lean (line fit to ring centroids), foliage balance (leaves and
    leaf clusters, by area) over the
    base, and breast-height diameter above the soil."""
    ax = cls["axis"]
    rings = [(z, c) for z, c, _r in ax.rings if soil0 + 0.35 <= z <= soil0 + FORK_Z - 0.1]
    n = len(rings)
    mz = sum(z for z, _c in rings) / n
    mx = sum(c.x for _z, c in rings) / n
    my = sum(c.y for _z, c in rings) / n
    szz = sum((z - mz) ** 2 for z, _c in rings)
    sx = sum((z - mz) * (c.x - mx) for z, c in rings) / szz
    sy = sum((z - mz) * (c.y - my) for z, c in rings) / szz
    lean = math.degrees(math.atan(math.hypot(sx, sy)))
    base = ax.centre(soil0 + 0.4)
    area = 0.0
    acc = Vector((0.0, 0.0, 0.0))
    for p in me.polygons:
        if p.material_index in (LEAF_IDX, CANOPY_IDX):
            a = p.area
            area += a
            acc += p.center * a
    centroid = acc / area if area else Vector()
    balance = (centroid - base).to_2d().length
    zsoil = ray_down(cls["soil"][0].tree, base.x, base.y) or 0.0
    dbh_ring = min(ax.rings, key=lambda r: abs(r[0] - (zsoil + 1.3)))
    return lean, balance, 2.0 * dbh_ring[2], centroid.z


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 12.0)), Vector((0.0, 0.0, -1.0)), 30.0)
    return None if loc is None else loc.z


def seal_audit(cls):
    """Sectors round the trunk's foot holding a trunk vertex at least
    SEAL_EPS under the soil straight above it; per root, its shallowest
    station outside the trunk."""
    soil = cls["soil"][0]
    trunk = cls["trunk"][0]
    low = [p for p in trunk.pts if p.z < min(q.z for q in trunk.pts) + 0.6]
    cx = sum(p.x for p in low) / len(low)
    cy = sum(p.y for p in low) / len(low)
    sealed = set()
    for p in low:
        g = ray_down(soil.tree, p.x, p.y)
        if g is not None and g - p.z >= SEAL_EPS:
            a = math.atan2(p.y - cy, p.x - cx) + math.pi
            sealed.add(int(a / TAU * SEAL_SECTORS) % SEAL_SECTORS)
    worst = []
    for rt in cls["roots"]:
        bins = {}
        joint = set()
        for p in rt.pts:
            k = int(round(math.hypot(p.x - cx, p.y - cy) / ROOT_STATION))
            if trunk.holds(p) and inside(trunk.tree, p):
                joint.add(k)
                continue
            g = ray_down(soil.tree, p.x, p.y)
            if g is not None:
                bins[k] = max(bins.get(k, -9.0), g - p.z)
        free = [b for k, b in bins.items() if k not in joint]
        worst.append(min(free) if free else -9.0)
    return len(sealed), worst


def leaf_audit(me, cls):
    """Per clump core: its carrier's (the branch tagged as its Parent)
    deepest vertex inside it. Per leaf: its petiole's depth inside its own
    core (tagged as its Parent)."""
    tip = vert_vals(me, "Tip", float)
    wood = cls["wood"]
    cores = {s.ident: s for s in cls["cores"]}
    seats = []
    carriers = set()
    for s in cls["cores"]:
        host = wood.get(s.parent)
        if host is None:
            seats.append(-9.0)
            continue
        carriers.add(s.parent)
        seats.append(deepest(s, [q for q in host.pts if s.holds(q)] or host.pts[:1]))
    lumps = {s.ident: s for s in cls["lumps"]}
    bites_l = []
    for s in cls["lumps"]:
        host = cores.get(s.parent)
        # the cluster's centroid (the mean of its points) under its core's skin
        cen = sum(s.pts, Vector()) / len(s.pts)
        bites_l.append(-9.0 if host is None else signed_depth(host.tree, cen))
    bites = []
    for s in cls["leaves"]:
        host = lumps.get(s.parent)
        if host is None:
            bites.append(-9.0)
            continue
        vi = min(s.verts, key=lambda i: tip[i])
        bites.append(signed_depth(host.tree, me.vertices[vi].co))
    return seats, bites_l, bites, carriers


def acorn_audit(cls):
    """Nut in cup; stalk in branch; pedicel in stalk and in cup."""
    wood = cls["wood"]
    stalks = {s.ident: s for s in cls["stalks"]}
    cups = {s.ident: s for s in cls["cups"]}
    nuts = [deepest(cups[s.ident], s.pts) if s.ident in cups else -9.0 for s in cls["nuts"]]
    stalk_bites = [deepest(wood[s.parent], s.pts) if s.parent in wood else -9.0
                   for s in cls["stalks"]]
    ped_stalk, ped_cup = [], []
    for s in cls["pedicels"]:
        ped_stalk.append(deepest(stalks[s.parent], s.pts) if s.parent in stalks else -9.0)
        ped_cup.append(deepest(cups[s.ident], s.pts) if s.ident in cups else -9.0)
    return nuts, stalk_bites, ped_stalk, ped_cup


def fallen_nut_audit(cls):
    cups = {s.ident: s for s in cls["cover"] if s.part == P_FCUP}
    return [deepest(cups[s.ident], s.pts) if s.ident in cups else -9.0
            for s in cls["cover"] if s.part == P_FNUT]


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
    """Per cover shell (or fallen acorn, cup and nut together) its most
    buried vertex under the soil; and the cover joined to the soil."""
    soil = cls["soil"][0]
    rests = {}
    fallen = {}
    for s in cls["cover"]:
        deep = -9.0
        for p in s.pts:
            g = ray_down(soil.tree, p.x, p.y)
            if g is not None:
                deep = max(deep, g - p.z)
        if s.part in (P_FCUP, P_FNUT):
            fallen[s.ident] = max(fallen.get(s.ident, -9.0), deep)
        else:
            rests.setdefault(s.part, []).append(deep)
    rests[P_FNUT] = list(fallen.values())
    parts = [soil] + cls["cover"]
    roots = union_components(parts)
    loose = sum(1 for r in roots[1:] if r != roots[0])
    return rests, loose


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
    img = bpy.data.images.new("OakNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = BARK_IDX
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
    plan = plan_tree()
    low = build_oak_mesh("OakLow", plan, "low", **flags)
    high = build_oak_mesh("OakHigh", plan, "high", **flags)
    mats = oak_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    bark = mats[BARK_IDX]

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
        return (fail("oak mesh did not build", 3),) + none2

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
    if len(cls["trunk"]) != 1 or len(cls["soil"]) != 1:
        return (fail(f"trunk/soil not found: {len(cls['trunk'])}/{len(cls['soil'])} shells", 3),) + none2
    soil0 = ray_down(cls["soil"][0].tree, 0.0, 0.0)
    n_branch = len(plan["branches"])
    n_leaves = len(plan["leaves"])
    n_carriers = len(set(plan["carriers"]))
    n_cores = len(plan["clumps"])
    n_hang = sum(a["n"] for a in plan["acorns"])
    expected_cover = TUFTS + LITTER + 2 * FALLEN_ACORNS + len(STICKS) + len(STICK_FORKS)
    seats, seat_missing, areas, widths, fork = branch_audits(low.data, cls)
    lean, balance, dbh, mass_z = plumb_audit(low.data, cls, soil0)
    sealed, root_beds = seal_audit(cls)
    core_seats, lump_bites, leaf_bites, carriers = leaf_audit(low.data, cls)
    n_lumps = len(plan["sats"])
    nuts, stalk_bites, ped_stalk, ped_cup = acorn_audit(cls)
    fnuts = fallen_nut_audit(cls)
    rests, loose = cover_audit(cls)

    img, tex = setup_bake_image(low, bark)
    if img is None:
        return (fail("oak has no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "OakLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "OakLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("OakColSrc", plan)
    collider = convex_hull_collider(collider_src, "OakCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_broadleaf_oak_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    all_nuts = nuts + fnuts
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
    print(f"measured shells={len(cls['all'])} branches={len(cls['branches'])}/{n_branch} "
          f"leaves={len(cls['leaves'])}/{n_leaves} carriers={len(carriers)}/{n_carriers} "
          f"roots={len(cls['roots'])} stalks={len(cls['stalks'])} cups={len(cls['cups'])} "
          f"nuts={len(cls['nuts'])}/{n_hang} cover={len(cls['cover'])}/{expected_cover}")
    print(f"measured seat min={min(seats):.4f} max={max(seats):.4f} n={len(seats)} "
          f"missing={seat_missing}")
    print(f"measured taper area min={min(areas):.4f} max={max(areas):.4f} n={len(areas)} "
          f"child_width max={max(widths):.4f} fork={fork:.4f}")
    print(f"measured nut_bite min={min(all_nuts):.4f} max={max(all_nuts):.4f} n={len(all_nuts)}")
    print(f"measured lean_deg={lean:.3f} balance={balance:.4f} mass_z={mass_z:.3f} dbh={dbh:.4f}")
    print(f"measured sealed={sealed}/{SEAL_SECTORS} root_bed min={min(root_beds):.4f} "
          f"n={len(root_beds)}")
    print(f"measured core_seat min={min(core_seats):.4f} max={max(core_seats):.4f} "
          f"n={len(core_seats)} lump_bite min={min(lump_bites):.4f} max={max(lump_bites):.4f} "
          f"n={len(lump_bites)} leaf_bite min={min(leaf_bites):.4f} max={max(leaf_bites):.4f} "
          f"n={len(leaf_bites)}")
    print(f"measured stalk_bite min={min(stalk_bites):.4f} pedicel_in_stalk "
          f"min={min(ped_stalk):.4f} pedicel_in_cup min={min(ped_cup):.4f} n={len(ped_cup)}")
    print(f"measured cover rest " + " ".join(
        f"{k}:{min(v):.4f}..{max(v):.4f}/{len(v)}" for k, v in sorted(rests.items()))
        + f" loose={loose}")

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
    # the taper is checked before the seat: a fat twig also bursts out of
    # its parent, and the budget it breaks first is the taper
    if (min(areas) < AREA_BAND[0] or max(areas) > AREA_BAND[1] or max(widths) > CHILD_MAX
            or not (FORK_BAND[0] <= fork <= FORK_BAND[1])):
        return (fail(f"taper: junction area ratio {min(areas):.4f}..{max(areas):.4f} (band "
                     f"{AREA_BAND}), widest child {max(widths):.4f} of its parent (max "
                     f"{CHILD_MAX}), fork {fork:.4f} (band {FORK_BAND})", 20),) + none2
    if (len(cls["branches"]) != n_branch or seat_missing or len(seats) != n_branch
            or min(seats) < SEAT_MIN):
        return (fail(f"branch seat: {len(seats)}/{n_branch} branches seated, shallowest base "
                     f"vertex {min(seats):.4f} of the parent's radius inside it (min {SEAT_MIN})",
                     17),) + none2
    if (len(all_nuts) != n_hang + FALLEN_ACORNS or min(all_nuts) < NUT_BITE[0]
            or max(all_nuts) > NUT_BITE[1]):
        return (fail(f"nut seat: {len(all_nuts)}/{n_hang + FALLEN_ACORNS} nuts, depth in cup "
                     f"{min(all_nuts):.4f}..{max(all_nuts):.4f} (band {NUT_BITE})", 18),) + none2
    if lean > LEAN_MAX_DEG or balance > BALANCE_MAX or abs(dbh - DBH) > DBH_TOL:
        return (fail(f"plumb/balance: lean {lean:.3f} deg (max {LEAN_MAX_DEG}), balance "
                     f"{balance:.4f} m (max {BALANCE_MAX}), dbh {dbh:.4f} "
                     f"(want {DBH} +/- {DBH_TOL})", 19),) + none2
    if sealed < SEAL_SECTORS or len(root_beds) != ROOTS or min(root_beds) < ROOT_BED_MIN:
        return (fail(f"sealed: trunk in {sealed}/{SEAL_SECTORS} sectors, {len(root_beds)}/{ROOTS} "
                     f"roots, shallowest root station {min(root_beds):.4f} (min {ROOT_BED_MIN})",
                     21),) + none2
    if (len(leaf_bites) != n_leaves or len(core_seats) != n_cores or len(lump_bites) != n_lumps
            or len(carriers) != n_carriers or min(core_seats) < CORE_BITE_MIN
            or min(lump_bites) < LUMP_BITE_MIN or min(leaf_bites) < LEAF_BITE_MIN):
        return (fail(f"leaf clumps: {len(core_seats)}/{n_cores} cores on {len(carriers)} "
                     f"carriers, shallowest carrier {min(core_seats):.4f} m inside its core (min "
                     f"{CORE_BITE_MIN}); {len(lump_bites)}/{n_lumps} clusters, shallowest "
                     f"{min(lump_bites):.4f} m into its core (min {LUMP_BITE_MIN}); "
                     f"{len(leaf_bites)}/{n_leaves} leaves, shallowest petiole "
                     f"{min(leaf_bites):.4f} m inside its cluster (min {LEAF_BITE_MIN})", 22),) + none2
    if (len(cls["stalks"]) != len(plan["acorns"]) or len(ped_cup) != n_hang
            or min(stalk_bites) < STALK_BITE_MIN or min(ped_stalk) < PEDICEL_BITE_MIN
            or min(ped_cup) < CUP_BITE_MIN):
        return (fail(f"hanging acorns: {len(cls['stalks'])} stalks, {len(ped_cup)}/{n_hang} "
                     f"pedicels; stalk in branch {min(stalk_bites):.4f} (min {STALK_BITE_MIN}), "
                     f"pedicel in stalk {min(ped_stalk):.4f} (min {PEDICEL_BITE_MIN}), pedicel "
                     f"in cup {min(ped_cup):.4f} (min {CUP_BITE_MIN})", 23),) + none2
    bands = {P_TUFT: TUFT_BAND, P_LITTER: REST_BAND, P_FNUT: REST_BAND, P_STICK: REST_BAND}
    bad = [(k, round(v, 4)) for k, vs in rests.items() for v in vs
           if not (bands[k][0] <= v <= bands[k][1])]
    n_cover = sum(len(v) for v in rests.values())
    if n_cover != TUFTS + LITTER + FALLEN_ACORNS + len(STICKS) + len(STICK_FORKS) or bad or loose:
        return (fail(f"ground cover: {n_cover} pieces, out of band {bad[:6]}, {loose} shells "
                     f"not joined to the soil", 24),) + none2
    return 0, low, bark


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
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.031, 0.033, 0.038, 1.0)
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

    # Key, fill, rim and the warm wedge, scaled for an 8 m tree. The key's
    # spread keeps it on the crown instead of flooding the near floor.
    light("Key", (-12.0, -15.0, 10.0), 7200.0, 5.0, (1.0, 0.95, 0.88), spread=30.0)
    light("Fill", (15.0, -10.0, 1.0), 1150.0, 18.0, (0.72, 0.82, 1.0))
    light("Rim", (-4.0, 7.0, 6.0), 900.0, 5.0, (0.62, 0.78, 1.0))
    light("Wedge", (8.5, 3.0, 3.5), 2100.0, 7.0, (1.0, 0.70, 0.42),
          target=(5.0, WALL_Y - 4.0, 0.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.42, -0.91, 0.0)).normalized()
    cam.location = centre + view * CAM_DIST + Vector((0.0, 0.0, CAM_DZ))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, 0.05))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the leaves.
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 25
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return fail("render produced no file", 14)
    return 0


FLAG_NAMES = ("float_branches", "pop_nuts", "lean_crown", "fat_twigs", "perch_trunk",
              "arch_roots", "orphan_clump", "scatter_clusters", "shed_leaves", "drop_acorns",
              "float_cover")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--float-branches", action="store_true")
    p.add_argument("--pop-nuts", action="store_true")
    p.add_argument("--lean-crown", action="store_true")
    p.add_argument("--fat-twigs", action="store_true")
    p.add_argument("--perch-trunk", action="store_true")
    p.add_argument("--arch-roots", action="store_true")
    p.add_argument("--orphan-clump", action="store_true")
    p.add_argument("--scatter-clusters", action="store_true")
    p.add_argument("--shed-leaves", action="store_true")
    p.add_argument("--drop-acorns", action="store_true")
    p.add_argument("--float-cover", action="store_true")
    args = p.parse_args(argv)

    code, low, _bark = check(
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
    print("broadleaf-oak OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
