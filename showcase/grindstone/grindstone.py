"""Game-ready grindstone — a showcase piece, not an example.

Asserts budget conformance of a procedural grindstone (thick sandstone
wheel, timber A-frame, open water trough, iron axle/hubs/crank) after
composing shipped pipeline pieces: bmesh construction, UVs, three
materials, high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. ``--skip-decimate`` skips the LOD
DECIMATE stage so the LOD-ratio budget fails. ``--stray-vert`` adds a
loose vertex so the mesh-hygiene budget fails. ``--lift-z`` raises the
mesh so the grounded-zmin budget fails. ``--float-crank`` offsets the
crank from the axle so joint-fit fails. ``--no-dip`` raises the stone
clear of the trough so the seat-conformance dip band fails.
``--short-legs`` raises the iron shoes and plants a dummy so the named
support budget fails while AABB zmin still passes. ``--float-legs``
lifts the A-frame timber off the shoes so the shoe-wood join fails.
``--narrow-trough`` shrinks the tub so it no longer seats in the sills.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python grindstone.py --
    blender --background --python grindstone.py -- --skip-decimate
    blender --background --python grindstone.py -- --output grindstone.png
"""
import argparse
import math
import os
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

STONE_R = 0.250
STONE_T = 0.095
STONE_SEGS = 32
CHAMFER = 0.012
TROUGH_H = 0.080
TROUGH_WALL = 0.018
DIP = 0.028
HUB_R = 0.048
HUB_T = 0.022
HUB_SEAT = 0.004
FRAME_Y = STONE_T / 2.0 + HUB_T + 0.055
LEG_SPREAD = 0.32
LEG_XY = (0.044, 0.044)
# Sill and king are fatter in Y than the diagonals so the braces
# tenon *into* the frame. Matching Y-thickness puts coplanar faces
# on the camera side and reads as a black hole in the timber.
SILL_Y = 0.070
KING_Y = 0.054
# Seat the tub into the sill inner faces. Deriving from LEG_XY left a
# daylight slot once the sill was fattened to nest the diagonals.
TROUGH_SEAT = 0.012
TROUGH_W = 2.0 * (FRAME_Y - SILL_Y / 2.0 + TROUGH_SEAT)
TROUGH_L = 2.0 * (LEG_SPREAD - 0.010)
TROUGH_Z0 = 0.058
AXLE_R = 0.014
AXLE_OVER = 0.055
CRANK_ARM = 0.13
HANDLE_L = 0.11
SHOE_H = 0.024
SHOE_XY = (0.070, 0.070)

BBOX_TOL = 0.015
OUTER_SIZE = (0.710, 0.419, 0.610)
STONE_DIA = 2.0 * STONE_R
STONE_DIA_TOL = 0.02
STONE_T_TOL = 0.015
BASE_TRIS_MIN = 700
BASE_TRIS_MAX = 1000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 240
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
METAL_FACES_MIN = 80
WOOD_FACES_MIN = 80
STONE_FACES_MIN = 80
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.999
LIFT_Z = 0.05
CRANK_JOIN = 0.008
SHOE_JOIN = 0.008
TROUGH_SILL_JOIN = 0.008
DIP_MIN = 0.015
DIP_MAX = 0.045
SHOE_Z_MAX = 1e-3
TROUGH_FLOOR_Z_MIN = 0.040

WOOD_IDX = 0
STONE_IDX = 1
METAL_IDX = 2


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


def add_basin(bm, loc, size, wall, mat_idx):
    """One manifold open tub. Five overlapping boxes bevel into degenerates."""
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = list(geo["verts"])
    origin = Vector(loc)
    sx, sy, sz = size
    for v in verts:
        v.co = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz)) + origin
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    top = max(faces, key=lambda f: f.calc_center_median().z)
    bmesh.ops.inset_region(
        bm,
        faces=[top],
        thickness=wall,
        depth=-(sz - wall),
        use_boundary=True,
        use_even_offset=True,
    )
    for f in {f for v in verts for f in v.link_faces}:
        f.material_index = mat_idx
    seen = set(verts)
    stack = list(verts)
    while stack:
        v = stack.pop()
        for e in v.link_edges:
            o = e.other_vert(v)
            if o not in seen:
                seen.add(o)
                stack.append(o)
    return list(seen)


