"""Game-ready 1970s lugged-steel road bicycle — a showcase piece, not an example.

Asserts budget conformance of a procedural classic road bicycle standing on
its side kickstand, after composing shipped pipeline pieces: bmesh
construction, UVs, ten materials, high-to-low normal bake, LOD chain, convex
collider, Unity glTF export.

A diamond frame of round tubes joined in chromed lugs (spear-pointed
sleeves at the head tube, the seat cluster and the bottom bracket shell),
with tapered chain stays and seat stays in chromed tips, a chrome-capped
seat-stay top, a brake bridge and a chain-stay bridge; a fork with a chromed
sloping crown, blade sockets and socks, raked blades and dropouts. Two 700c
wheels, each a box-section rim, 36 spokes laced three-cross from both
flanges of a small-flange hub (every spoke from a flange hole to a nipple
through the rim), a quick-release skewer and a tyre with a black file-tread
crown over tan gum sidewalls. A double chainring crankset (spider, arms,
bolts), quill pedals with toe clips and straps, a six-speed freewheel, a
roller chain of individual links wrapped over the big ring and a cog and
through the rear derailleur's two jockey wheels in an S, a front derailleur
cage straddling the chain, down-tube friction shifters with their cables,
side-pull calipers whose pads stand a millimetre off the rims, brake levers
under gum hoods on taped drop bars, a quill stem, a leather saddle on rails
and a seat post, a bottle in a wire cage, and a side kickstand whose foot
and both tyres stand on the ground, the bike leaning onto it.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--float-tyre`` both tyres and the stand foot
on the ground, ``--slip-wheel`` the hubs coaxial with their dropouts,
``--short-spoke`` every spoke end seated in its nipple and flange,
``--dish-wheel`` the wheels in the frame's centre plane, ``--steep-head`` the
steering trail, ``--bunch-spokes`` the three-cross lacing, ``--lift-chain``
the chain seated on its sprockets, ``--shift-rollers`` a straight chain line,
``--tuck-stand`` the mass centre inside the support triangle, ``--pop-bottle``
one connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts are
not byte-identical across Blender versions — the LOD gate is a ratio band,
not an exact count.

    blender --background --python road_bicycle.py --
    blender --background --python road_bicycle.py -- --skip-decimate
    blender --background --python road_bicycle.py -- --output bicycle.png
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

# --- Frame geometry (construction frame: front at +X, rider's left at +Y, the
#     drive side at -Y; built upright, then leaned onto the kickstand) ----------
R_TYRE = 0.335              # 700c x 25: 622 mm bead seat, 24 mm tyre
TYRE_SEC = 0.0118           # tyre section radius
CS_LEN = 0.415              # chain stay, BB centre to rear axle
BB_DROP = 0.070
ST_DEG = 73.5
HT_DEG = 73.0
ST_CT = 0.560               # 56 cm frame: BB centre to top-tube centreline
ST_EXT = 0.020              # seat tube above the top tube centreline
TT_EFF = 0.560
HT_ABOVE_TT = 0.025
HT_LEN = 0.140
DT_ABOVE_HT_BOT = 0.022
FORK_OFFSET = 0.045
LEAN_DEG = 5.0              # onto the kickstand, toward +Y
R_TT, R_DT, R_ST, R_HT = 0.0127, 0.0143, 0.0143, 0.0159

# --- Wheels ----------------------------------------------------------------------
TYRE_SEGS = 40
RIM_SEGS = 40
SPOKES = 36
CROSS = 3
FLANGE_R = 0.0225           # small-flange hub
HOLE_R = 0.0195             # flange hole circle
SPOKE_END_R = 0.2965        # spoke end, inside its nipple
RIM_HOLE_W = 0.0020         # rim holes drilled alternately either side
NIPPLE_LEN = 0.012
NIPPLE_IN = 0.0075          # spoke end this far into the nipple from its inner end
SPOKE_R = 0.0010
SPOKE_SIDES = 5
FRONT_FLANGES = (-0.035, 0.035)
FRONT_OLD = 0.050           # half over-locknut dimension (100 mm)
REAR_FLANGES = (-0.021, 0.036)
REAR_OLD = 0.063            # 126 mm, six-speed
RIM_HALF = [(0.3100, 0.0060), (0.3106, 0.0085), (0.3152, 0.0085), (0.3152, 0.0101),
            (0.3055, 0.0101), (0.2995, 0.0090), (0.2972, 0.0060)]

# --- Drivetrain ------------------------------------------------------------------
PITCH = 0.0127
CHAIN_Y = -0.046
RING_TEETH = (52, 42)
RING_Y = (-0.046, -0.0395)
RING_T = 0.0012             # half thickness
COG_TEETH = (24, 21, 19, 17, 15, 14)
COG_Y = (-0.031, -0.036, -0.041, -0.046, -0.051, -0.056)
COG_T = 0.0009
DRIVEN_COG = 3              # the 17: in line with the big ring
PULLEY_TEETH = 11
PULLEY_T = (0.00115, 0.00130)   # upper, lower: off every cog face
CRANK = 0.170
ROLLER_R = 0.0039
ROLLER_H = 0.0020           # roller half length (its rim), apex 0.3 mm beyond
ROLLER_PHASE = math.radians(7.85)
ROLLER_STEP_DEG = 11.13      # each roller turned a further step (mod 40 deg)
COG_PHASE_STEP = 0.923       # tooth phase of the idle cogs (rad per cog)
TAPER_IN, TAPER_OUT = 0.946, 0.927   # link plates taper, inner forward and outer back
# Drafts: the rings, cogs and jockeys each turned and scaled a hair across
# their thickness, the rollers coned, and each family of link plate (inner or
# outer, left or right) inset across its thickness by its own amount. Every
# wall face in the chain's plane then leans out of it by an angle no other
# part's shares, so none can lie on another's plane.
SPROCKET_DRAFT = (0.0030, 0.0042, 0.0060, 0.0072, 0.0084, 0.0096, 0.0108, 0.0120, 0.0160,
                  0.0180)
ROLLER_CONE = 0.95          # the right-hand end of a roller this much narrower
PLATE_INSET = {("in", 1.0): 0.00005, ("in", -1.0): 0.00010, ("out", 1.0): 0.00015,
               ("out", -1.0): 0.00020}
RIGHT_PLATE_SCALE = 0.953    # the right-hand plate of a pair a little shallower
LEVEL = 0.00012             # plate stagger step: every plate face on its own plane
INNER_A, INNER_T = 0.00145, 0.00120
OUTER_B, OUTER_T = 0.00205, 0.00120
PLATE_LEVELS = 5
APEX_LEVELS = 10
TILT_STEP_DEG = 1.201         # and a tilt about its own axis, so crowded plates differ in normal
GUIDE_OFF = (0.020, -0.068)  # upper jockey from the rear axle (x, z)
CAGE_LEN = 0.072

# --- Stand -------------------------------------------------------------------------
STAND_PIVOT = (-0.090, 0.030, 0.256)   # construction frame
FOOT_X = -0.235                        # world, after the lean
FOOT_Y = 0.165
FOOT_Y_TUCKED = 0.040                  # --tuck-stand

# --- Falsifier sizes -----------------------------------------------------------------
FLOAT_TYRE = 0.003
SLIP_WHEEL = 0.002
SHORT_SPOKE = 0.009
DISH_WHEEL = 0.003
STEEP_DEG = 6.0
BUNCH_DEG = 4.0
LIFT_CHAIN = 0.005
SHIFT_ROLLERS = 0.0015      # every roller along its pin, off the chain's plane
POP_BOTTLE = 0.080         # straight off the tube, clear of the cage's hoops

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (1.670, 0.438, 0.997)
BASE_TRIS_MIN = 45600
BASE_TRIS_MAX = 46600
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 10
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 970
BAKE_RES = 1024
CAGE_EXTRUSION = 0.003
# per slot: paint, chrome, alloy, steel, tread, gum, leather, tape, black, bottle
FACE_FLOORS = (940, 5650, 6250, 7410, 480, 850, 320, 970, 1620, 158)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
CONTACT_BAND = 2e-5
# Hubs coaxial with the dropout eyes.
COAX_TOL = 0.0005
# Spoke seats: hub end buried in its flange, rim end inside its nipple.
FLANGE_SEAT_MIN = 0.0020
FLANGE_SEAT_MAX = 0.0040
NIPPLE_AXIS_TOL = 0.0003
NIPPLE_DEPTH_MIN = 0.0020
# Wheels in the frame's centre plane; frame and wheelbase size.
PLANE_TOL = 0.0010
PLANE_ANGLE_MAX_DEG = 0.3
SEAT_TUBE_LEN = 0.580
WHEELBASE = 1.000
SIZE_TOL = 0.004
# Steering trail.
TRAIL_MIN = 0.045
TRAIL_MAX = 0.065
TRAIL_Y_TOL = 0.003
# Lacing: 36 spokes, 18 a flange, equal pitch at the rim, three-cross.
PITCH_TOL_DEG = 0.3
CROSS_MIN_DEG = 58.0
CROSS_MAX_DEG = 62.0
# Chain seated on the ring and the cog; a straight chain line.
RING_ENGAGED_MIN = 20
COG_ENGAGED_MIN = 6
SEAT_MIN = 0.0005
SEAT_MAX = 0.0065
CHAINLINE_TOL = 0.0010
# Stance: mass centre inside the triangle of both contacts and the stand foot.
STANCE_MARGIN = 0.020
HERO_YAW_DEG = -50.0
WALL_Y = 2.6

PAINT_IDX, CHROME_IDX, ALLOY_IDX, STEEL_IDX, RUBBER_IDX = 0, 1, 2, 3, 4
GUM_IDX, LEATHER_IDX, TAPE_IDX, BLACK_IDX, BOTTLE_IDX = 5, 6, 7, 8, 9
# Densities (kg/m^3) per material slot for the stance audit: frame tubes and
# rims are modelled solid but are hollow, so they carry an effective density;
# tyres are modelled solid round an air chamber.
DENSITY = (1100.0, 7800.0, 1500.0, 7800.0, 150.0, 150.0, 900.0, 600.0, 1200.0, 1000.0)

# Part tags: a face attribute naming which part a face belongs to, so the
# audits can find the shells they measure. Every measured value is read from
# the vertices, never from these constants.
(T_NONE, T_TYRE_F, T_TYRE_R, T_RIM_F, T_RIM_R, T_HUB_F, T_HUB_R, T_SPOKE_F, T_SPOKE_R,
 T_NIP_F, T_NIP_R, T_EYE_F, T_EYE_R, T_FRAME, T_HEADTUBE, T_SEATTUBE, T_RING, T_COG,
 T_ROLLER, T_PLATE, T_FOOT, T_BOTTLE, T_PULLEY) = range(23)

ZAX = Vector((0.0, 0.0, 1.0))
YAX = Vector((0.0, 1.0, 0.0))
XAX = Vector((1.0, 0.0, 0.0))

# --- Derived layout ------------------------------------------------------------------
_ST = math.radians(ST_DEG)
_HA = math.radians(HT_DEG)
BB_Z = R_TYRE - BB_DROP
BB = Vector((0.0, 0.0, BB_Z))
AXLE_RX = -math.sqrt(CS_LEN ** 2 - BB_DROP ** 2)
ST_DIR = Vector((-math.cos(_ST), 0.0, math.sin(_ST)))
HT_DIR = Vector((-math.cos(_HA), 0.0, math.sin(_HA)))
HT_FWD = Vector((math.sin(_HA), 0.0, math.cos(_HA)))
TT_Z = BB_Z + ST_CT * math.sin(_ST)
ST_TT = BB + ST_DIR * ST_CT
COT_HA = math.cos(_HA) / math.sin(_HA)


def steer_x(z):
    return ST_TT.x + TT_EFF + (TT_Z - z) * COT_HA


def steer_pt(z):
    return Vector((steer_x(z), 0.0, z))


HT_TOP_Z = TT_Z + HT_ABOVE_TT
HT_BOT_Z = HT_TOP_Z - HT_LEN * math.sin(_HA)
DT_HT_Z = HT_BOT_Z + DT_ABOVE_HT_BOT
AXLE_FX = steer_x(R_TYRE) + FORK_OFFSET / math.sin(_HA)
AXLE_F = Vector((AXLE_FX, 0.0, R_TYRE))
AXLE_R = Vector((AXLE_RX, 0.0, R_TYRE))
DT_TOP = steer_pt(DT_HT_Z)
DT_DIR = (DT_TOP - BB).normalized()
DT_UP = Vector((-DT_DIR.z, 0.0, DT_DIR.x))    # the down tube's upper side
CROWN_Z = HT_BOT_Z - 0.022
STEM_Z = 0.898


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


# --------------------------------------------------------------------------
# Construction helpers (copied from showcase/motor-scooter, not imported)
# --------------------------------------------------------------------------

class Build:
    """The bmesh under construction, its part-tag layer and named vertex
    groups (for the falsifiers that move one assembly)."""

    def __init__(self, bm):
        self.bm = bm
        self.tag = bm.faces.layers.int.new("part")
        self.groups = {}
        self.bevel = []

    def part(self, tag=T_NONE, *groups, bevel=False):
        return _Part(self, tag, groups, bevel)


class _Part:
    def __init__(self, b, tag, groups, bevel):
        self.b, self.t, self.g, self.bevel = b, tag, groups, bevel

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
        vs = [bm.verts[i] for i in range(self.nv, len(bm.verts))]
        for g in self.g:
            self.b.groups.setdefault(g, []).extend(vs)
        if self.bevel:
            self.b.bevel.extend(vs)
        return False


def _mark(faces, mat_idx):
    for f in faces:
        f.material_index = mat_idx


def frame(ez, ex_hint):
    """Rotation whose local Z is ``ez`` and local X is ``ex_hint`` made
    orthogonal to it (columns ex, ey, ez; right-handed)."""
    ez = Vector(ez).normalized()
    ex = Vector(ex_hint)
    ex = (ex - ez * ex.dot(ez)).normalized()
    ey = ez.cross(ex)
    return Matrix((ex, ey, ez)).transposed()


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False, seg_mats=None, rmod=None):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: the profile
    is an open polyline closed by n-gon caps at its two ends; otherwise it
    is a closed polygon revolved into a ring shell."""
    c = Vector(center)
    m = rot if rot is not None else Matrix.Identity(3)
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        ring = []
        for j, (r, z) in enumerate(profile):
            rr = r * (rmod(i, j) if rmod else 1.0)
            ring.append(bm.verts.new(c + m @ Vector((rr * ca, rr * sa, z))))
        rings.append(ring)
    n = len(profile)
    last = n - 1 if solid else n
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for j in range(last):
            k = (j + 1) % n
            f = bm.faces.new((r0[j], r1[j], r1[k], r0[k]))
            f.material_index = seg_mats[j] if seg_mats else mat_idx
    if solid:
        f0 = bm.faces.new([rings[i][0] for i in reversed(range(segs))])
        f1 = bm.faces.new([rings[i][n - 1] for i in range(segs)])
        f0.material_index = mat_idx
        f1.material_index = mat_idx
    return [v for ring in rings for v in ring]


