"""Game-ready camera quadcopter — a showcase piece, not an example.

Asserts budget conformance of a procedural prosumer camera drone after
composing shipped pipeline pieces: bmesh construction, UVs, eight materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

The drone is an X-frame quad. A moulded body shell is lofted from
superellipse sections, with a parting-line groove along both flanks, two
transverse panel lines, a grille on the nose, grilles on both flanks, a
sensor visor with two stereo lenses on the nose and a status light bar on
the tail. A battery pack sits in the top of the shell with grip ribs, a red
release latch on each side, a power button and four charge LEDs, in front
of it a GPS puck on a mast. Four folding arms each hinge on a vertical pin
through a clevis on the body: two lugs, a tongue on the arm's root cuff and a
knurled lock ring. A carbon tube runs out to a clamp cuff with two screws, a
navigation LED on its end and a mount plate. On the plate a brushless motor
(base, slotted stator bell, anodised top band, four screws, four mount
screws) carries a two-blade propeller: a hub, a colour-coded spinner and two
lofted, twisted, swept airfoil blades, handed to the motor's spin. Two skids
on four raked struts end in rubber feet. A three-axis gimbal hangs under the
nose on a damper stack (two plates, four rubber balls): yaw motor, yaw arm,
roll motor, roll arm, pitch motor, and a camera with a ribbed lens barrel, a
front ring and a glass element. Two antennas point down and back from the
tail.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-foot`` every foot on the
ground, ``--unlock-arm`` the motor layout on an exact X, ``--long-blades``
the propeller tip clearance, ``--narrow-skids`` the mass centre inside the
landing footprint, ``--drop-lens`` one connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python quad_drone.py --
    blender --background --python quad_drone.py -- --skip-decimate
    blender --background --python quad_drone.py -- --output drone.png
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

# --- Body shell: superellipse sections lofted along X (nose at +X) ----------
BODY_LB = 0.130             # half-length of the full envelope; the loft stops at 97 %
BODY_END = 0.97
BODY_W = 0.068              # half-width
BODY_HT = 0.034             # parting line to crown
BODY_HB = 0.030             # parting line to belly
BODY_ZC = 0.172             # parting-line height
BODY_N = 3.0                # section superellipse exponent
BODY_SEGS = 64
BODY_STATIONS = 40
GROOVE = 0.0012             # panel-line depth
PANEL_X = (-0.036, 0.047)   # transverse panel lines
CAP_CHAMFER = 0.0015

# --- Motor layout ------------------------------------------------------------
MOTOR_R = 0.260             # body centre to motor axis: 0.52 m diagonal
MOTOR_DEG = (45.0, 135.0, 225.0, 315.0)
SPIN = (1, -1, 1, -1)       # +1 counter-clockwise from above
PROP_PARK_DEG = (70.0, 45.0, 10.0, 340.0)   # blade azimuth as parked
ARM_Z = 0.188               # arm tube axis
ARM_R = 0.0115              # carbon arm tube
PIN_GAP = 0.017             # body surface to hinge pin, along the arm

# --- Propeller ---------------------------------------------------------------
PROP_R = 0.165              # 13-inch propeller
PROP_PITCH = 0.115          # geometric pitch (m per turn): blade angle = atan(P / 2 pi r)
PROP_BETA_MAX = 30.0
# (station r, chord, max thickness)
BLADE_STATIONS = [
    (0.006, 0.0095, 0.0032), (0.013, 0.0115, 0.0032), (0.020, 0.0175, 0.0030),
    (0.030, 0.0255, 0.0028), (0.045, 0.0300, 0.0025), (0.060, 0.0295, 0.0022),
    (0.080, 0.0275, 0.0019), (0.100, 0.0250, 0.0016), (0.120, 0.0220, 0.0014),
    (0.138, 0.0190, 0.0012), (0.150, 0.0165, 0.0011), (0.158, 0.0130, 0.0010),
    (0.1625, 0.0092, 0.0008), (0.165, 0.0048, 0.0005),
]
BLADE_CAMBER = 0.040
BLADE_PIVOT = 0.40
BLADE_SWEEP = 0.011         # tip swept back behind the motion
AIRFOIL_X = (1.0, 0.72, 0.45, 0.22, 0.07, 0.0, 0.07, 0.22, 0.45, 0.72)

# --- Landing gear ------------------------------------------------------------
SKID_Y = 0.112
SKID_Y_NARROW = 0.075       # --narrow-skids
SKID_HALF = 0.118
SKID_R = 0.0062
FOOT_R = 0.0115
FOOT_X0 = 0.100
STRUT_X_TOP = 0.048
STRUT_Y_TOP = 0.042
STRUT_X_BOT = 0.070
STRUT_R = 0.0052
FLOAT_FOOT = 0.003          # --float-foot

# --- Gimbal and camera -------------------------------------------------------
GX = 0.086
CAM_HALF = (0.030, 0.025)   # camera body half-width (Y), half-height (Z)
LENS_DROP = 0.012           # --drop-lens

# --- Battery -----------------------------------------------------------------
BATT_X = -0.040
BATT_HALF = (0.055, 0.034)
BATT_TOP = 0.236
GPS_X = 0.046
VENT_X = 0.093

# --- Falsifier sizes ---------------------------------------------------------
UNLOCK_ARM = 1              # the rear-left arm: its prop is parked across its arm,
UNLOCK_DEG = 2.5            # so its tips never set the envelope
LONG_BLADES = 0.014

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.692, 0.569, 0.243)
BASE_TRIS_MIN = 40000
BASE_TRIS_MAX = 42000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 8
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 540
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
BODY_FACES_MIN = 1580
CARBON_FACES_MIN = 2120
METAL_FACES_MIN = 5950
GLASS_FACES_MIN = 480
LED_FACES_MIN = 700
RUBBER_FACES_MIN = 1190
GRAPHITE_FACES_MIN = 7800
ANODIZED_FACES_MIN = 2000

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
FEET_COUNT = 4
# Motor layout: axes on an exact X about the body centre.
MOTOR_COUNT = 4
ANGLE_TOL_DEG = 0.3
RADIUS_TOL = 0.001
DIAG_TOL = 0.001
AXIS_TILT_MAX_DEG = 0.5
HUB_Z_TOL = 0.0005
HUB_AXIS_TOL = 0.0003
CENTROID_TOL = 0.001
# Propeller clearance: every disc clears each neighbouring disc by this band.
BLADES_PER_PROP = 2
CLEAR_MIN = 0.028
CLEAR_MAX = 0.050
# Stance: the mass centre, from shell volumes and material densities, stands
# this far inside the feet's ground-contact footprint on every side.
DENSITY = (350.0, 1600.0, 2700.0, 2500.0, 1200.0, 1200.0, 1400.0, 2700.0)
STANCE_MARGIN = 0.090
WHEELBASE = 2.0 * MOTOR_R
WHEELBASE_TOL = 0.003
BODY_LEN = 0.255
BODY_WIDTH = 0.136
BODY_TOL = 0.003
# Hero yaw: the nose turned toward the camera so the gimbal shows.
HERO_YAW_DEG = -118.0
WALL_Y = 2.2

BODY_IDX = 0
CARBON_IDX = 1
METAL_IDX = 2
GLASS_IDX = 3
LED_IDX = 4
RUBBER_IDX = 5
GRAPHITE_IDX = 6
ANODIZED_IDX = 7

ZAX = Vector((0.0, 0.0, 1.0))


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
    is a closed polygon revolved into a ring shell. ``rmod(i, j)`` scales the
    radius of profile point ``j`` on ring ``i``."""
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


