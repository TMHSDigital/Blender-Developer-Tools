"""Game-ready Scots pine — a showcase piece, not an example.

Asserts budget conformance of a procedural mature Scots pine after
composing shipped pipeline pieces: bmesh construction, UVs, six materials,
high-to-low normal bake, LOD chain, convex trunk collider, Unity glTF export.

The trunk is one lathe from a buttressed root flare, bedded in a mound of
needle-litter soil, to a leader shoot: a tall straight bole whose deep
plate ridges fade out into the thin upper bark. Five surface roots leave the
flare and dive into the soil. Eight whorls of heavy limbs rise above the bare
lower bole, where dead stubs and two long dead limbs stay on. Each limb is
seated in the trunk and carries side twigs, and every limb and twig ends inside a blue-green needle clump: a pom-pom of long
needle tufts drawn out of a small flattened core. The clumps overlap into a
broad, rounded crown. Cones hang under the upper limbs; fallen cones, two
mossy stones and dead sticks lie on the soil disc.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-branches`` the branch seat
in the trunk, ``--lean-crown`` trunk plumb, ``--bunch-whorls`` the whorl
tier spacing, ``--short-twigs`` the clump seat on its twig,
``--float-litter`` the ground cover bedded in the soil, ``--drop-cones``
one connected assembly.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python pine_tree.py --
    blender --background --python pine_tree.py -- --skip-decimate
    blender --background --python pine_tree.py -- --output pine.png
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

SEED = 1759
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))

# --- Ground ------------------------------------------------------------------
DISC_R = 1.80           # soil disc radius before its wobble, m
DISC_EDGE = 0.16        # the rim rolls down over this fraction of the radius
DISC_N = 20
MOUND_Z = 0.170
TRUNK_BED = 0.100       # the trunk's foot this far under the lowest soil round it

# --- Trunk -------------------------------------------------------------------
TRUNK_TOP = 6.70        # the lathe's top ring; the leader shoot runs on from it
TRUNK_R_BASE = 0.200    # taper term at z = 0 (above the flare)
TRUNK_R_TIP = 0.030
TRUNK_TAPER = 1.10
TRUNK_SIDES = 20
TRUNK_SIDES_HIGH = 40
COLLIDER_SIDES = 14     # the hull needs no more than this
RIDGES = 12             # vertical plate ridges round the girth
RIDGE_AMP = 0.070       # fraction of the radius, on the plated lower bole
RIDGE_AMP_TOP = 0.012   # and on the thin flaking bark above
PLATE_Z = (1.9, 3.0)    # the plates fade out over this height
FLARE_R = 0.200         # extra radius at the soil, on the buttress lobes
FLARE_H = 0.30
FLARE_LOBES = 5
SWAY = (0.022, 0.018)   # trunk axis sway, x and y amplitude (m)
DBH_Z = 1.30            # breast height above the soil

# --- Roots -------------------------------------------------------------------
ROOT_SIDES = 6
ROOT_REACH = (0.78, 0.98)

# --- Whorls, limbs, twigs ------------------------------------------------------
WHORLS = 8
WHORL_Z0 = 3.05
WHORL_STEP = 0.470
WHORL_STEP_SHRINK = 0.012
WHORL_STEP_JITTER = 0.030
BRANCHES = (3, 5)       # per whorl, inclusive
LIMB_L = (1.30, 2.25)   # reach = a + b (1 - f^1.6), f the whorl's height fraction
SPREAD_AZ = -26.8       # the crown is broadest across this bearing, deg
SPREAD = 0.16           # reach x (1 + SPREAD cos 2(yaw - SPREAD_AZ))
BRANCH_SEAT = 0.45      # limb base centre, as a fraction of the trunk radius
LIMB_STEPS = 7
LIMB_SIDES = 6
TWIG_SIDES = 4

# --- Needle clumps -------------------------------------------------------------
CLUMP_GRID = 3          # the core is a cube-sphere of 3 x 3 facets a side: 108 strands
CLUMP_CORE = 0.24       # core radius over the pad's radius
NEEDLE_LINES = 2.0      # needle lines across a tuft facet
SPLAY = 0.55            # tuft sideways scatter
CLUMP_BELOW = 0.75      # the pad's underside is this much flatter than its dome
CLUMP_RX = 0.74         # mean pad radius, m
CLUMP_LUMP = 0.40       # pad radius scatter, +/- half of this
CLUMP_TILT = 14.0       # a pad tips up to this far off level, deg
LEADER_UP = 0.36        # the leader clump's centre above the trunk's top ring

CONE_LEN = 0.090
CONE_R = 0.028

# --- Dead wood -----------------------------------------------------------------
STUBS = ((1.05, 0.9), (1.55, 3.1), (2.05, 4.9), (2.45, 2.0), (2.85, 5.9))  # (z, yaw)
DEAD_BRANCHES = ((2.20, 2.70, 1.30), (2.62, 5.95, 1.00))                  # (z, yaw, length)

# --- Ground cover ----------------------------------------------------------------
FALLEN_CONES = ((0.62, -0.80, 20.0), (0.98, -0.38, 130.0), (-0.52, -0.98, 75.0),
                (0.22, -1.24, 160.0), (-1.10, -0.30, 40.0))          # (x, y, yaw deg)
STONES = ((-0.98, -0.62, 0.27, 0.19, 30.0), (1.10, 0.50, 0.19, 0.13, 110.0))  # x, y, r, h, yaw
STICKS = (((0.30, -0.58), (1.12, -1.02), 0.020), ((-1.25, 0.18), (-0.78, -0.56), 0.016))
REST_SINK = 0.010       # a fallen cone or stick's lowest point this far into the soil
STONE_BED = 0.025       # a stone's whole underside at least this far under the soil

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (9.284, 7.932, 7.659)
BASE_TRIS_MIN = 43500
BASE_TRIS_MAX = 46000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 6
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 60
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# face floors: bark, needles, cone, deadwood, soil, stone
FACE_FLOORS = (2850, 35000, 950, 250, 820, 170)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Branch seat: each limb's (and dead stub's) base centre sits inside the
# trunk, measured as its radial distance from the trunk axis at that height
# over the trunk surface's radius on the same bearing (raycast from the axis).
SEAT_RATIO_MIN = 0.25
SEAT_RATIO_MAX = 0.75
FLOAT_BRANCHES = 1.20   # --float-branches starts every limb at 1.2 x radius
# Whorl tiers: limb bases cluster into whorls; gaps between whorls in band.
WHORL_SPLIT = 0.18
WHORL_SPREAD_MAX = 0.06
WHORL_GAP_MIN = 0.32
WHORL_GAP_MAX = 0.60
BUNCH_WHORL = 4
BUNCH_LIFT = 0.24
# Plumb and balance: trunk lean from ring centroids, the needle mass's
# centre over the trunk base, and the breast-height diameter.
LEAN_MAX_DEG = 1.0
BALANCE_MAX = 0.15      # needle-area centroid off the base axis, m
DBH = 0.377
DBH_TOL = 0.020
LEAN_BEND = 0.030       # --lean-crown bends the bole x += k (z - z0)^2, z0 <= z <= zc
LEAN_Z0 = 1.0
LEAN_ZC = 2.95          # just under the lowest whorl
# Clump seat: every clump's own carrier (limb, twig or leader) ends
# deep inside it, as the signed depth of the carrier's deepest vertex.
CLUMP_BITE_MIN = 0.040
SHORT_Q = 0.64          # --short-twigs: every carrier stops among the tufts, short of the core
# Ground cover: lowest vertex under the soil straight above it.
REST_BAND = (0.004, 0.040)
STONE_BAND = (0.015, 0.120)
ROOT_BED_MIN = 0.030    # every root's deepest vertex under the soil
TRUNK_BED_MIN = 0.050
FLOAT_LITTER = 0.080    # --float-litter lifts cones, stones and sticks
DROP_CONES = 0.05
# Hero yaw about Z only (level on the stage).
HERO_YAW_DEG = 0.0
WALL_Y = 9.0

BARK_IDX = 0
NEEDLE_IDX = 1
CONE_IDX = 2
DEAD_IDX = 3
SOIL_IDX = 4
STONE_IDX = 5
MAT_LABELS = ("bark", "needle", "cone", "deadwood", "soil", "stone")

# part tags, one per face, so the audits can name a shell's role
P_TRUNK, P_ROOT, P_LIMB, P_TWIG, P_CLUMP, P_CONE = 1, 2, 3, 4, 5, 6
P_STUB, P_DEAD, P_DEAD_TWIG, P_SOIL, P_STONE, P_LCONE, P_STICK = 7, 8, 9, 10, 11, 12, 13
CARRIER_PARTS = (P_LIMB, P_TWIG)
COVER_PARTS = (P_STONE, P_LCONE, P_STICK)


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
    """A closed-form draw in [0, 1) from three indices: per-facet variety
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
    return 1.0 + 0.035 * math.sin(3.0 * th + 0.7) + 0.025 * math.sin(5.0 * th + 2.1) \
        + 0.012 * math.sin(8.0 * th + 1.3)


