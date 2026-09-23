"""Game-ready treasure chest — a showcase piece, not an example.

Asserts budget conformance of a procedural slatted chest after composing
shipped pipeline pieces: bmesh construction, UVs, two materials, high-to-low
normal bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-legs`` named foot
supports, ``--float-hinge`` lid-hinge joint-fit, ``--narrow-bands``
band-wall seat, ``--lift-lid-bands`` lid bands on the vault.

Construction is closed-form; the only RNG is plank tone, seeded with
``TONE_SEED``. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python treasure_chest.py --
    blender --background --python treasure_chest.py -- --skip-decimate
    blender --background --python treasure_chest.py -- --output chest.png
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

# A small iron-bound chest: 0.74 × 0.46 m plan, ~0.37 m to the rim,
# shallow barrel-vault lid. The old piece was a crate of overlay boxes
# with a flat sandwich lid.
OUTER_W = 0.74
OUTER_D = 0.46
CAVITY_H = 0.28
WALL = 0.028
BOTTOM = 0.026
FOOT_H = 0.042
FOOT_S = 0.068
FOOT_NEST = 0.012
LID_T = 0.028
N_FRONT = 5
N_SIDE = 4
N_LID = 5
BAND_W = 0.042
BAND_T = 0.010
VAULT_R = 0.50
HINGE_R = 0.011
LID_ANGLE = math.radians(-38.0)
BRACKET = 0.050
IRON_T = 0.012
BBOX_TOL = 0.015
BODY_W = OUTER_W
BODY_D = OUTER_D
BODY_W_TOL = 0.04
BODY_D_TOL = 0.04
OUTER_SIZE = (0.764, 0.524, 0.696)

BASE_TRIS_MIN = 3600
BASE_TRIS_MAX = 4500
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 200
BAKE_RES = 256
CAGE_EXTRUSION = 0.06
METAL_FACES_MIN = 80
WOOD_FACES_MIN = 200
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.999
LIFT_Z = 0.05
FOOT_Z_MAX = 1e-3
HINGE_JOIN = 0.020
BAND_SEAT = 0.008

WOOD_IDX = 0
METAL_IDX = 1

# Lid bands are arc slabs on the lid's own vault: inner radius a named bite
# inside the lid's outer surface, outer radius BAND_T beyond that, over
# the lid's full angular span with the lid's own segment count.
LID_SEGS = 10
LID_BAND_BITE = 0.002
LID_BAND_RTOL = 1e-4
N_LID_BANDS = 3
PLANK_TONE_JITTER = 0.28
TONE_SEED = 43
LID_BAND_LIFT = 0.005


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
    return list(verts)


def add_arc_slab(bm, cz, a0, a1, r_in, r_out, x0, x1, n, mat_idx):
    """Solid barrel-vault slab along X. Inner/outer arcs, two X stations."""
    def mk(x, r, t):
        return bm.verts.new((x, r * math.sin(t), cz + r * math.cos(t)))

    rin, rout, lin, lout = [], [], [], []
    for i in range(n + 1):
        t = a0 + (a1 - a0) * (i / float(n))
        rin.append(mk(x0, r_in, t))
        rout.append(mk(x0, r_out, t))
        lin.append(mk(x1, r_in, t))
        lout.append(mk(x1, r_out, t))
    verts = rin + rout + lin + lout

    def face(vs):
        f = bm.faces.new(vs)
        f.material_index = mat_idx

    for i in range(n):
        face((rin[i], lin[i], lin[i + 1], rin[i + 1]))
        face((rout[i], rout[i + 1], lout[i + 1], lout[i]))
        face((rin[i], rin[i + 1], rout[i + 1], rout[i]))
        face((lin[i], lout[i], lout[i + 1], lin[i + 1]))
    face((rin[0], rout[0], lout[0], lin[0]))
    face((rin[-1], lin[-1], lout[-1], rout[-1]))
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


def build_chest_mesh(
    name, bevel_offset, bevel_segments,
    short_legs=False, float_hinge=False, narrow_bands=False,
    lift_lid_bands=False,
):
    bm = bmesh.new()
    try:
        wood = []
        metal = []
        lid_wood = []
        lid_metal = []
        hx = OUTER_W / 2.0
        hy = OUTER_D / 2.0
        body_top = FOOT_H + BOTTOM + CAVITY_H
        wall_h = CAVITY_H
        wall_z = FOOT_H + BOTTOM + wall_h / 2.0
        foot_z0 = 0.05 if short_legs else 0.0

        if short_legs:
            metal.extend(
                add_box(bm, (0.0, 0.0, 0.004), (0.04, 0.04, 0.008), METAL_IDX)
            )

        for sxn in (-1.0, 1.0):
            for syn in (-1.0, 1.0):
                wood.extend(
                    add_box(
                        bm,
                        (
                            sxn * (hx - FOOT_S / 2.0 - 0.010),
                            syn * (hy - FOOT_S / 2.0 - 0.010),
                            foot_z0 + (FOOT_H + FOOT_NEST) / 2.0,
                        ),
                        (FOOT_S, FOOT_S, FOOT_H + FOOT_NEST),
                        WOOD_IDX,
                    )
                )

        wood.extend(
            add_box(
                bm,
                (0.0, 0.0, FOOT_H + BOTTOM / 2.0),
                (OUTER_W, OUTER_D, BOTTOM),
                WOOD_IDX,
            )
        )

        pitch = OUTER_W / N_FRONT
        overlap = 0.006
        for i in range(N_FRONT):
            jw = 0.004 * math.sin(i * 1.7 + 0.4)
            x = -hx + pitch * (i + 0.5)
            y_off = 0.0015 if (i % 2) else 0.0
            wood.extend(
                add_box(
                    bm,
                    (x, -hy + WALL / 2.0 + y_off, wall_z),
                    (pitch + overlap + jw, WALL, wall_h),
                    WOOD_IDX,
                )
            )
            wood.extend(
                add_box(
                    bm,
                    (x, hy - WALL / 2.0 - y_off, wall_z),
                    (pitch + overlap + jw, WALL, wall_h),
                    WOOD_IDX,
                )
            )

        pitch_z = wall_h / N_SIDE
        inner_d = OUTER_D - 2.0 * WALL + 0.010
        for sign in (-1.0, 1.0):
            for i in range(N_SIDE):
                jh = 0.003 * math.sin(i * 1.3 + sign)
                z = FOOT_H + BOTTOM + pitch_z * (i + 0.5)
                x_off = 0.0015 if (i % 2) else 0.0
                wood.extend(
                    add_box(
                        bm,
                        (sign * (hx - WALL / 2.0 - sign * x_off), 0.0, z),
                        (WALL, inner_d, pitch_z + 0.006 + jh),
                        WOOD_IDX,
                    )
                )

        rim_t = 0.012
        rim_z = body_top - rim_t / 2.0 - 0.002
        wood.extend(
            add_box(
                bm, (0.0, -hy + WALL + rim_t / 2.0, rim_z),
                (OUTER_W - 2.0 * WALL, rim_t, rim_t), WOOD_IDX,
            )
        )
        wood.extend(
            add_box(
                bm, (0.0, hy - WALL - rim_t / 2.0, rim_z),
                (OUTER_W - 2.0 * WALL, rim_t, rim_t), WOOD_IDX,
            )
        )
        wood.extend(
            add_box(
                bm, (-hx + WALL + rim_t / 2.0 + 0.003, 0.0, rim_z),
                (rim_t, OUTER_D - 2.0 * WALL - 2.0 * rim_t - 0.012, rim_t), WOOD_IDX,
            )
        )
        wood.extend(
            add_box(
                bm, (hx - WALL - rim_t / 2.0 - 0.003, 0.0, rim_z),
                (rim_t, OUTER_D - 2.0 * WALL - 2.0 * rim_t - 0.012, rim_t), WOOD_IDX,
            )
        )

        band_t = 0.004 if narrow_bands else BAND_T
        band_y_off = 0.022 if narrow_bands else 0.0
        band_xs = (-OUTER_W * 0.32, 0.0, OUTER_W * 0.32)
        for bx in band_xs:
            metal.extend(
                add_box(
                    bm,
                    (
                        bx,
                        -hy - band_t / 2.0 - band_y_off,
                        FOOT_H + (wall_h + BOTTOM) / 2.0,
                    ),
                    (BAND_W, band_t, wall_h + BOTTOM + band_t),
                    METAL_IDX,
                )
            )
            metal.extend(
                add_box(
                    bm,
                    (
                        bx,
                        hy + band_t / 2.0 + band_y_off,
                        FOOT_H + (wall_h + BOTTOM) / 2.0,
                    ),
                    (BAND_W, band_t, wall_h + BOTTOM + band_t),
                    METAL_IDX,
                )
            )
            metal.extend(
                add_box(
                    bm,
                    (bx, 0.0, FOOT_H - band_t / 2.0 + 0.002),
                    (BAND_W, OUTER_D - 0.008, band_t),
                    METAL_IDX,
                )
            )

        for sxn in (-1.0, 1.0):
            for syn in (-1.0, 1.0):
                metal.extend(
                    add_box(
                        bm,
                        (
                            sxn * (hx - BRACKET / 2.0 + 0.004),
                            syn * (hy + IRON_T / 2.0),
                            wall_z,
                        ),
                        (BRACKET - 0.010, IRON_T, wall_h - 0.020),
                        METAL_IDX,
                    )
                )
                metal.extend(
                    add_box(
                        bm,
                        (
                            sxn * (hx + IRON_T / 2.0),
                            syn * (hy - BRACKET / 2.0 + 0.004),
                            wall_z,
                        ),
                        (IRON_T, BRACKET - 0.010, wall_h - 0.020),
                        METAL_IDX,
                    )
                )

        plate_t = 0.008
        metal.extend(
            add_box(
                bm,
                (0.0, -hy - BAND_T - plate_t / 2.0, FOOT_H + BOTTOM + CAVITY_H * 0.48),
                (0.11, plate_t, 0.12),
                METAL_IDX,
            )
        )
        st_y = -hy - BAND_T - plate_t - 0.006
        st_z = FOOT_H + BOTTOM + CAVITY_H * 0.58
        metal.extend(add_box(bm, (-0.012, st_y, st_z), (0.008, 0.014, 0.022), METAL_IDX))
        metal.extend(add_box(bm, (0.012, st_y, st_z), (0.008, 0.014, 0.022), METAL_IDX))
        metal.extend(add_box(bm, (0.0, st_y, st_z + 0.012), (0.032, 0.014, 0.008), METAL_IDX))

        cz = body_top - math.sqrt(max(VAULT_R * VAULT_R - hy * hy, 1e-6))
        a_front = math.atan2(-hy, body_top - cz)
        a_back = math.atan2(hy, body_top - cz)
        lid_wood.extend(
            add_arc_slab(
                bm, cz, a_front, a_back,
                VAULT_R, VAULT_R + LID_T,
                -hx + 0.008, hx - 0.008,
                LID_SEGS, WOOD_IDX,
            )
        )

        # Each lid band is one arc slab on the lid's vault. It used to be
        # eight boxes rotated about X by +t, but at angle t the arc's tangent
        # in (y, z) is (cos t, -sin t), which is a rotation of -t: every
        # segment sat 2t off the tangent and the bands fanned out from the
        # lid like feathers. --lift-lid-bands floats them off the vault.
        r_band_in = VAULT_R + LID_T - LID_BAND_BITE
        for bx in band_xs:
            lift = LID_BAND_LIFT if lift_lid_bands else 0.0
            lid_metal.extend(
                add_arc_slab(
                    bm, cz, a_front, a_back, r_band_in + lift, r_band_in + lift + BAND_T,
                    bx - BAND_W / 2.0, bx + BAND_W / 2.0, LID_SEGS, METAL_IDX,
                )
            )
            # The cap turning down over the lid's front edge: rotated by -t
            # so its thickness lies along the edge's normal (the tangent).
            tmid = a_front
            y = r_band_in * math.sin(tmid)
            z = cz + r_band_in * math.cos(tmid)
            lid_metal.extend(
                add_box(
                    bm, (bx, y - 0.008, z - 0.006),
                    (BAND_W, BAND_T, LID_T + 0.016),
                    METAL_IDX, euler=(-tmid, 0.0, 0.0),
                )
            )

        tmid = a_front
        r_hasp = VAULT_R + LID_T + 0.006
        y = r_hasp * math.sin(tmid)
        z = cz + r_hasp * math.cos(tmid)
        lid_metal.extend(
            add_box(
                bm, (0.0, y - 0.018, z - 0.010),
                (0.038, 0.010, 0.055),
                METAL_IDX, euler=(-tmid, 0.0, 0.0),
            )
        )

        knuckle_verts = []
        for hx_i in (-OUTER_W * 0.28, OUTER_W * 0.28):
            metal.extend(
                add_box(
                    bm, (hx_i, hy + HINGE_R * 0.15, body_top),
                    (0.050, 0.022, 0.022), METAL_IDX,
                )
            )
            lid_metal.extend(
                add_box(
                    bm, (hx_i, hy - 0.016, body_top + 0.006),
                    (0.036, 0.040, 0.008), METAL_IDX,
                )
            )
            # Short lid knuckles over the barrels, not a spanning stile.
            # A full-width stile only has verts at the X ends, 8 cm from
            # the barrels, so a BVH join against it is a false gap.
            kv = add_box(
                bm, (hx_i, hy + 0.002, body_top + 0.012),
                (0.070, 0.028, 0.016), WOOD_IDX,
            )
            lid_wood.extend(kv)
            knuckle_verts.extend(kv)

        hinge = Vector((0.0, hy, body_top))
        rot = Euler((LID_ANGLE, 0.0, 0.0)).to_matrix()
        for v in lid_wood + lid_metal:
            v.co = rot @ (v.co - hinge) + hinge
        if float_hinge:
            # Lift knuckles off the barrels without swinging the vault
            # past the declared AABB (a shifted rotation pivot did).
            for v in knuckle_verts:
                v.co.z += 0.08

        bevel_verts = wood + knuckle_verts
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
            for v in bevel_verts:
                if not v.is_valid:
                    continue
                for f in v.link_faces:
                    f.material_index = WOOD_IDX
        for v in metal + lid_metal:
            if not v.is_valid:
                continue
            for f in v.link_faces:
                f.material_index = METAL_IDX

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
    paint_planks(me)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


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
    """Per-shell ``PlankTone`` and ``GrainDir`` face attributes for the wood shader."""
    tone = [0.5] * len(me.polygons)
    grain = [(1.0, 0.0, 0.0)] * len(me.polygons)
    owner = {}
    rng = random.Random(TONE_SEED)
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        d = _long_axis(pts) if len(pts) > 2 else Vector((1.0, 0.0, 0.0))
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
    """Grain along each board (``GrainDir``), tone per board (``PlankTone``)."""
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
    noise.inputs["Scale"].default_value = 30.0
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


def chest_materials():
    """(wood, iron): shared by the check, the render and inspection."""
    wood = wood_material("ChestWood")
    metal = principled(
        "ChestMetal", (0.17, 0.165, 0.155, 1.0), 0.80, 0.46,
        noise_scale=18.0, wear=(0.20, 0.085, 0.032, 1.0),
    )
    return wood, metal


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
    idxs = poly.vertices
    if len(idxs) < 3:
        return 0.0
    v0 = me.vertices[idxs[0]].co
    area = 0.0
    for i in range(1, len(idxs) - 1):
        vs = (me.vertices[idxs[i]].co, me.vertices[idxs[i + 1]].co)
        area += (vs[0] - v0).cross(vs[1] - v0).length * 0.5
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
    feet = []
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if a[5] < 0.10 and dx < 0.12 and dy < 0.12 and dz > 0.03:
            feet.append(a)
    foot_z = min((a[2] for a in feet), default=99.0)
    return {"feet": len(feet), "foot_z": foot_z}


def body_audit(me):
    groups = shells(me)
    best = None
    best_area = -1.0
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy = a[3] - a[0], a[4] - a[1]
        if dx > 0.50 and dy > 0.30 and a[2] < 0.12:
            area = dx * dy
            if area > best_area:
                best_area = area
                best = a
    if best is None:
        return {"w": 0.0, "d": 0.0}
    return {"w": best[3] - best[0], "d": best[4] - best[1]}


def hinge_join(me):
    """Gap from lid knuckles to the hinge barrels.

    Barrels are compact metal at the back rim. Knuckles are compact wood
    at the same station. Lock-plate staples, lid-band caps, and the
    hasp must not enter this set — they sit on the front of the chest.
    """
    groups = shells(me)
    hinges = []
    lid_wood = []
    for g in groups:
        a = shell_aabb(me, g)
        m = mat_of(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        back_rim = a[1] > 0.15 and a[2] > 0.30
        if (
            m == METAL_IDX and back_rim
            and 0.03 < dx < 0.08 and 0.015 < dy < 0.040 and 0.015 < dz < 0.040
        ):
            hinges.append(g)
        if (
            m == WOOD_IDX and back_rim
            and 0.04 < dx < 0.12 and dy < 0.05 and dz < 0.04
        ):
            lid_wood.append(g)
    if not hinges or not lid_wood:
        return 99.0
    bm_h = bmesh.new()
    try:
        bm_h.from_mesh(me)
        keep = set()
        for g in hinges:
            keep.update(g)
        drop = [
            f for f in bm_h.faces
            if not all(v.index in keep for v in f.verts)
        ]
        if drop:
            bmesh.ops.delete(bm_h, geom=drop, context="FACES")
        if not bm_h.faces:
            return 99.0
        tree = BVHTree.FromBMesh(bm_h)
        best = 99.0
        for g in lid_wood:
            for i in g:
                hit = tree.find_nearest(me.vertices[i].co)
                if hit[0] is None:
                    continue
                best = min(best, hit[3])
        return best
    finally:
        bm_h.free()


def band_wall_gap(me):
    """Worst gap from a vertical iron band to wood.

    Overlap counts as 0. ``--narrow-bands`` floats the straps off the
    slats so this goes positive.
    """
    groups = shells(me)
    bands = []
    for g in groups:
        if mat_of(me, g) != METAL_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if dz > 0.15 and dx < 0.10 and dy < 0.08:
            bands.append(g)
    if not bands:
        return 99.0
    bm_wood = bmesh.new()
    try:
        bm_wood.from_mesh(me)
        drop = [f for f in bm_wood.faces if f.material_index != WOOD_IDX]
        if drop:
            bmesh.ops.delete(bm_wood, geom=drop, context="FACES")
        if not bm_wood.faces:
            return 99.0
        tree_wood = BVHTree.FromBMesh(bm_wood)
        worst = 0.0
        for g in bands:
            bm_s = bmesh.new()
            try:
                bm_s.from_mesh(me)
                member = set(g)
                drop_s = [
                    f for f in bm_s.faces
                    if not all(v.index in member for v in f.verts)
                ]
                if drop_s:
                    bmesh.ops.delete(bm_s, geom=drop_s, context="FACES")
                if not bm_s.faces:
                    worst = max(worst, 99.0)
                    continue
                tree_s = BVHTree.FromBMesh(bm_s)
                if tree_wood.overlap(tree_s):
                    continue
                best = 99.0
                for i in g:
                    hit = tree_wood.find_nearest(me.vertices[i].co)
                    if hit[0] is None:
                        continue
                    best = min(best, hit[3])
                if best > worst:
                    worst = best
            finally:
                bm_s.free()
        return worst
    finally:
        bm_wood.free()


def lid_band_audit(me):
    """Lid bands: how many span the vault, and how true they sit on it.

    Un-rotates every vertex about the hinge by -LID_ANGLE, back into the
    frame the lid was built in, and takes each iron shell's radius from the
    vault axis. A lid band is an iron shell spanning at least 60% of the
    lid's arc; for those, every vertex radius must lie between the band's
    inner and outer radius. The feathered segments never span the arc, so
    they are not bands at all.
    """
    hy = OUTER_D / 2.0
    body_top = FOOT_H + BOTTOM + CAVITY_H
    cz = body_top - math.sqrt(max(VAULT_R * VAULT_R - hy * hy, 1e-6))
    a_front = math.atan2(-hy, body_top - cz)
    a_back = math.atan2(hy, body_top - cz)
    hinge = Vector((0.0, hy, body_top))
    unrot = Euler((-LID_ANGLE, 0.0, 0.0)).to_matrix()
    r_lo = VAULT_R + LID_T - LID_BAND_BITE
    r_hi = r_lo + BAND_T
    # The builder re-centres the whole mesh on its AABB after swinging the
    # lid, so the hinge is no longer where it was built. The body is
    # symmetric about its construction centre: its own Y-centre is the shift.
    # The feet only: everything else low on the body includes the hasp,
    # which hangs from the lid down the front and is not symmetric.
    # Measured from the mesh's own lowest point, so a falsifier that lifts
    # the whole mesh still finds the feet.
    z0 = min(v.co.z for v in me.vertices)
    body_ys = [v.co.y for v in me.vertices if v.co.z < z0 + FOOT_H * 0.8]
    hinge = hinge + Vector((0.0, 0.5 * (min(body_ys) + max(body_ys)), 0.0))
    cz_shift = hinge.y - hy
    n = 0
    worst = 0.0
    for g in shells(me):
        if mat_of(me, g) != METAL_IDX:
            continue
        pts = [unrot @ (me.vertices[i].co - hinge) + hinge for i in g]
        # Lid iron only: above the body, around the vault's own radius.
        if min(p.z for p in pts) < body_top - 0.01:
            continue
        mean_r = sum(math.hypot(p.y, p.z - cz) for p in pts) / len(pts)
        if not (VAULT_R < mean_r < VAULT_R + LID_T + 0.05):
            continue
        pts = [Vector((p.x, p.y - cz_shift, p.z)) for p in pts]
        angs = [math.atan2(p.y, p.z - cz) for p in pts]
        if max(angs) - min(angs) < 0.6 * (a_back - a_front):
            continue
        n += 1
        for p in pts:
            r = math.hypot(p.y, p.z - cz)
            worst = max(worst, r_lo - r, r - r_hi)
    return {"bands": n, "worst": max(worst, 0.0)}


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, 0.40))
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
    img = bpy.data.images.new("ChestNrm", size, size, alpha=True, float_buffer=False)
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
    skip_decimate, lift_z=False, stray_vert=False,
    short_legs=False, float_hinge=False, narrow_bands=False,
    lift_lid_bands=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        short_legs=short_legs, float_hinge=float_hinge, narrow_bands=narrow_bands,
        lift_lid_bands=lift_lid_bands,
    )
    low = build_chest_mesh("ChestLow", 0.003, 2, **flags)
    high = build_chest_mesh("ChestHigh", 0.003, 4, **flags)
    wood, metal = chest_materials()
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
        return fail("chest mesh did not build", 3), None, None, None, None, None

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
        return fail("chest has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "ChestLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "ChestLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_chest_mesh("ChestColSrc", 0.0, 1, **flags)
    collider = convex_hull_collider(collider_src, "ChestCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_treasure_chest_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender points TMPDIR at its own temp preference, which on a portable
    # build is the working directory, so the export must not outlive this.
    if os.path.isfile(export_path):
        os.remove(export_path)

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    sup = support_audit(low.data)
    body = body_audit(low.data)
    hj = hinge_join(low.data)
    bg = band_wall_gap(low.data)
    lb = lid_band_audit(low.data)
    print(f"measured lid_bands={lb['bands']} lid_band_worst={lb['worst']:.6f}")

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
        f"measured supports feet={sup['feet']} foot_z={sup['foot_z']:.5f} "
        f"body_w={body['w']:.4f} body_d={body['d']:.4f} "
        f"hinge_join={hj:.5f} band_gap={bg:.5f}"
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
        hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"]
        or hyg["zero_area"] or hyg["doubles"] or hyg["ngons"] or zf
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}",
            15,
        ), None, None, None, None, None
    if abs(bb[2]) > ZMIN_EPS:
        return fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ), None, None, None, None, None
    if sup["feet"] < 4 or sup["foot_z"] > FOOT_Z_MAX:
        return fail(
            f"foot supports {sup['feet']} foot_z={sup['foot_z']:.5f} "
            "(--short-legs is the designed fail)",
            16,
        ), None, None, None, None, None
    if hj > HINGE_JOIN:
        return fail(
            f"lid-hinge gap {hj:.5f} > {HINGE_JOIN} "
            "(--float-hinge is the designed fail)",
            17,
        ), None, None, None, None, None
    if bg > BAND_SEAT:
        return fail(
            f"band-wall gap {bg:.5f} > {BAND_SEAT} "
            "(--narrow-bands is the designed fail)",
            18,
        ), None, None, None, None, None
    if lb["bands"] != N_LID_BANDS or lb["worst"] > LID_BAND_RTOL:
        return fail(
            f"lid bands: {lb['bands']} of {N_LID_BANDS} span the vault, worst "
            f"radial excursion {lb['worst']:.6f} > {LID_BAND_RTOL} "
            "(--lift-lid-bands is the designed fail)",
            18,
        ), None, None, None, None, None
    if abs(body["w"] - BODY_W) > BODY_W_TOL:
        return fail(
            f"body width {body['w']:.4f} off {BODY_W}",
            19,
        ), None, None, None, None, None
    if abs(body["d"] - BODY_D) > BODY_D_TOL:
        return fail(
            f"body depth {body['d']:.4f} off {BODY_D}",
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
    cam.location = (1.62, -2.22, 1.42)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.36)
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
    p.add_argument("--short-legs", action="store_true")
    p.add_argument("--float-hinge", action="store_true")
    p.add_argument("--narrow-bands", action="store_true")
    p.add_argument("--lift-lid-bands", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_legs=args.short_legs,
        float_hinge=args.float_hinge,
        narrow_bands=args.narrow_bands,
        lift_lid_bands=args.lift_lid_bands,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("treasure-chest OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
