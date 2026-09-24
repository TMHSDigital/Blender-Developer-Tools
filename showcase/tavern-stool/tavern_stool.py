"""Game-ready tavern stool — a showcase piece, not an example.

Asserts budget conformance of a procedural turned-leg stool after composing
shipped pipeline pieces: bmesh construction, UVs, two materials, high-to-low
normal bake, LOD chain, convex collider, Unity glTF export.

Each foot is an iron ferrule sleeve on the leg's own axis, its inner wall a
named grip inside the leg, with its raked bottom rim buried in a level iron
tread. The leg ends inside the sleeve, above the tread. Front-back and side
stretchers sit at different heights so their tenons do not meet in the leg.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-legs`` named ferrule
supports, ``--float-stretchers`` stretcher joint-fit, ``--pipe-ferrule``
ferrule grip, ``--sink-legs`` the foot stack (20), ``--low-bake`` the bake
texel density (21).

Construction is closed-form; member tones use a seeded RNG. DECIMATE
COLLAPSE triangle counts are not byte-identical across Blender versions —
the LOD gate is a ratio band, not an exact count.

    blender --background --python tavern_stool.py --
    blender --background --python tavern_stool.py -- --skip-decimate
    blender --background --python tavern_stool.py -- --output stool.png
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

# A short tavern stool: ~34 cm seat, 47 cm to the rim, legs splayed so
# the feet land near the seat's shadow. The old piece was a 16-gon puck
# on four stacked cones clustered under the disc.
SEAT_R = 0.170
SEAT_T = 0.040
SEAT_Z = 0.470
SEAT_SEGS = 48
N_LEGS = 4
LEG_TOP_R = 0.128
LEG_BOT_R = 0.202
LEG_SEGS = 16
FERRULE_H = 0.022
FERRULE_T = 0.0045
FERRULE_SEGS = 16
STRETCH_T = 0.58
# Front-back and side stretchers at different heights, so their tenons do
# not meet inside the leg. The first build set all four at one height.
STRETCH_T2 = 0.68
STRETCH_R = 0.011
STRETCH_SEGS = 12
STRETCH_TENON = 0.012
SEAT_TENON = 0.018
BBOX_TOL = 0.015
BODY_DIA = 2.0 * SEAT_R
BODY_DIA_TOL = 0.02
BODY_H = SEAT_Z
BODY_H_TOL = 0.02
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.341, 0.341, 0.470)

BASE_TRIS_MIN = 2750
BASE_TRIS_MAX = 3350
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 640
BAKE_RES = 1024
LOW_BAKE_RES = 256
TEXEL_MIN = 12.0
CAGE_EXTRUSION = 0.01
METAL_FACES_MIN = 48
WOOD_FACES_MIN = 200
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.999
LIFT_Z = 0.05
FERRULE_Z_MAX = 1e-3
STRETCH_JOIN = 0.008
# The foot: an iron ferrule sleeve on the leg's own axis gripping the leg,
# seated in a level iron tread. The first build ended every leg 3 mm above
# an open vertical ring on the floor, with a 1 mm air gap around the foot.
TREAD_H = 0.012
TREAD_R = 0.027
TREAD_SEGS = 16
FERRULE_GRIP = 0.0012
SLEEVE_SINK = 0.006
LEG_CLEAR = 0.004
FERRULE_BITE_MIN = 0.0006
FERRULE_BITE_MAX = 0.0025
SINK_LEGS = 0.010
FOOT_ABOVE_MIN = 0.0005
FOOT_BURIED_MIN = 0.001
PLANK_TONE_JITTER = 0.24
TONE_SEED = 29
WOOD_GRAIN_SCALE = 30.0

WOOD_IDX = 0
METAL_IDX = 1

# Turned-leg profile: (t along the axis from seat tenon to ferrule, radius).
# One loft, not four stacked cones. t=0 is up in the seat.
LEG_PROFILE = (
    (0.00, 0.018),
    (0.08, 0.022),
    (0.20, 0.025),
    (0.36, 0.016),
    (0.52, 0.015),
    (0.60, 0.018),
    (0.78, 0.016),
    (0.92, 0.018),
    (1.00, 0.017),
)

# Seat, underside to dish. One lathe, not three stacked cylinders.
# (z above the underside, radius). r=0 is the dish centre.
SEAT_PROFILE = (
    (0.000, 0.122),
    (0.010, 0.138),
    (0.016, 0.158),
    (0.022, 0.168),
    (0.032, 0.170),
    (0.040, 0.164),
    (0.037, 0.095),
    (0.034, 0.000),
)


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


def _bridge_rings(bm, a, b, mat_idx):
    if len(a) == 1 and len(b) > 1:
        c = a[0]
        for k in range(len(b)):
            kn = (k + 1) % len(b)
            face = bm.faces.new((c, b[k], b[kn]))
            face.material_index = mat_idx
    elif len(b) == 1 and len(a) > 1:
        c = b[0]
        for k in range(len(a)):
            kn = (k + 1) % len(a)
            face = bm.faces.new((c, a[kn], a[k]))
            face.material_index = mat_idx
    else:
        segs = len(a)
        for k in range(segs):
            kn = (k + 1) % segs
            face = bm.faces.new((a[k], a[kn], b[kn], b[k]))
            face.material_index = mat_idx


def loft_rings(bm, rings, mat_idx, cap_start=True, cap_end=True, cyclic=False):
    """Loft a stack of rings. A ring of one vert is a centre cap."""
    verts = [v for ring in rings for v in ring]
    n = len(rings)
    for i in range(n - 1):
        _bridge_rings(bm, rings[i], rings[i + 1], mat_idx)
    if cyclic and n > 2:
        _bridge_rings(bm, rings[-1], rings[0], mat_idx)
    if cap_start and len(rings[0]) > 1:
        ring = rings[0]
        c = bm.verts.new(sum((v.co for v in ring), Vector((0, 0, 0))) / len(ring))
        verts.append(c)
        for k in range(len(ring)):
            kn = (k + 1) % len(ring)
            face = bm.faces.new((c, ring[kn], ring[k]))
            face.material_index = mat_idx
    if cap_end and len(rings[-1]) > 1:
        ring = rings[-1]
        c = bm.verts.new(sum((v.co for v in ring), Vector((0, 0, 0))) / len(ring))
        verts.append(c)
        for k in range(len(ring)):
            kn = (k + 1) % len(ring)
            face = bm.faces.new((c, ring[k], ring[kn]))
            face.material_index = mat_idx
    return verts


def lathe_z(bm, profile, segs, mat_idx, z0=0.0):
    rings = []
    for z, r in profile:
        if r <= 1e-8:
            rings.append([bm.verts.new((0.0, 0.0, z0 + z))])
            continue
        ring = []
        for i in range(segs):
            a = 2.0 * math.pi * i / segs
            ring.append(
                bm.verts.new((r * math.cos(a), r * math.sin(a), z0 + z))
            )
        rings.append(ring)
    # Profile already ends at r=0 (dish) or a ring. No extra caps.
    cap_start = len(rings[0]) > 1
    cap_end = len(rings[-1]) > 1
    return loft_rings(bm, rings, mat_idx, cap_start=cap_start, cap_end=cap_end)


def lathe_axis(bm, a, b, profile, segs, mat_idx, cap_start=True, cap_end=True):
    a = Vector(a)
    b = Vector(b)
    delta = b - a
    length = delta.length
    if length < 1e-8:
        return []
    tangent = delta.normalized()
    side = Vector((-tangent.y, tangent.x, 0.0))
    if side.length < 1e-6:
        side = Vector((1.0, 0.0, 0.0))
    else:
        side.normalize()
    up = tangent.cross(side).normalized()
    rings = []
    for t, radius in profile:
        p = a + tangent * (t * length)
        if radius <= 1e-8:
            rings.append([bm.verts.new(p)])
            continue
        ring = []
        for i in range(segs):
            ang = 2.0 * math.pi * i / segs
            ring.append(
                bm.verts.new(p + side * (radius * math.cos(ang)) + up * (radius * math.sin(ang)))
            )
        rings.append(ring)
    return loft_rings(
        bm, rings, mat_idx, cap_start=cap_start, cap_end=cap_end,
    )


def add_cup(bm, xy, z0, z1, r_in, r_out, segs, mat_idx):
    """Vertical ferrule cup: annulus walls, open on the top, planted at z0."""
    cx, cy = xy
    specs = (
        (z0, r_in),
        (z0, r_out),
        (z1, r_out),
        (z1, r_in),
    )
    rings = []
    for z, r in specs:
        ring = []
        for i in range(segs):
            a = 2.0 * math.pi * i / segs
            ring.append(
                bm.verts.new((cx + r * math.cos(a), cy + r * math.sin(a), z))
            )
        rings.append(ring)
    return loft_rings(
        bm, rings, mat_idx, cap_start=False, cap_end=False, cyclic=True,
    )


def add_pipe_torus(bm, xy, z, major, minor, mat_idx):
    """Falsifier: a metal torus planted at z that does not cup the foot."""
    n_major, n_minor = 12, 4
    cx, cy = xy
    rings = []
    for i in range(n_major):
        u = i * (2.0 * math.pi / n_major)
        ring = []
        for j in range(n_minor):
            v = j * (2.0 * math.pi / n_minor)
            px = cx + (major + minor * math.cos(v)) * math.cos(u)
            py = cy + (major + minor * math.cos(v)) * math.sin(u)
            pz = z + minor * (1.0 + math.sin(v))
            ring.append(bm.verts.new((px, py, pz)))
        rings.append(ring)
    verts = [v for ring in rings for v in ring]
    for i in range(n_major):
        i2 = (i + 1) % n_major
        for j in range(n_minor):
            j2 = (j + 1) % n_minor
            face = bm.faces.new(
                (rings[i][j], rings[i2][j], rings[i2][j2], rings[i][j2])
            )
            face.material_index = mat_idx
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


def _leg_ends(i):
    ang = math.pi / 4.0 + i * (math.pi * 2.0 / N_LEGS)
    c, s = math.cos(ang), math.sin(ang)
    seat_under = SEAT_Z - SEAT_T
    top = Vector((LEG_TOP_R * c, LEG_TOP_R * s, seat_under + SEAT_TENON))
    bot = Vector((LEG_BOT_R * c, LEG_BOT_R * s, TREAD_H + LEG_CLEAR))
    foot_xy = (LEG_BOT_R * c, LEG_BOT_R * s)
    return top, bot, foot_xy, ang


def _axis_frame(tangent):
    side = Vector((-tangent.y, tangent.x, 0.0))
    if side.length < 1e-6:
        side = Vector((1.0, 0.0, 0.0))
    else:
        side.normalize()
    return side, tangent.cross(side).normalized()


def add_sleeve(bm, a, b, r_in, r_out, segs, mat_idx):
    """Ferrule sleeve on an arbitrary axis: annulus walls, both ends ringed."""
    a, b = Vector(a), Vector(b)
    t = (b - a).normalized()
    side, up = _axis_frame(t)
    rings = []
    for p, r in ((a, r_in), (a, r_out), (b, r_out), (b, r_in)):
        ring = []
        for i in range(segs):
            ang = 2.0 * math.pi * i / segs
            ring.append(bm.verts.new(p + side * (r * math.cos(ang)) + up * (r * math.sin(ang))))
        rings.append(ring)
    return loft_rings(bm, rings, mat_idx, cap_start=False, cap_end=False, cyclic=True)


def add_tread(bm, xy, z0, h, r, segs, mat_idx):
    """Level iron tread under a raked leg: a chamfered puck from z0 up."""
    ch = min(0.002, h * 0.25)
    prof = ((z0, r - ch), (z0 + ch, r), (z0 + h - ch, r), (z0 + h, r - ch))
    rings = []
    for z, rr in prof:
        ring = []
        for i in range(segs):
            ang = 2.0 * math.pi * i / segs
            ring.append(bm.verts.new((xy[0] + rr * math.cos(ang), xy[1] + rr * math.sin(ang), z)))
        rings.append(ring)
    return loft_rings(bm, rings, mat_idx, cap_start=True, cap_end=True)


def axis_at_z(top, bot, z):
    """Point on the leg axis (extended past ``bot``) at height z."""
    return bot + (top - bot) * ((z - bot.z) / (top.z - bot.z))


def build_stool_mesh(
    name,
    short_legs=False,
    float_stretchers=False,
    pipe_ferrule=False,
    sink_legs=False,
):
    bm = bmesh.new()
    try:
        wood_faces = []
        metal_faces = []
        before = set(bm.faces)
        lathe_z(bm, SEAT_PROFILE, SEAT_SEGS, WOOD_IDX, z0=SEAT_Z - SEAT_T)
        wood_faces.extend(set(bm.faces) - before)

        ferrule_z0 = 0.05 if short_legs else 0.0
        if short_legs:
            before = set(bm.faces)
            geo = bmesh.ops.create_cube(bm, size=1.0)
            for v in geo["verts"]:
                v.co.x *= 0.024
                v.co.y *= 0.024
                v.co.z *= 0.006
                v.co.z += 0.003
            metal_faces.extend(set(bm.faces) - before)

        leg_pts = []
        for i in range(N_LEGS):
            top, bot, foot_xy, ang = _leg_ends(i)
            leg_pts.append((top, bot, foot_xy, ang))
            leg_bot = bot
            if sink_legs:
                # The leg end run down into the tread, still inside its sleeve.
                leg_bot = axis_at_z(top, bot, bot.z - SINK_LEGS)
            before = set(bm.faces)
            lathe_axis(bm, top, leg_bot, LEG_PROFILE, LEG_SEGS, WOOD_IDX)
            wood_faces.extend(set(bm.faces) - before)

            # Sleeve on the leg's own axis, its inner wall a named grip
            # inside the leg's end radius; its raked bottom rim buried in a
            # level tread under the axis. The tread is centred where the
            # axis crosses the tread's top face.
            r_foot = LEG_PROFILE[-1][1]
            r_in = r_foot - FERRULE_GRIP
            r_out = r_in + FERRULE_T
            s0 = axis_at_z(top, bot, TREAD_H - SLEEVE_SINK)
            s1 = s0 + (top - bot).normalized() * FERRULE_H
            tread_c = axis_at_z(top, bot, TREAD_H)
            before = set(bm.faces)
            lift = Vector((0.0, 0.0, ferrule_z0))
            if pipe_ferrule:
                # The sleeve replaced by a pipe ring on the tread that does
                # not grip the leg; the tread stays, so the envelope and the
                # triangle band do not steal the failure.
                add_pipe_torus(
                    bm, (tread_c.x, tread_c.y), ferrule_z0 + TREAD_H, 0.022, 0.004,
                    METAL_IDX,
                )
            else:
                add_sleeve(bm, s0 + lift, s1 + lift, r_in, r_out, FERRULE_SEGS, METAL_IDX)
            add_tread(
                bm, (tread_c.x, tread_c.y), ferrule_z0, TREAD_H, TREAD_R,
                TREAD_SEGS, METAL_IDX,
            )
            metal_faces.extend(set(bm.faces) - before)

        if not float_stretchers:
            for i in range(N_LEGS):
                a_top, a_bot, _, _ = leg_pts[i]
                b_top, b_bot, _, _ = leg_pts[(i + 1) % N_LEGS]
                st = STRETCH_T if i % 2 == 0 else STRETCH_T2
                a = a_top.lerp(a_bot, st)
                b = b_top.lerp(b_bot, st)
                d = (b - a).normalized()
                r_leg = 0.0
                for t, r in LEG_PROFILE:
                    if t >= st:
                        r_leg = r
                        break
                a_end = a + d * (r_leg - STRETCH_TENON)
                b_end = b - d * (r_leg - STRETCH_TENON)
                before = set(bm.faces)
                lathe_axis(
                    bm, a_end, b_end,
                    ((0.0, STRETCH_R), (1.0, STRETCH_R)),
                    STRETCH_SEGS, WOOD_IDX,
                )
                wood_faces.extend(set(bm.faces) - before)

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        wood_set = set(wood_faces)
        metal_set = set(metal_faces)
        for face in bm.faces:
            if face in metal_set:
                face.material_index = METAL_IDX
                face.smooth = True
            else:
                face.material_index = WOOD_IDX
                face.smooth = True
        for edge in bm.edges:
            edge.smooth = True
            if edge.is_manifold and len(edge.link_faces) == 2:
                if edge.calc_face_angle() > math.radians(40.0):
                    edge.smooth = False
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

    The seat, every leg and every stretcher is its own shell, so each gets
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


def stool_materials():
    """(wood, metal): shared by the check, the render and inspection.

    The first build was one flat brown on seat, legs and stretchers alike,
    and bright satin metal (0.50 grey, metallic 1.0, roughness 0.32) that
    read as chrome on the feet.
    """
    wood = wood_material("StoolWood")
    metal = principled(
        "StoolIron", (0.050, 0.050, 0.052, 1.0), 0.65, 0.50,
        noise_scale=18.0, wear=(0.14, 0.066, 0.030, 1.0),
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
    cups = []
    for g in groups:
        if mat_of(me, g) != METAL_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if a[5] < 0.08 and dx > 0.03 and dy > 0.03 and dz < 0.05:
            cups.append(a)
    cup_z = min((a[2] for a in cups), default=99.0)
    return {"cups": len(cups), "cup_z": cup_z}


def seat_audit(me):
    groups = shells(me)
    best = None
    best_area = -1.0
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        area = dx * dy
        if dz > 0.02 and area > best_area:
            best_area = area
            best = a
    if best is None:
        return {"dia": 0.0, "height": 0.0, "zmin": 99.0}
    dia = 0.5 * ((best[3] - best[0]) + (best[4] - best[1]))
    return {"dia": dia, "height": best[5], "zmin": best[2]}


def stretcher_join(me):
    """Worst gap from a stretcher shell to the nearest leg."""
    groups = shells(me)
    legs = []
    stretchers = []
    for g in groups:
        if mat_of(me, g) != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if dz > 0.20 and max(dx, dy) < 0.16:
            legs.append(g)
        elif dz < 0.035 and 0.10 < max(dx, dy) < 0.30:
            stretchers.append(g)
    if not legs or not stretchers:
        return 99.0
    bm_leg = bmesh.new()
    try:
        bm_leg.from_mesh(me)
        keep = set()
        for g in legs:
            keep.update(g)
        drop = [
            f for f in bm_leg.faces
            if not all(v.index in keep for v in f.verts)
        ]
        if drop:
            bmesh.ops.delete(bm_leg, geom=drop, context="FACES")
        if not bm_leg.faces:
            return 99.0
        tree = BVHTree.FromBMesh(bm_leg)
        worst = 0.0
        for g in stretchers:
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
                if tree.overlap(tree_s):
                    continue
                best = 99.0
                for i in g:
                    hit = tree.find_nearest(me.vertices[i].co)
                    if hit[0] is None:
                        continue
                    best = min(best, hit[3])
                if best > worst:
                    worst = best
            finally:
                bm_s.free()
        return worst
    finally:
        bm_leg.free()


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


def foot_audit(me):
    """Ferrule grip and foot stack, per leg.

    Sleeves are metal shells that rise above the tread; treads are the flat
    metal shells on the floor. Grip is measured radially about the leg's own
    axis (its principal axis, from its vertices): the leg's radius where the
    sleeve wraps it, less the sleeve's inner radius. A nearest-face signed
    distance misreads points in the sleeve's hollow as inside its wall.
    The stack asserts each leg ends above its tread's top and each sleeve's
    lowest point is buried below it.
    """
    groups = shells(me)
    legs, sleeves, treads = [], [], []
    for g in groups:
        a = shell_aabb(me, g)
        dz = a[5] - a[2]
        mat = mat_of(me, g)
        if mat == WOOD_IDX and dz > 0.20 and max(a[3] - a[0], a[4] - a[1]) < 0.16:
            legs.append((g, a))
        elif mat == METAL_IDX and a[5] < 0.08:
            (sleeves if a[5] > TREAD_H + 0.004 else treads).append((g, a))

    def near(a, pool):
        cx, cy = 0.5 * (a[0] + a[3]), 0.5 * (a[1] + a[4])
        return min(pool, key=lambda q: math.hypot(0.5 * (q[1][0] + q[1][3]) - cx,
                                                  0.5 * (q[1][1] + q[1][4]) - cy))

    grips, above, buried = [], [], []
    for g, a in legs:
        if not sleeves or not treads:
            break
        foot = [i for i in g if me.vertices[i].co.z < 0.08]
        fa = shell_aabb(me, foot) if foot else a
        sg, sa = near(fa, sleeves)
        tg, ta = near(fa, treads)
        pts = [me.vertices[i].co.copy() for i in g]
        c = sum(pts, Vector()) / len(pts)
        ax = _long_axis(pts)

        def radial(p):
            d = p - c
            return (d - ax * d.dot(ax)).length

        spts = [me.vertices[i].co.copy() for i in sg]
        s_lo = min((p - c).dot(ax) for p in spts)
        s_hi = max((p - c).dot(ax) for p in spts)
        wrapped = [p for p in pts if s_lo <= (p - c).dot(ax) <= s_hi]
        if not wrapped:
            grips.append(-1.0)
        else:
            grips.append(max(radial(p) for p in wrapped) - min(radial(p) for p in spts))
        above.append(a[2] - ta[5])
        buried.append(ta[5] - sa[2])
    return {
        "legs": len(legs),
        "sleeves": len(sleeves),
        "treads": len(treads),
        "grip": min(grips) if grips else -1.0,
        "grip_max": max(grips) if grips else -1.0,
        "above": min(above) if above else -1.0,
        "buried": min(buried) if buried else -1.0,
    }


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, SEAT_Z))
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
    img = bpy.data.images.new("StoolNrm", size, size, alpha=True, float_buffer=False)
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
    skip_decimate,
    lift_z=False,
    stray_vert=False,
    short_legs=False,
    float_stretchers=False,
    pipe_ferrule=False,
    sink_legs=False,
    low_bake=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        short_legs=short_legs,
        float_stretchers=float_stretchers,
        pipe_ferrule=pipe_ferrule,
        sink_legs=sink_legs,
    )
    low = build_stool_mesh("StoolLow", **flags)
    high = build_stool_mesh("StoolHigh", **flags)
    paint_planks(low.data)
    paint_planks(high.data)
    wood, metal = stool_materials()
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
        return fail("stool mesh did not build", 3), None, None, None, None, None

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

    img, tex = setup_bake_image(low, size=LOW_BAKE_RES if low_bake else BAKE_RES, target_mat=wood)
    if img is None:
        return fail("stool has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)
    texel = texel_audit(low.data, img)
    print(f"measured bake_res={img.size[0]} texel_min={texel:.2f}")

    lod1 = make_lod(low, "StoolLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "StoolLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_stool_mesh("StoolColSrc", **flags)
    collider = convex_hull_collider(collider_src, "StoolCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_tavern_stool_{os.getpid()}.glb",
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
    sup = support_audit(low.data)
    st = seat_audit(low.data)
    sj = stretcher_join(low.data)
    ft = foot_audit(low.data)

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
        f"measured supports cups={sup['cups']} cup_z={sup['cup_z']:.5f} "
        f"seat_dia={st['dia']:.4f} seat_h={st['height']:.4f} "
        f"stretch_join={sj:.5f}"
    )
    print(
        f"measured feet legs={ft['legs']} sleeves={ft['sleeves']} treads={ft['treads']} "
        f"grip={ft['grip']:.5f}..{ft['grip_max']:.5f} leg_above_tread={ft['above']:.5f} "
        f"sleeve_buried={ft['buried']:.5f}"
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
    if sup["cups"] < 4 or sup["cup_z"] > FERRULE_Z_MAX:
        return fail(
            f"ferrule supports {sup['cups']} cup_z={sup['cup_z']:.5f} "
            "(--short-legs is the designed fail)",
            16,
        ), None, None, None, None, None
    if sj > STRETCH_JOIN:
        return fail(
            f"stretcher-leg gap {sj:.5f} > {STRETCH_JOIN} "
            "(--float-stretchers is the designed fail)",
            17,
        ), None, None, None, None, None
    if (
        ft["sleeves"] != N_LEGS
        or not (FERRULE_BITE_MIN <= ft["grip"] and ft["grip_max"] <= FERRULE_BITE_MAX)
    ):
        return fail(
            f"ferrule grip {ft['grip']:.5f}..{ft['grip_max']:.5f} not in "
            f"[{FERRULE_BITE_MIN}, {FERRULE_BITE_MAX}] sleeves={ft['sleeves']} "
            "(--pipe-ferrule is the designed fail)",
            18,
        ), None, None, None, None, None
    if abs(st["dia"] - BODY_DIA) > BODY_DIA_TOL:
        return fail(
            f"seat diameter {st['dia']:.4f} off {BODY_DIA}",
            19,
        ), None, None, None, None, None
    if abs(st["height"] - BODY_H) > BODY_H_TOL:
        return fail(
            f"seat height {st['height']:.4f} off {BODY_H}",
            19,
        ), None, None, None, None, None
    if (
        ft["legs"] != N_LEGS or ft["treads"] != N_LEGS
        or ft["above"] < FOOT_ABOVE_MIN or ft["buried"] < FOOT_BURIED_MIN
    ):
        return fail(
            f"foot stack: leg above tread {ft['above']:.5f} < {FOOT_ABOVE_MIN} or "
            f"sleeve buried {ft['buried']:.5f} < {FOOT_BURIED_MIN} "
            f"legs={ft['legs']} treads={ft['treads']} "
            "(--sink-legs is the designed fail)",
            20,
        ), None, None, None, None, None
    if texel < TEXEL_MIN:
        return fail(
            f"bake texel density {texel:.2f} px per UV cell < {TEXEL_MIN} "
            "(--low-bake is the designed fail)",
            21,
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

    low.rotation_euler.z = math.radians(-32.0)
    low.rotation_euler.x = math.radians(6.0)

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

    light("Key", (-3.6, -5.0, 5.4), 660.0, 4.0, (1.0, 0.94, 0.86), (50, 0, -36))
    light("Fill", (5.0, -3.4, 2.4), 46.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.2, 4.0, 3.8), 600.0, 5.5, (1.0, 0.70, 0.40), (-70, 0, 198))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.05, -1.38, 0.92)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.26)
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
    p.add_argument("--float-stretchers", action="store_true")
    p.add_argument("--pipe-ferrule", action="store_true")
    p.add_argument("--sink-legs", action="store_true")
    p.add_argument("--low-bake", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_legs=args.short_legs,
        float_stretchers=args.float_stretchers,
        pipe_ferrule=args.pipe_ferrule,
        sink_legs=args.sink_legs,
        low_bake=args.low_bake,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("tavern-stool OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
