"""Game-ready traffic cone and barrier set — a showcase piece, not an example.

Asserts budget conformance of a procedural roadworks set after composing
shipped pipeline pieces: bmesh construction, UVs, eleven materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

A patch of asphalt, broken at its edges, carries a worn white road line and
two sealed cracks. On it stand three 720 mm PVC traffic cones in a taper
line, a stack of three cones nested one inside the next, and a fourth cone
knocked over onto its side. Every cone is a moulded body (a hollow frustum
with a bead above the collar and a rolled lip round an open tip) bonded into
a square rubber base with chamfered corners, a raked top, a collar, four
moulded lugs and a recess underneath, and two retroreflective collar bands.
Behind them stands a folding A-frame barricade: four square steel legs hinged
in pairs on pivot bolts, spread by straps on spacer pins, each foot in a
rubber pad; two striped boards on each face, bolted to the legs; and a
warning lamp on a bracket at one end of the top board.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-cone`` every support bedded
on the slab, ``--gap-board`` the boards' bite into the legs,
``--float-band`` the collar bands' seat, ``--lean-cone`` and
``--skew-leg`` plumb, size and mirror symmetry, ``--loose-stack`` the
nesting of the stack, ``--loose-lamp`` one connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python traffic_cones.py --
    blender --background --python traffic_cones.py -- --skip-decimate
    blender --background --python traffic_cones.py -- --output cones.png
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

# --- Asphalt patch ------------------------------------------------------------
SLAB_T = 0.060
SLAB_HX = 1.50
SLAB_HY = 1.00
SLAB_CORNER = 0.16
SLAB_PERIM = 120
SLAB_JITTER = 0.024          # broken edge, closed-form
SLAB_TOP_CH = 0.010
SLAB_BOT_CH = 0.004
SEAT = 0.0015                # every support bears this far into the slab
LINE_Y = -0.84               # worn white road line
LINE_HALF_W = 0.050
LINE_END_CLEAR = 0.030
PAINT_TOP = 0.0010
PAINT_SINK = 0.0020
TAR_HALF_W = 0.011           # sealed cracks
TAR_TOP = 0.0008
TAR_SINK = 0.0024

# --- Cone (local frame: base bottom at z=0, axis +Z) --------------------------
CONE_H = 0.720               # 28 in cone
BASE_HALF = 0.178            # 14 in square base
BASE_CUT = 0.046             # chamfered corners
BASE_EDGE_T = 0.022
BASE_CH = 0.004
BASE_TOP_R = 0.165           # raked top meets the collar here
BASE_TOP_Z = 0.028
COLLAR_R = 0.150
COLLAR_Z = 0.044
COLLAR_TOP = 0.048
RECESS_R = 0.166             # moulded recess under the base: takes the collar below
RECESS_H = 0.018
BODY_BITE = 0.0015           # base hole bonded this far inside the body's wall
BODY_Z0 = 0.024
BODY_R0 = 0.137              # body outer radius at the collar top
BODY_R1 = 0.032              # ... at the top of the straight wall
BODY_TOP = 0.700
BODY_SLOPE = (BODY_R0 - BODY_R1) / (BODY_TOP - COLLAR_TOP)
STACK_PITCH = 0.036          # nesting pitch: set by the wall, not by the bases
NEST_BITE = 0.0010           # an upper cone's inner wall bears this far on the lower's outer wall
WALL_H = BODY_SLOPE * STACK_PITCH + NEST_BITE
BEAD = 0.0015
LIP = 0.0025
BODY_SEGS = 48
BAND_Z = ((0.326, 0.428), (0.479, 0.631))   # 4 in and 6 in collars
BAND_T = 0.0014
BAND_CH = 0.0006
BAND_BITE = 0.0006
LUG_RHO = 0.190
LUG_R = 0.016

STANDING = ((-0.74, -0.30, 12.0), (-0.12, -0.50, -7.0), (1.02, 0.34, 21.0))
STACK_XY = (-1.06, 0.44)
STACK_YAW = (3.1, -8.7, 14.9)  # never a multiple of the base's angle step apart
TIPPED_XY = (0.52, -0.46)    # base centre in plan
TIPPED_YAW = 126.87          # tip toward the back right: its base faces the lens
CONE_TONES = (0.15, 0.85, 0.45, 0.30, 0.65, 0.95, 0.05)

# --- Barricade ---------------------------------------------------------------
BAR_X = 0.10
BAR_Y = 0.46
LEG_X = 0.520                # hinge stations at BAR_X +- LEG_X
LEG_SPLIT = 0.0175           # leg centres off the hinge station: 3 mm between the pair
LEG_HALF = 0.016             # 32 mm square tube
LEG_RC = 0.003
HINGE_Z = 1.000
FOOT_Y = 0.300
LEG_OVER = 0.045
PAD_HX = 0.042
PAD_HY = 0.078
PAD_T = 0.016
LEG_IN_PAD = 0.007
BOARD_L = 1.240
BOARD_H = 0.200
BOARD_T = 0.018
BOARD_RC = 0.004
BOARD_Z = (0.800, 0.500)     # board centres, height above the slab, on the leg
BOARD_BITE = 0.0015
STRIPE_W = 0.100
STRIPE_PHASE = 0.0371
BOLT_V = 0.060
BOLT_SINK = 0.0008
STRAP_Z = 0.300
STRAP_W = 0.028
STRAP_T = 0.004
STRAP_GAP = 0.004
# lamp on a bracket at the left end of the top front board
LAMP_DX = 0.105
BR_T = 0.005
BR_HALF_W = 0.020
BR_BITE = 0.0008
BOX_H = 0.120
HOUSING_R = 0.098

# --- Falsifier sizes ---------------------------------------------------------
FLOAT_CONE = 0.004           # --float-cone: standing cone 2
GAP_BOARD = 0.003            # --gap-board: lower front board
FLOAT_BAND = 0.002           # --float-band: cone 0's upper band
LEAN_DEG = 1.5               # --lean-cone: cone 1's body in its base
SKEW_LEG = 0.0025            # --skew-leg: right front leg toward the centre
LOOSE_STACK = 0.010          # --loose-stack: the top cone of the stack (12 mm put its
                             # base bottom on the middle cone's collar-top plane)
LOOSE_LAMP = 0.003           # --loose-lamp: lamp off its board

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from the vertices.
OUTER_SIZE = (3.0365, 2.0374, 1.3354)
BASE_TRIS_MIN = 45300
BASE_TRIS_MAX = 46400
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 11
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 540
BAKE_RES = 1024
CAGE_EXTRUSION = 0.01

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Supports: every standing base, the stack's bottom base, the fallen cone's
# base and body, and the four barricade pads bear into the slab in a band.
SUPPORT_COUNT = 10
SINK_MIN = 0.0008
SINK_MAX = 0.0030
# Boards bite the legs they are bolted to.
BOARD_COUNT = 4
BOARD_LEG_JOINTS = 8
BOARD_BITE_MIN = 0.0008
BOARD_BITE_MAX = 0.0030
# Collar bands: inner face seated into the body, outer face proud of it.
BANDS = 14
BAND_SEAT_MIN = 0.0002
BAND_SEAT_MAX = 0.0015
BAND_PROUD_MIN = 0.0010
# Plumb and real-world size; the barricade's legs mirror about its centre.
PLUMB_CONES = 6
PLUMB_MAX_DEG = 0.2
CONE_H_TOL = 0.003
BASE_W = 2.0 * BASE_HALF
BASE_W_TOL = 0.003
LEGS = 4
MIRROR_EPS = 0.001
# Nesting: one stack of three, each on the one below at the nesting pitch.
STACK_N = 3
PITCH_MIN = 0.030
PITCH_MAX = 0.042
NEST_MIN = 0.0004
NEST_MAX = 0.0020

HERO_YAW_DEG = 0.0
CAM_VIEW = (-0.42, -0.91)
CAM_DIST = 5.9
CAM_LENS = 50.0
CAM_LIFT = 2.7
AIM_OFFSET = (0.0, 0.0, -0.32)
WALL_Y = 6.0

CONE_IDX = 0
REFLECT_IDX = 1
RUBBER_IDX = 2
ASPHALT_IDX = 3
PAINT_IDX = 4
TAR_IDX = 5
SHEETING_IDX = 6
BOARD_IDX = 7
STEEL_IDX = 8
PLASTIC_IDX = 9
LENS_IDX = 10

FACE_FLOORS = {
    CONE_IDX: 5560, REFLECT_IDX: 3760, RUBBER_IDX: 7440, ASPHALT_IDX: 540, PAINT_IDX: 50,
    TAR_IDX: 450, SHEETING_IDX: 58, BOARD_IDX: 350, STEEL_IDX: 2670, PLASTIC_IDX: 660,
    LENS_IDX: 640,
}
MAT_LABELS = ("cone PVC", "reflective", "rubber", "asphalt", "road paint", "tar",
              "sheeting", "board", "steel", "plastic", "lens")

X = Vector((1.0, 0.0, 0.0))
Y = Vector((0.0, 1.0, 0.0))
Z = Vector((0.0, 0.0, 1.0))
TONE = "PartTone"


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
    return faces


def _tone(bm, faces, t):
    layer = bm.faces.layers.float.get(TONE)
    for f in faces:
        f[layer] = t


def faces_of(verts):
    return {f for v in verts for f in v.link_faces}


def frame(ez, ex_hint):
    """Rotation whose local Z is ``ez`` and local X is ``ex_hint`` made
    orthogonal to it (columns ex, ey, ez)."""
    ez = Vector(ez).normalized()
    ex = Vector(ex_hint)
    ex = (ex - ez * ex.dot(ez)).normalized()
    ey = ez.cross(ex)
    return Matrix((ex, ey, ez)).transposed()


def m4(rot3, loc):
    m = rot3.to_4x4()
    m.translation = Vector(loc)
    return m


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: an open
    polyline closed by n-gon caps; otherwise a closed polygon revolved into a
    ring shell."""
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


