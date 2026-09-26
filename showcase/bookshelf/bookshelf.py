"""Game-ready bookshelf with leaning books — a showcase piece, not an example.

Asserts budget conformance of a procedural bookcase: a stained carcass
with two housed shelves, a base on a recessed plinth, lapped back boards
and a stepped cornice, filled with thirty-eight hardback books. Most
stand upright; seven lie in three stacks; two lean on a neighbour. Every
book is a rounded-spine cover in cloth or leather, a page block glued
into it, and two gilt bands tooled round the spine. Carried through UVs,
five materials (wood, cloth, leather, paper, gilt), a high-to-low normal
bake, an LOD chain, a convex collider, and a Unity glTF export.

The budget that matters is the one a leaning book fails invisibly: it has
to rest on its neighbour's head edge and on the shelf, not in either. Tip
it a few degrees too far and its board cuts through the neighbour's
corner; not far enough and it stands in the air against nothing. Every
seat, the bounding box, the triangle count and the book-overlap budget
(which must exempt the designed contact) still pass either way. The piece
finds each leaning book and its neighbour on the finished mesh and asserts
how deep the neighbour's head edge sits in the leaning board, as a band.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-side`` the named sides,
``--short-shelves`` the dado bite, ``--loose-pages`` the page-block bite,
``--float-books`` the book seat, ``--float-bands`` the band seat,
``--tall-book`` the headroom, ``--uniform-books`` the size spread,
``--air-lean`` and ``--deep-lean`` the lean contact, ``--crowd-books``
book interpenetration, ``--sharp-shelf`` edge treatment.

No randomness: every book's size, tint, gap, setback and seat is a table
entry or a closed-form term of its index. DECIMATE COLLAPSE triangle
counts are not byte-identical across Blender versions — the LOD gate is a
ratio band.

    blender --background --python bookshelf.py --
    blender --background --python bookshelf.py -- --air-lean
    blender --background --python bookshelf.py -- --output bookshelf.png
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

# The carcass. X across, Y front (-) to back (+), Z up. Two full-height
# sides carry everything; every cross member is housed into both of them.
W_OUT = 0.920
SIDE_T = 0.022
DEPTH = 0.300
SIDE_H = 1.140
DADO = 0.008
TOP_T = 0.026
TOP_SEAT = 0.006
TOP_OVER = 0.016
TOP_BACK_OVER = 0.006
CORN_T = 0.020
CORN_OVER = 0.010
CORN_BITE = 0.004
CORN_BACK_IN = 0.004
BACK_T = 0.012
BACK_INSET = 0.010
BACK_BITE = 0.005
N_BACK = 5
BACK_LAP = 0.002
BACK_STEP = 0.0015
SHELF_T = 0.022
SHELF_SETBACK = 0.004
SHELF_TOPS = (0.460, 0.800)
BASE_Z = 0.070
BASE_T = 0.020
BASE_SETBACK = 0.004
PLINTH_Z0 = 0.004
PLINTH_SET = 0.018
PLINTH_T = 0.018
PLINTH_BITE = 0.004
CHAMFER = 0.0025

# Books. Local frame: X across the thickness, Y from the spine (-) to the
# fore-edge (+), Z up the height, bottom of the cover at 0. The cover is
# one shell: a U of board, rounded spine and board, extruded up the
# height. The page block sits inside it, SQUARE short of the cover at the
# head, tail and fore-edge, and bites PAGE_BITE into both boards.
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
FLOAT_SIDE = 0.005
START_GAP = 0.006
GAP_BASE = 0.0025
GAP_SPAN = 0.0020
CROWD_GAP = -0.0041
SET_BASE = 0.006
SET_STEP = 0.0013
SET_CLEAR = 0.0004
SET_NUDGE = 0.0009
STACK_YAW = math.radians(3.0)
STACK_SHIFT = 0.006
LEAN_BITE = 0.0008
AIR_LEAN = -0.003
DEEP_LEAN = 0.0045
TALL_BOOK = 1.20
UNIFORM_BOOK = (0.034, 0.230, 0.170)
UNIFORM_JIT = 0.03
UPRIGHT_YAW = (-2.4, -0.8, 0.8, 2.4)

# Per shelf, left to right. ("up", T, H, D, kind), ("lean", T, H, D, kind,
# direction, degrees), ("stack", [(T, H, D, kind), ...] bottom first),
# ("gap", width). kind: "c" cloth, "l" leather. A leaning book leans onto
# the upright beside it: -1 onto the book on its left, +1 onto the right.
LAYOUT = (
    (
        ("stack", [(0.046, 0.300, 0.228, "l"), (0.036, 0.285, 0.214, "c")]),
        ("gap", 0.014),
        ("up", 0.052, 0.305, 0.226, "l"),
        ("up", 0.034, 0.282, 0.205, "c"),
        ("up", 0.041, 0.291, 0.214, "c"),
        ("up", 0.058, 0.268, 0.198, "l"),
        ("up", 0.030, 0.296, 0.221, "c"),
        ("up", 0.044, 0.262, 0.192, "c"),
        ("up", 0.037, 0.276, 0.207, "l"),
        ("up", 0.049, 0.255, 0.188, "c"),
        ("lean", 0.036, 0.300, 0.218, "c", -1, 18.0),
    ),
    (
        ("lean", 0.032, 0.268, 0.196, "l", 1, 22.0),
        ("up", 0.040, 0.228, 0.170, "c"),
        ("up", 0.026, 0.251, 0.183, "c"),
        ("up", 0.047, 0.262, 0.194, "l"),
        ("up", 0.022, 0.214, 0.158, "c"),
        ("up", 0.035, 0.240, 0.176, "c"),
        ("up", 0.055, 0.270, 0.201, "l"),
        ("up", 0.029, 0.233, 0.172, "c"),
        ("up", 0.038, 0.246, 0.180, "c"),
        ("up", 0.024, 0.221, 0.163, "l"),
        ("gap", 0.050),
        ("stack", [(0.034, 0.232, 0.170, "c"), (0.028, 0.214, 0.160, "l"),
                   (0.022, 0.196, 0.148, "c")]),
    ),
    (
        ("up", 0.031, 0.236, 0.172, "c"),
        ("up", 0.024, 0.212, 0.156, "c"),
        ("up", 0.043, 0.254, 0.187, "l"),
        ("up", 0.020, 0.198, 0.146, "c"),
        ("up", 0.036, 0.226, 0.166, "c"),
        ("up", 0.028, 0.243, 0.178, "l"),
        ("up", 0.045, 0.265, 0.195, "c"),
        ("up", 0.022, 0.205, 0.151, "c"),
        ("up", 0.033, 0.219, 0.161, "l"),
        ("up", 0.039, 0.248, 0.182, "c"),
        ("up", 0.026, 0.186, 0.140, "c"),
        ("up", 0.030, 0.231, 0.170, "c"),
        ("gap", 0.080),
        ("stack", [(0.030, 0.226, 0.166, "l"), (0.024, 0.200, 0.150, "c")]),
    ),
)
TALL_TARGET = (1, 6)  # the 0.270 m leather volume on the middle shelf
CLOTH_TINTS = ((0.22, 0.035, 0.030), (0.045, 0.095, 0.055), (0.035, 0.050, 0.115),
               (0.33, 0.21, 0.075), (0.10, 0.105, 0.11), (0.12, 0.045, 0.085),
               (0.30, 0.21, 0.13), (0.045, 0.095, 0.095))
LEATHER_TINTS = ((0.17, 0.070, 0.030), (0.26, 0.12, 0.050), (0.085, 0.040, 0.020),
                 (0.21, 0.055, 0.030))

BBOX_TOL = 0.020
OUTER_SIZE = (0.972, 0.332, 1.176)

BASE_TRIS_MIN = 10400
BASE_TRIS_MAX = 11400
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 5
FACE_FLOORS = {0: 300, 1: 1850, 2: 960, 3: 200, 4: 1780}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 200
BAKE_RES = 1024
CAGE_EXTRUSION = 0.01
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
SIDE_Z_MAX = 1e-4
DADO_MIN = 0.005
DADO_FAR_MIN = 0.006
PAGE_BITE_MIN = 0.0003
PAGE_BITE_MAX = 0.0012
SEAT_MIN = 0.0005
SEAT_MAX = 0.0036
BAND_BITE_MIN = 0.0001
BAND_BITE_MAX = 0.0008
BAND_PROUD_MIN = 0.0004
HEADROOM_MIN = 0.020
THICK_SPREAD_MIN = 2.5
HEIGHT_SPREAD_MIN = 1.5
UPRIGHT_TILT_MAX = math.radians(3.0)
LYING_TILT_MIN = math.radians(80.0)
LEAN_BITE_MIN = 0.0003
LEAN_BITE_MAX = 0.0020
LEAN_SEARCH = 0.03
RIGHT_ANGLE_TOL = math.radians(5.0)

WOOD_IDX = 0
CLOTH_IDX = 1
LEATHER_IDX = 2
PAPER_IDX = 3
GILT_IDX = 4
N_CROSS = len(SHELF_TOPS) + 2
N_BOOKS = sum(len(it[1]) if it[0] == "stack" else (0 if it[0] == "gap" else 1)
              for row in LAYOUT for it in row)
N_LEAN = sum(1 for row in LAYOUT for it in row if it[0] == "lean")
N_LYING = sum(len(it[1]) for row in LAYOUT for it in row if it[0] == "stack")


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


# --- one book, in its own frame ---------------------------------------------


def spine_chain(t, d):
    """Centre line of the cover's U and its outward normal at each point.

    Front board from the fore-edge to the spine, a half-round spine of
    SPINE_ARC segments, back board to the fore-edge. The boards are tangent
    to the spine, so the spine reads round and the boards flat.
    """
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
    0 cover, 1 pages, 2 band. The cover is chamfered here, in its own
    bmesh, so the placement code sees the finished corners it will rest on.
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
        # The bevel picks edges by face angle, which needs consistent normals.
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.edges.index_update()
        edges = sorted((ed for ed in bm.edges if ed.calc_face_angle(0.0) > math.radians(40.0)),
                       key=lambda ed: ed.index)
        bmesh.ops.bevel(bm, geom=edges, offset=COVER_CHAMFER, segments=1, profile=0.5,
                        affect="EDGES", clamp_overlap=True)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])

        # Page block: inside the U, biting both boards, square short of the
        # cover at head, tail and fore-edge. Its back stops PAGE_BACK short of
        # the line where the boards meet the spine, where the band ends lie.
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

        # Gilt bands round the spine, built on the cover's own outer chain:
        # every band vertex sits on a cover vertex's normal, so the band
        # follows the round of the spine exactly.
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
    t, h, d, kind = dims
    verts, faces = book_local(t, h, d, loose_pages=loose_pages, float_bands=float_bands)
    cover_ix = sorted({i for vs, k in faces if k == 0 for i in vs})
    return {"t": t, "h": h, "d": d, "kind": kind, "verts": verts, "faces": faces,
            "cover_ix": cover_ix, "M": rot.copy(), "world": [rot @ v for v in verts]}


def lean_face(book, side):
    """Point and outward normal of a leaning book's board face on ``side``."""
    rot = book["M"].to_3x3()
    n = (rot @ Vector((float(side), 0.0, 0.0))).normalized()
    return book["M"] @ Vector((side * book["t"] / 2.0, 0.0, 0.0)), n


