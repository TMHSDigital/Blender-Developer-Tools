"""Game-ready sci-fi hover bike — a showcase piece, not an example.

Asserts budget conformance of a procedural hover bike (a speeder parked on
its landing skids) after composing shipped pipeline pieces: bmesh
construction, UVs, ten materials, high-to-low normal bake, LOD chain,
convex collider, Unity glTF export.

The bike rides on two ducted fans, one ahead of the rider and one behind.
Between them a sculpted fuselage is lofted from superellipse sections along
the bike's length: a painted livery canopy over a dark belly, a parting-line
groove along both flanks and three transverse panel seams. On it: intake
grilles, tail vents, a crown vent, cooling fins and a finned heat sink;
access panels (a panel proud of a dark gasket by an even seam, hex
fasteners at the corners), an alloy service plate on the belly, a decal
plate, a hinged charge-port door; a pillion grab rail over the tail and a
tail-light cluster between the exhaust nozzles. A headlight pod sits on the
tank's front slope, a low fly screen behind it. Twin chrome stanchions in
pleated boots run through two sculpted triple clamps to fork caps; clip-on
clamps carry the bars with switch pods, lever perches, levers on pivot
bolts, ribbed grips and bar-end weights; an instrument cluster with an
emissive screen stands on a bracket under a small visor. A stitched,
pleated saddle is draped over the crown.

Each fan is a shroud (an airfoil-section ring: livery outside, dark inside,
with an accent band and a marker light) around a static motor can on four
canted stator vanes, a rotor hub, a spinner and seven twisted, lofted
blades. The two rotors are handed. Two aerofoil pylons (chord vertical in
the downwash) run from shroud to shroud, flared into both shroud walls,
tied into the belly by fairing webs, with a fastener row, a conduit in
P-clips along the crest and a foot peg. Under each pylon, at both ends, a
twin-plate pressed link hangs from a pylon lug to a skid lug, and an oleo
shock (anodised barrel, preload collar, boot, chrome rod) runs from a pylon
clevis to the link's middle: every joint a headed pin through two bosses
and one eye. The links carry two ski-section skid shoes on replaceable wear
strips, with bolted end caps, tied by two cross braces.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-skid`` both skids on the
ground, ``--offset-hub`` the fan hubs coaxial with their shrouds,
``--long-blades`` the blade-tip clearance band, ``--odd-hull`` the hull's
mirror symmetry, ``--skew-blade`` equal blade spacing, ``--narrow-skids``
the mass centre inside the skids' support polygon, ``--pop-lens`` one
connected assembly, ``--offset-pin`` every pin coaxial with its bushings,
``--skew-rod`` and ``--short-rod`` every shock rod coaxial with its barrel
and inside its stroke band.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python hover_bike.py --
    blender --background --python hover_bike.py -- --skip-decimate
    blender --background --python hover_bike.py -- --output bike.png
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

# --- Fuselage: superellipse sections lofted along X (nose at +X) -------------
HULL_XE = 0.515             # hull ends, each inside its shroud's wall
HULL_N = 2.6                # section superellipse exponent
HULL_PART = 0.60            # parting line (the shoulder), as a fraction of belly-to-crown
HULL_SEGS = 56
HULL_STATIONS = 46
GROOVE = 0.0016             # panel-seam depth
PANEL_X = (-0.44, 0.02, 0.36)
CAP_CHAMFER = 0.002
# (x, value) keys for the crown height, belly height and half-width
TOP_KEYS = [(-0.515, 0.472), (-0.49, 0.540), (-0.45, 0.660), (-0.40, 0.760),
            (-0.34, 0.795), (-0.27, 0.786), (-0.14, 0.782), (-0.02, 0.795),
            (0.10, 0.845), (0.20, 0.862), (0.28, 0.852), (0.36, 0.800),
            (0.43, 0.700), (0.48, 0.595), (0.515, 0.472)]
BOT_KEYS = [(-0.515, 0.374), (-0.40, 0.366), (0.00, 0.360), (0.40, 0.366),
            (0.515, 0.374)]
W_KEYS = [(-0.515, 0.082), (-0.45, 0.110), (-0.34, 0.142), (-0.18, 0.152),
          (0.02, 0.160), (0.16, 0.172), (0.30, 0.160), (0.42, 0.122),
          (0.515, 0.082)]

# --- Ducted fans ---------------------------------------------------------------
DUCT_X = 0.80               # fan axes at x = +-0.80 on the centreline
DUCT_Z0 = 0.30              # shroud trailing edge
DUCT_SEGS = 72
# shroud section (r, dz): throat 0.262 m, lip crown at dz 0.219, closed ring
DUCT_PROFILE = [
    (0.2700, 0.000), (0.2648, 0.030), (0.2627, 0.070), (0.2620, 0.110),
    (0.2630, 0.150), (0.2665, 0.180), (0.2730, 0.200), (0.2820, 0.2130),
    (0.2930, 0.2190), (0.3040, 0.2150), (0.3110, 0.2030), (0.3140, 0.1850),
    (0.3140, 0.0400), (0.3100, 0.0150), (0.3000, 0.0030), (0.2860, 0.000),
]
# segment j runs from point j to j+1: inner wall dark, lip and outside livery
DUCT_SEG_DARK = {0, 1, 2, 3, 4, 5, 14, 15}
BLADES_PER_FAN = 7
BLADE_ROOT = 0.058
BLADE_TIP = 0.252
ROTOR_DZ = 0.110
SPIN = {1: 1.0, -1: -1.0}   # front rotor counter-clockwise from above, rear clockwise
# (fraction root->tip, chord, max thickness, blade angle deg)
BLADE_STATIONS = [
    (0.00, 0.042, 0.0065, 46.0), (0.08, 0.050, 0.0060, 43.0), (0.18, 0.060, 0.0055, 39.0),
    (0.30, 0.066, 0.0050, 35.0), (0.45, 0.068, 0.0045, 31.0), (0.60, 0.066, 0.0040, 28.0),
    (0.75, 0.062, 0.0036, 26.0), (0.88, 0.057, 0.0032, 24.5), (1.00, 0.046, 0.0028, 23.0),
]
AIRFOIL_X = (1.0, 0.72, 0.45, 0.22, 0.07, 0.0, 0.07, 0.22, 0.45, 0.72)
BLADE_CAMBER = 0.045
BLADE_PIVOT = 0.40
VANE_DEG = (45.0, 135.0, 225.0, 315.0)
VANE_CANT = 12.0

# --- Pylons: aerofoil fairings from shroud to shroud, chord vertical ---------------
PYLON_Y = 0.230
PYLON_Z = 0.370             # half-chord height
PYLON_X = 0.625             # ends, inside the shroud walls
PYLON_CHORD = 0.074
PYLON_T = 0.34              # thickness / chord
PYLON_FLARE_X = 0.440       # the fillet into the shroud starts here
PYLON_FLARE = 1.45          # section growth at the shroud
PYLON_TE = 0.97             # blunt trailing edge (the underside), fraction of chord
PYLON_SEC = (0.02, 0.07, 0.16, 0.30, 0.46, 0.64, 0.82, PYLON_TE)
PYLON_BOLTS = (-0.39, -0.24, -0.05, 0.10, 0.24, 0.39)
WEB_X = (-0.20, 0.20)       # fairing webs from the pylons into the belly
WEB_Z = 0.415
WEB_SEC = (0.05, 0.20, 0.45, 0.72, 0.96)
PEG_X = -0.12

# --- Landing gear: per corner a twin-plate link and an oleo shock -----------------
# (|x|, z) of the pins (the wear strips' soles are the floor, z = 0); the
# gear lies in the vertical planes y = +-GEAR_Y under the pylons, pins along y.
GEAR_Y = PYLON_Y
LINK_TOP = (0.505, 0.292)   # pin A: pylon lug, link top
LINK_BOT = (0.640, 0.074)   # pin B: skid lug, link foot
SHOCK_TOP = (0.330, 0.300)  # pin C: pylon clevis, shock top eye
SHOCK_AT = 0.56             # pin E, the shock's foot, along the link A -> B
PAD_Z = (0.322, 0.348)      # mount pads engulfing the pylon's trailing edge
PIN_R = 0.0060
BUSH_RI = 0.0055            # a bushing's bore bites 0.5 mm into its pin
EYE_HALF = 0.0085           # a member eye's half-width along its pin
EYE_RO = 0.0125
CHEEK_Y = 0.0140            # cheek / link-plate mid-plane, off the joint's centre
BOSS_HALF = 0.0035
BOSS_RO = 0.0140
PLATE_HALF = 0.0025
PIN_BITE = 0.0005           # pin head and nut seat inside the outer bosses
JOINT_SEGS = 8
# shock stations along its axis from pin C (s = 0) to pin E (s = L)
CYL_S = (0.010, 0.150)      # body from the top eye's neck to the gland
CYL_R = 0.0220
ROD_R = 0.0085
ROD_IN = 0.085              # the rod's inner end inside the barrel
BOOT_S = (0.146, 0.188)
# --- Skids ------------------------------------------------------------------------
SKID_Y = GEAR_Y
SKID_Y_NARROW = 0.150       # --narrow-skids
SKID_W = 0.033              # shoe half-width: a ski, flat below and domed above
SKID_HT = 0.020             # crown over the section's centre line
SKID_HB = 0.008             # sole under it
STRIP_T = 0.0100            # wear strip thickness; the shoe rides this far up
STRIP_HW = 0.024
STRIP_X = 0.700
SKID_X = 0.76
SKID_TIP = (0.93, 0.098)
BRACE_X = 0.585
BRACE_R = 0.0085
FLOAT_SKID = 0.004          # --float-skid

# --- Cockpit ----------------------------------------------------------------------
RISER_X = 0.250
CLAMP_Z = 0.985
FORK_Y = 0.058
FORK_R = 0.0165
FORK_TOP = 1.012
BAR_Z = 0.996
BAR_HALF = 0.31
HEAD_Z = 0.600              # headlight axis height
SEAT_X0 = -0.330
SEAT_X1 = 0.000
SEAT_BITE = 0.012
SEAT_PITCH = 0.042
SEAT_SEAMS = 6
SEAT_SEAM0 = -0.290
SEAT_PUFF = 0.0035
SEAT_GROOVE = 0.003
SEAT_TOP_KEYS = [(-0.330, 0.840), (-0.290, 0.850), (-0.160, 0.846), (-0.060, 0.846),
                 (0.000, 0.852)]
SEAT_W_KEYS = [(-0.330, 0.112), (-0.250, 0.128), (-0.110, 0.120), (0.000, 0.098)]
NOZZLE_Y = 0.085
NOZZLE_Z = 0.640
NOZZLE_X = -0.400

# --- Falsifier sizes ---------------------------------------------------------------
FALSIFY_FAN = -1            # the rear fan: nothing in it sets the envelope
OFFSET_HUB = 0.0025
LONG_BLADES = 0.012
ODD_HULL = 0.004
SKEW_DEG = 4.0
POP_LENS = 0.020
OFFSET_PIN = 0.0015         # --offset-pin: the front-left link's foot pin, along x
SKEW_ROD = 0.0015           # --skew-rod: the rear-left rod, across its axis
SHORT_ROD = 0.045           # --short-rod: the rear-left rod's inner end, drawn out

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (2.234, 0.660, 1.112)
BASE_TRIS_MIN = 45000
BASE_TRIS_MAX = 46000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 10
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 1990
BAKE_RES = 1024
CAGE_EXTRUSION = 0.004
LIVERY_FACES_MIN = 3490
GRAPHITE_FACES_MIN = 5365
METAL_FACES_MIN = 5525
RUBBER_FACES_MIN = 1200
LEATHER_FACES_MIN = 1620
LIGHT_FACES_MIN = 490
GLASS_FACES_MIN = 460
ACCENT_FACES_MIN = 2565
CARBON_FACES_MIN = 1235
CHROME_FACES_MIN = 1215

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
SKID_COUNT = 2
# Fans: hub and motor can on the shroud axis, the shroud level.
FAN_COUNT = 2
HUB_AXIS_TOL = 0.001
AXIS_TILT_MAX_DEG = 0.3
FAN_PITCH_TOL = 0.002       # fan axes 1.60 m apart on the hull's centreline
# Tip clearance: blade tip to the shroud's inner wall, along the radial ray.
CLEAR_MIN = 0.006
CLEAR_MAX = 0.014
# Hull symmetry: every hull vertex has a partner at its mirror position.
MIRROR_EPS = 0.0005
HULL_LEN = 1.033
HULL_WIDTH = 0.344
SEAT_HEIGHT = 0.852
SIZE_TOL = 0.004
# Blade spacing: seven blades per rotor, equal gaps.
SPACING_TOL_DEG = 0.3
# Stance: the mass centre stands this far inside the skids' contact polygon.
DENSITY = (1600.0, 1400.0, 2700.0, 1200.0, 300.0, 1200.0, 2500.0, 2700.0, 1600.0, 7800.0)
HULL_DENSITY = 250.0        # the fuselage is a hollow monocoque with its internals
STANCE_MARGIN = 0.200
# Joints: every pin through three bushings (two outer bosses, one eye).
JOINT_COUNT = 16
JOINT_BUSHINGS = 3
PIN_OFFSET_MAX = 0.0003
PIN_TILT_MAX_DEG = 0.3
# Shocks: the rod on the barrel's axis; its travel inside the stroke band.
SHOCK_COUNT = 4
ROD_OFFSET_MAX = 0.0003
ROD_TILT_MAX_DEG = 0.3
EXPOSED_MIN = 0.100         # rod out of the gland
EXPOSED_MAX = 0.140
ENGAGE_MIN = 0.045          # rod still inside the barrel
# Face tags ("part" = role * 100 + unit) for the parts the audits read.
R_STRIP = 1
R_PIN = 2
R_BUSH = 3
R_CYL = 4
R_ROD = 5
# Hero yaw: the nose turned toward the camera's right.
HERO_YAW_DEG = -62.0
WALL_Y = 2.8

LIVERY_IDX = 0
GRAPHITE_IDX = 1
METAL_IDX = 2
RUBBER_IDX = 3
LEATHER_IDX = 4
LIGHT_IDX = 5
GLASS_IDX = 6
ACCENT_IDX = 7
CARBON_IDX = 8
CHROME_IDX = 9

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
# Construction helpers (copied from showcase/quad-drone, not imported)
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


def add_sheet(bm, surf, nu, nv, thick, mat_idx):
    """A closed plate: ``surf(u, v) -> (point, normal)`` over the unit square,
    offset ``thick`` back along the normal, rims stitched round the edge."""
    front, back = [], []
    for j in range(nv + 1):
        rf, rb = [], []
        for i in range(nu + 1):
            p, n = surf(i / nu, j / nv)
            rf.append(bm.verts.new(p))
            rb.append(bm.verts.new(p - n * thick))
        front.append(rf)
        back.append(rb)
    faces = []
    for j in range(nv):
        for i in range(nu):
            faces.append(bm.faces.new((front[j][i], front[j][i + 1], front[j + 1][i + 1],
                                       front[j + 1][i])))
            faces.append(bm.faces.new((back[j][i], back[j + 1][i], back[j + 1][i + 1],
                                       back[j][i + 1])))
    rim = ([(0, i) for i in range(nu + 1)] + [(j, nu) for j in range(1, nv + 1)]
           + [(nv, i) for i in reversed(range(nu))] + [(j, 0) for j in reversed(range(1, nv))])
    for k in range(len(rim)):
        (ja, ia), (jb, ib) = rim[k], rim[(k + 1) % len(rim)]
        faces.append(bm.faces.new((front[jb][ib], front[ja][ia], back[ja][ia], back[jb][ib])))
    _mark(faces, mat_idx)


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
# The fuselage's closed form
# --------------------------------------------------------------------------

def pchip(keys):
    """Monotone cubic through (x, y) keys (Fritsch-Carlson): no overshoot, so
    a crown key is the crown."""
    xs = [k[0] for k in keys]
    ys = [k[1] for k in keys]
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [d[0]] + [0.0] * (n - 2) + [d[-1]]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] > 0.0:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def f(x):
        x = min(max(x, xs[0]), xs[-1])
        i = 0
        while i < n - 2 and x > xs[i + 1]:
            i += 1
        t = (x - xs[i]) / h[i]
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1])
    return f


_TOP = pchip(TOP_KEYS)
_BOT = pchip(BOT_KEYS)
_WID = pchip(W_KEYS)
_SEAT_TOP = pchip(SEAT_TOP_KEYS)
_SEAT_W = pchip(SEAT_W_KEYS)


def hull_dims(x):
    """(parting-line height, half-width, crown height over it, belly depth)."""
    top, bot = _TOP(x), _BOT(x)
    zc = bot + HULL_PART * (top - bot)
    return zc, _WID(x), top - zc, zc - bot


def _se(c, n=HULL_N):
    return math.copysign(abs(c) ** (2.0 / n), c)


def hull_top(x, y):
    zc, w, ht, _hb = hull_dims(x)
    a = min(1.0, abs(y) / w)
    return zc + ht * (1.0 - a ** HULL_N) ** (1.0 / HULL_N)


def hull_side_y(x, z):
    zc, w, ht, hb = hull_dims(x)
    h = ht if z >= zc else hb
    a = min(1.0, abs(z - zc) / h)
    return w * (1.0 - a ** HULL_N) ** (1.0 / HULL_N)


def hull_F(p):
    zc, w, ht, hb = hull_dims(p.x)
    h = ht if p.z >= zc else hb
    return (abs(p.y) / w) ** HULL_N + (abs(p.z - zc) / h) ** HULL_N - 1.0


def hull_normal(p, eps=1e-5):
    g = Vector((
        hull_F(p + Vector((eps, 0, 0))) - hull_F(p - Vector((eps, 0, 0))),
        hull_F(p + Vector((0, eps, 0))) - hull_F(p - Vector((0, eps, 0))),
        hull_F(p + Vector((0, 0, eps))) - hull_F(p - Vector((0, 0, eps))),
    ))
    return g.normalized()


def hull_ring(x, inset=0.0):
    """One section loop: points [(y, z)] and per-segment material. The ring's
    parameter is symmetric about t = pi/2, so the loop is its own mirror."""
    zc, w, ht, hb = hull_dims(x)
    step = 2.0 * math.pi / HULL_SEGS
    du = min(math.asin(min(1.0, (GROOVE / ht) ** (HULL_N / 2.0))), 0.4 * step)
    dl = min(math.asin(min(1.0, (GROOVE / hb) ** (HULL_N / 2.0))), 0.4 * step)
    half = HULL_SEGS // 2
    ts = [(0.0, True), (du, False)]
    ts += [(step * i, False) for i in range(1, half)]
    ts += [(math.pi - du, False), (math.pi, True), (math.pi + dl, False)]
    ts += [(step * i, False) for i in range(half + 1, HULL_SEGS)]
    ts += [(2.0 * math.pi - dl, False)]
    pts = []
    grooved = []
    for t, g in ts:
        c, s = math.cos(t), math.sin(t)
        y = w * _se(c)
        z = zc + (ht if s >= 0.0 else hb) * _se(s)
        if g:
            y -= math.copysign(GROOVE, c)
        grooved.append(g)
        pts.append((y, z))
    if inset > 0.0:
        out = []
        for y, z in pts:
            d = math.hypot(y, z - zc)
            k = 1.0 - inset / d
            out.append((y * k, zc + (z - zc) * k))
        pts = out
    n = len(pts)
    # the belly below the parting line is dark composite, the canopy livery
    seg_mats = [GRAPHITE_IDX if (grooved[j] or grooved[(j + 1) % n]
                                 or pts[j][1] + pts[(j + 1) % n][1] < 2.0 * zc)
                else LIVERY_IDX for j in range(n)]
    return pts, seg_mats


def hull_stations():
    xs = []
    for k in range(HULL_STATIONS):
        s = -1.0 + 2.0 * k / (HULL_STATIONS - 1)
        xs.append(HULL_XE * (0.35 * math.sin(0.5 * math.pi * s) + 0.65 * s))
    xs = [x for x in xs if all(abs(x - g) > 0.006 for g in PANEL_X)]
    st = [(x, 0.0, False) for x in xs]
    for g in PANEL_X:
        st += [(g - 0.0016, 0.0, False), (g, GROOVE, True), (g + 0.0016, 0.0, False)]
    st.sort()
    st = [(-HULL_XE - 0.0015, CAP_CHAMFER, False)] + st + [(HULL_XE + 0.0015, CAP_CHAMFER, False)]
    return st


def add_hull(bm):
    rings, ring_mats, dark = [], [], []
    for x, inset, is_groove in hull_stations():
        pts, seg_mats = hull_ring(max(-HULL_XE, min(HULL_XE, x)), inset)
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
    f0.material_index = GRAPHITE_IDX
    f1.material_index = GRAPHITE_IDX


def bow(verts):
    """--odd-hull: a sideways bow, zero at both hull ends: an odd term in y."""
    for v in verts:
        x = max(-HULL_XE, min(HULL_XE, v.co.x))
        v.co.y += ODD_HULL * math.cos(0.5 * math.pi * x / HULL_XE)


def surface_frame(p, along):
    """Frame on the hull at ``p``: local Z the outward normal, local X
    ``along`` laid into the tangent plane."""
    return frame(hull_normal(p), along)


def grille_frame(p, along):
    rot = surface_frame(p, along)
    return Matrix((rot.col[0], rot.col[2], -rot.col[1])).transposed()   # u along, v out, w across


# --------------------------------------------------------------------------
# Assemblies
# --------------------------------------------------------------------------

def naca_half(x, t):
    return 5.0 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x * x
                      + 0.2843 * x ** 3 - 0.1036 * x ** 4)


def add_blade(bm, axis, e_r, spin, tip):
    """One lofted fan blade, every section wrapped onto its own cylinder so
    the tip is exactly ``tip`` from the axis: twisted, cambered, handed."""
    e_t = ZAX.cross(e_r) * spin
    secs = []
    for f, chord, thick, beta_deg in BLADE_STATIONS:
        r = BLADE_ROOT + f * (tip - BLADE_ROOT)
        beta = math.radians(beta_deg)
        ring = []
        for k, xc in enumerate(AIRFOIL_X):
            upper = k < 5
            camber = BLADE_CAMBER * chord * 4.0 * xc * (1.0 - xc)
            yt = naca_half(xc, thick)
            yy = camber + (yt if upper else -yt)
            s = (xc - BLADE_PIVOT) * chord
            t_off = -math.cos(beta) * s - math.sin(beta) * yy
            z_off = -math.sin(beta) * s + math.cos(beta) * yy
            a = t_off / r
            p = axis + ZAX * (ROTOR_DZ + z_off) + r * (e_r * math.cos(a) + e_t * math.sin(a))
            ring.append(bm.verts.new(p))
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


def add_fan(bm, side, bevel_verts, offset_hub=False, long_blades=False, skew_blade=False):
    """Shroud, accent band, marker light, motor can, stator vanes, rotor hub,
    spinner and blades of the fan at x = side * DUCT_X."""
    base = Vector((side * DUCT_X, 0.0, DUCT_Z0))
    add_lathe(bm, DUCT_PROFILE, DUCT_SEGS, LIVERY_IDX, center=base,
              seg_mats=[GRAPHITE_IDX if j in DUCT_SEG_DARK else LIVERY_IDX
                        for j in range(len(DUCT_PROFILE))])
    # accent band hooped onto the cylindrical outer wall (inner 3 mm inside it)
    add_lathe(bm, [(0.3110, 0.100), (0.3172, 0.1025), (0.3172, 0.1325), (0.3110, 0.1350)],
              DUCT_SEGS, ACCENT_IDX, center=base, phase=math.pi / DUCT_SEGS)
    # marker light on the shroud's nose (front) or tail (rear)
    e = Vector((side, 0.0, 0.0))
    rot = frame(e, (0.0, 1.0, 0.0))
    bevel_verts += add_prism(bm, rrect(0.036, 0.0075, 0.005), -0.006, 0.0022,
                             base + e * 0.314 + ZAX * 0.066, rot, LIGHT_IDX)
    # motor can on four canted stator vanes
    add_lathe(bm, [(0.020, -0.014), (0.046, -0.002), (0.062, 0.018), (0.0655, 0.040),
                   (0.0655, 0.090), (0.0625, 0.095)], 32, GRAPHITE_IDX, center=base, solid=True)
    for k, deg in enumerate(VANE_DEG):
        a = math.radians(deg)
        e_r = Vector((math.cos(a), math.sin(a), 0.0))
        e_t = ZAX.cross(e_r)
        cant = math.radians(VANE_CANT) * side
        ev = ZAX * math.cos(cant) + e_t * math.sin(cant)
        rot = Matrix((e_r, ev, e_r.cross(ev))).transposed()
        ol = [(0.050, -0.019), (0.273, -0.019), (0.273, 0.019), (0.050, 0.019)]
        bevel_verts += add_prism(bm, ol, -0.0045 - 0.0002 * k, 0.0045 + 0.0002 * k,
                                 base + ZAX * 0.049, rot, METAL_IDX)
    # rotor: hub, spinner, blades
    shift = Vector((0.0, OFFSET_HUB, 0.0)) if offset_hub else Vector()
    axis = base + shift
    add_lathe(bm, [(0.0700, 0.088), (0.0780, 0.092), (0.0780, 0.126), (0.0740, 0.130)], 32,
              METAL_IDX, center=axis, solid=True, phase=math.pi / 32.0)
    add_lathe(bm, [(0.0660, 0.124), (0.0685, 0.128), (0.0620, 0.145), (0.0480, 0.160),
                   (0.0280, 0.170), (0.0080, 0.174)], 32, ACCENT_IDX, center=axis, solid=True)
    tip = BLADE_TIP + (LONG_BLADES if long_blades else 0.0)
    park = math.radians(10.0 if side > 0 else 35.0)
    for b in range(BLADES_PER_FAN):
        a = park + 2.0 * math.pi * b / BLADES_PER_FAN
        if skew_blade and b == 0:
            a += math.radians(SKEW_DEG)
        e_r = Vector((math.cos(a), math.sin(a), 0.0))
        add_blade(bm, axis, e_r, SPIN[side], tip)


class Tagger:
    """Face tags for the parts the audits read: ``part`` = role * 100 + unit.
    Everything else keeps 0."""

    def __init__(self, bm):
        self.bm = bm
        self.layer = bm.faces.layers.int.new("part")

    def __call__(self, role, unit=0):
        return _Tag(self, role * 100 + unit)


class _Tag:
    def __init__(self, tg, code):
        self.tg, self.code = tg, code

    def __enter__(self):
        self.n0 = len(self.tg.bm.faces)
        return self

    def __exit__(self, *exc):
        bm = self.tg.bm
        bm.faces.ensure_lookup_table()
        for i in range(self.n0, len(bm.faces)):
            bm.faces[i][self.tg.layer] = self.code
        return False


def add_loft(bm, rings, mat_idx):
    """Closed loops of equal length joined in order, n-gon caps."""
    vs = [[bm.verts.new(p) for p in r] for r in rings]
    n = len(vs[0])
    faces = []
    for r0, r1 in zip(vs, vs[1:]):
        for k in range(n):
            m = (k + 1) % n
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
    faces.append(bm.faces.new(tuple(reversed(vs[0]))))
    faces.append(bm.faces.new(tuple(vs[-1])))
    _mark(faces, mat_idx)
    return [v for r in vs for v in r]


def smooth01(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def circle_pts(c, r, n=12, phase=0.0):
    return [(c[0] + r * math.cos(phase + 2.0 * math.pi * k / n),
             c[1] + r * math.sin(phase + 2.0 * math.pi * k / n)) for k in range(n)]


def aerofoil_loop(chord, t, sec=PYLON_SEC):
    """Symmetric section, leading edge first: [(u, w)], u metres along the
    chord from the leading edge, w across it; the trailing edge is blunt."""
    pts = [(0.0, 0.0)]
    pts += [(f * chord, naca_half(f, t) * chord) for f in sec]
    pts += [(f * chord, -naca_half(f, t) * chord) for f in reversed(sec)]
    return pts


def add_hex(bm, base, nrm, r, h, mat_idx, bury=0.001):
    """Hex bolt head standing on ``base`` along ``nrm``, its foot buried."""
    n = Vector(nrm).normalized()
    hint = XAX if abs(n.x) < 0.9 else YAX
    return add_lathe(bm, [(r, -bury), (r, h), (0.72 * r, h + 0.0012)], 6, mat_idx,
                     center=base, rot=frame(n, hint), solid=True, phase=math.pi / 12.0)


def add_xz_plate(bm, outline, y, half, mat_idx):
    """Planar outline [(x, z)] extruded across y from y - half to y + half."""
    rot = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))
    return add_prism(bm, outline, -half, half, (0.0, y, 0.0), rot, mat_idx)


def pylon_scale(x):
    return 1.0 + (PYLON_FLARE - 1.0) * smooth01(
        (abs(x) - PYLON_FLARE_X) / (PYLON_X - PYLON_FLARE_X))


def pylon_ring(x, y0):
    c = PYLON_CHORD * pylon_scale(x)
    top = PYLON_Z + 0.5 * c
    return [(x, y0 + w, top - u) for u, w in aerofoil_loop(c, PYLON_T)]


def add_pylons(bm, bevel_verts):
    """Two aerofoil pylons from shroud to shroud, chord vertical in the fans'
    downwash, flared into both shroud walls and tied into the belly by two
    fairing webs each; a fastener row on the outer face, a conduit in
    P-clips along the crest, a foot peg."""
    xs = [-PYLON_X, -0.595, -0.555, -0.515, -0.475, -PYLON_FLARE_X]
    xs = xs + [-x for x in reversed(xs)]
    zb = PYLON_Z + 0.5 * PYLON_CHORD - 0.30 * PYLON_CHORD
    yb = PYLON_Y + naca_half(0.30, PYLON_T) * PYLON_CHORD
    zc = PYLON_Z + 0.5 * PYLON_CHORD + 0.0040
    for s in (1.0, -1.0):
        y0 = s * PYLON_Y
        add_loft(bm, [pylon_ring(x, y0) for x in xs], LIVERY_IDX)
        # fastener row along the thickest line of the outer face
        for x in PYLON_BOLTS:
            add_hex(bm, Vector((x, s * yb, zb)), (0.0, s, 0.0), 0.0042, 0.0028, METAL_IDX)
        # conduit along the crest, its ends running into the flares
        add_tube(bm, [(-0.560, y0, zc), (0.560, y0, zc)], 0.0048, 8, RUBBER_IDX,
                 phase=math.pi / 8.0)
        for x in (-0.30, 0.0, 0.30):
            add_lathe(bm, [(0.0044, -0.0030), (0.0064, -0.0030), (0.0064, 0.0030),
                           (0.0044, 0.0030)], 8, METAL_IDX, center=(x, y0, zc),
                      rot=frame(XAX, ZAX), phase=math.pi / 8.0)
        # fairing webs into the belly: chord along the bike, flaring at the skin
        for x in WEB_X:
            yh = hull_side_y(x, WEB_Z) - 0.010
            p0 = Vector((x, s * (PYLON_Y + 0.004), PYLON_Z + 0.006))
            p1 = Vector((x, s * yh, WEB_Z))
            rings = []
            for t, k in ((0.0, 1.0), (0.55, 1.0), (0.80, 1.10), (0.92, 1.28), (1.0, 1.45)):
                p = p0 + (p1 - p0) * t
                c = 0.055 * k
                rings.append([(p.x + 0.5 * c - u, p.y, p.z + w)
                              for u, w in aerofoil_loop(c, 0.30, WEB_SEC)])
            add_loft(bm, rings, GRAPHITE_IDX)
        # foot peg: a ribbed rubber tread on a boss, accent end cap
        rot = frame((0.0, s, 0.0), (1.0, 0.0, 0.0))

        def ribs(ii, j):
            return 0.90 if (j in (2, 3) and ii % 2) else 1.0

        add_lathe(bm, [(0.0130, 0.006), (0.0165, 0.010), (0.0175, 0.016), (0.0175, 0.074),
                       (0.0165, 0.078), (0.0140, 0.080)], 16, RUBBER_IDX,
                  center=(PEG_X, y0, PYLON_Z), rot=rot, solid=True, rmod=ribs)
        add_lathe(bm, [(0.0105, 0.077), (0.0150, 0.0795), (0.0155, 0.087), (0.0105, 0.091)],
                  16, ACCENT_IDX, center=(PEG_X, y0, PYLON_Z), rot=rot, solid=True,
                  phase=math.pi / 16.0)


def corner_pins(e):
    """Pins A (link top), B (link foot), C (shock top), E (shock foot) of
    the corner at the front (e = 1) or rear (e = -1), in the plane y = 0."""
    a = Vector((e * LINK_TOP[0], 0.0, LINK_TOP[1]))
    b = Vector((e * LINK_BOT[0], 0.0, LINK_BOT[1]))
    c = Vector((e * SHOCK_TOP[0], 0.0, SHOCK_TOP[1]))
    return a, b, c, a + (b - a) * SHOCK_AT


def add_ring(bm, tg, unit, c, z0, z1, ro, phase, mat_idx=METAL_IDX):
    """One bushing on a joint (a boss or an eye), about the pin's axis (y).
    The three on a joint are turned to different phases, so their bores
    never share a face plane."""
    with tg(R_BUSH, unit):
        add_lathe(bm, [(BUSH_RI, z0), (ro, z0), (ro, z1), (BUSH_RI, z1)], JOINT_SEGS, mat_idx,
                  center=c, rot=frame(YAX, XAX), phase=phase)


def add_bosses(bm, tg, unit, c):
    for sy in (1.0, -1.0):
        z0, z1 = sy * (CHEEK_Y - BOSS_HALF), sy * (CHEEK_Y + BOSS_HALF)
        add_ring(bm, tg, unit, c, min(z0, z1), max(z0, z1), BOSS_RO,
                 0.0 if sy > 0 else 0.5 * math.pi / JOINT_SEGS)


def add_pin(bm, tg, unit, c):
    """Headed pin with a nut, through two bosses and the eye between them."""
    zo = CHEEK_Y + BOSS_HALF - PIN_BITE
    prof = [(0.0095, -zo - 0.0032), (0.0095, -zo), (PIN_R, -zo), (PIN_R, zo), (0.0098, zo),
            (0.0098, zo + 0.0036)]
    with tg(R_PIN, unit):
        add_lathe(bm, prof, JOINT_SEGS, CHROME_IDX, center=c, rot=frame(YAX, XAX), solid=True)


def add_gear(bm, tg, bevel_verts, offset_pin, skew_rod, short_rod):
    """Four corners, each a twin-plate pressed link from a pylon lug (A) to
    a skid lug (B) and an oleo shock from a pylon clevis (C) to the link's
    middle (E): every joint a pin through two bosses and one eye."""
    for s in (1.0, -1.0):
        yc = s * GEAR_Y
        dy = Vector((0.0, yc, 0.0))
        for e in (1.0, -1.0):
            k = (0 if s > 0 else 2) + (0 if e > 0 else 1)
            a, b, c, pe = [p + dy for p in corner_pins(e)]
            ua, ub, uc, ue = 4 * k, 4 * k + 1, 4 * k + 2, 4 * k + 3
            top = PAD_Z[0] + 0.008
            # mount pads engulfing the pylon's trailing edge
            for p in (a, c):
                bevel_verts += add_rbox(bm, 0.024, 0.0200, 0.005,
                                        [(0.002, PAD_Z[0]), (0.0, PAD_Z[0] + 0.003),
                                         (0.0, PAD_Z[1])], (p.x, yc, 0.0),
                                        Matrix.Identity(3), GRAPHITE_IDX, n_corner=2)
            # pylon lug at A: a single eye between the link plates
            ol = hull2d(circle_pts((a.x, a.z), 0.0115, 8) + [(a.x - 0.016, top), (a.x + 0.016, top)])
            add_xz_plate(bm, ol, yc, 0.0075, METAL_IDX)
            add_ring(bm, tg, ua, a, -EYE_HALF, EYE_HALF, EYE_RO, math.pi / JOINT_SEGS)
            add_pin(bm, tg, ua, a)
            # pylon clevis at C: two cheeks straddling the shock's top eye
            for sy in (1.0, -1.0):
                g = 0.0004 if sy > 0 else 0.0
                ol = hull2d(circle_pts((c.x, c.z), 0.0120 + g, 8)
                            + [(c.x - 0.017 - g, top + g), (c.x + 0.017 + g, top + g)])
                add_xz_plate(bm, ol, yc + sy * CHEEK_Y, PLATE_HALF, METAL_IDX)
            add_bosses(bm, tg, uc, c)
            add_ring(bm, tg, uc, c, -EYE_HALF, EYE_HALF, EYE_RO, math.pi / JOINT_SEGS)
            add_pin(bm, tg, uc, c)
            # twin pressed link plates A -> E -> B with bosses, a spacer between
            for sy in (1.0, -1.0):
                g = 0.0004 if sy > 0 else 0.0
                ol = hull2d(circle_pts((a.x, a.z), 0.0210 + g, 10)
                            + circle_pts((pe.x, pe.z), 0.0200 + g, 10)
                            + circle_pts((b.x, b.z), 0.0190 + g, 10))
                bevel_verts += add_xz_plate(bm, ol, yc + sy * CHEEK_Y, PLATE_HALF, METAL_IDX)
            for p, u in ((a, ua), (pe, ue), (b, ub)):
                add_bosses(bm, tg, u, p)
            add_lathe(bm, [(0.0065, -CHEEK_Y), (0.0065, CHEEK_Y)], 8, METAL_IDX,
                      center=(a + pe) * 0.5, rot=frame(YAX, XAX), solid=True)
            # skid lug at B on a pad clamped round the shoe's crown
            bl = b
            shoe_top = STRIP_T - 0.001 + SKID_HB + SKID_HT
            bevel_verts += add_rbox(bm, 0.032, 0.0230, 0.006,
                                    [(0.0, shoe_top - 0.006), (0.0, shoe_top + 0.004),
                                     (0.002, shoe_top + 0.006)], (b.x, yc, 0.0),
                                    Matrix.Identity(3), GRAPHITE_IDX, n_corner=2)
            ol = hull2d(circle_pts((bl.x, bl.z), 0.0115, 8)
                        + [(bl.x - 0.019, shoe_top + 0.001), (bl.x + 0.019, shoe_top + 0.001)])
            add_xz_plate(bm, ol, yc, 0.0075, METAL_IDX)
            add_ring(bm, tg, ub, bl, -EYE_HALF, EYE_HALF, EYE_RO, math.pi / JOINT_SEGS)
            shift = Vector((OFFSET_PIN, 0.0, 0.0)) if (offset_pin and k == 2) else Vector()
            add_pin(bm, tg, ub, bl + shift)
            add_pin(bm, tg, ue, pe)
            # the shock: barrel with a preload collar, chrome rod, boot, rod eye
            ax = (pe - c).normalized()
            ln = (pe - c).length
            rot = frame(ax, YAX)
            with tg(R_CYL, k):
                add_lathe(bm, [(0.0075, CYL_S[0]), (0.0150, CYL_S[0] + 0.008),
                               (CYL_R, CYL_S[0] + 0.016), (CYL_R, CYL_S[1] - 0.012),
                               (CYL_R - 0.003, CYL_S[1] - 0.006), (0.0140, CYL_S[1] - 0.003),
                               (0.0140, CYL_S[1])], 12, ACCENT_IDX, center=c, rot=rot, solid=True)
            add_lathe(bm, [(CYL_R - 0.0005, 0.034), (0.0250, 0.0355), (0.0250, 0.0505),
                           (CYL_R - 0.0005, 0.052)], 12, GRAPHITE_IDX, center=c, rot=rot,
                      phase=math.pi / 12.0)
            r_in = ROD_IN + (SHORT_ROD if (short_rod and k == 3) else 0.0)
            rc = c + (ax.cross(YAX).normalized() * SKEW_ROD if (skew_rod and k == 3) else Vector())
            with tg(R_ROD, k):
                add_lathe(bm, [(ROD_R, r_in), (ROD_R, ln - 0.013), (0.0065, ln - 0.009)], 10,
                          CHROME_IDX, center=rc, rot=rot, solid=True)
            prof = [(0.0125, BOOT_S[0])]
            ds = (BOOT_S[1] - BOOT_S[0] - 0.004) / 3.0
            for i in range(3):
                prof += [(0.0165, BOOT_S[0] + 0.002 + ds * (i + 0.25)),
                         (0.0138, BOOT_S[0] + 0.002 + ds * (i + 0.75))]
            prof += [(0.0105, BOOT_S[1])]
            add_lathe(bm, prof, 10, RUBBER_IDX, center=c, rot=rot, solid=True,
                      phase=math.pi / 10.0)
            add_ring(bm, tg, ue, pe, -EYE_HALF, EYE_HALF, EYE_RO, math.pi / JOINT_SEGS)


def add_skids(bm, tg, bevel_verts, narrow, float_skid):
    """Two painted skid shoes (a ski section: flat sole, domed crown,
    upturned tips) on replaceable wear strips, bolted end caps and side
    bolts; two cross braces."""
    sy_abs = SKID_Y_NARROW if narrow else SKID_Y
    zc0 = STRIP_T - 0.001 + SKID_HB
    nsec = 14
    for side, s in enumerate((1.0, -1.0)):
        yc = s * sy_abs
        lift = FLOAT_SKID if (float_skid and s > 0) else 0.0
        zc = zc0 + lift
        path = fillet_path([(-SKID_TIP[0], yc, SKID_TIP[1] + lift), (-SKID_X, yc, zc),
                            (SKID_X, yc, zc), (SKID_TIP[0], yc, SKID_TIP[1] + lift)], 0.10, 7)
        rings = []
        for i, p in enumerate(path):
            t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
            up = t.cross(YAX).normalized()
            kk = 1.0 - 0.15 * smooth01((abs(p.x) - SKID_X) / (SKID_TIP[0] - SKID_X))
            ring = []
            for q in range(nsec):
                a = 2.0 * math.pi * q / nsec
                sa = math.sin(a)
                n = 2.4 if sa >= 0.0 else 5.0
                h = SKID_HT if sa >= 0.0 else SKID_HB
                ring.append(p + YAX * (SKID_W * kk * _se(math.cos(a), n))
                            + up * (h * kk * _se(sa, n)))
            rings.append(ring)
        add_loft(bm, rings, LIVERY_IDX)
        with tg(R_STRIP, side):
            add_rbox(bm, STRIP_HW, 0.5 * STRIP_T, 0.0025,
                     [(0.003, -STRIP_X), (0.0, -STRIP_X + 0.006), (0.0, STRIP_X - 0.006),
                      (0.003, STRIP_X)], (0.0, yc, 0.5 * STRIP_T + lift), frame(XAX, YAX),
                     GRAPHITE_IDX, n_corner=2)
        # bolted end caps over the upturned tips
        for p_end, p_prev in ((path[0], path[1]), (path[-1], path[-2])):
            d = (p_end - p_prev).normalized()
            rot = frame(d, YAX)
            bevel_verts += add_rbox(bm, 0.85 * SKID_W + 0.003, 0.85 * SKID_HT + 0.003, 0.009,
                                    [(0.0, -0.028), (0.0, 0.002), (0.004, 0.008), (0.010, 0.011)],
                                    p_end, rot, ACCENT_IDX, n_corner=2)
            for sy in (1.0, -1.0):
                add_hex(bm, p_end - d * 0.013 + YAX * (sy * (0.85 * SKID_W + 0.003)),
                        (0.0, sy, 0.0), 0.0035, 0.0024, METAL_IDX)
        # the wear strip's through-bolts, heads on the shoe's outer side
        for x in (-0.46, -0.16, 0.16, 0.46):
            add_hex(bm, Vector((x, yc + s * (SKID_W - 0.0008), zc)), (0.0, s, 0.0),
                    0.0036, 0.0024, METAL_IDX, bury=0.0012)
    # cross braces tying the two shoes, collars at the shoes
    for e in (1.0, -1.0):
        x = e * BRACE_X
        z = zc0 + 0.006
        add_tube(bm, [(x, -(sy_abs - 0.006), z), (x, sy_abs - 0.006, z)], BRACE_R, 10, METAL_IDX)
        for sy in (1.0, -1.0):
            add_lathe(bm, [(BRACE_R - 0.0005, -0.004), (0.0125, -0.004), (0.0125, 0.004),
                           (BRACE_R - 0.0005, 0.004)], 10, ACCENT_IDX,
                      center=(x, sy * (sy_abs - SKID_W - 0.002), z), rot=frame(YAX, XAX),
                      phase=math.pi / 10.0)


def clamp_outline(k):
    """A triple clamp in plan: bosses round both stanchions and the stem."""
    return hull2d(circle_pts((RISER_X, FORK_Y), 0.0265 * k, 12)
                  + circle_pts((RISER_X, -FORK_Y), 0.0265 * k, 12)
                  + circle_pts((RISER_X + 0.030, 0.0), 0.024 * k, 12))


def add_cockpit(bm, bevel_verts, pop_lens):
    """Fork, triple clamps, clip-ons, bars, grips, levers, switch pods,
    cluster, windscreen, headlight."""
    ident = Matrix.Identity(3)
    # twin chrome stanchions in pleated boots, through two triple clamps
    for s in (1.0, -1.0):
        fc = Vector((RISER_X, s * FORK_Y, 0.0))
        zt = hull_top(RISER_X, s * FORK_Y)
        add_lathe(bm, [(FORK_R, zt - 0.030), (FORK_R, FORK_TOP - 0.002),
                       (FORK_R - 0.002, FORK_TOP)], 16, CHROME_IDX, center=fc, solid=True)
        prof = [(0.0260, zt - 0.020)]
        for k in range(4):
            z = zt + 0.004 + 0.012 * k
            prof += [(0.0255 - 0.0012 * k, z), (0.0205 - 0.0012 * k, z + 0.006)]
        prof += [(0.0200, zt + 0.054), (0.0170, zt + 0.057)]
        add_lathe(bm, prof, 12, RUBBER_IDX, center=fc, solid=True, phase=math.pi / 12.0)
        # fork cap (preload adjuster) and the clip-on clamp under it
        add_lathe(bm, [(0.0150, FORK_TOP - 0.004), (0.0172, FORK_TOP), (0.0172, FORK_TOP + 0.010),
                       (0.0125, FORK_TOP + 0.014)], 12, ACCENT_IDX, center=fc, solid=True)
        add_lathe(bm, [(FORK_R - 0.0005, BAR_Z - 0.011), (0.0250, BAR_Z - 0.011),
                       (0.0250, BAR_Z + 0.011), (FORK_R - 0.0005, BAR_Z + 0.011)], 16,
                  METAL_IDX, center=fc, phase=math.pi / 16.0)
    for k, (z0, z1) in enumerate(((0.903, 0.925), (0.962, 0.982))):
        bevel_verts += add_prism(bm, clamp_outline(1.0 - 0.06 * k), z0, z1, (0.0, 0.0, 0.0),
                                 ident, METAL_IDX)
        # pinch bolts on the clamp's rear face, one per stanchion
        for s in (1.0, -1.0):
            add_hex(bm, Vector((RISER_X - 0.0265 * (1.0 - 0.06 * k) + 0.0008,
                                s * (FORK_Y + 0.006), 0.5 * (z0 + z1))),
                    (-1.0, 0.0, 0.0), 0.0040, 0.0028, CHROME_IDX)
    # steering stem between the clamps and its nut on top
    sc = (RISER_X + 0.030, 0.0, 0.0)
    add_lathe(bm, [(0.0135, 0.918), (0.0135, 0.969)], 12, CHROME_IDX, center=sc, solid=True)
    add_lathe(bm, [(0.0125, 0.9795), (0.0125, 0.9905), (0.0090, 0.9925)], 6, ACCENT_IDX,
              center=sc, solid=True)
    for s in (1.0, -1.0):
        p0 = Vector((RISER_X, s * (FORK_Y + 0.020), BAR_Z))
        p1 = Vector((RISER_X + 0.004, s * 0.150, BAR_Z))
        p2 = Vector((RISER_X - 0.036, s * BAR_HALF, BAR_Z + 0.022))
        pts = fillet_path([p0, p1, p2], 0.05, 6)
        add_tube(bm, pts, 0.0110, 12, METAL_IDX)
        d0 = (p1 - p0).normalized()
        # clip-on boss where the bar leaves the clamp
        add_lathe(bm, [(0.0145, -0.004), (0.0145, 0.016), (0.0120, 0.020)], 12, METAL_IDX,
                  center=p0, rot=frame(d0, ZAX), solid=True)
        # switch pod: housing on the bar, two buttons facing the rider
        pp = p1 - d0 * 0.046
        rot = frame(d0, ZAX)
        add_rbox(bm, 0.0135, 0.0165, 0.006, [(0.002, -0.012), (0.0, -0.010), (0.0, 0.010),
                                             (0.002, 0.012)], pp, rot, GRAPHITE_IDX, n_corner=2)
        back = -rot.col[1] if rot.col[1].x > 0.0 else rot.col[1]
        for q, mat, h in ((1.0, ACCENT_IDX, 0.0025), (-1.0, CHROME_IDX, 0.0019)):
            add_lathe(bm, [(0.0040, -0.0015 - h), (0.0040, h), (0.0030, h + 0.0010)], 8, mat,
                      center=pp + back * 0.0160 + ZAX * (q * 0.0055), rot=frame(back, ZAX),
                      solid=True, phase=(0.0 if q > 0 else math.pi / 8.0))
        d = (p2 - p1).normalized()
        g0 = p1 + d * 0.050

        def grip(ii, j):
            return 0.93 if (2 <= j <= 9 and ii % 2) else 1.0

        gprof = [(0.0140, 0.000), (0.0165, 0.004)]
        for k in range(8):
            gprof.append((0.0165, 0.012 + 0.012 * k))
        gprof += [(0.0175, 0.106), (0.0175, 0.112), (0.0160, 0.115)]
        grip_len = (p2 - g0).length
        rot = frame(d, ZAX)
        add_lathe(bm, gprof, 12, RUBBER_IDX, center=g0, rot=rot, solid=True, rmod=grip)
        add_lathe(bm, [(0.0120, 0.000), (0.0170, 0.004), (0.0180, 0.014), (0.0130, 0.021)], 16,
                  ACCENT_IDX, center=g0 + d * (grip_len - 0.004), rot=rot, solid=True,
                  phase=math.pi / 16.0)
        # brake-lever perch, lever on its pivot bolt
        perch = p1 + d * 0.028
        add_lathe(bm, [(0.0145, 0.000), (0.0190, 0.002), (0.0190, 0.016), (0.0145, 0.018)], 16,
                  METAL_IDX, center=perch, rot=rot, solid=True, phase=math.pi / 32.0)
        fwd = d.cross(ZAX).normalized()
        if fwd.x < 0.0:
            fwd = -fwd
        lv0 = perch + d * 0.009 + fwd * 0.010 - ZAX * 0.004
        lv1 = lv0 + fwd * 0.030
        lv2 = lv1 + d * 0.105 - fwd * 0.004
        bevel_verts += add_bar(bm, [lv0, lv1, lv2], ZAX, 0.0060, 0.0028, 0.0018, ACCENT_IDX,
                               fillet=0.012)
        add_lathe(bm, [(0.0042, -0.0065), (0.0042, 0.0060), (0.0030, 0.0072)], 8, CHROME_IDX,
                  center=lv0 + fwd * 0.004, solid=True, phase=math.pi / 16.0)
    # instrument cluster facing the rider, emissive screen on its face,
    # on a bracket from the top clamp
    n_c = Vector((-1.0, 0.0, 1.25)).normalized()
    c = Vector((RISER_X + 0.060, 0.0, CLAMP_Z + 0.045))
    rot = frame(n_c, (0.0, 1.0, 0.0))
    add_rbox(bm, 0.070, 0.036, 0.012, [(0.003, -0.044), (0.0, -0.041), (0.0, -0.003),
                                       (0.003, 0.0)], c, rot, GRAPHITE_IDX, n_corner=4)
    bevel_verts += add_prism(bm, rrect(0.054, 0.025, 0.005), -0.0015, 0.0012, c, rot, LIGHT_IDX)
    add_bar(bm, [Vector((RISER_X + 0.034, 0.0, 0.976)), Vector((RISER_X + 0.058, 0.0, 0.996)),
                 c - n_c * 0.030], YAX, 0.012, 0.0045, 0.002, METAL_IDX, fillet=0.010)
    # visor: a small tinted screen rising off the cluster's front edge
    ex, ey = rot.col[0], rot.col[1]
    d_v = Vector((0.55, 0.0, 1.0)).normalized()

    def visor(u, v):
        uu = 2.0 * u - 1.0
        p = (c + ex * (0.074 * (1.0 - 0.18 * v * v) * uu) + ey * -0.030 - n_c * 0.006
             + d_v * (0.078 * v) + XAX * (0.014 * (1.0 - uu * uu) * math.sin(0.5 * math.pi * v)))
        return p, Vector((1.0, -0.25 * uu, 0.55)).normalized()

    add_sheet(bm, visor, 10, 4, 0.003, GLASS_IDX)
    # fly screen: a low tinted fairing from the tank's crown to the clamps
    ws_hw = 0.118

    def screen(u, v):
        uu = 2.0 * u - 1.0
        y = ws_hw * (1.0 - 0.30 * v * v) * uu
        xb = 0.440 - 0.030 * uu * uu
        zb = hull_top(xb, y) - 0.026
        xt = 0.392 - 0.022 * uu * uu
        zt_ = 0.958 - 0.024 * uu * uu
        p = Vector((xb + (xt - xb) * v + 0.014 * math.sin(math.pi * v), y, zb + (zt_ - zb) * v))
        nrm = Vector((1.0, -0.20 * uu, 0.55)).normalized()
        return p, nrm

    add_sheet(bm, screen, 12, 6, 0.004, GLASS_IDX)
    # headlight pod on the tank's front slope
    lo, hi = 0.36, HULL_XE
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if hull_top(mid, 0.0) > HEAD_Z:
            lo = mid
        else:
            hi = mid
    xh = 0.5 * (lo + hi) + 0.004
    ax = Vector((1.0, 0.0, 0.0))
    rot = frame(ax, ZAX)
    hc = Vector((xh, 0.0, HEAD_Z))
    add_lathe(bm, [(0.0540, -0.090), (0.0575, -0.030), (0.0585, 0.024), (0.0560, 0.034),
                   (0.0470, 0.036), (0.0440, 0.030), (0.0430, 0.012)], 32, LIVERY_IDX,
              center=hc, rot=rot, solid=True,
              seg_mats=[LIVERY_IDX, LIVERY_IDX, METAL_IDX, METAL_IDX, METAL_IDX, METAL_IDX],
              cap_mats=(LIVERY_IDX, METAL_IDX))
    add_lathe(bm, [(0.0400, 0.008), (0.0400, 0.016), (0.0300, 0.020), (0.0120, 0.023)], 24,
              LIGHT_IDX, center=hc, rot=rot, solid=True, phase=math.pi / 48.0)
    lens = hc + ax * (POP_LENS if pop_lens else 0.0)
    add_lathe(bm, [(0.0445, 0.020), (0.0450, 0.029), (0.0405, 0.039), (0.0260, 0.046),
                   (0.0090, 0.049)], 32, GLASS_IDX, center=lens, rot=rot, solid=True,
              phase=math.pi / 32.0)


def add_seat(bm):
    """Saddle draped over the crown: its underside follows the hull a bite
    inside it, its top carries puffed pleats between stitched seams."""
    seams = [SEAT_SEAM0 + SEAT_PITCH * k for k in range(SEAT_SEAMS + 1)]
    xs = []
    n_st = 44
    for k in range(n_st):
        x = SEAT_X0 + (SEAT_X1 - SEAT_X0) * k / (n_st - 1)
        if all(abs(x - g) > 0.004 for g in seams):
            xs.append((x, 0.0, False))
    for g in seams:
        xs += [(g - 0.0025, 0.0, False), (g, 0.0, True), (g + 0.0025, 0.0, False)]
    xs.sort()
    xs = ([(SEAT_X0 - 0.004, 0.010, False), (SEAT_X0 - 0.0015, 0.003, False)] + xs
          + [(SEAT_X1 + 0.0015, 0.003, False), (SEAT_X1 + 0.004, 0.010, False)])
    m = 28
    rings = []
    for x, inset, seam in xs:
        xc = max(SEAT_X0, min(SEAT_X1, x))
        hw = _SEAT_W(xc) - inset
        top = _SEAT_TOP(xc) - inset
        if seams[0] <= xc <= seams[-1]:
            ph = math.pi * (xc - seams[0]) / SEAT_PITCH
            top += SEAT_PUFF * math.sin(ph) ** 2
        if seam:
            top -= SEAT_GROOVE
        ring = []
        for i in range(m):
            t = 2.0 * math.pi * (i + 0.5) / m
            a = math.copysign(abs(math.cos(t)) ** 0.5, math.cos(t))
            b = math.copysign(abs(math.sin(t)) ** 0.5, math.sin(t))
            y = hw * a
            zb = hull_top(xc, y) - SEAT_BITE
            zt = top - 0.030 * abs(a) ** 3
            ring.append(bm.verts.new((x, y, zb + (zt - zb) * 0.5 * (b + 1.0))))
        rings.append(ring)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(m):
            k = (i + 1) % m
            faces.append(bm.faces.new((r0[i], r0[k], r1[k], r1[i])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, LEATHER_IDX)


def hull_patch(bm, s, x0, x1, f0, f1, proud, depth, mat_idx, nu=4, nv=4, below=False):
    """A plate conforming to the fuselage's flank: x from x0 to x1, height
    f0..f1 as fractions of the crown's height over the parting line (or,
    ``below``, of the belly's depth under it); its face ``proud`` off the
    skin, its back ``depth`` inside it."""

    def surf(u, v):
        x = x0 + (x1 - x0) * u
        zc, _w, ht, hb = hull_dims(x)
        f = f0 + (f1 - f0) * v
        z = zc - hb * f if below else zc + ht * f
        p = Vector((x, s * hull_side_y(x, z), z))
        n = hull_normal(p)
        return p + n * proud, n

    add_sheet(bm, surf, nu, nv, proud + depth, mat_idx)
    return surf


def flank_point(s, x, f, proud=0.0, below=False):
    zc, _w, ht, hb = hull_dims(x)
    z = zc - hb * f if below else zc + ht * f
    p = Vector((x, s * hull_side_y(x, z), z))
    n = hull_normal(p)
    return p + n * proud, n


def access_panel(bm, s, x0, x1, f0, f1, face_mat, bolts=True, below=False,
                 gasket=GRAPHITE_IDX):
    """A removable panel: a dark gasket proud of the skin, the panel proud
    of the gasket inset by an even seam, hex fasteners at the corners."""
    _zc, _w, ht, hb = hull_dims(0.5 * (x0 + x1))
    h = hb if below else ht
    g = 0.0040
    # skin, gasket and panel faces each at least 1 mm apart, fronts and backs
    hull_patch(bm, s, x0, x1, f0, f1, 0.0010, 0.0040, gasket, below=below)
    hull_patch(bm, s, x0 + g, x1 - g, f0 + g / h, f1 - g / h, 0.0025, 0.0015, face_mat,
               below=below)
    if bolts:
        ix, iz = 0.009, 0.009 / h
        for x in (x0 + ix, x1 - ix):
            for f in (f0 + iz, f1 - iz):
                p, n = flank_point(s, x, f, 0.0025, below)
                add_hex(bm, p, n, 0.0032, 0.0018, METAL_IDX)


def add_details(bm, bevel_verts):
    """Intake grilles, tail vents, cooling fins, a heat sink, access panels,
    a decal plate, a charge-port door, crown vent, grab rail, tail light,
    exhaust nozzles."""
    for s in (1.0, -1.0):
        # intake grille on the tank flank
        x = 0.200
        zc, _w, ht, _hb = hull_dims(x)
        z = zc + 0.30 * ht
        p = Vector((x, s * hull_side_y(x, z), z))
        bevel_verts += add_prism(bm, comb_outline(0.050, -0.007, 0.0008, 7, 0.0022, 0.0042),
                                 -0.021, 0.021, p, grille_frame(p, (1.0, 0.0, 0.0)),
                                 GRAPHITE_IDX)
        # louvred vent on the tail flank
        x = -0.250
        zc, _w, ht, _hb = hull_dims(x)
        z = zc + 0.30 * ht
        p = Vector((x, s * hull_side_y(x, z), z))
        bevel_verts += add_prism(bm, comb_outline(0.036, -0.007, 0.0008, 5, 0.0020, 0.0036),
                                 -0.016, 0.016, p, grille_frame(p, (1.0, 0.0, 0.0)),
                                 GRAPHITE_IDX)
        # cooling fins on the dark flank under the rider's knee
        x = 0.085
        zc, _w, _ht, hb = hull_dims(x)
        z = zc - 0.46 * hb
        p = Vector((x, s * hull_side_y(x, z), z))
        bevel_verts += add_prism(bm, comb_outline(0.040, -0.008, 0.0008, 6, 0.0026, 0.0060),
                                 -0.070, 0.070, p, grille_frame(p, (0.0, 0.0, 1.0)), METAL_IDX)
        # heat sink near the tail: upright fins across the rear flank
        x = -0.335
        zc, _w, _ht, hb = hull_dims(x)
        z = zc - 0.36 * hb
        p = Vector((x, s * hull_side_y(x, z), z))
        bevel_verts += add_prism(bm, comb_outline(0.052, -0.010, 0.0008, 7, 0.0022, 0.0105),
                                 -0.032, 0.032, p, grille_frame(p, (1.0, 0.0, 0.0)), METAL_IDX)
        # access panel on the tank flank, fore of the grille
        access_panel(bm, s, 0.040, 0.136, 0.08, 0.50, LIVERY_IDX)
        # alloy service plate on the dark belly, between heat sink and fins
        access_panel(bm, s, -0.215, -0.040, 0.14, 0.44, METAL_IDX, below=True,
                     gasket=RUBBER_IDX)
        # decal plate under the saddle's edge: a dark board, an anodised field
        hull_patch(bm, s, -0.188, -0.058, 0.07, 0.42, 0.0010, 0.0040, GRAPHITE_IDX)
        _zc, _w, ht, _hb = hull_dims(-0.123)
        g = 0.0060
        hull_patch(bm, s, -0.188 + g, -0.058 - g, 0.07 + g / ht, 0.42 - g / ht, 0.0022,
                   0.0015, ACCENT_IDX)
        if s > 0:
            # a second panel where the near side has its charge port
            access_panel(bm, s, 0.262, 0.344, 0.12, 0.46, LIVERY_IDX)
    # charge-port door on the near (y-) flank: hinged along its top edge,
    # an anodised latch tab at its foot
    s = -1.0
    x0, x1, f0, f1 = 0.270, 0.336, 0.16, 0.44
    access_panel(bm, s, x0, x1, f0, f1, LIVERY_IDX, bolts=False)
    _zc, _w, ht, _hb = hull_dims(0.5 * (x0 + x1))
    pa, _n = flank_point(s, x0 + 0.006, f1 - 0.004 / ht, 0.0040)
    pb, _n = flank_point(s, x1 - 0.006, f1 - 0.004 / ht, 0.0040)
    add_tube(bm, [pa, pb], 0.0032, 8, METAL_IDX)
    pl, nl = flank_point(s, 0.5 * (x0 + x1), f0 + 0.010 / ht, 0.0024)
    bevel_verts += add_prism(bm, rrect(0.009, 0.004, 0.002), -0.0010, 0.0028, pl,
                             frame(nl, XAX), ACCENT_IDX)
    # crown vent ahead of the saddle
    x = 0.100
    p = Vector((x, 0.0, hull_top(x, 0.0)))
    bevel_verts += add_prism(bm, comb_outline(0.032, -0.008, 0.0008, 6, 0.0020, 0.0036),
                             -0.045, 0.045, p, grille_frame(p, (1.0, 0.0, 0.0)), GRAPHITE_IDX)
    # pillion grab rail: a bent bar from both flanks, arching over the tail
    yf = hull_side_y(-0.355, 0.745) - 0.006
    rail = []
    for s in (-1.0, 1.0):
        half = [(-0.355, yf, 0.745), (-0.366, 0.132, 0.790), (-0.430, 0.112, 0.806),
                (-0.472, 0.052, 0.806)]
        pts = [Vector((x, s * y, z)) for x, y, z in half]
        rail += pts if s < 0 else list(reversed(pts))
    add_tube(bm, fillet_path(rail, 0.030, 3), 0.0105, 8, METAL_IDX, phase=math.pi / 8.0)
    for s in (1.0, -1.0):
        p, n = flank_point(s, -0.355, (0.745 - hull_dims(-0.355)[0]) / hull_dims(-0.355)[2])
        add_lathe(bm, [(0.0150, -0.004), (0.0150, 0.004), (0.0110, 0.007)], 12, METAL_IDX,
                  center=p, rot=frame(n, XAX), solid=True)
    # tail light cluster on the tail's rear slope: housing, lamp, dividers
    lo, hi = -HULL_XE, -0.36
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if hull_top(mid, 0.0) < 0.700:
            lo = mid
        else:
            hi = mid
    p = Vector((0.5 * (lo + hi), 0.0, 0.700))
    rot = frame(hull_normal(p), YAX)
    bevel_verts += add_rbox(bm, 0.048, 0.017, 0.008, [(0.002, -0.014), (0.0, -0.011),
                                                     (0.0, 0.004), (0.002, 0.006)],
                            p, rot, GRAPHITE_IDX, n_corner=3)
    add_prism(bm, rrect(0.040, 0.010, 0.006), 0.0040, 0.0066, p, rot, LIGHT_IDX)
    for q, h in ((-0.013, 0.0075), (0.013, 0.0079)):
        add_prism(bm, rrect(0.0014, 0.0115 + h - 0.0075, 0.0006), h - 0.0025, h,
                  p + rot.col[0] * q, rot, GRAPHITE_IDX)
    # exhaust nozzles out of the tail flanks, over the rear fan
    ax = Vector((-1.0, 0.0, 0.0))
    rot = frame(ax, ZAX)
    for k, s in enumerate((1.0, -1.0)):
        c = Vector((NOZZLE_X, s * NOZZLE_Y, NOZZLE_Z))

        def petals(ii, j):
            return 0.965 if (j in (2, 3) and ii % 2 == 0) else 1.0

        # a cup: closed at its buried back, its bore floored at the glow
        add_lathe(bm, [(0.0480, -0.160), (0.0505, 0.020), (0.0540, 0.160), (0.0520, 0.193),
                       (0.0470, 0.198), (0.0395, 0.188), (0.0355, 0.160), (0.0355, 0.120)],
                  24, METAL_IDX, center=c, rot=rot, solid=True, rmod=petals)
        add_lathe(bm, [(0.0505, 0.090), (0.0575, 0.093), (0.0575, 0.135), (0.0505, 0.138)],
                  24, ACCENT_IDX, center=c, rot=rot, phase=math.pi / 24.0)
        add_lathe(bm, [(0.0365, 0.114), (0.0365, 0.124), (0.0300, 0.128), (0.0100, 0.130)], 20,
                  LIGHT_IDX, center=c, rot=rot, solid=True, phase=k * math.pi / 40.0)
        add_lathe(bm, [(0.0160, 0.122), (0.0150, 0.150), (0.0100, 0.168), (0.0040, 0.180),
                       (0.0010, 0.182)], 12, METAL_IDX, center=c, rot=rot, solid=True,
                  phase=math.pi / 12.0)


def build_bike_mesh(name, bevel_offset, bevel_segments, float_skid=False, offset_hub=False,
                    long_blades=False, odd_hull=False, skew_blade=False, narrow_skids=False,
                    pop_lens=False, offset_pin=False, skew_rod=False, short_rod=False):
    bm = bmesh.new()
    try:
        bevel_verts = []
        tg = Tagger(bm)
        add_hull(bm)
        n_hull = len(bm.verts)
        for side in (1, -1):
            f = side == FALSIFY_FAN
            add_fan(bm, side, bevel_verts, offset_hub=offset_hub and f,
                    long_blades=long_blades and f, skew_blade=skew_blade and f)
        add_pylons(bm, bevel_verts)
        add_gear(bm, tg, bevel_verts, offset_pin, skew_rod, short_rod)
        add_skids(bm, tg, bevel_verts, narrow_skids, float_skid)
        add_cockpit(bm, bevel_verts, pop_lens)
        add_seat(bm)
        n_det = len(bm.verts)
        add_details(bm, bevel_verts)
        if odd_hull:
            # the fuselage bows, and everything laid on its skin with it
            bm.verts.ensure_lookup_table()
            bow([bm.verts[i] for i in range(n_hull)]
                + [bm.verts[i] for i in range(n_det, len(bm.verts))])

        if bevel_offset > 0.0:
            # Chamfer the prism plates' rims, one pass per material with
            # material= set, over sorted edges.
            for mat_idx in (GRAPHITE_IDX, METAL_IDX, ACCENT_IDX, LIGHT_IDX):
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
        # Fuselage, shrouds, tubes, blades and lathes are smooth-shaded;
        # grilles, chamfers, pleat seams and ribs stay crisp through sharp edges.
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


def _math(nt, op, a, b=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    if isinstance(a, float):
        n.inputs[0].default_value = a
    else:
        nt.links.new(a, n.inputs[0])
    if b is not None:
        if isinstance(b, float):
            n.inputs[1].default_value = b
        else:
            nt.links.new(b, n.inputs[1])
    return n.outputs["Value"]


def metal(name, color, roughness, env, stops, roughness_var=0.06, noise_scale=60.0):
    """Metal with a studio carried in the material (copied from
    showcase/road-bicycle, after espresso-machine). On a dark stage a metal
    mirrors the dark stage and reads as grey plastic; here the world-space
    reflection vector looks up a soft studio — a bright horizon band, a dim
    ceiling, the floor dark only straight down, the key's side brighter —
    added as emission, so gunmetal and chrome read as metal in the hero and
    on the asset sheet alike."""
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


# a muted teal: the fleet's contact-sheet saturation band holds it
LIVERY_RGB = (0.058, 0.196, 0.208, 1.0)


def bike_materials():
    """(livery, graphite, metal, rubber, leather, light, glass, accent,
    carbon, chrome): shared by the check and the render.

    The livery is a muted teal metallic paint under a clear coat, with twin
    pearl racing stripes either side of the centreline (object-space Y); the
    belly, inner shroud walls, grilles, pads, gaskets and wear strips a dark
    composite; the gear, skid shoes, vanes and clamps gunmetal with the
    studio term; grips, boots, conduits and pegs rubber; the saddle espresso
    leather; the lights emit by object-space X: warm white at the headlight,
    cyan on the screen, blue plasma in the nozzles, red on the rear shroud
    and — by object-space |Y| as well — on the tail light between the
    nozzles; the lens and windscreen smoked glass; spinners, levers, caps,
    collars and bands orange anodised aluminium; the blades glossy carbon;
    stanchions, shock rods and pins chrome.
    """
    livery = principled("BikeLivery", LIVERY_RGB, 0.45, 0.30,
                        roughness_var=0.05, noise_scale=24.0, coat=0.7)
    nt = livery.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
    ay = _math(nt, "ABSOLUTE", sep.outputs["Y"])
    stripe = _math(nt, "MULTIPLY", _math(nt, "GREATER_THAN", ay, 0.014),
                   _math(nt, "LESS_THAN", ay, 0.042))
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = LIVERY_RGB
    mix.inputs[7].default_value = (0.78, 0.78, 0.75, 1.0)
    nt.links.new(stripe, mix.inputs[0])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    graphite = principled("BikeComposite", (0.042, 0.044, 0.050, 1.0), 0.0, 0.46,
                          roughness_var=0.08, mottle=0.15, noise_scale=70.0)
    gunmetal = metal("BikeGunmetal", (0.36, 0.37, 0.39, 1.0), 0.30, 0.34,
                     [(0.0, 0.03), (0.18, 0.05), (0.30, 0.20), (0.40, 0.60), (0.48, 1.0),
                      (0.60, 0.40), (0.80, 0.25), (1.0, 0.18)], noise_scale=90.0)
    rubber = principled("BikeRubber", (0.021, 0.021, 0.023, 1.0), 0.0, 0.74,
                        roughness_var=0.08, noise_scale=80.0)
    leather = principled("BikeSaddle", (0.040, 0.030, 0.026, 1.0), 0.0, 0.46,
                         roughness_var=0.12, mottle=0.30, noise_scale=140.0)
    light = principled("BikeLights", (1.0, 1.0, 1.0, 1.0), 0.0, 0.25)
    nt = light.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    _emission(bsdf, (1.0, 1.0, 1.0, 1.0), 7.0)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
    fac = _math(nt, "MULTIPLY_ADD", sep.outputs["X"], 1.0 / 2.4)
    nt.nodes[-1].inputs[2].default_value = 0.5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    els[0].position = 0.0
    els[0].color = (1.0, 0.05, 0.03, 1.0)          # rear marker, x < -0.9
    els[1].position = 0.125
    els[1].color = (0.20, 0.55, 1.0, 1.0)          # nozzle plasma
    e2 = els.new(0.5833)
    e2.color = (0.30, 0.92, 1.0, 1.0)              # screen
    e3 = els.new(0.675)
    e3.color = (1.0, 0.93, 0.80, 1.0)              # headlight and front marker
    nt.links.new(fac, ramp.inputs["Fac"])
    # the tail light sits between the nozzles: aft of x -0.30 and inside
    # |y| 0.046, where no nozzle core reaches (theirs start at |y| 0.0485)
    tail = _math(nt, "MULTIPLY", _math(nt, "LESS_THAN", sep.outputs["X"], -0.30),
                 _math(nt, "LESS_THAN", _math(nt, "ABSOLUTE", sep.outputs["Y"]), 0.046))
    red = nt.nodes.new("ShaderNodeMix")
    red.data_type = "RGBA"
    nt.links.new(tail, red.inputs[0])
    nt.links.new(ramp.outputs["Color"], red.inputs[6])
    red.inputs[7].default_value = (1.0, 0.05, 0.03, 1.0)
    nt.links.new(red.outputs[2], bsdf.inputs["Base Color"])
    for key in ("Emission Color", "Emission"):
        if key in bsdf.inputs:
            nt.links.new(red.outputs[2], bsdf.inputs[key])
            break
    glass = principled("BikeSmokedGlass", (0.040, 0.075, 0.095, 1.0), 0.25, 0.03, coat=1.0)
    accent = principled("BikeAnodised", (0.88, 0.25, 0.025, 1.0), 1.0, 0.30,
                        roughness_var=0.06, noise_scale=60.0)
    carbon = principled("BikeCarbon", (0.026, 0.027, 0.030, 1.0), 0.0, 0.26,
                        roughness_var=0.06, mottle=0.12, noise_scale=160.0, coat=0.8)
    chrome = metal("BikeChrome", (0.90, 0.90, 0.92, 1.0), 0.10, 0.80,
                   [(0.0, 0.01), (0.30, 0.02), (0.38, 0.90), (0.47, 1.0), (0.53, 0.06),
                    (0.66, 0.08), (0.74, 0.75), (0.88, 0.60), (1.0, 0.20)],
                   roughness_var=0.03, noise_scale=70.0)
    return livery, graphite, gunmetal, rubber, leather, light, glass, accent, carbon, chrome


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
    def __init__(self, me, idx, verts, polys, tags=None):
        self.idx = idx
        codes = {}
        for p in polys:
            c = tags[p.index] if tags else 0
            codes[c] = codes.get(c, 0) + 1
        code = max(codes, key=codes.get) if codes else 0
        self.role, self.unit = code // 100, code % 100
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


def _annulus_about_mean(s, r_min, r_max):
    d = [math.hypot(p.x - s.mean.x, p.y - s.mean.y) for p in s.pts]
    return min(d) > r_min and max(d) < r_max


def lathe_axis(pts):
    """A turned part's axis (copied from showcase/cargo-loader): the
    eigenvector whose eigenvalue stands apart from the other two (its radial
    pair is equal by symmetry), so it holds for a long pin and a short, wide
    bushing alike."""
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    w, vecs = np.linalg.eigh(q.T @ q / len(p))
    if (w[2] - w[1]) > (w[1] - w[0]):
        return Vector(c), Vector(vecs[:, 2])
    return Vector(c), Vector(vecs[:, 0])


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    tags = [0] * len(me.polygons)
    if "part" in me.attributes:
        me.attributes["part"].data.foreach_get("value", tags)
    parts = [Shell(me, i, g, polys[i], tags) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    # the fuselage: the long two-tone shell; the shrouds: the two rings
    out["hull"] = next((s for s in parts if LIVERY_IDX in s.mats and GRAPHITE_IDX in s.mats
                        and 0.9 < s.size.x < 1.2), None)
    out["shrouds"] = sorted((s for s in parts if LIVERY_IDX in s.mats and GRAPHITE_IDX in s.mats
                             and 0.55 < s.size.x < 0.70 and 0.55 < s.size.y < 0.70
                             and s.size.z < 0.30), key=lambda s: -s.mean.x)
    # a turned hub's vertices all lie in an annulus about its own axis; a
    # 45-degree vane, whose AABB is just as square, reaches 0.11 m from its mean
    out["hubs"] = [s for s in parts if s.mat == METAL_IDX and 0.14 < s.size.x < 0.17
                   and abs(s.size.x - s.size.y) < 0.004 and s.size.z < 0.05
                   and _annulus_about_mean(s, 0.05, 0.085)]
    out["cans"] = [s for s in parts if s.mat == GRAPHITE_IDX and 0.12 < s.size.x < 0.14
                   and abs(s.size.x - s.size.y) < 0.004 and _annulus_about_mean(s, 0.015, 0.07)]
    out["blades"] = [s for s in parts if s.mat == CARBON_IDX]
    # the skids' ground contact is their wear strips
    out["skids"] = sorted((s for s in parts if s.role == R_STRIP), key=lambda s: s.unit)
    out["seat"] = next((s for s in parts if s.mat == LEATHER_IDX), None)
    for key, role in (("pins", R_PIN), ("bushings", R_BUSH), ("cyls", R_CYL), ("rods", R_ROD)):
        out[key] = {}
        for s in parts:
            if s.role == role:
                out[key].setdefault(s.unit, []).append(s)
    return out


def joint_audit(cls):
    """Every joint: one pin through three bushings; each bushing's centre on
    the pin's axis, its axis parallel to the pin's, its centre within the
    pin's span (after showcase/cargo-loader)."""
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
            worst_off = max(worst_off, (r - pa * along).length)
            worst_tilt = max(worst_tilt, math.degrees(math.acos(min(1.0, abs(ba.dot(pa))))))
            if not (lo < along < hi):
                bad.append((u, "span", round(along, 4)))
    return {"joints": len(units), "offset": worst_off, "tilt": worst_tilt, "bad": bad}


