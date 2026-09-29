"""Game-ready farm tractor in a muddy farmyard - a showcase piece, not an example.

Asserts budget conformance of a procedural mid-century utility tractor after
composing shipped pipeline pieces: bmesh construction, UVs, twelve materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

A patch of farmyard mud, two wheel ruts running through it and a puddle in
one of them. In the ruts stands a utility tractor (generic, no marks or
text): a cast-iron backbone (engine block, bell housing, gearbox and rear
axle centre housing with its trumpet housings); a pivoting front axle beam
on a pin through the front support's lugs, kingpins, spindles, a tie rod;
big rear wheels with chevron-lugged tyres on dished steel rims, clamp lugs
and cast-iron wheel weights; small ribbed front tyres; a grille shell with
its radiator and headlamps, a long bonnet over the engine, a fuel tank and
filler cap, a dash with gauges; a vertical exhaust stack with a rain cap and
an oil-bath pre-cleaner bowl; a steering wheel on a raked column; a pan seat
on a leaf spring; rear mudguards with a tail lamp and a work lamp;
footplates and pedals; a three-point linkage (lift arms, lift rods, lower
links, top link) with its drawbar, and a PTO shaft stub under its shield.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD band, ``--stray-vert`` mesh hygiene, ``--lift-z``
and ``--float-tyre`` grounding, ``--cock-hub``, ``--cant-pin`` and
``--unpin-link`` joint fit, ``--sink-tyre`` and ``--float-lugs`` seat
conformance, ``--skew-wheel``, ``--wide-track``, ``--tall-lugs`` and
``--odd-fender`` mirror and size, ``--bunch-lugs`` the lug pitch,
``--reverse-lugs`` the chevron handing, ``--offset-pivot`` the stance and
``--loose-lamp`` one connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts are
not byte-identical across Blender versions - the LOD gate is a ratio band.

    blender --background --python farm_tractor.py --
    blender --background --python farm_tractor.py -- --skip-decimate
    blender --background --python farm_tractor.py -- --output tractor.png
"""
import argparse
import math
import os
import sys
import tempfile
import traceback

import bmesh
import bpy
import numpy as np
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

# --- Farmyard patch (world frame) -----------------------------------------------
SOIL_T = 0.085               # the mud's nominal top over the patch's underside
RUT_D = 0.028                # rut floor under the nominal field
Z0 = SOIL_T - RUT_D          # rut floor: the tractor frame's z origin
PATCH_C = (-0.22, 0.0)
PATCH_A = 1.70               # half length
PATCH_B = 0.98               # half width
TERRAIN_NU, TERRAIN_NV = 96, 58
RUT_FLAT = 0.160             # the ruts' compacted floor, half width
RUT_WALL = 0.055
BERM_D = 0.245               # squeezed-out mud either side of each rut
BERM_W = 0.040
BERM_H = 0.013
EDGE_DROP = 0.030
PUDDLE = (0.130, -0.66, 0.30, 0.12)    # centre x, y and semi-axes of the dip
PUD_D = 0.040
PUD_WL = 0.35                # water level, as a fraction of the dip's depth
PUD_RIM = 0.72               # the water's outline, as a fraction of the semi-axes

# --- Tractor layout (tractor frame: x forward, y left, z up from the rut floor) --
WHEELBASE = 1.780
TRACK_R = 1.320              # rear tyre centre to tyre centre (52 in)
TRACK_F = 1.220              # front (48 in)
AX_R = -0.5 * WHEELBASE
AX_F = 0.5 * WHEELBASE
R_RT = 0.620                 # rear tyre over the lug tips: 1.240 m (11.2-28 class)
LUG_H = 0.028
R_FT = 0.345                 # front tyre: 0.690 m (4.00-19 class)
SINK = 0.030                 # every tyre pressed this far into the rut's mud
Z_AR = R_RT - SINK
Z_AF = R_FT - SINK
RUT_Y = 0.5 * TRACK_R

# Rear tyre carcass: crown radius against the distance from the mid-plane.
REAR_CROWN = ((0.000, 0.5920), (0.030, 0.5920), (0.070, 0.5905), (0.100, 0.5860),
              (0.120, 0.5780), (0.133, 0.5640), (0.1405, 0.5420))
LUGS_PER_HALF = 22
LUG_BITE = 0.004             # lug root below the carcass
LUG_X = 0.010                # each bar crosses the centre line by this much
LUG_END = 0.137              # the bar's shoulder end, from the mid-plane
LUG_SWEEP = 0.19             # the bar's run back round the tyre (rad), apex to shoulder
LUG_BW, LUG_TW, LUG_CH = 0.023, 0.016, 0.003
LUG_ST = (0.0, 0.16, 0.36, 0.56, 0.76, 0.90, 1.0)
TYRE_SEGS_R, RIM_SEGS_R = 96, 64
TYRE_SEGS_F, RIM_SEGS_F = 72, 48
TYRE_BITE = 0.0012           # beads hooped this far onto the bead seats (a rim facet's
                             # chord takes up to 0.43 mm of it)
# Rims (bead seat, flange top, drop well, wall, flange inner face and outer face,
# drop-well half width).
RIM_R = dict(RS=0.3556, RFL=0.3806, RD=0.3250, t=0.005, Wf=0.127, Wo=0.133, well=0.060)
RIM_F = dict(RS=0.2413, RFL=0.2573, RD=0.2220, t=0.004, Wf=0.038, Wo=0.042, well=0.012)
DISC_R = ((0.072, -0.0575), (0.236, -0.0575), (0.262, -0.0505), (0.284, -0.0375),
          (0.299, -0.0255), (0.307, -0.0195))
DISC_F = ((0.050, -0.0045), (0.090, -0.0045), (0.099, 0.0000), (0.110, 0.0030), (0.122, 0.0005),
          (0.131, -0.0035), (0.150, -0.0020), (0.185, 0.0045), (0.2195, 0.0065))

PIN_R = 0.018                # front-axle pivot pin
PIN_Z = Z_AF + 0.150
BEAM_Z = Z_AF + 0.083
KP_Y = 0.520                 # kingpins, from the centre line
BOL_Z0 = PIN_Z + 0.060       # front support's underside

HW, HB, HT, HR, CROWN = 0.225, 0.850, 1.100, 0.085, 0.010   # bonnet section
HX0, HX1 = 0.235, 0.965

COL_B = Vector((0.060, 0.0, 0.780))
COL_DIR = Vector((-math.sqrt(0.5), 0.0, math.sqrt(0.5)))
COL_L = 0.665
WHEEL_RS = 0.205

R_F = 0.690                  # mudguard inner radius, round the rear axle
FENDER_TH = (-58.0, 102.0)   # from the top, + forward (deg)

# three-point linkage stations (tractor frame)
LL_F = (-0.780, 0.300, 0.400)        # lower-link front pin (x, |y|, z)
LL_R = (-1.620, 0.400, 0.400)        # lower-link rear eye, on the drawbar
LIFT_X, LIFT_Z = -0.995, 0.905       # lift cross-shaft
ARM_END = (-1.300, 0.225, 0.875)
TL_F = Vector((-1.140, 0.0, 0.800))  # top link front pin
TL_R = Vector((-1.600, 0.0, 0.490))  # top link stowed on the drawbar's bracket

# --- Falsifier sizes -------------------------------------------------------------
FLOAT_TYRE = 0.040           # --float-tyre: left front tyre lifted out of the mud
COCK_HUB = 0.0015            # --cock-hub: left rear hub off its half-shaft
CANT_PIN = 1.5               # --cant-pin: pivot pin turned in plan (deg)
UNPIN = 0.008                # --unpin-link: top link short, rear eye off its pin
SINK_BITE = 0.0030           # --sink-tyre: right rear bead
FLOAT_LUGS = 0.007           # --float-lugs: left rear lugs lifted off the carcass
SKEW_WHEEL = 0.006           # --skew-wheel: left rear wheel moved aft
WIDE_TRACK = 0.004           # --wide-track: each rear wheel outward
TALL_LUGS = 0.008            # --tall-lugs: rear lug tips taller
ODD_FENDER = 0.003           # --odd-fender: left mudguard bowed outward
BUNCH_DEG = 2.0              # --bunch-lugs: every fourth right rear bar turned
PIVOT_OFF = 0.300            # --offset-pivot: pin and bushings moved to the right
LOOSE_LAMP = 0.004           # --loose-lamp: tail lamp off its mudguard

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from the vertices.
OUTER_SIZE = (3.5839, 2.0869, 1.7330)
BASE_TRIS_MIN = 121000
BASE_TRIS_MAX = 123600
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 12
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 1040
BAKE_RES = 1024
CAGE_EXTRUSION = 0.006

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Supports: four tyres, each pressed into the mud in a band, read by rays
# down onto the soil.
TYRE_COUNT = 4
SINK_MIN = 0.018
SINK_MAX = 0.045
# Joint fit.
COAX_MAX = 0.0003
COAX_DEG_MAX = 0.3
HUBS = 4
BUSHINGS = 2
EYES = 14
EYE_OFF_MAX = 0.0005
EYE_DEG_MAX = 1.0
EYE_PIN_PAST = 0.002         # a pin stands past both faces of its eye
# Seats.
TYRE_SEAT_MIN = 0.0004
TYRE_SEAT_MAX = 0.0020
LUG_BITE_MIN = 0.0020
LUG_BITE_MAX = 0.0060
LUG_PROUD_MIN = 0.020
LUGS = 4 * LUGS_PER_HALF
# Mirror and size.
MIRROR_EPS = 0.0005
WHEEL_MIRROR_EPS = 0.0005
SIZE_TOL = 0.004
DIAM_TOL = 0.006
REAR_DIAM = 2.0 * R_RT
# Tread.
PITCH_TOL_DEG = 0.25
HAND_MIN_DEG = 5.0
# Stance: mass centre inside the support triangle (the rear contact patches
# and the front axle's pivot) by a quarter of the rear track.
STANCE_MARGIN = 0.25 * TRACK_R

HERO_YAW_DEG = 0.0
CAM_VIEW = (0.56, -0.83)
CAM_DIST = 6.3
CAM_LENS = 50.0
CAM_LIFT = 1.55
AIM_OFFSET = (0.05, 0.0, -0.30)
WALL_Y = 6.0

PAINT_IDX = 0
WHEEL_IDX = 1
RUBBER_IDX = 2
IRON_IDX = 3
STEEL_IDX = 4
ZINC_IDX = 5
BLACK_IDX = 6
GLASS_IDX = 7
EXHAUST_IDX = 8
CORE_IDX = 9
SOIL_IDX = 10
WATER_IDX = 11

FACE_FLOORS = {
    PAINT_IDX: 8080, WHEEL_IDX: 8590, RUBBER_IDX: 14290, IRON_IDX: 6890, STEEL_IDX: 10000,
    ZINC_IDX: 2350, BLACK_IDX: 2660, GLASS_IDX: 790, EXHAUST_IDX: 1060, CORE_IDX: 50,
    SOIL_IDX: 11660, WATER_IDX: 128,
}
MAT_LABELS = ("body paint", "wheel paint", "rubber", "cast iron", "steel", "zinc",
              "black enamel", "glass", "exhaust", "radiator core", "soil", "water")
# Effective densities (kg/m^3): castings, tanks and tyres are modelled solid
# but are hollow or partly so.
DENSITY = (2000.0, 7850.0, 480.0, 2700.0, 7850.0, 7000.0, 2500.0, 2500.0, 2500.0, 2500.0,
           0.0, 0.0)

# Part tags: a face attribute naming which part a face belongs to, so the
# audits can find the shells they measure. Every measured value is read from
# the vertices, never from these constants.
(T_NONE, T_SOIL, T_WATER, T_TYRE, T_LUG, T_RIM, T_HUB_F, T_HUB_R, T_STUB, T_AXLE,
 T_PIVOT, T_BUSH, T_EYE, T_PIN) = range(14)

X = Vector((1.0, 0.0, 0.0))
Y = Vector((0.0, 1.0, 0.0))
Z = Vector((0.0, 0.0, 1.0))
TONE = "PartTone"
WEAR = "EdgeWear"


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


def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


# --------------------------------------------------------------------------
# Construction helpers (copied from showcase/go-kart and showcase/planet-rover,
# not imported)
# --------------------------------------------------------------------------

class Build:
    """The bmesh under construction, its part-tag and tone layers and named
    vertex groups (for the falsifiers that move one assembly)."""

    def __init__(self, bm):
        self.bm = bm
        self.tag = bm.faces.layers.int.new("part")
        self.tone = bm.faces.layers.float.new(TONE)
        self.groups = {}

    def part(self, tag=T_NONE, tone=0.5, *groups):
        return _Part(self, tag, tone, groups)

    def verts(self, *names):
        out = []
        for n in names:
            out.extend(self.groups.get(n, []))
        return out


class _Part:
    def __init__(self, b, tag, tone, groups):
        self.b, self.t, self.tone, self.g = b, tag, tone, groups

    def __enter__(self):
        self.nf = len(self.b.bm.faces)
        self.nv = len(self.b.bm.verts)
        return self

    def __exit__(self, *exc):
        bm = self.b.bm
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        for i in range(self.nf, len(bm.faces)):
            bm.faces[i][self.b.tag] = self.t
            bm.faces[i][self.b.tone] = self.tone
        vs = [bm.verts[i] for i in range(self.nv, len(bm.verts))]
        for g in self.g:
            self.b.groups.setdefault(g, []).extend(vs)
        return False


def _mark(faces, mat_idx):
    for f in faces:
        f.material_index = mat_idx
    return faces


def frame(ez, ex_hint):
    """Rotation whose local Z is ``ez`` and local X is ``ex_hint`` made
    orthogonal to it (columns ex, ey, ez; right-handed)."""
    ez = Vector(ez).normalized()
    ex = Vector(ex_hint)
    ex = (ex - ez * ex.dot(ez)).normalized()
    ey = ez.cross(ex)
    return Matrix((ex, ey, ez)).transposed()


def any_perp(v):
    v = Vector(v).normalized()
    return X if abs(v.x) < 0.9 else Y


