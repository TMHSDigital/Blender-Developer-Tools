"""Game-ready two-wheel wooden cart — a showcase piece, not an example.

Asserts budget conformance of a procedural cart (staved bed, side
walls, shafts, spoked wheels, iron hubs and axle) after composing
shipped pipeline pieces: bmesh construction, UVs, two materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF
export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier flag breaks one
stage so a named budget fails and the piece exits that budget's code:
``--skip-decimate`` (LOD ratio, 9), ``--lift-z`` (AABB grounded, 16),
``--float-wheel`` (named supports, 16), ``--flush-tyre`` (coplanar
cross-shell pairs, 15), ``--sink-tyre`` (tyre seat band, 18),
``--skew-wheel`` (wheel mirror, 19). The two wheel moves stay inside
``BBOX_TOL`` so the AABB gate cannot steal the failure.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python cart.py --
    blender --background --python cart.py -- --skip-decimate
    blender --background --python cart.py -- --flush-tyre
    blender --background --python cart.py -- --output cart.png
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

RIM_MAJOR = 0.30
# Felloe ring: flat-tread box section, not a round tube — round torus rims
# read as bicycle wheels. The iron tyre wraps the tread.
RIM_RADIAL = 0.012
RIM_W = 0.036
TYRE_T = 0.008
TYRE_W = 0.040
# Felloe outer radius is the *host* surface the tyre is hooped onto. The
# tyre's inner radius is derived from it minus a named interference, never
# set equal to it: r_in == r_out puts the tyre's inner cylinder and the
# felloe's tread on one plane for every segment, which is a guaranteed
# z-fight (it measured 32 coplanar cross-shell pairs, 16 per wheel).
RIM_OUTER = RIM_MAJOR + RIM_RADIAL
TYRE_SEAT = 0.004
TYRE_SEAT_MIN = 0.0030
TYRE_SEAT_MAX = 0.0055
WHEEL_SEGMENTS = 24
TRACK = 0.68
AXLE_X = -0.16
AXLE_R = 0.020
HUB_R = 0.052
HUB_W = 0.046
N_SPOKES = 8
SPOKE_T = 0.018
BED_L = 0.92
BED_W = 0.50
BED_T = 0.038
WALL_H = 0.16
WALL_T = 0.032
TAILGATE_H = 0.10
SHAFT_L = 0.58
SHAFT_T = 0.034
SHAFT_PITCH = math.radians(7.0)
N_SLATS = 6
IRON_T = 0.014
BOLSTER_H = 0.044

BBOX_TOL = 0.01
OUTER_SIZE = (1.539, 0.749, 0.640)
# Re-fitted after the wheel went from 16 to 24 segments (2600 -> 2856).
# Narrower than the band it replaces (200 wide, was 430) and centred on
# the measured value, so this is a tightening, not a widening.
BASE_TRIS_MIN = 2760
BASE_TRIS_MAX = 2960
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
GAP_MAX = 0.008
LIFT_Z = 0.05
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 360
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
METAL_FACES_MIN = 24
WOOD_FACES_MIN = 800

# Z-fighting: two separate bodies landing on one plane. Cross-shell, with
# hay-bale's constants (copied, not imported).
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
ZFIGHT_PAIRS_MAX = 0
# Named supports: a two-wheel cart's AABB zmin is grounded by whichever
# tyre happens to be lowest. Each tyre carries its own floor contact.
SUPPORT_ZMIN_EPS = 1e-4
# Mirrored members: the two wheels are the same part reflected in Y.
WHEEL_MIRROR_EPS = 5e-5
# Falsifier magnitudes, each sized to trip its own budget and nothing
# earlier: the wheel moves stay inside BBOX_TOL so the AABB gate cannot
# steal the failure.
SINK_TYRE_SEAT = 0.009
FLOAT_WHEEL_Z = 0.003
SKEW_WHEEL_Y = 0.006

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


def add_ring(bm, loc, r_mid, radial_t, width, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    """Flat-sided ring with a box cross-section (felloe / tyre profile).

    Manifold: outer tread, inner surface, and two side annuli, all quads.
    Built in the XY plane, width along Z, then rotated/translated.
    """
    r_in = r_mid - radial_t
    r_out = r_mid + radial_t
    hw = width / 2.0
    rings = []
    for i in range(segments):
        u = i * (2.0 * math.pi / segments)
        cu = math.cos(u)
        su = math.sin(u)
        rings.append(
            [
                bm.verts.new((r_in * cu, r_in * su, -hw)),
                bm.verts.new((r_out * cu, r_out * su, -hw)),
                bm.verts.new((r_out * cu, r_out * su, hw)),
                bm.verts.new((r_in * cu, r_in * su, hw)),
            ]
        )
    for i in range(segments):
        i2 = (i + 1) % segments
        a = rings[i]
        b = rings[i2]
        for quad in (
            (a[1], b[1], b[2], a[2]),
            (a[3], b[3], b[0], a[0]),
            (a[2], b[2], b[3], a[3]),
            (a[0], b[0], b[1], a[1]),
        ):
            face = bm.faces.new(quad)
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


def add_wheel(bm, loc, wood, metal):
    wood.extend(
        add_ring(
            bm, loc, RIM_MAJOR, RIM_RADIAL, RIM_W, WHEEL_SEGMENTS, WOOD_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
    )
    # Hooped, not pasted on: inner radius is RIM_OUTER - TYRE_SEAT so the
    # band bites into the felloe, and the tread still lands at
    # RIM_OUTER + TYRE_T so the tyre stays the ground contact.
    tyre_in = RIM_OUTER - TYRE_SEAT
    tyre_out = RIM_OUTER + TYRE_T
    metal.extend(
        add_ring(
            bm, loc, 0.5 * (tyre_in + tyre_out), 0.5 * (tyre_out - tyre_in),
            TYRE_W, WHEEL_SEGMENTS, METAL_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
    )
    wood.extend(
        add_cyl(
            bm,
            loc,
            HUB_R,
            HUB_W,
            12,
            WOOD_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
    )
    # Spokes root inside the hub and embed into the felloe ring — no
    # floating ends hidden by the hub band.
    inner = HUB_R * 0.4
    outer = RIM_MAJOR - RIM_RADIAL + 0.008
    mid_r = 0.5 * (inner + outer)
    slen = outer - inner
    for i in range(N_SPOKES):
        a = i * (2.0 * math.pi / N_SPOKES)
        dx = math.cos(a)
        dz = math.sin(a)
        cx = loc[0] + dx * mid_r
        cy = loc[1]
        cz = loc[2] + dz * mid_r
        wood.extend(
            add_box(
                bm,
                (cx, cy, cz),
                (slen, SPOKE_T * 0.85, SPOKE_T),
                WOOD_IDX,
                euler=(0.0, -a, 0.0),
            )
        )
    metal.extend(
        add_cyl(
            bm,
            loc,
            HUB_R + 0.010,
            0.016,
            12,
            METAL_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
    )
    metal.extend(
        add_cyl(
            bm,
            (loc[0], loc[1] + (HUB_W * 0.55 if loc[1] > 0 else -HUB_W * 0.55), loc[2]),
            0.022,
            0.018,
            10,
            METAL_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
    )


def build_cart_mesh(name, bevel_offset, bevel_segments):
    bm = bmesh.new()
    try:
        body = []
        wood_wheels = []
        metal = []
        axle_z = RIM_MAJOR
        # The bed rides on the axle through a bolster: axle top -> bolster ->
        # bed bottom. Never let the axle interpenetrate the slats.
        bed_z = axle_z + AXLE_R + BOLSTER_H + BED_T / 2.0
        bed_bottom = bed_z - BED_T / 2.0
        bed_cx = 0.06

        add_wheel(bm, (AXLE_X, TRACK / 2.0, axle_z), wood_wheels, metal)
        add_wheel(bm, (AXLE_X, -TRACK / 2.0, axle_z), wood_wheels, metal)

        metal.extend(
            add_cyl(
                bm,
                (AXLE_X, 0.0, axle_z),
                AXLE_R,
                TRACK + 0.06,
                10,
                METAL_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )

        slat_w = BED_W / N_SLATS
        y0 = -BED_W / 2.0 + slat_w / 2.0
        for i in range(N_SLATS):
            y = y0 + i * slat_w
            body.extend(
                add_box(
                    bm,
                    (bed_cx, y, bed_z),
                    (BED_L, slat_w * 0.88, BED_T),
                    WOOD_IDX,
                )
            )
        # Side walls and the front board finish flush at WALL_H; the back
        # board is a deliberately lower tailgate.
        for ysign in (-1.0, 1.0):
            body.extend(
                add_box(
                    bm,
                    (bed_cx, ysign * (BED_W / 2.0 + WALL_T / 2.0), bed_z + WALL_H / 2.0),
                    (BED_L * 0.98, WALL_T, WALL_H),
                    WOOD_IDX,
                )
            )
        body.extend(
            add_box(
                bm,
                (bed_cx + BED_L / 2.0 - WALL_T / 2.0, 0.0, bed_z + WALL_H / 2.0),
                (WALL_T, BED_W + WALL_T * 2.0, WALL_H),
                WOOD_IDX,
            )
        )
        body.extend(
            add_box(
                bm,
                (bed_cx - BED_L / 2.0 + WALL_T / 2.0, 0.0, bed_z + TAILGATE_H / 2.0),
                (WALL_T, BED_W + WALL_T * 2.0, TAILGATE_H),
                WOOD_IDX,
            )
        )
        # Bolsters: one sits on the axle, one forward; both carry the bed.
        for xj in (AXLE_X, bed_cx + BED_L * 0.28):
            body.extend(
                add_box(
                    bm,
                    (xj, 0.0, axle_z + AXLE_R + BOLSTER_H / 2.0),
                    (0.055, BED_W * 0.92, BOLSTER_H),
                    WOOD_IDX,
                )
            )

        # Shafts hang under the bed front: the back end embeds 6 mm into the
        # slat bottom and never pokes through the bed floor.
        shaft_x = bed_cx + BED_L / 2.0 + SHAFT_L / 2.0 - 0.04
        shaft_z = (
            bed_bottom + 0.006 - SHAFT_T / 2.0
            - math.sin(SHAFT_PITCH) * (SHAFT_L / 2.0)
        )
        for ysign in (-1.0, 1.0):
            body.extend(
                add_box(
                    bm,
                    (shaft_x, ysign * 0.12, shaft_z),
                    (SHAFT_L, SHAFT_T, SHAFT_T),
                    WOOD_IDX,
                    euler=(0.0, SHAFT_PITCH, 0.0),
                )
            )
            metal.extend(
                add_box(
                    bm,
                    (bed_cx + BED_L / 2.0 - 0.02, ysign * 0.12, bed_bottom - IRON_T / 2.0),
                    (0.05, 0.042, IRON_T),
                    METAL_IDX,
                )
            )

        # Tie-down plates sit on top of the bed floor, fully inboard of the
        # walls — visible, not buried inside the slats.
        for sx, sy in (
            (bed_cx - BED_L / 2.0 + 0.055, -BED_W / 2.0 + 0.055),
            (bed_cx - BED_L / 2.0 + 0.055, BED_W / 2.0 - 0.055),
            (bed_cx + BED_L / 2.0 - 0.055, -BED_W / 2.0 + 0.055),
            (bed_cx + BED_L / 2.0 - 0.055, BED_W / 2.0 - 0.055),
        ):
            metal.extend(
                add_box(
                    bm,
                    (sx, sy, bed_z + BED_T / 2.0 + IRON_T / 2.0),
                    (0.055, 0.055, IRON_T),
                    METAL_IDX,
                )
            )

        if bevel_offset > 0.0:
            edges = list({e for v in body for e in v.link_edges})
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


def shell_groups(me):
    """Vertex-index shells by edge connectivity (union-find), biggest first."""
    parent = list(range(len(me.vertices)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in me.edges:
        ra, rb = find(int(e.vertices[0])), find(int(e.vertices[1]))
        if ra != rb:
            parent[rb] = ra
    groups = {}
    for i in range(len(me.vertices)):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: -len(g))


def shell_box(me, idxs):
    co = [me.vertices[i].co for i in idxs]
    return {
        "xmin": min(c.x for c in co), "xmax": max(c.x for c in co),
        "ymin": min(c.y for c in co), "ymax": max(c.y for c in co),
        "zmin": min(c.z for c in co), "zmax": max(c.z for c in co),
    }


def coplanar_zfight_pairs(me, groups):
    """Coplanar face pairs from *different shells* — the z-fighting budget.

    Cross-shell, not merely share-no-vertex: two quads two steps apart on
    one flat cap share no vertex and are coplanar by construction, and
    counting those makes the budget unsatisfiable rather than meaningful.
    Z-fighting is two separate bodies landing on one plane, which is
    exactly a cross-shell pair. Combinatorics and constants copied from
    showcase/hay-bale (do not import across pieces).
    """
    owner = {}
    for si, comp in enumerate(groups):
        for vi in comp:
            owner[vi] = si
    faces = [(p.normal.copy(), p.center.copy(), owner.get(p.vertices[0], -1))
             for p in me.polygons]
    hits = 0
    for i in range(len(faces)):
        ni, ci, si = faces[i]
        for j in range(i + 1, len(faces)):
            nj, cj, sj = faces[j]
            if si == sj:
                continue
            if (ci - cj).length > COPLANAR_CENTRE_MAX:
                continue
            if abs(abs(ni.dot(nj)) - 1.0) > COPLANAR_NORMAL_EPS:
                continue
            if abs(ni.dot(cj - ci)) > COPLANAR_PLANE_EPS:
                continue
            hits += 1
    return hits


def wheel_shells(me, groups):
    """(rim, tyre) shell index pairs for each wheel, keyed by track side.

    Identified from the generated mesh by geometry — a shell centred on the
    axle line whose YZ extent is a full disc — never from a construction
    constant. The tyre is the metal-indexed member of the pair.
    """
    metal = set()
    for p in me.polygons:
        if p.material_index == METAL_IDX:
            metal.add(int(p.vertices[0]))
    found = {}
    for si, g in enumerate(groups):
        b = shell_box(me, g)
        dx = b["xmax"] - b["xmin"]
        dz = b["zmax"] - b["zmin"]
        if dx < 0.4 or abs(dx - dz) > 0.02:
            continue
        side = 1 if 0.5 * (b["ymin"] + b["ymax"]) > 0 else -1
        kind = "tyre" if any(i in metal for i in g) else "rim"
        found.setdefault(side, {})[kind] = si
    return found


def tyre_seat_depths(me, groups, rim_si, tyre_si, segments):
    """Per-station interference between the tyre's inner ring and the felloe.

    Banded and per angular station, not one global figure: a single number
    passes while one arc of the hoop visibly gaps. Both radii are recomputed
    from the generated vertices, so nothing here restates a constant.
    """
    axis_y = 0.5 * (shell_box(me, groups[tyre_si])["ymin"]
                    + shell_box(me, groups[tyre_si])["ymax"])
    rb = shell_box(me, groups[rim_si])
    cx = 0.5 * (rb["xmin"] + rb["xmax"])
    cz = 0.5 * (rb["zmin"] + rb["zmax"])

    def bins(idxs):
        out = {}
        for i in idxs:
            co = me.vertices[i].co
            ang = math.atan2(co.z - cz, co.x - cx)
            k = int(round(ang / (2.0 * math.pi / segments))) % segments
            out.setdefault(k, []).append(
                math.hypot(co.x - cx, co.z - cz))
        return out

    rim_bins = bins(groups[rim_si])
    tyre_bins = bins(groups[tyre_si])
    depths = []
    for k in sorted(set(rim_bins) & set(tyre_bins)):
        rim_out = max(rim_bins[k])
        tyre_in = min(tyre_bins[k])
        depths.append(rim_out - tyre_in)
    return depths, axis_y


def _wheel_centre(me, groups, rim_si):
    b = shell_box(me, groups[rim_si])
    return 0.5 * (b["xmin"] + b["xmax"]), 0.5 * (b["zmin"] + b["zmax"])


def break_tyre_seat(me, seat):
    """Falsifier surgery: re-radius each tyre's inner ring to `seat` deep.

    seat=0.0 puts the tyre's inner cylinder on the felloe's tread plane,
    which is the construction bug this piece was rebuilt to remove.
    """
    groups = shell_groups(me)
    for parts in wheel_shells(me, groups).values():
        cx, cz = _wheel_centre(me, groups, parts["rim"])
        idxs = groups[parts["tyre"]]
        radii = [math.hypot(me.vertices[i].co.x - cx,
                            me.vertices[i].co.z - cz) for i in idxs]
        split = 0.5 * (min(radii) + max(radii))
        for i, r in zip(idxs, radii):
            if r >= split:
                continue
            co = me.vertices[i].co
            scale = (RIM_OUTER - seat) / r
            co.x = cx + (co.x - cx) * scale
            co.z = cz + (co.z - cz) * scale
    me.update()


def move_one_wheel(me, delta):
    """Falsifier surgery: translate the +Y wheel only (rim, tyre, spokes).

    Everything whose vertices lie on the +Y side of the axle centreline and
    within the wheel's radius, so the assembly moves as one body and the
    opposite wheel still grounds the AABB.
    """
    groups = shell_groups(me)
    parts = wheel_shells(me, groups).get(1)
    if parts is None:
        return
    b = shell_box(me, groups[parts["tyre"]])
    cx, cz = _wheel_centre(me, groups, parts["rim"])
    y_lo, y_hi = b["ymin"] - 0.02, b["ymax"] + 0.02
    r_max = 0.5 * (b["xmax"] - b["xmin"]) + 1e-4
    for v in me.vertices:
        if not (y_lo <= v.co.y <= y_hi):
            continue
        if math.hypot(v.co.x - cx, v.co.z - cz) > r_max:
            continue
        v.co.x += delta[0]
        v.co.y += delta[1]
        v.co.z += delta[2]
    me.update()


def min_mat_distance(me, ia, ib):
    """Closest surface distance between two material islands via BVH.

    Vert-vert distance is the wrong metric for thin parts: a face interior
    can touch while its corner verts sit a radius apart.
    """
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
        for src in list(bm_a.verts) + list(bm_a.faces):
            co = src.co if hasattr(src, "co") else src.calc_center_median()
            hit = tree.find_nearest(co)
            if hit[0] is None:
                continue
            best = min(best, hit[3])
        return best
    finally:
        bm_a.free()
        bm_b.free()


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
    img = bpy.data.images.new("CartNrm", size, size, alpha=True, float_buffer=False)
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


def check(skip_decimate, lift_z=False, flush_tyre=False, sink_tyre=False,
          float_wheel=False, skew_wheel=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_cart_mesh("CartLow", bevel_offset=0.005, bevel_segments=2)
    high = build_cart_mesh("CartHigh", bevel_offset=0.005, bevel_segments=4)
    wood = principled(
        "CartWood", (0.42, 0.22, 0.08, 1.0), 0.0, 0.58,
        noise_scale=7.0, wear=(0.26, 0.12, 0.04, 1.0),
    )
    # Wrought iron, not black plastic. At (0.13, 0.32) the tyre rendered as
    # a flat black band with no sheen — darker and glossier than every
    # sibling piece's iron (hitching-post 0.16/0.48, wooden-ladder
    # 0.18/0.48). Raised to sit inside that calibration range, and the wear
    # colour lifted off near-black so the noise actually varies the surface.
    metal = principled(
        "CartIron", (0.20, 0.195, 0.185, 1.0), 1.0, 0.50,
        noise_scale=5.0, wear=(0.11, 0.105, 0.10, 1.0),
    )
    assign_slots(low, wood, metal)
    assign_slots(high, wood, metal)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
    if flush_tyre:
        break_tyre_seat(low.data, 0.0)
    if sink_tyre:
        break_tyre_seat(low.data, SINK_TYRE_SEAT)
    if float_wheel:
        move_one_wheel(low.data, (0.0, 0.0, FLOAT_WHEEL_Z))
    if skew_wheel:
        move_one_wheel(low.data, (0.0, SKEW_WHEEL_Y, 0.0))

    if low.data is None or len(low.data.polygons) < 6:
        return fail("cart mesh did not build", 3), None, None, None, None, None

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
        return fail("cart has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "CartLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "CartLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_cart_mesh("CartColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "CartCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_cart_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender sets TMPDIR from its own preference, which resolves to the
    # working directory on a stock portable build — so gettempdir() is the
    # repo root under CI and every run left a .glb behind. The budget only
    # needs the byte count, so drop the file once it is measured.
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

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
    hyg = hygiene_audit(low.data)
    gap_mw = min_mat_distance(low.data, METAL_IDX, WOOD_IDX)
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} euler={hyg['euler']}"
    )
    print(f"measured gap_metal_wood={gap_mw:.5f}")

    groups = shell_groups(low.data)
    zfight = coplanar_zfight_pairs(low.data, groups)
    wheels = wheel_shells(low.data, groups)
    support_zmins = {}
    seats = []
    for side, parts in sorted(wheels.items()):
        tb = shell_box(low.data, groups[parts["tyre"]])
        support_zmins["+Y" if side > 0 else "-Y"] = round(tb["zmin"], 6)
        depths, _ = tyre_seat_depths(
            low.data, groups, parts["rim"], parts["tyre"], WHEEL_SEGMENTS
        )
        seats.extend(depths)
    support_worst = max((abs(z) for z in support_zmins.values()), default=1e9)
    seat_min = min(seats) if seats else -1.0
    seat_max = max(seats) if seats else 1e9
    seat_n = len(seats)
    # Mirror: the two wheels are one part reflected in Y, so their rim
    # centres must match in X and Z and be opposite in Y.
    wheel_mirror = 1e9
    if len(wheels) == 2:
        boxes = {}
        for side, parts in wheels.items():
            b = shell_box(low.data, groups[parts["rim"]])
            boxes[side] = (
                0.5 * (b["xmin"] + b["xmax"]),
                0.5 * (b["ymin"] + b["ymax"]),
                0.5 * (b["zmin"] + b["zmax"]),
                b["xmax"] - b["xmin"],
                b["zmax"] - b["zmin"],
            )
        a, b2 = boxes[1], boxes[-1]
        wheel_mirror = max(
            abs(a[0] - b2[0]), abs(a[1] + b2[1]), abs(a[2] - b2[2]),
            abs(a[3] - b2[3]), abs(a[4] - b2[4]),
        )
    print(
        f"measured zfight_pairs={zfight} shells={len(groups)} "
        f"support_zmin={support_zmins} "
        f"tyre_seat=[{seat_min:.5f},{seat_max:.5f}] over {seat_n} stations "
        f"wheel_mirror={wheel_mirror*1000:.5f}mm"
    )

    if len(wheels) != 2 or any(len(p) != 2 for p in wheels.values()):
        return fail(
            f"expected 2 wheels of (rim, tyre) shells, found {wheels}",
            3,
        ), None, None, None, None, None
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
        or hyg["zero_area"]
        or hyg["doubles"]
        or hyg["ngons"]
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']}",
            15,
        ), None, None, None, None, None
    if zfight > ZFIGHT_PAIRS_MAX:
        return fail(
            f"coplanar cross-shell face pairs {zfight} > {ZFIGHT_PAIRS_MAX} "
            "(--flush-tyre is the designed fail: a tyre whose inner radius "
            "equals the felloe's outer radius puts both on one plane)",
            15,
        ), None, None, None, None, None
    if abs(bb[2]) > ZMIN_EPS:
        return fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ), None, None, None, None, None
    if support_worst > SUPPORT_ZMIN_EPS:
        return fail(
            f"named support zmin {support_worst:.6f} > {SUPPORT_ZMIN_EPS} "
            f"per-tyre zmin={support_zmins} "
            "(--float-wheel is the designed fail: one tyre off the floor "
            "while the other still grounds the AABB)",
            16,
        ), None, None, None, None, None
    if gap_mw > GAP_MAX:
        return fail(
            f"metal-wood gap {gap_mw:.5f} > {GAP_MAX} "
            "(tyres, hubs, straps, and plates must touch the wood they mount to)",
            17,
        ), None, None, None, None, None
    if seat_min < TYRE_SEAT_MIN or seat_max > TYRE_SEAT_MAX:
        return fail(
            f"tyre seat depth band [{seat_min:.5f}, {seat_max:.5f}] outside "
            f"[{TYRE_SEAT_MIN}, {TYRE_SEAT_MAX}] over {seat_n} stations "
            "(--sink-tyre is the designed fail: the hoop swallowed by the "
            "felloe reads as one body, not a tyre)",
            18,
        ), None, None, None, None, None
    if wheel_mirror > WHEEL_MIRROR_EPS:
        return fail(
            f"wheel mirror deviation {wheel_mirror*1000:.4f} mm > "
            f"{WHEEL_MIRROR_EPS*1000:.4f} mm "
            "(--skew-wheel is the designed fail: the two wheels are one part "
            "reflected in Y and must sit at matched X and Z)",
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

    low.rotation_euler.z = math.radians(-28.0)
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

    light("Key", (-3.4, -4.8, 5.4), 640.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (4.8, -3.4, 2.4), 46.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.2, 4.0, 3.8), 600.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.34, -1.62, 0.88)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.05, 0.0, 0.30)
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
        "--flush-tyre",
        action="store_true",
        help="falsification: tyre inner radius == felloe outer radius, so "
             "both land on one plane and the z-fight budget fails",
    )
    p.add_argument(
        "--sink-tyre",
        action="store_true",
        help="falsification: bury the tyre in the felloe so the seat band fails",
    )
    p.add_argument(
        "--float-wheel",
        action="store_true",
        help="falsification: lift one wheel off the floor while the other "
             "still grounds the AABB, so the named-support budget fails",
    )
    p.add_argument(
        "--skew-wheel",
        action="store_true",
        help="falsification: push one wheel out along the track so the "
             "wheel-mirror budget fails",
    )
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        flush_tyre=args.flush_tyre,
        sink_tyre=args.sink_tyre,
        float_wheel=args.float_wheel,
        skew_wheel=args.skew_wheel,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("cart OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