def shock_audit(cls):
    """Each shock: the rod coaxial with its barrel; the rod's length out of
    the gland, and its length still inside the barrel."""
    res = {"shocks": 0, "offset": 0.0, "tilt": 0.0, "exposed": [], "engage": []}
    for u in sorted(set(cls["cyls"]) | set(cls["rods"])):
        cyl = cls["cyls"].get(u, [])
        rod = cls["rods"].get(u, [])
        if len(cyl) != 1 or len(rod) != 1:
            continue
        res["shocks"] += 1
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


def fan_audit(cls):
    """Per fan: shroud axis (vertex mean of the lathe) and plumb (PCA), the
    rotor hub and motor can on that axis; blade tip clearance along the
    radial ray from the shroud axis to its inner wall; blades seated in the
    hub; blade count and angular gaps about the hub's own axis."""
    res = {"fans": len(cls["shrouds"]), "hub_axis": 9.0, "tilt": 90.0, "pitch": 0.0,
           "clear": [], "unseated": 0, "counts": [], "gap_err": [], "angles": [],
           "axis_y": 9.0}
    if len(cls["shrouds"]) != FAN_COUNT:
        return res
    offs, tilts, axes = [], [], []
    owned = [[] for _ in cls["shrouds"]]
    for bl in cls["blades"]:
        k = min(range(FAN_COUNT), key=lambda q: math.hypot(
            bl.mean.x - cls["shrouds"][q].mean.x, bl.mean.y - cls["shrouds"][q].mean.y))
        owned[k].append(bl)
    for k, sh in enumerate(cls["shrouds"]):
        cx, cy = sh.mean.x, sh.mean.y
        axes.append((cx, cy))
        _c, ax = pca_axis(sh.pts, largest=False)
        tilts.append(math.degrees(math.acos(min(1.0, abs(float(ax[2]))))))
        near = [h for h in cls["hubs"] + cls["cans"]
                if math.hypot(h.mean.x - cx, h.mean.y - cy) < 0.1]
        if len(near) != 2:
            offs.append(9.0)
        for h in near:
            offs.append(math.hypot(h.mean.x - cx, h.mean.y - cy))
        hub = min(cls["hubs"], key=lambda h: math.hypot(h.mean.x - cx, h.mean.y - cy),
                  default=None)
        clear = 9.0
        angs = []
        for bl in owned[k]:
            if hub is None or not bl.tree.overlap(hub.tree):
                res["unseated"] += 1
            for p in bl.pts:
                o = Vector((cx, cy, p.z))
                d = Vector((p.x - cx, p.y - cy, 0.0))
                r = d.length
                if r < 0.18:
                    continue
                hit, _n, _i, dist = sh.tree.ray_cast(o, d.normalized())
                wall = dist if hit is not None else 9.0
                clear = min(clear, wall - r)
            # spacing is the rotor's own: angles about its hub's axis, so a
            # rotor shifted off the shroud axis is exit 17's alone
            hx, hy = (hub.mean.x, hub.mean.y) if hub is not None else (cx, cy)
            angs.append(math.degrees(math.atan2(bl.mean.y - hy, bl.mean.x - hx)) % 360.0)
        angs.sort()
        n = len(angs)
        gaps = [((angs[(q + 1) % n] - angs[q]) % 360.0) for q in range(n)] if n else []
        res["clear"].append(clear)
        res["counts"].append(n)
        res["gap_err"].append(max((abs(g - 360.0 / BLADES_PER_FAN) for g in gaps), default=0.0))
        res["angles"].append([round(a, 3) for a in angs])
    res["hub_axis"] = max(offs)
    res["tilt"] = max(tilts)
    res["pitch"] = math.hypot(axes[0][0] - axes[1][0], axes[0][1] - axes[1][1])
    res["axis_y"] = max(abs(a[1]) for a in axes)
    return res


