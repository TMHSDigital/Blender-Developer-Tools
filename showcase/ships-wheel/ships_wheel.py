"""Game-ready ship's wheel on its pedestal — a showcase piece, not an example.

Asserts budget conformance of a procedural ship's wheel (a helm): eight
turned spokes running from a brass nave out to a laminated teak rim, eight
turned handles carried on past the rim on the spokes' own axes, a brass
band on the rim's face, brass ferrules where the handles leave the rim and
a second ring on the king spoke, all turning on an iron shaft held in a
brass bearing collar on a teak pedestal standing on a stepped plinth.
Carried through UVs, three materials (teak, brass, iron), a high-to-low
normal bake, an LOD chain, a compound convex collider, and a Unity glTF
export.

The budget that matters is the one a wheel fails invisibly: exact radial
repetition. Eight spokes that look evenly spread can be half a degree out
and the rim binds on the one that is long; a spoke a few millimetres short
still meets the rim in every picture taken face-on, but carries nothing;
a nave a couple of millimetres off the rim's centre wobbles the wheel on
every turn. The piece measures every spoke's and handle's axis off its own
vertices, every seat against the rim's measured inner and outer faces, the
rim's centre against the nave's, and the shaft inside the nave's bore.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--offset-hub`` the nave concentric
with the rim and coaxial on the shaft, ``--short-spoke`` a spoke seated in
the rim, ``--skew-spoke`` equal angular spacing.

No randomness. DECIMATE COLLAPSE triangle counts are not byte-identical
across Blender versions — the LOD gate is a ratio band.

    blender --background --python ships_wheel.py --
    blender --background --python ships_wheel.py -- --skew-spoke
    blender --background --python ships_wheel.py -- --output ships_wheel.png
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

# --- dimensions, metres. X across the wheel, Y along the shaft (the wheel's
# face looks toward -Y, the pedestal stands behind it at +Y), Z up.
# A one-metre, eight-spoke wheel: 0.72 m over the rim, 0.50 m from the
# centre to each handle's tip, a 160 mm brass nave on a 40 mm iron shaft,
# its centre a metre above the deck — the proportions of a small vessel's
# pedestal-mounted helm.

ZC = 1.000                  # wheel centre height
SPOKES = 8
KING_ANGLE = 90.0           # the king spoke stands upright at rest
R_IN, R_OUT, RIM_T = 0.310, 0.360, 0.046
HUB_R, HUB_Y0, HUB_L = 0.080, -0.065, 0.120
SHAFT_R, SHAFT_Y0, SHAFT_Y1 = 0.020, -0.080, 0.250
HUB_BORE = SHAFT_R + 0.0006
SPOKE_SEAT = 0.003          # spoke tip this far into the rim's inner face
HANDLE_SEAT = 0.004         # handle foot this far into the rim's outer face
HANDLE_TIP = 0.500
BAND_IN, BAND_OUT = R_IN + 0.020, R_OUT - 0.020   # a 10 mm brass inlay

# Pedestal: stepped plinth, square column, cap, brass collar on its face.
PLINTH = (-0.280, 0.280, -0.060, 0.500, 0.000, 0.050)
STEP = (-0.200, 0.200, 0.020, 0.420, 0.045, 0.090)
COLUMN = (-0.100, 0.100, 0.120, 0.320, 0.085, ZC + 0.100)
CAP = (-0.125, 0.125, 0.095, 0.345, ZC + 0.095, ZC + 0.140)
COLLAR_Y0, COLLAR_Y1 = 0.084, 0.124
BOLT_RING = 0.072

# Falsifier magnitudes.
OFFSET_HUB = 0.002
SHORT_SPOKE = 0.010
SKEW_SPOKE_DEG = 2.0
LIFT_Z = 0.05
SHORT_K, SKEW_K = 3, 1      # diagonal spokes: the envelope does not move

BBOX_TOL = 0.020
OUTER_SIZE = (1.000, 0.602, 1.500)

BASE_TRIS_MIN = 8700
BASE_TRIS_MAX = 9700
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
FACE_FLOORS = {0: 2800, 1: 1450, 2: 190}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 560
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05

CONC_TOL = 0.0003           # nave centre to rim centre, in the wheel's plane
COAX_TOL = 0.0003           # shaft axis to nave axis
BORE_MIN, BORE_MAX = 0.0003, 0.0010     # radial clearance, shaft in nave
SEAT_MIN, SEAT_MAX = 0.001, 0.006       # spoke tip / handle foot depth into the rim
SPACING_TOL = 0.05          # degrees, consecutive spoke axes vs 360 / N
COAX_DEG = 0.05             # handle axis vs its spoke's axis, degrees
WHEEL_D, WHEEL_D_TOL = 2 * HANDLE_TIP, 0.004
RIM_D, RIM_D_TOL = 2 * R_OUT, 0.004
ZC_TOL = 0.002

TIMBER_IDX = 0
BRASS_IDX = 1
IRON_IDX = 2

# Part ids, a face attribute written at build time; shells take their
# part from their faces. 0 is "not yet tagged".
P_PLINTH, P_COLUMN, P_CAP, P_COLLAR, P_BOLT, P_SHAFT, P_NUT = 1, 2, 3, 4, 5, 6, 7
P_HUB, P_SPOKE, P_RIM, P_BAND, P_HANDLE, P_FERRULE, P_KING = 8, 9, 10, 11, 12, 13, 14
P_PANEL, P_MOULD = 15, 16
NPARTS = 17
MOULD_W = 0.016


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
    id and material (faces still at part 0 are the new ones)."""

    def __init__(self, hi):
        self.bm = bmesh.new()
        self.hi = hi
        self.part = self.bm.faces.layers.int.new("Part")
        self.smooth = set()

    def seg(self, n):
        return n * 2 if self.hi else n

    def tag(self, part, mat, smooth=False):
        new = [f for f in self.bm.faces if f[self.part] == 0]
        for f in new:
            f[self.part] = part
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


