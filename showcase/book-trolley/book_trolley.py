"""Game-ready library book trolley — a showcase piece, not an example.

Asserts budget conformance of a procedural double-sided library book
truck: two arched end panels standing in skids on four swivel casters, a
flat bottom deck, and on each side two sloped troughs — a shelf tilted
back and a backrest square to it, both housed in the end panels — under a
turned push rail. The troughs are filled with rounded-spine hardbacks,
spines out; loose books lie in two stacks on the deck. Every book is a
cloth or leather cover, a page block glued into it and two gilt bands
round the spine. Carried through UVs, seven materials (wood, cloth,
leather, paper, gilt, iron, rubber), a high-to-low normal bake, an LOD
chain, a convex collider, and a Unity glTF export.

The budget that matters is the one a sloped shelf adds: a book in a trough
is carried at two places, its tail on the shelf and its fore-edge against
the backrest. A book seated on the shelf and standing off the backrest
passes every seat, the bounding box, the triangle count and the overlap
budget (which must exempt both designed contacts) — and on a real trolley
it would topple forward. The piece reads each backrest's face plane off
the finished mesh and asserts how deep every trough book's fore-edge sits
in it, as a band, beside the shelf seat.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-caster`` the named wheels,
``--short-shelves`` the dado bite, ``--loose-pages`` the page-block bite,
``--float-books`` the book seat, ``--float-bands`` the band seat,
``--drop-plates`` the caster plate seat, ``--skew-caster`` mirror
symmetry, ``--uniform-books`` the size spread, ``--off-back`` and
``--deep-back`` the backrest contact, ``--crowd-books`` book
interpenetration, ``--sharp-deck`` edge treatment.

No randomness: every book's size, tint, gap, yaw and seat is a table
entry or a closed-form term of its index. DECIMATE COLLAPSE triangle
counts are not byte-identical across Blender versions — the LOD gate is a
ratio band.

    blender --background --python book_trolley.py --
    blender --background --python book_trolley.py -- --off-back
    blender --background --python book_trolley.py -- --output book-trolley.png
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

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

# The carcass. X along the trolley, Y front (-) to back (+), Z up. Two end
# panels carry everything; every cross member is housed into both of them.
L_OUT = 0.720
END_T = 0.022
END_HALF = 0.250
END_Z0 = 0.115
END_SHOULDER = 0.930
END_TOP = 1.000
END_ARC = 16
SKID_HALF = 0.265
SKID_W = 0.070
SKID_Z0 = 0.092
SKID_Z1 = 0.127
DADO = 0.008
DECK_Z = 0.175
DECK_T = 0.020
DECK_HALF = 0.235
CHAMFER = 0.0025

# The troughs. Each is a shelf tilted TILT back toward the centre and a
# backrest square to it, meeting at a corner CORNER_Y off the centre line.
# In a trough's own frame s runs downhill into the backrest, t up the
# shelf normal; the corner is s = t = 0, the backrest's face s = 0 and the
# shelf's top t = 0.
TILT = math.radians(14.0)
CORNER_Y = 0.068
TIER_Z = (0.360, 0.680)
SHELF_T = 0.018
SHELF_D = 0.170
SHELF_TAIL = 0.006
BACK_T = 0.018
BACK_H = 0.170
BACK_SEAT = 0.006
RAIL_R = 0.016
RAIL_Z = 0.962
RAIL_BITE = 0.012
RAIL_SEG = 16

# Swivel casters, one under each end of each skid, rolling along X.
CASTER_Y = 0.225
WHEEL_R = 0.035
WHEEL_W = 0.024
WHEEL_SEG = 24
WHEEL_ROUND = 0.004
AXLE_R = 0.005
AXLE_HALF = 0.022
FORK_WO = 0.019
FORK_WI = 0.015
FORK_ZB = 0.024
FORK_ZI = 0.074
FORK_ZT = 0.082
FORK_D = 0.030
RACE_R = 0.021
RACE_Z0 = 0.081
RACE_Z1 = 0.090
RACE_SEG = 16
PLATE = 0.056
PLATE_T = 0.004
PLATE_BITE = 0.001
DROP_PLATES = 0.0025
IRON_CHAMFER = 0.0008
FLOAT_CASTER = 0.005
SKEW_CASTER = 0.006

# Books. Local frame: X across the thickness, Y from the spine (-) to the
# fore-edge (+), Z up the height, bottom of the cover at 0 (copied from
# showcase/bookshelf).
COVER_B = 0.0028
SQUARE = 0.004
PAGE_BACK = 0.0015
PAGE_BITE = 0.0006
LOOSE_PAGES = 0.0009
SPINE_ARC = 6
COVER_CHAMFER = 0.0008
BAND_OFF = 0.018
BAND_H = 0.006
BAND_BITE = 0.0003
BAND_PROUD = 0.0008
FLOAT_BAND = 0.0011
SEAT_BASE = 0.0010
SEAT_STEP = 0.00018
FLOAT_BOOKS = 0.006
START_GAP = 0.006
GAP_BASE = 0.0025
GAP_SPAN = 0.0020
CROWD_GAP = -0.0060
BACK_BITE = 0.0008
OFF_BACK = -0.0030
DEEP_BACK = 0.0045
FIT_CLEAR = 0.004
STACK_YAW = math.radians(3.0)
STACK_SHIFT = 0.006
STACK_Y = -0.080
STACK_STEP_Y = 0.004
UNIFORM_BOOK = (0.034, 0.215, 0.158)
UNIFORM_JIT = 0.03
UPRIGHT_YAW = (-2.4, -0.8, 0.8, 2.4)

# Per trough, left to right: (kind, T, H, D) or ("gap", width). Troughs
# are (side, tier): side 0 front, 1 back; tier 0 lower, 1 upper.
TROUGHS = (
    ((0, 1), (
        ("c", 0.032, 0.228, 0.165), ("l", 0.045, 0.242, 0.178), ("c", 0.026, 0.205, 0.150),
        ("c", 0.038, 0.236, 0.172), ("l", 0.052, 0.245, 0.184), ("c", 0.029, 0.198, 0.146),
        ("c", 0.041, 0.221, 0.163), ("l", 0.035, 0.232, 0.170), ("c", 0.048, 0.240, 0.176),
        ("c", 0.024, 0.186, 0.137), ("l", 0.037, 0.214, 0.158), ("c", 0.043, 0.226, 0.166),
        ("c", 0.030, 0.203, 0.149),
    )),
    ((0, 0), (
        ("l", 0.050, 0.244, 0.186), ("c", 0.034, 0.225, 0.166), ("c", 0.027, 0.210, 0.154),
        ("l", 0.044, 0.238, 0.176), ("c", 0.036, 0.218, 0.160), ("c", 0.020, 0.192, 0.141),
        ("l", 0.055, 0.243, 0.188), ("gap", 0.030), ("c", 0.031, 0.207, 0.152),
        ("c", 0.040, 0.231, 0.170), ("l", 0.028, 0.199, 0.146), ("c", 0.046, 0.236, 0.174),
        ("c", 0.033, 0.212, 0.156), ("l", 0.039, 0.228, 0.168),
    )),
    ((1, 1), (
        ("c", 0.036, 0.230, 0.168), ("l", 0.042, 0.240, 0.176), ("c", 0.028, 0.206, 0.151),
        ("c", 0.047, 0.235, 0.172), ("l", 0.031, 0.215, 0.158), ("c", 0.039, 0.224, 0.165),
        ("gap", 0.060), ("c", 0.025, 0.195, 0.143), ("l", 0.049, 0.244, 0.182),
        ("c", 0.034, 0.219, 0.161), ("c", 0.040, 0.227, 0.167),
    )),
    ((1, 0), (
        ("l", 0.046, 0.241, 0.180), ("c", 0.030, 0.214, 0.157), ("c", 0.037, 0.226, 0.166),
        ("l", 0.026, 0.201, 0.148), ("c", 0.051, 0.239, 0.178), ("c", 0.033, 0.217, 0.159),
        ("l", 0.040, 0.231, 0.170), ("c", 0.023, 0.188, 0.139), ("c", 0.044, 0.233, 0.172),
        ("gap", 0.040), ("l", 0.035, 0.222, 0.163), ("c", 0.029, 0.209, 0.153),
    )),
)
CROWD_TROUGH = (0, 1)
# Loose books on the deck: (x centre, [(kind, T, H, D), ...] bottom first).
STACKS = (
    (-0.160, (("l", 0.042, 0.232, 0.172), ("c", 0.034, 0.214, 0.158),
              ("c", 0.026, 0.180, 0.132))),
    (0.160, (("c", 0.048, 0.238, 0.176), ("l", 0.030, 0.150, 0.112))),
)
CLOTH_TINTS = ((0.22, 0.035, 0.030), (0.045, 0.095, 0.055), (0.035, 0.050, 0.115),
               (0.33, 0.21, 0.075), (0.10, 0.105, 0.11), (0.12, 0.045, 0.085),
               (0.30, 0.21, 0.13), (0.045, 0.095, 0.095))
LEATHER_TINTS = ((0.17, 0.070, 0.030), (0.26, 0.12, 0.050), (0.085, 0.040, 0.020),
                 (0.21, 0.055, 0.030))

BBOX_TOL = 0.020
OUTER_SIZE = (0.768, 0.530, 1.000)

BASE_TRIS_MIN = 16800
BASE_TRIS_MAX = 18600
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 7
FACE_FLOORS = {0: 510, 1: 2500, 2: 1320, 3: 280, 4: 2430, 5: 840, 6: 590}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 360
BAKE_RES = 1024
CAGE_EXTRUSION = 0.003
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
WHEEL_Z_MAX = 1e-4
DADO_MIN = 0.005
DADO_FAR_MIN = 0.006
PAGE_BITE_MIN = 0.0003
PAGE_BITE_MAX = 0.0012
SEAT_MIN = 0.0005
SEAT_MAX = 0.0036
BAND_BITE_MIN = 0.0001
BAND_BITE_MAX = 0.0008
BAND_PROUD_MIN = 0.0004
PLATE_SEAT_MIN = 0.0005
PLATE_SEAT_MAX = 0.0020
MIRROR_EPS = 1e-4
THICK_SPREAD_MIN = 2.5
HEIGHT_SPREAD_MIN = 1.5
UPRIGHT_TILT_MAX = math.radians(3.0)
LYING_TILT_MIN = math.radians(80.0)
BACK_MIN = 0.0003
BACK_MAX = 0.0020
SUPPORT_REACH = 0.02
RIGHT_ANGLE_TOL = math.radians(5.0)

WOOD_IDX = 0
CLOTH_IDX = 1
LEATHER_IDX = 2
PAPER_IDX = 3
GILT_IDX = 4
IRON_IDX = 5
RUBBER_IDX = 6
BOOK_MATS = (CLOTH_IDX, LEATHER_IDX, PAPER_IDX, GILT_IDX)
N_TROUGH = len(TROUGHS)
N_CROSS = 1 + 2 * N_TROUGH + 1
N_CASTERS = 4
N_UP = sum(1 for _k, row in TROUGHS for it in row if it[0] != "gap")
N_LYING = sum(len(books) for _x, books in STACKS)
N_BOOKS = N_UP + N_LYING


def eevee_engine_id():
    """EEVEE id: 'BLENDER_EEVEE' on 5.0+, 'BLENDER_EEVEE_NEXT' on 4.2-4.5."""
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def fail(msg, code):
    print(f"FAIL[{code}]: {msg}", file=sys.stderr)
    return code


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def evaluated_triangle_count(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    mesh = ev.to_mesh()
    try:
        mesh.calc_loop_triangles()
        return len(mesh.loop_triangles)
    finally:
        ev.to_mesh_clear()


def frac(x):
    return x - math.floor(x)


# --- one book, in its own frame (copied from showcase/bookshelf) -------------


def spine_chain(t, d):
    """Centre line of the cover's U and its outward normal at each point."""
    rc = t / 2.0 - COVER_B / 2.0
    yc = -d / 2.0 + t / 2.0
    pts = [(Vector((-rc, d / 2.0)), Vector((-1.0, 0.0)))]
    for k in range(SPINE_ARC + 1):
        phi = math.pi + math.pi * k / SPINE_ARC
        n = Vector((math.cos(phi), math.sin(phi)))
        pts.append((Vector((0.0, yc)) + n * rc, n))
    pts.append((Vector((rc, d / 2.0)), Vector((1.0, 0.0))))
    return pts, yc


