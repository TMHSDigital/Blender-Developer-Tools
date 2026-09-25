"""Game-ready ox yoke — a showcase piece, not an example.

Asserts budget conformance of a procedural double ox yoke: a carved oak
beam with two neck saddles and upturned ends, two bent-hickory oxbows
whose legs pass up through the beam and are pinned above it, and a forged
staple under the centre carrying a hung iron ring. It stands on the
bottoms of its two bows. Carried through UVs, three materials (oak,
hickory, iron), a high-to-low normal bake, an LOD chain, a compound
convex collider, and a Unity glTF export.

The budget that matters here is the one a yoke fails invisibly: each bow
and its saddle must close round an ox's neck. A bow bent too tight still
stands on the floor, still passes up through the beam, still takes its
pins and still fits the bounding box; only the opening knows. The piece
measures each opening's width between the bow's legs and its height from
the bow's inner bottom to the saddle, off the finished mesh.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-bow`` the named bows,
``--short-bows`` the leg protrusion, ``--short-staple`` the staple bite,
``--edge-on-ring`` the threaded ring, ``--float-pins`` the pin seat,
``--clip-ring`` the hung ring, ``--pinch-bows`` the neck opening,
``--skew-bow`` the mirrored bows.

No randomness. DECIMATE COLLAPSE triangle counts are not byte-identical
across Blender versions — the LOD gate is a ratio band.

    blender --background --python wooden_yoke.py --
    blender --background --python wooden_yoke.py -- --pinch-bows
    blender --background --python wooden_yoke.py -- --output wooden_yoke.png
"""
import argparse
import math
import os
import sys
import tempfile
import traceback

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

# The beam, lofted along X. Every shaping term is even in x, so the two
# halves of the yoke are mirror images and the two bows see one beam.
HALF_L = 0.700
BOTTOM_Z = 0.360
TOP_Z = 0.500
CROWN = 0.050
UPTURN = 0.140
UPTURN_POW = 6
BEAM_W = 0.130
BEAM_W_TAPER = 0.030
SECTION_N = 3.0
BEAM_SEG = 16
BEAM_STATIONS = 30
END_REACH = 0.012
SADDLE_DEPTH = 0.050
SADDLE_HALF = 0.160

# Bows: a round hickory rod bent into a U, legs straight up through the
# beam, bottom a half-ellipse whose lowest point stands on the floor.
BOW_X = 0.400
BOW_A = 0.155
PINCH_A = 0.120
BOW_R = 0.022
BOW_SEG = 12
BOW_ARC_Z = 0.200
BOW_ARC_STEPS = 16
BOW_PROTRUDE = 0.045
SHORT_BOW = -0.010
FLOAT_BOW = 0.008
SKEW_BOW = 0.006

# Iron: a pin across each leg tip, resting on the beam; a staple under the
# centre; a ring hung on the staple's bar.
PIN_R = 0.006
PIN_L = 0.140
PIN_SEAT = 0.0015
FLOAT_PIN = 0.005
STAPLE_R = 0.007
STAPLE_C = 0.030
STAPLE_DROP = 0.035
STAPLE_BITE = 0.015
SHORT_STAPLE = -0.005
RING_R = 0.050
RING_T = 0.008
RING_BITE = 0.001
RING_SEG = 24
RING_TUBE_SEG = 10
CLIP_RING = 0.006

BBOX_TOL = 0.020
OUTER_SIZE = (1.424, 0.140, 0.640)

BASE_TRIS_MIN = 4800
BASE_TRIS_MAX = 5800
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
FACE_FLOORS = {0: 950, 1: 650, 2: 750}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 300
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
BOW_Z_MAX = 1e-4
PROTRUDE_MIN = 0.025
PROTRUDE_MAX = 0.070
STAPLE_BITE_MIN = 0.008
STAPLE_BITE_MAX = 0.030
THREAD_COS_MIN = math.cos(math.radians(20.0))
PIN_SEAT_MIN = 0.0005
PIN_SEAT_MAX = 0.0030
RING_GAP_MIN = -0.003
RING_GAP_MAX = 0.0005
NECK_W_MIN = 0.240
NECK_W_MAX = 0.300
NECK_H_MIN = 0.300
NECK_H_MAX = 0.400
MIRROR_EPS = 1e-4

OAK_IDX = 0
HICKORY_IDX = 1
IRON_IDX = 2


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


# --- beam shape -------------------------------------------------------------


def upturn(x):
    return UPTURN * (x / HALF_L) ** UPTURN_POW


def saddle(x):
    """Raise of the beam's underside over each neck: a cosine bump, even in x."""
    d = abs(abs(x) - BOW_X)
    if d >= SADDLE_HALF:
        return 0.0
    return SADDLE_DEPTH * 0.5 * (1.0 + math.cos(math.pi * d / SADDLE_HALF))


def beam_top(x):
    return TOP_Z + CROWN * math.cos(math.pi * x / (2.0 * HALF_L)) ** 2 + upturn(x)


