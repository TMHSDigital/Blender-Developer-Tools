"""Game-ready Sonoran cactus garden — a showcase piece, not an example.

Asserts budget conformance of a procedural desert-garden vignette after
composing shipped pipeline pieces: bmesh construction, UVs, ten materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

A raised sand-and-gravel disc holds a Sonoran planting. A saguaro stands at
the back: a pleated column of fourteen ribs with rounded crests, a woody
boot at its foot and two corky scars, three arms that leave the trunk
through a narrowed neck, run out and turn up, and a crown of cream
flowers. Areoles run in rows down every rib crest, each a felt cushion with
a radiating cluster of spines. A fishhook barrel cactus sits at the front,
eighteen ribs with a red hooked central spine at every areole and a ring
of yellow fruit round its crown; a prickly pear grows pad on pad, each pad
jointed into the rim of the one below, dotted with glochids and carrying
magenta fruit; a blue agave rosette, weathered sandstone rocks, a sun
bleached mesquite branch, two fallen saguaro ribs, dry bunchgrass, pebbles
and gravel complete it.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--short-arm`` every saguaro arm biting into
the trunk, ``--shallow-pad`` every pad jointed into its parent pad,
``--lean-saguaro`` the saguaro plumb with its mass over its foot,
``--skew-ribs`` the ribs at equal angular spacing, ``--float-spines`` every
spine cluster rooted in the skin, ``--perch-barrel`` every plant bedded in
the sand, ``--float-cover`` the ground cover joined to the sand.

Seeded, not random: ``random.Random(SEED)`` draws the plan before anything
is built, and per-areole draws come from a closed-form hash of the
areole's indices, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python cactus_garden.py --
    blender --background --python cactus_garden.py -- --skip-decimate
    blender --background --python cactus_garden.py -- --output cactus.png
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

SEED = 8243
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- Ground ------------------------------------------------------------------
DISC_A = (1.46, 1.28)     # sand disc semi-axes before its wobble, m
DISC_EDGE = 0.14          # the rim rolls down over this fraction of the radius
DISC_N = {"low": 42, "high": 76}
MOUND_Z = 0.140

# --- Saguaro -----------------------------------------------------------------
SAG_XY = (-0.16, 0.34)
SAG_H = 2.20              # apex over the sand at the foot
SAG_R = 0.168             # crest radius of the column
SAG_RIBS = 14
SAG_DEPTH = 0.15          # valley depth, a fraction of the crest radius
SAG_S = 5                 # ring samples per rib
SAG_BED = 0.080           # the foot under the lowest sand round it
SAG_DOME = 0.24
SAG_RING_N = 24
SAG_DOME_N = 7
AREOLE_STEP = 0.11
HUB_DEPTH = 0.0050        # every areole's felt cushion roots this far under the skin
HOOK_DEPTH = 0.0060       # and every hooked central's base
# arms: bearing deg, junction height, reach of the upright's axis, elbow
# radius, tip height, radius, rise of the run
ARMS = ((188.0, 0.80, 0.43, 0.21, 1.60, 0.114, 0.05),
        (318.0, 1.06, 0.39, 0.20, 1.80, 0.106, 0.04),
        (68.0, 1.28, 0.36, 0.19, 1.86, 0.098, 0.03))
ARM_RIBS = 10
ARM_DEPTH = 0.16
ARM_S = 4
ARM_ROOT = 0.050          # every arm's path starts this far from the trunk's axis
ARM_STATIONS = 23
ARM_DOME = 0.11
ARM_DOME_N = 5
# boot and scars: bearing deg, height, angular span rad, height span, zone
SCARS = ((236.0, 0.07, 0.95, 0.20, 1.0), (262.0, 0.62, 0.42, 0.15, 2.0),
         (340.0, 1.48, 0.38, 0.13, 2.0))
# crown flowers: bearing deg, elevation on the crown's dome (rad, 0 at its rim)
SAG_FLOWERS = ((250.0, 0.98), (20.0, 0.92), (140.0, 1.02))

# --- Barrel ------------------------------------------------------------------
BARREL_XY = (-0.70, -0.24)
BARREL_H = 0.48
BARREL_R = 0.215
BARREL_EXP = 2.4          # the crest profile's superellipse exponent: round shoulders
BARREL_RIBS = 18
BARREL_DEPTH = 0.20
BARREL_S = 4
BARREL_BED = 0.050
BARREL_U = (-0.85, -0.70, -0.52, -0.34, -0.16, 0.02, 0.20, 0.36, 0.51, 0.64, 0.75, 0.84,
            0.91, 0.955, 0.985)
BARREL_AREOLE_U = (-0.40, -0.16, 0.08, 0.30, 0.50, 0.66, 0.80)
BARREL_FRUIT_N = 7

# --- Prickly pear -------------------------------------------------------------
PEAR_XY = (0.66, 0.30)
# root pads: (dx, dy, lean bearing deg, lean deg, yaw deg, a, b)
# child pads: (parent, rim angle deg, yaw deg, a, b)
# Yaws near -20 deg turn a root pad's face to the hero camera; children
# turn a little either way off their parent's plane.
PADS = (("root", 0.00, 0.00, 200.0, 14.0, -20.0, 0.150, 0.105),
        ("root", 0.26, -0.08, 20.0, 20.0, -38.0, 0.140, 0.100),
        ("root", 0.06, 0.22, 110.0, 24.0, 5.0, 0.130, 0.092),
        ("child", 0, 40.0, 20.0, 0.145, 0.102),
        ("child", 0, 140.0, -22.0, 0.135, 0.095),
        ("child", 1, 65.0, 25.0, 0.140, 0.098),
        ("child", 1, 32.0, -18.0, 0.120, 0.086),
        ("child", 3, 95.0, -25.0, 0.130, 0.092),
        ("child", 4, 115.0, 20.0, 0.118, 0.084),
        ("child", 5, 60.0, -20.0, 0.125, 0.088),
        ("child", 2, 85.0, 22.0, 0.122, 0.086),
        ("child", 7, 70.0, 18.0, 0.110, 0.078))
PAD_T = 0.0130            # half thickness at the pad's swollen centre
PAD_NA = 20
PAD_RN = (0.32, 0.58, 0.80, 0.94)
PAD_BITE = 0.032          # a child's joint this far inside its parent's rim
PAD_BED = 0.050           # a root pad's joint under the sand
PEAR_FRUIT = ((6, (60.0, 92.0)), (8, (82.0, 112.0)), (9, (75.0, 105.0)), (10, (68.0, 98.0, 126.0)),
              (11, (72.0, 104.0)))

# --- Agave, rocks, wood, cover -----------------------------------------------
AGAVE_XY = (0.44, -0.46)
AGAVE_N = 13
AGAVE_ROOT = 0.035
# sandstone rocks: x, y, radius
ROCKS = ((-0.30, -0.60, 0.115), (1.02, 0.00, 0.130), (-1.00, 0.34, 0.120), (0.22, 0.78, 0.085),
         (-0.43, 0.05, 0.060))
BRANCH = ((-0.92, -0.62), (-0.08, -0.96))
RODS = (((-1.10, -0.06), (-0.74, 0.14)), ((-1.06, 0.04), (-0.80, -0.20)))
TUFTS = ((-0.44, 0.78, 0.95), (-0.05, -0.20, 0.70), (1.02, 0.58, 0.90), (-0.98, -0.30, 0.80),
         (0.12, -0.95, 0.75), (0.95, -0.52, 0.60))
N_PEBBLES = 25

# falsifiers
SHORT_ARM = 0.070         # --short-arm: every arm drawn this far out of the trunk, still touching it
SHALLOW_PAD = 0.022       # --shallow-pad: the top right pad slid out of its joint
LEAN_DEG = 3.5            # --lean-saguaro: the whole saguaro tipped about its foot
SKEW_RIB = 4
SKEW_DEG = 7.0            # --skew-ribs: one trunk rib turned off its station
FLOAT_SPINES = 0.003      # --float-spines: every cluster lifted off the skin
PERCH_BARREL = 0.035      # --perch-barrel: the barrel raised onto the sand
FLOAT_COVER = 0.050       # --float-cover: pebbles, grass and wood lifted

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from the vertices.
OUTER_SIZE = (2.9950, 2.6077, 2.3754)
BASE_TRIS_MIN = 44700
BASE_TRIS_MAX = 46000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 10
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 120
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# sand, skin, spine, fruit, flower, agave, rock, gravel, wood, grass
FACE_FLOORS = (3400, 8400, 12100, 420, 900, 440, 990, 550, 610, 1120)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Arms: the deepest arm vertex inside the trunk, radially from the axis.
ARM_BITE_MIN = 0.080
ARM_BITE_MAX = 0.160
# Pads: a child's joint vertex inside its parent, measured along the child's axis.
PAD_SEAT_MIN = 0.022
PAD_SEAT_MAX = 0.040
# Saguaro: axis lean, mass centre over the foot, height and crest diameter.
LEAN_MAX_DEG = 1.0
MASS_OFF_MAX = 0.050
SAG_H_TOL = 0.05
SAG_D_BAND = (0.30, 0.37)
# Ribs: the spread of the gaps between crests, degrees.
RIB_SPREAD_MAX = 2.0
# Spines: every cluster's deepest vertex under the skin of its host.
ROOT_MIN = 0.0030
ROOT_MAX = 0.0080
# Bedding: a body's shallowest sector, a pad's or leaf's joint, under the sand.
BED_MIN = 0.025
BED_MAX = 0.150
LEAF_BED_MIN = 0.020
LEAF_BED_MAX = 0.100
HERO_YAW_DEG = 0.0
WALL_Y = 4.2

SAND_IDX = 0
SKIN_IDX = 1
SPINE_IDX = 2
FRUIT_IDX = 3
FLOWER_IDX = 4
AGAVE_IDX = 5
ROCK_IDX = 6
GRAVEL_IDX = 7
WOOD_IDX = 8
GRASS_IDX = 9
MAT_LABELS = ("sand", "skin", "spine", "fruit", "flower", "agave", "rock", "gravel", "wood",
              "grass")

# part labels (a face attribute): they name a shell, they never measure it
P_SAND, P_TRUNK, P_ARM, P_AREOLE, P_HOOK, P_BARREL, P_PAD, P_GLOCHID = 1, 2, 3, 4, 5, 6, 7, 8
P_FRUIT, P_FLOWER, P_SCAR, P_AGAVE, P_ROCK, P_PEBBLE, P_WOOD, P_GRASS = 9, 10, 11, 12, 13, 14, 15, 16
SPINE_PARTS = (P_AREOLE, P_HOOK, P_GLOCHID)
FLAT_PARTS = (P_PEBBLE,)


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


def hash01(a, b, c):
    """A closed-form draw in [0, 1) from three indices: per-areole variety
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


# --------------------------------------------------------------------------
# The ground as a function of plan position
# --------------------------------------------------------------------------

def disc_wobble(th):
    return 1.0 + 0.045 * math.sin(3.0 * th + 1.3) + 0.03 * math.sin(5.0 * th + 0.4) \
        + 0.018 * math.sin(8.0 * th + 2.2)


def disc_radius(x, y):
    """Normalised disc radius: 1 on the sand's rim."""
    X, Y = x / DISC_A[0], y / DISC_A[1]
    return math.hypot(X, Y) / disc_wobble(math.atan2(Y, X))


HUMPS = ((SAG_XY[0], SAG_XY[1], 0.020, 0.34), (BARREL_XY[0], BARREL_XY[1], 0.016, 0.30),
         (PEAR_XY[0] + 0.1, PEAR_XY[1] - 0.04, 0.012, 0.32), (AGAVE_XY[0], AGAVE_XY[1], 0.010, 0.28))