def book_local(t, h, d, loose_pages=False, float_bands=False):
    """A hardback in its own frame: cover, page block and two gilt bands.

    Returns (verts, faces) with each face as (vertex indices, kind), kind
    0 cover, 1 pages, 2 band.
    """
    chain, yc = spine_chain(t, d)
    bm = bmesh.new()
    try:
        kind = bm.faces.layers.int.new("kind")
        outer = [p + n * (COVER_B / 2.0) for p, n in chain]
        inner = [p - n * (COVER_B / 2.0) for p, n in chain]

        def ring(pts2, z):
            return [bm.verts.new((p.x, p.y, z)) for p in pts2]

        ob, ot = ring(outer, 0.0), ring(outer, h)
        ib, it = ring(inner, 0.0), ring(inner, h)
        m = len(chain)
        for i in range(m - 1):
            j = i + 1
            bm.faces.new((ob[i], ob[j], ot[j], ot[i]))
            bm.faces.new((ib[j], ib[i], it[i], it[j]))
            bm.faces.new((ot[i], ot[j], it[j], it[i]))
            bm.faces.new((ob[j], ob[i], ib[i], ib[j]))
        bm.faces.new((ob[0], ot[0], it[0], ib[0]))
        e = m - 1
        bm.faces.new((ib[e], it[e], ot[e], ob[e]))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.edges.index_update()
        edges = sorted((ed for ed in bm.edges if ed.calc_face_angle(0.0) > math.radians(40.0)),
                       key=lambda ed: ed.index)
        bmesh.ops.bevel(bm, geom=edges, offset=COVER_CHAMFER, segments=1, profile=0.5,
                        affect="EDGES", clamp_overlap=True)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])

        px = t / 2.0 - COVER_B + (-LOOSE_PAGES if loose_pages else PAGE_BITE)
        lo = Vector((-px, yc + PAGE_BACK, SQUARE))
        hi = Vector((px, d / 2.0 - SQUARE, h - SQUARE))
        corner = {}
        for a in (0, 1):
            for b in (0, 1):
                for c in (0, 1):
                    corner[(a, b, c)] = bm.verts.new((hi.x if a else lo.x, hi.y if b else lo.y,
                                                      hi.z if c else lo.z))
        box = (((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)),
               ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),
               ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)),
               ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)),
               ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)),
               ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)))
        for quad in box:
            f = bm.faces.new([corner[q] for q in quad])
            f[kind] = 1

        span = range(1, SPINE_ARC + 2)
        inner_off = FLOAT_BAND if float_bands else -BAND_BITE
        outer_off = inner_off + BAND_BITE + BAND_PROUD
        for z0 in (BAND_OFF, h - BAND_OFF - BAND_H):
            g = {}
            for j in span:
                p, n = chain[j]
                for side, off in (("in", inner_off), ("out", outer_off)):
                    q = p + n * (COVER_B / 2.0 + off)
                    for zz, z in (("b", z0), ("t", z0 + BAND_H)):
                        g[(j, side, zz)] = bm.verts.new((q.x, q.y, z))
            quads = []
            for j in list(span)[:-1]:
                k = j + 1
                quads.append((g[(j, "out", "b")], g[(k, "out", "b")], g[(k, "out", "t")],
                              g[(j, "out", "t")]))
                quads.append((g[(k, "in", "b")], g[(j, "in", "b")], g[(j, "in", "t")],
                              g[(k, "in", "t")]))
                quads.append((g[(j, "out", "t")], g[(k, "out", "t")], g[(k, "in", "t")],
                              g[(j, "in", "t")]))
                quads.append((g[(k, "out", "b")], g[(j, "out", "b")], g[(j, "in", "b")],
                              g[(k, "in", "b")]))
            a, z = span[0], span[-1]
            quads.append((g[(a, "in", "b")], g[(a, "out", "b")], g[(a, "out", "t")],
                          g[(a, "in", "t")]))
            quads.append((g[(z, "out", "b")], g[(z, "in", "b")], g[(z, "in", "t")],
                          g[(z, "out", "t")]))
            for vs in quads:
                f = bm.faces.new(vs)
                f[kind] = 2
        bm.verts.index_update()
        verts = [v.co.copy() for v in bm.verts]
        faces = [(tuple(v.index for v in f.verts), f[kind]) for f in bm.faces]
    finally:
        bm.free()
    return verts, faces


