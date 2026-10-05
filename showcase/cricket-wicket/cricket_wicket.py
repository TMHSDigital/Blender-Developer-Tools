"""Game-ready cricket wicket — a showcase piece, not an example.

Asserts budget conformance of a procedural cricket wicket as Law 8 of the
Laws of Cricket describes it: three turned ash stumps, 28 inches (711.2
mm) proud of the turf and 228.6 mm wide over their outer faces, each
topped with a grooved dome, and two stained bails whose spigots lie in
the grooves and whose barrels hang across the gaps. The stumps are driven
through a slab of turf with a worn bare patch, a chalked bowling crease
and tufts of grass. Carried through UVs, six materials, a high-to-low
normal bake, an LOD chain, a compound convex collider, and a Unity glTF
export.

The budgets that matter here are the ones a wicket fails invisibly. The
bails must lie in the grooves, not float over them: a bail lifted 6 mm
still spans the gap, still sits over the stumps, still fits the bounding
box; only the seat knows. And the stumps are a real size: thinned shafts,
a stump nudged along the crease, or a fat barrel each break a number the
Laws state, while every stump still stands on the floor.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` the grounded AABB, ``--float-stump`` the named
stumps, ``--shift-bails`` the bail footprint, ``--lift-bails`` the bail
seat, ``--sink-chalk`` the chalk line, ``--thin-stumps`` the stump
diameter, ``--skew-stump`` the mirrored stumps, ``--fat-bails`` the bail
projection.

Randomness is a fixed-seed ``random.Random`` for the grass tufts only.
DECIMATE COLLAPSE triangle counts are not byte-identical across Blender
versions — the LOD gate is a ratio band.

    blender --background --python cricket_wicket.py --
    blender --background --python cricket_wicket.py -- --lift-bails
    blender --background --python cricket_wicket.py -- --output cricket_wicket.webp
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
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402
import gallery_asset_quality  # noqa: E402

# Law 8, in metres. The stumps stand 28 in above the turf, are 9 in (228.6
# mm) wide over their outer faces, and are 1.375-1.5 in thick.
STUMP_H = 0.7112
STUMP_R = 0.01825
STUMP_SPACING = 0.09605
STUMP_SEG = 32
STUMP_SEG_HIGH = 48
THIN_SCALE = 0.90
SKEW_STUMP = 0.002
FLOAT_STUMP = 0.008

# The stump, from the foot up. The spike is driven through the turf; above
# the shaft the shoulder steps in to a neck, and the neck carries a domed
# crown cut across by a groove that runs along the line of the wicket.
TURF_T = 0.020
SPIKE = ((0.0045, 0.0030), (0.0110, 0.0100), (STUMP_R, 0.0170))
SHAFT_MID_ABOVE_TURF = 0.360
SHOULDER_BELOW_CROWN = 0.052
NECK_START_BELOW_CROWN = 0.040
NECK_R = 0.0165
NECK_TOP_BELOW_CROWN = 0.016
CROWN_R = NECK_R
CROWN_H = 0.0140
CROWN_FRACS = (0.8, 0.6, 0.4, 0.2)
GROOVE_W = 0.0065
GROOVE_FLOOR = 0.0035
GROOVE_RISE = 0.0035

# Bails: Law 8 gives 4 3/8 in overall, a 2 1/8 in barrel and spigots of 1
# 3/8 and 7/8 in. The long spigot rests on the outer stump, the short one
# on the middle stump; each bail is shifted out so the two short spigots
# meet without touching.
BAIL_LONG = 0.0349
BAIL_BARREL = 0.0540
BAIL_SHORT = 0.0222
SPIGOT_R = 0.0040
BARREL_R = 0.0100
FAT_BARREL_R = 0.0190
BAIL_SHIFT = 0.0016
BAIL_BITE = 0.0010
LIFT_BAIL = 0.005
BAIL_SEG = 16
BAIL_SEG_HIGH = 24

# Turf: a tight strip of pitch with a rolled edge, worn bare along the
# crease where the batters stand and the bowlers land, and a chalked bowling
# crease through the line of the stumps (Law 7). The popping crease, 1.22 m
# in front, is off this strip. The chalk stops at the last flat cell so it
# never rides the roll.
SLAB_X0, SLAB_X1 = -0.32, 0.32
SLAB_Y0, SLAB_Y1 = -0.20, 0.20
SLAB_NX, SLAB_NY = 16, 10
SLAB_ROLL = 0.003
WORN_C = (0.0, -0.02)
WORN_RX, WORN_RY = 0.23, 0.115
CHALK_HALF_W = 0.025
CHALK_HALF_L = 0.28
CHALK_BITE = 0.0010
CHALK_PROUD = 0.0015
SINK_CHALK = 0.0040
TUFTS = 56
TUFT_EDGE_BAND = 0.09
TUFT_INNER_KEEP = 0.18
TUFT_SPACING = 0.024
BLADES_PER_TUFT = 3
BLADE_R = 0.0018
BLADE_H = (0.022, 0.046)

# Law 5: a ball is 22.4-22.9 cm round, 71.3-72.9 mm across. This one rests on
# the worn patch with its lowest point a hair into the earth, its raised seam
# on a great circle turned off the vertical.
BALL_R = 0.0360
SMALL_BALL_R = 0.0300
BALL_SEG = 20
BALL_LATS = (-72.0, -54.0, -36.0, -18.0, 0.0, 18.0, 36.0, 54.0, 72.0)
BALL_AT = (0.175, -0.135)
BALL_TILT = 38.0
BALL_YAW = 25.0
BALL_BITE = 0.0006
FLOAT_BALL = 0.005
SEAM_R = 0.0010
SEAM_SEG = 40
SEAM_TUBE = 6
SINK_SEAM = 0.0030

BBOX_TOL = 0.010
OUTER_SIZE = (0.646, 0.406, 0.7359)

BASE_TRIS_MIN = 6100
BASE_TRIS_MAX = 6800
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 8
FACE_FLOORS = {0: 1300, 1: 630, 2: 100, 3: 135, 4: 6, 5: 1250, 6: 180, 7: 220}
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 360
STUMP_HULL_RINGS = (0, 2, 5, 6, 8)
BAIL_HULL_RINGS = (1, 3, 6, 7, 10, 12)
BALL_HULL_RINGS = (1, 3, 5, 7)
BAKE_RES = 512
CAGE_EXTRUSION = 0.004
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
STUMP_Z_MAX = 1e-4
TIP_MARGIN_MIN = 0.0005
BARREL_CLEAR_MIN = 0.0005
BAIL_PAIR_GAP_MIN = 0.0003
SEAT_MIN = 0.0005
SEAT_MAX = 0.0020
CHALK_PROUD_MIN = 0.0008
CHALK_PROUD_MAX = 0.0030
CHALK_BITE_MIN = 0.0005
STUMP_D_MIN = 0.0349
STUMP_D_MAX = 0.0381
HEIGHT_TOL = 0.0015
WIDTH = 0.2286
WIDTH_TOL = 0.0030
BALL_D_MIN = 0.0713
GAP_MIN = 0.040
MIRROR_EPS = 0.0010
PROJECT_MIN = 0.002
PROJECT_MAX = 0.0127
BALL_D_MIN_OK = 0.0713
BALL_D_MAX_OK = 0.0729
BALL_SEAT_MIN = 0.0002
BALL_SEAT_MAX = 0.0015
SEAM_PROUD_MIN = 0.0005
SEAM_PROUD_MAX = 0.0020

ASH_IDX = 0
BAIL_IDX = 1
TURF_IDX = 2
EARTH_IDX = 3
CHALK_IDX = 4
BLADE_IDX = 5
LEATHER_IDX = 6
SEAM_IDX = 7


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


# --- construction -----------------------------------------------------------


def new_island(ctx):
    ctx["next"] += 1
    return ctx["next"]


def stamp(ctx, face, island, uvmap, grain):
    face[ctx["isl"]] = island
    for loop in face.loops:
        loop[ctx["uv"]].uv = uvmap[loop.vert]
    face[ctx["gx"]], face[ctx["gy"]], face[ctx["gz"]] = grain


def island_of(ctx, faces, uvmap, grain=(1.0, 0.0, 0.0)):
    """One UV island over ``faces``; ``uvmap`` maps a vertex to (u, v)."""
    island = new_island(ctx)
    for f in faces:
        stamp(ctx, f, island, uvmap, grain)


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


def lathe(bm, profile, n, mat_idx, ctx, xf, grain, zfun=None, phase=0.0):
    """Revolve ``(r, z, cut)`` rows about local Z; ``cut`` rows go through ``zfun``.

    The first and last rows must have r = 0: they are the end poles. With
    ``n`` a multiple of 4 a ring vertex lies on every local axis, so the
    stumps (axis Z) and the bails (axis turned to X) both keep a vertex
    exactly one radius below the axis.
    """
    rings, poles = [], []
    for r, z, cut in profile:
        if r <= 0.0:
            zz = zfun(0.0, 0.0, z) if (cut and zfun) else z
            poles.append(bm.verts.new(xf @ Vector((0.0, 0.0, zz))))
            continue
        ring = []
        for k in range(n):
            a = 2.0 * math.pi * (k + phase) / n
            x, y = r * math.cos(a), r * math.sin(a)
            zz = zfun(x, y, z) if (cut and zfun) else z
            ring.append(bm.verts.new(xf @ Vector((x, y, zz))))
        rings.append(ring)
    tube(bm, rings, poles, mat_idx, ctx, [grain] * len(rings))


def dome(r):
    return CROWN_H * (1.0 - (r / CROWN_R) ** 2)


def groove_z(y, z_dome):
    """The crown's height over a point at lateral offset ``y`` (zs-relative)."""
    if abs(y) < GROOVE_W:
        return min(z_dome, GROOVE_FLOOR + GROOVE_RISE * (abs(y) / GROOVE_W) ** 2)
    return z_dome


