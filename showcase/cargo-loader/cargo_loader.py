"""Game-ready sci-fi cargo loader — a showcase piece, not an example.

Asserts budget conformance of a procedural bipedal powered-lift exoframe,
standing on its two feet and holding a cargo crate off the ground in its
forks, after composing shipped pipeline pieces: bmesh construction, UVs,
ten materials, high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

The loader stands 2.98 m to the top of its beacon. Two hydraulic legs
(foot, shin, thigh) are pinned at the ankle, knee and hip: every joint is a
clevis, two lugs with bushings on one member straddling an eye bushing on
the next, with a chrome pin through all three, its heads biting the outer
bushings. Each leg carries a hip ram in front of the thigh and a knee ram
behind it; each arm (upper arm, forearm) hangs from a shoulder yoke on a
tower beside the cockpit and carries a shoulder ram behind and an elbow
ram in front. Every ram is a dark steel cylinder with a chromed rod, a
pinned clevis at each end. The feet are broad and flat: a rubber sole, a
cast foot with a sloped top, grip cleats and a rubber toe bumper. The
forearms end in fork carriages, each a plate with a hazard-striped face and
a forged L-tine; the two tines carry a corrugated cargo crate with a steel
base, lid, corner posts and castings. The cockpit is an open roll cage
over a pelvis block: a bucket seat with a headrest, a four-point harness
with a buckle, two armrest consoles with joystick grips, a footplate, a
roof plate with an amber beacon and two work lights on brackets. Behind
the seat a power pack with a slatted grille, side cooling fins,
hazard-striped bands, two exhaust stacks and cable looms to the shoulders
and hips; a hydraulic tank under the pelvis.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-foot`` both soles on the
ground, ``--offset-pin`` every clevis pin coaxial with its bushings,
``--lift-crate`` the crate resting on both tines, ``--tilt-sole`` both
soles level and flat, ``--skew-rod`` every ram rod coaxial with its
cylinder, ``--bottom-ram`` every ram's exposed rod inside its stroke band,
``--overload`` the combined mass centre (loader and crate) inside the feet's
support polygon, ``--loose-light`` one connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python cargo_loader.py --
    blender --background --python cargo_loader.py -- --skip-decimate
    blender --background --python cargo_loader.py -- --output loader.png
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

# --- Pose: side view, x forward, z up; y = +left ------------------------------
LEG_Y = 0.50                # leg plane, both sides
ARM_Y = 0.74                # arm plane, both sides
ANKLE = (0.000, 0.320)
KNEE = (0.220, 0.920)       # the knee leads: a crouched stance
HIP = (-0.020, 1.520)
SHOULDER = (0.100, 2.100)
ELBOW = (0.120, 1.550)
WRIST = (0.800, 1.420)

# --- Clevis joints: two lugs straddle an eye; one pin through all three -------
MAIN = dict(eh=0.050, gap=0.008, lt=0.028, proud=0.003, rb=0.068, re=0.078,
            rp=0.030, rh=0.046, ht=0.016, sb=16, sp=14, bc=0.004, pc=True)
RAMJ = dict(eh=0.032, gap=0.006, lt=0.016, proud=0.002, rb=0.040, re=0.042,
            rp=0.017, rh=0.027, ht=0.010, sb=12, sp=10, bc=0.0, pc=False)
PIN_BITE = 0.0005           # pin head's inner face inside the outer bushing
JOINT_CLEAR = 0.020         # a fork block stops this far outside the eye's rim

# --- Rams -----------------------------------------------------------------------
RAM_R = 0.045               # cylinder barrel
RAM_COLLAR = 0.049
ROD_R = 0.022
RAM_FRAC = 0.58             # gland face at this fraction of the pin-to-pin length
RAM_ENGAGE = 0.060          # rod length left inside the barrel
BRACKET_STANDOFF = 0.075    # ram pin standoff past the member's own surface
BRACKET_BITE = 0.012

# --- Feet -------------------------------------------------------------------------
FOOT_CX = 0.100
FOOT_HA = 0.600             # half length (x -0.50 .. 0.70)
FOOT_HB = 0.220
FOOT_RC = 0.100
SOLE_T = 0.036
FOOT_TOP = 0.165

# --- Body -------------------------------------------------------------------------
PELVIS = (-0.360, 0.300, 0.640, 1.630, 1.880)     # x0, x1, half y, z0, z1
PACK = (-0.920, -0.340, 0.440, 1.600, 2.520)
TOWER = (-0.100, 0.220, 0.440, 0.600, 1.860, 2.300)  # x0, x1, y0, y1, z0, z1
YOKE = (-0.040, 0.240, 0.500, 2.200, 2.360)          # x0, x1, y0, z0, z1 (y1 from lugs)
CAGE_Y = 0.420
CAGE_R = 0.026
CAGE_XF = 0.270
CAGE_XR = -0.310
CAGE_TOP = 2.780
BEACON_X = -0.100

# --- Carriage, tines and crate ------------------------------------------------------
PLATE_X = (0.930, 0.970)
PLATE_Y = (0.400, 0.800)
PLATE_Z = (0.930, 1.500)
TINE_Y = 0.470
TINE_HW = 0.060
TINE_TOP = 1.000
TINE_TIP = 1.870
CRATE_X0 = 1.030
CRATE_HX = 0.3875
CRATE_HY = 0.560
CRATE_H = 0.620
CRATE_BITE = 0.002          # the crate's base stands this far down over the tines

# --- Falsifier sizes -----------------------------------------------------------------
FLOAT_FOOT = 0.005
OFFSET_PIN = 0.0025
LIFT_CRATE = 0.006
TILT_SOLE_DEG = 0.6
SKEW_ROD_DEG = 1.0
BOTTOM_EXPOSED = 0.040
OVERLOAD = 14.0
LOOSE_LIGHT = 0.060

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (2.827, 1.689, 2.974)
BASE_TRIS_MIN = 44000
BASE_TRIS_MAX = 45000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 10
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 760
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
PAINT_FACES_MIN = 2550
HAZARD_FACES_MIN = 560
CHROME_FACES_MIN = 2900
STEEL_FACES_MIN = 14300
RUBBER_FACES_MIN = 2550
SEAT_FACES_MIN = 440
WEBBING_FACES_MIN = 590
BEACON_FACES_MIN = 235
LIGHT_FACES_MIN = 140
CRATE_FACES_MIN = 480

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
SOLE_COUNT = 2
CONTACT_BAND = 2e-5         # a sole's contact: its lowest ring of vertices
# Soles: the bottom face flat and horizontal.
SOLE_FLAT_MAX = 0.0005
SOLE_TILT_MAX_DEG = 0.2
# Clevis joints: the pin's axis through every bushing's centre, parallel to it.
JOINT_COUNT = 28            # 12 limb joints + 2 per ram
JOINT_BUSHINGS = 3
PIN_OFFSET_MAX = 0.0003
PIN_TILT_MAX_DEG = 0.3
# Rams: the rod on the cylinder's axis, and inside its stroke.
RAM_COUNT = 8
ROD_OFFSET_MAX = 0.0003
ROD_TILT_MAX_DEG = 0.3
EXPOSED_MIN = 0.080
EXPOSED_MAX = 0.340
ENGAGE_MIN = 0.040
# Crate: resting on both tines, a bite of the base over each tine's top.
TINE_COUNT = 2
CRATE_BITE_MIN = 0.0010
CRATE_BITE_MAX = 0.0040
TINE_UNDER_MIN = 0.50       # each tine runs this far under the crate's base
CRATE_STEP = 0.010
CRATE_EDGE = 0.020          # stations stay off the base's chamfered rim
# Stance: loader and crate together; densities per material (kg/m^3).
DENSITY = (900.0, 900.0, 7800.0, 4500.0, 1100.0, 150.0, 300.0, 1200.0, 1500.0, 450.0)
STANCE_MARGIN = 0.200
# Hero yaw: the loader's front turned toward the camera's right.
HERO_YAW_DEG = -62.0
WALL_Y = 5.0

PAINT_IDX = 0
HAZARD_IDX = 1
CHROME_IDX = 2
STEEL_IDX = 3
RUBBER_IDX = 4
SEAT_IDX = 5
WEBBING_IDX = 6
BEACON_IDX = 7
LIGHT_IDX = 8
CRATE_IDX = 9

# Face roles (a face attribute): what each shell is, for the audits to find
# it. The measured values are read off the shell's vertices, never the tag.
R_OTHER = 0
R_PIN = 1
R_BUSH = 2
R_CYL = 3
R_ROD = 4
R_SOLE = 5
R_TINE = 6
R_CRATE = 7

ZAX = Vector((0.0, 0.0, 1.0))
YAX = Vector((0.0, 1.0, 0.0))
XAX = Vector((1.0, 0.0, 0.0))


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
# Construction helpers (copied from showcase/motor-scooter, not imported)
# --------------------------------------------------------------------------

_LAYERS = {}


def _mark(faces, mat_idx):
    for f in faces:
        f.material_index = mat_idx


def tag(verts, role, unit):
    """Stamp a part's faces with its role and unit (a joint or ram id)."""
    rl, ul = _LAYERS["role"], _LAYERS["unit"]
    for v in verts:
        for f in v.link_faces:
            f[rl] = role
            f[ul] = unit