# (u, v, w) -> (y, z, x): a section in the (y, z) plane lofted along x
ROT_X = Matrix(((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
# (u, v, w) -> (x, z, y): a section in the (x, z) plane lofted along y
ROT_Y = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))
I3 = Matrix.Identity(3)


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None, phase=0.0,
              solid=False):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: an open
    polyline closed by n-gon caps at its two ends; otherwise a closed
    polygon revolved into a ring shell."""
    c = Vector(center)
    m = rot if rot is not None else Matrix.Identity(3)
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new(c + m @ Vector((r * ca, r * sa, z))) for r, z in profile])
    n = len(profile)
    last = n - 1 if solid else n
    faces = []
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for j in range(last):
            k = (j + 1) % n
            faces.append(bm.faces.new((r0[j], r1[j], r1[k], r0[k])))
    if solid:
        faces.append(bm.faces.new([rings[i][0] for i in reversed(range(segs))]))
        faces.append(bm.faces.new([rings[i][n - 1] for i in range(segs)]))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def lathe_on(bm, profile, segs, mat_idx, center, axis, phase=0.0, solid=True, ref=None):
    axis = Vector(axis).normalized()
    return add_lathe(bm, profile, segs, mat_idx, center=center,
                     rot=frame(axis, ref if ref is not None else any_perp(axis)),
                     phase=phase, solid=solid)


_HEX = [0]


def add_hex(bm, center, axis, a, b, r, mat_idx, phase=0.0):
    """A hex head or nut on ``axis`` from a to b, its top edge chamfered.
    Every head is turned a further step: identical heads in a row would
    otherwise put their flats on shared planes."""
    _HEX[0] += 1
    ch = min(0.0010, 0.25 * (b - a))
    return lathe_on(bm, [(r, a), (r, b - ch), (r * 0.86, b)], 6, mat_idx, center, axis,
                    phase=phase + math.pi / 6.0 + 0.2113 * _HEX[0])


def add_rod(bm, center, axis, a, b, r, mat_idx, segs=12, ch=0.0):
    if ch > 0.0:
        prof = [(r - ch, a), (r, a + ch), (r, b - ch), (r - ch, b)]
    else:
        prof = [(r, a), (r, b)]
    return lathe_on(bm, prof, segs, mat_idx, center, axis)


def add_tube(bm, pts, radius, sides, mat_idx, phase=0.0, ref=None):
    """Capped round bar swept along a polyline (parallel-transport frames)."""
    pts = [Vector(p) for p in pts]
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    if ref is None:
        ref = Z if abs(tans[0].z) < 0.9 else X
    nrm = (Vector(ref) - tans[0] * Vector(ref).dot(tans[0])).normalized()
    rings = []
    for p, t in zip(pts, tans):
        nrm = (nrm - t * nrm.dot(t)).normalized()
        bi = t.cross(nrm)
        rings.append([
            bm.verts.new(p + radius * (nrm * math.cos(phase + 2.0 * math.pi * k / sides)
                                       + bi * math.sin(phase + 2.0 * math.pi * k / sides)))
            for k in range(sides)
        ])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def rrect(ha, hb, rc, n_corner=4):
    """Rounded rectangle loop (counter-clockwise)."""
    rc = max(min(rc, ha - 1e-4, hb - 1e-4), 0.0006)
    pts = []
    for k, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        cx, cy = sx * (ha - rc), sy * (hb - rc)
        a0 = 0.5 * math.pi * k
        for s in range(n_corner + 1):
            a = a0 + 0.5 * math.pi * s / n_corner
            pts.append((cx + rc * math.cos(a), cy + rc * math.sin(a)))
    return pts


def add_rbox(bm, ha, hb, rc, profile, origin, rot, mat_idx, n_corner=4):
    """Loft of rounded rectangles along local Z: profile [(inset, z)], each
    loop inset from (ha, hb, rc); n-gon caps at both ends."""
    o = Vector(origin)
    rings = []
    for inset, z in profile:
        loop = rrect(ha - inset, hb - inset, rc - inset, n_corner)
        rings.append([bm.verts.new(o + rot @ Vector((x, y, z))) for x, y in loop])
    n = len(rings[0])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def chamfered(h, c):
    """A slab profile [(inset, z)] from 0 to h with chamfer c at both faces."""
    return [(c, 0.0), (0.0, c), (0.0, h - c), (c, h)]


def box(bm, lo, hi, mat_idx, rc=0.006, ch=0.002, n_corner=2):
    """An axis-aligned box from ``lo`` to ``hi``, rounded in plan, chamfered
    top and bottom."""
    lo, hi = Vector(lo), Vector(hi)
    c = (lo + hi) * 0.5
    return add_rbox(bm, 0.5 * (hi.x - lo.x), 0.5 * (hi.y - lo.y), rc,
                    chamfered(hi.z - lo.z, ch), (c.x, c.y, lo.z), I3, mat_idx, n_corner)


def add_prism(bm, outline, w0, w1, origin, rot, mat_idx, ch=0.0):
    """Planar outline [(u, v)] extruded along local Z from w0 to w1, both
    faces chamfered by ``ch`` (an inset ring) when it is non-zero."""
    o = Vector(origin)
    if ch > 0.0:
        inner = inset_poly(outline, ch)
        layers = [(inner, w0), (outline, w0 + ch), (outline, w1 - ch), (inner, w1)]
    else:
        layers = [(outline, w0), (outline, w1)]
    rings = [[bm.verts.new(o + rot @ Vector((u, v, w))) for u, v in loop] for loop, w in layers]
    n = len(outline)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(n):
            faces.append(bm.faces.new((r0[i], r0[(i + 1) % n], r1[(i + 1) % n], r1[i])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_plate(bm, outline, w0, w1, band, mat_idx):
    """A square-edged plate: the outline extruded from w0 to w1, each face
    carrying a band ring ``band`` inside its edge (the face stays flat)."""
    inner = inset_poly(outline, band)
    layers = [(inner, w0), (outline, w0), (outline, w1), (inner, w1)]
    rings = [[bm.verts.new(Vector((u, v, w))) for u, v in loop] for loop, w in layers]
    n = len(outline)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(n):
            faces.append(bm.faces.new((r0[i], r0[(i + 1) % n], r1[(i + 1) % n], r1[i])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def poly_area(poly):
    n = len(poly)
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
                     for i in range(n))


def inset_poly(poly, d):
    """Every vertex of a (convex-ish) polygon moved ``d`` inward along its
    bisector."""
    n = len(poly)
    sgn = 1.0 if poly_area(poly) > 0.0 else -1.0
    out = []
    for i in range(n):
        a, p, b = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % n])
        e0 = (p - a).normalized()
        e1 = (b - p).normalized()
        n0 = Vector((-e0.y, e0.x)) * sgn
        n1 = Vector((-e1.y, e1.x)) * sgn
        bis = (n0 + n1)
        if bis.length < 1e-9:
            bis = n0
        bis.normalize()
        cosh = max(0.3, bis.dot(n0))
        q = p + bis * (d / cosh)
        out.append((q.x, q.y))
    return out


def fillet_path(pts, rf, steps=4):
    pts = [Vector(p) for p in pts]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, p, b = pts[i - 1], pts[i], pts[i + 1]
        r = min(rf, (a - p).length * 0.45, (b - p).length * 0.45)
        p0 = p + (a - p).normalized() * r
        p1 = p + (b - p).normalized() * r
        for k in range(steps + 1):
            t = k / steps
            out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * p + t * t * p1)
    out.append(pts[-1])
    return out


def add_bar(bm, pts, wax, half_w, half_t, rc, mat_idx, fillet=0.008, filleted=False):
    """Flat bar: its width lies along ``wax``, its thickness across it;
    rounded-rectangle section."""
    pts = [Vector(p) for p in pts] if filleted else fillet_path(pts, fillet)
    wax = Vector(wax).normalized()
    sec = rrect(half_w, half_t, rc, 2)
    rings = []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        t = (b - a).normalized()
        w = (wax - t * wax.dot(t)).normalized()
        th = t.cross(w)
        rings.append([bm.verts.new(p + w * x + th * y) for x, y in sec])
    n = len(sec)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_loft(bm, loops, mat_idx):
    """Closed loops [[Vector]] of equal length lofted in order, n-gon caps."""
    rings = [[bm.verts.new(p) for p in loop] for loop in loops]
    n = len(rings[0])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(n):
            m = (j + 1) % n
            faces.append(bm.faces.new((r0[j], r0[m], r1[m], r1[j])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_ring_loft(bm, loops, mat_idx):
    """Closed loops lofted in order and the last joined back to the first: a
    hollow tube (a shell with a wall), no caps."""
    rings = [[bm.verts.new(p) for p in loop] for loop in loops]
    n = len(rings[0])
    faces = []
    for i in range(len(rings)):
        r0, r1 = rings[i], rings[(i + 1) % len(rings)]
        for j in range(n):
            m = (j + 1) % n
            faces.append(bm.faces.new((r0[j], r0[m], r1[m], r1[j])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_sheet(bm, surf, nu, nv, thick, mat_idx):
    """A closed plate: ``surf(u, v) -> (point, normal)`` over the unit square,
    offset ``thick`` back along the normal, rims stitched round the edge."""
    front, back = [], []
    for j in range(nv + 1):
        rf, rb = [], []
        for i in range(nu + 1):
            p, n = surf(i / nu, j / nv)
            rf.append(bm.verts.new(p))
            rb.append(bm.verts.new(p - n * thick))
        front.append(rf)
        back.append(rb)
    faces = []
    for j in range(nv):
        for i in range(nu):
            faces.append(bm.faces.new((front[j][i], front[j][i + 1], front[j + 1][i + 1],
                                       front[j + 1][i])))
            faces.append(bm.faces.new((back[j][i], back[j + 1][i], back[j + 1][i + 1],
                                       back[j][i + 1])))
    rim = ([(0, i) for i in range(nu + 1)] + [(j, nu) for j in range(1, nv + 1)]
           + [(nv, i) for i in reversed(range(nu))] + [(j, 0) for j in reversed(range(1, nv))])
    for k in range(len(rim)):
        (ja, ia), (jb, ib) = rim[k], rim[(k + 1) % len(rim)]
        faces.append(bm.faces.new((front[jb][ib], front[ja][ia], back[ja][ia], back[jb][ib])))
    _mark(faces, mat_idx)
    return [v for row in front + back for v in row]


def thick_profile(pts, t):
    """A polyline [(r, w)] thickened by ``t`` about its centre line into a
    closed polygon (for a pressed disc or a pan)."""
    n = len(pts)
    up, dn = [], []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        dr, dw = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dr, dw)
        nr, nw = -dw / ln, dr / ln
        up.append((pts[i][0] + nr * t * 0.5, pts[i][1] + nw * t * 0.5))
        dn.append((pts[i][0] - nr * t * 0.5, pts[i][1] - nw * t * 0.5))
    return up + list(reversed(dn))


def hull2d(pts):
    """Convex hull, counter-clockwise (monotone chain)."""
    pts = sorted(set((round(x, 9), round(z, 9)) for x, z in pts))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 1e-12:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 1e-12:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def circles_hull(circles, n=16):
    pts = []
    for u, v, r in circles:
        for k in range(n):
            a = 2.0 * math.pi * (k + 0.5) / n
            pts.append((u + r * math.cos(a), v + r * math.sin(a)))
    return hull2d(pts)


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


def resample(pts, n):
    """``n`` points evenly spaced by arc length along a polyline."""
    pts = [Vector(p) for p in pts]
    lens = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    total = sum(lens)
    out = []
    for k in range(n):
        s = total * k / (n - 1)
        acc = 0.0
        for i, ln in enumerate(lens):
            if acc + ln >= s - 1e-12 or i == len(lens) - 1:
                t = 0.0 if ln < 1e-12 else min(1.0, max(0.0, (s - acc) / ln))
                out.append(pts[i] + (pts[i + 1] - pts[i]) * t)
                break
            acc += ln
    return out


def body_section(hw, zb, zt, rt, rb, crown, n, top_n=8):
    """A closed counter-clockwise loop in (y, z): top corners of radius
    ``rt``, bottom corners of radius ``rb``, the top crowned by an even term
    so the section is mirror-symmetric in y."""
    rt = max(rt, 0.0006)
    rb = max(rb, 0.0006)
    flat = hw - rt
    pts = []
    for k in range(n + 1):
        a = 0.5 * math.pi * k / n
        pts.append((flat + rt * math.cos(a), zt - rt + rt * math.sin(a)))
    for k in range(1, top_n):
        y = flat - 2.0 * flat * k / top_n
        pts.append((y, zt + crown * (1.0 - (y / flat) ** 2)))
    for k in range(n + 1):
        a = 0.5 * math.pi + 0.5 * math.pi * k / n
        pts.append((-flat + rt * math.cos(a), zt - rt + rt * math.sin(a)))
    for k in range(n + 1):
        a = math.pi + 0.5 * math.pi * k / n
        pts.append((-hw + rb + rb * math.cos(a), zb + rb + rb * math.sin(a)))
    for k in range(n + 1):
        a = 1.5 * math.pi + 0.5 * math.pi * k / n
        pts.append((hw - rb + rb * math.cos(a), zb + rb + rb * math.sin(a)))
    return pts


def top_z(hw, zt, rt, crown, y):
    """The top boundary of ``body_section`` at ``y``."""
    flat = hw - rt
    ay = abs(y)
    if ay <= flat:
        return zt + crown * (1.0 - (y / flat) ** 2)
    return zt - rt + math.sqrt(max(rt * rt - (ay - flat) ** 2, 0.0))


# --------------------------------------------------------------------------
# The farmyard patch
# --------------------------------------------------------------------------

def wob(th):
    return (1.0 + 0.030 * math.cos(3 * th + 0.7) + 0.022 * math.cos(5 * th + 2.1)
            + 0.012 * math.cos(7 * th + 0.3))


def patch_m(x, y):
    lx = (x - PATCH_C[0]) / PATCH_A
    ly = (y - PATCH_C[1]) / PATCH_B
    th = math.atan2(ly, lx)
    return (lx ** 4 + ly ** 4) ** 0.25 / wob(th)


def patch_point(u, v):
    """Grid (u, v) in [-1, 1]^2 onto the wobbled superellipse: each square
    ring of the grid lands on one superellipse ring (after planet-rover)."""
    m = max(abs(u), abs(v))
    if m < 1e-12:
        return PATCH_C[0], PATCH_C[1]
    n4 = (u ** 4 + v ** 4) ** 0.25
    px, py = u * m / n4, v * m / n4
    w = wob(math.atan2(py, px))
    return PATCH_C[0] + PATCH_A * px * w, PATCH_C[1] + PATCH_B * py * w


def soil_low(x, y):
    return (0.009 * math.cos(1.3 * x + 0.4) * math.cos(1.6 * y - 0.7)
            + 0.006 * math.sin(2.9 * x - 1.7 * y + 0.5))


def soil_fine(x, y):
    return (0.0040 * math.cos(7.3 * x + 4.1 * y + 1.3)
            + 0.0030 * math.sin(9.9 * y - 6.7 * x + 1.1)
            + 0.0018 * math.cos(15.1 * x - 12.3 * y))


def floor_fine(x, y):
    return (0.0009 * math.cos(11.0 * x + 0.7) * math.cos(9.0 * y)
            + 0.0006 * math.sin(17.0 * x - 3.0 * y))


def rut_mask(y):
    d = abs(abs(y) - RUT_Y)
    return 1.0 - smoothstep(RUT_FLAT, RUT_FLAT + RUT_WALL, d), d


def puddle_wob(th):
    return 1.0 + 0.12 * math.cos(2.0 * th + 0.5) + 0.07 * math.cos(3.0 * th + 1.3)


def puddle_r2(x, y):
    """The dip's elliptical radius, squared, pulled out of round by a
    closed-form wobble so the waterline is not an ellipse."""
    px, py, ax, ay = PUDDLE
    u, v = (x - px) / ax, (y - py) / ay
    return (u * u + v * v) / puddle_wob(math.atan2(v, u)) ** 2


def soil_top(x, y):
    """The mud: a closed-form field, two ruts pressed in along the rear
    track with a compacted, level floor (the tractor's z origin), berms of
    squeezed-out mud either side, and a dip in the right rut that holds a
    puddle."""
    m, d = rut_mask(y)
    field = SOIL_T + soil_low(x, y) + soil_fine(x, y)
    floor = Z0 + floor_fine(x, y)
    berm = BERM_H * math.exp(-((d - BERM_D) / BERM_W) ** 2) * (1.0 - m)
    z = field * (1.0 - m) + floor * m + berm
    r2 = puddle_r2(x, y)
    if r2 < 1.0:
        z -= PUD_D * (1.0 - r2) ** 2
    return z - EDGE_DROP * smoothstep(0.80, 1.0, patch_m(x, y)) ** 1.5


def track_warp(n):
    """n + 1 grid values over [-1, 1], closer together across the two ruts."""
    vt = RUT_Y / PATCH_B
    k = 4000
    xs = [-1.0 + 2.0 * i / k for i in range(k + 1)]
    dens = [1.0 + 1.2 * math.exp(-((abs(x) - vt) / 0.22) ** 2) for x in xs]
    cum = [0.0]
    for i in range(1, k + 1):
        cum.append(cum[-1] + 0.5 * (dens[i] + dens[i - 1]) * (xs[i] - xs[i - 1]))
    out, i = [], 0
    for j in range(n + 1):
        target = cum[-1] * j / n
        while i < k - 1 and cum[i + 1] < target:
            i += 1
        t = (target - cum[i]) / max(cum[i + 1] - cum[i], 1e-12)
        out.append(xs[i] + (xs[i + 1] - xs[i]) * min(max(t, 0.0), 1.0))
    out[0], out[-1] = -1.0, 1.0
    return out


def build_soil(b):
    bm = b.bm
    nu, nv = TERRAIN_NU, TERRAIN_NV
    vs = track_warp(nv)
    with b.part(T_SOIL, 0.5):
        grid = []
        for j in range(nv + 1):
            row = []
            for i in range(nu + 1):
                x, y = patch_point(-1.0 + 2.0 * i / nu, vs[j])
                row.append(bm.verts.new((x, y, soil_top(x, y))))
            grid.append(row)
        faces = []
        for j in range(nv):
            for i in range(nu):
                faces.append(bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1],
                                           grid[j + 1][i])))
        ring = ([grid[0][i] for i in range(nu + 1)] + [grid[j][nu] for j in range(1, nv + 1)]
                + [grid[nv][i] for i in reversed(range(nu))]
                + [grid[j][0] for j in reversed(range(1, nv))])
        # a rolled skirt down to the floor
        rings = [ring]
        for push, frac in ((0.024, 0.45), (0.030, 0.0)):
            nr = []
            for v in ring:
                d = Vector((v.co.x - PATCH_C[0], v.co.y - PATCH_C[1], 0.0)).normalized()
                nr.append(bm.verts.new((v.co.x + d.x * push, v.co.y + d.y * push,
                                        v.co.z * frac)))
            rings.append(nr)
        n = len(ring)
        for r0, r1 in zip(rings, rings[1:]):
            for k in range(n):
                m = (k + 1) % n
                faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
        cen = bm.verts.new((PATCH_C[0], PATCH_C[1], 0.0))
        last = rings[-1]
        for k in range(n):
            faces.append(bm.faces.new((cen, last[(k + 1) % n], last[k])))
        _mark(faces, SOIL_IDX)
        # rut floor shading uses the triangulation's own diagonals
        bmesh.ops.triangulate(bm, faces=[f for f in faces if len(f.verts) == 4],
                              quad_method="SHORT_EDGE")


def build_water(b):
    """The puddle: a thin slab whose rim lies buried in the dip's walls."""
    px, py, ax, ay = PUDDLE
    wl = Z0 - PUD_WL * PUD_D
    outline = []
    for k in range(48):
        th = 2.0 * math.pi * k / 48
        w = PUD_RIM * puddle_wob(th)
        outline.append((px + w * ax * math.cos(th), py + w * ay * math.sin(th)))
    with b.part(T_WATER, 0.5):
        add_prism(b.bm, outline, wl - 0.003, wl, (0.0, 0.0, 0.0), I3, WATER_IDX)


# --------------------------------------------------------------------------
# Backbone: rear axle centre housing, trumpets, gearbox, engine
# --------------------------------------------------------------------------

TRUMPET = ((0.130, 0.170), (0.140, 0.182), (0.140, 0.212), (0.112, 0.222), (0.096, 0.300),
           (0.084, 0.400), (0.076, 0.470), (0.092, 0.474), (0.098, 0.480), (0.098, 0.496),
           (0.064, 0.502))


def trumpet_r(w):
    pts = TRUMPET[3:8]
    for (r0, w0), (r1, w1) in zip(pts, pts[1:]):
        if w0 <= w <= w1:
            return r0 + (r1 - r0) * (w - w0) / (w1 - w0)
    return pts[-1][0]


_AXL = [0]


def axle_lathe(bm, profile, segs, mat, s, solid=True):
    """A lathe on the rear axle's line; profile (r, w) with w = |y|. Every
    part is turned a further, non-commensurate step: equal radii on one axle
    would otherwise share their facet planes."""
    _AXL[0] += 1
    return lathe_on(bm, profile, segs, mat, Vector((AX_R, 0.0, Z_AR)), Y * s,
                    phase=0.0371 * _AXL[0], solid=solid, ref=X)


def build_rear_axle(b, flags):
    bm = b.bm
    with b.part(T_NONE, 0.45, "tr"):
        add_rbox(bm, 0.200, 0.225, 0.090, [(0.020, 0.0), (0.0, 0.020), (0.0, 0.380), (0.020, 0.400)],
                 (AX_R, -0.200, 0.615), ROT_Y, IRON_IDX, n_corner=4)
    # rear cover plate with its bolts
    with b.part(T_NONE, 0.55, "tr"):
        add_rbox(bm, 0.160, 0.130, 0.050, chamfered(0.020, 0.004), (AX_R - 0.195, 0.0, 0.600),
                 frame(-X, Z), IRON_IDX, n_corner=3)
    for k in range(8):
        a = 2.0 * math.pi * k / 8 + 0.2
        p = Vector((AX_R - 0.211, 0.140 * math.cos(a), 0.600 + 0.110 * math.sin(a)))
        with b.part(T_NONE, 0.5, "tr"):
            add_hex(bm, p, -X, -0.0008, 0.008, 0.009, STEEL_IDX, phase=a)
    # hydraulic lift cover on top
    with b.part(T_NONE, 0.60, "tr"):
        add_rbox(bm, 0.150, 0.170, 0.040, [(0.0, 0.0), (0.0, 0.070), (0.012, 0.085)],
                 (AX_R + 0.020, 0.0, 0.820), I3, IRON_IDX, n_corner=3)
    for s in (-1.0, 1.0):
        side = "L" if s > 0 else "R"
        with b.part(T_NONE, 0.40 if s > 0 else 0.50, "tr"):
            axle_lathe(bm, TRUMPET, 40, IRON_IDX, s)
        for k in range(8):
            a = 2.0 * math.pi * k / 8 + 0.3
            p = Vector((AX_R + 0.125 * math.cos(a), s * 0.212, Z_AR + 0.125 * math.sin(a)))
            with b.part(T_NONE, 0.5, "tr"):
                add_hex(bm, p, Y * s, -0.0008, 0.0080, 0.0095, STEEL_IDX, phase=a)
        with b.part(T_AXLE, 0.5, "tr"):
            axle_lathe(bm, [(0.038, 0.488), (0.040, 0.490), (0.040, 0.638), (0.038, 0.640)], 24,
                       STEEL_IDX, s)
        gh = "hub" + side
        with b.part(T_HUB_R, 0.5, "tr", gh):
            axle_lathe(bm, [(0.060, 0.507), (0.068, 0.512), (0.068, 0.585), (0.124, 0.588),
                            (0.128, 0.592), (0.128, 0.600), (0.056, 0.6035)], 40, IRON_IDX, s)
        with b.part(T_NONE, 0.5, "tr", gh):
            axle_lathe(bm, [(0.050, 0.598), (0.050, 0.648), (0.046, 0.655), (0.030, 0.658)], 24,
                       IRON_IDX, s)
        if s > 0 and flags["cock_hub"]:
            for v in b.groups[gh]:
                v.co.z += COCK_HUB
        # brake drum housing on the trumpet's inner end
        with b.part(T_NONE, 0.55, "tr"):
            axle_lathe(bm, [(0.100, 0.232), (0.150, 0.236), (0.156, 0.244), (0.156, 0.300),
                            (0.148, 0.306), (0.098, 0.310)], 40, IRON_IDX, s)
        # fender stays from the trumpet up to the mudguard's inner edge
        for th in (18.0, -42.0):
            t = math.radians(th)
            top = Vector((AX_R + (R_F - 0.001) * math.sin(t), s * 0.490,
                          Z_AR + (R_F - 0.001) * math.cos(t)))
            foot = Vector((AX_R + 0.040 * math.sin(t), s * 0.430, Z_AR + 0.060))
            d = (top - foot).normalized()
            with b.part(T_NONE, 0.5, "tr"):
                add_bar(bm, [foot, foot + d * 0.12, top], d.cross(Y).normalized(), 0.016,
                        0.0045, 0.002, STEEL_IDX, fillet=0.04)


def build_gearbox_engine(b):
    bm = b.bm
    # gearbox between the centre housing and the bell housing
    with b.part(T_NONE, 0.50, "tr"):
        add_rbox(bm, 0.165, 0.160, 0.050, chamfered(0.650, 0.012), (-0.720, 0.0, 0.560), ROT_X,
                 IRON_IDX, n_corner=4)
    # top cover with the gear lever's turret
    with b.part(T_NONE, 0.62, "tr"):
        box(bm, (-0.470, -0.110, 0.705), (-0.200, 0.110, 0.738), IRON_IDX, rc=0.018, ch=0.004)
    for k, (dx, dy) in enumerate(((-0.455, -0.095), (-0.455, 0.095), (-0.215, -0.095),
                                  (-0.215, 0.095))):
        with b.part(T_NONE, 0.5, "tr"):
            add_hex(bm, Vector((dx, dy, 0.0)), Z, 0.7372, 0.7442 + 0.0002 * k, 0.0075, STEEL_IDX)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.040, 0.730), (0.040, 0.752), (0.030, 0.768), (0.020, 0.772)], 20,
                 IRON_IDX, Vector((-0.330, 0.0, 0.0)), Z)
    # bell housing, flanged to the block
    with b.part(T_NONE, 0.45, "tr"):
        add_rbox(bm, 0.175, 0.175, 0.070, [(0.012, 0.0), (0.0, 0.012), (0.0, 0.200),
                                           (-0.008, 0.205), (-0.008, 0.222), (0.004, 0.230)],
                 (-0.100, 0.0, 0.600), ROT_X, IRON_IDX, n_corner=4)
    # block, head, rocker cover, sump, timing cover
    with b.part(T_NONE, 0.55, "tr"):
        add_rbox(bm, 0.150, 0.170, 0.030, [(0.006, 0.0), (0.0, 0.006), (0.0, 0.504), (0.006, 0.510)],
                 (0.110, 0.0, 0.630), ROT_X, IRON_IDX, n_corner=3)
    with b.part(T_NONE, 0.40, "tr"):
        add_rbox(bm, 0.135, 0.050, 0.015, chamfered(0.4665, 0.004), (0.1335, 0.0, 0.846), ROT_X,
                 IRON_IDX, n_corner=3)
    with b.part(T_NONE, 0.35, "tr"):
        add_rbox(bm, 0.105, 0.036, 0.022, chamfered(0.410, 0.008), (0.160, 0.0, 0.916), ROT_X,
                 IRON_IDX, n_corner=3)
    with b.part(T_NONE, 0.65, "tr"):
        add_rbox(bm, 0.125, 0.060, 0.030, [(0.010, 0.0), (0.0, 0.010), (0.0, 0.420), (0.010, 0.430)],
                 (0.150, 0.0, 0.420), ROT_X, IRON_IDX, n_corner=3)
    with b.part(T_NONE, 0.60, "tr"):
        add_rbox(bm, 0.142, 0.009, 0.004, chamfered(0.450, 0.002), (0.140, 0.0, 0.4705), ROT_X,
                 IRON_IDX, n_corner=2)
    with b.part(T_NONE, 0.5, "tr"):
        add_hex(bm, Vector((0.300, 0.0, 0.0)), -Z, -0.3605, -0.3480, 0.012, STEEL_IDX)
    with b.part(T_NONE, 0.45, "tr"):
        add_rbox(bm, 0.130, 0.170, 0.060, chamfered(0.040, 0.006), (0.615, 0.0, 0.600), ROT_X,
                 IRON_IDX, n_corner=3)
    # core plugs and head bolts along the block's right side
    for k in range(3):
        with b.part(T_NONE, 0.5, "tr"):
            lathe_on(bm, [(0.022, -0.004), (0.022, 0.003), (0.018, 0.0045)], 20, STEEL_IDX,
                     Vector((0.220 + 0.150 * k, -0.150, 0.600)), -Y)
    # steering box on the bell housing's top
    with b.part(T_NONE, 0.40, "tr"):
        box(bm, (0.020, -0.055, 0.700), (0.140, 0.055, 0.800), IRON_IDX, rc=0.020, ch=0.006)