def add_sphere(bm, center, radius, mat_idx, segs=16, rings=10, spin=0.0):
    geo = bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=radius)
    verts = geo["verts"]
    c = Vector(center)
    rz = Matrix.Rotation(spin, 3, "Z")
    for v in verts:
        v.co = rz @ v.co + c
    _mark({f for v in verts for f in v.link_faces}, mat_idx)
    return list(verts)


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


def lug_outline(circles, extra=(), n=20):
    """Hull of circles [(u, v, r)] plus loose points: a cast lug plate."""
    pts = list(extra)
    for u, v, r in circles:
        for k in range(n):
            a = 2.0 * math.pi * (k + 0.5) / n
            pts.append((u + r * math.cos(a), v + r * math.sin(a)))
    return hull2d(pts)


def comb_outline(half_len, base_lo, base_hi, ribs, rib_half, rib_top):
    """Grille section: a base strip with ``ribs`` teeth standing on it."""
    pts = [(-half_len, base_lo), (half_len, base_lo), (half_len, base_hi)]
    pitch = 2.0 * half_len / ribs
    for k in reversed(range(ribs)):
        c = -half_len + pitch * (k + 0.5)
        pts += [(c + rib_half, base_hi), (c + rib_half, rib_top),
                (c - rib_half, rib_top), (c - rib_half, base_hi)]
    pts.append((-half_len, base_hi))
    return pts


def screw_profile(lo, hi, r):
    return [(r, lo), (r, hi - 0.0004), (r * 0.78, hi)]


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
# The body shell's closed form
# --------------------------------------------------------------------------

def _env(u, p):
    a = min(abs(u), 1.0)
    return (1.0 - a ** p) ** (1.0 / p)


def body_dims(x):
    """(half-width, crown height, belly depth) of the section at ``x``. The
    nose is rounder in plan and drops toward its visor; the tail is squarer."""
    u = x / BODY_LB
    nose = u > 0.0
    w = BODY_W * _env(u, 2.3 if nose else 2.8)
    ht = BODY_HT * _env(u, 2.0 if nose else 3.0)
    hb = BODY_HB * _env(u, 2.6 if nose else 3.2)
    return w, ht, hb


def _se(c, n=BODY_N):
    return math.copysign(abs(c) ** (2.0 / n), c)


def body_top(x, y):
    w, ht, _hb = body_dims(x)
    a = min(1.0, abs(y) / w)
    return BODY_ZC + ht * (1.0 - a ** BODY_N) ** (1.0 / BODY_N)


def body_bottom(x, y):
    w, _ht, hb = body_dims(x)
    a = min(1.0, abs(y) / w)
    return BODY_ZC - hb * (1.0 - a ** BODY_N) ** (1.0 / BODY_N)


def body_side_y(x, z):
    w, ht, hb = body_dims(x)
    h = ht if z >= BODY_ZC else hb
    a = min(1.0, abs(z - BODY_ZC) / h)
    return w * (1.0 - a ** BODY_N) ** (1.0 / BODY_N)


def body_F(p):
    w, ht, hb = body_dims(p.x)
    h = ht if p.z >= BODY_ZC else hb
    return (abs(p.y) / w) ** BODY_N + (abs(p.z - BODY_ZC) / h) ** BODY_N - 1.0


def body_normal(p, eps=1e-5):
    g = Vector((
        body_F(p + Vector((eps, 0, 0))) - body_F(p - Vector((eps, 0, 0))),
        body_F(p + Vector((0, eps, 0))) - body_F(p - Vector((0, eps, 0))),
        body_F(p + Vector((0, 0, eps))) - body_F(p - Vector((0, 0, eps))),
    ))
    return g.normalized()


def body_ray(phi, z):
    """Distance from the body axis to the shell along a level ray at ``phi``."""
    lo, hi = 0.0, 0.2
    c, s = math.cos(phi), math.sin(phi)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if body_F(Vector((mid * c, mid * s, z))) < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def body_ring(x, inset=0.0):
    """One section loop: points [(y, z)] and per-segment material."""
    w, ht, hb = body_dims(x)
    step = 2.0 * math.pi / BODY_SEGS
    du = min(math.asin(min(1.0, (GROOVE / ht) ** (BODY_N / 2.0))), 0.4 * step)
    dl = min(math.asin(min(1.0, (GROOVE / hb) ** (BODY_N / 2.0))), 0.4 * step)
    half = BODY_SEGS // 2
    ts = [(0.0, True), (du, False)]
    ts += [(step * i, False) for i in range(1, half)]
    ts += [(math.pi - du, False), (math.pi, True), (math.pi + dl, False)]
    ts += [(step * i, False) for i in range(half + 1, BODY_SEGS)]
    ts += [(2.0 * math.pi - dl, False)]
    pts = []
    grooved = []
    for t, g in ts:
        c, s = math.cos(t), math.sin(t)
        y = w * _se(c)
        z = BODY_ZC + (ht if s >= 0.0 else hb) * _se(s)
        if g:
            y -= math.copysign(GROOVE, c)
        grooved.append(g)
        pts.append((y, z))
    if inset > 0.0:
        out = []
        for y, z in pts:
            d = math.hypot(y, z - BODY_ZC)
            k = 1.0 - inset / d
            out.append((y * k, BODY_ZC + (z - BODY_ZC) * k))
        pts = out
    n = len(pts)
    # the belly below the parting line is dark moulding, the canopy light
    seg_mats = [GRAPHITE_IDX if (grooved[j] or grooved[(j + 1) % n]
                                 or pts[j][1] + pts[(j + 1) % n][1] < 2.0 * BODY_ZC)
                else BODY_IDX for j in range(n)]
    return pts, seg_mats


def body_stations():
    x_end = BODY_LB * BODY_END
    xs = [x_end * math.sin(0.5 * math.pi * (-1.0 + 2.0 * k / (BODY_STATIONS - 1)))
          for k in range(BODY_STATIONS)]
    xs = [x for x in xs if all(abs(x - g) > 0.005 for g in PANEL_X)]
    st = [(x, 0.0, False) for x in xs]
    for g in PANEL_X:
        st += [(g - 0.0013, 0.0, False), (g, GROOVE, True), (g + 0.0013, 0.0, False)]
    st.sort()
    st = [(-x_end - 0.0012, CAP_CHAMFER, False)] + st + [(x_end + 0.0012, CAP_CHAMFER, False)]
    return st


