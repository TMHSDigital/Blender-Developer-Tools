"""Game-ready mushroom stump — a showcase piece, not an example.

Asserts budget conformance of a procedural felled-tree stump on its patch of
forest floor after composing shipped pipeline pieces: bmesh construction,
UVs, twelve materials, high-to-low normal bake, LOD chain, convex stump
collider, Unity glTF export.

The stump is one lathe about a plumb axis: a chainsaw cut 0.50 m above the
soil, 0.62 m across the bark, flaring through five buttresses into the
ground. Its plated bark is cut by sixteen narrow furrows and peeled away in
two patches that show the sapwood. The cut face carries growth rings round
a dark heartwood and five radial drying checks that notch the rim, and a
strip of torn holding wood stands up where the tree broke off its hinge.
Five surface roots run out of the buttresses and dive into the soil. Moss
cushions grow on the shaded north flank; two tiers of turkey-tail brackets
grow out of the bark; three fly agarics (a mature cap, a domed one and a
button) stand on the soil in front of it, each on a bulbous, volva-ringed
stipe with a hanging skirt; two clusters of honey fungus grow on thin
ringed stipes out of a root and out of the stump's foot. Ground cover is
fallen leaves, two clumps of ferns, twigs and a few broken pebbles.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--perch-stump`` the stump sealed in the soil
all round, ``--float-caps`` every cap seated on its stipe, ``--tilt-cut``
the saw cut level, ``--fat-stump`` the stump's stated size, ``--arch-roots``
the roots bedded along their run, ``--float-mushrooms`` every stipe rooted
in its host, ``--float-brackets`` the brackets rooted in the bark,
``--sunny-moss`` the moss on up- and shade-facing surfaces,
``--float-cover`` the ground cover joined to the soil.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python mushroom_stump.py --
    blender --background --python mushroom_stump.py -- --skip-decimate
    blender --background --python mushroom_stump.py -- --output stump.png
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

SEED = 5173
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- Stump -----------------------------------------------------------------
R_CUT = 0.307           # bark radius at the cut, before out-of-round and furrows
TAPER = 0.07            # the bole widens this fraction from the cut to the soil
ELLIPSE = 0.035
CUT_H = 0.50            # saw cut above the soil at the axis
STUMP_SIDES = 96
STUMP_SIDES_HIGH = 192
FURROWS = 16
FURROW_D = 0.016
BARK_T = 0.022          # the sapwood lies this far under the plates
# buttresses: (azimuth deg, half-width rad, strength); a root runs out of each
LOBES = ((-10.0, 0.34, 1.00), (96.0, 0.30, 0.85), (165.0, 0.33, 0.95),
         (235.0, 0.30, 0.80), (300.0, 0.33, 1.00))
FLARE = 0.17
FLARE_H = 0.11
FOOT_OFFS = (-0.045, 0.010, 0.032, 0.066)   # foot rings: above the soil under each vertex
UPPER_Z0 = 0.13         # first level ring above the soil at the axis (lifted clear of the foot)
UPPER_STEP = 0.034
PEEL_LOW = 0.05
PEEL_TOP_CLEAR = 0.035
# peeled bark: (height above the soil m, azimuth deg, half-height m, half-arc m)
PEELS = ((0.33, 34.0, 0.085, 0.085), (0.16, 128.0, 0.050, 0.060))
# the cut face: rings as fractions of the wood's radius, bark ring first
CAP_FR = (0.965, 0.90, 0.80, 0.68, 0.55, 0.42, 0.29, 0.16)
# radial drying checks: (azimuth deg, reach inward as a fraction of the radius)
CHECKS = ((14.0, 0.46), (104.0, 0.62), (198.0, 0.38), (262.0, 0.30), (318.0, 0.54))
CHECK_D = 0.016
# the felling: the tree fell toward FALL_DEG; the hinge's holding wood tore
# along a chord HINGE_OFF toward the fall
FALL_DEG = 60.0
HINGE_OFF = 0.075
HINGE_N = 34
HINGE_SPIKES = (12, 16, 24)
HINGE_H = 0.060
HINGE_W = 0.017          # half-width at the base, across the chord
HINGE_BITE = 0.015
TILT_CUT_DEG = 5.0       # --tilt-cut: the cut plane turned about the hinge chord
FAT_STUMP = 1.08         # --fat-stump: every stump radius scaled

# --- Roots -----------------------------------------------------------------
ROOT_SIDES = 8
# (fraction of reach, centre above the soil m, radius m)
ROOT_PROF = ((0.28, 0.110, 0.100), (0.38, 0.075, 0.085), (0.48, 0.045, 0.072),
             (0.57, 0.025, 0.062), (0.66, 0.010, 0.052), (0.75, -0.004, 0.044),
             (0.83, -0.018, 0.036), (0.90, -0.032, 0.029), (0.96, -0.046, 0.023),
             (1.00, -0.058, 0.018))
ROOT_RINGS = 24
ROOT_REACH = (0.62, 0.72)
ARCH_ROOTS = 0.090       # --arch-roots: each root's middle raised off its bed

# --- Moss and brackets -------------------------------------------------------
# moss cushions on the shaded north flank: (height m, azimuth deg, half-height m, half-arc m)
MOSS = ((0.24, 90.0, 0.130, 0.120), (0.43, 74.0, 0.050, 0.075), (0.12, 116.0, 0.060, 0.090),
        (0.37, 100.0, 0.045, 0.060))
MOSS_T = 0.026
MOSS_EDGE = 0.003
MOSS_BITE = 0.006
MOSS_STAGGER = 0.0015
# turkey-tail tiers: (top height m, azimuth deg, height step m, [(width, reach)...])
TIERS = ((0.34, 134.0, -0.050, ((0.15, 0.085), (0.13, 0.075), (0.10, 0.060))),
         (0.37, -6.0, -0.046, ((0.15, 0.085), (0.13, 0.075), (0.10, 0.058))))
SHELF_NS = 14
SHELF_ROWS = (0.0, 0.16, 0.32, 0.47, 0.60, 0.72, 0.82, 0.91, 0.965, 1.0)
SHELF_NT = len(SHELF_ROWS) - 1
SHELF_BITE = 0.018
SHELF_STAGGER = 0.0015
FLOAT_BRACKETS = 0.035

# --- Mushrooms -------------------------------------------------------------
# fly agarics on the soil: (x, y, cap radius, stipe height, stipe radius, dome, lean x, lean y)
AGARICS = ((0.44, 0.47, 0.076, 0.168, 0.0138, 1.00, -0.06, 0.05),
           (0.65, 0.32, 0.052, 0.120, 0.0105, 1.45, 0.10, -0.04),
           (0.30, 0.66, 0.031, 0.052, 0.0090, 2.00, 0.02, 0.08))
AG_SIDES = 32
AG_SINK = 0.030          # the bulb's foot under the soil
AG_BITE = 0.014          # the stipe's tip inside its cap
GILL_D = 0.05
# honey-fungus clusters: (host, root index or azimuth deg, station, members)
HONEY = (("root", 1, 0.64, 7), ("stump", 36.0, 0.085, 6))
HONEY_SIDES = 10
HONEY_CAP_SIDES = 20
HONEY_BITE = 0.008
HOST_DEPTH = 0.030       # a honey stipe's foot inside its host
FLOAT_CAPS = 0.024       # --float-caps: every cap moved up its axis
FLOAT_MUSH = 0.050       # --float-mushrooms: every mushroom moved off its host

# --- Ground ----------------------------------------------------------------
SOIL_A = (0.98, 0.92)
SOIL_N = 44
SOIL_H0 = 0.15
SLOPE = 0.15             # the ground rises toward the back (-Y)
SOIL_EDGE = 0.16
SOIL_FLOOR = 0.012
N_LEAVES = 110
LEAF_BITE = 0.006
FLOAT_COVER = 0.025
FERN_CLUMPS = (((-0.63, -0.24), (150.0, 188.0, 222.0, 258.0), (0.36, 0.44)),
               ((-0.03, -0.69), (218.0, 252.0, 286.0, 320.0), (0.38, 0.46)))
FERN_PINNAE = 14
# twigs: (x, y, yaw deg, length, radius)
TWIGS = ((-0.50, 0.47, 20.0, 0.32, 0.010), (0.12, 0.72, -35.0, 0.24, 0.008),
         (0.62, -0.40, 70.0, 0.28, 0.009))
PEBBLES = ((0.15, 0.66, 0.045), (0.70, 0.10, 0.035), (-0.30, 0.60, 0.030), (0.56, 0.60, 0.040))
STONE_BED = 0.010

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (1.9961, 1.8965, 0.7807)
BASE_TRIS_MIN = 34700
BASE_TRIS_MAX = 35800
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 12
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 75
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# bark, wood, moss, bracket, agaric, honey, flesh, soil, litter, fern, stone, twig
FACE_FLOORS = (2280, 930, 860, 1440, 600, 1640, 3640, 1900, 1450, 3660, 345, 190)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Stump sealed: in each azimuth sector round its centroid, some stump
# vertex lies at least SEAL_EPS under the soil straight above it.
SEAL_SECTORS = 8
SEAL_EPS = 0.005
# Caps: the stipe's deepest vertex inside its own cap.
CAP_BITE_MIN = 0.003
CAP_BITE_MAX = 0.030
# Cut and size: plane fit on the sawn face; diameter across the bark just
# under the cut; height of the cut above the soil at the fit's centre.
CUT_TILT_MAX = 1.0
STUMP_D = 0.62
STUMP_HT = 0.50
SIZE_TOL = 0.015
# Roots: binned at ROOT_STATION along their run outside the stump, every
# station's most-buried vertex at least ROOT_BED_MIN under the soil.
ROOT_STATION = 0.05
ROOT_BED_MIN = 0.006
# Mushrooms: each stipe's deepest vertex in its host (soil or wood).
HOST_MIN = 0.008
HOST_MAX = 0.070
# Brackets: each shelf's deepest vertex inside the bark.
FUNGUS_BITE_MIN = 0.006
FUNGUS_BITE_MAX = 0.050
# Moss: top faces (facing away from the bark) that face up or north.
MOSS_TOP_DOT = 0.3
MOSS_UP_Z = 0.25
MOSS_SHADE_Y = 0.5
MOSS_FRAC_MIN = 0.85
# Hero yaw about Z only (level on the stage).
HERO_YAW_DEG = 180.0
WALL_Y = 4.0

BARK_IDX = 0
WOOD_IDX = 1
MOSS_IDX = 2
BRACKET_IDX = 3
AGARIC_IDX = 4
HONEY_IDX = 5
FLESH_IDX = 6
SOIL_IDX = 7
LITTER_IDX = 8
FERN_IDX = 9
STONE_IDX = 10
TWIG_IDX = 11
MAT_LABELS = ("bark", "wood", "moss", "bracket", "agaric", "honey", "flesh", "soil",
              "litter", "fern", "stone", "twig")

# face Part codes, so every audit classifies shells by what built them
P_SOIL, P_STUMP, P_ROOT, P_HINGE, P_MOSS, P_BRACKET, P_STIPE, P_CAP, P_LEAF, P_FERN, \
    P_TWIG, P_PEBBLE = range(1, 13)


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


def wrap(a):
    return (a + math.pi) % TAU - math.pi


def hor(v):
    return Vector((v.x, v.y, 0.0))


# --------------------------------------------------------------------------
# The stump's closed-form shape
# --------------------------------------------------------------------------

def fall_dir():
    a = math.radians(FALL_DEG)
    return Vector((math.cos(a), math.sin(a), 0.0))


def hinge_point():
    return fall_dir() * HINGE_OFF


def cut_z(x, y, soil0, tilt):
    """The saw cut: level at CUT_H above the soil at the axis. ``--tilt-cut``
    turns it about the hinge chord, so the hinge stays where it is."""
    z = soil0 + CUT_H
    if tilt:
        h = hinge_point()
        f = fall_dir()
        z += math.tan(math.radians(TILT_CUT_DEG)) * ((x - h.x) * f.x + (y - h.y) * f.y)
    return z


def lobe(a):
    best = 0.0
    for deg, w, s in LOBES:
        best = max(best, s * math.exp(-(wrap(a - math.radians(deg)) / w) ** 2))
    return best


def stump_radius(zrel, a, fat=1.0):
    """Bark radius (plate crests) at height ``zrel`` above the soil."""
    t = min(max(zrel / CUT_H, 0.0), 1.2)
    r = R_CUT * (1.0 + TAPER * (1.0 - t))
    r *= 1.0 + ELLIPSE * math.cos(2.0 * (a - 0.7))
    r *= 1.0 + 0.018 * math.sin(3.0 * a + 1.1 + 2.0 * zrel) + 0.012 * math.sin(5.0 * a + 0.4)
    fl = math.exp(-max(zrel, 0.0) / FLARE_H)
    r += FLARE * fl * (0.22 + 0.78 * lobe(a))
    return r * fat


def furrow(zrel, a):
    """Plates with narrow V furrows between them, wandering up the bole.
    cos(FURROWS a) is sampled on the lathe's own vertices, so the high and
    low builds carry the same furrows."""
    ph = FURROWS * a + 0.5 * math.sin(5.1 * zrel + 0.7) + 0.3 * math.sin(11.0 * zrel)
    v = (1.0 - math.cos(ph)) * 0.5
    depth = FURROW_D * (0.70 + 0.30 * math.sin(3.3 * zrel + 2.0 * a))
    return -depth * v ** 3


def peel_field(zrel, a, patches):
    """Largest (edge - r) over the peel patches: positive inside a patch,
    zero on its torn edge. Never at the rim or in the soil."""
    if zrel > CUT_H - PEEL_TOP_CLEAR or zrel < PEEL_LOW:
        return -1.0
    best = -9.0
    for p in patches:
        ds = (zrel - p["z"]) / p["hz"]
        da = wrap(a - p["a"]) * R_CUT / p["ha"]
        r = math.hypot(ds, da)
        th = math.atan2(da, ds)
        edge = 1.0 + 0.22 * math.sin(3.0 * th + p["ph"]) + 0.12 * math.sin(7.0 * th + 2.0 * p["ph"])
        best = max(best, edge - r)
    return best


# --------------------------------------------------------------------------
# The plan: every seeded draw happens here, before anything is built
# --------------------------------------------------------------------------

def plan_stump():
    rng = random.Random(SEED)

    def u(a, b):
        return a + (b - a) * rng.random()

    peels = [{"z": z, "a": math.radians(a), "hz": hz, "ha": ha, "ph": u(0.0, TAU)}
             for z, a, hz, ha in PEELS]
    moss = [{"z": z, "a": math.radians(a), "hz": hz * u(0.92, 1.08), "ha": ha * u(0.92, 1.08),
             "ph": u(0.0, TAU), "tone": rng.random()} for z, a, hz, ha in MOSS]
    shelves = []
    for ti, (z0, a0, dz, sizes) in enumerate(TIERS):
        for k, (w, d) in enumerate(sizes):
            shelves.append({"tier": ti, "z": z0 + dz * k + u(-0.006, 0.006),
                            "a": math.radians(a0 + (7.0 if k % 2 else -5.0) + u(-3.0, 3.0)),
                            "yaw": math.radians(u(-14.0, 14.0)),
                            "w": w * u(0.92, 1.08), "d": d * u(0.92, 1.08),
                            "ph": u(0.0, TAU), "tone": rng.random(), "lift": u(-0.02, 0.10)})
    roots = []
    for k, (deg, _w, s) in enumerate(LOBES):
        roots.append({"yaw": math.radians(deg + u(-4.0, 4.0)), "reach": u(*ROOT_REACH),
                      "wig": u(0.06, 0.12) * (1.0 if k % 2 else -1.0), "ph": u(0.0, TAU),
                      "scale": 0.80 + 0.20 * s, "tone": rng.random()})
    # the holding wood: each torn fibre bundle its own height, lean and
    # width, a few long splinters among short stubs
    hinge = []
    for i in range(HINGE_N + 1):
        v = rng.random()
        if i % 2:
            h = u(0.10, 0.28)                       # the torn floor between splinters
        else:
            h = 0.30 + 0.70 * v ** 1.5
            if i in HINGE_SPIKES:
                h = u(1.7, 2.2)                     # the long splinters
        hinge.append({"h": h, "lean": u(0.08, 0.40), "slide": u(-0.006, 0.006),
                      "w": u(0.75, 1.15)})
    agarics = [{"tone": u(0.0, 0.3), "spin": u(0.0, TAU), "cap_tone": rng.random()} for _ in AGARICS]
    honey = []
    for host, which, station, count in HONEY:
        members = []
        for m in range(count):
            span = (m + 0.5) / count - 0.5
            L = u(0.100, 0.160)
            # neighbours alternate: a tall one close in, a short one leaning
            # out, so their caps shingle instead of running into each other
            tall = m % 2 == 0
            members.append({"yaw": span * math.radians(210.0 if host == "root" else 120.0)
                            + math.radians(u(-7.0, 7.0)),
                            "L": L, "reach": L * (u(0.28, 0.40) if tall else u(0.70, 0.85)),
                            "h": L * (u(0.88, 0.98) if tall else u(0.50, 0.62)),
                            "rc": u(0.022, 0.034), "dome": u(0.9, 1.2), "spin": u(0.0, TAU),
                            "tone": u(0.7, 1.0), "cap_tone": rng.random(),
                            "dx": u(-0.012, 0.012), "dy": u(-0.012, 0.012)})
        honey.append({"host": host, "which": which, "station": station, "members": members})
    ferns = []
    for (cx, cy), yaws, (h0, h1) in FERN_CLUMPS:
        for yaw in yaws:
            ferns.append({"x": cx + u(-0.03, 0.03), "y": cy + u(-0.03, 0.03),
                          "yaw": math.radians(yaw + u(-8.0, 8.0)), "h": u(h0, h1),
                          "reach": u(0.26, 0.32), "lp": u(0.085, 0.11),
                          "tone": rng.random(), "curl": u(0.25, 0.40), "tw0": u(-0.12, 0.12)})
    twigs = [{"bend": u(-0.25, 0.25), "fork": u(0.35, 0.6), "tone": rng.random()} for _ in TWIGS]
    pebbles = [{"yaw": u(0.0, TAU), "jit": [rng.random() for _ in range(8)]} for _ in PEBBLES]

    avoid = ([((x, y), 0.12) for x, y, *_rest in AGARICS]
             + [((c[0][0], c[0][1]), 0.24) for c in FERN_CLUMPS]
             + [((x, y), r + 0.05) for x, y, r in PEBBLES])
    leaves = []
    tries = 0
    while len(leaves) < N_LEAVES and tries < 60000:
        tries += 1
        x = u(-1.0, 1.0) * SOIL_A[0]
        y = u(-1.0, 1.0) * SOIL_A[1]
        rr = math.hypot(x / SOIL_A[0], y / SOIL_A[1])
        if rr > 0.84 or math.hypot(x, y) < 0.44:
            continue
        # drifts, not a ring: the litter gathers in patches
        drift = 0.5 + 0.5 * math.sin(3.1 * x + 1.3) * math.sin(2.7 * y + 0.4)
        if rng.random() > 0.15 + 0.85 * drift:
            continue
        near_root = False
        for rt in roots:
            d = Vector((math.cos(rt["yaw"]), math.sin(rt["yaw"]), 0.0))
            along = x * d.x + y * d.y
            if -0.05 < along < rt["reach"] + 0.05 and abs(x * d.y - y * d.x) < 0.14:
                near_root = True
        if near_root:
            continue
        if any(math.hypot(x - c[0], y - c[1]) < r for c, r in avoid):
            continue
        ln = u(0.050, 0.100)
        # leaves never overlap: the one on top would lie on the other, not on the soil
        if any(math.hypot(x - lf["x"], y - lf["y"]) < 0.5 * (ln + lf["len"]) + 0.004 for lf in leaves):
            continue
        leaves.append({"x": x, "y": y, "yaw": u(0.0, TAU), "len": ln,
                       "wid": u(0.40, 0.60), "curl": u(0.002, 0.008), "tilt": u(-0.14, 0.14),
                       "tone": rng.random() ** 1.3})
    return {"peels": peels, "moss": moss, "shelves": shelves, "roots": roots, "hinge": hinge,
            "agarics": agarics, "honey": honey, "ferns": ferns, "twigs": twigs,
            "pebbles": pebbles, "leaves": leaves}


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

class Builder:
    def __init__(self, bm):
        self.bm = bm
        f = bm.faces.layers.float
        self.L = {n: f.new(n) for n in ("Tone", "Zone", "EndGrain", "Part", "Ident")}
        v = bm.verts.layers.float
        self.radial = v.new("Radial")
        self.peel = v.new("Peel")
        self.check = v.new("Check")

    def vert(self, co):
        return self.bm.verts.new(co)

    def face(self, verts, mat, tone, part, ident=0.0, zone=0.0, grain=0.0):
        out = []
        for v in verts:
            if not out or out[-1] is not v:
                out.append(v)
        if len(out) > 1 and out[0] is out[-1]:
            out.pop()
        f = self.bm.faces.new(out)
        f.material_index = mat
        L = self.L
        f[L["Tone"]] = tone
        f[L["Zone"]] = zone
        f[L["EndGrain"]] = grain
        f[L["Part"]] = float(part)
        f[L["Ident"]] = float(ident)
        return f


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


def add_tube(B, pts, radii, sides, mat, tone, part, ident=0.0, phase=0.0, zones=None,
             jag=None, end_mat=None, end_grain=0.0):
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
            ring.append(B.vert(p + off + r * (n * math.cos(a) + b * math.sin(a))))
        rings.append(ring)
    nz = len(rings) - 1
    for i, (r0, r1) in enumerate(zip(rings, rings[1:])):
        zone = zones[i] if zones else 0.0
        for k in range(sides):
            m = (k + 1) % sides
            B.face((r0[k], r0[m], r1[m], r1[k]), mat, tone, part, ident, zone)
    B.face(tuple(reversed(rings[0])), mat, tone, part, ident, zones[0] if zones else 0.0)
    B.face(tuple(rings[-1]), end_mat if end_mat is not None else mat, tone, part, ident,
           zones[nz - 1] if zones else 0.0, end_grain)
    return rings


def add_lens(B, outline, top, bottom, mat, tone, part, zone=0.0):
    """A thin closed leaf: an outline ring fanned to a raised top centre and a
    lowered bottom centre. Every outline edge has one top and one bottom face."""
    ring = [B.vert(p) for p in outline]
    vt = B.vert(top)
    vb = B.vert(bottom)
    n = len(ring)
    for k in range(n):
        m = (k + 1) % n
        B.face((ring[k], ring[m], vt), mat, tone, part, 0.0, zone)
        B.face((ring[m], ring[k], vb), mat, tone, part, 0.0, zone)


def lathe(B, origin, axis, profile, sides, spin, tone, part, ident, band_fn, offset_fn=None):
    """Closed body of revolution; profile (r, z) runs pole to pole.
    ``band_fn(k)`` gives (material, zone) for the band between profile rows
    k and k + 1; ``offset_fn(k, j)`` an extra axial offset per ring vertex."""
    axis = axis.normalized()
    ref = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = axis.cross(ref).normalized()
    e2 = axis.cross(e1)
    p0 = B.vert(origin + axis * profile[0][1])
    p1 = B.vert(origin + axis * profile[-1][1])
    rings = []
    for k, (r, z) in enumerate(profile[1:-1], start=1):
        ring = []
        for j in range(sides):
            a = spin + TAU * j / sides
            dz = offset_fn(k, j) if offset_fn else 0.0
            ring.append(B.vert(origin + axis * (z + dz) + r * (e1 * math.cos(a) + e2 * math.sin(a))))
        rings.append(ring)
    last = len(profile) - 2
    for j in range(sides):
        m = (j + 1) % sides
        mat, zone = band_fn(0)
        B.face((rings[0][m], rings[0][j], p0), mat, tone, part, ident, zone)
        mat, zone = band_fn(last)
        B.face((rings[-1][j], rings[-1][m], p1), mat, tone, part, ident, zone)
    for k, (r0, r1) in enumerate(zip(rings, rings[1:]), start=1):
        mat, zone = band_fn(k)
        for j in range(sides):
            m = (j + 1) % sides
            B.face((r0[j], r0[m], r1[m], r1[j]), mat, tone, part, ident, zone)


# --------------------------------------------------------------------------
# Ground
# --------------------------------------------------------------------------

def soil_height(x, y):
    h = (SOIL_H0 - SLOPE * y + 0.014 * math.sin(1.9 * x + 0.3) * math.cos(2.3 * y + 0.9)
         + 0.008 * math.sin(4.1 * x - 3.3 * y + 1.2) + 0.004 * math.sin(7.3 * x + 5.9 * y))
    return max(SOIL_FLOOR, h)


def add_soil(B):
    """A soil disc: a squircle-mapped grid whose rim rolls down to a flat
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
            wob = (1.0 + 0.06 * math.sin(3.0 * th + 0.7) + 0.04 * math.sin(5.0 * th + 2.1)
                   + 0.025 * math.sin(8.0 * th + 0.3))
            x = SOIL_A[0] * X * wob
            y = SOIL_A[1] * Y * wob
            on_rim = i in (0, n) or k in (0, n)
            z = 0.0 if on_rim else soil_height(x, y) * smoothstep(1.0 - r, 0.0, SOIL_EDGE)
            col.append(B.vert((x, y, z)))
        grid.append(col)
    for i in range(n):
        for k in range(n):
            B.face((grid[i][k], grid[i + 1][k], grid[i + 1][k + 1], grid[i][k + 1]),
                   SOIL_IDX, 0.5, P_SOIL)
    rim = ([grid[i][0] for i in range(n)] + [grid[n][k] for k in range(n)]
           + [grid[i][n] for i in range(n, 0, -1)] + [grid[0][k] for k in range(n, 0, -1)])
    B.face(list(reversed(rim)), SOIL_IDX, 0.5, P_SOIL)