def build_front_support(b, flags):
    """The front support (bolster) bolted under the radiator, its two lugs,
    the pivot pin through them and the axle beam's boss with its two
    bushings; the beam, the kingpin bosses, knuckles, kingpins, spindles and
    steering arms."""
    bm = b.bm
    with b.part(T_NONE, 0.50, "tr"):
        box(bm, (0.700, -0.125, BOL_Z0), (1.060, 0.125, BOL_Z0 + 0.065), IRON_IDX, rc=0.025,
            ch=0.008)
    for s in (-1.0, 1.0):
        with b.part(T_NONE, 0.50, "tr"):
            box(bm, (0.520, s * 0.130 - 0.024, 0.470), (0.745, s * 0.130 + 0.024, BOL_Z0 + 0.045),
                IRON_IDX, rc=0.012, ch=0.004)
    for k, x in enumerate((AX_F - 0.105, AX_F + 0.105)):
        lug = circles_hull([(0.0, PIN_Z, 0.038), (-0.070, BOL_Z0 + 0.020, 0.012),
                            (0.070, BOL_Z0 + 0.020, 0.012)], 24)
        with b.part(T_NONE, 0.5, "tr"):
            add_prism(bm, lug, x - 0.014, x + 0.014, (0.0, 0.0, 0.0), ROT_X, IRON_IDX, ch=0.002)
    # the pin and its bushings (moved together by --offset-pivot)
    pc = Vector((AX_F, -PIVOT_OFF if flags["offset_pivot"] else 0.0, PIN_Z))
    pin_ax = X
    if flags["cant_pin"]:
        pin_ax = Matrix.Rotation(math.radians(CANT_PIN), 3, "Z") @ X
    with b.part(T_PIVOT, 0.5, "tr"):
        lathe_on(bm, [(PIN_R - 0.0015, -0.150), (PIN_R, -0.1485), (PIN_R, 0.1485),
                      (PIN_R - 0.0015, 0.150)], 20, STEEL_IDX, pc, pin_ax, ref=Z)
    with b.part(T_NONE, 0.5, "tr"):
        add_hex(bm, pc, pin_ax, 0.1180, 0.1310, 0.0270, STEEL_IDX)
    with b.part(T_NONE, 0.5, "tr"):
        add_hex(bm, pc, -pin_ax, 0.1180, 0.1305, 0.0265, STEEL_IDX)
    # the bushings sit in the boss on its own axis; --cant-pin turns the pin alone
    for sgn in (1.0, -1.0):
        with b.part(T_BUSH, 0.5, "tr"):
            lathe_on(bm, [(PIN_R - 0.0005, 0.060), (0.031, 0.060), (0.031, 0.0758), (0.037, 0.0763),
                          (0.037, 0.0810), (PIN_R - 0.0005, 0.0810)], 24, STEEL_IDX, pc,
                     X * sgn, solid=False, ref=Z)
    # the beam's boss, and the beam
    bc = Vector((AX_F, 0.0, PIN_Z))
    with b.part(T_NONE, 0.40, "tr"):
        lathe_on(bm, [(0.040, -0.075), (0.045, -0.070), (0.045, 0.070), (0.040, 0.075)], 28,
                 IRON_IDX, bc, X, ref=Z)
    with b.part(T_NONE, 0.40, "tr"):
        add_rbox(bm, 0.030, 0.035, 0.012, chamfered(2.0 * (KP_Y - 0.005), 0.006),
                 (AX_F, -(KP_Y - 0.005), BEAM_Z), ROT_Y, IRON_IDX, n_corner=3)
    ends = {}
    for s in (-1.0, 1.0):
        K = Vector((AX_F, s * KP_Y, 0.0))
        with b.part(T_NONE, 0.45, "tr"):
            lathe_on(bm, [(0.035, Z_AF + 0.036), (0.037, Z_AF + 0.039), (0.037, Z_AF + 0.122),
                          (0.035, Z_AF + 0.125)], 20, IRON_IDX, K, Z)
        with b.part(T_NONE, 0.5, "tr"):
            lathe_on(bm, [(0.031, Z_AF + 0.029), (0.031, Z_AF + 0.037)], 20, STEEL_IDX, K, Z)
        with b.part(T_NONE, 0.55, "tr"):
            lathe_on(bm, [(0.034, Z_AF - 0.050), (0.036, Z_AF - 0.047), (0.036, Z_AF + 0.027),
                          (0.034, Z_AF + 0.030)], 20, IRON_IDX, K, Z)
        with b.part(T_NONE, 0.5, "tr"):
            add_rod(bm, K, Z, Z_AF - 0.062, Z_AF + 0.134, 0.015, STEEL_IDX, segs=12, ch=0.002)
        with b.part(T_NONE, 0.5, "tr"):
            add_hex(bm, K, -Z, -(Z_AF - 0.0495), -(Z_AF - 0.0610), 0.0230, STEEL_IDX)
        with b.part(T_NONE, 0.5, "tr"):
            lathe_on(bm, [(0.022, Z_AF + 0.124), (0.022, Z_AF + 0.133), (0.016, Z_AF + 0.140),
                          (0.006, Z_AF + 0.142)], 14, ZINC_IDX, K, Z)
        with b.part(T_STUB, 0.5, "tr"):
            lathe_on(bm, [(0.028, KP_Y), (0.028, 0.560), (0.024, 0.565), (0.024, 0.655),
                          (0.020, 0.660)], 20, STEEL_IDX, Vector((AX_F, 0.0, Z_AF)), Y * s, ref=X)
        with b.part(T_HUB_F, 0.5, "tr"):
            lathe_on(bm, [(0.040, 0.557), (0.046, 0.561), (0.046, 0.592), (0.084, 0.594),
                          (0.088, 0.598), (0.088, 0.6035), (0.036, 0.6055)], 32, IRON_IDX,
                     Vector((AX_F, 0.0, Z_AF)), Y * s, ref=X)
        with b.part(T_NONE, 0.5, "tr"):
            lathe_on(bm, [(0.034, 0.600), (0.034, 0.648), (0.030, 0.660), (0.016, 0.664)], 20,
                     ZINC_IDX, Vector((AX_F, 0.0, Z_AF)), Y * s, ref=X)
        # steering arm back from the knuckle, flat, its eye on a vertical pin
        za = Z_AF - 0.025
        root = Vector((AX_F, s * KP_Y, za))
        E = Vector((AX_F - 0.150, s * 0.470, za))
        dirn = (E - root).normalized()
        wax = Vector((-dirn.y, dirn.x, 0.0))
        with b.part(T_NONE, 0.5, "tr"):
            add_bar(bm, [root, E + dirn * 0.016], wax, 0.016, 0.007, 0.003, STEEL_IDX)
        ends[s] = E
    # tie rod: eyes on vertical pins at the arms' ends
    zc = Z_AF - 0.018 + 0.007
    for s in (-1.0, 1.0):
        E = ends[s]
        with b.part(T_EYE, 0.5, "tr"):
            lathe_on(bm, [(0.015, Z_AF - 0.0185), (0.018, Z_AF - 0.0160), (0.018, Z_AF - 0.0070),
                          (0.015, Z_AF - 0.0045)], 16, STEEL_IDX, Vector((E.x, E.y, 0.0)), Z)
        with b.part(T_PIN, 0.5, "tr"):
            lathe_on(bm, [(0.0070, Z_AF - 0.040), (0.0070, Z_AF + 0.004)], 10, STEEL_IDX,
                     Vector((E.x, E.y, 0.0)), Z)
        with b.part(T_NONE, 0.5, "tr"):
            add_hex(bm, Vector((E.x, E.y, 0.0)), Z, Z_AF - 0.0050, Z_AF + 0.0015, 0.0110, STEEL_IDX)
        with b.part(T_NONE, 0.5, "tr"):
            add_hex(bm, Vector((E.x, E.y, 0.0)), -Z, -(Z_AF - 0.0315), -(Z_AF - 0.0385), 0.0110,
                    STEEL_IDX)
    a, bb = Vector((ends[1.0].x, ends[1.0].y, zc)), Vector((ends[-1.0].x, ends[-1.0].y, zc))
    with b.part(T_NONE, 0.5, "tr"):
        add_tube(bm, [a + (bb - a).normalized() * 0.006, bb - (bb - a).normalized() * 0.006], 0.011,
                 12, STEEL_IDX)
    for p, sg in ((a, 1.0), (bb, -1.0)):
        with b.part(T_NONE, 0.5, "tr"):
            add_hex(bm, p + (bb - a).normalized() * sg * 0.060, (bb - a).normalized(), -0.005,
                    0.005, 0.0140, STEEL_IDX)


# --------------------------------------------------------------------------
# Wheels
# --------------------------------------------------------------------------

def rear_crown_r(w):
    w = abs(w)
    for (w0, r0), (w1, r1) in zip(REAR_CROWN, REAR_CROWN[1:]):
        if w <= w1:
            return r0 + (r1 - r0) * (w - w0) / (w1 - w0)
    return REAR_CROWN[-1][1]


def rear_tyre_profile(bite):
    rim = RIM_R
    rs = rim["RS"] - bite
    rfl, wf = rim["RFL"], rim["Wf"]
    half = [(0.5920, 0.030), (0.5905, 0.070), (0.5860, 0.100), (0.5780, 0.120), (0.5640, 0.133),
            (0.5420, 0.1405), (0.5050, 0.1425), (0.4600, 0.1400), (0.4250, 0.1345),
            (0.4000, 0.1320), (rfl + 0.008, 0.1285), (rfl + 0.0015, wf - 0.0006),
            (rim["RS"] + 0.003, wf - 0.0012), (rs, wf - 0.004), (rs, wf - 0.020)]
    return half + [(r, -w) for r, w in reversed(half)]


def front_tyre_profile(bite):
    rim = RIM_F
    rs = rim["RS"] - bite
    rfl, wf = rim["RFL"], rim["Wf"]
    half = [(0.3450, 0.006), (0.3440, 0.0085), (0.3340, 0.0105), (0.3335, 0.0145),
            (0.3410, 0.0165), (0.3420, 0.0290), (0.3395, 0.0350), (0.3330, 0.0415),
            (0.3210, 0.0475), (0.3020, 0.0520), (0.2820, 0.0525), (0.2700, 0.0480),
            (rfl + 0.004, 0.0440), (rfl + 0.0012, wf - 0.0006), (rim["RS"] + 0.002, wf - 0.0010),
            (rs, wf - 0.004), (rs, wf - 0.012)]
    return half + [(r, -w) for r, w in reversed(half)]


def rim_ring_profile(rim):
    RS, RFL, RD, t = rim["RS"], rim["RFL"], rim["RD"], rim["t"]
    Wf, Wo, ww = rim["Wf"], rim["Wo"], rim["well"]
    plus = [(RFL - 0.002, Wo), (RFL, Wo - 0.002), (RFL, Wf + 0.001), (RFL - 0.0015, Wf),
            (RS + 0.003, Wf), (RS, Wf - 0.003), (RS, ww + 0.012), (RS - 0.006, ww + 0.004),
            (RD, ww)]
    outer = plus + [(r, -w) for r, w in reversed(plus)]
    inner = [(RS - t, -Wo), (RS - t, -(ww + 0.014)), (RD - t, -(ww - 0.002)),
             (RD - t, ww - 0.002), (RS - t, ww + 0.014), (RS - t, Wo)]
    return outer + inner


def lug_theta(n, h):
    """The bar's apex (centre-end) angle round the spin axis: the halves are
    staggered by half a pitch."""
    pitch = 2.0 * math.pi / LUGS_PER_HALF
    phase = math.pi + LUG_SWEEP * (0.85 * 0.20 + 0.15 * 0.04)
    return phase + (n + (0.5 if h < 0 else 0.0)) * pitch


def build_lugs(b, C, spin, groups, lift=0.0, tall=0.0, bunch=False):
    """Chevron bars on a rear tyre. The spin axis is the world's +Y for both
    tyres: forward travel turns both wheels the same way. Each bar runs from
    its apex over the centre line back round the tyre to the shoulder, so the
    apex meets the ground first. ``spin`` -1 builds the tread about the
    wheel's own outboard axis instead, which on the right-hand wheel turns the
    tyre round."""
    bm = b.bm
    for h in (1.0, -1.0):
        for n in range(LUGS_PER_HALF):
            th_a = lug_theta(n, h)
            if bunch and h < 0 and n % 4 == 1:
                th_a -= math.radians(BUNCH_DEG)
            rings = []
            for t in LUG_ST:
                w = h * (-LUG_X + t * (LUG_END + LUG_X))
                rc = rear_crown_r(w)
                hgt = LUG_H * (1.0 - 0.40 * smoothstep(0.78, 1.0, t)) + tall
                root = rc - LUG_BITE + lift
                top = rc + hgt + lift
                th = th_a - LUG_SWEEP * (0.85 * t + 0.15 * t * t)
                sec = [(-LUG_BW, root), (LUG_BW, root), (LUG_TW, top - LUG_CH),
                       (LUG_TW - LUG_CH, top), (-LUG_TW + LUG_CH, top), (-LUG_TW, top - LUG_CH)]
                ring = []
                for dt, rr in sec:
                    a = th + dt / rc
                    ring.append(C + Vector((spin * rr * math.sin(a), spin * w, rr * math.cos(a))))
                rings.append(ring)
            with b.part(T_LUG, 0.5, *groups):
                add_loft(bm, rings, RUBBER_IDX)


def add_valve(b, C, rot, w, groups, r_well):
    av = math.radians(38.0)
    base = C + rot @ Vector((0.0, r_well - 0.002, w))
    vdir = rot @ Vector((0.0, -math.sin(av), math.cos(av)))
    with b.part(T_NONE, 0.5, *groups):
        lathe_on(b.bm, [(0.0042, 0.0), (0.0045, 0.006), (0.0036, 0.024), (0.0036, 0.028)], 10,
                 RUBBER_IDX, base, vdir)
    with b.part(T_NONE, 0.5, *groups):
        lathe_on(b.bm, [(0.0050, 0.0265), (0.0054, 0.028), (0.0054, 0.036), (0.0040, 0.0375)], 10,
                 ZINC_IDX, base, vdir)


def build_rear_wheel(b, s, flags):
    bm = b.bm
    side = "L" if s > 0 else "R"
    gw = "wheelR" + side
    dx = -SKEW_WHEEL if (flags["skew_wheel"] and s > 0) else 0.0
    dy = s * WIDE_TRACK if flags["wide_track"] else 0.0
    C = Vector((AX_R + dx, s * RUT_Y + dy, Z_AR))
    ax = Y * s
    rot = frame(ax, Z)
    bite = SINK_BITE if (flags["sink_tyre"] and s < 0) else TYRE_BITE
    with b.part(T_TYRE, 0.40 if s > 0 else 0.60, "tr", gw, "tyre_R" + side):
        add_lathe(bm, rear_tyre_profile(bite), TYRE_SEGS_R, RUBBER_IDX, center=C, rot=rot)
    spin = -1.0 if (flags["reverse_lugs"] and s < 0) else 1.0
    build_lugs(b, C, spin, ("tr", gw, "lugs_R" + side),
               lift=FLOAT_LUGS if (flags["float_lugs"] and s > 0) else 0.0,
               tall=TALL_LUGS if flags["tall_lugs"] else 0.0,
               bunch=flags["bunch_lugs"] and s < 0)
    with b.part(T_RIM, 0.5, "tr", gw):
        add_lathe(bm, rim_ring_profile(RIM_R), RIM_SEGS_R, WHEEL_IDX, center=C, rot=rot,
                  phase=math.pi / RIM_SEGS_R)
    with b.part(T_NONE, 0.45, "tr", gw):
        add_lathe(bm, thick_profile(DISC_R, 0.006), 64, WHEEL_IDX, center=C, rot=rot,
                  phase=0.0173)
    # clamp lugs welded in the rim's well, bolted through the disc
    for k in range(8):
        a = 2.0 * math.pi * (k + 0.5) / 8
        e_r = rot @ Vector((math.cos(a), math.sin(a), 0.0))
        e_t = rot @ Vector((-math.sin(a), math.cos(a), 0.0))
        lrot = Matrix((e_t, ax, e_r)).transposed()   # local (u, v, w) -> (tangent, axis, radial)
        with b.part(T_NONE, 0.5, "tr", gw):
            add_rbox(bm, 0.022, 0.015, 0.005, [(0.002, 0.0), (0.0, 0.002), (0.0, 0.0255)],
                     C + e_r * 0.296 + ax * (-0.021), lrot, WHEEL_IDX, n_corner=2)
        with b.part(T_NONE, 0.5, "tr", gw):
            add_hex(bm, C + e_r * 0.306, ax, -0.0072 - 0.0001 * k, -0.0005 + 0.0002 * k, 0.0085,
                    STEEL_IDX, phase=a)
    # wheel nuts on the disc
    for k in range(8):
        a = 2.0 * math.pi * k / 8 + 0.11
        p = C + rot @ Vector((0.100 * math.cos(a), 0.100 * math.sin(a), 0.0))
        with b.part(T_NONE, 0.5, "tr", gw):
            add_hex(bm, p, ax, -0.0557 - 0.00005 * k, -0.0440 + 0.0001 * k, 0.0120, STEEL_IDX,
                    phase=a)
    # cast-iron weights: two half-moons on the disc, three bolts each
    g = 0.007
    for half, (lo, hi) in enumerate(((-0.5 * math.pi, 0.5 * math.pi),
                                     (0.5 * math.pi, 1.5 * math.pi))):
        ro, ri = 0.225, 0.132
        ao, ai = math.asin(g / ro), math.asin(g / ri)
        outline = []
        for k in range(22):
            a = lo + ao + (hi - lo - 2 * ao) * k / 21
            outline.append((ro * math.cos(a), ro * math.sin(a)))
        for k in range(12):
            a = hi - ai - (hi - lo - 2 * ai) * k / 11
            outline.append((ri * math.cos(a), ri * math.sin(a)))
        if poly_area(outline) < 0.0:
            outline.reverse()
        e = 0.0003 * half
        with b.part(T_NONE, 0.35 + 0.3 * half, "tr", gw):
            add_prism(bm, outline, -0.0550 + e, -0.0100 + e, C, rot, IRON_IDX, ch=0.003)
        mid = 0.5 * (lo + hi)
        for k, da in enumerate((-0.75, 0.0, 0.75)):
            a = mid + da
            p = C + rot @ Vector((0.180 * math.cos(a), 0.180 * math.sin(a), 0.0))
            with b.part(T_NONE, 0.5, "tr", gw):
                add_hex(bm, p, ax, -0.0105 + e + 0.0001 * k, -0.0010 + e + 0.0001 * k, 0.0130,
                        STEEL_IDX, phase=a)
        # a cast grip on the weight's face
        a = mid
        gp = C + rot @ Vector((0.205 * math.cos(a), 0.205 * math.sin(a), -0.0110 + e))
        e_t = rot @ Vector((-math.sin(a), math.cos(a), 0.0))
        with b.part(T_NONE, 0.5, "tr", gw):
            add_bar(bm, [gp - e_t * 0.045, gp - e_t * 0.035 + ax * 0.0173, gp + e_t * 0.035 + ax * 0.0173,
                         gp + e_t * 0.045], rot @ Vector((math.cos(a), math.sin(a), 0.0)), 0.008,
                    0.006, 0.003, IRON_IDX, fillet=0.010)
    add_valve(b, C, rot, 0.030, ("tr", gw), RIM_R["RD"])


