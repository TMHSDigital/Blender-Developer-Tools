"""Game-ready pond margin — a showcase piece, not an example.

Asserts budget conformance of a procedural pond-edge vignette after
composing shipped pipeline pieces: bmesh construction, UVs, nine materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

A raised soil disc holds a shallow pond. The bank slopes from turf down
through a wet mud band into the basin; the water is its own mesh at a
declared level, rippled in low rings round the reeds and the branch, and its
rim runs on under the bank so no edge of it shows. A clump of cattails
stands in the shallows: arching strap leaves from one base and five stems,
each threaded through a brown seed head with a bare spike above it. Soft
rush tufts grow on the bank. Four notched lily pads float on the water with
two layered white-and-pink flowers among them; wet stones sit at the
waterline, a dead branch runs from the bank into the water, and pebbles and
fallen leaves lie on the mud.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--float-reeds`` every cattail leaf and stem
rooted in the mud, ``--sink-pad`` every pad floating at the water level,
``--flat-water`` the water level and ripple band, ``--slip-heads`` every
seed head threaded on its stem, ``--short-water`` the water enclosed by
the bank, ``--float-cover`` the ground cover joined to the soil.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python pond_edge.py --
    blender --background --python pond_edge.py -- --skip-decimate
    blender --background --python pond_edge.py -- --output pond.png
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

SEED = 6151
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- Ground ------------------------------------------------------------------
DISC_A = (1.58, 1.30)     # soil disc semi-axes before its wobble, m
DISC_EDGE = 0.13          # the rim rolls down over this fraction of the radius
DISC_N = {"low": 52, "high": 76}
LAND_Z = 0.17             # the bank's top at the front
BACK_RISE = 0.085         # the back bank stands this much higher
FLOOR_Z = 0.035           # the basin's floor at the pond's centre
POND_C = (0.0, -0.09)
POND_R = 0.99
BANK_OUT = 0.08           # the bank starts falling this far outside the pond radius
BANK_IN = 0.32            # and reaches the floor this far inside it

# --- Water -------------------------------------------------------------------
WATER_LEVEL = 0.115
WATER_MARGIN = 0.05       # the rim runs this far past the shoreline, under the bank
WATER_SLAB = 0.03
WATER_N = {"low": 52, "high": 80}
RIPPLE_AMP = 0.0026
RIPPLE_WAVE = 0.105
RIPPLE_DECAY = 0.28
WIND_AMP = 0.0006
CALM_W = 0.06             # ripples die out over this width round a pad or flower

# --- Cattails ----------------------------------------------------------------
CLUMP_AZ = 128.0          # the clump's bearing from the pond centre, degrees
CLUMP_IN = 0.11           # inside the shoreline, in the shallows
CLUMP_R = 0.110
N_LEAVES = 34
N_STEMS = 5
ROOT_DEPTH = 0.040        # every leaf and stem starts this far under the mud
ROOT_STEP = 0.0013        # staggered, so no two stem caps share a plane
LEAF_SEGS = 12

# --- Water plants, stones, branch, cover -----------------------------------
# lily pads (pond-local x, y, radius); flowers and floating leaves (x, y)
PADS = ((-0.44, -0.20, 0.145), (0.04, -0.34, 0.125), (0.46, 0.02, 0.115), (-0.06, 0.16, 0.135),
        (-0.72, 0.10, 0.110))
PAD_NA = 30
PAD_K = 4
PAD_NOTCH = 0.24          # the slit, radians
PAD_T = 0.003
PAD_TOP = 0.0015          # the pad's top over the water at its centre
PAD_UPTURN = 0.0035
FLOWERS = ((-0.20, -0.06), (0.26, -0.15))
FLOWER_SCALE = 1.25
FLOWER_REACH = 0.09
FLOATERS = ((-0.70, -0.18), (0.50, 0.22), (0.18, 0.28))
# wet stones on the shoreline: (bearing deg, radius)
STONES = ((214.0, 0.130), (158.0, 0.090), (-62.0, 0.120), (-98.0, 0.080), (24.0, 0.100))
BRANCH_AZ = -12.0
BRANCH_OUT = 0.20         # the butt on the bank, this far past the shoreline
BRANCH_IN = 0.28          # the tip in the water, this far inside it
# rush tufts: (bearing deg, out from the shoreline m, size)
TUFTS = ((70.0, 0.20, 1.00), (90.0, 0.34, 0.90), (48.0, 0.22, 0.80), (140.0, 0.22, 0.85),
         (163.0, 0.12, 0.62), (-40.0, 0.07, 0.50), (-150.0, 0.07, 0.48), (106.0, 0.24, 0.75),
         (24.0, 0.14, 0.60))
N_TURF = 16
N_PEBBLES = 24
N_LITTER = 34

# falsifiers
FLOAT_REEDS = 0.070       # --float-reeds: every leaf and stem base raised, tips held
SINK_PAD = 0.004          # --sink-pad: the first pad pushed under, its rim still awash
SLIP_HEADS = 0.008        # --slip-heads: every seed head slid sideways off its stem's axis
SHORT_MARGIN = -0.06      # --short-water: the rim stops short of the shoreline
FLOAT_COVER = 0.030       # --float-cover: every rush, pebble and bank leaf lifted

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from the vertices.
OUTER_SIZE = (3.2040, 2.6342, 1.5071)
BASE_TRIS_MIN = 36900
BASE_TRIS_MAX = 38300
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 9
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 120
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# water, soil, reed, seed head, pad, flower, stone, wood, litter
FACE_FLOORS = (5240, 5050, 7340, 1260, 1250, 1290, 1840, 210, 360)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Rooted: each leaf's and stem's lowest vertex under the soil straight above it.
ROOT_MIN = 0.020
ROOT_MAX = 0.070
# Floating: each pad's mean height over the water under its centroid, how far
# its lowest vertex draws under that water, and the tilt of its fitted plane.
FREEBOARD_MIN = -0.0005
FREEBOARD_MAX = 0.0040
DRAFT_MIN = 0.0005
DRAFT_MAX = 0.0040
PAD_TILT_MAX = 3.0
# Water: the median height of the surface, and its largest excursion from it.
LEVEL_TOL = 0.0015
RIPPLE_MIN = 0.0015
RIPPLE_MAX = 0.0090
# Heads: the stem's in-head centroid off the head's axis; the spike above it.
HEAD_AXIS_TOL = 0.002
SPIKE_MIN = 0.06
# Enclosed: the bank over every rim vertex and rim-edge midpoint of the water.
ENCLOSE_MIN = 0.008
HERO_YAW_DEG = 0.0
WALL_Y = 4.2

WATER_IDX = 0
SOIL_IDX = 1
REED_IDX = 2
SEED_IDX = 3
PAD_IDX = 4
FLOWER_IDX = 5
STONE_IDX = 6
WOOD_IDX = 7
LITTER_IDX = 8
MAT_LABELS = ("water", "soil", "reed", "seed head", "pad", "flower", "stone", "wood", "litter")

# part labels (a face attribute): they name a shell, they never measure it
P_SOIL, P_WATER, P_LEAF, P_STEM, P_HEAD, P_RUSH = 1, 2, 3, 4, 5, 6
P_PAD, P_FLOWER, P_STONE, P_BRANCH, P_PEBBLE, P_LITTER = 7, 8, 9, 10, 11, 12


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


def rotz(deg):
    return Matrix.Rotation(math.radians(deg), 3, "Z")


def perp_basis(d):
    ref = UP if abs(d.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = d.cross(ref).normalized()
    return e1, d.cross(e1).normalized()


def squircle(i, k, n):
    """A square grid mapped onto the unit disc (its border on the circle)."""
    uu = -1.0 + 2.0 * i / n
    vv = -1.0 + 2.0 * k / n
    return uu * math.sqrt(1.0 - vv * vv / 2.0), vv * math.sqrt(1.0 - uu * uu / 2.0)


# --------------------------------------------------------------------------
# The ground and the water surface as functions of plan position
# --------------------------------------------------------------------------

def disc_wobble(th):
    return 1.0 + 0.05 * math.sin(3.0 * th + 0.7) + 0.035 * math.sin(5.0 * th + 2.1) \
        + 0.02 * math.sin(8.0 * th + 0.3)


def disc_radius(x, y):
    """Normalised disc radius: 1 on the soil's rim."""
    X, Y = x / DISC_A[0], y / DISC_A[1]
    return math.hypot(X, Y) / disc_wobble(math.atan2(Y, X))


def pond_radius(th):
    return POND_R * (1.0 + 0.14 * math.cos(2.0 * (th - 0.15)) + 0.04 * math.sin(3.0 * th + 1.9)
                     + 0.025 * math.sin(5.0 * th + 0.2))


def pond_polar(x, y):
    dx, dy = x - POND_C[0], y - POND_C[1]
    return math.hypot(dx, dy), math.atan2(dy, dx)


def soil_height(x, y):
    """The bank: turf at LAND_Z falling through the waterline to the basin
    floor, all of it rolled down to Z = 0 at the disc's rim."""
    amb = (LAND_Z + BACK_RISE * smoothstep(y, -0.35, 1.05)
           + 0.016 * math.sin(1.7 * x + 0.4) * math.cos(1.5 * y + 0.8)
           + 0.009 * math.sin(3.9 * x - 2.7 * y + 1.1) + 0.004 * math.sin(7.3 * x + 5.1 * y))
    rho, th = pond_polar(x, y)
    R = pond_radius(th)
    s = smoothstep(R - rho, -BANK_OUT, BANK_IN)
    floor = FLOOR_Z + 0.04 * (rho / R) ** 2
    z = amb * (1.0 - s) + floor * s
    return z * smoothstep(1.0 - disc_radius(x, y), 0.0, DISC_EDGE)


def soil_wet(x, y, z):
    """1 on the mud at and under the waterline, 0 on dry turf; the disc's
    outer skirt is never wet, whatever its height."""
    rho, th = pond_polar(x, y)
    near = smoothstep(pond_radius(th) - rho, -BANK_OUT - 0.10, -BANK_OUT + 0.02)
    return (1.0 - smoothstep(z - WATER_LEVEL, 0.004, 0.055)) * near


