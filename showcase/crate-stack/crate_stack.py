"""Game-ready stack of three shipping crates — a showcase piece, not an example.

Asserts budget conformance of a procedural crate *stack*: one crate
generator invoked three times with a per-instance seed, each instance
yawed and seated on the lid of the one below, then run through the
shipped pipeline (bmesh construction, UVs, two materials, high-to-low
normal bake, LOD chain, convex collider, Unity glTF export).

What this piece is about is **reuse with variation**. The three crates
come out of a single ``build_crate`` call each, differing only by the
seed handed to it. That seed drives the yaw, the lean, and the plank
widths, so the crates read as three of the same design rather than one
model copied three times. True instancing (three objects sharing one
mesh datablock) and per-instance geometry variation are mutually
exclusive; this piece takes the variation and says so, and the shipped
asset is the flattened single mesh a game engine would receive.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-skids`` the named ground
supports, ``--float-stack`` the crate-to-crate seat, ``--same-seed`` the
per-instance variation budget.

Fixed seed 41. DECIMATE COLLAPSE triangle counts are not byte-identical
across Blender versions — the LOD gate is a ratio band, not an exact
count.

    blender --background --python crate_stack.py --
    blender --background --python crate_stack.py -- --same-seed
    blender --background --python crate_stack.py -- --output stack.png
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
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

# One crate: 0.58 x 0.42 at the posts, 0.244 tall including skids and lid.
# Three stacked come to knee height, wider than they are tall.
CRATE_X = 0.58
CRATE_Y = 0.42
POST = 0.034
SKID_H = 0.024
SKID_W = 0.052
SLAT_T = 0.013
RAIL_H = 0.032
TENON = 0.008
IRON_T = 0.0035
IRON_WRAP = 0.052
# Straps bite into the timber and stop short of the rail top. Sitting them
# flush made the plate corner and the post corner the same point, which is
# a welded double, not a fixing.
IRON_BITE = 0.0012
IRON_DROP = 0.005
# The lid bites down onto the rails for the same reason: a lid resting
# exactly on the rail top shares that plane and those corner vertices.
LID_BITE = 0.004
BODY_H = 0.205
N_SIDE = 3
N_END = 2
N_FLOOR = 3
N_LID = 3
SLAT_JITTER = 0.20

N_CRATES = 3
STACK_SEED = 41
# Each crate bites this far into the lid of the one below, so the seat is
# an overlap rather than two coincident faces (which would z-fight).
STACK_BITE = 0.005
YAW_MIN = 0.060
YAW_MAX = 0.170
# Crates also step sideways. Three boxes stacked dead-centre read as a
# filing cabinet however much they are yawed.
OFFSET_MAX = 0.030
YAW_SPREAD_MIN = 0.020
WIDTH_SPREAD_MIN = 0.0008

CRATE_H = SKID_H + BODY_H + SLAT_T - LID_BITE
STACK_H = N_CRATES * CRATE_H - (N_CRATES - 1) * STACK_BITE

BBOX_TOL = 0.020
OUTER_SIZE = (0.658, 0.524, 0.704)
# The crate body over its corner iron, measured in the crate's own frame.
BODY_X = CRATE_X + 2.0 * (IRON_T - IRON_BITE)
BODY_Y = CRATE_Y + 2.0 * (IRON_T - IRON_BITE)
CRATE_TOL = 0.015

BASE_TRIS_MIN = 3200
BASE_TRIS_MAX = 7200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 260
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
METAL_FACES_MIN = 120
WOOD_FACES_MIN = 600
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.999
LIFT_Z = 0.05
SKID_Z_MAX = 1e-3
GROUND_SKIDS_MIN = 3
STACK_SEAT_MAX = 0.0015
FLOAT_LIFT = 0.009
SHORT_SKID_LIFT = 0.012

WOOD_IDX = 0
METAL_IDX = 1


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


def add_box(bm, loc, scale, mat_idx, xform=None):
    """Axis-aligned box in the crate frame, optionally placed by *xform*."""
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = geo["verts"]
    for v in verts:
        p = Vector(
            (
                v.co.x * scale[0] + loc[0],
                v.co.y * scale[1] + loc[1],
                v.co.z * scale[2] + loc[2],
            )
        )
        v.co = xform @ p if xform is not None else p
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


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


def _span_layout(count, span, rng, gap=0.009):
    """Uneven plank widths that still fill *span* with named gaps."""
    raw = [1.0 + rng.uniform(-SLAT_JITTER, SLAT_JITTER) for _ in range(count)]
    s = sum(raw)
    usable = span - gap * (count + 1)
    widths = [usable * r / s for r in raw]
    pos = -span / 2.0 + gap
    centres = []
    for w in widths:
        centres.append(pos + w / 2.0)
        pos += w + gap
    return centres, widths


def build_crate(bm, base_z, yaw, rng, offset=(0.0, 0.0), short_skids=False):
    """One crate, placed with its skid underside at *base_z* and yawed.

    Called once per stack level. Everything that differs between levels
    comes out of *rng* and *yaw*; the geometry recipe itself is shared.
    """
    xform = Matrix.Translation((offset[0], offset[1], 0.0)) @ Matrix.Rotation(
        yaw, 4, "Z"
    )
    hx = CRATE_X / 2.0 - POST / 2.0
    hy = CRATE_Y / 2.0 - POST / 2.0
    skid_z0 = base_z + (SHORT_SKID_LIFT if short_skids else 0.0)
    deck_z = base_z + SKID_H
    top_z = deck_z + BODY_H
    wood = []

    # Two runners under the posts. These are the named ground supports on
    # the bottom crate and the seat feet on the ones above.
    # Three runners, not two: two leave a slot you can see daylight
    # through between stacked crates, and a centre bearer is what a crate
    # this wide would actually carry.
    for si, sy in enumerate((-hy, 0.0, hy)):
        z0 = skid_z0 if (short_skids and si == 0) else base_z
        wood.extend(
            add_box(
                bm,
                (0.0, sy, z0 + SKID_H / 2.0),
                (CRATE_X, SKID_W, SKID_H),
                WOOD_IDX,
                xform,
            )
        )
    # Corner posts, tenoned down into the skid line so no shared plane.
    post_h = BODY_H + TENON
    for sxn in (-1.0, 1.0):
        for syn in (-1.0, 1.0):
            wood.extend(
                add_box(
                    bm,
                    (sxn * hx, syn * hy, deck_z - TENON + post_h / 2.0),
                    (POST, POST, post_h),
                    WOOD_IDX,
                    xform,
                )
            )
    # Top rails and bottom sills, both tenoned into the posts.
    for zc, h in ((top_z - RAIL_H / 2.0, RAIL_H),
                  (deck_z - TENON + (RAIL_H + TENON) / 2.0, RAIL_H + TENON)):
        for syn in (-1.0, 1.0):
            wood.extend(
                add_box(
                    bm,
                    (0.0, syn * hy, zc),
                    (CRATE_X - POST + 2.0 * TENON, POST, h),
                    WOOD_IDX,
                    xform,
                )
            )
        for sxn in (-1.0, 1.0):
            wood.extend(
                add_box(
                    bm,
                    (sxn * hx, 0.0, zc),
                    (POST, CRATE_Y - POST + 2.0 * TENON, h),
                    WOOD_IDX,
                    xform,
                )
            )

    floor_c, floor_w = _span_layout(N_FLOOR, CRATE_X - POST, rng)
    for c, w in zip(floor_c, floor_w):
        wood.extend(
            add_box(
                bm,
                (c, 0.0, deck_z + SLAT_T / 2.0),
                (w, CRATE_Y - POST + TENON, SLAT_T),
                WOOD_IDX,
                xform,
            )
        )
    lid_c, lid_w = _span_layout(N_LID, CRATE_X, rng)
    for c, w in zip(lid_c, lid_w):
        wood.extend(
            add_box(
                bm,
                (c, 0.0, top_z + SLAT_T / 2.0 - LID_BITE),
                (w, CRATE_Y, SLAT_T),
                WOOD_IDX,
                xform,
            )
        )

    # Side and end boards. Their heights carry the per-instance jitter and
    # are what the variation budget recomputes.
    side_c, side_w = _span_layout(N_SIDE, BODY_H - RAIL_H * 1.6, rng)
    band_z = deck_z + RAIL_H * 0.8 + (BODY_H - RAIL_H * 1.6) / 2.0
    for syn in (-1.0, 1.0):
        y = syn * (CRATE_Y / 2.0 - SLAT_T / 2.0 - 0.0012)
        for c, w in zip(side_c, side_w):
            wood.extend(
                add_box(
                    bm,
                    (0.0, y, band_z + c),
                    (CRATE_X - POST + TENON, SLAT_T, w),
                    WOOD_IDX,
                    xform,
                )
            )
    end_c, end_w = _span_layout(N_END, BODY_H - RAIL_H * 1.6, rng)
    for sxn in (-1.0, 1.0):
        x = sxn * (CRATE_X / 2.0 - SLAT_T / 2.0 - 0.0012)
        for c, w in zip(end_c, end_w):
            wood.extend(
                add_box(
                    bm,
                    (x, 0.0, band_z + c),
                    (SLAT_T, CRATE_Y - POST + TENON, w),
                    WOOD_IDX,
                    xform,
                )
            )

    # L-straps: two plates meeting at the vertical corner edge, proud of
    # the post. Two plates, never three overlapping cubes.
    strap_z0 = deck_z + 0.010
    strap_h = top_z - IRON_DROP - strap_z0
    zc = strap_z0 + strap_h / 2.0
    # Outer face of each plate, after biting into the post.
    px = CRATE_X / 2.0 + IRON_T - IRON_BITE
    py = CRATE_Y / 2.0 + IRON_T - IRON_BITE
    for sxn in (-1.0, 1.0):
        for syn in (-1.0, 1.0):
            add_box(
                bm,
                (sxn * (px - IRON_T / 2.0), syn * (py - IRON_WRAP / 2.0), zc),
                (IRON_T, IRON_WRAP, strap_h),
                METAL_IDX,
                xform,
            )
            add_box(
                bm,
                (sxn * (px - IRON_WRAP / 2.0), syn * (py - IRON_T / 2.0), zc),
                (IRON_WRAP, IRON_T, strap_h - 2.0 * IRON_T),
                METAL_IDX,
                xform,
            )
    return wood, side_w


def build_stack_mesh(
    name,
    same_seed=False,
    short_skids=False,
    float_stack=False,
):
    bm = bmesh.new()
    wood_verts = []
    try:
        base_z = 0.0
        for i in range(N_CRATES):
            # Two streams. The design stream is what --same-seed collapses:
            # yaw and plank widths, the things that make each crate its own
            # instance. The placement stream stays per-instance either way,
            # so the falsified stack keeps the same footprint and fails on
            # the variation budget rather than on the bounding box.
            seed = STACK_SEED if same_seed else STACK_SEED + i * 7
            rng = random.Random(seed)
            place = random.Random(STACK_SEED * 31 + i)
            sign = 1.0 if i % 2 == 0 else -1.0
            yaw = sign * (YAW_MIN + rng.random() * (YAW_MAX - YAW_MIN - 0.02))
            offset = (
                0.0 if i == 0 else place.uniform(-OFFSET_MAX, OFFSET_MAX),
                0.0 if i == 0 else place.uniform(-OFFSET_MAX, OFFSET_MAX),
            )
            lift = FLOAT_LIFT if (float_stack and i == N_CRATES - 1) else 0.0
            verts, _widths = build_crate(
                bm,
                base_z + lift,
                yaw,
                rng,
                offset=offset,
                short_skids=short_skids and i == 0,
            )
            wood_verts.extend(verts)
            base_z += CRATE_H - STACK_BITE

        if wood_verts:
            edges = list({e for v in wood_verts for e in v.link_edges if v.is_valid})
            if edges:
                bmesh.ops.bevel(
                    bm,
                    geom=edges,
                    offset=0.0018,
                    segments=1,
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
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
    for i, mat in enumerate((wood, metal)):
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
    """UV bounds plus AABB overlap area, bucketed so this stays linear."""
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
    # Bucket on a grid at least as coarse as the largest island, so any
    # overlapping pair lands in a shared cell. O(n) instead of O(n^2).
    span = max(
        1e-6,
        max((a[2] - a[0]) for a in aabbs),
        max((a[3] - a[1]) for a in aabbs),
    )
    buckets = {}
    for i, a in enumerate(aabbs):
        c0 = int(math.floor(a[0] / span))
        c1 = int(math.floor(a[2] / span))
        r0 = int(math.floor(a[1] / span))
        r1 = int(math.floor(a[3] / span))
        for c in range(c0, c1 + 1):
            for r in range(r0, r1 + 1):
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
        "zero_area": zero_area, "doubles": doubles,
    }


def zfight_pairs(me):
    """Coplanar, near-coincident face pairs that share no vertex.

    Bucketed on a grid of ZFIGHT_EPS so a 2500-face stack does not cost
    three million Python-level pair tests in smoke.
    """
    data = [
        (p.center.copy(), p.normal.copy(), frozenset(p.vertices))
        for p in me.polygons
    ]
    cell = ZFIGHT_EPS
    buckets = {}
    for i, (c, _n, _v) in enumerate(data):
        key = (
            int(math.floor(c.x / cell)),
            int(math.floor(c.y / cell)),
            int(math.floor(c.z / cell)),
        )
        buckets.setdefault(key, []).append(i)
    eps2 = ZFIGHT_EPS * ZFIGHT_EPS
    count = 0
    checked = set()
    for key, members in buckets.items():
        kx, ky, kz = key
        near = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    near.extend(buckets.get((kx + dx, ky + dy, kz + dz), ()))
        for i in members:
            ci, ni, vi = data[i]
            for j in near:
                if j == i:
                    continue
                pair = (i, j) if i < j else (j, i)
                if pair in checked:
                    continue
                checked.add(pair)
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


def mat_of(me, group, face_of_vert):
    member = set(group)
    for i in group:
        for fi in face_of_vert[i]:
            poly = me.polygons[fi]
            if all(v in member for v in poly.vertices):
                return poly.material_index
    return None


def vert_faces(me):
    table = [[] for _ in range(len(me.vertices))]
    for fi, poly in enumerate(me.polygons):
        for vi in poly.vertices:
            table[vi].append(fi)
    return table


def xy_principal(pts):
    """Long/short XY extent and orientation of a shell, free of world yaw.

    Every part is an axis-aligned box in its crate's frame, then rotated
    about Z. A world-AABB test therefore measures the rotated bounding
    box, not the part: a 0.554 m board yawed 0.09 rad reports 0.061 m of
    depth instead of its 0.013 m thickness, and every shape filter keyed
    to thickness silently matches nothing. Recovering the box's own axes
    by principal components makes the classification yaw-invariant, and
    hands back the yaw as a by-product.
    """
    n = len(pts)
    cx = sum(p.x for p in pts) / n
    cy = sum(p.y for p in pts) / n
    sxx = syy = sxy = 0.0
    for p in pts:
        dx, dy = p.x - cx, p.y - cy
        sxx += dx * dx
        syy += dy * dy
        sxy += dx * dy
    theta = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    c, s = math.cos(theta), math.sin(theta)
    us = [(p.x - cx) * c + (p.y - cy) * s for p in pts]
    vs = [-(p.x - cx) * s + (p.y - cy) * c for p in pts]
    e1 = max(us) - min(us)
    e2 = max(vs) - min(vs)
    if e1 < e2:
        e1, e2 = e2, e1
        theta += math.pi / 2.0
    while theta > math.pi / 2.0:
        theta -= math.pi
    while theta <= -math.pi / 2.0:
        theta += math.pi
    return e1, e2, theta


def _levels_from_runners(cands):
    """Stack bases, clustered from the runners the mesh actually has.

    Binning against the declared pitch put a lid — which sits 8 mm below
    the next crate's base — on the wrong level the moment a falsifier
    shifted a crate, and the seat budget then compared a crate against
    itself. Clustering the measured runner heights instead makes the
    bands follow the geometry, including when a falsifier moves it.
    """
    bases = []
    for z in sorted(cands):
        if not bases or z - bases[-1] > CRATE_H * 0.5:
            bases.append(z)
        else:
            bases[-1] = min(bases[-1], z)
    return bases


def classify(me):
    """Bin every wood shell to a stack level and name the parts.

    Two passes: find the runners, cluster their heights into stack bases,
    then assign every shell to the highest base at or below it. Only the
    identification uses the layout; every number a budget later asserts
    on — heights, gaps, yaws, footprints — is measured from vertices.
    """
    vf = vert_faces(me)
    wood = []
    for g in shells(me):
        if mat_of(me, g, vf) != WOOD_IDX:
            continue
        pts = [me.vertices[i].co for i in g]
        zmin = min(p.z for p in pts)
        zmax = max(p.z for p in pts)
        e1, e2, theta = xy_principal(pts)
        wood.append(
            {
                "g": g, "zmin": zmin, "dz": zmax - zmin,
                "e1": e1, "e2": e2, "yaw": theta,
            }
        )

    # e2 is a band, not a ceiling: a side board is the same length and can
    # be thinner than a runner is tall, so an open-ended short-axis test
    # promotes boards to runners and floats the ground budget.
    runner_like = [
        s for s in wood
        if s["dz"] < SKID_H * 1.25
        and s["e1"] > CRATE_X * 0.85
        and SKID_W * 0.6 < s["e2"] < SKID_W * 1.8
    ]
    # Top rails share the runners' footprint and are only 2 mm taller, so
    # a shape filter alone puts four runners on every level. A runner is
    # the lowest thing in its crate; a rail is 27 cm above it.
    bases = _levels_from_runners([s["zmin"] for s in runner_like])
    if len(bases) != N_CRATES:
        bases = [i * (CRATE_H - STACK_BITE) for i in range(N_CRATES)]

    def level_of(z):
        lvl = 0
        for i, b in enumerate(bases):
            if z >= b - 1e-4:
                lvl = i
        return lvl

    out = {i: {"skids": [], "lids": [], "boards": []} for i in range(N_CRATES)}
    for s in wood:
        lvl = level_of(s["zmin"])
        rel = s["zmin"] - bases[lvl]
        if s in runner_like and rel < SKID_H * 3.0:
            out[lvl]["skids"].append(s)
        elif (
            s["dz"] < SLAT_T * 2.2
            and s["e1"] > CRATE_Y * 0.9
            and rel > CRATE_H * 0.6
        ):
            out[lvl]["lids"].append(s)
        elif (
            SLAT_T * 1.5 < s["dz"] < BODY_H * 0.7
            and s["e1"] > CRATE_X * 0.85
            and s["e2"] < SLAT_T * 2.2
        ):
            out[lvl]["boards"].append(dict(s, h=s["dz"]))
    return out, bases


def _bvh_gap(me, hosts, guests):
    """Worst surface gap from any guest shell to the host surface.

    Surface-to-surface, not vertex-to-vertex: a runner crossing a lid
    plank has no vertex near the plank's own vertices, and a vertex
    metric would report a large gap for parts that are in fact seated.
    Overlapping shells return 0.
    """
    if not hosts or not guests:
        return 99.0
    bm_h = bmesh.new()
    try:
        bm_h.from_mesh(me)
        keep = set()
        for g in hosts:
            keep.update(g)
        drop = [f for f in bm_h.faces if not all(v.index in keep for v in f.verts)]
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
                worst = max(worst, best)
            finally:
                bm_g.free()
        return worst
    finally:
        bm_h.free()


def stack_audit(me):
    """Ground supports, crate-to-crate seats, and per-instance variation."""
    by_level, bases = classify(me)

    ground = by_level[0]["skids"]
    ground_n = len(ground)
    # max, not min: one planted runner would hide a floating one.
    ground_z = max((s["zmin"] for s in ground), default=99.0)

    seat = 0.0
    seats_checked = 0
    for i in range(1, N_CRATES):
        hosts = [s["g"] for s in by_level[i - 1]["lids"]]
        guests = [s["g"] for s in by_level[i]["skids"]]
        if hosts and guests:
            seats_checked += 1
            seat = max(seat, _bvh_gap(me, hosts, guests))
        else:
            seat = 99.0

    widths = {}
    yaws = {}
    for i in range(N_CRATES):
        widths[i] = sorted(round(b["h"], 6) for b in by_level[i]["boards"])
        sk = by_level[i]["skids"]
        if sk:
            yaws[i] = sum(s["yaw"] for s in sk) / len(sk)

    width_spread = 0.0
    pairs = 0
    for i in range(N_CRATES):
        for j in range(i + 1, N_CRATES):
            wi, wj = widths.get(i) or [], widths.get(j) or []
            if wi and len(wi) == len(wj):
                d = max(abs(a - b) for a, b in zip(wi, wj))
                width_spread = d if pairs == 0 else min(width_spread, d)
                pairs += 1

    yaw_vals = [yaws[i] for i in range(N_CRATES) if i in yaws]
    yaw_spread = 0.0
    if len(yaw_vals) == N_CRATES:
        yaw_spread = min(
            abs(yaw_vals[i] - yaw_vals[j])
            for i in range(N_CRATES)
            for j in range(i + 1, N_CRATES)
        )
    return {
        "ground_n": ground_n,
        "ground_z": ground_z,
        "seat": seat,
        "seats": seats_checked,
        "lids": sum(len(by_level[i]["lids"]) for i in range(N_CRATES)),
        "boards": sum(len(by_level[i]["boards"]) for i in range(N_CRATES)),
        "board_counts": [len(by_level[i]["boards"]) for i in range(N_CRATES)],
        "skid_counts": [len(by_level[i]["skids"]) for i in range(N_CRATES)],
        "width_spread": width_spread,
        "width_pairs": pairs,
        "yaw_spread": yaw_spread,
        "yaw_min": min((abs(y) for y in yaw_vals), default=0.0),
        "yaw_max": max((abs(y) for y in yaw_vals), default=9.0),
        "yaws": [round(y, 4) for y in yaw_vals],
        "bases": [round(b, 4) for b in bases],
    }


def crate_size_audit(me, yaws, bases):
    """Each crate's own footprint, measured in that crate's frame.

    The stack AABB cannot cover this: it is the union of three yawed
    boxes, so a crate could drift to any size underneath it. Un-rotating
    by the yaw this crate was measured to have is what makes the number
    the crate's own width and depth rather than its rotated bounding box.
    """
    out = []
    for i, base in enumerate(bases):
        # Body band only. A band that reaches the crate base also picks
        # up the runners of the crate above, which carry a different yaw
        # and inflate the footprint by two centimetres.
        lo = base + SKID_H + 0.012
        hi = base + SKID_H + BODY_H - 0.012
        pts = [v.co for v in me.vertices if lo <= v.co.z <= hi]
        if not pts or i >= len(yaws):
            out.append((0.0, 0.0))
            continue
        c, s = math.cos(-yaws[i]), math.sin(-yaws[i])
        us = [p.x * c - p.y * s for p in pts]
        vs = [p.x * s + p.y * c for p in pts]
        out.append((max(us) - min(us), max(vs) - min(vs)))
    return out


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, STACK_H * 0.5))
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
    img = bpy.data.images.new("StackNrm", size, size, alpha=True, float_buffer=False)
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
    float_stack=False,
    same_seed=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        same_seed=same_seed,
        short_skids=short_skids,
        float_stack=float_stack,
    )
    nothing = (None,) * 5
    low = build_stack_mesh("StackLow", **flags)
    high = build_stack_mesh("StackHigh", **flags)
    wood = principled(
        "StackWood", (0.40, 0.18, 0.065, 1.0), 0.0, 0.55,
        noise_scale=9.0, wear=(0.20, 0.085, 0.030, 1.0),
    )
    metal = principled(
        "StackMetal", (0.20, 0.19, 0.180, 1.0), 0.88, 0.33,
        noise_scale=6.0, wear=(0.10, 0.095, 0.088, 1.0),
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
        return (fail("stack mesh did not build", 3),) + nothing

    base_tris = triangle_count(low.data)
    mats = [s for s in low.data.materials if s is not None]
    nmat = len(mats)
    distinct_mats = len({id(s) for s in mats})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, wood)
    if img is None:
        return (fail("stack has no UV layer", 3),) + nothing
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "StackLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "StackLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_stack_mesh("StackColSrc", **flags)
    collider = convex_hull_collider(collider_src, "StackCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(), f"bdt_crate_stack_{os.getpid()}.glb"
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    st = stack_audit(low.data)
    crates = crate_size_audit(low.data, st['yaws'], st['bases'])

    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured mat_index_counts={idx_counts}")
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
        f"outer={OUTER_SIZE} zmin={bb[2]:.5f}"
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
        f"measured stack ground_n={st['ground_n']} ground_z={st['ground_z']:.5f} "
        f"seats={st['seats']} seat_gap={st['seat']:.5f} lids={st['lids']} "
        f"boards={st['boards']} per_level_boards={st['board_counts']} "
        f"per_level_skids={st['skid_counts']}"
    )
    print(
        f"measured variation yaws={st['yaws']} yaw_spread={st['yaw_spread']:.4f} "
        f"yaw_min={st['yaw_min']:.4f} yaw_max={st['yaw_max']:.4f} "
        f"width_spread={st['width_spread']:.5f} pairs={st['width_pairs']}"
    )
    print(
        "measured crate_footprints="
        f"{[(round(c[0], 4), round(c[1], 4)) for c in crates]}"
    )

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(
            f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4
        ),) + nothing
    if nmat != MATERIAL_COUNT or distinct_mats != MATERIAL_COUNT:
        return (fail(
            f"material slots {nmat} distinct {distinct_mats} != {MATERIAL_COUNT}", 5
        ),) + nothing
    if idx_counts.get(METAL_IDX, 0) < METAL_FACES_MIN:
        return (fail(
            f"metal faces {idx_counts.get(METAL_IDX, 0)} < {METAL_FACES_MIN}", 5
        ),) + nothing
    if idx_counts.get(WOOD_IDX, 0) < WOOD_FACES_MIN:
        return (fail(
            f"wood faces {idx_counts.get(WOOD_IDX, 0)} < {WOOD_FACES_MIN}", 5
        ),) + nothing
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(
            f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6
        ),) + nothing
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + nothing
    if (
        abs(size_x - OUTER_SIZE[0]) > BBOX_TOL
        or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
        or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL
    ):
        return (fail(
            f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8
        ),) + nothing
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(
            f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
            "(--skip-decimate is the designed fail)", 9
        ),) + nothing
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(
            f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9
        ),) + nothing
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + nothing
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(
            f"bake failed result={bake_result} has_data={img.has_data}", 12
        ),) + nothing
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + nothing
    if (
        hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"]
        or hyg["zero_area"] or hyg["doubles"] or hyg["ngons"] or zf
    ):
        return (fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf} "
            "(--stray-vert is the designed fail)", 15
        ),) + nothing
    if abs(bb[2]) > ZMIN_EPS:
        return (fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)", 16
        ),) + nothing
    if st["ground_n"] < GROUND_SKIDS_MIN or st["ground_z"] > SKID_Z_MAX:
        return (fail(
            f"ground runners {st['ground_n']} ground_z={st['ground_z']:.5f} "
            "(--short-skids is the designed fail)", 16
        ),) + nothing
    if st["seats"] != N_CRATES - 1 or st["seat"] > STACK_SEAT_MAX:
        return (fail(
            f"stack seat gap {st['seat']:.5f} > {STACK_SEAT_MAX} over "
            f"{st['seats']} seats (--float-stack is the designed fail)", 18
        ),) + nothing
    for i, (cx, cy) in enumerate(crates):
        if abs(cx - BODY_X) > CRATE_TOL or abs(cy - BODY_Y) > CRATE_TOL:
            return (fail(
                f"crate {i} body footprint ({cx:.4f},{cy:.4f}) off "
                f"({BODY_X:.4f},{BODY_Y:.4f})", 19
            ),) + nothing
    if st["yaw_min"] < YAW_MIN * 0.8 or st["yaw_max"] > YAW_MAX * 1.2:
        return (fail(
            f"crate yaws {st['yaws']} outside [{YAW_MIN}, {YAW_MAX}]", 20
        ),) + nothing
    if st["yaw_spread"] < YAW_SPREAD_MIN or st["width_spread"] < WIDTH_SPREAD_MIN:
        return (fail(
            f"per-instance variation too small: yaw_spread={st['yaw_spread']:.4f} "
            f"(min {YAW_SPREAD_MIN}) width_spread={st['width_spread']:.5f} "
            f"(min {WIDTH_SPREAD_MIN}) — the three crates are copies, not "
            "instances (--same-seed is the designed fail)", 20
        ),) + nothing
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

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=16.0)
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
    wall.location = (0.0, 9.0, 0.0)
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

    light("Key", (-3.2, -4.0, 5.2), 545.0, 5.0, (1.0, 0.96, 0.90), (44, 0, -38))
    light("Fill", (4.2, -2.8, 1.5), 145.0, 9.0, (0.75, 0.85, 1.00), (72, 0, 54))
    light("Rim", (-1.5, 3.4, 2.6), 320.0, 3.0, (0.60, 0.78, 1.00), (-64, 0, 200))
    # Wedge sits between the subject and the wall so the pool lands on the
    # backdrop, not across the crates.
    light("Wedge", (1.2, 2.7, 2.3), 380.0, 7.0, (1.0, 0.76, 0.50), (-92, 0, 196))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 52.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.62, -2.42, 1.06)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, STACK_H * 0.46)
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
    p.add_argument("--float-stack", action="store_true")
    p.add_argument("--same-seed", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_skids=args.short_skids,
        float_stack=args.float_stack,
        same_seed=args.same_seed,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("crate-stack OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