def disc_radius(x, y):
    """Normalised disc radius: 1 on the soil's rim."""
    return math.hypot(x, y) / DISC_R / disc_wobble(math.atan2(y, x))


def soil_height(x, y):
    """A low mound of soil and needle litter heaped round the foot, rolled
    down to Z = 0 at the disc's rim."""
    rn2 = (x * x + y * y) / (DISC_R * DISC_R)
    z = MOUND_Z * (1.0 - 0.45 * rn2)
    z += 0.008 * math.sin(2.3 * x + 0.4) * math.cos(1.7 * y - 0.8) + 0.004 * math.sin(4.1 * x - 3.3 * y + 0.6)
    return z * smoothstep(1.0 - disc_radius(x, y), 0.0, DISC_EDGE)


def ground_min(cx, cy, r, n=24):
    return min(soil_height(cx + r * math.cos(TAU * k / n), cy + r * math.sin(TAU * k / n))
               for k in range(n))


# --------------------------------------------------------------------------
# The plan: every seeded draw happens here, before anything is built
# --------------------------------------------------------------------------

def trunk_radius(z):
    t = max(0.0, 1.0 - z / TRUNK_TOP)
    return TRUNK_R_TIP + TRUNK_R_BASE * t ** TRUNK_TAPER


def axis_at(z, lean=0.0):
    """Trunk axis centre at height z: a closed-form sway, zero at the ground."""
    x = SWAY[0] * (math.sin(1.1 * z + 0.3) - math.sin(0.3))
    y = SWAY[1] * (math.sin(0.8 * z + 1.9) - math.sin(1.9))
    if lean:
        # the bole bends; the crown above it is carried over rigidly, so the
        # envelope keeps its size and only the plumb budget can see it
        x += lean * (min(max(z, LEAN_Z0), LEAN_ZC) - LEAN_Z0) ** 2
    return Vector((x, y, z))


def plan_tree():
    rng = random.Random(SEED)

    def u(a, b):
        return a + (b - a) * rng.random()

    whorls = []
    z = WHORL_Z0
    for i in range(WHORLS):
        if i:
            z += WHORL_STEP - WHORL_STEP_SHRINK * i + u(-WHORL_STEP_JITTER, WHORL_STEP_JITTER)
        f = (z - WHORL_Z0) / (TRUNK_TOP - WHORL_Z0)
        n = BRANCHES[0] + min(BRANCHES[1] - BRANCHES[0], int(rng.random() * 3.0))
        yaw0 = i * math.radians(137.5) + u(-0.3, 0.3)
        branches = []
        for k in range(n):
            yaw = yaw0 + TAU * k / n + u(-0.35, 0.35)
            spread = 1.0 + SPREAD * math.cos(2.0 * (yaw - math.radians(SPREAD_AZ)))
            L = (LIMB_L[0] + LIMB_L[1] * (1.0 - f ** 1.6)) * u(0.76, 1.14) * spread
            br = {
                "z": z + u(-0.018, 0.018),
                "yaw": yaw,
                "L": L,
                "f": f,
                "elev": math.radians(13.0 + 26.0 * f + u(-5.0, 5.0)),
                "droop": (0.17 - 0.09 * f) * u(0.75, 1.25),
                "curl": u(-0.35, 0.35),
                "tipup": u(0.04, 0.10),
                "tone": rng.random(),
                "jit": [rng.random() for _ in range(24)],
                "cones": (f > 0.25 and rng.random() < 0.30),
                "cone_jit": [rng.random() for _ in range(6)],
            }
            br["n_side"] = max(1, min(3, int(round(L / 1.10))))
            branches.append(br)
        whorls.append({"z": z, "branches": branches})
    roots = []
    for k in range(FLARE_LOBES):
        roots.append({"yaw": TAU * k / FLARE_LOBES + 0.35 + u(-0.12, 0.12),
                      "reach": u(*ROOT_REACH), "tone": rng.random()})
    leader = {"tone": rng.random(), "yaw": u(0.0, TAU)}
    cover = {"cones": [(rng.random(), u(-0.25, 0.25)) for _c in FALLEN_CONES],
             "stones": [[rng.random() for _k in range(8)] for _s in STONES],
             "sticks": [rng.random() for _s in STICKS]}
    return {"whorls": whorls, "roots": roots, "leader": leader, "cover": cover}


def expected_clumps(plan):
    return 1 + sum(1 + br["n_side"] for wh in plan["whorls"] for br in wh["branches"])


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

class Builder:
    """The bmesh plus its face layers: Tone (shading variety), Part (the
    shell's role) and Carry (the clump a carrier ends in, or a clump's id)."""

    def __init__(self, bm):
        self.bm = bm
        self.tone = bm.faces.layers.float.new("Tone")
        self.part = bm.faces.layers.int.new("Part")
        self.carry = bm.faces.layers.int.new("Carry")
        self.tip = bm.verts.layers.float.new("Tip")   # 1 on a needle tuft's point
        # the packed UVMap first, so it stays the active (baked, exported) map;
        # NeedleUV runs across (x) and up (y) each tuft facet for the needle lines
        self.uv = bm.loops.layers.uv.new("UVMap")
        self.nuv = bm.loops.layers.uv.new("NeedleUV")
        self.next_clump = 0

    def face(self, verts, mat, tone, part, carry=-1, smooth=None):
        f = self.bm.faces.new(verts)
        f.material_index = mat
        f[self.tone] = tone
        f[self.part] = part
        f[self.carry] = carry
        if smooth is not None:
            f.smooth = smooth
        return f


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


def add_tube(B, pts, radii, sides, mat, tone, part, carry=-1, phase=0.0, jag=None):
    """Capped round bar swept along a polyline with a radius per point.
    ``jag``: per-vertex radial factors for the last ring (a broken end)."""
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
            ring.append(B.bm.verts.new(p + off + r * (n * math.cos(a) + b * math.sin(a))))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            B.face((r0[k], r0[m], r1[m], r1[k]), mat, tone, part, carry)
    B.face(tuple(reversed(rings[0])), mat, tone, part, carry)
    B.face(tuple(rings[-1]), mat, tone, part, carry)
    return [v for ring in rings for v in ring]


