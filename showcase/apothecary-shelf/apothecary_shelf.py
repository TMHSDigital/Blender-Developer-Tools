"""Game-ready apothecary shelf — a showcase piece, not an example.

Asserts budget conformance of a procedural apothecary shelf: a stained
carcass with housed shelves, gallery rails, a bank of three drawers and a
crest board, stocked with fifteen turned and blown vessels in five forms
(bottle, flask, jar, albarello, vial), each closed by a cork or a lid and
carrying a paper label. Carried through UVs, six materials (wood, glass,
glaze, cork, paper, brass), a high-to-low normal bake, an LOD chain, a
convex collider, and a Unity glTF export.

The budget that matters here is the one a stocked shelf fails invisibly:
every vessel has to fit between its shelf and the one above it. A flask a
few centimetres too tall runs its neck up into the next shelf, and the
bounding box, the triangle count and every seat budget still pass,
because the flask stands where it should and the shelf above it is still
in its dado. The piece reads each vessel's top and the underside of the
member above it off the finished mesh and asserts a headroom floor.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-side`` the named sides,
``--short-shelves`` the dado bite, ``--pop-corks`` the closure bite,
``--pull-knobs`` the knob bite, ``--float-jars`` the vessel seat,
``--lift-drawers`` the drawer seat, ``--float-labels`` the label seat,
``--tall-flask`` the headroom, ``--crowd-jars`` vessel interpenetration,
``--uniform-vessels`` the size spread, ``--sharp-rail`` edge treatment.

No randomness: every vessel's form, size, yaw, tint and seat is a
closed-form term of its index. DECIMATE COLLAPSE triangle counts are not
byte-identical across Blender versions — the LOD gate is a ratio band.

    blender --background --python apothecary_shelf.py --
    blender --background --python apothecary_shelf.py -- --tall-flask
    blender --background --python apothecary_shelf.py -- --output apothecary_shelf.png
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
W_OUT = 0.840
SIDE_T = 0.022
DEPTH = 0.250
SIDE_H = 1.000
DADO = 0.008
TOP_T = 0.024
TOP_SEAT = 0.006
TOP_OVER = 0.018
TOP_BACK_OVER = 0.006
CREST_H = 0.058
CREST_SHOULDER = 0.028
CREST_ARC = 12
CREST_T = 0.018
CREST_BITE = 0.004
BACK_T = 0.012
BACK_INSET = 0.010
BACK_BITE = 0.005
N_BACK = 4
BACK_LAP = 0.002
BACK_STEP = 0.0015
SHELF_T = 0.020
SHELF_SETBACK = 0.004
SHELF_TOPS = (0.175, 0.455, 0.735)
RAIL_H = 0.028
RAIL_T = 0.010
RAIL_INSET = 0.010
RAIL_BITE = 0.002
BASE_Z = 0.030
BASE_T = 0.018
BASE_SETBACK = 0.012
N_DRAWERS = 3
DRAWER_T = 0.018
DRAWER_SETBACK = 0.002
DRAWER_GAP = 0.004
DRAWER_BITE = 0.002
KNOB_BITE = 0.004
KNOB_LEN = 0.022
CHAMFER = 0.0025

# Vessels: a closed lathe body (twelve rings between two poles), a closure
# (cork or lid, five rings), and a paper label wrapped on the body's own
# rings. Every form has the same ring counts, so a vessel costs the same
# triangles whatever its form, and swapping forms moves no triangle budget.
SEG = 16
LABEL_COLS = 4
LABEL_BITE = 0.0003
LABEL_PROUD = 0.0008
FLOAT_LABEL = 0.0011
CLOSURE_BITE = 0.005
POP_CORK = 0.010
SEAT_BASE = 0.0010
SEAT_STEP = 0.0002
FLOAT_JARS = 0.006
LIFT_DRAWERS = 0.003
PULL_KNOBS = 0.008
FLOAT_SIDE = 0.005
TALL_FLASK = 1.20
CROWD = 0.55
VESSEL_CLEAR = 0.006
UNIFORM_R = 0.030
UNIFORM_H = 0.150

# (form, glass or glaze) per shelf, left to right.
LAYOUT = (
    ("jar", "albarello", "flask", "albarello", "jar"),
    ("bottle", "albarello", "vial", "bottle", "flask"),
    ("vial", "bottle", "vial", "flask", "bottle"),
)
FORMS = {
    # radius, body height, material, closure
    "bottle": (0.034, 0.200, "glass", "cork"),
    "flask": (0.050, 0.210, "glass", "cork"),
    "jar": (0.055, 0.130, "glaze", "lid"),
    "albarello": (0.048, 0.170, "glaze", "lid"),
    "vial": (0.018, 0.100, "glass", "cork"),
}
GLASS_TINTS = ((0.42, 0.17, 0.03), (0.14, 0.30, 0.11), (0.08, 0.14, 0.36), (0.22, 0.09, 0.26))
GLAZE_TINTS = ((0.74, 0.68, 0.54), (0.34, 0.44, 0.60), (0.36, 0.20, 0.10))

BBOX_TOL = 0.020
OUTER_SIZE = (0.876, 0.274, 1.076)

BASE_TRIS_MIN = 9800
BASE_TRIS_MAX = 11100
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 6
FACE_FLOORS = {0: 450, 1: 1800, 2: 1300, 3: 850, 4: 380, 5: 300}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 200
BAKE_RES = 512
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
CLOSURE_BITE_MIN = 0.002
CLOSURE_BITE_MAX = 0.010
KNOB_BITE_MIN = 0.002
KNOB_BITE_MAX = 0.010
SEAT_MIN = 0.0005
SEAT_MAX = 0.0030
DRAWER_SEAT_MIN = 0.001
DRAWER_SEAT_MAX = 0.004
LABEL_BITE_MIN = 0.0001
LABEL_BITE_MAX = 0.0008
LABEL_PROUD_MIN = 0.0004
HEADROOM_MIN = 0.020
DIAM_SPREAD_MIN = 2.0
HEIGHT_SPREAD_MIN = 1.5
RIGHT_ANGLE_TOL = math.radians(5.0)

WOOD_IDX = 0
GLASS_IDX = 1
GLAZE_IDX = 2
CORK_IDX = 3
PAPER_IDX = 4
BRASS_IDX = 5
N_CROSS = len(SHELF_TOPS) * 2 + 1


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


# --- profiles ---------------------------------------------------------------


def body_profile(form, r, h):
    """(r, z) from the bottom pole to the top pole: exactly twelve rings.

    Every foot is chamfered, so no body meets the shelf on a right angle.
    Returns the profile, the label's ring range and the mouth radius.
    """
    c = 0.003
    if form == "bottle":
        n = 0.012
        rings = [(r - c, 0.0), (r, c), (r, 0.25 * h), (r, 0.45 * h), (r, 0.65 * h),
                 (r * 0.96, 0.72 * h), (r * 0.78, 0.80 * h), (r * 0.45, 0.86 * h),
                 (n, 0.90 * h), (n, 0.96 * h), (n + 0.0035, 0.965 * h), (n + 0.0035, h)]
        label, mouth = (3, 5), n
    elif form == "flask":
        n = 0.011
        rings = [(r * 0.55, 0.0), (r * 0.62, 0.004), (r * 0.86, 0.06 * h), (r * 0.98, 0.14 * h),
                 (r, 0.24 * h), (r * 0.95, 0.34 * h), (r * 0.75, 0.44 * h), (r * 0.40, 0.51 * h),
                 (n, 0.56 * h), (n, 0.93 * h), (n + 0.003, 0.94 * h), (n + 0.003, h)]
        label, mouth = (4, 6), n
    elif form == "jar":
        rings = [(r - c, 0.0), (r, c), (r, 0.20 * h), (r, 0.45 * h), (r, 0.70 * h),
                 (r * 0.99, 0.80 * h), (r * 0.93, 0.86 * h), (r * 0.86, 0.90 * h),
                 (r * 0.84, 0.94 * h), (r * 0.88, 0.955 * h), (r * 0.88, h - 0.002),
                 (r * 0.86, h)]
        label, mouth = (3, 5), r * 0.88
    elif form == "albarello":
        rings = [(r - c, 0.0), (r, c), (r, 0.10 * h), (r * 0.90, 0.22 * h), (r * 0.86, 0.45 * h),
                 (r * 0.90, 0.68 * h), (r, 0.80 * h), (r * 0.96, 0.87 * h), (r * 0.80, 0.91 * h),
                 (r * 0.76, 0.95 * h), (r * 0.80, 0.96 * h), (r * 0.80, h)]
        label, mouth = (4, 6), r * 0.80
    else:  # vial
        n = 0.009
        c = 0.0018
        rings = [(r - c, 0.0), (r, c), (r, 0.20 * h), (r, 0.45 * h), (r, 0.70 * h),
                 (r * 0.96, 0.80 * h), (r * 0.80, 0.85 * h), (r * 0.62, 0.88 * h),
                 (n, 0.90 * h), (n, 0.96 * h), (n + 0.002, 0.965 * h), (n + 0.002, h)]
        label, mouth = (3, 5), n
    prof = [Vector((0.0, 0.0))] + [Vector(p) for p in rings] + [Vector((0.0, h))]
    return prof, label, mouth


def closure_profile(kind, mouth):
    """(r, z) from the closure's own bottom: five rings between two poles.

    A cork is narrower than the mouth and flares above it; a lid is wider
    than the rim, a skirt, a dome and a knob.
    """
    if kind == "cork":
        rc, ln = mouth - 0.001, 0.022 if mouth > 0.010 else 0.016
        # The flare stops short of the neck's own radius: a cork wall on the
        # neck's cylinder is a coplanar pair with it.
        rings = [(rc, 0.0), (rc * 1.06, 0.5 * ln), (rc * 1.20, 0.8 * ln),
                 (rc * 1.20, ln - 0.002), (rc * 1.08, ln)]
        top = ln
    else:
        rl = mouth + 0.004
        rings = [(rl, 0.0), (rl, 0.010), (rl * 0.80, 0.019), (0.012, 0.024), (0.014, 0.034)]
        top = 0.036
    return [Vector((0.0, 0.0))] + [Vector(p) for p in rings] + [Vector((0.0, top))]


def knob_profile():
    """(r, t) along the knob axis, from the end buried in the drawer front."""
    rings = [(0.005, 0.0), (0.005, 0.009), (0.004, 0.011), (0.010, 0.016), (0.011, 0.019),
             (0.009, 0.0215)]
    return [Vector((0.0, 0.0))] + [Vector(p) for p in rings] + [Vector((0.0, KNOB_LEN))]


# --- construction -----------------------------------------------------------


def new_island(ctx):
    ctx["next"] += 1
    return ctx["next"]


def stamp(ctx, face, island, uvmap):
    face[ctx["isl"]] = island
    for loop in face.loops:
        loop[ctx["uv"]].uv = uvmap[loop.vert]


def lathe(bm, profile, n, mat_idx, ctx, xf, phase=0.0, piece=0):
    """Revolve an (r, z) profile about local Z, placed by ``xf``.

    r == 0 at either end makes a pole. One strip island. Returns the
    rings (a vertex or a list of n vertices per profile point).
    """
    island = new_island(ctx)
    s = [0.0]
    for a, b in zip(profile, profile[1:]):
        s.append(s[-1] + (b - a).length)
    rings = []
    for p in profile:
        if p.x <= 0.0:
            rings.append(bm.verts.new(xf @ Vector((0.0, 0.0, p.y))))
            continue
        rings.append([bm.verts.new(xf @ Vector((p.x * math.cos(phase + 2 * math.pi * k / n),
                                                 p.x * math.sin(phase + 2 * math.pi * k / n),
                                                 p.y)))
                      for k in range(n)])
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            if isinstance(a, list) and isinstance(b, list):
                vs = (a[i], a[j], b[j], b[i])
                uv = {a[i]: (s[k], i / n), a[j]: (s[k], (i + 1) / n),
                      b[j]: (s[k + 1], (i + 1) / n), b[i]: (s[k + 1], i / n)}
            elif isinstance(b, list):
                vs = (a, b[j], b[i])
                uv = {a: (s[k], (i + 0.5) / n), b[j]: (s[k + 1], (i + 1) / n),
                      b[i]: (s[k + 1], i / n)}
            else:
                vs = (a[i], a[j], b)
                uv = {a[i]: (s[k], i / n), a[j]: (s[k], (i + 1) / n),
                      b: (s[k + 1], (i + 0.5) / n)}
            f = bm.faces.new(vs)
            f.material_index = mat_idx
            f[ctx["piece"]] = piece
            stamp(ctx, f, island, uv)
    return rings


def add_label(bm, profile, rings, n, phase, xf, ctx, piece, float_label=False):
    """A paper label on the body's own rings ``rings[0]..rings[1]``.

    Built on the host's arc with the host's segment count: every label
    vertex sits at a body vertex's angle and height, so the paper follows
    the body exactly, including a waist or a bulb. Inner face LABEL_BITE
    inside the body, outer face LABEL_PROUD outside it.
    """
    r0, r1 = rings
    inner_off = FLOAT_LABEL if float_label else -LABEL_BITE
    outer_off = inner_off + LABEL_BITE + LABEL_PROUD
    grid = {}
    for j in range(r0, r1 + 1):
        p = profile[j]
        for i in range(LABEL_COLS + 1):
            a = phase + 2 * math.pi * i / n
            for side, off in (("in", inner_off), ("out", outer_off)):
                rr = p.x + off
                grid[(j, i, side)] = bm.verts.new(
                    xf @ Vector((rr * math.cos(a), rr * math.sin(a), p.y)))
    quads = []
    for j in range(r0, r1):
        for i in range(LABEL_COLS):
            quads.append((grid[(j, i, "out")], grid[(j, i + 1, "out")],
                          grid[(j + 1, i + 1, "out")], grid[(j + 1, i, "out")]))
            quads.append((grid[(j + 1, i, "in")], grid[(j + 1, i + 1, "in")],
                          grid[(j, i + 1, "in")], grid[(j, i, "in")]))
    for i in range(LABEL_COLS):
        quads.append((grid[(r0, i, "in")], grid[(r0, i + 1, "in")],
                      grid[(r0, i + 1, "out")], grid[(r0, i, "out")]))
        quads.append((grid[(r1, i, "out")], grid[(r1, i + 1, "out")],
                      grid[(r1, i + 1, "in")], grid[(r1, i, "in")]))
    for j in range(r0, r1):
        quads.append((grid[(j, 0, "in")], grid[(j, 0, "out")],
                      grid[(j + 1, 0, "out")], grid[(j + 1, 0, "in")]))
        e = LABEL_COLS
        quads.append((grid[(j + 1, e, "in")], grid[(j + 1, e, "out")],
                      grid[(j, e, "out")], grid[(j, e, "in")]))
    for vs in quads:
        f = bm.faces.new(vs)
        f.material_index = PAPER_IDX
        f[ctx["piece"]] = piece


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


def add_crest(bm, a, y0, y1, z0, z_side, z_top, boards):
    """The crest: a board whose top is a shallow arc, extruded through Y.

    Both caps are single n-gons, chamfered with the rest and triangulated
    afterwards, so the shipped mesh has no n-gon.
    """
    sag = z_top - z_side
    rad = (a * a + sag * sag) / (2.0 * sag)
    zc = z_top - rad
    phi0 = math.asin(a / rad)
    outline = [(-a, z0), (a, z0)]
    for k in range(CREST_ARC + 1):
        phi = phi0 - 2.0 * phi0 * k / CREST_ARC
        outline.append((rad * math.sin(phi), zc + rad * math.cos(phi)))
    front = [bm.verts.new((x, y0, z)) for x, z in outline]
    back = [bm.verts.new((x, y1, z)) for x, z in outline]
    faces = [bm.faces.new(front), bm.faces.new(list(reversed(back)))]
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((front[j], front[i], back[i], back[j])))
    for f in faces:
        f.material_index = WOOD_IDX
    boards.extend(front + back)


def vessel_plan(uniform=False, crowd=False):
    """Every vessel: shelf, form, radius, height, centre, yaw and seat.

    Closed-form throughout. Each shelf's vessels share out the clear width
    between the sides evenly, and step front and back alternately inside
    the depth left between the rail and the back boards.
    """
    x_in = W_OUT / 2.0 - SIDE_T
    y_front = -DEPTH / 2.0 + RAIL_INSET + RAIL_T
    y_back = DEPTH / 2.0 - BACK_INSET - BACK_T - BACK_STEP
    out = []
    idx = 0
    for s, row in enumerate(LAYOUT):
        sizes = []
        for k, form in enumerate(row):
            r, h, _m, _c = FORMS[form]
            jr = 1.0 + 0.10 * (frac((idx + k) * 0.6180339887 + 0.21) - 0.5)
            jh = 1.0 + 0.10 * (frac((idx + k) * 0.4142135624 + 0.57) - 0.5)
            if uniform:
                r, h, jr, jh = UNIFORM_R, UNIFORM_H, 1.0, 1.0
            sizes.append((form, r * jr, h * jh))
        free = 2.0 * x_in - sum(2.0 * sz[1] for sz in sizes)
        gap = free / (len(sizes) + 1)
        x = -x_in + gap
        for k, (form, r, h) in enumerate(sizes):
            cx = x + r
            x += 2.0 * r + gap
            if crowd and s == 0:
                cx *= CROWD
            lo_y, hi_y = y_front + r + VESSEL_CLEAR, y_back - r - VESSEL_CLEAR
            mid, half = (lo_y + hi_y) * 0.5, (hi_y - lo_y) * 0.5
            cy = mid + half * (0.55 if k % 2 else -0.45)
            yaw = math.radians(18.0) * (frac(idx * 0.7548776662 + 0.1) - 0.5)
            seat = SEAT_BASE + SEAT_STEP * k
            out.append({"i": idx, "shelf": s, "form": form, "r": r, "h": h,
                        "c": (cx, cy), "yaw": yaw, "seat": seat})
            idx += 1
    return out


def build_shelf_mesh(
    name,
    stray_vert=False,
    float_side=False,
    short_shelves=False,
    pop_corks=False,
    pull_knobs=False,
    float_jars=False,
    lift_drawers=False,
    float_labels=False,
    tall_flask=False,
    crowd_jars=False,
    uniform_vessels=False,
    sharp_rail=False,
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
        ctx = {"uv": bm.loops.layers.uv.new("UVMap"),
               "isl": bm.faces.layers.int.new("UVIsland"),
               "piece": bm.faces.layers.int.new("Piece"), "next": 0}
        boards = []
        # Sides: the two named supports.
        for sx in (-1.0, 1.0):
            lift = FLOAT_SIDE if (float_side and sx < 0) else 0.0
            add_board(bm, (min(sx * x_out, sx * x_in), y0, lift),
                      (max(sx * x_out, sx * x_in), y1, SIDE_H + lift), boards)
        add_board(bm, (-x_out - TOP_OVER, y0 - TOP_OVER, top_z0),
                  (x_out + TOP_OVER, y1 + TOP_BACK_OVER, top_z1), boards)
        add_crest(bm, x_in, back_y0 - CREST_T - 0.004, back_y0 - 0.004,
                  top_z1 - CREST_BITE, top_z1 + CREST_SHOULDER, top_z1 + CREST_H, boards)
        # Back boards, housed into the sides and the top, standing on the
        # base. Lapped, not butted: a seam left open shows daylight through
        # the back, and a lap on one plane is a coplanar pair, so every other
        # board steps forward by BACK_STEP.
        span0, span1 = -x_in - BACK_BITE, x_in + BACK_BITE
        bw = (span1 - span0 + BACK_LAP * (N_BACK - 1)) / N_BACK
        for k in range(N_BACK):
            bx = span0 + k * (bw - BACK_LAP)
            step = BACK_STEP if k % 2 else 0.0
            add_board(bm, (bx, back_y0 - step, BASE_Z + BASE_T - BACK_BITE),
                      (bx + bw, back_y1 - step, top_z0 + BACK_BITE), boards)
        # Cross members: base, shelves and rails, each in a dado in both sides.
        reach = x_in - 0.004 if short_shelves else x_in + DADO
        add_board(bm, (-(x_in + DADO), y0 + BASE_SETBACK, BASE_Z),
                  (x_in + DADO, back_y0 + BACK_BITE, BASE_Z + BASE_T), boards)
        for s, zt in enumerate(SHELF_TOPS):
            add_board(bm, (-reach, y0 + SHELF_SETBACK, zt - SHELF_T),
                      (reach, back_y0 + BACK_BITE, zt), boards)
            add_board(bm, (-(x_in + DADO), y0 + RAIL_INSET, zt - RAIL_BITE),
                      (x_in + DADO, y0 + RAIL_INSET + RAIL_T, zt + RAIL_H - RAIL_BITE),
                      boards, sharp=(sharp_rail and s == len(SHELF_TOPS) - 1))
        # Drawer bank: three fronts standing in the base, a knob in each.
        dz0 = BASE_Z + BASE_T - DRAWER_BITE + (LIFT_DRAWERS if lift_drawers else 0.0)
        dz1 = SHELF_TOPS[0] - SHELF_T - DRAWER_GAP + (LIFT_DRAWERS if lift_drawers else 0.0)
        dw = (2.0 * x_in - DRAWER_GAP * (N_DRAWERS + 1)) / N_DRAWERS
        dy0 = y0 + DRAWER_SETBACK
        knobs = []
        for k in range(N_DRAWERS):
            dx = -x_in + DRAWER_GAP + k * (dw + DRAWER_GAP)
            add_board(bm, (dx, dy0, dz0), (dx + dw, dy0 + DRAWER_T, dz1), boards)
            knobs.append((dx + dw * 0.5, (dz0 + dz1) * 0.5))
        # A set of BMEdges iterates in address order: sort by index so the
        # bevel emits its faces in the same order on every run.
        bm.edges.index_update()
        # The crest's arc strips meet at a few degrees; only real edges chamfer.
        edges = sorted({e for v in boards for e in v.link_edges
                        if e.calc_face_angle(0.0) > math.radians(20.0)}, key=lambda e: e.index)
        bmesh.ops.bevel(bm, geom=edges, offset=CHAMFER, segments=1, profile=0.5,
                        affect="EDGES", clamp_overlap=True, material=WOOD_IDX)
        # Chamfer n-gon caps, then triangulate.
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
        for kx, kz in knobs:
            ky = dy0 + KNOB_BITE - (PULL_KNOBS if pull_knobs else 0.0)
            xf = Matrix.Translation((kx, ky, kz)) @ Matrix.Rotation(math.pi / 2.0, 4, "X")
            lathe(bm, knob_profile(), SEG, BRASS_IDX, ctx, xf)
        for v in vessel_plan(uniform=uniform_vessels, crowd=crowd_jars):
            form = v["form"]
            _r, _h, mat, kind = FORMS[form]
            prof, label, mouth = body_profile(form, v["r"], v["h"])
            z0 = SHELF_TOPS[v["shelf"]] - v["seat"] + (FLOAT_JARS if float_jars else 0.0)
            stretch = TALL_FLASK if (tall_flask and v["shelf"] == 1 and form == "flask") else 1.0
            xf = (Matrix.Translation((v["c"][0], v["c"][1], z0))
                  @ Matrix.Diagonal((1.0, 1.0, stretch, 1.0)))
            # Label centred on the front, turned by the vessel's yaw.
            phase = -math.pi / 2.0 + v["yaw"] - (LABEL_COLS / 2) * 2.0 * math.pi / SEG
            piece = v["i"] + 1
            midx = GLASS_IDX if mat == "glass" else GLAZE_IDX
            lathe(bm, prof, SEG, midx, ctx, xf, phase=phase, piece=piece)
            add_label(bm, prof, label, SEG, phase, xf, ctx, piece, float_label=float_labels)
            cz = prof[-1].y - CLOSURE_BITE + (POP_CORK if pop_corks else 0.0)
            cxf = xf @ Matrix.Translation((0.0, 0.0, cz))
            cmat = CORK_IDX if kind == "cork" else GLAZE_IDX
            lathe(bm, closure_profile(kind, mouth), SEG, cmat, ctx, cxf, phase=phase, piece=piece)
        if stray_vert:
            bm.verts.new((0.0, 0.0, 0.5))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(35.0):
                e.smooth = False
        pack_uvs(bm, ctx)
        bm.faces.layers.int.remove(ctx["isl"])
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    paint_pieces(me)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def pack_uvs(bm, ctx, margin=0.06):
    """One grid cell per UV island: strip islands by their layer tag, else a face each."""
    uv, isl = ctx["uv"], ctx["isl"]
    bm.faces.index_update()
    islands, order = {}, []
    for face in bm.faces:
        key = ("s", face[isl]) if face[isl] else ("f", face.index)
        if key not in islands:
            islands[key] = []
            order.append(key)
        islands[key].append(face)
    cols = max(1, math.ceil(math.sqrt(len(order))))
    rows = max(1, math.ceil(len(order) / cols))
    cw, ch = 1.0 / cols, 1.0 / rows
    pu, pv = margin * cw * 0.5, margin * ch * 0.5
    for idx, key in enumerate(order):
        faces = islands[key]
        coords = {}
        for face in faces:
            if face[isl]:
                coords[face.index] = [tuple(loop[uv].uv) for loop in face.loops]
                continue
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
            coords[face.index] = pts
        allc = [c for cs in coords.values() for c in cs]
        minx, maxx = min(c[0] for c in allc), max(c[0] for c in allc)
        miny, maxy = min(c[1] for c in allc), max(c[1] for c in allc)
        dx, dy = max(maxx - minx, 1e-8), max(maxy - miny, 1e-8)
        ou, ov = (idx % cols) * cw + pu, (idx // cols) * ch + pv
        for face in faces:
            for loop, (x, y) in zip(face.loops, coords[face.index]):
                loop[uv].uv = (ou + (x - minx) / dx * (cw - 2 * pu),
                               ov + (y - miny) / dy * (ch - 2 * pv))


def paint_pieces(me):
    """Face attributes the shaders read: per-board tone and grain, per-vessel tint.

    Every board gets a closed-form tone and the direction it runs in, its
    longest extent, so the grain follows the board. Every vessel gets a
    glass tint or a glaze from its index; the ``Piece`` tag is then dropped.
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
        if mats[fi] == GLASS_IDX:
            c = GLASS_TINTS[v % len(GLASS_TINTS)]
        else:
            c = GLAZE_TINTS[v % len(GLAZE_TINTS)]
        tint[fi] = (c[0], c[1], c[2], 1.0)
        tone[fi] = 0.5 + 0.3 * (frac(v * 0.4142135624) - 0.5)
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