def frame(ez, ex_hint):
    """Rotation whose local Z is ``ez`` and local X is ``ex_hint`` made
    orthogonal to it (columns ex, ey, ez; right-handed)."""
    ez = Vector(ez).normalized()
    ex = Vector(ex_hint)
    ex = (ex - ez * ex.dot(ez)).normalized()
    ey = ez.cross(ex)
    return Matrix((ex, ey, ez)).transposed()


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False, seg_mats=None, cap_mats=None, rmod=None):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: the profile
    is an open polyline closed by n-gon caps at its two ends; otherwise it
    is a closed polygon revolved into a ring shell."""
    c = Vector(center)
    m = rot if rot is not None else Matrix.Identity(3)
    rings = []
    for i in range(segs):
        a = phase + 2.0 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        ring = []
        for j, (r, z) in enumerate(profile):
            rr = r * (rmod(i, j) if rmod else 1.0)
            ring.append(bm.verts.new(c + m @ Vector((rr * ca, rr * sa, z))))
        rings.append(ring)
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
        f0.material_index = cap_mats[0] if cap_mats else mat_idx
        f1.material_index = cap_mats[1] if cap_mats else mat_idx
    return [v for ring in rings for v in ring]


def add_tube(bm, pts, radius, sides, mat_idx, phase=0.0):
    """Capped round bar swept along a polyline (parallel-transport frames)."""
    pts = [Vector(p) for p in pts]
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    ref = Vector((0.0, 0.0, 1.0)) if abs(tans[0].z) < 0.9 else Vector((1.0, 0.0, 0.0))
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


def box_profile(z0, z1, c):
    """A slab from z0 to z1 with a 45-degree chamfer ``c`` round both caps."""
    return [(c, z0), (0.0, z0 + c), (0.0, z1 - c), (c, z1)]


def add_box(bm, centre, half, mat_idx, rc=0.006, c=0.004, n_corner=2, rot=None):
    """A chamfered, round-cornered box: ``half`` = (x, y, z) half extents in
    the frame ``rot`` (world axes by default)."""
    rot = rot if rot is not None else Matrix.Identity(3)
    hx, hy, hz = half
    return add_rbox(bm, hx, hy, rc, box_profile(-hz, hz, min(c, 0.45 * hz)), centre, rot,
                    mat_idx, n_corner)


def add_rframe(bm, ha, hb, rc, t_in, z0, z1, origin, rot, mat_idx, n_corner=3):
    """A rounded-rectangle ring (a bezel): outer and inner walls, two faces."""
    o = Vector(origin)
    outer = rrect(ha, hb, rc, n_corner)
    inner = rrect(ha - t_in, hb - t_in, max(rc - t_in, 0.001), n_corner)
    loops = [[(x, y, z0) for x, y in outer], [(x, y, z1) for x, y in outer],
             [(x, y, z1) for x, y in inner], [(x, y, z0) for x, y in inner]]
    rings = [[bm.verts.new(o + rot @ Vector(p)) for p in loop] for loop in loops]
    n = len(outer)
    faces = []
    for a in range(4):
        r0, r1 = rings[a], rings[(a + 1) % 4]
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_plate_xz(bm, outline, y0, y1, mat_idx):
    """A world-XZ outline [(x, z)] extruded along Y from y0 to y1."""
    a = [bm.verts.new((x, y0, z)) for x, z in outline]
    b = [bm.verts.new((x, y1, z)) for x, z in outline]
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


def add_bar(bm, pts, wax, half_w, half_t, rc, mat_idx, fillet=0.008, filleted=False,
            n_corner=2):
    """Flat bar bent in the plane normal to ``wax``: its width lies along
    ``wax``, its thickness in the bending plane; rounded-rectangle section."""
    pts = [Vector(p) for p in pts] if filleted else fillet_path(pts, fillet)
    wax = Vector(wax).normalized()
    sec = rrect(half_w, half_t, rc, n_corner)
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


def circle_pts(cx, cz, r, n=16, phase=0.0):
    return [(cx + r * math.cos(phase + 2.0 * math.pi * k / n),
             cz + r * math.sin(phase + 2.0 * math.pi * k / n)) for k in range(n)]


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
# Members, clevis joints and rams
# --------------------------------------------------------------------------

def xz(p, y=0.0):
    return Vector((p[0], y, p[1]))


class Member:
    """A limb member between two joint stations in the XZ plane at ``y0``:
    ``t`` runs from p0 to p1, ``n`` is ``t`` turned -90 degrees in XZ."""

    def __init__(self, p0, p1, y0, stations):
        self.p0 = xz(p0, y0)
        self.p1 = xz(p1, y0)
        self.y0 = y0
        d = self.p1 - self.p0
        self.length = d.length
        self.t = d / self.length
        self.n = Vector((self.t.z, 0.0, -self.t.x))
        self.stations = stations

    def point(self, s, a_n=0.0, a_y=0.0):
        return self.p0 + self.t * s + self.n * a_n + YAX * a_y

    def hn(self, s):
        st = self.stations
        if s <= st[0][0]:
            return st[0][1]
        for (s0, h0, _y0), (s1, h1, _y1) in zip(st, st[1:]):
            if s <= s1:
                return h0 + (h1 - h0) * (s - s0) / (s1 - s0)
        return st[-1][1]


def add_member(bm, m, mat_idx, rc=0.022, c=0.006):
    """Loft of rounded rectangles along the member (n across, y wide), with
    a chamfered cap at each end."""
    st = m.stations
    rings = [(st[0][0], st[0][1] - c, st[0][2] - c), (st[0][0] + c, st[0][1], st[0][2])]
    rings += [s for s in st[1:-1]]
    rings += [(st[-1][0] - c, st[-1][1], st[-1][2]), (st[-1][0], st[-1][1] - c, st[-1][2] - c)]
    loops = []
    for s, hn, hy in rings:
        loop = rrect(hn, hy, min(rc, 0.8 * min(hn, hy)), 4)
        loops.append([m.point(s, a, b) for a, b in loop])
    return add_loft(bm, loops, mat_idx)


def add_bush(bm, p, yc, half, r, segs, c):
    rot = frame(YAX, XAX)
    prof = ([(r - c, -half), (r, -half + c), (r, half - c), (r - c, half)] if c > 0.0
            else [(r, -half), (r, half)])
    return add_lathe(bm, prof, segs, STEEL_IDX, center=(p.x, yc, p.z), rot=rot, solid=True,
                     phase=math.pi / segs)


def add_joint(bm, p, y0, js, jid, offset_pin=False):
    """Two lug bushings, the eye bushing between them and the pin through
    all three, its heads biting the outer bushings' faces."""
    p = Vector(p)
    for s in (1.0, -1.0):
        v = add_bush(bm, p, y0 + s * (js["eh"] + js["gap"] + 0.5 * js["lt"]),
                     0.5 * js["lt"] + js["proud"], js["rb"], js["sb"], js["bc"])
        tag(v, R_BUSH, jid)
    v = add_bush(bm, p, y0, js["eh"], js["re"], js["sb"], js["bc"])
    tag(v, R_BUSH, jid)
    lh = js["eh"] + js["gap"] + js["lt"] + js["proud"] - PIN_BITE
    rh, rp, ht = js["rh"], js["rp"], js["ht"]
    if js["pc"]:
        c = 0.25 * ht
        prof = [(rh - c, -lh - ht), (rh, -lh - ht + c), (rh, -lh), (rp, -lh), (rp, lh),
                (rh, lh), (rh, lh + ht - c), (rh - c, lh + ht)]
    else:
        prof = [(rh, -lh - ht), (rh, -lh), (rp, -lh), (rp, lh), (rh, lh), (rh, lh + ht)]
    pc = p + (Vector((OFFSET_PIN, 0.0, 0.0)) if offset_pin else Vector())
    v = add_lathe(bm, prof, js["sp"], CHROME_IDX, center=(pc.x, y0, pc.z),
                  rot=frame(YAX, XAX), solid=True)
    tag(v, R_PIN, jid)


def add_lugs(bm, p, y0, js, base_pts, mat_idx=STEEL_IDX):
    """The fork side of a clevis: two plates, each the hull of the lug's round
    end and its root inside the host."""
    outline = hull2d(circle_pts(p.x, p.z, js["rb"] - 0.010, 12) + base_pts)
    y_in = js["eh"] + js["gap"]
    y_out = y_in + js["lt"]
    vs = []
    for s in (1.0, -1.0):
        a, b = sorted((y0 + s * y_in, y0 + s * y_out))
        vs += add_plate_xz(bm, outline, a, b, mat_idx)
    return vs


def member_fork(bm, m, js, mat_idx=STEEL_IDX):
    """Lugs on the member's p1 end: roots in the fork block, round ends at p1."""
    s_end = m.stations[-1][0]
    hn = m.stations[-1][1] - 0.014
    base = []
    for s in (s_end - 0.060, s_end - 0.004):
        for a in (-hn, hn):
            q = m.point(s, a)
            base.append((q.x, q.z))
    return add_lugs(bm, m.p1, m.y0, js, base, mat_idx)


def fork_end(m_len, js):
    """Where a fork block stops short of the eye it carries."""
    return m_len - (js["re"] + JOINT_CLEAR)


def add_bracket(bm, p, y0, out, depth, js, mat_idx=STEEL_IDX):
    """A ram's clevis bracket: a block from inside the host (``depth`` back
    from the pin along ``out``) to just short of the ram's eye, and its lugs."""
    out = Vector(out).normalized()
    perp = Vector((out.z, 0.0, -out.x))
    d1 = js["re"] + 0.012
    hy = js["eh"] + js["gap"] + js["lt"] - 0.002
    rot = frame(out, perp)
    vs = add_rbox(bm, 0.036, hy, 0.010, box_profile(-depth, -d1, 0.004),
                  (p.x, y0, p.z), rot, mat_idx, 2)
    base = []
    for dd in (d1 + 0.014, d1 + 0.002):
        for w in (-0.028, 0.028):
            q = p - out * dd + perp * w
            base.append((q.x, q.z))
    vs += add_lugs(bm, p, y0, js, base, mat_idx)
    return vs


def member_bracket(bm, m, s, side, js):
    """A bracket on the member's surface at station s (side +1 along n, -1
    against it); returns the ram pin's station."""
    hn = m.hn(s)
    standoff = hn + BRACKET_STANDOFF
    out = m.n * side
    p = m.point(s) + out * standoff
    depth = standoff - hn + BRACKET_BITE
    add_bracket(bm, p, m.y0, out, depth, js)
    return p, out, depth


