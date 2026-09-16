"""Game-ready shipping crate — a showcase piece, not an example.

Asserts budget conformance of a procedural crate (skids, corner posts,
tenoned slats with seeded width jitter, L-straps, iron bail handles)
after composing shipped pipeline pieces: bmesh construction, UVs, two
materials, high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

The old piece was a solid beveled cube with identical slats glued on
and three overlapping cubes per corner that left window-holes through
the iron.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-skids`` named skid
supports, ``--float-handle`` handle-to-end joint-fit, ``--omit-slats``
slat-to-post seat.

Fixed seed 17 for slat-width jitter. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python shipping_crate.py --
    blender --background --python shipping_crate.py -- --skip-decimate
    blender --background --python shipping_crate.py -- --output crate.png
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
from mathutils import Vector
from mathutils.bvhtree import BVHTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

# A chest-sized shipping crate, ~96 × 62 × 58 cm inner, sitting on
# three skids. Outer AABB includes the proud L-straps and handles.
INNER = (0.96, 0.62, 0.52)
POST = 0.048
SKID_H = 0.036
SKID_W = 0.058
SLAT_T = 0.016
RAIL_H = 0.040
TENON = 0.010
IRON_T = 0.004
IRON_WRAP = 0.072
HANDLE_OUT = 0.038
HANDLE_R = 0.007
N_FLOOR = 6
N_LID = 6
N_LONG = 5
N_END = 4
SLAT_SEED = 17
SLAT_JITTER = 0.045

BBOX_TOL = 0.015
OUTER_SIZE = (1.146, 0.726, 0.612)
BODY_X, BODY_Y, BODY_Z = 1.056, 0.716, 0.576
BODY_TOL = 0.05

BASE_TRIS_MIN = 1200
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
METAL_FACES_MIN = 48
WOOD_FACES_MIN = 200
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.999
LIFT_Z = 0.05
SKID_Z_MAX = 1e-3
HANDLE_JOIN = 0.008
SLAT_JOIN = 0.006

WOOD_IDX = 0
METAL_IDX = 1


def eevee_engine_id():
    return "BLENDER_EEVEE_NEXT" if bpy.app.version >= (4, 2, 0) else "BLENDER_EEVEE"


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


def add_box(bm, loc, scale, mat_idx):
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = geo["verts"]
    for v in verts:
        v.co.x = v.co.x * scale[0] + loc[0]
        v.co.y = v.co.y * scale[1] + loc[1]
        v.co.z = v.co.z * scale[2] + loc[2]
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


def _bridge_rings(bm, a, b, mat_idx):
    segs = len(a)
    for k in range(segs):
        kn = (k + 1) % segs
        face = bm.faces.new((a[k], a[kn], b[kn], b[k]))
        face.material_index = mat_idx


def loft_rings(bm, rings, mat_idx, cap_start=True, cap_end=True):
    verts = [v for ring in rings for v in ring]
    n = len(rings)
    for i in range(n - 1):
        _bridge_rings(bm, rings[i], rings[i + 1], mat_idx)
    if cap_start and len(rings[0]) > 1:
        ring = rings[0]
        c = bm.verts.new(sum((v.co for v in ring), Vector((0, 0, 0))) / len(ring))
        verts.append(c)
        for k in range(len(ring)):
            kn = (k + 1) % len(ring)
            face = bm.faces.new((c, ring[kn], ring[k]))
            face.material_index = mat_idx
    if cap_end and len(rings[-1]) > 1:
        ring = rings[-1]
        c = bm.verts.new(sum((v.co for v in ring), Vector((0, 0, 0))) / len(ring))
        verts.append(c)
        for k in range(len(ring)):
            kn = (k + 1) % len(ring)
            face = bm.faces.new((c, ring[k], ring[kn]))
            face.material_index = mat_idx
    return verts


def add_pipe_curve(bm, points, radius, segs, mat_idx):
    rings = []
    n = len(points)
    for i, p in enumerate(points):
        p = Vector(p)
        if i < n - 1:
            tangent = (Vector(points[i + 1]) - p).normalized()
        else:
            tangent = (p - Vector(points[i - 1])).normalized()
        side = Vector((-tangent.y, tangent.x, 0.0))
        if side.length < 1e-6:
            side = Vector((1.0, 0.0, 0.0))
        else:
            side.normalize()
        up = tangent.cross(side).normalized()
        ring = []
        for k in range(segs):
            a = 2.0 * math.pi * k / segs
            ring.append(
                bm.verts.new(
                    p + side * (radius * math.cos(a)) + up * (radius * math.sin(a))
                )
            )
        rings.append(ring)
    return loft_rings(bm, rings, mat_idx, cap_start=True, cap_end=True)


def add_handle_bail(bm, x_in, x_out, y0, y1, z, radius, segs, mat_idx):
    """U-bail with quarter-circle corners so the loft stays on the tube.

    A four-point polyline puts a 90-degree tangent jump at each outer
    corner; the ring there orients to the next span and the bar sits on
    the mounting plate instead of entering it.
    """
    sign_x = 1.0 if x_out > x_in else -1.0
    sign_y = 1.0 if y1 > y0 else -1.0
    rad = min(0.014, abs(x_out - x_in) * 0.40, abs(y1 - y0) * 0.20)
    pts = [
        Vector((x_in, y0, z)),
        Vector((x_out - sign_x * rad, y0, z)),
    ]
    c1 = Vector((x_out - sign_x * rad, y0 + sign_y * rad, z))
    s1 = Vector((0.0, -sign_y * rad, 0.0))
    e1 = Vector((sign_x * rad, 0.0, 0.0))
    for i in range(1, 5):
        a = (math.pi / 2.0) * i / 4.0
        pts.append(c1 + s1 * math.cos(a) + e1 * math.sin(a))
    pts.append(Vector((x_out, y1 - sign_y * rad, z)))
    c2 = Vector((x_out - sign_x * rad, y1 - sign_y * rad, z))
    s2 = Vector((sign_x * rad, 0.0, 0.0))
    e2 = Vector((0.0, sign_y * rad, 0.0))
    for i in range(1, 5):
        a = (math.pi / 2.0) * i / 4.0
        pts.append(c2 + s2 * math.cos(a) + e2 * math.sin(a))
    pts.append(Vector((x_in, y1, z)))
    add_pipe_curve(bm, pts, radius, segs, mat_idx)


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


def _span_layout(count, span, rng):
    """Uneven slat widths that still fill `span` with named gaps."""
    raw = [1.0 + rng.uniform(-SLAT_JITTER, SLAT_JITTER) for _ in range(count)]
    s = sum(raw)
    gap = 0.010
    usable = span - gap * (count + 1)
    widths = [usable * r / s for r in raw]
    pos = -span / 2.0 + gap
    centres = []
    for w in widths:
        centres.append(pos + w / 2.0)
        pos += w + gap
    return centres, widths


def build_crate_mesh(
    name,
    short_skids=False,
    float_handle=False,
    omit_slats=False,
):
    ix, iy, iz = INNER
    hx = ix / 2.0 + POST / 2.0
    hy = iy / 2.0 + POST / 2.0
    post_h = iz + RAIL_H
    top_z = SKID_H + post_h
    rng = random.Random(SLAT_SEED)
    bm = bmesh.new()
    wood_verts = []
    try:
        skid_z0 = 0.055 if short_skids else 0.0
        if short_skids:
            geo = bmesh.ops.create_cube(bm, size=1.0)
            for v in geo["verts"]:
                v.co.x *= 0.024
                v.co.y *= 0.024
                v.co.z *= 0.006
                v.co.z += 0.003
            for f in {f for v in geo["verts"] for f in v.link_faces}:
                f.material_index = WOOD_IDX
        # Skids sit under the posts, not inset at the inner wall line —
        # that left a cave at the outer corner.
        skid_ys = (-hy, 0.0, hy)
        for sy in skid_ys:
            wood_verts.extend(
                add_box(
                    bm,
                    (0.0, sy, skid_z0 + SKID_H / 2.0),
                    (ix + 2.0 * POST, SKID_W, SKID_H),
                    WOOD_IDX,
                )
            )
        for sxn in (-1.0, 1.0):
            for syn in (-1.0, 1.0):
                wood_verts.extend(
                    add_box(
                        bm,
                        (sxn * hx, syn * hy, SKID_H - TENON + (post_h + TENON) / 2.0),
                        (POST, POST, post_h + TENON),
                        WOOD_IDX,
                    )
                )
        # Top rails tenon into the posts — overlapping, not sharing a plane.
        wood_verts.extend(
            add_box(
                bm, (0.0, hy, top_z - RAIL_H / 2.0),
                (ix + 2.0 * TENON, POST, RAIL_H), WOOD_IDX,
            )
        )
        wood_verts.extend(
            add_box(
                bm, (0.0, -hy, top_z - RAIL_H / 2.0),
                (ix + 2.0 * TENON, POST, RAIL_H), WOOD_IDX,
            )
        )
        wood_verts.extend(
            add_box(
                bm, (hx, 0.0, top_z - RAIL_H / 2.0),
                (POST, iy + 2.0 * TENON, RAIL_H), WOOD_IDX,
            )
        )
        wood_verts.extend(
            add_box(
                bm, (-hx, 0.0, top_z - RAIL_H / 2.0),
                (POST, iy + 2.0 * TENON, RAIL_H), WOOD_IDX,
            )
        )
        # Bottom sill tenons into the skid so the shared z=SKID_H plane
        # is not two coplanar faces (z-fight).
        sill_h = RAIL_H + TENON
        sill_z = SKID_H - TENON + sill_h / 2.0
        wood_verts.extend(
            add_box(
                bm, (0.0, hy, sill_z),
                (ix + 2.0 * TENON, POST, sill_h), WOOD_IDX,
            )
        )
        wood_verts.extend(
            add_box(
                bm, (0.0, -hy, sill_z),
                (ix + 2.0 * TENON, POST, sill_h), WOOD_IDX,
            )
        )
        wood_verts.extend(
            add_box(
                bm, (hx, 0.0, sill_z),
                (POST, iy + 2.0 * TENON, sill_h), WOOD_IDX,
            )
        )
        wood_verts.extend(
            add_box(
                bm, (-hx, 0.0, sill_z),
                (POST, iy + 2.0 * TENON, sill_h), WOOD_IDX,
            )
        )

        floor_c, floor_w = _span_layout(N_FLOOR, ix, rng)
        for c, w in zip(floor_c, floor_w):
            wood_verts.extend(
                add_box(
                    bm,
                    (c, 0.0, SKID_H + SLAT_T / 2.0),
                    (w, iy + TENON, SLAT_T),
                    WOOD_IDX,
                )
            )
        lid_c, lid_w = _span_layout(N_LID, ix + POST * 0.5, rng)
        for c, w in zip(lid_c, lid_w):
            wood_verts.extend(
                add_box(
                    bm,
                    (c, 0.0, top_z + SLAT_T / 2.0),
                    (w, iy + POST, SLAT_T),
                    WOOD_IDX,
                )
            )

        if not omit_slats:
            long_c, long_w = _span_layout(N_LONG, iz - 0.04, rng)
            for sign in (-1.0, 1.0):
                y = sign * (iy / 2.0 + POST - SLAT_T / 2.0 - 0.001)
                for c, w in zip(long_c, long_w):
                    wood_verts.extend(
                        add_box(
                            bm,
                            (0.0, y, SKID_H + 0.02 + iz / 2.0 + c),
                            (ix + TENON, SLAT_T, w),
                            WOOD_IDX,
                        )
                    )
        end_c, end_w = _span_layout(N_END, iz - 0.04, rng)
        for sign in (-1.0, 1.0):
            x = sign * (ix / 2.0 + POST - SLAT_T / 2.0 - 0.001)
            for c, w in zip(end_c, end_w):
                wood_verts.extend(
                    add_box(
                        bm,
                        (x, 0.0, SKID_H + 0.02 + iz / 2.0 + c),
                        (SLAT_T, iy + TENON, w),
                        WOOD_IDX,
                    )
                )

        if wood_verts:
            edges = list({e for v in wood_verts for e in v.link_edges if v.is_valid})
            if edges:
                bmesh.ops.bevel(
                    bm,
                    geom=edges,
                    offset=0.002,
                    segments=1,
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
                )

        # L-straps: two plates meeting at a vertical edge, proud of the
        # post. Not three overlapping cubes — those leave window holes.
        wrap = IRON_WRAP
        strap_z0 = 0.006
        strap_h = top_z - strap_z0
        zc = strap_z0 + strap_h / 2.0
        for sxn in (-1.0, 1.0):
            for syn in (-1.0, 1.0):
                ox = sxn * (hx + POST / 2.0 + IRON_T / 2.0)
                oy = syn * (hy + POST / 2.0 + IRON_T / 2.0)
                add_box(
                    bm,
                    (ox, syn * (hy + POST / 2.0 - wrap / 2.0 + IRON_T / 2.0), zc),
                    (IRON_T, wrap, strap_h),
                    METAL_IDX,
                )
                add_box(
                    bm,
                    (sxn * (hx + POST / 2.0 - wrap / 2.0 + IRON_T / 2.0), oy, zc),
                    (wrap - IRON_T, IRON_T, strap_h),
                    METAL_IDX,
                )

        hz = SKID_H + post_h * 0.52
        for sxn in (-1.0, 1.0):
            x_plate = sxn * (ix / 2.0 + POST - SLAT_T / 2.0)
            x_in = sxn * (ix / 2.0 + POST - SLAT_T - 0.008)
            x_out = sxn * (ix / 2.0 + POST + HANDLE_OUT)
            y0, y1 = -0.11, 0.11
            add_box(
                bm, (x_plate, y0, hz),
                (SLAT_T + IRON_T * 2.0, 0.034, 0.044), METAL_IDX,
            )
            add_box(
                bm, (x_plate, y1, hz),
                (SLAT_T + IRON_T * 2.0, 0.034, 0.044), METAL_IDX,
            )
            if float_handle:
                add_box(
                    bm, (x_out, 0.0, hz), (0.020, 0.020, 0.020), METAL_IDX,
                )
            else:
                add_handle_bail(
                    bm, x_in, x_out, y0, y1, hz, HANDLE_R, 8, METAL_IDX,
                )

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = True
            if edge.is_manifold and len(edge.link_faces) == 2:
                if edge.calc_face_angle() > math.radians(35.0):
                    edge.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


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
    idxs = poly.vertices
    if len(idxs) < 3:
        return 0.0
    v0 = me.vertices[idxs[0]].co
    area = 0.0
    for i in range(1, len(idxs) - 1):
        vs = (me.vertices[idxs[i]].co, me.vertices[idxs[i + 1]].co)
        area += (vs[0] - v0).cross(vs[1] - v0).length * 0.5
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
    skids = []
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if a[2] < 0.01 and dx > 0.6 and dy < 0.12 and dz < 0.08:
            skids.append(a)
    skid_z = min((a[2] for a in skids), default=99.0)
    return {"skids": len(skids), "skid_z": skid_z}


def body_audit(me):
    wood_ids = set()
    for p in me.polygons:
        if p.material_index == WOOD_IDX:
            wood_ids.update(p.vertices)
    pts = [
        me.vertices[i].co for i in wood_ids
        if me.vertices[i].co.z > SKID_H + 0.01
    ]
    if not pts:
        return {"dx": 0.0, "dy": 0.0, "dz": 0.0}
    xs, ys, zs = [p.x for p in pts], [p.y for p in pts], [p.z for p in pts]
    return {
        "dx": max(xs) - min(xs),
        "dy": max(ys) - min(ys),
        "dz": max(zs) - min(zs),
    }


def _bvh_gap(me, hosts, guests):
    if not hosts or not guests:
        return 99.0
    bm_h = bmesh.new()
    try:
        bm_h.from_mesh(me)
        keep = set()
        for g in hosts:
            keep.update(g)
        drop = [
            f for f in bm_h.faces
            if not all(v.index in keep for v in f.verts)
        ]
        if drop:
            bmesh.ops.delete(bm_h, geom=drop, context="FACES")
        if not bm_h.faces:
            return 99.0
        tree = BVHTree.FromBMesh(bm_h)
        worst = 0.0
        for g in guests:
            bm_g = bmesh.new()
            try:
                bm_g.from_mesh(me)
                member = set(g)
                drop_g = [
                    f for f in bm_g.faces
                    if not all(v.index in member for v in f.verts)
                ]
                if drop_g:
                    bmesh.ops.delete(bm_g, geom=drop_g, context="FACES")
                if not bm_g.faces:
                    worst = max(worst, 99.0)
                    continue
                tree_g = BVHTree.FromBMesh(bm_g)
                if tree.overlap(tree_g):
                    continue
                best = 99.0
                for i in g:
                    hit = tree.find_nearest(me.vertices[i].co)
                    if hit[0] is None:
                        continue
                    best = min(best, hit[3])
                if best > worst:
                    worst = best
            finally:
                bm_g.free()
        return worst
    finally:
        bm_h.free()


def handle_join(me):
    groups = shells(me)
    ends, handles = [], []
    for g in groups:
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if mat_of(me, g) == WOOD_IDX and dx < 0.04 and dy > 0.40 and 0.03 < dz < 0.18:
            ends.append(g)
        elif mat_of(me, g) == METAL_IDX and dz < 0.12 and max(dx, dy) > 0.15:
            handles.append(g)
    return _bvh_gap(me, ends, handles)


def slat_join(me):
    groups = shells(me)
    posts, slats = [], []
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if dz > 0.30 and dx < 0.08 and dy < 0.08:
            posts.append(g)
        elif 0.04 < dz < 0.16 and dx > 0.40 and dy < 0.030:
            slats.append(g)
    return _bvh_gap(me, posts, slats)


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, 0.40))
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
    img = bpy.data.images.new("CrateNrm", size, size, alpha=True, float_buffer=False)
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
    bpy.ops.export_scene.gltf(
        filepath=path,
        use_selection=True,
        export_yup=True,
        export_apply=True,
        export_draco_mesh_compression_enable=False,
        export_animations=False,
    )


def check(
    skip_decimate,
    lift_z=False,
    stray_vert=False,
    short_skids=False,
    float_handle=False,
    omit_slats=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        short_skids=short_skids,
        float_handle=float_handle,
        omit_slats=omit_slats,
    )
    low = build_crate_mesh("CrateLow", **flags)
    high = build_crate_mesh("CrateHigh", **flags)
    wood = principled(
        "CrateWood", (0.48, 0.22, 0.07, 1.0), 0.0, 0.50,
        noise_scale=7.0, wear=(0.28, 0.14, 0.05, 1.0),
    )
    metal = principled(
        "CrateMetal", (0.18, 0.17, 0.16, 1.0), 0.86, 0.36,
        noise_scale=5.0, wear=(0.10, 0.09, 0.08, 1.0),
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
        return fail("crate mesh did not build", 3), None, None, None, None, None

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
        return fail("crate has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "CrateLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "CrateLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_crate_mesh("CrateColSrc", **flags)
    collider = convex_hull_collider(collider_src, "CrateCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_shipping_crate_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    sup = support_audit(low.data)
    body = body_audit(low.data)
    hj = handle_join(low.data)
    sj = slat_join(low.data)

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
        f"measured supports skids={sup['skids']} skid_z={sup['skid_z']:.5f} "
        f"body=({body['dx']:.4f},{body['dy']:.4f},{body['dz']:.4f}) "
        f"handle_join={hj:.5f} slat_join={sj:.5f}"
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
    if sup["skids"] < 3 or sup["skid_z"] > SKID_Z_MAX:
        return fail(
            f"skid supports {sup['skids']} skid_z={sup['skid_z']:.5f} "
            "(--short-skids is the designed fail)",
            16,
        ), None, None, None, None, None
    if hj > HANDLE_JOIN:
        return fail(
            f"handle-end gap {hj:.5f} > {HANDLE_JOIN} "
            "(--float-handle is the designed fail)",
            17,
        ), None, None, None, None, None
    if sj > SLAT_JOIN:
        return fail(
            f"slat-post gap {sj:.5f} > {SLAT_JOIN} "
            "(--omit-slats is the designed fail)",
            18,
        ), None, None, None, None, None
    if abs(body["dx"] - BODY_X) > BODY_TOL:
        return fail(f"body dx {body['dx']:.4f} off {BODY_X}", 19), None, None, None, None, None
    if abs(body["dy"] - BODY_Y) > BODY_TOL:
        return fail(f"body dy {body['dy']:.4f} off {BODY_Y}", 19), None, None, None, None, None
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

    low.rotation_euler.z = math.radians(-48.0)
    low.rotation_euler.x = math.radians(4.0)

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

    light("Key", (-3.6, -5.0, 5.8), 680.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.6, 2.6), 48.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.4, 4.2, 4.1), 640.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.96, -2.44, 1.32)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.30)
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
    p.add_argument("--short-skids", action="store_true")
    p.add_argument("--float-handle", action="store_true")
    p.add_argument("--omit-slats", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_skids=args.short_skids,
        float_handle=args.float_handle,
        omit_slats=args.omit_slats,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("shipping-crate OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
