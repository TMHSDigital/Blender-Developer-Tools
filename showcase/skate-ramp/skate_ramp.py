"""Game-ready backyard quarter-pipe with a skateboard — a showcase piece, not an example.

Asserts budget conformance of a procedural 1.2 m skateboard quarter-pipe on
a 1.8 m transition, with a complete skateboard resting on its deck, after
composing shipped pipeline pieces: bmesh construction, UVs, nine materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

The frame is five transition templates cut from plywood — each a curved
band with a solid toe and an arm under the deck — standing on 2x4 sills,
with studs and a back post sistered to their faces, a lip joist behind the
coping and a rim joist at the back. Nine 2x4 stringers run across the
templates under the skin. The skin is two layers of 12 mm plywood in
full-width sheets, their seams offset between layers and every seam landing
on a stringer; a row of screws runs over each stringer, doubled where two
sheets meet. A steel coping pipe sits at the lip, standing a few millimetres
proud of the transition, with five bracket tabs welded to it and bolted to
the deck; a steel kicker plate, ground to a lip at its toe, carries the
transition down onto the ground over a timber toe block. A skateboard rests
on the deck near the coping: a seven-ply maple deck with concave and two
kicktails under grip tape, two trucks (baseplate, kingpin, bushings, cup
washer and nut, hanger with pivot arm, axle), four urethane wheels on
bearings, and eight mounting bolts through the grip.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--float-sill`` every sill on the ground,
``--short-rib`` every template seated on its sill and under the skin,
``--small-wheel`` every wheel on the deck, ``--sag-skin`` the transition's
circular arc, ``--sink-coping`` the coping's reveal, ``--proud-plate`` the
kicker plate flush with the skin, ``--stack-seams`` the staggered seams,
``--miss-screws`` every screw over a stringer, ``--skew-wheel`` the wheels
coaxial with their axles, ``--lift-grip`` one connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts are
not byte-identical across Blender versions — the LOD gate is a ratio band,
not an exact count.

    blender --background --python skate_ramp.py --
    blender --background --python skate_ramp.py -- --skip-decimate
    blender --background --python skate_ramp.py -- --output ramp.png
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

# --------------------------------------------------------------------------
# Design (metres). X runs up the ramp, Y across it, Z up. The transition is
# a circle of radius R about C = (0, R) in XZ, tangent to the ground at X=0.
# --------------------------------------------------------------------------
R = 1.80                    # transition radius: the riding surface
DECK_TOP = 1.200            # deck height
TH_TOP = 0.012              # top plywood layer
TH_IN = 0.012               # inner plywood layer
PLY_BITE = 0.0005           # inner layer bites the top layer; stringers bite the inner
R_IN0 = R + TH_TOP - PLY_BITE             # inner layer, concave face
R_IN1 = R_IN0 + TH_IN                     # inner layer, convex face (the underside)
R_STR = R_IN1 - PLY_BITE                 # stringer faces under the skin
STR_DEPTH = 0.038           # 2x4 laid flat: 38 mm radial, 89 mm along the arc
STR_HALF = 0.0445
RIB_BITE = 0.0009           # template edge into the inner layer's underside
R_RIB = R_IN1 - RIB_BITE
RIB_BAND = 0.22             # depth of each template's curved band
RIB_T = 0.018               # 18 mm plywood templates
SHEET_W = 1.220             # skin half width (8 ft sheets across the ramp)
FACET = 0.035               # arc facet length: every facet over 1 degree
S_PLATE = 0.40              # arc length of the kicker plate
PLATE_T = 0.006
PLATE_HALF = 1.200
TOE_LIP = 0.0008            # plate toe ground to this height
S_TOE_BACK = 0.56           # toe block's back, as arc length
STRINGER_S = (0.64, 0.84, 1.04, 1.24, 1.44, 1.64, 1.84, 2.04, 2.12)
TOP_SEAMS = (0.84, 1.84)
INNER_SEAMS = (1.24,)
SEAM_GAP = 0.0010
SEAM_ROW = 0.022            # screw rows either side of a seam
SCREW_Y = tuple(-1.14 + 0.19 * i for i in range(13))
SCREW_R = 0.0045
PIPE_R = 0.030              # 2-3/8 in coping
PIPE_RI = 0.0245
PIPE_HALF = 1.215
PIPE_PROUD = 0.004          # coping top above the deck
REVEAL = 0.005              # coping stands this far proud of the transition
PIPE_SEGS = 32
PIPE_STATIONS = 9
DECK_T = 0.018
X_BACK = 2.58
ARM_BITE = 0.0007
ARM_TOP = DECK_TOP - DECK_T + ARM_BITE
ARM_DEPTH = 0.22
SILL_H = 0.038
SILL_W = 0.089
RIB_BOT = SILL_H - 0.002
STUD_BOT = SILL_H - 0.0025
RIB_Y = (-1.2075, -0.60, 0.0, 0.60, 1.2075)
RIB_OUT = 1.2165            # outer templates' outer faces
TAB_Y = (-0.96, -0.48, 0.0, 0.48, 0.96)
DECK_SCREW_X = tuple(1.84 + 0.12 * i for i in range(7))

# Skateboard (local frame: U along the deck, V across it, Z up from the ramp deck)
BOARD_POS = (2.00, -0.35)
BOARD_YAW_DEG = 72.0
BOARD_L = 0.80
BOARD_W = 0.205
BOARD_T = 0.011
CONCAVE = 0.008
U_KICK = 0.232
KICK_DEG = 19.0
KICK_BLEND = 0.05
RW = 0.027                  # wheel radius (54 mm)
WHEEL_BITE = 0.0005         # wheel into the deck
AXLE_Z = RW - WHEEL_BITE
TRUCK_U = 0.190
WHEEL_V = 0.088
BP_BOT = AXLE_Z + 0.047     # baseplate underside
BP_T = 0.006
BOARD_BOT = BP_BOT + BP_T - 0.0004
BOARD_Z = BOARD_BOT + BOARD_T
KINGPIN_DEG = 35.0

# Falsifier displacements
FLOAT_SILL = 0.003
SHORT_RIB = 0.004
SMALL_WHEEL = 0.002
SAG_SKIN = 0.004
SINK_COPING = 0.006
PROUD_PLATE = 0.003
MISS_SCREWS = 0.060
SKEW_WHEEL = 0.002
LIFT_GRIP = 0.001

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from the vertices.
OUTER_SIZE = (2.529, 2.440, 1.339)
BASE_TRIS_MIN = 30600
BASE_TRIS_MAX = 31700
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 9
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 380
BAKE_RES = 1024
CAGE_EXTRUSION = 0.003
# per slot: ply, framing, steel, hardware, maple, grip, urethane, alloy, bushing
FACE_FLOORS = (3100, 1400, 1030, 6940, 1045, 855, 1460, 850, 440)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Templates: seated on their sills, and their curved edge under the skin.
RIB_SEAT_MIN = 0.0010
RIB_SEAT_MAX = 0.0060
RIB_BITE_MIN = 0.0003
RIB_BITE_MAX = 0.0025
# Wheels on the deck.
WHEEL_BITE_MIN = 0.0002
WHEEL_BITE_MAX = 0.0012
# Transition: a circle of the declared radius, tangent to the ground.
RADIUS_TOL = 0.005
ARC_DEV_MAX = 0.0010
TANGENT_TOL = 0.002
HEIGHT_TOL = 0.005
# Coping.
REVEAL_MIN = 0.002
REVEAL_MAX = 0.008
PROUD_MIN = 0.0
PROUD_MAX = 0.008
STRAIGHT_TOL = 0.0005
PARALLEL_MAX_DEG = 0.2
# Kicker plate.
STEP_MAX = 0.0006
TOE_MAX = 0.0012
# Seams and screws.
SEAM_STAGGER_MIN = 0.30
SEAM_ON_STRINGER = 0.015
SCREW_EDGE_MIN = 0.008
SCREW_SHEET_MIN = 0.005
# Trucks.
COAX_TOL = 0.0003
COAX_ANGLE_MAX_DEG = 0.5
HERO_YAW_DEG = -2.0
WALL_Y = 3.2

PLY_IDX, FRAME_IDX, STEEL_IDX, HW_IDX, MAPLE_IDX = 0, 1, 2, 3, 4
GRIP_IDX, URETHANE_IDX, ALLOY_IDX, BUSHING_IDX = 5, 6, 7, 8
BEVEL_BY_MAT = {PLY_IDX: 0.0015, FRAME_IDX: 0.0020, STEEL_IDX: 0.0008, MAPLE_IDX: 0.0012,
                ALLOY_IDX: 0.0006}

# Part tags: a face attribute naming which part a face belongs to, so the
# audits can find the shells they measure. Every measured value is read from
# the vertices, never from these constants.
(T_NONE, T_TOP, T_INNER, T_RIB, T_STRINGER, T_SILL, T_STUD, T_TOE, T_PLATE, T_COPING,
 T_DECK, T_JOIST, T_TAB, T_SCREW, T_FASTENER, T_BOARD, T_GRIP, T_WHEEL, T_AXLE, T_TRUCK,
 T_BEARING, T_BUSHING) = range(22)

ZAX = Vector((0.0, 0.0, 1.0))
YAX = Vector((0.0, 1.0, 0.0))
XAX = Vector((1.0, 0.0, 0.0))
# local (u, v, w) -> world (x, z, y): outlines drawn in the side view, extruded across
XZY = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))


def arc_pt(r, ph, y=0.0):
    return Vector((r * math.sin(ph), y, R - r * math.cos(ph)))


def radial(ph):
    """Outward from the centre (into the ramp)."""
    return Vector((math.sin(ph), 0.0, -math.cos(ph)))


def tangent(ph):
    return Vector((math.cos(ph), 0.0, math.sin(ph)))


def phis(ph0, ph1, r):
    n = max(2, int(math.ceil(abs(ph1 - ph0) * r / FACET)))
    return [ph0 + (ph1 - ph0) * i / n for i in range(n + 1)]


def _coping_axis(sink):
    d = R + PIPE_R - REVEAL + sink
    z = DECK_TOP + PIPE_PROUD - PIPE_R
    return Vector((math.sqrt(d * d - (z - R) ** 2), 0.0, z))


PIPE_A = _coping_axis(0.0)


def _end_angle():
    """Where the riding surface enters the coping 3 mm deep (bisection)."""
    a = PIPE_A
    ph_a = math.atan2(a.x, R - a.z)
    lo, hi = ph_a - 0.08, ph_a
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if (arc_pt(R, mid) - a).length > PIPE_R - 0.003:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


PH_END = _end_angle()
PH_PLATE = S_PLATE / R
PH_TOE = math.acos((R - TOE_LIP) / R)


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
# Construction helpers (copied from showcase/road-bicycle, not imported)
# --------------------------------------------------------------------------

class Build:
    """The bmesh under construction, its part-tag layer, named vertex groups
    (for the falsifiers that move one assembly) and the bevel set."""

    def __init__(self, bm):
        self.bm = bm
        self.tag = bm.faces.layers.int.new("part")
        self.ply = bm.verts.layers.float.new("plyfrac")
        self.bev = bm.verts.layers.int.new("bev")
        self.groups = {}

    def mark_bevel(self, verts):
        for v in verts:
            v[self.bev] = 1

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
            self.b.mark_bevel(vs)
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
    n = len(profile)
    last = n - 1 if solid else n
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for j in range(last):
            k = (j + 1) % n
            bm.faces.new((r0[j], r1[j], r1[k], r0[k])).material_index = mat_idx
    if solid:
        bm.faces.new([rings[i][0] for i in reversed(range(segs))]).material_index = mat_idx
        bm.faces.new([rings[i][n - 1] for i in range(segs)]).material_index = mat_idx
    return [v for ring in rings for v in ring]


def lathe_on(bm, profile, segs, mat_idx, center, axis, ref=XAX, solid=True, phase=0.0):
    if abs(Vector(axis).normalized().dot(Vector(ref))) > 0.9:
        ref = ZAX if abs(Vector(axis).normalized().z) < 0.9 else YAX
    return add_lathe(bm, profile, segs, mat_idx, center=center, rot=frame(axis, ref),
                     solid=solid, phase=phase)


def add_sweep(bm, pts, radius, sides, mat_idx, phase=0.0, ref=None):
    """Capped tube swept along a polyline with parallel-transport frames."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tans = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    if ref is None:
        ref = ZAX if abs(tans[0].z) < 0.9 else XAX
    nrm = (Vector(ref) - tans[0] * Vector(ref).dot(tans[0])).normalized()
    rings = []
    for p, t in zip(pts, tans):
        nrm = (nrm - t * nrm.dot(t)).normalized()
        bi = t.cross(nrm)
        rings.append([bm.verts.new(p + radius * (nrm * math.cos(phase + 2.0 * math.pi * k / sides)
                                                 + bi * math.sin(phase + 2.0 * math.pi * k / sides)))
                      for k in range(sides)])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            bm.faces.new((r0[k], r0[m], r1[m], r1[k])).material_index = mat_idx
    bm.faces.new(tuple(reversed(rings[0]))).material_index = mat_idx
    bm.faces.new(tuple(rings[-1])).material_index = mat_idx
    return [v for ring in rings for v in ring]


