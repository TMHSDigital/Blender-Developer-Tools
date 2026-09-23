"""Game-ready hitching post — a showcase piece, not an example.

Asserts budget conformance of a procedural timber hitching post (square
post, pyramidal cap, cross-arm, iron shoe, bands, and hitching rings)
after composing shipped pipeline pieces: bmesh construction, UVs, two
materials, high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. ``--skip-decimate`` skips the LOD
DECIMATE stage so the LOD-ratio budget fails. ``--lift-z`` raises the
mesh so the grounded-zmin budget fails. ``--stray-vert`` adds one loose
vertex so the hygiene budget fails. ``--twin-sole`` duplicates the shoe
plate so the coplanar-face budget fails. ``--clip-ring`` lifts a hung
ring off the eye centerline. ``--short-post`` starts the post above the
shoe cup so the seated-post budget fails. ``--sunk-bands`` builds the
iron bands inside the post, as the piece first shipped, so the band-seat
budget fails.

Construction is closed-form; the only RNG is the seeded per-piece wood
tone. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python hitching_post.py --
    blender --background --python hitching_post.py -- --skip-decimate
    blender --background --python hitching_post.py -- --lift-z
    blender --background --python hitching_post.py -- --stray-vert
    blender --background --python hitching_post.py -- --twin-sole
    blender --background --python hitching_post.py -- --clip-ring
    blender --background --python hitching_post.py -- --short-post
    blender --background --python hitching_post.py -- --sunk-bands
    blender --background --python hitching_post.py -- --output hitching-post.png
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

POST_W = 0.125
POST_H = 1.16
CAP_H = 0.096
CAP_OVERHANG = 0.010
CAP_EMBED = 0.010
SOLE_T = 0.016
POST_BITE = 0.006
SHOE_H = 0.064
SHOE_T = 0.012
ARM_Z = 0.88
ARM_L = 0.50
ARM_Y = 0.056
ARM_ZTH = 0.050
EYE_MAJOR = 0.016
EYE_MINOR = 0.0045
RING_MAJOR = 0.038
RING_MINOR = 0.0065
EYE_X = 0.162
BAND_H = 0.026
BAND_T = 0.008
BAND_ZS = (0.24, 0.56)
# Bands wrap the post: inner face BAND_BITE inside the post face, so each
# band stands BAND_T - BAND_BITE proud. The first build sized them from
# ``half - grip`` and sank them inside the post, so only the chamfered
# corners broke the surface, as black slits. --sunk-bands restores that.
BAND_BITE = 0.0015
BAND_PROUD_MIN = 0.004
# Per-piece wood tone jitter and grain frequency, as in shipping-crate.
PLANK_TONE_JITTER = 0.28
TONE_SEED = 29
WOOD_GRAIN_SCALE = 30.0
# Ring tube must fit through the eye: RING_MINOR < EYE_MAJOR - EYE_MINOR.
RING_FIT = 0.004
POST_ZMIN_LO = 0.004
POST_ZMIN_HI = 0.014
RING_CENTER_TOL = 0.008
AXIS_COS_MIN = math.cos(math.radians(0.5))
POST_XY_MAX = 0.010

BBOX_TOL = 0.01
OUTER_SIZE = (0.500, 0.149, 1.246)
BASE_TRIS_MIN = 1400
BASE_TRIS_MAX = 2400
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 280
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
METAL_FACES_MIN = 560
WOOD_FACES_MIN = 70
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 0.002
ZFIGHT_COS = 0.98
GAP_MAX = 0.008
LIFT_Z = 0.05

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


def add_cone(bm, loc, radius1, radius2, depth, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
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


def add_rim(bm, loc, major, minor, mat_idx, euler=(0.0, 0.0, 0.0), n_major=18, n_minor=8):
    rings = []
    for i in range(n_major):
        u = i * (2.0 * math.pi / n_major)
        ring = []
        for j in range(n_minor):
            v = j * (2.0 * math.pi / n_minor)
            ring.append(bm.verts.new((
                (major + minor * math.cos(v)) * math.cos(u),
                (major + minor * math.cos(v)) * math.sin(u),
                minor * math.sin(v),
            )))
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


def add_square_band(bm, z, half, t, h, mat_idx):
    """Closed square collar in XY, extruded along Z. One manifold torus."""
    z0 = z - h * 0.5
    z1 = z + h * 0.5
    inner = (
        (half, half),
        (-half, half),
        (-half, -half),
        (half, -half),
    )
    outer = (
        (half + t, half + t),
        (-(half + t), half + t),
        (-(half + t), -(half + t)),
        (half + t, -(half + t)),
    )

    def ring(zc, pts):
        return [bm.verts.new((p[0], p[1], zc)) for p in pts]

    i0 = ring(z0, inner)
    o0 = ring(z0, outer)
    i1 = ring(z1, inner)
    o1 = ring(z1, outer)

    def quad(a, b, c, d):
        face = bm.faces.new((a, b, c, d))
        face.material_index = mat_idx
        return face

    for k in range(4):
        n = (k + 1) % 4
        quad(i0[k], i0[n], i1[n], i1[k])
        quad(o0[k], o1[k], o1[n], o0[n])
        quad(i0[k], o0[k], o0[n], i0[n])
        quad(i1[k], i1[n], o1[n], o1[k])
    return i0 + o0 + i1 + o1


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


def zfight_pairs(me):
    # Same pair test as showcase/signpost (copied, not imported).
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


def _face_shells(me):
    parent = list(range(len(me.vertices)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for edge in me.edges:
        union(int(edge.vertices[0]), int(edge.vertices[1]))
    groups = {}
    for i in range(len(me.vertices)):
        groups.setdefault(find(i), []).append(i)
    shells = []
    for idxs in groups.values():
        want = set(idxs)
        polys = [
            p.index
            for p in me.polygons
            if all(v in want for v in p.vertices)
        ]
        if polys:
            shells.append((idxs, polys))
    return shells


def _bounds(me, idxs):
    xs, ys, zs = [], [], []
    for i in idxs:
        co = me.vertices[i].co
        xs.append(co.x)
        ys.append(co.y)
        zs.append(co.z)
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def _centroid(me, idxs):
    acc = Vector()
    for i in idxs:
        acc += me.vertices[i].co
    return acc / float(len(idxs))


def _majority_mat(me, poly_ids):
    counts = {}
    for i in poly_ids:
        mat = me.polygons[i].material_index
        counts[mat] = counts.get(mat, 0) + 1
    return max(counts, key=counts.get)


def _bvh(me, poly_ids):
    remap = {}
    verts = []
    faces = []
    for pi in poly_ids:
        face = []
        for vi in me.polygons[pi].vertices:
            if vi not in remap:
                remap[vi] = len(verts)
                verts.append(me.vertices[vi].co.copy())
            face.append(remap[vi])
        faces.append(face)
    return BVHTree.FromPolygons(verts, faces)


def seat_audit(me):
    """Recompute cup, hung-ring, and plumb budgets from the generated shells."""
    post = arm = cap = None
    soles, rings, eyes, bands, shanks = [], [], [], [], []
    for idxs, polys in _face_shells(me):
        x0, x1, y0, y1, z0, z1 = _bounds(me, idxs)
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        rec = {
            "idxs": idxs,
            "polys": polys,
            "c": _centroid(me, idxs),
            "z0": z0,
        }
        if _majority_mat(me, polys) == WOOD_IDX:
            if dz > 0.5 and dx < 0.30:
                post = rec
            elif dx > 0.30:
                arm = rec
            else:
                cap = rec
            continue
        if z0 < 0.004 and dz < 0.030 and dx > 0.10:
            soles.append(rec)
        elif dy < 0.025 and dx > 0.06 and dz > 0.06:
            rings.append(rec)
        elif dx < 0.025 and dy > 0.025 and dz > 0.02:
            eyes.append(rec)
        elif dx < 0.030 and dy < 0.030 and dz < 0.08:
            shanks.append(rec)
        else:
            bands.append(rec)

    out = {
        "post": int(post is not None),
        "arm": int(arm is not None),
        "cap": int(cap is not None),
        "soles": len(soles),
        "rings": len(rings),
        "eyes": len(eyes),
        "bands": len(bands),
        "post_zmin": -1.0,
        "post_xy": 99.0,
        "arm_cos": 0.0,
        "ring_err": 99.0,
        "ring_wood": 99,
        "eye_wood": 99,
        "band_gap": 99.0,
        "sole_shoe": 0,
        "shanks": 0,
        "shank_ring": 99,
        "shank_eye": 0,
        "band_proud": -1.0,
    }
    if (
        post is None
        or arm is None
        or cap is None
        or len(rings) != 2
        or len(eyes) != 2
        or len(bands) < 3
        or len(shanks) != 2
        or not soles
    ):
        return out

    wood_bvh = _bvh(me, post["polys"] + arm["polys"] + cap["polys"])
    ring_wood = 0
    eye_wood = 0
    ring_err = 0.0
    for eye, ring in zip(
        sorted(eyes, key=lambda r: r["c"].x),
        sorted(rings, key=lambda r: r["c"].x),
    ):
        ring_err = max(ring_err, abs((ring["c"] - eye["c"]).length - RING_MAJOR))
        ring_wood += len(wood_bvh.overlap(_bvh(me, ring["polys"])))
        eye_wood += len(wood_bvh.overlap(_bvh(me, eye["polys"])))

    shank_ring = 0
    shank_eye = 0
    for shank in shanks:
        shank_bvh = _bvh(me, shank["polys"])
        for ring in rings:
            shank_ring += len(shank_bvh.overlap(_bvh(me, ring["polys"])))
        eye = min(eyes, key=lambda rec: abs(rec["c"].x - shank["c"].x))
        shank_eye += len(shank_bvh.overlap(_bvh(me, eye["polys"])))

    band_gap = 0.0
    for band in bands:
        if wood_bvh.overlap(_bvh(me, band["polys"])):
            continue
        dmin = 1.0e9
        for i in band["idxs"]:
            hit = wood_bvh.find_nearest(me.vertices[i].co)
            if hit[3] is not None:
                dmin = min(dmin, hit[3])
        band_gap = max(band_gap, dmin)

    shoe = min(bands, key=lambda b: b["z0"])
    sole_shoe = len(_bvh(me, soles[0]["polys"]).overlap(_bvh(me, shoe["polys"])))

    # Each band above the shoe must stand proud of the post faces: its
    # outer half-width in plan against the post's.
    post_x0, post_x1, post_y0, post_y1, _pz0, _pz1 = _bounds(me, post["idxs"])
    post_half = 0.25 * ((post_x1 - post_x0) + (post_y1 - post_y0))
    band_proud = 99.0
    for band in bands:
        if band is shoe:
            continue
        bx0, bx1, by0, by1, _bz0, _bz1 = _bounds(me, band["idxs"])
        band_proud = min(band_proud, 0.25 * ((bx1 - bx0) + (by1 - by0)) - post_half)

    pos, neg = [], []
    for i in arm["idxs"]:
        co = me.vertices[i].co
        if co.x > 0.12:
            pos.append(co)
        elif co.x < -0.12:
            neg.append(co)
    if pos and neg:
        a = sum(pos, Vector()) / len(pos)
        b = sum(neg, Vector()) / len(neg)
        arm_cos = abs((a - b).normalized().dot(Vector((1.0, 0.0, 0.0))))
    else:
        arm_cos = 0.0

    out.update({
        "post_zmin": post["z0"],
        "post_xy": math.hypot(post["c"].x, post["c"].y),
        "arm_cos": arm_cos,
        "ring_err": ring_err,
        "ring_wood": ring_wood,
        "eye_wood": eye_wood,
        "band_gap": band_gap,
        "sole_shoe": sole_shoe,
        "shanks": len(shanks),
        "shank_ring": shank_ring,
        "shank_eye": shank_eye,
        "band_proud": band_proud,
    })
    return out


def add_stray_vert(me):
    # Inside the post so the bbox budget still passes and hygiene is the gate.
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, POST_H * 0.5))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def min_mat_distance(me, ia, ib):
    """Closest surface distance between two material islands via BVH."""
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
        for v in bm_a.verts:
            hit = tree.find_nearest(v.co)
            if hit[0] is None:
                continue
            best = min(best, hit[3])
        for f in bm_a.faces:
            hit = tree.find_nearest(f.calc_center_median())
            if hit[0] is None:
                continue
            best = min(best, hit[3])
        return best
    finally:
        bm_a.free()
        bm_b.free()


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


def add_torus(bm, center, major, minor, axis, mat_idx, n_major=24, n_minor=8):
    """Torus whose hole points along `axis`. The loop lies in the perpendicular plane."""
    axis = Vector(axis).normalized()
    tmp = Vector((0.0, 0.0, 1.0)) if abs(axis.z) < 0.85 else Vector((1.0, 0.0, 0.0))
    u = axis.cross(tmp).normalized()
    v = axis.cross(u).normalized()
    origin = Vector(center)
    rings = []
    for i in range(n_major):
        a = i * (2.0 * math.pi / n_major)
        radial = u * math.cos(a) + v * math.sin(a)
        ring = []
        for j in range(n_minor):
            b = j * (2.0 * math.pi / n_minor)
            point = origin + radial * (major + minor * math.cos(b)) + axis * (minor * math.sin(b))
            ring.append(bm.verts.new(point))
        rings.append(ring)
    bm.verts.ensure_lookup_table()
    made = []
    for i in range(n_major):
        i2 = (i + 1) % n_major
        for j in range(n_minor):
            j2 = (j + 1) % n_minor
            face = bm.faces.new((rings[i][j], rings[i2][j], rings[i2][j2], rings[i][j2]))
            face.material_index = mat_idx
            made.append(rings[i][j])
    return made


def build_hitching_post_mesh(
    name,
    bevel_offset,
    bevel_segments,
    short_post=False,
    clip_ring=False,
    twin_sole=False,
    small_cap=False,
    sunk_bands=False,
):
    """Post on a closed shoe, one rail, rings hung through eyes under the rail.

    The ring center is the eye center plus (0, 0, -RING_MAJOR), so the eye
    sits on the ring centerline. The eye hangs below the rail; the shank
    is bitten into the rail.
    """
    bm = bmesh.new()
    try:
        half = POST_W * 0.5
        post_z0 = (SOLE_T + 0.014) if short_post else (SOLE_T - POST_BITE)
        wood = []
        wood.extend(
            add_box(
                bm,
                (0.0, 0.0, (post_z0 + POST_H) * 0.5),
                (POST_W, POST_W, POST_H - post_z0),
                WOOD_IDX,
            )
        )
        wood.extend(
            add_box(
                bm,
                (0.0, 0.0, ARM_Z),
                (ARM_L, ARM_Y, ARM_ZTH),
                WOOD_IDX,
            )
        )
        if bevel_offset > 0.0:
            edges = list({e for v in wood for e in v.link_edges if v.is_valid})
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
            for face in ret.get("faces") or []:
                face.material_index = WOOD_IDX

        cap_r = (half * 0.55) if small_cap else (half + CAP_OVERHANG) * math.sqrt(2.0)
        add_cone(
            bm,
            (0.0, 0.0, POST_H + CAP_H * 0.5 - CAP_EMBED),
            cap_r,
            0.004,
            CAP_H,
            4,
            WOOD_IDX,
            euler=(0.0, 0.0, math.pi / 4.0),
        )

        grip = bevel_offset + 0.0015
        sole_w = POST_W + 2.0 * SHOE_T
        add_box(
            bm,
            (0.0, 0.0, SOLE_T * 0.5),
            (sole_w, sole_w, SOLE_T),
            METAL_IDX,
        )
        if twin_sole:
            add_box(
                bm,
                (0.0012, 0.0012, SOLE_T * 0.5),
                (sole_w, sole_w, SOLE_T),
                METAL_IDX,
            )
        wall_z0 = SOLE_T - 0.003
        wall_z1 = SHOE_H
        add_square_band(
            bm,
            0.5 * (wall_z0 + wall_z1),
            half - grip,
            SHOE_T,
            wall_z1 - wall_z0,
            METAL_IDX,
        )
        band_in = (half - grip) if sunk_bands else (half - BAND_BITE)
        for z in BAND_ZS:
            add_square_band(bm, z, band_in, BAND_T, BAND_H, METAL_IDX)

        arm_bottom = ARM_Z - ARM_ZTH * 0.5
        eye_z = arm_bottom - EYE_MAJOR - EYE_MINOR - 0.004
        # Shank stops in the top of the eye tube. Continuing it to the eye
        # center runs the pin through the hung ring.
        shank_bot = eye_z + EYE_MAJOR - 0.002
        shank_top = arm_bottom + 0.012
        shank_h = shank_top - shank_bot
        ring_lift = 0.024 if clip_ring else 0.0
        for sx in (-EYE_X, EYE_X):
            add_cyl(
                bm,
                (sx, 0.0, shank_bot + shank_h * 0.5),
                EYE_MINOR * 0.9,
                shank_h,
                8,
                METAL_IDX,
            )
            add_torus(
                bm,
                (sx, 0.0, eye_z),
                EYE_MAJOR,
                EYE_MINOR,
                (1.0, 0.0, 0.0),
                METAL_IDX,
                n_major=16,
                n_minor=8,
            )
            add_torus(
                bm,
                (sx, 0.0, eye_z - RING_MAJOR + ring_lift),
                RING_MAJOR,
                RING_MINOR,
                (0.0, 1.0, 0.0),
                METAL_IDX,
                n_major=24,
                n_minor=8,
            )

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
        for edge in bm.edges:
            if not edge.is_manifold or len(edge.link_faces) != 2:
                continue
            if edge.calc_face_angle() > math.radians(35.0):
                edge.smooth = False
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

    The post, the rail and the cap are each their own shell, so each gets
    one tone and grain running along its own long axis.
    """
    tone = [0.5] * len(me.polygons)
    grain = [(0.0, 0.0, 1.0)] * len(me.polygons)
    owner = {}
    rng = random.Random(TONE_SEED)
    for g, _polys in _face_shells(me):
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
    """Grain along the post and rail (``GrainDir``), tone per piece (``PlankTone``)."""
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


