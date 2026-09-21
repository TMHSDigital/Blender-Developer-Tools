"""Game-ready wall torch sconce — a showcase piece, not an example.

Asserts budget conformance of a procedural wall-mounted torch after
composing shipped pipeline pieces: bmesh construction, UVs, four
materials, high-to-low normal bake, LOD chain, convex collider,
Unity glTF export.

The plaque back sits on the wall plane Y=0 with zmin at 0. The iron
arm is a tube between the plate station and the cup station. The
bowl opens upward and holds the haft. Hygiene family 15–19:
``--stray-vert``, ``--lift-z``, ``--float-arm``, ``--float-plate``,
``--skinny-plaque``.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle
counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python wall_torch.py --
    blender --background --python wall_torch.py -- --skip-decimate
    blender --background --python wall_torch.py -- --output torch.png
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

WALL_W = 0.28
WALL_D = 0.070
WALL_H = 0.40
CORNICE_H = 0.028
GROUT = 0.007
NROWS = 4
STONE_D = 0.020
STONE_BITE = 0.004
PLATE_Z = 0.22
PLATE_R = 0.055
PLATE_T = 0.016
CUP_Y = 0.24
CUP_Z = 0.20
CUP_H = 0.052
CUP_R0 = 0.024
CUP_R1 = 0.050
ARM_R = 0.011
ARM_BITE = 0.012
HAFT_R = 0.016
LIFT_Z = 0.05
FLOAT_ARM = 0.55
FLOAT_PLATE = 0.08
SKINNY = 0.55

BBOX_TOL = 0.015
OUTER_SIZE = (0.304, 0.293, 0.424)
BASE_TRIS_MIN = 1400
BASE_TRIS_MAX = 1700
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 4
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 180
BAKE_RES = 256
CAGE_EXTRUSION = 0.06
STONE_FACES_MIN = 24
METAL_FACES_MIN = 24
FLAME_FACES_MIN = 8

STONE_IDX = 0
METAL_IDX = 1
WOOD_IDX = 2
FLAME_IDX = 3

DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZMIN_EPS = 1e-4
ZFIGHT_EPS = 0.002
ZFIGHT_COS = 0.98
ARM_GAP_MAX = 0.008
PLATE_GAP_MAX = 0.008
PLAQUE_W_TOL = 0.04


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


def add_cone(bm, loc, radius1, radius2, depth, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=segments > 4,
        segments=segments,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
    )
    verts = list(geo["verts"])
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


def add_cyl_between(bm, a, b, radius, segments, mat_idx):
    a = Vector(a)
    b = Vector(b)
    delta = b - a
    length = delta.length
    if length < 1e-8:
        return []
    quat = Vector((0.0, 0.0, 1.0)).rotation_difference(delta.normalized())
    eul = quat.to_euler("XYZ")
    return add_cone(
        bm,
        (a + b) * 0.5,
        radius,
        radius,
        length,
        segments,
        mat_idx,
        euler=(eul.x, eul.y, eul.z),
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


def build_torch_mesh(
    name,
    bevel_offset,
    bevel_segments,
    float_arm=False,
    float_plate=False,
    skinny_plaque=False,
):
    bm = bmesh.new()
    try:
        plaque_w = WALL_W * SKINNY if skinny_plaque else WALL_W
        add_box(
            bm,
            (0.0, WALL_D / 2.0, WALL_H / 2.0),
            (plaque_w, WALL_D, WALL_H),
            STONE_IDX,
        )
        add_box(
            bm,
            (0.0, WALL_D / 2.0 + 0.006, WALL_H + CORNICE_H / 2.0 - 0.004),
            (plaque_w + 0.024, WALL_D + 0.018, CORNICE_H),
            STONE_IDX,
        )

        course_h = (WALL_H - GROUT * (NROWS + 1)) / NROWS
        face_y = WALL_D - STONE_BITE + STONE_D / 2.0
        inner = plaque_w - 2.0 * GROUT
        for row in range(NROWS):
            zc = GROUT + row * (course_h + GROUT) + course_h / 2.0
            fracs = (0.58, 0.42) if row % 2 == 0 else (0.40, 0.60)
            x = -plaque_w / 2.0 + GROUT
            for frac in fracs:
                w = inner * frac - GROUT * 0.5
                cx = x + w / 2.0
                add_box(
                    bm,
                    (cx, face_y, zc),
                    (max(w, 0.04), STONE_D, course_h - 0.001),
                    STONE_IDX,
                )
                x += w + GROUT

        plate_y = WALL_D - 0.004 + PLATE_T / 2.0
        if float_plate:
            plate_y += FLOAT_PLATE
        add_cone(
            bm,
            (0.0, plate_y, PLATE_Z),
            PLATE_R,
            PLATE_R,
            PLATE_T,
            12,
            METAL_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
        for sx, sz in ((-0.032, 0.028), (0.032, 0.028), (-0.032, -0.028), (0.032, -0.028)):
            add_cone(
                bm,
                (sx, plate_y + PLATE_T / 2.0 + 0.004, PLATE_Z + sz),
                0.006,
                0.006,
                0.010,
                8,
                METAL_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )

        plate_st = Vector((0.0, plate_y, PLATE_Z))
        cup_st = Vector((0.0, CUP_Y - CUP_R1 + ARM_BITE, CUP_Z))
        arm_end = cup_st
        if float_arm:
            arm_end = plate_st + (cup_st - plate_st) * FLOAT_ARM
        add_cyl_between(bm, plate_st, arm_end, ARM_R, 8, METAL_IDX)

        add_cone(
            bm,
            (0.0, CUP_Y, CUP_Z),
            CUP_R0,
            CUP_R1,
            CUP_H,
            12,
            METAL_IDX,
        )
        add_cone(
            bm,
            (0.0, CUP_Y, CUP_Z - CUP_H / 2.0 - 0.006),
            CUP_R0 + 0.004,
            CUP_R0 + 0.004,
            0.010,
            12,
            METAL_IDX,
        )

        cup_rim = CUP_Z + CUP_H / 2.0
        haft_z0 = CUP_Z - CUP_H / 2.0 + 0.006
        haft_z1 = cup_rim + 0.026
        add_cone(
            bm,
            (0.0, CUP_Y, (haft_z0 + haft_z1) / 2.0),
            HAFT_R,
            HAFT_R,
            haft_z1 - haft_z0,
            10,
            WOOD_IDX,
        )

        add_cone(bm, (0.0, CUP_Y, cup_rim + 0.038), 0.034, 0.004, 0.078, 10, FLAME_IDX)
        add_cone(
            bm,
            (0.012, CUP_Y - 0.008, cup_rim + 0.028),
            0.022,
            0.003,
            0.058,
            8,
            FLAME_IDX,
            euler=(0.0, math.radians(14.0), 0.0),
        )
        add_cone(
            bm,
            (-0.010, CUP_Y + 0.006, cup_rim + 0.024),
            0.018,
            0.003,
            0.050,
            8,
            FLAME_IDX,
            euler=(math.radians(-10.0), math.radians(-12.0), 0.0),
        )

        if bevel_offset > 0.0:
            stone_edges = [
                e for e in bm.edges
                if any(f.material_index == STONE_IDX for f in e.link_faces)
            ]
            if stone_edges:
                ret = bmesh.ops.bevel(
                    bm,
                    geom=stone_edges,
                    offset=bevel_offset,
                    segments=bevel_segments,
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
                )
                for f in ret.get("faces") or []:
                    f.material_index = STONE_IDX

        zs = [v.co.z for v in bm.verts]
        zmin = min(zs)
        for v in bm.verts:
            v.co.z -= zmin
            if v.co.z < 0.0:
                v.co.z = 0.0

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = face.material_index in (METAL_IDX, FLAME_IDX)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        for poly in me.polygons:
            poly.use_smooth = poly.material_index in (METAL_IDX, FLAME_IDX)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def principled(
    name,
    color,
    metallic,
    roughness,
    emission=0.0,
    emission_color=None,
    noise_scale=0.0,
    wear=None,
):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission > 0.0:
        ecol = emission_color or color
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = ecol
            bsdf.inputs["Emission Strength"].default_value = emission
        elif "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = ecol
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


def assign_slots(obj, stone, metal, wood, flame):
    mats = obj.data.materials
    wanted = (stone, metal, wood, flame)
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
        bm.verts.new((0.0, CUP_Y, PLATE_Z))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def joint_audit(me):
    groups = shells(me)
    plaques = []
    plates = []
    cups = []
    arms = []
    for g in groups:
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        mat = mat_of(me, g)
        if mat == STONE_IDX and dz > 0.20 and dx > 0.12:
            plaques.append((g, a))
        elif mat == METAL_IDX and dy <= 0.04 and dx >= 0.08 and dz >= 0.08:
            plates.append((g, a))
        elif mat == METAL_IDX and a[4] > CUP_Y - 0.05 and dx > 0.05 and dz < 0.14:
            cups.append((g, a))
        elif mat == METAL_IDX and dy > dx and dy > dz:
            arms.append((g, a))
    arm_gap = 1e9
    for ag, _ in arms:
        for cg, _ in cups:
            arm_gap = min(arm_gap, shell_bvh_gap(me, ag, cg))
    plate_gap = 1e9
    for pg, _ in plates:
        for qg, _ in plaques:
            plate_gap = min(plate_gap, shell_bvh_gap(me, pg, qg))
    plaque_w = max((a[3] - a[0] for _, a in plaques), default=0.0)
    return {
        "plaques": len(plaques),
        "plates": len(plates),
        "cups": len(cups),
        "arms": len(arms),
        "arm_gap": arm_gap if arms and cups else 1e9,
        "plate_gap": plate_gap if plates and plaques else 1e9,
        "plaque_w": plaque_w,
    }


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("TorchNrm", size, size, alpha=True, float_buffer=False)
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
    float_arm=False,
    float_plate=False,
    skinny_plaque=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    kw = dict(
        float_arm=float_arm,
        float_plate=float_plate,
        skinny_plaque=skinny_plaque,
    )
    low = build_torch_mesh("TorchLow", bevel_offset=0.004, bevel_segments=2, **kw)
    high = build_torch_mesh("TorchHigh", bevel_offset=0.004, bevel_segments=4, **kw)
    stone = principled(
        "TorchStone", (0.36, 0.34, 0.30, 1.0), 0.0, 0.72,
        noise_scale=12.0, wear=(0.28, 0.26, 0.22, 1.0),
    )
    metal = principled(
        "TorchMetal", (0.14, 0.12, 0.10, 1.0), 0.88, 0.38,
        noise_scale=18.0, wear=(0.22, 0.16, 0.10, 1.0),
    )
    wood = principled(
        "TorchWood", (0.22, 0.11, 0.05, 1.0), 0.0, 0.64,
        noise_scale=14.0, wear=(0.12, 0.06, 0.03, 1.0),
    )
    flame = principled(
        "TorchFlame",
        (1.0, 0.28, 0.04, 1.0),
        0.0,
        0.48,
        emission=1.6,
        emission_color=(1.0, 0.30, 0.05, 1.0),
    )
    assign_slots(low, stone, metal, wood, flame)
    assign_slots(high, stone, metal, wood, flame)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("torch mesh did not build", 3), None, None, None, None, None

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
        return fail("torch has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "TorchLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "TorchLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_torch_mesh("TorchColSrc", bevel_offset=0.0, bevel_segments=1, **kw)
    collider = convex_hull_collider(collider_src, "TorchCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_wall_torch_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    jnt = joint_audit(low.data)

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
        f"measured plaques={jnt['plaques']} plates={jnt['plates']} "
        f"cups={jnt['cups']} arms={jnt['arms']} "
        f"arm_gap={jnt['arm_gap']:.5f} plate_gap={jnt['plate_gap']:.5f} "
        f"plaque_w={jnt['plaque_w']:.4f}"
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
    if idx_counts.get(STONE_IDX, 0) < STONE_FACES_MIN:
        return fail(
            f"stone faces {idx_counts.get(STONE_IDX, 0)} < {STONE_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(METAL_IDX, 0) < METAL_FACES_MIN:
        return fail(
            f"metal faces {idx_counts.get(METAL_IDX, 0)} < {METAL_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(FLAME_IDX, 0) < FLAME_FACES_MIN:
        return fail(
            f"flame faces {idx_counts.get(FLAME_IDX, 0)} < {FLAME_FACES_MIN}",
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
    if bb[2] > ZMIN_EPS:
        return fail(f"grounded zmin={bb[2]:.5f}", 16), None, None, None, None, None
    if jnt["arms"] < 1 or jnt["cups"] < 1 or jnt["arm_gap"] > ARM_GAP_MAX:
        return fail(
            f"arm-cup gap {jnt['arm_gap']:.5f} arms={jnt['arms']} cups={jnt['cups']}",
            17,
        ), None, None, None, None, None
    if jnt["plates"] < 1 or jnt["plaques"] < 1 or jnt["plate_gap"] > PLATE_GAP_MAX:
        return fail(
            f"plate-plaque gap {jnt['plate_gap']:.5f} plates={jnt['plates']} "
            f"plaques={jnt['plaques']}",
            18,
        ), None, None, None, None, None
    if abs(jnt["plaque_w"] - WALL_W) > PLAQUE_W_TOL:
        return fail(
            f"plaque width {jnt['plaque_w']:.4f} off {WALL_W}",
            19,
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
    return 0, low, high, stone, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, stone, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(stone, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(128.0)

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

    light("Key", (-3.6, -5.0, 5.4), 640.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.4, 2.4), 42.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.2, 4.0, 3.8), 560.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))
    light("FlameKick", (0.4, 1.2, 0.8), 90.0, 0.6, (1.0, 0.55, 0.22), (40, 0, 160))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 55.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-0.95, -1.15, 0.36)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.02, 0.06, 0.21)
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
    p.add_argument("--float-arm", action="store_true")
    p.add_argument("--float-plate", action="store_true")
    p.add_argument("--skinny-plaque", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, stone, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_arm=args.float_arm,
        float_plate=args.float_plate,
        skinny_plaque=args.skinny_plaque,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, stone, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("wall-torch OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
