"""Game-ready chopping block — a showcase piece, not an example.

Asserts budget conformance of a procedural splitting block (a hooped log
round with a felling axe standing in it) after composing shipped pipeline
pieces: bmesh construction, UVs, four materials, high-to-low normal bake,
LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result. They
are not API-contract witnesses. Each falsifier violates exactly one named
budget: ``--skip-decimate`` skips the LOD DECIMATE stage so the LOD-ratio
budget fails, ``--lift-z`` moves the mesh off the floor so the grounded
budget fails, ``--stray-vert`` adds one unconnected vertex so the
mesh-hygiene budget fails, ``--fat-haft`` widens the handle to the full
thickness of the axe eye so the eye joint-fit budget fails,
``--round-band`` generates the iron band on a circle instead of on the
log's own surface so the band-seat budget fails, ``--float-rivets`` lifts
the lap rivets off the hoop so the rivet-seat budget fails, and
``--round-haft`` turns the oval handle round so the haft-section budget
fails.

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
    blender --background --python chopping_block.py -- --float-rivets
    blender --background --python chopping_block.py -- --round-haft
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
# Lap joint. A hoop is a strip of iron riveted where its ends overlap; a
# ring of constant section reads as a painted stripe. The outer end steps
# up sharply at LAP_U0, and the lap tapers out past LAP_U1 where the hidden
# end runs underneath. Every kink is its own band section, and none lands
# on a log segment at either detail level (10 and 5 degrees).
LAP_U0 = math.radians(302.5)
LAP_STEP = math.radians(1.0)
LAP_U1 = math.radians(316.5)
LAP_TAPER = math.radians(4.0)
LAP_T = 0.0025
# Two domed rivets through the lap, each on its own band section so the
# surface under it is exact rather than a chord.
RIVET_US = (math.radians(307.5), math.radians(312.5))
RIVET_R = 0.0062
RIVET_H = 0.0042
RIVET_BITE = 0.0015
RIVET_SEGS = 8
# (height as a fraction of RIVET_H, radius scale). The first ring is below
# the band surface by RIVET_BITE; that is the seat.
RIVET_RINGS = ((0.45, 0.86), (0.82, 0.52), (0.97, 0.22))
FLOAT_RIVET = 0.003

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
HAFT_SEGS = 16
# (t along the haft, half thickness across the cheeks). The shoulder-waist-
# swell spread is wide on purpose: a 0.68 m haft that runs 15 mm to 18 mm
# reads as dowel at any distance a viewer will see it from. The swell holds
# its width to within 2 mm of the butt and then rounds off: a knob that
# tapers the whole way to its end cap reads as a pencil stub.
HAFT_SECTIONS = (
    (0.00, 0.0192),
    (0.10, 0.0205),
    (0.32, 0.0150),
    (0.58, 0.0136),
    (0.78, 0.0150),
    (0.88, 0.0188),
    (0.94, 0.0226),
    (0.975, 0.0222),
    (0.993, 0.0192),
    (1.00, 0.0140),
)
# An axe handle is oval, wider in the swing plane than across the cheeks.
# A round section at any width is a broom handle.
HAFT_OVAL = 1.35
HAFT_OVAL_MIN = 1.25
HAFT_OVAL_MAX = 1.60
# The grip station the oval is measured at, as a fraction along the haft.
HAFT_GRIP_T = 0.58
# The knob hooks toward the bit, the other half of the S the bow starts.
HAFT_HOOK = 0.016
FAT_HAFT_SCALE = 1.85

# Six closed shells: log, iron band, axe head, axe haft, two rivets.
PART_COUNT = 4 + len(RIVET_US)
BBOX_TOL = 0.012
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.526, 0.526, 1.006)
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
# Rivet seat, measured radially at each rivet vertex's own angle against the
# band surface read off the mesh. A floor so the head cannot float off the
# lap, a ceiling so it cannot sink into it, and a proud minimum so the dome
# is actually visible.
RIVET_SEAT_MIN = 0.0008
RIVET_SEAT_MAX = 0.0025
RIVET_PROUD_MIN = 0.0025
RIVET_SPAN_MAX = 0.03

ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 0.0012
ZFIGHT_COS = 0.9995
LIFT_Z = 0.05

BASE_TRIS_MIN = 1730
BASE_TRIS_MAX = 1870
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 4
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 560
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
# Floors catch the slot-assignment wipe class and the bevel-inherits-slot-0
# class: the axe head's chamfers are claimed from the bevel op's own return,
# so a regression there drops the metal count well below this floor.
WOOD_FACES_MIN = 160
GRAIN_FACES_MIN = 90
METAL_FACES_MIN = 170
HAFT_FACES_MIN = 150

WOOD_IDX = 0
GRAIN_IDX = 1
METAL_IDX = 2
# The haft is hickory, not bark. Sharing the bark slot made the handle the
# darkest wood on the piece and would fissure it with the bark texture.
HAFT_IDX = 3

# End-grain shading. The pith sits off the geometric centre, as it does in
# nearly every real log; concentric rings about the exact centre read as a
# target. Checks are drawn at the same angles the geometry notches.
PITH = (0.021, -0.013)
RING_SCALE = 38.0
CHECK_W0 = 0.0010
CHECK_WIDEN = 0.012


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
    # Bark on the sides and down to the ground; pale end grain on both sawn
    # faces and the top rim. A pale bottom chamfer ran a light ring round
    # the floor line, which is the foot of a tub, not the butt of a log.
    bark = [face for row in rows[:body_rows - 1] for face in row]
    grain = list(rows[body_rows - 1])
    for row in rows[body_rows:]:
        grain.extend(row)
    for cap in caps:
        grain.extend(cap)
    return verts, bark, grain


def lap_thickness(u):
    """Extra outer thickness of the hoop's lap joint at angle u."""
    d = (u - LAP_U0) % (2.0 * math.pi)
    span = LAP_U1 - LAP_U0
    if d <= LAP_STEP:
        return LAP_T * d / LAP_STEP
    if d <= span:
        return LAP_T
    if d <= span + LAP_TAPER:
        return LAP_T * (1.0 - (d - span) / LAP_TAPER)
    return 0.0


