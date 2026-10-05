"""Game-ready court-side basketball hoop — a showcase piece, not an example.

Asserts budget conformance of a procedural in-ground basketball goal on a
patch of court after composing shipped pipeline pieces: bmesh construction,
UVs, twelve materials, high-to-low normal bake, LOD chain, convex collider,
Unity glTF export.

The hoop stands on a two-pour concrete pad split by a sealed expansion
joint. Its 6 in square steel pole is one sweep from a sunk base plate
(four anchor bolts set into the slab, four gussets) through an S-shaped
gooseneck with a welded gusset web in each bend, up into the mast behind
the board. The mast carries the board through two bolted clamp sleeves,
standoffs and a back rail frame; two diagonal braces run from a collar on
the pole to the lower rail. The pole wears a square pad with seam grooves
and a hook-and-loop closing flap. The board sits in an aluminium frame
with a navy bottom edge pad, a painted border and shooter's square.

The rim is a regulation ring — 0.457 m inside diameter, top 3.05 m above
the court, inner edge 0.151 m off the board face — on a breakaway mount:
tapered bracket, hinge barrel and spring housing, bolted through a flange
plate, with twelve welded net hooks. The net is twelve cord loops hung on
those hooks, 24 laid strands that cross in a tapered diamond mesh, and a
knot at every crossing.

The court carries a painted driveway layout in faded paint (baseline, a
filled key with lane marks, free-throw line and circle, part of a
three-point arc); every line is sunk into its own slab and stands proud of
it. Two pebbled basketballs with black seams rest on the concrete.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-brace`` brace bite,
``--drop-net`` net loops threaded on the rim hooks, ``--tilt-rim`` rim
height / level / size / projection, ``--float-ball`` ball resting on the
slab at its radius, ``--short-bolts`` anchor bolts through the plate into
the slab, ``--float-paint`` court paint set into the slab, ``--loose-pad``
one connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python basketball_hoop.py --
    blender --background --python basketball_hoop.py -- --skip-decimate
    blender --background --python basketball_hoop.py -- --output hoop.png
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
from mathutils import Euler, Matrix, Vector
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

# Hoop coordinates: z = 0 is the court surface (the top of slab A), the pole
# axis is x = y = 0 and the board faces +y, over the court. The hoop is
# lifted onto the slab (SLAB_T) once it is built.

# --- Court pad -------------------------------------------------------------
SLAB_T = 0.10
SLAB_X = (-2.6, 2.6)
SLAB_Y = (-0.7, 5.9)
JOINT_Y = 2.9            # expansion joint between the two pours
JOINT_GAP = 0.012
JOINT_BITE = 0.003       # sealant strip bears into both slab edges
SEAL_DROP = 0.004        # sealant sits below the lower slab's top
SLAB_B_DROP = 0.0015     # the second pour settles a little under the first

# --- Court paint (a driveway layout, not regulation) -------------------------
LINE_W = 0.050
BASELINE_Y = 0.40
LANE_HALF = 1.35
FT_Y = 4.20              # free-throw line, 2.98 m from the board face
FT_R = LANE_HALF + 0.006  # circle clear of the lane lines' side faces
ARC_R = 4.20             # three-point arc about the basket centre
LINE_END = 0.008         # paint stops short of the joint gap and slab edges
EDGE_CLEAR = 0.03
HASH_Y = (1.95, 2.55, 3.45, 3.95)
HASH_LEN = 0.15
BLOCK_W = 0.20
# (top above host slab, sink below it) per paint group: overlapping groups
# never share a top or bottom plane
BASELINE_H = (0.0022, 0.0026)
LANE_H = (0.0018, 0.0020)
FTLINE_H = (0.0022, 0.0026)
FILL_H = (0.0010, 0.0014)
HASH_H = (0.0014, 0.0030)
FTCIRC_H = (0.0014, 0.0030)
ARC_H = (0.0018, 0.0020)
PAINT_SHELLS = 18

# --- Basketballs -----------------------------------------------------------
BALL_R = 0.1194          # size 7: 29.5 in circumference
BALL_SINK = 0.0020       # contact flat: the ball bears 2 mm into the slab
SEAM_R = 0.0032
SEAM_SINK = 0.0020       # seam cord centre under the ball surface
SEAM_PARALLEL = 0.60     # curved seams: planes at +/- this x R off centre
BALLS = (
    # (x, y, seam orientation) in hoop coordinates
    (2.05, 3.30, (0.55, 0.25, 0.40)),
    (-0.36, 0.20, (1.10, -0.35, 0.90)),
)

# --- Base plate: sunk into the slab, bolted through -------------------------
BASE_W = 0.46
BASE_T = 0.025
PLATE_SINK = 0.004       # plate bottom below the court surface
ANCHOR_XY = 0.180
ANCHOR_R = 0.011
ANCHOR_TOP = BASE_T + 0.062
ANCHOR_EMBED = 0.070     # anchor bolt depth under the court surface
WASHER_R = 0.026
NUT_R = 0.0195
GUSSET_T = 0.012
GUSSET_REACH = 0.110
GUSSET_H = 0.165
GUSSET_BITE = 0.004

# --- Pole: one square sweep from plate to mast top ---------------------------
POLE_HALF = 0.0762       # 6 in square pole
CORNER_R = 0.014
CORNER_PTS = 4
POLE_SEAT = 0.008
GOOSE_Z = 1.75
GOOSE_BEND_R = 0.45
GOOSE_ANGLE = math.radians(60.0)
GOOSE_STEPS = 9
MAST_TOP = 3.80
BEND_WEB_T = 0.014       # gusset web welded into the inside of each bend
BEND_WEB_LEG = 0.25
BEND_WEB_BITE = 0.004

# --- Board, frame and back rails ------------------------------------------
BOARD_FACE_Y = 1.22     # pole axis to board face: 48 in overhang
BOARD_T = 0.030
BOARD_W = 1.83          # regulation 6 ft x 3.5 ft, frame included
BOARD_H = 1.05
BOARD_BOT = 2.90
FRAME_W = 0.050
FRAME_PROUD = 0.014
FRAME_BACK = 0.014
PANEL_INSET = 0.022
EDGE_PAD_T = 0.024
EDGE_PAD_REVEAL = 0.008
RAIL_D = 0.050
RAIL_H = 0.050
RAIL_W = 1.30
RAIL_BITE = 0.003
RAIL_Z = (3.08, 3.72)
STILE_X = 0.24
STANDOFF = 0.10
STANDOFF_S = 0.070
CLAMP_H = 0.100
CLAMP_T = 0.016
CLAMP_BOLT_R = 0.012

# --- Board paint -------------------------------------------------------------
BOARD_LINE_W = 0.050
BORDER_W = 0.044         # border inner edge clear of the square's bottom line
BORDER_PROUD = 0.0008
SQUARE_PROUD = 0.0012
PAINT_SINK = 0.001
SQUARE_W = 0.59
SQUARE_H = 0.45

# --- Rim (regulation) on a breakaway mount -----------------------------------
RIM_TOP = 3.05
RIM_ID = 0.457
RIM_GAP = 0.151         # board face to the ring's inside edge
RING_R = 0.008
RING_SEGS = 48
FLANGE_W = 0.19
FLANGE_H = 0.17
FLANGE_T = 0.014
FLANGE_SINK = 0.002
BOLT_R = 0.011
STRUT_R = 0.006
STRUT_ANGLE = math.radians(30.0)
HINGE_R = 0.013
HINGE_HALF = 0.072
NET_HOOKS = 12
HOOK_MAJOR = 0.012
HOOK_MINOR = 0.0025
HOOK_BITE = 0.003

# --- Net -------------------------------------------------------------------
CORD_R = 0.004
NET_LOOP_R = 0.014
NET_LOOP_BITE = 0.0015  # loop cord bears into the hook's lower inside
NET_ROWS = 6
NET_LEN = 0.40
NET_BOT_R = 0.145
NET_STRAND_SIDES = 5
KNOT_OFFSET = 0.6       # strand centres sit +/- this x CORD_R off the knot
KNOT_R = 2.0 * CORD_R

# --- Pad and brace collar --------------------------------------------------
PAD_Z = (0.21, 1.24)
PAD_T = 0.038
PAD_GRIP = 0.003
FLAP_W = 0.060
FLAP_T = 0.004
FLAP_SINK = 0.002
COLLAR_Z = 1.36
COLLAR_H = 0.080
COLLAR_T = 0.016
BRACE_R = 0.022
BRACE_X = 0.55

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (5.200, 6.600, 4.050)
BASE_TRIS_MIN = 18500
BASE_TRIS_MAX = 20500
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 12
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 220
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
FACE_FLOORS = {}  # filled below, after the slot indices

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Each brace end must bite into its host: deepest brace vertex inside the
# collar, and inside the lower rail (signed distance to that shell).
BRACE_BITE_MIN = 0.006
SHORT_BRACE = 0.06
# A net loop is hung on its hook when the loop's cord circle passes through
# the hook eye: distance from the eye centre to the loop's centre circle is
# under the eye's clear radius. Dropped 25 mm, every loop hangs free.
NET_THREAD_MAX = 0.009
DROP_NET = 0.025
# Real-world rim: top 3.05 m over the court, 0.457 m inside, inner edge
# 0.151 m off the board face, and level.
RIM_TOP_TOL = 0.010
RIM_ID_TOL = 0.004
RIM_GAP_TOL = 0.005
RIM_TILT_MAX_DEG = 0.5
TILT_RIM_DEG = 3.0
LOOSE_PAD = 0.006
# A ball rests on its slab: fitted radius at the size-7 radius, and its
# lowest point 0.5-4 mm into the slab top it stands on (a contact flat,
# neither floating nor swallowed).
BALL_R_TOL = 0.002
BALL_SINK_MIN = 0.0005
BALL_SINK_MAX = 0.004
FLOAT_BALL = 0.020
# Anchor bolts pass through the plate into the slab: each bolt's foot at
# least 50 mm under the court surface, its head 30 mm or more above the
# plate. Shortened, the bolts stop inside the plate.
ANCHOR_EMBED_MIN = 0.050
ANCHOR_PROUD_MIN = 0.030
# Court paint is set into its own slab: every paint shell's top stands
# 0.5-3 mm proud of the slab it lies on, and its bottom is 1-4 mm under it.
PAINT_TOP_BAND = (0.0005, 0.0030)
PAINT_SINK_BAND = (0.0010, 0.0040)
FLOAT_PAINT = 0.006
# Hero yaw: the board faces the camera from ~40 degrees off its normal so
# the gooseneck's S reads in profile and the key runs toward the camera.
HERO_YAW_DEG = -172.0
CAM_VIEW = (-0.55, -0.77)
CAM_DIST = 20.0
CAM_LENS = 70.0
CAM_LIFT = 1.6
AIM_OFFSET = (0.0, 0.0, -0.45)
WALL_Y = 11.0

STEEL_IDX = 0
BOARD_IDX = 1
PAINT_IDX = 2
RIM_IDX = 3
NET_IDX = 4
PAD_IDX = 5
ALU_IDX = 6
CONCRETE_IDX = 7
LINE_IDX = 8
KEY_IDX = 9
BALL_IDX = 10
SEAM_IDX = 11

FACE_FLOORS.update({
    STEEL_IDX: ("steel", 2200), BOARD_IDX: ("board", 45), PAINT_IDX: ("paint", 28),
    RIM_IDX: ("rim", 850), NET_IDX: ("net", 2400), PAD_IDX: ("pad", 330),
    ALU_IDX: ("alu", 120), CONCRETE_IDX: ("concrete", 90), LINE_IDX: ("line", 440),
    KEY_IDX: ("key", 12), BALL_IDX: ("ball", 900), SEAM_IDX: ("seam", 2000),
})


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


def add_box(bm, loc, scale, mat_idx):
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = geo["verts"]
    origin = Vector(loc)
    for v in verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])) + origin
    _mark({f for v in verts for f in v.link_faces}, mat_idx)
    return list(verts)


def add_span_box(bm, x0, x1, y0, y1, z0, z1, mat_idx):
    return add_box(bm, (0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1)),
                   (x1 - x0, y1 - y0, z1 - z0), mat_idx)


def add_hexahedron(bm, pts, mat_idx):
    """Closed six-sided solid from 8 corners: 0-3 one end, 4-7 the other,
    both ends wound the same way."""
    v = [bm.verts.new(Vector(p)) for p in pts]
    quads = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    _mark([bm.faces.new([v[i] for i in q]) for q in quads], mat_idx)
    return v


def add_rect_frame(bm, cx, cz, y0, y1, ow, oh, iw, ih, mat_idx):
    """Rectangular annulus in the XZ plane, extruded from y0 to y1: one
    closed shell (a picture frame), never four boxes sharing faces."""
    outer = [(-ow / 2, -oh / 2), (ow / 2, -oh / 2), (ow / 2, oh / 2), (-ow / 2, oh / 2)]
    inner = [(-iw / 2, -ih / 2), (iw / 2, -ih / 2), (iw / 2, ih / 2), (-iw / 2, ih / 2)]
    o = {y: [bm.verts.new((cx + x, y, cz + z)) for x, z in outer] for y in (y0, y1)}
    n = {y: [bm.verts.new((cx + x, y, cz + z)) for x, z in inner] for y in (y0, y1)}
    faces = []
    for i in range(4):
        j = (i + 1) % 4
        faces.append(bm.faces.new((o[y0][i], o[y0][j], n[y0][j], n[y0][i])))
        faces.append(bm.faces.new((o[y1][j], o[y1][i], n[y1][i], n[y1][j])))
        faces.append(bm.faces.new((o[y0][j], o[y0][i], o[y1][i], o[y1][j])))
        faces.append(bm.faces.new((n[y0][i], n[y0][j], n[y1][j], n[y1][i])))
    _mark(faces, mat_idx)
    return o[y0] + o[y1] + n[y0] + n[y1]


def add_prism_x(bm, profile, x0, x1, mat_idx):
    """Closed convex (y, z) polygon extruded along X from x0 to x1."""
    a = [bm.verts.new((x0, y, z)) for y, z in profile]
    b = [bm.verts.new((x1, y, z)) for y, z in profile]
    n = len(profile)
    faces = [bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i])) for i in range(n)]
    faces.append(bm.faces.new(tuple(reversed(a))))
    faces.append(bm.faces.new(tuple(b)))
    _mark(faces, mat_idx)
    return a + b


def _revolve(bm, rings, closed_profile, mat_idx):
    """Faces between ``rings`` (one list per section station, each list over
    the profile). ``closed_profile`` False caps both profile ends."""
    segs = len(rings)
    n = len(rings[0])
    faces = []
    last = n if closed_profile else n - 1
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for j in range(last):
            k = (j + 1) % n
            faces.append(bm.faces.new((r0[j], r1[j], r1[k], r0[k])))
    if not closed_profile:
        faces.append(bm.faces.new([rings[i][0] for i in reversed(range(segs))]))
        faces.append(bm.faces.new([rings[i][n - 1] for i in range(segs)]))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: the profile
    is an open polyline closed by n-gon caps at its two ends; otherwise it
    is a closed polygon revolved into a ring shell."""
    c = Vector(center)
    m = rot if rot is not None else Matrix.Identity(3)
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new(c + m @ Vector((r * ca, r * sa, z))) for r, z in profile])
    return _revolve(bm, rings, not solid, mat_idx)