# --------------------------------------------------------------------------
# The stump
# --------------------------------------------------------------------------

class StumpSurface:
    """The built stump's lathe grid, sampled per column by height, so
    anything laid on the bark (moss, brackets, honey fungus) sits on the
    faces actually shipped."""

    def __init__(self, grid, sides):
        self.grid = grid
        self.sides = sides

    def _col(self, j, z):
        g = self.grid
        if z <= g[0][j].z:
            return g[0][j].copy()
        for i in range(len(g) - 1):
            a, b = g[i][j], g[i + 1][j]
            if z <= b.z:
                t = (z - a.z) / max(b.z - a.z, 1e-9)
                return a.lerp(b, t)
        return g[-1][j].copy()

    def point(self, z, a):
        fj = (a % TAU) / TAU * self.sides
        j = int(fj) % self.sides
        v = fj - math.floor(fj)
        j1 = (j + 1) % self.sides
        return self._col(j, z).lerp(self._col(j1, z), v)

    def normal(self, z, a):
        ez = 0.004
        ea = 0.010
        pz = self.point(z + ez, a) - self.point(z - ez, a)
        pa = self.point(z, a + ea) - self.point(z, a - ea)
        n = pa.cross(pz).normalized()
        if n.dot(hor(self.point(z, a))) < 0.0:
            n = -n
        return n


