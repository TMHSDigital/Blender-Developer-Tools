"""Game-ready wooden bucket — a showcase piece, not an example.

Asserts budget conformance of a procedural coopered bucket (tight staves
with seeded width jitter, a bottom seated in a croze, iron hoops lofted
on the stave faces, ear rings, a round rope bail through the rings)
after composing shipped pipeline pieces: bmesh construction, UVs, three
materials, high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

The old piece overlapped 14 identical staves into a 14-gon, wrapped them
in capped-cylinder hoops that floated off the flats, and lofted the bail
from 12 boxes that never entered the ear rings.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-staves`` named stave
supports, ``--float-handle`` bail-ear joint-fit, ``--float-bottom``
floor-croze joint-fit, ``--round-band`` hoop seat (hoop generated on a
circle instead of the stave chords).

Fixed seed 17 for stave-width jitter. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python wooden_bucket.py --
    blender --background --python wooden_bucket.py -- --skip-decimate
    blender --background --python wooden_bucket.py -- --output bucket.png
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

# Pail scale: 36 cm bowl, 33 cm rim.
HEIGHT = 0.36
R_BOT = 0.125
R_TOP = 0.168
BULGE = 0.012
N_STAVES = 16
STAVE_THICK = 0.018
N_RINGS = 6
STAVE_SEED = 17
STAVE_JITTER = 0.08
GAP_M = 0.0007
HOOP_ZS = (0.055, 0.155, 0.300)
HOOP_H = 0.022
HOOP_PROUD = 0.006
HOOP_BITE = 0.0025
HOOP_CHAMFER = 0.0025
HOOP_BITE_MIN = 0.0010
HOOP_BITE_MAX = 0.007
BOTTOM_T = 0.022
CHIME = 0.008
CROZE_BITE = 0.0025
FLOOR_GAP_MAX = 0.008
BAIL_R = 0.008
BAIL_SEGS = 24
BAIL_PIPE = 8
EAR_Z = HEIGHT - 0.016
RING_MAJOR = 0.013
RING_MINOR = 0.0035
BAIL_GAP_MAX = 0.006
STAVE_ZMIN_MAX = 0.001
SHORT_STAVES_LIFT = 0.040
LIFT_Z = 0.05
AREA_EPS = 1e-10
DOUBLES_EPS = 1e-5
ZMIN_EPS = 1e-4
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.998
BODY_TOL = 0.04
BODY_DIA = 0.335
BODY_H = 0.360
BBOX_TOL = 0.015
OUTER_SIZE = (0.383, 0.346, 0.527)

BASE_TRIS_MIN = 4000
BASE_TRIS_MAX = 5800
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
WOOD_FACES_MIN = 350
METAL_FACES_MIN = 180
ROPE_FACES_MIN = 40
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 420
BAKE_RES = 256
CAGE_EXTRUSION = 0.06
STAVE_COUNT = N_STAVES

WOOD_IDX = 0
METAL_IDX = 1
ROPE_IDX = 2


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
    t = max(0.0, min(1.0, z / HEIGHT))
    return R_BOT + (R_TOP - R_BOT) * t + BULGE * math.sin(math.pi * t)


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


def loft_rings(bm, rings, mat_idx, cap_start=True, cap_end=True):
    n = len(rings[0])
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            face = bm.faces.new((a[i], a[j], b[j], b[i]))
            face.material_index = mat_idx
    if cap_start:
        fan_cap(bm, rings[0], mat_idx, flip=True)
    if cap_end:
        fan_cap(bm, rings[-1], mat_idx, flip=False)


def fan_cap(bm, ring, mat_idx, flip=False):
    center = Vector((0.0, 0.0, 0.0))
    for v in ring:
        center += v.co
    center /= len(ring)
    hub = bm.verts.new(center)
    n = len(ring)
    for i in range(n):
        vs = (hub, ring[i], ring[(i + 1) % n])
        if flip:
            vs = (hub, vs[2], vs[1])
        face = bm.faces.new(vs)
        face.material_index = mat_idx
    return hub


def croze_xy(spans, z, bite, shrink=0.0):
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


def add_torus(bm, loc, major, minor, n_major, n_minor, mat_idx, euler=(0.0, 0.0, 0.0)):
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
    verts = [v for ring in rings for v in ring]
    for i in range(n_major):
        i2 = (i + 1) % n_major
        for j in range(n_minor):
            j2 = (j + 1) % n_minor
            face = bm.faces.new(
                (rings[i][j], rings[i2][j], rings[i2][j2], rings[i][j2])
            )
            face.material_index = mat_idx
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
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
    loft_rings(bm, rings, mat_idx, cap_start=True, cap_end=True)


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


def build_hoops(bm, spans, round_band):
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
        loft_cyclic(bm, sections, METAL_IDX)


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
                if abs(a.co.z - b.co.z) > 0.015:
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


def add_ears_and_bail(bm, spans, float_handle):
    """Ear plates + flat rings (hole along Z) and a round bail through them.

    Ring centres sit on the stave outer at EAR_Z. The bail is a semicircle
    in XZ whose ends are vertical, so they pass through the rings. A
    smaller semicircle is the falsifier: the bar sits on the ring.
    """
    u_l = 0.5 * (spans[0][0] + spans[0][1])
    u_r = 0.5 * (spans[N_STAVES // 2][0] + spans[N_STAVES // 2][1])
    r_l = host_outer_r(u_l, EAR_Z, spans, False)
    r_r = host_outer_r(u_r, EAR_Z, spans, False)
    plate_t = 0.007
    plate_h = 0.036
    plate_w = 0.028
    plate_z = HEIGHT - plate_h * 0.5 - 0.006
    x_l = -(r_l + plate_t * 0.5)
    x_r = r_r + plate_t * 0.5
    ring_x_l = -(r_l + plate_t + RING_MAJOR * 0.25)
    ring_x_r = r_r + plate_t + RING_MAJOR * 0.25
    for x in (x_l, x_r):
        add_box(
            bm,
            (x, 0.0, plate_z),
            (plate_t, plate_w, plate_h),
            METAL_IDX,
        )
    for x in (ring_x_l, ring_x_r):
        add_torus(
            bm,
            (x, 0.0, EAR_Z),
            RING_MAJOR,
            RING_MINOR,
            12,
            6,
            METAL_IDX,
            euler=(0.0, 0.0, 0.0),
        )
    rx = 0.5 * (abs(ring_x_l) + abs(ring_x_r))
    if float_handle:
        rx *= 0.72
        z0 = EAR_Z + 0.035
    else:
        z0 = EAR_Z
    pts = []
    for i in range(BAIL_SEGS + 1):
        t = math.pi * i / BAIL_SEGS
        pts.append((rx * math.cos(t), 0.0, z0 + rx * math.sin(t)))
    add_pipe_curve(bm, pts, BAIL_R, BAIL_PIPE, ROPE_IDX)


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


def build_bucket_mesh(
    name,
    bevel_offset,
    bevel_segments,
    short_staves=False,
    float_handle=False,
    round_band=False,
    float_bottom=False,
):
    bm = bmesh.new()
    gap_ang = GAP_M / max(R_TOP, 0.1)
    spans = stave_spans(N_STAVES, gap_ang, STAVE_JITTER, STAVE_SEED)
    z0 = SHORT_STAVES_LIFT if short_staves else 0.0
    try:
        build_staves(bm, spans, z0, bevel_offset, bevel_segments)
        bot_z0 = CHIME
        bot_z1 = CHIME + BOTTOM_T
        shrink = 0.022 if float_bottom else 0.0
        add_polygon_disk(
            bm, bot_z0, bot_z1,
            croze_xy(spans, 0.5 * (bot_z0 + bot_z1), CROZE_BITE, shrink),
            WOOD_IDX,
        )
        build_hoops(bm, spans, round_band)
        add_ears_and_bail(bm, spans, float_handle)
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


def assign_slots(obj, wood, metal, rope):
    mats = obj.data.materials
    wanted = (wood, metal, rope)
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
        if dz > 0.20:
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
        if dz > 0.06 or max(dx, dy) < 0.20:
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


def floor_gap(me):
    groups = shells(me)
    floors, staves = [], []
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dz = a[5] - a[2]
        r = 0.25 * ((a[3] - a[0]) + (a[4] - a[1]))
        if dz < 0.05 and r > 0.08:
            floors.append(g)
        elif dz > 0.20:
            staves.append(g)
    if not floors or not staves:
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
        for g in floors:
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


def bail_join(me):
    groups = shells(me)
    rings, bails = [], []
    for g in groups:
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        mat = mat_of(me, g)
        if mat == METAL_IDX and max(dx, dy, dz) < 0.08 and a[2] > 0.25:
            rings.append(g)
        elif mat == ROPE_IDX:
            bails.append(g)
    if not rings or not bails:
        return 99.0
    bm_b = bmesh.new()
    try:
        bm_b.from_mesh(me)
        keep = set()
        for g in bails:
            keep.update(g)
        drop = [f for f in bm_b.faces if not all(v.index in keep for v in f.verts)]
        if drop:
            bmesh.ops.delete(bm_b, geom=drop, context="FACES")
        if not bm_b.faces:
            return 99.0
        tree = BVHTree.FromBMesh(bm_b)
        best = 99.0
        for g in rings:
            for i in g:
                p = me.vertices[i].co
                loc, _n, _idx, dist = tree.find_nearest(p)
                if loc is None:
                    continue
                best = min(best, dist)
        return best
    finally:
        bm_b.free()


def body_plan(me):
    groups = shells(me)
    xs, ys, z0s, z1s = [], [], [], []
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        if a[5] - a[2] < 0.20:
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
    img = bpy.data.images.new("BucketNrm", size, size, alpha=True, float_buffer=False)
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
    float_handle=False,
    round_band=False,
    float_bottom=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        short_staves=short_staves,
        float_handle=float_handle,
        round_band=round_band,
        float_bottom=float_bottom,
    )
    low = build_bucket_mesh("BucketLow", 0.003, 2, **flags)
    high = build_bucket_mesh("BucketHigh", 0.003, 4, **flags)
    wood = principled(
        "BucketWood", (0.46, 0.24, 0.09, 1.0), 0.0, 0.52,
        noise_scale=7.0, wear=(0.28, 0.14, 0.05, 1.0),
    )
    metal = principled(
        "BucketHoop", (0.55, 0.53, 0.50, 1.0), 1.0, 0.28,
        noise_scale=5.0, wear=(0.35, 0.32, 0.28, 1.0),
    )
    rope = principled(
        "BucketRope", (0.42, 0.32, 0.18, 1.0), 0.0, 0.72,
        noise_scale=9.0, wear=(0.30, 0.22, 0.12, 1.0),
    )
    assign_slots(low, wood, metal, rope)
    assign_slots(high, wood, metal, rope)
    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("bucket mesh did not build", 3), None, None, None, None, None

    spans = stave_spans(N_STAVES, GAP_M / max(R_TOP, 0.1), STAVE_JITTER, STAVE_SEED)
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
    bjoin = bail_join(low.data)
    fgap = floor_gap(low.data)
    dia, ht = body_plan(low.data)
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}"
    )
    print(
        f"measured staves={sup['staves']} stave_z={sup['stave_z']:.5f} "
        f"hoop_bite={bite_min:.5f}..{bite_max:.5f} bail_join={bjoin:.5f} "
        f"floor_gap={fgap:.5f} body={dia:.4f}x{ht:.4f}"
    )

    img, tex = setup_bake_image(low, wood)
    if img is None:
        return fail("bucket has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BucketLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BucketLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_bucket_mesh("BucketColSrc", 0.0, 1)
    collider = convex_hull_collider(collider_src, "BucketCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_wooden_bucket_{os.getpid()}.glb",
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
    if idx_counts.get(METAL_IDX, 0) < METAL_FACES_MIN:
        return fail(
            f"metal faces {idx_counts.get(METAL_IDX, 0)} < {METAL_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(ROPE_IDX, 0) < ROPE_FACES_MIN:
        return fail(
            f"rope faces {idx_counts.get(ROPE_IDX, 0)} < {ROPE_FACES_MIN}",
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
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf} "
            "(--stray-vert is the designed fail)",
            15,
        ), None, None, None, None, None
    if abs(bb[2]) > ZMIN_EPS:
        return fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ), None, None, None, None, None
    if sup["staves"] != STAVE_COUNT or sup["stave_z"] > STAVE_ZMIN_MAX:
        return fail(
            f"named staves {sup['staves']} z={sup['stave_z']:.5f} "
            "(--short-staves is the designed fail)",
            16,
        ), None, None, None, None, None
    if bjoin > BAIL_GAP_MAX:
        return fail(
            f"bail-ear gap {bjoin:.5f} > {BAIL_GAP_MAX} "
            "(--float-handle is the designed fail)",
            17,
        ), None, None, None, None, None
    if fgap > FLOOR_GAP_MAX:
        return fail(
            f"floor-croze gap {fgap:.5f} > {FLOOR_GAP_MAX} "
            "(--float-bottom is the designed fail)",
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

    low.rotation_euler.z = math.radians(-38.0)
    low.rotation_euler.x = math.radians(8.0)

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
    cam.location = (0.94, -1.28, 1.16)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.28)
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
    p.add_argument("--float-handle", action="store_true")
    p.add_argument("--float-bottom", action="store_true")
    p.add_argument("--round-band", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_staves=args.short_staves,
        float_handle=args.float_handle,
        round_band=args.round_band,
        float_bottom=args.float_bottom,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("wooden-bucket OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
