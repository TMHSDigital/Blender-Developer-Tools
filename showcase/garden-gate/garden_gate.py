"""Game-ready hinged garden gate — a showcase piece, not an example.

Asserts budget conformance of a procedural ledged-and-braced garden gate:
six bow-topped vertical boards on three back ledges and two diagonal
braces, hung from a squared hinge post on two hook-and-band hinges, with
a barrel bolt on the back, a keeper staple on the latch post and a ring
pull on the front, both posts set into a packed-earth slab. Carried
through UVs, three materials (timber, forged iron, ground), a high-to-low
normal bake, an LOD chain, a compound convex collider, and a Unity glTF
export.

The budget that matters is the one a hinge fails invisibly: a pin in a
knuckle. A hook-and-band hinge is a rolled eye on the end of a strap,
dropped over an upright pin on a hook driven into the post. Off by a
millimetre the eye still sits on the hook in every picture, but the eye
binds or the pin is not inside it; tilt one pin and the two hinges no
longer share an axis, so the gate cannot turn. And the gate has to clear
the latch post as it swings, which no picture of a closed gate shows.
The piece measures every knuckle's axis and bore off its own vertices,
every pin's axis off its own end rings, and the swing circle of the
whole gate about the measured hinge axis.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--offset-knuckle`` the knuckle on
its pin, ``--lift-gate`` the knuckles' seat on the hooks,
``--tilt-pintle`` the plumb shared hinge axis, ``--tight-post`` the swing
clearance at the latch post.

No randomness. DECIMATE COLLAPSE triangle counts are not byte-identical
across Blender versions — the LOD gate is a ratio band.

    blender --background --python garden_gate.py --
    blender --background --python garden_gate.py -- --tight-post
    blender --background --python garden_gate.py -- --output garden_gate.png
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
from mathutils.kdtree import KDTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402
import gallery_asset_quality  # noqa: E402

# --- dimensions, metres. X along the gate, Y through it (front is -Y), Z up.
# A 900 mm ledged-and-braced gate between 100 mm posts. Hook-and-band hinges
# are sized at a third of the gate width (400 x 38 x 4.5 mm straps, 12 mm
# pins), the usual rule for a timber garden gate of this weight.

SLAB_X0, SLAB_X1, SLAB_Y, SLAB_TOP = -0.25, 1.31, 0.28, 0.04
PAD_HALF, FLAG_JOINT = 0.25, 0.012
FLAG_TOPS = (0.036, 0.043, 0.041, 0.034)
POST_W = 0.100
POST_BED = 0.020            # posts sunk this far into the slab
POST_TOP, POST_APEX = 1.200, 1.245
HINGE_POST_X = 0.0
GATE_X0, BOARD_W, BOARD_GAP, BOARDS = 0.080, 0.145, 0.006, 6
GATE_W = BOARDS * BOARD_W + (BOARDS - 1) * BOARD_GAP          # 0.900
GATE_X1 = GATE_X0 + GATE_W                                    # 0.980
LATCH_POST_X = GATE_X1 + 0.030 + POST_W * 0.5                 # 1.060
BOARD_T = 0.022
BOARD_Z0, BOARD_SIDE, BOARD_MID = 0.100, 1.000, 1.060
LEDGE_X0, LEDGE_X1, LEDGE_H, LEDGE_Y0, LEDGE_Y1 = 0.100, 0.960, 0.095, 0.010, 0.033
LEDGE_ZC = (0.220, 0.580, 0.880)
BRACE_W, BRACE_Y0, BRACE_Y1, BRACE_BITE = 0.085, 0.0105, 0.030, 0.002

# Hinges. The knuckle (rolled eye) is a tube round the pin; the strap runs
# from it along the board fronts; the hook's shank is driven into the post.
AXIS_X = 0.065
AXIS_Y = -0.0133
STRAP_L, STRAP_H, STRAP_Y0, STRAP_Y1 = 0.400, 0.038, -0.0160, -0.0105
STRAP_TAPER, STRAP_TIP_H = 0.060, 0.020
KNUCKLE_RI, KNUCKLE_RO, KNUCKLE_HH = 0.0066, 0.0112, 0.0200
PIN_R, PIN_ABOVE = 0.0060, 0.008
SHANK_S, SHANK_X0 = 0.014, -0.020
SEAT_BITE = 0.0005          # knuckle bottom this far below the hook's top
HINGE_ZC = (LEDGE_ZC[0], LEDGE_ZC[2])

# Latch: a barrel bolt on the middle ledge's back, a keeper staple on the
# latch post's inner face, a ring pull on the front.
BOLT_ZC = LEDGE_ZC[1]
BOLT_X0, BOLT_X1, BOLT_R = 0.830, 0.955, 0.006
BOLT_Y = LEDGE_Y1 + 0.003 + 0.007
KEEPER_X0, KEEPER_BITE, KEEPER_Y0, KEEPER_Y1, KEEPER_HH = -0.016, 0.006, 0.031, 0.055, 0.016
RING_X, RING_Z, RING_R, RING_TUBE = 0.890, 0.700, 0.030, 0.0042

# Falsifier magnitudes.
OFFSET_KNUCKLE = 0.0015
LIFT_GATE = 0.003
TILT_PINTLE = 0.06          # shear dx/dz about the knuckle's mid height
TIGHT_POST = 0.014
LIFT_Z = 0.05
RENDER_SWING_DEG = 24.0

BBOX_TOL = 0.020
OUTER_SIZE = (1.560, 0.560, 1.245)

BASE_TRIS_MIN = 3100
BASE_TRIS_MAX = 3550
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
FACE_FLOORS = {0: 330, 1: 1400, 2: 140}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 400
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05

COAX_TOL = 0.0003           # knuckle axis to pin axis, in plan, at the knuckle
BORE_MIN, BORE_MAX = 0.0003, 0.0010     # radial clearance, pin in knuckle
SEAT_MIN, SEAT_MAX = -0.0010, -0.0002   # knuckle bottom minus hook top
PLUMB_TOL = 0.0002          # pin top ring vs bottom ring, in plan
PAIR_TOL = 0.0003           # lower pin axis vs upper pin axis, in plan
SWING_MIN, SWING_MAX = 0.008, 0.030     # latch post outside the swing circle
GATE_W_TOL, GATE_H, GATE_H_TOL = 0.003, BOARD_MID - BOARD_Z0, 0.005
POST_H, POST_H_TOL = POST_APEX - SLAB_TOP, 0.005
STRAP_L_TOL, PIN_D, PIN_D_TOL = 0.005, 2 * PIN_R, 0.0005

TIMBER_IDX = 0
IRON_IDX = 1
GROUND_IDX = 2

# Part ids, a face attribute written at build time; shells take their
# part from their faces. 0 is "not yet tagged".
P_SLAB, P_POST_H, P_POST_L, P_BOARD, P_LEDGE, P_BRACE = 1, 2, 3, 4, 5, 6
P_STRAP, P_KNUCKLE, P_PIN, P_SHANK, P_BOLTHEAD, P_NAIL = 7, 8, 9, 10, 11, 12
P_LATCH, P_KEEPER, P_RING = 13, 14, 15
GATE_PARTS = {P_BOARD, P_LEDGE, P_BRACE, P_STRAP, P_KNUCKLE, P_BOLTHEAD, P_NAIL,
              P_LATCH, P_RING}
OBSTACLE_PARTS = {P_POST_L, P_KEEPER}


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


# --- construction -----------------------------------------------------------


class Builder:
    """One bmesh; every part is built, chamfered, then tagged with its part
    id, material and grain direction (faces still at part 0 are the new ones)."""

    def __init__(self, hi):
        self.bm = bmesh.new()
        self.hi = hi
        self.part = self.bm.faces.layers.int.new("Part")
        self.grain = self.bm.faces.layers.float.new("GrainDir")
        self.smooth = set()

    def seg(self, n):
        return n * 2 if self.hi else n

    def tag(self, part, mat, grain=0.0, smooth=False):
        new = [f for f in self.bm.faces if f[self.part] == 0]
        for f in new:
            f[self.part] = part
            f[self.grain] = grain
            f.material_index = mat
            if smooth:
                self.smooth.add(f)
        return new


def loft(bm, rings, cap=True):
    """Quads between consecutive rings (closed loops); n-gon caps at both ends."""
    faces = []
    for a, b in zip(rings, rings[1:]):
        n = len(a)
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    if cap:
        faces.append(bm.faces.new(rings[0]))
        faces.append(bm.faces.new(list(reversed(rings[-1]))))
    return faces


def chamfer(bm, faces, offset, mat):
    """One-segment chamfer on the shell's near-right-angle edges only.

    ``recalc_face_normals`` comes first: the dihedral is read off face
    normals. The bevel's own faces take ``mat`` explicitly; left alone they
    take slot 0. Edges are sorted by index so the operator input is stable.
    """
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    own = set(faces)
    bm.edges.index_update()
    edges = sorted({e for f in faces for e in f.edges}, key=lambda e: e.index)
    pick = [e for e in edges
            if len(e.link_faces) == 2 and all(lf in own for lf in e.link_faces)
            and math.radians(60.0) <= e.calc_face_angle(0.0) <= math.radians(120.0)]
    if pick and offset > 0.0:
        bmesh.ops.bevel(bm, geom=pick, offset=offset, segments=1, profile=0.5,
                        affect="EDGES", clamp_overlap=True, material=mat)


def prism(bm, outline, axis, d0, d1, off, mat):
    """Closed 2D ``outline`` extruded along ``axis`` ('x', 'y' or 'z') from d0 to d1.

    Outline coordinates are the other two axes in order (y, z), (x, z), (x, y).
    """
    def place(a, b, d):
        if axis == "x":
            return (d, a, b)
        if axis == "y":
            return (a, d, b)
        return (a, b, d)
    rings = [[bm.verts.new(place(a, b, d)) for a, b in outline] for d in (d0, d1)]
    faces = loft(bm, rings)
    chamfer(bm, faces, off, mat)


def box(bm, x0, x1, y0, y1, z0, z1, off, mat):
    prism(bm, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], "z", z0, z1, off, mat)


def revolve(bm, profile, n, origin, axis, closed=False, phase=0.0):
    """Revolve an (r, h) profile about ``axis`` through ``origin``.

    r == 0 entries at either end are poles. ``closed`` joins the last ring
    back to the first (a tube or torus section).
    """
    a = Vector(axis).normalized()
    u = (Vector((0.0, 0.0, 1.0)) if abs(a.z) < 0.9 else Vector((1.0, 0.0, 0.0))).cross(a).normalized()
    v = a.cross(u)
    o = Vector(origin)
    rings, poles = [], []
    for r, h in profile:
        if r <= 1e-9:
            poles.append((len(rings), bm.verts.new(o + a * h)))
        else:
            rings.append([bm.verts.new(o + a * h + (u * math.cos(phase + 2.0 * math.pi * k / n)
                                                    + v * math.sin(phase + 2.0 * math.pi * k / n)) * r)
                          for k in range(n)])
    faces = []
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for ra, rb in pairs:
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((ra[i], ra[j], rb[j], rb[i])))
    for at, pole in poles:
        ring = rings[0] if at == 0 else rings[-1]
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((pole, ring[i], ring[j])))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces


def torus(bm, centre, major, minor, n_major, n_minor, rot):
    """A ring in its own XZ plane, turned by ``rot`` and moved to ``centre``."""
    rings = []
    for i in range(n_major):
        t = 2.0 * math.pi * i / n_major
        c = Vector((math.cos(t) * major, 0.0, math.sin(t) * major))
        radial = Vector((math.cos(t), 0.0, math.sin(t)))
        ring = []
        for k in range(n_minor):
            s = 2.0 * math.pi * k / n_minor
            p = c + radial * math.cos(s) * minor + Vector((0.0, 1.0, 0.0)) * math.sin(s) * minor
            ring.append(bm.verts.new(Vector(centre) + rot @ p))
        rings.append(ring)
    faces = []
    for ra, rb in zip(rings, rings[1:] + rings[:1]):
        for i in range(n_minor):
            j = (i + 1) % n_minor
            faces.append(bm.faces.new((ra[i], ra[j], rb[j], rb[i])))
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def board_top(x):
    """Bow top: a parabolic arch from BOARD_SIDE at the stiles to BOARD_MID."""
    xc, half = GATE_X0 + GATE_W * 0.5, GATE_W * 0.5
    t = (x - xc) / half
    return BOARD_SIDE + (BOARD_MID - BOARD_SIDE) * (1.0 - t * t)


def build_slab(b):
    """Paving: a pad flag under each post, four flags across the opening.

    Every flag is its own shell with a 12 mm joint to the next; the two
    post pads stand at SLAB_TOP, the opening's flags a few millimetres
    proud or shy of it, so no two flag tops are one plane.
    """
    j = FLAG_JOINT * 0.5
    xa, xb = PAD_HALF, LATCH_POST_X - PAD_HALF
    flags = [(SLAB_X0, xa - j, -SLAB_Y, SLAB_Y, SLAB_TOP),
             (xb + j, SLAB_X1, -SLAB_Y, SLAB_Y, SLAB_TOP)]
    xm = 0.5 * (xa + xb) + 0.03
    for (x0, x1), (y0, y1), top in zip(((xa + j, xm - j), (xm + j, xb - j)) * 2,
                                       ((-SLAB_Y, -j),) * 2 + ((j, SLAB_Y),) * 2,
                                       FLAG_TOPS):
        flags.append((x0, x1, y0, y1, top))
    for x0, x1, y0, y1, top in flags:
        box(b.bm, x0, x1, y0, y1, 0.0, top, 0.009, GROUND_IDX)
        b.tag(P_SLAB, GROUND_IDX)


def build_post(b, xc, part):
    h = POST_W * 0.5
    z0 = SLAB_TOP - POST_BED
    sq = [(-h, -h), (h, -h), (h, h), (-h, h)]
    bm = b.bm
    r0 = [bm.verts.new((xc + x, y, z0)) for x, y in sq]
    r1 = [bm.verts.new((xc + x, y, POST_TOP)) for x, y in sq]
    apex = bm.verts.new((xc, 0.0, POST_APEX))
    faces = loft(bm, [r0, r1], cap=False)
    faces.append(bm.faces.new(list(reversed(r0))))
    for i in range(4):
        faces.append(bm.faces.new((r1[i], r1[(i + 1) % 4], apex)))
    chamfer(bm, faces, 0.008, TIMBER_IDX)
    b.tag(part, TIMBER_IDX, grain=0.0)


def build_boards(b):
    for i in range(BOARDS):
        x0 = GATE_X0 + i * (BOARD_W + BOARD_GAP)
        x1 = x0 + BOARD_W
        xm = 0.5 * (x0 + x1)
        outline = [(x0, BOARD_Z0), (x1, BOARD_Z0), (x1, board_top(x1)),
                   (xm, board_top(xm)), (x0, board_top(x0))]
        prism(b.bm, outline, "y", -BOARD_T * 0.5, BOARD_T * 0.5, 0.0025, TIMBER_IDX)
        b.tag(P_BOARD, TIMBER_IDX, grain=0.0)


def build_ledges_braces(b):
    for zc in LEDGE_ZC:
        box(b.bm, LEDGE_X0, LEDGE_X1, LEDGE_Y0, LEDGE_Y1, zc - LEDGE_H / 2, zc + LEDGE_H / 2,
            0.003, TIMBER_IDX)
        b.tag(P_LEDGE, TIMBER_IDX, grain=1.0)
    # Braces rise from the hinge side to the latch side, so they carry the
    # free edge's weight back down into the bottom hinge.
    for lo, hi in ((0, 1), (1, 2)):
        z0 = LEDGE_ZC[lo] + LEDGE_H / 2 - BRACE_BITE
        z1 = LEDGE_ZC[hi] - LEDGE_H / 2 + BRACE_BITE
        xa, xb = LEDGE_X0 + 0.010, LEDGE_X1 - 0.010
        theta = math.atan2(z1 - z0, xb - xa)
        dx = BRACE_W / math.sin(theta)
        outline = [(xa, z0), (xa + dx, z0), (xb, z1), (xb - dx, z1)]
        prism(b.bm, outline, "y", BRACE_Y0, BRACE_Y1, 0.003, TIMBER_IDX)
        b.tag(P_BRACE, TIMBER_IDX, grain=1.0)


def build_hinge(b, zc, knuckle_dx=0.0, lift=0.0, tilt=0.0):
    """Strap, knuckle, carriage-bolt heads (gate side, lifted with ``lift``),
    then the hook: pin and shank (post side, never lifted)."""
    bm = b.bm
    zcg = zc + lift
    xa, xe = AXIS_X, AXIS_X + STRAP_L
    hh, th = STRAP_H * 0.5, STRAP_TIP_H * 0.5
    outline = [(xa, zcg - hh), (xe - STRAP_TAPER, zcg - hh), (xe - 0.008, zcg - th),
               (xe, zcg), (xe - 0.008, zcg + th), (xe - STRAP_TAPER, zcg + hh), (xa, zcg + hh)]
    prism(bm, outline, "y", STRAP_Y0, STRAP_Y1, 0.0008, IRON_IDX)
    b.tag(P_STRAP, IRON_IDX)
    zk0 = zcg - KNUCKLE_HH
    prof = [(KNUCKLE_RI, 0.0), (KNUCKLE_RO, 0.0), (KNUCKLE_RO, 2 * KNUCKLE_HH),
            (KNUCKLE_RI, 2 * KNUCKLE_HH)]
    revolve(bm, prof, b.seg(12), (AXIS_X + knuckle_dx, AXIS_Y, zk0), (0, 0, 1), closed=True)
    b.tag(P_KNUCKLE, IRON_IDX, smooth=True)
    for k, dx in enumerate((0.075, 0.215, 0.335)):
        r, h = 0.0085, 0.0045
        dome = [(0.0, -0.0006), (r, -0.0006), (r, 0.0007), (r * 0.85, h * 0.6),
                (r * 0.5, h * 0.92), (0.0, h)]
        revolve(bm, dome, b.seg(8), (xa + dx, STRAP_Y0, zcg + (0.004 if k == 1 else 0.0)),
                (0, -1, 0))
        b.tag(P_BOLTHEAD, IRON_IDX, smooth=True)

    # The hook, unlifted. Its top is where the knuckle should rest.
    shank_top = zc - KNUCKLE_HH + SEAT_BITE
    box(bm, SHANK_X0, AXIS_X + 0.006, AXIS_Y - SHANK_S / 2, AXIS_Y + SHANK_S / 2,
        shank_top - SHANK_S, shank_top, 0.0015, IRON_IDX)
    b.tag(P_SHANK, IRON_IDX)
    z0 = shank_top - SHANK_S - 0.002
    z1 = zc + KNUCKLE_HH + PIN_ABOVE
    pin = [(0.0, 0.0), (PIN_R, 0.0), (PIN_R, z1 - z0), (PIN_R * 0.6, z1 - z0 + 0.0025),
           (0.0, z1 - z0 + 0.0035)]
    faces = revolve(bm, pin, b.seg(12), (AXIS_X, AXIS_Y, z0), (0, 0, 1))
    if tilt:
        for v in {v for f in faces for v in f.verts}:
            v.co.x += tilt * (v.co.z - zc)
    b.tag(P_PIN, IRON_IDX, smooth=True)


def build_nails(b, lift=0.0):
    """Rose-headed nails through every board into each ledge, except where a
    strap's bolts already hold the board."""
    for i in range(BOARDS):
        x0 = GATE_X0 + i * (BOARD_W + BOARD_GAP)
        for zc in LEDGE_ZC:
            for dx in (0.035, BOARD_W - 0.035):
                x = x0 + dx
                if zc in HINGE_ZC and x < AXIS_X + STRAP_L + 0.02:
                    continue
                head = [(0.0, -0.0007), (0.0048, -0.0007), (0.0048, 0.0008),
                        (0.0030, 0.0022), (0.0, 0.0028)]
                revolve(b.bm, head, b.seg(6), (x, -BOARD_T * 0.5, zc + lift), (0, -1, 0),
                        phase=math.radians(15.0 * (i % 3)))
                b.tag(P_NAIL, IRON_IDX)


