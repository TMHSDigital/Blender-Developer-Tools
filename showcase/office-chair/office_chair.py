"""Game-ready ergonomic task chair on a chair mat — a showcase piece, not an example.

Asserts budget conformance of a procedural task chair and its desk-corner
floor vignette after composing shipped pipeline pieces: bmesh construction,
UVs, fourteen materials, high-to-low normal bake, LOD chain, convex
collider, Unity glTF export.

The chair stands on a polished aluminium five-star base: five lofted spokes,
each a crowned section with two channels and a centre rib on its underside,
running from a moulded hub out to a socket boss. A hooded twin-wheel caster
hangs from every boss on a plumb swivel stem, each swivelled its own way,
and every wheel presses into a smoked polycarbonate chair mat with a
bevelled edge and a lip that runs forward under a desk. A chrome gas-lift
column rises out of the hub through a two-stage telescoping cover into the
socket of a synchro-tilt mechanism: tilt-spring housing, a knurled tension
knob and two lever paddles. The seat is a moulded graphite shell cupping a
two-tone upholstered cushion: a woven muted-teal centre panel sculpted
with a rear dish and two thigh channels that rolls over a waterfall front,
mid-grey knit side panels, a piped welt in the seam groove between them and another on
the top edge. An aluminium spine sweeps from the mechanism up behind a
reclined mesh back: an elastomeric weave stretched over a graphite frame
that thickens toward its foot, a cross bar and hub plate behind it, and an
S-curved lumbar pad on straps whose ends clamp the frame's sides as
sliders. A headrest of the same mesh in its own frame rides on an
aluminium stem. Two 4D armrests rise from aluminium brackets under the
shell: a telescoping post cover, a post with a height button and a pivot
button, a pad plate and a soft pad. A snake plant in a speckled stone pot
stands on the floor beside the mat.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--float-caster`` every wheel pressed into
the mat, ``--curl-mat`` the mat flat on the floor, ``--skew-spoke`` the
five-star geometry, ``--offset-column`` the gas lift coaxial with hub and
socket, ``--uneven-arms`` mirrored level armrests, ``--loose-wheel`` one
connected chair, ``--float-lumbar`` the lumbar sliders clamped on the back
frame, ``--float-leaves`` every leaf rooted in the pot's soil.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts are
not byte-identical across Blender versions — the LOD gate is a ratio band,
not an exact count.

    blender --background --python office_chair.py --
    blender --background --python office_chair.py -- --skip-decimate
    blender --background --python office_chair.py -- --output chair.png
"""
import argparse
import math
import os
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

X_AX = Vector((1.0, 0.0, 0.0))
Y_AX = Vector((0.0, 1.0, 0.0))
Z_AX = Vector((0.0, 0.0, 1.0))

# --- Five-star base (front of the chair is -Y) ----------------------------
SPOKES = 5
SPOKE0_DEG = 90.0            # spoke 0 points straight back
R_STEM = 0.305               # caster swivel axis radius
SPOKE_R0 = 0.030             # spoke root, buried in the hub
SPOKE_STATIONS = 12
SPOKE_W = (0.054, 0.040)     # section width, root -> tip
SPOKE_H = (0.040, 0.028)     # section height
SPOKE_ZB = (0.106, 0.088)    # section underside
SPOKE_ARCH = 0.004
HUB_PROFILE = [(0.030, 0.088), (0.046, 0.092), (0.052, 0.102), (0.052, 0.158),
               (0.048, 0.166), (0.040, 0.170)]
BOSS_R = 0.025
BOSS_PROFILE = [(0.018, 0.084), (0.024, 0.086), (0.025, 0.090), (0.025, 0.118),
                (0.023, 0.124), (0.017, 0.127)]

# --- Casters -----------------------------------------------------------------
WHEEL_R = 0.030
TRAIL = 0.030                # axle behind the swivel axis
# Caster yaw: trail direction, relative to the spoke's own bearing. Casters
# on a chair that has been rolled about point every which way.
CASTER_YAW = (160.0, 20.0, -115.0, 205.0, 70.0)
WHEEL_SEGS = 24
# (r, y) along the axle: nylon hub face, tyre sidewall, crowned tread,
# sidewall, dished nylon hub cap. No segment keeps r constant, so the
# caster's mirrored twin wheel never shares a tread plane with it.
WHEEL_PROFILE = [(0.0046, 0.0093), (0.0195, 0.0093), (0.0212, 0.0099), (0.0262, 0.0103),
                 (0.0288, 0.0118), (0.0297, 0.0145), (0.0300, 0.0177), (0.0297, 0.0210),
                 (0.0288, 0.0237), (0.0262, 0.0252), (0.0212, 0.0256), (0.0195, 0.0262),
                 (0.0120, 0.0266), (0.0046, 0.0262)]
WHEEL_TYRE_SEGS = range(2, 10)
AXLE_PROFILE = [(0.0025, -0.0290), (0.0040, -0.0283), (0.0040, 0.0283), (0.0025, 0.0290)]
WEB_HALF = 0.0085
HOOD_PROFILE = [(0.0336, -0.0282), (0.0360, -0.0282), (0.0366, -0.0276), (0.0366, 0.0276),
                (0.0360, 0.0282), (0.0336, 0.0282)]
HOOD_ARC = (10.0, -150.0)    # degrees about the axle; -90 is over the top
STEM_PROFILE = [(0.0040, 0.062), (0.0055, 0.0635), (0.0055, 0.116), (0.0040, 0.118)]
WASHER_PROFILE = [(0.0052, 0.0770), (0.0105, 0.0770), (0.0110, 0.0775), (0.0110, 0.0845),
                  (0.0052, 0.0845)]

# --- Gas lift and mechanism ------------------------------------------------------
COLUMN_PROFILE = [(0.022, 0.118), (0.025, 0.121), (0.025, 0.368), (0.023, 0.372)]
SLEEVES = (
    [(0.0285, 0.164), (0.0335, 0.164), (0.0340, 0.166), (0.0340, 0.228), (0.0330, 0.231),
     (0.0285, 0.231)],
    [(0.0258, 0.222), (0.0312, 0.222), (0.0316, 0.224), (0.0316, 0.278), (0.0306, 0.281),
     (0.0248, 0.281)],
)
SOCKET_PROFILE = [(0.020, 0.344), (0.030, 0.347), (0.034, 0.356), (0.036, 0.384)]
MECH_C = (0.0, 0.010, 0.398)
MECH_SIZE = (0.170, 0.240, 0.040)   # top 1 mm under the cushion's floor
TILT_C = (0.0, -0.070, 0.386)
TILT_R = 0.020
TILT_HALF = 0.100
KNOB_C = (0.0, -0.105, 0.388)
KNOB_PROFILE = [(0.006, -0.005), (0.019, -0.005), (0.021, -0.003), (0.021, 0.028),
                (0.0195, 0.034), (0.013, 0.038), (0.005, 0.040)]
LEVERS = (
    [(0.060, 0.000, 0.392), (0.150, -0.020, 0.388), (0.205, -0.055, 0.385)],
    [(-0.060, -0.020, 0.390), (-0.140, -0.040, 0.386), (-0.190, -0.070, 0.383)],
)

# --- Seat ----------------------------------------------------------------------
SEAT_HX = 0.250
SEAT_HY = 0.240
SEAT_RC = 0.100
SEAT_RMIN = 0.010
SEAT_CY = -0.030
SEAT_TAPER = 0.05            # back edge this much narrower than the front
SEAT_BULGE = 0.035           # sides bow out this much at mid-depth
SEAT_Z0 = 0.425              # the sculpting fades in from here ...
SEAT_ZFULL = 0.050           # ... over this rise, so no ring folds past another
SEAT_RING = dict(nc=8, nsx=12, nsy=12)
# (inset, z): bottom inside the shell, boxing side, a rounded top edge, the
# grey knit side panel, a seam groove, then the teal centre panel crowned in
SEAT_PROFILE = [(0.014, 0.419), (0.006, 0.4205), (0.001, 0.428), (0.000, 0.440),
                (0.000, 0.452), (0.002, 0.462), (0.006, 0.4700), (0.012, 0.4770),
                (0.020, 0.4815), (0.030, 0.4840), (0.042, 0.4852), (0.052, 0.4856),
                (0.058, 0.4846), (0.062, 0.4826), (0.066, 0.4846), (0.072, 0.4860),
                (0.084, 0.4872), (0.098, 0.4882), (0.112, 0.4889), (0.126, 0.4894),
                (0.140, 0.4897), (0.156, 0.4899), (0.174, 0.4900), (0.194, 0.4900),
                (0.214, 0.4900)]
SEAM_RING = 13               # the groove bottom: centre panel from here in
SEAT_DISH = 0.012
SEAT_WATERFALL = 0.024
SEAT_CHANNEL = 0.011         # thigh channels either side of the centre line
SEAT_CHANNEL_X = 0.095
SEAT_BOLSTER = 0.009
PIPE_R = 0.0032
PIPE_AT = (7, 8)             # the edge welt runs on the seam between these rings
PIPE_OUT = 0.0016            # centre outside the surface, so it bites by R - OUT
GROOVE_R = 0.0024            # a second welt laid in the seam groove
GROOVE_UP = 0.0010
WELT_PHASE = math.pi / 6.0     # a hexagon with a vertex on top: no welt face lies flat
PAN_HX = 0.254
PAN_HY = 0.244
PAN_RC = 0.100
PAN_PROFILE = [(0.020, 0.398), (0.008, 0.4005), (0.002, 0.406), (0.000, 0.416),
               (0.001, 0.425), (0.004, 0.4290), (0.009, 0.4300)]

# --- Back ----------------------------------------------------------------------
BACK_O = Vector((0.0, 0.235, 0.530))
BACK_RECLINE_DEG = 12.0
BACK_HX = 0.235
BACK_HY = 0.290              # outline half height; v runs 0 .. 2 * BACK_HY
BACK_RC = 0.090
BACK_TAPER0 = 0.84           # outline width scale at the bottom (1.0 at top)
BACK_ARCH = 0.036            # the top edge rises this much at the centre
BACK_WRAP = 0.060
LUMBAR_V = 0.170
LUMBAR_SIG = 0.090
LUMBAR_BULGE = 0.022
MESH_T = 0.003
MESH_INSETS = (0.000, 0.014, 0.040, 0.080, 0.130, 0.190)
FRAME_HA = 0.0150            # frame tube half depth (along the surface normal)
FRAME_HB = (0.0125, 0.0195)  # half width in the back's plane: top rail, foot
FRAME_THICK_V = (0.46, 0.10)  # the frame swells from the first v to the second
CROSS_V = 0.260
CROSS_OFF = -0.0115
CROSS_R = 0.0085
PAD_HX = 0.165
PAD_HY = 0.052
PAD_RC = 0.040
PAD_S = 0.0055               # S-curve amplitude across the lumbar pad's face
PAD_PROFILE = [(0.010, -0.0005), (0.003, 0.0020), (0.000, 0.0070), (0.002, 0.0120),
               (0.008, 0.0155), (0.018, 0.0170), (0.030, 0.0175)]
