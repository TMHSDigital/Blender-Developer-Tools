"""Game-ready street lantern — a showcase piece, not an example.

Asserts budget conformance of a procedural hanging lantern after composing
shipped pipeline pieces: bmesh construction, UVs, three materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

The arm axis, drop length, and roof stack are one closed-form chain: the
roof peak stays below the arm, the hanger is the arm's far station, and
the brace is an oriented box between a post-radius station and an arm
station. The square pyramid is lofted on the cage axes, not a 4-gon cone.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-brace`` brace-to-arm
joint, ``--sink-arm`` arm-over-roof clearance, ``--rake-post`` post plumb.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python street_lantern.py --
    blender --background --python street_lantern.py -- --skip-decimate
    blender --background --python street_lantern.py -- --output lantern.png
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

# Showcase lives at repo-root/showcase/, not under examples/. The framing
# helper is the repo's only shared import and lives next to the examples;
# resolve the repo root so we do not move gallery_framing.py.
_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

# Stepped plinth. One body at Z=0 — no coplanar corner pads.
FOOT_BASE = 0.30
FOOT_BASE_H = 0.042
FOOT_STEP = 0.22
FOOT_STEP_H = 0.038
# Step sits into the base so the two boxes do not share a coplanar face.
STEP_SINK = 0.002
FOOT_H = FOOT_BASE_H + FOOT_STEP_H - STEP_SINK

POST_SIDES = 8
POST_R_BOT = 0.050
POST_R_TOP = 0.042
POST_H = 1.12
COLLAR_H = 0.036
COLLAR_T = 0.016
CAP_H = 0.050
CAP_R = POST_R_TOP + 0.028
POST_FINIAL_H = 0.070

ARM_R = 0.022
ARM_LEN = 0.50
BRACE_T = 0.024
BRACE_POST_DROP = 0.155
BRACE_ARM_FRAC = 0.46

CAGE_W = 0.24
CAGE_H = 0.30
FRAME = 0.022
MUNTIN = 0.010
PANE_T = 0.006
PANE_REBATE = 0.003
# Rails seat into posts without sharing vertex positions.
CAGE_JOINT = 0.0015
ROOF_H = 0.095
FINIAL_H = 0.050
EAVE = 0.016
# Roof stack plus a gap so the arm passes *over* the cage, never through it.
DROP_H = ARM_R + ROOF_H + FINIAL_H + 0.024

BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.300, 0.786, 1.287)
POST_SIZE = (POST_R_BOT * 2.0, POST_H)
POST_SIZE_TOL = (0.02, 0.04)
BASE_TRIS_MIN = 3000
BASE_TRIS_MAX = 3800
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 120
BAKE_RES = 256
CAGE_EXTRUSION = 0.06
GLASS_FACES_MIN = 8
BRASS_FACES_MIN = 24
METAL_FACES_MIN = 200

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.998
LIFT_Z = 0.05
BRACE_GAP_MAX = 0.006
ARM_ROOF_CLEAR_MIN = 0.008
HANGER_ROOF_GAP_MAX = 0.004
PLUMB_MAX = 0.008
SINK_ARM = 0.14
RAKE = math.radians(8.0)

METAL_IDX = 0
GLASS_IDX = 1
BRASS_IDX = 2


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


def post_radius_at(z):
    t = (z - FOOT_H) / POST_H
    t = max(0.0, min(1.0, t))
    return POST_R_BOT + t * (POST_R_TOP - POST_R_BOT)


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
        cap_tris=True,
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


def add_square_pyramid(bm, loc, half, height, mat_idx):
    """Square pyramid whose base edges are parallel to X/Y — the cage axes."""
    origin = Vector(loc)
    z0 = origin.z - height * 0.5
    z1 = origin.z + height * 0.5
    corners = [
        bm.verts.new((origin.x - half, origin.y - half, z0)),
        bm.verts.new((origin.x + half, origin.y - half, z0)),
        bm.verts.new((origin.x + half, origin.y + half, z0)),
        bm.verts.new((origin.x - half, origin.y + half, z0)),
    ]
    apex = bm.verts.new((origin.x, origin.y, z1))
    for i in range(4):
        face = bm.faces.new((corners[i], corners[(i + 1) % 4], apex))
        face.material_index = mat_idx
    base = bm.faces.new(tuple(reversed(corners)))
    base.material_index = mat_idx
    return corners + [apex]


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


def build_lantern_mesh(
    name,
    bevel_offset,
    bevel_segments,
    float_brace=False,
    sink_arm=False,
    rake_post=False,
):
    bm = bmesh.new()
    try:
        bevel_verts = []
        post_z0 = FOOT_H
        post_top = post_z0 + POST_H
        hang_z = post_top
        arm_z = post_top
        if sink_arm:
            arm_z -= SINK_ARM
        cage_y = ARM_LEN
        cage_top = hang_z - DROP_H
        cage_bot = cage_top - CAGE_H
        cage_mid = 0.5 * (cage_top + cage_bot)
        post_euler = (RAKE, 0.0, 0.0) if rake_post else (0.0, 0.0, 0.0)

        bevel_verts.extend(
            add_box(
                bm,
                (0.0, 0.0, FOOT_BASE_H / 2.0),
                (FOOT_BASE, FOOT_BASE, FOOT_BASE_H),
                METAL_IDX,
            )
        )
        step_z0 = FOOT_BASE_H - STEP_SINK
        bevel_verts.extend(
            add_box(
                bm,
                (0.0, 0.0, step_z0 + FOOT_STEP_H / 2.0),
                (FOOT_STEP, FOOT_STEP, FOOT_STEP_H),
                METAL_IDX,
            )
        )
        add_cone(
            bm,
            (0.0, 0.0, post_z0 + 0.030),
            0.100,
            0.072,
            0.056,
            12,
            BRASS_IDX,
        )
        add_cone(
            bm,
            (0.0, 0.0, post_z0 + POST_H / 2.0),
            POST_R_BOT,
            POST_R_TOP,
            POST_H,
            POST_SIDES,
            METAL_IDX,
            euler=post_euler,
        )
        collar_z = post_z0 + POST_H * 0.36
        collar_r = post_radius_at(collar_z) + COLLAR_T
        add_cone(
            bm,
            (0.0, 0.0, collar_z),
            collar_r,
            collar_r,
            COLLAR_H,
            12,
            BRASS_IDX,
        )
        add_cone(
            bm,
            (0.0, 0.0, post_top),
            CAP_R,
            CAP_R,
            CAP_H,
            12,
            BRASS_IDX,
        )
        add_cone(
            bm,
            (0.0, 0.0, post_top + CAP_H / 2.0 + POST_FINIAL_H * 0.42),
            0.028,
            0.005,
            POST_FINIAL_H,
            8,
            BRASS_IDX,
        )

        arm_y0 = post_radius_at(arm_z) - 0.008
        arm_y1 = cage_y
        add_cone(
            bm,
            (0.0, 0.5 * (arm_y0 + arm_y1), arm_z),
            ARM_R,
            ARM_R,
            arm_y1 - arm_y0,
            8,
            METAL_IDX,
            euler=(math.radians(90.0), 0.0, 0.0),
        )

        brace_z = arm_z - BRACE_POST_DROP
        post_r = post_radius_at(brace_z)
        p_post = Vector((0.0, post_r + BRACE_T * 0.35, brace_z))
        p_arm = Vector((0.0, ARM_LEN * BRACE_ARM_FRAC, arm_z - ARM_R - BRACE_T * 0.20))
        if float_brace:
            p_arm = p_post + Vector((0.0, 0.11, -0.06))
        bevel_verts.extend(add_oriented_box(bm, p_post, p_arm, (BRACE_T, BRACE_T), METAL_IDX))

        apex_z = cage_top - 0.001 + ROOF_H
        stub_bot = apex_z + FINIAL_H * 0.70
        stub_top = arm_z - ARM_R + 0.006
        if stub_top - stub_bot > 0.008:
            add_cone(
                bm,
                (0.0, cage_y, 0.5 * (stub_top + stub_bot)),
                0.011,
                0.011,
                stub_top - stub_bot,
                8,
                METAL_IDX,
            )

        hw = CAGE_W / 2.0 - FRAME / 2.0
        post_h = CAGE_H - 2.0 * FRAME + 2.0 * CAGE_JOINT
        for sxn in (-1.0, 1.0):
            for syn in (-1.0, 1.0):
                bevel_verts.extend(
                    add_box(
                        bm,
                        (sxn * hw, cage_y + syn * hw, cage_mid),
                        (FRAME, FRAME, post_h),
                        METAL_IDX,
                    )
                )
        rail_len = CAGE_W - 2.0 * FRAME + 2.0 * CAGE_JOINT
        for z in (cage_bot + FRAME / 2.0, cage_mid, cage_top - FRAME / 2.0):
            for sign in (-1.0, 1.0):
                bevel_verts.extend(
                    add_box(
                        bm,
                        (0.0, cage_y + sign * hw, z),
                        (rail_len, FRAME, FRAME),
                        METAL_IDX,
                    )
                )
                bevel_verts.extend(
                    add_box(
                        bm,
                        (sign * hw, cage_y, z),
                        (FRAME, rail_len, FRAME),
                        METAL_IDX,
                    )
                )
        opening = (CAGE_H - 3.0 * FRAME) / 2.0
        muntin_h = opening + 2.0 * CAGE_JOINT
        lower_z = cage_bot + FRAME + opening / 2.0
        upper_z = cage_top - FRAME - opening / 2.0
        for sign in (-1.0, 1.0):
            for z in (lower_z, upper_z):
                bevel_verts.extend(
                    add_box(
                        bm,
                        (0.0, cage_y + sign * hw, z),
                        (MUNTIN, FRAME * 0.80, muntin_h),
                        METAL_IDX,
                    )
                )
                bevel_verts.extend(
                    add_box(
                        bm,
                        (sign * hw, cage_y, z),
                        (FRAME * 0.80, MUNTIN, muntin_h),
                        METAL_IDX,
                    )
                )

        open_w = CAGE_W - 2.0 * FRAME - 0.004
        open_h = CAGE_H - 2.0 * FRAME - 0.004
        pane_inset = CAGE_W / 2.0 - FRAME - PANE_T / 2.0 - PANE_REBATE
        add_box(
            bm,
            (0.0, cage_y + pane_inset, cage_mid),
            (open_w, PANE_T, open_h),
            GLASS_IDX,
        )
        add_box(
            bm,
            (0.0, cage_y - pane_inset, cage_mid),
            (open_w, PANE_T, open_h),
            GLASS_IDX,
        )
        add_box(
            bm,
            (pane_inset, cage_y, cage_mid),
            (PANE_T, open_w, open_h),
            GLASS_IDX,
        )
        add_box(
            bm,
            (-pane_inset, cage_y, cage_mid),
            (PANE_T, open_w, open_h),
            GLASS_IDX,
        )

        add_cone(
            bm,
            (0.0, cage_y, cage_bot + 0.040),
            0.024,
            0.018,
            0.048,
            8,
            BRASS_IDX,
        )

        roof_half = CAGE_W / 2.0 + EAVE
        add_square_pyramid(
            bm,
            Vector((0.0, cage_y, cage_top - 0.001 + ROOF_H / 2.0)),
            roof_half,
            ROOF_H,
            BRASS_IDX,
        )
        add_cone(
            bm,
            (0.0, cage_y, apex_z + FINIAL_H * 0.22),
            0.014,
            0.014,
            FINIAL_H * 0.44,
            8,
            BRASS_IDX,
        )
        add_cone(
            bm,
            (0.0, cage_y, apex_z + FINIAL_H * 0.62),
            0.020,
            0.006,
            FINIAL_H * 0.40,
            8,
            BRASS_IDX,
        )

        if bevel_offset > 0.0:
            edges = list({e for v in bevel_verts for e in v.link_edges})
            bmesh.ops.bevel(
                bm,
                geom=edges,
                offset=bevel_offset,
                segments=bevel_segments,
                profile=0.5,
                affect="EDGES",
                clamp_overlap=True,
            )

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        triangulate_ngons(bm)
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

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = face.material_index == GLASS_IDX
        for edge in bm.edges:
            mats = {f.material_index for f in edge.link_faces}
            if GLASS_IDX in mats:
                edge.smooth = False
            elif edge.is_manifold and len(edge.link_faces) == 2:
                edge.smooth = edge.calc_face_angle() < math.radians(35.0)
            else:
                edge.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        for poly in me.polygons:
            poly.use_smooth = poly.material_index == GLASS_IDX
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def principled(name, color, metallic, roughness, emission=None, roughness_var=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission is not None:
        ecol, strength = emission
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = ecol
            bsdf.inputs["Emission Strength"].default_value = strength
        elif "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = ecol
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = strength
    if roughness_var > 0.0:
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 14.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        lo = max(0.05, roughness - roughness_var)
        hi = min(0.95, roughness + roughness_var)
        ramp.color_ramp.elements[0].position = 0.30
        ramp.color_ramp.elements[0].color = (lo, lo, lo, 1.0)
        ramp.color_ramp.elements[1].position = 0.70
        ramp.color_ramp.elements[1].color = (hi, hi, hi, 1.0)
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
    return mat


def assign_slots(obj, metal, glass, brass):
    # Do not materials.clear() — that resets polygon material_index to 0
    # on this Blender, which would drop glass/brass faces onto metal.
    mats = obj.data.materials
    wanted = (metal, glass, brass)
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
        min(p.x for p in pts),
        min(p.y for p in pts),
        min(p.z for p in pts),
        max(p.x for p in pts),
        max(p.y for p in pts),
        max(p.z for p in pts),
    )


def mat_of(me, group):
    member = set(group)
    for poly in me.polygons:
        if all(i in member for i in poly.vertices):
            return poly.material_index
    return None


def shell_bvh_gap(me, ga, gb):
    """Nearest surface distance between two shells. Vert-vert misses mid-face seats."""
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
            if hit[0] is None:
                continue
            best = min(best, hit[3])
        for face in bm_a.faces:
            hit = tree.find_nearest(face.calc_center_median())
            if hit[0] is None:
                continue
            best = min(best, hit[3])
        return best
    finally:
        bm_a.free()
        bm_b.free()


def joint_audit(me):
    """Brace reaches the arm; roof stays under the arm."""
    groups = shells(me)
    boxes = [(g, shell_aabb(me, g), mat_of(me, g)) for g in groups]
    arms = []
    braces = []
    roofs = []
    hangers = []
    posts = []
    for g, a, mat in boxes:
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        cy = 0.5 * (a[1] + a[4])
        cz = 0.5 * (a[2] + a[5])
        if mat == METAL_IDX and dy > ARM_LEN * 0.55 and dz < ARM_R * 4.0 and dx < ARM_R * 4.0:
            arms.append((g, a))
            continue
        if mat == METAL_IDX and dz > POST_H * 0.7 and dx < POST_R_BOT * 3.0 and dy < POST_R_BOT * 3.0:
            posts.append((g, a))
            continue
        if mat == METAL_IDX and dz > 0.10 and dy > 0.10 and dx < 0.08 and cz > 0.9:
            braces.append((g, a))
            continue
        if mat == BRASS_IDX and dx > CAGE_W * 0.6 and dy > CAGE_W * 0.6 and cz > 0.9:
            roofs.append((g, a))
        if (
            mat == BRASS_IDX
            and dx < 0.06
            and dy < 0.06
            and cz > 0.9
        ):
            hangers.append((g, a))
    brace_gap = 99.0
    if arms and braces:
        brace_gap = min(shell_bvh_gap(me, b[0], a[0]) for b in braces for a in arms)
    roof_zmax = max((a[5] for _g, a in roofs), default=0.0)
    arm_zmin = min((a[2] for _g, a in arms), default=99.0)
    hanger_zmin = min((a[2] for _g, a in hangers), default=99.0)
    return {
        "parts": len(groups),
        "arms": len(arms),
        "braces": len(braces),
        "roofs": len(roofs),
        "posts": len(posts),
        "hangers": len(hangers),
        "brace_gap": brace_gap,
        "arm_roof_clear": arm_zmin - roof_zmax,
        "hanger_roof_gap": hanger_zmin - roof_zmax,
    }


def plumb_audit(me):
    """XY centroid of the post's bottom slab vs top slab."""
    drifts = []
    for group in shells(me):
        if mat_of(me, group) != METAL_IDX:
            continue
        a = shell_aabb(me, group)
        dz = a[5] - a[2]
        dx = a[3] - a[0]
        dy = a[4] - a[1]
        if dz < POST_H * 0.7 or dx > POST_R_BOT * 3.0 or dy > POST_R_BOT * 3.0:
            continue
        pts = [me.vertices[i].co for i in group]
        zcut_lo = a[2] + 0.08 * dz
        zcut_hi = a[5] - 0.08 * dz
        lo = [p for p in pts if p.z <= zcut_lo]
        hi = [p for p in pts if p.z >= zcut_hi]
        if len(lo) < 3 or len(hi) < 3:
            continue
        c_lo = Vector((sum(p.x for p in lo) / len(lo), sum(p.y for p in lo) / len(lo)))
        c_hi = Vector((sum(p.x for p in hi) / len(hi), sum(p.y for p in hi) / len(hi)))
        drifts.append((c_hi - c_lo).length)
    return max(drifts) if drifts else 99.0