# --- the layout -------------------------------------------------------------


def cover_points(book):
    return [book["world"][i] for i in book["cover_ix"]]


def bounds(pts):
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def move(book, delta):
    book["M"] = Matrix.Translation(delta) @ book["M"]
    book["world"] = [p + delta for p in book["world"]]


def make_book(dims, rot, loose_pages, float_bands):
    kind, t, h, d = dims
    verts, faces = book_local(t, h, d, loose_pages=loose_pages, float_bands=float_bands)
    cover_ix = sorted({i for vs, k in faces if k == 0 for i in vs})
    return {"t": t, "h": h, "d": d, "kind": kind, "verts": verts, "faces": faces,
            "cover_ix": cover_ix, "M": rot.copy(), "world": [rot @ v for v in verts]}


def trough_frame(side, tier):
    """Corner, downhill direction (into the backrest) and shelf normal of a trough."""
    sy = -1.0 if side == 0 else 1.0
    c = Vector((0.0, sy * CORNER_Y, TIER_Z[tier]))
    u = Vector((0.0, -sy * math.cos(TILT), -math.sin(TILT)))
    n = Vector((0.0, -sy * math.sin(TILT), math.cos(TILT)))
    return c, u, n


def plan_books(loose_pages=False, float_books=False, float_bands=False, uniform_books=False,
               crowd_books=False, off_back=False, deep_back=False):
    """Place every book. Closed-form: sizes from the tables, the rest from the index.

    A trough book is built in its own frame, turned into the trough (its
    height up the shelf normal, its fore-edge downhill) and yawed a degree
    or so about the shelf normal. It is then slid up the normal until its
    lowest cover vertex sits a stepped seat into the shelf, down the slope
    until its deepest vertex sits the back bite into the backrest, and
    along the trough to the running cursor.
    """
    x_in = L_OUT / 2.0 - END_T
    bite = BACK_BITE
    if off_back:
        bite = OFF_BACK
    if deep_back:
        bite = DEEP_BACK
    lift = FLOAT_BOOKS if float_books else 0.0
    books = []

    def sized(dims, n):
        kind, t, h, d = dims
        if uniform_books:
            ft = 1.0 + UNIFORM_JIT * (frac(n * 0.6180339887 + 0.1) - 0.5)
            t, h, d = UNIFORM_BOOK[0] * ft, UNIFORM_BOOK[1], UNIFORM_BOOK[2]
        return (kind, t, h, d)

    for (side, tier), row in TROUGHS:
        c, u, n = trough_frame(side, tier)
        xs = Vector((1.0, 0.0, 0.0)) if side == 0 else Vector((-1.0, 0.0, 0.0))
        basis = Matrix((xs, u, n)).transposed().to_4x4()
        cursor = -x_in + START_GAP
        k = 0
        for item in row:
            if item[0] == "gap":
                cursor += item[1]
                continue
            yaw = math.radians(UPRIGHT_YAW[k % len(UPRIGHT_YAW)])
            rot = Matrix.Rotation(yaw, 4, n) @ basis
            b = make_book(sized(item, len(books)), rot, loose_pages, float_bands)
            if crowd_books and (side, tier) == CROWD_TROUGH:
                gap = CROWD_GAP
            else:
                gap = GAP_BASE + GAP_SPAN * frac(k * 0.6180339887 + 0.3 + (2 * side + tier) * 0.17)
            pts = cover_points(b)
            t_min = min((p - c).dot(n) for p in pts)
            s_max = max((p - c).dot(u) for p in pts)
            lo_x = min(p.x for p in pts)
            seat = SEAT_BASE + SEAT_STEP * k
            move(b, n * (lift - seat - t_min) + u * (bite - s_max)
                 + Vector((cursor + gap - lo_x, 0.0, 0.0)))
            hi_x = bounds(cover_points(b))[1].x
            if hi_x > x_in - FIT_CLEAR:
                raise ValueError(f"trough {(side, tier)} overflows: book {k} ends at {hi_x:.4f}")
            b.update({"trough": (side, tier), "i": len(books)})
            books.append(b)
            cursor = hi_x
            k += 1

    deck_top = DECK_Z + DECK_T
    for si, (xc, stack) in enumerate(STACKS):
        top = deck_top + lift
        for j, dims in enumerate(stack):
            yaw = STACK_YAW * (1.0 if j % 2 else -1.0)
            rot = Matrix.Rotation(yaw, 4, "Z") @ Matrix.Rotation(-math.pi / 2.0, 4, "Y")
            b = make_book(sized(dims, len(books)), rot, loose_pages, float_bands)
            lo, hi = bounds(cover_points(b))
            shift = STACK_SHIFT * (0.5 - frac(j * 0.7548776662 + 0.2 + si * 0.31)) * 2.0
            # A book on a book takes a small seat of its own (1.0-1.4 mm), so
            # its underside never lands on the plane of the page block 2.2 mm
            # inside the board below it.
            seat = SEAT_BASE + SEAT_STEP * (j if j else 3 + 2 * si)
            move(b, Vector((xc + shift - (lo.x + hi.x) / 2.0,
                            STACK_Y + STACK_STEP_Y * j - (lo.y + hi.y) / 2.0,
                            top - seat - lo.z)))
            top = bounds(cover_points(b))[1].z
            b.update({"trough": None, "i": len(books)})
            books.append(b)
    return books


# --- construction -----------------------------------------------------------

BOX_FACES = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))


def add_frame_box(bm, origin, axes, lo, hi, mat):
    """Box spanning ``lo``..``hi`` in the frame (origin, axes); returns its verts."""
    vs = []
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                p = (origin + axes[0] * (hi[0] if a else lo[0]) + axes[1] * (hi[1] if b else lo[1])
                     + axes[2] * (hi[2] if c else lo[2]))
                vs.append(bm.verts.new(p))
    faces = [bm.faces.new([vs[i] for i in q]) for q in BOX_FACES]
    for f in faces:
        f.material_index = mat
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return vs


def add_box(bm, lo, hi, mat):
    return add_frame_box(bm, Vector(), (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))),
                         lo, hi, mat)


def add_prism(bm, profile, w0, w1, to3d, mat):
    """Extrude a closed 2D profile between stations w0 and w1; n-gon caps."""
    lo = [bm.verts.new(to3d(a, b, w0)) for a, b in profile]
    hi = [bm.verts.new(to3d(a, b, w1)) for a, b in profile]
    faces = [bm.faces.new(list(reversed(lo))), bm.faces.new(hi)]
    m = len(profile)
    for i in range(m):
        j = (i + 1) % m
        faces.append(bm.faces.new((lo[i], lo[j], hi[j], hi[i])))
    for f in faces:
        f.material_index = mat
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return lo + hi


def circle(r, segs, phase=0.0):
    return [(r * math.cos(phase + 2.0 * math.pi * k / segs),
             r * math.sin(phase + 2.0 * math.pi * k / segs)) for k in range(segs)]


def end_profile():
    """End panel outline in (y, z): straight sides, an arched top."""
    a = END_TOP - END_SHOULDER
    r = (END_HALF ** 2 + a * a) / (2.0 * a)
    zc = END_TOP - r
    phi0 = math.atan2(END_SHOULDER - zc, END_HALF)
    pts = [(-END_HALF, END_Z0), (END_HALF, END_Z0)]
    for k in range(END_ARC + 1):
        phi = phi0 + (math.pi - 2.0 * phi0) * k / END_ARC
        pts.append((r * math.cos(phi), zc + r * math.sin(phi)))
    return pts