def rsq(half, off):
    """Rounded square of half-width ``half`` offset outward by ``off``:
    corner centres fixed, so every offset is a true parallel of the pole."""
    c = half - CORNER_R
    r = CORNER_R + off
    out = []
    for q, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        for i in range(CORNER_PTS):
            a = 0.5 * math.pi * (q + i / (CORNER_PTS - 1))
            out.append((sx * c + r * math.cos(a), sy * c + r * math.sin(a)))
    return out


def add_sq_lathe(bm, profile, mat_idx, center=(0.0, 0.0, 0.0), solid=False):
    """add_lathe about the square pole: a profile [(offset, z), ...] where
    each station is the pole section grown by ``offset``."""
    c = Vector(center)
    secs = [rsq(POLE_HALF, off) for off, _z in profile]
    segs = len(secs[0])
    rings = [[bm.verts.new(c + Vector((secs[j][i][0], secs[j][i][1], profile[j][1])))
              for j in range(len(profile))] for i in range(segs)]
    return _revolve(bm, rings, not solid, mat_idx)


def add_tube(bm, pts, radius, sides, mat_idx, phase=0.0, section=None):
    """Capped bar swept along a polyline (parallel-transport frames): round
    of ``radius``, or the closed ``section`` [(a, b), ...] in the frame."""
    pts = [Vector(p) for p in pts]
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    ref = Vector((1.0, 0.0, 0.0)) if abs(tans[0].x) < 0.9 else Vector((0.0, 0.0, 1.0))
    nrm = (ref - tans[0] * ref.dot(tans[0])).normalized()
    if section is None:
        section = [(radius * math.cos(phase + 2.0 * math.pi * k / sides),
                    radius * math.sin(phase + 2.0 * math.pi * k / sides)) for k in range(sides)]
    rings = []
    for p, t in zip(pts, tans):
        nrm = (nrm - t * nrm.dot(t)).normalized()
        bi = t.cross(nrm)
        rings.append([bm.verts.new(p + nrm * a + bi * b) for a, b in section])
    n = len(section)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_ring(bm, center, axis, r_major, r_minor, segs, sides, mat_idx, phase=0.0):
    """Closed torus about ``axis`` through ``center``."""
    center = Vector(center)
    axis = Vector(axis).normalized()
    ref = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    u = axis.cross(ref).normalized()
    w = axis.cross(u)
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        radial = u * math.cos(a) + w * math.sin(a)
        c = center + radial * r_major
        rings.append([
            bm.verts.new(c + r_minor * (radial * math.cos(2.0 * math.pi * k / sides)
                                        + axis * math.sin(2.0 * math.pi * k / sides)))
            for k in range(sides)
        ])
    faces = []
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for k in range(sides):
            m = (k + 1) % sides
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_sphere(bm, center, radius, mat_idx, u=32, v=16, ico=0):
    if ico:
        geo = bmesh.ops.create_icosphere(bm, subdivisions=ico, radius=radius)
    else:
        geo = bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=radius)
    verts = geo["verts"]
    for vv in verts:
        vv.co += Vector(center)
    _mark({f for vv in verts for f in vv.link_faces}, mat_idx)
    return list(verts)


