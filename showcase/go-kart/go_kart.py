"""Game-ready go-kart on a patch of kart track - a showcase piece, not an example.

Asserts budget conformance of a procedural rental/racing go-kart after
composing shipped pipeline pieces: bmesh construction, UVs, fourteen
materials, high-to-low normal bake, LOD chain, convex collider, Unity glTF
export.

A patch of kart-track asphalt, broken on three edges, runs up to a red and
white kerb along the fourth. On it stands a go-kart (generic, no marks or
text): a bent-tube chassis whose main loop is one bar swept through every
bend, cross tubes that end inside the rails, welded gussets, bearing hangers,
kingpin brackets and a steering-column support; a floor tray; a moulded seat
on stays; a steering wheel on a raked column in a bushing, a steering plate
and two tie rods to the spindles' arms; spindles on kingpins with caster;
blue moulded bodywork: a nose cone on bumper bars ahead of the front axle
(a raised hump, lipped shoulders, a rounded chin), a curved front panel
leaning back from the hump with a plain white number plate, and two side
pods (a raised outer crest, a stepped deck with grip ribs, a groove along
the wall) on nerf bars; ten flat strap brackets welded to the tubes and
bolted flat to the mouldings; a tubular rear bumper; a small engine (finned
cylinder, fan shroud and pull-start, air-box, exhaust and silencer) clamped
to the right rail, driving a live rear axle through a clutch, a chain and a
sprocket; bearing carriers, a brake disc and caliper, a master cylinder
pushed by the brake pedal with its hose along the left rail to the caliper,
the throttle cable along the right rail to the carburettor, a fuel tank with
its line, a lead ballast block; and four slick tyres on split rims with
valve stems, the fronts narrower than the rears.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates one named budget:
``--skip-decimate`` the LOD band, ``--stray-vert`` mesh hygiene, ``--lift-z``
and ``--float-tyre`` grounding, ``--cock-hub``, ``--drop-bearing`` and
``--short-tierod`` joint fit, ``--sink-tyre`` and ``--lift-chain`` seat
conformance, ``--toe-wheel``, ``--wide-track``, ``--odd-frame`` and
``--no-caster`` mirror, size and angle, ``--aft-ballast`` the stance,
``--loose-ballast`` one connected assembly and ``--float-nose`` the
bodywork brackets.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts are
not byte-identical across Blender versions - the LOD gate is a ratio band.

    blender --background --python go_kart.py --
    blender --background --python go_kart.py -- --skip-decimate
    blender --background --python go_kart.py -- --output kart.png
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

# --- Track patch (world frame) -------------------------------------------------
SLAB_T = 0.060
SLAB_X = 0.935               # half length
SLAB_Y0 = -0.850             # front edge (broken)
SLAB_Y1 = 0.650              # back edge: straight, against the kerb
SLAB_CORNER = 0.120
SLAB_PERIM = 132
SLAB_JITTER = 0.016
SLAB_TOP_CH = 0.008
SLAB_BOT_CH = 0.004
KERB_HALF_L = 0.925          # stops short of the slab's sides: no shared end plane
KERB_W = 0.260
KERB_H = 0.032               # crest above the asphalt
KERB_BITE = 0.012            # the kerb's foot runs this far under the asphalt edge
KERB_STRIPES = 6
KERB_Z0 = 0.002              # underside: off the slab's underside plane

# --- Kart layout (kart frame: x forward, y left, z up from the asphalt top) -----
KART_X = -0.050
KART_Y = -0.100
WHEELBASE = 1.040
TRACK_F = 1.100              # tyre centre to tyre centre
TRACK_R = 1.200
AX_F = 0.5 * WHEELBASE
AX_R = -0.5 * WHEELBASE
R_TF, R_TR = 0.128, 0.140    # 10 in front, 11 in rear slick
W_TF, W_TR = 0.061, 0.098    # half width over the sidewall bulge
WF_F, WF_R = 0.055, 0.092    # rim flange inner face, half width
DISC_F = (-0.006, 0.006)     # rim centre disc, w from the tyre's mid-plane (+ outboard)
DISC_R = (-0.064, -0.052)
BORE_F, BORE_R = 0.0215, 0.0285
RS = 0.0635                  # 5 in bead seat
RFL = 0.0715                 # flange top
RD = 0.0580                  # drop well
RIM_T = 0.0035
TYRE_BITE = 0.0010           # tyre bead hooped this far onto the bead seat
SINK = 0.0015                # contact patch pressed into the asphalt
FLAT = 0.0040                # tyre deflection under load: a flat patch
TYRE_SEGS = 64
RIM_SEGS = 48
Z_AF = R_TF - FLAT - SINK
Z_AR = R_TR - FLAT - SINK
AXLE_R = 0.020               # 40 mm live axle
AXLE_W = 0.5505

TUBE_R = 0.015               # 30 mm chassis tube
TUBE_SIDES = 16
Z_F = 0.052
LOOP_PTS = ((-0.66, 0.30), (-0.22, 0.30), (0.02, 0.235), (0.34, 0.235), (0.44, 0.33),
            (0.60, 0.33))
LOOP_FILLET = 0.07
LOOP_STEPS = 7
CROSS_R = 0.0125
X_MID = -0.120               # the seat's cross tube
X_COLX = 0.460               # the column's cross tube
HANGER_Y = 0.300
HANGER_T = 0.006

KP_Y = 0.400                 # kingpin centre, from the kart's centre line
CASTER_DEG = 14.0
KP_R = 0.013
KP_HALF = 0.040
WEB_Y = 0.346
ARM_END = (0.440, 0.365)
ARM_Z = 0.097
TAB_HOLE = (0.415, 0.038)
EYE_Z0 = ARM_Z + 0.0025      # eye bottom: 0.5 mm into the plate under it
EYE_H = 0.010

COL_B = Vector((0.460, 0.0, 0.080))
COL_T = Vector((0.130, 0.0, 0.470))
COL_R = 0.010
WHEEL_R = 0.145
SEAT_Y = 0.040

CHAIN_Y = -0.445
PITCH = 0.009525             # 3/8 in chain
N_ENG, N_AXLE = 12, 60
Z_ENG = 0.180
LINKS = 88
CH_PIN, CH_MID = 0.0045, 0.0034     # plate half heights at a pin and between pins
CH_IN, CH_OUT = 0.0050, 0.0064      # inner and outer link half widths
SPR_HALF_T = 0.0020
CYL_DEG = 25.0

BALLAST = (0.070, 0.250, 0.115, 0.205)   # x0, x1, y0, y1 on the floor tray
BALLAST_AFT = (-0.800, -0.620, 0.020, 0.110)
BALLAST_PLATES = 3
BALLAST_T = 0.015

# --- Falsifier sizes -------------------------------------------------------------
FLOAT_TYRE = 0.004           # --float-tyre: left front tyre
COCK_HUB = 0.0015            # --cock-hub: left rear hub off the axle
DROP_BEARING = 0.0020        # --drop-bearing: right bearing and carrier
SHORT_TIEROD = 0.006         # --short-tierod: left tie rod's outer eye
SINK_BITE = 0.0030           # --sink-tyre: right rear tyre's bead
LIFT_CHAIN = 0.0040          # --lift-chain: the chain off both sprockets (1.7, 2.0, 2.5,
                             # 3.0 and 3.5 mm each put a chain face within 0.1 mm of a
                             # tooth flat's plane and exited 15)
TOE_DEG = 1.5                # --toe-wheel: left front corner
WIDE_TRACK = 0.0040          # --wide-track: each rear wheel outward
ODD_FRAME = 0.0030           # --odd-frame: left rail bowed outward
LOOSE_BALLAST = 0.0030       # --loose-ballast: the ballast stack lifted off the tray
FLOAT_NOSE = 0.0030          # --float-nose: the nose and its bolts slid forward off its brackets

# Bodywork brackets: flat straps welded to a tube at one end and bolted flat
# against a moulding at the other.
BRACKET_T = 0.0030           # strap thickness
TUBE_BITE = 0.0020           # a strap's welded end sunk into its tube
TAB_BITE = 0.0010            # a strap's tab pressed into the moulding it is bolted to

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from the vertices.
OUTER_SIZE = (1.8950, 1.7738, 0.6397)
BASE_TRIS_MIN = 81000
BASE_TRIS_MAX = 82700
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 14
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 900
BAKE_RES = 1024
CAGE_EXTRUSION = 0.006

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
# Supports: four tyres, each pressed into the asphalt in a band, contact
# patches in one plane.
TYRE_COUNT = 4
SINK_MIN = 0.0008
SINK_MAX = 0.0030
PATCH_PLANE_MAX = 0.0001
# Joint fit: hubs coaxial with their stub axles and the axle; the axle
# through both bearings; each tie-rod eye on its pin and bearing on its plate.
COAX_MAX = 0.0003
COAX_DEG_MAX = 0.3
HUBS = 4
BEARINGS = 2
EYES = 4
EYE_OFF_MAX = 0.0005
EYE_BITE_MIN = 0.0002
EYE_BITE_MAX = 0.0015
# Seat conformance: tyre beads on the bead seats; the chain on its sprockets.
TYRE_SEAT_MIN = 0.0004
TYRE_SEAT_MAX = 0.0020
CHAIN_SEAT_MIN = 0.0008
CHAIN_SEAT_MAX = 0.0030
CHAINLINE_MAX = 0.0005
SPROCKETS = 2
# Mirror, size and angle.
MIRROR_EPS = 0.0005
WHEEL_MIRROR_EPS = 0.0005
SIZE_TOL = 0.004
CASTER_MIN = 10.0
CASTER_MAX = 18.0
KINGPINS = 2
# Bodywork brackets: every strap bites both the tube it is welded to and the
# moulding it is bolted to.
BRACKETS = 10
BRACKET_BITE_MIN = 0.0005
BRACKET_BITE_MAX = 0.0025
# Stance: the mass centre stands inside the tyres' support polygon by at
# least 30 % of the wheelbase.
STANCE_MARGIN = 0.30 * WHEELBASE
DENSITY = (1900.0, 3000.0, 450.0, 120.0, 1700.0, 1600.0, 1500.0, 5000.0, 250.0, 500.0,
           11340.0, 0.0, 0.0, 950.0)

HERO_YAW_DEG = 0.0
CAM_VIEW = (0.62, -0.78)
CAM_DIST = 3.95
CAM_LENS = 50.0
CAM_LIFT = 1.75
AIM_OFFSET = (0.0, 0.0, -0.26)
WALL_Y = 5.0

PAINT_IDX = 0
CHROME_IDX = 1
RUBBER_IDX = 2
BODY_IDX = 3
SEAT_IDX = 4
ALU_IDX = 5
CASTING_IDX = 6
STEEL_IDX = 7
BLACK_IDX = 8
TANK_IDX = 9
LEAD_IDX = 10
ASPHALT_IDX = 11
KERB_IDX = 12
PLATE_IDX = 13

FACE_FLOORS = {
    PAINT_IDX: 2910, CHROME_IDX: 6430, RUBBER_IDX: 7530, BODY_IDX: 3410, SEAT_IDX: 1420,
    ALU_IDX: 11650, CASTING_IDX: 1760, STEEL_IDX: 3790, BLACK_IDX: 1550, TANK_IDX: 158,
    LEAD_IDX: 154, ASPHALT_IDX: 590, KERB_IDX: 115, PLATE_IDX: 114,
}
MAT_LABELS = ("frame paint", "chrome", "rubber", "bodywork", "seat", "aluminium",
              "engine casting", "steel", "black plastic", "fuel tank", "lead", "asphalt",
              "kerb paint", "number plate")

# Part tags: a face attribute naming which part a face belongs to, so the
# audits can find the shells they measure. Every measured value is read from
# the vertices, never from these constants.
(T_NONE, T_SLAB, T_KERB, T_LOOP, T_FRAME, T_TYRE, T_RIM, T_HUB_F, T_HUB_R, T_STUB,
 T_AXLE, T_BEARING, T_KINGPIN, T_ARM, T_TAB, T_PIN, T_EYE, T_CHAIN, T_SPROCKET,
 T_BODY, T_BALLAST, T_SEAT, T_BAR, T_BRACKET) = range(24)

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
# Construction helpers (copied from showcase/road-bicycle and
# showcase/traffic-cones, not imported)
# --------------------------------------------------------------------------

class Build:
    """The bmesh under construction, its part-tag and tone layers and named
    vertex groups (for the falsifiers that move one assembly)."""

    def __init__(self, bm):
        self.bm = bm
        self.tag = bm.faces.layers.int.new("part")
        self.tone = bm.faces.layers.float.new(TONE)
        self.groups = {}

    def part(self, tag=T_NONE, tone=0.5, *groups):
        return _Part(self, tag, tone, groups)

    def verts(self, *names):
        out = []
        for n in names:
            out.extend(self.groups.get(n, []))
        return out


class _Part:
    def __init__(self, b, tag, tone, groups):
        self.b, self.t, self.tone, self.g = b, tag, tone, groups

    def __enter__(self):
        self.nf = len(self.b.bm.faces)
        self.nv = len(self.b.bm.verts)
        return self

    def __exit__(self, *exc):
        bm = self.b.bm
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        for i in range(self.nf, len(bm.faces)):
            bm.faces[i][self.b.tag] = self.t
            bm.faces[i][self.b.tone] = self.tone
        vs = [bm.verts[i] for i in range(self.nv, len(bm.verts))]
        for g in self.g:
            self.b.groups.setdefault(g, []).extend(vs)
        return False


def _mark(faces, mat_idx):
    for f in faces:
        f.material_index = mat_idx
    return faces


def frame(ez, ex_hint):
    """Rotation whose local Z is ``ez`` and local X is ``ex_hint`` made
    orthogonal to it (columns ex, ey, ez; right-handed)."""
    ez = Vector(ez).normalized()
    ex = Vector(ex_hint)
    ex = (ex - ez * ex.dot(ez)).normalized()
    ey = ez.cross(ex)
    return Matrix((ex, ey, ez)).transposed()


def any_perp(v):
    v = Vector(v).normalized()
    return X if abs(v.x) < 0.9 else Y


def add_lathe(bm, profile, segs, mat_idx, center=(0.0, 0.0, 0.0), rot=None, phase=0.0,
              solid=False):
    """Revolve a profile [(r, z), ...] about local Z. ``solid``: an open
    polyline closed by n-gon caps at its two ends; otherwise a closed
    polygon revolved into a ring shell."""
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


def lathe_on(bm, profile, segs, mat_idx, center, axis, phase=0.0, solid=True, ref=None):
    axis = Vector(axis).normalized()
    return add_lathe(bm, profile, segs, mat_idx, center=center,
                     rot=frame(axis, ref if ref is not None else any_perp(axis)),
                     phase=phase, solid=solid)


_HEX = [0]


def add_hex(bm, center, axis, a, b, r, mat_idx, phase=0.0):
    """A hex head or nut on ``axis`` from a to b, its top edge chamfered.
    Every head is turned a further step: identical heads in a row would
    otherwise put their flats on shared planes."""
    _HEX[0] += 1
    ch = min(0.0008, 0.25 * (b - a))
    return lathe_on(bm, [(r, a), (r, b - ch), (r * 0.86, b)], 6, mat_idx, center, axis,
                    phase=phase + math.pi / 6.0 + 0.2113 * _HEX[0])


def add_dome(bm, center, axis, mat_idx, r=0.0065, h=0.0038, sink=0.0008, segs=12):
    """Button-head fastener: base sunk into the host, domed head."""
    prof = [(r, -sink), (r, 0.0008), (r * 0.86, 0.0022), (r * 0.55, 0.0033), (r * 0.18, h)]
    return lathe_on(bm, prof, segs, mat_idx, center, axis)


def add_rod(bm, center, axis, a, b, r, mat_idx, segs=12):
    return lathe_on(bm, [(r, a), (r, b)], segs, mat_idx, center, axis)


def add_tube(bm, pts, radius, sides, mat_idx, phase=0.0, ref=None):
    """Capped round bar swept along a polyline (parallel-transport frames)."""
    pts = [Vector(p) for p in pts]
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    if ref is None:
        ref = Z if abs(tans[0].z) < 0.9 else X
    nrm = (Vector(ref) - tans[0] * Vector(ref).dot(tans[0])).normalized()
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


def add_tube_loop_xy(bm, pts, radius, sides, mat_idx):
    """A closed round bar swept round a loop lying in a level plane: every
    ring is framed by the level normal and the loop's own tangent."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rings = []
    for i, p in enumerate(pts):
        t = (pts[(i + 1) % n] - pts[i - 1]).normalized()
        side = t.cross(Z).normalized()
        rings.append([bm.verts.new(p + radius * (Z * math.cos(2.0 * math.pi * k / sides)
                                                 + side * math.sin(2.0 * math.pi * k / sides)))
                      for k in range(sides)])
    faces = []
    for i in range(n):
        r0, r1 = rings[i], rings[(i + 1) % n]
        for k in range(sides):
            m = (k + 1) % sides
            faces.append(bm.faces.new((r0[k], r0[m], r1[m], r1[k])))
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


def chamfered(h, c):
    """A slab profile [(inset, z)] from 0 to h with chamfer c at both faces."""
    return [(c, 0.0), (0.0, c), (0.0, h - c), (c, h)]


def add_prism(bm, outline, w0, w1, origin, rot, mat_idx, ch=0.0):
    """Planar outline [(u, v)] extruded along local Z from w0 to w1, both
    faces chamfered by ``ch`` (an inset ring) when it is non-zero."""
    o = Vector(origin)
    if ch > 0.0:
        inner = inset_poly(outline, ch)
        layers = [(inner, w0), (outline, w0 + ch), (outline, w1 - ch), (inner, w1)]
    else:
        layers = [(outline, w0), (outline, w1)]
    rings = [[bm.verts.new(o + rot @ Vector((u, v, w))) for u, v in loop] for loop, w in layers]
    n = len(outline)
    faces = []
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(n):
            faces.append(bm.faces.new((r0[i], r0[(i + 1) % n], r1[(i + 1) % n], r1[i])))
    faces.append(bm.faces.new(tuple(reversed(rings[0]))))
    faces.append(bm.faces.new(tuple(rings[-1])))
    _mark(faces, mat_idx)
    return [v for ring in rings for v in ring]


def poly_area(poly):
    n = len(poly)
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
                     for i in range(n))


def inset_poly(poly, d):
    """Every vertex of a (convex-ish) polygon moved ``d`` inward along its
    bisector."""
    n = len(poly)
    sgn = 1.0 if poly_area(poly) > 0.0 else -1.0
    out = []
    for i in range(n):
        a, p, b = Vector(poly[i - 1]), Vector(poly[i]), Vector(poly[(i + 1) % n])
        e0 = (p - a).normalized()
        e1 = (b - p).normalized()
        n0 = Vector((-e0.y, e0.x)) * sgn
        n1 = Vector((-e1.y, e1.x)) * sgn
        bis = (n0 + n1)
        if bis.length < 1e-9:
            bis = n0
        bis.normalize()
        cosh = max(0.3, bis.dot(n0))
        q = p + bis * (d / cosh)
        out.append((q.x, q.y))
    return out


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