def post_size(me):
    for group in shells(me):
        if mat_of(me, group) != METAL_IDX:
            continue
        a = shell_aabb(me, group)
        dz = a[5] - a[2]
        dx = a[3] - a[0]
        dy = a[4] - a[1]
        if dz < POST_H * 0.7 or dx > POST_R_BOT * 3.0 or dy > POST_R_BOT * 3.0:
            continue
        return max(dx, dy), dz
    return 0.0, 0.0


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, FOOT_H + POST_H * 0.4))
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
    img = bpy.data.images.new("LanternNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = METAL_IDX
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


def check(
    skip_decimate,
    lift_z=False,
    stray_vert=False,
    float_brace=False,
    sink_arm=False,
    rake_post=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_lantern_mesh(
        "LanternLow",
        bevel_offset=0.004,
        bevel_segments=2,
        float_brace=float_brace,
        sink_arm=sink_arm,
        rake_post=rake_post,
    )
    high = build_lantern_mesh(
        "LanternHigh",
        bevel_offset=0.004,
        bevel_segments=4,
        float_brace=float_brace,
        sink_arm=sink_arm,
        rake_post=rake_post,
    )
    metal = principled("LanternMetal", (0.045, 0.048, 0.055, 1.0), 0.88, 0.34, roughness_var=0.08)
    glass = principled(
        "LanternGlass",
        (0.62, 0.32, 0.08, 1.0),
        0.0,
        0.22,
        emission=((0.85, 0.42, 0.10, 1.0), 0.45),
    )
    brass = principled("LanternBrass", (0.72, 0.46, 0.14, 1.0), 1.0, 0.28, roughness_var=0.07)
    assign_slots(low, metal, glass, brass)
    assign_slots(high, metal, glass, brass)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("lantern mesh did not build", 3), None, None, None, None, None

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
    jnt = joint_audit(low.data)
    plumb = plumb_audit(low.data)
    pxy, pz = post_size(low.data)

    img, tex = setup_bake_image(low, metal)
    if img is None:
        return fail("lantern has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "LanternLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "LanternLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_lantern_mesh(
        "LanternColSrc", bevel_offset=0.0, bevel_segments=1
    )
    collider = convex_hull_collider(collider_src, "LanternCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_street_lantern_{os.getpid()}.glb",
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
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}"
    )
    print(
        f"measured brace_gap={jnt['brace_gap']:.5f} "
        f"arm_roof_clear={jnt['arm_roof_clear']:.5f} "
        f"hanger_roof_gap={jnt['hanger_roof_gap']:.5f} "
        f"plumb={plumb:.5f} post_size=({pxy:.4f},{pz:.4f}) "
        f"parts={jnt['parts']} arms={jnt['arms']} braces={jnt['braces']} "
        f"roofs={jnt['roofs']} hangers={jnt['hangers']}"
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
    if idx_counts.get(GLASS_IDX, 0) < GLASS_FACES_MIN:
        return fail(
            f"glass faces {idx_counts.get(GLASS_IDX, 0)} < {GLASS_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(BRASS_IDX, 0) < BRASS_FACES_MIN:
        return fail(
            f"brass faces {idx_counts.get(BRASS_IDX, 0)} < {BRASS_FACES_MIN}",
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
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}",
            15,
        ), None, None, None, None, None
    if bb[2] > ZMIN_EPS:
        return fail(f"grounded zmin={bb[2]:.5f}", 16), None, None, None, None, None
    if jnt["braces"] < 1 or jnt["brace_gap"] > BRACE_GAP_MAX:
        return fail(
            f"brace gap {jnt['brace_gap']:.5f} braces={jnt['braces']}",
            17,
        ), None, None, None, None, None
    if jnt["arm_roof_clear"] < ARM_ROOF_CLEAR_MIN:
        return fail(
            f"arm-roof clearance {jnt['arm_roof_clear']:.5f}",
            18,
        ), None, None, None, None, None
    if jnt["hangers"] < 1 or jnt["hanger_roof_gap"] > HANGER_ROOF_GAP_MAX:
        return fail(
            f"hanger-roof gap {jnt['hanger_roof_gap']:.5f} hangers={jnt['hangers']}",
            18,
        ), None, None, None, None, None
    if (
        plumb > PLUMB_MAX
        or abs(pxy - POST_SIZE[0]) > POST_SIZE_TOL[0]
        or abs(pz - POST_SIZE[1]) > POST_SIZE_TOL[1]
    ):
        return fail(
            f"plumb {plumb:.5f} post_size=({pxy:.4f},{pz:.4f})",
            19,
        ), None, None, None, None, None
    return 0, low, high, metal, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, metal, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(metal, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    low.rotation_euler.z = math.radians(-28.0)
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

    light("Key", (-3.6, -5.0, 5.8), 680.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.6, 2.6), 48.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.4, 4.2, 4.1), 640.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.55, -3.70, 1.85)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.72)
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
    p.add_argument("--float-brace", action="store_true")
    p.add_argument("--sink-arm", action="store_true")
    p.add_argument("--rake-post", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, metal, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_brace=args.float_brace,
        sink_arm=args.sink_arm,
        rake_post=args.rake_post,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, metal, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("street-lantern OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