def add_ram(bm, a, b, y0, rid, host_out, host_depth, skew=False, bottom=False):
    """Cylinder from the base eye at ``a`` (a stem through the lug gap, a
    collared barrel, a gland) and a chromed rod into the rod eye at ``b``."""
    a = Vector((a.x, y0, a.z))
    b = Vector((b.x, y0, b.z))
    d = b - a
    length = d.length
    d.normalize()
    rot = frame(d, YAX)
    w0 = RAMJ["rb"] + 0.012
    wg = length - BOTTOM_EXPOSED if bottom else RAM_FRAC * length
    prof = [(0.016, 0.004), (0.020, 0.012), (0.020, w0 - 0.012), (0.034, w0 - 0.004),
            (RAM_COLLAR, w0), (RAM_COLLAR, w0 + 0.020), (RAM_R, w0 + 0.026),
            (RAM_R, wg - 0.026), (RAM_COLLAR, wg - 0.020), (RAM_COLLAR, wg - 0.006),
            (0.036, wg - 0.002), (0.030, wg)]
    v = add_lathe(bm, prof, 16, STEEL_IDX, center=a, rot=rot, solid=True)
    tag(v, R_CYL, rid)
    wr = wg - RAM_ENGAGE
    rod = add_lathe(bm, [(0.018, wr), (ROD_R, wr + 0.004), (ROD_R, length),
                         (0.018, length + 0.004)], 12, CHROME_IDX, center=a, rot=rot,
                    solid=True)
    if skew:
        m = Matrix.Rotation(math.radians(SKEW_ROD_DEG), 3, "Y")
        for vv in rod:
            vv.co = b + m @ (vv.co - b)
    tag(rod, R_ROD, rid)
    # a port boss on the barrel's base end and a hose from it into the host
    out = Vector(host_out).normalized()
    h = -(out - d * out.dot(d)).normalized()
    wp = w0 + 0.050
    port = a + d * wp + h * RAM_R
    add_lathe(bm, [(0.013, -0.012), (0.013, 0.010), (0.010, 0.014)], 8, STEEL_IDX,
              center=port, rot=frame(h, d), solid=True)
    root = a - out * (host_depth - 0.010) + d * 0.060
    add_tube(bm, fillet_path([port + h * 0.008, port + h * 0.030 + d * 0.030, root], 0.03, 3),
             0.0085, 6, RUBBER_IDX)
    return a, b, d, length


# --------------------------------------------------------------------------
# Assemblies
# --------------------------------------------------------------------------

def leg_members(side):
    y0 = side * LEG_Y
    shin = Member(ANKLE, KNEE, y0, None)
    se = fork_end(shin.length, MAIN)
    shin.stations = [(0.000, 0.052, 0.040), (0.070, 0.060, 0.046), (0.160, 0.078, 0.058),
                     (0.440, 0.078, 0.060), (se - 0.040, 0.076, 0.083), (se, 0.072, 0.083)]
    thigh = Member(KNEE, HIP, y0, None)
    tl = thigh.length
    thigh.stations = [(0.000, 0.052, 0.040), (0.070, 0.062, 0.046), (0.180, 0.090, 0.064),
                      (tl - 0.180, 0.090, 0.064), (tl - 0.070, 0.062, 0.046), (tl, 0.052, 0.040)]
    return shin, thigh


def arm_members(side):
    y0 = side * ARM_Y
    upper = Member(SHOULDER, ELBOW, y0, None)
    ue = fork_end(upper.length, MAIN)
    upper.stations = [(0.000, 0.050, 0.040), (0.070, 0.058, 0.046), (0.150, 0.072, 0.056),
                      (ue - 0.090, 0.072, 0.058), (ue - 0.040, 0.070, 0.083), (ue, 0.066, 0.083)]
    fore = Member(ELBOW, WRIST, y0, None)
    fe = fork_end(fore.length, MAIN)
    fore.stations = [(0.000, 0.050, 0.040), (0.070, 0.058, 0.046), (0.160, 0.070, 0.056),
                     (fe - 0.090, 0.066, 0.058), (fe - 0.040, 0.066, 0.083), (fe, 0.062, 0.083)]
    return upper, fore


class Ids:
    def __init__(self):
        self.joint = 0
        self.ram = 0

    def j(self):
        self.joint += 1
        return self.joint - 1

    def r(self):
        self.ram += 1
        return self.ram - 1


def add_foot(bm, side, ids, flags, bevel_verts):
    """Sole, foot, cleats, toe bumper and the ankle fork."""
    y0 = side * LEG_Y
    o = Vector((FOOT_CX, y0, 0.0))
    ident = Matrix.Identity(3)
    sole = add_rbox(bm, FOOT_HA + 0.005, FOOT_HB + 0.005, FOOT_RC,
                    [(0.006, 0.0), (0.0, 0.006), (0.0, SOLE_T - 0.006), (0.004, SOLE_T)],
                    o, ident, RUBBER_IDX, 6)
    if side > 0 and flags.get("float_foot"):
        for v in sole:
            v.co.z += FLOAT_FOOT
    if side > 0 and flags.get("tilt_sole"):
        # about the sole's front bottom edge: the toe stays down, the heel lifts
        piv = max(v.co.x for v in sole if v.co.z < 1e-6)
        m = Matrix.Rotation(math.radians(TILT_SOLE_DEG), 3, "Y")
        c = Vector((piv, y0, 0.0))
        for v in sole:
            v.co = c + m @ (v.co - c)
    tag(sole, R_SOLE, 0 if side > 0 else 1)
    add_rbox(bm, FOOT_HA, FOOT_HB, FOOT_RC,
             [(0.012, 0.024), (0.0, 0.036), (0.0, 0.118), (0.026, 0.150), (0.050, FOOT_TOP)],
             o, ident, PAINT_IDX, 6)
    # grip cleats across the top, before and behind the ankle
    k = 0
    for x in [0.160 + 0.060 * i for i in range(8)] + [-0.430 + 0.064 * i for i in range(5)]:
        e = 0.0003 * k
        hb = 0.120 - 0.002 * (k % 5)
        add_rbox(bm, 0.011, hb, 0.004,
                 [(0.0, FOOT_TOP - 0.004 - e), (0.0, FOOT_TOP + 0.006 + e),
                  (0.0025, FOOT_TOP + 0.0085 + e)], (x, y0, 0.0), ident, STEEL_IDX, 1)
        k += 1
    # rubber toe bumper round the front, over the foot's side faces
    cx, cy = FOOT_CX + FOOT_HA - FOOT_RC, FOOT_HB - FOOT_RC
    r = FOOT_RC + 0.008
    path = [Vector((cx - 0.10, y0 - cy - r, 0.078))]
    for i in range(9):
        a = -0.5 * math.pi + 0.5 * math.pi * i / 8
        path.append(Vector((cx + r * math.cos(a), y0 - cy + r * math.sin(a), 0.078)))
    for i in range(9):
        a = 0.5 * math.pi * i / 8
        path.append(Vector((cx + r * math.cos(a), y0 + cy + r * math.sin(a), 0.078)))
    path.append(Vector((cx - 0.10, y0 + cy + r, 0.078)))
    add_bar(bm, path, ZAX, 0.030, 0.014, 0.008, RUBBER_IDX, filleted=True)
    # heel block with a tow eye
    add_box(bm, (FOOT_CX - FOOT_HA + 0.030, y0, 0.100), (0.040, 0.110, 0.040), STEEL_IDX,
            rc=0.012, c=0.006)
    # ankle fork
    ax, az = ANKLE
    base = [(ax - 0.066, 0.128), (ax + 0.066, 0.128), (ax - 0.066, 0.152), (ax + 0.066, 0.152)]
    add_lugs(bm, xz(ANKLE, y0), y0, MAIN, base)
    add_joint(bm, xz(ANKLE, y0), y0, MAIN, ids.j())


def add_leg(bm, side, ids, flags, bevel_verts):
    """Shin, thigh, knee and hip joints, hip and knee rams."""
    shin, thigh = leg_members(side)
    y0 = shin.y0
    add_member(bm, shin, PAINT_IDX)
    member_fork(bm, shin, MAIN)
    add_joint(bm, shin.p1, y0, MAIN, ids.j(), offset_pin=(side > 0 and flags.get("offset_pin")))
    add_member(bm, thigh, PAINT_IDX)
    # hip: lugs hang from the pelvis's underside
    hx, hz = HIP
    base = [(hx - 0.060, PELVIS[3] + 0.030), (hx + 0.060, PELVIS[3] + 0.030),
            (hx - 0.060, PELVIS[3] + 0.070), (hx + 0.060, PELVIS[3] + 0.070)]
    add_lugs(bm, xz(HIP, y0), y0, MAIN, base)
    add_joint(bm, xz(HIP, y0), y0, MAIN, ids.j())
    # hazard guard on the shin's front
    s0, s1 = 0.190, 0.420
    sm = 0.5 * (s0 + s1)
    hn = shin.hn(sm)
    rot = Matrix((shin.t, YAX, shin.n)).transposed()
    bevel_verts += add_rbox(bm, 0.5 * (s1 - s0), 0.050, 0.014,
                            box_profile(hn - 0.006, hn + 0.010, 0.004),
                            shin.point(sm), rot, HAZARD_IDX, 3)
    # side cover plates on the thigh's outer face
    sm = 0.5 * thigh.length
    rot = Matrix((thigh.t, thigh.n, YAX * side)).transposed()
    bevel_verts += add_rbox(bm, 0.140, 0.062, 0.020,
                            box_profile(0.060, 0.072, 0.003), thigh.point(sm), rot,
                            STEEL_IDX, 3)
    # hip ram: pelvis front to the thigh's front
    a = Vector((PELVIS[1] + 0.100, y0, 1.720))
    add_bracket(bm, a, y0, XAX, 0.100 + BRACKET_BITE, RAMJ)
    b, _o, _d = member_bracket(bm, thigh, 0.50 * thigh.length, 1.0, RAMJ)
    rid = ids.r()
    add_ram(bm, a, b, y0, rid, XAX, 0.100 + BRACKET_BITE,
            skew=(side > 0 and flags.get("skew_rod")))
    add_joint(bm, a, y0, RAMJ, ids.j())
    add_joint(bm, b, y0, RAMJ, ids.j())
    # knee ram: thigh's back to the shin's back
    a, ao, ad = member_bracket(bm, thigh, 0.75 * thigh.length, -1.0, RAMJ)
    b, _o, _d = member_bracket(bm, shin, 0.45 * shin.length, -1.0, RAMJ)
    rid = ids.r()
    add_ram(bm, a, b, y0, rid, ao, ad, bottom=(side > 0 and flags.get("bottom_ram")))
    add_joint(bm, a, y0, RAMJ, ids.j())
    add_joint(bm, b, y0, RAMJ, ids.j())