def rrect(ha, hb, rc, n_corner=2):
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


def add_sheet(bm, surf, nu, nv, thick, mat_idx):
    """A closed plate: ``surf(u, v) -> (point, normal)`` over the unit square,
    offset ``thick`` back along the normal, rims stitched round the edge.
    Returns (front verts, back verts)."""
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
    return [v for row in front for v in row], [v for row in back for v in row]


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
# The ramp
# --------------------------------------------------------------------------

def arc_slab(bm, ph0, ph1, r_in, r_out, y0, y1, mat_idx, clamp=False):
    """A curved sheet between radii ``r_in(ph)`` (the face toward the centre)
    and ``r_out(ph)``, from angle ph0 to ph1, across y0..y1."""
    rings = []
    for ph in phis(ph0, ph1, R):
        ri, ro = r_in(ph), r_out(ph)
        pts = [arc_pt(ri, ph, y0), arc_pt(ro, ph, y0), arc_pt(ro, ph, y1), arc_pt(ri, ph, y1)]
        if clamp:
            pts = [Vector((p.x, p.y, max(p.z, 0.0))) for p in pts]
        rings.append(pts)
    return add_loft(bm, rings, mat_idx)


def sheet_spans(seams, s0, s1):
    edges = [s0] + [s for s in seams] + [s1]
    spans = []
    for k in range(len(edges) - 1):
        a = edges[k] + (SEAM_GAP * 0.5 if k > 0 else 0.0)
        b = edges[k + 1] - (SEAM_GAP * 0.5 if k + 1 < len(edges) - 1 else 0.0)
        spans.append((a, b))
    return spans


def add_skin(b, sag_skin, top_seams, inner_seams):
    s_end = PH_END * R
    top = sheet_spans(top_seams, S_PLATE + 0.001, s_end)
    faces = []
    for k, (s0, s1) in enumerate(top):
        sag = sag_skin and k == 1

        def r_in(ph, s0=s0, s1=s1, sag=sag):
            if not sag:
                return R
            # sin^2: level with its neighbours at both ends, 4 mm down mid-sheet
            return R + SAG_SKIN * math.sin(math.pi * (ph * R - s0) / (s1 - s0)) ** 2

        def r_out(ph, r_in=r_in):
            return r_in(ph) + TH_TOP
        # neighbouring sheets' side edges stand 0.3 mm apart: never one plane
        w = SHEET_W - 0.0006 * (k % 2)
        with b.part(T_TOP, "top", bevel=True):
            arc_slab(b.bm, s0 / R, s1 / R, r_in, r_out, -w, w, PLY_IDX)
        faces.append((s0, s1, r_in))
    inner = sheet_spans(inner_seams, S_PLATE + 0.003, s_end + 0.0026)
    for k, (s0, s1) in enumerate(inner):
        w = SHEET_W - 0.0012 - 0.0006 * (k % 2)
        with b.part(T_INNER, "inner", bevel=True):
            arc_slab(b.bm, s0 / R, s1 / R, lambda ph: R_IN0, lambda ph: R_IN1, -w, w, PLY_IDX)
    return faces


def add_plate(b, proud_plate):
    """Kicker plate: its top flush with the riding surface, its bottom on the
    toe block, clamped to the ground where the offset surface dips below it
    so the toe is ground to a lip."""
    def r_in(ph):
        if not proud_plate:
            return R
        return R - PROUD_PLATE * max(0.0, (ph - PH_TOE) / (PH_PLATE - PH_TOE))
    with b.part(T_PLATE, "plate"):
        vs = arc_slab(b.bm, PH_TOE, PH_PLATE, r_in, lambda ph: R + PLATE_T,
                      -PLATE_HALF, PLATE_HALF, STEEL_IDX, clamp=True)
    # every chamfer but the toe's (0.8 mm: nothing to chamfer)
    b.mark_bevel(vs[4:])
    # two rows of countersunk screws into the toe block
    for s in (0.20, 0.34):
        ph = s / R
        for y in (-1.05, -0.75, -0.45, -0.15, 0.15, 0.45, 0.75, 1.05):
            with b.part(T_FASTENER):
                lathe_on(b.bm, [(0.0050, -0.0020), (0.0050, 0.0), (0.0038, 0.00025)], 8, HW_IDX,
                         arc_pt(r_in(ph), ph, y), -radial(ph))


def add_toe_block(b):
    r1 = R + PLATE_T - 0.0004          # under the plate
    r2 = R_IN1 - PLY_BITE              # under the inner layer
    ph_a = math.acos((R - 0.003) / r1)
    ph_step = (S_PLATE + 0.002) / R
    ph_w = S_TOE_BACK / R
    x_w = r2 * math.sin(ph_w)
    out = [(r1 * math.sin(ph_a), 0.0), (x_w, 0.0)]
    for ph in reversed(phis(ph_step, ph_w, r2)):
        p = arc_pt(r2, ph)
        out.append((p.x, p.z))
    for ph in reversed(phis(ph_a, ph_step, r1)):
        p = arc_pt(r1, ph)
        out.append((p.x, p.z))
    out[-1] = (out[0][0], out[-1][1])
    with b.part(T_TOE, "toe", bevel=True):
        add_prism(b.bm, out, -1.21, 1.21, (0.0, 0.0, 0.0), XZY, FRAME_IDX)
    return x_w