def add_band(bm, pts, width, z0, z1, mat_idx):
    """Painted line: a flat closed strip of ``width`` along an XY polyline,
    from z0 (sunk) to z1 (proud)."""
    pts = [Vector((p[0], p[1], 0.0)) for p in pts]
    rings = []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        t = (b - a).normalized()
        n = Vector((-t.y, t.x, 0.0)) * (0.5 * width)
        rings.append([
            bm.verts.new(Vector((p.x - n.x, p.y - n.y, z0))),
            bm.verts.new(Vector((p.x + n.x, p.y + n.y, z0))),
            bm.verts.new(Vector((p.x + n.x, p.y + n.y, z1))),
            bm.verts.new(Vector((p.x - n.x, p.y - n.y, z1))),
        ])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(4):
            m = (k + 1) % 4
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def arc_pts(cx, cy, r, a0, a1, steps):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / steps),
             cy + r * math.sin(a0 + (a1 - a0) * i / steps)) for i in range(steps + 1)]


def gooseneck_path():
    """Pole centreline: vertical, bend forward, straight, bend back to a
    vertical mast. The straight run is solved from the mast's offset, so the
    mast always lands behind the board's standoffs."""
    board_back = BOARD_FACE_Y - BOARD_T
    rail_back = board_back - RAIL_D + RAIL_BITE
    mast_y = rail_back - STANDOFF - POLE_HALF
    a = GOOSE_ANGLE
    rb = GOOSE_BEND_R
    straight = (mast_y - 2.0 * rb * (1.0 - math.cos(a))) / math.sin(a)
    pts = [Vector((0.0, 0.0, BASE_T - POLE_SEAT)), Vector((0.0, 0.0, 0.9))]
    c1 = Vector((0.0, rb, GOOSE_Z))
    for i in range(GOOSE_STEPS + 1):
        t = a * i / GOOSE_STEPS
        pts.append(c1 + Vector((0.0, -rb * math.cos(t), rb * math.sin(t))))
    p_end1 = pts[-1]
    d = Vector((0.0, math.sin(a), math.cos(a)))
    p_start2 = p_end1 + d * straight
    c2 = p_start2 + Vector((0.0, -rb * math.cos(a), rb * math.sin(a)))
    for i in range(GOOSE_STEPS + 1):
        t = a * (1.0 - i / GOOSE_STEPS)
        pts.append(c2 + Vector((0.0, rb * math.cos(t), -rb * math.sin(t))))
    top_start = pts[-1]
    pts.append(Vector((0.0, top_start.y, 0.5 * (top_start.z + MAST_TOP))))
    pts.append(Vector((0.0, top_start.y, MAST_TOP)))
    bends = {"c1": c1, "c2": c2, "d": d, "mast_z0": top_start.z}
    return pts, mast_y, bends


def bend_webs(bends):
    """(y, z) outlines of the two gusset webs, each on the concave side of
    its bend: a leg along the straight inner edge either side and the bend's
    inner arc between, all a bite inside the tube; the chord closes it."""
    a = GOOSE_ANGLE
    rb = GOOSE_BEND_R
    ri = rb - POLE_HALF + BEND_WEB_BITE
    d = bends["d"]
    c1, c2 = bends["c1"], bends["c2"]
    web1 = [(POLE_HALF - BEND_WEB_BITE, GOOSE_Z - BEND_WEB_LEG)]
    for i in range(GOOSE_STEPS + 1):
        t = a * i / GOOSE_STEPS
        web1.append((c1.y - ri * math.cos(t), c1.z + ri * math.sin(t)))
    end = Vector((0.0, web1[-1][0], web1[-1][1])) + d * BEND_WEB_LEG
    web1.append((end.y, end.z))
    t2 = [Vector((0.0, c2.y + ri * math.cos(a), c2.z - ri * math.sin(a))) - d * BEND_WEB_LEG]
    web2 = [(t2[0].y, t2[0].z)]
    for i in range(GOOSE_STEPS + 1):
        t = a * (1.0 - i / GOOSE_STEPS)
        web2.append((c2.y + ri * math.cos(t), c2.z - ri * math.sin(t)))
    web2.append((web2[-1][0], bends["mast_z0"] + BEND_WEB_LEG))
    return web1, web2


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
# The hoop
# --------------------------------------------------------------------------

