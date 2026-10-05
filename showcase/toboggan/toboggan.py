"""Game-ready runner sled — a showcase piece, not an example.

Asserts budget conformance of a procedural Flexible-Flyer-style runner
sled: two steel-shod wooden runners with upturned front horns, six posts
carrying three cross bearers, a deck of seven lengthwise slats seated on
the bearers and screwed to them, one painted steering bar through both
runner horns drilled at its centre for a pull rope, and a three-strand
rope threaded through that hole and stopped with a knot behind it. Carried through UVs, five materials
(slat pine, stained frame, steel, hemp rope, red paint), a high-to-low
normal bake, an LOD chain, a compound convex collider, and a Unity glTF
export.

The budgets that matter here are the ones a sled fails invisibly. A sled
stands on its two shoes, not on its deck: an AABB that touches the floor
says nothing about whether *each* shoe does. The deck rides on tenoned
posts and seated slats, and the rope has to pass through the bar's hole
rather than through the bar. The piece measures each off the finished
mesh.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-shoe`` the named shoes,
``--short-post`` the post tenons, ``--short-bar`` the bar's protrusion,
``--float-slats`` the slat seat, ``--lift-runners`` the shoe seat,
``--float-bolts`` the bolt seat, ``--float-screws`` the screw seat, ``--miss-hole`` the rope in its hole,
``--tall-posts`` the real-world deck height, ``--skew-runner`` the
mirrored runners.

No randomness. DECIMATE COLLAPSE triangle counts are not byte-identical
across Blender versions — the LOD gate is a ratio band.

    blender --background --python toboggan.py --
    blender --background --python toboggan.py -- --miss-hole
    blender --background --python toboggan.py -- --output toboggan.webp
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
import gallery_asset_quality  # noqa: E402
import gallery_framing  # noqa: E402

# Frame: +X is the front of the sled, Y runs across it, Z is up, Z = 0 is
# the floor the shoes stand on.

# Runners: a chamfered timber on edge, swept along a curve that is flat
# under the deck and rises into a front horn and a short rear tail. The
# curve and its slope are closed-form, so the shoe and the body are
# parallel offsets of one centreline. The tail is a small kick-up only: a
# runner sled's back is cut off nearly flat.
RUN_Y = 0.150
RUN_HALF = 0.600
HORN_X0 = 0.280
HORN_RISE = 0.210
HORN_POW = 2.5
TAIL_X0 = -0.500
TAIL_RISE = 0.008
TAIL_POW = 2.0
RUN_STATIONS = 36
RUN_HW = 0.014
RUN_HH = 0.027
RUN_CH = 0.004

# Steel shoe: a flat strap under each runner, wider than the timber.
SHOE_HW = 0.017
SHOE_HH = 0.0045
SHOE_CH = 0.0015
SHOE_BITE = 0.0015
BODY_D = 2.0 * SHOE_HH - SHOE_BITE + RUN_HH
BODY_TOP = BODY_D + RUN_HH

# Posts, bearers, slats. The post tenons into the runner and into the
# bearer; the slat is rebated into the bearer.
POST_X = (-0.400, -0.040, 0.260)
POST_HX = 0.014
POST_HY = 0.012
POST_CH = 0.003
POST_BITE = 0.010
POST_TENON = 0.012
BEAR_HALF = 0.190
BEAR_HX = 0.020
BEAR_HZ = 0.0175
BEAR_CH = 0.004
SLAT_N = 7
SLAT_PITCH = 0.0605
SLAT_HW = 0.027
SLAT_HH = 0.008
SLAT_CH = 0.0025
SLAT_X0 = -0.520
SLAT_X1 = 0.420
SLAT_SEAT = 0.003
DECK_TOP = 0.145
BEAR_TOP = DECK_TOP - 2.0 * SLAT_HH + SLAT_SEAT
BEAR_ZC = BEAR_TOP - BEAR_HZ
BEAR_BOT = BEAR_ZC - BEAR_HZ

# Steering bar: one painted crossbar through both runner horns, proud of
# each, drilled through at its centre for the pull rope; a knot behind it.
BAR_X = 0.500
BAR_HX = 0.016
BAR_HZ = 0.018
BAR_CH = 0.010
BAR_PROT = 0.070
HOLE_R = 0.011
# Three-strand hemp: the section's radius swells along three helical
# strands, so the lay reads in the silhouette, not only in the shading.
ROPE_R = 0.006
ROPE_SEG = 12
ROPE_STEP = 0.006
LAY_AMP = 0.14
LAY_PITCH = 0.036
ROPE_RMAX = ROPE_R * (1.0 + LAY_AMP)
KNOT_R = 0.0165
KNOT_C = 0.010
TOGGLE_HALF = 0.050
TOGGLE_H = 0.009
DROP_X = 0.25
CURL_R = 0.22
CURL_A = math.radians(85.0)

# A domed screw head through each slat into every bearer it crosses,
# phase-turned per screw so no two heads share a facet plane.
SCREW_PROFILE = ((0.0042, 0.0004), (0.0035, 0.0013))
SCREW_TIP = 0.0018
SCREW_BITE = 0.0006
SCREW_SEG = 8

# Carriage bolts through each runner at every post.
BOLT_BITE = 0.0010
BOLT_PROFILE = ((0.0095, 0.0), (0.0095, 0.0015), (0.0085, 0.0028), (0.0060, 0.0042),
                (0.0030, 0.0050))
BOLT_TIP = 0.0054

# Falsifier displacements. Each stays inside BBOX_TOL.
FLOAT_SHOE = 0.006
SHORT_POST = -0.004
SHORT_BAR = 0.019
FLOAT_SLATS = 0.005
LIFT_RUNNERS = 0.004
FLOAT_BOLTS = 0.0035
FLOAT_SCREWS = 0.003
MISS_HOLE = 0.012
TALL_POSTS = 0.040
SKEW_RUNNER = 0.006

BBOX_TOL = 0.020
OUTER_SIZE = (1.623, 0.468, 0.243)

BASE_TRIS_MIN = 7050
BASE_TRIS_MAX = 7650
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 5
FACE_FLOORS = {0: 230, 1: 770, 2: 1450, 3: 1300, 4: 44}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 720
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
SHOE_Z_MAX = 1e-4
POST_BITE_MIN = 0.005
POST_BITE_MAX = 0.016
POST_TENON_MIN = 0.006
POST_TENON_MAX = 0.018
POST_CLEAR_MIN = 0.012
BAR_PROT_MIN = 0.055
BAR_PROT_MAX = 0.085
SLAT_SEAT_MIN = 0.0015
SLAT_SEAT_MAX = 0.0045
SHOE_SEAT_MIN = 0.0005
SHOE_SEAT_MAX = 0.0025
BOLT_PROUD_MIN = 0.0030
BOLT_PROUD_MAX = 0.0060
BOLT_BITE_MIN = 0.0005
BOLT_BITE_MAX = 0.0020
SCREW_BITE_MIN = 0.0003
SCREW_BITE_MAX = 0.0012
SCREW_PROUD_MIN = 0.0008
SCREW_PROUD_MAX = 0.0020
ROPE_CLEAR_MIN = 0.0005
ROPE_CLEAR_MAX = 0.0060
RUNNER_LEN = (1.15, 1.25)
DECK_LEN = (0.90, 0.98)
DECK_W = (0.40, 0.44)
DECK_H = (0.130, 0.155)
TRACK = (0.29, 0.31)
MIRROR_EPS = 1e-4

SLAT_IDX = 0
FRAME_IDX = 1
STEEL_IDX = 2
ROPE_IDX = 3
PAINT_IDX = 4

# Hero camera: front three-quarter, low, the rope curling toward the viewer.
CAM_YAW = 0.0
CAM_LENS = 50.0
CAM_LOC = (1.62, -1.50, 0.68)
CAM_AIM = (0.30, -0.10, 0.04)

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
    # PlankTone spans 0.35..0.65, so each piece lands 0.73..1.33 of the ramp:
    # neighbouring slats read as different boards, not one sheet.
    gain.inputs[1].default_value = 2.0
    gain.inputs[2].default_value = 0.03
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


def assign_slots(obj, mats):
    slots = obj.data.materials
    for i, mat in enumerate(mats):
        if i < len(slots):
            slots[i] = mat
        else:
            slots.append(mat)


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


# --- runner curve -----------------------------------------------------------


def hump(x):
    """Centreline height and slope at ``x``: flat under the deck, a horn in front, a tail behind."""
    if x > HORN_X0:
        span = RUN_HALF - HORN_X0
        u = (x - HORN_X0) / span
        return HORN_RISE * u ** HORN_POW, HORN_RISE * HORN_POW * u ** (HORN_POW - 1.0) / span
    if x < TAIL_X0:
        span = TAIL_X0 + RUN_HALF
        u = (TAIL_X0 - x) / span
        return TAIL_RISE * u ** TAIL_POW, -TAIL_RISE * TAIL_POW * u ** (TAIL_POW - 1.0) / span
    return 0.0, 0.0


def offset_pt(x, d):
    """Point ``d`` off the centreline along its normal, in the XZ plane (y = 0)."""
    f, df = hump(x)
    k = 1.0 / math.hypot(1.0, df)
    return Vector((x - d * df * k, 0.0, f + d * k))


def runner_stations():
    xs = {round(-RUN_HALF + 2.0 * RUN_HALF * k / RUN_STATIONS, 6) for k in range(RUN_STATIONS + 1)}
    xs |= {HORN_X0, TAIL_X0, BAR_X}
    return sorted(xs)


# --- construction -----------------------------------------------------------


def section8(hw, hh, ch):
    """A rectangle with its four corners chamfered: eight (side, up) offsets."""
    return [(hw - ch, hh), (hw, hh - ch), (hw, -(hh - ch)), (hw - ch, -hh),
            (-(hw - ch), -hh), (-hw, -(hh - ch)), (-hw, hh - ch), (-(hw - ch), hh)]


def section_round(hw, hh, r, steps=2):
    """A rectangle with its four corners rounded: ``steps`` + 1 points per quarter arc."""
    out = []
    for cx, cy, a0 in ((hw - r, hh - r, 90.0), (hw - r, -(hh - r), 0.0),
                       (-(hw - r), -(hh - r), -90.0), (-(hw - r), hh - r, -180.0)):
        for k in range(steps + 1):
            a = math.radians(a0 - 90.0 * k / steps)
            out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def member(bm, ctx, pts, side, hw, hh, ch, mat, grain, reach=0.0015, sec=None):
    """Chamfered-rectangle section swept along ``pts``.

    ``side`` is the direction the section's width ``hw`` runs in; ``up`` is
    ``t x side``, so a path along +X with side +Y has its height along +Z.
    Ends close on a pole a hair past the last ring, so every cap is a fan
    of triangles rather than an n-gon.
    """
    m = len(pts)
    tans = [(pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(m)]
    sec = sec or section8(hw, hh, ch)
    rings = []
    for p, t in zip(pts, tans):
        s = (side - t * side.dot(t)).normalized()
        u = t.cross(s)
        rings.append([bm.verts.new(p + s * a + u * b) for a, b in sec])
    poles = (bm.verts.new(pts[0] - tans[0] * reach), bm.verts.new(pts[-1] + tans[-1] * reach))
    tube(bm, rings, poles, mat, ctx, [grain] * m)


def resample(pts, step):
    """The polyline ``pts`` re-cut at an even arc-length ``step``, ends kept."""
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + (b - a).length)
    n = max(2, round(acc[-1] / step))
    out, j = [], 0
    for k in range(n + 1):
        s = acc[-1] * k / n
        while j < len(pts) - 2 and acc[j + 1] < s:
            j += 1
        f = (s - acc[j]) / max(acc[j + 1] - acc[j], 1e-12)
        out.append(pts[j].lerp(pts[j + 1], min(max(f, 0.0), 1.0)))
    return out


def rope_sweep(bm, ctx, pts, radius, seg, mat):
    """Three-strand rope swept along a 3D path with a parallel-transport frame.

    The section radius swells along three helical strands; the ``Lay``
    point attribute carries the same phase so the shader darkens the
    grooves between strands.
    """
    lay = ctx["lay"]
    m = len(pts)
    tans = [(pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(m)]
    n = Vector((0.0, 0.0, 1.0))
    rings, grains = [], []
    s = 0.0
    for i, (p, t) in enumerate(zip(pts, tans)):
        if i:
            s += (p - pts[i - 1]).length
        n = (n - t * n.dot(t)).normalized()
        b = t.cross(n)
        ring = []
        for k in range(seg):
            th = 2 * math.pi * k / seg
            c = math.cos(3.0 * th - 2.0 * math.pi * s / LAY_PITCH)
            r = radius * (1.0 + LAY_AMP * c)
            v = bm.verts.new(p + n * (r * math.cos(th)) + b * (r * math.sin(th)))
            v[lay] = 0.5 + 0.5 * c
            ring.append(v)
        rings.append(ring)
        grains.append(tuple(t))
    poles = (bm.verts.new(pts[0] - tans[0] * (0.5 * radius)),
             bm.verts.new(pts[-1] + tans[-1] * (0.5 * radius)))
    tube(bm, rings, poles, mat, ctx, grains)


def add_knot(bm, ctx, centre, radius, mat, rows=7, seg=10):
    """A stopper knot: a sphere on latitudinal rings about the X axis."""
    rings = []
    for k in range(1, rows + 1):
        phi = math.pi * k / (rows + 1)
        x = -radius * math.cos(phi)
        r = radius * math.sin(phi)
        rings.append([bm.verts.new(centre + Vector((x, r * math.cos(2 * math.pi * i / seg),
                                                    r * math.sin(2 * math.pi * i / seg))))
                      for i in range(seg)])
    poles = (bm.verts.new(centre + Vector((-radius, 0.0, 0.0))),
             bm.verts.new(centre + Vector((radius, 0.0, 0.0))))
    tube(bm, rings, poles, mat, ctx, [(0.0, 1.0, 0.0)] * len(rings))


def add_bar(bm, ctx, centre, hy, mat, short=0.0):
    """One crossbar drilled through along X at its centre: a chamfered
    rectangle ring of half-span ``hy`` around a 12-gon hole. ``short`` pulls
    the -Y end in by that much and leaves the +Y end where it is.

    Four strips (front ring, back ring, outer wall, hole wall), each quad a
    cell of a UV row, so no two faces share UV area.
    """
    hz, c = BAR_HZ, BAR_CH
    outer = [(hy, 0.0), (hy, hz - c), (hy - c, hz), (0.0, hz), (-(hy - c), hz), (-hy, hz - c),
             (-hy, 0.0), (-hy, -(hz - c)), (-(hy - c), -hz), (0.0, -hz), (hy - c, -hz),
             (hy, -(hz - c))]
    n = len(outer)
    inner = [(HOLE_R * math.cos(2 * math.pi * k / n), HOLE_R * math.sin(2 * math.pi * k / n))
             for k in range(n)]

    def ring(pts, dx):
        return [bm.verts.new(centre + Vector((dx, a + (short if a < -HOLE_R else 0.0), b)))
                for a, b in pts]

    of, ob = ring(outer, BAR_HX), ring(outer, -BAR_HX)
    inf, inb = ring(inner, BAR_HX), ring(inner, -BAR_HX)
    island = new_island(ctx)

    def strip(row, quads):
        for i, vs in enumerate(quads):
            f = bm.faces.new(vs)
            f.material_index = mat
            u0, u1, v0, v1 = i / n, (i + 1) / n, row / 4.0, (row + 1) / 4.0
            stamp(ctx, f, island, {vs[0]: (u0, v0), vs[1]: (u1, v0), vs[2]: (u1, v1),
                                   vs[3]: (u0, v1)}, (0.0, 1.0, 0.0))

    j = lambda i: (i + 1) % n  # noqa: E731
    strip(0, [(of[i], of[j(i)], inf[j(i)], inf[i]) for i in range(n)])
    strip(1, [(ob[i], ob[j(i)], inb[j(i)], inb[i]) for i in range(n)])
    strip(2, [(of[i], of[j(i)], ob[j(i)], ob[i]) for i in range(n)])
    strip(3, [(inf[i], inf[j(i)], inb[j(i)], inb[i]) for i in range(n)])


def lathe_axis(bm, profile, n, mat, ctx, origin, sign):
    """Revolve an (r, t) profile about an axis along ``sign`` * Y from ``origin``."""
    xf = Matrix.Translation(origin) @ Matrix.Rotation(-sign * math.pi / 2.0, 4, "X")
    rings, poles = [], []
    for p in profile:
        if p.x <= 0.0:
            poles.append(bm.verts.new(xf @ Vector((0.0, 0.0, p.y))))
        else:
            rings.append([bm.verts.new(xf @ Vector((p.x * math.cos(2 * math.pi * k / n),
                                                     p.x * math.sin(2 * math.pi * k / n), p.y)))
                          for k in range(n)])
    tube(bm, rings, poles, mat, ctx, [(0.0, 1.0, 0.0)] * len(rings))


def lathe_z(bm, profile, n, mat, ctx, origin, phase):
    """Revolve an (r, z) profile about +Z from ``origin``, turned by ``phase``."""
    rings, poles = [], []
    for p in profile:
        if p.x <= 0.0:
            poles.append(bm.verts.new(origin + Vector((0.0, 0.0, p.y))))
        else:
            rings.append([bm.verts.new(origin + Vector((
                p.x * math.cos(phase + 2 * math.pi * k / n),
                p.x * math.sin(phase + 2 * math.pi * k / n), p.y))) for k in range(n)])
    tube(bm, rings, poles, mat, ctx, [(0.0, 0.0, 1.0)] * len(rings))


def screw_profile():
    return ([Vector((0.0, 0.0))] + [Vector(p) for p in SCREW_PROFILE]
            + [Vector((0.0, SCREW_TIP))])


def bolt_profile():
    return ([Vector((0.0, 0.0))] + [Vector(p) for p in BOLT_PROFILE]
            + [Vector((0.0, BOLT_TIP))])


def rope_path(hx, hz, lift):
    """Knot, through the hole, a sag to the floor, then a curl lying on it."""
    kx = hx - BAR_HX - KNOT_C
    pts = [Vector((kx + 0.015 * k, 0.0, hz)) for k in range(4)]
    x_s = hx + BAR_HX + 0.01
    while pts[-1].x < x_s - 0.0075:
        pts.append(Vector((pts[-1].x + 0.015, 0.0, hz)))
    if x_s - pts[-1].x > 1e-4:
        pts.append(Vector((x_s, 0.0, hz)))
    steps = 12
    for k in range(1, steps + 1):
        s = k / steps
        sm = s * s * (3.0 - 2.0 * s)
        pts.append(Vector((x_s + DROP_X * s, 0.0, hz + (ROPE_RMAX - hz) * sm)))
    x_e = x_s + DROP_X
    arcs = 18
    for k in range(1, arcs + 1):
        th = CURL_A * k / arcs
        pts.append(Vector((x_e + CURL_R * math.sin(th), -CURL_R * (1.0 - math.cos(th)), ROPE_RMAX)))
    return [p + Vector((0.0, 0.0, lift)) for p in resample(pts, ROPE_STEP)], kx


def build_sled_mesh(
    name,
    stray_vert=False,
    float_shoe=False,
    short_post=False,
    short_bar=False,
    float_slats=False,
    lift_runners=False,
    miss_hole=False,
    float_bolts=False,
    float_screws=False,
    tall_posts=False,
    skew_runner=False,
):
    bm = bmesh.new()
    try:
        ctx = {"uv": bm.loops.layers.uv.new("UVMap"),
               "isl": bm.faces.layers.int.new("UVIsland"),
               "gx": bm.faces.layers.float.new("gx"),
               "gy": bm.faces.layers.float.new("gy"),
               "gz": bm.faces.layers.float.new("gz"),
               "lay": bm.verts.layers.float.new("Lay"), "next": 0}
        xs = runner_stations()
        raise_by = TALL_POSTS if tall_posts else 0.0
        for side in (-1.0, 1.0):
            y = side * RUN_Y
            dx = SKEW_RUNNER if (skew_runner and side < 0) else 0.0
            shoe_lift = FLOAT_SHOE if (float_shoe and side < 0) else 0.0
            body_lift = LIFT_RUNNERS if lift_runners else 0.0
            shoe = [offset_pt(x, SHOE_HH) + Vector((dx, y, shoe_lift)) for x in xs]
            body = [offset_pt(x, BODY_D + body_lift) + Vector((dx, y, 0.0)) for x in xs]
            member(bm, ctx, shoe, Vector((0.0, 1.0, 0.0)), SHOE_HW, SHOE_HH, SHOE_CH,
                   STEEL_IDX, (1.0, 0.0, 0.0))
            member(bm, ctx, body, Vector((0.0, 1.0, 0.0)), RUN_HW, RUN_HH, RUN_CH,
                   FRAME_IDX, (1.0, 0.0, 0.0))
            # Posts: tenoned into the runner below and the bearer above.
            z_bot = BODY_TOP - (SHORT_POST if short_post else POST_BITE)
            z_top = BEAR_BOT + raise_by + POST_TENON
            for px in POST_X:
                member(bm, ctx, [Vector((px, y, z_bot)), Vector((px, y, z_top))],
                       Vector((1.0, 0.0, 0.0)), POST_HX, POST_HY, POST_CH, FRAME_IDX,
                       (0.0, 0.0, 1.0))
            # Bolts through the runner and into the post, heads on the outer face.
            face = RUN_Y + RUN_HW
            shift = FLOAT_BOLTS if float_bolts else 0.0
            for px in POST_X:
                lathe_axis(bm, bolt_profile(), 12, STEEL_IDX, ctx,
                           Vector((px + dx, side * (face - BOLT_BITE + shift), BODY_D)), side)
        for px in POST_X:
            member(bm, ctx, [Vector((px, -BEAR_HALF, BEAR_ZC + raise_by)),
                             Vector((px, BEAR_HALF, BEAR_ZC + raise_by))],
                   Vector((1.0, 0.0, 0.0)), BEAR_HX, BEAR_HZ, BEAR_CH, FRAME_IDX,
                   (0.0, 1.0, 0.0))
        slat_z = DECK_TOP - SLAT_HH + raise_by + (FLOAT_SLATS if float_slats else 0.0)
        slat_sec = section_round(SLAT_HW, SLAT_HH, SLAT_CH)
        screw_z = slat_z + SLAT_HH - SCREW_BITE + (FLOAT_SCREWS if float_screws else 0.0)
        for k in range(SLAT_N):
            y = (k - (SLAT_N - 1) / 2.0) * SLAT_PITCH
            member(bm, ctx, [Vector((SLAT_X0, y, slat_z)), Vector((SLAT_X1, y, slat_z))],
                   Vector((0.0, 1.0, 0.0)), SLAT_HW, SLAT_HH, SLAT_CH, SLAT_IDX,
                   (1.0, 0.0, 0.0), sec=slat_sec)
            for j, px in enumerate(POST_X):
                lathe_z(bm, screw_profile(), SCREW_SEG, STEEL_IDX, ctx,
                        Vector((px, y, screw_z)), 2.39996 * (k * len(POST_X) + j))
        # One steering bar through both horns, drilled at its centre for the rope.
        bp = offset_pt(BAR_X, BODY_D)
        hx, hz = bp.x, bp.z
        add_bar(bm, ctx, Vector((hx, 0.0, hz)), RUN_Y + RUN_HW + BAR_PROT, PAINT_IDX,
                short=SHORT_BAR if short_bar else 0.0)
        pts, kx = rope_path(hx, hz, MISS_HOLE if miss_hole else 0.0)
        rope_sweep(bm, ctx, pts, ROPE_R, ROPE_SEG, ROPE_IDX)
        # A wooden toggle across the rope's end, lying on the floor.
        tip = pts[-1] - Vector((0.0, 0.0, pts[-1].z - TOGGLE_H))
        tang = (pts[-1] - pts[-2]).normalized()
        across = Vector((-tang.y, tang.x, 0.0)).normalized()
        member(bm, ctx, [tip - across * TOGGLE_HALF, tip + across * TOGGLE_HALF], tang,
               TOGGLE_H, TOGGLE_H, 0.003, FRAME_IDX, tuple(across))
        add_knot(bm, ctx, Vector((kx, 0.0, hz + (MISS_HOLE if miss_hole else 0.0))),
                 KNOT_R, ROPE_IDX)
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


def steel_material(name):
    """Bright worn strap steel, dulled and speckled with rust. Not chrome."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 55.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.42
    ramp.color_ramp.elements[0].color = (0.30, 0.30, 0.32, 1.0)
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = (0.17, 0.085, 0.045, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.85
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.30
    rough.inputs["To Max"].default_value = 0.62
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def paint_material(name):
    """Enamel red, worn to a darker undercoat in patches."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 22.0
    noise.inputs["Detail"].default_value = 9.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.40
    ramp.color_ramp.elements[0].color = (0.40, 0.030, 0.022, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.60, 0.060, 0.040, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.38
    rough.inputs["To Max"].default_value = 0.62
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def rope_material(name):
    """Hemp: diagonal lay lines from the rope's own UVs, so the twist follows the strand."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "DIAGONAL"
    wave.wave_profile = "SIN"
    wave.inputs["Scale"].default_value = 70.0
    wave.inputs["Distortion"].default_value = 2.5
    wave.inputs["Detail"].default_value = 2.0
    nt.links.new(tc.outputs["UV"], wave.inputs["Vector"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 160.0
    noise.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    mixf = nt.nodes.new("ShaderNodeMath")
    mixf.operation = "MULTIPLY_ADD"
    mixf.inputs[1].default_value = 0.35
    nt.links.new(wave.outputs["Fac"], mixf.inputs[0])
    nt.links.new(noise.outputs["Fac"], mixf.inputs[2])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.20, 0.14, 0.065, 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (0.58, 0.45, 0.25, 1.0)
    nt.links.new(mixf.outputs["Value"], ramp.inputs["Fac"])
    # ``Lay`` is 1 on a strand's crown and 0 in the groove between strands.
    lay = nt.nodes.new("ShaderNodeAttribute")
    lay.attribute_name = "Lay"
    shade = nt.nodes.new("ShaderNodeMath")
    shade.operation = "MULTIPLY_ADD"
    shade.inputs[1].default_value = 0.65
    shade.inputs[2].default_value = 0.35
    nt.links.new(lay.outputs["Fac"], shade.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(ramp.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(shade.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    return mat


def sled_materials():
    return (
        wood_material("SledSlat", (0.20, 0.105, 0.040), (0.56, 0.34, 0.15), rough=(0.50, 0.68)),
        wood_material("SledFrame", (0.075, 0.036, 0.016), (0.24, 0.125, 0.055), rough=(0.62, 0.80)),
        steel_material("SledSteel"),
        rope_material("SledRope"),
        paint_material("SledPaint"),
    )


def classify(me):
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    out = {k: [] for k in ("slat", "runner", "post", "bearer", "shoe", "bolt", "screw", "bar",
                           "rope", "knot", "toggle", "other")}
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        rec = {"g": g, "pts": pts, "lo": lo, "hi": hi, "ext": hi - lo,
               "c": sum(pts, Vector()) / len(pts)}
        m = mats.get(g[0], -1)
        e = rec["ext"]
        if m == SLAT_IDX:
            out["slat"].append(rec)
        elif m == FRAME_IDX:
            out["toggle" if e.z < 0.03 else "runner" if e.x > 0.8 else "bearer" if e.y > 0.3
                else "post"].append(rec)
        elif m == STEEL_IDX:
            out["shoe" if e.x > 0.8 else "screw" if e.z < 0.006 else "bolt"].append(rec)
        elif m == PAINT_IDX:
            out["bar"].append(rec)
        elif m == ROPE_IDX:
            out["rope" if e.x > 0.1 else "knot"].append(rec)
        else:
            out["other"].append(rec)
    return out


def sled_audit(me):
    parts = classify(me)
    out = {k: len(v) for k, v in parts.items()}
    runners = sorted(parts["runner"], key=lambda r: r["c"].y)
    shoes = sorted(parts["shoe"], key=lambda r: r["c"].y)

    def runner_for(y):
        return min(runners, key=lambda r: abs(r["c"].y - y)) if runners else None

    def top_near(rec, x, half=0.02):
        zs = [p.z for p in rec["pts"] if abs(p.x - x) < half]
        return max(zs) if zs else None

    # Each shoe is a named support: it stands on the floor by itself.
    out["shoe_z"] = max((r["lo"].z for r in shoes), default=99.0)

    # Posts: tenoned into the runner below and the bearer above, clear of the slats.
    bites, tenons, clears = [], [], []
    for post in parts["post"]:
        run = runner_for(post["c"].y)
        bear = min(parts["bearer"], key=lambda b: abs(b["c"].x - post["c"].x), default=None)
        top = top_near(run, post["c"].x) if run else None
        if top is None or bear is None:
            continue
        bites.append(top - post["lo"].z)
        tenons.append(post["hi"].z - bear["lo"].z)
        clears.append(bear["hi"].z - post["hi"].z)
    out["post_bite"] = (min(bites, default=-99.0), max(bites, default=99.0))
    out["post_tenon"] = (min(tenons, default=-99.0), max(tenons, default=99.0))
    out["post_clear"] = min(clears, default=-99.0)

    # The steering bar passes through both runners and stands proud of each outer face.
    prot = []
    if parts["bar"] and len(runners) == 2:
        bar = parts["bar"][0]
        prot = [runners[0]["lo"].y - bar["lo"].y, bar["hi"].y - runners[1]["hi"].y]
    out["bar_prot"] = (min(prot, default=-99.0), max(prot, default=99.0))

    # Slats are rebated into every bearer they cross.
    seats = []
    for s in parts["slat"]:
        for b in parts["bearer"]:
            if s["lo"].x < b["c"].x < s["hi"].x and b["lo"].y < s["c"].y < b["hi"].y:
                seats.append(b["hi"].z - s["lo"].z)
    out["slat_joints"] = len(seats)
    out["slat_seat"] = (min(seats, default=-99.0), max(seats, default=99.0))

    # A screw head at every slat-bearer joint: biting the slat, domed proud of it.
    sbite, sproud = [], []
    for sc in parts["screw"]:
        slat = next((s for s in parts["slat"] if s["lo"].x < sc["c"].x < s["hi"].x
                     and s["lo"].y < sc["c"].y < s["hi"].y), None)
        bear = next((b for b in parts["bearer"] if b["lo"].x < sc["c"].x < b["hi"].x), None)
        if slat is None or bear is None:
            continue
        sbite.append(slat["hi"].z - sc["lo"].z)
        sproud.append(sc["hi"].z - slat["hi"].z)
    out["screw_joints"] = len(sbite)
    out["screw_bite"] = (min(sbite, default=-99.0), max(sbite, default=99.0))
    out["screw_proud"] = (min(sproud, default=-99.0), max(sproud, default=99.0))

    # The steel shoe is seated up into its runner, measured on the flat run.
    sseat = []
    for sh in shoes:
        run = runner_for(sh["c"].y)
        flat_s = [p.z for p in sh["pts"] if abs(p.x) < 0.1]
        flat_r = [p.z for p in run["pts"] if abs(p.x) < 0.1] if run else []
        if flat_s and flat_r:
            sseat.append(max(flat_s) - min(flat_r))
    out["shoe_seat"] = (min(sseat, default=-99.0), max(sseat, default=99.0))

    # Bolt heads stand proud of the runner's outer face and bite into it.
    proud, bite = [], []
    for b in parts["bolt"]:
        run = runner_for(b["c"].y)
        if run is None:
            continue
        if b["c"].y > 0:
            proud.append(b["hi"].y - run["hi"].y)
            bite.append(run["hi"].y - b["lo"].y)
        else:
            proud.append(run["lo"].y - b["lo"].y)
            bite.append(b["hi"].y - run["lo"].y)
    out["bolt_proud"] = (min(proud, default=-99.0), max(proud, default=99.0))
    out["bolt_bite"] = (min(bite, default=-99.0), max(bite, default=99.0))

    # The rope passes through the bar's centre hole, with room to spare.
    out["rope_clear"] = -99.0
    out["hole_r"] = 0.0
    out["rope_inside"] = 0
    if parts["bar"] and parts["rope"]:
        bar, rope = parts["bar"][0], parts["rope"][0]
        cy, cz = (bar["lo"].y + bar["hi"].y) * 0.5, (bar["lo"].z + bar["hi"].z) * 0.5
        lim = 0.75 * bar["ext"].z * 0.5
        ring = [math.hypot(p.y - cy, p.z - cz) for p in bar["pts"]
                if math.hypot(p.y - cy, p.z - cz) < lim]
        inside = [math.hypot(p.y - cy, p.z - cz) for p in rope["pts"]
                  if bar["lo"].x <= p.x <= bar["hi"].x]
        out["rope_inside"] = len(inside)
        if ring and inside:
            out["hole_r"] = sum(ring) / len(ring)
            out["rope_clear"] = out["hole_r"] - max(inside)

    # Real-world size, read off the parts rather than the outer AABB.
    out["runner_len"] = (min((r["ext"].x for r in runners), default=-99.0),
                         max((r["ext"].x for r in runners), default=99.0))
    slats = parts["slat"]
    out["deck_len"] = (max(s["hi"].x for s in slats) - min(s["lo"].x for s in slats)) if slats else 0.0
    out["deck_w"] = (max(s["hi"].y for s in slats) - min(s["lo"].y for s in slats)) if slats else 0.0
    out["deck_h"] = max((s["hi"].z for s in slats), default=0.0)
    out["track"] = (runners[1]["c"].y - runners[0]["c"].y) if len(runners) == 2 else 0.0

    # Mirrored runners and shoes: one the image of the other through y = 0.
    mirror = 0.0
    for pair in (runners, shoes):
        if len(pair) != 2:
            mirror = 99.0
            continue
        a, b = pair
        mirror = max(mirror, abs(a["lo"].x - b["lo"].x), abs(a["hi"].x - b["hi"].x),
                     abs(a["lo"].z - b["lo"].z), abs(a["hi"].z - b["hi"].z),
                     abs(a["lo"].y + b["hi"].y), abs(a["hi"].y + b["lo"].y))
    out["mirror"] = mirror
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


def ring_near(me, group, seg, x):
    """Index of the swept ring of ``group`` whose centroid is nearest ``x``."""
    body = sorted(group)[:-2]
    return min(range(len(body) // seg),
               key=lambda r: abs(sum(me.vertices[body[r * seg + k]].co.x for k in range(seg)) / seg - x))


def ring_slice(me, group, seg, r0, r1, first, last):
    order = sorted(group)
    body, poles = order[:-2], order[-2:]
    pts = [me.vertices[body[r * seg + k]].co.copy() for r in range(r0, r1 + 1) for k in range(seg)]
    if first:
        pts.append(me.vertices[poles[0]].co.copy())
    if last:
        pts.append(me.vertices[poles[1]].co.copy())
    return pts


def hull_collider(obj, name):
    """Compound collider: four hulls per runner, one for the deck, one for the bar.

    A runner is a curve, so one hull would fill the wedge under its horn.
    Each hull is taken over a run of whole rings of the timber and its shoe,
    boundary rings shared, so the slices tile the curve without a gap.
    """
    me = obj.data
    parts = classify(me)
    groups = []
    shoes = sorted(parts["shoe"], key=lambda r: r["c"].y)
    for run in sorted(parts["runner"], key=lambda r: r["c"].y):
        shoe = min(shoes, key=lambda s: abs(s["c"].y - run["c"].y))
        n = len(sorted(run["g"])[:-2]) // 8
        cuts = [0, ring_near(me, run["g"], 8, -0.40), ring_near(me, run["g"], 8, HORN_X0),
                ring_near(me, run["g"], 8, 0.44), n - 1]
        for a, b in zip(cuts, cuts[1:]):
            groups.append(ring_slice(me, run["g"], 8, a, b, a == 0, b == n - 1)
                          + ring_slice(me, shoe["g"], 8, a, b, a == 0, b == n - 1))
    deck = [p for rec in parts["slat"] + parts["bearer"] for p in rec["pts"]]
    groups.append(deck)
    groups.append([p for rec in parts["bar"] for p in rec["pts"]])
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
    img = bpy.data.images.new("SledNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = FRAME_IDX
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
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_yup=True,
                              export_apply=True, export_draco_mesh_compression_enable=False,
                              export_animations=False)


def wire_normal(mat, tex):
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])


def check(skip_decimate, lift_z=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_sled_mesh("SledLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_sled_mesh("SledHigh", **hi_flags)
    mats = sled_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        _co = [0.0] * (len(low.data.vertices) * 3)
        low.data.vertices.foreach_get("co", _co)
        _co[2::3] = [z + LIFT_Z for z in _co[2::3]]
        low.data.vertices.foreach_set("co", _co)
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("sled mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[FRAME_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "SledLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "SledLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(high, "SledCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_sled_{os.getpid()}.glb")
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
    sa = sled_audit(low.data)

    def rng(t):
        return f"({t[0]:.5f},{t[1]:.5f})"

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
    print(f"measured parts slats={sa['slat']} runners={sa['runner']} posts={sa['post']} "
          f"bearers={sa['bearer']} shoes={sa['shoe']} bolts={sa['bolt']} screws={sa['screw']} "
          f"bar={sa['bar']} rope={sa['rope']} knot={sa['knot']} other={sa['other']} "
          f"shoe_z={sa['shoe_z']:.5f}")
    print(f"measured joints post_bite={rng(sa['post_bite'])} post_tenon={rng(sa['post_tenon'])} "
          f"post_clear={sa['post_clear']:.5f} bar_prot={rng(sa['bar_prot'])}")
    print(f"measured seats slat_joints={sa['slat_joints']} slat_seat={rng(sa['slat_seat'])} "
          f"shoe_seat={rng(sa['shoe_seat'])} bolt_proud={rng(sa['bolt_proud'])} "
          f"bolt_bite={rng(sa['bolt_bite'])} screw_joints={sa['screw_joints']} "
          f"screw_bite={rng(sa['screw_bite'])} screw_proud={rng(sa['screw_proud'])}")
    print(f"measured rope hole_r={sa['hole_r']:.5f} clear={sa['rope_clear']:.5f} "
          f"rings_in_bar={sa['rope_inside']}")
    print(f"measured size runner_len={rng(sa['runner_len'])} deck_len={sa['deck_len']:.4f} "
          f"deck_w={sa['deck_w']:.4f} deck_h={sa['deck_h']:.4f} track={sa['track']:.4f} "
          f"mirror={sa['mirror']:.6f}")

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
    if sa["shoe"] != 2 or sa["shoe_z"] > SHOE_Z_MAX:
        return (fail(f"shoes: {sa['shoe']} of 2, worst shoe zmin={sa['shoe_z']:.5f} > {SHOE_Z_MAX} "
                     "(--float-shoe is the designed fail)", 16),) + nothing
    if (sa["post"] != 6 or sa["bearer"] != 3 or sa["post_bite"][0] < POST_BITE_MIN
            or sa["post_bite"][1] > POST_BITE_MAX):
        return (fail(f"{sa['post']} of 6 posts, bite into the runner {sa['post_bite']} outside "
                     f"[{POST_BITE_MIN}, {POST_BITE_MAX}] (--short-post is the designed fail)",
                     17),) + nothing
    if (sa["post_tenon"][0] < POST_TENON_MIN or sa["post_tenon"][1] > POST_TENON_MAX
            or sa["post_clear"] < POST_CLEAR_MIN):
        return (fail(f"post tenon into the bearer {sa['post_tenon']} outside "
                     f"[{POST_TENON_MIN}, {POST_TENON_MAX}], clear of the slats "
                     f"{sa['post_clear']:.5f} < {POST_CLEAR_MIN}", 17),) + nothing
    if sa["bar"] != 1 or sa["bar_prot"][0] < BAR_PROT_MIN or sa["bar_prot"][1] > BAR_PROT_MAX:
        return (fail(f"{sa['bar']} of 1 steering bar, protrusion past the runner {sa['bar_prot']} "
                     f"outside [{BAR_PROT_MIN}, {BAR_PROT_MAX}] (--short-bar is the designed fail)",
                     17),) + nothing
    if (sa["slat"] != SLAT_N or sa["slat_joints"] != SLAT_N * len(POST_X)
            or sa["slat_seat"][0] < SLAT_SEAT_MIN or sa["slat_seat"][1] > SLAT_SEAT_MAX):
        return (fail(f"{sa['slat']} of {SLAT_N} slats, {sa['slat_joints']} joints, seat "
                     f"{sa['slat_seat']} outside [{SLAT_SEAT_MIN}, {SLAT_SEAT_MAX}] "
                     "(--float-slats is the designed fail)", 18),) + nothing
    njoint = SLAT_N * len(POST_X)
    if (sa["screw"] != njoint or sa["screw_joints"] != njoint
            or sa["screw_bite"][0] < SCREW_BITE_MIN or sa["screw_bite"][1] > SCREW_BITE_MAX
            or sa["screw_proud"][0] < SCREW_PROUD_MIN or sa["screw_proud"][1] > SCREW_PROUD_MAX):
        return (fail(f"{sa['screw']} screws at {sa['screw_joints']} of {njoint} joints, bite "
                     f"{sa['screw_bite']} [{SCREW_BITE_MIN}, {SCREW_BITE_MAX}], proud "
                     f"{sa['screw_proud']} [{SCREW_PROUD_MIN}, {SCREW_PROUD_MAX}] "
                     "(--float-screws is the designed fail)", 18),) + nothing
    if sa["shoe_seat"][0] < SHOE_SEAT_MIN or sa["shoe_seat"][1] > SHOE_SEAT_MAX:
        return (fail(f"shoe seat {sa['shoe_seat']} outside [{SHOE_SEAT_MIN}, {SHOE_SEAT_MAX}] "
                     "(--lift-runners is the designed fail)", 18),) + nothing
    if (sa["bolt"] != 2 * len(POST_X) or sa["bolt_proud"][0] < BOLT_PROUD_MIN
            or sa["bolt_proud"][1] > BOLT_PROUD_MAX or sa["bolt_bite"][0] < BOLT_BITE_MIN
            or sa["bolt_bite"][1] > BOLT_BITE_MAX):
        return (fail(f"{sa['bolt']} of {2 * len(POST_X)} bolts, proud {sa['bolt_proud']} "
                     f"[{BOLT_PROUD_MIN}, {BOLT_PROUD_MAX}], bite {sa['bolt_bite']} "
                     f"[{BOLT_BITE_MIN}, {BOLT_BITE_MAX}] (--float-bolts is the designed fail)",
                     18),) + nothing
    if (sa["bar"] != 1 or sa["rope"] != 1 or sa["rope_inside"] < 2
            or not (ROPE_CLEAR_MIN <= sa["rope_clear"] <= ROPE_CLEAR_MAX)):
        return (fail(f"rope through the hole: {sa['rope_inside']} rings in the bar, clearance "
                     f"{sa['rope_clear']:.5f} outside [{ROPE_CLEAR_MIN}, {ROPE_CLEAR_MAX}] "
                     "(--miss-hole is the designed fail)", 18),) + nothing
    if (not (RUNNER_LEN[0] <= sa["runner_len"][0] and sa["runner_len"][1] <= RUNNER_LEN[1])
            or not (DECK_LEN[0] <= sa["deck_len"] <= DECK_LEN[1])
            or not (DECK_W[0] <= sa["deck_w"] <= DECK_W[1])
            or not (DECK_H[0] <= sa["deck_h"] <= DECK_H[1])
            or not (TRACK[0] <= sa["track"] <= TRACK[1])):
        return (fail(f"real-world size: runner {sa['runner_len']} (band {RUNNER_LEN}), deck "
                     f"{sa['deck_len']:.4f} x {sa['deck_w']:.4f} (bands {DECK_LEN}, {DECK_W}), "
                     f"deck height {sa['deck_h']:.4f} (band {DECK_H}), track {sa['track']:.4f} "
                     f"(band {TRACK}) (--tall-posts is the designed fail)", 19),) + nothing
    if sa["mirror"] > MIRROR_EPS:
        return (fail(f"runners not mirrored: {sa['mirror']:.6f} > {MIRROR_EPS} "
                     "(--skew-runner is the designed fail)", 19),) + nothing
    return 0, low, high, mats, tex, collider


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats[FRAME_IDX], tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only.
    low.rotation_euler.z = math.radians(CAM_YAW)

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
    cam_data.lens = CAM_LENS
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = CAM_LOC
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = CAM_AIM
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
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "WEBP" if path.lower().endswith(".webp") else "PNG"
    if path.lower().endswith(".webp"):
        scene.render.image_settings.quality = 90
    scene.render.filepath = path
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    # asset-quality floors return 11, which this piece spends on the
    # collider ceiling; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return 24
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
    p.add_argument("--float-shoe", action="store_true")
    p.add_argument("--short-post", action="store_true")
    p.add_argument("--short-bar", action="store_true")
    p.add_argument("--float-slats", action="store_true")
    p.add_argument("--lift-runners", action="store_true")
    p.add_argument("--float-bolts", action="store_true")
    p.add_argument("--float-screws", action="store_true")
    p.add_argument("--miss-hole", action="store_true")
    p.add_argument("--tall-posts", action="store_true")
    p.add_argument("--skew-runner", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_shoe=args.float_shoe,
        short_post=args.short_post,
        short_bar=args.short_bar,
        float_slats=args.float_slats,
        lift_runners=args.lift_runners,
        float_bolts=args.float_bolts,
        float_screws=args.float_screws,
        miss_hole=args.miss_hole,
        tall_posts=args.tall_posts,
        skew_runner=args.skew_runner,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("toboggan OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
