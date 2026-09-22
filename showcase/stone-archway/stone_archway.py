"""Game-ready stone archway — a showcase piece, not an example.

Asserts budget conformance of a procedural masonry arch: two coursed
piers, nine voussoirs turning a semicircle, and a proud keystone, carried
through UVs, two materials, a high-to-low normal bake, an LOD chain, a
convex collider, and a Unity glTF export.

The budget that matters here is the one an arch can fail invisibly: the
voussoir intrados vertices must lie on a circle of the declared radius,
recomputed from vertex positions rather than from the angles the
generator used. A row of wedges that never turned is still a row of
wedges; only the circle fit knows the difference.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-pier`` the named pier
supports, ``--sink-keystone`` the keystone joint, ``--wide-mortar`` the
mortar-joint band, ``--off-circle`` the intrados circle fit.

Fixed seed 23 for course and block weathering. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python stone_archway.py --
    blender --background --python stone_archway.py -- --off-circle
    blender --background --python stone_archway.py -- --output arch.png
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

# A 1.2 m clear opening under a semicircular head: a gate arch, about
# 1.6 m across the piers and 2.0 m to the crown.
R_IN = 0.60
T_V = 0.20
R_OUT = R_IN + T_V
WALL_Y = 0.40
H_SPRING = 1.20
N_VOUSSOIR = 9
KEY_INDEX = N_VOUSSOIR // 2
# The keystone stands proud of the wall face and rises past the extrados.
KEY_PROUD = 0.035
KEY_RISE = 0.080
# The keystone reads by standing proud and rising past the extrados, not
# by being angularly wider: widening it eats its neighbours' mortar joints.
KEY_WIDEN = 0.0
# Voussoirs bite down into the pier head so the springing joint is an
# overlap, not two faces sharing the z = H_SPRING plane.
SPRING_BITE = 0.018
# Imposts: the projecting string-course at the springing line. They set
# the Y envelope, which is what lets the keystone falsifier change the
# keystone without changing the bounding box.
IMPOST_PROUD = 0.055
IMPOST_H = 0.075
IMPOST_OUT = 0.022
# Radial mortar joints, as an angle so the joint stays radial.
MORTAR_ANG = 0.016
N_COURSE = 5
COURSE_MORTAR = 0.007
WEATHER = 0.18
ARCH_SEED = 23
# Worn arrises. Also what lifts the block count out of programmer-art
# territory: nineteen unbevelled boxes are 228 triangles.
CHAMFER = 0.006

STACK_H = H_SPRING + R_OUT + KEY_RISE

BBOX_TOL = 0.020
OUTER_SIZE = (1.644, 0.510, 2.057)
SPAN_TOL = 0.015
OPENING_W = 2.0 * R_IN

BASE_TRIS_MIN = 700
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
COLLIDER_TRIS_MAX = 260
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
DRESSED_FACES_MIN = 100
ASHLAR_FACES_MIN = 280
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.999
LIFT_Z = 0.05
PIER_Z_MAX = 1e-3
PIERS_MIN = 2
# Intrados circle fit: every inner-arc vertex within this of R_IN.
ARC_TOL = 0.004
ARC_SPAN_MIN = math.radians(168.0)
# Mortar joint band, measured surface-to-surface per adjacent pair.
MORTAR_MIN = 0.006
MORTAR_MAX = 0.017
KEY_PROUD_MIN = 0.020
SPRING_GAP_MAX = 1e-4
FLOAT_PIER_LIFT = 0.012

ASHLAR_IDX = 0
DRESSED_IDX = 1


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


def add_box(bm, loc, scale, mat_idx):
    geo = bmesh.ops.create_cube(bm, size=1.0)
    verts = geo["verts"]
    for v in verts:
        v.co = Vector(
            (
                v.co.x * scale[0] + loc[0],
                v.co.y * scale[1] + loc[1],
                v.co.z * scale[2] + loc[2],
            )
        )
    for f in {f for v in verts for f in v.link_faces}:
        f.material_index = mat_idx
    return verts, (Vector(loc), mat_idx)


def add_wedge(bm, cz, a0, a1, r0, r1, hy, mat_idx):
    """One voussoir: a radial wedge in XZ, extruded across the wall in Y.

    Eight vertices, six quads, closed. The radial end faces are what the
    mortar-joint budget measures, so they stay flat and parallel to the
    neighbour's rather than being bevelled away.
    """
    prof = ((a0, r0), (a1, r0), (a1, r1), (a0, r1))
    rows = []
    for y in (-hy, hy):
        rows.append(
            [
                bm.verts.new((r * math.cos(a), y, cz + r * math.sin(a)))
                for a, r in prof
            ]
        )
    faces = [bm.faces.new(rows[0]), bm.faces.new(tuple(reversed(rows[1])))]
    for k in range(4):
        kn = (k + 1) % 4
        faces.append(
            bm.faces.new((rows[0][k], rows[0][kn], rows[1][kn], rows[1][k]))
        )
    for f in faces:
        f.material_index = mat_idx
    vs = [v for row in rows for v in row]
    c = sum((v.co for v in vs), Vector((0.0, 0.0, 0.0))) / len(vs)
    return vs, (c, mat_idx)


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
        ou = col * cell_w + pad_u
        ov = row * cell_h + pad_v
        for loop, (x, y) in zip(face.loops, coords):
            loop[uv].uv = (
                ou + (x - minx) / dx * usable_w,
                ov + (y - miny) / dy * usable_h,
            )


def assign_materials_by_block(bm, blocks):
    """Re-stamp material indices after the chamfer pass.

    ``bmesh.ops.bevel`` gives every face it creates ``material_index`` 0,
    so chamfering nineteen blocks repainted 464 of 494 faces with the
    first slot and left 30 on the second. The slot count and the distinct
    material check both still passed; only a per-material face floor
    catches it. Each block is its own shell, so re-deriving the material
    from the nearest recorded block centroid restores the assignment
    without depending on face or vertex ordering.
    """
    seen = set()
    for v in bm.verts:
        if v in seen:
            continue
        stack = [v]
        seen.add(v)
        comp = []
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for e in cur.link_edges:
                other = e.other_vert(cur)
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        centre = sum((x.co for x in comp), Vector((0.0, 0.0, 0.0))) / len(comp)
        _c, mat = min(blocks, key=lambda b: (b[0] - centre).length_squared)
        for f in {f for x in comp for f in x.link_faces}:
            f.material_index = mat


def build_pier(bm, sign, rng, float_pier=False):
    """One coursed pier, base course on the floor, head at H_SPRING."""
    raw = [1.0 + rng.uniform(-WEATHER, WEATHER) for _ in range(N_COURSE)]
    total = sum(raw)
    # N_COURSE beds, not N_COURSE-1: the impost needs one under it too,
    # or its underside lands exactly on the top course and the two share
    # a face centre, which is a z-fight.
    usable = H_SPRING - IMPOST_H - COURSE_MORTAR * N_COURSE
    heights = [usable * r / total for r in raw]
    verts = []
    blocks = []
    z = FLOAT_PIER_LIFT if (float_pier and sign < 0) else 0.0
    for i, h in enumerate(heights):
        # Courses weather back a little as they rise; the jitter also keeps
        # two neighbouring courses from presenting identical faces.
        inset = rng.uniform(0.0, 0.010)
        depth = WALL_Y - rng.uniform(0.0, 0.014)
        mat = DRESSED_IDX if i in (0, N_COURSE - 1) else ASHLAR_IDX
        vs, block = add_box(
            bm,
            (sign * (R_IN + T_V / 2.0), 0.0, z + h / 2.0),
            (T_V - inset, depth, h),
            mat,
        )
        verts.extend(vs)
        blocks.append(block)
        z += h + COURSE_MORTAR
    # The impost rides on the courses rather than sitting at an absolute
    # height: pinned to H_SPRING it stays put while --float-pier lifts the
    # courses into it, and the two then share a face plane.
    vs, block = add_box(
        bm,
        (sign * (R_IN + T_V / 2.0), 0.0, z + IMPOST_H / 2.0),
        (T_V + 2.0 * IMPOST_OUT, WALL_Y + 2.0 * IMPOST_PROUD, IMPOST_H),
        DRESSED_IDX,
    )
    verts.extend(vs)
    blocks.append(block)
    return verts, blocks


def build_arch(bm, rng, off_circle=False, sink_keystone=False, wide_mortar=False):
    """Nine voussoirs turning 0..pi, keystone at the crown."""
    gap = MORTAR_ANG * (3.0 if wide_mortar else 1.0)
    step = math.pi / N_VOUSSOIR
    cz = H_SPRING - SPRING_BITE
    verts = []
    blocks = []
    for k in range(N_VOUSSOIR):
        is_key = k == KEY_INDEX
        widen = KEY_WIDEN if is_key else 0.0
        a0 = k * step + gap / 2.0 - widen
        a1 = (k + 1) * step - gap / 2.0 + widen
        r1 = R_OUT + (KEY_RISE if is_key else 0.0)
        hy = WALL_Y / 2.0
        if is_key:
            # Sunk, not removed: the imposts still set the Y envelope, so
            # the bounding box is unchanged and the keystone budget is the
            # only thing that can see this.
            hy += KEY_PROUD * (0.25 if sink_keystone else 1.0)
        mat = DRESSED_IDX if is_key else ASHLAR_IDX
        r0 = R_IN
        if off_circle:
            # Same angles, same joints, same envelope — only the intrados
            # radius wanders. This is the failure the circle fit exists
            # for: nothing else in the piece can see it.
            r0 = R_IN + (0.018 if k % 2 else -0.018)
        # Weathering rides on the extrados only; the intrados is the face
        # the circle-fit budget measures and is left true.
        r1 += rng.uniform(0.0, 0.012)
        vs, block = add_wedge(bm, cz, a0, a1, r0, r1, hy, mat)
        verts.extend(vs)
        blocks.append(block)
    return verts, blocks


def build_arch_mesh(
    name,
    off_circle=False,
    sink_keystone=False,
    wide_mortar=False,
    float_pier=False,
):
    rng = random.Random(ARCH_SEED)
    bm = bmesh.new()
    try:
        blocks = []
        for sign in (-1.0, 1.0):
            _v, bl = build_pier(bm, sign, rng, float_pier=float_pier)
            blocks.extend(bl)
        _v, bl = build_arch(
            bm,
            rng,
            off_circle=off_circle,
            sink_keystone=sink_keystone,
            wide_mortar=wide_mortar,
        )
        blocks.extend(bl)
        edges = list(bm.edges)
        if edges:
            bmesh.ops.bevel(
                bm,
                geom=edges,
                offset=CHAMFER,
                segments=1,
                profile=0.5,
                affect="EDGES",
                clamp_overlap=True,
            )
        assign_materials_by_block(bm, blocks)
        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = False
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
        tex.inputs["Detail"].default_value = 9.0
        tex.inputs["Roughness"].default_value = 0.6
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


def assign_slots(obj, ashlar, dressed):
    mats = obj.data.materials
    for i, mat in enumerate((ashlar, dressed)):
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
        return 0.0, 0.0, 1.0, 1.0, 0.0, 0
    data = uv.data
    us = [loop.uv[0] for loop in data]
    vs = [loop.uv[1] for loop in data]
    aabbs = []
    for poly in mesh.polygons:
        pu = [data[i].uv[0] for i in poly.loop_indices]
        pv = [data[i].uv[1] for i in poly.loop_indices]
        aabbs.append((min(pu), min(pv), max(pu), max(pv)))
    span = max(
        1e-6,
        max((a[2] - a[0]) for a in aabbs),
        max((a[3] - a[1]) for a in aabbs),
    )
    buckets = {}
    for i, a in enumerate(aabbs):
        for c in range(int(a[0] // span), int(a[2] // span) + 1):
            for r in range(int(a[1] // span), int(a[3] // span) + 1):
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
                overlap += max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
                    0.0, min(a[3], b[3]) - max(a[1], b[1])
                )
    return min(us), min(vs), max(us), max(vs), overlap, len(aabbs)


def face_area(me, poly):
    idxs = poly.vertices
    if len(idxs) < 3:
        return 0.0
    v0 = me.vertices[idxs[0]].co
    area = 0.0
    for i in range(1, len(idxs) - 1):
        a = me.vertices[idxs[i]].co
        b = me.vertices[idxs[i + 1]].co
        area += (a - v0).cross(b - v0).length * 0.5
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
        "nv": nv, "ne": ne, "nf": nf, "ngons": ngons, "loose_v": loose_v,
        "loose_e": loose_e, "nonman": nonman, "zero_area": zero_area,
        "doubles": doubles,
    }


def zfight_pairs(me):
    """Coplanar, near-coincident face pairs that share no vertex."""
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
    for (kx, ky, kz), members in buckets.items():
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
            cur = stack.pop()
            group.append(cur)
            for nxt in neighbors[cur]:
                if not seen[nxt]:
                    seen[nxt] = True
                    stack.append(nxt)
        groups.append(group)
    return groups


def shell_tree(me, group):
    """A BVH for one shell, built once so pair gaps stay cheap."""
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        member = set(group)
        drop = [f for f in bm.faces if not all(v.index in member for v in f.verts)]
        if drop:
            bmesh.ops.delete(bm, geom=drop, context="FACES")
        if not bm.faces:
            return None
        return BVHTree.FromBMesh(bm)
    finally:
        bm.free()


def pair_gap(me, tree_a, group_b, tree_b=None):
    """Surface gap from shell B to shell A; 0 when the two interpenetrate.

    find_nearest returns an unsigned distance, so a block seated *inside*
    its host reports the distance to the host's skin rather than zero. The
    springing joint is an overlap by design, so without the overlap test
    first this reads a 5 mm gap where there is none.
    """
    if tree_a is None:
        return 99.0
    if tree_b is not None and tree_a.overlap(tree_b):
        return 0.0
    best = 99.0
    for i in group_b:
        hit = tree_a.find_nearest(me.vertices[i].co)
        if hit[0] is None:
            continue
        best = min(best, hit[3])
    return best


def classify(me):
    """Name the shells: pier courses by side, voussoirs by crown angle."""
    out = {"left": [], "right": [], "voussoirs": []}
    for g in shells(me):
        pts = [me.vertices[i].co for i in g]
        zmin = min(p.z for p in pts)
        zmax = max(p.z for p in pts)
        xc = sum(p.x for p in pts) / len(pts)
        rec = {"g": g, "zmin": zmin, "zmax": zmax, "xc": xc, "pts": pts}
        if zmax <= H_SPRING + 1e-6:
            (out["left"] if xc < 0 else out["right"]).append(rec)
        else:
            out["voussoirs"].append(rec)
    out["left"].sort(key=lambda r: r["zmin"])
    out["right"].sort(key=lambda r: r["zmin"])
    # Around the arch, not left to right: atan2 about the springing centre
    # orders the voussoirs even when a falsifier has flattened them.
    out["voussoirs"].sort(
        key=lambda r: math.atan2(
            max(1e-9, sum(p.z for p in r["pts"]) / len(r["pts"]) - (H_SPRING - SPRING_BITE)),
            sum(p.x for p in r["pts"]) / len(r["pts"]),
        ),
        reverse=True,
    )
    return out


def arch_audit(me):
    """Circle fit, mortar band, keystone proudness, pier supports."""
    parts = classify(me)
    cz = H_SPRING - SPRING_BITE

    # Intrados circle fit, measured on the vertices of faces that actually
    # face the springing centre. Selecting by radius alone would sweep in
    # the chamfer vertices sitting one bevel-width out on each radial face,
    # and report a 6 mm error on a true arch.
    member = {}
    for rec in parts["voussoirs"]:
        for i in rec["g"]:
            member[i] = True
    radii = []
    angles = []
    for poly in me.polygons:
        if not all(i in member for i in poly.vertices):
            continue
        c = poly.center
        rc = math.hypot(c.x, c.z - cz)
        if rc > R_IN + T_V * 0.5:
            continue
        inward = Vector((-c.x, 0.0, -(c.z - cz)))
        if inward.length < 1e-9:
            continue
        inward.normalize()
        n = poly.normal
        if abs(n.y) > 0.2:
            continue
        if Vector((n.x, 0.0, n.z)).normalized().dot(inward) < 0.9:
            continue
        for i in poly.vertices:
            p = me.vertices[i].co
            radii.append(math.hypot(p.x, p.z - cz))
            angles.append(math.atan2(p.z - cz, p.x))
    arc_dev = max((abs(r - R_IN) for r in radii), default=99.0)
    arc_span = (max(angles) - min(angles)) if angles else 0.0

    # Mortar joints, surface to surface, per adjacent pair around the arch.
    vs = parts["voussoirs"]
    trees = [shell_tree(me, rec["g"]) for rec in vs]
    gaps = []
    for i in range(len(vs) - 1):
        gaps.append(
            min(
                pair_gap(me, trees[i], vs[i + 1]["g"], trees[i + 1]),
                pair_gap(me, trees[i + 1], vs[i]["g"], trees[i]),
            )
        )
    gap_min = min(gaps) if gaps else 99.0
    gap_max = max(gaps) if gaps else 99.0

    # Keystone: the voussoir that stands proud of the wall face.
    wall_half = WALL_Y / 2.0
    prouds = [
        max(abs(p.y) for p in rec["pts"]) - wall_half for rec in vs
    ]
    key_proud = max(prouds) if prouds else 0.0

    # Springing joints must overlap the pier head, not rest on it.
    spring_gap = 0.0
    for side in ("left", "right"):
        if not parts[side] or not vs:
            spring_gap = 99.0
            continue
        head = parts[side][-1]
        tree = shell_tree(me, head["g"])
        idx = min(
            range(len(vs)),
            key=lambda k: abs(
                sum(p.x for p in vs[k]["pts"]) / len(vs[k]["pts"]) - head["xc"]
            ),
        )
        spring_gap = max(
            spring_gap, pair_gap(me, tree, vs[idx]["g"], trees[idx])
        )

    piers = 0
    pier_z = 99.0
    for side in ("left", "right"):
        if parts[side]:
            piers += 1
            pier_z = min(pier_z, 99.0)
    pier_worst = max(
        (parts[s][0]["zmin"] for s in ("left", "right") if parts[s]), default=99.0
    )

    return {
        "n_vous": len(vs),
        "n_left": len(parts["left"]),
        "n_right": len(parts["right"]),
        "arc_dev": arc_dev,
        "arc_span": arc_span,
        "gap_min": gap_min,
        "gap_max": gap_max,
        "key_proud": key_proud,
        "spring_gap": spring_gap,
        "piers": piers,
        "pier_worst": pier_worst,
        "gaps": [round(g, 5) for g in gaps],
    }


def opening_audit(me):
    """Clear opening width at mid-pier height, measured from vertices."""
    # Band stops clear of the impost, which projects inboard of the pier
    # face and is not part of the clear opening.
    zc = H_SPRING * 0.5
    half = H_SPRING * 0.40
    xs_left = [
        v.co.x for v in me.vertices
        if v.co.x < 0 and abs(v.co.z - zc) < half
    ]
    xs_right = [
        v.co.x for v in me.vertices
        if v.co.x > 0 and abs(v.co.z - zc) < half
    ]
    if not xs_left or not xs_right:
        return 0.0
    return min(xs_right) - max(xs_left)


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, H_SPRING * 0.5))
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
        for key in ("geom_interior", "geom_unused"):
            geom = result.get(key) or []
            if geom:
                bmesh.ops.delete(bm, geom=geom, context="VERTS")
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
    img = bpy.data.images.new("ArchNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = ASHLAR_IDX
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
    float_pier=False,
    sink_keystone=False,
    wide_mortar=False,
    off_circle=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        off_circle=off_circle,
        sink_keystone=sink_keystone,
        wide_mortar=wide_mortar,
        float_pier=float_pier,
    )
    nothing = (None,) * 5
    low = build_arch_mesh("ArchLow", **flags)
    high = build_arch_mesh("ArchHigh", **flags)
    ashlar = principled(
        "ArchAshlar", (0.300, 0.219, 0.126, 1.0), 0.0, 0.80,
        noise_scale=14.0, wear=(0.168, 0.113, 0.055, 1.0),
    )
    dressed = principled(
        "ArchDressed", (0.452, 0.348, 0.205, 1.0), 0.0, 0.62,
        noise_scale=8.0, wear=(0.262, 0.196, 0.108, 1.0),
    )
    assign_slots(low, ashlar, dressed)
    assign_slots(high, ashlar, dressed)
    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()

    if low.data is None or len(low.data.polygons) < 6:
        return (fail("arch mesh did not build", 3),) + nothing

    base_tris = triangle_count(low.data)
    mats = [s for s in low.data.materials if s is not None]
    nmat = len(mats)
    distinct = len({id(s) for s in mats})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, ashlar)
    if img is None:
        return (fail("arch has no UV layer", 3),) + nothing
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "ArchLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "ArchLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    col_src = build_arch_mesh("ArchColSrc", **flags)
    collider = convex_hull_collider(col_src, "ArchCollider")
    bpy.data.objects.remove(col_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(), f"bdt_stone_archway_{os.getpid()}.glb"
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    ar = arch_audit(low.data)
    opening = opening_audit(low.data)

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
        f"outer={OUTER_SIZE} zmin={bb[2]:.5f} opening={opening:.4f}"
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
        f"measured arch vous={ar['n_vous']} courses={ar['n_left']}/{ar['n_right']} "
        f"arc_dev={ar['arc_dev']:.5f} arc_span={math.degrees(ar['arc_span']):.1f}deg "
        f"gap=({ar['gap_min']:.5f},{ar['gap_max']:.5f}) "
        f"key_proud={ar['key_proud']:.5f} spring_gap={ar['spring_gap']:.5f} "
        f"pier_worst={ar['pier_worst']:.5f} gaps={ar['gaps']}"
    )

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(
            f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4
        ),) + nothing
    if nmat != MATERIAL_COUNT or distinct != MATERIAL_COUNT:
        return (fail(
            f"material slots {nmat} distinct {distinct} != {MATERIAL_COUNT}", 5
        ),) + nothing
    if idx_counts.get(DRESSED_IDX, 0) < DRESSED_FACES_MIN:
        return (fail(
            f"dressed faces {idx_counts.get(DRESSED_IDX, 0)} < {DRESSED_FACES_MIN}", 5
        ),) + nothing
    if idx_counts.get(ASHLAR_IDX, 0) < ASHLAR_FACES_MIN:
        return (fail(
            f"ashlar faces {idx_counts.get(ASHLAR_IDX, 0)} < {ASHLAR_FACES_MIN}", 5
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
        hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
        or hyg["doubles"] or hyg["ngons"] or zf
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
    if ar["piers"] < PIERS_MIN or ar["pier_worst"] > PIER_Z_MAX:
        return (fail(
            f"pier supports {ar['piers']} worst base z={ar['pier_worst']:.5f} "
            "(--float-pier is the designed fail)", 16
        ),) + nothing
    if ar["key_proud"] < KEY_PROUD_MIN or ar["spring_gap"] > SPRING_GAP_MAX:
        return (fail(
            f"keystone proud {ar['key_proud']:.5f} < {KEY_PROUD_MIN} or "
            f"springing gap {ar['spring_gap']:.5f} > {SPRING_GAP_MAX} "
            "(--sink-keystone is the designed fail)", 17
        ),) + nothing
    if not (MORTAR_MIN <= ar["gap_min"] and ar["gap_max"] <= MORTAR_MAX):
        return (fail(
            f"mortar joints ({ar['gap_min']:.5f}, {ar['gap_max']:.5f}) outside "
            f"[{MORTAR_MIN}, {MORTAR_MAX}] (--wide-mortar is the designed fail)", 18
        ),) + nothing
    if ar["arc_dev"] > ARC_TOL or ar["arc_span"] < ARC_SPAN_MIN:
        return (fail(
            f"intrados off circle by {ar['arc_dev']:.5f} > {ARC_TOL} or spans "
            f"{math.degrees(ar['arc_span']):.1f} deg < "
            f"{math.degrees(ARC_SPAN_MIN):.1f} "
            "(--off-circle is the designed fail)", 19
        ),) + nothing
    if abs(opening - OPENING_W) > SPAN_TOL:
        return (fail(
            f"clear opening {opening:.4f} off {OPENING_W}", 19
        ),) + nothing
    return 0, low, high, ashlar, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, ashlar, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(ashlar, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(-17.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=20.0)
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

    light("Key", (-4.0, -4.6, 6.0), 640.0, 5.0, (1.0, 0.96, 0.90), (42, 0, -40))
    light("Fill", (4.6, -3.2, 2.0), 108.0, 9.0, (0.75, 0.85, 1.00), (70, 0, 54))
    light("Rim", (-2.2, 3.8, 3.4), 420.0, 3.5, (0.60, 0.78, 1.00), (-60, 0, 202))
    light("Wedge", (1.35, 4.4, 2.35), 640.0, 6.0, (1.0, 0.70, 0.36), (-94, 0, 194))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (3.46, -5.18, 2.05)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, STACK_H * 0.48)
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
    p.add_argument("--float-pier", action="store_true")
    p.add_argument("--sink-keystone", action="store_true")
    p.add_argument("--wide-mortar", action="store_true")
    p.add_argument("--off-circle", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, ashlar, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_pier=args.float_pier,
        sink_keystone=args.sink_keystone,
        wide_mortar=args.wide_mortar,
        off_circle=args.off_circle,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, ashlar, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("stone-archway OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