def penetration(pts, p0, n):
    """How far the deepest of ``pts`` sits behind the plane (p0, n)."""
    return max(-(p - p0).dot(n) for p in pts)


def plan_books(loose_pages=False, float_books=False, float_bands=False, tall_book=False,
               uniform_books=False, crowd_books=False, air_lean=False, deep_lean=False):
    """Place every book. Closed-form: sizes from LAYOUT, the rest from the index.

    Each book is built, turned, then set down: its lowest cover vertex a
    stepped seat into whatever it stands on, its spine a stepped setback
    from the shelf front, and along the shelf at the running cursor. A
    leaning book is then slid (or its neighbour is) until the neighbour's
    head edge sits the lean bite into the leaning board.
    """
    x_in = W_OUT / 2.0 - SIDE_T
    y_front = -DEPTH / 2.0 + SHELF_SETBACK
    tops = (BASE_Z + BASE_T,) + SHELF_TOPS
    bite = LEAN_BITE + (AIR_LEAN - LEAN_BITE if air_lean else 0.0) + (
        DEEP_LEAN - LEAN_BITE if deep_lean else 0.0)
    lift = FLOAT_BOOKS if float_books else 0.0
    books = []
    for s, row in enumerate(LAYOUT):
        cursor = -x_in + START_GAP
        k = 0
        placed = []
        pending = None

        def sized(dims, s=s, ii=None, j=0):
            t, h, d, kind = dims
            if uniform_books:
                # One height and depth; thickness within +-1.5 %, so no two
                # spines are the same solid set a hair apart.
                n = s * 100 + (ii or 0) * 5 + j
                ft = 1.0 + UNIFORM_JIT * (frac(n * 0.6180339887 + 0.1) - 0.5)
                t, h, d = UNIFORM_BOOK[0] * ft, UNIFORM_BOOK[1], UNIFORM_BOOK[2]
            if tall_book and (s, ii) == TALL_TARGET:
                h *= TALL_BOOK
            return (t, h, d, kind)

        def gap_of(k, s=s):
            if crowd_books and s == 2:
                return CROWD_GAP
            return GAP_BASE + GAP_SPAN * frac(k * 0.6180339887 + 0.3 + s * 0.17)

        def y_keys(book):
            lo, hi = bounds(cover_points(book))
            yc = lo.y + book["t"] / 2.0
            return (lo.x + hi.x) / 2.0, (lo.y, yc, yc + PAGE_BACK, hi.y - SQUARE, hi.y)

        def set_down(book, k, x_left, support_top, seat_k=None):
            lo, hi = bounds(cover_points(book))
            seat = SEAT_BASE + SEAT_STEP * (k if seat_k is None else seat_k)
            move(book, Vector((x_left - lo.x,
                               y_front + SET_BASE + SET_STEP * (k % 7) - lo.y,
                               support_top - seat - lo.z)))
            # Spine fronts, spine lines and fore-edges are planes facing Y.
            # Two neighbours landing one on the same plane z-fight, so step
            # this book back until none of its planes meets a neighbour's.
            for _ in range(8):
                cx, keys = y_keys(book)
                near = [y_keys(o)[1] for o in placed if abs(y_keys(o)[0] - cx) < 0.12]
                if not any(abs(a - b) < SET_CLEAR for ks in near for a in keys for b in ks):
                    break
                move(book, Vector((0.0, SET_NUDGE, 0.0)))

        for ii, item in enumerate(row):
            tag = item[0]
            if tag == "gap":
                cursor += item[1]
                continue
            if tag == "up":
                # Upright books stand a degree or so off square, in a
                # four-step cycle. Every spine has the same facet angles, so
                # square neighbours share planes by accident whenever their
                # offsets line up; a degree apart, no two faces are parallel.
                yaw = math.radians(UPRIGHT_YAW[k % len(UPRIGHT_YAW)])
                b = make_book(sized(item[1:5], ii=ii), Matrix.Rotation(yaw, 4, "Z"),
                              loose_pages, float_bands)
                set_down(b, k, cursor + gap_of(k), tops[s] + lift)
                if pending is not None:
                    p0, n = lean_face(pending, 1)
                    pen = penetration(cover_points(b), p0, n)
                    move(b, Vector(((pen - bite) / n.x, 0.0, 0.0)))
                    b["lean_on"] = pending
                    pending = None
            elif tag == "lean":
                side, deg = item[5], item[6]
                rot = Matrix.Rotation(side * math.radians(deg), 4, "Y")
                b = make_book(sized(item[1:5], ii=ii), rot, loose_pages, float_bands)
                set_down(b, k, cursor + gap_of(k), tops[s] + lift)
                if side < 0:
                    nb = placed[-1]
                    p0, n = lean_face(b, -1)
                    pen = penetration(cover_points(nb), p0, n)
                    move(b, Vector(((bite - pen) / n.x, 0.0, 0.0)))
                    b["lean_on"] = nb
                else:
                    pending = b
            else:
                stack_top = tops[s] + lift
                centre = None
                stack = []
                for j, dims in enumerate(item[1]):
                    yaw = STACK_YAW * (1.0 if j % 2 else -1.0)
                    rot = Matrix.Rotation(yaw, 4, "Z") @ Matrix.Rotation(-math.pi / 2.0, 4, "Y")
                    b = make_book(sized(dims, ii=ii, j=j), rot, loose_pages, float_bands)
                    lo, hi = bounds(cover_points(b))
                    if centre is None:
                        centre = cursor + gap_of(k) + (hi.x - lo.x) / 2.0
                    shift = STACK_SHIFT * (0.5 - frac(j * 0.7548776662 + 0.2)) * 2.0
                    # A book stacked on a book takes a small seat of its own
                    # (1.0-1.4 mm), so its underside never lands on the plane
                    # of the page block 2.2 mm inside the board below it.
                    set_down(b, k, centre + shift - (hi.x - lo.x) / 2.0, stack_top,
                             seat_k=(j if j else None))
                    stack_top = bounds(cover_points(b))[1].z
                    b.update({"shelf": s, "i": len(books)})
                    books.append(b)
                    stack.append(b)
                    placed.append(b)
                    k += 1
                cursor = max(bounds(cover_points(x))[1].x for x in stack)
                continue
            b.update({"shelf": s, "i": len(books)})
            books.append(b)
            placed.append(b)
            cursor = bounds(cover_points(b))[1].x
            k += 1
    return books


