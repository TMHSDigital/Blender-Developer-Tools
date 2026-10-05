"""Game-ready village hand pump — a showcase piece, not an example.

Asserts budget conformance of a procedural cast-iron hand pump (plinth,
column, gooseneck, stuffing-box head, handle, wooden grip) after
composing shipped pipeline pieces: bmesh construction, UVs, two
materials, high-to-low normal bake, LOD chain, convex collider,
Unity glTF export.

The column stays on the origin; only zmin is snapped. The gooseneck is
a 6-gon tube about named stations on the lower-column radius, not a
chain of cylinders. The flange bites the plinth.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Hygiene family 15–19:
``--stray-vert``, ``--lift-z``, ``--float-spout``, ``--float-flange``,
``--skinny-col``; ``--shift-bucket`` (exit 20) sets the bucket out from
under the spout.

Construction is closed-form; the only RNG is the seeded per-piece wood
tone. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python hand_pump.py --
    blender --background --python hand_pump.py -- --skip-decimate
    blender --background --python hand_pump.py -- --output hand-pump.png
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

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402
import gallery_asset_quality  # noqa: E402

PLINTH_XY = 0.34
SLAB_H = 0.050
CAP_H = 0.040
PLINTH_BITE = 0.006
PLINTH_TOP = SLAB_H + CAP_H - PLINTH_BITE
COL_R_LO = 0.062
COL_R_HI = 0.046
COL_SEGS = 24
LOWER_H = 0.40
UPPER_H = 0.36
COL_H = LOWER_H + UPPER_H
SPOUT_Z = PLINTH_TOP + 0.36
SPOUT_R = 0.17                   # reach carries the nozzle out over the bucket
SPOUT_T = 0.036
SPOUT_N = 10
HANDLE_LIFT = 0.18
FLANGE_R = 0.095
FLANGE_H = 0.028
FLANGE_BITE = 0.006
BOLT_N = 4
BOLT_R = 0.008
BOLT_H = 0.014
# Cast detail. The foot and spout boss stay within COL_R_TOL of COL_R_LO so
# the column-radius budget still reads the barrel, not its mouldings.
FOOT_R = 0.068
BOSS_R = 0.067
RIB_N = 8                        # flutes on the upper barrel
RIB_W = 0.010
RIB_DEPTH = 0.008
RIB_PROUD = 0.004                # rib face proud of the barrel
TAIL_REACH = 0.085               # handle tail past the fulcrum, counterweighted
# A coopered bucket stands on the ground under the spout, clear of the
# plinth. Its profile is (r, z) from the foot up the outside, over the rim
# and down the inside to the inner floor; two iron hoops bind the staves.
BUCKET_PROFILE = (
    (0.068, 0.000), (0.075, 0.004), (0.082, 0.142), (0.084, 0.150),
    (0.077, 0.152), (0.073, 0.144), (0.068, 0.020),
)
BUCKET_SEGS = 16                 # one flat-shaded face per stave
# The collider source turns the bucket at 8 staves and leaves the hoops off:
# a convex collider does not need the cooperage, and at 16 staves the hull
# ran to 267 triangles, past Unity's 255 convex-collider ceiling.
BUCKET_PROXY_SEGS = 8
BUCKET_CLEAR = 0.010             # bucket side off the plinth slab
HOOP_Z = ((0.018, 0.034), (0.112, 0.128))
HOOP_T = 0.003
HOOP_BITE = 0.0008
BUCKET_CATCH_MARGIN = 0.015      # nozzle axis inside the mouth by this much
BUCKET_FREE_MIN = 0.004          # bucket shell to plinth: standing free
SHIFT_BUCKET = 0.12              # --shift-bucket: set out from under the spout

BBOX_TOL = 0.015
# y grew 0.382 -> 0.521 for the bucket in front of the plinth; z 1.052 ->
# 1.055 for the finial.
OUTER_SIZE = (0.610, 0.521, 1.055)
BASE_TRIS_MIN = 900
# 2200 -> 2600: the cast mouldings, flutes, finial, turned grip, handle
# tail and the hooped bucket take the pump from 1064 to 2412 triangles.
BASE_TRIS_MAX = 2600
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 220
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
METAL_FACES_MIN = 48
WOOD_FACES_MIN = 24

WOOD_IDX = 0
METAL_IDX = 1

# Per-piece wood tone jitter and grain frequency, as in shipping-crate.
PLANK_TONE_JITTER = 0.28
TONE_SEED = 29
WOOD_GRAIN_SCALE = 30.0

DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZMIN_EPS = 1e-4
ZFIGHT_EPS = 0.002
ZFIGHT_COS = 0.98
SPOUT_GAP_MAX = 0.008
FLANGE_GAP_MAX = 0.008
COL_R_TOL = 0.008
LIFT_Z = 0.05
FLOAT_SPOUT = 0.12
FLOAT_FLANGE = 0.04
SKINNY = 0.028


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


def add_box(bm, loc, scale, mat_idx, euler=(0.0, 0.0, 0.0)):
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = geo["verts"]
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        p = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
        v.co = rot @ p + origin
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


def add_oriented_box(bm, a, b, scale_xy, mat_idx):
    a = Vector(a)
    b = Vector(b)
    delta = b - a
    length = delta.length
    if length < 1e-8:
        return []
    quat = Vector((0.0, 0.0, 1.0)).rotation_difference(delta.normalized())
    eul = quat.to_euler("XYZ")
    return add_box(
        bm,
        ((a + b) * 0.5),
        (scale_xy[0], scale_xy[1], length),
        mat_idx,
        euler=(eul.x, eul.y, eul.z),
    )


def add_cyl_between(bm, a, b, radius, segments, mat_idx):
    a = Vector(a)
    b = Vector(b)
    delta = b - a
    length = delta.length
    if length < 1e-8:
        return []
    quat = Vector((0.0, 0.0, 1.0)).rotation_difference(delta.normalized())
    eul = quat.to_euler("XYZ")
    return add_cyl(
        bm,
        ((a + b) * 0.5),
        radius,
        length,
        segments,
        mat_idx,
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
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


def add_gooseneck(bm, x, y0, z0, radius, n, thick, mat_idx, t0=0.08, t1=1.0):
    pts = []
    for i in range(n + 1):
        t = t0 + (t1 - t0) * (i / n)
        ang = t * (math.pi / 2.0)
        pts.append(
            Vector(
                (
                    x,
                    y0 - radius * math.sin(ang),
                    z0 - radius * (1.0 - math.cos(ang)),
                )
            )
        )
    rings = 6
    r = thick * 0.5
    ring_verts = []
    for i, p in enumerate(pts):
        if i < n:
            tangent = (pts[i + 1] - p).normalized()
        else:
            tangent = (p - pts[i - 1]).normalized()
        side = tangent.cross(Vector((1.0, 0.0, 0.0)))
        if side.length < 1e-6:
            side = tangent.cross(Vector((0.0, 1.0, 0.0)))
        side.normalize()
        up = tangent.cross(side).normalized()
        ring = []
        for k in range(rings):
            ang = (2.0 * math.pi * k) / rings
            offset = side * math.cos(ang) * r + up * math.sin(ang) * r
            ring.append(bm.verts.new(p + offset))
        ring_verts.append(ring)
    bm.verts.ensure_lookup_table()
    for a, b in zip(ring_verts, ring_verts[1:]):
        for k in range(rings):
            k2 = (k + 1) % rings
            face = bm.faces.new((a[k], a[k2], b[k2], b[k]))
            face.material_index = mat_idx
    for end_i, p in ((0, pts[0]), (-1, pts[-1])):
        center = bm.verts.new(p)
        ring = ring_verts[end_i]
        for k in range(rings):
            k2 = (k + 1) % rings
            if end_i == 0:
                face = bm.faces.new((center, ring[k2], ring[k]))
            else:
                face = bm.faces.new((center, ring[k], ring[k2]))
            face.material_index = mat_idx
    return [v for ring in ring_verts for v in ring]


def add_cone(bm, loc, radius1, radius2, depth, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=True,
        segments=segments,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
    )
    verts = geo["verts"]
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


def add_rim(bm, loc, major, minor, mat_idx, euler=(0.0, 0.0, 0.0)):
    n_major = 14
    n_minor = 7
    rings = []
    for i in range(n_major):
        u = i * (2.0 * math.pi / n_major)
        ring = []
        for j in range(n_minor):
            v = j * (2.0 * math.pi / n_minor)
            x = (major + minor * math.cos(v)) * math.cos(u)
            y = (major + minor * math.cos(v)) * math.sin(u)
            z = minor * math.sin(v)
            ring.append(bm.verts.new((x, y, z)))
        rings.append(ring)
    bm.verts.ensure_lookup_table()
    for i in range(n_major):
        i2 = (i + 1) % n_major
        for j in range(n_minor):
            j2 = (j + 1) % n_minor
            face = bm.faces.new(
                (rings[i][j], rings[i2][j], rings[i2][j2], rings[i][j2])
            )
            face.material_index = mat_idx
    verts = [v for ring in rings for v in ring]
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    return verts


def add_ball(bm, loc, radius, mat_idx):
    geo = bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=4, radius=radius)
    verts = geo["verts"]
    origin = Vector(loc)
    for v in verts:
        v.co = v.co + origin
    for f in {f for v in verts for f in v.link_faces}:
        f.material_index = mat_idx
    return verts


def add_lathe(bm, profile, segments, mat_idx, loc=(0.0, 0.0, 0.0), euler=(0.0, 0.0, 0.0)):
    """One closed shell turned from an (r, z) profile about local Z.

    Profile runs bottom to top; the two end rings are closed with triangle
    fans, so the shell is watertight with no n-gons.
    """
    rings = []
    for r, z in profile:
        rings.append([
            bm.verts.new((r * math.cos(2.0 * math.pi * k / segments),
                          r * math.sin(2.0 * math.pi * k / segments), z))
            for k in range(segments)
        ])
    faces = []
    for a, b in zip(rings, rings[1:]):
        for k in range(segments):
            k2 = (k + 1) % segments
            faces.append(bm.faces.new((a[k], a[k2], b[k2], b[k])))
    for ring, z, bottom in ((rings[0], profile[0][1], True),
                            (rings[-1], profile[-1][1], False)):
        c = bm.verts.new((0.0, 0.0, z))
        for k in range(segments):
            k2 = (k + 1) % segments
            faces.append(bm.faces.new((c, ring[k2], ring[k]) if bottom
                                      else (c, ring[k], ring[k2])))
    for f in faces:
        f.material_index = mat_idx
    verts = list({v for f in faces for v in f.verts})
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    return verts


def add_hoop(bm, loc, r_lo, r_hi, z0, z1, t, segments, mat_idx):
    """A closed rectangular-section ring, its inner face following a taper.

    r_lo / r_hi are the inner radii at z0 / z1; t is the radial thickness.
    Four section corners swept round the axis close on themselves, so the
    ring is watertight without caps.
    """
    section = ((r_lo, z0), (r_lo + t, z0), (r_hi + t, z1), (r_hi, z1))
    rings = []
    for k in range(segments):
        ang = 2.0 * math.pi * k / segments
        c, s = math.cos(ang), math.sin(ang)
        rings.append([bm.verts.new((loc[0] + r * c, loc[1] + r * s, loc[2] + z))
                      for r, z in section])
    for k in range(segments):
        a, b = rings[k], rings[(k + 1) % segments]
        for j in range(4):
            j2 = (j + 1) % 4
            f = bm.faces.new((a[j], b[j], b[j2], a[j2]))
            f.material_index = mat_idx
    return [v for ring in rings for v in ring]


def bucket_wall_r(z):
    """Outside radius of the bucket staves at height z (foot to rim)."""
    (_r0, _z0), (r1, z1), (r2, z2) = BUCKET_PROFILE[0], BUCKET_PROFILE[1], BUCKET_PROFILE[2]
    return r1 + (r2 - r1) * (z - z1) / (z2 - z1)


def add_square_band(bm, z, half, t, h, mat_idx):
    metal = []
    metal.extend(add_box(bm, (0.0, half + t / 2.0, z), (2.0 * half + 2.0 * t, t, h), mat_idx))
    metal.extend(add_box(bm, (0.0, -(half + t / 2.0), z), (2.0 * half + 2.0 * t, t, h), mat_idx))
    metal.extend(add_box(bm, (half + t / 2.0, 0.0, z), (t, 2.0 * half, h), mat_idx))
    metal.extend(add_box(bm, (-(half + t / 2.0), 0.0, z), (t, 2.0 * half, h), mat_idx))
    return metal


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


def build_hand_pump_mesh(
    name,
    bevel_offset,
    bevel_segments,
    float_spout=False,
    float_flange=False,
    skinny_col=False,
    shift_bucket=False,
    proxy=False,
):
    """The pump; ``proxy`` builds the collider source (8-stave bucket, no hoops)."""
    bm = bmesh.new()
    try:
        wood = []
        r_lo = COL_R_LO - SKINNY if skinny_col else COL_R_LO
        r_hi = COL_R_HI - SKINNY * 0.6 if skinny_col else COL_R_HI
        top_z = PLINTH_TOP + COL_H
        pivot = Vector((0.0, r_hi + 0.028, top_z + 0.010))
        grip_end = Vector((-0.38, pivot.y + 0.015, pivot.z + HANDLE_LIFT))

        wood.extend(
            add_box(
                bm,
                (0.0, 0.0, SLAB_H / 2.0),
                (PLINTH_XY, PLINTH_XY, SLAB_H),
                WOOD_IDX,
            )
        )
        wood.extend(
            add_box(
                bm,
                (0.0, 0.0, SLAB_H - PLINTH_BITE + CAP_H / 2.0),
                (0.26, 0.26, CAP_H),
                WOOD_IDX,
            )
        )
        if bevel_offset > 0.0:
            edges = list({e for v in wood for e in v.link_edges})
            # set order follows memory addresses; sort so the bevel, and the
            # face order it produces, are the same on every run
            bm.edges.index_update()
            edges.sort(key=lambda e: e.index)
            ret = bmesh.ops.bevel(
                bm,
                geom=edges,
                offset=bevel_offset,
                segments=bevel_segments,
                profile=0.5,
                affect="EDGES",
                clamp_overlap=True,
            )
            for f in ret.get("faces") or []:
                f.material_index = WOOD_IDX

        # turned wooden grip: swells in the palm, necks at both ferrule ends
        wood.extend(
            add_lathe(
                bm,
                [(0.012, -0.060), (0.016, -0.052), (0.019, -0.030), (0.0205, 0.0),
                 (0.019, 0.030), (0.016, 0.050), (0.011, 0.060)],
                12,
                WOOD_IDX,
                loc=(grip_end.x, grip_end.y, grip_end.z),
                euler=(0.0, math.pi / 2.0, 0.0),
            )
        )

        flange_z = PLINTH_TOP - FLANGE_BITE + FLANGE_H / 2.0
        if float_flange:
            flange_z += FLOAT_FLANGE
        add_cyl(
            bm, (0.0, 0.0, flange_z), FLANGE_R, FLANGE_H, COL_SEGS, METAL_IDX
        )
        bolt_ring = FLANGE_R * 0.72
        for i in range(BOLT_N):
            ang = math.pi / 4.0 + i * (math.pi / 2.0)
            add_cyl(
                bm,
                (
                    bolt_ring * math.cos(ang),
                    bolt_ring * math.sin(ang),
                    flange_z + FLANGE_H / 2.0 + BOLT_H / 2.0 - 0.002,
                ),
                BOLT_R,
                BOLT_H,
                8,
                METAL_IDX,
            )

        # cast lower barrel, one turned shell: a moulded foot that steps down
        # onto the flange, the plain barrel, and a boss where the spout is
        # cast on. Every radius follows r_lo, so --skinny-col thins it all.
        dr = COL_R_LO - r_lo
        add_lathe(
            bm,
            [(r - dr, z) for r, z in (
                (FOOT_R, 0.000), (FOOT_R, 0.016), (0.065, 0.028), (COL_R_LO, 0.050),
                (COL_R_LO, SPOUT_Z - PLINTH_TOP - 0.030), (BOSS_R, SPOUT_Z - PLINTH_TOP - 0.018),
                (BOSS_R, SPOUT_Z - PLINTH_TOP + 0.018), (COL_R_LO, SPOUT_Z - PLINTH_TOP + 0.030),
                (COL_R_LO, LOWER_H),
            )],
            COL_SEGS,
            METAL_IDX,
            loc=(0.0, 0.0, PLINTH_TOP),
        )
        joint_z = PLINTH_TOP + LOWER_H
        add_cyl(
            bm,
            (0.0, 0.0, joint_z + UPPER_H / 2.0 - 0.006),
            r_hi,
            UPPER_H,
            COL_SEGS,
            METAL_IDX,
        )
        # moulded collar where the upper barrel is socketed into the lower
        add_cone(
            bm,
            (0.0, 0.0, joint_z + 0.004),
            0.066 - dr,
            r_hi + 0.006,
            0.028,
            COL_SEGS,
            METAL_IDX,
        )
        # fluted upper barrel: raised ribs cast proud of the column
        rib_z0 = joint_z + 0.045
        rib_z1 = top_z - 0.030
        for k in range(RIB_N):
            ang = (k + 0.5) * (2.0 * math.pi / RIB_N)
            rc = r_hi + RIB_PROUD - RIB_DEPTH / 2.0
            add_box(
                bm,
                (rc * math.cos(ang), rc * math.sin(ang), 0.5 * (rib_z0 + rib_z1)),
                (RIB_DEPTH, RIB_W, rib_z1 - rib_z0),
                METAL_IDX,
                euler=(0.0, 0.0, ang),
            )

        add_cyl(
            bm,
            (0.0, 0.0, top_z + 0.012),
            0.052,
            0.048,
            COL_SEGS,
            METAL_IDX,
        )
        add_cyl(
            bm,
            (0.0, 0.0, top_z + 0.044),
            0.032,
            0.030,
            8,
            METAL_IDX,
        )
        # domed cap and ball finial over the stuffing box
        add_cone(bm, (0.0, 0.0, top_z + 0.065), 0.030, 0.012, 0.020, 16, METAL_IDX)
        add_ball(bm, (0.0, 0.0, top_z + 0.087), 0.016, METAL_IDX)

        cheek_y = pivot.y
        add_box(
            bm,
            (0.028, cheek_y, pivot.z),
            (0.016, 0.046, 0.044),
            METAL_IDX,
        )
        add_box(
            bm,
            (-0.028, cheek_y, pivot.z),
            (0.016, 0.046, 0.044),
            METAL_IDX,
        )
        add_cyl(
            bm,
            (0.0, cheek_y, pivot.z),
            0.010,
            0.068,
            10,
            METAL_IDX,
            euler=(0.0, math.pi / 2.0, 0.0),
        )
        add_oriented_box(
            bm,
            (pivot.x, pivot.y, pivot.z),
            (grip_end.x + 0.03, grip_end.y, grip_end.z),
            (0.018, 0.014),
            METAL_IDX,
        )
        # the handle's short tail runs on past the fulcrum and ends in a
        # cast ball, the counterweight a village pump handle carries
        tail_end = Vector((TAIL_REACH, pivot.y, pivot.z - 0.030))
        add_oriented_box(
            bm,
            (pivot.x - 0.012, pivot.y, pivot.z + 0.004),
            (tail_end.x, tail_end.y, tail_end.z),
            (0.016, 0.013),
            METAL_IDX,
        )
        add_ball(bm, (tail_end.x, tail_end.y, tail_end.z), 0.019, METAL_IDX)

        y0 = -r_lo
        z0 = SPOUT_Z
        if float_spout:
            y0 -= FLOAT_SPOUT
        add_gooseneck(
            bm, 0.0, y0, z0, SPOUT_R, SPOUT_N, SPOUT_T, METAL_IDX, t0=-0.14
        )
        nozzle_y = y0 - SPOUT_R
        nozzle_z = z0 - SPOUT_R
        add_cone(
            bm,
            (0.0, nozzle_y, nozzle_z - 0.028),
            0.014,
            0.020,
            0.044,
            12,
            METAL_IDX,
        )
        # rolled drip lip at the mouth, so water leaves clean off the nozzle
        add_cone(
            bm,
            (0.0, nozzle_y, nozzle_z - 0.051),
            0.019,
            0.016,
            0.008,
            12,
            METAL_IDX,
        )

        # coopered bucket on the ground under the spout, stood just clear
        # of the plinth slab; staves are the flat-shaded lathe faces
        bucket_y = -(PLINTH_XY / 2.0 + BUCKET_CLEAR + BUCKET_PROFILE[3][0] + HOOP_T)
        if shift_bucket:
            bucket_y -= SHIFT_BUCKET
        bucket_loc = (0.0, bucket_y, 0.0)
        wood.extend(add_lathe(bm, list(BUCKET_PROFILE),
                              BUCKET_PROXY_SEGS if proxy else BUCKET_SEGS,
                              WOOD_IDX, loc=bucket_loc))
        for z0, z1 in (() if proxy else HOOP_Z):
            add_hoop(bm, bucket_loc, bucket_wall_r(z0) - HOOP_BITE,
                     bucket_wall_r(z1) - HOOP_BITE, z0, z1, HOOP_T,
                     BUCKET_SEGS, METAL_IDX)

        zs = [v.co.z for v in bm.verts]
        zmin = min(zs)
        for v in bm.verts:
            v.co.z -= zmin
            if v.co.z < 0.0:
                v.co.z = 0.0

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = face.material_index == METAL_IDX
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        for poly in me.polygons:
            poly.use_smooth = poly.material_index == METAL_IDX
    finally:
        bm.free()
    out = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(out)
    return out


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
        tex.inputs["Detail"].default_value = 6.0
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = color
        mix.inputs["B"].default_value = wear
        fac = mix.inputs.get("Factor") or mix.inputs.get("Fac")
        nt.links.new(tex.outputs["Fac"], fac)
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    return mat


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

    Each plinth slab and the handle grip is its own shell, so each gets
    one tone and grain running along its own long axis.
    """
    tone = [0.5] * len(me.polygons)
    grain = [(0.0, 0.0, 1.0)] * len(me.polygons)
    owner = {}
    rng = random.Random(TONE_SEED)
    for g in shells(me):
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