def box(bm, x0, x1, y0, y1, z0, z1, off, mat):
    sq = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    rings = [[bm.verts.new((x, y, z)) for x, y in sq] for z in (z0, z1)]
    faces = loft(bm, rings)
    chamfer(bm, faces, off, mat)


def revolve(bm, profile, n, origin, axis, closed=False, phase=0.0):
    """Revolve an (r, h) profile about ``axis`` through ``origin``.

    r == 0 entries at either end are poles. ``closed`` joins the last ring
    back to the first (a tube or ring section).
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


def spoke_dir(k, skew=0.0):
    a = math.radians(KING_ANGLE + 360.0 * k / SPOKES + skew)
    return Vector((math.cos(a), 0.0, math.sin(a)))


CENTRE = Vector((0.0, 0.0, ZC))


def build_pedestal(b):
    """Stepped plinth, square column, cap; each member tenoned into the one
    below. The collar and its bolts are brass and iron on the column's face."""
    bm = b.bm
    box(bm, *PLINTH, 0.010, TIMBER_IDX)
    b.tag(P_PLINTH, TIMBER_IDX)
    box(bm, *STEP, 0.008, TIMBER_IDX)
    b.tag(P_PLINTH, TIMBER_IDX)
    box(bm, *COLUMN, 0.012, TIMBER_IDX)
    b.tag(P_COLUMN, TIMBER_IDX)
    box(bm, *CAP, 0.010, TIMBER_IDX)
    b.tag(P_CAP, TIMBER_IDX)
    build_panels(b)
    # Bearing collar: a flanged brass ring round the shaft, its flange 4 mm
    # into the column's front face.
    bore = SHAFT_R + 0.0004
    prof = [(bore, 0.0), (0.040, 0.0), (0.044, 0.004), (0.044, 0.026), (0.058, 0.028),
            (0.060, 0.032), (0.060, COLLAR_Y1 - COLLAR_Y0), (bore, COLLAR_Y1 - COLLAR_Y0)]
    revolve(bm, prof, b.seg(24), (0.0, COLLAR_Y0, ZC), (0, 1, 0), closed=True)
    b.tag(P_COLLAR, BRASS_IDX, smooth=True)
    for k in range(4):
        a = math.radians(45.0 + 90.0 * k)
        x, z = BOLT_RING * math.cos(a), ZC + BOLT_RING * math.sin(a)
        dome = [(0.0, -0.0008), (0.0075, -0.0008), (0.0075, 0.0010), (0.0060, 0.0030),
                (0.0035, 0.0042), (0.0, 0.0046)]
        revolve(bm, dome, b.seg(8), (x, COLUMN[2], z), (0, -1, 0))
        b.tag(P_BOLT, IRON_IDX, smooth=True)


