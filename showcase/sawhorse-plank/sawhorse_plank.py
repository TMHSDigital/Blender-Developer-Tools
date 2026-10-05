"""Game-ready sawhorse pair carrying a plank — a showcase piece, not an example.

Asserts budget conformance of a procedural workshop prop: two pine
sawhorses (a beam on four splayed legs housed into its sides, an apron
across each end's leg pair, nailed) standing a fir plank across their
saddles, with a handsaw resting on the plank. Carried through UVs, four
materials (pine, fir, steel, beech), a high-to-low normal bake, an LOD
chain, a compound convex collider, and a Unity glTF export.

The budget that matters is the one a two-support span fails invisibly.
A plank laid across two horses has to bear on both saddles; let one horse
stand a few millimetres low and the plank still crosses it in every
picture, but it rests on one saddle and a corner, rocking. Each horse
has to stand on all four feet, each leg housed into the beam it carries,
and its legs splayed at one angle both ways. The piece measures the
plank's seat on each saddle, every foot's height off the floor, every
leg's housing bite into its beam, and every leg's side and end splay off
the leg's own end faces.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--loose-leg`` a leg's housing in
its beam, ``--short-leg`` every foot on the floor, ``--uneven-splay`` one
splay angle for every leg, ``--low-horse`` the plank's seat on both
saddles.

No randomness. DECIMATE COLLAPSE triangle counts are not byte-identical
across Blender versions — the LOD gate is a ratio band.

    blender --background --python sawhorse_plank.py --
    blender --background --python sawhorse_plank.py -- --low-horse
    blender --background --python sawhorse_plank.py -- --output sawhorse_plank.png
"""
import argparse
import math
import os
import sys
import tempfile
import traceback

import bmesh
import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon
from mathutils.kdtree import KDTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402
import gallery_asset_quality  # noqa: E402

# --- dimensions, metres. X along the plank, Y along each horse's beam, Z up.
# A traditional horse is about 30 in to the top of its beam with a 40 in beam
# and a 21.5 in stance; legs are splayed out to the sides and out to the
# ends. Here: a 0.72 m beam top, 0.95 m beam, legs splayed 15 deg to the
# side and 10 deg to the end (a 0.49 m stance), carrying an 8 ft 2x10 plank.

SPAN = 1.600                # beam centreline to beam centreline
H_TOP = 0.720               # beam top above the floor
BEAM_W, BEAM_H, BEAM_L = 0.090, 0.070, 0.950
LEG_T, LEG_W = 0.038, 0.089                 # leg section: across the beam, along it
LEG_W_FOOT = 0.068          # legs taper along the beam from LEG_W at the top to this at the foot
# Eased arrises: chamfer widths per member (low mesh, one flat segment) and
# the rounded segment count the high mesh bakes onto them.
ARRIS_BEAM, ARRIS_LEG, ARRIS_APRON, ARRIS_PLANK = 0.007, 0.0055, 0.0045, 0.0055
ARRIS_SEGS = 3
LEG_DROP = 0.012            # leg top this far under the beam top
HOUSING = 0.010             # leg's inner face let this far into the beam's side
LEG_TOP_X = BEAM_W * 0.5 - HOUSING + LEG_T * 0.5             # 0.054
LEG_TOP_Y = 0.330
SIDE_SPLAY, END_SPLAY = 15.0, 10.0          # degrees
APRON_Z0, APRON_Z1, APRON_T, APRON_INSET, APRON_BITE = 0.300, 0.520, 0.018, 0.006, 0.001
PLANK_L, PLANK_W, PLANK_T, PLANK_Y = 2.440, 0.235, 0.038, 0.040
SEAT_BITE = 0.0005          # plank's underside this far into each saddle

# Handsaw: a 24 in blade (heel and toe widths, tooth pitch and depth),
# standing on its toe against the near horse's end; SAW_REST_U is where along
# the saw (behind the heel, in the handle) it rests on the beam's top arris.
SAW_L, SAW_HEEL, SAW_TOE, SAW_PITCH, SAW_TOOTH = 0.600, 0.130, 0.060, 0.0100, 0.0060
SAW_T, HANDLE_T = 0.0009, 0.022
SAW_REST_U, SAW_V_MID = -0.140, 0.080

# Falsifier magnitudes.
LOOSE_LEG = 0.014
SHORT_LEG = 0.008
UNEVEN_SPLAY = 19.0
LOW_HORSE = 0.006
LIFT_Z = 0.05

BBOX_TOL = 0.020
OUTER_SIZE = (2.440, 1.135, 0.7575)

BASE_TRIS_MIN = 3000
BASE_TRIS_MAX = 3500
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 5
FACE_FLOORS = {0: 330, 1: 24, 2: 1070, 3: 300, 4: 108}
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

BITE_MIN, BITE_MAX = 0.006, 0.014           # leg inner face into the beam's side
FOOT_TOL = 1e-4                              # every foot on the floor
SPLAY_TOL = 0.15                             # degrees, each leg against the declared angle
SEAT_MIN, SEAT_MAX = -0.0010, -0.0002        # plank underside minus saddle top
SIZE_TOL = 0.003

PINE_IDX = 0
FIR_IDX = 1
STEEL_IDX = 2
BEECH_IDX = 3
BRASS_IDX = 4

# Part ids, a face attribute written at build time; shells take their
# part from their faces. 0 is "not yet tagged".
P_BEAM, P_LEG, P_APRON, P_PLANK, P_NAIL, P_BLADE, P_HANDLE, P_SCREW = 1, 2, 3, 4, 5, 6, 7, 8
EXPECTED_PARTS = {P_BEAM: 2, P_LEG: 8, P_APRON: 4, P_PLANK: 1, P_NAIL: 32,
                  P_BLADE: 1, P_HANDLE: 1, P_SCREW: 6}

