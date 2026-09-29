"""Game-ready fern and mossy rock — a showcase piece, not an example.

Asserts budget conformance of a procedural shaded woodland corner after
composing shipped pipeline pieces: bmesh construction, UVs, ten
materials, high-to-low normal bake, LOD chain, convex boulder collider,
Unity glTF export.

A large boulder, cleaved into broken faces with weathered bevels and split
by a deep crack, is sunk into a soil bank that rises toward the back. A
thick moss cushion lies over its top and drapes down its shaded front
flank, a conforming shell whose lumpy edge tucks into the stone; smaller
cushions sit on the far block and low on the flank. At its downhill foot a
male fern's shuttlecock crown rises from a scaly rootstock bedded in the
soil: ten arching bipinnate fronds, each a tapering rachis carrying
alternate pinnae cut into pinnules, with three fiddleheads unrolling at the
centre and old stipe bases round the rootstock. A smaller fern grows out of
the crack. Beech litter, pebbles, a fallen twig and wood sorrel lie at the
foot.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-fronds`` / ``--lift-crown``
every frond rooted in its crown and the crown bedded in the soil,
``--float-moss`` the moss cushion's thickness band on the rock,
``--perch-rock`` the boulder sealed all round, ``--sunny-moss`` moss facing
up or into the shade, ``--perch-crack-fern`` the crack fern rooted in the
crack, ``--flat-taper`` / ``--opposite-pinnae`` pinnae alternating and
tapering along the rachis, ``--open-crozier`` every fiddlehead a real
spiral, ``--float-cover`` the ground cover bedded in the soil.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python fern_mossy_rock.py --
    blender --background --python fern_mossy_rock.py -- --skip-decimate
    blender --background --python fern_mossy_rock.py -- --output fern.png
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

SEED = 3719
TAU = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))
# The bank faces away from the light: its downhill front (-Y) is the shaded
# side, where the moss drapes and the ferns grow.
SHADE = Vector((0.0, -1.0, 0.0))

# --- Ground ------------------------------------------------------------------
SOIL_A = (1.12, 1.03)    # soil disc half-axes before the wobble, m
SOIL_C = (0.10, 0.02)    # its centre, drawn toward the fern so no bare soil is spare
SOIL_N = 34
SOIL_H0 = 0.20
SLOPE = 0.19             # the bank rises toward the back (+Y), m per m
SOIL_EDGE = 0.16         # the rim rolls down over this fraction of the radius
SOIL_FLOOR = 0.02

# --- Boulder -----------------------------------------------------------------
ROCK_XY = (-0.06, 0.24)
ROCK_YAW = 12.0
ROCK_AXES = (0.76, 0.60, 0.56)
ROCK_O = (0.18, -0.04, 0.02)   # the radial field's origin; the crack plane passes through it
# cleavage planes (normal, offset as a fraction of the ellipsoid's support,
# weathering bevel): a tilted top, a broad front face, the flanks
ROCK_PLANES = (((0.10, -0.22, 1.0), 0.52, 0.110), ((0.06, -1.0, 0.18), 0.64, 0.070),
               ((-1.0, 0.10, 0.20), 0.64, 0.045), ((0.45, 0.90, 0.20), 0.66, 0.040),
               ((0.92, -0.28, 0.38), 0.66, 0.035), ((-0.55, -0.62, 0.52), 0.64, 0.040),
               ((-0.40, 0.75, 0.55), 0.66, 0.040), ((0.30, -0.70, 0.75), 0.66, 0.035),
               ((-0.75, -0.15, -0.35), 0.70, 0.045), ((0.20, -0.80, -0.30), 0.72, 0.045))
ROCK_CHIPS = 7
ROCK_AMP = 0.034
ROCK_N = 28
ROCK_N_HIGH = 40
ROCK_FOOT = 0.040        # the buried underside is cut flat this far over Z = 0
COLLIDER_N = 4
# the crack: a V cut along a plane through the origin, ``CRACK_W`` half-wide
# at the surface and ``CRACK_D`` deep, closing low on the flanks
CRACK_N = (0.95, 0.24, 0.10)
CRACK_W = 0.062
CRACK_D = 0.22
CRACK_LOW = -0.32
CRACK_A = 0.45           # directions this near the crack plane (rad) are drawn in toward it
CRACK_Q = 2.2
EMBED = 0.040            # every sector's most-buried flank vertex this far under the soil
FLANK_R = 0.90           # flank: at least this fraction of the sector's plan reach
SECTORS = 8

# --- Moss --------------------------------------------------------------------
# (centre direction from the rock frame's origin, radius m, stretch down
# the drape, thickness m, rings, segments, drape direction, reach toward
# the far flank as a fraction). The main cushion sits on the larger
# block's crown and drapes down its shaded front.
MOSS = (((-0.74, -0.30, 0.60), 0.40, 1.75, 0.058, 16, 72, (0.10, -1.0, -0.55), 0.70),
        ((0.46, 0.10, 0.88), 0.15, 1.15, 0.034, 7, 32, (0.0, -1.0, -0.5), 1.0),
        ((-0.52, -0.80, 0.12), 0.13, 1.30, 0.032, 7, 30, (0.0, -1.0, -0.5), 1.0),
        ((0.44, -0.80, 0.30), 0.12, 1.25, 0.030, 7, 30, (0.0, -1.0, -0.5), 1.0))
MOSS_TUCK = 0.005        # the cushion's rim this far inside the stone
MOSS_BITE = 0.006
MOSS_CLEAR = 0.020       # rim kept this far over the soil
MOSS_CRACK_CLEAR = 0.070  # and this far back from the crack's lip
SUNNY_D = (0.32, 0.92, 0.22)   # --sunny-moss: the main cushion's centre on the sunny back face

# --- Fern crown --------------------------------------------------------------
CROWN_XY = (0.44, -0.40)
KNOB_R = (0.080, 0.074, 0.056)   # rootstock half-axes
KNOB_SINK = 0.034        # its centre this far under the soil
FRONDS = 11
FROND_L = (0.96, 1.14)
STIPE_F = 0.22           # the stipe's share of the frond
FROND_E0 = (54.0, 77.0)  # elevation where it leaves the crown, deg
FROND_ETIP = (-40.0, -10.0)
FROND_RINGS = 22
FROND_SIDES = 5
FROND_SIDES_HIGH = 8
R_STIPE = 0.0046
R_RACHIS_TIP = 0.0014
PINNAE = 15              # per side on a crown frond
PINNA_LMAX = (0.118, 0.136)
PINNULES_MAX = 5
# Neighbouring pinnae are turned about their own axes in a three-step
# cycle: along a rachis they are otherwise translated copies in one blade
# plane, and their faces land on shared planes.
PINNA_TWIST = 0.20
# ...and each pinna turns further, in steps, until its plane clears the
# plane of every pinna whose faces can come within the coplanar range.
PINNA_SEP = math.radians(8.0)
PINNA_STEP = 0.04
CROSIERS = 3
CROSIER_TURNS = 1.65
CROSIER_R0 = 0.034
CROSIER_B = 0.135        # log-spiral rate: r = R0 exp(-b phi)
CROSIER_RINGS = (6, 36)  # stipe, coil
STUBS = 7

# --- Crack fern --------------------------------------------------------------
CRACK_FRONDS = 4
CRACK_FROND_L = (0.44, 0.56)
CRACK_PINNAE = 13
CRACK_PINNULES_MAX = 4
CKNOB_R = 0.030
CKNOB_DEPTH = 0.52       # its centre this fraction of the crack's depth down

# --- Ground cover ------------------------------------------------------------
LITTER = 56
PEBBLES = 16
SORREL = 8
TWIGS = 1
LEAFLET_SEP = math.radians(14.0)  # sorrel leaflets' planes kept this far apart
REST_SINK = 0.004        # a lying body's most-buried vertex this far under the soil
SORREL_BURY = 0.030

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (2.2896, 2.2209, 0.8601)
BASE_TRIS_MIN = 76800
BASE_TRIS_MAX = 77600
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 10
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 200
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# face floors: rock, moss, frond, stipe, crozier, rootstock, soil, litter, twig, sorrel
FACE_FLOORS = (9800, 2200, 48400, 1480, 750, 290, 2350, 1940, 64, 2230)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Rooted: every stipe's base cap inside its rootstock, every pinna's base
# inside its rachis, the crown's rootstock sealed in the soil.
STIPE_BITE_MIN = 0.004
PINNA_BITE_MIN = 0.0004
KNOB_SEAL_EPS = 0.010
FLOAT_FRONDS = 0.060     # --float-fronds starts each stipe this far out along its path
LIFT_CROWN = 0.050       # --lift-crown raises the rootstock alone
# Moss seat: the cushion's thickness over the stone along the stone's normal
MOSS_BAND = (0.006, 0.080)
MOSS_IN_MIN = 0.001      # rim and underside at least this far inside the stone
FLOAT_MOSS = 0.040
# Sealed: every sector's most-buried flank vertex under the soil
SEAL_EPS = 0.020
# Moss facing: area share of cushion faces facing up or into the shade
UP_MIN = 0.55
SHADE_MIN = 0.45
FACING_MIN = 0.85
# Crack fern: its rootstock bites the crack walls and sits in the cleft
CKNOB_BITE_MIN = 0.004
CRACK_REACH = 0.060
CRACK_SHIFT = 0.100      # --perch-crack-fern slides the crack fern sideways out of the cleft
# Pinnae: alternate along the rachis, longest low on the blade, tapering to the tip
ALT_BAND = (0.25, 0.75)  # gap to the next pinna over the same-side spacing
PEAK_BAND = (0.10, 0.60)
TIP_RATIO_MAX = 0.40
BASE_RATIO_MAX = 0.88
# Fiddleheads: turning and curvature rising toward the centre
SPIRAL_TURNS_MIN = 1.20
SPIRAL_RATIO_MIN = 1.80
# Ground cover: most-buried vertex under the soil straight above it
REST_BAND = (0.003, 0.030)
SORREL_BAND = (0.015, 0.060)
FLOAT_COVER = 0.050
# Hero yaw about Z only (level on the stage).
HERO_YAW_DEG = -50.0
WALL_Y = 4.2

ROCK_IDX = 0
MOSS_IDX = 1
FROND_IDX = 2
STIPE_IDX = 3
CROZIER_IDX = 4
ROOT_IDX = 5
SOIL_IDX = 6
LITTER_IDX = 7
TWIG_IDX = 8
SORREL_IDX = 9
MAT_LABELS = ("rock", "moss", "frond", "stipe", "crozier", "rootstock", "soil", "litter",
              "twig", "sorrel")

# part tags, one per face, so the audits can name a shell's role
P_SOIL, P_ROCK, P_MOSS, P_KNOB, P_STIPE, P_PINNA, P_CROSIER, P_STUB = 1, 2, 3, 4, 5, 6, 7, 8
P_CKNOB, P_LITTER, P_PEBBLE, P_TWIG, P_SORREL, P_LEAFLET = 9, 10, 11, 12, 13, 14
COVER_PARTS = (P_LITTER, P_PEBBLE, P_TWIG, P_SORREL)
KNOB_ID = 100
CKNOB_ID = 200


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
    """Polynomial soft minimum: the weathering bevel where two cuts meet."""
    if k <= 0.0:
        return min(a, b)
    h = max(k - abs(a - b), 0.0) / k
    return min(a, b) - h * h * k * 0.25


def hash01(a, b, c):
    """A closed-form draw in [0, 1) from three indices: per-part variety
    that no flag can shift."""
    x = math.sin(a * 12.9898 + b * 78.233 + c * 37.719 + SEED * 0.0137) * 43758.5453
    return x - math.floor(x)


def perp_basis(d):
    ref = UP if abs(d.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = d.cross(ref).normalized()
    return e1, d.cross(e1).normalized()


def rotz(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def rotate_about(v, axis, ang):
    return Matrix.Rotation(ang, 3, axis) @ v


# --------------------------------------------------------------------------
# The ground as a function of plan position
# --------------------------------------------------------------------------

def disc_wobble(th):
    return (1.0 + 0.05 * math.sin(3.0 * th + 0.7) + 0.03 * math.sin(5.0 * th + 2.1)
            + 0.02 * math.sin(8.0 * th + 0.3))


def soil_height(x, y):
    """A woodland bank rising toward the back, with low swells."""
    h = (SOIL_H0 + SLOPE * y + 0.018 * math.sin(2.1 * x + 0.4) * math.cos(1.7 * y + 0.8)
         + 0.008 * math.sin(4.3 * x - 3.1 * y + 1.1) + 0.004 * math.sin(8.3 * x + 6.9 * y))
    return max(SOIL_FLOOR, h)


def disc_frac(x, y):
    """How far out (x, y) lies on the soil disc, 1 at the rim."""
    x, y = x - SOIL_C[0], y - SOIL_C[1]
    th = math.atan2(y / SOIL_A[1], x / SOIL_A[0])
    return math.hypot(x / SOIL_A[0], y / SOIL_A[1]) / disc_wobble(th)


class Ground:
    """The built soil, sampled by a ray straight down, so everything seated
    on it sits on the faces actually shipped."""

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
# The boulder: a star-shaped radial field about an interior origin
# --------------------------------------------------------------------------

def draw_waves(rng, size):
    waves = []
    for freq, amp in ((1.9, 1.0), (2.9, 0.62), (4.3, 0.42), (6.1, 0.28), (8.7, 0.18),
                      (12.3, 0.11), (17.0, 0.07), (23.0, 0.045)):
        w = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized()
        waves.append((w * (freq / max(size, 0.4)), rng.uniform(0.0, TAU), amp))
    total = sum(a for _w, _p, a in waves)
    return [(w, p, a / total) for w, p, a in waves]


class Rock:
    """The boulder in its own frame. ``sample(d)`` is the distance from the
    origin ``o`` to the surface along unit ``d``: the ellipsoid, cut by each
    cleavage plane through a soft minimum, displaced by seeded waves, then
    notched by the crack. ``M`` maps the frame to the world."""

    def __init__(self, plan):
        self.axes = Vector(ROCK_AXES)
        self.o = Vector(ROCK_O)
        self.waves = plan["rock_waves"]
        self.planes = []
        for nrm, f, k in tuple(ROCK_PLANES) + tuple(plan["rock_chips"]):
            n = Vector(nrm).normalized()
            self.planes.append((n, f * self.support(n), k))
        self.nc = Vector(CRACK_N).normalized()
        self.bottom = plan.get("rock_bottom")
        self.M = Matrix.Identity(4)
        self.Mi = Matrix.Identity(4)

    def set_matrix(self, M):
        self.M = M.copy()
        self.Mi = M.inverted()

    def support(self, n):
        a = self.axes
        return math.sqrt((a.x * n.x) ** 2 + (a.y * n.y) ** 2 + (a.z * n.z) ** 2)

    def fbm(self, p):
        return sum(a * math.sin(w.dot(p) + ph) for w, ph, a in self.waves)

    def whole(self, d):
        """Radius along ``d`` before the crack."""
        a = self.axes
        qa = Vector((self.o.x / a.x, self.o.y / a.y, self.o.z / a.z))
        wa = Vector((d.x / a.x, d.y / a.y, d.z / a.z))
        A = wa.dot(wa)
        B = 2.0 * qa.dot(wa)
        C = qa.dot(qa) - 1.0
        te = (-B + math.sqrt(max(B * B - 4.0 * A * C, 0.0))) / (2.0 * A)
        r = te
        tmin = te
        for n, h, k in self.planes:
            dn = n.dot(d)
            if dn <= 1e-6:
                continue
            t = (h - n.dot(self.o)) / dn
            tmin = min(tmin, t)
            r = smin(r, t, k)
        if self.bottom is not None and d.z < -1e-6:
            r = smin(r, (self.bottom - self.o.z) / d.z, 0.04)
        flat = smoothstep(te - tmin, 0.0, 0.06)
        p = self.o + d * r
        return r + ROCK_AMP * self.fbm(p) * (1.0 - 0.6 * flat)

    def crack_depth(self, d, r0):
        dist = abs(self.nc.dot(d)) * r0
        if dist >= CRACK_W:
            return 0.0
        m = smoothstep(d.z, CRACK_LOW, CRACK_LOW + 0.34)
        return CRACK_D * m * (1.0 - dist / CRACK_W) ** 2

    def sample(self, d):
        """(radius, whole radius, crack depth) along unit ``d``."""
        r0 = self.whole(d)
        c = self.crack_depth(d, r0)
        return r0 - c, r0, c

    def local_point(self, d):
        return self.o + d * self.sample(d)[0]

    def point(self, d):
        return self.M @ self.local_point(d)

    def normal(self, d):
        e1, e2 = perp_basis(d)
        e = 0.004
        pa = self.local_point((d + e1 * e).normalized()) - self.local_point((d - e1 * e).normalized())
        pb = self.local_point((d + e2 * e).normalized()) - self.local_point((d - e2 * e).normalized())
        n = pa.cross(pb).normalized()
        if n.dot(d) < 0.0:
            n = -n
        return (self.M.to_3x3() @ n).normalized()

    def contains(self, p, margin=0.0):
        """World point ``p`` inside the boulder (grown by ``margin``)."""
        q = self.Mi @ p
        v = q - self.o
        ln = v.length
        if ln < 1e-9:
            return True
        return ln < self.sample(v / ln)[0] + margin


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


def crack_dirs(dirs, nc):
    """Turn the lattice so one family of its lines runs along the crack
    plane, then draw it in toward the plane so the narrow V is resolved:
    angle a off the plane goes to A (|a| / A)^Q inside A."""
    R = Vector((1.0, 0.0, 0.0)).rotation_difference(nc).to_matrix()
    out = []
    for d in dirs:
        d = R @ d
        s = max(-1.0, min(1.0, nc.dot(d)))
        a = math.asin(s)
        if abs(a) < CRACK_A:
            par = d - nc * s
            if par.length > 1e-9:
                a2 = math.copysign(CRACK_A * (abs(a) / CRACK_A) ** CRACK_Q, a)
                d = par.normalized() * math.cos(a2) + nc * math.sin(a2)
        out.append(d.normalized())
    return out


class RockMesh:
    """The boulder sampled on its crack-drawn cube-sphere."""

    def __init__(self, rock, n):
        self.rock = rock
        dirs, quads = cube_sphere(n)
        self.dirs = crack_dirs(dirs, rock.nc)
        self.quads = quads
        self.local = []
        self.crack = []
        for d in self.dirs:
            r, _r0, c = rock.sample(d)
            self.local.append(rock.o + d * r)
            self.crack.append(c)

    def world(self):
        return [self.rock.M @ p for p in self.local]

    def tree(self):
        return BVHTree.FromPolygons([tuple(p) for p in self.world()], self.quads)


def flank_bury(pts, ground):
    """Per sector about the plan centroid, the deepest flank vertex below
    the ground straight above it. Flank: at least FLANK_R of the sector's
    plan reach from the centroid."""
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


def place_rock(rock, perch):
    """Bed the boulder: sink it until every sector's most-buried flank
    vertex is EMBED under the soil. ``perch`` beds it against the soil
    height at its centre alone, as if the bank were level."""
    M0 = Matrix.Translation(Vector((ROCK_XY[0], ROCK_XY[1], 0.0))) @ rotz(ROCK_YAW)
    for _pass in range(2):
        rock.set_matrix(M0)
        pts = RockMesh(rock, ROCK_N).world()
        if perch:
            cz = soil_height(ROCK_XY[0], ROCK_XY[1])
            best = flank_bury(pts, lambda x, y: cz)
        else:
            best = flank_bury(pts, soil_height)
        dz = min(best) - EMBED
        rock.set_matrix(Matrix.Translation(Vector((0.0, 0.0, dz))) @ M0)
        if rock.bottom is not None:
            break
        # the buried underside is cut flat above the soil disc's base (the
        # frame turns only about Z, so a local height is a world height)
        rock.bottom = ROCK_FOOT - dz
    return rock


def rock_hull(rock):
    pts = RockMesh(rock, 10).world()
    return hull2d([(p.x, p.y) for p in pts])


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


# --------------------------------------------------------------------------
# Fronds: a rachis path, blade frames and the pinnae hung on it
# --------------------------------------------------------------------------

def frond_dir(fr, s):
    th = fr["e0"] + (fr["etip"] - fr["e0"]) * s ** fr["curv"]
    ps = fr["az"] + fr["lat"] * s * s
    return Vector((math.cos(th) * math.cos(ps), math.cos(th) * math.sin(ps), math.sin(th)))


def frond_path(fr):
    """Rachis points, tangents and blade side vectors (horizontal, left of
    the heading, turned by the frond's twist)."""
    n = fr["rings"]
    step = fr["L"] / (n - 1)
    p = fr["base"].copy()
    pts = [p.copy()]
    for i in range(1, n):
        s = (i - 0.5) / (n - 1)
        p = p + frond_dir(fr, s) * step
        pts.append(p.copy())
    tans, sides = [], []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        t = (b - a).normalized()
        s = i / (n - 1)
        ps = fr["az"] + fr["lat"] * s * s
        sv = Vector((-math.sin(ps), math.cos(ps), 0.0))
        sv = (sv - t * sv.dot(t)).normalized()
        sv = rotate_about(sv, t, fr["twist"] * s)
        tans.append(t)
        sides.append(sv)
    return pts, tans, sides


def rachis_radius(fr, s):
    return R_RACHIS_TIP + (fr["r0"] - R_RACHIS_TIP) * (1.0 - s) ** 0.75


def at(path, s):
    pts, tans, sides = path
    n = len(pts)
    x = min(max(s, 0.0), 1.0) * (n - 1)
    j = min(int(x), n - 2)
    f = x - j
    p = pts[j].lerp(pts[j + 1], f)
    t = (pts[j + 1] - pts[j]).normalized()
    sv = sides[j].lerp(sides[j + 1], f)
    sv = (sv - t * sv.dot(t)).normalized()
    return p, t, sv


def pinna_profile(u, peak):
    """Pinna length along the blade (0 at its base, 1 at the tip): the
    lowest pinnae shorter, the longest a third of the way up, tapering to
    a point."""
    if u < peak:
        return 0.50 + 0.50 * math.sin(0.5 * math.pi * u / peak)
    return 0.06 + 0.94 * math.cos(0.5 * math.pi * min(1.0, (u - peak) / (1.0 - peak))) ** 1.15


def plan_pinnae(fr, n_side, lmax, npin_max, key0, rng_u):
    """Alternate pinnae: stations on the two sides interleave by half a
    spacing, crowding a little toward the tip."""
    peak = fr["peak"]
    out = []
    for side, off in ((1.0, 0.0), (-1.0, 0.5)):
        for i in range(n_side):
            u = 0.015 + 0.955 * ((i + off + 0.25) / n_side) ** 0.94
            ell = lmax * pinna_profile(u, peak) * (0.94 + 0.12 * hash01(key0, i, side))
            npin = max(1, min(npin_max, int(round(ell / 0.0165))))
            k = key0 * 1000.0 + i * 2 + (0 if side > 0 else 1)
            out.append({"u": u, "i": i, "side": side, "ell": ell, "npin": npin, "key": k,
                        "beta": math.radians(78.0 - 26.0 * u + 6.0 * (hash01(k, 1, 1) - 0.5)),
                        "roll": PINNA_TWIST * ((i % 3) - 1) + 0.03 * (hash01(k, 1, 2) - 0.5),
                        "droop": 0.004 + 0.006 * hash01(k, 1, 3),
                        "sweep": 0.05 + 0.08 * hash01(k, 1, 4),
                        "rise": 0.08 + 0.08 * hash01(k, 1, 7)})
    return out


def pinna_frame(fr, pn, path, uu=None):
    """Where a pinna leaves the rachis and how it is set: its station, the
    rachis point, the rachis tangent, the blade normal, the pinna's axis
    and its unturned normal."""
    if uu is None:
        uu = pn["u"]
    s = fr["sb"] + uu * (0.985 - fr["sb"])
    p, t, sv = at(path, s)
    nb = t.cross(sv).normalized()
    sg = pn["side"]
    be = pn["beta"]
    e1 = (t * math.cos(be) + sv * (sg * math.sin(be)) + nb * pn["rise"]).normalized()
    e30 = (nb - e1 * nb.dot(e1)).normalized()
    return s, p, t, nb, e1, e30


def separate_pinnae(fronds):
    """Turn each pinna about its own axis, in PINNA_STEP steps either side
    of its planned twist, until its normal is PINNA_SEP off the normal of
    every pinna already set whose faces can come within
    COPLANAR_CENTRE_MAX of its own. Returns how many could not be cleared."""
    placed = []
    cos_sep = math.cos(PINNA_SEP)
    failed = 0
    for fr in fronds:
        path = frond_path(fr)
        for pn in sorted(fr["pinnae"], key=lambda q: (q["u"], q["side"])):
            _s, p, _t, _nb, e1, e30 = pinna_frame(fr, pn, path)
            half = 0.5 * pn["ell"]
            c = p + e1 * half
            near = [n for q, n, h in placed if (q - c).length < half + h + COPLANAR_CENTRE_MAX]
            r0 = pn["roll"]
            best = None
            for k in range(41):
                r = r0 + ((k + 1) // 2) * PINNA_STEP * (1.0 if k % 2 else -1.0)
                n = rotate_about(e30, e1, r)
                if all(abs(n.dot(m)) < cos_sep for m in near):
                    best = r
                    break
            if best is None:
                failed += 1
                best = r0
            pn["roll"] = best
            placed.append((c, rotate_about(e30, e1, best), half))
    return failed


def frond_clear(fr, rock, extra_pts=()):
    """True if the frond keeps off the boulder and above the soil."""
    path = frond_path(fr)
    pts, tans, sides = path
    for i, p in enumerate(pts):
        s = i / (len(pts) - 1)
        # a crack fern's stipe climbs out of the cleft: held off the walls
        # only, not the margin the open blade keeps
        if rock.contains(p, 0.0 if (fr["crack"] and s < fr["sb"]) else 0.035):
            return False
        if i > 2 and p.z < soil_height(p.x, p.y) + 0.05:
            return False
        if s >= fr["sb"]:
            u = (s - fr["sb"]) / (1.0 - fr["sb"])
            half = fr["lmax"] * pinna_profile(u, fr["peak"])
            for sg in (1.0, -1.0):
                q = p + sides[i] * (sg * half)
                if rock.contains(q, 0.030):
                    return False
                if q.z < soil_height(q.x, q.y) + 0.04:
                    return False
    return True


# --------------------------------------------------------------------------
# The plan: every seeded draw happens here, before anything is built
# --------------------------------------------------------------------------

def plan_scene():
    rng = random.Random(SEED)

    def u(a, b):
        return a + (b - a) * rng.random()

    plan = {"rock_waves": draw_waves(rng, max(ROCK_AXES))}
    chips = []
    for _k in range(ROCK_CHIPS):
        n = Vector((rng.gauss(0, 1), rng.gauss(0, 1), abs(rng.gauss(0, 0.8)) + 0.15))
        chips.append((tuple(n.normalized()), u(0.74, 0.84), 0.025))
    plan["rock_chips"] = chips
    rock = place_rock(Rock(plan), False)
    plan["rock_M"] = rock.M.copy()
    plan["rock_bottom"] = rock.bottom

    # --- the crown: a rootstock bedded at the boulder's downhill foot
    cx, cy = CROWN_XY
    knob_c = Vector((cx, cy, soil_height(cx, cy) - KNOB_SINK))
    plan["knob_c"] = knob_c
    plan["knob_lumps"] = [u(-1.0, 1.0) for _ in range(160)]
    fronds = []
    az0 = u(0.0, TAU)
    order = list(range(FRONDS))
    rng.shuffle(order)
    for k in range(FRONDS):
        az = az0 + TAU * k / FRONDS + u(-0.20, 0.20)
        age = order[k] / (FRONDS - 1)        # 0 youngest (upright) .. 1 oldest (spread)
        L = u(*FROND_L) * (0.92 + 0.10 * age)
        ring_r = 0.30 + 0.25 * age
        base = knob_c + Vector((math.cos(az) * KNOB_R[0] * ring_r,
                                math.sin(az) * KNOB_R[1] * ring_r, KNOB_R[2] * 0.55))
        fr = {"id": 300 + k, "parent": KNOB_ID, "base": base, "az": az, "L": L,
              "e0": math.radians(FROND_E0[1] - (FROND_E0[1] - FROND_E0[0]) * age + u(-2.0, 2.0)),
              "etip": math.radians(FROND_ETIP[1] - (FROND_ETIP[1] - FROND_ETIP[0]) * age
                                   + u(-4.0, 4.0)),
              "curv": u(1.5, 1.9), "lat": u(-0.30, 0.30), "twist": u(-0.35, 0.35),
              "rings": FROND_RINGS, "sb": STIPE_F + u(-0.02, 0.02), "r0": R_STIPE * u(0.92, 1.08),
              "lmax": u(*PINNA_LMAX) * L / 0.9, "peak": u(0.26, 0.38), "tone": rng.random(),
              "n_side": PINNAE, "npin_max": PINNULES_MAX, "crack": False}
        # a frond that would run into the boulder or the bank stands up
        # steeper and arches less until it clears
        for _t in range(16):
            if frond_clear(fr, rock):
                break
            fr["e0"] = min(fr["e0"] + math.radians(3.0), math.radians(84.0))
            fr["etip"] = fr["etip"] + math.radians(5.0)
        fr["pinnae"] = plan_pinnae(fr, PINNAE, fr["lmax"], PINNULES_MAX, fr["id"], u)
        fronds.append(fr)

    # --- the crack fern: a small rootstock wedged down the cleft
    nc = rock.nc
    v = Vector((0.0, -0.55, 0.83))
    v = (v - nc * v.dot(nc)).normalized()
    r, r0, c = rock.sample(v)
    ck_local = rock.o + v * (r0 - CKNOB_DEPTH * CRACK_D)
    ck = rock.M @ ck_local
    plan["cknob_c"] = ck
    plan["cknob_lumps"] = [u(-1.0, 1.0) for _ in range(60)]
    along = (rock.M.to_3x3() @ nc.cross(v)).normalized()
    out_w = (rock.M.to_3x3() @ v).normalized()
    plan["crack_frame"] = (along, out_w, (rock.M.to_3x3() @ nc).normalized())
    for k in range(CRACK_FRONDS):
        sgn = 1.0 if k % 2 == 0 else -1.0
        h = along * (sgn * (0.35 + 0.65 * (k // 2) / 2.0)) + out_w * 0.35
        az = math.atan2(h.y, h.x) + u(-0.25, 0.25)
        L = u(*CRACK_FROND_L)
        base = ck + out_w * (0.25 * CKNOB_R) + along * (sgn * 0.15 * CKNOB_R * (k // 2))
        fr = {"id": 400 + k, "parent": CKNOB_ID, "base": base, "az": az, "L": L,
              "e0": math.radians(u(68.0, 80.0)), "etip": math.radians(u(-12.0, 10.0)),
              "curv": u(1.4, 1.8), "lat": u(-0.25, 0.25), "twist": u(-0.3, 0.3),
              "rings": 16, "sb": 0.30 + u(-0.02, 0.02), "r0": 0.0036 * u(0.9, 1.1),
              "lmax": u(0.050, 0.062) * L / 0.35, "peak": u(0.26, 0.36), "tone": rng.random(),
              "n_side": CRACK_PINNAE, "npin_max": CRACK_PINNULES_MAX, "crack": True}
        for _t in range(16):
            if frond_clear(fr, rock):
                break
            fr["e0"] = min(fr["e0"] + math.radians(3.0), math.radians(86.0))
            fr["etip"] = fr["etip"] + math.radians(5.0)
        fr["pinnae"] = plan_pinnae(fr, CRACK_PINNAE, fr["lmax"], CRACK_PINNULES_MAX, fr["id"], u)
        fronds.append(fr)
    plan["fronds"] = fronds
    plan["sep_failed"] = separate_pinnae(fronds)

    # --- fiddleheads at the crown's heart
    crosiers = []
    for k in range(CROSIERS):
        a = az0 + 0.9 + TAU * k / CROSIERS + u(-0.3, 0.3)
        lean = u(0.10, 0.24)
        crosiers.append({"id": 500 + k, "az": a, "lean": lean, "h": u(0.09, 0.19),
                         "r0": CROSIER_R0 * u(0.85, 1.10), "tone": rng.random(),
                         "base": knob_c + Vector((math.cos(a) * 0.012, math.sin(a) * 0.012,
                                                  KNOB_R[2] * 0.55))})
    plan["crosiers"] = crosiers
    stubs = []
    for k in range(STUBS):
        a = az0 + 0.3 + TAU * (k + 0.5) / STUBS + u(-0.2, 0.2)
        stubs.append({"id": 600 + k, "az": a, "e": math.radians(u(35.0, 60.0)),
                      "L": u(0.045, 0.075), "tone": rng.random()})
    plan["stubs"] = stubs

    # --- ground cover, rejection-sampled on the disc, off the boulder and the crown
    hull = rock_hull(rock)
    plan["rock_hull"] = hull
    taken = []

    def spot(rmax, lo, hi, clear_knob, spacing):
        for _t in range(4000):
            x = SOIL_C[0] + u(-SOIL_A[0], SOIL_A[0])
            y = SOIL_C[1] + u(-SOIL_A[1], SOIL_A[1])
            if disc_frac(x, y) > rmax:
                continue
            m = hull_margin(hull, x, y)
            if not (-hi <= m <= -lo):
                continue
            if math.hypot(x - cx, y - cy) < clear_knob:
                continue
            if any(math.hypot(x - px, y - py) < spacing + pr for px, py, pr in taken):
                continue
            return x, y
        return None

    twigs = []
    for _k in range(TWIGS):
        s = spot(0.72, 0.12, 9.0, 0.30, 0.10)
        if s is None:
            continue
        twigs.append((s[0], s[1], u(0.0, TAU), u(0.34, 0.42), rng.random()))
        taken.append((s[0], s[1], 0.20))
    litter = []
    for k in range(LITTER):
        # most of it drifts against the boulder's foot; the rest lies open
        s = spot(0.80, 0.03, 0.30, 0.12, 0.03) if k % 3 else spot(0.80, 0.03, 9.0, 0.12, 0.03)
        if s is None:
            continue
        litter.append((s[0], s[1], u(0.0, TAU), u(0.090, 0.125), rng.random(),
                       (1.0 if rng.random() < 0.5 else -1.0) * u(0.20, 0.32)))
        taken.append((s[0], s[1], 0.035))
    pebbles = []
    for k in range(PEBBLES):
        near = k < PEBBLES * 0.6
        s = spot(0.78, 0.02, 0.22 if near else 9.0, 0.14, 0.02)
        if s is None:
            continue
        r = 0.018 + 0.030 * rng.random() ** 1.6
        pebbles.append((s[0], s[1], r, u(0.0, TAU), rng.random(), [u(-1, 1) for _ in range(26)]))
        taken.append((s[0], s[1], r * 1.3))
    sorrel = []
    for _k in range(SORREL):
        s = spot(0.74, 0.10, 9.0, 0.20, 0.10)
        if s is None:
            continue
        leaves = [{"az": u(0.0, TAU), "h": u(0.045, 0.085), "lean": u(0.10, 0.45),
                   "L": u(0.021, 0.029), "spin": u(0.0, TAU), "tone": rng.random()}
                  for _l in range(3 + (1 if rng.random() < 0.6 else 0))]
        sorrel.append((s[0], s[1], leaves))
        taken.append((s[0], s[1], 0.08))
    plan["cover"] = {"litter": litter, "pebbles": pebbles, "sorrel": sorrel, "twigs": twigs}
    return plan


def taper_frond(plan):
    """The crown frond held furthest inside the envelope: --flat-taper and
    --opposite-pinnae reshape it alone, so the bounding box cannot move."""
    crown = [f for f in plan["fronds"] if not f["crack"]]
    tips = [frond_path(f)[0] for f in crown]
    lo = Vector((min(p.x for ps in tips for p in ps), min(p.y for ps in tips for p in ps),
                 min(p.z for ps in tips for p in ps)))
    hi = Vector((max(p.x for ps in tips for p in ps), max(p.y for ps in tips for p in ps),
                 max(p.z for ps in tips for p in ps)))

    def margin(ps):
        return min(min(p.x - lo.x, hi.x - p.x, p.y - lo.y, hi.y - p.y, hi.z - p.z) for p in ps)

    k = max(range(len(crown)), key=lambda i: margin(tips[i]))
    return crown[k]["id"]


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

class Builder:
    """The bmesh plus its layers: Tone (shading variety), Part (the shell's
    role), Ident and Parent (who is carried by whom), Cap (1 on a tube's
    base cap, 2 on its end cap), Zone (the moss's top, a leaf's underside,
    a crack face), Ring (a tube vertex's ring, a cushion vertex's ring) and
    Tip (0 at a pinna's or leaf's base, 1 at its apex; along a frond on its
    stalk)."""

    def __init__(self, bm):
        self.bm = bm
        self.tone = bm.faces.layers.float.new("Tone")
        self.zone = bm.faces.layers.float.new("Zone")
        self.part = bm.faces.layers.int.new("Part")
        self.ident = bm.faces.layers.int.new("Ident")
        self.parent = bm.faces.layers.int.new("Parent")
        self.cap = bm.faces.layers.int.new("Cap")
        self.ring = bm.verts.layers.int.new("Ring")
        self.tip = bm.verts.layers.float.new("Tip")
        self.crack = bm.verts.layers.float.new("Crack")
        # the packed UVMap first, so it stays the active (baked, exported) map;
        # LeafUV runs across (x) and along (y) each pinna and leaf for its veins
        self.uv = bm.loops.layers.uv.new("UVMap")
        self.luv = bm.loops.layers.uv.new("LeafUV")
        self.leaf_uv = {}

    def vert(self, co, ring=-1, tip=0.0, luv=None):
        v = self.bm.verts.new(co)
        v[self.ring] = ring
        v[self.tip] = tip
        if luv is not None:
            self.leaf_uv[v] = luv
        return v

    def face(self, verts, mat, tone, part, ident=0, parent=-1, cap=0, zone=0.0):
        f = self.bm.faces.new(verts)
        f.material_index = mat
        f[self.tone] = tone
        f[self.part] = part
        f[self.ident] = ident
        f[self.parent] = parent
        f[self.cap] = cap
        f[self.zone] = zone
        return f

    def finish_luv(self, faces):
        for f in faces:
            for loop in f.loops:
                loop[self.luv].uv = self.leaf_uv.get(loop.vert, (0.5, 0.5))


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


def add_tube(B, pts, radii, sides, mat, tone, part, ident=0, parent=-1, phase=0.0, jag=None,
             squash=1.0, tips=None):
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
            tip = tips[idx] if tips is not None else idx / (len(pts) - 1)
            ring.append(B.vert(p + off + r * (n * (squash * math.cos(a)) + b * math.sin(a)),
                               ring=idx, tip=tip))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            B.face((r0[k], r0[m], r1[m], r1[k]), mat, tone, part, ident, parent)
    B.face(tuple(reversed(rings[0])), mat, tone, part, ident, parent, cap=1)
    B.face(tuple(rings[-1]), mat, tone, part, ident, parent, cap=2)
    return [v for ring in rings for v in ring]


def add_blob(B, centre, axes, n, lumps, mat, tone, part, ident, parent=-1):
    """A lumpy closed body on a cube-sphere lattice."""
    dirs, quads = cube_sphere(n)
    verts = []
    for i, d in enumerate(dirs):
        s = 1.0 + 0.16 * lumps[i % len(lumps)]
        verts.append(B.vert(centre + Vector((d.x * axes[0], d.y * axes[1], d.z * axes[2])) * s))
    for q in quads:
        a, b, c, e = (verts[i] for i in q)
        # split on the short diagonal so the lumps stay convex-ish and planar
        if (a.co - c.co).length <= (b.co - e.co).length:
            B.face((a, b, c), mat, tone, part, ident, parent)
            B.face((a, c, e), mat, tone, part, ident, parent)
        else:
            B.face((a, b, e), mat, tone, part, ident, parent)
            B.face((b, c, e), mat, tone, part, ident, parent)
    return verts


def fan_strip(B, P, run, faces, mat, tone, part, parent, zone):
    """Triangles from outline vertex ``P`` over the costa ``run``."""
    for c0, c1 in zip(run, run[1:]):
        faces.append(B.face((c0, P, c1), mat, tone, part, 0, parent, zone=zone))


def add_pinna(B, base, e1, e2, e3, ell, pn, tone, parent, mat=FROND_IDX, part=P_PINNA,
              flat=False):
    """A pinna cut into pinnules: one closed, thin shell. A costa runs from
    the base (inside the rachis) to the apex, curving toward the frond's
    tip; alternate oblong pinnules on its two sides are lobes cut almost to
    the costa. The rim is shared by a top and a bottom surface, each fanned
    from its own costa vertices, so every rim edge has one face above and
    one below. Pinnules rise off the costa and curl down at their tips."""
    npin = pn["npin"]
    sweep, droop = pn["sweep"], pn["droop"]
    key = pn["key"]
    lam0 = 0.150
    wing0 = 0.028
    alpha = math.radians(70.0)
    # a thin blade: the costa stands this proud of the rim above and below,
    # in pinna lengths, so a small pinna's faces tilt no more than a large one's
    lift_t = max(0.0012, 0.000012 / ell)
    lift_b = max(0.0010, 0.000010 / ell)

    def frame(x):
        a = Vector((1.0, 2.0 * sweep * x)).normalized()
        return a, Vector((-a.y, a.x))

    def cpt(x):
        return Vector((x, sweep * x * x))

    def world(q2, lat, x, lift=0.0):
        z = -droop * x * x + lift
        return base + e1 * (q2.x * ell) + e2 * (q2.y * ell) + e3 * (z * ell)

    x0, x1 = 0.07, 0.90
    dx = (x1 - x0) / npin
    lobes = {1.0: [], -1.0: []}
    stations = []
    for sg, off in ((1.0, 0.25), (-1.0, 0.75)):
        for j in range(npin):
            xj = x0 + (j + off) * dx
            stations.append((xj, sg, j))
    stations.sort()
    top, bot = {}, {}
    for xj, sg, j in stations:
        a, b = frame(xj)
        c = cpt(xj)
        lift = (1.0 - 0.7 * xj)
        top[(sg, j)] = B.vert(world(c, 0.0, xj, lift_t * lift), tip=min(0.99, xj), luv=(0.5, xj))
        bot[(sg, j)] = B.vert(world(c, 0.0, xj, -lift_b * lift), tip=min(0.99, xj), luv=(0.5, xj))
    vb = B.vert(base, tip=0.0, luv=(0.5, 0.0))
    va = B.vert(world(cpt(1.0), 0.0, 1.0), tip=1.0, luv=(0.5, 1.0))
    reach = lam0 + wing0 * 2.0
    for sg in (1.0, -1.0):
        for j in range(npin):
            xj = x0 + (j + (0.25 if sg > 0 else 0.75)) * dx
            a, b = frame(xj)
            c = cpt(xj)
            k2 = key * 7.0 + j * 2 + (0 if sg > 0 else 1)
            lam = lam0 * (1.0 - 0.60 * xj) * (1.0 if sg > 0 else 0.90) * (0.90 + 0.20 * hash01(k2, 3, 1))
            if flat:
                lam = lam0 * 0.62
            w = 0.80 * dx
            wing = wing0 * (1.0 + 0.8 * xj)
            ca, sa = math.cos(alpha), math.sin(alpha)
            B1 = Vector((-0.5 * w, wing))
            B2 = Vector((0.5 * w, wing))
            T = Vector((lam * ca + 0.15 * w, wing + lam * sa)) + Vector(((hash01(k2, 3, 2) - 0.5) * 0.2 * w, 0.0))
            e_p = (T - B1).normalized()
            e_d = (T - B2).normalized()
            E1 = B1 * 0.35 + T * 0.65 + Vector((-e_p.y, e_p.x)) * (0.22 * w)
            E2 = B2 * 0.35 + T * 0.65 + Vector((e_d.y, -e_d.x)) * (0.22 * w)
            run = []
            for q in (B1, E1, T, E2, B2):
                q2 = c + a * q.x + b * (sg * q.y)
                run.append(B.vert(world(q2, q.y, xj + q.x), tip=min(0.99, max(0.01, xj + q.x)),
                                  luv=(0.5 + 0.5 * sg * q.y / reach, xj + q.x)))
            lobes[sg].append(run)
    faces = []
    for sg in (1.0, -1.0):
        mine = [(xj, j) for xj, s2, j in stations if s2 == sg]
        for surf, zone in ((top, 0.0), (bot, 1.0)):
            costa = [(0.0, vb)] + [(xj, surf[(s2, j)]) for xj, s2, j in stations] + [(1.0, va)]
            idx = {id(v): i for i, (_x, v) in enumerate(costa)}
            cv = [v for _x, v in costa]
            prev = 0
            for (xj, j), run in zip(mine, lobes[sg]):
                m = surf[(sg, j)]
                mi = idx[id(m)]
                # the gap before this lobe
                gap = cv[prev:mi + 1]
                if prev == 0:
                    fan_strip(B, run[0], gap, faces, mat, tone, part, parent, zone)
                else:
                    P = lobes[sg][mine.index((xj, j)) - 1][-1]
                    h = (len(gap) - 1) // 2
                    fan_strip(B, P, gap[:h + 1], faces, mat, tone, part, parent, zone)
                    faces.append(B.face((gap[h], P, run[0]), mat, tone, part, 0, parent, zone=zone))
                    fan_strip(B, run[0], gap[h:], faces, mat, tone, part, parent, zone)
                for q0, q1 in zip(run, run[1:]):
                    faces.append(B.face((m, q0, q1), mat, tone, part, 0, parent, zone=zone))
                prev = mi
            fan_strip(B, lobes[sg][-1][-1], cv[prev:], faces, mat, tone, part, parent, zone)
    B.finish_luv(faces)
    return faces


def add_frond(B, fr, flags, taper_id, detail):
    """A stipe and rachis as one tapering tube, and its pinnae."""
    path = frond_path(fr)
    pts, tans, sides = path
    n = len(pts)
    radii = [rachis_radius(fr, i / (n - 1)) for i in range(n)]
    tpts = [p.copy() for p in pts]
    if flags["float_fronds"]:
        # the tube starts outside its rootstock; the path, and so every
        # pinna hung on it, is unchanged
        tpts[0] = tpts[0] + tans[0] * FLOAT_FRONDS
    sides_n = FROND_SIDES_HIGH if detail == "high" else FROND_SIDES
    tone = fr["tone"]
    add_tube(B, tpts, radii, sides_n, STIPE_IDX, tone, P_STIPE, fr["id"], fr["parent"],
             phase=fr["az"], tips=[i / (n - 1) for i in range(n)])
    flat = flags["flat_taper"] and fr["id"] == taper_id
    opposite = flags["opposite_pinnae"] and fr["id"] == taper_id
    sb = fr["sb"]
    lmax = fr["lmax"]
    for pn in fr["pinnae"]:
        uu = pn["u"]
        if opposite and pn["side"] < 0:
            # the lower side's pinnae moved level with the upper side's
            uu = 0.015 + 0.955 * ((pn["i"] + 0.27) / fr["n_side"]) ** 0.94
        s, p, t, nb, e1, e30 = pinna_frame(fr, pn, path, uu)
        e3 = rotate_about(e30, e1, pn["roll"])
        e2 = e3.cross(e1).normalized()
        if e2.dot(t) < 0.0:
            e2 = -e2
        ell = pn["ell"]
        if flat:
            ell = 0.80 * lmax
        r_here = rachis_radius(fr, s)
        k = pn["key"]
        base = p + t * ((hash01(k, 2, 2) - 0.5) * 0.8 * r_here)
        ptone = min(1.0, max(0.0, tone * 0.6 + 0.4 * hash01(k, 4, 1)))
        add_pinna(B, base, e1, e2, e3, ell, pn, ptone, fr["id"], flat=flat)


def crosier_path(cr, open_):
    """A fiddlehead: a stipe rising from the rootstock with a little lean,
    then a coil in the plane of that lean, rolling over outward and in on
    itself as a logarithmic spiral (radius R0 exp(-b phi), so its curvature
    rises toward the centre). ``open_``: a circular arc of the same length
    instead."""
    lean = Vector((math.cos(cr["az"]), math.sin(cr["az"]), 0.0))
    v = (UP + lean * cr["lean"]).normalized()
    h = (lean - v * lean.dot(v)).normalized()
    ns, nc_ = CROSIER_RINGS
    pts = []
    base = cr["base"]
    top = base + v * cr["h"]
    for i in range(ns):
        t = i / ns
        pts.append(base.lerp(top, t) + h * (0.010 * math.sin(math.pi * t)))
    R0 = cr["r0"]
    b = CROSIER_B
    total = CROSIER_TURNS * TAU
    # arc length of the spiral, for the open falsifier's circle
    arc = R0 * math.sqrt(1.0 + b * b) * (1.0 - math.exp(-b * total)) / b
    C = top + h * R0
    for i in range(nc_ + 1):
        phi = total * i / nc_
        if open_:
            ang = (arc / R0) * i / nc_
            p = C + (h * (-math.cos(ang)) + v * math.sin(ang)) * R0
        else:
            r = R0 * math.exp(-b * phi)
            p = C + (h * (-math.cos(phi)) + v * math.sin(phi)) * r
        pts.append(p)
    return pts


def add_crosier(B, cr, flags, detail):
    pts = crosier_path(cr, flags["open_crozier"])
    ns = CROSIER_RINGS[0]
    n = len(pts)
    radii = []
    for i in range(n):
        if i < ns:
            radii.append(0.0052 - 0.0006 * i / ns)
        else:
            f = (i - ns) / (n - 1 - ns)
            r = 0.0068 * (1.0 - f) + 0.0030 * f
            # the coiled pinnae swell the coil into a beaded roll
            radii.append(r * (1.0 + 0.20 * abs(math.sin(9.0 * math.pi * f))))
    sides = 8 if detail == "high" else 6
    add_tube(B, pts, radii, sides, CROZIER_IDX, cr["tone"], P_CROSIER, cr["id"], KNOB_ID,
             phase=cr["az"] + 0.4)


def add_stub(B, st, knob_c):
    d = Vector((math.cos(st["az"]) * math.cos(st["e"]), math.sin(st["az"]) * math.cos(st["e"]),
                math.sin(st["e"])))
    base = knob_c + Vector((math.cos(st["az"]) * KNOB_R[0] * 0.45,
                            math.sin(st["az"]) * KNOB_R[1] * 0.45, KNOB_R[2] * 0.50))
    pts = [base + d * (st["L"] * i / 3.0) for i in range(4)]
    jag = [(0.80, 0.004), (1.0, -0.003), (0.65, 0.006), (0.95, -0.002), (0.75, 0.005)]
    add_tube(B, pts, [0.0062, 0.0058, 0.0055, 0.0050], 5, ROOT_IDX, st["tone"], P_STUB, st["id"],
             KNOB_ID, phase=st["az"], jag=jag)


def add_moss(B, rock, tree, spec, idx, ground, lift=0.0, sunny=False):
    """A moss cushion laid on the stone: a lens over a patch of the surface,
    stretched down the fall line, its rim tucked into the stone and its
    base inside it. Its outline stops short of the crack lip and of the
    soil. Every point is snapped to the stone as built (``tree``)."""
    dvec, radius, stretch, thick, K, Mseg, drape, far = spec
    d0 = Vector(dvec).normalized()
    if sunny and idx == 0:
        # the main cushion moved round to the boulder's sunny back face
        d0 = Vector(SUNNY_D).normalized()
    # the drape: its direction across the patch in the rock frame
    down = Vector(drape).normalized()
    e1 = (down - d0 * down.dot(d0))
    if e1.length < 1e-3:
        e1 = Vector((0.0, -1.0, 0.0)) - d0 * (-d0.y)
    e1.normalize()
    e2 = d0.cross(e1).normalized()
    r0 = rock.sample(d0)[1]
    sgn0 = 1.0 if rock.nc.dot(d0) > 0.0 else -1.0
    ph = hash01(idx, 9, 1) * TAU

    def ok(d):
        r, rr0, _c = rock.sample(d)
        ragged = 0.5 + 0.5 * math.sin(37.0 * d.y + 23.0 * d.z + ph) * math.cos(19.0 * d.z - 11.0 * d.y)
        if sgn0 * rock.nc.dot(d) * rr0 < CRACK_W + MOSS_CRACK_CLEAR + 0.05 * ragged:
            return False
        p = rock.M @ (rock.o + d * r)
        return p.z > ground(p.x, p.y) + MOSS_CLEAR

    def dir_at(th, rho):
        edge = (1.0 + 0.14 * math.sin(2.0 * th + ph) + 0.10 * math.sin(3.0 * th + 2.0 * ph)
                + 0.07 * math.sin(7.0 * th + ph) + 0.05 * math.sin(11.0 * th + 3.0 * ph)
                + 0.035 * math.sin(23.0 * th + 5.0 * ph))
        ax = math.cos(th) * (stretch if math.cos(th) > 0.0 else 1.0)
        ay = math.sin(th) * (far if math.sin(th) < 0.0 else 1.0)
        rr = rho * edge * radius / r0
        return (d0 + e1 * (rr * ax) + e2 * (rr * ay)).normalized()

    # the outline: shrink each spoke until every ring on it clears the
    # crack and the soil
    fracs = [k / K for k in range(1, K + 1)]
    limit = []
    for m in range(Mseg):
        th = TAU * m / Mseg
        lo, hi = 0.0, 1.0
        if all(ok(dir_at(th, f)) for f in fracs):
            limit.append(1.0)
            continue
        for _ in range(24):
            mid = 0.5 * (lo + hi)
            if all(ok(dir_at(th, mid * f)) for f in fracs):
                lo = mid
            else:
                hi = mid
        limit.append(max(lo, 0.02))

    def lump(th, rho):
        """Hummocks: the cushion's height over the stone, 0.5..1.2 of its
        nominal thickness."""
        f = smoothstep(rho, 0.0, 0.45)
        return (0.80 + 0.13 * math.sin(3.0 * th + ph) * math.cos(6.0 * rho + ph)
                + f * (0.11 * math.sin(7.0 * th + 2.0 * ph) * math.sin(9.0 * rho + ph)
                       + 0.10 * math.sin(13.0 * th + ph) * math.cos(17.0 * rho + 2.0 * ph)
                       + 0.07 * math.sin(21.0 * th + 3.0 * ph) * math.sin(26.0 * rho)))

    Rm = rock.M.to_3x3()
    tone = hash01(idx, 9, 2)
    top_rings, bot_rings, lumps = [], [], []
    for k in range(1, K + 1):
        rho = k / K
        tr, br, lr = [], [], []
        for m in range(Mseg):
            th = TAU * m / Mseg
            d = dir_at(th, rho * limit[m])
            p, fn, _i, _dd = tree.find_nearest(rock.point(d))
            nrm = rock.normal(d)
            if fn.dot(nrm) < 0.0:
                fn = -fn
            nrm = (nrm + fn).normalized()
            lr.append(lump(th, rho) if k < K else 0.5)
            if k == K:
                v = B.vert(p + nrm * (lift - MOSS_TUCK), ring=k)
                tr.append(v)
                br.append(v)
            else:
                t = thick * max(0.0, 1.0 - rho * rho) ** 0.35 * lump(th, rho)
                tr.append(B.vert(p + nrm * (t + lift), ring=k))
                if k in (K // 2, K - 1):
                    br.append(B.vert(p - nrm * (MOSS_BITE * (0.6 + 1.2 * (1.0 - rho)) - lift),
                                     ring=-1))
                else:
                    br.append(None)
        top_rings.append(tr)
        bot_rings.append(br)
        lumps.append(lr)
    p0, f0, _i, _dd = tree.find_nearest(rock.point(d0))
    n0 = rock.normal(d0)
    if f0.dot(n0) < 0.0:
        f0 = -f0
    n0 = (n0 + f0).normalized()
    ct = B.vert(p0 + n0 * (thick * lump(0.0, 0.0) + lift), ring=0)
    cb = B.vert(p0 - n0 * (1.8 * MOSS_BITE - lift), ring=-1)
    ident = 700 + idx
    def zone(a, b):
        # a top face's zone: 0.5 in a hollow to 1 on a hummock (0 marks the
        # underside), so the shader darkens the cushion into its hollows
        return 0.5 + 0.5 * min(1.0, max(0.0, (0.5 * (a + b) - 0.55) / 0.55))

    for m in range(Mseg):
        q = (m + 1) % Mseg
        B.face((top_rings[0][m], top_rings[0][q], ct), MOSS_IDX, tone, P_MOSS, ident,
               zone=zone(lumps[0][m], lumps[0][q]))
    for kk, (r0_, r1_) in enumerate(zip(top_rings, top_rings[1:])):
        for m in range(Mseg):
            q = (m + 1) % Mseg
            B.face((r0_[m], r1_[m], r1_[q], r0_[q]), MOSS_IDX, tone, P_MOSS, ident,
                   zone=zone(lumps[kk][m], lumps[kk + 1][q]))
    bots = [br for br in bot_rings if br[0] is not None]
    for m in range(Mseg):
        q = (m + 1) % Mseg
        B.face((bots[0][q], bots[0][m], cb), MOSS_IDX, tone, P_MOSS, ident, zone=0.0)
    for r0_, r1_ in zip(bots, bots[1:]):
        for m in range(Mseg):
            q = (m + 1) % Mseg
            B.face((r0_[q], r1_[q], r1_[m], r0_[m]), MOSS_IDX, tone, P_MOSS, ident, zone=0.0)


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
            x = SOIL_C[0] + SOIL_A[0] * X * wob
            y = SOIL_C[1] + SOIL_A[1] * Y * wob
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


def add_rock(B, rock_mesh, tone):
    verts = []
    for p, c in zip(rock_mesh.world(), rock_mesh.crack):
        v = B.vert(p)
        v[B.crack] = min(1.0, c / CRACK_D)
        verts.append(v)
    for q in rock_mesh.quads:
        a, b, c, d = (verts[i] for i in q)
        crack = sum(rock_mesh.crack[i] > 0.02 for i in q) >= 3
        z = 1.0 if crack else 0.0
        # split on the short diagonal: a flat facet, and a ray lands on the
        # face actually shipped
        if (a.co - c.co).length <= (b.co - d.co).length:
            B.face((a, b, c), ROCK_IDX, tone, P_ROCK, 1, zone=z)
            B.face((a, c, d), ROCK_IDX, tone, P_ROCK, 1, zone=z)
        else:
            B.face((a, b, d), ROCK_IDX, tone, P_ROCK, 1, zone=z)
            B.face((b, c, d), ROCK_IDX, tone, P_ROCK, 1, zone=z)


LITTER_SIDE = ((0.07, 0.10), (0.18, 0.21), (0.32, 0.28), (0.48, 0.30), (0.64, 0.27), (0.78, 0.20),
               (0.90, 0.11))
LITTER_MID = (0.35, 0.68)


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


def add_leaf(B, base, e1, e3, L, tone, part, key, mat, droop, fold, bottom=0.010, curlup=0.0):
    """A beech leaf: one closed, thin shell. Its wavy ovate rim is shared by
    a top and a bottom surface, each zipped to its own midrib."""
    e2 = e3.cross(e1)
    wob = [0.88 + 0.24 * hash01(key, 7, k) for k in range(16)]

    def P(x, y, lift=0.0):
        return base + e1 * (x * L) + e2 * (y * L) + e3 * ((fold * abs(y) + curlup * y * y
                                                           - droop * x * x + lift) * L)

    vb = B.vert(base, tip=0.0, luv=(0.5, 0.0))
    va = B.vert(P(1.0, 0.0), tip=1.0, luv=(0.5, 1.0))
    sides = []
    for sg, off in ((1.0, 0), (-1.0, 8)):
        run = []
        for k, (x, y) in enumerate(LITTER_SIDE):
            yy = sg * y * wob[k + off] * (1.0 + 0.06 * math.sin(9.0 * x + key))
            run.append(B.vert(P(x, yy), tip=x, luv=(0.5 + yy, x)))
        sides.append(run)
    mids = []
    for lift in (0.010, -bottom):
        mids.append([B.vert(P(x, 0.0, lift), tip=x, luv=(0.5, x)) for x in LITTER_MID])
    xa = [0.0] + [x for x, _y in LITTER_SIDE] + [1.0]
    xm = [0.0] + list(LITTER_MID) + [1.0]
    faces = []
    for run in sides:
        A = [vb] + run + [va]
        for mi, mid in enumerate(mids):
            M = [vb] + mid + [va]
            for tri in zipper(A, M, xa, xm):
                faces.append(B.face(tri, mat, tone, part, int(key), -1, zone=float(mi)))
    B.finish_luv(faces)
    return [vb, va] + [v for run in sides for v in run] + [v for run in mids for v in run]


def add_leaflet(B, base, e1, e3, L, tone, ident, parent, key):
    """A wood-sorrel leaflet: a heart, notched at its tip, folded down its
    midrib. One closed shell fanned from a centre vertex above and below."""
    e2 = e3.cross(e1)
    outline = ((0.10, 0.10), (0.30, 0.34), (0.55, 0.50), (0.80, 0.52), (0.97, 0.30))
    notch = (0.86, 0.0)

    def P(x, y, lift=0.0):
        return base + e1 * (x * L) + e2 * (y * L) + e3 * ((-0.06 * abs(y) + lift) * L)

    loop = [B.vert(base)]
    loop += [B.vert(P(x, y * (0.95 + 0.1 * hash01(key, k, 1)))) for k, (x, y) in enumerate(outline)]
    loop.append(B.vert(P(*notch)))
    loop += [B.vert(P(x, -y * (0.95 + 0.1 * hash01(key, k, 2))))
             for k, (x, y) in reversed(list(enumerate(outline)))]
    ct = B.vert(P(0.50, 0.0, 0.015))
    cb = B.vert(P(0.50, 0.0, -0.012))
    for i in range(len(loop)):
        a, b = loop[i], loop[(i + 1) % len(loop)]
        B.face((a, b, ct), SORREL_IDX, tone, P_LEAFLET, ident, parent, zone=0.0)
        B.face((b, a, cb), SORREL_IDX, tone, P_LEAFLET, ident, parent, zone=1.0)
    return loop + [ct, cb]


def settle(verts, G, sink):
    """Drop a lying body so its most-buried vertex is ``sink`` under the soil."""
    lift = min(v.co.z - G.z(v.co.x, v.co.y) for v in verts)
    for v in verts:
        v.co.z -= lift + sink


def build_cover(B, plan, G, flags):
    cov = plan["cover"]
    lift = FLOAT_COVER if flags["float_cover"] else 0.0
    for k, (x, y, yaw, L, tone, tilt) in enumerate(cov["litter"]):
        c, nrm = G.hit(x, y)
        e1 = Vector((math.cos(yaw), math.sin(yaw), 0.0))
        e1 = (e1 - nrm * e1.dot(nrm)).normalized()
        e3 = (nrm * math.cos(tilt) + nrm.cross(e1) * math.sin(tilt)).normalized()
        base = c - e1 * (0.45 * L) + e3 * 0.002
        vs = add_leaf(B, base, e1, e3, L, tone, P_LITTER, 1000 + k, LITTER_IDX,
                      droop=-0.05 + 0.08 * hash01(k, 5, 1), fold=0.05 + 0.08 * hash01(k, 5, 2),
                      curlup=0.25 * hash01(k, 5, 3))
        settle(vs, G, REST_SINK - lift)
    for k, (x, y, r, yaw, tone, lumps) in enumerate(cov["pebbles"]):
        c = Vector((x, y, G.z(x, y)))
        ax = (r * 1.25, r * 0.95, r * 0.62)
        vs = add_blob(B, c, ax, 2, lumps, ROCK_IDX, 0.2 + 0.6 * tone, P_PEBBLE, 1100 + k)
        rot = Matrix.Rotation(yaw, 3, "Z")
        for v in vs:
            v.co = c + rot @ (v.co - c)
        settle(vs, G, REST_SINK - lift)
    set_leaflets = []
    cos_sep = math.cos(LEAFLET_SEP)
    for k, (x, y, leaves) in enumerate(cov["sorrel"]):
        for m, lf in enumerate(leaves):
            ident = 1200 + 10 * k + m
            a = lf["az"]
            hd = Vector((math.cos(a), math.sin(a), 0.0))
            x0 = x + hd.x * 0.012 * m
            y0 = y + hd.y * 0.012 * m
            g = G.z(x0, y0)
            b0 = Vector((x0, y0, g - SORREL_BURY + lift))
            top = Vector((x0, y0, g)) + (UP + hd * lf["lean"]).normalized() * lf["h"]
            mid = b0.lerp(top, 0.6) + hd * (0.012 + 0.01 * lf["lean"])
            pts = [b0, b0.lerp(mid, 0.5), mid, top]
            add_tube(B, pts, [0.0013, 0.0012, 0.0011, 0.0010], 4, SORREL_IDX, lf["tone"],
                     P_SORREL, ident, -1, phase=a)
            for j in range(3):
                ang = lf["spin"] + TAU * j / 3.0
                d = Vector((math.cos(ang), math.sin(ang),
                            -0.10 - 0.22 * j - 0.08 * hash01(ident, j, 3))).normalized()
                e30 = (UP - d * UP.dot(d)).normalized()
                r0 = 0.12 * (j - 1) + 0.05 * hash01(ident, j, 4)
                c = top + d * (0.5 * lf["L"])
                near = [n for q, n in set_leaflets if (q - c).length < 0.08]
                for step in range(41):
                    r = r0 + ((step + 1) // 2) * 0.05 * (1.0 if step % 2 else -1.0)
                    e3 = rotate_about(e30, d, r)
                    if all(abs(e3.dot(n)) < cos_sep for n in near):
                        break
                set_leaflets.append((c, e3))
                add_leaflet(B, top - UP * 0.0020 - d * 0.0004, d, e3, lf["L"], lf["tone"], ident * 10 + j,
                            ident, ident * 10.0 + j)
    for k, (x, y, yaw, L, tone) in enumerate(cov["twigs"]):
        h = Vector((math.cos(yaw), math.sin(yaw), 0.0))
        s = Vector((-h.y, h.x, 0.0))
        pts, main_pts = [], []
        for i in range(8):
            t = i / 7.0
            q = Vector((x, y, 0.0)) + h * (L * (t - 0.5)) + s * (0.025 * math.sin(2.6 * t * math.pi + tone))
            main_pts.append(Vector((q.x, q.y, G.z(q.x, q.y) + 0.010)))
        vs = add_tube(B, main_pts, [0.011 * (1.0 - 0.5 * i / 7.0) for i in range(8)], 6, TWIG_IDX,
                      tone, P_TWIG, 1300 + k, jag=[(0.8, 0.004), (1.0, -0.002), (0.7, 0.005)])
        b0 = main_pts[3]
        side = [b0, b0 + (h * 0.5 + s * 0.9).normalized() * 0.05, b0 + (h * 0.7 + s * 0.8).normalized() * 0.11]
        side = [side[0]] + [Vector((p.x, p.y, G.z(p.x, p.y) + 0.002)) for p in side[1:]]
        settle(vs, G, REST_SINK - lift)
        vs = add_tube(B, side, [0.0070, 0.0055, 0.0040], 5, TWIG_IDX, tone, P_TWIG, 1300 + k)
        settle(vs, G, REST_SINK - lift)


# --------------------------------------------------------------------------
# The whole mesh
# --------------------------------------------------------------------------

def build_mesh(name, plan, detail="low", **flags):
    bm = bmesh.new()
    try:
        B = Builder(bm)
        add_soil(B)
        # a temp tree for ray casts needs face normals first
        bm.normal_update()
        G = Ground(BVHTree.FromBMesh(bm))
        rock = Rock(plan)
        place_rock(rock, flags["perch_rock"])
        rm = RockMesh(rock, ROCK_N_HIGH if detail == "high" else ROCK_N)
        add_rock(B, rm, 0.45)
        # the moss snaps to the stone as built: a tree of the shipped faces
        tri_pts = rm.world()
        tri = []
        for q in rm.quads:
            a, b, c, d = q
            if (tri_pts[a] - tri_pts[c]).length <= (tri_pts[b] - tri_pts[d]).length:
                tri += [(a, b, c), (a, c, d)]
            else:
                tri += [(a, b, d), (b, c, d)]
        rtree = BVHTree.FromPolygons([tuple(p) for p in tri_pts], tri)
        lift = FLOAT_MOSS if flags["float_moss"] else 0.0
        for i, spec in enumerate(MOSS):
            add_moss(B, rock, rtree, spec, i, soil_height, lift, flags["sunny_moss"])

        # the crown
        kc = plan["knob_c"] + (UP * LIFT_CROWN if flags["lift_crown"] else Vector())
        add_blob(B, kc, KNOB_R, 3, plan["knob_lumps"], ROOT_IDX, 0.4, P_KNOB, KNOB_ID)
        for st in plan["stubs"]:
            add_stub(B, st, plan["knob_c"])
        taper_id = taper_frond(plan)
        shift = Vector()
        if flags["perch_crack_fern"]:
            n = plan["crack_frame"][2]
            shift = Vector((n.x, n.y, 0.0)).normalized() * CRACK_SHIFT
        add_blob(B, plan["cknob_c"] + shift, (CKNOB_R, CKNOB_R, CKNOB_R * 0.8), 2,
                 plan["cknob_lumps"], ROOT_IDX, 0.6, P_CKNOB, CKNOB_ID)
        for fr in plan["fronds"]:
            if fr["crack"] and shift.length:
                fr = dict(fr)
                fr["base"] = fr["base"] + shift
            add_frond(B, fr, flags, taper_id, detail)
        for cr in plan["crosiers"]:
            add_crosier(B, cr, flags, detail)
        build_cover(B, plan, G, flags)

        triangulate_ngons(bm)
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        cav = bm.verts.layers.float.new("Cavity")
        for v in bm.verts:
            if not v.link_faces or v.link_faces[0].material_index != ROCK_IDX:
                continue
            acc = 0.0
            for e in v.link_edges:
                w = e.other_vert(v).co - v.co
                ln = w.length
                if ln > 1e-9:
                    acc += w.dot(v.normal) / ln
            v[cav] = max(-1.0, min(1.0, 4.0 * acc / max(1, len(v.link_edges))))
        # Everything smooth-shaded, with every material boundary and every
        # fold sharper than its crease a hard edge: the stone's cleavage
        # edges and crack lips, a pinna's rim where its two surfaces meet.
        crease = {ROCK_IDX: 38.0, FROND_IDX: 55.0, LITTER_IDX: 55.0, SORREL_IDX: 55.0}
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(crease.get(mats.pop(), 62.0))
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


def build_collider_source(name, plan):
    """The boulder alone, coarse: players walk through the ferns."""
    bm = bmesh.new()
    try:
        rock = Rock(plan)
        rock.set_matrix(plan["rock_M"])
        for p in RockMesh(rock, COLLIDER_N).world():
            bm.verts.new(p)
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


def coord_z(nt, coord):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    return sep.outputs["Z"]


def normal_xyz(nt):
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
    return sep.outputs


def leaf_uv(nt):
    luv = nt.nodes.new("ShaderNodeUVMap")
    luv.uv_map = "LeafUV"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(luv.outputs["UV"], sep.inputs["Vector"])
    return sep.outputs


def add_bump(nt, bsdf, height, strength, distance):
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def translucent(nt, bsdf, rgb, amount):
    """Mix a translucent lobe under the surface: a thin leaf lit from the
    other side."""
    out = nt.nodes["Material Output"]
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = (*rgb, 1.0)
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = amount
    nt.links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])


def rock_material():
    mat, nt, bsdf, coord = surface("Gritstone")
    # A cool grey woodland gritstone: isotropic mottling, fine grain driving
    # roughness and a small bump, a seeded tone per stone (the pebbles share
    # it), green algae in the hollows and down the shaded foot, pale lichen
    # crust on the upper faces, and fresh, paler stone in the crack.
    tone = attr(nt, "Tone")
    mottle = noise(nt, coord, 2.6, 6.0, 0.62)
    col = ramp(nt, mottle, ((0.25, (0.070, 0.066, 0.058)), (0.50, (0.130, 0.122, 0.108)),
                            (0.78, (0.200, 0.188, 0.165))))
    col = mix_color(nt, col, (0.150, 0.118, 0.085), remap(nt, tone, 0.2, 0.9, 0.0, 0.45))
    blot = noise(nt, coord, 7.5, 4.0, 0.6)
    col = mix_color(nt, col, (0.045, 0.045, 0.042), remap(nt, blot, 0.48, 0.66, 0.0, 0.65))
    grain = noise(nt, coord, 160.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.050, 0.050, 0.050), remap(nt, grain, 0.40, 0.70, 0.45, 0.0))
    # lichen: pale sage rosettes, and a few orange ones on the upper faces
    ros = voronoi(nt, mapping(nt, coord, scale=(1.0, 1.0, 1.0)), 8.0)
    sage = math_node(nt, "MULTIPLY", remap(nt, ros, 0.20, 0.12, 0.0, 0.85),
                     remap(nt, noise(nt, coord, 3.0, 2.0, 0.5), 0.45, 0.60, 0.0, 1.0))
    col = mix_color(nt, col, (0.30, 0.32, 0.25), sage)
    ros2 = voronoi(nt, mapping(nt, coord, scale=(1.3, 1.1, 1.2)), 13.0)
    ora = math_node(nt, "MULTIPLY", remap(nt, ros2, 0.10, 0.05, 0.0, 0.9),
                    remap(nt, noise(nt, coord, 2.2, 2.0, 0.5), 0.58, 0.66, 0.0, 1.0))
    cav = attr(nt, "Cavity")
    nx = normal_xyz(nt)
    algae = math_node(nt, "MAXIMUM", remap(nt, cav, 0.05, 0.40, 0.0, 0.8),
                      math_node(nt, "MULTIPLY", remap(nt, nx["Y"], -0.2, -0.8, 0.0, 0.55),
                                remap(nt, noise(nt, coord, 5.0, 4.0, 0.6), 0.40, 0.60, 0.0, 1.0)))
    col = mix_color(nt, col, (0.050, 0.075, 0.030), algae)
    streak = noise(nt, mapping(nt, coord, scale=(14.0, 14.0, 1.2)), 1.0, 4.0, 0.55)
    col = mix_color(nt, col, (0.030, 0.031, 0.029), remap(nt, streak, 0.50, 0.68, 0.0, 0.60))
    low = remap(nt, coord_z(nt, coord), 0.18, 0.55, 0.55, 0.0)
    col = mix_color(nt, col, (0.040, 0.050, 0.024), low)
    ora = math_node(nt, "MULTIPLY", ora, remap(nt, nx["Z"], 0.1, 0.6, 0.0, 1.0))
    col = mix_color(nt, col, (0.42, 0.22, 0.05), ora)
    crack = attr(nt, "Crack")
    col = mix_color(nt, col, (0.018, 0.017, 0.016), remap(nt, crack, 0.35, 0.95, 0.0, 0.9))
    col = mix_color(nt, col, (0.30, 0.27, 0.23), math_node(nt, "MULTIPLY", attr(nt, "Zone"),
                                                           remap(nt, crack, 0.0, 0.3, 0.45, 0.0)))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, grain, 0.3, 0.7, 0.72, 0.92), bsdf.inputs["Roughness"])
    add_bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "MULTIPLY", mottle, 0.5),
                                 math_node(nt, "MULTIPLY", grain, 0.35)), 0.35, 0.01)
    return mat


def moss_material():
    mat, nt, bsdf, coord = surface("Moss")
    # A deep, velvety cushion: bright new tips over dark stems, lumpier
    # green in hummocks, a few browned patches, the underside dark.
    tone = attr(nt, "Tone")
    base = ramp(nt, tone, ((0.0, (0.040, 0.085, 0.012)), (0.5, (0.060, 0.115, 0.016)),
                           (1.0, (0.080, 0.140, 0.020))))
    fuzz = noise(nt, coord, 420.0, 3.0, 0.7)
    tufts = noise(nt, coord, 90.0, 4.0, 0.6)
    patchy = noise(nt, coord, 9.0, 3.0, 0.5)
    col = mix_color(nt, base, (0.050, 0.060, 0.018), remap(nt, patchy, 0.40, 0.65, 0.45, 0.0))
    col = mix_color(nt, col, (0.014, 0.028, 0.006), remap(nt, fuzz, 0.30, 0.70, 0.75, 0.0))
    col = mix_color(nt, col, (0.12, 0.20, 0.030), remap(nt, tufts, 0.50, 0.75, 0.0, 0.55))
    dry = noise(nt, coord, 16.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.13, 0.10, 0.04), remap(nt, dry, 0.66, 0.76, 0.0, 0.35))
    # the cushion darkens into its hollows (the lumps' own height over the stone)
    # small hummocks: cells domed up, dark crevices between them
    warp = nt.nodes.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value = 5.0
    warp.inputs["Detail"].default_value = 2.0
    nt.links.new(coord, warp.inputs["Vector"])
    wv = nt.nodes.new("ShaderNodeVectorMath")
    wv.operation = "MULTIPLY_ADD"
    nt.links.new(warp.outputs["Color"], wv.inputs[0])
    wv.inputs[1].default_value = (0.09, 0.09, 0.09)
    nt.links.new(coord, wv.inputs[2])
    big = voronoi(nt, wv.outputs["Vector"], 11.0, "F1")
    small = voronoi(nt, wv.outputs["Vector"], 29.0, "F1")
    cells = math_node(nt, "MINIMUM", math_node(nt, "MULTIPLY", big, 1.25), small)
    dome = remap(nt, cells, 0.0, 0.62, 1.0, 0.0)
    col = mix_color(nt, (0.016, 0.026, 0.008), col, remap(nt, cells, 0.62, 0.30, 0.35, 1.0))
    col = mix_color(nt, col, (0.09, 0.15, 0.024), remap(nt, cells, 0.22, 0.0, 0.0, 0.18))
    col = mix_color(nt, (0.020, 0.028, 0.010), col, attr(nt, "Zone"))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    height = math_node(nt, "ADD", math_node(nt, "MULTIPLY", dome, 2.5),
                       math_node(nt, "ADD", fuzz, math_node(nt, "MULTIPLY", tufts, 0.8)))
    add_bump(nt, bsdf, height, 1.0, 0.006)
    return mat