def add_sweep(bm, pts, radius, sides, mat_idx, phase=0.0, matfn=None, rfn=None, ref=None):
    """Capped tube swept along a polyline with parallel-transport frames.
    ``radius`` is a number or one per point; ``rfn(i, k)`` scales it per
    vertex; ``matfn(i)`` is the material of the band after point i."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    radii = list(radius) if isinstance(radius, (list, tuple)) else [radius] * n
    tans = []
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        tans.append((b - a).normalized())
    if ref is None:
        ref = ZAX if abs(tans[0].z) < 0.9 else XAX
    nrm = (Vector(ref) - tans[0] * Vector(ref).dot(tans[0])).normalized()
    rings = []
    for i, (p, t) in enumerate(zip(pts, tans)):
        nrm = (nrm - t * nrm.dot(t)).normalized()
        bi = t.cross(nrm)
        ring = []
        for k in range(sides):
            a = phase + 2.0 * math.pi * k / sides
            r = radii[i] * (rfn(i, k) if rfn else 1.0)
            ring.append(bm.verts.new(p + r * (nrm * math.cos(a) + bi * math.sin(a))))
        rings.append(ring)
    for i, (r0, r1) in enumerate(zip(rings, rings[1:])):
        for k in range(sides):
            m = (k + 1) % sides
            f = bm.faces.new((r0[k], r0[m], r1[m], r1[k]))
            f.material_index = matfn(i) if matfn else mat_idx
    f0 = bm.faces.new(tuple(reversed(rings[0])))
    f1 = bm.faces.new(tuple(rings[-1]))
    f0.material_index = matfn(0) if matfn else mat_idx
    f1.material_index = matfn(n - 2) if matfn else mat_idx
    return [v for ring in rings for v in ring]


def rrect(ha, hb, rc, n_corner=4):
    """Rounded rectangle loop (counter-clockwise)."""
    rc = max(min(rc, ha - 1e-4, hb - 1e-4), 0.0003)
    pts = []
    for k, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        cx, cy = sx * (ha - rc), sy * (hb - rc)
        a0 = 0.5 * math.pi * k
        for s in range(n_corner + 1):
            a = a0 + 0.5 * math.pi * s / n_corner
            pts.append((cx + rc * math.cos(a), cy + rc * math.sin(a)))
    return pts


def add_rbox(bm, ha, hb, rc, profile, origin, rot, mat_idx, n_corner=2):
    """Loft of rounded rectangles along local Z: profile [(inset, z)]."""
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


def add_prism(bm, outline, w0, w1, origin, rot, mat_idx):
    """Planar outline [(u, v)] extruded along local Z from w0 to w1."""
    o = Vector(origin)
    a = [bm.verts.new(o + rot @ Vector((u, v, w0))) for u, v in outline]
    b = [bm.verts.new(o + rot @ Vector((u, v, w1))) for u, v in outline]
    n = len(outline)
    faces = [bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i])) for i in range(n)]
    faces.append(bm.faces.new(tuple(reversed(a))))
    faces.append(bm.faces.new(tuple(b)))
    _mark(faces, mat_idx)
    return a + b


def add_loft(bm, rings_pts, mat_idx):
    """Closed loops [[Vector]] lofted in order, n-gon caps at both ends."""
    rings = [[bm.verts.new(p) for p in loop] for loop in rings_pts]
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


def add_bar(bm, pts, wax, half_w, half_t, rc, mat_idx, fillet=0.008, filleted=False, steps=3):
    """Flat bar bent in the plane normal to ``wax``: width along ``wax``,
    thickness in the bending plane; rounded-rectangle section."""
    pts = [Vector(p) for p in pts] if filleted else fillet_path(pts, fillet, steps)
    wax = Vector(wax).normalized()
    sec = rrect(half_w, half_t, rc, 1)
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


def fillet_corners(pts, rf, steps=5, min_deg=25.0):
    """Fillet only the vertices where the path turns by more than min_deg."""
    pts = [Vector(p) for p in pts]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, p, b = pts[i - 1], pts[i], pts[i + 1]
        if (p - a).angle(b - p, 0.0) < math.radians(min_deg):
            out.append(p)
            continue
        r = min(rf, (a - p).length * 0.45, (b - p).length * 0.45)
        p0 = p + (a - p).normalized() * r
        p1 = p + (b - p).normalized() * r
        for k in range(steps + 1):
            t = k / steps
            out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * p + t * t * p1)
    out.append(pts[-1])
    return out


def resample(pts, step):
    """Points at uniform arc-length spacing along a polyline (ends kept)."""
    pts = [Vector(p) for p in pts]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + (b - a).length)
    total = cum[-1]
    n = max(2, int(round(total / step)) + 1)
    out = []
    j = 0
    for k in range(n):
        s = total * k / (n - 1)
        while j < len(pts) - 2 and cum[j + 1] < s:
            j += 1
        seg = cum[j + 1] - cum[j]
        t = 0.0 if seg <= 0.0 else (s - cum[j]) / seg
        out.append(pts[j].lerp(pts[j + 1], min(max(t, 0.0), 1.0)))
    return out, total


def bezier(p0, p1, p2, p3, n):
    p0, p1, p2, p3 = (Vector(p) for p in (p0, p1, p2, p3))
    out = []
    for k in range(n + 1):
        t = k / n
        u = 1.0 - t
        out.append(u ** 3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t ** 3 * p3)
    return out


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


def pchip(keys):
    """Monotone cubic through (x, y) keys (Fritsch-Carlson): no overshoot."""
    xs = [k[0] for k in keys]
    ys = [k[1] for k in keys]
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [d[0]] + [0.0] * (n - 2) + [d[-1]]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] > 0.0:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def f(x):
        x = min(max(x, xs[0]), xs[-1])
        i = 0
        while i < n - 2 and x > xs[i + 1]:
            i += 1
        t = (x - xs[i]) / h[i]
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1])
    return f


def _se(c, n):
    return math.copysign(abs(c) ** (2.0 / n), c)


# --------------------------------------------------------------------------
# Frame
# --------------------------------------------------------------------------

def add_sleeve(bm, base, axis, ref, r_tube, l0, l1, mat_idx, segs=16, nz=3,
               bite=0.0006, thick=0.0012, power=5.0):
    """A lug socket: a sleeve round a tube from ``base`` along ``axis``, its
    far edge cut to a spear point on either side of ``ref`` (the frame's
    normal, so the points show in side view) and thinned to a feathered
    edge. The inner face bites the tube (one band: it is hidden in it); the
    base annulus is buried in the host the tube joins."""
    ez = Vector(axis).normalized()
    ex = (Vector(ref) - ez * Vector(ref).dot(ez)).normalized()
    ey = ez.cross(ex)
    b = Vector(base)
    r_in = r_tube - bite
    r_out = r_tube + thick
    r_edge = r_tube + 0.00025
    outer = []
    inner = [[], []]
    for j in range(nz + 1):
        t = j / nz
        ro = []
        for i in range(segs):
            phi = 2.0 * math.pi * i / segs
            length = l0 + l1 * abs(math.cos(phi)) ** power
            z = length * t
            r_o = r_out - (r_out - r_edge) * t ** 2.2
            d = ex * math.cos(phi) + ey * math.sin(phi)
            ro.append(bm.verts.new(b + ez * z + d * r_o))
            if j in (0, nz):
                inner[0 if j == 0 else 1].append(bm.verts.new(b + ez * z + d * r_in))
        outer.append(ro)
    faces = []
    for j in range(nz):
        for i in range(segs):
            k = (i + 1) % segs
            faces.append(bm.faces.new((outer[j][i], outer[j][k], outer[j + 1][k], outer[j + 1][i])))
    for i in range(segs):
        k = (i + 1) % segs
        faces.append(bm.faces.new((inner[0][i], inner[1][i], inner[1][k], inner[0][k])))
        faces.append(bm.faces.new((outer[0][i], inner[0][i], inner[0][k], outer[0][k])))
        faces.append(bm.faces.new((outer[nz][i], outer[nz][k], inner[1][k], inner[1][i])))
    _mark(faces, mat_idx)


def lathe_on(bm, profile, segs, mat_idx, center, axis, ref=XAX, solid=True, phase=0.0,
             rmod=None, seg_mats=None):
    if abs(Vector(axis).normalized().dot(Vector(ref))) > 0.9:
        ref = ZAX if abs(Vector(axis).normalized().z) < 0.9 else YAX
    return add_lathe(bm, profile, segs, mat_idx, center=center, rot=frame(axis, ref),
                     solid=solid, phase=phase, rmod=rmod, seg_mats=seg_mats)


def tube(bm, a, b, r, mat_idx, sides=16, phase=0.0):
    return add_sweep(bm, [a, b], r, sides, mat_idx, phase=phase)


def chainstay_path(s):
    return fillet_path([
        Vector((-0.004, s * 0.019, BB_Z + 0.002)),
        Vector((-0.060, s * 0.0215, BB_Z + 0.010)),
        Vector((-0.160, s * 0.030, BB_Z + 0.025)),
        Vector((-0.300, s * 0.050, BB_Z + 0.048)),
        Vector((AXLE_RX + 0.075, s * 0.062, R_TYRE - 0.004)),
        Vector((AXLE_RX + 0.028, s * 0.066, R_TYRE + 0.001)),
    ], 0.08, 3)


def seatstay_ends(s):
    top = BB + ST_DIR * ((TT_Z - 0.030 - BB_Z) / ST_DIR.z)
    return (Vector((top.x, s * 0.019, top.z)),
            Vector((AXLE_RX + 0.016, s * 0.065, R_TYRE + 0.040)))


def tapered(pts, r0, r1, chrome_tail=0.0):
    """Radii tapering along a path and a material function that chromes its
    last ``chrome_tail`` metres."""
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + (b - a).length)
    total = cum[-1]
    radii = [r0 + (r1 - r0) * (c / total) ** 1.4 for c in cum]

    def matfn(i):
        mid = 0.5 * (cum[i] + cum[i + 1])
        return CHROME_IDX if total - mid < chrome_tail else PAINT_IDX
    return radii, matfn


def add_dropout(b, centre, side, old, outline, eye_tag, group):
    """A dropout plate in the wheel's plane at the axle, and its eye: a
    boss round the axle hole the skewer clamps."""
    bm = b.bm
    yc = side * (old + 0.0028)
    with b.part(T_NONE, group, bevel=True):
        add_prism(bm, outline, yc - 0.00225, yc + 0.00225, Vector((centre.x, 0.0, centre.z)),
                  frame(YAX, XAX), CHROME_IDX)
    w0, w1 = side * (old - 0.0002), side * (old + 0.0058)
    lo, hi = min(w0, w1), max(w0, w1)
    with b.part(eye_tag, group):
        add_lathe(bm, [(0.0098, lo), (0.0104, lo + 0.0008), (0.0104, hi - 0.0008), (0.0098, hi)],
                  16, CHROME_IDX, center=Vector((centre.x, 0.0, centre.z)),
                  rot=frame(YAX, XAX), solid=True)


def rear_dropout_outline(drive):
    """(x, z) round the rear axle, in frame(YAX, XAX) coordinates (u = x,
    v = -z)."""
    pts = [(0.036, -0.007), (0.036, 0.009), (0.022, 0.044), (0.010, 0.048), (-0.012, 0.014),
           (-0.014, 0.000)]
    if drive:
        pts += [(-0.012, -0.020), (-0.004, -0.034), (0.008, -0.032), (0.012, -0.012)]
    else:
        pts += [(-0.008, -0.011), (0.010, -0.011)]
    return [(x, -z) for x, z in pts]


def fork_dropout_outline():
    pts = [(-0.008, 0.032), (0.010, 0.028), (0.012, 0.000), (0.004, -0.010), (-0.008, -0.008),
           (-0.012, 0.004)]
    return [(x, -z) for x, z in pts]


def add_frame(b, steep_head):
    bm = b.bm
    # main triangle
    with b.part(T_FRAME, "frame"):
        tube(bm, ST_TT, steer_pt(TT_Z), R_TT, PAINT_IDX)
        tube(bm, BB, DT_TOP, R_DT, PAINT_IDX)
    with b.part(T_SEATTUBE, "frame"):
        # its own phase: rings sharing the down tube's start would weld the two
        tube(bm, BB, BB + ST_DIR * (ST_CT + ST_EXT), R_ST, PAINT_IDX, phase=math.pi / 16.0)
    with b.part(T_HEADTUBE, "frame"):
        vs = tube(bm, steer_pt(HT_BOT_Z), steer_pt(HT_TOP_Z), R_HT, PAINT_IDX, sides=20)
        if steep_head:
            mid = steer_pt(0.5 * (HT_BOT_Z + HT_TOP_Z))
            m = Matrix.Rotation(math.radians(STEEP_DEG), 3, "Y")
            for v in vs:
                v.co = mid + m @ (v.co - mid)
    with b.part(T_NONE, "frame"):
        # head badge: a blank oval plate curved round the head tube's front
        zc = 0.5 * (HT_BOT_Z + HT_TOP_Z) + 0.006

        def badge(u, v):
            x, y = 2.0 * u - 1.0, 2.0 * v - 1.0
            ex_, ey_ = x * math.sqrt(1.0 - 0.5 * y * y), y * math.sqrt(1.0 - 0.5 * x * x)
            ang = ex_ * 0.62
            c = steer_pt(zc) + HT_DIR * (ey_ * 0.017)
            n = HT_FWD * math.cos(ang) + YAX * math.sin(ang)
            return c + n * (R_HT + 0.0009), n
        add_sheet(bm, badge, 6, 6, 0.0016, CHROME_IDX)

        # lugs
        add_sleeve(bm, steer_pt(HT_TOP_Z) + HT_DIR * 0.0008, -HT_DIR, YAX, R_HT, 0.020, 0.016,
                   CHROME_IDX, segs=24)
        add_sleeve(bm, steer_pt(TT_Z) - XAX * 0.010, -XAX, YAX, R_TT, 0.032, 0.022, CHROME_IDX)
        add_sleeve(bm, steer_pt(HT_BOT_Z) - HT_DIR * 0.0008, HT_DIR, YAX, R_HT, 0.020, 0.016,
                   CHROME_IDX, segs=24)
        add_sleeve(bm, DT_TOP - DT_DIR * 0.010, -DT_DIR, YAX, R_DT, 0.034, 0.024, CHROME_IDX)
        add_sleeve(bm, BB + ST_DIR * (ST_CT + ST_EXT - 0.0015), -ST_DIR, YAX, R_ST, 0.030, 0.022,
                   CHROME_IDX)
        add_sleeve(bm, ST_TT + XAX * 0.010, XAX, YAX, R_TT, 0.028, 0.020, CHROME_IDX)
        add_sleeve(bm, BB + ST_DIR * 0.008, ST_DIR, YAX, R_ST, 0.036, 0.018, CHROME_IDX)
        add_sleeve(bm, BB + DT_DIR * 0.008, DT_DIR, YAX, R_DT, 0.038, 0.018, CHROME_IDX)
        # seat-lug collar round the post and the binder bolt behind it
        top = BB + ST_DIR * (ST_CT + ST_EXT)
        lathe_on(bm, [(0.0128, -0.006), (0.0160, -0.0056), (0.0162, 0.0030), (0.0150, 0.0062),
                      (0.0128, 0.0066)], 20, CHROME_IDX, top, ST_DIR, solid=False)
        back = top - ST_DIR * 0.016 - HT_FWD * 0.0
        binder = Vector((back.x - 0.0175, 0.0, back.z - 0.004))
        lathe_on(bm, [(0.0050, -0.012), (0.0056, -0.011), (0.0056, 0.011), (0.0050, 0.012)], 12,
                 CHROME_IDX, binder, YAX)
        lathe_on(bm, [(0.0040, 0.011), (0.0055, 0.0115), (0.0055, 0.0165), (0.0045, 0.017)], 6,
                 CHROME_IDX, binder, YAX)
        add_rbox(bm, 0.0070, 0.0105, 0.004, [(0.0015, -0.010), (0.0, -0.0085), (0.0, 0.0085),
                                             (0.0015, 0.010)],
                 Vector((back.x - 0.0105, 0.0, back.z - 0.004)), frame(YAX, XAX), CHROME_IDX)
        # bottom-bracket shell and cups
        lathe_on(bm, [(0.0180, -0.0345), (0.0200, -0.0335), (0.0200, 0.0335), (0.0180, 0.0345)],
                 20, CHROME_IDX, BB, YAX)
        for s in (1.0, -1.0):
            lathe_on(bm, [(0.0150, s * 0.0320), (0.0212, s * 0.0328), (0.0212, s * 0.0372),
                          (0.0150, s * 0.0380)], 20, BLACK_IDX, BB, YAX, solid=False)
    # stays
    with b.part(T_NONE, "frame"):
        for s in (1.0, -1.0):
            pts = chainstay_path(s)
            radii, matfn = tapered(pts, 0.0110, 0.0062, chrome_tail=0.050)
            add_sweep(bm, pts, radii, 14, PAINT_IDX, matfn=matfn)
            d0 = (pts[1] - pts[0]).normalized()
            add_sleeve(bm, pts[0] + d0 * 0.012, d0, ZAX, 0.0110, 0.020, 0.012, CHROME_IDX,
                       segs=16)
            top, bot = seatstay_ends(s)
            spts = [top.lerp(bot, k / 8.0) for k in range(9)]
            radii, matfn = tapered(spts, 0.0082, 0.0060, chrome_tail=0.045)
            add_sweep(bm, spts, radii, 12, PAINT_IDX, matfn=matfn)
            d = (top - bot).normalized()
            lathe_on(bm, [(0.0080, -0.006), (0.0090, -0.002), (0.0088, 0.002), (0.0068, 0.0055),
                          (0.0035, 0.0072)], 16, CHROME_IDX, top, d)
        # brake bridge between the seat stays
        top, bot = seatstay_ends(1.0)
        t = _bridge_t(top, bot)
        p = bot.lerp(top, t)
        tube(bm, Vector((p.x, -p.y + 0.002, p.z)), Vector((p.x, p.y - 0.002, p.z)), 0.0055,
             PAINT_IDX, sides=12)
        # chain-stay bridge behind the bottom bracket
        cs = chainstay_path(1.0)
        q = _path_at_x(cs, -0.125)
        tube(bm, Vector((q.x, -q.y + 0.003, q.z)), Vector((q.x, q.y - 0.003, q.z)), 0.0065,
             PAINT_IDX, sides=12)
    # rear dropouts and eyes
    for s, drive in ((1.0, False), (-1.0, True)):
        add_dropout(b, AXLE_R, s, REAR_OLD, rear_dropout_outline(drive), T_EYE_R, "frame")
    add_fork(b)


def _bridge_t(top, bot):
    """Seat-stay station 0.370 m from the rear axle."""
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        p = bot.lerp(top, mid)
        if math.hypot(p.x - AXLE_R.x, p.z - AXLE_R.z) < 0.370:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _path_at_x(pts, x):
    for a, b in zip(pts, pts[1:]):
        if (a.x - x) * (b.x - x) <= 0.0:
            t = (x - a.x) / (b.x - a.x)
            return a.lerp(b, t)
    return pts[-1]


def add_fork(b):
    bm = b.bm
    with b.part(T_NONE, "frame"):
        # sloping crown, chromed, square to the steering axis
        c = steer_pt(CROWN_Z)
        add_rbox(bm, 0.0165, 0.0105, 0.0055, [(0.0045, -0.041), (0.0015, -0.039), (0.0, -0.034),
                                              (0.0, 0.034), (0.0015, 0.039), (0.0045, 0.041)],
                 c, frame(YAX, HT_FWD), CHROME_IDX)
        # steerer up through the head tube into the headset's locknut
        tube(bm, c, steer_pt(HT_TOP_Z + 0.014), 0.0112, CHROME_IDX, sides=16)
        # headset: lower cup on the crown, upper cup, washer and knurled locknut
        lathe_on(bm, [(0.0105, -0.0135), (0.0182, -0.0135), (0.0190, -0.010), (0.0190, 0.001),
                      (0.0172, 0.004), (0.0105, 0.004)], 20, CHROME_IDX,
                 steer_pt(HT_BOT_Z), HT_DIR, solid=False)
        lathe_on(bm, [(0.0105, -0.004), (0.0172, -0.004), (0.0190, -0.001), (0.0190, 0.008),
                      (0.0105, 0.008)], 20, CHROME_IDX, steer_pt(HT_TOP_Z), HT_DIR, solid=False)
        lathe_on(bm, [(0.0100, 0.0078), (0.0176, 0.0078), (0.0176, 0.0105), (0.0100, 0.0105)], 20,
                 CHROME_IDX, steer_pt(HT_TOP_Z), HT_DIR, solid=False)
        lathe_on(bm, [(0.0100, 0.0103), (0.0178, 0.0103), (0.0182, 0.0125), (0.0182, 0.0185),
                      (0.0170, 0.0205), (0.0100, 0.0205)], 24, CHROME_IDX, steer_pt(HT_TOP_Z),
                 HT_DIR, solid=False,
                 rmod=lambda i, j: 1.035 if (i % 2 and 2 <= j <= 3) else 1.0)
        # blades: out of the crown's sockets, straight, raked forward to the dropouts
        for s in (1.0, -1.0):
            top = c + YAX * (s * 0.030) - HT_DIR * 0.004
            y_do = s * (FRONT_OLD + 0.0028)
            tip = AXLE_F + Vector((-0.003, y_do, 0.024))
            p1 = steer_pt(CROWN_Z - 0.230) + YAX * (s * 0.046)
            ctrl = steer_pt(CROWN_Z - 0.300) + YAX * (s * 0.050)
            pts = [top.lerp(p1, k / 6.0) for k in range(6)]
            for k in range(7):
                t = k / 6.0
                pts.append((1 - t) ** 2 * p1 + 2 * (1 - t) * t * ctrl + t * t * tip)
            radii, matfn = tapered(pts, 0.0125, 0.0068, chrome_tail=0.130)
            add_sweep(bm, pts, radii, 14, PAINT_IDX, matfn=matfn, ref=XAX)
            d0 = (pts[1] - pts[0]).normalized()
            add_sleeve(bm, pts[0] + d0 * 0.002, d0, XAX, 0.0125, 0.020, 0.014, CHROME_IDX,
                       segs=16)
    for s in (1.0, -1.0):
        add_dropout(b, AXLE_F, s, FRONT_OLD, fork_dropout_outline(), T_EYE_F, "frame")


# --------------------------------------------------------------------------
# Wheels
# --------------------------------------------------------------------------

def add_revolve(bm, c, profile, segs, matfn, a0=-0.5 * math.pi):
    """A closed (r, w) profile revolved round the axle (Y) through ``c``;
    ring 0 points straight down."""
    rings = []
    for k in range(segs):
        a = a0 + 2.0 * math.pi * k / segs
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((c.x + r * ca, c.y + w, c.z + r * sa)) for r, w in profile])
    n = len(profile)
    for k in range(segs):
        r0, r1 = rings[k], rings[(k + 1) % segs]
        for j in range(n):
            m = (j + 1) % n
            f = bm.faces.new((r0[j], r1[j], r1[m], r0[m]))
            f.material_index = matfn(j)
    return [v for ring in rings for v in ring]


def tyre_profile():
    s = TYRE_SEC
    rc = R_TYRE - s
    pts = [(0.3110, -0.0074)]
    ts = []
    for k in range(11):
        t = math.radians(-125.0 + 250.0 * k / 10.0)
        pts.append((rc + s * math.cos(t), s * math.sin(t)))
        ts.append(t)
    pts.append((0.3110, 0.0074))
    tread = set()
    for j in range(1, 11):
        if abs(ts[j - 1]) < math.radians(55.0) and abs(ts[j]) < math.radians(55.0):
            tread.add(j)
    return pts, tread


def hub_profile(old, f1, f2, rear):
    def flange(f):
        return [(0.0120, f - 0.0035), (0.0200, f - 0.0017), (FLANGE_R, f - 0.0008),
                (FLANGE_R, f + 0.0008), (0.0200, f + 0.0017), (0.0120, f + 0.0035)]
    p = [(0.0098, -old), (0.0110, -old + 0.0010), (0.0110, -old + 0.0055),
         (0.0090, -old + 0.0065), (0.0125, -old + 0.0080)]
    if rear:
        p += [(0.0125, f1 - 0.0060)]
    p += flange(f1)
    p += [(0.0112, 0.5 * (f1 + f2))]
    p += flange(f2)
    p += [(0.0125, old - 0.0080), (0.0090, old - 0.0065), (0.0110, old - 0.0055),
          (0.0110, old - 0.0010), (0.0098, old)]
    return p


def add_wheel(b, c, front, short_spoke=False, bunch=False):
    bm = b.bm
    g = "wheel_f" if front else "wheel_r"
    tags = ((T_TYRE_F, T_RIM_F, T_HUB_F, T_SPOKE_F, T_NIP_F) if front
            else (T_TYRE_R, T_RIM_R, T_HUB_R, T_SPOKE_R, T_NIP_R))
    old = FRONT_OLD if front else REAR_OLD
    f1, f2 = FRONT_FLANGES if front else REAR_FLANGES
    prof, tread = tyre_profile()
    with b.part(tags[0], g, g + "_tyre"):
        add_revolve(bm, c, prof, TYRE_SEGS,
                    lambda j: RUBBER_IDX if j in tread else GUM_IDX)
    rim_prof = RIM_HALF + [(r, -w) for r, w in reversed(RIM_HALF)]
    with b.part(tags[1], g, g + "_rim"):
        add_revolve(bm, c, rim_prof, RIM_SEGS, lambda j: ALLOY_IDX, a0=-0.5 * math.pi + 0.017)
    with b.part(tags[2], g):
        add_lathe(bm, hub_profile(old, f1, f2, not front), 16, ALLOY_IDX, center=c,
                  rot=frame(YAX, XAX), solid=True)
    step = 2.0 * math.pi / SPOKES
    hole_step = CROSS * 2.0 * step
    for k in range(SPOKES):
        theta = step * k
        side = 1.0 if k % 2 == 0 else -1.0
        m = k // 2
        f = f2 if side > 0 else f1
        phi = theta + (hole_step if m % 2 == 0 else -hole_step)
        if bunch and front and k == 5:
            theta += math.radians(BUNCH_DEG)
            phi += math.radians(BUNCH_DEG)
        e = c + Vector((SPOKE_END_R * math.cos(theta), side * RIM_HOLE_W,
                        SPOKE_END_R * math.sin(theta)))
        h = c + Vector((HOLE_R * math.cos(phi), f, HOLE_R * math.sin(phi)))
        u = (e - h).normalized()
        end = e - u * SHORT_SPOKE if (short_spoke and front and k == 4) else e
        with b.part(tags[3], g, g + "_spoke_rim"):
            add_sweep(bm, [h, end], SPOKE_R, SPOKE_SIDES, STEEL_IDX, phase=0.37 * k)
        with b.part(tags[4], g, g + "_rim"):
            lathe_on(bm, [(0.0019, 0.0), (0.0019, NIPPLE_LEN)], 5, CHROME_IDX, e - u * NIPPLE_IN,
                     u, ref=YAX)
    # axle, skewer, cam lever on the left, cone nut on the right
    with b.part(T_NONE, g):
        lathe_on(bm, [(0.0045, -(old + 0.012)), (0.0045, old + 0.012)], 12, STEEL_IDX, c, YAX)
        lathe_on(bm, [(0.0070, old + 0.0055), (0.0088, old + 0.0065), (0.0088, old + 0.0130),
                      (0.0072, old + 0.0160)], 20, ALLOY_IDX, c, YAX)
        lathe_on(bm, [(0.0082, -(old + 0.0055)), (0.0090, -(old + 0.0070)),
                      (0.0072, -(old + 0.0130)), (0.0045, -(old + 0.0150))], 16, ALLOY_IDX, c, YAX)
        lv = Vector((-0.35, 0.0, 0.94)) if front else Vector((0.62, 0.0, 0.78))
        pts = [c + YAX * (old + 0.0125) + lv * 0.004, c + YAX * (old + 0.0150) + lv * 0.030,
               c + YAX * (old + 0.0200) + lv * 0.056]
        add_bar(bm, pts, YAX, 0.0035, 0.0048, 0.0025, ALLOY_IDX, fillet=0.02)
    if not front:
        with b.part(T_NONE, g):
            add_lathe(bm, [(0.0165, -0.0262), (0.0180, -0.0270), (0.0180, -0.0585),
                           (0.0165, -0.0593)], 24, STEEL_IDX, center=c, rot=frame(YAX, XAX),
                      solid=True)


# --------------------------------------------------------------------------
# Drivetrain: sprockets and the chain path
# --------------------------------------------------------------------------

def pitch_radius(n):
    return PITCH / (2.0 * math.sin(math.pi / n))


def add_sprocket(bm, centre, y, n, phase, r_in, half_t, mat_idx, draft=0.0, simple=False):
    """A toothed annulus in the XZ plane at ``y``: four points per tooth on
    the outer loop (flank bases and tip corners), one inner point per tooth;
    each tooth's cap is one n-gon, triangulated later."""
    r_p = pitch_radius(n)
    step = 2.0 * math.pi / n
    r_f = r_p - 0.0012
    r_t = r_p + 0.0035
    g = min(0.0031 / r_f, 0.35 * step)
    w1 = 0.5 * step - g
    w2 = min(0.0012 / r_p, 0.8 * w1)
    outer, inner = [], []
    tooth = ((-w1, r_f), (0.0, r_t), (w1, r_f)) if simple else \
        ((-w1, r_f), (-w2, r_t), (w2, r_t), (w1, r_f))
    ppt = len(tooth)
    for j in range(n):
        a = phase + j * step
        for da, r in tooth:
            outer.append((a + da, r))
        inner.append((a, r_in))

    def v(ar, yy, top=False):
        a, r = ar
        if top:
            a, r = a + draft, r * (1.0 + draft)
        return bm.verts.new((centre.x + r * math.cos(a), yy, centre.z + r * math.sin(a)))
    ot = [v(p, y + half_t, True) for p in outer]
    ob = [v(p, y - half_t) for p in outer]
    it = [v(p, y + half_t, True) for p in inner]
    ib = [v(p, y - half_t) for p in inner]
    faces = []
    m = len(outer)
    for j in range(n):
        o = [ppt * j + q for q in range(ppt)] + [(ppt * j + ppt) % m]
        jn = (j + 1) % n
        faces.append(bm.faces.new([it[j]] + [ot[q] for q in o] + [it[jn]]))
        faces.append(bm.faces.new([ib[jn]] + [ob[q] for q in reversed(o)] + [ib[j]]))
        faces.append(bm.faces.new((it[jn], ib[jn], ib[j], it[j])))
    for q in range(m):
        k = (q + 1) % m
        faces.append(bm.faces.new((ot[q], ob[q], ob[k], ot[k])))
    _mark(faces, mat_idx)