def sand_height(x, y):
    """A low mound of sand drifted round the plants' feet, rolled down to
    Z = 0 at the disc's rim."""
    rn2 = (x / DISC_A[0]) ** 2 + (y / DISC_A[1]) ** 2
    z = MOUND_Z * (1.0 - 0.30 * rn2)
    z += 0.010 * math.sin(2.1 * x + 0.6) * math.cos(1.7 * y - 0.4) + 0.005 * math.sin(4.3 * x - 3.1 * y + 1.2)
    for hx, hy, amp, w in HUMPS:
        z += amp * math.exp(-((x - hx) ** 2 + (y - hy) ** 2) / (w * w))
    return z * smoothstep(1.0 - disc_radius(x, y), 0.0, DISC_EDGE)


def ground_min(cx, cy, r, n=24):
    return min(sand_height(cx + r * math.cos(TAU * k / n), cy + r * math.sin(TAU * k / n))
               for k in range(n))


# --------------------------------------------------------------------------
# Ribbed bodies
# --------------------------------------------------------------------------

def crest_angles(n, phase, skew_k=None, skew_deg=0.0):
    out = [phase + TAU * k / n for k in range(n)]
    if skew_k is not None:
        out[skew_k] += math.radians(skew_deg)
    return out


def rib_shape(t):
    """1 on a crest, 0 in a valley: rounded crests, pleated valleys."""
    return abs(math.cos(math.pi * t)) ** 0.65


def rib_ring(centre, e1, e2, R, crests, depth, S):
    n = len(crests)
    out = []
    for k in range(n):
        c0 = crests[k]
        c1 = crests[(k + 1) % n] + (TAU if k == n - 1 else 0.0)
        for j in range(S):
            t = j / S
            th = c0 + (c1 - c0) * t
            g = rib_shape(t)
            r = R * (1.0 - depth * (1.0 - g))
            out.append((centre + (e1 * math.cos(th) + e2 * math.sin(th)) * r, g))
    return out


def transport_frames(pts):
    n = len(pts)
    tans = []
    for i in range(n):
        tans.append((pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized())
    e1, _e2 = perp_basis(tans[0])
    nrm = e1
    frames = []
    for t in tans:
        nrm = (nrm - t * nrm.dot(t)).normalized()
        frames.append((t, nrm, t.cross(nrm)))
    return frames


def resample(pts, n):
    """``n`` points at equal arc length along a polyline, and their arc lengths."""
    seg = [(b - a).length for a, b in zip(pts, pts[1:])]
    total = sum(seg)
    out, ss = [], []
    j, acc = 0, 0.0
    for k in range(n):
        s = total * k / (n - 1)
        while j < len(seg) - 1 and acc + seg[j] < s:
            acc += seg[j]
            j += 1
        f = 0.0 if seg[j] == 0.0 else min(max((s - acc) / seg[j], 0.0), 1.0)
        out.append(pts[j].lerp(pts[j + 1], f))
        ss.append(s)
    return out, ss


# --------------------------------------------------------------------------
# The plan: every seeded draw happens here, before anything is built
# --------------------------------------------------------------------------

def plan_garden():
    rng = random.Random(SEED)

    def u(a, b):
        return a + (b - a) * rng.random()

    plan = {"sag_phase": u(0.0, TAU), "sag_tone": rng.random(),
            "arm_phase": [u(0.0, TAU) for _a in ARMS], "arm_tone": [rng.random() for _a in ARMS],
            "barrel_phase": u(0.0, TAU), "barrel_tone": rng.random(),
            "pads": [{"ph": u(0.0, TAU), "tone": rng.random()} for _p in PADS]}
    plan["agave"] = [{"L": u(0.90, 1.10), "tw": u(-0.25, 0.25), "tone": rng.random(),
                      "jit": u(-0.08, 0.08), "curl": u(0.25, 0.45)} for _k in range(AGAVE_N)]
    plan["rocks"] = [{"flat": u(0.52, 0.72), "long": u(1.15, 1.45), "yaw": u(0.0, TAU),
                      "tone": rng.random(),
                      "waves": [(Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized(),
                                 u(0.0, TAU), a) for a in (0.10, 0.06, 0.035)],
                      "cuts": [(Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 0.6))).normalized(),
                                u(0.62, 0.80)) for _c in range(3)]}
                     for _r in ROCKS]
    plan["branch"] = {"wig": [u(-1, 1) for _k in range(9)], "tone": rng.random(),
                      "twigs": [(u(0.25, 0.40), u(0.6, 0.9), u(0.18, 0.26)),
                                (u(0.55, 0.72), u(-0.9, -0.6), u(0.12, 0.18))]}
    plan["rods"] = [{"tone": rng.random(), "bow": u(-0.02, 0.02)} for _r in RODS]
    plan["tufts"] = [{"j": (u(-0.02, 0.02), u(-0.02, 0.02)), "tone": rng.random(),
                      "blades": [{"yaw": u(0.0, TAU), "h": u(0.50, 1.0), "lean": u(0.20, 0.60),
                                  "w": u(0.8, 1.2), "tw": u(-0.6, 0.6), "off": (u(-1, 1), u(-1, 1)),
                                  "tone": rng.random()} for _b in range(40)]}
                     for _t in TUFTS]

    def spot():
        while True:
            X, Y = u(-1.0, 1.0), u(-1.0, 1.0)
            if X * X + Y * Y <= 1.0:
                return X * DISC_A[0] * 0.82, Y * DISC_A[1] * 0.82

    pebbles = []
    for _k in range(500):
        x, y = spot()
        pebbles.append({"x": x, "y": y, "r": 0.014 + 0.030 * rng.random() ** 2.0,
                        "flat": u(0.45, 0.72), "long": u(1.0, 1.5), "yaw": u(0.0, TAU),
                        "tilt": (u(-0.2, 0.2), u(-0.2, 0.2)), "tone": rng.random(),
                        "waves": [(Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized(),
                                   u(0.0, TAU), a) for a in (1.0, 0.6, 0.4, 0.3)]})
    plan["pebbles"] = pebbles
    return plan


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

class PadFrame:
    def __init__(self, J, u, w, a, b, ph, tone, parent):
        self.u = u.normalized()
        self.w = (w - self.u * w.dot(self.u)).normalized()
        self.n = self.w.cross(self.u).normalized()
        self.a, self.b, self.ph, self.tone, self.parent = a, b, ph, tone, parent
        self.c = J + self.u * self.ae(-0.5 * math.pi)
        self.J = J

    def ae(self, phi):
        return self.a * (1.0 + 0.02 * math.sin(2.0 * phi + self.ph))

    def be(self, phi):
        return self.b * (1.0 + 0.10 * math.sin(phi)) * (1.0 + 0.03 * math.sin(3.0 * phi + self.ph))

    def half(self, rn, phi):
        """Thick to near the rim, swollen at the centre: a paddle, never a blade."""
        rn = min(rn, 1.0)
        return (PAD_T * max(0.0, 1.0 - rn ** 4) ** 0.5 * (0.85 + 0.15 * (1.0 - rn * rn))
                * (1.0 + 0.08 * math.sin(2.0 * phi + self.ph)))

    def shape(self, phi):
        """The outline as a superellipse: broad shoulders above, a rounder
        base than an ellipse's point below."""
        e = 2.0 / (2.5 if math.sin(phi) > 0.0 else 2.15)
        c, s = math.cos(phi), math.sin(phi)
        return math.copysign(abs(c) ** e, c), math.copysign(abs(s) ** e, s)

    def point(self, phi, rn, side=0.0):
        sx, sy = self.shape(phi)
        p = self.c + self.w * (self.be(phi) * rn * sx) + self.u * (self.ae(phi) * rn * sy)
        return p + self.n * (side * self.half(rn, phi))

    def rim_normal(self, phi):
        eps = 1e-4
        t = self.point(phi + eps, 1.0) - self.point(phi - eps, 1.0)
        nq = t.cross(self.n).normalized()
        if nq.dot(self.point(phi, 1.0) - self.c) < 0.0:
            nq = -nq
        return nq


class Layout:
    def __init__(self, plan, short_arm=False, shallow_pad=False, perch_barrel=False, skew_ribs=False):
        self.plan = plan
        # the saguaro
        zf = sand_height(*SAG_XY)
        self.sag_foot = Vector((SAG_XY[0], SAG_XY[1], zf))
        self.sag_bottom = ground_min(SAG_XY[0], SAG_XY[1], SAG_R) - SAG_BED - zf
        self.sag_crests = crest_angles(SAG_RIBS, plan["sag_phase"], SKEW_RIB if skew_ribs else None,
                                       SKEW_DEG)
        self.arms = []
        for k, arm in enumerate(ARMS):
            g = self.arm_geometry(arm, ARM_ROOT, plan["arm_phase"][k], plan["arm_tone"][k])
            # every station as built, before any falsifier moves the arm:
            # the trunk's areoles clear the arm where it is designed to be
            g["pts0"] = list(g["pts"])
            if short_arm:
                g["pts"] = [p + g["d"] * SHORT_ARM for p in g["pts"]]
            self.arms.append(g)

        # the barrel
        zb = ground_min(BARREL_XY[0], BARREL_XY[1], BARREL_R * 0.75)
        self.barrel_hc = 0.40 * BARREL_H
        self.barrel_hz = 0.60 * BARREL_H
        z0 = zb - BARREL_BED - self.barrel_h(BARREL_U[0])
        if perch_barrel:
            z0 += PERCH_BARREL
        self.barrel_o = Vector((BARREL_XY[0], BARREL_XY[1], z0))
        self.barrel_crests = crest_angles(BARREL_RIBS, plan["barrel_phase"])

        # the prickly pear
        self.pads = []
        for k, (spec, pp) in enumerate(zip(PADS, plan["pads"])):
            if spec[0] == "root":
                _kind, dx, dy, laz, lean, yaw, a, b = spec
                x, y = PEAR_XY[0] + dx, PEAR_XY[1] + dy
                J = Vector((x, y, sand_height(x, y) - PAD_BED))
                la = math.radians(laz)
                u = (UP * math.cos(math.radians(lean))
                     + Vector((math.cos(la), math.sin(la), 0.0)) * math.sin(math.radians(lean)))
                w = Vector((math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0.0))
                self.pads.append(PadFrame(J, u, w, a, b, pp["ph"], pp["tone"], -1))
            else:
                _kind, par, rim, yaw, a, b = spec
                P = self.pads[par]
                phi = math.radians(rim)
                Q = P.point(phi, 1.0)
                nq = P.rim_normal(phi)
                # out of the rim, turned up toward the sky within the parent's plane
                up_p = (UP - P.n * UP.dot(P.n)).normalized()
                uc = (nq + P.u * 0.25 + up_p * 0.35).normalized()
                J = Q - uc * PAD_BITE
                if shallow_pad and k == len(PADS) - 1:
                    J = J + uc * SHALLOW_PAD
                w0 = uc.cross(P.n).normalized()
                y = math.radians(yaw)
                wc = w0 * math.cos(y) + uc.cross(w0) * math.sin(y)
                self.pads.append(PadFrame(J, uc, wc, a, b, pp["ph"], pp["tone"], par))
        for p in self.pads:
            if p.u.z < 0.3:
                raise RuntimeError("a pad grows downward")

        # agave, rocks, wood, cover
        self.rocks = [dict(rp, x=x, y=y, r=r) for (x, y, r), rp in zip(ROCKS, plan["rocks"])]
        occupied = [(SAG_XY[0], SAG_XY[1], SAG_R + 0.10), (BARREL_XY[0], BARREL_XY[1], BARREL_R + 0.10),
                    (AGAVE_XY[0], AGAVE_XY[1], 0.40)]
        occupied += [(p.c.x, p.c.y, 0.14) for p in self.pads[:2]]
        occupied += [(r["x"], r["y"], r["r"] * 1.5 + 0.03) for r in self.rocks]
        for (x0, y0), (x1, y1) in [BRANCH] + list(RODS):
            for k in range(7):
                t = k / 6.0
                occupied.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 0.06))
        self.tufts = []
        for (x, y, size), tp in zip(TUFTS, plan["tufts"]):
            if disc_radius(x, y) > 0.84:
                raise RuntimeError(f"tuft at ({x}, {y}) is off the disc")
            self.tufts.append(dict(tp, x=x + tp["j"][0], y=y + tp["j"][1], size=size,
                                   n=int(round(20 * size)), h=0.20 + 0.20 * size,
                                   spread=0.025 + 0.03 * size))
        occupied += [(t["x"], t["y"], 0.12) for t in self.tufts]

        def free(x, y, r, placed):
            return all(math.hypot(x - px, y - py) > r + pr for px, py, pr in occupied + placed)

        placed = []
        self.pebbles = []
        for pb in plan["pebbles"]:
            if disc_radius(pb["x"], pb["y"]) > 0.80:
                continue
            if not free(pb["x"], pb["y"], pb["r"] * 1.6, placed):
                continue
            self.pebbles.append(pb)
            placed.append((pb["x"], pb["y"], pb["r"] * 1.6))
            if len(self.pebbles) >= N_PEBBLES:
                break

    # --- saguaro geometry --------------------------------------------------
    @staticmethod
    def trunk_radius(h):
        R = SAG_R * (0.93 + 0.07 * smoothstep(h, -0.05, 0.40))
        R *= 1.0 - 0.035 * math.exp(-((h - 1.30) / 0.10) ** 2)
        R *= 1.0 + 0.025 * math.exp(-((h - 0.70) / 0.25) ** 2)
        return R

    def trunk_axis(self, h):
        return self.sag_foot + UP * h

    def arm_geometry(self, arm, root, phase, tone):
        az, h0, reach, rc, h1, ra, rise = arm
        d = Vector((math.cos(math.radians(az)), math.sin(math.radians(az)), 0.0))
        o = self.trunk_axis(h0)
        x1 = reach - rc
        pts = []
        for k in range(10):
            s = k / 9.0
            pts.append(o + d * (root + (x1 - root) * s) + UP * (rise * s * s))
        C = o + d * x1 + UP * (rise + rc)
        for k in range(1, 13):
            ph = 0.5 * math.pi * k / 12.0
            pts.append(C + (-UP * math.cos(ph) + d * math.sin(ph)) * rc)
        a = pts[-1]
        b = self.trunk_axis(h1 - ARM_DOME) + d * (reach + 0.035)
        for k in range(1, 9):
            pts.append(a.lerp(b, k / 8.0))
        st, ss = resample(pts, ARM_STATIONS)
        s_exit = SAG_R - root
        radii = [ra * (0.76 + 0.24 * smoothstep(s, s_exit, s_exit + 0.20)) for s in ss]
        # the pleats open out of a smooth collar where the arm leaves the trunk
        depths = [ARM_DEPTH * (0.30 + 0.70 * smoothstep(s, s_exit - 0.02, s_exit + 0.26)) for s in ss]
        return {"d": d, "pts": st, "ss": ss, "radii": radii, "depths": depths, "phase": phase, "tone": tone,
                "az": az,
                "crests": crest_angles(ARM_RIBS, phase), "ra": ra}

    def barrel_h(self, u):
        return self.barrel_hc + self.barrel_hz * u

    @staticmethod
    def barrel_r(u):
        return BARREL_R * max(0.0, 1.0 - abs(u) ** BARREL_EXP) ** (1.0 / BARREL_EXP)

    def barrel_slope(self, u):
        """-dr/dh of the barrel's crest profile: the rise of its surface normal."""
        e = BARREL_EXP
        au = min(abs(u), 0.999)
        dr = BARREL_R * au ** (e - 1.0) * (1.0 - au ** e) ** (1.0 / e - 1.0)
        return math.copysign(dr, u) / self.barrel_hz


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