def add_stone(bm, loc, axle_z):
    """Ring-stack wheel: slight face inset so the rim reads thick, tris caps."""
    hw = STONE_T / 2.0
    rings_yz = [
        (-hw, STONE_R * 0.97),
        (-hw + CHAMFER, STONE_R),
        (hw - CHAMFER, STONE_R),
        (hw, STONE_R * 0.97),
    ]
    rings = []
    for y_off, radius in rings_yz:
        ring = []
        for i in range(STONE_SEGS):
            a = 2.0 * math.pi * i / STONE_SEGS
            ring.append(
                bm.verts.new(
                    (
                        loc[0] + radius * math.cos(a),
                        loc[1] + y_off,
                        axle_z + radius * math.sin(a),
                    )
                )
            )
        rings.append(ring)
    for i in range(len(rings) - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(STONE_SEGS):
            kn = (k + 1) % STONE_SEGS
            face = bm.faces.new((a[k], a[kn], b[kn], b[k]))
            face.material_index = STONE_IDX
    for ring, y_off, inward in (
        (rings[0], rings_yz[0][0], True),
        (rings[-1], rings_yz[-1][0], False),
    ):
        c = bm.verts.new((loc[0], loc[1] + y_off, axle_z))
        for k in range(STONE_SEGS):
            kn = (k + 1) % STONE_SEGS
            if inward:
                face = bm.faces.new((c, ring[kn], ring[k]))
            else:
                face = bm.faces.new((c, ring[k], ring[kn]))
            face.material_index = STONE_IDX
    return [v for ring in rings for v in ring]


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


def build_grindstone_mesh(
    name, bevel_offset, bevel_segments,
    float_crank=False, no_dip=False, short_legs=False, float_legs=False,
    narrow_trough=False,
):
    bm = bmesh.new()
    try:
        wood = []
        metal = []
        dip = DIP
        tub_z0 = TROUGH_Z0 - (0.040 if no_dip else 0.0)
        trough_top = TROUGH_Z0 + TROUGH_H
        stone_bottom = trough_top - dip
        axle_z = STONE_R + stone_bottom
        axle_len = 2.0 * FRAME_Y + 2.0 * AXLE_OVER
        axle_end = axle_len / 2.0
        # Inward, not proud: an outward offset grows the Y AABB and
        # trips exit 8 before the crank-join budget.
        crank_y = axle_end - (0.022 if float_crank else 0.012)
        shoe_z = 0.05 if short_legs else 0.0
        bearing_h = 0.090
        bearing_xz = (0.078, bearing_h)
        king_xy = (0.052, KING_Y)
        # Diagonals *are* the legs. A tall stump beside an angled timber
        # paints a see-through triangle on the stump face. Bury a short
        # tenon in the shoe (never proud of the iron) and start the
        # diagonal on the shoe top so the angled end-cap cannot pierce
        # Z=0.
        tenon_z = shoe_z + SHOE_H * 0.50
        diag_z = shoe_z + SHOE_H + 0.008
        if float_legs:
            tenon_z = shoe_z + SHOE_H + 0.070
            diag_z = shoe_z + SHOE_H + 0.070
        sill_h = 0.050
        sill_bottom = (
            shoe_z + SHOE_H + 0.055 if float_legs else shoe_z + SHOE_H * 0.40
        )
        sill_z = sill_bottom + sill_h / 2.0

        for y in (-FRAME_Y, FRAME_Y):
            # King post fills the A-crotch so the bearing is not a cube
            # perched on two sticks with a triangular hole under it.
            wood.extend(
                add_oriented_box(
                    bm,
                    (0.0, y, sill_z),
                    (0.0, y, axle_z + bearing_h * 0.35),
                    king_xy,
                    WOOD_IDX,
                )
            )
            wood.extend(
                add_box(
                    bm,
                    (0.0, y, axle_z),
                    (bearing_xz[0], 0.058, bearing_xz[1]),
                    WOOD_IDX,
                )
            )
            # Tie beam sits on the shoes and occupies the A-foot.
            wood.extend(
                add_box(
                    bm,
                    (0.0, y, sill_z),
                    (LEG_SPREAD * 2.0 + SHOE_XY[0], SILL_Y, sill_h),
                    WOOD_IDX,
                )
            )
            for x in (-LEG_SPREAD, LEG_SPREAD):
                if not float_legs:
                    wood.extend(
                        add_box(
                            bm,
                            (x, y, tenon_z),
                            (LEG_XY[0] * 0.92, LEG_XY[1] * 0.92, SHOE_H * 0.90),
                            WOOD_IDX,
                        )
                    )
                wood.extend(
                    add_oriented_box(
                        bm,
                        (x, y, diag_z),
                        (0.0, y, axle_z - 0.010),
                        LEG_XY,
                        WOOD_IDX,
                    )
                )
                metal.extend(
                    add_box(
                        bm,
                        (x, y, shoe_z + SHOE_H / 2.0),
                        (SHOE_XY[0], SHOE_XY[1], SHOE_H),
                        METAL_IDX,
                    )
                )

        for x in (-LEG_SPREAD, LEG_SPREAD):
            # End stretchers tenon through both sills at sill height.
            # A higher independent Z left them floating as extra cubes.
            wood.extend(
                add_box(
                    bm,
                    (x, 0.0, sill_z),
                    (0.038, FRAME_Y * 2.0, sill_h * 0.70),
                    WOOD_IDX,
                )
            )

        tw = TROUGH_W * (0.58 if narrow_trough else 1.0)
        chamfer = []
        basin_verts = add_basin(
            bm,
            (0.0, 0.0, tub_z0 + TROUGH_H / 2.0),
            (TROUGH_L, tw, TROUGH_H),
            TROUGH_WALL,
            WOOD_IDX,
        )
        chamfer.extend(basin_verts)

        chamfer.extend(
            add_cyl(
                bm,
                (0.0, crank_y + HANDLE_L * 0.15, axle_z + CRANK_ARM),
                0.016,
                HANDLE_L,
                10,
                WOOD_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )
        wood.extend(chamfer)

        add_stone(bm, (0.0, 0.0), axle_z)

        metal.extend(
            add_cyl(
                bm,
                (0.0, 0.0, axle_z),
                AXLE_R,
                axle_len,
                12,
                METAL_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )
        for ysign in (-1.0, 1.0):
            metal.extend(
                add_cyl(
                    bm,
                    (0.0, ysign * (STONE_T / 2.0 + HUB_T / 2.0 - HUB_SEAT), axle_z),
                    HUB_R,
                    HUB_T,
                    14,
                    METAL_IDX,
                    euler=(math.pi / 2.0, 0.0, 0.0),
                )
            )
        metal.extend(
            add_box(
                bm,
                (0.0, crank_y, axle_z + CRANK_ARM / 2.0),
                (0.018, 0.018, CRANK_ARM + 0.02),
                METAL_IDX,
            )
        )
        metal.extend(
            add_cyl(
                bm,
                (0.0, crank_y, axle_z + CRANK_ARM),
                0.010,
                HANDLE_L * 0.55,
                10,
                METAL_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )

        if short_legs:
            metal.extend(
                add_box(
                    bm,
                    (0.0, 0.0, 0.005),
                    (0.020, 0.020, 0.010),
                    METAL_IDX,
                )
            )

        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy

        if bevel_offset > 0.0:
            edges = []
            trough_verts = set(basin_verts)
            for e in {e for v in trough_verts for e in v.link_edges}:
                if min(v.co.z for v in e.verts) < tub_z0 - 0.002:
                    continue
                if any(f.material_index != WOOD_IDX for f in e.link_faces):
                    continue
                edges.append(e)
            if edges:
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

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        for poly in me.polygons:
            poly.use_smooth = False
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


def assign_slots(obj, wood, stone, metal):
    mats = obj.data.materials
    wanted = (wood, stone, metal)
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
    for p in me.polygons:
        if all(i in member for i in p.vertices):
            return p.material_index
    return None


def support_audit(me):
    groups = shells(me)
    shoes = []
    for g in groups:
        if mat_of(me, g) != METAL_IDX:
            continue
        a = shell_aabb(me, g)
        if a[5] < 0.08 and (a[4] - a[1]) > 0.04 and (a[3] - a[0]) > 0.04:
            shoes.append(a)
    shoe_z = min((a[2] for a in shoes), default=99.0)
    return {"shoes": len(shoes), "shoe_z": shoe_z}


def trough_floor_z(me):
    """Z of the wide shallow wood shell (the trough floor)."""
    groups = shells(me)
    best = 99.0
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if dx > TROUGH_L * 0.7 and dy > TROUGH_W * 0.55:
            best = min(best, a[2])
    return best


def stone_audit(me):
    stone_pts = []
    groups = shells(me)
    for g in groups:
        if mat_of(me, g) != STONE_IDX:
            continue
        stone_pts.extend(me.vertices[i].co for i in g)
    if not stone_pts:
        return {
            "dia": 0.0, "thick": 0.0, "zmin": 99.0, "dip": -1.0, "trough_z": 99.0,
        }
    xs = [p.x for p in stone_pts]
    ys = [p.y for p in stone_pts]
    zs = [p.z for p in stone_pts]
    dia = max(max(xs) - min(xs), max(zs) - min(zs))
    thick = max(ys) - min(ys)
    zmin = min(zs)
    tb = None
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy = a[3] - a[0], a[4] - a[1]
        if abs(dx - TROUGH_L) < 0.08 and dy > 0.08 and a[2] < 0.15:
            tb = a
            break
    trough_z = tb[2] if tb else trough_floor_z(me)
    trough_top = tb[5] if tb else (TROUGH_Z0 + TROUGH_H)
    return {
        "dia": dia,
        "thick": thick,
        "zmin": zmin,
        "dip": trough_top - zmin,
        "trough_z": trough_z,
    }


def crank_join(me):
    """Gap from crank-arm verts to the axle shell."""
    groups = shells(me)
    axle = None
    crank = None
    for g in groups:
        if mat_of(me, g) != METAL_IDX:
            continue
        a = shell_aabb(me, g)
        dy, dx, dz = a[4] - a[1], a[3] - a[0], a[5] - a[2]
        if dy > 0.30 and dx < 0.06 and dz < 0.06:
            axle = g
        if dz > CRANK_ARM * 0.6 and dy < 0.05 and dx < 0.05:
            crank = g
    if axle is None or crank is None:
        return 99.0
    axle_pts = [me.vertices[i].co for i in axle]
    crank_pts = [me.vertices[i].co for i in crank]
    best = 99.0
    for c in crank_pts:
        d = min((c - a).length for a in axle_pts)
        if d < best:
            best = d
    return best


def trough_sill_gap(me):
    """Daylight in Y between the trough and each A-frame sill.

    Per-side, not a mixed max. The crank handle makes the mesh AABB
    asymmetric, so a global |ymin|/ymax vs min(sill inner) compares the
    trough's long side against the opposite sill and reports overlap
    while the other side shows daylight.
    Overlap on a side is 0. Missing shells return 99.
    """
    groups = shells(me)
    trough = None
    plus_sill = None
    minus_sill = None
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        cy = 0.5 * (a[1] + a[4])
        if abs(dx - TROUGH_L) < 0.08 and dy > 0.08 and a[2] < 0.15:
            trough = a
        if (
            dx > LEG_SPREAD * 1.2
            and dy > SILL_Y * 0.55
            and abs(cy) > FRAME_Y * 0.40
            and a[5] < 0.14
        ):
            if cy > 0.0:
                plus_sill = a
            else:
                minus_sill = a
    if trough is None or plus_sill is None or minus_sill is None:
        return 99.0
    gap_plus = plus_sill[1] - trough[4]
    gap_minus = trough[1] - minus_sill[4]
    return max(0.0, gap_plus, gap_minus)


def shoe_wood_gap(me):
    """Worst gap from an iron shoe to wood.

    Overlapping solids count as 0. Vert-vert and shoe-corner-to-surface
    both lie about a shoe-width away even when a tenon is buried in the
    iron; overlap is the join.
    """
    groups = shells(me)
    shoes = []
    for g in groups:
        if mat_of(me, g) != METAL_IDX:
            continue
        a = shell_aabb(me, g)
        if a[5] < 0.08 and (a[4] - a[1]) > 0.04 and (a[3] - a[0]) > 0.04:
            shoes.append(g)
    if not shoes:
        return 99.0
    bm_wood = bmesh.new()
    try:
        bm_wood.from_mesh(me)
        drop = [f for f in bm_wood.faces if f.material_index != WOOD_IDX]
        if drop:
            bmesh.ops.delete(bm_wood, geom=drop, context="FACES")
        if not bm_wood.faces:
            return 99.0
        tree_wood = BVHTree.FromBMesh(bm_wood)
        worst = 0.0
        for g in shoes:
            bm_s = bmesh.new()
            try:
                bm_s.from_mesh(me)
                member = set(g)
                drop_s = [
                    f for f in bm_s.faces
                    if not all(v.index in member for v in f.verts)
                ]
                if drop_s:
                    bmesh.ops.delete(bm_s, geom=drop_s, context="FACES")
                if not bm_s.faces:
                    worst = max(worst, 99.0)
                    continue
                tree_s = BVHTree.FromBMesh(bm_s)
                if tree_wood.overlap(tree_s):
                    continue
                best = 99.0
                for i in g:
                    hit = tree_wood.find_nearest(me.vertices[i].co)
                    if hit[0] is None:
                        continue
                    best = min(best, hit[3])
                if best > worst:
                    worst = best
            finally:
                bm_s.free()
        return worst
    finally:
        bm_wood.free()


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, STONE_R))
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


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("GrindstoneNrm", size, size, alpha=True, float_buffer=False)
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


def check(
    skip_decimate, lift_z=False, stray_vert=False,
    float_crank=False, no_dip=False, short_legs=False, float_legs=False,
    narrow_trough=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        float_crank=float_crank, no_dip=no_dip,
        short_legs=short_legs, float_legs=float_legs,
        narrow_trough=narrow_trough,
    )
    low = build_grindstone_mesh("GrindstoneLow", 0.004, 2, **flags)
    high = build_grindstone_mesh("GrindstoneHigh", 0.004, 4, **flags)
    wood = principled(
        "GrindstoneWood", (0.38, 0.20, 0.08, 1.0), 0.0, 0.62,
        noise_scale=6.5, wear=(0.22, 0.11, 0.04, 1.0),
    )
    stone = principled(
        "GrindstoneStone", (0.40, 0.36, 0.30, 1.0), 0.0, 0.92,
        noise_scale=14.0, wear=(0.28, 0.24, 0.18, 1.0),
    )
    metal = principled(
        "GrindstoneIron", (0.14, 0.145, 0.155, 1.0), 1.0, 0.38,
        noise_scale=5.0, wear=(0.05, 0.05, 0.06, 1.0),
    )
    assign_slots(low, wood, stone, metal)
    assign_slots(high, wood, stone, metal)
    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("grindstone mesh did not build", 3), None, None, None, None, None

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

    img, tex = setup_bake_image(low, stone)
    if img is None:
        return fail("grindstone has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "GrindstoneLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "GrindstoneLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_grindstone_mesh("GrindstoneColSrc", 0.0, 1, **flags)
    collider = convex_hull_collider(collider_src, "GrindstoneCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_grindstone_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    sup = support_audit(low.data)
    st = stone_audit(low.data)
    cj = crank_join(low.data)
    sw = shoe_wood_gap(low.data)
    ts = trough_sill_gap(low.data)

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
        f"measured supports shoes={sup['shoes']} shoe_z={sup['shoe_z']:.5f} "
        f"stone_dia={st['dia']:.4f} stone_t={st['thick']:.4f} "
        f"dip={st['dip']:.5f} trough_z={st['trough_z']:.5f} "
        f"crank_join={cj:.5f} shoe_wood={sw:.5f} trough_sill={ts:.5f}"
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
    if idx_counts.get(STONE_IDX, 0) < STONE_FACES_MIN:
        return fail(
            f"stone faces {idx_counts.get(STONE_IDX, 0)} < {STONE_FACES_MIN}",
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
        hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"]
        or hyg["zero_area"] or hyg["doubles"] or hyg["ngons"] or zf
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}",
            15,
        ), None, None, None, None, None
    if abs(bb[2]) > ZMIN_EPS:
        return fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ), None, None, None, None, None
    if sup["shoes"] < 4 or sup["shoe_z"] > SHOE_Z_MAX:
        return fail(
            f"shoe supports {sup['shoes']} shoe_z={sup['shoe_z']:.5f} "
            "(--short-legs is the designed fail)",
            16,
        ), None, None, None, None, None
    if cj > CRANK_JOIN:
        return fail(
            f"crank-axle gap {cj:.5f} > {CRANK_JOIN} "
            "(--float-crank is the designed fail)",
            17,
        ), None, None, None, None, None
    if sw > SHOE_JOIN:
        return fail(
            f"shoe-wood gap {sw:.5f} > {SHOE_JOIN} "
            "(--float-legs is the designed fail)",
            17,
        ), None, None, None, None, None
    if ts > TROUGH_SILL_JOIN:
        return fail(
            f"trough-sill gap {ts:.5f} > {TROUGH_SILL_JOIN} "
            "(--narrow-trough is the designed fail)",
            18,
        ), None, None, None, None, None
    if not (DIP_MIN <= st["dip"] <= DIP_MAX):
        return fail(
            f"stone dip {st['dip']:.5f} not in [{DIP_MIN}, {DIP_MAX}] "
            "(--no-dip is the designed fail)",
            18,
        ), None, None, None, None, None
    if st["trough_z"] < TROUGH_FLOOR_Z_MIN:
        return fail(
            f"trough floor zmin {st['trough_z']:.5f} < {TROUGH_FLOOR_Z_MIN} "
            "(tub must sit on the frame, not the dirt)",
            18,
        ), None, None, None, None, None
    if abs(st["dia"] - STONE_DIA) > STONE_DIA_TOL:
        return fail(
            f"stone diameter {st['dia']:.4f} off {STONE_DIA}",
            19,
        ), None, None, None, None, None
    if abs(st["thick"] - STONE_T) > STONE_T_TOL:
        return fail(
            f"stone thickness {st['thick']:.4f} off {STONE_T}",
            19,
        ), None, None, None, None, None
    return 0, low, high, stone, tex, collider


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

    low.rotation_euler.z = math.radians(-22.0)
    low.rotation_euler.x = math.radians(0.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=14.0)
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

    light("Key", (-3.6, -5.0, 5.4), 660.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.4, 2.4), 46.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.2, 4.0, 3.8), 600.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.55, -1.95, 0.92)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.32)
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
    p.add_argument("--skip-decimate", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--float-crank", action="store_true")
    p.add_argument("--no-dip", action="store_true")
    p.add_argument("--short-legs", action="store_true")
    p.add_argument("--float-legs", action="store_true")
    p.add_argument("--narrow-trough", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, hero_mat, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_crank=args.float_crank,
        no_dip=args.no_dip,
        short_legs=args.short_legs,
        float_legs=args.float_legs,
        narrow_trough=args.narrow_trough,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, hero_mat, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("grindstone OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
