"""Game-ready hanging iron cauldron — a showcase piece, not an example.

Asserts budget conformance of a procedural cauldron (lathed pot with a
rolled rim, pipe bail through ear rings, timber tripod tenoned into a
turned crown, iron ferrule cups) after composing shipped pipeline pieces:
bmesh construction, UVs, two materials, high-to-low normal bake, LOD
chain, convex collider, Unity glTF export.

The old piece was an 8-sided cone tripod piercing a 10-gon cap, a bail
of 12 boxes, a torus rim overlapping the lathe, and ferrules floating
2 mm off the ground.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--short-legs`` named ferrule
supports, ``--float-hook`` hook-bail joint-fit, ``--pipe-ferrule``
ferrule-cup seat (pole starts above the well).

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python iron_cauldron.py --
    blender --background --python iron_cauldron.py -- --skip-decimate
    blender --background --python iron_cauldron.py -- --output cauldron.png
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

# Camp cauldron ~40 cm across, hanging from an ~85 cm timber tripod
# whose feet land on a ~1.0 m circle. The pot's own size is gated
# separately from the outer AABB (the AABB is the tripod).
POT_H = 0.320
POT_THICK = 0.012
N_AROUND = 32
N_RINGS = 12
R_BOT = 0.028
R_MID = 0.185
R_TOP = 0.148
POT_Z0 = 0.155
APEX_Z = 0.860
TRIPOD_R = 0.560
POLE_SEGS = 16
POLE_R_FOOT = 0.024
POLE_R_TOP = 0.016
FERRULE_H = 0.034
FERRULE_T = 0.006
FERRULE_SEGS = 16
FERRULE_FLOOR = 0.004
CROWN_H = 0.072
CROWN_R = 0.046
INSERT_R = 0.026
BAIL_SEGS = 24
BAIL_PIPE = 8
BAIL_R = 0.007
HOOK_R = 0.006
EAR_MAJOR = 0.018
EAR_MINOR = 0.0045
POLE_OFFSET = math.radians(18.0)

BBOX_TOL = 0.015
OUTER_SIZE = (0.987, 0.961, 0.860)
BODY_DIA = 0.355
BODY_DIA_TOL = 0.04
BODY_H = 0.334
BODY_H_TOL = 0.04
POT_LEG_CLEARANCE_MIN = 0.04

BASE_TRIS_MIN = 2800
BASE_TRIS_MAX = 4200
COLLIDER_TRIS_MAX = 280
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
METAL_FACES_MIN = 200
WOOD_FACES_MIN = 80
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.999
LIFT_Z = 0.05
FERRULE_Z_MAX = 1e-3
HOOK_JOIN = 0.010
FERRULE_BITE_MIN = -0.006
FERRULE_BITE_MAX = 0.000

WOOD_IDX = 0
METAL_IDX = 1


def eevee_engine_id():
    return "BLENDER_EEVEE_NEXT" if bpy.app.version >= (4, 2, 0) else "BLENDER_EEVEE"


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
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z0 + z)))
        rings.append(ring)
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
                bm.verts.new(
                    p
                    + side * (radius * math.cos(ang))
                    + up * (radius * math.sin(ang))
                )
            )
        rings.append(ring)
    return loft_rings(bm, rings, mat_idx, cap_start=cap_start, cap_end=cap_end)


def add_cup_along(bm, origin, tangent, r_in, r_out, height, segs, mat_idx, floor=FERRULE_FLOOR):
    """Closed iron shoe coaxial with the pole.

    `origin` is the intended ground station of the pole foot. The cup is
    shifted along `tangent` so the downhill outer rim sits at Z=0 —
    a world-Z bucket lets a leaning pole slice the lip. Returns the
    shifted origin (axis point of the outer floor).
    """
    t = Vector(tangent).normalized()
    o = Vector(origin)
    side = Vector((-t.y, t.x, 0.0))
    if side.length < 1e-6:
        side = Vector((1.0, 0.0, 0.0))
    else:
        side.normalize()
    up = t.cross(side).normalized()
    lean = math.sqrt(max(0.0, 1.0 - t.z * t.z))
    o = o + t * ((r_out * lean) / max(t.z, 0.25))
    specs = (
        (0.0, r_out),
        (height, r_out),
        (height, r_in),
        (floor, r_in),
    )
    rings = []
    for dist, r in specs:
        p = o + t * dist
        ring = []
        for i in range(segs):
            a = 2.0 * math.pi * i / segs
            ring.append(
                bm.verts.new(
                    p + side * (r * math.cos(a)) + up * (r * math.sin(a))
                )
            )
        rings.append(ring)
    loft_rings(bm, rings, mat_idx, cap_start=True, cap_end=True)
    return o, t


def add_torus(bm, loc, major, minor, n_major, n_minor, mat_idx, euler=(0.0, 0.0, 0.0)):
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
    verts = [v for ring in rings for v in ring]
    for i in range(n_major):
        i2 = (i + 1) % n_major
        for j in range(n_minor):
            j2 = (j + 1) % n_minor
            face = bm.faces.new(
                (rings[i][j], rings[i2][j], rings[i2][j2], rings[i][j2])
            )
            face.material_index = mat_idx
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    return verts


def add_pipe_curve(bm, points, radius, segs, mat_idx):
    rings = []
    n = len(points)
    for i, p in enumerate(points):
        p = Vector(p)
        if i < n - 1:
            tangent = (Vector(points[i + 1]) - p).normalized()
        else:
            tangent = (p - Vector(points[i - 1])).normalized()
        side = Vector((-tangent.y, tangent.x, 0.0))
        if side.length < 1e-6:
            side = Vector((1.0, 0.0, 0.0))
        else:
            side.normalize()
        up = tangent.cross(side).normalized()
        ring = []
        for k in range(segs):
            a = 2.0 * math.pi * k / segs
            ring.append(
                bm.verts.new(
                    p + side * (radius * math.cos(a)) + up * (radius * math.sin(a))
                )
            )
        rings.append(ring)
    return loft_rings(bm, rings, mat_idx, cap_start=True, cap_end=True)


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


def pot_radius(z_local):
    t = max(0.0, min(1.0, z_local / POT_H))
    return (
        (1.0 - t) ** 2 * R_BOT
        + 2.0 * t * (1.0 - t) * (R_MID * 1.32)
        + t ** 2 * R_TOP
    )


def pole_feet():
    feet = []
    for i in range(3):
        ang = i * (2.0 * math.pi / 3.0) + POLE_OFFSET
        feet.append(Vector((TRIPOD_R * math.cos(ang), TRIPOD_R * math.sin(ang), 0.0)))
    return feet


def build_cauldron_mesh(
    name,
    short_legs=False,
    float_hook=False,
    pipe_ferrule=False,
):
    bm = bmesh.new()
    wood_verts = []
    try:
        # Dual-wall lathe plus a rolled rim. No overlapping torus, no
        # extra bottom cylinder — those left a hole in the floor and a
        # faceted lip sitting on the mouth.
        zs = [POT_H * i / (N_RINGS - 1) for i in range(N_RINGS)]
        rim = (
            (POT_H + 0.004, R_TOP + 0.012),
            (POT_H + 0.010, R_TOP + 0.018),
            (POT_H + 0.014, R_TOP + 0.014),
            (POT_H + 0.011, R_TOP + 0.006),
        )
        outers, inners = [], []
        for z_local in zs:
            z = POT_Z0 + z_local
            r = pot_radius(z_local)
            ri = max(r - POT_THICK, 0.014)
            oring, iring = [], []
            for i in range(N_AROUND):
                a = 2.0 * math.pi * i / N_AROUND
                oring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
                iring.append(bm.verts.new((ri * math.cos(a), ri * math.sin(a), z)))
            outers.append(oring)
            inners.append(iring)
        for z_off, r in rim:
            z = POT_Z0 + z_off
            ri = max(r - POT_THICK, 0.014)
            oring, iring = [], []
            for i in range(N_AROUND):
                a = 2.0 * math.pi * i / N_AROUND
                oring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
                iring.append(bm.verts.new((ri * math.cos(a), ri * math.sin(a), z)))
            outers.append(oring)
            inners.append(iring)
        for k in range(len(outers) - 1):
            for i in range(N_AROUND):
                j = (i + 1) % N_AROUND
                fo = bm.faces.new(
                    (outers[k][i], outers[k + 1][i], outers[k + 1][j], outers[k][j])
                )
                fo.material_index = METAL_IDX
                fi = bm.faces.new(
                    (inners[k][j], inners[k + 1][j], inners[k + 1][i], inners[k][i])
                )
                fi.material_index = METAL_IDX
        for i in range(N_AROUND):
            j = (i + 1) % N_AROUND
            lip = bm.faces.new(
                (outers[-1][i], outers[-1][j], inners[-1][j], inners[-1][i])
            )
            lip.material_index = METAL_IDX
        oc = bm.verts.new((0.0, 0.0, POT_Z0))
        ic = bm.verts.new((0.0, 0.0, POT_Z0 + POT_THICK))
        for i in range(N_AROUND):
            j = (i + 1) % N_AROUND
            bot = bm.faces.new((oc, outers[0][j], outers[0][i]))
            bot.material_index = METAL_IDX
            ibot = bm.faces.new((ic, inners[0][i], inners[0][j]))
            ibot.material_index = METAL_IDX

        mouth_z = POT_Z0 + POT_H
        # Vertical rings (hole along Y) so the XZ bail can thread them.
        ear_x = R_TOP + 0.008
        ear_z = mouth_z + 0.002
        for sign in (-1.0, 1.0):
            add_torus(
                bm,
                (sign * ear_x, 0.0, ear_z),
                EAR_MAJOR,
                EAR_MINOR,
                14,
                6,
                METAL_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        # Semicircle through the ear holes, ends past the rings.
        t0 = -0.42
        t1 = math.pi + 0.42
        bail_pts = []
        for i in range(BAIL_SEGS + 1):
            t = t0 + (t1 - t0) * i / BAIL_SEGS
            bail_pts.append(
                (ear_x * math.cos(t), 0.0, ear_z + ear_x * math.sin(t))
            )
        add_pipe_curve(bm, bail_pts, BAIL_R, BAIL_PIPE, METAL_IDX)
        bail_peak = Vector(bail_pts[len(bail_pts) // 2])
        hook_z = bail_peak.z + (0.08 if float_hook else 0.0)
        add_torus(
            bm,
            (0.0, 0.0, hook_z),
            BAIL_R + HOOK_R * 0.85,
            HOOK_R,
            12,
            6,
            METAL_IDX,
            euler=(0.0, math.radians(90.0), 0.0),
        )
        crown_z0 = APEX_Z - CROWN_H
        lathe_axis(
            bm,
            (0.0, 0.0, hook_z + HOOK_R),
            (0.0, 0.0, crown_z0 + 0.008),
            ((0.0, HOOK_R * 0.9), (1.0, HOOK_R * 0.9)),
            8,
            METAL_IDX,
        )

        lathe_z(
            bm,
            (
                (0.000, 0.032),
                (0.018, 0.046),
                (0.048, 0.042),
                (CROWN_H, 0.026),
            ),
            16,
            WOOD_IDX,
            z0=crown_z0,
        )
        feet = pole_feet()
        ferrule_z0 = 0.05 if short_legs else 0.0
        if short_legs:
            geo = bmesh.ops.create_cube(bm, size=1.0)
            for v in geo["verts"]:
                v.co.x *= 0.024
                v.co.y *= 0.024
                v.co.z *= 0.006
                v.co.z += 0.003
            for f in {f for v in geo["verts"] for f in v.link_faces}:
                f.material_index = METAL_IDX
        for foot in feet:
            ang = math.atan2(foot.y, foot.x)
            top = Vector((
                INSERT_R * math.cos(ang),
                INSERT_R * math.sin(ang),
                APEX_Z - 0.030,
            ))
            origin = Vector((foot.x, foot.y, ferrule_z0))
            tangent = (top - origin).normalized()
            r_in = POLE_R_FOOT + 0.002
            r_out = r_in + FERRULE_T
            lean = math.sqrt(max(0.0, 1.0 - tangent.z * tangent.z))
            shifted = origin + tangent * ((r_out * lean) / max(tangent.z, 0.25))
            add_cup_along(
                bm, origin, tangent, r_in, r_out, FERRULE_H,
                FERRULE_SEGS, METAL_IDX,
            )
            # Same shoe either way so AABB/zmin stay put. --pipe-ferrule
            # starts the pole above the well; ferrule_bite only samples
            # wood inside the cup's own axis span, so a hovering pole
            # cannot fake a seat.
            seat = FERRULE_H + 0.05 if pipe_ferrule else (FERRULE_FLOOR + 0.002)
            bot = shifted + tangent * seat
            lathe_axis(
                bm, bot, top,
                ((0.0, POLE_R_FOOT), (1.0, POLE_R_TOP)),
                POLE_SEGS, WOOD_IDX,
            )

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = True
            if edge.is_manifold and len(edge.link_faces) == 2:
                if edge.calc_face_angle() > math.radians(55.0):
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


def pot_tripod_clearance(mesh):
    feet = pole_feet()
    apex = Vector((0.0, 0.0, APEX_Z))
    z0 = POT_Z0 - 0.02
    z1 = POT_Z0 + POT_H + 0.03
    min_c = None
    for v in mesh.vertices:
        p = Vector(v.co)
        if p.z < z0 or p.z > z1:
            continue
        if math.hypot(p.x, p.y) < 0.06:
            continue
        nearest = None
        on_pole = False
        for foot in feet:
            ab = apex - foot
            denom = ab.length_squared
            if denom < 1e-12:
                continue
            t = max(0.0, min(1.0, (p - foot).dot(ab) / denom))
            axis = (p - (foot + t * ab)).length
            rad = POLE_R_FOOT * (1.0 - t) + POLE_R_TOP * t
            gap = axis - rad
            if axis < rad + 0.006:
                on_pole = True
                break
            if nearest is None or gap < nearest:
                nearest = gap
        if on_pole or nearest is None:
            continue
        if min_c is None or nearest < min_c:
            min_c = nearest
    return min_c if min_c is not None else -1.0


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
        if a[5] < 0.14 and dx > 0.03 and dy > 0.03 and dz < 0.12:
            cups.append(a)
    cup_z = min((a[2] for a in cups), default=99.0)
    return {"cups": len(cups), "cup_z": cup_z}


def pot_audit(me):
    groups = shells(me)
    best = None
    best_r = -1.0
    for g in groups:
        if mat_of(me, g) != METAL_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        r = 0.5 * 0.5 * (dx + dy)
        if dz > 0.20 and r > best_r:
            best_r = r
            best = a
    if best is None:
        return {"dia": 0.0, "height": 0.0}
    return {
        "dia": 0.5 * ((best[3] - best[0]) + (best[4] - best[1])),
        "height": best[5] - best[2],
    }


def hook_bail_join(me):
    """Worst gap from the compact hook ring to the bail pipe."""
    groups = shells(me)
    hooks, bails = [], []
    for g in groups:
        if mat_of(me, g) != METAL_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        cz = 0.5 * (a[2] + a[5])
        if cz > 0.55 and max(dx, dy, dz) < 0.08:
            hooks.append(g)
        elif dz > 0.12 and a[2] > 0.35 and max(dx, dy) > 0.20:
            bails.append(g)
    if not hooks or not bails:
        return 99.0
    bm_b = bmesh.new()
    try:
        bm_b.from_mesh(me)
        keep = set()
        for g in bails:
            keep.update(g)
        drop = [
            f for f in bm_b.faces
            if not all(v.index in keep for v in f.verts)
        ]
        if drop:
            bmesh.ops.delete(bm_b, geom=drop, context="FACES")
        if not bm_b.faces:
            return 99.0
        tree = BVHTree.FromBMesh(bm_b)
        worst = 0.0
        for g in hooks:
            bm_h = bmesh.new()
            try:
                bm_h.from_mesh(me)
                member = set(g)
                drop_h = [
                    f for f in bm_h.faces
                    if not all(v.index in member for v in f.verts)
                ]
                if drop_h:
                    bmesh.ops.delete(bm_h, geom=drop_h, context="FACES")
                if not bm_h.faces:
                    worst = max(worst, 99.0)
                    continue
                tree_h = BVHTree.FromBMesh(bm_h)
                if tree.overlap(tree_h):
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
                bm_h.free()
        return worst
    finally:
        bm_b.free()


def ferrule_bite(me):
    """Pole radius minus cup inner wall, in the pole's own frame.

    World-XY distance lies about a leaning pole that is coaxial with its
    shoe: the foot sits on the axis while the rim is offset in XY, so a
    vertical-bucket metric reports a false gap. Measure radial distance
    from the pole axis instead.
    """
    groups = shells(me)
    cups, woods = [], []
    for g in groups:
        a = shell_aabb(me, g)
        if mat_of(me, g) == METAL_IDX and a[5] < 0.12 and (a[5] - a[2]) < 0.10:
            cups.append(g)
        elif mat_of(me, g) == WOOD_IDX and a[2] < 0.12 and (a[5] - a[2]) > 0.15:
            woods.append(g)
    if not cups or not woods:
        return 0.0
    feet = pole_feet()
    apex = Vector((0.0, 0.0, APEX_Z))
    wood_pts = [me.vertices[i].co.copy() for g in woods for i in g]
    bites = []
    for g in cups:
        pts = [me.vertices[i].co.copy() for i in g]
        centroid = sum(pts, Vector((0.0, 0.0, 0.0))) / len(pts)
        foot = min(feet, key=lambda f: (f - centroid).length)
        axis = apex - foot
        if axis.length < 1e-8:
            continue
        axis.normalize()

        def rad(p):
            return (p - foot).cross(axis).length

        wall = [rad(p) for p in pts if rad(p) > 0.010]
        if not wall:
            continue
        r_in = min(wall)
        span = [(p - foot).dot(axis) for p in pts]
        t0, t1 = min(span), max(span)
        near = [
            p for p in wood_pts
            if rad(p) > 0.010
            and (p - centroid).length < 0.10
            and (t0 - 0.002) <= (p - foot).dot(axis) <= (t1 + 0.002)
        ]
        if not near:
            continue
        r_wood = min(rad(p) for p in near)
        bites.append(r_wood - r_in)
    if not bites:
        return 0.05
    return min(bites)


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, APEX_Z))
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
    img = bpy.data.images.new("CauldronNrm", size, size, alpha=True, float_buffer=False)
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
    float_hook=False,
    pipe_ferrule=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        short_legs=short_legs,
        float_hook=float_hook,
        pipe_ferrule=pipe_ferrule,
    )
    low = build_cauldron_mesh("CauldronLow", **flags)
    high = build_cauldron_mesh("CauldronHigh", **flags)
    wood = principled(
        "TripodWood", (0.38, 0.22, 0.09, 1.0), 0.0, 0.58,
        noise_scale=6.0, wear=(0.22, 0.12, 0.05, 1.0),
    )
    metal = principled(
        "CauldronIron", (0.10, 0.095, 0.09, 1.0), 0.92, 0.40,
        noise_scale=5.0, wear=(0.18, 0.16, 0.14, 1.0),
    )
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
        return fail("cauldron mesh did not build", 3), None, None, None, None, None

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
    clearance = pot_tripod_clearance(low.data)
    print(f"measured pot_tripod_clearance={clearance:.4f}")
    if clearance < POT_LEG_CLEARANCE_MIN:
        return fail(
            f"pot clips tripod clearance {clearance:.4f} "
            f"< {POT_LEG_CLEARANCE_MIN}",
            3,
        ), None, None, None, None, None

    img, tex = setup_bake_image(low, wood)
    if img is None:
        return fail("cauldron has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "CauldronLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "CauldronLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_cauldron_mesh("CauldronColSrc", **flags)
    collider = convex_hull_collider(collider_src, "CauldronCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_iron_cauldron_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    sup = support_audit(low.data)
    pot = pot_audit(low.data)
    hj = hook_bail_join(low.data)
    bite = ferrule_bite(low.data)

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
        f"pot_dia={pot['dia']:.4f} pot_h={pot['height']:.4f} "
        f"hook_join={hj:.5f} ferrule_bite={bite:.5f}"
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
    if sup["cups"] < 3 or sup["cup_z"] > FERRULE_Z_MAX:
        return fail(
            f"ferrule supports {sup['cups']} cup_z={sup['cup_z']:.5f} "
            "(--short-legs is the designed fail)",
            16,
        ), None, None, None, None, None
    if hj > HOOK_JOIN:
        return fail(
            f"hook-bail gap {hj:.5f} > {HOOK_JOIN} "
            "(--float-hook is the designed fail)",
            17,
        ), None, None, None, None, None
    if not (FERRULE_BITE_MIN <= bite <= FERRULE_BITE_MAX):
        return fail(
            f"ferrule bite {bite:.5f} not in "
            f"[{FERRULE_BITE_MIN}, {FERRULE_BITE_MAX}] "
            "(--pipe-ferrule is the designed fail)",
            18,
        ), None, None, None, None, None
    if abs(pot["dia"] - BODY_DIA) > BODY_DIA_TOL:
        return fail(
            f"pot diameter {pot['dia']:.4f} off {BODY_DIA}",
            19,
        ), None, None, None, None, None
    if abs(pot["height"] - BODY_H) > BODY_H_TOL:
        return fail(
            f"pot height {pot['height']:.4f} off {BODY_H}",
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
    low.rotation_euler.x = math.radians(4.0)

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
    cam.location = (1.82, -2.50, 1.40)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.40)
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
    p.add_argument("--float-hook", action="store_true")
    p.add_argument("--pipe-ferrule", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        short_legs=args.short_legs,
        float_hook=args.float_hook,
        pipe_ferrule=args.pipe_ferrule,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("iron-cauldron OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
