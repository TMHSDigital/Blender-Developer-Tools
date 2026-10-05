"""Game-ready wingback armchair in a reading corner — a showcase piece, not an example.

Asserts budget conformance of a procedural reading-corner vignette after
composing shipped pipeline pieces: bmesh construction, UVs, nine materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

A Queen Anne / Chesterfield-style wingback armchair in oxblood leather stands
on a fringed wool rug. Its tall back is deep-button tufted: thirteen buttons
on a diamond lattice, each seated in a funnelled dimple, with the leather
puffed into pillows between them and folded into sharp pleats along every
line that joins two buttons; above the top row and beside the side columns
the pleats run straight out to the edge. Two wings sweep forward from the
back and down into rolled arms. Each arm is one lofted scroll profile — a
flat inner face, an English roll over the top that tucks under on the
outside, a flared outer panel — with a crowned front, a piped welt round the
front seam and a row of brass nailheads following the scroll. A loose seat
cushion with a crowned top and piped welts on both seams rests on the deck,
whose crowned front rail carries a third row of nailheads.
Cabriole front legs end in pad feet; square rear legs splay back into brass
ferrules. Beside the chair a round walnut side table on a turned baluster
pedestal and three snake-foot legs carries a brass reading lamp (domed base,
knopped stem, socket, bulb, harp, finial, spider and a linen shade) and two
cloth-bound books.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh hygiene,
``--lift-z`` grounded zmin, ``--float-foot`` every foot on the rug,
``--short-legs`` the legs tenoned into the body, ``--sink-buttons`` every
button seated in its dimple, ``--odd-wing`` the chair's mirror symmetry,
``--drift-buttons`` the diamond lattice, ``--narrow-tripod`` the table's
mass centre inside its feet, ``--lift-cushion`` the cushion resting on the
deck, ``--bunch-nails`` the nailheads evenly spaced and seated.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts are
not byte-identical across Blender versions — the LOD gate is a ratio band,
not an exact count.

    blender --background --python wingback_armchair.py --
    blender --background --python wingback_armchair.py -- --skip-decimate
    blender --background --python wingback_armchair.py -- --output armchair.png
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

# Lathe segment multiplier: the high mesh for the bake turns finer.
SEG_MUL = [1.0]

# --- Rug (the whole vignette stands on it; the chair's front is -Y) --------
RUG_T = 0.010
Z0 = RUG_T                   # chair and table z below are above the rug top
RUG_C = (0.24, -0.03)
RUG_HX = 0.93
RUG_HY = 0.70
RUG_RC = 0.02
RUG_PROFILE = [(0.006, 0.0), (0.0015, 0.0012), (0.0, 0.0040), (0.0, 0.0065),
               (0.0015, 0.0088), (0.006, RUG_T)]
FRINGE_PITCH = 0.032
FRINGE_R = 0.0032
FRINGE_LEN = 0.058

# --- Seat base: the upholstered box between the arms ------------------------
BASE_HX = 0.305
BASE_Y = (-0.405, 0.345)
BASE_RC = 0.035
BASE_PROFILE = [(0.010, 0.245), (0.002, 0.249), (0.0, 0.258), (0.0, 0.332),
                (0.002, 0.340), (0.008, 0.345)]

# --- Back (reclined slab; front face deep-button tufted) ---------------------
BACK_REC_DEG = 8.0
BACK_O = (0.0, 0.262, 0.235)
BACK_T = 0.120
BACK_HU = 0.395
BACK_VT = (0.878, 0.830)     # top edge v at the centre line and at the sides
BACK_CROWN = 0.030
BACK_CORNER = 0.040
LAT_DU = 0.011               # grid pitch; a tenth of the button pitch
LAT_DV = 0.012
LAT_P = 27                   # lattice-aligned u samples: -27..27 * LAT_DU
GRID_V0 = 0.18
GRID_Q = 52
TOP_STEPS = 6
U_OUTER = (0.330, 0.360, 0.395)
BTN_DX = 0.110               # diamond lattice: columns and rows
BTN_DY = 0.120
BTN_V0 = 0.300
BTN_ROWS = 5
BTN_COLS = 2                 # i = -2..2, buttons where i + j is even
PUFF = 0.018
PLEAT_P = 0.6
DIMPLE_D = 0.016
DIMPLE_S = 0.028
TUFT_HALF = 0.300
BTN_PROFILE = [(0.0082, -0.0025), (0.0108, -0.0008), (0.0112, 0.0018), (0.0098, 0.0045),
               (0.0066, 0.0066), (0.0022, 0.0074)]

# --- Arms (right arm at +X; the left is its mirror) --------------------------
ARM_Y = (-0.415, 0.345)
ARM_ROLL_C = (0.362, 0.592)
ARM_ROLL_R = 0.066
ARM_STAR = (0.350, 0.540)
ARM_FRONT = [(0.990, -0.003), (0.965, -0.008), (0.920, -0.012), (0.820, -0.016),
             (0.620, -0.019), (0.350, -0.021)]
PIPE_R = 0.0048
PIPE_OUT = 0.0020
NAIL_S = 0.93
NAIL_PITCH = 0.030
NAIL_MARGIN = 0.030
NAIL_SINK = 0.0010
RAIL_Z = 0.262               # nail row along the front rail
RAIL_HALF = 0.270
NAIL_PROFILE = [(0.0044, 0.0), (0.0056, 0.0011), (0.0050, 0.0026), (0.0028, 0.0038),
                (0.0008, 0.0041)]

# --- Wings --------------------------------------------------------------------
WING_XI = (0.318, 0.335)     # inner face x at the back, at the front
WING_PROFILE = [(0.30, -0.010), (0.60, -0.009), (0.80, -0.006), (0.92, -0.002),
                (0.970, 0.004), (0.992, 0.013), (1.0, 0.026), (1.0, 0.046),
                (0.992, 0.059), (0.970, 0.067), (0.92, 0.072), (0.80, 0.076),
                (0.60, 0.079), (0.30, 0.080)]
WING_CTRL = [(-0.115, 0.632), (-0.150, 0.665), (-0.172, 0.715), (-0.183, 0.775),
             (-0.182, 0.840), (-0.170, 0.900), (-0.145, 0.950), (-0.105, 0.992),
             (-0.055, 1.022), (0.005, 1.042), (0.075, 1.054), (0.150, 1.060),
             (0.230, 1.060)]
WING_PIPE_N = 0.036

# --- Cushion ------------------------------------------------------------------
CUSH_HX = 0.292
CUSH_FRONT = -0.448
CUSH_RC = 0.045
CUSH_BULGE = 0.010
CUSH_PROFILE = [(0.012, 0.343), (0.004, 0.345), (0.0, 0.3505), (0.0, 0.380), (0.0, 0.410),
                (0.0, 0.4335), (0.001, 0.438), (0.006, 0.4435), (0.014, 0.4474),
                (0.030, 0.4492), (0.060, 0.4510), (0.100, 0.4521), (0.150, 0.4528),
                (0.200, 0.4531)]
WELT_Z = (0.3478, 0.4358)

# --- Legs -----------------------------------------------------------------------
FRONT_LEG_XY = (0.345, -0.365)
REAR_LEG_XY = (0.340, 0.355)
FOOT_SINK = 0.0020
LEG_TOP = (0.265, 0.245)     # front, rear: top of the leg inside the body
SHORT_LEG = 2                # --short-legs: the right rear leg
SHORT_DROP = 0.040          # --short-legs drops that leg's top out of the body

# --- Side table, lamp and books ------------------------------------------------
TABLE_C = (0.900, -0.020)
TABLE_TOP_Z = 0.575
TABLE_LEG_YAW = -30.0
TFOOT_R = 0.203
NARROW = 0.30                # --narrow-tripod scales the legs' reach
FLOAT_TFOOT = 0.003
LAMP_OFF = (0.045, 0.075)
BOOK_SIZES = ((0.215, 0.150, 0.030), (0.196, 0.134, 0.026))
BOOK_AT = ((-0.075, -0.065, 18.0), (-0.068, -0.070, 4.0))

# --- Budgets ------------------------------------------------------------------------
BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from the mesh's vertices.
OUTER_SIZE = (2.0304, 1.4000, 1.1600)
BASE_TRIS_MIN = 43700
BASE_TRIS_MAX = 44900
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 9
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 820
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
FACE_FLOORS = (("leather", 14500), ("wood", 3350), ("brass", 4450), ("shade", 620),
               ("rug", 615), ("fringe", 1390), ("cloth", 114), ("paper", 11), ("bulb", 195))

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Feet: every chair foot (2 pads, 2 ferrules) and table foot (3 pads) sunk
# into the rug's pile by a banded depth, read against the rug top.
CHAIR_FEET = 4
TABLE_FEET = 3
SINK_BAND = (0.0008, 0.0040)
# Legs tenoned into the body: each leg's top above the body's underside.
LEG_BITE = (0.012, 0.045)
# Buttons: 13, each seated a banded depth into the back below the surface
# point under its centre, its dome proud of it, and that point a dimple.
BTN_COUNT = 13
BTN_SEAT = (0.0012, 0.0045)
BTN_PROUD_MIN = 0.004
DIMPLE_MIN = 0.008
DIMPLE_RING = 0.040
SINK_BUTTONS = 0.006
# Mirror symmetry of the upholstered body, and its real-world size.
MIRROR_EPS = 0.0005
ODD_WING = 0.006
SEAT_HEIGHT = (0.43, 0.48)
BACK_HEIGHT = (1.07, 1.13)
CHAIR_WIDTH = (0.83, 0.88)
# Diamond lattice: every pair of diagonal neighbours at one spacing.
LATTICE_PAIRS = 16
LATTICE_NEAR = 0.20
LATTICE_SPREAD_MAX = 0.004
LATTICE_BAND = (0.150, 0.175)
DRIFT_BUTTONS = 0.018
# Table: mass centre of table, lamp and books inside the feet's triangle.
TRIPOD_MARGIN_MIN = 0.045
DENSITY = (600.0, 700.0, 4500.0, 300.0, 0.0, 0.0, 700.0, 700.0, 600.0)
# Cushion resting on the deck: its underside pressed into the deck top.
CUSHION_REST = (0.0008, 0.0040)
LIFT_CUSHION = 0.005
# Nailheads: per arm, consecutive nails at one pitch, each sunk into the
# arm's front by a banded depth with its dome proud of it.
NAIL_SPREAD_MAX = 0.0015
NAIL_SEAT = (0.0004, 0.0025)
NAIL_PROUD_MIN = 0.0020
BUNCH_NAIL = 6
BUNCH_SHIFT = 0.45
HERO_YAW_DEG = 0.0
WALL_Y = 3.2

LEATHER_IDX = 0
WOOD_IDX = 1
BRASS_IDX = 2
SHADE_IDX = 3
RUG_IDX = 4
FRINGE_IDX = 5
CLOTH_IDX = 6
PAPER_IDX = 7
BULB_IDX = 8

# Part tags (face attribute "part" = kind * 1000 + index). Measurements read
# positions off the mesh; the tag only says which shell is which part.
(RUG, TASSEL, BASE, ARM, ARMPIPE, NAIL, WING, WINGPIPE, BACK, BUTTON, CUSHION, WELT,
 LEG, PAD, FERRULE, TTOP, PED, TLEG, TPAD, LBASE, LSTEM, SOCKET, BULB, HARP, FINIAL,
 SHADE, SPIDER, COVER, PAGES) = range(1, 30)
BODY_KINDS = (BASE, ARM, ARMPIPE, WING, WINGPIPE, BACK, CUSHION, WELT)
TABLE_KINDS = (TTOP, PED, TLEG, TPAD, LBASE, LSTEM, SOCKET, BULB, HARP, FINIAL, SHADE,
               SPIDER, COVER, PAGES)
FLAG_NAMES = ("float_foot", "short_legs", "sink_buttons", "odd_wing", "drift_buttons",
              "narrow_tripod", "lift_cushion", "bunch_nails")


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

def W(x, y, z):
    """Chair- and table-local height (above the rug top) to world."""
    return Vector((x, y, z + Z0))


def _mark(faces, mat_idx):
    for f in faces:
        f.material_index = mat_idx


def tag(bm, verts, kind, idx=0):
    layer = bm.faces.layers.int.get("part")
    for f in {f for v in verts for f in v.link_faces}:
        f[layer] = kind * 1000 + idx
    return verts


def set_tone(bm, verts, tone):
    layer = bm.faces.layers.float.get("tone")
    for f in {f for v in verts for f in v.link_faces}:
        f[layer] = tone


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False, seg_mats=None):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: the profile
    is an open polyline closed by n-gon caps at its two ends; otherwise it
    is a closed polygon revolved into a ring shell."""
    segs = max(3, int(round(segs * SEG_MUL[0])))
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
            f = bm.faces.new((r0[j], r1[j], r1[k], r0[k]))
            f.material_index = seg_mats[j] if seg_mats else mat_idx
    if solid:
        f0 = bm.faces.new([rings[i][0] for i in reversed(range(segs))])
        f1 = bm.faces.new([rings[i][n - 1] for i in range(segs)])
        f0.material_index = mat_idx
        f1.material_index = mat_idx
    return [v for ring in rings for v in ring]