def fillet_loop(pts, rf, steps=4):
    pts = [Vector(p) for p in pts]
    n = len(pts)
    out = []
    for i in range(n):
        a, p, b = pts[i - 1], pts[i], pts[(i + 1) % n]
        r = min(rf, (a - p).length * 0.45, (b - p).length * 0.45)
        p0 = p + (a - p).normalized() * r
        p1 = p + (b - p).normalized() * r
        for k in range(steps + 1):
            t = k / steps
            out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * p + t * t * p1)
    return out


def add_bar(bm, pts, wax, half_w, half_t, rc, mat_idx, fillet=0.008, filleted=False):
    """Flat bar: its width lies along ``wax``, its thickness across it;
    rounded-rectangle section."""
    pts = [Vector(p) for p in pts] if filleted else fillet_path(pts, fillet)
    if not isinstance(wax, list):
        wax = Vector(wax).normalized()
    sec = rrect(half_w, half_t, rc, 2)
    waxes = [Vector(w).normalized() for w in wax] if isinstance(wax, list) else None
    rings = []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        t = (b - a).normalized()
        if waxes is not None:
            wax = waxes[i]
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


def rpoly(pts, r, n):
    """A convex polygon with every corner rounded by a quadratic fillet of
    ``n`` steps (n + 1 points per corner)."""
    pts = [Vector(p) for p in pts]
    m = len(pts)
    out = []
    for i in range(m):
        a, p, b = pts[i - 1], pts[i], pts[(i + 1) % m]
        rr = min(r, (a - p).length * 0.45, (b - p).length * 0.45)
        p0 = p + (a - p).normalized() * rr
        p1 = p + (b - p).normalized() * rr
        for k in range(n + 1):
            t = k / n
            q = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p + t * t * p1
            out.append((q.x, q.y))
    return out


def tri_short(bm, faces):
    """Split non-planar quads along their short diagonals: a fixed split is
    not mirror-symmetric, and a fastener aimed at one triangulation floats
    over the other."""
    quads = [f for f in faces if f.is_valid and len(f.verts) == 4]
    if quads:
        bmesh.ops.triangulate(bm, faces=quads, quad_method="SHORT_EDGE")


def add_loft(bm, loops, mat_idx):
    """Closed loops [[Vector]] of equal length lofted in order, n-gon caps."""
    rings = [[bm.verts.new(p) for p in loop] for loop in loops]
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
    return [v for row in front + back for v in row]


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


def circles_hull(circles, n=16):
    pts = []
    for u, v, r in circles:
        for k in range(n):
            a = 2.0 * math.pi * (k + 0.5) / n
            pts.append((u + r * math.cos(a), v + r * math.sin(a)))
    return hull2d(pts)


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


def pchip(keys):
    """Monotone cubic through (x, y) keys (Fritsch-Carlson): no overshoot."""
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


def resample(pts, n):
    """``n`` points evenly spaced by arc length along a polyline."""
    pts = [Vector(p) for p in pts]
    seg = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    lens = [(b - a).length for a, b in seg]
    total = sum(lens)
    out = []
    for k in range(n):
        s = total * k / (n - 1)
        acc = 0.0
        for (a, b), ln in zip(seg, lens):
            if acc + ln >= s - 1e-12 or ln == lens[-1]:
                t = 0.0 if ln < 1e-12 else min(1.0, max(0.0, (s - acc) / ln))
                out.append(a + (b - a) * t)
                break
            acc += ln
    return out


# --------------------------------------------------------------------------
# The track patch and the kerb (world frame)
# --------------------------------------------------------------------------

def _edge(a, b, n):
    return [a + (b - a) * (k / n) for k in range(n)]


def slab_outline():
    """Counter-clockwise from the back-left corner: the left side, the
    rounded front corners and the front edge, the right side, then the
    straight back edge. A closed-form jitter pushes the three open edges
    along their normal and fades to nothing toward the kerb, so the back
    edge and both back corners stay exact."""
    x0, x1, y0, y1, rc = -SLAB_X, SLAB_X, SLAB_Y0, SLAB_Y1, SLAB_CORNER
    pts = _edge(Vector((x0, y1)), Vector((x0, y0 + rc)), 22)
    for k in range(9):
        a = math.pi + 0.5 * math.pi * k / 8.0
        pts.append(Vector((x0 + rc + rc * math.cos(a), y0 + rc + rc * math.sin(a))))
    pts += _edge(Vector((x0 + rc, y0)), Vector((x1 - rc, y0)), 40)[1:]
    for k in range(9):
        a = 1.5 * math.pi + 0.5 * math.pi * k / 8.0
        pts.append(Vector((x1 - rc + rc * math.cos(a), y0 + rc + rc * math.sin(a))))
    pts += _edge(Vector((x1, y0 + rc)), Vector((x1, y1)), 22)[1:]
    pts.append(Vector((x1, y1)))
    pts += _edge(Vector((x1, y1)), Vector((x0, y1)), 30)[1:]
    n = len(pts)
    out = []
    for k, p in enumerate(pts):
        t = (pts[(k + 1) % n] - pts[k - 1]).normalized()
        nrm = Vector((t.y, -t.x))
        s = k / n
        fade = min(1.0, max(0.0, (y1 - 0.02 - p.y) / 0.30))
        j = SLAB_JITTER * fade * (0.50 * math.sin(2 * math.pi * 3 * s + 0.4)
                                  + 0.30 * math.sin(2 * math.pi * 7 * s + 1.3)
                                  + 0.20 * math.sin(2 * math.pi * 19 * s + 2.1))
        out.append(p + nrm * j)
    return out


def inset_ring(base, inset):
    out = []
    n = len(base)
    sgn = 1.0 if poly_area([(p.x, p.y) for p in base]) > 0.0 else -1.0
    for k, p in enumerate(base):
        t = (base[(k + 1) % n] - base[k - 1]).normalized()
        nrm = Vector((-t.y, t.x)) * sgn
        out.append(p + nrm * inset)
    return out


def build_slab(b):
    base = slab_outline()
    with b.part(T_SLAB, 0.5):
        rings_2d = [(inset_ring(base, SLAB_BOT_CH), 0.0), (base, SLAB_BOT_CH),
                    (base, SLAB_T - SLAB_TOP_CH), (inset_ring(base, SLAB_TOP_CH), SLAB_T)]
        loops = [[Vector((p.x, p.y, z)) for p in ring] for ring, z in rings_2d]
        add_loft(b.bm, loops, ASPHALT_IDX)


def kerb_profile():
    """The kerb's section (y, z) in world: a foot tucked under the asphalt's
    chamfered edge, a smooth ramp to a rounded crest, a short fall to the
    grass side."""
    y1, t, h = SLAB_Y1, SLAB_T, KERB_H
    return [(y1 - KERB_BITE, KERB_Z0), (y1 + KERB_W, KERB_Z0),
            (y1 + KERB_W, t - 0.014), (y1 + KERB_W - 0.006, t + 0.004),
            (y1 + KERB_W - 0.020, t + 0.016), (y1 + KERB_W - 0.050, t + h * 0.86),
            (y1 + KERB_W - 0.090, t + h), (y1 + 0.160, t + h * 0.93),
            (y1 + 0.110, t + h * 0.74), (y1 + 0.060, t + h * 0.42),
            (y1 + 0.020, t + 0.0055), (y1 - 0.004, t + 0.0008),
            (y1 - KERB_BITE, t - 0.004)]


def build_kerb(b):
    prof = kerb_profile()
    xs = [-KERB_HALF_L + 2.0 * KERB_HALF_L * k / KERB_STRIPES for k in range(KERB_STRIPES + 1)]
    bm = b.bm
    # the ends are chamfered by a pulled-in ring
    cy = sum(p[0] for p in prof) / len(prof)
    cz = sum(p[1] for p in prof) / len(prof)

    def ring(x, pull=0.0):
        return [bm.verts.new((x, y + (cy - y) * pull, z + (cz - z) * pull)) for y, z in prof]

    stations = [(-KERB_HALF_L, 0.06), (-KERB_HALF_L + 0.004, 0.0)]
    stations += [(x, 0.0) for x in xs[1:-1]]
    stations += [(KERB_HALF_L - 0.004, 0.0), (KERB_HALF_L, 0.06)]
    painted = []
    with b.part(T_KERB, 0.5):
        rings = [ring(x, pull) for x, pull in stations]
        n = len(prof)
        for k, (r0, r1) in enumerate(zip(rings, rings[1:])):
            xm = 0.5 * (stations[k][0] + stations[k + 1][0])
            stripe = min(KERB_STRIPES - 1, int((xm + KERB_HALF_L) / (2.0 * KERB_HALF_L) * KERB_STRIPES))
            for j in range(n):
                m = (j + 1) % n
                f = bm.faces.new((r0[j], r0[m], r1[m], r1[j]))
                f.material_index = KERB_IDX
                painted.append((f, 0.0 if stripe % 2 == 0 else 1.0))
        for f, stripe in ((bm.faces.new(tuple(reversed(rings[0]))), 0.0),
                          (bm.faces.new(tuple(rings[-1])), 1.0)):
            f.material_index = KERB_IDX
            painted.append((f, stripe))
    # the part context stamped every face with its tone: paint the stripes
    for f, stripe in painted:
        f[b.tone] = stripe


# --------------------------------------------------------------------------
# Chassis
# --------------------------------------------------------------------------

def loop_path(odd=0.0):
    left = [Vector((x, y, Z_F)) for x, y in LOOP_PTS]
    right = [Vector((x, -y, Z_F)) for x, y in reversed(LOOP_PTS)]
    pts = fillet_loop(left + right, LOOP_FILLET, LOOP_STEPS)
    # drop consecutive duplicates the fillets leave where arcs meet
    out = []
    for p in pts:
        if not out or (p - out[-1]).length > 1e-6:
            out.append(p)
    if (out[0] - out[-1]).length < 1e-6:
        out.pop()
    if odd:
        # --odd-frame: the left rail bowed outward over a short run
        for p in out:
            if p.y > 0.0 and -0.22 < p.x < 0.02:
                p.y += odd * math.cos(math.pi * (p.x + 0.10) / 0.24) ** 2
    return out


_LOOP = None


def rail_y(x):
    """The left rail's centre line at station ``x`` (default frame)."""
    global _LOOP
    if _LOOP is None:
        _LOOP = loop_path()
    pts = _LOOP
    n = len(pts)
    best = None
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        if a.y <= 0.05 or b.y <= 0.05:
            continue
        if (a.x - x) * (b.x - x) <= 0.0 and abs(b.x - a.x) > 1e-9:
            t = (x - a.x) / (b.x - a.x)
            y = a.y + (b.y - a.y) * t
            if best is None or y > best:
                best = y
    return best


def build_frame(b, flags):
    bm = b.bm
    with b.part(T_LOOP, 0.5, "kart"):
        add_tube_loop_xy(bm, loop_path(ODD_FRAME if flags["odd_frame"] else 0.0), TUBE_R,
                         TUBE_SIDES, PAINT_IDX)
    # cross tubes end on the rails' centre lines: their caps are inside the rails
    for x in (X_MID, X_COLX):
        ry = rail_y(x)
        with b.part(T_FRAME, 0.5, "kart"):
            add_tube(bm, [Vector((x, -ry, Z_F)), Vector((x, ry, Z_F))], CROSS_R, 14, PAINT_IDX)
        # welded gussets in the corners, level with the tube centres; the
        # fore and aft plates sit 0.2 mm apart in height
        for s in (-1.0, 1.0):
            for fore in (1.0, -1.0):
                xa = x + fore * 0.050
                ya = rail_y(xa)
                xe_ = x + fore * 0.003
                tri = [(xe_, ry), (xa, ya), (xe_, ry - 0.050)]
                tri = [(u, s * v) for u, v in tri]
                if poly_area(tri) < 0.0:
                    tri.reverse()
                dz = 0.0001 * fore
                with b.part(T_FRAME, 0.5, "kart"):
                    add_prism(bm, tri, Z_F - 0.0015 + dz, Z_F + 0.0015 + dz, (0.0, 0.0, 0.0),
                              Matrix.Identity(3), PAINT_IDX)
    # bearing hangers: plates on the rear rails, carrying the axle
    for s in (-1.0, 1.0):
        outline = circles_hull([(-0.585, Z_F - 0.004, 0.002), (-0.455, Z_F - 0.004, 0.002),
                                (AX_R, Z_AR, 0.057)], 24)
        rot = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))   # (u, v, w) -> (x, w, v)
        with b.part(T_FRAME, 0.5, "kart"):
            add_prism(bm, outline, s * HANGER_Y - HANGER_T / 2, s * HANGER_Y + HANGER_T / 2,
                      (0.0, 0.0, 0.0), rot, PAINT_IDX, ch=0.0008)
    # steering-column support: an inverted U off the rails
    ry = rail_y(0.300)
    u_pts = [Vector((0.300, ry, Z_F)), Vector((0.290, ry - 0.020, 0.140)),
             Vector((0.282, 0.120, 0.212)), Vector((0.282, -0.120, 0.212)),
             Vector((0.290, -(ry - 0.020), 0.140)), Vector((0.300, -ry, Z_F))]
    with b.part(T_FRAME, 0.5, "kart"):
        add_tube(bm, fillet_path(u_pts, 0.045, 6), CROSS_R, 14, PAINT_IDX)


def col_dir():
    return (COL_T - COL_B).normalized()


def col_point_x(x):
    d = col_dir()
    s = (x - COL_B.x) / d.x
    return COL_B + d * s


def col_point_z(z):
    d = col_dir()
    s = (z - COL_B.z) / d.z
    return COL_B + d * s


def build_steering_column(b):
    bm = b.bm
    d = col_dir()
    L = (COL_T - COL_B).length
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(COL_R * 0.8, -0.010), (COL_R, -0.008), (COL_R, L + 0.004),
                      (COL_R * 0.8, L + 0.006)], 16, CHROME_IDX, COL_B, d)
    # lower bearing block on the column cross tube
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(COL_R - 0.0005, -0.014), (0.018, -0.014), (0.020, -0.012),
                      (0.020, 0.012), (0.018, 0.014), (COL_R - 0.0005, 0.014)], 20, BLACK_IDX,
                 COL_B, d, solid=False)
    # bushing on the support: a bracket plate up from the U's top bar
    pb = col_point_x(0.282)
    rot = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))
    outline = circles_hull([(0.282, 0.212, 0.010), (pb.x, pb.z, 0.017)], 16)
    with b.part(T_FRAME, 0.5, "kart"):
        add_prism(bm, outline, -0.003, 0.003, (0.0, 0.0, 0.0), rot, PAINT_IDX, ch=0.0006)
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(COL_R - 0.0005, -0.022), (0.019, -0.022), (0.022, -0.019),
                      (0.022, 0.019), (0.019, 0.022), (COL_R - 0.0005, 0.022)], 20, BLACK_IDX,
                 pb, d, solid=False)
    # steering plate at the column's foot
    pz = col_point_z(ARM_Z)
    outline = circles_hull([(pz.x, 0.0, 0.017), (TAB_HOLE[0], TAB_HOLE[1], 0.012),
                            (TAB_HOLE[0], -TAB_HOLE[1], 0.012)], 16)
    with b.part(T_TAB, 0.5, "kart"):
        add_prism(bm, outline, ARM_Z - 0.003, ARM_Z + 0.003, (0.0, 0.0, 0.0),
                  Matrix.Identity(3), CHROME_IDX, ch=0.0006)
    # the wheel: a dished three-spoke wheel, grip, hub boss and its bolts
    c = COL_T + d * 0.004
    up = (Z - d * Z.dot(d)).normalized()
    rt = up.cross(d)
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(COL_R - 0.0005, -0.036), (0.024, -0.036), (0.030, -0.030),
                      (0.032, -0.004), (0.030, 0.002), (0.020, 0.004), (COL_R - 0.0005, 0.004)],
                 24, ALU_IDX, c, d, solid=False, ref=up)
    grip = []
    for k in range(12):
        a = 2.0 * math.pi * k / 12
        grip.append((WHEEL_R + 0.0105 * math.cos(a), 0.0145 * math.sin(a)))
    with b.part(T_NONE, 0.35, "kart"):
        add_lathe(bm, grip, 48, RUBBER_IDX, center=c, rot=frame(d, up))
    for ang in (0.0, 180.0, 270.0):
        a = math.radians(ang)
        rad = up * math.sin(a) + rt * math.cos(a)
        tan = d.cross(rad)
        with b.part(T_NONE, 0.5, "kart"):
            add_bar(bm, [c + rad * 0.026 - d * 0.018, c + rad * 0.080 - d * 0.010,
                         c + rad * (WHEEL_R - 0.004)], tan, 0.013, 0.0035, 0.002, ALU_IDX,
                    fillet=0.02)
    for k in range(6):
        a = 2.0 * math.pi * k / 6 + 0.3
        p = c + (up * math.sin(a) + rt * math.cos(a)) * 0.022 + d * (0.0032 + 0.0002 * k)
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, p, d, -0.0010, 0.0035, 0.0042, CHROME_IDX, phase=a)


def kp_axis(caster):
    c = math.radians(caster)
    return Vector((-math.sin(c), 0.0, math.cos(c)))


def kp_centre(s):
    return Vector((AX_F, s * KP_Y, Z_AF))


def arm_end(s):
    return Vector((ARM_END[0], s * ARM_END[1], ARM_Z))


def build_kingpin_brackets(b, caster):
    """C-brackets on the frame's front corners: a web welded to the rail and
    two lugs square to the kingpin; the kingpin bolt through them."""
    bm = b.bm
    a = kp_axis(caster)
    for s in (-1.0, 1.0):
        K = kp_centre(s)
        rot_web = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))
        web = rpoly([(0.486, Z_F - 0.006), (0.562, Z_F - 0.006), (0.552, 0.180), (0.472, 0.180)],
                    0.012, 3)
        if poly_area(web) < 0.0:
            web.reverse()
        with b.part(T_FRAME, 0.5, "kart"):
            add_prism(bm, web, s * WEB_Y - 0.003, s * WEB_Y + 0.003, (0.0, 0.0, 0.0), rot_web,
                      PAINT_IDX, ch=0.0007)
        rot = frame(a, Y)          # local u along world Y
        u_web = s * (WEB_Y - KP_Y) - s * 0.0045
        lug = circles_hull([(0.0, 0.0, 0.019), (u_web, 0.026, 0.004), (u_web, -0.026, 0.004)], 20)
        for sgn in (1.0, -1.0):
            s0 = sgn * (KP_HALF - 0.0005)
            s1 = sgn * (KP_HALF + 0.0055)
            with b.part(T_FRAME, 0.5, "kart"):
                add_prism(bm, lug, min(s0, s1), max(s0, s1), K, rot, PAINT_IDX, ch=0.0006)
        with b.part(T_NONE, 0.5, "kart"):
            add_rod(bm, K, a, -(KP_HALF + 0.0160), KP_HALF + 0.0100, 0.0055, CHROME_IDX)
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, K, a, KP_HALF + 0.0053, KP_HALF + 0.0125, 0.0105, CHROME_IDX)
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, K, -a, KP_HALF + 0.0053, KP_HALF + 0.0122, 0.0105, CHROME_IDX)


