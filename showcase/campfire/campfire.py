"""Game-ready campfire — a showcase piece, not an example.

Asserts budget conformance of a procedural campfire (two-course
wedge-stone ring stacked on a shared plane, pit-floor cobbles and ash,
a kissing log tripod, and resting firewood) after composing shipped
pipeline pieces: bmesh construction, UVs, three materials, high-to-low
normal bake, LOD chain, convex collider, Unity glTF export.

The old piece was two floating courses of identical boxes with a
daylight mortar gap, a 12-gon teepee whose tips occupied the same
point, and an empty pit.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-stones`` named
bottom-course supports, ``--float-logs`` teepee kiss, ``--gap-courses``
the stacked-course seat.

Fixed seed 17 for stone-width jitter. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python campfire.py --
    blender --background --python campfire.py -- --skip-decimate
    blender --background --python campfire.py -- --output campfire.png
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

N_AROUND = 14
N_ROWS = 2
R_INNER = 0.26
R_OUTER = 0.39
R_MID = 0.5 * (R_INNER + R_OUTER)
STONE_H = 0.078
STONE_SEED = 17
STONE_JITTER = 0.10
GAP_ANG = 0.004
N_COBBLES = 12
COBBLE_H = 0.016
ASH_H = 0.010
ASH_R = 0.20
N_STICKS = 3
STICK_R = 0.028
STICK_SEGS = 12
LOG_R = 0.030
LOG_LEN = 0.28
Z_APEX = 0.365
R_BASE = 0.20
COURSE_GAP = 0.022
FLOAT_LOG = 0.055
SHORT_STONES_LIFT = 0.040
LIFT_Z = 0.05
KISS_MAX = 0.008
COURSE_SEAT_MAX = 0.004
STAVE_ZMIN_MAX = 0.001

AREA_EPS = 1e-10
DOUBLES_EPS = 1e-5
ZMIN_EPS = 1e-4
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.998
BODY_TOL = 0.04
RING_DIA = 0.807
RING_H = 0.156
BBOX_TOL = 0.015
OUTER_SIZE = (0.807, 0.808, 0.404)

BASE_TRIS_MIN = 1400
BASE_TRIS_MAX = 3600
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
WOOD_FACES_MIN = 80
ASH_FACES_MIN = 24
STONE_FACES_MIN = 200
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 360
BAKE_RES = 256
CAGE_EXTRUSION = 0.06
BOTTOM_COUNT = N_AROUND

STONE_IDX = 0
WOOD_IDX = 1
ASH_IDX = 2


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


def stone_spans(n, gap_ang, jitter, seed):
    rng = random.Random(seed)
    weights = [1.0 + rng.uniform(-jitter, jitter) for _ in range(n)]
    total = sum(weights)
    usable = 2.0 * math.pi - n * gap_ang
    spans = []
    a = 0.0
    for w in weights:
        width = usable * (w / total)
        spans.append((a, a + width))
        a += width + gap_ang
    return spans


def add_wedge(bm, a0, a1, r_in, r_out, z0, z1, mat_idx, lump=0.0):
    mid_z = 0.5 * (z0 + z1)
    mid_ang = 0.5 * (a0 + a1)
    layers = (
        (z0, 0.985, 0.0),
        (mid_z, 1.025, lump),
        (z1, 0.97, 0.0),
    )
    rings = []
    for z, r_scale, lp in layers:
        ring = []
        for ang, r in (
            (a0, r_in),
            (a1, r_in),
            (a1, r_out * r_scale),
            (a0, r_out * r_scale),
        ):
            x = r * math.cos(ang)
            y = r * math.sin(ang)
            if lp > 0.0 and r > 0.5 * (r_in + r_out):
                h = math.sin(ang * 5.0 + z * 17.0 + mid_ang * 3.0)
                scale = 1.0 + lp * max(-0.7, min(0.7, h))
                x *= scale
                y *= scale
            ring.append(bm.verts.new((x, y, z)))
        rings.append(ring)
    verts = [v for ring in rings for v in ring]
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(4):
            j = (i + 1) % 4
            face = bm.faces.new((a[i], a[j], b[j], b[i]))
            face.material_index = mat_idx
    bot = rings[0]
    top = rings[-1]
    face = bm.faces.new((bot[0], bot[3], bot[2], bot[1]))
    face.material_index = mat_idx
    face = bm.faces.new((top[0], top[1], top[2], top[3]))
    face.material_index = mat_idx
    return verts


def add_cyl_between(bm, a, b, r0, r1, segs, mat_idx):
    a = Vector(a)
    b = Vector(b)
    delta = b - a
    length = delta.length
    if length < 1e-8:
        return []
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=True,
        segments=segs,
        radius1=r0,
        radius2=r1,
        depth=length,
    )
    verts = list(geo["verts"])
    quat = Vector((0.0, 0.0, 1.0)).rotation_difference(delta.normalized())
    rot = quat.to_matrix()
    mid = (a + b) * 0.5
    for v in verts:
        v.co = rot @ v.co + mid
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


def add_ash_disk(bm, radius, height, segs, mat_idx):
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=True,
        segments=segs,
        radius1=radius,
        radius2=radius * 0.92,
        depth=height,
    )
    verts = list(geo["verts"])
    for v in verts:
        v.co.z += height * 0.5
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


def triangulate_ngons(bm):
    faces = [f for f in bm.faces if len(f.verts) > 4]
    if faces:
        bmesh.ops.triangulate(bm, faces=faces)


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


def build_campfire_mesh(
    name,
    bevel_offset,
    bevel_segments,
    short_stones=False,
    float_logs=False,
    gap_courses=False,
):
    bm = bmesh.new()
    spans = stone_spans(N_AROUND, GAP_ANG, STONE_JITTER, STONE_SEED)
    z_ground = SHORT_STONES_LIFT if short_stones else 0.0
    extra = COURSE_GAP if gap_courses else 0.0
    stone_verts = []
    try:
        for row in range(N_ROWS):
            z0 = z_ground + row * STONE_H + (extra if row else 0.0)
            z1 = z0 + STONE_H
            rot_off = (row % 2) * (math.pi / N_AROUND)
            for a0, a1 in spans:
                stone_verts.extend(
                    add_wedge(
                        bm,
                        a0 + rot_off,
                        a1 + rot_off,
                        R_INNER,
                        R_OUTER,
                        z0,
                        z1,
                        STONE_IDX,
                        lump=0.022,
                    )
                )

        if bevel_offset > 0.0:
            vertical = []
            seen = set()
            for v in stone_verts:
                for e in v.link_edges:
                    if e in seen:
                        continue
                    seen.add(e)
                    a, b = e.verts
                    if abs(a.co.z - b.co.z) > 0.02:
                        vertical.append(e)
            if vertical:
                ret = bmesh.ops.bevel(
                    bm,
                    geom=vertical,
                    offset=min(bevel_offset, 0.008),
                    segments=bevel_segments,
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
                )
                for f in ret.get("faces") or []:
                    f.material_index = STONE_IDX

        add_ash_disk(bm, ASH_R, ASH_H, 16, ASH_IDX)
        rng = random.Random(STONE_SEED)
        for i in range(N_COBBLES):
            ang = 2.0 * math.pi * i / N_COBBLES + 0.18
            r = 0.07 + 0.05 * ((i % 3) / 2.0)
            sz = 0.028 + 0.010 * (i % 2)
            loc = Vector((r * math.cos(ang), r * math.sin(ang), COBBLE_H * 0.5))
            geo = bmesh.ops.create_cube(bm, size=1.0)
            verts = geo["verts"]
            for v in verts:
                p = Vector((
                    v.co.x * (sz * 1.4),
                    v.co.y * sz,
                    v.co.z * COBBLE_H,
                ))
                h = rng.uniform(-0.12, 0.12)
                p = Vector((p.x * (1.0 + h), p.y * (1.0 - 0.5 * h), p.z))
                rot_z = ang + rng.uniform(-0.2, 0.2)
                c, s = math.cos(rot_z), math.sin(rot_z)
                v.co = Vector((
                    p.x * c - p.y * s,
                    p.x * s + p.y * c,
                    p.z,
                )) + loc
            for f in {f for v in verts for f in v.link_faces}:
                f.material_index = STONE_IDX

        apex_ring = (STICK_R * 0.55) / math.sin(math.pi / N_STICKS)
        if float_logs:
            apex_ring *= 2.8
        z_base = COBBLE_H + STICK_R * 0.35
        overshoot = STICK_R * 1.15
        for i in range(N_STICKS):
            yaw = i * (2.0 * math.pi / N_STICKS) + math.pi / 6.0
            base = Vector((
                R_BASE * math.cos(yaw),
                R_BASE * math.sin(yaw),
                z_base,
            ))
            apex = Vector((
                apex_ring * math.cos(yaw),
                apex_ring * math.sin(yaw),
                Z_APEX - i * (STICK_R * 0.55),
            ))
            direction = (apex - base).normalized()
            end = apex + direction * overshoot
            add_cyl_between(
                bm, base, end, STICK_R, STICK_R * 0.78, STICK_SEGS, WOOD_IDX,
            )

        for i in range(2):
            yaw = i * (math.pi / 2.0) + math.radians(22.0)
            z = COBBLE_H + LOG_R + 0.010 * i
            a = Vector((
                0.5 * LOG_LEN * math.cos(yaw),
                0.5 * LOG_LEN * math.sin(yaw),
                z,
            ))
            b = Vector((-a.x, -a.y, z))
            add_cyl_between(bm, a, b, LOG_R * (1.0 - 0.06 * i), LOG_R * 0.86, 12, WOOD_IDX)

        for i in range(6):
            ang = 2.0 * math.pi * i / 6.0 + 0.4
            r = 0.04 + 0.02 * (i % 2)
            sz = 0.018 + 0.006 * (i % 3)
            loc = (
                r * math.cos(ang),
                r * math.sin(ang),
                ASH_H + sz * 0.45,
            )
            geo = bmesh.ops.create_cube(bm, size=1.0)
            verts = geo["verts"]
            for v in verts:
                p = Vector((v.co.x * sz * 1.3, v.co.y * sz, v.co.z * sz * 0.7))
                c, s = math.cos(ang), math.sin(ang)
                v.co = Vector((p.x * c - p.y * s, p.x * s + p.y * c, p.z)) + Vector(loc)
            for f in {f for v in verts for f in v.link_faces}:
                f.material_index = WOOD_IDX

        triangulate_ngons(bm)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = face.material_index == WOOD_IDX
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if WOOD_IDX in mats and STONE_IDX not in mats and ASH_IDX not in mats:
                edge.smooth = True
                if edge.is_manifold and len(edge.link_faces) == 2:
                    if edge.calc_face_angle() > math.radians(38.0):
                        edge.smooth = False
            else:
                edge.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        for poly in me.polygons:
            poly.use_smooth = poly.material_index == WOOD_IDX
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
        rmix.inputs["B"].default_value = min(1.0, roughness + 0.16)
        rfac = rmix.inputs.get("Factor") or rmix.inputs.get("Fac")
        nt.links.new(tex.outputs["Fac"], rfac)
        nt.links.new(rmix.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def assign_slots(obj, stone, wood, ash):
    mats = obj.data.materials
    wanted = (stone, wood, ash)
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


def face_area(me, poly):
    verts = [me.vertices[i].co for i in poly.vertices]
    if len(verts) < 3:
        return 0.0
    acc = Vector((0.0, 0.0, 0.0))
    origin = verts[0]
    for a, b in zip(verts[1:], verts[2:]):
        acc += (a - origin).cross(b - origin)
    return 0.5 * acc.length


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
    bottoms = []
    for g in groups:
        if mat_of(me, g) != STONE_IDX:
            continue
        a = shell_aabb(me, g)
        dz = a[5] - a[2]
        r = 0.25 * ((a[3] - a[0]) + (a[4] - a[1]))
        if dz > 0.05 and r > 0.04 and a[2] < 0.02:
            bottoms.append(a)
    zmin = min((a[2] for a in bottoms), default=99.0)
    return {"stones": len(bottoms), "stone_z": zmin}


def course_seat(me):
    groups = shells(me)
    lower, upper = [], []
    for g in groups:
        if mat_of(me, g) != STONE_IDX:
            continue
        a = shell_aabb(me, g)
        dz = a[5] - a[2]
        r = 0.25 * ((a[3] - a[0]) + (a[4] - a[1]))
        if dz < 0.05 or r < 0.04:
            continue
        mid = 0.5 * (a[2] + a[5])
        if mid < STONE_H:
            lower.append(a)
        else:
            upper.append(a)
    if not lower or not upper:
        return 99.0
    return min(a[2] for a in upper) - max(a[5] for a in lower)


def teepee_kiss(me):
    groups = shells(me)
    sticks = []
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        if a[5] < 0.25:
            continue
        sticks.append(g)
    if len(sticks) < 2:
        return 99.0
    trees = []
    for g in sticks:
        bm_s = bmesh.new()
        bm_s.from_mesh(me)
        keep = set(g)
        drop = [f for f in bm_s.faces if not all(v.index in keep for v in f.verts)]
        if drop:
            bmesh.ops.delete(bm_s, geom=drop, context="FACES")
        if bm_s.faces:
            trees.append((g, BVHTree.FromBMesh(bm_s), bm_s))
        else:
            bm_s.free()
    best = 99.0
    try:
        for i in range(len(trees)):
            g, _tree, _bm = trees[i]
            zmax = max(me.vertices[k].co.z for k in g)
            for j in range(i + 1, len(trees)):
                tree = trees[j][1]
                pair = 99.0
                for k in g:
                    p = me.vertices[k].co
                    if p.z < zmax - 0.10:
                        continue
                    loc, _n, _idx, dist = tree.find_nearest(p)
                    if loc is None:
                        continue
                    pair = min(pair, dist)
                best = min(best, pair)
        return best
    finally:
        for _g, _t, bm_s in trees:
            bm_s.free()


def body_plan(me):
    groups = shells(me)
    xs, ys, z0s, z1s = [], [], [], []
    for g in groups:
        if mat_of(me, g) != STONE_IDX:
            continue
        a = shell_aabb(me, g)
        if a[5] - a[2] < 0.05:
            continue
        xs.extend((a[0], a[3]))
        ys.extend((a[1], a[4]))
        z0s.append(a[2])
        z1s.append(a[5])
    if not xs:
        return 0.0, 0.0
    dia = 0.5 * ((max(xs) - min(xs)) + (max(ys) - min(ys)))
    return dia, max(z1s) - min(z0s)


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, 0.20))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def make_lod(obj, name, ratio, skip_decimate):
    mesh = obj.data.copy()
    lod = bpy.data.objects.new(name, mesh)
    lod.matrix_world = obj.matrix_world.copy()
    bpy.context.collection.objects.link(lod)
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
        bmesh.ops.dissolve_limit(
            bm,
            angle_limit=math.radians(10.0),
            verts=list(bm.verts),
            edges=list(bm.edges),
            delimit={"NORMAL"},
        )
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
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
    img = bpy.data.images.new("CampfireNrm", size, size, alpha=True, float_buffer=False)
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
    short_stones=False,
    float_logs=False,
    gap_courses=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        short_stones=short_stones,
        float_logs=float_logs,
        gap_courses=gap_courses,
    )
    low = build_campfire_mesh("CampfireLow", 0.006, 2, **flags)
    high = build_campfire_mesh("CampfireHigh", 0.006, 4, **flags)
    stone = principled(
        "CampfireStone", (0.40, 0.42, 0.46, 1.0), 0.0, 0.84,
        noise_scale=8.0, wear=(0.28, 0.27, 0.24, 1.0),
    )
    wood = principled(
        "CampfireWood", (0.38, 0.18, 0.07, 1.0), 0.0, 0.62,
        noise_scale=6.0, wear=(0.18, 0.09, 0.04, 1.0),
    )
    ash = principled(
        "CampfireAsh", (0.12, 0.11, 0.10, 1.0), 0.0, 0.94,
        noise_scale=10.0, wear=(0.08, 0.07, 0.06, 1.0),
    )
    assign_slots(low, stone, wood, ash)
    assign_slots(high, stone, wood, ash)
    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("campfire mesh did not build", 3), None, None, None, None, None

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
    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    sup = support_audit(low.data)
    cseat = course_seat(low.data)
    kiss = teepee_kiss(low.data)
    dia, ht = body_plan(low.data)
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}"
    )
    print(
        f"measured stones={sup['stones']} stone_z={sup['stone_z']:.5f} "
        f"course_seat={cseat:.5f} kiss={kiss:.5f} body={dia:.4f}x{ht:.4f}"
    )

    img, tex = setup_bake_image(low, stone)
    if img is None:
        return fail("campfire has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "CampfireLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "CampfireLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_campfire_mesh("CampfireColSrc", 0.0, 1)
    collider = convex_hull_collider(collider_src, "CampfireCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_campfire_{os.getpid()}.glb",
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
    if idx_counts.get(WOOD_IDX, 0) < WOOD_FACES_MIN:
        return fail(
            f"wood faces {idx_counts.get(WOOD_IDX, 0)} < {WOOD_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(ASH_IDX, 0) < ASH_FACES_MIN:
        return fail(
            f"ash faces {idx_counts.get(ASH_IDX, 0)} < {ASH_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(STONE_IDX, 0) < STONE_FACES_MIN:
        return fail(
            f"stone faces {idx_counts.get(STONE_IDX, 0)} < {STONE_FACES_MIN}",
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
        hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
        or hyg["doubles"] or hyg["ngons"] or zf
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}",
            15,
        ), None, None, None, None, None
    if bb[2] > ZMIN_EPS or sup["stones"] != BOTTOM_COUNT or sup["stone_z"] > STAVE_ZMIN_MAX:
        return fail(
            f"grounded zmin={bb[2]:.5f} stones={sup['stones']} "
            f"stone_z={sup['stone_z']:.5f}",
            16,
        ), None, None, None, None, None
    if kiss > KISS_MAX:
        return fail(f"teepee kiss {kiss:.5f} > {KISS_MAX}", 17), None, None, None, None, None
    if abs(cseat) > COURSE_SEAT_MAX:
        return fail(
            f"course seat {cseat:.5f} abs > {COURSE_SEAT_MAX}",
            18,
        ), None, None, None, None, None
    if abs(dia - RING_DIA) > BODY_TOL or abs(ht - RING_H) > BODY_TOL:
        return fail(
            f"ring {dia:.4f}x{ht:.4f} off {RING_DIA}x{RING_H}",
            19,
        ), None, None, None, None, None
    return 0, low, high, stone, tex, collider


def render_still(low, _stone, _tex, path, engine):
    scene = bpy.context.scene
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(-28.0)

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

    bb = world_bbox(low)
    span = max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], 0.2)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (span * 1.24, -span * 1.80, span * 1.36)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.5 * (bb[2] + bb[5]) - 0.04 * span)
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
    p.add_argument("--short-stones", action="store_true")
    p.add_argument("--float-logs", action="store_true")
    p.add_argument("--gap-courses", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, stone, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_stones=args.short_stones,
        float_logs=args.float_logs,
        gap_courses=args.gap_courses,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, stone, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("campfire OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