STRAP_U = (0.150, BACK_HX - 0.006)   # from inside the pad to inside the slider
STRAP_HV = 0.020
STRAP_OFF = (0.0010, 0.0042)
SLIDER_HV = 0.030            # slider half length along the frame
SLIDER_WALL = 0.004          # clamp wall over the frame tube
HEAD_V = 0.725               # headrest centre, on the back's surface
HEAD_OFF = 0.018             # carried this far forward of the back's surface
HEAD_HX = 0.140
HEAD_HY = 0.062
HEAD_RC = 0.050
HEAD_INSETS = (0.000, 0.010, 0.028, 0.048)
HEAD_FRAME = (0.011, 0.010)

# --- Arms (right arm at +X; the left is its mirror) -----------------------------
ARM_X = 0.273
ARM_Y = 0.030
PAD_Y = 0.000
BRACKET_PTS = [(0.100, 0.401), (0.200, 0.401), (0.245, 0.404), (0.266, 0.418),
               (0.273, 0.440), (0.273, 0.500), (0.273, 0.600)]
BRACKET_HALF = (0.006, 0.025)
POST_PROFILE = [(0.003, 0.505), (0.000, 0.509), (0.000, 0.646), (0.003, 0.650)]
COVER_PROFILE = [(0.004, 0.496), (0.000, 0.500), (0.000, 0.584), (0.003, 0.588)]
SUPPORT_PROFILE = [(0.003, 0.645), (0.000, 0.648), (0.000, 0.657), (0.003, 0.660)]
ARMPAD_PROFILE = [(0.008, 0.6555), (0.002, 0.6580), (0.000, 0.6660), (0.002, 0.6780),
                  (0.008, 0.6860), (0.018, 0.6895), (0.030, 0.6905)]

# --- Floor vignette: a chair mat under the casters, a potted plant beside it --
MAT_T = 0.004                # polycarbonate sheet thickness
MAT_SINK = 0.0006            # the casters press this far into the sheet
CHAIR_Z = MAT_T - MAT_SINK   # so the chair is built this far off the floor
MAT_HX = 0.600
MAT_HY = 0.640
MAT_CY = 0.060
MAT_RC = 0.060
MAT_TONGUE = 0.200           # the lip that runs forward under a desk
MAT_TONGUE_HX = 0.250
MAT_TONGUE_SHOULDER = 0.090
MAT_RING = dict(nc=6, nsx=36, nsy=12)
# (inset, z): a chamfered foot, a short wall and a bevelled top edge
MAT_PROFILE = [(0.0015, 0.0), (0.0, 0.0008), (0.0, 0.0014), (0.005, 0.0031),
               (0.011, 0.0039), (0.016, MAT_T)]
PLANT_C = (0.880, -0.080)
POT_SEGS = 40
# a planter with a foot, a swelling belly, a waist and a rolled lip
POT_PROFILE = [(0.004, 0.000), (0.092, 0.000), (0.100, 0.003), (0.103, 0.012),
               (0.100, 0.022), (0.116, 0.060), (0.136, 0.130), (0.146, 0.200),
               (0.143, 0.250), (0.141, 0.266), (0.150, 0.274), (0.152, 0.284),
               (0.148, 0.292), (0.140, 0.291), (0.132, 0.280), (0.126, 0.200),
               (0.110, 0.060), (0.090, 0.040), (0.004, 0.036)]
# soil biting the pot's inner wall by 1.2 mm, crowned toward the middle
SOIL_PROFILE = [(0.004, 0.215), (0.1283, 0.215), (0.1313, 0.255), (0.085, 0.2575),
                (0.004, 0.2595)]
SOIL_TOP = 0.2595
LEAF_COUNT = 9
LEAF_STATIONS = 10
LEAF_ROOT = 0.025            # blade bases buried at least this far under the crown
LEAF_ROOT_STEP = 0.001       # and each 1 mm deeper than the last, so no two base caps share a plane

# --- Budgets ------------------------------------------------------------------------
BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (1.635, 1.480, 1.317)
BASE_TRIS_MIN = 43700
BASE_TRIS_MAX = 45200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 14
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 580
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
FACE_FLOORS = (("fabric", 1330), ("mesh", 1450), ("shell", 3260), ("nylon", 4100),
               ("aluminium", 3950), ("chrome", 1370), ("rubber", 1820),
               ("leatherette", 1600), ("steel", 510), ("border", 1060), ("mat", 790),
               ("ceramic", 750), ("soil", 220), ("leaf", 715))

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Named supports: every wheel pressed into the mat, the mat's underside flat
# on the floor, the pot on the floor.
WHEEL_COUNT = 10
WHEEL_SINK = (0.0003, 0.0010)
FLOAT_CASTER = 3
FLOAT_LIFT = 0.005
MAT_FLAT_EPS = 1e-4
CURL_MAT = 0.006             # the back-left corner of the mat curled up
# Five-star geometry: spokes and bosses 72 degrees apart, bosses and swivel
# stems on one circle, stems plumb, coaxial with their bosses, and seated in
# them to a banded depth.
SPACING_TOL_DEG = 0.25
RADIUS_RANGE_MAX = 0.001
STEM_TILT_MAX_DEG = 0.2
STEM_COAX_MAX = 0.0003
STEM_SEAT = (0.025, 0.040)
SKEW_SPOKE = 0
SKEW_DEG = 3.0
# Gas lift: the column's axis through the hub's and the socket's axes, plumb,
# and inserted into each to a banded depth.
COLUMN_COAX_MAX = 0.0003
COLUMN_TILT_MAX_DEG = 0.2
HUB_BITE = (0.040, 0.065)
SOCKET_BITE = (0.020, 0.040)
OFFSET_COLUMN = 0.003
# Stance and size: the armrests a mirrored, level pair; seat height, armrest
# height over the seat and star diameter in band; the mass centre inside the
# caster contact polygon.
ARM_MIRROR_EPS = 0.0005
UNEVEN_ARM = 0.010
SEAT_HEIGHT = (0.44, 0.50)
ARM_OVER_SEAT = (0.17, 0.26)
STAR_DIAMETER = 0.660
STAR_TOL = 0.005
STANCE_MARGIN = 0.12
# Densities by material slot (kg/m^3). Foam cushions and pads are light;
# the mechanism is a pressed-steel housing modelled solid, so steel takes
# an effective density. The mat and the plant are not part of the chair's
# mass.
DENSITY = (50.0, 400.0, 1150.0, 1150.0, 2700.0, 7850.0, 1200.0, 300.0, 3000.0, 50.0,
           1200.0, 2000.0, 1300.0, 700.0)
# Connected chair: one wheel slid off its axle end.
LOOSE_CASTER = 0
LOOSE_SLIDE = 0.024
# Lumbar sliders clamp the frame: every slider vertex a banded distance off
# the frame tube it rides on.
SLIDER_GAP = (0.0020, 0.0065)
FLOAT_LUMBAR = 0.006
# Plant: every leaf's base buried in the soil to a banded depth, inside the pot.
LEAF_DEPTH = (0.015, 0.045)
LEAF_WALL_CLEAR = 0.010
FLOAT_LEAVES = 0.040

HERO_YAW_DEG = 18.0
WALL_Y = 3.2
CAM_LENS = 50.0
CAM_VIEW = (-0.55, -0.83)
CAM_DIST = 4.75
CAM_LIFT = 0.72
AIM_OFFSET = (0.0, 0.0, -0.13)

FABRIC_IDX = 0
MESH_IDX = 1
SHELL_IDX = 2
NYLON_IDX = 3
ALU_IDX = 4
CHROME_IDX = 5
RUBBER_IDX = 6
LEATHER_IDX = 7
STEEL_IDX = 8
BORDER_IDX = 9
MAT_IDX = 10
CERAMIC_IDX = 11
SOIL_IDX = 12
LEAF_IDX = 13

# Part tags (face attribute "part" = kind * 100 + index). Measurements read
# positions off the mesh; the tag only says which shell is which part.
(SPOKE, BOSS, STEM, WHEEL, AXLE, WEB, HOOD, WASHER, HUB, COLUMN, SLEEVE, SOCKET, MECH,
 TILT, KNOB, LEVER, PADDLE, PAN, CUSHION, PIPING, FRAME, MESHPANEL, LUMBAR, STRAP,
 CROSSBAR, BACKHUB, SPINE, BRACKET, POST, SUPPORT, ARMPAD, BUTTON, HEADSTEM,
 HEADFRAME, HEADMESH, HEADHUB, SLIDER, COVER, PIVOT, MAT, POT, SOIL, LEAF) = range(1, 44)
ARM_KINDS = (BRACKET, POST, SUPPORT, ARMPAD, BUTTON, COVER, PIVOT)
VIGNETTE_KINDS = (MAT, POT, SOIL, LEAF)


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
# Construction helpers
# --------------------------------------------------------------------------

def _mark(faces, mat_idx):
    for f in faces:
        f.material_index = mat_idx


def tag(bm, verts, kind, idx=0):
    layer = bm.faces.layers.int.get("part")
    for f in {f for v in verts for f in v.link_faces}:
        f[layer] = kind * 100 + idx