def tyre_profile(R, W, Wf, bite):
    rs = RS - bite
    half = [(R, W * 0.35), (R, W - 0.026), (R - 0.0015, W - 0.019), (R - 0.004, W - 0.013),
            (R - 0.010, W - 0.0062), (R - 0.020, W - 0.0012), (RFL + 0.016, W),
            (RFL + 0.006, W - 0.004), (RFL + 0.0015, Wf - 0.0006), (RS + 0.003, Wf - 0.0012),
            (rs, Wf - 0.004), (rs, Wf - 0.015)]
    minus = [(r, -w) for r, w in reversed(half)]
    return half + minus


def rim_profile(Wf, d0, d1, rb):
    t = RIM_T
    Wo = Wf + 0.004
    ws = 0.5 * (d0 + d1)
    plus = [(RFL - 0.0012, Wo), (RFL, Wo - 0.0012), (RFL, Wf + 0.0008), (RFL - 0.0010, Wf),
            (RS + 0.0020, Wf), (RS, Wf - 0.0020), (RS, Wf - 0.0180), (RS - 0.0020, Wf - 0.0205),
            (RD, Wf - 0.0250)]
    minus = [(r, -w) for r, w in reversed(plus)]
    outer = plus + [(RD, ws + 0.0025), (RD - 0.0012, ws), (RD, ws - 0.0025)] + minus
    ri = RD - t
    inner = [(RS - t, -Wo), (ri, -(Wf - 0.025)), (ri, d0 - 0.004), (ri - 0.004, d0),
             (rb + 0.004, d0), (rb, d0 + 0.002), (rb, d1 - 0.002), (rb + 0.004, d1),
             (ri - 0.004, d1), (ri, d1 + 0.004), (ri, Wf - 0.025), (RS - t, Wo)]
    return outer + inner


def build_wheel(b, centre, side, front, tag_groups, tyre_group, bite=TYRE_BITE, tone=0.5):
    """Tyre, split rim with its bolts, studs and valve. ``side`` +1 left,
    -1 right: the rim's +w is outboard."""
    bm = b.bm
    c = Vector(centre)
    ax = Y * side
    R, W, Wf = (R_TF, W_TF, WF_F) if front else (R_TR, W_TR, WF_R)
    d0, d1 = DISC_F if front else DISC_R
    rb = BORE_F if front else BORE_R
    rot = frame(ax, Z)
    with b.part(T_TYRE, tone, *tag_groups, "tyres", tyre_group):
        # a ring of vertices points straight down, so the patch is centred
        add_lathe(bm, tyre_profile(R, W, Wf, bite), TYRE_SEGS, RUBBER_IDX, center=c, rot=rot,
                  phase=0.5 * math.pi * 0.0 + math.pi)
    with b.part(T_RIM, 0.5, *tag_groups):
        add_lathe(bm, rim_profile(Wf, d0, d1, rb), RIM_SEGS, ALU_IDX, center=c, rot=rot,
                  phase=math.pi / RIM_SEGS)
    # split-rim bolts through the disc: heads outboard, nuts inboard
    nb, rbc = (6, 0.040) if front else (6, 0.048)
    for k in range(nb):
        a = 2.0 * math.pi * k / nb + (0.0 if front else math.pi / 6.0)
        p = c + rot @ Vector((rbc * math.cos(a), rbc * math.sin(a), 0.0))
        e = 0.0002 * k
        with b.part(T_NONE, 0.5, *tag_groups):
            add_hex(bm, p, ax, d1 - 0.0004 - e, d1 + 0.0040 + e, 0.0048, CHROME_IDX, phase=a)
        if front:
            # the rear's nuts would sit inside the hub flange behind the disc
            with b.part(T_NONE, 0.5, *tag_groups):
                add_hex(bm, p, -ax, -d0 - 0.0004 - e, -d0 + 0.0036 + e, 0.0048, CHROME_IDX,
                        phase=a)
    if not front:
        # three hub studs and nuts
        for k in range(3):
            a = 2.0 * math.pi * k / 3 + 0.25
            p = c + rot @ Vector((0.038 * math.cos(a), 0.038 * math.sin(a), 0.0))
            e = 0.0002 * k
            with b.part(T_NONE, 0.5, *tag_groups):
                add_rod(bm, p, ax, d0 - 0.006, d1 + 0.0105 + e, 0.0040, STEEL_IDX, segs=10)
            with b.part(T_NONE, 0.5, *tag_groups):
                add_hex(bm, p, ax, d1 - 0.0003 - e, d1 + 0.0078 + e, 0.0072, CHROME_IDX, phase=a)
    # valve stem through the barrel, into the dish, outboard side
    wv = 0.030 if front else 0.018
    av = math.radians(38.0)
    base = c + rot @ Vector((0.0, RD - RIM_T * 0.5, wv))
    vdir = rot @ Vector((0.0, -math.sin(av), math.cos(av)))
    with b.part(T_NONE, 0.5, *tag_groups):
        lathe_on(bm, [(0.0030, 0.0), (0.0032, 0.004), (0.0026, 0.016), (0.0026, 0.019)], 10,
                 RUBBER_IDX, base, vdir)
    with b.part(T_NONE, 0.5, *tag_groups):
        lathe_on(bm, [(0.0037, 0.0175), (0.0040, 0.019), (0.0040, 0.026), (0.0030, 0.0275)], 10,
                 CHROME_IDX, base, vdir)


def build_front_corner(b, s, caster, toe):
    """Spindle (sleeve, stub axle, steering arm, arm pin), spacer, hub and
    the wheel, all in group ``cornerL``/``cornerR``; toe turns the group about
    the vertical through the kingpin centre."""
    bm = b.bm
    g = "cornerL" if s > 0 else "cornerR"
    a = kp_axis(caster)
    K = kp_centre(s)
    ax = Y * s
    with b.part(T_KINGPIN, 0.5, "kart", g):
        lathe_on(bm, [(KP_R - 0.0015, -KP_HALF), (KP_R, -KP_HALF + 0.0015),
                      (KP_R, KP_HALF - 0.0015), (KP_R - 0.0015, KP_HALF)], 20, CHROME_IDX, K, a)
    w0 = KP_Y - 0.008
    with b.part(T_STUB, 0.5, "kart", g):
        lathe_on(bm, [(0.0085, w0), (0.0085, 0.6095), (0.0070, 0.6120)], 16, CHROME_IDX,
                 Vector((AX_F, 0.0, Z_AF)), ax)
    with b.part(T_NONE, 0.5, "kart", g):
        lathe_on(bm, [(0.0080, KP_Y + KP_R - 0.0008), (0.0125, KP_Y + KP_R - 0.0008),
                      (0.0125, 0.5005), (0.0080, 0.5005)], 16, CHROME_IDX,
                 Vector((AX_F, 0.0, Z_AF)), ax, solid=False)
    with b.part(T_HUB_F, 0.5, "kart", g):
        lathe_on(bm, [(0.0080, 0.500), (0.0200, 0.500), (0.0220, 0.502), (0.0220, 0.598),
                      (0.0200, 0.600), (0.0080, 0.600)], 24, ALU_IDX,
                 Vector((AX_F, 0.0, Z_AF)), ax, solid=False)
    with b.part(T_NONE, 0.5, "kart", g):
        add_hex(bm, Vector((AX_F, 0.0, Z_AF)), ax, 0.5995, 0.6075, 0.0110, CHROME_IDX)
    build_wheel(b, (AX_F, s * TRACK_F / 2, Z_AF), s, True, ("kart", g), "tyre_" + g,
                tone=0.45 if s > 0 else 0.60)
    # steering arm: from the kingpin at arm height back to the pin
    s_arm = (ARM_Z - K.z) / a.z
    root = K + a * s_arm
    E = arm_end(s)
    dirn = (E - root).normalized()
    wax = Vector((-dirn.y, dirn.x, 0.0))
    with b.part(T_ARM, 0.5, "kart", g):
        add_bar(bm, [root, E + dirn * 0.012], wax, 0.011, 0.003, 0.0025, CHROME_IDX)
    with b.part(T_PIN, 0.5, "kart", g):
        lathe_on(bm, [(0.0040, ARM_Z - 0.011), (0.0040, EYE_Z0 + EYE_H + 0.004)], 10, CHROME_IDX,
                 Vector((E.x, E.y, 0.0)), Z)
    with b.part(T_NONE, 0.5, "kart", g):
        add_hex(bm, Vector((E.x, E.y, 0.0)), Z, EYE_Z0 + EYE_H - 0.0002,
                EYE_Z0 + EYE_H + 0.0055, 0.0075, CHROME_IDX)
    with b.part(T_NONE, 0.5, "kart", g):
        add_hex(bm, Vector((E.x, E.y, 0.0)), -Z, -(ARM_Z - 0.0028), -(ARM_Z - 0.0090), 0.0075,
                CHROME_IDX)
    if toe:
        # --toe-wheel: the whole corner turned about the vertical through K
        R3 = Matrix.Rotation(math.radians(toe), 3, "Z")
        for v in b.groups[g]:
            v.co = K + R3 @ (v.co - K)
        E = K + R3 @ (E - K)
    return E


def build_tie_rods(b, ends, short):
    bm = b.bm
    for s in (-1.0, 1.0):
        E = ends[s]
        H = Vector((TAB_HOLE[0], s * TAB_HOLE[1], 0.0))
        zc = EYE_Z0 + 0.5 * EYE_H
        dz = 0.0002 if s < 0 else 0.0
        hc = Vector((H.x, H.y, zc))
        ec = Vector((E.x, E.y, zc))
        dirn = (ec - hc).normalized()
        if short and s > 0:
            ec = ec - dirn * SHORT_TIEROD
        for p in (hc, ec):
            with b.part(T_EYE, 0.5, "kart"):
                lathe_on(bm, [(0.0085, EYE_Z0 + dz), (0.0105, EYE_Z0 + 0.002 + dz),
                              (0.0105, EYE_Z0 + EYE_H - 0.002 + dz), (0.0085, EYE_Z0 + EYE_H + dz)],
                         16, CHROME_IDX, Vector((p.x, p.y, 0.0)), Z)
        with b.part(T_NONE, 0.5, "kart"):
            add_tube(bm, [hc + dirn * 0.005, ec - dirn * 0.005], 0.0055, 12, CHROME_IDX)
        for p, sg in ((hc, 1.0), (ec, -1.0)):
            with b.part(T_NONE, 0.5, "kart"):
                add_hex(bm, p + dirn * sg * 0.022, dirn, -0.003, 0.003, 0.0080, CHROME_IDX)
        # the steering plate's pins
        with b.part(T_PIN, 0.5, "kart"):
            lathe_on(bm, [(0.0040, ARM_Z - 0.011), (0.0040, EYE_Z0 + EYE_H + 0.004)], 10,
                     CHROME_IDX, Vector((H.x, H.y, 0.0)), Z)
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, Vector((H.x, H.y, 0.0)), Z, EYE_Z0 + EYE_H - 0.0002 + dz,
                    EYE_Z0 + EYE_H + 0.0055 + dz, 0.0075, CHROME_IDX)
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, Vector((H.x, H.y, 0.0)), -Z, -(ARM_Z - 0.0028), -(ARM_Z - 0.0090),
                    0.0075, CHROME_IDX)


# --------------------------------------------------------------------------
# Rear axle, drivetrain, brake
# --------------------------------------------------------------------------

_AXL = [0]


def axle_lathe(bm, profile, segs, mat, s, phase=0.0, solid=False):
    """A lathe on the rear axle's line; profile (r, w) with w = |y|. Every
    part is turned a further, non-commensurate step: equal bores on one axle
    would otherwise share their facet planes."""
    _AXL[0] += 1
    return lathe_on(bm, profile, segs, mat, Vector((AX_R, 0.0, Z_AR)), Y * s,
                    phase=phase + 0.0371 * _AXL[0], solid=solid, ref=X)


def build_rear(b, flags):
    bm = b.bm
    with b.part(T_AXLE, 0.5, "kart"):
        lathe_on(bm, [(AXLE_R - 0.0015, -AXLE_W), (AXLE_R, -AXLE_W + 0.0015),
                      (AXLE_R, AXLE_W - 0.0015), (AXLE_R - 0.0015, AXLE_W)], 24, STEEL_IDX,
                 Vector((AX_R, 0.0, Z_AR)), Y, ref=X)
    for s in (-1.0, 1.0):
        side = "L" if s > 0 else "R"
        # bearing carrier: three-lobed flange and boss bolted to the hanger
        gb = "bearing" + side
        w_face = HANGER_Y + HANGER_T / 2
        lobes = [(0.042 * math.cos(math.radians(90 + 120 * k)),
                  0.042 * math.sin(math.radians(90 + 120 * k)), 0.013) for k in range(3)]
        outline = circles_hull(lobes + [(0.0, 0.0, 0.034)], 16)
        rot = frame(Y * s, X)
        with b.part(T_NONE, 0.5, "kart", gb):
            add_prism(bm, outline, w_face - 0.0005, w_face + 0.0085,
                      Vector((AX_R, 0.0, Z_AR)), rot if s > 0 else frame(-Y, X),
                      ALU_IDX, ch=0.0008)
        with b.part(T_NONE, 0.5, "kart", gb):
            axle_lathe(bm, [(0.0280, w_face + 0.004), (0.0335, w_face + 0.004),
                            (0.0345, w_face + 0.008), (0.0345, w_face + 0.030),
                            (0.0325, w_face + 0.033), (0.0280, w_face + 0.033)], 32, ALU_IDX, s)
        with b.part(T_BEARING, 0.5, "kart", gb):
            axle_lathe(bm, [(AXLE_R - 0.0005, w_face - 0.002), (0.0285, w_face - 0.002),
                            (0.0285, w_face + 0.031), (AXLE_R - 0.0005, w_face + 0.031)], 32,
                       STEEL_IDX, s)
        for k, (u, v, _r) in enumerate(lobes):
            p = Vector((AX_R, 0.0, Z_AR)) + (rot if s > 0 else frame(-Y, X)) @ Vector((u, v, 0.0))
            with b.part(T_NONE, 0.5, "kart", gb):
                add_hex(bm, p, Y * s, w_face + 0.0083 - 0.0002 * k, w_face + 0.0140 + 0.0002 * k, 0.0070,
                        CHROME_IDX)
        # locking collar outboard of the bearing
        with b.part(T_NONE, 0.5, "kart"):
            axle_lathe(bm, [(AXLE_R - 0.0005, w_face + 0.0325), (0.0290, w_face + 0.0325),
                            (0.0300, w_face + 0.0335), (0.0300, w_face + 0.0435),
                            (0.0290, w_face + 0.0445), (AXLE_R - 0.0005, w_face + 0.0445)], 32,
                       ALU_IDX, s)
        if s < 0 and flags["drop_bearing"]:
            for v in b.groups[gb]:
                v.co.z -= DROP_BEARING
        # hub and wheel
        gh = "hub" + side
        gw = "wheel" + side
        with b.part(T_HUB_R, 0.5, "kart", gh, gw):
            axle_lathe(bm, [(AXLE_R - 0.0005, 0.468), (0.0315, 0.468), (0.0330, 0.4695),
                            (0.0330, 0.5250), (0.0500, 0.5260), (0.0520, 0.5280), (0.0520, 0.5365),
                            (0.0290, 0.5365), (0.0290, 0.5420), (AXLE_R - 0.0005, 0.5420)], 32,
                       ALU_IDX, s)
        for k in range(2):
            a = math.radians(60.0 + 180.0 * k)
            p = Vector((AX_R + 0.030 * math.cos(a), s * 0.492, Z_AR + 0.030 * math.sin(a)))
            with b.part(T_NONE, 0.5, "kart", gh, gw):
                add_hex(bm, p, Vector((math.cos(a), 0.0, math.sin(a))), -0.004, 0.0045 + 0.0002 * k,
                        0.0062, CHROME_IDX)
        bite = SINK_BITE if (flags["sink_tyre"] and s < 0) else TYRE_BITE
        build_wheel(b, (AX_R, s * TRACK_R / 2, Z_AR), s, False, ("kart", gw), "tyre_" + gw,
                    bite=bite, tone=0.30 if s > 0 else 0.75)
        if s > 0 and flags["cock_hub"]:
            for v in b.groups[gh]:
                v.co.z += COCK_HUB
        if flags["wide_track"]:
            for v in b.groups[gw]:
                v.co.y += s * WIDE_TRACK
    # brake: disc on a carrier, caliper on a bracket from the rear crossmember
    s = 1.0
    wd = 0.228
    with b.part(T_NONE, 0.5, "kart"):
        axle_lathe(bm, [(AXLE_R - 0.0005, wd - 0.026), (0.0300, wd - 0.026), (0.0310, wd - 0.025),
                        (0.0310, wd - 0.0055), (0.0560, wd - 0.0055), (0.0560, wd - 0.0045),
                        (AXLE_R - 0.0005, wd - 0.0045)], 32, ALU_IDX, s)
    disc = [(0.0500, wd - 0.005), (0.0890, wd - 0.005), (0.0905, wd - 0.0035), (0.0905, wd + 0.0035),
            (0.0890, wd + 0.005), (0.0500, wd + 0.005)]
    with b.part(T_NONE, 0.5, "kart"):
        axle_lathe(bm, disc, 48, STEEL_IDX, s)
    for k in range(6):
        a = 2.0 * math.pi * k / 6
        p = Vector((AX_R + 0.053 * math.cos(a), 0.0, Z_AR + 0.053 * math.sin(a)))
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, p, Y, wd + 0.0048 - 0.0002 * k, wd + 0.0098 + 0.0002 * k, 0.0050, CHROME_IDX,
                    phase=a)
    ca = math.radians(140.0)
    cc = Vector((AX_R + 0.074 * math.cos(ca), wd, Z_AR + 0.074 * math.sin(ca)))
    rot = frame(Y, Vector((-math.sin(ca), 0.0, math.cos(ca))))
    with b.part(T_NONE, 0.5, "kart"):
        add_rbox(bm, 0.036, 0.022, 0.008, [(0.002, -0.024), (0.0, -0.022), (0.0, 0.022),
                                           (0.002, 0.024)], cc, rot, ALU_IDX, n_corner=3)
    rear_cross = Vector((-0.660, wd, Z_F))
    with b.part(T_NONE, 0.5, "kart"):
        add_bar(bm, [cc + Vector((-0.010, 0.0, -0.012)), rear_cross + Vector((0.004, 0.0, 0.006))],
                Y, 0.012, 0.003, 0.002, ALU_IDX)
    return wd


