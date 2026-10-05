"""Game-ready fallen log — a showcase piece, not an example.

Asserts budget conformance of a procedural forest-floor log after composing
shipped pipeline pieces: bmesh construction, UVs, nine materials, high-to-low
normal bake, LOD chain, convex log collider, Unity glTF export.

The log is one lathe along a bowed axis, about 3.1 m long, tapering from a
flared butt to a snapped top. Its bark is plated and cut by narrow furrows,
and it is peeled away in four patches that show the sapwood underneath,
cut by beetle galleries. The butt is an old saw cut, its growth rings
weathered round a rotted-out hollow heart; the top is a snapped break of
splintered fibres with a long tongue. Two broken branch stubs stand out of
it. The log has settled into a soil mound along its whole length. Moss
cushions grow on its top and shaded north side; three tiers of bracket
fungi grow out of its south flank; a cluster of toadstools, two clumps of
ferns and a scatter of fallen leaves lie on the soil round it.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--hump-ground`` the log bedded along
its length, ``--float-fungi`` the brackets rooted in the bark,
``--tilt-ground`` the mass centre over the contact patch, ``--sunny-moss``
the moss on up- and shade-facing surfaces, ``--float-litter`` the ground
cover rooted in the soil.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python fallen_log.py --
    blender --background --python fallen_log.py -- --skip-decimate
    blender --background --python fallen_log.py -- --output log.png
"""
import argparse
import math
import os
import random
import sys
import tempfile
import traceback

import bmesh
import bpy
from mathutils import Vector
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

SEED = 2231
TAU = 2.0 * math.pi

# --- Log -------------------------------------------------------------------
LOG_L = 3.10            # butt ring to top ring along the axis
R_BUTT = 0.300
R_TOP = 0.245
BUTT_FLARE = 0.035      # extra radius at the butt, fading over the first metres
ELLIPSE = 0.05          # out-of-round, turning slowly along the log
LOG_SIDES = 64
LOG_SIDES_HIGH = 128
RING_STEP = 0.04
FURROWS = 16            # bark furrows round the girth
FURROW_D = 0.022        # furrow depth below the plates
BARK_T = 0.026          # sapwood lies this far under the plate surface
BOW = (0.08, -0.025)    # plan bow: sin(pi s) and sin(2 pi s) terms, m
BURY = 0.045            # the log's underside is this far into its bed
R_MID = 0.28            # metres per radian, for patch sizes on the girth
# peeled bark: (s, a deg, half-length m, half-arc m)
PEELS = ((0.30, 140.0, 0.24, 0.12), (0.60, 168.0, 0.30, 0.10),
         (0.88, 125.0, 0.18, 0.13), (0.08, 118.0, 0.12, 0.09))
# moss cushions on the top and the shaded (north, +Y) side
MOSS = ((0.17, 72.0, 0.30, 0.15), (0.43, 80.0, 0.33, 0.13), (0.55, 36.0, 0.24, 0.12),
        (0.77, 98.0, 0.20, 0.11), (0.94, 62.0, 0.11, 0.10), (0.30, 26.0, 0.20, 0.11),
        (0.66, 112.0, 0.10, 0.07), (0.04, 80.0, 0.09, 0.09), (0.36, 55.0, 0.12, 0.08),
        (0.86, 40.0, 0.14, 0.10))
MOSS_T = 0.028
MOSS_EDGE = 0.003       # the cushion's rim tucks this far under the bark
MOSS_BITE = 0.006       # the cushion's base, inside the bark (staggered per patch)
MOSS_STAGGER = 0.0015
# broken branch stubs: (s, a deg, length past the bark, radius, lean along the log)
STUBS = ((0.60, 78.0, 0.44, 0.055, 0.35), (0.30, 200.0, 0.16, 0.045, -0.20))
# bracket fungus tiers: (s, top a deg, a step deg, [(width, reach)...])
TIERS = ((0.45, 176.0, 8.5, ((0.30, 0.16), (0.27, 0.15), (0.23, 0.13), (0.19, 0.11),
                             (0.15, 0.085))),
         (0.80, 172.0, 9.0, ((0.26, 0.14), (0.22, 0.125), (0.18, 0.10), (0.14, 0.08))),
         (0.15, 166.0, 9.0, ((0.21, 0.115), (0.17, 0.095), (0.13, 0.07))))
SHELF_NS = 12
SHELF_ROWS = (0.0, 0.18, 0.35, 0.50, 0.63, 0.75, 0.85, 0.935, 1.0)  # thin white margin row
SHELF_NT = len(SHELF_ROWS) - 1
SHELF_BITE = 0.020      # a shelf's back edge, inside the bark
SHELF_STAGGER = 0.0015  # neighbouring shelves bite to different depths
FLOAT_FUNGI = 0.035     # --float-fungi: every shelf moved this far off the bark

# --- Ground ----------------------------------------------------------------
SOIL_A = (2.00, 1.06)   # mound semi-axes
SOIL_Y0 = 0.03
SOIL_H0 = 0.075
SOIL_N = 48
SOIL_EDGE = 0.20        # rolled rim, fraction of the radius
BERM_H = 0.035          # soil drifted against the log's sides
BERM_W = 0.12
SOIL_FLOOR = 0.012
N_LEAVES = 130
LEAF_BITE = 0.006
FLOAT_LITTER = 0.025
TOAD_CENTRE = (0.45, -0.62)
N_TOADS = 8
FERN_CLUMPS = (((0.95, 0.62), (18.0, 46.0, 74.0, 100.0, 126.0, 154.0), (0.64, 0.80)),
               ((-1.30, 0.55), (95.0, 135.0, 170.0, 205.0), (0.48, 0.60)))
FERN_PINNAE = 14
# falsifier grounds
HUMP_X = 0.03          # the hump sits under the log's mass centre
HUMP_W = 0.24
HUMP_DROP = 0.09
TILT_DROP = 0.08
TILT_BANK = 0.05

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (4.1189, 2.1885, 1.0267)
BASE_TRIS_MIN = 35600
BASE_TRIS_MAX = 37200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 9
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 240
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
# bark, wood, rot, moss, bracket, toadstool, soil, litter, fern
FACE_FLOORS = (4600, 800, 340, 2150, 2200, 1160, 2240, 1870, 4580)

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Contact patch: the log shell binned along X; a bin is bedded when its
# most-buried vertex is below the soil surface by a depth inside the band.
STATION = 0.10
BED_MIN = 0.020
BED_MAX = 0.090
BEDDED_MIN = 0.75
CONTACT_EPS = 0.003
# Mass centre: inside the plan hull of the buried vertices by this much.
HULL_MARGIN_MIN = 0.06
# Brackets: each shelf's deepest vertex inside the bark, as a band.
FUNGUS_BITE_MIN = 0.008
FUNGUS_BITE_MAX = 0.050
# Moss: top faces (facing away from the bark) that face up or north.
MOSS_TOP_DOT = 0.3
MOSS_UP_Z = 0.25
MOSS_SHADE_Y = 0.5
MOSS_FRAC_MIN = 0.85
# Hero yaw about Z only (level on the stage).
HERO_YAW_DEG = 0.0
WALL_Y = 4.5

BARK_IDX = 0
WOOD_IDX = 1
ROT_IDX = 2
MOSS_IDX = 3
BRACKET_IDX = 4
TOAD_IDX = 5
SOIL_IDX = 6
LITTER_IDX = 7
FERN_IDX = 8
MAT_LABELS = ("bark", "wood", "rot", "moss", "bracket", "toadstool", "soil", "litter",
              "fern")


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