def add_arm(bm, side, ids, flags, bevel_verts):
    """Shoulder tower and yoke, upper arm, forearm, elbow and wrist joints,
    shoulder and elbow rams, carriage plate and tine."""
    upper, fore = arm_members(side)
    y0 = upper.y0
    x0, x1, ty0, ty1, tz0, tz1 = TOWER
    add_box(bm, (0.5 * (x0 + x1), side * 0.5 * (ty0 + ty1), 0.5 * (tz0 + tz1)),
            (0.5 * (x1 - x0), 0.5 * (ty1 - ty0), 0.5 * (tz1 - tz0)), PAINT_IDX, rc=0.030,
            c=0.008, n_corner=3)
    # louvred vent on the tower's front face
    for k in range(4):
        e = 0.0004 * k
        add_box(bm, (x1 + 0.010 + e, side * 0.5 * (ty0 + ty1), 1.985 + 0.052 * k),
                (0.012, 0.052 - 0.002 * k, 0.013), STEEL_IDX, rc=0.005, c=0.003)
    yx0, yx1, yy0, yz0, yz1 = YOKE
    yy1 = ARM_Y + MAIN["eh"] + MAIN["gap"] + MAIN["lt"] - 0.003
    add_rbox(bm, 0.5 * (yx1 - yx0), 0.5 * (yy1 - yy0), 0.045,
             [(0.008, yz0), (0.0, yz0 + 0.008), (0.0, yz1 - 0.040), (0.014, yz1 - 0.016),
              (0.034, yz1)], (0.5 * (yx0 + yx1), side * 0.5 * (yy0 + yy1), 0.0),
             Matrix.Identity(3), PAINT_IDX, 4)
    add_box(bm, (0.5 * (yx0 + yx1), side * 0.5 * (yy0 + yy1), yz1 + 0.004),
            (0.5 * (yx1 - yx0) - 0.046, 0.5 * (yy1 - yy0) - 0.046, 0.008), STEEL_IDX,
            rc=0.020, c=0.003, n_corner=3)
    add_box(bm, (0.5 * (x0 + x1), side * (ty1 + 0.001), 0.5 * (tz0 + tz1) - 0.030),
            (0.5 * (x1 - x0) - 0.035, 0.005, 0.5 * (tz1 - tz0) - 0.080), STEEL_IDX,
            rc=0.020, c=0.003, n_corner=3)
    sx, sz = SHOULDER
    base = [(sx - 0.060, yz0 + 0.030), (sx + 0.060, yz0 + 0.030),
            (sx - 0.060, yz0 + 0.060), (sx + 0.060, yz0 + 0.060)]
    add_lugs(bm, xz(SHOULDER, y0), y0, MAIN, base)
    add_joint(bm, xz(SHOULDER, y0), y0, MAIN, ids.j())
    add_member(bm, upper, PAINT_IDX)
    member_fork(bm, upper, MAIN)
    rot = Matrix((upper.t, upper.n, YAX * side)).transposed()
    bevel_verts += add_rbox(bm, 0.110, 0.050, 0.018, box_profile(0.049, 0.064, 0.003),
                            upper.point(0.260), rot, STEEL_IDX, 3)
    add_joint(bm, upper.p1, y0, MAIN, ids.j())
    add_member(bm, fore, PAINT_IDX)
    member_fork(bm, fore, MAIN)
    fe = fore.stations[-1][0]
    for k, (an, r) in enumerate(((0.022, 0.011), (-0.020, 0.009))):
        off = 0.066 + 0.004 * k
        pts = [fore.point(0.100, an, side * 0.030), fore.point(0.160, an, side * off),
               fore.point(fe - 0.110, an, side * off), fore.point(fe - 0.030, an, side * 0.070)]
        add_tube(bm, fillet_path(pts, 0.040, 3), r, 8, RUBBER_IDX)
    add_joint(bm, fore.p1, y0, MAIN, ids.j())
    # shoulder ram: yoke's back to the upper arm's back
    a = Vector((yx0 - 0.100, y0, 2.280))
    add_bracket(bm, a, y0, -XAX, 0.100 + BRACKET_BITE, RAMJ)
    b, _o, _d = member_bracket(bm, upper, 0.25, 1.0, RAMJ)
    rid = ids.r()
    add_ram(bm, a, b, y0, rid, -XAX, 0.100 + BRACKET_BITE)
    add_joint(bm, a, y0, RAMJ, ids.j())
    add_joint(bm, b, y0, RAMJ, ids.j())
    # elbow ram: upper arm's front to the forearm's top
    a, ao, ad = member_bracket(bm, upper, 0.14, -1.0, RAMJ)
    b, _o, _d = member_bracket(bm, fore, 0.28, -1.0, RAMJ)
    rid = ids.r()
    add_ram(bm, a, b, y0, rid, ao, ad)
    add_joint(bm, a, y0, RAMJ, ids.j())
    add_joint(bm, b, y0, RAMJ, ids.j())
    # carriage: an arm from the wrist eye forward into the plate
    carm = Member(WRIST, (PLATE_X[0] + 0.022, WRIST[1]), y0,
                  [(0.000, 0.048, 0.040), (0.070, 0.054, 0.046), (0.0, 0.0, 0.0)])
    carm.stations[-1] = (carm.length, 0.054, 0.046)
    add_member(bm, carm, PAINT_IDX)
    px0, px1 = PLATE_X
    py0, py1 = PLATE_Y
    pz0, pz1 = PLATE_Z
    prot = frame(XAX, YAX)            # local x = +Y, local y = +Z, local z = +X
    bevel_verts += add_rbox(bm, 0.5 * (py1 - py0), 0.5 * (pz1 - pz0), 0.030,
                            box_profile(px0, px1, 0.006),
                            (0.0, side * 0.5 * (py0 + py1), 0.5 * (pz0 + pz1)), prot,
                            STEEL_IDX, 3)
    # hazard face outboard of the tine
    hy0, hy1 = TINE_Y + TINE_HW + 0.030, py1 - 0.030
    bevel_verts += add_rbox(bm, 0.5 * (hy1 - hy0), 0.5 * (1.440 - 1.030), 0.012,
                            box_profile(px1 - 0.005, px1 + 0.008, 0.003),
                            (0.0, side * 0.5 * (hy0 + hy1), 0.5 * (1.440 + 1.030)), prot,
                            HAZARD_IDX, 3)
    # the forged L-tine: shank up the plate's face, blade forward under the crate
    tz0 = TINE_TOP - 0.060
    outline = [(px1 - 0.015, tz0), (TINE_TIP - 0.180, tz0), (TINE_TIP, TINE_TOP - 0.022),
               (TINE_TIP + 0.004, TINE_TOP - 0.010), (TINE_TIP - 0.008, TINE_TOP),
               (px1 + 0.060, TINE_TOP), (px1 + 0.048, TINE_TOP + 0.012),
               (px1 + 0.045, 1.250), (px1 + 0.035, 1.262), (px1 - 0.015, 1.262)]
    tine = add_plate_xz(bm, outline, side * TINE_Y - TINE_HW, side * TINE_Y + TINE_HW,
                        STEEL_IDX)
    tag(tine, R_TINE, 0 if side > 0 else 1)
    bevel_verts += tine