def beam_bottom(x):
    return BOTTOM_Z + saddle(x) + upturn(x)


def beam_width(x):
    return BEAM_W - BEAM_W_TAPER * (x / HALF_L) ** 2


def beam_stations(leg_xs, bow_xs):
    """Stations for x >= 0, mirrored: a uniform run plus one at every leg and neck.

    A station on each leg and bow centre puts a beam ring exactly where a pin rests, so
    the top the pin is measured against is a vertex, not a chord.
    """
    pos = {round(HALF_L * k / BEAM_STATIONS, 6) for k in range(BEAM_STATIONS + 1)}
    pos |= {round(abs(x), 6) for x in list(leg_xs) + list(bow_xs)}
    pos = sorted(pos)
    return sorted({-x for x in pos} | set(pos))


def section(x, k):
    """Superellipse section vertex ``k`` of BEAM_SEG at station ``x``: (y, z)."""
    phi = 2.0 * math.pi * k / BEAM_SEG
    c, s = math.cos(phi), math.sin(phi)
    e = 2.0 / SECTION_N
    zc = (beam_top(x) + beam_bottom(x)) * 0.5
    hh = (beam_top(x) - beam_bottom(x)) * 0.5
    y = beam_width(x) * 0.5 * math.copysign(abs(c) ** e, c)
    z = zc + hh * math.copysign(abs(s) ** e, s)
    return y, z


# --- construction -----------------------------------------------------------


def new_island(ctx):
    ctx["next"] += 1
    return ctx["next"]


def stamp(ctx, face, island, uvmap, grain):
    face[ctx["isl"]] = island
    for loop in face.loops:
        loop[ctx["uv"]].uv = uvmap[loop.vert]
    face[ctx["gx"]], face[ctx["gy"]], face[ctx["gz"]] = grain


def tube(bm, rings, closed_ends, mat_idx, ctx, grains):
    """Quads between consecutive rings, fans to the two end poles."""
    island = new_island(ctx)
    n = len(rings[0])
    arc = [0.0]
    for a, b in zip(rings, rings[1:]):
        ca = sum((v.co for v in a), Vector()) / n
        cb = sum((v.co for v in b), Vector()) / n
        arc.append(arc[-1] + (cb - ca).length)
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new((a[i], a[j], b[j], b[i]))
            f.material_index = mat_idx
            stamp(ctx, f, island, {a[i]: (arc[k], i / n), a[j]: (arc[k], (i + 1) / n),
                                   b[j]: (arc[k + 1], (i + 1) / n), b[i]: (arc[k + 1], i / n)},
                  grains[k])
    for pole, ring, s, g, sign in ((closed_ends[0], rings[0], arc[0], grains[0], -1.0),
                                   (closed_ends[1], rings[-1], arc[-1], grains[-1], 1.0)):
        for i in range(n):
            j = (i + 1) % n
            vs = (pole, ring[i], ring[j]) if sign < 0 else (pole, ring[j], ring[i])
            f = bm.faces.new(vs)
            f.material_index = mat_idx
            stamp(ctx, f, island, {pole: (s + sign * 0.01, (i + 0.5) / n),
                                   ring[i]: (s, i / n), ring[j]: (s, (i + 1) / n)}, g)


def add_beam(bm, ctx, leg_xs, bow_xs):
    xs = beam_stations(leg_xs, bow_xs)
    rings = []
    for x in xs:
        rings.append([bm.verts.new((x, *section(x, k))) for k in range(BEAM_SEG)])
    z0 = (beam_top(xs[0]) + beam_bottom(xs[0])) * 0.5
    z1 = (beam_top(xs[-1]) + beam_bottom(xs[-1])) * 0.5
    poles = (bm.verts.new((xs[0] - END_REACH, 0.0, z0)), bm.verts.new((xs[-1] + END_REACH, 0.0, z1)))
    tube(bm, rings, poles, OAK_IDX, ctx, [(1.0, 0.0, 0.0)] * len(rings))