def smoothstep(x, lo, hi):
    t = min(max((x - lo) / (hi - lo), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def wrap(a):
    return (a + math.pi) % TAU - math.pi


# --------------------------------------------------------------------------
# The log's closed-form shape
# --------------------------------------------------------------------------

def ground_line(x):
    """Soil level along the log's bed. One function of X, so the log settles
    evenly along its length and the bed under it is the same line."""
    return SOIL_H0 + 0.010 * math.sin(1.7 * x + 0.4) + 0.005 * math.sin(3.3 * x + 1.1)


def base_radius(s, a):
    r = R_BUTT + (R_TOP - R_BUTT) * s + BUTT_FLARE * math.exp(-s / 0.05)
    r *= 1.0 + ELLIPSE * math.cos(2.0 * (a - 0.6 - 0.9 * s))
    r *= (1.0 + 0.022 * math.sin(TAU * 1.6 * s + 1.3 + a)
          + 0.016 * math.sin(TAU * 3.7 * s + 2.0 * a + 0.5))
    return r


def furrow(s, a):
    """Plates with narrow V furrows between them; the plates break across
    the log, so the furrow depth changes along it."""
    ph = FURROWS * a + 0.35 * math.sin(TAU * 2.3 * s + 0.7) + 0.2 * math.sin(TAU * 5.1 * s)
    v = (1.0 - math.cos(ph)) * 0.5
    depth = FURROW_D * (0.75 + 0.25 * math.sin(TAU * 4.3 * s + 3.0 * a))
    return -depth * v ** 3


def axis_xy(s):
    s = min(max(s, 0.0), 1.0)
    x = -0.5 * LOG_L + LOG_L * s
    y = BOW[0] * math.sin(math.pi * s) + BOW[1] * math.sin(TAU * s)
    return x, y


def axis_point(s):
    x, y = axis_xy(s)
    bottom = base_radius(s, 1.5 * math.pi) + furrow(s, 1.5 * math.pi)
    return Vector((x, y, ground_line(x) - BURY + bottom))


def axis_frame(s):
    e = 1e-3
    t = (axis_point(min(1.0, s + e)) - axis_point(max(0.0, s - e))).normalized()
    lat = Vector((0.0, 0.0, 1.0)).cross(t).normalized()
    return t, lat, t.cross(lat)


def ring_dir(frame, a):
    _t, lat, vert = frame
    return lat * math.cos(a) + vert * math.sin(a)


def peel_field(s, a, patches):
    """Largest (edge - r) over the peel patches: positive inside a patch,
    zero on its torn edge."""
    best = -9.0
    for p in patches:
        ds = (s - p["s"]) * LOG_L / p["hs"]
        da = wrap(a - p["a"]) * R_MID / p["ha"]
        r = math.hypot(ds, da)
        th = math.atan2(da, ds)
        edge = 1.0 + 0.22 * math.sin(3.0 * th + p["ph"]) + 0.12 * math.sin(7.0 * th + 2.0 * p["ph"])
        best = max(best, edge - r)
    return best


def peeled(s, a, patches):
    return peel_field(s, a, patches) > 0.0


# --------------------------------------------------------------------------
# The plan: every seeded draw happens here, before anything is built
# --------------------------------------------------------------------------

def plan_log():
    rng = random.Random(SEED)

    def u(a, b):
        return a + (b - a) * rng.random()

    peels = [{"s": s, "a": math.radians(a), "hs": hs, "ha": ha, "ph": u(0.0, TAU)}
             for s, a, hs, ha in PEELS]
    moss = [{"s": s, "a": math.radians(a), "hs": hs * u(0.92, 1.08), "ha": ha * u(0.92, 1.08),
             "ph": u(0.0, TAU), "tone": rng.random()} for s, a, hs, ha in MOSS]
    shelves = []
    for ti, (s0, a0, da, sizes) in enumerate(TIERS):
        for k, (w, d) in enumerate(sizes):
            shelves.append({
                "tier": ti,
                "s": s0 + (0.030 if k % 2 else -0.022) * (1.0 + 0.4 * rng.random()),
                "yaw": math.radians(u(-16.0, 16.0)),
                "a": math.radians(a0 + da * k + u(-1.5, 1.5)),
                "w": w * u(0.92, 1.08), "d": d * u(0.92, 1.08),
                "ph": u(0.0, TAU), "tone": rng.random(), "lift": u(-0.03, 0.08),
            })
    # the snapped top: one splinter length per 1/64 of the girth
    spikes = []
    for j in range(64):
        v = rng.random()
        spikes.append((0.015 + 0.19 * v ** 2.5) * (1.0 if j % 2 else 0.30))
    lip = [u(0.004, 0.020) for _ in range(64)]

    toads = []
    for k in range(N_TOADS):
        ang = TAU * k / N_TOADS + u(-0.4, 0.4)
        rad = 0.02 + 0.13 * rng.random() ** 0.7
        toads.append({"x": TOAD_CENTRE[0] + rad * math.cos(ang),
                      "y": TOAD_CENTRE[1] + rad * math.sin(ang),
                      "h": u(0.07, 0.14), "rc": u(0.028, 0.052),
                      "lean": (u(-0.25, 0.25), u(-0.25, 0.25)), "spin": u(0.0, TAU),
                      "tone": rng.random()})
    ferns = []
    for (cx, cy), yaws, (h0, h1) in FERN_CLUMPS:
        for yaw in yaws:
            ferns.append({"x": cx + u(-0.03, 0.03), "y": cy + u(-0.03, 0.03),
                          "yaw": math.radians(yaw + u(-8.0, 8.0)), "h": u(h0, h1),
                          "reach": u(0.34, 0.44), "lp": u(0.10, 0.13),
                          "tone": rng.random(), "curl": u(0.25, 0.40)})
    avoid = [(TOAD_CENTRE, 0.22)] + [((c[0][0], c[0][1]), 0.26) for c in FERN_CLUMPS]
    leaves = []
    tries = 0
    while len(leaves) < N_LEAVES and tries < 20000:
        tries += 1
        x = u(-1.0, 1.0) * SOIL_A[0]
        y = u(-1.0, 1.0) * SOIL_A[1] + SOIL_Y0
        if (x / SOIL_A[0]) ** 2 + ((y - SOIL_Y0) / SOIL_A[1]) ** 2 > 0.74 ** 2:
            continue
        s = (x + 0.5 * LOG_L) / LOG_L
        if -0.10 < s < 1.14 and abs(y - axis_xy(s)[1]) < 0.40:
            continue
        if any(math.hypot(x - c[0], y - c[1]) < r for c, r in avoid):
            continue
        if any(math.hypot(x - lf["x"], y - lf["y"]) < 0.055 for lf in leaves):
            continue
        leaves.append({"x": x, "y": y, "yaw": u(0.0, TAU), "len": u(0.055, 0.110),
                       "wid": u(0.38, 0.58), "curl": u(0.002, 0.008),
                       "tone": rng.random() ** 1.5})
    return {"peels": peels, "moss": moss, "shelves": shelves, "spikes": spikes, "lip": lip,
            "toads": toads, "ferns": ferns, "leaves": leaves}


# --------------------------------------------------------------------------
# Ground
# --------------------------------------------------------------------------

def soil_height(x, y, mode):
    s = (x + 0.5 * LOG_L) / LOG_L
    past = max(0.0, -s, s - 1.0) * LOG_L
    w_end = math.exp(-(past / 0.25) ** 2)
    dy = y - axis_xy(s)[1]
    ady = abs(dy)
    ambient = (SOIL_H0 + 0.020 * math.sin(1.3 * x + 0.2) * math.cos(1.9 * y + 0.5)
               + 0.012 * math.sin(2.9 * x - 2.1 * y + 1.0) + 0.006 * math.sin(5.3 * x + 3.7 * y))
    w = w_end * (1.0 - smoothstep(ady, 0.38, 0.75))
    h = ambient * (1.0 - w) + ground_line(x) * w
    h += BERM_H * math.exp(-((ady - 0.30) / BERM_W) ** 2) * w_end
    if mode == "hump":
        band = w_end * (1.0 - smoothstep(ady, 0.36, 0.50))
        h -= HUMP_DROP * band * (1.0 - math.exp(-((x - HUMP_X) / HUMP_W) ** 2))
    elif mode == "tilt":
        band = w_end * (1.0 - smoothstep(ady, 0.36, 0.50))
        h += band * (TILT_BANK * smoothstep(dy, 0.06, 0.20)
                     - TILT_DROP * (1.0 - smoothstep(dy, 0.02, 0.10)))
    return max(SOIL_FLOOR, h)


def add_soil(bm, L, mode):
    """A soil mound: a squircle-mapped grid whose rim rolls down to a flat
    base at Z = 0. The base is one n-gon, triangulated later."""
    n = SOIL_N
    grid = []
    for i in range(n + 1):
        col = []
        for k in range(n + 1):
            uu = -1.0 + 2.0 * i / n
            vv = -1.0 + 2.0 * k / n
            X = uu * math.sqrt(1.0 - vv * vv / 2.0)
            Y = vv * math.sqrt(1.0 - uu * uu / 2.0)
            r = min(1.0, math.hypot(X, Y))
            th = math.atan2(Y, X)
            wob = (1.0 + 0.07 * math.sin(3.0 * th + 0.7) + 0.05 * math.sin(5.0 * th + 2.1)
                   + 0.03 * math.sin(8.0 * th + 0.3))
            x = SOIL_A[0] * X * wob
            y = SOIL_A[1] * Y * wob + SOIL_Y0
            on_rim = i in (0, n) or k in (0, n)
            z = 0.0 if on_rim else soil_height(x, y, mode) * smoothstep(1.0 - r, 0.0, SOIL_EDGE)
            col.append(bm.verts.new((x, y, z)))
        grid.append(col)
    faces = []
    for i in range(n):
        for k in range(n):
            faces.append(new_face(bm, (grid[i][k], grid[i + 1][k], grid[i + 1][k + 1],
                                       grid[i][k + 1]), SOIL_IDX, L, 0.5))
    rim = ([grid[i][0] for i in range(n)] + [grid[n][k] for k in range(n)]
           + [grid[i][n] for i in range(n, 0, -1)] + [grid[0][k] for k in range(n, 0, -1)])
    faces.append(new_face(bm, list(reversed(rim)), SOIL_IDX, L, 0.5))
    return faces


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

def new_face(bm, verts, mat, L, tone, zone=0.0, grain=0.0):
    out = []
    for v in verts:
        if not out or out[-1] is not v:
            out.append(v)
    if len(out) > 1 and out[0] is out[-1]:
        out.pop()
    f = bm.faces.new(out)
    f.material_index = mat
    f[L["tone"]] = tone
    f[L["zone"]] = zone
    f[L["grain"]] = grain
    return f


def frames(pts):
    """Parallel-transported (tangent, normal, binormal) along a polyline."""
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    ref = Vector((0.0, 0.0, 1.0)) if abs(tans[0].z) < 0.9 else Vector((1.0, 0.0, 0.0))
    nrm = (ref - tans[0] * ref.dot(tans[0])).normalized()
    out = []
    for t in tans:
        nrm = (nrm - t * nrm.dot(t)).normalized()
        out.append((t, nrm, t.cross(nrm)))
    return out


def add_tube(bm, pts, radii, sides, mat, L, tone, phase=0.0, jag=None, end_mat=None,
             zone=0.0):
    """Capped round bar swept along a polyline with a radius per point.
    ``jag``: per-vertex (radial factor, axial offset) for the last ring."""
    pts = [Vector(p) for p in pts]
    rings = []
    for idx, (p, (t, n, b)) in enumerate(zip(pts, frames(pts))):
        ring = []
        for k in range(sides):
            a = phase + TAU * k / sides
            r = radii[idx]
            off = Vector((0.0, 0.0, 0.0))
            if jag is not None and idx == len(pts) - 1:
                r *= jag[k % len(jag)][0]
                off = t * jag[k % len(jag)][1]
            ring.append(bm.verts.new(p + off + r * (n * math.cos(a) + b * math.sin(a))))
        rings.append(ring)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            faces.append(new_face(bm, (r0[k], r0[m], r1[m], r1[k]), mat, L, tone, zone))
    faces.append(new_face(bm, tuple(reversed(rings[0])), mat, L, tone, zone))
    faces.append(new_face(bm, tuple(rings[-1]), end_mat if end_mat is not None else mat,
                          L, tone, zone, 0.4 if end_mat is not None else 0.0))
    return faces


def add_lens(bm, outline, top, bottom, mat, L, tone, zone=0.0):
    """A thin closed leaf: an outline ring fanned to a raised top centre and a
    lowered bottom centre. Every outline edge has one top and one bottom face."""
    ring = [bm.verts.new(p) for p in outline]
    vt = bm.verts.new(top)
    vb = bm.verts.new(bottom)
    n = len(ring)
    for k in range(n):
        m = (k + 1) % n
        new_face(bm, (ring[k], ring[m], vt), mat, L, tone, zone)
        new_face(bm, (ring[m], ring[k], vb), mat, L, tone, zone)


def add_lathe(bm, origin, axis, profile, sides, spin, mat, L, tone, part_fn):
    """Closed body of revolution; profile (r, z) runs pole to pole."""
    axis = axis.normalized()
    ref = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    e1 = axis.cross(ref).normalized()
    e2 = axis.cross(e1)
    p0 = bm.verts.new(origin + axis * profile[0][1])
    p1 = bm.verts.new(origin + axis * profile[-1][1])
    rings = []
    for r, z in profile[1:-1]:
        ring = []
        for j in range(sides):
            a = spin + TAU * j / sides
            ring.append(bm.verts.new(origin + axis * z + r * (e1 * math.cos(a) + e2 * math.sin(a))))
        rings.append(ring)
    for j in range(sides):
        m = (j + 1) % sides
        new_face(bm, (rings[0][m], rings[0][j], p0), mat, L, tone, part_fn(0))
        new_face(bm, (rings[-1][j], rings[-1][m], p1), mat, L, tone, part_fn(len(profile) - 2))
    for k, (r0, r1) in enumerate(zip(rings, rings[1:])):
        for j in range(sides):
            m = (j + 1) % sides
            new_face(bm, (r0[j], r0[m], r1[m], r1[j]), mat, L, tone, part_fn(k + 1))


class LogSurface:
    """The built log's vertex grid, sampled bilinearly, so anything laid on
    the bark (moss, brackets) sits on the faces actually shipped."""

    def __init__(self, grid, n, sides):
        self.grid = grid
        self.n = n
        self.sides = sides

    def point(self, s, a):
        fi = min(max(s, 0.0), 1.0) * self.n
        i = min(int(fi), self.n - 1)
        u = fi - i
        fj = (a % TAU) / TAU * self.sides
        j = int(fj) % self.sides
        v = fj - math.floor(fj)
        j1 = (j + 1) % self.sides
        g = self.grid
        return (g[i][j] * ((1 - u) * (1 - v)) + g[i + 1][j] * (u * (1 - v))
                + g[i][j1] * ((1 - u) * v) + g[i + 1][j1] * (u * v))

    def normal(self, s, a):
        es = 0.004
        ea = 0.012
        ps = self.point(s + es, a) - self.point(s - es, a)
        pa = self.point(s, a + ea) - self.point(s, a - ea)
        n = ps.cross(pa).normalized()
        if n.dot(self.point(s, a) - axis_point(s)) < 0.0:
            n = -n
        return n


def build_log(bm, plan, sides, L, radial, peel_layer):
    n = int(round(LOG_L / RING_STEP))
    grid = []
    flags = []
    for i in range(n + 1):
        s = i / n
        c = axis_point(s)
        fr = axis_frame(s)
        ring = []
        pf = []
        for j in range(sides):
            a = TAU * j / sides
            field = peel_field(s, a, plan["peels"])
            peel = field > 0.0
            r = base_radius(s, a) - BARK_T if peel else base_radius(s, a) + furrow(s, a)
            ring.append(c + ring_dir(fr, a) * r)
            pf.append((peel, field))
        grid.append(ring)
        flags.append(pf)
    verts = [[bm.verts.new(p) for p in ring] for ring in grid]
    for ring, pf in zip(verts, flags):
        for v, (_peel, field) in zip(ring, pf):
            v[radial] = 1.0
            # the torn edge, for the bark shader: 0.5 exactly on the patch
            # outline, so the edge is cut between vertices, not along faces
            v[peel_layer] = min(1.0, max(0.0, 0.5 + 2.0 * field))
    flags = [[f for f, _field in pf] for pf in flags]
    for i in range(n):
        for j in range(sides):
            m = (j + 1) % sides
            q = (verts[i][j], verts[i][m], verts[i + 1][m], verts[i + 1][j])
            f = (flags[i][j], flags[i][m], flags[i + 1][m], flags[i + 1][j])
            npeel = sum(f)
            if npeel == 0 or npeel == 4:
                new_face(bm, q, WOOD_IDX if npeel else BARK_IDX, L, 0.1 if npeel else 0.25)
                continue
            # a quad on a peel's edge splits along the diagonal that keeps
            # its bark corner apart, so the torn edge runs at 45 degrees
            # instead of stepping round the quad grid
            if npeel == 3:
                k = 1 if not (f[0] and f[2]) else 0
            else:
                k = (i + j) % 2
            tris = (((q[0], q[1], q[2]), (0, 1, 2)), ((q[0], q[2], q[3]), (0, 2, 3))) if k == 0 \
                else (((q[0], q[1], q[3]), (0, 1, 3)), ((q[1], q[2], q[3]), (1, 2, 3)))
            for tri, idx in tris:
                wood = all(f[x] for x in idx)
                new_face(bm, tri, WOOD_IDX if wood else BARK_IDX, L, 0.1 if wood else 0.25)

    def cap(ring0, s, spec, centre_off, inward, sector_mat, tone):
        """End cap rings from the lathe's end ring inward: ``spec`` rows are
        (radius fn, axial offset fn, material, grain, radial value)."""
        c = axis_point(s)
        fr = axis_frame(s)
        t = fr[0] * inward
        prev = ring0
        for rad_fn, off_fn, mat, grain, rv in spec:
            ring = []
            for j in range(sides):
                a = TAU * j / sides
                v = bm.verts.new(c + t * off_fn(j, a) + ring_dir(fr, a) * rad_fn(a))
                v[radial] = rv
                ring.append(v)
            for j in range(sides):
                m = (j + 1) % sides
                new_face(bm, (prev[j], prev[m], ring[m], ring[j]), mat, L, tone, 0.0, grain)
            prev = ring
        centre = bm.verts.new(c + t * centre_off)
        centre[radial] = 0.0
        for j in range(sides):
            m = (j + 1) % sides
            new_face(bm, (prev[j], prev[m], centre), sector_mat, L, tone, 0.0,
                     1.0 if sector_mat == WOOD_IDX else 0.0)

    # the butt: an old saw cut, weathered concave, round a rotted hollow heart
    def rf(k):
        return lambda a: base_radius(0.0, a) * k

    def off(d):
        return lambda j, a: d

    butt = [(lambda a: base_radius(0.0, a) - BARK_T, off(0.0), BARK_IDX, 0.0, 0.97),
            (rf(0.86), off(0.003), WOOD_IDX, 1.0, 0.86),
            (rf(0.72), off(0.005), WOOD_IDX, 1.0, 0.72),
            (rf(0.60), off(0.007), WOOD_IDX, 1.0, 0.60),
            (rf(0.50), off(0.009), WOOD_IDX, 1.0, 0.50),
            (rf(0.46), off(0.030), ROT_IDX, 0.0, 0.46),
            (rf(0.42), off(0.100), ROT_IDX, 0.0, 0.42),
            (rf(0.37), off(0.200), ROT_IDX, 0.0, 0.37),
            (rf(0.30), off(0.310), ROT_IDX, 0.0, 0.30),
            (rf(0.20), off(0.390), ROT_IDX, 0.0, 0.20)]
    cap(verts[0], 0.0, butt, 0.42, 1.0, ROT_IDX, 0.35)

    # the top: a snapped break, the upper fibres pulled out longest, with a
    # tongue torn out along the north-upper side
    spikes = plan["spikes"]
    lip = plan["lip"]

    def sector(a):
        return int((a % TAU) / TAU * 64) % 64

    def brk(k):
        w = 0.25 + 0.75 * math.sin(math.pi * k)

        def f(j, a):
            tilt = 0.06 + 0.05 * math.sin(a)
            tongue = 0.20 * max(0.0, math.cos(a - 1.2)) ** 4
            sec = sector(a)
            # every ring breaks at its own length: splinters, not a dome
            crag = 0.035 * math.sin(sec * 2.7 + k * 11.0) * math.sin(sec * 1.3 + k * 5.0)
            return tilt + tongue + spikes[sec] * w + crag + 0.01 * (1.0 - k)
        return f

    top = [(lambda a: base_radius(1.0, a) - BARK_T, lambda j, a: lip[sector(a)], BARK_IDX, 0.0,
            0.97)]
    for k in (0.84, 0.66, 0.48, 0.30, 0.14):
        top.append((lambda a, k=k: base_radius(1.0, a) * k, brk(k), WOOD_IDX, 0.4, k))
    cap(verts[n], 1.0, top, 0.075, 1.0, WOOD_IDX, 0.9)
    return LogSurface(grid, n, sides)


def add_moss(bm, surf, patch, L, rot, bite):
    """A moss cushion: a lens over a patch of the bark, its rim tucked under
    the bark surface and its base inside the log."""
    K = 6
    M = 20
    sc = patch["s"]
    ac = patch["a"] + rot

    def lump(s, a):
        return (0.72 + 0.28 * math.sin(41.0 * s + 6.0 * a + patch["ph"])
                * math.sin(23.0 * s - 5.0 * a + 1.3 * patch["ph"]))

    top_rings = []
    bot_rings = []
    for k in range(1, K + 1):
        rho = k / K
        tr = []
        br = []
        for m in range(M):
            th = TAU * m / M
            edge = 1.0 + 0.20 * math.sin(3.0 * th + patch["ph"]) + 0.10 * math.sin(5.0 * th + 2.0 * patch["ph"])
            s = sc + rho * edge * patch["hs"] * math.cos(th) / LOG_L
            a = ac + rho * edge * patch["ha"] * math.sin(th) / R_MID
            p = surf.point(s, a)
            nrm = surf.normal(s, a)
            thick = MOSS_T * max(0.0, 1.0 - rho * rho) ** 0.5 * lump(s, a)
            tv = bm.verts.new(p + nrm * (thick - MOSS_EDGE))
            tr.append(tv)
            br.append(tv if k == K else bm.verts.new(p - nrm * bite))
        top_rings.append(tr)
        bot_rings.append(br)
    p0 = surf.point(sc, ac)
    n0 = surf.normal(sc, ac)
    ct = bm.verts.new(p0 + n0 * (MOSS_T * lump(sc, ac) - MOSS_EDGE))
    cb = bm.verts.new(p0 - n0 * bite)
    tone = patch["tone"]
    for rings, centre, flip in ((top_rings, ct, False), (bot_rings, cb, True)):
        for m in range(M):
            q = (m + 1) % M
            tri = (rings[0][m], rings[0][q], centre)
            new_face(bm, tri[::-1] if flip else tri, MOSS_IDX, L, tone)
        for r0, r1 in zip(rings, rings[1:]):
            for m in range(M):
                q = (m + 1) % M
                quad = (r0[m], r1[m], r1[q], r0[q])
                new_face(bm, quad[::-1] if flip else quad, MOSS_IDX, L, tone)


def add_shelf(bm, surf, shelf, L, float_off, bite):
    """One bracket: a horizontal half-lens with a flat pore surface under a
    domed, zoned cap, its back edge set into the bark."""
    s, a = shelf["s"], shelf["a"]
    p = surf.point(s, a)
    n = surf.normal(s, a)
    nh = Vector((n.x, n.y, 0.0)).normalized()
    up = Vector((0.0, 0.0, 1.0))
    wv = up.cross(nh)
    # the shelf body swings about its attachment; the back row stays on the bark
    cy, sy = math.cos(shelf["yaw"]), math.sin(shelf["yaw"])
    nr = Vector((nh.x * cy - nh.y * sy, nh.x * sy + nh.y * cy, 0.0))
    wr = up.cross(nr)
    W, D, ph = shelf["w"], shelf["d"], shelf["ph"]
    t0 = 0.16 * D
    tb = 0.055 * D
    ns, nt = SHELF_NS, SHELF_NT
    top = [[None] * (nt + 1) for _ in range(ns + 1)]
    bot = [[None] * (nt + 1) for _ in range(ns + 1)]
    for i in range(ns + 1):
        si = -1.0 + 2.0 * i / ns
        env = max(0.0, 1.0 - si * si)
        reach = D * env ** 0.5 * (1.0 + 0.08 * math.sin(5.0 * si + ph))
        for j in range(nt + 1):
            t = SHELF_ROWS[j]
            grow = (reach + bite) * t ** 0.9
            wc = 0.5 * W * si
            slope = -0.12 * D * t * t + shelf["lift"] * D * t
            wave = 0.005 * math.sin(6.0 * si + ph) * t ** 3
            # a year's growth per step: shallow concentric ridges on the cap
            ridge = 0.022 * D * math.sin(t * 3.5 * TAU) * (1.0 - t) * env ** 0.35
            zt = t0 * (1.0 - t ** 1.6) * env ** 0.35 + slope + wave + ridge
            zb = -tb * (1.0 - t ** 2.2) * env ** 0.35 + slope + wave
            base = (p + nh * (float_off - bite) + wv * wc + nr * grow
                    + wr * (0.18 * wc * t))
            vt = bm.verts.new(base + up * zt)
            top[i][j] = vt
            shared = i in (0, ns) or j == nt
            bot[i][j] = vt if shared else bm.verts.new(base + up * zb)
    tone = shelf["tone"]
    for i in range(ns):
        for j in range(nt):
            zone = (j + 0.5) / nt
            new_face(bm, (top[i][j], top[i + 1][j], top[i + 1][j + 1], top[i][j + 1]),
                     BRACKET_IDX, L, tone, zone)
            new_face(bm, (bot[i][j + 1], bot[i + 1][j + 1], bot[i + 1][j], bot[i][j]),
                     BRACKET_IDX, L, tone, 2.0)
        new_face(bm, (top[i][0], bot[i][0], bot[i + 1][0], top[i + 1][0]), BRACKET_IDX, L,
                 tone, 0.0)


def soil_hit(tree, x, y):
    loc, nrm, _i, _d = tree.ray_cast(Vector((x, y, 5.0)), Vector((0.0, 0.0, -1.0)), 20.0)
    if loc is None:
        return Vector((x, y, 0.0)), Vector((0.0, 0.0, 1.0))
    if nrm.z < 0.0:
        nrm = -nrm
    return loc, nrm


def add_leaf(bm, tree, lf, L, lift):
    c, nrm = soil_hit(tree, lf["x"], lf["y"])
    e1 = Vector((math.cos(lf["yaw"]), math.sin(lf["yaw"]), 0.0))
    e1 = (e1 - nrm * e1.dot(nrm)).normalized()
    e2 = nrm.cross(e1)
    ln = lf["len"]
    wd = ln * lf["wid"] * 0.5
    shape = ((-0.50, 0.0), (-0.30, 0.62), (0.0, 1.0), (0.28, 0.78), (0.50, 0.0),
             (0.28, -0.78), (0.0, -1.0), (-0.30, -0.62))
    up = Vector((0.0, 0.0, lift))
    outline = []
    for fx, fy in shape:
        curl = lf["curl"] * (fy * fy + 0.6 * (2.0 * fx) ** 2)
        outline.append(c + e1 * (fx * ln) + e2 * (fy * wd) + nrm * (0.0015 + curl) + up)
    add_lens(bm, outline, c + nrm * 0.004 + up, c - nrm * LEAF_BITE + up, LITTER_IDX, L,
             lf["tone"])


def add_toadstool(bm, tree, td, L):
    base, _n = soil_hit(tree, td["x"], td["y"])
    base = base - Vector((0.0, 0.0, 0.02))
    axis = Vector((td["lean"][0], td["lean"][1], 1.0)).normalized()
    h = td["h"] + 0.02
    rc = td["rc"]
    sr = 0.17 * rc + 0.002
    tip = base + axis * h
    add_tube(bm, [base, base + axis * (0.3 * h), base + axis * (0.7 * h), tip],
             [sr * 1.3, sr, sr * 0.9, sr * 0.85], 8, TOAD_IDX, L, td["tone"], zone=0.0)
    prof = ((0.0, 0.0), (0.25, 0.002), (0.55, 0.006), (0.85, 0.012), (1.0, 0.022),
            (0.97, 0.034), (0.85, 0.050), (0.62, 0.064), (0.32, 0.073), (0.0, 0.076))
    prof = [(r * rc, z * rc / 0.076 * 0.9) for r, z in prof]

    def part(k):
        if k <= 3:
            return 0.5
        return 1.0 + min(1.0, max(0.0, (prof[min(k, len(prof) - 1)][0]) / rc))

    add_lathe(bm, tip - axis * 0.010, axis, prof, 14, td["spin"], TOAD_IDX, L, td["tone"], part)


def add_fern(bm, tree, fd, L):
    base, _n = soil_hit(tree, fd["x"], fd["y"])
    base = base - Vector((0.0, 0.0, 0.03))
    hdir = Vector((math.cos(fd["yaw"]), math.sin(fd["yaw"]), 0.0))
    up = Vector((0.0, 0.0, 1.0))
    H, R = fd["h"], fd["reach"]
    pts = []
    steps = 12
    for k in range(steps):
        t = k / (steps - 1)
        z = H * (2.0 * t - t * t) * (1.0 - fd["curl"] * t ** 3) + 0.03 * min(1.0, t * 8.0)
        pts.append(base + hdir * (R * t ** 1.25) + up * z)
    radii = [0.0070 - 0.0048 * (k / (steps - 1)) for k in range(steps)]
    add_tube(bm, pts, radii, 5, FERN_IDX, L, fd["tone"])

    def at(t):
        x = t * (steps - 1)
        i = min(int(x), steps - 2)
        f = x - i
        return pts[i].lerp(pts[i + 1], f), (pts[i + 1] - pts[i]).normalized()

    for k in range(FERN_PINNAE):
        t = 0.22 + 0.73 * k / (FERN_PINNAE - 1)
        lp = fd["lp"] * max(0.18, math.sin(math.pi * (t - 0.12) / 0.92)) ** 0.7
        for side, dt in ((1.0, 0.0), (-1.0, 0.012)):
            p, tan = at(min(0.995, t + dt))
            bn = (up - tan * up.dot(tan)).normalized()
            # each pinna twists a little about the rachis: neighbours along
            # one side are otherwise translated copies in one blade plane.
            # Period 3, so any two neighbours differ by at least 0.1 rad.
            tw = 0.10 * ((k % 3) - 1) + (0.04 if side < 0 else 0.0)
            bn = (bn * math.cos(tw) + tan.cross(bn) * math.sin(tw)).normalized()
            sd = tan.cross(bn) * side
            e1 = (sd * math.cos(0.35) + tan * math.sin(0.35) - bn * 0.12).normalized()
            e2 = (tan - e1 * tan.dot(e1)).normalized()
            e3 = e1.cross(e2).normalized()
            wp = 0.24 * lp
            # droop and midrib depth step per pinna too, so no two nearby
            # pinna faces share a plane by chance
            dr = 0.22 + 0.05 * ((k + (1 if side < 0 else 0)) % 4)
            rib = 0.0022 + 0.0006 * (k % 2)
            outline = []
            for f, sg in ((0.0, 0.0), (0.22, 1.0), (0.5, 1.0), (0.78, 1.0), (1.0, 0.0),
                          (0.78, -1.0), (0.5, -1.0), (0.22, -1.0)):
                hw = wp * math.sin(math.pi * f) ** 0.6 if 0.0 < f < 1.0 else 0.0
                droop = dr * lp * f * f
                outline.append(p + e1 * (f * lp) + e2 * (sg * hw) - bn * droop)
            mid = p + e1 * (0.45 * lp) - bn * (dr * lp * 0.2)
            add_lens(bm, outline, mid + e3 * rib, mid - e3 * rib, FERN_IDX, L,
                     fd["tone"], 0.5 + 0.5 * t)


def build_log_mesh(name, plan, detail="low", hump_ground=False, tilt_ground=False,
                   float_fungi=False, sunny_moss=False, float_litter=False):
    mode = "hump" if hump_ground else ("tilt" if tilt_ground else None)
    bm = bmesh.new()
    try:
        L = {"tone": bm.faces.layers.float.new("Tone"),
             "zone": bm.faces.layers.float.new("Zone"),
             "grain": bm.faces.layers.float.new("EndGrain")}
        radial = bm.verts.layers.float.new("Radial")
        sides = LOG_SIDES_HIGH if detail == "high" else LOG_SIDES

        add_soil(bm, L, mode)
        bm.faces.ensure_lookup_table()
        bm.normal_update()   # FromBMesh reads the stored face normals
        soil_tree = BVHTree.FromBMesh(bm)

        surf = build_log(bm, plan, sides, L, radial, bm.verts.layers.float.new("Peel"))

        rot = math.pi if sunny_moss else 0.0
        for k, patch in enumerate(plan["moss"]):
            add_moss(bm, surf, patch, L, rot, MOSS_BITE + MOSS_STAGGER * k)

        for s, a_deg, ln, r, lean in STUBS:
            a = math.radians(a_deg)
            c = axis_point(s)
            fr = axis_frame(s)
            perp = ring_dir(fr, a)
            d = (perp + fr[0] * lean).normalized()
            R = base_radius(s, a)
            b0 = c + perp * (0.35 * R)
            pts = [b0, b0 + d * (0.70 * R), b0 + d * (0.70 * R + 0.55 * ln),
                   b0 + d * (0.70 * R + ln)]
            jag = [(0.85, 0.012), (1.0, -0.006), (0.75, 0.024), (0.95, -0.010),
                   (0.80, 0.018), (1.0, 0.0), (0.9, 0.030), (0.7, 0.008)]
            add_tube(bm, pts, [r * 1.3, r * 1.15, r * 0.95, r * 0.85], 10, BARK_IDX, L, 0.3,
                     phase=a, jag=jag, end_mat=WOOD_IDX)

        off = FLOAT_FUNGI if float_fungi else 0.0
        for k, shelf in enumerate(plan["shelves"]):
            add_shelf(bm, surf, shelf, L, off, SHELF_BITE + SHELF_STAGGER * (k % 4))

        lift = FLOAT_LITTER if float_litter else 0.0
        for lf in plan["leaves"]:
            add_leaf(bm, soil_tree, lf, L, lift)
        for td in plan["toads"]:
            add_toadstool(bm, soil_tree, td, L)
        for fd in plan["ferns"]:
            add_fern(bm, soil_tree, fd, L)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy
            v.co.z -= zmin

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # Everything organic is smooth-shaded except broken wood; the
        # furrows and the fern and leaf lenses carry in the silhouette. Every
        # material boundary and every fold sharper than 70 degrees is a hard
        # edge.
        for face in bm.faces:
            # broken wood (the snapped top, the stub ends) stays faceted:
            # splinters are facets, not a smooth dome
            face.smooth = not (face.material_index == WOOD_IDX
                               and abs(face[L["grain"]] - 0.4) < 1e-6)
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            else:
                edge.smooth = edge.calc_face_angle() < math.radians(70.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def build_collider_source(name):
    """The log alone, round and unfurrowed: players walk through ferns."""
    bm = bmesh.new()
    try:
        L = {"tone": bm.faces.layers.float.new("Tone"),
             "zone": bm.faces.layers.float.new("Zone"),
             "grain": bm.faces.layers.float.new("EndGrain")}
        rings = []
        n = 12
        for i in range(n + 1):
            s = i / n
            c = axis_point(s)
            fr = axis_frame(s)
            rings.append([bm.verts.new(c + ring_dir(fr, TAU * j / 16) * base_radius(s, TAU * j / 16))
                          for j in range(16)])
        for r0, r1 in zip(rings, rings[1:]):
            for j in range(16):
                m = (j + 1) % 16
                new_face(bm, (r0[j], r0[m], r1[m], r1[j]), BARK_IDX, L, 0.0)
        new_face(bm, tuple(reversed(rings[0])), BARK_IDX, L, 0.0)
        new_face(bm, tuple(rings[-1]), BARK_IDX, L, 0.0)
        triangulate_ngons(bm)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


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
# Materials
# --------------------------------------------------------------------------

def enabled_socket(sockets, name):
    """The one enabled socket called ``name`` (Mix / Map Range carry one per
    data type under one name; identifiers changed in 5.2)."""
    for sock in sockets:
        if sock.name == name and sock.enabled:
            return sock
    return sockets[name]


def surface(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = 0.0
    coord = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    return mat, nt, bsdf, coord


def mapping(nt, vec, scale=(1.0, 1.0, 1.0)):
    node = nt.nodes.new("ShaderNodeMapping")
    node.inputs["Scale"].default_value = scale
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Vector"]


def noise(nt, vec, scale, detail, roughness):
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = roughness
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]


def wave(nt, vec, direction, scale, distortion):
    node = nt.nodes.new("ShaderNodeTexWave")
    node.wave_type = "BANDS"
    node.bands_direction = direction
    node.inputs["Scale"].default_value = scale
    node.inputs["Distortion"].default_value = distortion
    node.inputs["Detail"].default_value = 3.0
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]


def ramp(nt, fac, stops):
    node = nt.nodes.new("ShaderNodeValToRGB")
    els = node.color_ramp.elements
    els[0].position = stops[0][0]
    els[0].color = (*stops[0][1], 1.0)
    els[1].position = stops[-1][0]
    els[1].color = (*stops[-1][1], 1.0)
    for pos, rgb in stops[1:-1]:
        els.new(pos).color = (*rgb, 1.0)
    nt.links.new(fac, node.inputs["Fac"])
    return node.outputs["Color"]


def remap(nt, value, from_lo, from_hi, to_lo, to_hi):
    node = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(value, enabled_socket(node.inputs, "Value"))
    enabled_socket(node.inputs, "From Min").default_value = from_lo
    enabled_socket(node.inputs, "From Max").default_value = from_hi
    enabled_socket(node.inputs, "To Min").default_value = to_lo
    enabled_socket(node.inputs, "To Max").default_value = to_hi
    return enabled_socket(node.outputs, "Result")


def math_node(nt, op, a, b):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    for i, value in enumerate((a, b)):
        if isinstance(value, (int, float)):
            node.inputs[i].default_value = value
        else:
            nt.links.new(value, node.inputs[i])
    return node.outputs[0]


def mix_color(nt, a, b, fac):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    if isinstance(fac, (int, float)):
        enabled_socket(node.inputs, "Factor").default_value = fac
    else:
        nt.links.new(fac, enabled_socket(node.inputs, "Factor"))
    for nm, value in (("A", a), ("B", b)):
        sock = enabled_socket(node.inputs, nm)
        if isinstance(value, tuple):
            sock.default_value = (*value, 1.0)
        else:
            nt.links.new(value, sock)
    return enabled_socket(node.outputs, "Result")


def attr(nt, name):
    node = nt.nodes.new("ShaderNodeAttribute")
    node.attribute_type = "GEOMETRY"
    node.attribute_name = name
    return node.outputs["Fac"]


def height(nt, coord):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    return sep.outputs["Z"]


def bump(nt, bsdf, h, strength, distance):
    node = nt.nodes.new("ShaderNodeBump")
    node.inputs["Strength"].default_value = strength
    node.inputs["Distance"].default_value = distance
    nt.links.new(h, node.inputs["Height"])
    nt.links.new(node.outputs["Normal"], bsdf.inputs["Normal"])


def damp(nt, col, coord, rgb, amount):
    """Wood darkens where it has lain in the wet soil."""
    fac = remap(nt, height(nt, coord), 0.06, 0.24, amount, 0.0)
    return mix_color(nt, col, rgb, fac)


def bark_material():
    mat, nt, bsdf, coord = surface("LogBark")
    # Furrows: ridged noise stretched along the log (X), so the fissures run
    # with the grain and branch; the plates between them catch the light.
    plates = noise(nt, mapping(nt, coord, scale=(1.6, 7.0, 7.0)), 3.0, 8.0, 0.62)
    fn = noise(nt, mapping(nt, coord, scale=(0.9, 13.0, 13.0)), 1.0, 6.0, 0.58)
    ridge = math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", fn, 0.5), 0.0)
    furrow_f = remap(nt, ridge, 0.0, 0.10, 1.0, 0.0)
    fine = noise(nt, mapping(nt, coord, scale=(5.0, 34.0, 34.0)), 2.0, 6.0, 0.55)
    col = ramp(nt, plates, ((0.30, (0.050, 0.041, 0.033)), (0.50, (0.085, 0.070, 0.056)),
                            (0.70, (0.125, 0.108, 0.088)), (0.85, (0.160, 0.142, 0.120))))
    col = mix_color(nt, col, (0.012, 0.009, 0.007), furrow_f)
    col = mix_color(nt, col, (0.030, 0.024, 0.019), remap(nt, fine, 0.35, 0.65, 0.4, 0.0))
    # crustose lichen: a few soft grey-green blots on the plates
    lich = noise(nt, mapping(nt, coord, scale=(1.2, 1.2, 1.2)), 3.0, 5.0, 0.55)
    col = mix_color(nt, col, (0.16, 0.17, 0.13), remap(nt, lich, 0.64, 0.74, 0.0, 0.55))
    col = damp(nt, col, coord, (0.028, 0.022, 0.016), 0.6)
    # where a boundary face crosses into a peel, the torn edge shows the
    # sapwood under a dark rim of broken bark
    peel = attr(nt, "Peel")
    col = mix_color(nt, col, (0.010, 0.008, 0.006), remap(nt, peel, 0.36, 0.47, 0.0, 1.0))
    col = mix_color(nt, col, (0.34, 0.23, 0.13), remap(nt, peel, 0.49, 0.51, 0.0, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, plates, 0.35, 0.8, 0.95, 0.78), bsdf.inputs["Roughness"])
    bump(nt, bsdf, math_node(nt, "ADD", math_node(nt, "MULTIPLY", furrow_f, -1.0),
                             math_node(nt, "ADD", math_node(nt, "MULTIPLY", plates, 0.5),
                                       math_node(nt, "MULTIPLY", fine, 0.25))), 1.0, 0.03)
    return mat


def wood_material():
    mat, nt, bsdf, coord = surface("LogWood")
    grain_fac = attr(nt, "EndGrain")
    streak = noise(nt, mapping(nt, coord, scale=(1.2, 22.0, 22.0)), 2.0, 6.0, 0.6)
    base = ramp(nt, streak, ((0.30, (0.25, 0.16, 0.085)), (0.55, (0.38, 0.26, 0.15)),
                             (0.80, (0.46, 0.34, 0.21))))
    # beetle galleries: a wandering egg gallery along the grain (X) and the
    # larval tunnels radiating across it, thinning out away from it
    egg = wave(nt, coord, "Y", 2.2, 7.0)
    larva = wave(nt, coord, "X", 16.0, 4.0)
    near = remap(nt, egg, 0.55, 0.95, 0.0, 1.0)
    line = math_node(nt, "MAXIMUM", remap(nt, egg, 0.955, 0.985, 0.0, 1.0),
                     math_node(nt, "MULTIPLY", remap(nt, larva, 0.88, 0.97, 0.0, 0.9), near))
    line = math_node(nt, "MULTIPLY", line, remap(nt, grain_fac, 0.0, 0.3, 1.0, 0.0))
    col = mix_color(nt, base, (0.09, 0.055, 0.030), line)
    # end grain: growth rings on the radial attribute, heartwood darker
    radial = attr(nt, "Radial")
    wob = noise(nt, coord, 9.0, 3.0, 0.5)
    ringv = math_node(nt, "SINE", math_node(nt, "ADD",
                                            math_node(nt, "MULTIPLY", radial, TAU * 21.0),
                                            math_node(nt, "MULTIPLY", wob, 2.2)), 0.0)
    endcol = ramp(nt, radial, ((0.45, (0.20, 0.11, 0.055)), (0.62, (0.36, 0.22, 0.11)),
                               (0.90, (0.55, 0.42, 0.27))))
    endcol = mix_color(nt, endcol, (0.13, 0.075, 0.040), remap(nt, ringv, 0.55, 1.0, 0.0, 0.7))
    col = mix_color(nt, col, endcol, remap(nt, grain_fac, 0.6, 1.0, 0.0, 1.0))
    # weathering: the snapped top has greyed in the open
    col = mix_color(nt, col, (0.27, 0.25, 0.22), remap(nt, attr(nt, "Tone"), 0.5, 0.8, 0.0, 0.55))
    col = damp(nt, col, coord, (0.10, 0.065, 0.040), 0.5)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.82
    bump(nt, bsdf, math_node(nt, "ADD", streak, math_node(nt, "MULTIPLY", line, -0.6)),
         0.5, 0.01)
    return mat


def rot_material():
    mat, nt, bsdf, coord = surface("LogRot")
    punk = noise(nt, coord, 14.0, 6.0, 0.65)
    col = ramp(nt, punk, ((0.35, (0.030, 0.017, 0.010)), (0.60, (0.090, 0.050, 0.028)),
                          (0.80, (0.160, 0.090, 0.050))))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    bump(nt, bsdf, punk, 0.8, 0.02)
    return mat


def moss_material():
    mat, nt, bsdf, coord = surface("Moss")
    tone = attr(nt, "Tone")
    # each cushion its own green; within it, olive hollows, bright
    # yellow-green crowns and a fine fuzz
    base = ramp(nt, tone, ((0.0, (0.045, 0.095, 0.015)), (0.5, (0.080, 0.150, 0.022)),
                           (1.0, (0.120, 0.200, 0.030))))
    fuzz = noise(nt, coord, 140.0, 4.0, 0.7)
    tufts = noise(nt, coord, 26.0, 4.0, 0.6)
    patchy = noise(nt, coord, 6.0, 3.0, 0.5)
    col = mix_color(nt, base, (0.060, 0.070, 0.020), remap(nt, patchy, 0.40, 0.65, 0.55, 0.0))
    col = mix_color(nt, col, (0.018, 0.040, 0.010), remap(nt, fuzz, 0.35, 0.65, 0.65, 0.0))
    col = mix_color(nt, col, (0.20, 0.27, 0.045), remap(nt, tufts, 0.58, 0.74, 0.0, 0.65))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    bump(nt, bsdf, math_node(nt, "ADD", fuzz, math_node(nt, "MULTIPLY", tufts, 1.6)), 0.9, 0.008)
    return mat


def bracket_material():
    mat, nt, bsdf, coord = surface("BracketFungus")
    # Zone: 0..1 across the cap from the bark to the margin; 2.0 on the
    # pore surface. The shelves' concentric bands are the face rows.
    zone = attr(nt, "Zone")
    tone = attr(nt, "Tone")
    # Artist's conk: a crusted brown cap zoned darker toward the bark, a
    # white growing margin and a white pore surface underneath.
    zone = math_node(nt, "ADD", zone, math_node(nt, "MULTIPLY", tone, 0.05))
    col = ramp(nt, zone, ((0.00, (0.030, 0.017, 0.010)), (0.25, (0.060, 0.032, 0.016)),
                          (0.45, (0.110, 0.058, 0.026)), (0.62, (0.170, 0.092, 0.040)),
                          (0.76, (0.220, 0.130, 0.058)), (0.86, (0.280, 0.185, 0.095)),
                          (0.94, (0.780, 0.740, 0.640)), (1.20, (0.820, 0.780, 0.680)),
                          (1.90, (0.760, 0.720, 0.620)), (2.10, (0.740, 0.700, 0.600))))
    velvet = noise(nt, coord, 60.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.06, 0.035, 0.02), remap(nt, velvet, 0.3, 0.7, 0.30, 0.0))
    # spore dust: the rust-brown bloom a conk drops on the shelf below
    dust = noise(nt, coord, 8.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.30, 0.13, 0.05), remap(nt, dust, 0.55, 0.75, 0.0, 0.35))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.86
    bump(nt, bsdf, velvet, 0.3, 0.004)
    return mat