def revolve(bm, profile, segs, mat_idx, M, phase=0.0):
    """Closed (r, z) polygon revolved about local Z, placed by the 4x4 ``M``."""
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new(M @ Vector((r * ca, r * sa, z))) for r, z in profile])
    n = len(profile)
    faces = []
    for i in range(segs):
        r0, r1 = rings[i], rings[(i + 1) % segs]
        for j in range(n):
            k = (j + 1) % n
            faces.append(bm.faces.new((r0[j], r1[j], r1[k], r0[k])))
    return _mark(faces, mat_idx)


def loft_loops(bm, loops, mat_idx, M):
    """Closed loops of equal length joined in a closed ring of loops (a torus)."""
    vs = [[bm.verts.new(M @ Vector(p)) for p in loop] for loop in loops]
    n, k = len(vs), len(vs[0])
    faces = []
    for j in range(n):
        a, b = vs[j], vs[(j + 1) % n]
        for i in range(k):
            i2 = (i + 1) % k
            faces.append(bm.faces.new((a[i], a[i2], b[i2], b[i])))
    return _mark(faces, mat_idx)


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


def add_bar(bm, pts, wax, half_w, half_t, rc, mat_idx, fillet=0.008):
    """Flat bar bent in the plane normal to ``wax``: its width lies along
    ``wax``, its thickness in the bending plane; rounded-rectangle section."""
    pts = fillet_path(pts, fillet)
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


def add_ribbon(bm, pts2d, half_w, z0, z1, mat_idx):
    """A flat strip laid along a plan polyline: a six-point section with its
    top corners chamfered, swept with capped ends."""
    pts = [Vector((x, y)) for x, y in pts2d]
    sec = [(-half_w, z0), (half_w, z0), (half_w, z1 - 0.0008), (half_w * 0.55, z1),
           (-half_w * 0.55, z1), (-half_w, z1 - 0.0008)]
    rings = []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        t = (b - a).normalized()
        nrm = Vector((-t.y, t.x))
        rings.append([bm.verts.new((p.x + nrm.x * s, p.y + nrm.y * s, z)) for s, z in sec])
    n = len(sec)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    return _mark(faces, mat_idx)


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


def lug_outline(circles, n=16):
    pts = []
    for u, v, r in circles:
        for k in range(n):
            a = 2.0 * math.pi * (k + 0.5) / n
            pts.append((u + r * math.cos(a), v + r * math.sin(a)))
    return hull2d(pts)


def merge_bm(dst, src, M):
    """Copy every face of ``src`` into ``dst`` through the 4x4 ``M``, keeping
    material index and tone."""
    sl = src.faces.layers.float.get(TONE)
    dl = dst.faces.layers.float.get(TONE)
    vmap = {v: dst.verts.new(M @ v.co) for v in src.verts}
    out = []
    for f in src.faces:
        nf = dst.faces.new([vmap[v] for v in f.verts])
        nf.material_index = f.material_index
        nf[dl] = f[sl]
        out.append(nf)
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


# --------------------------------------------------------------------------
# The asphalt patch
# --------------------------------------------------------------------------

def slab_outline():
    """Rounded rectangle resampled evenly and pushed along its normal by a
    closed-form jitter: the broken edge of a cut-out patch of road."""
    loop = [Vector(p) for p in rrect(SLAB_HX, SLAB_HY, SLAB_CORNER, 10)]
    seg = [(loop[i], loop[(i + 1) % len(loop)]) for i in range(len(loop))]
    total = sum((b - a).length for a, b in seg)
    out = []
    for k in range(SLAB_PERIM):
        target = total * k / SLAB_PERIM
        acc = 0.0
        for a, b in seg:
            ln = (b - a).length
            if acc + ln >= target:
                out.append(a + (b - a) * ((target - acc) / ln))
                break
            acc += ln
    pts = []
    for k, p in enumerate(out):
        a = out[k - 1]
        b = out[(k + 1) % len(out)]
        t = (b - a).normalized()
        nrm = Vector((t.y, -t.x))
        s = k / SLAB_PERIM
        j = SLAB_JITTER * (0.50 * math.sin(2 * math.pi * 3 * s + 0.4)
                           + 0.30 * math.sin(2 * math.pi * 7 * s + 1.3)
                           + 0.20 * math.sin(2 * math.pi * 19 * s + 2.1))
        pts.append((p + nrm * j, nrm))
    return pts


def inset_ring(outline, inset):
    # the normal at each point is an average of neighbours; re-derive it so
    # the inset follows the jittered edge
    base = [p for p, _n in outline]
    out = []
    for k, p in enumerate(base):
        t = (base[(k + 1) % len(base)] - base[k - 1]).normalized()
        nrm = Vector((t.y, -t.x))
        out.append(p - nrm * inset)
    return out


def slab_top_polygon():
    return inset_ring(slab_outline(), SLAB_TOP_CH)


def x_range_at(poly, y):
    xs = []
    n = len(poly)
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        if (a.y - y) * (b.y - y) < 0.0:
            t = (y - a.y) / (b.y - a.y)
            xs.append(a.x + (b.x - a.x) * t)
    return min(xs), max(xs)


def build_slab(bm):
    outline = slab_outline()
    rings_2d = [(inset_ring(outline, SLAB_BOT_CH), 0.0), (inset_ring(outline, 0.0), SLAB_BOT_CH),
                (inset_ring(outline, 0.0), SLAB_T - SLAB_TOP_CH), (inset_ring(outline, SLAB_TOP_CH), SLAB_T)]
    rings = [[bm.verts.new((p.x, p.y, z)) for p in ring] for ring, z in rings_2d]
    n = len(rings[0])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, ASPHALT_IDX)
    _tone(bm, faces, 0.5)

    # the road line runs to within a clearance of the patch's broken edge
    top = slab_top_polygon()
    lo0, hi0 = x_range_at(top, LINE_Y - LINE_HALF_W)
    lo1, hi1 = x_range_at(top, LINE_Y + LINE_HALF_W)
    x0 = max(lo0, lo1) + LINE_END_CLEAR
    x1 = min(hi0, hi1) - LINE_END_CLEAR
    line = [(x0 + (x1 - x0) * k / 8, LINE_Y) for k in range(9)]
    _tone(bm, add_ribbon(bm, line, LINE_HALF_W, SLAB_T - PAINT_SINK, SLAB_T + PAINT_TOP,
                         PAINT_IDX), 0.5)

    # two sealed cracks, closed-form meanders
    crack_a = []
    for k in range(41):
        t = k / 40
        x = -1.28 + 1.10 * t
        y = -0.60 + 0.07 * math.sin(2.3 * x + 0.4) + 0.025 * math.sin(7.9 * x + 1.1) + 0.10 * t
        crack_a.append((x, y))
    crack_b = []
    for k in range(41):
        t = k / 40
        crack_b.append((0.98 + 0.34 * t + 0.030 * math.sin(9.0 * t + 0.3),
                        -0.66 + 0.30 * t + 0.022 * math.sin(13.0 * t + 1.7)))
    for path, tone in ((crack_a, 0.3), (crack_b, 0.7)):
        _tone(bm, add_ribbon(bm, path, TAR_HALF_W, SLAB_T - TAR_SINK, SLAB_T + TAR_TOP, TAR_IDX),
              tone)