def build_panels(b):
    """A moulded frame round a raised field on the column's front and both
    sides. The frame's rails stand 12 mm proud, its stiles 11 mm (so no two
    front faces are one plane), the field 6 mm; each is let into the column
    by a different depth so no two back faces are one plane either."""
    x0, x1, y0, y1, z0, z1 = COLUMN
    pz0, pz1 = z0 + 0.090, ZC - 0.140
    W = MOULD_W

    def faces():
        # (point(u, d, z), u0, u1): d is how far proud of that face.
        yield (lambda u, d, z: (u, y0 - d, z)), x0 + 0.026, x1 - 0.026
        yield (lambda u, d, z: (x0 - d, u, z)), y0 + 0.026, y1 - 0.026
        yield (lambda u, d, z: (x1 + d, u, z)), y0 + 0.026, y1 - 0.026

    def slab(pt, ua, ub, za, zb, proud, bite, part):
        c = [pt(u, d, z) for u in (ua, ub) for d in (-bite, proud) for z in (za, zb)]
        box(b.bm, min(q[0] for q in c), max(q[0] for q in c), min(q[1] for q in c),
            max(q[1] for q in c), min(q[2] for q in c), max(q[2] for q in c), 0.002, TIMBER_IDX)
        b.tag(part, TIMBER_IDX)

    for pt, u0, u1 in faces():
        for za, zb in ((pz0, pz0 + W), (pz1 - W, pz1)):
            slab(pt, u0 - 0.002, u1 + 0.002, za, zb, 0.012, 0.003, P_MOULD)
        for ua, ub in ((u0, u0 + W), (u1 - W, u1)):
            slab(pt, ua, ub, pz0 + W - 0.003, pz1 - W + 0.003, 0.011, 0.004, P_MOULD)
        slab(pt, u0 + W - 0.002, u1 - W + 0.002, pz0 + W - 0.002, pz1 - W + 0.002, 0.006, 0.002,
             P_PANEL)


def build_shaft(b):
    bm = b.bm
    L = SHAFT_Y1 - SHAFT_Y0
    prof = [(0.0, 0.0), (SHAFT_R, 0.0), (SHAFT_R, L), (0.0, L)]
    revolve(bm, prof, b.seg(16), (0.0, SHAFT_Y0, ZC), (0, 1, 0))
    b.tag(P_SHAFT, IRON_IDX, smooth=True)
    # Acorn cap nut over the shaft's end, 2 mm into the nave's front.
    nut = [(0.0, -0.002), (0.034, -0.002), (0.034, 0.012), (0.030, 0.016), (0.024, 0.016),
           (0.024, 0.022), (0.020, 0.030), (0.012, 0.035), (0.0, 0.037)]
    revolve(bm, nut, b.seg(12), (0.0, HUB_Y0, ZC), (0, -1, 0), phase=math.radians(15.0))
    b.tag(P_NUT, BRASS_IDX, smooth=True)


def build_hub(b, dx=0.0):
    """The nave: a turned brass drum with a front boss, bored for the shaft."""
    prof = [(HUB_BORE, 0.0), (0.040, 0.0), (0.050, 0.006), (0.058, 0.012), (0.060, 0.020),
            (0.074, 0.024), (HUB_R, 0.030), (HUB_R, 0.090), (0.074, 0.096), (0.062, 0.102),
            (0.060, 0.110), (0.054, HUB_L), (HUB_BORE, HUB_L)]
    revolve(b.bm, prof, b.seg(32), (dx, HUB_Y0, ZC), (0, 1, 0), closed=True)
    b.tag(P_HUB, BRASS_IDX, smooth=True)


def build_rim(b):
    """One laminated teak ring, rectangular in section with chamfered arrises,
    and a brass band let into its face."""
    h = RIM_T * 0.5
    prof = [(R_IN, -h), (R_OUT, -h), (R_OUT, h), (R_IN, h)]
    faces = revolve(b.bm, prof, b.seg(64), (0.0, 0.0, ZC), (0, 1, 0), closed=True)
    chamfer(b.bm, faces, 0.004, TIMBER_IDX)
    b.tag(P_RIM, TIMBER_IDX)
    band = [(BAND_IN, -h + 0.0008), (BAND_OUT, -h + 0.0008), (BAND_OUT, -h - 0.0022),
            (BAND_IN, -h - 0.0022)]
    revolve(b.bm, band, b.seg(64), (0.0, 0.0, ZC), (0, 1, 0), closed=True)
    b.tag(P_BAND, BRASS_IDX, smooth=True)


def spoke_profile(short=0.0):
    tip = R_IN + SPOKE_SEAT - short
    return [(0.0, 0.068), (0.0160, 0.068), (0.0175, 0.086), (0.0215, 0.091), (0.0215, 0.097),
            (0.0172, 0.103), (0.0192, 0.150), (0.0186, 0.215), (0.0160, 0.268), (0.0186, 0.278),
            (0.0186, 0.284), (0.0156, 0.292), (0.0150, tip - 0.004), (0.0140, tip), (0.0, tip)]


def handle_profile():
    foot = R_OUT - HANDLE_SEAT
    return [(0.0, foot), (0.0172, foot), (0.0172, 0.374), (0.0148, 0.384), (0.0186, 0.402),
            (0.0206, 0.426), (0.0186, 0.450), (0.0128, 0.468), (0.0150, 0.477), (0.0166, 0.487),
            (0.0138, 0.495), (0.0078, 0.4993), (0.0, HANDLE_TIP)]