def toadstool_material():
    mat, nt, bsdf, coord = surface("Toadstool")
    # Zone: 0 stem, 0.5 gills, 1..2 cap from the crown to the margin.
    zone = attr(nt, "Zone")
    col = ramp(nt, zone, ((0.00, (0.70, 0.62, 0.48)), (0.40, (0.66, 0.58, 0.44)),
                          (0.50, (0.46, 0.36, 0.24)), (0.95, (0.46, 0.36, 0.24)),
                          (1.05, (0.33, 0.12, 0.030)), (1.55, (0.62, 0.30, 0.070)),
                          (2.00, (0.78, 0.52, 0.20))))
    speck = noise(nt, coord, 90.0, 2.0, 0.5)
    col = mix_color(nt, col, (0.25, 0.10, 0.03), remap(nt, speck, 0.55, 0.7, 0.0, 0.3))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.45
    return mat


def soil_material():
    mat, nt, bsdf, coord = surface("ForestSoil")
    clods = noise(nt, coord, 6.0, 6.0, 0.62)
    crumbs = noise(nt, coord, 70.0, 3.0, 0.6)
    col = ramp(nt, clods, ((0.30, (0.030, 0.022, 0.016)), (0.55, (0.060, 0.043, 0.030)),
                           (0.80, (0.095, 0.072, 0.052))))
    col = mix_color(nt, col, (0.018, 0.013, 0.010), remap(nt, crumbs, 0.35, 0.55, 0.6, 0.0))
    # needle and twig duff: fine pale flecks
    duff = noise(nt, mapping(nt, coord, scale=(40.0, 8.0, 40.0)), 3.0, 3.0, 0.5)
    col = mix_color(nt, col, (0.16, 0.11, 0.06), remap(nt, duff, 0.66, 0.74, 0.0, 0.6))
    # a green film of moss and algae in the damp hollows
    film = noise(nt, coord, 2.2, 4.0, 0.55)
    col = mix_color(nt, col, (0.040, 0.060, 0.018), remap(nt, film, 0.50, 0.62, 0.0, 0.75))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.96
    bump(nt, bsdf, math_node(nt, "ADD", clods, math_node(nt, "MULTIPLY", crumbs, 0.6)),
         0.6, 0.01)
    return mat