def rib_outline(x_toe, extra=0.0):
    r_in = R_RIB + extra
    r_out = R_RIB + RIB_BAND
    ph0 = math.asin(x_toe / r_in)
    ph1 = math.acos((R - ARM_TOP) / r_in)
    pts = [(x_toe, RIB_BOT)]
    for ph in phis(ph0, ph1, r_in):
        p = arc_pt(r_in, ph)
        pts.append((p.x, p.z))
    pts.append((X_BACK - 0.010, ARM_TOP))
    z_arm = ARM_TOP - ARM_DEPTH
    pts.append((X_BACK - 0.010, z_arm))
    ph_a = math.acos((R - z_arm) / r_out)
    ph_b = math.acos((R - RIB_BOT) / r_out)
    for ph in phis(ph_a, ph_b, r_out):
        p = arc_pt(r_out, ph)
        pts.append((p.x, p.z))
    return pts


def z_outer(x):
    r_out = R_RIB + RIB_BAND
    if x >= r_out:
        return 9.0
    return R - math.sqrt(r_out * r_out - x * x)


def add_frame(b, x_toe_block, short_rib, float_sill):
    x_toe = x_toe_block - 0.004
    for k, yc in enumerate(RIB_Y):
        outer = abs(yc) > 1.0
        y0, y1 = yc - RIB_T * 0.5, yc + RIB_T * 0.5
        extra = SHORT_RIB if (short_rib and k == 2) else 0.0
        with b.part(T_RIB, f"rib{k}", bevel=True):
            add_prism(b.bm, rib_outline(x_toe, extra), y0, y1, (0.0, 0.0, 0.0), XZY, PLY_IDX)
        # studs and a back post sistered to the template's inboard face
        side = -math.copysign(1.0, yc) if outer else -1.0
        face = y0 if side < 0 else y1
        sy0, sy1 = sorted((face + side * 0.036, face - side * 0.002))
        for xs in (1.30, 1.62, 2.10):
            xa, xb = xs - 0.0445, xs + 0.0445
            top_a = min(z_outer(xa), ARM_TOP - ARM_DEPTH) + 0.05
            top_b = min(z_outer(xb), ARM_TOP - ARM_DEPTH) + 0.05
            with b.part(T_STUD, bevel=True):
                add_prism(b.bm, [(xa, STUD_BOT), (xb, STUD_BOT), (xb, top_b), (xa, top_a)],
                          sy0, sy1, (0.0, 0.0, 0.0), XZY, FRAME_IDX)
        with b.part(T_STUD, bevel=True):
            add_prism(b.bm, [(X_BACK - 0.125, STUD_BOT), (X_BACK - 0.036, STUD_BOT),
                             (X_BACK - 0.036, DECK_TOP - DECK_T + 0.0002),
                             (X_BACK - 0.125, DECK_TOP - DECK_T + 0.0002)],
                      sy0, sy1, (0.0, 0.0, 0.0), XZY, FRAME_IDX)
        # the sill under template and studs
        if outer:
            s_out = math.copysign(RIB_OUT - 0.003, yc)
            ya, yb = sorted((s_out, s_out - math.copysign(SILL_W, yc)))
        else:
            # centred under template and stud together
            ya, yb = y0 - 0.0545, y0 + 0.0345
        lift = FLOAT_SILL if (float_sill and k == 2) else 0.0
        xa, xb = x_toe_block - 0.010, X_BACK - 0.005
        with b.part(T_SILL, "sill_mid" if k == 2 else "sill", bevel=True):
            add_rbox(b.bm, 0.5 * (xb - xa), 0.5 * SILL_H, 0.004,
                     [(0.0, ya), (0.0, yb)],
                     (0.5 * (xa + xb), 0.0, 0.5 * SILL_H + lift), XZY, FRAME_IDX)
    # stringers across the templates, ends buried in the outer ones
    for k, s in enumerate(STRINGER_S):
        ph = s / R
        # neighbours' end cuts 0.3 mm apart, so no two share a plane
        end = RIB_OUT - 0.005 - 0.0003 * (k % 2)
        with b.part(T_STRINGER, bevel=True):
            add_rbox(b.bm, STR_HALF, 0.5 * STR_DEPTH, 0.003, [(0.0, -end), (0.0, end)],
                     arc_pt(R_STR + 0.5 * STR_DEPTH, ph), frame(YAX, tangent(ph)), FRAME_IDX)
    # lip joist behind the coping and rim joist at the back, under the deck
    deck_bot = DECK_TOP - DECK_T
    for x0, x1 in ((PIPE_A.x + 0.022, PIPE_A.x + 0.060), (X_BACK - 0.038, X_BACK)):
        with b.part(T_JOIST, bevel=True):
            add_rbox(b.bm, 0.5 * (x1 - x0), 0.070, 0.004,
                     [(0.0, -(RIB_OUT - 0.0058)), (0.0, RIB_OUT - 0.0058)],
                     (0.5 * (x0 + x1), 0.0, deck_bot + 0.0004 - 0.070), XZY, FRAME_IDX)


def add_deck(b):
    x0 = PIPE_A.x + 0.016
    x1 = X_BACK + 0.003
    with b.part(T_DECK, "deck", bevel=True):
        add_prism(b.bm, [(x0, -1.2185), (x1, -1.2185), (x1, 1.2185), (x0, 1.2185)],
                  DECK_TOP - DECK_T, DECK_TOP, (0.0, 0.0, 0.0), Matrix.Identity(3), PLY_IDX)
    # deck screws along every template's arm
    for yc in RIB_Y:
        for x in DECK_SCREW_X:
            with b.part(T_FASTENER):
                lathe_on(b.bm, [(SCREW_R, -0.0015), (SCREW_R, 0.0001), (0.0032, 0.0004)], 8, HW_IDX,
                         (x, yc, DECK_TOP), ZAX)


def add_coping(b, sink_coping):
    a = _coping_axis(SINK_COPING if sink_coping else 0.0)
    prof = [(PIPE_R, -PIPE_HALF + 2 * PIPE_HALF * i / (PIPE_STATIONS - 1))
            for i in range(PIPE_STATIONS)]
    prof += [(PIPE_RI, z) for _r, z in reversed(prof)]
    with b.part(T_COPING, "coping", bevel=True):
        add_lathe(b.bm, prof, PIPE_SEGS, STEEL_IDX, center=(a.x, 0.0, a.z),
                  rot=frame(YAX, XAX), phase=math.pi / PIPE_SEGS)
    # bracket tabs welded to the pipe's back and bolted down to the deck
    for yt in TAB_Y:
        with b.part(T_TAB, bevel=True):
            add_rbox(b.bm, 0.0365, 0.030, 0.006, [(0.0, DECK_TOP - 0.0004),
                                                   (0.0, DECK_TOP + 0.0036)],
                     (PIPE_A.x + 0.0485, yt, 0.0), Matrix.Identity(3), STEEL_IDX)
        for n, dx in enumerate((0.046, 0.070)):
            dz = 0.0002 * n
            with b.part(T_FASTENER):
                lathe_on(b.bm, [(0.0080, -0.0005 + dz), (0.0080, 0.0008 + dz), (0.0066, 0.0026 + dz),
                                (0.0040, 0.0038 + dz), (0.0015, 0.0042 + dz)], 12, HW_IDX,
                         (PIPE_A.x + dx, yt, DECK_TOP + 0.0036), ZAX, phase=n * math.pi / 12)


def add_skin_screws(b, top_seams, miss_screws, sheets):
    """A row over every stringer, two where sheets meet; each head is set
    into the face of the sheet it holds down (``sheets``: (s0, s1, r_in))."""
    rows = []
    for s in STRINGER_S:
        if any(abs(s - t) < 1e-6 for t in top_seams):
            rows += [s - SEAM_ROW, s + SEAM_ROW]
        else:
            rows.append(s + (MISS_SCREWS if (miss_screws and abs(s - 1.44) < 1e-6) else 0.0))
    for s in rows:
        ph = s / R
        r_face = next(r_in for s0, s1, r_in in sheets if s0 <= s <= s1)(ph)
        for y in SCREW_Y:
            with b.part(T_SCREW):
                lathe_on(b.bm, [(SCREW_R, -0.0015), (SCREW_R, 0.0001), (0.0032, 0.0004)], 8, HW_IDX,
                         arc_pt(r_face, ph, y), -radial(ph))


# --------------------------------------------------------------------------
# The skateboard (built in its own frame, then set on the deck)
# --------------------------------------------------------------------------

def board_half_width(u, inset=0.0):
    """The deck's plan outline, or that outline offset ``inset`` inward
    (the round ends stay concentric, so the grip's edge follows the rail)."""
    rn = 0.5 * BOARD_W - inset
    d = abs(u) - 0.5 * (BOARD_L - BOARD_W)
    if d <= 0.0:
        return rn
    return math.sqrt(max(rn * rn - d * d, 0.0))


def board_top(u, v):
    d = abs(u) - U_KICK
    kt = math.tan(math.radians(KICK_DEG))
    if d <= 0.0:
        kick = 0.0
    elif d < KICK_BLEND:
        kick = kt * d * d / (2.0 * KICK_BLEND)
    else:
        kick = kt * (d - 0.5 * KICK_BLEND)
    # the concave runs through the kicks: a translational surface, so the
    # grip's faces never share a plane with the deck's (a fading concave
    # twists the kicks and lined up 28 grip-deck face pairs)
    conc = CONCAVE * (2.0 * v / BOARD_W) ** 2
    return BOARD_Z + kick + conc