def check_dip(j, sides, frac):
    """Depth of a drying check at column ``j`` and radial fraction ``frac``."""
    for deg, reach in CHECKS:
        jc = int(round(math.radians(deg) / TAU * sides)) % sides
        if j == jc:
            return CHECK_D * smoothstep(frac, 1.0 - reach, 1.0)
    return 0.0


def build_stump(B, plan, sides, G, flags):
    soil0 = G.z(0.0, 0.0)
    fat = FAT_STUMP if flags["fat_stump"] else 1.0
    tilt = flags["tilt_cut"]
    perch = flags["perch_stump"]
    peels = plan["peels"]
    angles = [TAU * j / sides for j in range(sides)]

    def bark_r(zrel, a):
        field = peel_field(zrel, a, peels)
        rr = stump_radius(zrel, a, fat)
        return (rr - BARK_T if field > 0.0 else rr + furrow(zrel, a) * fat), field

    grid = []
    fields = []
    # foot rings follow the soil under each vertex; --perch-stump sets them
    # from the soil at the axis alone, which leaves the downhill side open
    for off in FOOT_OFFS:
        ring = []
        pf = []
        for a in angles:
            r, field = bark_r(off, a)
            x, y = r * math.cos(a), r * math.sin(a)
            z = (soil0 if perch else G.z(x, y)) + off
            ring.append(Vector((x, y, z)))
            pf.append(field)
        grid.append(ring)
        fields.append(pf)
    zb = max(soil0 + UPPER_Z0, max(p.z for p in grid[-1]) + 0.03)
    zc = soil0 + CUT_H
    # a fixed ring count, so a falsifier that moves the foot keeps the topology
    n_up = int(math.ceil((CUT_H - UPPER_Z0) / UPPER_STEP))
    for i in range(n_up + 1):
        f = i / n_up
        znom = zb + f * (zc - zb)
        zrel = znom - soil0
        ring = []
        pf = []
        for j, a in enumerate(angles):
            r, field = bark_r(zrel, a)
            x, y = r * math.cos(a), r * math.sin(a)
            z = zb + f * (cut_z(x, y, soil0, tilt) - zb)
            if i == n_up:
                z -= 0.7 * check_dip(j, sides, 1.0)
            ring.append(Vector((x, y, z)))
            pf.append(field)
        grid.append(ring)
        fields.append(pf)

    verts = [[B.vert(p) for p in ring] for ring in grid]
    for ring, pf in zip(verts, fields):
        for v, field in zip(ring, pf):
            v[B.radial] = 1.0
            # the torn edge, for the bark shader: 0.5 exactly on the patch
            # outline, so the edge is cut between vertices, not along faces
            v[B.peel] = min(1.0, max(0.0, 0.5 + 2.0 * field))
    flags_ = [[fl > 0.0 for fl in pf] for pf in fields]
    for i in range(len(verts) - 1):
        for j in range(sides):
            m = (j + 1) % sides
            q = (verts[i][j], verts[i][m], verts[i + 1][m], verts[i + 1][j])
            f = (flags_[i][j], flags_[i][m], flags_[i + 1][m], flags_[i + 1][j])
            npeel = sum(f)
            if npeel == 0 or npeel == 4:
                B.face(q, WOOD_IDX if npeel else BARK_IDX, 0.1 if npeel else 0.25, P_STUMP)
                continue
            # a quad on a peel's edge splits along the diagonal that keeps
            # its bark corner apart, so the torn edge runs at 45 degrees
            if npeel == 3:
                k = 1 if not (f[0] and f[2]) else 0
            else:
                k = (i + j) % 2
            tris = (((q[0], q[1], q[2]), (0, 1, 2)), ((q[0], q[2], q[3]), (0, 2, 3))) if k == 0 \
                else (((q[0], q[1], q[3]), (0, 1, 3)), ((q[1], q[2], q[3]), (1, 2, 3)))
            for tri, idx in tris:
                wood = all(f[x] for x in idx)
                B.face(tri, WOOD_IDX if wood else BARK_IDX, 0.1 if wood else 0.25, P_STUMP)

    # the foot under the soil: a fan to a buried centre
    bottom = B.vert(Vector((0.0, 0.0, sum(v.co.z for v in verts[0]) / sides - 0.02)))
    for j in range(sides):
        m = (j + 1) % sides
        B.face((verts[0][m], verts[0][j], bottom), BARK_IDX, 0.25, P_STUMP)

    # the saw cut: the bark's top edge, then the end grain ring by ring to
    # the pith, notched by the drying checks
    rb = [stump_radius(CUT_H, a, fat) - BARK_T for a in angles]
    prev = verts[-1]
    spec = [(1.0, BARK_IDX, 1.0, 0.0)] + [(k, WOOD_IDX, k, 1.0) for k in CAP_FR]
    for frac, mat, radial, grain in spec:
        ring = []
        for j, a in enumerate(angles):
            x = rb[j] * frac * math.cos(a)
            y = rb[j] * frac * math.sin(a)
            dip = check_dip(j, sides, frac)
            weather = 0.0012 * math.sin(9.0 * x + 2.0) * math.cos(8.0 * y + 1.0)
            v = B.vert(Vector((x, y, cut_z(x, y, soil0, tilt) - dip + weather)))
            v[B.radial] = radial
            v[B.check] = dip / CHECK_D
            ring.append(v)
        for j in range(sides):
            m = (j + 1) % sides
            B.face((prev[j], prev[m], ring[m], ring[j]), mat, 0.25 if mat == BARK_IDX else 0.6,
                   P_STUMP, 0.0, 0.0, grain)
        prev = ring
    pith = B.vert(Vector((0.0, 0.0, cut_z(0.0, 0.0, soil0, tilt) - 0.001)))
    pith[B.radial] = 0.0
    for j in range(sides):
        m = (j + 1) % sides
        B.face((prev[j], prev[m], pith), WOOD_IDX, 0.6, P_STUMP, 0.0, 0.0, 1.0)

    # the holding wood: a jagged strip of torn fibres standing on the hinge
    # chord, leaning toward the fall, its foot set into the cut
    fd = fall_dir()
    hd = Vector((-fd.y, fd.x, 0.0))
    hp = hinge_point()
    rmin = min(rb)
    half = math.sqrt(max(rmin * rmin - HINGE_OFF * HINGE_OFF, 0.01)) * 0.66
    stations = []
    for i, fib in enumerate(plan["hinge"]):
        t = -1.0 + 2.0 * i / HINGE_N
        env = max(0.0, 1.0 - t * t)
        p = hp + hd * (t * half)
        h = HINGE_H * (0.25 + 0.75 * env ** 0.5) * fib["h"]
        zc0 = cut_z(p.x, p.y, soil0, tilt)
        w0 = HINGE_W * (0.45 + 0.55 * env ** 0.5) * fib["w"]
        wt = 0.22 * w0
        tip = fd * (fib["lean"] * h) + hd * fib["slide"]
        stations.append((
            B.vert(Vector((p.x, p.y, zc0 - HINGE_BITE)) - fd * w0),
            B.vert(Vector((p.x, p.y, zc0 + h)) - fd * wt + tip),
            B.vert(Vector((p.x, p.y, zc0 + h)) + fd * wt + tip),
            B.vert(Vector((p.x, p.y, zc0 - HINGE_BITE)) + fd * w0),
        ))
    for s0, s1 in zip(stations, stations[1:]):
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            B.face((s0[a], s1[a], s1[b], s0[b]), WOOD_IDX, 0.8, P_HINGE, 0.0, 0.0, 0.4)
    B.face(tuple(reversed(stations[0])), WOOD_IDX, 0.8, P_HINGE, 0.0, 0.0, 0.4)
    B.face(tuple(stations[-1]), WOOD_IDX, 0.8, P_HINGE, 0.0, 0.0, 0.4)
    return StumpSurface(grid, sides), soil0


def root_profile():
    """ROOT_PROF resampled at ROOT_RINGS even steps of the reach, so a
    ring falls in every station the bed audit bins."""
    out = []
    for i in range(ROOT_RINGS):
        rf = ROOT_PROF[0][0] + (1.0 - ROOT_PROF[0][0]) * i / (ROOT_RINGS - 1)
        for (f0, z0, r0), (f1, z1, r1) in zip(ROOT_PROF, ROOT_PROF[1:]):
            if rf <= f1 + 1e-9:
                t = (rf - f0) / (f1 - f0)
                out.append((rf, z0 + (z1 - z0) * t, r0 + (r1 - r0) * t))
                break
    return out