def build_front_wheel(b, s, flags):
    bm = b.bm
    side = "L" if s > 0 else "R"
    gw = "wheelF" + side
    C = Vector((AX_F, s * 0.5 * TRACK_F, Z_AF))
    ax = Y * s
    rot = frame(ax, Z)
    with b.part(T_TYRE, 0.45 if s > 0 else 0.55, "tr", gw, "tyre_F" + side):
        add_lathe(bm, front_tyre_profile(TYRE_BITE), TYRE_SEGS_F, RUBBER_IDX, center=C, rot=rot)
    with b.part(T_RIM, 0.5, "tr", gw):
        add_lathe(bm, rim_ring_profile(RIM_F), RIM_SEGS_F, WHEEL_IDX, center=C, rot=rot,
                  phase=math.pi / RIM_SEGS_F)
    with b.part(T_NONE, 0.45, "tr", gw):
        add_lathe(bm, thick_profile(DISC_F, 0.005), 48, WHEEL_IDX, center=C, rot=rot,
                  phase=0.0211)
    for k in range(5):
        a = 2.0 * math.pi * k / 5 + 0.2
        p = C + rot @ Vector((0.065 * math.cos(a), 0.065 * math.sin(a), 0.0))
        with b.part(T_NONE, 0.5, "tr", gw):
            add_hex(bm, p, ax, -0.0030 - 0.0001 * k, 0.0070 + 0.0001 * k, 0.0090, STEEL_IDX,
                    phase=a)
    add_valve(b, C, rot, 0.006, ("tr", gw), RIM_F["RD"])
    if flags["float_tyre"] and s > 0:
        for v in b.groups["tyre_F" + side]:
            v.co.z += FLOAT_TYRE


# --------------------------------------------------------------------------
# Bodywork
# --------------------------------------------------------------------------

def hood_path(n_corner):
    pts = [Vector((HW, HB)), Vector((HW, HB + 0.5 * (HT - HR - HB)))]
    for p in body_section(HW, HB, HT, HR, 0.01, CROWN, 3 * n_corner, top_n=10):
        if p[1] >= HT - HR - 1e-9:
            pts.append(Vector(p))
    # body_section starts on the right corner and runs over the top leftward
    pts += [Vector((-HW, HB + 0.5 * (HT - HR - HB))), Vector((-HW, HB))]
    out = []
    for p in pts:
        if not out or (p - out[-1]).length > 1e-6:
            out.append(p)
    return resample(out, 34 + 6 * n_corner)


def build_bonnet(b, n_corner):
    bm = b.bm
    path = hood_path(n_corner)
    nu = len(path) - 1

    def surf(u, v):
        i = min(int(round(u * nu)), nu)
        p2 = path[i]
        a = path[max(i - 1, 0)]
        c = path[min(i + 1, nu)]
        t = (c - a).normalized()
        n2 = Vector((t.y, -t.x))
        x = HX0 + (HX1 - HX0) * v
        n = Vector((0.0, n2.x, n2.y))
        # outward: away from the section's centre
        if n.dot(Vector((0.0, p2.x, p2.y - 0.95))) < 0.0:
            n = -n
        return Vector((x, p2.x, p2.y)), n
    with b.part(T_NONE, 0.5, "tr"):
        add_sheet(bm, surf, nu, 14, 0.003, PAINT_IDX)
    # a zinc trim strip down the bonnet's crown, its ends tucked under
    zt = top_z(HW, HT, HR, CROWN, 0.0)
    with b.part(T_NONE, 0.5, "tr"):
        add_bar(bm, [Vector((HX0 + 0.030, 0.0, zt - 0.004)), Vector((HX0 + 0.050, 0.0, zt + 0.0012)),
                     Vector((HX1 - 0.040, 0.0, zt + 0.0012)), Vector((HX1 - 0.020, 0.0, zt - 0.004))],
                Y, 0.010, 0.0020, 0.0012, ZINC_IDX, fillet=0.015)
    # the bonnet's side louvres: pressed lips leaning out at the top, three a
    # side, each a step longer (level lips of one length share their planes)
    for s in (-1.0, 1.0):
        for k in range(3):
            z = 0.935 + 0.034 * k
            x0, x1 = 0.520 - 0.006 * k, 0.760 + 0.004 * k
            with b.part(T_NONE, 0.5, "tr"):
                add_bar(bm, [Vector((x0, s * (HW - 0.0015), z)), Vector((x0 + 0.022, s * (HW + 0.0045), z)),
                             Vector((x1 - 0.022, s * (HW + 0.0045), z)), Vector((x1, s * (HW - 0.0015), z))],
                        Vector((0.0, s * 0.30, 0.954)), 0.009, 0.0022, 0.0015, PAINT_IDX, fillet=0.012)


def tank_section(d, n_corner):
    return body_section(HW + 0.004 - d, 0.836 + d, HT + 0.004 - d, HR + 0.004 - d, 0.020 - d, CROWN,
                        n_corner * 2, top_n=10)


def build_tank_dash(b, n_corner):
    bm = b.bm
    prof = [(0.006, 0.022), (0.0, 0.028), (0.0, 0.040), (0.0, 0.247), (0.0, 0.259), (0.006, 0.265)]
    loops = [[Vector((x, y, z)) for y, z in tank_section(d, n_corner)] for d, x in prof]
    with b.part(T_NONE, 0.5, "tr"):
        add_loft(bm, loops, PAINT_IDX)
    ztop = top_z(HW + 0.004, HT + 0.004, HR + 0.004, CROWN, 0.0)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.030, ztop - 0.012), (0.030, ztop + 0.022), (0.034, ztop + 0.026)], 20,
                 STEEL_IDX, Vector((0.160, 0.0, 0.0)), Z)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.041, ztop + 0.023), (0.043, ztop + 0.027), (0.043, ztop + 0.038),
                      (0.036, ztop + 0.045), (0.012, ztop + 0.048)], 24, ZINC_IDX,
                 Vector((0.160, 0.0, 0.0)), Z)
    for k in range(4):
        a = 2.0 * math.pi * k / 4 + 0.4
        p = Vector((0.160 + 0.043 * math.cos(a), 0.043 * math.sin(a), ztop + 0.030))
        with b.part(T_NONE, 0.5, "tr"):
            add_rod(bm, p, Vector((math.cos(a), math.sin(a), 0.0)), -0.004, 0.006, 0.0040, ZINC_IDX,
                    segs=8)
    # dash panel behind the tank, the column through it, gauges and switches
    dash = [(y, z) for y, z in body_section(0.215, 0.620, 1.085, 0.080, 0.020, 0.0, n_corner * 2,
                                            top_n=6)]
    loops = [[Vector((x, y + 0.0, z)) for y, z in (dash if d == 0.0 else
                                                  body_section(0.215 - d, 0.620 + d, 1.085 - d,
                                                               0.080 - d, 0.020 - d, 0.0,
                                                               n_corner * 2, top_n=6))]
             for d, x in ((0.003, 0.004), (0.0, 0.007), (0.0, 0.027), (0.003, 0.030))]
    with b.part(T_NONE, 0.5, "tr"):
        add_loft(bm, loops, PAINT_IDX)
    for k, yy in enumerate((0.090, -0.090)):
        c = Vector((0.0045, yy, 0.975))
        with b.part(T_NONE, 0.5, "tr"):
            lathe_on(bm, [(0.034, -0.003), (0.038, 0.001), (0.038, 0.010), (0.034, 0.014)], 24,
                     BLACK_IDX, c, -X)
        with b.part(T_NONE, 0.5, "tr"):
            lathe_on(bm, [(0.030, 0.0125), (0.0395, 0.0130), (0.0395, 0.0180), (0.0320, 0.0205)], 24,
                     ZINC_IDX, c, -X, solid=False)
        with b.part(T_NONE, 0.2, "tr"):
            lathe_on(bm, [(0.0310, 0.0120), (0.0310, 0.0165)], 24, GLASS_IDX, c, -X)
    for k, (yy, zz, r) in enumerate(((0.000, 1.030, 0.014), (0.150, 0.800, 0.011),
                                     (-0.150, 0.800, 0.011))):
        c = Vector((0.0045, yy, zz))
        with b.part(T_NONE, 0.5, "tr"):
            lathe_on(bm, [(r, -0.002), (r, 0.012), (r * 0.8, 0.016)], 16, ZINC_IDX, c, -X)
        with b.part(T_NONE, 0.5, "tr"):
            lathe_on(bm, [(r * 0.45, 0.014), (r * 0.45, 0.030), (r * 0.9, 0.032), (r * 0.9, 0.044),
                          (r * 0.6, 0.048)], 12, BLACK_IDX, c, -X)


def grille_section(d, n_corner):
    return body_section(0.240 - d, 0.560 + d, 1.140 - d, 0.100 - d, 0.030 - d, CROWN,
                        n_corner * 2, top_n=10)


def build_grille(b, n_corner):
    bm = b.bm
    prof = [(0.006, 0.940), (0.0, 0.940), (0.0, 0.946), (0.0, 1.170), (0.0, 1.176), (0.0015, 1.1845),
            (0.0040, 1.1885), (0.0060, 1.1850), (0.0060, 1.176), (0.0060, 0.946)]
    loops = [[Vector((x, y, z)) for y, z in grille_section(d, n_corner)] for d, x in prof]
    with b.part(T_NONE, 0.5, "tr"):
        add_ring_loft(bm, loops, PAINT_IDX)
    # vertical bars in the opening, biting the shell's top and bottom walls
    # each bar a further step in x and z from the centre out, so neighbours
    # do not share planes and mirrored bars still match
    for k in range(11):
        y = -0.200 + 0.040 * k
        j = min(k, 10 - k)
        zt = top_z(0.234, 1.134, 0.094, CROWN, y) + 0.003
        z0 = 0.5625 - 0.00023 * j
        with b.part(T_NONE, 0.5, "tr"):
            add_rbox(bm, 0.012, 0.004, 0.0025, chamfered(zt - z0, 0.001), (1.164 - 0.00041 * j, y, z0),
                     I3, PAINT_IDX, n_corner=2)
    # radiator core, top tank, filler neck and cap
    with b.part(T_NONE, 0.5, "tr"):
        box(bm, (0.955, -0.236, 0.585), (1.012, 0.236, 1.058), CORE_IDX, rc=0.004, ch=0.002)
    with b.part(T_NONE, 0.5, "tr"):
        box(bm, (0.948, -0.200, 1.052), (1.019, 0.200, 1.100), BLACK_IDX, rc=0.020, ch=0.006)
    zt = top_z(0.240, 1.140, 0.100, CROWN, 0.0)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.020, 1.095), (0.020, zt + 0.010), (0.024, zt + 0.013)], 16, STEEL_IDX,
                 Vector((0.985, 0.0, 0.0)), Z)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.030, zt + 0.011), (0.032, zt + 0.014), (0.032, zt + 0.022), (0.026, zt + 0.028),
                      (0.008, zt + 0.030)], 20, ZINC_IDX, Vector((0.985, 0.0, 0.0)), Z)
    # headlamps on brackets off the shell's sides
    for s in (-1.0, 1.0):
        c = Vector((1.030, s * 0.320, 0.960))
        with b.part(T_NONE, 0.5, "tr"):
            lathe_on(bm, [(0.014, -0.064), (0.042, -0.058), (0.062, -0.042), (0.072, -0.016),
                          (0.074, 0.008), (0.071, 0.013)], 28, PAINT_IDX, c, X, ref=Z)
        with b.part(T_NONE, 0.5, "tr"):
            lathe_on(bm, [(0.060, 0.006), (0.0765, 0.009), (0.0775, 0.019), (0.070, 0.025),
                          (0.061, 0.023)], 28, ZINC_IDX, c, X, solid=False, ref=Z)
        with b.part(T_NONE, 0.1, "tr"):
            lathe_on(bm, [(0.0625, 0.011), (0.0630, 0.018), (0.052, 0.025), (0.030, 0.029),
                          (0.006, 0.0305)], 28, GLASS_IDX, c, X, ref=Z)
        with b.part(T_NONE, 0.5, "tr"):
            add_bar(bm, [c + Vector((-0.040, -s * 0.050, -0.012)), Vector((0.985, s * 0.2385, 0.935))],
                    Z, 0.015, 0.0040, 0.002, STEEL_IDX)


def fender_path():
    pts = [(0.470, -0.020), (0.472, -0.008), (0.480, 0.000), (0.500, 0.0045), (0.580, 0.0085),
           (0.660, 0.0100), (0.740, 0.0085), (0.810, 0.0040), (0.832, -0.0040),
           (0.845, -0.0200), (0.850, -0.0400), (0.850, -0.0750)]
    return resample([Vector(p) for p in pts], 26)


_FPATH = None


def fender_point(s, u, v, odd=0.0):
    """Mudguard outer surface and outward normal: ``u`` across the section
    (inner edge to the skirt's foot), ``v`` along the arc (rear to front)."""
    global _FPATH
    if _FPATH is None:
        _FPATH = fender_path()
    path = _FPATH
    nu = len(path) - 1
    f = u * nu
    i = min(int(f), nu - 1)
    t = f - i
    p2 = path[i] * (1 - t) + path[i + 1] * t
    tg = (path[i + 1] - path[i]).normalized()
    th = math.radians(FENDER_TH[0] + (FENDER_TH[1] - FENDER_TH[0]) * v)
    yr = p2.x
    if odd and s > 0:
        thd = math.degrees(th)
        if -20.0 < thd < 40.0:
            yr += odd * math.cos(math.pi * (thd - 10.0) / 60.0) ** 2
    r = R_F + p2.y
    er = Vector((math.sin(th), 0.0, math.cos(th)))
    p = Vector((AX_R, 0.0, Z_AR)) + er * r + Vector((0.0, s * yr, 0.0))
    # normal: the section's own normal in (y, r), turned into the radial plane
    # the path's left normal: out of the crown, out of the skirt, in off the lip
    n2 = Vector((-tg.y, tg.x))
    n = Vector((0.0, s * n2.x, 0.0)) + er * n2.y
    return p, n.normalized()


def build_fenders(b, flags):
    bm = b.bm
    for s in (-1.0, 1.0):
        odd = ODD_FENDER if flags["odd_fender"] else 0.0

        def surf(u, v, s=s, odd=odd):
            return fender_point(s, u, v, odd)
        with b.part(T_NONE, 0.5 if s > 0 else 0.55, "tr"):
            add_sheet(bm, surf, 25, 40, 0.003, PAINT_IDX)


def build_footplates(b):
    bm = b.bm
    for s in (-1.0, 1.0):
        outline = [(x, s * y) for x, y in rrect(0.185, 0.1675, 0.020, 3)]
        outline = [(x - 0.065, y + s * 0.3375) for x, y in outline]
        if poly_area(outline) < 0.0:
            outline.reverse()
        with b.part(T_NONE, 0.5, "tr"):
            add_plate(bm, outline, 0.462, 0.470, 0.010, PAINT_IDX)
        # bare-steel anti-slip strips, worn bright by boots
        for k in range(5):
            x = -0.215 + 0.070 * k
            with b.part(T_NONE, 0.5, "tr"):
                add_bar(bm, [Vector((x, s * 0.195, 0.4695)), Vector((x + 0.030, s * 0.470, 0.4695))], X,
                        0.009, 0.0030, 0.0012, STEEL_IDX)
        # a turned-up lip along the outer edge
        with b.part(T_NONE, 0.5, "tr"):
            add_bar(bm, [Vector((-0.235, s * 0.498, 0.4665)), Vector((0.105, s * 0.498, 0.4665))], Z,
                    0.012, 0.0030, 0.0015, PAINT_IDX)
        for k, x in enumerate((-0.180, 0.060)):
            with b.part(T_NONE, 0.5, "tr"):
                add_bar(bm, [Vector((x, s * 0.150, 0.520 + 0.0003 * k)), Vector((x, s * 0.200, 0.470)),
                             Vector((x, s * 0.380, 0.4605))], X, 0.015, 0.004, 0.002, STEEL_IDX,
                        fillet=0.03)


# --------------------------------------------------------------------------
# Engine accessories: exhaust, pre-cleaner, dynamo and belt, starter, filter
# --------------------------------------------------------------------------

def chain_tangent(ca, ra, cb, rb):
    d = cb - ca
    dist = d.length
    dh = d / dist
    dp = Vector((-dh.y, dh.x))
    k = (rb - ra) / dist
    s = math.sqrt(max(0.0, 1.0 - k * k))
    n = dh * k + dp * s
    return ca - n * ra, cb - n * rb


def belt_path(circles, step=0.008):
    """An open-belt loop round convex circles [(centre2d, r)] in order,
    sampled every ``step`` of arc length (after go-kart's chain path)."""
    n = len(circles)
    deps, arrs = [None] * n, [None] * n
    for i in range(n):
        ca, ra = circles[i]
        cb, rb = circles[(i + 1) % n]
        pa, pb = chain_tangent(ca, ra, cb, rb)
        deps[i] = pa
        arrs[(i + 1) % n] = pb
    out = []
    for i in range(n):
        c, r = circles[i]
        a0 = math.atan2(arrs[i].y - c.y, arrs[i].x - c.x)
        a1 = math.atan2(deps[i].y - c.y, deps[i].x - c.x)
        sweep = (a1 - a0) % (2.0 * math.pi)
        m = max(2, int(sweep * r / step))
        for k in range(m):
            a = a0 + sweep * k / m
            out.append(c + Vector((math.cos(a), math.sin(a))) * r)
        p0, p1 = deps[i], arrs[(i + 1) % n]
        m = max(1, int((p1 - p0).length / (4 * step)))
        for k in range(m):
            out.append(p0 + (p1 - p0) * (k / m))
    return out


def add_pulley(b, c, r, groups=("tr",)):
    prof = [(r - 0.010, 0.0), (r, 0.002), (r, 0.004), (r - 0.009, 0.011), (r, 0.018), (r, 0.020),
            (r - 0.010, 0.022)]
    with b.part(T_NONE, 0.5, *groups):
        lathe_on(b.bm, prof, 28, STEEL_IDX, c, X, ref=Z)