def chain_tangent(ca, ra, cb, rb):
    d = cb - ca
    dist = d.length
    dh = d / dist
    dp = Vector((-dh.y, dh.x))
    k = (rb - ra) / dist
    s = math.sqrt(max(0.0, 1.0 - k * k))
    n = dh * k + dp * s
    return ca - n * ra, cb - n * rb


def chain_path(circles):
    """Open-belt path round two circles [(centre2d, r)], anticlockwise:
    (segments, total length)."""
    n = len(circles)
    deps, arrs = [None] * n, [None] * n
    for i in range(n):
        ca, ra = circles[i]
        cb, rb = circles[(i + 1) % n]
        pa, pb = chain_tangent(ca, ra, cb, rb)
        deps[i] = pa
        arrs[(i + 1) % n] = pb
    segs = []
    for i in range(n):
        c, r = circles[i]
        a0 = math.atan2(arrs[i].y - c.y, arrs[i].x - c.x)
        a1 = math.atan2(deps[i].y - c.y, deps[i].x - c.x)
        sweep = (a1 - a0) % (2.0 * math.pi)
        segs.append(("arc", c, r, a0, sweep, i))
        segs.append(("line", deps[i], arrs[(i + 1) % n], None, None, i))
    total = sum(sweep_len(sg) for sg in segs)
    return segs, total


def sweep_len(sg):
    if sg[0] == "arc":
        return abs(sg[4]) * sg[2]
    return (sg[2] - sg[1]).length


def r_pitch(n):
    return PITCH / (2.0 * math.sin(math.pi / n))


def engine_x():
    """The engine sprocket's station that makes the chain a whole number of
    3/8 in pitches round both sprockets."""
    A = Vector((AX_R, Z_AR))

    def length(xe):
        return chain_path([(A, r_pitch(N_AXLE)), (Vector((xe, Z_ENG)), r_pitch(N_ENG))])[1]
    target = LINKS * PITCH
    lo, hi = AX_R + 0.14, AX_R + 0.40
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if length(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def chain_pins(xe, lift):
    A = Vector((AX_R, Z_AR))
    E = Vector((xe, Z_ENG))
    segs, total = chain_path([(A, r_pitch(N_AXLE) + lift), (E, r_pitch(N_ENG) + lift)])
    pitch = total / LINKS
    lens = [sweep_len(sg) for sg in segs]
    pins = []
    for k in range(LINKS):
        s = k * pitch
        i = 0
        while i < len(segs) - 1 and s > lens[i]:
            s -= lens[i]
            i += 1
        sg = segs[i]
        if sg[0] == "arc":
            _, c, r, a0, _sw, ci = sg
            a = a0 + s / r
            pins.append((c + Vector((math.cos(a), math.sin(a))) * r, ci, a))
        else:
            _, p0, p1, _, _, ci = sg
            d = (p1 - p0).normalized()
            pins.append((p0 + d * s, None, None))
    return pins


def add_sprocket(bm, cx, cz, y, n, phase, r_in, half_t, mat_idx):
    """A toothed annulus in the XZ plane at ``y`` (after road-bicycle)."""
    r_p = r_pitch(n)
    step = 2.0 * math.pi / n
    r_f = r_p - 0.0026
    r_t = r_p + 0.0040
    g = min(0.0031 / r_f, 0.35 * step)
    w1 = 0.5 * step - g
    w2 = min(0.0012 / r_p, 0.8 * w1)
    outer, inner = [], []
    tooth = ((-w1, r_f), (-w2, r_t), (w2, r_t), (w1, r_f))
    for j in range(n):
        a = phase + j * step
        for da, r in tooth:
            outer.append((a + da, r))
        inner.append((a, r_in))

    def v(ar, yy):
        a, r = ar
        return bm.verts.new((cx + r * math.cos(a), yy, cz + r * math.sin(a)))
    ot = [v(p, y + half_t) for p in outer]
    ob = [v(p, y - half_t) for p in outer]
    it = [v(p, y + half_t) for p in inner]
    ib = [v(p, y - half_t) for p in inner]
    faces = []
    m = len(outer)
    for j in range(n):
        o = [4 * j + q for q in range(4)] + [(4 * j + 4) % m]
        jn = (j + 1) % n
        faces.append(bm.faces.new([it[j]] + [ot[q] for q in o] + [it[jn]]))
        faces.append(bm.faces.new([ib[jn]] + [ob[q] for q in reversed(o)] + [ib[j]]))
        faces.append(bm.faces.new((it[jn], ib[jn], ib[j], it[j])))
    for q in range(m):
        k = (q + 1) % m
        faces.append(bm.faces.new((ot[q], ob[q], ob[k], ot[k])))
    _mark(faces, mat_idx)


def build_chain(b, pins):
    """The chain as one closed sweep: rings either side of every pin framed
    by the bisector of the two links that meet there, a waist between pins,
    inner and outer links alternately narrow and wide."""
    bm = b.bm
    n = len(pins)
    P = [Vector((p.x, CHAIN_Y, p.y)) for p, _c, _a in pins]
    rings = []

    def ring(c, t, hh, hw):
        t = t.normalized()
        nrm = Vector((-t.z, 0.0, t.x))
        return [bm.verts.new(c + Y * x + nrm * y) for x, y in rrect(hw, hh, 0.0014, 1)]

    for k in range(n):
        a, bb = P[k], P[(k + 1) % n]
        prev = P[k - 1]
        nxt = P[(k + 2) % n]
        t = bb - a
        ta = (t.normalized() + (a - prev).normalized())
        tb = (t.normalized() + (nxt - bb).normalized())
        hw = CH_IN if k % 2 == 0 else CH_OUT
        rings.append(ring(a + t * 0.02, ta, CH_PIN, hw))
        rings.append(ring(a + t * 0.5, t, CH_MID, hw))
        rings.append(ring(a + t * 0.98, tb, CH_PIN, hw))
    m = len(rings)
    faces = []
    for i in range(m):
        r0, r1 = rings[i], rings[(i + 1) % m]
        k = len(r0)
        for j in range(k):
            jj = (j + 1) % k
            faces.append(bm.faces.new((r0[j], r0[jj], r1[jj], r1[j])))
    _mark(faces, STEEL_IDX)


def sprocket_phase(pins, ci, n):
    angs = [a for (_p, c, a) in pins if c == ci]
    if not angs:
        return 0.0
    return angs[len(angs) // 2] - math.pi / n


def build_drivetrain(b, flags):
    bm = b.bm
    xe = engine_x()
    # the teeth are phased to the seated chain; --lift-chain moves the chain alone
    seated = chain_pins(xe, 0.0)
    pins = chain_pins(xe, LIFT_CHAIN) if flags["lift_chain"] else seated
    ph_a = sprocket_phase(seated, 0, N_AXLE)
    ph_e = sprocket_phase(seated, 1, N_ENG)
    s = -1.0
    wc = -CHAIN_Y
    # axle sprocket on its carrier, bolted
    with b.part(T_NONE, 0.5, "kart"):
        axle_lathe(bm, [(AXLE_R - 0.0005, wc - 0.027), (0.0295, wc - 0.027), (0.0300, wc - 0.0265),
                        (0.0300, wc - 0.0085), (0.0635, wc - 0.0085), (0.0640, wc - 0.0080),
                        (0.0640, wc - 0.0015), (0.0240, wc - 0.0015), (AXLE_R - 0.0005, wc - 0.0050)],
                   32, ALU_IDX, s)
    with b.part(T_SPROCKET, 0.5, "kart"):
        add_sprocket(bm, AX_R, Z_AR, CHAIN_Y, N_AXLE, ph_a, 0.0560, SPR_HALF_T, ALU_IDX)
    for k in range(6):
        a = 2.0 * math.pi * k / 6 + 0.2
        p = Vector((AX_R + 0.060 * math.cos(a), 0.0, Z_AR + 0.060 * math.sin(a)))
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, p, -Y, wc + SPR_HALF_T - 0.0003 - 0.0002 * k,
                    wc + SPR_HALF_T + 0.0048 + 0.0002 * k,
                    0.0052, CHROME_IDX, phase=a)
    # engine sprocket on the clutch drum
    C = Vector((xe, 0.0, Z_ENG))
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.020, 0.394), (0.030, 0.397), (0.046, 0.401), (0.048, 0.406),
                      (0.048, 0.428), (0.044, 0.433), (0.016, 0.4355)], 32, STEEL_IDX, C, -Y, ref=X)
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.013, 0.434), (0.013, 0.4510)], 20, STEEL_IDX, C, -Y, ref=X)
    with b.part(T_SPROCKET, 0.5, "kart"):
        add_sprocket(bm, xe, Z_ENG, CHAIN_Y, N_ENG, ph_e, 0.0105, SPR_HALF_T, STEEL_IDX)
    with b.part(T_NONE, 0.5, "kart"):
        add_hex(bm, C, -Y, 0.4503, 0.4568, 0.0100, CHROME_IDX)
    with b.part(T_CHAIN, 0.5, "kart"):
        build_chain(b, pins)
    return xe


def build_engine(b, xe):
    """A small four-stroke: crankcase on a plate clamped to the right rail, a
    finned cylinder and head leaning forward, fan shroud with pull-start on
    the seat side, air-box ahead, exhaust header to a silencer behind."""
    bm = b.bm
    ry = -HANGER_Y
    I3 = Matrix.Identity(3)
    # mount plate on the rail and two clamps round it
    with b.part(T_NONE, 0.5, "kart"):
        add_rbox(bm, 0.150, 0.100, 0.014, chamfered(0.0080, 0.0012),
                 (xe, ry, Z_F + TUBE_R - 0.0005), I3, ALU_IDX, n_corner=3)
    for k, dx in enumerate((-0.112, 0.112)):
        with b.part(T_NONE, 0.5, "kart"):
            add_rbox(bm, 0.016, 0.0255, 0.008, chamfered(0.0400, 0.0015),
                     (xe + dx, ry, Z_F - 0.023 + 0.0003 * k), I3, ALU_IDX, n_corner=3)
    plate_top = Z_F + TUBE_R - 0.0005 + 0.0080
    for k, (dx, dy) in enumerate(((-0.132, 0.080), (0.132, 0.080), (-0.132, -0.080),
                                  (0.132, -0.080))):
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, Vector((xe + dx, ry + dy, 0.0)), Z, plate_top - 0.0003 - 0.00015 * k,
                    plate_top + 0.0055 + 0.0002 * k, 0.0070, CHROME_IDX)
    # crankcase
    cz0 = plate_top - 0.001
    with b.part(T_NONE, 0.45, "kart"):
        add_rbox(bm, 0.118, 0.090, 0.030, [(0.006, 0.0), (0.0, 0.006), (0.0, 0.164),
                                           (0.010, 0.170)], (xe + 0.004, -0.305, cz0), I3,
                 CASTING_IDX, n_corner=4)
    # PTO-side bearing cover and its bolts, oil filler and drain plug
    with b.part(T_NONE, 0.40, "kart"):
        lathe_on(bm, [(0.062, -0.002), (0.064, 0.002), (0.064, 0.006), (0.058, 0.009),
                      (0.034, 0.010)], 32, CASTING_IDX, Vector((xe, -0.393, Z_ENG)), -Y, ref=X)
    for k in range(6):
        a = 2.0 * math.pi * k / 6 + 0.3
        p = Vector((xe + 0.056 * math.cos(a), -0.393, Z_ENG + 0.056 * math.sin(a)))
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, p, -Y, 0.0070 - 0.0002 * k, 0.0135 + 0.0002 * k, 0.0048, CHROME_IDX)
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.014, -0.004), (0.016, 0.004), (0.016, 0.014), (0.012, 0.018),
                      (0.005, 0.019)], 16, BLACK_IDX, Vector((xe - 0.080, -0.360, cz0 + 0.1695)), Z)
    with b.part(T_NONE, 0.5, "kart"):
        add_hex(bm, Vector((xe + 0.070, -0.395, cz0 + 0.020)), -Y, -0.002, 0.006, 0.0075,
                CHROME_IDX)
    # cylinder and head, leaning forward
    cyl = Vector((math.sin(math.radians(CYL_DEG)), 0.0, math.cos(math.radians(CYL_DEG))))
    C = Vector((xe, -0.305, Z_ENG))
    rot = frame(cyl, X)
    prof = [(0.016, 0.060), (0.016, 0.078)]
    for k in range(9):
        z0 = 0.082 + k * 0.012
        prof += [(0.004, z0), (0.0, z0 + 0.0015), (0.0, z0 + 0.0035), (0.004, z0 + 0.005),
                 (0.017, z0 + 0.0055), (0.017, z0 + 0.0115)]
    prof += [(0.004, 0.190), (0.0, 0.1915), (0.0, 0.196), (0.004, 0.198)]
    with b.part(T_NONE, 0.40, "kart"):
        add_rbox(bm, 0.060, 0.064, 0.018, prof, C, rot, CASTING_IDX, n_corner=3)
    hprof = [(0.010, 0.194)]
    for k in range(4):
        z0 = 0.199 + k * 0.012
        hprof += [(0.004, z0), (0.0, z0 + 0.0015), (0.0, z0 + 0.0040), (0.004, z0 + 0.0055),
                  (0.014, z0 + 0.006), (0.014, z0 + 0.0115)]
    hprof += [(0.004, 0.248), (0.0, 0.250), (0.0, 0.256), (0.006, 0.260)]
    with b.part(T_NONE, 0.55, "kart"):
        add_rbox(bm, 0.066, 0.070, 0.020, hprof, C, rot, CASTING_IDX, n_corner=3)
    with b.part(T_NONE, 0.5, "kart"):
        add_rbox(bm, 0.050, 0.054, 0.016, [(0.0, 0.2585), (0.0, 0.272), (0.006, 0.280),
                                           (0.016, 0.283)], C, rot, BLACK_IDX, n_corner=3)
    # spark plug and its boot on the head's front
    ex = rot @ X
    pp = C + cyl * 0.228 + ex * 0.064
    pax = (ex * math.cos(math.radians(25)) + cyl * math.sin(math.radians(25))).normalized()
    with b.part(T_NONE, 0.5, "kart"):
        add_hex(bm, pp, pax, -0.004, 0.006, 0.0095, CHROME_IDX)
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.0060, 0.0055), (0.0105, 0.010), (0.0110, 0.030), (0.0090, 0.040),
                      (0.0045, 0.046)], 14, RUBBER_IDX, pp, pax)
    lead_start = pp + pax * 0.043
    with b.part(T_NONE, 0.5, "kart"):
        add_tube(bm, fillet_path([lead_start - pax * 0.004, lead_start + pax * 0.030,
                                  Vector((xe + 0.02, -0.230, 0.330)),
                                  Vector((xe - 0.02, -0.212, 0.300))], 0.03, 5), 0.0035, 8,
                 RUBBER_IDX)
    # fan shroud and recoil starter on the seat side
    with b.part(T_NONE, 0.5, "kart"):
        add_rbox(bm, 0.128, 0.130, 0.045, [(0.004, 0.0), (0.0, 0.004), (0.0, 0.020),
                                           (0.006, 0.026)], (xe - 0.004, -0.2170, Z_ENG + 0.030),
                 frame(Y, X), BLACK_IDX, n_corner=4)
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.075, 0.000), (0.075, 0.006), (0.069, 0.013), (0.048, 0.018),
                      (0.020, 0.020)], 32, CASTING_IDX, Vector((xe, -0.1915, Z_ENG)), Y, ref=X)
    hp = Vector((xe - 0.040, -0.2030, Z_ENG + 0.030 + 0.130 + 0.010))
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.004, -0.045), (0.009, -0.043), (0.011, -0.036), (0.011, 0.036),
                      (0.009, 0.043), (0.004, 0.045)], 12, BLACK_IDX, hp, X)
    with b.part(T_NONE, 0.5, "kart"):
        add_tube(bm, fillet_path([Vector((xe - 0.050, -0.1905, Z_ENG + 0.060)),
                                  Vector((xe - 0.052, -0.1890, Z_ENG + 0.110)),
                                  hp + Vector((-0.012, 0.004, -0.004))], 0.02, 4), 0.0022, 8,
                 BLACK_IDX)
    # air-box ahead of the cylinder and the carburettor into the barrel
    abx = xe + 0.212
    with b.part(T_NONE, 0.5, "kart"):
        add_rbox(bm, 0.048, 0.072, 0.022, [(0.006, 0.0), (0.0, 0.006), (0.0, 0.124),
                                           (0.008, 0.132)], (abx, -0.312, 0.190), I3, BLACK_IDX,
                 n_corner=4)
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.011, 0.0), (0.016, 0.004), (0.016, 0.010), (0.004, 0.014)], 16, ALU_IDX,
                 Vector((abx, -0.3825, 0.256)), -Y, ref=X)
    carb0 = C + cyl * 0.120 + ex * 0.052
    carb1 = Vector((abx - 0.045, -0.312, carb0.z))
    with b.part(T_NONE, 0.5, "kart"):
        add_tube(bm, [Vector((carb0.x, -0.312, carb0.z)), carb1], 0.0155, 16, ALU_IDX)
    # exhaust: header from the head's outboard face to a silencer behind
    port = C + cyl * 0.212 + Vector((0.0, -0.066, 0.0))
    mz, my, mx0 = 0.336, -0.300, xe - 0.118
    header = [port + Vector((0.0, 0.006, 0.0)), port + Vector((0.0, -0.030, 0.004)),
              Vector((port.x - 0.070, -0.392, port.z - 0.010)),
              Vector((mx0 + 0.010, -0.330, mz)), Vector((mx0 - 0.020, my, mz))]
    with b.part(T_NONE, 0.5, "kart"):
        add_tube(bm, fillet_path(header, 0.035, 6), 0.0135, 14, STEEL_IDX)
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.030, 0.0), (0.044, 0.006), (0.049, 0.018), (0.049, 0.222),
                      (0.044, 0.234), (0.030, 0.240)], 32, STEEL_IDX, Vector((mx0, my, mz)), -X)
    with b.part(T_NONE, 0.5, "kart"):
        add_tube(bm, fillet_path([Vector((mx0 - 0.200, my - 0.010, mz - 0.012)),
                                  Vector((mx0 - 0.262, my - 0.010, mz - 0.016)),
                                  Vector((mx0 - 0.300, my - 0.010, mz - 0.040))], 0.03, 5),
                 0.0115, 12, STEEL_IDX)
    with b.part(T_NONE, 0.5, "kart"):
        add_bar(bm, [Vector((mx0 - 0.060, my, mz - 0.040)), Vector((xe - 0.105, my, 0.232))], Y,
                0.012, 0.0025, 0.0015, STEEL_IDX)
    return C