def build_hoop(bm, bevel_verts, short_brace, drop_net, tilt_rim, loose_pad, short_bolts):
    # base plate (sunk into the slab), gussets, anchor bolts through it
    bevel_verts += add_span_box(bm, -BASE_W / 2, BASE_W / 2, -BASE_W / 2, BASE_W / 2,
                                -PLATE_SINK, BASE_T, STEEL_IDX)
    for k in range(4):
        ang = 0.5 * math.pi * k
        rad = Vector((math.cos(ang), math.sin(ang), 0.0))
        tan = Vector((-math.sin(ang), math.cos(ang), 0.0))
        r0 = POLE_HALF - GUSSET_BITE
        z0 = BASE_T - 0.003
        tri = [(r0, z0), (r0 + GUSSET_REACH, z0), (r0 + 0.018, z0 + GUSSET_H),
               (r0, z0 + GUSSET_H)]
        pts = []
        for s in (-0.5, 0.5):
            for r, z in tri:
                pts.append(rad * r + tan * (s * GUSSET_T) + Vector((0.0, 0.0, z)))
        bevel_verts += add_hexahedron(bm, pts, STEEL_IDX)
    bolt_foot = 0.5 * BASE_T if short_bolts else -ANCHOR_EMBED
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            c = (sx * ANCHOR_XY, sy * ANCHOR_XY, 0.0)
            add_lathe(bm, [(ANCHOR_R, bolt_foot), (ANCHOR_R, ANCHOR_TOP - 0.003),
                           (ANCHOR_R * 0.7, ANCHOR_TOP)], 8, STEEL_IDX, center=c,
                      solid=True)
            zw = BASE_T - 0.001
            add_lathe(bm, [(WASHER_R - 0.0015, zw), (WASHER_R, zw + 0.0015),
                           (WASHER_R, zw + 0.0045), (WASHER_R - 0.0015, zw + 0.0055)],
                      14, STEEL_IDX, center=c, solid=True)
            zn = zw + 0.0045
            add_lathe(bm, [(NUT_R * 0.86, zn), (NUT_R, zn + 0.003), (NUT_R, zn + 0.016),
                           (NUT_R * 0.86, zn + 0.019)], 6, STEEL_IDX, center=c,
                      phase=math.pi / 6.0, solid=True)

    # the pole: one square sweep from inside the plate to the mast top
    path, mast_y, bends = gooseneck_path()
    add_tube(bm, path, 0.0, 0, STEEL_IDX, section=rsq(POLE_HALF, 0.0))
    for web in bend_webs(bends):
        bevel_verts += add_prism_x(bm, web, -BEND_WEB_T / 2, BEND_WEB_T / 2, STEEL_IDX)
    cap_z = MAST_TOP
    add_sq_lathe(bm, [(0.006, cap_z - 0.016), (0.006, cap_z + 0.010), (-0.004, cap_z + 0.022),
                      (-0.012, cap_z + 0.026)], STEEL_IDX, center=(0.0, mast_y, 0.0),
                 solid=True)

    # square pad wrapped on the pole, gripping it; grooves split it into
    # panels and a hook-and-loop flap closes it up one corner
    ri = LOOSE_PAD if loose_pad else -PAD_GRIP
    ro = PAD_T
    z0, z1 = PAD_Z
    prof = [(ri, z0), (ro - 0.012, z0), (ro, z0 + 0.012)]
    for g in (1.0 / 3.0, 2.0 / 3.0):
        gz = z0 + (z1 - z0) * g
        prof += [(ro, gz - 0.012), (ro - 0.008, gz - 0.004), (ro - 0.008, gz + 0.004),
                 (ro, gz + 0.012)]
    prof += [(ro, z1 - 0.012), (ro - 0.012, z1), (ri, z1)]
    add_sq_lathe(bm, prof, PAD_IDX)
    face = POLE_HALF + PAD_T
    fx = POLE_HALF - CORNER_R - 0.5 * FLAP_W
    bevel_verts += add_span_box(bm, fx - FLAP_W / 2, fx + FLAP_W / 2, face - FLAP_SINK,
                                face + FLAP_T, z0 + 0.05, z1 - 0.05, PAD_IDX)

    # brace collar and the two support braces to the lower rail
    cz0 = COLLAR_Z - COLLAR_H / 2.0
    cz1 = COLLAR_Z + COLLAR_H / 2.0
    ct = COLLAR_T
    add_sq_lathe(bm, [(-0.003, cz0), (ct - 0.004, cz0), (ct, cz0 + 0.004),
                      (ct, cz1 - 0.004), (ct - 0.004, cz1), (-0.003, cz1)], STEEL_IDX)
    board_back = BOARD_FACE_Y - BOARD_T
    rail_y = board_back - RAIL_D / 2.0 + RAIL_BITE
    for sx in (-1.0, 1.0):
        # the brace foot sits in the middle of the collar wall
        p0 = Vector((sx * (POLE_HALF + 0.5 * ct - 0.0015), 0.015, COLLAR_Z))
        p1 = Vector((sx * BRACE_X, rail_y, RAIL_Z[0]))
        if short_brace:
            p1 = p1 - (p1 - p0).normalized() * SHORT_BRACE
        add_tube(bm, [p0, p1], BRACE_R, 12, STEEL_IDX)

    # mast clamps (bolted), standoffs, back rails and stiles
    yrot = {sx: Matrix.Rotation(sx * 0.5 * math.pi, 3, "Y") for sx in (-1.0, 1.0)}
    for rz in RAIL_Z:
        h = CLAMP_H / 2.0
        add_sq_lathe(bm, [(-0.003, rz - h), (CLAMP_T - 0.004, rz - h), (CLAMP_T, rz - h + 0.004),
                          (CLAMP_T, rz + h - 0.004), (CLAMP_T - 0.004, rz + h), (-0.003, rz + h)],
                     STEEL_IDX, center=(0.0, mast_y, 0.0))
        for sx in (-1.0, 1.0):
            # the two heads on a face stand 1 mm apart so their caps never
            # share a plane
            for dz, hh in ((-0.026, 0.0), (0.026, 0.001)):
                add_lathe(bm, [(CLAMP_BOLT_R, -0.002 - hh), (CLAMP_BOLT_R, 0.007 + hh),
                               (CLAMP_BOLT_R * 0.8, 0.0095 + hh)], 6, STEEL_IDX,
                          center=(sx * (POLE_HALF + CLAMP_T), mast_y, rz + dz), rot=yrot[sx],
                          phase=math.pi / 6.0, solid=True)
        y0 = mast_y
        y1 = board_back - RAIL_D + RAIL_BITE + 0.006
        bevel_verts += add_box(bm, (0.0, 0.5 * (y0 + y1), rz), (STANDOFF_S, y1 - y0,
                                                                 STANDOFF_S), STEEL_IDX)
        bevel_verts += add_box(bm, (0.0, rail_y, rz), (RAIL_W, RAIL_D, RAIL_H), STEEL_IDX)
    for sx in (-1.0, 1.0):
        h = RAIL_Z[1] - RAIL_Z[0]
        bevel_verts += add_box(bm, (sx * STILE_X, board_back - 0.0215, 0.5 * sum(RAIL_Z)),
                               (0.040, 0.047, h), STEEL_IDX)

    # board panel inside its aluminium frame
    bz = BOARD_BOT + BOARD_H / 2.0
    bevel_verts += add_box(bm, (0.0, BOARD_FACE_Y - BOARD_T / 2.0, bz),
                           (BOARD_W - 2.0 * PANEL_INSET, BOARD_T, BOARD_H - 2.0 * PANEL_INSET),
                           BOARD_IDX)
    bevel_verts += add_rect_frame(
        bm, 0.0, bz, board_back - FRAME_BACK, BOARD_FACE_Y + FRAME_PROUD,
        BOARD_W, BOARD_H, BOARD_W - 2.0 * FRAME_W, BOARD_H - 2.0 * FRAME_W, ALU_IDX)

    # edge pad wrapped round the frame's bottom member, a reveal past the
    # frame's ends so its caps never land on the frame's end faces
    fy_back = board_back - FRAME_BACK
    fy_front = BOARD_FACE_Y + FRAME_PROUD
    py0 = fy_back - EDGE_PAD_T
    py1 = fy_front + EDGE_PAD_T
    pz0 = BOARD_BOT - EDGE_PAD_T
    pz1 = BOARD_BOT + FRAME_W + 0.006
    ch = 0.012
    pad_prof = [(py0 + ch, pz0), (py1 - ch, pz0), (py1, pz0 + ch), (py1, pz1 - ch),
                (py1 - ch, pz1), (py0 + ch, pz1), (py0, pz1 - ch), (py0, pz0 + ch)]
    half = BOARD_W / 2.0 + EDGE_PAD_REVEAL
    bevel_verts += add_prism_x(bm, pad_prof, -half, half, PAD_IDX)

    # painted border (tucked 3 mm under the frame) and shooter's square
    bw = BOARD_W - 2.0 * FRAME_W + 0.006
    bh = BOARD_H - 2.0 * FRAME_W + 0.006
    add_rect_frame(bm, 0.0, bz, BOARD_FACE_Y - PAINT_SINK, BOARD_FACE_Y + BORDER_PROUD,
                   bw, bh, bw - 0.006 - 2.0 * BORDER_W, bh - 0.006 - 2.0 * BORDER_W,
                   PAINT_IDX)
    sq_z = RIM_TOP - BOARD_LINE_W + SQUARE_H / 2.0
    add_rect_frame(bm, 0.0, sq_z, BOARD_FACE_Y - PAINT_SINK, BOARD_FACE_Y + SQUARE_PROUD,
                   SQUARE_W, SQUARE_H, SQUARE_W - 2.0 * BOARD_LINE_W,
                   SQUARE_H - 2.0 * BOARD_LINE_W, PAINT_IDX)

    # --- breakaway rim assembly (every vertex from here on tilts with --tilt-rim)
    rim_start = len(bm.verts)
    ring_z = RIM_TOP - RING_R
    ring_rc = RIM_ID / 2.0 + RING_R
    ring_cy = BOARD_FACE_Y + RIM_GAP + RIM_ID / 2.0
    fz = ring_z - 0.03
    fy0 = BOARD_FACE_Y - FLANGE_SINK
    fy1 = BOARD_FACE_Y + FLANGE_T
    bevel_verts += add_box(bm, (0.0, 0.5 * (fy0 + fy1), fz), (FLANGE_W, fy1 - fy0, FLANGE_H),
                           RIM_IDX)
    xrot = Euler((-0.5 * math.pi, 0.0, 0.0)).to_matrix()
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            add_lathe(bm, [(BOLT_R, fy1 - 0.003), (BOLT_R, fy1 + 0.005),
                           (BOLT_R * 0.8, fy1 + 0.0075)], 6, STEEL_IDX,
                      center=(sx * 0.068, 0.0, fz + sz * 0.062), rot=xrot,
                      phase=math.pi / 6.0, solid=True)
    by0 = fy1 - 0.004
    by1 = ring_cy - ring_rc + 0.004
    top = ring_z + 0.004
    bracket = [
        (-0.055, by0, top - 0.075), (0.055, by0, top - 0.075), (0.055, by0, top), (-0.055, by0, top),
        (-0.026, by1, top - 0.018), (0.026, by1, top - 0.018), (0.026, by1, top), (-0.026, by1, top),
    ]
    bevel_verts += add_hexahedron(bm, bracket, RIM_IDX)
    # hinge barrel across the bracket's heel, bearing into the flange
    add_lathe(bm, [(HINGE_R - 0.002, -HINGE_HALF), (HINGE_R, -HINGE_HALF + 0.002),
                   (HINGE_R, HINGE_HALF - 0.002), (HINGE_R - 0.002, HINGE_HALF)], 12,
              STEEL_IDX, center=(0.0, fy1 + HINGE_R - 0.003, top - 0.062), rot=yrot[1.0],
              solid=True)
    # spring housing on the bracket, sloping down toward the ring
    hy0 = fy1 - 0.003
    hy1 = by0 + 0.095
    hz0 = top - 0.004
    housing = [
        (-0.046, hy0, hz0), (0.046, hy0, hz0), (0.046, hy0, top + 0.052), (-0.046, hy0, top + 0.052),
        (-0.040, hy1, hz0), (0.040, hy1, hz0), (0.040, hy1, top + 0.026), (-0.040, hy1, top + 0.026),
    ]
    bevel_verts += add_hexahedron(bm, housing, RIM_IDX)
    for sx in (-1.0, 1.0):
        phi = -0.5 * math.pi + sx * STRUT_ANGLE
        p1 = Vector((ring_rc * math.cos(phi), ring_cy + ring_rc * math.sin(phi), ring_z - 0.003))
        p0 = Vector((sx * 0.030, by0 + 0.055, top - 0.050))
        add_tube(bm, [p0, p1], STRUT_R, 8, RIM_IDX)
    add_ring(bm, (0.0, ring_cy, ring_z), (0.0, 0.0, 1.0), ring_rc, RING_R, RING_SEGS, 8,
             RIM_IDX)

    # net hooks: eyes welded under the ring, in the ring's radial plane
    hook_eyes = []
    for k in range(NET_HOOKS):
        phi = -0.5 * math.pi + math.pi / NET_HOOKS + 2.0 * math.pi * k / NET_HOOKS
        rad = Vector((math.cos(phi), math.sin(phi), 0.0))
        tan = Vector((-math.sin(phi), math.cos(phi), 0.0))
        e = Vector((0.0, ring_cy, 0.0)) + rad * ring_rc
        e.z = ring_z - RING_R - HOOK_MAJOR + HOOK_BITE
        add_ring(bm, e, tan, HOOK_MAJOR, HOOK_MINOR, 8, 4, RIM_IDX)
        hook_eyes.append((phi, e, rad, tan))

    # --- the net (drops with --drop-net)
    net_start = len(bm.verts)
    bottoms = []
    for phi, e, rad, tan in hook_eyes:
        top_pt = e - Vector((0.0, 0.0, HOOK_MAJOR - HOOK_MINOR - CORD_R + NET_LOOP_BITE))
        lc = top_pt - Vector((0.0, 0.0, NET_LOOP_R))
        add_ring(bm, lc, rad, NET_LOOP_R, CORD_R, 10, 4, NET_IDX, phase=0.3)
        bottoms.append((phi, lc - Vector((0.0, 0.0, NET_LOOP_R)), tan))
    dphi = 2.0 * math.pi / NET_HOOKS
    z_top = bottoms[0][1].z

    def net_point(phi, j, off):
        f = j / NET_ROWS
        r = ring_rc + (NET_BOT_R - ring_rc) * (1.0 - (1.0 - f) ** 1.4) + off
        z = z_top - NET_LEN * f
        return Vector((r * math.cos(phi), ring_cy + r * math.sin(phi), z))

    for phi0, b, tan in bottoms:
        for spin, off, phase in ((1.0, KNOT_OFFSET * CORD_R, 0.0),
                                 (-1.0, -KNOT_OFFSET * CORD_R, 0.37)):
            pts = [b + tan * (spin * 0.003)]
            for j in range(1, NET_ROWS + 1):
                pts.append(net_point(phi0 + spin * j * dphi / 2.0, j, off))
            add_tube(bm, pts, CORD_R, NET_STRAND_SIDES, NET_IDX, phase=phase)
    # a knot where each pair of strands crosses
    for j in range(1, NET_ROWS + 1):
        for phi0, _b, _t in bottoms:
            add_sphere(bm, net_point(phi0 + j * dphi / 2.0, j, 0.0), KNOT_R, NET_IDX, ico=1)
    bm.verts.ensure_lookup_table()
    if drop_net:
        for v in bm.verts[net_start:]:
            v.co.z -= DROP_NET
    if tilt_rim:
        pivot = Vector((0.0, BOARD_FACE_Y, ring_z))
        rot = Matrix.Rotation(math.radians(-TILT_RIM_DEG), 3, "X")
        for v in bm.verts[rim_start:]:
            v.co = pivot + rot @ (v.co - pivot)
    return Vector((0.0, ring_cy))