_SHORE = {}


def shore(th):
    """Distance from the pond centre to the waterline along bearing th."""
    key = round(th, 9)
    if key in _SHORE:
        return _SHORE[key]
    c, s = math.cos(th), math.sin(th)
    lo, hi = 0.0, pond_radius(th) + BANK_OUT + 0.05
    for _ in range(44):
        mid = 0.5 * (lo + hi)
        if soil_height(POND_C[0] + mid * c, POND_C[1] + mid * s) < WATER_LEVEL:
            lo = mid
        else:
            hi = mid
    _SHORE[key] = 0.5 * (lo + hi)
    return _SHORE[key]


def pond_point(th, rho):
    return POND_C[0] + rho * math.cos(th), POND_C[1] + rho * math.sin(th)


# --------------------------------------------------------------------------
# The plan: every seeded draw happens here, before anything is built
# --------------------------------------------------------------------------

def plan_pond():
    rng = random.Random(SEED)

    def u(a, b):
        return a + (b - a) * rng.random()

    plan = {}
    plan["leaves"] = [{"az": TAU * k / N_LEAVES + u(-0.22, 0.22), "off": (u(-1, 1), u(-1, 1)),
                       "L": u(0.70, 1.12), "a0": u(0.04, 0.20), "a1": u(0.50, 1.30),
                       "p": u(1.8, 2.8), "w": u(0.018, 0.026), "tw": u(-0.40, 0.40),
                       "tone": rng.random()} for k in range(N_LEAVES)]
    stems = []
    for k in range(N_STEMS):
        a = TAU * k / N_STEMS + u(-0.3, 0.3)
        r = u(0.45, 1.0)
        # each stem leans out of the stand, so the heads stand apart
        stems.append({"off": (math.cos(a) * r, math.sin(a) * r), "lean_az": a + u(-0.4, 0.4),
                      "H": u(1.24, 1.48), "lean": u(0.05, 0.12),
                      "head_len": u(0.13, 0.17), "head_r": u(0.0125, 0.0150),
                      "spike": u(0.09, 0.14), "ph": u(0.0, TAU), "tone": rng.random()})
    plan["stems"] = stems
    plan["pads"] = [{"notch": u(0.0, TAU), "ph": u(0.0, TAU), "tone": rng.random(),
                     "j": (u(-0.008, 0.008), u(-0.008, 0.008))} for _k in PADS]
    plan["flowers"] = [{"spin": u(0.0, TAU), "tone": rng.random(), "ph": u(0.0, TAU)}
                       for _k in FLOWERS]
    plan["floaters"] = [{"yaw": u(0.0, TAU), "len": u(0.055, 0.075), "wid": u(0.55, 0.70),
                         "cup": u(0.20, 0.45), "tone": rng.random()} for _k in FLOATERS]
    plan["stones"] = [{"flat": u(0.40, 0.52), "long": u(1.15, 1.45), "yaw": u(0.0, TAU),
                       "tone": rng.random(),
                       "waves": [(Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized(),
                                  u(0.0, TAU), a) for a in (0.10, 0.06, 0.035)]}
                      for _k in STONES]
    plan["branch"] = {"wig": [u(-1, 1) for _k in range(8)], "tone": rng.random(),
                      "twigs": [(u(0.25, 0.40), u(0.55, 0.90), u(0.20, 0.32)),
                                (u(0.55, 0.70), u(-0.95, -0.60), u(0.14, 0.22))]}
    plan["tufts"] = [{"j": (u(-0.03, 0.03), u(-0.03, 0.03)), "tone": rng.random(),
                      "blades": [{"yaw": u(0.0, TAU), "h": u(0.50, 1.0), "lean": u(0.10, 0.50),
                                  "w": u(0.8, 1.25), "tw": u(-0.6, 0.6), "off": (u(-1, 1), u(-1, 1)),
                                  "tone": rng.random()} for _b in range(64)]}
                     for _k in TUFTS]

    def spot():
        while True:
            X, Y = u(-1.0, 1.0), u(-1.0, 1.0)
            if X * X + Y * Y <= 1.0:
                return X * DISC_A[0] * 0.84, Y * DISC_A[1] * 0.84

    turf = []
    for _k in range(300):
        x, y = spot()
        turf.append({"x": x, "y": y, "tone": rng.random(), "h": u(0.10, 0.19), "n": rng.choice((10, 12, 14)),
                     "spread": u(0.025, 0.040),
                     "blades": [{"yaw": u(0.0, TAU), "h": u(0.55, 1.0), "lean": u(0.25, 0.70),
                                 "w": u(0.7, 1.0), "tw": u(-0.5, 0.5), "off": (u(-1, 1), u(-1, 1)),
                                 "tone": rng.random()} for _b in range(16)]})
    plan["turf"] = turf
    pebbles = []
    for _k in range(600):
        x, y = spot()
        pebbles.append({"x": x, "y": y, "r": 0.016 + 0.040 * rng.random() ** 2.0,
                        "flat": u(0.45, 0.72), "long": u(1.0, 1.5), "yaw": u(0.0, TAU),
                        "tilt": (u(-0.2, 0.2), u(-0.2, 0.2)), "tone": rng.random(),
                        "waves": [(Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized(),
                                   u(0.0, TAU), a) for a in (1.0, 0.6, 0.4, 0.3)],
                        "near": rng.random()})
    plan["pebbles"] = pebbles
    litter = []
    for _k in range(600):
        x, y = spot()
        litter.append({"x": x, "y": y, "yaw": u(0.0, TAU), "len": u(0.055, 0.085),
                       "wid": u(0.45, 0.70), "cup": u(0.15, 0.50), "tone": rng.random(),
                       "near": rng.random()})
    plan["litter"] = litter
    plan["ripple_ph"] = [u(0.0, TAU) for _k in range(16)]
    return plan


# --------------------------------------------------------------------------
# Layout: where everything goes, decided once against the default build
# --------------------------------------------------------------------------

class Layout:
    def __init__(self, plan):
        self.plan = plan
        th = math.radians(CLUMP_AZ)
        self.clump = pond_point(th, shore(th) - CLUMP_IN)
        cx, cy = self.clump
        self.stems = []
        for st in plan["stems"]:
            s = dict(st)
            s["x"] = cx + st["off"][0] * CLUMP_R
            s["y"] = cy + st["off"][1] * CLUMP_R
            self.stems.append(s)
        self.leaves = []
        for lf in plan["leaves"]:
            q = dict(lf)
            q["x"] = cx + lf["off"][0] * 0.045
            q["y"] = cy + lf["off"][1] * 0.045
            self.leaves.append(q)

        self.pads = []
        for (px, py, r), pp in zip(PADS, plan["pads"]):
            self.pads.append(dict(pp, x=POND_C[0] + px + pp["j"][0], y=POND_C[1] + py + pp["j"][1], r=r))
        self.flowers = [dict(fp, x=POND_C[0] + fx, y=POND_C[1] + fy)
                        for (fx, fy), fp in zip(FLOWERS, plan["flowers"])]
        self.floaters = [dict(fp, x=POND_C[0] + fx, y=POND_C[1] + fy)
                         for (fx, fy), fp in zip(FLOATERS, plan["floaters"])]
        for item, reach in ([(p, p["r"]) for p in self.pads] + [(f, FLOWER_REACH) for f in self.flowers]
                            + [(f, 0.045) for f in self.floaters]):
            rho, th = pond_polar(item["x"], item["y"])
            if rho + reach + 0.06 > shore(th):
                raise RuntimeError(f"floating part at ({item['x']:.2f}, {item['y']:.2f}) "
                                   "too near the shore")
        floats = [(p["x"], p["y"], p["r"]) for p in self.pads] + \
            [(f["x"], f["y"], FLOWER_REACH) for f in self.flowers] + [(f["x"], f["y"], 0.045) for f in self.floaters]
        for i, a in enumerate(floats):
            for b in floats[i + 1:]:
                if math.hypot(a[0] - b[0], a[1] - b[1]) < a[2] + b[2] + 0.015:
                    raise RuntimeError("floating parts overlap")

        self.stones = []
        for (az, r), sp in zip(STONES, plan["stones"]):
            th = math.radians(az)
            x, y = pond_point(th, shore(th) + 0.012)
            self.stones.append(dict(sp, x=x, y=y, r=r))

        th = math.radians(BRANCH_AZ)
        s0 = shore(th)
        br = plan["branch"]
        pts = []
        side = Vector((-math.sin(th), math.cos(th), 0.0))
        for k in range(8):
            t = k / 7.0
            rho = s0 + BRANCH_OUT - (BRANCH_OUT + BRANCH_IN) * t
            x, y = pond_point(th, rho)
            p = Vector((x, y, 0.0)) + side * (0.035 * br["wig"][k] + 0.05 * math.sin(2.6 * t + 0.4))
            pts.append(p)
        r0, r1 = 0.034, 0.016
        z0 = soil_height(pts[0].x, pts[0].y) + 0.20 * r0
        z1 = WATER_LEVEL - 0.55 * r1
        for k, p in enumerate(pts):
            t = k / 7.0
            p.z = z0 + (z1 - z0) * t - 0.012 * math.sin(math.pi * t)
        self.branch = {"pts": pts, "r0": r0, "r1": r1, "tone": br["tone"], "twigs": br["twigs"]}
        if disc_radius(pts[0].x, pts[0].y) > 0.84:
            raise RuntimeError("the branch's butt is off the bank")
        for fx, fy, reach in floats:
            if any(math.hypot(p.x - fx, p.y - fy) < reach + 0.04 for p in pts):
                raise RuntimeError("the branch runs into a floating part")
        entry = None
        for a, b in zip(pts, pts[1:]):
            if a.z >= WATER_LEVEL > b.z:
                f = (a.z - WATER_LEVEL) / (a.z - b.z)
                entry = a.lerp(b, f)
        self.branch_entry = entry

        self.tufts = []
        for (az, out, size), tp in zip(TUFTS, plan["tufts"]):
            th = math.radians(az)
            x, y = pond_point(th, shore(th) + out)
            if disc_radius(x, y) > 0.80:
                raise RuntimeError(f"rush tuft at {az} deg is off the bank")
            self.tufts.append(dict(tp, x=x + tp["j"][0], y=y + tp["j"][1], size=size,
                                   n=int(round(60 * size)), h=0.26 + 0.42 * size,
                                   spread=0.028 + 0.036 * size))

        # ripple sources: the clump, every stem, the branch where it goes in,
        # two of the stones; calm round everything floating
        ph = plan["ripple_ph"]
        src = [(cx, cy, 1.0, ph[0])]
        for k, s in enumerate(self.stems):
            src.append((s["x"], s["y"], 0.55, ph[1 + k]))
        if entry is not None:
            src.append((entry.x, entry.y, 0.9, ph[8]))
        for k in (0, 2):
            st = self.stones[k]
            src.append((st["x"], st["y"], 0.45, ph[9 + k]))
        self.sources = src
        self.calmers = [(p["x"], p["y"], p["r"] + 0.02) for p in self.pads] + \
            [(f["x"], f["y"], FLOWER_REACH - 0.005) for f in self.flowers] +             [(f["x"], f["y"], 0.045) for f in self.floaters]

        # scatter: pebbles near the waterline and on the turf, leaves on the bank
        occupied = [(t["x"], t["y"], 0.16 * t["size"] + 0.05) for t in self.tufts]
        occupied += [(s["x"], s["y"], s["r"] * 1.5 + 0.04) for s in self.stones]
        occupied += [(p.x, p.y, 0.07) for p in pts]
        occupied.append((cx, cy, 0.14))

        def free(x, y, r, placed):
            return all(math.hypot(x - px, y - py) > r + pr for px, py, pr in occupied + placed)

        def bank(x, y, near):
            z = soil_height(x, y)
            if disc_radius(x, y) > 0.83 or z < WATER_LEVEL + 0.006:
                return False
            rho, th = pond_polar(x, y)
            out = rho - shore(th)
            return out < 0.22 if near else out >= 0.22

        placed = []
        self.turf = []
        for tf in plan["turf"]:
            if not bank(tf["x"], tf["y"], False) or not free(tf["x"], tf["y"], 0.09, placed):
                continue
            self.turf.append(tf)
            placed.append((tf["x"], tf["y"], 0.09))
            if len(self.turf) >= N_TURF:
                break
        self.pebbles = []
        for pb in plan["pebbles"]:
            if not bank(pb["x"], pb["y"], pb["near"] < 0.85):
                continue
            if not free(pb["x"], pb["y"], pb["r"] * 1.6, placed):
                continue
            self.pebbles.append(pb)
            placed.append((pb["x"], pb["y"], pb["r"] * 1.6))
            if len(self.pebbles) >= N_PEBBLES:
                break
        self.litter = []
        for lf in plan["litter"]:
            if not bank(lf["x"], lf["y"], lf["near"] < 0.5):
                continue
            if not free(lf["x"], lf["y"], 0.040, placed):
                continue
            self.litter.append(lf)
            placed.append((lf["x"], lf["y"], 0.040))
            if len(self.litter) >= N_LITTER:
                break

    def ripple(self, x, y, flat=False):
        if flat:
            return 0.0
        h = 0.0
        for sx, sy, amp, ph in self.sources:
            r = math.hypot(x - sx, y - sy)
            h += (RIPPLE_AMP * amp * math.exp(-r / RIPPLE_DECAY)
                  * math.sin(TAU * r / RIPPLE_WAVE - ph) * smoothstep(r, 0.008, 0.045))
        h += WIND_AMP * (0.6 * math.sin(9.1 * x + 4.3 * y + 0.3) + 0.4 * math.sin(-6.7 * x + 11.2 * y + 1.7))
        calm = 1.0
        for cx, cy, rc in self.calmers:
            calm *= smoothstep(math.hypot(x - cx, y - cy), rc, rc + CALM_W)
        return h * calm


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
    # every cell split on its short diagonal: a ray onto a non-planar quad
    # lands on whichever diagonal the tree picks
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