def _sock(sockets, identifier):
    """A Mix-node socket by identifier; its A/B/Result names repeat per type."""
    return next(sk for sk in sockets if sk.identifier == identifier)


def wood_material(name):
    """Grain along each slab and the grip (``GrainDir``), tone per piece (``PlankTone``)."""
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
    ramp.color_ramp.elements[0].color = (0.12, 0.052, 0.018, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.38, 0.18, 0.065, 1.0)
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


def pump_materials():
    """(wood, iron): shared by the check, the render and inspection.

    A cast-iron village pump is painted in dark green enamel and weathers
    to rust at the
    edges and pores; the first build was polished metal (metallic 1.0,
    roughness 0.38) and read as chrome; the second build's near-black
    paint vanished into the dark stage.
    """
    wood = wood_material("HandPumpWood")
    metal = principled(
        "HandPumpIron", (0.020, 0.150, 0.075, 1.0), 0.25, 0.42,
        noise_scale=24.0, wear=(0.16, 0.065, 0.025, 1.0),
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
    mat = obj.matrix_world
    pts = [mat @ v.co for v in obj.data.vertices]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
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
    overlap = 0.0
    for i in range(len(aabbs)):
        a = aabbs[i]
        for j in range(i + 1, len(aabbs)):
            b = aabbs[j]
            x0 = max(a[0], b[0])
            y0 = max(a[1], b[1])
            x1 = min(a[2], b[2])
            y1 = min(a[3], b[3])
            overlap += max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return min(us), min(vs), max(us), max(vs), overlap, len(aabbs)


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
    nv, ne, nf = len(me.vertices), len(me.edges), len(me.polygons)
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
    return {
        "nv": nv, "ne": ne, "nf": nf, "ngons": ngons,
        "loose_v": loose_v, "loose_e": loose_e, "nonman": nonman,
        "zero_area": zero_area, "doubles": doubles, "euler": nv - ne + nf,
    }


def zfight_pairs(me):
    data = [
        (p.center.copy(), p.normal.copy(), frozenset(p.vertices))
        for p in me.polygons
    ]
    eps2 = ZFIGHT_EPS * ZFIGHT_EPS
    count = 0
    for i in range(len(data)):
        ci, ni, vi = data[i]
        for j in range(i + 1, len(data)):
            cj, nj, vj = data[j]
            if (cj - ci).length_squared > eps2:
                continue
            if abs(ni.dot(nj)) <= ZFIGHT_COS:
                continue
            if vi & vj:
                continue
            count += 1
    return count


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
            current = stack.pop()
            group.append(current)
            for nxt in neighbors[current]:
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(nxt)
        groups.append(group)
    return groups


def shell_aabb(me, group):
    pts = [me.vertices[i].co for i in group]
    return (
        min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts),
        max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts),
    )