# --------------------------------------------------------------------------
# Seat, bodywork, pedals, tank, ballast, bumpers
# --------------------------------------------------------------------------

SEAT_SPINE = [(0.050, 0.150), (0.010, 0.092), (-0.060, 0.070), (-0.130, 0.066),
              (-0.230, 0.072), (-0.310, 0.110), (-0.380, 0.200), (-0.440, 0.300),
              (-0.490, 0.400), (-0.520, 0.470)]
_SEAT_W = pchip([(0.0, 0.140), (0.2, 0.165), (0.45, 0.175), (0.75, 0.178), (0.92, 0.160),
                 (1.0, 0.130)])
_SEAT_D = pchip([(0.0, 0.030), (0.15, 0.080), (0.35, 0.110), (0.55, 0.125), (0.80, 0.110),
                 (0.93, 0.070), (1.0, 0.040)])
_SEAT_E = pchip([(0.0, 3.0), (0.4, 3.4), (0.7, 2.6), (1.0, 2.2)])
SEAT_NU, SEAT_NV = 24, 30
SEAT_THICK = 0.006


def seat_spine():
    pts = fillet_path([Vector((x, 0.0, z)) for x, z in SEAT_SPINE], 0.06, 6)
    dense = resample(pts, 241)
    return dense


_SPINE = None


def seat_point(u, v, lift=0.0):
    """The seat's outer surface at (u along the spine, v across the U)."""
    global _SPINE
    if _SPINE is None:
        _SPINE = seat_spine()
    sp = _SPINE
    f = u * (len(sp) - 1)
    i = min(int(f), len(sp) - 2)
    t = f - i
    p = sp[i] * (1 - t) + sp[i + 1] * t
    tg = (sp[i + 1] - sp[i]).normalized()
    nrm = Vector((tg.z, 0.0, -tg.x))
    if nrm.z < 0.0 and u < 0.5:
        nrm = -nrm
    th = (v - 0.5) * math.pi
    c, s = math.sin(th), math.cos(th)
    ex = _SEAT_E(u)
    w = _SEAT_W(u)
    dd = _SEAT_D(u)
    yy = w * math.copysign(abs(c) ** (2.0 / ex), c)
    nn = dd * (1.0 - abs(s) ** (2.0 / ex))
    return p + Vector((0.0, SEAT_Y + yy, lift)) + nrm * nn


def seat_surf(u, v, eps=1e-4):
    p = seat_point(u, v)
    pu = seat_point(min(1.0, u + eps), v) - seat_point(max(0.0, u - eps), v)
    pv = seat_point(u, min(1.0, v + eps)) - seat_point(u, max(0.0, v - eps))
    return p, pu.cross(pv).normalized()


def build_seat(b):
    bm = b.bm
    # the sheet is offset against its normal: make the normal point out of
    # the shell (down under the pan), so the thickness goes into the seat
    _p0, n0 = seat_surf(0.4, 0.5)
    flip = n0.z > 0.0

    def surf(u, v):
        p, n = seat_surf(u, v)
        return p, (-n if flip else n)
    with b.part(T_SEAT, 0.5, "kart"):
        vs = add_sheet(bm, surf, SEAT_NU, SEAT_NV, SEAT_THICK, SEAT_IDX)
    # seat on its cross tube: lowest point 1 mm into the tube's top
    zlow = min(v.co.z for v in vs)
    dz = (Z_F + CROSS_R - 0.001) - zlow
    for v in vs:
        v.co.z += dz
    return dz


def build_seat_mounts(b, dz):
    bm = b.bm
    # stays from the back's upper sides down to the hangers' tops
    for s in (-1.0, 1.0):
        v = 0.5 + s * 0.46
        p = seat_point(0.80, v) + Vector((0.0, 0.0, dz))
        # 2.5 mm outside the side wall: the stay's face bites the wall
        top = p + Vector((0.0, s * 0.0005, 0.0))
        foot = Vector((AX_R + 0.024, s * (HANGER_Y - HANGER_T / 2 - 0.0022), Z_AR + 0.044))
        d = (foot - top).normalized()
        wax = d.cross(Y).normalized()
        with b.part(T_NONE, 0.5, "kart"):
            add_bar(bm, [top - d * 0.012, top + d * 0.10, foot + d * 0.012], wax, 0.012, 0.0028,
                    0.0015, CHROME_IDX, fillet=0.05)
        with b.part(T_NONE, 0.5, "kart"):
            add_dome(bm, foot + d * 0.004 + Y * (-s) * 0.0028, -Y * s, CHROME_IDX, r=0.0068)
    # front brackets from the pan's sides down to the rails
    for s in (-1.0, 1.0):
        v = 0.5 + s * 0.49
        top = seat_point(0.24, v) + Vector((0.0, 0.0, dz))
        foot = Vector((top.x, s * rail_y(top.x), Z_F + 0.004))
        top_out = top + Vector((0.0, s * 0.0015, 0.0))
        with b.part(T_NONE, 0.5, "kart"):
            add_bar(bm, [top_out + Vector((0.0, 0.0, 0.015)), top_out, foot], X, 0.011, 0.0025,
                    0.0015, CHROME_IDX, fillet=0.02)


def pod_section(y_in, y_out, zb, zt_in, zt_out, n):
    """A moulded pod's section (left pod, y outward): a flat floor, an outer
    wall with a moulded groove along it and a slight bulge, a raised outer
    crest, a step down to the inner deck, and a plain inner wall."""
    h = zt_out - zb
    hi = zt_in - zb
    pts = [(y_in, zb + 0.14 * hi), (y_in + 0.012, zb), (y_out - 0.024, zb),
           (y_out - 0.002, zb + 0.28 * h), (y_out - 0.001, zb + 0.44 * h),
           (y_out - 0.006, zb + 0.48 * h), (y_out, zb + 0.52 * h),
           (y_out + 0.003, zb + 0.72 * h), (y_out - 0.010, zt_out),
           (y_out - 0.034, zt_out - 0.003), (y_out - 0.046, zt_in + 0.002),
           (y_in + 0.022, zt_in), (y_in, zt_in - 0.16 * hi)]
    return rpoly(pts, 0.009, n)


# (x, y inner, y outer, bottom, inner deck, outer crest): the front tapers in
# and down toward the front wheel, the rear rises and flares ahead of the rear
# tyre
POD_ST = [(-0.330, 0.478, 0.656, 0.090, 0.184, 0.198),
          (-0.322, 0.472, 0.664, 0.083, 0.190, 0.208),
          (-0.295, 0.470, 0.670, 0.081, 0.192, 0.214),
          (-0.230, 0.470, 0.670, 0.081, 0.188, 0.210),
          (-0.140, 0.470, 0.667, 0.081, 0.181, 0.204),
          (-0.030, 0.470, 0.662, 0.081, 0.177, 0.200),
          (0.080, 0.470, 0.657, 0.081, 0.176, 0.198),
          (0.170, 0.470, 0.648, 0.081, 0.172, 0.192),
          (0.235, 0.471, 0.634, 0.082, 0.162, 0.180),
          (0.282, 0.474, 0.614, 0.084, 0.148, 0.164),
          (0.314, 0.478, 0.594, 0.087, 0.136, 0.150),
          (0.330, 0.484, 0.580, 0.092, 0.128, 0.140)]
POD_RIB_X = (-0.140, -0.100, -0.060, -0.020, 0.020, 0.060, 0.100)
POD_RIB_H = 0.0044           # grip rib height over the deck
POD_RIB_BITE = 0.0006

# (x, half width, bottom, shoulder, hump half width, hump top): a low nose
# cone ahead of the front axle, a raised centre hump that carries the front
# panel's foot, lipped shoulders toward the wheels and a rounded chin
NOSE_ST = [(0.650, 0.394, 0.081, 0.160, 0.204, 0.209),
           (0.657, 0.400, 0.075, 0.166, 0.210, 0.215),
           (0.700, 0.412, 0.074, 0.165, 0.208, 0.214),
           (0.760, 0.418, 0.074, 0.160, 0.202, 0.205),
           (0.820, 0.414, 0.075, 0.150, 0.192, 0.188),
           (0.870, 0.402, 0.077, 0.138, 0.180, 0.166),
           (0.900, 0.386, 0.080, 0.128, 0.170, 0.148),
           (0.918, 0.366, 0.084, 0.120, 0.162, 0.134),
           (0.928, 0.346, 0.090, 0.114, 0.154, 0.124)]


def nose_section(hw, zb, zs, hc, zc, n):
    """The nose's section: flat floor, outer wall to a lip along each
    shoulder, the shoulder falling into a valley, a ramp up to the hump."""
    right = [(hw - 0.022, zb), (hw, zb + 0.022), (hw, zs - 0.014), (hw - 0.010, zs + 0.010),
             (hw - 0.028, zs + 0.002), (hc + 0.045, zs + 0.004), (hc, zc - 0.008),
             (hc - 0.030, zc)]
    left = [(-y, z) for y, z in reversed(right)]
    return rpoly(right + left, 0.012, n)


def surface_hit(tree, x, y, z_top=1.0):
    """The top surface under (x, y) and its outward (upward) normal."""
    hit, nrm, _i, _d = tree.ray_cast(Vector((x, y, z_top)), Vector((0.0, 0.0, -1.0)), 2.0)
    if nrm is not None and nrm.z < 0.0:
        nrm = -nrm
    return hit, nrm


def loft_tree(loops):
    tmp = bmesh.new()
    try:
        add_loft(tmp, loops, BODY_IDX)
        tri_short(tmp, list(tmp.faces))
        tmp.normal_update()
        return BVHTree.FromBMesh(tmp)
    finally:
        tmp.free()


def add_loft_short(bm, loops, mat_idx):
    nf = len(bm.faces)
    vs = add_loft(bm, loops, mat_idx)
    bm.faces.ensure_lookup_table()
    tri_short(bm, [bm.faces[i] for i in range(nf, len(bm.faces))])
    return vs


def panel_point(u, v):
    """The front panel's front face, u across (-1..1), v up (0..1): a
    moulding leaning back 40 deg from its foot in the nose's hump toward the
    column, bulged forward, its sides wrapped back and its top corners
    rounded down."""
    vv = v * (1.0 - 0.16 * u ** 4)
    x = 0.705 - 0.180 * vv + 0.028 * math.sin(math.pi * vv) - (0.030 + 0.030 * vv) * u * u
    y = (0.185 - 0.030 * vv) * u
    z = 0.200 + 0.200 * vv + 0.012 * u * u * vv
    return Vector((x, y, z))


PANEL_T = 0.004


def panel_surf(u, v, eps=1e-4):
    """Point and forward normal of the panel's front face at (u, v)."""
    p = panel_point(u, v)
    du = panel_point(min(1.0, u + eps), v) - panel_point(max(-1.0, u - eps), v)
    dv = panel_point(u, min(1.0, v + eps)) - panel_point(u, max(0.0, v - eps))
    n = du.cross(dv).normalized()
    if n.x < 0.0:
        n = -n
    return p, n


def panel_back(u, v, off):
    """A point ``off`` behind the panel's back face at (u, v)."""
    p, n = panel_surf(u, v)
    return p - n * (PANEL_T + off)


def add_strap(bm, pts, wax, mat_idx=None, fillet=0.006):
    """A bodywork bracket: 20 mm flat strap, BRACKET_T thick."""
    if not isinstance(wax, list):
        pts = fillet_path(pts, fillet, 2)
    return add_bar(bm, pts, wax, 0.010, 0.5 * BRACKET_T, 0.0010,
                   ALU_IDX if mat_idx is None else mat_idx, filleted=True)


def panel_du(u, v, eps=1e-4):
    """The panel's across-direction at (u, v): a tab's width must follow it,
    or the wrapped sides tip one edge of the tab off the panel."""
    return (panel_point(min(1.0, u + eps), v) - panel_point(max(-1.0, u - eps), v)).normalized()


def weld_end(axis_pt, axis_dir, towards, r_host):
    """The welded end of a strap on a tube: on the tube's surface line
    facing ``towards``, TUBE_BITE under the surface."""
    a = Vector(axis_dir).normalized()
    d = Vector(towards) - Vector(axis_pt)
    d = (d - a * d.dot(a)).normalized()
    return Vector(axis_pt) + d * (r_host - TUBE_BITE)


def build_body(b, n_corner, flags):
    """A moulded nose on bumper bars, two moulded pods on nerf bars and a
    curved front panel with a number plate; every moulding bolted to flat
    strap brackets welded to the tubes."""
    bm = b.bm
    half_t = 0.5 * BRACKET_T
    tab = half_t - TAB_BITE          # a tab's centre plane behind the face it bites
    # bumper bars from the front crossmember forward into the nose
    for s in (-1.0, 1.0):
        with b.part(T_BAR, 0.5, "kart"):
            add_tube(bm, fillet_path([Vector((0.600, s * 0.140, Z_F)),
                                      Vector((0.636, s * 0.140, 0.104)),
                                      Vector((0.860, s * 0.160, 0.112))], 0.04, 5), 0.0110, 12,
                     CHROME_IDX)
    # the nose
    loops = []
    for k, (x, hw, zb, zs, hc, zc) in enumerate(NOSE_ST):
        loops.append([Vector((x, u, v)) for u, v in nose_section(hw, zb, zs, hc, zc, n_corner)])
    nose_tree = loft_tree(loops)
    with b.part(T_BODY, 0.5, "kart", "nose"):
        add_loft_short(bm, loops, BODY_IDX)
    for k, (x, y) in enumerate(((0.720, 0.330), (0.720, -0.330), (0.850, 0.300), (0.850, -0.300))):
        hit, nrm = surface_hit(nose_tree, x, y)
        if hit is not None:
            with b.part(T_NONE, 0.5, "kart", "nose"):
                add_dome(bm, hit - nrm * 0.0002 * k, nrm, CHROME_IDX, r=0.0075, h=0.0042)
    # nose brackets: straps welded on the front crossmember, their tabs bolted
    # flat to the nose's back face
    x_back = NOSE_ST[0][0]
    for s in (-1.0, 1.0):
        y = s * 0.215
        xt = x_back - tab
        p0 = weld_end(Vector((0.600, y, Z_F)), Y, Vector((0.612, y, 0.100)), TUBE_R)
        with b.part(T_BRACKET, 0.5, "kart"):
            add_strap(bm, [p0, Vector((0.614, y, 0.098)), Vector((xt, y, 0.118)),
                           Vector((xt, y, 0.166))], Y)
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, Vector((xt, y, 0.146)), -X, half_t - 0.0003, half_t + 0.0045, 0.0055,
                    CHROME_IDX)
    # the front panel, its foot sunk in the nose's hump
    with b.part(T_BODY, 0.5, "kart"):
        add_sheet(bm, lambda uu, vv: panel_surf(2.0 * uu - 1.0, vv), 14, 12, PANEL_T, BODY_IDX)
    # a plain number plate on its face, pressed 1 mm into it
    u0, u1, v0, v1 = -0.72, 0.72, 0.24, 0.74

    def plate(uu, vv):
        p, n = panel_surf(u0 + (u1 - u0) * uu, v0 + (v1 - v0) * vv)
        return p + n * 0.0015, n
    with b.part(T_NONE, 0.5, "kart"):
        add_sheet(bm, plate, 8, 6, 0.0025, PLATE_IDX)
    # upper brackets: straps welded on the column support's top bar, their
    # feet bent down flat against the panel's back
    for s in (-1.0, 1.0):
        u = s * 0.40
        tabs = [panel_back(u, v, tab) for v in (0.94, 0.90, 0.86, 0.82, 0.78)]
        y = tabs[0].y
        p0 = weld_end(Vector((0.282, y, 0.212)), Y, tabs[0], CROSS_R)
        with b.part(T_BRACKET, 0.5, "kart"):
            add_strap(bm, [p0] + tabs, panel_du(u, 0.86))
        p, n = panel_surf(u, 0.86)
        with b.part(T_NONE, 0.5, "kart"):
            add_dome(bm, p + n * 0.0002, n, CHROME_IDX, r=0.0068, h=0.0040)
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, tabs[2], -n, half_t - 0.0003, half_t + 0.0040, 0.0052, CHROME_IDX)
    # lower brackets: an angle strap in the wedge behind the panel's foot, one
    # leg bolted to the panel, the other to the nose's hump
    for s in (-1.0, 1.0):
        u = s * 0.55

        def seat_z(q):
            hit, _nrm = surface_hit(nose_tree, q.x, q.y)
            return hit.z + tab if hit is not None else -1.0
        lo_v, hi_v = 0.0, 0.14
        for _ in range(40):
            mid = 0.5 * (lo_v + hi_v)
            q = panel_back(u, mid, tab)
            if q.z < seat_z(q):
                lo_v = mid
            else:
                hi_v = mid
        corner = panel_back(u, hi_v, tab)
        leg = [panel_back(u, v, tab) for v in (0.25, 0.20, 0.15)]
        foot = []
        for dx in (0.012, 0.024):
            q = Vector((corner.x - dx, corner.y, 0.0))
            q.z = seat_z(q)
            foot.append(q)
        path = fillet_path(leg + [corner] + foot, 0.004, 3)
        du = panel_du(u, 0.20)
        waxes = [Y if q.x < corner.x - 0.0015 else du for q in path]
        with b.part(T_BRACKET, 0.5, "kart"):
            add_strap(bm, path, waxes)
        p, n = panel_surf(u, 0.20)
        with b.part(T_NONE, 0.5, "kart"):
            add_dome(bm, p + n * 0.0002, n, CHROME_IDX, r=0.0062, h=0.0036)
        fb = foot[-1] + Vector((0.004, 0.0, 0.0))
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, Vector((fb.x, fb.y, 0.0)), Z, fb.z + half_t - 0.0003,
                    fb.z + half_t + 0.0042, 0.0050, CHROME_IDX)
    # nerf bars, pods, their grip ribs, bolts and brackets
    for s in (-1.0, 1.0):
        gp = "podL" if s > 0 else "podR"
        for k, x in enumerate((0.160, -0.220)):
            ry = rail_y(x)
            with b.part(T_BAR, 0.5, "kart"):
                # level under the pod, its top 1.5 mm into the pod's floor
                add_tube(bm, fillet_path([Vector((x, s * ry, Z_F)), Vector((x, s * 0.400, 0.0715)),
                                          Vector((x, s * 0.630, 0.0715))], 0.05, 5), 0.0110, 12,
                         CHROME_IDX)
        loops = []
        for x, yi, yo, zb, zti, zto in POD_ST:
            sec = pod_section(yi, yo, zb, zti, zto, n_corner)
            if s < 0:
                sec = [(-u, v) for u, v in reversed(sec)]
            loops.append([Vector((x, u, v)) for u, v in sec])
        tree = loft_tree(loops)
        with b.part(T_BODY, 0.5, "kart", gp):
            add_loft_short(bm, loops, BODY_IDX)
        for k, (x, y) in enumerate(((0.130, 0.560), (0.190, 0.560), (-0.250, 0.560),
                                    (-0.190, 0.560))):
            hit, nrm = surface_hit(tree, x, s * y)
            if hit is not None:
                with b.part(T_NONE, 0.5, "kart", gp):
                    add_dome(bm, hit - nrm * 0.0002 * k, nrm, CHROME_IDX, r=0.0070, h=0.0040)
        # moulded grip ribs across the deck, following its surface
        # (each rib a little taller and deeper than the last, its ends staggered:
        # ribs on one flat deck would otherwise share their top, bottom and end
        # planes)
        for i, x in enumerate(POD_RIB_X):
            h = POD_RIB_H + 0.00031 * i
            bite = POD_RIB_BITE + 0.00017 * i
            y0, y1 = 0.500 + 0.0011 * i, 0.600 - 0.0013 * i
            pts = []
            for k in range(3):
                y = y0 + (y1 - y0) * k / 2.0
                hit, nrm = surface_hit(tree, x, s * y)
                if hit is not None:
                    pts.append(hit + nrm * (0.5 * h - bite))
            if len(pts) == 3:
                with b.part(T_NONE, 0.5, "kart", gp):
                    add_bar(bm, pts, X, 0.0050, 0.5 * h, 0.0018, BODY_IDX, filleted=True)
        # pod brackets: straps welded on the nerf bars, their tabs bolted flat
        # to the pod's inner wall
        for k, x in enumerate((0.160, -0.220)):
            y_in = 0.470
            yt = s * (y_in - tab)
            # the strap stands across the bar: sunk until its corners are under
            # the bar's surface
            p0 = Vector((x, s * 0.452, 0.0715 + 0.0040))
            with b.part(T_BRACKET, 0.5, "kart"):
                add_strap(bm, [p0, Vector((x, s * 0.452, 0.094)), Vector((x, yt, 0.104)),
                               Vector((x, yt, 0.150))], X)
            with b.part(T_NONE, 0.5, "kart"):
                add_dome(bm, Vector((x, yt - s * (half_t - 0.0008), 0.132)), -Y * s, CHROME_IDX,
                         r=0.0060, h=0.0034)
    if flags["float_nose"]:
        for v in b.groups["nose"]:
            v.co.x += FLOAT_NOSE


