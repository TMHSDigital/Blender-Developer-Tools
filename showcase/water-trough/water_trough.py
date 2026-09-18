"""Game-ready wooden water trough — a showcase piece, not an example.

Asserts budget conformance of a procedural staved trough on a timber
stand (U-staves and U end-caps from one radius function, contained
water, iron straps lofted on that same host, trestle legs) after
composing shipped pipeline pieces: bmesh construction, UVs, three
materials, high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

The hull, ends, straps and water all sample the same YZ arc. End caps
are U-boards the staves tenon into, not a bounding-box slab around the
U. Legs run from a hull-outer station to a shoe at Z=0.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-legs`` named shoe
supports, ``--box-ends`` end-cap U-fit, ``--float-strap`` strap seat,
``--narrow-hull`` hull real-world size.

No RNG. Stave seams use closed-form ``sin(i)``. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python water_trough.py --
    blender --background --python water_trough.py -- --skip-decimate
    blender --background --python water_trough.py -- --output trough.png
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

TRAY_L = 1.08
TRAY_R = 0.22
STAVE_T = 0.032
N_STAVES = 10
A_SPAN = 1.20
END_T = 0.044
END_OVERHANG = 0.010
STAVE_GAP = 0.008
STRAP_W = 0.028
STRAP_T = 0.008
STRAP_BITE = 0.008
SHOE_H = 0.028
SHOE_XY = (0.058, 0.052)
LEG_X = TRAY_L * 0.28
STRAP_X = TRAY_L * 0.18
LEG_TOP_Y = 0.090
LEG_BOT_Y = 0.250
STRETCHER_Z = 0.115
STRETCHER_T = 0.028
LEG_W = 0.048
WATER_GAP = 0.004
WATER_FILL = 0.68

BBOX_TOL = 0.01
OUTER_SIZE = (1.093, 0.552, 0.504)
HULL_SIZE = (1.08, 0.44)
HULL_SIZE_TOL = (0.08, 0.08)
NARROW_HULL_R = 0.12
BASE_TRIS_MIN = 3300
BASE_TRIS_MAX = 4000
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 80
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
METAL_FACES_MIN = 24
WOOD_FACES_MIN = 24
WATER_FACES_MIN = 6

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.998
LIFT_Z = 0.05
SHOE_COUNT = 4
SHOE_ZMIN_MAX = 1e-3
END_RIM_SPAN_MAX = 0.080
STRAP_GAP_MAX = 0.008
WATER_CONTACT_MAX = 0.008
PLUMB_MAX = 0.010

WOOD_IDX = 0
METAL_IDX = 1
WATER_IDX = 2


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


def _face(bm, vs, mat_idx):
    face = bm.faces.new(vs)
    face.material_index = mat_idx
    return face


def _arc_point(a, radius, x, zc):
    return Vector((x, radius * math.sin(a), zc - radius * math.cos(a)))


def hull_z_at_y(y, radius, zc):
    y = max(-radius + 1e-6, min(radius - 1e-6, y))
    return zc - math.sqrt(radius * radius - y * y)


def add_u_shell(bm, x0, x1, r_in, r_out, n_seg, zc, a_span, mat_idx):
    in0, out0, in1, out1 = [], [], [], []
    for i in range(n_seg + 1):
        a = -a_span + 2.0 * a_span * i / n_seg
        in0.append(bm.verts.new(_arc_point(a, r_in, x0, zc)))
        out0.append(bm.verts.new(_arc_point(a, r_out, x0, zc)))
        in1.append(bm.verts.new(_arc_point(a, r_in, x1, zc)))
        out1.append(bm.verts.new(_arc_point(a, r_out, x1, zc)))
    collected = in0 + out0 + in1 + out1
    for i in range(n_seg):
        _face(bm, (out0[i], out0[i + 1], out1[i + 1], out1[i]), mat_idx)
        _face(bm, (in0[i + 1], in0[i], in1[i], in1[i + 1]), mat_idx)
        _face(bm, (out0[i], in0[i], in0[i + 1], out0[i + 1]), mat_idx)
        _face(bm, (out1[i + 1], in1[i + 1], in1[i], out1[i]), mat_idx)
    _face(bm, (out0[0], out1[0], in1[0], in0[0]), mat_idx)
    _face(bm, (out0[n_seg], in0[n_seg], in1[n_seg], out1[n_seg]), mat_idx)
    return collected


def add_stave(bm, a0, a1, x0, x1, r_in, r_out, zc, mat_idx):
    def ring(x):
        return [
            bm.verts.new(_arc_point(a0, r_out, x, zc)),
            bm.verts.new(_arc_point(a1, r_out, x, zc)),
            bm.verts.new(_arc_point(a1, r_in, x, zc)),
            bm.verts.new(_arc_point(a0, r_in, x, zc)),
        ]

    r0 = ring(x0)
    r1 = ring(x1)
    _face(bm, (r0[0], r0[1], r1[1], r1[0]), mat_idx)
    _face(bm, (r0[2], r0[3], r1[3], r1[2]), mat_idx)
    _face(bm, (r0[1], r0[2], r1[2], r1[1]), mat_idx)
    _face(bm, (r0[3], r0[0], r1[0], r1[3]), mat_idx)
    _face(bm, (r0[0], r0[3], r0[2], r0[1]), mat_idx)
    _face(bm, (r1[0], r1[1], r1[2], r1[3]), mat_idx)
    return r0 + r1


def add_box_end(bm, x_mid, radius, zc, a_span, thick, mat_idx):
    y_span = 2.0 * radius * math.sin(a_span)
    z_lo = zc - radius
    z_hi = zc - radius * math.cos(a_span)
    z_mid = 0.5 * (z_lo + z_hi)
    verts = add_box(
        bm,
        (x_mid, 0.0, z_mid),
        (thick, y_span, z_hi - z_lo),
        mat_idx,
    )
    edges = list({e for v in verts for e in v.link_edges})
    bmesh.ops.subdivide_edges(bm, edges=edges, cuts=6, use_grid_fill=True)
    return verts


def add_u_water(bm, x0, x1, r, n_seg, zc, z_water, mat_idx):
    ca = max(-1.0, min(1.0, (zc - z_water) / r))
    a_wl = math.acos(ca)
    ring0, ring1 = [], []
    for i in range(n_seg + 1):
        a = -a_wl + 2.0 * a_wl * i / n_seg
        ring0.append(bm.verts.new(_arc_point(a, r, x0, zc)))
        ring1.append(bm.verts.new(_arc_point(a, r, x1, zc)))
    collected = ring0 + ring1
    for i in range(n_seg):
        _face(bm, (ring0[i], ring0[i + 1], ring1[i + 1], ring1[i]), mat_idx)
    _face(bm, (ring0[0], ring1[0], ring1[n_seg], ring0[n_seg]), mat_idx)
    _face(bm, tuple(reversed(ring0)), mat_idx)
    _face(bm, tuple(ring1), mat_idx)
    return collected


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


def build_trough_mesh(
    name,
    bevel_offset,
    bevel_segments,
    box_ends=False,
    float_strap=False,
    short_legs=False,
    narrow_hull=False,
):
    bm = bmesh.new()
    try:
        wood = []
        tray_r = NARROW_HULL_R if narrow_hull else TRAY_R
        zc = SHOE_H + 0.335 + TRAY_R
        r_in = tray_r
        r_out = tray_r + STAVE_T
        x_cap_l0 = -TRAY_L / 2.0 - END_T * 0.15
        x_cap_l1 = -TRAY_L / 2.0 + END_T * 0.85
        x_cap_r0 = TRAY_L / 2.0 - END_T * 0.85
        x_cap_r1 = TRAY_L / 2.0 + END_T * 0.15
        x_stave_0 = -TRAY_L / 2.0 + END_T * 0.40
        x_stave_1 = TRAY_L / 2.0 - END_T * 0.40

        span = 2.0 * A_SPAN
        usable = span - STAVE_GAP * N_STAVES
        width = usable / N_STAVES
        a = -A_SPAN + STAVE_GAP * 0.5
        for i in range(N_STAVES):
            jitter = 0.0035 * math.sin(i * 1.7 + 0.4)
            a0 = a
            a1 = a + width + jitter
            wood.extend(
                add_stave(bm, a0, a1, x_stave_0, x_stave_1, r_in, r_out, zc, WOOD_IDX)
            )
            a = a1 + STAVE_GAP

        if not box_ends:
            r_cap_in = r_in - 0.006
            r_cap_out = r_out + END_OVERHANG
            wood.extend(
                add_u_shell(
                    bm, x_cap_l0, x_cap_l1, r_cap_in, r_cap_out, N_STAVES, zc, A_SPAN, WOOD_IDX
                )
            )
            wood.extend(
                add_u_shell(
                    bm, x_cap_r0, x_cap_r1, r_cap_in, r_cap_out, N_STAVES, zc, A_SPAN, WOOD_IDX
                )
            )

        top_z = hull_z_at_y(LEG_TOP_Y, r_out, zc)
        bot_z = SHOE_H * 0.55
        shoe_mid = SHOE_H / 2.0
        if short_legs:
            shoe_mid += 0.045
        for sx in (-LEG_X, LEG_X):
            for ysign in (-1.0, 1.0):
                top_pt = Vector((sx, ysign * LEG_TOP_Y, top_z))
                bot_pt = Vector((sx, ysign * LEG_BOT_Y, bot_z))
                direction = (top_pt - bot_pt).normalized()
                top_pt = top_pt + direction * (STAVE_T * 0.35)
                wood.extend(add_oriented_box(bm, top_pt, bot_pt, (LEG_W, 0.034), WOOD_IDX))
            t_st = (STRETCHER_Z - bot_z) / max(top_z - bot_z, 1e-6)
            y_leg = LEG_BOT_Y + t_st * (LEG_TOP_Y - LEG_BOT_Y)
            # Inner face of the diagonal leg, not through its volume.
            side_len = 2.0 * (y_leg - 0.022)
            wood.extend(
                add_box(
                    bm,
                    (sx, 0.0, STRETCHER_Z),
                    (0.042, side_len, STRETCHER_T),
                    WOOD_IDX,
                )
            )
        long_len = 2.0 * LEG_X - LEG_W
        wood.extend(
            add_box(
                bm,
                (0.0, 0.0, STRETCHER_Z),
                (long_len, 0.042, STRETCHER_T),
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

        if box_ends:
            add_box_end(
                bm, 0.5 * (x_cap_l0 + x_cap_l1), r_out, zc, A_SPAN, END_T, WOOD_IDX
            )
            add_box_end(
                bm, 0.5 * (x_cap_r0 + x_cap_r1), r_out, zc, A_SPAN, END_T, WOOD_IDX
            )

        r_strap_in = r_out + 0.040 if float_strap else r_out - STRAP_BITE
        r_strap_out = r_strap_in + STRAP_T
        for sx in (-STRAP_X, STRAP_X):
            add_u_shell(
                bm,
                sx - STRAP_W / 2.0,
                sx + STRAP_W / 2.0,
                r_strap_in,
                r_strap_out,
                16,
                zc,
                A_SPAN,
                METAL_IDX,
            )
        for sx in (-LEG_X, LEG_X):
            for ysign in (-1.0, 1.0):
                add_box(
                    bm,
                    (sx, ysign * LEG_BOT_Y, shoe_mid),
                    (SHOE_XY[0], SHOE_XY[1], SHOE_H),
                    METAL_IDX,
                )

        z_bot = zc - r_in
        z_rim = zc - r_in * math.cos(A_SPAN)
        z_water = z_bot + WATER_FILL * (z_rim - z_bot)
        add_u_water(
            bm,
            x_cap_l1 - 0.010,
            x_cap_r0 + 0.010,
            r_in - WATER_GAP,
            N_STAVES,
            zc,
            z_water,
            WATER_IDX,
        )

        triangulate_ngons(bm)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6)
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        rcx = 0.5 * (min(xs) + max(xs))
        rcy = 0.5 * (min(ys) + max(ys))
        zmin = min(zs)
        for v in bm.verts:
            v.co.x -= rcx
            v.co.y -= rcy
            v.co.z -= zmin
            if v.co.z < 0.0:
                v.co.z = 0.0

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        for poly in me.polygons:
            poly.use_smooth = False
    finally:
        bm.free()
    out = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(out)
    return out


def principled(name, color, metallic, roughness, roughness_var=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if roughness_var > 0.0:
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 11.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        lo = max(0.08, roughness - roughness_var)
        hi = min(0.95, roughness + roughness_var)
        ramp.color_ramp.elements[0].position = 0.28
        ramp.color_ramp.elements[0].color = (lo, lo, lo, 1.0)
        ramp.color_ramp.elements[1].position = 0.72
        ramp.color_ramp.elements[1].color = (hi, hi, hi, 1.0)
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
    return mat


def assign_slots(obj, wood, metal, water):
    mats = obj.data.materials
    wanted = (wood, metal, water)
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


def min_vert_gap(me, ga, gb):
    pa = [me.vertices[i].co for i in ga]
    pb = [me.vertices[i].co for i in gb]
    step_a = max(1, len(pa) // 80)
    step_b = max(1, len(pb) // 80)
    best = 1e9
    for a in pa[::step_a]:
        for b in pb[::step_b]:
            d = (a - b).length
            if d < best:
                best = d
    return best


def support_audit(me):
    shoes = []
    for group in shells(me):
        if mat_of(me, group) != METAL_IDX:
            continue
        a = shell_aabb(me, group)
        dz = a[5] - a[2]
        dx = a[3] - a[0]
        dy = a[4] - a[1]
        cz = 0.5 * (a[2] + a[5])
        if cz > 0.08 or dz > 0.06:
            continue
        if max(dx, dy) < 0.03:
            continue
        shoes.append(a)
    zmin = min((a[2] for a in shoes), default=99.0)
    return {"shoes": len(shoes), "shoe_z": zmin}


def joint_audit(me):
    groups = shells(me)
    boxes = [(g, shell_aabb(me, g), mat_of(me, g)) for g in groups]
    staves = []
    ends = []
    straps = []
    waters = []
    for g, a, mat in boxes:
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        cx = 0.5 * (a[0] + a[3])
        if mat == WOOD_IDX and dx > TRAY_L * 0.5:
            staves.append((g, a))
            continue
        if mat == WOOD_IDX and dx < END_T * 3.5 and dy > 0.25 and abs(cx) > TRAY_L * 0.35:
            ends.append((g, a))
            continue
        if mat == METAL_IDX and dy > 0.15 and dz > 0.10:
            straps.append((g, a))
            continue
        if mat == WATER_IDX:
            waters.append((g, a))
    hulls = staves
    rim_span = 0.0
    for g, a in ends:
        pts = [me.vertices[i].co for i in g]
        ymax = max(abs(p.y) for p in pts)
        rim = [p for p in pts if abs(abs(p.y) - ymax) < 0.025]
        if rim:
            span = max(p.z for p in rim) - min(p.z for p in rim)
            if span > rim_span:
                rim_span = span
    strap_gap = 99.0
    if straps and hulls:
        strap_gap = min(shell_bvh_gap(me, s[0], h[0]) for s in straps for h in hulls)
    water_gap = 99.0
    if waters and hulls:
        water_gap = min(shell_bvh_gap(me, w[0], h[0]) for w in waters for h in hulls)
    hull_xy = (0.0, 0.0)
    if staves:
        xs = [v for _g, a in staves for v in (a[0], a[3])]
        ys = [v for _g, a in staves for v in (a[1], a[4])]
        hull_xy = (max(xs) - min(xs), max(ys) - min(ys))
    return {
        "parts": len(groups),
        "hulls": len(hulls),
        "ends": len(ends),
        "straps": len(straps),
        "waters": len(waters),
        "rim_span": rim_span,
        "strap_gap": strap_gap,
        "water_gap": water_gap,
        "hull_xy": hull_xy,
    }


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, 0.25))
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
    img = bpy.data.images.new("TroughNrm", size, size, alpha=True, float_buffer=False)
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
    box_ends=False,
    float_strap=False,
    short_legs=False,
    narrow_hull=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_trough_mesh(
        "TroughLow",
        bevel_offset=0.004,
        bevel_segments=2,
        box_ends=box_ends,
        float_strap=float_strap,
        short_legs=short_legs,
        narrow_hull=narrow_hull,
    )
    high = build_trough_mesh(
        "TroughHigh",
        bevel_offset=0.004,
        bevel_segments=4,
        box_ends=box_ends,
        float_strap=float_strap,
        short_legs=short_legs,
        narrow_hull=narrow_hull,
    )
    wood = principled("TroughWood", (0.40, 0.22, 0.08, 1.0), 0.0, 0.58, roughness_var=0.10)
    metal = principled("TroughIron", (0.10, 0.105, 0.12, 1.0), 1.0, 0.32, roughness_var=0.08)
    water = principled("TroughWater", (0.06, 0.16, 0.18, 1.0), 0.0, 0.08)
    assign_slots(low, wood, metal, water)
    assign_slots(high, wood, metal, water)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("trough mesh did not build", 3), None, None, None, None, None

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
    jnt = joint_audit(low.data)

    img, tex = setup_bake_image(low, wood)
    if img is None:
        return fail("trough has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "TroughLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "TroughLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_trough_mesh("TroughColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "TroughCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_water_trough_{os.getpid()}.glb",
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
        f"measured shoes={sup['shoes']} shoe_z={sup['shoe_z']:.5f} "
        f"rim_span={jnt['rim_span']:.4f} strap_gap={jnt['strap_gap']:.5f} "
        f"water_gap={jnt['water_gap']:.5f} hull_xy={jnt['hull_xy']} "
        f"ends={jnt['ends']} straps={jnt['straps']}"
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
    if idx_counts.get(WATER_IDX, 0) < WATER_FACES_MIN:
        return fail(
            f"water faces {idx_counts.get(WATER_IDX, 0)} < {WATER_FACES_MIN}",
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
    hx, hy = jnt["hull_xy"]
    if abs(hx - HULL_SIZE[0]) > HULL_SIZE_TOL[0] or abs(hy - HULL_SIZE[1]) > HULL_SIZE_TOL[1]:
        return fail(
            f"hull size ({hx:.4f},{hy:.4f}) off {HULL_SIZE}",
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
    if (
        bb[2] > ZMIN_EPS
        or sup["shoes"] != SHOE_COUNT
        or sup["shoe_z"] > SHOE_ZMIN_MAX
    ):
        return fail(
            f"grounded zmin={bb[2]:.5f} shoes={sup['shoes']} "
            f"shoe_z={sup['shoe_z']:.5f}",
            16,
        ), None, None, None, None, None
    if jnt["ends"] < 2 or jnt["rim_span"] > END_RIM_SPAN_MAX:
        return fail(
            f"end rim span {jnt['rim_span']:.4f} ends={jnt['ends']}",
            17,
        ), None, None, None, None, None
    if jnt["straps"] < 2 or jnt["strap_gap"] > STRAP_GAP_MAX:
        return fail(
            f"strap gap {jnt['strap_gap']:.5f} straps={jnt['straps']}",
            18,
        ), None, None, None, None, None
    if jnt["water_gap"] > WATER_CONTACT_MAX:
        return fail(
            f"water-hull gap {jnt['water_gap']:.5f}",
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

    low.rotation_euler.z = math.radians(-38.0)
    low.rotation_euler.x = math.radians(0.0)

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
    cam.location = (1.349, -1.833, 1.030)
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
    p.add_argument("--short-legs", action="store_true")
    p.add_argument("--box-ends", action="store_true")
    p.add_argument("--float-strap", action="store_true")
    p.add_argument("--narrow-hull", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        box_ends=args.box_ends,
        float_strap=args.float_strap,
        short_legs=args.short_legs,
        narrow_hull=args.narrow_hull,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("water-trough OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