def mirror_audit(cls):
    """Every hull vertex against its mirror partner across y = 0."""
    hull = cls["hull"]
    if hull is None:
        return 9.0
    kd = KDTree(len(hull.pts))
    for i, p in enumerate(hull.pts):
        kd.insert(p, i)
    kd.balance()
    worst = 0.0
    for p in hull.pts:
        _co, _i, d = kd.find(Vector((p.x, -p.y, p.z)))
        worst = max(worst, d)
    return worst


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


def stance_audit(cls):
    """Mass centre against the convex hull of both skids' soles."""
    total = 0.0
    mom = Vector()
    for s in cls["all"]:
        if s.mat is None:
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * (HULL_DENSITY if s is cls["hull"] else DENSITY[s.mat])
        total += m
        mom += m * cen
    com = mom / total
    # each skid's own sole (its lowest vertices), whether or not it is
    # grounded: grounding is exit 16's job, the polygon's shape is this one's
    contact = [(p.x, p.y) for sk in cls["skids"] for p in sk.pts if p.z < sk.lo.z + 0.0005]
    margin = -1.0
    if len(contact) >= 3:
        hull = hull2d(contact)
        margin = 9.0
        for k in range(len(hull)):
            a, b = hull[k], hull[(k + 1) % len(hull)]
            ex, ey = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ex, ey)
            margin = min(margin, (ex * (com.y - a[1]) - ey * (com.x - a[0])) / ln)
    return {"mass": total, "com": com, "margin": margin}


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
    img = bpy.data.images.new("BikeNrm", size, size, alpha=True, float_buffer=False)
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


