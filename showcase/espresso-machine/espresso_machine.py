"""Game-ready E61 espresso machine on a countertop — a showcase piece, not an example.

Asserts budget conformance of a procedural prosumer semi-automatic espresso
machine after composing shipped pipeline pieces: bmesh construction, UVs,
fourteen materials, high-to-low normal bake, LOD chain, convex collider,
Unity glTF export.

The machine is the classic E61 pattern, generic and unbranded. A black
painted chassis behind a stainless front panel, two folded side panels with
louvred vent slots, a back panel and a cup-warmer tray with a tubular rail,
on four adjustable feet. The chromed E61 group head — a skirted bayonet ring,
a waisted body and the mushroom cap — hangs off the panel on its cast neck
and thermosiphon pipe; its lever pivots on a pin through two bosses on the
chimney. A spouted portafilter with a walnut handle is locked into the group
against the gasket. Steam and hot-water valves carry bakelite knobs, and
each wand hangs from a ball joint. Twin pressure gauges with printed dials sit
in chrome bezels either side of the group; a toggle switch and a pilot lamp
below. A drip tray with a slotted grate carries a shot cup of espresso; four
upturned cups stand on the warmer tray. On the honed stone counter beside it:
a knock box with spent pucks, a tamper and a milk pitcher.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` / ``--float-foot`` grounded, ``--offset-pin`` the
lever pin coaxial through its bosses, ``--sink-cup`` the cups seated on
their host, ``--narrow-body`` the body's real-world size, ``--offset-pf``
the portafilter coaxial with the group, ``--drop-pf`` the portafilter
seated to the gasket, ``--proud-gauge`` the gauge faces recessed in their
bezels, ``--shift-tray`` the drip tray inside the body's footprint,
``--bunch-feet`` the mass centre inside the feet, ``--loose-knob`` one
connected assembly.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python espresso_machine.py --
    blender --background --python espresso_machine.py -- --skip-decimate
    blender --background --python espresso_machine.py -- --output espresso.png
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

# --- Countertop section (the machine faces -Y, toward the counter's front) --
CT = 0.030                   # slab thickness: the counter top is z = CT
COUNTER_X = (-0.335, 0.335)
COUNTER_Y = (-0.400, 0.255)
COUNTER_R = (0.002, 0.004, 0.011, 0.003)   # back-bottom, front-bottom, bullnose, back-top

# --- Body: black chassis, front / back panels, folded side panels ----------
FOOT_H = 0.012
BODY_Z0 = CT + FOOT_H        # chassis underside
BODY_TOP = CT + 0.380        # chassis top; the warmer tray sits on it
BODY_HX = 0.150              # outer face of the side panels
NARROW_HX = 0.1415           # --narrow-body: 17 mm narrower, the valve flanges still clear the folds
PANEL_T = 0.0020
CORE_IN = 0.006              # chassis side inside the panels' outer face
CORE_Y = (-0.1700, 0.1960)
FP_Y = (-0.1750, -0.1680)    # front panel; its face is 0.5 mm into the side returns
BP_Y = (0.1945, 0.1995)
SIDE_YF, SIDE_YB = -0.1755, 0.2000   # side panel centre line at the front / back fold
RETURN = 0.012               # the folds' reach in from the side
BEND_R = 0.004
VENT_Y = ((0.035, 0.095), (0.110, 0.170))
VENT_Z0 = BODY_TOP - 0.090
VENT_SLOTS = 7
VENT_PITCH = 0.005           # slot height, and bar height between slots

# --- Warmer tray and rail ---------------------------------------------------
TRAY_PROFILE = [(0.0015, 0.0), (0.0, 0.0015), (0.0, 0.0092), (0.0010, 0.0110),
                (0.0026, 0.0112), (0.0036, 0.0100), (0.0048, 0.0036), (0.0062, 0.0026)]
TRAY_Z0 = BODY_TOP - 0.0005
WARM_FLOOR = TRAY_Z0 + TRAY_PROFILE[-1][1]
RAIL_R = 0.0045
RAIL_Y = (-0.140, 0.172)
RAIL_Z = BODY_TOP + 0.032
POST_X = 0.050
LEG_BITE = 0.0008

# --- Cups: (x, y, radial scale, height scale, yaw deg, seat bite) ---------
WARM_CUPS = [(-0.080, -0.100, 1.00, 1.00, -90.0, 0.00020),
             (-0.004, -0.118, 1.00, 1.00, -60.0, 0.00038),
             (0.068, -0.080, 1.30, 1.22, 60.0, 0.00056),
             (0.024, 0.012, 1.00, 1.00, 150.0, 0.00074)]
SHOT_BITE = 0.00035
SINK_CUP = 0.003             # --sink-cup: the big cup this far into the tray
CUP_PROF = [(0.0148, 0.0012), (0.0165, 0.0000), (0.0192, 0.0000), (0.0200, 0.0018),
            (0.0196, 0.0042), (0.0228, 0.0072), (0.0268, 0.0150), (0.0292, 0.0270),
            (0.0304, 0.0400), (0.0310, 0.0495), (0.0307, 0.0516), (0.0296, 0.0524),
            (0.0284, 0.0518), (0.0280, 0.0495), (0.0276, 0.0400), (0.0262, 0.0275),
            (0.0232, 0.0170), (0.0185, 0.0110), (0.0120, 0.0090)]
CUP_OUTER = CUP_PROF[1:11]
CUP_H = 0.0524

# --- Drip tray and grate ----------------------------------------------------
DRIP_HX = 0.125
DRIP_Y = (-0.290, -0.158)
DRIP_R = 0.010
DRIP_Z0 = BODY_Z0 + 0.0022
DRIP_H = 0.033
DRIP_TOP = DRIP_Z0 + DRIP_H
DRIP_PROFILE = [(0.0015, 0.0), (0.0, 0.0015), (0.0, DRIP_H - 0.0015), (0.0012, DRIP_H),
                (0.0035, DRIP_H), (0.0047, DRIP_H - 0.0012), (0.0060, 0.0045), (0.0075, 0.0030)]
GRATE_INSET = 0.0025
GRATE_T = 0.0020
GRATE_Z = DRIP_TOP + 0.0002  # mid-plane: top 1.2 mm proud of the rim, bottom 0.8 mm into it
GRATE_TOP = GRATE_Z + 0.5 * GRATE_T
SLOT_W, BAR_W, N_SLOTS = 0.004, 0.003, 31
SHIFT_TRAY = 0.030           # --shift-tray

# --- E61 group head (vertical axis at (0, GY); heights above ZG, the gasket's face)
GY = FP_Y[0] - 0.0595
ZG = CT + 0.175
GROUP_PROFILE = [(0.0345, -0.0120), (0.0395, -0.0120), (0.0412, -0.0104), (0.0412, 0.0040),
                 (0.0400, 0.0070), (0.0372, 0.0098), (0.0366, 0.0200), (0.0366, 0.0500),
                 (0.0380, 0.0570), (0.0414, 0.0625), (0.0452, 0.0665), (0.0460, 0.0700),
                 (0.0460, 0.0770), (0.0442, 0.0822), (0.0396, 0.0872), (0.0330, 0.0922),
                 (0.0250, 0.0962), (0.0160, 0.0987), (0.0100, 0.0997), (0.0100, 0.0035),
                 (0.0345, 0.0035)]
GASKET = [(0.0292, 0.0), (0.0349, 0.0), (0.0349, 0.0040), (0.0292, 0.0040)]
PF_SEAT = 0.0004             # the basket rim presses this far into the gasket
DROP_PF = 0.0020             # --drop-pf
OFFSET_PF = 0.0012           # --offset-pf
PF_HANDLE_AZ = -120.0        # handle bearing, degrees from +X: front-left, in profile to the camera
PF_HANDLE_DIP = 8.0
ZP = ZG + 0.1215             # lever pivot
LEVER_DOWN = 20.0            # lever at rest, below horizontal, toward the front
OFFSET_PIN = 0.0015          # --offset-pin

# --- Valves, knobs, wands ---------------------------------------------------
VALVE_X, VALVE_Z = 0.119, CT + 0.300
LOOSE_KNOB = 0.005           # --loose-knob

# --- Gauges, switch, lamp ---------------------------------------------------
GAUGE_X, GAUGE_Z = 0.036, CT + 0.340   # side by side above the group
GAUGE_RB = 0.0235            # bezel bore
GAUGE_NEEDLE_T = (0.42, 0.06)   # needle position along the 270 deg arc (left, right)
PROUD_GAUGE = 0.0045         # --proud-gauge
SWITCH_XZ = (-0.100, CT + 0.105)
LAMP_XZ = (0.100, CT + 0.105)

# --- Feet --------------------------------------------------------------------
FEET_XY = ((-0.115, -0.140), (0.115, -0.140), (-0.115, 0.165), (0.115, 0.165))
BUNCH_FEET_Y = (0.128, 0.175)            # --bunch-feet: all four under the back
FOOT_R = 0.0140
# Each foot sinks a little further into the counter, tucks a little further
# into the chassis and is turned a quarter facet from the last, so no two
# feet share a plane even when --bunch-feet packs them 47 mm apart. The pad's
# top is a steep chamfer: a near-flat one put two bunched pads' top rings in
# one plane.
FOOT_BITES = (0.00025, 0.00040, 0.00055, 0.00070)
FOOT_TUCKS = (0.0030, 0.0032, 0.0034, 0.0036)
FLOAT_FOOT = 0.003

# --- Props on the counter ---------------------------------------------------
KNOCK_XY = (0.245, -0.110)
KNOCK_BITE = 0.0003
TAMPER_XY = (-0.178, -0.325)
TAMPER_BITE = 0.00045
PITCHER_XY = (-0.248, -0.185)
PITCHER_YAW = 213.5
PITCHER_BITE = 0.00035

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.670, 0.655, 0.4755)
BASE_TRIS_MIN = 43000
BASE_TRIS_MAX = 44300
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 14
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 520
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
# stainless, chrome, bakelite, wood, ceramic, rubber, glass, dial, ink,
# needle, stone, paint, coffee, lamp
FACE_FLOORS = (4400, 6700, 870, 580, 5330, 1140, 580, 1510, 58, 32, 84, 24, 415, 106)
MAT_LABELS = ("stainless", "chrome", "bakelite", "wood", "ceramic", "rubber", "glass",
              "dial", "ink", "needle", "stone", "paint", "coffee", "lamp")

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
FEET_COUNT = 4
FOOT_SEAT = (0.0001, 0.0008)
# Lever: the pin's axis runs through each boss and the lever's hub.
PIN_OFFSET_MAX = 0.0003
PIN_TILT_MAX_DEG = 0.5
# Cups: every cup seated on its host (warmer tray or drip grate) by a band.
CUP_COUNT = 5
CUP_SEAT = (0.0001, 0.0009)
# Size: body width across the side panels, warmer-tray top above the counter.
BODY_W = 0.300
BODY_W_TOL = 0.004
BODY_H = 0.3907
BODY_H_TOL = 0.004
# Portafilter: coaxial with the group, rim pressed into the gasket by a band.
PF_OFFSET_MAX = 0.0003
PF_SEAT_BAND = (0.0001, 0.0008)
# Gauges: the glass sits back inside the bezel's lip by a band.
GAUGE_COUNT = 2
GAUGE_RECESS = (0.0015, 0.0050)
# Drip tray: inside the side panels by a margin, and tucked behind the panel.
TRAY_MARGIN_MIN = 0.010
TRAY_TUCK_MIN = 0.005
# Stance: mass centre this far inside the feet's support polygon.
STANCE_MARGIN = 0.060

HERO_YAW_DEG = 0.0
WALL_Y = 2.4

STEEL_IDX = 0
CHROME_IDX = 1
BAKELITE_IDX = 2
WOOD_IDX = 3
CERAMIC_IDX = 4
RUBBER_IDX = 5
GLASS_IDX = 6
DIAL_IDX = 7
INK_IDX = 8
NEEDLE_IDX = 9
STONE_IDX = 10
PAINT_IDX = 11
COFFEE_IDX = 12
LAMP_IDX = 13

# part tags (a face attribute): what each shell is, for the audits
P_COUNTER, P_FOOT, P_STEM, P_NUT, P_CORE, P_FRONT, P_BACK, P_SIDE = 1, 2, 3, 4, 5, 6, 7, 8
P_CUPTRAY, P_RAIL, P_POST, P_CUP, P_CUP_HANDLE, P_DRIP, P_GRATE, P_COFFEE = 9, 10, 11, 12, 13, 14, 15, 17
P_GROUP, P_GASKET, P_PF, P_EAR, P_SHANK, P_HANDLE, P_SPOUT, P_NECK = 18, 19, 20, 21, 22, 23, 24, 25
P_PIPE, P_CHIMNEY, P_LUGPOST, P_BOSS, P_PIN, P_HUB, P_ARM, P_BALL = 26, 27, 28, 29, 30, 31, 32, 33
P_VALVE, P_KNOB, P_KNOBCAP, P_STUB, P_JOINT, P_WAND, P_NOZZLE = 34, 35, 36, 37, 38, 39, 40
P_BEZEL, P_DIAL, P_NEEDLE, P_GHUB, P_GLASS, P_SWITCH, P_LAMP = 41, 42, 43, 44, 45, 46, 47
P_KNOCK, P_BAR, P_PUCK, P_TAMPER, P_PITCHER, P_PHANDLE = 48, 49, 50, 51, 52, 53
# the counter and what rests on it
PROP_PARTS = {P_COUNTER, P_CUP, P_CUP_HANDLE, P_COFFEE, P_KNOCK, P_BAR, P_PUCK, P_TAMPER,
              P_PITCHER, P_PHANDLE}
# densities, kg/m^3, per material; the chassis box is a frame round a
# boiler and air, so it is overridden
DENSITY = (7900.0, 8500.0, 1400.0, 700.0, 2300.0, 1200.0, 2500.0, 2700.0, 2700.0,
           2700.0, 2700.0, 7800.0, 1000.0, 1200.0)
PART_DENSITY = {P_CORE: 350.0}

Y_UP = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)))    # local Z -> +Y
Y_DOWN = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))  # local Z -> -Y
X_UP = Matrix(((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)))    # local Z -> +X


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

class Builder:
    """A bmesh plus the part tag written on every face it gains."""

    def __init__(self, bm):
        self.bm = bm
        self.tag = bm.faces.layers.int.new("part")

    def part(self, pid):
        for f in self.bm.faces:
            if f[self.tag] == 0:
                f[self.tag] = pid


def _mark(faces, mat_idx):
    for f in faces:
        f.material_index = mat_idx


def add_box(bm, lo, hi, mat_idx):
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = geo["verts"]
    lo, hi = Vector(lo), Vector(hi)
    c = (lo + hi) * 0.5
    s = hi - lo
    for v in verts:
        v.co = Vector((v.co.x * s.x, v.co.y * s.y, v.co.z * s.z)) + c
    _mark({f for v in verts for f in v.link_faces}, mat_idx)
    return list(verts)


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None,
              phase=0.0, solid=False, rmod=None, face_mat=None):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: the profile
    is an open polyline closed by n-gon caps at its two ends; otherwise it
    is a closed polygon revolved into a ring shell. ``rmod(i, j)`` scales
    the radius of profile point ``j`` on ring ``i``; ``face_mat(i, j)``
    picks the material of the face between rings i, i+1 and points j, j+1."""
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
            mi = face_mat(i, j) if face_mat else None
            f.material_index = mat_idx if mi is None else mi
    if solid:
        f0 = bm.faces.new([rings[i][0] for i in reversed(range(segs))])
        f1 = bm.faces.new([rings[i][n - 1] for i in range(segs)])
        f0.material_index = mat_idx
        f1.material_index = mat_idx
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