def build_roots(B, plan, G, arch):
    """Surface roots out of the buttresses, bedded along their run and
    diving into the soil at the tip. Returns each root's centreline."""
    lines = []
    for k, rt in enumerate(plan["roots"]):
        pts = []
        radii = []
        for rf, dz, rad in root_profile():
            a = rt["yaw"] + rt["wig"] * math.sin(7.0 * rf + rt["ph"]) * rf
            d = rt["reach"] * rf
            x, y = d * math.cos(a), d * math.sin(a)
            lift = ARCH_ROOTS * math.sin(math.pi * min(max((rf - 0.36) / 0.52, 0.0), 1.0)) \
                if arch else 0.0
            # near the disc's rolled rim the soil thins: keep the root inside it
            zc = max(G.z(x, y) + dz * rt["scale"], rad * rt["scale"] + 0.006)
            pts.append(Vector((x, y, zc + lift)))
            radii.append(rad * rt["scale"])
        add_tube(B, pts, radii, ROOT_SIDES, BARK_IDX, 0.3 + 0.4 * rt["tone"], P_ROOT, k + 1,
                 phase=rt["yaw"])
        lines.append((pts, radii))
    return lines


def add_moss(B, surf, patch, rot, bite, soil0):
    """A moss cushion: a lens over a patch of the bark, its rim tucked under
    the bark surface and its base inside the stump."""
    K = 6
    M = 20
    zc = soil0 + patch["z"]
    ac = patch["a"] + rot

    def lump(z, a):
        return (0.72 + 0.28 * math.sin(13.0 * z + 6.0 * a + patch["ph"])
                * math.sin(7.4 * z - 5.0 * a + 1.3 * patch["ph"]))

    top_rings = []
    bot_rings = []
    for k in range(1, K + 1):
        rho = k / K
        tr = []
        br = []
        for m in range(M):
            th = TAU * m / M
            edge = 1.0 + 0.20 * math.sin(3.0 * th + patch["ph"]) + 0.10 * math.sin(5.0 * th + 2.0 * patch["ph"])
            z = zc + rho * edge * patch["hz"] * math.cos(th)
            a = ac + rho * edge * patch["ha"] * math.sin(th) / R_CUT
            p = surf.point(z, a)
            nrm = surf.normal(z, a)
            thick = MOSS_T * max(0.0, 1.0 - rho * rho) ** 0.5 * lump(z, a)
            tv = B.vert(p + nrm * (thick - MOSS_EDGE))
            tr.append(tv)
            br.append(tv if k == K else B.vert(p - nrm * bite))
        top_rings.append(tr)
        bot_rings.append(br)
    p0 = surf.point(zc, ac)
    n0 = surf.normal(zc, ac)
    ct = B.vert(p0 + n0 * (MOSS_T * lump(zc, ac) - MOSS_EDGE))
    cb = B.vert(p0 - n0 * bite)
    tone = patch["tone"]
    for rings, centre, flip in ((top_rings, ct, False), (bot_rings, cb, True)):
        for m in range(M):
            q = (m + 1) % M
            tri = (rings[0][m], rings[0][q], centre)
            B.face(tri[::-1] if flip else tri, MOSS_IDX, tone, P_MOSS)
        for r0, r1 in zip(rings, rings[1:]):
            for m in range(M):
                q = (m + 1) % M
                quad = (r0[m], r1[m], r1[q], r0[q])
                B.face(quad[::-1] if flip else quad, MOSS_IDX, tone, P_MOSS)


def add_shelf(B, surf, shelf, float_off, bite, soil0, ident):
    """One turkey-tail bracket: a thin, lobed, wavy half-lens with a pore
    surface under a zoned cap. Its back edge follows the bark round the
    girth and is set into it."""
    z = soil0 + shelf["z"]
    W, D, ph = shelf["w"], shelf["d"], shelf["ph"]
    cy, sy = math.cos(shelf["yaw"]), math.sin(shelf["yaw"])
    t0 = 0.10 * D
    tb = 0.040 * D
    ns, nt = SHELF_NS, SHELF_NT
    top = [[None] * (nt + 1) for _ in range(ns + 1)]
    bot = [[None] * (nt + 1) for _ in range(ns + 1)]
    for i in range(ns + 1):
        si = -1.0 + 2.0 * i / ns
        env = max(0.0, 1.0 - si * si)
        ai = shelf["a"] + 0.5 * W * si / R_CUT
        p = surf.point(z, ai)
        nh = hor(surf.normal(z, ai)).normalized()
        nr = Vector((nh.x * cy - nh.y * sy, nh.x * sy + nh.y * cy, 0.0))
        # a lobed margin: the reach swells and dips round the fan
        reach = D * env ** 0.5 * (1.0 + 0.10 * math.sin(5.0 * si + ph) + 0.07 * math.sin(11.0 * si + 2.0 * ph))
        for j in range(nt + 1):
            t = SHELF_ROWS[j]
            grow = (reach + bite) * t ** 0.9
            slope = -0.10 * D * t * t + shelf["lift"] * D * t
            wave = 0.008 * math.sin(7.0 * si + ph) * t ** 2.5
            ridge = 0.018 * D * math.sin(t * 4.5 * TAU) * (1.0 - t) * env ** 0.35
            zt = t0 * (1.0 - t ** 1.4) * env ** 0.35 + slope + wave + ridge
            zb = -tb * (1.0 - t ** 2.0) * env ** 0.35 + slope + wave
            base = p + nh * (float_off - bite) + nr * grow
            vt = B.vert(base + UP * zt)
            top[i][j] = vt
            shared = i in (0, ns) or j == nt
            bot[i][j] = vt if shared else B.vert(base + UP * zb)
    tone = shelf["tone"]
    for i in range(ns):
        for j in range(nt):
            zone = (j + 0.5) / nt
            B.face((top[i][j], top[i + 1][j], top[i + 1][j + 1], top[i][j + 1]),
                   BRACKET_IDX, tone, P_BRACKET, ident, zone)
            B.face((bot[i][j + 1], bot[i + 1][j + 1], bot[i + 1][j], bot[i][j]),
                   BRACKET_IDX, tone, P_BRACKET, ident, 2.0)
        B.face((top[i][0], bot[i][0], bot[i + 1][0], top[i + 1][0]), BRACKET_IDX, tone,
               P_BRACKET, ident, 0.0)


# --------------------------------------------------------------------------
# Mushrooms
# --------------------------------------------------------------------------

AG_CAP = ((0.0, 0.0), (0.18, 0.035), (0.40, 0.070), (0.62, 0.100), (0.82, 0.125),
          (0.95, 0.150), (1.00, 0.190), (0.99, 0.235), (0.92, 0.310), (0.78, 0.390),
          (0.58, 0.450), (0.34, 0.490), (0.12, 0.505), (0.0, 0.510))
AG_MARGIN = 6
HONEY_CAP = ((0.0, 0.0), (0.20, 0.030), (0.45, 0.060), (0.70, 0.085), (0.90, 0.110),
             (1.00, 0.150), (0.97, 0.215), (0.86, 0.320), (0.68, 0.420), (0.45, 0.500),
             (0.22, 0.560), (0.08, 0.600), (0.0, 0.610))
HONEY_MARGIN = 5


def add_cap(B, origin, axis, prof, margin, rc, dome, sides, spin, mat, tone, ident):
    """A cap on the stipe: a lathe from the centre of its gills out to the
    margin and back over the crown. The gill surface is pleated into ridges.
    Zone runs 1 at the crown to 2 at the margin on the cap, 2 on the gills."""
    pts = [(r * rc, z * rc * dome) for r, z in prof]

    def band(k):
        if k < margin:
            return FLESH_IDX, 2.0
        return mat, 1.0 + min(1.0, prof[min(k + 1, len(prof) - 1)][0])

    def gills(k, j):
        if 0 < k < margin - 1 and j % 2 == 0:
            return -GILL_D * rc * dome * math.sin(math.pi * prof[k][0] / 0.95)
        return 0.0

    lathe(B, origin, axis, pts, sides, spin, tone, P_CAP, ident, band, gills)


def agaric_profile(h, rs):
    rb = 1.75 * rs
    bz = min(rb, 0.55 * h / 2.8)
    prof = [(0.0, 0.0), (0.50 * rb, 0.12 * bz), (0.85 * rb, 0.45 * bz), (rb, 1.0 * bz),
            (0.97 * rb, 1.5 * bz), (0.86 * rb, 1.85 * bz), (0.92 * rb, 1.95 * bz),
            (0.70 * rb, 2.2 * bz), (1.08 * rs, 2.8 * bz)]
    if h >= 0.09:
        zr = 0.80 * h
        sk = 1.5 * rs
        prof += [(1.00 * rs, 0.40 * h), (0.95 * rs, zr - 0.10 * h),
                 (0.93 * rs + 0.0012, zr - 0.006), (0.92 * rs + sk, zr - 0.9 * sk),
                 (0.94 * rs + sk + 0.0015, zr - 0.85 * sk), (0.92 * rs + 0.25 * sk, zr + 0.002),
                 (0.88 * rs, zr + 0.012)]
    prof += [(0.85 * rs, h - 0.004), (0.0, h)]
    return prof


def add_agaric(B, G, spec, pl, ident, float_cap, lift):
    x, y, rc, h, rs, dome, lx, ly = spec
    gz = G.z(x, y)
    axis = Vector((lx, ly, 1.0)).normalized()
    origin = Vector((x, y, gz - AG_SINK)) + UP * lift
    prof = agaric_profile(h, rs)

    def stipe_band(k):
        return FLESH_IDX, min(1.0, prof[min(k + 1, len(prof) - 1)][1] / h)

    lathe(B, origin, axis, prof, 24, pl["spin"], pl["tone"], P_STIPE, ident, stipe_band)
    cap_o = origin + axis * (h - AG_BITE + (FLOAT_CAPS if float_cap else 0.0))
    add_cap(B, cap_o, axis, AG_CAP, AG_MARGIN, rc, dome, AG_SIDES, pl["spin"], AGARIC_IDX,
            pl["tone"], ident)


def add_honey(B, base, out, m, ident, float_cap, shift):
    """One honey-fungus mushroom: a thin, curved, ringed stipe out of its
    host and a convex, umbonate cap on its tip."""
    o = Vector((out.x, out.y, 0.0)).normalized()
    ca, sa = math.cos(m["yaw"]), math.sin(m["yaw"])
    o = Vector((o.x * ca - o.y * sa, o.x * sa + o.y * ca, 0.0))
    b = base + Vector((m["dx"], m["dy"], 0.0)) + shift
    n = 8
    pts = []
    radii = []
    zones = []
    for k in range(n):
        t = k / (n - 1)
        pts.append(b + o * (m["reach"] * t ** 0.6) + UP * (m["h"] * t))
        r = 0.0075 - 0.0020 * t
        if k == 5:
            r += 0.0028     # the ring on the stipe
        radii.append(r)
        zones.append(min(1.0, (t + 0.5 / (n - 1))))
    add_tube(B, pts, radii, HONEY_SIDES, FLESH_IDX, m["tone"], P_STIPE, ident, zones=zones)
    tan = (pts[-1] - pts[-2]).normalized()
    axis = (tan + UP * 0.8).normalized()
    cap_o = pts[-1] - axis * HONEY_BITE + axis * (FLOAT_CAPS if float_cap else 0.0)
    add_cap(B, cap_o, axis, HONEY_CAP, HONEY_MARGIN, m["rc"], m["dome"], HONEY_CAP_SIDES,
            m["spin"], HONEY_IDX, m["tone"], ident)