def resample(pts, count, length=None):
    """``count`` points at equal arc-length steps along a polyline, from its
    start to ``length`` along it (the whole of it when None)."""
    lens = [(b - a).length for a, b in zip(pts, pts[1:])]
    total = sum(lens) if length is None else length
    out = []
    for i in range(count):
        d = total * i / (count - 1)
        for (a, b), ln in zip(zip(pts, pts[1:]), lens):
            if d <= ln + 1e-12:
                out.append(a.lerp(b, d / ln if ln else 0.0))
                break
            d -= ln
        else:
            out.append(pts[-1].copy())
    return out


def clump_q(p, c, rx, rz):
    """Where ``p`` lies in a pad's ellipsoid: 0 at its centre, 1 on its skin."""
    d = p - c
    rzz = rz if d.z >= 0.0 else rz * CLUMP_BELOW
    return math.sqrt((d.x * d.x + d.y * d.y) / (rx * rx) + d.z * d.z / (rzz * rzz))


def carrier_path(pts, clump, short):
    """A carrier's centreline. It ends at its clump's centre, or with
    ``short`` it stops where it has only just entered the pad (0.95 of the
    way out from the centre) — same point count, so the face budget holds."""
    if not short:
        return pts
    c, rx, rz = clump
    lens = [(b - a).length for a, b in zip(pts, pts[1:])]
    run = 0.0
    stop = sum(lens)
    for (a, b), ln in zip(zip(pts, pts[1:]), lens):
        qa, qb = clump_q(a, c, rx, rz), clump_q(b, c, rx, rz)
        if qa >= SHORT_Q > qb:
            lo, hi = 0.0, 1.0
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                if clump_q(a.lerp(b, mid), c, rx, rz) >= SHORT_Q:
                    lo = mid
                else:
                    hi = mid
            stop = run + ln * lo
            break
        run += ln
    return resample(pts, len(pts), stop)


def add_clump(B, c, rx, rz, yaw, tone, key):
    """A needle clump: a brush of long, thin needle strands. A small dark
    core (a flattened cube-sphere, tipped a little off level) has every
    facet split in two, and each half is drawn out into one tapered strand.
    Each strand is aimed along the core's outward direction plus a hashed
    scatter, so the strands splay through the whole dome instead of lying
    in a plane, and it reaches the pad's ellipsoid. The core is small beside
    the strands' length, so every strand is a narrow sliver. One closed
    shell. Returns its id."""
    cid = B.next_clump
    B.next_clump += 1
    bm = B.bm
    ta = TAU * hash01(key, 9, 1)
    rot = Matrix.Rotation(math.radians(CLUMP_TILT) * hash01(key, 9, 2), 3,
                          Vector((math.cos(ta), math.sin(ta), 0.0))) @ Matrix.Rotation(yaw, 3, "Z")
    inv = rot.transposed()
    dirs, quads = cube_sphere(CLUMP_GRID)
    verts = []
    for i, d in enumerate(dirs):
        lump = 1.0 + CLUMP_LUMP * (hash01(key, i, 1) - 0.5)
        rzz = rz * (CLUMP_BELOW if d.z < 0.0 else 1.0)
        verts.append(bm.verts.new(c + rot @ Vector((d.x * rx, d.y * rx, d.z * rzz)) * (CLUMP_CORE * lump)))

    def reach(w):
        rzz = rz * (CLUMP_BELOW if w.z < 0.0 else 1.0)
        return 1.0 / math.sqrt((w.x * w.x + w.y * w.y) / (rx * rx) + w.z * w.z / (rzz * rzz))

    def strand(corners, k):
        ctr = sum((v.co for v in corners), Vector()) / 3.0
        u = (ctr - c).normalized()
        scatter = Vector((hash01(key, k, 3) - 0.5, hash01(key, k, 4) - 0.5,
                          hash01(key, k, 5) - 0.5)) * (2.0 * SPLAY)
        d = (u + scatter + UP * 0.12).normalized()
        if d.dot(u) < 0.35:
            d = (d + u).normalized()
        ln = reach(inv @ d) * (0.78 + 0.40 * hash01(key, k, 6)) - (ctr - c).length
        apex = bm.verts.new(ctr + d * max(ln, 0.08))
        apex[B.tip] = 1.0
        for e in range(3):
            f = B.face((corners[e], corners[(e + 1) % 3], apex), NEEDLE_IDX, tone, P_CLUMP, cid, False)
            for loop, uv in zip(f.loops, ((0.0, 0.0), (1.0, 0.0), (0.5, 1.0))):
                loop[B.nuv].uv = uv

    for k, q in enumerate(quads):
        o = k % 2
        qv = [verts[i] for i in q]
        strand((qv[o], qv[o + 1], qv[(o + 2) % 4]), 2 * k)
        strand((qv[o], qv[(o + 2) % 4], qv[(o + 3) % 4]), 2 * k + 1)
    return cid


def add_cone(B, top, axis, tone, spin, part):
    """A closed pine cone from ``top`` along ``axis``: stepped scale rings,
    each turned half a scale from the last."""
    bm = B.bm
    axis = axis.normalized()
    ref = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    u_ = axis.cross(ref).normalized()
    w_ = axis.cross(u_)
    prof = [(0.30, 0.00), (0.72, 0.14), (0.96, 0.30), (1.00, 0.48), (0.88, 0.66),
            (0.62, 0.82), (0.30, 0.95)]
    sides = 8
    rings = []
    for k, (rf, zf) in enumerate(prof):
        ring = []
        for j in range(sides):
            a = spin + TAU * j / sides + k * math.pi / sides
            rr = CONE_R * rf * (1.0 + 0.10 * ((j + k) % 2))
            ring.append(bm.verts.new(top + axis * (CONE_LEN * zf)
                                     + rr * (u_ * math.cos(a) + w_ * math.sin(a))))
        rings.append(ring)
    cap0 = bm.verts.new(top - axis * 0.004)
    tip = bm.verts.new(top + axis * CONE_LEN)
    verts = [v for r in rings for v in r] + [cap0, tip]
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(sides):
            m = (j + 1) % sides
            B.face((r0[j], r0[m], r1[m], r1[j]), CONE_IDX, tone, part, -1, False)
    for j in range(sides):
        m = (j + 1) % sides
        B.face((rings[0][m], rings[0][j], cap0), CONE_IDX, tone, part, -1, False)
        B.face((rings[-1][j], rings[-1][m], tip), CONE_IDX, tone, part, -1, False)
    return verts


def trunk_ring_z(zb, zs):
    zs_ = [zb, zs - 0.03, zs + 0.04, zs + 0.11, zs + 0.20, zs + 0.33, zs + 0.50, zs + 0.72, 1.05]
    z = 1.35
    while z < TRUNK_TOP - 0.15:
        zs_.append(round(z, 4))
        z += 0.30
    zs_ += [TRUNK_TOP - 0.08, TRUNK_TOP]
    return zs_


def trunk_foot():
    """(bottom z, soil z at the axis): the foot is bedded under the lowest
    soil round the flare."""
    zs = soil_height(0.0, 0.0)
    zb = ground_min(0.0, 0.0, TRUNK_R_BASE + FLARE_R + 0.03) - TRUNK_BED
    return zb, zs