def add_caster(bm, cx, cy, dz, drop_plate, groups):
    """Plate, swivel race, fork, axle and wheel, stacked under a skid end."""
    iron, rubber = groups["iron"], groups["rubber"]
    pz0 = SKID_Z0 + PLATE_BITE - PLATE_T - (DROP_PLATES if drop_plate else 0.0)
    iron.extend(add_box(bm, (cx - PLATE / 2, cy - PLATE / 2, pz0 + dz),
                        (cx + PLATE / 2, cy + PLATE / 2, pz0 + PLATE_T + dz), IRON_IDX))
    iron.extend(add_prism(bm, circle(RACE_R, RACE_SEG), RACE_Z0 + dz, RACE_Z1 + dz,
                          lambda a, b, w: Vector((cx + a, cy + b, w)), IRON_IDX))
    fork = ((-FORK_WO, FORK_ZB), (-FORK_WI, FORK_ZB), (-FORK_WI, FORK_ZI), (FORK_WI, FORK_ZI),
            (FORK_WI, FORK_ZB), (FORK_WO, FORK_ZB), (FORK_WO, FORK_ZT), (-FORK_WO, FORK_ZT))
    iron.extend(add_prism(bm, fork, cx - FORK_D / 2, cx + FORK_D / 2,
                          lambda a, b, w: Vector((w, cy + a, b + dz)), IRON_IDX))
    iron.extend(add_prism(bm, circle(AXLE_R, 12), cy - AXLE_HALF, cy + AXLE_HALF,
                          lambda a, b, w: Vector((cx + a, w, WHEEL_R + b + dz)), IRON_IDX))
    rubber.extend(add_prism(bm, circle(WHEEL_R, WHEEL_SEG, -math.pi / 2.0),
                            cy - WHEEL_W / 2, cy + WHEEL_W / 2,
                            lambda a, b, w: Vector((cx + a, w, WHEEL_R + b + dz)), RUBBER_IDX))


def bevel_group(bm, verts, offset, segments, mat, min_angle):
    """Chamfer every edge of ``verts``' shells sharper than ``min_angle``."""
    # A set of BMEdges iterates in address order: sort by index so the bevel
    # emits its faces in the same order on every run.
    bm.edges.index_update()
    live = [v for v in verts if v.is_valid]
    edges = sorted({e for v in live for e in v.link_edges
                    if e.calc_face_angle(0.0) > min_angle}, key=lambda e: e.index)
    bmesh.ops.bevel(bm, geom=edges, offset=offset, segments=segments, profile=0.5,
                    affect="EDGES", clamp_overlap=True, material=mat)