def post_materials():
    """(wood, iron): shared by the check, the render and inspection."""
    wood = wood_material("HitchPostWood")
    metal = principled(
        "HitchPostIron", (0.17, 0.165, 0.155, 1.0), 0.80, 0.46,
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


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("HitchPostNrm", size, size, alpha=True, float_buffer=False)
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
    twin_sole=False,
    clip_ring=False,
    short_post=False,
    sunk_bands=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_hitching_post_mesh(
        "HitchPostLow",
        bevel_offset=0.008,
        bevel_segments=2,
        short_post=short_post,
        clip_ring=clip_ring,
        twin_sole=twin_sole,
        sunk_bands=sunk_bands,
    )
    high = build_hitching_post_mesh(
        "HitchPostHigh", bevel_offset=0.008, bevel_segments=4, sunk_bands=sunk_bands,
    )
    wood, metal = post_materials()
    paint_planks(low.data)
    paint_planks(high.data)
    assign_slots(low, wood, metal)
    assign_slots(high, wood, metal)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
    if stray_vert:
        add_stray_vert(low.data)

    if low.data is None or len(low.data.polygons) < 6:
        return fail("hitching post mesh did not build", 3), None, None, None, None, None

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
        return fail("hitching post has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "HitchPostLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "HitchPostLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_hitching_post_mesh(
        "HitchPostColSrc", bevel_offset=0.0, bevel_segments=1
    )
    collider = convex_hull_collider(collider_src, "HitchPostCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_hitching_post_{os.getpid()}.glb",
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
    hyg = hygiene_audit(low.data)
    zfight = zfight_pairs(low.data)
    gap = min_mat_distance(low.data, METAL_IDX, WOOD_IDX)
    seat = seat_audit(low.data)
    print(
        f"measured collider_tris={col_tris} bake={bake_result} "
        f"bake_has_data={img.has_data} export_bytes={export_size}"
    )
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} euler={hyg['euler']} "
        f"zfight={zfight}"
    )
    print(f"measured wood_metal_gap={gap:.5f} zmin={bb[2]:.6f}")
    print(
        f"measured seat post_zmin={seat['post_zmin']:.5f} post_xy={seat['post_xy']:.5f} "
        f"arm_cos={seat['arm_cos']:.6f} ring_err={seat['ring_err']:.5f} "
        f"ring_wood={seat['ring_wood']} eye_wood={seat['eye_wood']} "
        f"band_gap={seat['band_gap']:.5f} sole_shoe={seat['sole_shoe']} "
        f"shank_ring={seat['shank_ring']} shank_eye={seat['shank_eye']} "
        f"parts={seat['post']}/{seat['arm']}/{seat['cap']}/"
        f"soles={seat['soles']}/rings={seat['rings']}/eyes={seat['eyes']}/bands={seat['bands']} "
        f"band_proud={seat['band_proud']:.5f}"
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
        or         hyg["zero_area"]
        or hyg["doubles"]
        or hyg["ngons"]
        or zfight
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zfight} "
            "(--stray-vert / --twin-sole are the designed fails)",
            15,
        ), None, None, None, None, None
    if abs(bb[2]) > ZMIN_EPS:
        return fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ), None, None, None, None, None
    if gap > GAP_MAX:
        return fail(
            f"wood-metal gap {gap:.5f} > {GAP_MAX}",
            17,
        ), None, None, None, None, None
    if (
        seat["rings"] != 2
        or seat["eyes"] != 2
        or seat["bands"] < 3
        or seat["soles"] < 1
        or seat["ring_err"] > RING_CENTER_TOL
        or seat["ring_wood"]
        or seat["eye_wood"]
        or seat["shanks"] != 2
        or seat["band_gap"] > GAP_MAX
        or seat["sole_shoe"] < 1
        or seat["shank_ring"]
        or seat["shank_eye"] < 1
        or seat["band_proud"] < BAND_PROUD_MIN
    ):
        return fail(
            f"hung ring / shoe seat ring_err={seat['ring_err']:.5f} "
            f"ring_wood={seat['ring_wood']} eye_wood={seat['eye_wood']} "
            f"band_gap={seat['band_gap']:.5f} sole_shoe={seat['sole_shoe']} "
            f"shank_ring={seat['shank_ring']} shank_eye={seat['shank_eye']} "
            f"band_proud={seat['band_proud']:.5f} (min {BAND_PROUD_MIN}) "
            "(--clip-ring / --sunk-bands are the designed fails)",
            18,
        ), None, None, None, None, None
    if (
        not (POST_ZMIN_LO < seat["post_zmin"] < POST_ZMIN_HI)
        or seat["post_xy"] > POST_XY_MAX
        or seat["arm_cos"] < AXIS_COS_MIN
    ):
        return fail(
            f"post seat zmin={seat['post_zmin']:.5f} xy={seat['post_xy']:.5f} "
            f"arm_cos={seat['arm_cos']:.6f} "
            "(--short-post is the designed fail)",
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

    low.rotation_euler.z = math.radians(-18.0)
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

    light("Key", (-3.6, -5.0, 5.4), 660.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.4, 2.4), 46.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.2, 4.0, 3.8), 600.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.25, -3.12, 1.22)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.63)
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
        help="falsification: one loose vertex so the hygiene budget fails",
    )
    p.add_argument(
        "--twin-sole",
        action="store_true",
        help="falsification: duplicate the shoe plate so coplanar faces fail",
    )
    p.add_argument(
        "--clip-ring",
        action="store_true",
        help="falsification: lift the rings off the eye centerline",
    )
    p.add_argument(
        "--short-post",
        action="store_true",
        help="falsification: start the post above the shoe cup",
    )
    p.add_argument(
        "--sunk-bands",
        action="store_true",
        help="falsification: bands inside the post, only the corners showing",
    )
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        twin_sole=args.twin_sole,
        clip_ring=args.clip_ring,
        short_post=args.short_post,
        sunk_bands=args.sunk_bands,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("hitching-post OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
