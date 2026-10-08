"""Game-ready river delta map tile — a showcase piece, not an example.

Asserts budget conformance of a procedural strategy-game map tile after
composing shipped pipeline pieces: bmesh construction, UVs, seven
materials, high-to-low normal bake, LOD chain, convex hull colliders,
Unity glTF export.

A square tile 2.40 m on a side, low and flat. A river comes in through the
back edge and splits twice into four distributaries that fan out across a
delta plain to the sea at the front; the sea fills the tile out to its rim
on the front and both sides. Every channel runs between natural levees a
little higher than the marsh behind them, its water falling all the way to
the mouth, where it slides out under the sea in a plume of silt. Sandy
middle-ground bars stand off three of the mouths; an oxbow lake and two
ponds lie in the floodbasins; reed beds fringe the channels and the shore,
willows and poplars stand on the levees and the older plain, drift logs
float in the sea or lie stranded on the bars, and a fisherman's hut stands
on stilts in a bay at the end of a jetty, a boat moored beside it and a
fish weir of stakes in the shallows.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--uphill-channel`` the water
falling all the way down every channel, ``--choke-branch`` the width rule
at each bifurcation, ``--splay-fork`` the bifurcation angle,
``--plug-mouth`` every mouth reaching the sea, ``--breach-levee`` the
levees over the water and the marsh, ``--drown-islet`` the islands above
water, ``--flat-sea`` the sea's level and swell, ``--short-sea`` the water
contained, ``--float-reeds`` the reeds rooted, ``--sink-logs`` the
floating logs and the boat afloat, ``--lift-hut`` the stilts, jetty posts
and weir stakes footed in the bed, ``--float-trees`` the trees rooted.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python river_delta_tile.py --
    blender --background --python river_delta_tile.py -- --skip-decimate
    blender --background --python river_delta_tile.py -- --output delta.png
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

SEED = 5203
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- The tile: a square, its back edge at +Y ------------------------------------
HALF = 1.20               # half the side, m
TILE_N = {"low": 176, "high": 264}   # lattice cells along a side
SEA_Z = 0.150             # the sea's declared level
RIM_Z = SEA_Z + 0.034     # the rim's flat top
CHAMFER = 0.005           # the rim's outer arris drops this far
LIP_W = 0.040             # the rim's flat band
LIP_R = 0.060             # the ground climbs to the rim over this
EDGE_IN = 0.0015          # water cut by the back edge stops this far inside it

# --- The delta: polar about an apex behind the tile -----------------------------
APEX = (-0.06, 1.62)
COAST_R0 = 2.17
COAST_K = 0.80            # the fan's coast draws back toward the sides, per rad^2 off the axis
COAST_SIDE = 0.06         # off the fan's flanks the coast runs to the sides along this line
COAST_LOBE = 0.105        # each mouth builds its lobe out this far
COAST_SIG = math.radians(5.5)
COAST_WIG = ((7, 0.012, 0.4), (13, 0.006, 2.2), (23, 0.003, 1.1))
SHORE_GRAD = 0.10         # the shore's rise from the sea, m per m
SHELF, DEEP = 0.009, 0.032

# --- Water levels ------------------------------------------------------------
W_IN = 0.016              # the river at the apex's ring through the back edge
R_FLAT = 1.85             # past this radius the channels' water lies at the sea's level
BASIN = 0.0042            # the floodbasin this far over its local water
EB = 0.022                # the bank's rise to the floodbasin
SWELL = 0.0007
OLD_H = 0.0050            # the older upper delta plain stands this much higher, behind
OLD_R = (0.65, 1.35)      # ... easing down to the lower plain between these radii
FARM_R = (1.25, 1.55)     # fields on the upper plain, giving out to marsh between these radii

# --- The channels: (parent, control points, the parent's discharge share) --------
PATH_STEP = 0.003
W_TRUNK = 0.052           # the trunk's half-width
D_TRUNK = 0.011           # its depth under the water
BRANCHES = (
    (-1, ((-0.13, 1.31), (-0.10, 1.12), (-0.03, 0.94), (-0.07, 0.74), (-0.04, 0.56), (-0.03, 0.43)), 1.0),
    (0, ((-0.12, 0.29), (-0.24, 0.15), (-0.33, 0.03), (-0.40, -0.05)), 0.56),
    (0, ((0.07, 0.30), (0.18, 0.19), (0.28, 0.07), (0.36, 0.00)), 0.44),
    (1, ((-0.57, -0.09), (-0.69, -0.19), (-0.79, -0.31), (-0.86, -0.43), (-0.90, -0.55)), 0.52),
    (1, ((-0.40, -0.22), (-0.40, -0.38), (-0.42, -0.53), (-0.39, -0.67), (-0.37, -0.81)), 0.48),
    (2, ((0.36, -0.19), (0.33, -0.34), (0.30, -0.50), (0.28, -0.64), (0.27, -0.78)), 0.57),
    (2, ((0.53, -0.04), (0.65, -0.15), (0.74, -0.28), (0.80, -0.40), (0.84, -0.53)), 0.43),
)
MOUTH_PATHS = ((0, 1, 3), (0, 1, 4), (0, 2, 5), (0, 2, 6))
MOUTH_FLARE = 0.55        # a mouth widens this much toward the coast
TAIL_CARVE = 0.05         # past the coast the channel's bed fades over this
LEVEE_H = (0.0055, 0.040)   # crest over the bank: base, per metre of half-width
LEVEE_P = (0.008, 0.45)     # crest this far out from the bank: base, per half-width
UPHILL = 0.012            # --uphill-channel raises one channel's water mid-course
UPHILL_B = 1
CHOKE = 0.62              # --choke-branch narrows one channel to this
CHOKE_B = 6
SPLAY = math.radians(30.0)   # --splay-fork swings one channel out about its fork by this
SPLAY_B = 4
PLUG = 0.006              # --plug-mouth dams one mouth this far over the water
PLUG_B = 4
BREACH_B = 2              # --breach-levee cuts a crevasse in this channel's bank
BREACH_S = (0.24, 0.36)

# --- Bars, ponds -------------------------------------------------------------------
BAR_MOUTHS = (3, 5, 6)    # middle-ground bars off these mouths
BAR_A = (0.135, 0.115, 0.145)
BAR_B = (0.072, 0.064, 0.074)
BAR_SWEEP = 0.35         # the bars' flanks swept back downstream, per bar length at the flank
BAR_TOP = 0.0048
BAR_DROP = 0.0060
DROWN = 0.0100            # --drown-islet lowers the first bar's crest this far
# ponds: centre, radius of the arc (0 for an ellipse), half-width / radii, span
PONDS = (((0.30, 0.84), 0.120, 0.019, (math.radians(-75.0), math.radians(70.0))),
         ((0.74, 0.40), 0.0, (0.060, 0.038), math.radians(25.0)),
         ((-0.73, 0.06), 0.0, (0.044, 0.030), math.radians(-30.0)))
POND_D = 0.006
POND_STEEP = 0.30

# --- Water sheet ---------------------------------------------------------------------
WET_H = 0.0025            # a lattice vertex is wet under its water plus this
WATER_FLOOR = SEA_Z - 0.042   # the slab's flat underside, under all the ground it lies on
RIPPLE = ((0.0011, 23.0, 0.35), (0.0008, 37.0, 2.10), (0.0005, 61.0, 4.0))
SHORT_PULL = 0.050

# --- Scatter -----------------------------------------------------------------------
N_REED = 300
REED_ROOT = 0.005
REED_H = (0.020, 0.044)   # a blade's height over the ground
REED_SPREAD = 0.011       # a clump's feet within this of its middle
FLOAT_REEDS = 0.03
N_WILLOW = 26
N_POPLAR = 9
ROOT_D = 0.010
FLOAT_TREES = 0.04
POST_ROOT = 0.010
LIFT_HUT = 0.030
SINK_LOGS = 0.030
SECTORS = 8

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (2.4000, 2.4000, 0.2948)
BASE_TRIS_MIN = 138000
BASE_TRIS_MAX = 142500
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 7
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 360
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# face floors: terrain, water, reed, timber, bark, foliage, plinth
FACE_FLOORS = (51900, 45300, 16880, 955, 627, 5257, 9560)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Channels
DRAIN_EPS = 1e-6
DRAIN_STEP = 0.004
WIDTH_BAND = (0.88, 1.12)     # (sum of the children's widths squared) / the parent's
WIDTH_STATION = (0.10, 0.15)  # upstream on the parent, downstream on each child
FORK_BAND = (58.0, 82.0)      # degrees between the children
FORK_STATIONS = (0.07, 0.19)
MOUTH_WET = 0.0010
MOUTH_EPS = 0.0020
CREST_MIN = 0.0040
BACK_MIN = 0.0018
ISLAND_MIN = 0.0025
# Water
LEVEL_EPS = 0.0015
RIPPLE_BAND = (0.0010, 0.0060)
POND_FLAT = 0.0004
ENCLOSE_MIN = 0.0015
# Scatter
REED_BAND = (0.002, 0.030)
FLOAT_BAND = (0.25, 0.75)
PERCH_BAND = 0.0025
POST_BAND = (0.004, 0.050)
ROOT_BAND = (0.004, 0.050)
HERO_YAW_DEG = 0.0
WALL_Y = 4.2

TERRAIN_IDX = 0
WATER_IDX = 1
REED_IDX = 2
TIMBER_IDX = 3
BARK_IDX = 4
FOLIAGE_IDX = 5
PLINTH_IDX = 6
MAT_LABELS = ("terrain", "water", "reed", "timber", "bark", "foliage", "plinth")

# part tags, one per face, so the audits can name a shell's role
(P_TILE, P_WATER, P_REED, P_TRUNK, P_CROWN, P_FLOAT, P_LOG, P_POST, P_BUILT) = range(1, 10)


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


def sq_in(x, y):
    """Distance inside the square's outline (negative outside)."""
    return HALF - max(abs(x), abs(y))


def square_lattice(n, half):
    """An (n + 1)^2 lattice over the square, its cells split on alternating
    diagonals: points, CCW triangles, and the outline ring in CCW order."""
    s = 2.0 * half / n
    pts = [(-half + i * s, -half + j * s) for j in range(n + 1) for i in range(n + 1)]

    def k(i, j):
        return j * (n + 1) + i

    tris = []
    for j in range(n):
        for i in range(n):
            a, b, c, d = k(i, j), k(i + 1, j), k(i + 1, j + 1), k(i, j + 1)
            if (i + j) % 2 == 0:
                tris.append((a, b, c))
                tris.append((a, c, d))
            else:
                tris.append((a, b, d))
                tris.append((b, c, d))
    ring = ([k(i, 0) for i in range(n)] + [k(n, j) for j in range(n)]
            + [k(i, n) for i in range(n, 0, -1)] + [k(0, j) for j in range(n, 0, -1)])
    return pts, tris, ring


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


# --------------------------------------------------------------------------
# The ground and the water as functions of plan position
# --------------------------------------------------------------------------

def polar(x, y):
    dx, dy = x - APEX[0], y - APEX[1]
    return math.hypot(dx, dy), math.atan2(dy, dx)


def wrel(r, r_top):
    """The channels' water over the sea, falling with distance from the apex
    to the sea's level at R_FLAT, and level with the sea past it: the
    backwater reach of every distributary."""
    t = min(max((r - r_top) / (R_FLAT - r_top), 0.0), 1.0)
    return W_IN * (1.0 - t) ** 1.25


def swell(x, y):
    return SWELL * (math.sin(5.3 * x + 1.7 * y + 0.4) * math.cos(4.1 * y - 2.3 * x + 1.1)
                    + 0.6 * math.sin(11.0 * x - 7.0 * y + 2.0))


def ripple(plan, x, y):
    ph = plan["ripple"]
    out = 0.0
    for k, (amp, freq, ang) in enumerate(RIPPLE):
        out += amp * math.sin(freq * (x * math.cos(ang) + y * math.sin(ang)) + ph[k])
    return out