def check(skip_decimate, lift_z=False, stray_vert=False, float_skid=False, offset_hub=False,
          long_blades=False, odd_hull=False, skew_blade=False, narrow_skids=False,
          pop_lens=False, offset_pin=False, skew_rod=False, short_rod=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(float_skid=float_skid, offset_hub=offset_hub, long_blades=long_blades,
                 odd_hull=odd_hull, skew_blade=skew_blade, narrow_skids=narrow_skids,
                 pop_lens=pop_lens, offset_pin=offset_pin, skew_rod=skew_rod,
                 short_rod=short_rod)
    low = build_bike_mesh("HoverBikeLow", bevel_offset=0.0006, bevel_segments=1, **flags)
    high = build_bike_mesh("HoverBikeHigh", bevel_offset=0.0006, bevel_segments=3, **flags)
    mats = bike_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the composite: the grilles and pads are where the
    # high mesh's rounder chamfer differs from the low.
    target = mats[GRAPHITE_IDX]

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    none3 = (None, None, None)
    if low.data is None or len(low.data.polygons) < 6:
        return (fail("bike mesh did not build", 3),) + none3

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
    skids = [s.lo.z for s in cls["skids"]]
    fan = fan_audit(cls)
    mirror = mirror_audit(cls)
    hull = cls["hull"]
    hull_size = (hull.size.x, hull.size.y) if hull else (0.0, 0.0)
    seat_z = cls["seat"].hi.z if cls["seat"] else 0.0
    stance = stance_audit(cls)
    ncomp, comp_sizes = connected_components(cls)
    joints = joint_audit(cls)
    shocks = shock_audit(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("bike has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "HoverBikeLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "HoverBikeLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_bike_mesh("HoverBikeColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "HoverBikeCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_hover_bike_{os.getpid()}.glb")
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
    print(f"measured shells={len(cls['all'])} skids={len(skids)} "
          f"skid_zmin={[round(z, 5) for z in skids]}")
    print(f"measured fans={fan['fans']} hubs={len(cls['hubs'])} cans={len(cls['cans'])} "
          f"hub_axis={fan['hub_axis']:.6f} tilt={fan['tilt']:.4f} pitch={fan['pitch']:.5f}")
    print(f"measured blades={fan['counts']} unseated={fan['unseated']} "
          f"clear={[round(c, 5) for c in fan['clear']]} "
          f"gap_err={[round(g, 4) for g in fan['gap_err']]}")
    print(f"measured mirror={mirror:.6f} hull=({hull_size[0]:.4f},{hull_size[1]:.4f}) "
          f"seat_z={seat_z:.4f}")
    print(f"measured mass={stance['mass']:.3f}kg com=({stance['com'].x:.4f},"
          f"{stance['com'].y:.4f},{stance['com'].z:.4f}) margin={stance['margin']:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")
    print(f"measured joints={joints['joints']} pin_offset={joints['offset']:.6f} "
          f"pin_tilt={joints['tilt']:.4f} bad={joints['bad'][:4]}")
    print(f"measured shocks={shocks['shocks']} rod_offset={shocks['offset']:.6f} "
          f"rod_tilt={shocks['tilt']:.4f} exposed={[round(e, 4) for e in shocks['exposed']]} "
          f"engage={[round(e, 4) for e in shocks['engage']]}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + none3
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5),) + none3
    floors = ((LIVERY_IDX, LIVERY_FACES_MIN, "livery"),
              (GRAPHITE_IDX, GRAPHITE_FACES_MIN, "composite"),
              (METAL_IDX, METAL_FACES_MIN, "gunmetal"), (RUBBER_IDX, RUBBER_FACES_MIN, "rubber"),
              (LEATHER_IDX, LEATHER_FACES_MIN, "leather"), (LIGHT_IDX, LIGHT_FACES_MIN, "light"),
              (GLASS_IDX, GLASS_FACES_MIN, "glass"), (ACCENT_IDX, ACCENT_FACES_MIN, "anodised"),
              (CARBON_IDX, CARBON_FACES_MIN, "carbon"), (CHROME_IDX, CHROME_FACES_MIN, "chrome"))
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
    if len(skids) != SKID_COUNT or max(skids) > ZMIN_EPS:
        return (fail(f"skids: {len(skids)} (want {SKID_COUNT}), zmin per skid "
                     f"{[round(z, 5) for z in skids]} (each must be within {ZMIN_EPS} of 0)", 16),) + none3
    if (fan["fans"] != FAN_COUNT or len(cls["hubs"]) != FAN_COUNT
            or len(cls["cans"]) != FAN_COUNT or fan["hub_axis"] > HUB_AXIS_TOL
            or fan["tilt"] > AXIS_TILT_MAX_DEG
            or abs(fan["pitch"] - 2.0 * DUCT_X) > FAN_PITCH_TOL
            or fan["axis_y"] > HUB_AXIS_TOL):
        return (fail(f"fans not coaxial: hub/can off the shroud axis {fan['hub_axis']:.5f} m "
                     f"(tol {HUB_AXIS_TOL}), shroud tilt {fan['tilt']:.3f} deg, fan pitch "
                     f"{fan['pitch']:.5f} m, {fan['fans']} shrouds, {len(cls['hubs'])} hubs, "
                     f"{len(cls['cans'])} cans", 17),) + none3
    if fan["unseated"] or any(not (CLEAR_MIN <= c <= CLEAR_MAX) for c in fan["clear"]):
        return (fail(f"blade tip clearance {[round(c, 5) for c in fan['clear']]} not in "
                     f"[{CLEAR_MIN}, {CLEAR_MAX}], or {fan['unseated']} blades not in their hub", 18),) + none3
    if (mirror > MIRROR_EPS or abs(hull_size[0] - HULL_LEN) > SIZE_TOL
            or abs(hull_size[1] - HULL_WIDTH) > SIZE_TOL
            or abs(seat_z - SEAT_HEIGHT) > SIZE_TOL):
        return (fail(f"hull mirror deviation {mirror:.5f} m (eps {MIRROR_EPS}), or size off: "
                     f"hull {hull_size[0]:.4f} x {hull_size[1]:.4f}, seat {seat_z:.4f}", 19),) + none3
    if (any(n != BLADES_PER_FAN for n in fan["counts"])
            or any(g > SPACING_TOL_DEG for g in fan["gap_err"])):
        return (fail(f"blade spacing: counts {fan['counts']} (want {BLADES_PER_FAN}), worst gap "
                     f"error {[round(g, 3) for g in fan['gap_err']]} deg (tol {SPACING_TOL_DEG})", 20),) + none3
    if stance["margin"] < STANCE_MARGIN:
        return (fail(f"stance: mass centre {stance['margin']:.4f} m inside the skids' contact "
                     f"polygon < {STANCE_MARGIN}", 21),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 22),) + none3
    if (joints["joints"] != JOINT_COUNT or joints["bad"] or joints["offset"] > PIN_OFFSET_MAX
            or joints["tilt"] > PIN_TILT_MAX_DEG):
        return (fail(f"joints: {joints['joints']} (want {JOINT_COUNT}), {joints['bad'][:4]}, a "
                     f"bushing {joints['offset']:.6f} m off its pin's axis (cap {PIN_OFFSET_MAX}), "
                     f"tilt {joints['tilt']:.4f} deg (cap {PIN_TILT_MAX_DEG})", 24),) + none3
    if (shocks["shocks"] != SHOCK_COUNT or shocks["offset"] > ROD_OFFSET_MAX
            or shocks["tilt"] > ROD_TILT_MAX_DEG
            or any(not (EXPOSED_MIN <= e <= EXPOSED_MAX) for e in shocks["exposed"])
            or any(g < ENGAGE_MIN for g in shocks["engage"])):
        return (fail(f"shocks: {shocks['shocks']} (want {SHOCK_COUNT}), rod "
                     f"{shocks['offset']:.6f} m off its barrel's axis (cap {ROD_OFFSET_MAX}), tilt "
                     f"{shocks['tilt']:.4f} deg; exposed rod {[round(e, 4) for e in shocks['exposed']]} "
                     f"m (band {EXPOSED_MIN}-{EXPOSED_MAX}), engaged "
                     f"{[round(g, 4) for g in shocks['engage']]} m (floor {ENGAGE_MIN})", 25),) + none3
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

    # The house rig scaled to a 2.2 m vehicle: warm key upper left, cool
    # fill low right, cool rim behind, warm wedge pooled on the back wall.
    light("Key", (-2.2, -2.6, 2.6), 90.0, 1.4, (1.0, 0.93, 0.84), spread=30.0)
    light("Fill", (2.8, -1.9, 0.6), 17.0, 3.2, (0.72, 0.82, 1.0))
    light("Rim", (-1.0, 1.8, 1.6), 90.0, 1.2, (0.62, 0.78, 1.0))
    light("Wedge", (2.4, 2.4, 1.0), 180.0, 2.0, (1.0, 0.68, 0.38),
          target=(centre.x + 2.6, centre.y + WALL_Y, 0.55))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    view = Vector((-0.55, -0.83, 0.0)).normalized()
    cam.location = centre + view * 3.55 + Vector((0.0, 0.0, 1.55))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.07))
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
    # Standard, not AgX: AgX washes the teal livery and orange anodising toward pastel
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 23
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
    p.add_argument("--float-skid", action="store_true")
    p.add_argument("--offset-hub", action="store_true")
    p.add_argument("--long-blades", action="store_true")
    p.add_argument("--odd-hull", action="store_true")
    p.add_argument("--skew-blade", action="store_true")
    p.add_argument("--narrow-skids", action="store_true")
    p.add_argument("--pop-lens", action="store_true")
    p.add_argument("--offset-pin", action="store_true")
    p.add_argument("--skew-rod", action="store_true")
    p.add_argument("--short-rod", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_skid=args.float_skid,
        offset_hub=args.offset_hub,
        long_blades=args.long_blades,
        odd_hull=args.odd_hull,
        skew_blade=args.skew_blade,
        narrow_skids=args.narrow_skids,
        pop_lens=args.pop_lens,
        offset_pin=args.offset_pin,
        skew_rod=args.skew_rod,
        short_rod=args.short_rod,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("hover-bike OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