def add_loft(bm, rings_co, mat_idx, closed=False, caps=True):
    """Rings of points (each a closed loop, equal counts) joined in order."""
    rings = [[bm.verts.new(p) for p in ring] for ring in rings_co]
    faces = []
    n = len(rings)
    m = len(rings[0])
    for i in range(n if closed else n - 1):
        r0, r1 = rings[i], rings[(i + 1) % n]
        for k in range(m):
            k1 = (k + 1) % m
            faces.append(bm.faces.new((r0[k], r0[k1], r1[k1], r1[k])))
    if not closed and caps:
        faces.append(bm.faces.new(tuple(reversed(rings[0]))))
        faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def sweep_rings(pts, section, normals=None, side=None, closed=False, scales=None):
    """Section [(a, b), ...] placed along a polyline: ``a`` along the frame
    normal, ``b`` along the binormal. The normal comes from ``normals`` (a
    surface), a fixed ``side`` axis (a planar path), or parallel transport.
    ``scales`` scales the section per point."""
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
        s = scales[i] if scales else 1.0
        rings.append([p + nv * (sa * s) + bv * (sb * s) for sa, sb in section])
    return rings


def add_sweep(bm, pts, section, mat_idx, normals=None, side=None, closed=False, scales=None):
    return add_loft(bm, sweep_rings(pts, section, normals, side, closed, scales), mat_idx,
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


def rrect_loop(hx, hy, r, nc=8, nsx=6, nsy=6):
    """Rounded rectangle, counter-clockwise, with ``nsx`` / ``nsy`` spans on
    the straight sides."""
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
    x = (x - z * x.dot(z))
    if x.length < 1e-6:
        x = Vector((1.0, 0.0, 0.0)) if abs(z.x) < 0.9 else Vector((0.0, 1.0, 0.0))
        x = x - z * x.dot(z)
    x.normalize()
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


def bvh_of(verts):
    faces = list({f for v in verts for f in v.link_faces})
    vs = list({v for f in faces for v in f.verts})
    idx = {v: i for i, v in enumerate(vs)}
    return BVHTree.FromPolygons([v.co.copy() for v in vs], [[idx[v] for v in f.verts] for f in faces])


def cast(tree, origin, direction, dist=1.0):
    loc, nrm, _i, _d = tree.ray_cast(Vector(origin), Vector(direction).normalized(), dist)
    if loc is None:
        return None, None
    if nrm.dot(direction) > 0.0:
        nrm = -nrm
    return loc, nrm


def outline_normals(pts, centre):
    """Outward 2D normals of a closed polyline, pointing away from ``centre``."""
    n = len(pts)
    out = []
    for i in range(n):
        ax, ay = pts[i - 1]
        bx, by = pts[(i + 1) % n]
        tx, ty = bx - ax, by - ay
        ln = math.hypot(tx, ty) or 1.0
        nx, ny = ty / ln, -tx / ln
        if nx * (pts[i][0] - centre[0]) + ny * (pts[i][1] - centre[1]) < 0.0:
            nx, ny = -nx, -ny
        out.append((nx, ny))
    return out


def scaled(pts, centre, s):
    cx, cy = centre
    return [(cx + (x - cx) * s, cy + (y - cy) * s) for x, y in pts]


def chord_walk(path, pitch, margin):
    """Stations along an open polyline, ``pitch`` apart as straight chords,
    starting ``margin`` along it and stopping ``margin`` short of its end."""
    seg = [math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)]
    total = sum(seg)

    def at(s):
        for i, ln in enumerate(seg):
            if s <= ln or i == len(seg) - 1:
                t = min(1.0, max(0.0, s / ln)) if ln > 0 else 0.0
                return (path[i][0] + (path[i + 1][0] - path[i][0]) * t,
                        path[i][1] + (path[i + 1][1] - path[i][1]) * t)
            s -= ln
        return path[-1]

    out = [at(margin)]
    s = margin
    step = pitch / 200.0
    while True:
        prev = out[-1]
        s2 = s
        while s2 < total - margin and math.dist(at(s2), prev) < pitch:
            s2 += step
        if s2 >= total - margin:
            break
        # refine the chord to the pitch by bisection between s2 - step and s2
        lo, hi = s2 - step, s2
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            if math.dist(at(mid), prev) < pitch:
                lo = mid
            else:
                hi = mid
        s = hi
        out.append(at(s))
    return out, at


# --------------------------------------------------------------------------
# Rug and fringe
# --------------------------------------------------------------------------

def add_rug(bm):
    def xf(x, y, z):
        return Vector((RUG_C[0] + x, RUG_C[1] + y, z))

    rings = rrect_rings(RUG_HX, RUG_HY, RUG_RC, 0.004, RUG_PROFILE, xf, nc=3, nsx=24, nsy=18)
    return tag(bm, add_loft(bm, rings, RUG_IDX), RUG)


def add_fringe(bm):
    """Tassels along both short ends: each a four-sided strand from inside
    the rug's edge out onto the floor, a vertex of its section down so it
    lies on the floor along a line; lengths and lateral drift vary per
    tassel so no two neighbours share a plane."""
    n = int((2.0 * RUG_HY - 0.06) / FRINGE_PITCH) + 1
    y0 = RUG_C[1] - 0.5 * FRINGE_PITCH * (n - 1)
    idx = 0
    for side in (-1.0, 1.0):
        xe = RUG_C[0] + side * RUG_HX
        for k in range(n):
            y = y0 + FRINGE_PITCH * k
            ph = k * 2.39996 + (0.7 if side > 0 else 0.0)
            # each strand rolled its own way about its path; its lowest
            # vertex, r cos(roll) below the path, lies on the floor
            roll = 0.40 * math.sin(1.7 * ph + 0.3)
            sec = [(FRINGE_R * math.cos(math.pi + roll + 2.0 * math.pi * j / 4),
                    FRINGE_R * math.sin(math.pi + roll + 2.0 * math.pi * j / 4)) for j in range(4)]
            rc = FRINGE_R * math.cos(roll)
            drift = 0.0075 * math.sin(ph)
            ln = FRINGE_LEN + 0.011 * math.sin(k * 1.713 + 0.5 * side)
            zs = 0.0050 + 0.0007 * math.sin(ph + 1.0)
            z1 = 0.0046 + 0.0005 * math.sin(1.3 * ph + 2.0)
            z2 = rc + 0.0005 + 0.0004 * math.sin(0.7 * ph + 0.5)
            pts = [Vector((xe - side * 0.014, y, zs)),
                   Vector((xe + side * 0.003, y + 0.05 * drift, z1)),
                   Vector((xe + side * 0.016, y + 0.25 * drift, z2)),
                   Vector((xe + side * (0.016 + 0.45 * ln), y + 0.62 * drift, rc * 0.95)),
                   Vector((xe + side * (0.016 + ln), y + drift, rc * 1.30))]
            ups = [Z_AX] * len(pts)
            scales = [1.0, 1.0, 1.0, 0.95, 1.30]
            tag(bm, add_sweep(bm, pts, sec, FRINGE_IDX, normals=ups, scales=scales), TASSEL, idx)
            idx += 1
    return idx


# --------------------------------------------------------------------------
# Chair: base, back, buttons, arms, wings, cushion, legs
# --------------------------------------------------------------------------