def _tangent(ca, ra, sa, cb, rb, sb):
    d = cb - ca
    dist = d.length
    dh = d / dist
    dp = Vector((-dh.y, dh.x))
    k = (sb * rb - sa * ra) / dist
    s = math.sqrt(max(0.0, 1.0 - k * k))
    n = dh * k + dp * s
    return ca - n * (sa * ra), cb - n * (sb * rb)


def chain_segments(circles):
    n = len(circles)
    deps, arrs = [None] * n, [None] * n
    for i in range(n):
        ca, ra, sa = circles[i]
        cb, rb, sb = circles[(i + 1) % n]
        pa, pb = _tangent(ca, ra, sa, cb, rb, sb)
        deps[i] = pa
        arrs[(i + 1) % n] = pb
    segs = []
    for i in range(n):
        c, r, s = circles[i]
        a0 = math.atan2(arrs[i].y - c.y, arrs[i].x - c.x)
        a1 = math.atan2(deps[i].y - c.y, deps[i].x - c.x)
        if s > 0:
            sweep = (a1 - a0) % (2.0 * math.pi)
        else:
            sweep = -((a0 - a1) % (2.0 * math.pi))
        segs.append(("arc", c, r, a0, sweep, i))
        segs.append(("line", deps[i], arrs[(i + 1) % n], None, None, i))
    return segs