# --------------------------------------------------------------------------
# Traffic cone
# --------------------------------------------------------------------------

def r_out(z):
    return BODY_R0 - BODY_SLOPE * (z - COLLAR_TOP)


def r_in(z):
    return r_out(z) - WALL_H


def base_angles():
    """Uniform angles plus the eight corners of the chamfered square, so every
    square ring carries its corners exactly and every round ring follows."""
    a, c = BASE_HALF, BASE_CUT
    t1 = math.atan2(a - c, a)
    corners = []
    for q in range(4):
        corners += [t1 + q * 0.5 * math.pi, 0.5 * math.pi - t1 + q * 0.5 * math.pi]
    uni = [2.0 * math.pi * k / 56 for k in range(56)]
    keep = [u for u in uni
            if all(abs(((u - cc + math.pi) % (2 * math.pi)) - math.pi) > math.radians(2.0)
                   for cc in corners)]
    return sorted(keep + corners)


def sq_r(theta, a):
    c = BASE_CUT * a / BASE_HALF
    ca, sa = abs(math.cos(theta)), abs(math.sin(theta))
    r = (2.0 * a - c) / (ca + sa)
    if ca > 1e-9:
        r = min(r, a / ca)
    if sa > 1e-9:
        r = min(r, a / sa)
    return r


def base_loops():
    angs = base_angles()

    def sq(a, z):
        return [(sq_r(t, a) * math.cos(t), sq_r(t, a) * math.sin(t), z) for t in angs]

    def circ(r, z):
        return [(r * math.cos(t), r * math.sin(t), z) for t in angs]

    return [
        sq(BASE_HALF - BASE_CH, 0.0),
        sq(BASE_HALF, BASE_CH),
        sq(BASE_HALF, BASE_EDGE_T - BASE_CH),
        sq(BASE_HALF - BASE_CH, BASE_EDGE_T),
        circ(BASE_TOP_R, BASE_TOP_Z),
        circ(COLLAR_R, BASE_TOP_Z + 0.002),
        circ(COLLAR_R, COLLAR_Z),
        circ(COLLAR_R - 0.004, COLLAR_TOP),
        circ(r_out(COLLAR_TOP) - BODY_BITE, COLLAR_TOP),
        circ(r_out(RECESS_H) - BODY_BITE, RECESS_H),
        circ(RECESS_R, RECESS_H),
        circ(RECESS_R, 0.003),
        circ(RECESS_R + 0.003, 0.0),
    ]


def base_top_z(theta, rho):
    """Height of the base's raked top at (theta, rho): linear between the
    square edge ring and the round ring at that angle."""
    r3 = sq_r(theta, BASE_HALF - BASE_CH)
    t = (r3 - rho) / (r3 - BASE_TOP_R)
    return BASE_EDGE_T + t * (BASE_TOP_Z - BASE_EDGE_T)


def body_profile():
    pts = [(r_out(BODY_Z0), BODY_Z0), (r_out(0.064), 0.064), (r_out(0.069) + BEAD, 0.069),
           (r_out(0.080) + BEAD, 0.080), (r_out(0.085), 0.085)]
    for z0, z1 in BAND_Z:
        pts += [(r_out(z0), z0), (r_out(z1), z1)]
    pts += [(r_out(0.690), 0.690), (r_out(0.697) + LIP, 0.697), (r_out(0.709) + LIP, 0.709),
            (r_out(0.7165) + 0.0008, 0.7165), (r_out(CONE_H) - 0.0015, CONE_H),
            (r_in(CONE_H) + 0.0015, CONE_H), (r_in(0.716), 0.716), (r_in(0.700), 0.700),
            (r_in(BODY_Z0), BODY_Z0)]
    return pts


def band_profile(z0, z1, extra=0.0):
    e = extra
    return [(r_out(z0) - BAND_BITE + e, z0), (r_out(z0) + BAND_T - BAND_CH + e, z0),
            (r_out(z0 + BAND_CH) + BAND_T + e, z0 + BAND_CH),
            (r_out(z1 - BAND_CH) + BAND_T + e, z1 - BAND_CH),
            (r_out(z1) + BAND_T - BAND_CH + e, z1), (r_out(z1) - BAND_BITE + e, z1)]


def cone_bm(tone, lean_deg=0.0, float_band=0.0):
    """One cone in its local frame, in its own bmesh."""
    cb = bmesh.new()
    layer = cb.faces.layers.float.new(TONE)
    ident = Matrix.Identity(4)
    loft_loops(cb, base_loops(), RUBBER_IDX, ident)
    # four moulded lugs on the raked top, one toward each corner
    for q in range(4):
        th = math.radians(45.0 + 90.0 * q)
        zc = base_top_z(th, LUG_RHO)
        prof = [(LUG_R, -0.003), (LUG_R, 0.002), (LUG_R - 0.004, 0.0048), (0.004, 0.0060)]
        add_lathe(cb, prof, 16, RUBBER_IDX,
                  center=(LUG_RHO * math.cos(th), LUG_RHO * math.sin(th), zc), solid=True)
    lean = (Matrix.Translation((0.0, 0.0, COLLAR_TOP))
            @ Matrix.Rotation(math.radians(lean_deg), 4, "X")
            @ Matrix.Translation((0.0, 0.0, -COLLAR_TOP)))
    revolve(cb, body_profile(), BODY_SEGS, CONE_IDX, lean)
    for bi, (z0, z1) in enumerate(BAND_Z):
        revolve(cb, band_profile(z0, z1, float_band if bi == 1 else 0.0), BODY_SEGS,
                REFLECT_IDX, lean)
    for f in cb.faces:
        f[layer] = tone
    return cb