# Grain direction face attribute: fibres along Z, X or Y.
G_Z, G_X, G_Y = 0.0, 1.0, 2.0


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

    @property
    def arris(self):
        """Chamfer segments: a flat one on the low mesh, rounded on the high."""
        return ARRIS_SEGS if self.hi else 1

    def tag(self, part, mat, grain=G_Z, smooth=False):
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


def chamfer(bm, faces, offset, mat, segments=1):
    """Arris on the shell's near-right-angle edges only.

    The low mesh takes one flat segment; the high mesh takes ARRIS_SEGS
    rounded ones, and the bake carries that roundness onto the low's flat
    chamfer, so the game mesh keeps its budget and still reads eased.

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
        bmesh.ops.bevel(bm, geom=pick, offset=offset, segments=segments, profile=0.5,
                        affect="EDGES", clamp_overlap=True, material=mat)


def solid(bm, lower, upper, off, mat, segments=1):
    """A hexahedron from two four-vertex rings (lower and upper), chamfered."""
    rings = [[bm.verts.new(p) for p in lower], [bm.verts.new(p) for p in upper]]
    faces = loft(bm, rings)
    chamfer(bm, faces, off, mat, segments)


def box(bm, x0, x1, y0, y1, z0, z1, off, mat, segments=1):
    sq = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    solid(bm, [(x, y, z0) for x, y in sq], [(x, y, z1) for x, y in sq], off, mat, segments)


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


def nail_head(b, origin, axis, phase=0.0, sink=0.0007):
    """A rose-headed nail sunk ``sink`` into the face it is driven through.

    Two nails in one face differ in sink and in phase: at one depth their
    underside discs share a plane, at one phase their flats do.
    """
    head = [(0.0, -sink), (0.0050, -sink), (0.0050, 0.0008), (0.0031, 0.0023), (0.0, 0.0029)]
    revolve(b.bm, head, b.seg(6), origin, axis, phase=phase)
    b.tag(P_NAIL, STEEL_IDX)


def horse_top(k, low_horse=False):
    return H_TOP - (LOW_HORSE if (low_horse and k == 1) else 0.0)


def leg_centre(hx, sx, sy, ztop, z, side_deg=SIDE_SPLAY, dx=0.0):
    """Leg centreline at height ``z``: from its top under the beam, out to
    the side by ``side_deg`` and out to the end by END_SPLAY as it drops."""
    drop = ztop - z
    return Vector((hx + sx * (LEG_TOP_X + dx + drop * math.tan(math.radians(side_deg))),
                   sy * (LEG_TOP_Y + drop * math.tan(math.radians(END_SPLAY))), z))


def build_horse(b, k, loose_leg=False, short_leg=False, uneven_splay=False, low_horse=False):
    """Beam, four legs, two end aprons and their nails for horse ``k`` (0 at -X)."""
    bm = b.bm
    hx = (k - 0.5) * SPAN
    top = horse_top(k, low_horse)
    box(bm, hx - BEAM_W / 2, hx + BEAM_W / 2, -BEAM_L / 2, BEAM_L / 2, top - BEAM_H, top,
        ARRIS_BEAM, PINE_IDX, b.arris)
    b.tag(P_BEAM, PINE_IDX, grain=G_Y)
    ztop = top - LEG_DROP

    def leg_w(z):
        """Leg width along the beam: LEG_W at its top, LEG_W_FOOT at the floor."""
        f = max(0.0, min(1.0, z / ztop))
        return LEG_W_FOOT + (LEG_W - LEG_W_FOOT) * f
    # The leg that the per-leg falsifiers act on: the +X, +Y leg of horse 1.
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            target = k == 1 and sx > 0 and sy > 0
            side = UNEVEN_SPLAY if (uneven_splay and target) else SIDE_SPLAY
            dx = LOOSE_LEG if (loose_leg and target) else 0.0
            zbot = SHORT_LEG if (short_leg and target) else 0.0
            rings = []
            for z in (zbot, ztop):
                c = leg_centre(hx, sx, sy, ztop, z, side, dx)
                hx_, hy_ = LEG_T / 2, leg_w(z) / 2
                rings.append([(c.x - hx_, c.y - hy_, z), (c.x + hx_, c.y - hy_, z),
                              (c.x + hx_, c.y + hy_, z), (c.x - hx_, c.y + hy_, z)])
            solid(bm, rings[0], rings[1], ARRIS_LEG, PINE_IDX, b.arris)
            b.tag(P_LEG, PINE_IDX, grain=G_Z)
            # Two nails through the leg's outer face into the beam.
            n = Vector((sx, 0.0, math.tan(math.radians(side)))).normalized()
            for m, zn in enumerate((ztop - 0.018, ztop - 0.046)):
                c = leg_centre(hx, sx, sy, ztop, zn, side, dx)
                nail_head(b, c + Vector((sx * LEG_T / 2, 0.0, 0.0)), n,
                          phase=0.3 * (k + 1) + m * math.radians(30.0), sink=0.0007 + m * 0.0003)

    # An apron across each end's leg pair, on the legs' end faces.
    te, ts = math.tan(math.radians(END_SPLAY)), math.tan(math.radians(SIDE_SPLAY))
    for sy in (-1.0, 1.0):
        def yo(z):
            # The legs' end faces, which taper: the apron follows them.
            return sy * (LEG_TOP_Y + leg_w(z) / 2 + (ztop - z) * te)

        def xo(z):
            return LEG_TOP_X + LEG_T / 2 + (ztop - z) * ts - APRON_INSET

        lower, upper = [], []
        for z, ring in ((APRON_Z0, lower), (APRON_Z1, upper)):
            yi, ye = yo(z) - sy * APRON_BITE, yo(z) + sy * APRON_T
            ring.extend([(hx - xo(z), yi, z), (hx + xo(z), yi, z),
                         (hx + xo(z), ye, z), (hx - xo(z), ye, z)])
        solid(bm, lower, upper, ARRIS_APRON, PINE_IDX, b.arris)
        b.tag(P_APRON, PINE_IDX, grain=G_X)
        n = Vector((0.0, sy, te)).normalized()
        for sx in (-1.0, 1.0):
            for m, zn in enumerate((0.360, 0.460)):
                c = leg_centre(hx, sx, sy, ztop, zn)
                nail_head(b, Vector((c.x, yo(zn) + sy * APRON_T, zn)), n,
                          phase=0.2 * k + m * math.radians(30.0), sink=0.0007 + m * 0.0003)


def build_plank(b):
    z0 = H_TOP - SEAT_BITE
    box(b.bm, -PLANK_L / 2, PLANK_L / 2, PLANK_Y - PLANK_W / 2, PLANK_Y + PLANK_W / 2,
        z0, z0 + PLANK_T, ARRIS_PLANK, FIR_IDX, b.arris)
    b.tag(P_PLANK, FIR_IDX, grain=G_X)


def chaikin(pts, rounds):
    """Corner-cutting on a closed outline: each round replaces every corner
    by two points a quarter of the way along its edges."""
    for _ in range(rounds):
        out = []
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            out += [(0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by),
                    (0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by)]
        pts = out
    return pts


# A closed western handsaw handle in saw-local (u along the blade, v across
# it, the blade's toothed edge on v = 0, its heel at u = 0): a front cheek
# over the heel, a top horn and a lower horn at the back, and a hand-hole
# slanted the way the grip is held. Control points, rounded by Chaikin.
HANDLE_CTRL = [(0.022, 0.000), (0.024, 0.124), (0.008, 0.152), (-0.040, 0.168),
               (-0.098, 0.180), (-0.106, 0.161), (-0.084, 0.146), (-0.100, 0.108),
               (-0.124, 0.058), (-0.150, 0.016), (-0.160, -0.010), (-0.130, -0.017),
               (-0.070, -0.005)]
HOLE_C, HOLE_A, HOLE_B, HOLE_ROT = (-0.050, 0.075), 0.050, 0.018, 53.0
HANDLE_FRONT_U = 0.024
NUT_R, NUT_SLOT = 0.0058, 0.0012
NUTS = ((0.009, 0.028), (0.009, 0.104), (-0.036, 0.022))


def ccw(pts):
    area = sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]))
    return pts if area > 0 else list(reversed(pts))


def cap_prism(bm, outer, holes, w0, w1, place):
    """A prism of a 2D outline with holes, w0..w1 through it: caps from
    ``tessellate_polygon`` (which honours holes), quad walls round every loop."""
    loops = [outer] + holes
    flat = [p for lp in loops for p in lp]
    tris = tessellate_polygon([[Vector((u, v, 0.0)) for u, v in lp] for lp in loops])
    lo = [bm.verts.new(place(u, v, w0)) for u, v in flat]
    hi = [bm.verts.new(place(u, v, w1)) for u, v in flat]
    faces = []
    for a, b_, c in tris:
        faces.append(bm.faces.new((hi[a], hi[b_], hi[c])))
        faces.append(bm.faces.new((lo[c], lo[b_], lo[a])))
    start = 0
    for lp in loops:
        n = len(lp)
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((lo[start + i], lo[start + j], hi[start + j], hi[start + i])))
        start += n
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces


def split_nut(b, u, v, w, place, k):
    # ``w`` is the outer cheek (w = -HANDLE_T/2): the nut stands out along -w.
    """A brass split nut: two half-discs either side of a screwdriver slot,
    0.2 mm apart in height so their tops are never one plane; nut ``k`` is
    raised and sunk a further 0.3 mm per index for the same reason."""
    turn = math.radians(35.0 + 50.0 * k)
    nx, ny = -math.sin(turn), math.cos(turn)          # across the slot
    for side in (1.0, -1.0):
        t0 = turn if side > 0 else turn + math.pi
        sh = NUT_SLOT * 0.5 * side
        pts = ccw([(u + NUT_R * math.cos(t0 + math.pi * i / 7.0) + nx * sh,
                    v + NUT_R * math.sin(t0 + math.pi * i / 7.0) + ny * sh) for i in range(8)])
        # Each nut and each half its own height: nuts closer than the
        # coplanar search radius would otherwise share their top planes.
        top = (0.0016 if side > 0 else 0.0018) + 0.0003 * k
        sink = (0.0006 if side > 0 else 0.0008) + 0.0003 * k
        cap_prism(b.bm, pts, [], w + sink, w - top, place)
        b.tag(P_SCREW, BRASS_IDX)


def build_saw(b, place):
    """Western handsaw: a tapered, toothed steel blade let into a closed
    beech handle with a hand-hole, held by brass split nuts.

    ``place`` maps saw-local (u along the blade, v across it, w through it)
    into the world.
    """
    bm = b.bm
    # Blade: toothed edge along v = 0, back edge tapering heel to toe. The
    # caps are a quad strip (each tooth's root to the back edge above it)
    # plus a triangle per tooth: an ear-clipped comb would join collinear
    # tooth roots into zero-area triangles.
    n_teeth = int(round(SAW_L / SAW_PITCH))
    pitch = SAW_L / n_teeth
    roots = [(i * pitch, 0.0) for i in range(n_teeth + 1)]
    tips = [((i + 0.35) * pitch, -SAW_TOOTH) for i in range(n_teeth)]
    backs = [(u, SAW_HEEL + (SAW_TOE - SAW_HEEL) * u / SAW_L) for u, _v in roots]
    outline = []
    for i in range(n_teeth):
        outline += [roots[i], tips[i]]
    outline.append(roots[-1])
    outline += list(reversed(backs))
    layers = [[bm.verts.new(place(u, v, w)) for u, v in outline] for w in (-SAW_T / 2, SAW_T / 2)]
    nout = len(outline)
    faces = [bm.faces.new((layers[0][i], layers[0][(i + 1) % nout],
                           layers[1][(i + 1) % nout], layers[1][i])) for i in range(nout)]
    for L in layers:
        root = [L[2 * i] for i in range(n_teeth + 1)]
        tip = [L[2 * i + 1] for i in range(n_teeth)]
        back = [L[2 * n_teeth + 1 + (n_teeth - i)] for i in range(n_teeth + 1)]
        for i in range(n_teeth):
            faces.append(bm.faces.new((root[i], tip[i], root[i + 1])))
            faces.append(bm.faces.new((root[i], root[i + 1], back[i + 1], back[i])))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    b.tag(P_BLADE, STEEL_IDX)

    # Handle: the rounded outline with the hand-hole, chamfered all round.
    outer = ccw(chaikin(HANDLE_CTRL, 3 if b.hi else 2))
    nh = b.seg(16)
    rot = math.radians(HOLE_ROT)
    hole = []
    for i in range(nh):
        t = 2.0 * math.pi * i / nh
        x, y = HOLE_A * math.cos(t), HOLE_B * math.sin(t)
        hole.append((HOLE_C[0] + x * math.cos(rot) - y * math.sin(rot),
                     HOLE_C[1] + x * math.sin(rot) + y * math.cos(rot)))
    hole = list(reversed(ccw(hole)))
    h = HANDLE_T / 2
    faces = cap_prism(bm, outer, [hole], -h, h, place)
    chamfer(bm, faces, 0.0025, BEECH_IDX)
    b.tag(P_HANDLE, BEECH_IDX, grain=G_X, smooth=True)
    for k, (u, v) in enumerate(NUTS):
        split_nut(b, u, v, -h, place, k)


def saw_placer():
    """Saw-local to world. The saw stands on its toe and leans against the
    near horse's end, its flat facing out: the toe's edge on the floor, the
    handle's back cheek on the beam's top arris at SAW_REST_U along the saw.
    The lean is solved so both touch: with A = SAW_L - SAW_REST_U and
    B = the handle's half-thickness less the blade's, A cos(b) - B sin(b)
    is the beam-top height."""
    hx = 0.5 * SPAN
    a_len = SAW_L - SAW_REST_U
    b_off = HANDLE_T / 2 - SAW_T / 2
    r = math.hypot(a_len, b_off)
    lean = math.acos(H_TOP / r) - math.atan2(b_off, a_len)
    c, s_ = math.cos(lean), math.sin(lean)
    z0 = (SAW_T / 2) * s_
    y0 = -BEAM_L / 2 - a_len * s_ - (HANDLE_T / 2) * c

    def place(u, v, w):
        return Vector((hx + v - SAW_V_MID, y0 + (SAW_L - u) * s_ + w * c,
                       (SAW_L - u) * c - w * s_ + z0))
    return place


def build_mesh(name, hi=False, stray_vert=False, loose_leg=False, short_leg=False,
               uneven_splay=False, low_horse=False):
    b = Builder(hi)
    try:
        for k in (0, 1):
            build_horse(b, k, loose_leg, short_leg, uneven_splay, low_horse)
        build_plank(b)
        build_saw(b, saw_placer())
        bm = b.bm
        if stray_vert:
            bm.verts.new((-SPAN / 2, 0.0, H_TOP - BEAM_H / 2))
        big = [f for f in bm.faces if len(f.verts) > 4]
        bmesh.ops.triangulate(bm, faces=big, quad_method="BEAUTY", ngon_method="EAR_CLIP")
        smooth_verts = {v for f in b.smooth if f.is_valid for v in f.verts}
        for f in bm.faces:
            f.smooth = f[b.part] in (P_HANDLE,) and all(v in smooth_verts for v in f.verts)
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
    """``WoodTone`` per shell, so no two members read as one stick."""
    tone = [0.5] * len(me.polygons)
    vf = [[] for _ in range(len(me.vertices))]
    for p in me.polygons:
        for i in p.vertices:
            vf[i].append(p.index)
    for k, g in enumerate(shells(me)):
        t = 0.5 + 0.6 * (((k * 0.6180339887 + 0.37) % 1.0) - 0.5)
        for fi in {fi for i in g for fi in vf[i]}:
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


def _math(nt, op, a, b=None, c=None):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    for i, src in enumerate((a, b, c)):
        if src is None:
            continue
        if isinstance(src, (int, float)):
            node.inputs[i].default_value = src
        else:
            nt.links.new(src, node.inputs[i])
    return node.outputs["Value"]


def _fmix(nt, fac, a, b):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "FLOAT"
    nt.links.new(fac, _sock(node.inputs, "Factor_Float"))
    nt.links.new(a, _sock(node.inputs, "A_Float"))
    nt.links.new(b, _sock(node.inputs, "B_Float"))
    return _sock(node.outputs, "Result_Float")


def wood_material(name, ramp_cols, tone_gain, rough, knots=False, gloss=False):
    """Grain along each member's long axis (GrainDir picks Z, X or Y).

    Growth rings round the fibre axis, broken up so no two pieces and no two
    bands read alike: each piece samples the rings at its own offset (from
    WoodTone), the coordinates are pushed about by low-frequency noise, a
    finer ring set rides over the coarse one, and a fine fleck noise sits on
    top. The ramp is kept low in contrast: earlywood to latewood, not stripes.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "WoodTone"
    gdir = nt.nodes.new("ShaderNodeAttribute")
    gdir.attribute_name = "GrainDir"

    # Per-piece offset into the log, then a slow noise warp.
    off = nt.nodes.new("ShaderNodeCombineXYZ")
    for i, k in enumerate((4.1, 7.3, 2.9)):
        nt.links.new(_math(nt, "MULTIPLY", tone.outputs["Fac"], k), off.inputs[i])
    shifted = nt.nodes.new("ShaderNodeVectorMath")
    shifted.operation = "ADD"
    nt.links.new(coord.outputs["Object"], shifted.inputs[0])
    nt.links.new(off.outputs["Vector"], shifted.inputs[1])
    warp_n = nt.nodes.new("ShaderNodeTexNoise")
    warp_n.inputs["Scale"].default_value = 1.6
    warp_n.inputs["Detail"].default_value = 3.0
    nt.links.new(shifted.outputs["Vector"], warp_n.inputs["Vector"])
    warp_s = nt.nodes.new("ShaderNodeVectorMath")
    warp_s.operation = "SCALE"
    warp_s.inputs["Scale"].default_value = 0.045
    nt.links.new(warp_n.outputs["Color"], warp_s.inputs[0])
    warped = nt.nodes.new("ShaderNodeVectorMath")
    warped.operation = "ADD"
    nt.links.new(shifted.outputs["Vector"], warped.inputs[0])
    nt.links.new(warp_s.outputs["Vector"], warped.inputs[1])
    vec = warped.outputs["Vector"]

    def rings(axis, scale, ring_scale, distortion):
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = scale
        nt.links.new(vec, mp.inputs["Vector"])
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.wave_type = "RINGS"
        wave.rings_direction = axis
        wave.wave_profile = "SAW"
        wave.inputs["Scale"].default_value = ring_scale
        wave.inputs["Distortion"].default_value = distortion
        wave.inputs["Detail"].default_value = 5.0
        wave.inputs["Detail Scale"].default_value = 1.5
        wave.inputs["Detail Roughness"].default_value = 0.65
        nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
        return wave.outputs["Fac"]

    def fibres(axis, scale):
        coarse = rings(axis, scale, 4.5, 7.0)
        fine = rings(axis, scale, 13.0, 3.0)
        return _fmix_const(nt, 0.32, coarse, fine)

    def streaks(scale):
        """Figure: long, thin streaks along the fibre (noise stretched along it)."""
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = scale
        nt.links.new(vec, mp.inputs["Vector"])
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 9.0
        n.inputs["Detail"].default_value = 6.0
        n.inputs["Roughness"].default_value = 0.62
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n.outputs["Fac"]
    is_x = _math(nt, "COMPARE", gdir.outputs["Fac"], 1.0, 0.5)
    is_y = _math(nt, "COMPARE", gdir.outputs["Fac"], 2.0, 0.5)
    grain = _fmix(nt, is_y, _fmix(nt, is_x, fibres("Z", (6.0, 6.0, 0.35)),
                                  fibres("X", (0.35, 6.0, 6.0))),
                  fibres("Y", (6.0, 0.35, 6.0)))
    streak = _fmix(nt, is_y, _fmix(nt, is_x, streaks((8.0, 8.0, 0.25)),
                                   streaks((0.25, 8.0, 8.0))),
                   streaks((8.0, 0.25, 8.0)))

    # Earlywood is the broad pale ground; latewood is a thin dark line at the
    # top of each saw-profile ring, so faces read as lines and cathedrals,
    # not as soft stripes.
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*ramp_cols[0], 1.0)
    els[1].position, els[1].color = 0.66, (*ramp_cols[1], 1.0)
    late = els.new(0.90)
    late.color = (*ramp_cols[2], 1.0)
    tail = els.new(0.985)
    tail.color = (*ramp_cols[1], 1.0)
    nt.links.new(grain, ramp.inputs["Fac"])
    gain = _math(nt, "MULTIPLY_ADD", tone.outputs["Fac"], tone_gain[0], tone_gain[1])
    grey = nt.nodes.new("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(gain, grey.inputs[ch])
    base = _mix(nt, "MULTIPLY", ramp.outputs["Color"], grey.outputs["Color"], 1.0)
    # Fine fleck: pores and handling, a few percent either way.
    fleck = nt.nodes.new("ShaderNodeTexNoise")
    fleck.inputs["Scale"].default_value = 140.0
    fleck.inputs["Detail"].default_value = 2.0
    nt.links.new(vec, fleck.inputs["Vector"])
    fl = nt.nodes.new("ShaderNodeMapRange")
    fl.inputs["To Min"].default_value = 0.90
    fl.inputs["To Max"].default_value = 1.08
    nt.links.new(fleck.outputs["Fac"], fl.inputs["Value"])
    flc = nt.nodes.new("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(fl.outputs["Result"], flc.inputs[ch])
    base = _mix(nt, "MULTIPLY", base, flc.outputs["Color"], 1.0)
    # Figure: the streaks shift the shade +-10% along the fibre.
    fig = nt.nodes.new("ShaderNodeMapRange")
    fig.inputs["To Min"].default_value = 0.86
    fig.inputs["To Max"].default_value = 1.10
    nt.links.new(streak, fig.inputs["Value"])
    figc = nt.nodes.new("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(fig.outputs["Result"], figc.inputs[ch])
    base = _mix(nt, "MULTIPLY", base, figc.outputs["Color"], 1.0)
    if knots:
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 2.6
        nt.links.new(vec, vor.inputs["Vector"])
        knot = nt.nodes.new("ShaderNodeMapRange")
        knot.interpolation_type = "SMOOTHSTEP"
        knot.inputs["From Min"].default_value = 0.05
        knot.inputs["From Max"].default_value = 0.020
        nt.links.new(vor.outputs["Distance"], knot.inputs["Value"])
        base = _mix(nt, "MIX", base, (0.085, 0.048, 0.022), knot.outputs["Result"])
    # Grime: the work's handling, broken by noise.
    blot = nt.nodes.new("ShaderNodeTexNoise")
    blot.inputs["Scale"].default_value = 6.0
    blot.inputs["Detail"].default_value = 5.0
    nt.links.new(coord.outputs["Object"], blot.inputs["Vector"])
    dirt = nt.nodes.new("ShaderNodeMapRange")
    dirt.inputs["From Min"].default_value = 0.55
    dirt.inputs["From Max"].default_value = 0.75
    dirt.inputs["To Max"].default_value = 0.30
    nt.links.new(blot.outputs["Fac"], dirt.inputs["Value"])
    base = _mix(nt, "MULTIPLY", base, (0.60, 0.55, 0.48), dirt.outputs["Result"])
    nt.links.new(base, bsdf.inputs["Base Color"])
    # Latewood is denser and a touch glossier; handling polishes the figure.
    r = _math(nt, "MULTIPLY_ADD", grain, -0.10, rough)
    r = _math(nt, "MULTIPLY_ADD", streak, -0.12, r)
    nt.links.new(_math(nt, "ADD", r, 0.06), bsdf.inputs["Roughness"])
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    if gloss:
        try:
            bsdf.inputs["Coat Weight"].default_value = 0.45
            bsdf.inputs["Coat Roughness"].default_value = 0.22
        except KeyError:
            pass
    bump = nt.nodes.new("ShaderNodeBump")
    bump.name = "WoodBump"
    bump.inputs["Strength"].default_value = 0.18
    bump.inputs["Distance"].default_value = 0.0010
    nt.links.new(grain, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _fmix_const(nt, fac, a, b):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "FLOAT"
    _sock(node.inputs, "Factor_Float").default_value = fac
    nt.links.new(a, _sock(node.inputs, "A_Float"))
    nt.links.new(b, _sock(node.inputs, "B_Float"))
    return _sock(node.outputs, "Result_Float")


def steel_material(name):
    """Saw steel and nails: polished blade steel brushed along its length
    (noise stretched along the saw, driving roughness, so highlights streak
    the way they do on a real blade), a faint grey etch-tone variation, and
    rust only in rare small patches."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 45.0
    noise.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    rust = nt.nodes.new("ShaderNodeMapRange")
    rust.interpolation_type = "SMOOTHSTEP"
    rust.inputs["From Min"].default_value = 0.70
    rust.inputs["From Max"].default_value = 0.77
    nt.links.new(noise.outputs["Fac"], rust.inputs["Value"])
    # Brushing: fine noise squashed across the blade, long along it. The saw
    # stands near-vertical, so its length runs along object Z.
    bmap = nt.nodes.new("ShaderNodeMapping")
    bmap.inputs["Scale"].default_value = (260.0, 260.0, 4.0)
    nt.links.new(tc.outputs["Object"], bmap.inputs["Vector"])
    brush = nt.nodes.new("ShaderNodeTexNoise")
    brush.inputs["Scale"].default_value = 3.0
    brush.inputs["Detail"].default_value = 8.0
    nt.links.new(bmap.outputs["Vector"], brush.inputs["Vector"])
    tone = _math(nt, "MULTIPLY_ADD", brush.outputs["Fac"], 0.22, 0.88)
    toned = nt.nodes.new("ShaderNodeCombineColor")
    for ch, k in (("Red", 0.70), ("Green", 0.71), ("Blue", 0.73)):
        nt.links.new(_math(nt, "MULTIPLY", tone, k), toned.inputs[ch])
    base = _mix(nt, "MIX", toned.outputs["Color"], (0.22, 0.09, 0.035), rust.outputs["Result"])
    nt.links.new(base, bsdf.inputs["Base Color"])
    metal = _math(nt, "MULTIPLY_ADD", rust.outputs["Result"], -0.85, 1.0)
    nt.links.new(metal, bsdf.inputs["Metallic"])
    rough = _math(nt, "MULTIPLY_ADD", brush.outputs["Fac"], 0.18, 0.16)
    rough = _math(nt, "MULTIPLY_ADD", rust.outputs["Result"], 0.55, rough)
    nt.links.new(rough, bsdf.inputs["Roughness"])
    return mat


def brass_material(name):
    """Brass split nuts: warm metal, dulled and darkened in the slot."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 300.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.52, 0.33, 0.10, 1.0)
    ramp.color_ramp.elements[1].color = (0.86, 0.64, 0.26, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.22
    return mat


def piece_materials():
    # Ramp colours (linear): pale earlywood, its darker edge, the latewood line.
    # Horses: honey-aged pine. Plank: fresh, paler fir. Handle: varnished apple,
    # a fine diffuse-porous wood, so its latewood line is barely darker.
    pine = wood_material("HorsePine", ((0.440, 0.262, 0.115), (0.385, 0.222, 0.094),
                                       (0.165, 0.080, 0.030)), (0.55, 0.70), 0.72)
    fir = wood_material("PlankFir", ((0.560, 0.390, 0.205), (0.500, 0.338, 0.172),
                                     (0.250, 0.135, 0.055)), (0.35, 0.80), 0.66, knots=True)
    beech = wood_material("HandleBeech", ((0.300, 0.112, 0.046), (0.262, 0.094, 0.038),
                                          (0.205, 0.072, 0.029)), (0.25, 0.85), 0.34, gloss=True)
    return (pine, fir, steel_material("SawSteel"), beech, brass_material("NutBrass"))


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


def end_centroid(pts, z, eps=1e-6):
    ring = [p for p in pts if abs(p.z - z) <= eps]
    return sum(ring, Vector()) / len(ring)


def horse_audit(me):
    parts = classify(me)
    out = {k: len(parts.get(k, [])) for k in range(0, 9)}
    beams = sorted(parts.get(P_BEAM, []), key=lambda r: r["c"].x)
    plank = parts.get(P_PLANK, [])
    legs = []
    for r in parts.get(P_LEG, []):
        beam = min(beams, key=lambda bm_: abs(bm_["c"].x - r["c"].x)) if beams else None
        if beam is None:
            continue
        hx = beam["c"].x
        sx = 1.0 if r["c"].x > hx else -1.0
        sy = 1.0 if r["c"].y > 0.0 else -1.0
        bot, top = end_centroid(r["pts"], r["lo"].z), end_centroid(r["pts"], r["hi"].z)
        dz = top.z - bot.z
        side = math.degrees(math.atan2(sx * (bot.x - top.x), dz))
        end = math.degrees(math.atan2(sy * (bot.y - top.y), dz))
        # Housing: how far the leg's inner face is let into the beam's side,
        # read on every leg vertex at or above the beam's underside.
        inside = [abs(p.x - hx) for p in r["pts"] if p.z >= beam["lo"].z]
        bite = BEAM_W * 0.5 - min(inside) if inside else -99.0
        legs.append({"horse": beams.index(beam), "sx": sx, "sy": sy, "foot": r["lo"].z,
                     "side": side, "end": end, "bite": bite})
    out["legs"] = sorted(legs, key=lambda d: (d["horse"], d["sx"], d["sy"]))
    seats = []
    if plank and beams:
        pk = plank[0]
        for bmr in beams:
            covers = (pk["lo"].x < bmr["lo"].x and pk["hi"].x > bmr["hi"].x
                      and pk["lo"].y > bmr["lo"].y and pk["hi"].y < bmr["hi"].y)
            seats.append({"seat": pk["lo"].z - bmr["hi"].z, "covers": covers})
    out["seats"] = seats
    out["span"] = (beams[1]["c"].x - beams[0]["c"].x) if len(beams) == 2 else -99.0
    out["beam_l"] = min((r["ext"].y for r in beams), default=-99.0)
    if plank:
        e = plank[0]["ext"]
        out["plank"] = (e.x, e.y, e.z)
    else:
        out["plank"] = (-99.0, -99.0, -99.0)
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
    """Compound collider: one hull per horse, one over the plank.

    The saw is left out: a 22 mm handle and a millimetre of blade on the
    plank's top, inside the plank hull's reach for any game query.
    """
    parts = classify(obj.data)
    beams = sorted(parts.get(P_BEAM, []), key=lambda r: r["c"].x)
    groups = []
    for bmr in beams:
        groups.append([p for k in (P_BEAM, P_LEG, P_APRON) for r in parts.get(k, [])
                       for p in r["pts"] if abs(r["c"].x - bmr["c"].x) < SPAN / 2])
    groups.append([p for r in parts.get(P_PLANK, []) for p in r["pts"]])
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
    img = bpy.data.images.new("HorseNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = PINE_IDX
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
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_yup=True,
                              export_apply=True, export_draco_mesh_compression_enable=False,
                              export_animations=False)


def check(skip_decimate, lift_z=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_mesh("SawhorseLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_mesh("SawhorseHigh", hi=True, **hi_flags)
    mats = piece_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        _co = [0.0] * (len(low.data.vertices) * 3)
        low.data.vertices.foreach_get("co", _co)
        _co[2::3] = [z + LIFT_Z for z in _co[2::3]]
        low.data.vertices.foreach_set("co", _co)
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[PINE_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "SawhorseLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "SawhorseLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(low, "SawhorseCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_sawhorse_plank_{os.getpid()}.glb")
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
    ha = horse_audit(low.data)
    legs = ha["legs"]

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
    print("measured parts " + " ".join(f"{k}={ha[k]}" for k in range(0, 9)))
    for d in legs:
        print(f"measured leg horse={d['horse']} sx={d['sx']:+.0f} sy={d['sy']:+.0f} "
              f"foot={d['foot'] * 1000:.4f}mm side={d['side']:.4f}deg end={d['end']:.4f}deg "
              f"bite={d['bite'] * 1000:.3f}mm")
    for i, s in enumerate(ha["seats"]):
        print(f"measured seat{i}={s['seat'] * 1000:.4f}mm covers={s['covers']}")
    print(f"measured span={ha['span']:.4f} beam_l={ha['beam_l']:.4f} "
          f"plank=({ha['plank'][0]:.4f},{ha['plank'][1]:.4f},{ha['plank'][2]:.4f})")

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
    bad = {k: (ha[k], n) for k, n in EXPECTED_PARTS.items() if ha[k] != n}
    if bad or ha[0]:
        return (fail(f"part counts (got, want) {bad} untagged shells {ha[0]}", 3),) + nothing
    for d in legs:
        if not (BITE_MIN <= d["bite"] <= BITE_MAX):
            return (fail(f"horse {d['horse']} leg ({d['sx']:+.0f},{d['sy']:+.0f}) is let "
                         f"{d['bite'] * 1000:.2f} mm into its beam, band [{BITE_MIN * 1000}, "
                         f"{BITE_MAX * 1000}] mm (--loose-leg is the designed fail)", 17),) + nothing
    for d in legs:
        if abs(d["foot"]) > FOOT_TOL:
            return (fail(f"horse {d['horse']} leg ({d['sx']:+.0f},{d['sy']:+.0f}) foot "
                         f"{d['foot'] * 1000:.2f} mm off the floor (> {FOOT_TOL * 1000} mm) "
                         "(--short-leg is the designed fail)", 18),) + nothing
    for d in legs:
        if abs(d["side"] - SIDE_SPLAY) > SPLAY_TOL or abs(d["end"] - END_SPLAY) > SPLAY_TOL:
            return (fail(f"horse {d['horse']} leg ({d['sx']:+.0f},{d['sy']:+.0f}) splay "
                         f"{d['side']:.3f} deg side / {d['end']:.3f} deg end, declared "
                         f"{SIDE_SPLAY} / {END_SPLAY} +- {SPLAY_TOL} "
                         "(--uneven-splay is the designed fail)", 19),) + nothing
    pl = ha["plank"]
    if (abs(ha["span"] - SPAN) > SIZE_TOL or abs(ha["beam_l"] - BEAM_L) > SIZE_TOL
            or abs(pl[0] - PLANK_L) > SIZE_TOL or abs(pl[1] - PLANK_W) > SIZE_TOL
            or abs(pl[2] - PLANK_T) > SIZE_TOL):
        return (fail(f"real-world size: span {ha['span']:.4f} (want {SPAN}), beam "
                     f"{ha['beam_l']:.4f} (want {BEAM_L}), plank {pl[0]:.4f} x {pl[1]:.4f} x "
                     f"{pl[2]:.4f} (want {PLANK_L} x {PLANK_W} x {PLANK_T})", 19),) + nothing
    if len(ha["seats"]) != 2:
        return (fail(f"expected a plank seat on two saddles, found {len(ha['seats'])}", 20),) + nothing
    for i, s in enumerate(ha["seats"]):
        if not s["covers"] or not (SEAT_MIN <= s["seat"] <= SEAT_MAX):
            return (fail(f"saddle {i}: plank underside {s['seat'] * 1000:.3f} mm from the beam "
                         f"top (band [{SEAT_MIN * 1000}, {SEAT_MAX * 1000}] mm), spans it in plan "
                         f"{s['covers']} (--low-horse is the designed fail)", 20),) + nothing
    return 0, low, high, mats, tex, collider


def wire_normal(mats, tex):
    """The baked map into every slot: the whole low mesh shares one UV
    layout, so the bake (rounded arrises, hand-hole edges) belongs to each
    material, not only the one that held the bake target."""
    for mat in mats:
        nt = mat.node_tree
        src = tex if tex.id_data == nt else nt.nodes.new("ShaderNodeTexImage")
        if src is not tex:
            src.image = tex.image
        nrm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(src.outputs["Color"], nrm.inputs["Color"])
        bump = nt.nodes.get("WoodBump")
        target = bump.inputs["Normal"] if bump else nt.nodes["Principled BSDF"].inputs["Normal"]
        nt.links.new(nrm.outputs["Normal"], target)


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only.
    low.rotation_euler.z = math.radians(-48.0)

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
    wall.location = (0.0, 3.4, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, kind, loc, energy, size, col, target=(0.0, 0.0, 0.4), spread=180.0):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        if kind == "AREA":
            ld.size = size
            ld.spread = math.radians(spread)
        else:
            ld.shadow_soft_size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(ob)

    light("Key", "AREA", (-3.4, -4.6, 5.0), 350.0, 1.0, (1.0, 0.96, 0.90), spread=40.0)
    light("Fill", "AREA", (4.0, -3.4, 2.0), 30.0, 4.0, (0.75, 0.85, 1.0))
    light("Rim", "AREA", (2.4, 2.6, 3.0), 220.0, 1.5, (0.60, 0.78, 1.0), (0.0, 0.0, 0.6), spread=50.0)
    # Reflector card for the saw: a polished blade mirrors what it faces, and
    # in a dark studio that is black. The blade's camera-side normal, after
    # the piece's -48 deg turn and the saw's lean, mirrors the camera ray out
    # low to the left, so the card stands there (out of frame), aimed at the
    # saw. Wide and weak, it barely lifts the wood.
    light("Card", "AREA", (-2.7, -1.6, 0.75), 16.0, 1.3, (0.92, 0.95, 1.0), (0.18, -0.91, 0.40))
    ld = bpy.data.lights.new("Wedge", "SPOT")
    ld.energy, ld.color = 420.0, (1.0, 0.70, 0.40)
    ld.spot_size, ld.spot_blend, ld.shadow_soft_size = math.radians(60.0), 1.0, 0.3
    wedge = bpy.data.objects.new("Wedge", ld)
    wedge.location = (-0.8, 1.6, 2.4)
    wedge.rotation_euler = (Vector((0.6, 3.4, 0.9)) - wedge.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.collection.objects.link(wedge)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-0.55, -3.70, 1.55)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.05, 0.0, 0.24)
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
        scene.eevee.taa_render_samples = 64
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
    p.add_argument("--loose-leg", action="store_true",
                   help="falsification: one leg pulled 14 mm out of its housing (exit 17)")
    p.add_argument("--short-leg", action="store_true",
                   help="falsification: one leg 8 mm short of the floor (exit 18)")
    p.add_argument("--uneven-splay", action="store_true",
                   help="falsification: one leg splayed 19 deg instead of 15 (exit 19)")
    p.add_argument("--low-horse", action="store_true",
                   help="falsification: the second horse 6 mm low under the plank (exit 20)")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        loose_leg=args.loose_leg,
        short_leg=args.short_leg,
        uneven_splay=args.uneven_splay,
        low_horse=args.low_horse,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("sawhorse plank OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