def crown_local_max(n):
    """Highest crown vertex above the crown's base ring, for ``n`` segments."""
    best = groove_z(0.0, dome(0.0))
    for f in CROWN_FRACS:
        r = f * CROWN_R
        for k in range(n):
            y = r * math.sin(2.0 * math.pi * k / n)
            best = max(best, groove_z(y, dome(r)))
    return best


def stump_profile(zs, radius_scale):
    """Foot pole, spike, shaft, shoulder, neck, crown rings, crown pole."""
    rows = [(0.0, 0.0, False)]
    rows += [(r * radius_scale if r >= STUMP_R else r, z, False) for r, z in SPIKE]
    zt = TURF_T
    rs = STUMP_R * radius_scale
    rows += [(rs, zt, False), (rs, zt + SHAFT_MID_ABOVE_TURF, False),
             (rs, zs - SHOULDER_BELOW_CROWN, False),
             (NECK_R, zs - NECK_START_BELOW_CROWN, False),
             (NECK_R, zs - NECK_TOP_BELOW_CROWN, False),
             (CROWN_R, zs, True)]
    for f in CROWN_FRACS:
        rows.append((f * CROWN_R, zs + dome(f * CROWN_R), True))
    rows.append((0.0, zs + dome(0.0), True))
    return rows


def add_stump(bm, ctx, cx, seg, zs, radius_scale, lift):
    def cut(x, y, z):
        return zs + groove_z(y, z - zs)

    xf = Matrix.Translation(Vector((cx, 0.0, lift)))
    lathe(bm, stump_profile(zs, radius_scale), seg, ASH_IDX, ctx, xf, (0.0, 0.0, 1.0), cut)


def bail_profile(barrel_r):
    """(r, t) from the long tip, through the barrel, to the short tip."""
    """A turned barrel: a crisp shoulder off each spigot, then a full-width collar
    set off from the body by a V-cut bead line, as a bail is turned on the lathe."""
    ll, lb, ls = BAIL_LONG, BAIL_BARREL, BAIL_SHORT
    r = barrel_r
    return [
        (0.0, 0.0, False), (0.0030, 0.0006, False), (SPIGOT_R, 0.0020, False),
        (SPIGOT_R, ll - 0.0010, False), (SPIGOT_R, ll, False),
        (r * 0.72, ll + 0.0012, False), (r * 0.94, ll + 0.0040, False), (r, ll + 0.0075, False),
        (r, ll + 0.0135, False), (r * 0.84, ll + 0.0152, False), (r * 0.97, ll + 0.0170, False),
        (r * 0.97, ll + lb - 0.0170, False), (r * 0.84, ll + lb - 0.0152, False),
        (r, ll + lb - 0.0135, False),
        (r, ll + lb - 0.0075, False), (r * 0.94, ll + lb - 0.0040, False),
        (r * 0.72, ll + lb - 0.0012, False),
        (SPIGOT_R, ll + lb, False), (SPIGOT_R, ll + lb + 0.0010, False),
        (SPIGOT_R, ll + lb + ls - 0.0020, False), (0.0030, ll + lb + ls - 0.0006, False),
        (0.0, ll + lb + ls, False),
    ]


def add_bail(bm, ctx, side, axis_z, seg, barrel_r, lift):
    """Bail on ``side`` (-1 left, +1 right): long spigot out, short spigot in."""
    centre = side * (STUMP_SPACING * 0.5 + BAIL_SHIFT)
    tip = centre + side * (BAIL_BARREL * 0.5 + BAIL_LONG)
    # local +Z -> world +X (left bail) or -X (right bail).
    rot = Matrix.Rotation(math.pi * 0.5 * (-side), 4, "Y")
    xf = Matrix.Translation(Vector((tip, 0.0, axis_z + lift))) @ rot
    # The right bail's facets are turned half a segment, so the two collinear
    # spigots do not share facet planes (a coplanar cross-shell pair by definition).
    lathe(bm, bail_profile(barrel_r), seg, BAIL_IDX, ctx, xf, (1.0, 0.0, 0.0),
          phase=0.5 if side > 0 else 0.0)