def add_base(bm):
    hy = 0.5 * (BASE_Y[1] - BASE_Y[0])
    cy = 0.5 * (BASE_Y[1] + BASE_Y[0])

    def xf(x, y, z):
        # the front rail is crowned forward a little
        yy = y + cy
        fr = smooth01((BASE_Y[0] + 0.10 - yy) / 0.10)
        bulge = 0.006 * (1.0 - (x / BASE_HX) ** 2) * fr
        zf = smooth01((z - 0.248) / 0.02) * smooth01((0.342 - z) / 0.02)
        return W(x, yy - bulge * zf, z)

    rings = rrect_rings(BASE_HX, hy, BASE_RC, 0.006, BASE_PROFILE, xf, nc=6, nsx=12, nsy=14)
    return tag(bm, add_loft(bm, rings, LEATHER_IDX), BASE)


def back_axes():
    r = math.radians(BACK_REC_DEG)
    vdir = Vector((0.0, math.sin(r), math.cos(r)))
    ndir = Vector((0.0, -math.cos(r), math.sin(r)))      # toward the sitter
    return vdir, ndir


def back_origin():
    return W(*BACK_O)


def v_top(u):
    # an arched crest whose corners roll down into the wings
    return (BACK_VT[1] + (BACK_VT[0] - BACK_VT[1]) * (1.0 - (u / BACK_HU) ** 2)
            - BACK_CORNER * smooth01((abs(u) - 0.330) / 0.065))


def back_crown(u, v):
    return (BACK_CROWN * (1.0 - (u / 0.42) ** 2) * smooth01(v / 0.25)
            * (1.0 - 0.5 * smooth01((v - (v_top(u) - 0.10)) / 0.10)))


def tuft_pattern(u, v):
    """Pillows between buttons, folded into pleats along every line that
    joins two diagonal neighbours; straight pleats out to the edges beyond
    the lattice. Every term is even in u."""
    a = u / BTN_DX + (v - BTN_V0) / BTN_DY
    b = u / BTN_DX - (v - BTN_V0) / BTN_DY
    dia = (abs(math.sin(0.5 * math.pi * a)) * abs(math.sin(0.5 * math.pi * b))) ** PLEAT_P
    vf = abs(math.sin(0.5 * math.pi * u / BTN_DX)) ** PLEAT_P
    hf = abs(math.sin(0.5 * math.pi * (v - BTN_V0) / BTN_DY)) ** PLEAT_P
    v_last = BTN_V0 + (BTN_ROWS - 1) * BTN_DY
    t_v = max(smooth01((v - v_last) / (0.5 * BTN_DY)), smooth01((BTN_V0 - v) / (0.5 * BTN_DY)))
    p = dia + (vf - dia) * t_v
    t_s = smooth01((abs(u) - BTN_COLS * BTN_DX) / (0.5 * BTN_DX))
    return p + (hf - p) * t_s


def back_h(u, v, dimples):
    dim = sum(math.exp(-((u - ub) ** 2 + (v - vb) ** 2) / DIMPLE_S ** 2) for ub, vb in dimples)
    tuft = PUFF * tuft_pattern(u, v) - DIMPLE_D * dim
    fade = (smooth01((TUFT_HALF - abs(u)) / 0.025) * smooth01((v_top(u) - v) / 0.035)
            * smooth01((v - 0.20) / 0.04))
    return back_crown(u, v) + tuft * fade


def back_point(u, v, depth=0.0, out_u=0.0, out_v=0.0):
    vdir, ndir = back_axes()
    return back_origin() + X_AX * (u + out_u) + vdir * (v + out_v) + ndir * depth


def crown_normal(u, v):
    e = 1e-4
    du = (back_point(u + e, v, back_crown(u + e, v)) - back_point(u - e, v, back_crown(u - e, v)))
    dv = (back_point(u, v + e, back_crown(u, v + e)) - back_point(u, v - e, back_crown(u, v - e)))
    n = du.cross(dv).normalized()
    return n if n.dot(back_axes()[1]) > 0.0 else -n


def button_sites(drift=False):
    sites = []
    for j in range(BTN_ROWS):
        for i in range(-BTN_COLS, BTN_COLS + 1):
            if (i + j) % 2:
                continue
            u = i * BTN_DX
            if drift and j == 2 and abs(i) == BTN_COLS:
                u += math.copysign(DRIFT_BUTTONS, i)
            sites.append((u, BTN_V0 + j * BTN_DY))
    return sites


def add_back(bm, dimples):
    us = ([-u for u in reversed(U_OUTER)] + [p * LAT_DU for p in range(-LAT_P, LAT_P + 1)]
          + list(U_OUTER))
    vq = [0.0, 0.06, 0.12] + [GRID_V0 + q * LAT_DV for q in range(GRID_Q + 1)]
    nu = len(us)
    grid_uv = []
    for iv in range(len(vq) + TOP_STEPS):
        row = []
        for u in us:
            if iv < len(vq):
                v = vq[iv]
            else:
                k = iv - len(vq) + 1
                v = vq[-1] + (v_top(u) - vq[-1]) * k / TOP_STEPS
            row.append((u, v))
        grid_uv.append(row)
    nv = len(grid_uv)
    verts = [[bm.verts.new(back_point(u, v, back_h(u, v, dimples))) for u, v in row]
             for row in grid_uv]
    faces = []
    lat_u0 = len(U_OUTER)
    lat_v0 = 3
    for iv in range(nv - 1):
        for iu in range(nu - 1):
            v00, v10 = verts[iv][iu], verts[iv][iu + 1]
            v01, v11 = verts[iv + 1][iu], verts[iv + 1][iu + 1]
            p = iu - lat_u0 - LAT_P
            q = iv - lat_v0
            lattice = (lat_u0 <= iu and iu + 1 <= lat_u0 + 2 * LAT_P
                       and 0 <= q and iv + 1 <= lat_v0 + GRID_Q)
            if lattice:
                # split each cell along the diagonal of the nearest pleat
                ac = (p + q + 1.0) / 10.0 + (GRID_V0 - BTN_V0) / BTN_DY
                bc = (p - q) / 10.0 - (GRID_V0 - BTN_V0) / BTN_DY
                da = abs(ac - 2.0 * round(ac / 2.0))
                db = abs(bc - 2.0 * round(bc / 2.0))
                along_a = da <= db
            else:
                along_a = (v10.co - v01.co).length <= (v00.co - v11.co).length
            if along_a:
                faces.append(bm.faces.new((v00, v10, v01)))
                faces.append(bm.faces.new((v10, v11, v01)))
            else:
                faces.append(bm.faces.new((v00, v10, v11)))
                faces.append(bm.faces.new((v00, v11, v01)))
    # border loop: bottom, right, top (reversed), left
    loop = ([(0, iu) for iu in range(nu)] + [(iv, nu - 1) for iv in range(1, nv)]
            + [(nv - 1, iu) for iu in range(nu - 2, -1, -1)] + [(iv, 0) for iv in range(nv - 2, 0, -1)])
    uv2 = [grid_uv[iv][iu] for iv, iu in loop]
    nrm2 = outline_normals(uv2, (0.0, 0.45))
    front = [verts[iv][iu] for iv, iu in loop]
    rings = [front]
    for depth_f, out in ((-0.30, 0.012), (-0.72, 0.008), (-1.0, -0.004)):
        rings.append([bm.verts.new(back_point(u, v, depth_f * BACK_T, out * nu_, out * nv_))
                      for (u, v), (nu_, nv_) in zip(uv2, nrm2)])
    m = len(front)
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for k in range(m):
            k1 = (k + 1) % m
            faces.append(bm.faces.new((r0[k], r0[k1], r1[k1], r1[k])))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, LEATHER_IDX)
    allv = [v for row in verts for v in row] + [v for r in rings[1:] for v in r]
    return tag(bm, allv, BACK)


def add_buttons(bm, back_tree, sites, sink=0.0):
    for k, (u, v) in enumerate(sites):
        axis = crown_normal(u, v)
        guess = back_point(u, v, back_crown(u, v))
        hit, _n = cast(back_tree, guess + axis * 0.10, -axis, 0.3)
        if hit is None:
            hit = guess
        c = hit - axis * sink
        tag(bm, add_lathe(bm, BTN_PROFILE, 12, LEATHER_IDX, center=c,
                          rot=frame_from(axis, X_AX), phase=0.37 * k, solid=True), BUTTON, k)


def arm_outline():
    """Right arm's section in (x, z): flat inner face, an English roll over
    the top that tucks under on the outside, and a flared outer panel."""
    pts = [(0.300, 0.235), (0.346, 0.235), (0.392, 0.235), (0.395, 0.300), (0.398, 0.380),
           (0.401, 0.460), (0.401, 0.492), (0.396, 0.510), (0.386, 0.522)]
    cx, cz = ARM_ROLL_C
    n = 28
    for k in range(n):
        a = math.radians(-72.0 + 268.0 * k / (n - 1))
        pts.append((cx + ARM_ROLL_R * math.cos(a), cz + ARM_ROLL_R * math.sin(a)))
    pts += [(0.300, 0.545), (0.300, 0.470), (0.300, 0.390), (0.300, 0.310)]
    return pts