def add_trunk(B, tone, sides, lean, collider=False):
    """One lathe from the buried foot to the top ring, closed flat at the
    foot and by a bud point at the top. Deep plate ridges on the lower bole
    fade into thin flaking bark above."""
    zb, zs = trunk_foot()
    rings = []
    for z in trunk_ring_z(zb, zs):
        c = axis_at(z, lean)
        rn = trunk_radius(z)
        flare = math.exp(-max(z - zs, 0.0) / FLARE_H)
        amp = RIDGE_AMP_TOP + (RIDGE_AMP - RIDGE_AMP_TOP) * (1.0 - smoothstep(z, *PLATE_Z))
        ring = []
        for j in range(sides):
            a = TAU * j / sides
            lobe = 0.5 + 0.5 * math.cos(FLARE_LOBES * (a - 0.35))
            r = rn + FLARE_R * flare * (0.30 + 0.70 * lobe * lobe)
            if not collider:
                # ridges: cos(RIDGES a) sampled on the lathe's own vertices,
                # so the high (40) and low (20) builds carry the same furrows
                r *= 1.0 + amp * math.cos(RIDGES * a + 0.4 * math.sin(2.1 * z))
            ring.append(B.bm.verts.new(c + Vector((r * math.cos(a), r * math.sin(a), 0.0))))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(sides):
            m = (j + 1) % sides
            B.face((r0[j], r0[m], r1[m], r1[j]), BARK_IDX, tone, P_TRUNK)
    B.face(tuple(reversed(rings[0])), BARK_IDX, tone, P_TRUNK)
    bud = B.bm.verts.new(axis_at(TRUNK_TOP, lean) + Vector((0.0, 0.0, 0.05)))
    for j in range(sides):
        m = (j + 1) % sides
        B.face((rings[-1][j], rings[-1][m], bud), BARK_IDX, tone, P_TRUNK)


def limb_path(br, base, steps=LIMB_STEPS):
    """Branch centreline from its base: out along its yaw, rising at its
    elevation, levelling off with droop and turning up again at the tip."""
    pts = []
    L = br["L"]
    for i in range(steps):
        s = i / (steps - 1)
        yaw = br["yaw"] + br["curl"] * s
        h = Vector((math.cos(yaw), math.sin(yaw), 0.0))
        run = s * L * math.cos(br["elev"])
        rise = s * L * math.sin(br["elev"]) - br["droop"] * L * s * s + br["tipup"] * L * s ** 5
        # a crooked limb, not a dowel: closed-form kinks that vanish at the base
        ph = br.get("tone", 0.0) * 6.283
        side = Vector((-h.y, h.x, 0.0)) * (0.045 * L * s * math.sin(7.0 * s + ph))
        rise += 0.030 * L * s * math.sin(9.0 * s + 2.0 * ph)
        pts.append(base + h * run + side + Vector((0.0, 0.0, rise)))
    return pts


def sample(pts, s):
    """Point at parameter s in [0, 1] along a polyline of equal steps."""
    n = len(pts) - 1
    x = min(max(s, 0.0), 1.0) * n
    i = min(int(x), n - 1)
    f = x - i
    return pts[i].lerp(pts[i + 1], f), (pts[i + 1] - pts[i]).normalized()


def settle(verts, sink):
    """Drop a lying body so its most-buried vertex is ``sink`` under the soil."""
    lift = min(v.co.z - soil_height(v.co.x, v.co.y) for v in verts)
    for v in verts:
        v.co.z -= lift + sink


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


def add_stone(B, x, y, r, h, yaw, jit, lift):
    """A weathered stone: a cube-sphere squashed to ``h``, cut by three
    cleavage planes and a flat bed, bedded in the soil."""
    dirs, quads = cube_sphere(4)
    cuts = []
    for k in range(3):
        a = yaw + TAU * (k + 0.3 * jit[k]) / 3.0
        nrm = Vector((math.cos(a), math.sin(a), 0.55 + 0.4 * jit[k + 3])).normalized()
        cuts.append((nrm, r * (0.62 + 0.12 * jit[k + 5])))
    verts = []
    for d in dirs:
        wob = 1.0 + 0.08 * math.sin(3.1 * d.x + 5.0 * jit[6]) * math.cos(2.7 * d.y + 3.0 * jit[7])
        p = Vector((d.x * r * wob, d.y * r * 0.82 * wob, d.z * h))
        for nrm, off in cuts:
            over = p.dot(nrm) - off
            if over > 0.0:
                p -= nrm * over
        p.z = max(p.z, -0.45 * h)
        p = Matrix.Rotation(yaw, 3, "Z") @ p
        verts.append(B.bm.verts.new(Vector((x, y, 0.0)) + p))
    for q in quads:
        B.face([verts[i] for i in q], STONE_IDX, jit[0], P_STONE)
    # bed the whole underside: the highest vertex of the flat bed sits
    # STONE_BED under the soil straight above it
    bed = [v for v in verts if v.co.z < min(w.co.z for w in verts) + 1e-6]
    over = max(v.co.z - soil_height(v.co.x, v.co.y) for v in bed)
    for v in verts:
        v.co.z -= over + STONE_BED - lift
    return verts


def add_soil(B):
    n = DISC_N
    grid = []
    for i in range(n + 1):
        col = []
        for k in range(n + 1):
            X, Y = squircle(i, k, n)
            wob = disc_wobble(math.atan2(Y, X))
            x = DISC_R * X * wob
            y = DISC_R * Y * wob
            on_rim = i in (0, n) or k in (0, n)
            z = 0.0 if on_rim else soil_height(x, y)
            col.append(B.bm.verts.new((x, y, z)))
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


def add_limb(B, br, z, lean, flags):
    """One live limb seated in the trunk, its side twigs,
    the needle clump at the end of each, and any cones hung under it."""
    c = axis_at(z, lean)
    h0 = Vector((math.cos(br["yaw"]), math.sin(br["yaw"]), 0.0))
    R = trunk_radius(z)
    base = c + h0 * (BRANCH_SEAT * R)
    pts = limb_path(br, base)
    L = br["L"]
    jit = br["jit"]
    rb = min(0.018 + 0.024 * L, 0.46 * R + 0.004)
    radii = [rb * (1.0 - 0.76 * i / (len(pts) - 1)) for i in range(len(pts))]
    short = flags["short_twigs"]
    lower = 1.0 + 0.22 * (1.0 - br["f"])   # the heavy lower limbs carry bigger pads

    def pad_tone(p, k):
        # outer and higher pads are lighter; the crown's heart is shaded
        out = min(1.0, hor(p - c).length / 3.4)
        high = min(1.0, max(0.0, (p.z - WHORL_Z0) / (TRUNK_TOP + 0.6 - WHORL_Z0)))
        return 0.15 + 0.45 * hash01(br["tone"] * 97.0, k, 11) + 0.25 * out + 0.15 * high

    def pad(p, scale, k, carrier_pts, carrier_radii, sides, tone):
        rx = CLUMP_RX * scale * lower * (0.78 + 0.44 * hash01(br["tone"] * 31.0, k, 2))
        rz = rx * (0.50 + 0.16 * hash01(br["tone"] * 53.0, k, 4))
        cid = add_clump(B, p, rx, rz, TAU * hash01(br["tone"] * 71.0, k, 6), pad_tone(p, k),
                        br["tone"] * 1000.0 + k)
        path = carrier_path(carrier_pts, (p, rx, rz), short)
        add_tube(B, path, carrier_radii, sides, BARK_IDX, tone, P_TWIG, cid, phase=br["yaw"])

    limb_pts = list(pts)
    if flags["float_branches"]:
        # the tube starts outside the bark; the path, and so the tip and
        # everything hung on it, is unchanged
        d0 = (pts[1] - pts[0]).normalized()
        hd = Vector((d0.x, d0.y, 0.0))
        k = (FLOAT_BRANCHES - BRANCH_SEAT) * R / max(hd.length, 1e-6)
        limb_pts = [pts[0] + d0 * k] + pts[1:]
    wood = 0.55 + 0.4 * br["tone"]
    # the limb's own clump, at its tip
    rx = CLUMP_RX * 1.12 * lower * (0.78 + 0.44 * hash01(br["tone"] * 31.0, 0, 2))
    rz = rx * (0.50 + 0.16 * hash01(br["tone"] * 53.0, 0, 4))
    cid = add_clump(B, pts[-1], rx, rz, TAU * hash01(br["tone"] * 71.0, 0, 6), pad_tone(pts[-1], 0),
                    br["tone"] * 1000.0)
    add_tube(B, carrier_path(limb_pts, (pts[-1], rx, rz), short), radii, LIMB_SIDES, BARK_IDX,
             wood, P_LIMB, cid, phase=br["yaw"])

    # side twigs, alternating along the outer limb, each ending in a pad
    n_side = br["n_side"]
    for k in range(n_side):
        s = 0.30 + 0.58 * (k + 0.5) / n_side + 0.05 * (jit[k] - 0.5)
        side = 1.0 if k % 2 == 0 else -1.0
        p, t = sample(pts, s)
        ang = side * (0.75 + 0.45 * jit[k + 5])
        d = Matrix.Rotation(ang, 3, "Z") @ Vector((t.x, t.y, 0.0)).normalized()
        d = (d + UP * (-0.22 + 0.60 * jit[k + 10])).normalized()
        tl = (0.40 + 0.45 * (1.0 - s)) * min(L, 3.4) / 2.6 + 0.22
        tpts = [p, p + d * (tl * 0.5) + UP * (0.03 * tl), p + d * tl + UP * (0.08 * tl)]
        tr = max(0.007, 0.45 * rb * (1.0 - 0.76 * s))
        pad(tpts[-1], 0.98, k + 1, tpts, [tr, tr * 0.75, tr * 0.5], TWIG_SIDES, wood)

    # cones hang under the limb, a cluster of two or three
    if br["cones"]:
        cj = br["cone_jit"]
        count = 2 + (1 if cj[0] > 0.5 else 0)
        for m in range(count):
            s = 0.52 + 0.06 * m + 0.03 * cj[m + 1]
            p, t = sample(pts, s)
            r_here = rb * (1.0 - 0.76 * s)
            outward = Vector((t.x, t.y, 0.0)).normalized()
            spin_side = Matrix.Rotation((m - 1) * 0.9, 3, "Z") @ outward
            axis = (-UP * 1.0 + spin_side * 0.45).normalized()
            top = p - UP * (r_here * 0.3)
            if flags["drop_cones"]:
                top = top - UP * DROP_CONES
            add_cone(B, top, axis, cj[m + 2], cj[m + 3] * 3.0, P_CONE)


