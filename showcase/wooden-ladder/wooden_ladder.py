"""Game-ready wooden ladder — a showcase piece, not an example.

Asserts budget conformance of a procedural timber ladder after composing
shipped pipeline pieces: bmesh construction, UVs, two materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates exactly one
named budget: ``--skip-decimate`` skips the LOD DECIMATE stage so the
LOD-ratio budget fails, ``--lift-z`` moves the mesh off the floor so the
grounded budget fails, ``--stray-vert`` adds one unconnected vertex so the
mesh-hygiene budget fails, ``--twin-sole`` duplicates a shoe plate so the
coplanar-face budget fails, ``--fat-rungs`` widens the tenons to the full
stile depth so the rung-to-stile joint-fit budget fails,
``--drift-rungs`` restores the old jittered rung heights so the rung-pitch
budget fails, ``--short-stile`` starts the rail above the sleeve so the
shoe-bite budget fails, and ``--float-nuts`` backs the tie-rod nuts off
their washers so the tie-rod seat budget fails.

Construction is closed-form; the only RNG is the seeded per-piece wood
tone. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python wooden_ladder.py --
    blender --background --python wooden_ladder.py -- --skip-decimate
    blender --background --python wooden_ladder.py -- --lift-z
    blender --background --python wooden_ladder.py -- --stray-vert
    blender --background --python wooden_ladder.py -- --fat-rungs
    blender --background --python wooden_ladder.py -- --short-stile
    blender --background --python wooden_ladder.py -- --twin-sole
    blender --background --python wooden_ladder.py -- --drift-rungs
    blender --background --python wooden_ladder.py -- --float-nuts
    blender --background --python wooden_ladder.py -- --output preview.webp
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

# Showcase lives at repo-root/showcase/, not under examples/. The framing
# helper is the repo's only shared import and lives next to the examples;
# resolve the repo root so we do not move gallery_framing.py.
_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402
import gallery_asset_quality  # noqa: E402

STILE_H = 1.50
STILE_W_BOT = 0.064
STILE_W_TOP = 0.050
STILE_D = 0.038
CENTER = 0.198
N_RUNGS = 6
# Tenon stays inside the chamfer. The visible barrel is wider and stops
# outside the stile, so the two radii are different stations.
RUNG_R = 0.011
BARREL_RATIO = 1.34
RUNG_SEGS = 12
# Through-wedged: each tenon runs right through its rail and stands
# TENON_PROUD past the outer face, where its end grain shows.
TENON_PROUD = 0.002
RUNG_SHOULDER = 0.90             # barrel radius at the shoulders, x r_barrel
RUNG_SWELL = 1.14                # barrel radius at mid-span, x r_barrel
# Rungs sit at one even pitch: a climber's feet find them blind, so height
# jitter is a defect, not variation. Variation lives in the turning (a few
# percent of barrel) and the wood tone. --drift-rungs restores the old
# jittered heights; the rung-pitch budget (exit 19) catches it.
RUNG_BARREL_SCALE = (1.00, 1.04, 0.97, 1.03, 0.98, 1.02)
DRIFT_Z_OFFSETS = (0.0, 0.016, -0.012, 0.014, -0.018, 0.008)
RUNG_PITCH_TOL = 0.002
# Per-piece wood tone jitter and grain frequency, as in shipping-crate.
PLANK_TONE_JITTER = 0.28
TONE_SEED = 29
WOOD_GRAIN_SCALE = 95.0
BAND_Z0 = 0.0
BAND_H = 0.058
BAND_T = 0.007
RAIL_Z0 = 0.020
CAP_DROP = 0.010
CAP_RISE = 0.016
PLATE_H = 0.006
SOLE_H = 0.032
SOLE_PAD = 0.008
RAKE = math.radians(12.0)
BBOX_TOL = 0.01
# 2 stiles + 6 rungs + 2 shoe sleeves + 2 cap sleeves + 2 cap plates + 2 soles
# + 2 iron tie-rods + 4 washers + 4 square nuts.
PART_COUNT = 26
# Iron tie-rods run through both stiles just under the bottom and top rungs,
# the rod every wooden ladder carries to keep the rails from spreading off
# the tenons. Each end is clamped by a square nut over a round washer bedded
# on the stile's outer face.
TIE_RUNGS = (0, N_RUNGS - 1)     # rung indices the rods sit under
TIE_DROP = 0.036                 # rod axis below the rung axis
TIE_R = 0.0065
TIE_SEGS = 8
TIE_PROUD = 0.016                # rod end past the stile outer face
WASHER_R = 0.016
WASHER_T = 0.0025
WASHER_SEGS = 12
NUT_HALF = 0.0125                # half the square nut's flat-to-flat width
NUT_T = 0.010                    # nut thickness along the rod
SEAT_SINK = 0.0005               # washer into the wood, nut into the washer
SEAT_BITE_MIN = 0.0002           # seated: each bearing face at least this far in
SEAT_BITE_MAX = 0.0020           # ... and not buried deeper than this
NUT_AXIS_TOL = 0.0015            # washer / nut centre on the rod axis (y, z)
TIE_THROUGH_MIN = 0.003          # rod thread end proud of each nut's outer face
FLOAT_NUTS = 0.004               # --float-nuts: nuts backed off their washers
RUNG_DEPTH_CLEARANCE = 0.003
TENON_ENGAGE_MIN = 0.008
TENON_PROUD_MIN = 0.001          # through: tenon end past the outer face
TENON_PROUD_MAX = 0.004          # ... and not a stub sticking out
SHOE_BITE_MIN = 0.010
SHOE_COVER_MIN = 0.016
RAIL_ZMIN_MIN = 0.012
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 0.002
ZFIGHT_COS = 0.98
LIFT_Z = 0.05
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.490, 0.376, 1.487)

BASE_TRIS_MIN = 1800
# Raised from 2800 for the two tie-rods, four washers and four nuts (+320 tris);
# the old ceiling left 120 triangles of headroom, less than the hardware.
BASE_TRIS_MAX = 3100
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
# The caps and shoes carry far more chamfer than body faces, so a floor above
# their 24 unbevelled box faces is what catches a bevel whose new faces fell
# back to the wood slot.
METAL_FACES_MIN = 180
WOOD_FACES_MIN = 280

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
    # Duplicated from snippets/lod_chain.py / decimate_to_budget.py (not a package).
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
        cap_tris=True,
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


def add_cylinder(bm, loc, radius, depth, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    return add_cone(bm, loc, radius, radius, depth, segments, mat_idx, euler=euler)


def half_w(z):
    t = min(1.0, max(0.0, z / STILE_H))
    return 0.5 * (STILE_W_BOT + (STILE_W_TOP - STILE_W_BOT) * t)


def inner_x(z, sign):
    x = sign * CENTER
    hw = half_w(z)
    return x + hw if sign < 0.0 else x - hw


def add_ruled_box(bm, x, z0, z1, hw0, hw1, hd, mat_idx):
    """Tapered box. Width is the local X half-extent at each end; depth is constant."""

    def ring(z, hw):
        return [
            bm.verts.new((x - hw, -hd, z)),
            bm.verts.new((x + hw, -hd, z)),
            bm.verts.new((x + hw, hd, z)),
            bm.verts.new((x - hw, hd, z)),
        ]

    bottom = ring(z0, hw0)
    top = ring(z1, hw1)

    def quad(a, b, c, d):
        face = bm.faces.new((a, b, c, d))
        face.material_index = mat_idx
        return face

    for i in range(4):
        j = (i + 1) % 4
        quad(bottom[i], bottom[j], top[j], top[i])
    quad(bottom[3], bottom[2], bottom[1], bottom[0])
    quad(top[0], top[1], top[2], top[3])
    return bottom + top


def add_rect_band(bm, zc, cx, hx, hy, tx, ty, h, mat_idx):
    """Closed rectangular collar, constant section, axis along local Z."""
    z0 = zc - h * 0.5
    z1 = zc + h * 0.5
    inner = (
        (cx + hx, hy),
        (cx - hx, hy),
        (cx - hx, -hy),
        (cx + hx, -hy),
    )
    outer = (
        (cx + hx + tx, hy + ty),
        (cx - hx - tx, hy + ty),
        (cx - hx - tx, -(hy + ty)),
        (cx + hx + tx, -(hy + ty)),
    )

    def ring(z, pts):
        return [bm.verts.new((p[0], p[1], z)) for p in pts]

    i0, o0 = ring(z0, inner), ring(z0, outer)
    i1, o1 = ring(z1, inner), ring(z1, outer)

    def quad(a, b, c, d):
        face = bm.faces.new((a, b, c, d))
        face.material_index = mat_idx
        return face

    for k in range(4):
        n = (k + 1) % 4
        quad(i0[k], i0[n], i1[n], i1[k])
        quad(o0[k], o1[k], o1[n], o0[n])
        quad(i0[k], o0[k], o0[n], i0[n])
        quad(i1[k], i1[n], o1[n], o1[k])
    return i0 + o0 + i1 + o1


def add_turned_rung(bm, z, x_left, x_right, tenon, r_tenon, r_barrel, segs, mat_idx):
    """One shell: thin tenon inside each stile, thicker barrel only in the clear span.

    The barrel is turned, not a plain dowel: it starts at a shoulder just
    under the barrel radius and swells to RUNG_SWELL at mid-span, the
    profile a lathe leaves on a ladder round (one extra ring per rung).
    """
    # the inboard tenon ring sits 4 mm inside the rail so the joint audit
    # always samples tenon section inside the wood (the end is past it)
    xs = (
        x_left - tenon,
        x_left - 0.004,
        x_left + 0.004,
        0.5 * (x_left + x_right),
        x_right - 0.004,
        x_right + 0.004,
        x_right + tenon,
    )
    shoulder = r_barrel * RUNG_SHOULDER
    rs = (r_tenon, r_tenon, shoulder, r_barrel * RUNG_SWELL, shoulder, r_tenon, r_tenon)
    rings = []
    for x, radius in zip(xs, rs):
        ring = []
        for i in range(segs):
            ang = i * (2.0 * math.pi / segs)
            ring.append(bm.verts.new((
                x,
                radius * math.cos(ang),
                z + radius * math.sin(ang),
            )))
        rings.append(ring)
    bm.verts.ensure_lookup_table()

    def face(verts):
        poly = bm.faces.new(verts)
        poly.material_index = mat_idx
        return poly

    for i in range(len(rings) - 1):
        for j in range(segs):
            j2 = (j + 1) % segs
            face((rings[i][j], rings[i][j2], rings[i + 1][j2], rings[i + 1][j]))
    for ring, x, radius, outward in (
        (rings[0], xs[0], rs[0], -1.0),
        (rings[-1], xs[-1], rs[-1], 1.0),
    ):
        cap = bm.verts.new((x, 0.0, z))
        for j in range(segs):
            j2 = (j + 1) % segs
            if outward < 0.0:
                face((cap, ring[j2], ring[j]))
            else:
                face((cap, ring[j], ring[j2]))
    return [v for ring in rings for v in ring]


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


def build_ladder_mesh(
    name,
    bevel_offset,
    bevel_segments,
    rung_radius=RUNG_R,
    short_stile=False,
    twin_sole=False,
    drift_rungs=False,
    float_nuts=False,
):
    """Raked tapered rails, turned rungs, sleeve shoes with level soles.

    The sleeve is built in the rail frame so it follows the rake. The sole
    is a separate world-level plate the sleeve bites into. The rail ends
    inside the sleeve, above the sole.
    """
    bm = bmesh.new()
    metal_faces = set()
    try:
        rail_z0 = (BAND_Z0 + BAND_H + 0.012) if short_stile else RAIL_Z0
        rail_z1 = STILE_H - CAP_DROP
        stile_verts = []
        for sign in (-1.0, 1.0):
            stile_verts.extend(
                add_ruled_box(
                    bm,
                    sign * CENTER,
                    rail_z0,
                    rail_z1,
                    half_w(rail_z0),
                    half_w(rail_z1),
                    STILE_D * 0.5,
                    WOOD_IDX,
                )
            )

        z_lo = 0.22
        z_hi = STILE_H - 0.20
        for i in range(N_RUNGS):
            t = i / (N_RUNGS - 1)
            z = z_lo + t * (z_hi - z_lo) + (DRIFT_Z_OFFSETS[i] if drift_rungs else 0.0)
            add_turned_rung(
                bm,
                z,
                inner_x(z, -1.0),
                inner_x(z, 1.0),
                2.0 * half_w(z) + TENON_PROUD,
                rung_radius,
                rung_radius * BARREL_RATIO * RUNG_BARREL_SCALE[i],
                RUNG_SEGS,
                WOOD_IDX,
            )

        if bevel_offset > 0.0:
            edges = list(
                {
                    edge
                    for vertex in stile_verts
                    for edge in vertex.link_edges
                    if vertex.is_valid
                }
            )
            # set order follows memory addresses; sort so the bevel, and
            # the face order it produces, are the same on every run
            bm.edges.index_update()
            edges.sort(key=lambda e: e.index)
            if edges:
                bmesh.ops.bevel(
                    bm,
                    geom=edges,
                    offset=bevel_offset,
                    segments=bevel_segments,
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
                )

        before = set(bm.faces)
        metal_verts = []
        hd = STILE_D * 0.5
        for sign in (-1.0, 1.0):
            x = sign * CENTER
            shoe_z = BAND_Z0 + BAND_H * 0.5
            grip = 0.0015 + bevel_offset
            metal_verts.extend(
                add_rect_band(
                    bm,
                    shoe_z,
                    x,
                    half_w(shoe_z) - grip,
                    hd - grip,
                    BAND_T,
                    BAND_T,
                    BAND_H,
                    METAL_IDX,
                )
            )
            cap_h = CAP_RISE + 0.006
            cap_z = rail_z1 + (CAP_RISE - 0.006) * 0.5
            chw = half_w(rail_z1)
            metal_verts.extend(
                add_rect_band(
                    bm,
                    cap_z,
                    x,
                    chw - grip,
                    hd - grip,
                    BAND_T,
                    BAND_T,
                    cap_h,
                    METAL_IDX,
                )
            )
            # Plate overlaps the sleeve top so the two faces are not coplanar.
            plate_z = rail_z1 + CAP_RISE - 0.002 + PLATE_H * 0.5
            metal_verts.extend(
                add_box(
                    bm,
                    (x, 0.0, plate_z),
                    (
                        (chw + BAND_T) * 2.0 + 0.006,
                        (hd + BAND_T) * 2.0 + 0.006,
                        PLATE_H,
                    ),
                    METAL_IDX,
                )
            )
        metal_faces.update(set(bm.faces) - before)

        if bevel_offset > 0.0 and metal_verts:
            metal_edges = list(
                {
                    edge
                    for vertex in metal_verts
                    for edge in vertex.link_edges
                    if vertex.is_valid
                }
            )
            # set order follows memory addresses; sort so the bevel, and
            # the face order it produces, are the same on every run
            bm.edges.index_update()
            metal_edges.sort(key=lambda e: e.index)
            if metal_edges:
                bevelled = bmesh.ops.bevel(
                    bm,
                    geom=metal_edges,
                    offset=min(bevel_offset, 0.0016),
                    segments=bevel_segments,
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
                )
                metal_faces.update(bevelled.get("faces") or [])

        # Iron tie-rods under the bottom and top rungs, through both stiles,
        # each end clamped by a square nut seated on the stile's outer face.
        # Built after the bevels: rods and nuts carry their own facets.
        before = set(bm.faces)
        nut_gap = FLOAT_NUTS if float_nuts else 0.0
        for i in TIE_RUNGS:
            t = i / (N_RUNGS - 1)
            z = z_lo + t * (z_hi - z_lo) - TIE_DROP
            outer = CENTER + half_w(z)
            span = 2.0 * (outer + TIE_PROUD)
            add_cylinder(bm, (0.0, 0.0, z), TIE_R, span, TIE_SEGS, METAL_IDX,
                         euler=(0.0, math.radians(90.0), 0.0))
            for sign in (-1.0, 1.0):
                washer_in = outer - SEAT_SINK
                add_cylinder(bm, (sign * (washer_in + WASHER_T * 0.5), 0.0, z),
                             WASHER_R, WASHER_T, WASHER_SEGS, METAL_IDX,
                             euler=(0.0, math.radians(90.0), 0.0))
                inner_face = washer_in + WASHER_T - SEAT_SINK + nut_gap
                xc = sign * (inner_face + NUT_T * 0.5)
                # a four-segment cone lies on the rod axis as a diamond;
                # turning it 45 deg about that axis levels the flats
                nut = add_cone(bm, (0.0, 0.0, 0.0), NUT_HALF * math.sqrt(2.0),
                               NUT_HALF * math.sqrt(2.0), NUT_T, 4, METAL_IDX,
                               euler=(0.0, math.radians(90.0), 0.0))
                spin = Euler((math.radians(45.0), 0.0, 0.0)).to_matrix()
                for v in nut:
                    v.co = spin @ v.co + Vector((xc, 0.0, z))
        metal_faces.update(set(bm.faces) - before)

        rake = Euler((RAKE, 0.0, 0.0)).to_matrix()
        for v in bm.verts:
            v.co = rake @ v.co
        zs = [v.co.z for v in bm.verts]
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zmin = min(zs)
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy
            v.co.z -= zmin

        def world_of(local):
            q = rake @ Vector(local)
            q.x -= cx
            q.y -= cy
            q.z -= zmin
            return q

        before = set(bm.faces)
        sole_centers = []
        sole_verts = []
        for sign in (-1.0, 1.0):
            x = sign * CENTER
            shoe_z = BAND_Z0 + BAND_H * 0.5
            sole_w = (half_w(shoe_z) + BAND_T + SOLE_PAD) * 2.0
            sole_d = (hd + BAND_T + SOLE_PAD) * 2.0
            anchor = world_of((x, 0.0, 0.0))
            sole_centers.append((anchor.x, anchor.y, sole_w, sole_d))
            sole_verts.extend(
                add_box(
                    bm,
                    (anchor.x, anchor.y, SOLE_H * 0.5),
                    (sole_w, sole_d, SOLE_H),
                    METAL_IDX,
                )
            )
        if bevel_offset > 0.0 and sole_verts:
            sole_edges = list(
                {
                    edge
                    for vertex in sole_verts
                    for edge in vertex.link_edges
                    if vertex.is_valid
                }
            )
            # set order follows memory addresses; sort so the bevel, and
            # the face order it produces, are the same on every run
            bm.edges.index_update()
            sole_edges.sort(key=lambda e: e.index)
            if sole_edges:
                bevelled = bmesh.ops.bevel(
                    bm,
                    geom=sole_edges,
                    offset=min(bevel_offset, 0.0014),
                    segments=1,
                    profile=0.5,
                    affect="EDGES",
                    clamp_overlap=True,
                )
                metal_faces.update(bevelled.get("faces") or [])
        if twin_sole and sole_centers:
            sx, sy, sw, sd = sole_centers[0]
            add_box(
                bm,
                (sx + 0.0012, sy + 0.0012, SOLE_H * 0.5),
                (sw, sd, SOLE_H),
                METAL_IDX,
            )
        metal_faces.update(set(bm.faces) - before)

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        for face in bm.faces:
            face.smooth = True
        for edge in bm.edges:
            edge.smooth = True
            if edge.is_manifold and len(edge.link_faces) == 2:
                if edge.calc_face_angle() > math.radians(40.0):
                    edge.smooth = False
        for f in metal_faces:
            if f.is_valid:
                f.material_index = METAL_IDX
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
        tex.inputs["Detail"].default_value = 4.0
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = color
        mix.inputs["B"].default_value = wear
        fac = mix.inputs.get("Factor") or mix.inputs.get("Fac")
        nt.links.new(tex.outputs["Fac"], fac)
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
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
    zero_area = sum(1 for area in areas if area <= AREA_EPS)
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


def shell_records(me):
    """One record per edge-connected shell, in world space and un-raked."""
    neighbors = [[] for _ in range(len(me.vertices))]
    for edge in me.edges:
        a, b = int(edge.vertices[0]), int(edge.vertices[1])
        neighbors[a].append(b)
        neighbors[b].append(a)
    unrake = Euler((-RAKE, 0.0, 0.0)).to_matrix()
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
    records = []
    for group in groups:
        member = set(group)
        world = [me.vertices[i].co.copy() for i in group]
        local = [unrake @ p for p in world]
        mats = {}
        for poly in me.polygons:
            if all(v in member for v in poly.vertices):
                mats[poly.material_index] = mats.get(poly.material_index, 0) + 1
        mat = max(mats, key=mats.get) if mats else -1
        records.append({"world": world, "local": local, "mat": mat})
    return records


def _span_at(pts, z):
    """X extent of a ruled stile at height z, from the end rings.

    Bevel does not add vertices along the rail, so the section is the
    linear blend of the two end widths.
    """
    z0 = min(p.z for p in pts)
    z1 = max(p.z for p in pts)
    if z1 - z0 < 1e-6:
        return None
    bot = [p for p in pts if p.z <= z0 + 0.015]
    top = [p for p in pts if p.z >= z1 - 0.015]
    if len(bot) < 2 or len(top) < 2:
        return None
    t = min(1.0, max(0.0, (z - z0) / (z1 - z0)))
    x0 = (1.0 - t) * min(p.x for p in bot) + t * min(p.x for p in top)
    x1 = (1.0 - t) * max(p.x for p in bot) + t * max(p.x for p in top)
    return x0, x1


def joint_audit(me):
    """Rung tenon fit and shoe seat, recomputed from vertex positions."""
    recs = shell_records(me)
    stiles = []
    rungs = []
    bands = []
    soles = []
    for rec in recs:
        loc = rec["local"]
        zs = [p.z for p in loc]
        xs = [p.x for p in loc]
        dz = max(zs) - min(zs)
        dx = max(xs) - min(xs)
        wz = [p.z for p in rec["world"]]
        wz0 = min(wz)
        wdz = max(wz) - wz0
        if rec["mat"] == WOOD_IDX and dz > 0.8:
            stiles.append(rec)
        elif rec["mat"] == WOOD_IDX and dx > 0.2:
            rungs.append(rec)
        elif rec["mat"] == METAL_IDX and wz0 < 0.004 and wdz < SOLE_H + 0.01:
            soles.append(rec)
        elif rec["mat"] == METAL_IDX and min(zs) < 0.08 and dz < 0.12:
            bands.append(rec)
    empty = {
        "parts": len(recs),
        "stiles": len(stiles),
        "rungs": len(rungs),
        "bands": len(bands),
        "soles": len(soles),
        "clearance": -1.0,
        "engage": -1.0,
        "proud": -1.0,
        "shoe_bite": -1.0,
        "shoe_cover": -1.0,
        "rail_zmin": -1.0,
        "sole_zmin": 1.0,
    }
    if len(stiles) != 2 or len(rungs) != N_RUNGS or len(bands) != 2 or len(soles) != 2:
        return empty
    clearance = 1e9
    engage = 1e9
    proud = 1e9
    for rung in rungs:
        rz = sum(p.z for p in rung["local"]) / len(rung["local"])
        rx0 = min(p.x for p in rung["local"])
        rx1 = max(p.x for p in rung["local"])
        for stile in stiles:
            span = _span_at(stile["local"], rz)
            if span is None:
                return empty
            x0, x1 = span
            inside = [p for p in rung["local"] if x0 + 0.003 < p.x < x1 - 0.003]
            if len(inside) < 3:
                return empty
            stile_dy = max(p.y for p in stile["local"]) - min(p.y for p in stile["local"])
            rung_dy = max(p.y for p in inside) - min(p.y for p in inside)
            clearance = min(clearance, (stile_dy - rung_dy) * 0.5)
            if x1 < 0.0:
                engage = min(engage, x1 - rx0)
                proud = min(proud, x0 - rx0)
            else:
                engage = min(engage, rx1 - x0)
                proud = min(proud, rx1 - x1)
    shoe_bite = 1e9
    shoe_cover = 1e9
    for stile in stiles:
        sx = sum(p.x for p in stile["local"]) / len(stile["local"])
        band = min(bands, key=lambda b: abs(sum(p.x for p in b["local"]) / len(b["local"]) - sx))
        stile_z0 = min(p.z for p in stile["local"])
        band_z0 = min(p.z for p in band["local"])
        band_z1 = max(p.z for p in band["local"])
        shoe_bite = min(shoe_bite, stile_z0 - band_z0)
        shoe_cover = min(shoe_cover, band_z1 - stile_z0)
    rail_zmin = min(min(p.z for p in s["world"]) for s in stiles)
    sole_zmin = max(min(p.z for p in s["world"]) for s in soles)
    empty.update({
        "clearance": clearance,
        "engage": engage,
        "proud": proud,
        "shoe_bite": shoe_bite,
        "shoe_cover": shoe_cover,
        "rail_zmin": rail_zmin,
        "sole_zmin": sole_zmin,
    })
    return empty


def tie_audit(me):
    """Tie-rod hardware, recomputed from vertex positions (un-raked frame).

    Rods are metal shells long in X and thin in Z; washers are thin metal
    discs and nuts thicker metal blocks, both above the shoes. Every washer
    and nut must sit on its rod's axis. Each washer beds a hair into its
    stile's outer face and each nut into its washer's outboard face: seated,
    not floating off, not buried. Each rod's thread end must stand proud of
    both nuts, so the nuts are on the rod at all.
    """
    recs = shell_records(me)
    stiles, rods, washers, nuts = [], [], [], []
    for rec in recs:
        loc = rec["local"]
        dx = max(p.x for p in loc) - min(p.x for p in loc)
        dy = max(p.y for p in loc) - min(p.y for p in loc)
        dz = max(p.z for p in loc) - min(p.z for p in loc)
        if rec["mat"] == WOOD_IDX and dz > 0.8:
            stiles.append(loc)
        elif rec["mat"] == METAL_IDX and dx > 0.3 and dz < 0.02:
            rods.append(loc)
        elif rec["mat"] == METAL_IDX and min(p.z for p in loc) > 0.1 and dx < 0.02:
            if dx < 0.0045 and 0.02 < dy < 0.04 and 0.02 < dz < 0.04:
                washers.append(loc)
            elif dx > 0.005 and dy < 0.03 and dz < 0.03:
                nuts.append(loc)
    out = {"rods": len(rods), "washers": len(washers), "nuts": len(nuts),
           "bite_min": -1.0, "bite_max": 99.0, "axis": 99.0, "through": -1.0}
    ends = 2 * len(TIE_RUNGS)
    if (len(stiles) != 2 or len(rods) != len(TIE_RUNGS)
            or len(washers) != ends or len(nuts) != ends):
        return out
    stiles.sort(key=lambda s: sum(p.x for p in s))

    def mean(pts, k):
        return sum(p[k] for p in pts) / len(pts)

    bite_min, bite_max, axis, through = 1e9, -1e9, 0.0, 1e9
    for washer in washers:
        wx, wy, wz = mean(washer, 0), mean(washer, 1), mean(washer, 2)
        rod = min(rods, key=lambda r: abs(mean(r, 2) - wz))
        axis = max(axis, abs(wy - mean(rod, 1)), abs(wz - mean(rod, 2)))
        # the washer's inboard face bedded into the stile's outer face
        if wx < 0.0:
            bite = max(p.x for p in washer) - _span_at(stiles[0], wz)[0]
        else:
            bite = _span_at(stiles[1], wz)[1] - min(p.x for p in washer)
        bite_min, bite_max = min(bite_min, bite), max(bite_max, bite)
        # the nut on this end bears on the washer's outboard face
        side = [n for n in nuts if (mean(n, 0) < 0.0) == (wx < 0.0)]
        nut = min(side, key=lambda n: abs(mean(n, 2) - wz))
        axis = max(axis, abs(mean(nut, 1) - mean(rod, 1)),
                   abs(mean(nut, 2) - mean(rod, 2)))
        if wx < 0.0:
            bite = max(p.x for p in nut) - min(p.x for p in washer)
            through = min(through, min(p.x for p in nut) - min(p.x for p in rod))
        else:
            bite = max(p.x for p in washer) - min(p.x for p in nut)
            through = min(through, max(p.x for p in rod) - max(p.x for p in nut))
        bite_min, bite_max = min(bite_min, bite), max(bite_max, bite)
    out.update({"bite_min": bite_min, "bite_max": bite_max, "axis": axis,
                "through": through})
    return out


def _vertex_shells(me):
    """Connected vertex groups, as lists of vertex indices."""
    nbr = [[] for _ in me.vertices]
    for e in me.edges:
        a, b = e.vertices
        nbr[a].append(b)
        nbr[b].append(a)
    seen = [False] * len(me.vertices)
    groups = []
    for st in range(len(me.vertices)):
        if seen[st]:
            continue
        seen[st] = True
        stack, g = [st], []
        while stack:
            c = stack.pop()
            g.append(c)
            for n in nbr[c]:
                if not seen[n]:
                    seen[n] = True
                    stack.append(n)
        groups.append(g)
    return groups


def _wood_rung_shells(me):
    """Vertex positions of every rung: the WOOD shells wide in X, short in Z.

    The material test matters: the iron tie-rods are just as wide and
    shorter still, and must not be read as rungs.
    """
    vert_mat = {}
    for poly in me.polygons:
        for v in poly.vertices:
            vert_mat.setdefault(v, poly.material_index)
    rungs = []
    for g in _vertex_shells(me):
        if vert_mat.get(g[0]) != WOOD_IDX:
            continue
        pts = [me.vertices[i].co for i in g]
        dx = max(p.x for p in pts) - min(p.x for p in pts)
        dz = max(p.z for p in pts) - min(p.z for p in pts)
        if dx > 0.25 and dz < 0.08:
            rungs.append(pts)
    return rungs


def rung_pitch(me):
    """Worst deviation of a rung-to-rung gap from the mean gap, metres.

    Rungs are the wooden shells wide across X and short in Z; each one's
    height is the mean Z of its vertices.
    """
    zs = []
    for pts in _wood_rung_shells(me):
        zs.append(sum(p.z for p in pts) / len(pts))
    zs.sort()
    if len(zs) < 3:
        return len(zs), 99.0
    gaps = [b - a for a, b in zip(zs, zs[1:])]
    mean = sum(gaps) / len(gaps)
    return len(zs), max(abs(g - mean) for g in gaps)


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

    Every rail and rung is its own shell, so each gets one tone and grain
    running along its own long axis (up the rails, across the rungs).
    """
    tone = [0.5] * len(me.polygons)
    grain = [(0.0, 0.0, 1.0)] * len(me.polygons)
    species = [0.0] * len(me.polygons)
    owner = {}
    rng = random.Random(TONE_SEED)
    for g in _vertex_shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        d = _long_axis(pts) if len(pts) > 2 else Vector((0.0, 0.0, 1.0))
        t = 0.5 + rng.uniform(-PLANK_TONE_JITTER, PLANK_TONE_JITTER)
        # rungs run across X: turned from pale hickory, the rails from oak
        s = 1.0 if abs(d.x) > 0.8 else 0.0
        for i in g:
            owner[i] = (t, tuple(d), s)
    for poly in me.polygons:
        t, d, s = owner[poly.vertices[0]]
        tone[poly.index] = t
        grain[poly.index] = d
        species[poly.index] = s
    a = me.attributes.new("PlankTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)
    b = me.attributes.new("GrainDir", "FLOAT_VECTOR", "FACE")
    b.data.foreach_set("vector", [c for v in grain for c in v])
    c = me.attributes.new("Species", "FLOAT", "FACE")
    c.data.foreach_set("value", species)


def _sock(sockets, identifier):
    """A Mix-node socket by identifier; its A/B/Result names repeat per type."""
    return next(sk for sk in sockets if sk.identifier == identifier)


def wood_material(name):
    """Grain along each rail and rung (``GrainDir``), tone per piece (``PlankTone``)."""
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
    squash.inputs[1].default_value = 0.985
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
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[0].color = (0.030, 0.015, 0.007, 1.0)
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = (0.19, 0.095, 0.040, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    # rungs are pale hickory against the darker oak rails (``Species``)
    hickory = nt.nodes.new("ShaderNodeValToRGB")
    hickory.color_ramp.elements[0].position = 0.38
    hickory.color_ramp.elements[0].color = (0.16, 0.10, 0.052, 1.0)
    hickory.color_ramp.elements[1].position = 0.62
    hickory.color_ramp.elements[1].color = (0.58, 0.42, 0.25, 1.0)
    nt.links.new(noise.outputs["Fac"], hickory.inputs["Fac"])
    species = nt.nodes.new("ShaderNodeAttribute")
    species.attribute_name = "Species"
    timber = nt.nodes.new("ShaderNodeMix")
    timber.data_type = "RGBA"
    nt.links.new(species.outputs["Fac"], _sock(timber.inputs, "Factor_Float"))
    nt.links.new(ramp.outputs["Color"], _sock(timber.inputs, "A_Color"))
    nt.links.new(hickory.outputs["Color"], _sock(timber.inputs, "B_Color"))
    # end grain (the face looks down the grain: the through-tenon ends on
    # the rail sides, the rail tops) drinks finish and reads darker
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    to_obj = nt.nodes.new("ShaderNodeVectorTransform")
    to_obj.vector_type = "NORMAL"
    to_obj.convert_from = "WORLD"
    to_obj.convert_to = "OBJECT"
    nt.links.new(geo.outputs["Normal"], to_obj.inputs["Vector"])
    end_dot = nt.nodes.new("ShaderNodeVectorMath")
    end_dot.operation = "DOT_PRODUCT"
    nt.links.new(to_obj.outputs["Vector"], end_dot.inputs[0])
    nt.links.new(gdir.outputs["Vector"], end_dot.inputs[1])
    end_abs = nt.nodes.new("ShaderNodeMath")
    end_abs.operation = "ABSOLUTE"
    nt.links.new(end_dot.outputs["Value"], end_abs.inputs[0])
    end_shade = nt.nodes.new("ShaderNodeMapRange")
    end_shade.inputs["From Min"].default_value = 0.80
    end_shade.inputs["From Max"].default_value = 0.95
    end_shade.inputs["To Min"].default_value = 1.0
    end_shade.inputs["To Max"].default_value = 0.42
    nt.links.new(end_abs.outputs["Value"], end_shade.inputs["Value"])
    end_mix = nt.nodes.new("ShaderNodeMix")
    end_mix.data_type = "RGBA"
    end_mix.blend_type = "MULTIPLY"
    _sock(end_mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(_sock(timber.outputs, "Result_Color"), _sock(end_mix.inputs, "A_Color"))
    nt.links.new(end_shade.outputs["Result"], _sock(end_mix.inputs, "B_Color"))
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 1.1
    gain.inputs[2].default_value = 0.45
    nt.links.new(tone.outputs["Fac"], gain.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(_sock(end_mix.outputs, "Result_Color"), _sock(mix.inputs, "A_Color"))
    nt.links.new(gain.outputs["Value"], _sock(mix.inputs, "B_Color"))
    # handling grime: short-range AO darkens where rungs enter the stiles
    # and under the iron sleeves, so the joints read at thumbnail scale
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.035
    grime = nt.nodes.new("ShaderNodeMapRange")
    grime.inputs["To Min"].default_value = 0.45
    grime.inputs["To Max"].default_value = 1.0
    nt.links.new(ao.outputs["AO"], grime.inputs["Value"])
    dirt = nt.nodes.new("ShaderNodeMix")
    dirt.data_type = "RGBA"
    dirt.blend_type = "MULTIPLY"
    _sock(dirt.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(_sock(mix.outputs, "Result_Color"), _sock(dirt.inputs, "A_Color"))
    nt.links.new(grime.outputs["Result"], _sock(dirt.inputs, "B_Color"))
    nt.links.new(_sock(dirt.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = 0.72
    rough.inputs["To Max"].default_value = 0.52
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def ladder_materials():
    """(wood, iron): shared by the check, the render and inspection."""
    wood = wood_material("LadderWood")
    metal = principled(
        "LadderMetal", (0.085, 0.082, 0.078, 1.0), 0.80, 0.42,
        noise_scale=18.0, wear=(0.11, 0.050, 0.024, 1.0),
    )
    return wood, metal


def add_stray_vert(me):
    # Falsification only: one unconnected vertex, placed inside the existing
    # bounds so the bbox budget still passes and the hygiene budget is the
    # gate that fires.
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, STILE_H / 3.0))
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
    img = bpy.data.images.new("LadderNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = WOOD_IDX
    return img, tex


def bake_normal(high, low):
    # Duplicated from snippets/bake_normal_high_to_low.py (not a package).
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
    # Duplicated from snippets/export_preset_unity.py (not a package).
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
    fat_rungs=False,
    short_stile=False,
    twin_sole=False,
    drift_rungs=False,
    float_nuts=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # Falsification: a tenon as deep as the stile, which breaks the front
    # and back chamfers. The barrel stays outside the stile.
    rung_radius = STILE_D / 2.0 if fat_rungs else RUNG_R
    low = build_ladder_mesh(
        "LadderLow",
        bevel_offset=0.0022,
        bevel_segments=2,
        rung_radius=rung_radius,
        short_stile=short_stile,
        twin_sole=twin_sole,
        drift_rungs=drift_rungs,
        float_nuts=float_nuts,
    )
    high = build_ladder_mesh(
        "LadderHigh",
        bevel_offset=0.0022,
        bevel_segments=4,
        rung_radius=rung_radius,
        short_stile=short_stile,
        twin_sole=twin_sole,
        drift_rungs=drift_rungs,
        float_nuts=float_nuts,
    )
    if lift_z:
        low.location.z += LIFT_Z
    if stray_vert:
        add_stray_vert(low.data)
    # world_bbox reads matrix_world, which is evaluated data. Without this the
    # cached matrix hides a moved object and the grounded budget cannot fail.
    bpy.context.view_layer.update()
    wood, metal = ladder_materials()
    paint_planks(low.data)
    paint_planks(high.data)
    assign_slots(low, wood, metal)
    assign_slots(high, wood, metal)

    if low.data is None or len(low.data.polygons) < 6:
        return fail("ladder mesh did not build", 3), None, None, None, None, None

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
        return fail("ladder has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "LadderLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "LadderLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_ladder_mesh("LadderColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "LadderCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_wooden_ladder_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender points TMPDIR at the working directory, so the export must not
    # outlive the measurement.
    if os.path.exists(export_path):
        os.remove(export_path)

    print(
        f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}"
    )
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
    zf = zfight_pairs(low.data)
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf} "
        f"euler={hyg['euler']}"
    )
    joint = joint_audit(low.data)
    n_rungs, pitch_dev = rung_pitch(low.data)
    print(f"measured rung_pitch rungs={n_rungs} worst_dev={pitch_dev:.5f}")
    tie = tie_audit(low.data)
    print(
        f"measured tie_rods rods={tie['rods']} washers={tie['washers']} "
        f"nuts={tie['nuts']} seat_bite={tie['bite_min']:.5f}..{tie['bite_max']:.5f} "
        f"axis_off={tie['axis']:.5f} thread_proud={tie['through']:.5f}"
    )
    print(
        f"measured joints parts={joint['parts']} stiles={joint['stiles']} "
        f"rungs={joint['rungs']} bands={joint['bands']} soles={joint['soles']} "
        f"clearance={joint['clearance']:.5f} engage={joint['engage']:.5f} "
        f"tenon_proud={joint['proud']:.5f} shoe_bite={joint['shoe_bite']:.5f} "
        f"shoe_cover={joint['shoe_cover']:.5f} rail_zmin={joint['rail_zmin']:.5f} "
        f"sole_zmin={joint['sole_zmin']:.5f}"
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
            f"wood faces {idx_counts.get(WOOD_IDX, 0)} < {WOOD_FACES_MIN}",
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
        or zf
    ):
        return fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf} "
            "(--stray-vert / --twin-sole are the designed fails)",
            15,
        ), None, None, None, None, None
    if abs(bb[2]) > ZMIN_EPS:
        return fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ), None, None, None, None, None
    if abs(joint["sole_zmin"]) > ZMIN_EPS or joint["rail_zmin"] < RAIL_ZMIN_MIN:
        return fail(
            f"sole_zmin {joint['sole_zmin']:.5f} rail_zmin {joint['rail_zmin']:.5f}",
            16,
        ), None, None, None, None, None
    if joint["parts"] != PART_COUNT:
        return fail(
            f"part count {joint['parts']} != {PART_COUNT} "
            f"(stiles={joint['stiles']} rungs={joint['rungs']})",
            17,
        ), None, None, None, None, None
    if joint["clearance"] < RUNG_DEPTH_CLEARANCE:
        return fail(
            f"rung-to-stile depth clearance {joint['clearance']:.5f} < "
            f"{RUNG_DEPTH_CLEARANCE} (--fat-rungs is the designed fail)",
            17,
        ), None, None, None, None, None
    if joint["engage"] < TENON_ENGAGE_MIN:
        return fail(
            f"tenon engagement {joint['engage']:.5f} < {TENON_ENGAGE_MIN}",
            17,
        ), None, None, None, None, None
    if not (TENON_PROUD_MIN <= joint["proud"] <= TENON_PROUD_MAX):
        return fail(
            f"through-tenon proud {joint['proud']:.5f} not in "
            f"[{TENON_PROUD_MIN}, {TENON_PROUD_MAX}]",
            17,
        ), None, None, None, None, None
    if joint["shoe_bite"] < SHOE_BITE_MIN or joint["shoe_cover"] < SHOE_COVER_MIN:
        return fail(
            f"shoe bite {joint['shoe_bite']:.5f} cover {joint['shoe_cover']:.5f} "
            "(--short-stile is the designed fail)",
            18,
        ), None, None, None, None, None
    if n_rungs != N_RUNGS or pitch_dev > RUNG_PITCH_TOL:
        return fail(
            f"rung pitch: {n_rungs} rungs, worst gap {pitch_dev:.5f} off the mean "
            f"> {RUNG_PITCH_TOL} (--drift-rungs is the designed fail)",
            19,
        ), None, None, None, None, None
    if (
        tie["rods"] != len(TIE_RUNGS)
        or tie["washers"] != 2 * len(TIE_RUNGS)
        or tie["nuts"] != 2 * len(TIE_RUNGS)
        or tie["bite_min"] < SEAT_BITE_MIN
        or tie["bite_max"] > SEAT_BITE_MAX
        or tie["axis"] > NUT_AXIS_TOL
        or tie["through"] < TIE_THROUGH_MIN
    ):
        return fail(
            f"tie-rod seat: rods {tie['rods']} washers {tie['washers']} nuts "
            f"{tie['nuts']} seat bite {tie['bite_min']:.5f}..{tie['bite_max']:.5f} "
            f"not in [{SEAT_BITE_MIN}, {SEAT_BITE_MAX}], axis off {tie['axis']:.5f}, "
            f"thread proud {tie['through']:.5f} < {TIE_THROUGH_MIN}? "
            "(--float-nuts is the designed fail)",
            20,
        ), None, None, None, None, None
    return 0, low, high, wood, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def barn_wall_material():
    """Render-only lean surface: staggered weathered boards, dark seams."""
    mat = bpy.data.materials.new("BarnBoards")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    # Brick rows run along the texture's Y; turn the wall's Z onto it.
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (math.radians(90.0), 0.0, 0.0)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    boards = nt.nodes.new("ShaderNodeTexBrick")
    boards.offset = 0.37
    boards.inputs["Scale"].default_value = 1.0
    boards.inputs["Brick Width"].default_value = 1.35
    boards.inputs["Row Height"].default_value = 0.17
    boards.inputs["Mortar Size"].default_value = 0.006
    boards.inputs["Mortar Smooth"].default_value = 0.3
    boards.inputs["Bias"].default_value = 0.0
    boards.inputs["Color1"].default_value = (0.070, 0.052, 0.038, 1.0)
    boards.inputs["Color2"].default_value = (0.105, 0.080, 0.058, 1.0)
    boards.inputs["Mortar"].default_value = (0.008, 0.007, 0.006, 1.0)
    nt.links.new(mapping.outputs["Vector"], boards.inputs["Vector"])
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 6.0
    grain.inputs["Detail"].default_value = 8.0
    stretch = nt.nodes.new("ShaderNodeMapping")
    stretch.inputs["Scale"].default_value = (0.12, 1.0, 6.0)
    nt.links.new(coord.outputs["Object"], stretch.inputs["Vector"])
    nt.links.new(stretch.outputs["Vector"], grain.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 0.55
    nt.links.new(boards.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(grain.outputs["Color"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.004
    nt.links.new(boards.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def rope_coil(low, turns=3, loop_r=0.135, rope_r=0.012):
    """A hand-coiled rope hung over the second-highest rung (ladder frame).

    Rungs are read off the mesh the way ``rung_pitch`` reads them: the
    wooden shells wide across X and short in Z. The coil's loops hang in
    the plane across the rung, their tops draped over it, and are laid
    from a three-lobed section turned one step per ring, as the showcase
    rope rule asks.
    """
    me = low.data
    rungs = _wood_rung_shells(me)
    rungs.sort(key=lambda pts: sum(p.z for p in pts))
    rung = rungs[-2]
    rz = sum(p.z for p in rung) / len(rung)
    ry = sum(p.y for p in rung) / len(rung)
    rr = (max(p.z for p in rung) - min(p.z for p in rung)) / 2.0
    # The wall stands on the side the rails rake toward; the coil hangs
    # forward of the rung, away from it, so it never meets the boards.
    top_band = [v.co.y for v in me.vertices if v.co.z > max(p.z for p in rung) + 0.3]
    foot_band = [v.co.y for v in me.vertices if v.co.z < 0.08]
    wall_side = 1.0 if sum(top_band) / len(top_band) > sum(foot_band) / len(foot_band) else -1.0
    ztop = rz + rr + rope_r
    x0 = 0.035

    steps, sides = 36 * turns, 9
    pitch = 2.3 * rope_r

    def centre(i):
        # a hanging loop is a teardrop: pinched over the rung, full below;
        # it reaches far forward of the rung and barely behind it
        t = i / 36.0 * 2.0 * math.pi
        fan = 1.0 - 0.06 * (i / steps)                 # turns read as separate
        s = math.sin(t)
        reach = (loop_r * 0.9 if s > 0 else loop_r * 0.28) * fan
        y = ry - wall_side * reach * s
        z = ztop - loop_r * 1.35 * fan * (1.0 - math.cos(t))
        return Vector((x0 + pitch * i / 36.0, y, z))

    bm = bmesh.new()
    try:
        rings = []
        for i in range(steps + 1):
            c = centre(i)
            tang = (centre(i + 1) - centre(i - 1)).normalized()
            n = tang.cross(Vector((1.0, 0.0, 0.0))).normalized()
            b = tang.cross(n)
            ring = []
            for k in range(sides):
                a = 2 * math.pi * k / sides + i * (2 * math.pi / sides)
                lobe = 1.0 + 0.16 * math.cos(3 * (2 * math.pi * k / sides))
                ring.append(bm.verts.new(c + rope_r * lobe * (n * math.cos(a) + b * math.sin(a))))
            rings.append(ring)
        for r0, r1 in zip(rings, rings[1:]):
            for k in range(sides):
                f = bm.faces.new((r0[k], r0[(k + 1) % sides], r1[(k + 1) % sides], r1[k]))
                f.smooth = True
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
        cme = bpy.data.meshes.new("RopeCoil")
        bm.to_mesh(cme)
    finally:
        bm.free()
    rmat = bpy.data.materials.new("Hemp")
    rmat.use_nodes = True
    rnt = rmat.node_tree
    rb = rnt.nodes["Principled BSDF"]
    rnoise = rnt.nodes.new("ShaderNodeTexNoise")
    rnoise.inputs["Scale"].default_value = 90.0
    rnoise.inputs["Detail"].default_value = 6.0
    rramp = rnt.nodes.new("ShaderNodeValToRGB")
    rramp.color_ramp.elements[0].color = (0.16, 0.115, 0.065, 1.0)
    rramp.color_ramp.elements[1].color = (0.40, 0.31, 0.18, 1.0)
    rnt.links.new(rnoise.outputs["Fac"], rramp.inputs["Fac"])
    rnt.links.new(rramp.outputs["Color"], rb.inputs["Base Color"])
    rb.inputs["Roughness"].default_value = 0.9
    cme.materials.append(rmat)
    return bpy.data.objects.new("RopeCoil", cme)


def render_still(low, wood, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(wood, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    # A leaning ladder needs something to lean on. Render-only: a wall
    # section on the side the rails rake toward, its face through the
    # rail tops, in the ladder's own frame and turned with it. The ladder
    # is turned so that side faces away from the camera.
    me = low.data
    ztop = max(v.co.z for v in me.vertices)
    top = [v.co.y for v in me.vertices if v.co.z > ztop - 0.08]
    foot = [v.co.y for v in me.vertices if v.co.z < 0.08]
    lean = 1.0 if sum(top) / len(top) > sum(foot) / len(foot) else -1.0
    top_y = max(top) if lean > 0 else min(top)
    low.rotation_euler.z = math.radians(-28.0 if lean > 0 else 152.0)
    panel_me = bpy.data.meshes.new("LeanWall")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 3.8
            v.co.y = top_y + lean * (v.co.y + 0.5) * 0.10
            v.co.z = (v.co.z + 0.5) * 1.95
        bm.to_mesh(panel_me)
    finally:
        bm.free()
    panel_me.materials.append(barn_wall_material())
    panel = bpy.data.objects.new("LeanWall", panel_me)
    panel.rotation_euler.z = low.rotation_euler.z
    scene.collection.objects.link(panel)

    # A laid-rope coil hung over the second-highest rung: the ladder in use,
    # not in a catalogue. Render-only, parented to the ladder so it turns
    # with it; not part of the asset, its budgets or its export.
    coil = rope_coil(low)
    coil.parent = low
    scene.collection.objects.link(coil)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        # Oversized so no edge of the set can enter frame; the committed hero
        # used to show the wall's left edge as a bright band in the corner.
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
    cam.location = (2.55, -3.55, 1.38)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.74)
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
        scene, cam, hero=[low], elements=[low, coil], stage=[floor, wall, panel],
    )
    if fcode:
        return fcode
    # asset-quality floors (examples/gallery_asset_quality.py) return 11,
    # which this piece's numbering already spends; remap at the call site
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall, panel]):
        return 21
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
        "--fat-rungs",
        action="store_true",
        help="falsification: tenons as deep as the stile, failing joint fit",
    )
    p.add_argument(
        "--short-stile",
        action="store_true",
        help="falsification: rails start above the shoe sleeve",
    )
    p.add_argument(
        "--twin-sole",
        action="store_true",
        help="falsification: duplicate a sole so a coplanar pair z-fights",
    )
    p.add_argument(
        "--drift-rungs",
        action="store_true",
        help="falsification: the old jittered rung heights",
    )
    p.add_argument(
        "--float-nuts",
        action="store_true",
        help="falsification: back the tie-rod nuts off the stile faces",
    )
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        fat_rungs=args.fat_rungs,
        short_stile=args.short_stile,
        twin_sole=args.twin_sole,
        drift_rungs=args.drift_rungs,
        float_nuts=args.float_nuts,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("wooden-ladder OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