def add_slab(bm, ctx):
    nx, ny = SLAB_NX, SLAB_NY
    dx, dy = (SLAB_X1 - SLAB_X0) / nx, (SLAB_Y1 - SLAB_Y0) / ny
    top = {}
    for i in range(nx + 1):
        for j in range(ny + 1):
            x, y, z = SLAB_X0 + i * dx, SLAB_Y0 + j * dy, TURF_T
            if i in (0, nx) or j in (0, ny):
                if i == 0:
                    x -= SLAB_ROLL
                if i == nx:
                    x += SLAB_ROLL
                if j == 0:
                    y -= SLAB_ROLL
                if j == ny:
                    y += SLAB_ROLL
                z -= SLAB_ROLL
            top[(i, j)] = bm.verts.new((x, y, z))
    top_faces = []
    for i in range(nx):
        for j in range(ny):
            f = bm.faces.new((top[(i, j)], top[(i + 1, j)], top[(i + 1, j + 1)], top[(i, j + 1)]))
            cx = SLAB_X0 + (i + 0.5) * dx - WORN_C[0]
            cy = SLAB_Y0 + (j + 0.5) * dy - WORN_C[1]
            worn = (cx / WORN_RX) ** 2 + (cy / WORN_RY) ** 2 < 1.0
            f.material_index = EARTH_IDX if worn else TURF_IDX
            top_faces.append(f)
    island_of(ctx, top_faces, {v: (v.co.x, v.co.y) for v in top.values()})

    order = ([(i, 0) for i in range(nx + 1)] + [(nx, j) for j in range(1, ny + 1)]
             + [(i, ny) for i in range(nx - 1, -1, -1)] + [(0, j) for j in range(ny - 1, 0, -1)])
    upper = [top[k] for k in order]
    lower = [bm.verts.new((v.co.x, v.co.y, 0.0)) for v in upper]
    arc = [0.0]
    for a, b in zip(upper, upper[1:] + upper[:1]):
        arc.append(arc[-1] + (b.co - a.co).length)
    wall_faces = []
    m = len(upper)
    for k in range(m):
        a, b = k, (k + 1) % m
        f = bm.faces.new((upper[a], lower[a], lower[b], upper[b]))
        f.material_index = EARTH_IDX
        wall_faces.append(f)
    # A ring that closes on itself needs per-face UVs: the seam vertex has two u values.
    island = new_island(ctx)
    for k, f in enumerate(wall_faces):
        a, b = k, (k + 1) % m
        uv = {upper[a]: (arc[k], TURF_T), lower[a]: (arc[k], 0.0),
              lower[b]: (arc[k + 1], 0.0), upper[b]: (arc[k + 1], TURF_T)}
        stamp(ctx, f, island, uv, (1.0, 0.0, 0.0))
    # Off the stump line: on the slab's centre it would weld to the middle
    # stump's spike point at the origin.
    centre = bm.verts.new((0.0, SLAB_Y0 + 0.75 * (SLAB_Y1 - SLAB_Y0), 0.0))
    # A fan's triangles share a corner, so a planar map overlaps their AABBs;
    # unroll it into one strip per triangle instead.
    island = new_island(ctx)
    for k in range(m):
        f = bm.faces.new((centre, lower[(k + 1) % m], lower[k]))
        f.material_index = EARTH_IDX
        stamp(ctx, f, island, {centre: (0.0, (k + 0.5) / m), lower[(k + 1) % m]: (1.0, (k + 1) / m),
                               lower[k]: (1.0, k / m)}, (1.0, 0.0, 0.0))
    return top


def add_chalk(bm, ctx, sink):
    z0 = TURF_T - CHALK_BITE
    z1 = TURF_T + CHALK_PROUD
    if sink:
        z1 = TURF_T - sink
        z0 = z1 - 0.0025
    hx, hy = CHALK_HALF_L, CHALK_HALF_W
    v = [bm.verts.new((sx * hx, sy * hy, z)) for z in (z0, z1) for sy in (-1, 1) for sx in (-1, 1)]
    quads = [((0, 1, 3, 2), "z"), ((4, 6, 7, 5), "z"), ((0, 4, 5, 1), "y"), ((2, 3, 7, 6), "y"),
             ((0, 2, 6, 4), "x"), ((1, 5, 7, 3), "x")]
    for idx, axis in quads:
        f = bm.faces.new([v[i] for i in idx])
        f.material_index = CHALK_IDX
        proj = {"z": lambda c: (c.x, c.y), "y": lambda c: (c.x, c.z), "x": lambda c: (c.y, c.z)}[axis]
        island_of(ctx, [f], {vv: proj(vv.co) for vv in f.verts})


def in_worn(x, y, scale=1.0):
    return ((x - WORN_C[0]) / (WORN_RX * scale)) ** 2 + ((y - WORN_C[1]) / (WORN_RY * scale)) ** 2 < 1.0


def add_tufts(bm, ctx, stump_xs):
    """Grass thickens toward the slab's edges and thins out where it is walked."""
    rng = random.Random(11)
    placed = 0
    centres = []
    margin = (SLAB_X1 - SLAB_X0) / SLAB_NX  # stay off the rolled outer cells
    while placed < TUFTS:
        x = rng.uniform(SLAB_X0 + margin, SLAB_X1 - margin)
        y = rng.uniform(SLAB_Y0 + margin, SLAB_Y1 - margin)
        edge = min(x - SLAB_X0, SLAB_X1 - x, y - SLAB_Y0, SLAB_Y1 - y) - margin
        keep = max(TUFT_INNER_KEEP, 1.0 - edge / TUFT_EDGE_BAND)
        if rng.random() > keep:
            continue
        if in_worn(x, y, 1.12) or abs(y) < CHALK_HALF_W + 0.025:
            continue
        if any(math.hypot(x - sx, y) < 0.09 for sx in stump_xs):
            continue
        if math.hypot(x - BALL_AT[0], y - BALL_AT[1]) < 0.08:
            continue
        # Crowding at the edges must not stack two tufts' roots in one spot.
        if any(math.hypot(x - tx, y - ty) < TUFT_SPACING for tx, ty in centres):
            continue
        centres.append((x, y))
        placed += 1
        turn = rng.uniform(0.0, 0.5 * math.pi)
        for k in range(BLADES_PER_TUFT):
            bx, by = x + rng.uniform(-0.006, 0.006), y + rng.uniform(-0.006, 0.006)
            h = rng.uniform(*BLADE_H)
            lean = rng.uniform(0.003, 0.012)
            ang = rng.uniform(0.0, 2.0 * math.pi)
            tipc = Vector((bx + lean * math.cos(ang), by + lean * math.sin(ang), TURF_T + h))
            base_z = TURF_T + 0.0004
            # Each blade's square root is turned a third of a quarter-turn from
            # its neighbour's, so no two in a tuft share a facet plane.
            a0 = turn + k * (0.5 * math.pi / BLADES_PER_TUFT) + rng.uniform(-0.12, 0.12)
            ring = [bm.verts.new((bx + BLADE_R * math.cos(a0 + a), by + BLADE_R * math.sin(a0 + a), base_z))
                    for a in (0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi)]
            # Root depth walks a golden-ratio sequence, so two blades turned
            # alike in different tufts still tilt their buried facets apart.
            root = 0.0022 + 0.0016 * ((len(centres) * BLADES_PER_TUFT + k) * 0.6180339887 % 1.0)
            poles = (bm.verts.new((bx, by, TURF_T - root)), bm.verts.new(tipc))
            tube(bm, [ring], poles, BLADE_IDX, ctx, [(0.0, 0.0, 1.0)])