def add_box(bm, loc, scale, mat_idx):
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = geo["verts"]
    origin = Vector(loc)
    for v in verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])) + origin
    _mark({f for v in verts for f in v.link_faces}, mat_idx)
    return list(verts)


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False, seg_mats=None, cap_mats=None, rmod=None, arc=None):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: the profile
    is an open polyline closed by n-gon caps at its two ends; otherwise it
    is a closed polygon revolved into a ring shell. ``arc`` = (a0, a1) in
    radians revolves a closed profile over part of a turn and caps its two
    ends. ``seg_mats`` gives a material per profile segment, ``cap_mats``
    the (start, end) caps, and ``rmod(i, j)`` scales the radius of profile
    point ``j`` on ring ``i``."""
    c = Vector(center)
    m = rot if rot is not None else Matrix.Identity(3)
    n_rings = segs + 1 if arc else segs
    rings = []
    for i in range(n_rings):
        if arc:
            a = arc[0] + (arc[1] - arc[0]) * i / segs
        else:
            a = phase + 2.0 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        ring = []
        for j, (r, z) in enumerate(profile):
            rr = r * (rmod(i, j) if rmod else 1.0)
            ring.append(bm.verts.new(c + m @ Vector((rr * ca, rr * sa, z))))
        rings.append(ring)
    n = len(profile)
    last = n - 1 if solid else n
    faces = []
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % n_rings]
        for j in range(last):
            k = (j + 1) % n
            f = bm.faces.new((r0[j], r1[j], r1[k], r0[k]))
            f.material_index = seg_mats[j] if seg_mats else mat_idx
            faces.append(f)
    if solid:
        f0 = bm.faces.new([rings[i][0] for i in reversed(range(segs))])
        f1 = bm.faces.new([rings[i][n - 1] for i in range(segs)])
        f0.material_index = cap_mats[0] if cap_mats else mat_idx
        f1.material_index = cap_mats[1] if cap_mats else mat_idx
    if arc:
        for ring in (rings[0], rings[-1]):
            f = bm.faces.new(ring)
            f.material_index = mat_idx
    return [v for ring in rings for v in ring]


def add_loft(bm, rings_co, mat_idx, closed=False, caps=True, band_mats=None, cap_mats=None):
    """Rings of points (each a closed loop, equal counts) joined in order.
    ``closed`` joins the last ring back to the first (a torus-like tube);
    otherwise ``caps`` closes both ends with n-gons. ``band_mats(i)`` gives
    the material of the band between rings ``i`` and ``i + 1``."""
    rings = [[bm.verts.new(p) for p in ring] for ring in rings_co]
    n = len(rings)
    m = len(rings[0])
    for i in range(n if closed else n - 1):
        r0, r1 = rings[i], rings[(i + 1) % n]
        mat = band_mats(i) if band_mats else mat_idx
        for k in range(m):
            k1 = (k + 1) % m
            bm.faces.new((r0[k], r0[k1], r1[k1], r1[k])).material_index = mat
    if not closed and caps:
        c0, c1 = cap_mats if cap_mats else (mat_idx, mat_idx)
        bm.faces.new(tuple(reversed(rings[0]))).material_index = c0
        bm.faces.new(tuple(rings[-1])).material_index = c1
    return [v for ring in rings for v in ring]


def sweep_rings(pts, section, normals=None, side=None, closed=False):
    """Section [(a, b), ...] placed along a polyline: ``a`` along the frame
    normal, ``b`` along the binormal. ``section`` may be a function of the
    point index, for a member whose section changes along its length. The
    normal comes from ``normals`` (a surface), from a fixed ``side`` axis
    (a planar path), or by parallel transport."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rings = []
    prev = None
    for i, p in enumerate(pts):
        if closed:
            a, b = pts[i - 1], pts[(i + 1) % n]
        else:
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        t = (b - a).normalized()
        if normals is not None:
            nv = Vector(normals[i])
            nv = (nv - t * nv.dot(t)).normalized()
            bv = t.cross(nv)
        elif side is not None:
            bv = Vector(side)
            bv = (bv - t * bv.dot(t)).normalized()
            nv = bv.cross(t)
        else:
            if prev is None:
                ref = X_AX if abs(t.x) < 0.9 else Z_AX
                prev = (ref - t * ref.dot(t)).normalized()
            nv = (prev - t * prev.dot(t)).normalized()
            prev = nv
            bv = t.cross(nv)
        sec = section(i) if callable(section) else section
        rings.append([p + nv * sa + bv * sb for sa, sb in sec])
    return rings


def add_sweep(bm, pts, section, mat_idx, normals=None, side=None, closed=False):
    return add_loft(bm, sweep_rings(pts, section, normals, side, closed), mat_idx,
                    closed=closed)


def circle_section(r, n, phase=0.0):
    return [(r * math.cos(phase + 2.0 * math.pi * k / n), r * math.sin(phase + 2.0 * math.pi * k / n))
            for k in range(n)]


def superellipse_section(ha, hb, n, p):
    out = []
    for k in range(n):
        t = 2.0 * math.pi * (k + 0.5) / n
        c, s = math.cos(t), math.sin(t)
        out.append((ha * math.copysign(abs(c) ** (2.0 / p), c),
                    hb * math.copysign(abs(s) ** (2.0 / p), s)))
    return out


def rect_section(ha, hb, c):
    return [(ha, -hb + c), (ha, hb - c), (ha - c, hb), (-ha + c, hb), (-ha, hb - c),
            (-ha, -hb + c), (-ha + c, -hb), (ha - c, -hb)]


def rrect_loop(hx, hy, r, nc=8, nsx=6, nsy=6):
    """Rounded rectangle, counter-clockwise, with ``nsx`` / ``nsy`` spans on
    the straight sides so a loop can bend over a curved surface."""
    corners = ((1, 1), (-1, 1), (-1, -1), (1, -1))
    pts = []
    for k, (sx, sy) in enumerate(corners):
        cx, cy = sx * (hx - r), sy * (hy - r)
        a0 = 0.5 * math.pi * k
        for s in range(nc + 1):
            a = a0 + 0.5 * math.pi * s / nc
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        a1 = a0 + 0.5 * math.pi
        nx, ny = corners[(k + 1) % 4]
        p0 = (cx + r * math.cos(a1), cy + r * math.sin(a1))
        p1 = (nx * (hx - r) + r * math.cos(a1), ny * (hy - r) + r * math.sin(a1))
        nside = nsx if k in (0, 2) else nsy
        for s in range(1, nside):
            t = s / nside
            pts.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t))
    return pts


def rrect_rings(hx, hy, rc, rmin, profile, xform, nc=8, nsx=6, nsy=6):
    rings = []
    for d, z in profile:
        r = max(rc - d, rmin)
        rings.append([xform(x, y, z) for x, y in rrect_loop(hx - d, hy - d, r, nc, nsx, nsy)])
    return rings


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


def frame_from(axis, ref):
    """Rotation whose local Z is ``axis`` and local X lies toward ``ref``."""
    z = Vector(axis).normalized()
    x = Vector(ref)
    x = (x - z * x.dot(z)).normalized()
    y = z.cross(x)
    return Matrix((x, y, z)).transposed()


def catmull(pts, per=6):
    pts = [Vector(p) for p in pts]
    ext = [pts[0] * 2.0 - pts[1]] + pts + [pts[-1] * 2.0 - pts[-2]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2.0 * p1) + (-p0 + p2) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                              + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t))
    out.append(pts[-1])
    return out


def smooth01(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def frac(x):
    return x - math.floor(x)


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------

def spoke_section():
    """Crowned top, straight sides, two underside channels either side of a
    centre rib: (a across in -1..1, b up in 0..1)."""
    right = [(0.93, 0.0), (1.0, 0.08), (1.0, 0.40)]
    crown = []
    for i in range(1, 10):
        phi = math.pi * i / 10.0
        c, s = math.cos(phi), math.sin(phi)
        crown.append((math.copysign(abs(c) ** (2.0 / 3.0), c), 0.40 + 0.60 * abs(s) ** (2.0 / 3.0)))
    under = [(-1.0, 0.40), (-1.0, 0.08), (-0.93, 0.0), (-0.74, 0.0), (-0.68, 0.06),
             (-0.68, 0.52), (-0.62, 0.58), (-0.20, 0.58), (-0.14, 0.52), (-0.14, 0.10),
             (-0.08, 0.03), (0.08, 0.03), (0.14, 0.10), (0.14, 0.52), (0.20, 0.58),
             (0.62, 0.58), (0.68, 0.52), (0.68, 0.06), (0.74, 0.0)]
    return right + crown + under


def add_spoke(bm, bearing):
    er = Vector((math.cos(bearing), math.sin(bearing), 0.0))
    et = Vector((-math.sin(bearing), math.cos(bearing), 0.0))
    sec = spoke_section()
    rings = []
    for i in range(SPOKE_STATIONS):
        t = i / (SPOKE_STATIONS - 1)
        r = SPOKE_R0 + (R_STEM - SPOKE_R0) * t
        w = SPOKE_W[0] + (SPOKE_W[1] - SPOKE_W[0]) * t
        h = SPOKE_H[0] + (SPOKE_H[1] - SPOKE_H[0]) * t
        zb = SPOKE_ZB[0] + (SPOKE_ZB[1] - SPOKE_ZB[0]) * t + SPOKE_ARCH * math.sin(math.pi * t)
        rings.append([er * r + et * (a * 0.5 * w) + Z_AX * (zb + b * h) for a, b in sec])
    return add_loft(bm, rings, ALU_IDX)


def caster_frame(k, skew=0.0):
    """Stem position and the caster's (trail, axle) directions."""
    bearing = math.radians(SPOKE0_DEG + 360.0 * k / SPOKES) + skew
    stem = Vector((R_STEM * math.cos(bearing), R_STEM * math.sin(bearing), 0.0))
    yaw = bearing + math.radians(CASTER_YAW[k])
    xl = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    yl = Vector((-math.sin(yaw), math.cos(yaw), 0.0))
    return bearing, stem, xl, yl


def add_caster(bm, k, skew=0.0, lift=0.0, slide=0.0):
    """Twin-wheel caster on spoke k's swivel axis. ``lift`` raises the
    caster body (not the stem); ``slide`` pushes the +axle wheel along the
    axle."""
    _bearing, stem, xl, yl = caster_frame(k, skew)
    up = Z_AX * lift
    # stem, washer: plumb about the swivel axis
    tag(bm, add_lathe(bm, STEM_PROFILE, 12, CHROME_IDX, center=stem, solid=True), STEM, k)
    tag(bm, add_lathe(bm, WASHER_PROFILE, 14, CHROME_IDX, center=stem + up), WASHER, k)
    # axle frame: local Z along the axle, local X along the trail
    axle_c = stem + xl * TRAIL + Z_AX * WHEEL_R + up
    rot = Matrix((xl, -Z_AX, yl)).transposed()
    # a ring at angle +90 degrees points straight down: the contact vertex
    phase = 0.5 * math.pi
    seg_mats = [RUBBER_IDX if j in WHEEL_TYRE_SEGS else NYLON_IDX
                for j in range(len(WHEEL_PROFILE) - 1)]
    tag(bm, add_lathe(bm, WHEEL_PROFILE, WHEEL_SEGS, NYLON_IDX, center=axle_c + yl * slide,
                      rot=rot, phase=phase, solid=True, seg_mats=seg_mats), WHEEL, k)
    mirrored = [(r, -y) for r, y in reversed(WHEEL_PROFILE)]
    tag(bm, add_lathe(bm, mirrored, WHEEL_SEGS, NYLON_IDX, center=axle_c, rot=rot, phase=phase,
                      solid=True, seg_mats=list(reversed(seg_mats))), WHEEL, k)
    tag(bm, add_lathe(bm, AXLE_PROFILE, 12, CHROME_IDX, center=axle_c, rot=rot, solid=True),
        AXLE, k)
    # nylon web between the wheels: hull of the axle boss and the stem lug
    circles = [(TRAIL, WHEEL_R, 0.0135), (0.0, 0.070, 0.012)]
    pts = []
    for cx, cz, r in circles:
        for i in range(20):
            a = 2.0 * math.pi * (i + 0.5) / 20
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    outline = hull2d(pts)
    base = stem + up
    a = [bm.verts.new(base + xl * x + Z_AX * z - yl * WEB_HALF) for x, z in outline]
    b = [bm.verts.new(base + xl * x + Z_AX * z + yl * WEB_HALF) for x, z in outline]
    n = len(outline)
    faces = [bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n])) for i in range(n)]
    faces.append(bm.faces.new(tuple(reversed(a))))
    faces.append(bm.faces.new(tuple(b)))
    _mark(faces, NYLON_IDX)
    tag(bm, a + b, WEB, k)
    # hood over both wheels
    tag(bm, add_lathe(bm, HOOD_PROFILE, 14, NYLON_IDX, center=axle_c, rot=rot,
                      arc=(math.radians(HOOD_ARC[0]) + phase - 0.5 * math.pi,
                           math.radians(HOOD_ARC[1]) + phase - 0.5 * math.pi)), HOOD, k)
    return a + b


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


