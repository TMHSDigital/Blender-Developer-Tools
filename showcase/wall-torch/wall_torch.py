"""Game-ready wall torch sconce — a showcase piece, not an example.

Asserts budget conformance of a procedural wall-mounted torch after
composing shipped pipeline pieces: bmesh construction, UVs, five
materials, high-to-low normal bake, LOD chain, convex collider,
Unity glTF export.

The plaque back sits on the wall plane Y=0 with zmin at 0. The iron plate
is bolted to the face of the stones, a named bite into it. A level arm
runs from the plate into the wall of an open iron cup, whose mid-height
is the arm's height. The cup sits on the haft's axis, which leans out
from the wall; the haft stands on the cup floor and carries a pitch wrap,
and the flames stand upright from the wrap. Hygiene family 15–19:
``--stray-vert``, ``--lift-z``, ``--float-arm``, ``--float-plate``,
``--skinny-plaque``; ``--droop-arm`` (20), ``--sink-plate`` (21),
``--low-bake`` (22).

Construction is closed-form; stone tones use a seeded RNG. DECIMATE
COLLAPSE triangle counts are not byte-identical across Blender versions —
the LOD gate is a ratio band, not an exact count.

    blender --background --python wall_torch.py --
    blender --background --python wall_torch.py -- --skip-decimate
    blender --background --python wall_torch.py -- --output torch.png
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

WALL_W = 0.28
WALL_D = 0.070
WALL_H = 0.40
CORNICE_H = 0.028
GROUT = 0.007
NROWS = 4
STONE_D = 0.020
STONE_BITE = 0.004
PLATE_Z = 0.20
PLATE_R = 0.055
PLATE_T = 0.016
PLATE_BITE = 0.003
CUP_Y = 0.24
CUP_H = 0.052
CUP_R0 = 0.024
CUP_R1 = 0.050
CUP_T = 0.005
# Floor thicker than the wall so the haft's foot, the drip boss and the
# floor's two faces sit on four planes at least 2.5 mm apart.
FLOOR_T = 0.010
CUP_SEGS = 16
ARM_R = 0.011
HAFT_R = 0.016
HAFT_LEN = 0.20
HAFT_SEGS = 10
HAFT_TILT_DEG = 15.0
WRAP_H = 0.055
WRAP_R = 0.024
FLAME_SEAT = 0.012
FLAME_SEGS = 12
# (t along the flame's own axis, radius): a teardrop, widest low.
FLAME_PROFILE = (
    (0.0, 0.0), (0.0, 0.012), (0.018, 0.026), (0.045, 0.023),
    (0.080, 0.011), (0.112, 0.0),
)
DROOP_ARM = 0.02
ARM_LEVEL_DEG = 1.0
PLATE_PROUD_MIN = 0.008
PLATE_SEAT_MIN = 0.001
PLATE_SEAT_MAX = 0.005
MORTAR_TONE = 0.08
PLANK_TONE_JITTER = 0.26
TONE_SEED = 31
WOOD_GRAIN_SCALE = 34.0
LIFT_Z = 0.05
FLOAT_ARM = 0.55
FLOAT_PLATE = 0.08
SKINNY = 0.55

BBOX_TOL = 0.015
OUTER_SIZE = (0.304, 0.322, 0.485)
BASE_TRIS_MIN = 1800
BASE_TRIS_MAX = 2250
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 5
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 180
BAKE_RES = 1024
LOW_BAKE_RES = 256
TEXEL_MIN = 12.0
CAGE_EXTRUSION = 0.06
STONE_FACES_MIN = 24
METAL_FACES_MIN = 24
FLAME_FACES_MIN = 8
PITCH_FACES_MIN = 10

STONE_IDX = 0
METAL_IDX = 1
WOOD_IDX = 2
FLAME_IDX = 3
PITCH_IDX = 4

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


def lathe_axis(bm, base, axis, profile, segs, mat_idx):
    """Solid of revolution about ``axis`` from ``base``.

    ``profile`` is (t metres along the axis, radius); a radius of 0 is a
    single centre vertex, which closes the solid there with a fan.
    """
    base = Vector(base)
    axis = Vector(axis).normalized()
    side = axis.cross(Vector((1.0, 0.0, 0.0)))
    if side.length < 1e-6:
        side = axis.cross(Vector((0.0, 1.0, 0.0)))
    side.normalize()
    up = axis.cross(side).normalized()
    rings = []
    for t, r in profile:
        p = base + axis * t
        if r <= 1e-9:
            rings.append([bm.verts.new(p)])
            continue
        rings.append([
            bm.verts.new(p + (side * math.cos(2.0 * math.pi * k / segs)
                              + up * math.sin(2.0 * math.pi * k / segs)) * r)
            for k in range(segs)
        ])
    faces = []
    for a, b in zip(rings, rings[1:]):
        if len(a) == 1:
            for k in range(segs):
                faces.append(bm.faces.new((a[0], b[(k + 1) % segs], b[k])))
        elif len(b) == 1:
            for k in range(segs):
                faces.append(bm.faces.new((a[k], a[(k + 1) % segs], b[0])))
        else:
            for k in range(segs):
                k2 = (k + 1) % segs
                faces.append(bm.faces.new((a[k], a[k2], b[k2], b[k])))
    for f in faces:
        f.material_index = mat_idx
    return [v for ring in rings for v in ring]


def stone_face_y():
    """Front face of the facing stones: the plane a fixture is bolted to."""
    return WALL_D - STONE_BITE + STONE_D


def torch_axis(tilt_deg=HAFT_TILT_DEG):
    """Haft axis: leaning out from the wall (+Y) by the named tilt."""
    t = math.radians(tilt_deg)
    return Vector((0.0, math.sin(t), math.cos(t)))


def build_torch_mesh(
    name,
    bevel_offset,
    bevel_segments,
    float_arm=False,
    float_plate=False,
    skinny_plaque=False,
    droop_arm=False,
    sink_plate=False,
):
    bm = bmesh.new()
    try:
        plaque_w = WALL_W * SKINNY if skinny_plaque else WALL_W
        stone = []
        stone.extend(add_box(
            bm,
            (0.0, WALL_D / 2.0, WALL_H / 2.0),
            (plaque_w, WALL_D, WALL_H),
            STONE_IDX,
        ))
        stone.extend(add_box(
            bm,
            (0.0, WALL_D / 2.0 + 0.006, WALL_H + CORNICE_H / 2.0 - 0.004),
            (plaque_w + 0.024, WALL_D + 0.018, CORNICE_H),
            STONE_IDX,
        ))

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
                stone.extend(add_box(
                    bm,
                    (cx, face_y, zc),
                    (max(w, 0.04), STONE_D, course_h - 0.001),
                    STONE_IDX,
                ))
                x += w + GROUT

        if bevel_offset > 0.0:
            # Stone only, before any iron exists; sorted so the bevel lays
            # its faces down in the same order every run.
            bm.edges.index_update()
            edges = sorted({e for v in stone for e in v.link_edges}, key=lambda e: e.index)
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
                f.material_index = STONE_IDX

        # The plate is bolted to the stone face, a named bite into it. The
        # first build seated it on the backing slab, 4 mm behind the face of
        # the stones, so only its bolt heads showed.
        seat_face = WALL_D - 0.004 if sink_plate else stone_face_y() - PLATE_BITE
        plate_y = seat_face + PLATE_T / 2.0
        # The arm root stays at the seated plate, so floating the plate
        # moves only the plate.
        arm_root_y = plate_y
        if float_plate:
            plate_y += FLOAT_PLATE
        add_cone(
            bm, (0.0, plate_y, PLATE_Z), PLATE_R, PLATE_R, PLATE_T, 16,
            METAL_IDX, euler=(math.pi / 2.0, 0.0, 0.0),
        )
        for sx, sz in ((-0.032, 0.028), (0.032, 0.028), (-0.032, -0.028), (0.032, -0.028)):
            add_cone(
                bm, (sx, plate_y + PLATE_T / 2.0 + 0.004, PLATE_Z + sz),
                0.006, 0.0045, 0.010, 8, METAL_IDX, euler=(-math.pi / 2.0, 0.0, 0.0),
            )

        # The cup sits on the haft axis, which leans out from the wall. Its
        # station is where the level arm meets the cup's wall.
        axis = torch_axis()
        # The cup's mid-height is the arm's height, so a level arm meets it.
        cup_base = Vector((0.0, CUP_Y, PLATE_Z)) - axis * (CUP_H * 0.5)
        cup_prof = (
            (0.0, 0.0),
            (0.0, CUP_R0),
            (CUP_H, CUP_R1),
            (CUP_H, CUP_R1 - CUP_T),
            (FLOOR_T, CUP_R0 - CUP_T * 0.6),
            (FLOOR_T, 0.0),
        )
        lathe_axis(bm, cup_base, axis, cup_prof, CUP_SEGS, METAL_IDX)
        # A drip boss under the cup, biting its floor.
        lathe_axis(
            bm, cup_base - axis * 0.012, axis,
            ((0.0, 0.0), (0.0, 0.006), (0.006, 0.012),
             (0.012 + 0.25 * FLOOR_T, 0.012), (0.012 + 0.25 * FLOOR_T, 0.0)),
            CUP_SEGS, METAL_IDX,
        )

        # Level arm from inside the plate to inside the cup wall at mid-cup.
        mid = cup_base + axis * (CUP_H * 0.5)
        r_mid = 0.5 * (CUP_R0 + CUP_R1)
        arm_z = PLATE_Z
        plate_st = Vector((0.0, arm_root_y - PLATE_T * 0.25, arm_z))
        cup_st = Vector((0.0, mid.y - r_mid + CUP_T * 0.5, mid.z))
        if droop_arm:
            plate_st.z += DROOP_ARM
        arm_end = cup_st
        if float_arm:
            arm_end = plate_st + (cup_st - plate_st) * FLOAT_ARM
        add_cyl_between(bm, plate_st, arm_end, ARM_R, 10, METAL_IDX)

        # The haft stands on the cup floor and runs up the tilted axis.
        haft_base = cup_base + axis * (FLOOR_T * 0.5)
        lathe_axis(
            bm, haft_base, axis,
            ((0.0, 0.0), (0.0, HAFT_R * 0.92), (0.02, HAFT_R),
             (HAFT_LEN * 0.6, HAFT_R * 1.06), (HAFT_LEN, HAFT_R * 1.10), (HAFT_LEN, 0.0)),
            HAFT_SEGS, WOOD_IDX,
        )
        # Pitch-soaked wrap over the head, the haft end inside it.
        head = haft_base + axis * (HAFT_LEN - WRAP_H + 0.012)
        lathe_axis(
            bm, head, axis,
            ((0.0, 0.0), (0.0, HAFT_R * 1.12), (0.006, WRAP_R), (WRAP_H * 0.55, WRAP_R * 1.06),
             (WRAP_H - 0.006, WRAP_R * 0.96), (WRAP_H, WRAP_R * 0.70), (WRAP_H, 0.0)),
            HAFT_SEGS, PITCH_IDX,
        )
        top = head + axis * WRAP_H

        # Flames stand up, whatever the haft does: a teardrop and two licks,
        # each seated a named depth into the wrap.
        up = Vector((0.0, 0.0, 1.0))
        for off, lean, scale in (
            (Vector((0.0, 0.0, 0.0)), up, 1.0),
            (Vector((0.012, -0.006, 0.0)), Vector((0.25, -0.1, 1.0)), 0.62),
            (Vector((-0.011, 0.007, 0.0)), Vector((-0.22, 0.12, 1.0)), 0.55),
        ):
            base = top + off - up * FLAME_SEAT
            lathe_axis(
                bm, base, lean,
                tuple((t * scale, r * (0.6 + 0.4 * scale)) for t, r in FLAME_PROFILE),
                FLAME_SEGS, FLAME_IDX,
            )

        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z -= zmin
            if v.co.z < 0.0:
                v.co.z = 0.0

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
        # Turned iron, the haft, the wrap and the flame are smooth; dressed
        # stone keeps its chamfer facets. Fan caps stay flat.
        for poly in me.polygons:
            poly.use_smooth = (
                poly.material_index != STONE_IDX and len(poly.vertices) == 4
            ) or poly.material_index == FLAME_IDX
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
    """Per-shell ``PlankTone`` and ``GrainDir`` face attributes.

    Every facing stone and the haft are their own shells, so each gets one
    tone (and the haft grain along its own axis). The backing slab shows
    only in the joints, so it takes the mortar tone: the first build gave
    stone and joint one flat grey and the courses did not read.
    """
    tone = [0.5] * len(me.polygons)
    grain = [(0.0, 0.0, 1.0)] * len(me.polygons)
    owner = {}
    rng = random.Random(TONE_SEED)
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        d = _long_axis(pts) if len(pts) > 2 else Vector((0.0, 0.0, 1.0))
        t = 0.5 + rng.uniform(-PLANK_TONE_JITTER, PLANK_TONE_JITTER)
        a = shell_aabb(me, g)
        if mat_of(me, g) == STONE_IDX and a[5] - a[2] > 0.20 and a[3] - a[0] > 0.12:
            t = MORTAR_TONE
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
    """Grain along the haft (``GrainDir``), tone per piece (``PlankTone``)."""
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


def stone_material(name):
    """Isotropic mottling, fine speckle in roughness, a tone per stone."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_name = "PlankTone"
    shift = nt.nodes.new("ShaderNodeVectorMath")
    shift.operation = "ADD"
    nt.links.new(coord.outputs["Object"], shift.inputs[0])
    nt.links.new(tone.outputs["Fac"], shift.inputs[1])
    mottle = nt.nodes.new("ShaderNodeTexNoise")
    mottle.inputs["Scale"].default_value = 24.0
    mottle.inputs["Detail"].default_value = 8.0
    mottle.inputs["Roughness"].default_value = 0.6
    nt.links.new(shift.outputs["Vector"], mottle.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.32
    ramp.color_ramp.elements[0].color = (0.085, 0.080, 0.072, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.20, 0.188, 0.165, 1.0)
    nt.links.new(mottle.outputs["Fac"], ramp.inputs["Fac"])
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 1.3
    gain.inputs[2].default_value = 0.25
    nt.links.new(tone.outputs["Fac"], gain.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(ramp.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(gain.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    speck = nt.nodes.new("ShaderNodeTexNoise")
    speck.inputs["Scale"].default_value = 260.0
    nt.links.new(coord.outputs["Object"], speck.inputs["Vector"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.72
    rough.inputs["To Max"].default_value = 0.92
    nt.links.new(speck.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def torch_materials():
    """(stone, metal, wood, flame, pitch): shared by the check, the render and inspection.

    The first build was one flat grey for stone and joint alike, and iron at
    metallic 0.88, roughness 0.38 that read as polished.
    """
    stone = stone_material("TorchStone")
    metal = principled(
        "TorchIron", (0.050, 0.048, 0.046, 1.0), 0.65, 0.52,
        noise_scale=18.0, wear=(0.15, 0.070, 0.030, 1.0),
    )
    wood = wood_material("TorchWood")
    flame = principled(
        "TorchFlame",
        (1.0, 0.45, 0.10, 1.0),
        0.0,
        0.48,
        emission=3.2,
        emission_color=(1.0, 0.42, 0.08, 1.0),
    )
    pitch = principled(
        "TorchPitch", (0.030, 0.022, 0.016, 1.0), 0.0, 0.62,
        noise_scale=40.0, wear=(0.10, 0.060, 0.030, 1.0),
    )
    return stone, metal, wood, flame, pitch


def assign_slots(obj, stone, metal, wood, flame, pitch):
    mats = obj.data.materials
    wanted = (stone, metal, wood, flame, pitch)
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
        elif mat == METAL_IDX and dy > dx and dy > dz and dy > 0.06:
            arms.append((g, a))
    arm_gap = 1e9
    for ag, _ in arms:
        for cg, _ in cups:
            arm_gap = min(arm_gap, shell_bvh_gap(me, ag, cg))
    # The plate is bolted to the stone face, so its gap is measured to any
    # stone shell, not only the backing slab behind the stones.
    stones = [g for g in groups if mat_of(me, g) == STONE_IDX]
    plate_gap = 1e9
    for pg, _ in plates:
        for qg in stones:
            plate_gap = min(plate_gap, shell_bvh_gap(me, pg, qg))
    plaque_w = max((a[3] - a[0] for _, a in plaques), default=0.0)
    # Arm level: its long axis, from the shell's own vertices.
    arm_tilt = 90.0
    for ag, _ in arms:
        pts = [me.vertices[i].co.copy() for i in ag]
        d = _long_axis(pts)
        arm_tilt = min(arm_tilt, math.degrees(math.asin(min(1.0, abs(d.z)))))
    # Plate seat: the plate stands proud of the facing stones and its back
    # bites their face. Facing stones are the thin stone shells.
    faces = [a for g, a in ((g, shell_aabb(me, g)) for g in groups)
             if mat_of(me, g) == STONE_IDX and a[4] - a[1] < 0.03]
    stone_front = max((a[4] for a in faces), default=0.0)
    plate_proud = max((a[4] for _, a in plates), default=-1.0) - stone_front
    plate_seat = stone_front - min((a[1] for _, a in plates), default=1.0)
    return {
        "arm_tilt": arm_tilt,
        "facing": len(faces),
        "plate_proud": plate_proud,
        "plate_seat": plate_seat,
        "plaques": len(plaques),
        "plates": len(plates),
        "cups": len(cups),
        "arms": len(arms),
        "arm_gap": arm_gap if arms and cups else 1e9,
        "plate_gap": plate_gap if plates and plaques else 1e9,
        "plaque_w": plaque_w,
    }


def texel_audit(mesh, img):
    """Smallest UV cell, in baked texels along its longer side.

    Every face packs into its own UV cell, so a small image spreads a few
    texels over each face and the render's bilinear lookup reads the next
    cell's normals across the border: dark slivers on the hero.
    """
    uv = mesh.uv_layers.active
    if uv is None or img is None:
        return 0.0
    res = min(img.size[0], img.size[1])
    data = uv.data
    worst = 1e9
    for poly in mesh.polygons:
        us = [data[i].uv[0] for i in poly.loop_indices]
        vs = [data[i].uv[1] for i in poly.loop_indices]
        worst = min(worst, max(max(us) - min(us), max(vs) - min(vs)) * res)
    return worst


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
    droop_arm=False,
    sink_plate=False,
    low_bake=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    kw = dict(
        float_arm=float_arm,
        float_plate=float_plate,
        skinny_plaque=skinny_plaque,
        droop_arm=droop_arm,
        sink_plate=sink_plate,
    )
    low = build_torch_mesh("TorchLow", bevel_offset=0.004, bevel_segments=2, **kw)
    high = build_torch_mesh("TorchHigh", bevel_offset=0.004, bevel_segments=4, **kw)
    paint_planks(low.data)
    paint_planks(high.data)
    mats = torch_materials()
    stone = mats[0]
    assign_slots(low, *mats)
    assign_slots(high, *mats)

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

    img, tex = setup_bake_image(low, size=LOW_BAKE_RES if low_bake else BAKE_RES, target_mat=stone)
    if img is None:
        return fail("torch has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)
    texel = texel_audit(low.data, img)
    print(f"measured bake_res={img.size[0]} texel_min={texel:.2f}")

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
        f"measured plaques={jnt['plaques']} plates={jnt['plates']} "
        f"cups={jnt['cups']} arms={jnt['arms']} "
        f"arm_gap={jnt['arm_gap']:.5f} plate_gap={jnt['plate_gap']:.5f} "
        f"plaque_w={jnt['plaque_w']:.4f}"
    )
    print(
        f"measured arm_tilt={jnt['arm_tilt']:.3f}deg facing_stones={jnt['facing']} "
        f"plate_proud={jnt['plate_proud']:.5f} plate_seat={jnt['plate_seat']:.5f}"
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
    if idx_counts.get(PITCH_IDX, 0) < PITCH_FACES_MIN:
        return fail(
            f"pitch faces {idx_counts.get(PITCH_IDX, 0)} < {PITCH_FACES_MIN}",
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
    if jnt["arms"] != 1 or jnt["arm_tilt"] > ARM_LEVEL_DEG:
        return fail(
            f"arm tilt {jnt['arm_tilt']:.3f} deg > {ARM_LEVEL_DEG} arms={jnt['arms']}",
            20,
        ), None, None, None, None, None
    if (
        jnt["plate_proud"] < PLATE_PROUD_MIN
        or not (PLATE_SEAT_MIN <= jnt["plate_seat"] <= PLATE_SEAT_MAX)
    ):
        return fail(
            f"plate proud {jnt['plate_proud']:.5f} < {PLATE_PROUD_MIN} or seat "
            f"{jnt['plate_seat']:.5f} not in [{PLATE_SEAT_MIN}, {PLATE_SEAT_MAX}]",
            21,
        ), None, None, None, None, None
    if texel < TEXEL_MIN:
        return fail(
            f"bake texel density {texel:.2f} px per UV cell < {TEXEL_MIN} "
            "(--low-bake is the designed fail)",
            22,
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

    light("Key", (-3.6, -5.0, 5.4), 640.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.4, 2.4), 42.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.2, 4.0, 3.8), 380.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))
    light("FlameKick", (0.4, 1.2, 0.8), 90.0, 0.6, (1.0, 0.55, 0.22), (40, 0, 160))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 55.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-1.19, -1.45, 0.44)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.02, 0.07, 0.25)
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
    p.add_argument("--droop-arm", action="store_true")
    p.add_argument("--sink-plate", action="store_true")
    p.add_argument("--low-bake", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, stone, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_arm=args.float_arm,
        float_plate=args.float_plate,
        skinny_plaque=args.skinny_plaque,
        droop_arm=args.droop_arm,
        sink_plate=args.sink_plate,
        low_bake=args.low_bake,
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