def add_body(bm):
    rings, ring_mats, dark = [], [], []
    for x, inset, is_groove in body_stations():
        pts, seg_mats = body_ring(max(-BODY_LB * BODY_END, min(BODY_LB * BODY_END, x)), inset)
        rings.append([bm.verts.new((x, y, z)) for y, z in pts])
        ring_mats.append(seg_mats)
        dark.append(is_groove)
    n = len(rings[0])
    for k, (r0, r1) in enumerate(zip(rings, rings[1:])):
        for j in range(n):
            m = (j + 1) % n
            f = bm.faces.new((r0[j], r0[m], r1[m], r1[j]))
            f.material_index = GRAPHITE_IDX if (dark[k] or dark[k + 1]) else ring_mats[k][j]
    f0 = bm.faces.new(tuple(reversed(rings[0])))
    f1 = bm.faces.new(tuple(rings[-1]))
    f0.material_index = BODY_IDX
    f1.material_index = BODY_IDX


def surface_frame(p, along):
    """Frame on the shell at ``p``: local Z the outward normal, local X
    ``along`` laid into the tangent plane."""
    return frame(body_normal(p), along)


# --------------------------------------------------------------------------
# Assemblies
# --------------------------------------------------------------------------

def blade_beta(r):
    return min(math.radians(PROP_BETA_MAX), math.atan(PROP_PITCH / (2.0 * math.pi * r)))


def naca_half(x, t):
    return 5.0 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x * x
                      + 0.2843 * x ** 3 - 0.1036 * x ** 4)


def add_blade(bm, hub_c, e_r, spin, scale=1.0):
    """One lofted blade: twisted, cambered, swept back behind its motion."""
    e_t = (ZAX.cross(e_r)) * spin
    secs = []
    for r, chord, thick in BLADE_STATIONS:
        rr = r * scale
        beta = blade_beta(r)
        cdir = -math.cos(beta) * e_t - math.sin(beta) * ZAX
        ndir = -math.sin(beta) * e_t + math.cos(beta) * ZAX
        sweep = -BLADE_SWEEP * (max(0.0, r - 0.040) / (PROP_R - 0.040)) ** 2
        base = hub_c + e_r * rr + e_t * sweep
        ring = []
        for k, xc in enumerate(AIRFOIL_X):
            upper = k < 5
            camber = BLADE_CAMBER * chord * 4.0 * xc * (1.0 - xc)
            yt = naca_half(xc, thick)
            y = camber + (yt if upper else -yt)
            ring.append(bm.verts.new(base + cdir * ((xc - BLADE_PIVOT) * chord) + ndir * y))
        secs.append(ring)
    n = len(AIRFOIL_X)
    faces = []
    for r0, r1 in zip(secs, secs[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(secs[0]))))
    faces.append(bm.faces.new(tuple(secs[-1])))
    _mark(faces, CARBON_IDX)
    return [v for s in secs for v in s]


def motor_stack(z_arm):
    """Heights of the motor stack above the arm axis."""
    plate0 = z_arm + 0.0115
    plate1 = plate0 + 0.0060
    base0 = plate1 - 0.0006
    bell0 = base0 + 0.0052
    bell1 = bell0 + 0.0172
    hub0 = bell1 - 0.0008
    return {"plate0": plate0, "plate1": plate1, "base0": base0, "bell0": bell0,
            "bell1": bell1, "hub0": hub0, "prop": hub0 + 0.0050}