# --- construction -----------------------------------------------------------


def add_board(bm, lo, hi, boards, sharp=False):
    """Axis-aligned board from corner ``lo`` to ``hi``; its verts go in ``boards``."""
    geo = bmesh.ops.create_cube(bm, size=1.0)
    c = [(lo[k] + hi[k]) * 0.5 for k in range(3)]
    s = [hi[k] - lo[k] for k in range(3)]
    for v in geo["verts"]:
        v.co = Vector((c[0] + v.co.x * s[0], c[1] + v.co.y * s[1], c[2] + v.co.z * s[2]))
    for f in {f for v in geo["verts"] for f in v.link_faces}:
        f.material_index = WOOD_IDX
    if not sharp:
        boards.extend(geo["verts"])
    return geo["verts"]


def build_bookshelf_mesh(
    name,
    stray_vert=False,
    float_side=False,
    short_shelves=False,
    sharp_shelf=False,
    **book_flags,
):
    x_out = W_OUT / 2.0
    x_in = x_out - SIDE_T
    y0, y1 = -DEPTH / 2.0, DEPTH / 2.0
    top_z0 = SIDE_H - TOP_SEAT
    top_z1 = top_z0 + TOP_T
    back_y1 = y1 - BACK_INSET
    back_y0 = back_y1 - BACK_T
    bm = bmesh.new()
    try:
        uv = bm.loops.layers.uv.new("UVMap")
        piece = bm.faces.layers.int.new("Piece")
        boards = []
        # Sides: the two named supports.
        for sx in (-1.0, 1.0):
            lift = FLOAT_SIDE if (float_side and sx < 0) else 0.0
            add_board(bm, (min(sx * x_out, sx * x_in), y0, lift),
                      (max(sx * x_out, sx * x_in), y1, SIDE_H + lift), boards)
        add_board(bm, (-x_out - TOP_OVER, y0 - TOP_OVER, top_z0),
                  (x_out + TOP_OVER, y1 + TOP_BACK_OVER, top_z1), boards)
        # Cornice: a wider board seated on the top, stepping out past it.
        # Its back stops short of the top's back, or the two share a plane.
        add_board(bm, (-x_out - TOP_OVER - CORN_OVER, y0 - TOP_OVER - CORN_OVER,
                       top_z1 - CORN_BITE),
                  (x_out + TOP_OVER + CORN_OVER, y1 + TOP_BACK_OVER - CORN_BACK_IN,
                   top_z1 - CORN_BITE + CORN_T), boards)
        # Back boards, housed into the sides and the top, standing in the
        # base; lapped, every other one stepped forward so no lap is a plane.
        span0, span1 = -x_in - BACK_BITE, x_in + BACK_BITE
        bw = (span1 - span0 + BACK_LAP * (N_BACK - 1)) / N_BACK
        for k in range(N_BACK):
            bx = span0 + k * (bw - BACK_LAP)
            step = BACK_STEP if k % 2 else 0.0
            add_board(bm, (bx, back_y0 - step, BASE_Z + BASE_T - BACK_BITE),
                      (bx + bw, back_y1 - step, top_z0 + BACK_BITE), boards)
        # Cross members: plinth, base and shelves, each in a dado in both sides.
        add_board(bm, (-(x_in + DADO), y0 + PLINTH_SET, PLINTH_Z0),
                  (x_in + DADO, y0 + PLINTH_SET + PLINTH_T, BASE_Z + PLINTH_BITE), boards)
        add_board(bm, (-(x_in + DADO), y0 + BASE_SETBACK, BASE_Z),
                  (x_in + DADO, back_y0 + BACK_BITE, BASE_Z + BASE_T), boards)
        reach = x_in - 0.004 if short_shelves else x_in + DADO
        for s, zt in enumerate(SHELF_TOPS):
            add_board(bm, (-reach, y0 + SHELF_SETBACK, zt - SHELF_T),
                      (reach, back_y0 + BACK_BITE, zt), boards,
                      sharp=(sharp_shelf and s == len(SHELF_TOPS) - 1))
        # A set of BMEdges iterates in address order: sort by index so the
        # bevel emits its faces in the same order on every run.
        bm.edges.index_update()
        edges = sorted({e for v in boards for e in v.link_edges
                        if e.calc_face_angle(0.0) > math.radians(20.0)}, key=lambda e: e.index)
        bmesh.ops.bevel(bm, geom=edges, offset=CHAMFER, segments=1, profile=0.5,
                        affect="EDGES", clamp_overlap=True, material=WOOD_IDX)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])

        books = plan_books(**book_flags)
        for b in books:
            vs = [bm.verts.new(p) for p in b["world"]]
            cover = LEATHER_IDX if b["kind"] == "l" else CLOTH_IDX
            for idx, kind in b["faces"]:
                f = bm.faces.new([vs[i] for i in idx])
                f.material_index = (cover, PAPER_IDX, GILT_IDX)[kind]
                f[piece] = b["i"] + 1
        if stray_vert:
            bm.verts.new((0.0, 0.0, 0.62))
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
    """Face attributes the shaders read: per-board tone and grain, per-book tint.

    Every carcass board gets a closed-form tone and its long axis as grain.
    Every book gets a cloth or leather tint from its index, and its page
    block the book's own thickness axis, so the page lines run parallel to
    the boards however the book is turned. The ``Piece`` tag is then dropped.
    """
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
        if not faces or mats[next(iter(faces))] != WOOD_IDX:
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
    """Stained timber: grain along each board, tone per board (copied from crate-stack)."""
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
    ramp.color_ramp.elements[0].color = (0.070, 0.031, 0.013, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.21, 0.10, 0.042, 1.0)
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
    rough.inputs["To Min"].default_value = 0.66
    rough.inputs["To Max"].default_value = 0.48
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
    """Gold leaf tooling: warm, metallic, a little worn by the noise."""
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
    # Half metallic and fairly rough: a fully metallic band on a spine facing
    # the camera mirrors the dark stage and reads black.
    bsdf.inputs["Metallic"].default_value = 0.55
    bsdf.inputs["Roughness"].default_value = 0.45
    return mat