def frond_material():
    mat, nt, bsdf, coord = surface("Frond")
    # A fern's pinnae: rich green on top with a waxy sheen, each frond and
    # pinna its own shade, paler at the pinnule tips; the underside paler
    # still with rows of rusty sori beside the costa.
    tone = attr(nt, "Tone")
    top = ramp(nt, tone, ((0.0, (0.030, 0.085, 0.012)), (0.5, (0.050, 0.125, 0.018)),
                          (1.0, (0.085, 0.165, 0.026))))
    uvs = leaf_uv(nt)
    across = math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", uvs["X"], 0.5), 0.0)
    col = mix_color(nt, top, (0.13, 0.22, 0.045), remap(nt, across, 0.18, 0.46, 0.0, 0.45))
    vein = remap(nt, across, 0.0, 0.03, 1.0, 0.0)
    col = mix_color(nt, col, (0.10, 0.17, 0.05), math_node(nt, "MULTIPLY", vein, 0.6))
    speck = noise(nt, coord, 60.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.025, 0.060, 0.010), remap(nt, speck, 0.35, 0.7, 0.0, 0.35))
    under = ramp(nt, tone, ((0.0, (0.090, 0.150, 0.040)), (1.0, (0.130, 0.195, 0.060))))
    sori = voronoi(nt, coord, 260.0)
    band = math_node(nt, "MULTIPLY", remap(nt, across, 0.05, 0.10, 0.0, 1.0),
                     remap(nt, across, 0.18, 0.13, 0.0, 1.0))
    under = mix_color(nt, under, (0.20, 0.10, 0.035),
                      math_node(nt, "MULTIPLY", band, remap(nt, sori, 0.25, 0.12, 0.0, 0.9)))
    col = mix_color(nt, col, under, attr(nt, "Zone"))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.48
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    add_bump(nt, bsdf, vein, 0.2, 0.004)
    translucent(nt, bsdf, (0.10, 0.20, 0.03), 0.28)
    return mat


