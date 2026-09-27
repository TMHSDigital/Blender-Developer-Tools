"""Game-ready outdoor basketball hoop — a showcase piece, not an example.

Asserts budget conformance of a procedural in-ground basketball goal after
composing shipped pipeline pieces: bmesh construction, UVs, six materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

The pole is one sweep from the anchor plate through an S-shaped gooseneck
into the mast behind the board (a bent bar is one sweep). The mast carries
the board through two clamp collars, standoffs and a back rail frame; two
diagonal support braces run from a collar on the pole to the lower rail.
The rim is a regulation ring — 0.457 m inside diameter, top at 3.05 m,
inner edge 0.151 m off the board face — on a tapered bracket bolted through
a flange plate, with twelve welded net hooks. The net is twelve cord loops
hung on those hooks and 24 laid strands that cross in a tapered diamond
mesh. The board is framed, with a painted border and shooter's square.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-brace`` brace bite,
``--drop-net`` net loops threaded on the rim hooks, ``--tilt-rim`` rim
height / level / size / projection, ``--loose-pad`` one connected
assembly.

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

# --- Anchor plate: the only thing on the ground --------------------------
BASE_W = 0.42
BASE_T = 0.025
ANCHOR_XY = 0.165
ANCHOR_R = 0.011
ANCHOR_TOP = BASE_T + 0.062
WASHER_R = 0.026
NUT_R = 0.0195
GUSSET_T = 0.012
GUSSET_REACH = 0.115
GUSSET_H = 0.165
GUSSET_BITE = 0.004

# --- Pole: one sweep from plate to mast top ------------------------------
POLE_R = 0.057          # 4.5 in OD steel pole
POLE_SIDES = 18
POLE_SEAT = 0.008       # pole foot below the plate's top face
GOOSE_Z = 1.75          # where the gooseneck leaves the vertical
GOOSE_BEND_R = 0.45
GOOSE_ANGLE = math.radians(60.0)
GOOSE_STEPS = 9
MAST_TOP = 3.80

# --- Board, frame and back rails ------------------------------------------
BOARD_FACE_Y = 1.22     # pole axis to board face: 48 in overhang
BOARD_T = 0.030
BOARD_W = 1.83          # regulation 6 ft x 3.5 ft, frame included
BOARD_H = 1.05
BOARD_BOT = 2.90
FRAME_W = 0.035
FRAME_PROUD = 0.010
FRAME_BACK = 0.012
PANEL_INSET = 0.020
EDGE_PAD_T = 0.018
EDGE_PAD_REVEAL = 0.008
RAIL_D = 0.050
RAIL_H = 0.050
RAIL_W = 1.30
RAIL_BITE = 0.003
RAIL_Z = (3.08, 3.72)
STILE_X = 0.24
STANDOFF = 0.10
STANDOFF_S = 0.060
CLAMP_H = 0.090

# --- Paint -----------------------------------------------------------------
LINE_W = 0.050
BORDER_PROUD = 0.0008
SQUARE_PROUD = 0.0012
PAINT_SINK = 0.001
SQUARE_W = 0.59
SQUARE_H = 0.45

# --- Rim (regulation) ------------------------------------------------------
RIM_TOP = 3.05
RIM_ID = 0.457
RIM_GAP = 0.151         # board face to the ring's inside edge
RING_R = 0.008
RING_SEGS = 48
FLANGE_W = 0.16
FLANGE_H = 0.15
FLANGE_T = 0.014
FLANGE_SINK = 0.002
BOLT_R = 0.011
STRUT_R = 0.006
STRUT_ANGLE = math.radians(30.0)
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

# --- Pad and brace collar --------------------------------------------------
PAD_Z = (0.21, 1.36)
PAD_T = 0.038
PAD_GRIP = 0.003
COLLAR_Z = 1.55
COLLAR_H = 0.080
COLLAR_T = 0.016
BRACE_R = 0.0165
BRACE_X = 0.55

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (1.846, 2.054, 3.950)
BASE_TRIS_MIN = 8700
BASE_TRIS_MAX = 10000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 6
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 220
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
STEEL_FACES_MIN = 1000
BOARD_FACES_MIN = 30
PAINT_FACES_MIN = 24
RIM_FACES_MIN = 450
NET_FACES_MIN = 700
PAD_FACES_MIN = 120

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
# Real-world rim: top 3.05 m, 0.457 m inside, inner edge 0.151 m off the
# board face, and level.
RIM_TOP_TOL = 0.010
RIM_ID_TOL = 0.004
RIM_GAP_TOL = 0.005
RIM_TILT_MAX_DEG = 0.5
TILT_RIM_DEG = 3.0
LOOSE_PAD = 0.006
# Hero yaw: the board faces the camera from ~40 degrees off its normal so
# the gooseneck's S reads in profile and the net and square read face-on.
HERO_YAW_DEG = -172.0
WALL_Y = 9.0

STEEL_IDX = 0
BOARD_IDX = 1
PAINT_IDX = 2
RIM_IDX = 3
NET_IDX = 4
PAD_IDX = 5


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
    faces = []
    last = n - 1 if solid else n
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


def add_tube(bm, pts, radius, sides, mat_idx, phase=0.0):
    """Capped round bar swept along a polyline (parallel-transport frames)."""
    pts = [Vector(p) for p in pts]
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    ref = Vector((1.0, 0.0, 0.0)) if abs(tans[0].x) < 0.9 else Vector((0.0, 0.0, 1.0))
    nrm = (ref - tans[0] * ref.dot(tans[0])).normalized()
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


def gooseneck_path():
    """Pole centreline: vertical, bend forward, straight, bend back to a
    vertical mast. The straight run is solved from the mast's offset, so the
    mast always lands behind the board's standoffs."""
    board_back = BOARD_FACE_Y - BOARD_T
    rail_back = board_back - RAIL_D + RAIL_BITE
    mast_y = rail_back - STANDOFF - POLE_R
    a = GOOSE_ANGLE
    rb = GOOSE_BEND_R
    straight = (mast_y - 2.0 * rb * (1.0 - math.cos(a))) / math.sin(a)
    pts = [Vector((0.0, 0.0, BASE_T - POLE_SEAT)), Vector((0.0, 0.0, 0.9))]
    # first bend: centre ahead of the pole at the bend height
    c1 = Vector((0.0, rb, GOOSE_Z))
    for i in range(GOOSE_STEPS + 1):
        t = a * i / GOOSE_STEPS
        pts.append(c1 + Vector((0.0, -rb * math.cos(t), rb * math.sin(t))))
    p_end1 = pts[-1]
    d = Vector((0.0, math.sin(a), math.cos(a)))
    p_start2 = p_end1 + d * straight
    # second bend back to vertical: centre on the other side of the run
    c2 = p_start2 + Vector((0.0, -rb * math.cos(a), rb * math.sin(a)))
    for i in range(GOOSE_STEPS + 1):
        t = a * (1.0 - i / GOOSE_STEPS)
        pts.append(c2 + Vector((0.0, rb * math.cos(t), -rb * math.sin(t))))
    top_start = pts[-1]
    pts.append(Vector((0.0, top_start.y, 0.5 * (top_start.z + MAST_TOP))))
    pts.append(Vector((0.0, top_start.y, MAST_TOP)))
    return pts, mast_y, top_start.z


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

