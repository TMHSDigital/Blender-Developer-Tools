"""Game-ready wooden bucket — a showcase piece, not an example.

Asserts budget conformance of a procedural coopered bucket after composing
shipped pipeline pieces: bmesh construction, UVs, three materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. ``--skip-decimate`` skips the LOD
DECIMATE stage so the LOD-ratio budget fails.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python wooden_bucket.py --
    blender --background --python wooden_bucket.py -- --skip-decimate
    blender --background --python wooden_bucket.py -- --output bucket.png
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

# Showcase lives at repo-root/showcase/, not under examples/. The framing
# helper is the repo's only shared import and lives next to the examples;
# resolve the repo root so we do not move gallery_framing.py.
_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

HEIGHT = 0.36
R_BOT = 0.125
R_TOP = 0.168
N_STAVES = 14
STAVE_THICK = 0.022
N_RINGS = 4
# Negative gap = overlapping staves so the hull is sealed.
STAVE_GAP = -0.08
HOOP_ZS = (0.055, 0.155, 0.305)
HOOP_H = 0.026
HOOP_PAD = 0.011
BOTTOM_T = 0.024
BAIL_R = 0.012
BAIL_SEGS = 12
BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.402, 0.345, 0.544)

BASE_TRIS_MIN = 4150
BASE_TRIS_MAX = 4400
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 420
BAKE_RES = 256
CAGE_EXTRUSION = 0.06
METAL_FACES_MIN = 24
ROPE_FACES_MIN = 12

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
    # Duplicated from snippets/lod_chain.py / decimate_to_budget.py (not a package).
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
    return R_BOT + (R_TOP - R_BOT) * t


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
    verts = list(geo["verts"])
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mat_idx
    return verts


def add_cylinder(bm, loc, radius, depth, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    return add_cone(bm, loc, radius, radius, depth, segments, mat_idx, euler=euler)


def add_rim(bm, loc, major, minor, mat_idx, euler=(0.0, 0.0, 0.0)):
    n_major = 12
    n_minor = 6
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


def build_bucket_mesh(name, bevel_offset, bevel_segments):
    bm = bmesh.new()
    stave_verts = []
    hoop_faces = set()
    rope_faces = set()
    try:
        zs = [HEIGHT * i / (N_RINGS - 1) for i in range(N_RINGS)]
        for i in range(N_STAVES):
            a0 = 2.0 * math.pi * i / N_STAVES
            a1 = 2.0 * math.pi * (i + 1.0 - STAVE_GAP) / N_STAVES
            outer = []
            inner = []
            for z in zs:
                r = radius_at(z)
                ov = (
                    bm.verts.new((r * math.cos(a0), r * math.sin(a0), z)),
                    bm.verts.new((r * math.cos(a1), r * math.sin(a1), z)),
                )
                ri = r - STAVE_THICK
                iv = (
                    bm.verts.new((ri * math.cos(a0), ri * math.sin(a0), z)),
                    bm.verts.new((ri * math.cos(a1), ri * math.sin(a1), z)),
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
            # Rim only — no top lid. Interior stays open.
            top = bm.faces.new((outer[-1][0], outer[-1][1], inner[-1][1], inner[-1][0]))
            top.material_index = WOOD_IDX
            bot = bm.faces.new((outer[0][1], outer[0][0], inner[0][0], inner[0][1]))
            bot.material_index = WOOD_IDX

        if bevel_offset > 0.0:
            edges = list({e for v in stave_verts for e in v.link_edges})
            bmesh.ops.bevel(
                bm,
                geom=edges,
                offset=bevel_offset,
                segments=bevel_segments,
                profile=0.5,
                affect="EDGES",
                clamp_overlap=True,
            )

        # Bottom seated inside the hull so the basin actually holds.
        add_cylinder(
            bm,
            (0.0, 0.0, BOTTOM_T / 2.0),
            R_BOT - STAVE_THICK * 0.35,
            BOTTOM_T,
            16,
            WOOD_IDX,
        )

        for z in HOOP_ZS:
            before = set(bm.faces)
            add_cylinder(
                bm,
                (0.0, 0.0, z),
                radius_at(z) + HOOP_PAD,
                HOOP_H,
                20,
                METAL_IDX,
            )
            hoop_faces.update(set(bm.faces) - before)

        ear_x = R_TOP + 0.006
        ear_z = HEIGHT - 0.018
        for sign in (-1.0, 1.0):
            before = set(bm.faces)
            add_box(
                bm,
                (sign * ear_x, 0.0, ear_z),
                (0.028, 0.036, 0.048),
                METAL_IDX,
            )
            add_rim(
                bm,
                (sign * (ear_x + 0.006), 0.0, ear_z + 0.012),
                0.016,
                0.005,
                METAL_IDX,
                euler=(math.radians(90.0), 0.0, 0.0),
            )
            hoop_faces.update(set(bm.faces) - before)

        bail_major = ear_x + 0.004
        bail_pts = []
        for i in range(BAIL_SEGS + 1):
            t = math.pi * i / BAIL_SEGS
            bail_pts.append(
                (
                    bail_major * math.cos(t),
                    0.0,
                    ear_z + 0.012 + bail_major * math.sin(t),
                )
            )
        before = set(bm.faces)
        for a, b in zip(bail_pts, bail_pts[1:]):
            add_oriented_box(bm, a, b, (BAIL_R * 2.0, BAIL_R * 2.0), ROPE_IDX)
        rope_faces.update(set(bm.faces) - before)

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = True
            if edge.is_manifold and len(edge.link_faces) == 2:
                if edge.calc_face_angle() > math.radians(35.0):
                    edge.smooth = False
        for f in hoop_faces:
            if f.is_valid:
                f.material_index = METAL_IDX
        for f in rope_faces:
            if f.is_valid:
                f.material_index = ROPE_IDX
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def principled(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def assign_slots(obj, wood, metal, rope):
    mats = obj.data.materials
    if len(mats) == 0:
        mats.append(wood)
        mats.append(metal)
        mats.append(rope)
        return
    mats[0] = wood
    if len(mats) == 1:
        mats.append(metal)
    else:
        mats[1] = metal
    if len(mats) == 2:
        mats.append(rope)
    else:
        mats[2] = rope


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
    # Duplicated from snippets/convex_hull_collider.py (not a package).
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
    # Adapted from snippets/setup_bake_target_image.py — do not replace slots.
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
    # Duplicated from snippets/bake_normal_high_to_low.py (not a package).
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
    # Duplicated from snippets/export_preset_unity.py (not a package).
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


def check(skip_decimate):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_bucket_mesh("BucketLow", bevel_offset=0.003, bevel_segments=2)
    high = build_bucket_mesh("BucketHigh", bevel_offset=0.003, bevel_segments=4)
    wood = principled("BucketWood", (0.46, 0.24, 0.09, 1.0), 0.0, 0.52)
    metal = principled("BucketMetal", (0.58, 0.56, 0.52, 1.0), 1.0, 0.24)
    rope = principled("BucketRope", (0.42, 0.32, 0.18, 1.0), 0.0, 0.78)
    assign_slots(low, wood, metal, rope)
    assign_slots(high, wood, metal, rope)

    if low.data is None or len(low.data.polygons) < 6:
        return fail("bucket mesh did not build", 3), None, None, None, None, None

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
        return fail("bucket has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BucketLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BucketLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_bucket_mesh("BucketColSrc", bevel_offset=0.0, bevel_segments=1)
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

    print(
        f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}"
    )
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

    # Three-quarter from above so the open basin and bottom read.
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
    cam.location = (1.05, -1.42, 1.12)
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
    p.add_argument(
        "--skip-decimate",
        action="store_true",
        help="falsification: skip the LOD DECIMATE stage",
    )
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(args.skip_decimate)
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