def add_flat_sweep(bm, pts, a, b, normal, sides, mat_idx, closed=False):
    """A bar of elliptical section swept along a path lying in the plane
    whose normal is ``normal``: half-width ``a`` in that plane, half
    thickness ``b`` across it."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    nv = Vector(normal).normalized()
    rings = []
    for i, p in enumerate(pts):
        if closed:
            t = (pts[(i + 1) % n] - pts[(i - 1) % n]).normalized()
        else:
            t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        perp = nv.cross(t).normalized()
        rings.append([
            bm.verts.new(p + perp * (a * math.cos(2.0 * math.pi * k / sides))
                         + nv * (b * math.sin(2.0 * math.pi * k / sides)))
            for k in range(sides)
        ])
    faces = []
    pairs = list(zip(rings, rings[1:]))
    if closed:
        pairs.append((rings[-1], rings[0]))
    for r0, r1 in pairs:
        for k in range(sides):
            m = (k + 1) % sides
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    if not closed:
        faces.append(bm.faces.new(tuple(reversed(rings[0]))))
        faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def add_prism(bm, outline, origin, u, v, w, w0, w1, mat_idx):
    """Convex 2D outline in the (u, v) frame at ``origin``, extruded along
    ``w`` from w0 to w1; n-gon caps (triangulated after the chamfer pass)."""
    o, u, v, w = Vector(origin), Vector(u), Vector(v), Vector(w)
    a = [bm.verts.new(o + u * p + v * q + w * w0) for p, q in outline]
    b = [bm.verts.new(o + u * p + v * q + w * w1) for p, q in outline]
    n = len(outline)
    faces = [bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n])) for i in range(n)]
    faces.append(bm.faces.new(tuple(reversed(a))))
    faces.append(bm.faces.new(tuple(b)))
    _mark(faces, mat_idx)
    return a + b


def loft(bm, rings_co, mat_idx, caps=True):
    rings = [[bm.verts.new(p) for p in ring] for ring in rings_co]
    n = len(rings[0])
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    if caps:
        faces.append(bm.faces.new(tuple(reversed(rings[0]))))
        faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for r in rings for v in r]


def add_sheet(bm, path, hs, t, solid, frame, mat_idx):
    """A sheet of thickness ``t`` whose mid-surface runs along a 2D ``path``
    (plan coordinates a, b) and up through the heights ``hs``. ``solid(i, j)``
    says whether the cell between path stations i, i+1 and heights j, j+1 is
    metal; open cells are slots, walled all round. One manifold shell, all
    quads. ``frame(a, b, h)`` maps a plan point and a height into the world."""
    n, m = len(path), len(hs)
    nrms = []
    segn = []
    for i in range(n - 1):
        (a0, b0), (a1, b1) = path[i], path[i + 1]
        ln = math.hypot(a1 - a0, b1 - b0)
        segn.append((-(b1 - b0) / ln, (a1 - a0) / ln))
    for i in range(n):
        ns = [segn[k] for k in (i - 1, i) if 0 <= k < n - 1]
        na = sum(q[0] for q in ns)
        nb = sum(q[1] for q in ns)
        ln = math.hypot(na, nb)
        na, nb = na / ln, nb / ln
        k = 0.5 * t / max(na * ns[0][0] + nb * ns[0][1], 0.3)
        nrms.append((na * k, nb * k))
    cache = {}

    def vert(i, j, s):
        key = (i, j, s)
        if key not in cache:
            a, b = path[i]
            da, db = nrms[i]
            cache[key] = bm.verts.new(frame(a + s * da, b + s * db, hs[j]))
        return cache[key]

    def is_solid(i, j):
        return 0 <= i < n - 1 and 0 <= j < m - 1 and solid(i, j)

    faces = []
    for i in range(n - 1):
        for j in range(m - 1):
            if not solid(i, j):
                continue
            faces.append(bm.faces.new((vert(i, j, 1), vert(i + 1, j, 1), vert(i + 1, j + 1, 1),
                                       vert(i, j + 1, 1))))
            faces.append(bm.faces.new((vert(i, j + 1, -1), vert(i + 1, j + 1, -1),
                                       vert(i + 1, j, -1), vert(i, j, -1))))
            if not is_solid(i - 1, j):
                faces.append(bm.faces.new((vert(i, j, 1), vert(i, j + 1, 1), vert(i, j + 1, -1),
                                           vert(i, j, -1))))
            if not is_solid(i + 1, j):
                faces.append(bm.faces.new((vert(i + 1, j, -1), vert(i + 1, j + 1, -1),
                                           vert(i + 1, j + 1, 1), vert(i + 1, j, 1))))
            if not is_solid(i, j - 1):
                faces.append(bm.faces.new((vert(i, j, -1), vert(i + 1, j, -1), vert(i + 1, j, 1),
                                           vert(i, j, 1))))
            if not is_solid(i, j + 1):
                faces.append(bm.faces.new((vert(i, j + 1, 1), vert(i + 1, j + 1, 1),
                                           vert(i + 1, j + 1, -1), vert(i, j + 1, -1))))
    _mark(faces, mat_idx)
    return list(cache.values())


def rrect(cx, cy, hx, hy, r, n=6):
    """Rounded rectangle, counter-clockwise, 4 * (n + 1) points."""
    out = []
    for qx, qy, a0 in ((1, -1, -0.5 * math.pi), (1, 1, 0.0), (-1, 1, 0.5 * math.pi),
                       (-1, -1, math.pi)):
        ccx, ccy = cx + qx * (hx - r), cy + qy * (hy - r)
        for k in range(n + 1):
            a = a0 + 0.5 * math.pi * k / n
            out.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return out


def add_pan(bm, cx, cy, hx, hy, r, z0, profile, mat_idx):
    """A pressed pan: rounded-rectangle rings lofted through (inset, height)
    profile stations, closed underneath and across its floor."""
    rings = []
    for d, dz in profile:
        rings.append([Vector((x, y, z0 + dz))
                      for x, y in rrect(cx, cy, hx - d, hy - d, max(r - d, 0.0015))])
    return loft(bm, rings, mat_idx)


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


def fillet(pts, rad, steps=6):
    """Round each interior corner of a 3D polyline with a quadratic arc."""
    pts = [Vector(p) for p in pts]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, p, c = pts[i - 1], pts[i], pts[i + 1]
        d0 = (p - a).normalized()
        d1 = (c - p).normalized()
        p0, p1 = p - d0 * rad, p + d1 * rad
        for k in range(steps + 1):
            t = k / steps
            out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * p + t * t * p1)
    out.append(pts[-1])
    return out


def catmull(pts, per=6):
    pts = [Vector(p) for p in pts]
    ext = [pts[0] * 2.0 - pts[1]] + pts + [pts[-1] * 2.0 - pts[-2]]
    out = []
    for i in range(1, len(pts)):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2.0 * p1) + (-p0 + p2) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                              + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t))
    out.append(pts[-1])
    return out


def pin_profile(x_neg, x_pos, shaft_r, head_r):
    """Solid lathe profile of a pin with dome heads whose undersides sit at
    x_neg / x_pos along its axis."""
    return [(head_r * 0.33, x_neg - 0.0026), (head_r * 0.74, x_neg - 0.0020),
            (head_r * 0.96, x_neg - 0.0009), (head_r, x_neg), (shaft_r, x_neg),
            (shaft_r, x_pos), (head_r, x_pos), (head_r * 0.96, x_pos + 0.0009),
            (head_r * 0.74, x_pos + 0.0020), (head_r * 0.33, x_pos + 0.0026)]


def along(d):
    """Rotation taking local Z onto direction d."""
    return Vector(d).normalized().to_track_quat("Z", "X").to_matrix()


def interp_r(prof, z):
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        if min(z0, z1) <= z <= max(z0, z1) and abs(z1 - z0) > 1e-12:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return prof[-1][0]


# --------------------------------------------------------------------------
# The machine
# --------------------------------------------------------------------------

def add_counter(bm, bevel_verts):
    # profile across the counter's depth, u = -y (the front is u1)
    u0, u1 = -COUNTER_Y[1], -COUNTER_Y[0]
    rb, rf, rt, rk = COUNTER_R
    corners = [((u0 + rb, rb), rb, math.pi, 1.5 * math.pi),
               ((u1 - rf, rf), rf, 1.5 * math.pi, 2.0 * math.pi),
               ((u1 - rt, CT - rt), rt, 0.0, 0.5 * math.pi),
               ((u0 + rk, CT - rk), rk, 0.5 * math.pi, math.pi)]
    prof = []
    for (cu, cz), r, a0, a1 in corners:
        steps = 6 if r > 0.006 else 3
        for s in range(steps + 1):
            a = a0 + (a1 - a0) * s / steps
            prof.append((cu + r * math.cos(a), cz + r * math.sin(a)))
    x0, x1 = COUNTER_X
    rings = [[Vector((x, -u, z)) for u, z in prof] for x in (x1, x0)]
    bevel_verts += loft(bm, rings, STONE_IDX)


def side_panel_path(hx, sign):
    xs = hx - 0.5 * PANEL_T
    rb = BEND_R
    pts = [(xs - RETURN, SIDE_YF)]
    for k in range(5):
        a = -0.5 * math.pi + 0.5 * math.pi * k / 4
        pts.append((xs - rb + rb * math.cos(a), SIDE_YF + rb + rb * math.sin(a)))
    for y in (VENT_Y[0][0], VENT_Y[0][1], VENT_Y[1][0], VENT_Y[1][1]):
        pts.append((xs, y))
    for k in range(5):
        a = 0.5 * math.pi * k / 4
        pts.append((xs - rb + rb * math.cos(a), SIDE_YB - rb + rb * math.sin(a)))
    pts.append((xs - RETURN, SIDE_YB))
    return [(sign * a, b) for a, b in pts]


def add_side_panel(bm, hx, sign):
    path = side_panel_path(hx, sign)
    z0, z1 = BODY_Z0 + 0.0005, BODY_TOP + 0.0075
    hs = [z0] + [VENT_Z0 + VENT_PITCH * k for k in range(2 * VENT_SLOTS)] + [z1]
    xs = hx - 0.5 * PANEL_T
    slot_rows = {1 + 2 * s for s in range(VENT_SLOTS)}

    def solid(i, j):
        (a0, b0), (a1, b1) = path[i], path[i + 1]
        if abs(abs(a0) - xs) > 1e-9 or abs(abs(a1) - xs) > 1e-9:
            return True
        mid = 0.5 * (b0 + b1)
        in_vent = any(y0 < mid < y1 for y0, y1 in VENT_Y)
        return not (in_vent and j in slot_rows)

    add_sheet(bm, path, hs, PANEL_T, solid, lambda a, b, h: Vector((a, b, h)), STEEL_IDX)


def add_grate(bm, shift):
    x0, x1 = -DRIP_HX + GRATE_INSET, DRIP_HX - GRATE_INSET
    y0, y1 = DRIP_Y[0] + GRATE_INSET, DRIP_Y[1] - GRATE_INSET
    span = N_SLOTS * SLOT_W + (N_SLOTS - 1) * BAR_W
    xs = [x0]
    x = -0.5 * span
    slot_segs = set()
    for k in range(N_SLOTS):
        xs.append(x)
        slot_segs.add(len(xs) - 1)
        x += SLOT_W
        xs.append(x)
        x += BAR_W
    xs.append(x1)
    path = [(xv, GRATE_Z) for xv in xs]
    hs = [y0, y0 + 0.012, y1 - 0.012, y1]

    def solid(i, j):
        return not (j == 1 and i in slot_segs)

    add_sheet(bm, path, hs, GRATE_T, solid, lambda a, b, h: Vector((a + shift, h, b)),
              STEEL_IDX)


def add_cup(bm, B, xy, host_z, bite, sr, sz, upturned, yaw, phase, coffee=False):
    """A demitasse (or, scaled, a cappuccino cup) with its handle, built
    upright about the origin and then set on its host: rim down on the
    warmer tray, foot down on the grate."""
    bm.verts.ensure_lookup_table()
    start = len(bm.verts)
    prof = [(r * sr, z * sz) for r, z in CUP_PROF]
    outer = [(r * sr, z * sz) for r, z in CUP_OUTER]
    add_lathe(bm, prof, 48, CERAMIC_IDX, solid=True, phase=phase)
    B.part(P_CUP)

    def rw(z):
        return interp_r(outer, z)

    hp = [(0.041, -0.0020), (0.0425, 0.0060), (0.0392, 0.0132), (0.0310, 0.0166),
          (0.0232, 0.0134), (0.0192, 0.0062), (0.0185, -0.0020)]
    pts = []
    for z, dr in hp:
        zz = z * sz
        pts.append(Vector((rw(zz) + dr * sr, 0.0, zz)))
    add_flat_sweep(bm, catmull(pts, per=4), 0.0020 * sr, 0.0031 * sr, (0.0, 1.0, 0.0), 8,
                   CERAMIC_IDX)
    B.part(P_CUP_HANDLE)
    if coffee:
        zt = 0.0360 * sz
        inner = [(r * sr, z * sz) for r, z in CUP_PROF[12:]]
        rc = interp_r(inner, zt) + 0.0005
        add_lathe(bm, [(rc, zt), (rc, zt - 0.0040)], 48, COFFEE_IDX, solid=True,
                  phase=phase + 0.5 * math.pi / 48)
        B.part(P_COFFEE)
    bm.verts.ensure_lookup_table()
    verts = list(bm.verts)[start:]
    m = Matrix.Rotation(math.radians(yaw), 3, "Z")
    if upturned:
        m = m @ Matrix.Rotation(math.pi, 3, "X")
        dz = host_z - bite + CUP_H * sz
    else:
        dz = host_z - bite
    off = Vector((xy[0], xy[1], dz))
    for v in verts:
        v.co = m @ v.co + off


def build_machine_mesh(name, bevel_offset, bevel_segments, flags=None):
    fl = dict(flags or {})
    hx = NARROW_HX if fl.get("narrow_body") else BODY_HX
    bm = bmesh.new()
    try:
        B = Builder(bm)
        bevel_verts = []
        chrome_bevel = []

        # --- counter
        add_counter(bm, bevel_verts)
        B.part(P_COUNTER)

        # --- adjustable feet: rubber pad, chrome stem, hex lock nut
        seg_f = 24
        for i, (fx, fy) in enumerate(FEET_XY):
            if fl.get("bunch_feet"):
                fy = BUNCH_FEET_Y[0] if fy < 0.0 else BUNCH_FEET_Y[1]
            lift = FLOAT_FOOT if (fl.get("float_foot") and i == 3) else 0.0
            zb = CT - FOOT_BITES[i] + lift
            ph = 0.25 * i * 2.0 * math.pi / seg_f
            add_lathe(bm, [(FOOT_R - 0.0015, zb), (FOOT_R, zb + 0.0015), (FOOT_R, zb + 0.0060),
                           (FOOT_R - 0.0020, zb + 0.0080), (0.0065, zb + 0.0095)], seg_f,
                      RUBBER_IDX, center=(fx, fy, 0.0), solid=True, phase=ph)
            B.part(P_FOOT)
            st = 0.00015 * i
            add_lathe(bm, [(0.0055, CT + 0.0050 + st), (0.0060, CT + 0.0060 + st),
                           (0.0060, BODY_Z0 + FOOT_TUCKS[i])], 16, CHROME_IDX,
                      center=(fx, fy, 0.0), solid=True, phase=ph)
            B.part(P_STEM)
            add_lathe(bm, [(0.0088, BODY_Z0 - 0.0048 + st), (0.0088, BODY_Z0 - 0.0018 + st)], 6,
                      CHROME_IDX, center=(fx, fy, 0.0), solid=True, phase=ph)
            B.part(P_NUT)

        # --- chassis, front and back panels, folded side panels
        ci = hx - CORE_IN
        bevel_verts += add_box(bm, (-ci, CORE_Y[0], BODY_Z0), (ci, CORE_Y[1], BODY_TOP), PAINT_IDX)
        B.part(P_CORE)
        fpx = hx - 0.004
        bevel_verts += add_box(bm, (-fpx, FP_Y[0], DRIP_TOP + 0.004),
                               (fpx, FP_Y[1], BODY_TOP + 0.0065), STEEL_IDX)
        B.part(P_FRONT)
        bevel_verts += add_box(bm, (-fpx, BP_Y[0], BODY_Z0 + 0.0010),
                               (fpx, BP_Y[1], BODY_TOP + 0.0055), STEEL_IDX)
        B.part(P_BACK)
        for sign in (1.0, -1.0):
            add_side_panel(bm, hx, sign)
            B.part(P_SIDE)

        # --- warmer tray, rail and posts
        thx = ci - 0.0015
        ty0, ty1 = CORE_Y[0] + 0.0045, CORE_Y[1] - 0.0045
        add_pan(bm, 0.0, 0.5 * (ty0 + ty1), thx, 0.5 * (ty1 - ty0), 0.012, TRAY_Z0,
                TRAY_PROFILE, STEEL_IDX)
        B.part(P_CUPTRAY)
        rx = hx - 0.028
        zl = WARM_FLOOR - LEG_BITE
        rail = [(-rx, RAIL_Y[0], zl), (-rx, RAIL_Y[0], RAIL_Z), (-rx, RAIL_Y[1], RAIL_Z),
                (rx, RAIL_Y[1], RAIL_Z), (rx, RAIL_Y[0], RAIL_Z), (rx, RAIL_Y[0], zl)]
        add_tube(bm, fillet(rail, 0.014, 6), RAIL_R, 12, CHROME_IDX)
        B.part(P_RAIL)
        for k, px in enumerate((-POST_X, POST_X)):
            add_tube(bm, [(px, RAIL_Y[1], zl - 0.0002 * k), (px, RAIL_Y[1], RAIL_Z)], 0.0032, 10,
                     CHROME_IDX, phase=0.1 * k)
            B.part(P_POST)

        # --- cups upturned on the warmer tray
        for k, (cx, cy, sr, sz, yaw, bite) in enumerate(WARM_CUPS):
            if fl.get("sink_cup") and k == 2:
                bite += SINK_CUP
            add_cup(bm, B, (cx, cy), WARM_FLOOR, bite, sr, sz, True, yaw,
                    phase=0.37 * k * 2.0 * math.pi / 48)

        # --- drip tray and grate, shot cup of espresso on the grate
        tshift = SHIFT_TRAY if fl.get("shift_tray") else 0.0
        add_pan(bm, tshift, 0.5 * (DRIP_Y[0] + DRIP_Y[1]), DRIP_HX, 0.5 * (DRIP_Y[1] - DRIP_Y[0]),
                DRIP_R, DRIP_Z0, DRIP_PROFILE, STEEL_IDX)
        B.part(P_DRIP)
        add_grate(bm, tshift)
        B.part(P_GRATE)
        add_cup(bm, B, (0.0, GY), GRATE_TOP, SHOT_BITE, 1.0, 1.0, False, -35.0,
                phase=0.19 * 2.0 * math.pi / 48, coffee=True)

        # --- E61 group: neck, body, gasket, thermosiphon pipe, chimney
        gc = Vector((0.0, GY, ZG))
        add_lathe(bm, [(0.0200, -0.0025), (0.0300, -0.0025), (0.0300, 0.0035), (0.0270, 0.0065),
                       (0.0228, 0.0110), (0.0228, 0.0590)], 40, CHROME_IDX,
                  center=(0.0, FP_Y[0], ZG + 0.034), rot=Y_DOWN, solid=True)
        B.part(P_NECK)
        add_lathe(bm, GROUP_PROFILE, 64, CHROME_IDX, center=gc)
        B.part(P_GROUP)
        add_lathe(bm, GASKET, 64, RUBBER_IDX, center=gc, phase=math.pi / 64)
        B.part(P_GASKET)
        add_tube(bm, [(0.0, GY + 0.030, ZG + 0.0860), (0.0, FP_Y[0] + 0.003, ZG + 0.0860)],
                 0.0075, 16, CHROME_IDX)
        add_lathe(bm, [(0.0082, -0.0020), (0.0118, -0.0020), (0.0118, 0.0028), (0.0082, 0.0048)],
                  24, CHROME_IDX, center=(0.0, FP_Y[0], ZG + 0.0860), rot=Y_DOWN, solid=True)
        B.part(P_PIPE)
        add_lathe(bm, [(0.0165, 0.0950), (0.0165, 0.1080), (0.0152, 0.1118), (0.0060, 0.1132)],
                  40, CHROME_IDX, center=gc, solid=True, phase=math.pi / 40)
        B.part(P_CHIMNEY)

        # --- lever: two lug posts with bosses, a pin, the lever's hub, arm, ball
        # the two posts are staggered 0.8 mm in y and 0.3 mm in z, so their
        # mirrored chamfers do not share a plane
        for lo, hi in (((0.0082, GY - 0.0045, ZG + 0.1100), (0.0113, GY + 0.0045, ZP)),
                       ((-0.0113, GY - 0.0037, ZG + 0.1097), (-0.0082, GY + 0.0053, ZP - 0.0003))):
            chrome_bevel += add_box(bm, lo, hi, CHROME_IDX)
            B.part(P_LUGPOST)
        for s in (1.0, -1.0):
            w0, w1 = (0.0080, 0.0115) if s > 0 else (-0.0115, -0.0080)
            add_lathe(bm, [(0.0055, w0), (0.0062, w0 + 0.0007), (0.0062, w1 - 0.0007), (0.0055, w1)],
                      24, CHROME_IDX, center=(0.0, GY, ZP), rot=X_UP, solid=True,
                      phase=0.0 if s > 0 else math.pi / 24)
            B.part(P_BOSS)
        pc = Vector((0.0, GY, ZP + (OFFSET_PIN if fl.get("offset_pin") else 0.0)))
        add_lathe(bm, pin_profile(-0.0112, 0.0112, 0.0021, 0.0036), 16, CHROME_IDX, center=pc,
                  rot=X_UP, solid=True)
        B.part(P_PIN)
        add_lathe(bm, [(0.0050, -0.0068), (0.0058, -0.0062), (0.0058, 0.0062), (0.0050, 0.0068)],
                  20, CHROME_IDX, center=(0.0, GY, ZP), rot=X_UP, solid=True, phase=math.pi / 20)
        B.part(P_HUB)
        dl = Vector((0.0, -math.cos(math.radians(LEVER_DOWN)), -math.sin(math.radians(LEVER_DOWN))))
        hub = Vector((0.0, GY, ZP))
        add_tube(bm, [hub, hub + dl * 0.064], 0.0032, 12, CHROME_IDX)
        B.part(P_ARM)
        add_lathe(bm, [(0.0035, -0.0105), (0.0072, -0.0090), (0.0099, -0.0052), (0.0108, 0.0),
                       (0.0099, 0.0052), (0.0072, 0.0090), (0.0032, 0.0104)], 24, BAKELITE_IDX,
                  center=hub + dl * 0.070, rot=along(dl), solid=True)
        B.part(P_BALL)

        # --- portafilter: body, ears, shank, walnut handle, spout block, spouts
        pfc = gc + Vector((OFFSET_PF if fl.get("offset_pf") else 0.0, 0.0,
                           -DROP_PF if fl.get("drop_pf") else 0.0))
        s_ = PF_SEAT
        add_lathe(bm, [(0.0282, s_), (0.0350, s_), (0.0350, -0.0128), (0.0382, -0.0142),
                       (0.0388, -0.0172), (0.0366, -0.0240), (0.0305, -0.0318), (0.0205, -0.0368),
                       (0.0105, -0.0386)], 64, CHROME_IDX, center=pfc, solid=True,
                  phase=0.5 * math.pi / 64)
        B.part(P_PF)
        haz = math.radians(PF_HANDLE_AZ)
        for s in (1.0, -1.0):
            ea = haz + s * 0.5 * math.pi
            u = Vector((math.cos(ea), math.sin(ea), 0.0))
            w = Vector((-math.sin(ea), math.cos(ea), 0.0))
            outline = [(0.0340, -0.0166), (0.0452, -0.0166), (0.0458, -0.0160), (0.0458, -0.0151),
                       (0.0452, -0.0146), (0.0340, -0.0146)]
            chrome_bevel += add_prism(bm, outline, pfc, u, Vector((0.0, 0.0, 1.0)), w, -0.0060,
                                      0.0060 - 0.0002 * (s > 0), CHROME_IDX)
            B.part(P_EAR)
        dip = math.radians(PF_HANDLE_DIP)
        dh = Vector((math.cos(haz) * math.cos(dip), math.sin(haz) * math.cos(dip), -math.sin(dip)))
        root = pfc + Vector((0.0, 0.0, -0.0200))
        add_tube(bm, [root + dh * 0.020, root + dh * 0.078], 0.0058, 16, CHROME_IDX)
        B.part(P_SHANK)
        add_lathe(bm, [(0.0050, 0.0000), (0.0088, 0.0015), (0.0102, 0.0080), (0.0110, 0.0350),
                       (0.0128, 0.0700), (0.0138, 0.0860), (0.0133, 0.0935), (0.0116, 0.0990),
                       (0.0086, 0.1028), (0.0048, 0.1047), (0.0020, 0.1052)], 24, WOOD_IDX, center=root + dh * 0.070, rot=along(dh),
                  solid=True)
        B.part(P_HANDLE)
        add_lathe(bm, [(0.0115, -0.0376), (0.0115, -0.0425), (0.0098, -0.0455), (0.0070, -0.0470)],
                  32, CHROME_IDX, center=pfc, solid=True)
        for s in (1.0, -1.0):
            add_tube(bm, [pfc + Vector((s * 0.0030, 0.0, -0.0440)),
                          pfc + Vector((s * 0.0120, 0.0, -0.0575))], 0.0030, 10, CHROME_IDX,
                     phase=0.0 if s > 0 else 0.2)
        B.part(P_SPOUT)

        # --- steam (right) and hot-water (left) valves, knobs, ball joints, wands
        for s in (1.0, -1.0):
            vc = Vector((s * VALVE_X, FP_Y[0], VALVE_Z))
            add_lathe(bm, [(0.0120, -0.0020), (0.0165, -0.0020), (0.0165, 0.0030), (0.0138, 0.0052),
                           (0.0122, 0.0078), (0.0122, 0.0300), (0.0100, 0.0312)], 32, CHROME_IDX,
                      center=vc, rot=Y_DOWN, solid=True, phase=0.0 if s > 0 else math.pi / 32)
            B.part(P_VALVE)
            kc = vc + Vector((0.0, -(LOOSE_KNOB if (fl.get("loose_knob") and s > 0) else 0.0), 0.0))

            def flute(i, j):
                return 0.93 if (j in (3, 4) and i % 2) else 1.0

            add_lathe(bm, [(0.0085, 0.0290), (0.0140, 0.0293), (0.0162, 0.0308), (0.0172, 0.0350),
                           (0.0172, 0.0470), (0.0162, 0.0512), (0.0126, 0.0540), (0.0068, 0.0548)],
                      36, BAKELITE_IDX, center=kc, rot=Y_DOWN, solid=True, rmod=flute)
            B.part(P_KNOB)
            add_lathe(bm, [(0.0058, 0.0530), (0.0060, 0.0552), (0.0046, 0.0560), (0.0020, 0.0562)],
                      24, CHROME_IDX, center=kc, rot=Y_DOWN, solid=True)
            B.part(P_KNOBCAP)
            jx, jy = s * VALVE_X, FP_Y[0] - 0.019
            add_lathe(bm, [(0.0058, VALVE_Z - 0.0060), (0.0058, VALVE_Z - 0.0205),
                           (0.0050, VALVE_Z - 0.0215)], 16, CHROME_IDX, center=(jx, jy, 0.0),
                      solid=True, phase=0.0 if s > 0 else math.pi / 16)
            B.part(P_STUB)
            jc = Vector((jx, jy, VALVE_Z - 0.026))
            add_lathe(bm, [(0.0030, -0.0076), (0.0058, -0.0055), (0.0078, 0.0), (0.0058, 0.0055),
                           (0.0030, 0.0076)], 20, CHROME_IDX, center=jc, solid=True,
                      phase=0.0 if s > 0 else math.pi / 20)
            B.part(P_JOINT)
            if s > 0:
                dw = Vector((0.22, -0.10, -1.0)).normalized()
                d2 = Vector((0.25, -0.55, -1.0)).normalized()
                l1, l2, wr = 0.150, 0.028, 0.0042
            else:
                dw = Vector((-0.12, -0.14, -1.0)).normalized()
                d2 = Vector((-0.10, -0.40, -1.0)).normalized()
                l1, l2, wr = 0.090, 0.016, 0.0040
            p1 = jc + dw * l1
            p2 = p1 + d2 * l2
            add_tube(bm, [jc, jc + dw * (0.5 * l1), p1 - dw * 0.006, p1 + d2 * 0.006, p2], wr, 12,
                     CHROME_IDX)
            B.part(P_WAND)
            add_lathe(bm, [(0.0035, -0.0040), (0.0052, -0.0010), (0.0052, 0.0080), (0.0040, 0.0120),
                           (0.0016, 0.0130)], 16, CHROME_IDX, center=p2, rot=along(d2), solid=True)
            B.part(P_NOZZLE)

        # --- twin pressure gauges: bezel, printed dial, needle and hub, glass
        seg_g = 96
        for gi, s in enumerate((-1.0, 1.0)):
            # the right gauge sits 0.4 mm prouder: side by side, the two
            # dials' and bezels' faces would otherwise share planes
            gcen = Vector((s * GAUGE_X, FP_Y[0] - 0.0004 * gi, GAUGE_Z))
            add_lathe(bm, [(GAUGE_RB, -0.0015), (0.0262, -0.0015), (0.0262, 0.0062), (0.0272, 0.0082),
                           (0.0276, 0.0104), (0.0269, 0.0121), (0.0252, 0.0129), (0.0232, 0.0124),
                           (0.0226, 0.0113), (0.0229, 0.0103), (GAUGE_RB, 0.0100)], 64, CHROME_IDX,
                      center=gcen, rot=Y_DOWN, phase=0.0 if s > 0 else math.pi / 64)
            B.part(P_BEZEL)
            fc = gcen + Vector((0.0, -(PROUD_GAUGE if fl.get("proud_gauge") else 0.0), 0.0))
            # ticks every 3 segments along a 270 deg arc from lower left,
            # clockwise; every fourth tick is long; the last sixth is red
            ticks = {}
            for k in range(25):
                a = 225.0 - 270.0 * k / 24.0
                i = int(round((a % 360.0) / (360.0 / seg_g) - 0.5)) % seg_g
                ticks[i] = (k % 4 == 0)
            red = set()
            for k in range(20 * 3, 24 * 3 + 1):
                a = 225.0 - 270.0 * k / 72.0
                red.add(int(round((a % 360.0) / (360.0 / seg_g) - 0.5)) % seg_g)

            def dial_mat(i, j, ticks=ticks, red=red):
                if j == 1 and ticks.get(i):
                    return INK_IDX
                if j == 2 and i in ticks:
                    return INK_IDX
                if j == 3 and i in red:
                    return NEEDLE_IDX
                return DIAL_IDX

            rd = GAUGE_RB + 0.0004
            add_lathe(bm, [(0.0030, 0.0040), (0.0150, 0.0040), (0.0172, 0.0040), (0.0200, 0.0040),
                           (0.0214, 0.0040), (rd, 0.0040), (rd, 0.0020), (0.0030, 0.0020)], seg_g,
                      DIAL_IDX, center=fc, rot=Y_DOWN, solid=True, face_mat=dial_mat)
            B.part(P_DIAL)
            add_lathe(bm, [(0.0022, 0.0034), (0.0024, 0.0058), (0.0012, 0.0062)], 16, BAKELITE_IDX,
                      center=fc, rot=Y_DOWN, solid=True)
            B.part(P_GHUB)
            th = math.radians(225.0 - 270.0 * GAUGE_NEEDLE_T[gi])
            nu = (math.cos(th), math.sin(th))
            nv = (-nu[1], nu[0])
            outline = [(nu[0] * 0.0190, nu[1] * 0.0190),
                       (nu[0] * 0.004 + nv[0] * 0.0008, nu[1] * 0.004 + nv[1] * 0.0008),
                       (-nu[0] * 0.0045 + nv[0] * 0.0006, -nu[1] * 0.0045 + nv[1] * 0.0006),
                       (-nu[0] * 0.0045 - nv[0] * 0.0006, -nu[1] * 0.0045 - nv[1] * 0.0006),
                       (nu[0] * 0.004 - nv[0] * 0.0008, nu[1] * 0.004 - nv[1] * 0.0008)]
            add_prism(bm, outline, fc, Vector((1.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)),
                      Vector((0.0, -1.0, 0.0)), 0.0047, 0.0053, NEEDLE_IDX)
            B.part(P_NEEDLE)
            rg = GAUGE_RB + 0.0007   # not the dial's radius: the rims would share planes
            add_lathe(bm, [(rg, 0.0068), (rg, 0.0086), (0.0160, 0.0092), (0.0060, 0.0095)], 64,
                      GLASS_IDX, center=fc, rot=Y_DOWN, solid=True, phase=math.pi / 64)
            B.part(P_GLASS)

        # --- power toggle and pilot lamp
        sc = Vector((SWITCH_XZ[0], FP_Y[0], SWITCH_XZ[1]))
        add_lathe(bm, [(0.0074, -0.0015), (0.0074, 0.0040)], 6, CHROME_IDX, center=sc, rot=Y_DOWN,
                  solid=True)
        add_lathe(bm, [(0.0042, 0.0030), (0.0042, 0.0070), (0.0030, 0.0078)], 16, CHROME_IDX,
                  center=sc, rot=Y_DOWN, solid=True)
        add_tube(bm, [sc + Vector((0.0, -0.0060, 0.0)), sc + Vector((0.0, -0.0200, -0.0070))],
                 0.0019, 10, CHROME_IDX)
        B.part(P_SWITCH)
        lc = Vector((LAMP_XZ[0], FP_Y[0], LAMP_XZ[1]))
        add_lathe(bm, [(0.0050, -0.0015), (0.0085, -0.0015), (0.0085, 0.0030), (0.0070, 0.0042),
                       (0.0050, 0.0042)], 24, CHROME_IDX, center=lc, rot=Y_DOWN, solid=True)
        add_lathe(bm, [(0.0054, 0.0036), (0.0054, 0.0050), (0.0042, 0.0068), (0.0020, 0.0076)], 24,
                  LAMP_IDX, center=lc, rot=Y_DOWN, solid=True, phase=math.pi / 24)
        B.part(P_LAMP)

        # --- props: knock box with pucks, tamper, milk pitcher
        # a stainless bin on a rubber base ring, a rubber-sleeved bar across its rim
        kc = Vector((KNOCK_XY[0], KNOCK_XY[1], CT - KNOCK_BITE))
        add_lathe(bm, [(0.0560, 0.0000), (0.0622, 0.0000), (0.0636, 0.0012), (0.0636, 0.0110),
                       (0.0620, 0.0122), (0.0560, 0.0122)], 64, RUBBER_IDX, center=kc,
                  phase=math.pi / 64)
        add_lathe(bm, [(0.0500, 0.0075), (0.0585, 0.0060), (0.0604, 0.0100), (0.0612, 0.0450),
                       (0.0604, 0.0800), (0.0588, 0.0850), (0.0552, 0.0850), (0.0536, 0.0805),
                       (0.0544, 0.0450), (0.0536, 0.0240), (0.0506, 0.0200), (0.0400, 0.0200)],
                  64, STEEL_IDX, center=kc, solid=True)
        B.part(P_KNOCK)
        ba = math.radians(30.0)
        bd = Vector((math.cos(ba), math.sin(ba), 0.0))
        bz = kc + Vector((0.0, 0.0, 0.0820))
        add_tube(bm, [bz - bd * 0.0575, bz + bd * 0.0575], 0.0075, 16, RUBBER_IDX)
        B.part(P_BAR)
        add_lathe(bm, [(0.0288, 0.0200 - 0.0003), (0.0292, 0.0215), (0.0292, 0.0305),
                       (0.0280, 0.0317)], 32, COFFEE_IDX, center=kc + Vector((-0.012, 0.010, 0.0)),
                  solid=True)
        add_lathe(bm, [(0.0280, 0.0317 - 0.0004), (0.0286, 0.0330), (0.0286, 0.0418),
                       (0.0274, 0.0429)], 32, COFFEE_IDX, center=kc + Vector((-0.004, 0.016, 0.0)),
                  solid=True, phase=0.4)
        B.part(P_PUCK)

        tc = Vector((TAMPER_XY[0], TAMPER_XY[1], CT - TAMPER_BITE))
        add_lathe(bm, [(0.0280, 0.0000), (0.0290, 0.0010), (0.0290, 0.0130), (0.0275, 0.0145),
                       (0.0140, 0.0170), (0.0100, 0.0200), (0.0095, 0.0260)], 48, STEEL_IDX,
                  center=tc, solid=True)
        add_lathe(bm, [(0.0092, 0.0240), (0.0125, 0.0262), (0.0150, 0.0330), (0.0140, 0.0420),
                       (0.0165, 0.0560), (0.0200, 0.0700), (0.0205, 0.0780), (0.0180, 0.0860),
                       (0.0120, 0.0910), (0.0040, 0.0930)], 32, WOOD_IDX, center=tc, solid=True,
                  phase=math.pi / 32)
        B.part(P_TAMPER)

        pprof = [(0.0330, 0.0010), (0.0345, 0.0000), (0.0360, 0.0015), (0.0368, 0.0200),
                 (0.0360, 0.0450), (0.0335, 0.0700), (0.0315, 0.0880), (0.0318, 0.0960),
                 (0.0322, 0.0985), (0.0312, 0.0990), (0.0306, 0.0975), (0.0303, 0.0880),
                 (0.0322, 0.0700), (0.0347, 0.0450), (0.0355, 0.0200), (0.0345, 0.0035),
                 (0.0300, 0.0024)]
        psegs = 64

        def spout(i, j):
            z = pprof[j][1]
            if z < 0.070:
                return 1.0
            a = 2.0 * math.pi * i / psegs
            d = abs(math.atan2(math.sin(a), math.cos(a)))
            if d >= 0.62:
                return 1.0
            h = min((z - 0.070) / 0.0285, 1.0)
            return 1.0 + 0.30 * (1.0 - (d / 0.62) ** 2) ** 2 * h ** 1.5

        pyaw = Matrix.Rotation(math.radians(PITCHER_YAW), 3, "Z")
        pc2 = Vector((PITCHER_XY[0], PITCHER_XY[1], CT - PITCHER_BITE))
        add_lathe(bm, pprof, psegs, STEEL_IDX, center=pc2, rot=pyaw, solid=True, rmod=spout)
        B.part(P_PITCHER)
        hp = [(0.0311, 0.0830), (0.0420, 0.0850), (0.0560, 0.0800), (0.0630, 0.0650),
              (0.0610, 0.0480), (0.0520, 0.0340), (0.0420, 0.0270), (0.0360, 0.0240)]
        hpts = [pc2 + pyaw @ Vector((-r, 0.0, z)) for r, z in hp]
        add_flat_sweep(bm, catmull(hpts, per=4), 0.0030, 0.0050, pyaw @ Vector((0.0, 1.0, 0.0)),
                       8, STEEL_IDX)
        B.part(P_PHANDLE)

        if bevel_offset > 0.0:
            # Chamfer the counter's cut ends, the chassis and panel boxes and
            # the chrome tabs, one pass per material with material= set, over
            # sorted edges (a set of BMEdges iterates in memory order).
            for verts, mat_idx, off in ((bevel_verts, STONE_IDX, 2.5 * bevel_offset),
                                        (bevel_verts, PAINT_IDX, 2.0 * bevel_offset),
                                        (bevel_verts, STEEL_IDX, 1.2 * bevel_offset),
                                        (chrome_bevel, CHROME_IDX, 0.5 * bevel_offset)):
                bm.edges.index_update()
                edges = sorted(
                    {e for v in verts if v.is_valid for e in v.link_edges
                     if len(e.link_faces) == 2
                     and all(f.material_index == mat_idx for f in e.link_faces)
                     and e.calc_face_angle() > math.radians(60.0)},
                    key=lambda e: e.index,
                )
                if edges:
                    bmesh.ops.bevel(bm, geom=edges, offset=off, segments=bevel_segments,
                                    profile=0.5, affect="EDGES", clamp_overlap=True,
                                    material=mat_idx)

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
        bsdf.inputs["Coat Roughness"].default_value = 0.08
    if roughness_var > 0.0 or mottle > 0.0:
        coord = nt.nodes.new("ShaderNodeTexCoord")
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = noise_scale
        noise.inputs["Detail"].default_value = 6.0
        if stretch:
            # brushed: the noise is squeezed along one axis into fine streaks
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


def metal(name, color, roughness, env, stops, interp="EASE", roughness_var=0.04,
          noise_scale=40.0, stretch=None):
    """Polished metal with a studio carried in the material. A metal on a
    dark stage mirrors the dark stage and reads as grey plastic (the stand
    mixer's bowl did). Here the world-space reflection vector looks up a
    soft studio: a bright band of walls and softboxes around the horizon,
    a dim ceiling, the floor dark only straight down, and the left side
    (the key's side) brighter than the right. It is added as emission, so
    chrome and stainless read as metal in the hero and on the asset
    sheet's neutral stage alike. A vertical panel seen from above mirrors
    what lies just below the horizon, which is why the band reaches down
    to it; a ramp bright only above the horizon left the panels black."""
    mat = principled(name, color, 1.0, roughness, roughness_var=roughness_var,
                     noise_scale=noise_scale, stretch=stretch)
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
    cr.interpolation = interp
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


def stone_material():
    """Honed limestone: isotropic object-space mottling in two octaves, fine
    dark fossil speckle, and the speckle again in the roughness and a faint
    bump (the stand mixer's counter, warmer and a shade darker)."""
    mat = bpy.data.materials.new("CounterStone")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = 0.0
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mott = nt.nodes.new("ShaderNodeTexNoise")
    mott.inputs["Scale"].default_value = 7.0
    mott.inputs["Detail"].default_value = 8.0
    mott.inputs["Roughness"].default_value = 0.62
    nt.links.new(coord.outputs["Object"], mott.inputs["Vector"])
    base = nt.nodes.new("ShaderNodeValToRGB")
    base.color_ramp.elements[0].position = 0.34
    base.color_ramp.elements[0].color = (0.115, 0.104, 0.088, 1.0)
    base.color_ramp.elements[1].position = 0.70
    base.color_ramp.elements[1].color = (0.180, 0.163, 0.140, 1.0)
    nt.links.new(mott.outputs["Fac"], base.inputs["Fac"])
    dots = nt.nodes.new("ShaderNodeTexVoronoi")
    dots.inputs["Scale"].default_value = 140.0
    nt.links.new(coord.outputs["Object"], dots.inputs["Vector"])
    dramp = nt.nodes.new("ShaderNodeValToRGB")
    dramp.color_ramp.elements[0].position = 0.0
    dramp.color_ramp.elements[0].color = (0.55, 0.55, 0.55, 1.0)
    dramp.color_ramp.elements[1].position = 0.12
    dramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(dots.outputs["Distance"], dramp.inputs["Fac"])
    mult = nt.nodes.new("ShaderNodeVectorMath")
    mult.operation = "MULTIPLY"
    nt.links.new(base.outputs["Color"], mult.inputs[0])
    nt.links.new(dramp.outputs["Color"], mult.inputs[1])
    nt.links.new(mult.outputs["Vector"], bsdf.inputs["Base Color"])
    speck = nt.nodes.new("ShaderNodeTexNoise")
    speck.inputs["Scale"].default_value = 260.0
    speck.inputs["Detail"].default_value = 2.0
    nt.links.new(coord.outputs["Object"], speck.inputs["Vector"])
    rr = nt.nodes.new("ShaderNodeValToRGB")
    rr.color_ramp.elements[0].position = 0.35
    rr.color_ramp.elements[0].color = (0.42, 0.42, 0.42, 1.0)
    rr.color_ramp.elements[1].position = 0.70
    rr.color_ramp.elements[1].color = (0.62, 0.62, 0.62, 1.0)
    nt.links.new(speck.outputs["Fac"], rr.inputs["Fac"])
    nt.links.new(rr.outputs["Color"], bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    bump.inputs["Distance"].default_value = 0.0005
    nt.links.new(speck.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def glass_material():
    mat = principled("GaugeGlass", (0.92, 0.94, 0.95, 1.0), 0.0, 0.03)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Alpha"].default_value = 0.14
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(mat, attr, val)
            break
        except (AttributeError, TypeError):
            continue
    return mat


def lamp_material():
    mat = principled("PilotLamp", (0.95, 0.42, 0.08, 1.0), 0.0, 0.2)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.45, 0.10, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 4.0
    return mat


def machine_materials():
    """Shared by the check and the render, in slot order."""
    # stops are (0.5 + 0.5 * reflection z, brightness): steel carries a soft
    # gradient down a panel; chrome a narrow bright horizon over a dark
    # floor, a dark gap, and a softbox above
    steel = metal("BrushedStainless", (0.72, 0.72, 0.74, 1.0), 0.28, 0.21,
                  [(0.0, 0.03), (0.18, 0.05), (0.275, 0.16), (0.375, 0.52), (0.475, 1.0),
                   (0.60, 0.36), (0.80, 0.22), (1.0, 0.18)],
                  roughness_var=0.06, noise_scale=9.0, stretch=(1.0, 1.0, 140.0))
    chrome = metal("Chrome", (0.92, 0.92, 0.94, 1.0), 0.10, 0.95,
                   [(0.0, 0.01), (0.30, 0.02), (0.38, 0.90), (0.47, 1.0), (0.53, 0.06),
                    (0.66, 0.08), (0.74, 0.75), (0.88, 0.60), (1.0, 0.20)], "LINEAR",
                   roughness_var=0.03,
                   noise_scale=70.0)
    bakelite = principled("Bakelite", (0.014, 0.012, 0.011, 1.0), 0.0, 0.30,
                          roughness_var=0.06, noise_scale=90.0, coat=0.35)
    wood = principled("Walnut", (0.215, 0.100, 0.046, 1.0), 0.0, 0.42, roughness_var=0.08,
                      mottle=0.30, noise_scale=55.0, coat=0.25, stretch=(1.0, 1.0, 12.0))
    ceramic = principled("Porcelain", (0.70, 0.68, 0.645, 1.0), 0.0, 0.14, roughness_var=0.04,
                         noise_scale=40.0, coat=0.45)
    rubber = principled("Rubber", (0.022, 0.022, 0.024, 1.0), 0.0, 0.66, roughness_var=0.08,
                        noise_scale=80.0)
    glass = glass_material()
    dial = principled("DialFace", (0.84, 0.83, 0.78, 1.0), 0.0, 0.42)
    ink = principled("DialInk", (0.015, 0.015, 0.018, 1.0), 0.0, 0.50)
    needle = principled("NeedleRed", (0.56, 0.035, 0.025, 1.0), 0.0, 0.34)
    stone = stone_material()
    paint = principled("ChassisPaint", (0.020, 0.020, 0.022, 1.0), 0.0, 0.46,
                       roughness_var=0.06, noise_scale=60.0)
    coffee = principled("Crema", (0.300, 0.155, 0.065, 1.0), 0.0, 0.38, roughness_var=0.08,
                        mottle=0.35, noise_scale=140.0)
    lamp = lamp_material()
    return (steel, chrome, bakelite, wood, ceramic, rubber, glass, dial, ink, needle, stone,
            paint, coffee, lamp)


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


class Shell:
    def __init__(self, me, idx, verts, polys, tags):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.mean = sum(pts, Vector()) / len(pts)
        mats, parts = {}, {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
            t = tags[p.index]
            if t:
                parts[t] = parts.get(t, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        self.part = max(parts, key=parts.get) if parts else 0
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)


def pca_axis(pts, largest=True):
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    _w, vecs = np.linalg.eigh(q.T @ q)
    axis = vecs[:, -1] if largest else vecs[:, 0]
    return c, axis


def classify(me):
    groups = shells(me)
    owner = [0] * len(me.vertices)
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(p)
    attr = me.attributes.get("part")
    tags = [0] * len(me.polygons)
    if attr is not None:
        attr.data.foreach_get("value", tags)
    parts = [Shell(me, i, g, polys[i], tags) for i, g in enumerate(groups)]
    by = {}
    for s in parts:
        by.setdefault(s.part, []).append(s)
    return {"all": parts, "groups": groups, "by": by}


def one(cls, pid):
    got = cls["by"].get(pid, [])
    return got[0] if len(got) == 1 else None


def feet_audit(cls):
    counter = one(cls, P_COUNTER)
    feet = cls["by"].get(P_FOOT, [])
    if counter is None:
        return None
    top = counter.hi.z
    return {"count": len(feet), "top": top, "seats": [top - f.lo.z for f in feet]}


def pin_audit(cls):
    """The lever pin's axis against each boss's and the hub's own axis."""
    pin = one(cls, P_PIN)
    joined = cls["by"].get(P_BOSS, []) + cls["by"].get(P_HUB, [])
    if pin is None:
        return None
    c, axis = pca_axis(pin.pts)
    tilt = math.degrees(math.acos(min(1.0, abs(float(axis[0])))))
    worst, not_through = 0.0, 0
    for k in joined:
        t = (k.mean.x - c[0]) / axis[0]
        py, pz = c[1] + axis[1] * t, c[2] + axis[2] * t
        worst = max(worst, math.hypot(k.mean.y - py, k.mean.z - pz))
        if k.lo.x < pin.lo.x - 1e-6 or k.hi.x > pin.hi.x + 1e-6:
            not_through += 1
    return {"bosses": len(cls["by"].get(P_BOSS, [])), "hubs": len(cls["by"].get(P_HUB, [])),
            "offset": worst, "tilt": tilt, "not_through": not_through}


def cups_audit(cls):
    """Every cup's seat on its host, read off the mesh: rays down from above
    the cup's lowest ring onto the host alone; the host's top is the highest
    hit. Cups above the chassis stand on the warmer tray, the rest on the
    drip grate."""
    tray = one(cls, P_CUPTRAY)
    grate = one(cls, P_GRATE)
    cups = cls["by"].get(P_CUP, [])
    if tray is None or grate is None:
        return None
    seats = []
    for c in cups:
        host = tray if c.lo.z > tray.lo.z - 0.01 else grate
        low = [p for p in c.pts if p.z < c.lo.z + 0.0004]
        top = None
        for p in low:
            hit = host.tree.ray_cast(Vector((p.x, p.y, c.lo.z + 0.02)), Vector((0.0, 0.0, -1.0)))
            if hit[0] is not None:
                top = hit[0].z if top is None else max(top, hit[0].z)
        seats.append(None if top is None else top - c.lo.z)
    return {"count": len(cups), "seats": seats}


def size_audit(cls):
    counter = one(cls, P_COUNTER)
    sides = cls["by"].get(P_SIDE, [])
    tray = one(cls, P_CUPTRAY)
    if counter is None or tray is None or len(sides) != 2:
        return None
    width = max(s.hi.x for s in sides) - min(s.lo.x for s in sides)
    return {"width": width, "height": tray.hi.z - counter.hi.z}


def pf_audit(cls):
    pf = one(cls, P_PF)
    group = one(cls, P_GROUP)
    gasket = one(cls, P_GASKET)
    if pf is None or group is None or gasket is None:
        return None
    return {"offset": math.hypot(pf.mean.x - group.mean.x, pf.mean.y - group.mean.y),
            "seat": pf.hi.z - gasket.lo.z,
            "gasket_offset": math.hypot(gasket.mean.x - group.mean.x, gasket.mean.y - group.mean.y)}


def gauge_audit(cls):
    bezels = cls["by"].get(P_BEZEL, [])
    glasses = cls["by"].get(P_GLASS, [])
    recess = []
    for g in glasses:
        b = min(bezels, key=lambda s: abs(s.mean.x - g.mean.x), default=None)
        if b is not None:
            recess.append(g.lo.y - b.lo.y)
    return {"bezels": len(bezels), "glasses": len(glasses), "recess": recess}


def tray_audit(cls):
    drip = one(cls, P_DRIP)
    front = one(cls, P_FRONT)
    sides = cls["by"].get(P_SIDE, [])
    if drip is None or front is None or len(sides) != 2:
        return None
    lo = min(s.lo.x for s in sides)
    hi = max(s.hi.x for s in sides)
    return {"margin": min(drip.lo.x - lo, hi - drip.hi.x), "tuck": drip.hi.y - front.lo.y}


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


def stance_audit(cls):
    """The machine's mass centre against the convex polygon of its feet's
    contact faces."""
    total = 0.0
    mom = Vector()
    for s in cls["all"]:
        if s.mat is None or s.part in PROP_PARTS:
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * PART_DENSITY.get(s.part, DENSITY[s.mat])
        total += m
        mom += m * cen
    com = mom / total
    pts = []
    for f in cls["by"].get(P_FOOT, []):
        pts += [(p.x, p.y) for p in f.pts if p.z < f.lo.z + 1e-4]
    if len(pts) < 3:
        return None
    hull = hull2d(pts)
    margin = 9.0
    for i in range(len(hull)):
        (x0, y0), (x1, y1) = hull[i], hull[(i + 1) % len(hull)]
        ln = math.hypot(x1 - x0, y1 - y0)
        margin = min(margin, ((x1 - x0) * (com.y - y0) - (y1 - y0) * (com.x - x0)) / ln)
    return {"mass": total, "com": com, "margin": margin}


def connected_components(cls):
    # a faceless shell (a stray vertex) is hygiene's to report, not a part
    parts = [s for s in cls["all"] if s.tri_idx]
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
    loose = [parts[i].part for i in range(n) if sizes[find(i)] < max(sizes.values())]
    return len(roots), sorted(sizes.values()), loose


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        # inside the envelope, so only the hygiene budget can see it
        bm.verts.new((0.0, 0.0, 0.2))
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
    img = bpy.data.images.new("EspressoNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = PAINT_IDX
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


FLAG_NAMES = ("float_foot", "offset_pin", "sink_cup", "narrow_body", "offset_pf", "drop_pf",
              "proud_gauge", "shift_tray", "bunch_feet", "loose_knob")


def check(skip_decimate, lift_z=False, stray_vert=False, flags=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(flags or {})
    low = build_machine_mesh("EspressoLow", bevel_offset=0.0006, bevel_segments=1, flags=flags)
    high = build_machine_mesh("EspressoHigh", bevel_offset=0.0006, bevel_segments=3, flags=flags)
    mats = machine_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the chassis paint: its chamfered box is where the
    # high mesh's rounder chamfer differs most from the low.
    target = mats[PAINT_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("machine mesh did not build", 3),) + none3

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
    pin = pin_audit(cls)
    cups = cups_audit(cls)
    size = size_audit(cls)
    pf = pf_audit(cls)
    gauge = gauge_audit(cls)
    tray = tray_audit(cls)
    stance = stance_audit(cls)
    ncomp, comp_sizes, loose = connected_components(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("machine has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "EspressoLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "EspressoLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_machine_mesh("EspressoColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "EspressoCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_espresso_machine_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} parts="
          f"{ {k: len(v) for k, v in sorted(cls['by'].items())} }")
    if feet:
        print(f"measured feet={feet['count']} counter_top={feet['top']:.5f} "
              f"seats={[round(s, 5) for s in feet['seats']]}")
    if pin:
        print(f"measured pin bosses={pin['bosses']} hubs={pin['hubs']} "
              f"offset={pin['offset']:.6f} tilt_deg={pin['tilt']:.4f} "
              f"not_through={pin['not_through']}")
    if cups:
        print(f"measured cups={cups['count']} seats="
              f"{[None if s is None else round(s, 5) for s in cups['seats']]}")
    if size:
        print(f"measured size width={size['width']:.5f} height={size['height']:.5f}")
    if pf:
        print(f"measured portafilter offset={pf['offset']:.6f} seat={pf['seat']:.5f} "
              f"gasket_offset={pf['gasket_offset']:.6f}")
    if gauge:
        print(f"measured gauges bezels={gauge['bezels']} glasses={gauge['glasses']} "
              f"recess={[round(r, 5) for r in gauge['recess']]}")
    if tray:
        print(f"measured drip_tray margin={tray['margin']:.5f} tuck={tray['tuck']:.5f}")
    if stance:
        print(f"measured mass={stance['mass']:.3f}kg com=({stance['com'].x:.4f},"
              f"{stance['com'].y:.4f},{stance['com'].z:.4f}) margin={stance['margin']:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]} loose_parts={sorted(set(loose))}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    for idx, (floor, label) in enumerate(zip(FACE_FLOORS, MAT_LABELS)):
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
    if (feet is None or feet["count"] != FEET_COUNT
            or any(not (FOOT_SEAT[0] <= s <= FOOT_SEAT[1]) for s in feet["seats"])):
        return (fail(f"feet on the counter: {feet}", 16),) + none3
    if (pin is None or pin["bosses"] != 2 or pin["hubs"] != 1
            or pin["offset"] > PIN_OFFSET_MAX or pin["tilt"] > PIN_TILT_MAX_DEG
            or pin["not_through"]):
        return (fail(f"lever pin: {pin}", 17),) + none3
    if (cups is None or cups["count"] != CUP_COUNT
            or any(s is None or not (CUP_SEAT[0] <= s <= CUP_SEAT[1]) for s in cups["seats"])):
        return (fail(f"cups seated: {cups}", 18),) + none3
    if (size is None or abs(size["width"] - BODY_W) > BODY_W_TOL
            or abs(size["height"] - BODY_H) > BODY_H_TOL):
        return (fail(f"size: {size}", 19),) + none3
    if pf is None or pf["offset"] > PF_OFFSET_MAX or pf["gasket_offset"] > PF_OFFSET_MAX:
        return (fail(f"portafilter coaxial: {pf}", 20),) + none3
    if not (PF_SEAT_BAND[0] <= pf["seat"] <= PF_SEAT_BAND[1]):
        return (fail(f"portafilter seat: {pf}", 21),) + none3
    if (gauge["bezels"] != GAUGE_COUNT or gauge["glasses"] != GAUGE_COUNT
            or any(not (GAUGE_RECESS[0] <= r <= GAUGE_RECESS[1]) for r in gauge["recess"])):
        return (fail(f"gauge faces: {gauge}", 22),) + none3
    if tray is None or tray["margin"] < TRAY_MARGIN_MIN or tray["tuck"] < TRAY_TUCK_MIN:
        return (fail(f"drip tray footprint: {tray}", 23),) + none3
    if stance is None or stance["margin"] < STANCE_MARGIN:
        return (fail(f"stance: {stance}", 24),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 25),) + none3
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
    # low right, cool rim behind, warm wedge pooled on the back wall. The
    # camera looks along (-0.55, 0.83), so the wall behind the machine in
    # frame lies 1.6 m to its -X; the wedge pools there.
    light("Key", (-0.9, -1.6, 1.5), 32.0, 0.8, (1.0, 0.95, 0.90), spread=18.0)
    light("Fill", (1.8, -0.6, 0.35), 3.4, 2.2, (0.72, 0.82, 1.0))
    light("Rim", (-0.5, 1.2, 0.9), 18.0, 0.7, (0.62, 0.78, 1.0))
    light("Wedge", (-1.1, 1.3, 0.6), 52.0, 1.2, (1.0, 0.68, 0.38),
          target=(centre.x - 1.6, centre.y + WALL_Y, 0.35))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((0.55, -0.83, 0.0)).normalized()
    cam.location = centre + view * 1.98 + Vector((0.0, 0.0, 0.52))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.080))
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
        return 26
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
    p.add_argument("--sink-cup", action="store_true")
    p.add_argument("--narrow-body", action="store_true")
    p.add_argument("--offset-pf", action="store_true")
    p.add_argument("--drop-pf", action="store_true")
    p.add_argument("--proud-gauge", action="store_true")
    p.add_argument("--shift-tray", action="store_true")
    p.add_argument("--bunch-feet", action="store_true")
    p.add_argument("--loose-knob", action="store_true")
    args = p.parse_args(argv)

    flags = {k: getattr(args, k) for k in FLAG_NAMES}
    code, low, target, tex = check(args.skip_decimate, lift_z=args.lift_z,
                                   stray_vert=args.stray_vert, flags=flags)
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("espresso-machine OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