def build_rear_bumper(b):
    bm = b.bm
    zt, zl, xb = 0.150, 0.078, -0.810
    top = [Vector((-0.700, 0.680, zt)), Vector((-0.790, 0.640, zt)), Vector((xb, 0.500, zt)),
           Vector((xb, -0.500, zt)), Vector((-0.790, -0.640, zt)), Vector((-0.700, -0.680, zt))]
    with b.part(T_NONE, 0.5, "kart"):
        add_tube(bm, fillet_path(top, 0.07, 7), 0.0140, 14, CHROME_IDX)
    for s in (-1.0, 1.0):
        with b.part(T_NONE, 0.5, "kart"):
            lathe_on(bm, [(0.0125, -0.004), (0.0150, 0.000), (0.0150, 0.010), (0.0110, 0.016)],
                     14, BLACK_IDX, Vector((-0.700, s * 0.680, zt)),
                     (Vector((-0.700, s * 0.680, zt)) - Vector((-0.790, s * 0.640, zt))).normalized())
    with b.part(T_NONE, 0.5, "kart"):
        add_tube(bm, [Vector((xb + 0.004, -0.400, zl)), Vector((xb + 0.004, 0.400, zl))], 0.0120,
                 14, CHROME_IDX)
    for s in (-1.0, 1.0):
        with b.part(T_NONE, 0.5, "kart"):
            add_tube(bm, [Vector((xb, s * 0.300, zt - 0.006)), Vector((xb + 0.004, s * 0.300, zl - 0.004))],
                     0.0100, 12, CHROME_IDX)
        with b.part(T_NONE, 0.5, "kart"):
            add_tube(bm, fillet_path([Vector((-0.660, s * 0.200, Z_F)),
                                      Vector((-0.740, s * 0.225, 0.100)),
                                      Vector((xb + 0.006, s * 0.260, zt - 0.004))], 0.05, 5),
                     0.0120, 12, CHROME_IDX)


def build_floor_and_pedals(b):
    bm = b.bm
    ztop = Z_F - TUBE_R + 0.0008
    left = [(-0.100, 0.292), (0.020, 0.252), (0.340, 0.252), (0.440, 0.344), (0.560, 0.344)]
    outline = [(x, y) for x, y in left] + [(x, -y) for x, y in reversed(left)]
    outline = [(x, y) for x, y in outline]
    if poly_area(outline) < 0.0:
        outline.reverse()
    with b.part(T_NONE, 0.5, "kart"):
        add_prism(bm, outline, ztop - 0.003, ztop, (0.0, 0.0, 0.0), Matrix.Identity(3), ALU_IDX,
                  ch=0.0006)
    # pedals: pivot plates off the front crossmember, arms leaning back
    for s in (-1.0, 1.0):
        yc = s * 0.120
        piv = Vector((0.540, yc, 0.088))
        rot = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)))
        plate = circles_hull([(piv.x, piv.z, 0.014), (0.590, Z_F, 0.010), (0.610, Z_F, 0.010)], 16)
        yp = yc + s * 0.020
        with b.part(T_FRAME, 0.5, "kart"):
            add_prism(bm, plate, yp - 0.0025, yp + 0.0025, (0.0, 0.0, 0.0), rot, PAINT_IDX,
                      ch=0.0005)
        with b.part(T_NONE, 0.5, "kart"):
            add_rod(bm, piv, Y * s, -0.020, 0.026, 0.0055, CHROME_IDX)
        with b.part(T_NONE, 0.5, "kart"):
            lathe_on(bm, [(0.0050, -0.014), (0.0110, -0.014), (0.0120, -0.012), (0.0120, 0.012),
                          (0.0110, 0.014), (0.0050, 0.014)], 16, ALU_IDX, piv, Y, solid=False)
        top = Vector((0.462, yc, 0.246))
        with b.part(T_NONE, 0.5, "kart"):
            add_bar(bm, [piv + Vector((0.0, 0.0, 0.002)), Vector((0.522, yc, 0.150)), top], Y, 0.009,
                    0.004, 0.002, ALU_IDX, fillet=0.03)
        back = Vector((-0.55, 0.0, 0.83)).normalized()
        rotp = frame(back, Y)
        with b.part(T_NONE, 0.5, "kart"):
            add_rbox(bm, 0.038, 0.030, 0.008, chamfered(0.006, 0.0012), top - back * 0.004, rotp,
                     ALU_IDX, n_corner=3)
        with b.part(T_NONE, 0.35, "kart"):
            add_rbox(bm, 0.034, 0.026, 0.007, chamfered(0.0030, 0.0008), top + back * 0.0015,
                     rotp, RUBBER_IDX, n_corner=3)


def build_tank(b, xe):
    bm = b.bm
    ztray = Z_F - TUBE_R + 0.0008
    x0, x1 = 0.180, 0.340
    with b.part(T_NONE, 0.5, "kart"):
        add_rbox(bm, 0.5 * (x1 - x0), 0.075, 0.030, [(0.010, 0.0), (0.0, 0.010), (0.0, 0.112),
                                                     (0.016, 0.126)],
                 (0.5 * (x0 + x1), 0.0, ztray - 0.001), Matrix.Identity(3), TANK_IDX, n_corner=4)
    top = ztray - 0.001 + 0.126
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.022, -0.004), (0.024, 0.004), (0.024, 0.014), (0.020, 0.018),
                      (0.010, 0.019)], 20, BLACK_IDX, Vector((0.290, 0.022, top)), Z)
    # hold-down strap over the tank, its feet bolted to the tray
    xs = 0.225
    strap = [Vector((xs, -0.102, ztray + 0.0006)), Vector((xs, -0.0755, ztray + 0.0006)),
             Vector((xs, -0.0755, top - 0.014)), Vector((xs, -0.058, top + 0.0010)),
             Vector((xs, 0.058, top + 0.0010)), Vector((xs, 0.0755, top - 0.014)),
             Vector((xs, 0.0755, ztray + 0.0006)), Vector((xs, 0.102, ztray + 0.0006))]
    with b.part(T_NONE, 0.5, "kart"):
        add_bar(bm, fillet_path(strap, 0.006, 3), X, 0.012, 0.0014, 0.0008, BLACK_IDX,
                filleted=True)
    for k, yy in enumerate((-0.093, 0.093)):
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, Vector((xs, yy, 0.0)), Z, ztray + 0.0016, ztray + 0.0062 + 0.0002 * k,
                    0.0060, CHROME_IDX)
    # fuel line from the tank's foot to the carburettor
    line = [Vector((0.188, -0.050, ztray + 0.014)), Vector((0.120, -0.090, ztray + 0.008)),
            Vector((0.010, -0.190, ztray + 0.008)), Vector((-0.080, -0.205, ztray + 0.010)),
            Vector((xe + 0.150, -0.214, 0.120)), Vector((xe + 0.140, -0.262, 0.240)),
            Vector((xe + 0.128, -0.300, 0.262))]
    with b.part(T_NONE, 0.5, "kart"):
        add_tube(bm, fillet_path(line, 0.04, 5), 0.0038, 8, RUBBER_IDX)


def rail_run(s, x_hi, x_lo, bumps=(0.160, -0.220)):
    """Points along the top outer shoulder of the left (s=+1) or right rail
    from ``x_hi`` back to ``x_lo``, for a line clipped to the rail; lifted
    over the nerf bars' roots."""
    pts = [p for p in loop_path() if p.y * s > 0.05 and x_lo <= p.x <= x_hi]
    pts.sort(key=lambda p: -p.x)
    out = []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]
        c = pts[min(i + 1, len(pts) - 1)]
        t = (c - a).normalized()
        o = Vector((-t.y, t.x, 0.0))
        if o.y * s < 0.0:
            o = -o
        q = p + (o + Z) * (0.7071 * (TUBE_R + 0.0032))
        for xb in bumps:
            q.z += 0.0040 * max(0.0, 1.0 - abs(p.x - xb) / 0.030)
        out.append(q)
    return out


def build_controls(b, xe, wd):
    """Brake master cylinder on the tray, pushed by the left pedal, its hose
    clipped along the left rail to the caliper; the throttle cable from the
    right pedal along the right rail and up to the carburettor."""
    bm = b.bm
    ztray = Z_F - TUBE_R + 0.0008
    mc = Vector((0.400, 0.170, 0.072))
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.0105, -0.035), (0.0125, -0.032), (0.0125, 0.030), (0.0105, 0.035)], 20,
                 ALU_IDX, mc, X)
    with b.part(T_NONE, 0.35, "kart"):
        lathe_on(bm, [(0.0080, 0.034), (0.0092, 0.038), (0.0078, 0.042), (0.0090, 0.046),
                      (0.0050, 0.050)], 14, RUBBER_IDX, mc, X)
    with b.part(T_NONE, 0.5, "kart"):
        add_rbox(bm, 0.016, 0.019, 0.004, chamfered(mc.z - 0.0115 - ztray + 0.001, 0.0010),
                 (mc.x + 0.0037, mc.y, ztray - 0.001), Matrix.Identity(3), ALU_IDX, n_corner=2)
    ztop = mc.z - 0.0115
    for k, (dx, dy) in enumerate(((-0.009, 0.0148), (0.009, -0.0148))):
        with b.part(T_NONE, 0.5, "kart"):
            add_hex(bm, Vector((mc.x + 0.0037 + dx, mc.y + dy, 0.0)), Z, ztop - 0.0003 - 0.00015 * k,
                    ztop + 0.0040 + 0.0002 * k, 0.0038, CHROME_IDX)
    res = mc + Vector((-0.012, 0.0, 0.0115))
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.0090, -0.002), (0.0095, 0.004), (0.0095, 0.028), (0.0085, 0.031)], 16,
                 TANK_IDX, res, Z)
    with b.part(T_NONE, 0.5, "kart"):
        lathe_on(bm, [(0.0102, 0.0295), (0.0108, 0.031), (0.0108, 0.037), (0.0060, 0.040)], 16,
                 BLACK_IDX, res, Z)
    # pushrod from the boot to the brake pedal's arm
    with b.part(T_NONE, 0.5, "kart"):
        add_rod(bm, mc, (Vector((0.528, 0.120, 0.130)) - mc).normalized(), 0.044,
                (Vector((0.528, 0.120, 0.130)) - mc).length, 0.0035, STEEL_IDX, segs=10)
    # brake hose: out of the cylinder's back, along the left rail, up to the caliper
    ca = math.radians(140.0)
    cc = Vector((AX_R + 0.074 * math.cos(ca), wd, Z_AR + 0.074 * math.sin(ca)))
    run = rail_run(1.0, 0.300, -0.400)
    hose = ([mc + Vector((-0.030, 0.0, 0.0)), mc + Vector((-0.050, 0.004, -0.002)),
             Vector((0.330, 0.215, run[0].z + 0.004))] + run
            + [Vector((-0.430, 0.286, 0.100)), Vector((-0.470, 0.268, 0.165)),
               Vector((-0.520, 0.262, 0.212)), Vector((-0.550, 0.255, 0.214)),
               cc + Vector((0.011, 0.016, 0.018))])
    with b.part(T_NONE, 0.5, "kart"):
        add_tube(bm, fillet_path(hose, 0.03, 2), 0.0040, 8, RUBBER_IDX)
    # throttle cable: from the right pedal's arm, along the right rail, up
    # inboard of the air-box and down onto the carburettor
    run = rail_run(-1.0, 0.330, 0.000)
    cable = ([Vector((0.528, -0.120, 0.130)), Vector((0.500, -0.160, 0.100)),
              Vector((0.440, -0.205, 0.080))] + run
             + [Vector((-0.030, -0.226, 0.150)), Vector((-0.060, -0.222, 0.300)),
                Vector((-0.095, -0.226, 0.345)), Vector((xe + 0.163, -0.255, 0.352)),
                Vector((xe + 0.153, -0.300, 0.318)), Vector((xe + 0.153, -0.310, 0.278))])
    with b.part(T_NONE, 0.5, "kart"):
        add_tube(bm, fillet_path(cable, 0.03, 2), 0.0025, 6, BLACK_IDX)


def build_ballast(b, aft, loose):
    """Lead plates stacked on the floor tray and bolted through it."""
    bm = b.bm
    x0, x1, y0, y1 = BALLAST_AFT if aft else BALLAST
    z = (Z_F - TUBE_R + 0.0008) if not aft else (Z_F + CROSS_R + 0.010)
    for k in range(BALLAST_PLATES):
        zk = z - 0.0005 + k * (BALLAST_T - 0.0005)
        with b.part(T_BALLAST, 0.3 + 0.2 * k, "kart", "ballast"):
            # each plate 0.6 mm smaller all round: stacked copies share side planes
            sh = 0.0006 * k
            add_rbox(bm, 0.5 * (x1 - x0) - sh, 0.5 * (y1 - y0) - sh, 0.006 - 0.5 * sh,
                     chamfered(BALLAST_T, 0.0012),
                     (0.5 * (x0 + x1), 0.5 * (y0 + y1), zk), Matrix.Identity(3), LEAD_IDX,
                     n_corner=2)
    ztop = z - 0.0005 + BALLAST_PLATES * (BALLAST_T - 0.0005) + 0.0005
    for k, dx in enumerate((-0.060, 0.060)):
        with b.part(T_NONE, 0.5, "kart", "ballast"):
            add_hex(bm, Vector((0.5 * (x0 + x1) + dx, 0.5 * (y0 + y1), 0.0)), Z, ztop - 0.0004,
                    ztop + 0.0060 + 0.0002 * k, 0.0080, CHROME_IDX)
    if loose:
        for v in b.groups["ballast"]:
            v.co.z += LOOSE_BALLAST


def orient_islands(bm):
    """Outward normals on every closed island, by its signed volume: the
    heuristic in recalc_face_normals turned the nose inside out."""
    bm.faces.index_update()
    seen = [False] * len(bm.faces)
    for f0 in bm.faces:
        if seen[f0.index]:
            continue
        seen[f0.index] = True
        stack, isl = [f0], []
        while stack:
            f = stack.pop()
            isl.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if not seen[g.index]:
                        seen[g.index] = True
                        stack.append(g)
        vol = 0.0
        for f in isl:
            vs = [lp.vert.co for lp in f.loops]
            for k in range(1, len(vs) - 1):
                vol += vs[0].dot(vs[k].cross(vs[k + 1]))
        if vol < 0.0:
            bmesh.ops.reverse_faces(bm, faces=isl)