def build_trolley_mesh(
    name,
    stray_vert=False,
    float_caster=False,
    short_shelves=False,
    sharp_deck=False,
    drop_plates=False,
    skew_caster=False,
    with_books=True,
    **book_flags,
):
    x_out = L_OUT / 2.0
    x_in = x_out - END_T
    x_mid = x_out - END_T / 2.0
    X = Vector((1.0, 0.0, 0.0))
    bm = bmesh.new()
    try:
        uv = bm.loops.layers.uv.new("UVMap")
        piece = bm.faces.layers.int.new("Piece")
        wood, sharp = [], []
        groups = {"iron": [], "rubber": []}
        # End panels, each standing in its skid.
        prof = end_profile()
        for sx in (-1.0, 1.0):
            a, b = sorted((sx * x_in, sx * x_out))
            wood.extend(add_prism(bm, prof, a, b, lambda y, z, w: Vector((w, y, z)), WOOD_IDX))
            wood.extend(add_box(bm, (sx * x_mid - SKID_W / 2, -SKID_HALF, SKID_Z0),
                                (sx * x_mid + SKID_W / 2, SKID_HALF, SKID_Z1), WOOD_IDX))
        # Deck, housed in both ends.
        # --sharp-deck leaves it square: one member, centred, so the mirror
        # budget cannot see it and only the edge budget can.
        deck = add_box(bm, (-(x_in + DADO), -DECK_HALF, DECK_Z),
                       (x_in + DADO, DECK_HALF, DECK_Z + DECK_T), WOOD_IDX)
        (sharp if sharp_deck else wood).extend(deck)
        # Troughs: a tilted shelf and a backrest square to it, both housed.
        reach = x_in - 0.004 if short_shelves else x_in + DADO
        for (side, tier), _row in TROUGHS:
            c, u, n = trough_frame(side, tier)
            axes = (X, u, n)
            wood.extend(add_frame_box(bm, c, axes, (-reach, -SHELF_D, -SHELF_T),
                                      (reach, BACK_T + SHELF_TAIL, 0.0), WOOD_IDX))
            wood.extend(add_frame_box(bm, c, axes, (-(x_in + DADO), 0.0, -BACK_SEAT),
                                      (x_in + DADO, BACK_T, BACK_H), WOOD_IDX))
        # Push rail along the ridge, its ends blind in both panels.
        rail = circle(RAIL_R, RAIL_SEG)
        wood.extend(add_prism(bm, rail, -(x_in + RAIL_BITE), x_in + RAIL_BITE,
                              lambda y, z, w: Vector((w, y, RAIL_Z + z)), WOOD_IDX))
        # Casters.
        k = 0
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                dz = FLOAT_CASTER if (float_caster and k == 0) else 0.0
                dx = SKEW_CASTER if (skew_caster and k == 3) else 0.0
                add_caster(bm, sx * x_mid + dx, sy * CASTER_Y, dz, drop_plates, groups)
                k += 1
        bevel_group(bm, wood, CHAMFER, 1, WOOD_IDX, math.radians(30.0))
        bevel_group(bm, groups["iron"], IRON_CHAMFER, 1, IRON_IDX, math.radians(30.0))
        bevel_group(bm, groups["rubber"], WHEEL_ROUND, 2, RUBBER_IDX, math.radians(30.0))
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])

        books = plan_books(**book_flags) if with_books else []
        for b in books:
            vs = [bm.verts.new(p) for p in b["world"]]
            cover = LEATHER_IDX if b["kind"] == "l" else CLOTH_IDX
            for idx, kind in b["faces"]:
                f = bm.faces.new([vs[i] for i in idx])
                f.material_index = (cover, PAPER_IDX, GILT_IDX)[kind]
                f[piece] = b["i"] + 1
        if stray_vert:
            bm.verts.new((0.0, 0.0, DECK_Z + DECK_T / 2.0))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(35.0):
                e.smooth = False
        pack_uvs(bm, uv)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    paint_pieces(me, books)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def pack_uvs(bm, uv, margin=0.06):
    """One grid cell per face, projected on its dominant axis."""
    faces = list(bm.faces)
    cols = max(1, math.ceil(math.sqrt(len(faces))))
    rows = max(1, math.ceil(len(faces) / cols))
    cw, ch = 1.0 / cols, 1.0 / rows
    pu, pv = margin * cw * 0.5, margin * ch * 0.5
    for idx, face in enumerate(faces):
        nrm = face.normal
        ax, ay, az = abs(nrm.x), abs(nrm.y), abs(nrm.z)
        pts = []
        for loop in face.loops:
            co = loop.vert.co
            if az >= ax and az >= ay:
                pts.append((co.x, co.y))
            elif ax >= ay:
                pts.append((co.y, co.z))
            else:
                pts.append((co.x, co.z))
        minx, maxx = min(c[0] for c in pts), max(c[0] for c in pts)
        miny, maxy = min(c[1] for c in pts), max(c[1] for c in pts)
        dx, dy = max(maxx - minx, 1e-8), max(maxy - miny, 1e-8)
        ou, ov = (idx % cols) * cw + pu, (idx // cols) * ch + pv
        for loop, (x, y) in zip(face.loops, pts):
            loop[uv].uv = (ou + (x - minx) / dx * (cw - 2 * pu),
                           ov + (y - miny) / dy * (ch - 2 * pv))


def paint_pieces(me, books):
    """Face attributes the shaders read: per-board tone and grain, per-book tint."""
    npoly = len(me.polygons)
    piece = [0] * npoly
    me.attributes["Piece"].data.foreach_get("value", piece)
    mats = [0] * npoly
    me.polygons.foreach_get("material_index", mats)
    tone = [0.5] * npoly
    grain = [(1.0, 0.0, 0.0)] * npoly
    tint = [(0.5, 0.5, 0.5, 1.0)] * npoly
    vf = [[] for _ in range(len(me.vertices))]
    for p in me.polygons:
        for i in p.vertices:
            vf[i].append(p.index)
    for k, g in enumerate(shells(me)):
        faces = {fi for i in g for fi in vf[i]}
        if not faces or mats[next(iter(faces))] not in (WOOD_IDX, IRON_IDX):
            continue
        pts = [me.vertices[i].co for i in g]
        ext = [max(p[a] for p in pts) - min(p[a] for p in pts) for a in range(3)]
        axis = ext.index(max(ext))
        d = tuple(1.0 if a == axis else 0.0 for a in range(3))
        t = 0.5 + 0.30 * (frac(k * 0.6180339887 + 0.3) - 0.5)
        for fi in faces:
            tone[fi] = t
            grain[fi] = d
    for fi in range(npoly):
        v = piece[fi] - 1
        if v < 0:
            continue
        b = books[v]
        if mats[fi] == LEATHER_IDX:
            c = LEATHER_TINTS[int(frac(v * 0.6180339887 + 0.1) * len(LEATHER_TINTS))]
        else:
            c = CLOTH_TINTS[int(frac(v * 0.6180339887 + 0.4) * len(CLOTH_TINTS))]
        tint[fi] = (c[0], c[1], c[2], 1.0)
        tone[fi] = 0.5 + 0.3 * (frac(v * 0.4142135624) - 0.5)
        ax = b["M"].to_3x3() @ Vector((1.0, 0.0, 0.0))
        grain[fi] = tuple(ax.normalized())
    me.attributes.remove(me.attributes["Piece"])
    a = me.attributes.new("PlankTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)
    b = me.attributes.new("GrainDir", "FLOAT_VECTOR", "FACE")
    b.data.foreach_set("vector", [c for v in grain for c in v])
    c = me.attributes.new("Tint", "FLOAT_COLOR", "FACE")
    c.data.foreach_set("color", [x for v in tint for x in v])


# --- surface ----------------------------------------------------------------


def _sock(sockets, identifier):
    return next(sk for sk in sockets if sk.identifier == identifier)


def wood_material(name):
    """Stained oak: grain along each board, tone per board (copied from showcase/bookshelf)."""
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
    squash = nt.nodes.new("ShaderNodeMath")
    squash.operation = "MULTIPLY"
    squash.inputs[1].default_value = 0.94
    nt.links.new(dot.outputs["Value"], squash.inputs[0])
    along = nt.nodes.new("ShaderNodeVectorMath")
    along.operation = "SCALE"
    nt.links.new(gdir.outputs["Vector"], along.inputs[0])
    nt.links.new(squash.outputs["Value"], along.inputs["Scale"])
    grain_co = nt.nodes.new("ShaderNodeVectorMath")
    grain_co.operation = "SUBTRACT"
    nt.links.new(coord.outputs["Object"], grain_co.inputs[0])
    nt.links.new(along.outputs["Vector"], grain_co.inputs[1])
    shift = nt.nodes.new("ShaderNodeVectorMath")
    shift.operation = "ADD"
    nt.links.new(grain_co.outputs["Vector"], shift.inputs[0])
    nt.links.new(tone.outputs["Fac"], shift.inputs[1])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 34.0
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.62
    nt.links.new(shift.outputs["Vector"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.085, 0.044, 0.019, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.25, 0.135, 0.060, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 1.2
    gain.inputs[2].default_value = 0.40
    nt.links.new(tone.outputs["Fac"], gain.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(ramp.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(gain.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.62
    rough.inputs["To Max"].default_value = 0.44
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def cover_material(name, scale, low, roughness):
    """A book cover: the per-book ``Tint``, broken up by a fine noise."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Tint"
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    shade = nt.nodes.new("ShaderNodeMapRange")
    shade.inputs["To Min"].default_value = low
    shade.inputs["To Max"].default_value = 1.1
    nt.links.new(noise.outputs["Fac"], shade.inputs["Value"])
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "SCALE"
    nt.links.new(attr.outputs["Color"], mul.inputs[0])
    nt.links.new(shade.outputs["Result"], mul.inputs["Scale"])
    nt.links.new(mul.outputs["Vector"], bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = roughness + 0.08
    rough.inputs["To Max"].default_value = roughness - 0.08
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def paper_material(name):
    """Page edges: warm off-white with fine lines parallel to the boards."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    gdir = nt.nodes.new("ShaderNodeAttribute")
    gdir.attribute_name = "GrainDir"
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(tc.outputs["Object"], dot.inputs[0])
    nt.links.new(gdir.outputs["Vector"], dot.inputs[1])
    across = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(dot.outputs["Value"], across.inputs["X"])
    lines = nt.nodes.new("ShaderNodeTexNoise")
    lines.inputs["Scale"].default_value = 900.0
    lines.inputs["Detail"].default_value = 2.0
    nt.links.new(across.outputs["Vector"], lines.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.40, 0.34, 0.24, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.68, 0.61, 0.47, 1.0)
    nt.links.new(lines.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    return mat


def gilt_material(name):
    """Gold leaf tooling: warm, half metallic, a little worn by the noise."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 300.0
    noise.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.36, 0.23, 0.07, 1.0)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (0.80, 0.56, 0.20, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.55
    bsdf.inputs["Roughness"].default_value = 0.45
    return mat


def iron_material(name):
    """Caster iron: near-black, rough, a little rust in the noise. Not chrome."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 160.0
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.40
    ramp.color_ramp.elements[0].color = (0.035, 0.034, 0.033, 1.0)
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = (0.080, 0.050, 0.034, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.52
    rough.inputs["To Max"].default_value = 0.78
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    bsdf.inputs["Metallic"].default_value = 0.7
    return mat


def rubber_material(name):
    """Solid rubber tyres: charcoal, matte."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.028, 0.027, 0.026, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.78
    return mat


def trolley_materials():
    return (
        wood_material("TrolleyWood"),
        cover_material("BookCloth", 420.0, 0.78, 0.86),
        cover_material("BookLeather", 70.0, 0.62, 0.48),
        paper_material("BookPages"),
        gilt_material("BookGilt"),
        iron_material("CasterIron"),
        rubber_material("CasterRubber"),
    )


def assign_slots(obj, mats):
    slots = obj.data.materials
    for i, mat in enumerate(mats):
        if i < len(slots):
            slots[i] = mat
        else:
            slots.append(mat)


# --- measurement ------------------------------------------------------------


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs, ys, zs = [c.x for c in corners], [c.y for c in corners], [c.z for c in corners]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def uv_stats(mesh):
    uv = mesh.uv_layers.active
    if uv is None:
        return 0.0, 0.0, 1.0, 1.0, 0.0, 0
    data = uv.data
    us = [loop.uv[0] for loop in data]
    vs = [loop.uv[1] for loop in data]
    aabbs = []
    for poly in mesh.polygons:
        pu = [data[i].uv[0] for i in poly.loop_indices]
        pv = [data[i].uv[1] for i in poly.loop_indices]
        aabbs.append((min(pu), min(pv), max(pu), max(pv)))
    span = max(1e-6, max(a[2] - a[0] for a in aabbs), max(a[3] - a[1] for a in aabbs))
    buckets = {}
    for i, a in enumerate(aabbs):
        for c in range(int(a[0] // span), int(a[2] // span) + 1):
            for r in range(int(a[1] // span), int(a[3] // span) + 1):
                buckets.setdefault((c, r), []).append(i)
    overlap = 0.0
    seen = set()
    for members in buckets.values():
        for ii in range(len(members)):
            for jj in range(ii + 1, len(members)):
                i, j = members[ii], members[jj]
                key = (i, j) if i < j else (j, i)
                if key in seen:
                    continue
                seen.add(key)
                a, b = aabbs[i], aabbs[j]
                overlap += max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
                    0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return min(us), min(vs), max(us), max(vs), overlap, len(aabbs)


def face_area(me, poly):
    idxs = poly.vertices
    v0 = me.vertices[idxs[0]].co
    area = 0.0
    for i in range(1, len(idxs) - 1):
        area += (me.vertices[idxs[i]].co - v0).cross(me.vertices[idxs[i + 1]].co - v0).length * 0.5
    return area


def hygiene_audit(me):
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
    return {"ngons": ngons, "loose_v": loose_v, "loose_e": loose_e,
            "nonman": nonman, "zero_area": zero_area, "doubles": doubles}


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


def zfight_pairs(me):
    """Coplanar face pairs from *different shells* (copied from showcase/grindstone)."""
    owner = {}
    for si, g in enumerate(shells(me)):
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


def right_angle_edges(me):
    """Manifold edges between two wood faces that meet within 5 degrees of 90."""
    count = 0
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        for e in bm.edges:
            if len(e.link_faces) != 2:
                continue
            if any(f.material_index != WOOD_IDX for f in e.link_faces):
                continue
            if abs(e.calc_face_angle(0.0) - math.pi / 2.0) <= RIGHT_ANGLE_TOL:
                count += 1
    finally:
        bm.free()
    return count


def mirror_error(me):
    """Worst distance from a non-book vertex's X and Y mirror images to the mesh."""
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    pts = [me.vertices[i].co.copy() for i in range(len(me.vertices))
           if mats.get(i, -1) not in BOOK_MATS]
    if not pts:
        return 99.0
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    worst = 0.0
    for p in pts:
        for q in (Vector((-p.x, p.y, p.z)), Vector((p.x, -p.y, p.z))):
            worst = max(worst, kd.find(q)[2])
    return worst


def shell_tree(me, groups):
    member = set(i for g in groups for i in g)
    order = sorted(member)
    remap = {v: k for k, v in enumerate(order)}
    polys = [[remap[i] for i in p.vertices] for p in me.polygons if p.vertices[0] in member]
    return BVHTree.FromPolygons([me.vertices[i].co.copy() for i in order], polys)


def depth_in(tree, p, reach=1.0):
    """Signed depth of ``p`` inside the shell ``tree``: positive inside, negative outside."""
    hit = tree.find_nearest(p, reach)
    if hit[0] is None:
        return -reach
    loc, nrm, _i, dist = hit
    return dist if (p - loc).dot(nrm) < 0.0 else -dist


def classify(me):
    """Split the finished mesh into named parts by material and shape."""
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    groups = shells(me)
    owner = {}
    for si, g in enumerate(groups):
        for i in g:
            owner[i] = si
    polys = {}
    for p in me.polygons:
        polys.setdefault(owner[p.vertices[0]], []).append(p)
    out = {k: [] for k in ("end", "skid", "deck", "shelf", "back", "rail", "plate", "iron",
                           "wheel", "cover", "pages", "band", "other")}
    for si, g in enumerate(groups):
        pts = [me.vertices[i].co.copy() for i in g]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        ext = hi - lo
        ranked = sorted(polys.get(si, []), key=lambda p: -p.area)
        rec = {"g": g, "pts": pts, "lo": lo, "hi": hi, "ext": ext,
               "c": sum(pts, Vector()) / len(pts),
               "big": [(p.center.copy(), p.normal.copy()) for p in ranked[:2]]}
        m = mats.get(g[0], -1)
        if m == WOOD_IDX:
            nz = abs(rec["big"][0][1].z) if rec["big"] else 0.0
            if ext.x < 0.05 and ext.z > 0.7:
                out["end"].append(rec)
            elif ext.x < 0.1 and ext.y > 0.4 and ext.z < 0.05:
                out["skid"].append(rec)
            elif ext.x > 0.6 and ext.y < 0.04 and ext.z < 0.04:
                out["rail"].append(rec)
            elif ext.x > 0.6 and nz > 0.999:
                out["deck"].append(rec)
            elif ext.x > 0.6 and nz > 0.9:
                out["shelf"].append(rec)
            elif ext.x > 0.6 and nz < 0.5:
                out["back"].append(rec)
            else:
                out["other"].append(rec)
        elif m == IRON_IDX:
            (out["plate"] if ext.z < 0.006 and ext.x > 0.04 else out["iron"]).append(rec)
        elif m == RUBBER_IDX:
            out["wheel"].append(rec)
        elif m in (CLOTH_IDX, LEATHER_IDX):
            face = ranked[0]
            rec["n"] = face.normal.copy()
            rec["face_len"] = max((me.vertices[face.vertices[k]].co
                                   - me.vertices[face.vertices[k - 1]].co).length
                                  for k in range(len(face.vertices)))
            out["cover"].append(rec)
        elif m == PAPER_IDX:
            out["pages"].append(rec)
        elif m == GILT_IDX:
            out["band"].append(rec)
        else:
            out["other"].append(rec)
    return out


def overlaps_xy(a, b, pad=0.0):
    return (a["lo"].x - pad < b["hi"].x and b["lo"].x - pad < a["hi"].x
            and a["lo"].y - pad < b["hi"].y and b["lo"].y - pad < a["hi"].y)


def trolley_audit(me):
    parts = classify(me)
    out = {k: len(v) for k, v in parts.items()}

    # Named supports: the four wheels, each on the floor.
    out["wheel_z"] = max((r["lo"].z for r in parts["wheel"]), default=99.0)

    # Every cross member is housed in both end panels: bite past the inner
    # face, and clear of the far face.
    ends = sorted(parts["end"], key=lambda r: r["c"].x)
    cross = parts["deck"] + parts["shelf"] + parts["back"] + parts["rail"]
    out["cross"] = len(cross)
    bite, far = 99.0, 99.0
    if len(ends) == 2:
        left_in, left_out = ends[0]["hi"].x, ends[0]["lo"].x
        right_in, right_out = ends[1]["lo"].x, ends[1]["hi"].x
        for r in cross:
            bite = min(bite, left_in - r["lo"].x, r["hi"].x - right_in)
            far = min(far, r["lo"].x - left_out, right_out - r["hi"].x)
    out["dado"], out["dado_far"] = bite, far

    # Caster plates: each one's top a band into the skid above it.
    pseats = []
    for r in parts["plate"]:
        above = [s for s in parts["skid"] if overlaps_xy(s, r)]
        if above:
            pseats.append(r["hi"].z - min(s["lo"].z for s in above))
    out["plate_seat"] = (min(pseats, default=-99.0), max(pseats, default=99.0))
    out["n_plate_seated"] = len(pseats)

    # Books: each cover with the page block and bands nearest it.
    covers = parts["cover"]
    trees = [shell_tree(me, [c["g"]]) for c in covers]
    units = [{"cover": c, "tree": t, "pages": [], "band": []} for c, t in zip(covers, trees)]
    for kind in ("pages", "band"):
        for r in parts[kind]:
            if units:
                u = min(units, key=lambda u: sum(u["tree"].find_nearest(p)[3]
                                                 for p in r["pts"]) / len(r["pts"]))
                u[kind].append(r)
    out["units"] = len(units)
    out["unmatched"] = sum(1 for u in units if len(u["pages"]) != 1 or len(u["band"]) != 2)

    page_d = [depth_in(u["tree"], p) for u in units for r in u["pages"] for p in r["pts"]]
    out["page_bite"] = (min(page_d, default=-99.0), max(page_d, default=99.0))

    b_in, b_out = [], []
    for u in units:
        for r in u["band"]:
            ds = sorted(depth_in(u["tree"], p) for p in r["pts"])
            half = len(ds) // 2
            b_in.extend(ds[half:])
            b_out.append(-max(ds[:half]))
    out["band_bite"] = (min(b_in, default=-99.0), max(b_in, default=99.0))
    out["band_proud"] = min(b_out, default=-99.0)

    # Pose of each book from its largest face, a board: standing or lying.
    for u in units:
        c = u["cover"]
        n = c["n"]
        tilt = math.asin(min(1.0, abs(n.z)))
        c["pose"] = ("up" if tilt <= UPRIGHT_TILT_MAX else
                     "lying" if tilt >= LYING_TILT_MIN else "other")
        ds = [p.dot(n) for p in c["pts"]]
        c["thick"] = max(ds) - min(ds)
    out["n_up"] = sum(1 for u in units if u["cover"]["pose"] == "up")
    out["n_lying"] = sum(1 for u in units if u["cover"]["pose"] == "lying")

    # Each trough is a shelf and the one backrest that bites into it.
    shelves = parts["shelf"]
    stree = [shell_tree(me, [r["g"]]) for r in shelves]
    btree = [shell_tree(me, [r["g"]]) for r in parts["back"]]
    for r, t in zip(shelves, stree):
        r["backs"] = [b for b, bt in zip(parts["back"], btree) if t.overlap(bt)]
        top = [f for f in r["big"] if f[1].z > 0.0]
        r["top"] = top[0] if top else None
    out["troughs_paired"] = sum(1 for r in shelves if len(r["backs"]) == 1 and r["top"])

    # Seats. A standing book is on the shelf of its own side whose top plane
    # (read off the mesh) is nearest its lowest point; the seat is how deep
    # that point sits under the plane. A lying book is on the deck or the
    # cover below it, measured in Z.
    seats = []
    deck = parts["deck"]
    for u in units:
        c = u["cover"]
        if c["pose"] == "up":
            best = None
            for r in shelves:
                if r["top"] is None or (r["c"].y > 0) != (c["c"].y > 0):
                    continue
                p0, n = r["top"]
                dmin = min((p - p0).dot(n) for p in c["pts"])
                if abs(dmin) <= SUPPORT_REACH and (best is None or abs(dmin) < abs(best[0])):
                    best = (dmin, r)
            if best is not None:
                u["support"] = best[1]
                seats.append(-best[0])
        elif c["pose"] == "lying":
            cands = [r for r in deck + covers if r is not c and overlaps_xy(r, c)
                     and c["lo"].z - SUPPORT_REACH <= r["hi"].z <= c["lo"].z + 0.01]
            if cands:
                u["support"] = max(cands, key=lambda r: r["hi"].z)
                seats.append(u["support"]["hi"].z - c["lo"].z)
    out["seat"] = (min(seats, default=-99.0), max(seats, default=99.0))
    out["n_seated"] = len(seats)

    # Size spread: thickness across the boards, height along the board face.
    th = [u["cover"]["thick"] for u in units]
    hs = [u["cover"]["face_len"] for u in units]
    out["thick_spread"] = max(th) / min(th) if th else 0.0
    out["height_spread"] = max(hs) / min(hs) if hs else 0.0

    # The second support: every standing book's fore-edge in its trough's
    # backrest. Depth past the plane of the backrest face that looks at the
    # book, read off the mesh, over the book's cover vertices.
    backs = []
    for u in units:
        c = u["cover"]
        if c["pose"] != "up":
            continue
        sup = u.get("support")
        if sup is None or len(sup.get("backs", ())) != 1:
            backs.append(-99.0)
            continue
        br = sup["backs"][0]
        u["back"] = br
        facing = [f for f in br["big"] if f[1].dot(c["c"] - f[0]) > 0.0]
        if not facing:
            backs.append(-99.0)
            continue
        p0, n = facing[0]
        backs.append(max(-(p - p0).dot(n) for p in c["pts"]))
    out["back_bite"] = (min(backs, default=-99.0), max(backs, default=99.0))
    out["n_backed"] = len(backs)

    # Books do not run into one another, nor into the carcass, except where
    # they are meant to: a book on the one it is stacked on, a trough book on
    # its shelf and against its backrest, a stack on the deck.
    utrees = [shell_tree(me, [u["cover"]["g"]] + [r["g"] for r in u["pages"] + u["band"]])
              for u in units]
    carcass = [r for k in ("end", "skid", "deck", "shelf", "back", "rail") for r in parts[k]]
    ctrees = [shell_tree(me, [r["g"]]) for r in carcass]
    designed = set()
    for i, u in enumerate(units):
        for j, v in enumerate(units):
            if u.get("support") is v["cover"]:
                designed.add((min(i, j), max(i, j)))
    hits, where = 0, []
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            if (i, j) in designed:
                continue
            if utrees[i].overlap(utrees[j]):
                hits += 1
                where.append((units[i]["cover"]["c"], units[j]["cover"]["c"]))
        for r, ct in zip(carcass, ctrees):
            if r is units[i].get("support") or r is units[i].get("back"):
                continue
            if utrees[i].overlap(ct):
                hits += 1
                where.append((units[i]["cover"]["c"], r["c"]))
    out["book_hits"] = hits
    out["hit_at"] = where
    return out


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


def hull_collider(obj, name):
    """One convex hull over the carcass and casters; the books sit inside it."""
    me = obj.data
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    pts = [me.vertices[i].co.copy() for i in range(len(me.vertices))
           if mats.get(i, -1) not in BOOK_MATS]
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        vs = [bm.verts.new(p) for p in pts]
        ret = bmesh.ops.convex_hull(bm, input=vs)
        drop = []
        for v in ret["geom_interior"] + ret["geom_unused"]:
            if isinstance(v, bmesh.types.BMVert) and v not in drop:
                drop.append(v)
        bmesh.ops.delete(bm, geom=drop, context="VERTS")
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1.0),
                                 verts=list(bm.verts), edges=list(bm.edges))
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    col = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(col)
    return col


def setup_bake_image(obj, target_mat, size):
    img = bpy.data.images.new("TrolleyNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = WOOD_IDX
    return img, tex


def bake_normal(high, low):
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
        type="NORMAL", use_selected_to_active=True, cage_extrusion=CAGE_EXTRUSION,
        use_cage=False, normal_space="TANGENT", margin=4,
        margin_type="ADJACENT_FACES", use_clear=True, target="IMAGE_TEXTURES",
    )


def export_unity(path, objects):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=path, use_selection=True, export_yup=True, export_apply=True,
        export_draco_mesh_compression_enable=False, export_animations=False,
    )


def check(skip_decimate, lift_z=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_trolley_mesh("TrolleyLow", **flags)
    # The bake source is the carcass and casters only. Only the wood takes a
    # baked map, and the books sit within any cage of it: seated 1-3 mm into
    # the deck and shelves, 6 mm off the end panels. Rays from those faces
    # found the covers and baked each book's footprint into the deck.
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_trolley_mesh("TrolleyHigh", with_books=False, **hi_flags)
    mats = trolley_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("trolley mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[WOOD_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "TrolleyLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "TrolleyLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(high, "TrolleyCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_book_trolley_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender points TMPDIR at its own temp preference, which on a portable
    # build is the working directory, so the export must not outlive this.
    if os.path.isfile(export_path):
        os.remove(export_path)

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    sa = trolley_audit(low.data)
    mirror = mirror_error(low.data)
    right = right_angle_edges(low.data)

    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured mat_index_counts={dict(sorted(idx_counts.items()))}")
    print(f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
          f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}")
    print(f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
          f"overlap={overlap:.6f} nfaces={nfaces}")
    print(f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
          f"outer={OUTER_SIZE} zmin={bb[2]:.5f}")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured parts ends={sa['end']} skids={sa['skid']} deck={sa['deck']} "
          f"shelves={sa['shelf']} backs={sa['back']} rail={sa['rail']} plates={sa['plate']} "
          f"iron={sa['iron']} wheels={sa['wheel']} covers={sa['cover']} pages={sa['pages']} "
          f"bands={sa['band']} other={sa['other']} unmatched={sa['unmatched']} "
          f"up={sa['n_up']} lying={sa['n_lying']} wheel_z={sa['wheel_z']:.5f}")
    print(f"measured joints cross={sa['cross']} dado={sa['dado']:.5f} "
          f"dado_far={sa['dado_far']:.5f} "
          f"page_bite=({sa['page_bite'][0]:.5f},{sa['page_bite'][1]:.5f})")
    print(f"measured seats book=({sa['seat'][0]:.5f},{sa['seat'][1]:.5f}) n={sa['n_seated']} "
          f"band_bite=({sa['band_bite'][0]:.5f},{sa['band_bite'][1]:.5f}) "
          f"band_proud={sa['band_proud']:.5f} "
          f"plate_seat=({sa['plate_seat'][0]:.5f},{sa['plate_seat'][1]:.5f}) "
          f"n_plate={sa['n_plate_seated']}")
    print(f"measured mirror={mirror:.7f} thick_spread={sa['thick_spread']:.3f} "
          f"height_spread={sa['height_spread']:.3f} troughs_paired={sa['troughs_paired']} "
          f"back=({sa['back_bite'][0]:.5f},{sa['back_bite'][1]:.5f}) n_backed={sa['n_backed']} "
          f"book_hits={sa['book_hits']} right_angle_wood={right}")
    if sa["book_hits"]:
        print(f"measured hit_at={[(tuple(round(x, 3) for x in a), tuple(round(x, 3) for x in b)) for a, b in sa['hit_at'][:6]]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + nothing
    if nmat != MATERIAL_COUNT or distinct != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct} != {MATERIAL_COUNT}", 5),) + nothing
    for idx, floor in FACE_FLOORS.items():
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"material {idx} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + nothing
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + nothing
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + nothing
    if (abs(size_x - OUTER_SIZE[0]) > BBOX_TOL or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
            or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL):
        return (fail(f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8),) + nothing
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
                     "(--skip-decimate is the designed fail)", 9),) + nothing
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9),) + nothing
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + nothing
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + nothing
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + nothing
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf} (--stray-vert is the designed fail)", 15),) + nothing
    if abs(bb[2]) > ZMIN_EPS:
        return (fail(f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
                     "(--lift-z is the designed fail)", 16),) + nothing
    if sa["wheel"] != N_CASTERS or sa["wheel_z"] > WHEEL_Z_MAX:
        return (fail(f"wheels: {sa['wheel']} of {N_CASTERS}, worst wheel z={sa['wheel_z']:.5f} "
                     f"> {WHEEL_Z_MAX} (--float-caster is the designed fail)", 16),) + nothing
    if (sa["end"] != 2 or sa["cross"] != N_CROSS or sa["dado"] < DADO_MIN
            or sa["dado_far"] < DADO_FAR_MIN):
        return (fail(f"{sa['end']} of 2 ends, {sa['cross']} of {N_CROSS} cross members, dado bite "
                     f"{sa['dado']:.5f} (min {DADO_MIN}), far face {sa['dado_far']:.5f} "
                     f"(min {DADO_FAR_MIN}) (--short-shelves is the designed fail)", 17),) + nothing
    if (sa["units"] != N_BOOKS or sa["unmatched"] or sa["page_bite"][0] < PAGE_BITE_MIN
            or sa["page_bite"][1] > PAGE_BITE_MAX):
        return (fail(f"{sa['units']} of {N_BOOKS} books, {sa['unmatched']} without one page "
                     f"block and two bands, page bite {sa['page_bite']} outside "
                     f"[{PAGE_BITE_MIN}, {PAGE_BITE_MAX}] (--loose-pages is the designed fail)",
                     17),) + nothing
    if sa["n_seated"] != N_BOOKS or sa["seat"][0] < SEAT_MIN or sa["seat"][1] > SEAT_MAX:
        return (fail(f"{sa['n_seated']} of {N_BOOKS} books seated, seat {sa['seat']} outside "
                     f"[{SEAT_MIN}, {SEAT_MAX}] (--float-books is the designed fail)", 18),) + nothing
    if (sa["band_bite"][0] < BAND_BITE_MIN or sa["band_bite"][1] > BAND_BITE_MAX
            or sa["band_proud"] < BAND_PROUD_MIN):
        return (fail(f"band bite {sa['band_bite']} outside [{BAND_BITE_MIN}, {BAND_BITE_MAX}] "
                     f"or proud {sa['band_proud']:.5f} < {BAND_PROUD_MIN} "
                     "(--float-bands is the designed fail)", 18),) + nothing
    if (sa["n_plate_seated"] != N_CASTERS or sa["plate_seat"][0] < PLATE_SEAT_MIN
            or sa["plate_seat"][1] > PLATE_SEAT_MAX):
        return (fail(f"{sa['n_plate_seated']} of {N_CASTERS} caster plates under a skid, seat "
                     f"{sa['plate_seat']} outside [{PLATE_SEAT_MIN}, {PLATE_SEAT_MAX}] "
                     "(--drop-plates is the designed fail)", 18),) + nothing
    if mirror > MIRROR_EPS:
        return (fail(f"carcass and casters off mirror symmetry by {mirror:.6f} > {MIRROR_EPS} "
                     "(--skew-caster is the designed fail)", 19),) + nothing
    if sa["thick_spread"] < THICK_SPREAD_MIN or sa["height_spread"] < HEIGHT_SPREAD_MIN:
        return (fail(f"book spread thickness {sa['thick_spread']:.3f} (min {THICK_SPREAD_MIN}), "
                     f"height {sa['height_spread']:.3f} (min {HEIGHT_SPREAD_MIN}) "
                     "(--uniform-books is the designed fail)", 20),) + nothing
    if (sa["n_up"] != N_UP or sa["n_lying"] != N_LYING or sa["troughs_paired"] != N_TROUGH
            or sa["n_backed"] != N_UP or sa["back_bite"][0] < BACK_MIN
            or sa["back_bite"][1] > BACK_MAX):
        return (fail(f"{sa['n_up']} of {N_UP} trough and {sa['n_lying']} of {N_LYING} lying books, "
                     f"{sa['troughs_paired']} of {N_TROUGH} troughs with one backrest, backrest "
                     f"contact {sa['back_bite']} outside [{BACK_MIN}, {BACK_MAX}] "
                     "(--off-back and --deep-back are the designed fails)", 21),) + nothing
    if sa["book_hits"]:
        return (fail(f"{sa['book_hits']} book overlaps, need 0 "
                     "(--crowd-books is the designed fail)", 22),) + nothing
    if right:
        return (fail(f"{right} right-angle wood edges, need 0 "
                     "(--sharp-deck is the designed fail)", 23),) + nothing
    return 0, low, high, mats, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats[WOOD_IDX], tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only.
    low.rotation_euler.z = math.radians(-16.0)

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
    wall.location = (0.0, 8.5, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, kind, loc, energy, size, col, rot=(0, 0, 0)):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        if kind == "AREA":
            ld.size = size
        else:
            ld.shadow_soft_size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", "AREA", (-2.4, -3.4, 3.2), 480.0, 3.0, (1.0, 0.95, 0.88), (50, 0, -35))
    light("Fill", "AREA", (3.2, -2.8, 1.6), 80.0, 5.0, (0.74, 0.84, 1.0), (68, 0, 48))
    light("Rim", "AREA", (-1.8, 2.6, 2.6), 220.0, 3.0, (0.62, 0.78, 1.0), (-55, 0, 200))
    ld = bpy.data.lights.new("Wedge", "SPOT")
    ld.energy, ld.color = 260.0, (1.0, 0.66, 0.34)
    ld.spot_size, ld.spot_blend, ld.shadow_soft_size = math.radians(50.0), 1.0, 0.3
    wedge = bpy.data.objects.new("Wedge", ld)
    wedge.location = (0.6, 1.8, 2.2)
    wedge.rotation_euler = (Vector((0.2, 0.6, 0.0)) - wedge.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.collection.objects.link(wedge)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.10, -3.10, 1.50)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.48)
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

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low], stage=[floor, wall])
    if fcode:
        return fcode
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
    p.add_argument("--float-caster", action="store_true")
    p.add_argument("--short-shelves", action="store_true")
    p.add_argument("--loose-pages", action="store_true")
    p.add_argument("--float-books", action="store_true")
    p.add_argument("--float-bands", action="store_true")
    p.add_argument("--drop-plates", action="store_true")
    p.add_argument("--skew-caster", action="store_true")
    p.add_argument("--uniform-books", action="store_true")
    p.add_argument("--off-back", action="store_true")
    p.add_argument("--deep-back", action="store_true")
    p.add_argument("--crowd-books", action="store_true")
    p.add_argument("--sharp-deck", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_caster=args.float_caster,
        short_shelves=args.short_shelves,
        sharp_deck=args.sharp_deck,
        drop_plates=args.drop_plates,
        skew_caster=args.skew_caster,
        loose_pages=args.loose_pages,
        float_books=args.float_books,
        float_bands=args.float_bands,
        uniform_books=args.uniform_books,
        crowd_books=args.crowd_books,
        off_back=args.off_back,
        deep_back=args.deep_back,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("book-trolley OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