def add_loft(bm, rings, apex, mat, L, V, tone, zone, part, alongs):
    """Rings of (point, rib) joined into a closed body: a flat base cap and
    a fan to ``apex``."""
    rows = []
    for ring, al in zip(rings, alongs):
        row = []
        for p, rib in ring:
            v = bm.verts.new(p)
            v[V["rib"]] = rib
            v[V["along"]] = al
            row.append(v)
        rows.append(row)
    m = len(rows[0])
    for r0, r1 in zip(rows, rows[1:]):
        for k in range(m):
            q = (k + 1) % m
            new_face(bm, (r0[k], r0[q], r1[q], r1[k]), mat, L, tone, zone, part)
    new_face(bm, list(reversed(rows[0])), mat, L, tone, zone, part)
    tv = bm.verts.new(apex)
    tv[V["rib"]] = 1.0
    tv[V["along"]] = 1.0
    last = rows[-1]
    for k in range(m):
        new_face(bm, (last[k], last[(k + 1) % m], tv), mat, L, tone, zone, part)


def add_tube(bm, pts, radii, sides, mat, L, V, tone, part, zone=0.0, tip=None, alongs=None,
             phase=0.0, zones=None):
    """A tube through ``pts`` with parallel-transported rings, a flat base
    cap, and either a flat top cap or a point at ``tip``."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tans = []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)] if tip is None or i < n - 1 else Vector(tip)
        tans.append((b - a).normalized())
    e1, e2 = perp_basis(tans[0])
    nrm = e1 * math.cos(phase) + e2 * math.sin(phase)
    zones = zones or [zone] * n
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
    for i, (r0, r1) in enumerate(zip(rings, rings[1:])):
        for k in range(sides):
            m = (k + 1) % sides
            new_face(bm, (r0[k], r0[m], r1[m], r1[k]), mat, L, tone, zones[i], part)
    new_face(bm, tuple(reversed(rings[0])), mat, L, tone, zones[0], part)
    if tip is None:
        new_face(bm, tuple(rings[-1]), mat, L, tone, zones[-1], part)
    else:
        tv = bm.verts.new(tip)
        if alongs is not None:
            tv[V["along"]] = 1.0
        for k in range(sides):
            new_face(bm, (rings[-1][k], rings[-1][(k + 1) % sides], tv), mat, L, tone, zones[-1], part)


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


def add_ovoid(bm, L, V, centre, axis, rw, rl, mat, tone, zone, part, n=2, taper=0.18):
    """An egg along ``axis``: a fruit, a bud, a stamen cushion."""
    dirs, quads = cube_sphere(n)
    e1, e2 = perp_basis(axis)
    verts = []
    for d in dirs:
        s = 1.0 - taper * d.z
        p = centre + e1 * (d.x * rw * s) + e2 * (d.y * rw * s) + axis * (d.z * rl)
        v = bm.verts.new(p)
        v[V["along"]] = 0.5 + 0.5 * d.z
        verts.append(v)
    for q in quads:
        new_face(bm, [verts[i] for i in q], mat, L, tone, zone, part)


# --------------------------------------------------------------------------
# Spines
# --------------------------------------------------------------------------

def add_areole(bm, L, V, p, nrm, ref, k, spines, felt_h, depth, ra, tone, part, zone_spine, lift,
               zone_felt=1.0):
    """A spine cluster rooted on an areole: a low bipyramid of felt whose
    lower apex is buried ``depth`` under the skin at ``p``; the upper faces
    at the slots in ``spines`` are poked out into spines (slot, tilt, length)."""
    nrm = nrm.normalized()
    e1 = (ref - nrm * ref.dot(nrm)).normalized()
    e2 = nrm.cross(e1)
    base = p + nrm * lift
    eq = []
    for i in range(k):
        a = TAU * i / k
        v = bm.verts.new(base + nrm * 0.0003 + (e1 * math.cos(a) + e2 * math.sin(a)) * ra)
        v[V["along"]] = 0.0
        eq.append(v)
    up = bm.verts.new(base + nrm * felt_h)
    low = bm.verts.new(base - nrm * depth)
    up[V["along"]] = 0.0
    low[V["along"]] = 0.0
    poke = {s: (tilt, length) for s, tilt, length in spines}
    for i in range(k):
        j = (i + 1) % k
        new_face(bm, (eq[j], eq[i], low), SPINE_IDX, L, tone, zone_felt, part)
        if i in poke:
            tilt, length = poke[i]
            a = TAU * (i + 0.5) / k
            rd = e1 * math.cos(a) + e2 * math.sin(a)
            d = (nrm * math.cos(tilt) + rd * math.sin(tilt)).normalized()
            tip = bm.verts.new(base + nrm * (0.5 * felt_h) + d * length)
            tip[V["along"]] = 1.0
            for tri in ((eq[i], eq[j], tip), (eq[j], up, tip), (up, eq[i], tip)):
                new_face(bm, tri, SPINE_IDX, L, tone, zone_spine, part)
        else:
            new_face(bm, (eq[i], eq[j], up), SPINE_IDX, L, tone, zone_felt, part)


def saguaro_cluster(bm, L, V, p, nrm, ref, key, lift):
    a, b, c = key
    spin = TAU * hash01(a, b, c)
    ref = (ref * math.cos(spin) + nrm.cross(ref) * math.sin(spin))
    spines = [(0, 0.30 + 0.20 * hash01(a, c, b), 0.030 + 0.010 * hash01(b, a, c)),
              (2, 1.00 + 0.25 * hash01(c, a, b), 0.020 + 0.008 * hash01(c, b, a)),
              (4, 1.00 + 0.25 * hash01(b, c, a), 0.020 + 0.008 * hash01(a, a, c))]
    add_areole(bm, L, V, p, nrm, ref, 6, spines, 0.0030, HUB_DEPTH, 0.0034, hash01(a, b, b),
               P_AREOLE, 0.0, lift)


# --------------------------------------------------------------------------
# The parts
# --------------------------------------------------------------------------

def trunk_levels(lay):
    """(height over the foot, radius scale) for every trunk ring."""
    top = SAG_H - SAG_DOME
    out = [(lay.sag_bottom + (top - lay.sag_bottom) * k / SAG_RING_N, 1.0) for k in range(SAG_RING_N + 1)]
    for k in range(1, SAG_DOME_N + 1):
        g = 0.5 * math.pi * k / (SAG_DOME_N + 1)
        out.append((top + SAG_DOME * math.sin(g), math.cos(g)))
    return out


def trunk_ring_radius(lay, h, scale):
    return lay.trunk_radius(min(h, SAG_H - SAG_DOME)) * scale


def arm_near(lay, q, pad=0.02):
    for arm in lay.arms:
        for p, r in zip(arm["pts0"], arm["radii"]):
            if (q - p).length < r + pad:
                return True
    return False


def scar_hit(th, h):
    for az, hc, span, hs, _z in SCARS:
        dth = (th - math.radians(az) + math.pi) % TAU - math.pi
        if (dth / (0.5 * span + 0.05)) ** 2 + ((h - hc) / (0.5 * hs + 0.04)) ** 2 < 1.0:
            return True
    return False


def add_saguaro(bm, L, V, lay, lift_spines):
    X, Y = Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0))
    tone = lay.plan["sag_tone"]
    levels = trunk_levels(lay)
    rings, alongs = [], []
    for h, sc in levels:
        rings.append(rib_ring(lay.trunk_axis(h), X, Y, trunk_ring_radius(lay, h, sc), lay.sag_crests,
                              SAG_DEPTH, SAG_S))
        alongs.append(max(0.0, h) / SAG_H)
    add_loft(bm, rings, lay.trunk_axis(SAG_H), SKIN_IDX, L, V, tone, 0.0, P_TRUNK, alongs)

    # areoles down every crest, staggered rib to rib
    for k, c in enumerate(lay.sag_crests):
        radial = X * math.cos(c) + Y * math.sin(c)
        h = 0.05 + 0.05 * (k % 2)
        m = 0
        while h < SAG_H - SAG_DOME + 0.03:
            q = lay.trunk_axis(h) + radial * lay.trunk_radius(h)
            if not arm_near(lay, q) and not scar_hit(c, h):
                saguaro_cluster(bm, L, V, q, radial, UP, (1, k, m), lift_spines)
            h += AREOLE_STEP
            m += 1

    # arms
    for ai, arm in enumerate(lay.arms):
        frames = transport_frames(arm["pts"])
        rings, alongs = [], []
        for p, (t, n, b), r, dep in zip(arm["pts"], frames, arm["radii"], arm["depths"]):
            rings.append(rib_ring(p, n, b, r, arm["crests"], dep, ARM_S))
            alongs.append(0.5)
        t, n, b = frames[-1]
        pe, re_ = arm["pts"][-1], arm["radii"][-1]
        for k in range(1, ARM_DOME_N + 1):
            g = 0.5 * math.pi * k / (ARM_DOME_N + 1)
            rings.append(rib_ring(pe + t * (ARM_DOME * math.sin(g)), n, b, re_ * math.cos(g), arm["crests"],
                                  ARM_DEPTH, ARM_S))
            alongs.append(0.5)
        add_loft(bm, rings, pe + t * ARM_DOME, SKIN_IDX, L, V, arm["tone"], 0.0, P_ARM, alongs)
        arm["tip"] = (pe, t, n, b, re_)
        s_clear = SAG_R - ARM_ROOT + 0.035
        for i, (p, (t, n, b), r) in enumerate(zip(arm["pts"], frames, arm["radii"])):
            if arm["ss"][i] < s_clear:
                continue
            for k, c in enumerate(arm["crests"]):
                if (i + k) % 3:
                    continue
                radial = n * math.cos(c) + b * math.sin(c)
                q = p + radial * r
                saguaro_cluster(bm, L, V, q, radial, t, (2 + ai, k, i), lift_spines)

    # the boot and the scars: corky callus following the ribs
    for si, (az, hc, span, hs, zone) in enumerate(SCARS):
        add_scar(bm, L, V, lay, math.radians(az), hc, span, hs, zone, si)

    # crown flowers
    top = SAG_H - SAG_DOME
    for fi, (az, g) in enumerate(SAG_FLOWERS):
        a = math.radians(az)
        radial = X * math.cos(a) + Y * math.sin(a)
        Rb = lay.trunk_radius(top)
        p = lay.trunk_axis(top) + UP * (SAG_DOME * math.sin(g)) + radial * (Rb * math.cos(g))
        nrm = (radial * (math.cos(g) / Rb) + UP * (math.sin(g) / SAG_DOME)).normalized()
        add_flower(bm, L, V, p, nrm, 0.3 + 0.2 * fi, fi)
    # one on the right arm's tip
    pe, t, n, b, re_ = lay.arms[1]["tip"]
    add_flower(bm, L, V, pe + t * (ARM_DOME * 0.80) + n * (re_ * 0.55), (t + n * 0.9).normalized(), 0.8, 9)


def add_scar(bm, L, V, lay, thc, hc, span, hs, zone, si):
    """A conforming slab of callus: its face a few mm proud of the ribbed
    skin, its back sunk into it, its edge an uneven oval."""
    nu, nv = 8, 6
    X, Y = Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0))

    def skin(th, h):
        n = len(lay.sag_crests)
        # find the rib interval and the rib shape at th
        best = 1.0
        for k in range(n):
            c0 = lay.sag_crests[k]
            c1 = lay.sag_crests[(k + 1) % n] + (TAU if k == n - 1 else 0.0)
            d = (th - c0) % TAU
            if d < c1 - c0:
                best = rib_shape(d / (c1 - c0))
        R = lay.trunk_radius(h)
        return R * (1.0 - SAG_DEPTH * (1.0 - best)), best

    tops, bots = [], []
    for i in range(nu + 1):
        rt, rb = [], []
        for k in range(nv + 1):
            U, W = -1.0 + 2.0 * i / nu, -1.0 + 2.0 * k / nv
            X0 = U * math.sqrt(1.0 - W * W / 2.0)
            Y0 = W * math.sqrt(1.0 - U * U / 2.0)
            ang = math.atan2(Y0, X0)
            wob = (1.0 + 0.16 * math.sin(3.0 * ang + si * 1.7) + 0.10 * math.sin(5.0 * ang + si * 0.6)
                   + 0.06 * math.sin(9.0 * ang + si * 2.9))
            th = thc + 0.5 * span * X0 * wob
            h = max(hc + 0.5 * hs * Y0 * wob, lay.sag_bottom + 0.01)
            r, rib = skin(th, h)
            radial = X * math.cos(th) + Y * math.sin(th)
            edge = max(abs(U), abs(W))
            proud = 0.0045 * (1.0 - 0.6 * edge ** 4) + 0.0015 * math.sin(7.0 * th + 11.0 * h)
            vt = bm.verts.new(lay.trunk_axis(h) + radial * (r + proud))
            vb = bm.verts.new(lay.trunk_axis(h) + radial * (r - 0.008))
            for v in (vt, vb):
                v[V["rib"]] = rib
                v[V["along"]] = max(0.0, h) / SAG_H
            rt.append(vt)
            rb.append(vb)
        tops.append(rt)
        bots.append(rb)
    tone = 0.3 + 0.2 * si
    for i in range(nu):
        for k in range(nv):
            new_face(bm, (tops[i][k], tops[i + 1][k], tops[i + 1][k + 1], tops[i][k + 1]), WOOD_IDX, L,
                     tone, zone, P_SCAR)
            new_face(bm, (bots[i][k + 1], bots[i + 1][k + 1], bots[i + 1][k], bots[i][k]), WOOD_IDX, L,
                     tone, zone, P_SCAR)
    rim_t = ([tops[i][0] for i in range(nu)] + [tops[nu][k] for k in range(nv)]
             + [tops[i][nv] for i in range(nu, 0, -1)] + [tops[0][k] for k in range(nv, 0, -1)])
    rim_b = ([bots[i][0] for i in range(nu)] + [bots[nu][k] for k in range(nv)]
             + [bots[i][nv] for i in range(nu, 0, -1)] + [bots[0][k] for k in range(nv, 0, -1)])
    m = len(rim_t)
    for j in range(m):
        q = (j + 1) % m
        new_face(bm, (rim_t[q], rim_t[j], rim_b[j], rim_b[q]), WOOD_IDX, L, tone, zone, P_SCAR)


def petal(bm, L, V, root, ax, rd, tilt, length, width, cup, tone, zone, asym=1.0):
    out = (rd * math.cos(tilt) + ax * math.sin(tilt)).normalized()
    sd = ax.cross(rd).normalized()
    nrm = sd.cross(out).normalized()
    ring = []
    for f in (0.0, 0.12, 0.32, 0.55, 0.78, 0.92, 1.0):
        w = width * 0.5 * math.sin(math.pi * min(1.0, f ** 0.7)) if 0.0 < f < 1.0 else 0.0
        ring.append((f, w))
    right = list(ring)
    left = [(f, -w * asym) for f, w in reversed(ring[1:-1])]
    pts, alongs = [], []
    for f, w in right + left:
        lift = cup * min(1.0, abs(w) / (0.5 * width)) ** 2 * 0.5 * width + 0.10 * length * f * f
        pts.append(root + out * (f * length) + sd * w + nrm * lift)
        alongs.append(f)
    mid = root + out * (0.45 * length) + nrm * (0.02 * length)
    add_lens(bm, pts, mid + nrm * 0.0008, mid - nrm * 0.0008, FLOWER_IDX, L, tone, zone, P_FLOWER,
             V, alongs, 0.45)


def add_flower(bm, L, V, p, ax, tone, fi):
    """A saguaro flower: a green floral tube sunk in the skin, a cup of
    cream petals and a yellow stamen cushion."""
    tube = [p - ax * 0.012, p + ax * 0.008, p + ax * 0.024]
    add_tube(bm, tube, [0.0095, 0.0110, 0.0140], 8, FLOWER_IDX, L, V, tone, P_FLOWER, zone=2.0,
             alongs=[0.0, 0.1, 0.2], phase=0.4 * fi)
    top = p + ax * 0.022
    e1, e2 = perp_basis(ax)
    for k in range(8):
        a = 0.37 * fi + TAU * k / 8
        rd = e1 * math.cos(a) + e2 * math.sin(a)
        root = top + rd * (0.0075 + 0.0004 * k) + ax * (0.0003 * (k % 3))
        tilt = 0.55 + 0.05 * ((k * 3 + fi) % 4 - 1.5)
        petal(bm, L, V, root, ax, rd, tilt, 0.034 * (1.0 + 0.05 * ((k + fi) % 3 - 1)), 0.020, 0.35,
              tone, 0.0, 1.0 + 0.04 * ((k * 7 + fi) % 5 - 2))
    add_ovoid(bm, L, V, top + ax * 0.004, ax, 0.0085, 0.0065, FLOWER_IDX, tone, 3.0, P_FLOWER, taper=0.0)


def add_barrel(bm, L, V, lay, lift_spines):
    X, Y = Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0))
    o = lay.barrel_o
    tone = lay.plan["barrel_tone"]
    rings, alongs = [], []
    for u in BARREL_U:
        rings.append(rib_ring(o + UP * lay.barrel_h(u), X, Y, lay.barrel_r(u), lay.barrel_crests,
                              BARREL_DEPTH, BARREL_S))
        alongs.append(0.5 + 0.5 * u)
    apex = o + UP * (lay.barrel_h(BARREL_U[-1]) - 0.012)
    add_loft(bm, rings, apex, SKIN_IDX, L, V, tone, 1.0, P_BARREL, alongs)
    for k, c in enumerate(lay.barrel_crests):
        radial = X * math.cos(c) + Y * math.sin(c)
        for m, u in enumerate(BARREL_AREOLE_U):
            r = lay.barrel_r(u)
            nrm = (radial + UP * lay.barrel_slope(u)).normalized()
            q = o + UP * lay.barrel_h(u) + radial * r
            key = (7, k, m)
            spin = TAU * hash01(*key)
            ref = UP * math.cos(spin) + radial.cross(UP).normalized() * math.sin(spin)
            spines = [(0, 1.05 + 0.2 * hash01(k, m, 3), 0.018 + 0.006 * hash01(m, k, 5)),
                      (2, 1.10 + 0.2 * hash01(k, m, 4), 0.020 + 0.006 * hash01(m, k, 6)),
                      (4, 1.05 + 0.2 * hash01(k, m, 8), 0.018 + 0.006 * hash01(m, k, 9))]
            add_areole(bm, L, V, q, nrm, ref, 6, spines, 0.0030, HUB_DEPTH, 0.0036, hash01(k, m, 1),
                       P_AREOLE, 0.0, lift_spines)
            # the fishhook: a red central, hooked down at its tip
            Lh = 0.064 + 0.016 * hash01(m, k, 2)
            side = radial.cross(UP).normalized() * (0.12 * (hash01(k, m, 7) - 0.5))
            d = (nrm + UP * 0.42 + side).normalized()
            b0 = q + nrm * (lift_spines - HOOK_DEPTH)
            pts = [b0, b0 + d * (0.35 * Lh), b0 + d * (0.72 * Lh), b0 + d * (0.94 * Lh) - UP * 0.005]
            tip = b0 + d * (0.88 * Lh) - UP * 0.017 - nrm * 0.005
            add_tube(bm, pts, [0.0027, 0.0023, 0.0018, 0.0013], 3, SPINE_IDX, L, V, hash01(m, k, 3),
                     P_HOOK, zone=2.0, tip=tip, alongs=[0.0, 0.35, 0.7, 0.9], phase=spin)
    # a ring of yellow fruit round the crown, between the crests
    uf = 0.93
    rf = lay.barrel_r(uf)
    for j in range(BARREL_FRUIT_N):
        a = lay.barrel_crests[0] + TAU * (j + 0.5) / BARREL_FRUIT_N
        radial = X * math.cos(a) + Y * math.sin(a)
        nrm = (radial + UP * lay.barrel_slope(uf)).normalized()
        ax = (nrm + UP * 0.6).normalized()
        c = o + UP * lay.barrel_h(uf) + radial * (rf * (1.0 - BARREL_DEPTH * 0.5)) + ax * 0.016
        add_ovoid(bm, L, V, c, ax, 0.0150 + 0.0015 * hash01(j, 1, 2), 0.0235, FRUIT_IDX,
                  0.2 * hash01(j, 3, 4), 0.0, P_FRUIT)


def add_pad(bm, L, V, pf):
    """A flat obovate pad: two domed faces meeting on a shared rim."""
    rows_t, rows_b = [], []
    for rn in PAD_RN:
        rt, rb = [], []
        for j in range(PAD_NA):
            phi = -0.5 * math.pi + TAU * j / PAD_NA
            for rows, side in ((rt, 1.0), (rb, -1.0)):
                v = bm.verts.new(pf.point(phi, rn, side))
                v[V["along"]] = rn
                v[V["rib"]] = 1.0
                rows.append(v)
        rows_t.append(rt)
        rows_b.append(rb)
    rim = []
    for j in range(PAD_NA):
        phi = -0.5 * math.pi + TAU * j / PAD_NA
        v = bm.verts.new(pf.point(phi, 1.0))
        v[V["along"]] = 1.0
        v[V["rib"]] = 1.0
        rim.append(v)
    ct = bm.verts.new(pf.point(0.0, 0.0, 1.0))
    cb = bm.verts.new(pf.point(0.0, 0.0, -1.0))
    for v in (ct, cb):
        v[V["rib"]] = 1.0
    for rows, centre, flip in ((rows_t, ct, False), (rows_b, cb, True)):
        chain = rows + [rim]
        for j in range(PAD_NA):
            q = (j + 1) % PAD_NA
            tri = (centre, chain[0][j], chain[0][q])
            new_face(bm, tri[::-1] if flip else tri, SKIN_IDX, L, pf.tone, 2.0, P_PAD)
        for r0, r1 in zip(chain, chain[1:]):
            for j in range(PAD_NA):
                q = (j + 1) % PAD_NA
                quad = (r0[j], r1[j], r1[q], r0[q])
                new_face(bm, quad[::-1] if flip else quad, SKIN_IDX, L, pf.tone, 2.0, P_PAD)


def add_glochids(bm, L, V, pf, pi, lift):
    """Areoles on a diagonal lattice over both faces, clear of the rim."""
    for side in (1.0, -1.0):
        spots = []
        for row in range(-3, 4):
            for col in range(-3, 4):
                x = 0.44 * (col + 0.5 * (row % 2)) + (0.11 if side < 0 else 0.0)
                y = 0.30 * row
                if 0.1 < math.hypot(x, y) < 0.68:
                    spots.append((row, col, math.hypot(x, y), math.atan2(y, x)))
        for ri, j, rn, phi in spots:
                p = pf.point(phi, rn, side)
                e = 1e-3
                du = pf.point(phi, rn + e, side) - pf.point(phi, rn - e, side)
                dv = pf.point(phi + e, rn, side) - pf.point(phi - e, rn, side)
                nrm = du.cross(dv).normalized()
                if nrm.dot(pf.n * side) < 0.0:
                    nrm = -nrm
                key = (11 + pi, ri + (10 if side < 0 else 0), j)
                spin = TAU * hash01(*key)
                ref = pf.u * math.cos(spin) + pf.w * math.sin(spin)
                add_areole(bm, L, V, p, nrm, ref, 4, [], 0.0026, HUB_DEPTH, 0.0024, hash01(j, ri, pi),
                           P_GLOCHID, 3.0, lift, zone_felt=3.0)


def add_pear(bm, L, V, lay, lift_spines):
    for pi, pf in enumerate(lay.pads):
        add_pad(bm, L, V, pf)
        add_glochids(bm, L, V, pf, pi, lift_spines)
    for pi, rims in PEAR_FRUIT:
        pf = lay.pads[pi]
        for j, rim in enumerate(rims):
            phi = math.radians(rim)
            Q = pf.point(phi, 1.0)
            nq = pf.rim_normal(phi)
            rl = 0.026 + 0.004 * hash01(pi, j, 1)
            add_ovoid(bm, L, V, Q + nq * (rl - 0.007), nq, 0.0165 + 0.002 * hash01(pi, j, 2), rl,
                      FRUIT_IDX, 0.5 + 0.5 * hash01(pi, j, 3), 1.0, P_FRUIT, taper=-0.15)


def add_strap(bm, pts, width, thick, hd, twist, mat, L, V, tone, part, section=4, roll=0.0, channel=0.0):
    """A strap along ``pts`` ending in a point: a keeled section for an
    agave leaf (``channel`` lifts its edges over a hollowed top), a V
    section (``section=3``) for a grass blade."""
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
        if section == 4:
            lift = nrm * (th * channel)
            ring = [bm.verts.new(pts[i] - side * w + lift), bm.verts.new(pts[i] + nrm * (th * (1.0 - 1.2 * channel))),
                    bm.verts.new(pts[i] + side * w + lift), bm.verts.new(pts[i] - nrm * th)]
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


def add_agave(bm, L, V, lay, tree):
    base, _n = sand_hit(tree, *AGAVE_XY)
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for k, lp in enumerate(lay.plan["agave"]):
        f = k / (AGAVE_N - 1)
        az = golden * k * 1.0 + 0.4
        hd = Vector((math.cos(az), math.sin(az), 0.0))
        b = Vector((AGAVE_XY[0], AGAVE_XY[1], 0.0)) + hd * (0.030 * (1.0 - 0.6 * f))
        g, _nn = sand_hit(tree, b.x, b.y)
        b.z = g.z - AGAVE_ROOT - 0.0011 * k
        Lk = (0.46 - 0.18 * f) * lp["L"]
        a0 = 1.00 - 0.80 * f + lp["jit"]
        a1 = a0 + lp["curl"] * (1.0 - 0.5 * f)
        segs = 9
        pts = [b.copy()]
        pos = b.copy()
        for i in range(segs):
            s = (i + 0.5) / segs
            a = a0 + (a1 - a0) * s ** 1.6
            pos = pos + (hd * math.sin(a) + UP * math.cos(a)) * (Lk / segs)
            pts.append(pos.copy())
        W = (0.130 - 0.050 * f)

        def width(s, W=W):
            body = 0.78 + 0.22 * smoothstep(s, 0.0, 0.30)
            return W * body * (1.0 if s < 0.45 else ((1.0 - s) / 0.55) ** 0.9)

        def thick(s):
            return 0.021 * (1.0 - 0.70 * s)

        add_strap(bm, pts, width, thick, hd, lp["tw"], AGAVE_IDX, L, V, lp["tone"], P_AGAVE,
                  roll=0.12 * math.sin(2.3 * k), channel=0.55)


def add_tuft(bm, L, V, tf, tree, lift):
    for k, bl in enumerate(tf["blades"][:tf["n"]]):
        ox, oy = bl["off"]
        b, _n = sand_hit(tree, tf["x"] + ox * tf["spread"], tf["y"] + oy * tf["spread"])
        b = b - UP * (0.018 + 0.00053 * k) + UP * lift
        h = tf["h"] * bl["h"] + 0.02
        hd = Vector((math.cos(bl["yaw"]), math.sin(bl["yaw"]), 0.0))
        segs = 4
        pts = []
        for i in range(segs + 1):
            t = i / segs
            pts.append(b + UP * (h * (t - 0.45 * bl["lean"] * t * t))
                       + hd * (h * bl["lean"] * (0.12 * t + t * t)))
        W = 0.0085 * bl["w"]

        def width(s, W=W):
            return W * (1.0 - 0.75 * s ** 1.3)

        def thick(s):
            return 0.0010 * (1.0 - 0.6 * s)

        add_strap(bm, pts, width, thick, hd, bl["tw"], GRASS_IDX, L, V,
                  0.6 * tf["tone"] + 0.4 * bl["tone"], P_GRASS, section=3,
                  roll=0.18 * math.sin(3.7 * k + bl["yaw"]))


def add_pebble(bm, L, V, pb, tree, lift):
    dirs, quads = cube_sphere(2)
    yaw = rotz(math.degrees(pb["yaw"]))
    tilt = Matrix.Rotation(pb["tilt"][0], 3, "X") @ Matrix.Rotation(pb["tilt"][1], 3, "Y")
    r = pb["r"]
    ax = Vector((r * pb["long"], r, r * pb["flat"]))
    pts = []
    for d in dirs:
        q = Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z))
        q *= 1.0 + 0.10 * sum(a * math.sin(w.dot(d) * 3.0 + ph) for w, ph, a in pb["waves"]) / 2.3
        pts.append(yaw @ (tilt @ q) + Vector((pb["x"], pb["y"], 0.0)))
    gaps = [p.z - sand_hit(tree, p.x, p.y)[0].z for p in pts]
    dz = max(-0.6 * ax.z - min(gaps), ax.z - max(gaps))
    dz = min(dz, -0.003 - min(gaps)) + lift
    verts = [bm.verts.new(p + Vector((0.0, 0.0, dz))) for p in pts]
    for q in quads:
        new_face(bm, [verts[i] for i in q], GRAVEL_IDX, L, pb["tone"], 0.0, P_PEBBLE)


def add_rock(bm, L, V, rk, tree, n):
    """Weathered sandstone: a lumpy ellipsoid cleaved by three planes."""
    dirs, quads = cube_sphere(n)
    yaw = rotz(math.degrees(rk["yaw"]))
    r = rk["r"]
    ax = Vector((r * rk["long"], r, r * rk["flat"]))
    pts = []
    for d in dirs:
        q = Vector((d.x * ax.x, d.y * ax.y, d.z * ax.z))
        q *= 1.0 + sum(a * math.sin(3.0 * w.dot(d) + ph) for w, ph, a in rk["waves"])
        for cn, off in rk["cuts"]:
            lim = off * r * (0.9 + 0.1 * abs(cn.z))
            e = q.dot(cn) - lim
            if e > 0.0:
                q = q - cn * e
        pts.append(yaw @ q + Vector((rk["x"], rk["y"], 0.0)))
    gaps = [p.z - sand_hit(tree, p.x, p.y)[0].z for p in pts]
    height = max(p.z for p in pts) - min(p.z for p in pts)
    dz = -max(0.012, 0.22 * height) - min(gaps)
    verts = [bm.verts.new(p + Vector((0.0, 0.0, dz))) for p in pts]
    for q in quads:
        new_face(bm, [verts[i] for i in q], ROCK_IDX, L, rk["tone"], 0.0, P_ROCK)


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


def add_wood(bm, L, V, lay, tree, lift):
    br = lay.plan["branch"]
    pts, radii = lying_path(tree, BRANCH[0], BRANCH[1], br["wig"], 0.035, 0.030, 0.013, 12, 0.40)
    pts = [p + UP * lift for p in pts]
    d = (pts[-1] - pts[-2]).normalized()
    add_tube(bm, pts, radii, 10, WOOD_IDX, L, V, br["tone"], P_WOOD, zone=0.0,
             tip=pts[-1] + d * (2.4 * radii[-1]) + UP * 0.003, alongs=[k / 11.0 for k in range(12)])
    n = len(pts)
    for t, az, ln in br["twigs"]:
        k = t * (n - 1)
        i = min(int(k), n - 2)
        f = k - i
        p = pts[i].lerp(pts[i + 1], f)
        dd = (pts[i + 1] - pts[i]).normalized()
        side = UP.cross(dd).normalized()
        r = radii[i] + (radii[i + 1] - radii[i]) * f
        tw = (dd * 0.55 + side * az + UP * 0.30).normalized()
        start = p - tw * (0.5 * r)
        tp = [start + tw * (ln * s) + UP * (-0.02 * ln * s * s) for s in (0.0, 0.35, 0.7, 0.92)]
        add_tube(bm, tp, [0.55 * r, 0.45 * r, 0.36 * r, 0.26 * r], 7, WOOD_IDX, L, V, br["tone"], P_WOOD,
                 tip=start + tw * ln + UP * (-0.02 * ln))
    # fallen saguaro ribs: long woody rods
    for (a, b), rp in zip(RODS, lay.plan["rods"]):
        pts, radii = lying_path(tree, a, b, [1.0, -0.5, 0.8], rp["bow"], 0.0105, 0.0085, 8, 0.35)
        pts = [p + UP * lift for p in pts]
        add_tube(bm, pts, radii, 6, WOOD_IDX, L, V, rp["tone"], P_WOOD, zone=3.0,
                 alongs=[k / 7.0 for k in range(8)], phase=rp["bow"] * 50.0)


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

def build_garden_mesh(name, plan, lay, detail="low", lean=False, float_spines=False, float_cover=False):
    bm = bmesh.new()
    try:
        L = {"tone": bm.faces.layers.float.new("Tone"),
             "zone": bm.faces.layers.float.new("Zone"),
             "part": bm.faces.layers.int.new("Part")}
        V = {"skirt": bm.verts.layers.float.new("Skirt"),
             "rib": bm.verts.layers.float.new("Rib"),
             "along": bm.verts.layers.float.new("Along")}

        add_sand(bm, L, V, DISC_N[detail])
        bm.faces.ensure_lookup_table()
        bm.normal_update()
        tree = BVHTree.FromBMesh(bm)

        lift = FLOAT_SPINES if float_spines else 0.0
        bm.verts.ensure_lookup_table()
        n0 = len(bm.verts)
        add_saguaro(bm, L, V, lay, lift)
        bm.verts.ensure_lookup_table()
        if lean:
            n1 = len(bm.verts)
            rot = Matrix.Rotation(math.radians(LEAN_DEG), 3, Vector((math.sin(0.4), -math.cos(0.4), 0.0)))
            foot = lay.sag_foot
            for i in range(n0, n1):
                v = bm.verts[i]
                v.co = foot + rot @ (v.co - foot)
        add_barrel(bm, L, V, lay, lift)
        add_pear(bm, L, V, lay, lift)
        add_agave(bm, L, V, lay, tree)
        for rk in lay.rocks:
            add_rock(bm, L, V, rk, tree, 6 if detail == "low" else 9)
        cover = FLOAT_COVER if float_cover else 0.0
        add_wood(bm, L, V, lay, tree, cover)
        for tf in lay.tufts:
            add_tuft(bm, L, V, tf, tree, cover)
        for pb in lay.pebbles:
            add_pebble(bm, L, V, pb, tree, cover)

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
        # Gravel flat-shaded, as chips; everything else smooth, with every
        # material boundary and every fold sharper than 60 degrees a hard
        # edge — 32 on the rocks, so each cleavage plane stays a broken face.
        part = L["part"]
        for face in bm.faces:
            face.smooth = face[part] not in FLAT_PARTS
        for edge in bm.edges:
            mats_ = {f.material_index for f in edge.link_faces}
            if len(mats_) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                limit = 32.0 if edge.link_faces[0][part] == P_ROCK else 60.0
                edge.smooth = edge.calc_face_angle() < math.radians(limit)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def build_collider_source(name):
    """The sand disc alone, coarse: players brush through the plants."""
    bm = bmesh.new()
    try:
        for j in range(32):
            th = TAU * j / 32
            X, Y = math.cos(th), math.sin(th)
            wob = disc_wobble(th)
            for f in (1.0, 0.78):
                x, y = DISC_A[0] * X * wob * f, DISC_A[1] * Y * wob * f
                bm.verts.new((x, y, 0.0 if f == 1.0 else sand_height(x, y)))
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
    mat, nt, bsdf, coord = surface("DesertSand")
    drift = noise(nt, coord, 1.4, 4.0, 0.55)
    col = ramp(nt, drift, ((0.30, (0.118, 0.088, 0.060)), (0.55, (0.150, 0.112, 0.076)),
                           (0.80, (0.168, 0.128, 0.088))))
    # wind ripples: low bands across the drift, their troughs a shade darker
    rip = wave(nt, mapping(nt, coord, scale=(1.0, 1.0, 1.0), rot=(0.0, 0.0, 0.55)), 14.0, 5.0, 2.0)
    col = mix_color(nt, col, (0.092, 0.068, 0.047), remap(nt, rip, 0.0, 0.45, 0.35, 0.0))
    # a gravel lag: dark basalt and rusty grains among the sand
    g0, g1, _gd = voronoi_color(nt, coord, 70.0)
    col = mix_color(nt, col, (0.040, 0.036, 0.033), remap(nt, g0, 0.90, 0.94, 0.0, 0.85))
    col = mix_color(nt, col, (0.130, 0.062, 0.036), remap(nt, g1, 0.90, 0.94, 0.0, 0.70))
    fines = voronoi_color(nt, coord, 260.0)[0]
    col = mix_color(nt, col, (0.20, 0.17, 0.13), remap(nt, fines, 0.90, 0.96, 0.0, 0.5))
    # the disc's cut edge: pale caliche over red-brown sand over gravel
    wob = noise(nt, coord, 5.0, 3.0, 0.5)
    hz = math_node(nt, "ADD", remap(nt, height(nt, coord), 0.0, MOUND_Z * 0.7, 0.0, 1.0),
                   remap(nt, wob, 0.0, 1.0, -0.08, 0.08))
    prof = ramp(nt, hz, ((0.00, (0.078, 0.066, 0.056)), (0.30, (0.120, 0.070, 0.045)),
                         (0.55, (0.150, 0.100, 0.065)), (0.72, (0.200, 0.175, 0.140)),
                         (0.86, (0.130, 0.098, 0.066)), (1.00, (0.150, 0.112, 0.076))))
    stones = voronoi_color(nt, coord, 30.0)
    prof = mix_color(nt, prof, (0.07, 0.065, 0.06), math_node(nt, "MULTIPLY", remap(nt, stones[2], 0.14, 0.08, 0.0, 0.9),
                                                             remap(nt, hz, 0.40, 0.15, 0.0, 1.0)))
    col = mix_color(nt, col, prof, attr(nt, "Skirt"))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.93
    bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "MULTIPLY", rip, 0.6),
                             remap(nt, g0, 0.90, 0.94, 0.0, 0.5)), 0.30, 0.004)
    return mat


def skin_material():
    """Cactus skin, one substance across the three cacti; a face zone picks
    the species (0 saguaro, 1 barrel, 2 pad)."""
    mat, nt, bsdf, coord = surface("CactusSkin")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    rib = attr(nt, "Rib")
    along = attr(nt, "Along")
    sag = ramp(nt, tone, ((0.0, (0.068, 0.090, 0.056)), (1.0, (0.080, 0.100, 0.062))))
    barrel = ramp(nt, tone, ((0.0, (0.088, 0.100, 0.046)), (1.0, (0.100, 0.108, 0.052))))
    pad = ramp(nt, tone, ((0.0, (0.118, 0.148, 0.118)), (1.0, (0.140, 0.165, 0.130))))
    col = mix_color(nt, sag, barrel, remap(nt, zone, 0.4, 0.6, 0.0, 1.0))
    col = mix_color(nt, col, pad, remap(nt, zone, 1.4, 1.6, 0.0, 1.0))
    # pleats: dark valleys, a pale bloom of wax on the crests
    col = mix_color(nt, col, (0.018, 0.026, 0.016), remap(nt, rib, 0.0, 0.60, 0.80, 0.0))
    col = mix_color(nt, col, (0.135, 0.150, 0.112), remap(nt, rib, 0.80, 1.0, 0.0, 0.40))
    # fine streaks along the column and mottling
    streak = noise(nt, mapping(nt, coord, scale=(28.0, 28.0, 1.5)), 3.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.035, 0.045, 0.028), remap(nt, streak, 0.40, 0.70, 0.0, 0.45))
    mottle = noise(nt, coord, 9.0, 4.0, 0.55)
    col = mix_color(nt, col, (0.092, 0.092, 0.060), remap(nt, mottle, 0.60, 0.75, 0.0, 0.35))
    sag_zone = remap(nt, zone, 0.4, 0.6, 1.0, 0.0)
    # the saguaro's corky grey foot
    cork = math_node(nt, "MULTIPLY", remap(nt, along, 0.10, 0.03, 0.0, 1.0), sag_zone)
    col = mix_color(nt, col, (0.085, 0.072, 0.058), math_node(nt, "MULTIPLY", cork, 0.9))
    # pads flush purple at the rim under sun stress
    pad_zone = remap(nt, zone, 1.4, 1.6, 0.0, 1.0)
    col = mix_color(nt, col, (0.075, 0.040, 0.055),
                    math_node(nt, "MULTIPLY", remap(nt, along, 0.80, 1.0, 0.0, 0.55), pad_zone))
    # the barrel's woolly crown
    bar_zone = remap(nt, zone, 0.4, 0.6, 0.0, 1.0)
    bar_zone = math_node(nt, "MULTIPLY", bar_zone, remap(nt, zone, 1.4, 1.6, 1.0, 0.0))
    col = mix_color(nt, col, (0.20, 0.16, 0.10),
                    math_node(nt, "MULTIPLY", remap(nt, along, 0.965, 1.0, 0.0, 0.9), bar_zone))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, rib, 0.0, 1.0, 0.72, 0.48), bsdf.inputs["Roughness"])
    bump(nt, bsdf, math_node(nt, "ADD", streak, math_node(nt, "MULTIPLY", mottle, 0.4)), 0.18, 0.002)
    return mat


def spine_material():
    """Spines and felt: zone 0 a spine, 1 felt, 2 a hooked central, 3 a glochid tuft."""
    mat, nt, bsdf, coord = surface("CactusSpine")
    zone = attr(nt, "Zone")
    along = attr(nt, "Along")
    tone = attr(nt, "Tone")
    spine = mix_color(nt, (0.30, 0.28, 0.24), (0.075, 0.066, 0.058), remap(nt, along, 0.2, 1.0, 0.0, 1.0))
    spine = mix_color(nt, spine, (0.22, 0.18, 0.12), remap(nt, tone, 0.6, 1.0, 0.0, 0.5))
    felt = ramp(nt, tone, ((0.0, (0.20, 0.17, 0.12)), (1.0, (0.26, 0.22, 0.15))))
    hook = mix_color(nt, (0.330, 0.085, 0.040), (0.420, 0.300, 0.170), remap(nt, along, 0.5, 1.0, 0.0, 1.0))
    gloch = ramp(nt, tone, ((0.0, (0.26, 0.20, 0.08)), (1.0, (0.33, 0.26, 0.11))))
    col = mix_color(nt, spine, felt, band(nt, zone, 1.0, 1.0))
    col = mix_color(nt, col, hook, band(nt, zone, 2.0, 2.0))
    col = mix_color(nt, col, gloch, band(nt, zone, 3.0, 3.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, zone, 0.0, 1.0, 0.38, 0.90), bsdf.inputs["Roughness"])
    return mat


def fruit_material():
    """Zone 0 the barrel's yellow fruit, 1 the pear's magenta tunas."""
    mat, nt, bsdf, coord = surface("CactusFruit")
    zone = attr(nt, "Zone")
    tone = attr(nt, "Tone")
    along = attr(nt, "Along")
    yellow = ramp(nt, tone, ((0.0, (0.44, 0.32, 0.055)), (1.0, (0.40, 0.34, 0.080))))
    yellow = mix_color(nt, yellow, (0.30, 0.16, 0.06), remap(nt, along, 0.85, 1.0, 0.0, 0.6))
    tuna = ramp(nt, tone, ((0.0, (0.140, 0.080, 0.040)), (0.45, (0.230, 0.030, 0.075)),
                           (1.0, (0.200, 0.020, 0.085))))
    col = mix_color(nt, yellow, tuna, remap(nt, zone, 0.4, 0.6, 0.0, 1.0))
    dots = voronoi_color(nt, coord, 180.0)[0]
    col = mix_color(nt, col, (0.30, 0.24, 0.12), remap(nt, dots, 0.92, 0.97, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.42
    return mat


def flower_material():
    """Cream petals, a green floral tube (zone 2), a yellow stamen cushion (zone 3)."""
    mat, nt, bsdf, coord = surface("SaguaroFlower")
    zone = attr(nt, "Zone")
    along = attr(nt, "Along")
    col = mix_color(nt, (0.56, 0.52, 0.40), (0.66, 0.63, 0.52), remap(nt, along, 0.1, 0.8, 0.0, 1.0))
    col = mix_color(nt, col, (0.10, 0.12, 0.06), band(nt, zone, 2.0, 2.0))
    col = mix_color(nt, col, (0.50, 0.36, 0.06), band(nt, zone, 3.0, 3.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.5
    try:
        bsdf.inputs["Subsurface Weight"].default_value = 0.12
    except KeyError:
        pass
    return mat


def agave_material():
    mat, nt, bsdf, coord = surface("AgaveLeaf")
    tone = attr(nt, "Tone")
    along = attr(nt, "Along")
    col = ramp(nt, tone, ((0.0, (0.110, 0.135, 0.125)), (1.0, (0.135, 0.155, 0.140))))
    # pale imprints of the leaf that pressed on it in the bud
    imp = noise(nt, mapping(nt, coord, scale=(6.0, 6.0, 6.0)), 2.5, 2.0, 0.5)
    col = mix_color(nt, col, (0.150, 0.165, 0.140), remap(nt, imp, 0.55, 0.62, 0.0, 0.45))
    # a paler base, a brown terminal spine
    col = mix_color(nt, col, (0.16, 0.16, 0.12), remap(nt, along, 0.12, 0.0, 0.0, 0.6))
    col = mix_color(nt, col, (0.060, 0.036, 0.022), remap(nt, along, 0.86, 0.93, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    bump(nt, bsdf, imp, 0.08, 0.002)
    return mat


def rock_material():
    mat, nt, bsdf, coord = surface("Sandstone")
    tone = attr(nt, "Tone")
    col = ramp(nt, tone, ((0.0, (0.150, 0.085, 0.050)), (0.5, (0.185, 0.115, 0.070)),
                          (1.0, (0.165, 0.110, 0.078))))
    # bedding: soft bands through the stone
    beds = noise(nt, mapping(nt, coord, scale=(1.5, 1.5, 22.0)), 2.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.225, 0.160, 0.105), remap(nt, beds, 0.52, 0.62, 0.0, 0.6))
    col = mix_color(nt, col, (0.095, 0.052, 0.032), remap(nt, beds, 0.40, 0.32, 0.0, 0.5))
    # desert varnish in dark patches, pale lichen flecks
    varnish = noise(nt, coord, 6.0, 4.0, 0.6)
    col = mix_color(nt, col, (0.045, 0.030, 0.022), remap(nt, varnish, 0.58, 0.72, 0.0, 0.70))
    fleck = voronoi_color(nt, coord, 120.0)[0]
    col = mix_color(nt, col, (0.26, 0.24, 0.20), remap(nt, fleck, 0.93, 0.97, 0.0, 0.35))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    grit = noise(nt, coord, 60.0, 3.0, 0.6)
    bump(nt, bsdf, math_node(nt, "ADD", grit, math_node(nt, "MULTIPLY", beds, 0.8)), 0.35, 0.004)
    return mat


def gravel_material():
    mat, nt, bsdf, coord = surface("Gravel")
    tone = attr(nt, "Tone")
    col = ramp(nt, tone, ((0.00, (0.060, 0.055, 0.050)), (0.30, (0.130, 0.072, 0.045)),
                          (0.55, (0.170, 0.140, 0.100)), (0.80, (0.090, 0.082, 0.074)),
                          (1.00, (0.230, 0.215, 0.190))))
    speck = noise(nt, coord, 40.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.04, 0.035, 0.03), remap(nt, speck, 0.55, 0.72, 0.0, 0.5))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    bump(nt, bsdf, speck, 0.2, 0.002)
    return mat


def wood_material():
    """Sun-bleached wood: zone 0 the branch, 1 the saguaro's boot, 2 a scar,
    3 a fallen saguaro rib."""
    mat, nt, bsdf, coord = surface("DryWood")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    g = mapping(nt, coord, scale=(3.0, 55.0, 55.0), rot=(0.0, 0.0, -math.atan2(BRANCH[1][1] - BRANCH[0][1],
                                                                            BRANCH[1][0] - BRANCH[0][0])))
    grain = noise(nt, g, 1.5, 6.0, 0.6)
    col = ramp(nt, grain, ((0.30, (0.150, 0.140, 0.125)), (0.50, (0.235, 0.220, 0.195)),
                           (0.72, (0.300, 0.285, 0.255))))
    col = mix_color(nt, col, (0.20, 0.16, 0.12), remap(nt, tone, 0.0, 1.0, 0.0, 0.35))
    cracks = noise(nt, mapping(nt, g, scale=(0.7, 0.5, 0.5)), 3.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.045, 0.040, 0.035), remap(nt, cracks, 0.60, 0.68, 0.0, 0.8))
    # the saguaro's callus: corky, dark, fissured
    cork = noise(nt, coord, 30.0, 5.0, 0.65)
    callus = ramp(nt, cork, ((0.35, (0.022, 0.017, 0.014)), (0.60, (0.058, 0.043, 0.032)),
                             (0.80, (0.090, 0.072, 0.054))))
    callus = mix_color(nt, callus, (0.070, 0.060, 0.050), remap(nt, zone, 1.5, 2.0, 0.0, 0.3))
    col = mix_color(nt, col, callus, band(nt, zone, 1.0, 2.0))
    # fallen ribs: grey, split lengthwise
    col = mix_color(nt, col, (0.170, 0.160, 0.145), math_node(nt, "MULTIPLY", band(nt, zone, 3.0, 3.0), 0.5))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    bump(nt, bsdf, math_node(nt, "ADD", grain, math_node(nt, "ADD", cracks, cork)), 0.40, 0.003)
    return mat


def grass_material():
    mat, nt, bsdf, coord = surface("DryGrass")
    tone = attr(nt, "Tone")
    along = attr(nt, "Along")
    col = ramp(nt, tone, ((0.0, (0.150, 0.118, 0.062)), (0.5, (0.215, 0.172, 0.092)),
                          (1.0, (0.250, 0.215, 0.130))))
    col = mix_color(nt, col, (0.12, 0.10, 0.07), remap(nt, along, 0.25, 0.0, 0.0, 0.6))
    col = mix_color(nt, col, (0.30, 0.28, 0.22), remap(nt, along, 0.7, 1.0, 0.0, 0.5))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.75
    return mat


def garden_materials():
    """Ten slots, in index order: shared by the check and the render."""
    return (sand_material(), skin_material(), spine_material(), fruit_material(), flower_material(),
            agave_material(), rock_material(), gravel_material(), wood_material(), grass_material())


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
    for key, pid in (("sand", P_SAND), ("trunk", P_TRUNK), ("arms", P_ARM), ("barrel", P_BARREL),
                     ("pads", P_PAD), ("agave", P_AGAVE)):
        out[key] = [s for s in parts if s.part == pid]
    out["spines"] = [s for s in parts if s.part in SPINE_PARTS]
    return out


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
    return None if loc is None else loc.z


PARITY_DIR = Vector((0.31, 0.47, 0.83)).normalized()


def inside(tree, p):
    """Ray parity: an odd number of crossings out of a closed shell. A
    nearest face's normal is no witness near a thin pad's rim, where the
    nearest face can stand edge-on to the point."""
    count, o = 0, p.copy()
    for _ in range(64):
        loc, _n, _i, _d = tree.ray_cast(o, PARITY_DIR, 10.0)
        if loc is None:
            break
        count += 1
        o = loc + PARITY_DIR * 1e-6
    return count % 2 == 1


def signed_depth(tree, p):
    """How far ``p`` lies inside the closed shell of ``tree`` (negative outside)."""
    loc, _nrm, _i, dist = tree.find_nearest(p)
    if loc is None:
        return -9.0
    return dist if inside(tree, p) else -dist


def slab_centroid(pts, z0, z1):
    sel = [p for p in pts if z0 <= p.z <= z1]
    if not sel:
        return None
    c = sum(sel, Vector()) / len(sel)
    return c


def trunk_axis_audit(trunk, sand):
    """The trunk's axis from a bottom and a top slab's centroids, its lean,
    its height over the sand at the foot and its crest diameter mid-column."""
    zlo = min(p.z for p in trunk.pts)
    zhi = max(p.z for p in trunk.pts)
    H = zhi - zlo
    c0 = slab_centroid(trunk.pts, zlo + 0.12 * H, zlo + 0.20 * H)
    c1 = slab_centroid(trunk.pts, zlo + 0.70 * H, zlo + 0.78 * H)
    d = c1 - c0
    lean = math.degrees(math.atan2(hor(d).length, d.z))
    ground = ray_down(sand.tree, c0.x, c0.y)
    height = zhi - (ground if ground is not None else 0.0)

    def axis_at(z):
        f = (z - c0.z) / d.z
        return c0 + d * f

    # the construction frame: the trunk turned about its lower slab so its
    # measured axis is vertical, so a leaning trunk still shows level rings
    rot = d.normalized().rotation_difference(UP).to_matrix()
    upright = [c0 + rot @ (p - c0) for p in trunk.pts]
    return axis_at, lean, height, c0, ground, upright


def ring_at(pts, z_target, gap=0.01):
    """The ring of vertices nearest ``z_target``: vertices near that height
    split wherever consecutive heights jump by more than ``gap``, so a ring
    tilted a fraction of a degree still comes out whole."""
    near = sorted((p for p in pts if abs(p.z - z_target) < 0.08), key=lambda p: p.z)
    groups, cur = [], []
    for p in near:
        if cur and p.z - cur[-1].z > gap:
            groups.append(cur)
            cur = []
        cur.append(p)
    if cur:
        groups.append(cur)
    return min(groups, key=lambda g: abs(sum(p.z for p in g) / len(g) - z_target))


def rib_audit(pts, z_target):
    """The ring nearest ``z_target``: its crests (local radius maxima about
    the ring's centroid), and the spread of the gaps between them."""
    ring = ring_at(pts, z_target)
    c = sum(ring, Vector()) / len(ring)
    polar = sorted((math.atan2(p.y - c.y, p.x - c.x), hor(p - c).length) for p in ring)
    n = len(polar)
    crests = [polar[i][0] for i in range(n)
              if polar[i][1] > polar[i - 1][1] and polar[i][1] > polar[(i + 1) % n][1]]
    gaps = [math.degrees((crests[(i + 1) % len(crests)] - crests[i]) % TAU) for i in range(len(crests))]
    diameter = 2.0 * max(r for _a, r in polar)
    return len(crests), (max(gaps) - min(gaps)) if gaps else 99.0, diameter


def arm_audit(arms, trunk, axis_at):
    """Each arm: its deepest vertex inside the trunk, measured radially from
    the trunk's axis at the vertex's own height (a ray out onto the trunk)."""
    out = []
    for arm in arms:
        best = -9.0
        for p in arm.pts:
            a = axis_at(p.z)
            dv = hor(p - a)
            if dv.length < 1e-6:
                continue
            loc, _n, _i, dist = trunk.tree.ray_cast(Vector((a.x, a.y, p.z)), dv.normalized(), 2.0)
            if loc is None:
                continue
            best = max(best, dist - dv.length)
        out.append(best)
    return out


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


def pad_audit(pads, sand):
    """Each pad's joint: the extreme vertex down its long axis. A root pad's
    joint lies under the sand (its depth); a child's lies inside another pad,
    and its seat is how far the child's axis runs on inside that pad."""
    roots, seats = [], []
    for s in pads:
        c, ax = principal_axis(s.pts)
        if ax.z < 0.0:
            ax = -ax
        J = min(s.pts, key=lambda p: (p - c).dot(ax))
        g = ray_down(sand.tree, J.x, J.y)
        if g is not None and g > J.z:
            roots.append(g - J.z)
            continue
        best = None
        for o in pads:
            if o is s:
                continue
            dep = signed_depth(o.tree, J)
            if best is None or dep > best[0]:
                best = (dep, o)
        dep, host = best
        if dep > 0.0:
            loc, _n, _i, dist = host.tree.ray_cast(J + ax * 1e-5, ax, 1.0)
            seats.append(dist if loc is not None else 0.0)
        else:
            seats.append(dep)
    return roots, seats


def mass_audit(trunk, arms, c0):
    pts = list(trunk.pts)
    for a in arms:
        pts += a.pts
    m = sum(pts, Vector()) / len(pts)
    return hor(m - c0).length


def spine_audit(spines, hosts):
    """Every spine cluster's deepest vertex under the skin of the host it
    sits on (the host whose surface is nearest the cluster's centre)."""
    depths = []
    for s in spines:
        best = None
        for h in hosts:
            if (s.centre.x < h.lo.x - 0.05 or s.centre.x > h.hi.x + 0.05 or s.centre.y < h.lo.y - 0.05
                    or s.centre.y > h.hi.y + 0.05 or s.centre.z < h.lo.z - 0.05 or s.centre.z > h.hi.z + 0.05):
                continue
            loc, _n, _i, dist = h.tree.find_nearest(s.centre)
            if loc is not None and (best is None or dist < best[0]):
                best = (dist, h)
        if best is None:
            depths.append(-9.0)
            continue
        host = best[1]
        depths.append(max(signed_depth(host.tree, p) for p in s.pts))
    return depths


def bed_audit(body, sand, sectors=8):
    """A body's most-buried vertex in each sector round its foot, under the
    sand straight above it: the shallowest sector."""
    zlo = min(p.z for p in body.pts)
    foot = [p for p in body.pts if p.z < zlo + 0.02]
    c = sum(foot, Vector()) / len(foot)
    best = [-9.0] * sectors
    for p in body.pts:
        if p.z > zlo + 0.25:
            continue
        g = ray_down(sand.tree, p.x, p.y)
        if g is None:
            continue
        k = int(((math.atan2(p.y - c.y, p.x - c.x) + math.pi) / TAU) * sectors) % sectors
        best[k] = max(best[k], g - p.z)
    return min(best)


def leaf_bed_audit(leaves, sand):
    out = []
    for s in leaves:
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
    sand = cls["sand"][0]
    others = [s for s in cls["all"] if s is not sand]
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
        result = bmesh.ops.convex_hull(bm, input=list(bm.verts))
        interior = [g for g in result.get("geom_interior") or [] if g.is_valid]
        if interior:
            bmesh.ops.delete(bm, geom=interior, context="VERTS")
        unused = [g for g in result.get("geom_unused") or [] if g.is_valid]
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
    img = bpy.data.images.new("CactusNrm", size, size, alpha=True, float_buffer=False)
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


def check(skip_decimate, lift_z=False, stray_vert=False, short_arm=False, shallow_pad=False,
          lean_saguaro=False, skew_ribs=False, float_spines=False, perch_barrel=False, float_cover=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    plan = plan_garden()
    lay = Layout(plan, short_arm=short_arm, shallow_pad=shallow_pad, perch_barrel=perch_barrel,
                 skew_ribs=skew_ribs)
    flags = dict(lean=lean_saguaro, float_spines=float_spines, float_cover=float_cover)
    low = build_garden_mesh("CactusLow", plan, lay, "low", **flags)
    high = build_garden_mesh("CactusHigh", plan, lay, "high", **flags)
    mats = garden_materials()
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
        return (fail("garden mesh did not build", 3),) + none2

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
    if len(cls["sand"]) != 1 or len(cls["trunk"]) != 1 or len(cls["barrel"]) != 1:
        return (fail(f"sand, trunk or barrel shell not found: {len(cls['sand'])}, {len(cls['trunk'])}, "
                     f"{len(cls['barrel'])}", 3),) + none2
    sand, trunk, barrel = cls["sand"][0], cls["trunk"][0], cls["barrel"][0]
    axis_at, lean, sag_height, c0, g_foot, upright = trunk_axis_audit(trunk, sand)
    mass_off = mass_audit(trunk, cls["arms"], c0)
    trunk_ribs, trunk_spread, trunk_d = rib_audit(upright, (g_foot or 0.0) + 1.0)
    b_mid = 0.5 * (min(p.z for p in barrel.pts) + max(p.z for p in barrel.pts))
    barrel_ribs, barrel_spread, _bd = rib_audit(barrel.pts, b_mid)
    bites = arm_audit(cls["arms"], trunk, axis_at)
    pad_roots, pad_seats = pad_audit(cls["pads"], sand)
    hosts = [trunk, barrel] + cls["arms"] + cls["pads"]
    spine_depths = spine_audit(cls["spines"], hosts)
    bed_bodies = [bed_audit(trunk, sand), bed_audit(barrel, sand)]
    leaf_beds = leaf_bed_audit(cls["agave"], sand)
    nshells, nloose, loose_kinds = cover_audit(cls)

    img, tex = setup_bake_image(low, sand_mat)
    if img is None:
        return (fail("garden has no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "CactusLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "CactusLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("CactusColSrc")
    collider = convex_hull_collider(collider_src, "CactusCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_cactus_garden_{os.getpid()}.glb")
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
          f"outer={OUTER_SIZE} zmin={bb[2]:.5f}")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured shells={len(cls['all'])} arms={len(cls['arms'])} pads={len(cls['pads'])} "
          f"spine_clusters={len(cls['spines'])} agave_leaves={len(cls['agave'])} "
          f"pebbles={len(lay.pebbles)}")
    print(f"measured arm_bites={[round(b, 4) for b in bites]}")
    print(f"measured pad_roots={[round(b, 4) for b in pad_roots]} pad_seats={[round(b, 4) for b in pad_seats]}")
    print(f"measured saguaro lean={lean:.3f}deg mass_off={mass_off:.4f} height={sag_height:.4f} "
          f"crest_d={trunk_d:.4f}")
    print(f"measured ribs trunk n={trunk_ribs} spread={trunk_spread:.3f}deg "
          f"barrel n={barrel_ribs} spread={barrel_spread:.3f}deg")
    if spine_depths:
        print(f"measured spine roots n={len(spine_depths)} min={min(spine_depths):.5f} "
              f"max={max(spine_depths):.5f}")
    print(f"measured bed bodies={[round(b, 4) for b in bed_bodies]} "
          f"leaves min={min(leaf_beds):.4f} max={max(leaf_beds):.4f}")
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
    if len(bites) != len(ARMS) or any(not (ARM_BITE_MIN <= b <= ARM_BITE_MAX) for b in bites):
        return (fail(f"arm joints: {len(bites)}/{len(ARMS)} arms, deepest vertex inside the trunk "
                     f"{[round(b, 4) for b in bites]} m, not all in [{ARM_BITE_MIN}, {ARM_BITE_MAX}]",
                     17),) + none2
    n_child = sum(1 for p in PADS if p[0] == "child")
    if (len(pad_seats) != n_child or len(pad_roots) != len(PADS) - n_child
            or any(not (PAD_SEAT_MIN <= s <= PAD_SEAT_MAX) for s in pad_seats)):
        return (fail(f"pad joints: {len(pad_seats)}/{n_child} child pads, seat along the axis "
                     f"{[round(s, 4) for s in pad_seats]} m, not all in [{PAD_SEAT_MIN}, {PAD_SEAT_MAX}]",
                     18),) + none2
    if (lean > LEAN_MAX_DEG or mass_off > MASS_OFF_MAX or abs(sag_height - SAG_H) > SAG_H_TOL
            or not (SAG_D_BAND[0] <= trunk_d <= SAG_D_BAND[1])):
        return (fail(f"saguaro: lean {lean:.3f} deg (max {LEAN_MAX_DEG}), mass centre {mass_off:.4f} m off "
                     f"the foot (max {MASS_OFF_MAX}), height {sag_height:.4f} m ({SAG_H} +- {SAG_H_TOL}), "
                     f"crest diameter {trunk_d:.4f} m (band {SAG_D_BAND})", 19),) + none2
    if (trunk_ribs != SAG_RIBS or barrel_ribs != BARREL_RIBS or trunk_spread > RIB_SPREAD_MAX
            or barrel_spread > RIB_SPREAD_MAX):
        return (fail(f"ribs: trunk {trunk_ribs}/{SAG_RIBS} spread {trunk_spread:.3f} deg, barrel "
                     f"{barrel_ribs}/{BARREL_RIBS} spread {barrel_spread:.3f} deg "
                     f"(max {RIB_SPREAD_MAX})", 20),) + none2
    if not spine_depths or min(spine_depths) < ROOT_MIN or max(spine_depths) > ROOT_MAX:
        return (fail(f"spine clusters: {len(spine_depths)}, deepest vertex under the skin "
                     f"{min(spine_depths):.5f}-{max(spine_depths):.5f} m, not in [{ROOT_MIN}, {ROOT_MAX}]",
                     21),) + none2
    beds = bed_bodies + pad_roots
    if (any(not (BED_MIN <= b <= BED_MAX) for b in beds) or len(leaf_beds) != AGAVE_N
            or any(not (LEAF_BED_MIN <= b <= LEAF_BED_MAX) for b in leaf_beds)):
        return (fail(f"bedding: saguaro, barrel and root pads {[round(b, 4) for b in beds]} m under the "
                     f"sand (band [{BED_MIN}, {BED_MAX}]); agave leaves {min(leaf_beds):.4f}-"
                     f"{max(leaf_beds):.4f} m (band [{LEAF_BED_MIN}, {LEAF_BED_MAX}])", 22),) + none2
    if nloose:
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

    # Key, fill, rim and the warm wedge on the back wall.
    light("Key", (-3.6, -4.6, 5.0), 300.0, 2.6, (1.0, 0.94, 0.85), spread=16.0)
    light("Fill", (6.0, -3.5, 1.4), 9.0, 7.0, (0.72, 0.82, 1.0))
    light("Rim", (-1.6, 3.4, 3.4), 150.0, 2.6, (0.62, 0.78, 1.0))
    light("Wedge", (3.8, 1.2, 2.6), 300.0, 3.4, (1.0, 0.75, 0.50),
          target=(2.2, WALL_Y - 1.2, 0.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.36, -0.93, 0.0)).normalized()
    cam.location = centre + view * 7.75 + Vector((0.0, 0.0, 1.00))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.10))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the flowers.
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
    p.add_argument("--short-arm", action="store_true")
    p.add_argument("--shallow-pad", action="store_true")
    p.add_argument("--lean-saguaro", action="store_true")
    p.add_argument("--skew-ribs", action="store_true")
    p.add_argument("--float-spines", action="store_true")
    p.add_argument("--perch-barrel", action="store_true")
    p.add_argument("--float-cover", action="store_true")
    args = p.parse_args(argv)

    code, low, _sand = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_arm=args.short_arm,
        shallow_pad=args.shallow_pad,
        lean_saguaro=args.lean_saguaro,
        skew_ribs=args.skew_ribs,
        float_spines=args.float_spines,
        perch_barrel=args.perch_barrel,
        float_cover=args.float_cover,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("cactus-garden OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