def add_soil(bm, L, V, n):
    grid = []
    for i in range(n + 1):
        col = []
        for k in range(n + 1):
            X, Y = squircle(i, k, n)
            wob = disc_wobble(math.atan2(Y, X))
            x = DISC_A[0] * X * wob
            y = DISC_A[1] * Y * wob
            on_rim = i in (0, n) or k in (0, n)
            z = 0.0 if on_rim else soil_height(x, y)
            v = bm.verts.new((x, y, z))
            v[V["wet"]] = soil_wet(x, y, z)
            v[V["turf"]] = ((1.0 - smoothstep(disc_radius(x, y), 0.82, 0.92))
                            * smoothstep(z - WATER_LEVEL, 0.02, 0.06))
            v[V["skirt"]] = smoothstep(disc_radius(x, y), 0.85, 0.92)
            col.append(v)
        grid.append(col)
    grid_faces(bm, grid, n, SOIL_IDX, L, 0.5, P_SOIL)
    new_face(bm, list(reversed(grid_rim(grid, n))), SOIL_IDX, L, 0.5, 0.0, P_SOIL)


def add_water(bm, L, V, lay, n, margin, flat):
    """The water: a rippled sheet out to the rim (past the shoreline, under
    the bank), a short wall down, and a flat underside."""
    grid = []
    for i in range(n + 1):
        col = []
        for k in range(n + 1):
            X, Y = squircle(i, k, n)
            r = math.hypot(X, Y)
            th = math.atan2(Y, X)
            rho = r * (shore(th) + margin)
            x, y = pond_point(th, rho)
            v = bm.verts.new((x, y, WATER_LEVEL + lay.ripple(x, y, flat)))
            v[V["depth"]] = max(0.0, WATER_LEVEL - soil_height(x, y))
            col.append(v)
        grid.append(col)
    grid_faces(bm, grid, n, WATER_IDX, L, 0.5, P_WATER)
    rim = grid_rim(grid, n)
    zb = WATER_LEVEL - WATER_SLAB
    low = [bm.verts.new((v.co.x, v.co.y, zb)) for v in rim]
    m = len(rim)
    for j in range(m):
        q = (j + 1) % m
        new_face(bm, (rim[j], rim[q], low[q], low[j]), WATER_IDX, L, 0.5, 1.0, P_WATER)
    centre = bm.verts.new((POND_C[0], POND_C[1], zb))
    for j in range(m):
        new_face(bm, (low[(j + 1) % m], low[j], centre), WATER_IDX, L, 0.5, 1.0, P_WATER)


def soil_hit(tree, x, y):
    loc, nrm, _i, _d = tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
    if loc is None:
        return Vector((x, y, 0.0)), Vector((0.0, 0.0, 1.0))
    if nrm.z < 0.0:
        nrm = -nrm
    return loc, nrm


def add_strap(bm, pts, width, thick, hd, twist, mat, L, V, tone, part, lift=0.0, section=4, roll=0.0):
    """A strap along ``pts`` ending in a point: a diamond section for a
    cattail leaf, a V section (``section=3``) for a rush blade. ``lift``
    raises the root and fades to 0 at the tip."""
    n = len(pts) - 1
    pts = [p + UP * (lift * (1.0 - k / n)) for k, p in enumerate(pts)]
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
        if section == 4:
            ring = [bm.verts.new(pts[i] - side * w), bm.verts.new(pts[i] + nrm * th),
                    bm.verts.new(pts[i] + side * w), bm.verts.new(pts[i] - nrm * th)]
        else:
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
        for q in range(section):
            w = (q + 1) % section
            new_face(bm, (r0[q], r1[q], r1[w], r0[w]), mat, L, tone, 0.0, part)
    last = rings[-1]
    for q in range(section):
        new_face(bm, (last[q], tip, last[(q + 1) % section]), mat, L, tone, 0.0, part)