def build_latch(b, lift=0.0, post_dx=0.0):
    bm = b.bm
    z = BOLT_ZC + lift
    # Barrel bolt: backplate on the middle ledge's back, two guides, the rod
    # (drawn back, inside the gate's edge) and its knob.
    box(bm, BOLT_X0 - 0.005, BOLT_X1 - 0.020, LEDGE_Y1 - 0.0005, LEDGE_Y1 + 0.003,
        z - 0.020, z + 0.020, 0.0008, IRON_IDX)
    b.tag(P_LATCH, IRON_IDX)
    for gx in (BOLT_X0 + 0.010, BOLT_X1 - 0.045):
        box(bm, gx, gx + 0.018, LEDGE_Y1 + 0.0025, BOLT_Y + BOLT_R + 0.003,
            z - BOLT_R - 0.003, z + BOLT_R + 0.003, 0.0008, IRON_IDX)
        b.tag(P_LATCH, IRON_IDX)
    rod = [(0.0, 0.0), (BOLT_R, 0.0), (BOLT_R, BOLT_X1 - BOLT_X0 - 0.002),
           (BOLT_R * 0.6, BOLT_X1 - BOLT_X0), (0.0, BOLT_X1 - BOLT_X0)]
    revolve(bm, rod, b.seg(10), (BOLT_X0, BOLT_Y, z), (1, 0, 0))
    b.tag(P_LATCH, IRON_IDX, smooth=True)
    knob = [(0.0, 0.0), (0.004, 0.0), (0.004, 0.020), (0.0065, 0.024), (0.0, 0.029)]
    revolve(bm, knob, b.seg(8), (BOLT_X0 + 0.055, BOLT_Y, z), (0, 0, 1))
    b.tag(P_LATCH, IRON_IDX, smooth=True)
    # Ring pull on the front: a round rose, a staple, a hanging ring.
    rz = RING_Z + lift
    rose = [(0.0, -0.0005), (0.024, -0.0005), (0.024, 0.0015), (0.019, 0.0035), (0.0, 0.0040)]
    revolve(bm, rose, b.seg(12), (RING_X, -BOARD_T * 0.5, rz), (0, -1, 0))
    b.tag(P_RING, IRON_IDX, smooth=True)
    box(bm, RING_X - 0.0045, RING_X + 0.0045, -BOARD_T * 0.5 - 0.0110, -BOARD_T * 0.5 - 0.0030,
        rz - 0.0045, rz + 0.0045, 0.0008, IRON_IDX)
    b.tag(P_RING, IRON_IDX)
    # The ring hangs from the staple and leans out at the bottom, the way a
    # ring pull rests against a board that is not quite plumb under it.
    rot = Matrix.Rotation(math.radians(-14.0), 3, "X")
    pivot = Vector((RING_X, -BOARD_T * 0.5 - 0.0085, rz + 0.001))
    torus(bm, pivot + rot @ Vector((0.0, 0.0, -RING_R)), RING_R, RING_TUBE,
          b.seg(16), b.seg(6), rot)
    b.tag(P_RING, IRON_IDX, smooth=True)
    # Keeper staple on the latch post's inner face, bitten into the post.
    face = LATCH_POST_X - POST_W * 0.5 - post_dx
    box(bm, face + KEEPER_X0, face + KEEPER_BITE, KEEPER_Y0, KEEPER_Y1,
        BOLT_ZC - KEEPER_HH, BOLT_ZC + KEEPER_HH, 0.0015, IRON_IDX)
    b.tag(P_KEEPER, IRON_IDX)


