"""Game-ready wooden barrel — a showcase piece, not an example.

Asserts budget conformance of a procedural staved barrel (tight staves
with seeded width jitter, heads seated in a croze, iron hoops lofted on
the stave faces, a bung) after composing shipped pipeline pieces: bmesh
construction, UVs, two materials, high-to-low normal bake, LOD chain,
convex collider, Unity glTF export.

The old piece was a 12-gon with 5 mm daylight between identical staves
and circular capped-cylinder hoops that floated off every stave face.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-staves`` named stave
supports, ``--float-head`` head-croze joint-fit, ``--one-piece-head``
head boards (one slab instead of boards), ``--round-band`` hoop seat
(hoop generated on a circle instead of the stave chords).

Fixed seed 17 for stave-width jitter. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python wooden_barrel.py --
    blender --background --python wooden_barrel.py -- --skip-decimate
    blender --background --python wooden_barrel.py -- --output barrel.png
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

# Wine-cask scale: 88 cm tall, 72 cm at the bulge.
HEIGHT = 0.88
R_END = 0.27
R_MID = 0.36
N_STAVES = 20
STAVE_THICK = 0.028
N_RINGS = 8
STAVE_SEED = 17
STAVE_JITTER = 0.08
GAP_M = 0.0012
HOOP_ZS = (0.085, 0.255, 0.625, 0.795)
HOOP_H = 0.030
HOOP_PROUD = 0.007
HOOP_BITE = 0.003
HOOP_CHAMFER = 0.003
HOOP_BITE_MIN = 0.0012
HOOP_BITE_MAX = 0.008
LID_T = 0.028
CHIME = 0.014
CROZE_BITE = 0.003
HEAD_GAP_MAX = 0.010
BUNG_Z = 0.44
BUNG_R = 0.022
BUNG_SEGS = 24
STAVE_ZMIN_MAX = 0.001
SHORT_STAVES_LIFT = 0.045
LIFT_Z = 0.05
AREA_EPS = 1e-10
DOUBLES_EPS = 1e-5
ZMIN_EPS = 1e-4
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.998
BODY_TOL = 0.04
BODY_DIA = 0.714
BODY_H = 0.880
BBOX_TOL = 0.015
OUTER_SIZE = (0.722, 0.714, 0.880)

BASE_TRIS_MIN = 6000
BASE_TRIS_MAX = 8500
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
WOOD_FACES_MIN = 400
METAL_FACES_MIN = 200
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 400
BAKE_RES = 256
CAGE_EXTRUSION = 0.05
STAVE_COUNT = N_STAVES

WOOD_IDX = 0
METAL_IDX = 1

# Each head is HEAD_BOARDS boards cut across X from the croze outline, with
# a BOARD_SEAM between neighbours. A board is a thin wooden shell at least
# BOARD_MIN_SPAN wide in plan (the bung is 0.05, the narrowest board 0.36).
HEAD_BOARDS = 4
BOARD_SEAM = 0.0015
BOARD_SEAM_MIN = 0.0008
BOARD_SEAM_MAX = 0.003
BOARD_MIN_SPAN = 0.30
# Per-piece wood tone jitter and grain frequency, as in shipping-crate.
PLANK_TONE_JITTER = 0.28
TONE_SEED = 29
WOOD_GRAIN_SCALE = 30.0


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


def radius_at(z):
    return R_END + (R_MID - R_END) * math.sin(math.pi * z / HEIGHT)


def stave_spans(n, gap_ang, jitter, seed):
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


def host_outer_r(u, z, spans, round_band):
    """Radial distance of the outer stave face at angle u.

    One function owns the surface. The hoop, the head croze and the
    assertions all evaluate it. ``round_band`` is the falsifier: a circle
    of ``radius_at(z)`` instead of the stave chord, which is what made
    the old cylinder float off every flat.
    """
    r = radius_at(z)
    if round_band:
        return r
    u = u % (2.0 * math.pi)
    for a0, a1 in spans:
        if a0 - 1e-9 <= u <= a1 + 1e-9:
            mid = 0.5 * (a0 + a1)
            half = 0.5 * (a1 - a0)
            den = math.cos(u - mid)
            if abs(den) < 1e-4:
                return r * math.cos(half)
            return r * math.cos(half) / den
    return r


def loft_cyclic(bm, sections, mat_idx):
    vert_rings = [[bm.verts.new(p) for p in s] for s in sections]
    m = len(vert_rings)
    n = len(vert_rings[0])
    faces = []
    for k in range(m):
        a = vert_rings[k]
        b = vert_rings[(k + 1) % m]
        for i in range(n):
            j = (i + 1) % n
            face = bm.faces.new((a[i], a[j], b[j], b[i]))
            face.material_index = mat_idx
            faces.append(face)
    return [v for ring in vert_rings for v in ring], faces


def fan_cap(bm, ring, mat_idx, flip=False):
    center = Vector((0.0, 0.0, 0.0))
    for v in ring:
        center += v.co
    center /= len(ring)
    hub = bm.verts.new(center)
    faces = []
    n = len(ring)
    for i in range(n):
        vs = (hub, ring[i], ring[(i + 1) % n])
        if flip:
            vs = (hub, vs[2], vs[1])
        face = bm.faces.new(vs)
        face.material_index = mat_idx
        faces.append(face)
    return hub, faces


def croze_xy(spans, z, bite, shrink=0.0):
    """Head outline = inner stave chords plus croze bite.

    A circle leaves a triangular slot at every stave joint. Sampling
    each stave at both edges and the mid-face, then connecting in
    order, makes the head follow the same host as the hoops.
    """
    pts = []
    for a0, a1 in spans:
        for u in (a0, 0.5 * (a0 + a1), a1):
            r = host_outer_r(u, z, spans, False) - STAVE_THICK + bite - shrink
            pts.append((r * math.cos(u), r * math.sin(u)))
    return pts


def add_polygon_disk(bm, z0, z1, xy_ring, mat_idx):
    rings = []
    for z in (z0, z1):
        ring = [bm.verts.new((x, y, z)) for x, y in xy_ring]
        rings.append(ring)
    a, b = rings
    n = len(xy_ring)
    for i in range(n):
        j = (i + 1) % n
        face = bm.faces.new((a[i], a[j], b[j], b[i]))
        face.material_index = mat_idx
    fan_cap(bm, a, mat_idx, flip=True)
    fan_cap(bm, b, mat_idx, flip=False)


def add_bung(bm, u, z, spans):
    r_out = host_outer_r(u, z, spans, False)
    cu, su = math.cos(u), math.sin(u)
    radial = Vector((cu, su, 0.0))
    origin = radial * (r_out - STAVE_THICK * 0.45)
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=True,
        segments=BUNG_SEGS,
        radius1=BUNG_R,
        radius2=BUNG_R * 0.92,
        depth=STAVE_THICK + 0.018,
    )
    verts = list(geo["verts"])
    quat = Vector((0.0, 0.0, 1.0)).rotation_difference(radial)
    rot = quat.to_matrix()
    for v in verts:
        v.co = rot @ v.co + origin + Vector((0.0, 0.0, z))
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = WOOD_IDX
    return verts


def build_hoops(bm, spans, round_band):
    faces_all = []
    for z_mid in HOOP_ZS:
        z0 = z_mid - HOOP_H * 0.5
        z1 = z_mid + HOOP_H * 0.5
        c = HOOP_CHAMFER
        sections = []
        samples = []
        for a0, a1 in spans:
            samples.append(a0)
            samples.append(0.5 * (a0 + a1))
            samples.append(a1)
        for u in samples:
            cu, su = math.cos(u), math.sin(u)
            r0 = host_outer_r(u, z0, spans, round_band)
            r1 = host_outer_r(u, z1, spans, round_band)
            profile = (
                (r0 - HOOP_BITE, z0),
                (r0 + HOOP_PROUD - c, z0),
                (r0 + HOOP_PROUD, z0 + c),
                (r1 + HOOP_PROUD, z1 - c),
                (r1 + HOOP_PROUD - c, z1),
                (r1 - HOOP_BITE, z1),
            )
            sections.append([Vector((r * cu, r * su, z)) for r, z in profile])
        _verts, faces = loft_cyclic(bm, sections, METAL_IDX)
        faces_all.extend(faces)
    return faces_all


def build_staves(bm, spans, z0, bevel_offset, bevel_segments):
    zs = [HEIGHT * i / (N_RINGS - 1) for i in range(N_RINGS)]
    stave_verts = []
    for a0, a1 in spans:
        outer = []
        inner = []
        for z in zs:
            r = radius_at(z)
            ov = (
                bm.verts.new((r * math.cos(a0), r * math.sin(a0), z0 + z)),
                bm.verts.new((r * math.cos(a1), r * math.sin(a1), z0 + z)),
            )
            ri = r - STAVE_THICK
            iv = (
                bm.verts.new((ri * math.cos(a0), ri * math.sin(a0), z0 + z)),
                bm.verts.new((ri * math.cos(a1), ri * math.sin(a1), z0 + z)),
            )
            outer.append(ov)
            inner.append(iv)
            stave_verts.extend(ov)
            stave_verts.extend(iv)
        for k in range(N_RINGS - 1):
            o0a, o0b = outer[k]
            o1a, o1b = outer[k + 1]
            i0a, i0b = inner[k]
            i1a, i1b = inner[k + 1]
            for vs in (
                (o0a, o1a, o1b, o0b),
                (i0b, i1b, i1a, i0a),
                (o0a, i0a, i1a, o1a),
                (o0b, o1b, i1b, i0b),
            ):
                face = bm.faces.new(vs)
                face.material_index = WOOD_IDX
        top = bm.faces.new((outer[-1][0], outer[-1][1], inner[-1][1], inner[-1][0]))
        top.material_index = WOOD_IDX
        bot = bm.faces.new((outer[0][1], outer[0][0], inner[0][0], inner[0][1]))
        bot.material_index = WOOD_IDX
    if bevel_offset > 0.0:
        long_edges = []
        seen = set()
        for v in stave_verts:
            for e in v.link_edges:
                if e in seen:
                    continue
                seen.add(e)
                a, b = e.verts
                if abs(a.co.z - b.co.z) > 0.02:
                    long_edges.append(e)
        if long_edges:
            bmesh.ops.bevel(
                bm,
                geom=long_edges,
                offset=bevel_offset,
                segments=bevel_segments,
                profile=0.5,
                affect="EDGES",
                clamp_overlap=True,
            )
    return stave_verts


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


def build_barrel_mesh(
    name,
    bevel_offset,
    bevel_segments,
    short_staves=False,
    float_head=False,
    round_band=False,
    one_piece_head=False,
):
    bm = bmesh.new()
    gap_ang = GAP_M / R_MID
    spans = stave_spans(N_STAVES, gap_ang, STAVE_JITTER, STAVE_SEED)
    z0 = SHORT_STAVES_LIFT if short_staves else 0.0
    try:
        build_staves(bm, spans, z0, bevel_offset, bevel_segments)
        shrink = 0.028 if float_head else 0.0
        bot_z0 = CHIME
        bot_z1 = CHIME + LID_T
        top_z0 = HEIGHT - CHIME - LID_T
        top_z1 = HEIGHT - CHIME
        n_boards = 1 if one_piece_head else HEAD_BOARDS
        add_board_disk(
            bm, bot_z0, bot_z1,
            croze_xy(spans, 0.5 * (bot_z0 + bot_z1), CROZE_BITE, shrink),
            WOOD_IDX, n_boards,
        )
        add_board_disk(
            bm, top_z0, top_z1,
            croze_xy(spans, 0.5 * (top_z0 + top_z1), CROZE_BITE, shrink),
            WOOD_IDX, n_boards,
        )
        add_bung(bm, 0.5 * (spans[0][0] + spans[0][1]), BUNG_Z, spans)
        build_hoops(bm, spans, round_band)
        triangulate_ngons(bm)
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
    staves = []
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dz = a[5] - a[2]
        if dz > 0.50:
            staves.append(a)
    stave_z = min((a[2] for a in staves), default=99.0)
    return {"staves": len(staves), "stave_z": stave_z}


def hoop_seat(me, spans):
    groups = shells(me)
    bites = []
    for g in groups:
        if mat_of(me, g) != METAL_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if dz > 0.08 or max(dx, dy) < 0.40:
            continue
        rs = [math.hypot(me.vertices[i].co.x, me.vertices[i].co.y) for i in g]
        for i, r in zip(g, rs):
            p = me.vertices[i].co
            u = math.atan2(p.y, p.x)
            host = host_outer_r(u, p.z, spans, False)
            if r > host + 0.0005:
                continue
            bites.append(host - r)
    if not bites:
        return 0.05, 0.05
    return min(bites), max(bites)


def head_gap(me, spans):
    groups = shells(me)
    heads, staves = [], []
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dz = a[5] - a[2]
        if dz < 0.06 and max(a[3] - a[0], a[4] - a[1]) >= BOARD_MIN_SPAN:
            heads.append(g)
        elif dz > 0.50:
            staves.append(g)
    if not heads or not staves:
        return 99.0
    bm_s = bmesh.new()
    try:
        bm_s.from_mesh(me)
        keep = set()
        for g in staves:
            keep.update(g)
        drop = [f for f in bm_s.faces if not all(v.index in keep for v in f.verts)]
        if drop:
            bmesh.ops.delete(bm_s, geom=drop, context="FACES")
        if not bm_s.faces:
            return 99.0
        tree = BVHTree.FromBMesh(bm_s)
        worst = 0.0
        for g in heads:
            a = shell_aabb(me, g)
            if a[2] > 0.2:
                continue
            rmax = max(math.hypot(me.vertices[i].co.x, me.vertices[i].co.y) for i in g)
            for i in g:
                p = me.vertices[i].co
                if math.hypot(p.x, p.y) < 0.90 * rmax:
                    continue
                loc, _n, _i, dist = tree.find_nearest(p)
                if loc is None:
                    continue
                worst = max(worst, dist)
        return worst
    finally:
        bm_s.free()


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

    Every stave and every board is its own shell, so each gets one tone and
    grain running along its own long axis (up the curved staves, across
    the flat boards).
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
    """Grain along each stave or board (``GrainDir``), tone per piece (``PlankTone``)."""
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


def clip_x(ring, x, keep_above):
    """Sutherland-Hodgman clip of a closed xy ring against the line X = x."""
    out = []
    n = len(ring)
    for i in range(n):
        p, q = ring[i], ring[(i + 1) % n]
        p_in = p[0] >= x if keep_above else p[0] <= x
        q_in = q[0] >= x if keep_above else q[0] <= x
        if p_in:
            out.append(p)
        if p_in != q_in:
            t = (x - p[0]) / (q[0] - p[0])
            out.append((x, p[1] + t * (q[1] - p[1])))
    # a cut landing on an existing vertex would leave a zero-length edge
    clean = []
    for p in out:
        if not clean or math.dist(p, clean[-1]) > 1e-4:
            clean.append(p)
    if len(clean) > 2 and math.dist(clean[0], clean[-1]) <= 1e-4:
        clean.pop()
    return clean


def add_board_disk(bm, z0, z1, xy_ring, mat_idx, n_boards):
    """A head of ``n_boards`` boards, the outline cut across X with seams between.

    Each board is the croze outline clipped to its strip, so the outer
    edge of every board is still the croze and the head seats exactly
    as the one-piece disk did.
    """
    xs = [p[0] for p in xy_ring]
    x_lo, x_hi = min(xs), max(xs)
    w = (x_hi - x_lo) / n_boards
    for k in range(n_boards):
        ring = xy_ring
        if k > 0:
            ring = clip_x(ring, x_lo + k * w + BOARD_SEAM * 0.5, True)
        if k < n_boards - 1:
            ring = clip_x(ring, x_lo + (k + 1) * w - BOARD_SEAM * 0.5, False)
        add_polygon_disk(bm, z0, z1, ring, mat_idx)


def board_audit(me, z_lo, z_hi):
    """Boards of the flat wooden disk between ``z_lo`` and ``z_hi``: count and seams.

    A board is a thin wooden shell wide in plan. Sorted across X, the
    seam is the gap between one board's max X and the next one's min X.
    """
    boards = []
    for g in shells(me):
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        if a[5] - a[2] > 0.06 or max(a[3] - a[0], a[4] - a[1]) < BOARD_MIN_SPAN:
            continue
        if not (z_lo <= 0.5 * (a[2] + a[5]) <= z_hi):
            continue
        boards.append(a)
    boards.sort(key=lambda a: a[0])
    seams = [boards[i + 1][0] - boards[i][3] for i in range(len(boards) - 1)]
    return len(boards), seams


def barrel_materials():
    """(wood, iron): shared by the check, the render and inspection."""
    wood = wood_material("BarrelWood")
    metal = principled(
        "BarrelHoop", (0.17, 0.165, 0.155, 1.0), 0.80, 0.46,
        noise_scale=18.0, wear=(0.20, 0.085, 0.032, 1.0),
    )
    return wood, metal


def body_plan(me):
    groups = shells(me)
    xs, ys, z0s, z1s = [], [], [], []
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        if a[5] - a[2] < 0.50:
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
        bm.verts.new((0.0, 0.0, HEIGHT * 0.5))
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
    img = bpy.data.images.new("BarrelNrm", size, size, alpha=True, float_buffer=False)
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
    short_staves=False,
    float_head=False,
    round_band=False,
    one_piece_head=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        short_staves=short_staves,
        float_head=float_head,
        round_band=round_band,
        one_piece_head=one_piece_head,
    )
    low = build_barrel_mesh("BarrelLow", 0.004, 2, **flags)
    high = build_barrel_mesh("BarrelHigh", 0.004, 4, **flags)
    wood, metal = barrel_materials()
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
        bpy.context.view_layer.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("barrel mesh did not build", 3), None, None, None, None, None

    spans = stave_spans(N_STAVES, GAP_M / R_MID, STAVE_JITTER, STAVE_SEED)
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
    bite_min, bite_max = hoop_seat(low.data, spans)
    hgap = head_gap(low.data, spans)
    boards_bot, seams_bot = board_audit(low.data, 0.0, 0.2)
    boards_top, seams_top = board_audit(low.data, HEIGHT - 0.2, HEIGHT + 0.2)
    seams = seams_bot + seams_top
    dia, ht = body_plan(low.data)
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}"
    )
    print(
        f"measured staves={sup['staves']} stave_z={sup['stave_z']:.5f} "
        f"hoop_bite={bite_min:.5f}..{bite_max:.5f} head_gap={hgap:.5f} "
        f"body={dia:.4f}x{ht:.4f}"
    )
    print(
        f"measured head_boards={boards_bot}+{boards_top} "
        f"seams={min(seams, default=0.0):.5f}..{max(seams, default=0.0):.5f}"
    )

    img, tex = setup_bake_image(low, wood)
    if img is None:
        return fail("barrel has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BarrelLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BarrelLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_barrel_mesh("BarrelColSrc", 0.0, 1)
    collider = convex_hull_collider(collider_src, "BarrelCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_wooden_barrel_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender points TMPDIR at the working directory, so the export must not
    # outlive the measurement.
    if os.path.exists(export_path):
        os.remove(export_path)

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
    if idx_counts.get(METAL_IDX, 0) < METAL_FACES_MIN:
        return fail(
            f"metal hoop faces {idx_counts.get(METAL_IDX, 0)} < {METAL_FACES_MIN}",
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
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf} "
            "(--stray-vert is the designed fail)",
            15,
        ), None, None, None, None, None
    if (
        abs(bb[2]) > ZMIN_EPS
        or sup["staves"] != STAVE_COUNT
        or sup["stave_z"] > STAVE_ZMIN_MAX
    ):
        return fail(
            f"zmin {bb[2]:.6f} staves={sup['staves']} stave_z={sup['stave_z']:.5f} "
            "(--lift-z / --short-staves is the designed fail)",
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
    if hgap > HEAD_GAP_MAX:
        return fail(
            f"head-croze gap {hgap:.5f} > {HEAD_GAP_MAX} "
            "(--float-head is the designed fail)",
            17,
        ), None, None, None, None, None
    if (
        boards_bot != HEAD_BOARDS
        or boards_top != HEAD_BOARDS
        or min(seams, default=0.0) < BOARD_SEAM_MIN
        or max(seams, default=99.0) > BOARD_SEAM_MAX
    ):
        return fail(
            f"head boards {boards_bot}+{boards_top} != {HEAD_BOARDS} each, or "
            f"seams {min(seams, default=0.0):.5f}..{max(seams, default=0.0):.5f} "
            f"outside [{BOARD_SEAM_MIN}, {BOARD_SEAM_MAX}] "
            "(--one-piece-head is the designed fail)",
            17,
        ), None, None, None, None, None
    if bite_min < HOOP_BITE_MIN or bite_max > HOOP_BITE_MAX:
        return fail(
            f"hoop bite {bite_min:.5f}..{bite_max:.5f} "
            f"outside [{HOOP_BITE_MIN}, {HOOP_BITE_MAX}] "
            "(--round-band is the designed fail)",
            18,
        ), None, None, None, None, None
    if abs(dia - BODY_DIA) > BODY_TOL or abs(ht - BODY_H) > BODY_TOL:
        return fail(
            f"body plan {dia:.4f}x{ht:.4f} off {BODY_DIA}x{BODY_H}",
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


def render_still(low, wood, _tex, path, engine):
    scene = bpy.context.scene
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(-32.0)
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
    cam.location = (1.68, -2.38, 1.38)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, HEIGHT / 2.0 + 0.02)
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
    p.add_argument("--short-staves", action="store_true")
    p.add_argument("--float-head", action="store_true")
    p.add_argument("--round-band", action="store_true")
    p.add_argument("--one-piece-head", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_staves=args.short_staves,
        float_head=args.float_head,
        round_band=args.round_band,
        one_piece_head=args.one_piece_head,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("wooden-barrel OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