def board_surf(inset, lift):
    half = 0.5 * BOARD_L - 0.0015 - inset

    def surf(a, bb):
        u = half * math.sin((2.0 * a - 1.0) * 0.5 * math.pi)
        w = max(board_half_width(u, inset), 0.004)
        v = (2.0 * bb - 1.0) * w
        e = 1e-4
        z = board_top(u, v)
        du = (board_top(u + e, v) - board_top(u - e, v)) / (2 * e)
        dv = (board_top(u, v + e) - board_top(u, v - e)) / (2 * e)
        n = Vector((-du, -dv, 1.0)).normalized()
        return Vector((u, v, z + lift)), n
    return surf


def add_wheel(b, centre, small, tag_group):
    shrink = SMALL_WHEEL if small else 0.0
    prof = [(0.0106, -0.0150), (0.0200, -0.0160), (0.0238, -0.0158), (0.0258, -0.0148),
            (0.0268, -0.0128), (0.0270, -0.0100), (0.0270, 0.0100), (0.0268, 0.0128),
            (0.0258, 0.0148), (0.0238, 0.0158), (0.0200, 0.0160), (0.0106, 0.0150)]
    prof = [(r - shrink * (r - 0.0106) / (RW - 0.0106), z) for r, z in prof]
    with b.part(T_WHEEL, tag_group):
        add_lathe(b.bm, prof, 32, URETHANE_IDX, center=centre, rot=frame(YAX, XAX))
    for sgn in (-1.0, 1.0):
        bp = [(0.0036, sgn * 0.0145), (0.0110, sgn * 0.0145), (0.0110, sgn * 0.0075),
              (0.0036, sgn * 0.0075)]
        if sgn > 0:
            bp = list(reversed(bp))
        with b.part(T_BEARING):
            add_lathe(b.bm, bp, 16, HW_IDX, center=centre, rot=frame(YAX, XAX),
                      phase=(math.pi / 16 if sgn > 0 else 0.0))


def add_truck(b, sgn, small_wheel, skew_wheel):
    """One truck at u = sgn * TRUCK_U; its kingpin on the inboard side."""
    uc = sgn * TRUCK_U
    with b.part(T_TRUCK, bevel=True):
        add_rbox(b.bm, 0.034, 0.030, 0.008, [(0.0, BP_BOT), (0.0, BP_BOT + BP_T)],
                 (uc, 0.0, 0.0), Matrix.Identity(3), ALLOY_IDX)
    k = Vector((-sgn * math.sin(math.radians(KINGPIN_DEG)), 0.0,
                -math.cos(math.radians(KINGPIN_DEG))))
    k0 = Vector((uc - sgn * 0.020, 0.0, BP_BOT + 0.002))
    with b.part(T_FASTENER):
        lathe_on(b.bm, [(0.0035, -0.004), (0.0035, 0.050)], 12, HW_IDX, k0, k)
    with b.part(T_BUSHING):
        lathe_on(b.bm, [(0.0080, 0.001), (0.0112, 0.0025), (0.0118, 0.0080), (0.0112, 0.0135),
                        (0.0090, 0.0145)], 20, BUSHING_IDX, k0, k)
    with b.part(T_BUSHING):
        lathe_on(b.bm, [(0.0085, 0.0240), (0.0102, 0.0252), (0.0106, 0.0290), (0.0100, 0.0328),
                        (0.0085, 0.0338)], 20, BUSHING_IDX, k0, k)
    with b.part(T_FASTENER):
        lathe_on(b.bm, [(0.0060, 0.0332), (0.0125, 0.0336), (0.0128, 0.0352), (0.0060, 0.0356)],
                 20, HW_IDX, k0, k)
    with b.part(T_FASTENER):
        lathe_on(b.bm, [(0.0068, 0.0352), (0.0068, 0.0420), (0.0050, 0.0428)], 6, HW_IDX, k0, k)
    seat = k0 + k * 0.019
    with b.part(T_TRUCK, bevel=True):
        lathe_on(b.bm, [(0.0140, 0.0130), (0.0148, 0.0140), (0.0148, 0.0240), (0.0140, 0.0250)],
                 20, ALLOY_IDX, k0, k)
    # hanger: axle housing, a tapered body up to the kingpin seat, pivot arm
    ax = Vector((uc, 0.0, AXLE_Z))
    with b.part(T_TRUCK):
        lathe_on(b.bm, [(0.0082, -0.0690), (0.0100, -0.0660), (0.0106, -0.0560),
                        (0.0106, 0.0560), (0.0100, 0.0660), (0.0082, 0.0690)], 20, ALLOY_IDX,
                 ax, YAX, ref=XAX)
    d = (seat - ax)
    axis = d.normalized()
    w = YAX.cross(axis).normalized()
    rings = []
    for t, hv, hw in ((0.0, 0.050, 0.0095), (0.45, 0.030, 0.0105), (0.85, 0.016, 0.0112)):
        c = ax + d * t
        rings.append([c + YAX * x + w * y for x, y in rrect(hv, hw, 0.004, 2)])
    with b.part(T_TRUCK, bevel=True):
        add_loft(b.bm, rings, ALLOY_IDX)
    pivot = Vector((uc + sgn * 0.024, 0.0, BP_BOT + 0.001))
    arm0 = ax + Vector((sgn * 0.004, 0.0, 0.006))
    with b.part(T_TRUCK):
        add_sweep(b.bm, [arm0, arm0.lerp(pivot, 0.5), pivot], 0.0055, 12, ALLOY_IDX)
    with b.part(T_TRUCK):
        lathe_on(b.bm, [(0.0085, -0.0100), (0.0085, 0.0015)], 16, ALLOY_IDX, pivot,
                 (pivot - arm0).normalized())
    # axle, nuts, wheels
    with b.part(T_AXLE, "axle"):
        lathe_on(b.bm, [(0.0040, -0.108), (0.0040, 0.108)], 12, HW_IDX, ax, YAX, ref=XAX)
    for vs in (-1.0, 1.0):
        with b.part(T_FASTENER):
            lathe_on(b.bm, [(0.0036, vs * 0.1036), (0.0068, vs * 0.1036), (0.0068, vs * 0.1096),
                            (0.0036, vs * 0.1096)] if vs < 0 else
                     [(0.0036, 0.1096), (0.0068, 0.1096), (0.0068, 0.1036), (0.0036, 0.1036)],
                     6, HW_IDX, ax, YAX, ref=XAX, solid=False)
    for vs in (-1.0, 1.0):
        idx = (0 if sgn > 0 else 2) + (0 if vs < 0 else 1)
        c = Vector((uc, vs * WHEEL_V, AXLE_Z))
        if skew_wheel and idx == 0:
            c.x += SKEW_WHEEL
        add_wheel(b, c, small_wheel and idx == 0, f"wheel{idx}")


def add_skateboard(b, small_wheel, skew_wheel, lift_grip):
    bm = b.bm
    nv0 = len(bm.verts)
    with b.part(T_BOARD, bevel=True):
        front, back = add_sheet(bm, board_surf(0.0, 0.0), 40, 10, BOARD_T, MAPLE_IDX)
    for v in front:
        v[b.ply] = 1.0
    for v in back:
        v[b.ply] = 0.0
    lg = LIFT_GRIP if lift_grip else 0.0
    with b.part(T_GRIP, "grip"):
        add_sheet(bm, board_surf(0.002, 0.0005 + lg), 40, 10, 0.0008, GRIP_IDX)
    for sgn in (-1.0, 1.0):
        uc = sgn * TRUCK_U
        for n, (du, dv) in enumerate(((-0.027, -0.0205), (-0.027, 0.0205), (0.027, -0.0205),
                                      (0.027, 0.0205))):
            u, v = uc + du, dv
            # each head 0.15 mm higher than the last: no two tops share a plane;
            # they bite the grip only, never the deck under it
            dz = 0.00015 * n
            p = Vector((u, v, board_top(u, v) + 0.0005 + lg))
            with b.part(T_FASTENER, "grip"):
                lathe_on(bm, [(0.0042, -0.00055 + dz), (0.0042, 0.0004 + dz),
                              (0.0030, 0.0007 + dz)], 8, HW_IDX, p, ZAX, phase=0.2 * n)
        add_truck(b, sgn, small_wheel, skew_wheel)
    m = (Matrix.Translation((BOARD_POS[0], BOARD_POS[1], DECK_TOP))
         @ Matrix.Rotation(math.radians(BOARD_YAW_DEG), 4, "Z"))
    bm.verts.ensure_lookup_table()
    for i in range(nv0, len(bm.verts)):
        bm.verts[i].co = m @ bm.verts[i].co