def band_mean_radius(segs):
    mid_z = 0.5 * (BAND_Z0 + BAND_Z1)
    return sum(
        log_radius(i * (2.0 * math.pi / segs), mid_z) for i in range(segs)
    ) / segs


def band_host_radii(u, round_band, mean_r):
    """Log radius the hoop is built on, at its bottom and top edge."""
    if round_band:
        return mean_r, mean_r
    return log_radius(u, BAND_Z0), log_radius(u, BAND_Z1)


def band_outer_radius(u, z, round_band, mean_r):
    """The hoop's outer face at angle u and height z, lap included."""
    r0, r1 = band_host_radii(u, round_band, mean_r)
    za = BAND_Z0 + BAND_CHAMFER
    zb = BAND_Z1 - BAND_CHAMFER
    k = (z - za) / (zb - za)
    return r0 + (r1 - r0) * k + BAND_PROUD + lap_thickness(u)


def band_angles(segs):
    """Log-segment angles plus every kink of the lap and every rivet."""
    us = {i * (2.0 * math.pi / segs) for i in range(segs)}
    us.update(
        (
            LAP_U0,
            LAP_U0 + LAP_STEP,
            LAP_U1,
            LAP_U1 + LAP_TAPER,
        )
    )
    us.update(RIVET_US)
    return sorted(u % (2.0 * math.pi) for u in us)


def build_band(bm, segs, round_band):
    """Iron hoop, generated on the log's own surface.

    ``round_band`` is the falsifier: the hoop is generated on a circle of
    the mean radius instead, which is exactly what made the old torus sink
    into the wood on one side and float off it on the other.
    """
    mean_r = band_mean_radius(segs)
    sections = []
    c = BAND_CHAMFER
    for u in band_angles(segs):
        cu, su = math.cos(u), math.sin(u)
        r0, r1 = band_host_radii(u, round_band, mean_r)
        lap = lap_thickness(u)
        profile = (
            (r0 - BAND_BITE, BAND_Z0),
            (r0 + BAND_PROUD + lap - c, BAND_Z0),
            (r0 + BAND_PROUD + lap, BAND_Z0 + c),
            (r1 + BAND_PROUD + lap, BAND_Z1 - c),
            (r1 + BAND_PROUD + lap - c, BAND_Z1),
            (r1 - BAND_BITE, BAND_Z1),
        )
        sections.append([Vector((r * cu, r * su, z)) for r, z in profile])
    return loft_cyclic(bm, sections)