def build_gate_mesh(name, hi=False, stray_vert=False, offset_knuckle=False, lift_gate=False,
                    tilt_pintle=False, tight_post=False):
    b = Builder(hi)
    lift = LIFT_GATE if lift_gate else 0.0
    post_dx = TIGHT_POST if tight_post else 0.0
    try:
        build_slab(b)
        build_post(b, HINGE_POST_X, P_POST_H)
        build_post(b, LATCH_POST_X - post_dx, P_POST_L)
        # The gate is built at rest, then everything that hangs is lifted
        # together under --lift-gate; the hooks and posts stay put.
        start = len(b.bm.verts)
        build_boards(b)
        build_ledges_braces(b)
        if lift:
            for v in list(b.bm.verts)[start:]:
                v.co.z += lift
        for k, zc in enumerate(HINGE_ZC):
            build_hinge(b, zc, knuckle_dx=OFFSET_KNUCKLE if (offset_knuckle and k == 1) else 0.0,
                        lift=lift, tilt=TILT_PINTLE if (tilt_pintle and k == 1) else 0.0)
        build_nails(b, lift)
        build_latch(b, lift, post_dx)

        bm = b.bm
        if stray_vert:
            bm.verts.new((0.0, 0.0, 0.6))
        big = [f for f in bm.faces if len(f.verts) > 4]
        bmesh.ops.triangulate(bm, faces=big, quad_method="BEAUTY", ngon_method="EAR_CLIP")
        smooth_verts = {v for f in b.smooth if f.is_valid for v in f.verts}
        for f in bm.faces:
            f.smooth = f[b.part] in (P_KNUCKLE, P_PIN, P_RING, P_BOLTHEAD, P_LATCH) and all(
                v in smooth_verts for v in f.verts)
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(35.0):
                e.smooth = False
        pack_uvs(bm)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        b.bm.free()
    paint_pieces(me)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def pack_uvs(bm, margin=0.08):
    """One grid cell per face, box-projected on the face's dominant axis."""
    uv = bm.loops.layers.uv.new("UVMap")
    faces = list(bm.faces)
    cols = max(1, math.ceil(math.sqrt(len(faces))))
    rows = max(1, math.ceil(len(faces) / cols))
    cw, ch = 1.0 / cols, 1.0 / rows
    pu, pv = margin * cw * 0.5, margin * ch * 0.5
    for i, face in enumerate(faces):
        ax, ay, az = abs(face.normal.x), abs(face.normal.y), abs(face.normal.z)
        coords = []
        for loop in face.loops:
            co = loop.vert.co
            if az >= ax and az >= ay:
                coords.append((co.x, co.y))
            elif ax >= ay:
                coords.append((co.y, co.z))
            else:
                coords.append((co.x, co.z))
        minx, maxx = min(c[0] for c in coords), max(c[0] for c in coords)
        miny, maxy = min(c[1] for c in coords), max(c[1] for c in coords)
        dx, dy = max(maxx - minx, 1e-8), max(maxy - miny, 1e-8)
        ou, ov = (i % cols) * cw + pu, (i // cols) * ch + pv
        for loop, (x, y) in zip(face.loops, coords):
            loop[uv].uv = (ou + (x - minx) / dx * (cw - 2 * pu),
                           ov + (y - miny) / dy * (ch - 2 * pv))


def paint_pieces(me):
    """``WoodTone`` per shell, so no two boards read as one plank."""
    tone = [0.5] * len(me.polygons)
    vf = [[] for _ in range(len(me.vertices))]
    for p in me.polygons:
        for i in p.vertices:
            vf[i].append(p.index)
    pv = [0] * len(me.polygons)
    me.attributes["Part"].data.foreach_get("value", pv)
    for k, g in enumerate(shells(me)):
        t = 0.5 + 0.55 * (((k * 0.6180339887 + 0.3) % 1.0) - 0.5)
        fs = {fi for i in g for fi in vf[i]}
        part = pv[next(iter(fs))] if fs else 0
        if part == P_POST_H:
            t = 0.12
        elif part == P_POST_L:
            t = 0.22
        for fi in fs:
            tone[fi] = t
    a = me.attributes.new("WoodTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)


# --- surface ----------------------------------------------------------------


def _sock(sockets, identifier):
    return next(sk for sk in sockets if sk.identifier == identifier)


def _mix(nt, blend, a, b, fac):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.blend_type = blend
    fsock = _sock(node.inputs, "Factor_Float")
    if isinstance(fac, (int, float)):
        fsock.default_value = fac
    else:
        nt.links.new(fac, fsock)
    for ident, src in (("A_Color", a), ("B_Color", b)):
        if isinstance(src, tuple):
            _sock(node.inputs, ident).default_value = (*src, 1.0)
        else:
            nt.links.new(src, _sock(node.inputs, ident))
    return _sock(node.outputs, "Result_Color")


def _math(nt, op, a, b=None):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    for i, src in enumerate((a, b)):
        if src is None:
            continue
        if isinstance(src, (int, float)):
            node.inputs[i].default_value = src
        else:
            nt.links.new(src, node.inputs[i])
    return node.outputs["Value"]


def timber_material(name):
    """Weathered oak gone silver-brown: grain along each member, a tone per
    board, darker end grain and grime toward the ground."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "WoodTone"
    grain_dir = nt.nodes.new("ShaderNodeAttribute")
    grain_dir.attribute_name = "GrainDir"

    # Stretch the object coordinates along the member: vertical members
    # squash Z, horizontal and diagonal ones squash X, so the noise reads as
    # long fibres either way.
    def fibres(scale_vec):
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = scale_vec
        nt.links.new(coord.outputs["Object"], mp.inputs["Vector"])
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.wave_type = "BANDS"
        wave.bands_direction = "X"
        wave.inputs["Scale"].default_value = 2.2
        wave.inputs["Distortion"].default_value = 11.0
        wave.inputs["Detail"].default_value = 6.0
        wave.inputs["Detail Scale"].default_value = 1.5
        nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
        return wave.outputs["Fac"]
    vert = fibres((22.0, 22.0, 1.2))
    mp_h = nt.nodes.new("ShaderNodeMapping")
    mp_h.inputs["Scale"].default_value = (1.2, 22.0, 22.0)
    mp_h.inputs["Rotation"].default_value = (0.0, math.radians(90.0), 0.0)
    nt.links.new(coord.outputs["Object"], mp_h.inputs["Vector"])
    wave_h = nt.nodes.new("ShaderNodeTexWave")
    wave_h.wave_type = "BANDS"
    wave_h.bands_direction = "X"
    wave_h.inputs["Scale"].default_value = 2.2
    wave_h.inputs["Distortion"].default_value = 11.0
    wave_h.inputs["Detail"].default_value = 6.0
    wave_h.inputs["Detail Scale"].default_value = 1.5
    nt.links.new(mp_h.outputs["Vector"], wave_h.inputs["Vector"])
    gmix = nt.nodes.new("ShaderNodeMix")
    gmix.data_type = "FLOAT"
    nt.links.new(grain_dir.outputs["Fac"], _sock(gmix.inputs, "Factor_Float"))
    nt.links.new(vert, _sock(gmix.inputs, "A_Float"))
    nt.links.new(wave_h.outputs["Fac"], _sock(gmix.inputs, "B_Float"))
    grain = _sock(gmix.outputs, "Result_Float")

    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.20
    ramp.color_ramp.elements[0].color = (0.060, 0.044, 0.030, 1.0)
    mid = ramp.color_ramp.elements.new(0.55)
    mid.color = (0.150, 0.115, 0.080, 1.0)
    ramp.color_ramp.elements[2].position = 0.92
    ramp.color_ramp.elements[2].color = (0.235, 0.200, 0.155, 1.0)
    nt.links.new(grain, ramp.inputs["Fac"])

    # Per-board tone: a warm-to-grey shift and a brightness spread.
    gain = _math(nt, "MULTIPLY_ADD", tone.outputs["Fac"], 0.80)
    gain.node.inputs[2].default_value = 0.62
    gaingrey = nt.nodes.new("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(gain, gaingrey.inputs[ch])
    base = _mix(nt, "MULTIPLY", ramp.outputs["Color"], gaingrey.outputs["Color"], 1.0)
    silver = _mix(nt, "MIX", base, (0.205, 0.200, 0.190), 0.0)
    fac = _math(nt, "MULTIPLY", tone.outputs["Fac"], 0.40)
    nt.links.new(fac, _sock(silver.node.inputs, "Factor_Float"))

    # Grime: wet wood near the ground, broken by noise.
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
    band = nt.nodes.new("ShaderNodeMapRange")
    band.interpolation_type = "SMOOTHSTEP"
    band.inputs["From Min"].default_value = 0.05
    band.inputs["From Max"].default_value = 0.32
    band.inputs["To Min"].default_value = 0.65
    band.inputs["To Max"].default_value = 0.0
    nt.links.new(sep.outputs["Z"], band.inputs["Value"])
    blot = nt.nodes.new("ShaderNodeTexNoise")
    blot.inputs["Scale"].default_value = 9.0
    blot.inputs["Detail"].default_value = 5.0
    nt.links.new(coord.outputs["Object"], blot.inputs["Vector"])
    grime = _math(nt, "MULTIPLY", band.outputs["Result"], blot.outputs["Fac"])
    base = _mix(nt, "MIX", silver, (0.045, 0.040, 0.032), grime)
    nt.links.new(base, bsdf.inputs["Base Color"])
    rough = _math(nt, "MULTIPLY_ADD", grain, -0.12)
    rough.node.inputs[2].default_value = 0.86
    nt.links.new(rough, bsdf.inputs["Roughness"])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.name = "TimberBump"
    bump.inputs["Strength"].default_value = 0.32
    bump.inputs["Distance"].default_value = 0.0015
    nt.links.new(grain, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def iron_material(name):
    """Black forged iron, rubbed bright on the edges and rusting in patches."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 60.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.028, 0.027, 0.026, 1.0)
    mid = ramp.color_ramp.elements.new(0.62)
    mid.color = (0.050, 0.044, 0.040, 1.0)
    ramp.color_ramp.elements[2].position = 0.78
    ramp.color_ramp.elements[2].color = (0.20, 0.085, 0.035, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    metal = nt.nodes.new("ShaderNodeMapRange")
    metal.inputs["From Min"].default_value = 0.62
    metal.inputs["From Max"].default_value = 0.76
    metal.inputs["To Min"].default_value = 0.75
    metal.inputs["To Max"].default_value = 0.10
    nt.links.new(noise.outputs["Fac"], metal.inputs["Value"])
    nt.links.new(metal.outputs["Result"], bsdf.inputs["Metallic"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["From Min"].default_value = 0.55
    rough.inputs["From Max"].default_value = 0.78
    rough.inputs["To Min"].default_value = 0.42
    rough.inputs["To Max"].default_value = 0.85
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    pit = nt.nodes.new("ShaderNodeTexNoise")
    pit.inputs["Scale"].default_value = 260.0
    nt.links.new(tc.outputs["Object"], pit.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.0006
    nt.links.new(pit.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def ground_material(name):
    """Sandstone flags, each its own tone, pitted, dirt in the low spots."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 7.0
    noise.inputs["Detail"].default_value = 9.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.070, 0.060, 0.048, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.150, 0.132, 0.105, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 95.0
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    peb = nt.nodes.new("ShaderNodeMapRange")
    peb.inputs["From Min"].default_value = 0.10
    peb.inputs["From Max"].default_value = 0.02
    nt.links.new(vor.outputs["Distance"], peb.inputs["Value"])
    base = _mix(nt, "MIX", ramp.outputs["Color"], (0.20, 0.188, 0.168), peb.outputs["Result"])
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "WoodTone"
    gain = _math(nt, "MULTIPLY_ADD", tone.outputs["Fac"], 0.9)
    gain.node.inputs[2].default_value = 0.65
    grey = nt.nodes.new("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(gain, grey.inputs[ch])
    base = _mix(nt, "MULTIPLY", base, grey.outputs["Color"], 1.0)
    nt.links.new(base, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    bump.inputs["Distance"].default_value = 0.004
    nt.links.new(peb.outputs["Result"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def gate_materials():
    return (timber_material("GateTimber"), iron_material("GateIron"), ground_material("GateGround"))


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


def classify(me):
    """Shells grouped by the ``Part`` face attribute their faces carry."""
    part_attr = me.attributes.get("Part")
    pv = [0] * len(me.polygons)
    if part_attr is not None:
        part_attr.data.foreach_get("value", pv)
    vpart = {}
    for p in me.polygons:
        for i in p.vertices:
            vpart.setdefault(i, pv[p.index])
    out = {}
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        rec = {"g": g, "pts": pts, "lo": lo, "hi": hi, "ext": hi - lo,
               "c": sum(pts, Vector()) / len(pts)}
        out.setdefault(vpart.get(g[0], 0) if len(g) >= 4 else 0, []).append(rec)
    return out


def plan(p):
    return Vector((p.x, p.y))


def ring_centroids(pts):
    """Centroids of the full-radius rings of a revolved pin: the two lowest
    distinct heights that carry more than two vertices (poles excluded)."""
    by_z = {}
    for p in pts:
        by_z.setdefault(round(p.z, 6), []).append(p)
    rings = sorted((z, ps) for z, ps in by_z.items() if len(ps) > 2)
    return [(z, sum((plan(p) for p in ps), Vector((0.0, 0.0))) / len(ps), ps) for z, ps in rings]


def gate_audit(me):
    parts = classify(me)
    out = {k: len(parts.get(k, [])) for k in range(0, 16)}
    knuckles = sorted(parts.get(P_KNUCKLE, []), key=lambda r: r["c"].z)
    pins = sorted(parts.get(P_PIN, []), key=lambda r: r["c"].z)
    shanks = sorted(parts.get(P_SHANK, []), key=lambda r: r["c"].z)
    hinges = []
    for kn, pin, sh in zip(knuckles, pins, shanks):
        k_axis = sum((plan(p) for p in kn["pts"]), Vector((0.0, 0.0))) / len(kn["pts"])
        r_in = min((plan(p) - k_axis).length for p in kn["pts"])
        zmid = 0.5 * (kn["lo"].z + kn["hi"].z)
        rings = ring_centroids(pin["pts"])
        (z0, c0, ps0), (z1, c1, _ps1) = rings[0], rings[-1]
        axis_at = c0 + (c1 - c0) * ((zmid - z0) / (z1 - z0))
        # The bottom ring shares its height with the pole; the max is the radius.
        r_pin = max((plan(p) - c0).length for p in ps0)
        coax = (k_axis - axis_at).length
        hinges.append({
            "coax": coax, "bore": r_in - r_pin - coax, "r_in": r_in, "r_pin": r_pin,
            "seat": kn["lo"].z - sh["hi"].z, "plumb": (c1 - c0).length, "foot": c0,
            "axis": k_axis, "zmid": zmid,
        })
    out["hinges"] = hinges
    out["pair"] = (hinges[0]["foot"] - hinges[1]["foot"]).length if len(hinges) == 2 else 99.0

    # Swing: every vertex that turns with the gate, about the measured hinge
    # axis (the mean of the two knuckle axes), against the latch post and
    # its keeper.
    axis = (sum((h["axis"] for h in hinges), Vector((0.0, 0.0))) / len(hinges)
            if hinges else Vector((0.0, 0.0)))
    swing = [p for k in GATE_PARTS for r in parts.get(k, []) for p in r["pts"]]
    obst = [p for k in OBSTACLE_PARTS for r in parts.get(k, []) for p in r["pts"]]
    r_max = max(((plan(p) - axis).length for p in swing), default=99.0)
    d_min = min(((plan(p) - axis).length for p in obst), default=-99.0)
    out["swing_r"], out["obst_d"], out["swing_clear"] = r_max, d_min, d_min - r_max

    boards = parts.get(P_BOARD, [])
    out["gate_w"] = (max(r["hi"].x for r in boards) - min(r["lo"].x for r in boards)) if boards else -99.0
    out["gate_h"] = (max(r["hi"].z for r in boards) - min(r["lo"].z for r in boards)) if boards else -99.0
    # Post height above the flag it stands in.
    slab = parts.get(P_SLAB, [])
    posts = parts.get(P_POST_H, []) + parts.get(P_POST_L, [])
    heights = []
    for r in posts:
        under = [f for f in slab if f["lo"].x <= r["c"].x <= f["hi"].x and f["lo"].y <= r["c"].y <= f["hi"].y]
        heights.append(r["hi"].z - under[0]["hi"].z if under else -99.0)
    out["post_h"] = min(heights, default=-99.0)
    straps = parts.get(P_STRAP, [])
    out["strap_l"] = min((r["ext"].x for r in straps), default=-99.0)
    out["pin_d"] = min((2.0 * h["r_pin"] for h in hinges), default=-99.0)
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
    """Compound collider: one hull per post, one over the gate's timber, the slab.

    The ironwork is left out: millimetres of strap and bolt on faces the
    gate's hull already covers, and pins inside the hinge post's reach.
    """
    parts = classify(obj.data)
    groups = [r["pts"] for k in (P_POST_H, P_POST_L) for r in parts.get(k, [])]
    groups.append([p for r in parts.get(P_SLAB, []) for p in r["pts"]])
    groups.append([p for k in (P_BOARD, P_LEDGE, P_BRACE) for r in parts.get(k, []) for p in r["pts"]])
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for pts in groups:
            if len(pts) < 4:
                continue
            tmp = bmesh.new()
            try:
                vs = [tmp.verts.new(p) for p in pts]
                bmesh.ops.convex_hull(tmp, input=vs)
                remap = {}
                for f in tmp.faces:
                    for v in f.verts:
                        if v not in remap:
                            remap[v] = bm.verts.new(v.co)
                    bm.faces.new([remap[v] for v in f.verts])
            finally:
                tmp.free()
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    col = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(col)
    return col


def setup_bake_image(obj, target_mat, size):
    img = bpy.data.images.new("GateNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = TIMBER_IDX
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


EXPECTED_PARTS = {P_SLAB: 6, P_POST_H: 1, P_POST_L: 1, P_BOARD: BOARDS, P_LEDGE: 3,
                  P_BRACE: 2, P_STRAP: 2, P_KNUCKLE: 2, P_PIN: 2, P_SHANK: 2,
                  P_BOLTHEAD: 6, P_LATCH: 5, P_KEEPER: 1, P_RING: 3}


def expected_nails():
    n = 0
    for i in range(BOARDS):
        x0 = GATE_X0 + i * (BOARD_W + BOARD_GAP)
        for zc in LEDGE_ZC:
            for dx in (0.035, BOARD_W - 0.035):
                if not (zc in HINGE_ZC and x0 + dx < AXIS_X + STRAP_L + 0.02):
                    n += 1
    return n


def check(skip_decimate, lift_z=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_gate_mesh("GateLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_gate_mesh("GateHigh", hi=True, **hi_flags)
    mats = gate_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("gate mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[TIMBER_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "GateLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "GateLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(low, "GateCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_garden_gate_{os.getpid()}.glb")
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
    ga = gate_audit(low.data)
    hs = ga["hinges"]

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
    print("measured parts " + " ".join(f"{k}={ga[k]}" for k in range(0, 16)))
    for i, h in enumerate(hs):
        print(f"measured hinge{i} coax={h['coax'] * 1000:.4f}mm bore={h['bore'] * 1000:.4f}mm "
              f"r_in={h['r_in'] * 1000:.4f} r_pin={h['r_pin'] * 1000:.4f} "
              f"seat={h['seat'] * 1000:.4f}mm plumb={h['plumb'] * 1000:.4f}mm")
    print(f"measured pin_pair={ga['pair'] * 1000:.4f}mm swing_r={ga['swing_r']:.5f} "
          f"obst_d={ga['obst_d']:.5f} swing_clear={ga['swing_clear'] * 1000:.3f}mm")
    print(f"measured gate_w={ga['gate_w']:.4f} gate_h={ga['gate_h']:.4f} post_h={ga['post_h']:.4f} "
          f"strap_l={ga['strap_l']:.4f} pin_d={ga['pin_d'] * 1000:.3f}mm")

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
    want = dict(EXPECTED_PARTS)
    want[P_NAIL] = expected_nails()
    bad = {k: (ga[k], n) for k, n in want.items() if ga[k] != n}
    if bad or ga[0]:
        return (fail(f"part counts (got, want) {bad} untagged shells {ga[0]}", 3),) + nothing
    for i, h in enumerate(hs):
        if h["coax"] > COAX_TOL or not (BORE_MIN <= h["bore"] <= BORE_MAX):
            return (fail(f"hinge {i}: knuckle axis {h['coax'] * 1000:.3f} mm off its pin "
                         f"(<= {COAX_TOL * 1000} mm), radial clearance {h['bore'] * 1000:.3f} mm "
                         f"outside [{BORE_MIN * 1000}, {BORE_MAX * 1000}] mm "
                         "(--offset-knuckle is the designed fail)", 17),) + nothing
    for i, h in enumerate(hs):
        if not (SEAT_MIN <= h["seat"] <= SEAT_MAX):
            return (fail(f"hinge {i}: knuckle bottom {h['seat'] * 1000:.3f} mm from the hook's top, "
                         f"band [{SEAT_MIN * 1000}, {SEAT_MAX * 1000}] mm "
                         "(--lift-gate is the designed fail)", 18),) + nothing
    for i, h in enumerate(hs):
        if h["plumb"] > PLUMB_TOL:
            return (fail(f"hinge {i}: pin top {h['plumb'] * 1000:.3f} mm off plumb over its foot "
                         f"(> {PLUMB_TOL * 1000} mm) (--tilt-pintle is the designed fail)", 19),) + nothing
    if ga["pair"] > PAIR_TOL:
        return (fail(f"the two pins are {ga['pair'] * 1000:.3f} mm apart in plan "
                     f"(> {PAIR_TOL * 1000} mm): no shared hinge axis", 19),) + nothing
    if (abs(ga["gate_w"] - GATE_W) > GATE_W_TOL or abs(ga["gate_h"] - GATE_H) > GATE_H_TOL
            or abs(ga["post_h"] - POST_H) > POST_H_TOL or abs(ga["strap_l"] - STRAP_L) > STRAP_L_TOL
            or abs(ga["pin_d"] - PIN_D) > PIN_D_TOL):
        return (fail(f"real-world size: gate {ga['gate_w']:.4f} x {ga['gate_h']:.4f} (want "
                     f"{GATE_W:.3f} x {GATE_H:.3f}), post {ga['post_h']:.4f} (want {POST_H:.3f}), "
                     f"strap {ga['strap_l']:.4f} (want {STRAP_L}), pin {ga['pin_d'] * 1000:.2f} mm "
                     f"(want {PIN_D * 1000:.0f})", 19),) + nothing
    if not (SWING_MIN <= ga["swing_clear"] <= SWING_MAX):
        return (fail(f"swing circle {ga['swing_r']:.4f} m against the latch post at "
                     f"{ga['obst_d']:.4f} m: clearance {ga['swing_clear'] * 1000:.2f} mm outside "
                     f"[{SWING_MIN * 1000}, {SWING_MAX * 1000}] mm "
                     "(--tight-post is the designed fail)", 20),) + nothing
    return 0, low, high, mats, tex, collider


def swing_open(me, deg):
    """Turn every shell that hangs on the hinges by ``deg`` about the hinge
    axis measured off the knuckles. Render only: every budget above was
    asserted on the closed gate. Positive opens away from the front, toward +Y."""
    parts = classify(me)
    knuckles = parts.get(P_KNUCKLE, [])
    pts = [p for r in knuckles for p in r["pts"]]
    axis = Vector((sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts), 0.0))
    rot = Matrix.Rotation(math.radians(deg), 3, "Z")
    for k in GATE_PARTS:
        for r in parts.get(k, []):
            for i in r["g"]:
                v = me.vertices[i]
                v.co = axis + rot @ (v.co - axis)
    me.update()


def wire_normal(mat, tex):
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    bump = nt.nodes.get("TimberBump")
    target = bump.inputs["Normal"] if bump else nt.nodes["Principled BSDF"].inputs["Normal"]
    nt.links.new(nrm.outputs["Normal"], target)


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats[TIMBER_IDX], tex)
    swing_open(low.data, RENDER_SWING_DEG)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only, so the camera sees the gate's
    # front and the hinge knuckles on their pins at the left.
    yaw = math.radians(-44.0)
    low.rotation_euler.z = yaw
    centre = Vector((0.5 * (SLAB_X0 + SLAB_X1), 0.0, 0.0))
    low.location = -(Matrix.Rotation(yaw, 3, "Z") @ centre)

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

    def light(name, kind, loc, energy, size, col, target=(0.0, 0.0, 0.5)):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        if kind == "AREA":
            ld.size = size
        else:
            ld.shadow_soft_size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(ob)

    # The swung gate's face looks front-right, so the key comes from there.
    light("Key", "AREA", (2.2, -3.6, 4.0), 380.0, 0.9, (1.0, 0.95, 0.88))
    light("Fill", "AREA", (-4.2, -3.0, 1.8), 50.0, 5.0, (0.74, 0.84, 1.0))
    light("Rim", "AREA", (-2.1, 3.4, 2.9), 280.0, 3.0, (0.62, 0.78, 1.0), (0.0, 0.0, 0.9))
    ld = bpy.data.lights.new("Wedge", "SPOT")
    ld.energy, ld.color = 260.0, (1.0, 0.66, 0.34)
    ld.spot_size, ld.spot_blend, ld.shadow_soft_size = math.radians(55.0), 1.0, 0.3
    wedge = bpy.data.objects.new("Wedge", ld)
    wedge.location = (0.8, 2.4, 2.4)
    wedge.rotation_euler = (Vector((0.2, 0.8, 0.3)) - wedge.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.collection.objects.link(wedge)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-2.38, -3.32, 1.59)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.55)
    scene.collection.objects.link(aim)
    con = cam.constraints.new("TRACK_TO")
    con.target = aim
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    scene.camera = cam

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 48
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
    # Standard, not Filmic/AgX: the gallery look is graded by eye under
    # Standard, and the lights are set so nothing clips to white.
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low], stage=[floor, wall])
    if fcode:
        return fcode
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
    p.add_argument("--skip-decimate", action="store_true",
                   help="falsification: no DECIMATE on the LODs (exit 9)")
    p.add_argument("--stray-vert", action="store_true",
                   help="falsification: one loose vertex (exit 15)")
    p.add_argument("--lift-z", action="store_true",
                   help="falsification: the whole piece 50 mm off the floor (exit 16)")
    p.add_argument("--offset-knuckle", action="store_true",
                   help="falsification: the top knuckle 1.5 mm off its pin (exit 17)")
    p.add_argument("--lift-gate", action="store_true",
                   help="falsification: the gate 3 mm up off its hooks (exit 18)")
    p.add_argument("--tilt-pintle", action="store_true",
                   help="falsification: the top pin leaned 3.4 deg (exit 19)")
    p.add_argument("--tight-post", action="store_true",
                   help="falsification: the latch post set 14 mm closer (exit 20)")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        offset_knuckle=args.offset_knuckle,
        lift_gate=args.lift_gate,
        tilt_pintle=args.tilt_pintle,
        tight_post=args.tight_post,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("garden gate OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