def seat_contour(x, y):
    """Top-surface sculpting: a dish toward the back, two thigh channels
    along the front half, a waterfall that rolls the front edge down,
    bolsters at the sides. Every term is even in x."""
    ax = abs(x)
    dish = -SEAT_DISH * math.exp(-((x / 0.15) ** 2 + ((y - 0.04) / 0.13) ** 2))
    channel = (-SEAT_CHANNEL * math.exp(-((ax - SEAT_CHANNEL_X) / 0.036) ** 2)
               * smooth01((0.06 - y) / 0.12))
    fall = -SEAT_WATERFALL * smooth01((-0.09 - y) / 0.15)
    bolster = SEAT_BOLSTER * smooth01((ax - 0.13) / 0.09)
    return dish + channel + fall + bolster


def seat_plan(x, y):
    """Plan scale: narrower at the back, sides bowed out at mid-depth."""
    taper = 1.0 - SEAT_TAPER * (y + SEAT_HY) / (2.0 * SEAT_HY)
    return taper * (1.0 + SEAT_BULGE * math.cos(0.5 * math.pi * y / SEAT_HY) ** 2)


def seat_xform(x, y, z):
    zf = smooth01((z - SEAT_Z0) / SEAT_ZFULL)
    return Vector((x * seat_plan(x, y), y + SEAT_CY, z + zf * seat_contour(x, y)))


def pan_xform(x, y, z):
    # the shell follows the cushion's plan but not its contour
    return Vector((x * seat_plan(x, y), y + SEAT_CY, z))


def welt_ring(d0, z0, d1, z1, out):
    """A cord's centre on the seam between two profile points, pushed
    ``out`` along the profile's outward normal."""
    ln = math.hypot(d1 - d0, z1 - z0)
    dp = 0.5 * (d0 + d1) - out * (z1 - z0) / ln
    zp = 0.5 * (z0 + z1) + out * (d1 - d0) / ln
    return [seat_xform(x, y, zp)
            for x, y in rrect_loop(SEAT_HX - dp, SEAT_HY - dp, max(SEAT_RC - dp, SEAT_RMIN),
                                   **SEAT_RING)]


def add_seat(bm):
    tag(bm, add_loft(bm, rrect_rings(PAN_HX, PAN_HY, PAN_RC, SEAT_RMIN, PAN_PROFILE, pan_xform,
                                     **SEAT_RING), SHELL_IDX), PAN)
    # two-tone cushion: grey knit side panels out to the groove, teal centre
    rings = rrect_rings(SEAT_HX, SEAT_HY, SEAT_RC, SEAT_RMIN, SEAT_PROFILE, seat_xform,
                        **SEAT_RING)
    tag(bm, add_loft(bm, rings, FABRIC_IDX,
                     band_mats=lambda i: FABRIC_IDX if i >= SEAM_RING else BORDER_IDX,
                     cap_mats=(BORDER_IDX, FABRIC_IDX)), CUSHION)
    # piped welt along the top edge, biting the cushion by PIPE_R - PIPE_OUT
    (d0, z0), (d1, z1) = SEAT_PROFILE[PIPE_AT[0]], SEAT_PROFILE[PIPE_AT[1]]
    tag(bm, add_sweep(bm, welt_ring(d0, z0, d1, z1, PIPE_OUT), circle_section(PIPE_R, 6, WELT_PHASE),
                      LEATHER_IDX, side=Z_AX, closed=True), PIPING, 0)
    # a second welt laid in the seam groove, its centre GROOVE_UP over the
    # groove bottom so it bites the bottom and sits between the walls
    dg, zg = SEAT_PROFILE[SEAM_RING]
    groove = [seat_xform(x, y, zg + GROOVE_UP)
              for x, y in rrect_loop(SEAT_HX - dg, SEAT_HY - dg, max(SEAT_RC - dg, SEAT_RMIN),
                                     **SEAT_RING)]
    tag(bm, add_sweep(bm, groove, circle_section(GROOVE_R, 6, WELT_PHASE), LEATHER_IDX, side=Z_AX,
                      closed=True), PIPING, 1)


def back_axes():
    rec = math.radians(BACK_RECLINE_DEG)
    vdir = Vector((0.0, math.sin(rec), math.cos(rec)))
    ndir = Vector((0.0, -math.cos(rec), math.sin(rec)))      # toward the sitter
    return vdir, ndir


def back_point(u, v, off=0.0):
    """The back's surface: outline coordinate u (scaled by a taper that
    narrows the bottom), height v along the recline, offset ``off`` along
    the back's forward normal. Wrapped round the sitter and bulged forward
    at the lumbar."""
    vdir, ndir = back_axes()
    s = BACK_TAPER0 + (1.0 - BACK_TAPER0) * v / (2.0 * BACK_HY)
    ux = u * s
    w = (-BACK_WRAP * (ux / BACK_HX) ** 2
         + LUMBAR_BULGE * math.exp(-((v - LUMBAR_V) / LUMBAR_SIG) ** 2))
    return BACK_O + X_AX * ux + vdir * v + ndir * (w + off)


def back_normal(u, v):
    e = 1e-4
    du = back_point(u + e, v) - back_point(u - e, v)
    dv = back_point(u, v + e) - back_point(u, v - e)
    n = du.cross(dv).normalized()
    return n if n.dot(back_axes()[1]) > 0.0 else -n


def back_loop(d, nc=10, nsx=10, nsy=12):
    """Outline (u, v) at an inset: a rounded rectangle whose top edge is
    arched, even in u."""
    r = max(BACK_RC - d, 0.012)
    out = []
    for x, y in rrect_loop(BACK_HX - d, BACK_HY - d, r, nc, nsx, nsy):
        v = y + BACK_HY
        rise = BACK_ARCH * (1.0 - (x / BACK_HX) ** 2) * smooth01((v - 0.6 * BACK_HY) / BACK_HY)
        out.append((x, v + rise))
    return out


def frame_hb(v):
    """The frame's half width in the back's plane: slim along the top rail,
    swelling toward the foot where it takes the load."""
    return FRAME_HB[0] + (FRAME_HB[1] - FRAME_HB[0]) * smooth01(
        (FRAME_THICK_V[0] - v) / (FRAME_THICK_V[0] - FRAME_THICK_V[1]))


def frame_section(v, grow=0.0):
    return superellipse_section(FRAME_HA + grow, frame_hb(v) + grow, 12, 2.8)


def add_mesh_panel(bm, loops, point, kind):
    """A stretched mesh: front and back skins MESH_T apart on a surface,
    lofted from its outermost loop (the frame's centreline) inward."""
    front = [[point(u, v, 0.5 * MESH_T) for u, v in lp] for lp in loops]
    back = [[point(u, v, -0.5 * MESH_T) for u, v in lp] for lp in loops]
    tag(bm, add_loft(bm, list(reversed(front)) + back, MESH_IDX), kind)


