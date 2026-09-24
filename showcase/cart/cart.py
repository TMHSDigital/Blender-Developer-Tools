"""Game-ready two-wheel handcart — a showcase piece, not an example.

Asserts budget conformance of a procedural handcart (planked bed on two
rails that run on as shafts, board walls with iron corner straps, prop
legs, spoked wheels on long naves, iron tyres, axle and washers) after
composing shipped pipeline pieces: bmesh construction, UVs, two
materials, high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier flag breaks one
stage so a named budget fails and the piece exits that budget's code:
``--skip-decimate`` (LOD ratio, 9), ``--flush-tyre`` (coplanar
cross-shell pairs, 15), ``--lift-z`` (AABB grounded, 16),
``--float-wheel`` and ``--short-props`` (named supports, 16),
``--wide-seams`` (wall board seams, 17), ``--sink-tyre`` (tyre seat
band, 18), ``--lift-bed`` (one connected assembly, 18), ``--skew-wheel``
(wheel mirror, 19), ``--sharp-bar`` (edge treatment, 20), ``--low-bake``
(bake texel density, 21). The wheel,
leg and bed moves stay inside ``BBOX_TOL`` so the AABB gate cannot steal
the failure.

Seeded, not random: per-board tone uses ``random.Random(TONE_SEED)``.
Construction is closed-form. DECIMATE COLLAPSE triangle counts are not
byte-identical across Blender versions — the LOD gate is a ratio band,
not an exact count.

    blender --background --python cart.py --
    blender --background --python cart.py -- --skip-decimate
    blender --background --python cart.py -- --flush-tyre
    blender --background --python cart.py -- --output cart.png
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
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

RIM_OUTER = 0.312
# Felloe: flat-tread box section, not a round tube — round torus rims read
# as bicycle wheels. RIM_RADIAL is the half-depth: a 40 mm felloe. The
# first build's 24 mm read as a bent strip at hero size.
RIM_RADIAL = 0.020
RIM_MAJOR = RIM_OUTER - RIM_RADIAL
RIM_W = 0.036
TYRE_T = 0.008
TYRE_W = 0.040
# Felloe outer radius is the *host* surface the tyre is hooped onto. The
# tyre's inner radius is derived from it minus a named interference, never
# set equal to it: r_in == r_out puts the tyre's inner cylinder and the
# felloe's tread on one plane for every segment, which is a guaranteed
# z-fight (it measured 32 coplanar cross-shell pairs, 16 per wheel).
TYRE_SEAT = 0.004
TYRE_SEAT_MIN = 0.0030
TYRE_SEAT_MAX = 0.0055
WHEEL_R = RIM_OUTER + TYRE_T
WHEEL_SEGMENTS = 24
TRACK = 0.68
AXLE_R = 0.020
# The axle runs past each washer, so a washer pushed out by --skew-wheel
# still stops short of the axle's end cap instead of landing on its plane.
AXLE_PROUD = 0.016
# A nave is a long barrel, not a disc. The first build's 46 mm hub read as
# a toy wheel in every view; 130 mm with an iron band at each end is a
# cartwheel's proportion.
NAVE_L = 0.130
NAVE_R_END = 0.044
NAVE_R_MID = 0.058
NAVE_BAND_ZONE = 0.028
NAVE_BAND_W = 0.016
NAVE_BAND_T = 0.006
NAVE_BAND_BITE = 0.002
NAVE_SEGS = 12
WASHER_R = 0.032
WASHER_BITE = 0.003
WASHER_T = 0.009
N_SPOKES = 10
SPOKE_W = 0.022
SPOKE_D = 0.018
SPOKE_ROOT = 0.020
SPOKE_TENON = 0.014

# Chassis, stacked from the axle up. Each member bites the one below it by
# a named depth, so nothing rests on a tangent line or floats.
BED_L = 0.92
BED_W = 0.50
BED_CX = 0.06
AXLE_X = BED_CX - 0.22
AXLE_BITE = 0.006
BOLSTER_H = 0.044
BOLSTER_X = 0.060
BOLSTER_SPAN = 0.52
RAIL_Y = 0.17
RAIL_W = 0.040
RAIL_H = 0.050
RAIL_BITE = 0.006
RAIL_BACK = 0.03
FLOOR_T = 0.030
N_FLOOR = 9
FLOOR_GAP = 0.004
FLOOR_BITE = 0.004
# Walls stand on the floor, inset from its edge. The first build hung them
# outside the planks at mid-thickness, which left every slat end poking out
# under the front board as a row of teeth; flush with the plank ends they
# would share the end grain's plane.
WALL_H = 0.18
WALL_T = 0.028
WALL_SEAT = 0.006
WALL_INSET = 0.004
WALL_BOARDS = 2
WALL_SEAM = 0.003
WALL_SEAM_MIN = 0.0015
WALL_SEAM_MAX = 0.005
WIDE_SEAM = 0.010
# End boards sit between the side walls: recessed, seated deeper, split at
# a different height and topped lower, so no face of an end board lands on
# a plane of a side board.
END_INSET = 0.003
END_BITE = 0.012
END_SEAT = 0.009
END_SPLIT = 0.46
END_DROP = 0.008
TAILGATE_H = 0.100
SHAFT_L = 0.58
HANDLE_R = 0.017
HANDLE_BACK = 0.07
HANDLE_PROUD = 0.012
# The first build hovered its shaft tips 0.30 m off the floor with the
# centre of mass ahead of the axle: it would tip. Two prop legs under the
# rails stand it level. Thinner than the rail, so their faces never share
# its planes.
LEG_T = 0.034
LEG_BACK = 0.09
LEG_BITE = 0.024
SHORT_PROP_Z = 0.003
# Iron corner straps: one L-section shell per corner, bitten into both
# faces of the side wall it is nailed to.
STRAP_LEG = 0.050
STRAP_T = 0.004
STRAP_BITE = 0.0015
STRAP_MARGIN = 0.012
IRON_BEVEL = 0.0012
BEVEL_MIN_ANGLE = math.radians(50.0)
PLANK_TONE_JITTER = 0.28
TONE_SEED = 31
WOOD_GRAIN_SCALE = 30.0

BBOX_TOL = 0.01
# Rails run on as shafts past the bed (X); axle ends past the washers (Y);
# the tyre tops (Z). Re-declared for the rebuild: 1.539 x 0.749 before.
OUTER_SIZE = (1.580, 0.842, 0.640)
# Re-fitted for the rebuild (2856 -> 5284: naves, bands, washers, straps,
# legs, boards). Centred on the measurement, 250 wide against the old 200.
BASE_TRIS_MIN = 5160
BASE_TRIS_MAX = 5410
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
GAP_MAX = 0.008
LIFT_Z = 0.05
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 360
# One UV cell per face: at 256 px each of the ~2900 faces got about 4 px,
# and the render's bilinear lookup read neighbouring cells' normals as a
# black hexagon and sandpaper speckle on the side boards (tavern-stool's
# defect). 1024 px gives every cell 17 px against a 12 px floor.
BAKE_RES = 1024
LOW_BAKE_RES = 256
TEXEL_MIN = 12.0
# The cage only has to cover the chamfer difference between the 3-segment
# high and the 1-segment low (under 2 mm). At 0.08 it reached past the
# 74 mm between side wall and felloe, so rays from the wall hit the high
# wheel and baked its rim onto the board as a black staircase.
CAGE_EXTRUSION = 0.01
METAL_FACES_MIN = 800
WOOD_FACES_MIN = 1200

# Z-fighting: two separate bodies landing on one plane. Cross-shell, with
# hay-bale's constants (copied, not imported).
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
ZFIGHT_PAIRS_MAX = 0
# Named supports: two tyres and two prop legs. The AABB zmin is grounded by
# whichever of them is lowest, so each carries its own floor contact.
SUPPORT_ZMIN_EPS = 1e-4
N_LEGS = 2
# Mirrored members: the two wheels are the same part reflected in Y.
WHEEL_MIRROR_EPS = 5e-5
# Every member is joined to the rest: the BVH-overlap graph of the shells
# is one component. A bed resting a hair above its rails passes every
# per-part budget and is still a floating box.
CONTACT_COMPONENTS = 1
LIFT_BED = FLOOR_BITE + 0.003
# Edge treatment: every edge is chamfered, so a manifold edge still within
# RIGHT_ANGLE_TOL of 90 degrees is one a bevel pass skipped.
RIGHT_ANGLE_TOL = math.radians(5.0)
RIGHT_ANGLE_MAX = 0
# Falsifier magnitudes, each sized to trip its own budget and nothing
# earlier: the wheel moves stay inside BBOX_TOL so the AABB gate cannot
# steal the failure.
SINK_TYRE_SEAT = 0.009
FLOAT_WHEEL_Z = 0.003
SKEW_WHEEL_Y = 0.006

WOOD_IDX = 0
METAL_IDX = 1


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def evaluated_triangle_count(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        eval_mesh.calc_loop_triangles()
        return len(eval_mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()


def deselect_all():
    for ob in list(bpy.context.view_layer.objects):
        if ob is None:
            continue
        ob.select_set(False)


def _faces_of(verts, mat_idx):
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx


def add_box(bm, loc, scale, mat_idx, euler=(0.0, 0.0, 0.0)):
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = geo["verts"]
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        p = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
        v.co = rot @ p + origin
    _faces_of(verts, mat_idx)
    return verts


def add_span(bm, lo, hi, mat_idx):
    """Axis-aligned box from its min corner to its max corner."""
    lo = Vector(lo)
    hi = Vector(hi)
    return add_box(bm, (lo + hi) * 0.5, hi - lo, mat_idx)


def add_oriented_box(bm, a, b, scale_xy, mat_idx):
    """Box whose long axis runs from station ``a`` to station ``b``.

    For a direction in the XZ plane the rotation is about Y alone, so the
    box's local Y stays world Y — a spoke's thin side stays along the axle.
    """
    a = Vector(a)
    b = Vector(b)
    delta = b - a
    length = delta.length
    if length < 1e-8:
        return []
    quat = Vector((0.0, 0.0, 1.0)).rotation_difference(delta.normalized())
    eul = quat.to_euler("XYZ")
    return add_box(
        bm, (a + b) * 0.5, (scale_xy[0], scale_xy[1], length), mat_idx,
        euler=(eul.x, eul.y, eul.z),
    )


def add_cyl(bm, loc, radius, depth, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=True,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=depth,
    )
    verts = geo["verts"]
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    _faces_of(verts, mat_idx)
    return verts


def add_ring(bm, loc, r_in, r_out, width, segments, mat_idx):
    """Flat-sided ring with a box cross-section, its axis along world Y.

    Manifold: outer tread, inner surface, and two side annuli, all quads.
    Built in the XZ plane with u measured from +X toward +Z, so a segment
    count divisible by four puts a vertex at the very bottom.
    """
    hw = width / 2.0
    ox, oy, oz = loc
    rings = []
    for i in range(segments):
        u = i * (2.0 * math.pi / segments)
        cu = math.cos(u)
        su = math.sin(u)
        rings.append(
            [
                bm.verts.new((ox + r_in * cu, oy - hw, oz + r_in * su)),
                bm.verts.new((ox + r_out * cu, oy - hw, oz + r_out * su)),
                bm.verts.new((ox + r_out * cu, oy + hw, oz + r_out * su)),
                bm.verts.new((ox + r_in * cu, oy + hw, oz + r_in * su)),
            ]
        )
    for i in range(segments):
        a = rings[i]
        b = rings[(i + 1) % segments]
        for quad in (
            (a[1], b[1], b[2], a[2]),
            (a[3], b[3], b[0], a[0]),
            (a[2], b[2], b[3], a[3]),
            (a[0], b[0], b[1], a[1]),
        ):
            bm.faces.new(quad).material_index = mat_idx
    return [v for ring in rings for v in ring]


def add_lathe_y(bm, loc, profile, segments, mat_idx):
    """Closed solid of revolution about world Y from ``(dy, radius)`` pairs.

    Capped at both ends with an n-gon that ``finish_caps`` triangulates
    after the chamfer pass: a triangle-fan cap, chamfered 5 mm at its rim,
    folded its centre out through the cap as non-manifold slivers.
    """
    ox, oy, oz = loc
    rings = []
    for dy, r in profile:
        ring = []
        for i in range(segments):
            u = 2.0 * math.pi * i / segments
            ring.append(bm.verts.new(
                (ox + r * math.cos(u), oy + dy, oz + r * math.sin(u))))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for k in range(segments):
            kn = (k + 1) % segments
            bm.faces.new((a[k], a[kn], b[kn], b[k])).material_index = mat_idx
    bm.faces.new(list(reversed(rings[0]))).material_index = mat_idx
    bm.faces.new(rings[-1]).material_index = mat_idx
    return [v for ring in rings for v in ring]


def add_l_strap(bm, corner, sx, sy, z0, z1, mat_idx):
    """One L-section iron strap wrapped round a vertical box corner.

    ``corner`` is the wood's outer corner in plan; ``sx``/``sy`` point out
    of the box. Both legs bite ``STRAP_BITE`` into the wood faces. One
    shell: two overlapping boxes would chamfer a strip onto the same line
    twice. Each cap is one L n-gon until ``finish_caps`` triangulates it
    after the chamfer pass; caps pre-split on the inner-corner diagonal
    left 24 non-manifold edges per strap once the reflex corner was
    chamfered.
    """
    xc, yc = corner
    b, t, leg = STRAP_BITE, STRAP_T, STRAP_LEG
    xi, yi = xc - sx * b, yc - sy * b
    xo, yo = xc + sx * (t - b), yc + sy * (t - b)
    plan = [
        (xi, yi),
        (xi - sx * leg, yi),
        (xi - sx * leg, yo),
        (xo, yo),
        (xo, yi - sy * leg),
        (xi, yi - sy * leg),
    ]
    lo = [bm.verts.new((x, y, z0)) for x, y in plan]
    hi = [bm.verts.new((x, y, z1)) for x, y in plan]
    n = len(plan)
    for k in range(n):
        kn = (k + 1) % n
        bm.faces.new((lo[k], lo[kn], hi[kn], hi[k])).material_index = mat_idx
    bm.faces.new(list(reversed(lo))).material_index = mat_idx
    bm.faces.new(hi).material_index = mat_idx
    return lo + hi


def finish_caps(bm):
    """Triangulate every face with more than four corners.

    Lathe and strap caps are built as n-gons so the chamfer pass has clean
    rims to work on; the shipped mesh carries no n-gon.
    """
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        bmesh.ops.triangulate(
            bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY",
        )


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
        ax = abs(nrm.x)
        ay = abs(nrm.y)
        az = abs(nrm.z)
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


def chassis_levels():
    """Z of every chassis level, stacked from the axle up by named bites."""
    axle_z = WHEEL_R
    bolster_z0 = axle_z + AXLE_R - AXLE_BITE
    bolster_z1 = bolster_z0 + BOLSTER_H
    rail_z0 = bolster_z1 - RAIL_BITE
    rail_z1 = rail_z0 + RAIL_H
    floor_z0 = rail_z1 - FLOOR_BITE
    floor_z1 = floor_z0 + FLOOR_T
    wall_z0 = floor_z1 - WALL_SEAT
    return {
        "axle": axle_z, "bolster0": bolster_z0, "bolster1": bolster_z1,
        "rail0": rail_z0, "rail1": rail_z1, "floor0": floor_z0,
        "floor1": floor_z1, "wall0": wall_z0, "wall1": wall_z0 + WALL_H,
    }


def board_heights(z0, total, n, seam, split=None):
    """(bottom, top) of ``n`` boards stacked in ``total`` with ``seam`` gaps."""
    if n == 1:
        return [(z0, z0 + total)]
    usable = total - (n - 1) * seam
    if split is not None and n == 2:
        hs = [usable * split, usable * (1.0 - split)]
    else:
        hs = [usable / n] * n
    out = []
    z = z0
    for h in hs:
        out.append((z, z + h))
        z += h + seam
    return out


def add_wheel(bm, loc, wood, metal):
    ox, oy, oz = loc
    wood.extend(add_ring(
        bm, loc, RIM_MAJOR - RIM_RADIAL, RIM_OUTER, RIM_W, WHEEL_SEGMENTS, WOOD_IDX,
    ))
    # Hooped, not pasted on: inner radius is RIM_OUTER - TYRE_SEAT so the
    # band bites into the felloe, and the tread still lands at WHEEL_R so
    # the tyre stays the ground contact.
    metal.extend(add_ring(
        bm, loc, RIM_OUTER - TYRE_SEAT, WHEEL_R, TYRE_W, WHEEL_SEGMENTS, METAL_IDX,
    ))
    zone = NAVE_BAND_ZONE
    half = NAVE_L / 2.0
    wood.extend(add_lathe_y(
        bm, loc,
        [(-half, NAVE_R_END), (-half + zone, NAVE_R_END), (0.0, NAVE_R_MID),
         (half - zone, NAVE_R_END), (half, NAVE_R_END)],
        NAVE_SEGS, WOOD_IDX,
    ))
    for s in (-1.0, 1.0):
        metal.extend(add_ring(
            bm, (ox, oy + s * (half - zone / 2.0), oz),
            NAVE_R_END - NAVE_BAND_BITE, NAVE_R_END + NAVE_BAND_T,
            NAVE_BAND_W, NAVE_SEGS, METAL_IDX,
        ))
    # Outboard washer: bites the nave's end and the axle.
    out = 1.0 if oy > 0.0 else -1.0
    w_mid = oy + out * (half - WASHER_BITE + WASHER_T / 2.0)
    metal.extend(add_ring(
        bm, (ox, w_mid, oz), AXLE_R - 0.002, WASHER_R, WASHER_T, NAVE_SEGS, METAL_IDX,
    ))
    # Spokes root inside the nave and tenon into the felloe.
    r0 = NAVE_R_MID - SPOKE_ROOT
    r1 = RIM_MAJOR - RIM_RADIAL + SPOKE_TENON
    for i in range(N_SPOKES):
        a = (i + 0.5) * (2.0 * math.pi / N_SPOKES)
        d = Vector((math.cos(a), 0.0, math.sin(a)))
        c = Vector(loc)
        wood.extend(add_oriented_box(bm, c + d * r0, c + d * r1,
                                     (SPOKE_W, SPOKE_D), WOOD_IDX))


def build_cart_mesh(name, bevel_offset, bevel_segments, sharp_bar=False,
                    wide_seams=False, short_props=False):
    lv = chassis_levels()
    bed_x0 = BED_CX - BED_L / 2.0
    bed_x1 = BED_CX + BED_L / 2.0
    bm = bmesh.new()
    try:
        wood = []
        metal = []
        axle_z = lv["axle"]
        for s in (1.0, -1.0):
            add_wheel(bm, (AXLE_X, s * TRACK / 2.0, axle_z), wood, metal)
        axle_len = TRACK + NAVE_L + 2.0 * AXLE_PROUD
        metal.extend(add_cyl(
            bm, (AXLE_X, 0.0, axle_z), AXLE_R, axle_len, 12, METAL_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        ))

        # Bolster notched onto the axle; rails on the bolster.
        wood.extend(add_span(
            bm,
            (AXLE_X - BOLSTER_X / 2.0, -BOLSTER_SPAN / 2.0, lv["bolster0"]),
            (AXLE_X + BOLSTER_X / 2.0, BOLSTER_SPAN / 2.0, lv["bolster1"]),
            WOOD_IDX,
        ))
        tip_x = bed_x1 + SHAFT_L
        for s in (-1.0, 1.0):
            wood.extend(add_span(
                bm,
                (bed_x0 + RAIL_BACK, s * RAIL_Y - RAIL_W / 2.0, lv["rail0"]),
                (tip_x, s * RAIL_Y + RAIL_W / 2.0, lv["rail1"]),
                WOOD_IDX,
            ))
            # Prop leg tenoned into the rail's underside.
            leg_x = bed_x1 - LEG_BACK
            foot_z = SHORT_PROP_Z if short_props else 0.0
            wood.extend(add_span(
                bm,
                (leg_x - LEG_T / 2.0, s * RAIL_Y - LEG_T / 2.0, foot_z),
                (leg_x + LEG_T / 2.0, s * RAIL_Y + LEG_T / 2.0,
                 lv["rail0"] + LEG_BITE),
                WOOD_IDX,
            ))
        # Pulling bar through both shaft tips.
        bar_half = RAIL_Y + RAIL_W / 2.0 + HANDLE_PROUD
        bar = set(add_cyl(
            bm, (tip_x - HANDLE_BACK, 0.0, 0.5 * (lv["rail0"] + lv["rail1"])),
            HANDLE_R, 2.0 * bar_half, 12, WOOD_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        ))
        wood.extend(bar)

        # Floor: planks across the rails.
        w = (BED_L - (N_FLOOR - 1) * FLOOR_GAP) / N_FLOOR
        for i in range(N_FLOOR):
            x0 = bed_x0 + i * (w + FLOOR_GAP)
            wood.extend(add_span(
                bm, (x0, -BED_W / 2.0, lv["floor0"]),
                (x0 + w, BED_W / 2.0, lv["floor1"]), WOOD_IDX,
            ))

        # Side walls: stacked boards standing on the floor.
        seam = WIDE_SEAM if wide_seams else WALL_SEAM
        yo = BED_W / 2.0 - WALL_INSET
        xa = bed_x0 + WALL_INSET
        xb = bed_x1 - WALL_INSET
        for s in (-1.0, 1.0):
            for z0, z1 in board_heights(lv["wall0"], WALL_H, WALL_BOARDS, seam):
                ylo, yhi = sorted((s * yo, s * (yo - WALL_T)))
                wood.extend(add_span(bm, (xa, ylo, z0), (xb, yhi, z1), WOOD_IDX))
        # End boards between the side walls, biting into them.
        e_half = yo - WALL_T + END_BITE
        e_z0 = lv["floor1"] - END_SEAT
        front = board_heights(
            e_z0, lv["wall1"] - END_DROP - e_z0, WALL_BOARDS, seam, split=END_SPLIT,
        )
        tail = board_heights(e_z0, TAILGATE_H, 1, seam)
        for boards, xs in (
            (front, (xb - END_INSET - WALL_T, xb - END_INSET)),
            (tail, (xa + END_INSET, xa + END_INSET + WALL_T)),
        ):
            for z0, z1 in boards:
                wood.extend(add_span(
                    bm, (xs[0], -e_half, z0), (xs[1], e_half, z1), WOOD_IDX,
                ))

        # Iron corner straps on the side walls' corners.
        sz0 = lv["floor1"] + STRAP_MARGIN
        sz1 = lv["wall1"] - STRAP_MARGIN
        for cx, sx in ((xb, 1.0), (xa, -1.0)):
            for sy in (-1.0, 1.0):
                metal.extend(add_l_strap(bm, (cx, sy * yo), sx, sy, sz0, sz1, METAL_IDX))

        bm.edges.index_update()

        def sharp(edge, idx):
            if len(edge.link_faces) != 2:
                return False
            # --sharp-bar leaves the pull bar's rims square: 48 triangles
            # short, well inside the triangle band, so only the edge
            # budget can see it. Skipping the whole iron pass dropped
            # 1200 and tripped the triangle floor instead.
            if sharp_bar and all(v in bar for v in edge.verts):
                return False
            if any(f.material_index != idx for f in edge.link_faces):
                return False
            return edge.calc_face_angle(0.0) > BEVEL_MIN_ANGLE

        if bevel_offset > 0.0:
            edges = sorted(
                (e for e in bm.edges if sharp(e, WOOD_IDX)), key=lambda e: e.index
            )
            bmesh.ops.bevel(
                bm, geom=edges, offset=bevel_offset, segments=bevel_segments,
                profile=0.5, affect="EDGES", clamp_overlap=True, material=WOOD_IDX,
            )
            bm.edges.index_update()
            edges = sorted(
                (e for e in bm.edges if sharp(e, METAL_IDX)), key=lambda e: e.index
            )
            bmesh.ops.bevel(
                bm, geom=edges, offset=IRON_BEVEL, segments=1, profile=0.5,
                affect="EDGES", clamp_overlap=True, material=METAL_IDX,
            )
        finish_caps(bm)

        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        zmin = min(zs)
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy
            v.co.z -= zmin

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # Smooth across the felloe's, nave's and axle's facets; hard at every
        # chamfer and material boundary, so a board stays a board.
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = True
            if len(edge.link_faces) == 2:
                f0, f1 = edge.link_faces
                if (f0.material_index != f1.material_index
                        or edge.calc_face_angle(0.0) > math.radians(35.0)):
                    edge.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    paint_planks(me)
    out = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(out)
    return out


def _long_axis(pts):
    """Principal axis of a point set, by power iteration on its covariance."""
    c = sum(pts, Vector()) / len(pts)
    cov = [[0.0] * 3 for _ in range(3)]
    for p in pts:
        d = p - c
        for i in range(3):
            for j in range(3):
                cov[i][j] += d[i] * d[j]
    v = Vector((1.0, 0.3, 0.1))
    for _ in range(30):
        w = Vector([sum(cov[i][j] * v[j] for j in range(3)) for i in range(3)])
        if w.length < 1e-12:
            break
        v = w.normalized()
    return v


def paint_planks(me):
    """Per-shell ``PlankTone`` and ``GrainDir`` face attributes for the wood shader.

    Every plank, board, rail, leg, spoke and felloe is its own shell, so
    each gets one seeded tone and grain along its own long axis.
    """
    tone = [0.5] * len(me.polygons)
    grain = [(0.0, 0.0, 1.0)] * len(me.polygons)
    owner = {}
    rng = random.Random(TONE_SEED)
    for g in shell_groups(me):
        pts = [me.vertices[i].co.copy() for i in g]
        d = _long_axis(pts) if len(pts) > 2 else Vector((0.0, 0.0, 1.0))
        t = 0.5 + rng.uniform(-PLANK_TONE_JITTER, PLANK_TONE_JITTER)
        for i in g:
            owner[i] = (t, tuple(d))
    for poly in me.polygons:
        t, d = owner[poly.vertices[0]]
        tone[poly.index] = t
        grain[poly.index] = d
    a = me.attributes.new("PlankTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)
    b = me.attributes.new("GrainDir", "FLOAT_VECTOR", "FACE")
    b.data.foreach_set("vector", [c for v in grain for c in v])


def principled(name, color, metallic, roughness, noise_scale=0.0, wear=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if noise_scale > 0.0 and wear is not None:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = noise_scale
        tex.inputs["Detail"].default_value = 8.0
        tex.inputs["Roughness"].default_value = 0.55
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = color
        mix.inputs["B"].default_value = wear
        fac = mix.inputs.get("Factor") or mix.inputs.get("Fac")
        nt.links.new(tex.outputs["Fac"], fac)
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
        rmix = nt.nodes.new("ShaderNodeMix")
        rmix.data_type = "FLOAT"
        rmix.inputs["A"].default_value = roughness
        rmix.inputs["B"].default_value = min(1.0, roughness + 0.18)
        rfac = rmix.inputs.get("Factor") or rmix.inputs.get("Fac")
        nt.links.new(tex.outputs["Fac"], rfac)
        nt.links.new(rmix.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def _sock(sockets, identifier):
    """A Mix-node socket by identifier; its A/B/Result names repeat per type."""
    return next(sk for sk in sockets if sk.identifier == identifier)


def wood_material(name):
    """Grain along each board and rail (``GrainDir``), tone per piece (``PlankTone``).

    Copied from showcase/wheelbarrow (do not import across pieces).
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    gdir = nt.nodes.new("ShaderNodeAttribute")
    gdir.attribute_name = "GrainDir"
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "PlankTone"
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(coord.outputs["Object"], dot.inputs[0])
    nt.links.new(gdir.outputs["Vector"], dot.inputs[1])
    squash = nt.nodes.new("ShaderNodeMath")
    squash.operation = "MULTIPLY"
    squash.inputs[1].default_value = 0.94
    nt.links.new(dot.outputs["Value"], squash.inputs[0])
    along = nt.nodes.new("ShaderNodeVectorMath")
    along.operation = "SCALE"
    nt.links.new(gdir.outputs["Vector"], along.inputs[0])
    nt.links.new(squash.outputs["Value"], along.inputs["Scale"])
    grain_co = nt.nodes.new("ShaderNodeVectorMath")
    grain_co.operation = "SUBTRACT"
    nt.links.new(coord.outputs["Object"], grain_co.inputs[0])
    nt.links.new(along.outputs["Vector"], grain_co.inputs[1])
    shift = nt.nodes.new("ShaderNodeVectorMath")
    shift.operation = "ADD"
    nt.links.new(grain_co.outputs["Vector"], shift.inputs[0])
    nt.links.new(tone.outputs["Fac"], shift.inputs[1])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = WOOD_GRAIN_SCALE
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.62
    nt.links.new(shift.outputs["Vector"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.13, 0.058, 0.020, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.40, 0.20, 0.075, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 1.1
    gain.inputs[2].default_value = 0.45
    nt.links.new(tone.outputs["Fac"], gain.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(ramp.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(gain.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.72
    rough.inputs["To Max"].default_value = 0.52
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def cart_materials():
    """(wood, iron): shared by the check, the render and inspection.

    Forged iron, dark and rusted. The first build's metallic 1.0 at 0.50
    roughness rendered the tyres as bright polished steel beside the wood.
    """
    wood = wood_material("CartWood")
    metal = principled(
        "CartIron", (0.17, 0.165, 0.155, 1.0), 0.80, 0.46,
        noise_scale=18.0, wear=(0.20, 0.085, 0.032, 1.0),
    )
    return wood, metal


def assign_slots(obj, wood, metal):
    mats = obj.data.materials
    wanted = (wood, metal)
    for i, mat in enumerate(wanted):
        if i < len(mats):
            mats[i] = mat
        else:
            mats.append(mat)


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def uv_stats(mesh):
    """UV bounds and the summed pairwise AABB overlap area.

    A sweep over boxes sorted by min u: the same pairs and the same sum as
    the all-pairs loop, without its quadratic cost on a 4k-face piece.
    """
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
    for i in range(len(aabbs)):
        a = aabbs[i]
        for j in range(i + 1, len(aabbs)):
            b = aabbs[j]
            if b[0] >= a[2]:
                break
            y0 = max(a[1], b[1])
            y1 = min(a[3], b[3])
            overlap += (min(a[2], b[2]) - b[0]) * max(0.0, y1 - y0)
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
    nv, ne, nf = len(me.vertices), len(me.edges), len(me.polygons)
    ngons = sum(1 for p in me.polygons if len(p.vertices) > 4)
    areas = [face_area(me, p) for p in me.polygons]
    zero_area = sum(1 for a in areas if a <= AREA_EPS)
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        loose_v = sum(1 for v in bm.verts if len(v.link_edges) == 0)
        loose_e = sum(1 for e in bm.edges if len(e.link_faces) == 0)
        nonman = sum(1 for e in bm.edges if not e.is_manifold)
        ret = bmesh.ops.find_doubles(bm, verts=list(bm.verts), dist=DOUBLES_EPS)
        doubles = len(ret.get("targetmap") or {})
    finally:
        bm.free()
    return {
        "nv": nv,
        "ne": ne,
        "nf": nf,
        "ngons": ngons,
        "loose_v": loose_v,
        "loose_e": loose_e,
        "nonman": nonman,
        "zero_area": zero_area,
        "doubles": doubles,
        "euler": nv - ne + nf,
    }


def shell_groups(me):
    """Vertex-index shells by edge connectivity (union-find), biggest first."""
    parent = list(range(len(me.vertices)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in me.edges:
        ra, rb = find(int(e.vertices[0])), find(int(e.vertices[1]))
        if ra != rb:
            parent[rb] = ra
    groups = {}
    for i in range(len(me.vertices)):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: (-len(g), min(g)))


def shell_box(me, idxs):
    co = [me.vertices[i].co for i in idxs]
    return {
        "xmin": min(c.x for c in co), "xmax": max(c.x for c in co),
        "ymin": min(c.y for c in co), "ymax": max(c.y for c in co),
        "zmin": min(c.z for c in co), "zmax": max(c.z for c in co),
    }


def shell_mat(me, idxs):
    member = set(idxs)
    for p in me.polygons:
        if p.vertices[0] in member:
            return p.material_index
    return None


def coplanar_zfight_pairs(me, groups):
    """Coplanar face pairs from *different shells* — the z-fighting budget.

    Cross-shell, not merely share-no-vertex: two quads two steps apart on
    one flat cap share no vertex and are coplanar by construction, and
    counting those makes the budget unsatisfiable rather than meaningful.
    Z-fighting is two separate bodies landing on one plane, which is
    exactly a cross-shell pair. Combinatorics and constants copied from
    showcase/hay-bale (do not import across pieces); candidate pairs come
    from a KD-tree range query at COPLANAR_CENTRE_MAX, the same pairs the
    all-pairs loop visits.
    """
    owner = {}
    for si, comp in enumerate(groups):
        for vi in comp:
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


def wheel_shells(me, groups):
    """(rim, tyre) shell index pairs for each wheel, keyed by track side.

    Identified from the generated mesh by geometry — a shell centred on the
    axle line whose XZ extent is a full disc — never from a construction
    constant. The tyre is the metal-indexed member of the pair.
    """
    metal = set()
    for p in me.polygons:
        if p.material_index == METAL_IDX:
            metal.add(int(p.vertices[0]))
    found = {}
    for si, g in enumerate(groups):
        b = shell_box(me, g)
        dx = b["xmax"] - b["xmin"]
        dz = b["zmax"] - b["zmin"]
        if dx < 0.4 or abs(dx - dz) > 0.02:
            continue
        side = 1 if 0.5 * (b["ymin"] + b["ymax"]) > 0 else -1
        kind = "tyre" if any(i in metal for i in g) else "rim"
        found.setdefault(side, {})[kind] = si
    return found


def tyre_seat_depths(me, groups, rim_si, tyre_si, segments):
    """Per-station interference between the tyre's inner ring and the felloe.

    Banded and per angular station, not one global figure: a single number
    passes while one arc of the hoop visibly gaps. Both radii are recomputed
    from the generated vertices, so nothing here restates a constant.
    """
    axis_y = 0.5 * (shell_box(me, groups[tyre_si])["ymin"]
                    + shell_box(me, groups[tyre_si])["ymax"])
    rb = shell_box(me, groups[rim_si])
    cx = 0.5 * (rb["xmin"] + rb["xmax"])
    cz = 0.5 * (rb["zmin"] + rb["zmax"])

    def bins(idxs):
        out = {}
        for i in idxs:
            co = me.vertices[i].co
            ang = math.atan2(co.z - cz, co.x - cx)
            k = int(round(ang / (2.0 * math.pi / segments))) % segments
            out.setdefault(k, []).append(
                math.hypot(co.x - cx, co.z - cz))
        return out

    rim_bins = bins(groups[rim_si])
    tyre_bins = bins(groups[tyre_si])
    depths = []
    for k in sorted(set(rim_bins) & set(tyre_bins)):
        rim_out = max(rim_bins[k])
        tyre_in = min(tyre_bins[k])
        depths.append(rim_out - tyre_in)
    return depths, axis_y


def _wheel_centre(me, groups, rim_si):
    b = shell_box(me, groups[rim_si])
    return 0.5 * (b["xmin"] + b["xmax"]), 0.5 * (b["zmin"] + b["zmax"])


def break_tyre_seat(me, seat):
    """Falsifier surgery: re-radius each tyre's inner ring to `seat` deep.

    seat=0.0 puts the tyre's inner cylinder on the felloe's tread plane,
    which is the construction bug this piece was rebuilt to remove.
    """
    groups = shell_groups(me)
    for parts in wheel_shells(me, groups).values():
        cx, cz = _wheel_centre(me, groups, parts["rim"])
        idxs = groups[parts["tyre"]]
        radii = [math.hypot(me.vertices[i].co.x - cx,
                            me.vertices[i].co.z - cz) for i in idxs]
        split = 0.5 * (min(radii) + max(radii))
        for i, r in zip(idxs, radii):
            if r >= split:
                continue
            co = me.vertices[i].co
            scale = (RIM_OUTER - seat) / r
            co.x = cx + (co.x - cx) * scale
            co.z = cz + (co.z - cz) * scale
    me.update()


def move_one_wheel(me, delta):
    """Falsifier surgery: translate the +Y wheel only, as one body.

    Moves every shell lying wholly inside that wheel's envelope — felloe,
    tyre, nave, bands, washer, spokes — so the assembly stays intact and
    the opposite wheel still grounds the AABB. The axle runs across both
    wheels, so it is never wholly inside one and stays put.
    """
    groups = shell_groups(me)
    parts = wheel_shells(me, groups).get(1)
    if parts is None:
        return
    b = shell_box(me, groups[parts["tyre"]])
    cx, cz = _wheel_centre(me, groups, parts["rim"])
    wy = 0.5 * (b["ymin"] + b["ymax"])
    r_max = 0.5 * (b["xmax"] - b["xmin"]) + 1e-3
    for g in groups:
        inside = all(
            math.hypot(me.vertices[i].co.x - cx, me.vertices[i].co.z - cz) <= r_max
            and abs(me.vertices[i].co.y - wy) <= NAVE_L / 2.0 + 0.02
            for i in g
        )
        if not inside:
            continue
        for i in g:
            co = me.vertices[i].co
            co.x += delta[0]
            co.y += delta[1]
            co.z += delta[2]
    me.update()


def lift_bed(me, dz):
    """Falsifier surgery: raise the box — planks, walls, straps — off its rails.

    The box is every shell whose floor sits at or above the rails' top less
    the floor's bite, read off the mesh. Lifted by more than that bite, the
    planks clear the rails and the box is joined to nothing below it.
    """
    groups = shell_groups(me)
    rails = [g for g in groups
             if shell_mat(me, g) == WOOD_IDX
             and (shell_box(me, g)["xmax"] - shell_box(me, g)["xmin"]) > BED_L + 0.3]
    if not rails:
        return
    rail_top = max(shell_box(me, g)["zmax"] for g in rails)
    floor = rail_top - FLOOR_BITE - 1e-4
    for g in groups:
        if shell_box(me, g)["zmin"] < floor:
            continue
        for i in g:
            me.vertices[i].co.z += dz
    me.update()


def support_audit(me, groups, wheels):
    """Floor contact per named support: each tyre and each prop leg.

    Legs are the wood shells that stand tall and thin; counted, so a leg a
    classifier drops cannot pass vacuously.
    """
    out = {}
    for side, parts in sorted(wheels.items()):
        tb = shell_box(me, groups[parts["tyre"]])
        out["tyre+Y" if side > 0 else "tyre-Y"] = tb["zmin"]
    legs = []
    for g in groups:
        if shell_mat(me, g) != WOOD_IDX:
            continue
        b = shell_box(me, g)
        if (b["zmax"] - b["zmin"]) > 0.3 and (b["xmax"] - b["xmin"]) < 0.06 \
                and (b["ymax"] - b["ymin"]) < 0.06:
            legs.append(b)
    legs.sort(key=lambda b: b["ymin"])
    for i, b in enumerate(legs):
        out[f"leg{i}"] = b["zmin"]
    return out, len(legs)


def wall_board_audit(me, groups):
    """Side-wall boards per side and the seam between each stacked pair.

    Boards are the wood shells that run the bed's length, are one board
    thick, and stand above the rails — read off the mesh.
    """
    rails_top = -1.0
    for g in groups:
        b = shell_box(me, g)
        if shell_mat(me, g) == WOOD_IDX and (b["xmax"] - b["xmin"]) > BED_L + 0.3:
            rails_top = max(rails_top, b["zmax"])
    sides = {-1: [], 1: []}
    for g in groups:
        if shell_mat(me, g) != WOOD_IDX:
            continue
        b = shell_box(me, g)
        if (b["xmax"] - b["xmin"]) < 0.8 * BED_L:
            continue
        if (b["ymax"] - b["ymin"]) > 2.0 * WALL_T or b["zmin"] < rails_top:
            continue
        sides[1 if b["ymin"] > 0 else -1].append(b)
    seams = []
    for boards in sides.values():
        boards.sort(key=lambda b: b["zmin"])
        for lo, hi in zip(boards, boards[1:]):
            seams.append(hi["zmin"] - lo["zmax"])
    return len(sides[-1]), len(sides[1]), seams


def contact_components(me, groups):
    """Components of the shells' BVH-overlap graph.

    Every joint in the piece is a bite, so joined members' surfaces cross.
    One component means every member is attached to the assembly; a second
    is a part — or a whole sub-assembly — hanging in the air.
    """
    verts = [v.co.copy() for v in me.vertices]
    owner = {}
    for si, g in enumerate(groups):
        for vi in g:
            owner[vi] = si
    polys = [[] for _ in groups]
    for p in me.polygons:
        polys[owner[p.vertices[0]]].append(tuple(p.vertices))
    trees = [BVHTree.FromPolygons(verts, ps) if ps else None for ps in polys]
    boxes = [shell_box(me, g) for g in groups]
    parent = list(range(len(groups)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    pad = 1e-4
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            a, b = boxes[i], boxes[j]
            if (a["xmin"] > b["xmax"] + pad or b["xmin"] > a["xmax"] + pad
                    or a["ymin"] > b["ymax"] + pad or b["ymin"] > a["ymax"] + pad
                    or a["zmin"] > b["zmax"] + pad or b["zmin"] > a["zmax"] + pad):
                continue
            if trees[i] is None or trees[j] is None:
                continue
            if trees[i].overlap(trees[j]):
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[rb] = ra
    return len({find(i) for i in range(len(groups))})


def right_angle_edges(me):
    """Manifold edges whose two faces meet at 90 degrees, iron and timber.

    Every box and ring in the piece is chamfered, and a chamfer turns a
    90-degree edge into two shallower ones. An edge still at 90 is one a
    bevel pass skipped: the razor edge that renders as a hard black line.
    Copied from showcase/crate-stack (do not import across pieces).
    """
    counts = {WOOD_IDX: 0, METAL_IDX: 0}
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        for e in bm.edges:
            if len(e.link_faces) != 2:
                continue
            if abs(e.calc_face_angle(0.0) - math.pi / 2.0) <= RIGHT_ANGLE_TOL:
                idx = e.link_faces[0].material_index
                counts[idx] = counts.get(idx, 0) + 1
    finally:
        bm.free()
    return counts


def min_mat_distance(me, ia, ib):
    """Closest surface distance between two material islands via BVH.

    Vert-vert distance is the wrong metric for thin parts: a face interior
    can touch while its corner verts sit a radius apart.
    """
    bm_a = bmesh.new()
    bm_b = bmesh.new()
    try:
        bm_a.from_mesh(me)
        bm_b.from_mesh(me)
        bm_a.faces.ensure_lookup_table()
        bm_b.faces.ensure_lookup_table()
        drop_a = [f for f in bm_a.faces if f.material_index != ia]
        drop_b = [f for f in bm_b.faces if f.material_index != ib]
        if drop_a:
            bmesh.ops.delete(bm_a, geom=drop_a, context="FACES")
        if drop_b:
            bmesh.ops.delete(bm_b, geom=drop_b, context="FACES")
        if not bm_a.faces or not bm_b.faces:
            return 1e9
        tree = BVHTree.FromBMesh(bm_b)
        best = 1e9
        for src in list(bm_a.verts) + list(bm_a.faces):
            co = src.co if hasattr(src, "co") else src.calc_center_median()
            hit = tree.find_nearest(co)
            if hit[0] is None:
                continue
            best = min(best, hit[3])
        return best
    finally:
        bm_a.free()
        bm_b.free()


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


def texel_audit(mesh, img):
    """Smallest UV cell, in baked texels along its longer side.

    Every face packs into its own UV cell, so a small image spreads a few
    texels over each face and the render's bilinear lookup reads the next
    cell's normals across the border. Copied from showcase/tavern-stool
    (do not import across pieces).
    """
    uv = mesh.uv_layers.active
    if uv is None or img is None:
        return 0.0
    res = min(img.size[0], img.size[1])
    data = uv.data
    worst = 1e9
    for poly in mesh.polygons:
        us = [data[i].uv[0] for i in poly.loop_indices]
        vs = [data[i].uv[1] for i in poly.loop_indices]
        worst = min(worst, max(max(us) - min(us), max(vs) - min(vs)) * res)
    return worst


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("CartNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = WOOD_IDX
    return img, tex


def bake_normal(high, low):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    deselect_all()
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
    deselect_all()
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


def _no():
    return None, None, None, None, None


def check(skip_decimate, lift_z=False, flush_tyre=False, sink_tyre=False,
          float_wheel=False, skew_wheel=False, short_props=False,
          wide_seams=False, lift_bed_flag=False, sharp_bar=False,
          low_bake=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(sharp_bar=sharp_bar, wide_seams=wide_seams, short_props=short_props)
    low = build_cart_mesh("CartLow", 0.005, 1, **flags)
    high = build_cart_mesh("CartHigh", 0.005, 3, **flags)
    wood, metal = cart_materials()
    assign_slots(low, wood, metal)
    assign_slots(high, wood, metal)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
    if flush_tyre:
        break_tyre_seat(low.data, 0.0)
    if sink_tyre:
        break_tyre_seat(low.data, SINK_TYRE_SEAT)
    if float_wheel:
        move_one_wheel(low.data, (0.0, 0.0, FLOAT_WHEEL_Z))
    if skew_wheel:
        move_one_wheel(low.data, (0.0, SKEW_WHEEL_Y, 0.0))
    if lift_bed_flag:
        lift_bed(low.data, LIFT_BED)

    if low.data is None or len(low.data.polygons) < 6:
        return (fail("cart mesh did not build", 3),) + _no()

    base_tris = triangle_count(low.data)
    mats = [s for s in low.data.materials if s is not None]
    nmat = len(mats)
    distinct_mats = len({id(s) for s in mats})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    print(f"measured mat_index_counts={idx_counts}")
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x = bb[3] - bb[0]
    size_y = bb[4] - bb[1]
    size_z = bb[5] - bb[2]

    img, tex = setup_bake_image(low, wood, LOW_BAKE_RES if low_bake else BAKE_RES)
    if img is None:
        return (fail("cart has no UV layer", 3),) + _no()
    bake_result = bake_normal(high, low)
    texel = texel_audit(low.data, img)
    print(f"measured bake_res={img.size[0]} texel_min={texel:.2f}")

    lod1 = make_lod(low, "CartLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "CartLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_cart_mesh("CartColSrc", 0.0, 1)
    collider = convex_hull_collider(collider_src, "CartCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_cart_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender sets TMPDIR from its own preference, which resolves to the
    # working directory on a stock portable build — so gettempdir() is the
    # repo root under CI and every run left a .glb behind. The budget only
    # needs the byte count, so drop the file once it is measured.
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(
        f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
        f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}"
    )
    print(
        f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
        f"overlap={overlap:.6f} nfaces={nfaces}"
    )
    print(
        f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
        f"outer={OUTER_SIZE} zmin={bb[2]:.4f}"
    )
    print(
        f"measured collider_tris={col_tris} bake={bake_result} "
        f"bake_has_data={img.has_data} export_bytes={export_size}"
    )
    hyg = hygiene_audit(low.data)
    gap_mw = min_mat_distance(low.data, METAL_IDX, WOOD_IDX)
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} euler={hyg['euler']}"
    )
    print(f"measured gap_metal_wood={gap_mw:.5f}")

    groups = shell_groups(low.data)
    zfight = coplanar_zfight_pairs(low.data, groups)
    wheels = wheel_shells(low.data, groups)
    supports, n_legs = support_audit(low.data, groups, wheels)
    seats = []
    for side, parts in sorted(wheels.items()):
        depths, _ = tyre_seat_depths(
            low.data, groups, parts["rim"], parts["tyre"], WHEEL_SEGMENTS
        )
        seats.extend(depths)
    support_worst = max((abs(z) for z in supports.values()), default=1e9)
    seat_min = min(seats) if seats else -1.0
    seat_max = max(seats) if seats else 1e9
    seat_n = len(seats)
    # Mirror: the two wheels are one part reflected in Y, so their rim
    # centres must match in X and Z and be opposite in Y.
    wheel_mirror = 1e9
    if len(wheels) == 2:
        boxes = {}
        for side, parts in wheels.items():
            b = shell_box(low.data, groups[parts["rim"]])
            boxes[side] = (
                0.5 * (b["xmin"] + b["xmax"]),
                0.5 * (b["ymin"] + b["ymax"]),
                0.5 * (b["zmin"] + b["zmax"]),
                b["xmax"] - b["xmin"],
                b["zmax"] - b["zmin"],
            )
        a, b2 = boxes[1], boxes[-1]
        wheel_mirror = max(
            abs(a[0] - b2[0]), abs(a[1] + b2[1]), abs(a[2] - b2[2]),
            abs(a[3] - b2[3]), abs(a[4] - b2[4]),
        )
    n_left, n_right, seams = wall_board_audit(low.data, groups)
    seam_lo = min(seams) if seams else -1.0
    seam_hi = max(seams) if seams else 1e9
    components = contact_components(low.data, groups)
    right_angles = right_angle_edges(low.data)
    n_right_angles = sum(right_angles.values())
    print(
        f"measured zfight_pairs={zfight} shells={len(groups)} "
        f"supports={ {k: round(v, 6) for k, v in supports.items()} } legs={n_legs} "
        f"tyre_seat=[{seat_min:.5f},{seat_max:.5f}] over {seat_n} stations "
        f"wheel_mirror={wheel_mirror*1000:.5f}mm"
    )
    print(
        f"measured wall_boards=({n_left},{n_right}) "
        f"seams=[{seam_lo:.5f},{seam_hi:.5f}] components={components} "
        f"right_angle_edges={right_angles}"
    )

    if len(wheels) != 2 or any(len(p) != 2 for p in wheels.values()):
        return (fail(f"expected 2 wheels of (rim, tyre) shells, found {wheels}", 3),) + _no()
    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(
            f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4,
        ),) + _no()
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(
            f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5,
        ),) + _no()
    if idx_counts.get(METAL_IDX, 0) < METAL_FACES_MIN:
        return (fail(
            f"metal faces {idx_counts.get(METAL_IDX, 0)} < {METAL_FACES_MIN}", 5,
        ),) + _no()
    if idx_counts.get(WOOD_IDX, 0) < WOOD_FACES_MIN:
        return (fail(
            f"wood faces {idx_counts.get(WOOD_IDX, 0)} < {WOOD_FACES_MIN}", 5,
        ),) + _no()
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(
            f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6,
        ),) + _no()
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + _no()
    if (
        abs(size_x - OUTER_SIZE[0]) > BBOX_TOL
        or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
        or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL
    ):
        return (fail(
            f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8,
        ),) + _no()
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(
            f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
            "(--skip-decimate is the designed fail)",
            9,
        ),) + _no()
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(
            f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9,
        ),) + _no()
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + _no()
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(
            f"bake failed result={bake_result} has_data={img.has_data}", 12,
        ),) + _no()
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + _no()
    if (
        hyg["loose_v"]
        or hyg["loose_e"]
        or hyg["nonman"]
        or hyg["zero_area"]
        or hyg["doubles"]
        or hyg["ngons"]
    ):
        return (fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']}",
            15,
        ),) + _no()
    if zfight > ZFIGHT_PAIRS_MAX:
        return (fail(
            f"coplanar cross-shell face pairs {zfight} > {ZFIGHT_PAIRS_MAX} "
            "(--flush-tyre is the designed fail: a tyre whose inner radius "
            "equals the felloe's outer radius puts both on one plane)",
            15,
        ),) + _no()
    if abs(bb[2]) > ZMIN_EPS:
        return (fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ),) + _no()
    if n_legs != N_LEGS or support_worst > SUPPORT_ZMIN_EPS:
        return (fail(
            f"named supports {supports} legs={n_legs}: worst zmin "
            f"{support_worst:.6f} > {SUPPORT_ZMIN_EPS} "
            "(--float-wheel and --short-props are the designed fails: one "
            "support off the floor while the rest still ground the AABB)",
            16,
        ),) + _no()
    if gap_mw > GAP_MAX:
        return (fail(
            f"metal-wood gap {gap_mw:.5f} > {GAP_MAX} "
            "(tyres, bands, washers and straps must touch the wood they mount to)",
            17,
        ),) + _no()
    if (n_left, n_right) != (WALL_BOARDS, WALL_BOARDS) or not (
        WALL_SEAM_MIN <= seam_lo and seam_hi <= WALL_SEAM_MAX
    ):
        return (fail(
            f"side-wall boards ({n_left},{n_right}) != {WALL_BOARDS} per side or "
            f"seams [{seam_lo:.5f},{seam_hi:.5f}] outside "
            f"[{WALL_SEAM_MIN}, {WALL_SEAM_MAX}] "
            "(--wide-seams is the designed fail)",
            17,
        ),) + _no()
    if seat_min < TYRE_SEAT_MIN or seat_max > TYRE_SEAT_MAX:
        return (fail(
            f"tyre seat depth band [{seat_min:.5f}, {seat_max:.5f}] outside "
            f"[{TYRE_SEAT_MIN}, {TYRE_SEAT_MAX}] over {seat_n} stations "
            "(--sink-tyre is the designed fail: the hoop swallowed by the "
            "felloe reads as one body, not a tyre)",
            18,
        ),) + _no()
    if components != CONTACT_COMPONENTS:
        return (fail(
            f"shell contact graph has {components} components, expected "
            f"{CONTACT_COMPONENTS} (--lift-bed is the designed fail: the box "
            "raised off its rails is joined to nothing below it)",
            18,
        ),) + _no()
    if wheel_mirror > WHEEL_MIRROR_EPS:
        return (fail(
            f"wheel mirror deviation {wheel_mirror*1000:.4f} mm > "
            f"{WHEEL_MIRROR_EPS*1000:.4f} mm "
            "(--skew-wheel is the designed fail: the two wheels are one part "
            "reflected in Y and must sit at matched X and Z)",
            19,
        ),) + _no()
    if n_right_angles > RIGHT_ANGLE_MAX:
        return (fail(
            f"right-angle edges {right_angles} > {RIGHT_ANGLE_MAX} "
            "(--sharp-bar is the designed fail: the pull bar left unchamfered)",
            20,
        ),) + _no()
    if texel < TEXEL_MIN:
        return (fail(
            f"bake texel density {texel:.2f} px per UV cell < {TEXEL_MIN} "
            "(--low-bake is the designed fail: a 256 px bake smears each "
            "face's normals into its neighbours')",
            21,
        ),) + _no()
    return 0, low, high, wood, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, wood, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(wood, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(-28.0)
    low.rotation_euler.x = math.radians(0.0)

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
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02, 0.021, 0.025, 1.0,
    )
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", (-3.4, -4.8, 5.4), 640.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (4.8, -3.4, 2.4), 46.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.2, 4.0, 3.8), 600.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.34, -1.62, 0.88)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.05, 0.0, 0.30)
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
    scene.render.image_settings.file_format = (
        "WEBP" if path.lower().endswith(".webp") else "PNG"
    )
    if path.lower().endswith(".webp"):
        scene.render.image_settings.quality = 90
    scene.render.filepath = path
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(
        scene, cam, hero=[low], elements=[low], stage=[floor, wall],
    )
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
    p.add_argument(
        "--skip-decimate",
        action="store_true",
        help="falsification: skip the LOD DECIMATE stage",
    )
    p.add_argument(
        "--lift-z",
        action="store_true",
        help="falsification: lift the mesh so zmin fails the grounded budget",
    )
    p.add_argument(
        "--flush-tyre",
        action="store_true",
        help="falsification: tyre inner radius == felloe outer radius, so "
             "both land on one plane and the z-fight budget fails",
    )
    p.add_argument(
        "--sink-tyre",
        action="store_true",
        help="falsification: bury the tyre in the felloe so the seat band fails",
    )
    p.add_argument(
        "--float-wheel",
        action="store_true",
        help="falsification: lift one wheel off the floor while the other "
             "still grounds the AABB, so the named-support budget fails",
    )
    p.add_argument(
        "--skew-wheel",
        action="store_true",
        help="falsification: push one wheel out along the track so the "
             "wheel-mirror budget fails",
    )
    p.add_argument(
        "--short-props",
        action="store_true",
        help="falsification: stop both prop legs 3 mm above the floor while "
             "the tyres still ground the AABB, so the named-support budget fails",
    )
    p.add_argument(
        "--wide-seams",
        action="store_true",
        help="falsification: open the wall-board seams to 10 mm (same "
             "triangles), so the board-seam budget fails",
    )
    p.add_argument(
        "--lift-bed",
        action="store_true",
        help="falsification: raise the box off its rails, so the contact "
             "graph splits and the one-assembly budget fails",
    )
    p.add_argument(
        "--sharp-bar",
        action="store_true",
        help="falsification: leave the pull bar's rims unchamfered, so the "
             "edge-treatment budget fails",
    )
    p.add_argument(
        "--low-bake",
        action="store_true",
        help="falsification: bake the normal map at 256 px, so the "
             "texel-density budget fails",
    )
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        flush_tyre=args.flush_tyre,
        sink_tyre=args.sink_tyre,
        float_wheel=args.float_wheel,
        skew_wheel=args.skew_wheel,
        short_props=args.short_props,
        wide_seams=args.wide_seams,
        lift_bed_flag=args.lift_bed,
        sharp_bar=args.sharp_bar,
        low_bake=args.low_bake,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("cart OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
