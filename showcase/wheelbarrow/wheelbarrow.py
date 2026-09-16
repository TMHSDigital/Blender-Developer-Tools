"""Game-ready wooden wheelbarrow — a showcase piece, not an example.

Asserts budget conformance of a procedural wheelbarrow (two chassis
shafts, box tray, flat-tread spoked wheel, rear legs) after composing
shipped pipeline pieces: bmesh construction, UVs, two materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. ``--skip-decimate`` skips the LOD
DECIMATE stage so the LOD-ratio budget fails. ``--stray-vert`` adds a
loose vertex so the mesh-hygiene budget fails. ``--lift-z`` raises the
mesh so the grounded-zmin budget fails. ``--short-legs`` lifts only the
shoes so the named-support budget fails while the wheel still grounds
the AABB. ``--fat-spokes`` thickens the spokes to the hub diameter so
joint-fit fails. ``--pipe-rim`` swaps the flat felloe/tyre for a torus
so the tread-aspect seat budget fails. ``--float-walls`` lifts the
tray walls off the floor so the wall-floor seat budget fails.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python wheelbarrow.py --
    blender --background --python wheelbarrow.py -- --skip-decimate
    blender --background --python wheelbarrow.py -- --output barrow.png
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

# Wheel: flat-tread wooden felloe + iron tyre. Torus rims read as bicycle
# tyres; the cart pass already killed that class.
RIM_MAJOR = 0.170
RIM_RADIAL = 0.014
RIM_W = 0.042
TYRE_T = 0.007
TYRE_BITE = 0.002
TYRE_W = 0.046
HUB_R = 0.032
HUB_W = 0.044
N_SPOKES = 8
SPOKE_T = 0.014
WHEEL_X = 0.58
WHEEL_Z = RIM_MAJOR + RIM_RADIAL + TYRE_T
RIM_MINOR_PIPE = 0.020

# Chassis shafts are the handles. They run under the tray, then converge
# into forks at the axle. Tray, legs, and wheel all hang off this frame.
SHAFT_Y = 0.255
SHAFT_W = 0.036
SHAFT_H = 0.044
SHAFT_Z = 0.280
HANDLE_X = -0.78
HANDLE_Z = 0.56
TRAY_X0 = -0.32
TRAY_X1 = 0.40
TRAY_L = TRAY_X1 - TRAY_X0
TRAY_W = 2.0 * SHAFT_Y
FLOOR_T = 0.022
N_FLOOR = 5
# Negative: slats overlap so the wood bevel cannot open daylight
# through the tray floor.
SLAT_GAP = -0.003
WALL_H = 0.22
WALL_T = 0.022
WALL_SEAT = 0.012
HANDLE_SEAT = 0.055
FRONT_H = 0.26
REAR_H = 0.10
FORK_Y = HUB_W / 2.0 + 0.016
LEG_X = -0.06
SHOE_H = 0.024
SHOE_XY = (0.058, 0.050)

BBOX_TOL = 0.015
OUTER_SIZE = (1.558, 0.630, 0.574)
TRAY_SIZE = (0.720, 0.532, 0.220)
TRAY_SIZE_TOL = (0.02, 0.02, 0.02)
BASE_TRIS_MIN = 2300
BASE_TRIS_MAX = 2800
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
METAL_FACES_MIN = 180
WOOD_FACES_MIN = 700
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.999
LIFT_Z = 0.05
GAP_MAX = 0.010
SPOKE_CLEAR_MIN = 0.010
TREAD_ASPECT_MIN = 2.5
HANDLE_JOIN = 0.020
WALL_SEAT_MIN = 0.005
SHOE_Z_MAX = 1e-3

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


def add_ring(bm, loc, r_mid, radial_t, width, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    """Flat-sided ring (felloe / tyre). Quads only; box cross-section."""
    r_in = r_mid - radial_t
    r_out = r_mid + radial_t
    hw = width / 2.0
    rings = []
    for i in range(segments):
        u = i * (2.0 * math.pi / segments)
        cu = math.cos(u)
        su = math.sin(u)
        rings.append(
            [
                bm.verts.new((r_in * cu, r_in * su, -hw)),
                bm.verts.new((r_out * cu, r_out * su, -hw)),
                bm.verts.new((r_out * cu, r_out * su, hw)),
                bm.verts.new((r_in * cu, r_in * su, hw)),
            ]
        )
    for i in range(segments):
        i2 = (i + 1) % segments
        a = rings[i]
        b = rings[i2]
        for quad in (
            (a[1], b[1], b[2], a[2]),
            (a[3], b[3], b[0], a[0]),
            (a[2], b[2], b[3], a[3]),
            (a[0], b[0], b[1], a[1]),
        ):
            face = bm.faces.new(quad)
            face.material_index = mat_idx
    verts = [v for ring in rings for v in ring]
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    return verts


def add_rim(bm, loc, major, minor, mat_idx, euler=(0.0, 0.0, 0.0)):
    """Torus rim — used only by the --pipe-rim falsifier."""
    n_major = 16
    n_minor = 8
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


def add_wheel(bm, loc, wood, metal, pipe_rim, spoke_t):
    if pipe_rim:
        # Metal is the outer tyre so named-support zmin stays 0 and the
        # falsifier can reach the tread-aspect gate (exit 18). An inner
        # metal torus floats and trips exit 16 first.
        wood.extend(
            add_rim(
                bm, loc, RIM_MAJOR, RIM_MINOR_PIPE * 0.45, WOOD_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )
        metal.extend(
            add_rim(
                bm, loc, RIM_MAJOR + 0.004, RIM_MINOR_PIPE, METAL_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )
    else:
        wood.extend(
            add_ring(
                bm, loc, RIM_MAJOR, RIM_RADIAL, RIM_W, 16, WOOD_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )
        metal.extend(
            add_ring(
                bm, loc,
                RIM_MAJOR + RIM_RADIAL + TYRE_T / 2.0 - TYRE_BITE / 2.0,
                TYRE_T / 2.0 + TYRE_BITE / 2.0,
                TYRE_W, 16, METAL_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )
    wood.extend(
        add_cyl(
            bm, loc, HUB_R, HUB_W, 12, WOOD_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
    )
    inner = HUB_R * 0.4
    outer = RIM_MAJOR - RIM_RADIAL + 0.008
    mid_r = 0.5 * (inner + outer)
    slen = outer - inner
    for i in range(N_SPOKES):
        a = i * (2.0 * math.pi / N_SPOKES)
        dx = math.cos(a)
        dz = math.sin(a)
        cx = loc[0] + dx * mid_r
        cy = loc[1]
        cz = loc[2] + dz * mid_r
        wood.extend(
            add_box(
                bm, (cx, cy, cz), (slen, spoke_t * 0.85, spoke_t), WOOD_IDX,
                euler=(0.0, -a, 0.0),
            )
        )
    metal.extend(
        add_cyl(
            bm, loc, HUB_R + 0.010, 0.016, 12, METAL_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
    )
    metal.extend(
        add_cyl(
            bm, loc, 0.014, FORK_Y * 2.0 + 0.04, 10, METAL_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
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


def build_barrow_mesh(
    name, bevel_offset, bevel_segments,
    pipe_rim=False, fat_spokes=False, short_legs=False, float_walls=False,
):
    bm = bmesh.new()
    try:
        body = []
        metal = []
        spoke_t = HUB_R * 2.2 if fat_spokes else SPOKE_T
        shoe_z = 0.05 if short_legs else 0.0
        shoe_top = shoe_z + SHOE_H
        floor_z = SHAFT_Z + SHAFT_H / 2.0 + FLOOR_T / 2.0
        floor_top = SHAFT_Z + SHAFT_H / 2.0 + FLOOR_T
        seat = -0.003 if float_walls else WALL_SEAT
        wall_z = floor_top - seat + WALL_H / 2.0
        front_z = floor_top - seat + FRONT_H / 2.0
        rear_z = floor_top - seat + REAR_H / 2.0

        for ysign in (-1.0, 1.0):
            y = ysign * SHAFT_Y
            fy = ysign * FORK_Y
            body.extend(
                add_oriented_box(
                    bm,
                    (HANDLE_X, y, HANDLE_Z),
                    (TRAY_X0 + HANDLE_SEAT, y, SHAFT_Z),
                    (SHAFT_W - 0.010, SHAFT_H - 0.010),
                    WOOD_IDX,
                )
            )
            body.extend(
                add_oriented_box(
                    bm,
                    (TRAY_X0, y, SHAFT_Z),
                    (TRAY_X1, y, SHAFT_Z),
                    (SHAFT_W, SHAFT_H),
                    WOOD_IDX,
                )
            )
            body.extend(
                add_oriented_box(
                    bm,
                    (TRAY_X1, y, SHAFT_Z),
                    (WHEEL_X, fy, WHEEL_Z),
                    (SHAFT_W, SHAFT_H),
                    WOOD_IDX,
                )
            )
            body.extend(
                add_oriented_box(
                    bm,
                    (LEG_X, y, SHAFT_Z),
                    (LEG_X + 0.02, ysign * (SHAFT_Y + 0.035), shoe_top),
                    (0.034, 0.034),
                    WOOD_IDX,
                )
            )
            metal.extend(
                add_box(
                    bm,
                    (LEG_X + 0.02, ysign * (SHAFT_Y + 0.035), shoe_z + SHOE_H / 2.0),
                    (SHOE_XY[0], SHOE_XY[1], SHOE_H),
                    METAL_IDX,
                )
            )
            metal.extend(
                add_box(
                    bm,
                    (WHEEL_X, ysign * (FORK_Y - SHAFT_W / 2.0 - 0.005), WHEEL_Z),
                    (0.040, 0.008, 0.040),
                    METAL_IDX,
                )
            )

        body.extend(
            add_oriented_box(
                bm,
                (LEG_X, -SHAFT_Y, 0.12),
                (LEG_X, SHAFT_Y, 0.12),
                (0.028, 0.028),
                WOOD_IDX,
            )
        )
        body.extend(
            add_oriented_box(
                bm,
                (TRAY_X1 + 0.04, -FORK_Y, WHEEL_Z + 0.02),
                (TRAY_X1 + 0.04, FORK_Y, WHEEL_Z + 0.02),
                (0.024, 0.024),
                WOOD_IDX,
            )
        )

        slat_span = TRAY_L
        slat_w = (slat_span - (N_FLOOR - 1) * SLAT_GAP) / N_FLOOR
        # Slats run under the side walls; walls sit on the floor, not
        # beside a through-gap at the inner arris.
        slat_y = TRAY_W + WALL_T
        for i in range(N_FLOOR):
            x = TRAY_X0 + slat_w / 2.0 + i * (slat_w + SLAT_GAP)
            body.extend(
                add_box(
                    bm,
                    (x, 0.0, floor_z),
                    (slat_w, slat_y, FLOOR_T),
                    WOOD_IDX,
                )
            )
        for ysign in (-1.0, 1.0):
            body.extend(
                add_box(
                    bm,
                    (0.5 * (TRAY_X0 + TRAY_X1), ysign * (TRAY_W / 2.0), wall_z),
                    (TRAY_L, WALL_T, WALL_H),
                    WOOD_IDX,
                )
            )
        body.extend(
            add_box(
                bm,
                (TRAY_X1, 0.0, front_z),
                (WALL_T, TRAY_W + WALL_T, FRONT_H),
                WOOD_IDX,
            )
        )
        body.extend(
            add_box(
                bm,
                (TRAY_X0, 0.0, rear_z),
                (WALL_T, TRAY_W + WALL_T, REAR_H),
                WOOD_IDX,
            )
        )

        strap_r_y = TRAY_W / 2.0 + WALL_T / 2.0 + 0.004
        for sx in (TRAY_X0 + TRAY_L * 0.28, TRAY_X0 + TRAY_L * 0.72):
            z0 = SHAFT_Z + SHAFT_H / 2.0
            z1 = z0 + FLOOR_T + WALL_H
            for ysign in (-1.0, 1.0):
                metal.extend(
                    add_oriented_box(
                        bm,
                        (sx, ysign * strap_r_y, z0),
                        (sx, ysign * strap_r_y, z1),
                        (0.018, 0.008),
                        METAL_IDX,
                    )
                )
            metal.extend(
                add_oriented_box(
                    bm,
                    (sx, -strap_r_y, z0),
                    (sx, strap_r_y, z0),
                    (0.018, 0.008),
                    METAL_IDX,
                )
            )

        if bevel_offset > 0.0:
            edges = []
            for e in {e for v in body for e in v.link_edges}:
                if min(v.co.z for v in e.verts) < shoe_top + 0.008:
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

        wood_wheel = []
        wheel_z = (
            RIM_MAJOR + 0.004 + RIM_MINOR_PIPE if pipe_rim else WHEEL_Z
        )
        add_wheel(
            bm, (WHEEL_X, 0.0, wheel_z), wood_wheel, metal, pipe_rim, spoke_t
        )

        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy

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
    # Combinatorics match examples/mesh-hygiene-audit.audit (copied, not imported).
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


def zfight_pairs(me):
    """Disjoint faces sharing a plane and a position, which z-fight."""
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
        min(p.x for p in pts),
        min(p.y for p in pts),
        min(p.z for p in pts),
        max(p.x for p in pts),
        max(p.y for p in pts),
        max(p.z for p in pts),
    )


def support_audit(me):
    """Named supports must each sit on Z=0. AABB zmin is the lowest one."""
    groups = shells(me)
    metal_groups = []
    for g in groups:
        faces = [
            p for p in me.polygons if all(i in set(g) for i in p.vertices)
        ]
        if not faces:
            continue
        if faces[0].material_index != METAL_IDX:
            continue
        metal_groups.append(shell_aabb(me, g))
    shoes = [a for a in metal_groups if a[5] < 0.08 and (a[4] - a[1]) > 0.03]
    tyres = [
        a for a in metal_groups
        if (a[3] - a[0]) > 0.25 and (a[5] - a[2]) > 0.25
    ]
    shoe_z = min((a[2] for a in shoes), default=99.0)
    tyre_z = min((a[2] for a in tyres), default=99.0)
    return {
        "shoes": len(shoes),
        "tyres": len(tyres),
        "shoe_z": shoe_z,
        "tyre_z": tyre_z,
    }


def tray_size(me):
    """Side-wall pair: length, track, and height of the box they bound."""
    groups = shells(me)
    walls = []
    for g in groups:
        faces = [
            p for p in me.polygons if all(i in set(g) for i in p.vertices)
        ]
        if not faces or faces[0].material_index != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if abs(dx - TRAY_L) < 0.10 and dy < 0.06 and abs(dz - WALL_H) < 0.08:
            walls.append(a)
    if len(walls) < 2:
        return (0.0, 0.0, 0.0)
    left = min(walls, key=lambda a: a[1])
    right = max(walls, key=lambda a: a[1])
    return (
        0.5 * ((left[3] - left[0]) + (right[3] - right[0])),
        right[4] - left[1],
        0.5 * ((left[5] - left[2]) + (right[5] - right[2])),
    )


def wall_floor_seat(me):
    """How far the side walls drop into the floor shells, metres.

    Recomputed from AABBs. A wall that only kisses the floor top after
    a bevel reports ~0 and fails the seat floor.
    """
    groups = shells(me)
    floors = []
    walls = []
    for g in groups:
        faces = [
            p for p in me.polygons if all(i in set(g) for i in p.vertices)
        ]
        if not faces or faces[0].material_index != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if dz < FLOOR_T * 2.2 and dy > TRAY_W * 0.5:
            floors.append(a)
        if abs(dx - TRAY_L) < 0.10 and dy < WALL_T * 4.0 and abs(dz - WALL_H) < 0.08:
            walls.append(a)
    if not floors or not walls:
        return -1.0
    floor_top = max(a[5] for a in floors)
    wall_bot = min(a[2] for a in walls)
    return floor_top - wall_bot


def handle_join_gap(me):
    """Daylight between the handle sticks and the tray rear.

    Handles are the wood shells whose xmax is behind the tray; the tray
    rear is the wood shell with the smallest xmax among tall-wide parts.
    """
    groups = shells(me)
    wood = []
    for g in groups:
        faces = [
            p for p in me.polygons if all(i in set(g) for i in p.vertices)
        ]
        if not faces or faces[0].material_index != WOOD_IDX:
            continue
        wood.append(shell_aabb(me, g))
    if not wood:
        return 99.0
    xmin = min(a[0] for a in wood)
    handles = [a for a in wood if a[0] < xmin + 0.08]
    trayish = [a for a in wood if (a[4] - a[1]) > TRAY_W * 0.6]
    if not handles or not trayish:
        return 99.0
    tray_x0 = min(a[0] for a in trayish)
    handle_x1 = max(a[3] for a in handles)
    return tray_x0 - handle_x1


def spoke_clearance(me):
    """Hub diameter minus fattest spoke thickness.

    Spokes are the wood shells around the wheel centroid. Floor slats
    also have a thin Z and a long X; matching on those dimensions
    reports a false clearance that ``--fat-spokes`` cannot violate.
    """
    groups = shells(me)
    hubs = []
    spoke_thick = []
    for g in groups:
        faces = [
            p for p in me.polygons if all(i in set(g) for i in p.vertices)
        ]
        if not faces or faces[0].material_index != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        cx = 0.5 * (a[0] + a[3])
        cz = 0.5 * (a[2] + a[5])
        if abs(cx - WHEEL_X) > RIM_MAJOR or abs(cz - WHEEL_Z) > RIM_MAJOR:
            continue
        if abs(dy - HUB_W) < 0.012 and max(dx, dz) < HUB_R * 2.4:
            hubs.append(a)
            continue
        if dx > RIM_MAJOR and dz > RIM_MAJOR:
            continue
        thick = min(dx, dy, dz)
        longest = max(dx, dy, dz)
        if longest > HUB_R * 2.0 and thick < HUB_R * 2.6:
            spoke_thick.append(thick)
    if not hubs:
        return -1.0
    hub = hubs[0]
    hub_d = max(hub[3] - hub[0], hub[5] - hub[2])
    if not spoke_thick:
        return hub_d
    return hub_d - max(spoke_thick)


def tread_aspect(me):
    """Tyre Y-width over radial thickness. Flat treads are wide; torii are not.

    Measured on the tyre shell's own verts, not on every vert in its AABB —
    the felloe and hub sit inside that box and would inflate the radial span.
    """
    groups = shells(me)
    best = None
    for g in groups:
        member = set(g)
        faces = [
            p for p in me.polygons if all(i in member for i in p.vertices)
        ]
        if not faces or faces[0].material_index != METAL_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if dx < 0.25 or dz < 0.25:
            continue
        cx = 0.5 * (a[0] + a[3])
        cz = 0.5 * (a[2] + a[5])
        rs = [
            math.hypot(me.vertices[i].co.x - cx, me.vertices[i].co.z - cz)
            for i in g
        ]
        radial = max(rs) - min(rs)
        if radial < 1e-6:
            continue
        aspect = dy / radial
        score = dx * dz
        if best is None or score > best[0]:
            best = (score, aspect)
    return best[1] if best else 0.0


def min_mat_distance(me, ia, ib):
    bm_a = bmesh.new()
    bm_b = bmesh.new()
    try:
        bm_a.from_mesh(me)
        bm_b.from_mesh(me)
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


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, SHAFT_Z))
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
    img = bpy.data.images.new("BarrowNrm", size, size, alpha=True, float_buffer=False)
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


def check(
    skip_decimate, lift_z=False, stray_vert=False,
    fat_spokes=False, pipe_rim=False, short_legs=False, float_walls=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        pipe_rim=pipe_rim, fat_spokes=fat_spokes,
        short_legs=short_legs, float_walls=float_walls,
    )
    low = build_barrow_mesh("BarrowLow", 0.004, 2, **flags)
    high = build_barrow_mesh("BarrowHigh", 0.004, 4, **flags)
    wood = principled(
        "BarrowWood", (0.40, 0.22, 0.09, 1.0), 0.0, 0.58,
        noise_scale=7.0, wear=(0.24, 0.12, 0.04, 1.0),
    )
    metal = principled(
        "BarrowIron", (0.11, 0.115, 0.13, 1.0), 1.0, 0.32,
        noise_scale=5.0, wear=(0.05, 0.05, 0.06, 1.0),
    )
    assign_slots(low, wood, metal)
    assign_slots(high, wood, metal)
    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("barrow mesh did not build", 3), None, None, None, None, None

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
        return fail("barrow has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BarrowLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BarrowLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_barrow_mesh("BarrowColSrc", 0.0, 1, **flags)
    collider = convex_hull_collider(collider_src, "BarrowCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_wheelbarrow_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    sup = support_audit(low.data)
    tsz = tray_size(low.data)
    hgap = handle_join_gap(low.data)
    sclear = spoke_clearance(low.data)
    aspect = tread_aspect(low.data)
    gap_mw = min_mat_distance(low.data, METAL_IDX, WOOD_IDX)
    seat = wall_floor_seat(low.data)

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
        f"tyres={sup['tyres']} tyre_z={sup['tyre_z']:.5f}"
    )
    print(
        f"measured tray=({tsz[0]:.4f},{tsz[1]:.4f},{tsz[2]:.4f}) "
        f"handle_gap={hgap:.5f} spoke_clear={sclear:.5f} "
        f"tread_aspect={aspect:.3f} gap_metal_wood={gap_mw:.5f} "
        f"wall_floor_seat={seat:.5f}"
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
        hyg["loose_v"]
        or hyg["loose_e"]
        or hyg["nonman"]
        or hyg["zero_area"]
        or hyg["doubles"]
        or hyg["ngons"]
        or zf
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
    if sup["shoes"] < 2 or sup["shoe_z"] > SHOE_Z_MAX:
        return fail(
            f"shoe supports {sup['shoes']} shoe_z={sup['shoe_z']:.5f} "
            "(--short-legs is the designed fail)",
            16,
        ), None, None, None, None, None
    if sup["tyres"] < 1 or sup["tyre_z"] > SHOE_Z_MAX:
        return fail(
            f"tyre supports {sup['tyres']} tyre_z={sup['tyre_z']:.5f}",
            16,
        ), None, None, None, None, None
    if sclear < SPOKE_CLEAR_MIN:
        return fail(
            f"spoke clearance {sclear:.5f} < {SPOKE_CLEAR_MIN} "
            "(--fat-spokes is the designed fail)",
            17,
        ), None, None, None, None, None
    if hgap > HANDLE_JOIN:
        return fail(
            f"handle-tray gap {hgap:.5f} > {HANDLE_JOIN}",
            17,
        ), None, None, None, None, None
    if seat < WALL_SEAT_MIN:
        return fail(
            f"wall-floor seat {seat:.5f} < {WALL_SEAT_MIN} "
            "(--float-walls is the designed fail)",
            17,
        ), None, None, None, None, None
    if gap_mw > GAP_MAX:
        return fail(
            f"metal-wood gap {gap_mw:.5f} > {GAP_MAX}",
            17,
        ), None, None, None, None, None
    if aspect < TREAD_ASPECT_MIN:
        return fail(
            f"tread aspect {aspect:.3f} < {TREAD_ASPECT_MIN} "
            "(--pipe-rim is the designed fail)",
            18,
        ), None, None, None, None, None
    if (
        abs(tsz[0] - TRAY_SIZE[0]) > TRAY_SIZE_TOL[0]
        or abs(tsz[1] - TRAY_SIZE[1]) > TRAY_SIZE_TOL[1]
        or abs(tsz[2] - TRAY_SIZE[2]) > TRAY_SIZE_TOL[2]
    ):
        return fail(
            f"tray size ({tsz[0]:.4f},{tsz[1]:.4f},{tsz[2]:.4f}) "
            f"off declared {TRAY_SIZE}",
            19,
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

    low.rotation_euler.z = math.radians(-32.0)
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
    cam.location = (1.95, -2.35, 1.18)
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
        "--stray-vert",
        action="store_true",
        help="falsification: add a loose vertex so the hygiene budget fails",
    )
    p.add_argument(
        "--fat-spokes",
        action="store_true",
        help="falsification: spokes as thick as the hub, failing joint fit",
    )
    p.add_argument(
        "--pipe-rim",
        action="store_true",
        help="falsification: torus tyre on a flat felloe, failing tread aspect",
    )
    p.add_argument(
        "--short-legs",
        action="store_true",
        help="falsification: shoes float while the wheel still grounds the AABB",
    )
    p.add_argument(
        "--float-walls",
        action="store_true",
        help="falsification: walls kiss the floor so the seat budget fails",
    )
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        fat_spokes=args.fat_spokes,
        pipe_rim=args.pipe_rim,
        short_legs=args.short_legs,
        float_walls=args.float_walls,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("wheelbarrow OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