def litter_material():
    mat, nt, bsdf, coord = surface("LeafLitter")
    tone = attr(nt, "Tone")
    # mostly dead brown, a few still rust and ochre
    col = ramp(nt, tone, ((0.0, (0.060, 0.030, 0.012)), (0.40, (0.150, 0.070, 0.022)),
                          (0.70, (0.300, 0.120, 0.030)), (1.0, (0.450, 0.300, 0.070))))
    blot = noise(nt, coord, 35.0, 3.0, 0.6)
    col = mix_color(nt, col, (0.08, 0.04, 0.015), remap(nt, blot, 0.45, 0.75, 0.0, 0.5))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.75
    return mat


def fern_material():
    mat, nt, bsdf, coord = surface("Fern")
    tone = attr(nt, "Tone")
    zone = attr(nt, "Zone")
    col = ramp(nt, tone, ((0.0, (0.040, 0.120, 0.020)), (0.5, (0.070, 0.180, 0.030)),
                          (1.0, (0.110, 0.230, 0.040))))
    # the frond's tip is this season's growth, lighter
    col = mix_color(nt, col, (0.16, 0.30, 0.06), remap(nt, zone, 0.8, 1.0, 0.0, 0.6))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    return mat


def log_materials():
    """Nine slots, in index order: shared by the check and the render."""
    return (bark_material(), wood_material(), rot_material(), moss_material(),
            bracket_material(), toadstool_material(), soil_material(), litter_material(),
            fern_material())


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
            if b[1] >= a[3] or a[1] >= b[3]:
                continue
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
        mats = {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        remap_ = {vi: n for n, vi in enumerate(verts)}
        self.tree = BVHTree.FromPolygons(
            [tuple(p) for p in pts], [[remap_[v] for v in p.vertices] for p in polys])
        self.polys = polys


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    bark = [s for s in parts if s.mat == BARK_IDX]
    out["log"] = max(bark, key=lambda s: s.size.x) if bark else None
    out["stubs"] = [s for s in bark if s is not out["log"]]
    out["soil"] = [s for s in parts if s.mat == SOIL_IDX]
    out["fungi"] = [s for s in parts if s.mat == BRACKET_IDX]
    out["moss"] = [s for s in parts if s.mat == MOSS_IDX]
    out["leaves"] = [s for s in parts if s.mat == LITTER_IDX]
    out["toads"] = [s for s in parts if s.mat == TOAD_IDX]
    out["ferns"] = [s for s in parts if s.mat == FERN_IDX]
    return out


def contact_audit(log, soil):
    """Bury depth of every log vertex below the soil surface straight under
    it (a ray down onto the soil shell alone), binned along X."""
    down = Vector((0.0, 0.0, -1.0))
    bury = []
    for p in log.pts:
        loc, _n, _i, _d = soil.tree.ray_cast(Vector((p.x, p.y, 5.0)), down, 20.0)
        bury.append(loc.z - p.z if loc is not None else -1.0)
    x0 = log.lo.x
    nb = max(1, int(math.ceil((log.hi.x - x0) / STATION)))
    best = [-1.0] * nb
    for p, b in zip(log.pts, bury):
        k = min(nb - 1, int((p.x - x0) / STATION))
        best[k] = max(best[k], b)
    bedded = [BED_MIN <= b <= BED_MAX for b in best]
    contact = [p for p, b in zip(log.pts, bury) if b >= CONTACT_EPS]
    return sum(bedded) / nb, best, contact


def volume_centroid(me, shell):
    vol = 0.0
    acc = Vector((0.0, 0.0, 0.0))
    for poly in shell.polys:
        vs = [me.vertices[i].co for i in poly.vertices]
        for k in range(1, len(vs) - 1):
            a, b, c = vs[0], vs[k], vs[k + 1]
            v6 = a.dot(b.cross(c))
            vol += v6
            acc += v6 * (a + b + c)
    return acc / (4.0 * vol), vol / 6.0


def hull2d(pts):
    pts = sorted(set((round(p.x, 6), round(p.y, 6)) for p in pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def hull_margin(hull, q):
    """Signed distance of q inside a CCW hull (negative outside)."""
    if len(hull) < 3:
        return -9.0
    best = 9.0
    for a, b in zip(hull, hull[1:] + hull[:1]):
        ex, ey = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ex, ey)
        d = (ex * (q.y - a[1]) - ey * (q.x - a[0])) / ln
        best = min(best, d)
    return best


def fungus_audit(fungi, log):
    """Per shelf: its deepest vertex inside the log shell (signed distance
    to the nearest bark face along that face's outward normal)."""
    out = []
    for f in fungi:
        deepest = -9.0
        for p in f.pts:
            loc, nrm, _i, _d = log.tree.find_nearest(p)
            if loc is None:
                continue
            deepest = max(deepest, -(p - loc).dot(nrm))
        out.append(deepest)
    return out


def moss_audit(moss, log):
    """Area fraction of moss top faces (facing away from the bark under
    them) whose normal faces up or north, into the shade."""
    top = 0.0
    good = 0.0
    for m in moss:
        for poly in m.polys:
            loc, ln, _i, _d = log.tree.find_nearest(poly.center)
            if loc is None or poly.normal.dot(ln) < MOSS_TOP_DOT:
                continue
            a = poly.area
            top += a
            if poly.normal.z > MOSS_UP_Z or poly.normal.y > MOSS_SHADE_Y:
                good += a
    return (good / top if top else 0.0), top


def union_components(parts):
    n = len(parts)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(n), key=lambda i: parts[i].lo.x)
    for oi, i in enumerate(order):
        a = parts[i]
        for j in order[oi + 1:]:
            b = parts[j]
            if b.lo.x > a.hi.x:
                break
            if (a.lo.y > b.hi.y or b.lo.y > a.hi.y or a.lo.z > b.hi.z or b.lo.z > a.hi.z):
                continue
            if find(i) == find(j):
                continue
            if a.tree.overlap(b.tree):
                parent[find(i)] = find(j)
    return [find(i) for i in range(n)]


def cover_audit(cls):
    """Ground cover (leaves, toadstools, fern rachises and pinnae) joined to
    the soil through BVH overlaps: how many shells are not."""
    soil = cls["soil"][0]
    cover = cls["leaves"] + cls["toads"] + cls["ferns"]
    parts = [soil] + cover
    roots = union_components(parts)
    loose = [p for p, r in zip(parts[1:], roots[1:]) if r != roots[0]]
    loose_leaves = sum(1 for p in loose if p.mat == LITTER_IDX)
    return len(cover), len(loose), loose_leaves


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
    img = bpy.data.images.new("LogNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = BARK_IDX
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


def check(skip_decimate, lift_z=False, stray_vert=False, hump_ground=False,
          float_fungi=False, tilt_ground=False, sunny_moss=False, float_litter=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    plan = plan_log()
    flags = dict(hump_ground=hump_ground, tilt_ground=tilt_ground, float_fungi=float_fungi,
                 sunny_moss=sunny_moss, float_litter=float_litter)
    low = build_log_mesh("LogLow", plan, "low", **flags)
    high = build_log_mesh("LogHigh", plan, "high", **flags)
    mats = log_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    bark = mats[BARK_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        _co = [0.0] * (len(low.data.vertices) * 3)
        low.data.vertices.foreach_get("co", _co)
        _co[2::3] = [z + LIFT_Z for z in _co[2::3]]
        low.data.vertices.foreach_set("co", _co)
        low.data.update()

    none2 = (None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("log mesh did not build", 3),) + none2

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
    if cls["log"] is None or len(cls["soil"]) != 1:
        return (fail(f"log or soil shell not found: soil shells {len(cls['soil'])}", 3),) + none2
    log = cls["log"]
    soil = cls["soil"][0]
    frac, best, contact = contact_audit(log, soil)
    centroid, volume = volume_centroid(low.data, log)
    hull = hull2d(contact)
    margin = hull_margin(hull, centroid)
    depths = fungus_audit(cls["fungi"], log)
    moss_frac, moss_top = moss_audit(cls["moss"], log)
    ncover, nloose, loose_leaves = cover_audit(cls)

    img, tex = setup_bake_image(low, bark)
    if img is None:
        return (fail("log has no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "LogLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "LogLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("LogColSrc")
    collider = convex_hull_collider(collider_src, "LogCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_fallen_log_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    expected_fungi = len(plan["shelves"])
    expected_cover = (N_LEAVES + 2 * N_TOADS
                      + len(plan["ferns"]) * (1 + 2 * FERN_PINNAE))
    unbedded = [round(b, 3) for b in best if not (BED_MIN <= b <= BED_MAX)]
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
    print(f"measured shells={len(cls['all'])} stubs={len(cls['stubs'])} "
          f"fungi={len(cls['fungi'])} moss={len(cls['moss'])} leaves={len(cls['leaves'])} "
          f"toads={len(cls['toads'])} ferns={len(cls['ferns'])} "
          f"log_len={log.size.x:.4f} log_verts={len(log.pts)}")
    print(f"measured bedded={frac:.4f} stations={len(best)} "
          f"bury min={min(best):.4f} max={max(best):.4f} unbedded={unbedded[:12]}")
    print(f"measured centroid=({centroid.x:.4f},{centroid.y:.4f},{centroid.z:.4f}) "
          f"volume={volume:.4f} contact_verts={len(contact)} hull_margin={margin:.4f}")
    print(f"measured fungus_bite min={min(depths, default=-9):.4f} "
          f"max={max(depths, default=-9):.4f} n={len(depths)}")
    print(f"measured moss_up_shade={moss_frac:.4f} moss_top_area={moss_top:.4f}")
    print(f"measured cover={ncover} loose={nloose} loose_leaves={loose_leaves}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none2
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none2
    for idx, (floor, label) in enumerate(zip(FACE_FLOORS, MAT_LABELS)):
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{label} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + none2
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + none2
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + none2
    if (abs(size_x - OUTER_SIZE[0]) > BBOX_TOL or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
            or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL):
        return (fail(f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8),) + none2
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
                     "(--skip-decimate is the designed fail)", 9),) + none2
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9),) + none2
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + none2
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + none2
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + none2
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf}", 15),) + none2
    if bb[2] > ZMIN_EPS:
        return (fail(f"grounded zmin={bb[2]:.5f}", 16),) + none2
    if frac < BEDDED_MIN:
        return (fail(f"log bedded along {frac:.4f} of its length (min {BEDDED_MIN}); "
                     f"station bury band [{BED_MIN}, {BED_MAX}], off-band {unbedded[:8]}", 17),) + none2
    if (len(depths) != expected_fungi or min(depths) < FUNGUS_BITE_MIN
            or max(depths) > FUNGUS_BITE_MAX):
        return (fail(f"brackets rooted: {len(depths)}/{expected_fungi} shelves, deepest vertex "
                     f"in the bark {min(depths, default=-9):.4f}..{max(depths, default=-9):.4f} "
                     f"not in [{FUNGUS_BITE_MIN}, {FUNGUS_BITE_MAX}]", 18),) + none2
    if margin < HULL_MARGIN_MIN:
        return (fail(f"mass centre ({centroid.x:.4f},{centroid.y:.4f}) {margin:.4f} m inside "
                     f"the contact hull (min {HULL_MARGIN_MIN}): the log would roll", 19),) + none2
    if len(cls["moss"]) != len(MOSS) or moss_frac < MOSS_FRAC_MIN:
        return (fail(f"moss: {len(cls['moss'])}/{len(MOSS)} cushions, {moss_frac:.4f} of top "
                     f"area faces up or north (min {MOSS_FRAC_MIN})", 20),) + none2
    if ncover != expected_cover or nloose:
        return (fail(f"ground cover: {ncover}/{expected_cover} shells, {nloose} not rooted in "
                     f"the soil ({loose_leaves} leaves)", 21),) + none2
    return 0, low, bark


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

    # Key, fill, rim and the warm wedge, scaled for a 4 m mound.
    light("Key", (-4.5, -5.5, 7.0), 260.0, 3.0, (1.0, 0.95, 0.88), spread=11.0)
    light("Fill", (7.0, -4.0, 1.5), 8.0, 8.0, (0.72, 0.82, 1.0))
    light("Rim", (-2.0, 4.0, 3.5), 170.0, 3.0, (0.62, 0.78, 1.0))
    light("Wedge", (4.5, 1.5, 3.0), 420.0, 4.0, (1.0, 0.68, 0.38),
          target=(2.5, WALL_Y - 1.5, 0.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.50, -0.87, 0.0)).normalized()
    cam.location = centre + view * 5.6 + Vector((0.0, 0.0, 2.8))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((-0.22, 0.0, -0.16))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the moss.
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
    p.add_argument("--hump-ground", action="store_true")
    p.add_argument("--float-fungi", action="store_true")
    p.add_argument("--tilt-ground", action="store_true")
    p.add_argument("--sunny-moss", action="store_true")
    p.add_argument("--float-litter", action="store_true")
    args = p.parse_args(argv)

    code, low, _bark = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        hump_ground=args.hump_ground,
        float_fungi=args.float_fungi,
        tilt_ground=args.tilt_ground,
        sunny_moss=args.sunny_moss,
        float_litter=args.float_litter,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("fallen-log OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
