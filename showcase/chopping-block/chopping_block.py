"""Game-ready chopping block — a showcase piece, not an example.

Asserts budget conformance of a procedural splitting block (a hooped log
round with a felling axe standing in it) after composing shipped pipeline
pieces: bmesh construction, UVs, three materials, high-to-low normal bake,
LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates exactly one named
budget: ``--skip-decimate`` skips the LOD DECIMATE stage so the LOD-ratio
budget fails, ``--lift-z`` moves the mesh off the floor so the grounded
budget fails, ``--stray-vert`` adds one unconnected vertex so the
mesh-hygiene budget fails, ``--fat-haft`` widens the handle to the full
thickness of the axe eye so the eye joint-fit budget fails, and
``--round-band`` generates the iron band on a circle instead of on the
log's own surface so the band-seat budget fails.

No RNG. The log's out-of-round profile is a closed-form sum of sines, so
construction is deterministic. DECIMATE COLLAPSE triangle counts are not
byte-identical across Blender versions — the LOD gate is a ratio band,
not an exact count.

    blender --background --python chopping_block.py --
    blender --background --python chopping_block.py -- --skip-decimate
    blender --background --python chopping_block.py -- --lift-z
    blender --background --python chopping_block.py -- --stray-vert
    blender --background --python chopping_block.py -- --fat-haft
    blender --background --python chopping_block.py -- --round-band
    blender --background --python chopping_block.py -- --output block.png
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

# A splitting block is a log round: 0.41 m across, 0.46 m tall, near-parallel
# sides. The old piece was a truncated cone 0.44 m across and 0.36 m tall,
# which reads as a pail.
# A log round is wider than it is tall: 0.52 m across, 0.36 m high. At
# 0.41 across and 0.46 high the silhouette was a cylinder as tall as it was
# wide, which is a canister no matter what detail is put on its surface.
BLOCK_R = 0.260
BLOCK_H = 0.36
BLOCK_SEGS = 36
BLOCK_TAPER = 0.052
# The bake's high-poly is the same construction at a higher detail level, so
# what the normal map records is real rounding, not a second sculpt.
HIGH_SEG_SCALE = 2
HIGH_CHAMFER_SEGS = 3
# Out-of-round profile, as (frequency, phase, amplitude). A perfect circle
# reads as a turned bucket. Frequencies are chosen so that no sum or
# difference with the rim-chip frequency lands on 1 or on 1 mod BLOCK_SEGS:
# that is what keeps each ring's centroid exactly on the axis, which is in
# turn what makes the plumb assertion meaningful rather than approximate.
WOBBLE = ((3.0, 0.4, 0.030), (7.0, 2.1, 0.019), (11.0, 5.0, 0.011))
WOBBLE_TWIST = 0.10

# Stump hoop, low on the body. Generated from the log's own radius function,
# so it seats uniformly on an out-of-round surface; a circular hoop
# alternately sinks and floats, which is what the old torus did. Up under
# the rim it read as the clamp ring of a lid.
BAND_Z0 = 0.075
BAND_Z1 = 0.125
BAND_BITE = 0.004
BAND_PROUD = 0.006
BAND_CHAMFER = 0.0022

# (z, rim scale). The scaled rings are modelled chamfers: the rim of a sawn
# log catches light, and modelling it costs less than bevelling 32 segments.
# The band's own two heights are ring heights, so the hoop's inner face and
# the log's facet interpolate identically between them and the seat cannot
# open up between rings.
BLOCK_RINGS = (
    (0.000, 0.958),
    (0.018, 1.000),
    (BAND_Z0, 1.000),
    (BAND_Z1, 1.000),
    (0.250, 1.000),
    (BLOCK_H - 0.028, 1.000),
    (BLOCK_H, 0.955),
)
# A block that gets split on reads as a canister with a lid unless the top
# is dished and hacked, the rim is chipped, and the end grain has opened up
# along radial checks. The cracks are the single strongest read.
TOP_RIM_SCALE = 0.955
TOP_RIM_CHIP = 0.035
TOP_CAP_RINGS = (0.72, 0.44, 0.18)
TOP_DISH = 0.0110
TOP_SCAR = 0.0110
# (angle, depth). Depth stays under the 28 mm top chamfer so a check can
# notch the rim without pushing it below the chamfer ring and inverting it.
TOP_CRACKS = ((0.55, 0.015), (2.60, 0.011), (4.35, 0.018))
TOP_CRACK_WIDTH = 0.15

# Felling axe. The head is a single lofted shell from poll to bit, not a
# stack of boxes. Angles are measured in the XZ plane before the azimuth
# spin; the 18 degrees between the head axis and the haft is the hang angle.
HEAD_LEN = 0.225
HEAD_EYE_T = 0.26
AXE_BIT_ANGLE = math.radians(228.0)
AXE_HAFT_ANGLE = math.radians(126.0)
AXE_AZIMUTH = math.radians(34.0)
BIT_CENTER = (0.010, 0.0, BLOCK_H - 0.030)
# (t along poll to bit, half height along the edge, half thickness). The
# first and last pairs are the lengthwise chamfers on the poll and the bit;
# every corner of every section is chamfered by HEAD_CHAMFER. Modelling the
# chamfer is what replaced a bmesh bevel here: bevelling a four-sided loft
# left sixteen boundary edges and two doubles at the bit.
# A felling axe is long and narrow: 225 mm poll to bit with a 148 mm edge.
# At 155 mm with a 172 mm edge it read as a paddle; at 185 mm against a
# 530 mm block it read as a trowel. The head is sized off the block, not
# off an absolute idea of an axe -- half the block diameter is what makes
# the two objects look like they belong in the same scene.
HEAD_SECTIONS = (
    (0.000, 0.0280, 0.0215),
    (0.028, 0.0340, 0.0270),
    (0.150, 0.0485, 0.0385),
    (0.330, 0.0520, 0.0280),
    (0.620, 0.0615, 0.0160),
    (0.870, 0.0710, 0.0062),
    (0.980, 0.0745, 0.0018),
    (1.000, 0.0728, 0.0013),
)
HEAD_CHAMFER = 0.0042
HAFT_LEN = 0.68
HAFT_DROP = 0.024
HAFT_BOW = 0.020
HAFT_SEGS = 12
# (t along the haft, radius). The last two rings round the knob off, so the
# haft needs no bevel of its own. The shoulder-waist-swell spread is wide on
# purpose: a 0.68 m haft that runs 15 mm to 18 mm reads as dowel at any
# distance a viewer will see it from.
HAFT_SECTIONS = (
    (0.00, 0.0192),
    (0.10, 0.0205),
    (0.32, 0.0150),
    (0.58, 0.0132),
    (0.80, 0.0150),
    (0.91, 0.0225),
    (0.97, 0.0206),
    (1.00, 0.0124),
)
FAT_HAFT_SCALE = 1.85

# Four closed shells: log, iron band, axe head, axe haft.
PART_COUNT = 4
BBOX_TOL = 0.012
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.526, 0.526, 1.012)
# Stated real-world size of the block itself, checked separately from the
# fitted AABB so a proportion drift is named rather than absorbed by it.
BLOCK_DIAMETER = 0.535
BLOCK_HEIGHT = 0.360
BLOCK_DIAMETER_TOL = 0.030
BLOCK_HEIGHT_TOL = 0.010
PLUMB_EPS = 1e-5

# Joint contract, all recomputed from vertex positions in the axe's own
# construction frame.
EYE_CLEARANCE_MIN = 0.006
HAFT_ENGAGE_MIN = 0.020
HAFT_INSIDE_MIN = 0.006
BIT_BURY_MIN = 0.030
BIT_INSET_MIN = 0.030
BAND_BITE_MIN = 0.002
BAND_BITE_MAX = 0.007
HAFT_BLOCK_CLEAR_MIN = 0.015

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 0.0012
ZFIGHT_COS = 0.9995
LIFT_Z = 0.05

BASE_TRIS_MIN = 1410
BASE_TRIS_MAX = 1530
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 470
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
# Floors catch the slot-assignment wipe class and the bevel-inherits-slot-0
# class: the axe head's chamfers are claimed from the bevel op's own return,
# so a regression there drops the metal count well below this floor.
WOOD_FACES_MIN = 160
GRAIN_FACES_MIN = 90
METAL_FACES_MIN = 170

WOOD_IDX = 0
GRAIN_IDX = 1
METAL_IDX = 2


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


def log_radius(u, z):
    """Radius of the log's side at angle u and height z.

    One function owns the surface. The iron band, the assertions and the
    mesh all evaluate it, so the band cannot drift off the wood when a
    dimension changes.
    """
    zt = z / BLOCK_H
    taper = 1.0 - BLOCK_TAPER * zt
    wobble = 1.0
    for freq, phase, amp in WOBBLE:
        wobble += amp * math.sin(freq * u + phase + WOBBLE_TWIST * freq * zt)
    return BLOCK_R * taper * wobble


def rim_scale(u):
    """Chipped top rim. Always below 1.0, so the widest point of the block
    stays on the body and the rim cannot become the AABB."""
    chip = 0.5 * (1.0 + math.sin(5.0 * u + 1.7))
    return TOP_RIM_SCALE - TOP_RIM_CHIP * chip


def top_dz(u, rr):
    """Dish, hack scarring and radial checks on the sawn top.

    Dish and scars vanish at the rim; the checks do not, because a drying
    check opens widest at the edge and notches it.
    """
    scar = 0.5 * (1.0 + math.sin(3.0 * u + 0.9))
    drop = TOP_DISH * (1.0 - rr * rr) + TOP_SCAR * scar * (1.0 - rr)
    for angle, depth in TOP_CRACKS:
        d = (u - angle + math.pi) % (2.0 * math.pi) - math.pi
        drop += (
            depth
            * math.exp(-((d / TOP_CRACK_WIDTH) ** 2))
            * (0.25 + 0.75 * rr)
        )
    return -drop


def fan_cap(bm, ring):
    center = Vector((0.0, 0.0, 0.0))
    for v in ring:
        center += v.co
    center /= len(ring)
    hub = bm.verts.new(center)
    n = len(ring)
    faces = [bm.faces.new((hub, ring[i], ring[(i + 1) % n])) for i in range(n)]
    return hub, faces


def loft(bm, rings, cap_start=True, cap_end=True):
    """Sweep equal-length vertex rings into a closed shell.

    Returns (verts, rows, caps): rows[i] holds the faces between ring i and
    ring i+1, so a caller can give the sawn rim a different material slot
    from the bark side without re-deriving which faces those are.
    """
    vert_rings = [[bm.verts.new(p) for p in ring] for ring in rings]
    bm.verts.ensure_lookup_table()
    n = len(vert_rings[0])
    rows = []
    for a, b in zip(vert_rings, vert_rings[1:]):
        row = []
        for i in range(n):
            j = (i + 1) % n
            row.append(bm.faces.new((a[i], a[j], b[j], b[i])))
        rows.append(row)
    verts = [v for ring in vert_rings for v in ring]
    caps = []
    if cap_start:
        hub, faces = fan_cap(bm, vert_rings[0])
        verts.append(hub)
        caps.append(faces)
    if cap_end:
        hub, faces = fan_cap(bm, vert_rings[-1])
        verts.append(hub)
        caps.append(faces)
    return verts, rows, caps


def loft_cyclic(bm, sections):
    """Sweep a closed cross-section around a closed path (a hoop)."""
    vert_rings = [[bm.verts.new(p) for p in s] for s in sections]
    bm.verts.ensure_lookup_table()
    m = len(vert_rings)
    n = len(vert_rings[0])
    faces = []
    for k in range(m):
        a = vert_rings[k]
        b = vert_rings[(k + 1) % m]
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    return [v for ring in vert_rings for v in ring], faces


def chamfered_rect(he, hs, chamfer, segs):
    """Rectangle corner loop with quarter-arc corners, walked CCW.

    ``segs`` of 1 gives a flat chamfer; higher values round it, which is how
    the bake's high-poly differs from the shipped low-poly.
    """
    c = max(1e-5, min(chamfer, 0.35 * he, 0.35 * hs))
    corners = (
        (he - c, hs - c, 0.0),
        (-(he - c), hs - c, 0.5 * math.pi),
        (-(he - c), -(hs - c), math.pi),
        (he - c, -(hs - c), 1.5 * math.pi),
    )
    pts = []
    for cx, cy, a0 in corners:
        for k in range(segs + 1):
            a = a0 + 0.5 * math.pi * (k / segs)
            pts.append((cx + c * math.cos(a), cy + c * math.sin(a)))
    return pts


def build_log(bm, segs):
    """Log round: body, chamfered rims, and a dished, hacked top face.

    The top cap is a ring stack rather than a single fan so the sawn face
    can carry the dish and the hack scars. A flat pale disc up there is what
    made the old piece read as a lidded pail.
    """
    us = [i * (2.0 * math.pi / segs) for i in range(segs)]
    rings = []
    for z, scale in BLOCK_RINGS[:-1]:
        rings.append(
            [
                Vector(
                    (
                        log_radius(u, z) * scale * math.cos(u),
                        log_radius(u, z) * scale * math.sin(u),
                        z,
                    )
                )
                for u in us
            ]
        )
    rim = [log_radius(u, BLOCK_H) * rim_scale(u) for u in us]
    rings.append(
        [
            Vector((r * math.cos(u), r * math.sin(u), BLOCK_H + top_dz(u, 1.0)))
            for r, u in zip(rim, us)
        ]
    )
    body_rows = len(rings) - 1
    for rr in TOP_CAP_RINGS:
        rings.append(
            [
                Vector(
                    (
                        r * rr * math.cos(u),
                        r * rr * math.sin(u),
                        BLOCK_H + top_dz(u, rr),
                    )
                )
                for r, u in zip(rim, us)
            ]
        )
    verts, rows, caps = loft(bm, rings)
    # Bark on the sides, pale end grain on both sawn faces and their rims.
    bark = [face for row in rows[1:body_rows - 1] for face in row]
    grain = list(rows[0]) + list(rows[body_rows - 1])
    for row in rows[body_rows:]:
        grain.extend(row)
    for cap in caps:
        grain.extend(cap)
    return verts, bark, grain


def build_band(bm, segs, round_band):
    """Iron hoop, generated on the log's own surface.

    ``round_band`` is the falsifier: the hoop is generated on a circle of
    the mean radius instead, which is exactly what made the old torus sink
    into the wood on one side and float off it on the other.
    """
    mid_z = 0.5 * (BAND_Z0 + BAND_Z1)
    mean_r = sum(
        log_radius(i * (2.0 * math.pi / segs), mid_z) for i in range(segs)
    ) / segs
    sections = []
    c = BAND_CHAMFER
    for i in range(segs):
        u = i * (2.0 * math.pi / segs)
        cu, su = math.cos(u), math.sin(u)
        if round_band:
            r0 = r1 = mean_r
        else:
            r0 = log_radius(u, BAND_Z0)
            r1 = log_radius(u, BAND_Z1)
        profile = (
            (r0 - BAND_BITE, BAND_Z0),
            (r0 + BAND_PROUD - c, BAND_Z0),
            (r0 + BAND_PROUD, BAND_Z0 + c),
            (r1 + BAND_PROUD, BAND_Z1 - c),
            (r1 + BAND_PROUD - c, BAND_Z1),
            (r1 - BAND_BITE, BAND_Z1),
        )
        sections.append([Vector((r * cu, r * su, z)) for r, z in profile])
    return loft_cyclic(bm, sections)


def axe_frame():
    """Orthonormal head frame plus the haft direction.

    ``f`` runs poll to bit, ``s`` is the cheek normal and ``eh`` is the edge
    direction. The haft is deliberately not perpendicular to ``f``: the 18
    degrees between them is the hang angle.
    """
    f = Vector((math.cos(AXE_BIT_ANGLE), 0.0, math.sin(AXE_BIT_ANGLE)))
    s = Vector((0.0, 1.0, 0.0))
    eh = s.cross(f).normalized()
    haft = Vector((math.cos(AXE_HAFT_ANGLE), 0.0, math.sin(AXE_HAFT_ANGLE)))
    bit = Vector(BIT_CENTER)
    poll = bit - f * HEAD_LEN
    eye = poll + f * (HEAD_EYE_T * HEAD_LEN)
    return f, s, eh, haft, poll, eye


def build_head(bm, chamfer_segs):
    f, s, eh, _haft, poll, _eye = axe_frame()
    rings = []
    for t, he, hs in HEAD_SECTIONS:
        center = poll + f * (t * HEAD_LEN)
        rings.append(
            [
                center + eh * px + s * py
                for px, py in chamfered_rect(he, hs, HEAD_CHAMFER, chamfer_segs)
            ]
        )
    verts, rows, caps = loft(bm, rings)
    faces = [face for row in rows for face in row]
    faces.extend(face for cap in caps for face in cap)
    return verts, faces


def haft_rings(scale, segs):
    _f, s, _eh, haft, _poll, eye = axe_frame()
    start = eye - haft * HAFT_DROP
    end = eye + haft * HAFT_LEN
    # A straight stick reads as a broom. The bow is a quadratic Bezier
    # leaning away from the bit, the way a hung haft curves.
    bit_dir = Vector((math.cos(AXE_BIT_ANGLE), 0.0, math.sin(AXE_BIT_ANGLE)))
    mid = (start + end) * 0.5 - bit_dir * HAFT_BOW
    rings = []
    for t, radius in HAFT_SECTIONS:
        omt = 1.0 - t
        p = start * (omt * omt) + mid * (2.0 * omt * t) + end * (t * t)
        dp = (mid - start) * (2.0 * omt) + (end - mid) * (2.0 * t)
        tangent = dp.normalized()
        side = s.cross(tangent).normalized()
        up = tangent.cross(side).normalized()
        r = radius * scale
        ring = []
        for i in range(segs):
            a = i * (2.0 * math.pi / segs)
            ring.append(p + side * (r * math.cos(a)) + up * (r * math.sin(a)))
        rings.append(ring)
    return rings


def build_haft(bm, scale, segs):
    verts, rows, caps = loft(bm, haft_rings(scale, segs))
    faces = [face for row in rows for face in row]
    faces.extend(face for cap in caps for face in cap)
    return verts, faces


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


def build_chopping_block_mesh(name, detail=1, haft_scale=1.0, round_band=False):
    log_segs = BLOCK_SEGS * detail
    haft_segs = HAFT_SEGS * detail
    chamfer_segs = HIGH_CHAMFER_SEGS if detail > 1 else 1
    bm = bmesh.new()
    try:
        _log_verts, bark_faces, grain_faces = build_log(bm, log_segs)
        _band_verts, band_faces = build_band(bm, log_segs, round_band)
        head_verts, head_faces = build_head(bm, chamfer_segs)
        haft_verts, haft_faces = build_haft(bm, haft_scale, haft_segs)

        # The axe is built in the XZ plane so the frame maths stays readable.
        spin = Matrix.Rotation(AXE_AZIMUTH, 3, "Z")
        for v in head_verts + haft_verts:
            v.co = spin @ v.co

        metal = set(band_faces) | set(head_faces)
        grain = set(grain_faces)
        # Only the haft is a turned surface. Everything else is faceted: the
        # log is flat-shaded so its out-of-round wobble and the checks in the
        # end grain each catch their own light. Smoothed, a 36-gon log is a
        # featureless drum and every bit of surface modelling is wasted --
        # that is what made the round-2 block read as a canister.
        flat = set(band_faces) | set(head_faces) | set(bark_faces) | grain

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            if face in metal:
                face.material_index = METAL_IDX
            elif face in grain:
                face.material_index = GRAIN_IDX
            else:
                face.material_index = WOOD_IDX
            face.smooth = face not in flat
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


def principled(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def assign_slots(obj, *wanted):
    # Index-preserving: clearing the slot list resets every polygon's
    # material_index to 0 on some versions, which renders the piece
    # single-material while the slot count still passes.
    mats = obj.data.materials
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
    }


def zfight_pairs(me):
    """Disjoint faces sharing a plane and a position, which z-fight.

    Faces that share a vertex are excluded: the triangles of one flat fan
    cap are coplanar and close-centred by construction, and counting those
    would make the budget unsatisfiable rather than meaningful.
    """
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
    """Vertex-index groups, one per connected shell.

    The parts interpenetrate on purpose but share no vertices, so edge
    connectivity separates them.
    """
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


def classify_shells(me, groups):
    """Name each shell from its own geometry, never from build order."""
    co = [v.co for v in me.vertices]
    stats = []
    for group in groups:
        pts = [co[i] for i in group]
        zs = [p.z for p in pts]
        stats.append(
            {
                "idx": group,
                "zmin": min(zs),
                "zmax": max(zs),
                "zspan": max(zs) - min(zs),
            }
        )
    log = min(stats, key=lambda s: s["zmin"])
    rest = [s for s in stats if s is not log]
    if len(rest) != 3:
        return {"log": log, "band": None, "head": None, "haft": None}
    band = min(rest, key=lambda s: s["zspan"])
    rest = [s for s in rest if s is not band]
    haft = max(rest, key=lambda s: s["zmax"])
    head = [s for s in rest if s is not haft][0]
    return {"log": log, "band": band, "head": head, "haft": haft}


def block_bvh(me, group):
    """BVH over the log shell only, so contact is measured against the wood."""
    member = set(group)
    verts = [tuple(v.co) for v in me.vertices]
    polys = [
        tuple(p.vertices)
        for p in me.polygons
        if all(i in member for i in p.vertices)
    ]
    return BVHTree.FromPolygons(verts, polys, all_triangles=False, epsilon=0.0)


def inside_block(bvh, point):
    """An odd hit count straight up means the point is inside the log."""
    origin = Vector(point)
    direction = Vector((0.0, 0.0, 1.0))
    hits = 0
    for _ in range(16):
        hit = bvh.ray_cast(origin, direction)
        if hit[0] is None:
            break
        hits += 1
        origin = hit[0] + direction * 1e-5
    return hits % 2 == 1


def joint_audit(me, groups):
    """Every named joint minimum, recomputed from vertex positions."""
    named = classify_shells(me, groups)
    out = {
        "parts": len(groups),
        "eye_clear": -1.0,
        "engage": -1.0,
        "inside": -1.0,
        "bury": -1.0,
        "bit_inset": -1.0,
        "band_bite_min": -1.0,
        "band_bite_max": 99.0,
        "haft_clear": -1.0,
        "haft_in_log": -1,
        "plumb": 99.0,
    }
    if any(named[k] is None for k in ("band", "head", "haft")):
        return out
    co = [v.co for v in me.vertices]
    log, band, head, haft = (named[k] for k in ("log", "band", "head", "haft"))

    # Plumb: the bottom and top quarters of the log must share an axis, or
    # the block leans. Measured over slabs, not over the exact zmax ring: a
    # notched rim has only a few vertices at its true maximum and their
    # centroid is meaningless.
    log_pts = [co[i] for i in log["idx"]]
    slab_h = 0.25 * (log["zmax"] - log["zmin"])
    bottom = [p for p in log_pts if p.z < log["zmin"] + slab_h]
    top = [p for p in log_pts if p.z > log["zmax"] - slab_h]
    if bottom and top:
        bc = sum(bottom, Vector()) / len(bottom)
        tc = sum(top, Vector()) / len(top)
        out["plumb"] = math.hypot(bc.x - tc.x, bc.y - tc.y)

    # Axe measurements run in the construction frame, un-spun by the azimuth,
    # so the head's own AABB is not inflated by the presentation rotation.
    unspin = Matrix.Rotation(-AXE_AZIMUTH, 3, "Z")
    f, s, eh, _haft_dir, poll, eye = axe_frame()
    head_pts = [unspin @ co[i] for i in head["idx"]]
    haft_pts = [unspin @ co[i] for i in haft["idx"]]
    eye_f = (eye - poll).dot(f)
    slab = 0.025
    head_slab = [p for p in head_pts if abs((p - poll).dot(f) - eye_f) < slab]
    haft_slab = [p for p in haft_pts if abs((p - poll).dot(f) - eye_f) < slab]
    if head_slab and haft_slab:
        out["eye_clear"] = max(abs(p.dot(s)) for p in head_slab) - max(
            abs(p.dot(s)) for p in haft_slab
        )
        head_hi = max(p.dot(eh) for p in head_slab)
        head_lo = min(p.dot(eh) for p in head_slab)
        haft_lo = min(p.dot(eh) for p in haft_slab)
        out["engage"] = head_hi - haft_lo
        out["inside"] = haft_lo - head_lo

    # The bit has to be in the wood, and well in from the rim.
    top_z = log["zmax"]
    buried = [p for p in (co[i] for i in head["idx"]) if p.z < top_z]
    if buried:
        out["bury"] = top_z - min(p.z for p in buried)
        out["bit_inset"] = BLOCK_R - max(math.hypot(p.x, p.y) for p in buried)

    # Band seat, measured per angular bin. A radius midpoint cannot separate
    # the hoop's inner face from its outer one on an out-of-round log — the
    # thin side's outer vertices sit inside the fat side's inner ones — so
    # bin by angle and ask how deep the hoop bites the wood at each angle.
    bvh = block_bvh(me, log["idx"])
    bins = [0.0] * BLOCK_SEGS
    step = 2.0 * math.pi / BLOCK_SEGS
    for i in band["idx"]:
        p = co[i]
        if not inside_block(bvh, p):
            continue
        b = int(round(math.atan2(p.y, p.x) / step)) % BLOCK_SEGS
        bins[b] = max(bins[b], bvh.find_nearest(p)[3])
    out["band_bite_min"] = min(bins)
    out["band_bite_max"] = max(bins)

    haft_world = [co[i] for i in haft["idx"]]
    out["haft_clear"] = min(bvh.find_nearest(p)[3] for p in haft_world)
    out["haft_in_log"] = sum(1 for p in haft_world if inside_block(bvh, p))
    return out


def add_stray_vert(me):
    # Falsification only: one unconnected vertex, placed inside the existing
    # bounds so the bbox budget still passes and hygiene is the gate that fires.
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, BLOCK_H * 0.5))
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()


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
    img = bpy.data.images.new("ChopBlockNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = WOOD_IDX
    return img, tex


def deselect_all():
    for ob in list(bpy.context.view_layer.objects):
        if ob is None:
            continue
        ob.select_set(False)


def bake_normal(high, low):
    # Duplicated from snippets/bake_normal_high_to_low.py (not a package).
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
    # Duplicated from snippets/export_preset_unity.py (not a package).
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


def check(skip_decimate, lift_z=False, stray_vert=False, fat_haft=False,
          round_band=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    haft_scale = FAT_HAFT_SCALE if fat_haft else 1.0
    low = build_chopping_block_mesh(
        "ChopBlockLow",
        detail=1,
        haft_scale=haft_scale,
        round_band=round_band,
    )
    high = build_chopping_block_mesh(
        "ChopBlockHigh",
        detail=HIGH_SEG_SCALE,
        haft_scale=haft_scale,
        round_band=round_band,
    )
    if lift_z:
        low.location.z += LIFT_Z
    if stray_vert:
        add_stray_vert(low.data)
    # world_bbox reads matrix_world, which is evaluated data. Without this the
    # cached matrix hides a moved object and the grounded budget cannot fail.
    bpy.context.view_layer.update()
    # The bark has to sit well below the sawn face or a flat-shaded log round
    # reads as a turned wooden drum: the pale top is the whole point of the
    # silhouette and it needs something dark to be pale against.
    wood = principled("ChopBlockBark", (0.105, 0.058, 0.028, 1.0), 0.0, 0.86)
    grain = principled("ChopBlockGrain", (0.560, 0.400, 0.215, 1.0), 0.0, 0.62)
    metal = principled("ChopBlockIron", (0.20, 0.196, 0.196, 1.0), 1.0, 0.34)
    assign_slots(low, wood, grain, metal)
    assign_slots(high, wood, grain, metal)

    if low.data is None or len(low.data.polygons) < 6:
        return fail("chopping block mesh did not build", 3), None, None, None, None, None

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
        return fail("chopping block has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "ChopBlockLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "ChopBlockLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_chopping_block_mesh(
        "ChopBlockColSrc",
        detail=1,
        haft_scale=haft_scale,
        round_band=round_band,
    )
    collider = convex_hull_collider(collider_src, "ChopBlockCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_chopping_block_{os.getpid()}.glb",
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
    hyg = hygiene_audit(low.data)
    zfight = zfight_pairs(low.data)
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zfight}"
    )
    groups = shells(low.data)
    joint = joint_audit(low.data, groups)
    log_stats = classify_shells(low.data, groups)["log"]
    log_pts = [low.data.vertices[i].co for i in log_stats["idx"]]
    log_dia = 2.0 * max(math.hypot(p.x, p.y) for p in log_pts)
    log_h = log_stats["zmax"] - log_stats["zmin"]
    print(
        f"measured joints parts={joint['parts']} eye_clear={joint['eye_clear']:.5f} "
        f"engage={joint['engage']:.5f} inside={joint['inside']:.5f} "
        f"bury={joint['bury']:.5f} bit_inset={joint['bit_inset']:.5f}"
    )
    print(
        f"measured contact band_bite={joint['band_bite_min']:.5f}"
        f"..{joint['band_bite_max']:.5f} "
        f"haft_clear={joint['haft_clear']:.5f} "
        f"haft_in_log={joint['haft_in_log']} plumb={joint['plumb']:.7f}"
    )
    print(f"measured log diameter={log_dia:.4f} height={log_h:.4f}")

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
    if idx_counts.get(WOOD_IDX, 0) < WOOD_FACES_MIN:
        return fail(
            f"bark faces {idx_counts.get(WOOD_IDX, 0)} < {WOOD_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(GRAIN_IDX, 0) < GRAIN_FACES_MIN:
        return fail(
            f"end-grain faces {idx_counts.get(GRAIN_IDX, 0)} < {GRAIN_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(METAL_IDX, 0) < METAL_FACES_MIN:
        return fail(
            f"metal faces {idx_counts.get(METAL_IDX, 0)} < {METAL_FACES_MIN}",
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
        or zfight
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zfight} "
            "(--stray-vert is the designed fail)",
            15,
        ), None, None, None, None, None
    if abs(bb[2]) > ZMIN_EPS:
        return fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ), None, None, None, None, None
    if joint["parts"] != PART_COUNT:
        return fail(
            f"shell count {joint['parts']} != {PART_COUNT}",
            17,
        ), None, None, None, None, None
    if joint["eye_clear"] < EYE_CLEARANCE_MIN:
        return fail(
            f"axe eye clearance {joint['eye_clear']:.5f} < {EYE_CLEARANCE_MIN} "
            "(--fat-haft is the designed fail)",
            17,
        ), None, None, None, None, None
    if joint["engage"] < HAFT_ENGAGE_MIN:
        return fail(
            f"haft engagement {joint['engage']:.5f} < {HAFT_ENGAGE_MIN}",
            17,
        ), None, None, None, None, None
    if joint["inside"] < HAFT_INSIDE_MIN:
        return fail(
            f"haft breakout margin {joint['inside']:.5f} < {HAFT_INSIDE_MIN}",
            17,
        ), None, None, None, None, None
    if joint["bury"] < BIT_BURY_MIN:
        return fail(
            f"bit bury depth {joint['bury']:.5f} < {BIT_BURY_MIN}",
            17,
        ), None, None, None, None, None
    if joint["bit_inset"] < BIT_INSET_MIN:
        return fail(
            f"bit inset from the rim {joint['bit_inset']:.5f} < {BIT_INSET_MIN}",
            17,
        ), None, None, None, None, None
    if (
        joint["band_bite_min"] < BAND_BITE_MIN
        or joint["band_bite_max"] > BAND_BITE_MAX
    ):
        return fail(
            f"band bite {joint['band_bite_min']:.5f}..{joint['band_bite_max']:.5f} "
            f"outside [{BAND_BITE_MIN}, {BAND_BITE_MAX}] "
            "(--round-band is the designed fail)",
            18,
        ), None, None, None, None, None
    if joint["haft_clear"] < HAFT_BLOCK_CLEAR_MIN or joint["haft_in_log"]:
        return fail(
            f"haft-to-log clearance {joint['haft_clear']:.5f} < "
            f"{HAFT_BLOCK_CLEAR_MIN} or {joint['haft_in_log']} haft vertices "
            "inside the log",
            18,
        ), None, None, None, None, None
    if joint["plumb"] > PLUMB_EPS:
        return fail(
            f"log axis out of plumb by {joint['plumb']:.7f} > {PLUMB_EPS}",
            19,
        ), None, None, None, None, None
    if (
        abs(log_dia - BLOCK_DIAMETER) > BLOCK_DIAMETER_TOL
        or abs(log_h - BLOCK_HEIGHT) > BLOCK_HEIGHT_TOL
    ):
        return fail(
            f"log ({log_dia:.4f} x {log_h:.4f}) off the stated "
            f"{BLOCK_DIAMETER} x {BLOCK_HEIGHT} chopping block",
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

    # Presentation spin. The head axis must land roughly square to the view
    # vector or the axe reads as a dark blob seen down its own length; the
    # haft then falls across frame as a diagonal instead of a vertical stick.
    low.rotation_euler.z = math.radians(2.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        # Oversized so no edge of the set can enter frame at any framing.
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

    light("Key", (-3.1, -4.3, 4.6), 900.0, 3.4, (1.0, 0.94, 0.86), (46, 0, -36))
    light("Fill", (5.0, -3.4, 2.4), 60.0, 8.0, (0.72, 0.82, 1.0), (62, 0, 50))
    light("Wedge", (2.35, 2.5, 1.55), 900.0, 2.4, (1.0, 0.68, 0.38), (-64, 0, 218))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.72, -2.34, 1.96)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.42)
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
        "--stray-vert",
        action="store_true",
        help="falsification: add a loose vertex so the hygiene budget fails",
    )
    p.add_argument(
        "--fat-haft",
        action="store_true",
        help="falsification: a haft as thick as the eye, failing joint fit",
    )
    p.add_argument(
        "--round-band",
        action="store_true",
        help="falsification: a circular hoop on an out-of-round log",
    )
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        fat_haft=args.fat_haft,
        round_band=args.round_band,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("chopping-block OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
