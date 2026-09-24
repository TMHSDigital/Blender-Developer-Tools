"""Game-ready post-and-rail fence kit — a showcase piece, not an example.

Asserts budget conformance of a tiling timber fence section after
composing shipped pipeline pieces: bmesh construction, UVs, two
materials, high-to-low normal bake, LOD chain, convex collider,
Unity glTF export.

Posts, rails, kick, brace and iron bands share named stations
(``POST_XS``, ``RAIL_ZS``, ``SHOE_H``). The post stations come from the
tile: the outer face of the iron bands sits ``KIT_CLEAR`` inside the tile
edge, so adjacent copies meet without interpenetrating. Each band is one
mitred shell. The brace is a board with plumb-cut ends, face-nailed to
the middle rail and housed in both posts. Rails and kick tenon into the
post volume without sharing corner verts.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. ``--skip-decimate`` skips the LOD
DECIMATE stage so the LOD-ratio budget fails. Hygiene family 15–19:
``--stray-vert``, ``--lift-z`` / ``--short-shoes``, ``--short-brace``,
``--gap-rails``, ``--long-rails``. ``--float-brace`` fails the brace
bearing (20); ``--wide-tile`` fails the tile fit (21).

Construction is closed-form; plank tones use a seeded RNG. This piece
does not re-witness the modular-kit snap contract. DECIMATE COLLAPSE
triangle counts are not byte-identical across Blender versions — the LOD
gate is a ratio band, not an exact count.

    blender --background --python fence_kit.py --
    blender --background --python fence_kit.py -- --skip-decimate
    blender --background --python fence_kit.py -- --output fence.png
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

TILE = 1.60
POST_W = 0.110
POST_H = 1.14
CAP_H = 0.095
CAP_OVERHANG = 0.012
RAIL_Y = 0.055
RAIL_Z = 0.064
RAIL_ZS = (0.30, 0.58, 0.86)
KICK_Z = 0.125
KICK_Y = 0.040
BRACE_T = 0.042
IRON_T = 0.016
SHOE_H = 0.034
TENON = 0.005
COLLAR_BITE = 0.004
# The section tiles at TILE: the outer face of the iron bands, not the post
# centre, sits a named clearance inside the tile edge, so neighbouring
# copies meet band to band without interpenetrating or sharing a plane.
KIT_CLEAR = 0.002
TILE_FIT_TOL = 0.010
WIDE_TILE_CLEAR = -0.012
BAND_REACH = POST_W / 2.0 - COLLAR_BITE + IRON_T
HX = TILE / 2.0 - KIT_CLEAR - BAND_REACH
POST_XS = (-HX, HX)
RAIL_HALF = HX - POST_W * 0.5 + TENON
BRACE_D = 0.022
BRACE_BITE = 0.002
BRACE_TENON = 0.012
BRACE_CLEAR = 0.012
FLOAT_BRACE = 0.006
BRACE_POST_BITE_MIN = 0.004
BRACE_RAIL_BITE_MIN = 0.001
PLANK_TONE_JITTER = 0.28
TONE_SEED = 17
WOOD_GRAIN_SCALE = 30.0

BBOX_TOL = 0.015
OUTER_SIZE = (1.596, 0.134, 1.232)
BASE_TRIS_MIN = 850
BASE_TRIS_MAX = 1200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 180
BAKE_RES = 256
CAGE_EXTRUSION = 0.06
METAL_FACES_MIN = 48
WOOD_FACES_MIN = 48

WOOD_IDX = 0
METAL_IDX = 1

DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZMIN_EPS = 1e-4
ZFIGHT_EPS = 0.002
ZFIGHT_COS = 0.98
SHOE_COUNT = 2
SHOE_ZMIN_MAX = 0.002
BRACE_GAP_MAX = 0.008
RAIL_GAP_MAX = 0.008
SPAN_TOL = 0.04
LIFT_Z = 0.05
SHORT_SHOE = 0.08
SHORT_BRACE = 0.22
GAP_RAIL = 0.10
LONG_RAIL = 0.08


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


def add_collar(bm, px, z, half, t, h, mat_idx, closed=True):
    """One iron band around a post, mitred at the corners, one shell.

    Inner face a named bite inside the post, outer face proud of it. A U
    band (``closed=False``) leaves the span-facing side open for the rail
    and stops its arms a quarter-thickness inside the post's inner face,
    so no arm end lands on that face's plane. The first build was three or
    four separate plates with open slits at every corner.
    """
    a = half - COLLAR_BITE
    b = a + t
    s = 1.0 if px >= 0.0 else -1.0
    if closed:
        outer = [(b, b), (-b, b), (-b, -b), (b, -b)]
        inner = [(a, a), (-a, a), (-a, -a), (a, -a)]
    else:
        e = half - t * 0.25
        outer = [(-e, -b), (b, -b), (b, b), (-e, b)]
        inner = [(-e, -a), (a, -a), (a, a), (-e, a)]
    z0, z1 = z - h * 0.5, z + h * 0.5

    def ring(pts, zz):
        return [bm.verts.new((px + s * x, y, zz)) for x, y in pts]

    ob, ot = ring(outer, z0), ring(outer, z1)
    ib, it = ring(inner, z0), ring(inner, z1)
    n = len(outer)
    segs = range(n) if closed else range(n - 1)
    faces = []
    for i in segs:
        j = (i + 1) % n
        faces.append(bm.faces.new((ob[i], ob[j], ot[j], ot[i])))
        faces.append(bm.faces.new((ib[j], ib[i], it[i], it[j])))
        faces.append(bm.faces.new((ot[i], ot[j], it[j], it[i])))
        faces.append(bm.faces.new((ob[j], ob[i], ib[i], ib[j])))
    if not closed:
        for i in (0, n - 1):
            faces.append(bm.faces.new((ob[i], ib[i], it[i], ot[i])))
    for f in faces:
        f.material_index = mat_idx
    return ob + ot + ib + it


def add_brace(bm, x0, z0, x1, z1, y_back, depth, height, mat_idx):
    """A board brace between two posts, ends cut plumb.

    A box rotated onto the diagonal has ends square to its own axis: one
    corner buries itself in the post and the other stands off in the air.
    Cut plumb, both ends enter the post faces along their full height.
    """
    y_front = y_back - depth
    vs = []
    for x, zc in ((x0, z0), (x1, z1)):
        for y in (y_back, y_front):
            for dz in (-0.5, 0.5):
                vs.append(bm.verts.new((x, y, zc + dz * height)))
    # index: (end, y, z) -> end*4 + y*2 + z
    q = [
        (0, 1, 3, 2), (4, 6, 7, 5),       # plumb ends
        (0, 4, 5, 1), (2, 3, 7, 6),       # back / front faces
        (0, 2, 6, 4), (1, 5, 7, 3),       # underside / top
    ]
    for quad in q:
        bm.faces.new([vs[i] for i in quad]).material_index = mat_idx
    return vs


def rail_depth(i):
    return RAIL_Y * (1.0 + 0.10 * math.sin(i * 2.15 + 0.3))


def rail_height(i):
    return RAIL_Z * (1.0 + 0.06 * math.sin(i * 1.7 + 1.1))


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


def build_fence_mesh(
    name,
    bevel_offset,
    bevel_segments,
    short_brace=False,
    short_shoes=False,
    gap_rails=False,
    long_rails=False,
    float_brace=False,
    wide_tile=False,
):
    bm = bmesh.new()
    try:
        wood_verts = []
        half = POST_W * 0.5
        hx = TILE / 2.0 - (WIDE_TILE_CLEAR if wide_tile else KIT_CLEAR) - BAND_REACH
        post_xs = (-hx, hx)
        rail_half = hx - half + TENON
        if gap_rails:
            rail_half -= GAP_RAIL

        for px in post_xs:
            wood_verts.extend(
                add_box(
                    bm,
                    (px, 0.0, POST_H / 2.0),
                    (POST_W, POST_W, POST_H),
                    WOOD_IDX,
                )
            )

        for i, z in enumerate(RAIL_ZS):
            ry = rail_depth(i)
            rz = rail_height(i)
            wood_verts.extend(
                add_box(bm, (0.0, 0.0, z), (2.0 * rail_half, ry, rz), WOOD_IDX)
            )

        kick_z0 = SHOE_H - 0.003
        wood_verts.extend(
            add_box(
                bm,
                (0.0, 0.0, kick_z0 + KICK_Z / 2.0),
                (2.0 * rail_half, KICK_Y, KICK_Z),
                WOOD_IDX,
            )
        )

        if long_rails:
            wood_verts.extend(
                add_box(
                    bm,
                    (0.0, 0.0, (RAIL_ZS[0] + RAIL_ZS[1]) * 0.5),
                    (2.0 * (RAIL_HALF + LONG_RAIL), RAIL_Y, RAIL_Z),
                    WOOD_IDX,
                )
            )

        # The brace is a board face-nailed to the middle rail and housed in
        # both posts: it clears the bottom rail at the left post and the top
        # rail at the right one, and its back face bites the middle rail.
        # The first build ran post centre to post centre through the rail
        # bands, 6 mm into all three rails, with square-cut ends.
        x_a = post_xs[0] + half
        x_b = post_xs[1] - half
        h = BRACE_T
        for _ in range(3):
            z_a = RAIL_ZS[0] + rail_height(0) / 2.0 + BRACE_CLEAR + h / 2.0
            z_b = RAIL_ZS[-1] - rail_height(len(RAIL_ZS) - 1) / 2.0 - BRACE_CLEAR - h / 2.0
            slope = (z_b - z_a) / (x_b - x_a)
            h = BRACE_T * math.sqrt(1.0 + slope * slope)
        x0 = x_a - BRACE_TENON + (SHORT_BRACE if short_brace else 0.0)
        x1 = x_b + BRACE_TENON
        y_back = -rail_depth(1) / 2.0 + BRACE_BITE - (FLOAT_BRACE if float_brace else 0.0)
        wood_verts.extend(
            add_brace(
                bm,
                x0, z_a + slope * (x0 - x_a),
                x1, z_a + slope * (x1 - x_a),
                y_back, BRACE_D, h, WOOD_IDX,
            )
        )

        if bevel_offset > 0.0:
            # A set of BMEdges iterates in memory order; sort by index.
            bm.edges.index_update()
            edges = sorted({e for v in wood_verts for e in v.link_edges}, key=lambda e: e.index)
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

        cap_half = half + CAP_OVERHANG
        for px in post_xs:
            add_cone(
                bm,
                (px, 0.0, POST_H + CAP_H / 2.0 - 0.003),
                cap_half * math.sqrt(2.0),
                0.020,
                CAP_H,
                4,
                WOOD_IDX,
                euler=(0.0, 0.0, math.pi / 4.0),
            )

        shoe_lift = SHORT_SHOE if short_shoes else 0.0
        for px in post_xs:
            add_collar(
                bm, px, SHOE_H / 2.0 + shoe_lift, half, IRON_T, SHOE_H, METAL_IDX,
                closed=True,
            )
            for z in RAIL_ZS:
                add_collar(
                    bm, px, z, half, IRON_T, RAIL_Z * 1.25, METAL_IDX, closed=False
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
        tex.inputs["Detail"].default_value = 6.0
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

    Every post, rail, kick, brace and cap is its own shell, so each gets
    one tone and grain along its own long axis. Iron shells get a tone
    too; the iron shader ignores it.
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
    """Grain along each member (``GrainDir``), tone per member (``PlankTone``)."""
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


def fence_materials():
    """(wood, metal): shared by the check, the render and inspection.

    The first build was one flat brown on every member and satin iron
    (metallic 1.0, roughness 0.28) that read as chrome.
    """
    wood = wood_material("FenceWood")
    metal = principled(
        "FenceIron", (0.045, 0.046, 0.048, 1.0), 0.60, 0.55,
        noise_scale=18.0, wear=(0.13, 0.062, 0.028, 1.0),
    )
    return wood, metal


def assign_slots(obj, wood, metal):
    # Do not materials.clear() — that resets polygon material_index to 0
    # on this Blender, which would drop metal faces onto wood.
    mats = obj.data.materials
    wanted = (wood, metal)
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
        bm.verts.new((0.0, 0.0, POST_H * 0.55))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


def shell_bite(me, ga, gb):
    """Deepest vertex of shell ``ga`` inside closed shell ``gb`` (m); negative if none is."""
    bm_b = bmesh.new()
    try:
        bm_b.from_mesh(me)
        keep_b = set(gb)
        drop_b = [f for f in bm_b.faces if not all(v.index in keep_b for v in f.verts)]
        if drop_b:
            bmesh.ops.delete(bm_b, geom=drop_b, context="FACES")
        if not bm_b.faces:
            return -1e9
        bmesh.ops.recalc_face_normals(bm_b, faces=list(bm_b.faces))
        tree = BVHTree.FromBMesh(bm_b)
        best = -1e9
        for i in ga:
            co = me.vertices[i].co
            loc, nrm, _idx, dist = tree.find_nearest(co)
            if loc is None:
                continue
            depth = dist if (co - loc).dot(nrm) < 0.0 else -dist
            best = max(best, depth)
        return best
    finally:
        bm_b.free()


def joint_audit(me):
    groups = shells(me)
    posts = []
    rails = []
    braces = []
    shoes = []
    for g in groups:
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        mat = mat_of(me, g)
        if mat == WOOD_IDX and dz > 0.70 and dx < 0.18 and dy < 0.18:
            posts.append((g, a))
        if mat == WOOD_IDX and dx > TILE * 0.45 and dz < 0.18:
            rails.append((g, a))
        if mat == WOOD_IDX and dx > 0.40 and dz > 0.25 and dy < 0.12:
            braces.append((g, a))
        if mat == METAL_IDX and a[2] < 0.08 and dz < 0.08 and max(dx, dy) < 0.22:
            shoes.append((g, a))
    left = [a for _g, a in shoes if (a[0] + a[3]) * 0.5 < 0.0]
    right = [a for _g, a in shoes if (a[0] + a[3]) * 0.5 >= 0.0]
    shoe_n = (1 if left else 0) + (1 if right else 0)
    shoe_z = 99.0
    if shoes:
        shoe_z = min(a[2] for _g, a in shoes)
    brace_gap = 99.0
    if braces and posts:
        per_post = [
            min(shell_bvh_gap(me, b[0], p[0]) for b in braces) for p in posts
        ]
        brace_gap = max(per_post)
    rail_gap = 99.0
    if rails and posts:
        rail_gap = min(
            shell_bvh_gap(me, r[0], p[0]) for r in rails for p in posts
        )
    span_x = 0.0
    if rails:
        xs = [v for _g, a in rails for v in (a[0], a[3])]
        span_x = max(xs) - min(xs)
    # The brace is housed in both posts (deepest brace vertex inside each
    # post) and bears on the middle rail. Neither has a vertex where they
    # cross mid-span, so the bearing is the brace's back plane measured
    # against the rail's front plane, both read off the mesh, and only
    # counted where their heights overlap.
    post_bites = [shell_bite(me, b[0], p[0]) for b in braces for p in posts]
    brace_post_bite = min(post_bites) if post_bites else -1.0
    brace_rail_bite = -1.0
    if braces and rails:
        # The middle rail is the one centred on its station, whatever its
        # length, so a falsifier that moves the posts still finds it.
        mid = min(rails, key=lambda r: abs(0.5 * (r[1][2] + r[1][5]) - RAIL_ZS[1]))[1]
        brace_rail_bite = min(
            (b[1][4] - mid[1]) if (b[1][2] < mid[5] and b[1][5] > mid[2]) else -1.0
            for b in braces
        )
    return {
        "brace_post_bite": brace_post_bite,
        "brace_rail_bite": brace_rail_bite,
        "posts": len(posts),
        "rails": len(rails),
        "braces": len(braces),
        "shoes": shoe_n,
        "shoe_z": shoe_z,
        "brace_gap": brace_gap,
        "rail_gap": rail_gap,
        "span_x": span_x,
    }


def setup_bake_image(obj, target_mat, size=BAKE_RES):
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("FenceNrm", size, size, alpha=True, float_buffer=False)
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
    short_brace=False,
    short_shoes=False,
    gap_rails=False,
    long_rails=False,
    float_brace=False,
    wide_tile=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    kw = dict(
        short_brace=short_brace,
        short_shoes=short_shoes,
        gap_rails=gap_rails,
        long_rails=long_rails,
        float_brace=float_brace,
        wide_tile=wide_tile,
    )
    low = build_fence_mesh("FenceLow", bevel_offset=0.006, bevel_segments=2, **kw)
    high = build_fence_mesh("FenceHigh", bevel_offset=0.006, bevel_segments=4, **kw)
    paint_planks(low.data)
    paint_planks(high.data)
    wood, metal = fence_materials()
    assign_slots(low, wood, metal)
    assign_slots(high, wood, metal)

    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("fence mesh did not build", 3), None, None, None, None, None

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
        return fail("fence has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "FenceLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "FenceLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_fence_mesh(
        "FenceColSrc", bevel_offset=0.0, bevel_segments=1, **kw
    )
    collider = convex_hull_collider(collider_src, "FenceCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_fence_kit_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    if os.path.isfile(export_path):
        # Measured; do not leave a .glb per run in the temp directory.
        os.remove(export_path)

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
        f"measured posts={jnt['posts']} rails={jnt['rails']} "
        f"braces={jnt['braces']} shoes={jnt['shoes']} "
        f"shoe_z={jnt['shoe_z']:.5f} brace_gap={jnt['brace_gap']:.5f} "
        f"rail_gap={jnt['rail_gap']:.5f} span_x={jnt['span_x']:.4f}"
    )
    print(
        f"measured brace_post_bite={jnt['brace_post_bite']:.5f} "
        f"brace_rail_bite={jnt['brace_rail_bite']:.5f} tile={TILE} size_x={size_x:.4f}"
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
        bb[2] > ZMIN_EPS
        or jnt["shoes"] != SHOE_COUNT
        or jnt["shoe_z"] > SHOE_ZMIN_MAX
    ):
        return fail(
            f"grounded zmin={bb[2]:.5f} shoes={jnt['shoes']} "
            f"shoe_z={jnt['shoe_z']:.5f}",
            16,
        ), None, None, None, None, None
    if jnt["braces"] < 1 or jnt["posts"] < 2 or jnt["brace_gap"] > BRACE_GAP_MAX:
        return fail(
            f"brace gap {jnt['brace_gap']:.5f} braces={jnt['braces']} "
            f"posts={jnt['posts']}",
            17,
        ), None, None, None, None, None
    if jnt["rails"] < 3 or jnt["rail_gap"] > RAIL_GAP_MAX:
        return fail(
            f"rail gap {jnt['rail_gap']:.5f} rails={jnt['rails']}",
            18,
        ), None, None, None, None, None
    if abs(jnt["span_x"] - 2.0 * RAIL_HALF) > SPAN_TOL:
        return fail(
            f"rail span {jnt['span_x']:.4f} off {2.0 * RAIL_HALF}",
            19,
        ), None, None, None, None, None
    if (
        jnt["brace_post_bite"] < BRACE_POST_BITE_MIN
        or jnt["brace_rail_bite"] < BRACE_RAIL_BITE_MIN
    ):
        return fail(
            f"brace housing {jnt['brace_post_bite']:.5f} < {BRACE_POST_BITE_MIN} "
            f"or rail bearing {jnt['brace_rail_bite']:.5f} < {BRACE_RAIL_BITE_MIN}",
            20,
        ), None, None, None, None, None
    if not (TILE - TILE_FIT_TOL <= size_x <= TILE):
        return fail(
            f"section width {size_x:.4f} does not fit the {TILE} m tile "
            f"(band {TILE - TILE_FIT_TOL:.3f}-{TILE})",
            21,
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

    # Level on the floor: an X tilt sinks one face of the shoes.
    low.rotation_euler.z = math.radians(-16.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
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

    light("Key", (-3.6, -5.0, 5.8), 680.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.6, 2.6), 48.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.4, 4.2, 4.1), 640.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.50, -3.46, 1.95)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.58)
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
    p.add_argument("--short-shoes", action="store_true")
    p.add_argument("--short-brace", action="store_true")
    p.add_argument("--gap-rails", action="store_true")
    p.add_argument("--long-rails", action="store_true")
    p.add_argument("--float-brace", action="store_true")
    p.add_argument("--wide-tile", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_brace=args.short_brace,
        short_shoes=args.short_shoes,
        gap_rails=args.gap_rails,
        long_rails=args.long_rails,
        float_brace=args.float_brace,
        wide_tile=args.wide_tile,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("fence-kit OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