def add_tube(bm, pts, radii, sides, mats, L, V, tone, part, zones=None, tip=None, alongs=None,
             phase=0.0):
    """A tube through ``pts`` with parallel-transported rings, a flat base
    cap, and either a flat top cap or a point at ``tip``. ``mats``/``zones``
    are per segment."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tans = []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)] if tip is None or i < n - 1 else Vector(tip)
        tans.append((b - a).normalized())
    e1, e2 = perp_basis(tans[0])
    # each tube starts its facets at its own angle: two parallel tubes with
    # one frame would lay facets on shared planes
    nrm = e1 * math.cos(phase) + e2 * math.sin(phase)
    rings = []
    for i, (p, t, r) in enumerate(zip(pts, tans, radii)):
        nrm = (nrm - t * nrm.dot(t)).normalized()
        b = t.cross(nrm)
        ring = [bm.verts.new(p + r * (nrm * math.cos(TAU * k / sides) + b * math.sin(TAU * k / sides)))
                for k in range(sides)]
        if alongs is not None:
            for v in ring:
                v[V["along"]] = alongs[i]
        rings.append(ring)
    zones = zones or [0.0] * n
    for i, (r0, r1) in enumerate(zip(rings, rings[1:])):
        for k in range(sides):
            m = (k + 1) % sides
            new_face(bm, (r0[k], r0[m], r1[m], r1[k]), mats[i], L, tone, zones[i], part)
    new_face(bm, tuple(reversed(rings[0])), mats[0], L, tone, zones[0], part)
    if tip is None:
        new_face(bm, tuple(rings[-1]), mats[-1], L, tone, zones[-1], part)
    else:
        tv = bm.verts.new(tip)
        if alongs is not None:
            tv[V["along"]] = 1.0
        for k in range(sides):
            new_face(bm, (rings[-1][k], rings[-1][(k + 1) % sides], tv), mats[-1], L, tone,
                     zones[-1], part)


def add_lens(bm, outline, top, bottom, mat, L, tone, zone, part, V=None, alongs=None, mid_along=0.5):
    ring = [bm.verts.new(p) for p in outline]
    vt = bm.verts.new(top)
    vb = bm.verts.new(bottom)
    if alongs is not None:
        for v, a in zip(ring, alongs):
            v[V["along"]] = a
        vt[V["along"]] = mid_along
        vb[V["along"]] = mid_along
    n = len(ring)
    for k in range(n):
        m = (k + 1) % n
        new_face(bm, (ring[k], ring[m], vt), mat, L, tone, zone, part)
        new_face(bm, (ring[m], ring[k], vb), mat, L, tone, zone, part)


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


# --------------------------------------------------------------------------
# The parts
# --------------------------------------------------------------------------

def leaf_path(base, az, length, a0, a1, p):
    hd = Vector((math.cos(az), math.sin(az), 0.0))
    for _try in range(12):
        pts = [base.copy()]
        pos = base.copy()
        ds = length / LEAF_SEGS
        for i in range(LEAF_SEGS):
            s = (i + 0.5) / LEAF_SEGS
            a = a0 + (a1 - a0) * s ** p
            pos = pos + (hd * math.sin(a) + UP * math.cos(a)) * ds
            pts.append(pos.copy())
        # a leaf arches over; it never droops its tip into the water
        if pts[-1].z > WATER_LEVEL + 0.40:
            return pts, hd
        a1 -= 0.08
    return pts, hd


def add_leaf(bm, L, V, lf, soil_tree, lift, idx):
    base, _n = soil_hit(soil_tree, lf["x"], lf["y"])
    base = base - UP * (ROOT_DEPTH + ROOT_STEP * (idx % 5) * 0.5)
    pts, hd = leaf_path(base, lf["az"], lf["L"], lf["a0"], lf["a1"], lf["p"])
    W = lf["w"]

    def width(s):
        return W * (1.0 - 0.28 * s) * (1.0 if s < 0.70 else ((1.0 - s) / 0.30) ** 0.7)

    def thick(s):
        return 0.0018 * (1.0 - 0.6 * s)

    add_strap(bm, pts, width, thick, hd, lf["tw"], REED_IDX, L, V, lf["tone"], P_LEAF, lift)


def stem_frame(st, base):
    ld = Vector((math.cos(st["lean_az"]), math.sin(st["lean_az"]), 0.0))
    H = st["H"]

    def at(s):
        return base + UP * (H * s) + ld * (st["lean"] * H * s * s)

    def tangent(s):
        return (UP * H + ld * (2.0 * st["lean"] * H * s)).normalized()

    return at, tangent


def stem_heights(st):
    H = st["H"]
    ht = 1.0 - st["spike"] / H              # head top, as a fraction of H
    hb = ht - st["head_len"] / H            # head bottom
    return hb, ht


def add_stem(bm, L, V, st, soil_tree, lift, slip, idx):
    base, _n = soil_hit(soil_tree, st["x"], st["y"])
    base = base - UP * (ROOT_DEPTH + ROOT_STEP * idx)
    at, tangent = stem_frame(st, base)
    hb, ht = stem_heights(st)
    ss = [hb * k / 14.0 for k in range(14)]
    ss += [hb + (ht - hb) * k / 4.0 for k in range(5)]
    ss += [ht + (1.0 - ht) * (0.12 + 0.88 * k / 7.0) for k in range(7)]
    ss = ss[:-1]
    radii = []
    mats = []
    zones = []
    for s in ss:
        if s < hb:
            radii.append(0.0052 + (0.0036 - 0.0052) * s / hb)
        elif s <= ht + 1e-9:
            radii.append(0.0034)
        else:
            f = (s - ht) / (1.0 - ht)
            radii.append(0.0021 + (0.0007 - 0.0021) * f)
        mats.append(SEED_IDX if s >= ht - 1e-9 else REED_IDX)
        zones.append(2.0 if s >= ht - 1e-9 else 0.0)
    pts = [at(s) + UP * (lift * (1.0 - s)) for s in ss]
    add_tube(bm, pts, radii, 8, mats, L, V, st["tone"], P_STEM, zones=zones, tip=at(1.0),
             alongs=list(ss), phase=st["ph"] + 0.37 * idx)

    # the seed head, threaded on the stem between hb and ht
    sc = 0.5 * (hb + ht)
    centre = at(sc)
    axis = tangent(sc)
    if slip:
        centre = centre + Vector((1.0, 0.0, 0.0)) * SLIP_HEADS
    add_head(bm, L, V, centre, axis, st["head_len"], st["head_r"], st["ph"], st["tone"])


def add_head(bm, L, V, centre, axis, length, radius, ph, tone):
    e1, e2 = perp_basis(axis)
    NR, NS = 14, 16
    rings = []
    for k in range(1, NR):
        u = k / NR
        x = 2.0 * u - 1.0
        r = radius * (1.0 - abs(x) ** 2.6) ** (1.0 / 2.6)
        ring = []
        for j in range(NS):
            a = TAU * j / NS
            rr = r * (1.0 + 0.035 * math.sin(5.0 * a + ph) * math.sin(3.0 * math.pi * u + ph))
            v = bm.verts.new(centre + axis * (0.5 * length * x) + (e1 * math.cos(a) + e2 * math.sin(a)) * rr)
            v[V["along"]] = u
            ring.append(v)
        rings.append(ring)
    bot = bm.verts.new(centre - axis * (0.5 * length))
    top = bm.verts.new(centre + axis * (0.5 * length))
    top[V["along"]] = 1.0
    for j in range(NS):
        m = (j + 1) % NS
        new_face(bm, (rings[0][m], rings[0][j], bot), SEED_IDX, L, tone, 0.0, P_HEAD)
        new_face(bm, (rings[-1][j], rings[-1][m], top), SEED_IDX, L, tone, 0.0, P_HEAD)
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(NS):
            m = (j + 1) % NS
            new_face(bm, (r0[j], r0[m], r1[m], r1[j]), SEED_IDX, L, tone, 0.0, P_HEAD)


def add_tuft(bm, L, V, tf, soil_tree, lift):
    for k, bl in enumerate(tf["blades"][:tf["n"]]):
        ox, oy = bl["off"]
        b, _n = soil_hit(soil_tree, tf["x"] + ox * tf["spread"], tf["y"] + oy * tf["spread"])
        b = b - UP * (0.020 + 0.00053 * k) + UP * lift
        h = tf["h"] * bl["h"] + 0.02
        hd = Vector((math.cos(bl["yaw"]), math.sin(bl["yaw"]), 0.0))
        segs = 4
        pts = []
        # every blade leaves the ground already leaning its own way, so no
        # two root caps lie flat on one plane
        for i in range(segs + 1):
            t = i / segs
            pts.append(b + UP * (h * (t - 0.40 * bl["lean"] * t * t))
                       + hd * (h * bl["lean"] * (0.12 * t + t * t)))
        W = 0.0135 * bl["w"]

        def width(s, W=W):
            return W * (1.0 - 0.75 * s ** 1.3)

        def thick(s):
            return 0.0011 * (1.0 - 0.6 * s)

        add_strap(bm, pts, width, thick, hd, bl["tw"], REED_IDX, L, V,
                  0.6 * tf["tone"] + 0.4 * bl["tone"], P_RUSH, section=3,
                  roll=0.18 * math.sin(3.7 * k + bl["yaw"]))


def add_pad(bm, L, V, pad, sink):
    cx, cy, R = pad["x"], pad["y"], pad["r"]
    ph = pad["ph"]
    level = WATER_LEVEL - sink
    span = TAU - PAD_NOTCH
    phi0 = pad["notch"] + 0.5 * PAD_NOTCH

    def rim(phi):
        return R * (1.0 + 0.035 * math.sin(3.0 * phi + ph) + 0.018 * math.sin(7.0 * phi + 2.0 * ph))

    def top_z(rn, phi):
        return (level + PAD_TOP + PAD_UPTURN * rn ** 5
                + 0.0012 * rn * rn * math.sin(4.0 * phi + ph))

    def bot_z(rn, phi):
        return top_z(rn, phi) - PAD_T * (1.0 - 0.55 * rn * rn)

    tops, bots = [], []
    for k in range(1, PAD_K + 1):
        rn = k / PAD_K
        tr, br = [], []
        for j in range(PAD_NA + 1):
            f = j / PAD_NA
            phi = phi0 + span * f
            r = rn * rim(phi)
            x, y = cx + r * math.cos(phi), cy + r * math.sin(phi)
            vt = bm.verts.new((x, y, top_z(rn, phi)))
            vb = bm.verts.new((x, y, bot_z(rn, phi)))
            for v in (vt, vb):
                v[V["pad_ang"]] = span * f
                v[V["pad_r"]] = rn
            tr.append(vt)
            br.append(vb)
        tops.append(tr)
        bots.append(br)
    ct = bm.verts.new((cx, cy, top_z(0.0, 0.0)))
    cb = bm.verts.new((cx, cy, bot_z(0.0, 0.0)))
    for v in (ct, cb):
        v[V["pad_ang"]] = 0.5 * span
    tone = pad["tone"]
    for rings, centre, zone, flip in ((tops, ct, 0.0, False), (bots, cb, 2.0, True)):
        for j in range(PAD_NA):
            tri = (centre, rings[0][j], rings[0][j + 1])
            new_face(bm, tri[::-1] if flip else tri, PAD_IDX, L, tone, zone, P_PAD)
        for r0, r1 in zip(rings, rings[1:]):
            for j in range(PAD_NA):
                quad = (r0[j], r1[j], r1[j + 1], r0[j + 1])
                new_face(bm, quad[::-1] if flip else quad, PAD_IDX, L, tone, zone, P_PAD)
    K = PAD_K

    def loop(rings, centre):
        return ([centre] + [rings[k][0] for k in range(K)] + [rings[K - 1][j] for j in range(1, PAD_NA + 1)]
                + [rings[k][PAD_NA] for k in range(K - 2, -1, -1)])

    lt, lb = loop(tops, ct), loop(bots, cb)
    m = len(lt)
    for i in range(m):
        q = (i + 1) % m
        new_face(bm, (lt[i], lb[i], lb[q], lt[q]), PAD_IDX, L, tone, 1.0, P_PAD)


def petal(bm, L, V, root, rd, tilt, length, width, cup, curl, tone, zone, twist=0.0, asym=1.0):
    """One petal or sepal: a thin cupped lens from ``root`` out along ``rd``,
    raised by ``tilt`` radians."""
    out = (rd * math.cos(tilt) + UP * math.sin(tilt)).normalized()
    sd = UP.cross(rd).normalized()
    nrm = sd.cross(out).normalized()
    if twist:
        nrm = (nrm * math.cos(twist) + out.cross(nrm) * math.sin(twist)).normalized()
        sd = nrm.cross(out).normalized()
    ring = []
    for f in (0.0, 0.10, 0.28, 0.50, 0.72, 0.88, 1.0):
        w = width * 0.5 * math.sin(math.pi * min(1.0, f ** 0.75)) if 0.0 < f < 1.0 else 0.0
        ring.append((f, w))
    # root, up the right edge to the tip, back down the left
    right = list(ring)
    # the two halves differ a little: a mirror-symmetric petal turned about
    # the flower's axis lands faces on the planes of its neighbours
    left = [(f, -w * asym) for f, w in reversed(ring[1:-1])]
    pts = []
    alongs = []
    for f, w in right + left:
        lift = cup * min(1.0, abs(w) / (0.5 * width)) ** 2 * 0.5 * width + curl * length * f * f
        pts.append(root + out * (f * length) + sd * w + nrm * lift)
        alongs.append(f)
    mid = root + out * (0.45 * length) + nrm * (curl * length * 0.2)
    add_lens(bm, pts, mid + nrm * 0.0009, mid - nrm * 0.0009, FLOWER_IDX, L, tone, zone, P_FLOWER,
             V, alongs, 0.45)


def add_lily(bm, L, V, fl):
    centre = Vector((fl["x"], fl["y"], WATER_LEVEL))
    spin = fl["spin"]
    tone = fl["tone"]
    # (count, length, width, tilt, height, cup, curl, zone): sepals, then
    # outer, middle and inner petals
    rings = ((4, 0.052, 0.020, 0.17, -0.0008, 0.25, 0.05, 1.0),
             (8, 0.058, 0.021, 0.30, 0.0010, 0.35, 0.10, 0.0),
             (8, 0.050, 0.019, 0.62, 0.0040, 0.40, 0.10, 0.0),
             (6, 0.040, 0.016, 0.98, 0.0070, 0.45, 0.06, 0.0))
    for ri, (cnt, ln, wd, tilt, dz, cup, curl, zone) in enumerate(rings):
        for k in range(cnt):
            a = spin + TAU * (k + 0.5 * ri) / cnt
            rd = Vector((math.cos(a), math.sin(a), 0.0))
            # every petal tilts and twists by its own step, and roots at its
            # own radius and height: planes through one axis would meet
            t = tilt + 0.035 * ((k * 3 + ri) % 5 - 2)
            tw = 0.06 * ((k + ri) % 3 - 1)
            root = centre + rd * (0.0028 + 0.00047 * k) + UP * (dz + 0.00061 * k + 0.00023 * ri)
            asym = 1.0 + 0.035 * (((k * 7 + ri * 3) % 5) - 2)
            petal(bm, L, V, root, rd, t, FLOWER_SCALE * ln * (1.0 + 0.04 * ((k + ri) % 3 - 1)),
                  FLOWER_SCALE * wd, cup, curl, tone, zone, tw, asym)
    # the stamen crown: a short yellow drum with a domed top
    prof = tuple((FLOWER_SCALE * r, FLOWER_SCALE * z) for r, z in
                 ((0.0045, 0.000), (0.0110, 0.003), (0.0122, 0.009), (0.0100, 0.0135), (0.0055, 0.0150)))
    NS = 16
    base = centre + UP * 0.0005
    rings_v = []
    for r, z in prof:
        rings_v.append([bm.verts.new(base + Vector((r * math.cos(TAU * j / NS), r * math.sin(TAU * j / NS), z)))
                        for j in range(NS)])
    bot = bm.verts.new(base + UP * (-0.001))
    top = bm.verts.new(base + UP * (FLOWER_SCALE * 0.0138))
    for j in range(NS):
        m = (j + 1) % NS
        new_face(bm, (rings_v[0][m], rings_v[0][j], bot), FLOWER_IDX, L, tone, 3.0, P_FLOWER)
        new_face(bm, (rings_v[-1][j], rings_v[-1][m], top), FLOWER_IDX, L, tone, 3.0, P_FLOWER)
    for r0, r1 in zip(rings_v, rings_v[1:]):
        for j in range(NS):
            m = (j + 1) % NS
            new_face(bm, (r0[j], r0[m], r1[m], r1[j]), FLOWER_IDX, L, tone, 3.0, P_FLOWER)


def leaf_outline(length, wid, cup):
    pts = []
    n = 10
    for k in range(n):
        a = TAU * k / n
        x = 0.5 * length * math.cos(a)
        y = 0.5 * length * wid * math.sin(a) * (1.0 - 0.25 * math.cos(a))
        # pointed at the tip (+x), rounded at the stalk
        if math.cos(a) > 0.0:
            y *= 1.0 - 0.45 * math.cos(a) ** 3
        z = cup * 0.5 * length * wid * (math.sin(a) ** 2) * 0.5
        pts.append(Vector((x, y, z)))
    return pts


def add_leaf_litter(bm, L, V, lf, tree, lift, on_water=False):
    local = leaf_outline(lf["len"], lf["wid"], lf["cup"])
    yaw = rotz(math.degrees(lf["yaw"]))
    if on_water:
        base = Vector((lf["x"], lf["y"], WATER_LEVEL))
        nrm = UP
    else:
        base, nrm = soil_hit(tree, lf["x"], lf["y"])
    q = UP.rotation_difference(nrm).to_matrix()
    if not on_water:
        # tipped a few degrees off the ground, never parallel to the face under it
        a = 3.0 * lf["yaw"]
        q = q @ Matrix.Rotation(0.07 + 0.03 * math.sin(5.0 * lf["yaw"]), 3,
                                Vector((math.cos(a), math.sin(a), 0.0)))
    pts = [base + q @ (yaw @ p) for p in local]
    mid = base + q @ Vector((0.0, 0.0, 0.0008))
    top = mid + nrm * 0.0012
    bot = mid - nrm * 0.0012
    allp = pts + [top, bot]
    if on_water:
        dz = (WATER_LEVEL - 0.0010) - min(p.z for p in allp)
    else:
        gaps = [p.z - soil_hit(tree, p.x, p.y)[0].z for p in allp]
        dz = -0.0015 - min(gaps) + lift
    shift = UP * dz
    add_lens(bm, [p + shift for p in pts], top + shift, bot + shift, LITTER_IDX, L, lf["tone"], 0.0,
             P_LITTER)


def add_pebble(bm, L, V, pb, tree, lift):
    dirs, quads = cube_sphere(3)
    yaw = rotz(math.degrees(pb["yaw"]))
    tilt = Matrix.Rotation(pb["tilt"][0], 3, "X") @ Matrix.Rotation(pb["tilt"][1], 3, "Y")
    r = pb["r"]
    ax = Vector((r * pb["long"], r, r * pb["flat"]))
    pts = []
    for d in dirs:
        q = Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z))
        q *= 1.0 + 0.10 * sum(a * math.sin(w.dot(d) * 3.0 + ph) for w, ph, a in pb["waves"]) / 2.3
        pts.append(yaw @ (tilt @ q) + Vector((pb["x"], pb["y"], 0.0)))
    gaps = [p.z - soil_hit(tree, p.x, p.y)[0].z for p in pts]
    dz = max(-0.6 * ax.z - min(gaps), ax.z - max(gaps))
    dz = min(dz, -0.003 - min(gaps)) + lift
    verts = [bm.verts.new(p + Vector((0.0, 0.0, dz))) for p in pts]
    for v in verts:
        v[V["wet"]] = 1.0 - smoothstep(v.co.z - WATER_LEVEL, 0.0, 0.03)
    for q in quads:
        new_face(bm, [verts[i] for i in q], STONE_IDX, L, pb["tone"], 0.0, P_PEBBLE)


def add_stone(bm, L, V, st, tree, n):
    dirs, quads = cube_sphere(n)
    yaw = rotz(math.degrees(st["yaw"]))
    r = st["r"]
    ax = Vector((r * st["long"], r, r * st["flat"]))
    pts = []
    for d in dirs:
        q = Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z))
        q *= 1.0 + sum(a * math.sin(3.0 * w.dot(d) + ph) for w, ph, a in st["waves"])
        # flatter underneath, domed on top: a water-worn stone
        if q.z < 0.0:
            q.z *= 0.75
        pts.append(yaw @ q + Vector((st["x"], st["y"], 0.0)))
    gaps = [p.z - soil_hit(tree, p.x, p.y)[0].z for p in pts]
    # seated: the deepest vertex a quarter of the stone's height under the mud
    dz = -max(0.010, 0.25 * 1.75 * ax.z) - min(gaps)
    verts = [bm.verts.new(p + Vector((0.0, 0.0, dz))) for p in pts]
    for v in verts:
        v[V["wet"]] = 1.0 - smoothstep(v.co.z - WATER_LEVEL, 0.0, 0.035)
    for q in quads:
        new_face(bm, [verts[i] for i in q], STONE_IDX, L, st["tone"], 0.0, P_STONE)


def add_branch(bm, L, V, br):
    pts = br["pts"]
    n = len(pts)
    radii = [br["r0"] + (br["r1"] - br["r0"]) * (k / (n - 1)) ** 0.8 for k in range(n)]
    # a smoother path: two stations per span
    fine, fr = [], []
    for k in range(n - 1):
        for s in (0.0, 0.5):
            fine.append(pts[k].lerp(pts[k + 1], s))
            fr.append(radii[k] + (radii[k + 1] - radii[k]) * s)
    # the thin end snapped off: a short taper to a splintered point
    d = (pts[-1] - pts[-2]).normalized()
    fine.append(pts[-1])
    fr.append(radii[-1])
    fine.append(pts[-1] + d * (1.2 * radii[-1]))
    fr.append(0.55 * radii[-1])
    add_tube(bm, fine, fr, 10, [WOOD_IDX] * len(fine), L, V, br["tone"], P_BRANCH,
             zones=[0.0] * (len(fine) - 1) + [1.0], tip=pts[-1] + d * (2.6 * radii[-1]) + UP * 0.004)
    for t, az, ln in br["twigs"]:
        k = t * (n - 1)
        i = min(int(k), n - 2)
        f = k - i
        p = pts[i].lerp(pts[i + 1], f)
        d = (pts[i + 1] - pts[i]).normalized()
        side = UP.cross(d).normalized()
        r = radii[i] + (radii[i + 1] - radii[i]) * f
        tw = (d * 0.55 + side * az + UP * 0.35).normalized()
        start = p - tw * (0.5 * r)
        tp = [start + tw * (ln * s) + UP * (-0.03 * ln * s * s) for s in (0.0, 0.35, 0.7, 0.92)]
        tipp = start + tw * ln + UP * (-0.03 * ln)
        add_tube(bm, tp, [0.55 * r, 0.45 * r, 0.36 * r, 0.26 * r], 7, [WOOD_IDX] * 4, L, V,
                 br["tone"], P_BRANCH, zones=[0.0, 0.0, 0.0, 1.0], tip=tipp)


def set_wet(bm, V, parts_layer, part):
    for f in bm.faces:
        if f[parts_layer] == part:
            for v in f.verts:
                v[V["wet"]] = 1.0 - smoothstep(v.co.z - WATER_LEVEL, 0.0, 0.03)


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

def build_pond_mesh(name, plan, lay, detail="low", float_reeds=False, sink_pad=False,
                    flat_water=False, slip_heads=False, short_water=False, float_cover=False):
    bm = bmesh.new()
    try:
        L = {"tone": bm.faces.layers.float.new("Tone"),
             "zone": bm.faces.layers.float.new("Zone"),
             "part": bm.faces.layers.int.new("Part")}
        V = {"wet": bm.verts.layers.float.new("Wet"),
             "turf": bm.verts.layers.float.new("Turf"),
             "skirt": bm.verts.layers.float.new("Skirt"),
             "depth": bm.verts.layers.float.new("Depth"),
             "along": bm.verts.layers.float.new("Along"),
             "pad_ang": bm.verts.layers.float.new("PadAng"),
             "pad_r": bm.verts.layers.float.new("PadR")}

        add_soil(bm, L, V, DISC_N[detail])
        bm.faces.ensure_lookup_table()
        bm.normal_update()   # FromBMesh reads the stored face normals
        soil_tree = BVHTree.FromBMesh(bm)

        add_water(bm, L, V, lay, WATER_N[detail], SHORT_MARGIN if short_water else WATER_MARGIN,
                  flat_water)
        lift = FLOAT_REEDS if float_reeds else 0.0
        for k, lf in enumerate(lay.leaves):
            add_leaf(bm, L, V, lf, soil_tree, lift, k)
        for k, st in enumerate(lay.stems):
            add_stem(bm, L, V, st, soil_tree, lift, slip_heads, k)
        cover = FLOAT_COVER if float_cover else 0.0
        for tf in lay.tufts + lay.turf:
            add_tuft(bm, L, V, tf, soil_tree, cover)
        for k, pad in enumerate(lay.pads):
            add_pad(bm, L, V, pad, SINK_PAD if (sink_pad and k == 0) else 0.0)
        for fl in lay.flowers:
            add_lily(bm, L, V, fl)
        for fl in lay.floaters:
            add_leaf_litter(bm, L, V, fl, soil_tree, 0.0, on_water=True)
        for st in lay.stones:
            add_stone(bm, L, V, st, soil_tree, 5 if detail == "low" else 8)
        add_branch(bm, L, V, lay.branch)
        for pb in lay.pebbles:
            add_pebble(bm, L, V, pb, soil_tree, cover)
        for lf in lay.litter:
            add_leaf_litter(bm, L, V, lf, soil_tree, cover)
        set_wet(bm, V, L["part"], P_BRANCH)

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
        # sharper than 60 degrees is a hard edge.
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
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def build_collider_source(name):
    """The soil disc alone, coarse: the water is a trigger volume, and
    players walk through reeds."""
    bm = bmesh.new()
    try:
        for j in range(32):
            th = TAU * j / 32
            X, Y = math.cos(th), math.sin(th)
            wob = disc_wobble(th)
            for f in (1.0, 0.78):
                x, y = DISC_A[0] * X * wob * f, DISC_A[1] * Y * wob * f
                bm.verts.new((x, y, 0.0 if f == 1.0 else soil_height(x, y)))
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


def water_material():
    mat, nt, bsdf, coord = surface("PondWater")
    depth = remap(nt, attr(nt, "Depth"), 0.0, 0.11, 0.0, 1.0)
    # shallow water over the mud reads brown-olive, the deep middle near black
    col = ramp(nt, depth, ((0.00, (0.100, 0.082, 0.048)), (0.18, (0.060, 0.060, 0.036)),
                           (0.45, (0.026, 0.036, 0.028)), (1.00, (0.010, 0.017, 0.016))))
    # a faint duckweed-and-pollen film drifted into the shallows
    film = noise(nt, coord, 7.0, 4.0, 0.55)
    edge = remap(nt, depth, 0.10, 0.35, 1.0, 0.0)
    col = mix_color(nt, col, (0.070, 0.085, 0.035),
                    math_node(nt, "MULTIPLY", remap(nt, film, 0.52, 0.70, 0.0, 0.7), edge))
    nt.links.new(col, bsdf.inputs["Base Color"])
    rough = remap(nt, film, 0.52, 0.70, 0.08, 0.16)
    nt.links.new(rough, bsdf.inputs["Roughness"])
    bsdf.inputs["IOR"].default_value = 1.33
    # a pond is not a mirror: under a bright sky the sheet should not blow out
    bsdf.inputs["Specular IOR Level"].default_value = 0.32
    ruffle = noise(nt, mapping(nt, coord, scale=(1.0, 2.5, 1.0)), 38.0, 2.0, 0.5)
    bump(nt, bsdf, ruffle, 0.06, 0.002)
    return mat


def soil_material():
    mat, nt, bsdf, coord = surface("BankMud")
    wet = attr(nt, "Wet")
    clods = noise(nt, coord, 6.0, 6.0, 0.62)
    crumbs = noise(nt, coord, 70.0, 3.0, 0.6)
    dry = ramp(nt, clods, ((0.30, (0.046, 0.035, 0.024)), (0.55, (0.078, 0.060, 0.041)),
                           (0.80, (0.108, 0.086, 0.060))))
    dry = mix_color(nt, dry, (0.024, 0.018, 0.013), remap(nt, crumbs, 0.35, 0.55, 0.55, 0.0))
    # turf on the bank's top, thinning to bare earth on the disc's skirt
    film = noise(nt, coord, 2.6, 5.0, 0.6)
    turf = math_node(nt, "MULTIPLY", remap(nt, film, 0.34, 0.58, 0.0, 0.90), attr(nt, "Turf"))
    dry = mix_color(nt, dry, (0.050, 0.068, 0.024), turf)
    # wet mud at the waterline: darker, a little grey-green, glossy
    mud = ramp(nt, clods, ((0.3, (0.022, 0.019, 0.014)), (0.8, (0.040, 0.036, 0.024))))
    col = mix_color(nt, dry, mud, wet)
    # the disc's cut edge shows its horizons: dark humus under the turf,
    # brown subsoil, pale clay with stones at the foot
    wob = noise(nt, coord, 5.0, 3.0, 0.5)
    hz = math_node(nt, "ADD", remap(nt, height(nt, coord), 0.0, LAND_Z + BACK_RISE * 0.5, 0.0, 1.0),
                   remap(nt, wob, 0.0, 1.0, -0.08, 0.08))
    prof = ramp(nt, hz, ((0.00, (0.092, 0.078, 0.060)), (0.30, (0.110, 0.084, 0.058)),
                         (0.58, (0.078, 0.057, 0.038)), (0.74, (0.036, 0.027, 0.019)),
                         (1.00, (0.030, 0.024, 0.017))))
    fibres = noise(nt, mapping(nt, coord, scale=(30.0, 30.0, 5.0)), 4.0, 3.0, 0.5)
    prof = mix_color(nt, prof, (0.13, 0.10, 0.07), math_node(nt, "MULTIPLY", remap(nt, fibres, 0.62, 0.70, 0.0, 0.6),
                                                               remap(nt, hz, 0.55, 0.80, 0.0, 1.0)))
    stones = voronoi_color(nt, coord, 24.0)
    prof = mix_color(nt, prof, (0.16, 0.15, 0.13), math_node(nt, "MULTIPLY", remap(nt, stones[2], 0.16, 0.10, 0.0, 0.9),
                                                               remap(nt, hz, 0.45, 0.20, 0.0, 1.0)))
    col = mix_color(nt, col, prof, attr(nt, "Skirt"))
    grit = voronoi_color(nt, coord, 160.0)[0]
    col = mix_color(nt, col, (0.12, 0.11, 0.09), remap(nt, grit, 0.94, 0.97, 0.0, 0.25))
    nt.links.new(col, bsdf.inputs["Base Color"])
    rough = remap(nt, wet, 0.0, 1.0, 0.95, 0.32)
    nt.links.new(rough, bsdf.inputs["Roughness"])
    bump(nt, bsdf, math_node(nt, "ADD", clods, math_node(nt, "MULTIPLY", crumbs, 0.6)), 0.55, 0.01)
    return mat


def reed_material():
    mat, nt, bsdf, coord = surface("ReedLeaf")
    tone = attr(nt, "Tone")
    along = attr(nt, "Along")
    col = ramp(nt, tone, ((0.0, (0.085, 0.125, 0.040)), (0.45, (0.120, 0.160, 0.055)),
                          (0.80, (0.165, 0.190, 0.070)), (1.0, (0.250, 0.230, 0.110))))
    # parallel veins along each leaf
    veins = noise(nt, mapping(nt, coord, scale=(60.0, 60.0, 2.0)), 3.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.055, 0.080, 0.028), remap(nt, veins, 0.45, 0.65, 0.0, 0.45))
    # pale sheathing bases, withered straw tips
    col = mix_color(nt, col, (0.30, 0.29, 0.17), remap(nt, along, 0.12, 0.0, 0.0, 0.7))
    tips = math_node(nt, "MULTIPLY", remap(nt, along, 0.72, 1.0, 0.0, 1.0),
                     remap(nt, tone, 0.2, 0.9, 0.35, 0.85))
    col = mix_color(nt, col, (0.36, 0.29, 0.14), tips)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.52
    bump(nt, bsdf, veins, 0.15, 0.002)
    return mat


def seed_material():
    mat, nt, bsdf, coord = surface("SeedHead")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    col = ramp(nt, tone, ((0.0, (0.105, 0.052, 0.024)), (0.5, (0.140, 0.070, 0.030)),
                          (1.0, (0.170, 0.092, 0.042))))
    fuzz = noise(nt, coord, 260.0, 3.0, 0.7)
    col = mix_color(nt, col, (0.060, 0.030, 0.014), remap(nt, fuzz, 0.35, 0.65, 0.55, 0.0))
    # paler felt where a head has started to split
    blot = noise(nt, coord, 22.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.30, 0.24, 0.17), remap(nt, blot, 0.66, 0.74, 0.0, 0.55))
    # the bare spike above the head
    col = mix_color(nt, col, (0.24, 0.17, 0.090), remap(nt, zone, 1.0, 2.0, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    bump(nt, bsdf, fuzz, 0.35, 0.0015)
    return mat


def pad_material():
    mat, nt, bsdf, coord = surface("LilyPad")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    ang = attr(nt, "PadAng")
    pr = attr(nt, "PadR")
    col = ramp(nt, tone, ((0.0, (0.026, 0.056, 0.014)), (0.6, (0.036, 0.070, 0.018)),
                          (1.0, (0.060, 0.074, 0.020))))
    # radial veins from the stalk
    v = math_node(nt, "FRACT", math_node(nt, "MULTIPLY", ang, 22.0 / TAU), 0.0)
    v = math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", v, 0.5), 0.0)
    vein = remap(nt, v, 0.44, 0.50, 0.0, 1.0)
    col = mix_color(nt, col, (0.058, 0.090, 0.028), math_node(nt, "MULTIPLY", vein,
                                                             remap(nt, pr, 0.1, 0.4, 0.0, 0.7)))
    blotch = noise(nt, coord, 30.0, 3.0, 0.55)
    col = mix_color(nt, col, (0.12, 0.070, 0.035), remap(nt, blotch, 0.60, 0.72, 0.0, 0.45))
    # a bronze rim, and a maroon underside
    col = mix_color(nt, col, (0.14, 0.070, 0.035), remap(nt, pr, 0.86, 1.0, 0.0, 0.75))
    col = mix_color(nt, col, (0.13, 0.040, 0.050), remap(nt, zone, 0.5, 1.5, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, zone, 0.0, 1.5, 0.22, 0.6), bsdf.inputs["Roughness"])
    bump(nt, bsdf, math_node(nt, "ADD", vein, math_node(nt, "MULTIPLY", blotch, 0.3)), 0.2, 0.001)
    return mat


def flower_material():
    mat, nt, bsdf, coord = surface("LilyFlower")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    along = attr(nt, "Along")
    white = ramp(nt, tone, ((0.0, (0.80, 0.78, 0.74)), (1.0, (0.82, 0.76, 0.74))))
    pink = ramp(nt, tone, ((0.0, (0.66, 0.30, 0.40)), (1.0, (0.72, 0.36, 0.48))))
    col = mix_color(nt, white, pink, remap(nt, along, 0.45, 1.0, 0.0, 0.85))
    col = mix_color(nt, col, (0.93, 0.86, 0.60), remap(nt, along, 0.25, 0.0, 0.0, 0.5))
    # sepals: green outside, flushed pink
    sep = mix_color(nt, (0.10, 0.15, 0.06), (0.45, 0.22, 0.26), remap(nt, along, 0.3, 1.0, 0.0, 0.6))
    col = mix_color(nt, col, sep, remap(nt, zone, 0.5, 1.0, 0.0, 1.0))
    # the stamen crown
    col = mix_color(nt, col, (0.78, 0.52, 0.05), remap(nt, zone, 2.5, 3.0, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    bsdf.inputs["Subsurface Weight"].default_value = 0.15
    return mat


def stone_material():
    mat, nt, bsdf, coord = surface("WetStone")
    tone = attr(nt, "Tone")
    wet = attr(nt, "Wet")
    col = ramp(nt, tone, ((0.0, (0.070, 0.068, 0.064)), (0.35, (0.120, 0.108, 0.092)),
                          (0.65, (0.150, 0.132, 0.105)), (1.0, (0.098, 0.096, 0.090))))
    mottle = noise(nt, coord, 9.0, 5.0, 0.6)
    col = mix_color(nt, col, (0.050, 0.048, 0.045), remap(nt, mottle, 0.38, 0.68, 0.65, 0.0))
    veins = noise(nt, mapping(nt, coord, scale=(1.0, 1.0, 5.0)), 6.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.26, 0.24, 0.21), remap(nt, veins, 0.60, 0.66, 0.0, 0.5))
    speck = voronoi_color(nt, coord, 140.0)[0]
    col = mix_color(nt, col, (0.30, 0.29, 0.26), remap(nt, speck, 0.93, 0.97, 0.0, 0.22))
    # a green algae line at the water's edge, the wet part dark
    band = math_node(nt, "MULTIPLY", remap(nt, wet, 0.25, 0.55, 0.0, 1.0), remap(nt, wet, 0.75, 0.95, 1.0, 0.3))
    col = mix_color(nt, col, (0.050, 0.070, 0.025), math_node(nt, "MULTIPLY", band, 0.7))
    col = mix_color(nt, col, (0.035, 0.034, 0.030), remap(nt, wet, 0.3, 1.0, 0.0, 0.7))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, wet, 0.0, 0.8, 0.68, 0.18), bsdf.inputs["Roughness"])
    bump(nt, bsdf, mottle, 0.25, 0.004)
    return mat


def wood_material(branch_az):
    mat, nt, bsdf, coord = surface("Driftwood")
    tone = attr(nt, "Tone")
    wet = attr(nt, "Wet")
    zone = attr(nt, "Zone")
    # bark furrows along the branch: the texture space turned onto its bearing
    g = mapping(nt, coord, scale=(3.0, 70.0, 70.0), rot=(0.0, 0.0, -math.radians(branch_az)))
    grain = noise(nt, g, 1.5, 6.0, 0.6)
    col = ramp(nt, grain, ((0.30, (0.050, 0.042, 0.033)), (0.50, (0.105, 0.088, 0.066)),
                           (0.72, (0.160, 0.138, 0.108))))
    col = mix_color(nt, col, (0.12, 0.08, 0.05), remap(nt, tone, 0.0, 1.0, 0.0, 0.3))
    cracks = noise(nt, mapping(nt, coord, scale=(2.0, 25.0, 25.0), rot=(0.0, 0.0, -math.radians(branch_az))),
                   3.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.03, 0.025, 0.02), remap(nt, cracks, 0.60, 0.70, 0.0, 0.8))
    # grey lichen flecks, and pale bare wood where the ends broke
    fleck = noise(nt, coord, 45.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.20, 0.21, 0.18), remap(nt, fleck, 0.66, 0.74, 0.0, 0.6))
    col = mix_color(nt, col, (0.26, 0.20, 0.13), remap(nt, zone, 0.5, 1.0, 0.0, 1.0))
    col = mix_color(nt, col, (0.045, 0.038, 0.028), remap(nt, wet, 0.2, 1.0, 0.0, 0.8))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, wet, 0.0, 1.0, 0.82, 0.30), bsdf.inputs["Roughness"])
    bump(nt, bsdf, math_node(nt, "ADD", grain, cracks), 0.4, 0.003)
    return mat


def litter_material():
    mat, nt, bsdf, coord = surface("LeafLitter")
    tone = attr(nt, "Tone")
    col = ramp(nt, tone, ((0.0, (0.12, 0.070, 0.035)), (0.30, (0.19, 0.105, 0.045)),
                          (0.55, (0.25, 0.18, 0.07)), (0.80, (0.16, 0.12, 0.06)),
                          (1.0, (0.10, 0.075, 0.045))))
    rot = noise(nt, coord, 40.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.07, 0.045, 0.025), remap(nt, rot, 0.55, 0.72, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.78
    bump(nt, bsdf, rot, 0.2, 0.001)
    return mat


def pond_materials():
    """Nine slots, in index order: shared by the check and the render."""
    return (water_material(), soil_material(), reed_material(), seed_material(), pad_material(),
            flower_material(), stone_material(), wood_material(BRANCH_AZ), litter_material())


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
        self.tree = BVHTree.FromPolygons(
            [tuple(p) for p in pts], [[remap_[v] for v in p.vertices] for p in polys])
        self.polys = polys
        self.centre = sum(pts, Vector()) / len(pts)


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
    for key, pid in (("soil", P_SOIL), ("water", P_WATER), ("leaves", P_LEAF), ("stems", P_STEM),
                     ("heads", P_HEAD), ("pads", P_PAD)):
        out[key] = [s for s in parts if s.part == pid]
    return out


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
    return None if loc is None else loc.z


def root_audit(cls):
    """Each cattail leaf and stem: its lowest vertex under the soil straight
    above it (a ray down onto the soil shell alone)."""
    soil = cls["soil"][0]
    depths = []
    for s in cls["leaves"] + cls["stems"]:
        low = min(s.pts, key=lambda p: p.z)
        g = ray_down(soil.tree, low.x, low.y)
        depths.append(-9.0 if g is None else g - low.z)
    return depths


def plane_fit(pts):
    c = sum(pts, Vector()) / len(pts)
    sxx = sxy = syy = sxz = syz = 0.0
    for p in pts:
        d = p - c
        sxx += d.x * d.x
        sxy += d.x * d.y
        syy += d.y * d.y
        sxz += d.x * d.z
        syz += d.y * d.z
    det = sxx * syy - sxy * sxy
    a = (sxz * syy - syz * sxy) / det
    b = (syz * sxx - sxz * sxy) / det
    return c, math.degrees(math.atan(math.hypot(a, b)))


def pad_audit(cls):
    """Each pad: its mean height over the water surface under its centroid,
    how far its lowest vertex draws under that surface, and the tilt of the
    plane fitted through it."""
    water = cls["water"][0]
    out = []
    for s in cls["pads"]:
        c, tilt = plane_fit(s.pts)
        w = ray_down(water.tree, c.x, c.y)
        if w is None:
            out.append((-9.0, -9.0, 90.0))
            continue
        low = min(p.z for p in s.pts)
        out.append((c.z - w, w - low, tilt))
    return out


def water_top(water):
    top = [p for p in water.polys if p.normal.z > 0.3]
    count = {}
    for p in top:
        for e in p.edge_keys:
            count[e] = count.get(e, 0) + 1
    rim = [e for e, n in count.items() if n == 1]
    verts = sorted({v for p in top for v in p.vertices})
    return top, verts, rim


def level_audit(me, cls):
    water = cls["water"][0]
    _top, verts, _rim = water_top(water)
    zs = sorted(me.vertices[i].co.z for i in verts)
    level = zs[len(zs) // 2]
    amp = max(abs(z - level) for z in zs)
    return level, amp, len(verts)


def enclose_audit(me, cls):
    """The bank over every rim vertex and every rim-edge midpoint of the
    water's top (a ray down onto the soil shell alone)."""
    water = cls["water"][0]
    soil = cls["soil"][0]
    _top, _verts, rim = water_top(water)
    pts = []
    for a, b in rim:
        pa, pb = me.vertices[a].co, me.vertices[b].co
        pts.append(pa)
        pts.append((pa + pb) * 0.5)
    worst = 9.0
    for p in pts:
        g = ray_down(soil.tree, p.x, p.y)
        worst = min(worst, -9.0 if g is None else g - p.z)
    return worst, len(rim)


