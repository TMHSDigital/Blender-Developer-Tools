"""Game-ready park bench — a showcase piece, not an example.

Asserts budget conformance of a procedural wrought-iron bench (quarter-
circle scroll feet tangent to the posts, slatted seat and back, arm
scrolls) after composing shipped pipeline pieces: bmesh construction,
UVs, two materials, high-to-low normal bake, LOD chain, convex collider,
Unity glTF export.

Posts, feet, stretchers and arms share named stations (hx, hy, SEAT_Z,
ARM_Z, SCROLL_R). A foot is a quarter-circle about (hy ± R, R) so it is
tangent to the post at z=R and plants at z=0.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` LOD, ``--stray-vert`` hygiene, ``--lift-z``
zmin, ``--short-feet`` named toes, ``--float-stretcher`` stretcher seat,
``--gap-slats`` slat-to-rail, ``--narrow-seat`` sitting width.

No RNG. Slat widths use closed-form ``sin(i)``. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python park_bench.py --
    blender --background --python park_bench.py -- --skip-decimate
    blender --background --python park_bench.py -- --output bench.png
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

SEAT_W = 1.40
SEAT_D = 0.50
SEAT_Z = 0.43
N_SEAT = 7
N_BACK = 5
SLAT_T = 0.030
BACK_H = 0.38
IRON_T = 0.024
SCROLL_R = 0.11
SCROLL_N = 12
ARM_Z = 0.64
ARM_SCROLL_R = 0.055
STRETCHER_Z = 0.16
POST_INSET_X = 0.07
POST_INSET_Y = 0.045
HX = SEAT_W / 2.0 - POST_INSET_X
HY = SEAT_D / 2.0 - POST_INSET_Y
SEAT_SPAN = 2.0 * HX
SEAT_SPAN_TOL = 0.08

BBOX_TOL = 0.015
OUTER_SIZE = (1.295, 0.632, 0.884)
BASE_TRIS_MIN = 2200
BASE_TRIS_MAX = 4200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 180
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
METAL_FACES_MIN = 48
WOOD_FACES_MIN = 24
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.998
STRETCHER_GAP_MAX = 0.008
SLAT_GAP_MAX = 0.008
TOE_COUNT = 4
TOE_ZMIN_MAX = 0.002
FLOAT_STRETCHER = 0.10
GAP_SLAT = 0.10
SHORT_FOOT = 0.16
LIFT_Z = 0.05
NARROW_SEAT = 0.55

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


def add_arc_yz(bm, x, cy, cz, radius, a0, a1, n, thick, mat_idx, t0=0.0, t1=1.0):
    pts = []
    for i in range(n + 1):
        t = t0 + (t1 - t0) * (i / n)
        ang = a0 + (a1 - a0) * t
        pts.append(Vector((x, cy + radius * math.cos(ang), cz + radius * math.sin(ang))))
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
    bm.faces.ensure_lookup_table()
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


def add_foot_scroll(bm, x, y_post, y_out, thick, mat_idx):
    """Quarter-circle from post join (y_post, R) to toe (y_out, 0)."""
    cy = y_out
    cz = SCROLL_R
    if y_out < y_post:
        a0, a1 = 0.0, -math.pi / 2.0
    else:
        a0, a1 = math.pi, 1.5 * math.pi
    return add_arc_yz(
        bm, x, cy, cz, SCROLL_R, a0, a1, SCROLL_N, thick, mat_idx, t0=0.08, t1=1.0
    )


def add_arm_scroll(bm, x, y_post, thick, mat_idx):
    cy = y_post - ARM_SCROLL_R
    cz = ARM_Z
    return add_arc_yz(
        bm, x, cy, cz, ARM_SCROLL_R, 0.0, -math.pi / 2.0, 8, thick, mat_idx, t0=0.08, t1=1.0
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


def build_bench_mesh(
    name,
    bevel_offset,
    bevel_segments,
    float_stretcher=False,
    gap_slats=False,
    short_feet=False,
    narrow_seat=False,
):
    bm = bmesh.new()
    try:
        wood = []
        t = IRON_T
        hx, hy = HX, HY
        slat_span = SEAT_SPAN + t * 0.50
        if gap_slats:
            slat_span = SEAT_SPAN - IRON_T - 0.024
        if narrow_seat:
            slat_span = SEAT_SPAN * NARROW_SEAT

        usable = 2.0 * hy - 0.06
        gap = 0.010
        widths = []
        for i in range(N_SEAT):
            widths.append(1.0 + 0.10 * math.sin(i * 1.7 + 0.3))
        scale = (usable - gap * (N_SEAT - 1)) / sum(widths)
        y_cursor = -hy + 0.03
        for i, w in enumerate(widths):
            slat_w = w * scale
            y = y_cursor + slat_w * 0.5
            wood.extend(
                add_box(
                    bm,
                    (0.0, y, SEAT_Z + SLAT_T / 2.0),
                    (slat_span, slat_w * 0.92, SLAT_T),
                    WOOD_IDX,
                )
            )
            y_cursor += slat_w + gap

        back_span = BACK_H - 0.04
        bwidths = [1.0 + 0.08 * math.sin(i * 1.4 + 0.8) for i in range(N_BACK)]
        bscale = (back_span - gap * (N_BACK - 1)) / sum(bwidths)
        z_cursor = SEAT_Z + SLAT_T + 0.04
        for w in bwidths:
            slat_h = w * bscale
            z = z_cursor + slat_h * 0.5
            wood.extend(
                add_box(
                    bm,
                    (0.0, hy, z),
                    (slat_span, SLAT_T, slat_h * 0.90),
                    WOOD_IDX,
                )
            )
            z_cursor += slat_h + gap

        for xsign in (-1.0, 1.0):
            x = xsign * hx
            wood.extend(
                add_box(
                    bm,
                    (x, 0.0, ARM_Z + t * 0.5 + SLAT_T * 0.5),
                    (SLAT_T * 1.15, 2.0 * hy + t, SLAT_T),
                    WOOD_IDX,
                )
            )

        if bevel_offset > 0.0:
            edges = list({e for v in wood for e in v.link_edges})
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

        add_box(bm, (0.0, -hy, SEAT_Z - t * 0.35), (SEAT_SPAN, t, t), METAL_IDX)
        add_box(bm, (0.0, hy, SEAT_Z - t * 0.35), (SEAT_SPAN, t, t), METAL_IDX)
        for xsign in (-1.0, 1.0):
            add_box(
                bm,
                (xsign * hx, 0.0, SEAT_Z - t * 0.35),
                (t, 2.0 * hy, t),
                METAL_IDX,
            )

        back_top = SEAT_Z + SLAT_T + BACK_H + 0.02
        for xsign in (-1.0, 1.0):
            x = xsign * hx
            add_oriented_box(
                bm, (x, hy, SCROLL_R), (x, hy, back_top), (t, t), METAL_IDX
            )
            add_oriented_box(
                bm, (x, -hy, SCROLL_R), (x, -hy, ARM_Z), (t, t), METAL_IDX
            )
            add_oriented_box(
                bm, (x, -hy, ARM_Z), (x, hy, ARM_Z), (t * 0.95, t * 0.95), METAL_IDX
            )
            add_foot_scroll(bm, x, -hy, -hy - SCROLL_R, t, METAL_IDX)
            add_foot_scroll(bm, x, hy, hy + SCROLL_R, t, METAL_IDX)
            add_arm_scroll(bm, x, -hy, t * 0.90, METAL_IDX)

        add_box(bm, (0.0, hy, back_top), (SEAT_SPAN, t, t), METAL_IDX)

        st_trim = FLOAT_STRETCHER if float_stretcher else 0.0
        yx = hx - st_trim
        add_oriented_box(
            bm,
            (-yx, -hy, STRETCHER_Z),
            (-yx, hy, STRETCHER_Z),
            (t * 0.9, t * 0.9),
            METAL_IDX,
        )
        add_oriented_box(
            bm,
            (yx, -hy, STRETCHER_Z),
            (yx, hy, STRETCHER_Z),
            (t * 0.9, t * 0.9),
            METAL_IDX,
        )
        cx_end = yx - t * 0.40
        add_oriented_box(
            bm,
            (-cx_end, 0.0, STRETCHER_Z),
            (cx_end, 0.0, STRETCHER_Z),
            (t * 0.9, t * 0.9),
            METAL_IDX,
        )

        if short_feet:
            for v in bm.verts:
                if v.co.z < SCROLL_R * 0.55 and abs(v.co.y) > hy + SCROLL_R * 0.35:
                    v.co.z += SHORT_FOOT

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
            if v.co.z < 0.0:
                v.co.z = 0.0

        ngons = [f for f in bm.faces if len(f.verts) > 4]
        if ngons:
            bmesh.ops.triangulate(bm, faces=ngons)
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
        bm.verts.new((0.0, 0.0, SEAT_Z + 0.12))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def joint_audit(me):
    groups = shells(me)
    posts = []
    stretchers = []
    slats = []
    for g in groups:
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        mat = mat_of(me, g)
        if mat == METAL_IDX and dz > 0.28 and dx < 0.08 and dy < 0.08:
            posts.append((g, a))
        if mat == METAL_IDX and abs(0.5 * (a[2] + a[5]) - STRETCHER_Z) < 0.05 and max(dx, dy) > 0.25:
            stretchers.append((g, a))
        if mat == WOOD_IDX and dz < 0.08 and dx > SEAT_SPAN * 0.4:
            slats.append((g, a))
    metal_verts = []
    for poly in me.polygons:
        if poly.material_index != METAL_IDX:
            continue
        for i in poly.vertices:
            metal_verts.append(me.vertices[i].co)
    stations = (
        (HX, HY + SCROLL_R, 0.0),
        (HX, -HY - SCROLL_R, 0.0),
        (-HX, HY + SCROLL_R, 0.0),
        (-HX, -HY - SCROLL_R, 0.0),
    )
    toes = 0
    toe_z = 99.0
    for sx, sy, sz in stations:
        nearby = []
        for co in metal_verts:
            d = ((co.x - sx) ** 2 + (co.y - sy) ** 2) ** 0.5
            if d < SCROLL_R * 0.55:
                nearby.append(co)
        if nearby:
            toes += 1
            toe_z = min(toe_z, min(c.z for c in nearby))
    st_gap = 99.0
    if stretchers and posts:
        st_gap = min(shell_bvh_gap(me, s[0], p[0]) for s in stretchers for p in posts)
    slat_gap = 99.0
    rails = [p for p in posts]
    if slats and rails:
        slat_gap = min(shell_bvh_gap(me, s[0], p[0]) for s in slats for p in rails)
    seat_x = 0.0
    if slats:
        xs = [v for _g, a in slats for v in (a[0], a[3])]
        seat_x = max(xs) - min(xs)
    return {
        "toes": toes,
        "toe_z": toe_z,
        "posts": len(posts),
        "stretchers": len(stretchers),
        "st_gap": st_gap,
        "slat_gap": slat_gap,
        "seat_x": seat_x,
        "slats": len(slats),
    }


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("BenchNrm", size, size, alpha=True, float_buffer=False)
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
    skip_decimate,
    lift_z=False,
    stray_vert=False,
    float_stretcher=False,
    gap_slats=False,
    short_feet=False,
    narrow_seat=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    kw = dict(
        float_stretcher=float_stretcher,
        gap_slats=gap_slats,
        short_feet=short_feet,
        narrow_seat=narrow_seat,
    )
    low = build_bench_mesh("BenchLow", bevel_offset=0.004, bevel_segments=2, **kw)
    high = build_bench_mesh("BenchHigh", bevel_offset=0.004, bevel_segments=4, **kw)
    wood = principled(
        "BenchWood", (0.40, 0.20, 0.07, 1.0), 0.0, 0.58,
        noise_scale=18.0, wear=(0.28, 0.14, 0.05, 1.0),
    )
    metal = principled(
        "BenchIron", (0.09, 0.095, 0.11, 1.0), 1.0, 0.32,
        noise_scale=22.0, wear=(0.16, 0.14, 0.10, 1.0),
    )
    assign_slots(low, wood, metal)
    assign_slots(high, wood, metal)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("bench mesh did not build", 3), None, None, None, None, None

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
        return fail("bench has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BenchLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BenchLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_bench_mesh(
        "BenchColSrc", bevel_offset=0.0, bevel_segments=1, **kw
    )
    collider = convex_hull_collider(collider_src, "BenchCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_park_bench_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0

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
    zf = zfight_pairs(low.data)
    jnt = joint_audit(low.data)
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}"
    )
    print(
        f"measured toes={jnt['toes']} toe_z={jnt['toe_z']:.5f} "
        f"posts={jnt['posts']} stretchers={jnt['stretchers']} "
        f"st_gap={jnt['st_gap']:.5f} slat_gap={jnt['slat_gap']:.5f} "
        f"seat_x={jnt['seat_x']:.4f} slats={jnt['slats']}"
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
    if abs(jnt["seat_x"] - SEAT_SPAN) > SEAT_SPAN_TOL:
        return fail(
            f"seat span {jnt['seat_x']:.4f} off {SEAT_SPAN}",
            19,
        ), None, None, None, None, None
    if bb[2] > ZMIN_EPS or jnt["toes"] != TOE_COUNT or jnt["toe_z"] > TOE_ZMIN_MAX:
        return fail(
            f"grounded zmin={bb[2]:.5f} toes={jnt['toes']} toe_z={jnt['toe_z']:.5f}",
            16,
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
    if jnt["stretchers"] < 2 or jnt["st_gap"] > STRETCHER_GAP_MAX:
        return fail(
            f"stretcher gap {jnt['st_gap']:.5f} stretchers={jnt['stretchers']}",
            17,
        ), None, None, None, None, None
    if jnt["slats"] < 4 or jnt["slat_gap"] > SLAT_GAP_MAX:
        return fail(
            f"slat gap {jnt['slat_gap']:.5f} slats={jnt['slats']}",
            18,
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

    low.rotation_euler.z = math.radians(-14.0)
    low.rotation_euler.x = math.radians(2.0)

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
    cam.location = (2.22, -2.90, 1.34)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.42)
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
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--short-feet", action="store_true")
    p.add_argument("--float-stretcher", action="store_true")
    p.add_argument("--gap-slats", action="store_true")
    p.add_argument("--narrow-seat", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_stretcher=args.float_stretcher,
        gap_slats=args.gap_slats,
        short_feet=args.short_feet,
        narrow_seat=args.narrow_seat,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("park-bench OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
