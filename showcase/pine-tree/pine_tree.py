"""Game-ready Scots pine — a showcase piece, not an example.

Asserts budget conformance of a procedural conifer after composing shipped
pipeline pieces: bmesh construction, UVs, four materials, high-to-low
normal bake, LOD chain, convex trunk collider, Unity glTF export.

The trunk is one lathe from a buttressed root flare to the leader: it
tapers, sways a little, and carries vertical bark ridges. Five surface
roots leave the flare and dive into the ground. Ten whorls of branches
rise in tiers above a bare lower bole; each whorl has 4-6 branches whose
count, yaw, length, rise and droop come from a fixed seed. Each branch is
a tapered limb seated in the trunk, carrying side shoots, and the outer
shoots carry faceted bottlebrush needle masses: the inner limbs are bare,
as a pine's are, so the tiers read as branches rather than a stack of
cones. A few dead stubs and two dead lower branches stay on the bole, and
clusters of cones hang in the upper crown.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-branches`` the branch seat
in the trunk, ``--lean-crown`` trunk plumb, ``--bunch-whorls`` the whorl
tier spacing, ``--drop-cones`` one connected assembly.

Seeded, not random: ``random.Random(SEED)`` draws the whole plan before
anything is built, so flags never shift the stream. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python pine_tree.py --
    blender --background --python pine_tree.py -- --skip-decimate
    blender --background --python pine_tree.py -- --output pine.png
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

SEED = 1759

# --- Trunk -----------------------------------------------------------------
TRUNK_TOP = 7.00        # leader tip ring; a bud closes it
TRUNK_R_BASE = 0.158    # taper term at z = 0 (above the flare)
TRUNK_R_TIP = 0.010
TRUNK_TAPER = 1.25
TRUNK_SIDES = 20
TRUNK_SIDES_HIGH = 40
RIDGES = 10             # vertical bark ridges round the girth
RIDGE_AMP = 0.050       # fraction of the radius
FLARE_R = 0.190         # extra radius at the ground, on the buttress lobes
FLARE_H = 0.28
FLARE_LOBES = 5
SWAY = (0.022, 0.018)   # trunk axis sway, x and y amplitude (m)
DBH_Z = 1.30            # breast height

# --- Roots -----------------------------------------------------------------
ROOT_SIDES = 8
ROOT_REACH = (0.62, 0.82)

# --- Whorls and branches ----------------------------------------------------
WHORLS = 10
WHORL_Z0 = 1.85
WHORL_STEP = 0.575
WHORL_STEP_SHRINK = 0.011
WHORL_STEP_JITTER = 0.035
BRANCHES = (4, 6)       # per whorl, inclusive
BRANCH_L_MIN = 0.30
BRANCH_L_SPAN = 1.72
BRANCH_SEAT = 0.45      # limb base centre, as a fraction of the trunk radius
LIMB_SIDES = 6
TWIG_SIDES = 4
NEEDLE_L = 0.170        # needle tuft length off a shoot's core
SHOOT_SIDES = 4
SHOOT_STEP = 0.120      # ring spacing along a shoot
SHOOT_CORE = 0.24       # shoot core radius / needle length
SHOOT_LEAN = 1.00       # needles lean forward along the shoot
CONE_LEN = 0.095
CONE_R = 0.028

# --- Dead wood -------------------------------------------------------------
STUBS = ((0.72, 0.9), (0.98, 3.1), (1.38, 4.9), (1.62, 2.0))  # (z, yaw)
DEAD_BRANCHES = ((1.18, 5.6, 0.62), (1.50, 1.2, 0.48))     # (z, yaw, length)

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (4.775, 5.261, 7.226)
BASE_TRIS_MIN = 32500
BASE_TRIS_MAX = 36000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 4
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 60
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
BARK_FACES_MIN = 3900
NEEDLE_FACES_MIN = 20500
CONE_FACES_MIN = 1400
DEAD_FACES_MIN = 150

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Branch seat: each limb's (and dead stub's) base centre sits inside the
# trunk, measured as its radial distance from the trunk axis at that height
# over the trunk surface's radius on the same bearing (raycast from the axis).
SEAT_RATIO_MIN = 0.25
SEAT_RATIO_MAX = 0.75
FLOAT_BRANCHES = 1.20   # --float-branches starts every limb at 1.2 x radius
LIMB_REACH = 0.08       # a bark shell within this of the trunk surface is a limb
# Whorl tiers: limb bases cluster into whorls; gaps between whorls in band.
WHORL_SPLIT = 0.18
WHORL_SPREAD_MAX = 0.06
WHORL_GAP_MIN = 0.40
WHORL_GAP_MAX = 0.68
BUNCH_WHORL = 5
BUNCH_LIFT = 0.30
# Plumb and balance: trunk lean from ring centroids, the needle mass's
# centre over the trunk base, and the breast-height diameter.
LEAN_MAX_DEG = 1.0
BALANCE_MAX = 0.15      # needle-area centroid off the base axis, m
DBH = 0.266
DBH_TOL = 0.020
LEAN_BEND = 0.0075      # --lean-crown bends the axis x += k (z - z0)^2
LEAN_Z0 = 1.0
DROP_CONES = 0.05
# Hero yaw about Z only (level on the stage).
HERO_YAW_DEG = 80.0
WALL_Y = 9.0

BARK_IDX = 0
NEEDLE_IDX = 1
CONE_IDX = 2
DEAD_IDX = 3


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
# The plan: every seeded draw happens here, before anything is built
# --------------------------------------------------------------------------

def trunk_radius(z):
    t = max(0.0, 1.0 - z / TRUNK_TOP)
    return TRUNK_R_TIP + TRUNK_R_BASE * t ** TRUNK_TAPER


def axis_at(z, lean=0.0):
    """Trunk axis centre at height z: a closed-form sway, zero at the ground."""
    x = SWAY[0] * (math.sin(1.1 * z + 0.3) - math.sin(0.3))
    y = SWAY[1] * (math.sin(0.8 * z + 1.9) - math.sin(1.9))
    if lean:
        x += lean * max(0.0, z - LEAN_Z0) ** 2
    return Vector((x, y, z))


def plan_tree():
    rng = random.Random(SEED)

    def u(a, b):
        return a + (b - a) * rng.random()

    whorls = []
    z = WHORL_Z0
    top = TRUNK_TOP + 0.1
    for i in range(WHORLS):
        if i:
            z += WHORL_STEP - WHORL_STEP_SHRINK * i + u(-WHORL_STEP_JITTER, WHORL_STEP_JITTER)
        f = (z - WHORL_Z0) / (top - WHORL_Z0)
        n = BRANCHES[0] + min(BRANCHES[1] - BRANCHES[0], int(rng.random() * 3.0))
        yaw0 = i * math.radians(137.5) + u(-0.3, 0.3)
        branches = []
        for k in range(n):
            reach = BRANCH_L_MIN + BRANCH_L_SPAN * ((top - z) / (top - WHORL_Z0)) ** 1.1
            br = {
                "z": z + u(-0.018, 0.018),
                "yaw": yaw0 + 2.0 * math.pi * k / n + u(-0.32, 0.32),
                "L": reach * u(0.76, 1.12),
                "elev": math.radians(-6.0 + 44.0 * f + u(-6.0, 6.0)),
                "droop": (0.26 - 0.20 * f) * u(0.7, 1.25),
                "curl": u(-0.38, 0.38),
                "tipup": u(0.05, 0.12),
                "tone": rng.random(),
                "twig_jit": [rng.random() for _ in range(12)],
                "brush_tones": [rng.random() for _ in range(8)],
                "cones": (f > 0.35 and rng.random() < 0.34),
                "cone_jit": [rng.random() for _ in range(6)],
            }
            branches.append(br)
        whorls.append({"z": z, "branches": branches})
    roots = []
    for k in range(FLARE_LOBES):
        roots.append({"yaw": 2.0 * math.pi * k / FLARE_LOBES + 0.35 + u(-0.12, 0.12),
                      "reach": u(*ROOT_REACH), "tone": rng.random()})
    leader_tone = rng.random()
    return {"whorls": whorls, "roots": roots, "leader_tone": leader_tone}


# --------------------------------------------------------------------------
# Construction helpers
# --------------------------------------------------------------------------

def _mark(faces, mat_idx, tone_layer=None, tone=0.0):
    for f in faces:
        f.material_index = mat_idx
        if tone_layer is not None:
            f[tone_layer] = tone


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


def add_tapered_tube(bm, pts, radii, sides, mat_idx, layer, tone, phase=0.0, jag=None):
    """Capped round bar swept along a polyline with a radius per point.
    ``jag``: per-vertex radial factors for the last ring (a broken end)."""
    pts = [Vector(p) for p in pts]
    rings = []
    fr = frames(pts)
    for idx, (p, (t, n, b)) in enumerate(zip(pts, fr)):
        ring = []
        for k in range(sides):
            a = phase + 2.0 * math.pi * k / sides
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
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx, layer, tone)
    return faces


def add_shoot(bm, pts, needle, layer, tone, seed):
    """A needled shoot: a thin core swept along ``pts`` whose every quad is
    pulled out into a needle tuft pointing forward along the shoot, closed
    by a terminal tuft at the tip. One closed shell."""
    pts = resample([Vector(p) for p in pts], SHOOT_STEP)
    fr = frames(pts)
    sides = SHOOT_SIDES
    core = needle * SHOOT_CORE
    rings = []
    for idx, (p, (t, nrm, bi)) in enumerate(zip(pts, fr)):
        ring = []
        for j in range(sides):
            a = 2.0 * math.pi * j / sides + idx * math.pi / sides
            ring.append(bm.verts.new(p + core * (nrm * math.cos(a) + bi * math.sin(a))))
        rings.append(ring)
    tip_layer = bm.faces.layers.float.get("Tip")
    faces = []
    k = 0
    nseg = len(rings) - 1
    for idx, (r0, r1) in enumerate(zip(rings, rings[1:])):
        t = fr[idx][0].lerp(fr[idx + 1][0], 0.5).normalized()
        for j in range(sides):
            m = (j + 1) % sides
            q = (r0[j], r0[m], r1[m], r1[j])
            c = sum((v.co for v in q), Vector()) / 4.0
            out = c - pts[idx].lerp(pts[idx + 1], 0.5)
            out = (out - t * out.dot(t)).normalized()
            # closed-form scatter of needle length and lean, per tuft
            h = math.sin(seed * 12.9898 + k * 78.233) * 43758.5453
            h -= math.floor(h)
            k += 1
            ln = needle * (0.78 + 0.44 * h)
            apex = bm.verts.new(c + out * ln + t * (ln * SHOOT_LEAN))
            for e in range(4):
                fc = bm.faces.new((q[e], q[(e + 1) % 4], apex))
                fc[tip_layer] = (idx + 0.5) / nseg
                faces.append(fc)
    t0 = fr[0][0]
    t1 = fr[-1][0]
    start = bm.verts.new(pts[0] - t0 * core * 1.5)
    end = bm.verts.new(pts[-1] + t1 * needle * 1.15)
    for j in range(sides):
        m = (j + 1) % sides
        fa = bm.faces.new((rings[0][m], rings[0][j], start))
        fb = bm.faces.new((rings[-1][j], rings[-1][m], end))
        fa[tip_layer] = 0.0
        fb[tip_layer] = 1.0
        faces += [fa, fb]
    _mark(faces, NEEDLE_IDX, layer, tone)
    for fc in faces:
        fc.smooth = False
    return faces


def resample(pts, step):
    """Polyline resampled at (about) ``step`` spacing, ends kept."""
    lens = [(b - a).length for a, b in zip(pts, pts[1:])]
    total = sum(lens)
    n = max(2, int(round(total / step)))
    out = []
    for i in range(n + 1):
        d = total * i / n
        for (a, b), ln in zip(zip(pts, pts[1:]), lens):
            if d <= ln or (a, b) == (pts[-2], pts[-1]):
                out.append(a.lerp(b, min(1.0, d / ln if ln else 0.0)))
                break
            d -= ln
    return out


def add_cone(bm, top, axis, layer, tone, spin):
    """A closed pine cone hanging from ``top`` along ``axis``: stepped scale
    rings, each turned half a scale from the last."""
    axis = axis.normalized()
    ref = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    u_ = axis.cross(ref).normalized()
    w_ = axis.cross(u_)
    prof = [(0.30, 0.00), (0.72, 0.14), (0.96, 0.30), (1.00, 0.48), (0.88, 0.66),
            (0.62, 0.82), (0.30, 0.95)]
    sides = 8
    rings = []
    for k, (rf, zf) in enumerate(prof):
        ring = []
        for j in range(sides):
            a = spin + 2.0 * math.pi * j / sides + k * math.pi / sides
            rr = CONE_R * rf * (1.0 + 0.10 * ((j + k) % 2))
            ring.append(bm.verts.new(top + axis * (CONE_LEN * zf)
                                     + rr * (u_ * math.cos(a) + w_ * math.sin(a))))
        rings.append(ring)
    cap0 = bm.verts.new(top - axis * 0.004)
    tip = bm.verts.new(top + axis * CONE_LEN)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(sides):
            m = (j + 1) % sides
            faces.append(bm.faces.new((r0[j], r0[m], r1[m], r1[j])))
    for j in range(sides):
        m = (j + 1) % sides
        faces.append(bm.faces.new((rings[0][m], rings[0][j], cap0)))
        faces.append(bm.faces.new((rings[-1][j], rings[-1][m], tip)))
    _mark(faces, CONE_IDX, layer, tone)
    for fc in faces:
        fc.smooth = False
    return faces


def trunk_ring_z():
    zs = [0.0, 0.03, 0.08, 0.15, 0.25, 0.38, 0.55, 0.75, 1.0]
    z = 1.3
    while z < TRUNK_TOP - 0.15:
        zs.append(round(z, 4))
        z += 0.3
    zs += [TRUNK_TOP - 0.08, TRUNK_TOP]
    return zs


def add_trunk(bm, layer, tone, sides, lean, collider=False):
    """One lathe from the flare to the leader tip, closed flat at the ground
    and by a bud point at the top."""
    rings = []
    for z in trunk_ring_z():
        c = axis_at(z, lean)
        rn = trunk_radius(z)
        flare = math.exp(-z / FLARE_H)
        ring = []
        for j in range(sides):
            a = 2.0 * math.pi * j / sides
            lobe = 0.5 + 0.5 * math.cos(FLARE_LOBES * (a - 0.35))
            r = rn + FLARE_R * flare * (0.30 + 0.70 * lobe * lobe)
            if not collider:
                # ridges: cos(RIDGES a) sampled on the lathe's own vertices,
                # so the high (40) and low (20) builds carry the same furrows
                r *= 1.0 + RIDGE_AMP * math.cos(RIDGES * a + 0.4 * math.sin(2.1 * z))
            ring.append(bm.verts.new(c + Vector((r * math.cos(a), r * math.sin(a), 0.0))))
        rings.append(ring)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(sides):
            m = (j + 1) % sides
            faces.append(bm.faces.new((r0[j], r0[m], r1[m], r1[j])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    bud = bm.verts.new(axis_at(TRUNK_TOP, lean) + Vector((0.0, 0.0, 0.05)))
    for j in range(sides):
        m = (j + 1) % sides
        faces.append(bm.faces.new((rings[-1][j], rings[-1][m], bud)))
    _mark(faces, BARK_IDX, layer, tone)


def limb_path(br, base, steps=6):
    """Branch centreline from its base: out along its yaw, rising at its
    elevation, sagging with droop and turning up again at the tip."""
    pts = []
    L = br["L"]
    for i in range(steps):
        s = i / (steps - 1)
        yaw = br["yaw"] + br["curl"] * s
        h = Vector((math.cos(yaw), math.sin(yaw), 0.0))
        run = s * L * math.cos(br["elev"])
        rise = s * L * math.sin(br["elev"]) - br["droop"] * L * s * s + br["tipup"] * L * s ** 5
        # a crooked limb, not a dowel: closed-form kinks that vanish at the base
        ph = br.get("tone", 0.0) * 6.283
        side = Vector((-h.y, h.x, 0.0)) * (0.045 * L * s * math.sin(7.0 * s + ph))
        rise += 0.025 * L * s * math.sin(9.0 * s + 2.0 * ph)
        pts.append(base + h * run + side + Vector((0.0, 0.0, rise)))
    return pts


def sample(pts, s):
    """Point at parameter s in [0, 1] along a polyline of equal steps."""
    n = len(pts) - 1
    x = min(max(s, 0.0), 1.0) * n
    i = min(int(x), n - 1)
    f = x - i
    return pts[i].lerp(pts[i + 1], f), (pts[i + 1] - pts[i]).normalized()


def build_tree_mesh(name, plan, detail="low", float_branches=False, lean_crown=False,
                    bunch_whorls=False, drop_cones=False):
    lean = LEAN_BEND if lean_crown else 0.0
    bm = bmesh.new()
    try:
        tone_layer = bm.faces.layers.float.new("Tone")
        bm.faces.layers.float.new("Tip")   # needle shoots: 0 at the base, 1 at the tip
        sides = TRUNK_SIDES_HIGH if detail == "high" else TRUNK_SIDES
        up = Vector((0.0, 0.0, 1.0))

        add_trunk(bm, tone_layer, 0.1, sides, lean)

        # surface roots: from inside the flare, out and down into the ground
        for rt in plan["roots"]:
            h = Vector((math.cos(rt["yaw"]), math.sin(rt["yaw"]), 0.0))
            reach = rt["reach"]
            c0 = axis_at(0.0, lean)
            prof = [(0.05, 0.38, 0.100), (0.32, 0.20, 0.090), (0.56, 0.085, 0.064),
                    (0.80, 0.020, 0.040), (1.00, -0.010, 0.018)]
            pts = [c0 + h * (reach * rf) + Vector((0.0, 0.0, zc)) for rf, zc, _r in prof]
            radii = [r for _rf, _zc, r in prof]
            add_tapered_tube(bm, pts, radii, ROOT_SIDES, BARK_IDX, tone_layer, rt["tone"])

        # dead stubs and dead lower branches
        dead_tone = 0.3
        for z, yaw in STUBS:
            c = axis_at(z, lean)
            h = Vector((math.cos(yaw), math.sin(yaw), -0.25)).normalized()
            base = c + Vector((h.x, h.y, 0.0)).normalized() * (BRANCH_SEAT * trunk_radius(z))
            ln = trunk_radius(z) * (1.0 - BRANCH_SEAT) + 0.06 + 0.02 * (yaw % 1.0)
            rb = 0.030
            pts = [base, base + h * (ln * 0.55), base + h * ln]
            jag = [(0.85, 0.012), (1.0, -0.006), (0.75, 0.020), (0.95, -0.010),
                   (0.80, 0.016), (1.0, 0.0)]
            add_tapered_tube(bm, pts, [rb, rb * 0.92, rb * 0.82], 6, DEAD_IDX, tone_layer,
                             dead_tone, jag=jag)
        for z, yaw, ln in DEAD_BRANCHES:
            c = axis_at(z, lean)
            br = {"yaw": yaw, "L": ln, "elev": math.radians(-14.0), "droop": 0.20,
                  "curl": 0.15, "tipup": 0.0}
            h = Vector((math.cos(yaw), math.sin(yaw), 0.0))
            base = c + h * (BRANCH_SEAT * trunk_radius(z))
            pts = limb_path(br, base, steps=5)
            add_tapered_tube(bm, pts, [0.024, 0.019, 0.014, 0.009, 0.005], 5, DEAD_IDX,
                             tone_layer, dead_tone + 0.2)
            for s, side in ((0.45, 1.0), (0.7, -1.0)):
                p, t = sample(pts, s)
                d = (Matrix.Rotation(side * 0.9, 3, "Z") @ t)
                d.z -= 0.25
                d.normalize()
                add_tapered_tube(bm, [p, p + d * 0.12, p + d * 0.22], [0.008, 0.006, 0.003],
                                 4, DEAD_IDX, tone_layer, dead_tone + 0.1)

        # the live crown
        for wi, wh in enumerate(plan["whorls"]):
            for br in wh["branches"]:
                z = br["z"] + (BUNCH_LIFT if bunch_whorls and wi == BUNCH_WHORL else 0.0)
                c = axis_at(z, lean)
                h0 = Vector((math.cos(br["yaw"]), math.sin(br["yaw"]), 0.0))
                R = trunk_radius(z)
                base = c + h0 * (BRANCH_SEAT * R)
                pts = limb_path(br, base)
                L = br["L"]
                rb = min(0.010 + 0.020 * L, 0.48 * R + 0.004)
                radii = [rb * (1.0 - 0.72 * i / (len(pts) - 1)) for i in range(len(pts))]
                limb_pts = list(pts)
                if float_branches:
                    # the tube starts outside the bark; the path, and so the
                    # tip and everything hung on it, is unchanged
                    d0 = (pts[1] - pts[0]).normalized()
                    hd = Vector((d0.x, d0.y, 0.0))
                    k = (FLOAT_BRANCHES - BRANCH_SEAT) * R / max(hd.length, 1e-6)
                    limb_pts[0] = pts[0] + d0 * k
                add_tapered_tube(bm, limb_pts, radii, LIMB_SIDES, BARK_IDX, tone_layer,
                                 0.55 + 0.4 * br["tone"], phase=br["yaw"])

                bt = br["brush_tones"]
                jit = br["twig_jit"]
                needle = NEEDLE_L * (0.85 + 0.12 * min(L, 1.8))
                seed = br["tone"] * 100.0
                # the leading shoot: the limb's last quarter, turned up past
                # the tip, with two laterals forking off it on longer limbs
                p_a, _ = sample(pts, 0.76)
                p_b, t_b = sample(pts, 1.0)
                lead = (t_b + up * 0.55).normalized()
                tip_len = 0.14 + 0.07 * L
                add_shoot(bm, [p_a, p_a.lerp(p_b, 0.5), p_b, p_b + lead * tip_len],
                          needle, tone_layer, bt[0], seed)
                if L > 0.8:
                    for side in (-1.0, 1.0):
                        # staggered, so the two forks never share a start
                        p, t = sample(pts, 0.86 + 0.035 * side)
                        d = Matrix.Rotation(side * 0.62, 3, "Z") @ Vector((t.x, t.y, 0.0))
                        d = (d.normalized() + up * 0.42).normalized()
                        ln = 0.20 + 0.08 * L
                        add_shoot(bm, [p, p + d * (ln * 0.5), p + d * ln + up * 0.04],
                                  needle * 0.92, tone_layer, bt[1 if side < 0 else 2],
                                  seed + side * 3.0)

                # side branches, alternating, each ending in its own shoots
                n_twigs = max(0, min(5, int(round(L / 0.34))))
                for k in range(n_twigs):
                    s = 0.34 + 0.40 * (k + 0.5) / max(n_twigs, 1) + 0.04 * (jit[k] - 0.5)
                    side = 1.0 if k % 2 == 0 else -1.0
                    p, t = sample(pts, s)
                    ang = side * (0.80 + 0.40 * jit[k + 5])
                    d = Matrix.Rotation(ang, 3, "Z") @ Vector((t.x, t.y, 0.0)).normalized()
                    d = (d + up * (0.16 + 0.20 * jit[k + 6])).normalized()
                    tl = (0.25 + 0.30 * (1.0 - s)) * min(L, 1.9) * 0.62 + 0.10
                    q1 = p + d * (tl * 0.5)
                    q2 = p + d * tl + up * (0.04 * tl)
                    tr = max(0.006, 0.42 * rb * (1.0 - 0.72 * s))
                    add_tapered_tube(bm, [p, q1, q2], [tr, tr * 0.75, tr * 0.5], TWIG_SIDES,
                                     BARK_IDX, tone_layer, 0.6 + 0.4 * br["tone"])
                    b0 = p.lerp(q2, 0.42)
                    b3 = q2 + (d + up * 0.7).normalized() * (0.10 + 0.12 * tl)
                    add_shoot(bm, [b0, b0.lerp(q2, 0.5), q2, b3],
                              needle * (0.88 + 0.16 * jit[k + 3]), tone_layer, bt[3 + k],
                              seed + 7.0 + k)
                    if tl > 0.30:
                        # a lateral off the side branch, forking forward
                        pl = p.lerp(q2, 0.62)
                        dl = Matrix.Rotation(-side * 0.7, 3, "Z") @ Vector((d.x, d.y, 0.0))
                        dl = (dl.normalized() + up * 0.45).normalized()
                        add_shoot(bm, [pl, pl + dl * 0.11, pl + dl * 0.22],
                                  needle * 0.85, tone_layer, bt[(4 + k) % 8], seed + 11.0 + k)

                # cones hang under the limb, a cluster of two or three
                if br["cones"]:
                    cj = br["cone_jit"]
                    count = 2 + (1 if cj[0] > 0.5 else 0)
                    for m in range(count):
                        s = 0.60 + 0.06 * m + 0.03 * cj[m + 1]
                        p, t = sample(pts, s)
                        r_here = rb * (1.0 - 0.72 * s)
                        outward = Vector((t.x, t.y, 0.0)).normalized()
                        spin_side = Matrix.Rotation((m - 1) * 0.9, 3, "Z") @ outward
                        axis = (-up * 1.0 + spin_side * 0.45).normalized()
                        top = p - up * (r_here * 0.3)
                        if drop_cones:
                            top = top - up * DROP_CONES
                        add_cone(bm, top, axis, tone_layer, cj[m + 2], spin=cj[m + 3] * 3.0)

        # the leader's own needles, round the top of the trunk
        zt = TRUNK_TOP
        l0 = axis_at(zt - 0.46, lean)
        l1 = axis_at(zt - 0.20, lean)
        l2 = axis_at(zt, lean)
        l3 = l2 + up * 0.06
        add_shoot(bm, [l0, l1, l2, l3], NEEDLE_L * 0.85, tone_layer, plan["leader_tone"], 5.0)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        # roots dive into the ground: whatever is below z = 0 is bedded flat
        # on it (the trunk's own bottom cap is at z = 0 already)
        for v in bm.verts:
            if v.co.z < 0.0:
                v.co.z = 0.0
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
        # Wood is smooth-shaded (the ridges and taper carry in the silhouette);
        # needle masses and cones stay faceted, and every material boundary
        # is a hard edge.
        for face in bm.faces:
            if face.material_index in (BARK_IDX, DEAD_IDX):
                face.smooth = True
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if len(mats) > 1 or not edge.is_manifold or len(edge.link_faces) != 2:
                edge.smooth = False
            elif mats <= {BARK_IDX, DEAD_IDX}:
                edge.smooth = edge.calc_face_angle() < math.radians(50.0)
            else:
                edge.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def build_collider_source(name, plan):
    """The trunk alone, without ridges: players walk under the branches."""
    bm = bmesh.new()
    try:
        layer = bm.faces.layers.float.new("Tone")
        add_trunk(bm, layer, 0.5, TRUNK_SIDES, 0.0, collider=True)
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


def surface(name, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = metallic
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


def tone_attr(nt):
    node = nt.nodes.new("ShaderNodeAttribute")
    node.attribute_type = "GEOMETRY"
    node.attribute_name = "Tone"
    return node.outputs["Fac"]


def bark_material():
    mat, nt, bsdf, coord = surface("PineBark")
    # Scots pine: thick grey-brown plates on the lower bole, thin fox-red
    # flaking bark above. Plates are noise squeezed round the girth and
    # stretched up it, so the fissures run vertically.
    plates = noise(nt, mapping(nt, coord, scale=(9.0, 9.0, 2.2)), 3.0, 8.0, 0.62)
    flakes = noise(nt, mapping(nt, coord, scale=(26.0, 26.0, 9.0)), 1.0, 5.0, 0.55)
    low = ramp(nt, plates, ((0.36, (0.030, 0.022, 0.017)), (0.50, (0.085, 0.062, 0.046)),
                            (0.66, (0.150, 0.118, 0.090)), (0.82, (0.200, 0.165, 0.130))))
    high = ramp(nt, flakes, ((0.30, (0.230, 0.090, 0.040)), (0.55, (0.420, 0.180, 0.075)),
                             (0.80, (0.560, 0.290, 0.140))))
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    zmix = math_node(nt, "ADD", sep.outputs["Z"], remap(nt, plates, 0.3, 0.7, -0.5, 0.5))
    fac = remap(nt, zmix, 2.4, 4.4, 0.0, 1.0)
    col = mix_color(nt, low, high, fac)
    tone = tone_attr(nt)
    col = mix_color(nt, col, (0.05, 0.035, 0.025), remap(nt, tone, 0.0, 1.0, 0.0, 0.45))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, plates, 0.35, 0.8, 0.92, 0.72), bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.8
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(plates, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def needle_material():
    mat, nt, bsdf, coord = surface("PineNeedles")
    # Blue-green Scots pine needles: each mass takes its own tone, and a
    # fine speckle breaks the facets up so they read as needles, not plastic.
    tone = tone_attr(nt)
    base = ramp(nt, tone, ((0.0, (0.030, 0.062, 0.030)), (0.5, (0.048, 0.090, 0.040)),
                           (1.0, (0.075, 0.120, 0.050))))
    speck = noise(nt, coord, 90.0, 3.0, 0.7)
    col = mix_color(nt, base, (0.018, 0.034, 0.020), remap(nt, speck, 0.35, 0.7, 0.55, 0.0))
    # this year's growth: the last hand-width of every shoot is a lighter,
    # yellower green
    tip = nt.nodes.new("ShaderNodeAttribute")
    tip.attribute_type = "GEOMETRY"
    tip.attribute_name = "Tip"
    col = mix_color(nt, col, (0.130, 0.175, 0.060),
                    remap(nt, tip.outputs["Fac"], 0.55, 1.0, 0.0, 0.55))
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(remap(nt, speck, 0.3, 0.7, 0.86, 0.66), bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    return mat


def cone_material():
    mat, nt, bsdf, coord = surface("PineCone")
    tone = tone_attr(nt)
    blot = noise(nt, coord, 60.0, 4.0, 0.6)
    base = ramp(nt, blot, ((0.35, (0.110, 0.066, 0.036)), (0.65, (0.260, 0.165, 0.090))))
    col = mix_color(nt, base, (0.16, 0.12, 0.09), remap(nt, tone, 0.0, 1.0, 0.0, 0.35))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.72
    return mat


def deadwood_material():
    mat, nt, bsdf, coord = surface("PineDeadwood")
    # Weathered, barkless: silver-grey with dark checks.
    streak = noise(nt, mapping(nt, coord, scale=(30.0, 30.0, 6.0)), 2.0, 6.0, 0.6)
    col = ramp(nt, streak, ((0.35, (0.070, 0.062, 0.055)), (0.55, (0.200, 0.186, 0.165)),
                            (0.80, (0.310, 0.292, 0.262))))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    return mat


def tree_materials():
    """(bark, needles, cone, deadwood): shared by the check and the render."""
    return bark_material(), needle_material(), cone_material(), deadwood_material()


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
        self.centre = (self.lo + self.hi) * 0.5
        mats = {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        remap_ = {vi: n for n, vi in enumerate(verts)}
        self.tree = BVHTree.FromPolygons(
            [tuple(p) for p in pts], [[remap_[v] for v in p.vertices] for p in polys])
        self.polys = polys


class TrunkAxis:
    """Trunk ring centroids read off the mesh: every lathe ring shares one z."""

    def __init__(self, trunk):
        rings = {}
        for p in trunk.pts:
            rings.setdefault(round(p.z, 5), []).append(p)
        # a ring has the lathe's full side count; the bud apex is a single vertex
        full = max(len(v) for v in rings.values())
        self.rings = []
        for z in sorted(rings):
            ps = rings[z]
            if len(ps) != full:
                continue
            c = sum(ps, Vector()) / len(ps)
            r = sum(((q - c).to_2d().length for q in ps)) / len(ps)
            self.rings.append((z, c, r))

    def radius(self, z):
        rs = self.rings
        if z <= rs[0][0]:
            return rs[0][2]
        for (z0, _c0, r0), (z1, _c1, r1) in zip(rs, rs[1:]):
            if z <= z1:
                return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
        return rs[-1][2]

    def centre(self, z):
        rs = self.rings
        if z <= rs[0][0]:
            return rs[0][1].copy()
        for (z0, c0, _r0), (z1, c1, _r1) in zip(rs, rs[1:]):
            if z <= z1:
                return c0.lerp(c1, (z - z0) / (z1 - z0))
        return rs[-1][1].copy()


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    bark = [s for s in parts if s.mat == BARK_IDX]
    trunk = [s for s in bark if s.size.z > 5.0]
    out["trunk"] = trunk
    if len(trunk) != 1:
        return out
    ax = TrunkAxis(trunk[0])
    out["axis"] = ax
    out["roots"] = [s for s in bark if s is not trunk[0] and s.hi.z < 0.5]

    def starts_inside(s):
        return min((p - ax.centre(p.z)).to_2d().length - ax.radius(p.z)
                   for p in s.pts) < LIMB_REACH

    # a limb (or a dead stub) starts at the trunk; a side shoot starts on
    # its limb, out in the crown. The seat audit then says whether a limb's
    # base is actually inside the bark.
    others = [s for s in bark if s is not trunk[0] and s not in out["roots"]]
    out["limbs"] = [s for s in others if starts_inside(s)]
    out["twigs"] = [s for s in others if not starts_inside(s)]
    dead = [s for s in parts if s.mat == DEAD_IDX]
    out["dead_seated"] = [s for s in dead if starts_inside(s)]
    out["brushes"] = [s for s in parts if s.mat == NEEDLE_IDX]
    out["cones"] = [s for s in parts if s.mat == CONE_IDX]
    return out


def member_base(s, ax, n):
    """Centroid of the ``n`` vertices nearest the trunk axis: the base ring."""
    ranked = sorted(s.pts, key=lambda p: (p - ax.centre(p.z)).to_2d().length)
    ring = ranked[:n]
    return sum(ring, Vector()) / len(ring)


def seat_audit(cls):
    """Per limb and seated dead member: base-centre radial distance over the
    trunk surface radius on the same bearing (raycast from the axis)."""
    ax = cls["axis"]
    trunk = cls["trunk"][0]
    ratios = [_seat_ratio(s, LIMB_SIDES, ax, trunk) for s in cls["limbs"]]
    for s in cls["dead_seated"]:
        # stubs are 6-sided (3 rings), dead branches 5-sided (5 rings)
        n = 6 if len(s.pts) == 18 else 5
        ratios.append(_seat_ratio(s, n, ax, trunk))
    return ratios


def _seat_ratio(s, n, ax, trunk):
    b = member_base(s, ax, n)
    c = ax.centre(b.z)
    d = (b - c).to_2d()
    dist = d.length
    if dist < 1e-6:
        return 0.0
    direction = Vector((d.x, d.y, 0.0)).normalized()
    hit, _n, _i, surf = trunk.tree.ray_cast(Vector((c.x, c.y, b.z)), direction, 2.0)
    if hit is None:
        return 9.0
    return dist / surf


def whorl_audit(cls):
    """Cluster limb base heights into whorls; gaps, spreads, counts."""
    ax = cls["axis"]
    zs = sorted(member_base(s, ax, LIMB_SIDES).z for s in cls["limbs"])
    tiers = []
    for z in zs:
        if tiers and z - tiers[-1][-1] < WHORL_SPLIT:
            tiers[-1].append(z)
        else:
            tiers.append([z])
    heights = [sum(t) / len(t) for t in tiers]
    gaps = [b - a for a, b in zip(heights, heights[1:])]
    spreads = [max(t) - min(t) for t in tiers]
    counts = [len(t) for t in tiers]
    return heights, gaps, spreads, counts


def plumb_audit(me, cls):
    """Trunk lean (line fit to ring centroids), needle-mass balance over the
    base, and breast-height diameter."""
    ax = cls["axis"]
    rings = [(z, c) for z, c, _r in ax.rings if 0.8 <= z <= TRUNK_TOP - 1.0]
    n = len(rings)
    mz = sum(z for z, _c in rings) / n
    mx = sum(c.x for _z, c in rings) / n
    my = sum(c.y for _z, c in rings) / n
    szz = sum((z - mz) ** 2 for z, _c in rings)
    sx = sum((z - mz) * (c.x - mx) for z, c in rings) / szz
    sy = sum((z - mz) * (c.y - my) for z, c in rings) / szz
    lean = math.degrees(math.atan(math.hypot(sx, sy)))
    base = ax.centre(0.5)
    area = 0.0
    acc = Vector((0.0, 0.0, 0.0))
    for p in me.polygons:
        if p.material_index == NEEDLE_IDX:
            a = p.area
            area += a
            acc += p.center * a
    centroid = acc / area if area else Vector()
    balance = (centroid - base).to_2d().length
    dbh_ring = min(ax.rings, key=lambda r: abs(r[0] - (ax.rings[0][0] + DBH_Z)))
    dbh = 2.0 * dbh_ring[2]
    return lean, balance, dbh, centroid.z


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
    sizes = {}
    for i in range(n):
        sizes[find(i)] = sizes.get(find(i), 0) + 1
    return len(sizes), sorted(sizes.values())


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
    img = bpy.data.images.new("PineNrm", size, size, alpha=True, float_buffer=False)
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


def check(skip_decimate, lift_z=False, stray_vert=False, float_branches=False,
          lean_crown=False, bunch_whorls=False, drop_cones=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    plan = plan_tree()
    flags = dict(float_branches=float_branches, lean_crown=lean_crown,
                 bunch_whorls=bunch_whorls, drop_cones=drop_cones)
    low = build_tree_mesh("PineLow", plan, "low", **flags)
    high = build_tree_mesh("PineHigh", plan, "high", **flags)
    mats = tree_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    bark = mats[BARK_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none2 = (None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("tree mesh did not build", 3),) + none2

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
    if len(cls["trunk"]) != 1:
        return (fail(f"trunk not found: {len(cls['trunk'])} candidates", 3),) + none2
    expected_limbs = sum(len(w["branches"]) for w in plan["whorls"])
    expected_dead = len(STUBS) + len(DEAD_BRANCHES)
    ratios = seat_audit(cls)
    heights, gaps, spreads, counts = whorl_audit(cls)
    lean, balance, dbh, mass_z = plumb_audit(low.data, cls)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, bark)
    if img is None:
        return (fail("tree has no UV layer", 3),) + none2
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "PineLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "PineLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_collider_source("PineColSrc", plan)
    collider = convex_hull_collider(collider_src, "PineCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_pine_tree_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} limbs={len(cls['limbs'])} "
          f"twigs={len(cls['twigs'])} brushes={len(cls['brushes'])} "
          f"cones={len(cls['cones'])} roots={len(cls['roots'])} "
          f"dead_seated={len(cls['dead_seated'])}")
    print(f"measured seat_ratio min={min(ratios):.4f} max={max(ratios):.4f} n={len(ratios)}")
    print(f"measured whorls={len(heights)} counts={counts} "
          f"heights={[round(h, 3) for h in heights]}")
    print(f"measured whorl_gaps min={min(gaps, default=0):.4f} max={max(gaps, default=0):.4f} "
          f"spread_max={max(spreads, default=0):.4f}")
    print(f"measured lean_deg={lean:.3f} balance={balance:.4f} mass_z={mass_z:.3f} "
          f"dbh={dbh:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-3:]} n={len(comp_sizes)}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none2
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none2
    floors = ((BARK_IDX, BARK_FACES_MIN, "bark"), (NEEDLE_IDX, NEEDLE_FACES_MIN, "needle"),
              (CONE_IDX, CONE_FACES_MIN, "cone"), (DEAD_IDX, DEAD_FACES_MIN, "deadwood"))
    for idx, floor, label in floors:
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
    if (len(cls["limbs"]) != expected_limbs or len(cls["dead_seated"]) != expected_dead
            or min(ratios) < SEAT_RATIO_MIN or max(ratios) > SEAT_RATIO_MAX):
        return (fail(f"branch seat: limbs {len(cls['limbs'])}/{expected_limbs} dead "
                     f"{len(cls['dead_seated'])}/{expected_dead} base/radius "
                     f"{min(ratios):.4f}..{max(ratios):.4f} not in "
                     f"[{SEAT_RATIO_MIN}, {SEAT_RATIO_MAX}]", 17),) + none2
    if (lean > LEAN_MAX_DEG or balance > BALANCE_MAX or abs(dbh - DBH) > DBH_TOL):
        return (fail(f"plumb/balance: lean {lean:.3f} deg (max {LEAN_MAX_DEG}), balance "
                     f"{balance:.4f} m (max {BALANCE_MAX}), dbh {dbh:.4f} "
                     f"(want {DBH} +/- {DBH_TOL})", 19),) + none2
    if (len(heights) != WHORLS or min(counts) < BRANCHES[0] or max(counts) > BRANCHES[1]
            or max(spreads) > WHORL_SPREAD_MAX or min(gaps) < WHORL_GAP_MIN
            or max(gaps) > WHORL_GAP_MAX):
        return (fail(f"whorl tiers: {len(heights)} whorls (want {WHORLS}), counts {counts}, "
                     f"gaps {min(gaps, default=0):.4f}..{max(gaps, default=0):.4f} (band "
                     f"[{WHORL_GAP_MIN}, {WHORL_GAP_MAX}]), spread "
                     f"{max(spreads, default=0):.4f}", 20),) + none2
    if ncomp != 1:
        return (fail(f"tree splits into {ncomp} components", 21),) + none2
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

    # Key, fill, rim and the warm wedge, scaled for a 7 m tree. The key's
    # spread keeps it on the crown instead of flooding the near floor.
    light("Key", (-11.0, -15.0, 9.0), 3000.0, 5.0, (1.0, 0.95, 0.88), spread=24.0)
    light("Fill", (15.0, -10.0, 1.0), 150.0, 18.0, (0.72, 0.82, 1.0))
    light("Rim", (-4.0, 6.0, 5.5), 800.0, 5.0, (0.62, 0.78, 1.0))
    light("Wedge", (8.0, 2.5, 3.5), 1900.0, 7.0, (1.0, 0.68, 0.38),
          target=(4.0, WALL_Y - 4.0, 0.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.45, -0.89, 0.0)).normalized()
    cam.location = centre + view * 21.5 + Vector((0.0, 0.0, -1.2))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, 0.05))
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
    # Standard, not AgX: AgX lifts the stage toward grey and pastels the needles.
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
    p.add_argument("--float-branches", action="store_true")
    p.add_argument("--lean-crown", action="store_true")
    p.add_argument("--bunch-whorls", action="store_true")
    p.add_argument("--drop-cones", action="store_true")
    args = p.parse_args(argv)

    code, low, _bark = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_branches=args.float_branches,
        lean_crown=args.lean_crown,
        bunch_whorls=args.bunch_whorls,
        drop_cones=args.drop_cones,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("pine-tree OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