def add_arm(bm, i, bevel_verts, unlock=False, long_blades=False):
    phi = math.radians(MOTOR_DEG[i])
    e_r = Vector((math.cos(phi), math.sin(phi), 0.0))
    e_t = Vector((-math.sin(phi), math.cos(phi), 0.0))
    r_b = body_ray(phi, ARM_Z)
    r_p = r_b + PIN_GAP
    pin = e_r * r_p + Vector((0.0, 0.0, ARM_Z))
    lug_rot = Matrix((e_r, e_t, ZAX)).transposed()   # u radial, v tangential, w up
    arm_rot = frame(e_r, ZAX)                          # local Z along the arm

    # --- body side: clevis block, two lugs, hinge pin
    add_rbox(bm, 0.0165, 0.0155, 0.006,
             [(0.0, r_b - 0.018), (0.0, r_p - 0.0080), (0.0015, r_p - 0.0065)],
             (0.0, 0.0, ARM_Z), frame(e_r, e_t), GRAPHITE_IDX)
    for k, (z0, z1, rad) in enumerate(((0.0068, 0.0138, 0.0125), (-0.0138, -0.0068, 0.0121))):
        back = r_p - 0.014 - 0.0012 * k
        ol = lug_outline([(r_p, 0.0, rad)], [(back, rad), (back, -rad)], n=20 + 2 * k)
        bevel_verts += add_prism(bm, ol, ARM_Z + z0, ARM_Z + z1, (0.0, 0.0, 0.0), lug_rot,
                                 GRAPHITE_IDX)
    pprof = [(0.0024, -0.0138 - 0.0020), (0.0036, -0.0138 - 0.0016),
             (0.0040, -0.0138 - 0.0006), (0.0040, -0.0136), (0.0022, -0.0136),
             (0.0022, 0.0136), (0.0040, 0.0136), (0.0040, 0.0138 + 0.0006),
             (0.0036, 0.0138 + 0.0016), (0.0024, 0.0138 + 0.0020)]
    add_lathe(bm, pprof, 14, METAL_IDX, center=pin, solid=True)

    # --- arm side: tongue, root cuff, lock ring, tube, motor cuff ...
    side = []
    ol = lug_outline([(r_p, 0.0, 0.0118)], [(r_p + 0.022, 0.0100), (r_p + 0.022, -0.0100)])
    tongue = add_prism(bm, ol, ARM_Z - 0.0057, ARM_Z + 0.0057, (0.0, 0.0, 0.0), lug_rot,
                       GRAPHITE_IDX)
    bevel_verts += tongue
    side += tongue
    side += add_lathe(bm, [(0.0135, 0.0), (0.0150, 0.0015), (0.0150, 0.0365), (0.0137, 0.038)],
                      32, GRAPHITE_IDX, center=pin + e_r * 0.006, rot=arm_rot, solid=True)

    def knurl(ii, j):
        return 0.94 if (j in (1, 2) and ii % 2) else 1.0

    side += add_lathe(bm, [(0.0158, 0.0), (0.0172, 0.0012), (0.0172, 0.0158), (0.0158, 0.017)],
                      40, ANODIZED_IDX, center=pin + e_r * 0.017, rot=arm_rot, solid=True,
                      rmod=knurl)
    motor = e_r * MOTOR_R + Vector((0.0, 0.0, ARM_Z))
    side += add_tube(bm, [pin + e_r * 0.030, motor + e_r * 0.006], ARM_R, 24, CARBON_IDX)
    side += add_lathe(bm, [(0.0140, 0.0), (0.0152, 0.0012), (0.0152, 0.0373), (0.0140, 0.0385)],
                      32, GRAPHITE_IDX, center=motor - e_r * 0.0225, rot=arm_rot, solid=True,
                      phase=math.pi / 32.0)
    # navigation light on the cuff's end: red forward, green aft (by shader)
    side += add_lathe(bm, [(0.0075, 0.0), (0.0080, 0.0012), (0.0066, 0.0032), (0.0036, 0.0043),
                           (0.0010, 0.0046)], 24, LED_IDX, center=motor + e_r * 0.0155,
                      rot=arm_rot, solid=True)
    # two clamp screws on the cuff's flank
    for k, dr in enumerate((-0.014, 0.008)):
        c = motor + e_r * dr
        side += add_lathe(bm, screw_profile(0.0135 - 0.0002 * k, 0.0177 + 0.0002 * k, 0.0026), 12,
                          METAL_IDX, center=c, rot=frame(e_t, ZAX), solid=True,
                          phase=k * math.pi / 24.0)
    st = motor_stack(ARM_Z)
    axis = Vector((motor.x, motor.y, 0.0))
    side += add_lathe(bm, [(0.0280, 0.0), (0.0296, 0.0014), (0.0296, 0.0046), (0.0282, 0.0060)],
                      48, GRAPHITE_IDX, center=axis + ZAX * st["plate0"], solid=True)
    for k in range(4):
        a = phi + math.pi / 4.0 + 0.5 * math.pi * k
        c = axis + Vector((math.cos(a), math.sin(a), 0.0)) * 0.0250 + ZAX * st["plate1"]
        side += add_lathe(bm, screw_profile(-0.0009 - 0.00015 * k, 0.0010 + 0.00015 * k, 0.0021),
                          10, METAL_IDX, center=c, solid=True, phase=k * math.pi / 20.0)
    side += add_lathe(bm, [(0.0200, 0.0), (0.0214, 0.0010), (0.0214, 0.0048), (0.0204, 0.0060)],
                      48, METAL_IDX, center=axis + ZAX * st["base0"], solid=True,
                      phase=math.pi / 48.0)

    def slots(ii, j):
        return 0.93 if (j in (2, 3) and ii % 4 in (0, 1)) else 1.0

    side += add_lathe(bm, [(0.0222, 0.0), (0.0228, 0.0010), (0.0228, 0.0030), (0.0228, 0.0110),
                           (0.0228, 0.0150), (0.0218, 0.0165), (0.0180, 0.0172)],
                      48, METAL_IDX, center=axis + ZAX * st["bell0"], solid=True, rmod=slots)
    side += add_lathe(bm, [(0.0221, 0.0), (0.0233, 0.0006), (0.0233, 0.0030), (0.0221, 0.0036)],
                      48, ANODIZED_IDX, center=axis + ZAX * (st["bell0"] + 0.0114),
                      phase=math.pi / 48.0)
    for k in range(4):
        a = phi + 0.5 * math.pi * k
        c = axis + Vector((math.cos(a), math.sin(a), 0.0)) * 0.0155 + ZAX * st["bell1"]
        side += add_lathe(bm, screw_profile(-0.0011 - 0.00015 * k, 0.0012 + 0.00015 * k, 0.0017),
                          10, METAL_IDX, center=c, solid=True, phase=k * math.pi / 20.0)
    # the propeller: hub, spinner (red on the counter-clockwise props), blades
    side += add_lathe(bm, [(0.0125, 0.0), (0.0134, 0.0009), (0.0134, 0.0091), (0.0120, 0.0100)],
                      32, CARBON_IDX, center=axis + ZAX * st["hub0"], solid=True)
    cap_mat = ANODIZED_IDX if SPIN[i] > 0 else METAL_IDX
    side += add_lathe(bm, [(0.0092, 0.0), (0.0100, 0.0010), (0.0096, 0.0036), (0.0070, 0.0060),
                           (0.0035, 0.0071), (0.0010, 0.0074)], 32, cap_mat,
                      center=axis + ZAX * (st["hub0"] + 0.0094), solid=True)
    hub_c = axis + ZAX * st["prop"]
    psi = math.radians(PROP_PARK_DEG[i])
    for sgn in (1.0, -1.0):
        e_b = Vector((math.cos(psi), math.sin(psi), 0.0)) * sgn
        scale = (PROP_R + LONG_BLADES) / PROP_R if long_blades else 1.0
        side += add_blade(bm, hub_c, e_b, SPIN[i], scale)

    if unlock:
        # the arm folded a few degrees back about its hinge pin: not locked open
        rz = Matrix.Rotation(math.radians(UNLOCK_DEG), 3, "Z")
        for v in side:
            v.co = pin + rz @ (v.co - pin)


def add_landing_gear(bm, narrow, float_foot):
    sy_abs = SKID_Y_NARROW if narrow else SKID_Y
    for s in (1.0, -1.0):
        sy = s * sy_abs
        add_tube(bm, [(-SKID_HALF, sy, FOOT_R), (SKID_HALF, sy, FOOT_R)], SKID_R, 16, CARBON_IDX)
        for sx in (1.0, -1.0):
            lift = FLOAT_FOOT if (float_foot and s > 0 and sx > 0) else 0.0
            rot = frame((sx, 0.0, 0.0), (0.0, 0.0, -1.0))
            add_lathe(bm, [(0.0098, 0.0), (0.0115, 0.0025), (0.0115, 0.0220), (0.0105, 0.0285),
                           (0.0075, 0.0325), (0.0030, 0.0345)], 24, RUBBER_IDX,
                      center=(sx * FOOT_X0, sy, FOOT_R + lift), rot=rot, solid=True)
            # T-collar on the skid, strut into it, root pad under the belly
            add_lathe(bm, [(0.0098, 0.0), (0.0108, 0.0010), (0.0108, 0.0210), (0.0098, 0.0220)],
                      24, GRAPHITE_IDX, center=(sx * STRUT_X_BOT - 0.011, sy, FOOT_R),
                      rot=frame((1.0, 0.0, 0.0), (0.0, 0.0, -1.0)), solid=True,
                      phase=math.pi / 24.0)
            xt, yt = sx * STRUT_X_TOP, s * STRUT_Y_TOP
            zt = body_bottom(xt, yt)
            add_rbox(bm, 0.013, 0.011, 0.005, [(0.0012, zt - 0.0068), (0.0, zt - 0.0056),
                                               (0.0, zt + 0.0050)],
                     (xt, yt, 0.0), Matrix.Identity(3), GRAPHITE_IDX)
            add_tube(bm, [(xt, yt, zt - 0.0030), (sx * STRUT_X_BOT, sy, FOOT_R + 0.0040)],
                     STRUT_R, 14, CARBON_IDX)