def mat_of(me, group):
    member = set(group)
    for poly in me.polygons:
        if all(i in member for i in poly.vertices):
            return poly.material_index
    return None


def shell_bvh_gap(me, ga, gb):
    bm_a = bmesh.new()
    bm_b = bmesh.new()
    try:
        bm_a.from_mesh(me)
        bm_b.from_mesh(me)
        keep_a, keep_b = set(ga), set(gb)
        drop_a = [f for f in bm_a.faces if not all(v.index in keep_a for v in f.verts)]
        drop_b = [f for f in bm_b.faces if not all(v.index in keep_b for v in f.verts)]
        if drop_a:
            bmesh.ops.delete(bm_a, geom=drop_a, context="FACES")
        if drop_b:
            bmesh.ops.delete(bm_b, geom=drop_b, context="FACES")
        if not bm_a.faces or not bm_b.faces:
            return 1e9
        tree = BVHTree.FromBMesh(bm_b)
        best = 1e9
        for v in bm_a.verts:
            hit = tree.find_nearest(v.co)
            if hit[0] is not None:
                best = min(best, hit[3])
        for f in bm_a.faces:
            hit = tree.find_nearest(f.calc_center_median())
            if hit[0] is not None:
                best = min(best, hit[3])
        return best
    finally:
        bm_a.free()
        bm_b.free()


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, PLINTH_TOP + LOWER_H * 0.5))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def joint_audit(me):
    groups = shells(me)
    plinths = []
    columns = []
    spouts = []
    flanges = []
    buckets = []
    nozzles = []
    for g in groups:
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        mat = mat_of(me, g)
        if mat == WOOD_IDX and dz < 0.08 and dx > 0.20:
            plinths.append((g, a))
        if mat == METAL_IDX and dz > 0.25 and dx < 0.18 and dy < 0.18:
            columns.append((g, a))
        if mat == METAL_IDX and dy > 0.10 and dx < 0.10 and a[1] < -0.04:
            spouts.append((g, a))
        # centred on the column axis: the bucket's hoops are as wide and as low
        if (mat == METAL_IDX and dz < 0.05 and dx > 0.14 and a[2] < PLINTH_TOP + 0.05
                and abs(a[0] + a[3]) < 0.02 and abs(a[1] + a[4]) < 0.02):
            flanges.append((g, a))
        if mat == WOOD_IDX and dz > 0.10 and 0.12 < dx < 0.22 and a[4] < 0.0:
            buckets.append((g, a))
        if (mat == METAL_IDX and dx < 0.05 and dy < 0.05 and a[2] > 0.15
                and a[4] < -0.10):
            nozzles.append((g, a))
    spout_gap = 99.0
    if spouts and columns:
        spout_gap = min(
            shell_bvh_gap(me, s[0], c[0]) for s in spouts for c in columns
        )
    flange_gap = 99.0
    if flanges and plinths:
        flange_gap = min(
            shell_bvh_gap(me, f[0], p[0]) for f in flanges for p in plinths
        )
    col_r = 0.0
    if columns:
        widest = max(columns, key=lambda t: max(t[1][3] - t[1][0], t[1][4] - t[1][1]))
        a = widest[1]
        col_r = 0.5 * max(a[3] - a[0], a[4] - a[1])
    plinth_z = 99.0
    if plinths:
        plinth_z = min(a[2] for _g, a in plinths)
    # Bucket: where the nozzle's water falls against the bucket mouth. The
    # mouth radius is the innermost vertex ring within 12 mm of the rim; the
    # nozzle is the lowest small metal shell out on the spout side.
    catch = -99.0
    bucket_z = 99.0
    bucket_free = -99.0
    if buckets and nozzles:
        bg, ba = buckets[0]
        cx, cy = 0.5 * (ba[0] + ba[3]), 0.5 * (ba[1] + ba[4])
        top = ba[5]
        mouth = min(
            math.hypot(me.vertices[i].co.x - cx, me.vertices[i].co.y - cy)
            for i in bg if me.vertices[i].co.z > top - 0.012
        )
        ng, na = min(nozzles, key=lambda t: t[1][2])
        nx, ny = 0.5 * (na[0] + na[3]), 0.5 * (na[1] + na[4])
        nr = 0.5 * max(na[3] - na[0], na[4] - na[1])
        catch = mouth - (math.hypot(nx - cx, ny - cy) + nr)
        bucket_z = ba[2]
        if plinths:
            bucket_free = min(shell_bvh_gap(me, bg, p[0]) for p in plinths)
    return {
        "plinths": len(plinths),
        "columns": len(columns),
        "spouts": len(spouts),
        "flanges": len(flanges),
        "spout_gap": spout_gap,
        "flange_gap": flange_gap,
        "col_r": col_r,
        "plinth_z": plinth_z,
        "buckets": len(buckets),
        "catch": catch,
        "bucket_z": bucket_z,
        "bucket_free": bucket_free,
    }


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("HandPumpNrm", size, size, alpha=True, float_buffer=False)
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
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_yup=True,
                              export_apply=True, export_draco_mesh_compression_enable=False,
                              export_animations=False)