class Terrain:
    """The tile's ground and water in closed form. The channels are
    Catmull-Rom centrelines; their water is a function of distance from the
    apex alone, so it falls along every channel and is continuous through
    every bifurcation. The ground is that water plus the floodbasin's rise
    and the levees, carved by the channels, tapered into the sea at the
    coast, with bars, ponds and the rim."""

    def __init__(self, flags):
        self.flags = flags
        self.br = []
        for b, (parent, ctrl, q) in enumerate(BRANCHES):
            ctrl = list(ctrl)
            if flags.get("splay_fork") and b == SPLAY_B:
                # swing the channel out about its junction
                j = self.br[parent]["path"][-1]
                ang = SPLAY * (1.0 if b % 2 == 0 else -1.0)
                ca, sa = math.cos(ang), math.sin(ang)
                ctrl = [(j[0] + (px - j[0]) * ca - (py - j[1]) * sa, j[1] + (px - j[0]) * sa + (py - j[1]) * ca)
                        for px, py in ctrl]
            if parent >= 0:
                ctrl = [self.br[parent]["path"][-1][:2]] + ctrl
                w = self.br[parent]["w"] * math.sqrt(q)
                dep = self.br[parent]["dep"] * q ** 0.25
            else:
                w, dep = W_TRUNK, D_TRUNK
            if flags.get("choke_branch") and b == CHOKE_B:
                w *= CHOKE
            path = catmull_open(ctrl, PATH_STEP)
            kd = KDTree(len(path))
            for i, (x, y, _s) in enumerate(path):
                kd.insert((x, y, 0.0), i)
            kd.balance()
            self.br.append({"parent": parent, "path": path, "kd": kd, "w": w, "dep": dep,
                            "lh": LEVEE_H[0] + LEVEE_H[1] * w, "ep": LEVEE_P[0] + LEVEE_P[1] * w,
                            "mouth": not any(p == b for p, _c, _q in BRANCHES), "len": path[-1][2]})
        self.r_top = polar(*self.br[0]["path"][0][:2])[0]
        self.mouth_th = [polar(*br["path"][-1][:2])[1] for br in self.br if br["mouth"]]
        for br in self.br:
            br["s_cross"] = br["len"]
            if br["mouth"]:
                for x, y, s in br["path"]:
                    if self.dc(x, y) <= 0.0:
                        br["s_cross"] = s
                        break
        # the middle-ground bars, off three mouths, past the channel's end
        self.bars = []
        for k, b in enumerate(BAR_MOUTHS):
            path = self.br[b]["path"]
            ex, ey, _s = path[-1]
            px, py, _s = path[-12]
            dx, dy = ex - px, ey - py
            ln = math.hypot(dx, dy)
            dx, dy = dx / ln, dy / ln
            off = 0.035 + BAR_A[k] * 0.70
            top = BAR_TOP - (DROWN if (k == 0 and flags.get("drown_islet")) else 0.0)
            self.bars.append({"c": (ex + dx * off, ey + dy * off), "ang": math.atan2(dy, dx),
                              "a": BAR_A[k], "b": BAR_B[k], "top": top})
        # ponds: each level under the lowest ground round it
        self.ponds = []
        for k, (c, rad, hw, span) in enumerate(PONDS):
            self.ponds.append({"c": c, "rad": rad, "hw": hw, "span": span, "level": 0.0})
        for k, p in enumerate(self.ponds):
            lows = []
            for j in range(96):
                th = TAU * j / 96
                for f in (1.05, 1.25, 1.5):
                    x, y = self.pond_point(p, th, f)
                    lows.append(self.ground(x, y, ponds=False))
            p["level"] = min(lows) - 0.0035

    # -- geometry helpers -------------------------------------------------------

    def coast_r(self, th):
        r = COAST_R0 - COAST_K * (th + 0.5 * math.pi) ** 2
        for tm in self.mouth_th:
            r += COAST_LOBE * math.exp(-((th - tm) / COAST_SIG) ** 2)
        # off the flanks the land runs out to the sides along a line
        sn = -math.sin(th)
        if sn > 0.05:
            side = (APEX[1] - COAST_SIDE) / sn
            k = 0.06
            r = 0.5 * (r + side + math.sqrt((r - side) ** 2 + k * k))
        return r + sum(a * math.sin(k * th + p) for k, a, p in COAST_WIG)

    def dc(self, x, y):
        r, th = polar(x, y)
        return self.coast_r(th) - r

    def width(self, b, s):
        br = self.br[b]
        w = br["w"]
        if br["mouth"]:
            w *= 1.0 + MOUTH_FLARE * smoothstep(s, br["s_cross"] - 0.16, br["s_cross"] + 0.03)
        return w

    def pond_rho(self, p, x, y):
        cx, cy = p["c"]
        if p["rad"] > 0.0:
            d = math.hypot(x - cx, y - cy)
            a = math.atan2(y - cy, x - cx) % TAU
            a0, a1 = p["span"]
            mid = 0.5 * (a0 + a1)
            half = 0.5 * (a1 - a0)
            da = abs((a - mid + math.pi) % TAU - math.pi)
            off = max(0.0, da - half) * p["rad"]
            return math.hypot((d - p["rad"]) / p["hw"], off / p["hw"])
        rx, ry = p["hw"]
        ca, sa = math.cos(p["span"]), math.sin(p["span"])
        u = (x - cx) * ca + (y - cy) * sa
        v = -(x - cx) * sa + (y - cy) * ca
        return math.hypot(u / rx, v / ry)

    def pond_point(self, p, th, f):
        """A point at ``f`` times the pond's half-width out from its axis."""
        cx, cy = p["c"]
        if p["rad"] > 0.0:
            a0, a1 = p["span"]
            a = a0 + (a1 - a0) * (0.5 + 0.5 * math.sin(th))
            rr = p["rad"] + f * p["hw"] * math.cos(th)
            return cx + rr * math.cos(a), cy + rr * math.sin(a)
        rx, ry = p["hw"]
        ca, sa = math.cos(p["span"]), math.sin(p["span"])
        u, v = f * rx * math.cos(th), f * ry * math.sin(th)
        return cx + u * ca - v * sa, cy + u * sa + v * ca

    def channels(self, x, y):
        """Per branch (e, d, w, s): distance beyond the bank, from the
        centreline, the half-width and the station of the nearest point."""
        out = []
        for b, br in enumerate(self.br):
            _co, i, d = br["kd"].find((x, y, 0.0))
            s = br["path"][i][2]
            w = self.width(b, s)
            out.append((d - w, d, w, s))
        return out

    def water_land(self, r, dc):
        """The channels' water inland, falling with distance from the apex."""
        del dc
        return SEA_Z + wrel(r, self.r_top)

    def sea_depth(self, out, x, y):
        d = SHELF * (1.0 - math.exp(-out / 0.10)) + (DEEP - SHELF) * smoothstep(out, 0.22, 0.75)
        # shoaled in front of the mouths by the plume's load
        for br in self.br:
            if br["mouth"]:
                ex, ey, _s = br["path"][-1]
                d *= 1.0 - 0.45 * math.exp(-((x - ex) ** 2 + (y - ey) ** 2) / 0.18 ** 2)
        return d * (1.0 + 0.08 * math.sin(3.1 * x + 1.3 * y) * math.cos(2.7 * y - 1.9 * x))

    def bar_q2(self, bar, x, y):
        """The bar's squared normalised radius: under 1 inside its outline."""
        cx, cy = bar["c"]
        ca, sa = math.cos(bar["ang"]), math.sin(bar["ang"])
        u = (x - cx) * ca + (y - cy) * sa
        vn = (-(x - cx) * sa + (y - cy) * ca) / bar["b"]
        # a middle-ground bar's arrowhead: its head blunt to the current,
        # its flanks swept back downstream round the water it splits, as the
        # Wax Lake and Mississippi mouth bars grow — not a hull-like teardrop
        us = u - BAR_SWEEP * bar["a"] * vn * vn
        a = bar["a"] * (0.62 if us < 0.0 else 1.0)
        phi = math.atan2(vn, us / a)
        # a ragged outline
        wob = 1.0 + 0.10 * math.sin(3.0 * phi + bar["ang"] * 5.0) + 0.06 * math.sin(7.0 * phi + 1.3)
        return ((us / a) ** 2 + vn * vn) / (wob * wob)

    def bar_z(self, bar, x, y):
        # a flat-topped crown, falling away round its margin into the shoal
        return SEA_Z + bar["top"] - BAR_DROP * self.bar_q2(bar, x, y) ** 1.5

    def carve_fade(self, b, s):
        br = self.br[b]
        start = br["s_cross"] + 0.5 * TAIL_CARVE
        # a channel that never reaches the sea is carved to its end
        if not br["mouth"] or br["len"] <= start:
            return 1.0
        return 1.0 - smoothstep(s, start, br["len"])

    def ground(self, x, y, rim=True, ponds=True, info=None):
        """The ground's height. ``info`` (a dict) is filled with what the
        builders and the audits read: the water here, the nearest channel."""
        r, th = polar(x, y)
        dc = self.coast_r(th) - r
        wl = self.water_land(r, dc) if dc >= 0.0 else SEA_Z
        ch = self.channels(x, y)
        lev = 0.0
        bed = 9.0
        e_min = 9.0
        nb = 0
        for b, (e, d, w, s) in enumerate(ch):
            br = self.br[b]
            if e < e_min:
                e_min, nb = e, b
            if e >= 0.0:
                lev = max(lev, br["lh"] * (e / br["ep"]) * math.exp(1.0 - e / br["ep"]))
            if d < w:
                dep = br["dep"] * self.carve_fade(b, s) * (1.0 - (d / w) ** 2)
                if dep > 2e-4:
                    bed = min(bed, wl - dep)
        elev = ((wl - SEA_Z) + BASIN * (1.0 - math.exp(-max(e_min, 0.0) / EB)) + lev + swell(x, y)
                + OLD_H * smoothstep(r, OLD_R[1], OLD_R[0]) * smoothstep(e_min, 0.0, 0.06))
        if self.flags.get("breach_levee"):
            e, d, w, s = ch[BREACH_B]
            br = self.br[BREACH_B]
            if BREACH_S[0] <= s <= BREACH_S[1] and 0.0 <= e < 4.0 * br["ep"]:
                # the left bank, looking downstream
                i = min(int(round(s / PATH_STEP)), len(br["path"]) - 2)
                px, py, _s = br["path"][i]
                qx, qy, _s = br["path"][i + 1]
                if (qx - px) * (y - py) - (qy - py) * (x - px) > 0.0:
                    elev = min(elev, wl - SEA_Z - 0.002)
        if dc >= 0.0:
            z = SEA_Z + min(elev, SHORE_GRAD * dc)
        else:
            z = SEA_Z - self.sea_depth(-dc, x, y)
        for bar in self.bars:
            z = max(z, self.bar_z(bar, x, y))
        if self.flags.get("plug_mouth"):
            e, d, w, s = ch[PLUG_B]
            sc = self.br[PLUG_B]["s_cross"]
            if sc - 0.07 <= s <= sc - 0.04 and e < 2.0 * self.br[PLUG_B]["ep"]:
                z = max(z, wl + PLUG)
                bed = 9.0
        pk = -1
        if ponds:
            for k, p in enumerate(self.ponds):
                rho = self.pond_rho(p, x, y)
                if rho < 1.6:
                    pk = k
                pb = p["level"] - POND_D * (1.0 - min(rho, 1.0) ** 2) + POND_STEEP * max(0.0, rho - 1.0) * (
                    p["hw"] if p["rad"] > 0.0 else min(p["hw"]))
                z = min(z, pb)
        if rim:
            hin = sq_in(x, y)
            lip = smoothstep(hin, LIP_W + LIP_R, LIP_W)
            if lip > 0.0:
                z += (RIM_Z - z) * lip
        z = min(z, bed)
        # never within a millimetre of the water over it: the two sheets
        # share the lattice, and must not share a vertex or a plane (a face
        # within the coplanar test's 0.8 degrees, 50 mm off, strays 0.7 mm)
        lvl = self.ponds[pk]["level"] if pk >= 0 else wl
        off = 9e-4 + 6e-4 * hash01(x * 997.0, y * 991.0, 5)
        if abs(z - lvl) < off:
            z = lvl + (off if z >= lvl else -off)
        if info is not None:
            info.update(r=r, th=th, dc=dc, wl=wl, e=e_min, nb=nb, s=ch[nb][3], pond=pk, chan=bed < 9.0)
            if pk >= 0:
                info["wl"] = self.ponds[pk]["level"]
        return z

    def frame(self, b, s):
        """A channel's centreline point, unit tangent and left normal at ``s``."""
        path = self.br[b]["path"]
        i = min(max(int(round(s / PATH_STEP)), 0), len(path) - 2)
        x, y, _s = path[i]
        qx, qy, _s = path[i + 1]
        tx, ty = qx - x, qy - y
        ln = math.hypot(tx, ty) or 1.0
        tx, ty = tx / ln, ty / ln
        return (x, y), (tx, ty), (-ty, tx)


class Ground:
    """A built surface, sampled by a ray straight down."""

    def __init__(self, tree):
        self.tree = tree

    def z(self, x, y):
        loc, _n, _i, _d = self.tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
        return None if loc is None else loc.z


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------