def stipe_material():
    mat, nt, bsdf, coord = surface("Stipe")
    # The stalk: dark and densely clad in rusty scales at the base, green up
    # the rachis, grooved above.
    tip = attr(nt, "Tip")
    tone = attr(nt, "Tone")
    green = ramp(nt, tone, ((0.0, (0.060, 0.120, 0.020)), (1.0, (0.095, 0.160, 0.032))))
    scales = noise(nt, coord, 320.0, 2.0, 0.6)
    brown = ramp(nt, scales, ((0.35, (0.050, 0.025, 0.010)), (0.65, (0.230, 0.120, 0.045))))
    col = mix_color(nt, brown, green, remap(nt, tip, 0.06, 0.20, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    return mat


def crozier_material():
    mat, nt, bsdf, coord = surface("Crozier")
    # A young frond still rolled: pale green, furred with golden-brown
    # scales thickest on the coil.
    tip = attr(nt, "Tip")
    scales = noise(nt, coord, 260.0, 3.0, 0.6)
    col = mix_color(nt, (0.11, 0.19, 0.04), (0.30, 0.17, 0.06), remap(nt, tip, 0.05, 0.25, 0.25, 0.75))
    col = mix_color(nt, col, (0.10, 0.05, 0.015), remap(nt, scales, 0.45, 0.70, 0.0, 0.7))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.7
    add_bump(nt, bsdf, scales, 0.5, 0.003)
    return mat


def rootstock_material():
    mat, nt, bsdf, coord = surface("Rootstock")
    # The crown's rootstock and old stipe bases: dark, fibrous, shaggy with
    # papery brown scales.
    fib = noise(nt, mapping(nt, coord, scale=(40.0, 40.0, 140.0)), 1.0, 4.0, 0.6)
    col = ramp(nt, fib, ((0.30, (0.030, 0.018, 0.010)), (0.60, (0.120, 0.070, 0.030)),
                         (0.85, (0.250, 0.150, 0.065))))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    add_bump(nt, bsdf, fib, 0.7, 0.004)
    return mat


def soil_material():
    mat, nt, bsdf, coord = surface("Humus")
    # Dark woodland humus: crumbs, leaf fragments and a film of moss in the
    # hollows.
    clods = noise(nt, coord, 6.0, 6.0, 0.62)
    crumbs = noise(nt, coord, 90.0, 3.0, 0.6)
    col = ramp(nt, clods, ((0.30, (0.030, 0.022, 0.015)), (0.55, (0.060, 0.043, 0.028)),
                           (0.80, (0.095, 0.070, 0.046))))
    col = mix_color(nt, col, (0.015, 0.011, 0.008), remap(nt, crumbs, 0.35, 0.55, 0.6, 0.0))
    frags = voronoi(nt, coord, 40.0)
    col = mix_color(nt, col, (0.16, 0.085, 0.035), remap(nt, frags, 0.06, 0.02, 0.0, 0.55))
    film = noise(nt, coord, 2.4, 4.0, 0.55)
    col = mix_color(nt, col, (0.040, 0.066, 0.018), remap(nt, film, 0.50, 0.64, 0.0, 0.7))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    add_bump(nt, bsdf, math_node(nt, "ADD", clods, math_node(nt, "MULTIPLY", crumbs, 0.6)), 0.5, 0.01)
    return mat


def litter_material():
    mat, nt, bsdf, coord = surface("BeechLitter")
    # Last autumn's beech leaves: copper to russet, darker where rotting,
    # parallel veins from LeafUV.
    tone = attr(nt, "Tone")
    base = ramp(nt, tone, ((0.0, (0.040, 0.024, 0.012)), (0.35, (0.080, 0.042, 0.018)),
                           (0.65, (0.150, 0.066, 0.022)), (0.85, (0.190, 0.090, 0.028)),
                           (1.0, (0.150, 0.110, 0.045))))
    blot = noise(nt, coord, 30.0, 3.0, 0.6)
    col = mix_color(nt, base, (0.05, 0.030, 0.015), remap(nt, blot, 0.55, 0.75, 0.0, 0.6))
    uvs = leaf_uv(nt)
    across = math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", uvs["X"], 0.5), 0.0)
    lat = math_node(nt, "SINE", math_node(nt, "MULTIPLY", math_node(
        nt, "SUBTRACT", uvs["Y"], math_node(nt, "MULTIPLY", across, 0.9)), TAU * 5.0), 0.0)
    vein = math_node(nt, "MAXIMUM", remap(nt, across, 0.0, 0.02, 1.0, 0.0),
                     remap(nt, lat, 0.85, 1.0, 0.0, 0.5))
    col = mix_color(nt, col, (0.08, 0.04, 0.015), math_node(nt, "MULTIPLY", vein, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.75
    add_bump(nt, bsdf, vein, 0.3, 0.004)
    return mat


def twig_material():
    mat, nt, bsdf, coord = surface("Twig")
    streak = noise(nt, mapping(nt, coord, scale=(60.0, 60.0, 60.0)), 1.0, 5.0, 0.6)
    col = ramp(nt, streak, ((0.35, (0.050, 0.035, 0.024)), (0.65, (0.125, 0.092, 0.062))))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    add_bump(nt, bsdf, streak, 0.4, 0.004)
    return mat


def sorrel_material():
    mat, nt, bsdf, coord = surface("WoodSorrel")
    # Wood sorrel: fresh, light green, a purple flush under the leaflets.
    tone = attr(nt, "Tone")
    top = ramp(nt, tone, ((0.0, (0.090, 0.200, 0.040)), (1.0, (0.140, 0.260, 0.055))))
    col = mix_color(nt, top, (0.13, 0.06, 0.10), math_node(nt, "MULTIPLY", attr(nt, "Zone"), 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    translucent(nt, bsdf, (0.12, 0.24, 0.05), 0.25)
    return mat


def piece_materials():
    """Ten slots, in index order: shared by the check and the render."""
    return (rock_material(), moss_material(), frond_material(), stipe_material(),
            crozier_material(), rootstock_material(), soil_material(), litter_material(),
            twig_material(), sorrel_material())


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


def classify(me):
    groups = shells(me)
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(p)
    part_of = face_vals(me, "Part")
    ident_of = face_vals(me, "Ident")
    parent_of = face_vals(me, "Parent")
    parts = [Shell(me, g, polys[i], part_of, ident_of, parent_of) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups, "cap_of": face_vals(me, "Cap"),
           "zone_of": face_vals(me, "Zone", float)}

    def of(*kinds):
        return [s for s in parts if s.part in kinds]

    for key, kinds in (("soil", (P_SOIL,)), ("rock", (P_ROCK,)), ("moss", (P_MOSS,)),
                       ("knob", (P_KNOB,)), ("cknob", (P_CKNOB,)), ("stipes", (P_STIPE,)),
                       ("pinnae", (P_PINNA,)), ("crosiers", (P_CROSIER,)), ("stubs", (P_STUB,)),
                       ("cover", COVER_PARTS), ("leaflets", (P_LEAFLET,))):
        out[key] = of(*kinds)
    return out


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


def ray_down(tree, x, y):
    loc, _n, _i, _d = tree.ray_cast(Vector((x, y, 12.0)), Vector((0.0, 0.0, -1.0)), 30.0)
    return None if loc is None else loc.z


def sector_seal(pts, soil):
    """Per sector about the plan centroid, the most-buried flank vertex
    under the soil straight above it (flank: at least FLANK_R of the
    sector's plan reach)."""
    return flank_bury(pts, lambda x, y: ray_down(soil.tree, x, y))


def rooted_audit(me, cls):
    """Stipes, crosiers and stubs: the shallowest base-cap vertex inside
    their rootstock. Pinnae: the base (Tip 0) vertex inside the rachis
    tagged as its Parent. The crown's rootstock sealed in the soil."""
    cap_of = cls["cap_of"]
    tip = vert_vals(me, "Tip", float)
    knobs = {s.ident: s for s in cls["knob"] + cls["cknob"]}
    stalk_bites = []
    for s in cls["stipes"] + cls["crosiers"] + cls["stubs"]:
        host = knobs.get(s.parent)
        cap = set()
        for p in s.polys:
            if cap_of[p.index] == 1:
                cap.update(p.vertices)
        if host is None or not cap:
            stalk_bites.append(-9.0)
            continue
        stalk_bites.append(min(signed_depth(host.tree, me.vertices[i].co) for i in cap))
    rachis = {s.ident: s for s in cls["stipes"]}
    pinna_bites = []
    for s in cls["pinnae"]:
        host = rachis.get(s.parent)
        if host is None:
            pinna_bites.append(-9.0)
            continue
        vi = min(s.verts, key=lambda i: tip[i])
        pinna_bites.append(signed_depth(host.tree, me.vertices[vi].co))
    knob_seal = [-9.0]
    if cls["knob"]:
        knob_seal = sector_seal(cls["knob"][0].pts, cls["soil"][0])
    return stalk_bites, pinna_bites, knob_seal


def moss_audit(me, cls):
    """Per moss vertex, its height over the stone along the stone's normal
    at the nearest point: the top surface (rings inside the rim) in the
    band; the rim and the underside inside the stone. Facing: the area
    share of top faces whose stone, under the face, faces up or into the
    shade (the hummocks' own facets face every way)."""
    rock = cls["rock"][0]
    ring = vert_vals(me, "Ring")
    zone_of = cls["zone_of"]
    tops, ins = [], []
    area = 0.0
    good = 0.0
    for s in cls["moss"]:
        top_v = set()
        rim_v = set()
        for p in s.polys:
            if zone_of[p.index] > 0.25:
                top_v.update(p.vertices)
                a = p.area
                area += a
                n = rock.tree.find_nearest(p.center)[1]
                if n.dot(UP) >= UP_MIN or n.dot(SHADE) >= SHADE_MIN:
                    good += a
        kmax = max(ring[i] for i in s.verts)
        for i in s.verts:
            co = me.vertices[i].co
            loc, nrm, _f, _d = rock.tree.find_nearest(co)
            h = (co - loc).dot(nrm)
            if i in top_v and 0 <= ring[i] < kmax:
                tops.append(h)
            else:
                ins.append(-h)
            if ring[i] == kmax:
                rim_v.add(i)
    return tops, ins, (good / area if area else 0.0)


def crack_fern_audit(cls):
    """The crack fern's rootstock: its deepest vertex inside the stone, and
    its centre in the cleft — outside the stone, with stone within reach on
    two opposite sides."""
    if not cls["cknob"]:
        return -9.0, False, 9.0
    ck = cls["cknob"][0]
    rock = cls["rock"][0]
    bite = max(signed_depth(rock.tree, q) for q in ck.pts)
    c = sum(ck.pts, Vector()) / len(ck.pts)
    in_void = not inside(rock.tree, c)
    best = 9.0
    for k in range(12):
        a = math.pi * k / 12.0
        d = Vector((math.cos(a), math.sin(a), 0.0))
        h1 = rock.tree.ray_cast(c, d, 1.0)
        h2 = rock.tree.ray_cast(c, -d, 1.0)
        if h1[0] is not None and h2[0] is not None:
            best = min(best, max(h1[3], h2[3]))
    return bite, in_void, best


def pinna_audit(me, cls):
    """Per frond: its pinnae sorted by station along the rachis (the base
    vertex projected on the rachis's ring centroids). Alternation: every
    pair of neighbours on opposite sides, and each gap over the same-side
    spacing in band. Taper: where the longest pinna stands on the blade,
    the tip pinnae's mean length and the lowest pinnae's over the longest."""
    ring = vert_vals(me, "Ring")
    tip = vert_vals(me, "Tip", float)
    by_frond = {}
    for s in cls["pinnae"]:
        by_frond.setdefault(s.parent, []).append(s)
    out = []
    for st in cls["stipes"]:
        pins = by_frond.get(st.ident, [])
        if len(pins) < 6:
            out.append({"n": len(pins)})
            continue
        rings = {}
        for vi in st.verts:
            rings.setdefault(ring[vi], []).append(me.vertices[vi].co)
        cs = [sum(rings[k], Vector()) / len(rings[k]) for k in sorted(rings)]
        acc = [0.0]
        for a, b in zip(cs, cs[1:]):
            acc.append(acc[-1] + (b - a).length)
        rows = []
        for s in pins:
            vb = min(s.verts, key=lambda i: tip[i])
            va = max(s.verts, key=lambda i: tip[i])
            pb = me.vertices[vb].co
            pa = me.vertices[va].co
            best, arc, tan = 9e9, 0.0, Vector((0.0, 0.0, 1.0))
            for i in range(len(cs) - 1):
                ab = cs[i + 1] - cs[i]
                t = min(max((pb - cs[i]).dot(ab) / max(ab.length_squared, 1e-12), 0.0), 1.0)
                d = (cs[i] + ab * t - pb).length
                if d < best:
                    best, arc, tan = d, acc[i] + ab.length * t, ab.normalized()
            ch = pa - pb
            lat = ch - tan * ch.dot(tan)
            rows.append((arc, (pa - pb).length, lat.normalized() if lat.length > 1e-9 else lat))
        rows.sort(key=lambda r: r[0])
        alt_ok = all(a[2].dot(b[2]) < 0.0 for a, b in zip(rows, rows[1:]))
        gaps = []
        for i in range(len(rows) - 2):
            span = rows[i + 2][0] - rows[i][0]
            gaps.append((rows[i + 1][0] - rows[i][0]) / span if span > 1e-9 else 0.0)
        s0, s1 = rows[0][0], rows[-1][0]
        lens = [r[1] for r in rows]
        lmax = max(lens)
        ui = [(r[0] - s0) / (s1 - s0) for r in rows]
        peak = ui[lens.index(lmax)]
        tipm = [ln for ln, uu in zip(lens, ui) if uu >= 0.8]
        out.append({"n": len(pins), "alt": alt_ok, "gap_lo": min(gaps), "gap_hi": max(gaps),
                    "peak": peak, "tip": sum(tipm) / len(tipm) / lmax,
                    "base": 0.5 * (lens[0] + lens[1]) / lmax})
    return out


def spiral_audit(me, cls):
    """Per fiddlehead: the centreline from its ring centroids; the total
    turning of the coil (from where it first bends past 30 degrees to its
    tip), and the mean curvature of the coil's inner third over its outer
    third, by arc length."""
    ring = vert_vals(me, "Ring")
    out = []
    for s in cls["crosiers"]:
        rings = {}
        for vi in s.verts:
            rings.setdefault(ring[vi], []).append(me.vertices[vi].co)
        cs = [sum(rings[k], Vector()) / len(rings[k]) for k in sorted(rings)]
        turn, kap, seg = [], [], []
        for a, b, c in zip(cs, cs[1:], cs[2:]):
            u1, u2 = (b - a), (c - b)
            ang = u1.angle(u2, 0.0)
            ln = 0.5 * (u1.length + u2.length)
            turn.append(ang)
            kap.append(ang / ln)
            seg.append(ln)
        cum = 0.0
        start = len(turn)
        for i, a in enumerate(turn):
            cum += a
            if cum > math.radians(30.0):
                start = max(0, i - 1)
                break
        coil_t = sum(turn[start:]) / TAU
        arcs = []
        acc = 0.0
        for ln in seg[start:]:
            acc += ln
            arcs.append(acc)
        total = arcs[-1] if arcs else 1.0
        k = kap[start:]
        outer = [kk for kk, a in zip(k, arcs) if a <= total / 3.0]
        inner = [kk for kk, a in zip(k, arcs) if a >= 2.0 * total / 3.0]
        ratio = (sum(inner) / len(inner)) / (sum(outer) / len(outer)) if inner and outer else 0.0
        out.append((coil_t, ratio))
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
    """Per cover shell its most-buried vertex under the soil; and the cover
    (sorrel leaflets included) joined to the soil."""
    soil = cls["soil"][0]
    rests = {}
    for s in cls["cover"]:
        deep = -9.0
        for p in s.pts:
            g = ray_down(soil.tree, p.x, p.y)
            if g is not None:
                deep = max(deep, g - p.z)
        rests.setdefault(s.part, []).append(deep)
    parts = [soil] + cls["cover"] + cls["leaflets"]
    roots = union_components(parts)
    loose = sum(1 for r in roots[1:] if r != roots[0])
    return rests, loose


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
    low = build_mesh("FernRockLow", plan, "low", **flags)
    high = build_mesh("FernRockHigh", plan, "high", **flags)
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
    if len(cls["rock"]) != 1 or len(cls["soil"]) != 1 or len(cls["knob"]) != 1:
        return (fail(f"rock/soil/rootstock not found: {len(cls['rock'])}/{len(cls['soil'])}/"
                     f"{len(cls['knob'])} shells", 3),) + none2
    n_fronds = len(plan["fronds"])
    n_pinnae = sum(len(f["pinnae"]) for f in plan["fronds"])
    n_stalks = n_fronds + CROSIERS + STUBS
    cov = plan["cover"]
    n_cover = len(cov["litter"]) + len(cov["pebbles"]) + sum(len(s[2]) for s in cov["sorrel"]) \
        + 2 * len(cov["twigs"])
    stalk_bites, pinna_bites, knob_seal = rooted_audit(low.data, cls)
    moss_tops, moss_ins, facing = moss_audit(low.data, cls)
    rock_seal = sector_seal(cls["rock"][0].pts, cls["soil"][0])
    ck_bite, ck_void, ck_reach = crack_fern_audit(cls)
    pins = pinna_audit(low.data, cls)
    spirals = spiral_audit(low.data, cls)
    rests, loose = cover_audit(cls)

    img, tex = setup_bake_image(low, rock_mat)
    if img is None:
        return (fail("no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "FernRockLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "FernRockLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("FernRockColSrc", plan)
    collider = convex_hull_collider(collider_src, "FernRockCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_fern_mossy_rock_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    fp = [p for p in pins if p.get("n", 0) >= 6]
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
    print(f"measured shells={len(cls['all'])} stipes={len(cls['stipes'])}/{n_fronds} "
          f"pinnae={len(cls['pinnae'])}/{n_pinnae} crosiers={len(cls['crosiers'])} "
          f"stubs={len(cls['stubs'])} moss={len(cls['moss'])} cover={len(cls['cover'])}/{n_cover} "
          f"leaflets={len(cls['leaflets'])} pinnae_unturned={plan['sep_failed']}")
    print(f"measured rooted stalk_bite min={min(stalk_bites):.4f} n={len(stalk_bites)} "
          f"pinna_bite min={min(pinna_bites):.4f} n={len(pinna_bites)} "
          f"knob_seal min={min(knob_seal):.4f} sectors={sum(1 for b in knob_seal if b >= KNOB_SEAL_EPS)}")
    print(f"measured moss top min={min(moss_tops):.4f} max={max(moss_tops):.4f} n={len(moss_tops)} "
          f"inside min={min(moss_ins):.4f} n={len(moss_ins)} facing={facing:.4f}")
    print(f"measured rock_seal min={min(rock_seal):.4f} sectors={sum(1 for b in rock_seal if b >= SEAL_EPS)}"
          f" all={[round(b, 3) for b in rock_seal]}")
    print(f"measured crack_fern bite={ck_bite:.4f} in_void={ck_void} walls={ck_reach:.4f}")
    if fp:
        print(f"measured pinnae fronds={len(fp)} alt={all(p['alt'] for p in fp)} "
              f"gap={min(p['gap_lo'] for p in fp):.3f}..{max(p['gap_hi'] for p in fp):.3f} "
              f"peak={min(p['peak'] for p in fp):.3f}..{max(p['peak'] for p in fp):.3f} "
              f"tip max={max(p['tip'] for p in fp):.3f} base max={max(p['base'] for p in fp):.3f}")
    print(f"measured spirals " + " ".join(f"{t:.3f}/{r:.3f}" for t, r in spirals))
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
    if (len(cls["stipes"]) != n_fronds or len(pinna_bites) != n_pinnae
            or len(stalk_bites) != n_stalks or min(stalk_bites) < STIPE_BITE_MIN
            or min(pinna_bites) < PINNA_BITE_MIN or min(knob_seal) < KNOB_SEAL_EPS):
        return (fail(f"rooted: {len(cls['stipes'])}/{n_fronds} fronds, {len(pinna_bites)}/"
                     f"{n_pinnae} pinnae, {len(stalk_bites)}/{n_stalks} stalks; shallowest stalk "
                     f"base {min(stalk_bites):.4f} m inside its rootstock (min {STIPE_BITE_MIN}), "
                     f"shallowest pinna base {min(pinna_bites):.4f} inside its rachis (min "
                     f"{PINNA_BITE_MIN}), rootstock's worst sector {min(knob_seal):.4f} under the "
                     f"soil (min {KNOB_SEAL_EPS})", 17),) + none2
    if (len(cls["moss"]) != len(MOSS) or min(moss_tops) < MOSS_BAND[0]
            or max(moss_tops) > MOSS_BAND[1] or min(moss_ins) < MOSS_IN_MIN):
        return (fail(f"moss seat: {len(cls['moss'])}/{len(MOSS)} cushions, top "
                     f"{min(moss_tops):.4f}..{max(moss_tops):.4f} m over the stone (band "
                     f"{MOSS_BAND}), rim and underside {min(moss_ins):.4f} inside it (min "
                     f"{MOSS_IN_MIN})", 18),) + none2
    if min(rock_seal) < SEAL_EPS:
        return (fail(f"boulder sealed: worst sector {min(rock_seal):.4f} m under the soil (min "
                     f"{SEAL_EPS}); {sum(1 for b in rock_seal if b >= SEAL_EPS)}/{SECTORS} sectors",
                     20),) + none2
    if facing < FACING_MIN:
        return (fail(f"moss facing: {facing:.4f} of the cushion faces up or into the shade (min "
                     f"{FACING_MIN})", 21),) + none2
    if ck_bite < CKNOB_BITE_MIN or not ck_void or ck_reach > CRACK_REACH:
        return (fail(f"crack fern: rootstock bites the stone {ck_bite:.4f} m (min {CKNOB_BITE_MIN}),"
                     f" centre in the cleft {ck_void}, walls within {ck_reach:.4f} m (max "
                     f"{CRACK_REACH})", 22),) + none2
    bad = [p for p in pins if p.get("n", 0) < 6 or not p["alt"]
           or not (ALT_BAND[0] <= p["gap_lo"] and p["gap_hi"] <= ALT_BAND[1])
           or not (PEAK_BAND[0] <= p["peak"] <= PEAK_BAND[1])
           or p["tip"] > TIP_RATIO_MAX or p["base"] > BASE_RATIO_MAX]
    if len(pins) != n_fronds or bad:
        b = bad[0] if bad else {}
        return (fail(f"pinnae: {len(bad)} of {len(pins)} fronds out of arrangement; first: {b} "
                     f"(gap band {ALT_BAND}, peak {PEAK_BAND}, tip <= {TIP_RATIO_MAX}, base <= "
                     f"{BASE_RATIO_MAX})", 23),) + none2
    if (len(spirals) != CROSIERS or min(t for t, _r in spirals) < SPIRAL_TURNS_MIN
            or min(r for _t, r in spirals) < SPIRAL_RATIO_MIN):
        return (fail(f"fiddleheads: {len(spirals)}/{CROSIERS}, coil turns "
                     f"{min(t for t, _r in spirals):.3f} (min {SPIRAL_TURNS_MIN}), inner/outer "
                     f"curvature {min(r for _t, r in spirals):.3f} (min {SPIRAL_RATIO_MIN})", 24),) + none2
    bands = {P_LITTER: REST_BAND, P_PEBBLE: REST_BAND, P_TWIG: REST_BAND, P_SORREL: SORREL_BAND}
    badc = [(k, round(v, 4)) for k, vs in rests.items() for v in vs
            if not (bands[k][0] <= v <= bands[k][1])]
    got = sum(len(v) for v in rests.values())
    if got != n_cover or badc or loose:
        return (fail(f"ground cover: {got}/{n_cover} pieces, out of band {badc[:6]}, {loose} shells "
                     f"not joined to the soil", 25),) + none2
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

    # Key, fill, rim and the warm wedge. The key's spread keeps it on the
    # piece instead of flooding the stage.
    light("Key", (-3.2, -4.0, 4.6), 232.0, 4.0, (1.0, 0.95, 0.88), spread=40.0)
    light("Fill", (4.6, -3.0, 0.8), 38.0, 8.0, (0.72, 0.82, 1.0))
    light("Rim", (-1.2, 3.0, 2.8), 140.0, 3.0, (0.62, 0.78, 1.0))
    light("Wedge", (2.8, 1.6, 1.4), 204.0, 5.0, (1.0, 0.72, 0.44),
          target=(1.6, WALL_Y - 1.2, 0.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.50, -0.86, 0.0)).normalized()
    cam.location = centre + view * 4.0 + Vector((0.0, 0.0, 0.72))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.08))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the fronds.
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 26
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return fail("render produced no file", 14)
    return 0


FLAG_NAMES = ("float_fronds", "lift_crown", "float_moss", "perch_rock", "sunny_moss",
              "perch_crack_fern", "flat_taper", "opposite_pinnae", "open_crozier", "float_cover")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--float-fronds", action="store_true")
    p.add_argument("--lift-crown", action="store_true")
    p.add_argument("--float-moss", action="store_true")
    p.add_argument("--perch-rock", action="store_true")
    p.add_argument("--sunny-moss", action="store_true")
    p.add_argument("--perch-crack-fern", action="store_true")
    p.add_argument("--flat-taper", action="store_true")
    p.add_argument("--opposite-pinnae", action="store_true")
    p.add_argument("--open-crozier", action="store_true")
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
    print("fern-mossy-rock OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