def build_accessories(b):
    bm = b.bm
    xp = 0.664
    # crank nose and pulley; water pump, its pulley, shaft and fan; dynamo
    with b.part(T_NONE, 0.5, "tr"):
        add_rod(bm, Vector((0.0, 0.0, 0.500)), X, 0.648, 0.672, 0.030, STEEL_IDX, segs=16)
    add_pulley(b, Vector((xp, 0.0, 0.500)), 0.060)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.050, 0.618), (0.050, 0.646), (0.034, 0.656), (0.030, 0.662)], 20, IRON_IDX,
                 Vector((0.0, 0.0, 0.780)), X, ref=Z)
    add_pulley(b, Vector((xp, 0.0, 0.780)), 0.055)
    with b.part(T_NONE, 0.5, "tr"):
        add_rod(bm, Vector((0.0, 0.0, 0.780)), X, 0.660, 0.905, 0.012, STEEL_IDX, segs=12)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.042, 0.880), (0.042, 0.912), (0.030, 0.918)], 20, STEEL_IDX,
                 Vector((0.0, 0.0, 0.780)), X, ref=Z)
    for k in range(4):
        a = 2.0 * math.pi * k / 4 + 0.35
        e = Vector((0.0, math.cos(a), math.sin(a)))
        t = Vector((0.0, -math.sin(a), math.cos(a)))
        wax = (t * math.cos(0.45) + X * math.sin(0.45)).normalized()
        c = Vector((0.896, 0.0, 0.780))
        with b.part(T_NONE, 0.5, "tr"):
            add_bar(bm, [c + e * 0.034, c + e * 0.120, c + e * 0.190], wax, 0.030, 0.0022, 0.004,
                    STEEL_IDX, fillet=0.01)
    dyn = Vector((0.0, -0.200, 0.650))
    with b.part(T_NONE, 0.35, "tr"):
        lathe_on(bm, [(0.040, 0.420), (0.050, 0.425), (0.055, 0.440), (0.055, 0.620), (0.050, 0.634),
                      (0.030, 0.642)], 28, BLACK_IDX, dyn, X, ref=Z)
    with b.part(T_NONE, 0.5, "tr"):
        add_rod(bm, dyn, X, 0.636, 0.680, 0.008, STEEL_IDX, segs=10)
    add_pulley(b, Vector((xp, -0.200, 0.650)), 0.038)
    for k, x in enumerate((0.470, 0.590)):
        with b.part(T_NONE, 0.5, "tr"):
            add_bar(bm, [Vector((x, -0.200, 0.650)), Vector((x, -0.170, 0.640)),
                         Vector((x, -0.140, 0.600 + 0.0005 * k))], X, 0.014, 0.004, 0.002, STEEL_IDX,
                    fillet=0.02)
    # the fan belt round the three pulleys, in the grooves
    xb = xp + 0.011
    circ = [(Vector((0.0, 0.500)), 0.060 - 0.006), (Vector((0.0, 0.780)), 0.055 - 0.006),
            (Vector((-0.200, 0.650)), 0.038 - 0.006)]
    path = belt_path(circ)
    loop = []
    n = len(path)
    for i, p in enumerate(path):
        t = (path[(i + 1) % n] - path[i - 1]).normalized()
        nr = Vector((t.y, -t.x))
        for u, v in rrect(0.0055, 0.0040, 0.0015, 1):
            q = p + nr * v
            loop.append(Vector((xb + u, q.x, q.y)))
    k = len(rrect(0.0055, 0.0040, 0.0015, 1))
    rings = [loop[i * k:(i + 1) * k] for i in range(n)]
    with b.part(T_NONE, 0.5, "tr"):
        add_ring_loft(bm, rings, RUBBER_IDX)
    # starter on the bell housing flange; oil filter on a boss off the block
    with b.part(T_NONE, 0.40, "tr"):
        lathe_on(bm, [(0.030, 0.118), (0.046, 0.122), (0.046, 0.320), (0.040, 0.332), (0.020, 0.338)], 24,
                 BLACK_IDX, Vector((0.0, -0.200, 0.515)), X, ref=Z)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.018, 0.150), (0.022, 0.154), (0.022, 0.250), (0.018, 0.254)], 16, BLACK_IDX,
                 Vector((0.0, -0.200, 0.575)), X, ref=Z)
    with b.part(T_NONE, 0.5, "tr"):
        box(bm, (0.410, -0.172, 0.525), (0.470, -0.145, 0.585), IRON_IDX, rc=0.010, ch=0.003)
    with b.part(T_NONE, 0.30, "tr"):
        lathe_on(bm, [(0.034, 0.470), (0.040, 0.474), (0.040, 0.574), (0.036, 0.580), (0.030, 0.584)], 24,
                 BLACK_IDX, Vector((0.440, -0.205, 0.0)), Z)
    # exhaust manifold on the right, ports into the block; the downpipe to the stack
    with b.part(T_NONE, 0.5, "tr"):
        add_tube(bm, [Vector((0.180, -0.188, 0.745)), Vector((0.560, -0.188, 0.745))], 0.026, 16,
                 EXHAUST_IDX)
    for k in range(4):
        x = 0.220 + 0.100 * k
        with b.part(T_NONE, 0.5, "tr"):
            add_tube(bm, [Vector((x, -0.138, 0.745)), Vector((x, -0.188, 0.745))], 0.018, 12, EXHAUST_IDX)
        with b.part(T_NONE, 0.5, "tr"):
            add_rbox(bm, 0.030, 0.026, 0.006, chamfered(0.012, 0.002), (x, -0.146 - 0.00043 * k, 0.745),
                     frame(-Y, X), EXHAUST_IDX, n_corner=2)
    sx, sy = 0.760, -0.130
    down = [Vector((0.540, -0.188, 0.745)), Vector((0.650, -0.188, 0.752)),
            Vector((0.730, -0.150, 0.790)), Vector((sx, sy, 0.860)), Vector((sx, sy, 0.960))]
    with b.part(T_NONE, 0.5, "tr"):
        add_tube(bm, fillet_path(down, 0.05, 6), 0.029, 14, EXHAUST_IDX)
    # the stack through the bonnet: collar, a silencer barrel, a lip
    zb = top_z(HW, HT, HR, CROWN, sy)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.036, 0.940), (0.036, 1.180), (0.052, 1.200), (0.052, 1.420), (0.036, 1.440),
                      (0.036, 1.628), (0.039, 1.630), (0.039, 1.638), (0.032, 1.640)], 24,
                 EXHAUST_IDX, Vector((sx, sy, 0.0)), Z)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.050, zb - 0.010), (0.056, zb - 0.004), (0.056, zb + 0.006), (0.040, zb + 0.012)],
                 24, ZINC_IDX, Vector((sx, sy, 0.0)), Z)
    # rain cap: a flap hinged at the stack's back, lifted open, with its counterweight
    hinge = Vector((sx - 0.039, sy, 1.638))
    open_a = math.radians(22.0)
    fl = Matrix.Rotation(-open_a, 3, "Y")
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.0045, -0.018), (0.0045, 0.018)], 10, STEEL_IDX, hinge, Y, ref=X)
    fc = hinge + fl @ Vector((0.043, 0.0, 0.002))
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.046, -0.002), (0.047, 0.001), (0.046, 0.003), (0.030, 0.006), (0.004, 0.0072)],
                 24, EXHAUST_IDX, fc, fl @ Z, ref=X)
    with b.part(T_NONE, 0.5, "tr"):
        add_bar(bm, [hinge + fl @ Vector((0.010, 0.0, 0.004)), hinge + fl @ Vector((-0.010, 0.0, 0.0)),
                     hinge + fl @ Vector((-0.030, 0.0, -0.010))], Y, 0.006, 0.0025, 0.001, STEEL_IDX,
                fillet=0.008)
    with b.part(T_NONE, 0.5, "tr"):
        add_rod(bm, hinge + fl @ Vector((-0.034, 0.0, -0.014)), fl @ -X, -0.010, 0.010, 0.010,
                EXHAUST_IDX, segs=12, ch=0.002)
    # air cleaner can in front of the block, its pipe up through the bonnet to
    # the pre-cleaner: a zinc base, a glass bowl, a zinc cap and wing nut
    ac = Vector((0.770, 0.100, 0.0))
    with b.part(T_NONE, 0.35, "tr"):
        lathe_on(bm, [(0.050, 0.600), (0.058, 0.608), (0.058, 0.930), (0.050, 0.940), (0.026, 0.944)], 24,
                 BLACK_IDX, ac, Z)
    with b.part(T_NONE, 0.5, "tr"):
        add_bar(bm, [Vector((0.715, 0.100, 0.700)), Vector((0.690, 0.100, 0.690)),
                     Vector((0.650, 0.100, 0.690))], Z, 0.018, 0.004, 0.002, STEEL_IDX, fillet=0.01)
    zb = top_z(HW, HT, HR, CROWN, ac.y)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.028, 0.935), (0.028, 1.232), (0.032, 1.236)], 20, STEEL_IDX, ac, Z)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.042, zb - 0.010), (0.047, zb - 0.004), (0.047, zb + 0.006), (0.032, zb + 0.012)],
                 20, ZINC_IDX, ac, Z)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.030, 1.226), (0.052, 1.230), (0.058, 1.240), (0.058, 1.256), (0.052, 1.262)], 28,
                 ZINC_IDX, ac, Z)
    with b.part(T_NONE, 0.25, "tr"):
        lathe_on(bm, [(0.050, 1.258), (0.058, 1.268), (0.062, 1.290), (0.061, 1.312), (0.055, 1.330),
                      (0.050, 1.334)], 28, GLASS_IDX, ac, Z)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.050, 1.331), (0.056, 1.334), (0.056, 1.346), (0.044, 1.356), (0.010, 1.360)], 28,
                 ZINC_IDX, ac, Z)
    with b.part(T_NONE, 0.5, "tr"):
        add_rod(bm, ac, Z, 1.352, 1.380, 0.0045, STEEL_IDX, segs=10)
    with b.part(T_NONE, 0.5, "tr"):
        add_bar(bm, [ac + Vector((-0.020, 0.0, 1.372)), ac + Vector((0.0, 0.0, 1.366)),
                     ac + Vector((0.020, 0.0, 1.372))], Y, 0.004, 0.0025, 0.001, ZINC_IDX,
                fillet=0.006)
    with b.part(T_NONE, 0.5, "tr"):
        add_tube(bm, fillet_path([Vector((0.745, 0.150, 0.760)), Vector((0.650, 0.175, 0.745)),
                                  Vector((0.560, 0.182, 0.730))], 0.04, 4), 0.017, 12, RUBBER_IDX)
    with b.part(T_NONE, 0.5, "tr"):
        add_tube(bm, [Vector((0.200, 0.165, 0.725)), Vector((0.575, 0.165, 0.725))], 0.024, 14, IRON_IDX)


# --------------------------------------------------------------------------
# Controls: column and wheel, seat on its spring, levers, pedals
# --------------------------------------------------------------------------

def build_controls(b):
    bm = b.bm
    d = COL_DIR
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.020, -0.030), (0.024, -0.026), (0.024, COL_L - 0.080), (0.021, COL_L - 0.074)],
                 20, PAINT_IDX, COL_B, d, ref=Y)
    with b.part(T_NONE, 0.5, "tr"):
        add_rod(bm, COL_B, d, COL_L - 0.090, COL_L + 0.0095, 0.011, STEEL_IDX, segs=12)
    c = COL_B + d * COL_L
    up = (Z - d * Z.dot(d)).normalized()
    rt = up.cross(d)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.012, -0.034), (0.030, -0.032), (0.036, -0.020), (0.036, 0.004),
                      (0.030, 0.010), (0.012, 0.012)], 24, BLACK_IDX, c, d, ref=up)
    with b.part(T_NONE, 0.5, "tr"):
        add_hex(bm, c, d, 0.0100, 0.0180, 0.0120, ZINC_IDX)
    grip = [(WHEEL_RS + 0.0120 * math.cos(2.0 * math.pi * k / 12),
             0.0125 * math.sin(2.0 * math.pi * k / 12)) for k in range(12)]
    with b.part(T_NONE, 0.5, "tr"):
        add_lathe(bm, grip, 56, BLACK_IDX, center=c + d * 0.030, rot=frame(d, up))
    for ang in (90.0, 210.0, 330.0):
        a = math.radians(ang)
        rad = up * math.sin(a) + rt * math.cos(a)
        tan = d.cross(rad)
        with b.part(T_NONE, 0.5, "tr"):
            add_bar(bm, [c + rad * 0.028 - d * 0.004, c + rad * 0.100 + d * 0.018,
                         c + rad * (WHEEL_RS - 0.002) + d * 0.030], tan, 0.009, 0.0035, 0.002,
                    STEEL_IDX, fillet=0.03)
    # the pan seat: a pressed bowl on a leaf spring
    sc = Vector((-1.150, 0.0, 1.012))
    cl = [(0.022, 0.000), (0.110, 0.004), (0.160, 0.018), (0.190, 0.042), (0.205, 0.070),
          (0.212, 0.092), (0.216, 0.100)]
    with b.part(T_NONE, 0.5, "tr", "seat"):
        vs = add_lathe(bm, thick_profile(cl, 0.0045), 44, BLACK_IDX, center=(0.0, 0.0, 0.0))
    for v in vs:
        lx, ly, lz = v.co.x, v.co.y, v.co.z
        r = math.hypot(lx, ly)
        lz += 0.085 * smoothstep(-0.02, 0.17, -lx) * smoothstep(0.10, 0.20, r)
        v.co = sc + Vector((lx * 0.88, ly, lz))
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.040, -0.004), (0.040, 0.003), (0.034, 0.006)], 20, STEEL_IDX, sc, Z)
    with b.part(T_NONE, 0.5, "tr"):
        box(bm, (-1.165, -0.036, 0.992), (-1.075, 0.036, 1.0125), STEEL_IDX, rc=0.008, ch=0.002)
    leaf = [Vector((-0.735, 0.0, 0.955)), Vector((-0.860, 0.0, 0.990)), Vector((-1.000, 0.0, 1.000)),
            Vector((-1.130, 0.0, 1.002))]
    with b.part(T_NONE, 0.5, "tr"):
        add_bar(bm, leaf, Y, 0.028, 0.006, 0.002, STEEL_IDX, fillet=0.08)
    leaf2 = [p - Vector((0.0, 0.0, 0.0105)) for p in leaf[:3]]
    leaf2[-1] = leaf2[-1] + Vector((0.050, 0.0, 0.004))
    with b.part(T_NONE, 0.5, "tr"):
        add_bar(bm, leaf2, Y, 0.026, 0.005, 0.002, STEEL_IDX, fillet=0.08)
    with b.part(T_NONE, 0.5, "tr"):
        box(bm, (-0.790, -0.036, 0.895), (-0.720, 0.036, 0.952), IRON_IDX, rc=0.010, ch=0.003)
    for k, x in enumerate((-0.745, -0.770)):
        with b.part(T_NONE, 0.5, "tr"):
            add_hex(bm, Vector((x, 0.0, 0.0)), Z, 0.9585 - 0.0003 * k, 0.9665 + 0.0002 * k, 0.0085, STEEL_IDX)
    # gear lever with its boot and knob
    lever = [Vector((-0.330, 0.0, 0.740)), Vector((-0.335, 0.0, 0.840)), Vector((-0.380, 0.030, 0.950)),
             Vector((-0.440, 0.060, 1.010))]
    with b.part(T_NONE, 0.5, "tr"):
        add_tube(bm, fillet_path(lever, 0.06, 5), 0.0085, 10, STEEL_IDX)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.030, 0.765), (0.030, 0.772), (0.020, 0.788), (0.024, 0.796), (0.014, 0.812),
                      (0.017, 0.818), (0.010, 0.832)], 16, RUBBER_IDX, Vector((-0.331, 0.0, 0.0)), Z)
    kd = (lever[-1] - lever[-2]).normalized()
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.006, -0.012), (0.018, -0.008), (0.024, 0.006), (0.020, 0.022), (0.008, 0.030)],
                 16, BLACK_IDX, lever[-1], kd)
    # pedals: pivots on the bell housing, clutch on the left, brake on the right
    for s in (-1.0, 1.0):
        piv = Vector((-0.030, s * 0.182, 0.530))
        with b.part(T_NONE, 0.5, "tr"):
            add_rod(bm, piv, Y * s, -0.012, 0.028, 0.018, IRON_IDX, segs=16, ch=0.002)
        pad = Vector((0.085, s * 0.215, 0.604))
        with b.part(T_NONE, 0.5, "tr"):
            add_bar(bm, [piv + Y * s * 0.020, Vector((0.020, s * 0.205, 0.560)), pad], Y, 0.009, 0.013,
                    0.003, STEEL_IDX, fillet=0.03)
        back = Vector((-0.45, 0.0, 0.89)).normalized()
        with b.part(T_NONE, 0.5, "tr"):
            add_rbox(bm, 0.040, 0.030, 0.008, chamfered(0.008, 0.0015), pad - back * 0.004,
                     frame(back, Y), STEEL_IDX, n_corner=3)
        with b.part(T_NONE, 0.35, "tr"):
            add_rbox(bm, 0.034, 0.024, 0.007, chamfered(0.004, 0.001), pad + back * 0.0032,
                     frame(back, Y), RUBBER_IDX, n_corner=3)


# --------------------------------------------------------------------------
# Three-point linkage, drawbar, PTO
# --------------------------------------------------------------------------

def add_eye(b, c, axis, r, hl, groups=("tr",)):
    with b.part(T_EYE, 0.5, *groups):
        lathe_on(b.bm, [(r - 0.003, -hl), (r, -hl + 0.003), (r, hl - 0.003), (r - 0.003, hl)], 20,
                 STEEL_IDX, c, axis, ref=Z if abs(Vector(axis).z) < 0.9 else X)


def add_pin(b, c, axis, a, bb, r, head=True, groups=("tr",)):
    with b.part(T_PIN, 0.5, *groups):
        lathe_on(b.bm, [(r - 0.0012, a), (r, a + 0.0012), (r, bb - 0.0012), (r - 0.0012, bb)], 12,
                 STEEL_IDX, c, axis, ref=Z if abs(Vector(axis).z) < 0.9 else X)
    if head:
        with b.part(T_NONE, 0.5, *groups):
            add_hex(b.bm, c, axis, bb - 0.010, bb - 0.002, r * 1.6, STEEL_IDX)