def build_tree_mesh(name, plan, detail="low", **flags):
    lean = LEAN_BEND if flags["lean_crown"] else 0.0
    bm = bmesh.new()
    try:
        B = Builder(bm)
        sides = TRUNK_SIDES_HIGH if detail == "high" else TRUNK_SIDES

        add_soil(B)
        add_trunk(B, 0.1, sides, lean)

        # surface roots: from inside the flare, out and down into the soil
        for rt in plan["roots"]:
            h = Vector((math.cos(rt["yaw"]), math.sin(rt["yaw"]), 0.0))
            reach = rt["reach"]
            prof = [(0.06, 0.34, 0.120), (0.30, 0.12, 0.095), (0.55, 0.035, 0.066),
                    (0.80, -0.025, 0.042), (1.00, -0.070, 0.022)]
            pts = []
            for rf, dz, _r in prof:
                q = h * (reach * rf)
                pts.append(Vector((q.x, q.y, soil_height(q.x, q.y) + dz)))
            add_tube(B, pts, [r for _rf, _dz, r in prof], ROOT_SIDES, BARK_IDX, rt["tone"], P_ROOT)

        # dead stubs and long dead lower limbs on the bare bole
        dead_tone = 0.3
        for z, yaw in STUBS:
            c = axis_at(z, lean)
            h = Vector((math.cos(yaw), math.sin(yaw), -0.25)).normalized()
            base = c + Vector((h.x, h.y, 0.0)).normalized() * (BRANCH_SEAT * trunk_radius(z))
            ln = trunk_radius(z) * (1.0 - BRANCH_SEAT) + 0.07 + 0.03 * (yaw % 1.0)
            rb = 0.034
            pts = [base, base + h * (ln * 0.55), base + h * ln]
            jag = [(0.85, 0.012), (1.0, -0.006), (0.75, 0.020), (0.95, -0.010),
                   (0.80, 0.016), (1.0, 0.0)]
            add_tube(B, pts, [rb, rb * 0.92, rb * 0.82], 6, DEAD_IDX, dead_tone, P_STUB, jag=jag)
        for z, yaw, ln in DEAD_BRANCHES:
            c = axis_at(z, lean)
            br = {"yaw": yaw, "L": ln, "elev": math.radians(-10.0), "droop": 0.20,
                  "curl": 0.15, "tipup": 0.0}
            h = Vector((math.cos(yaw), math.sin(yaw), 0.0))
            base = c + h * (BRANCH_SEAT * trunk_radius(z))
            pts = limb_path(br, base, steps=5)
            add_tube(B, pts, [0.042, 0.033, 0.024, 0.015, 0.008], 5, DEAD_IDX, dead_tone + 0.2, P_DEAD)
            for s, side in ((0.40, 1.0), (0.62, -1.0), (0.80, 1.0)):
                p, t = sample(pts, s)
                d = Matrix.Rotation(side * 0.9, 3, "Z") @ t
                d.z -= 0.20
                d.normalize()
                add_tube(B, [p, p + d * 0.14, p + d * 0.27], [0.011, 0.007, 0.004], 4, DEAD_IDX,
                         dead_tone + 0.1, P_DEAD_TWIG)

        # the live crown
        for wi, wh in enumerate(plan["whorls"]):
            for br in wh["branches"]:
                z = br["z"] + (BUNCH_LIFT if flags["bunch_whorls"] and wi == BUNCH_WHORL else 0.0)
                add_limb(B, br, z, lean, flags)

        # the leader: a shoot from inside the trunk's top into the crown's
        # top pad
        ld = plan["leader"]
        c0 = axis_at(TRUNK_TOP - 0.30, lean)
        c1 = axis_at(TRUNK_TOP, lean)
        ctop = c1 + UP * LEADER_UP
        rx, rz = CLUMP_RX * 1.05, CLUMP_RX * 0.62
        cid = add_clump(B, ctop, rx, rz, ld["yaw"], 0.85, 5.0)
        lpts = carrier_path([c0, c1, c1.lerp(ctop, 0.5), ctop], (ctop, rx, rz), flags["short_twigs"])
        add_tube(B, lpts, [0.030, 0.026, 0.018, 0.010], TWIG_SIDES + 2, BARK_IDX, ld["tone"], P_TWIG, cid)

        # ground cover: fallen cones, mossy stones, dead sticks
        cov = plan["cover"]
        lift = FLOAT_LITTER if flags["float_litter"] else 0.0
        for (x, y, yaw), (tone, tilt) in zip(FALLEN_CONES, cov["cones"]):
            a = math.radians(yaw)
            axis = Vector((math.cos(a), math.sin(a), tilt * 0.3))
            top = Vector((x, y, soil_height(x, y) + 0.05)) - axis.normalized() * (CONE_LEN * 0.5)
            verts = add_cone(B, top, axis, tone, tone * 5.0, P_LCONE)
            settle(verts, REST_SINK - lift)
        for (x, y, r, h, yaw), jit in zip(STONES, cov["stones"]):
            add_stone(B, x, y, r, h, math.radians(yaw), jit, lift)
        for ((ax_, ay), (bx, by), r), tone in zip(STICKS, cov["sticks"]):
            a = Vector((ax_, ay, 0.0))
            b = Vector((bx, by, 0.0))
            pts = []
            for i in range(6):
                t = i / 5.0
                p = a.lerp(b, t)
                side = Vector((-(b - a).y, (b - a).x, 0.0)).normalized()
                p += side * (0.03 * math.sin(2.8 * t * math.pi + tone * 6.0))
                pts.append(Vector((p.x, p.y, soil_height(p.x, p.y) + r * 0.6)))
            verts = add_tube(B, pts, [r * (1.0 - 0.45 * i / 5.0) for i in range(6)], 5, DEAD_IDX,
                             0.4 + 0.4 * tone, P_STICK)
            settle(verts, REST_SINK - lift)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # Wood, soil and stone are smooth-shaded (their facets carry in the
        # silhouette); needle clumps and cones stay faceted, and every
        # material boundary is a hard edge.
        soft = {BARK_IDX, DEAD_IDX, SOIL_IDX, STONE_IDX}
        for face in bm.faces:
            if face.material_index in soft:
                face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            elif mats <= soft:
                edge.smooth = edge.calc_face_angle() < math.radians(50.0)
            else:
                edge.smooth = False
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