def _input(bsdf, *names):
    for n in names:
        if n in bsdf.inputs:
            return bsdf.inputs[n]
    return None


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
    ramp.color_ramp.elements[0].color = (0.085, 0.036, 0.014, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.27, 0.125, 0.048, 1.0)
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


def glaze_material(name):
    """Glazed stoneware: the per-vessel ``Tint``, glossy, with a faint mottle."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Tint"
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 45.0
    noise.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    shade = nt.nodes.new("ShaderNodeMapRange")
    shade.inputs["To Min"].default_value = 0.86
    shade.inputs["To Max"].default_value = 1.0
    nt.links.new(noise.outputs["Fac"], shade.inputs["Value"])
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "SCALE"
    nt.links.new(attr.outputs["Color"], mul.inputs[0])
    nt.links.new(shade.outputs["Result"], mul.inputs["Scale"])
    nt.links.new(mul.outputs["Vector"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.28
    return mat


def glass_material(name):
    """Tinted glass, filled: dark through the middle, lighter at the silhouette.

    No transmission. EEVEE's transmission rendered every bottle as a grainy
    speckle that 256 samples did not clear, with or without raytracing, so
    the depth of the glass is carried by a facing ramp and a clear coat.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Tint"
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.45
    depth = nt.nodes.new("ShaderNodeMapRange")
    depth.inputs["To Min"].default_value = 0.30
    depth.inputs["To Max"].default_value = 0.95
    nt.links.new(lw.outputs["Facing"], depth.inputs["Value"])
    mul = nt.nodes.new("ShaderNodeVectorMath")
    mul.operation = "SCALE"
    nt.links.new(attr.outputs["Color"], mul.inputs[0])
    nt.links.new(depth.outputs["Result"], mul.inputs["Scale"])
    nt.links.new(mul.outputs["Vector"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.06
    coat = _input(bsdf, "Coat Weight", "Clearcoat")
    if coat is not None:
        coat.default_value = 1.0
    coat_r = _input(bsdf, "Coat Roughness", "Clearcoat Roughness")
    if coat_r is not None:
        coat_r.default_value = 0.03
    return mat


def paper_material(name):
    """Aged paper with ruled lines of ink broken into words by noise."""
    mat = speckled(name, (0.56, 0.49, 0.36), (0.78, 0.72, 0.58), 25.0, 0.9)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    paper = bsdf.inputs["Base Color"].links[0].from_socket
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
    lines = nt.nodes.new("ShaderNodeMath")
    lines.operation = "PINGPONG"
    lines.inputs[1].default_value = 0.0045
    nt.links.new(sep.outputs["Z"], lines.inputs[0])
    rule = nt.nodes.new("ShaderNodeMath")
    rule.operation = "LESS_THAN"
    rule.inputs[1].default_value = 0.0005
    nt.links.new(lines.outputs["Value"], rule.inputs[0])
    words = nt.nodes.new("ShaderNodeTexNoise")
    words.inputs["Scale"].default_value = 220.0
    words.inputs["Detail"].default_value = 1.0
    nt.links.new(tc.outputs["Object"], words.inputs["Vector"])
    gate = nt.nodes.new("ShaderNodeMath")
    gate.operation = "GREATER_THAN"
    gate.inputs[1].default_value = 0.50
    nt.links.new(words.outputs["Fac"], gate.inputs[0])
    ink = nt.nodes.new("ShaderNodeMath")
    ink.operation = "MULTIPLY"
    nt.links.new(rule.outputs["Value"], ink.inputs[0])
    nt.links.new(gate.outputs["Value"], ink.inputs[1])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(ink.outputs["Value"], _sock(mix.inputs, "Factor_Float"))
    nt.links.new(paper, _sock(mix.inputs, "A_Color"))
    _sock(mix.inputs, "B_Color").default_value = (0.26, 0.18, 0.12, 1.0)
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    return mat


def speckled(name, color_a, color_b, scale, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*color_a, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (*color_b, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def brass_material(name):
    """Aged brass: warm, a little dull, darker in the recesses of the noise."""
    mat = speckled(name, (0.30, 0.19, 0.07), (0.55, 0.39, 0.16), 60.0, 0.42)
    mat.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.9
    return mat


def shelf_materials():
    return (
        wood_material("ShelfWood"),
        glass_material("ShelfGlass"),
        glaze_material("ShelfGlaze"),
        speckled("ShelfCork", (0.30, 0.19, 0.10), (0.52, 0.37, 0.21), 90.0, 0.85),
        paper_material("ShelfPaper"),
        brass_material("ShelfBrass"),
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


def classify(me):
    """Split the finished mesh into named parts by material and shape."""
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    out = {k: [] for k in ("side", "top", "crest", "back", "cross", "drawer", "knob",
                           "body", "closure", "label", "other")}
    for g in shells(me):
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
                out["crest"].append(rec)
            elif hi.z > SIDE_H:
                out["top"].append(rec)
            elif ext.x > 0.7:
                out["cross"].append(rec)
            else:
                out["drawer"].append(rec)
        elif m == BRASS_IDX:
            out["knob"].append(rec)
        elif m == PAPER_IDX:
            out["label"].append(rec)
        elif m == CORK_IDX:
            out["closure"].append(rec)
        elif m in (GLASS_IDX, GLAZE_IDX):
            out["body" if ext.z > 0.06 else "closure"].append(rec)
        else:
            out["other"].append(rec)
    return out


def axis_of(rec):
    """A lathe's axis in plan: the mean of its vertices, exact for a full revolution."""
    return Vector((rec["c"].x, rec["c"].y))


def shelf_audit(me):
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

    # Vessels: each body with its closure and label, by nearest axis.
    bodies = parts["body"]
    units = [{"body": b, "closure": [], "label": []} for b in bodies]
    for kind in ("closure", "label"):
        for r in parts[kind]:
            if not units:
                break
            # Nearest axis in plan among the bodies at this part's height:
            # the shelves stack vessels in the same plan positions.
            p = Vector((r["c"].x, r["c"].y))
            level = [u for u in units
                     if u["body"]["lo"].z <= r["c"].z <= u["body"]["hi"].z + 0.06]
            if level:
                u = min(level, key=lambda u: (axis_of(u["body"]) - p).length)
                u[kind].append(r)
    out["units"] = len(units)
    out["unmatched"] = sum(1 for u in units if len(u["closure"]) != 1 or len(u["label"]) != 1)

    shelves = [r for r in parts["cross"] if r["ext"].y > 0.15]
    horizontals = shelves + parts["top"]
    closure_bites, seats, heads = [], [], []
    for u in units:
        b = u["body"]
        for c in u["closure"]:
            closure_bites.append(b["hi"].z - c["lo"].z)
        under = [s for s in shelves if s["hi"].z <= b["lo"].z + 0.01]
        if under:
            s = max(under, key=lambda s: s["hi"].z)
            u["shelf"] = s
            seats.append(s["hi"].z - b["lo"].z)
        top = max([b["hi"].z] + [c["hi"].z for c in u["closure"]])
        above = [h for h in horizontals if h["lo"].z > b["lo"].z + 0.05]
        if above:
            heads.append(min(h["lo"].z for h in above) - top)
    out["closure_bite"] = (min(closure_bites, default=-99.0), max(closure_bites, default=99.0))
    out["seat"] = (min(seats, default=-99.0), max(seats, default=99.0))
    out["headroom"] = min(heads, default=-99.0)
    out["n_seated"] = len(seats)

    # Labels on their bodies: each label vertex against the body vertex it
    # was built on, measured radially from the body's own axis.
    lab_in, lab_out = [], []
    for u in units:
        b = u["body"]
        kd = KDTree(len(b["pts"]))
        for k, p in enumerate(b["pts"]):
            kd.insert(p, k)
        kd.balance()
        ax = axis_of(b)
        for lab in u["label"]:
            # Positive is inside the body. Half the label's vertices are its
            # inner face and half its outer; sorting splits them without a
            # sign test, so a floated label's inner face still reads as inner.
            ds = []
            for p in lab["pts"]:
                q = kd.find(p)[0]
                ds.append((Vector((q.x, q.y)) - ax).length - (Vector((p.x, p.y)) - ax).length)
            ds.sort()
            half = len(ds) // 2
            lab_in.append(min(ds[half:]))
            lab_out.append(-max(ds[:half]))
    out["label_bite"] = (min(lab_in, default=-99.0), max(lab_in, default=99.0))
    out["label_proud"] = min(lab_out, default=-99.0)

    # Knobs bite their drawer fronts; drawer fronts stand in the base.
    base = min(parts["cross"], key=lambda r: r["lo"].z) if parts["cross"] else None
    knob_bites, drawer_seats = [], []
    for d in parts["drawer"]:
        if base is not None:
            drawer_seats.append(base["hi"].z - d["lo"].z)
        near = [k for k in parts["knob"] if d["lo"].x < k["c"].x < d["hi"].x]
        for k in near:
            knob_bites.append(k["hi"].y - d["lo"].y)
    out["knob_bite"] = (min(knob_bites, default=-99.0), max(knob_bites, default=99.0))
    out["n_knob_bites"] = len(knob_bites)
    out["drawer_seat"] = (min(drawer_seats, default=-99.0), max(drawer_seats, default=99.0))

    # Vessels do not run into one another, nor into the carcass beyond the
    # shelf each one stands in.
    trees = [shell_tree(me, [u["body"]["g"]] + [r["g"] for r in u["closure"] + u["label"]])
             for u in units]
    carcass = [r for k in ("side", "back", "cross", "top") for r in parts[k]]
    ctrees = [shell_tree(me, [r["g"]]) for r in carcass]
    hits = 0
    for i in range(len(trees)):
        for j in range(i + 1, len(trees)):
            if trees[i].overlap(trees[j]):
                hits += 1
        for r, ct in zip(carcass, ctrees):
            if r is units[i].get("shelf"):
                continue
            if trees[i].overlap(ct):
                hits += 1
    out["vessel_hits"] = hits

    # Forms vary: widest body over narrowest, tallest over shortest.
    # Diameter from the axis, not the AABB: a yawed 16-gon's box width
    # moves with the yaw.
    diams = [2.0 * max((Vector((p.x, p.y)) - axis_of(b)).length for p in b["pts"])
             for b in bodies]
    hts = [b["ext"].z for b in bodies]
    out["diam_spread"] = max(diams) / min(diams) if diams else 0.0
    out["height_spread"] = max(hts) / min(hts) if hts else 0.0
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
    """One convex hull over the carcass and the knobs; the vessels sit inside it."""
    me = obj.data
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    pts = [me.vertices[i].co.copy() for i in range(len(me.vertices))
           if mats.get(i) in (WOOD_IDX, BRASS_IDX)]
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
    img = bpy.data.images.new("ShelfNrm", size, size, alpha=True, float_buffer=False)
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
    low = build_shelf_mesh("ShelfLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_shelf_mesh("ShelfHigh", **hi_flags)
    mats = shelf_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("shelf mesh did not build, or has no UV layer", 3),) + nothing

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

    lod1 = make_lod(low, "ShelfLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "ShelfLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(high, "ShelfCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_apothecary_{os.getpid()}.glb")
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
    sa = shelf_audit(low.data)
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
    print(f"measured parts sides={sa['side']} top={sa['top']} crest={sa['crest']} "
          f"back={sa['back']} cross={sa['cross']} drawers={sa['drawer']} knobs={sa['knob']} "
          f"bodies={sa['body']} closures={sa['closure']} labels={sa['label']} "
          f"other={sa['other']} unmatched={sa['unmatched']} side_z={sa['side_z']:.5f}")
    print(f"measured joints dado={sa['dado']:.5f} dado_far={sa['dado_far']:.5f} "
          f"closure_bite=({sa['closure_bite'][0]:.5f},{sa['closure_bite'][1]:.5f}) "
          f"knob_bite=({sa['knob_bite'][0]:.5f},{sa['knob_bite'][1]:.5f})")
    print(f"measured seats vessel=({sa['seat'][0]:.5f},{sa['seat'][1]:.5f}) "
          f"n={sa['n_seated']} drawer=({sa['drawer_seat'][0]:.5f},{sa['drawer_seat'][1]:.5f}) "
          f"label_bite=({sa['label_bite'][0]:.5f},{sa['label_bite'][1]:.5f}) "
          f"label_proud={sa['label_proud']:.5f}")
    print(f"measured headroom={sa['headroom']:.5f} vessel_hits={sa['vessel_hits']} "
          f"diam_spread={sa['diam_spread']:.3f} height_spread={sa['height_spread']:.3f} "
          f"right_angle_wood={right}")

    n_vessels = sum(len(row) for row in LAYOUT)
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
    if (sa["units"] != n_vessels or sa["unmatched"]
            or not (CLOSURE_BITE_MIN <= sa["closure_bite"][0])
            or sa["closure_bite"][1] > CLOSURE_BITE_MAX):
        return (fail(f"{sa['units']} of {n_vessels} vessels, {sa['unmatched']} without one "
                     f"closure and one label, closure bite {sa['closure_bite']} outside "
                     f"[{CLOSURE_BITE_MIN}, {CLOSURE_BITE_MAX}] (--pop-corks is the designed fail)",
                     17),) + nothing
    if (sa["n_knob_bites"] != N_DRAWERS or sa["knob_bite"][0] < KNOB_BITE_MIN
            or sa["knob_bite"][1] > KNOB_BITE_MAX):
        return (fail(f"{sa['n_knob_bites']} of {N_DRAWERS} knobs, bite {sa['knob_bite']} outside "
                     f"[{KNOB_BITE_MIN}, {KNOB_BITE_MAX}] (--pull-knobs is the designed fail)",
                     17),) + nothing
    if sa["n_seated"] != n_vessels or sa["seat"][0] < SEAT_MIN or sa["seat"][1] > SEAT_MAX:
        return (fail(f"{sa['n_seated']} of {n_vessels} vessels on a shelf, seat {sa['seat']} "
                     f"outside [{SEAT_MIN}, {SEAT_MAX}] (--float-jars is the designed fail)",
                     18),) + nothing
    if (sa["drawer"] != N_DRAWERS or sa["drawer_seat"][0] < DRAWER_SEAT_MIN
            or sa["drawer_seat"][1] > DRAWER_SEAT_MAX):
        return (fail(f"{sa['drawer']} of {N_DRAWERS} drawers, seat {sa['drawer_seat']} outside "
                     f"[{DRAWER_SEAT_MIN}, {DRAWER_SEAT_MAX}] (--lift-drawers is the designed fail)",
                     18),) + nothing
    if (sa["label_bite"][0] < LABEL_BITE_MIN or sa["label_bite"][1] > LABEL_BITE_MAX
            or sa["label_proud"] < LABEL_PROUD_MIN):
        return (fail(f"label bite {sa['label_bite']} outside [{LABEL_BITE_MIN}, {LABEL_BITE_MAX}] "
                     f"or proud {sa['label_proud']:.5f} < {LABEL_PROUD_MIN} "
                     "(--float-labels is the designed fail)", 18),) + nothing
    if sa["headroom"] < HEADROOM_MIN:
        return (fail(f"headroom {sa['headroom']:.5f} < {HEADROOM_MIN} "
                     "(--tall-flask is the designed fail)", 20),) + nothing
    if sa["vessel_hits"]:
        return (fail(f"{sa['vessel_hits']} vessel overlaps, need 0 "
                     "(--crowd-jars is the designed fail)", 21),) + nothing
    if sa["diam_spread"] < DIAM_SPREAD_MIN or sa["height_spread"] < HEIGHT_SPREAD_MIN:
        return (fail(f"vessel spread diameter {sa['diam_spread']:.3f} (min {DIAM_SPREAD_MIN}), "
                     f"height {sa['height_spread']:.3f} (min {HEIGHT_SPREAD_MIN}) "
                     "(--uniform-vessels is the designed fail)", 22),) + nothing
    if right:
        return (fail(f"{right} right-angle wood edges, need 0 "
                     "(--sharp-rail is the designed fail)", 23),) + nothing
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

    light("Key", "AREA", (-2.4, -3.4, 3.2), 420.0, 3.0, (1.0, 0.95, 0.88), (50, 0, -35))
    light("Fill", "AREA", (3.2, -2.8, 1.6), 70.0, 5.0, (0.74, 0.84, 1.0), (68, 0, 48))
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
    cam.location = (1.05, -3.05, 1.05)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.54)
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
    p.add_argument("--pop-corks", action="store_true")
    p.add_argument("--pull-knobs", action="store_true")
    p.add_argument("--float-jars", action="store_true")
    p.add_argument("--lift-drawers", action="store_true")
    p.add_argument("--float-labels", action="store_true")
    p.add_argument("--tall-flask", action="store_true")
    p.add_argument("--crowd-jars", action="store_true")
    p.add_argument("--uniform-vessels", action="store_true")
    p.add_argument("--sharp-rail", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_side=args.float_side,
        short_shelves=args.short_shelves,
        pop_corks=args.pop_corks,
        pull_knobs=args.pull_knobs,
        float_jars=args.float_jars,
        lift_drawers=args.lift_drawers,
        float_labels=args.float_labels,
        tall_flask=args.tall_flask,
        crowd_jars=args.crowd_jars,
        uniform_vessels=args.uniform_vessels,
        sharp_rail=args.sharp_rail,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("apothecary shelf OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