def check(
    skip_decimate,
    lift_z=False,
    stray_vert=False,
    float_spout=False,
    float_flange=False,
    skinny_col=False,
    shift_bucket=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    kw = dict(
        float_spout=float_spout,
        float_flange=float_flange,
        skinny_col=skinny_col,
        shift_bucket=shift_bucket,
    )
    low = build_hand_pump_mesh("HandPumpLow", bevel_offset=0.004, bevel_segments=2, **kw)
    high = build_hand_pump_mesh("HandPumpHigh", bevel_offset=0.004, bevel_segments=4, **kw)
    wood, metal = pump_materials()
    paint_planks(low.data)
    paint_planks(high.data)
    assign_slots(low, wood, metal)
    assign_slots(high, wood, metal)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("hand pump mesh did not build", 3), None, None, None, None, None

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

    img, tex = setup_bake_image(low, wood)
    if img is None:
        return fail("hand pump has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "HandPumpLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "HandPumpLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_hand_pump_mesh(
        "HandPumpColSrc", bevel_offset=0.0, bevel_segments=1, proxy=True, **kw
    )
    collider = convex_hull_collider(collider_src, "HandPumpCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_hand_pump_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender points TMPDIR at the working directory, so the export must not
    # outlive the measurement.
    if os.path.exists(export_path):
        os.remove(export_path)

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    jnt = joint_audit(low.data)

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
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}"
    )
    print(
        f"measured plinths={jnt['plinths']} columns={jnt['columns']} "
        f"spouts={jnt['spouts']} flanges={jnt['flanges']} "
        f"spout_gap={jnt['spout_gap']:.5f} flange_gap={jnt['flange_gap']:.5f} "
        f"col_r={jnt['col_r']:.5f} plinth_z={jnt['plinth_z']:.5f}"
    )
    print(
        f"measured bucket buckets={jnt['buckets']} catch={jnt['catch']:.5f} "
        f"zmin={jnt['bucket_z']:.5f} clear={jnt['bucket_free']:.5f}"
    )

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return fail(
            f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]",
            4,
        ), None, None, None, None, None
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return fail(
            f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(METAL_IDX, 0) < METAL_FACES_MIN:
        return fail(
            f"metal faces {idx_counts.get(METAL_IDX, 0)} < {METAL_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(WOOD_IDX, 0) < WOOD_FACES_MIN:
        return fail(
            f"wood faces {idx_counts.get(WOOD_IDX, 0)} < {WOOD_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return fail(
            f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})",
            6,
        ), None, None, None, None, None
    if overlap > UV_OVERLAP_MAX:
        return fail(
            f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}",
            7,
        ), None, None, None, None, None
    if bb[2] > ZMIN_EPS or jnt["plinth_z"] > ZMIN_EPS:
        return fail(
            f"grounded zmin={bb[2]:.5f} plinth_z={jnt['plinth_z']:.5f}",
            16,
        ), None, None, None, None, None
    if jnt["spouts"] < 1 or jnt["columns"] < 1 or jnt["spout_gap"] > SPOUT_GAP_MAX:
        return fail(
            f"spout gap {jnt['spout_gap']:.5f} spouts={jnt['spouts']} "
            f"columns={jnt['columns']}",
            17,
        ), None, None, None, None, None
    if jnt["flanges"] < 1 or jnt["plinths"] < 1 or jnt["flange_gap"] > FLANGE_GAP_MAX:
        return fail(
            f"flange gap {jnt['flange_gap']:.5f} flanges={jnt['flanges']} "
            f"plinths={jnt['plinths']}",
            18,
        ), None, None, None, None, None
    if abs(jnt["col_r"] - COL_R_LO) > COL_R_TOL:
        return fail(
            f"column radius {jnt['col_r']:.5f} off {COL_R_LO}",
            19,
        ), None, None, None, None, None
    if (
        jnt["buckets"] != 1
        or jnt["catch"] < BUCKET_CATCH_MARGIN
        or jnt["bucket_z"] > ZMIN_EPS
        or jnt["bucket_free"] < BUCKET_FREE_MIN
    ):
        return fail(
            f"bucket under spout: buckets={jnt['buckets']} catch {jnt['catch']:.5f} "
            f"< {BUCKET_CATCH_MARGIN}? zmin {jnt['bucket_z']:.5f} clear of plinth "
            f"{jnt['bucket_free']:.5f} (--shift-bucket is the designed fail)",
            20,
        ), None, None, None, None, None
    if (
        abs(size_x - OUTER_SIZE[0]) > BBOX_TOL
        or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
        or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL
    ):
        return fail(
            f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
            f"off outer {OUTER_SIZE}",
            8,
        ), None, None, None, None, None
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return fail(
            f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
            "(--skip-decimate is the designed fail)",
            9,
        ), None, None, None, None, None
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return fail(
            f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]",
            9,
        ), None, None, None, None, None
    if col_tris > COLLIDER_TRIS_MAX:
        return fail(
            f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}",
            11,
        ), None, None, None, None, None
    if bake_result != {"FINISHED"} or not img.has_data:
        return fail(
            f"bake failed result={bake_result} has_data={img.has_data}",
            12,
        ), None, None, None, None, None
    if export_size <= 0:
        return fail("export file missing or empty", 13), None, None, None, None, None
    if (
        hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
        or hyg["doubles"] or hyg["ngons"] or zf
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}",
            15,
        ), None, None, None, None, None
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

    low.rotation_euler.z = math.radians(-36.0)
    low.rotation_euler.x = math.radians(0.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        # Oversized so no edge of the set can enter frame; at 14 m the wall's
        # left edge showed as a bright band in the corner of the hero.
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

    light("Key", (-3.6, -5.0, 5.4), 620.0, 3.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.4, 2.4), 60.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    # cool rim from behind: lifts the column, handle and spout silhouettes
    # off the dark backdrop, where the first hero lost them
    rim = bpy.data.lights.new("Rim", "AREA")
    rim.energy = 140.0
    rim.size = 1.2
    rim.color = (0.62, 0.78, 1.0)
    rim_ob = bpy.data.objects.new("Rim", rim)
    rim_ob.location = (-1.1, 1.6, 1.9)
    # aimed at the column so it grazes the silhouette, not the backdrop
    rim_ob.rotation_euler = (Vector((0.0, 0.0, 0.7)) - rim_ob.location).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(rim_ob)
    light("Wedge", (2.2, 4.0, 3.8), 600.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.15, -2.35, 1.08)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.52)
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
    # asset-quality floors (examples/gallery_asset_quality.py) return 11,
    # which this piece's numbering already spends; remap at the call site
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
    p.add_argument("--float-spout", action="store_true")
    p.add_argument("--float-flange", action="store_true")
    p.add_argument("--skinny-col", action="store_true")
    p.add_argument("--shift-bucket", action="store_true",
                   help="falsification: stand the bucket out from under the spout")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_spout=args.float_spout,
        float_flange=args.float_flange,
        skinny_col=args.skinny_col,
        shift_bucket=args.shift_bucket,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("hand-pump OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