def seg_len(sg):
    if sg[0] == "arc":
        return abs(sg[4]) * sg[2]
    return (sg[2] - sg[1]).length


def chain_circles(alpha, lift):
    c1 = Vector((BB.x, BB.z))
    c2 = Vector((AXLE_R.x, AXLE_R.z))
    g = c2 + Vector(GUIDE_OFF)
    t = g + Vector((math.sin(alpha), -math.cos(alpha))) * CAGE_LEN
    rp = pitch_radius(PULLEY_TEETH)
    return [(c1, pitch_radius(RING_TEETH[0]) + lift, 1.0),
            (c2, pitch_radius(COG_TEETH[DRIVEN_COG]) + lift, 1.0),
            (g, rp, -1.0), (t, rp, 1.0)]


def solve_chain(lift, n_fixed=None):
    """The cage angle that makes the loop an even whole number of pitches,
    and the pins spaced one pitch apart along it. ``n_fixed`` keeps a given
    chain (the lifted chain is the same chain; the cage swings to take it up)."""
    def length(alpha):
        return sum(seg_len(sg) for sg in chain_segments(chain_circles(alpha, lift)))
    l0 = length(0.0)
    n_links = int(round(l0 / PITCH / 2.0)) * 2
    alpha = None
    tries = (n_fixed,) if n_fixed else (n_links, n_links + 2, n_links - 2)
    for n_try in tries:
        target = n_try * PITCH
        lo, hi = -0.7, 0.7
        flo, fhi = length(lo) - target, length(hi) - target
        if flo * fhi > 0.0:
            continue
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            fm = length(mid) - target
            if fm * flo > 0.0:
                lo, flo = mid, fm
            else:
                hi = mid
        alpha, n_links = 0.5 * (lo + hi), n_try
        break
    if alpha is None:
        raise RuntimeError("chain length has no cage solution")
    circles = chain_circles(alpha, lift)
    segs = chain_segments(circles)
    lens = [seg_len(sg) for sg in segs]
    pins = []
    for k in range(n_links):
        s = k * PITCH
        i = 0
        while i < len(segs) - 1 and s > lens[i]:
            s -= lens[i]
            i += 1
        sg = segs[i]
        if sg[0] == "arc":
            _, c, r, a0, sweep, ci = sg
            a = a0 + math.copysign(s / r, sweep)
            p = c + Vector((math.cos(a), math.sin(a))) * r
            sgn = 1.0 if sweep > 0 else -1.0
            tang = Vector((-math.sin(a), math.cos(a))) * sgn
            pins.append((p, tang, ci, a))
        else:
            _, p0, p1, _, _, ci = sg
            d = (p1 - p0).normalized()
            pins.append((p0 + d * s, d, None, None))
    return circles, pins