def build_collider_source(name):
    """The trunk alone, without ridges: players walk under the branches."""
    bm = bmesh.new()
    try:
        B = Builder(bm)
        add_trunk(B, 0.5, COLLIDER_SIDES, 0.0, collider=True)
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
    faces = [f for f in bm.faces if len(f.verts) > 4]
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


def surface(name, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = metallic
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


def tone_attr(nt):
    node = nt.nodes.new("ShaderNodeAttribute")
    node.attribute_type = "GEOMETRY"
    node.attribute_name = "Tone"
    return node.outputs["Fac"]


def normal_z(nt):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
    return sep.outputs["Z"]


def add_bump(nt, bsdf, height, strength, distance):
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def bark_material():
    mat, nt, bsdf, coord = surface("PineBark")
    # Scots pine: thick grey-brown plates on the lower bole, thin fox-red
    # flaking bark above. Plates are noise squeezed round the girth and
    # stretched up it, so the fissures run vertically.
    plates = noise(nt, mapping(nt, coord, scale=(9.0, 9.0, 2.2)), 3.0, 8.0, 0.62)
    flakes = noise(nt, mapping(nt, coord, scale=(26.0, 26.0, 9.0)), 1.0, 5.0, 0.55)
    low = ramp(nt, plates, ((0.36, (0.026, 0.020, 0.016)), (0.50, (0.075, 0.056, 0.042)),
                            (0.66, (0.135, 0.108, 0.084)), (0.82, (0.185, 0.155, 0.124))))
    high = ramp(nt, flakes, ((0.30, (0.200, 0.080, 0.036)), (0.55, (0.370, 0.160, 0.068)),
                             (0.80, (0.480, 0.250, 0.125))))
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    zmix = math_node(nt, "ADD", sep.outputs["Z"], remap(nt, plates, 0.3, 0.7, -0.4, 0.4))
    fac = remap(nt, zmix, PLATE_Z[0], PLATE_Z[1] + 0.4, 0.0, 1.0)
    col = mix_color(nt, low, high, fac)
    tone = tone_attr(nt)
    col = mix_color(nt, col, (0.05, 0.035, 0.025), remap(nt, tone, 0.0, 1.0, 0.0, 0.40))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, plates, 0.35, 0.8, 0.92, 0.72), bsdf.inputs["Roughness"])
    add_bump(nt, bsdf, plates, 0.8, 0.02)
    return mat


def needle_material():
    mat, nt, bsdf, coord = surface("PineNeedles")
    # Blue-green Scots pine needles: each pad takes its own tone (lighter
    # outside and high, shaded in the crown's heart), a fine speckle breaks
    # the facets into needles, and upward facets carry the glaucous bloom.
    tone = tone_attr(nt)
    base = ramp(nt, tone, ((0.0, (0.014, 0.038, 0.027)), (0.45, (0.032, 0.080, 0.050)),
                           (1.0, (0.068, 0.130, 0.078))))
    speck = noise(nt, coord, 55.0, 4.0, 0.7)
    col = mix_color(nt, base, (0.010, 0.019, 0.016), remap(nt, speck, 0.35, 0.7, 0.60, 0.0))
    col = mix_color(nt, col, (0.070, 0.098, 0.084), remap(nt, normal_z(nt), 0.35, 1.0, 0.0, 0.30))
    # fine needle lines on every tuft facet, converging on its point
    nuv = nt.nodes.new("ShaderNodeUVMap")
    nuv.uv_map = "NeedleUV"
    nsep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(nuv.outputs["UV"], nsep.inputs["Vector"])
    lines = math_node(nt, "SINE", math_node(nt, "MULTIPLY", nsep.outputs["X"], TAU * NEEDLE_LINES), 0.0)
    col = mix_color(nt, col, (0.006, 0.011, 0.009), remap(nt, lines, 0.2, 1.0, 0.0, 0.55))
    # each tuft runs from a shaded base to a lighter, greyer point
    tip = nt.nodes.new("ShaderNodeAttribute")
    tip.attribute_type = "GEOMETRY"
    tip.attribute_name = "Tip"
    col = mix_color(nt, col, (0.006, 0.012, 0.010), remap(nt, tip.outputs["Fac"], 0.0, 0.45, 0.30, 0.0))
    col = mix_color(nt, col, (0.100, 0.145, 0.105), remap(nt, tip.outputs["Fac"], 0.55, 1.0, 0.0, 0.45))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, speck, 0.3, 0.7, 0.90, 0.72), bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    add_bump(nt, bsdf, speck, 0.45, 0.02)
    return mat


def cone_material():
    mat, nt, bsdf, coord = surface("PineCone")
    tone = tone_attr(nt)
    blot = noise(nt, coord, 60.0, 4.0, 0.6)
    base = ramp(nt, blot, ((0.35, (0.100, 0.060, 0.034)), (0.65, (0.240, 0.150, 0.082))))
    col = mix_color(nt, base, (0.15, 0.115, 0.085), remap(nt, tone, 0.0, 1.0, 0.0, 0.35))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.72
    return mat


def deadwood_material():
    mat, nt, bsdf, coord = surface("PineDeadwood")
    # Weathered, barkless: silver-grey with dark checks.
    streak = noise(nt, mapping(nt, coord, scale=(30.0, 30.0, 6.0)), 2.0, 6.0, 0.6)
    col = ramp(nt, streak, ((0.35, (0.065, 0.058, 0.052)), (0.55, (0.185, 0.172, 0.152)),
                            (0.80, (0.290, 0.272, 0.244))))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    return mat


def soil_material():
    mat, nt, bsdf, coord = surface("NeedleLitter")
    # Dark humus under a mat of fallen needles: two crossing layers of thin
    # streaks, rust-brown fresh and grey-brown old.
    dirt = noise(nt, coord, 6.0, 6.0, 0.6)
    col = ramp(nt, dirt, ((0.30, (0.018, 0.013, 0.010)), (0.70, (0.045, 0.032, 0.022))))
    for k, (rot, tint) in enumerate(((0.5, (0.150, 0.075, 0.032)), (-1.1, (0.105, 0.070, 0.045)),
                                     (2.2, (0.130, 0.068, 0.030)))):
        streak = noise(nt, mapping(nt, coord, scale=(110.0, 6.0, 6.0), rot=(0.0, 0.0, rot)),
                       2.0 + k, 2.0, 0.5)
        col = mix_color(nt, col, tint, remap(nt, streak, 0.60, 0.68, 0.0, 0.85))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    add_bump(nt, bsdf, dirt, 0.4, 0.02)
    return mat