def add_gimbal(bm, bevel_verts, drop_lens):
    zb = body_bottom(GX, 0.0)
    zcam = zb - 0.070
    ident = Matrix.Identity(3)
    add_rbox(bm, 0.026, 0.024, 0.006, [(0.0012, zb - 0.0055), (0.0, zb - 0.0043),
                                       (0.0, zb + 0.0120)], (GX, 0.0, 0.0), ident, GRAPHITE_IDX)
    for k, (sx, sy) in enumerate(((1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0))):
        add_sphere(bm, (GX + sx * 0.017, sy * 0.016, zb - 0.0108), 0.0058, RUBBER_IDX,
                   spin=k * math.pi / 32.0)
    add_rbox(bm, 0.022, 0.020, 0.005, [(0.0010, zb - 0.0215), (0.0, zb - 0.0205),
                                       (0.0, zb - 0.0165), (0.0010, zb - 0.0155)],
             (GX, 0.0, 0.0), ident, GRAPHITE_IDX)

    def band(ii, j):
        return 0.95 if (j in (2, 3) and ii % 2) else 1.0

    # yaw motor
    add_lathe(bm, [(0.0140, 0.0), (0.0160, 0.0015), (0.0160, 0.0050), (0.0160, 0.0110),
                   (0.0160, 0.0135), (0.0150, 0.0155)], 40, METAL_IDX,
              center=(GX, 0.0, zb - 0.0360), solid=True, rmod=band)
    # yaw arm: back, down, forward into the roll motor
    add_bar(bm, [(GX + 0.008, 0.0, zb - 0.0375), (GX - 0.056, 0.0, zb - 0.0375),
                 (GX - 0.056, 0.0, zcam), (GX - 0.041, 0.0, zcam)],
            (0.0, 1.0, 0.0), 0.0080, 0.0030, 0.0018, GRAPHITE_IDX)
    # roll motor (axis along X)
    rx = frame((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    add_lathe(bm, [(0.0150, 0.0), (0.0165, 0.0012), (0.0165, 0.0040), (0.0165, 0.0080),
                   (0.0165, 0.0108), (0.0150, 0.0120)], 40, METAL_IDX,
              center=(GX - 0.050, 0.0, zcam), rot=rx, solid=True, rmod=band)
    # roll arm: out to the camera's flank and forward to the pitch motor
    add_bar(bm, [(GX - 0.043, 0.0, zcam), (GX - 0.034, 0.0, zcam), (GX - 0.034, 0.047, zcam),
                 (GX + 0.002, 0.047, zcam)],
            (0.0, 0.0, 1.0), 0.0080, 0.0030, 0.0018, GRAPHITE_IDX, fillet=0.007)
    # pitch motor (axis along Y) and the bearing cap opposite
    ry = frame((0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    add_lathe(bm, [(0.0145, 0.0), (0.0160, 0.0012), (0.0160, 0.0050), (0.0160, 0.0110),
                   (0.0160, 0.0150), (0.0148, 0.0165)], 40, METAL_IDX,
              center=(GX, 0.0285, zcam), rot=ry, solid=True, rmod=band)
    add_lathe(bm, [(0.0100, 0.0), (0.0110, 0.0010), (0.0110, 0.0035), (0.0100, 0.0045)], 32,
              METAL_IDX, center=(GX, -0.0285, zcam), rot=frame((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
              solid=True)
    # camera body, top grille
    cam_rot = frame((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    add_rbox(bm, CAM_HALF[0], CAM_HALF[1], 0.009,
             [(0.0015, GX - 0.030), (0.0, GX - 0.0285), (0.0, GX + 0.0305), (0.0015, GX + 0.032)],
             (0.0, 0.0, zcam), cam_rot, GRAPHITE_IDX, n_corner=5)
    top_rot = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))  # u=x, v=z, w=-y
    bevel_verts += add_prism(bm, comb_outline(0.0175, -0.0010, 0.0006, 6, 0.0011, 0.0018),
                             -0.016, 0.016, (GX - 0.004, 0.0, zcam + CAM_HALF[1]), top_rot,
                             GRAPHITE_IDX)
    # lens: ribbed barrel (a ring shell), silver front ring, glass element
    lx = GX + 0.0305

    def ribs(ii, j):
        return 0.955 if (j in (4, 5) and ii % 2) else 1.0

    add_lathe(bm, [(0.0150, 0.0), (0.0198, 0.0), (0.0210, 0.0015), (0.0210, 0.0070),
                   (0.0216, 0.0080), (0.0216, 0.0170), (0.0210, 0.0180), (0.0210, 0.0255),
                   (0.0200, 0.0270), (0.0165, 0.0270), (0.0165, 0.0040), (0.0150, 0.0040)],
              64, GRAPHITE_IDX, center=(lx, 0.0, zcam), rot=rx, rmod=ribs)
    add_lathe(bm, [(0.0180, 0.0245), (0.0212, 0.0245), (0.0219, 0.0252), (0.0219, 0.0285),
                   (0.0206, 0.0292), (0.0180, 0.0292)], 64, METAL_IDX,
              center=(lx, 0.0, zcam), rot=rx, phase=math.pi / 64.0)
    gx = lx + (LENS_DROP if drop_lens else 0.0)
    add_lathe(bm, [(0.0169, 0.0205), (0.0172, 0.0230), (0.0160, 0.0262), (0.0130, 0.0284),
                   (0.0085, 0.0298), (0.0030, 0.0304)], 48, GLASS_IDX,
              center=(gx, 0.0, zcam), rot=rx, solid=True)


def add_top(bm, bevel_verts):
    """Battery pack, GPS puck, nose grille, flank grilles, visor, tail light,
    antennas."""
    ident = Matrix.Identity(3)
    # battery: seated below the lowest point of the crown under its footprint
    hx, hy = BATT_HALF
    lo = min(body_top(BATT_X + hx * a, hy * b) for a in (-1.0, 0.0, 1.0) for b in (-1.0, 0.0, 1.0))
    z0 = lo - 0.004
    add_rbox(bm, hx, hy, 0.012, [(0.0015, z0), (0.0, z0 + 0.0015), (0.0, BATT_TOP - 0.0035),
                                 (0.0035, BATT_TOP)], (BATT_X, 0.0, 0.0), ident, GRAPHITE_IDX,
             n_corner=5)
    top_rot = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))  # u=x, v=z, w=-y
    bevel_verts += add_prism(bm, comb_outline(0.036, -0.0012, 0.0004, 9, 0.0013, 0.0016),
                             -0.022, 0.022, (BATT_X + 0.004, 0.0, BATT_TOP), top_rot,
                             GRAPHITE_IDX)
    for s in (1.0, -1.0):
        rot = frame((0.0, s, 0.0), (1.0, 0.0, 0.0))
        zc = BATT_TOP - 0.013 - (0.0003 if s < 0 else 0.0)
        bevel_verts += add_rbox(bm, 0.013, 0.0055, 0.003, [(0.0, -0.002), (0.0, 0.0022),
                                                          (0.0010, 0.0032)],
                                (BATT_X + 0.012, s * hy, zc), rot, ANODIZED_IDX)
    rear = frame((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    xr = BATT_X - hx
    add_lathe(bm, [(0.0034, -0.0020), (0.0034, 0.0010), (0.0028, 0.0018), (0.0012, 0.0021)], 20,
              METAL_IDX, center=(xr, -0.016, BATT_TOP - 0.013), rot=rear, solid=True)
    for k in range(4):
        add_lathe(bm, [(0.0012, -0.0012 - 0.00015 * k), (0.0012, 0.0004 + 0.00015 * k),
                       (0.0007, 0.0009 + 0.00015 * k)], 10, LED_IDX,
                  center=(xr, -0.004 + 0.006 * k, BATT_TOP - 0.013), rot=rear, solid=True,
                  phase=k * math.pi / 20.0)
    # GPS puck on a mast
    zt = body_top(GPS_X, 0.0)
    add_lathe(bm, [(0.0062, -0.004), (0.0062, 0.0100), (0.0055, 0.0106)], 24, GRAPHITE_IDX,
              center=(GPS_X, 0.0, zt), solid=True)
    add_lathe(bm, [(0.0200, 0.0), (0.0215, 0.0015), (0.0215, 0.0060), (0.0180, 0.0095),
                   (0.0110, 0.0118), (0.0030, 0.0126)], 40, BODY_IDX,
              center=(GPS_X, 0.0, zt + 0.0090), solid=True)
    add_lathe(bm, [(0.0212, 0.0), (0.0222, 0.0005), (0.0222, 0.0022), (0.0212, 0.0027)], 40,
              GRAPHITE_IDX, center=(GPS_X, 0.0, zt + 0.0080))
    # nose grille, laid on the crown
    p = Vector((VENT_X, 0.0, body_top(VENT_X, 0.0)))
    rot = surface_frame(p, (1.0, 0.0, 0.0))
    grille = Matrix((rot.col[0], rot.col[2], -rot.col[1])).transposed()
    bevel_verts += add_prism(bm, comb_outline(0.017, -0.0035, 0.0006, 6, 0.0012, 0.0019),
                             -0.019, 0.019, p, grille, GRAPHITE_IDX)
    # flank grilles, above the parting line behind the rear arms
    for s in (1.0, -1.0):
        z = BODY_ZC + 0.0105
        p = Vector((-0.086, s * body_side_y(-0.086, z), z))
        rot = surface_frame(p, (1.0, 0.0, 0.0))
        grille = Matrix((rot.col[0], rot.col[2], -rot.col[1])).transposed()
        bevel_verts += add_prism(bm, comb_outline(0.017, -0.0035, 0.0005, 5, 0.0011, 0.0016),
                                 -0.0045, 0.0045, p, grille, GRAPHITE_IDX)
    # sensor visor on the nose face, two stereo lenses
    x_end = BODY_LB * BODY_END + 0.0012
    w, ht, hb = body_dims(BODY_LB * BODY_END)
    zc = BODY_ZC + 0.5 * (ht - hb)
    nose = frame((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    bevel_verts += add_prism(bm, rrect(0.0150, 0.0055, 0.0040, 4), -0.004, 0.0012,
                             (x_end, 0.0, zc), nose, GRAPHITE_IDX)
    for k, s in enumerate((1.0, -1.0)):
        add_lathe(bm, [(0.0034, -0.0002 * k), (0.0034, 0.0018 + 0.0002 * k),
                       (0.0026, 0.0026 + 0.0002 * k), (0.0010, 0.0030 + 0.0002 * k)], 20,
                  GLASS_IDX, center=(x_end + 0.0004, s * 0.0085, zc), rot=nose, solid=True,
                  phase=k * math.pi / 40.0)
    # tail light bar
    w, ht, hb = body_dims(-BODY_LB * BODY_END)
    zc = BODY_ZC + 0.5 * (ht - hb)
    tail = frame((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    add_prism(bm, rrect(0.018, 0.0028, 0.0024, 4), -0.003, 0.0010, (-x_end, 0.0, zc), tail,
              LED_IDX)
    # antennas: down and back from the belly, splayed out
    for s in (1.0, -1.0):
        xa, ya = -0.100, s * 0.030
        za = body_bottom(xa, ya)
        add_lathe(bm, [(0.0055, -0.0060), (0.0060, 0.0020), (0.0050, 0.0035)], 20,
                  GRAPHITE_IDX, center=(xa, ya, za + 0.0015),
                  rot=frame((0.0, 0.0, -1.0), (1.0, 0.0, 0.0)), solid=True)
        d = Vector((-0.42, s * 0.30, -1.0)).normalized()
        add_lathe(bm, [(0.0036, 0.0), (0.0038, 0.004), (0.0033, 0.030), (0.0030, 0.056),
                       (0.0034, 0.058), (0.0034, 0.066), (0.0024, 0.070), (0.0010, 0.0712)],
                  16, GRAPHITE_IDX, center=(xa, ya, za - 0.0020), rot=frame(d, (1.0, 0.0, 0.0)),
                  solid=True)


def build_drone_mesh(name, bevel_offset, bevel_segments, unlock_arm=False, long_blades=False,
                     narrow_skids=False, float_foot=False, drop_lens=False):
    bm = bmesh.new()
    try:
        bevel_verts = []
        add_body(bm)
        for i in range(4):
            add_arm(bm, i, bevel_verts, unlock=(unlock_arm and i == UNLOCK_ARM),
                    long_blades=(long_blades and i == UNLOCK_ARM))
        add_landing_gear(bm, narrow_skids, float_foot)
        add_gimbal(bm, bevel_verts, drop_lens)
        add_top(bm, bevel_verts)

        if bevel_offset > 0.0:
            # Chamfer the prism plates' rims, one pass per material with
            # material= set, over sorted edges.
            for mat_idx in (GRAPHITE_IDX, ANODIZED_IDX):
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
        # Moulded shell, tubes, blades and lathes are smooth-shaded; grilles,
        # chamfers and knurls stay crisp through sharp edges.
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
        bsdf.inputs["Coat Roughness"].default_value = 0.06
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


def drone_materials():
    """(body, carbon, metal, glass, led, rubber, graphite, anodized): shared
    by the check and the render.

    The shell is a warm light-grey moulding with a clear coat; arms, skids,
    hubs and blades are glossy carbon; motors, pins and screws gunmetal; the
    lens and stereo sensors dark glass; the lights emit red forward of the
    body's centre and green aft of it (object-space X); feet and dampers
    rubber; clevises, battery, gimbal and grilles a dark graphite plastic;
    the lock rings, latches, top bands and the counter-clockwise spinners
    red anodised aluminium.
    """
    body = principled("DroneShell", (0.60, 0.605, 0.60, 1.0), 0.0, 0.34,
                      roughness_var=0.06, mottle=0.04, noise_scale=30.0, coat=0.25)
    carbon = principled("DroneCarbon", (0.024, 0.025, 0.028, 1.0), 0.0, 0.26,
                        roughness_var=0.06, mottle=0.12, noise_scale=160.0, coat=0.8)
    metal = principled("DroneGunmetal", (0.34, 0.35, 0.37, 1.0), 1.0, 0.30,
                       roughness_var=0.08, noise_scale=90.0)
    glass = principled("DroneLensGlass", (0.012, 0.018, 0.035, 1.0), 0.0, 0.04, coat=1.0)
    led = principled("DroneNavLight", (1.0, 1.0, 1.0, 1.0), 0.0, 0.25)
    nt = led.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    _emission(bsdf, (1.0, 1.0, 1.0, 1.0), 6.0)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.05, 1.0, 0.18, 1.0)
    ramp.color_ramp.elements[1].position = 0.5
    ramp.color_ramp.elements[1].color = (1.0, 0.06, 0.03, 1.0)
    gt = nt.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = 0.0
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["X"], gt.inputs[0])
    nt.links.new(gt.outputs["Value"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    for key in ("Emission Color", "Emission"):
        if key in bsdf.inputs:
            nt.links.new(ramp.outputs["Color"], bsdf.inputs[key])
            break
    rubber = principled("DroneRubber", (0.022, 0.022, 0.024, 1.0), 0.0, 0.72,
                        roughness_var=0.08, noise_scale=80.0)
    graphite = principled("DroneGraphite", (0.050, 0.052, 0.058, 1.0), 0.0, 0.42,
                          roughness_var=0.08, mottle=0.15, noise_scale=70.0)
    anodized = principled("DroneAnodised", (0.62, 0.050, 0.030, 1.0), 1.0, 0.32,
                          roughness_var=0.06, noise_scale=60.0)
    return body, carbon, metal, glass, led, rubber, graphite, anodized


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
    return c, axis


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    parts = [Shell(me, i, g, polys[i]) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    # the shell is two-tone (light canopy, dark belly): the largest shell
    # that carries any canopy faces
    bodies = [s for s in parts if BODY_IDX in s.mats]
    out["body"] = max(bodies, key=lambda s: len(s.verts)) if bodies else None
    out["bells"] = [s for s in parts if s.mat == METAL_IDX
                    and 0.040 < s.size.x < 0.050 and 0.040 < s.size.y < 0.050
                    and 0.012 < s.size.z < 0.024]
    top = min((b.hi.z for b in out["bells"]), default=0.0)
    carbon = [s for s in parts if s.mat == CARBON_IDX]
    out["hubs"] = [s for s in carbon if 0.024 < s.size.x < 0.030 and 0.024 < s.size.y < 0.030
                   and s.size.z < 0.012]
    out["blades"] = [s for s in carbon if max(s.size.x, s.size.y) > 0.08 and s.size.z < 0.03
                     and s.lo.z > top - 0.012]
    out["feet"] = [s for s in parts if s.mat == RUBBER_IDX and s.hi.z < 0.04]
    return out


def feet_audit(cls):
    return [f.lo.z for f in cls["feet"]]


def layout_audit(cls):
    """Motor axes about the body centre: angular gaps, radii, diagonals,
    tilt; hub heights and hubs on their motor axes."""
    body = cls["body"]
    cx, cy = (body.centre.x, body.centre.y) if body else (0.0, 0.0)
    motors = []
    for b in cls["bells"]:
        _c, ax = pca_axis(b.pts, largest=False)
        tilt = math.degrees(math.acos(min(1.0, abs(float(ax[2])))))
        ang = math.degrees(math.atan2(b.mean.y - cy, b.mean.x - cx)) % 360.0
        motors.append((ang, b.mean.x, b.mean.y, tilt))
    motors.sort()
    res = {"motors": len(motors), "hubs": len(cls["hubs"]), "angle_err": 0.0,
           "radius_spread": 0.0, "diag": [], "diag_diff": 0.0, "tilt": 0.0,
           "hub_z_spread": 0.0, "hub_axis": 0.0, "centroid": 0.0, "angles": []}
    if len(motors) != MOTOR_COUNT:
        return res
    angs = [m[0] for m in motors]
    gaps = [((angs[(k + 1) % 4] - angs[k]) % 360.0) for k in range(4)]
    res["angles"] = [round(a, 3) for a in angs]
    res["angle_err"] = max(abs(g - 90.0) for g in gaps)
    radii = [math.hypot(m[1] - cx, m[2] - cy) for m in motors]
    res["radius_spread"] = max(radii) - min(radii)
    diag = [math.hypot(motors[k][1] - motors[k + 2][1], motors[k][2] - motors[k + 2][2])
            for k in range(2)]
    res["diag"] = diag
    res["diag_diff"] = abs(diag[0] - diag[1])
    res["tilt"] = max(m[3] for m in motors)
    mx = sum(m[1] for m in motors) / 4.0
    my = sum(m[2] for m in motors) / 4.0
    res["centroid"] = math.hypot(mx - cx, my - cy)
    hz = [h.mean.z for h in cls["hubs"]]
    if hz:
        res["hub_z_spread"] = max(hz) - min(hz)
    res["hub_axis"] = max((min(math.hypot(h.mean.x - m[1], h.mean.y - m[2]) for m in motors)
                           for h in cls["hubs"]), default=9.0)
    return res


def clearance_audit(cls):
    """Per propeller: the swept disc radius of its blades about its motor
    axis, its blade count, blades seated in the hub; per neighbouring pair of
    motors, the gap between their discs."""
    bells = cls["bells"]
    motors = sorted(((math.atan2(b.mean.y, b.mean.x) % (2.0 * math.pi), b) for b in bells),
                    key=lambda t: t[0])
    res = {"discs": [], "blades": [], "unseated": 0, "clear": []}
    if len(motors) != MOTOR_COUNT:
        return res
    own = {k: [] for k in range(4)}
    for bl in cls["blades"]:
        k = min(range(4), key=lambda q: math.hypot(bl.mean.x - motors[q][1].mean.x,
                                                   bl.mean.y - motors[q][1].mean.y))
        own[k].append(bl)
    for k in range(4):
        b = motors[k][1]
        hub = min(cls["hubs"], key=lambda h: math.hypot(h.mean.x - b.mean.x, h.mean.y - b.mean.y))
        r = 0.0
        for bl in own[k]:
            r = max(r, max(math.hypot(p.x - b.mean.x, p.y - b.mean.y) for p in bl.pts))
            if not bl.tree.overlap(hub.tree):
                res["unseated"] += 1
        res["discs"].append(r)
        res["blades"].append(len(own[k]))
    for k in range(4):
        a, b = motors[k][1], motors[(k + 1) % 4][1]
        d = math.hypot(a.mean.x - b.mean.x, a.mean.y - b.mean.y)
        res["clear"].append(d - res["discs"][k] - res["discs"][(k + 1) % 4])
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


def stance_audit(cls, lay):
    """Mass centre against the feet's ground-contact footprint; wheelbase and
    body size read off the mesh."""
    total = 0.0
    mom = Vector()
    for s in cls["all"]:
        if s.mat is None:
            continue
        vol, cen = shell_mass(s)
        # the moulded shell is weighed as a hollow moulding with its
        # electronics, whichever tone covers more of it
        m = abs(vol) * DENSITY[BODY_IDX if s is cls["body"] else s.mat]
        total += m
        mom += m * cen
    com = mom / total
    # each foot's own sole (its lowest ring), whether or not it is grounded:
    # grounding is the feet budget's job (exit 16), the footprint's shape is this one's
    contact = [(p.x, p.y) for f in cls["feet"] for p in f.pts if p.z < f.lo.z + 0.0005]
    margin = -1.0
    if len(contact) >= 3:
        hull = hull2d(contact)
        margin = 9.0
        for k in range(len(hull)):
            a, b = hull[k], hull[(k + 1) % len(hull)]
            ex, ey = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ex, ey)
            margin = min(margin, (ex * (com.y - a[1]) - ey * (com.x - a[0])) / ln)
    body = cls["body"]
    wheel = sum(lay["diag"]) / len(lay["diag"]) if lay["diag"] else 0.0
    return {"mass": total, "com": com, "margin": margin, "wheelbase": wheel,
            "body": (body.size.x, body.size.y) if body else (0.0, 0.0)}


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
        bm.verts.new((0.0, 0.0, 0.12))
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
    img = bpy.data.images.new("DroneNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = GRAPHITE_IDX
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


def check(skip_decimate, lift_z=False, stray_vert=False, float_foot=False, unlock_arm=False,
          long_blades=False, narrow_skids=False, drop_lens=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(unlock_arm=unlock_arm, long_blades=long_blades, narrow_skids=narrow_skids,
                 float_foot=float_foot, drop_lens=drop_lens)
    low = build_drone_mesh("DroneLow", bevel_offset=0.0005, bevel_segments=1, **flags)
    high = build_drone_mesh("DroneHigh", bevel_offset=0.0005, bevel_segments=3, **flags)
    mats = drone_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the graphite: the grilles, lugs and tongues are where
    # the high mesh's rounder chamfer differs from the low.
    target = mats[GRAPHITE_IDX]

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
        return (fail("drone mesh did not build", 3),) + none3

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
    feet = feet_audit(cls)
    lay = layout_audit(cls)
    clr = clearance_audit(cls)
    stance = stance_audit(cls, lay)
    ncomp, comp_sizes = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("drone has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "DroneLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "DroneLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_drone_mesh("DroneColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "DroneCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_quad_drone_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} feet={len(feet)} "
          f"feet_zmin={[round(z, 5) for z in feet]}")
    print(f"measured motors={lay['motors']} hubs={lay['hubs']} angles={lay['angles']} "
          f"angle_err={lay['angle_err']:.4f} radius_spread={lay['radius_spread']:.6f} "
          f"diag={[round(d, 5) for d in lay['diag']]} diag_diff={lay['diag_diff']:.6f} "
          f"tilt={lay['tilt']:.4f} hub_z_spread={lay['hub_z_spread']:.6f} "
          f"hub_axis={lay['hub_axis']:.6f} centroid={lay['centroid']:.6f}")
    print(f"measured blades={clr['blades']} unseated={clr['unseated']} "
          f"discs={[round(r, 5) for r in clr['discs']]} "
          f"clear={[round(c, 5) for c in clr['clear']]}")
    print(f"measured mass={stance['mass']:.3f}kg com=({stance['com'].x:.4f},"
          f"{stance['com'].y:.4f},{stance['com'].z:.4f}) margin={stance['margin']:.4f} "
          f"wheelbase={stance['wheelbase']:.5f} body=({stance['body'][0]:.4f},"
          f"{stance['body'][1]:.4f})")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    floors = ((BODY_IDX, BODY_FACES_MIN, "shell"), (CARBON_IDX, CARBON_FACES_MIN, "carbon"),
              (METAL_IDX, METAL_FACES_MIN, "gunmetal"), (GLASS_IDX, GLASS_FACES_MIN, "glass"),
              (LED_IDX, LED_FACES_MIN, "light"), (RUBBER_IDX, RUBBER_FACES_MIN, "rubber"),
              (GRAPHITE_IDX, GRAPHITE_FACES_MIN, "graphite"),
              (ANODIZED_IDX, ANODIZED_FACES_MIN, "anodised"))
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
    if len(feet) != FEET_COUNT or max(feet) > ZMIN_EPS:
        return (fail(f"feet: {len(feet)} (want {FEET_COUNT}), zmin per foot "
                     f"{[round(z, 5) for z in feet]} (each must be within {ZMIN_EPS} of 0)", 16),) + none3
    if (lay["motors"] != MOTOR_COUNT or lay["hubs"] != MOTOR_COUNT
            or lay["angle_err"] > ANGLE_TOL_DEG or lay["radius_spread"] > RADIUS_TOL
            or lay["diag_diff"] > DIAG_TOL or lay["tilt"] > AXIS_TILT_MAX_DEG
            or lay["hub_z_spread"] > HUB_Z_TOL or lay["hub_axis"] > HUB_AXIS_TOL
            or lay["centroid"] > CENTROID_TOL):
        return (fail(f"motor layout off an exact X: {lay}", 17),) + none3
    if (len(clr["discs"]) != MOTOR_COUNT or any(n != BLADES_PER_PROP for n in clr["blades"])
            or clr["unseated"] or any(not (CLEAR_MIN <= c <= CLEAR_MAX) for c in clr["clear"])):
        return (fail(f"propeller clearance: discs {[round(r, 4) for r in clr['discs']]}, "
                     f"gaps {[round(c, 4) for c in clr['clear']]} (band [{CLEAR_MIN}, "
                     f"{CLEAR_MAX}]), blades {clr['blades']}, unseated {clr['unseated']}", 18),) + none3
    if (stance["margin"] < STANCE_MARGIN
            or abs(stance["wheelbase"] - WHEELBASE) > WHEELBASE_TOL
            or abs(stance["body"][0] - BODY_LEN) > BODY_TOL
            or abs(stance["body"][1] - BODY_WIDTH) > BODY_TOL):
        return (fail(f"stance: mass centre margin {stance['margin']:.4f} < {STANCE_MARGIN} "
                     f"or size off: {stance}", 19),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 20),) + none3
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

    # The house rig scaled to a 0.7 m prop: warm key upper left, cool fill
    # low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-1.4, -1.8, 1.9), 45.0, 1.0, (1.0, 0.95, 0.90), spread=20.0)
    light("Fill", (2.0, -1.3, 0.4), 7.0, 2.6, (0.72, 0.82, 1.0))
    light("Rim", (-0.6, 1.1, 1.0), 30.0, 0.8, (0.62, 0.78, 1.0))
    light("Wedge", (1.0, 1.2, 0.7), 45.0, 1.2, (1.0, 0.68, 0.38),
          target=(centre.x + 1.4, centre.y + WALL_Y, 0.45))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.55, -0.80, 0.0)).normalized()
    cam.location = centre + view * 1.17 + Vector((0.0, 0.0, 0.48))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.012))
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
    # Standard, not AgX: AgX washes the red anodising toward pastel
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
    p.add_argument("--float-foot", action="store_true")
    p.add_argument("--unlock-arm", action="store_true")
    p.add_argument("--long-blades", action="store_true")
    p.add_argument("--narrow-skids", action="store_true")
    p.add_argument("--drop-lens", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_foot=args.float_foot,
        unlock_arm=args.unlock_arm,
        long_blades=args.long_blades,
        narrow_skids=args.narrow_skids,
        drop_lens=args.drop_lens,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("quad-drone OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