def add_leaf(B, G, lf, lift):
    c, nrm = G.hit(lf["x"], lf["y"])
    e1 = Vector((math.cos(lf["yaw"]), math.sin(lf["yaw"]), 0.0))
    e1 = (e1 - nrm * e1.dot(nrm)).normalized()
    # a leaf never lies dead flat: it rolls a few degrees about its midrib
    nrm = (nrm * math.cos(lf["tilt"]) + nrm.cross(e1) * math.sin(lf["tilt"])).normalized()
    e2 = nrm.cross(e1)
    ln = lf["len"]
    wd = ln * lf["wid"] * 0.5
    shape = ((-0.50, 0.0), (-0.30, 0.62), (0.0, 1.0), (0.28, 0.78), (0.50, 0.0),
             (0.28, -0.78), (0.0, -1.0), (-0.30, -0.62))
    up = Vector((0.0, 0.0, lift))
    outline = []
    for fx, fy in shape:
        curl = lf["curl"] * (fy * fy + 0.6 * (2.0 * fx) ** 2)
        outline.append(c + e1 * (fx * ln) + e2 * (fy * wd) + nrm * (0.0015 + curl) + up)
    add_lens(B, outline, c + nrm * 0.004 + up, c - nrm * LEAF_BITE + up, LITTER_IDX,
             lf["tone"], P_LEAF)


def add_fern(B, G, fd):
    base, _n = G.hit(fd["x"], fd["y"])
    base = base - Vector((0.0, 0.0, 0.03))
    hdir = Vector((math.cos(fd["yaw"]), math.sin(fd["yaw"]), 0.0))
    H, R = fd["h"], fd["reach"]
    pts = []
    steps = 12
    for k in range(steps):
        t = k / (steps - 1)
        z = H * (2.0 * t - t * t) * (1.0 - fd["curl"] * t ** 3) + 0.03 * min(1.0, t * 8.0)
        pts.append(base + hdir * (R * t ** 1.25) + UP * z)
    radii = [0.0060 - 0.0040 * (k / (steps - 1)) for k in range(steps)]
    add_tube(B, pts, radii, 5, FERN_IDX, fd["tone"], P_FERN)

    def at(t):
        x = t * (steps - 1)
        i = min(int(x), steps - 2)
        f = x - i
        return pts[i].lerp(pts[i + 1], f), (pts[i + 1] - pts[i]).normalized()

    for k in range(FERN_PINNAE):
        t = 0.22 + 0.73 * k / (FERN_PINNAE - 1)
        lp = fd["lp"] * max(0.18, math.sin(math.pi * (t - 0.12) / 0.92)) ** 0.7
        for side, dt in ((1.0, 0.0), (-1.0, 0.012)):
            p, tan = at(min(0.995, t + dt))
            bn = (UP - tan * UP.dot(tan)).normalized()
            # each pinna twists a little about the rachis: neighbours along
            # one side are otherwise translated copies in one blade plane.
            # Period 3, so any two neighbours differ by at least 0.1 rad.
            tw = 0.10 * ((k % 3) - 1) + (0.04 if side < 0 else 0.0) + fd["tw0"]
            bn = (bn * math.cos(tw) + tan.cross(bn) * math.sin(tw)).normalized()
            sd = tan.cross(bn) * side
            e1 = (sd * math.cos(0.35) + tan * math.sin(0.35) - bn * 0.12).normalized()
            e2 = (tan - e1 * tan.dot(e1)).normalized()
            e3 = e1.cross(e2).normalized()
            wp = 0.24 * lp
            dr = 0.22 + 0.05 * ((k + (1 if side < 0 else 0)) % 4)
            rib = 0.0022 + 0.0006 * (k % 2)
            outline = []
            for f, sg in ((0.0, 0.0), (0.22, 1.0), (0.5, 1.0), (0.78, 1.0), (1.0, 0.0),
                          (0.78, -1.0), (0.5, -1.0), (0.22, -1.0)):
                hw = wp * math.sin(math.pi * f) ** 0.6 if 0.0 < f < 1.0 else 0.0
                droop = dr * lp * f * f
                outline.append(p + e1 * (f * lp) + e2 * (sg * hw) - bn * droop)
            mid = p + e1 * (0.45 * lp) - bn * (dr * lp * 0.2)
            add_lens(B, outline, mid + e3 * rib, mid - e3 * rib, FERN_IDX, fd["tone"], P_FERN,
                     0.5 + 0.5 * t)


def add_twig(B, G, spec, tw):
    x, y, yaw_deg, ln, r = spec
    yaw = math.radians(yaw_deg)
    d = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    side = Vector((-d.y, d.x, 0.0))
    pts = []
    n = 7
    for k in range(n):
        t = k / (n - 1)
        q = Vector((x, y, 0.0)) + d * (ln * (t - 0.5)) + side * (tw["bend"] * ln * (t * t - t))
        pts.append(Vector((q.x, q.y, G.z(q.x, q.y) + 0.30 * r)))
    radii = [r * (1.0 - 0.45 * k / (n - 1)) for k in range(n)]
    add_tube(B, pts, radii, 6, TWIG_IDX, tw["tone"], P_TWIG)
    # a side shoot, forked off the middle and lying on the soil
    m = pts[3]
    fdir = (d * math.cos(0.6) + side * math.sin(0.6)).normalized()
    fl = ln * tw["fork"] * 0.5
    fpts = []
    for k in range(4):
        t = k / 3.0
        q = m + fdir * (fl * t)
        fpts.append(Vector((q.x, q.y, G.z(q.x, q.y) + 0.30 * r * 0.6 + (0.4 * r if k == 0 else 0.0))))
    add_tube(B, fpts, [r * 0.62, r * 0.55, r * 0.48, r * 0.40], 6, TWIG_IDX, tw["tone"], P_TWIG)


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


def add_pebble(B, G, spec, pb):
    """A broken pebble: a cube-sphere cut by three cleavage planes and a
    flat bed, bedded in the soil."""
    x, y, r = spec
    h = 0.62 * r
    jit = pb["jit"]
    yaw = pb["yaw"]
    dirs, quads = cube_sphere(4)
    cuts = []
    for k in range(3):
        a = yaw + TAU * (k + 0.3 * jit[k]) / 3.0
        nrm = Vector((math.cos(a), math.sin(a), 0.55 + 0.4 * jit[k + 3])).normalized()
        cuts.append((nrm, r * (0.62 + 0.12 * jit[min(k + 5, 7)])))
    verts = []
    for dvec in dirs:
        wob = 1.0 + 0.08 * math.sin(3.1 * dvec.x + 5.0 * jit[6]) * math.cos(2.7 * dvec.y + 3.0 * jit[7])
        p = Vector((dvec.x * r * wob, dvec.y * r * 0.82 * wob, dvec.z * h))
        for nrm, off in cuts:
            over = p.dot(nrm) - off
            if over > 0.0:
                p -= nrm * over
        p.z = max(p.z, -0.45 * h)
        p = Matrix.Rotation(yaw, 3, "Z") @ p
        verts.append(B.vert(Vector((x, y, 0.0)) + p))
    for q in quads:
        B.face([verts[i] for i in q], STONE_IDX, jit[0], P_PEBBLE)
    bed = [v for v in verts if v.co.z < min(w.co.z for w in verts) + 1e-6]
    over = max(v.co.z - G.z(v.co.x, v.co.y) for v in bed)
    for v in verts:
        v.co.z -= over + STONE_BED


# --------------------------------------------------------------------------
# The whole piece
# --------------------------------------------------------------------------

def build_mesh(name, plan, detail="low", **flags):
    bm = bmesh.new()
    try:
        B = Builder(bm)
        sides = STUMP_SIDES_HIGH if detail == "high" else STUMP_SIDES
        add_soil(B)
        bm.faces.ensure_lookup_table()
        bm.normal_update()   # FromBMesh reads the stored face normals
        G = Ground(BVHTree.FromBMesh(bm))

        surf, soil0 = build_stump(B, plan, sides, G, flags)
        roots = build_roots(B, plan, G, flags["arch_roots"])

        rot = math.pi if flags["sunny_moss"] else 0.0
        for k, patch in enumerate(plan["moss"]):
            add_moss(B, surf, patch, rot, MOSS_BITE + MOSS_STAGGER * k, soil0)

        off = FLOAT_BRACKETS if flags["float_brackets"] else 0.0
        for k, shelf in enumerate(plan["shelves"]):
            add_shelf(B, surf, shelf, off, SHELF_BITE + SHELF_STAGGER * (k % 3), soil0, k + 1)

        lift = FLOAT_MUSH if flags["float_mushrooms"] else 0.0
        ident = 0
        for spec, pl in zip(AGARICS, plan["agarics"]):
            ident += 1
            add_agaric(B, G, spec, pl, ident, flags["float_caps"], lift)
        for cl in plan["honey"]:
            if cl["host"] == "root":
                pts, radii = roots[cl["which"]]
                x = cl["station"] * (len(pts) - 1)
                i = min(int(x), len(pts) - 2)
                f = x - i
                c = pts[i].lerp(pts[i + 1], f)
                rad = radii[i] + (radii[i + 1] - radii[i]) * f
                out = hor(pts[i + 1] - pts[i])
                base = c + UP * (rad - HOST_DEPTH)
                shift = UP * lift
            else:
                # on the foot, ``station`` above the soil at the bark
                a = math.radians(cl["which"])
                p0 = surf.point(soil0, a)
                zg = G.z(p0.x, p0.y) + cl["station"]
                p = surf.point(zg, a)
                n = surf.normal(zg, a)
                base = p - n * HOST_DEPTH
                out = hor(n)
                shift = hor(n).normalized() * lift
            for m in cl["members"]:
                ident += 1
                add_honey(B, base, out, m, ident, flags["float_caps"], shift)

        lift = FLOAT_COVER if flags["float_cover"] else 0.0
        for lf in plan["leaves"]:
            add_leaf(B, G, lf, lift)
        for fd in plan["ferns"]:
            add_fern(B, G, fd)
        for spec, tw in zip(TWIGS, plan["twigs"]):
            add_twig(B, G, spec, tw)
        for spec, pb in zip(PEBBLES, plan["pebbles"]):
            add_pebble(B, G, spec, pb)

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
        # Everything organic is smooth-shaded except what is broken: the
        # torn holding wood and the cleaved pebbles are facets. Every
        # material boundary and every fold sharper than 70 degrees is a hard
        # edge, so the sawn rim stays crisp against the bark.
        part = B.L["Part"]
        for face in bm.faces:
            face.smooth = int(round(face[part])) not in (P_HINGE, P_PEBBLE)
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(70.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj, (cx, cy, zmin)


def build_collider_source(name, shift, plan):
    """The stump alone, unfurrowed, down to the soil: players walk through
    ferns and step over roots."""
    bm = bmesh.new()
    try:
        B = Builder(bm)
        rings = []
        sides = 16
        soil0 = soil_height(0.0, 0.0)
        for zrel in (-0.02, 0.03, 0.08, 0.15, 0.25, 0.38, CUT_H):
            ring = []
            for j in range(sides):
                a = TAU * j / sides
                r = stump_radius(zrel, a)
                ring.append(B.vert(Vector((r * math.cos(a), r * math.sin(a), soil0 + zrel))))
            rings.append(ring)
        for r0, r1 in zip(rings, rings[1:]):
            for j in range(sides):
                m = (j + 1) % sides
                B.face((r0[j], r0[m], r1[m], r1[j]), BARK_IDX, 0.0, P_STUMP)
        B.face(tuple(reversed(rings[0])), BARK_IDX, 0.0, P_STUMP)
        B.face(tuple(rings[-1]), BARK_IDX, 0.0, P_STUMP)
        triangulate_ngons(bm)
        for v in bm.verts:
            v.co -= Vector(shift)
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


def voronoi(nt, vec, scale, randomness=1.0):
    node = nt.nodes.new("ShaderNodeTexVoronoi")
    node.inputs["Scale"].default_value = scale
    node.inputs["Randomness"].default_value = randomness
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Distance"]


def wave(nt, vec, direction, scale, distortion, detail=3.0):
    node = nt.nodes.new("ShaderNodeTexWave")
    node.wave_type = "BANDS"
    node.bands_direction = direction
    node.inputs["Scale"].default_value = scale
    node.inputs["Distortion"].default_value = distortion
    node.inputs["Detail"].default_value = detail
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]


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