def add_body(bm, ids, flags, bevel_verts):
    """Pelvis, tank, footplate, seat, harness, consoles, cage, beacon, lights."""
    x0, x1, hy, z0, z1 = PELVIS
    add_rbox(bm, 0.5 * (x1 - x0), hy, 0.080, [(0.010, z0), (0.0, z0 + 0.010), (0.0, z1 - 0.030),
                                              (0.012, z1 - 0.008), (0.030, z1)],
             (0.5 * (x0 + x1), 0.0, 0.0), Matrix.Identity(3), PAINT_IDX, 4)
    bevel_verts += add_rbox(bm, 0.340, 0.050, 0.012, box_profile(x1 - 0.006, x1 + 0.009, 0.003),
                            (0.0, 0.0, 1.790), frame(XAX, YAX), HAZARD_IDX, 3)
    for s in (1.0, -1.0):
        add_box(bm, (0.5 * (x0 + x1) - 0.020, s * (hy + 0.001), 1.755),
                (0.5 * (x1 - x0) - 0.090, 0.005, 0.065), STEEL_IDX, rc=0.024, c=0.003,
                n_corner=3)
    # hydraulic tank slung under the pelvis between the hips
    tank = [(0.020, -0.312), (0.050, -0.306), (0.066, -0.290), (0.070, -0.270), (0.070, 0.270),
            (0.066, 0.290), (0.050, 0.306), (0.020, 0.312)]
    add_lathe(bm, tank, 24, STEEL_IDX, center=(0.000, 0.0, 1.575), rot=frame(YAX, XAX),
              solid=True)
    for s in (1.0, -1.0):
        add_lathe(bm, [(0.075, -0.012), (0.078, -0.008), (0.078, 0.008), (0.075, 0.012)], 24,
                  STEEL_IDX, center=(0.0, s * 0.200, 1.575), rot=frame(YAX, XAX), solid=True)
    # footplate: a cleated plate out of the pelvis's front
    add_box(bm, (x1 + 0.090, 0.0, 1.655), (0.120, 0.260, 0.014), STEEL_IDX, rc=0.020, c=0.004)
    for i in range(4):
        e = 0.0003 * i
        add_box(bm, (x1 + 0.040 + 0.045 * i, 0.0, 1.673 + e), (0.008, 0.220 - 0.004 * i, 0.006),
                RUBBER_IDX, rc=0.004, c=0.002)
    # seat frame, cushion, backrest, headrest and shell
    add_box(bm, (0.000, 0.0, 1.900), (0.170, 0.210, 0.030), STEEL_IDX, rc=0.020, c=0.006)
    add_rbox(bm, 0.190, 0.240, 0.060,
             [(0.012, 1.918), (0.0, 1.932), (0.0, 1.985), (0.014, 2.008), (0.034, 2.020)],
             (0.000, 0.0, 0.0), Matrix.Identity(3), SEAT_IDX, 4)
    lean = math.radians(9.0)
    up = Vector((-math.sin(lean), 0.0, math.cos(lean)))
    back = Vector((-math.cos(lean), 0.0, -math.sin(lean)))
    foot = Vector((-0.155, 0.0, 1.990))
    brot = frame(back, YAX)               # local x = Y, local y = up, local z = back
    if brot.col[1].dot(up) < 0.0:
        brot = frame(back, -YAX)
    bc = foot + up * 0.270
    add_rbox(bm, 0.230, 0.270, 0.070,
             [(0.020, 0.0), (0.004, 0.012), (0.0, 0.030), (0.0, 0.070), (0.006, 0.090)],
             bc, brot, SEAT_IDX, 4)
    add_rbox(bm, 0.245, 0.285, 0.075, box_profile(0.075, 0.115, 0.006), bc, brot, STEEL_IDX, 4)
    hc = foot + up * 0.640 + back * 0.030
    add_rbox(bm, 0.130, 0.065, 0.045,
             [(0.016, -0.020), (0.0, -0.004), (0.0, 0.040), (0.010, 0.056)], hc, brot, SEAT_IDX,
             4)
    for s in (1.0, -1.0):
        p0 = foot + up * 0.520 + back * 0.070 + YAX * (s * 0.080)
        add_tube(bm, [p0, p0 + up * 0.110], 0.008, 10, CHROME_IDX)
    # four-point harness: shoulder straps over the backrest, lap belt, buckle
    buckle = Vector((0.090, 0.0, 2.034))
    for s in (1.0, -1.0):
        top = foot + up * 0.520 + back * 0.050 + YAX * (s * 0.095)
        pts = [top, foot + up * 0.548 + back * 0.030 + YAX * (s * 0.095),
               foot + up * 0.545 - back * 0.008 + YAX * (s * 0.095),
               foot + up * 0.300 - back * 0.008 + YAX * (s * 0.080),
               foot + up * 0.060 - back * 0.010 + YAX * (s * 0.055),
               Vector((-0.080, s * 0.048, 2.030)), buckle + Vector((-0.020, s * 0.018, 0.0))]
        add_bar(bm, pts, YAX, 0.022, 0.0030, 0.0015, WEBBING_IDX, fillet=0.040, n_corner=1)
        lap = [Vector((-0.120, s * 0.225, 1.990)), Vector((-0.060, s * 0.236, 2.026)),
               Vector((0.040, s * 0.110, 2.030)), buckle + Vector((0.0, s * 0.020, 0.0))]
        add_bar(bm, lap, XAX, 0.022, 0.0030, 0.0015, WEBBING_IDX, fillet=0.040, n_corner=1)
    add_box(bm, buckle + Vector((0.0, 0.0, 0.004)), (0.030, 0.034, 0.008), CHROME_IDX,
            rc=0.008, c=0.003)
    # armrest consoles and joystick grips
    for s in (1.0, -1.0):
        add_box(bm, (0.070, s * 0.330, 1.960), (0.150, 0.040, 0.100), PAINT_IDX, rc=0.018,
                c=0.006, n_corner=3)
        add_box(bm, (0.000, s * 0.330, 2.072), (0.100, 0.036, 0.016), SEAT_IDX, rc=0.016,
                c=0.006, n_corner=3)
        base = Vector((0.170, s * 0.330, 2.056))
        stick = Vector((0.20, 0.0, 1.0)).normalized()
        rot = frame(stick, XAX)
        add_lathe(bm, [(0.030, 0.0), (0.028, 0.010), (0.016, 0.030), (0.010, 0.040)], 16,
                  RUBBER_IDX, center=base, rot=rot, solid=True)
        add_lathe(bm, [(0.007, 0.020), (0.007, 0.090)], 10, CHROME_IDX, center=base, rot=rot,
                  solid=True)

        def ribs(i, j):
            return 0.93 if (2 <= j <= 7 and j % 2 == 1) else 1.0

        grip = [(0.014, 0.080), (0.019, 0.090)] + [(0.021, 0.100 + 0.014 * k) for k in range(7)]
        grip += [(0.022, 0.200), (0.016, 0.212), (0.008, 0.216)]
        add_lathe(bm, grip, 14, RUBBER_IDX, center=base, rot=rot, solid=True, rmod=ribs)
        add_lathe(bm, [(0.006, 0.206), (0.009, 0.212), (0.008, 0.221), (0.004, 0.223)], 10,
                  BEACON_IDX, center=base + stick * 0.0 + rot @ Vector((0.012, 0.0, 0.0)),
                  rot=rot, solid=True)
    # roll cage: two bent side frames, cross tubes, side rails
    for s in (1.0, -1.0):
        y = s * CAGE_Y
        frame_pts = [(CAGE_XF, y, z1 - 0.030), (CAGE_XF, y, CAGE_TOP - 0.120),
                     (CAGE_XF - 0.080, y, CAGE_TOP), (CAGE_XR + 0.040, y, CAGE_TOP),
                     (CAGE_XR, y, CAGE_TOP - 0.080), (CAGE_XR, y, z1 - 0.030)]
        add_tube(bm, fillet_path(frame_pts, 0.070, 4), CAGE_R, 10, STEEL_IDX)
        add_tube(bm, [(CAGE_XF, y, 2.420), (CAGE_XR, y, 2.420)], 0.020, 10, STEEL_IDX,
                 phase=math.pi / 10.0)
        for x in (CAGE_XF, CAGE_XR):
            add_lathe(bm, [(0.034, -0.036), (0.040, -0.030), (0.040, 0.006), (0.034, 0.012)], 16,
                      STEEL_IDX, center=(x, y, z1 + 0.000), solid=True)
    for x in (0.130, -0.170):
        add_tube(bm, [(x, -CAGE_Y - 0.004, CAGE_TOP), (x, CAGE_Y + 0.004, CAGE_TOP)], 0.022, 10,
                 STEEL_IDX, phase=math.pi / 10.0)
    add_tube(bm, [(CAGE_XF, -CAGE_Y - 0.004, 2.300), (CAGE_XF, CAGE_Y + 0.004, 2.300)], 0.020,
             10, STEEL_IDX)
    # roof plate and beacon
    add_box(bm, (-0.030, 0.0, CAGE_TOP + 0.022), (0.215, 0.405, 0.010), STEEL_IDX, rc=0.040,
            c=0.003, n_corner=3)
    bz = CAGE_TOP + 0.030
    add_lathe(bm, [(0.066, 0.000), (0.074, 0.006), (0.074, 0.030), (0.064, 0.038)], 24,
              STEEL_IDX, center=(BEACON_X, 0.0, bz), solid=True)
    add_lathe(bm, [(0.055, 0.030), (0.058, 0.046), (0.058, 0.110), (0.050, 0.132),
                   (0.034, 0.146), (0.012, 0.150)], 24, BEACON_IDX, center=(BEACON_X, 0.0, bz),
              solid=True)
    for k in range(4):
        a = 2.0 * math.pi * (k + 0.5) / 4
        ca, sa = math.cos(a), math.sin(a)
        pts = [(BEACON_X + 0.068 * ca, 0.068 * sa, bz + 0.026),
               (BEACON_X + 0.068 * ca, 0.068 * sa, bz + 0.110),
               (BEACON_X + 0.030 * ca, 0.030 * sa, bz + 0.158)]
        add_tube(bm, fillet_path(pts, 0.03, 4), 0.0045, 6, STEEL_IDX)
    add_lathe(bm, [(0.006, 0.146), (0.034, 0.152), (0.034, 0.160), (0.006, 0.164)], 16,
              STEEL_IDX, center=(BEACON_X, 0.0, bz), solid=True)
    # work lights on brackets off the front cross tube
    aim = Vector((1.0, 0.0, -0.28)).normalized()
    for s in (1.0, -1.0):
        root = Vector((0.130, s * 0.300, CAGE_TOP))
        head = Vector((0.265, s * 0.300, CAGE_TOP - 0.040))
        add_bar(bm, [root + Vector((-0.010, 0.0, 0.004)), root + Vector((0.030, 0.0, 0.030)),
                     head + Vector((-0.040, 0.0, 0.040)), head - aim * 0.030], YAX, 0.018,
                0.005, 0.003, STEEL_IDX, fillet=0.020)
        hc = head + (aim * LOOSE_LIGHT if (s > 0 and flags.get("loose_light")) else Vector())
        rot = frame(aim, YAX)                 # local x = Y, local y = up-ish, local z = aim
        add_rbox(bm, 0.075, 0.050, 0.018,
                 [(0.008, -0.070), (0.0, -0.062), (0.0, 0.012), (0.004, 0.016)], hc, rot,
                 STEEL_IDX, 3)
        add_rframe(bm, 0.080, 0.055, 0.020, 0.014, 0.004, 0.024, hc, rot, STEEL_IDX)
        add_rbox(bm, 0.064, 0.040, 0.012, box_profile(0.006, 0.022, 0.003), hc, rot,
                 LIGHT_IDX, 3)