def add_back(bm, lumbar_shift=0.0):
    # frame: a closed moulded tube on the outline, slim at the top rail and
    # swelling toward the foot
    outline = back_loop(0.0)
    pts = [back_point(u, v) for u, v in outline]
    nrm = [back_normal(u, v) for u, v in outline]
    tag(bm, add_sweep(bm, pts, lambda i: frame_section(outline[i][1]), SHELL_IDX,
                      normals=nrm, closed=True), FRAME)
    # elastomeric mesh stretched from the frame's centreline in
    add_mesh_panel(bm, [back_loop(d) for d in MESH_INSETS], back_point, MESHPANEL)
    # lumbar: an S-curved pad on the mesh, straps out to two sliders that
    # clamp the frame's sides; ``lumbar_shift`` floats the whole unit forward
    _vdir, ndir = back_axes()
    shift = ndir * lumbar_shift

    def pad_point(x, y, z):
        s = PAD_S * math.sin(math.pi * y / PAD_HY) * max(0.0, z) / PAD_PROFILE[-1][1]
        return back_point(x, y + LUMBAR_V, z + s) + shift

    tag(bm, add_loft(bm, rrect_rings(PAD_HX, PAD_HY, PAD_RC, 0.008, PAD_PROFILE, pad_point,
                                     nc=6, nsx=10, nsy=6), FABRIC_IDX), LUMBAR)
    sec = rect_section(STRAP_HV, 0.5 * (STRAP_OFF[1] - STRAP_OFF[0]), 0.0008)
    mid = 0.5 * (STRAP_OFF[0] + STRAP_OFF[1])
    for side in (-1.0, 1.0):
        rings = []
        for i in range(7):
            u = side * (STRAP_U[0] + (STRAP_U[1] - STRAP_U[0]) * i / 6)
            rings.append([back_point(u, LUMBAR_V + sv, mid + so) + shift for sv, so in sec])
        if side < 0:
            rings = [list(reversed(r)) for r in rings]
        tag(bm, add_loft(bm, rings, SHELL_IDX), STRAP, 0 if side > 0 else 1)
        # slider: a sleeve on the frame's own section, SLIDER_WALL proud of it
        vs = [LUMBAR_V - SLIDER_HV + 2.0 * SLIDER_HV * i / 4 for i in range(5)]
        spts = [back_point(side * BACK_HX, v) + shift for v in vs]
        snrm = [back_normal(side * BACK_HX, v) for v in vs]
        tag(bm, add_sweep(bm, spts, lambda i: frame_section(vs[i], SLIDER_WALL), NYLON_IDX,
                          normals=snrm), SLIDER, 0 if side > 0 else 1)
    # cross bar and hub plate behind the panel
    cross = [back_point(-0.241 + 0.482 * i / 15, CROSS_V, CROSS_OFF) for i in range(16)]
    tag(bm, add_sweep(bm, cross, circle_section(CROSS_R, 12), SHELL_IDX), CROSSBAR)
    hub_c = back_point(0.0, CROSS_V, -0.006)
    tag(bm, add_lathe(bm, [(0.036, 0.0), (0.040, 0.003), (0.040, 0.020), (0.036, 0.024)], 32,
                      SHELL_IDX, center=hub_c, rot=frame_from(-ndir, X_AX), solid=True), BACKHUB)
    # aluminium spine: out of the mechanism's rear, down under the back and
    # up behind the panel into the hub plate
    ctrl = [Vector((0.0, 0.060, 0.398)), Vector((0.0, 0.150, 0.398)),
            Vector((0.0, 0.232, 0.404)), Vector((0.0, 0.268, 0.432)),
            Vector((0.0, 0.284, 0.478)),
            back_point(0.0, 0.03, -0.036), back_point(0.0, 0.14, -0.030),
            back_point(0.0, CROSS_V, -0.020)]
    tag(bm, add_sweep(bm, catmull(ctrl, per=4), superellipse_section(0.008, 0.026, 20, 4.0),
                      ALU_IDX, side=X_AX), SPINE)
    # headrest: an aluminium stem up the back from the hub plate, clear of
    # the frame's top rail, into a hub behind a framed mesh pad carried
    # HEAD_OFF forward of the back's surface
    def head_point(u, v, off=0.0):
        return back_point(u, v, HEAD_OFF + off)

    ctrl = [back_point(0.0, CROSS_V + 0.014, -0.019), back_point(0.0, 0.42, -0.028),
            back_point(0.0, 0.60, -0.036), back_point(0.0, 0.672, -0.018),
            head_point(0.0, HEAD_V, -0.008)]
    tag(bm, add_sweep(bm, catmull(ctrl, per=5), superellipse_section(0.006, 0.019, 16, 4.0),
                      ALU_IDX, side=X_AX), HEADSTEM)
    hc = head_point(0.0, HEAD_V, -0.0055)
    tag(bm, add_lathe(bm, [(0.026, -0.0020), (0.030, 0.0), (0.030, 0.0030), (0.027, 0.0040)],
                      28, SHELL_IDX, center=hc, rot=frame_from(back_normal(0.0, HEAD_V), X_AX),
                      solid=True), HEADHUB)

    def head_loop(d):
        return [(x, y + HEAD_V) for x, y in
                rrect_loop(HEAD_HX - d, HEAD_HY - d, max(HEAD_RC - d, 0.008), 6, 10, 3)]

    outline = head_loop(0.0)
    tag(bm, add_sweep(bm, [head_point(u, v) for u, v in outline],
                      superellipse_section(HEAD_FRAME[0], HEAD_FRAME[1], 10, 2.8), SHELL_IDX,
                      normals=[back_normal(u, v) for u, v in outline], closed=True), HEADFRAME)
    add_mesh_panel(bm, [head_loop(d) for d in HEAD_INSETS], head_point, HEADMESH)


def add_arm(bm, side, raise_=0.0):
    s = 1.0 if side == 0 else -1.0
    up = Vector((0.0, 0.0, raise_))
    path = catmull([Vector((s * x, ARM_Y, z)) for x, z in BRACKET_PTS], per=4)
    tag(bm, add_sweep(bm, path, rect_section(BRACKET_HALF[0], BRACKET_HALF[1], 0.0022), ALU_IDX,
                      side=Y_AX), BRACKET, side)

    def at(cx, cy, dz):
        return lambda x, y, z: Vector((cx + x, cy + y, z + dz))

    # telescoping cover fixed on the bracket; the post slides in it
    cover = rrect_rings(0.025, 0.039, 0.016, 0.004, COVER_PROFILE, at(s * ARM_X, ARM_Y, 0.0),
                        nc=5, nsx=2, nsy=3)
    tag(bm, add_loft(bm, cover, SHELL_IDX), COVER, side)
    post = rrect_rings(0.020, 0.034, 0.012, 0.004, POST_PROFILE, at(s * ARM_X, ARM_Y, raise_),
                       nc=5, nsx=2, nsy=3)
    tag(bm, add_loft(bm, post, NYLON_IDX), POST, side)
    btn_prof = [(0.0065, 0.0), (0.0065, 0.0030), (0.0055, 0.0048), (0.0020, 0.0053)]
    btn = Vector((s * ARM_X, ARM_Y - 0.034 + 0.001, 0.622)) + up
    tag(bm, add_lathe(bm, btn_prof, 20, CHROME_IDX, center=btn, rot=frame_from(-Y_AX, X_AX),
                      solid=True), BUTTON, side)
    # the pivot / width button on the post's outer face
    piv = Vector((s * (ARM_X + 0.020 - 0.001), ARM_Y + 0.004, 0.628)) + up
    tag(bm, add_lathe(bm, btn_prof, 20, CHROME_IDX, center=piv,
                      rot=frame_from(X_AX * s, Z_AX), solid=True), PIVOT, side)
    sup = rrect_rings(0.028, 0.110, 0.024, 0.004, SUPPORT_PROFILE, at(s * ARM_X, PAD_Y, raise_),
                      nc=6, nsx=2, nsy=6)
    tag(bm, add_loft(bm, sup, SHELL_IDX), SUPPORT, side)
    pad = rrect_rings(0.042, 0.128, 0.036, 0.004, ARMPAD_PROFILE, at(s * ARM_X, PAD_Y, raise_),
                      nc=6, nsx=3, nsy=8)
    tag(bm, add_loft(bm, pad, LEATHER_IDX), ARMPAD, side)


def mat_loop(d):
    """The mat's plan at an inset: a rounded rectangle whose front edge
    carries a lip forward under the desk, even in x."""
    r = max(MAT_RC - d, 0.010)
    out = []
    for x, y in rrect_loop(MAT_HX - d, MAT_HY - d, r, **MAT_RING):
        if y < 0.0:
            y -= MAT_TONGUE * smooth01(
                (MAT_TONGUE_HX + MAT_TONGUE_SHOULDER - abs(x)) / MAT_TONGUE_SHOULDER)
        out.append((x, y + MAT_CY))
    return out


def add_mat(bm, curl=False):
    rings = []
    for d, z in MAT_PROFILE:
        ring = []
        for x, y in mat_loop(d):
            zz = z
            if curl:
                zz += CURL_MAT * smooth01(((-x) + (y - MAT_CY) - 0.72) / 0.40)
            ring.append(Vector((x, y, zz)))
        rings.append(ring)
    tag(bm, add_loft(bm, rings, MAT_IDX), MAT)


def add_plant(bm, lift=0.0):
    c = Vector((PLANT_C[0], PLANT_C[1], 0.0))
    tag(bm, add_lathe(bm, POT_PROFILE, POT_SEGS, CERAMIC_IDX, center=c, solid=True), POT)
    tag(bm, add_lathe(bm, SOIL_PROFILE, POT_SEGS, SOIL_IDX, center=c, phase=math.pi / POT_SEGS,
                      solid=True), SOIL)
    # snake-plant blades: a folded V section, lanceolate in width, leaning
    # out and turning slowly, every base buried LEAF_ROOT under the crown
    for i in range(LEAF_COUNT):
        a = 0.4 + i * 2.39996323
        rb = 0.014 + 0.048 * math.sqrt((i + 0.5) / LEAF_COUNT)
        h = 0.44 + 0.30 * frac(i * 0.618034 + 0.27)
        w = 0.058 + 0.024 * frac(i * 0.414214 + 0.61)
        lean = math.radians(2.0 + 8.0 * (rb - 0.014) / 0.048 + 3.0 * frac(i * 0.732051 + 0.2))
        twist = math.radians(-35.0 + 70.0 * frac(i * 0.259921 + 0.13))
        er = Vector((math.cos(a), math.sin(a), 0.0))
        et = Vector((-math.sin(a), math.cos(a), 0.0))
        base = c + er * rb + Z_AX * (SOIL_TOP - LEAF_ROOT - LEAF_ROOT_STEP * i + lift)
        reach = h * math.tan(lean)
        rings = []
        for s in range(LEAF_STATIONS):
            t = s / (LEAF_STATIONS - 1)
            p = base + Z_AX * (h * t) + er * (reach * t ** 1.6)
            tang = (Z_AX * h + er * (reach * 1.6 * t ** 0.6)).normalized()
            ang = twist * t
            across = et * math.cos(ang) + er * math.sin(ang)
            across = (across - tang * across.dot(tang)).normalized()
            depth = tang.cross(across)
            hw = max(0.0025, 0.5 * w * math.sin(math.pi * (0.10 + 0.90 * t)) ** 0.7)
            fold = 0.30 * hw
            th = 0.0008 + 0.0030 * (1.0 - t)
            sec = [(-1.0, fold), (-0.5, 0.25 * fold), (0.0, 0.0), (0.5, 0.25 * fold),
                   (1.0, fold), (0.5, 0.25 * fold - th), (0.0, -th), (-0.5, 0.25 * fold - th)]
            rings.append([p + across * (u * hw) + depth * dd for u, dd in sec])
        tag(bm, add_loft(bm, rings, LEAF_IDX), LEAF, i)


# --------------------------------------------------------------------------
# The chair
# --------------------------------------------------------------------------