def build_hitch(b, flags):
    bm = b.bm
    ll_f = {}
    for s in (-1.0, 1.0):
        # lower-link brackets hung from the trumpet: two cheeks round the eye
        f = Vector((LL_F[0], s * LL_F[1], LL_F[2]))
        for k, dy in enumerate((-0.028, 0.028)):
            y = s * LL_F[1] + dy
            outline = circles_hull([(f.x, f.z, 0.032), (f.x - 0.050, Z_AR - 0.080, 0.012),
                                    (f.x + 0.050, Z_AR - 0.080, 0.012)], 24)
            with b.part(T_NONE, 0.5, "tr"):
                add_prism(bm, outline, y - 0.006 + 0.0002 * k, y + 0.006 + 0.0002 * k, (0.0, 0.0, 0.0),
                          ROT_Y, IRON_IDX, ch=0.0015)
        add_pin(b, f, Y * s, -0.045, 0.050, 0.012)
        add_eye(b, f, Y, 0.030, 0.016)
        r = Vector((LL_R[0], s * LL_R[1], LL_R[2]))
        add_eye(b, r, Y, 0.034, 0.022)
        with b.part(T_NONE, 0.5, "tr"):
            add_bar(bm, [f, r], Z, 0.025, 0.011, 0.004, STEEL_IDX)
        ll_f[s] = (f, r)
        # lift arm, lift rod and their pins
        hub = Vector((LIFT_X, s * ARM_END[1], LIFT_Z))
        with b.part(T_NONE, 0.5, "tr"):
            add_rod(bm, hub, Y * s, -0.020, 0.020, 0.044, STEEL_IDX, segs=20, ch=0.003)
        ae = Vector((ARM_END[0], s * ARM_END[1], ARM_END[2]))
        with b.part(T_NONE, 0.5, "tr"):
            add_bar(bm, [hub, ae], Y, 0.013, 0.024, 0.006, STEEL_IDX)
        add_eye(b, ae, Y, 0.030, 0.013)
        rt = ae + Y * s * 0.030
        add_eye(b, rt, Y, 0.026, 0.011)
        add_pin(b, ae + Y * s * 0.015, Y * s, -0.040, 0.040, 0.011)
        # the rod's foot on the lower link, beside it
        t = (-1.300 - f.x) / (r.x - f.x)
        on = f + (r - f) * t
        rb = on + Y * s * 0.030
        add_eye(b, rb, Y, 0.024, 0.011)
        add_pin(b, on + Y * s * 0.012, Y * s, -0.040, 0.040, 0.011)
        with b.part(T_NONE, 0.5, "tr"):
            dd = (rb - rt).normalized()
            add_tube(bm, [rt + dd * 0.020, rb - dd * 0.020], 0.013, 12, STEEL_IDX)
        if s < 0:
            # levelling box and crank on the right-hand rod
            mid = rt + (rb - rt) * 0.40
            dd = (rb - rt).normalized()
            with b.part(T_NONE, 0.5, "tr"):
                add_rbox(bm, 0.024, 0.020, 0.006, chamfered(0.080, 0.004), mid - dd * 0.040,
                         frame(dd, X), STEEL_IDX, n_corner=2)
            with b.part(T_NONE, 0.5, "tr"):
                add_bar(bm, [mid - dd * 0.030, mid - dd * 0.030 - Y * 0.050,
                             mid - dd * 0.030 - Y * 0.055 + X * 0.070], Z, 0.006, 0.004, 0.002,
                        STEEL_IDX, fillet=0.01)
    # the lift cross-shaft through the cover
    with b.part(T_NONE, 0.5, "tr"):
        add_rod(bm, Vector((LIFT_X, 0.0, LIFT_Z)), Y, -0.255, 0.255, 0.026, STEEL_IDX, segs=20, ch=0.003)
    # drawbar through the lower links' rear eyes: it is their pin
    with b.part(T_PIN, 0.5, "tr"):
        lathe_on(bm, [(0.0175, -0.470), (0.0190, -0.468), (0.0190, 0.468), (0.0175, 0.470)], 16,
                 STEEL_IDX, Vector((LL_R[0], 0.0, LL_R[2])), Y, ref=Z)
    for s in (-1.0, 1.0):
        with b.part(T_NONE, 0.5, "tr"):
            add_rod(bm, Vector((LL_R[0], s * 0.448, LL_R[2])), Z, -0.030, 0.030, 0.0045, STEEL_IDX,
                    segs=8)
    # centre hitch plate on the drawbar, the top link's stowage cheeks and pin
    with b.part(T_NONE, 0.5, "tr"):
        add_rbox(bm, 0.060, 0.040, 0.010, chamfered(0.024, 0.002), Vector((LL_R[0] - 0.050, 0.0,
                                                                          LL_R[2] - 0.012)),
                 I3, STEEL_IDX, n_corner=2)
    for k, dy in enumerate((-0.030, 0.030)):
        outline = circles_hull([(LL_R[0], LL_R[2], 0.024), (TL_R.x, TL_R.z, 0.020)], 20)
        with b.part(T_NONE, 0.5, "tr"):
            add_prism(bm, outline, dy - 0.005 + 0.0002 * k, dy + 0.005 + 0.0002 * k, (0.0, 0.0, 0.0),
                      ROT_Y, STEEL_IDX, ch=0.0012)
    add_pin(b, TL_R, Y, -0.050, 0.050, 0.010)
    # top link: clevis on the housing, pinned eye, turnbuckle, stowed eye
    for k, dy in enumerate((-0.032, 0.032)):
        outline = circles_hull([(TL_F.x, TL_F.z, 0.030), (AX_R - 0.180, 0.850, 0.015),
                                (AX_R - 0.180, 0.740, 0.015)], 20)
        with b.part(T_NONE, 0.5, "tr"):
            add_prism(bm, outline, dy - 0.006 + 0.0002 * k, dy + 0.006 + 0.0002 * k, (0.0, 0.0, 0.0),
                      ROT_Y, IRON_IDX, ch=0.0015)
    add_pin(b, TL_F, Y, -0.052, 0.052, 0.012)
    dl = (TL_R - TL_F).normalized()
    rear = TL_R - dl * (UNPIN if flags["unpin_link"] else 0.0)
    add_eye(b, TL_F, Y, 0.028, 0.018)
    add_eye(b, rear, Y, 0.026, 0.018)
    ln = (rear - TL_F).length
    with b.part(T_NONE, 0.5, "tr"):
        add_rod(bm, TL_F, dl, 0.020, ln - 0.020, 0.0125, STEEL_IDX, segs=12)
    with b.part(T_NONE, 0.40, "tr"):
        lathe_on(bm, [(0.018, 0.30 * ln), (0.024, 0.30 * ln + 0.008), (0.024, 0.70 * ln - 0.008),
                      (0.018, 0.70 * ln)], 16, STEEL_IDX, TL_F, dl)
    for k, fr in enumerate((0.30, 0.70)):
        with b.part(T_NONE, 0.5, "tr"):
            add_hex(bm, TL_F + dl * (fr * ln + (-0.012 if k == 0 else 0.012)), dl, -0.006, 0.006, 0.020,
                    STEEL_IDX)
    with b.part(T_NONE, 0.5, "tr"):
        add_rod(bm, TL_F + dl * (0.5 * ln), Y, -0.060, 0.060, 0.0060, STEEL_IDX, segs=10, ch=0.001)
    # PTO: splined stub out of the rear cover, its shield over it
    spl = []
    for k in range(6):
        a0 = 2.0 * math.pi * k / 6
        for da, r in ((-0.30, 0.0152), (-0.20, 0.0178), (0.20, 0.0178), (0.30, 0.0152)):
            spl.append((r * math.cos(a0 + da), r * math.sin(a0 + da)))
    with b.part(T_NONE, 0.5, "tr"):
        add_prism(bm, spl, 0.180, 0.345, Vector((AX_R, 0.0, 0.550)), frame(-X, Z), STEEL_IDX, ch=0.0012)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.040, 0.205), (0.044, 0.209), (0.044, 0.226), (0.030, 0.232)], 24, IRON_IDX,
                 Vector((AX_R, 0.0, 0.550)), -X, ref=Z)

    def shield(u, v):
        a = math.radians(200.0 - 220.0 * u)
        r = 0.085
        x = AX_R - 0.201 - 0.120 * v
        p = Vector((x, r * math.cos(a), 0.550 + r * math.sin(a) * 0.8))
        n = Vector((0.0, math.cos(a), math.sin(a) * 1.25)).normalized()
        return p, n
    with b.part(T_NONE, 0.5, "tr"):
        add_sheet(bm, shield, 22, 6, 0.003, PAINT_IDX)


def build_lamps(b):
    bm = b.bm
    # tail lamp on the right mudguard's skirt, facing back
    p, n = fender_point(-1.0, 0.96, 0.12)
    base = p - n * 0.0015
    # the lamp stands clear of the skirt: only its bracket touches the mudguard
    lc = base + n * 0.046 + Vector((0.0, 0.0, 0.004))
    with b.part(T_NONE, 0.5, "lamp"):
        add_bar(bm, [base, base + n * 0.026, lc + Vector((0.012, 0.0, 0.0))], X, 0.012, 0.003, 0.0015,
                STEEL_IDX, fillet=0.008)
    with b.part(T_NONE, 0.5, "lamp"):
        lathe_on(bm, [(0.010, -0.034), (0.030, -0.030), (0.036, -0.018), (0.036, 0.004), (0.034, 0.007)],
                 20, ZINC_IDX, lc, -X, ref=Z)
    with b.part(T_NONE, 0.5, "lamp"):
        lathe_on(bm, [(0.029, 0.004), (0.0385, 0.006), (0.0385, 0.012), (0.031, 0.015)], 20, BLACK_IDX,
                 lc, -X, solid=False, ref=Z)
    with b.part(T_NONE, 1.0, "lamp"):
        lathe_on(bm, [(0.0305, 0.006), (0.0305, 0.012), (0.022, 0.017), (0.005, 0.019)], 20, GLASS_IDX,
                 lc, -X, ref=Z)
    # work lamp on the left mudguard, on a stalk, aimed back and down
    p, n = fender_point(1.0, 0.62, 0.22)
    top = p + n * 0.070
    with b.part(T_NONE, 0.5, "tr"):
        add_rod(bm, p, n, -0.0035, 0.075, 0.0085, STEEL_IDX, segs=10)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.020, -0.002), (0.020, 0.004), (0.014, 0.008)], 14, STEEL_IDX, p, n)
    aim = (Vector((-0.80, 0.0, -0.40))).normalized()
    lc = top + aim * 0.012
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.012, -0.034), (0.034, -0.031), (0.050, -0.020), (0.058, 0.002), (0.056, 0.006)],
                 24, ZINC_IDX, lc, aim, ref=Z)
    with b.part(T_NONE, 0.5, "tr"):
        lathe_on(bm, [(0.047, 0.004), (0.060, 0.006), (0.060, 0.013), (0.050, 0.017)], 24, BLACK_IDX,
                 lc, aim, solid=False, ref=Z)
    with b.part(T_NONE, 0.1, "tr"):
        lathe_on(bm, [(0.0485, 0.0045), (0.0485, 0.013), (0.035, 0.019), (0.006, 0.021)], 24, GLASS_IDX,
                 lc, aim, ref=Z)


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def edge_wear(bm):
    """Per-vertex edge wear: how sharp the convex edges through a vertex are
    (0 on a smooth surface or a 45-degree chamfer, 1 on a square edge such
    as a sheet's rolled rim). The paint shaders chip through to primer and
    bare metal where it is high; every part that carries it has a vertex
    ring a few millimetres in from its square edges, so the wear stays on
    the edge rather than being interpolated across a whole face."""
    lay = bm.verts.layers.float.new(WEAR)
    bm.verts.index_update()
    acc = {}
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        ang = e.calc_face_angle_signed(0.0)
        if ang <= 0.0:
            continue
        w = smoothstep(math.radians(50.0), math.radians(85.0), ang)
        for v in e.verts:
            if w > acc.get(v.index, 0.0):
                acc[v.index] = w
    bm.verts.index_update()
    for v in bm.verts:
        v[lay] = acc.get(v.index, 0.0)


def build_mesh(name, n_corner, flags):
    bm = bmesh.new()
    _HEX[0] = 0
    _AXL[0] = 0
    try:
        b = Build(bm)
        build_soil(b)
        build_water(b)
        build_rear_axle(b, flags)
        build_gearbox_engine(b)
        build_front_support(b, flags)
        for s in (-1.0, 1.0):
            build_rear_wheel(b, s, flags)
            build_front_wheel(b, s, flags)
        build_bonnet(b, n_corner)
        build_tank_dash(b, n_corner)
        build_grille(b, n_corner)
        build_fenders(b, flags)
        build_footplates(b)
        build_accessories(b)
        build_controls(b)
        build_hitch(b, flags)
        build_lamps(b)
        if flags["loose_lamp"]:
            for v in b.groups["lamp"]:
                v.co.y -= LOOSE_LAMP
        # stand the tractor in the ruts
        for v in set(b.groups["tr"]) | set(b.groups["lamp"]):
            v.co.z += Z0
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=DOUBLES_EPS)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.edges.index_update()
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(35.0)
        edge_wear(bm)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def _node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def _ramp(nt, a, ca, b, cb):
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].position = a
    r.color_ramp.elements[0].color = ca
    r.color_ramp.elements[1].position = b
    r.color_ramp.elements[1].color = cb
    return r


def _mix(nt, fac_socket, c1, c2):
    mx = nt.nodes.new("ShaderNodeMixRGB")
    mx.blend_type = "MIX"
    if isinstance(fac_socket, float):
        mx.inputs[0].default_value = fac_socket
    else:
        nt.links.new(fac_socket, mx.inputs[0])
    for i, c in ((1, c1), (2, c2)):
        if isinstance(c, tuple):
            mx.inputs[i].default_value = c
        else:
            nt.links.new(c, mx.inputs[i])
    return mx.outputs[0]


def _math(nt, op, a, b, clamp=False):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    m.use_clamp = clamp
    for i, v in ((0, a), (1, b)):
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = float(v)
        else:
            nt.links.new(v, m.inputs[i])
    return m.outputs[0]


def _gray(v):
    return (v, v, v, 1.0)


def _stretched(nt, coord_socket, sx, sy, sz):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord_socket, sep.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    for i, (k, sc) in enumerate((("X", sx), ("Y", sy), ("Z", sz))):
        nt.links.new(_math(nt, "MULTIPLY", sep.outputs[k], sc), comb.inputs[i])
    return comb.outputs[0]