def sprocket_phase(pins, circle_idx, n):
    """Tooth phase that seats the middle pin of a wrap in a valley."""
    angs = [a for (_p, _t, ci, a) in pins if ci == circle_idx]
    if not angs:
        return 0.0
    a = angs[len(angs) // 2]
    return a - math.pi / n


def inset_convex(poly, d):
    """A convex polygon with every edge moved ``d`` inwards."""
    n = len(poly)
    pts = [Vector(p) for p in poly]
    area = sum(pts[i].x * pts[(i + 1) % n].y - pts[(i + 1) % n].x * pts[i].y for i in range(n))
    sgn = 1.0 if area > 0.0 else -1.0
    lines = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        e = (b - a).normalized()
        nrm = Vector((-e.y, e.x)) * sgn
        lines.append((a + nrm * d, e))
    out = []
    for i in range(n):
        (p1, e1), (p2, e2) = lines[i - 1], lines[i]
        den = e1.x * e2.y - e1.y * e2.x
        t = ((p2.x - p1.x) * e2.y - (p2.y - p1.y) * e2.x) / den
        q = p1 + e1 * t
        out.append((q.x, q.y))
    return out


def add_chain(b, pins, shift):
    """Rollers and alternating inner and outer plate pairs. Every plate face
    that could share a plane with a near neighbour's is staggered by LEVEL,
    chosen greedily, so no two plates within reach sit on one plane."""
    bm = b.bm
    n = len(pins)

    # each roller's cone ends get a height chosen so that no roller within
    # reach has the same cone angle: equal angles are what let two cone faces
    # share a plane
    apex = []
    for k, (p, _t, _ci, _a) in enumerate(pins):
        used = {apex[j] for j in range(k) if (pins[j][0] - p).length < 0.06}
        lvl = next((q for q in range(APEX_LEVELS) if q not in used), None)
        if lvl is None:
            raise RuntimeError("roller cone levels ran out")
        apex.append(lvl)
    for k, (p, t, _ci, _a) in enumerate(pins):
        yc = CHAIN_Y + (SHIFT_ROLLERS if shift else 0.0)
        ah = 0.0018 + 0.0001 * apex[k]
        # each roller turned a further step (kept 10 deg clear of a face square
        # to the run): no two near rollers share a face plane
        ang = math.atan2(t.y, t.x) + ROLLER_PHASE + math.radians((ROLLER_STEP_DEG * k) % 40.0)
        with b.part(T_ROLLER, "chain"):
            r0, r1 = [], []
            for i in range(6):
                a = ang + 2.0 * math.pi * i / 6.0
                x, z = p.x + ROLLER_R * math.cos(a), p.y + ROLLER_R * math.sin(a)
                r0.append(bm.verts.new((x, yc - ROLLER_H, z)))
                x1 = p.x + ROLLER_R * ROLLER_CONE * math.cos(a)
                z1 = p.y + ROLLER_R * ROLLER_CONE * math.sin(a)
                r1.append(bm.verts.new((x1, yc + ROLLER_H, z1)))
            # steep cone ends, buried in the outer plates
            a0 = bm.verts.new((p.x, yc - ROLLER_H - ah, p.y))
            a1 = bm.verts.new((p.x, yc + ROLLER_H + ah, p.y))
            faces = []
            for i in range(6):
                j = (i + 1) % 6
                faces.append(bm.faces.new((r0[i], r0[j], r1[j], r1[i])))
                faces.append(bm.faces.new((r0[j], r0[i], a0)))
                faces.append(bm.faces.new((r1[i], r1[j], a1)))
            _mark(faces, STEEL_IDX)
    levels = {}
    placed = []
    combos = [(lv, tv) for tv in (0, 1, -1, 2, -2, 3, -3, 4, -4) for lv in range(PLATE_LEVELS)]
    for k in range(n):
        pa, pb = pins[k][0], pins[(k + 1) % n][0]
        cls = "in" if k % 2 == 0 else "out"
        cen = 0.5 * (pa + pb)
        used = {cb for (c2, cl2, cb) in placed if cl2 == cls and (c2 - cen).length < 0.075}
        combo = next((q for q in combos if q not in used), None)
        if combo is None:
            raise RuntimeError("chain plate stagger ran out of levels")
        placed.append((cen, cls, combo))
        levels[k] = (cls,) + combo
    for k in range(n):
        pa, pb = pins[k][0], pins[(k + 1) % n][0]
        cls, lv, tv = levels[k]
        u = (pb - pa).normalized()
        v = Vector((-u.y, u.x))
        L = (pb - pa).length
        # inner links taper forward, outer links back: their edge faces
        # never run parallel along a straight run
        if cls == "in":
            ha, hb = 0.0041, 0.0041 * TAPER_IN
        else:
            ha, hb = 0.0043 * TAPER_OUT, 0.0043
        loc = [(0.0, -ha), (-ha, 0.0), (0.0, ha), (L, hb), (L + hb, 0.0), (L, -hb)]
        yc = CHAIN_Y
        a0 = (INNER_A if cls == "in" else OUTER_B) + LEVEL * lv
        th = INNER_T if cls == "in" else OUTER_T
        tilt = math.radians(TILT_STEP_DEG * tv)
        ct, st = math.cos(tilt), math.sin(tilt)

        def place(x, z, yy):
            # tilt the plate about its own long axis (through the pin line)
            dv, dy = z, yy - yc
            z2, y2 = dv * ct - dy * st, dv * st + dy * ct
            q = pa + u * x + v * z2
            return (q.x, yc + y2, q.y)
        # the right-hand plate a hair shallower: a plate pair's side faces
        # would otherwise share their planes
        for s, sc in ((1.0, 1.0), (-1.0, RIGHT_PLATE_SCALE)):
            with b.part(T_PLATE, "chain"):
                ys = sorted((yc + s * a0, yc + s * (a0 + th)))
                base = [(x, z * sc) for x, z in loc]
                outer_loop = inset_convex(base, PLATE_INSET[(cls, s)])
                inner_face, outer_face = (base, outer_loop) if s > 0 else (outer_loop, base)
                lo = [bm.verts.new(place(x, z, ys[0])) for x, z in inner_face]
                hi = [bm.verts.new(place(x, z, ys[1])) for x, z in outer_face]
                m = len(loc)
                faces = [bm.faces.new((lo[i], lo[(i + 1) % m], hi[(i + 1) % m], hi[i]))
                         for i in range(m)]
                faces.append(bm.faces.new(tuple(reversed(lo))))
                faces.append(bm.faces.new(tuple(hi)))
                _mark(faces, STEEL_IDX)


def add_drivetrain(b, lift_chain, shift_rollers):
    bm = b.bm
    n_links = len(solve_chain(0.0)[1])
    circles, pins = solve_chain(LIFT_CHAIN if lift_chain else 0.0, n_links)
    ring_phase = sprocket_phase(pins, 0, RING_TEETH[0])
    cog_phase = sprocket_phase(pins, 1, COG_TEETH[DRIVEN_COG])
    # chainrings on the spider
    for i, (n, y) in enumerate(zip(RING_TEETH, RING_Y)):
        with b.part(T_RING, "drive"):
            add_sprocket(bm, BB, y, n, ring_phase if i == 0 else 0.0, 0.066 + 0.0005 * i, RING_T,
                         ALLOY_IDX, draft=SPROCKET_DRAFT[i], simple=(i != 0))
    with b.part(T_NONE, "drive"):
        # BB axle, drive crank boss, spider arms and the drive crank
        lathe_on(bm, [(0.0085, -0.058), (0.0085, 0.058)], 12, STEEL_IDX, BB, YAX)
        lathe_on(bm, [(0.0150, -0.0400), (0.0200, -0.0420), (0.0200, -0.0590),
                      (0.0165, -0.0610)], 24, ALLOY_IDX, BB, YAX)
        for k in range(5):
            a = 2.0 * math.pi * k / 5.0
            d = Vector((math.cos(a), 0.0, math.sin(a)))
            add_bar(bm, [BB + d * 0.012 + YAX * -0.0428, BB + d * 0.076 + YAX * -0.0428],
                    Vector((-d.z, 0.0, d.x)), 0.0090, 0.0024, 0.002, ALLOY_IDX)
            bp = BB + d * 0.072
            lathe_on(bm, [(0.0040, -0.0506), (0.0047, -0.0501), (0.0047, -0.0380),
                          (0.0040, -0.0375)], 12, CHROME_IDX, Vector((bp.x, 0.0, bp.z)), YAX)
        add_crank(bm, 1.0)
    with b.part(T_NONE, "drive"):
        lathe_on(bm, [(0.0165, 0.0400), (0.0200, 0.0420), (0.0200, 0.0590), (0.0165, 0.0610)],
                 24, ALLOY_IDX, BB, YAX)
        add_crank(bm, -1.0)
    # freewheel cogs on the rear hub
    for i, (n, y) in enumerate(zip(COG_TEETH, COG_Y)):
        with b.part(T_COG, "wheel_r"):
            phase = cog_phase if i == DRIVEN_COG else COG_PHASE_STEP * i
            add_sprocket(bm, AXLE_R, y, n, phase, 0.0160 + 0.0003 * i,
                         COG_T, STEEL_IDX, draft=SPROCKET_DRAFT[2 + i],
                         simple=(i != DRIVEN_COG))
    add_chain(b, pins, shift_rollers)
    add_rear_derailleur(b, circles, pins)
    add_front_derailleur(b)


def add_crank(bm, drive):
    """Crank arm at 3 o'clock (drive) or 9 o'clock (left), quill pedal with
    a toe clip and strap."""
    s = -1.0 if drive > 0 else 1.0          # side in Y
    d = XAX if drive > 0 else -XAX
    y0, y1 = s * 0.0510, s * 0.0605
    ym = 0.5 * (y0 + y1)
    loops = []
    for k in range(5):
        t = k / 4.0
        p = BB + d * (0.004 + (CRANK - 0.004) * t)
        hw = 0.0125 - 0.0045 * t
        loop = rrect(0.5 * abs(y1 - y0), hw, 0.0035, 2)
        loops.append([Vector((p.x, ym + yy, p.z + zz)) for yy, zz in loop])
    add_loft(bm, loops, ALLOY_IDX)
    eye = BB + d * CRANK
    lathe_on(bm, [(0.0105, min(y0, y1) - 0.0003), (0.0105, max(y0, y1) + 0.0003)], 16,
             ALLOY_IDX, eye, YAX)
    # pedal: spindle, barrel, two toothed cage plates, end plate
    lathe_on(bm, [(0.0055, s * 0.050), (0.0055, s * 0.160)] if s > 0 else
             [(0.0055, s * 0.160), (0.0055, s * 0.050)], 10, STEEL_IDX, eye, YAX)
    lathe_on(bm, [(0.0080, s * 0.066), (0.0095, s * 0.070), (0.0095, s * 0.150),
                  (0.0080, s * 0.154)] if s > 0 else
             [(0.0080, s * 0.154), (0.0095, s * 0.150), (0.0095, s * 0.070),
              (0.0080, s * 0.066)], 14, ALLOY_IDX, eye, YAX)
    for fx, tooth in ((0.030, 0.0155), (-0.030, 0.0148)):
        outline = [(0.074, -0.010), (0.156, -0.010), (0.156, 0.012)]
        for q in range(4):
            yy = 0.156 - (q + 0.5) * (0.082 / 4.0)
            outline += [(yy + 0.0045, 0.012), (yy + 0.0020, tooth), (yy - 0.0020, tooth),
                        (yy - 0.0045, 0.012)]
        outline += [(0.074, 0.012)]
        outline = [(s * yy, zz) for yy, zz in outline]
        if s < 0:
            outline.reverse()
        add_prism(bm, [(yy, zz) for yy, zz in outline], -0.00125, 0.00125,
                  Vector((eye.x + fx, 0.0, eye.z)), frame(XAX, YAX), ALLOY_IDX)
    add_rbox(bm, 0.0335, 0.0120, 0.004, [(0.0, -0.00125), (0.0, 0.00125)],
             Vector((eye.x, s * 0.155, eye.z + 0.001)), frame(YAX, XAX), ALLOY_IDX)
    # toe clip forward over the pedal, and its strap
    yc = s * 0.113
    clip = [Vector((eye.x + 0.029, yc, eye.z + 0.011)), Vector((eye.x + 0.060, yc, eye.z + 0.016)),
            Vector((eye.x + 0.082, yc, eye.z + 0.032)), Vector((eye.x + 0.086, yc, eye.z + 0.054)),
            Vector((eye.x + 0.072, yc, eye.z + 0.068)), Vector((eye.x + 0.046, yc, eye.z + 0.072))]
    add_bar(bm, clip, YAX, 0.0060, 0.0011, 0.0009, CHROME_IDX, fillet=0.02)
    strap = [Vector((eye.x + 0.050, yc, eye.z + 0.0725)), Vector((eye.x + 0.012, yc, eye.z + 0.070)),
             Vector((eye.x - 0.030, yc, eye.z + 0.042)), Vector((eye.x - 0.036, yc, eye.z + 0.000)),
             Vector((eye.x - 0.020, yc, eye.z - 0.013)), Vector((eye.x + 0.022, yc, eye.z - 0.013)),
             Vector((eye.x + 0.033, yc, eye.z + 0.004))]
    add_bar(bm, strap, YAX, 0.0062, 0.0008, 0.0006, BLACK_IDX, fillet=0.02)


def add_rear_derailleur(b, circles, pins):
    bm = b.bm
    g_c, rp, _ = circles[2]
    t_c = circles[3][0]
    ph_g = sprocket_phase(pins, 2, PULLEY_TEETH)
    ph_t = sprocket_phase(pins, 3, PULLEY_TEETH)
    with b.part(T_PULLEY, "rd"):
        add_sprocket(bm, Vector((g_c.x, 0.0, g_c.y)), CHAIN_Y, PULLEY_TEETH, ph_g, 0.0045,
                     PULLEY_T[0], BLACK_IDX, draft=SPROCKET_DRAFT[8])
    with b.part(T_PULLEY, "rd"):
        add_sprocket(bm, Vector((t_c.x, 0.0, t_c.y)), CHAIN_Y, PULLEY_TEETH, ph_t, 0.0045,
                     PULLEY_T[1], BLACK_IDX, draft=SPROCKET_DRAFT[9])
    with b.part(T_NONE, "rd", bevel=True):
        gw = Vector((g_c.x, 0.0, g_c.y))
        tw = Vector((t_c.x, 0.0, t_c.y))
        ax = (tw - gw).normalized()
        cage_rot = frame(YAX, ax)
        outline = []
        for k in range(7):
            a = math.pi * k / 6.0 + 0.5 * math.pi
            outline.append((0.0125 * math.cos(a), 0.0125 * math.sin(a)))
        L = (tw - gw).length
        for k in range(7):
            a = math.pi * k / 6.0 - 0.5 * math.pi
            outline.append((L + 0.0125 * math.cos(a), 0.0125 * math.sin(a)))
        # frame(YAX, ax): local x along the cage (G to T), local y across it
        for yp, sc in ((CHAIN_Y - 0.0056, 1.0), (CHAIN_Y + 0.0046, 0.965)):
            add_prism(bm, [(x * sc + L * 0.5 * (1.0 - sc), y * sc) for x, y in outline], yp,
                      yp + 0.0010, gw, cage_rot, ALLOY_IDX)
        for p in (gw, tw):
            lathe_on(bm, [(0.0052, CHAIN_Y - 0.0063), (0.0052, CHAIN_Y + 0.0063)], 10, CHROME_IDX,
                     Vector((p.x, 0.0, p.z)), YAX)
        # parallelogram body from the hanger bolt down to the cage pivot
        hanger = AXLE_R + Vector((-0.004, 0.0, -0.026))
        lathe_on(bm, [(0.0050, -0.0742), (0.0062, -0.0737), (0.0062, -0.0650),
                      (0.0055, -0.0640)], 16, CHROME_IDX, Vector((hanger.x, 0.0, hanger.z)), YAX)
        piv = gw
        d = (piv - hanger)
        body_ax = Vector((d.x, 0.0, d.z)).normalized()
        mid = hanger + d * 0.5
        # knuckles at the hanger and at the cage pivot, two link plates between
        lathe_on(bm, [(0.0095, -0.0800), (0.0105, -0.0790), (0.0105, -0.0670),
                      (0.0095, -0.0660)], 16, ALLOY_IDX, Vector((hanger.x, 0.0, hanger.z)), YAX)
        lathe_on(bm, [(0.0085, -0.0760), (0.0095, -0.0750), (0.0095, -0.0570),
                      (0.0085, -0.0560)], 14, ALLOY_IDX, Vector((piv.x, 0.0, piv.z)), YAX)
        # the inner link a little narrower and shorter than the outer
        links = ((-0.0755, 0.0020, 0.0078, 0.0), (-0.0678, 0.0016, 0.0070, -0.0015))
        for yc_, hw_, hb_, ext in links:
            add_rbox(bm, hw_, hb_, 0.0015, [(0.0006, -0.5 * d.length - 0.004 - ext),
                                            (0.0, -0.5 * d.length - 0.003 - ext),
                                            (0.0, 0.5 * d.length + 0.003 + ext),
                                            (0.0006, 0.5 * d.length + 0.004 + ext)],
                     Vector((mid.x, yc_, mid.z)), frame(body_ax, YAX), ALLOY_IDX, n_corner=1)
        lathe_on(bm, [(0.0038, -0.0700), (0.0038, CHAIN_Y - 0.0065)], 12, CHROME_IDX,
                 Vector((piv.x, 0.0, piv.z)), YAX)
        b.groups["rd_anchor"] = [hanger + (piv - hanger) * 0.30 + YAX * -0.0678]


def add_front_derailleur(b):
    bm = b.bm
    with b.part(T_NONE, "fd", bevel=True):
        s_fd = 0.150
        c = BB + ST_DIR * s_fd
        lathe_on(bm, [(0.0138, -0.009), (0.0168, -0.008), (0.0168, 0.008), (0.0138, 0.009)], 24,
                 ALLOY_IDX, c, ST_DIR, solid=False)
        a0, a1 = math.radians(80.0), math.radians(124.0)
        r0, r1 = pitch_radius(RING_TEETH[0]) + 0.0072, pitch_radius(RING_TEETH[0]) + 0.0300
        for yp, da, dr in ((-0.0525, 0.0, 0.0), (-0.0360, 0.03, 0.0015)):
            outline = []
            for k in range(9):
                a = a0 + da + (a1 - a0 - 2.0 * da) * k / 8.0
                outline.append(((r0 + dr) * math.cos(a), (r0 + dr) * math.sin(a)))
            for k in range(9):
                a = a1 - da - (a1 - a0 - 2.0 * da) * k / 8.0
                outline.append(((r1 - dr) * math.cos(a), (r1 - dr) * math.sin(a)))
            outline = [(x, -z) for x, z in outline]
            add_prism(bm, outline, yp, yp + 0.0010, Vector((BB.x, 0.0, BB.z)), frame(YAX, XAX),
                      ALLOY_IDX)
        for a in (a0 + 0.04, a1 - 0.05):
            r = 0.5 * (r0 + r1) + 0.004
            p = Vector((BB.x + r * math.cos(a), 0.0, BB.z + r * math.sin(a)))
            lathe_on(bm, [(0.0022, -0.0533), (0.0022, -0.0346)], 8, ALLOY_IDX, p, YAX)
        # body: from the clamp's drive side out over the cage
        am = math.radians(112.0)
        rm = 0.5 * (r0 + r1)
        top = Vector((BB.x + rm * math.cos(am), 0.0, BB.z + rm * math.sin(am)))
        p0 = c + YAX * -0.012
        p1 = top + YAX * -0.053
        ax = (p1 - p0).normalized()
        b.groups["fd_anchor"] = [p0.lerp(p1, 0.35)]
        add_rbox(bm, 0.0070, 0.0060, 0.003, [(0.0015, -0.002), (0.0, 0.0),
                                             ((0.0), (p1 - p0).length), (0.0015, (p1 - p0).length
                                                                         + 0.002)],
                 p0, frame(ax, ST_DIR), ALLOY_IDX)


# --------------------------------------------------------------------------
# Cockpit: stem, bars, tape, levers, cables, brakes
# --------------------------------------------------------------------------

HOOK_R = 0.068
BAR_R = 0.0119


def bar_centre():
    return Vector((steer_x(STEM_Z) + 0.100, 0.0, STEM_Z))


def bar_half(s):
    """One side of the drop bar, from the clamp outwards, as a polyline."""
    cb = bar_centre()
    xb, zb = cb.x, cb.z
    hc = Vector((xb + 0.045, s * 0.200, zb - HOOK_R))
    pts = [Vector((xb, 0.0, zb)), Vector((xb, s * 0.130, zb)), Vector((xb + 0.045, s * 0.200, zb))]
    for k in range(1, 13):
        th = math.radians(90.0 - 15.0 * k)
        pts.append(hc + Vector((HOOK_R * math.cos(th), 0.0, HOOK_R * math.sin(th))))
    pts.append(Vector((xb - 0.070, s * 0.200, zb - 2.0 * HOOK_R)))
    pts = fillet_corners(pts, 0.045, steps=6, min_deg=25.0)
    return pts, hc


def add_cockpit(b):
    bm = b.bm
    cb = bar_centre()
    with b.part(T_NONE, "cockpit"):
        # quill and stem
        q0 = steer_pt(HT_TOP_Z - 0.050)
        q1 = steer_pt(STEM_Z + 0.006)
        tube(bm, q0, q1, 0.0106, ALLOY_IDX, sides=16)
        lathe_on(bm, [(0.0055, -0.001), (0.0060, 0.000), (0.0060, 0.008), (0.0050, 0.009)], 6,
                 CHROME_IDX, q1, HT_DIR)
        ext0 = steer_pt(STEM_Z) - HT_DIR * 0.004
        add_sweep(bm, [ext0, cb - XAX * 0.012], [0.0135, 0.0118], 14, ALLOY_IDX)
        lathe_on(bm, [(0.0126, -0.020), (0.0172, -0.019), (0.0172, 0.019), (0.0126, 0.020)], 20,
                 ALLOY_IDX, cb, YAX, solid=False)
        lathe_on(bm, [(0.0114, -0.028), (0.0132, -0.027), (0.0132, 0.027), (0.0114, 0.028)], 20,
                 ALLOY_IDX, cb, YAX, solid=False)
        lathe_on(bm, [(0.0035, -0.004), (0.0045, -0.003), (0.0045, 0.012), (0.0038, 0.013)], 6,
                 CHROME_IDX, cb + Vector((0.004, 0.0, -0.021)), -ZAX)
        # the bare bar between the tape's ends (the taped bar lies inside the tape)
        add_sweep(bm, [cb - YAX * 0.066, cb + YAX * 0.066], BAR_R, 12, ALLOY_IDX, ref=ZAX)
    for s in (1.0, -1.0):
        half, hc = bar_half(s)
        cut = next(i for i, p in enumerate(half) if abs(p.y) > 0.058)
        seg = [half[cut - 1].lerp(half[cut], (0.058 - abs(half[cut - 1].y))
                                  / max(1e-9, abs(half[cut].y) - abs(half[cut - 1].y)))]
        seg += half[cut:]
        end_dir = (seg[-1] - seg[-2]).normalized()
        seg[-1] = seg[-1] + end_dir * 0.002
        pts, total = resample(seg, 0.0073)
        cum = [total * k / (len(pts) - 1) for k in range(len(pts))]
        wrap = 0.022

        def rfn(i, k, cum=cum):
            u = (cum[i] / wrap + k / 8.0) % 1.0
            return 1.0 + 0.045 * u
        with b.part(T_NONE, "cockpit"):
            add_sweep(bm, pts, BAR_R + 0.0016, 8, TAPE_IDX, rfn=rfn, ref=ZAX)
            d0 = (pts[1] - pts[0]).normalized()
            lathe_on(bm, [(0.0128, -0.005), (0.0142, -0.0045), (0.0142, 0.0045), (0.0128, 0.005)],
                     16, BLACK_IDX, pts[0] + d0 * 0.001, d0, ref=ZAX, solid=False)
            lathe_on(bm, [(0.0098, -0.006), (0.0106, 0.0030), (0.0100, 0.0038), (0.0060, 0.0042)],
                     12, BLACK_IDX, pts[-1], end_dir, ref=ZAX)
        add_lever(b, s, hc)
    add_brakes(b)


def add_lever(b, s, hc):
    bm = b.bm
    th = math.radians(20.0)
    base = hc + Vector((HOOK_R * math.cos(th), 0.0, HOOK_R * math.sin(th)))
    h = Vector((math.cos(math.radians(15.0)), 0.0, math.sin(math.radians(15.0))))
    v = Vector((-h.z, 0.0, h.x))
    wkeys = pchip([(-0.014, 0.0120), (0.0, 0.0145), (0.040, 0.0133), (0.060, 0.0150),
                   (0.070, 0.0110)])
    hkeys = pchip([(-0.014, 0.0150), (0.0, 0.0185), (0.035, 0.0165), (0.060, 0.0190),
                   (0.070, 0.0125)])
    loops = []
    for k in range(9):
        t = -0.014 + 0.084 * k / 8.0
        c = base + h * t + v * 0.004
        hw, hh = wkeys(t), hkeys(t)
        loop = []
        for i in range(12):
            a = 2.0 * math.pi * i / 12.0
            yy = hw * _se(math.cos(a), 2.6)
            zz = hh * _se(math.sin(a), 2.6)
            loop.append(c + YAX * yy + v * zz)
        loops.append(loop)
    with b.part(T_NONE, "cockpit"):
        add_loft(bm, loops, GUM_IDX)
    with b.part(T_NONE, "cockpit"):
        blade = [base + h * 0.052 - v * 0.004]
        for deg in (12.0, 0.0, -14.0, -28.0, -42.0, -56.0, -66.0):
            a = math.radians(deg)
            blade.append(hc + Vector(((HOOK_R + 0.024) * math.cos(a), 0.0,
                                      (HOOK_R + 0.024) * math.sin(a))))
        add_bar(bm, blade, YAX, 0.0068, 0.0028, 0.0020, ALLOY_IDX, fillet=0.02)
    b.groups.setdefault("lever_tops", []).append(base + h * 0.030 + v * 0.024)


def caliper(b, centre, pivot, bolt_dir, host):
    """Side-pull caliper hung from ``pivot``: two arms round the tyre to
    shoes and pads a millimetre off the rim's braking faces."""
    bm = b.bm
    u = Vector((pivot.x - centre.x, 0.0, pivot.z - centre.z))
    rho_p = u.length
    u.normalize()
    t = Vector((-u.z, 0.0, u.x))

    def at(rho, y, tt=0.0):
        return Vector((centre.x, 0.0, centre.z)) + u * rho + YAX * y + t * tt
    with b.part(T_NONE, "brakes"):
        tube(bm, host, pivot + bolt_dir * 0.014, 0.0035, CHROME_IDX, sides=10)
        lathe_on(bm, [(0.0040, 0.0), (0.0058, 0.001), (0.0058, 0.0075), (0.0040, 0.0085)], 6,
                 CHROME_IDX, pivot + bolt_dir * 0.008, bolt_dir)
        for s, st in ((1.0, 0.0034), (-1.0, -0.0034)):
            pts = [at(rho_p + 0.002, -s * 0.010, st), at(rho_p + 0.001, s * 0.020, st),
                   at(rho_p - 0.012, s * 0.031, st), at(0.341, s * 0.029, st),
                   at(0.322, s * 0.0235, st), at(0.3065, s * 0.0215, st)]
            add_bar(bm, pts, t, 0.0028, 0.0055, 0.0020, ALLOY_IDX, fillet=0.012)
    with b.part(T_NONE, "brakes"):
        for s, sc in ((1.0, 1.0), (-1.0, 0.96)):
            shoe = at(0.3060, s * 0.0170)
            add_rbox(bm, 0.0035, 0.0050 * sc, 0.0015, [(0.0006, -0.022 * sc), (0.0, -0.0205 * sc),
                                                       (0.0, 0.0205 * sc), (0.0006, 0.022 * sc)],
                     shoe, frame(t, YAX), ALLOY_IDX, n_corner=1)
            pad = at(0.3060, s * 0.0132)
            add_rbox(bm, 0.0022, 0.0040 * sc, 0.0012, [(0.0005, -0.019 * sc), (0.0, -0.018 * sc),
                                                       (0.0, 0.018 * sc), (0.0005, 0.019 * sc)],
                     pad, frame(t, YAX), RUBBER_IDX, n_corner=1)
        b.groups.setdefault("cable_stops", []).append(at(rho_p - 0.0055, 0.0255, 0.0034))


def add_brakes(b):
    c = steer_pt(CROWN_Z)
    front_pivot = c + HT_FWD * 0.024
    caliper(b, AXLE_F, front_pivot, HT_FWD, c)
    top, bot = seatstay_ends(1.0)
    p = bot.lerp(top, _bridge_t(top, bot))
    bridge = Vector((p.x, 0.0, p.z))
    u = (bridge - AXLE_R).normalized()
    tdir = Vector((-u.z, 0.0, u.x))
    caliper(b, AXLE_R, bridge + tdir * 0.014, tdir, bridge)


def add_cables(b):
    bm = b.bm
    tops = b.groups.get("lever_tops", [])
    stops = b.groups.get("cable_stops", [])
    with b.part(T_NONE, "cables"):
        # front brake: the left lever over to the front caliper
        s0 = tops[0]
        e = stops[0]
        pts = bezier(s0, s0 + Vector((0.060, -0.030, 0.070)), e + Vector((0.030, 0.0, 0.100)), e,
                     18)
        add_sweep(bm, pts, 0.0025, 6, BLACK_IDX)
        # rear brake: the right lever back to a stop on the top tube, bare
        # cable along the top tube through three clips, a loop down to the caliper
        s1 = tops[1]
        tt_z = TT_Z + R_TT + 0.0022
        e1 = Vector((steer_x(TT_Z) - 0.075, 0.0, tt_z))
        e2 = Vector((ST_TT.x + 0.070, 0.0, tt_z))
        pts = bezier(s1, s1 + Vector((-0.020, 0.020, 0.090)), e1 + Vector((0.120, 0.0, 0.050)),
                     e1 + XAX * 0.006, 18)
        add_sweep(bm, pts, 0.0025, 6, BLACK_IDX)
        tube(bm, e1 + XAX * 0.004, e2 - XAX * 0.004, 0.0008, STEEL_IDX, sides=6)
        for p, dr in ((e1, 0.0), (e2, 0.0003)):
            lathe_on(bm, [(0.0030 + dr, -0.010), (0.0034 + dr, -0.009), (0.0034 + dr, 0.009),
                          (0.0030 + dr, 0.010)], 8, CHROME_IDX, p, XAX)
        for k in range(3):
            x = e1.x + (e2.x - e1.x) * (k + 1) / 4.0
            dr = 0.0002 * k
            lathe_on(bm, [(0.0124, -0.004), (0.0158 + dr, -0.0035), (0.0158 + dr, 0.0035),
                          (0.0124, 0.004)], 16, CHROME_IDX, Vector((x, 0.0, TT_Z)), XAX,
                     solid=False)
        e3 = stops[1]
        pts = bezier(e2 - XAX * 0.006, e2 + Vector((-0.110, 0.0, 0.020)),
                     e3 + Vector((0.030, 0.0, 0.080)), e3, 16)
        add_sweep(bm, pts, 0.0025, 6, BLACK_IDX)


def add_shifters(b):
    bm = b.bm
    st = 0.420
    c = BB + DT_DIR * st
    dn = -DT_UP
    with b.part(T_NONE, "shifters"):
        lathe_on(bm, [(R_DT - 0.0005, -0.007), (R_DT + 0.0022, -0.0065), (R_DT + 0.0022, 0.0065),
                      (R_DT - 0.0005, 0.007)], 20, CHROME_IDX, c, DT_DIR, solid=False)
        for s in (1.0, -1.0):
            dr = 0.0 if s > 0 else 0.0003
            lathe_on(bm, [(0.0055 + dr, s * 0.004), (0.0060 + dr, s * 0.006),
                          (0.0060 + dr, s * 0.024), (0.0050 + dr, s * 0.026)] if s > 0 else
                     [(0.0050 + dr, s * 0.026), (0.0060 + dr, s * 0.024), (0.0060 + dr, s * 0.006),
                      (0.0055 + dr, s * 0.004)], 12, CHROME_IDX, c, YAX)
            lv = (DT_DIR * 0.8 + DT_UP * 0.6).normalized()
            p0 = c + YAX * (s * 0.0205)
            add_bar(bm, [p0 - lv * (0.006 + dr), p0 + lv * (0.060 + dr)], YAX, 0.0022,
                    0.0050 - dr, 0.0015, ALLOY_IDX)
            dz = 0.0 if s > 0 else 0.0006
            lathe_on(bm, [(0.0040 + dr, -0.002 - dz), (0.0052 + dr, 0.004), (0.0048 + dr, 0.010),
                          (0.0025 + dr, 0.013 + dz)], 10, BLACK_IDX, p0 + lv * 0.056, lv)
    with b.part(T_NONE, "cables"):
        # gear cables down the down tube's underside, under the shell, and on
        rd_end = b.groups["rd_anchor"][0]
        for s, y in ((-1.0, -0.004), (1.0, 0.004)):
            start = c + YAX * (s * 0.016)
            p1 = BB + DT_DIR * (st - 0.030) + dn * (R_DT + 0.0012) + YAX * y
            p2 = BB + DT_DIR * 0.05 + dn * (R_DT + 0.0012) + YAX * y
            p3 = BB + Vector((0.0, y, -0.0212))
            if s < 0:
                cs = chainstay_path(-1.0)
                q1 = _path_at_x(cs, -0.080) + Vector((0.0, 0.0, 0.0118))
                q2 = _path_at_x(cs, -0.300) + Vector((0.0, 0.0, 0.0098))
                pts = [start, p1, p2, p3, BB + Vector((-0.030, -0.020, -0.012)), q1, q2,
                       AXLE_R + Vector((0.050, -0.064, 0.002))]
                pts = fillet_corners(pts, 0.03, steps=4, min_deg=10.0)
                add_sweep(bm, pts, 0.0008, 6, STEEL_IDX)
                h0 = AXLE_R + Vector((0.052, -0.064, 0.002))
                loop = bezier(h0, h0 + Vector((-0.050, -0.004, 0.010)),
                              rd_end + Vector((0.010, -0.002, 0.040)), rd_end, 12)
                add_sweep(bm, [h0 - Vector((0.004, 0, 0))] + loop[1:], 0.0022, 6, BLACK_IDX)
            else:
                fd = b.groups["fd_anchor"][0]
                pts = [start, p1, p2, p3, BB + Vector((0.010, -0.010, -0.018)),
                       BB + Vector((0.024, -0.024, 0.030)), fd]
                pts = fillet_corners(pts, 0.03, steps=4, min_deg=10.0)
                add_sweep(bm, pts, 0.0008, 6, STEEL_IDX)


# --------------------------------------------------------------------------
# Saddle, post, bottle, stand
# --------------------------------------------------------------------------

SADDLE_XN = -0.065
SADDLE_XR = -0.340


def add_saddle(b):
    bm = b.bm
    post_top = BB + ST_DIR * 0.700
    with b.part(T_NONE, "saddle"):
        tube(bm, BB + ST_DIR * 0.460, post_top, 0.0133, ALLOY_IDX, sides=18)
        cradle = post_top + ST_DIR * 0.012
        lathe_on(bm, [(0.0100, -0.024), (0.0112, -0.022), (0.0112, 0.022), (0.0100, 0.024)], 18,
                 ALLOY_IDX, cradle, YAX)
        lathe_on(bm, [(0.0030, -0.010), (0.0040, -0.009), (0.0040, 0.008), (0.0055, 0.009),
                      (0.0055, 0.014), (0.0045, 0.015)], 6, CHROME_IDX, cradle, -ST_DIR)
    wk = pchip([(0.0, 0.020), (0.10, 0.023), (0.40, 0.030), (0.60, 0.052), (0.78, 0.078),
                (0.90, 0.084), (0.97, 0.076), (1.0, 0.060)])
    zk = pchip([(0.0, 0.990), (0.25, 0.996), (0.55, 0.992), (0.80, 0.994), (1.0, 1.000)])
    dk = pchip([(0.0, 0.020), (0.40, 0.026), (0.80, 0.040), (1.0, 0.040)])
    loops = []
    nst = 14
    for k in range(nst):
        s = k / (nst - 1)
        x = SADDLE_XN + (SADDLE_XR - SADDLE_XN) * s
        w, zt, d = wk(s), zk(s), dk(s)
        loop = []
        for i in range(19):
            t = math.pi * i / 18.0
            loop.append(Vector((x, w * _se(math.cos(t), 2.4), (zt - d) + d * _se(math.sin(t), 2.4))))
        for yy, dz in ((-w + 0.006, 0.0012), (-0.5 * w, 0.62), (0.0, 0.72), (0.5 * w, 0.62),
                       (w - 0.006, 0.0012)):
            loop.append(Vector((x, yy, (zt - d) + (dz if dz < 0.01 else d * dz))))
        loops.append(loop)
    with b.part(T_NONE, "saddle"):
        add_loft(bm, loops, LEATHER_IDX)
    zr = post_top.z + 0.012
    with b.part(T_NONE, "saddle"):
        # nose piece, cantle plate, rails and rivets
        nose = Vector((SADDLE_XN - 0.018, 0.0, zk(0.07) - 0.018))
        add_rbox(bm, 0.012, 0.009, 0.004, [(0.001, -0.014), (0.0, -0.012), (0.0, 0.012),
                                           (0.001, 0.014)], nose, frame(XAX, YAX), CHROME_IDX)
        rear_z = zk(0.97) - dk(0.97) + 0.0045
        cant = []
        for k in range(9):
            a = math.pi * (0.15 + 0.7 * k / 8.0)
            cant.append(Vector((SADDLE_XR + 0.030 - 0.028 * math.sin(a), 0.070 * math.cos(a),
                                rear_z)))
        add_bar(bm, cant, ZAX, 0.0050, 0.0012, 0.0008, CHROME_IDX, filleted=True)
        for s in (1.0, -1.0):
            rail = [nose + Vector((0.008, s * 0.004, -0.004)),
                    Vector((SADDLE_XN - 0.030, s * 0.016, zr + 0.010)),
                    Vector((SADDLE_XN - 0.075, s * 0.022, zr)),
                    Vector((SADDLE_XR + 0.090, s * 0.022, zr)),
                    Vector((SADDLE_XR + 0.045, s * 0.040, zr + 0.008)),
                    Vector((SADDLE_XR + 0.030 - 0.028 * math.sin(math.pi * 0.5 - 0.35),
                            s * 0.070 * math.cos(math.pi * 0.5 - 0.35) * 1.0, rear_z))]
            add_sweep(bm, fillet_path(rail, 0.02, 4), 0.0035, 8, STEEL_IDX)
        for k in range(5):
            p = Vector((SADDLE_XR - 0.0006, -0.036 + 0.018 * k, zk(1.0) - 0.014))
            dh = 0.00015 * k      # each dome its own height and phase: no shared planes
            lathe_on(bm, [(0.0040, -0.0020 - dh), (0.0040, 0.0006), (0.0028, 0.0018 + dh),
                          (0.0012, 0.0024 + dh)], 8, CHROME_IDX, p, -XAX, phase=0.29 * k)
        lathe_on(bm, [(0.0045, -0.003), (0.0045, 0.0008), (0.0030, 0.0022), (0.0012, 0.0028)], 8,
                 CHROME_IDX, Vector((SADDLE_XN - 0.012, 0.0, zk(0.04) - 0.0005)), ZAX)


def add_bottle(b):
    bm = b.bm

    def at(s, off, y=0.0):
        return BB + DT_DIR * s + DT_UP * off + YAX * y
    r_bot = 0.0365
    axis_off = R_DT + 0.004 + r_bot
    base = at(0.190, axis_off)
    with b.part(T_BOTTLE, "bottle"):
        lathe_on(bm, [(0.0300, 0.000), (0.0350, 0.002), (0.0365, 0.008), (0.0365, 0.150),
                      (0.0360, 0.162), (0.0300, 0.176), (0.0230, 0.184), (0.0225, 0.188)], 20,
                 BOTTLE_IDX, base, DT_DIR)
    with b.part(T_NONE, "bottle"):
        lathe_on(bm, [(0.0205, 0.184), (0.0215, 0.186), (0.0215, 0.199), (0.0150, 0.202),
                      (0.0085, 0.203), (0.0080, 0.214), (0.0060, 0.216)], 20, BLACK_IDX, base,
                 DT_DIR)
    with b.part(T_NONE, "cage"):
        wr = 0.0022
        for sb in (0.250, 0.370):
            lathe_on(bm, [(0.0045, R_DT - 0.002), (0.0045, R_DT + 0.004)], 10, CHROME_IDX,
                     at(sb, 0.0), DT_UP)
        spine_off = R_DT + 0.0025
        # a crossbar at each boss joins the two spines; the bolt through it
        # holds the cage to the tube
        for sb, ph in ((0.250, 0.0), (0.370, math.pi / 8.0)):
            add_sweep(bm, [at(sb, spine_off, -0.0135), at(sb, spine_off, 0.0135)], wr, 8,
                      CHROME_IDX, phase=ph)
            lathe_on(bm, [(0.0030, 0.0010), (0.0042, 0.0012), (0.0042, 0.0030), (0.0026, 0.0040)],
                     12, CHROME_IDX, at(sb, spine_off), DT_UP)
        for y, ph, e in ((0.012, 0.0, 0.0), (-0.012, math.pi / 8.0, 0.0015)):
            pts = [at(0.199 + e, spine_off + 0.0015, y), at(0.250, spine_off, y),
                   at(0.370, spine_off, y), at(0.392 - e, spine_off + 0.0015, y)]
            add_sweep(bm, pts, wr, 8, CHROME_IDX, phase=ph)
        hook = [at(0.199, spine_off + 0.0015, 0.012), at(0.186, R_DT + 0.012, 0.011),
                at(0.1845, axis_off, 0.0), at(0.186, R_DT + 0.012, -0.011),
                at(0.199, spine_off + 0.0015, -0.012)]
        add_sweep(bm, fillet_path(hook, 0.012, 4), wr, 8, CHROME_IDX)
        rh = r_bot + wr - 0.0006
        for sh in (0.272, 0.362):
            ctr = at(sh, axis_off)
            pts = [at(sh, spine_off, 0.012)]
            for k in range(17):
                a = math.radians(32.0 + (360.0 - 64.0) * k / 16.0)
                pts.append(ctr - DT_UP * (rh * math.cos(a)) + YAX * (rh * math.sin(a)))
            pts.append(at(sh, spine_off, -0.012))
            add_sweep(bm, fillet_corners(pts, 0.008, steps=3, min_deg=30.0), wr, 8, CHROME_IDX)


def add_stand_mount(b):
    bm = b.bm
    with b.part(T_NONE, "stand"):
        x = STAND_PIVOT[0]
        cs = chainstay_path(1.0)
        q = _path_at_x(cs, x)
        add_rbox(bm, 0.020, 0.010, 0.004, [(0.0015, -0.036), (0.0, -0.034), (0.0, 0.034),
                                           (0.0015, 0.036)],
                 Vector((x, 0.0, q.z - 0.0145)), frame(YAX, XAX), ALLOY_IDX)
        add_rbox(bm, 0.016, 0.0025, 0.0015, [(0.0006, -0.033), (0.0, -0.032), (0.0, 0.032),
                                             (0.0006, 0.033)],
                 Vector((x, 0.0, q.z + 0.0105)), frame(YAX, XAX), BLACK_IDX)
        lathe_on(bm, [(0.0030, -0.030), (0.0030, 0.016), (0.0060, 0.017), (0.0060, 0.022),
                      (0.0045, 0.023)], 6, CHROME_IDX, Vector((x, 0.0, q.z)), ZAX)
        lathe_on(bm, [(0.0080, -0.012), (0.0090, -0.010), (0.0090, 0.010), (0.0080, 0.012)], 14,
                 ALLOY_IDX, Vector(STAND_PIVOT), XAX)


def add_stand_leg(b, pivot, ground, tuck):
    """Built after the lean, in world space: the leg from the pivot to a
    rubber foot whose sole stands on the ground plane the tyres touch."""
    bm = b.bm
    foot = Vector((FOOT_X, FOOT_Y_TUCKED if tuck else FOOT_Y, ground))
    with b.part(T_NONE, "stand"):
        add_sweep(bm, [pivot, foot + ZAX * 0.010], 0.0068, 12, ALLOY_IDX)
    with b.part(T_FOOT, "stand"):
        add_lathe(bm, [(0.0125, 0.0), (0.0135, 0.003), (0.0130, 0.012), (0.0085, 0.019)], 16,
                  RUBBER_IDX, center=foot, solid=True)


# --------------------------------------------------------------------------
# The bicycle
# --------------------------------------------------------------------------

def build_bicycle_mesh(name, bevel_offset, bevel_segments, float_tyre=False, slip_wheel=False,
                       short_spoke=False, dish_wheel=False, steep_head=False, bunch_spokes=False,
                       lift_chain=False, shift_rollers=False, tuck_stand=False, pop_bottle=False):
    bm = bmesh.new()
    try:
        b = Build(bm)
        add_frame(b, steep_head)
        add_wheel(b, AXLE_F, True, short_spoke=short_spoke, bunch=bunch_spokes)
        add_wheel(b, AXLE_R, False)
        add_drivetrain(b, lift_chain, shift_rollers)
        add_cockpit(b)
        add_cables(b)
        add_shifters(b)
        add_saddle(b)
        add_bottle(b)
        add_stand_mount(b)

        # lean the bike onto its stand: about the line through both contacts
        lean = Matrix.Rotation(-math.radians(LEAN_DEG), 3, "X")
        for v in bm.verts:
            v.co = lean @ v.co
        tyres = b.groups["wheel_f_tyre"] + b.groups["wheel_r_tyre"]
        ground = min(v.co.z for v in tyres)
        add_stand_leg(b, lean @ Vector(STAND_PIVOT), ground, tuck_stand)

        # falsifiers that move one finished assembly, in world space
        if float_tyre:
            for v in b.groups["wheel_r_tyre"]:
                v.co.z += FLOAT_TYRE
        if slip_wheel:
            for v in set(b.groups["wheel_f"]):
                v.co.x += SLIP_WHEEL
        if dish_wheel:
            moved = set(b.groups["wheel_r_tyre"]) | set(b.groups["wheel_r_rim"])
            for v in moved:
                v.co.y -= DISH_WHEEL
            _dish_spokes(b)
        if pop_bottle:
            nrm = lean @ DT_UP
            for v in set(b.groups["bottle"]):
                v.co += nrm * POP_BOTTLE

        if bevel_offset > 0.0:
            for mat_idx in (CHROME_IDX, ALLOY_IDX):
                bm.edges.index_update()
                edges = sorted(
                    {e for v in b.bevel if v.is_valid for e in v.link_edges
                     if len(e.link_faces) == 2
                     and all(f.material_index == mat_idx for f in e.link_faces)
                     and e.calc_face_angle() > math.radians(60.0)},
                    key=lambda e: e.index,
                )
                if edges:
                    bmesh.ops.bevel(bm, geom=edges, offset=bevel_offset,
                                    segments=bevel_segments, profile=0.5, affect="EDGES",
                                    clamp_overlap=True, material=mat_idx)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-7)
        triangulate_ngons(bm)
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z -= zmin
            if v.co.z < 0.0:
                v.co.z = 0.0

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(50.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def _dish_spokes(b):
    """--dish-wheel: the rear rim and tyre are shifted; each rear spoke's
    rim-end ring (the half of its vertices farther from the hub) follows."""
    c = Vector(Matrix.Rotation(-math.radians(LEAN_DEG), 3, "X") @ AXLE_R)
    verts = b.groups["wheel_r_spoke_rim"]
    # each spoke is SPOKE_SIDES vertices at each end, built consecutively
    n = 2 * SPOKE_SIDES
    for k in range(0, len(verts), n):
        spoke = verts[k:k + n]
        far = sorted(spoke, key=lambda v: (v.co - c).length)[SPOKE_SIDES:]
        for v in far:
            v.co.y -= DISH_WHEEL


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def principled(name, color, metallic, roughness, roughness_var=0.0, mottle=0.0,
               noise_scale=14.0, coat=0.0, stretch=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if coat > 0.0 and "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.06
    if roughness_var > 0.0 or mottle > 0.0:
        coord = nt.nodes.new("ShaderNodeTexCoord")
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = noise_scale
        noise.inputs["Detail"].default_value = 6.0
        if stretch:
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = stretch
            nt.links.new(coord.outputs["Object"], mp.inputs["Vector"])
            nt.links.new(mp.outputs["Vector"], noise.inputs["Vector"])
        else:
            nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
        if roughness_var > 0.0:
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            lo = max(0.03, roughness - roughness_var)
            hi = min(0.95, roughness + roughness_var)
            ramp.color_ramp.elements[0].position = 0.30
            ramp.color_ramp.elements[0].color = (lo, lo, lo, 1.0)
            ramp.color_ramp.elements[1].position = 0.70
            ramp.color_ramp.elements[1].color = (hi, hi, hi, 1.0)
            nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
        if mottle > 0.0:
            cramp = nt.nodes.new("ShaderNodeValToRGB")
            dark = tuple(c * (1.0 - mottle) for c in color[:3]) + (1.0,)
            cramp.color_ramp.elements[0].position = 0.35
            cramp.color_ramp.elements[0].color = dark
            cramp.color_ramp.elements[1].position = 0.75
            cramp.color_ramp.elements[1].color = color
            nt.links.new(noise.outputs["Fac"], cramp.inputs["Fac"])
            nt.links.new(cramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def metal(name, color, roughness, env, stops, interp="EASE", roughness_var=0.04,
          noise_scale=40.0, stretch=None):
    """Metal with a studio carried in the material (copied from
    showcase/espresso-machine). On a dark stage a metal mirrors the dark
    stage and reads as grey plastic; here the world-space reflection vector
    looks up a soft studio — a bright horizon band, a dim ceiling, the floor
    dark only straight down, the key's side brighter — added as emission,
    so chrome reads as chrome in the hero and on the asset sheet alike."""
    mat = principled(name, color, 1.0, roughness, roughness_var=roughness_var,
                     noise_scale=noise_scale, stretch=stretch)
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
    cr.interpolation = interp
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
    side = nt.nodes.new("ShaderNodeMath")
    side.operation = "MULTIPLY"
    nt.links.new(mx.outputs["Result"], side.inputs[0])
    side.inputs[1].default_value = env
    tint = nt.nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1.0
    tint.inputs[2].default_value = color
    nt.links.new(ramp.outputs["Color"], tint.inputs[1])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tint.outputs[0], em.inputs["Color"])
    nt.links.new(side.outputs["Value"], em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(bsdf.outputs["BSDF"], add.inputs[0])
    nt.links.new(em.outputs["Emission"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
    return mat


def bicycle_materials():
    """Shared by the check and the render, in slot order."""
    paint = principled("FramePaint", (0.43, 0.035, 0.030, 1.0), 0.0, 0.24, roughness_var=0.04,
                       noise_scale=40.0, coat=0.8)
    chrome = metal("Chrome", (0.92, 0.92, 0.94, 1.0), 0.10, 0.95,
                   [(0.0, 0.01), (0.30, 0.02), (0.38, 0.90), (0.47, 1.0), (0.53, 0.06),
                    (0.66, 0.08), (0.74, 0.75), (0.88, 0.60), (1.0, 0.20)], "LINEAR",
                   roughness_var=0.03, noise_scale=70.0)
    alloy = metal("PolishedAlloy", (0.80, 0.80, 0.81, 1.0), 0.24, 0.40,
                  [(0.0, 0.03), (0.18, 0.05), (0.30, 0.20), (0.40, 0.60), (0.48, 1.0),
                   (0.60, 0.40), (0.80, 0.25), (1.0, 0.18)], roughness_var=0.06, noise_scale=60.0)
    steel = metal("SpokeSteel", (0.62, 0.62, 0.64, 1.0), 0.30, 0.30,
                  [(0.0, 0.03), (0.30, 0.10), (0.42, 0.55), (0.50, 0.90), (0.62, 0.30),
                   (1.0, 0.15)], roughness_var=0.06, noise_scale=90.0)
    rubber = principled("FileTread", (0.028, 0.028, 0.030, 1.0), 0.0, 0.62, roughness_var=0.12,
                        noise_scale=420.0)
    gum = principled("GumWall", (0.50, 0.30, 0.13, 1.0), 0.0, 0.55, roughness_var=0.08,
                     mottle=0.14, noise_scale=180.0)
    leather = principled("SaddleLeather", (0.36, 0.16, 0.055, 1.0), 0.0, 0.36,
                         roughness_var=0.10, mottle=0.28, noise_scale=90.0, coat=0.35)
    tape = principled("CottonTape", (0.72, 0.68, 0.58, 1.0), 0.0, 0.85, roughness_var=0.06,
                      mottle=0.12, noise_scale=300.0)
    black = principled("BlackParts", (0.022, 0.022, 0.024, 1.0), 0.0, 0.40, roughness_var=0.08,
                       noise_scale=90.0, coat=0.2)
    bottle = principled("BottlePlastic", (0.72, 0.72, 0.68, 1.0), 0.0, 0.32, roughness_var=0.06,
                        noise_scale=60.0, coat=0.3)
    return paint, chrome, alloy, steel, rubber, gum, leather, tape, black, bottle


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
                report.append((si, sj, tuple(round(x, 4) for x in ci), i, j))
    return hits


class Shell:
    def __init__(self, me, idx, verts, polys, tags):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.mean = sum(pts, Vector()) / len(pts)
        mats, tg = {}, {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
            t = tags[p.index]
            tg[t] = tg.get(t, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        self.tag = max(tg, key=tg.get) if tg else T_NONE
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)


def pca(pts):
    """(mean, eigenvalues ascending, eigenvectors as columns)."""
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    w, vecs = np.linalg.eigh(q.T @ q / len(p))
    return Vector(c), w, vecs


def classify(me):
    groups = shells(me)
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(p)
    tags = [0] * len(me.polygons)
    attr = me.attributes.get("part")
    if attr is not None:
        attr.data.foreach_get("value", tags)
    parts = [Shell(me, i, g, polys[i], tags) for i, g in enumerate(groups)]
    by = {}
    for s in parts:
        by.setdefault(s.tag, []).append(s)
    return {"all": parts, "groups": groups, "by": by}


def tagged(cls, tag):
    return cls["by"].get(tag, [])


def line_dist(p, c, a):
    d = p - c
    return (d - a * d.dot(a)).length


def axis_of(s, which):
    c, _w, vecs = pca(s.pts)
    return c, Vector(vecs[:, which]).normalized()


def contact(s):
    pts = [p for p in s.pts if p.z < s.lo.z + CONTACT_BAND]
    return Vector((sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts), s.lo.z))


def coax_audit(cls):
    """Each hub's axle line (principal PCA axis) against both dropout eyes'
    centres."""
    worst, counts = 0.0, []
    for hub_t, eye_t in ((T_HUB_F, T_EYE_F), (T_HUB_R, T_EYE_R)):
        hubs, eyes = tagged(cls, hub_t), tagged(cls, eye_t)
        counts.append((len(hubs), len(eyes)))
        if len(hubs) != 1 or len(eyes) != 2:
            return 9.0, counts
        c, a = axis_of(hubs[0], 2)
        for e in eyes:
            worst = max(worst, line_dist(e.mean, c, a))
    return worst, counts


def spoke_ends(s, c):
    """(hub end, rim end): centroids of a spoke's near and far rings."""
    d = sorted(s.pts, key=lambda p: (p - c).length)
    half = len(d) // 2
    near = sum(d[:half], Vector()) / half
    far = sum(d[half:], Vector()) / (len(d) - half)
    return near, far


def spoke_audit(cls):
    """Hub end buried in its flange (read off the hub's own radius at that
    station) and rim end inside a nipple, on its axis and past its ends."""
    res = {"flange": [9.0, -9.0], "nip_off": 0.0, "nip_depth": 9.0, "count": []}
    for hub_t, sp_t, nip_t in ((T_HUB_F, T_SPOKE_F, T_NIP_F), (T_HUB_R, T_SPOKE_R, T_NIP_R)):
        hubs, spokes, nips = tagged(cls, hub_t), tagged(cls, sp_t), tagged(cls, nip_t)
        res["count"].append((len(spokes), len(nips)))
        if len(hubs) != 1 or not spokes or not nips:
            res["flange"] = [-9.0, 9.0]
            return res
        hc, ha = axis_of(hubs[0], 2)
        hub_ax = [(p - hc).dot(ha) for p in hubs[0].pts]
        hub_rad = [line_dist(p, hc, ha) for p in hubs[0].pts]
        nip_info = []
        for n in nips:
            nc, na = axis_of(n, 2)
            if (nc - hc).dot(na) < 0.0:
                na = -na
            ext = [(p - nc).dot(na) for p in n.pts]
            nip_info.append((nc, na, min(ext), max(ext)))
        for s in spokes:
            near, far = spoke_ends(s, hc)
            ax = (near - hc).dot(ha)
            rho = line_dist(near, hc, ha)
            r_here = max((r for r, a in zip(hub_rad, hub_ax) if abs(a - ax) <= 0.0012),
                         default=0.0)
            depth = r_here - rho
            res["flange"][0] = min(res["flange"][0], depth)
            res["flange"][1] = max(res["flange"][1], depth)
            nc, na, e0, e1 = min(nip_info, key=lambda q: (q[0] - far).length)
            off = line_dist(far, nc, na)
            t = (far - nc).dot(na)
            res["nip_off"] = max(res["nip_off"], off)
            res["nip_depth"] = min(res["nip_depth"], t - e0, e1 - t)
    return res


def frame_plane(cls):
    pts = [p for t in (T_FRAME, T_HEADTUBE, T_SEATTUBE) for s in tagged(cls, t) for p in s.pts]
    c, _w, vecs = pca(pts)
    return c, Vector(vecs[:, 0]).normalized()


def plane_audit(cls):
    """Each rim's centre against the frame's centre plane, and its axis
    against the frame's normal; the seat tube's length; the wheelbase."""
    cf, nf = frame_plane(cls)
    res = {"offset": [], "angle": [], "st_len": 0.0, "wheelbase": 0.0}
    for rim_t in (T_RIM_F, T_RIM_R):
        rims = tagged(cls, rim_t)
        if len(rims) != 1:
            res["offset"].append(9.0)
            res["angle"].append(90.0)
            continue
        c, n = axis_of(rims[0], 0)
        res["offset"].append(abs((c - cf).dot(nf)))
        res["angle"].append(math.degrees(math.acos(min(1.0, abs(n.dot(nf))))))
    sts = tagged(cls, T_SEATTUBE)
    if len(sts) == 1:
        c, a = axis_of(sts[0], 2)
        ext = [(p - c).dot(a) for p in sts[0].pts]
        # the tube's cap ends are square to its axis: its axial extent is its length
        res["st_len"] = max(ext) - min(ext)
    tf, tr = tagged(cls, T_TYRE_F), tagged(cls, T_TYRE_R)
    if len(tf) == 1 and len(tr) == 1:
        a, b = tf[0].mean, tr[0].mean
        res["wheelbase"] = math.hypot(a.x - b.x, a.y - b.y)
    return res


def trail_audit(cls):
    res = {"trail": 9.0, "offset": 9.0, "rake": 0.0}
    hts, tf = tagged(cls, T_HEADTUBE), tagged(cls, T_TYRE_F)
    if len(hts) != 1 or len(tf) != 1:
        return res
    c, a = axis_of(hts[0], 2)
    if a.z < 0.0:
        a = -a
    hit = c - a * (c.z / a.z)
    cp = contact(tf[0])
    res["trail"] = hit.x - cp.x
    res["offset"] = abs(hit.y - cp.y)
    res["rake"] = math.degrees(math.acos(min(1.0, a.z)))
    return res


def _ang(v, e1, e2):
    return math.atan2(v.dot(e2), v.dot(e1))


def _wrap(a):
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def lacing_audit(cls):
    """Rim-end angles equally pitched; hub end three crosses round from its
    rim end; 18 spokes from each flange."""
    res = {"count": [], "sides": [], "pitch": 0.0, "cross": [99.0, -99.0]}
    for rim_t, sp_t in ((T_RIM_F, T_SPOKE_F), (T_RIM_R, T_SPOKE_R)):
        rims, spokes = tagged(cls, rim_t), tagged(cls, sp_t)
        res["count"].append(len(spokes))
        if len(rims) != 1 or not spokes:
            res["pitch"] = 99.0
            return res
        c, n = axis_of(rims[0], 0)
        e1 = (XAX - n * XAX.dot(n)).normalized()
        e2 = n.cross(e1)
        thetas, plus = [], 0
        for s in spokes:
            near, far = spoke_ends(s, c)
            th = _ang(far - c, e1, e2)
            ph = _ang(near - c, e1, e2)
            thetas.append(th)
            cr = abs(math.degrees(_wrap(ph - th)))
            res["cross"][0] = min(res["cross"][0], cr)
            res["cross"][1] = max(res["cross"][1], cr)
            if (near - c).dot(n) > 0.0:
                plus += 1
        res["sides"].append((plus, len(spokes) - plus))
        ts = sorted(thetas)
        want = 360.0 / len(ts)
        for a, b2 in zip(ts, ts[1:] + [ts[0] + 2.0 * math.pi]):
            res["pitch"] = max(res["pitch"], abs(math.degrees(b2 - a) - want))
    return res


def sprocket_frame(s):
    c, _w, vecs = pca(s.pts)
    n = Vector(vecs[:, 0]).normalized()
    rads = [line_dist(p, c, n) for p in s.pts]
    r_max, r_min = max(rads), min(rads)
    r_root = min(r for r in rads if r > 0.5 * (r_max + r_min))
    return c, n, r_root


def _overlap(a, b):
    if (a.lo.x > b.hi.x or b.lo.x > a.hi.x or a.lo.y > b.hi.y or b.lo.y > a.hi.y
            or a.lo.z > b.hi.z or b.lo.z > a.hi.z):
        return False
    return bool(a.tree.overlap(b.tree))


def chain_audit(cls):
    """Rollers that engage the big ring and the driven cog, seated between
    root and pitch; every roller and the driven cog in the ring's plane."""
    rollers = tagged(cls, T_ROLLER)
    res = {"rollers": len(rollers), "ring": 0, "cog": 0, "seat": [9.0, -9.0],
           "line": 9.0, "cog_line": 9.0}
    rings, cogs = tagged(cls, T_RING), tagged(cls, T_COG)
    if not rollers or not rings or not cogs:
        return res

    def engaged(sp):
        # the roller's body straddles the sprocket's plane and cuts its teeth
        # (a pin tip grazing the next cog is not engagement)
        c, n, _r = sprocket_frame(sp)
        return [r for r in rollers
                if abs((r.mean - c).dot(n)) <= ROLLER_H and _overlap(r, sp)]
    ring = max(rings, key=lambda s: len(engaged(s)))
    cog = max(cogs, key=lambda s: len(engaged(s)))
    for sp, key in ((ring, "ring"), (cog, "cog")):
        c, n, r_root = sprocket_frame(sp)
        eng = engaged(sp)
        res[key] = len(eng)
        for r in eng:
            d = line_dist(r.mean, c, n) - r_root
            res["seat"][0] = min(res["seat"][0], d)
            res["seat"][1] = max(res["seat"][1], d)
    c, n, _r = sprocket_frame(ring)
    res["line"] = max(abs((r.mean - c).dot(n)) for r in rollers)
    cc, _n, _r = sprocket_frame(cog)
    res["cog_line"] = abs((cc - c).dot(n))
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


def hull2d(pts):
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


def stance_audit(cls):
    total = 0.0
    mom = Vector()
    for s in cls["all"]:
        if s.mat is None:
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * DENSITY[s.mat]
        total += m
        mom += m * cen
    com = mom / total
    sups = tagged(cls, T_TYRE_F) + tagged(cls, T_TYRE_R) + tagged(cls, T_FOOT)
    contact_pts = [(p.x, p.y) for sk in sups for p in sk.pts if p.z < sk.lo.z + CONTACT_BAND]
    margin = -1.0
    if len(contact_pts) >= 3:
        hull = hull2d(contact_pts)
        margin = 9.0
        for k in range(len(hull)):
            a, b = hull[k], hull[(k + 1) % len(hull)]
            ex, ey = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ex, ey)
            margin = min(margin, (ex * (com.y - a[1]) - ey * (com.x - a[0])) / ln)
    return {"mass": total, "com": com, "margin": margin}


def connected_components(cls):
    parts = cls["all"]
    n = len(parts)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(n), key=lambda i: parts[i].lo.x)
    for ii, i in enumerate(order):
        a = parts[i]
        for j in order[ii + 1:]:
            b = parts[j]
            if b.lo.x > a.hi.x:
                break
            if find(i) == find(j):
                continue
            if _overlap(a, b):
                parent[find(i)] = find(j)
    roots = {find(i) for i in range(n)}
    sizes = {}
    for i in range(n):
        sizes[find(i)] = sizes.get(find(i), 0) + 1
    return len(roots), sorted(sizes.values())


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
    img = bpy.data.images.new("BicycleNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = ALLOY_IDX
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


FLAG_NAMES = ("float_tyre", "slip_wheel", "short_spoke", "dish_wheel", "steep_head",
              "bunch_spokes", "lift_chain", "shift_rollers", "tuck_stand", "pop_bottle")


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_bicycle_mesh("BicycleLow", bevel_offset=0.0005, bevel_segments=1, **flags)
    high = build_bicycle_mesh("BicycleHigh", bevel_offset=0.0005, bevel_segments=3, **flags)
    mats = bicycle_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the alloy: cranks, arms, levers and cages are where the
    # high mesh's rounder chamfer differs from the low.
    target = mats[ALLOY_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("bicycle mesh did not build", 3),) + none3

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
    zrep = []
    zf = zfight_pairs(low.data, cls["groups"], zrep)
    tyre_z = [s.lo.z for s in tagged(cls, T_TYRE_F) + tagged(cls, T_TYRE_R)]
    foot_z = [s.lo.z for s in tagged(cls, T_FOOT)]
    coax, coax_counts = coax_audit(cls)
    spk = spoke_audit(cls)
    pl = plane_audit(cls)
    tr = trail_audit(cls)
    lace = lacing_audit(cls)
    ch = chain_audit(cls)
    stance = stance_audit(cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("bicycle has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BicycleLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BicycleLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(low, "BicycleCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_road_bicycle_{os.getpid()}.glb")
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
          f"outer={OUTER_SIZE} zmin={bb[2]:.4f} min=({bb[0]:.4f},{bb[1]:.4f})")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    if zrep:
        print(f"measured zfight_first_pair at {zrep[0][2]}")
    print(f"measured shells={len(cls['all'])} tyre_zmin={[round(z, 5) for z in tyre_z]} "
          f"foot_zmin={[round(z, 5) for z in foot_z]}")
    print(f"measured coax={coax:.6f} counts={coax_counts}")
    print(f"measured spokes={spk['count']} flange_seat=[{spk['flange'][0]:.5f},"
          f"{spk['flange'][1]:.5f}] nipple_off={spk['nip_off']:.6f} "
          f"nipple_depth={spk['nip_depth']:.5f}")
    print(f"measured plane_offset={[round(x, 6) for x in pl['offset']]} "
          f"plane_angle={[round(x, 4) for x in pl['angle']]} st_len={pl['st_len']:.5f} "
          f"wheelbase={pl['wheelbase']:.5f}")
    print(f"measured rake={tr['rake']:.3f} trail={tr['trail']:.5f} offset={tr['offset']:.6f}")
    print(f"measured lacing count={lace['count']} sides={lace['sides']} "
          f"pitch_dev={lace['pitch']:.4f} cross=[{lace['cross'][0]:.3f},{lace['cross'][1]:.3f}]")
    print(f"measured chain rollers={ch['rollers']} ring_engaged={ch['ring']} "
          f"cog_engaged={ch['cog']} seat=[{ch['seat'][0]:.5f},{ch['seat'][1]:.5f}] "
          f"line={ch['line']:.6f} cog_line={ch['cog_line']:.6f}")
    print(f"measured mass={stance['mass']:.3f}kg com=({stance['com'].x:.4f},"
          f"{stance['com'].y:.4f},{stance['com'].z:.4f}) margin={stance['margin']:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[:6]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    labels = ("paint", "chrome", "alloy", "steel", "tread rubber", "gum", "leather", "tape",
              "black", "bottle")
    for idx, (floor, label) in enumerate(zip(FACE_FLOORS, labels)):
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{label} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + none3
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
    if bb[2] > ZMIN_EPS:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none3
    if len(tyre_z) != 2 or len(foot_z) != 1 or max(tyre_z + foot_z) > ZMIN_EPS:
        return (fail(f"supports: {len(tyre_z)} tyres (want 2), {len(foot_z)} stand foot (want 1), "
                     f"zmin per tyre {[round(z, 5) for z in tyre_z]}, foot "
                     f"{[round(z, 5) for z in foot_z]} (each within {ZMIN_EPS} of 0)", 16),) + none3
    if coax > COAX_TOL:
        return (fail(f"hub axis {coax:.5f} m off a dropout eye's centre (tol {COAX_TOL}); "
                     f"hubs/eyes {coax_counts}", 17),) + none3
    if (spk["count"] != [(SPOKES, SPOKES), (SPOKES, SPOKES)]
            or not (FLANGE_SEAT_MIN <= spk["flange"][0] and spk["flange"][1] <= FLANGE_SEAT_MAX)
            or spk["nip_off"] > NIPPLE_AXIS_TOL or spk["nip_depth"] < NIPPLE_DEPTH_MIN):
        return (fail(f"spoke seats: counts {spk['count']}, flange depth "
                     f"[{spk['flange'][0]:.5f}, {spk['flange'][1]:.5f}] not in "
                     f"[{FLANGE_SEAT_MIN}, {FLANGE_SEAT_MAX}], nipple axis off "
                     f"{spk['nip_off']:.5f} (tol {NIPPLE_AXIS_TOL}), end inside nipple by "
                     f"{spk['nip_depth']:.5f} (min {NIPPLE_DEPTH_MIN})", 18),) + none3
    if (max(pl["offset"]) > PLANE_TOL or max(pl["angle"]) > PLANE_ANGLE_MAX_DEG
            or abs(pl["st_len"] - SEAT_TUBE_LEN) > SIZE_TOL
            or abs(pl["wheelbase"] - WHEELBASE) > SIZE_TOL + 0.001):
        return (fail(f"wheels off the frame's plane {[round(x, 5) for x in pl['offset']]} m "
                     f"(tol {PLANE_TOL}), tilted {[round(x, 3) for x in pl['angle']]} deg "
                     f"(max {PLANE_ANGLE_MAX_DEG}), or size off: seat tube {pl['st_len']:.4f}, "
                     f"wheelbase {pl['wheelbase']:.4f}", 19),) + none3
    if not (TRAIL_MIN <= tr["trail"] <= TRAIL_MAX) or tr["offset"] > TRAIL_Y_TOL:
        return (fail(f"steering: trail {tr['trail']:.5f} m not in [{TRAIL_MIN}, {TRAIL_MAX}] or "
                     f"axis {tr['offset']:.5f} m off the contact (tol {TRAIL_Y_TOL}); "
                     f"rake {tr['rake']:.3f} deg", 20),) + none3
    if (lace["count"] != [SPOKES, SPOKES]
            or lace["sides"] != [(SPOKES // 2, SPOKES // 2)] * 2
            or lace["pitch"] > PITCH_TOL_DEG
            or not (CROSS_MIN_DEG <= lace["cross"][0] and lace["cross"][1] <= CROSS_MAX_DEG)):
        return (fail(f"lacing: counts {lace['count']}, flange split {lace['sides']}, pitch off by "
                     f"{lace['pitch']:.3f} deg (tol {PITCH_TOL_DEG}), cross angle "
                     f"[{lace['cross'][0]:.2f}, {lace['cross'][1]:.2f}] not in "
                     f"[{CROSS_MIN_DEG}, {CROSS_MAX_DEG}]", 21),) + none3
    if (ch["ring"] < RING_ENGAGED_MIN or ch["cog"] < COG_ENGAGED_MIN
            or not (SEAT_MIN <= ch["seat"][0] and ch["seat"][1] <= SEAT_MAX)):
        return (fail(f"chain seat: {ch['ring']} rollers on the ring (min {RING_ENGAGED_MIN}), "
                     f"{ch['cog']} on the cog (min {COG_ENGAGED_MIN}), seated "
                     f"[{ch['seat'][0]:.5f}, {ch['seat'][1]:.5f}] above the root, not in "
                     f"[{SEAT_MIN}, {SEAT_MAX}]", 22),) + none3
    if ch["line"] > CHAINLINE_TOL or ch["cog_line"] > CHAINLINE_TOL:
        return (fail(f"chain line: a roller {ch['line']:.5f} m off the ring's plane, the cog "
                     f"{ch['cog_line']:.5f} m (tol {CHAINLINE_TOL})", 23),) + none3
    if stance["margin"] < STANCE_MARGIN:
        return (fail(f"stance: mass centre {stance['margin']:.4f} m inside the support "
                     f"triangle < {STANCE_MARGIN}", 24),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes[:6]}", 25),) + none3
    return 0, low, target, tex


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
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
    wall.location = (0.0, centre.y + WALL_Y, 0.0)
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

    # The house rig scaled to a 1.7 m bicycle: warm key upper left, cool
    # fill low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-2.1, -2.5, 2.4), 38.0, 1.4, (1.0, 0.92, 0.82), spread=30.0)
    light("Fill", (2.6, -1.8, 0.6), 7.0, 3.0, (0.72, 0.82, 1.0))
    light("Rim", (-1.0, 1.7, 1.6), 60.0, 1.2, (0.62, 0.78, 1.0))
    light("Wedge", (2.3, 2.3, 1.0), 150.0, 1.8, (1.0, 0.62, 0.30),
          target=(centre.x + 2.4, centre.y + WALL_Y, 0.55))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.55, -0.83, 0.0)).normalized()
    cam.location = centre + view * 3.30 + Vector((0.0, 0.0, 0.62))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.02))
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
    # Standard, not AgX: AgX washes the red enamel and the tan walls grey
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


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--float-tyre", action="store_true")
    p.add_argument("--slip-wheel", action="store_true")
    p.add_argument("--short-spoke", action="store_true")
    p.add_argument("--dish-wheel", action="store_true")
    p.add_argument("--steep-head", action="store_true")
    p.add_argument("--bunch-spokes", action="store_true")
    p.add_argument("--lift-chain", action="store_true")
    p.add_argument("--shift-rollers", action="store_true")
    p.add_argument("--tuck-stand", action="store_true")
    p.add_argument("--pop-bottle", action="store_true")
    args = p.parse_args(argv)

    flags = {name: getattr(args, name) for name in FLAG_NAMES}
    code, low, target, tex = check(args.skip_decimate, lift_z=args.lift_z,
                                   stray_vert=args.stray_vert, **flags)
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("road-bicycle OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