def build_chair_mesh(name, bevel_offset, bevel_segments, skew_spoke=False, float_caster=False,
                     offset_column=False, uneven_arms=False, loose_wheel=False,
                     float_lumbar=False, curl_mat=False, float_leaves=False):
    bm = bmesh.new()
    try:
        bm.faces.layers.int.new("part")
        bevel_verts = []

        # --- five-star base
        tag(bm, add_lathe(bm, HUB_PROFILE, 40, NYLON_IDX, solid=True), HUB)
        for k in range(SPOKES):
            skew = math.radians(SKEW_DEG) if (skew_spoke and k == SKEW_SPOKE) else 0.0
            bearing, stem, _xl, _yl = caster_frame(k, skew)
            tag(bm, add_spoke(bm, bearing), SPOKE, k)
            tag(bm, add_lathe(bm, BOSS_PROFILE, 24, ALU_IDX, center=stem, solid=True), BOSS, k)
            bevel_verts += add_caster(
                bm, k, skew,
                lift=FLOAT_LIFT if (float_caster and k == FLOAT_CASTER) else 0.0,
                slide=LOOSE_SLIDE if (loose_wheel and k == LOOSE_CASTER) else 0.0)

        # --- gas lift: chrome column in a two-stage telescoping cover
        col_c = Vector((OFFSET_COLUMN if offset_column else 0.0, 0.0, 0.0))
        tag(bm, add_lathe(bm, COLUMN_PROFILE, 32, CHROME_IDX, center=col_c, solid=True), COLUMN)
        for i, prof in enumerate(SLEEVES):
            tag(bm, add_lathe(bm, prof, 36, NYLON_IDX, phase=math.pi / 36.0 * i), SLEEVE, i)

        # --- synchro-tilt mechanism
        tag(bm, add_lathe(bm, SOCKET_PROFILE, 32, STEEL_IDX, solid=True), SOCKET)
        mech = add_box(bm, MECH_C, MECH_SIZE, STEEL_IDX)
        tag(bm, mech, MECH)
        bevel_verts += mech
        tc = Vector(TILT_C)
        tag(bm, add_lathe(bm, [(0.012, -TILT_HALF), (TILT_R - 0.002, -TILT_HALF),
                               (TILT_R, -TILT_HALF + 0.002), (TILT_R, TILT_HALF - 0.002),
                               (TILT_R - 0.002, TILT_HALF), (0.012, TILT_HALF)], 24, STEEL_IDX,
                          center=tc, rot=frame_from(X_AX, Z_AX), solid=True), TILT)
        tag(bm, add_lathe(bm, KNOB_PROFILE, 36, NYLON_IDX, center=KNOB_C,
                          rot=frame_from(-Y_AX, X_AX), solid=True,
                          rmod=lambda i, j: 0.92 if (j in (2, 3) and i % 2) else 1.0), KNOB)
        for i, ctrl in enumerate(LEVERS):
            path = catmull([Vector(p) for p in ctrl], per=4)
            tag(bm, add_sweep(bm, path, circle_section(0.0042, 10), STEEL_IDX), LEVER, i)
            d = (path[-1] - path[-4]).normalized()
            paddle = add_lathe(bm, [(0.003, -0.006), (0.010, -0.002), (0.0125, 0.010),
                                    (0.0125, 0.030), (0.0090, 0.040), (0.0030, 0.043)], 20,
                               NYLON_IDX, center=path[-1], rot=frame_from(d, Z_AX), solid=True)
            c = path[-1]
            for v in paddle:
                off = v.co - c
                v.co = c + off - Z_AX * (off.z * 0.55)
            tag(bm, paddle, PADDLE, i)

        # --- seat shell, cushion and welts; back, spine, headrest; arms
        add_seat(bm)
        add_back(bm, FLOAT_LUMBAR if float_lumbar else 0.0)
        add_arm(bm, 0, UNEVEN_ARM if uneven_arms else 0.0)
        add_arm(bm, 1)

        if bevel_offset > 0.0:
            # Chamfer the mechanism housing and the caster webs, one pass per
            # material with material= set, over sorted edges (a set of BMEdges
            # iterates in memory order).
            for mat_idx, off in ((STEEL_IDX, 2.0 * bevel_offset), (NYLON_IDX, bevel_offset)):
                bm.edges.index_update()
                edges = sorted(
                    {e for v in bevel_verts if v.is_valid for e in v.link_edges
                     if len(e.link_faces) == 2
                     and all(f.material_index == mat_idx for f in e.link_faces)
                     and e.calc_face_angle() > math.radians(60.0)},
                    key=lambda e: e.index,
                )
                if edges:
                    bmesh.ops.bevel(bm, geom=edges, offset=off, segments=bevel_segments,
                                    profile=0.5, affect="EDGES", clamp_overlap=True,
                                    material=mat_idx)

        # the chair stands on the mat: wheels CHAIR_Z off the floor, which
        # leaves them MAT_SINK into the sheet
        for v in bm.verts:
            v.co.z += CHAIR_Z
        add_mat(bm, curl=curl_mat)
        add_plant(bm, FLOAT_LEAVES if float_leaves else 0.0)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z -= zmin
            if v.co.z < 0.0:
                v.co.z = 0.0

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # Everything moulded, turned or upholstered is smooth-shaded; chamfers,
        # knurls, seams and material boundaries stay crisp through sharp edges.
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(35.0)
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

def _set(bsdf, key, value):
    if key in bsdf.inputs:
        bsdf.inputs[key].default_value = value