def plan_scene(T):
    """Every seeded draw, before anything is built."""
    rng = random.Random(SEED)
    plan = {"ripple": [rng.uniform(0.0, TAU) for _ in range(6)]}
    taken = []   # (x, y, r): placed trees, reeds, logs, the hut

    def clear(x, y, r, gap=0.004):
        return all(math.hypot(x - a, y - b) >= r + c + gap for a, b, c in taken)

    # the hut, its jetty, the boat and the weir: in the bay between the
    # second and third mouths
    t4 = polar(*T.br[4]["path"][-1][:2])[1]
    t5 = polar(*T.br[5]["path"][-1][:2])[1]
    tb = 0.42 * t4 + 0.58 * t5
    rc = T.coast_r(tb)
    ux, uy = math.cos(tb), math.sin(tb)
    hut = (APEX[0] + ux * (rc + 0.115), APEX[1] + uy * (rc + 0.115))
    shore = (APEX[0] + ux * (rc - 0.035), APEX[1] + uy * (rc - 0.035))
    plan["hut"] = {"c": hut, "shore": shore, "dir": (ux, uy), "yaw": tb + 0.5 * math.pi}
    taken.append((hut[0], hut[1], 0.075))
    for f in (0.2, 0.45, 0.7):
        taken.append((shore[0] + (hut[0] - shore[0]) * f, shore[1] + (hut[1] - shore[1]) * f, 0.02))
    lx, ly = -uy, ux
    plan["boat"] = {"c": (hut[0] - ux * 0.035 + lx * 0.072, hut[1] - uy * 0.035 + ly * 0.072),
                    "yaw": tb + 0.18, "len": 0.085, "beam": 0.030}
    taken.append((plan["boat"]["c"][0], plan["boat"]["c"][1], 0.045))
    # the weir: two lines of stakes meeting in a V that points out to sea,
    # off the shore between the third and fourth mouths
    t6 = polar(*T.br[6]["path"][-1][:2])[1]
    tw = 0.5 * (t5 + t6)
    rw = T.coast_r(tw)
    wx, wy = math.cos(tw), math.sin(tw)
    apex = (APEX[0] + wx * (rw + 0.21), APEX[1] + wy * (rw + 0.21))
    stakes = []
    for side in (-1.0, 1.0):
        ang = tw + math.pi + side * math.radians(28.0)
        for k in range(8):
            d = 0.012 + k * 0.016
            stakes.append((apex[0] + math.cos(ang) * d, apex[1] + math.sin(ang) * d,
                           0.010 + 0.004 * rng.uniform(0.0, 1.0)))
    plan["weir"] = stakes
    for x, y, _h in stakes:
        taken.append((x, y, 0.006))

    # logs: three afloat, four stranded up the beaches
    logs = []
    floats = ((4, 0.10, 0.06, 0.6), (6, 0.40, 0.0, 2.3), (0, 0.55, 0.0, 0.12))
    for b, past, side, yaw in floats:
        br = T.br[b]
        if br["mouth"]:
            (x, y), (tx, ty), (nx, ny) = T.frame(b, br["len"] - 0.004)
            x, y = x + tx * past + nx * side, y + ty * past + ny * side
        else:
            (x, y), (tx, ty), (nx, ny) = T.frame(b, past)
        ln = rng.uniform(0.075, 0.105)
        logs.append({"x": x, "y": y, "yaw": math.atan2(ty, tx) + yaw, "len": ln,
                     "r": rng.uniform(0.0050, 0.0065), "float": True, "tone": rng.uniform(0.0, 1.0),
                     "bend": rng.uniform(-1.0, 1.0)})
        taken.append((x, y, 0.5 * ln))
    got = 0
    for _ in range(3000):
        if got >= 4:
            break
        # all up the beaches, none on the bars: a bleached log across a bar
        # reads, at a distance, as a boat's oar
        th = rng.uniform(-2.2, -0.9)
        x = APEX[0] + (T.coast_r(th) - 0.032) * math.cos(th)
        y = APEX[1] + (T.coast_r(th) - 0.032) * math.sin(th)
        ln = rng.uniform(0.070, 0.110)
        draws = [rng.uniform(0.0, 1.0) for _ in range(4)]
        if sq_in(x, y) < 0.16 or not clear(x, y, 0.5 * ln):
            continue
        info = {}
        z = T.ground(x, y, info=info)
        if z < SEA_Z + 0.0015 or info["chan"]:
            continue
        logs.append({"x": x, "y": y, "yaw": TAU * draws[0], "len": ln, "r": 0.0045 + 0.0020 * draws[1],
                     "float": False, "tone": draws[2], "bend": 2.0 * draws[3] - 1.0})
        taken.append((x, y, 0.5 * ln))
        got += 1
    plan["logs"] = logs

    # trees: a row of poplars along the trunk's levee, willows on the levees
    # and the older plain
    trees = []
    br = T.br[0]
    for k in range(N_POPLAR):
        s = 0.16 + k * 0.065
        (x, y), (_tx, _ty), (nx, ny) = T.frame(0, s)
        side = -1.0
        e = br["w"] + 1.05 * br["ep"]
        x, y = x + nx * side * e, y + ny * side * e
        trees.append({"x": x, "y": y, "kind": "poplar", "size": rng.uniform(0.0, 1.0),
                      "tone": rng.uniform(0.0, 1.0), "spin": rng.uniform(0.0, TAU), "r": 0.018})
        taken.append((x, y, 0.018))
    got = 0
    for _ in range(20000):
        if got >= N_WILLOW:
            break
        x = rng.uniform(-HALF, HALF)
        y = rng.uniform(-HALF, HALF)
        size = rng.uniform(0.0, 1.0)
        tone = rng.uniform(0.0, 1.0)
        spin = rng.uniform(0.0, TAU)
        keep = rng.uniform(0.0, 1.0)
        r = 0.028 + 0.012 * size
        if sq_in(x, y) < LIP_W + LIP_R + 0.03 or not clear(x, y, r):
            continue
        info = {}
        T.ground(x, y, info=info)
        if info["dc"] < 0.12 or info["pond"] >= 0 or info["e"] < 0.012:
            continue
        nbr = T.br[info["nb"]]
        on_levee = 0.4 * nbr["ep"] < info["e"] < 1.8 * nbr["ep"]
        grove = 0.5 + 0.5 * math.sin(6.0 * x + 2.0 * y + 0.7) * math.cos(4.0 * y - 3.0 * x + 1.4)
        back = smoothstep(info["r"], 1.55, 0.9)
        if keep > (0.75 if on_levee else 0.0) + 0.55 * grove * back:
            continue
        taken.append((x, y, r))
        trees.append({"x": x, "y": y, "kind": "willow", "size": size, "tone": tone, "spin": spin, "r": r})
        got += 1
    plan["trees"] = trees

    # reeds: clumps along the channels' banks, round the shore, in the marsh
    reeds = []
    for _ in range(40000):
        if len(reeds) >= N_REED:
            break
        mode = rng.uniform(0.0, 1.0)
        draws = [rng.uniform(0.0, 1.0) for _ in range(6)]
        if mode < 0.55:
            b = min(int(draws[0] * len(T.br)), len(T.br) - 1)
            br = T.br[b]
            s = draws[1] * br["len"]
            (x, y), _t, (nx, ny) = T.frame(b, s)
            side = 1.0 if draws[2] < 0.5 else -1.0
            e = T.width(b, s) + 0.006 + 0.016 * draws[3]
            x, y = x + nx * side * e, y + ny * side * e
        elif mode < 0.85:
            th = -math.pi * (0.20 + 0.60 * draws[0])
            dc = 0.016 + 0.045 * draws[1]
            x = APEX[0] + (T.coast_r(th) - dc) * math.cos(th)
            y = APEX[1] + (T.coast_r(th) - dc) * math.sin(th)
        elif mode < 0.91:
            x = -HALF + 2.0 * HALF * draws[0]
            y = -HALF + 2.0 * HALF * draws[1]
            marsh = math.sin(8.0 * x + 3.0 * y) * math.cos(6.0 * y - 5.0 * x + 0.8)
            if marsh < 0.35:
                continue
        else:
            # on the bars' crowns
            bar = T.bars[min(int(draws[0] * len(T.bars)), len(T.bars) - 1)]
            ang = TAU * draws[1]
            f = 0.35 * math.sqrt(draws[2])
            x = bar["c"][0] + f * bar["a"] * math.cos(ang) * math.cos(bar["ang"]) - f * bar["b"] * math.sin(ang) * math.sin(bar["ang"])
            y = bar["c"][1] + f * bar["a"] * math.cos(ang) * math.sin(bar["ang"]) + f * bar["b"] * math.sin(ang) * math.cos(bar["ang"])
        if sq_in(x, y) < LIP_W + LIP_R + 0.02 or not clear(x, y, REED_SPREAD, 0.001):
            continue
        info = {}
        z = T.ground(x, y, info=info)
        if z < info["wl"] + 0.0010 or info["pond"] >= 0 and T.pond_rho(T.ponds[info["pond"]], x, y) < 1.15:
            continue
        if info["r"] < 0.95 and mode < 0.55:
            continue
        taken.append((x, y, REED_SPREAD))
        reeds.append({"x": x, "y": y, "n": 11 + int(8 * draws[4]), "h": draws[5], "seed": len(reeds)})
    plan["reeds"] = reeds

    return plan


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

class Builder:
    """The bmesh plus its layers: Tone (shading variety), Part (the shell's
    role), Ident (which tree, log or sheet), Cap (1 on a shell's bottom, 3
    on the tile's skirt), Zone (a water sheet's top); per vertex Rel (the
    ground over its local water), Sand, Silt (the water's load), Open (the
    open sea), Blade (up a reed)."""

    def __init__(self, bm):
        self.bm = bm
        self.tone = bm.faces.layers.float.new("Tone")
        self.zone = bm.faces.layers.float.new("Zone")
        self.part = bm.faces.layers.int.new("Part")
        self.ident = bm.faces.layers.int.new("Ident")
        self.cap = bm.faces.layers.int.new("Cap")
        self.rel = bm.verts.layers.float.new("Rel")
        self.sand = bm.verts.layers.float.new("Sand")
        self.silt = bm.verts.layers.float.new("Silt")
        self.open = bm.verts.layers.int.new("Open")
        self.blade = bm.verts.layers.float.new("Blade")
        self.farm = bm.verts.layers.float.new("Farm")
        self.uv = bm.loops.layers.uv.new("UVMap")

    def vert(self, co):
        return self.bm.verts.new(co)

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


def sand_of(T, info, x, y, z):
    """Sand on the bars, on the lobes' beaches at the mouths and on the
    shallows in front of them; silt and mud elsewhere."""
    sand = 0.0
    for bar in T.bars:
        d = math.sqrt(T.bar_q2(bar, x, y))
        # sandy round its margins and on the shoal round it, its crown grown
        # over with marsh
        sand = max(sand, smoothstep(d, 1.35, 0.85) * (1.0 - 0.85 * smoothstep(d, 0.62, 0.42)))
    lobe = max(math.exp(-((info["th"] - tm) / (1.4 * COAST_SIG)) ** 2) for tm in T.mouth_th)
    sand = max(sand, lobe * smoothstep(info["dc"], 0.09, 0.02) * smoothstep(info["dc"], -0.12, -0.02))
    return sand


def add_tile(B, T, n):
    """The tile: a lattice over the square carrying the delta, the seabed
    and the rim, its outline chamfered down to the rim's edge height (cut
    where the river comes in), and a skirt to a flat base at Z = 0."""
    pts, tris, ring = square_lattice(n, HALF)
    on_ring = set(ring)
    verts = []
    chan = []
    sea = []
    for k, (x, y) in enumerate(pts):
        info = {}
        z = T.ground(x, y, info=info)
        if k in on_ring:
            z = min(RIM_Z - CHAMFER, z)
        v = B.vert((x, y, z))
        v[B.rel] = z - info["wl"]
        v[B.sand] = sand_of(T, info, x, y, z)
        # the lower delta, near the sea: salt marsh and mudflat
        v[B.silt] = smoothstep(info["dc"], 0.40, 0.04)
        # the upper plain, clear of the channels and the ponds: farmland
        v[B.farm] = (smoothstep(info["r"], FARM_R[1], FARM_R[0]) * smoothstep(info["e"], 0.035, 0.075)
                     * (0.0 if info["pond"] >= 0 else 1.0) * smoothstep(sq_in(x, y), LIP_W + LIP_R, LIP_W + LIP_R + 0.03))
        verts.append(v)
        chan.append(info["e"] < 0.012 or z < info["wl"])
        sea.append(info["dc"] < 0.0)
    for a, b, c in tris:
        va, vb, vc = verts[a], verts[b], verts[c]
        hin = min(sq_in(v.co.x, v.co.y) for v in (va, vb, vc))
        if hin < LIP_W + LIP_R + 0.005 and not (chan[a] or chan[b] or chan[c]) and \
                min(v.co.z for v in (va, vb, vc)) > SEA_Z + 0.004:
            mat = PLINTH_IDX
        elif hin < LIP_W + LIP_R + 0.005 and sea[a] and sea[b] and sea[c] and \
                max(v.co.z for v in (va, vb, vc)) > SEA_Z + 0.0005:
            # the frame's slate runs down into the sea as a quay wall, with
            # no strip of shore along it
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


def silt_of(T, x, y, info):
    """The water's load: the channels carry it; out in the sea it fans out
    of the mouths and fades."""
    if info["dc"] >= 0.0:
        return 1.0
    best = 0.0
    for br in T.br:
        if not br["mouth"]:
            continue
        ex, ey, _s = br["path"][-1]
        px, py, _s = br["path"][-20]
        tx, ty = ex - px, ey - py
        ln = math.hypot(tx, ty)
        tx, ty = tx / ln, ty / ln
        u = (x - ex) * tx + (y - ey) * ty
        v = -(x - ex) * ty + (y - ey) * tx
        spread = 0.035 + 0.30 * max(u, 0.0)
        f = math.exp(-max(u, 0.0) / 0.30 - (v / spread) ** 2) * smoothstep(u, -0.25, 0.0)
        best = max(best, f)
    return max(best, 0.45 * smoothstep(info["dc"], -0.05, 0.0))


def add_water(B, T, plan, n, flags):
    """All the water as one lattice slab over the tile's own cells: the sea,
    every channel, and each pond. A cell holds water when any corner lies
    under its water; the sheet's rim then runs under the banks, the shore
    and the rim. The channels' surface is read off their water function,
    the sea's rippled, the ponds' flat."""
    pts, tris, _ring = square_lattice(n, HALF)
    info_of = []
    wet = []
    swell_max = sum(a for a, _f, _g in RIPPLE)
    for k, (x, y) in enumerate(pts):
        info = {}
        g = T.ground(x, y, info=info)
        info["g"] = g
        info_of.append(info)
        # out where the sea swells, its rim must clear the swell's crest too
        lift = swell_max * smoothstep(-info["dc"], 0.26, 0.45) if info["pond"] < 0 else 0.0
        wet.append(g < info["wl"] + WET_H + lift)
    region = {t for t in tris if any(wet[i] for i in t)}
    # a vertex the region touches in two fans would pinch the slab's walls:
    # fill round it until every boundary vertex has one fan
    by_vert = {}
    for t in tris:
        for i in t:
            by_vert.setdefault(i, []).append(t)
    for _ in range(16):
        use = {}
        for t in region:
            for k in range(3):
                a, b = t[k], t[(k + 1) % 3]
                key = (min(a, b), max(a, b))
                use[key] = use.get(key, 0) + 1
        bcount = {}
        for (a, b), c in use.items():
            if c == 1:
                bcount[a] = bcount.get(a, 0) + 1
                bcount[b] = bcount.get(b, 0) + 1
        pinch = [i for i, c in bcount.items() if c > 2]
        if not pinch:
            break
        for i in pinch:
            region.update(by_vert[i])
    # components: keep the sea with its channels, and the ponds
    nbr = {}
    for t in region:
        for k in range(3):
            a, b = t[k], t[(k + 1) % 3]
            nbr.setdefault((min(a, b), max(a, b)), []).append(t)
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
    ident = {}
    for t, c in comp.items():
        for i in t:
            inf = info_of[i]
            if not wet[i]:
                continue
            if inf["pond"] >= 0:
                ident[c] = 10 + inf["pond"]
            elif inf["dc"] < -0.2:
                ident.setdefault(c, 1)
    region = {t for t in region if comp[t] in ident}
    flat = flags.get("flat_sea", False)
    shore = set()
    if flags.get("short_sea"):
        use = {}
        for t in region:
            for k in range(3):
                a, b = t[k], t[(k + 1) % 3]
                key = (min(a, b), max(a, b))
                use[key] = use.get(key, 0) + 1
        shore = {i for key, c in use.items() if c == 1 for i in key
                 if -0.05 < info_of[i]["dc"] < 0.08 and info_of[i]["e"] > 0.02 and info_of[i]["pond"] < 0
                 and sq_in(*pts[i]) > LIP_W + LIP_R + 0.03}
    level = {}
    for t in region:
        if ident[comp[t]] >= 10:
            for i in t:
                level[i] = T.ponds[ident[comp[t]] - 10]["level"]
    top = {}
    for t in region:
        for i in t:
            if i in top:
                continue
            x, y = pts[i]
            inf = info_of[i]
            z = level.get(i, inf["wl"])
            if i not in level:
                if inf["dc"] < 0.0 and not flat:
                    # calm in the lee of the shore and over the mouths'
                    # plumes, and round the bars, which shelter it
                    calm = min(smoothstep(T.bar_q2(bar, x, y), 2.5, 5.0) for bar in T.bars)
                    z += ripple(plan, x, y) * smoothstep(-inf["dc"], 0.26, 0.45) * calm
                if flags.get("uphill_channel") and inf["nb"] == UPHILL_B and inf["dc"] > 0.0:
                    br = T.br[UPHILL_B]
                    z += UPHILL * math.exp(-((inf["s"] - 0.5 * br["len"]) / 0.07) ** 2)
            if i in shore:
                # out from the apex, off the shore it ran under
                dx, dy = x - APEX[0], y - APEX[1]
                ln = math.hypot(dx, dy)
                x, y = x + dx / ln * SHORT_PULL, y + dy / ln * SHORT_PULL
            # the back edge cuts the channel's water: stop it just inside
            x = min(max(x, -HALF + EDGE_IN), HALF - EDGE_IN)
            y = min(max(y, -HALF + EDGE_IN), HALF - EDGE_IN)
            v = B.vert((x, y, z))
            # the colour reads the seabed as if the rim were not there: the
            # sea runs deep right up to the frame's wall, as against a quay,
            # not shoaling into a pale seam along it
            g = inf["g"]
            if sq_in(x, y) < LIP_W + LIP_R + 0.01:
                g = min(g, T.ground(x, y, rim=False))
            v[B.rel] = g - inf["wl"]
            v[B.silt] = 1.0 if i in level else silt_of(T, x, y, inf)
            v[B.open] = 2 if i in level else (1 if inf["dc"] < -0.45 else 0)
            top[i] = v
    use = {}
    for t in region:
        for k in range(3):
            a, b = t[k], t[(k + 1) % 3]
            key = (min(a, b), max(a, b))
            use[key] = use.get(key, 0) + 1
    lows = {}

    def low(i):
        if i not in lows:
            v = top[i]
            w = B.vert((v.co.x, v.co.y, WATER_FLOOR))
            w[B.rel] = v[B.rel]
            w[B.silt] = v[B.silt]
            lows[i] = w
        return lows[i]

    for t in sorted(region):
        idn = ident[comp[t]]
        B.face(tuple(top[i] for i in t), WATER_IDX, 0.5, P_WATER, idn, zone=1.0)
        B.face(tuple(low(i) for i in reversed(t)), WATER_IDX, 0.5, P_WATER, idn, cap=1)
        for k in range(3):
            a, b = t[k], t[(k + 1) % 3]
            if use[(min(a, b), max(a, b))] == 1:
                B.face((top[b], top[a], low(a), low(b)), WATER_IDX, 0.5, P_WATER, idn)


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