def build_spokes(b, short_spoke=False, skew_spoke=False):
    """Eight turned spokes, each tenoned into the nave and into the rim's inner
    face, with a handle on the same axis seated into the rim's outer face."""
    bm = b.bm
    for k in range(SPOKES):
        skew = SKEW_SPOKE_DEG if (skew_spoke and k == SKEW_K) else 0.0
        d = spoke_dir(k, skew)
        short = SHORT_SPOKE if (short_spoke and k == SHORT_K) else 0.0
        revolve(bm, spoke_profile(short), b.seg(10), CENTRE, d)
        b.tag(P_SPOKE, TIMBER_IDX, smooth=True)
        revolve(bm, handle_profile(), b.seg(10), CENTRE, d)
        b.tag(P_HANDLE, TIMBER_IDX, smooth=True)
        ferrule = [(0.0164, R_OUT + 0.001), (0.0205, R_OUT + 0.001), (0.0215, R_OUT + 0.004),
                   (0.0215, R_OUT + 0.010), (0.0205, R_OUT + 0.013), (0.0164, R_OUT + 0.013)]
        revolve(bm, ferrule, b.seg(12), CENTRE, d, closed=True)
        b.tag(P_FERRULE, BRASS_IDX, smooth=True)
        if k == 0:
            # The king spoke: a brass ring round its handle marks the wheel's
            # midships position by touch in the dark.
            king = [(0.0180, 0.418), (0.0222, 0.420), (0.0228, 0.426), (0.0222, 0.432),
                    (0.0180, 0.434)]
            revolve(bm, king, b.seg(12), CENTRE, d, closed=True)
            b.tag(P_KING, BRASS_IDX, smooth=True)