def add_pack(bm, bevel_verts):
    """Power pack behind the seat: slatted grille, side fins, hazard bands,
    exhaust stacks and cable looms to the shoulders and hips."""
    x0, x1, hy, z0, z1 = PACK
    add_rbox(bm, 0.5 * (x1 - x0), hy, 0.070,
             [(0.012, z0), (0.0, z0 + 0.012), (0.0, z1 - 0.040), (0.016, z1 - 0.012),
              (0.040, z1)], (0.5 * (x0 + x1), 0.0, 0.0), Matrix.Identity(3), PAINT_IDX, 4)
    # rear grille: a frame plate and staggered slats
    grot = frame(-XAX, YAX)
    gz = 0.5 * (1.760 + 2.360)
    add_rbox(bm, 0.300, 0.300, 0.030, box_profile(-0.006, 0.010, 0.003), (x0, 0.0, gz), grot,
             STEEL_IDX, 3)
    for k in range(9):
        e = 0.0004 * k
        z = 1.790 + 0.066 * k
        add_box(bm, (x0 - 0.018 - e, 0.0, z), (0.012, 0.270 - 0.003 * k, 0.018), STEEL_IDX,
                rc=0.006, c=0.004, rot=frame(ZAX, XAX))
    # side fins and hazard bands
    for s in (1.0, -1.0):
        for k in range(9):
            e = 0.0004 * k
            x = -0.806 + 0.044 * k
            outline = [(x - 0.004, 1.880 + e), (x + 0.004, 1.880 + e), (x + 0.004, 2.380 - e),
                       (x, 2.392 - e), (x - 0.004, 2.380 - e)]
            ya, yb = sorted((s * (hy - 0.010 - e), s * (hy + 0.030 + e)))
            add_plate_xz(bm, outline, ya, yb, STEEL_IDX)
        hrot = frame(YAX * s, XAX)
        bevel_verts += add_rbox(bm, 0.210, 0.070, 0.014, box_profile(hy - 0.006, hy + 0.010, 0.003),
                                (-0.630, 0.0, 1.720), hrot, HAZARD_IDX, 3)
    # carry handles on the top
    for s in (1.0, -1.0):
        y = s * 0.110
        add_tube(bm, fillet_path([(-0.880, y, z1 - 0.012), (-0.880, y, z1 + 0.060),
                                  (-0.800, y, z1 + 0.060), (-0.800, y, z1 - 0.012)], 0.025, 3),
                 0.012, 8, STEEL_IDX)
    # exhaust stacks with rain caps
    for s in (1.0, -1.0):
        c = (-0.720, s * 0.250, z1 - 0.030)
        add_lathe(bm, [(0.048, 0.000), (0.052, 0.010), (0.040, 0.030), (0.034, 0.040),
                       (0.034, 0.200), (0.040, 0.206), (0.040, 0.230), (0.030, 0.236)], 16,
                  STEEL_IDX, center=c, solid=True)
    # cable looms: pack to shoulder yoke, pack to pelvis
    for s in (1.0, -1.0):
        for k, dz in enumerate((0.0, 0.045)):
            r = 0.016 - 0.003 * k
            pts = [(-0.420, s * (hy - 0.030), 2.340 - dz), (-0.300, s * (hy + 0.060), 2.400 - dz),
                   (-0.100, s * (0.610 + 0.020 * k), 2.340 - dz), (0.000, s * (0.620 + 0.020 * k),
                                                                   2.260 - dz)]
            add_tube(bm, fillet_path(pts, 0.080, 4), r, 8, RUBBER_IDX)
        pts = [(-0.480, s * (hy - 0.030), 1.800), (-0.360, s * (hy + 0.070), 1.760),
               (-0.200, s * (hy + 0.090), 1.740), (-0.120, s * (hy + 0.080), 1.760)]
        add_tube(bm, fillet_path(pts, 0.080, 4), 0.018, 8, RUBBER_IDX)


def add_crate(bm, flags, bevel_verts):
    """Corrugated cargo crate on a steel base, with a lid, corner posts and
    castings, resting on the two tines."""
    lift = LIFT_CRATE if flags.get("lift_crate") else 0.0
    cx = CRATE_X0 + CRATE_HX
    zb = TINE_TOP - CRATE_BITE + lift
    zt = zb + CRATE_H
    base = add_rbox(bm, CRATE_HX, CRATE_HY, 0.020, box_profile(zb, zb + 0.050, 0.006),
                    (cx, 0.0, 0.0), Matrix.Identity(3), STEEL_IDX, 3)
    tag(base, R_CRATE, 0)
    bevel_verts += base
    # corrugated walls: one loop, ribs pressed out on all four sides
    ix, iy = CRATE_HX - 0.030, CRATE_HY - 0.030
    dep = 0.016
    loop = []

    def side_pts(p0, p1, outward, count):
        pts = []
        for k in range(count):
            f0 = (k + 0.18) / count
            f1 = (k + 0.32) / count
            f2 = (k + 0.68) / count
            f3 = (k + 0.82) / count
            for f, o in ((f0, 0.0), (f1, dep), (f2, dep), (f3, 0.0)):
                p = p0 + (p1 - p0) * f + outward * o
                pts.append(p)
        return pts

    c = [Vector((ix, -iy)), Vector((ix, iy)), Vector((-ix, iy)), Vector((-ix, -iy))]
    outs = [Vector((1, 0)), Vector((0, 1)), Vector((-1, 0)), Vector((0, -1))]
    counts = [11, 7, 11, 7]
    for i in range(4):
        loop.append(c[i])
        loop += side_pts(c[i], c[(i + 1) % 4], outs[i], counts[i])
    rings = []
    for z in (zb + 0.030, zt - 0.040):
        rings.append([Vector((cx + p.x, p.y, z)) for p in loop])
    add_loft(bm, rings, CRATE_IDX)
    # lid
    lid = add_rbox(bm, CRATE_HX - 0.004, CRATE_HY - 0.004, 0.020,
                   box_profile(zt - 0.050, zt, 0.006), (cx, 0.0, 0.0), Matrix.Identity(3),
                   CRATE_IDX, 3)
    bevel_verts += lid
    # corner posts and castings
    for sx in (1.0, -1.0):
        for sy in (1.0, -1.0):
            px = cx + sx * (CRATE_HX - 0.026)
            py = sy * (CRATE_HY - 0.026)
            add_box(bm, (px, py, 0.5 * (zb + 0.024 + zt - 0.030)),
                    (0.032, 0.032, 0.5 * (CRATE_H - 0.054)),
                    STEEL_IDX, rc=0.008, c=0.004)
            for z, e in ((zb + 0.0585, 0.0006), (zt - 0.058, 0.0012)):
                add_box(bm, (px + sx * (0.010 + e), py + sy * (0.010 + e), z),
                        (0.030, 0.030, 0.030), STEEL_IDX, rc=0.006, c=0.004)
    # lifting eyes on the lid
    for sy in (1.0, -1.0):
        add_lathe(bm, [(0.040, 0.0), (0.048, 0.006), (0.040, 0.012), (0.032, 0.006)], 16,
                  STEEL_IDX, center=(cx, sy * 0.360, zt + 0.010),
                  rot=frame(XAX, YAX))
    # a hazard label on the front
    fx = cx + CRATE_HX - 0.030 + dep
    add_rbox(bm, 0.110, 0.070, 0.010, box_profile(-0.004, 0.006, 0.002),
             (fx, 0.0, zb + 0.5 * CRATE_H), frame(XAX, YAX), HAZARD_IDX, 3)