# --------------------------------------------------------------------------
# The court
# --------------------------------------------------------------------------

def build_court(bm, bevel_verts, basket, float_ball, float_paint):
    x0, x1 = SLAB_X
    ga = JOINT_Y - JOINT_GAP / 2.0
    gb = JOINT_Y + JOINT_GAP / 2.0
    top_a = SLAB_T
    top_b = SLAB_T - SLAB_B_DROP
    bevel_verts += add_span_box(bm, x0, x1, SLAB_Y[0], ga, 0.0, top_a, CONCRETE_IDX)
    bevel_verts += add_span_box(bm, x0, x1, gb, SLAB_Y[1], 0.0, top_b, CONCRETE_IDX)
    add_span_box(bm, x0 + 0.005, x1 - 0.005, ga - JOINT_BITE, gb + JOINT_BITE, 0.006,
                 top_b - SEAL_DROP, SEAM_IDX)

    paint_start = len(bm.verts)

    def line(pts, host_top, heights, mat=LINE_IDX, width=LINE_W):
        add_band(bm, pts, width, host_top - heights[1], host_top + heights[0], mat)

    xe0, xe1 = x0 + EDGE_CLEAR, x1 - EDGE_CLEAR
    a_end = ga - LINE_END
    b_start = gb + LINE_END
    line([(xe0, BASELINE_Y), (xe1, BASELINE_Y)], top_a, BASELINE_H)
    for sx in (-1.0, 1.0):
        x = sx * LANE_HALF
        line([(x, BASELINE_Y), (x, a_end)], top_a, LANE_H)
        line([(x, b_start), (x, FT_Y + 0.012)], top_b, LANE_H)
    line([(-LANE_HALF, FT_Y), (LANE_HALF, FT_Y)], top_b, FTLINE_H)
    # key fill, overlapping the lane lines' inner halves
    fw = 2.0 * (LANE_HALF - 0.015)
    line([(0.0, BASELINE_Y), (0.0, a_end - 0.003)], top_a, FILL_H, KEY_IDX, fw)
    line([(0.0, b_start + 0.003), (0.0, FT_Y)], top_b, FILL_H, KEY_IDX, fw)
    # lane marks: a block and three ticks outside each lane line
    for sx in (-1.0, 1.0):
        for i, hy in enumerate(HASH_Y):
            host = top_a if hy < JOINT_Y else top_b
            w = BLOCK_W if i == 0 else LINE_W
            line([(sx * LANE_HALF, hy), (sx * (LANE_HALF + HASH_LEN), hy)], host, HASH_H,
                 width=w)
    line(arc_pts(0.0, FT_Y, FT_R, 0.0, math.pi, 40), top_b, FTCIRC_H)
    a0 = math.acos(xe1 / ARC_R)
    line(arc_pts(basket.x, basket.y, ARC_R, a0, math.pi - a0, 64), top_b, ARC_H)
    bm.verts.ensure_lookup_table()
    if float_paint:
        for v in bm.verts[paint_start:]:
            v.co.z += FLOAT_PAINT

    ball_start = len(bm.verts)
    for bx, by, eul in BALLS:
        host = top_a if by < JOINT_Y else top_b
        c = Vector((bx, by, host + BALL_R - BALL_SINK))
        add_sphere(bm, c, BALL_R, BALL_IDX, u=32, v=16)
        m = Euler(eul).to_matrix()
        rs = BALL_R - SEAM_SINK
        d = SEAM_PARALLEL * BALL_R
        seams = [(Vector((0, 0, 0)), Vector((1, 0, 0)), rs),
                 (Vector((0, 0, 0)), Vector((0, 1, 0)), rs)]
        for s in (-1.0, 1.0):
            seams.append((Vector((s * d, 0, 0)), Vector((1, 0, 0)), math.sqrt(rs * rs - d * d)))
        for off, axis, rc in seams:
            add_ring(bm, c + m @ off, m @ axis, rc, SEAM_R, 48, 6, SEAM_IDX)
    bm.verts.ensure_lookup_table()
    if float_ball:
        for v in bm.verts[ball_start:]:
            v.co.z += FLOAT_BALL