def add_arm(bm, side, bunch=False):
    """One arm: its section lofted along y with crowned ends, a piped welt
    round the front seam and a row of nailheads following the scroll."""
    sg = 1.0 if side == 0 else -1.0
    outline = arm_outline()
    y0, y1 = ARM_Y

    def to3(pts2, y):
        return [W(sg * x, y, z) for x, z in pts2]

    rings = []
    for s, dy in reversed(ARM_FRONT):
        rings.append(to3(scaled(outline, ARM_STAR, s), y1 - dy))   # back end, crowned
    nst = 13
    for k in range(nst + 1):
        rings.append(to3(outline, y1 + (y0 - y1) * k / nst))
    for s, dy in ARM_FRONT:
        rings.append(to3(scaled(outline, ARM_STAR, s), y0 + dy))
    arm_verts = tag(bm, add_loft(bm, rings, LEATHER_IDX), ARM, side)
    # piped welt on the front seam: a cord round the section, its centre
    # outside the seam so it bites the arm by R - OUT
    nrm = outline_normals(outline, ARM_STAR)
    k2 = PIPE_OUT / math.sqrt(2.0)
    pts = [W(sg * (x + nx * k2), y0 - k2, z + nz * k2) for (x, z), (nx, nz) in zip(outline, nrm)]
    ups = [Vector((sg * nx, 0.0, nz)) for nx, nz in nrm]
    tag(bm, add_sweep(bm, pts, circle_section(PIPE_R, 6), LEATHER_IDX, normals=ups, closed=True),
        ARMPIPE, side)
    # nailheads along the scroll, inside the welt: every station a chord of
    # one pitch from the last, seated on the arm's own front surface
    tree = bvh_of(arm_verts)
    ring = scaled(outline, ARM_STAR, NAIL_S)
    path = ring[2:] + ring[:1]            # outer bottom corner round to inner bottom
    stations, at = chord_walk(path, NAIL_PITCH, NAIL_MARGIN)
    if bunch:
        # slide one nail part of a pitch toward the next
        a, b = stations[BUNCH_NAIL], stations[BUNCH_NAIL + 1]
        stations[BUNCH_NAIL] = (a[0] + (b[0] - a[0]) * BUNCH_SHIFT, a[1] + (b[1] - a[1]) * BUNCH_SHIFT)
    for k, (x, z) in enumerate(stations):
        hit, n = cast(tree, W(sg * x, y0 - 0.10, z), Y_AX, 0.3)
        if hit is None:
            continue
        sink = NAIL_SINK + 0.0003 * (k % 2)
        prof = [(r, zz - sink) for r, zz in NAIL_PROFILE]
        tag(bm, add_lathe(bm, prof, 8, BRASS_IDX, center=hit, rot=frame_from(n, Z_AX),
                          phase=0.53 * k + 0.23 * side, solid=True), NAIL, side * 100 + k)
    return len(stations)


def add_rail_nails(bm, base_verts):
    """A row of nailheads across the front rail under the cushion, at the
    arms' pitch, each seated on the rail's own crowned face."""
    tree = bvh_of(base_verts)
    n = int(2.0 * RAIL_HALF / NAIL_PITCH + 1e-9) + 1
    stations = [(NAIL_PITCH * (k - 0.5 * (n - 1)), RAIL_Z) for k in range(n)]
    for k, (x, z) in enumerate(stations):
        hit, n = cast(tree, W(x, BASE_Y[0] - 0.20, z), Y_AX, 0.4)
        if hit is None:
            continue
        sink = NAIL_SINK + 0.0003 * (k % 2)
        prof = [(r, zz - sink) for r, zz in NAIL_PROFILE]
        tag(bm, add_lathe(bm, prof, 8, BRASS_IDX, center=hit, rot=frame_from(n, Z_AX),
                          phase=0.53 * k + 0.61, solid=True), NAIL, 200 + k)
    return len(stations)


def back_front_y(z_local):
    return BACK_O[1] + (z_local - BACK_O[2]) * math.tan(math.radians(BACK_REC_DEG))


def wing_outline():
    def yb(z):
        return back_front_y(z) + 0.045

    bottom = [(yb(0.600), 0.600), (0.200, 0.612), (0.080, 0.618), (-0.040, 0.625)]
    front = [(p.x, p.y) for p in catmull([Vector((y, z, 0.0)) for y, z in WING_CTRL], per=2)]
    back = [(yb(1.050), 1.050), (yb(0.950), 0.950), (yb(0.850), 0.850), (yb(0.750), 0.750),
            (yb(0.660), 0.660)]
    return bottom + front + back, len(bottom), len(bottom) + len(front)


def wing_xi(y):
    t = min(1.0, max(0.0, (0.36 - y) / 0.54))
    return WING_XI[0] + (WING_XI[1] - WING_XI[0]) * t


def add_wing(bm, side, shift=0.0):
    sg = 1.0 if side == 0 else -1.0
    outline, i0, i1 = wing_outline()
    centre = (0.07, 0.84)

    def to3(y, z, n):
        return W(sg * (wing_xi(y) + n + shift), y, z)

    rings = [[to3(y, z, n) for y, z in scaled(outline, centre, s)] for s, n in WING_PROFILE]
    tag(bm, add_loft(bm, rings, LEATHER_IDX), WING, side)
    # piped front edge, from inside the arm's roll round to inside the back
    nrm = outline_normals(outline, centre)
    seg = range(i0, i1 + 1)
    pts = [to3(outline[i][0] + nrm[i][0] * PIPE_OUT, outline[i][1] + nrm[i][1] * PIPE_OUT,
               WING_PIPE_N) for i in seg]
    ups = [Vector((0.0, nrm[i][0], nrm[i][1])) for i in seg]
    tag(bm, add_sweep(bm, pts, circle_section(PIPE_R, 6), LEATHER_IDX, normals=ups), WINGPIPE, side)


def cushion_back_y():
    """The cushion's back edge, 5 mm clear of the back's front face at every
    height and width the cushion spans (read off the back's surface)."""
    ymin = 9.0
    for iu in range(-6, 7):
        u = CUSH_HX * iu / 6.0
        for iz in range(12):
            z = CUSH_PROFILE[0][1] + (CUSH_PROFILE[-1][1] - CUSH_PROFILE[0][1]) * iz / 11.0
            # v such that the crown-only surface passes height z (one Newton pass)
            vdir, _ndir = back_axes()
            v = (z - BACK_O[2]) / vdir.z
            for _ in range(3):
                p = back_point(u, v, back_crown(u, v))
                v -= (p.z - Z0 - z) / vdir.z
            ymin = min(ymin, back_point(u, v, back_crown(u, v)).y)
    return ymin - 0.005


def add_cushion(bm, lift=0.0):
    yb = cushion_back_y()
    hy = 0.5 * (yb - CUSH_FRONT)
    cy = 0.5 * (yb + CUSH_FRONT)
    z0, z1 = CUSH_PROFILE[2][1], CUSH_PROFILE[5][1]

    def bulge(z):
        return 1.0 + CUSH_BULGE * math.sin(math.pi * min(1.0, max(0.0, (z - z0) / (z1 - z0))))

    def xf(x, y, z):
        b = bulge(z)
        return W(x * b if abs(x) > 1e-9 else x, cy + y * (1.0 + (b - 1.0) * 0.6), z + lift)

    rings = rrect_rings(CUSH_HX, hy, CUSH_RC, 0.010, CUSH_PROFILE, xf, nc=6, nsx=10, nsy=12)
    tag(bm, add_loft(bm, rings, LEATHER_IDX), CUSHION)
    for k, zw in enumerate(WELT_Z):
        loop = rrect_loop(CUSH_HX + PIPE_OUT, hy + PIPE_OUT, CUSH_RC + PIPE_OUT, 6, 10, 12)
        pts = [W(x, cy + y, zw + lift) for x, y in loop]
        tag(bm, add_sweep(bm, pts, circle_section(PIPE_R * 0.9, 6), LEATHER_IDX, side=Z_AX,
                          closed=True), WELT, k)
    return yb


def add_front_leg(bm, side, top_z):
    """Cabriole leg: knee bulging forward, a slim ankle and a pad foot."""
    sg = 1.0 if side == 0 else -1.0
    lx, ly = FRONT_LEG_XY
    ctrl = [(0.0, 0.0, top_z), (0.0, 0.0, 0.235), (0.004, -0.018, 0.195), (0.004, -0.013, 0.150),
            (0.0, 0.004, 0.095), (-0.002, 0.012, 0.046), (0.0, 0.004, 0.024), (0.0, -0.008, 0.013)]
    radii = [0.027, 0.027, 0.030, 0.025, 0.018, 0.0125, 0.0140, 0.0150]
    pts = catmull([W(sg * (lx + dx), ly + dy, z) for dx, dy, z in ctrl], per=3)
    rs = catmull([Vector((r, 0.0, 0.0)) for r in radii], per=3)
    sec = superellipse_section(1.0, 1.0, 16, 2.6)
    tag(bm, add_sweep(bm, pts, sec, WOOD_IDX, scales=[r.x for r in rs]), LEG, side)
    pad = [(0.0215, -FOOT_SINK), (0.0255, -FOOT_SINK + 0.003), (0.0268, 0.006), (0.0245, 0.0115),
           (0.0180, 0.0165), (0.0120, 0.0190)]
    tag(bm, add_lathe(bm, pad, 24, WOOD_IDX, center=W(sg * lx, ly - 0.008, 0.0), solid=True),
        PAD, side)


def add_rear_leg(bm, side, top_z):
    """Square tapered leg splayed back, in a brass ferrule with a level sole."""
    sg = 1.0 if side == 0 else -1.0
    lx, ly = REAR_LEG_XY
    ctrl = [(0.0, 0.0, top_z), (0.002, 0.015, 0.180), (0.006, 0.040, 0.080), (0.009, 0.060, 0.010)]
    radii = [0.0165, 0.0155, 0.0130, 0.0112]
    pts = catmull([W(sg * (lx + dx), ly + dy, z) for dx, dy, z in ctrl], per=4)
    rs = catmull([Vector((r, 0.0, 0.0)) for r in radii], per=4)
    sec = superellipse_section(1.0, 1.0, 12, 4.0)
    tag(bm, add_sweep(bm, pts, sec, WOOD_IDX, side=X_AX, scales=[r.x for r in rs]), LEG, 2 + side)
    axis = (pts[-1] - pts[-5]).normalized()
    foot = pts[-1]
    cup = [(0.0120, -0.0040), (0.0150, -0.0030), (0.0158, 0.0010), (0.0152, 0.0300),
           (0.0138, 0.0340), (0.0118, 0.0345)]
    base = foot - axis * 0.0045
    verts = add_lathe(bm, cup, 20, BRASS_IDX, center=base, rot=frame_from(-axis, Y_AX), solid=True)
    # the lathe's axis follows the raked leg; its sole is flattened level
    sole = Z0 - FOOT_SINK
    lo = min(v.co.z for v in verts)
    for v in verts:
        v.co.z += sole + 0.0015 - lo
        if v.co.z < sole + 0.0095:
            v.co.z = sole
    tag(bm, verts, FERRULE, side)


# --------------------------------------------------------------------------
# Side table, lamp, books
# --------------------------------------------------------------------------

