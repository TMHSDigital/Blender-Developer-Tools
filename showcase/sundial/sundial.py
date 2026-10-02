"""Game-ready garden sundial — a showcase piece, not an example.

Asserts budget conformance of a procedural horizontal sundial: a stepped
stone plinth, a tapered octagonal granite column with a flared collar and
a cap, a bronze dial plate with a raised rim, a curved-backed bronze
gnomon, and inked hour lines laid out for a named latitude. Carried
through UVs, three materials (stone, bronze, ink), a high-to-low normal
bake, an LOD chain, a compound convex collider, and a Unity glTF export.

The budget that matters here is the one a sundial fails invisibly: it has
to tell the time. A gnomon whose style edge is tilted to the wrong angle
still stands on the plate, still fits the bounding box and still takes its
bite; a dial whose hour lines are spaced evenly at 15 degrees looks like a
sundial in every picture. Only the geometry knows. The piece measures the
style edge's inclination off the finished gnomon's faces, and every hour
line's bearing off its own vertices, and compares them with the horizontal
dial formula ``tan(H) = sin(latitude) * tan(15 deg * hours from noon)``.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--wrong-latitude`` the style angle,
``--linear-hours`` the hour-line bearings, ``--float-gnomon`` the gnomon's
bite into the plate, ``--float-lines`` the inked lines' seat,
``--lean-pedestal`` the column's plumb, ``--shift-noon`` the noon line on
the gnomon's meridian.

No randomness. DECIMATE COLLAPSE triangle counts are not byte-identical
across Blender versions — the LOD gate is a ratio band.

    blender --background --python sundial.py --
    blender --background --python sundial.py -- --linear-hours
    blender --background --python sundial.py -- --output sundial.png
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
from mathutils.kdtree import KDTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

# The dial: a horizontal plate for 45 degrees north. The gnomon's style
# edge rises toward north (+Y) at the latitude; hour lines fan out from
# the point where the style edge meets the plate.
LATITUDE = 45.0
LAT = math.radians(LATITUDE)
WRONG_LATITUDE = 38.0
HOURS = [h for h in range(7, 18) if h != 12]
TICKS = [h + 0.5 for h in range(7, 17)]
NOON_HALF_W = 0.0050

# Stone, bottom up. Every upper part is tenoned SEAT into its host and its
# top is the figure that is fixed, so no two bodies land on one plane.
SEAT = 0.010
BASE_W, BASE_TOP = 0.600, 0.085
STEP_W, STEP_TOP = 0.480, 0.150
COL_AF0, COL_AF1, COL_TOP = 0.270, 0.205, 0.810
COLLAR_AF0, COLLAR_AF1 = 0.215, 0.340
COLLAR_Z0, COLLAR_TOP = 0.795, 0.835
FOOT_AF0, FOOT_AF1, FOOT_Z0, FOOT_TOP = 0.350, 0.290, STEP_TOP - SEAT * 0.5, STEP_TOP + 0.050
CAP_AF, CAP_TOP = 0.460, 0.870
CAP_Z0 = COLLAR_TOP - SEAT
LEAN = 0.012
# Astragal beads round the column shaft: one bedded in the foot, one tucked
# up into the collar. Each grips the shaft by BEAD_GRIP and is buried in its
# host block by BEAD_BED, so neither lands on a face of either.
BEAD_GRIP, BEAD_BED, BEAD_H, BEAD_PROUD = 0.008, 0.003, 0.026, 0.034

# Dial plate: bronze, a bead rim round a flat field.
PLATE_SEG = 64
PLATE_SEG_HI = 128
PLATE_Z0 = CAP_TOP - 0.004
PLATE_TOP = CAP_TOP + 0.010
FIELD_R = 0.176
PLATE_R = 0.200

# Gnomon: a thin bronze plate in the meridian plane, style edge straight,
# back edge curved. The style edge is the top edge from foot to apex.
GN_L = 0.130
GN_T = 0.008
GN_BITE = 0.0035
GN_SAG = 0.016
GN_CHAMFER = 0.0008
FLOAT_GNOMON = 0.005

# Ink: raised lines on the plate, a keel in the bronze under a low ridge.
# Hour lines run in to an inner chapter ring; the numerals stand in the band
# between it and the outer ring, each stroke laid along its own radius.
BAR_R0, BAR_R1 = 0.060, 0.127
TICK_R0 = 0.108
BAR_HALF_W = 0.0030
TICK_HALF_W = 0.0020
RING_R = 0.1665
INNER_RING_R = 0.1285
NUM_R0, NUM_R1 = 0.1345, 0.1595
NUM_HALF_W = 0.0016
NUM_V_W, NUM_X_W, NUM_GAP = 0.0110, 0.0104, 0.0030
NUMERALS = {7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI",
            13: "I", 14: "II", 15: "III", 16: "IV", 17: "V"}
BAR_TICK_SPLIT_R = 0.105
NUM_BAND = (0.131, 0.161)
NOON_Y0, NOON_Y1, NOON_TIP = 0.138, 0.152, 0.170
INK_KEEL, INK_SHOULDER, INK_EDGE, INK_RIDGE = -0.0025, -0.0010, 0.0010, 0.0020
FLOAT_LINES = 0.004
SHIFT_NOON = 0.003

BBOX_TOL = 0.020
OUTER_SIZE = (0.600, 0.600, 1.010)

BASE_TRIS_MIN = 3600
BASE_TRIS_MAX = 4200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
FACE_FLOORS = {0: 240, 1: 430, 2: 1300}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 480
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05

STYLE_TOL_DEG = 0.25
FOOT_TOL = 0.0005
BEARING_TOL_DEG = 0.10
RADIAL_TOL_DEG = 1.0
BITE_MIN, BITE_MAX = 0.0020, 0.0050
PROUD_MIN, PROUD_MAX = 0.0005, 0.0025
INK_SEAT_MIN, INK_SEAT_MAX = 0.0008, 0.0030
MERIDIAN_TOL = 0.0005
PLUMB_TOL = 0.0015
COLUMN_H, COLUMN_H_TOL = 0.670, 0.020
PLATE_DIA, PLATE_DIA_TOL = 0.400, 0.004
GNOMON_H, GNOMON_H_TOL = 0.130, 0.003

STONE_IDX = 0
BRONZE_IDX = 1
INK_IDX = 2


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


# --- dial geometry ----------------------------------------------------------


def hour_bearing(hours, linear=False):
    """Bearing from north, east positive, of the line for solar time ``hours``.

    The horizontal-dial formula tan(phi) = sin(lat) * tan(H) with H the hour
    angle, taken through atan2 so the quadrant is right near the 6 o'clock
    lines. ``linear`` spaces them at 15 degrees an hour instead.
    """
    h = math.radians(15.0 * (hours - 12.0))
    if linear:
        return h
    return math.atan2(math.sin(LAT) * math.sin(h), math.cos(h))


def plate_profile():
    zt, zb = PLATE_TOP, PLATE_Z0
    return [(0.0, zt), (FIELD_R, zt), (FIELD_R + 0.005, zt + 0.004),
            (PLATE_R - 0.007, zt + 0.004), (PLATE_R, zt - 0.003),
            (PLATE_R, zb + 0.004), (PLATE_R - 0.005, zb), (0.0, zb)]


def ink_section(half_w):
    """Keeled hexagon: a ridge proud of the plate, a keel buried in it."""
    return [(0.0, INK_KEEL), (half_w, INK_SHOULDER), (half_w, INK_EDGE),
            (0.0, INK_RIDGE), (-half_w, INK_EDGE), (-half_w, INK_SHOULDER)]


def gnomon_outline(wrong_latitude):
    """(y, z) polygon of the gnomon, style edge from foot to apex first.

    The style edge is fixed by its apex and its slope. At the design
    latitude it runs through the dial centre at the plate's top; at the
    wrong one the apex stays put and the foot slides south, so the
    envelope does not change.
    """
    zt, zb = PLATE_TOP, PLATE_TOP - GN_BITE
    apex_z = zt + GN_L * math.tan(LAT)
    slope = math.tan(math.radians(WRONG_LATITUDE)) if wrong_latitude else math.tan(LAT)
    y_a = GN_L - (apex_z - zb) / slope
    # The style edge is one straight edge, foot to apex: intermediate vertices
    # on it are collinear, and an ear-clipped cap turns collinear triples into
    # zero-area triangles.
    pts = [(y_a, zb), (GN_L, apex_z)]
    steps = 10
    for k in range(1, steps):
        s = k / steps
        pts.append((GN_L - GN_SAG * math.sin(math.pi * s), apex_z + (zb - apex_z) * s))
    pts.append((GN_L, zb))
    return pts


# --- construction -----------------------------------------------------------


def loft(bm, rings, mat, cap=True):
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
    for f in faces:
        f.material_index = mat
    return faces


def chamfer(bm, faces, offset, mat):
    """One-segment chamfer on the shell's near-right-angle edges only.

    ``recalc_face_normals`` comes first: the dihedral is read off face
    normals, and a wound-wrong face turns a 90 degree edge into a 90
    degree edge the other way round. The bevel's own faces take ``mat``
    explicitly; left alone they take slot 0.
    """
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    own = set(faces)
    bm.edges.index_update()
    edges = sorted({e for f in faces for e in f.edges}, key=lambda e: e.index)
    pick = [e for e in edges
            if len(e.link_faces) == 2 and all(lf in own for lf in e.link_faces)
            and math.radians(60.0) <= e.calc_face_angle(0.0) <= math.radians(120.0)]
    if pick:
        bmesh.ops.bevel(bm, geom=pick, offset=offset, segments=1, profile=0.5,
                        affect="EDGES", clamp_overlap=True, material=mat)


def stone_frustum(bm, n, af0, af1, z0, z1, off, lean=0.0):
    """Regular n-gon frustum, flats on the axes, ``af`` across flats."""
    rings = []
    for af, z, shift in ((af0, z0, 0.0), (af1, z1, lean)):
        radius = af * 0.5 / math.cos(math.pi / n)
        rings.append([bm.verts.new((radius * math.cos((k + 0.5) * 2.0 * math.pi / n) + shift,
                                    radius * math.sin((k + 0.5) * 2.0 * math.pi / n), z))
                      for k in range(n)])
    faces = loft(bm, rings, STONE_IDX)
    chamfer(bm, faces, off, STONE_IDX)


def column_af(z):
    """Across-flats width of the (unleaned) column shaft at height ``z``."""
    z0 = STEP_TOP - SEAT
    return COL_AF0 + (COL_AF1 - COL_AF0) * (z - z0) / (COL_TOP - z0)


def octo_ring(bm, profile):
    """Closed (af, z) profile swept round an octagon, flats on the axes."""
    n = 8
    rings = []
    for af, z in profile:
        radius = af * 0.5 / math.cos(math.pi / n)
        rings.append([bm.verts.new((radius * math.cos((k + 0.5) * 2.0 * math.pi / n),
                                    radius * math.sin((k + 0.5) * 2.0 * math.pi / n), z))
                      for k in range(n)])
    faces = []
    for a, b in zip(rings, rings[1:] + rings[:1]):
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    for f in faces:
        f.material_index = STONE_IDX
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def add_beads(bm):
    """Astragals: a half-round bead on the foot and another under the collar.

    The profile is offset from the shaft's own width at the bead's height,
    so the inner wall is BEAD_GRIP inside the taper, and the flat that
    would sit on the host block is buried BEAD_BED into it instead.
    """
    g, h, p = 2.0 * BEAD_GRIP, BEAD_H, BEAD_PROUD
    zb = FOOT_TOP - BEAD_BED
    af = column_af(zb + h * 0.5)
    octo_ring(bm, [(af - g, zb), (af + 0.010, zb), (af + p, zb + 0.009),
                   (af + p - 0.006, zb + 0.019), (af + 0.006, zb + h), (af - g, zb + h)])
    zt = COLLAR_Z0 + BEAD_BED
    af = column_af(zt - h * 0.5)
    octo_ring(bm, [(af - g, zt - h), (af + 0.010, zt - h), (af + p, zt - 0.015),
                   (af + p - 0.006, zt - 0.007), (af + 0.006, zt), (af - g, zt)])


def numeral_strokes(text):
    """Strokes of a Roman numeral as ((u0, v0), (u1, v1)) pairs, u across, v 0..1 up.

    ``u`` is metres across the band, centred on the hour line; ``v`` runs
    from the inner edge of the numeral band to the outer. The two strokes of
    a V cross just above its point rather than sharing a vertex.
    """
    hw, e = NUM_HALF_W, 0.0006
    widths = {"I": 2.0 * hw, "V": NUM_V_W, "X": NUM_X_W}
    total = sum(widths[c] for c in text) + NUM_GAP * (len(text) - 1)
    u = -total * 0.5
    out = []
    for c in text:
        w = widths[c]
        if c == "I":
            out.append(((u + hw, 0.0), (u + hw, 1.0)))
        elif c == "V":
            out.append(((u + hw, 1.0), (u + w * 0.5 + e, 0.0)))
            out.append(((u + w - hw, 1.0), (u + w * 0.5 - e, 0.0)))
        else:
            out.append(((u + hw, 1.0), (u + w - hw, 0.0)))
            out.append(((u + w - hw, 1.0), (u + hw, 0.0)))
        u += w + NUM_GAP
    return out


def add_numerals(bm, linear_hours, lift):
    """Hour numerals in the chapter band, each stroke on its own radius.

    A glyph point (u, v) goes to bearing ``phi + u / r_mid`` at radius
    ``NUM_R0 + v * (NUM_R1 - NUM_R0)``. Constant angular offset keeps an I
    radial, and two parallel-looking strokes are never on one plane. Glyph
    up is outward, glyph right is clockwise seen from above.
    """
    r_mid = 0.5 * (NUM_R0 + NUM_R1)
    for h, text in NUMERALS.items():
        phi = hour_bearing(h, linear_hours)
        for (ua, va), (ub, vb) in numeral_strokes(text):
            ends = []
            for u, v in ((ua, va), (ub, vb)):
                th, r = phi + u / r_mid, NUM_R0 + v * (NUM_R1 - NUM_R0)
                ends.append(Vector((r * math.sin(th), r * math.cos(th), 0.0)))
            straight_bar(bm, ends[0], ends[1], ink_section(NUM_HALF_W), PLATE_TOP + lift)


def numeral_stroke_count():
    return sum(len(numeral_strokes(t)) for t in NUMERALS.values())


def lathe_z(bm, profile, n, mat, closed=False):
    """Revolve an (r, z) profile about the Z axis; r == 0 entries are poles."""
    rings, poles, verts = [], [], []
    for r, z in profile:
        if r <= 1e-9:
            v = bm.verts.new((0.0, 0.0, z))
            poles.append((len(rings), v))
            verts.append(v)
        else:
            ring = [bm.verts.new((r * math.cos(2.0 * math.pi * k / n),
                                  r * math.sin(2.0 * math.pi * k / n), z)) for k in range(n)]
            rings.append(ring)
            verts += ring
    faces = []
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for a, b in pairs:
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    for at, pole in poles:
        ring = rings[0] if at == 0 else rings[-1]
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((pole, ring[i], ring[j])))
    for f in faces:
        f.material_index = mat
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return verts


def straight_bar(bm, p0, p1, section, zref, off=None):
    """``section`` (across, up) pairs swept from plan point p0 to p1."""
    d = (p1 - p0).normalized()
    side = Vector((-d.y, d.x, 0.0))
    rings = [[bm.verts.new((p.x + side.x * u, p.y + side.y * u, zref + z)) for u, z in section]
             for p in (p0, p1)]
    faces = loft(bm, rings, INK_IDX)
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def add_noon_arrow(bm, shift, lift):
    w, h = NOON_HALF_W, NOON_HALF_W * 2.0
    outline = [(-w, NOON_Y0), (w, NOON_Y0), (w, NOON_Y1), (h, NOON_Y1), (0.0, NOON_TIP),
               (-h, NOON_Y1), (-w, NOON_Y1)]
    rings = [[bm.verts.new((x + shift, y, PLATE_TOP + z + lift)) for x, y in outline]
             for z in (INK_KEEL, INK_RIDGE)]
    faces = loft(bm, rings, INK_IDX)
    chamfer(bm, faces, 0.0004, INK_IDX)


def build_sundial_mesh(
    name,
    hi=False,
    stray_vert=False,
    lift_lines=False,
    lift_gnomon=False,
    linear_hours=False,
    wrong_latitude=False,
    lean_pedestal=False,
    shift_noon=False,
):
    n_plate = PLATE_SEG_HI if hi else PLATE_SEG
    lift = FLOAT_LINES if lift_lines else 0.0
    bm = bmesh.new()
    try:
        smooth = set()
        stone_frustum(bm, 4, BASE_W, BASE_W, 0.0, BASE_TOP, 0.006)
        stone_frustum(bm, 4, STEP_W, STEP_W, BASE_TOP - SEAT, STEP_TOP, 0.005)
        stone_frustum(bm, 8, COL_AF0, COL_AF1, STEP_TOP - SEAT, COL_TOP, 0.004,
                      lean=LEAN if lean_pedestal else 0.0)
        stone_frustum(bm, 8, FOOT_AF0, FOOT_AF1, FOOT_Z0, FOOT_TOP, 0.004)
        stone_frustum(bm, 8, COLLAR_AF0, COLLAR_AF1, COLLAR_Z0, COLLAR_TOP, 0.004)
        stone_frustum(bm, 8, CAP_AF, CAP_AF, CAP_Z0, CAP_TOP, 0.006)
        add_beads(bm)

        smooth.update(lathe_z(bm, plate_profile(), n_plate, BRONZE_IDX))

        outline = gnomon_outline(wrong_latitude)
        gz = FLOAT_GNOMON if lift_gnomon else 0.0
        rings = [[bm.verts.new((x, y, z + gz)) for y, z in outline] for x in (-GN_T / 2, GN_T / 2)]
        faces = loft(bm, rings, BRONZE_IDX)
        chamfer(bm, faces, GN_CHAMFER, BRONZE_IDX)

        ring_profile = [(RING_R + u, PLATE_TOP + z + lift) for u, z in ink_section(0.003)]
        smooth.update(lathe_z(bm, ring_profile, n_plate, INK_IDX, closed=True))
        inner_profile = [(INNER_RING_R + u, PLATE_TOP + z + lift) for u, z in ink_section(0.0025)]
        smooth.update(lathe_z(bm, inner_profile, n_plate, INK_IDX, closed=True))
        add_numerals(bm, linear_hours, lift)
        for h in HOURS:
            phi = hour_bearing(h, linear_hours)
            d = Vector((math.sin(phi), math.cos(phi), 0.0))
            straight_bar(bm, d * BAR_R0, d * BAR_R1, ink_section(BAR_HALF_W), PLATE_TOP + lift)
        for h in TICKS:
            phi = hour_bearing(h, linear_hours)
            d = Vector((math.sin(phi), math.cos(phi), 0.0))
            straight_bar(bm, d * TICK_R0, d * BAR_R1, ink_section(TICK_HALF_W), PLATE_TOP + lift)
        add_noon_arrow(bm, SHIFT_NOON if shift_noon else 0.0, lift)

        if stray_vert:
            bm.verts.new((0.0, 0.0, 0.5))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        big = [f for f in bm.faces if len(f.verts) > 4]
        bmesh.ops.triangulate(bm, faces=big, quad_method="BEAUTY", ngon_method="EAR_CLIP")
        for f in bm.faces:
            f.smooth = all(v in smooth for v in f.verts)
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(35.0):
                e.smooth = False
        pack_uvs(bm)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
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
    """``StoneTone`` per shell, so no two blocks of granite read as one cut."""
    tone = [0.5] * len(me.polygons)
    vf = [[] for _ in range(len(me.vertices))]
    for p in me.polygons:
        for i in p.vertices:
            vf[i].append(p.index)
    for k, g in enumerate(shells(me)):
        t = 0.5 + 0.35 * (((k * 0.6180339887 + 0.3) % 1.0) - 0.5)
        for fi in {fi for i in g for fi in vf[i]}:
            tone[fi] = t
    a = me.attributes.new("StoneTone", "FLOAT", "FACE")
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


def stone_material(name):
    """Weathered granite: coarse tone, fine speckle, grime and lichen in the joints."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "StoneTone"

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 5.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.14, 0.13, 0.115, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.31, 0.285, 0.25, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])

    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 150.0
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    speck = nt.nodes.new("ShaderNodeValToRGB")
    speck.color_ramp.elements[0].position = 0.04
    speck.color_ramp.elements[0].color = (0.30, 0.29, 0.28, 1.0)
    speck.color_ramp.elements[1].position = 0.20
    speck.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(vor.outputs["Distance"], speck.inputs["Fac"])
    base = _mix(nt, "MULTIPLY", ramp.outputs["Color"], speck.outputs["Color"], 1.0)

    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 0.40
    gain.inputs[2].default_value = 0.80
    nt.links.new(tone.outputs["Fac"], gain.inputs[0])
    gaingrey = nt.nodes.new("ShaderNodeCombineColor")
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(gain.outputs["Value"], gaingrey.inputs[ch])
    base = _mix(nt, "MULTIPLY", base, gaingrey.outputs["Color"], 1.0)

    # Weathering lives where water sits: a narrow band at the ground and at
    # each joint of the plinth and foot, broken up by noise. Grime darkens the
    # band; a grey-olive lichen takes part of it. Low contrast on purpose.
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
    joints = None
    for jz, w in ((0.0, 0.035), (BASE_TOP, 0.022), (STEP_TOP, 0.022), (FOOT_TOP, 0.016)):
        dz = nt.nodes.new("ShaderNodeMath")
        dz.operation = "SUBTRACT"
        nt.links.new(sep.outputs["Z"], dz.inputs[0])
        dz.inputs[1].default_value = jz
        ab = nt.nodes.new("ShaderNodeMath")
        ab.operation = "ABSOLUTE"
        nt.links.new(dz.outputs["Value"], ab.inputs[0])
        band = nt.nodes.new("ShaderNodeMapRange")
        band.interpolation_type = "SMOOTHSTEP"
        band.inputs["From Min"].default_value = 0.0
        band.inputs["From Max"].default_value = w
        band.inputs["To Min"].default_value = 1.0
        band.inputs["To Max"].default_value = 0.0
        nt.links.new(ab.outputs["Value"], band.inputs["Value"])
        if joints is None:
            joints = band.outputs["Result"]
        else:
            mx = nt.nodes.new("ShaderNodeMath")
            mx.operation = "MAXIMUM"
            nt.links.new(joints, mx.inputs[0])
            nt.links.new(band.outputs["Result"], mx.inputs[1])
            joints = mx.outputs["Value"]
    patch = nt.nodes.new("ShaderNodeTexNoise")
    patch.inputs["Scale"].default_value = 24.0
    patch.inputs["Detail"].default_value = 6.0
    nt.links.new(coord.outputs["Object"], patch.inputs["Vector"])
    patchmap = nt.nodes.new("ShaderNodeMapRange")
    patchmap.interpolation_type = "SMOOTHSTEP"
    patchmap.inputs["From Min"].default_value = 0.42
    patchmap.inputs["From Max"].default_value = 0.66
    nt.links.new(patch.outputs["Fac"], patchmap.inputs["Value"])
    cover = nt.nodes.new("ShaderNodeMath")
    cover.operation = "MULTIPLY"
    nt.links.new(joints, cover.inputs[0])
    nt.links.new(patchmap.outputs["Result"], cover.inputs[1])
    grime = nt.nodes.new("ShaderNodeMath")
    grime.operation = "MULTIPLY"
    grime.inputs[1].default_value = 0.35
    nt.links.new(joints, grime.inputs[0])
    base = _mix(nt, "MIX", base, (0.075, 0.07, 0.06), grime.outputs["Value"])
    lichen = nt.nodes.new("ShaderNodeMath")
    lichen.operation = "MULTIPLY"
    lichen.inputs[1].default_value = 0.6
    nt.links.new(cover.outputs["Value"], lichen.inputs[0])
    base = _mix(nt, "MIX", base, (0.105, 0.115, 0.075), lichen.outputs["Value"])
    nt.links.new(base, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    # Bush-hammered pitting: a fine bump the baked normal map feeds into at render.
    pit = nt.nodes.new("ShaderNodeTexNoise")
    pit.inputs["Scale"].default_value = 110.0
    pit.inputs["Detail"].default_value = 3.0
    nt.links.new(coord.outputs["Object"], pit.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.name = "StoneBump"
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.002
    nt.links.new(pit.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def bronze_material(name):
    """Cast bronze going green in patches. Warm and metallic, not gold, not chrome."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 26.0
    noise.inputs["Detail"].default_value = 7.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[0].color = (0.62, 0.37, 0.12, 1.0)
    mid = ramp.color_ramp.elements.new(0.62)
    mid.color = (0.88, 0.58, 0.21, 1.0)
    ramp.color_ramp.elements[2].position = 0.80
    ramp.color_ramp.elements[2].color = (0.16, 0.40, 0.31, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    metal = nt.nodes.new("ShaderNodeMapRange")
    metal.inputs["From Min"].default_value = 0.70
    metal.inputs["From Max"].default_value = 0.82
    metal.inputs["To Min"].default_value = 0.92
    metal.inputs["To Max"].default_value = 0.15
    nt.links.new(noise.outputs["Fac"], metal.inputs["Value"])
    nt.links.new(metal.outputs["Result"], bsdf.inputs["Metallic"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["From Min"].default_value = 0.70
    rough.inputs["From Max"].default_value = 0.82
    rough.inputs["To Min"].default_value = 0.30
    rough.inputs["To Max"].default_value = 0.70
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def ink_material(name):
    """Blackened wax filling the engraving: near-black, satin."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.012, 0.011, 0.010, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Metallic"].default_value = 0.2
    return mat


def sundial_materials():
    return (stone_material("DialGranite"), bronze_material("DialBronze"), ink_material("DialInk"))


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
    """Shells by what they are: stone blocks, the dial plate, the gnomon, ink pieces."""
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    out = {"stone": [], "bead": [], "plate": [], "gnomon": [], "ink": [], "other": []}
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        rec = {"g": g, "pts": pts, "lo": lo, "hi": hi, "ext": hi - lo,
               "c": sum(pts, Vector()) / len(pts)}
        m = mats.get(g[0], -1)
        if len(g) < 4:
            out["other"].append(rec)
        elif m == STONE_IDX:
            # A bead is the only stone shell shallower than the 35 mm cap.
            out["bead" if rec["ext"].z < BEAD_H + 0.002 else "stone"].append(rec)
        elif m == BRONZE_IDX:
            out["plate" if max(rec["ext"].x, rec["ext"].y) > 0.25 else "gnomon"].append(rec)
        elif m == INK_IDX:
            out["ink"].append(rec)
        else:
            out["other"].append(rec)
    return out


def principal_bearing(pts):
    """Bearing of a shell's long axis in plan, from north, folded into (-90, 90]."""
    cx = sum(p.x for p in pts) / len(pts)
    cy = sum(p.y for p in pts) / len(pts)
    sxx = sum((p.x - cx) ** 2 for p in pts)
    syy = sum((p.y - cy) ** 2 for p in pts)
    sxy = sum((p.x - cx) * (p.y - cy) for p in pts)
    theta = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    deg = math.degrees(math.atan2(math.cos(theta), math.sin(theta)))
    while deg > 90.0:
        deg -= 180.0
    while deg <= -90.0:
        deg += 180.0
    return deg


def sundial_audit(me):
    parts = classify(me)
    out = {k: len(v) for k, v in parts.items()}
    plate = parts["plate"][0] if len(parts["plate"]) == 1 else None
    gnomon = parts["gnomon"][0] if len(parts["gnomon"]) == 1 else None

    plate_top = -99.0
    centre = Vector((0.0, 0.0, 0.0))
    if plate:
        centre = Vector((plate["c"].x, plate["c"].y, 0.0))
        field = [p.z for p in plate["pts"] if math.hypot(p.x - centre.x, p.y - centre.y) < 0.17]
        plate_top = max(field) if field else -99.0
        out["plate_dia"] = max(plate["ext"].x, plate["ext"].y)
    out["plate_top"] = plate_top

    # Style edge: the gnomon's faces that look up and south, whose normals are
    # in the meridian plane. Their tilt from the horizontal is the style angle.
    me.calc_loop_triangles()
    gset = set(gnomon["g"]) if gnomon else set()
    faces = [p for p in me.polygons if gnomon and set(p.vertices) <= gset
             and abs(p.normal.x) < 1e-3 and p.normal.z > 0.05 and p.normal.y < -0.05]
    out["style_faces"] = len(faces)
    angle, foot = -99.0, 99.0
    if faces:
        tot = sum(face_area(me, p) for p in faces)
        angle = sum(math.degrees(math.atan2(-p.normal.y, p.normal.z)) * face_area(me, p)
                    for p in faces) / tot
        foot = sum((p.center.z + p.normal.y * (p.center.y - centre.y) / p.normal.z) * face_area(me, p)
                   for p in faces) / tot
    out["style_deg"] = angle
    out["foot_err"] = abs(foot - plate_top)
    out["gnomon_x"] = gnomon["c"].x if gnomon else 99.0
    out["gnomon_bite"] = plate_top - gnomon["lo"].z if gnomon else -99.0
    out["gnomon_h"] = gnomon["hi"].z - plate_top if gnomon else -99.0

    # Ink: the ring, the noon arrow (the piece on the meridian), the hour bars
    # and the half-hour ticks (told apart by how far out they sit).
    ink = list(parts["ink"])
    ring = [r for r in ink if max(r["ext"].x, r["ext"].y) > 0.2]
    rest = [r for r in ink if r not in ring]
    north = [r for r in rest if r["c"].y > centre.y]
    noon = min(north, key=lambda r: abs(r["c"].x - centre.x), default=None)
    pieces = [r for r in rest if r is not noon]
    rad = {id(r): math.hypot(r["c"].x - centre.x, r["c"].y - centre.y) for r in pieces}
    numerals = [r for r in pieces if NUM_BAND[0] < rad[id(r)] < NUM_BAND[1]]
    bars = [r for r in pieces if rad[id(r)] < BAR_TICK_SPLIT_R]
    ticks = [r for r in pieces if r not in bars and r not in numerals]
    out["ring"], out["noon"], out["bars"], out["ticks"] = len(ring), 1 if noon else 0, len(bars), len(ticks)
    out["numeral_strokes"] = len(numerals)
    out["noon_off"] = abs(noon["c"].x - gnomon["c"].x) if noon and gnomon else 99.0

    def bearings(group):
        got = sorted(math.degrees(math.atan2(r["c"].x - centre.x, r["c"].y - centre.y))
                     for r in group)
        radial = max((abs((principal_bearing(r["pts"])
                           - math.degrees(math.atan2(r["c"].x - centre.x, r["c"].y - centre.y))
                           + 90.0) % 180.0 - 90.0) for r in group), default=0.0)
        return got, radial

    err, radial = 0.0, 0.0
    for group, hours in ((bars, HOURS), (ticks, TICKS)):
        got, rad = bearings(group)
        want = sorted(math.degrees(hour_bearing(h)) for h in hours)
        radial = max(radial, rad)
        if len(got) != len(want):
            err = 99.0
        else:
            err = max(err, max((abs(a - b) for a, b in zip(got, want)), default=0.0))
    out["bearing_err"] = err
    out["radial_err"] = radial
    lines = ring + rest
    out["line_proud"] = (min((r["hi"].z - plate_top for r in lines), default=-99.0),
                         max((r["hi"].z - plate_top for r in lines), default=99.0))
    out["line_seat"] = (min((plate_top - r["lo"].z for r in lines), default=-99.0),
                        max((plate_top - r["lo"].z for r in lines), default=99.0))

    # Column: tallest stone shell. Plumb is the plan centroid of its bottom ring
    # against its top ring; its height is the real-world figure.
    column = max(parts["stone"], key=lambda r: r["ext"].z, default=None)
    out["column_h"] = column["ext"].z if column else -99.0
    out["plumb"] = 99.0
    if column:
        zlo, zhi = column["lo"].z, column["hi"].z
        low = [p for p in column["pts"] if p.z < zlo + 0.02]
        top = [p for p in column["pts"] if p.z > zhi - 0.02]
        a = Vector((sum(p.x for p in low) / len(low), sum(p.y for p in low) / len(low)))
        b = Vector((sum(p.x for p in top) / len(top), sum(p.y for p in top) / len(top)))
        out["plumb"] = (a - b).length
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
    """Compound collider: one hull per stone block, the plate and the gnomon.

    The ink is left out; it is a millimetre of relief on a surface the plate's
    hull already covers. So are the two column beads: 17 mm of moulding
    round a shaft whose hull is already there. The plate is hulled over every fourth segment.
    """
    me = obj.data
    parts = classify(me)
    groups = [r["pts"] for r in parts["stone"] + parts["gnomon"]]
    for r in parts["plate"]:
        step = 2.0 * math.pi / 16.0
        keep = []
        for p in r["pts"]:
            q = math.atan2(p.y, p.x) / step
            if math.hypot(p.x, p.y) < 1e-9 or abs(q - round(q)) < 1e-6:
                keep.append(p)
        groups.append(keep)
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
    img = bpy.data.images.new("DialNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = STONE_IDX
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


def check(skip_decimate, lift_z=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_sundial_mesh("SundialLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_sundial_mesh("SundialHigh", hi=True, **hi_flags)
    mats = sundial_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("sundial mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[STONE_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "SundialLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "SundialLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(low, "SundialCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_sundial_{os.getpid()}.glb")
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
    sa = sundial_audit(low.data)

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
    print(f"measured parts stone={sa['stone']} bead={sa['bead']} plate={sa['plate']} "
          f"gnomon={sa['gnomon']} ink={sa['ink']} other={sa['other']} ring={sa['ring']} "
          f"noon={sa['noon']} bars={sa['bars']} ticks={sa['ticks']} "
          f"numeral_strokes={sa['numeral_strokes']} style_faces={sa['style_faces']}")
    print(f"measured style={sa['style_deg']:.4f}deg foot_err={sa['foot_err']:.5f} "
          f"bearing_err={sa['bearing_err']:.5f}deg radial_err={sa['radial_err']:.4f}deg")
    print(f"measured bite={sa['gnomon_bite']:.5f} line_proud=({sa['line_proud'][0]:.5f},"
          f"{sa['line_proud'][1]:.5f}) line_seat=({sa['line_seat'][0]:.5f},"
          f"{sa['line_seat'][1]:.5f}) noon_off={sa['noon_off']:.5f}")
    print(f"measured plumb={sa['plumb']:.5f} column_h={sa['column_h']:.4f} "
          f"plate_dia={sa.get('plate_dia', -99.0):.4f} gnomon_h={sa['gnomon_h']:.4f} "
          f"plate_top={sa['plate_top']:.5f}")

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
    n_num = numeral_stroke_count()
    if (sa["stone"] != 6 or sa["bead"] != 2 or sa["plate"] != 1 or sa["gnomon"] != 1
            or sa["ring"] != 2 or sa["noon"] != 1 or sa["bars"] != len(HOURS)
            or sa["ticks"] != len(TICKS) or sa["numeral_strokes"] != n_num):
        return (fail(f"parts: stone {sa['stone']}/6 bead {sa['bead']}/2 plate {sa['plate']}/1 "
                     f"gnomon {sa['gnomon']}/1 ring {sa['ring']}/2 noon {sa['noon']}/1 "
                     f"bars {sa['bars']}/{len(HOURS)} ticks {sa['ticks']}/{len(TICKS)} "
                     f"numeral strokes {sa['numeral_strokes']}/{n_num}", 3),) + nothing
    if abs(sa["style_deg"] - LATITUDE) > STYLE_TOL_DEG:
        return (fail(f"style edge {sa['style_deg']:.3f} deg off the plate, latitude is "
                     f"{LATITUDE} deg (--wrong-latitude is the designed fail)", 17),) + nothing
    if sa["bearing_err"] > BEARING_TOL_DEG or sa["radial_err"] > RADIAL_TOL_DEG:
        return (fail(f"hour lines off tan(H) = sin(lat) tan(15 h) by {sa['bearing_err']:.3f} deg "
                     f"(radial {sa['radial_err']:.3f} deg) (--linear-hours is the designed fail)",
                     17),) + nothing
    if not (BITE_MIN <= sa["gnomon_bite"] <= BITE_MAX):
        return (fail(f"gnomon bite {sa['gnomon_bite']:.5f} outside [{BITE_MIN}, {BITE_MAX}] "
                     "(--float-gnomon is the designed fail)", 18),) + nothing
    if sa["foot_err"] > FOOT_TOL:
        return (fail(f"style edge meets the plate {sa['foot_err']:.5f} m from the dial centre "
                     f"(> {FOOT_TOL})", 18),) + nothing
    if (not (PROUD_MIN <= sa["line_proud"][0] and sa["line_proud"][1] <= PROUD_MAX)
            or not (INK_SEAT_MIN <= sa["line_seat"][0] and sa["line_seat"][1] <= INK_SEAT_MAX)):
        return (fail(f"ink lines proud {sa['line_proud']} (band [{PROUD_MIN}, {PROUD_MAX}]), "
                     f"seated {sa['line_seat']} (band [{INK_SEAT_MIN}, {INK_SEAT_MAX}]) "
                     "(--float-lines is the designed fail)", 18),) + nothing
    if sa["noon_off"] > MERIDIAN_TOL:
        return (fail(f"noon line {sa['noon_off']:.5f} m off the gnomon's meridian "
                     f"(> {MERIDIAN_TOL}) (--shift-noon is the designed fail)", 19),) + nothing
    if sa["plumb"] > PLUMB_TOL:
        return (fail(f"column top {sa['plumb']:.5f} m off plumb over its foot "
                     f"(> {PLUMB_TOL}) (--lean-pedestal is the designed fail)", 19),) + nothing
    if (abs(sa["column_h"] - COLUMN_H) > COLUMN_H_TOL
            or abs(sa["plate_dia"] - PLATE_DIA) > PLATE_DIA_TOL
            or abs(sa["gnomon_h"] - GNOMON_H) > GNOMON_H_TOL):
        return (fail(f"real-world size: column {sa['column_h']:.4f} (want {COLUMN_H}), plate "
                     f"{sa['plate_dia']:.4f} (want {PLATE_DIA}), gnomon {sa['gnomon_h']:.4f} "
                     f"(want {GNOMON_H})", 19),) + nothing
    return 0, low, high, mats, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    bump = nt.nodes.get("StoneBump")
    target = bump.inputs["Normal"] if bump else nt.nodes["Principled BSDF"].inputs["Normal"]
    nt.links.new(nrm.outputs["Normal"], target)


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats[STONE_IDX], tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only. The gnomon lies in the
    # meridian plane, so the yaw turns its face toward the camera; at -28
    # degrees it was seen 62 degrees off its normal and read as a needle.
    low.rotation_euler.z = math.radians(-58.0)

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

    def light(name, kind, loc, energy, size, col, rot=(0, 0, 0)):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        if kind == "AREA":
            ld.size = size
        else:
            ld.shadow_soft_size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", "AREA", (-2.2, -2.4, 3.2), 300.0, 0.6, (1.0, 0.95, 0.88), (42, 0, -42))
    light("Fill", "AREA", (3.2, -2.6, 1.4), 60.0, 5.0, (0.74, 0.84, 1.0), (70, 0, 50))
    light("Rim", "AREA", (-1.6, 2.6, 2.2), 220.0, 3.0, (0.62, 0.78, 1.0), (-55, 0, 200))
    ld = bpy.data.lights.new("Wedge", "SPOT")
    ld.energy, ld.color = 220.0, (1.0, 0.66, 0.34)
    ld.spot_size, ld.spot_blend, ld.shadow_soft_size = math.radians(50.0), 1.0, 0.3
    wedge = bpy.data.objects.new("Wedge", ld)
    wedge.location = (0.5, 1.6, 1.9)
    wedge.rotation_euler = (Vector((0.2, 0.5, 0.0)) - wedge.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.collection.objects.link(wedge)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 60.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -3.1, 2.9)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.43)
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

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low], stage=[floor, wall])
    if fcode:
        return fcode
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
    p.add_argument("--wrong-latitude", action="store_true")
    p.add_argument("--linear-hours", action="store_true")
    p.add_argument("--float-gnomon", action="store_true")
    p.add_argument("--float-lines", action="store_true")
    p.add_argument("--lean-pedestal", action="store_true")
    p.add_argument("--shift-noon", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        wrong_latitude=args.wrong_latitude,
        linear_hours=args.linear_hours,
        lift_gnomon=args.float_gnomon,
        lift_lines=args.float_lines,
        lean_pedestal=args.lean_pedestal,
        shift_noon=args.shift_noon,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("sundial OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