def add_ball(bm, ctx, radius, sink_seam, lift):
    """A leather ball on a tilted axis, resting on the turf, with a raised seam."""
    rot = (Matrix.Rotation(math.radians(BALL_YAW), 4, "Z")
           @ Matrix.Rotation(math.radians(BALL_TILT), 4, "Y"))
    profile = [(0.0, -radius, False)]
    profile += [(radius * math.cos(math.radians(la)), radius * math.sin(math.radians(la)), False)
                for la in BALL_LATS]
    profile.append((0.0, radius, False))
    n0 = len(bm.verts)
    lathe(bm, profile, BALL_SEG, LEATHER_IDX, ctx, rot, (0.0, 0.0, 1.0))
    shape = list(bm.verts)[n0:]
    low = min(v.co.z for v in shape)
    shift = Vector((BALL_AT[0], BALL_AT[1], TURF_T - BALL_BITE + lift - low))
    for v in shape:
        v.co += shift
    centre = shift.copy()
    axis = (rot @ Vector((0.0, 0.0, 1.0))).normalized()
    u = axis.cross(Vector((1.0, 0.0, 0.0))).normalized()
    w = axis.cross(u).normalized()
    major = radius - (sink_seam if sink_seam else 0.0)
    rings = []
    for i in range(SEAM_SEG):
        a = 2.0 * math.pi * i / SEAM_SEG
        radial = u * math.cos(a) + w * math.sin(a)
        c = centre + radial * major
        rings.append([bm.verts.new(c + radial * (SEAM_R * math.cos(2 * math.pi * k / SEAM_TUBE))
                                   + axis * (SEAM_R * math.sin(2 * math.pi * k / SEAM_TUBE)))
                      for k in range(SEAM_TUBE)])
    island = new_island(ctx)
    for i in range(SEAM_SEG):
        a, b = rings[i], rings[(i + 1) % SEAM_SEG]
        tang = tuple((b[0].co - a[0].co).normalized())
        for k in range(SEAM_TUBE):
            j = (k + 1) % SEAM_TUBE
            f = bm.faces.new((a[k], a[j], b[j], b[k]))
            f.material_index = SEAM_IDX
            stamp(ctx, f, island, {a[k]: (i / SEAM_SEG, k / SEAM_TUBE),
                                   a[j]: (i / SEAM_SEG, (k + 1) / SEAM_TUBE),
                                   b[j]: ((i + 1) / SEAM_SEG, (k + 1) / SEAM_TUBE),
                                   b[k]: ((i + 1) / SEAM_SEG, k / SEAM_TUBE)}, tang)