def tipped_matrix(cb):
    """The fallen cone lies on the edge of its base and the lip of its tip:
    solve the roll about local X at which both touch, then yaw and seat it."""
    base = [v.co.copy() for v in cb.verts
            if any(f.material_index == RUBBER_IDX for f in v.link_faces)]
    lip = [v.co.copy() for v in cb.verts if v.co.z > 0.65
           and any(f.material_index == CONE_IDX for f in v.link_faces)]

    def gap(phi):
        r = Matrix.Rotation(phi, 3, "X")
        return min((r @ p).z for p in base) - min((r @ p).z for p in lip)

    lo, hi = math.radians(90.0), math.radians(120.0)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if gap(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    phi = 0.5 * (lo + hi)
    rot = Matrix.Rotation(math.radians(TIPPED_YAW), 4, "Z") @ Matrix.Rotation(phi, 4, "X")
    zmin = min((rot @ v.co).z for v in cb.verts)
    return Matrix.Translation((TIPPED_XY[0], TIPPED_XY[1], SLAB_T - SEAT - zmin)) @ rot, phi


def build_cones(bm, flags):
    k = 0
    for i, (x, y, yaw) in enumerate(STANDING):
        cb = cone_bm(CONE_TONES[k], lean_deg=LEAN_DEG if (flags["lean_cone"] and i == 1) else 0.0,
                     float_band=FLOAT_BAND if (flags["float_band"] and i == 0) else 0.0)
        lift = FLOAT_CONE if (flags["float_cone"] and i == 2) else 0.0
        M = Matrix.Translation((x, y, SLAB_T - SEAT + lift)) @ Matrix.Rotation(
            math.radians(yaw), 4, "Z")
        merge_bm(bm, cb, M)
        cb.free()
        k += 1
    for j, yaw in enumerate(STACK_YAW):
        cb = cone_bm(CONE_TONES[k])
        lift = LOOSE_STACK if (flags["loose_stack"] and j == len(STACK_YAW) - 1) else 0.0
        M = Matrix.Translation((STACK_XY[0], STACK_XY[1],
                                SLAB_T - SEAT + j * STACK_PITCH + lift)) @ Matrix.Rotation(
            math.radians(yaw), 4, "Z")
        merge_bm(bm, cb, M)
        cb.free()
        k += 1
    cb = cone_bm(CONE_TONES[k])
    M, _phi = tipped_matrix(cb)
    merge_bm(bm, cb, M)
    cb.free()


# --------------------------------------------------------------------------
# A-frame barricade
# --------------------------------------------------------------------------

def leg_line(sgn, back, dx=0.0):
    """Foot-to-pivot line of one leg: (bottom end, top end, direction,
    outward face normal, pad centre)."""
    xs = BAR_X + sgn * LEG_X + (sgn * LEG_SPLIT if back else -sgn * LEG_SPLIT) + dx
    ys = 1.0 if back else -1.0
    H = Vector((xs, BAR_Y, SLAB_T + HINGE_Z))
    G = Vector((xs, BAR_Y + ys * FOOT_Y, SLAB_T))
    d = (H - G).normalized()
    pad_top = SLAB_T - SEAT + PAD_T
    E = G + d * ((pad_top - LEG_IN_PAD - G.z) / d.z)
    T = H + d * LEG_OVER
    padc = G + d * ((pad_top - G.z) / d.z)
    n_out = X.cross(d) * (-1.0 if back else 1.0)
    return E, T, d, n_out, padc


def leg_y(back, z):
    ys = 1.0 if back else -1.0
    return BAR_Y + ys * FOOT_Y * (1.0 - (z - SLAB_T) / HINGE_Z)


def board_bm(n_corner, tone):
    """A striped board in its own frame (u along its length, v up the leg, w
    through it), its faces split on 45-degree lines into orange and white."""
    bb = bmesh.new()
    layer = bb.faces.layers.float.new(TONE)
    L, H, T = BOARD_L, BOARD_H, BOARD_T
    ch = 0.003
    rings = []
    for inset, u in ((ch, -L / 2), (0.0, -L / 2 + ch), (0.0, L / 2 - ch), (ch, L / 2)):
        loop = rrect(H / 2 - inset, T / 2 - inset, BOARD_RC - inset, n_corner)
        rings.append([bb.verts.new((u, v, w)) for v, w in loop])
    n = len(rings[0])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            bb.faces.new((r0[k], r0[m], r1[m], r1[k]))
    bb.faces.new(tuple(reversed(rings[0])))
    bb.faces.new(tuple(rings[-1]))
    pitch = STRIPE_W * math.sqrt(2.0)
    no = Vector((1.0, 1.0, 0.0)).normalized()
    j0 = math.floor((-(L + H) / 2 - STRIPE_PHASE) / pitch)
    j1 = math.ceil(((L + H) / 2 - STRIPE_PHASE) / pitch)
    for j in range(j0, j1 + 1):
        c = STRIPE_PHASE + j * pitch
        geom = list(bb.verts) + list(bb.edges) + list(bb.faces)
        bmesh.ops.bisect_plane(bb, geom=geom, plane_co=(c, 0.0, 0.0), plane_no=no)
    bb.normal_update()
    for f in bb.faces:
        if abs(f.normal.z) > 0.95:
            s = sum(v.co.x + v.co.y for v in f.verts) / len(f.verts)
            k = math.floor((s - STRIPE_PHASE) / pitch)
            f.material_index = SHEETING_IDX if k % 2 == 0 else REFLECT_IDX
        else:
            f.material_index = BOARD_IDX
        f[layer] = tone
    return bb


def add_dome(bm, center, axis, mat_idx, r=0.012, h=0.0062, segs=16):
    prof = [(r, -BOLT_SINK), (r, 0.0012), (r * 0.86, 0.0034), (r * 0.55, 0.0052),
            (r * 0.18, h)]
    return add_lathe(bm, prof, segs, mat_idx, center=center, rot=frame(axis, X if abs(
        Vector(axis).x) < 0.9 else Y), solid=True)


def add_hex(bm, center, axis, a, b, r, mat_idx):
    prof = [(r, a), (r, b - 0.001), (r * 0.82, b)]
    return add_lathe(bm, prof, 6, mat_idx, center=center, rot=frame(axis, Y), phase=math.pi / 6,
                     solid=True)


def add_rod(bm, center, axis, a, b, r, mat_idx, segs=12):
    return add_lathe(bm, [(r, a), (r, b)], segs, mat_idx, center=center,
                     rot=frame(axis, Y), solid=True)


def build_barrier(bm, n_corner, bevel_verts, flags):
    parts = []   # (faces, tone)

    def keep(verts, tone):
        parts.append((faces_of(verts), tone))

    for sgn in (-1.0, 1.0):
        for back in (False, True):
            dx = (-sgn * SKEW_LEG) if (flags["skew_leg"] and sgn > 0 and not back) else 0.0
            E, T, d, n_out, padc = leg_line(sgn, back, dx)
            rot = frame(d, X)
            ln = (T - E).length
            keep(add_rbox(bm, LEG_HALF, LEG_HALF, LEG_RC,
                          [(0.0015, 0.0), (0.0, 0.0015), (0.0, ln - 0.0015), (0.0015, ln)],
                          E, rot, STEEL_IDX, n_corner), 0.4 + 0.1 * sgn + (0.1 if back else 0.0))
            keep(add_rbox(bm, LEG_HALF + 0.0016, LEG_HALF + 0.0016, 0.0045,
                          [(0.0, 0.0), (0.0, 0.011), (0.003, 0.0145), (0.0075, 0.0165)],
                          T - d * 0.012, rot, PLASTIC_IDX, n_corner), 0.5)
            # the pad stays under the design foot; --skew-leg moves the leg alone
            _E, _T, _d, _n, padc0 = leg_line(sgn, back)
            keep(add_rbox(bm, PAD_HX, PAD_HY, 0.012,
                          [(0.003, 0.0), (0.0, 0.003), (0.0, PAD_T - 0.004), (0.004, PAD_T)],
                          (padc0.x, padc0.y, SLAB_T - SEAT), Matrix.Identity(3), RUBBER_IDX,
                          n_corner), 0.4 if back else 0.6)

        # hinge: washer between the pair, a pivot bolt with a head outside and a nut inside
        xst = BAR_X + sgn * LEG_X
        ph = Vector((xst, BAR_Y, SLAB_T + HINGE_Z))
        ax = X * sgn
        reach = LEG_SPLIT + LEG_HALF
        keep(add_lathe(bm, [(0.0125, -0.002), (0.0125, 0.002)], 20, STEEL_IDX, center=ph,
                       rot=frame(ax, Y), solid=True), 0.5)
        keep(add_rod(bm, ph, ax, -(reach + 0.0068), reach + 0.0066, 0.006, STEEL_IDX), 0.5)
        keep(add_hex(bm, ph, ax, reach - 0.0006, reach + 0.0072, 0.0115, STEEL_IDX), 0.5)
        keep(add_hex(bm, ph, -ax, reach - 0.0006, reach + 0.0072, 0.0105, STEEL_IDX), 0.5)

        # spreader strap on the inner side, pinned to the front leg and, through a
        # spacer, to the back leg
        zs = SLAB_T + STRAP_Z
        x_front = xst - sgn * LEG_SPLIT
        x_back = xst + sgn * LEG_SPLIT
        x_strap = x_front - sgn * (LEG_HALF + STRAP_GAP + STRAP_T / 2)
        yf, yb = leg_y(False, zs), leg_y(True, zs)
        outline = lug_outline([(yf, zs, STRAP_W / 2), (yb, zs, STRAP_W / 2)])
        srot = Matrix(((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
        sv = add_prism(bm, outline, -STRAP_T / 2, STRAP_T / 2, (x_strap, 0.0, 0.0), srot,
                       STEEL_IDX)
        bevel_verts.extend(sv)
        keep(sv, 0.5)
        x_in = x_strap - sgn * STRAP_T / 2
        for yy, xl, spacer in ((yf, x_front, False), (yb, x_back, True)):
            p0 = Vector((x_in, yy, zs))
            far = abs((xl + sgn * LEG_HALF) - x_in)
            keep(add_rod(bm, p0, ax, -0.003, far + 0.0052, 0.005, STEEL_IDX), 0.5)
            keep(add_dome(bm, p0, -ax, STEEL_IDX, r=0.0095, h=0.0046, segs=16), 0.5)
            keep(add_hex(bm, Vector((xl + sgn * LEG_HALF, yy, zs)), ax, -0.0006, 0.0040,
                         0.0085, STEEL_IDX), 0.5)
            if spacer:
                s0 = x_strap + sgn * (STRAP_T / 2 - 0.0005)
                s1 = x_back - sgn * (LEG_HALF - 0.0005)
                keep(add_rod(bm, Vector((s0, yy, zs)), ax, 0.0, abs(s1 - s0), 0.0085,
                             STEEL_IDX, segs=16), 0.5)

    # boards: two on each face, bolted to the legs of that face
    lamp_board = None
    for back in (False, True):
        _E, _T, d, n_out, _p = leg_line(1.0, back)
        for bi, zb in enumerate(BOARD_Z):
            G = Vector((BAR_X, BAR_Y + (FOOT_Y if back else -FOOT_Y), SLAB_T))
            A = G + d * ((SLAB_T + zb - G.z) / d.z)
            gap = GAP_BOARD if (flags["gap_board"] and not back and bi == 1) else 0.0
            C = A + n_out * (LEG_HALF - BOARD_BITE + BOARD_T / 2 + gap)
            M = Matrix((X, d, n_out)).transposed().to_4x4()
            M.translation = C
            bb = board_bm(n_corner, 0.2 + 0.2 * bi + (0.4 if back else 0.0))
            merge_bm(bm, bb, M)
            bb.free()
            ux = LEG_X + (LEG_SPLIT if back else -LEG_SPLIT)
            for su in (-1.0, 1.0):
                for sv_ in (-1.0, 1.0):
                    p = C + X * (su * ux) + d * (sv_ * BOLT_V) + n_out * (BOARD_T / 2)
                    keep(add_dome(bm, p, n_out, STEEL_IDX), 0.5)
            if not back and bi == 0:
                lamp_board = (C, d, n_out)

    # warning lamp: a bracket bolted to the top front board, a battery box, a
    # drum housing with a fresnel lens and bezel on each face
    C, d, n_out = lamp_board
    # --loose-lamp pulls the lamp level off the board, so the envelope's top
    # (the housing) does not move
    level = Vector((0.0, n_out.y, 0.0)).normalized()
    shift = level * (LOOSE_LAMP if flags["loose_lamp"] else 0.0)
    xl = BAR_X - LEG_X + LAMP_DX
    f_top = C + d * (BOARD_H / 2) + n_out * (BOARD_T / 2) + X * (xl - BAR_X) + shift
    off = n_out * (BR_T / 2 - BR_BITE)
    q0 = f_top + off - d * 0.090
    q1 = f_top + off + d * 0.006
    q2 = q1 + Z * 0.035
    q3 = q2 + Z * 0.045
    keep(add_bar(bm, [q0, q1, q2, q3], X, BR_HALF_W, BR_T / 2, 0.001, STEEL_IDX, fillet=0.012),
         0.5)
    # two bolts 40 mm apart on one bracket: the second sits 0.3 mm deeper, or
    # their base caps share a plane
    for s, deep in ((0.070, 0.0), (0.030, 0.0003)):
        keep(add_dome(bm, f_top + n_out * (BR_T - BR_BITE - deep) - d * s, n_out, STEEL_IDX,
                      r=0.008, h=0.0042, segs=12), 0.5)
    z_box = q3.z - 0.020
    keep(add_rbox(bm, 0.075, 0.042, 0.010,
                  [(0.003, 0.0), (0.0, 0.003), (0.0, BOX_H - 0.004), (0.004, BOX_H)],
                  (xl, q3.y, z_box), Matrix.Identity(3), PLASTIC_IDX, n_corner), 0.5)
    hc = Vector((xl, q3.y, z_box + BOX_H + HOUSING_R - 0.012))
    keep(add_lathe(bm, [(0.080, -0.036), (0.094, -0.034), (0.098, -0.029), (0.098, 0.029),
                        (0.094, 0.034), (0.080, 0.036)], 32, PLASTIC_IDX, center=hc,
                   rot=frame(Y, X), solid=True), 0.5)
    lens = [(0.082, 0.0348), (0.082, 0.0400), (0.068, 0.0465), (0.068, 0.0450), (0.052, 0.0505),
            (0.052, 0.0490), (0.034, 0.0535), (0.034, 0.0520), (0.012, 0.0555), (0.004, 0.0558)]
    bezel = [(0.080, 0.0340), (0.090, 0.0340), (0.090, 0.0395), (0.086, 0.0432), (0.080, 0.0432)]
    for ax in (-Y, Y):
        keep(add_lathe(bm, lens, 32, LENS_IDX, center=hc, rot=frame(ax, X), solid=True), 0.5)
        f = revolve(bm, bezel, 32, PLASTIC_IDX, m4(frame(ax, X), hc))
        parts.append((set(f), 0.5))

    for faces, tone in parts:
        _tone(bm, [f for f in faces if f.is_valid], tone)


def build_mesh(name, n_corner, bevel_segments, flags):
    bm = bmesh.new()
    try:
        bm.faces.layers.float.new(TONE)
        bevel_verts = []
        build_slab(bm)
        build_cones(bm, flags)
        build_barrier(bm, n_corner, bevel_verts, flags)
        # chamfer the straps' rims (prisms), material= set, over sorted edges
        bm.edges.index_update()
        edges = sorted(
            {e for v in bevel_verts if v.is_valid for e in v.link_edges
             if len(e.link_faces) == 2
             and all(f.material_index == STEEL_IDX for f in e.link_faces)
             and e.calc_face_angle() > math.radians(60.0)},
            key=lambda e: e.index,
        )
        if edges:
            bmesh.ops.bevel(bm, geom=edges, offset=0.0008, segments=bevel_segments,
                            profile=0.5, affect="EDGES", clamp_overlap=True, material=STEEL_IDX)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # Lathed and moulded bodies are smooth-shaded; chamfers, stripes and
        # material boundaries stay crisp.
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
    nt.links.new(fac_socket, mx.inputs[0])
    for i, c in ((1, c1), (2, c2)):
        if isinstance(c, tuple):
            mx.inputs[i].default_value = c
        else:
            nt.links.new(c, mx.inputs[i])
    return mx.outputs[0]


def _gray(v):
    return (v, v, v, 1.0)


def weathered(name, col_a, col_b, rough, dirt_col, dirt_top, dirt_amt, scuff_col, scuff_amt,
              scuff_scale=38.0, metallic=0.0, rough_var=0.08, bump=0.0, bump_scale=600.0,
              coat=0.0, rub=0.0, rub_col=(0.030, 0.027, 0.025, 1.0)):
    """A designed surface: a per-part tone between two colours (the PartTone
    face attribute), grime rising from the slab to ``dirt_top``, sparse
    scuffs, ``rub``: level black tyre and boot rubs (a noise squashed flat,
    so each mark runs round the part, not up it), roughness breakup and an
    optional fine bump."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = metallic
    if coat > 0.0 and "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    coord = nt.nodes.new("ShaderNodeTexCoord")
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = TONE
    tone = _mix(nt, attr.outputs["Fac"], col_a, col_b)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs[0])
    hmap = _node(nt, "ShaderNodeMapRange")
    hmap.inputs["From Min"].default_value = SLAB_T
    hmap.inputs["From Max"].default_value = SLAB_T + dirt_top
    hmap.inputs["To Min"].default_value = dirt_amt
    hmap.inputs["To Max"].default_value = 0.0
    nt.links.new(sep.outputs["Z"], hmap.inputs["Value"])
    dn = _node(nt, "ShaderNodeTexNoise", Scale=4.0, Detail=6.0)
    nt.links.new(coord.outputs["Object"], dn.inputs["Vector"])
    dr = _ramp(nt, 0.35, _gray(0.25), 0.70, _gray(1.0))
    nt.links.new(dn.outputs["Fac"], dr.inputs["Fac"])
    dm = nt.nodes.new("ShaderNodeMath")
    dm.operation = "MULTIPLY"
    nt.links.new(hmap.outputs["Result"], dm.inputs[0])
    nt.links.new(dr.outputs["Color"], dm.inputs[1])
    grime = _mix(nt, dm.outputs["Value"], tone, dirt_col)
    sn = _node(nt, "ShaderNodeTexNoise", Scale=scuff_scale, Detail=10.0)
    nt.links.new(coord.outputs["Object"], sn.inputs["Vector"])
    sr = _ramp(nt, 0.60, _gray(0.0), 0.70, _gray(scuff_amt))
    nt.links.new(sn.outputs["Fac"], sr.inputs["Fac"])
    col = _mix(nt, sr.outputs["Color"], grime, scuff_col)
    if rub > 0.0:
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1.0, 1.0, 16.0)
        nt.links.new(coord.outputs["Object"], mp.inputs["Vector"])
        rn = _node(nt, "ShaderNodeTexNoise", Scale=3.2, Detail=6.0, Roughness=0.62)
        nt.links.new(mp.outputs["Vector"], rn.inputs["Vector"])
        rk = _ramp(nt, 0.635, _gray(0.0), 0.700, _gray(rub))
        nt.links.new(rn.outputs["Fac"], rk.inputs["Fac"])
        col = _mix(nt, rk.outputs["Color"], col, rub_col)
    nt.links.new(col, bsdf.inputs["Base Color"])
    rr = _ramp(nt, 0.30, _gray(max(0.03, rough - rough_var)), 0.70,
               _gray(min(0.95, rough + rough_var)))
    nt.links.new(dn.outputs["Fac"], rr.inputs["Fac"])
    radd = nt.nodes.new("ShaderNodeMath")
    radd.operation = "ADD"
    radd.use_clamp = True
    nt.links.new(rr.outputs["Color"], radd.inputs[0])
    nt.links.new(dm.outputs["Value"], radd.inputs[1])
    nt.links.new(radd.outputs["Value"], bsdf.inputs["Roughness"])
    if bump > 0.0:
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = bump_scale
        nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
        bp = _node(nt, "ShaderNodeBump", Strength=bump)
        bp.inputs["Distance"].default_value = 0.0005
        nt.links.new(vor.outputs["Distance"], bp.inputs["Height"])
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


def asphalt_material():
    """Dense asphalt: a dark binder with light aggregate showing through, a
    few large darker oil stains that are also glossier, and the aggregate
    again as a bump."""
    mat = bpy.data.materials.new("Asphalt")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 140.0
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    agg = _ramp(nt, 0.0, (0.150, 0.144, 0.136, 1.0), 0.30, (0.030, 0.029, 0.028, 1.0))
    nt.links.new(vor.outputs["Distance"], agg.inputs["Fac"])
    stones = nt.nodes.new("ShaderNodeTexVoronoi")
    stones.inputs["Scale"].default_value = 60.0
    nt.links.new(coord.outputs["Object"], stones.inputs["Vector"])
    coarse = _ramp(nt, 0.0, (0.125, 0.118, 0.108, 1.0), 0.22, (0.030, 0.029, 0.028, 1.0))
    nt.links.new(stones.outputs["Distance"], coarse.inputs["Fac"])
    light = nt.nodes.new("ShaderNodeMixRGB")
    light.blend_type = "LIGHTEN"
    light.inputs[0].default_value = 1.0
    nt.links.new(agg.outputs["Color"], light.inputs[1])
    nt.links.new(coarse.outputs["Color"], light.inputs[2])
    big = _node(nt, "ShaderNodeTexNoise", Scale=1.3, Detail=4.0)
    nt.links.new(coord.outputs["Object"], big.inputs["Vector"])
    stain = _ramp(nt, 0.38, _gray(0.55), 0.62, _gray(1.0))
    nt.links.new(big.outputs["Fac"], stain.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(light.outputs[0], mul.inputs[1])
    nt.links.new(stain.outputs["Color"], mul.inputs[2])
    nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
    rr = _ramp(nt, 0.38, _gray(0.62), 0.62, _gray(0.92))
    nt.links.new(big.outputs["Fac"], rr.inputs["Fac"])
    nt.links.new(rr.outputs["Color"], bsdf.inputs["Roughness"])
    hsum = nt.nodes.new("ShaderNodeMath")
    hsum.operation = "ADD"
    nt.links.new(vor.outputs["Distance"], hsum.inputs[0])
    nt.links.new(stones.outputs["Distance"], hsum.inputs[1])
    bp = _node(nt, "ShaderNodeBump", Strength=0.40)
    bp.inputs["Distance"].default_value = 0.002
    nt.links.new(hsum.outputs["Value"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def road_paint_material():
    """Road paint worn through to the binder where a noise mask says so."""
    mat = bpy.data.materials.new("RoadPaint")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.72
    coord = nt.nodes.new("ShaderNodeTexCoord")
    wear = _node(nt, "ShaderNodeTexNoise", Scale=13.0, Detail=9.0)
    nt.links.new(coord.outputs["Object"], wear.inputs["Vector"])
    ramp = _ramp(nt, 0.30, (0.050, 0.048, 0.046, 1.0), 0.40, (0.62, 0.61, 0.57, 1.0))
    nt.links.new(wear.outputs["Fac"], ramp.inputs["Fac"])
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 140.0
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    speck = _ramp(nt, 0.0, _gray(0.72), 0.25, _gray(1.0))
    nt.links.new(vor.outputs["Distance"], speck.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(ramp.outputs["Color"], mul.inputs[1])
    nt.links.new(speck.outputs["Color"], mul.inputs[2])
    nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
    bp = _node(nt, "ShaderNodeBump", Strength=0.25)
    bp.inputs["Distance"].default_value = 0.0015
    nt.links.new(vor.outputs["Distance"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def principled(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def _emission(bsdf, color, strength):
    for key in ("Emission Color", "Emission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = color
            break
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = strength


def set_materials():
    """Slot order: cone PVC, reflective sheeting, rubber, asphalt, road
    paint, tar, orange sheeting, board plastic, galvanised steel, black
    plastic, amber lens. Shared by the check and the render."""
    cone = weathered("ConePVC", (0.90, 0.19, 0.012, 1.0), (0.74, 0.20, 0.040, 1.0), 0.46,
                     (0.13, 0.085, 0.050, 1.0), 0.26, 0.85, (0.30, 0.10, 0.04, 1.0), 0.55,
                     scuff_scale=26.0, coat=0.15, rub=0.92)
    reflect = weathered("ReflectiveWhite", (0.78, 0.78, 0.76, 1.0), (0.66, 0.66, 0.63, 1.0), 0.30,
                        (0.36, 0.32, 0.26, 1.0), 0.40, 0.60, (0.50, 0.50, 0.49, 1.0), 0.65,
                        scuff_scale=70.0, bump=0.12, bump_scale=900.0, rub=0.6,
                        rub_col=(0.10, 0.095, 0.088, 1.0))
    rubber = weathered("RubberBase", (0.036, 0.035, 0.034, 1.0), (0.050, 0.048, 0.045, 1.0), 0.78,
                       (0.17, 0.155, 0.14, 1.0), 0.03, 0.55, (0.10, 0.098, 0.095, 1.0), 0.8,
                       scuff_scale=20.0, bump=0.25, bump_scale=400.0)
    asphalt = asphalt_material()
    paint = road_paint_material()
    tar = weathered("CrackSeal", (0.016, 0.015, 0.014, 1.0), (0.022, 0.020, 0.018, 1.0), 0.32,
                    (0.05, 0.048, 0.045, 1.0), 0.01, 0.4, (0.06, 0.058, 0.055, 1.0), 0.5)
    sheeting = weathered("OrangeSheeting", (0.86, 0.23, 0.020, 1.0), (0.78, 0.25, 0.045, 1.0),
                         0.30, (0.24, 0.13, 0.07, 1.0), 0.70, 0.50, (0.55, 0.30, 0.16, 1.0),
                         0.55, scuff_scale=70.0, bump=0.12, bump_scale=900.0)
    board = weathered("BoardPlastic", (0.66, 0.65, 0.61, 1.0), (0.60, 0.59, 0.55, 1.0), 0.50,
                      (0.30, 0.26, 0.21, 1.0), 0.80, 0.5, (0.45, 0.44, 0.41, 1.0), 0.5,
                      scuff_scale=60.0)
    steel = weathered("GalvanisedSteel", (0.56, 0.57, 0.58, 1.0), (0.48, 0.49, 0.50, 1.0), 0.42,
                      (0.22, 0.19, 0.15, 1.0), 0.35, 0.7, (0.32, 0.28, 0.23, 1.0), 0.5,
                      metallic=1.0, rough_var=0.12, scuff_scale=18.0)
    add_studio(steel, (0.55, 0.57, 0.60, 1.0), 0.55,
               [(0.0, 0.02), (0.30, 0.05), (0.42, 0.45), (0.50, 1.0), (0.62, 0.30), (1.0, 0.12)])
    plastic = weathered("BlackPlastic", (0.030, 0.030, 0.032, 1.0), (0.040, 0.040, 0.042, 1.0),
                        0.42, (0.16, 0.15, 0.13, 1.0), 0.05, 0.3, (0.12, 0.12, 0.12, 1.0), 0.6)
    lens = principled("AmberLens", (0.80, 0.26, 0.010, 1.0), 0.0, 0.10)
    lb = lens.node_tree.nodes["Principled BSDF"]
    if "Coat Weight" in lb.inputs:
        lb.inputs["Coat Weight"].default_value = 1.0
    _emission(lb, (1.0, 0.36, 0.02, 1.0), 0.55)
    return cone, reflect, rubber, asphalt, paint, tar, sheeting, board, steel, plastic, lens


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
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.centre = (self.lo + self.hi) * 0.5
        self.mean = sum(pts, Vector()) / len(pts)
        mats = {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        self.mats = set(mats)
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)
        self.polys = polys


def pca_axis(pts, largest=True):
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    _w, vecs = np.linalg.eigh(q.T @ q)
    axis = vecs[:, -1] if largest else vecs[:, 0]
    if axis[2] < 0.0:
        axis = -axis
    return Vector(c), Vector(axis)


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    slabs = [s for s in parts if s.mat == ASPHALT_IDX]
    out["slab"] = max(slabs, key=lambda s: len(s.verts)) if slabs else None
    out["slab_top"] = out["slab"].hi.z if out["slab"] else 0.0
    bodies = [s for s in parts if s.mat == CONE_IDX and max(s.size) > 0.5]
    for b in bodies:
        b.axis_c, b.axis = pca_axis(b.pts)
        b.tilt = math.degrees(math.acos(min(1.0, abs(b.axis.z))))
    out["bodies"] = bodies
    rubber = [s for s in parts if s.mat == RUBBER_IDX]
    out["bases"] = [s for s in rubber if max(s.size) > 0.30]
    out["pads"] = [s for s in rubber if 0.06 < max(s.size) < 0.25]
    out["bands"] = [s for s in parts if s.mats == {REFLECT_IDX}]
    out["boards"] = [s for s in parts if BOARD_IDX in s.mats]
    out["legs"] = [s for s in parts if s.mat == STEEL_IDX and s.size.z > 0.8]
    return out


def support_audit(cls):
    """Every standing base, the stack's bottom base, the fallen cone's base
    and body and every barricade pad bear into the slab in a band."""
    top = cls["slab_top"]
    sup = []
    for b in cls["bases"]:
        if b.lo.z < top + 0.012:
            sup.append(("base", top - b.lo.z))
    for b in cls["bodies"]:
        if b.tilt > 45.0:
            sup.append(("fallen body", top - b.lo.z))
    for p in cls["pads"]:
        sup.append(("pad", top - p.lo.z))
    return sup


def board_audit(cls):
    """Each board's back face against the front face of every leg it is
    bolted to: planes read off the faces, compared along the board normal."""
    res = []
    for bd in cls["boards"]:
        c, n = pca_axis(bd.pts, largest=False)
        for leg in cls["legs"]:
            _lc, ld = pca_axis(leg.pts)
            if abs(ld.dot(n)) > 0.02:
                continue
            if leg.hi.x < bd.lo.x or leg.lo.x > bd.hi.x:
                continue
            dist = (c - leg.mean).dot(n)
            if abs(dist) > 0.06:
                continue
            n_out = n if dist > 0.0 else -n
            bvs = [p for p in bd.polys if Vector(p.normal).dot(-n_out) > 0.999]
            lvs = [p for p in leg.polys if Vector(p.normal).dot(n_out) > 0.999]
            if not bvs or not lvs:
                res.append(-1.0)
                continue
            me_pts = bd.pts
            remap_b = {vi: k for k, vi in enumerate(bd.verts)}
            remap_l = {vi: k for k, vi in enumerate(leg.verts)}
            db = [me_pts[remap_b[v]].dot(n_out) for p in bvs for v in p.vertices]
            dl = [leg.pts[remap_l[v]].dot(n_out) for p in lvs for v in p.vertices]
            res.append(sum(dl) / len(dl) - sum(db) / len(db))
    return res


def host_radius(body, p):
    """The host body's outer surface at the vertex's own station and angle:
    a ray from outside toward the axis, along the vertex's radial."""
    c, a = body.axis_c, body.axis
    rel = p - c
    s = rel.dot(a)
    q = rel - a * s
    rho = q.length
    if rho < 1e-6:
        return None, rho
    u = q / rho
    origin = c + a * s + u * (rho + 0.03)
    hit, _n, _i, _d = body.tree.ray_cast(origin, -u, 0.08)
    if hit is None:
        return None, rho
    return (hit - (c + a * s)).length, rho


def band_audit(cls):
    """Per band: the host is the coaxial body whose outer wall is nearest the
    band; per angular segment, the innermost vertex's seat depth and the
    outermost's stand-off."""
    seats, prouds, orphans = [], [], 0
    for band in cls["bands"]:
        best, best_d = None, 9.0
        for b in cls["bodies"]:
            rel = band.mean - b.axis_c
            if (rel - b.axis * rel.dot(b.axis)).length > 0.01:
                continue
            hr, rho = host_radius(b, band.pts[0])
            if hr is None:
                continue
            if abs(rho - hr) < best_d:
                best, best_d = b, abs(rho - hr)
        if best is None:
            orphans += 1
            continue
        bins = {}
        for p in band.pts:
            hr, rho = host_radius(best, p)
            if hr is None:
                orphans += 1
                continue
            rel = p - best.axis_c
            q = rel - best.axis * rel.dot(best.axis)
            ref = Vector((1.0, 0.0, 0.0)) if abs(best.axis.x) < 0.9 else Vector((0.0, 1.0, 0.0))
            e1 = (ref - best.axis * ref.dot(best.axis)).normalized()
            e2 = best.axis.cross(e1)
            ang = math.atan2(q.dot(e2), q.dot(e1))
            key = round(ang / (2.0 * math.pi / BODY_SEGS)) % BODY_SEGS
            lo_d, hi_d = bins.get(key, (9.0, -9.0))
            d = rho - hr
            bins[key] = (min(lo_d, d), max(hi_d, d))
        for lo_d, hi_d in bins.values():
            seats.append(-lo_d)
            prouds.append(hi_d)
    return seats, prouds, orphans


def base_under(cls, body):
    """The base bonded to a body: the rubber shell on its axis whose bottom is
    just under the body's (in a stack, the bases of the cones above are also
    under the body's middle, so compare bottoms)."""
    a = body.axis
    body_bot = min(p.dot(a) for p in body.pts)
    best, best_d = None, 9.0
    for b in cls["bases"]:
        rel = b.mean - body.axis_c
        off = (rel - a * rel.dot(a)).length
        if off > 0.03:
            continue
        dz = body_bot - min(p.dot(a) for p in b.pts)
        if 0.0 < dz < best_d:
            best, best_d = b, dz
    return best


def across_flats(pts, cx, cy):
    p = np.array([(v.x - cx, v.y - cy) for v in pts])
    th = np.radians(np.arange(0.0, 90.0, 0.02))
    dirs = np.stack([np.cos(th), np.sin(th)], axis=1)
    h = (p @ dirs.T).max(axis=0)
    h2 = (-(p @ dirs.T)).max(axis=0)
    return float((h + h2).min())


def plumb_audit(cls):
    res = []
    for b in cls["bodies"]:
        if b.tilt > 45.0:
            continue
        zs = [p.z for p in b.pts]
        z0, z1 = min(zs), max(zs)
        lo = [p for p in b.pts if p.z < z0 + 0.03]
        hi = [p for p in b.pts if p.z > z1 - 0.03]
        cl = sum(lo, Vector()) / len(lo)
        ch = sum(hi, Vector()) / len(hi)
        tilt = math.degrees(math.atan2(math.hypot(ch.x - cl.x, ch.y - cl.y), ch.z - cl.z))
        base = base_under(cls, b)
        h = (z1 - base.lo.z) if base else 0.0
        w = across_flats(base.pts, b.axis_c.x, b.axis_c.y) if base else 0.0
        res.append((tilt, h, w))
    return res


def mirror_audit(cls):
    boards = cls["boards"]
    if not boards:
        return 9.0, 0
    xm = sum(0.5 * (b.lo.x + b.hi.x) for b in boards) / len(boards)
    legs = cls["legs"]
    left = [l for l in legs if l.centre.x < xm]
    right = [l for l in legs if l.centre.x > xm]
    worst = 0.0
    if len(left) != len(right):
        return 9.0, len(legs)
    for L in left:
        R = min(right, key=lambda r: abs(r.centre.y - L.centre.y))
        worst = max(worst, abs((xm - L.lo.x) - (R.hi.x - xm)), abs((xm - L.hi.x) - (R.lo.x - xm)),
                    abs(L.lo.y - R.lo.y), abs(L.hi.y - R.hi.y), abs(L.lo.z - R.lo.z),
                    abs(L.hi.z - R.hi.z))
    return worst, len(legs)


def stack_audit(cls):
    """Coaxial plumb bodies form stacks; for each pair, the pitch between
    body bottoms and the upper's inner wall against the lower's outer wall,
    by rays at stations along the overlap."""
    plumb = [b for b in cls["bodies"] if b.tilt < 45.0]
    stacks = []
    used = set()
    for b in plumb:
        if b.idx in used:
            continue
        grp = [c for c in plumb if math.hypot(c.axis_c.x - b.axis_c.x, c.axis_c.y - b.axis_c.y) < 0.01]
        for c in grp:
            used.add(c.idx)
        if len(grp) > 1:
            stacks.append(sorted(grp, key=lambda s: s.lo.z))
    pairs = []
    for st in stacks:
        for lo_b, up_b in zip(st, st[1:]):
            pitch = up_b.lo.z - lo_b.lo.z
            ax, ay = lo_b.axis_c.x, lo_b.axis_c.y
            bites = []
            z = up_b.lo.z + 0.06
            while z < lo_b.hi.z - 0.05:
                for k in range(16):
                    a = 2.0 * math.pi * (k + 0.25) / 16
                    d = Vector((math.cos(a), math.sin(a), 0.0))
                    o = Vector((ax, ay, z))
                    h_up = up_b.tree.ray_cast(o, d, 0.5)[0]
                    h_lo = lo_b.tree.ray_cast(o + d * 0.4, -d, 0.5)[0]
                    if h_up is None or h_lo is None:
                        bites.append(-1.0)
                        continue
                    r_up = math.hypot(h_up.x - ax, h_up.y - ay)
                    r_lo = math.hypot(h_lo.x - ax, h_lo.y - ay)
                    bites.append(r_lo - r_up)
                z += 0.04
            pairs.append((pitch, min(bites) if bites else -1.0, max(bites) if bites else -1.0))
    return stacks, pairs


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
    img = bpy.data.images.new("ConesNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = BOARD_IDX
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
    low = build_mesh("ConesLow", n_corner=1, bevel_segments=1, flags=flags)
    high = build_mesh("ConesHigh", n_corner=3, bevel_segments=3, flags=flags)
    mats = set_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the board plastic: the boards' edges are where the
    # high mesh's rounded corners differ from the low mesh's chamfers.
    target = mats[BOARD_IDX]

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
    zf = zfight_pairs(low.data, cls["groups"])
    sup = support_audit(cls)
    brd = board_audit(cls)
    seats, prouds, orphans = band_audit(cls)
    plumb = plumb_audit(cls)
    mirror, nlegs = mirror_audit(cls)
    stacks, pairs = stack_audit(cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("mesh has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "ConesLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "ConesLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(low, "ConesCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_traffic_cones_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    sinks = [s for _l, s in sup]
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
    print(f"measured shells={len(cls['all'])} slab_top={cls['slab_top']:.5f} "
          f"supports={len(sup)} {[(l, round(s * 1000, 3)) for l, s in sup]}")
    print(f"measured boards={len(cls['boards'])} board_bites_mm={[round(b * 1000, 3) for b in brd]}")
    if seats:
        print(f"measured bands={len(cls['bands'])} seat_mm=({min(seats) * 1000:.3f},"
              f"{max(seats) * 1000:.3f}) proud_min_mm={min(prouds) * 1000:.3f} orphans={orphans}")
    print(f"measured plumb={[(round(t, 4), round(h, 5), round(w, 5)) for t, h, w in plumb]}")
    print(f"measured legs={nlegs} mirror_mm={mirror * 1000:.4f}")
    print(f"measured stacks={[len(s) for s in stacks]} pairs="
          f"{[(round(p, 5), round(a * 1000, 3), round(b * 1000, 3)) for p, a, b in pairs]}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")

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
    if len(sup) != SUPPORT_COUNT or any(not (SINK_MIN <= s <= SINK_MAX) for s in sinks):
        return (fail(f"supports: {len(sup)} (want {SUPPORT_COUNT}), sink into the slab "
                     f"{[(l, round(s * 1000, 3)) for l, s in sup]} mm (band "
                     f"[{SINK_MIN * 1000}, {SINK_MAX * 1000}])", 16),) + none3
    if (len(cls["boards"]) != BOARD_COUNT or len(brd) != BOARD_LEG_JOINTS
            or any(not (BOARD_BITE_MIN <= b <= BOARD_BITE_MAX) for b in brd)):
        return (fail(f"boards into legs: {len(cls['boards'])} boards, {len(brd)} joints "
                     f"{[round(b * 1000, 3) for b in brd]} mm (band [{BOARD_BITE_MIN * 1000}, "
                     f"{BOARD_BITE_MAX * 1000}])", 17),) + none3
    if (len(cls["bands"]) != BANDS or orphans or not seats
            or min(seats) < BAND_SEAT_MIN or max(seats) > BAND_SEAT_MAX
            or min(prouds) < BAND_PROUD_MIN):
        return (fail(f"band seat: {len(cls['bands'])} bands, orphans {orphans}, seat "
                     f"{min(seats) * 1000 if seats else 0:.3f}..{max(seats) * 1000 if seats else 0:.3f} mm "
                     f"(band [{BAND_SEAT_MIN * 1000}, {BAND_SEAT_MAX * 1000}]), proud min "
                     f"{min(prouds) * 1000 if prouds else 0:.3f} mm", 18),) + none3
    if (len(plumb) != PLUMB_CONES or any(t > PLUMB_MAX_DEG or abs(h - CONE_H) > CONE_H_TOL
                                         or abs(w - BASE_W) > BASE_W_TOL for t, h, w in plumb)
            or nlegs != LEGS or mirror > MIRROR_EPS):
        return (fail(f"plumb/size/mirror: {[(round(t, 3), round(h, 4), round(w, 4)) for t, h, w in plumb]}"
                     f", legs {nlegs}, mirror {mirror * 1000:.3f} mm", 19),) + none3
    if (len(stacks) != 1 or len(stacks[0]) != STACK_N
            or any(not (PITCH_MIN <= p <= PITCH_MAX) or a < NEST_MIN or b > NEST_MAX
                   for p, a, b in pairs)):
        return (fail(f"nesting: stacks {[len(s) for s in stacks]}, pairs "
                     f"{[(round(p, 4), round(a * 1000, 3), round(b * 1000, 3)) for p, a, b in pairs]}"
                     f" (pitch [{PITCH_MIN}, {PITCH_MAX}], bite [{NEST_MIN * 1000}, "
                     f"{NEST_MAX * 1000}] mm)", 20),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 21),) + none3
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
    # behind to lift the cones and the barricade off the wall, and the warm
    # wedge pooled on the back wall.
    light("Key", (-3.6, -4.6, 4.4), 205.0, 3.0, (1.0, 0.95, 0.90), spread=32.0)
    light("Fill", (5.0, -3.4, 1.2), 26.0, 7.0, (0.72, 0.82, 1.0))
    light("Rim", (-1.4, 3.0, 3.0), 170.0, 2.5, (0.62, 0.78, 1.0))
    light("Wedge", (3.4, 2.4, 2.6), 330.0, 4.0, (1.0, 0.68, 0.38),
          target=(centre.x + 2.6, WALL_Y, 0.4))

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
    # Standard, not AgX: AgX washes the fluorescent orange toward pastel
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 22
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
    p.add_argument("--float-cone", action="store_true")
    p.add_argument("--gap-board", action="store_true")
    p.add_argument("--float-band", action="store_true")
    p.add_argument("--lean-cone", action="store_true")
    p.add_argument("--skew-leg", action="store_true")
    p.add_argument("--loose-stack", action="store_true")
    p.add_argument("--loose-lamp", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_cone=args.float_cone,
        gap_board=args.gap_board,
        float_band=args.float_band,
        lean_cone=args.lean_cone,
        skew_leg=args.skew_leg,
        loose_stack=args.loose_stack,
        loose_lamp=args.loose_lamp,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("traffic-cones OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