def build_wheel_mesh(name, hi=False, stray_vert=False, offset_hub=False, short_spoke=False,
                     skew_spoke=False):
    b = Builder(hi)
    try:
        build_pedestal(b)
        build_shaft(b)
        build_hub(b, OFFSET_HUB if offset_hub else 0.0)
        build_rim(b)
        build_spokes(b, short_spoke, skew_spoke)

        bm = b.bm
        if stray_vert:
            bm.verts.new((0.0, 0.2, 0.5))
        big = [f for f in bm.faces if len(f.verts) > 4]
        bmesh.ops.triangulate(bm, faces=big, quad_method="BEAUTY", ngon_method="EAR_CLIP")
        smooth_verts = {v for f in b.smooth if f.is_valid for v in f.verts}
        for f in bm.faces:
            f.smooth = f[b.part] in (P_COLLAR, P_BOLT, P_SHAFT, P_NUT, P_HUB, P_SPOKE, P_BAND,
                                     P_HANDLE, P_FERRULE, P_KING) and all(
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
    """Per shell: ``WoodTone`` (one tone per member, the panel fields darker
    than their frames) and ``GrainCo``, a point attribute giving each vertex
    in its member's own grain frame — x along the fibres, y and z across
    them, offset per member — so the shader runs the grain along every
    spoke and handle, round the rim and up the column."""
    tone = [0.5] * len(me.polygons)
    grain = [0.0] * (3 * len(me.vertices))
    vf = [[] for _ in range(len(me.vertices))]
    for poly in me.polygons:
        for i in poly.vertices:
            vf[i].append(poly.index)
    pv = [0] * len(me.polygons)
    me.attributes["Part"].data.foreach_get("value", pv)
    centre = Vector((0.0, ZC))
    for k, g in enumerate(shells(me)):
        golden = (k * 0.6180339887 + 0.3) % 1.0
        t = 0.5 + 0.6 * (golden - 0.5)
        fs = {fi for i in g for fi in vf[i]}
        part = pv[next(iter(fs))] if fs else 0
        if part in (P_PLINTH, P_COLUMN, P_CAP):
            t = 0.25 + 0.08 * (k % 3)
        elif part == P_PANEL:
            t = 0.08
        elif part == P_MOULD:
            t = 0.55
        elif part == P_RIM:
            t = 0.62
        for fi in fs:
            tone[fi] = t
        # Flat-sawn figure: the ring centre sits well off the member, so the
        # rings cut it as near-parallel, uneven lines along its length.
        o1, o2 = 0.18 + 0.30 * golden, 0.11 + 0.23 * ((golden * 7.31) % 1.0)
        pts = [me.vertices[i].co for i in g]
        c = sum((Vector((q.x, q.z)) for q in pts), Vector((0.0, 0.0))) / len(pts) - centre
        for i in g:
            q = me.vertices[i].co
            if part in (P_SPOKE, P_HANDLE) and c.length > 1e-6:
                d = c.normalized()
                r = Vector((q.x, q.z)) - centre
                along, a1, a2 = r.dot(d), r.dot(Vector((-d.y, d.x))), q.y
            elif part == P_RIM:
                r = Vector((q.x, q.z)) - centre
                along = math.atan2(r.y, r.x) * 0.335
                a1, a2 = r.length - 0.335, q.y
            elif part == P_PLINTH:
                along, a1, a2 = q.x, q.y, q.z
            else:
                along, a1, a2 = q.z, q.x, q.y
            grain[3 * i:3 * i + 3] = (along + 3.7 * golden, a1 + o1, a2 + o2)
    a = me.attributes.new("WoodTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)
    gco = me.attributes.new("GrainCo", "FLOAT_VECTOR", "POINT")
    gco.data.foreach_set("vector", grain)


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


def teak_material(name):
    """Varnished teak: flat-sawn figure running along each member (read from
    the ``GrainCo`` frame), rings of uneven width broken by noise, a fine
    fibre layer, a tone and a slight hue per member, and a satin varnish
    that wears matt where hands grip."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "WoodTone"
    gco = nt.nodes.new("ShaderNodeAttribute")
    gco.attribute_type = "GEOMETRY"
    gco.attribute_name = "GrainCo"

    # Rings about the fibre axis (x of the grain frame), their spacing pulled
    # around by low-frequency noise added to the coordinate, so bands vary in
    # width and wander instead of repeating.
    warp = nt.nodes.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value = 2.2
    warp.inputs["Detail"].default_value = 2.0
    nt.links.new(gco.outputs["Vector"], warp.inputs["Vector"])
    wsub = nt.nodes.new("ShaderNodeVectorMath")
    wsub.operation = "SUBTRACT"
    wsub.inputs[1].default_value = (0.5, 0.5, 0.5)
    nt.links.new(warp.outputs["Color"], wsub.inputs[0])
    wscale = nt.nodes.new("ShaderNodeVectorMath")
    wscale.operation = "MULTIPLY"
    wscale.inputs[1].default_value = (0.0, 0.035, 0.035)
    nt.links.new(wsub.outputs["Vector"], wscale.inputs[0])
    wadd = nt.nodes.new("ShaderNodeVectorMath")
    wadd.operation = "ADD"
    nt.links.new(gco.outputs["Vector"], wadd.inputs[0])
    nt.links.new(wscale.outputs["Vector"], wadd.inputs[1])
    rings = nt.nodes.new("ShaderNodeTexWave")
    rings.wave_type = "RINGS"
    rings.rings_direction = "X"
    rings.wave_profile = "SAW"
    rings.inputs["Scale"].default_value = 4.8
    rings.inputs["Distortion"].default_value = 2.0
    rings.inputs["Detail"].default_value = 2.5
    rings.inputs["Detail Scale"].default_value = 0.8
    nt.links.new(wadd.outputs["Vector"], rings.inputs["Vector"])
    soft = nt.nodes.new("ShaderNodeMapRange")
    soft.interpolation_type = "SMOOTHSTEP"
    soft.inputs["From Min"].default_value = 0.15
    soft.inputs["From Max"].default_value = 1.0
    nt.links.new(rings.outputs["Fac"], soft.inputs["Value"])
    # Fine fibres: noise stretched hard along the grain.
    fmap = nt.nodes.new("ShaderNodeMapping")
    fmap.inputs["Scale"].default_value = (6.0, 260.0, 260.0)
    nt.links.new(gco.outputs["Vector"], fmap.inputs["Vector"])
    fib = nt.nodes.new("ShaderNodeTexNoise")
    fib.inputs["Scale"].default_value = 1.0
    fib.inputs["Detail"].default_value = 4.0
    nt.links.new(fmap.outputs["Vector"], fib.inputs["Vector"])
    figure = _math(nt, "ADD", _math(nt, "MULTIPLY", soft.outputs["Result"], 0.70),
                   _math(nt, "MULTIPLY", fib.outputs["Fac"], 0.30))

    # A narrow ramp: the figure shows as a shift in shade, not as stripes.
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.15
    ramp.color_ramp.elements[0].color = (0.128, 0.057, 0.022, 1.0)
    mid = ramp.color_ramp.elements.new(0.55)
    mid.color = (0.205, 0.098, 0.041, 1.0)
    ramp.color_ramp.elements[2].position = 0.92
    ramp.color_ramp.elements[2].color = (0.280, 0.142, 0.064, 1.0)
    nt.links.new(figure, ramp.inputs["Fac"])

    # Per member: brightness, and a hue between redder and more golden teak.
    gain = _math(nt, "MULTIPLY_ADD", tone.outputs["Fac"], 0.55)
    gain.node.inputs[2].default_value = 0.74
    grey = nt.nodes.new("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(gain, grey.inputs[ch])
    base = _mix(nt, "MULTIPLY", ramp.outputs["Color"], grey.outputs["Color"], 1.0)
    hue = _math(nt, "FRACT", _math(nt, "MULTIPLY", tone.outputs["Fac"], 3.7))
    tint = _mix(nt, "MIX", (1.06, 0.95, 0.88), (0.96, 1.00, 1.04), hue)
    base = _mix(nt, "MULTIPLY", base, tint, 1.0)
    # Hand-worn: broad blotches where the varnish has gone matt.
    blot = nt.nodes.new("ShaderNodeTexNoise")
    blot.inputs["Scale"].default_value = 14.0
    blot.inputs["Detail"].default_value = 6.0
    nt.links.new(coord.outputs["Object"], blot.inputs["Vector"])
    wear = nt.nodes.new("ShaderNodeMapRange")
    wear.inputs["From Min"].default_value = 0.56
    wear.inputs["From Max"].default_value = 0.70
    wear.inputs["To Min"].default_value = 0.0
    wear.inputs["To Max"].default_value = 0.30
    nt.links.new(blot.outputs["Fac"], wear.inputs["Value"])
    base = _mix(nt, "MIX", base, (0.150, 0.095, 0.058), wear.outputs["Result"])
    nt.links.new(base, bsdf.inputs["Base Color"])
    rough = _math(nt, "MULTIPLY_ADD", wear.outputs["Result"], 0.75)
    rough.node.inputs[2].default_value = 0.30
    nt.links.new(rough, bsdf.inputs["Roughness"])

    bump = nt.nodes.new("ShaderNodeBump")
    bump.name = "TimberBump"
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.0008
    nt.links.new(fib.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def brass_material(name):
    """Brass gone warm and slightly tarnished, rubbed bright in patches."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 38.0
    noise.inputs["Detail"].default_value = 7.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[0].color = (0.30, 0.20, 0.07, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.72, 0.52, 0.22, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 1.0
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["From Min"].default_value = 0.35
    rough.inputs["From Max"].default_value = 0.72
    rough.inputs["To Min"].default_value = 0.42
    rough.inputs["To Max"].default_value = 0.20
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def iron_material(name):
    """Black iron, oily and dark, a little rust at the edges."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 70.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.50
    ramp.color_ramp.elements[0].color = (0.030, 0.029, 0.028, 1.0)
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = (0.17, 0.075, 0.032, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.6
    bsdf.inputs["Roughness"].default_value = 0.45
    return mat


def wheel_materials():
    return (teak_material("WheelTeak"), brass_material("WheelBrass"), iron_material("WheelIron"))


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


def face_plane(p):
    """A point in the wheel's own plane (X, Z), the shaft axis being Y."""
    return Vector((p.x, p.z))


def axis_record(rec, centre):
    """A revolved member's axis off its own vertices: the direction from the
    wheel centre to the shell's centroid (a revolved shell's centroid lies on
    its axis), and how far along that axis its ends reach."""
    c = face_plane(rec["c"]) - centre
    ang = math.degrees(math.atan2(c.y, c.x)) % 360.0
    d = c.normalized()
    hs = [(face_plane(p) - centre).dot(d) for p in rec["pts"]]
    return {"ang": ang, "near": min(hs), "far": max(hs), "dir": d}


def wheel_audit(me):
    parts = classify(me)
    out = {k: len(parts.get(k, [])) for k in range(0, NPARTS)}
    rim = parts.get(P_RIM, [])
    hub = parts.get(P_HUB, [])
    shaft = parts.get(P_SHAFT, [])
    if not (rim and hub and shaft):
        out["ok"] = False
        return out
    rim, hub, shaft = rim[0], hub[0], shaft[0]
    # The rim, the nave and the shaft are each revolved about Y: the plan
    # centroid of a shell's vertices is its axis in the wheel's plane.
    rc = face_plane(rim["c"])
    hc = face_plane(hub["c"])
    sc = face_plane(shaft["c"])
    out["rim_in"] = min((face_plane(p) - rc).length for p in rim["pts"])
    out["rim_out"] = max((face_plane(p) - rc).length for p in rim["pts"])
    out["rim_zc"] = rim["c"].z
    out["conc"] = (hc - rc).length
    bore = min((face_plane(p) - hc).length for p in hub["pts"])
    r_shaft = max((face_plane(p) - sc).length for p in shaft["pts"])
    out["coax"] = (sc - hc).length
    out["bore"] = bore - r_shaft - out["coax"]
    out["r_bore"], out["r_shaft"] = bore, r_shaft

    spokes = sorted((axis_record(r, rc) for r in parts.get(P_SPOKE, [])), key=lambda a: a["ang"])
    handles = [axis_record(r, rc) for r in parts.get(P_HANDLE, [])]
    out["spokes"], out["handles"] = spokes, handles
    # Spoke tips against the rim's measured inner face; handle feet against
    # its measured outer face. Both are depths into the rim.
    out["spoke_seat"] = [s["far"] - out["rim_in"] for s in spokes]
    out["handle_seat"] = [out["rim_out"] - h["near"] for h in handles]
    n = len(spokes)
    step = 360.0 / SPOKES
    out["spacing"] = [((spokes[(i + 1) % n]["ang"] - spokes[i]["ang"]) % 360.0) - step
                      for i in range(n)] if n else [99.0]
    coax = []
    for h in handles:
        dev = min(abs(((h["ang"] - s["ang"]) + 180.0) % 360.0 - 180.0) for s in spokes) if spokes else 99.0
        coax.append(dev)
    out["handle_coax"] = coax
    out["wheel_d"] = 2.0 * max((h["far"] for h in handles), default=0.0)
    out["ok"] = True
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
    """Compound collider: one hull over the plinth, one over the column and
    its cap, one over the whole wheel (rim, spokes, handles, nave, shaft).

    A turning wheel is a disc to anything that hits it; the gaps between the
    spokes are not worth hulls of their own."""
    parts = classify(obj.data)
    groups = [
        [p for r in parts.get(P_PLINTH, []) for p in r["pts"]],
        [p for k in (P_COLUMN, P_CAP, P_PANEL, P_MOULD, P_COLLAR, P_BOLT) for r in parts.get(k, []) for p in r["pts"]],
        [p for k in (P_HUB, P_SHAFT, P_NUT, P_SPOKE, P_RIM, P_BAND, P_HANDLE, P_FERRULE, P_KING)
         for r in parts.get(k, []) for p in r["pts"]],
    ]
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
    img = bpy.data.images.new("WheelNrm", size, size, alpha=True, float_buffer=False)
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


EXPECTED_PARTS = {P_PLINTH: 2, P_COLUMN: 1, P_CAP: 1, P_COLLAR: 1, P_BOLT: 4, P_SHAFT: 1,
                  P_NUT: 1, P_HUB: 1, P_SPOKE: SPOKES, P_RIM: 1, P_BAND: 1,
                  P_HANDLE: SPOKES, P_FERRULE: SPOKES, P_KING: 1, P_PANEL: 3, P_MOULD: 12}


def check(skip_decimate, lift_z=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_wheel_mesh("WheelLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_wheel_mesh("WheelHigh", hi=True, **hi_flags)
    mats = wheel_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("wheel mesh did not build, or has no UV layer", 3),) + nothing

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

    lod1 = make_lod(low, "WheelLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "WheelLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(low, "WheelCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_ships_wheel_{os.getpid()}.glb")
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
    wa = wheel_audit(low.data)

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
    print("measured parts " + " ".join(f"{k}={wa[k]}" for k in range(0, NPARTS)))
    if wa.get("ok"):
        print(f"measured rim_in={wa['rim_in']:.5f} rim_out={wa['rim_out']:.5f} "
              f"rim_zc={wa['rim_zc']:.5f} conc={wa['conc'] * 1000:.4f}mm "
              f"coax={wa['coax'] * 1000:.4f}mm bore={wa['bore'] * 1000:.4f}mm "
              f"(r_bore={wa['r_bore'] * 1000:.3f} r_shaft={wa['r_shaft'] * 1000:.3f})")
        print("measured spoke_ang=" + ",".join(f"{s['ang']:.4f}" for s in wa["spokes"]))
        print("measured spacing_dev=" + ",".join(f"{d:.5f}" for d in wa["spacing"]))
        print("measured spoke_seat_mm=" + ",".join(f"{s * 1000:.3f}" for s in wa["spoke_seat"]))
        print("measured handle_seat_mm=" + ",".join(f"{s * 1000:.3f}" for s in wa["handle_seat"]))
        print("measured handle_coax_deg=" + ",".join(f"{d:.5f}" for d in wa["handle_coax"]))
        print(f"measured wheel_d={wa['wheel_d']:.5f} rim_d={2 * wa['rim_out']:.5f}")

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
    bad = {k: (wa[k], n) for k, n in EXPECTED_PARTS.items() if wa[k] != n}
    if bad or wa[0] or not wa.get("ok"):
        return (fail(f"part counts (got, want) {bad} untagged shells {wa[0]}", 3),) + nothing
    if wa["conc"] > CONC_TOL or wa["coax"] > COAX_TOL or not (BORE_MIN <= wa["bore"] <= BORE_MAX):
        return (fail(f"nave {wa['conc'] * 1000:.3f} mm off the rim's centre (<= {CONC_TOL * 1000} mm), "
                     f"shaft {wa['coax'] * 1000:.3f} mm off the nave's axis (<= {COAX_TOL * 1000} mm), "
                     f"bore clearance {wa['bore'] * 1000:.3f} mm outside "
                     f"[{BORE_MIN * 1000}, {BORE_MAX * 1000}] mm "
                     "(--offset-hub is the designed fail)", 17),) + nothing
    for i, s in enumerate(wa["spoke_seat"]):
        if not (SEAT_MIN <= s <= SEAT_MAX):
            return (fail(f"spoke {i} ({wa['spokes'][i]['ang']:.2f} deg): tip {s * 1000:.3f} mm into the "
                         f"rim's inner face, band [{SEAT_MIN * 1000}, {SEAT_MAX * 1000}] mm "
                         "(--short-spoke is the designed fail)", 18),) + nothing
    for i, s in enumerate(wa["handle_seat"]):
        if not (SEAT_MIN <= s <= SEAT_MAX):
            return (fail(f"handle {i}: foot {s * 1000:.3f} mm into the rim's outer face, band "
                         f"[{SEAT_MIN * 1000}, {SEAT_MAX * 1000}] mm", 18),) + nothing
    worst = max(abs(d) for d in wa["spacing"])
    if len(wa["spacing"]) != SPOKES or worst > SPACING_TOL:
        return (fail(f"spoke spacing off 360/{SPOKES} by up to {worst:.4f} deg (> {SPACING_TOL} deg) "
                     "(--skew-spoke is the designed fail)", 19),) + nothing
    worst = max(wa["handle_coax"], default=99.0)
    if worst > COAX_DEG:
        return (fail(f"a handle is {worst:.4f} deg off its spoke's axis (> {COAX_DEG} deg)", 19),) + nothing
    if (abs(wa["wheel_d"] - WHEEL_D) > WHEEL_D_TOL or abs(2 * wa["rim_out"] - RIM_D) > RIM_D_TOL
            or abs(wa["rim_zc"] - ZC) > ZC_TOL):
        return (fail(f"real-world size: wheel {wa['wheel_d']:.4f} m over the handles (want {WHEEL_D}), "
                     f"rim {2 * wa['rim_out']:.4f} m (want {RIM_D}), centre {wa['rim_zc']:.4f} m "
                     f"above the deck (want {ZC})", 19),) + nothing
    return 0, low, high, mats, tex, collider


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
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only, so the camera sees the wheel's
    # face, the spokes' turnings and the nave, with the pedestal behind.
    yaw = math.radians(-28.0)
    low.rotation_euler.z = yaw
    centre = Vector((0.0, 0.22, 0.0))
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

    def light(name, kind, loc, energy, size, col, target=(0.0, 0.0, 0.9)):
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

    light("Key", "AREA", (-2.4, -3.6, 4.2), 250.0, 1.0, (1.0, 0.95, 0.88))
    light("Fill", "AREA", (3.6, -2.8, 1.8), 35.0, 5.0, (0.74, 0.84, 1.0))
    light("Rim", "AREA", (1.8, 3.2, 3.0), 160.0, 3.0, (0.62, 0.78, 1.0), (0.0, 0.0, 1.0))
    # Warm wedge: on the wall behind the wheel, between it and the wall,
    # so the wheel's silhouette reads against a warm gradient.
    light("Wedge", "AREA", (0.2, 6.6, 0.3), 420.0, 2.0, (1.0, 0.70, 0.40), (-0.1, 8.5, 1.6))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-1.69, -4.55, 1.79)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.76)
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
    p.add_argument("--skip-decimate", action="store_true",
                   help="falsification: no DECIMATE on the LODs (exit 9)")
    p.add_argument("--stray-vert", action="store_true",
                   help="falsification: one loose vertex (exit 15)")
    p.add_argument("--lift-z", action="store_true",
                   help="falsification: the whole piece 50 mm off the floor (exit 16)")
    p.add_argument("--offset-hub", action="store_true",
                   help="falsification: the nave 2 mm off the rim's centre (exit 17)")
    p.add_argument("--short-spoke", action="store_true",
                   help="falsification: one spoke 10 mm short of the rim (exit 18)")
    p.add_argument("--skew-spoke", action="store_true",
                   help="falsification: one spoke and its handle turned 2 deg (exit 19)")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        offset_hub=args.offset_hub,
        short_spoke=args.short_spoke,
        skew_spoke=args.skew_spoke,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("ships wheel OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