def seat(points, G, sink):
    """Sink until every sector's most-buried vertex is ``sink`` under the
    ground."""
    cx = sum(p.x for p in points) / len(points)
    cy = sum(p.y for p in points) / len(points)
    best = [None] * SECTORS
    for p in points:
        s = min(SECTORS - 1, int((math.atan2(p.y - cy, p.x - cx) % TAU) / TAU * SECTORS))
        g = G.z(p.x, p.y)
        d = (0.0 if g is None else g) - p.z
        best[s] = d if best[s] is None else max(best[s], d)
    return min(b for b in best if b is not None) - sink


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
        rings.append([B.vert(p + r * (nrm * math.cos(TAU * k / sides + phase) + b * math.sin(TAU * k / sides + phase)))
                      for k in range(sides)])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            B.face((r0[k], r0[m], r1[m], r1[k]), mat, tone, part, ident)
    B.face(tuple(reversed(rings[0])), mat, tone, part, ident, cap=1)
    B.face(tuple(rings[-1]), mat, tone, part, ident, cap=2)
    return rings


def box(B, centre, size, yaw, mat, tone, part, ident, taper=0.0):
    """A box on its centre, turned ``yaw`` about Z; ``taper`` draws the top
    in."""
    cx, cy, cz = centre
    sx, sy, sz = size
    R = Matrix.Rotation(yaw, 3, "Z")
    vs = []
    for k, (ix, iy, iz) in enumerate(((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                                      (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))):
        f = 1.0 - taper if iz > 0 else 1.0
        vs.append(B.vert(Vector((cx, cy, cz)) + R @ Vector((ix * sx * f, iy * sy * f, iz * sz))))
    for q, cap in (((0, 3, 2, 1), 1), ((4, 5, 6, 7), 0), ((0, 1, 5, 4), 0), ((1, 2, 6, 5), 0),
                   ((2, 3, 7, 6), 0), ((3, 0, 4, 7), 0)):
        B.face(tuple(vs[i] for i in q), mat, tone, part, ident, cap=cap)


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
        g = min(G.z(x + 0.006 * math.cos(a), y + 0.006 * math.sin(a)) for a in (0.0, 2.1, 4.2))
        g = min(g, G.z(x, y))
        # --float-trees lifts the willows: the poplars stand tallest, and
        # would carry the envelope with them
        foot = Vector((x, y, g - ROOT_D + (lift if t["kind"] == "willow" else 0.0)))
        spin = Matrix.Rotation(t["spin"], 3, "Z")
        if t["kind"] == "poplar":
            h = 0.075 + 0.025 * t["size"]
            trunk_r = 0.0035 + 0.001 * t["size"]
            top = foot + Vector((0.0, 0.0, ROOT_D + 0.22 * h))
            tube(B, (foot, top), (trunk_r, trunk_r * 0.85), 6, BARK_IDX, t["tone"], P_TRUNK, ident)
            tone = 0.08 + 0.22 * t["tone"]
            rc = 0.0105 + 0.003 * t["size"]
            # a column of foliage drawn to a point
            for k, (zf, f) in enumerate(((0.38, 1.0), (0.62, 0.86), (0.84, 0.62), (1.0, 0.36))):
                c = foot + Vector((0.0, 0.0, ROOT_D + zf * h))
                lump_ball(B, c, Vector((rc * f, rc * f * 0.9, 0.24 * h * (1.15 - 0.3 * zf))),
                          Matrix.Rotation(t["spin"] + 1.3 * k, 3, "Z"), tone, ident)
        else:
            h = 0.030 + 0.016 * t["size"]
            trunk_r = 0.0045 + 0.0015 * t["size"]
            lean = spin @ Vector((0.004, 0.0, 0.0))
            mid = foot + Vector((0.0, 0.0, ROOT_D + 0.5 * h)) + 0.5 * lean
            top = foot + Vector((0.0, 0.0, ROOT_D + h)) + lean
            tube(B, (foot, mid, top), (trunk_r, trunk_r * 0.85, trunk_r * 0.62), 6, BARK_IDX, t["tone"],
                 P_TRUNK, ident)
            tone = 0.55 + 0.40 * t["tone"]
            rc = 0.030 + 0.012 * t["size"]
            # a weeping willow: one bell of foliage lofted from a rounded
            # crown out to a curtain of shoots hanging nearly to the ground
            # in a ragged hem, long and short strands by turns
            M = 24
            hang = min(0.85 * rc, h - 0.010)
            prof = ((0.0, 0.62), (0.50, 0.55), (0.82, 0.38), (0.98, 0.12), (1.04, -0.40), (1.10, -1.0))
            rings = []
            for j, (rf, zf) in enumerate(prof[1:]):
                ring = []
                for k in range(M):
                    a = t["spin"] + TAU * k / M
                    jag = ((0.45 if k % 2 else 0.80) + 0.20 * hash01(n, k, 11)) if j == len(prof) - 2 else 1.0
                    lump = 1.0 + 0.06 * math.sin(5.0 * a + 3.0 * t["tone"]) * (1.0 if j < 3 else 0.5)
                    zz = zf * rc if zf > 0.0 else (zf * hang * jag if j == len(prof) - 2 else zf * hang)
                    ring.append(B.vert(top + Vector((rf * rc * lump * math.cos(a), rf * rc * lump * math.sin(a), zz))))
                rings.append(ring)
            apex = B.vert(top + Vector((0.0, 0.0, prof[0][1] * rc)))
            for k in range(M):
                B.face((apex, rings[0][k], rings[0][(k + 1) % M]), FOLIAGE_IDX, tone, P_CROWN, ident)
            for r0, r1 in zip(rings, rings[1:]):
                for k in range(M):
                    q = (k + 1) % M
                    B.face((r0[k], r1[k], r1[q], r0[q]), FOLIAGE_IDX, tone, P_CROWN, ident)
            B.face(tuple(reversed(rings[-1])), FOLIAGE_IDX, tone, P_CROWN, ident, cap=1)


def add_reeds(B, plan, G, flags):
    """Each clump a dense sheaf of blades fanning out from its foot, each
    blade a thin three-sided spire."""
    lift = FLOAT_REEDS if flags.get("float_reeds") else 0.0
    for n, c in enumerate(plan["reeds"]):
        x, y = c["x"], c["y"]
        for k in range(c["n"]):
            h1 = hash01(c["seed"], k, 1)
            h2 = hash01(c["seed"], k, 2)
            h3 = hash01(c["seed"], k, 3)
            ang = TAU * (k / c["n"] + 0.35 * h1)
            rr = REED_SPREAD * math.sqrt(0.08 + 0.92 * h2)
            fx, fy = x + rr * math.cos(ang), y + rr * math.sin(ang)
            g = G.z(fx, fy)
            if g is None:
                continue
            h = REED_H[0] + (REED_H[1] - REED_H[0]) * (0.55 * c["h"] + 0.45 * h3) * (1.0 - 0.35 * rr / REED_SPREAD)
            # the outer blades lean out further
            lean = 0.06 + 0.40 * (rr / REED_SPREAD) ** 1.5
            d = Vector((math.cos(ang) * lean, math.sin(ang) * lean, 1.0)).normalized()
            foot = Vector((fx, fy, g - REED_ROOT + lift))
            rad = 0.0010 + 0.0004 * h1
            e1, e2 = perp_basis(d)
            base = []
            for m in range(3):
                a = TAU * m / 3 + ang
                v = B.vert(foot + rad * (e1 * math.cos(a) + e2 * math.sin(a)))
                v[B.blade] = 0.0
                base.append(v)
            tip = B.vert(foot + d * (h + REED_ROOT))
            tip[B.blade] = 1.0
            tone = 0.1 + 0.8 * hash01(c["seed"], k, 4)
            ident = 1000 + n * 32 + k
            for m in range(3):
                B.face((base[m], base[(m + 1) % 3], tip), REED_IDX, tone, P_REED, ident)
            B.face(tuple(reversed(base)), REED_IDX, tone, P_REED, ident, cap=1)


def add_logs(B, plan, G, W, flags):
    """Drift logs, bleached: afloat in the water to about half their
    girth, or stranded on the bars and beaches."""
    sink = SINK_LOGS if flags.get("sink_logs") else 0.0
    for n, lg in enumerate(plan["logs"]):
        c, s = math.cos(lg["yaw"]), math.sin(lg["yaw"])
        half = 0.5 * lg["len"]
        r = lg["r"]
        pts = []
        for k in range(5):
            t = -1.0 + 2.0 * k / 4
            bow = 0.004 * lg["bend"] * (1.0 - t * t)
            pts.append(Vector((lg["x"] + c * half * t - s * bow, lg["y"] + s * half * t + c * bow, 0.0)))
        radii = [r * (1.12 - 0.22 * k / 4) for k in range(5)]
        if lg["float"]:
            wz = W.z(lg["x"], lg["y"])
            z0 = (SEA_Z if wz is None else wz) - 0.12 * r - sink
            part = P_FLOAT
        else:
            ring_pts = [p + Vector((0.0, 0.0, rr * math.cos(TAU * j / 8))) + Vector((-s, c, 0.0)) * rr * math.sin(TAU * j / 8)
                        for p, rr in zip(pts, radii) for j in range(8)]
            z0 = seat(ring_pts, G, 0.0) + 0.0
            # half-buried in the sand, sealed all round
            z0 = min(z0, min(G.z(p.x, p.y) for p in pts) - 0.30 * r) - PERCH_BAND
            part = P_LOG
        pts = [p + Vector((0.0, 0.0, z0)) for p in pts]
        tube(B, pts, radii, 8, TIMBER_IDX, 0.62 + 0.3 * lg["tone"], part, 300 + n)


def add_boat(B, plan, W, flags):
    """A small flat-bottomed boat, lofted from six sections: a hull with a
    thickness, open above, its gunwales and its dark inside, a thwart across
    it, floating."""
    bt = plan["boat"]
    sink = SINK_LOGS if flags.get("sink_logs") else 0.0
    L, beam = bt["len"], bt["beam"]
    H = 0.010
    c, s = math.cos(bt["yaw"]), math.sin(bt["yaw"])
    wz = W.z(*bt["c"])
    z0 = (SEA_Z if wz is None else wz) - 0.0040 - sink

    def at(u, vx, vz):
        return Vector((bt["c"][0] + c * u * L - s * vx, bt["c"][1] + s * u * L + c * vx, z0 + vz))

    secs = []
    for u, wf, zf in ((-0.50, 0.66, 0.96), (-0.36, 0.92, 1.0), (-0.10, 1.0, 1.0),
                      (0.18, 0.92, 1.02), (0.36, 0.62, 1.08), (0.50, 0.12, 1.20)):
        hw = 0.5 * beam * wf
        t_ = min(0.0016, 0.35 * hw)
        # a shallow vee to the bottom, inside and out: no flat panel to lie
        # in another shell's plane
        prof = ((-0.62 * hw, 0.0008), (-hw, 0.50 * H), (-hw * 1.05, H * zf), (-(hw * 1.05 - t_), H * zf),
                (-(hw - t_), 0.50 * H), (-(0.62 * hw - t_), 0.0022), (0.0, 0.0016),
                ((0.62 * hw - t_), 0.0022), ((hw - t_), 0.50 * H), ((hw * 1.05 - t_), H * zf),
                (hw * 1.05, H * zf), (hw, 0.50 * H), (0.62 * hw, 0.0008), (0.0, 0.0))
        secs.append([B.vert(at(u, vx, vz)) for vx, vz in prof])
    m = len(secs[0])
    for r0, r1 in zip(secs, secs[1:]):
        for j in range(m):
            q = (j + 1) % m
            # the inside (between the gunwales' inner edges) dark and worn
            tone = 0.12 if 3 <= j <= 8 else 0.36
            B.face((r0[j], r0[q], r1[q], r1[j]), TIMBER_IDX, tone, P_FLOAT, 400)
    # each end closed by quads across the hull's wall, outer to inner: the
    # bow's section is a few millimetres wide, and as one n-gon its
    # triangulation differs by Blender version (4.5 cuts a zero-area sliver)
    wall = ((0, 1, 4, 5), (1, 2, 3, 4), (13, 0, 5, 6), (12, 13, 6, 7), (11, 12, 7, 8), (10, 11, 8, 9))
    for q in wall:
        B.face(tuple(secs[0][i] for i in reversed(q)), TIMBER_IDX, 0.36, P_FLOAT, 400, cap=1)
        B.face(tuple(secs[-1][i] for i in q), TIMBER_IDX, 0.36, P_FLOAT, 400, cap=2)
    # a thwart across the middle, its ends let into the sides
    th = 0.5 * beam * 0.98 - 0.0012
    box(B, tuple(at(-0.02, 0.0, 0.70 * H)), (0.0045, th, 0.0009), bt["yaw"], TIMBER_IDX, 0.45, P_BUILT, 401)


def add_built(B, T, plan, G, flags):
    """The fisherman's hut on six stilts in the bay, its jetty to the shore
    on pairs of posts, and the fish weir's stakes. Every post's foot is
    sunk in the bed; every deck stands clear of the water."""
    lift = LIFT_HUT if flags.get("lift_hut") else 0.0
    hut = plan["hut"]
    caps = []   # (x, y, z) of every post's foot and top so far
    hx, hy = hut["c"]
    yaw = hut["yaw"]
    R = Matrix.Rotation(yaw, 3, "Z")
    ident = 500

    def post(x, y, ztop, r, tone):
        nonlocal ident
        g = G.z(x, y)
        g = SEA_Z - 0.01 if g is None else g
        # each post's foot and top stepped off its neighbours', so no two
        # caps share a plane
        zf, zt = g - POST_ROOT, ztop
        while any(math.hypot(x - a, y - b) < 0.06 and abs(zf - c) < 4e-4 for a, b, c in caps):
            zf -= 5e-4
        while any(math.hypot(x - a, y - b) < 0.06 and abs(zt - c) < 4e-4 for a, b, c in caps):
            zt -= 5e-4
        caps.extend(((x, y, zf), (x, y, zt)))
        foot = Vector((x, y, zf + lift))
        top = Vector((x, y, zt + lift))
        tube(B, (foot, 0.5 * (foot + top), top), (r, r * 0.95, r * 0.9), 6, TIMBER_IDX, tone, P_POST, ident,
             phase=TAU * hash01(ident, 3, 9))
        ident += 1

    deck = SEA_Z + 0.020
    for ix in (-1, 0, 1):
        for iy in (-1, 1):
            p = Vector((hx, hy, 0.0)) + R @ Vector((ix * 0.036, iy * 0.028, 0.0))
            post(p.x, p.y, deck - 0.0008, 0.0026, 0.30)
    box(B, (hx, hy, deck - 0.0025 + lift), (0.049, 0.039, 0.0025), yaw, TIMBER_IDX, 0.45, P_BUILT, 600)
    body_c = (hx, hy, deck + 0.0175 + lift)
    box(B, body_c, (0.034, 0.026, 0.0185), yaw, TIMBER_IDX, 0.40, P_BUILT, 601)
    # the doorway and a window, dark, on the side facing the jetty and the front
    d = Vector((hx, hy, 0.0)) + R @ Vector((0.0, -0.0262, 0.0))
    box(B, (d.x, d.y, deck + 0.0125 + lift), (0.0075, 0.0009, 0.0115), yaw, TIMBER_IDX, 0.02, P_BUILT, 602)
    wv = Vector((hx, hy, 0.0)) + R @ Vector((0.0343, 0.004, 0.0))
    box(B, (wv.x, wv.y, deck + 0.022 + lift), (0.0009, 0.0065, 0.0055), yaw, TIMBER_IDX, 0.02, P_BUILT, 603)
    # a thatched gable roof, its ridge along the hut, overhanging
    zt = deck + 0.035 + lift
    L, Wd, rise, oh = 0.034 + 0.009, 0.026 + 0.010, 0.020, 0.0035
    corners = []
    for ix in (-1, 1):
        for iy in (-1, 1):
            for dz in (0.0, oh):
                p = Vector((hx, hy, 0.0)) + R @ Vector((ix * L, iy * Wd, 0.0))
                corners.append(Vector((p.x, p.y, zt - 0.003 + dz)))
    ridge = []
    for ix in (-1, 1):
        p = Vector((hx, hy, 0.0)) + R @ Vector((ix * L, 0.0, 0.0))
        ridge.append(Vector((p.x, p.y, zt + rise)))
    # an eave-to-ridge prism with a thickness: outer and inner skins
    vs = {}
    for ix in (0, 1):
        for iy in (0, 1):
            for k in (0, 1):
                vs[(ix, iy, k)] = B.vert(corners[ix * 4 + iy * 2 + k])
    rv = {(ix, k): B.vert(ridge[ix] + Vector((0.0, 0.0, oh * k))) for ix in (0, 1) for k in (0, 1)}
    tone = 0.97
    for iy in (0, 1):
        # outer slope (upper skin k=1), inner (k=0)
        a, b = vs[(0, iy, 1)], vs[(1, iy, 1)]
        top = (rv[(1, 1)], rv[(0, 1)])
        quad = (a, b, top[0], top[1]) if iy == 0 else (b, a, top[1], top[0])
        B.face(quad, REED_IDX, tone, P_BUILT, 604)
        a, b = vs[(0, iy, 0)], vs[(1, iy, 0)]
        top = (rv[(1, 0)], rv[(0, 0)])
        quad = (b, a, top[1], top[0]) if iy == 0 else (a, b, top[0], top[1])
        B.face(quad, REED_IDX, tone, P_BUILT, 604)
        # the eave's edge
        e = (vs[(0, iy, 0)], vs[(1, iy, 0)], vs[(1, iy, 1)], vs[(0, iy, 1)])
        B.face(e if iy == 0 else tuple(reversed(e)), REED_IDX, tone, P_BUILT, 604)
    for ix in (0, 1):
        # the gable ends: a ring of six verts
        ring = (vs[(ix, 0, 0)], vs[(ix, 0, 1)], rv[(ix, 1)], vs[(ix, 1, 1)], vs[(ix, 1, 0)], rv[(ix, 0)])
        B.face(ring if ix == 1 else tuple(reversed(ring)), REED_IDX, tone, P_BUILT, 604)
    # the jetty: from the shore to the hut's platform, a plank deck on posts
    sx, sy = hut["shore"]
    dx, dy = hx - sx, hy - sy
    ln = math.hypot(dx, dy)
    tx, ty = dx / ln, dy / ln
    jl = ln - 0.040
    jc = (sx + tx * 0.5 * jl, sy + ty * 0.5 * jl)
    jz = SEA_Z + 0.0155
    box(B, (jc[0], jc[1], jz - 0.00175 + lift), (0.5 * jl, 0.0105, 0.00175), math.atan2(ty, tx),
        TIMBER_IDX, 0.55, P_BUILT, 605)
    npost = max(2, int(jl / 0.042) + 1)
    for k in range(npost):
        f = 0.03 + 0.94 * k / (npost - 1)
        px, py = sx + tx * f * jl, sy + ty * f * jl
        for side in (-1.0, 1.0):
            post(px - ty * side * 0.0085, py + tx * side * 0.0085, jz - 0.0007, 0.0018, 0.25)
    # the weir's stakes
    for k, (x, y, h) in enumerate(plan["weir"]):
        post(x, y, SEA_Z + h, 0.0016, 0.20 + 0.3 * hash01(k, 1, 7))
    # and the wattle hurdles woven along each arm between them, standing
    # out of the water as one dark fence line: a V of bare stakes read as
    # scattered debris
    stakes = plan["weir"]
    arm = len(stakes) // 2
    for side in range(2):
        (x0, y0, _h0), (x1, y1, _h1) = stakes[side * arm], stakes[side * arm + arm - 1]
        ln = math.hypot(x1 - x0, y1 - y0)
        box(B, (0.5 * (x0 + x1), 0.5 * (y0 + y1), SEA_Z + 0.0012 + lift), (0.5 * ln + 0.002, 0.0010, 0.0052),
            math.atan2(y1 - y0, x1 - x0), TIMBER_IDX, 0.16, P_BUILT, 610 + side)


def break_coplanar(B, parts, passes=10):
    """Blades, lumps, trunks, posts and logs are many small faces in every
    direction; now and then one lands in another shell's plane. Turn the
    shell's piece a few degrees about the vertical through its lowest point,
    or drop it a fraction of a millimetre where the shared plane is level,
    until none does."""
    bm = B.bm
    for pass_ in range(passes):
        bm.normal_update()
        bm.verts.index_update()
        faces = list(bm.faces)
        key = [(f[B.part], f[B.ident]) for f in faces]
        cent = [f.calc_center_median() for f in faces]
        kd = KDTree(len(faces))
        for i, c in enumerate(cent):
            kd.insert(c, i)
        kd.balance()
        bad = {}
        for i, f in enumerate(faces):
            if key[i][0] not in parts:
                continue
            for _co, j, _d in kd.find_range(cent[i], COPLANAR_CENTRE_MAX):
                if key[j] == key[i]:
                    continue
                g = faces[j]
                if abs(abs(f.normal.dot(g.normal)) - 1.0) > 4.0 * COPLANAR_NORMAL_EPS:
                    continue
                # either face's normal: the audit measures along the one it meets first
                if min(abs(f.normal.dot(cent[j] - cent[i])), abs(g.normal.dot(cent[j] - cent[i])))                         > 4.0 * COPLANAR_PLANE_EPS:
                    continue
                # of two movable shells only one moves, so the pair parts
                k = max(key[i], key[j]) if key[j][0] in parts else key[i]
                bad[k] = bad.get(k, False) or abs(f.normal.z) > 0.99
        if not bad:
            return
        for k in sorted(bad):
            vs = {v for f, kk in zip(faces, key) if kk == k for v in f.verts}
            if bad[k]:
                for v in vs:
                    v.co.z -= 0.0010
                continue
            root = min(vs, key=lambda v: v.co.z).co.copy()
            R = Matrix.Rotation(math.radians(3.0 + 2.0 * pass_), 3, "Z")
            for v in vs:
                v.co = root + R @ (v.co - root)


def build_mesh(name, T, plan, detail_="low", **flags):
    bm = bmesh.new()
    try:
        B = Builder(bm)
        n = TILE_N[detail_]
        add_tile(B, T, n)
        bm.normal_update()
        G = Ground(BVHTree.FromBMesh(bm))
        add_water(B, T, plan, n, flags)
        bm.normal_update()
        water_faces = [f for f in bm.faces if f[B.part] == P_WATER and f[B.zone] > 0.5]
        vmap = {}
        wverts, wfaces = [], []
        for f in water_faces:
            idx = []
            for v in f.verts:
                if v not in vmap:
                    vmap[v] = len(wverts)
                    wverts.append(v.co.copy())
                idx.append(vmap[v])
            wfaces.append(idx)
        W = Ground(BVHTree.FromPolygons(wverts, wfaces))
        add_built(B, T, plan, G, flags)
        add_boat(B, plan, W, flags)
        add_logs(B, plan, G, W, flags)
        add_reeds(B, plan, G, flags)
        add_trees(B, plan, G, flags)
        triangulate_ngons(bm)
        break_coplanar(B, (P_REED, P_TRUNK, P_CROWN, P_LOG, P_FLOAT, P_POST))
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        # Everything smooth-shaded, with every material boundary and every
        # fold sharper than its crease a hard edge.
        crease = {TERRAIN_IDX: 50.0, WATER_IDX: 30.0, REED_IDX: 75.0, TIMBER_IDX: 35.0,
                  BARK_IDX: 70.0, FOLIAGE_IDX: 70.0, PLINTH_IDX: 30.0}
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
    and the delta's plain in seven fans from the apex, each from where it
    comes in over the back edge out to the coast. Boats sail the water;
    units walk the land."""
    groups = [[Vector((sx * HALF, sy * HALF, z)) for sx in (-1, 1) for sy in (-1, 1) for z in (0.0, SEA_Z)]]
    # the bearings the tile spans from the apex, back corners to back corners
    th0 = math.atan2(-HALF - APEX[1], -HALF - APEX[0])
    th1 = math.atan2(-HALF - APEX[1], HALF - APEX[0])
    lo = math.atan2(HALF - APEX[1], -HALF - APEX[0])
    hi = math.atan2(HALF - APEX[1], HALF - APEX[0])
    del th0, th1
    fans = 7
    rays = 5
    for f in range(fans):
        pts = []
        for k in range(rays):
            th = lo + (hi - lo) * (f + k / (rays - 1)) / fans
            ux, uy = math.cos(th), math.sin(th)
            # the ray enters the tile through the back edge, leaves at the coast or a side
            r_in = (HALF - APEX[1]) / uy if uy < -1e-6 else 0.0
            r_side = min(((HALF if ux > 0 else -HALF) - APEX[0]) / ux if abs(ux) > 1e-6 else 9.0,
                         (-HALF - APEX[1]) / uy if uy < -1e-6 else 9.0)
            r_out = min(T.coast_r(th), r_side)
            if r_out <= r_in:
                continue
            for g in (0.0, 0.33, 0.66, 1.0):
                r = r_in + (r_out - r_in) * g
                x = min(max(APEX[0] + r * ux, -HALF), HALF)
                y = min(max(APEX[1] + r * uy, -HALF), HALF)
                z = T.ground(x, y, rim=False)
                pts.append(Vector((x, y, SEA_Z)))
                pts.append(Vector((x, y, max(z, SEA_Z + 0.002))))
        if len(pts) >= 8:
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


def terrain_material():
    mat, nt, bsdf, coord = surface("DeltaGround")
    # The delta's skin by its height over the local water: dark wet mud at
    # the water's edge, then a mosaic of marsh — sedge, rush, wet meadow,
    # rusty patches, standing water in the hollows — and drier, paler silt
    # loam with grass on the levee crests and the older plain behind; sand
    # on the bars and the lobes' beaches; under the water, sand in the
    # shallows going to grey silt.
    rel = attr(nt, "Rel")
    sand = attr(nt, "Sand")
    big = noise(nt, coord, 2.2, 3.0, 0.55)
    patch = noise(nt, mapping(nt, coord, scale=(1.0, 1.0, 1.0)), 6.5, 4.0, 0.6)
    fine = noise(nt, coord, 55.0, 3.0, 0.6)
    marsh = ramp(nt, patch, ((0.25, (0.035, 0.065, 0.028)), (0.40, (0.060, 0.100, 0.040)),
                             (0.52, (0.100, 0.125, 0.050)), (0.62, (0.150, 0.125, 0.065)),
                             (0.74, (0.085, 0.105, 0.045)), (0.85, (0.050, 0.080, 0.035))))
    meadow = ramp(nt, big, ((0.30, (0.150, 0.250, 0.050)), (0.48, (0.220, 0.300, 0.065)),
                            (0.62, (0.300, 0.330, 0.100)), (0.78, (0.350, 0.330, 0.140))))
    dry = remap(nt, math_node(nt, "ADD", rel, mul(nt, big, 0.004)), 0.0070, 0.0110, 0.0, 1.0)
    col = mix_color(nt, marsh, meadow, dry)
    # the lower delta: salt marsh, grey-olive and purple-brown, in drifts
    salt = ramp(nt, noise(nt, coord, 9.0, 3.0, 0.6), ((0.30, (0.15, 0.17, 0.08)), (0.50, (0.21, 0.20, 0.11)),
                                                       (0.65, (0.20, 0.13, 0.11)), (0.80, (0.25, 0.22, 0.12))))
    low = mul(nt, attr(nt, "Silt"), remap(nt, big, 0.25, 0.55, 0.55, 1.0))
    col = mix_color(nt, col, salt, mul(nt, low, math_node(nt, "SUBTRACT", 1.0, mul(nt, dry, 0.7))))
    # big beds of dark rush and pale reed-straw across the marsh
    beds = noise(nt, coord, 3.4, 3.0, 0.5)
    col = mix_color(nt, col, (0.050, 0.085, 0.030), mul(nt, remap(nt, beds, 0.60, 0.70, 0.0, 0.75),
                                                        math_node(nt, "SUBTRACT", 1.0, dry)))
    col = mix_color(nt, col, (0.33, 0.29, 0.14), mul(nt, remap(nt, beds, 0.36, 0.28, 0.0, 0.55),
                                                     math_node(nt, "SUBTRACT", 1.0, dry)))
    # rush tussocks and sedge speckle in the marsh
    tuss = voronoi(nt, coord, 85.0)
    wetland = remap(nt, rel, 0.0085, 0.0055, 0.0, 1.0)
    col = mix_color(nt, col, (0.035, 0.070, 0.022), mul(nt, remap(nt, tuss, 0.32, 0.06, 0.0, 0.65), wetland))
    col = mix_color(nt, col, (0.30, 0.25, 0.11), mul(nt, remap(nt, voronoi(nt, coord, 140.0), 0.08, 0.02, 0.0, 0.5),
                                                     wetland))
    col = mix_color(nt, col, (0.04, 0.07, 0.025), remap(nt, fine, 0.35, 0.65, 0.30, 0.0))
    # the upper plain farmed, as a lowland patchwork seen from the air:
    # strips of fields on a slanting grid, the field lines staggered and the
    # fields of uneven width strip by strip, each its own crop — winter
    # wheat, young barley, ripe gold, pale stubble, fresh-ploughed brown,
    # fallow — drilled in rows that run along or across it, its tone
    # varying across it, and every field parted from the next by a
    # hedgerow of dark bushes, gapped here and there
    xyz = coord_xyz(nt, coord)
    ca, sa = math.cos(0.38), math.sin(0.38)
    u = math_node(nt, "ADD", mul(nt, xyz["X"], ca), mul(nt, xyz["Y"], sa))
    v = math_node(nt, "SUBTRACT", mul(nt, xyz["Y"], ca), mul(nt, xyz["X"], sa))
    fv = mul(nt, v, 1.0 / 0.080)
    jv = math_node(nt, "FLOOR", fv, 0.0)

    def white1(w):
        node = nt.nodes.new("ShaderNodeTexWhiteNoise")
        node.noise_dimensions = "1D"
        nt.links.new(w, node.inputs["W"])
        return node.outputs["Value"]

    wdt = math_node(nt, "ADD", 0.080, mul(nt, white1(jv), 0.075))
    shift = mul(nt, white1(math_node(nt, "ADD", jv, 17.3)), wdt)
    fu = math_node(nt, "DIVIDE", math_node(nt, "ADD", u, shift), wdt)
    iu = math_node(nt, "FLOOR", fu, 0.0)
    cell = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(iu, cell.inputs["X"])
    nt.links.new(jv, cell.inputs["Y"])
    wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "3D"
    nt.links.new(cell.outputs["Vector"], wn.inputs["Vector"])
    pick = wn.outputs["Value"]
    crop = ramp(nt, pick, ((0.00, (0.060, 0.130, 0.030)), (0.13, (0.130, 0.220, 0.045)),
                           (0.27, (0.200, 0.270, 0.060)), (0.40, (0.400, 0.320, 0.120)),
                           (0.52, (0.420, 0.360, 0.200)), (0.63, (0.165, 0.100, 0.055)),
                           (0.76, (0.200, 0.200, 0.090)), (0.88, (0.330, 0.300, 0.130)),
                           (0.95, (0.100, 0.180, 0.040))))
    crop.node.color_ramp.interpolation = "CONSTANT"
    wn3 = nt.nodes.new("ShaderNodeTexWhiteNoise")
    wn3.noise_dimensions = "3D"
    nt.links.new(mapping(nt, cell.outputs["Vector"], scale=(2.3, 0.7, 1.0)), wn3.inputs["Vector"])
    pick2 = wn3.outputs["Value"]
    # the drill rows, along the strip or across it by field; deeper furrows
    # in the ploughed ones
    across = math_node(nt, "GREATER_THAN", pick2, 0.5)
    rowc = math_node(nt, "ADD", u, mul(nt, across, math_node(nt, "SUBTRACT", v, u)))
    rows = math_node(nt, "SINE", mul(nt, rowc, TAU * 95.0), 0.0)
    plough = mul(nt, remap(nt, pick, 0.62, 0.64, 0.0, 1.0), remap(nt, pick, 0.76, 0.74, 0.0, 1.0))
    crop = mix_color(nt, crop, (0.045, 0.040, 0.022), mul(nt, remap(nt, rows, 0.1, 1.0, 0.0, 1.0),
                                                         math_node(nt, "ADD", 0.22, mul(nt, plough, 0.30))))
    # each field's tone drifts across it, wetter and drier ground
    drift = noise(nt, coord, 22.0, 3.0, 0.55)
    crop = mix_color(nt, crop, (0.05, 0.075, 0.025), remap(nt, drift, 0.40, 0.70, 0.0, 0.30))
    crop = mix_color(nt, crop, (0.44, 0.40, 0.22), remap(nt, drift, 0.40, 0.25, 0.0, 0.18))
    # hedgerows: in metres off the field's edge, dark bushes in a line,
    # gapped where a gate or a lane runs through
    fr_u = math_node(nt, "FRACT", fu, 0.0)
    edge_u = mul(nt, math_node(nt, "MINIMUM", fr_u, math_node(nt, "SUBTRACT", 1.0, fr_u)), wdt)
    fr_v = math_node(nt, "FRACT", fv, 0.0)
    edge_v = mul(nt, math_node(nt, "MINIMUM", fr_v, math_node(nt, "SUBTRACT", 1.0, fr_v)), 0.080)
    bushes = voronoi(nt, coord, 190.0)
    wob = mul(nt, bushes, 0.0040)
    hedge = math_node(nt, "MAXIMUM", remap(nt, math_node(nt, "ADD", edge_u, wob), 0.0060, 0.0036, 0.0, 1.0),
                      remap(nt, math_node(nt, "ADD", edge_v, wob), 0.0060, 0.0036, 0.0, 1.0))
    hedge = mul(nt, hedge, remap(nt, noise(nt, coord, 14.0, 2.0, 0.5), 0.33, 0.39, 0.0, 1.0))
    hedge_col = ramp(nt, bushes, ((0.05, (0.075, 0.130, 0.035)), (0.45, (0.030, 0.062, 0.018)),
                                  (0.80, (0.012, 0.025, 0.008))))
    # the crops a little muted toward the grass round them, as seen from
    # height through haze, then the hedges over them
    crop = mix_color(nt, crop, (0.17, 0.21, 0.07), 0.18)
    crop = mix_color(nt, crop, hedge_col, hedge)
    # whole fields in or out: each field's own distance from the apex, a
    # little jittered, against the upper plain's reach
    cu = math_node(nt, "SUBTRACT", mul(nt, math_node(nt, "ADD", iu, 0.5), wdt), shift)
    cv = mul(nt, math_node(nt, "ADD", jv, 0.5), 0.080)
    cx = math_node(nt, "SUBTRACT", mul(nt, cu, ca), mul(nt, cv, sa))
    cy = math_node(nt, "ADD", mul(nt, cu, sa), mul(nt, cv, ca))
    rc_ = math_node(nt, "SQRT", math_node(nt, "ADD", math_node(nt, "POWER", math_node(nt, "SUBTRACT", cx, APEX[0]), 2.0),
                                          math_node(nt, "POWER", math_node(nt, "SUBTRACT", cy, APEX[1]), 2.0)), 0.0)
    wn2 = nt.nodes.new("ShaderNodeTexWhiteNoise")
    wn2.noise_dimensions = "3D"
    nt.links.new(mapping(nt, cell.outputs["Vector"], scale=(1.7, 1.3, 1.0)), wn2.inputs["Vector"])
    reach = math_node(nt, "SUBTRACT", math_node(nt, "ADD", FARM_R[0], mul(nt, wn2.outputs["Value"], 0.25)), rc_)
    farm = mul(nt, remap(nt, reach, -0.001, 0.001, 0.0, 1.0), remap(nt, attr(nt, "Farm"), 0.55, 0.75, 0.0, 1.0))
    col = mix_color(nt, col, crop, farm)
    # dark wet mud at the water's edge, glistening
    mud = remap(nt, math_node(nt, "ADD", rel, mul(nt, noise(nt, coord, 9.0, 2.0, 0.5), 0.0012)),
                0.0034, 0.0010, 0.0, 1.0)
    mud_col = ramp(nt, fine, ((0.3, (0.060, 0.050, 0.035)), (0.7, (0.105, 0.085, 0.058))))
    col = mix_color(nt, col, mud_col, mud)
    # sand
    sand_dry = ramp(nt, fine, ((0.3, (0.36, 0.30, 0.19)), (0.7, (0.45, 0.38, 0.25))))
    sand_col = mix_color(nt, sand_dry, (0.24, 0.20, 0.13), remap(nt, rel, 0.0030, 0.0004, 0.0, 0.85))
    ripples = math_node(nt, "SINE", math_node(nt, "MULTIPLY", math_node(
        nt, "ADD", coord_xyz(nt, coord)["X"], mul(nt, noise(nt, coord, 6.0, 2.0, 0.5), 0.05)), 520.0), 0.0)
    sand_col = mix_color(nt, sand_col, (0.20, 0.16, 0.10), mul(nt, remap(nt, ripples, 0.6, 1.0, 0.0, 0.25),
                                                                 remap(nt, rel, 0.002, 0.0, 0.0, 1.0)))
    col = mix_color(nt, col, sand_col, remap(nt, sand, 0.15, 0.65, 0.0, 1.0))
    # under the water: sand in the shallows, silt deeper
    sub = remap(nt, rel, 0.0, -0.004, 0.0, 1.0)
    bed = ramp(nt, remap(nt, rel, -0.002, -0.022, 0.0, 1.0),
               ((0.0, (0.30, 0.27, 0.18)), (0.5, (0.20, 0.19, 0.14)), (1.0, (0.12, 0.12, 0.10))))
    col = mix_color(nt, col, bed, sub)
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, mud, 0.0, 1.0, 0.92, 0.30), bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.30
    add_bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "ADD", mul(nt, fine, 0.6), mul(nt, tuss, 0.5)),
                                 mul(nt, hedge, farm, 1.5)), 0.35, 0.003)
    return mat


def water_material():
    mat, nt, bsdf, coord = surface("DeltaWater")
    # The sea clear, from pale shallows over the sand to deep blue; the
    # channels laden with silt, olive and darker where they run deep; their
    # load fanning out of the mouths in tan plumes that swirl and fade into
    # the sea; the ponds peaty and still.
    # The depth is read off the seabed smoothly, one long ramp from the
    # turquoise over the sand to the deep blue offshore; the sheen is kept
    # soft, so the swell's facets do not mirror the dark studio back as
    # hard-edged blotches over it.
    depth = remap(nt, math_node(nt, "MULTIPLY", attr(nt, "Rel"), -1.0), 0.0, 0.034, 0.0, 1.0)
    sea = ramp(nt, depth, ((0.00, (0.22, 0.50, 0.42)), (0.12, (0.11, 0.42, 0.42)), (0.30, (0.045, 0.30, 0.36)),
                           (0.55, (0.020, 0.18, 0.28)), (0.80, (0.010, 0.10, 0.20)), (1.00, (0.007, 0.065, 0.15))))
    # the plume: a broad, soft-edged tongue, its load swirled a little
    swirl = noise(nt, mapping(nt, coord, scale=(1.0, 1.0, 1.0)), 3.0, 2.0, 0.45)
    load = attr(nt, "Silt")
    silt = mul(nt, load, remap(nt, swirl, 0.30, 0.70, 0.82, 1.12))
    chan = ramp(nt, depth, ((0.0, (0.200, 0.190, 0.105)), (0.20, (0.120, 0.150, 0.090)),
                            (0.45, (0.065, 0.105, 0.075))))
    # tan and opaque at the mouth, a milky jade where it thins over the sea
    plume = mix_color(nt, (0.24, 0.31, 0.19), (0.29, 0.25, 0.13), remap(nt, silt, 0.20, 0.75, 0.0, 1.0))
    plume = mix_color(nt, plume, chan, remap(nt, load, 0.92, 1.0, 0.0, 1.0))
    fade = remap(nt, silt, 0.02, 0.50, 0.0, 1.0)
    col = mix_color(nt, sea, plume, math_node(nt, "POWER", fade, 0.7))
    # the ponds dark and peaty, a little green
    col = mix_color(nt, col, (0.030, 0.055, 0.045), remap(nt, attr(nt, "Open"), 1.5, 1.9, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    # the silty channels and ponds a little duller than the clear sea
    nt.links.new(remap(nt, load, 0.5, 1.0, 0.16, 0.20), bsdf.inputs["Roughness"])
    bsdf.inputs["IOR"].default_value = 1.33
    nt.links.new(remap(nt, load, 0.5, 1.0, 0.28, 0.12), bsdf.inputs["Specular IOR Level"])
    ruffle = noise(nt, mapping(nt, coord, scale=(1.0, 1.6, 1.0)), 34.0, 3.0, 0.5)
    add_bump(nt, bsdf, ruffle, 0.05, 0.002)
    return mat


def reed_material():
    mat, nt, bsdf, coord = surface("Reed")
    # Common reed: green at the foot, straw-gold up the blade, a purple-brown
    # plume at the tip; the hut's thatch (tone near 1) weathered straw.
    tone = attr(nt, "Tone")
    up = attr(nt, "Blade")
    stem = ramp(nt, tone, ((0.0, (0.17, 0.25, 0.06)), (0.5, (0.27, 0.30, 0.08)), (0.9, (0.36, 0.32, 0.12))))
    gold = ramp(nt, tone, ((0.0, (0.46, 0.40, 0.17)), (0.6, (0.55, 0.45, 0.20)), (0.9, (0.50, 0.38, 0.16))))
    col = mix_color(nt, stem, gold, remap(nt, up, 0.25, 0.75, 0.0, 1.0))
    col = mix_color(nt, col, (0.20, 0.12, 0.08), mul(nt, remap(nt, up, 0.82, 0.95, 0.0, 1.0),
                                                     remap(nt, tone, 0.3, 0.6, 0.0, 1.0)))
    straws = noise(nt, mapping(nt, coord, scale=(60.0, 60.0, 4.0)), 8.0, 3.0, 0.6)
    thatch = ramp(nt, straws, ((0.3, (0.24, 0.19, 0.11)), (0.7, (0.42, 0.34, 0.19))))
    col = mix_color(nt, col, thatch, remap(nt, tone, 0.93, 0.95, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.72
    add_bump(nt, bsdf, straws, 0.35, 0.002)
    translucent(nt, bsdf, (0.30, 0.28, 0.08), 0.12)
    return mat


def timber_material():
    mat, nt, bsdf, coord = surface("Timber")
    # Weathered planks and posts, silver-brown; drift logs bleached pale;
    # the doorway and window dark (tone near 0).
    tone = attr(nt, "Tone")
    col = ramp(nt, tone, ((0.0, (0.020, 0.016, 0.012)), (0.08, (0.05, 0.04, 0.03)), (0.25, (0.17, 0.12, 0.075)),
                          (0.45, (0.27, 0.21, 0.14)), (0.62, (0.42, 0.38, 0.32)), (1.0, (0.62, 0.58, 0.50))))
    grain = noise(nt, mapping(nt, coord, scale=(3.0, 3.0, 60.0)), 12.0, 4.0, 0.6)
    planks = math_node(nt, "SINE", math_node(nt, "MULTIPLY", coord_xyz(nt, coord)["X"], 900.0), 0.0)
    col = mix_color(nt, col, (0.08, 0.06, 0.045), remap(nt, grain, 0.35, 0.70, 0.0, 0.45))
    col = mix_color(nt, col, (0.06, 0.045, 0.03), mul(nt, remap(nt, planks, 0.85, 1.0, 0.0, 0.35),
                                                      remap(nt, tone, 0.40, 0.50, 0.0, 1.0)))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    add_bump(nt, bsdf, grain, 0.4, 0.002)
    return mat


def bark_material():
    mat, nt, bsdf, coord = surface("Bark")
    tone = attr(nt, "Tone")
    col = ramp(nt, tone, ((0.0, (0.12, 0.10, 0.075)), (1.0, (0.24, 0.20, 0.15))))
    ridges = noise(nt, mapping(nt, coord, scale=(40.0, 40.0, 3.0)), 6.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.05, 0.04, 0.03), remap(nt, ridges, 0.4, 0.7, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    add_bump(nt, bsdf, ridges, 0.5, 0.002)
    return mat


def foliage_material():
    mat, nt, bsdf, coord = surface("Foliage")
    # poplars (tone under 0.5) deep green; willows silvery grey-green with
    # the pale undersides showing, one or two yellowing
    tone = attr(nt, "Tone")
    nz = normal_xyz(nt)["Z"]
    col = ramp(nt, tone, ((0.00, (0.030, 0.100, 0.030)), (0.30, (0.050, 0.140, 0.040)),
                          (0.50, (0.10, 0.20, 0.07)), (0.55, (0.22, 0.31, 0.13)),
                          (0.80, (0.30, 0.37, 0.17)), (0.92, (0.36, 0.40, 0.16)), (1.0, (0.50, 0.44, 0.12))))
    leaves = voronoi(nt, coord, 160.0)
    # a willow's curtain hangs in streaks of shoots
    strands = noise(nt, mapping(nt, coord, scale=(90.0, 90.0, 3.0)), 6.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.10, 0.14, 0.06), mul(nt, remap(nt, strands, 0.45, 0.70, 0.0, 0.55),
                                                     remap(nt, tone, 0.5, 0.6, 0.0, 1.0),
                                                     remap(nt, nz, 0.6, 0.2, 0.0, 1.0)))
    col = mix_color(nt, col, (0.02, 0.04, 0.015), remap(nt, leaves, 0.25, 0.55, 0.0, 0.50))
    col = mix_color(nt, col, (0.52, 0.58, 0.44), mul(nt, remap(nt, nz, 0.3, 0.9, 0.0, 0.25),
                                                     remap(nt, leaves, 0.25, 0.05, 0.0, 1.0),
                                                     remap(nt, tone, 0.5, 0.6, 0.0, 1.0)))
    col = mix_color(nt, col, (0.015, 0.03, 0.012), remap(nt, nz, -0.1, -0.7, 0.0, 0.55))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.75
    add_bump(nt, bsdf, leaves, 0.6, 0.003)
    translucent(nt, bsdf, (0.12, 0.25, 0.05), 0.15)
    return mat


def plinth_material():
    mat, nt, bsdf, coord = surface("TilePlinth")
    # the tile's frame, as the terrain category's: a dark slate band round
    # the top, and the skirt the delta's ground in section — a turf line,
    # then bedded silts and sands in brown and grey-tan with a scatter of
    # pebbles, over darker older clay at the foot
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
    """Seven slots, in index order: shared by the check and the render."""
    return (terrain_material(), water_material(), reed_material(), timber_material(), bark_material(),
            foliage_material(), plinth_material())


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
    def __init__(self, me, verts, polys, part_of, ident_of, tree=True):
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
        self.polys = polys
        self.tree = None
        if tree:
            remap_ = {vi: n for n, vi in enumerate(verts)}
            self.tree = BVHTree.FromPolygons(
                [tuple(p) for p in pts], [[remap_[v] for v in p.vertices] for p in polys])


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
    all_ = []
    for si, g in enumerate(groups):
        polys = by_shell[si]
        kind = part[polys[0].index] if polys else 0
        all_.append(Shell(me, g, polys, part, ident, tree=kind not in (P_REED, P_CROWN)))

    def of(*kinds):
        return [s for s in all_ if s.part in kinds]

    zone = face_vals(me, "Zone", float)
    water = of(P_WATER)
    top = [p for s in water for p in s.polys if zone[p.index] > 0.5]
    vi = {}
    vs, fs = [], []
    for p in top:
        idx = []
        for v in p.vertices:
            if v not in vi:
                vi[v] = len(vs)
                vs.append(me.vertices[v].co.copy())
            idx.append(vi[v])
        fs.append(idx)
    return {"groups": groups, "all": all_, "tile": of(P_TILE), "water": water,
            "water_top": BVHTree.FromPolygons(vs, fs), "reeds": of(P_REED), "trunks": of(P_TRUNK),
            "crowns": of(P_CROWN), "floats": of(P_FLOAT), "logs": of(P_LOG), "posts": of(P_POST),
            "built": of(P_BUILT)}


def ray_down(tree, x, y):
    # from just over the tallest tree: a ray's start far up costs float precision
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 1.0)), Vector((0.0, 0.0, -1.0)), 2.0)
    return None if loc is None else loc.z


def mouth_paths(T):
    """Each mouth's course from the back edge to its end, as (x, y) every
    DRAIN_STEP, through its parents."""
    out = []
    for chain in MOUTH_PATHS:
        pts = []
        for b in chain:
            path = T.br[b]["path"]
            n = max(1, int(round(DRAIN_STEP / PATH_STEP)))
            pts.extend((x, y) for x, y, _s in path[::n])
        out.append([p for p in pts if p[1] < HALF - 0.012])
    return out


def drain_audit(cls, T):
    """Along every mouth's course, the water's surface sampled straight down
    every 4 mm: the largest rise from one sample to the next (where water
    lies at both)."""
    wt = cls["water_top"]
    worst = -9.0
    n = 0
    for pts in mouth_paths(T):
        zs = [ray_down(wt, x, y) for x, y in pts]
        for a, b in zip(zs, zs[1:]):
            if a is None or b is None:
                continue
            n += 1
            worst = max(worst, b - a)
    return worst, n


def mouth_audit(cls, T, sea_level):
    """Along every mouth's course: water lying over the ground at every
    sample, and the water at its end against the sea's level."""
    wt = cls["water_top"]
    tile = cls["tile"][0]
    shallow = 9.0
    gaps = 0
    ends = []
    for pts in mouth_paths(T):
        for x, y in pts:
            w = ray_down(wt, x, y)
            g = ray_down(tile.tree, x, y)
            if w is None or g is None:
                gaps += 1
                continue
            shallow = min(shallow, w - g)
        x, y = pts[-1]
        w = ray_down(wt, x, y)
        ends.append(9.0 if w is None else w - sea_level)
    return shallow, gaps, ends


def wetted_span(cls, cx, cy, nx, ny, half, step=0.0004):
    """Across a channel through (cx, cy) along (nx, ny): the run of samples,
    containing the centre, where water lies over the ground."""
    wt = cls["water_top"]
    tile = cls["tile"][0]

    def wet(t):
        x, y = cx + nx * t, cy + ny * t
        w = ray_down(wt, x, y)
        g = ray_down(tile.tree, x, y)
        return w is not None and g is not None and w > g

    if not wet(0.0):
        return None
    lo = 0.0
    while lo > -half and wet(lo - step):
        lo -= step
    hi = 0.0
    while hi < half and wet(hi + step):
        hi += step
    return lo, hi


def fork_audit(cls, T):
    """At every bifurcation: the wetted width across the parent upstream and
    across each child downstream, and the angle between the children's
    courses, each child's course found from the wetted span's middle at two
    stations."""
    out = []
    for b, br in enumerate(T.br):
        kids = [k for k, (p, _c, _q) in enumerate(BRANCHES) if p == b]
        if len(kids) != 2:
            continue
        (cx, cy), _t, (nx, ny) = T.frame(b, br["len"] - WIDTH_STATION[0])
        sp = wetted_span(cls, cx, cy, nx, ny, 3.0 * br["w"])
        wp = None if sp is None else sp[1] - sp[0]
        widths = []
        dirs = []
        for k in kids:
            (cx, cy), _t, (nx, ny) = T.frame(k, WIDTH_STATION[1])
            sp = wetted_span(cls, cx, cy, nx, ny, 3.0 * T.br[k]["w"])
            widths.append(None if sp is None else sp[1] - sp[0])
            mids = []
            for s in FORK_STATIONS:
                (cx, cy), _t, (nx, ny) = T.frame(k, s)
                sp = wetted_span(cls, cx, cy, nx, ny, 3.0 * T.br[k]["w"])
                if sp is None:
                    mids.append(None)
                else:
                    m = 0.5 * (sp[0] + sp[1])
                    mids.append((cx + nx * m, cy + ny * m))
            if None in mids:
                dirs.append(None)
            else:
                dirs.append((mids[1][0] - mids[0][0], mids[1][1] - mids[0][1]))
        ratio = None
        if wp and None not in widths:
            ratio = sum(w * w for w in widths) / (wp * wp)
        angle = None
        if None not in dirs:
            (ax, ay), (bx, by) = dirs
            angle = math.degrees(math.acos(max(-1.0, min(1.0, (ax * bx + ay * by)
                                                          / (math.hypot(ax, ay) * math.hypot(bx, by))))))
        out.append({"b": b, "wp": wp, "w": widths, "ratio": ratio, "angle": angle})
    return out


def levee_audit(cls, T):
    """Every 25 mm along every channel, each bank: its crest (the highest
    ground out to three crest-distances past the bank) over the water at the
    channel's centre, and over the marsh behind it."""
    wt = cls["water_top"]
    tile = cls["tile"][0]
    over_w = 9.0
    over_m = 9.0
    n = 0
    for b, br in enumerate(T.br):
        s0 = 0.10 if br["parent"] >= 0 else 0.0
        s1 = br["s_cross"] - 0.14 if br["mouth"] else br["len"] - 0.08
        s = s0
        while s <= s1:
            (cx, cy), _t, (nx, ny) = T.frame(b, s)
            s += 0.025
            if sq_in(cx, cy) < LIP_W + LIP_R + 0.06:
                continue
            w = T.width(b, s - 0.025)
            wz = ray_down(wt, cx, cy)
            if wz is None:
                over_w = min(over_w, -9.0)
                continue
            for side in (-1.0, 1.0):
                crest = -9.0
                e = 0.0
                while e <= 3.0 * br["ep"]:
                    x, y = cx + nx * side * (w + e), cy + ny * side * (w + e)
                    g = ray_down(tile.tree, x, y)
                    if g is not None:
                        crest = max(crest, g)
                    e += 0.001
                em = max(3.4 * br["ep"], 0.055)
                mx, my = cx + nx * side * (w + em), cy + ny * side * (w + em)
                info = {}
                T.ground(mx, my, info=info)
                n += 1
                over_w = min(over_w, crest - wz)
                if info["nb"] != b or info["dc"] < 0.06 or info["pond"] >= 0 or sq_in(mx, my) < LIP_W + LIP_R:
                    continue
                gm = ray_down(tile.tree, mx, my)
                if gm is not None:
                    over_m = min(over_m, crest - gm)
    return over_w, over_m, n


def island_audit(cls, T, sea_level):
    """Each island's core: the lowest ground over it, against the water
    round it — the sea for the bars, the higher of the two channels either
    side for the islands between them."""
    wt = cls["water_top"]
    tile = cls["tile"][0]
    out = []
    for k, bar in enumerate(T.bars):
        cx, cy = bar["c"]
        lows = []
        for j in range(13):
            a = TAU * j / 12
            f = 0.0 if j == 12 else 0.022
            g = ray_down(tile.tree, cx + f * math.cos(a), cy + f * math.sin(a))
            lows.append(-9.0 if g is None else g)
        out.append(("bar%d" % k, min(lows) - sea_level))
    for b, br in enumerate(T.br):
        kids = [k for k, (p, _c, _q) in enumerate(BRANCHES) if p == b]
        if len(kids) != 2:
            continue
        a_, b_ = kids
        pa = T.frame(a_, 0.30)[0]
        pb = T.frame(b_, 0.30)[0]
        cx, cy = 0.5 * (pa[0] + pb[0]), 0.5 * (pa[1] + pb[1])
        water = max((ray_down(wt, *pa) or 9.0), (ray_down(wt, *pb) or 9.0))
        lows = []
        for j in range(13):
            a = TAU * j / 12
            f = 0.0 if j == 12 else 0.035
            g = ray_down(tile.tree, cx + f * math.cos(a), cy + f * math.sin(a))
            lows.append(-9.0 if g is None else g)
        out.append(("isle%d" % b, min(lows) - water))
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
    """The open sea's top: median height and largest excursion from it;
    each pond's top flat."""
    opn = vert_vals(me, "Open")
    zs = []
    flat = 0.0
    for s in cls["water"]:
        _top, verts, _rim = water_top(me, s)
        if s.ident >= 10:
            pz = [me.vertices[v].co.z for v in verts]
            flat = max(flat, max(pz) - min(pz))
        else:
            zs.extend(me.vertices[v].co.z for v in verts if opn[v])
    zs.sort()
    med = zs[len(zs) // 2] if zs else 0.0
    exc = max(abs(z - med) for z in zs) if zs else 0.0
    return med, exc, flat, len(cls["water"])


def enclose_audit(me, cls):
    """Over every rim vertex and rim-edge midpoint of every water sheet's
    top, the ground — save where the back edge cuts the river in section."""
    tile = cls["tile"][0]
    worst = 9.0
    n = 0
    cut = 0
    for s in cls["water"]:
        _t, _v, rim = water_top(me, s)
        for a, b in rim:
            pa, pb = me.vertices[a].co, me.vertices[b].co
            for p in (pa, (pa + pb) * 0.5):
                if p.y > HALF - 2.0 * EDGE_IN:
                    cut += 1
                    continue
                n += 1
                g = ray_down(tile.tree, p.x, p.y)
                worst = min(worst, -9.0 if g is None else g - p.z)
    return worst, n, cut


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


def foot_depths(me, cls, key):
    """Each shell's foot (its bottom cap): the shallowest of its corners
    under the ground straight above it."""
    tile = cls["tile"][0]
    cap = face_vals(me, "Cap")
    out = []
    for s in cls[key]:
        vs = {v for p in s.polys if cap[p.index] == 1 for v in p.vertices}
        if not vs:
            out.append(-9.0)
            continue
        out.append(min((ray_down(tile.tree, me.vertices[v].co.x, me.vertices[v].co.y) or -9.0)
                       - me.vertices[v].co.z for v in vs))
    return out


def float_audit(cls):
    """Every floating log and the boat: the share of its height under the
    water's surface at its middle; every stranded log sealed in the ground
    in each sector."""
    wt = cls["water_top"]
    tile = cls["tile"][0]
    fracs = []
    for s in cls["floats"]:
        cx, cy = 0.5 * (s.lo.x + s.hi.x), 0.5 * (s.lo.y + s.hi.y)
        w = ray_down(wt, cx, cy)
        fracs.append(-1.0 if w is None else (w - s.lo.z) / max(s.hi.z - s.lo.z, 1e-9))
    seals = [min(sector_bury(s.pts, lambda x, y: ray_down(tile.tree, x, y))) for s in cls["logs"]]
    return fracs, seals


def post_audit(me, cls):
    """Every stilt, jetty post and weir stake: its foot under the bed, its
    top over the water."""
    feet = foot_depths(me, cls, "posts")
    wt = cls["water_top"]
    clear = 9.0
    for s in cls["posts"]:
        cx, cy = 0.5 * (s.lo.x + s.hi.x), 0.5 * (s.lo.y + s.hi.y)
        w = ray_down(wt, cx, cy)
        g = ray_down(cls["tile"][0].tree, cx, cy)
        level = max(w if w is not None else -9.0, g if g is not None else -9.0)
        clear = min(clear, s.hi.z - level)
    return feet, clear


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, 0.2))
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
    img = bpy.data.images.new("DeltaNrm", size, size, alpha=True, float_buffer=False)
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
    low = build_mesh("RiverDeltaLow", T, plan, "low", **flags)
    high = build_mesh("RiverDeltaHigh", T, plan, "high", **flags)
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
    if len(cls["tile"]) != 1 or not cls["water"]:
        return (fail(f"tile/water not found: {len(cls['tile'])}/{len(cls['water'])}", 3),) + none2
    w_med, w_exc, p_flat, n_water = water_audit(low.data, cls)
    d_rise, d_n = drain_audit(cls, T)
    forks = fork_audit(cls, T)
    m_shallow, m_gaps, m_ends = mouth_audit(cls, T, w_med)
    l_over_w, l_over_m, l_n = levee_audit(cls, T)
    islands = island_audit(cls, T, w_med)
    enclose, n_rim, n_cut = enclose_audit(low.data, cls)
    reed_feet = foot_depths(low.data, cls, "reeds")
    fracs, seals = float_audit(cls)
    post_feet, post_clear = post_audit(low.data, cls)
    roots = foot_depths(low.data, cls, "trunks")

    img, tex = setup_bake_image(low, bake_mat)
    if img is None:
        return (fail("no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "RiverDeltaLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "RiverDeltaLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(build_collider_source(T), "RiverDeltaCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_river_delta_tile_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} water={n_water} reeds={len(cls['reeds'])} "
          f"trunks={len(cls['trunks'])} floats={len(cls['floats'])} logs={len(cls['logs'])} "
          f"posts={len(cls['posts'])} built={len(cls['built'])}")
    print(f"measured drain rise={d_rise:.7f} samples={d_n}")
    for f in forks:
        print(f"measured fork b={f['b']} wp={f['wp']} w={f['w']} ratio={f['ratio']} angle={f['angle']}")
    print(f"measured mouths shallow={m_shallow:.5f} gaps={m_gaps} ends={[round(e, 5) for e in m_ends]}")
    print(f"measured levees over_water={l_over_w:.5f} over_marsh={l_over_m:.5f} n={l_n}")
    print(f"measured islands {[(k, round(v, 5)) for k, v in islands]}")
    print(f"measured water median={w_med:.5f} excursion={w_exc:.5f} ponds_flat={p_flat:.6f} "
          f"enclose={enclose:.5f} n={n_rim} cut={n_cut}")
    print(f"measured reeds feet min={min(reed_feet):.4f} max={max(reed_feet):.4f} n={len(reed_feet)}")
    print(f"measured floats fracs={[round(f, 3) for f in fracs]} stranded seals={[round(s, 4) for s in seals]}")
    print(f"measured posts feet min={min(post_feet):.4f} max={max(post_feet):.4f} n={len(post_feet)} "
          f"clear={post_clear:.4f}")
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
    if d_rise > DRAIN_EPS or d_n < 400:
        return (fail(f"channels: the water rises {d_rise:.6f} m between samples (max {DRAIN_EPS}) "
                     f"over {d_n} samples", 17),) + none2
    bad = [f for f in forks if f["ratio"] is None or not (WIDTH_BAND[0] <= f["ratio"] <= WIDTH_BAND[1])]
    if len(forks) != 3 or bad:
        return (fail(f"width rule: (sum of the children's widths squared) over the parent's "
                     f"{[None if f['ratio'] is None else round(f['ratio'], 3) for f in forks]} "
                     f"(band {WIDTH_BAND})", 18),) + none2
    bad = [f for f in forks if f["angle"] is None or not (FORK_BAND[0] <= f["angle"] <= FORK_BAND[1])]
    if bad:
        return (fail(f"bifurcation angles {[None if f['angle'] is None else round(f['angle'], 1) for f in forks]} "
                     f"deg (band {FORK_BAND})", 19),) + none2
    if m_gaps or m_shallow < MOUTH_WET or max(abs(e) for e in m_ends) > MOUTH_EPS:
        return (fail(f"mouths: {m_gaps} samples along a course without water over the ground, shallowest "
                     f"{m_shallow:.5f} m (min {MOUTH_WET}), ends off the sea's level by "
                     f"{[round(e, 5) for e in m_ends]} (max {MOUTH_EPS})", 20),) + none2
    if l_over_w < CREST_MIN or l_over_m < BACK_MIN:
        return (fail(f"levees: a crest {l_over_w:.5f} m over the channel's water (min {CREST_MIN}), "
                     f"{l_over_m:.5f} m over the marsh behind it (min {BACK_MIN})", 21),) + none2
    low_isl = [(k, round(v, 5)) for k, v in islands if v < ISLAND_MIN]
    if len(islands) != len(T.bars) + 3 or low_isl:
        return (fail(f"islands: {low_isl} stand under {ISLAND_MIN} m over the water round them", 22),) + none2
    if abs(w_med - SEA_Z) > LEVEL_EPS or not (RIPPLE_BAND[0] <= w_exc <= RIPPLE_BAND[1]) or p_flat > POND_FLAT:
        return (fail(f"water: median {w_med:.5f} m (level {SEA_Z} +- {LEVEL_EPS}), ripple {w_exc:.5f} m "
                     f"(band {RIPPLE_BAND}), ponds {p_flat:.5f} m (flat within {POND_FLAT})", 23),) + none2
    if enclose < ENCLOSE_MIN:
        return (fail(f"water not contained: ground over the rims {enclose:.5f} m (min {ENCLOSE_MIN})", 24),) + none2
    n_reed = sum(c["n"] for c in plan["reeds"])
    if len(reed_feet) != n_reed or min(reed_feet) < REED_BAND[0] or max(reed_feet) > REED_BAND[1]:
        return (fail(f"reeds: {len(reed_feet)}/{n_reed} blades, feet {min(reed_feet):.4f}..{max(reed_feet):.4f} "
                     f"m under the ground (band {REED_BAND})", 25),) + none2
    n_float = sum(1 for lg in plan["logs"] if lg["float"]) + 1
    if (len(fracs) != n_float or min(fracs) < FLOAT_BAND[0] or max(fracs) > FLOAT_BAND[1]
            or not seals or min(seals) < PERCH_BAND):
        return (fail(f"floats: {len(fracs)}/{n_float} afloat, under the water by {[round(f, 3) for f in fracs]} "
                     f"of their height (band {FLOAT_BAND}); stranded logs sealed {[round(s, 4) for s in seals]} "
                     f"(min {PERCH_BAND})", 26),) + none2
    if min(post_feet) < POST_BAND[0] or max(post_feet) > POST_BAND[1] or post_clear < 0.003:
        return (fail(f"posts: feet {min(post_feet):.4f}..{max(post_feet):.4f} m under the bed (band {POST_BAND}), "
                     f"tops {post_clear:.4f} m over the water", 27),) + none2
    if len(roots) != len(plan["trees"]) or min(roots) < ROOT_BAND[0] or max(roots) > ROOT_BAND[1]:
        return (fail(f"trees: {len(roots)}/{len(plan['trees'])} trunks, feet {min(roots):.4f}..{max(roots):.4f} "
                     f"m under the ground (band {ROOT_BAND})", 28),) + none2
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 29),) + none2
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

    # Key high on the left, low enough that the trees, reeds and the hut
    # throw shadows across the flat plain; fill, rim, and the warm wedge
    # dropping its pool on the floor off to the left, clear of the water.
    light("Key", (-3.4, -2.2, 3.6), 280.0, 3.0, (1.0, 0.95, 0.88), spread=28.0)
    light("Fill", (4.2, -3.2, 1.6), 45.0, 8.0, (0.72, 0.82, 1.0))
    light("Rim", (0.8, 3.2, 2.6), 140.0, 3.0, (0.65, 0.80, 1.0))
    light("Wedge", (-2.3, 2.1, 2.4), 260.0, 1.5, (1.0, 0.68, 0.40),
          target=(-2.5, 2.4, 0.0), spread=38.0)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.20, -0.98, 0.0)).normalized()
    cam.location = centre + view * 4.40 + Vector((0.0, 0.0, 3.65))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, -0.22, -0.10))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the tile.
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


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--uphill-channel", action="store_true")
    p.add_argument("--choke-branch", action="store_true")
    p.add_argument("--splay-fork", action="store_true")
    p.add_argument("--plug-mouth", action="store_true")
    p.add_argument("--breach-levee", action="store_true")
    p.add_argument("--drown-islet", action="store_true")
    p.add_argument("--flat-sea", action="store_true")
    p.add_argument("--short-sea", action="store_true")
    p.add_argument("--float-reeds", action="store_true")
    p.add_argument("--sink-logs", action="store_true")
    p.add_argument("--lift-hut", action="store_true")
    p.add_argument("--float-trees", action="store_true")
    args = p.parse_args(argv)

    flags = {k: getattr(args, k) for k in (
        "uphill_channel", "choke_branch", "splay_fork", "plug_mouth", "breach_levee", "drown_islet",
        "flat_sea", "short_sea", "float_reeds", "sink_logs", "lift_hut", "float_trees")}
    code, low, _mat = check(args.skip_decimate, lift_z=args.lift_z, stray_vert=args.stray_vert, **flags)
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("river-delta-tile OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