def stone_material():
    mat, nt, bsdf, coord = surface("MossyStone")
    # Grey granite, moss cushions on its upward faces.
    grain = noise(nt, coord, 14.0, 6.0, 0.6)
    rock = ramp(nt, grain, ((0.30, (0.060, 0.058, 0.055)), (0.55, (0.140, 0.136, 0.126)),
                            (0.80, (0.210, 0.204, 0.190))))
    patch = noise(nt, coord, 5.0, 4.0, 0.6)
    moss = ramp(nt, patch, ((0.35, (0.022, 0.040, 0.014)), (0.70, (0.050, 0.075, 0.022))))
    mask = math_node(nt, "MULTIPLY", remap(nt, normal_z(nt), 0.30, 0.75, 0.0, 1.0),
                     remap(nt, patch, 0.38, 0.55, 0.2, 1.0))
    col = mix_color(nt, rock, moss, mask)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.86
    add_bump(nt, bsdf, grain, 0.5, 0.02)
    return mat


def tree_materials():
    """(bark, needles, cone, deadwood, soil, stone): shared by the check and the render."""
    return (bark_material(), needle_material(), cone_material(), deadwood_material(),
            soil_material(), stone_material())


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
    def __init__(self, me, idx, verts, polys, part_of, carry_of):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.centre = (self.lo + self.hi) * 0.5
        mats, parts = {}, {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
            parts[part_of[p.index]] = parts.get(part_of[p.index], 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        self.part = max(parts, key=parts.get) if parts else 0
        self.carry = carry_of[polys[0].index] if polys else -1
        remap_ = {vi: n for n, vi in enumerate(verts)}
        self.tree = BVHTree.FromPolygons(
            [tuple(p) for p in pts], [[remap_[v] for v in p.vertices] for p in polys])
        self.polys = polys


class TrunkAxis:
    """Trunk ring centroids read off the mesh: every lathe ring shares one z."""

    def __init__(self, trunk):
        rings = {}
        for p in trunk.pts:
            rings.setdefault(round(p.z, 5), []).append(p)
        # a ring has the lathe's full side count; the bud apex is a single vertex
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
    polys = shell_polys(me, groups)
    part_of = face_ints(me, "Part")
    carry_of = face_ints(me, "Carry")
    parts = [Shell(me, i, g, polys[i], part_of, carry_of) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups, "part_of": part_of, "carry_of": carry_of}

    def of(*kinds):
        return [s for s in parts if s.part in kinds]

    out["trunk"] = of(P_TRUNK)
    out["roots"] = of(P_ROOT)
    out["limbs"] = of(P_LIMB)
    out["twigs"] = of(P_TWIG)
    out["dead_seated"] = of(P_STUB, P_DEAD)
    out["clumps"] = of(P_CLUMP)
    out["cones"] = of(P_CONE)
    out["soil"] = of(P_SOIL)
    out["cover"] = of(*COVER_PARTS)
    if len(out["trunk"]) == 1:
        out["axis"] = TrunkAxis(out["trunk"][0])
    return out


def member_base(s, ax, n):
    """Centroid of the ``n`` vertices nearest the trunk axis: the base ring."""
    ranked = sorted(s.pts, key=lambda p: (p - ax.centre(p.z)).to_2d().length)
    ring = ranked[:n]
    return sum(ring, Vector()) / len(ring)


def seat_audit(cls):
    """Per limb and seated dead member: base-centre radial distance over the
    trunk surface radius on the same bearing (raycast from the axis)."""
    ax = cls["axis"]
    trunk = cls["trunk"][0]
    ratios = [_seat_ratio(s, LIMB_SIDES, ax, trunk) for s in cls["limbs"]]
    for s in cls["dead_seated"]:
        # stubs are 6-sided, dead limbs 5-sided
        ratios.append(_seat_ratio(s, 6 if s.part == P_STUB else 5, ax, trunk))
    return ratios


def _seat_ratio(s, n, ax, trunk):
    b = member_base(s, ax, n)
    c = ax.centre(b.z)
    d = (b - c).to_2d()
    dist = d.length
    if dist < 1e-6:
        return 0.0
    direction = Vector((d.x, d.y, 0.0)).normalized()
    hit, _n, _i, surf = trunk.tree.ray_cast(Vector((c.x, c.y, b.z)), direction, 2.0)
    if hit is None:
        return 9.0
    return dist / surf


def whorl_audit(cls):
    """Cluster limb base heights into whorls; gaps, spreads, counts."""
    ax = cls["axis"]
    zs = sorted(member_base(s, ax, LIMB_SIDES).z for s in cls["limbs"])
    tiers = []
    for z in zs:
        if tiers and z - tiers[-1][-1] < WHORL_SPLIT:
            tiers[-1].append(z)
        else:
            tiers.append([z])
    heights = [sum(t) / len(t) for t in tiers]
    gaps = [b - a for a, b in zip(heights, heights[1:])]
    spreads = [max(t) - min(t) for t in tiers]
    counts = [len(t) for t in tiers]
    return heights, gaps, spreads, counts


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 12.0)), Vector((0.0, 0.0, -1.0)), 30.0)
    return None if loc is None else loc.z


def plumb_audit(me, cls):
    """Trunk lean (line fit to ring centroids), needle-mass balance over the
    base, and breast-height diameter above the soil."""
    ax = cls["axis"]
    rings = [(z, c) for z, c, _r in ax.rings if 0.8 <= z <= TRUNK_TOP - 1.0]
    n = len(rings)
    mz = sum(z for z, _c in rings) / n
    mx = sum(c.x for _z, c in rings) / n
    my = sum(c.y for _z, c in rings) / n
    szz = sum((z - mz) ** 2 for z, _c in rings)
    sx = sum((z - mz) * (c.x - mx) for z, c in rings) / szz
    sy = sum((z - mz) * (c.y - my) for z, c in rings) / szz
    lean = math.degrees(math.atan(math.hypot(sx, sy)))
    base = ax.centre(0.5)
    area = 0.0
    acc = Vector((0.0, 0.0, 0.0))
    for p in me.polygons:
        if p.material_index == NEEDLE_IDX:
            a = p.area
            area += a
            acc += p.center * a
    centroid = acc / area if area else Vector()
    balance = (centroid - base).to_2d().length
    zsoil = ray_down(cls["soil"][0].tree, base.x, base.y) or 0.0
    dbh_ring = min(ax.rings, key=lambda r: abs(r[0] - (zsoil + DBH_Z)))
    dbh = 2.0 * dbh_ring[2]
    return lean, balance, dbh, centroid.z


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


def clump_audit(me, cls):
    """Per needle clump: how deep its own carrier's deepest vertex lies
    inside it (the carrier is the limb, twig or leader tagged with the
    clump's id)."""
    part_of, carry_of = cls["part_of"], cls["carry_of"]
    by_cid = {}
    for p in me.polygons:
        if part_of[p.index] in CARRIER_PARTS and carry_of[p.index] >= 0:
            by_cid.setdefault(carry_of[p.index], set()).update(p.vertices)
    out = []
    for s in cls["clumps"]:
        best = -9.0
        for vi in by_cid.get(s.carry, ()):
            q = me.vertices[vi].co
            if not (s.lo.x <= q.x <= s.hi.x and s.lo.y <= q.y <= s.hi.y and s.lo.z <= q.z <= s.hi.z):
                continue
            best = max(best, signed_depth(s.tree, q))
        out.append(best)
    return out