def build_hoop_mesh(name, bevel_offset, bevel_segments, short_brace=False,
                    drop_net=False, tilt_rim=False, loose_pad=False, short_bolts=False,
                    float_ball=False, float_paint=False):
    bm = bmesh.new()
    try:
        bevel_verts = []
        basket = build_hoop(bm, bevel_verts, short_brace, drop_net, tilt_rim, loose_pad,
                            short_bolts)
        # stand the hoop on the court: its z = 0 is the top of slab A
        for v in bm.verts:
            v.co.z += SLAB_T
        build_court(bm, bevel_verts, basket, float_ball, float_paint)

        if bevel_offset > 0.0:
            # One pass per material, with material= set: left at its default
            # the chamfer faces take slot 0 and the board's rim would render
            # (and classify) as steel. A set of BMEdges iterates in memory
            # order, which varies run to run; sort by index.
            for mat_idx in (STEEL_IDX, BOARD_IDX, RIM_IDX, PAD_IDX, ALU_IDX, CONCRETE_IDX):
                bm.edges.index_update()
                edges = sorted(
                    {e for v in bevel_verts if v.is_valid for e in v.link_edges
                     if all(f.material_index == mat_idx for f in e.link_faces)},
                    key=lambda e: e.index,
                )
                if not edges:
                    continue
                bmesh.ops.bevel(
                    bm,
                    geom=edges,
                    offset=bevel_offset,
                    segments=bevel_segments,
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
                    material=mat_idx,
                )

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        zmin = min(zs)
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy
            v.co.z -= zmin
            if v.co.z < 0.0:
                v.co.z = 0.0

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # Round stock is smooth-shaded. Chamfers, material boundaries, bends
        # over 35 degrees, and a flat face meeting a much narrower facet (the
        # pole's flats against its corner fillets) stay sharp, so flats read
        # flat and fillets read round.
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
                continue
            ang = edge.calc_face_angle()
            fa, fb = edge.link_faces
            aa, ab = fa.calc_area(), fb.calc_area()
            lopsided = ang > math.radians(5.0) and max(aa, ab) > 6.0 * min(aa, ab)
            edge.smooth = ang < math.radians(35.0) and not lopsided
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
    nt.links.new(bsdf.outputs["BSDF"], add.inputs[0])
    nt.links.new(em.outputs["Emission"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
    return mat


def concrete_material():
    """Broom-finished concrete: large soft stains and scuffs over a fine
    aggregate speckle, the speckle again in a faint bump."""
    mat = bpy.data.materials.new("CourtConcrete")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.86
    coord = nt.nodes.new("ShaderNodeTexCoord")
    big = nt.nodes.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 0.9
    big.inputs["Detail"].default_value = 4.0
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 220.0
    fine.inputs["Detail"].default_value = 2.0
    for n in (big, fine):
        nt.links.new(coord.outputs["Object"], n.inputs["Vector"])
    stain = nt.nodes.new("ShaderNodeValToRGB")
    stain.color_ramp.elements[0].position = 0.36
    stain.color_ramp.elements[0].color = (0.062, 0.060, 0.057, 1.0)
    stain.color_ramp.elements[1].position = 0.66
    stain.color_ramp.elements[1].color = (0.135, 0.130, 0.122, 1.0)
    nt.links.new(big.outputs["Fac"], stain.inputs["Fac"])
    speck = nt.nodes.new("ShaderNodeValToRGB")
    speck.color_ramp.elements[0].position = 0.42
    speck.color_ramp.elements[0].color = (0.80, 0.80, 0.80, 1.0)
    speck.color_ramp.elements[1].position = 0.60
    speck.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(fine.outputs["Fac"], speck.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(stain.outputs["Color"], mul.inputs[1])
    nt.links.new(speck.outputs["Color"], mul.inputs[2])
    nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    nt.links.new(fine.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def worn_paint(name, color, wear):
    """Court paint worn through to the concrete where a noise mask says so."""
    mat = principled(name, color, 0.0, 0.70, roughness_var=0.10, noise_scale=30.0)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 9.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.10, 0.097, 0.092, 1.0)
    ramp.color_ramp.elements[1].position = 0.30 + wear
    ramp.color_ramp.elements[1].color = color
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def ball_material():
    """Composite leather: a pebble grain from a fine Voronoi cell pattern
    as bump, with a faint darker grime in the pebble valleys."""
    mat = principled("BallLeather", (0.36, 0.105, 0.035, 1.0), 0.0, 0.62)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "F1"
    vor.inputs["Scale"].default_value = 380.0
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.45
    bump.inputs["Distance"].default_value = 0.002
    nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.30, 0.085, 0.030, 1.0)
    ramp.color_ramp.elements[1].position = 0.55
    ramp.color_ramp.elements[1].color = (0.36, 0.105, 0.035, 1.0)
    nt.links.new(vor.outputs["Distance"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def hoop_materials():
    """Slot order: steel, board, paint, rim, net, pad, alu, concrete, line,
    key, ball, seam. Shared by the check and the render.

    Powder-coated steel is near-black satin with a soft studio sheen, not
    chrome; the frame is satin aluminium; the rim is enamelled orange; the
    board is a weathered off-white with worn red paint; the court paint is
    faded and worn through to the concrete.
    """
    steel = principled("HoopSteel", (0.030, 0.034, 0.040, 1.0), 0.0, 0.34,
                       roughness_var=0.10, mottle=0.20, coat=0.30)
    add_studio(steel, (0.55, 0.60, 0.68, 1.0), 0.16,
               [(0.0, 0.02), (0.30, 0.04), (0.42, 0.40), (0.50, 1.0), (0.62, 0.30), (1.0, 0.12)])
    board = principled("HoopBoard", (0.60, 0.60, 0.58, 1.0), 0.0, 0.34,
                       roughness_var=0.10, mottle=0.10, noise_scale=6.0)
    paint = principled("HoopPaint", (0.46, 0.050, 0.038, 1.0), 0.0, 0.50,
                       roughness_var=0.12, mottle=0.22, noise_scale=30.0)
    rim = principled("HoopRim", (0.78, 0.21, 0.030, 1.0), 0.35, 0.42,
                     roughness_var=0.12, mottle=0.18, noise_scale=40.0)
    net = principled("HoopNet", (0.78, 0.77, 0.72, 1.0), 0.0, 0.82)
    pad = principled("HoopPad", (0.028, 0.060, 0.17, 1.0), 0.0, 0.58,
                     roughness_var=0.10, mottle=0.12)
    alu = principled("FrameAlu", (0.62, 0.63, 0.65, 1.0), 1.0, 0.30,
                     roughness_var=0.06, noise_scale=60.0)
    add_studio(alu, (0.62, 0.63, 0.65, 1.0), 0.55,
               [(0.0, 0.03), (0.28, 0.08), (0.40, 0.55), (0.48, 1.0), (0.60, 0.35), (1.0, 0.20)])
    concrete = concrete_material()
    line = worn_paint("CourtLine", (0.50, 0.49, 0.46, 1.0), 0.14)
    key = worn_paint("CourtKey", (0.050, 0.080, 0.066, 1.0), 0.10)
    ball = ball_material()
    seam = principled("BallSeam", (0.012, 0.011, 0.011, 1.0), 0.0, 0.55)
    return steel, board, paint, rim, net, pad, alu, concrete, line, key, ball, seam


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
    def __init__(self, me, idx, verts, polys):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.centre = (self.lo + self.hi) * 0.5
        mats = {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tree = BVHTree.FromPolygons(
            [tuple(p) for p in pts], [[remap[v] for v in p.vertices] for p in polys])
        self.polys = polys


def shell_bite(a, b):
    """Deepest vertex of shell ``a`` inside closed shell ``b`` (m); negative if none is.
    Signed by the nearest face's outward normal (normals were recalculated)."""
    best = -1e9
    for co in a.pts:
        loc, nrm, _i, dist = b.tree.find_nearest(co)
        if loc is None:
            continue
        depth = dist if (co - loc).dot(nrm) < 0.0 else -dist
        best = max(best, depth)
    return best


def circle_fit(pts):
    """Centre, unit axis and mean radius of a ring of points (PCA)."""
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    _w, vecs = np.linalg.eigh(q.T @ q)
    axis = vecs[:, 0]
    if axis[2] < 0.0:
        axis = -axis
    inplane = q - np.outer(q @ axis, axis)
    radius = float(np.linalg.norm(inplane, axis=1).mean())
    return c, axis, radius, np.linalg.norm(inplane, axis=1)


def point_circle_distance(p, c, axis, radius):
    d = np.asarray(p, dtype=np.float64) - c
    h = float(d @ axis)
    rad = d - h * axis
    return math.hypot(float(np.linalg.norm(rad)) - radius, h)


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}

    def by(idx):
        return [s for s in parts if s.mat == idx]

    steel = by(STEEL_IDX)
    out["pole"] = [s for s in steel if s.size.z > 3.0]
    out["braces"] = [s for s in steel if 1.0 < s.size.z < 3.0 and s.size.x < 0.8]
    out["collars"] = [s for s in steel if 0.15 < s.size.x < 0.25 and 0.15 < s.size.y < 0.25
                      and 0.05 < s.size.z < 0.12 and s.centre.z < 2.5]
    rails = [s for s in steel if s.size.x > 1.0 and s.size.z < 0.08]
    out["low_rail"] = sorted(rails, key=lambda s: s.centre.z)[:1]
    out["plate"] = [s for s in steel if s.size.x > 0.4 and s.size.y > 0.4 and s.size.z < 0.05]
    out["bolts"] = [s for s in steel if s.size.x < 0.03 and s.size.y < 0.03
                    and 0.06 < s.size.z < 0.3 and s.centre.z < 0.5]
    rim = by(RIM_IDX)
    out["ring"] = [s for s in rim if s.size.x > 0.4]
    out["hooks"] = [s for s in rim if max(s.size) < 0.035]
    net = by(NET_IDX)
    out["loops"] = [s for s in net if 0.025 <= max(s.size) < 0.05]
    out["strands"] = [s for s in net if max(s.size) >= 0.05]
    out["knots"] = [s for s in net if max(s.size) < 0.025]
    out["board"] = by(BOARD_IDX)
    out["slabs"] = [s for s in by(CONCRETE_IDX) if s.size.x > 1.0]
    out["paint"] = by(LINE_IDX) + by(KEY_IDX)
    out["balls"] = by(BALL_IDX)
    return out


def slab_under(cls, x, y):
    for s in cls["slabs"]:
        if s.lo.x <= x <= s.hi.x and s.lo.y <= y <= s.hi.y:
            return s
    return None


def brace_audit(cls):
    if len(cls["braces"]) != 2 or not cls["collars"] or not cls["low_rail"]:
        return len(cls["braces"]), -1.0, -1.0
    collar = cls["collars"][0]
    rail = cls["low_rail"][0]
    c_bite = min(shell_bite(b, collar) for b in cls["braces"])
    r_bite = min(shell_bite(b, rail) for b in cls["braces"])
    return len(cls["braces"]), c_bite, r_bite


def net_audit(cls):
    """Worst hook: distance from its eye centre to the nearest loop's cord circle."""
    loops = [circle_fit(s.pts) for s in cls["loops"]]
    worst = 0.0
    for h in cls["hooks"]:
        e, _a, _r, _ = circle_fit(h.pts)
        best = min((point_circle_distance(e, c, a, r) for c, a, r, _ in loops), default=9.0)
        worst = max(worst, best)
    return len(cls["hooks"]), len(cls["loops"]), len(cls["strands"]), worst


def rim_audit(cls):
    """Rim top over the court, inside diameter, inner-edge gap to the board
    face, tilt."""
    if len(cls["ring"]) != 1 or not cls["board"]:
        return None
    ring = cls["ring"][0]
    c, axis, _r, radii = circle_fit(ring.pts)
    host = slab_under(cls, float(c[0]), float(c[1]))
    if host is None:
        return None
    tilt = math.degrees(math.acos(min(1.0, abs(float(axis[2])))))
    inner_r = float(radii.min())
    top = ring.hi.z - host.hi.z
    face_y = max(s.hi.y for s in cls["board"])
    gap = (float(c[1]) - inner_r) - face_y
    return {"top": top, "id": 2.0 * inner_r, "gap": gap, "tilt": tilt}


def ball_audit(cls):
    """Per ball: fitted radius and how far its lowest point is into the
    slab it stands on (the ball's own vertices, not the build constants)."""
    out = []
    for b in cls["balls"]:
        p = np.array([tuple(v) for v in b.pts], dtype=np.float64)
        c = p.mean(axis=0)
        r = float(np.linalg.norm(p - c, axis=1).mean())
        host = slab_under(cls, float(c[0]), float(c[1]))
        sink = (host.hi.z - b.lo.z) if host else -1.0
        out.append((r, sink))
    return out


def bolt_audit(cls):
    """Worst anchor bolt: depth of its foot under the slab top it is set in,
    and how far its head stands above the plate."""
    if not cls["plate"] or len(cls["bolts"]) != 4:
        return len(cls["bolts"]), -1.0, -1.0
    plate = cls["plate"][0]
    embed, proud = 9.0, 9.0
    for b in cls["bolts"]:
        host = slab_under(cls, b.centre.x, b.centre.y)
        embed = min(embed, (host.hi.z - b.lo.z) if host else -1.0)
        proud = min(proud, b.hi.z - plate.hi.z)
    return 4, embed, proud


def paint_audit(cls):
    """Every court-paint shell against the slab under its centre: the
    lowest top-above and the lowest/highest sink-below."""
    tops, sinks = [], []
    for s in cls["paint"]:
        host = slab_under(cls, s.centre.x, s.centre.y)
        if host is None:
            return len(cls["paint"]), -1.0, -1.0, -1.0, -1.0
        tops.append(s.hi.z - host.hi.z)
        sinks.append(host.hi.z - s.lo.z)
    if not tops:
        return 0, -1.0, -1.0, -1.0, -1.0
    return len(tops), min(tops), max(tops), min(sinks), max(sinks)


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
    return len(roots), sorted(sizes.values())


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
    img = bpy.data.images.new("HoopNrm", size, size, alpha=True, float_buffer=False)
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
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_yup=True,
                              export_apply=True, export_draco_mesh_compression_enable=False,
                              export_animations=False)


def check(skip_decimate, lift_z=False, stray_vert=False, short_brace=False,
          drop_net=False, tilt_rim=False, loose_pad=False, float_ball=False,
          short_bolts=False, float_paint=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(short_brace=short_brace, drop_net=drop_net, tilt_rim=tilt_rim,
                 loose_pad=loose_pad, float_ball=float_ball, short_bolts=short_bolts,
                 float_paint=float_paint)
    low = build_hoop_mesh("HoopLow", bevel_offset=0.004, bevel_segments=2, **flags)
    high = build_hoop_mesh("HoopHigh", bevel_offset=0.004, bevel_segments=4, **flags)
    mats = hoop_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    steel = mats[STEEL_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none6 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("hoop mesh did not build", 3),) + none6

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
    nbraces, collar_bite, rail_bite = brace_audit(cls)
    nhooks, nloops, nstrands, thread = net_audit(cls)
    rim = rim_audit(cls)
    balls = ball_audit(cls)
    nbolts, bolt_embed, bolt_proud = bolt_audit(cls)
    npaint, ptop_lo, ptop_hi, psink_lo, psink_hi = paint_audit(cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, steel)
    if img is None:
        return (fail("hoop has no UV layer", 3),) + none6
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "HoopLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "HoopLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_hoop_mesh("HoopColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "HoopCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_basketball_hoop_{os.getpid()}.glb")
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
          f"outer={OUTER_SIZE} zmin={bb[2]:.4f}")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured shells={len(cls['all'])} braces={nbraces} "
          f"collar_bite={collar_bite:.5f} rail_bite={rail_bite:.5f}")
    print(f"measured hooks={nhooks} loops={nloops} strands={nstrands} "
          f"knots={len(cls['knots'])} worst_thread={thread:.5f}")
    if rim:
        print(f"measured rim_top={rim['top']:.4f} rim_id={rim['id']:.4f} "
              f"rim_gap={rim['gap']:.4f} rim_tilt_deg={rim['tilt']:.3f}")
    print("measured balls=" + " ".join(f"(r={r:.4f},sink={s:.5f})" for r, s in balls))
    print(f"measured bolts={nbolts} bolt_embed={bolt_embed:.4f} bolt_proud={bolt_proud:.4f}")
    print(f"measured paint_shells={npaint} top={ptop_lo:.5f}..{ptop_hi:.5f} "
          f"sink={psink_lo:.5f}..{psink_hi:.5f}")
    print(f"measured components={ncomp} sizes={comp_sizes}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none6
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none6
    for idx, (label, floor) in sorted(FACE_FLOORS.items()):
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{label} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + none6
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + none6
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + none6
    if (abs(size_x - OUTER_SIZE[0]) > BBOX_TOL or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
            or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL):
        return (fail(f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8),) + none6
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
                     "(--skip-decimate is the designed fail)", 9),) + none6
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9),) + none6
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + none6
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + none6
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + none6
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf}", 15),) + none6
    if bb[2] > ZMIN_EPS:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none6
    if nbraces != 2 or min(collar_bite, rail_bite) < BRACE_BITE_MIN:
        return (fail(f"brace bite collar={collar_bite:.5f} rail={rail_bite:.5f} "
                     f"braces={nbraces} (want 2, >= {BRACE_BITE_MIN})", 17),) + none6
    if nhooks != NET_HOOKS or nloops != NET_HOOKS or thread > NET_THREAD_MAX:
        return (fail(f"net seat: hooks={nhooks} loops={nloops} worst eye-to-loop "
                     f"{thread:.5f} > {NET_THREAD_MAX}", 18),) + none6
    if (rim is None or abs(rim["top"] - RIM_TOP) > RIM_TOP_TOL
            or abs(rim["id"] - RIM_ID) > RIM_ID_TOL
            or abs(rim["gap"] - RIM_GAP) > RIM_GAP_TOL
            or rim["tilt"] > RIM_TILT_MAX_DEG):
        return (fail(f"rim off regulation: {rim}", 19),) + none6
    # Seat checks run before the component check: a floated ball or lifted
    # paint also detaches, and must name its own budget.
    if (len(balls) != len(BALLS)
            or any(abs(r - BALL_R) > BALL_R_TOL or not (BALL_SINK_MIN <= s <= BALL_SINK_MAX)
                   for r, s in balls)):
        return (fail(f"ball seat: {balls} (want {len(BALLS)} balls, r {BALL_R}+/-{BALL_R_TOL}, "
                     f"sink {BALL_SINK_MIN}..{BALL_SINK_MAX})", 21),) + none6
    if nbolts != 4 or bolt_embed < ANCHOR_EMBED_MIN or bolt_proud < ANCHOR_PROUD_MIN:
        return (fail(f"anchor bolts={nbolts} embed={bolt_embed:.4f} (>= {ANCHOR_EMBED_MIN}) "
                     f"proud={bolt_proud:.4f} (>= {ANCHOR_PROUD_MIN})", 22),) + none6
    if (npaint != PAINT_SHELLS
            or not (PAINT_TOP_BAND[0] <= ptop_lo and ptop_hi <= PAINT_TOP_BAND[1])
            or not (PAINT_SINK_BAND[0] <= psink_lo and psink_hi <= PAINT_SINK_BAND[1])):
        return (fail(f"court paint: shells={npaint} top {ptop_lo:.5f}..{ptop_hi:.5f} "
                     f"(band {PAINT_TOP_BAND}) sink {psink_lo:.5f}..{psink_hi:.5f} "
                     f"(band {PAINT_SINK_BAND})", 23),) + none6
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 20),) + none6
    return 0, low, steel, tex


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, steel, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(steel, tex)
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

    # Key from the camera's left and high, fill from the right, a cool rim
    # behind tracing the pole, and the warm wedge on the back wall.
    light("Key", (-9.0, -12.0, 10.0), 960.0, 5.0, (1.0, 0.95, 0.90), spread=34.0)
    light("Fill", (12.0, -8.5, 3.0), 120.0, 16.0, (0.72, 0.82, 1.0))
    light("Rim", (-3.5, 6.0, 6.0), 1000.0, 4.0, (0.62, 0.78, 1.0))
    light("Wedge", (9.0, 4.0, 6.0), 1350.0, 7.0, (1.0, 0.68, 0.38),
          target=(5.0, WALL_Y - 3.0, 0.0))

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
        scene.eevee.taa_render_samples = 64
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
    p.add_argument("--short-brace", action="store_true")
    p.add_argument("--drop-net", action="store_true")
    p.add_argument("--tilt-rim", action="store_true")
    p.add_argument("--loose-pad", action="store_true")
    p.add_argument("--float-ball", action="store_true")
    p.add_argument("--short-bolts", action="store_true")
    p.add_argument("--float-paint", action="store_true")
    args = p.parse_args(argv)

    code, low, steel, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_brace=args.short_brace,
        drop_net=args.drop_net,
        tilt_rim=args.tilt_rim,
        loose_pad=args.loose_pad,
        float_ball=args.float_ball,
        short_bolts=args.short_bolts,
        float_paint=args.float_paint,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, steel, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("basketball-hoop OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