def damp(nt, col, coord, rgb, amount, lo=0.10, hi=0.32):
    """Wood and bark darken where they meet the wet soil."""
    fac = remap(nt, height(nt, coord), lo, hi, amount, 0.0)
    return mix_color(nt, col, rgb, fac)


def bark_material():
    mat, nt, bsdf, coord = surface("StumpBark")
    # Plates: ridged noise stretched up the bole (Z), so the fissures run
    # with the grain and branch, broken across by short horizontal cracks.
    plates = noise(nt, mapping(nt, coord, scale=(7.0, 7.0, 1.5)), 3.0, 8.0, 0.62)
    fn = noise(nt, mapping(nt, coord, scale=(13.0, 13.0, 0.9)), 1.0, 6.0, 0.58)
    ridge = math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", fn, 0.5), 0.0)
    furrow_f = remap(nt, ridge, 0.0, 0.10, 1.0, 0.0)
    brk = noise(nt, mapping(nt, coord, scale=(3.0, 3.0, 24.0)), 2.0, 4.0, 0.5)
    cross = remap(nt, math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", brk, 0.5), 0.0),
                  0.0, 0.035, 0.85, 0.0)
    fine = noise(nt, mapping(nt, coord, scale=(34.0, 34.0, 5.0)), 2.0, 6.0, 0.55)
    col = ramp(nt, plates, ((0.30, (0.052, 0.042, 0.034)), (0.50, (0.090, 0.074, 0.059)),
                            (0.70, (0.135, 0.116, 0.095)), (0.85, (0.175, 0.155, 0.130))))
    col = mix_color(nt, col, (0.012, 0.009, 0.007), furrow_f)
    col = mix_color(nt, col, (0.016, 0.012, 0.010), cross)
    col = mix_color(nt, col, (0.030, 0.024, 0.019), remap(nt, fine, 0.35, 0.65, 0.4, 0.0))
    # crustose lichen: a few soft grey-green blots on the plates
    lich = noise(nt, mapping(nt, coord, scale=(1.4, 1.4, 1.4)), 3.0, 5.0, 0.55)
    col = mix_color(nt, col, (0.17, 0.18, 0.13), remap(nt, lich, 0.63, 0.73, 0.0, 0.55))
    col = damp(nt, col, coord, (0.026, 0.028, 0.014), 0.65)
    # where a boundary face crosses into a peel, the torn edge shows the
    # sapwood under a dark rim of broken bark
    peel = attr(nt, "Peel")
    col = mix_color(nt, col, (0.010, 0.008, 0.006), remap(nt, peel, 0.36, 0.47, 0.0, 1.0))
    col = mix_color(nt, col, (0.36, 0.25, 0.14), remap(nt, peel, 0.49, 0.51, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, plates, 0.35, 0.8, 0.95, 0.78), bsdf.inputs["Roughness"])
    bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "MULTIPLY", furrow_f, -1.0),
                             math_node(nt, "ADD", math_node(nt, "MULTIPLY", plates, 0.5),
                                       math_node(nt, "MULTIPLY", cross, -0.4))), 0.9, 0.03)
    return mat


def wood_material():
    mat, nt, bsdf, coord = surface("StumpWood")
    grain = attr(nt, "EndGrain")
    # sapwood under the peeled bark: pale, streaked up the grain (Z)
    streak = noise(nt, mapping(nt, coord, scale=(22.0, 22.0, 1.2)), 2.0, 6.0, 0.6)
    sap = ramp(nt, streak, ((0.30, (0.19, 0.13, 0.075)), (0.55, (0.28, 0.20, 0.12)),
                            (0.80, (0.34, 0.27, 0.18))))
    sap = mix_color(nt, sap, (0.20, 0.19, 0.17), remap(nt, noise(nt, coord, 4.0, 4.0, 0.55), 0.4, 0.7, 0.1, 0.55))
    holes = noise(nt, coord, 40.0, 2.0, 0.5)
    sap = mix_color(nt, sap, (0.06, 0.035, 0.02), remap(nt, holes, 0.72, 0.76, 0.0, 0.9))
    # torn holding wood: long pale fibres
    fib = noise(nt, mapping(nt, coord, scale=(60.0, 60.0, 3.0)), 2.0, 4.0, 0.6)
    broken = ramp(nt, fib, ((0.35, (0.26, 0.18, 0.10)), (0.60, (0.46, 0.36, 0.24)),
                            (0.80, (0.56, 0.47, 0.34))))
    # the saw cut: growth rings on the Radial attribute round a dark
    # heartwood, a pale sapwood band, weathered grey toward the rim
    radial = attr(nt, "Radial")
    # growth rings: uneven years (the ring phase wanders with two noises)
    # drawn as thin dark latewood lines, not sine bands
    wob = noise(nt, coord, 3.0, 3.0, 0.5)
    wob2 = noise(nt, coord, 11.0, 2.0, 0.5)
    phase = math_node(nt, "ADD", math_node(nt, "MULTIPLY", radial, TAU * 24.0),
                      math_node(nt, "ADD", math_node(nt, "MULTIPLY", wob, 9.0),
                                math_node(nt, "MULTIPLY", wob2, 2.5)))
    ringv = math_node(nt, "SINE", phase, 0.0)
    late = remap(nt, ringv, 0.62, 0.95, 0.0, 1.0)
    endcol = ramp(nt, radial, ((0.02, (0.05, 0.025, 0.013)), (0.06, (0.14, 0.075, 0.036)),
                               (0.50, (0.17, 0.095, 0.048)), (0.62, (0.22, 0.15, 0.085)),
                               (0.76, (0.27, 0.21, 0.14)), (0.96, (0.29, 0.23, 0.155))))
    endcol = mix_color(nt, endcol, (0.070, 0.040, 0.022), math_node(nt, "MULTIPLY", late, 0.75))
    # chainsaw marks: faint streaks across the face, one direction
    saw = noise(nt, mapping(nt, coord, scale=(3.0, 55.0, 3.0), rot=(0.0, 0.0, 0.5)), 2.0, 3.0, 0.5)
    endcol = mix_color(nt, endcol, (0.10, 0.07, 0.045), remap(nt, saw, 0.55, 0.75, 0.0, 0.18))
    # years in the open: silver-grey weathering from the rim in, in blotches
    weather = noise(nt, coord, 3.0, 4.0, 0.55)
    wfac = math_node(nt, "ADD", remap(nt, radial, 0.35, 1.0, 0.0, 0.50),
                     remap(nt, weather, 0.38, 0.66, 0.0, 0.50))
    endcol = mix_color(nt, endcol, (0.200, 0.192, 0.176), wfac)
    ringv = late
    stain = noise(nt, coord, 5.0, 5.0, 0.6)
    endcol = mix_color(nt, endcol, (0.07, 0.055, 0.04), remap(nt, stain, 0.60, 0.72, 0.0, 0.6))
    algae = noise(nt, coord, 2.5, 3.0, 0.5)
    endcol = mix_color(nt, endcol, (0.07, 0.10, 0.035),
                       math_node(nt, "MULTIPLY", remap(nt, radial, 0.80, 1.0, 0.0, 0.7),
                                 remap(nt, algae, 0.50, 0.65, 0.0, 1.0)))
    # the drying checks: a thin dark crack along the floor of each groove
    chk = attr(nt, "Check")
    endcol = mix_color(nt, endcol, (0.018, 0.012, 0.008), remap(nt, chk, 0.02, 0.35, 0.0, 0.45))
    endcol = mix_color(nt, endcol, (0.008, 0.005, 0.004), remap(nt, chk, 0.80, 0.95, 0.0, 1.0))
    col = mix_color(nt, sap, broken, remap(nt, grain, 0.2, 0.35, 0.0, 1.0))
    col = mix_color(nt, col, endcol, remap(nt, grain, 0.6, 0.9, 0.0, 1.0))
    col = damp(nt, col, coord, (0.10, 0.065, 0.040), 0.45)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.84
    bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "MULTIPLY", ringv, -0.25),
                             math_node(nt, "ADD", math_node(nt, "MULTIPLY", saw, 0.15),
                                       math_node(nt, "MULTIPLY", streak, 0.4))), 0.45, 0.01)
    return mat


def moss_material():
    mat, nt, bsdf, coord = surface("Moss")
    tone = attr(nt, "Tone")
    base = ramp(nt, tone, ((0.0, (0.045, 0.095, 0.015)), (0.5, (0.080, 0.150, 0.022)),
                           (1.0, (0.120, 0.200, 0.030))))
    fuzz = noise(nt, coord, 140.0, 4.0, 0.7)
    tufts = noise(nt, coord, 26.0, 4.0, 0.6)
    patchy = noise(nt, coord, 6.0, 3.0, 0.5)
    col = mix_color(nt, base, (0.060, 0.070, 0.020), remap(nt, patchy, 0.40, 0.65, 0.55, 0.0))
    col = mix_color(nt, col, (0.018, 0.040, 0.010), remap(nt, fuzz, 0.35, 0.65, 0.65, 0.0))
    col = mix_color(nt, col, (0.20, 0.27, 0.045), remap(nt, tufts, 0.58, 0.74, 0.0, 0.65))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    bump(nt, bsdf, math_node(nt, "ADD", fuzz, math_node(nt, "MULTIPLY", tufts, 1.6)), 0.9, 0.008)
    return mat


def bracket_material():
    mat, nt, bsdf, coord = surface("TurkeyTail")
    # Zone: 0..1 across the cap from the bark to the margin; 2.0 on the pore
    # surface. Turkey tail: narrow concentric bands of brown, rust, tan and
    # blue-grey, a cream growing margin, a cream pore surface.
    zone = attr(nt, "Zone")
    tone = attr(nt, "Tone")
    zone = math_node(nt, "ADD", zone, math_node(nt, "MULTIPLY", tone, 0.04))
    zf = math_node(nt, "MULTIPLY", zone, 0.5)
    col = ramp(nt, zf, ((0.000, (0.050, 0.030, 0.018)), (0.060, (0.180, 0.090, 0.035)),
                        (0.110, (0.070, 0.045, 0.030)), (0.160, (0.330, 0.200, 0.090)),
                        (0.210, (0.160, 0.170, 0.175)), (0.260, (0.060, 0.050, 0.045)),
                        (0.310, (0.380, 0.280, 0.160)), (0.360, (0.140, 0.150, 0.165)),
                        (0.410, (0.250, 0.130, 0.055)), (0.445, (0.480, 0.400, 0.280)),
                        (0.475, (0.800, 0.760, 0.640)), (0.600, (0.820, 0.790, 0.690)),
                        (0.950, (0.760, 0.720, 0.620)), (1.000, (0.740, 0.700, 0.600))))
    velvet = noise(nt, coord, 70.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.05, 0.035, 0.025), remap(nt, velvet, 0.3, 0.7, 0.25, 0.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.78
    bump(nt, bsdf, velvet, 0.3, 0.003)
    return mat


def agaric_material():
    mat, nt, bsdf, coord = surface("FlyAgaric")
    # Zone: 1 at the crown to 2 at the margin.
    zone = attr(nt, "Zone")
    col = ramp(nt, math_node(nt, "SUBTRACT", zone, 1.0),
               ((0.00, (0.40, 0.018, 0.008)), (0.35, (0.66, 0.040, 0.012)),
                (0.80, (0.82, 0.14, 0.025)), (1.00, (0.86, 0.30, 0.050))))
    # the warts: remnants of the universal veil, white flecks thinning out
    # toward the margin
    dist = voronoi(nt, coord, 52.0, 0.9)
    density = remap(nt, zone, 1.3, 1.95, 0.30, 0.20)
    wart = remap(nt, math_node(nt, "SUBTRACT", dist, density), -0.06, 0.0, 1.0, 0.0)
    wart = math_node(nt, "MULTIPLY", wart, remap(nt, zone, 1.85, 1.98, 1.0, 0.0))
    col = mix_color(nt, col, (0.88, 0.84, 0.72), wart)
    streak = noise(nt, coord, 90.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.50, 0.03, 0.01), remap(nt, streak, 0.55, 0.75, 0.0, 0.25))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, wart, 0.0, 1.0, 0.32, 0.80), bsdf.inputs["Roughness"])
    bump(nt, bsdf, wart, 0.6, 0.002)
    return mat