def add_table(bm, narrow=False, float_foot=False):
    tx, ty = TABLE_C
    top = [(0.205, 0.551), (0.222, 0.552), (0.230, 0.556), (0.235, 0.562), (0.236, 0.567),
           (0.233, 0.572), (0.226, 0.575), (0.205, 0.575)]
    tag(bm, add_lathe(bm, top, 48, WOOD_IDX, center=W(tx, ty, 0.0), solid=True), TTOP)
    ped = [(0.012, 0.085), (0.020, 0.095), (0.030, 0.113), (0.044, 0.133), (0.046, 0.150),
           (0.042, 0.165), (0.030, 0.180), (0.024, 0.215), (0.030, 0.260), (0.040, 0.310),
           (0.038, 0.350), (0.027, 0.390), (0.019, 0.430), (0.021, 0.460), (0.028, 0.480),
           (0.032, 0.500), (0.028, 0.515), (0.040, 0.525), (0.052, 0.535), (0.052, 0.548),
           (0.048, 0.560)]
    tag(bm, add_lathe(bm, ped, 32, WOOD_IDX, center=W(tx, ty, 0.0), solid=True), PED)
    reach = NARROW if narrow else 1.0
    path = [(0.020, 0.170), (0.055, 0.160), (0.095, 0.125), (0.135, 0.075), (0.170, 0.035),
            (0.190, 0.016), (0.203, 0.011)]
    sec = superellipse_section(0.0125, 0.0095, 12, 2.4)
    for k in range(3):
        ang = math.radians(TABLE_LEG_YAW + 120.0 * k)
        er = Vector((math.cos(ang), math.sin(ang), 0.0))
        et = Vector((-math.sin(ang), math.cos(ang), 0.0))
        lift = FLOAT_TFOOT if (float_foot and k == 0) else 0.0
        ctrl = []
        for i, (rho, z) in enumerate(path):
            rho2 = 0.020 + (rho - 0.020) * reach
            dz = lift * smooth01((i - 3) / 3.0)
            ctrl.append(W(tx, ty, 0.0) + er * rho2 + Z_AX * (z + dz))
        pts = catmull(ctrl, per=3)
        nstat = len(pts)
        scales = [1.25 - 0.45 * i / (nstat - 1) for i in range(nstat)]
        tag(bm, add_sweep(bm, pts, sec, WOOD_IDX, side=et, scales=scales), TLEG, k)
        rho_f = 0.020 + (TFOOT_R - 0.020) * reach
        pad = [(0.0125, -FOOT_SINK + lift), (0.0158, -FOOT_SINK + 0.0028 + lift),
               (0.0170, 0.0060 + lift), (0.0150, 0.0140 + lift), (0.0105, 0.0200 + lift),
               (0.0060, 0.0225 + lift)]
        tag(bm, add_lathe(bm, pad, 20, WOOD_IDX, center=W(tx, ty, 0.0) + er * rho_f, solid=True),
            TPAD, k)


def add_lamp(bm):
    lx, ly = TABLE_C[0] + LAMP_OFF[0], TABLE_C[1] + LAMP_OFF[1]
    c = W(lx, ly, TABLE_TOP_Z)
    base = [(0.066, -0.0008), (0.070, 0.002), (0.0705, 0.006), (0.064, 0.011), (0.050, 0.018),
            (0.032, 0.024), (0.020, 0.030), (0.016, 0.036), (0.012, 0.040)]
    tag(bm, add_lathe(bm, base, 40, BRASS_IDX, center=c, solid=True), LBASE)
    stem = [(0.0060, 0.030), (0.0075, 0.034), (0.0075, 0.165), (0.0105, 0.172), (0.0140, 0.182),
            (0.0150, 0.190), (0.0140, 0.198), (0.0105, 0.208), (0.0075, 0.215), (0.0075, 0.380),
            (0.0085, 0.386)]
    tag(bm, add_lathe(bm, stem, 24, BRASS_IDX, center=c, solid=True), LSTEM)
    sock = [(0.009, 0.378), (0.016, 0.384), (0.018, 0.392), (0.018, 0.420), (0.016, 0.428),
            (0.013, 0.432)]
    tag(bm, add_lathe(bm, sock, 24, BRASS_IDX, center=c, phase=0.13, solid=True), SOCKET)
    bulb = [(0.010, 0.426), (0.013, 0.434), (0.022, 0.450), (0.029, 0.470), (0.030, 0.485),
            (0.027, 0.498), (0.018, 0.508), (0.008, 0.512)]
    tag(bm, add_lathe(bm, bulb, 24, BULB_IDX, center=c, solid=True), BULB)
    harp = [(-0.012, 0.392), (-0.030, 0.405), (-0.052, 0.440), (-0.058, 0.490), (-0.045, 0.530),
            (-0.020, 0.552), (0.0, 0.557), (0.020, 0.552), (0.045, 0.530), (0.058, 0.490),
            (0.052, 0.440), (0.030, 0.405), (0.012, 0.392)]
    hp = catmull([c + Vector((x, 0.0, z)) for x, z in harp], per=3)
    tag(bm, add_sweep(bm, hp, circle_section(0.0022, 6), BRASS_IDX, side=Y_AX), HARP)
    fin = [(0.004, 0.553), (0.009, 0.556), (0.010, 0.562), (0.008, 0.570), (0.004, 0.575)]
    tag(bm, add_lathe(bm, fin, 16, BRASS_IDX, center=c, phase=0.21, solid=True), FINIAL)
    shade = [(0.1500, 0.3960), (0.1545, 0.3950), (0.1560, 0.3985), (0.1400, 0.4400),
             (0.1265, 0.4760), (0.1120, 0.5150), (0.0990, 0.5530), (0.1000, 0.5575),
             (0.0960, 0.5590), (0.0948, 0.5540), (0.1078, 0.5155), (0.1222, 0.4755),
             (0.1357, 0.4395), (0.1485, 0.4010)]
    tag(bm, add_lathe(bm, shade, 48, SHADE_IDX, center=c), SHADE)
    for k in range(3):
        a = math.radians(90.0 + 120.0 * k)
        d = Vector((math.cos(a), math.sin(a), 0.0))
        pts = [c + Vector((0.0, 0.0, 0.5585)) + d * (0.004 + 0.093 * t / 5) - Z_AX * (0.003 * t / 5)
               for t in range(6)]
        tag(bm, add_sweep(bm, pts, circle_section(0.0016, 5), BRASS_IDX, side=Z_AX), SPIDER, k)
    return c


def add_books(bm):
    """Two cloth-bound books: a U-shaped case (boards and a rounded spine)
    round a page block that bites both boards."""
    tx, ty = TABLE_C
    z = TABLE_TOP_Z - 0.0012
    for k, ((bw, bd, bh), (ox, oy, yaw)) in enumerate(zip(BOOK_SIZES, BOOK_AT)):
        rot = Matrix.Rotation(math.radians(yaw), 3, "Z")
        o = W(tx + ox, ty + oy, z)
        tb = 0.0022
        rs = 0.5 * bh

        def P(w, d, h):
            return o + rot @ Vector((w - 0.5 * bw, d - 0.5 * bd, h))

        prof = [(bd, 0.0)]
        for i in range(9):
            a = -0.5 * math.pi - math.pi * i / 8.0
            prof.append((rs + rs * math.cos(a) * 0.55, rs + rs * math.sin(a)))
        prof.append((bd, bh))
        prof.append((bd, bh - tb))
        ri = rs - tb
        for i in range(9):
            a = 0.5 * math.pi + math.pi * i / 8.0
            prof.append((rs + ri * math.cos(a) * 0.45, rs + ri * math.sin(a)))
        prof.append((bd, tb))
        rings = [[P(w, d, h) for d, h in prof] for w in (0.0, bw)]
        cv = add_loft(bm, rings, CLOTH_IDX)
        tag(bm, cv, COVER, k)
        set_tone(bm, cv, float(k))
        pb = []
        for w in (0.003, bw - 0.003):
            pb.append([P(w, d, h) for d, h in ((bd - 0.0035, tb - 0.0004), (bd - 0.0035, bh - tb + 0.0004),
                                               (0.0120, bh - tb + 0.0004), (0.0120, tb - 0.0004))])
        tag(bm, add_loft(bm, pb, PAPER_IDX), PAGES, k)
        z += bh - 0.0009


# --------------------------------------------------------------------------
# The vignette
# --------------------------------------------------------------------------

def build_mesh(name, seg_mul=1.0, float_foot=False, short_legs=False, sink_buttons=False,
               odd_wing=False, drift_buttons=False, narrow_tripod=False, lift_cushion=False,
               bunch_nails=False):
    SEG_MUL[0] = seg_mul
    bm = bmesh.new()
    try:
        bm.faces.layers.int.new("part")
        bm.faces.layers.float.new("tone")
        add_rug(bm)
        add_fringe(bm)
        add_rail_nails(bm, add_base(bm))
        sites = button_sites(drift_buttons)
        back_verts = add_back(bm, sites)
        add_buttons(bm, bvh_of(back_verts), sites, SINK_BUTTONS if sink_buttons else 0.0)
        for side in (0, 1):
            add_arm(bm, side, bunch=bunch_nails)
            add_wing(bm, side, ODD_WING if (odd_wing and side == 0) else 0.0)
        add_cushion(bm, LIFT_CUSHION if lift_cushion else 0.0)
        for side in (0, 1):
            add_front_leg(bm, side, LEG_TOP[0])
            short = short_legs and 2 + side == SHORT_LEG
            add_rear_leg(bm, side, LEG_TOP[1] - (SHORT_DROP if short else 0.0))
        add_table(bm, narrow=narrow_tripod, float_foot=float_foot)
        add_lamp(bm)
        add_books(bm)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        for v in bm.verts:
            # the fringe's floor-lying vertices land a rounding error under 0
            if v.co.z < 0.0:
                v.co.z = 0.0
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # Upholstery, turned wood and brass are smooth-shaded; pleats, seams,
        # board edges and material boundaries stay crisp through sharp edges.
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
        SEG_MUL[0] = 1.0
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
        bsdf.inputs["Coat Roughness"].default_value = 0.12
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