def build_ramp_mesh(name, bevel_scale, bevel_segments, float_sill=False, short_rib=False,
                    small_wheel=False, sag_skin=False, sink_coping=False, proud_plate=False,
                    stack_seams=False, miss_screws=False, skew_wheel=False, lift_grip=False):
    bm = bmesh.new()
    try:
        b = Build(bm)
        # the inner joint 10 mm from the top one: stacked, still on its stringer
        inner_seams = (0.85,) if stack_seams else INNER_SEAMS
        sheets = add_skin(b, sag_skin, TOP_SEAMS, inner_seams)
        add_plate(b, proud_plate)
        x_w = add_toe_block(b)
        add_frame(b, x_w, short_rib, float_sill)
        add_deck(b)
        add_coping(b, sink_coping)
        add_skin_screws(b, TOP_SEAMS, miss_screws, sheets)
        add_skateboard(b, small_wheel, skew_wheel, lift_grip)

        # consistent winding and fresh normals, or every dihedral reads 0
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        if bevel_scale > 0.0:
            for mat_idx, off in sorted(BEVEL_BY_MAT.items()):
                bm.edges.index_update()
                edges = sorted(
                    {e for e in bm.edges if e.verts[0][b.bev] and e.verts[1][b.bev]
                     and len(e.link_faces) == 2
                     and all(f.material_index == mat_idx for f in e.link_faces)
                     and e.calc_face_angle() > math.radians(60.0)},
                    key=lambda e: e.index,
                )
                if edges:
                    bmesh.ops.bevel(bm, geom=edges, offset=off * bevel_scale,
                                    segments=bevel_segments, profile=0.5, affect="EDGES",
                                    clamp_overlap=True, material=mat_idx)

        bm.verts.layers.int.remove(b.bev)
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
                edge.smooth = edge.calc_face_angle() < math.radians(40.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    paint_attributes(me)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


# --------------------------------------------------------------------------
# Surface attributes for the shaders
# --------------------------------------------------------------------------

def _long_axis(pts):
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    q = p - p.mean(axis=0)
    w, vecs = np.linalg.eigh(q.T @ q / len(p))
    v = Vector(vecs[:, 2]).normalized()
    return v if (v.x + v.y + v.z) >= 0.0 else -v


def paint_attributes(me):
    """Per-shell ``PlankTone`` and ``GrainDir`` for every sheet and stick of
    timber (grain along its own long axis), and ``Ride`` on the riding
    surface's sheets, where the shader lays wheel marks and the stencil."""
    tags = [0] * len(me.polygons)
    attr = me.attributes.get("part")
    if attr is not None:
        attr.data.foreach_get("value", tags)
    tone = [0.5] * len(me.polygons)
    grain = [(0.0, 1.0, 0.0)] * len(me.polygons)
    ride = [0.0] * len(me.polygons)
    owner = {}
    for n, g in enumerate(shells(me)):
        pts = [me.vertices[i].co for i in g]
        d = _long_axis(pts) if len(pts) > 2 else YAX
        t = 0.5 + 0.28 * math.sin(n * 2.399 + 0.7) * math.cos(n * 0.913)
        for i in g:
            owner[i] = (t, tuple(d))
    for poly in me.polygons:
        t, d = owner[poly.vertices[0]]
        tone[poly.index] = t
        grain[poly.index] = d
        ride[poly.index] = 1.0 if tags[poly.index] == T_TOP else 0.0
    a = me.attributes.new("PlankTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)
    g = me.attributes.new("GrainDir", "FLOAT_VECTOR", "FACE")
    g.data.foreach_set("vector", [c for v in grain for c in v])
    r = me.attributes.new("Ride", "FLOAT", "FACE")
    r.data.foreach_set("value", ride)


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def _sock(sockets, identifier):
    """A Mix-node socket by identifier; its A/B/Result names repeat per type."""
    return next(sk for sk in sockets if sk.identifier == identifier)


def _mix(nt, a, b, fac, blend="MIX"):
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = blend
    if isinstance(fac, float):
        _sock(mix.inputs, "Factor_Float").default_value = fac
    else:
        nt.links.new(fac, _sock(mix.inputs, "Factor_Float"))
    for sock, val in (("A_Color", a), ("B_Color", b)):
        if isinstance(val, tuple):
            _sock(mix.inputs, sock).default_value = val
        else:
            nt.links.new(val, _sock(mix.inputs, sock))
    return _sock(mix.outputs, "Result_Color")


def _math(nt, op, a, b=None):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = op
    for i, val in enumerate((a, b)):
        if val is None:
            continue
        if isinstance(val, float):
            m.inputs[i].default_value = val
        else:
            nt.links.new(val, m.inputs[i])
    return m.outputs["Value"]


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
    showcase/road-bicycle). On a dark stage a metal mirrors the dark stage and
    reads as grey plastic; here the world-space reflection vector looks up a
    soft studio — a bright horizon band, a dim ceiling, the floor dark only
    straight down, the key's side brighter — added as emission."""
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
    side = _math(nt, "MULTIPLY", mx.outputs["Result"], env)
    tint = _mix(nt, ramp.outputs["Color"], color, 1.0, "MULTIPLY")
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tint, em.inputs["Color"])
    nt.links.new(side, em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(bsdf.outputs["BSDF"], add.inputs[0])
    nt.links.new(em.outputs["Emission"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
    return mat


def wood(name, dark, light, grain_scale, rough=(0.74, 0.56), ride=False):
    """Grain along each sheet and stick (``GrainDir``), tone per piece
    (``PlankTone``); on the riding sheets (``Ride``) a worn stencilled roundel
    and wheel marks running up the transition."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    gdir = nt.nodes.new("ShaderNodeAttribute")
    gdir.attribute_name = "GrainDir"
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "PlankTone"
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(coord.outputs["Object"], dot.inputs[0])
    nt.links.new(gdir.outputs["Vector"], dot.inputs[1])
    along = nt.nodes.new("ShaderNodeVectorMath")
    along.operation = "SCALE"
    nt.links.new(gdir.outputs["Vector"], along.inputs[0])
    nt.links.new(_math(nt, "MULTIPLY", dot.outputs["Value"], 0.94), along.inputs["Scale"])
    grain_co = nt.nodes.new("ShaderNodeVectorMath")
    grain_co.operation = "SUBTRACT"
    nt.links.new(coord.outputs["Object"], grain_co.inputs[0])
    nt.links.new(along.outputs["Vector"], grain_co.inputs[1])
    shift = nt.nodes.new("ShaderNodeVectorMath")
    shift.operation = "ADD"
    nt.links.new(grain_co.outputs["Vector"], shift.inputs[0])
    nt.links.new(tone.outputs["Fac"], shift.inputs[1])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = grain_scale
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.62
    nt.links.new(shift.outputs["Vector"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = dark + (1.0,)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = light + (1.0,)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    gain = _math(nt, "MULTIPLY_ADD", tone.outputs["Fac"], 0.55)
    gain.node.inputs[2].default_value = 0.72
    col = _mix(nt, ramp.outputs["Color"], gain, 1.0, "MULTIPLY")
    rough_n = nt.nodes.new("ShaderNodeMapRange")
    rough_n.inputs["To Min"].default_value = rough[0]
    rough_n.inputs["To Max"].default_value = rough[1]
    nt.links.new(noise.outputs["Fac"], rough_n.inputs["Value"])
    rough_out = rough_n.outputs["Result"]
    if ride:
        rattr = nt.nodes.new("ShaderNodeAttribute")
        rattr.attribute_name = "Ride"
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(coord.outputs["Object"], sep.inputs[0])
        # stencilled roundel, seen square-on from the front: a ring and a dot
        comb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(sep.outputs["Y"], comb.inputs["Y"])
        nt.links.new(sep.outputs["Z"], comb.inputs["Z"])
        dist = nt.nodes.new("ShaderNodeVectorMath")
        dist.operation = "DISTANCE"
        nt.links.new(comb.outputs["Vector"], dist.inputs[0])
        dist.inputs[1].default_value = (0.0, -0.42, 0.66)
        d = dist.outputs["Value"]
        ring = _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", d, 0.215),
                     _math(nt, "LESS_THAN", d, 0.275))
        dotm = _math(nt, "LESS_THAN", d, 0.085)
        bar = _math(nt, "MULTIPLY", _math(nt, "LESS_THAN",
                                          _math(nt, "ABSOLUTE", _math(nt, "SUBTRACT",
                                                                      sep.outputs["Z"], 0.66)),
                                          0.022),
                    _math(nt, "LESS_THAN", d, 0.215))
        bar = _math(nt, "MULTIPLY", bar, _math(nt, "GREATER_THAN", d, 0.12))
        paint = _math(nt, "MINIMUM", _math(nt, "ADD", _math(nt, "ADD", ring, dotm), bar), 1.0)
        wnoise = nt.nodes.new("ShaderNodeTexNoise")
        wnoise.inputs["Scale"].default_value = 14.0
        wnoise.inputs["Detail"].default_value = 8.0
        nt.links.new(coord.outputs["Object"], wnoise.inputs["Vector"])
        wear = _math(nt, "GREATER_THAN", wnoise.outputs["Fac"], 0.36)
        paint = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", paint, wear), rattr.outputs["Fac"])
        paint = _math(nt, "MULTIPLY", paint, 0.88)
        col = _mix(nt, col, (0.40, 0.085, 0.06, 1.0), paint)
        # wheel marks: streaks that run up the ramp, thin across it
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1.2, 16.0, 1.2)
        nt.links.new(coord.outputs["Object"], mp.inputs["Vector"])
        snoise = nt.nodes.new("ShaderNodeTexNoise")
        snoise.inputs["Scale"].default_value = 2.2
        snoise.inputs["Detail"].default_value = 3.0
        nt.links.new(mp.outputs["Vector"], snoise.inputs["Vector"])
        sramp = nt.nodes.new("ShaderNodeMapRange")
        sramp.inputs["From Min"].default_value = 0.55
        sramp.inputs["From Max"].default_value = 0.76
        nt.links.new(snoise.outputs["Fac"], sramp.inputs["Value"])
        lateral = nt.nodes.new("ShaderNodeMapRange")
        lateral.inputs["From Min"].default_value = 1.05
        lateral.inputs["From Max"].default_value = 0.35
        nt.links.new(_math(nt, "ABSOLUTE", sep.outputs["Y"]), lateral.inputs["Value"])
        skid = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", sramp.outputs["Result"],
                                           lateral.outputs["Result"]), rattr.outputs["Fac"])
        col = _mix(nt, col, (0.07, 0.055, 0.045, 1.0), _math(nt, "MULTIPLY", skid, 0.38))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(rough_out, bsdf.inputs["Roughness"])
    return mat


def maple_material():
    """Seven plies showing on the rails (from the ``plyfrac`` point
    attribute, 0 at the bottom face and 1 under the grip), glue lines between
    them, and a painted bottom."""
    mat = bpy.data.materials.new("BoardMaple")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "plyfrac"
    f = attr.outputs["Fac"]
    stripe = _math(nt, "LESS_THAN", _math(nt, "FRACT", _math(nt, "MULTIPLY", f, 7.0)), 0.16)
    dyed = _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", f, 0.43),
                 _math(nt, "LESS_THAN", f, 0.57))
    col = _mix(nt, (0.60, 0.43, 0.25, 1.0), (0.10, 0.20, 0.30, 1.0), dyed)
    col = _mix(nt, col, (0.20, 0.12, 0.06, 1.0), stripe)
    col = _mix(nt, col, (0.08, 0.19, 0.32, 1.0), _math(nt, "LESS_THAN", f, 0.02))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.48
    return mat


def ramp_materials():
    """Shared by the check and the render, in slot order."""
    ply = wood("Plywood", (0.29, 0.20, 0.11), (0.57, 0.44, 0.28), 7.0, rough=(0.88, 0.74),
               ride=True)
    framing = wood("FramingPine", (0.24, 0.165, 0.080), (0.54, 0.41, 0.23), 11.0,
                   rough=(0.80, 0.62))
    steel = metal("Steel", (0.46, 0.47, 0.49, 1.0), 0.38, 0.15,
                  [(0.0, 0.03), (0.30, 0.10), (0.42, 0.55), (0.50, 0.90), (0.62, 0.30),
                   (1.0, 0.15)], roughness_var=0.07, noise_scale=5.0, stretch=(0.6, 9.0, 0.6))
    hardware = metal("ZincHardware", (0.30, 0.30, 0.31, 1.0), 0.45, 0.06,
                     [(0.0, 0.03), (0.30, 0.10), (0.42, 0.55), (0.50, 0.90), (0.62, 0.30),
                      (1.0, 0.15)], roughness_var=0.05, noise_scale=90.0)
    maple = maple_material()
    grip = principled("GripTape", (0.030, 0.030, 0.032, 1.0), 0.0, 0.92, roughness_var=0.05,
                      noise_scale=900.0)
    urethane = principled("Urethane", (0.78, 0.71, 0.54, 1.0), 0.0, 0.40, roughness_var=0.06,
                          mottle=0.05, noise_scale=120.0, coat=0.2)
    alloy = metal("TruckAlloy", (0.80, 0.80, 0.81, 1.0), 0.24, 0.40,
                  [(0.0, 0.03), (0.18, 0.05), (0.30, 0.20), (0.40, 0.60), (0.48, 1.0),
                   (0.60, 0.40), (0.80, 0.25), (1.0, 0.18)], roughness_var=0.06, noise_scale=60.0)
    bushing = principled("Bushing", (0.66, 0.16, 0.045, 1.0), 0.0, 0.50, roughness_var=0.06,
                         noise_scale=80.0)
    return ply, framing, steel, hardware, maple, grip, urethane, alloy, bushing


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

def vert_bbox(obj):
    """World AABB read off the vertices (``bound_box`` is a cached copy that
    an in-place vertex edit does not refresh)."""
    mw = obj.matrix_world
    pts = [mw @ v.co for v in obj.data.vertices]
    return (min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts),
            max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))


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
        self.mean = sum(pts, Vector()) / len(pts)
        tg = {}
        for p in polys:
            t = tags[p.index]
            tg[t] = tg.get(t, 0) + 1
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


def kasa(xz):
    """Algebraic circle fit (x, z) -> (cx, cz, r)."""
    p = np.array(xz, dtype=np.float64)
    a = np.column_stack((p[:, 0], p[:, 1], np.ones(len(p))))
    rhs = -(p[:, 0] ** 2 + p[:, 1] ** 2)
    (d, e, f), *_ = np.linalg.lstsq(a, rhs, rcond=None)
    cx, cz = -0.5 * d, -0.5 * e
    return cx, cz, math.sqrt(max(cx * cx + cz * cz - f, 0.0))


def polar(p, cx, cz):
    """(angle, radius) about (cx, cz) in the construction's own convention."""
    return math.atan2(p.x - cx, cz - p.z), math.hypot(p.x - cx, p.z - cz)


def arc_fit(sheets, concave):
    """Fit a circle to one face of a layer of curved sheets: the face toward
    the centre (``concave``) or away from it. Pass 1 fits every vertex of the
    layer (the faces are concentric); pass 2 keeps the chosen face's
    vertices, clear of each sheet's ends and sides (where the chamfers are),
    and refits. Returns (cx, cz, r, max radial deviation, samples)."""
    pts = [p for s in sheets for p in s.pts]
    if len(pts) < 8:
        return 0.0, 0.0, 0.0, 9.0, 0
    cx, cz, _r = kasa([(p.x, p.z) for p in pts])
    keep = []
    for s in sheets:
        pol = [polar(p, cx, cz) for p in s.pts]
        a0 = min(a for a, _ in pol)
        a1 = max(a for a, _ in pol)
        r_mid = 0.5 * (min(r for _, r in pol) + max(r for _, r in pol))
        m = 0.006 / max(_r, 0.1)
        for p, (a, r) in zip(s.pts, pol):
            if not (a0 + m < a < a1 - m):
                continue
            if not (s.lo.y + 0.0005 < p.y < s.hi.y - 0.0005):
                continue
            if (r < r_mid) == concave:
                keep.append(p)
    if len(keep) < 8:
        return cx, cz, _r, 9.0, len(keep)
    cx, cz, r = kasa([(p.x, p.z) for p in keep])
    dev = max(abs(math.hypot(p.x - cx, p.z - cz) - r) for p in keep)
    return cx, cz, r, dev, len(keep)


def ang_range(s, cx, cz):
    a = [polar(p, cx, cz)[0] for p in s.pts]
    return min(a), max(a)


def rib_audit(cls, fit_in):
    """Each template: seated on its sill (the sill's top above the template's
    bottom, read off both shells) and its curved edge a band inside the inner
    layer's underside, per angular bin, across the inner layer's span."""
    res = {"ribs": 0, "seat": [9.0, -9.0], "bite": [9.0, -9.0]}
    ribs, sills, inner = tagged(cls, T_RIB), tagged(cls, T_SILL), tagged(cls, T_INNER)
    res["ribs"] = len(ribs)
    cx, cz, r_under = fit_in[0], fit_in[1], fit_in[2]
    if not ribs or not inner:
        return res
    lo = min(ang_range(s, cx, cz)[0] for s in inner) + 0.02
    hi = max(ang_range(s, cx, cz)[1] for s in inner) - 0.02
    for rib in ribs:
        under = [s for s in sills if s.lo.y - 1e-4 <= rib.mean.y <= s.hi.y + 1e-4]
        if len(under) != 1:
            res["seat"][0] = -9.0
            continue
        seat = under[0].hi.z - rib.lo.z
        res["seat"][0] = min(res["seat"][0], seat)
        res["seat"][1] = max(res["seat"][1], seat)
        bins = {}
        for p in rib.pts:
            a, r = polar(p, cx, cz)
            if lo < a < hi and r < r_under + 0.02:
                k = round(a / 0.01)
                bins[k] = min(bins.get(k, 9.0), r)
        for r in bins.values():
            res["bite"][0] = min(res["bite"][0], r_under - r)
            res["bite"][1] = max(res["bite"][1], r_under - r)
    return res


def wheel_audit(cls):
    wheels, decks = tagged(cls, T_WHEEL), tagged(cls, T_DECK)
    res = {"wheels": len(wheels), "bite": [9.0, -9.0]}
    if len(decks) != 1:
        return res
    top = decks[0].hi.z
    for w in wheels:
        bite = top - w.lo.z
        res["bite"][0] = min(res["bite"][0], bite)
        res["bite"][1] = max(res["bite"][1], bite)
    return res


def coping_audit(cls, fit_top):
    """Station centres of the pipe's outer surface: straight, parallel to
    the ramp's width, and standing a band proud of the transition and of
    the deck."""
    res = {"pipes": 0, "straight": 9.0, "angle": 90.0, "reveal": [9.0, -9.0], "proud": -9.0}
    pipes, decks = tagged(cls, T_COPING), tagged(cls, T_DECK)
    res["pipes"] = len(pipes)
    if len(pipes) != 1 or len(decks) != 1:
        return res
    p = pipes[0]
    c, _w, vecs = pca(p.pts)
    ax = Vector(vecs[:, 2]).normalized()
    rad = [(q - c - ax * (q - c).dot(ax)).length for q in p.pts]
    r_split = 0.5 * (min(rad) + max(rad))
    stations = {}
    for q, r in zip(p.pts, rad):
        if r < r_split or not (p.lo.y + 0.01 < q.y < p.hi.y - 0.01):
            continue
        stations.setdefault(round(q.y, 4), []).append(q)
    centres = []
    for ys, qs in sorted(stations.items()):
        if len(qs) < 8:
            continue
        cc = sum(qs, Vector()) / len(qs)
        rr = sum((q - cc).length for q in qs) / len(qs)
        centres.append((cc, rr))
    if len(centres) < 3:
        return res
    c2, _w2, v2 = pca([cc for cc, _ in centres])
    ax2 = Vector(v2[:, 2]).normalized()
    res["straight"] = max((cc - c2 - ax2 * (cc - c2).dot(ax2)).length for cc, _ in centres)
    res["angle"] = math.degrees(math.acos(min(1.0, abs(ax2.dot(YAX)))))
    cx, cz, r_fit = fit_top[0], fit_top[1], fit_top[2]
    for cc, rr in centres:
        rev = r_fit - (math.hypot(cc.x - cx, cc.z - cz) - rr)
        res["reveal"][0] = min(res["reveal"][0], rev)
        res["reveal"][1] = max(res["reveal"][1], rev)
    res["proud"] = p.hi.z - decks[0].hi.z
    return res


def plate_audit(cls, fit_top):
    """The plate's top at its upper end against the first top sheet's top at
    its lower end (both read off the mesh, radially about the fitted
    centre), and the height of its toe."""
    res = {"plates": 0, "step": 9.0, "toe": 9.0}
    plates, tops = tagged(cls, T_PLATE), tagged(cls, T_TOP)
    res["plates"] = len(plates)
    if len(plates) != 1 or not tops:
        return res
    cx, cz, r_fit = fit_top[0], fit_top[1], fit_top[2]
    pl = plates[0]
    pol = [polar(q, cx, cz) for q in pl.pts]
    a1 = max(a for a, _ in pol)
    end = [r for (a, r), q in zip(pol, pl.pts)
           if a > a1 - 0.004 / r_fit and abs(q.y) < pl.hi.y - 0.0005]
    first = min(tops, key=lambda s: ang_range(s, cx, cz)[0])
    pol2 = [polar(q, cx, cz) for q in first.pts]
    b0 = min(a for a, _ in pol2)
    start = [r for (a, r), q in zip(pol2, first.pts)
             if a < b0 + 0.004 / r_fit and abs(q.y) < first.hi.y - 0.0005]
    if end and start:
        res["step"] = abs(min(end) - min(start))
    res["toe"] = max(q.z for q in pl.pts if q.x < pl.lo.x + 0.002)
    return res


def seam_audit(cls, fit_top):
    """Seams (the gap mid-points between consecutive sheets of a layer, as
    arc length); every top seam this far from every inner seam, and every
    seam over a stringer."""
    res = {"top": [], "inner": [], "stringers": 0, "stagger": -9.0, "on": -9.0}
    cx, cz, r_fit = fit_top[0], fit_top[1], fit_top[2]
    for key, tag in (("top", T_TOP), ("inner", T_INNER)):
        rs = sorted(ang_range(s, cx, cz) for s in tagged(cls, tag))
        res[key] = [0.5 * (rs[k][1] + rs[k + 1][0]) * r_fit for k in range(len(rs) - 1)]
    strs = [tuple(a * r_fit for a in ang_range(s, cx, cz)) for s in tagged(cls, T_STRINGER)]
    res["stringers"] = len(strs)
    if res["top"] and res["inner"]:
        res["stagger"] = min(abs(a - b) for a in res["top"] for b in res["inner"])
    seams = res["top"] + res["inner"]
    if seams and strs:
        res["on"] = min(max(min(sm - s0, s1 - sm) for s0, s1 in strs) for sm in seams)
    return res


def screw_audit(cls, fit_top):
    """Every skin screw's head over a stringer (clearance to the stringer's
    nearer edge, along the arc) and inside one top sheet."""
    res = {"screws": 0, "edge": 9.0, "sheet": 9.0}
    cx, cz, r_fit = fit_top[0], fit_top[1], fit_top[2]
    screws = tagged(cls, T_SCREW)
    res["screws"] = len(screws)
    strs = [tuple(a * r_fit for a in ang_range(s, cx, cz)) for s in tagged(cls, T_STRINGER)]
    sheets = [(tuple(a * r_fit for a in ang_range(s, cx, cz)), s) for s in tagged(cls, T_TOP)]
    if not screws or not strs or not sheets:
        return res
    for sc in screws:
        s0, s1 = (a * r_fit for a in ang_range(sc, cx, cz))
        res["edge"] = min(res["edge"], max(min(s0 - a, b - s1) for a, b in strs))
        best = -9.0
        for (a, b), sh in sheets:
            if sh.lo.y <= sc.lo.y and sc.hi.y <= sh.hi.y:
                best = max(best, min(s0 - a, b - s1))
        res["sheet"] = min(res["sheet"], best)
    return res


def coax_audit(cls):
    """Each wheel's centre on its axle's line, its axis along the axle."""
    res = {"axles": 0, "wheels": 0, "off": 9.0, "angle": 90.0, "per_axle": []}
    axles, wheels = tagged(cls, T_AXLE), tagged(cls, T_WHEEL)
    res["axles"], res["wheels"] = len(axles), len(wheels)
    if len(axles) != 2 or len(wheels) != 4:
        return res
    lines = []
    for a in axles:
        c, _w, v = pca(a.pts)
        lines.append((c, Vector(v[:, 2]).normalized()))
    res["off"], res["angle"] = 0.0, 0.0
    count = [0, 0]
    for w in wheels:
        c, _wv, v = pca(w.pts)
        k = min(range(2), key=lambda i: ((c - lines[i][0])
                                         - lines[i][1] * (c - lines[i][0]).dot(lines[i][1])).length)
        lc, la = lines[k]
        count[k] += 1
        d = c - lc
        res["off"] = max(res["off"], (d - la * d.dot(la)).length)
        wa = max((Vector(v[:, i]).normalized() for i in range(3)), key=lambda e: abs(e.dot(la)))
        res["angle"] = max(res["angle"], math.degrees(math.acos(min(1.0, abs(wa.dot(la))))))
    res["per_axle"] = count
    return res


def _overlap(a, b):
    if (a.lo.x > b.hi.x or b.lo.x > a.hi.x or a.lo.y > b.hi.y or b.lo.y > a.hi.y
            or a.lo.z > b.hi.z or b.lo.z > a.hi.z):
        return False
    return bool(a.tree.overlap(b.tree))


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
        bm.verts.new((1.0, 0.0, 0.5))
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
    img = bpy.data.images.new("RampNrm", size, size, alpha=True, float_buffer=False)
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


FLAG_NAMES = ("float_sill", "short_rib", "small_wheel", "sag_skin", "sink_coping",
              "proud_plate", "stack_seams", "miss_screws", "skew_wheel", "lift_grip")


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_ramp_mesh("RampLow", 1.0, 1, **flags)
    high = build_ramp_mesh("RampHigh", 1.0, 3, **flags)
    mats = ramp_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the steel: the coping's ends, the plate and the tabs
    # are where the high mesh's rounder chamfer differs from the low.
    target = mats[STEEL_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        _co = [0.0] * (len(low.data.vertices) * 3)
        low.data.vertices.foreach_get("co", _co)
        _co[2::3] = [z + LIFT_Z for z in _co[2::3]]
        low.data.vertices.foreach_set("co", _co)
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("ramp mesh did not build", 3),) + none3

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat = len(slots)
    distinct_mats = len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    print(f"measured mat_index_counts={dict(sorted(idx_counts.items()))}")
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = vert_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]
    hyg = hygiene_audit(low.data)
    cls = classify(low.data)
    zrep = []
    zf = zfight_pairs(low.data, cls["groups"], zrep)
    sills, toes, plates = tagged(cls, T_SILL), tagged(cls, T_TOE), tagged(cls, T_PLATE)
    sill_z = [s.lo.z for s in sills]
    fit_top = arc_fit(tagged(cls, T_TOP), True)
    fit_in = arc_fit(tagged(cls, T_INNER), False)
    ribs = rib_audit(cls, fit_in)
    whl = wheel_audit(cls)
    decks = tagged(cls, T_DECK)
    deck_top = decks[0].hi.z if len(decks) == 1 else 0.0
    cop = coping_audit(cls, fit_top)
    plt = plate_audit(cls, fit_top)
    sea = seam_audit(cls, fit_top)
    scr = screw_audit(cls, fit_top)
    cox = coax_audit(cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("ramp has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "RampLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "RampLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(low, "RampCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_skate_ramp_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    # every piece-specific budget, pass or fail, so a falsifier run shows
    # that it breaks exactly one
    budgets = {
        "grounded": bb[2] <= ZMIN_EPS and len(sills) == 5 and len(toes) == 1
        and len(plates) == 1 and max(sill_z + [t.lo.z for t in toes + plates]) <= ZMIN_EPS,
        "ribs": ribs["ribs"] == 5 and RIB_SEAT_MIN <= ribs["seat"][0]
        and ribs["seat"][1] <= RIB_SEAT_MAX and RIB_BITE_MIN <= ribs["bite"][0]
        and ribs["bite"][1] <= RIB_BITE_MAX,
        "wheels": whl["wheels"] == 4 and WHEEL_BITE_MIN <= whl["bite"][0]
        and whl["bite"][1] <= WHEEL_BITE_MAX,
        "arc": abs(fit_top[2] - R) <= RADIUS_TOL and fit_top[3] <= ARC_DEV_MAX
        and abs(fit_top[1] - fit_top[2]) <= TANGENT_TOL
        and abs(deck_top - DECK_TOP) <= HEIGHT_TOL,
        "coping": cop["pipes"] == 1 and cop["straight"] <= STRAIGHT_TOL
        and cop["angle"] <= PARALLEL_MAX_DEG and REVEAL_MIN <= cop["reveal"][0]
        and cop["reveal"][1] <= REVEAL_MAX and PROUD_MIN <= cop["proud"] <= PROUD_MAX,
        "plate": plt["plates"] == 1 and plt["step"] <= STEP_MAX and plt["toe"] <= TOE_MAX,
        "seams": len(sea["top"]) == 2 and len(sea["inner"]) == 1 and sea["stringers"] == 9
        and sea["stagger"] >= SEAM_STAGGER_MIN and sea["on"] >= SEAM_ON_STRINGER,
        "screws": scr["screws"] > 0 and scr["edge"] >= SCREW_EDGE_MIN
        and scr["sheet"] >= SCREW_SHEET_MIN,
        "coaxial": cox["per_axle"] == [2, 2] and cox["off"] <= COAX_TOL
        and cox["angle"] <= COAX_ANGLE_MAX_DEG,
        "assembly": ncomp == 1,
    }

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
    zkinds = {}
    for rep in zrep:
        key = tuple(sorted((cls['all'][rep[0]].tag, cls['all'][rep[1]].tag)))
        zkinds.setdefault(key, [0, rep[2]])[0] += 1
    for key, (n, at) in sorted(zkinds.items()):
        print(f"measured zfight_pairs tags={key} n={n} e.g. at {at}")
    print(f"measured shells={len(cls['all'])} sill_zmin={[round(z, 5) for z in sill_z]} "
          f"toe_zmin={[round(t.lo.z, 5) for t in toes]} "
          f"plate_zmin={[round(t.lo.z, 5) for t in plates]}")
    print(f"measured ribs={ribs['ribs']} seat=[{ribs['seat'][0]:.5f},{ribs['seat'][1]:.5f}] "
          f"bite=[{ribs['bite'][0]:.5f},{ribs['bite'][1]:.5f}]")
    print(f"measured wheels={whl['wheels']} bite=[{whl['bite'][0]:.5f},{whl['bite'][1]:.5f}]")
    print(f"measured arc r={fit_top[2]:.5f} dev={fit_top[3]:.5f} centre=({fit_top[0]:.5f},"
          f"{fit_top[1]:.5f}) lowest={fit_top[1] - fit_top[2]:.5f} n={fit_top[4]} "
          f"deck_top={deck_top:.5f} inner_r={fit_in[2]:.5f}")
    print(f"measured coping straight={cop['straight']:.6f} angle={cop['angle']:.4f} "
          f"reveal=[{cop['reveal'][0]:.5f},{cop['reveal'][1]:.5f}] proud={cop['proud']:.5f}")
    print(f"measured plate step={plt['step']:.5f} toe={plt['toe']:.5f}")
    print(f"measured seams top={[round(s, 4) for s in sea['top']]} "
          f"inner={[round(s, 4) for s in sea['inner']]} stringers={sea['stringers']} "
          f"stagger={sea['stagger']:.4f} on_stringer={sea['on']:.4f}")
    print(f"measured screws={scr['screws']} edge={scr['edge']:.4f} sheet={scr['sheet']:.4f}")
    print(f"measured coax axles={cox['axles']} wheels={cox['wheels']} per_axle={cox['per_axle']} "
          f"off={cox['off']:.6f} angle={cox['angle']:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[:6]}")
    print(f"measured budget_fails={[k for k, ok in budgets.items() if not ok]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    labels = ("plywood", "framing", "steel", "hardware", "maple", "grip", "urethane", "alloy",
              "bushing")
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
    if not budgets["grounded"]:
        return (fail(f"supports: {len(sills)} sills (want 5), {len(toes)} toe block, "
                     f"{len(plates)} plate, zmin per sill {[round(z, 5) for z in sill_z]}, toe "
                     f"{[round(t.lo.z, 5) for t in toes]}, plate "
                     f"{[round(t.lo.z, 5) for t in plates]} (each within {ZMIN_EPS} of 0)", 16),) + none3
    if not budgets["ribs"]:
        return (fail(f"templates: {ribs['ribs']} (want 5), seated on their sills "
                     f"[{ribs['seat'][0]:.5f}, {ribs['seat'][1]:.5f}] (band [{RIB_SEAT_MIN}, "
                     f"{RIB_SEAT_MAX}]), curved edge into the skin [{ribs['bite'][0]:.5f}, "
                     f"{ribs['bite'][1]:.5f}] (band [{RIB_BITE_MIN}, {RIB_BITE_MAX}])", 17),) + none3
    if not budgets["wheels"]:
        return (fail(f"wheels on the deck: {whl['wheels']} (want 4), bite "
                     f"[{whl['bite'][0]:.5f}, {whl['bite'][1]:.5f}] (band [{WHEEL_BITE_MIN}, "
                     f"{WHEEL_BITE_MAX}])", 18),) + none3
    if not budgets["arc"]:
        return (fail(f"transition: radius {fit_top[2]:.5f} (want {R} +- {RADIUS_TOL}), deviation "
                     f"{fit_top[3]:.5f} (max {ARC_DEV_MAX}), lowest point "
                     f"{fit_top[1] - fit_top[2]:.5f} (tol {TANGENT_TOL}), deck {deck_top:.5f} "
                     f"(want {DECK_TOP} +- {HEIGHT_TOL})", 19),) + none3
    if not budgets["coping"]:
        return (fail(f"coping: straight {cop['straight']:.5f} (tol {STRAIGHT_TOL}), "
                     f"{cop['angle']:.3f} deg off the ramp's width (max {PARALLEL_MAX_DEG}), "
                     f"reveal [{cop['reveal'][0]:.5f}, {cop['reveal'][1]:.5f}] (band "
                     f"[{REVEAL_MIN}, {REVEAL_MAX}]), above the deck {cop['proud']:.5f} "
                     f"(band [{PROUD_MIN}, {PROUD_MAX}])", 20),) + none3
    if not budgets["plate"]:
        return (fail(f"kicker plate: step to the skin {plt['step']:.5f} (max {STEP_MAX}), toe "
                     f"{plt['toe']:.5f} (max {TOE_MAX})", 21),) + none3
    if not budgets["seams"]:
        return (fail(f"seams: top {[round(s, 4) for s in sea['top']]}, inner "
                     f"{[round(s, 4) for s in sea['inner']]}, stagger {sea['stagger']:.4f} (min "
                     f"{SEAM_STAGGER_MIN}), over a stringer by {sea['on']:.4f} (min "
                     f"{SEAM_ON_STRINGER}), {sea['stringers']} stringers", 22),) + none3
    if not budgets["screws"]:
        return (fail(f"screws: {scr['screws']}, clear of a stringer's edge by {scr['edge']:.4f} "
                     f"(min {SCREW_EDGE_MIN}), inside a sheet by {scr['sheet']:.4f} (min "
                     f"{SCREW_SHEET_MIN})", 23),) + none3
    if not budgets["coaxial"]:
        return (fail(f"trucks: wheels per axle {cox['per_axle']}, a wheel {cox['off']:.5f} m off "
                     f"its axle (tol {COAX_TOL}), axis {cox['angle']:.3f} deg off (max "
                     f"{COAX_ANGLE_MAX_DEG})", 24),) + none3
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
    floor.location.z = -0.0005
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

    # The house rig scaled to a 2.5 m ramp: warm key upper left, cool fill
    # low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-3.2, -3.6, 3.4), 57.0, 2.0, (1.0, 0.92, 0.82), spread=30.0)
    light("Fill", (3.8, -2.6, 0.9), 9.0, 4.0, (0.72, 0.82, 1.0))
    light("Rim", (-1.5, 2.6, 2.6), 110.0, 1.8, (0.62, 0.78, 1.0))
    # the wedge stands clear of the ramp's back corner and pools on the wall
    light("Wedge", (4.1, 2.85, 1.3), 700.0, 2.0, (1.0, 0.68, 0.42),
          target=(centre.x + 4.3, centre.y + WALL_Y, 0.6))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.55, -0.83, 0.0)).normalized()
    cam.location = centre + view * 6.5 + Vector((0.0, 0.0, 1.85))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.16))
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
    # Standard, not AgX: AgX washes the plywood and the painted roundel grey
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
    p.add_argument("--float-sill", action="store_true")
    p.add_argument("--short-rib", action="store_true")
    p.add_argument("--small-wheel", action="store_true")
    p.add_argument("--sag-skin", action="store_true")
    p.add_argument("--sink-coping", action="store_true")
    p.add_argument("--proud-plate", action="store_true")
    p.add_argument("--stack-seams", action="store_true")
    p.add_argument("--miss-screws", action="store_true")
    p.add_argument("--skew-wheel", action="store_true")
    p.add_argument("--lift-grip", action="store_true")
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
    print("skate-ramp OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
