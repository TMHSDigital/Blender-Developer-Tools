"""Game-ready wooden wheelbarrow — a showcase piece, not an example.

Asserts budget conformance of a procedural wheelbarrow (two shafts, each
one timber from grip to axle; a flared hopper tray; a flat-tread spoked
wheel; rear legs) after composing
shipped pipeline pieces: bmesh construction, UVs, two materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. ``--skip-decimate`` skips the LOD
DECIMATE stage so the LOD-ratio budget fails. ``--stray-vert`` adds a
loose vertex so the mesh-hygiene budget fails. ``--lift-z`` raises the
mesh so the grounded-zmin budget fails. ``--short-legs`` lifts only the
shoes so the named-support budget fails while the wheel still grounds
the AABB. ``--fat-spokes`` thickens the spokes to the hub diameter so
joint-fit fails. ``--pipe-rim`` swaps the flat felloe/tyre for a torus
so the tread-aspect seat budget fails. ``--float-walls`` lifts the
tray walls off the floor so the wall-floor seat budget fails.
``--wide-seams`` opens the seams between wall boards to 8 mm so the
wall-board budget fails. ``--split-shafts`` builds each shaft as three
boxes so the shaft-run budget fails. ``--box-tray`` stands the tray walls
vertical on the same top outline so the flare budget fails.

Construction is closed-form; the only RNG is the seeded per-board wood
tone. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python wheelbarrow.py --
    blender --background --python wheelbarrow.py -- --skip-decimate
    blender --background --python wheelbarrow.py -- --output barrow.png
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

# Wheel: flat-tread wooden felloe + iron tyre. Torus rims read as bicycle
# tyres; the cart pass already killed that class.
RIM_MAJOR = 0.170
RIM_RADIAL = 0.014
RIM_W = 0.042
TYRE_T = 0.007
TYRE_BITE = 0.002
TYRE_W = 0.046
HUB_R = 0.032
HUB_W = 0.044
N_SPOKES = 8
SPOKE_T = 0.014
WHEEL_X = 0.58
WHEEL_Z = RIM_MAJOR + RIM_RADIAL + TYRE_T
RIM_MINOR_PIPE = 0.020

# Chassis shafts are the handles. Each is ONE timber swept from the grip,
# under the tray, to the axle: it runs level under the tray and narrows
# gently in plan all the way (grips HANDLE_Y apart, SHAFT_Y at the tray
# rear, SHAFT_Y_FRONT at its front, FORK_Y at the hub). Built as three
# boxes, the handle stopped at the tray's corner, the level run hid under
# the side walls, and the fork started at the front corner: the tray
# carried everything and the barrow read as a crate on legs.
HANDLE_Y = 0.27
SHAFT_Y = 0.19
SHAFT_Y_FRONT = 0.15
SHAFT_W = 0.036
SHAFT_H = 0.044
SHAFT_Z = 0.280
HANDLE_X = -0.78
HANDLE_Z = 0.56
TRAY_X0 = -0.32
TRAY_X1 = 0.40
TRAY_L = TRAY_X1 - TRAY_X0
# The tray is a hopper, not a box: a floor of inner half-width TRAY_YB on
# the shafts, sides flared out by FLARE, the front raked over the wheel by
# RAKE for tipping, the low rear leaning back by REAR_LEAN.
TRAY_YB = 0.21
TRAY_W = 2.0 * TRAY_YB
FLARE = math.radians(15.0)
RAKE = math.radians(30.0)
REAR_LEAN = math.radians(12.0)
FLARE_MIN = math.radians(10.0)
RAKE_MIN = math.radians(20.0)
FLOOR_T = 0.022
N_FLOOR = 5
# Negative: slats overlap so the wood bevel cannot open daylight
# through the tray floor.
SLAT_GAP = -0.003
WALL_H = 0.22
WALL_T = 0.022
# A raked wall's outer bottom edge sits WALL_T*sin(RAKE) below its inner
# one, so the seat is kept under FLOOR_T minus that or the edge pokes out
# of the floor's underside.
WALL_SEAT = 0.008
# Side and front walls are WALL_BOARDS boards stacked with a WALL_SEAM
# between them, held by the iron straps; the low rear wall is one board.
WALL_BOARDS = 2
WALL_SEAM = 0.002
WALL_SEAM_MIN = 0.001
WALL_SEAM_MAX = 0.004
WIDE_SEAM = 0.008
# Per-board wood tone jitter and grain frequency, as in shipping-crate.
PLANK_TONE_JITTER = 0.28
TONE_SEED = 29
WOOD_GRAIN_SCALE = 30.0
FRONT_H = 0.26
REAR_H = 0.10
FORK_Y = HUB_W / 2.0 + 0.016
LEG_X = -0.06
LEG_SPLAY = 0.08          # each leg's foot sits this far outboard of its shaft
LEG_BRACE_Z = 0.12
BEARER_BACK = 0.04        # bearer under the tray, this far behind its front
STRAP_T = 0.008
STRAP_TOP_CLEAR = 0.010   # straps stop this far below the wall top
SHOE_H = 0.024
SHOE_XY = (0.058, 0.050)

BBOX_TOL = 0.015
OUTER_SIZE = (1.563, 0.594, 0.577)
TRAY_SIZE = (0.939, 0.578, 0.225)
TRAY_SIZE_TOL = (0.02, 0.02, 0.02)
BASE_TRIS_MIN = 2300
BASE_TRIS_MAX = 2800
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 220
BAKE_RES = 256
CAGE_EXTRUSION = 0.08
METAL_FACES_MIN = 180
WOOD_FACES_MIN = 700
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
ZFIGHT_EPS = 1e-4
ZFIGHT_COS = 0.999
LIFT_Z = 0.05
GAP_MAX = 0.010
SPOKE_CLEAR_MIN = 0.010
TREAD_ASPECT_MIN = 2.5
WALL_SEAT_MIN = 0.005
SHOE_Z_MAX = 1e-3

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


def add_hex(bm, inner, outer, mat_idx):
    """A six-faced board from its inner quad and outer quad (same winding)."""
    vi = [bm.verts.new(p) for p in inner]
    vo = [bm.verts.new(p) for p in outer]
    quads = [vi, vo[::-1]] + [
        (vi[k], vo[k], vo[(k + 1) % 4], vi[(k + 1) % 4]) for k in range(4)
    ]
    for q in quads:
        bm.faces.new(q).material_index = mat_idx
    return vi + vo


def add_sweep(bm, pts, w, h, mat_idx):
    """One square-section timber swept through a polyline, mitred at bends.

    At an interior point the section lies in the bisector plane of the two
    segments, scaled by 1/cos(half the bend) so the timber keeps its width
    through the bend. One shell: a shaft that bends is one piece of wood.
    """
    pts = [Vector(p) for p in pts]
    dirs = [(b - a).normalized() for a, b in zip(pts, pts[1:])]
    rings = []
    for i, p in enumerate(pts):
        if i == 0:
            t, k = dirs[0], 1.0
        elif i == len(pts) - 1:
            t, k = dirs[-1], 1.0
        else:
            t = (dirs[i - 1] + dirs[i]).normalized()
            k = 1.0 / max(0.5, dirs[i - 1].dot(t))
        side = t.cross(Vector((0.0, 0.0, 1.0))).normalized()
        up = side.cross(t).normalized()
        rings.append([
            bm.verts.new(p + (side * sx * w / 2.0 + up * sz * h / 2.0) * k)
            for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))
        ])
    for a, b in zip(rings, rings[1:]):
        for j in range(4):
            j2 = (j + 1) % 4
            bm.faces.new((a[j], a[j2], b[j2], b[j])).material_index = mat_idx
    bm.faces.new(rings[0][::-1]).material_index = mat_idx
    bm.faces.new(rings[-1]).material_index = mat_idx
    return [v for r in rings for v in r]


def add_cyl(bm, loc, radius, depth, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    geo = bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=True,
        segments=segments,
        radius1=radius,
        radius2=radius,
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


def add_ring(bm, loc, r_mid, radial_t, width, segments, mat_idx, euler=(0.0, 0.0, 0.0)):
    """Flat-sided ring (felloe / tyre). Quads only; box cross-section."""
    r_in = r_mid - radial_t
    r_out = r_mid + radial_t
    hw = width / 2.0
    rings = []
    for i in range(segments):
        u = i * (2.0 * math.pi / segments)
        cu = math.cos(u)
        su = math.sin(u)
        rings.append(
            [
                bm.verts.new((r_in * cu, r_in * su, -hw)),
                bm.verts.new((r_out * cu, r_out * su, -hw)),
                bm.verts.new((r_out * cu, r_out * su, hw)),
                bm.verts.new((r_in * cu, r_in * su, hw)),
            ]
        )
    for i in range(segments):
        i2 = (i + 1) % segments
        a = rings[i]
        b = rings[i2]
        for quad in (
            (a[1], b[1], b[2], a[2]),
            (a[3], b[3], b[0], a[0]),
            (a[2], b[2], b[3], a[3]),
            (a[0], b[0], b[1], a[1]),
        ):
            face = bm.faces.new(quad)
            face.material_index = mat_idx
    verts = [v for ring in rings for v in ring]
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    return verts


def add_rim(bm, loc, major, minor, mat_idx, euler=(0.0, 0.0, 0.0)):
    """Torus rim — used only by the --pipe-rim falsifier."""
    n_major = 16
    n_minor = 8
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
    for i in range(n_major):
        i2 = (i + 1) % n_major
        for j in range(n_minor):
            j2 = (j + 1) % n_minor
            face = bm.faces.new(
                (rings[i][j], rings[i2][j], rings[i2][j2], rings[i][j2])
            )
            face.material_index = mat_idx
    verts = [v for ring in rings for v in ring]
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    return verts


def add_wheel(bm, loc, wood, metal, pipe_rim, spoke_t):
    if pipe_rim:
        # Metal is the outer tyre so named-support zmin stays 0 and the
        # falsifier can reach the tread-aspect gate (exit 18). An inner
        # metal torus floats and trips exit 16 first.
        wood.extend(
            add_rim(
                bm, loc, RIM_MAJOR, RIM_MINOR_PIPE * 0.45, WOOD_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )
        metal.extend(
            add_rim(
                bm, loc, RIM_MAJOR + 0.004, RIM_MINOR_PIPE, METAL_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )
    else:
        wood.extend(
            add_ring(
                bm, loc, RIM_MAJOR, RIM_RADIAL, RIM_W, 16, WOOD_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )
        metal.extend(
            add_ring(
                bm, loc,
                RIM_MAJOR + RIM_RADIAL + TYRE_T / 2.0 - TYRE_BITE / 2.0,
                TYRE_T / 2.0 + TYRE_BITE / 2.0,
                TYRE_W, 16, METAL_IDX,
                euler=(math.pi / 2.0, 0.0, 0.0),
            )
        )
    wood.extend(
        add_cyl(
            bm, loc, HUB_R, HUB_W, 12, WOOD_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
    )
    inner = HUB_R * 0.4
    outer = RIM_MAJOR - RIM_RADIAL + 0.008
    mid_r = 0.5 * (inner + outer)
    slen = outer - inner
    for i in range(N_SPOKES):
        a = i * (2.0 * math.pi / N_SPOKES)
        dx = math.cos(a)
        dz = math.sin(a)
        cx = loc[0] + dx * mid_r
        cy = loc[1]
        cz = loc[2] + dz * mid_r
        wood.extend(
            add_box(
                bm, (cx, cy, cz), (slen, spoke_t * 0.85, spoke_t), WOOD_IDX,
                euler=(0.0, -a, 0.0),
            )
        )
    metal.extend(
        add_cyl(
            bm, loc, HUB_R + 0.010, 0.016, 12, METAL_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
    )
    metal.extend(
        add_cyl(
            bm, loc, 0.014, FORK_Y * 2.0 + 0.04, 10, METAL_IDX,
            euler=(math.pi / 2.0, 0.0, 0.0),
        )
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


def add_board_stack(bm, center, size, n, seam, mat_idx):
    """A wall of ``n`` boards stacked in Z with ``seam`` between them."""
    cx, cy, cz = center
    sx, sy, sz = size
    h = (sz - (n - 1) * seam) / n
    z = cz - sz / 2.0 + h / 2.0
    verts = []
    for _ in range(n):
        verts.extend(add_box(bm, (cx, cy, z), (sx, sy, h), mat_idx))
        z += h + seam
    return verts


def build_barrow_mesh(
    name, bevel_offset, bevel_segments,
    pipe_rim=False, fat_spokes=False, short_legs=False, float_walls=False,
    wide_seams=False, split_shafts=False, box_tray=False,
):
    bm = bmesh.new()
    try:
        body = []
        metal = []
        spoke_t = HUB_R * 2.2 if fat_spokes else SPOKE_T
        shoe_z = 0.05 if short_legs else 0.0
        shoe_top = shoe_z + SHOE_H
        floor_bot = SHAFT_Z + SHAFT_H / 2.0
        floor_z = floor_bot + FLOOR_T / 2.0
        floor_top = floor_bot + FLOOR_T
        seat = -0.003 if float_walls else WALL_SEAT
        zb = floor_top - seat          # inner bottom edge of every wall
        T = WALL_T

        def shaft_y(x):
            """Shaft centreline half-spacing under the tray (linear taper)."""
            t = (x - TRAY_X0) / (TRAY_X1 - TRAY_X0)
            return SHAFT_Y + (SHAFT_Y_FRONT - SHAFT_Y) * t

        # ---- the frame: two shafts, legs, a bearer under the tray front
        for ysign in (-1.0, 1.0):
            path = [
                (HANDLE_X, ysign * HANDLE_Y, HANDLE_Z),
                (TRAY_X0, ysign * SHAFT_Y, SHAFT_Z),
                (TRAY_X1, ysign * SHAFT_Y_FRONT, SHAFT_Z),
                (WHEEL_X, ysign * FORK_Y, WHEEL_Z),
            ]
            if split_shafts:
                # --split-shafts: the old three separate boxes per side
                for a, b in zip(path, path[1:]):
                    body.extend(add_oriented_box(bm, a, b, (SHAFT_W, SHAFT_H), WOOD_IDX))
            else:
                body.extend(add_sweep(bm, path, SHAFT_W, SHAFT_H, WOOD_IDX))
            ly = shaft_y(LEG_X)
            foot = (LEG_X + 0.02, ysign * (ly + LEG_SPLAY), shoe_top)
            body.extend(
                add_oriented_box(
                    bm, (LEG_X, ysign * ly, SHAFT_Z), foot, (0.034, 0.034), WOOD_IDX,
                )
            )
            metal.extend(
                add_box(
                    bm,
                    (foot[0], foot[1], shoe_z + SHOE_H / 2.0),
                    (SHOE_XY[0], SHOE_XY[1], SHOE_H),
                    METAL_IDX,
                )
            )
            metal.extend(
                add_box(
                    bm,
                    (WHEEL_X, ysign * (FORK_Y - SHAFT_W / 2.0 - 0.005), WHEEL_Z),
                    (0.040, 0.008, 0.040),
                    METAL_IDX,
                )
            )

        # leg stretcher, its ends on the leg axes at its height
        ly = shaft_y(LEG_X)
        f = (SHAFT_Z - LEG_BRACE_Z) / (SHAFT_Z - shoe_top)
        by = ly + LEG_SPLAY * f
        bx = LEG_X + 0.02 * f
        body.extend(
            add_oriented_box(
                bm, (bx, -by, LEG_BRACE_Z), (bx, by, LEG_BRACE_Z), (0.028, 0.028), WOOD_IDX,
            )
        )
        # bearer between the shafts under the tray front, ends buried in the
        # shafts; the old spreader stood inside the wheel between the forks
        bx = TRAY_X1 - BEARER_BACK
        body.extend(
            add_oriented_box(
                bm, (bx, -shaft_y(bx), SHAFT_Z), (bx, shaft_y(bx), SHAFT_Z),
                (0.030, SHAFT_H * 0.8), WOOD_IDX,
            )
        )

        # ---- the tray: a hopper between a bottom and a top outline.
        # Heights are vertical; each wall is the planar band between its
        # bottom edge and its top edge. --box-tray stands every wall
        # vertical on the TOP outline, so the envelope stays put.
        tf, tr, tl = math.tan(FLARE), math.tan(RAKE), math.tan(REAR_LEAN)
        cf, cr, cl = math.cos(FLARE), math.cos(RAKE), math.cos(REAR_LEAN)

        def side_y(h):
            return TRAY_YB + (WALL_H if box_tray else h) * tf

        def front_x(h):
            return TRAY_X1 + (FRONT_H if box_tray else h) * tr

        def rear_x(h):
            return TRAY_X0 - (REAR_H if box_tray else h) * tl

        # outward horizontal offset of a wall's outer face (thickness T
        # measured along the wall's normal)
        off_s = T if box_tray else T / cf
        off_f = T if box_tray else T / cr
        off_r = T if box_tray else T / cl

        tray = []
        # floor: slats across the shafts, under every wall's full footprint
        fx0 = rear_x(0.0) - off_r
        fx1 = front_x(0.0) + off_f
        slat_w = (fx1 - fx0 - (N_FLOOR - 1) * SLAT_GAP) / N_FLOOR
        slat_y = 2.0 * (side_y(0.0) + off_s)
        for i in range(N_FLOOR):
            x = fx0 + slat_w / 2.0 + i * (slat_w + SLAT_GAP)
            tray.extend(
                add_box(bm, (x, 0.0, floor_z), (slat_w, slat_y, FLOOR_T), WOOD_IDX)
            )

        # --wide-seams: the same boards and triangles, seams past the band
        seam_w = WIDE_SEAM if wide_seams else WALL_SEAM

        def bands(height, n):
            b = (height - (n - 1) * seam_w) / n
            return [(k * (b + seam_w), k * (b + seam_w) + b) for k in range(n)]

        for s in (-1.0, 1.0):
            # side boards run past the end walls' outer faces (the ends are
            # housed into them), following the rake and the lean
            for h0, h1 in bands(WALL_H, WALL_BOARDS):
                def ring(h, out):
                    # outer face: the inner point moved T along the normal
                    ny, nz = (1.0, 0.0) if box_tray else (cf, -math.sin(FLARE))
                    y = s * (side_y(h) + (T * ny if out else 0.0))
                    z = zb + h + (T * nz if out else 0.0)
                    return [
                        (rear_x(h) - off_r, y, z),
                        (front_x(h) + off_f, y, z),
                    ]
                inner = ring(h0, False) + ring(h1, False)[::-1]
                outer = ring(h0, True) + ring(h1, True)[::-1]
                if s < 0:
                    inner, outer = inner[::-1], outer[::-1]
                tray.extend(add_hex(bm, inner, outer, WOOD_IDX))

        def end_wall(height, n, x_of, off, sign, angle):
            """Front (sign +1) or rear (-1) boards, ends housed half a
            board into the side walls."""
            for h0, h1 in bands(height, n):
                def edge(h, out):
                    nx, nz = (1.0, 0.0) if box_tray else (math.cos(angle), -math.sin(angle))
                    x = x_of(h) + sign * (T * nx if out else 0.0)
                    z = zb + h + (T * nz if out else 0.0)
                    y = side_y(h) + 0.5 * off_s
                    return [(x, -y, z), (x, y, z)]
                inner = edge(h0, False) + edge(h1, False)[::-1]
                outer = edge(h0, True) + edge(h1, True)[::-1]
                if sign < 0:
                    inner, outer = inner[::-1], outer[::-1]
                tray.extend(add_hex(bm, inner, outer, WOOD_IDX))

        end_wall(FRONT_H, WALL_BOARDS, front_x, off_f, 1.0, RAKE)
        end_wall(REAR_H, 1, rear_x, off_r, -1.0, REAR_LEAN)
        body.extend(tray)
        tray_set = set(tray)

        # iron straps: up each side wall's outer face from the floor's
        # underside, stopping short of the wall top, joined under the floor
        for sx in (TRAY_X0 + TRAY_L * 0.28, TRAY_X0 + TRAY_L * 0.72):
            z0 = floor_bot
            ry = side_y(0.0) + off_s + STRAP_T / 2.0
            for s in (-1.0, 1.0):
                top_h = WALL_H - STRAP_TOP_CLEAR
                # the outer face at height z is side_y + off_s horizontally
                ty = side_y(top_h) + off_s + STRAP_T / 2.0
                tz = zb + top_h
                metal.extend(add_oriented_box(
                    bm, (sx, s * ry, z0), (sx, s * ry, zb), (0.018, STRAP_T), METAL_IDX,
                ))
                metal.extend(add_oriented_box(
                    bm, (sx, s * ry, zb - 0.004), (sx, s * ty, tz), (0.018, STRAP_T), METAL_IDX,
                ))
            metal.extend(add_oriented_box(
                bm, (sx, -ry, z0), (sx, ry, z0), (0.018, STRAP_T), METAL_IDX,
            ))

        if bevel_offset > 0.0:
            edges = []
            # set order follows memory addresses; sort so the bevel, and
            # the face order it produces, are the same on every run
            bm.edges.index_update()
            for e in sorted({e for v in body for e in v.link_edges}, key=lambda e: e.index):
                if min(v.co.z for v in e.verts) < shoe_top + 0.008:
                    continue
                if all(v in tray_set for v in e.verts) and max(
                    v.co.z for v in e.verts
                ) < floor_top - 1e-4:
                    continue
                edges.append(e)
            if edges:
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
                # a face beveled on some edges and not others comes out an
                # n-gon; split those, the triangle count is the same
                ngons = [f for f in bm.faces if len(f.verts) > 4]
                if ngons:
                    bmesh.ops.triangulate(bm, faces=ngons)

        wood_wheel = []
        wheel_z = (
            RIM_MAJOR + 0.004 + RIM_MINOR_PIPE if pipe_rim else WHEEL_Z
        )
        add_wheel(
            bm, (WHEEL_X, 0.0, wheel_z), wood_wheel, metal, pipe_rim, spoke_t
        )

        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy

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
        "euler": nv - ne + nf,
    }


def zfight_pairs(me):
    """Disjoint faces sharing a plane and a position, which z-fight."""
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
        min(p.x for p in pts),
        min(p.y for p in pts),
        min(p.z for p in pts),
        max(p.x for p in pts),
        max(p.y for p in pts),
        max(p.z for p in pts),
    )


def support_audit(me):
    """Named supports must each sit on Z=0. AABB zmin is the lowest one."""
    groups = shells(me)
    metal_groups = []
    for g in groups:
        faces = [
            p for p in me.polygons if all(i in set(g) for i in p.vertices)
        ]
        if not faces:
            continue
        if faces[0].material_index != METAL_IDX:
            continue
        metal_groups.append(shell_aabb(me, g))
    shoes = [a for a in metal_groups if a[5] < 0.08 and (a[4] - a[1]) > 0.03]
    tyres = [
        a for a in metal_groups
        if (a[3] - a[0]) > 0.25 and (a[5] - a[2]) > 0.25
    ]
    shoe_z = min((a[2] for a in shoes), default=99.0)
    tyre_z = min((a[2] for a in tyres), default=99.0)
    return {
        "shoes": len(shoes),
        "tyres": len(tyres),
        "shoe_z": shoe_z,
        "tyre_z": tyre_z,
    }


def tray_parts(me):
    """Wood shells of the tray, classified: side boards per side, front and
    rear boards, floor slats. Each entry is (shell vertex indices, AABB).

    A wall board is taller than a slat (dz > 0.05) and within its wall's
    reach of the tray: side boards are long in X and outboard of the floor,
    end boards are wide in Y and at the tray's front or rear.
    """
    out = {"side": {-1: [], 1: []}, "front": [], "rear": [], "floor": []}
    for g in shells(me):
        faces = [p for p in me.polygons if all(i in set(g) for i in p.vertices)]
        if not faces or faces[0].material_index != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        cx, cy = 0.5 * (a[0] + a[3]), 0.5 * (a[1] + a[4])
        if dz < FLOOR_T * 2.2 and dy > TRAY_W and a[0] > TRAY_X0 - 0.2:
            out["floor"].append((g, a))
        elif dz <= 0.05 or dz > FRONT_H + 0.08:
            continue
        elif dx > TRAY_L * 0.8 and abs(cy) > TRAY_YB * 0.9 and dy < 0.1:
            out["side"][1 if cy > 0.0 else -1].append((g, a))
        elif dy > TRAY_W * 0.8 and dx < 0.2 and cx > TRAY_X1 - 0.05:
            out["front"].append((g, a))
        elif dy > TRAY_W * 0.8 and dx < 0.2 and cx < TRAY_X0 + 0.05:
            out["rear"].append((g, a))
    return out


def tray_size(me):
    """Side-wall pair: length, track, and height of the hopper they bound."""
    sides = {}
    for k, boards in tray_parts(me)["side"].items():
        for _g, a in boards:
            b = sides.get(k)
            sides[k] = a if b is None else (
                min(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]),
                max(a[3], b[3]), max(a[4], b[4]), max(a[5], b[5]),
            )
    if len(sides) < 2:
        return (0.0, 0.0, 0.0)
    left, right = sides[-1], sides[1]
    return (
        0.5 * ((left[3] - left[0]) + (right[3] - right[0])),
        right[4] - left[1],
        0.5 * ((left[5] - left[2]) + (right[5] - right[2])),
    )


def wall_floor_seat(me):
    """How far the walls drop into the floor slats, metres.

    Per board: the floor top minus the lowest vertex on the board's INNER
    face. Of the board's two largest faces (inner and outer), the inner one
    is the one whose centre lies nearer the tray's centre in plan; the
    board's vertices on that face's plane give the inner bottom edge. A
    leaning board's outer bottom edge sits lower than its inner one, so the
    board's AABB zmin would overstate the seat. The smallest seat over every
    wall board is returned; a wall that only kisses the floor reports ~0 and
    fails the seat floor.
    """
    parts = tray_parts(me)
    if not parts["floor"]:
        return -1.0
    floor_top = max(a[5] for _g, a in parts["floor"])
    fx = [a for _g, a in parts["floor"]]
    centre = Vector((0.5 * (min(a[0] for a in fx) + max(a[3] for a in fx)), 0.0))

    def inner_bottom(g):
        member = set(g)
        faces = sorted((p for p in me.polygons if all(i in member for i in p.vertices)),
                       key=lambda p: -p.area)[:2]
        inner = min(faces, key=lambda p: (p.center.xy - centre).length)
        return min(me.vertices[i].co.z for i in g
                   if abs((me.vertices[i].co - inner.center).dot(inner.normal)) < 1e-4)

    # each wall seats on its lowest board; the boards above it stack on it
    walls = [parts["side"][-1], parts["side"][1], parts["front"], parts["rear"]]
    seats = [floor_top - min(inner_bottom(g) for g, _a in w) for w in walls if w]
    return min(seats) if seats else -1.0


def wall_boards(me):
    """Boards per side wall and in the front wall, and the seams between them.

    Seams are measured in each wall's own plane, along the direction that
    runs up the wall, taken from the boards' own largest face: the gap
    between one board's top and the next one's bottom. An AABB seam in Z
    would read negative on a leaning board, because its outer face sits
    lower than its inner one.
    """
    parts = tray_parts(me)

    def up_of(boards, along):
        if not boards:
            return Vector((0.0, 0.0, 1.0))
        member = set(boards[0][0])
        big = max((p for p in me.polygons if all(i in member for i in p.vertices)),
                  key=lambda p: p.area)
        u = big.normal.cross(along).normalized()
        return u if u.z > 0.0 else -u

    stacks = [(b, up_of(b, Vector(ax))) for b, ax in (
        (parts["side"][-1], (1.0, 0.0, 0.0)), (parts["side"][1], (1.0, 0.0, 0.0)),
        (parts["front"], (0.0, 1.0, 0.0)))]
    seams = []
    for boards, u in stacks:
        spans = sorted(
            (min(me.vertices[i].co.dot(u) for i in g),
             max(me.vertices[i].co.dot(u) for i in g))
            for g, _a in boards
        )
        seams.extend(b[0] - a[1] for a, b in zip(spans, spans[1:]))
    return len(parts["side"][-1]), len(parts["side"][1]), len(parts["front"]), seams


def tray_flare(me):
    """(side flare, front rake) in degrees, from the boards' own faces.

    For each side board, the largest face whose normal points mostly
    outward in Y; the flare is how far that normal dips below horizontal.
    The same for front boards along X. A box tray measures 0 and 0.
    """
    parts = tray_parts(me)

    def lean(boards, axis):
        out = []
        for g, _a in boards:
            member = set(g)
            faces = [p for p in me.polygons
                     if all(i in member for i in p.vertices) and abs(p.normal[axis]) > 0.5]
            if faces:
                n = max(faces, key=lambda p: p.area).normal
                out.append(math.degrees(math.asin(min(1.0, abs(n.z)))))
        return min(out) if out else 0.0

    return (lean(parts["side"][-1] + parts["side"][1], 1), lean(parts["front"], 0))


def shaft_runs(me):
    """Wood shells that run unbroken from behind the tray to beyond its front.

    A barrow's two shafts are single timbers from grip to axle; built as
    handle, level run and fork, no one shell spans the tray and this is 0.
    """
    n = 0
    for g in shells(me):
        faces = [p for p in me.polygons if all(i in set(g) for i in p.vertices)]
        if not faces or faces[0].material_index != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        if a[0] < TRAY_X0 - 0.2 and a[3] > TRAY_X1 + 0.1:
            n += 1
    return n


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

    Every board, shaft, leg and spoke is its own shell, so each gets one
    tone and grain running along its own long axis.
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
    """Grain along each board and shaft (``GrainDir``), tone per piece (``PlankTone``)."""
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


def barrow_materials():
    """(wood, iron): shared by the check, the render and inspection."""
    wood = wood_material("BarrowWood")
    metal = principled(
        "BarrowIron", (0.17, 0.165, 0.155, 1.0), 0.80, 0.46,
        noise_scale=18.0, wear=(0.20, 0.085, 0.032, 1.0),
    )
    return wood, metal


def spoke_clearance(me):
    """Hub diameter minus fattest spoke thickness.

    Spokes are the wood shells around the wheel centroid. Floor slats
    also have a thin Z and a long X; matching on those dimensions
    reports a false clearance that ``--fat-spokes`` cannot violate.
    """
    groups = shells(me)
    hubs = []
    spoke_thick = []
    for g in groups:
        faces = [
            p for p in me.polygons if all(i in set(g) for i in p.vertices)
        ]
        if not faces or faces[0].material_index != WOOD_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        cx = 0.5 * (a[0] + a[3])
        cz = 0.5 * (a[2] + a[5])
        if abs(cx - WHEEL_X) > RIM_MAJOR or abs(cz - WHEEL_Z) > RIM_MAJOR:
            continue
        if abs(dy - HUB_W) < 0.012 and max(dx, dz) < HUB_R * 2.4:
            hubs.append(a)
            continue
        if dx > RIM_MAJOR and dz > RIM_MAJOR:
            continue
        thick = min(dx, dy, dz)
        longest = max(dx, dy, dz)
        if longest > HUB_R * 2.0 and thick < HUB_R * 2.6:
            spoke_thick.append(thick)
    if not hubs:
        return -1.0
    hub = hubs[0]
    hub_d = max(hub[3] - hub[0], hub[5] - hub[2])
    if not spoke_thick:
        return hub_d
    return hub_d - max(spoke_thick)


def tread_aspect(me):
    """Tyre Y-width over radial thickness. Flat treads are wide; torii are not.

    Measured on the tyre shell's own verts, not on every vert in its AABB —
    the felloe and hub sit inside that box and would inflate the radial span.
    """
    groups = shells(me)
    best = None
    for g in groups:
        member = set(g)
        faces = [
            p for p in me.polygons if all(i in member for i in p.vertices)
        ]
        if not faces or faces[0].material_index != METAL_IDX:
            continue
        a = shell_aabb(me, g)
        dx, dy, dz = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        if dx < 0.25 or dz < 0.25:
            continue
        cx = 0.5 * (a[0] + a[3])
        cz = 0.5 * (a[2] + a[5])
        rs = [
            math.hypot(me.vertices[i].co.x - cx, me.vertices[i].co.z - cz)
            for i in g
        ]
        radial = max(rs) - min(rs)
        if radial < 1e-6:
            continue
        aspect = dy / radial
        score = dx * dz
        if best is None or score > best[0]:
            best = (score, aspect)
    return best[1] if best else 0.0


def min_mat_distance(me, ia, ib):
    bm_a = bmesh.new()
    bm_b = bmesh.new()
    try:
        bm_a.from_mesh(me)
        bm_b.from_mesh(me)
        drop_a = [f for f in bm_a.faces if f.material_index != ia]
        drop_b = [f for f in bm_b.faces if f.material_index != ib]
        if drop_a:
            bmesh.ops.delete(bm_a, geom=drop_a, context="FACES")
        if drop_b:
            bmesh.ops.delete(bm_b, geom=drop_b, context="FACES")
        if not bm_a.faces or not bm_b.faces:
            return 1e9
        tree = BVHTree.FromBMesh(bm_b)
        best = 1e9
        for src in list(bm_a.verts) + list(bm_a.faces):
            co = src.co if hasattr(src, "co") else src.calc_center_median()
            hit = tree.find_nearest(co)
            if hit[0] is None:
                continue
            best = min(best, hit[3])
        return best
    finally:
        bm_a.free()
        bm_b.free()


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, SHAFT_Z))
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
    img = bpy.data.images.new("BarrowNrm", size, size, alpha=True, float_buffer=False)
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
    skip_decimate, lift_z=False, stray_vert=False,
    fat_spokes=False, pipe_rim=False, short_legs=False, float_walls=False,
    wide_seams=False, split_shafts=False, box_tray=False,
):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    flags = dict(
        pipe_rim=pipe_rim, fat_spokes=fat_spokes,
        short_legs=short_legs, float_walls=float_walls,
        wide_seams=wide_seams, split_shafts=split_shafts, box_tray=box_tray,
    )
    low = build_barrow_mesh("BarrowLow", 0.004, 2, **flags)
    high = build_barrow_mesh("BarrowHigh", 0.004, 4, **flags)
    wood, metal = barrow_materials()
    paint_planks(low.data)
    paint_planks(high.data)
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
        return fail("barrow mesh did not build", 3), None, None, None, None, None

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
        return fail("barrow has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BarrowLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BarrowLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_barrow_mesh("BarrowColSrc", 0.0, 1, **flags)
    collider = convex_hull_collider(collider_src, "BarrowCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_wheelbarrow_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender points TMPDIR at the working directory, so the export must not
    # outlive the measurement.
    if os.path.exists(export_path):
        os.remove(export_path)

    hyg = hygiene_audit(low.data)
    zf = zfight_pairs(low.data)
    sup = support_audit(low.data)
    tsz = tray_size(low.data)
    runs = shaft_runs(low.data)
    flare, rake = tray_flare(low.data)
    sclear = spoke_clearance(low.data)
    aspect = tread_aspect(low.data)
    gap_mw = min_mat_distance(low.data, METAL_IDX, WOOD_IDX)
    seat = wall_floor_seat(low.data)
    n_left, n_right, n_front, seams = wall_boards(low.data)

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
        f"measured supports shoes={sup['shoes']} shoe_z={sup['shoe_z']:.5f} "
        f"tyres={sup['tyres']} tyre_z={sup['tyre_z']:.5f}"
    )
    print(
        f"measured tray=({tsz[0]:.4f},{tsz[1]:.4f},{tsz[2]:.4f}) "
        f"shaft_runs={runs} flare={flare:.2f} rake={rake:.2f} spoke_clear={sclear:.5f} "
        f"tread_aspect={aspect:.3f} gap_metal_wood={gap_mw:.5f} "
        f"wall_floor_seat={seat:.5f}"
    )
    print(
        f"measured wall_boards left={n_left} right={n_right} front={n_front} "
        f"seams={min(seams, default=0.0):.5f}..{max(seams, default=0.0):.5f}"
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
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf}",
            15,
        ), None, None, None, None, None
    if abs(bb[2]) > ZMIN_EPS:
        return fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)",
            16,
        ), None, None, None, None, None
    if sup["shoes"] < 2 or sup["shoe_z"] > SHOE_Z_MAX:
        return fail(
            f"shoe supports {sup['shoes']} shoe_z={sup['shoe_z']:.5f} "
            "(--short-legs is the designed fail)",
            16,
        ), None, None, None, None, None
    if sup["tyres"] < 1 or sup["tyre_z"] > SHOE_Z_MAX:
        return fail(
            f"tyre supports {sup['tyres']} tyre_z={sup['tyre_z']:.5f}",
            16,
        ), None, None, None, None, None
    if sclear < SPOKE_CLEAR_MIN:
        return fail(
            f"spoke clearance {sclear:.5f} < {SPOKE_CLEAR_MIN} "
            "(--fat-spokes is the designed fail)",
            17,
        ), None, None, None, None, None
    if seat < WALL_SEAT_MIN:
        return fail(
            f"wall-floor seat {seat:.5f} < {WALL_SEAT_MIN} "
            "(--float-walls is the designed fail)",
            17,
        ), None, None, None, None, None
    if (
        (n_left, n_right, n_front) != (WALL_BOARDS,) * 3
        or min(seams, default=0.0) < WALL_SEAM_MIN
        or max(seams, default=99.0) > WALL_SEAM_MAX
    ):
        return fail(
            f"wall boards left={n_left} right={n_right} front={n_front} "
            f"!= {WALL_BOARDS}, or seams "
            f"{min(seams, default=0.0):.5f}..{max(seams, default=0.0):.5f} "
            f"outside [{WALL_SEAM_MIN}, {WALL_SEAM_MAX}] "
            "(--wide-seams is the designed fail)",
            17,
        ), None, None, None, None, None
    if gap_mw > GAP_MAX:
        return fail(
            f"metal-wood gap {gap_mw:.5f} > {GAP_MAX}",
            17,
        ), None, None, None, None, None
    if aspect < TREAD_ASPECT_MIN:
        return fail(
            f"tread aspect {aspect:.3f} < {TREAD_ASPECT_MIN} "
            "(--pipe-rim is the designed fail)",
            18,
        ), None, None, None, None, None
    if runs != 2:
        return fail(
            f"{runs} shafts run unbroken from behind the tray past its front, "
            "need 2 (--split-shafts is the designed fail)",
            20,
        ), None, None, None, None, None
    if flare < math.degrees(FLARE_MIN) or rake < math.degrees(RAKE_MIN):
        return fail(
            f"tray flare {flare:.2f} deg / rake {rake:.2f} deg under "
            f"{math.degrees(FLARE_MIN):.0f} / {math.degrees(RAKE_MIN):.0f} "
            "(--box-tray is the designed fail)",
            21,
        ), None, None, None, None, None
    if (
        abs(tsz[0] - TRAY_SIZE[0]) > TRAY_SIZE_TOL[0]
        or abs(tsz[1] - TRAY_SIZE[1]) > TRAY_SIZE_TOL[1]
        or abs(tsz[2] - TRAY_SIZE[2]) > TRAY_SIZE_TOL[2]
    ):
        return fail(
            f"tray size ({tsz[0]:.4f},{tsz[1]:.4f},{tsz[2]:.4f}) "
            f"off declared {TRAY_SIZE}",
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

    low.rotation_euler.z = math.radians(-32.0)
    low.rotation_euler.x = math.radians(0.0)

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
    cam.location = (1.95, -2.35, 1.18)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.32)
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
        "--fat-spokes",
        action="store_true",
        help="falsification: spokes as thick as the hub, failing joint fit",
    )
    p.add_argument(
        "--pipe-rim",
        action="store_true",
        help="falsification: torus tyre on a flat felloe, failing tread aspect",
    )
    p.add_argument(
        "--short-legs",
        action="store_true",
        help="falsification: shoes float while the wheel still grounds the AABB",
    )
    p.add_argument(
        "--float-walls",
        action="store_true",
        help="falsification: walls kiss the floor so the seat budget fails",
    )
    p.add_argument(
        "--wide-seams",
        action="store_true",
        help="falsification: 8 mm seams between wall boards",
    )
    p.add_argument(
        "--split-shafts",
        action="store_true",
        help="falsification: each shaft as handle, level run and fork, three shells",
    )
    p.add_argument(
        "--box-tray",
        action="store_true",
        help="falsification: vertical tray walls on the same top outline",
    )
    args = p.parse_args(argv)

    code, low, _high, wood, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        fat_spokes=args.fat_spokes,
        pipe_rim=args.pipe_rim,
        short_legs=args.short_legs,
        float_walls=args.float_walls,
        wide_seams=args.wide_seams,
        split_shafts=args.split_shafts,
        box_tray=args.box_tray,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, wood, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("wheelbarrow OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