def metal(name, color, roughness, env, stops, roughness_var=0.05, noise_scale=40.0):
    """Polished metal with a studio carried in the material (copied from
    showcase/espresso-machine): the world-space reflection vector looks up a
    bright band of walls and softboxes round the horizon, added as emission,
    so brass reads as metal on the dark stage and on the asset sheet alike."""
    mat = principled(name, color, 1.0, roughness, roughness_var=roughness_var,
                     noise_scale=noise_scale)
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
    cr.interpolation = "EASE"
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


def leather_material():
    """Oxblood leather: a two-octave mottle, rubbed lighter and browner
    where it faces up and wears, darkened in the pleats and seams by
    ambient occlusion, a fine pebbled grain and soft crinkles in the bump,
    and a waxed coat."""
    mat = principled("OxbloodLeather", (0.150, 0.030, 0.024, 1.0), 0.0, 0.40)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    mott = nt.nodes.new("ShaderNodeTexNoise")
    mott.inputs["Scale"].default_value = 11.0
    mott.inputs["Detail"].default_value = 7.0
    mott.inputs["Roughness"].default_value = 0.6
    nt.links.new(coord.outputs["Object"], mott.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.28
    ramp.color_ramp.elements[0].color = (0.066, 0.021, 0.018, 1.0)
    ramp.color_ramp.elements[1].position = 0.74
    ramp.color_ramp.elements[1].color = (0.150, 0.052, 0.042, 1.0)
    nt.links.new(mott.outputs["Fac"], ramp.inputs["Fac"])
    # wear: upward-facing, rubbed patches go lighter and browner
    wear_n = nt.nodes.new("ShaderNodeTexNoise")
    wear_n.inputs["Scale"].default_value = 4.0
    wear_n.inputs["Detail"].default_value = 4.0
    nt.links.new(coord.outputs["Object"], wear_n.inputs["Vector"])
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs[0])
    up = _math(nt, "MULTIPLY_ADD", sep.outputs["Z"], 0.5, 0.5)
    wear = _math(nt, "MULTIPLY", _math(nt, "POWER", up, 3.0),
                 _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", wear_n.outputs["Fac"], 0.42), 2.6, clamp=True))
    base = _mix(nt, wear, ramp.outputs["Color"], (0.190, 0.082, 0.056, 1.0))
    # occlusion: pleats, seams and the joints between parts go deeper
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.05
    aor = nt.nodes.new("ShaderNodeValToRGB")
    aor.color_ramp.elements[0].position = 0.25
    aor.color_ramp.elements[0].color = (0.30, 0.30, 0.30, 1.0)
    aor.color_ramp.elements[1].position = 0.95
    aor.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(ao.outputs["AO"], aor.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(base, mul.inputs[1])
    nt.links.new(aor.outputs["Color"], mul.inputs[2])
    nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
    rr = nt.nodes.new("ShaderNodeValToRGB")
    rr.color_ramp.elements[0].position = 0.25
    rr.color_ramp.elements[0].color = (0.30, 0.30, 0.30, 1.0)
    rr.color_ramp.elements[1].position = 0.80
    rr.color_ramp.elements[1].color = (0.55, 0.55, 0.55, 1.0)
    nt.links.new(mott.outputs["Fac"], rr.inputs["Fac"])
    rough = _math(nt, "ADD", rr.outputs["Color"], _math(nt, "MULTIPLY", wear, -0.12))
    nt.links.new(rough, bsdf.inputs["Roughness"])
    grain = nt.nodes.new("ShaderNodeTexVoronoi")
    grain.inputs["Scale"].default_value = 420.0
    nt.links.new(coord.outputs["Object"], grain.inputs["Vector"])
    crink = nt.nodes.new("ShaderNodeTexNoise")
    crink.inputs["Scale"].default_value = 38.0
    crink.inputs["Detail"].default_value = 3.0
    crink.inputs["Distortion"].default_value = 1.2
    nt.links.new(coord.outputs["Object"], crink.inputs["Vector"])
    height = _math(nt, "ADD", grain.outputs["Distance"], _math(nt, "MULTIPLY", crink.outputs["Fac"], 1.4))
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.16
    bump.inputs["Distance"].default_value = 0.0004
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.25
        bsdf.inputs["Coat Roughness"].default_value = 0.30
    return mat


def _math(nt, op, a, b=None, c=None, clamp=False):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    node.use_clamp = clamp
    for i, x in enumerate((a, b, c)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            node.inputs[i].default_value = float(x)
        else:
            nt.links.new(x, node.inputs[i])
    return node.outputs["Value"]


def _mix(nt, fac, a, b):
    """a where fac is 0, b where fac is 1 (a, b colour tuples or sockets)."""
    node = nt.nodes.new("ShaderNodeMixRGB")
    node.blend_type = "MIX"
    nt.links.new(fac, node.inputs[0])
    for i, x in ((1, a), (2, b)):
        if isinstance(x, tuple):
            node.inputs[i].default_value = x
        else:
            nt.links.new(x, node.inputs[i])
    return node.outputs[0]


def _band(nt, d, lo, hi, soft=0.004):
    """1 where lo < d < hi, soft-edged."""
    a = _math(nt, "DIVIDE", _math(nt, "SUBTRACT", d, lo), soft, clamp=True)
    b = _math(nt, "DIVIDE", _math(nt, "SUBTRACT", hi, d), soft, clamp=True)
    return _math(nt, "MULTIPLY", a, b)


def rug_material():
    """Wool rug, faded: an ivory outer guard, a madder border with an ivory
    running motif, an ivory inner guard, an indigo field with a stepped
    ivory-and-madder medallion and corner spandrels; abrash (the dye lots'
    banding) and a pile bump over all of it. Laid out in object space."""
    mat = bpy.data.materials.new("WoolRug")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.92
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs[0])
    x = _math(nt, "SUBTRACT", sep.outputs["X"], RUG_C[0])
    y = _math(nt, "SUBTRACT", sep.outputs["Y"], RUG_C[1])
    ax = _math(nt, "ABSOLUTE", x)
    ay = _math(nt, "ABSOLUTE", y)
    d = _math(nt, "MINIMUM", _math(nt, "SUBTRACT", RUG_HX, ax), _math(nt, "SUBTRACT", RUG_HY, ay))
    ivory = (0.25, 0.205, 0.145, 1.0)
    madder = (0.118, 0.048, 0.037, 1.0)
    indigo = (0.027, 0.032, 0.046, 1.0)
    rust = (0.15, 0.080, 0.046, 1.0)
    col = indigo
    # medallion: nested diamonds in the field's centre
    diam = _math(nt, "ADD", _math(nt, "DIVIDE", ax, 0.46), _math(nt, "DIVIDE", ay, 0.34))
    col = _mix(nt, _band(nt, diam, -1.0, 1.0, 0.01), col, ivory)
    col = _mix(nt, _band(nt, diam, -1.0, 0.86, 0.01), col, madder)
    col = _mix(nt, _band(nt, diam, 0.34, 0.46, 0.01), col, indigo)
    col = _mix(nt, _band(nt, diam, -1.0, 0.20, 0.01), col, rust)
    # corner spandrels: quarter diamonds in the field's corners
    cx = _math(nt, "SUBTRACT", RUG_HX - 0.20, ax)
    cy = _math(nt, "SUBTRACT", RUG_HY - 0.20, ay)
    spd = _math(nt, "ADD", _math(nt, "DIVIDE", cx, 0.30), _math(nt, "DIVIDE", cy, 0.22))
    col = _mix(nt, _band(nt, spd, -1.0, 1.0, 0.01), col, madder)
    col = _mix(nt, _band(nt, spd, 0.55, 0.70, 0.01), col, ivory)
    # borders by distance to the edge
    col = _mix(nt, _band(nt, d, 0.0, 0.200, 0.002), col, ivory)
    col = _mix(nt, _band(nt, d, 0.030, 0.170, 0.002), col, madder)
    # running motif in the border: rosettes along the edge
    along = _math(nt, "ADD", _math(nt, "MULTIPLY", x, 1.0), _math(nt, "MULTIPLY", y, 1.0))
    ros = _math(nt, "MULTIPLY", _math(nt, "SINE", _math(nt, "MULTIPLY", along, 34.0)),
                _math(nt, "SINE", _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", x, y), 34.0)))
    motif = _math(nt, "MULTIPLY", _band(nt, d, 0.060, 0.140, 0.004),
                  _math(nt, "GREATER_THAN", ros, 0.55))
    col = _mix(nt, motif, col, ivory)
    col = _mix(nt, _band(nt, d, 0.0, 0.010, 0.002), col, madder)
    # abrash and pile
    ab = nt.nodes.new("ShaderNodeTexNoise")
    ab.inputs["Scale"].default_value = 3.0
    ab.inputs["Detail"].default_value = 3.0
    nt.links.new(coord.outputs["Object"], ab.inputs["Vector"])
    abr = nt.nodes.new("ShaderNodeValToRGB")
    abr.color_ramp.elements[0].color = (0.78, 0.78, 0.78, 1.0)
    abr.color_ramp.elements[1].color = (1.08, 1.08, 1.08, 1.0)
    nt.links.new(ab.outputs["Fac"], abr.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(col, mul.inputs[1])
    nt.links.new(abr.outputs["Color"], mul.inputs[2])
    nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
    pile = nt.nodes.new("ShaderNodeTexNoise")
    pile.inputs["Scale"].default_value = 420.0
    pile.inputs["Detail"].default_value = 2.0
    nt.links.new(coord.outputs["Object"], pile.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.0008
    nt.links.new(pile.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def shade_material():
    mat = principled("LinenShade", (0.62, 0.53, 0.38, 1.0), 0.0, 0.85, mottle=0.12,
                     noise_scale=60.0)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.70, 0.40, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.45
    coord = nt.nodes.new("ShaderNodeTexCoord")
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"
    wv.bands_direction = "Z"
    wv.inputs["Scale"].default_value = 240.0
    wv.inputs["Distortion"].default_value = 0.0
    nt.links.new(coord.outputs["Object"], wv.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.0003
    nt.links.new(wv.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def cloth_material():
    """Book cloth: each book's face attribute ``tone`` picks its colour."""
    mat = principled("BookCloth", (0.05, 0.10, 0.07, 1.0), 0.0, 0.62, roughness_var=0.08,
                     noise_scale=180.0)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = "tone"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.035, 0.080, 0.055, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.150, 0.110, 0.060, 1.0)
    nt.links.new(attr.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def bulb_material():
    mat = principled("WarmBulb", (0.95, 0.80, 0.55, 1.0), 0.0, 0.2)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.72, 0.40, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 6.0
    return mat


def vignette_materials():
    """Shared by the check and the render, in slot order."""
    leather = leather_material()
    wood = principled("Walnut", (0.110, 0.048, 0.022, 1.0), 0.0, 0.40, roughness_var=0.08,
                      mottle=0.40, noise_scale=45.0, coat=0.35, stretch=(1.0, 1.0, 10.0))
    brass = metal("AgedBrass", (0.80, 0.58, 0.28, 1.0), 0.26, 0.55,
                  [(0.0, 0.03), (0.20, 0.05), (0.30, 0.18), (0.40, 0.55), (0.48, 1.0),
                   (0.60, 0.35), (0.80, 0.20), (1.0, 0.16)], roughness_var=0.08, noise_scale=60.0)
    shade = shade_material()
    rug = rug_material()
    fringe = principled("CottonFringe", (0.46, 0.41, 0.31, 1.0), 0.0, 0.90, mottle=0.18,
                        noise_scale=90.0)
    cloth = cloth_material()
    paper = principled("PageEdges", (0.52, 0.48, 0.38, 1.0), 0.0, 0.85, mottle=0.10,
                       noise_scale=300.0)
    bulb = bulb_material()
    return leather, wood, brass, shade, rug, fringe, cloth, paper, bulb


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
                report.append((si, sj, tuple(round(c, 3) for c in ci)))
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
        self.kind, self.part = tg // 1000, tg % 1000
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx) if polys else None


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
    return {"all": parts, "groups": groups, "by": by}


def union_tree(shell_list):
    pts, tris = [], []
    for s in shell_list:
        base = len(pts)
        pts += [tuple(p) for p in s.pts]
        tris += [[base + i for i in t] for t in s.tri_idx]
    return BVHTree.FromPolygons(pts, tris)


def pca_axis(pts, largest=False):
    c = sum(pts, Vector()) / len(pts)
    m = [[0.0] * 3 for _ in range(3)]
    for p in pts:
        d = p - c
        for i in range(3):
            for j in range(3):
                m[i][j] += d[i] * d[j]
    mat = Matrix(m)
    # power iteration on the covariance (largest), or on its adjugate-shifted
    # form (smallest)
    if not largest:
        tr = m[0][0] + m[1][1] + m[2][2]
        mat = Matrix(((tr - m[0][0], -m[0][1], -m[0][2]), (-m[1][0], tr - m[1][1], -m[1][2]),
                      (-m[2][0], -m[2][1], tr - m[2][2])))
    v = Vector((0.31, 0.57, 0.76))
    for _ in range(200):
        v = (mat @ v).normalized()
    return c, v


def feet_audit(cls, rug):
    top = rug.hi.z
    by = cls["by"]
    chair = by.get(PAD, []) + by.get(FERRULE, [])
    table = by.get(TPAD, [])
    return top, [top - s.lo.z for s in chair], [top - s.lo.z for s in table]


def leg_audit(cls):
    """Each chair leg's top against the body's underside straight above it:
    a ray up from below the leg top meets the underside first."""
    by = cls["by"]
    body = [s for k in (BASE, ARM, BACK) for s in by.get(k, [])]
    tree = union_tree(body)
    bites = []
    for leg in by.get(LEG, []):
        top_z = leg.hi.z
        ring = [p for p in leg.pts if p.z >= top_z - 1e-4]
        c = sum(ring, Vector()) / len(ring)
        hit, _n = cast(tree, c - Z_AX * 0.15, Z_AX, 0.6)
        bites.append(c.z - hit.z if hit is not None else -9.0)
    return bites


def seat_audit(parts, host_tree, dimple=False):
    """Per part (a lathe dome): its axis (smallest principal axis, pointed
    away from the host), the host surface under its centre, how deep its
    deepest vertex sits below that point, how far its top stands proud,
    and (``dimple``) how far the host's surface rises round it."""
    out = []
    for s in parts:
        c, a = pca_axis(s.pts)
        _loc, hn, _i, _d = host_tree.find_nearest(c)
        if hn is not None and a.dot(hn) < 0.0:
            a = -a
        hit, _n = cast(host_tree, c + a * 0.05, -a, 0.2)
        if hit is None:
            out.append((9.0, -9.0, 0.0, c))
            continue
        # the host lies behind the head: the ray from outside along -a met it
        depth = max((hit - p).dot(a) for p in s.pts)
        proud = max((p - hit).dot(a) for p in s.pts)
        rise = 0.0
        if dimple:
            e1 = a.orthogonal().normalized()
            e2 = a.cross(e1)
            hs = []
            for k in range(8):
                t = 2.0 * math.pi * k / 8
                q = hit + (e1 * math.cos(t) + e2 * math.sin(t)) * DIMPLE_RING
                h2, _n2 = cast(host_tree, q + a * 0.08, -a, 0.2)
                if h2 is not None:
                    hs.append((h2 - hit).dot(a))
            rise = sum(hs) / len(hs) if hs else 0.0
        out.append((depth, proud, rise, hit))
    return out


def mirror_audit(cls):
    pts = [p for k in BODY_KINDS for s in cls["by"].get(k, []) for p in s.pts]
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    worst = 0.0
    for p in pts:
        _co, _i, d = kd.find(Vector((-p.x, p.y, p.z)))
        worst = max(worst, d)
    xs = [p.x for p in pts]
    return worst, max(xs) - min(xs), len(pts)


def lattice_audit(buttons):
    cs = [s.mean for s in buttons]
    ds = []
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            d = (cs[i] - cs[j]).length
            if d < LATTICE_NEAR:
                ds.append(d)
    return ds


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


def tripod_audit(cls):
    by = cls["by"]
    total = 0.0
    mom = Vector()
    for k in TABLE_KINDS:
        for s in by.get(k, []):
            vol, cen = shell_mass(s)
            m = abs(vol) * DENSITY[s.mat]
            total += m
            mom += m * cen
    if total <= 0.0:
        return 0.0, Vector(), -9.0
    com = mom / total
    feet = []
    for s in by.get(TPAD, []):
        low = [p for p in s.pts if p.z <= s.lo.z + 0.002]
        feet.append(((sum(p.x for p in low) / len(low)), (sum(p.y for p in low) / len(low))))
    if len(feet) < 3:
        return total, com, -9.0
    hull = hull2d(feet)
    margin = 9.0
    for i in range(len(hull)):
        ax, ay = hull[i]
        bx, by_ = hull[(i + 1) % len(hull)]
        ex, ey = bx - ax, by_ - ay
        ln = math.hypot(ex, ey)
        margin = min(margin, (ex * (com.y - ay) - ey * (com.x - ax)) / ln)
    return total, com, margin


def nail_audit(cls):
    by = cls["by"]
    arms = by.get(ARM, [])
    rows = {0: [], 1: [], 2: []}
    for s in by.get(NAIL, []):
        rows.setdefault(s.part // 100, []).append(s)
    pitches, seats = [], []
    counts = []
    for side in (0, 1, 2):
        # a nail's station is where its axis meets its host's surface: the
        # two arms' fronts and the front rail
        row = sorted(rows.get(side, []), key=lambda s: s.part)
        counts.append(len(row))
        host = [a for a in arms if a.part == side] if side < 2 else by.get(BASE, [])
        st = seat_audit(row, host[0].tree) if (host and row) else []
        seats += st
        pitches.append([(st[i + 1][3] - st[i][3]).length for i in range(len(st) - 1)])
    return counts, pitches, seats


def rng_(xs, nd=4):
    if not xs:
        return "()"
    return f"({min(xs):.{nd}f}..{max(xs):.{nd}f})"


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
    img = bpy.data.images.new("ArmchairNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = WOOD_IDX
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


def measure(low):
    """Every piece-specific measurement, read off the mesh."""
    me = low.data
    cls = classify(me)
    by = cls["by"]
    r = {"cls": cls}
    rug = by.get(RUG, [None])[0]
    r["rug_top"], r["chair_sinks"], r["table_sinks"] = feet_audit(cls, rug)
    r["leg_bites"] = leg_audit(cls)
    backs = by.get(BACK, [])
    r["buttons"] = seat_audit(by.get(BUTTON, []), backs[0].tree, dimple=True) if backs else []
    r["mirror"], r["width"], r["body_verts"] = mirror_audit(cls)
    cush = by.get(CUSHION, [])
    r["seat_h"] = cush[0].hi.z - r["rug_top"] if cush else 0.0
    r["back_h"] = backs[0].hi.z - r["rug_top"] if backs else 0.0
    r["lattice"] = lattice_audit(by.get(BUTTON, []))
    r["mass"], r["com"], r["tripod"] = tripod_audit(cls)
    bases = by.get(BASE, [])
    r["rest"] = (bases[0].hi.z - cush[0].lo.z) if (bases and cush) else -9.0
    r["nail_counts"], r["nail_pitches"], r["nail_seats"] = nail_audit(cls)
    return r


def budgets_of(bb, r):
    btn = r["buttons"]
    lat = r["lattice"]
    pitches = [p for row in r["nail_pitches"] for p in row]
    spreads = [(max(row) - min(row)) if row else 9.0 for row in r["nail_pitches"]]
    ns = r["nail_seats"]
    return {
        "grounded": bb[2] <= ZMIN_EPS,
        "feet": (len(r["chair_sinks"]) == CHAIR_FEET and len(r["table_sinks"]) == TABLE_FEET
                 and all(SINK_BAND[0] <= s <= SINK_BAND[1] for s in r["chair_sinks"] + r["table_sinks"])),
        "legs": len(r["leg_bites"]) == 4 and all(LEG_BITE[0] <= b <= LEG_BITE[1] for b in r["leg_bites"]),
        "buttons": (len(btn) == BTN_COUNT and all(BTN_SEAT[0] <= d <= BTN_SEAT[1] for d, _p, _r, _h in btn)
                    and all(p >= BTN_PROUD_MIN for _d, p, _r, _h in btn)
                    and all(rr >= DIMPLE_MIN for _d, _p, rr, _h in btn)),
        "mirror": (r["mirror"] <= MIRROR_EPS and SEAT_HEIGHT[0] <= r["seat_h"] <= SEAT_HEIGHT[1]
                   and BACK_HEIGHT[0] <= r["back_h"] <= BACK_HEIGHT[1]
                   and CHAIR_WIDTH[0] <= r["width"] <= CHAIR_WIDTH[1]),
        "lattice": (len(lat) == LATTICE_PAIRS and (max(lat) - min(lat)) <= LATTICE_SPREAD_MAX
                    and LATTICE_BAND[0] <= min(lat) and max(lat) <= LATTICE_BAND[1]) if lat else False,
        "tripod": r["tripod"] >= TRIPOD_MARGIN_MIN,
        "cushion": CUSHION_REST[0] <= r["rest"] <= CUSHION_REST[1],
        "nails": (r["nail_counts"][0] == r["nail_counts"][1] and r["nail_counts"][0] >= 20
                  and r["nail_counts"][2] >= 12
                  and bool(pitches) and max(spreads) <= NAIL_SPREAD_MAX
                  and len(ns) == sum(r["nail_counts"])
                  and all(NAIL_SEAT[0] <= d <= NAIL_SEAT[1] and p >= NAIL_PROUD_MIN for d, p, _r, _h in ns)),
    }


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_mesh("ArmchairLow", 1.0, **flags)
    high = build_mesh("ArmchairHigh", 1.5, **flags)
    mats = vignette_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    wood = mats[WOOD_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none1 = (None,)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("armchair mesh did not build", 3),) + none1

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
    r = measure(low)
    cls = r["cls"]
    zrep = []
    zf = zfight_pairs(low.data, cls["groups"], zrep)
    if not cls["by"].get(RUG) or not cls["by"].get(BACK) or not cls["by"].get(CUSHION):
        return (fail("rug, back or cushion shell not found", 3),) + none1

    img, tex = setup_bake_image(low, wood)
    if img is None:
        return (fail("armchair has no UV layer", 3),) + none1
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "ArmchairLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "ArmchairLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(low, "ArmchairCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_wingback_armchair_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    budgets = budgets_of(bb, r)
    by = cls["by"]
    btn = r["buttons"]
    lat = r["lattice"]
    ns = r["nail_seats"]
    spreads = [(max(row) - min(row)) if row else 9.0 for row in r["nail_pitches"]]
    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
          f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}")
    print(f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
          f"overlap={overlap:.6f} nfaces={nfaces}")
    print(f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
          f"outer={OUTER_SIZE} zmin={bb[2]:.5f} min=({bb[0]:.4f},{bb[1]:.4f}) max=({bb[3]:.4f},{bb[4]:.4f})")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    zkinds = {}
    for si, sj, at in zrep:
        key = tuple(sorted((cls['all'][si].kind, cls['all'][sj].kind)))
        zkinds.setdefault(key, [0, at])[0] += 1
    for key, (n, at) in sorted(zkinds.items()):
        print(f"measured zfight_pairs kinds={key} n={n} e.g. at {at}")
    print(f"measured shells={len(cls['all'])} tassels={len(by.get(TASSEL, []))} "
          f"buttons={len(by.get(BUTTON, []))} nails={r['nail_counts']} legs={len(by.get(LEG, []))}")
    print(f"measured feet rug_top={r['rug_top']:.4f} chair_sinks={rng_(r['chair_sinks'], 5)} "
          f"table_sinks={rng_(r['table_sinks'], 5)}")
    print(f"measured leg_bites={[round(b, 4) for b in r['leg_bites']]}")
    print(f"measured buttons n={len(btn)} seat={rng_([d for d, _p, _r, _h in btn], 5)} "
          f"proud={rng_([p for _d, p, _r, _h in btn], 5)} dimple={rng_([rr for _d, _p, rr, _h in btn], 5)}")
    print(f"measured mirror={r['mirror']:.6f} over {r['body_verts']} verts seat_h={r['seat_h']:.4f} "
          f"back_h={r['back_h']:.4f} width={r['width']:.4f}")
    print(f"measured lattice pairs={len(lat)} {rng_(lat, 5)} spread="
          f"{(max(lat) - min(lat)) if lat else 9.0:.5f}")
    print(f"measured tripod mass={r['mass']:.2f}kg com=({r['com'].x:.4f},{r['com'].y:.4f},"
          f"{r['com'].z:.4f}) margin={r['tripod']:.4f}")
    print(f"measured cushion rest={r['rest']:.5f}")
    print(f"measured nails counts={r['nail_counts']} pitch={rng_([p for row in r['nail_pitches'] for p in row], 5)} "
          f"spread={[round(s, 5) for s in spreads]} seat={rng_([d for d, _p, _r, _h in ns], 5)} "
          f"proud={rng_([p for _d, p, _r, _h in ns], 5)}")
    print(f"measured budget_fails={[k for k, ok in budgets.items() if not ok]}")

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
    if not budgets["grounded"]:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none1
    if not budgets["feet"]:
        return (fail(f"feet: {len(r['chair_sinks'])}/{CHAIR_FEET} chair and {len(r['table_sinks'])}/"
                     f"{TABLE_FEET} table feet sunk {rng_(r['chair_sinks'], 5)} / "
                     f"{rng_(r['table_sinks'], 5)} m into the rug, not all in {SINK_BAND}", 16),) + none1
    if not budgets["legs"]:
        return (fail(f"legs: {len(r['leg_bites'])}/4 legs tenoned "
                     f"{[round(b, 4) for b in r['leg_bites']]} m into the body, not all in {LEG_BITE}", 17),) + none1
    if not budgets["buttons"]:
        return (fail(f"buttons: {len(btn)}/{BTN_COUNT}, seated {rng_([d for d, _p, _r, _h in btn], 5)} m "
                     f"(band {BTN_SEAT}), proud {rng_([p for _d, p, _r, _h in btn], 5)} m "
                     f"(min {BTN_PROUD_MIN}), dimple {rng_([rr for _d, _p, rr, _h in btn], 5)} m "
                     f"(min {DIMPLE_MIN})", 18),) + none1
    if not budgets["mirror"]:
        return (fail(f"mirror and size: worst vertex {r['mirror']:.6f} m off its mirror partner "
                     f"(max {MIRROR_EPS}), seat {r['seat_h']:.4f} m {SEAT_HEIGHT}, back "
                     f"{r['back_h']:.4f} m {BACK_HEIGHT}, width {r['width']:.4f} m {CHAIR_WIDTH}", 19),) + none1
    if not budgets["lattice"]:
        return (fail(f"lattice: {len(lat)}/{LATTICE_PAIRS} diagonal pairs at {rng_(lat, 5)} m, spread "
                     f"{(max(lat) - min(lat)) if lat else 9.0:.5f} (max {LATTICE_SPREAD_MAX}), "
                     f"band {LATTICE_BAND}", 20),) + none1
    if not budgets["tripod"]:
        return (fail(f"tripod: mass centre of table, lamp and books {r['tripod']:.4f} m inside the "
                     f"feet's triangle (min {TRIPOD_MARGIN_MIN})", 21),) + none1
    if not budgets["cushion"]:
        return (fail(f"cushion: underside {r['rest']:.5f} m into the deck, not in {CUSHION_REST}", 22),) + none1
    if not budgets["nails"]:
        return (fail(f"nails: {r['nail_counts']} per arm, pitch spread {[round(s, 5) for s in spreads]} "
                     f"(max {NAIL_SPREAD_MAX}), seated {rng_([d for d, _p, _r, _h in ns], 5)} m "
                     f"(band {NAIL_SEAT}), proud {rng_([p for _d, p, _r, _h in ns], 5)} m "
                     f"(min {NAIL_PROUD_MIN})", 23),) + none1
    return 0, low


def render_still(low, path, engine):
    scene = bpy.context.scene
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(HERO_YAW_DEG)
    bpy.context.view_layer.update()
    corners = [low.matrix_world @ Vector(c) for c in low.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    centre = 0.5 * (lo + hi)

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

    # The house rig scaled to a 2 m vignette: warm key upper left, cool fill
    # low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-2.2, -2.6, 2.3), 136.0, 1.4, (1.0, 0.95, 0.90), spread=30.0)
    light("Fill", (2.8, -1.9, 0.5), 13.0, 3.0, (0.72, 0.82, 1.0))
    light("Rim", (-0.9, 1.6, 1.4), 70.0, 1.2, (0.62, 0.78, 1.0))
    light("Wedge", (2.4, 2.4, 1.0), 150.0, 2.0, (1.0, 0.68, 0.38),
          target=(centre.x + 2.6, centre.y + WALL_Y, 0.5))
    # the reading lamp: a warm point inside its shade
    ld = bpy.data.lights.new("Bulb", "POINT")
    ld.energy = 6.0
    ld.color = (1.0, 0.72, 0.42)
    ld.shadow_soft_size = 0.02
    bulb = bpy.data.objects.new("Bulb", ld)
    bulb.location = low.matrix_world @ W(TABLE_C[0] + LAMP_OFF[0], TABLE_C[1] + LAMP_OFF[1],
                                         TABLE_TOP_Z + 0.470)
    scene.collection.objects.link(bulb)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.50, -0.87, 0.0)).normalized()
    cam.location = centre + view * 4.30 + Vector((0.0, 0.0, 0.64))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.15))
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
    # Standard, not AgX: AgX lifts the oxblood toward brick and greys the stage.
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
    p.add_argument("--float-foot", action="store_true")
    p.add_argument("--short-legs", action="store_true")
    p.add_argument("--sink-buttons", action="store_true")
    p.add_argument("--odd-wing", action="store_true")
    p.add_argument("--drift-buttons", action="store_true")
    p.add_argument("--narrow-tripod", action="store_true")
    p.add_argument("--lift-cushion", action="store_true")
    p.add_argument("--bunch-nails", action="store_true")
    args = p.parse_args(argv)

    flags = {name: getattr(args, name) for name in FLAG_NAMES}
    code, low = check(args.skip_decimate, lift_z=args.lift_z, stray_vert=args.stray_vert, **flags)
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("wingback-armchair OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