def build_rivets(bm, segs, round_band, float_out):
    """Domed rivet heads through the lap, seated into the band's own face.

    Each head is placed from ``band_outer_radius`` at its own angle, which
    is a band section, so the seat is measured against the exact surface.
    ``float_out`` is the falsifier: it moves every head off the lap.
    """
    mean_r = band_mean_radius(segs)
    zc = 0.5 * (BAND_Z0 + BAND_Z1)

    def surface_point(u, z):
        r = band_outer_radius(u, z, round_band, mean_r)
        return Vector((r * math.cos(u), r * math.sin(u), z))

    verts, faces = [], []
    for u in RIVET_US:
        # Aim the head down the band's own surface normal. The log is out
        # of round, so its surface is not square to the radial: across one
        # head the radius falls 1.4 mm, and a radially aimed head sank on
        # one side and lifted on the other.
        eps = 1e-4
        du = surface_point(u + eps, zc) - surface_point(u - eps, zc)
        dz = surface_point(u, zc + eps) - surface_point(u, zc - eps)
        normal = du.cross(dz).normalized()
        if normal.dot(Vector((math.cos(u), math.sin(u), 0.0))) < 0.0:
            normal = -normal
        tang = du.normalized()
        up = normal.cross(tang).normalized()
        center = surface_point(u, zc) + normal * float_out
        stations = ((-RIVET_BITE / RIVET_H, 1.0),) + RIVET_RINGS
        rings = []
        for h, scale in stations:
            ring = []
            for i in range(RIVET_SEGS):
                a = i * (2.0 * math.pi / RIVET_SEGS)
                offset = (tang * math.cos(a) + up * math.sin(a)) * (RIVET_R * scale)
                ring.append(center + normal * (h * RIVET_H) + offset)
            rings.append(ring)
        v, rows, caps = loft(bm, rings)
        verts.extend(v)
        faces.extend(face for row in rows for face in row)
        faces.extend(face for cap in caps for face in cap)
    return verts, faces


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


def haft_curve():
    """Start, control and end points of the haft's centreline Bezier."""
    _f, _s, _eh, haft, _poll, eye = axe_frame()
    start = eye - haft * HAFT_DROP
    end = eye + haft * HAFT_LEN
    # A straight stick reads as a broom. The bow is a quadratic Bezier
    # leaning away from the bit, the way a hung haft curves.
    bit_dir = Vector((math.cos(AXE_BIT_ANGLE), 0.0, math.sin(AXE_BIT_ANGLE)))
    mid = (start + end) * 0.5 - bit_dir * HAFT_BOW
    return start, mid, end


def haft_point(t):
    start, mid, end = haft_curve()
    omt = 1.0 - t
    p = start * (omt * omt) + mid * (2.0 * omt * t) + end * (t * t)
    dp = (mid - start) * (2.0 * omt) + (end - mid) * (2.0 * t)
    return p, dp.normalized()


def haft_rings(scale, segs, oval=HAFT_OVAL):
    f, s, _eh, _haft, _poll, _eye = axe_frame()
    rings = []
    for t, radius in HAFT_SECTIONS:
        p, tangent = haft_point(t)
        side = s.cross(tangent).normalized()
        up = tangent.cross(side).normalized()
        # The knob hooks toward the bit: smoothstep in over the last fifth.
        k = min(1.0, max(0.0, (t - 0.80) / 0.20))
        hook = HAFT_HOOK * k * k * (3.0 - 2.0 * k)
        p = p + side * (hook if side.dot(f) > 0.0 else -hook)
        # ``side`` lies in the swing plane, ``up`` across the cheeks; the
        # oval is wide along the first and keeps the eye fit on the second.
        # ``scale`` thickens across the cheeks only: that is the dimension
        # the eye has to clear, and the one --fat-haft breaks. Scaling the
        # swing-plane width too grew the knob past the bounding box, so
        # the falsifier failed exit 8 instead of its own budget.
        ring = []
        for i in range(segs):
            a = i * (2.0 * math.pi / segs)
            ring.append(
                p
                + side * (radius * oval * math.cos(a))
                + up * (radius * scale * math.sin(a))
            )
        rings.append(ring)
    return rings


def build_haft(bm, scale, segs, oval=HAFT_OVAL):
    verts, rows, caps = loft(bm, haft_rings(scale, segs, oval))
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