def sweep(bm, pts, radius, seg, side, mat_idx, ctx, cone=0.35, grain=None):
    """Round section swept along ``pts`` with its frame fixed to the path's plane.

    ``side`` is the plane's normal; the section's vertex 3*seg/4 points
    down the path's ``up`` (t x side) negative, so a path's lowest point
    puts a vertex exactly ``radius`` below it. Ends close in blunt cones.

    ``grain`` fixes one grain direction for the whole shell. The shader
    stretches its noise along the face's direction, so a per-ring tangent
    breaks the figure at every ring: the bent bows rendered as bamboo.
    """
    m = len(pts)
    tans = [(pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(m)]
    rings = []
    for p, t in zip(pts, tans):
        s = (side - t * side.dot(t)).normalized()
        up = t.cross(s)
        rings.append([bm.verts.new(p + s * (radius * math.cos(2 * math.pi * k / seg))
                                   + up * (radius * math.sin(2 * math.pi * k / seg)))
                      for k in range(seg)])
    poles = (bm.verts.new(pts[0] - tans[0] * (cone * radius)),
             bm.verts.new(pts[-1] + tans[-1] * (cone * radius)))
    grains = [grain] * m if grain is not None else [tuple(t) for t in tans]
    tube(bm, rings, poles, mat_idx, ctx, grains)


def bow_path(cx, a, tip_l, tip_r, lift=0.0):
    """U centreline: left leg down, half-ellipse under the neck, right leg up."""
    pts = []
    zc = BOW_ARC_Z + lift
    b = zc - (BOW_R + lift)
    for k in range(6):
        pts.append(Vector((cx - a, 0.0, tip_l + (zc - tip_l) * k / 6)))
    for k in range(BOW_ARC_STEPS + 1):
        th = math.pi + math.pi * k / BOW_ARC_STEPS
        pts.append(Vector((cx + a * math.cos(th), 0.0, zc + b * math.sin(th))))
    for k in range(1, 7):
        pts.append(Vector((cx + a, 0.0, zc + (tip_r - zc) * k / 6)))
    return pts


def lathe_y(bm, profile, n, mat_idx, ctx, origin):
    """Revolve an (r, t) profile about an axis along +Y from ``origin``."""
    xf = Matrix.Translation(origin) @ Matrix.Rotation(-math.pi / 2.0, 4, "X")
    rings, poles = [], []
    for p in profile:
        if p.x <= 0.0:
            poles.append(bm.verts.new(xf @ Vector((0.0, 0.0, p.y))))
        else:
            rings.append([bm.verts.new(xf @ Vector((p.x * math.cos(2 * math.pi * k / n),
                                                     p.x * math.sin(2 * math.pi * k / n), p.y)))
                          for k in range(n)])
    tube(bm, rings, poles, mat_idx, ctx, [(0.0, 1.0, 0.0)] * len(rings))


def pin_profile():
    """A forged pin: shank with a flat head at the far end, from its near end."""
    h = PIN_L
    # Two shank rings over the beam's crown, so the seat is measured on
    # vertices where the pin rests rather than on a span between its ends.
    rings = [(PIN_R * 0.7, 0.0), (PIN_R, 0.004), (PIN_R, h * 0.5 - 0.02), (PIN_R, h * 0.5 + 0.02),
             (PIN_R, h - 0.010), (PIN_R * 1.7, h - 0.008),
             (PIN_R * 1.7, h - 0.002), (PIN_R * 1.2, h)]
    return [Vector((0.0, 0.0))] + [Vector(r) for r in rings] + [Vector((0.0, h))]


def add_ring(bm, centre, normal_axis, ctx):
    """Torus of RING_R by RING_T in the plane whose normal is ``normal_axis``."""
    n = Vector(normal_axis)
    u = Vector((0.0, 0.0, 1.0)) if abs(n.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    v = n.cross(u)
    rings = []
    for i in range(RING_SEG):
        a = 2.0 * math.pi * i / RING_SEG
        radial = u * math.cos(a) + v * math.sin(a)
        c = centre + radial * RING_R
        rings.append([bm.verts.new(c + radial * (RING_T * math.cos(2 * math.pi * k / RING_TUBE_SEG))
                                   + n * (RING_T * math.sin(2 * math.pi * k / RING_TUBE_SEG)))
                      for k in range(RING_TUBE_SEG)])
    island = new_island(ctx)
    for i in range(RING_SEG):
        a, b = rings[i], rings[(i + 1) % RING_SEG]
        tang = tuple((b[0].co - a[0].co).normalized())
        for k in range(RING_TUBE_SEG):
            j = (k + 1) % RING_TUBE_SEG
            f = bm.faces.new((a[k], a[j], b[j], b[k]))
            f.material_index = IRON_IDX
            stamp(ctx, f, island, {a[k]: (i / RING_SEG, k / RING_TUBE_SEG),
                                   a[j]: (i / RING_SEG, (k + 1) / RING_TUBE_SEG),
                                   b[j]: ((i + 1) / RING_SEG, (k + 1) / RING_TUBE_SEG),
                                   b[k]: ((i + 1) / RING_SEG, k / RING_TUBE_SEG)}, tang)


def build_yoke_mesh(
    name,
    stray_vert=False,
    float_bow=False,
    short_bows=False,
    short_staple=False,
    edge_on_ring=False,
    float_pins=False,
    clip_ring=False,
    pinch_bows=False,
    skew_bow=False,
):
    a = PINCH_A if pinch_bows else BOW_A
    bows = []
    for side in (-1.0, 1.0):
        cx = side * BOW_X + (SKEW_BOW if (skew_bow and side > 0) else 0.0)
        bows.append((cx, side))
    leg_xs = [cx + d for cx, _s in bows for d in (-a, a)]
    bm = bmesh.new()
    try:
        ctx = {"uv": bm.loops.layers.uv.new("UVMap"),
               "isl": bm.faces.layers.int.new("UVIsland"),
               "gx": bm.faces.layers.float.new("gx"),
               "gy": bm.faces.layers.float.new("gy"),
               "gz": bm.faces.layers.float.new("gz"), "next": 0}
        add_beam(bm, ctx, leg_xs, [cx for cx, _s in bows])
        for cx, side in bows:
            lift = FLOAT_BOW if (float_bow and side < 0) else 0.0
            protrude = SHORT_BOW if short_bows else BOW_PROTRUDE
            tip_l = beam_top(cx - a) + protrude
            tip_r = beam_top(cx + a) + protrude
            sweep(bm, bow_path(cx, a, tip_l, tip_r, lift=lift), BOW_R, BOW_SEG,
                  Vector((0.0, 1.0, 0.0)), HICKORY_IDX, ctx, grain=(0.0, 0.0, 1.0))
            # Pins across each leg tip, resting on the beam's top at that leg.
            for lx in (cx - a, cx + a):
                pz = beam_top(lx) + PIN_R - PIN_SEAT + (FLOAT_PIN if float_pins else 0.0)
                lathe_y(bm, pin_profile(), 12, IRON_IDX, ctx,
                        Vector((lx, -PIN_L * 0.5, pz)))
        # Staple under the centre: a round bar bent into a U across Y, its
        # legs driven up into the beam.
        bb = beam_bottom(0.0)
        top = bb + (SHORT_STAPLE if short_staple else STAPLE_BITE)
        bar_z = bb - STAPLE_DROP
        pts = [Vector((0.0, -STAPLE_C, top + (bar_z - top) * k / 4)) for k in range(4)]
        for k in range(13):
            th = math.pi + math.pi * k / 12
            pts.append(Vector((0.0, STAPLE_C * math.cos(th), bar_z + STAPLE_C * math.sin(th))))
        pts += [Vector((0.0, STAPLE_C, bar_z + (top - bar_z) * k / 4)) for k in range(1, 5)]
        sweep(bm, pts, STAPLE_R, 12, Vector((1.0, 0.0, 0.0)), IRON_IDX, ctx)
        # The ring hangs on the staple's bar: its inner edge rests on the
        # bar's top, and its hole runs along the bar (Y).
        low = bar_z - STAPLE_C
        rc = Vector((0.0, 0.0, low + STAPLE_R + RING_T - RING_R - RING_BITE
                     + (CLIP_RING if clip_ring else 0.0)))
        add_ring(bm, rc, (1.0, 0.0, 0.0) if edge_on_ring else (0.0, 1.0, 0.0), ctx)
        if stray_vert:
            bm.verts.new((0.0, 0.0, 0.1))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(40.0):
                e.smooth = False
        pack_uvs(bm, ctx)
        bm.faces.layers.int.remove(ctx["isl"])
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    paint_pieces(me)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def pack_uvs(bm, ctx, margin=0.06):
    """One grid cell per UV island (every face here belongs to a strip island)."""
    uv, isl = ctx["uv"], ctx["isl"]
    islands, order = {}, []
    for face in bm.faces:
        key = face[isl]
        if key not in islands:
            islands[key] = []
            order.append(key)
        islands[key].append(face)
    cols = max(1, math.ceil(math.sqrt(len(order))))
    rows = max(1, math.ceil(len(order) / cols))
    cw, ch = 1.0 / cols, 1.0 / rows
    pu, pv = margin * cw * 0.5, margin * ch * 0.5
    for idx, key in enumerate(order):
        faces = islands[key]
        allc = [tuple(loop[uv].uv) for f in faces for loop in f.loops]
        minx, maxx = min(c[0] for c in allc), max(c[0] for c in allc)
        miny, maxy = min(c[1] for c in allc), max(c[1] for c in allc)
        dx, dy = max(maxx - minx, 1e-8), max(maxy - miny, 1e-8)
        ou, ov = (idx % cols) * cw + pu, (idx // cols) * ch + pv
        for face in faces:
            for loop in face.loops:
                x, y = loop[uv].uv
                loop[uv].uv = (ou + (x - minx) / dx * (cw - 2 * pu),
                               ov + (y - miny) / dy * (ch - 2 * pv))


def paint_pieces(me):
    """``GrainDir`` from the per-face path tangent, ``PlankTone`` per shell."""
    npoly = len(me.polygons)
    comps = []
    for nm in ("gx", "gy", "gz"):
        vals = [0.0] * npoly
        me.attributes[nm].data.foreach_get("value", vals)
        comps.append(vals)
        me.attributes.remove(me.attributes[nm])
    grain = [c for i in range(npoly) for c in (comps[0][i], comps[1][i], comps[2][i])]
    tone = [0.5] * npoly
    vf = [[] for _ in range(len(me.vertices))]
    for p in me.polygons:
        for i in p.vertices:
            vf[i].append(p.index)
    for k, g in enumerate(shells(me)):
        t = 0.5 + 0.3 * (((k * 0.6180339887 + 0.3) % 1.0) - 0.5)
        for fi in {fi for i in g for fi in vf[i]}:
            tone[fi] = t
    a = me.attributes.new("PlankTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)
    b = me.attributes.new("GrainDir", "FLOAT_VECTOR", "FACE")
    b.data.foreach_set("vector", grain)


# --- surface ----------------------------------------------------------------


def _sock(sockets, identifier):
    return next(sk for sk in sockets if sk.identifier == identifier)


def wood_material(name, dark, light, rough=(0.72, 0.52)):
    """Timber whose grain runs along ``GrainDir`` and whose tone varies by piece."""
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
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 1.0
    gain.inputs[2].default_value = 0.50
    nt.links.new(tone.outputs["Fac"], gain.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(ramp.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(gain.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    rmap = nt.nodes.new("ShaderNodeMapRange")
    rmap.inputs["To Min"].default_value = rough[0]
    rmap.inputs["To Max"].default_value = rough[1]
    nt.links.new(noise.outputs["Fac"], rmap.inputs["Value"])
    nt.links.new(rmap.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def iron_material(name):
    """Forged iron: near-black, rough, rusted in patches. Not chrome."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.035, 0.033, 0.031, 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (0.20, 0.085, 0.035, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.65
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.55
    rough.inputs["To Max"].default_value = 0.85
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def yoke_materials():
    return (
        wood_material("YokeOak", (0.075, 0.040, 0.018), (0.25, 0.14, 0.065)),
        wood_material("YokeHickory", (0.13, 0.075, 0.035), (0.36, 0.22, 0.11), rough=(0.66, 0.46)),
        iron_material("YokeIron"),
    )


def assign_slots(obj, mats):
    slots = obj.data.materials
    for i, mat in enumerate(mats):
        if i < len(slots):
            slots[i] = mat
        else:
            slots.append(mat)


# --- measurement ------------------------------------------------------------


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs, ys, zs = [c.x for c in corners], [c.y for c in corners], [c.z for c in corners]
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
    span = max(1e-6, max(a[2] - a[0] for a in aabbs), max(a[3] - a[1] for a in aabbs))
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
                    0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return min(us), min(vs), max(us), max(vs), overlap, len(aabbs)


def face_area(me, poly):
    idxs = poly.vertices
    v0 = me.vertices[idxs[0]].co
    area = 0.0
    for i in range(1, len(idxs) - 1):
        area += (me.vertices[idxs[i]].co - v0).cross(me.vertices[idxs[i + 1]].co - v0).length * 0.5
    return area


def hygiene_audit(me):
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
    return {"ngons": ngons, "loose_v": loose_v, "loose_e": loose_e,
            "nonman": nonman, "zero_area": zero_area, "doubles": doubles}


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


def zfight_pairs(me):
    """Coplanar face pairs from *different shells* (copied from showcase/grindstone)."""
    owner = {}
    for si, g in enumerate(shells(me)):
        for vi in g:
            owner[vi] = si
    faces = [(p.normal.copy(), p.center.copy(), owner.get(p.vertices[0], -1))
             for p in me.polygons]
    kd = KDTree(len(faces))
    for i, (_n, c, _s) in enumerate(faces):
        kd.insert(c, i)
    kd.balance()
    hits = 0
    for i, (ni, ci, si) in enumerate(faces):
        for _co, j, _d in kd.find_range(ci, COPLANAR_CENTRE_MAX):
            if j <= i:
                continue
            nj, cj, sj = faces[j]
            if si == sj:
                continue
            if abs(abs(ni.dot(nj)) - 1.0) > COPLANAR_NORMAL_EPS:
                continue
            if abs(ni.dot(cj - ci)) > COPLANAR_PLANE_EPS:
                continue
            hits += 1
    return hits


def classify(me):
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    out = {"beam": [], "bow": [], "pin": [], "staple": [], "ring": [], "other": []}
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        rec = {"g": g, "pts": pts, "lo": lo, "hi": hi, "ext": hi - lo,
               "c": sum(pts, Vector()) / len(pts)}
        m = mats.get(g[0], -1)
        if m == OAK_IDX:
            out["beam"].append(rec)
        elif m == HICKORY_IDX:
            out["bow"].append(rec)
        elif m == IRON_IDX:
            e = rec["ext"]
            if e.z < 4.0 * PIN_R and e.y > 0.05:
                out["pin"].append(rec)
            elif min(e.x, e.y) < 2.5 * RING_T + 1e-3 and max(e.x, e.y) > 0.09:
                out["ring"].append(rec)
            else:
                out["staple"].append(rec)
        else:
            out["other"].append(rec)
    return out


def yoke_audit(me):
    parts = classify(me)
    out = {k: len(v) for k, v in parts.items()}
    beam = parts["beam"][0]["pts"] if parts["beam"] else []

    def beam_top_at(x):
        near = [p.z for p in beam if abs(p.x - x) < 0.002]
        return max(near) if near else 99.0

    def beam_bottom_at(x):
        near = [p.z for p in beam if abs(p.x - x) < 0.002]
        return min(near) if near else -99.0

    bows = sorted(parts["bow"], key=lambda r: r["c"].x)
    out["bow_z"] = max((r["lo"].z for r in bows), default=99.0)

    # Legs pass up through the beam and stand proud of it.
    protrude, widths, heights = [], [], []
    for r in bows:
        cx = (r["lo"].x + r["hi"].x) * 0.5
        for sgn in (-1.0, 1.0):
            leg = [p for p in r["pts"] if (p.x - cx) * sgn > 0 and p.z > BOTTOM_Z]
            if not leg:
                continue
            lx = sum(p.x for p in leg) / len(leg)
            protrude.append(max(p.z for p in leg) - beam_top_at(lx))
        # Neck opening: between the legs' inner faces at mid-height, and from
        # the bow's inner bottom up to the saddle.
        mid = [p for p in r["pts"] if BOW_ARC_Z + 0.01 < p.z < BOW_ARC_Z + 0.15]
        left = [p.x for p in mid if p.x < cx]
        right = [p.x for p in mid if p.x > cx]
        if left and right:
            widths.append(min(right) - max(left))
        under = [p.z for p in r["pts"] if abs(p.x - cx) < 0.002 and p.z < BOW_ARC_Z]
        if under:
            heights.append(beam_bottom_at(cx) - max(under))
    out["protrude"] = (min(protrude, default=-99.0), max(protrude, default=99.0))
    out["n_legs"] = len(protrude)
    out["neck_w"] = (min(widths, default=-99.0), max(widths, default=99.0))
    out["neck_h"] = (min(heights, default=-99.0), max(heights, default=99.0))

    # Mirrored bows: one the image of the other through x = 0.
    mirror = 99.0
    if len(bows) == 2:
        a, b = bows
        mirror = max(abs(a["lo"].x + b["hi"].x), abs(a["hi"].x + b["lo"].x),
                     abs(a["lo"].z - b["lo"].z), abs(a["hi"].z - b["hi"].z),
                     abs(a["lo"].y - b["lo"].y), abs(a["hi"].y - b["hi"].y))
    out["mirror"] = mirror

    # Pins rest on the beam's top at their leg.
    # Measured on the shank over the beam; the head hangs past the beam's edge.
    seats = [beam_top_at(r["c"].x) - min(p.z for p in r["pts"] if abs(p.y) < 0.03)
             for r in parts["pin"]]
    out["pin_seat"] = (min(seats, default=-99.0), max(seats, default=99.0))

    # Staple driven into the beam; ring threaded on, and hanging from, its bar.
    out["staple_bite"] = -99.0
    out["thread"] = 0.0
    out["ring_gap"] = 99.0
    if parts["staple"] and parts["ring"]:
        st = parts["staple"][0]
        out["staple_bite"] = st["hi"].z - beam_bottom_at(st["c"].x)
        r_s = st["ext"].x * 0.5
        bar = Vector((st["c"].x, (st["lo"].y + st["hi"].y) * 0.5, st["lo"].z + r_s))
        normal_s = min(range(3), key=lambda k: st["ext"][k])
        bar_dir = Vector((0.0, 0.0, 1.0)).cross(Vector([1.0 if k == normal_s else 0.0
                                                        for k in range(3)])).normalized()
        rg = parts["ring"][0]
        c = rg["c"]
        nk = min(range(3), key=lambda k: rg["ext"][k])
        n = Vector([1.0 if k == nk else 0.0 for k in range(3)])
        radial = [((p - c) - n * (p - c).dot(n)).length for p in rg["pts"]]
        r_in, r_out = min(radial), max(radial)
        d = bar - c
        in_plane = (d - n * d.dot(n)).length
        out["thread"] = abs(n.dot(bar_dir))
        out["ring_gap"] = r_in - (in_plane + r_s)
        out["ring_tube"] = (r_out - r_in) * 0.5
    return out


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


def ring_sample(me, group, seg, ring_step, vert_step, keep=None):
    """Every ``ring_step``-th ring and ``vert_step``-th vertex of a swept shell.

    Vertices are laid ring after ring in build order, so index order is
    ring order; the two end poles are the last two indices and are kept.
    """
    order = sorted(group)
    body, poles = order[:-2], order[-2:]
    nrings = len(body) // seg
    pts = []
    for r in range(nrings):
        if r % ring_step and r != nrings - 1:
            continue
        ring = [me.vertices[body[r * seg + k]].co.copy() for k in range(0, seg, vert_step)]
        if keep is None or keep(sum(ring, Vector()) / len(ring)):
            pts += ring
    return pts + [me.vertices[i].co.copy() for i in poles if keep is None
                  or keep(me.vertices[i].co)]


def hull_collider(obj, name):
    """Compound collider: one hull for the beam, one per bow leg and one per bow foot.

    A single hull over a bow fills the neck opening, which is exactly the
    space the yoke exists to leave open. Hulls are taken over sampled rings
    of each swept shell, not over every vertex.
    """
    me = obj.data
    parts = classify(me)
    groups = []
    if parts["beam"]:
        groups.append(ring_sample(me, parts["beam"][0]["g"], BEAM_SEG, 8, 2))
    for r in parts["bow"]:
        cx = (r["lo"].x + r["hi"].x) * 0.5
        g = r["g"]
        groups.append(ring_sample(me, g, BOW_SEG, 5, 2,
                                  lambda c, cx=cx: c.x < cx and c.z > BOW_ARC_Z - 0.01))
        groups.append(ring_sample(me, g, BOW_SEG, 5, 2,
                                  lambda c, cx=cx: c.x > cx and c.z > BOW_ARC_Z - 0.01))
        groups.append(ring_sample(me, g, BOW_SEG, 4, 2, lambda c: c.z <= BOW_ARC_Z + 0.01))
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for pts in groups:
            if len(pts) < 4:
                continue
            tmp = bmesh.new()
            try:
                vs = [tmp.verts.new(p) for p in pts]
                bmesh.ops.convex_hull(tmp, input=vs)
                remap = {}
                for f in tmp.faces:
                    for v in f.verts:
                        if v not in remap:
                            remap[v] = bm.verts.new(v.co)
                    bm.faces.new([remap[v] for v in f.verts])
            finally:
                tmp.free()
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    col = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(col)
    return col


def setup_bake_image(obj, target_mat, size):
    img = bpy.data.images.new("YokeNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = OAK_IDX
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
        type="NORMAL", use_selected_to_active=True, cage_extrusion=CAGE_EXTRUSION,
        use_cage=False, normal_space="TANGENT", margin=4,
        margin_type="ADJACENT_FACES", use_clear=True, target="IMAGE_TEXTURES",
    )


def export_unity(path, objects):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(
        filepath=path, use_selection=True, export_yup=True, export_apply=True,
        export_draco_mesh_compression_enable=False, export_animations=False,
    )


def check(skip_decimate, lift_z=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_yoke_mesh("YokeLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_yoke_mesh("YokeHigh", **hi_flags)
    mats = yoke_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("yoke mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[OAK_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "YokeLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "YokeLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(high, "YokeCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_yoke_{os.getpid()}.glb")
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
    ya = yoke_audit(low.data)

    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured mat_index_counts={dict(sorted(idx_counts.items()))}")
    print(f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
          f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}")
    print(f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
          f"overlap={overlap:.6f} nfaces={nfaces}")
    print(f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
          f"outer={OUTER_SIZE} zmin={bb[2]:.5f}")
    print(f"measured collider_tris={col_tris} bake={bake_result} "
          f"bake_has_data={img.has_data} export_bytes={export_size}")
    print(f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
          f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
          f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}")
    print(f"measured parts beam={ya['beam']} bows={ya['bow']} pins={ya['pin']} "
          f"staple={ya['staple']} ring={ya['ring']} other={ya['other']} "
          f"bow_z={ya['bow_z']:.5f} legs={ya['n_legs']}")
    print(f"measured joints protrude=({ya['protrude'][0]:.5f},{ya['protrude'][1]:.5f}) "
          f"staple_bite={ya['staple_bite']:.5f} thread={ya['thread']:.4f}")
    print(f"measured seats pin=({ya['pin_seat'][0]:.5f},{ya['pin_seat'][1]:.5f}) "
          f"ring_gap={ya['ring_gap']:.5f}")
    print(f"measured neck width=({ya['neck_w'][0]:.5f},{ya['neck_w'][1]:.5f}) "
          f"height=({ya['neck_h'][0]:.5f},{ya['neck_h'][1]:.5f}) mirror={ya['mirror']:.6f}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + nothing
    if nmat != MATERIAL_COUNT or distinct != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct} != {MATERIAL_COUNT}", 5),) + nothing
    for idx, floor in FACE_FLOORS.items():
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"material {idx} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + nothing
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6),) + nothing
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + nothing
    if (abs(size_x - OUTER_SIZE[0]) > BBOX_TOL or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
            or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL):
        return (fail(f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8),) + nothing
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
                     "(--skip-decimate is the designed fail)", 9),) + nothing
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9),) + nothing
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + nothing
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(f"bake failed result={bake_result} has_data={img.has_data}", 12),) + nothing
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + nothing
    if (hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
            or hyg["doubles"] or hyg["ngons"] or zf):
        return (fail(f"hygiene {hyg} zfight={zf} (--stray-vert is the designed fail)", 15),) + nothing
    if abs(bb[2]) > ZMIN_EPS:
        return (fail(f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
                     "(--lift-z is the designed fail)", 16),) + nothing
    if ya["bow"] != 2 or ya["bow_z"] > BOW_Z_MAX:
        return (fail(f"bows: {ya['bow']} of 2, worst bow z={ya['bow_z']:.5f} > {BOW_Z_MAX} "
                     "(--float-bow is the designed fail)", 16),) + nothing
    if (ya["n_legs"] != 4 or ya["protrude"][0] < PROTRUDE_MIN
            or ya["protrude"][1] > PROTRUDE_MAX):
        return (fail(f"{ya['n_legs']} of 4 legs, protrusion above the beam {ya['protrude']} "
                     f"outside [{PROTRUDE_MIN}, {PROTRUDE_MAX}] (--short-bows is the designed fail)",
                     17),) + nothing
    if not (STAPLE_BITE_MIN <= ya["staple_bite"] <= STAPLE_BITE_MAX):
        return (fail(f"staple bite {ya['staple_bite']:.5f} outside [{STAPLE_BITE_MIN}, "
                     f"{STAPLE_BITE_MAX}] (--short-staple is the designed fail)", 17),) + nothing
    if ya["ring"] != 1 or ya["thread"] < THREAD_COS_MIN:
        return (fail(f"{ya['ring']} ring, hole axis against the bar {ya['thread']:.4f} < "
                     f"{THREAD_COS_MIN:.4f} (--edge-on-ring is the designed fail)", 17),) + nothing
    if ya["pin"] != 4 or ya["pin_seat"][0] < PIN_SEAT_MIN or ya["pin_seat"][1] > PIN_SEAT_MAX:
        return (fail(f"{ya['pin']} of 4 pins, seat {ya['pin_seat']} outside [{PIN_SEAT_MIN}, "
                     f"{PIN_SEAT_MAX}] (--float-pins is the designed fail)", 18),) + nothing
    if not (RING_GAP_MIN <= ya["ring_gap"] <= RING_GAP_MAX):
        return (fail(f"ring hangs {ya['ring_gap']:.5f} off its bar, outside [{RING_GAP_MIN}, "
                     f"{RING_GAP_MAX}] (--clip-ring is the designed fail)", 18),) + nothing
    if (not (NECK_W_MIN <= ya["neck_w"][0] and ya["neck_w"][1] <= NECK_W_MAX)
            or not (NECK_H_MIN <= ya["neck_h"][0] and ya["neck_h"][1] <= NECK_H_MAX)):
        return (fail(f"neck opening width {ya['neck_w']} (band [{NECK_W_MIN}, {NECK_W_MAX}]), "
                     f"height {ya['neck_h']} (band [{NECK_H_MIN}, {NECK_H_MAX}]) "
                     "(--pinch-bows is the designed fail)", 19),) + nothing
    if ya["mirror"] > MIRROR_EPS:
        return (fail(f"bows not mirrored: {ya['mirror']:.6f} > {MIRROR_EPS} "
                     "(--skew-bow is the designed fail)", 19),) + nothing
    return 0, low, high, mats, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats[OAK_IDX], tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only.
    low.rotation_euler.z = math.radians(-22.0)

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
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, kind, loc, energy, size, col, rot=(0, 0, 0)):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        if kind == "AREA":
            ld.size = size
        else:
            ld.shadow_soft_size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", "AREA", (-2.4, -3.2, 3.0), 360.0, 3.0, (1.0, 0.95, 0.88), (50, 0, -35))
    light("Fill", "AREA", (3.2, -2.6, 1.4), 60.0, 5.0, (0.74, 0.84, 1.0), (70, 0, 50))
    light("Rim", "AREA", (-1.6, 2.6, 2.2), 220.0, 3.0, (0.62, 0.78, 1.0), (-55, 0, 200))
    ld = bpy.data.lights.new("Wedge", "SPOT")
    ld.energy, ld.color = 220.0, (1.0, 0.66, 0.34)
    ld.spot_size, ld.spot_blend, ld.shadow_soft_size = math.radians(50.0), 1.0, 0.3
    wedge = bpy.data.objects.new("Wedge", ld)
    wedge.location = (0.5, 1.6, 1.9)
    wedge.rotation_euler = (Vector((0.2, 0.5, 0.0)) - wedge.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.collection.objects.link(wedge)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.95, -2.35, 1.05)
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
    scene.render.image_settings.file_format = "WEBP" if path.lower().endswith(".webp") else "PNG"
    if path.lower().endswith(".webp"):
        scene.render.image_settings.quality = 90
    scene.render.filepath = path
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low], stage=[floor, wall])
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
    p.add_argument("--float-bow", action="store_true")
    p.add_argument("--short-bows", action="store_true")
    p.add_argument("--short-staple", action="store_true")
    p.add_argument("--edge-on-ring", action="store_true")
    p.add_argument("--float-pins", action="store_true")
    p.add_argument("--clip-ring", action="store_true")
    p.add_argument("--pinch-bows", action="store_true")
    p.add_argument("--skew-bow", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_bow=args.float_bow,
        short_bows=args.short_bows,
        short_staple=args.short_staple,
        edge_on_ring=args.edge_on_ring,
        float_pins=args.float_pins,
        clip_ring=args.clip_ring,
        pinch_bows=args.pinch_bows,
        skew_bow=args.skew_bow,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("wooden yoke OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