def bookshelf_materials():
    return (
        wood_material("BookshelfWood"),
        cover_material("BookCloth", 420.0, 0.78, 0.86),
        cover_material("BookLeather", 70.0, 0.62, 0.48),
        paper_material("BookPages"),
        gilt_material("BookGilt"),
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
    big, polys = {}, {}
    for p in me.polygons:
        si = owner[p.vertices[0]]
        polys.setdefault(si, []).append(p)
        if si not in big or p.area > big[si].area:
            big[si] = p
    out = {k: [] for k in ("side", "top", "cornice", "back", "cross", "cover", "pages",
                           "band", "other")}
    for si, g in enumerate(groups):
        pts = [me.vertices[i].co.copy() for i in g]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        ext = hi - lo
        rec = {"g": g, "pts": pts, "lo": lo, "hi": hi, "ext": ext,
               "c": sum(pts, Vector()) / len(pts)}
        m = mats.get(g[0], -1)
        if m == WOOD_IDX:
            if ext.x < 0.05 and ext.z > 0.9:
                out["side"].append(rec)
            elif ext.y < 0.03 and ext.z > 0.9:
                out["back"].append(rec)
            elif lo.z > SIDE_H:
                out["cornice"].append(rec)
            elif hi.z > SIDE_H:
                out["top"].append(rec)
            elif ext.x > 0.7:
                out["cross"].append(rec)
            else:
                out["other"].append(rec)
        elif m in (CLOTH_IDX, LEATHER_IDX):
            face = big[si]
            rec["n"] = face.normal.copy()
            # The two boards' outer faces: the largest faces, one per side.
            ranked = sorted(polys[si], key=lambda p: -p.area)[:4]
            rec["boards"] = [(p.center.copy(), p.normal.copy()) for p in ranked
                             if abs(abs(p.normal.dot(face.normal)) - 1.0) < 1e-3]
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


def bookshelf_audit(me):
    parts = classify(me)
    out = {k: len(v) for k, v in parts.items()}
    sides = sorted(parts["side"], key=lambda r: r["c"].x)
    out["side_z"] = max((r["lo"].z for r in sides), default=99.0)

    # Every cross member is housed in both sides: bite past the inner face,
    # and clear of the far face.
    bite, far = 99.0, 99.0
    if len(sides) == 2:
        left_in, left_out = sides[0]["hi"].x, sides[0]["lo"].x
        right_in, right_out = sides[1]["lo"].x, sides[1]["hi"].x
        for r in parts["cross"]:
            bite = min(bite, left_in - r["lo"].x, r["hi"].x - right_in)
            far = min(far, r["lo"].x - left_out, right_out - r["hi"].x)
    out["dado"], out["dado_far"] = bite, far

    # Books: each cover with the page block and bands nearest it.
    covers = parts["cover"]
    trees = [shell_tree(me, [c["g"]]) for c in covers]
    units = [{"cover": c, "tree": t, "pages": [], "band": []} for c, t in zip(covers, trees)]
    for kind in ("pages", "band"):
        for r in parts[kind]:
            # The cover every vertex of the part sits closest to, on average:
            # a page block's corners are in its own boards, a band on its own
            # spine. A centroid alone is nearer a neighbour's board in a stack.
            if units:
                u = min(units, key=lambda u: sum(u["tree"].find_nearest(p)[3]
                                                 for p in r["pts"]) / len(r["pts"]))
                u[kind].append(r)
    out["units"] = len(units)
    out["unmatched"] = sum(1 for u in units if len(u["pages"]) != 1 or len(u["band"]) != 2)

    # Pages glued in: every page-block corner inside the cover's boards.
    page_d = [depth_in(u["tree"], p) for u in units for r in u["pages"] for p in r["pts"]]
    out["page_bite"] = (min(page_d, default=-99.0), max(page_d, default=99.0))

    # Bands on the spine: inner face inside the cover, outer face proud.
    b_in, b_out = [], []
    for u in units:
        for r in u["band"]:
            ds = sorted(depth_in(u["tree"], p) for p in r["pts"])
            half = len(ds) // 2
            b_in.extend(ds[half:])
            b_out.append(-max(ds[:half]))
    out["band_bite"] = (min(b_in, default=-99.0), max(b_in, default=99.0))
    out["band_proud"] = min(b_out, default=-99.0)

    # Pose of each book from its largest face, a board: upright, lying or leaning.
    for u in units:
        c = u["cover"]
        n = c["n"]
        tilt = math.asin(min(1.0, abs(n.z)))
        c["pose"] = ("up" if tilt <= UPRIGHT_TILT_MAX else
                     "lying" if tilt >= LYING_TILT_MIN else "lean")
        c["tilt"] = tilt
        ds = [p.dot(n) for p in c["pts"]]
        c["thick"] = max(ds) - min(ds)
    out["n_lean"] = sum(1 for u in units if u["cover"]["pose"] == "lean")
    out["n_lying"] = sum(1 for u in units if u["cover"]["pose"] == "lying")

    # Seat: what each book stands on is the highest shelf or cover under its
    # footprint whose top is within reach of its lowest point.
    shelves = [r for r in parts["cross"] if r["ext"].y > 0.15]
    horizontals = shelves + parts["top"]
    seats = []
    for u in units:
        c = u["cover"]
        cands = [r for r in shelves + covers if r is not c and overlaps_xy(r, c)
                 and c["lo"].z - 0.02 <= r["hi"].z <= c["lo"].z + 0.01]
        if cands:
            u["support"] = max(cands, key=lambda r: r["hi"].z)
            seats.append(u["support"]["hi"].z - c["lo"].z)
    out["seat"] = (min(seats, default=-99.0), max(seats, default=99.0))
    out["n_seated"] = len(seats)

    # Headroom: the top of each book (bands included) under the member above.
    heads = []
    for u in units:
        c = u["cover"]
        top = max([c["hi"].z] + [r["hi"].z for r in u["band"]])
        above = [h for h in horizontals if h["lo"].z > c["lo"].z + 0.05]
        if above:
            heads.append(min(h["lo"].z for h in above) - top)
    out["headroom"] = min(heads, default=-99.0)

    # Size spread: thickness across the boards, height along the board face.
    th = [u["cover"]["thick"] for u in units]
    hs = [u["cover"]["face_len"] for u in units]
    out["thick_spread"] = max(th) / min(th) if th else 0.0
    out["height_spread"] = max(hs) / min(hs) if hs else 0.0

    # Lean contact: the neighbour's head edge in the leaning board, as a band.
    leans = []
    for u in units:
        c = u["cover"]
        if c["pose"] != "lean":
            continue
        n = c["n"] if c["n"].x > 0 else -c["n"]
        up_x = -n.z  # the board's up direction, in the XZ plane, has this x
        side = 1.0 if up_x > 0 else -1.0
        sup = u.get("support")
        mates = [v for v in units if v["cover"]["pose"] == "up" and v.get("support") is sup
                 and (v["cover"]["c"].x - c["c"].x) * side > 0]
        if not mates:
            leans.append(-99.0)
            continue
        mate = min(mates, key=lambda v: abs(v["cover"]["c"].x - c["c"].x))
        u["lean_on"] = mate
        # Depth past the plane of the leaning board's outer face, read off the
        # mesh, over the neighbour's vertices near that board. A plane, not
        # the cover solid: the board is 2.8 mm thick, and a head edge driven
        # right through it is in the hollow, outside the cover again.
        to_mate = mate["cover"]["c"] - c["c"]
        facing = [b for b in c["boards"] if b[1].dot(to_mate) > 0.0]
        if not facing:
            leans.append(-99.0)
            continue
        p0, n = max(facing, key=lambda b: b[0].dot(b[1]))
        ds = [-(p - p0).dot(n) for p in mate["cover"]["pts"]
              if u["tree"].find_nearest(p, LEAN_SEARCH)[0] is not None]
        leans.append(max(ds, default=-99.0))
    out["lean"] = (min(leans, default=-99.0), max(leans, default=99.0))

    # Books do not run into one another, nor into the carcass, except where
    # they are meant to: a book on the one it is stacked on, a leaning book
    # on its neighbour, a book in the shelf it stands on.
    utrees = [shell_tree(me, [u["cover"]["g"]] + [r["g"] for r in u["pages"] + u["band"]])
              for u in units]
    carcass = [r for k in ("side", "back", "cross", "top", "cornice") for r in parts[k]]
    ctrees = [shell_tree(me, [r["g"]]) for r in carcass]
    designed = set()
    for i, u in enumerate(units):
        for j, v in enumerate(units):
            if u.get("support") is v["cover"] or u.get("lean_on") is v:
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
            if r is units[i].get("support"):
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
    """One convex hull over the carcass; the books sit inside it."""
    me = obj.data
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    pts = [me.vertices[i].co.copy() for i in range(len(me.vertices)) if mats.get(i) == WOOD_IDX]
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
    img = bpy.data.images.new("BookshelfNrm", size, size, alpha=True, float_buffer=False)
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
    low = build_bookshelf_mesh("BookshelfLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_bookshelf_mesh("BookshelfHigh", **hi_flags)
    mats = bookshelf_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("bookshelf mesh did not build, or has no UV layer", 3),) + nothing

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

    lod1 = make_lod(low, "BookshelfLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BookshelfLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(high, "BookshelfCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_bookshelf_{os.getpid()}.glb")
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
    sa = bookshelf_audit(low.data)
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
    print(f"measured parts sides={sa['side']} top={sa['top']} cornice={sa['cornice']} "
          f"back={sa['back']} cross={sa['cross']} covers={sa['cover']} pages={sa['pages']} "
          f"bands={sa['band']} other={sa['other']} unmatched={sa['unmatched']} "
          f"lean={sa['n_lean']} lying={sa['n_lying']} side_z={sa['side_z']:.5f}")
    print(f"measured joints dado={sa['dado']:.5f} dado_far={sa['dado_far']:.5f} "
          f"page_bite=({sa['page_bite'][0]:.5f},{sa['page_bite'][1]:.5f})")
    print(f"measured seats book=({sa['seat'][0]:.5f},{sa['seat'][1]:.5f}) n={sa['n_seated']} "
          f"band_bite=({sa['band_bite'][0]:.5f},{sa['band_bite'][1]:.5f}) "
          f"band_proud={sa['band_proud']:.5f}")
    print(f"measured headroom={sa['headroom']:.5f} thick_spread={sa['thick_spread']:.3f} "
          f"height_spread={sa['height_spread']:.3f} "
          f"lean=({sa['lean'][0]:.5f},{sa['lean'][1]:.5f}) book_hits={sa['book_hits']} "
          f"right_angle_wood={right}")

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
    if sa["side"] != 2 or sa["side_z"] > SIDE_Z_MAX:
        return (fail(f"sides: {sa['side']} of 2, worst side z={sa['side_z']:.5f} > {SIDE_Z_MAX} "
                     "(--float-side is the designed fail)", 16),) + nothing
    if sa["cross"] != N_CROSS or sa["dado"] < DADO_MIN or sa["dado_far"] < DADO_FAR_MIN:
        return (fail(f"{sa['cross']} of {N_CROSS} cross members, dado bite {sa['dado']:.5f} "
                     f"(min {DADO_MIN}), far face {sa['dado_far']:.5f} (min {DADO_FAR_MIN}) "
                     "(--short-shelves is the designed fail)", 17),) + nothing
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
    if sa["headroom"] < HEADROOM_MIN:
        return (fail(f"headroom {sa['headroom']:.5f} < {HEADROOM_MIN} "
                     "(--tall-book is the designed fail)", 20),) + nothing
    if sa["thick_spread"] < THICK_SPREAD_MIN or sa["height_spread"] < HEIGHT_SPREAD_MIN:
        return (fail(f"book spread thickness {sa['thick_spread']:.3f} (min {THICK_SPREAD_MIN}), "
                     f"height {sa['height_spread']:.3f} (min {HEIGHT_SPREAD_MIN}) "
                     "(--uniform-books is the designed fail)", 21),) + nothing
    if (sa["n_lean"] != N_LEAN or sa["n_lying"] != N_LYING
            or sa["lean"][0] < LEAN_BITE_MIN or sa["lean"][1] > LEAN_BITE_MAX):
        return (fail(f"{sa['n_lean']} of {N_LEAN} leaning and {sa['n_lying']} of {N_LYING} lying "
                     f"books, lean contact {sa['lean']} outside [{LEAN_BITE_MIN}, {LEAN_BITE_MAX}] "
                     "(--air-lean and --deep-lean are the designed fails)", 22),) + nothing
    if sa["book_hits"]:
        return (fail(f"{sa['book_hits']} book overlaps, need 0 "
                     "(--crowd-books is the designed fail)", 23),) + nothing
    if right:
        return (fail(f"{right} right-angle wood edges, need 0 "
                     "(--sharp-shelf is the designed fail)", 24),) + nothing
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
    low.rotation_euler.z = math.radians(-14.0)

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
    cam.location = (1.27, -3.74, 1.175)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.565)
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
    p.add_argument("--float-side", action="store_true")
    p.add_argument("--short-shelves", action="store_true")
    p.add_argument("--loose-pages", action="store_true")
    p.add_argument("--float-books", action="store_true")
    p.add_argument("--float-bands", action="store_true")
    p.add_argument("--tall-book", action="store_true")
    p.add_argument("--uniform-books", action="store_true")
    p.add_argument("--air-lean", action="store_true")
    p.add_argument("--deep-lean", action="store_true")
    p.add_argument("--crowd-books", action="store_true")
    p.add_argument("--sharp-shelf", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_side=args.float_side,
        short_shelves=args.short_shelves,
        sharp_shelf=args.sharp_shelf,
        loose_pages=args.loose_pages,
        float_books=args.float_books,
        float_bands=args.float_bands,
        tall_book=args.tall_book,
        uniform_books=args.uniform_books,
        crowd_books=args.crowd_books,
        air_lean=args.air_lean,
        deep_lean=args.deep_lean,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("bookshelf OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