def principled(name, color, metallic, roughness, roughness_var=0.0, mottle=0.0,
               noise_scale=14.0, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if coat > 0.0 and "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.1
    if roughness_var > 0.0 or mottle > 0.0:
        coord = nt.nodes.new("ShaderNodeTexCoord")
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = noise_scale
        noise.inputs["Detail"].default_value = 6.0
        nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
        if roughness_var > 0.0:
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            lo = max(0.05, roughness - roughness_var)
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
    surface = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].links \
        else bsdf.outputs["BSDF"]
    nt.links.new(surface, add.inputs[0])
    nt.links.new(em.outputs["Emission"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
    return mat


STUDIO_METAL = [(0.0, 0.03), (0.28, 0.08), (0.40, 0.55), (0.48, 1.0), (0.60, 0.35), (1.0, 0.20)]
STUDIO_SATIN = [(0.0, 0.02), (0.30, 0.04), (0.42, 0.40), (0.50, 1.0), (0.62, 0.30), (1.0, 0.12)]


def bands(nt, coord, axis, scale, profile="SIN", distortion=0.0):
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"
    wv.bands_direction = axis
    wv.wave_profile = profile
    wv.inputs["Scale"].default_value = scale
    wv.inputs["Distortion"].default_value = distortion
    nt.links.new(coord.outputs["Object"], wv.inputs["Vector"])
    return wv


def math_node(nt, op, a, b):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    for i, x in enumerate((a, b)):
        if isinstance(x, (int, float)):
            m.inputs[i].default_value = x
        else:
            nt.links.new(x, m.inputs[i])
    return m.outputs["Value"]


def woven(name, dark, light, weave_scale, bump_strength, heather_scale=160.0, sheen=0.5):
    """Upholstery: a heathered yarn tone over a plain weave. The weave is
    the product of crossed sine bands on two object axes (the third axis
    added in, so the sloped lumbar pad weaves too), carried mostly in the
    bump and a little in the tone. Undistorted: distorted bands read as
    wood grain."""
    mat = principled(name, light, 0.0, 0.82)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    heather = nt.nodes.new("ShaderNodeTexNoise")
    heather.inputs["Scale"].default_value = heather_scale
    heather.inputs["Detail"].default_value = 8.0
    nt.links.new(coord.outputs["Object"], heather.inputs["Vector"])
    bx = bands(nt, coord, "X", weave_scale)
    by = bands(nt, coord, "Y", weave_scale)
    bz = bands(nt, coord, "Z", weave_scale)
    warp = math_node(nt, "MULTIPLY", math_node(nt, "ADD", by.outputs["Fac"], bz.outputs["Fac"]),
                     0.5)
    cloth = math_node(nt, "MULTIPLY", bx.outputs["Fac"], warp)
    tone = math_node(nt, "ADD", math_node(nt, "MULTIPLY", heather.outputs["Fac"], 0.8),
                     math_node(nt, "MULTIPLY", cloth, 0.30))
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = light
    nt.links.new(tone, ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.0006
    nt.links.new(cloth, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    _set(bsdf, "Sheen Weight", sheen)
    return mat


def mesh_material():
    """Elastomeric mesh: horizontal elastomer ribs over fine vertical
    strands, open between them. The open cells are transparent, so the
    frame, spine and stage show through, and the ribs catch the light."""
    mat = principled("ChairMesh", (0.19, 0.19, 0.20, 1.0), 0.0, 0.48)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    ribs = math_node(nt, "GREATER_THAN", bands(nt, coord, "Z", MESH_RIB_SCALE).outputs["Fac"],
                     0.58)
    strands = math_node(nt, "GREATER_THAN",
                        bands(nt, coord, "X", MESH_STRAND_SCALE).outputs["Fac"], 0.55)
    solid = math_node(nt, "MAXIMUM", ribs, math_node(nt, "MULTIPLY", strands, 0.75))
    tone = nt.nodes.new("ShaderNodeMixRGB")
    tone.inputs["Color1"].default_value = (0.085, 0.086, 0.090, 1.0)
    tone.inputs["Color2"].default_value = (0.25, 0.25, 0.26, 1.0)
    nt.links.new(ribs, tone.inputs["Fac"])
    nt.links.new(tone.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    bump.inputs["Distance"].default_value = 0.0008
    nt.links.new(ribs, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    out = nt.nodes["Material Output"]
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    mixs = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(solid, mixs.inputs["Fac"])
    nt.links.new(transp.outputs["BSDF"], mixs.inputs[1])
    nt.links.new(bsdf.outputs["BSDF"], mixs.inputs[2])
    nt.links.new(mixs.outputs["Shader"], out.inputs["Surface"])
    return mat


MESH_RIB_SCALE = 42.0
MESH_STRAND_SCALE = 120.0


def leaf_material():
    """Sansevieria: dark green with the paler wavy cross-bands the plant is
    known by, waxy."""
    mat = principled("PlantLeaf", (0.030, 0.070, 0.034, 1.0), 0.0, 0.42, coat=0.25)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    wv = bands(nt, coord, "Z", 7.0, distortion=16.0)
    wv.inputs["Detail"].default_value = 4.0
    wv.inputs["Detail Scale"].default_value = 2.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.018, 0.044, 0.022, 1.0)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.050, 0.085, 0.042, 1.0)
    nt.links.new(wv.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def chair_materials():
    """Slot order: fabric, mesh, shell, nylon, aluminium, chrome, rubber,
    leatherette, steel, border, mat, ceramic, soil, leaf. Shared by the check
    and the render.

    The seat's centre panel and the lumbar pad are a muted-teal woven
    upholstery, the seat's side panels a mid-grey knit; the back and
    headrest are a grey elastomeric mesh in graphite frames; the seat shell,
    arm plates and covers are graphite plastic with a satin sheen; the
    casters, hub, posts, sliders and sleeves black nylon; the star, spine,
    headrest stem and arm brackets polished aluminium; the column, stems,
    axles and buttons chrome; the treads grey polyurethane; the arm pads and
    welts black leatherette; the mechanism graphite-painted steel. The mat is
    a smoked polycarbonate sheet; the pot a speckled stone ceramic.
    """
    fabric = woven("ChairFabric", (0.060, 0.105, 0.120, 1.0), (0.150, 0.250, 0.275, 1.0),
                   110.0, 0.35)
    mesh = mesh_material()
    shell = principled("ChairShell", (0.040, 0.041, 0.045, 1.0), 0.0, 0.36,
                       roughness_var=0.05, mottle=0.08, noise_scale=40.0)
    add_studio(shell, (0.55, 0.57, 0.62, 1.0), 0.10, STUDIO_SATIN)
    nylon = principled("ChairNylon", (0.022, 0.022, 0.025, 1.0), 0.0, 0.42,
                       roughness_var=0.08, noise_scale=70.0)
    add_studio(nylon, (0.55, 0.57, 0.62, 1.0), 0.05, STUDIO_SATIN)
    alu = principled("ChairAluminium", (0.88, 0.89, 0.91, 1.0), 1.0, 0.20,
                     roughness_var=0.05, noise_scale=120.0)
    add_studio(alu, (0.80, 0.81, 0.83, 1.0), 0.60, STUDIO_METAL)
    chrome = principled("ChairChrome", (0.93, 0.93, 0.95, 1.0), 1.0, 0.07)
    add_studio(chrome, (0.90, 0.90, 0.92, 1.0), 0.80, STUDIO_METAL)
    rubber = principled("ChairTread", (0.115, 0.115, 0.12, 1.0), 0.0, 0.62,
                        roughness_var=0.06, noise_scale=90.0)
    leather = principled("ChairLeatherette", (0.030, 0.029, 0.029, 1.0), 0.0, 0.38,
                         roughness_var=0.10, mottle=0.25, noise_scale=260.0)
    steel = principled("ChairSteel", (0.060, 0.062, 0.068, 1.0), 0.6, 0.42,
                       roughness_var=0.08, noise_scale=60.0)
    add_studio(steel, (0.55, 0.60, 0.68, 1.0), 0.14, STUDIO_SATIN)
    border = woven("ChairBorderFabric", (0.045, 0.047, 0.052, 1.0), (0.105, 0.108, 0.116, 1.0),
                   200.0, 0.25, heather_scale=300.0, sheen=0.3)
    mat = principled("MatPolycarbonate", (0.050, 0.053, 0.058, 1.0), 0.0, 0.32,
                     roughness_var=0.08, noise_scale=8.0, coat=0.25)
    add_studio(mat, (0.55, 0.57, 0.62, 1.0), 0.05, STUDIO_SATIN)
    ceramic = principled("PotCeramic", (0.200, 0.192, 0.180, 1.0), 0.0, 0.64,
                         roughness_var=0.08, mottle=0.35, noise_scale=320.0)
    soil = principled("PotSoil", (0.034, 0.025, 0.018, 1.0), 0.0, 0.94,
                      mottle=0.45, noise_scale=180.0)
    leaf = leaf_material()
    return (fabric, mesh, shell, nylon, alu, chrome, rubber, leather, steel, border, mat,
            ceramic, soil, leaf)


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
    # sweep along u: only pairs whose u spans overlap are compared
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
    def __init__(self, me, idx, verts, polys, part_attr):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.mean = sum(pts, Vector()) / len(pts)
        mats, tags = {}, {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
            t = part_attr[p.index].value
            tags[t] = tags.get(t, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        tg = max(tags, key=tags.get) if tags else 0
        self.kind, self.part = tg // 100, tg % 100
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.down = [p.normal.z < -0.99 for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)


def classify(me):
    groups = shells(me)
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(p)
    attr = me.attributes["part"].data
    parts = [Shell(me, i, g, polys[i], attr) for i, g in enumerate(groups)]
    by = {}
    for s in parts:
        by.setdefault(s.kind, []).append(s)
    for v in by.values():
        v.sort(key=lambda s: s.part)
    chair = [s for s in parts if s.kind not in VIGNETTE_KINDS]
    return {"all": parts, "chair": chair, "groups": groups, "by": by}


def slab_axis(s, frac_=0.1):
    """Axis of a turned part from the XY centroids of its bottom and top slabs."""
    z0 = s.lo.z + frac_ * s.size.z
    z1 = s.hi.z - frac_ * s.size.z
    bot = [p for p in s.pts if p.z <= z0]
    top = [p for p in s.pts if p.z >= z1]
    a = sum(bot, Vector()) / len(bot)
    b = sum(top, Vector()) / len(top)
    return a, (b - a).normalized()


def axis_at(origin, direction, z):
    t = (z - origin.z) / direction.z
    return origin + direction * t


def tilt_deg(direction):
    return math.degrees(math.acos(min(1.0, abs(direction.z))))


def surface_below(tree, x, y, z_from):
    """Height of a shell's surface straight below (x, y), by a ray cast on
    that shell's own tree; None when the ray misses it."""
    hit = tree.ray_cast(Vector((x, y, z_from)), Vector((0.0, 0.0, -1.0)))
    return None if hit[0] is None else hit[0].z


def support_audit(by):
    """Named supports: the mat's underside flat on the floor, every wheel
    pressed into the mat under it, the pot on the floor."""
    out = {}
    mats = by.get(MAT, [])
    pots = by.get(POT, [])
    wheels = by.get(WHEEL, [])
    out["mats"], out["pots"], out["wheels"] = len(mats), len(pots), len(wheels)
    if len(mats) != 1 or len(pots) != 1:
        return out
    mat = mats[0]
    under = set()
    for tri, down in zip(mat.tri_idx, mat.down):
        if down:
            under.update(tri)
    out["mat_under_n"] = len(under)
    out["mat_under_z"] = max(mat.pts[i].z for i in under) if under else 9.0
    sinks = []
    for w in wheels:
        low = min(w.pts, key=lambda p: p.z)
        top = surface_below(mat.tree, low.x, low.y, low.z + 0.05)
        sinks.append(-9.0 if top is None else top - low.z)
    out["wheel_sink"] = (min(sinks), max(sinks)) if sinks else (0.0, 0.0)
    out["pot_z"] = pots[0].lo.z
    return out


def star_audit(by):
    """Spoke and boss bearings 72 degrees apart; bosses and stems on one
    circle; stems plumb, coaxial with their bosses and seated in them."""
    spokes, bosses, stems = by.get(SPOKE, []), by.get(BOSS, []), by.get(STEM, [])
    out = {"spokes": len(spokes), "bosses": len(bosses), "stems": len(stems)}
    if not (len(spokes) == len(bosses) == len(stems) == SPOKES):
        return out
    worst = 0.0
    for group in (spokes, bosses):
        b = sorted(math.degrees(math.atan2(s.mean.y, s.mean.x)) % 360.0 for s in group)
        gaps = [(b[(i + 1) % SPOKES] - b[i]) % 360.0 for i in range(SPOKES)]
        worst = max(worst, max(abs(g - 360.0 / SPOKES) for g in gaps))
    out["spacing"] = worst
    br = [math.hypot(s.mean.x, s.mean.y) for s in bosses]
    out["boss_r"] = (min(br), max(br))
    tilts, coax, seats, sr = [], [], [], []
    for stem, boss in zip(stems, bosses):
        o, d = slab_axis(stem)
        tilts.append(tilt_deg(d))
        p = axis_at(o, d, boss.mean.z)
        coax.append(math.hypot(p.x - boss.mean.x, p.y - boss.mean.y))
        seats.append(stem.hi.z - boss.lo.z)
        sr.append(math.hypot(o.x, o.y))
    out["stem_tilt"] = max(tilts)
    out["stem_coax"] = max(coax)
    out["stem_seat"] = (min(seats), max(seats))
    out["stem_r"] = (min(sr), max(sr))
    out["star_d"] = 2.0 * sum(max(math.hypot(p.x, p.y) for p in s.pts) for s in bosses) / SPOKES
    return out


def column_audit(by):
    cols, hubs, sockets = by.get(COLUMN, []), by.get(HUB, []), by.get(SOCKET, [])
    if not (len(cols) == len(hubs) == len(sockets) == 1):
        return None
    col, hub, sock = cols[0], hubs[0], sockets[0]
    o, d = slab_axis(col)
    ph = axis_at(o, d, hub.mean.z)
    ps = axis_at(o, d, sock.mean.z)
    return {"coax_hub": math.hypot(ph.x - hub.mean.x, ph.y - hub.mean.y),
            "coax_socket": math.hypot(ps.x - sock.mean.x, ps.y - sock.mean.y),
            "tilt": tilt_deg(d), "hub_bite": hub.hi.z - col.lo.z,
            "socket_bite": col.hi.z - sock.lo.z}


def shell_mass(s):
    """Volume and centroid of one closed shell (divergence theorem over a
    fan triangulation of its faces)."""
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
    """Armrests mirrored and level; seat, armrest and star sizes; the
    chair's mass centre inside the polygon of the wheels' contacts."""
    by = cls["by"]
    out = {}
    worst = 0.0
    pairs = 0
    for kind in ARM_KINDS:
        group = by.get(kind, [])
        right = [s for s in group if s.part == 0]
        left = [s for s in group if s.part == 1]
        if len(right) != 1 or len(left) != 1:
            return None
        r, lft = right[0], left[0]
        pairs += 1
        worst = max(worst, abs(r.lo.x + lft.hi.x), abs(r.hi.x + lft.lo.x),
                    abs(r.lo.y - lft.lo.y), abs(r.hi.y - lft.hi.y),
                    abs(r.lo.z - lft.lo.z), abs(r.hi.z - lft.hi.z))
    out["arm_pairs"] = pairs
    out["arm_mirror"] = worst
    cushion = by.get(CUSHION, [])
    if len(cushion) != 1:
        return None
    out["seat_h"] = cushion[0].hi.z
    out["arm_over"] = min(s.hi.z for s in by[ARMPAD]) - cushion[0].hi.z
    total = 0.0
    mom = Vector()
    for s in cls["chair"]:
        if s.mat is None:
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * DENSITY[s.mat]
        total += m
        mom += m * cen
    com = mom / total
    contacts = []
    for w in by.get(WHEEL, []):
        contacts += [(p.x, p.y) for p in w.pts if p.z <= w.lo.z + 1e-4]
    hull = hull2d(contacts)
    margin = 9.0
    for i in range(len(hull)):
        ax, ay = hull[i]
        bx, by_ = hull[(i + 1) % len(hull)]
        ex, ey = bx - ax, by_ - ay
        ln = math.hypot(ex, ey)
        # counter-clockwise hull: inside is to the left of every edge
        margin = min(margin, (ex * (com.y - ay) - ey * (com.x - ax)) / ln)
    out.update({"mass": total, "com": com, "margin": margin, "hull_n": len(hull)})
    return out


def connected_components(parts):
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
    return len(roots), sorted(sizes.values())


def lumbar_audit(by):
    """Each slider hugs the frame tube it rides on: every slider vertex a
    banded distance off the frame's surface, all round."""
    sliders, frames = by.get(SLIDER, []), by.get(FRAME, [])
    if len(sliders) != 2 or len(frames) != 1:
        return None
    frame = frames[0]
    gaps = []
    for s in sliders:
        d = [(frame.tree.find_nearest(p)[0] - p).length for p in s.pts]
        gaps.append((min(d), max(d)))
    return {"sliders": len(sliders), "gap": (min(g[0] for g in gaps), max(g[1] for g in gaps))}


def leaf_audit(by):
    """Every leaf's base buried in the soil to a banded depth, measured
    against the soil's own surface straight above it, and inside the pot."""
    leaves, soils = by.get(LEAF, []), by.get(SOIL, [])
    if len(soils) != 1:
        return None
    soil = soils[0]
    axis = Vector((0.5 * (soil.lo.x + soil.hi.x), 0.5 * (soil.lo.y + soil.hi.y), 0.0))
    soil_r = 0.5 * max(soil.size.x, soil.size.y)
    depths, reach = [], []
    for lf in leaves:
        base = [p for p in lf.pts if p.z <= lf.lo.z + 0.002]
        b = sum(base, Vector()) / len(base)
        top = surface_below(soil.tree, b.x, b.y, soil.hi.z + 0.05)
        depths.append(-9.0 if top is None else top - lf.lo.z)
        reach.append(max(math.hypot(p.x - axis.x, p.y - axis.y) for p in base))
    return {"leaves": len(leaves), "depth": (min(depths), max(depths)) if depths else (0, 0),
            "wall_clear": soil_r - max(reach) if reach else -9.0}


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        # inside the envelope, so only the hygiene budget can see it
        bm.verts.new((0.0, 0.0, 0.6))
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
        interior = result.get("geom_interior") or []
        unused = result.get("geom_unused") or []
        if interior:
            bmesh.ops.delete(bm, geom=interior, context="VERTS")
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
    img = bpy.data.images.new("ChairNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = STEEL_IDX
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


def _r(v):
    return tuple(round(x, 5) for x in v) if isinstance(v, tuple) else round(v, 5)


def check(skip_decimate, lift_z=False, stray_vert=False, float_caster=False, skew_spoke=False,
          offset_column=False, uneven_arms=False, loose_wheel=False, float_lumbar=False,
          curl_mat=False, float_leaves=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(skew_spoke=skew_spoke, float_caster=float_caster, offset_column=offset_column,
                 uneven_arms=uneven_arms, loose_wheel=loose_wheel, float_lumbar=float_lumbar,
                 curl_mat=curl_mat, float_leaves=float_leaves)
    low = build_chair_mesh("ChairLow", bevel_offset=0.0008, bevel_segments=1, **flags)
    high = build_chair_mesh("ChairHigh", bevel_offset=0.0008, bevel_segments=3, **flags)
    mats = chair_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the mechanism's painted steel: its housing is where
    # the high mesh's rounder chamfer differs most from the low.
    steel = mats[STEEL_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none1 = (None,)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("chair mesh did not build", 3),) + none1

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
    sup = support_audit(cls["by"])
    star = star_audit(cls["by"])
    column = column_audit(cls["by"])
    stance = stance_audit(cls)
    ncomp, comp_sizes = connected_components(cls["chair"])
    lumbar = lumbar_audit(cls["by"])
    leaves = leaf_audit(cls["by"])

    img, tex = setup_bake_image(low, steel)
    if img is None:
        return (fail("chair has no UV layer", 3),) + none1
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "ChairLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "ChairLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_chair_mesh("ChairColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "ChairCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_office_chair_{os.getpid()}.glb")
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
          f"outer={OUTER_SIZE} zmin={bb[2]:.4f} min=({bb[0]:.4f},{bb[1]:.4f}) "
          f"max=({bb[3]:.4f},{bb[4]:.4f})")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured shells={len(cls['all'])} chair_shells={len(cls['chair'])} "
          f"supports={ {k: _r(v) for k, v in sup.items()} }")
    print(f"measured star={ {k: _r(v) for k, v in star.items()} }")
    if column:
        print(f"measured column coax_hub={column['coax_hub']:.6f} "
              f"coax_socket={column['coax_socket']:.6f} tilt={column['tilt']:.4f} "
              f"hub_bite={column['hub_bite']:.4f} socket_bite={column['socket_bite']:.4f}")
    if stance:
        print(f"measured arm_pairs={stance['arm_pairs']} arm_mirror={stance['arm_mirror']:.6f} "
              f"seat_h={stance['seat_h']:.4f} arm_over={stance['arm_over']:.4f} "
              f"mass={stance['mass']:.2f}kg com=({stance['com'].x:.4f},{stance['com'].y:.4f},"
              f"{stance['com'].z:.4f}) margin={stance['margin']:.4f} hull_n={stance['hull_n']}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")
    if lumbar:
        print(f"measured lumbar sliders={lumbar['sliders']} gap={_r(lumbar['gap'])}")
    if leaves:
        print(f"measured leaves={leaves['leaves']} depth={_r(leaves['depth'])} "
              f"wall_clear={leaves['wall_clear']:.4f}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none1
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none1
    for idx, (label, floor) in enumerate(FACE_FLOORS):
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{label} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + none1
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + none1
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + none1
    if (abs(size_x - OUTER_SIZE[0]) > BBOX_TOL or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
            or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL):
        return (fail(f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8),) + none1
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
                     "(--skip-decimate is the designed fail)", 9),) + none1
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9),) + none1
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + none1
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + none1
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + none1
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf}", 15),) + none1
    if bb[2] > ZMIN_EPS:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none1
    if sup["mats"] != 1 or sup["pots"] != 1:
        return (fail(f"supports: {sup['mats']} mats, {sup['pots']} pots (want 1 and 1)", 16),) + none1
    if sup["mat_under_z"] > MAT_FLAT_EPS:
        return (fail(f"mat not flat on the floor: underside rises to {sup['mat_under_z']:.5f} "
                     f"> {MAT_FLAT_EPS}", 16),) + none1
    if (sup["wheels"] != WHEEL_COUNT or not (WHEEL_SINK[0] <= sup["wheel_sink"][0]
                                             and sup["wheel_sink"][1] <= WHEEL_SINK[1])):
        return (fail(f"wheels: {sup['wheels']} (want {WHEEL_COUNT}), pressed into the mat "
                     f"{_r(sup['wheel_sink'])} outside {WHEEL_SINK}", 16),) + none1
    if sup["pot_z"] > ZMIN_EPS:
        return (fail(f"pot off the floor: {sup['pot_z']:.5f}", 16),) + none1
    if ("spacing" not in star or star["spacing"] > SPACING_TOL_DEG
            or star["boss_r"][1] - star["boss_r"][0] > RADIUS_RANGE_MAX
            or star["stem_r"][1] - star["stem_r"][0] > RADIUS_RANGE_MAX
            or star["stem_tilt"] > STEM_TILT_MAX_DEG or star["stem_coax"] > STEM_COAX_MAX
            or not (STEM_SEAT[0] <= star["stem_seat"][0] and star["stem_seat"][1] <= STEM_SEAT[1])):
        return (fail(f"five-star geometry: {star}", 17),) + none1
    if (column is None or column["coax_hub"] > COLUMN_COAX_MAX
            or column["coax_socket"] > COLUMN_COAX_MAX or column["tilt"] > COLUMN_TILT_MAX_DEG
            or not (HUB_BITE[0] <= column["hub_bite"] <= HUB_BITE[1])
            or not (SOCKET_BITE[0] <= column["socket_bite"] <= SOCKET_BITE[1])):
        return (fail(f"gas lift not coaxial or not seated: {column}", 18),) + none1
    if (stance is None or stance["arm_pairs"] != len(ARM_KINDS)
            or stance["arm_mirror"] > ARM_MIRROR_EPS
            or not (SEAT_HEIGHT[0] <= stance["seat_h"] <= SEAT_HEIGHT[1])
            or not (ARM_OVER_SEAT[0] <= stance["arm_over"] <= ARM_OVER_SEAT[1])
            or abs(star["star_d"] - STAR_DIAMETER) > STAR_TOL
            or stance["margin"] < STANCE_MARGIN):
        return (fail(f"stance and size: {stance}, star diameter {star.get('star_d')}", 19),) + none1
    if ncomp != 1:
        return (fail(f"chair splits into {ncomp} components {comp_sizes}", 20),) + none1
    if (lumbar is None or not (SLIDER_GAP[0] <= lumbar["gap"][0]
                               and lumbar["gap"][1] <= SLIDER_GAP[1])):
        return (fail(f"lumbar sliders not clamped on the frame: {lumbar} (band {SLIDER_GAP})",
                     21),) + none1
    if (leaves is None or leaves["leaves"] != LEAF_COUNT
            or not (LEAF_DEPTH[0] <= leaves["depth"][0] and leaves["depth"][1] <= LEAF_DEPTH[1])
            or leaves["wall_clear"] < LEAF_WALL_CLEAR):
        return (fail(f"leaves not rooted in the soil: {leaves} (depth band {LEAF_DEPTH}, "
                     f"wall clear >= {LEAF_WALL_CLEAR})", 22),) + none1
    return 0, low


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
    floor.location.z = -0.001
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

    # The house rig scaled to the vignette: warm key upper left, cool fill
    # low right, cool rim behind, warm wedge pooled on the back wall.
    for name, offset, energy, size, col, target, spread in LIGHTS:
        light(name, offset, energy, size, col,
              None if target is None else centre + Vector(target), spread)

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


# (name, offset from the vignette centre, energy, size, colour, target
# offset or None for the centre, spread)
LIGHTS = (
    ("Key", (-2.4, -2.9, 2.6), 118.0, 1.4, (1.0, 0.95, 0.90), None, 28.0),
    ("Fill", (3.0, -2.0, 0.6), 18.0, 3.4, (0.72, 0.82, 1.0), None, None),
    ("Rim", (-1.0, 1.8, 1.6), 80.0, 1.2, (0.62, 0.78, 1.0), None, None),
    ("Wedge", (3.0, 1.6, 1.6), 140.0, 2.0, (1.0, 0.68, 0.38), (3.2, WALL_Y - 0.9, -0.66), None),
)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--float-caster", action="store_true")
    p.add_argument("--curl-mat", action="store_true")
    p.add_argument("--skew-spoke", action="store_true")
    p.add_argument("--offset-column", action="store_true")
    p.add_argument("--uneven-arms", action="store_true")
    p.add_argument("--loose-wheel", action="store_true")
    p.add_argument("--float-lumbar", action="store_true")
    p.add_argument("--float-leaves", action="store_true")
    args = p.parse_args(argv)

    code, low = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_caster=args.float_caster,
        skew_spoke=args.skew_spoke,
        offset_column=args.offset_column,
        uneven_arms=args.uneven_arms,
        loose_wheel=args.loose_wheel,
        float_lumbar=args.float_lumbar,
        curl_mat=args.curl_mat,
        float_leaves=args.float_leaves,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("office-chair OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