def build_loader_mesh(name, bevel_offset, bevel_segments, **flags):
    bm = bmesh.new()
    try:
        _LAYERS["role"] = bm.faces.layers.int.new("Role")
        _LAYERS["unit"] = bm.faces.layers.int.new("Unit")
        bevel_verts = []
        ids = Ids()
        for side in (1.0, -1.0):
            add_foot(bm, side, ids, flags, bevel_verts)
            add_leg(bm, side, ids, flags, bevel_verts)
            add_arm(bm, side, ids, flags, bevel_verts)
        add_body(bm, ids, flags, bevel_verts)
        add_pack(bm, bevel_verts)
        add_crate(bm, flags, bevel_verts)

        if bevel_offset > 0.0:
            for mat_idx in (STEEL_IDX, HAZARD_IDX):
                bm.edges.index_update()
                edges = sorted(
                    {e for v in bevel_verts if v.is_valid for e in v.link_edges
                     if len(e.link_faces) == 2
                     and all(f.material_index == mat_idx for f in e.link_faces)
                     and e.calc_face_angle() > math.radians(60.0)},
                    key=lambda e: e.index,
                )
                if edges:
                    bmesh.ops.bevel(bm, geom=edges, offset=bevel_offset,
                                    segments=bevel_segments, profile=0.5, affect="EDGES",
                                    clamp_overlap=True, material=mat_idx)

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
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
                edge.smooth = edge.calc_face_angle() < math.radians(35.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
        _LAYERS.clear()
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
        bsdf.inputs["Coat Roughness"].default_value = 0.10
    if roughness_var > 0.0 or mottle > 0.0:
        coord = nt.nodes.new("ShaderNodeTexCoord")
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = noise_scale
        noise.inputs["Detail"].default_value = 6.0
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


def _emission(bsdf, color, strength):
    for key in ("Emission Color", "Emission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = color
            break
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = strength


def hazard_material(name, yellow, black):
    """Diagonal yellow and black bands in object space: the band coordinate
    is x + y + z, so a face turned any way shows them at 45 degrees."""
    mat = principled(name, yellow, 0.0, 0.50, roughness_var=0.12, noise_scale=40.0)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs[0])
    add1 = nt.nodes.new("ShaderNodeMath")
    add1.operation = "ADD"
    nt.links.new(sep.outputs[0], add1.inputs[0])
    nt.links.new(sep.outputs[1], add1.inputs[1])
    add2 = nt.nodes.new("ShaderNodeMath")
    add2.operation = "ADD"
    nt.links.new(add1.outputs[0], add2.inputs[0])
    nt.links.new(sep.outputs[2], add2.inputs[1])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 1.0 / 0.110
    nt.links.new(add2.outputs[0], mul.inputs[0])
    fr = nt.nodes.new("ShaderNodeMath")
    fr.operation = "FRACT"
    nt.links.new(mul.outputs[0], fr.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = yellow
    ramp.color_ramp.elements[1].position = 0.5
    ramp.color_ramp.elements[1].color = black
    nt.links.new(fr.outputs[0], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def loader_materials():
    """(paint, hazard, chrome, steel, rubber, seat, webbing, beacon, light,
    crate): shared by the check and the render.

    The frame is a worn industrial yellow enamel; hazard panels are muted
    yellow and black bands; ram rods and pins hard chrome; lugs, bushings,
    cylinders, cage, tines and fittings dark gunmetal steel; soles, bumpers,
    hoses and grips rubber; the seat black vinyl; the harness faded orange
    webbing; the beacon an amber lens with a glow; the work lights a warm
    white glow; the crate a weathered blue-grey container paint.
    """
    paint = principled("LoaderPaint", (0.56, 0.38, 0.055, 1.0), 0.0, 0.46,
                       roughness_var=0.06, mottle=0.12, noise_scale=9.0)
    hazard = hazard_material("LoaderHazard", (0.44, 0.30, 0.040, 1.0), (0.018, 0.018, 0.020, 1.0))
    chrome = principled("LoaderChrome", (0.88, 0.88, 0.90, 1.0), 1.0, 0.12,
                        roughness_var=0.04, noise_scale=120.0)
    steel = principled("LoaderSteel", (0.085, 0.088, 0.095, 1.0), 0.75, 0.40,
                       roughness_var=0.10, noise_scale=60.0)
    rubber = principled("LoaderRubber", (0.022, 0.022, 0.024, 1.0), 0.0, 0.80,
                        roughness_var=0.08, noise_scale=90.0)
    seat = principled("LoaderSeatVinyl", (0.030, 0.030, 0.034, 1.0), 0.0, 0.46,
                      roughness_var=0.10, mottle=0.20, noise_scale=140.0)
    webbing = principled("LoaderHarness", (0.42, 0.10, 0.030, 1.0), 0.0, 0.70,
                         roughness_var=0.08, mottle=0.15, noise_scale=200.0)
    beacon = principled("LoaderBeacon", (0.60, 0.26, 0.02, 1.0), 0.0, 0.12, coat=1.0)
    _emission(beacon.node_tree.nodes["Principled BSDF"], (1.0, 0.40, 0.04, 1.0), 6.0)
    light = principled("LoaderWorkLight", (0.80, 0.78, 0.70, 1.0), 0.0, 0.08, coat=1.0)
    _emission(light.node_tree.nodes["Principled BSDF"], (1.0, 0.90, 0.72, 1.0), 8.0)
    crate = principled("LoaderCratePaint", (0.115, 0.180, 0.205, 1.0), 0.0, 0.55,
                       roughness_var=0.12, mottle=0.25, noise_scale=11.0)
    return paint, hazard, chrome, steel, rubber, seat, webbing, beacon, light, crate


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
    def __init__(self, me, idx, verts, polys, role, unit):
        self.idx = idx
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.mean = sum(pts, Vector()) / len(pts)
        mats = {}
        roles = {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
            key = (role[p.index], unit[p.index])
            roles[key] = roles.get(key, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        self.role, self.unit = max(roles, key=roles.get) if roles else (R_OTHER, -1)
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.normals = [p.normal.copy() for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)


def pca(pts):
    """(mean, eigenvalues ascending, eigenvectors as columns)."""
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    w, vecs = np.linalg.eigh(q.T @ q / len(p))
    return Vector(c), w, vecs


def lathe_axis(pts):
    """A turned part's axis: the eigenvector whose eigenvalue stands apart
    from the other two (its radial pair is equal by symmetry), so it holds
    for a long pin and a short, wide bushing alike."""
    c, w, vecs = pca(pts)
    if (w[2] - w[1]) > (w[1] - w[0]):
        return c, Vector(vecs[:, 2])
    return c, Vector(vecs[:, 0])


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    role = [0] * len(me.polygons)
    unit = [0] * len(me.polygons)
    if "Role" in me.attributes:
        me.attributes["Role"].data.foreach_get("value", role)
        me.attributes["Unit"].data.foreach_get("value", unit)
    parts = [Shell(me, i, g, polys[i], role, unit) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    out["soles"] = sorted((s for s in parts if s.role == R_SOLE), key=lambda s: s.unit)
    out["tines"] = sorted((s for s in parts if s.role == R_TINE), key=lambda s: s.unit)
    out["crate"] = [s for s in parts if s.role == R_CRATE]
    out["pins"] = {}
    out["bushings"] = {}
    out["cyls"] = {}
    out["rods"] = {}
    for s in parts:
        key = {R_PIN: "pins", R_BUSH: "bushings", R_CYL: "cyls", R_ROD: "rods"}.get(s.role)
        if key:
            out[key].setdefault(s.unit, []).append(s)
    return out


def sole_audit(cls):
    """Each sole's bottom faces: height spread, and tilt of their plane."""
    res = []
    for s in cls["soles"]:
        pts = []
        for tri, n in zip(s.tri_idx, s.normals):
            if n.z < -0.9:
                pts += [s.pts[i] for i in tri]
        if len(pts) < 3:
            res.append((9.0, 90.0))
            continue
        _c, _w, vecs = pca(pts)
        nrm = Vector(vecs[:, 0])
        tilt = math.degrees(math.acos(min(1.0, abs(nrm.z))))
        res.append((max(p.z for p in pts) - min(p.z for p in pts), tilt))
    return res


def joint_audit(cls):
    """Every joint: one pin, three bushings; each bushing's centre on the
    pin's axis and its axis parallel to the pin's; each within the pin's
    span."""
    worst_off, worst_tilt, bad = 0.0, 0.0, []
    units = sorted(set(cls["pins"]) | set(cls["bushings"]))
    for u in units:
        pins = cls["pins"].get(u, [])
        bush = cls["bushings"].get(u, [])
        if len(pins) != 1 or len(bush) != JOINT_BUSHINGS:
            bad.append((u, len(pins), len(bush)))
            continue
        pc, pa = lathe_axis(pins[0].pts)
        proj = [(p - pc).dot(pa) for p in pins[0].pts]
        lo, hi = min(proj), max(proj)
        for b in bush:
            bc, ba = lathe_axis(b.pts)
            r = bc - pc
            along = r.dot(pa)
            off = (r - pa * along).length
            tilt = math.degrees(math.acos(min(1.0, abs(ba.dot(pa)))))
            worst_off = max(worst_off, off)
            worst_tilt = max(worst_tilt, tilt)
            if not (lo < along < hi):
                bad.append((u, "span", round(along, 4)))
    return {"joints": len(units), "offset": worst_off, "tilt": worst_tilt, "bad": bad}


def ram_audit(cls):
    """Each ram: rod coaxial with its cylinder; the rod's exposed length
    past the gland, and its length still inside the barrel."""
    res = {"rams": 0, "offset": 0.0, "tilt": 0.0, "exposed": [], "engage": []}
    for u in sorted(set(cls["cyls"]) | set(cls["rods"])):
        cyl = cls["cyls"].get(u, [])
        rod = cls["rods"].get(u, [])
        if len(cyl) != 1 or len(rod) != 1:
            continue
        res["rams"] += 1
        cc, ca = lathe_axis(cyl[0].pts)
        rc, ra = lathe_axis(rod[0].pts)
        if ca.dot(rc - cc) < 0.0:
            ca = -ca
        r = rc - cc
        res["offset"] = max(res["offset"], (r - ca * r.dot(ca)).length)
        res["tilt"] = max(res["tilt"], math.degrees(math.acos(min(1.0, abs(ra.dot(ca))))))
        cyl_hi = max((p - cc).dot(ca) for p in cyl[0].pts)
        rod_proj = [(p - cc).dot(ca) for p in rod[0].pts]
        res["exposed"].append(max(rod_proj) - cyl_hi)
        res["engage"].append(cyl_hi - min(rod_proj))
    return res


def crate_audit(cls):
    """Each tine's blade top against the crate base's underside, read at
    stations every CRATE_STEP along the tine's centre line: a ray down onto
    the tine alone and a ray up into the base alone. The blade has vertices
    only at its ends, so the stations sample the faces, not the corners.
    Reports each tine's (lowest, highest) bite and the run it spends under
    the base."""
    res = {"bites": [], "under": []}
    if len(cls["crate"]) != 1:
        return res
    cr = cls["crate"][0]
    down, up = Vector((0.0, 0.0, -1.0)), Vector((0.0, 0.0, 1.0))
    for t in cls["tines"]:
        yc = t.mean.y
        bites = []
        x = cr.lo.x + CRATE_EDGE
        while x < cr.hi.x - CRATE_EDGE:
            top = t.tree.ray_cast(Vector((x, yc, cr.hi.z + 0.5)), down)
            bot = cr.tree.ray_cast(Vector((x, yc, t.lo.z - 0.5)), up)
            if top[0] is not None and bot[0] is not None:
                bites.append(top[0].z - bot[0].z)
            x += CRATE_STEP
        res["bites"].append((min(bites), max(bites)) if bites else (-9.0, -9.0))
        res["under"].append(len(bites) * CRATE_STEP)
    return res


def shell_mass(s):
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


def stance_audit(cls, overload=False):
    """Mass centre of loader and crate against the convex hull of both soles'
    contact rings."""
    total = 0.0
    mom = Vector()
    cargo = 0.0
    crate_box = cls["crate"][0] if cls["crate"] else None
    for s in cls["all"]:
        if s.mat is None:
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * DENSITY[s.mat]
        if (crate_box is not None and s.lo.x >= crate_box.lo.x - 0.02
                and s.hi.x <= crate_box.hi.x + 0.03 and s.lo.z >= crate_box.lo.z - 0.02):
            if overload:
                m *= OVERLOAD
            cargo += m
        total += m
        mom += m * cen
    com = mom / total
    contact_pts = [(p.x, p.y) for sk in cls["soles"] for p in sk.pts
                   if p.z < sk.lo.z + CONTACT_BAND]
    margin = -1.0
    if len(contact_pts) >= 3:
        hull = hull2d(contact_pts)
        margin = 9.0
        for k in range(len(hull)):
            a, b = hull[k], hull[(k + 1) % len(hull)]
            ex, ey = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ex, ey)
            margin = min(margin, (ex * (com.y - a[1]) - ey * (com.x - a[0])) / ln)
    return {"mass": total, "cargo": cargo, "com": com, "margin": margin}


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
        bm.verts.new((0.0, 0.0, 1.2))
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
    img = bpy.data.images.new("LoaderNrm", size, size, alpha=True, float_buffer=False)
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


FLAG_NAMES = ("float_foot", "offset_pin", "lift_crate", "tilt_sole", "skew_rod", "bottom_ram",
              "loose_light")


def check(skip_decimate, lift_z=False, stray_vert=False, overload=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_loader_mesh("LoaderLow", bevel_offset=0.0015, bevel_segments=1, **flags)
    high = build_loader_mesh("LoaderHigh", bevel_offset=0.0015, bevel_segments=3, **flags)
    mats = loader_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the steel: the tines, carriage plates and crate are
    # where the high mesh's rounder chamfer differs from the low.
    target = mats[STEEL_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("loader mesh did not build", 3),) + none3

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
    sole_z = [s.lo.z for s in cls["soles"]]
    soles = sole_audit(cls)
    joints = joint_audit(cls)
    rams = ram_audit(cls)
    crate = crate_audit(cls)
    stance = stance_audit(cls, overload)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("loader has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "LoaderLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "LoaderLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_loader_mesh("LoaderColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "LoaderCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_cargo_loader_{os.getpid()}.glb")
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
          f"outer={OUTER_SIZE} zmin={bb[2]:.4f} min=({bb[0]:.4f},{bb[1]:.4f})")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured shells={len(cls['all'])} soles={len(sole_z)} "
          f"sole_zmin={[round(z, 5) for z in sole_z]}")
    print(f"measured soles flat={[round(f, 6) for f, _t in soles]} "
          f"tilt={[round(t, 4) for _f, t in soles]}")
    print(f"measured joints={joints['joints']} pin_offset={joints['offset']:.6f} "
          f"pin_tilt={joints['tilt']:.4f} bad={joints['bad'][:4]}")
    print(f"measured rams={rams['rams']} rod_offset={rams['offset']:.6f} "
          f"rod_tilt={rams['tilt']:.4f} exposed={[round(e, 4) for e in rams['exposed']]} "
          f"engage={[round(e, 4) for e in rams['engage']]}")
    print(f"measured crate bites={[(round(a, 5), round(b, 5)) for a, b in crate['bites']]} "
          f"under={[round(u, 4) for u in crate['under']]}")
    print(f"measured mass={stance['mass']:.1f}kg cargo={stance['cargo']:.1f}kg "
          f"com=({stance['com'].x:.4f},{stance['com'].y:.4f},{stance['com'].z:.4f}) "
          f"margin={stance['margin']:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    floors = ((PAINT_IDX, PAINT_FACES_MIN, "paint"), (HAZARD_IDX, HAZARD_FACES_MIN, "hazard"),
              (CHROME_IDX, CHROME_FACES_MIN, "chrome"), (STEEL_IDX, STEEL_FACES_MIN, "steel"),
              (RUBBER_IDX, RUBBER_FACES_MIN, "rubber"), (SEAT_IDX, SEAT_FACES_MIN, "seat vinyl"),
              (WEBBING_IDX, WEBBING_FACES_MIN, "harness webbing"),
              (BEACON_IDX, BEACON_FACES_MIN, "beacon lens"),
              (LIGHT_IDX, LIGHT_FACES_MIN, "work-light lens"),
              (CRATE_IDX, CRATE_FACES_MIN, "crate paint"))
    for idx, floor, label in floors:
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
    if len(sole_z) != SOLE_COUNT or max(sole_z) > ZMIN_EPS:
        return (fail(f"supports: {len(sole_z)} soles (want {SOLE_COUNT}), zmin per sole "
                     f"{[round(z, 5) for z in sole_z]} (each within {ZMIN_EPS} of 0)", 16),) + none3
    if (joints["joints"] != JOINT_COUNT or joints["bad"] or joints["offset"] > PIN_OFFSET_MAX
            or joints["tilt"] > PIN_TILT_MAX_DEG):
        return (fail(f"clevis joints: {joints['joints']} (want {JOINT_COUNT}), bad {joints['bad']}, "
                     f"a bushing {joints['offset']:.6f} m off its pin's axis (cap {PIN_OFFSET_MAX}), "
                     f"tilt {joints['tilt']:.4f} deg (cap {PIN_TILT_MAX_DEG})", 17),) + none3
    if (len(crate["bites"]) != TINE_COUNT
            or not all(CRATE_BITE_MIN <= a and b <= CRATE_BITE_MAX for a, b in crate["bites"])
            or min(crate["under"] or [0.0]) < TINE_UNDER_MIN):
        return (fail(f"crate on the tines: bites (low, high) "
                     f"{[(round(a, 5), round(b, 5)) for a, b in crate['bites']]} m not all "
                     f"in [{CRATE_BITE_MIN}, {CRATE_BITE_MAX}], or a tine under the base for "
                     f"{[round(u, 4) for u in crate['under']]} m (< {TINE_UNDER_MIN})", 18),) + none3
    if any(f > SOLE_FLAT_MAX or t > SOLE_TILT_MAX_DEG for f, t in soles):
        return (fail(f"soles not level: spread {[round(f, 6) for f, _t in soles]} m "
                     f"(max {SOLE_FLAT_MAX}), tilt {[round(t, 4) for _f, t in soles]} deg "
                     f"(max {SOLE_TILT_MAX_DEG})", 19),) + none3
    if (rams["rams"] != RAM_COUNT or rams["offset"] > ROD_OFFSET_MAX
            or rams["tilt"] > ROD_TILT_MAX_DEG):
        return (fail(f"rams: {rams['rams']} (want {RAM_COUNT}), a rod {rams['offset']:.6f} m off its "
                     f"cylinder's axis (cap {ROD_OFFSET_MAX}), tilt {rams['tilt']:.4f} deg "
                     f"(cap {ROD_TILT_MAX_DEG})", 20),) + none3
    if (not all(EXPOSED_MIN <= e <= EXPOSED_MAX for e in rams["exposed"])
            or min(rams["engage"]) < ENGAGE_MIN):
        return (fail(f"ram stroke: exposed rod {[round(e, 4) for e in rams['exposed']]} m not all in "
                     f"[{EXPOSED_MIN}, {EXPOSED_MAX}], or engaged {min(rams['engage']):.4f} m "
                     f"< {ENGAGE_MIN}", 21),) + none3
    if stance["margin"] < STANCE_MARGIN:
        return (fail(f"stance: mass centre {stance['margin']:.4f} m inside the soles' support "
                     f"polygon < {STANCE_MARGIN} (cargo {stance['cargo']:.1f} kg)", 22),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 23),) + none3
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

    # The house rig scaled to a 3 m machine: warm key upper left, cool fill
    # low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-4.6, -5.5, 5.0), 370.0, 3.0, (1.0, 0.93, 0.85), spread=30.0)
    light("Fill", (5.6, -3.9, 1.3), 85.0, 6.0, (0.72, 0.82, 1.0))
    light("Rim", (-2.2, 3.7, 3.5), 290.0, 2.6, (0.62, 0.78, 1.0))
    light("Wedge", (5.0, 5.0, 2.2), 740.0, 3.9, (1.0, 0.72, 0.46),
          target=(centre.x + 5.2, centre.y + WALL_Y, 1.2))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.55, -0.83, 0.0)).normalized()
    cam.location = centre + view * 9.10 + Vector((0.0, 0.0, 1.75))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.05))
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
    # Standard, not AgX: AgX washes the yellow enamel and the hazard bands grey
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
    p.add_argument("--offset-pin", action="store_true")
    p.add_argument("--lift-crate", action="store_true")
    p.add_argument("--tilt-sole", action="store_true")
    p.add_argument("--skew-rod", action="store_true")
    p.add_argument("--bottom-ram", action="store_true")
    p.add_argument("--overload", action="store_true")
    p.add_argument("--loose-light", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        overload=args.overload,
        float_foot=args.float_foot,
        offset_pin=args.offset_pin,
        lift_crate=args.lift_crate,
        tilt_sole=args.tilt_sole,
        skew_rod=args.skew_rod,
        bottom_ram=args.bottom_ram,
        loose_light=args.loose_light,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("cargo-loader OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