def build_chopping_block_mesh(name, detail=1, haft_scale=1.0, round_band=False,
                              haft_oval=HAFT_OVAL, float_rivets=0.0):
    log_segs = BLOCK_SEGS * detail
    haft_segs = HAFT_SEGS * detail
    chamfer_segs = HIGH_CHAMFER_SEGS if detail > 1 else 1
    bm = bmesh.new()
    try:
        _log_verts, bark_faces, grain_faces = build_log(bm, log_segs)
        _band_verts, band_faces = build_band(bm, log_segs, round_band)
        _rivet_verts, rivet_faces = build_rivets(
            bm, log_segs, round_band, float_rivets
        )
        head_verts, head_faces = build_head(bm, chamfer_segs)
        haft_verts, haft_faces = build_haft(
            bm, haft_scale, haft_segs, haft_oval
        )

        # The axe is built in the XZ plane so the frame maths stays readable.
        spin = Matrix.Rotation(AXE_AZIMUTH, 3, "Z")
        for v in head_verts + haft_verts:
            v.co = spin @ v.co

        metal = set(band_faces) | set(head_faces) | set(rivet_faces)
        grain = set(grain_faces)
        haft = set(haft_faces)
        # Only the axe head is faceted. Flat-shading the log made its 36
        # equal facets read as coopered staves and the block as a tub, and
        # flat-shading the hoop threw a separate highlight off every facet,
        # a row of piano keys. The wobble still reads in the silhouette;
        # the bark and the end grain carry their surface in the material.
        # Hard edges come from the crease angle and from every material
        # boundary, so the sawn rim stays a crisp edge against the bark.
        flat = set(head_faces)

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            if face in metal:
                face.material_index = METAL_IDX
            elif face in grain:
                face.material_index = GRAIN_IDX
            elif face in haft:
                face.material_index = HAFT_IDX
            else:
                face.material_index = WOOD_IDX
            face.smooth = face not in flat
        for edge in bm.edges:
            edge.smooth = True
            if edge.is_manifold and len(edge.link_faces) == 2:
                fa, fb = edge.link_faces
                if (
                    edge.calc_face_angle() > math.radians(40.0)
                    or fa.material_index != fb.material_index
                ):
                    edge.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def enabled_socket(sockets, name):
    """The one enabled socket called ``name``.

    Mix and Map Range carry a socket of each data type under one name, and
    their identifiers changed in 5.2; the enabled one is unambiguous on
    every version.
    """
    for sock in sockets:
        if sock.name == name and sock.enabled:
            return sock
    raise KeyError(f"no enabled socket {name!r}")


def surface(name, metallic):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = metallic
    coord = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    return mat, nt, bsdf, coord


def mapping(nt, vec, scale=(1.0, 1.0, 1.0), loc=(0.0, 0.0, 0.0)):
    node = nt.nodes.new("ShaderNodeMapping")
    node.inputs["Scale"].default_value = scale
    node.inputs["Location"].default_value = loc
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Vector"]


def noise(nt, vec, scale, detail, roughness):
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = roughness
    nt.links.new(vec, node.inputs["Vector"])
    return node.outputs["Fac"]


def ramp(nt, fac, stops):
    """Colour ramp over (position, rgb) stops, ascending."""
    node = nt.nodes.new("ShaderNodeValToRGB")
    els = node.color_ramp.elements
    els[0].position = stops[0][0]
    els[0].color = (*stops[0][1], 1.0)
    els[1].position = stops[-1][0]
    els[1].color = (*stops[-1][1], 1.0)
    for pos, rgb in stops[1:-1]:
        els.new(pos).color = (*rgb, 1.0)
    nt.links.new(fac, node.inputs["Fac"])
    return node.outputs["Color"]


def remap(nt, value, from_lo, from_hi, to_lo, to_hi):
    node = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(value, enabled_socket(node.inputs, "Value"))
    enabled_socket(node.inputs, "From Min").default_value = from_lo
    enabled_socket(node.inputs, "From Max").default_value = from_hi
    enabled_socket(node.inputs, "To Min").default_value = to_lo
    enabled_socket(node.inputs, "To Max").default_value = to_hi
    return enabled_socket(node.outputs, "Result")


def math_node(nt, op, *inputs):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    for i, value in enumerate(inputs):
        if isinstance(value, (int, float)):
            node.inputs[i].default_value = value
        else:
            nt.links.new(value, node.inputs[i])
    return node.outputs[0]