def build_mesh(name, n_corner, flags):
    bm = bmesh.new()
    _HEX[0] = 0
    _AXL[0] = 0
    try:
        b = Build(bm)
        build_slab(b)
        build_kerb(b)
        build_frame(b, flags)
        caster = 0.0 if flags["no_caster"] else CASTER_DEG
        build_kingpin_brackets(b, caster)
        ends = {}
        for s in (-1.0, 1.0):
            ends[s] = build_front_corner(b, s, caster, TOE_DEG if (flags["toe_wheel"] and s > 0) else 0.0)
        build_steering_column(b)
        build_tie_rods(b, ends, flags["short_tierod"])
        wd = build_rear(b, flags)
        xe = build_drivetrain(b, flags)
        build_engine(b, xe)
        dz = build_seat(b)
        build_seat_mounts(b, dz)
        build_body(b, n_corner, flags)
        build_rear_bumper(b)
        build_floor_and_pedals(b)
        build_tank(b, xe)
        build_controls(b, xe, wd)
        build_ballast(b, flags["aft_ballast"], flags["loose_ballast"])
        # loaded tyres: every tread vertex under the contact plane lies on it
        zc = -SINK
        for v in b.groups["tyres"]:
            if v.co.z < zc:
                v.co.z = zc
        if flags["float_tyre"]:
            for v in b.groups["tyre_cornerL"]:
                v.co.z += FLOAT_TYRE
        # place the kart on the patch
        for v in set(b.groups["kart"]):
            v.co += Vector((KART_X, KART_Y, SLAB_T))
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=DOUBLES_EPS)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        orient_islands(bm)
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
              coat=0.0, wear=0.0, wear_col=(0.5, 0.5, 0.5, 1.0), streak=0.0, hot=None):
    """A designed surface (after traffic-cones): a per-part tone between two
    colours (the PartTone face attribute), grime rising from the asphalt to
    ``dirt_top``, sparse scuffs, roughness breakup and an optional fine bump."""
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
    if hot is not None:
        # oily grime round the engine: distance from its centre, broken up
        hc, hr, hcol, hamt = hot
        dist = nt.nodes.new("ShaderNodeVectorMath")
        dist.operation = "DISTANCE"
        dist.inputs[1].default_value = hc
        nt.links.new(coord.outputs["Object"], dist.inputs[0])
        hm = _node(nt, "ShaderNodeMapRange")
        hm.inputs["From Min"].default_value = 0.0
        hm.inputs["From Max"].default_value = hr
        hm.inputs["To Min"].default_value = hamt
        hm.inputs["To Max"].default_value = 0.0
        nt.links.new(dist.outputs["Value"], hm.inputs["Value"])
        hn = _node(nt, "ShaderNodeTexNoise", Scale=14.0, Detail=8.0)
        nt.links.new(coord.outputs["Object"], hn.inputs["Vector"])
        hr_ = _ramp(nt, 0.30, _gray(0.35), 0.62, _gray(1.0))
        nt.links.new(hn.outputs["Fac"], hr_.inputs["Fac"])
        hmul = nt.nodes.new("ShaderNodeMath")
        hmul.operation = "MULTIPLY"
        hmul.use_clamp = True
        nt.links.new(hm.outputs["Result"], hmul.inputs[0])
        nt.links.new(hr_.outputs["Color"], hmul.inputs[1])
        col = _mix(nt, hmul.outputs["Value"], col, hcol)
    if streak > 0.0 or wear > 0.0:
        # the lower half of a moulding takes the knocks: tyre rubber rubbed on
        # in dark streaks, and light scratches through the surface, both
        # stretched fore and aft
        low = _node(nt, "ShaderNodeMapRange")
        low.inputs["From Min"].default_value = SLAB_T + 0.09
        low.inputs["From Max"].default_value = SLAB_T + 0.20
        low.inputs["To Min"].default_value = 1.0
        low.inputs["To Max"].default_value = 0.20
        nt.links.new(sep.outputs["Z"], low.inputs["Value"])
        for amt, scale, lo_, hi_, mark in ((streak, (0.9, 9.0, 12.0), 0.56, 0.70,
                                            (0.022, 0.021, 0.021, 1.0)),
                                           (wear, (1.4, 34.0, 34.0), 0.63, 0.67, wear_col)):
            if amt <= 0.0:
                continue
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.inputs["Scale"].default_value = scale
            nt.links.new(coord.outputs["Object"], mp.inputs["Vector"])
            stn = _node(nt, "ShaderNodeTexNoise", Scale=3.0, Detail=8.0)
            nt.links.new(mp.outputs["Vector"], stn.inputs["Vector"])
            str_ = _ramp(nt, lo_, _gray(0.0), hi_, _gray(amt))
            nt.links.new(stn.outputs["Fac"], str_.inputs["Fac"])
            smul = nt.nodes.new("ShaderNodeMath")
            smul.operation = "MULTIPLY"
            nt.links.new(str_.outputs["Color"], smul.inputs[0])
            nt.links.new(low.outputs["Result"], smul.inputs[1])
            col = _mix(nt, smul.outputs["Value"], col, mark)
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


STUDIO = [(0.0, 0.02), (0.30, 0.05), (0.42, 0.45), (0.50, 1.0), (0.62, 0.30), (1.0, 0.12)]