def pack_uvs(bm, ctx, margin=0.06):
    """Big islands on a grid in the upper band; the blades' tiny ones in the lower."""
    uv, isl = ctx["uv"], ctx["isl"]
    islands, order = {}, []
    for face in bm.faces:
        key = face[isl]
        if key not in islands:
            islands[key] = []
            order.append(key)
        islands[key].append(face)
    big = [k for k in order if not all(f.material_index == BLADE_IDX for f in islands[k])]
    small = [k for k in order if k not in set(big)]

    def lay(keys, v0, v1):
        if not keys:
            return
        cols = max(1, math.ceil(math.sqrt(len(keys) * (1.0 / max(v1 - v0, 1e-6)))))
        rows = max(1, math.ceil(len(keys) / cols))
        cw, ch = 1.0 / cols, (v1 - v0) / rows
        pu, pv = margin * cw * 0.5, margin * ch * 0.5
        for idx, key in enumerate(keys):
            faces = islands[key]
            allc = [tuple(loop[uv].uv) for f in faces for loop in f.loops]
            minx, maxx = min(c[0] for c in allc), max(c[0] for c in allc)
            miny, maxy = min(c[1] for c in allc), max(c[1] for c in allc)
            dx, dy = max(maxx - minx, 1e-8), max(maxy - miny, 1e-8)
            ou, ov = (idx % cols) * cw + pu, v0 + (idx // cols) * ch + pv
            for face in faces:
                for loop in face.loops:
                    x, y = loop[uv].uv
                    loop[uv].uv = (ou + (x - minx) / dx * (cw - 2 * pu),
                                   ov + (y - miny) / dy * (ch - 2 * pv))

    lay(big, 0.25, 1.0)
    lay(small, 0.0, 0.25)


def build_wicket_mesh(
    name,
    high=False,
    stray_vert=False,
    float_stump=False,
    thin_stumps=False,
    skew_stump=False,
    lift_bails=False,
    fat_bails=False,
    sink_chalk=False,
    small_ball=False,
    float_ball=False,
    sink_seam=False,
):
    seg = STUMP_SEG_HIGH if high else STUMP_SEG
    bseg = BAIL_SEG_HIGH if high else BAIL_SEG
    zs = TURF_T + STUMP_H - crown_local_max(seg)
    xs = [-STUMP_SPACING, 0.0, STUMP_SPACING + (SKEW_STUMP if skew_stump else 0.0)]
    bm = bmesh.new()
    try:
        ctx = {"uv": bm.loops.layers.uv.new("UVMap"),
               "isl": bm.faces.layers.int.new("UVIsland"),
               "gx": bm.faces.layers.float.new("gx"),
               "gy": bm.faces.layers.float.new("gy"),
               "gz": bm.faces.layers.float.new("gz"), "next": 0}
        for k, cx in enumerate(xs):
            add_stump(bm, ctx, cx, seg, zs, THIN_SCALE if thin_stumps else 1.0,
                      FLOAT_STUMP if (float_stump and k == 0) else 0.0)
        axis_z = zs + GROOVE_FLOOR - BAIL_BITE + SPIGOT_R
        for side in (-1.0, 1.0):
            add_bail(bm, ctx, side, axis_z, bseg, FAT_BARREL_R if fat_bails else BARREL_R,
                     LIFT_BAIL if lift_bails else 0.0)
        add_slab(bm, ctx)
        add_chalk(bm, ctx, SINK_CHALK if sink_chalk else 0.0)
        add_ball(bm, ctx, SMALL_BALL_R if small_ball else BALL_R, SINK_SEAM if sink_seam else 0.0,
                 FLOAT_BALL if float_ball else 0.0)
        add_tufts(bm, ctx, [-STUMP_SPACING, 0.0, STUMP_SPACING])
        if stray_vert:
            bm.verts.new((0.0, 0.2, 0.1))
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


def paint_pieces(me):
    """``GrainDir`` from the per-face grain, ``PlankTone`` per shell."""
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


def wood_material(name, dark, light, rough=(0.72, 0.52), bands=(), band_color=(0.03, 0.012, 0.005),
                  coat=0.0, stretch=0.94, grain_scale=60.0, scuffs=(), scuff_color=(0.13, 0.095, 0.065),
                  ramp=(0.30, 0.72)):
    """Timber whose grain runs along ``GrainDir`` and whose tone varies by piece.

    ``bands`` are (z, half-width) rings of ``band_color`` in object space (a maker's
    turned bands); ``coat`` is a lacquer layer. ``stretch`` is how far the noise is
    drawn out along the grain (1.0 would be an endless streak). ``scuffs`` are
    (x, z, rx, rz) ellipses on the -Y face, where the ball has dulled the
    lacquer and left leather on the wood.
    """
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
    squash.inputs[1].default_value = stretch
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
    noise.inputs["Scale"].default_value = grain_scale
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.62
    nt.links.new(shift.outputs["Vector"], noise.inputs["Vector"])
    cramp = nt.nodes.new("ShaderNodeValToRGB")
    cramp.color_ramp.elements[0].position = ramp[0]
    cramp.color_ramp.elements[0].color = (*dark, 1.0)
    cramp.color_ramp.elements[1].position = ramp[1]
    cramp.color_ramp.elements[1].color = (*light, 1.0)
    nt.links.new(noise.outputs["Fac"], cramp.inputs["Fac"])
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 1.0
    gain.inputs[2].default_value = 0.50
    nt.links.new(tone.outputs["Fac"], gain.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(cramp.outputs["Color"], _sock(mix.inputs, "A_Color"))
    nt.links.new(gain.outputs["Value"], _sock(mix.inputs, "B_Color"))
    colour = _sock(mix.outputs, "Result_Color")
    if bands:
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
        acc = None
        for zc, hw in bands:
            sub = nt.nodes.new("ShaderNodeMath")
            sub.operation = "SUBTRACT"
            sub.inputs[1].default_value = zc
            nt.links.new(sep.outputs["Z"], sub.inputs[0])
            ab = nt.nodes.new("ShaderNodeMath")
            ab.operation = "ABSOLUTE"
            nt.links.new(sub.outputs["Value"], ab.inputs[0])
            lt = nt.nodes.new("ShaderNodeMath")
            lt.operation = "LESS_THAN"
            lt.inputs[1].default_value = hw
            nt.links.new(ab.outputs["Value"], lt.inputs[0])
            if acc is None:
                acc = lt.outputs["Value"]
            else:
                both = nt.nodes.new("ShaderNodeMath")
                both.operation = "ADD"
                both.use_clamp = True
                nt.links.new(acc, both.inputs[0])
                nt.links.new(lt.outputs["Value"], both.inputs[1])
                acc = both.outputs["Value"]
        banded = nt.nodes.new("ShaderNodeMix")
        banded.data_type = "RGBA"
        _sock(banded.inputs, "B_Color").default_value = (*band_color, 1.0)
        nt.links.new(acc, _sock(banded.inputs, "Factor_Float"))
        nt.links.new(colour, _sock(banded.inputs, "A_Color"))
        colour = _sock(banded.outputs, "Result_Color")
    scuff = None
    if scuffs:
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
        # Only the face toward the bowler: 0 behind y = 0, 1 by a third of the radius.
        front = nt.nodes.new("ShaderNodeMapRange")
        front.inputs["From Min"].default_value = 0.0
        front.inputs["From Max"].default_value = -STUMP_R * 0.35
        nt.links.new(sep.outputs["Y"], front.inputs["Value"])
        spot = None
        for sx, sz, rx, rz in scuffs:
            terms = []
            for comp, centre, rad in (("X", sx, rx), ("Z", sz, rz)):
                d = nt.nodes.new("ShaderNodeMath")
                d.operation = "SUBTRACT"
                d.inputs[1].default_value = centre
                nt.links.new(sep.outputs[comp], d.inputs[0])
                q = nt.nodes.new("ShaderNodeMath")
                q.operation = "DIVIDE"
                q.inputs[1].default_value = rad
                nt.links.new(d.outputs["Value"], q.inputs[0])
                sq = nt.nodes.new("ShaderNodeMath")
                sq.operation = "POWER"
                sq.inputs[1].default_value = 2.0
                nt.links.new(q.outputs["Value"], sq.inputs[0])
                terms.append(sq.outputs["Value"])
            r2 = nt.nodes.new("ShaderNodeMath")
            r2.operation = "ADD"
            nt.links.new(terms[0], r2.inputs[0])
            nt.links.new(terms[1], r2.inputs[1])
            fall = nt.nodes.new("ShaderNodeMapRange")
            fall.inputs["From Min"].default_value = 1.0
            fall.inputs["From Max"].default_value = 0.25
            nt.links.new(r2.outputs["Value"], fall.inputs["Value"])
            if spot is None:
                spot = fall.outputs["Result"]
            else:
                mx = nt.nodes.new("ShaderNodeMath")
                mx.operation = "MAXIMUM"
                nt.links.new(spot, mx.inputs[0])
                nt.links.new(fall.outputs["Result"], mx.inputs[1])
                spot = mx.outputs["Value"]
        # Broken up by a noise so it reads as a smear, not a decal.
        grit = nt.nodes.new("ShaderNodeTexNoise")
        grit.inputs["Scale"].default_value = 180.0
        grit.inputs["Detail"].default_value = 3.0
        nt.links.new(coord.outputs["Object"], grit.inputs["Vector"])
        gmap = nt.nodes.new("ShaderNodeMapRange")
        gmap.inputs["From Min"].default_value = 0.25
        gmap.inputs["From Max"].default_value = 0.75
        gmap.inputs["To Min"].default_value = 0.40
        gmap.inputs["To Max"].default_value = 0.95
        nt.links.new(grit.outputs["Fac"], gmap.inputs["Value"])
        m1 = nt.nodes.new("ShaderNodeMath")
        m1.operation = "MULTIPLY"
        nt.links.new(spot, m1.inputs[0])
        nt.links.new(front.outputs["Result"], m1.inputs[1])
        m2 = nt.nodes.new("ShaderNodeMath")
        m2.operation = "MULTIPLY"
        nt.links.new(m1.outputs["Value"], m2.inputs[0])
        nt.links.new(gmap.outputs["Result"], m2.inputs[1])
        scuff = m2.outputs["Value"]
        bruised = nt.nodes.new("ShaderNodeMix")
        bruised.data_type = "RGBA"
        _sock(bruised.inputs, "B_Color").default_value = (*scuff_color, 1.0)
        nt.links.new(scuff, _sock(bruised.inputs, "Factor_Float"))
        nt.links.new(colour, _sock(bruised.inputs, "A_Color"))
        colour = _sock(bruised.outputs, "Result_Color")
    nt.links.new(colour, bsdf.inputs["Base Color"])
    if coat:
        for key, val in (("Coat Weight", coat), ("Coat Roughness", 0.12)):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = val
    rmap = nt.nodes.new("ShaderNodeMapRange")
    rmap.inputs["To Min"].default_value = rough[0]
    rmap.inputs["To Max"].default_value = rough[1]
    nt.links.new(noise.outputs["Fac"], rmap.inputs["Value"])
    rough_out = rmap.outputs["Result"]
    if scuff is not None:
        # The lacquer is knocked off where the ball hits: rougher, and no coat.
        dull = nt.nodes.new("ShaderNodeMix")
        dull.data_type = "FLOAT"
        _sock(dull.inputs, "B_Float").default_value = 0.82
        nt.links.new(scuff, _sock(dull.inputs, "Factor_Float"))
        nt.links.new(rough_out, _sock(dull.inputs, "A_Float"))
        rough_out = _sock(dull.outputs, "Result_Float")
        if coat and "Coat Weight" in bsdf.inputs:
            cw = nt.nodes.new("ShaderNodeMapRange")
            cw.inputs["To Min"].default_value = coat
            cw.inputs["To Max"].default_value = 0.0
            nt.links.new(scuff, cw.inputs["Value"])
            nt.links.new(cw.outputs["Result"], bsdf.inputs["Coat Weight"])
    nt.links.new(rough_out, bsdf.inputs["Roughness"])
    return mat


def noise_material(name, dark, light, scale, rough, tone_mix=False, detail=6.0):
    """Two-colour noise surface (turf, earth, chalk, grass); optional per-shell tone."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    fac = noise.outputs["Fac"]
    if tone_mix:
        tone = nt.nodes.new("ShaderNodeAttribute")
        tone.attribute_name = "PlankTone"
        add = nt.nodes.new("ShaderNodeMath")
        add.operation = "ADD"
        add.inputs[1].default_value = -0.45
        nt.links.new(tone.outputs["Fac"], add.inputs[0])
        both = nt.nodes.new("ShaderNodeMath")
        both.operation = "ADD"
        nt.links.new(noise.outputs["Fac"], both.inputs[0])
        nt.links.new(add.outputs["Value"], both.inputs[1])
        fac = both.outputs["Value"]
    nt.links.new(fac, ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    return mat


def leather_material(name):
    """Red cricket-ball leather: deep, slightly glossy, mottled."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 140.0
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.30, 0.012, 0.010, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.55, 0.030, 0.020, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.38
    return mat


def wicket_materials():
    return (
        # Scuffs: red leather smeared on where the ball has struck, at the
        # height a ball that hits the stumps passes them.
        wood_material("StumpAsh", (0.21, 0.13, 0.060), (0.64, 0.47, 0.25), rough=(0.42, 0.26),
                      bands=((0.625, 0.0030), (0.640, 0.0012)), coat=0.6, stretch=0.985,
                      grain_scale=95.0,
                      scuffs=((0.0, 0.24, 0.017, 0.050), (STUMP_SPACING, 0.16, 0.013, 0.032)),
                      scuff_color=(0.40, 0.085, 0.05), ramp=(0.40, 0.64)),
        wood_material("BailStained", (0.20, 0.085, 0.030), (0.52, 0.25, 0.095), rough=(0.40, 0.26),
                      coat=0.6, stretch=0.97, grain_scale=80.0),
        noise_material("Turf", (0.030, 0.070, 0.012), (0.085, 0.160, 0.030), 70.0, 0.92),
        noise_material("EarthWorn", (0.095, 0.060, 0.034), (0.20, 0.135, 0.075), 45.0, 0.95),
        noise_material("CreaseChalk", (0.62, 0.60, 0.55), (0.88, 0.87, 0.83), 80.0, 0.88),
        noise_material("GrassBlade", (0.05, 0.12, 0.020), (0.17, 0.30, 0.050), 30.0, 0.70,
                       tone_mix=True),
        leather_material("BallLeather"),
        noise_material("SeamThread", (0.55, 0.50, 0.40), (0.82, 0.78, 0.68), 90.0, 0.80),
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
    kinds = {ASH_IDX: "stump", BAIL_IDX: "bail", TURF_IDX: "slab", EARTH_IDX: "slab",
             CHALK_IDX: "chalk", BLADE_IDX: "blade", LEATHER_IDX: "ball", SEAM_IDX: "seam"}
    out = {"stump": [], "bail": [], "slab": [], "chalk": [], "blade": [], "ball": [],
           "seam": [], "other": []}
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        rec = {"g": g, "pts": pts, "lo": lo, "hi": hi, "ext": hi - lo,
               "c": sum(pts, Vector()) / len(pts)}
        out[kinds.get(mats.get(g[0], -1), "other")].append(rec)
    return out


def stump_geometry(rec, zt):
    """Axis (x, y), shaft radius, neck radius and crown top of one stump."""
    shaft = [p for p in rec["pts"] if zt + 0.30 < p.z < zt + 0.50]
    cx = sum(p.x for p in shaft) / len(shaft)
    cy = sum(p.y for p in shaft) / len(shaft)
    rad = max(math.hypot(p.x - cx, p.y - cy) for p in shaft)
    top = rec["hi"].z
    neck = [p for p in rec["pts"] if top - 0.035 < p.z < top - 0.012]
    neck_r = max(math.hypot(p.x - cx, p.y - cy) for p in neck)
    floor = [p.z for p in rec["pts"]
             if abs(p.y - cy) < 0.0005 and abs(p.x - cx) < 0.012 and p.z > top - 0.020]
    return {"cx": cx, "cy": cy, "r": rad, "neck_r": neck_r, "top": top,
            "floor": max(floor) if floor else -99.0}


def wicket_audit(me):
    parts = classify(me)
    out = {k: len(v) for k, v in parts.items()}
    slab = parts["slab"][0] if parts["slab"] else None
    zt = slab["hi"].z if slab else 0.0
    out["zt"] = zt
    stumps = sorted(parts["stump"], key=lambda r: r["c"].x)
    geo = [stump_geometry(r, zt) for r in stumps] if len(stumps) == 3 else []
    out["stump_z"] = max((abs(r["lo"].z) for r in stumps), default=99.0)
    out["height"] = ((min(g["top"] for g in geo) - zt, max(g["top"] for g in geo) - zt)
                     if geo else (-99.0, 99.0))
    out["dia"] = ((2 * min(g["r"] for g in geo), 2 * max(g["r"] for g in geo))
                  if geo else (-99.0, 99.0))
    out["width"] = ((geo[2]["cx"] + geo[2]["r"]) - (geo[0]["cx"] - geo[0]["r"])) if geo else -99.0
    gaps = [(geo[i + 1]["cx"] - geo[i + 1]["r"]) - (geo[i]["cx"] + geo[i]["r"])
            for i in range(2)] if geo else []
    out["gap"] = (min(gaps), max(gaps)) if gaps else (-99.0, 99.0)
    out["mirror"] = max(abs(geo[0]["cx"] + geo[2]["cx"]), abs(geo[1]["cx"]),
                        abs(geo[0]["cy"] - geo[2]["cy"]),
                        abs(geo[0]["top"] - geo[2]["top"])) if geo else 99.0

    bails = sorted(parts["bail"], key=lambda r: r["c"].x)
    seats, margins, clears = [], [], []
    out["pair_gap"] = (bails[1]["lo"].x - bails[0]["hi"].x) if len(bails) == 2 else -99.0
    out["project"] = (max(r["hi"].z for r in bails) - max(r["hi"].z for r in stumps)
                      if bails and stumps else -99.0)
    for b in bails if geo else []:
        za = (b["lo"].z + b["hi"].z) * 0.5
        ya = (b["lo"].y + b["hi"].y) * 0.5
        spig = [p for p in b["pts"] if math.hypot(p.y - ya, p.z - za) < 0.0045]
        barrel = [p for p in b["pts"] if math.hypot(p.y - ya, p.z - za) > 0.0075]
        for xt in (b["lo"].x, b["hi"].x):
            k = min(range(3), key=lambda i: abs(geo[i]["cx"] - xt))
            g = geo[k]
            margins.append(g["neck_r"] - abs(xt - g["cx"]))
            under = [p.z for p in spig if abs(p.x - g["cx"]) < g["neck_r"]]
            seats.append(g["floor"] - min(under) if under else -99.0)
        bl, br = min(p.x for p in barrel), max(p.x for p in barrel)
        zlo, zhi = min(p.z for p in barrel), max(p.z for p in barrel)
        for side, edge_x in ((-1, bl), (1, br)):
            cands = [(i, g) for i, g in enumerate(geo)
                     if (g["cx"] < edge_x if side < 0 else g["cx"] > edge_x)]
            if not cands:
                continue
            i, g = (max(cands, key=lambda t: t[1]["cx"]) if side < 0
                    else min(cands, key=lambda t: t[1]["cx"]))
            band = [p.x for p in stumps[i]["pts"] if zlo <= p.z <= zhi]
            if not band:
                continue
            clears.append(edge_x - max(band) if side < 0 else min(band) - edge_x)
    out["seats"] = (min(seats, default=-99.0), max(seats, default=99.0))
    out["n_seats"] = len(seats)
    out["margin"] = min(margins, default=-99.0)
    out["barrel_clear"] = min(clears, default=-99.0)
    ball = parts["ball"][0] if parts["ball"] else None
    seam = parts["seam"][0] if parts["seam"] else None
    out["ball_d"] = -99.0
    out["ball_seat"] = -99.0
    out["seam_proud"] = -99.0
    if ball:
        bc = sum(ball["pts"], Vector()) / len(ball["pts"])
        mean_r = sum((p - bc).length for p in ball["pts"]) / len(ball["pts"])
        out["ball_d"] = 2.0 * mean_r
        out["ball_seat"] = zt - ball["lo"].z
        if seam:
            out["seam_proud"] = max((p - bc).length for p in seam["pts"]) - mean_r
    ch = parts["chalk"][0] if parts["chalk"] else None
    out["chalk_proud"] = (ch["hi"].z - zt) if ch else -99.0
    out["chalk_bite"] = (zt - ch["lo"].z) if ch else -99.0
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


def ring_points(me, group, seg, vert_step, rings):
    """Every ``vert_step``-th vertex of the chosen rings of a lathed shell, plus its poles.

    Vertices are laid pole, ring after ring, pole in build order. A hull
    only needs the rings where the silhouette turns, not every ring.
    """
    order = sorted(group)
    body = order[1:-1]
    pts = []
    for r in rings:
        pts += [me.vertices[body[r * seg + k]].co.copy() for k in range(0, seg, vert_step)]
    return pts + [me.vertices[order[0]].co.copy(), me.vertices[order[-1]].co.copy()]


def hull_collider(obj, name):
    """Compound collider: a hull per stump, one per bail, one for the turf slab."""
    me = obj.data
    parts = classify(me)
    groups = []
    for r in parts["stump"]:
        groups.append(ring_points(me, r["g"], STUMP_SEG, 4, STUMP_HULL_RINGS))
    for r in parts["bail"]:
        groups.append(ring_points(me, r["g"], BAIL_SEG, 4, BAIL_HULL_RINGS))
    for r in parts["ball"]:
        groups.append(ring_points(me, r["g"], BALL_SEG, 4, BALL_HULL_RINGS))
    for r in parts["slab"]:
        groups.append([p for p in r["pts"]
                       if p.z < 1e-6 or abs(p.z - (TURF_T - SLAB_ROLL)) < 1e-6])
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
    img = bpy.data.images.new("WicketNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = ASH_IDX
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


def apply_shift_bails(me):
    """Falsifier: slide both bails 8 mm outward along the wicket's line."""
    parts = classify(me)
    for rec in parts["bail"]:
        d = -0.008 if rec["c"].x < 0 else 0.008
        for i in rec["g"]:
            me.vertices[i].co.x += d
    me.update()


def check(skip_decimate, lift_z=False, shift_bails=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_wicket_mesh("WicketLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_wicket_mesh("WicketHigh", high=True, **hi_flags)
    if shift_bails:
        apply_shift_bails(low.data)
        apply_shift_bails(high.data)
    mats = wicket_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("wicket mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[ASH_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "WicketLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "WicketLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(low, "WicketCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_wicket_{os.getpid()}.glb")
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
    wa = wicket_audit(low.data)

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
    print(f"measured parts stumps={wa['stump']} bails={wa['bail']} slab={wa['slab']} "
          f"chalk={wa['chalk']} blades={wa['blade']} other={wa['other']} "
          f"stump_z={wa['stump_z']:.5f}")
    print(f"measured stumps height=({wa['height'][0]:.5f},{wa['height'][1]:.5f}) "
          f"dia=({wa['dia'][0]:.5f},{wa['dia'][1]:.5f}) width={wa['width']:.5f} "
          f"gap=({wa['gap'][0]:.5f},{wa['gap'][1]:.5f}) mirror={wa['mirror']:.6f}")
    print(f"measured bails seats={wa['n_seats']}x({wa['seats'][0]:.5f},{wa['seats'][1]:.5f}) "
          f"tip_margin={wa['margin']:.5f} barrel_clear={wa['barrel_clear']:.5f} "
          f"pair_gap={wa['pair_gap']:.5f} project={wa['project']:.5f}")
    print(f"measured chalk proud={wa['chalk_proud']:.5f} bite={wa['chalk_bite']:.5f}")
    print(f"measured ball d={wa['ball_d']:.5f} seat={wa['ball_seat']:.5f} "
          f"seam_proud={wa['seam_proud']:.5f} blades={wa['blade']}")

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
    if wa["stump"] != 3 or wa["stump_z"] > STUMP_Z_MAX:
        return (fail(f"stumps: {wa['stump']} of 3, worst foot z={wa['stump_z']:.5f} > {STUMP_Z_MAX} "
                     "(--float-stump is the designed fail)", 16),) + nothing
    if wa["bail"] != 2 or wa["n_seats"] != 4:
        return (fail(f"{wa['bail']} of 2 bails, {wa['n_seats']} of 4 spigots located", 17),) + nothing
    if wa["margin"] < TIP_MARGIN_MIN:
        return (fail(f"a spigot tip is {wa['margin']:.5f} inside its stump's neck, below "
                     f"{TIP_MARGIN_MIN} (--shift-bails is the designed fail)", 17),) + nothing
    if wa["barrel_clear"] < BARREL_CLEAR_MIN:
        return (fail(f"barrel clears its stump by {wa['barrel_clear']:.5f} < {BARREL_CLEAR_MIN} "
                     "(--shift-bails is the designed fail)", 17),) + nothing
    if wa["pair_gap"] < BAIL_PAIR_GAP_MIN:
        return (fail(f"bails meet: gap {wa['pair_gap']:.5f} < {BAIL_PAIR_GAP_MIN}", 17),) + nothing
    if wa["seats"][0] < SEAT_MIN or wa["seats"][1] > SEAT_MAX:
        return (fail(f"bail spigot seats {wa['seats']} outside [{SEAT_MIN}, {SEAT_MAX}] "
                     "(--lift-bails is the designed fail)", 18),) + nothing
    if not (CHALK_PROUD_MIN <= wa["chalk_proud"] <= CHALK_PROUD_MAX) or wa["chalk_bite"] < CHALK_BITE_MIN:
        return (fail(f"chalk proud {wa['chalk_proud']:.5f} (band [{CHALK_PROUD_MIN}, "
                     f"{CHALK_PROUD_MAX}]), bite {wa['chalk_bite']:.5f} < {CHALK_BITE_MIN} "
                     "(--sink-chalk is the designed fail)", 18),) + nothing
    if not (BALL_SEAT_MIN <= wa["ball_seat"] <= BALL_SEAT_MAX):
        return (fail(f"ball rests {wa['ball_seat']:.5f} into the turf, outside [{BALL_SEAT_MIN}, "
                     f"{BALL_SEAT_MAX}] (--float-ball is the designed fail)", 18),) + nothing
    if not (SEAM_PROUD_MIN <= wa["seam_proud"] <= SEAM_PROUD_MAX):
        return (fail(f"seam stands {wa['seam_proud']:.5f} proud of the ball, outside "
                     f"[{SEAM_PROUD_MIN}, {SEAM_PROUD_MAX}] (--sink-seam is the designed fail)", 18),) + nothing
    if wa["dia"][0] < STUMP_D_MIN or wa["dia"][1] > STUMP_D_MAX:
        return (fail(f"stump diameter {wa['dia']} outside Law 8's [{STUMP_D_MIN}, {STUMP_D_MAX}] "
                     "(--thin-stumps is the designed fail)", 19),) + nothing
    if (abs(wa["height"][0] - STUMP_H) > HEIGHT_TOL or abs(wa["height"][1] - STUMP_H) > HEIGHT_TOL):
        return (fail(f"stump height {wa['height']} off {STUMP_H} by more than {HEIGHT_TOL}", 19),) + nothing
    if abs(wa["width"] - WIDTH) > WIDTH_TOL or wa["gap"][1] >= BALL_D_MIN or wa["gap"][0] < GAP_MIN:
        return (fail(f"width {wa['width']:.5f} (Law 8: {WIDTH} +- {WIDTH_TOL}), gaps {wa['gap']} "
                     f"(a ball of {BALL_D_MIN} must not pass; stumps must not touch)", 19),) + nothing
    if not (BALL_D_MIN_OK <= wa["ball_d"] <= BALL_D_MAX_OK):
        return (fail(f"ball diameter {wa['ball_d']:.5f} outside Law 5's [{BALL_D_MIN_OK}, "
                     f"{BALL_D_MAX_OK}] (--small-ball is the designed fail)", 19),) + nothing
    if wa["mirror"] > MIRROR_EPS:
        return (fail(f"stumps not mirrored: {wa['mirror']:.6f} > {MIRROR_EPS} "
                     "(--skew-stump is the designed fail)", 19),) + nothing
    if not (PROJECT_MIN <= wa["project"] <= PROJECT_MAX):
        return (fail(f"bails stand {wa['project']:.5f} above the stumps, outside [{PROJECT_MIN}, "
                     f"{PROJECT_MAX}] (Law 8: 12.7 mm; --fat-bails is the designed fail)", 19),) + nothing
    return 0, low, high, mats, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats[ASH_IDX], tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Nearly square to the wicket, so the bails lie across the frame as bars
    # rather than foreshortening into the stump tops.
    low.rotation_euler.z = math.radians(-12.0)

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
    cam_data.lens = 65.0
    cam = bpy.data.objects.new("Cam", cam_data)
    # 28 degrees off square, a hair above the crowns so the grooves show.
    cam.location = (0.83, -2.88, 0.80)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.33)
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

    fcode = gallery_framing.check_framing(scene, cam, hero=[low], elements=[low], stage=[floor, wall])
    if fcode:
        return fcode
    if gallery_asset_quality.check_asset_quality(scene, cam, [low], stage=[floor, wall]):
        return gallery_asset_quality.EXIT_ASSET_QUALITY
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
    p.add_argument("--float-stump", action="store_true")
    p.add_argument("--shift-bails", action="store_true")
    p.add_argument("--lift-bails", action="store_true")
    p.add_argument("--sink-chalk", action="store_true")
    p.add_argument("--thin-stumps", action="store_true")
    p.add_argument("--skew-stump", action="store_true")
    p.add_argument("--fat-bails", action="store_true")
    p.add_argument("--small-ball", action="store_true")
    p.add_argument("--float-ball", action="store_true")
    p.add_argument("--sink-seam", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        shift_bails=args.shift_bails,
        stray_vert=args.stray_vert,
        float_stump=args.float_stump,
        thin_stumps=args.thin_stumps,
        skew_stump=args.skew_stump,
        lift_bails=args.lift_bails,
        fat_bails=args.fat_bails,
        sink_chalk=args.sink_chalk,
        small_ball=args.small_ball,
        float_ball=args.float_ball,
        sink_seam=args.sink_seam,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("cricket wicket OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