def honey_material():
    mat, nt, bsdf, coord = surface("HoneyFungus")
    zone = attr(nt, "Zone")
    tone = attr(nt, "Tone")
    col = ramp(nt, math_node(nt, "SUBTRACT", zone, 1.0),
               ((0.00, (0.20, 0.10, 0.035)), (0.25, (0.34, 0.19, 0.060)),
                (0.65, (0.58, 0.38, 0.12)), (1.00, (0.70, 0.52, 0.19))))
    col = mix_color(nt, col, (0.45, 0.25, 0.07), remap(nt, tone, 0.7, 1.0, 0.0, 0.35))
    # dark fibrous scales on the crown
    scales = noise(nt, coord, 160.0, 2.0, 0.5)
    sc = math_node(nt, "MULTIPLY", remap(nt, scales, 0.55, 0.65, 0.0, 1.0),
                   remap(nt, zone, 1.0, 1.6, 0.85, 0.0))
    col = mix_color(nt, col, (0.12, 0.06, 0.025), sc)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.52
    bump(nt, bsdf, scales, 0.25, 0.002)
    return mat


def flesh_material():
    mat, nt, bsdf, coord = surface("MushroomFlesh")
    # Zone: 0..1 up a stipe, 2 on the gills. Tone under 0.5 is a fly agaric
    # (white), over it a honey fungus (dark brown foot, cream top, cream gills).
    zone = attr(nt, "Zone")
    tone = attr(nt, "Tone")
    zf = math_node(nt, "MULTIPLY", zone, 0.5)
    white = ramp(nt, zf, ((0.00, (0.62, 0.56, 0.42)), (0.10, (0.80, 0.76, 0.66)),
                          (0.45, (0.86, 0.84, 0.77)), (0.60, (0.90, 0.88, 0.82)),
                          (1.00, (0.90, 0.88, 0.82))))
    honey = ramp(nt, zf, ((0.00, (0.12, 0.065, 0.030)), (0.18, (0.26, 0.15, 0.065)),
                          (0.38, (0.60, 0.46, 0.26)), (0.50, (0.74, 0.64, 0.44)),
                          (0.60, (0.72, 0.62, 0.42)), (1.00, (0.68, 0.58, 0.38))))
    col = mix_color(nt, white, honey, remap(nt, tone, 0.45, 0.55, 0.0, 1.0))
    fib = noise(nt, mapping(nt, coord, scale=(60.0, 60.0, 8.0)), 2.0, 4.0, 0.5)
    col = mix_color(nt, col, (0.30, 0.24, 0.16), remap(nt, fib, 0.60, 0.75, 0.0, 0.2))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.60
    return mat


def soil_material():
    mat, nt, bsdf, coord = surface("ForestSoil")
    clods = noise(nt, coord, 6.0, 6.0, 0.62)
    crumbs = noise(nt, coord, 70.0, 3.0, 0.6)
    col = ramp(nt, clods, ((0.30, (0.030, 0.022, 0.016)), (0.55, (0.060, 0.043, 0.030)),
                           (0.80, (0.095, 0.072, 0.052))))
    col = mix_color(nt, col, (0.018, 0.013, 0.010), remap(nt, crumbs, 0.35, 0.55, 0.6, 0.0))
    duff = noise(nt, mapping(nt, coord, scale=(40.0, 8.0, 40.0)), 3.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.16, 0.11, 0.06), remap(nt, duff, 0.66, 0.74, 0.0, 0.6))
    film = noise(nt, coord, 2.2, 4.0, 0.55)
    col = mix_color(nt, col, (0.040, 0.060, 0.018), remap(nt, film, 0.50, 0.62, 0.0, 0.75))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.96
    bump(nt, bsdf, math_node(nt, "ADD", clods, math_node(nt, "MULTIPLY", crumbs, 0.6)),
         0.6, 0.01)
    return mat


def litter_material():
    mat, nt, bsdf, coord = surface("LeafLitter")
    tone = attr(nt, "Tone")
    col = ramp(nt, tone, ((0.0, (0.060, 0.030, 0.012)), (0.40, (0.150, 0.070, 0.022)),
                          (0.70, (0.300, 0.120, 0.030)), (1.0, (0.450, 0.300, 0.070))))
    blot = noise(nt, coord, 35.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.08, 0.04, 0.015), remap(nt, blot, 0.45, 0.75, 0.0, 0.5))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.75
    return mat


def fern_material():
    mat, nt, bsdf, coord = surface("Fern")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    col = ramp(nt, tone, ((0.0, (0.040, 0.120, 0.020)), (0.5, (0.070, 0.180, 0.030)),
                          (1.0, (0.110, 0.230, 0.040))))
    col = mix_color(nt, col, (0.16, 0.30, 0.06), remap(nt, zone, 0.8, 1.0, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    return mat


def stone_material():
    mat, nt, bsdf, coord = surface("Pebble")
    tone = attr(nt, "Tone")
    mott = noise(nt, coord, 14.0, 5.0, 0.6)
    speck = noise(nt, coord, 160.0, 2.0, 0.5)
    col = ramp(nt, mott, ((0.30, (0.13, 0.13, 0.12)), (0.55, (0.22, 0.21, 0.19)),
                          (0.80, (0.30, 0.29, 0.26))))
    col = mix_color(nt, col, (0.36, 0.30, 0.22), remap(nt, tone, 0.5, 1.0, 0.0, 0.35))
    col = mix_color(nt, col, (0.05, 0.05, 0.05), remap(nt, speck, 0.60, 0.70, 0.0, 0.7))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, speck, 0.3, 0.7, 0.9, 0.7), bsdf.inputs["Roughness"])
    bump(nt, bsdf, math_node(nt, "ADD", mott, math_node(nt, "MULTIPLY", speck, 0.4)), 0.4, 0.004)
    return mat


def twig_material():
    mat, nt, bsdf, coord = surface("Twig")
    tone = attr(nt, "Tone")
    n = noise(nt, mapping(nt, coord, scale=(30.0, 30.0, 30.0)), 3.0, 5.0, 0.6)
    col = ramp(nt, n, ((0.3, (0.09, 0.07, 0.055)), (0.7, (0.20, 0.16, 0.12))))
    col = mix_color(nt, col, (0.26, 0.24, 0.21), remap(nt, tone, 0.5, 1.0, 0.0, 0.5))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    bump(nt, bsdf, n, 0.4, 0.003)
    return mat


def stump_materials():
    """Twelve slots, in index order: shared by the check and the render."""
    return (bark_material(), wood_material(), moss_material(), bracket_material(),
            agaric_material(), honey_material(), flesh_material(), soil_material(),
            litter_material(), fern_material(), stone_material(), twig_material())


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


def face_floats(me, name):
    vals = [0.0] * len(me.polygons)
    me.attributes[name].data.foreach_get("value", vals)
    return vals


def vert_floats(me, name):
    vals = [0.0] * len(me.vertices)
    me.attributes[name].data.foreach_get("value", vals)
    return vals


class Shell:
    def __init__(self, me, verts, polys, part, ident):
        self.verts = verts
        self.part = part
        self.ident = ident
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        remap_ = {vi: n for n, vi in enumerate(verts)}
        self.tree = BVHTree.FromPolygons(
            [tuple(p) for p in pts], [[remap_[v] for v in p.vertices] for p in polys])
        self.polys = polys

    def holds(self, q, pad=0.0):
        return (self.lo.x - pad <= q.x <= self.hi.x + pad and self.lo.y - pad <= q.y <= self.hi.y + pad
                and self.lo.z - pad <= q.z <= self.hi.z + pad)


def classify(me):
    groups = shells(me)
    part = face_floats(me, "Part")
    ident = face_floats(me, "Ident")
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(p)
    parts = []
    for g, ps in zip(groups, polys):
        if not ps:
            continue
        parts.append(Shell(me, g, ps, int(round(part[ps[0].index])), int(round(ident[ps[0].index]))))
    out = {"all": parts, "groups": groups}

    def of(p):
        return [s for s in parts if s.part == p]

    for key, p in (("soil", P_SOIL), ("stump", P_STUMP), ("roots", P_ROOT), ("hinge", P_HINGE),
                   ("moss", P_MOSS), ("brackets", P_BRACKET), ("stipes", P_STIPE),
                   ("caps", P_CAP), ("leaves", P_LEAF), ("ferns", P_FERN), ("twigs", P_TWIG),
                   ("pebbles", P_PEBBLE)):
        out[key] = of(p)
    return out


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 8.0)), Vector((0.0, 0.0, -1.0)), 30.0)
    return None if loc is None else loc.z


PARITY_DIRS = (Vector((0.31, 0.47, 0.83)).normalized(), Vector((-0.62, 0.21, -0.75)).normalized(),
               Vector((0.55, -0.79, 0.27)).normalized())


def inside(tree, p):
    """Ray parity, by majority over three directions: an odd number of
    crossings out of a closed shell."""
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


def seal_audit(stump, soil):
    """Sectors round the stump's centroid holding a stump vertex at least
    SEAL_EPS under the soil straight above it."""
    cx = sum(p.x for p in stump.pts) / len(stump.pts)
    cy = sum(p.y for p in stump.pts) / len(stump.pts)
    sealed = set()
    for p in stump.pts:
        g = ray_down(soil.tree, p.x, p.y)
        if g is not None and g - p.z >= SEAL_EPS:
            a = math.atan2(p.y - cy, p.x - cx) + math.pi
            sealed.add(int(a / TAU * SEAL_SECTORS) % SEAL_SECTORS)
    return len(sealed), Vector((cx, cy, 0.0))


def cap_audit(cls):
    """Per cap: the deepest vertex of its own stipe inside it."""
    stipes = {s.ident: s for s in cls["stipes"]}
    out = []
    for cap in cls["caps"]:
        st = stipes.get(cap.ident)
        best = -9.0
        if st is not None:
            for q in st.pts:
                if cap.holds(q, 0.03):
                    best = max(best, signed_depth(cap.tree, q))
        out.append(best)
    return out


def cut_audit(me, cls):
    """Plane fit on the sawn face (end-grain faces, checks left out), its
    tilt; the stump's diameter across the bark just under the cut; the
    cut's height above the soil at the fit's centre."""
    grain = face_floats(me, "EndGrain")
    part = face_floats(me, "Part")
    chk = vert_floats(me, "Check")
    ids = set()
    for p in me.polygons:
        if int(round(part[p.index])) == P_STUMP and grain[p.index] > 0.9:
            ids.update(p.vertices)
    pts = [me.vertices[i].co for i in ids if chk[i] < 0.01]
    n = len(pts)
    sx = sum(p.x for p in pts) / n
    sy = sum(p.y for p in pts) / n
    sz = sum(p.z for p in pts) / n
    sxx = sum((p.x - sx) ** 2 for p in pts)
    syy = sum((p.y - sy) ** 2 for p in pts)
    sxy = sum((p.x - sx) * (p.y - sy) for p in pts)
    sxz = sum((p.x - sx) * (p.z - sz) for p in pts)
    syz = sum((p.y - sy) * (p.z - sz) for p in pts)
    det = sxx * syy - sxy * sxy
    a = (sxz * syy - syz * sxy) / det
    b = (syz * sxx - sxz * sxy) / det
    tilt = math.degrees(math.atan(math.hypot(a, b)))
    stump = cls["stump"][0]
    band = [p for p in stump.pts
            if 0.005 <= (sz + a * (p.x - sx) + b * (p.y - sy)) - p.z <= 0.05]
    dx = max(p.x for p in band) - min(p.x for p in band)
    dy = max(p.y for p in band) - min(p.y for p in band)
    g = ray_down(cls["soil"][0].tree, sx, sy)
    ht = sz - (g if g is not None else 0.0)
    return tilt, 0.5 * (dx + dy), ht, n