def principal_axis(pts):
    c = sum(pts, Vector()) / len(pts)
    C = Matrix(((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))
    for p in pts:
        d = p - c
        for i in range(3):
            for j in range(3):
                C[i][j] += d[i] * d[j]
    v = Vector((0.1, 0.2, 1.0)).normalized()
    for _ in range(80):
        v = (C @ v).normalized()
    return c, v


def head_audit(cls):
    """Each seed head: its axis from its own vertices, the stem whose
    vertices inside the head's middle run closest to that axis, their
    centroid's distance off it, and how far the stem runs on above it."""
    heads = cls["heads"]
    stems = cls["stems"]
    out = []
    used = set()
    for h in heads:
        c, ax = principal_axis(h.pts)
        half = max(abs((p - c).dot(ax)) for p in h.pts)
        best = None
        for s in stems:
            inside = [p for p in s.pts if abs((p - c).dot(ax)) < 0.6 * half]
            if not inside:
                continue
            m = sum(inside, Vector()) / len(inside)
            d = m - c
            off = (d - ax * d.dot(ax)).length
            above = max((p - c).dot(ax) for p in s.pts) - half
            if best is None or off < best[0]:
                best = (off, above, s.idx)
        if best is None:
            out.append((9.0, -9.0))
            continue
        used.add(best[2])
        out.append((best[0], best[1]))
    return out, len(used)


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
    """Every shell joined to the soil through BVH overlaps (floating parts
    through the water): how many are not."""
    soil = cls["soil"][0]
    others = [s for s in cls["all"] if s is not soil]
    parts = [soil] + others
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
    img = bpy.data.images.new("PondNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = SOIL_IDX
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


def check(skip_decimate, lift_z=False, stray_vert=False, float_reeds=False, sink_pad=False,
          flat_water=False, slip_heads=False, short_water=False, float_cover=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    plan = plan_pond()
    lay = Layout(plan)
    flags = dict(float_reeds=float_reeds, sink_pad=sink_pad, flat_water=flat_water,
                 slip_heads=slip_heads, short_water=short_water, float_cover=float_cover)
    low = build_pond_mesh("PondLow", plan, lay, "low", **flags)
    high = build_pond_mesh("PondHigh", plan, lay, "high", **flags)
    mats = pond_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    soil_mat = mats[SOIL_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none2 = (None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("pond mesh did not build", 3),) + none2

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
    zf = zfight_pairs(low.data, cls["groups"])
    if len(cls["soil"]) != 1 or len(cls["water"]) != 1:
        return (fail(f"soil or water shell not found: soil {len(cls['soil'])}, "
                     f"water {len(cls['water'])}", 3),) + none2
    roots = root_audit(cls)
    pads = pad_audit(cls)
    level, amp, ntop = level_audit(low.data, cls)
    heads, nheaded = head_audit(cls)
    enclose, nrim = enclose_audit(low.data, cls)
    nshells, nloose, loose_kinds = cover_audit(cls)

    img, tex = setup_bake_image(low, soil_mat)
    if img is None:
        return (fail("pond has no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "PondLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "PondLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("PondColSrc")
    collider = convex_hull_collider(collider_src, "PondCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_pond_edge_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    n_reeds = len(lay.leaves) + len(lay.stems)
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
    print(f"measured shells={len(cls['all'])} leaves={len(cls['leaves'])} stems={len(cls['stems'])} "
          f"heads={len(cls['heads'])} pads={len(cls['pads'])} tufts={len(lay.tufts)} "
          f"pebbles={len(lay.pebbles)} litter={len(lay.litter)}")
    if roots:
        print(f"measured roots n={len(roots)}/{n_reeds} min={min(roots):.4f} max={max(roots):.4f}")
    for k, (fb, dr, tl) in enumerate(pads):
        print(f"measured pad {k} freeboard={fb:.5f} draft={dr:.5f} tilt={tl:.3f}")
    print(f"measured water level={level:.5f} (declared {WATER_LEVEL}) ripple_amp={amp:.5f} "
          f"top_verts={ntop}")
    for k, (off, above) in enumerate(heads):
        print(f"measured head {k} axis_off={off:.5f} spike_above={above:.4f}")
    print(f"measured enclosed min_bank_over_rim={enclose:.5f} rim_edges={nrim}")
    print(f"measured cover shells={nshells} loose={nloose} kinds={dict(sorted(loose_kinds.items()))}")

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
    if len(roots) != n_reeds or min(roots) < ROOT_MIN or max(roots) > ROOT_MAX:
        return (fail(f"rooted reeds: {len(roots)}/{n_reeds} leaves and stems, lowest vertex "
                     f"{min(roots):.4f}-{max(roots):.4f} m under the mud, not in "
                     f"[{ROOT_MIN}, {ROOT_MAX}]", 17),) + none2
    if (len(pads) != len(PADS)
            or any(not (FREEBOARD_MIN <= fb <= FREEBOARD_MAX) or not (DRAFT_MIN <= dr <= DRAFT_MAX)
                   or tl > PAD_TILT_MAX for fb, dr, tl in pads)):
        return (fail(f"floating pads: {len(pads)}/{len(PADS)}, (freeboard, draft, tilt) {pads} "
                     f"not all in [{FREEBOARD_MIN}, {FREEBOARD_MAX}], [{DRAFT_MIN}, {DRAFT_MAX}], "
                     f"<= {PAD_TILT_MAX} deg", 18),) + none2
    if abs(level - WATER_LEVEL) > LEVEL_TOL or not (RIPPLE_MIN <= amp <= RIPPLE_MAX):
        return (fail(f"water: level {level:.5f} (declared {WATER_LEVEL} +- {LEVEL_TOL}), ripple "
                     f"{amp:.5f} not in [{RIPPLE_MIN}, {RIPPLE_MAX}]", 19),) + none2
    if (len(heads) != N_STEMS or nheaded != N_STEMS
            or any(off > HEAD_AXIS_TOL or above < SPIKE_MIN for off, above in heads)):
        return (fail(f"seed heads: {len(heads)} on {nheaded} stems of {N_STEMS}, (axis offset, spike) "
                     f"{heads} (offset <= {HEAD_AXIS_TOL}, spike >= {SPIKE_MIN})", 20),) + none2
    if enclose < ENCLOSE_MIN:
        return (fail(f"water not enclosed: the bank over its rim {enclose:.5f} m "
                     f"(min {ENCLOSE_MIN})", 21),) + none2
    if nloose:
        return (fail(f"ground cover: {nloose} of {nshells} shells not joined to the soil "
                     f"{dict(sorted(loose_kinds.items()))}", 22),) + none2
    return 0, low, soil_mat


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

    # Key, fill, rim, a low sheen behind the pond for the water to reflect,
    # and the warm wedge on the back wall.
    light("Key", (-3.6, -4.6, 5.6), 232.0, 2.6, (1.0, 0.95, 0.88), spread=14.0)
    light("Fill", (6.0, -3.5, 1.4), 7.0, 7.0, (0.72, 0.82, 1.0))
    light("Rim", (-1.8, 3.4, 3.2), 120.0, 2.6, (0.62, 0.78, 1.0))
    light("Sheen", (1.1, 3.0, 1.2), 14.0, 1.2, (0.85, 0.90, 1.0),
          target=(centre.x + 0.1, centre.y - 0.2, WATER_LEVEL))
    light("Wedge", (3.8, 1.2, 2.6), 300.0, 3.4, (1.0, 0.75, 0.50),
          target=(2.2, WALL_Y - 1.2, 0.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.36, -0.93, 0.0)).normalized()
    cam.location = centre + view * 5.6 + Vector((0.0, 0.0, 1.95))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.37))
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
        # screen-traced reflections, so the reeds show in the water
        try:
            scene.eevee.use_raytracing = True
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "WEBP" if path.lower().endswith(".webp") else "PNG"
    if path.lower().endswith(".webp"):
        scene.render.image_settings.quality = 90
    scene.render.filepath = path
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the lilies.
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
    p.add_argument("--float-reeds", action="store_true")
    p.add_argument("--sink-pad", action="store_true")
    p.add_argument("--flat-water", action="store_true")
    p.add_argument("--slip-heads", action="store_true")
    p.add_argument("--short-water", action="store_true")
    p.add_argument("--float-cover", action="store_true")
    args = p.parse_args(argv)

    code, low, _soil = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_reeds=args.float_reeds,
        sink_pad=args.sink_pad,
        flat_water=args.flat_water,
        slip_heads=args.slip_heads,
        short_water=args.short_water,
        float_cover=args.float_cover,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("pond-edge OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