def ground_audit(cls):
    """Each ground-cover piece's deepest vertex under the soil straight above it, each
    root's deepest vertex under the soil, and the trunk foot's depth."""
    soil = cls["soil"][0]
    rests = {}
    for s in cls["cover"]:
        deep = -9.0
        for p in s.pts:
            g = ray_down(soil.tree, p.x, p.y)
            if g is not None:
                deep = max(deep, g - p.z)
        rests.setdefault(s.part, []).append(deep)
    roots = []
    for s in cls["roots"]:
        deep = -9.0
        for p in s.pts:
            g = ray_down(soil.tree, p.x, p.y)
            if g is not None:
                deep = max(deep, g - p.z)
        roots.append(deep)
    trunk = cls["trunk"][0]
    low = min(trunk.pts, key=lambda p: p.z)
    g = ray_down(soil.tree, low.x, low.y)
    foot = -9.0 if g is None else g - low.z
    return rests, roots, foot


def connected_components(cls):
    parts = [s for s in cls["all"] if s.polys]
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
    sizes = {}
    for i in range(n):
        sizes[find(i)] = sizes.get(find(i), 0) + 1
    return len(sizes), sorted(sizes.values())


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
    img = bpy.data.images.new("PineNrm", size, size, alpha=True, float_buffer=False)
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
    low = build_tree_mesh("PineLow", plan, "low", **flags)
    high = build_tree_mesh("PineHigh", plan, "high", **flags)
    mats = tree_materials()
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
        return (fail("tree mesh did not build", 3),) + none2

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
    expected_limbs = sum(len(w["branches"]) for w in plan["whorls"])
    expected_dead = len(STUBS) + len(DEAD_BRANCHES)
    expected_pads = expected_clumps(plan)
    expected_cover = len(FALLEN_CONES) + len(STONES) + len(STICKS)
    ratios = seat_audit(cls)
    heights, gaps, spreads, counts = whorl_audit(cls)
    lean, balance, dbh, mass_z = plumb_audit(low.data, cls)
    bites = clump_audit(low.data, cls)
    rests, root_beds, foot = ground_audit(cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, bark)
    if img is None:
        return (fail("tree has no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "PineLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "PineLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("PineColSrc")
    collider = convex_hull_collider(collider_src, "PineCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_pine_tree_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    rest_lo = {k: min(v) for k, v in rests.items()}
    rest_hi = {k: max(v) for k, v in rests.items()}
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
    print(f"measured shells={len(cls['all'])} limbs={len(cls['limbs'])} "
          f"twigs={len(cls['twigs'])} clumps={len(cls['clumps'])} "
          f"cones={len(cls['cones'])} roots={len(cls['roots'])} "
          f"dead_seated={len(cls['dead_seated'])} cover={len(cls['cover'])}")
    print(f"measured seat_ratio min={min(ratios):.4f} max={max(ratios):.4f} n={len(ratios)}")
    print(f"measured whorls={len(heights)} counts={counts} "
          f"heights={[round(h, 3) for h in heights]}")
    print(f"measured whorl_gaps min={min(gaps, default=0):.4f} max={max(gaps, default=0):.4f} "
          f"spread_max={max(spreads, default=0):.4f}")
    print(f"measured lean_deg={lean:.3f} balance={balance:.4f} mass_z={mass_z:.3f} "
          f"dbh={dbh:.4f}")
    print(f"measured clump_bite min={min(bites):.4f} max={max(bites):.4f} n={len(bites)}")
    print(f"measured ground rest_min={ {k: round(v, 4) for k, v in rest_lo.items()} } "
          f"rest_max={ {k: round(v, 4) for k, v in rest_hi.items()} } "
          f"root_bed_min={min(root_beds):.4f} foot={foot:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-3:]} n={len(comp_sizes)}")

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
    if (len(cls["limbs"]) != expected_limbs or len(cls["dead_seated"]) != expected_dead
            or min(ratios) < SEAT_RATIO_MIN or max(ratios) > SEAT_RATIO_MAX):
        return (fail(f"branch seat: limbs {len(cls['limbs'])}/{expected_limbs} dead "
                     f"{len(cls['dead_seated'])}/{expected_dead} base/radius "
                     f"{min(ratios):.4f}..{max(ratios):.4f} not in "
                     f"[{SEAT_RATIO_MIN}, {SEAT_RATIO_MAX}]", 17),) + none2
    if (lean > LEAN_MAX_DEG or balance > BALANCE_MAX or abs(dbh - DBH) > DBH_TOL):
        return (fail(f"plumb/balance: lean {lean:.3f} deg (max {LEAN_MAX_DEG}), balance "
                     f"{balance:.4f} m (max {BALANCE_MAX}), dbh {dbh:.4f} "
                     f"(want {DBH} +/- {DBH_TOL})", 19),) + none2
    if (len(heights) != WHORLS or min(counts) < BRANCHES[0] or max(counts) > BRANCHES[1]
            or max(spreads) > WHORL_SPREAD_MAX or min(gaps) < WHORL_GAP_MIN
            or max(gaps) > WHORL_GAP_MAX):
        return (fail(f"whorl tiers: {len(heights)} whorls (want {WHORLS}), counts {counts}, "
                     f"gaps {min(gaps, default=0):.4f}..{max(gaps, default=0):.4f} (band "
                     f"[{WHORL_GAP_MIN}, {WHORL_GAP_MAX}]), spread "
                     f"{max(spreads, default=0):.4f}", 20),) + none2
    if len(bites) != expected_pads or min(bites) < CLUMP_BITE_MIN:
        return (fail(f"clump seat: {len(bites)}/{expected_pads} clumps, shallowest carrier "
                     f"{min(bites):.4f} m inside its clump (min {CLUMP_BITE_MIN})", 22),) + none2
    bands = {P_LCONE: REST_BAND, P_STICK: REST_BAND, P_STONE: STONE_BAND}
    bad = [(k, round(v, 4)) for k, vs in rests.items() for v in vs
           if not (bands[k][0] <= v <= bands[k][1])]
    if (sum(len(v) for v in rests.values()) != expected_cover or bad
            or min(root_beds) < ROOT_BED_MIN or foot < TRUNK_BED_MIN):
        return (fail(f"ground bedding: {sum(len(v) for v in rests.values())}/{expected_cover} "
                     f"cover pieces, out of band {bad}, shallowest root {min(root_beds):.4f} "
                     f"(min {ROOT_BED_MIN}), trunk foot {foot:.4f} (min {TRUNK_BED_MIN})", 23),) + none2
    if ncomp != 1:
        return (fail(f"tree splits into {ncomp} components", 21),) + none2
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
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.052, 0.054, 0.062, 1.0)
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

    # Key, fill, rim and the warm wedge, scaled for a 7 m tree. The key's
    # spread keeps it on the crown instead of flooding the near floor.
    light("Key", (-11.0, -15.0, 9.0), 5200.0, 5.0, (1.0, 0.95, 0.88), spread=28.0)
    light("Fill", (15.0, -10.0, 1.0), 520.0, 18.0, (0.72, 0.82, 1.0))
    light("Rim", (-4.0, 6.0, 5.5), 900.0, 5.0, (0.62, 0.78, 1.0))
    light("Wedge", (8.0, 2.5, 3.5), 2250.0, 7.0, (1.0, 0.65, 0.34),
          target=(4.5, WALL_Y - 4.0, 0.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.45, -0.89, 0.0)).normalized()
    cam.location = centre + view * 24.5 + Vector((0.0, 0.0, -1.6))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the needles.
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


FLAGS = ("float_branches", "lean_crown", "bunch_whorls", "short_twigs", "float_litter", "drop_cones")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--float-branches", action="store_true")
    p.add_argument("--lean-crown", action="store_true")
    p.add_argument("--bunch-whorls", action="store_true")
    p.add_argument("--short-twigs", action="store_true")
    p.add_argument("--float-litter", action="store_true")
    p.add_argument("--drop-cones", action="store_true")
    args = p.parse_args(argv)

    code, low, _bark = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        **{k: getattr(args, k) for k in FLAGS},
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("pine-tree OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