def worn(name, col_a, col_b, rough, metallic=0.0, primer=None, bare=None, chip=0.0,
         rust=0.0, rust_col=(0.20, 0.085, 0.035, 1.0), mud_top=0.30, mud_amt=0.8,
         mud_col=(0.115, 0.082, 0.055, 1.0), spray=0.0, bump=0.10, bump_scale=300.0,
         coat=0.0, oil=0.0, fade=0.0, grime=0.0, scuff=0.0):
    """A designed, weathered surface: a per-part tone between two colours,
    paint chipped through to primer and to bare metal where the edge-wear
    attribute is high, sparse scuffs through to primer on the faces, paint
    faded where it faces the sky, grime darkening toward the ground, rust
    streaks running down, mud rising from the ground with a splashed edge and
    flecks above it, oily darkening, roughness breakup and a fine bump."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    if coat > 0.0 and "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    coord = nt.nodes.new("ShaderNodeTexCoord")
    obj = coord.outputs["Object"]
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(obj, sep.inputs[0])
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = TONE
    col = _mix(nt, attr.outputs["Fac"], col_a, col_b)
    # broad mottle, so no panel is one flat colour
    mot = _node(nt, "ShaderNodeTexNoise", Scale=3.5, Detail=4.0)
    nt.links.new(obj, mot.inputs["Vector"])
    mr = _ramp(nt, 0.3, _gray(0.82), 0.7, _gray(1.08))
    nt.links.new(mot.outputs["Fac"], mr.inputs["Fac"])
    mm = nt.nodes.new("ShaderNodeMixRGB")
    mm.blend_type = "MULTIPLY"
    mm.inputs[0].default_value = 1.0
    nt.links.new(col, mm.inputs[1])
    nt.links.new(mr.outputs["Color"], mm.inputs[2])
    col = mm.outputs[0]
    if fade > 0.0:
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        gsep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Normal"], gsep.inputs[0])
        up = _ramp(nt, 0.35, _gray(0.0), 0.95, _gray(fade))
        nt.links.new(gsep.outputs["Z"], up.inputs["Fac"])
        fn = _node(nt, "ShaderNodeTexNoise", Scale=5.0, Detail=5.0)
        nt.links.new(obj, fn.inputs["Vector"])
        fr = _ramp(nt, 0.30, _gray(0.45), 0.70, _gray(1.0))
        nt.links.new(fn.outputs["Fac"], fr.inputs["Fac"])
        faded = nt.nodes.new("ShaderNodeMixRGB")
        faded.blend_type = "MIX"
        faded.inputs[0].default_value = 0.55
        nt.links.new(col, faded.inputs[1])
        faded.inputs[2].default_value = (0.30, 0.36, 0.26, 1.0)
        col = _mix(nt, _math(nt, "MULTIPLY", up.outputs["Color"], fr.outputs["Color"]), col,
                   faded.outputs[0])
    if grime > 0.0:
        gm = _node(nt, "ShaderNodeMapRange")
        gm.inputs["From Min"].default_value = SOIL_T
        gm.inputs["From Max"].default_value = SOIL_T + 1.30
        gm.inputs["To Min"].default_value = grime
        gm.inputs["To Max"].default_value = 0.0
        nt.links.new(sep.outputs["Z"], gm.inputs["Value"])
        gn2 = _node(nt, "ShaderNodeTexNoise", Scale=3.0, Detail=6.0)
        nt.links.new(obj, gn2.inputs["Vector"])
        gmix = _math(nt, "MULTIPLY", gm.outputs["Result"],
                     _math(nt, "ADD", _math(nt, "MULTIPLY", gn2.outputs["Fac"], 1.2), 0.2))
        col = _mix(nt, _math(nt, "MINIMUM", gmix, 1.0), col, (0.040, 0.032, 0.022, 1.0))
    rough_s = None
    metal_s = None
    if chip > 0.0:
        wear = nt.nodes.new("ShaderNodeAttribute")
        wear.attribute_name = WEAR
        # chips come in patches along an edge, not as an unbroken line
        cn = _node(nt, "ShaderNodeTexNoise", Scale=22.0, Detail=10.0, Roughness=0.65)
        nt.links.new(obj, cn.inputs["Vector"])
        gate = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", cn.outputs["Fac"], 0.50), 6.0, clamp=True)
        cm = _math(nt, "MULTIPLY", wear.outputs["Fac"], gate)
        cm = _math(nt, "MULTIPLY", cm, chip)
        c1 = _ramp(nt, 0.30, _gray(0.0), 0.36, _gray(1.0))
        nt.links.new(cm, c1.inputs["Fac"])
        c2 = _ramp(nt, 0.58, _gray(0.0), 0.64, _gray(1.0))
        nt.links.new(cm, c2.inputs["Fac"])
        if scuff > 0.0:
            sn2 = _node(nt, "ShaderNodeTexNoise", Scale=26.0, Detail=12.0, Roughness=0.7)
            nt.links.new(obj, sn2.inputs["Vector"])
            s2 = _ramp(nt, 0.678, _gray(0.0), 0.70, _gray(scuff))
            nt.links.new(sn2.outputs["Fac"], s2.inputs["Fac"])
            col = _mix(nt, s2.outputs["Color"], col, (0.12, 0.080, 0.055, 1.0))
        col = _mix(nt, c1.outputs["Color"], col, primer)
        col = _mix(nt, c2.outputs["Color"], col, bare)
        metal_s = _math(nt, "MULTIPLY", c2.outputs["Color"], 0.85)
        rough_s = _math(nt, "MULTIPLY", c2.outputs["Color"], -0.15)
    if rust > 0.0:
        sv = _stretched(nt, obj, 1.0, 1.0, 0.06)
        sn = _node(nt, "ShaderNodeTexNoise", Scale=48.0, Detail=3.0)
        nt.links.new(sv, sn.inputs["Vector"])
        sr = _ramp(nt, 0.57, _gray(0.0), 0.68, _gray(rust))
        nt.links.new(sn.outputs["Fac"], sr.inputs["Fac"])
        gn = _node(nt, "ShaderNodeTexNoise", Scale=2.5, Detail=2.0)
        nt.links.new(obj, gn.inputs["Vector"])
        gr = _ramp(nt, 0.40, _gray(0.0), 0.58, _gray(1.0))
        nt.links.new(gn.outputs["Fac"], gr.inputs["Fac"])
        rm = _math(nt, "MULTIPLY", sr.outputs["Color"], gr.outputs["Color"])
        col = _mix(nt, rm, col, rust_col)
    if oil > 0.0:
        on = _node(nt, "ShaderNodeTexNoise", Scale=6.0, Detail=6.0)
        nt.links.new(obj, on.inputs["Vector"])
        orr = _ramp(nt, 0.45, _gray(0.0), 0.70, _gray(oil))
        nt.links.new(on.outputs["Fac"], orr.inputs["Fac"])
        col = _mix(nt, orr.outputs["Color"], col, (0.02, 0.018, 0.015, 1.0))
    # mud from the ground up, a splashed edge, and flecks above it
    hmap = _node(nt, "ShaderNodeMapRange")
    hmap.inputs["From Min"].default_value = SOIL_T - 0.02
    hmap.inputs["From Max"].default_value = SOIL_T + mud_top
    hmap.inputs["To Min"].default_value = 1.0
    hmap.inputs["To Max"].default_value = 0.0
    nt.links.new(sep.outputs["Z"], hmap.inputs["Value"])
    dn = _node(nt, "ShaderNodeTexNoise", Scale=7.0, Detail=8.0, Roughness=0.6)
    nt.links.new(obj, dn.inputs["Vector"])
    ms = _math(nt, "ADD", hmap.outputs["Result"], _math(nt, "MULTIPLY", dn.outputs["Fac"], 0.55))
    mr2 = _ramp(nt, 0.82, _gray(0.0), 0.90, _gray(mud_amt))
    nt.links.new(ms, mr2.inputs["Fac"])
    mud = mr2.outputs["Color"]
    if spray > 0.0:
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 18.0
        nt.links.new(obj, vor.inputs["Vector"])
        spr = _ramp(nt, 0.10, _gray(spray), 0.17, _gray(0.0))
        nt.links.new(vor.outputs["Distance"], spr.inputs["Fac"])
        hm2 = _node(nt, "ShaderNodeMapRange")
        hm2.inputs["From Min"].default_value = SOIL_T + mud_top * 0.6
        hm2.inputs["From Max"].default_value = SOIL_T + mud_top * 2.4
        hm2.inputs["To Min"].default_value = 1.0
        hm2.inputs["To Max"].default_value = 0.0
        nt.links.new(sep.outputs["Z"], hm2.inputs["Value"])
        sp = _math(nt, "MULTIPLY", spr.outputs["Color"], hm2.outputs["Result"])
        mud = _math(nt, "MAXIMUM", mud, sp)
    col = _mix(nt, mud, col, mud_col)
    nt.links.new(col, bsdf.inputs["Base Color"])
    rr = _ramp(nt, 0.30, _gray(max(0.03, rough - 0.08)), 0.70, _gray(min(0.95, rough + 0.08)))
    nt.links.new(dn.outputs["Fac"], rr.inputs["Fac"])
    rs = _math(nt, "ADD", rr.outputs["Color"], _math(nt, "MULTIPLY", mud, 0.6), clamp=True)
    if rough_s is not None:
        rs = _math(nt, "ADD", rs, rough_s, clamp=True)
    nt.links.new(rs, bsdf.inputs["Roughness"])
    if metal_s is not None:
        nt.links.new(_math(nt, "ADD", metal_s, metallic, clamp=True), bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Metallic"].default_value = metallic
    if bump > 0.0:
        bn = _node(nt, "ShaderNodeTexNoise", Scale=bump_scale, Detail=6.0)
        nt.links.new(obj, bn.inputs["Vector"])
        bh = _math(nt, "ADD", bn.outputs["Fac"], _math(nt, "MULTIPLY", mud, 0.8))
        bp = _node(nt, "ShaderNodeBump", Strength=bump)
        bp.inputs["Distance"].default_value = 0.0008
        nt.links.new(bh, bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def add_studio(mat, color, env, stops):
    """A studio carried in the material (after espresso-machine): the
    world-space reflection vector looks up a soft band of softboxes round the
    horizon, brighter on the key's side, added as emission. A metal on a dark
    stage mirrors the dark stage and reads as grey plastic without it."""
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    out = nt.nodes["Material Output"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Reflection"], sep.inputs[0])
    mz = nt.nodes.new("ShaderNodeMapRange")
    mz.inputs["From Min"].default_value = -1.0
    mz.inputs["From Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], mz.inputs["Value"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (stops[0][1],) * 3 + (1.0,)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (stops[-1][1],) * 3 + (1.0,)
    for pos, val in stops[1:-1]:
        e = cr.elements.new(pos)
        e.color = (val, val, val, 1.0)
    nt.links.new(mz.outputs["Result"], ramp.inputs["Fac"])
    mx = nt.nodes.new("ShaderNodeMapRange")
    mx.inputs["From Min"].default_value = -1.0
    mx.inputs["From Max"].default_value = 1.0
    mx.inputs["To Min"].default_value = 1.0
    mx.inputs["To Max"].default_value = 0.40
    nt.links.new(sep.outputs["X"], mx.inputs["Value"])
    side = _math(nt, "MULTIPLY", mx.outputs["Result"], env)
    tint = nt.nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1.0
    tint.inputs[2].default_value = color
    nt.links.new(ramp.outputs["Color"], tint.inputs[1])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tint.outputs[0], em.inputs["Color"])
    nt.links.new(side, em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(bsdf.outputs["BSDF"], add.inputs[0])
    nt.links.new(em.outputs["Emission"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
    return mat


STUDIO = [(0.0, 0.02), (0.30, 0.05), (0.42, 0.45), (0.50, 1.0), (0.62, 0.30), (1.0, 0.12)]


def soil_material():
    """Farmyard mud: a brown field with clods and straw flecks, darker and
    glossier where it is wet down in the ruts, and the rear tyres' chevron
    bars printed in the rut floors (apex to the rear: the bar's point meets
    the ground first)."""
    mat = bpy.data.materials.new("FarmyardMud")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    obj = coord.outputs["Object"]
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(obj, sep.inputs[0])
    n1 = _node(nt, "ShaderNodeTexNoise", Scale=4.0, Detail=8.0, Roughness=0.6)
    nt.links.new(obj, n1.inputs["Vector"])
    base = _ramp(nt, 0.30, (0.105, 0.072, 0.045, 1.0), 0.70, (0.175, 0.122, 0.075, 1.0))
    nt.links.new(n1.outputs["Fac"], base.inputs["Fac"])
    col = base.outputs["Color"]
    # wet: the rut floors and the dip, darker and glossy
    wet = _node(nt, "ShaderNodeMapRange")
    wet.inputs["From Min"].default_value = Z0 + 0.010
    wet.inputs["From Max"].default_value = Z0 + 0.001
    wet.inputs["To Min"].default_value = 0.0
    wet.inputs["To Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], wet.inputs["Value"])
    wn = _node(nt, "ShaderNodeTexNoise", Scale=9.0, Detail=5.0)
    nt.links.new(obj, wn.inputs["Vector"])
    # only up-facing mud in the ruts is wet, not the patch's skirt
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    gsep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], gsep.inputs[0])
    up = _ramp(nt, 0.70, _gray(0.0), 0.92, _gray(1.0))
    nt.links.new(gsep.outputs["Z"], up.inputs["Fac"])
    wet_m = _math(nt, "MULTIPLY", wet.outputs["Result"], up.outputs["Color"])
    wf = _math(nt, "MULTIPLY", wet_m, _math(nt, "ADD", wn.outputs["Fac"], 0.35))
    wf = _math(nt, "MINIMUM", wf, 1.0)
    col = _mix(nt, wf, col, (0.055, 0.040, 0.028, 1.0))
    # straw flecks on the berms and the field
    sv = _stretched(nt, obj, 1.0, 9.0, 1.0)
    st = _node(nt, "ShaderNodeTexNoise", Scale=28.0, Detail=2.0)
    nt.links.new(sv, st.inputs["Vector"])
    sr = _ramp(nt, 0.68, _gray(0.0), 0.72, _gray(0.7))
    nt.links.new(st.outputs["Fac"], sr.inputs["Fac"])
    sm = _math(nt, "MULTIPLY", sr.outputs["Color"], _math(nt, "SUBTRACT", 1.0, wet_m))
    col = _mix(nt, sm, col, (0.42, 0.33, 0.17, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(_math(nt, "SUBTRACT", 0.92, _math(nt, "MULTIPLY", wf, 0.72)), bsdf.inputs["Roughness"])
    # chevron prints in the rut floors: u = (x - K|d|) / P, staggered half a pitch
    ay = _math(nt, "ABSOLUTE", sep.outputs["Y"], 0.0)
    dd = _math(nt, "SUBTRACT", ay, RUT_Y)
    ad = _math(nt, "ABSOLUTE", dd, 0.0)
    k_run = LUG_SWEEP * R_RT / (LUG_END + LUG_X)
    pitch = 2.0 * math.pi * R_RT / LUGS_PER_HALF
    u = _math(nt, "DIVIDE", _math(nt, "SUBTRACT", sep.outputs["X"], _math(nt, "MULTIPLY", ad, k_run)),
              pitch)
    u = _math(nt, "ADD", u, _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", dd, 0.0), 0.5))
    fr = _math(nt, "FRACT", u, 0.0)
    band = _ramp(nt, 0.0, _gray(1.0), 0.28, _gray(0.0))
    nt.links.new(fr, band.inputs["Fac"])
    inside = _ramp(nt, 0.118, _gray(1.0), 0.138, _gray(0.0))
    nt.links.new(ad, inside.inputs["Fac"])
    lug = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", band.outputs["Color"], inside.outputs["Color"]),
                wet_m)
    clod = nt.nodes.new("ShaderNodeTexVoronoi")
    clod.inputs["Scale"].default_value = 38.0
    nt.links.new(obj, clod.inputs["Vector"])
    h = _math(nt, "SUBTRACT", _math(nt, "MULTIPLY", clod.outputs["Distance"], 0.6),
              _math(nt, "MULTIPLY", lug, 1.2))
    h = _math(nt, "ADD", h, _math(nt, "MULTIPLY", n1.outputs["Fac"], 0.5))
    bp = _node(nt, "ShaderNodeBump", Strength=0.55)
    bp.inputs["Distance"].default_value = 0.006
    nt.links.new(h, bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def water_material():
    mat = bpy.data.materials.new("PuddleWater")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.016, 0.012, 0.008, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.06
    coord = nt.nodes.new("ShaderNodeTexCoord")
    n = _node(nt, "ShaderNodeTexNoise", Scale=14.0, Detail=3.0)
    nt.links.new(coord.outputs["Object"], n.inputs["Vector"])
    bp = _node(nt, "ShaderNodeBump", Strength=0.08)
    bp.inputs["Distance"].default_value = 0.002
    nt.links.new(n.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    add_studio(mat, (0.30, 0.26, 0.21, 1.0), 0.10, STUDIO)
    return mat


def glass_material():
    mat = bpy.data.materials.new("LampGlass")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = TONE
    col = _mix(nt, attr.outputs["Fac"], (0.60, 0.58, 0.46, 1.0), (0.55, 0.030, 0.020, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.08
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.8
    add_studio(mat, (0.70, 0.70, 0.66, 1.0), 0.55, STUDIO)
    return mat


def core_material():
    """Radiator core: fine horizontal fins, black-painted copper."""
    mat = bpy.data.materials.new("RadiatorCore")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"
    wv.bands_direction = "Z"
    wv.inputs["Scale"].default_value = 160.0
    nt.links.new(coord.outputs["Object"], wv.inputs["Vector"])
    r = _ramp(nt, 0.35, (0.012, 0.012, 0.012, 1.0), 0.65, (0.075, 0.068, 0.058, 1.0))
    nt.links.new(wv.outputs["Fac"], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.65
    bsdf.inputs["Metallic"].default_value = 0.3
    bp = _node(nt, "ShaderNodeBump", Strength=0.6)
    bp.inputs["Distance"].default_value = 0.0015
    nt.links.new(wv.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def set_materials():
    """Slot order: body paint, wheel paint, rubber, cast iron, steel, zinc,
    black enamel, glass, exhaust, radiator core, soil, water. Shared by the
    check and the render."""
    primer = (0.22, 0.080, 0.048, 1.0)
    bare = (0.32, 0.31, 0.30, 1.0)
    paint = worn("BodyPaint", (0.062, 0.240, 0.092, 1.0), (0.052, 0.212, 0.080, 1.0), 0.44,
                 primer=primer, bare=bare, chip=1.0, rust=0.95, mud_top=0.62, mud_amt=0.9,
                 spray=1.0, coat=0.12, fade=0.8, grime=0.55, scuff=0.9)
    add_studio(paint, (0.30, 0.42, 0.34, 1.0), 0.06, STUDIO)
    wheel = worn("WheelPaint", (0.58, 0.52, 0.37, 1.0), (0.52, 0.46, 0.32, 1.0), 0.48,
                 primer=primer, bare=bare, chip=1.0, rust=0.55, grime=0.35, scuff=0.5, mud_top=0.30, mud_amt=0.95,
                 spray=0.9)
    rubber = worn("TyreRubber", (0.030, 0.029, 0.028, 1.0), (0.040, 0.038, 0.036, 1.0), 0.80,
                  mud_top=0.22, mud_amt=0.95, mud_col=(0.10, 0.072, 0.048, 1.0), spray=0.7,
                  bump=0.15, bump_scale=500.0)
    iron = worn("CastIron", (0.070, 0.078, 0.072, 1.0), (0.058, 0.064, 0.060, 1.0), 0.62,
                metallic=0.35, primer=(0.20, 0.08, 0.05, 1.0), bare=(0.24, 0.23, 0.22, 1.0), chip=0.8,
                rust=0.6, mud_top=0.30, mud_amt=0.85, spray=0.8, bump=0.25, bump_scale=420.0,
                oil=0.6)
    add_studio(iron, (0.40, 0.40, 0.40, 1.0), 0.06, STUDIO)
    steel = worn("ForgedSteel", (0.16, 0.155, 0.15, 1.0), (0.12, 0.115, 0.11, 1.0), 0.48, metallic=0.9,
                 rust=0.8, rust_col=(0.22, 0.10, 0.045, 1.0), mud_top=0.30, mud_amt=0.8, spray=0.6,
                 oil=0.4)
    add_studio(steel, (0.45, 0.45, 0.46, 1.0), 0.22, STUDIO)
    zinc = worn("ZincPlate", (0.62, 0.62, 0.60, 1.0), (0.54, 0.54, 0.52, 1.0), 0.30, metallic=1.0,
                rust=0.3, mud_top=0.20, mud_amt=0.6, bump=0.05)
    add_studio(zinc, (0.66, 0.67, 0.70, 1.0), 0.55, STUDIO)
    black = worn("BlackEnamel", (0.022, 0.022, 0.024, 1.0), (0.032, 0.032, 0.034, 1.0), 0.40,
                 primer=(0.20, 0.08, 0.05, 1.0), bare=(0.30, 0.29, 0.28, 1.0), chip=0.8, rust=0.4,
                 mud_top=0.25, mud_amt=0.7)
    add_studio(black, (0.35, 0.35, 0.36, 1.0), 0.10, STUDIO)
    glass = glass_material()
    exhaust = worn("ExhaustIron", (0.20, 0.090, 0.040, 1.0), (0.12, 0.070, 0.045, 1.0), 0.78,
                   metallic=0.3, rust=1.0, rust_col=(0.30, 0.13, 0.05, 1.0), mud_top=0.2,
                   mud_amt=0.4, bump=0.35, bump_scale=260.0, oil=0.5)
    core = core_material()
    soil = soil_material()
    water = water_material()
    return (paint, wheel, rubber, iron, steel, zinc, black, glass, exhaust, core, soil, water)


def assign_slots(obj, wanted):
    # Do not materials.clear() - that resets polygon material_index to 0.
    mats = obj.data.materials
    for i, mat in enumerate(wanted):
        if i < len(mats):
            mats[i] = mat
        else:
            mats.append(mat)


# --------------------------------------------------------------------------
# Audits
# --------------------------------------------------------------------------

def vert_bbox(me):
    # read the vertices: bound_box is cached and an in-place edit does not refresh it
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lo, hi = co.min(axis=0), co.max(axis=0)
    return (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])


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


def zfight_pairs(me, groups, report=None):
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
            if report is not None:
                report.append((tuple(round(v, 4) for v in ci), tuple(round(v, 4) for v in cj),
                               tuple(round(v, 3) for v in ni), me.polygons[i].material_index,
                               me.polygons[j].material_index))
    return hits


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
    def __init__(self, me, idx, verts, polys, tags):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.centre = (self.lo + self.hi) * 0.5
        self.mean = sum(pts, Vector()) / len(pts)
        mats, tg = {}, {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
            t = tags[p.index]
            tg[t] = tg.get(t, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        self.mats = set(mats)
        self.tag = max(tg, key=tg.get) if tg else T_NONE
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)
        self.polys = polys


def pca(pts):
    """(mean, eigenvalues ascending, eigenvectors as columns)."""
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    w, vecs = np.linalg.eigh(q.T @ q / len(p))
    return Vector(c), w, vecs


def lathe_axis(pts):
    """A body of revolution's axis: the eigenvector whose eigenvalue stands
    apart from the other two (the two radial ones are equal)."""
    c, w, vecs = pca(pts)
    k = 2 if (w[1] - w[0]) < (w[2] - w[1]) else 0
    a = Vector(vecs[:, k])
    return c, a.normalized()


def pca_line(pts):
    c, _w, vecs = pca(pts)
    return c, Vector(vecs[:, 2]).normalized()


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    attr = me.attributes.get("part")
    tags = [0] * len(me.polygons)
    if attr is not None:
        tags = [d.value for d in attr.data]
    parts = [Shell(me, i, g, polys[i], tags) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    for key, t in (("soil", T_SOIL), ("water", T_WATER), ("tyres", T_TYRE), ("lugs", T_LUG),
                   ("rims", T_RIM), ("hubs_f", T_HUB_F), ("hubs_r", T_HUB_R), ("stubs", T_STUB),
                   ("axles", T_AXLE), ("pivot", T_PIVOT), ("bush", T_BUSH), ("eyes", T_EYE),
                   ("pins", T_PIN)):
        out[key] = [s for s in parts if s.tag == t]
    out["tractor"] = [s for s in parts if s.tag not in (T_SOIL, T_WATER)]
    ax = out["axles"]
    out["y_mid"] = 0.5 * (ax[0].mean.y + ax[1].mean.y) if len(ax) == 2 else 0.0
    ty = sorted(out["tyres"], key=lambda s: s.centre.x)
    out["rear_tyres"] = ty[:2] if len(ty) == TYRE_COUNT else []
    out["front_tyres"] = ty[2:] if len(ty) == TYRE_COUNT else []
    # every lug belongs to the rear tyre whose centre it is nearest
    out["lug_of"] = {}
    for lg in out["lugs"]:
        if out["rear_tyres"]:
            t = min(out["rear_tyres"], key=lambda s: (s.centre - lg.mean).length)
            out["lug_of"].setdefault(t.idx, []).append(lg)
    return out


def soil_z(soil, x, y):
    hit = soil.tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 10.0)
    return hit[0].z if hit[0] is not None else None


def support_audit(cls):
    """Per tyre (carcass and its lugs): the deepest vertex under the mud's
    surface, read by a ray down onto the soil shell."""
    soil = cls["soil"][0] if len(cls["soil"]) == 1 else None
    res = []
    if soil is None:
        return res
    for t in cls["tyres"]:
        pts = list(t.pts) + [p for lg in cls["lug_of"].get(t.idx, []) for p in lg.pts]
        best = -9.0
        for p in pts:
            if p.z > soil.hi.z:
                continue
            gz = soil_z(soil, p.x, p.y)
            if gz is not None:
                best = max(best, gz - p.z)
        res.append(best)
    return res


def coax(host_pts, part_pts):
    hc, ha = pca_line(host_pts)
    pc, pa = lathe_axis(part_pts)
    if pa.dot(ha) < 0.0:
        pa = -pa
    rel = pc - hc
    off = (rel - ha * rel.dot(ha)).length
    ang = math.degrees(math.acos(min(1.0, abs(pa.dot(ha)))))
    return off, ang


def nearest(shells_, p):
    return min(shells_, key=lambda s: (s.mean - p).length) if shells_ else None


def joint_audit(cls):
    """Hubs coaxial with their spindles and half-shafts; the pivot pin
    coaxial with both bushings; every link eye on a pin: the eye's centre on
    the pin's axis, its axis along the pin's, the pin past both faces."""
    res = {"hubs": [], "bush": [], "eyes": []}
    for h in cls["hubs_f"]:
        st = nearest(cls["stubs"], h.mean)
        if st is not None:
            res["hubs"].append(("front",) + coax(st.pts, h.pts))
    for h in cls["hubs_r"]:
        ax = nearest(cls["axles"], h.mean)
        if ax is not None:
            res["hubs"].append(("rear",) + coax(ax.pts, h.pts))
    if len(cls["pivot"]) == 1:
        for bsh in cls["bush"]:
            res["bush"].append(coax(cls["pivot"][0].pts, bsh.pts))
    pins = [(p,) + pca_line(p.pts) for p in cls["pins"]]
    for e in cls["eyes"]:
        ec, ea = lathe_axis(e.pts)
        best = None
        for p, pc, pa in pins:
            rel = ec - pc
            off = (rel - pa * rel.dot(pa)).length
            # coaxial pins either side: prefer the one whose span holds the eye
            pp = [(q - pc).dot(pa) for q in p.pts]
            along = rel.dot(pa)
            outside = max(0.0, min(pp) - along, along - max(pp))
            score = off + 10.0 * outside
            if best is None or score < best[4]:
                best = (off, p, pc, pa, score)
        if best is None:
            res["eyes"].append((9.0, 90.0, -9.0))
            continue
        off, p, pc, pa, _sc = best
        ang = math.degrees(math.acos(min(1.0, abs(ea.dot(pa)))))
        ep = [(q - pc).dot(pa) for q in e.pts]
        pp = [(q - pc).dot(pa) for q in p.pts]
        past = min(min(ep) - min(pp), max(pp) - max(ep))
        res["eyes"].append((off, ang, past))
    return res


def rim_host_radius(rim, c, a, p):
    """The rim's outer surface at the vertex's own station and angle: a ray
    from outside toward the axis, along the vertex's radial."""
    rel = p - c
    s = rel.dot(a)
    q = rel - a * s
    rho = q.length
    if rho < 1e-6:
        return None, rho
    u = q / rho
    origin = c + a * s + u * (rho + 0.03)
    hit, _n, _i, _d = rim.tree.ray_cast(origin, -u, 0.06)
    if hit is None:
        return None, rho
    return (hit - (c + a * s)).length, rho


def tyre_seat_audit(cls):
    """Per tyre, per angular segment, the innermost vertices (the bead)
    against the rim's bead seat read by rays: the seat depth."""
    seats, orphans = [], 0
    for t in cls["tyres"]:
        rim = nearest(cls["rims"], t.mean)
        if rim is None:
            orphans += 1
            continue
        c, a = lathe_axis(rim.pts)
        e1 = (any_perp(a) - a * any_perp(a).dot(a)).normalized()
        e2 = a.cross(e1)
        segs = TYRE_SEGS_R if t.size.z > 1.0 else TYRE_SEGS_F
        bins = {}
        for p in t.pts:
            rel = p - c
            q = rel - a * rel.dot(a)
            ang = math.atan2(q.dot(e2), q.dot(e1))
            key = round(ang / (2.0 * math.pi / segs)) % segs
            bins.setdefault(key, []).append((q.length, p))
        for key, lst in bins.items():
            rmin = min(r for r, _p in lst)
            for r, p in lst:
                if r > rmin + 0.0002:
                    continue
                hr, rho = rim_host_radius(rim, c, a, p)
                if hr is None:
                    orphans += 1
                    continue
                seats.append(hr - rho)
    return seats, orphans