def mix_color(nt, a, b, fac):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    nt.links.new(fac, enabled_socket(node.inputs, "Factor"))
    for name, value in (("A", a), ("B", b)):
        sock = enabled_socket(node.inputs, name)
        if isinstance(value, tuple):
            sock.default_value = (*value, 1.0)
        else:
            nt.links.new(value, sock)
    return enabled_socket(node.outputs, "Result")


def bark_material():
    mat, nt, bsdf, coord = surface("ChopBlockBark", 0.0)
    # Fissures run up the trunk: the noise is squeezed round the girth and
    # stretched along it, so ridges and furrows come out vertical. At an
    # 11:1 stretch the streaks were fine enough to read as planed timber;
    # 4:1 at this scale gives furrows a few centimetres apart.
    plates = noise(nt, mapping(nt, coord, scale=(8.0, 8.0, 2.0)), 3.0, 8.0, 0.64)
    nt.links.new(
        ramp(
            nt,
            plates,
            (
                (0.40, (0.016, 0.010, 0.006)),
                (0.50, (0.058, 0.036, 0.021)),
                (0.62, (0.105, 0.066, 0.039)),
                (0.80, (0.150, 0.100, 0.062)),
            ),
        ),
        bsdf.inputs["Base Color"],
    )
    nt.links.new(remap(nt, plates, 0.35, 0.8, 1.0, 0.78), bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.85
    bump.inputs["Distance"].default_value = 0.02
    nt.links.new(plates, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def grain_material():
    mat, nt, bsdf, coord = surface("ChopBlockGrain", 0.0)
    # Growth rings about an off-centre pith, flattened onto the sawn face.
    flat = mapping(nt, coord, scale=(1.0, 1.0, 0.0), loc=(-PITH[0], -PITH[1], 0.0))
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.rings_direction = "SPHERICAL"
    wave.inputs["Scale"].default_value = RING_SCALE
    wave.inputs["Distortion"].default_value = 2.6
    wave.inputs["Detail"].default_value = 3.0
    nt.links.new(flat, wave.inputs["Vector"])
    rings = ramp(
        nt,
        wave.outputs["Fac"],
        (
            (0.30, (0.600, 0.450, 0.265)),
            (0.72, (0.520, 0.370, 0.205)),
            (0.95, (0.400, 0.268, 0.140)),
        ),
    )
    weather = noise(nt, coord, 6.0, 4.0, 0.55)
    base = mix_color(
        nt, rings, (0.330, 0.250, 0.170), remap(nt, weather, 0.45, 0.75, 0.0, 0.45)
    )
    # Radial checks at the angles the geometry notches, widening toward the
    # rim and fading out before the pith, as a drying check does.
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord, sep.inputs["Vector"])
    x, y = sep.outputs["X"], sep.outputs["Y"]
    ang = math_node(nt, "ARCTAN2", y, x)
    rad = math_node(
        nt, "SQRT", math_node(nt, "MULTIPLY_ADD", x, x, math_node(nt, "MULTIPLY", y, y))
    )
    width = math_node(nt, "MULTIPLY_ADD", rad, CHECK_WIDEN, CHECK_W0)
    nearest = None
    for angle, _depth in TOP_CRACKS:
        wrapped = math_node(
            nt, "WRAP", math_node(nt, "SUBTRACT", ang, angle), math.pi, -math.pi
        )
        arc = math_node(nt, "MULTIPLY", math_node(nt, "ABSOLUTE", wrapped), rad)
        q = math_node(nt, "DIVIDE", arc, width)
        nearest = q if nearest is None else math_node(nt, "MINIMUM", nearest, q)
    line = remap(nt, nearest, 0.0, 1.0, 1.0, 0.0)
    fade = remap(nt, rad, 0.22 * BLOCK_R, 0.55 * BLOCK_R, 0.0, 1.0)
    crack = math_node(nt, "MULTIPLY", line, fade)
    nt.links.new(
        mix_color(nt, base, (0.050, 0.032, 0.020), crack), bsdf.inputs["Base Color"]
    )
    nt.links.new(
        remap(nt, wave.outputs["Fac"], 0.0, 1.0, 0.58, 0.74), bsdf.inputs["Roughness"]
    )
    return mat


def iron_material():
    mat, nt, bsdf, coord = surface("ChopBlockIron", 1.0)
    # Forged iron is never one grey: mill scale, polish where it is handled
    # and struck, and a little rust in the low spots.
    # Fine and low in contrast: at a coarser scale the blotches read as
    # marbling, not as scale on forged metal.
    blot = noise(nt, coord, 45.0, 6.0, 0.6)
    nt.links.new(
        ramp(
            nt,
            blot,
            (
                (0.40, (0.085, 0.082, 0.079)),
                (0.60, (0.140, 0.136, 0.131)),
                (0.72, (0.130, 0.100, 0.076)),
                (0.82, (0.180, 0.096, 0.052)),
            ),
        ),
        bsdf.inputs["Base Color"],
    )
    nt.links.new(remap(nt, blot, 0.35, 0.8, 0.34, 0.60), bsdf.inputs["Roughness"])
    nt.links.new(remap(nt, blot, 0.66, 0.80, 1.0, 0.35), bsdf.inputs["Metallic"])
    return mat


def haft_material():
    mat, nt, bsdf, coord = surface("ChopBlockHaft", 0.0)
    # Oiled hickory: lighter than the bark by a clear margin, with handling
    # grime breaking the colour up.
    grime = noise(nt, coord, 24.0, 5.0, 0.55)
    nt.links.new(
        ramp(
            nt,
            grime,
            (
                (0.35, (0.300, 0.170, 0.075)),
                (0.55, (0.420, 0.262, 0.120)),
                (0.75, (0.480, 0.318, 0.155)),
            ),
        ),
        bsdf.inputs["Base Color"],
    )
    nt.links.new(remap(nt, grime, 0.3, 0.8, 0.62, 0.42), bsdf.inputs["Roughness"])
    return mat


def block_materials():
    """Materials in slot order: bark, end grain, iron, haft."""
    return bark_material(), grain_material(), iron_material(), haft_material()


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
        spans = [
            max(p[k] for p in pts) - min(p[k] for p in pts) for k in range(3)
        ]
        zs = [p.z for p in pts]
        stats.append(
            {
                "idx": group,
                "zmin": min(zs),
                "zmax": max(zs),
                "zspan": max(zs) - min(zs),
                "span": max(spans),
            }
        )
    # Rivets are the only shells a few centimetres across.
    rivets = [s for s in stats if s["span"] < RIVET_SPAN_MAX]
    parts = [s for s in stats if s["span"] >= RIVET_SPAN_MAX]
    log = min(parts, key=lambda s: s["zmin"])
    rest = [s for s in parts if s is not log]
    if len(rest) != 3:
        return {
            "log": log, "band": None, "head": None, "haft": None,
            "rivets": rivets,
        }
    band = min(rest, key=lambda s: s["zspan"])
    rest = [s for s in rest if s is not band]
    haft = max(rest, key=lambda s: s["zmax"])
    head = [s for s in rest if s is not haft][0]
    return {
        "log": log, "band": band, "head": head, "haft": haft, "rivets": rivets,
    }


def band_outer_hit(bvh, u, z):
    """Radius of the band's outer face at angle u and height z, read off
    the mesh by casting from the axis and keeping the farthest hit."""
    direction = Vector((math.cos(u), math.sin(u), 0.0))
    origin = Vector((0.0, 0.0, z))
    outer = None
    for _ in range(16):
        hit = bvh.ray_cast(origin, direction)
        if hit[0] is None:
            break
        outer = math.hypot(hit[0].x, hit[0].y)
        origin = hit[0] + direction * 1e-5
    return outer


def rivet_seats(me, band, rivets):
    """(deepest seat, least proud) per rivet, measured radially at each
    vertex's own angle against the band surface, never nearest-surface."""
    bvh = block_bvh(me, band["idx"])
    co = [v.co for v in me.vertices]
    out = []
    for rivet in rivets:
        depths = []
        for i in rivet["idx"]:
            p = co[i]
            outer = band_outer_hit(bvh, math.atan2(p.y, p.x), p.z)
            if outer is None:
                depths = None
                break
            depths.append(outer - math.hypot(p.x, p.y))
        if depths is None:
            out.append((-1.0, -1.0))
        else:
            out.append((max(depths), -min(depths)))
    return out


def haft_oval(haft_pts):
    """Width across the swing plane over thickness across the cheeks, at the
    grip station, in the construction frame. Vertices are taken from a thin
    slab round the station so exactly one section ring is measured."""
    _f, s, _eh, _haft, _poll, _eye = axe_frame()
    p0, tangent = haft_point(HAFT_GRIP_T)
    swing = s.cross(tangent).normalized()
    slab = [q for q in haft_pts if abs((q - p0).dot(tangent)) < 0.004]
    if not slab:
        return 0.0
    c = sum(slab, Vector()) / len(slab)
    thick = max(abs((q - c).dot(s)) for q in slab)
    wide = max(abs((q - c).dot(swing)) for q in slab)
    return wide / thick if thick > 0.0 else 0.0


def block_bvh(me, group):
    """BVH over one shell only, so contact is measured against that part."""
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
        "rivet_seats": [],
        "haft_oval": 0.0,
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
    out["rivet_seats"] = rivet_seats(me, band, named["rivets"])
    out["haft_oval"] = haft_oval(haft_pts)
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
          round_band=False, round_haft=False, float_rivets=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    shape = {
        "haft_scale": FAT_HAFT_SCALE if fat_haft else 1.0,
        "round_band": round_band,
        "haft_oval": 1.0 if round_haft else HAFT_OVAL,
        "float_rivets": FLOAT_RIVET if float_rivets else 0.0,
    }
    low = build_chopping_block_mesh("ChopBlockLow", detail=1, **shape)
    high = build_chopping_block_mesh(
        "ChopBlockHigh", detail=HIGH_SEG_SCALE, **shape
    )
    if lift_z:
        low.location.z += LIFT_Z
    if stray_vert:
        add_stray_vert(low.data)
    # world_bbox reads matrix_world, which is evaluated data. Without this the
    # cached matrix hides a moved object and the grounded budget cannot fail.
    bpy.context.view_layer.update()
    # The bark has to sit well below the sawn face or a log round reads as
    # a turned wooden drum: the pale top is the whole point of the
    # silhouette and it needs something dark to be pale against.
    mats = block_materials()
    wood = mats[WOOD_IDX]
    assign_slots(low, *mats)
    assign_slots(high, *mats)

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

    collider_src = build_chopping_block_mesh("ChopBlockColSrc", detail=1, **shape)
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
    # Blender points TMPDIR at its own temp preference, which is the working
    # directory on a stock portable build, so gettempdir() can be the repo
    # root. Remove the file once it is measured rather than leaving it there.
    if os.path.isfile(export_path):
        os.remove(export_path)

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
    seats = joint["rivet_seats"]
    print(
        "measured rivets "
        + " ".join(f"seat={a:.5f},proud={b:.5f}" for a, b in seats)
        + f" haft_oval={joint['haft_oval']:.4f}"
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
    if idx_counts.get(HAFT_IDX, 0) < HAFT_FACES_MIN:
        return fail(
            f"haft faces {idx_counts.get(HAFT_IDX, 0)} < {HAFT_FACES_MIN}",
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
    if len(seats) != len(RIVET_US) or any(
        not (RIVET_SEAT_MIN <= seat <= RIVET_SEAT_MAX) or proud < RIVET_PROUD_MIN
        for seat, proud in seats
    ):
        return fail(
            "rivet seats "
            + ", ".join(f"{a:.5f} (proud {b:.5f})" for a, b in seats)
            + f" outside [{RIVET_SEAT_MIN}, {RIVET_SEAT_MAX}] or proud < "
            f"{RIVET_PROUD_MIN} (--float-rivets is the designed fail)",
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
    if not (HAFT_OVAL_MIN <= joint["haft_oval"] <= HAFT_OVAL_MAX):
        return fail(
            f"haft section {joint['haft_oval']:.4f} wide-to-thick outside "
            f"[{HAFT_OVAL_MIN}, {HAFT_OVAL_MAX}]: a round haft is a broom "
            "handle (--round-haft is the designed fail)",
            19,
        ), None, None, None, None, None
    return 0, low, high, wood, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    # The bark's fissure bump sits on top of the baked normal, not instead
    # of it.
    bump = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeBump"), None)
    target = bump.inputs["Normal"] if bump else bsdf.inputs["Normal"]
    nt.links.new(nrm.outputs["Normal"], target)


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
    p.add_argument(
        "--round-haft",
        action="store_true",
        help="falsification: a round haft section, failing the oval budget",
    )
    p.add_argument(
        "--float-rivets",
        action="store_true",
        help="falsification: rivet heads lifted off the lap, failing their seat",
    )
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        fat_haft=args.fat_haft,
        round_band=args.round_band,
        round_haft=args.round_haft,
        float_rivets=args.float_rivets,
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