def build_hoop_mesh(name, bevel_offset, bevel_segments, short_brace=False,
                    drop_net=False, tilt_rim=False, loose_pad=False):
    bm = bmesh.new()
    try:
        bevel_verts = []

        # anchor plate, gussets, anchor bolts
        bevel_verts += add_box(bm, (0.0, 0.0, BASE_T / 2.0), (BASE_W, BASE_W, BASE_T), STEEL_IDX)
        for k in range(4):
            ang = 0.5 * math.pi * k
            rad = Vector((math.cos(ang), math.sin(ang), 0.0))
            tan = Vector((-math.sin(ang), math.cos(ang), 0.0))
            r0 = POLE_R - GUSSET_BITE
            z0 = BASE_T - 0.003
            tri = [(r0, z0), (r0 + GUSSET_REACH, z0), (r0 + 0.018, z0 + GUSSET_H),
                   (r0, z0 + GUSSET_H)]
            pts = []
            for s in (-0.5, 0.5):
                for r, z in tri:
                    pts.append(rad * r + tan * (s * GUSSET_T) + Vector((0.0, 0.0, z)))
            bevel_verts += add_hexahedron(bm, pts, STEEL_IDX)
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                c = (sx * ANCHOR_XY, sy * ANCHOR_XY, 0.0)
                add_lathe(bm, [(ANCHOR_R, BASE_T - 0.012), (ANCHOR_R, ANCHOR_TOP - 0.003),
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

        # the pole: one sweep from inside the plate to the mast top
        path, mast_y, mast_z0 = gooseneck_path()
        add_tube(bm, path, POLE_R, POLE_SIDES, STEEL_IDX)
        cap_z = MAST_TOP
        add_lathe(bm, [(POLE_R + 0.006, cap_z - 0.014), (POLE_R + 0.006, cap_z + 0.010),
                       (POLE_R * 0.75, cap_z + 0.030), (0.018, cap_z + 0.040)],
                  POLE_SIDES, STEEL_IDX, center=(0.0, mast_y, 0.0), solid=True)

        # padding wrapped on the pole, gripping it; grooves split it into panels
        ri = POLE_R - PAD_GRIP
        if loose_pad:
            ri = POLE_R + LOOSE_PAD
        ro = POLE_R + PAD_T
        z0, z1 = PAD_Z
        prof = [(ri, z0), (ro - 0.012, z0), (ro, z0 + 0.012)]
        for g in (1.0 / 3.0, 2.0 / 3.0):
            gz = z0 + (z1 - z0) * g
            prof += [(ro, gz - 0.012), (ro - 0.007, gz - 0.004), (ro - 0.007, gz + 0.004),
                     (ro, gz + 0.012)]
        prof += [(ro, z1 - 0.012), (ro - 0.012, z1), (ri, z1)]
        add_lathe(bm, prof, POLE_SIDES, PAD_IDX)

        # brace collar and the two support braces to the lower rail
        cr_i = POLE_R - 0.003
        cr_o = POLE_R + COLLAR_T
        cz0 = COLLAR_Z - COLLAR_H / 2.0
        cz1 = COLLAR_Z + COLLAR_H / 2.0
        add_lathe(bm, [(cr_i, cz0), (cr_o - 0.004, cz0), (cr_o, cz0 + 0.004),
                       (cr_o, cz1 - 0.004), (cr_o - 0.004, cz1), (cr_i, cz1)],
                  POLE_SIDES, STEEL_IDX)
        board_back = BOARD_FACE_Y - BOARD_T
        rail_y = board_back - RAIL_D / 2.0 + RAIL_BITE
        for sx in (-1.0, 1.0):
            # the brace foot sits in the middle of the collar wall
            p0 = Vector((sx * 0.5 * (cr_i + cr_o), 0.015, COLLAR_Z))
            p1 = Vector((sx * BRACE_X, rail_y, RAIL_Z[0]))
            if short_brace:
                p1 = p1 - (p1 - p0).normalized() * SHORT_BRACE
            add_tube(bm, [p0, p1], BRACE_R, 10, STEEL_IDX)

        # mast clamps, standoffs, back rails and stiles
        for rz in RAIL_Z:
            add_lathe(bm, [(cr_i, rz - CLAMP_H / 2.0), (cr_o - 0.004, rz - CLAMP_H / 2.0),
                           (cr_o, rz - CLAMP_H / 2.0 + 0.004), (cr_o, rz + CLAMP_H / 2.0 - 0.004),
                           (cr_o - 0.004, rz + CLAMP_H / 2.0), (cr_i, rz + CLAMP_H / 2.0)],
                      POLE_SIDES, STEEL_IDX, center=(0.0, mast_y, 0.0))
            y0 = mast_y
            y1 = board_back - RAIL_D + RAIL_BITE + 0.006
            bevel_verts += add_box(bm, (0.0, 0.5 * (y0 + y1), rz), (STANDOFF_S, y1 - y0,
                                                                     STANDOFF_S), STEEL_IDX)
            bevel_verts += add_box(bm, (0.0, rail_y, rz), (RAIL_W, RAIL_D, RAIL_H), STEEL_IDX)
        for sx in (-1.0, 1.0):
            h = RAIL_Z[1] - RAIL_Z[0]
            bevel_verts += add_box(bm, (sx * STILE_X, board_back - 0.0215, 0.5 * sum(RAIL_Z)),
                                   (0.040, 0.047, h), STEEL_IDX)

        # board panel inside its frame
        bz = BOARD_BOT + BOARD_H / 2.0
        bevel_verts += add_box(bm, (0.0, BOARD_FACE_Y - BOARD_T / 2.0, bz),
                               (BOARD_W - 2.0 * PANEL_INSET, BOARD_T, BOARD_H - 2.0 * PANEL_INSET),
                               BOARD_IDX)
        bevel_verts += add_rect_frame(
            bm, 0.0, bz, board_back - FRAME_BACK, BOARD_FACE_Y + FRAME_PROUD,
            BOARD_W, BOARD_H, BOARD_W - 2.0 * FRAME_W, BOARD_H - 2.0 * FRAME_W, STEEL_IDX)

        # edge pad wrapped round the frame's bottom member, a reveal past the
        # frame's ends so its caps never land on the frame's end faces
        fy_back = board_back - FRAME_BACK
        fy_front = BOARD_FACE_Y + FRAME_PROUD
        py0 = fy_back - EDGE_PAD_T
        py1 = fy_front + EDGE_PAD_T
        pz0 = BOARD_BOT - EDGE_PAD_T
        pz1 = BOARD_BOT + FRAME_W + 0.006
        ch = 0.010
        pad_prof = [(py0 + ch, pz0), (py1 - ch, pz0), (py1, pz0 + ch), (py1, pz1 - ch),
                    (py1 - ch, pz1), (py0 + ch, pz1), (py0, pz1 - ch), (py0, pz0 + ch)]
        half = BOARD_W / 2.0 + EDGE_PAD_REVEAL
        bevel_verts += add_prism_x(bm, pad_prof, -half, half, PAD_IDX)

        # painted border (tucked 3 mm under the frame) and shooter's square
        bw = BOARD_W - 2.0 * FRAME_W + 0.006
        bh = BOARD_H - 2.0 * FRAME_W + 0.006
        add_rect_frame(bm, 0.0, bz, BOARD_FACE_Y - PAINT_SINK, BOARD_FACE_Y + BORDER_PROUD,
                       bw, bh, bw - 0.006 - 2.0 * LINE_W, bh - 0.006 - 2.0 * LINE_W, PAINT_IDX)
        sq_z = RIM_TOP - LINE_W + SQUARE_H / 2.0
        add_rect_frame(bm, 0.0, sq_z, BOARD_FACE_Y - PAINT_SINK, BOARD_FACE_Y + SQUARE_PROUD,
                       SQUARE_W, SQUARE_H, SQUARE_W - 2.0 * LINE_W, SQUARE_H - 2.0 * LINE_W,
                       PAINT_IDX)

        # --- rim assembly (every vertex from here on tilts with --tilt-rim)
        rim_start = len(bm.verts)
        ring_z = RIM_TOP - RING_R
        ring_rc = RIM_ID / 2.0 + RING_R
        ring_cy = BOARD_FACE_Y + RIM_GAP + RIM_ID / 2.0
        fz = ring_z - 0.02
        fy0 = BOARD_FACE_Y - FLANGE_SINK
        fy1 = BOARD_FACE_Y + FLANGE_T
        bevel_verts += add_box(bm, (0.0, 0.5 * (fy0 + fy1), fz), (FLANGE_W, fy1 - fy0, FLANGE_H),
                               RIM_IDX)
        xrot = Euler((-0.5 * math.pi, 0.0, 0.0)).to_matrix()
        for sx in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                add_lathe(bm, [(BOLT_R, fy1 - 0.003), (BOLT_R, fy1 + 0.005),
                               (BOLT_R * 0.8, fy1 + 0.0075)], 6, STEEL_IDX,
                          center=(sx * 0.055, 0.0, fz + sz * 0.052), rot=xrot,
                          phase=math.pi / 6.0, solid=True)
        # tapered bracket: flange face to the ring's near side
        by0 = fy1 - 0.004
        by1 = ring_cy - ring_rc + 0.004
        top = ring_z + 0.004
        bracket = [
            (-0.055, by0, top - 0.075), (0.055, by0, top - 0.075), (0.055, by0, top), (-0.055, by0, top),
            (-0.026, by1, top - 0.018), (0.026, by1, top - 0.018), (0.026, by1, top), (-0.026, by1, top),
        ]
        bevel_verts += add_hexahedron(bm, bracket, RIM_IDX)
        # two struts from the bracket to the ring, either side of the board line
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
            # the loop's cord bears on the lower inside of the hook eye
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
        bm.verts.ensure_lookup_table()
        if drop_net:
            for v in bm.verts[net_start:]:
                v.co.z -= DROP_NET
        if tilt_rim:
            pivot = Vector((0.0, BOARD_FACE_Y, ring_z))
            rot = Matrix.Rotation(math.radians(-TILT_RIM_DEG), 3, "X")
            for v in bm.verts[rim_start:]:
                v.co = pivot + rot @ (v.co - pivot)

        if bevel_offset > 0.0:
            # One pass per material, with material= set: left at its default
            # the chamfer faces take slot 0 and the board's rim would render
            # (and classify) as steel. A set of BMEdges iterates in memory
            # order, which varies run to run; sort by index.
            for mat_idx in (STEEL_IDX, BOARD_IDX, RIM_IDX, PAD_IDX):
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
        # Round stock (pole, pad, ring, cord) is smooth-shaded; plates and
        # boxes keep their chamfers crisp through sharp edges.
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

def principled(name, color, metallic, roughness, roughness_var=0.0, mottle=0.0,
               noise_scale=14.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
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


def hoop_materials():
    """(steel, board, paint, rim, net, pad): shared by the check and the render.

    Powder-coated steel is dark and rough, not chrome; the rim is enamelled
    orange; the board is a weathered off-white with red paint that is a
    touch worn; the cord is off-white nylon; the pad is navy vinyl.
    """
    steel = principled("HoopSteel", (0.040, 0.046, 0.052, 1.0), 0.55, 0.52,
                       roughness_var=0.14, mottle=0.25)
    board = principled("HoopBoard", (0.62, 0.62, 0.60, 1.0), 0.0, 0.38,
                       roughness_var=0.10, mottle=0.07, noise_scale=6.0)
    paint = principled("HoopPaint", (0.52, 0.045, 0.035, 1.0), 0.0, 0.50,
                       roughness_var=0.12, mottle=0.22, noise_scale=30.0)
    rim = principled("HoopRim", (0.82, 0.21, 0.025, 1.0), 0.35, 0.42,
                     roughness_var=0.12, mottle=0.18, noise_scale=40.0)
    net = principled("HoopNet", (0.80, 0.79, 0.74, 1.0), 0.0, 0.82)
    pad = principled("HoopPad", (0.030, 0.065, 0.19, 1.0), 0.0, 0.62,
                     roughness_var=0.10, mottle=0.10)
    return steel, board, paint, rim, net, pad


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
    steel = [s for s in parts if s.mat == STEEL_IDX]
    out["pole"] = [s for s in steel if s.size.z > 3.0]
    out["braces"] = [s for s in steel if 1.0 < s.size.z < 3.0 and s.size.x < 0.8]
    out["collars"] = [s for s in steel if 0.1 < s.size.x < 0.2 and 0.1 < s.size.y < 0.2
                      and 0.05 < s.size.z < 0.1 and s.centre.z < 2.5]
    rails = [s for s in steel if s.size.x > 1.0 and s.size.z < 0.08]
    out["low_rail"] = sorted(rails, key=lambda s: s.centre.z)[:1]
    rim = [s for s in parts if s.mat == RIM_IDX]
    out["ring"] = [s for s in rim if s.size.x > 0.4]
    out["hooks"] = [s for s in rim if max(s.size) < 0.035]
    net = [s for s in parts if s.mat == NET_IDX]
    out["loops"] = [s for s in net if max(s.size) < 0.05]
    out["strands"] = [s for s in net if max(s.size) >= 0.05]
    boards = [s for s in parts if s.mat == BOARD_IDX]
    out["board"] = boards
    return out


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
    """Rim top height, inside diameter, inner-edge gap to the board face, tilt."""
    if len(cls["ring"]) != 1 or not cls["board"]:
        return None
    ring = cls["ring"][0]
    c, axis, _r, radii = circle_fit(ring.pts)
    tilt = math.degrees(math.acos(min(1.0, abs(float(axis[2])))))
    inner_r = float(radii.min())
    top = ring.hi.z
    face_y = max(s.hi.y for s in cls["board"])
    gap = (float(c[1]) - inner_r) - face_y
    return {"top": top, "id": 2.0 * inner_r, "gap": gap, "tilt": tilt}


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


def check(skip_decimate, lift_z=False, stray_vert=False, short_brace=False,
          drop_net=False, tilt_rim=False, loose_pad=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(short_brace=short_brace, drop_net=drop_net, tilt_rim=tilt_rim,
                 loose_pad=loose_pad)
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
          f"worst_thread={thread:.5f}")
    if rim:
        print(f"measured rim_top={rim['top']:.4f} rim_id={rim['id']:.4f} "
              f"rim_gap={rim['gap']:.4f} rim_tilt_deg={rim['tilt']:.3f}")
    print(f"measured components={ncomp} sizes={comp_sizes}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none6
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none6
    floors = ((STEEL_IDX, STEEL_FACES_MIN, "steel"), (BOARD_IDX, BOARD_FACES_MIN, "board"),
              (PAINT_IDX, PAINT_FACES_MIN, "paint"), (RIM_IDX, RIM_FACES_MIN, "rim"),
              (NET_IDX, NET_FACES_MIN, "net"), (PAD_IDX, PAD_FACES_MIN, "pad"))
    for idx, floor, label in floors:
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

    # Key and fill in the lantern's directions, scaled for a 4 m prop; the
    # key's spread keeps it on the hoop instead of flooding the near floor.
    # The warm wedge washes the back wall on the right, the rim traces the
    # pole and gooseneck against it.
    light("Key", (-8.5, -12.0, 9.0), 1800.0, 4.0, (1.0, 0.95, 0.90), spread=28.0)
    light("Fill", (12.0, -8.5, 2.0), 160.0, 16.0, (0.72, 0.82, 1.0))
    light("Rim", (-3.5, 5.0, 4.0), 900.0, 4.0, (0.62, 0.78, 1.0))
    light("Wedge", (8.0, 3.0, 5.0), 1500.0, 6.0, (1.0, 0.68, 0.38),
          target=(4.5, WALL_Y - 3.5, 0.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    # near eye height, a little under the board, so the rim and net read
    # against the board rather than against the floor
    view = Vector((-0.55, -0.77, 0.0)).normalized()
    cam.location = centre + view * 12.2 + Vector((0.0, 0.0, -0.25))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, 0.18))
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
        return 21
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
    args = p.parse_args(argv)

    code, low, steel, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_brace=args.short_brace,
        drop_net=args.drop_net,
        tilt_rim=args.tilt_rim,
        loose_pad=args.loose_pad,
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