def asphalt_material():
    """Kart-track asphalt: a dark binder with fine light aggregate, darker
    rubbered-in streaks along the racing line, and the aggregate as a bump."""
    mat = bpy.data.materials.new("TrackAsphalt")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 170.0
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    agg = _ramp(nt, 0.0, (0.140, 0.136, 0.130, 1.0), 0.30, (0.026, 0.026, 0.026, 1.0))
    nt.links.new(vor.outputs["Distance"], agg.inputs["Fac"])
    stones = nt.nodes.new("ShaderNodeTexVoronoi")
    stones.inputs["Scale"].default_value = 70.0
    nt.links.new(coord.outputs["Object"], stones.inputs["Vector"])
    coarse = _ramp(nt, 0.0, (0.112, 0.108, 0.100, 1.0), 0.20, (0.026, 0.026, 0.026, 1.0))
    nt.links.new(stones.outputs["Distance"], coarse.inputs["Fac"])
    light = nt.nodes.new("ShaderNodeMixRGB")
    light.blend_type = "LIGHTEN"
    light.inputs[0].default_value = 1.0
    nt.links.new(agg.outputs["Color"], light.inputs[1])
    nt.links.new(coarse.outputs["Color"], light.inputs[2])
    # rubber laid down in streaks along X (the racing line)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs[0])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    mul_x = nt.nodes.new("ShaderNodeMath")
    mul_x.operation = "MULTIPLY"
    mul_x.inputs[1].default_value = 0.08
    nt.links.new(sep.outputs["X"], mul_x.inputs[0])
    nt.links.new(mul_x.outputs["Value"], comb.inputs["X"])
    mul_y = nt.nodes.new("ShaderNodeMath")
    mul_y.operation = "MULTIPLY"
    mul_y.inputs[1].default_value = 3.0
    nt.links.new(sep.outputs["Y"], mul_y.inputs[0])
    nt.links.new(mul_y.outputs["Value"], comb.inputs["Y"])
    streak = _node(nt, "ShaderNodeTexNoise", Scale=2.2, Detail=5.0)
    nt.links.new(comb.outputs["Vector"], streak.inputs["Vector"])
    sr = _ramp(nt, 0.40, _gray(1.0), 0.66, _gray(0.52))
    nt.links.new(streak.outputs["Fac"], sr.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(light.outputs[0], mul.inputs[1])
    nt.links.new(sr.outputs["Color"], mul.inputs[2])
    nt.links.new(mul.outputs[0], bsdf.inputs["Base Color"])
    rr = _ramp(nt, 0.40, _gray(0.86), 0.66, _gray(0.62))
    nt.links.new(streak.outputs["Fac"], rr.inputs["Fac"])
    nt.links.new(rr.outputs["Color"], bsdf.inputs["Roughness"])
    hsum = nt.nodes.new("ShaderNodeMath")
    hsum.operation = "ADD"
    nt.links.new(vor.outputs["Distance"], hsum.inputs[0])
    nt.links.new(stones.outputs["Distance"], hsum.inputs[1])
    bp = _node(nt, "ShaderNodeBump", Strength=0.35)
    bp.inputs["Distance"].default_value = 0.002
    nt.links.new(hsum.outputs["Value"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def kerb_material():
    """Kerb paint: the stripe tone picks red or white, worn through to the
    concrete on the crest and streaked with tyre rubber."""
    mat = bpy.data.materials.new("KerbPaint")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = TONE
    paint = _mix(nt, attr.outputs["Fac"], (0.78, 0.77, 0.74, 1.0), (0.62, 0.035, 0.028, 1.0))
    wear = _node(nt, "ShaderNodeTexNoise", Scale=16.0, Detail=9.0)
    nt.links.new(coord.outputs["Object"], wear.inputs["Vector"])
    wr = _ramp(nt, 0.30, _gray(1.0), 0.36, _gray(0.0))
    nt.links.new(wear.outputs["Fac"], wr.inputs["Fac"])
    worn = _mix(nt, wr.outputs["Color"], paint, (0.20, 0.19, 0.18, 1.0))
    rub = _node(nt, "ShaderNodeTexNoise", Scale=5.0, Detail=4.0)
    nt.links.new(coord.outputs["Object"], rub.inputs["Vector"])
    rbr = _ramp(nt, 0.52, _gray(0.0), 0.70, _gray(0.55))
    nt.links.new(rub.outputs["Fac"], rbr.inputs["Fac"])
    col = _mix(nt, rbr.outputs["Color"], worn, (0.03, 0.03, 0.03, 1.0))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.62
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 120.0
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    bp = _node(nt, "ShaderNodeBump", Strength=0.2)
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


def set_materials():
    """Slot order: frame paint, chrome/zinc, rubber, bodywork, seat,
    aluminium, engine casting, dark steel, black plastic, fuel tank, lead,
    asphalt, kerb paint, number plate. Shared by the check and the render.
    The bodywork is blue with a white plate, so the warm accents are the
    red frame and kerb: the yellow livery this piece first shipped with
    filled the lower half of the hero and pushed the wedge warmth to
    +0.288, out of the calibration band."""
    eng = Vector((engine_x() + KART_X, -0.305 + KART_Y, Z_ENG + SLAB_T))
    oil = (0.030, 0.025, 0.020, 1.0)
    paint = weathered("FramePaint", (0.58, 0.035, 0.022, 1.0), (0.50, 0.030, 0.026, 1.0), 0.30,
                      (0.12, 0.08, 0.05, 1.0), 0.10, 0.6, (0.20, 0.17, 0.15, 1.0), 0.45,
                      scuff_scale=30.0, coat=0.35, wear=0.75, wear_col=(0.26, 0.25, 0.24, 1.0),
                      hot=(eng, 0.34, oil, 0.80))
    add_studio(paint, (0.55, 0.20, 0.18, 1.0), 0.10, STUDIO)
    chrome = weathered("Chrome", (0.80, 0.80, 0.82, 1.0), (0.74, 0.75, 0.77, 1.0), 0.14,
                       (0.25, 0.22, 0.19, 1.0), 0.08, 0.5, (0.45, 0.44, 0.42, 1.0), 0.3,
                       metallic=1.0, rough_var=0.05, scuff_scale=40.0, hot=(eng, 0.30, oil, 0.55))
    add_studio(chrome, (0.70, 0.72, 0.76, 1.0), 0.75, STUDIO)
    rubber = weathered("TyreRubber", (0.034, 0.033, 0.032, 1.0), (0.046, 0.044, 0.042, 1.0), 0.72,
                       (0.13, 0.12, 0.11, 1.0), 0.02, 0.5, (0.075, 0.072, 0.07, 1.0), 0.8,
                       scuff_scale=26.0, bump=0.15, bump_scale=700.0)
    body = weathered("Bodywork", (0.018, 0.090, 0.36, 1.0), (0.014, 0.072, 0.30, 1.0), 0.34,
                     (0.030, 0.034, 0.042, 1.0), 0.08, 0.40, (0.030, 0.085, 0.24, 1.0), 0.45,
                     scuff_scale=30.0, coat=0.35, wear=0.45, wear_col=(0.30, 0.36, 0.48, 1.0),
                     streak=0.75)
    seat = weathered("SeatGlass", (0.060, 0.064, 0.074, 1.0), (0.070, 0.074, 0.084, 1.0), 0.30,
                     (0.12, 0.11, 0.10, 1.0), 0.05, 0.3, (0.16, 0.16, 0.17, 1.0), 0.15,
                     scuff_scale=18.0, coat=1.0, wear=0.5, wear_col=(0.20, 0.20, 0.21, 1.0))
    alu = weathered("Aluminium", (0.70, 0.71, 0.72, 1.0), (0.62, 0.63, 0.64, 1.0), 0.38,
                    (0.26, 0.23, 0.20, 1.0), 0.08, 0.6, (0.50, 0.50, 0.50, 1.0), 0.35,
                    metallic=1.0, rough_var=0.10, scuff_scale=36.0, hot=(eng, 0.30, oil, 0.60))
    add_studio(alu, (0.62, 0.64, 0.67, 1.0), 0.30, STUDIO)
    casting = weathered("EngineCasting", (0.50, 0.50, 0.48, 1.0), (0.42, 0.42, 0.41, 1.0), 0.58,
                        (0.18, 0.15, 0.12, 1.0), 0.30, 0.55, (0.30, 0.28, 0.26, 1.0), 0.55,
                        metallic=0.85, rough_var=0.10, scuff_scale=30.0, bump=0.35,
                        bump_scale=500.0, hot=(eng + Vector((0.0, 0.0, -0.08)), 0.22, oil, 0.55))
    add_studio(casting, (0.50, 0.50, 0.50, 1.0), 0.18, STUDIO)
    steel = weathered("DarkSteel", (0.22, 0.21, 0.20, 1.0), (0.17, 0.16, 0.15, 1.0), 0.40,
                      (0.14, 0.10, 0.07, 1.0), 0.10, 0.5, (0.30, 0.22, 0.15, 1.0), 0.5,
                      metallic=1.0, rough_var=0.10, scuff_scale=24.0, hot=(eng, 0.30, oil, 0.60))
    add_studio(steel, (0.45, 0.45, 0.46, 1.0), 0.30, STUDIO)
    black = weathered("BlackPlastic", (0.024, 0.024, 0.026, 1.0), (0.034, 0.034, 0.036, 1.0), 0.46,
                      (0.14, 0.13, 0.11, 1.0), 0.05, 0.3, (0.11, 0.11, 0.11, 1.0), 0.5)
    tank = weathered("TankPlastic", (0.80, 0.78, 0.72, 1.0), (0.74, 0.72, 0.66, 1.0), 0.36,
                     (0.30, 0.24, 0.16, 1.0), 0.06, 0.4, (0.55, 0.50, 0.42, 1.0), 0.35,
                     scuff_scale=30.0)
    lead = weathered("LeadBallast", (0.31, 0.32, 0.33, 1.0), (0.26, 0.27, 0.28, 1.0), 0.70,
                     (0.14, 0.13, 0.12, 1.0), 0.03, 0.3, (0.44, 0.45, 0.46, 1.0), 0.4,
                     metallic=0.6, scuff_scale=40.0)
    asphalt = asphalt_material()
    kerb = kerb_material()
    plate = weathered("NumberPlate", (0.86, 0.86, 0.84, 1.0), (0.82, 0.82, 0.80, 1.0), 0.32,
                      (0.30, 0.26, 0.20, 1.0), 0.05, 0.3, (0.55, 0.53, 0.50, 1.0), 0.25,
                      scuff_scale=24.0, coat=0.35, wear=0.5, wear_col=(0.48, 0.47, 0.45, 1.0),
                      streak=0.35)
    return (paint, chrome, rubber, body, seat, alu, casting, steel, black, tank, lead, asphalt,
            kerb, plate)


def assign_slots(obj, wanted):
    # Do not materials.clear() - that resets polygon material_index to 0.
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
    def __init__(self, me, idx, verts, polys, tags):
        self.idx = idx
        self.verts = verts
        pts = [me.vertices[i].co.copy() for i in verts]
        self.pts = pts
        self.lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        self.hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        self.size = self.hi - self.lo
        self.centre = (self.lo + self.hi) * 0.5
        self.mean = sum(pts, Vector()) / len(pts)
        mats, tg = {}, {}
        for p in polys:
            mats[p.material_index] = mats.get(p.material_index, 0) + 1
            t = tags[p.index]
            tg[t] = tg.get(t, 0) + 1
        self.mat = max(mats, key=mats.get) if mats else None
        self.mats = set(mats)
        self.tag = max(tg, key=tg.get) if tg else T_NONE
        remap = {vi: n for n, vi in enumerate(verts)}
        self.tri_idx = [[remap[v] for v in p.vertices] for p in polys]
        self.tree = BVHTree.FromPolygons([tuple(p) for p in pts], self.tri_idx)
        self.polys = polys


def pca(pts):
    """(mean, eigenvalues ascending, eigenvectors as columns)."""
    p = np.array([tuple(v) for v in pts], dtype=np.float64)
    c = p.mean(axis=0)
    q = p - c
    w, vecs = np.linalg.eigh(q.T @ q / len(p))
    return Vector(c), w, vecs


def lathe_axis(pts):
    """A body of revolution's axis: the eigenvector whose eigenvalue stands
    apart from the other two (the two radial ones are equal)."""
    c, w, vecs = pca(pts)
    k = 2 if (w[1] - w[0]) < (w[2] - w[1]) else 0
    a = Vector(vecs[:, k])
    return c, a.normalized()


def classify(me):
    groups = shells(me)
    polys = shell_polys(me, groups)
    attr = me.attributes.get("part")
    tags = [0] * len(me.polygons)
    if attr is not None:
        tags = [d.value for d in attr.data]
    parts = [Shell(me, i, g, polys[i], tags) for i, g in enumerate(groups)]
    out = {"all": parts, "groups": groups}
    for key, t in (("slab", T_SLAB), ("kerb", T_KERB), ("loop", T_LOOP), ("tyres", T_TYRE),
                   ("rims", T_RIM), ("hubs_f", T_HUB_F), ("hubs_r", T_HUB_R), ("stubs", T_STUB),
                   ("axles", T_AXLE), ("bearings", T_BEARING), ("kingpins", T_KINGPIN),
                   ("arms", T_ARM), ("tabs", T_TAB), ("pins", T_PIN), ("eyes", T_EYE),
                   ("chains", T_CHAIN), ("sprockets", T_SPROCKET), ("ballast", T_BALLAST),
                   ("brackets", T_BRACKET)):
        out[key] = [s for s in parts if s.tag == t]
    out["slab_top"] = max(s.hi.z for s in out["slab"]) if out["slab"] else 0.0
    out["kart"] = [s for s in parts if s.tag not in (T_SLAB, T_KERB)]
    loop = out["loop"][0] if out["loop"] else None
    out["y_mid"] = 0.5 * (loop.lo.y + loop.hi.y) if loop else 0.0
    return out


def support_audit(cls):
    """Each tyre's lowest vertex under the asphalt's top, read off the slab."""
    top = cls["slab_top"]
    return [top - t.lo.z for t in cls["tyres"]]


def coax(host_pts, part_pts):
    hc, ha = pca_line(host_pts)
    pc, pa = lathe_axis(part_pts)
    if pa.dot(ha) < 0.0:
        pa = -pa
    rel = pc - hc
    off = (rel - ha * rel.dot(ha)).length
    ang = math.degrees(math.acos(min(1.0, abs(pa.dot(ha)))))
    return off, ang


def pca_line(pts):
    c, _w, vecs = pca(pts)
    return c, Vector(vecs[:, 2]).normalized()


def nearest(shells_, p):
    return min(shells_, key=lambda s: (s.mean - p).length) if shells_ else None


def joint_audit(cls):
    """Hubs coaxial with their stubs and the axle; bearings coaxial with the
    axle; tie-rod eyes on their pins and bearing on their plates."""
    res = {"hubs": [], "bearings": [], "eyes": []}
    axle = cls["axles"][0] if len(cls["axles"]) == 1 else None
    for h in cls["hubs_f"]:
        st = nearest(cls["stubs"], h.mean)
        if st is not None:
            res["hubs"].append(("front",) + coax(st.pts, h.pts))
    for h in cls["hubs_r"]:
        if axle is not None:
            res["hubs"].append(("rear",) + coax(axle.pts, h.pts))
    for bg in cls["bearings"]:
        if axle is not None:
            res["bearings"].append(coax(axle.pts, bg.pts))
    plates = cls["arms"] + cls["tabs"]
    for e in cls["eyes"]:
        pin = min(cls["pins"], key=lambda p: math.hypot(p.mean.x - e.mean.x, p.mean.y - e.mean.y)) \
            if cls["pins"] else None
        off = math.hypot(pin.mean.x - e.mean.x, pin.mean.y - e.mean.y) if pin else 9.0
        under = [p for p in plates if p.lo.x - 0.002 <= e.mean.x <= p.hi.x + 0.002
                 and p.lo.y - 0.002 <= e.mean.y <= p.hi.y + 0.002 and p.hi.z <= e.hi.z]
        if under:
            pl = max(under, key=lambda p: p.hi.z)
            # the plate's top face under the eye, read by a ray down onto the plate
            hit = pl.tree.ray_cast(Vector((e.mean.x, e.mean.y, e.hi.z + 0.01)),
                                   Vector((0.0, 0.0, -1.0)), 0.1)[0]
            bite = (hit.z - e.lo.z) if hit is not None else -9.0
        else:
            bite = -9.0
        res["eyes"].append((off, bite))
    return res


def rim_host_radius(rim, c, a, p):
    """The rim's outer surface at the vertex's own station and angle: a ray
    from outside toward the axis, along the vertex's radial."""
    rel = p - c
    s = rel.dot(a)
    q = rel - a * s
    rho = q.length
    if rho < 1e-6:
        return None, rho
    u = q / rho
    origin = c + a * s + u * (rho + 0.03)
    hit, _n, _i, _d = rim.tree.ray_cast(origin, -u, 0.06)
    if hit is None:
        return None, rho
    return (hit - (c + a * s)).length, rho


def tyre_seat_audit(cls):
    """Per tyre, per angular segment, the innermost vertices (the bead)
    against the rim's bead seat read by rays: the seat depth."""
    seats, orphans = [], 0
    for t in cls["tyres"]:
        rim = nearest(cls["rims"], t.mean)
        if rim is None:
            orphans += 1
            continue
        c, a = lathe_axis(rim.pts)
        e1 = (any_perp(a) - a * any_perp(a).dot(a)).normalized()
        e2 = a.cross(e1)
        bins = {}
        for p in t.pts:
            rel = p - c
            q = rel - a * rel.dot(a)
            ang = math.atan2(q.dot(e2), q.dot(e1))
            key = round(ang / (2.0 * math.pi / TYRE_SEGS)) % TYRE_SEGS
            bins.setdefault(key, []).append((q.length, p))
        for key, lst in bins.items():
            rmin = min(r for r, _p in lst)
            for r, p in lst:
                if r > rmin + 0.0002:
                    continue
                hr, rho = rim_host_radius(rim, c, a, p)
                if hr is None:
                    orphans += 1
                    continue
                seats.append(hr - rho)
    return seats, orphans


def chain_audit(cls):
    """Per sprocket: the chain's inner edge against the tooth root circle
    (both read off the mesh) over the middle half of the wrap, and the chain's
    plane against the sprocket's."""
    res = []
    if len(cls["chains"]) != 1:
        return res
    ch = cls["chains"][0]
    for sp in cls["sprockets"]:
        c, a = lathe_axis(sp.pts)
        e1 = (any_perp(a) - a * any_perp(a).dot(a)).normalized()
        e2 = a.cross(e1)
        # a sprocket's vertices lie on three circles: the bore, the tooth
        # roots and the tooth tips
        rho = sorted({round((p - c - a * (p - c).dot(a)).length, 5) for p in sp.pts})
        r_root = rho[1] if len(rho) >= 3 else 9.0
        r_tip = rho[-1]
        # one bin per tooth: four tip vertices per tooth (two per face)
        nb = max(3, sum(1 for p in sp.pts
                        if (p - c - a * (p - c).dot(a)).length > r_tip - 1e-5) // 4)
        mins = [None] * nb
        for p in ch.pts:
            rel = p - c
            q = rel - a * rel.dot(a)
            r = q.length
            if r > r_tip + 0.01:
                continue
            k = int(((math.atan2(q.dot(e2), q.dot(e1)) + math.pi) / (2.0 * math.pi)) * nb) % nb
            if mins[k] is None or r < mins[k]:
                mins[k] = r
        wrap = [m is not None and m < r_tip for m in mins]
        # the longest circular run of wrapped bins, trimmed to its middle half
        best = (0, 0)
        for start in range(nb):
            if wrap[start] and not wrap[start - 1]:
                ln = 0
                while ln < nb and wrap[(start + ln) % nb]:
                    ln += 1
                best = max(best, (ln, start))
        ln, start = best
        core = [mins[(start + i) % nb] for i in range(ln // 4, ln - ln // 4)]
        seat = [r_root - m for m in core if m is not None]
        line = abs(ch.mean.dot(a) - sp.mean.dot(a))
        res.append({"root": r_root, "tip": r_tip, "wrap_deg": ln * 360.0 / nb,
                    "seat_min": min(seat) if seat else -9.0, "seat_max": max(seat) if seat else 9.0,
                    "line": line})
    return res


def mirror_audit(cls):
    """Every frame and bodywork vertex against its mirror partner across the
    loop's centre plane."""
    y0 = cls["y_mid"]
    pts = [p for s in cls["kart"] if s.mat in (PAINT_IDX, BODY_IDX) for p in s.pts]
    if not pts:
        return 9.0, 0
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    worst = 0.0
    for p in pts:
        _co, _i, d = kd.find(Vector((p.x, 2.0 * y0 - p.y, p.z)))
        worst = max(worst, d)
    return worst, len(pts)


def wheel_audit(cls):
    """Tyres paired front and rear: mirror of the pair, wheelbase and both
    tracks from the tyres' own centres."""
    y0 = cls["y_mid"]
    ty = cls["tyres"]
    res = {"mirror": 9.0, "wheelbase": 0.0, "track_f": 0.0, "track_r": 0.0}
    if len(ty) != TYRE_COUNT:
        return res
    xs = sorted(ty, key=lambda s: s.centre.x)
    rear, front = xs[:2], xs[2:]
    worst = 0.0
    for pair in (front, rear):
        L, R = sorted(pair, key=lambda s: -s.centre.y)
        worst = max(worst, abs((L.centre.y - y0) - (y0 - R.centre.y)), abs(L.centre.x - R.centre.x),
                    abs(L.lo.z - R.lo.z), abs(L.size.x - R.size.x), abs(L.size.y - R.size.y),
                    abs(L.size.z - R.size.z))
    res["mirror"] = worst
    res["wheelbase"] = (0.5 * (front[0].centre.x + front[1].centre.x)
                        - 0.5 * (rear[0].centre.x + rear[1].centre.x))
    res["track_f"] = abs(front[0].centre.y - front[1].centre.y)
    res["track_r"] = abs(rear[0].centre.y - rear[1].centre.y)
    return res


def caster_audit(cls):
    out = []
    for k in cls["kingpins"]:
        _c, a = pca_line(k.pts)
        if a.z < 0.0:
            a = -a
        out.append(math.degrees(math.atan2(-a.x, a.z)))
    return out


_RAYS = (Vector((0.5774, 0.5774, 0.5774)), Vector((-0.6247, 0.3123, 0.7158)),
         Vector((0.2673, -0.8018, 0.5345)))


def is_inside(tree, p):
    """Ray parity, majority of three rays: a nearest-face normal misreads a
    point beside a thin plate's rim."""
    votes = 0
    for d in _RAYS:
        n = 0
        o = Vector(p)
        for _ in range(64):
            hit = tree.ray_cast(o, d)[0]
            if hit is None:
                break
            n += 1
            o = hit + d * 1e-6
        votes += n % 2
    return votes >= 2


def inside_depth(host, p):
    """How far ``p`` lies inside the closed shell ``host`` (negative: its
    distance outside): the distance to the nearest face, signed by parity."""
    loc, _nrm, _i, d = host.tree.find_nearest(p)
    if loc is None:
        return -9.0
    return d if is_inside(host.tree, p) else -d


def bracket_audit(cls):
    """Per bracket strap, its bite into each moulding or tube it meets (the
    deepest strap vertex inside that shell, read by nearest-face signed
    distance); the two deepest are the two joints the strap makes."""
    hosts = [s for s in cls["all"] if s.tag in (T_BODY, T_LOOP, T_FRAME, T_BAR)
             and len(s.pts) > 64]
    out = []
    for br in cls["brackets"]:
        lo, hi = br.lo - Vector((0.01, 0.01, 0.01)), br.hi + Vector((0.01, 0.01, 0.01))
        bites = []
        for h in hosts:
            if (h.lo.x > hi.x or h.hi.x < lo.x or h.lo.y > hi.y or h.hi.y < lo.y
                    or h.lo.z > hi.z or h.hi.z < lo.z):
                continue
            bites.append(max(inside_depth(h, p) for p in br.pts))
        bites.sort(reverse=True)
        bites += [-9.0, -9.0]
        out.append((bites[0], bites[1]))
    return out


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
    """Mass centre against the convex hull of the tyres' contact patches."""
    total = 0.0
    mom = Vector()
    for s in cls["kart"]:
        if s.mat is None:
            continue
        vol, cen = shell_mass(s)
        m = abs(vol) * DENSITY[s.mat]
        total += m
        mom += m * cen
    com = mom / total if total > 0.0 else Vector()
    contact = [(p.x, p.y) for t in cls["tyres"] for p in t.pts if p.z < t.lo.z + 1e-5]
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
    # Adapted from snippets/setup_bake_target_image.py - do not replace slots.
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("KartNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = BODY_IDX
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
    low = build_mesh("KartLow", n_corner=2, flags=flags)
    high = build_mesh("KartHigh", n_corner=4, flags=flags)
    mats = set_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    # The bake targets the bodywork: its rounded corners are where the high
    # mesh's fillets differ from the low mesh's.
    target = mats[BODY_IDX]

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
    sinks = support_audit(cls)
    joints = joint_audit(cls)
    seats, orphans = tyre_seat_audit(cls)
    chain = chain_audit(cls)
    mirror, nmirror = mirror_audit(cls)
    wheels = wheel_audit(cls)
    casters = caster_audit(cls)
    stance = stance_audit(cls)
    ncomp, comp_sizes = connected_components(cls)
    brackets = bracket_audit(cls)

    img, tex = setup_bake_image(low, target)
    if img is None:
        return (fail("mesh has no UV layer", 3),) + none3
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "KartLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "KartLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = convex_hull_collider(low, "KartCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_go_kart_{os.getpid()}.glb")
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    hubs = joints["hubs"]
    brg = joints["bearings"]
    eyes = joints["eyes"]
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
          f"tyres={len(cls['tyres'])} sink_mm={[round(s * 1000, 3) for s in sinks]}")
    print(f"measured hubs={[(h[0], round(h[1] * 1000, 4), round(h[2], 4)) for h in hubs]} "
          f"bearings={[(round(o * 1000, 4), round(a, 4)) for o, a in brg]}")
    print(f"measured eyes={[(round(o * 1000, 3), round(bt * 1000, 3)) for o, bt in eyes]}")
    if seats:
        print(f"measured tyre_seat_mm=({min(seats) * 1000:.3f},{max(seats) * 1000:.3f}) "
              f"n={len(seats)} orphans={orphans} rims={len(cls['rims'])}")
    for c in chain:
        print(f"measured chain root={c['root']:.5f} tip={c['tip']:.5f} wrap={c['wrap_deg']:.1f} "
              f"seat_mm=({c['seat_min'] * 1000:.3f},{c['seat_max'] * 1000:.3f}) "
              f"line_mm={c['line'] * 1000:.4f}")
    print(f"measured mirror_mm={mirror * 1000:.4f} (n={nmirror}) wheel_mirror_mm="
          f"{wheels['mirror'] * 1000:.4f} wheelbase={wheels['wheelbase']:.5f} "
          f"track_f={wheels['track_f']:.5f} track_r={wheels['track_r']:.5f} "
          f"caster={[round(c, 3) for c in casters]}")
    print(f"measured mass={stance['mass']:.2f}kg com=({stance['com'].x:.4f},{stance['com'].y:.4f},"
          f"{stance['com'].z:.4f}) margin={stance['margin']:.4f}")
    print(f"measured components={ncomp} sizes={comp_sizes[-5:]}")
    print(f"measured brackets={len(brackets)} bites_mm="
          f"{[(round(a * 1000, 3), round(c * 1000, 3)) for a, c in brackets]}")

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
    if (len(sinks) != TYRE_COUNT or any(not (SINK_MIN <= s <= SINK_MAX) for s in sinks)
            or max(sinks) - min(sinks) > PATCH_PLANE_MAX):
        return (fail(f"tyres: {len(sinks)} (want {TYRE_COUNT}), pressed into the asphalt "
                     f"{[round(s * 1000, 3) for s in sinks]} mm (band [{SINK_MIN * 1000}, "
                     f"{SINK_MAX * 1000}], patches within {PATCH_PLANE_MAX * 1000} mm of one "
                     "plane)", 16),) + none3
    if (len(hubs) != HUBS or len(brg) != BEARINGS or len(eyes) != EYES
            or any(o > COAX_MAX or a > COAX_DEG_MAX for _k, o, a in hubs)
            or any(o > COAX_MAX or a > COAX_DEG_MAX for o, a in brg)
            or any(o > EYE_OFF_MAX or not (EYE_BITE_MIN <= bt <= EYE_BITE_MAX) for o, bt in eyes)):
        return (fail(f"joint fit: hubs {[(k, round(o * 1000, 3), round(a, 3)) for k, o, a in hubs]}, "
                     f"bearings {[(round(o * 1000, 3), round(a, 3)) for o, a in brg]} (off the axis "
                     f"<= {COAX_MAX * 1000} mm, {COAX_DEG_MAX} deg); eyes "
                     f"{[(round(o * 1000, 3), round(bt * 1000, 3)) for o, bt in eyes]} (off the pin "
                     f"<= {EYE_OFF_MAX * 1000} mm, bite [{EYE_BITE_MIN * 1000}, "
                     f"{EYE_BITE_MAX * 1000}] mm)", 17),) + none3
    if (len(cls["tyres"]) != TYRE_COUNT or orphans or not seats
            or min(seats) < TYRE_SEAT_MIN or max(seats) > TYRE_SEAT_MAX
            or len(chain) != SPROCKETS
            or any(c["seat_min"] < CHAIN_SEAT_MIN or c["seat_max"] > CHAIN_SEAT_MAX
                   or c["line"] > CHAINLINE_MAX for c in chain)):
        return (fail(f"seat: tyre beads {min(seats) * 1000 if seats else 0:.3f}.."
                     f"{max(seats) * 1000 if seats else 0:.3f} mm (band [{TYRE_SEAT_MIN * 1000}, "
                     f"{TYRE_SEAT_MAX * 1000}]), orphans {orphans}; chain "
                     f"{[(round(c['seat_min'] * 1000, 3), round(c['seat_max'] * 1000, 3), round(c['line'] * 1000, 3)) for c in chain]}"
                     f" mm (band [{CHAIN_SEAT_MIN * 1000}, {CHAIN_SEAT_MAX * 1000}], line <= "
                     f"{CHAINLINE_MAX * 1000})", 18),) + none3
    if (mirror > MIRROR_EPS or wheels["mirror"] > WHEEL_MIRROR_EPS
            or abs(wheels["wheelbase"] - WHEELBASE) > SIZE_TOL
            or abs(wheels["track_f"] - TRACK_F) > SIZE_TOL
            or abs(wheels["track_r"] - TRACK_R) > SIZE_TOL
            or len(casters) != KINGPINS or any(not (CASTER_MIN <= c <= CASTER_MAX) for c in casters)):
        return (fail(f"mirror/size/angle: frame mirror {mirror * 1000:.3f} mm, wheels "
                     f"{wheels['mirror'] * 1000:.3f} mm (eps {MIRROR_EPS * 1000}), wheelbase "
                     f"{wheels['wheelbase']:.4f}, tracks {wheels['track_f']:.4f} / "
                     f"{wheels['track_r']:.4f} (+- {SIZE_TOL}), caster "
                     f"{[round(c, 3) for c in casters]} deg (band [{CASTER_MIN}, {CASTER_MAX}])",
                     19),) + none3
    if stance["margin"] < STANCE_MARGIN:
        return (fail(f"stance: mass centre {stance['margin']:.4f} m inside the support polygon "
                     f"< {STANCE_MARGIN:.4f}", 20),) + none3
    if ncomp != 1:
        return (fail(f"assembly splits into {ncomp} components {comp_sizes}", 21),) + none3
    if (len(brackets) != BRACKETS
            or any(not (BRACKET_BITE_MIN <= v <= BRACKET_BITE_MAX) for pair in brackets for v in pair)):
        return (fail(f"brackets: {len(brackets)} (want {BRACKETS}), bites "
                     f"{[(round(a * 1000, 3), round(c * 1000, 3)) for a, c in brackets]} mm "
                     f"(band [{BRACKET_BITE_MIN * 1000}, {BRACKET_BITE_MAX * 1000}])", 23),) + none3
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
    # behind to lift the kart off the wall, and the warm wedge pooled on the
    # back wall.
    light("Key", (-1.6, -3.8, 3.6), 156.0, 2.6, (1.0, 0.95, 0.90), spread=34.0)
    light("Fill", (4.2, -2.2, 1.0), 34.0, 6.0, (0.72, 0.82, 1.0))
    light("Rim", (-1.8, 2.6, 2.4), 100.0, 2.2, (0.62, 0.78, 1.0))
    light("Wedge", (-1.4, 2.8, 1.8), 165.0, 3.6, (1.0, 0.76, 0.50),
          target=(centre.x - 0.8, WALL_Y, 0.5))

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
    # Standard, not AgX: AgX washes the blue bodywork and the red paint grey
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
    p.add_argument("--float-tyre", action="store_true")
    p.add_argument("--cock-hub", action="store_true")
    p.add_argument("--drop-bearing", action="store_true")
    p.add_argument("--short-tierod", action="store_true")
    p.add_argument("--sink-tyre", action="store_true")
    p.add_argument("--lift-chain", action="store_true")
    p.add_argument("--toe-wheel", action="store_true")
    p.add_argument("--wide-track", action="store_true")
    p.add_argument("--odd-frame", action="store_true")
    p.add_argument("--no-caster", action="store_true")
    p.add_argument("--aft-ballast", action="store_true")
    p.add_argument("--loose-ballast", action="store_true")
    p.add_argument("--float-nose", action="store_true")
    args = p.parse_args(argv)

    code, low, target, tex = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_tyre=args.float_tyre,
        cock_hub=args.cock_hub,
        drop_bearing=args.drop_bearing,
        short_tierod=args.short_tierod,
        sink_tyre=args.sink_tyre,
        lift_chain=args.lift_chain,
        toe_wheel=args.toe_wheel,
        wide_track=args.wide_track,
        odd_frame=args.odd_frame,
        no_caster=args.no_caster,
        aft_ballast=args.aft_ballast,
        loose_ballast=args.loose_ballast,
        float_nose=args.float_nose,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, target, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("go-kart OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