def carcass_radius(tyre, c, a, p):
    """The carcass's outer surface at the vertex's own station and angle:
    a ray from outside toward the axis along the vertex's radial."""
    rel = p - c
    s = rel.dot(a)
    q = rel - a * s
    rho = q.length
    u = q / rho
    origin = c + a * s + u * (rho + 0.08)
    hit = tyre.tree.ray_cast(origin, -u, 0.20)[0]
    if hit is None:
        return None, rho
    return (hit - (c + a * s)).length, rho


def lug_audit(cls):
    """Every bar's root inside the carcass by a band, its crown proud of it;
    per rear tyre and half, the bars' pitch round the spin axis; each bar's
    handing (its apex ahead of its shoulder end in forward rolling, which
    turns both rear wheels the same way, about +Y)."""
    res = {"count": 0, "bite": [9.0, -9.0], "proud": 9.0, "orphans": 0, "pitch": 0.0,
           "hand": 180.0, "hand_max": -180.0, "per_tyre": []}
    for t in cls["rear_tyres"]:
        lugs = cls["lug_of"].get(t.idx, [])
        res["count"] += len(lugs)
        res["per_tyre"].append(len(lugs))
        rim = nearest(cls["rims"], t.mean)
        if rim is None or not lugs:
            res["orphans"] += 1
            continue
        c, a = lathe_axis(rim.pts)
        halves = {1: [], -1: []}
        for lg in lugs:
            deep, proud = -9.0, -9.0
            for p in lg.pts:
                hr, rho = carcass_radius(t, c, a, p)
                if hr is None:
                    continue
                deep = max(deep, hr - rho)
                proud = max(proud, rho - hr)
            if deep < -8.0:
                res["orphans"] += 1
            res["bite"][0] = min(res["bite"][0], deep)
            res["bite"][1] = max(res["bite"][1], deep)
            res["proud"] = min(res["proud"], proud)
            dy = [p.y - c.y for p in lg.pts]
            h = 1 if sum(dy) > 0.0 else -1
            # the spin angle about +Y: from +Z toward +X
            th = [math.atan2(p.x - c.x, p.z - c.z) for p in lg.pts]
            order = sorted(range(len(lg.pts)), key=lambda i: h * dy[i])
            ce = order[:6]
            sh = order[-6:]

            def mean_ang(idx):
                return math.atan2(sum(math.sin(th[i]) for i in idx), sum(math.cos(th[i]) for i in idx))
            d = math.degrees((mean_ang(ce) - mean_ang(sh) + math.pi) % (2.0 * math.pi) - math.pi)
            res["hand"] = min(res["hand"], d)
            res["hand_max"] = max(res["hand_max"], d)
            m = lg.mean - c
            halves[h].append(math.atan2(m.x, m.z))
        for h, angs in halves.items():
            if len(angs) < 2:
                res["pitch"] = 99.0
                continue
            ts = sorted(angs)
            want = 360.0 / len(ts)
            for x0, x1 in zip(ts, ts[1:] + [ts[0] + 2.0 * math.pi]):
                res["pitch"] = max(res["pitch"], abs(math.degrees(x1 - x0) - want))
    return res


def mirror_audit(cls):
    """Every body-paint vertex against its mirror partner across the
    tractor's centre plane (half-way between the rear half-shafts)."""
    y0 = cls["y_mid"]
    pts = [p for s in cls["tractor"] if s.mat == PAINT_IDX for p in s.pts]
    if not pts:
        return 9.0, 0
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    worst = 0.0
    for p in pts:
        _co, _i, d = kd.find(Vector((p.x, 2.0 * y0 - p.y, p.z)))
        worst = max(worst, d)
    return worst, len(pts)


def wheel_audit(cls):
    """Tyres paired front and rear: mirror of each pair, wheelbase and both
    tracks from the carcasses' own centres; each rear tyre's diameter over
    its lugs about its rim's axis."""
    y0 = cls["y_mid"]
    res = {"mirror": 9.0, "wheelbase": 0.0, "track_f": 0.0, "track_r": 0.0, "diam": []}
    if len(cls["tyres"]) != TYRE_COUNT:
        return res
    rear, front = cls["rear_tyres"], cls["front_tyres"]
    worst = 0.0
    for pair in (front, rear):
        L, R = sorted(pair, key=lambda s: -s.centre.y)
        worst = max(worst, abs((L.centre.y - y0) - (y0 - R.centre.y)), abs(L.centre.x - R.centre.x),
                    abs(L.lo.z - R.lo.z), abs(L.size.x - R.size.x), abs(L.size.y - R.size.y),
                    abs(L.size.z - R.size.z))
    res["mirror"] = worst
    res["wheelbase"] = (0.5 * (front[0].centre.x + front[1].centre.x)
                        - 0.5 * (rear[0].centre.x + rear[1].centre.x))
    res["track_f"] = abs(front[0].centre.y - front[1].centre.y)
    res["track_r"] = abs(rear[0].centre.y - rear[1].centre.y)
    for t in rear:
        rim = nearest(cls["rims"], t.mean)
        if rim is None:
            res["diam"].append(0.0)
            continue
        c, a = lathe_axis(rim.pts)
        pts = list(t.pts) + [p for lg in cls["lug_of"].get(t.idx, []) for p in lg.pts]
        rmax = max(((p - c) - a * (p - c).dot(a)).length for p in pts)
        res["diam"].append(2.0 * rmax)
    return res


def shell_mass(s):
    vol = 0.0
    mom = Vector()
    for tri in s.tri_idx:
        a = s.pts[tri[0]]
        for k in range(1, len(tri) - 1):
            b, c = s.pts[tri[k]], s.pts[tri[k + 1]]
            v = a.dot(b.cross(c)) / 6.0
            vol += v
            mom += v * (a + b + c) / 4.0
    return vol, (mom / vol if abs(vol) > 1e-15 else s.mean)


def stance_audit(cls):
    """Mass centre against the tractor's real support: a triangle, because
    the front axle pivots on its pin. Its corners are the two rear tyres'
    contact patches (the centroid of each tyre's vertices under the mud) and
    the pivot pin's centre, all in plan."""
    total = 0.0
    mom = Vector()
    for s in cls["tractor"]:
        if s.mat is None:
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * DENSITY[s.mat]
        total += m
        mom += m * cen
    com = mom / total if total > 0.0 else Vector()
    soil = cls["soil"][0] if len(cls["soil"]) == 1 else None
    tri = []
    for t in cls["rear_tyres"]:
        pts = list(t.pts) + [p for lg in cls["lug_of"].get(t.idx, []) for p in lg.pts]
        sub = []
        for p in pts:
            if soil is not None and p.z < soil.hi.z:
                gz = soil_z(soil, p.x, p.y)
                if gz is not None and p.z < gz:
                    sub.append(p)
        if sub:
            tri.append((sum(p.x for p in sub) / len(sub), sum(p.y for p in sub) / len(sub)))
    if len(cls["pivot"]) == 1:
        pv = cls["pivot"][0].mean
        tri.append((pv.x, pv.y))
    margin = -1.0
    if len(tri) == 3:
        hull = hull2d(tri)
        margin = 9.0
        for k in range(len(hull)):
            a, b = hull[k], hull[(k + 1) % len(hull)]
            ex, ey = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ex, ey)
            margin = min(margin, (ex * (com.y - a[1]) - ey * (com.x - a[0])) / ln)
    return {"mass": total, "com": com, "margin": margin, "tri": tri}


def connected_components(cls):
    parts = cls["all"]
    n = len(parts)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        a = parts[i]
        for j in range(i + 1, n):
            b = parts[j]
            if (a.lo.x > b.hi.x or b.lo.x > a.hi.x or a.lo.y > b.hi.y or b.lo.y > a.hi.y
                    or a.lo.z > b.hi.z or b.lo.z > a.hi.z):
                continue
            if find(i) == find(j):
                continue
            if a.tree.overlap(b.tree):
                parent[find(i)] = find(j)
    roots = {find(i) for i in range(n)}
    sizes = {}
    for i in range(n):
        sizes[find(i)] = sizes.get(find(i), 0) + 1
    if os.environ.get("BDT_TRACTOR_DIAG"):
        big = max(sizes, key=sizes.get)
        for i in range(n):
            if find(i) != big:
                p = parts[i]
                print(f"diag: stray shell {i} mat={p.mat} tag={p.tag} centre="
                      f"({p.centre.x:.3f},{p.centre.y:.3f},{p.centre.z:.3f})")
    return len(roots), sorted(sizes.values())


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        # inside the envelope, so only the hygiene budget can see it
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
    # Duplicated from snippets/convex_hull_collider.py (not a package). The
    # hull is fed the vertices alone: handed faces too, it keeps some.
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for v in obj.data.vertices:
            bm.verts.new(v.co)
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
    # Adapted from snippets/setup_bake_target_image.py - do not replace slots.
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("TractorNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = PAINT_IDX
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


def _mm(v):
    return round(v * 1000.0, 3)


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_mesh("TractorLow", n_corner=2, flags=flags)
    high = build_mesh("TractorHigh", n_corner=4, flags=flags)
    mats = set_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the body paint: the bonnet, tank and grille shell's
    # rounded corners are where the high mesh differs from the low.
    target = mats[PAINT_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("mesh did not build", 3),) + none3

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat = len(slots)
    distinct_mats = len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    print(f"measured mat_index_counts={dict(sorted(idx_counts.items()))}")
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = vert_bbox(low.data)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]
    hyg = hygiene_audit(low.data)
    cls = classify(low.data)
    zrep = [] if os.environ.get("BDT_TRACTOR_DIAG") else None
    zf = zfight_pairs(low.data, cls["groups"], zrep)
    if zrep:
        seen = {}
        for r in zrep:
            key = (round(r[0][0], 2), round(r[0][1], 2), round(r[0][2], 2), r[3], r[4])
            seen.setdefault(key, [0, r])[0] += 1
        for key, (cnt, r) in sorted(seen.items(), key=lambda kv: -kv[1][0])[:60]:
            print(f"diag: coplanar x{cnt} {r}")
    sinks = support_audit(cls)
    joints = joint_audit(cls)
    seats, orphans = tyre_seat_audit(cls)
    lugs = lug_audit(cls)
    mirror, nmirror = mirror_audit(cls)
    wheels = wheel_audit(cls)
    stance = stance_audit(cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("mesh has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "TractorLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "TractorLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(low, "TractorCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_farm_tractor_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    hubs, bush, eyes = joints["hubs"], joints["bush"], joints["eyes"]
    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
          f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}")
    print(f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
          f"overlap={overlap:.6f} nfaces={nfaces}")
    print(f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
          f"outer={OUTER_SIZE} zmin={bb[2]:.5f} min=({bb[0]:.4f},{bb[1]:.4f})")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured shells={len(cls['all'])} tyres={len(cls['tyres'])} "
          f"sink_mm={[_mm(s) for s in sinks]}")
    print(f"measured hubs={[(h[0], _mm(h[1]), round(h[2], 4)) for h in hubs]} "
          f"bushings={[(_mm(o), round(a, 4)) for o, a in bush]}")
    print(f"measured eyes={[(_mm(o), round(a, 3), _mm(p)) for o, a, p in eyes]}")
    if seats:
        print(f"measured tyre_seat_mm=({min(seats) * 1000:.3f},{max(seats) * 1000:.3f}) "
              f"n={len(seats)} orphans={orphans} rims={len(cls['rims'])}")
    print(f"measured lugs={lugs['count']} per_tyre={lugs['per_tyre']} bite_mm=({_mm(lugs['bite'][0])},"
          f"{_mm(lugs['bite'][1])}) proud_mm={_mm(lugs['proud'])} orphans={lugs['orphans']} "
          f"pitch_dev_deg={lugs['pitch']:.4f} hand_deg=({lugs['hand']:.3f},{lugs['hand_max']:.3f})")
    print(f"measured mirror_mm={mirror * 1000:.4f} (n={nmirror}) wheel_mirror_mm="
          f"{wheels['mirror'] * 1000:.4f} wheelbase={wheels['wheelbase']:.5f} "
          f"track_f={wheels['track_f']:.5f} track_r={wheels['track_r']:.5f} "
          f"rear_diam={[round(d, 5) for d in wheels['diam']]}")
    print(f"measured mass={stance['mass']:.1f}kg com=({stance['com'].x:.4f},{stance['com'].y:.4f},"
          f"{stance['com'].z:.4f}) support={[(round(x, 4), round(y, 4)) for x, y in stance['tri']]} "
          f"margin={stance['margin']:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]} shells={len(cls['all'])}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    for idx, floor in FACE_FLOORS.items():
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{MAT_LABELS[idx]} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + none3
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + none3
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + none3
    if (abs(size_x - OUTER_SIZE[0]) > BBOX_TOL or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
            or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL):
        return (fail(f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8),) + none3
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
                     "(--skip-decimate is the designed fail)", 9),) + none3
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9),) + none3
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + none3
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + none3
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + none3
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf}", 15),) + none3
    if bb[2] > ZMIN_EPS or bb[2] < -ZMIN_EPS:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none3
    if len(sinks) != TYRE_COUNT or any(not (SINK_MIN <= s <= SINK_MAX) for s in sinks):
        return (fail(f"tyres: {len(sinks)} (want {TYRE_COUNT}), pressed into the mud "
                     f"{[_mm(s) for s in sinks]} mm (band [{SINK_MIN * 1000}, {SINK_MAX * 1000}])",
                     16),) + none3
    if (len(hubs) != HUBS or len(bush) != BUSHINGS or len(eyes) != EYES
            or any(o > COAX_MAX or a > COAX_DEG_MAX for _k, o, a in hubs)
            or any(o > COAX_MAX or a > COAX_DEG_MAX for o, a in bush)
            or any(o > EYE_OFF_MAX or a > EYE_DEG_MAX or p < EYE_PIN_PAST for o, a, p in eyes)):
        return (fail(f"joint fit: hubs {[(k, _mm(o), round(a, 3)) for k, o, a in hubs]}, pivot "
                     f"bushings {[(_mm(o), round(a, 3)) for o, a in bush]} (off the axis <= "
                     f"{COAX_MAX * 1000} mm, {COAX_DEG_MAX} deg); {len(eyes)} eyes (want {EYES}) "
                     f"{[(_mm(o), round(a, 2), _mm(p)) for o, a, p in eyes]} (off the pin <= "
                     f"{EYE_OFF_MAX * 1000} mm, {EYE_DEG_MAX} deg, pin past both faces >= "
                     f"{EYE_PIN_PAST * 1000} mm)", 17),) + none3
    if (len(cls["tyres"]) != TYRE_COUNT or orphans or not seats
            or min(seats) < TYRE_SEAT_MIN or max(seats) > TYRE_SEAT_MAX
            or lugs["count"] != LUGS or lugs["orphans"]
            or lugs["bite"][0] < LUG_BITE_MIN or lugs["bite"][1] > LUG_BITE_MAX
            or lugs["proud"] < LUG_PROUD_MIN):
        return (fail(f"seat: tyre beads {min(seats) * 1000 if seats else 0:.3f}.."
                     f"{max(seats) * 1000 if seats else 0:.3f} mm (band [{TYRE_SEAT_MIN * 1000}, "
                     f"{TYRE_SEAT_MAX * 1000}]), orphans {orphans}; {lugs['count']} lugs (want {LUGS}), "
                     f"roots {_mm(lugs['bite'][0])}..{_mm(lugs['bite'][1])} mm into the carcass "
                     f"(band [{LUG_BITE_MIN * 1000}, {LUG_BITE_MAX * 1000}]), proud "
                     f"{_mm(lugs['proud'])} mm (>= {LUG_PROUD_MIN * 1000})", 18),) + none3
    if (mirror > MIRROR_EPS or wheels["mirror"] > WHEEL_MIRROR_EPS
            or abs(wheels["wheelbase"] - WHEELBASE) > SIZE_TOL
            or abs(wheels["track_f"] - TRACK_F) > SIZE_TOL
            or abs(wheels["track_r"] - TRACK_R) > SIZE_TOL
            or len(wheels["diam"]) != 2 or any(abs(d - REAR_DIAM) > DIAM_TOL for d in wheels["diam"])):
        return (fail(f"mirror/size: body mirror {mirror * 1000:.3f} mm, wheels "
                     f"{wheels['mirror'] * 1000:.3f} mm (eps {MIRROR_EPS * 1000}), wheelbase "
                     f"{wheels['wheelbase']:.4f}, tracks {wheels['track_f']:.4f} / "
                     f"{wheels['track_r']:.4f} (+- {SIZE_TOL}), rear tyres "
                     f"{[round(d, 4) for d in wheels['diam']]} m (want {REAR_DIAM} +- {DIAM_TOL})",
                     19),) + none3
    if lugs["pitch"] > PITCH_TOL_DEG:
        return (fail(f"lug pitch off by {lugs['pitch']:.3f} deg (<= {PITCH_TOL_DEG})", 20),) + none3
    if lugs["hand"] < HAND_MIN_DEG:
        return (fail(f"chevron handing: a bar's apex {lugs['hand']:.3f} deg ahead of its shoulder "
                     f"(>= {HAND_MIN_DEG}: the point meets the ground first)", 21),) + none3
    if stance["margin"] < STANCE_MARGIN:
        return (fail(f"stance: mass centre {stance['margin']:.4f} m inside the support triangle "
                     f"< {STANCE_MARGIN:.4f}", 22),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 23),) + none3
    return 0, low, target, tex


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    # chain the baked normal under the paint's own bump
    for link in list(bsdf.inputs["Normal"].links):
        src = link.from_node
        if src.type == "BUMP":
            nt.links.new(nrm.outputs["Normal"], src.inputs["Normal"])
            return
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, target, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(target, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(HERO_YAW_DEG)
    bpy.context.view_layer.update()
    corners = [low.matrix_world @ Vector(c) for c in low.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    centre = (lo + hi) * 0.5

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
    floor.location.z = -0.001
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

    # Key from the camera's left and high, a cool fill low right, a cool rim
    # behind to lift the tractor off the wall, the warm wedge pooled on the
    # back wall.
    light("Key", (-2.6, -6.0, 6.2), 420.0, 4.0, (1.0, 0.95, 0.90), spread=36.0)
    light("Fill", (7.5, -3.5, 1.6), 60.0, 9.0, (0.72, 0.82, 1.0))
    light("Rim", (-3.4, 4.2, 4.2), 380.0, 3.4, (0.62, 0.78, 1.0))
    light("Wedge", (-2.4, 4.3, 2.8), 760.0, 5.5, (1.0, 0.72, 0.44),
          target=(centre.x - 1.4, WALL_Y, 1.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = CAM_LENS
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((CAM_VIEW[0], CAM_VIEW[1], 0.0)).normalized()
    cam.location = centre + view * CAM_DIST + Vector((0.0, 0.0, CAM_LIFT))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector(AIM_OFFSET)
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
    # Standard, not AgX: AgX washes the green paint and the grey wheels flat
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


FLAGS = ("float_tyre", "cock_hub", "cant_pin", "unpin_link", "sink_tyre", "float_lugs",
         "skew_wheel", "wide_track", "tall_lugs", "odd_fender", "bunch_lugs", "reverse_lugs",
         "offset_pivot", "loose_lamp")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--float-tyre", action="store_true")
    p.add_argument("--cock-hub", action="store_true")
    p.add_argument("--cant-pin", action="store_true")
    p.add_argument("--unpin-link", action="store_true")
    p.add_argument("--sink-tyre", action="store_true")
    p.add_argument("--float-lugs", action="store_true")
    p.add_argument("--skew-wheel", action="store_true")
    p.add_argument("--wide-track", action="store_true")
    p.add_argument("--tall-lugs", action="store_true")
    p.add_argument("--odd-fender", action="store_true")
    p.add_argument("--bunch-lugs", action="store_true")
    p.add_argument("--reverse-lugs", action="store_true")
    p.add_argument("--offset-pivot", action="store_true")
    p.add_argument("--loose-lamp", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        **{k: getattr(args, k) for k in FLAGS},
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("farm-tractor OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