def root_audit(cls):
    """Per root: its vertices outside the stump, binned by distance from
    the stump's axis; every bin's most-buried vertex under the soil."""
    soil = cls["soil"][0]
    stump = cls["stump"][0]
    cx = sum(p.x for p in stump.pts) / len(stump.pts)
    cy = sum(p.y for p in stump.pts) / len(stump.pts)
    worst = []
    stations = 0
    for rt in cls["roots"]:
        bins = {}
        joint = set()
        for p in rt.pts:
            k = int(math.hypot(p.x - cx, p.y - cy) / ROOT_STATION)
            if stump.holds(p) and inside(stump.tree, p):
                # where the root leaves the buttress the stump seals it
                joint.add(k)
                continue
            g = ray_down(soil.tree, p.x, p.y)
            if g is not None:
                bins[k] = max(bins.get(k, -9.0), g - p.z)
        free = [b for k, b in bins.items() if k not in joint]
        stations += len(free)
        worst.append(min(free) if free else -9.0)
    return worst, stations


def host_audit(cls, hosts):
    """Per stipe: its deepest vertex in its host — under the soil straight
    above it, or inside the root or stump it grows out of."""
    soil = cls["soil"][0]
    roots = {s.ident: s for s in cls["roots"]}
    stump = cls["stump"][0]
    out = []
    for st in cls["stipes"]:
        kind, which = hosts.get(st.ident, ("?", 0))
        best = -9.0
        if kind == "soil":
            for p in st.pts:
                g = ray_down(soil.tree, p.x, p.y)
                if g is not None:
                    best = max(best, g - p.z)
        else:
            host = roots.get(which) if kind == "root" else stump
            if host is not None:
                for p in st.pts:
                    if host.holds(p, 0.002):
                        best = max(best, signed_depth(host.tree, p))
        out.append(best)
    return out


def fungus_audit(fungi, stump):
    """Per shelf: its deepest vertex inside the stump shell (signed distance
    to the nearest bark face along that face's outward normal)."""
    out = []
    for f in fungi:
        deepest = -9.0
        for p in f.pts:
            loc, nrm, _i, _d = stump.tree.find_nearest(p)
            if loc is None:
                continue
            deepest = max(deepest, -(p - loc).dot(nrm))
        out.append(deepest)
    return out


def moss_audit(moss, stump):
    """Area fraction of moss top faces (facing away from the bark under
    them) whose normal faces up or north, into the shade."""
    top = 0.0
    good = 0.0
    for m in moss:
        for poly in m.polys:
            loc, ln, _i, _d = stump.tree.find_nearest(poly.center)
            if loc is None or poly.normal.dot(ln) < MOSS_TOP_DOT:
                continue
            a = poly.area
            top += a
            if poly.normal.z > MOSS_UP_Z or poly.normal.y > MOSS_SHADE_Y:
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
    """Ground cover (leaves, fern rachises and pinnae, twigs, pebbles)
    joined to the soil through BVH overlaps: how many shells are not."""
    soil = cls["soil"][0]
    cover = cls["leaves"] + cls["ferns"] + cls["twigs"] + cls["pebbles"]
    parts = [soil] + cover
    roots = union_components(parts)
    loose = [p for p, r in zip(parts[1:], roots[1:]) if r != roots[0]]
    loose_leaves = sum(1 for p in loose if p.part == P_LEAF)
    return len(cover), len(loose), loose_leaves


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, 0.3))
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
        interior = [g for g in (result.get("geom_interior") or []) if g.is_valid]
        if interior:
            bmesh.ops.delete(bm, geom=interior, context="VERTS")
        unused = [g for g in (result.get("geom_unused") or []) if g.is_valid]
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
    img = bpy.data.images.new("StumpNrm", size, size, alpha=True, float_buffer=False)
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


FLAG_NAMES = ("perch_stump", "float_caps", "tilt_cut", "fat_stump", "arch_roots",
              "float_mushrooms", "float_brackets", "sunny_moss", "float_cover")


def mushroom_hosts(plan):
    hosts = {}
    ident = 0
    for _spec in AGARICS:
        ident += 1
        hosts[ident] = ("soil", 0)
    for cl in plan["honey"]:
        for _m in cl["members"]:
            ident += 1
            hosts[ident] = ("root", cl["which"] + 1) if cl["host"] == "root" else ("stump", 0)
    return hosts


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = {k: bool(flags.get(k, False)) for k in FLAG_NAMES}
    plan = plan_stump()
    low, shift = build_mesh("StumpLow", plan, "low", **flags)
    high, _shift = build_mesh("StumpHigh", plan, "high", **flags)
    mats = stump_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    bark = mats[BARK_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none2 = (None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("stump mesh did not build", 3),) + none2

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
    if len(cls["stump"]) != 1 or len(cls["soil"]) != 1:
        return (fail(f"stump or soil shell not found: stump {len(cls['stump'])} "
                     f"soil {len(cls['soil'])}", 3),) + none2
    stump = cls["stump"][0]
    soil = cls["soil"][0]
    nsealed, _centre = seal_audit(stump, soil)
    caps = cap_audit(cls)
    tilt, diam, ht, ncut = cut_audit(low.data, cls)
    root_beds, root_stations = root_audit(cls)
    hosts = mushroom_hosts(plan)
    host_depths = host_audit(cls, hosts)
    depths = fungus_audit(cls["brackets"], stump)
    moss_frac, moss_top = moss_audit(cls["moss"], stump)
    ncover, nloose, loose_leaves = cover_audit(cls)

    img, _tex = setup_bake_image(low, bark)
    if img is None:
        return (fail("stump has no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "StumpLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "StumpLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("StumpColSrc", shift, plan)
    collider = convex_hull_collider(collider_src, "StumpCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_mushroom_stump_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    n_mush = len(hosts)
    expected_cover = (len(plan["leaves"]) + len(plan["ferns"]) * (1 + 2 * FERN_PINNAE)
                      + 2 * len(TWIGS) + len(PEBBLES))
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
    print(f"measured shells={len(cls['all'])} roots={len(cls['roots'])} "
          f"hinge={len(cls['hinge'])} moss={len(cls['moss'])} brackets={len(cls['brackets'])} "
          f"stipes={len(cls['stipes'])} caps={len(cls['caps'])} leaves={len(cls['leaves'])} "
          f"ferns={len(cls['ferns'])} twigs={len(cls['twigs'])} pebbles={len(cls['pebbles'])}")
    print(f"measured sealed={nsealed}/{SEAL_SECTORS}")
    print(f"measured cap_bite min={min(caps, default=-9):.4f} max={max(caps, default=-9):.4f} "
          f"n={len(caps)}")
    print(f"measured cut_tilt={tilt:.4f}deg diameter={diam:.4f} height={ht:.4f} cut_verts={ncut}")
    print(f"measured root_bed min={min(root_beds, default=-9):.4f} "
          f"per_root={[round(b, 4) for b in root_beds]} stations={root_stations}")
    print(f"measured host_depth min={min(host_depths, default=-9):.4f} "
          f"max={max(host_depths, default=-9):.4f} n={len(host_depths)}")
    print(f"measured fungus_bite min={min(depths, default=-9):.4f} "
          f"max={max(depths, default=-9):.4f} n={len(depths)}")
    print(f"measured moss_up_shade={moss_frac:.4f} moss_top_area={moss_top:.4f}")
    print(f"measured cover={ncover} loose={nloose} loose_leaves={loose_leaves}")

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
    if nsealed < SEAL_SECTORS:
        return (fail(f"stump sealed in the soil in only {nsealed}/{SEAL_SECTORS} sectors "
                     "(--perch-stump is the designed fail)", 17),) + none2
    if (len(caps) != n_mush or len(cls["stipes"]) != n_mush or min(caps) < CAP_BITE_MIN
            or max(caps) > CAP_BITE_MAX):
        return (fail(f"caps seated: {len(caps)}/{n_mush} caps on {len(cls['stipes'])} stipes, "
                     f"stipe bite {min(caps, default=-9):.4f}..{max(caps, default=-9):.4f} "
                     f"not in [{CAP_BITE_MIN}, {CAP_BITE_MAX}]", 18),) + none2
    if tilt > CUT_TILT_MAX:
        return (fail(f"saw cut tilted {tilt:.4f} deg (max {CUT_TILT_MAX})", 19),) + none2
    if abs(diam - STUMP_D) > SIZE_TOL or abs(ht - STUMP_HT) > SIZE_TOL:
        return (fail(f"stump {diam:.4f} m across, cut {ht:.4f} m above the soil; stated "
                     f"{STUMP_D} and {STUMP_HT} +-{SIZE_TOL}", 19),) + none2
    if len(root_beds) != len(LOBES) or min(root_beds) < ROOT_BED_MIN:
        return (fail(f"roots bedded: {len(root_beds)}/{len(LOBES)} roots, shallowest station "
                     f"{min(root_beds, default=-9):.4f} m under the soil (min {ROOT_BED_MIN})",
                     20),) + none2
    if (len(host_depths) != n_mush or min(host_depths) < HOST_MIN
            or max(host_depths) > HOST_MAX):
        return (fail(f"mushrooms rooted: {len(host_depths)}/{n_mush} stipes, deepest vertex in "
                     f"the host {min(host_depths, default=-9):.4f}..{max(host_depths, default=-9):.4f} "
                     f"not in [{HOST_MIN}, {HOST_MAX}]", 21),) + none2
    if (len(depths) != len(plan["shelves"]) or min(depths) < FUNGUS_BITE_MIN
            or max(depths) > FUNGUS_BITE_MAX):
        return (fail(f"brackets rooted: {len(depths)}/{len(plan['shelves'])} shelves, deepest "
                     f"vertex in the bark {min(depths, default=-9):.4f}..{max(depths, default=-9):.4f} "
                     f"not in [{FUNGUS_BITE_MIN}, {FUNGUS_BITE_MAX}]", 22),) + none2
    if len(cls["moss"]) != len(MOSS) or moss_frac < MOSS_FRAC_MIN:
        return (fail(f"moss: {len(cls['moss'])}/{len(MOSS)} cushions, {moss_frac:.4f} of top "
                     f"area faces up or north (min {MOSS_FRAC_MIN})", 23),) + none2
    if ncover != expected_cover or nloose:
        return (fail(f"ground cover: {ncover}/{expected_cover} shells, {nloose} not joined to "
                     f"the soil ({loose_leaves} leaves)", 24),) + none2
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

    # Key, fill, rim and the warm wedge, scaled for a 2.2 m disc.
    light("Key", (-3.2, -3.8, 5.0), 148.0, 2.4, (1.0, 0.95, 0.88), spread=12.0)
    light("Fill", (5.0, -3.0, 1.2), 6.0, 6.0, (0.72, 0.82, 1.0))
    light("Rim", (-1.5, 3.0, 2.8), 90.0, 2.4, (0.62, 0.78, 1.0))
    light("Wedge", (3.2, 1.2, 2.4), 210.0, 3.5, (1.0, 0.68, 0.38),
          target=(1.8, WALL_Y - 1.2, 0.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.50, -0.87, 0.0)).normalized()
    cam.location = centre + view * 3.7 + Vector((0.0, 0.0, 1.95))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.20))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the caps.
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


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--perch-stump", action="store_true")
    p.add_argument("--float-caps", action="store_true")
    p.add_argument("--tilt-cut", action="store_true")
    p.add_argument("--fat-stump", action="store_true")
    p.add_argument("--arch-roots", action="store_true")
    p.add_argument("--float-mushrooms", action="store_true")
    p.add_argument("--float-brackets", action="store_true")
    p.add_argument("--sunny-moss", action="store_true")
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
    print("mushroom-stump OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
