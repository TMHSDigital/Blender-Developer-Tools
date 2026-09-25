"""Game-ready brazier — a showcase piece, not an example.

Asserts budget conformance of a procedural iron brazier: a spun bowl
with a rolled rim on three forged legs, a bed of ash in the bowl and a
heap of broken, glowing coals on it. Carried through UVs, three
materials (iron, coal, ash), a high-to-low normal bake, an LOD chain, a
compound convex collider, and a Unity glTF export.

The budget that matters here is the one a brazier can fail invisibly: it
holds burning coals, so it must not tip when it is knocked. The piece
recomputes the centre of mass from the closed shells, weighted by the
density of each material, and the support polygon from the feet that
touch the floor, and asserts the angle it can lean before it tips.
Legs tucked in under the bowl still ground the piece and still fit its
bounding box; only the tip angle knows the difference.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-foot`` the named feet,
``--short-legs`` the leg-to-bowl bite, ``--float-coals`` the coal seat,
``--overfill`` the freeboard, ``--tuck-legs`` the tip angle,
``--pile-coals`` coal interpenetration, ``--uniform-coals`` coal size
variation.

No randomness: every coal's size, shape and cleave is a closed-form term
of its index. DECIMATE COLLAPSE triangle counts are not byte-identical
across Blender versions — the LOD gate is a ratio band.

    blender --background --python brazier.py --
    blender --background --python brazier.py -- --tuck-legs
    blender --background --python brazier.py -- --output brazier.png
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
from mathutils.kdtree import KDTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

# The bowl: a half-ellipsoid spun from sheet iron, rim at RIM_Z, with a
# rolled bead at the lip. The inner wall is the outer wall offset along
# its own normal by WALL.
RIM_R = 0.340
RIM_Z = 0.600
DEPTH = 0.200
WALL = 0.008
BEAD_R = 0.010
BOWL_SEG = 32
BOWL_STEPS = 14

# Three forged legs: a chamfered-square bar swept in one piece from inside
# the bowl wall, out and down to a flat foot, ending in a small curl.
N_LEGS = 3
LEG_A = 0.011
LEG_CHAMFER = 0.30
ATTACH_PHI = math.radians(40.0)
LEG_BITE = 0.003
LEG_CONE = 0.25
FOOT_R = 0.290
TUCK_FOOT_R = 0.150
SHORT_LEG_GAP = 0.012
FLOAT_FOOT = 0.012

# Ash: a shallow dome whose rim bites into the bowl's inner wall.
ASH_Z = 0.490
ASH_DOME = 0.035
ASH_BITE = 0.003
ASH_SEG = 32
OVERFILL = 0.045

# Coals: broken lumps (a cleaved icosphere, flat-shaded) sunk into the
# ash. Sizes vary by a closed-form draw on the index.
COAL_BASE = 0.026
COAL_VAR = 0.40
COAL_SINK = 0.30
COAL_GAP = 0.002
COAL_TRIES = 90
# A heap is a fixed number of coals: packing as many as fit made the
# count, and so the triangle budget, move with every falsifier that
# changes the space or the spacing.
N_COALS = 36
PILE_SCALE = 0.60
FLOAT_COALS = 0.030

DENSITY = {0: 7850.0, 1: 500.0, 2: 600.0}

BBOX_TOL = 0.020
OUTER_SIZE = (0.696, 0.696, 0.612)

BASE_TRIS_MIN = 6600
BASE_TRIS_MAX = 8200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 3
IRON_FACES_MIN = 1400
COAL_FACES_MIN = 2800
ASH_FACES_MIN = 380
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 400
BAKE_RES = 512
CAGE_EXTRUSION = 0.01
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
FOOT_Z_MAX = 1e-3
LEG_BITE_MIN = 0.0015
COAL_SEAT_MIN = 0.004
COAL_SEAT_MAX = 0.030
FREEBOARD_MIN = 0.030
TIP_MIN = math.radians(13.0)
COAL_SPREAD_MIN = 1.35

IRON_IDX = 0
COAL_IDX = 1
ASH_IDX = 2


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


# --- profiles ---------------------------------------------------------------


def outer_point(phi):
    """Outer bowl wall at polar angle phi (0 at the bottom pole, pi/2 at the rim)."""
    return Vector((RIM_R * math.sin(phi), RIM_Z - DEPTH * math.cos(phi)))


def outer_normal(phi):
    p = outer_point(phi)
    n = Vector((p.x / RIM_R ** 2, (p.y - RIM_Z) / DEPTH ** 2))
    return n.normalized()


def bowl_profile():
    """(r, z) loop from the outer pole, over the rolled bead, to the inner pole.

    The inner wall is the outer one offset along its own normal, so the
    wall is WALL thick everywhere; a sideways offset thins it to nothing
    where the bowl runs flat.
    """
    phi_top = math.acos((BEAD_R + 0.002) / DEPTH)
    phis = [phi_top * k / BOWL_STEPS for k in range(BOWL_STEPS + 1)]
    outer = [outer_point(p) for p in phis]
    inner = [outer_point(p) - outer_normal(p) * WALL for p in phis]
    centre = Vector((RIM_R - 0.002, RIM_Z + 0.002))
    bead = []
    lo = math.atan2(outer[-1].y - centre.y, outer[-1].x - centre.x)
    hi = math.atan2(inner[-1].y - centre.y, inner[-1].x - centre.x) + 2.0 * math.pi
    for k in range(1, 8):
        a = lo + (hi - lo) * k / 8
        bead.append(centre + Vector((math.cos(a), math.sin(a))) * BEAD_R)
    loop = [Vector((0.0, outer[0].y))] + outer[1:] + bead + list(reversed(inner[1:]))
    loop.append(Vector((0.0, inner[0].y)))
    return loop, inner


def inner_radius(inner, z):
    """Inner wall radius at height z, linear between the offset samples."""
    pts = sorted(inner, key=lambda p: p.y)
    if z <= pts[0].y:
        return 0.0
    for a, b in zip(pts, pts[1:]):
        if a.y <= z <= b.y:
            f = (z - a.y) / (b.y - a.y) if b.y > a.y else 0.0
            return a.x + (b.x - a.x) * f
    return pts[-1].x


# --- construction -----------------------------------------------------------


def stamp(ctx, face, island, uvmap):
    """Tag ``face`` with its UV island and write its provisional strip UVs.

    Kept in bmesh layers, not a dict keyed by BMFace: an operator that
    frees and reallocates faces (create_icosphere with subdivisions=2)
    hands a later face a dead face's identity, and the dict then answers
    for the wrong face.
    """
    face[ctx["isl"]] = island
    for loop in face.loops:
        loop[ctx["uv"]].uv = uvmap[loop.vert]


def new_island(ctx):
    ctx["next"] += 1
    return ctx["next"]


def lathe(bm, profile, n, mat_idx, ctx, smooth=True):
    """Revolve an (r, z) profile about Z; r == 0 at the ends makes a pole.

    One strip island (profile length by angle); pole fans put their pole
    half a column over so no two faces overlap in UV.
    """
    island = new_island(ctx)
    s = [0.0]
    for a, b in zip(profile, profile[1:]):
        s.append(s[-1] + (b - a).length)
    rings = []
    for p in profile:
        if p.x <= 0.0:
            rings.append(bm.verts.new((0.0, 0.0, p.y)))
            continue
        rings.append([bm.verts.new((p.x * math.cos(2 * math.pi * k / n),
                                    p.x * math.sin(2 * math.pi * k / n), p.y))
                      for k in range(n)])
    faces = []
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            if isinstance(a, list) and isinstance(b, list):
                vs = (a[i], a[j], b[j], b[i])
                uv = {a[i]: (s[k], i / n), a[j]: (s[k], (i + 1) / n),
                      b[j]: (s[k + 1], (i + 1) / n), b[i]: (s[k + 1], i / n)}
            elif isinstance(b, list):
                vs = (a, b[j], b[i])
                uv = {a: (s[k], (i + 0.5) / n), b[j]: (s[k + 1], (i + 1) / n),
                      b[i]: (s[k + 1], i / n)}
            else:
                vs = (a[i], a[j], b)
                uv = {a[i]: (s[k], i / n), a[j]: (s[k], (i + 1) / n),
                      b: (s[k + 1], (i + 0.5) / n)}
            f = bm.faces.new(vs)
            f.material_index = mat_idx
            f.smooth = smooth
            stamp(ctx, f, island, uv)
            faces.append(f)
    return faces


def leg_section():
    """A chamfered square bar, flat side down: (side, up) offsets."""
    a, c = LEG_A, LEG_A * LEG_CHAMFER
    pts = [(a, -(a - c)), (a, a - c), (a - c, a), (-(a - c), a),
           (-a, a - c), (-a, -(a - c)), (-(a - c), -a), (a - c, -a)]
    return pts


def bezier(p0, p1, p2, p3, n):
    out = []
    for k in range(n + 1):
        t = k / n
        u = 1.0 - t
        out.append(p0 * u ** 3 + p1 * 3 * u * u * t + p2 * 3 * u * t * t + p3 * t ** 3)
    return out


def leg_path(foot_r, short=False, float_foot=False):
    """(rho, z) centreline, from inside the bowl wall to the curled foot.

    One sweep: the bar leaves the bowl along the wall's normal, bends down
    and out, runs level on the floor with a flat face down, and curls up.
    """
    base = outer_point(ATTACH_PHI)
    n = outer_normal(ATTACH_PHI)
    start = base + n * (SHORT_LEG_GAP if short else -LEG_BITE)
    p1 = base + n * 0.030
    lift = FLOAT_FOOT if float_foot else 0.0
    foot0 = Vector((foot_r - 0.015, LEG_A + lift))
    foot1 = Vector((foot_r + 0.015, LEG_A + lift))
    pts = [start]
    # The handle into the foot is level, so the bar arrives flat on the floor.
    pts += bezier(p1, p1 + n * 0.10, foot0 - Vector((0.10, 0.0)), foot0, 12)
    pts += [foot0 + (foot1 - foot0) * (k / 3) for k in range(1, 4)]
    curl = bezier(foot1, foot1 + Vector((0.012, 0.0)), foot1 + Vector((0.024, 0.006)),
                  foot1 + Vector((0.026, 0.020)), 4)
    pts += curl[1:]
    return pts


def sweep_bar(bm, pts, section, side, mat_idx, ctx, cone=LEG_CONE):
    """Sweep ``section`` along ``pts`` (3D), frame fixed to the path's plane.

    Ends close in a blunt cone so there is no n-gon cap. Returns vertices.
    """
    island = new_island(ctx)
    m = len(pts)
    tans = []
    for i in range(m):
        d = pts[min(i + 1, m - 1)] - pts[max(i - 1, 0)]
        tans.append(d.normalized())
    n = len(section)
    rings = []
    for p, t in zip(pts, tans):
        s = side - t * side.dot(t)
        s.normalize()
        up = t.cross(s)
        rings.append([bm.verts.new(p + s * x + up * y) for x, y in section])
    arc = [0.0]
    for i in range(1, m):
        arc.append(arc[-1] + (pts[i] - pts[i - 1]).length)
    for k in range(m - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new((a[i], a[j], b[j], b[i]))
            f.material_index = mat_idx
            f.smooth = False
            stamp(ctx, f, island, {a[i]: (arc[k], i / n), a[j]: (arc[k], (i + 1) / n),
                                   b[j]: (arc[k + 1], (i + 1) / n), b[i]: (arc[k + 1], i / n)})
    reach = cone * LEG_A
    for ring, p, t, sign, s_end in ((rings[0], pts[0], tans[0], -1.0, arc[0]),
                                    (rings[-1], pts[-1], tans[-1], 1.0, arc[-1])):
        pole = bm.verts.new(p + t * (sign * reach))
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new((pole, ring[i], ring[j]))
            f.material_index = mat_idx
            f.smooth = False
            stamp(ctx, f, island, {pole: (s_end + sign * reach, (i + 0.5) / n),
                                   ring[i]: (s_end, i / n), ring[j]: (s_end, (i + 1) / n)})
    return [v for r in rings for v in r]


def coal_size(i, uniform=False):
    """Closed-form size draw per coal: golden-ratio spacing, no RNG."""
    if uniform:
        # One draw for every coal, small enough that the full heap still
        # fits: the coals do not set the envelope, so nothing else moves.
        return COAL_BASE * (1.0 - COAL_VAR * 0.5)
    f = (i * 0.6180339887 + 0.37) % 1.0
    return COAL_BASE * (1.0 + COAL_VAR * (f - 0.5) * 2.0)


def coal_axes(i, size):
    """Ellipsoid half-axes: a charcoal lump is longer than it is tall."""
    e = (i * 0.4142135 + 0.2) % 1.0
    return (size * (1.15 + 0.25 * e), size * (0.95 - 0.15 * e), size * 0.72)


_ICO = {}


def ico_unit():
    """Unit icosphere (subdivisions 2): vertex positions and face index lists."""
    if not _ICO:
        tmp = bmesh.new()
        try:
            bmesh.ops.create_icosphere(tmp, subdivisions=2, radius=1.0)
            tmp.verts.index_update()
            _ICO["verts"] = [v.co.copy() for v in tmp.verts]
            _ICO["faces"] = [[v.index for v in f.verts] for f in tmp.faces]
        finally:
            tmp.free()
    return _ICO["verts"], _ICO["faces"]


def coal_shape(axes, i):
    """A broken lump, centred on the origin: a scaled icosphere cleaved by three planes.

    Every vertex beyond a plane is projected onto it, so the lump reads as
    split charcoal rather than a pebble.
    """
    unit, _faces = ico_unit()
    yaw = i * 2.39996
    c, s = math.cos(yaw), math.sin(yaw)
    pts = []
    for u in unit:
        x, y, z = u.x * axes[0], u.y * axes[1], u.z * axes[2]
        pts.append(Vector((c * x - s * y, s * x + c * y, z)))
    # Tumbled, not set upright: each lump leans by a closed-form few
    # degrees. Stood level, two similar lumps once carried a pair of
    # near-parallel buried faces in one plane (a coplanar pair).
    tilt = Matrix.Rotation(0.18 * (((i * 0.6180340) % 1.0) - 0.5), 3, "X") @         Matrix.Rotation(0.18 * (((i * 0.4142136) % 1.0) - 0.5), 3, "Y")
    pts = [tilt @ p for p in pts]
    for k in range(3):
        a = yaw + k * 2.1 + 0.4
        el = 0.35 + 0.25 * ((i + k) % 3)
        nrm = Vector((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el)))
        d = 0.70 * min(axes) + 0.18 * max(axes) * (((i * 7 + k * 3) % 5) / 5.0)
        for p in pts:
            h = p.dot(nrm)
            if h > d:
                p -= nrm * (h - d)
    return pts


def add_coal(bm, centre, shape, mat_idx):
    """Emit a lump built by ``coal_shape`` at ``centre``. Flat-shaded."""
    _unit, faces = ico_unit()
    vs = [bm.verts.new(p + centre) for p in shape]
    for idx in faces:
        f = bm.faces.new([vs[k] for k in idx])
        f.material_index = mat_idx
        f.smooth = False
    return vs


def coal_layout(inner, ash_z, r_edge, pile=False, uniform=False):
    """Greedy sunflower packing: each coal at the smallest radius that clears the rest.

    Coal ``i`` tries the golden angle times ``i`` and walks outward until
    its centre is at least the sum of its own and each placed coal's plan
    radius bound (plus COAL_GAP) from every one of them, and its bound
    stays inside the inner wall at the height of its base. Bounds come
    from the same constants that size each coal, so a bigger coal takes
    more room. ``pile`` shrinks the spacing so neighbours interpenetrate.
    """
    shapes = {}

    def shape(i):
        if i not in shapes:
            shapes[i] = coal_shape(coal_axes(i, coal_size(i, uniform)), i)
        return shapes[i]

    def bound(i):
        # The lump's own plan radius after cleaving, read off its vertices.
        return max(math.hypot(p.x, p.y) for p in shape(i))

    def ash_at(rho):
        return ash_z + ASH_DOME * (1.0 - min(1.0, (rho / r_edge) ** 2))

    scale = PILE_SCALE if pile else 1.0
    placed = []
    for i in range(COAL_TRIES):
        if len(placed) == N_COALS:
            break
        b = bound(i)
        theta = i * 2.39996323
        rho = 0.0
        while True:
            x, y = rho * math.cos(theta), rho * math.sin(theta)
            limit = inner_radius(inner, ash_at(rho) - 0.02) - COAL_GAP
            if rho + b > limit:
                break
            if all(math.hypot(x - px, y - py) >= (b + pb) * scale + COAL_GAP
                   for px, py, pb, _i in placed):
                placed.append((x, y, b, i))
                break
            rho += 0.002
    coals = []
    for x, y, _b, i in placed:
        size = coal_size(i, uniform)
        axes = coal_axes(i, size)
        # Each lump settles a little differently. Sunk to one fraction, two
        # buried undersides once landed in one plane (a coplanar pair).
        sink = COAL_SINK + 0.06 * (((i * 0.3819660) % 1.0) - 0.5)
        z = ash_at(math.hypot(x, y)) + axes[2] * (1.0 - 2.0 * sink)
        coals.append((Vector((x, y, z)), shape(i), i))
    return coals


def pack_uvs(bm, ctx, margin=0.06):
    """One grid cell per UV island: strip islands by their layer tag, else a face each."""
    uv, isl = ctx["uv"], ctx["isl"]
    bm.faces.index_update()
    islands, order = {}, []
    for face in bm.faces:
        key = ("s", face[isl]) if face[isl] else ("f", face.index)
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
        coords = {}
        for face in faces:
            if face[isl]:
                coords[face.index] = [tuple(loop[uv].uv) for loop in face.loops]
                continue
            nrm = face.normal
            ax, ay, az = abs(nrm.x), abs(nrm.y), abs(nrm.z)
            pts = []
            for loop in face.loops:
                co = loop.vert.co
                if az >= ax and az >= ay:
                    pts.append((co.x, co.y))
                elif ax >= ay:
                    pts.append((co.y, co.z))
                else:
                    pts.append((co.x, co.z))
            coords[face.index] = pts
        allc = [c for cs in coords.values() for c in cs]
        minx, maxx = min(c[0] for c in allc), max(c[0] for c in allc)
        miny, maxy = min(c[1] for c in allc), max(c[1] for c in allc)
        dx, dy = max(maxx - minx, 1e-8), max(maxy - miny, 1e-8)
        ou, ov = (idx % cols) * cw + pu, (idx // cols) * ch + pv
        for face in faces:
            for loop, (x, y) in zip(face.loops, coords[face.index]):
                loop[uv].uv = (ou + (x - minx) / dx * (cw - 2 * pu),
                               ov + (y - miny) / dy * (ch - 2 * pv))


def build_brazier_mesh(
    name,
    stray_vert=False,
    float_foot=False,
    short_legs=False,
    float_coals=False,
    overfill=False,
    tuck_legs=False,
    pile_coals=False,
    uniform_coals=False,
):
    profile, inner = bowl_profile()
    ash_z = ASH_Z + (OVERFILL if overfill else 0.0)
    r_edge = inner_radius(inner, ash_z) + ASH_BITE
    bm = bmesh.new()
    try:
        ctx = {"uv": bm.loops.layers.uv.new("UVMap"),
               "isl": bm.faces.layers.int.new("UVIsland"), "next": 0}
        lathe(bm, profile, BOWL_SEG, IRON_IDX, ctx)
        foot_r = TUCK_FOOT_R if tuck_legs else FOOT_R
        for k in range(N_LEGS):
            az = 2.0 * math.pi * k / N_LEGS + math.pi / 2.0
            radial = Vector((math.cos(az), math.sin(az), 0.0))
            side = Vector((-math.sin(az), math.cos(az), 0.0))
            path = leg_path(foot_r, short=short_legs, float_foot=(float_foot and k == 0))
            pts = [radial * p.x + Vector((0.0, 0.0, p.y)) for p in path]
            sweep_bar(bm, pts, leg_section(), side, IRON_IDX, ctx)
        # Ash: the dome, then down the inner wall (biting it) to the bottom.
        ash = [Vector((0.0, inner[0].y - ASH_BITE))]
        lows = sorted(inner, key=lambda p: p.y)
        for p in lows:
            if inner[0].y + 0.004 < p.y < ash_z - 0.004:
                ash.append(Vector((inner_radius(inner, p.y) + ASH_BITE, p.y)))
        ash.append(Vector((r_edge, ash_z)))
        for k in range(1, 6):
            rho = r_edge * (1.0 - k / 6.0)
            ash.append(Vector((rho, ash_z + ASH_DOME * (1.0 - (rho / r_edge) ** 2))))
        ash.append(Vector((0.0, ash_z + ASH_DOME)))
        lathe(bm, ash, ASH_SEG, ASH_IDX, ctx)
        for centre, shape, _i in coal_layout(inner, ash_z, r_edge, pile=pile_coals,
                                             uniform=uniform_coals):
            if float_coals:
                centre = centre + Vector((0.0, 0.0, FLOAT_COALS))
            add_coal(bm, centre, shape, COAL_IDX)
        if stray_vert:
            bm.verts.new((0.0, 0.0, 0.25))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        pack_uvs(bm, ctx)
        bm.faces.layers.int.remove(ctx["isl"])
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


# --- surface ----------------------------------------------------------------


def _sock(sockets, identifier):
    return next(sk for sk in sockets if sk.identifier == identifier)


def iron_material(name):
    """Forged iron: near-black, rough, rusted in patches. Not chrome."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 14.0
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


def coal_material(name):
    """Charcoal: black and matte, glowing orange in the cracks."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.022, 0.020, 0.019, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.9
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = 60.0
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    crack = nt.nodes.new("ShaderNodeMapRange")
    crack.inputs["From Min"].default_value = 0.0
    crack.inputs["From Max"].default_value = 0.04
    crack.inputs["To Min"].default_value = 1.0
    crack.inputs["To Max"].default_value = 0.0
    nt.links.new(vor.outputs["Distance"], crack.inputs["Value"])
    # Hotter lower down: the heap burns from the ash up.
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
    heat = nt.nodes.new("ShaderNodeMapRange")
    heat.inputs["From Min"].default_value = 0.60
    heat.inputs["From Max"].default_value = 0.47
    heat.inputs["To Min"].default_value = 0.35
    heat.inputs["To Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], heat.inputs["Value"])
    # Not every crack burns: a noise mask breaks the network up, so a lump
    # glows in patches instead of wearing an even honeycomb.
    mask_n = nt.nodes.new("ShaderNodeTexNoise")
    mask_n.inputs["Scale"].default_value = 22.0
    mask_n.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], mask_n.inputs["Vector"])
    mask = nt.nodes.new("ShaderNodeMapRange")
    mask.inputs["From Min"].default_value = 0.42
    mask.inputs["From Max"].default_value = 0.62
    nt.links.new(mask_n.outputs["Fac"], mask.inputs["Value"])
    burn = nt.nodes.new("ShaderNodeMath")
    burn.operation = "MULTIPLY"
    nt.links.new(crack.outputs["Result"], burn.inputs[0])
    nt.links.new(mask.outputs["Result"], burn.inputs[1])
    glow = nt.nodes.new("ShaderNodeMath")
    glow.operation = "MULTIPLY"
    nt.links.new(burn.outputs["Value"], glow.inputs[0])
    nt.links.new(heat.outputs["Result"], glow.inputs[1])
    strength = nt.nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    strength.inputs[1].default_value = 7.0
    nt.links.new(glow.outputs["Value"], strength.inputs[0])
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.32, 0.06, 1.0)
    nt.links.new(strength.outputs["Value"], bsdf.inputs["Emission Strength"])
    return mat


def ash_material(name):
    """Ash: pale, matte, with darker cinders mottled through it."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.06, 0.056, 0.053, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.26, 0.245, 0.225, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.97
    return mat


def brazier_materials():
    return iron_material("BrazierIron"), coal_material("BrazierCoal"), ash_material("BrazierAsh")


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


def shell_tree(me, group):
    member = set(group)
    remap = {v: k for k, v in enumerate(group)}
    polys = [[remap[i] for i in p.vertices] for p in me.polygons if p.vertices[0] in member]
    return BVHTree.FromPolygons([me.vertices[i].co.copy() for i in group], polys)


def inside_depth(tree, pts):
    """Deepest point of ``pts`` inside ``tree``'s surface; negative is a gap."""
    best = -99.0
    for p in pts:
        loc, nrm, _i, dist = tree.find_nearest(p)
        if loc is None:
            continue
        d = dist if (p - loc).dot(nrm) < 0.0 else -dist
        best = max(best, d)
    return best


def classify(me):
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    out = {"bowl": [], "leg": [], "ash": [], "coal": [], "other": []}
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        rec = {"g": g, "pts": pts, "c": sum(pts, Vector()) / len(pts)}
        m = mats.get(g[0], -1)
        if m == IRON_IDX:
            out["bowl" if len(g) > 400 else "leg"].append(rec)
        elif m == ASH_IDX:
            out["ash"].append(rec)
        elif m == COAL_IDX:
            out["coal"].append(rec)
        else:
            out["other"].append(rec)
    return out


def mass_centre(me):
    """Centre of mass of the closed shells, each triangle weighted by density.

    Signed tetrahedra from the origin: every shell is closed and wound
    outward, so interior volumes cancel and each material contributes
    its volume times its density.
    """
    me.calc_loop_triangles()
    m_tot = 0.0
    acc = Vector((0.0, 0.0, 0.0))
    for tri in me.loop_triangles:
        a, b, c = (me.vertices[i].co for i in tri.vertices)
        v = a.dot(b.cross(c)) / 6.0
        rho = DENSITY.get(me.polygons[tri.polygon_index].material_index, 0.0)
        m_tot += v * rho
        acc += (a + b + c) * (v * rho / 4.0)
    return acc / m_tot if m_tot else Vector(), m_tot


def convex_hull_2d(pts):
    pts = sorted(set((round(p[0], 9), round(p[1], 9)) for p in pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def brazier_audit(me):
    parts = classify(me)
    bowl = parts["bowl"][0] if parts["bowl"] else None
    ash = parts["ash"][0] if parts["ash"] else None
    out = {k: len(v) for k, v in parts.items()}
    out["foot_worst"] = max((min(p.z for p in r["pts"]) for r in parts["leg"]), default=99.0)

    # Legs bite the bowl wall: deepest leg vertex inside the bowl shell.
    bowl_tree = shell_tree(me, bowl["g"]) if bowl else None
    bites = [inside_depth(bowl_tree, r["pts"]) for r in parts["leg"]] if bowl_tree else []
    out["leg_bite"] = min(bites, default=-99.0)

    # Coals sit in the ash: deepest coal vertex inside the ash shell.
    ash_tree = shell_tree(me, ash["g"]) if ash else None
    seats = [inside_depth(ash_tree, r["pts"]) for r in parts["coal"]] if ash_tree else []
    out["seat_min"] = min(seats, default=-99.0)
    out["seat_max"] = max(seats, default=99.0)

    # Freeboard: the rim above the highest coal or ash.
    rim = max(p.z for p in bowl["pts"]) if bowl else 0.0
    top = max((p.z for r in parts["coal"] + parts["ash"] for p in r["pts"]), default=99.0)
    out["freeboard"] = rim - top

    # Coals do not interpenetrate one another.
    trees = [shell_tree(me, r["g"]) for r in parts["coal"]]
    hits = 0
    for i in range(len(trees)):
        for j in range(i + 1, len(trees)):
            if trees[i].overlap(trees[j]):
                hits += 1
    out["coal_hits"] = hits

    # Coal sizes vary: largest footprint over smallest.
    foot = []
    for r in parts["coal"]:
        xs = [p.x for p in r["pts"]]
        ys = [p.y for p in r["pts"]]
        foot.append((max(xs) - min(xs)) * (max(ys) - min(ys)))
    out["coal_spread"] = (max(foot) / min(foot)) if foot else 0.0

    # Tip angle: distance from the mass centre to the nearest edge of the
    # support polygon, over its height.
    com, mass = mass_centre(me)
    contacts = [(p.x, p.y) for r in parts["leg"] for p in r["pts"] if p.z <= 1e-6]
    hull = convex_hull_2d(contacts)
    d_edge = -99.0
    if len(hull) >= 3:
        d_edge = 99.0
        for a, b in zip(hull, hull[1:] + hull[:1]):
            ex, ey = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ex, ey)
            d = (ex * (com.y - a[1]) - ey * (com.x - a[0])) / ln
            d_edge = min(d_edge, d)
    out["com"] = com
    out["mass"] = mass
    out["d_edge"] = d_edge
    out["tip"] = math.atan2(d_edge, com.z) if com.z > 0 else -1.0
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


def hull_collider(obj, name):
    """Compound collider: one convex hull for the bowl and its contents, one per leg.

    A single hull over the whole brazier fills the space between the legs,
    which a character should be able to kick a foot through.
    """
    me = obj.data
    parts = classify(me)
    # Sampled in build order: the bowl is rings of BOWL_SEG, a leg rings
    # of eight. The ash and coals sit below the rim, inside the bowl's hull.
    bowl = sorted(parts["bowl"][0]["g"])
    groups = [[me.vertices[v].co.copy() for k, v in enumerate(bowl)
               if (k // BOWL_SEG) % 2 == 0 and (k % BOWL_SEG) % 4 == 0]
              + [me.vertices[bowl[-1]].co.copy()]]
    for r in parts["leg"]:
        leg = sorted(r["g"])
        groups.append([me.vertices[v].co.copy() for k, v in enumerate(leg)
                       if (k // 8) % 4 == 0 and k % 2 == 0] + [me.vertices[leg[-1]].co.copy()])
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for pts in groups:
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
    img = bpy.data.images.new("BrazierNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = IRON_IDX
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
    low = build_brazier_mesh("BrazierLow", **flags)
    hi_flags = {k: v for k, v in flags.items() if k != "stray_vert"}
    high = build_brazier_mesh("BrazierHigh", **hi_flags)
    mats = brazier_materials()
    assign_slots(low, mats)
    assign_slots(high, mats)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or not low.data.uv_layers:
        return (fail("brazier mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    slots = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(slots), len({id(s) for s in slots})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, mats[IRON_IDX], BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BrazierLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BrazierLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(high, "BrazierCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_brazier_{os.getpid()}.glb")
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
    ba = brazier_audit(low.data)

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
    print(f"measured parts bowl={ba['bowl']} legs={ba['leg']} ash={ba['ash']} "
          f"coals={ba['coal']} other={ba['other']} foot_worst={ba['foot_worst']:.5f} "
          f"leg_bite={ba['leg_bite']:.5f} seat=({ba['seat_min']:.5f},{ba['seat_max']:.5f}) "
          f"freeboard={ba['freeboard']:.5f} coal_hits={ba['coal_hits']} "
          f"coal_spread={ba['coal_spread']:.3f}")
    print(f"measured stability mass={ba['mass']:.2f}kg com=({ba['com'].x:.5f},"
          f"{ba['com'].y:.5f},{ba['com'].z:.5f}) d_edge={ba['d_edge']:.5f} "
          f"tip={math.degrees(ba['tip']):.2f}deg")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + nothing
    if nmat != MATERIAL_COUNT or distinct != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct} != {MATERIAL_COUNT}", 5),) + nothing
    for idx, floor, label in ((IRON_IDX, IRON_FACES_MIN, "iron"),
                              (COAL_IDX, COAL_FACES_MIN, "coal"),
                              (ASH_IDX, ASH_FACES_MIN, "ash")):
        if idx_counts.get(idx, 0) < floor:
            return (fail(f"{label} faces {idx_counts.get(idx, 0)} < {floor}", 5),) + nothing
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
    if ba["leg"] != N_LEGS or ba["foot_worst"] > FOOT_Z_MAX:
        return (fail(f"feet: {ba['leg']} of {N_LEGS} legs, worst foot z={ba['foot_worst']:.5f} "
                     f"> {FOOT_Z_MAX} (--float-foot is the designed fail)", 16),) + nothing
    if ba["leg_bite"] < LEG_BITE_MIN:
        return (fail(f"legs bite the bowl {ba['leg_bite']:.5f} < {LEG_BITE_MIN} "
                     "(--short-legs is the designed fail)", 17),) + nothing
    if ba["seat_min"] < COAL_SEAT_MIN or ba["seat_max"] > COAL_SEAT_MAX:
        return (fail(f"coal seat ({ba['seat_min']:.5f}, {ba['seat_max']:.5f}) outside "
                     f"[{COAL_SEAT_MIN}, {COAL_SEAT_MAX}] (--float-coals is the designed fail)", 18),) + nothing
    if ba["freeboard"] < FREEBOARD_MIN:
        return (fail(f"freeboard {ba['freeboard']:.5f} < {FREEBOARD_MIN} "
                     "(--overfill is the designed fail)", 18),) + nothing
    if ba["tip"] < TIP_MIN:
        return (fail(f"tip angle {math.degrees(ba['tip']):.2f} deg < "
                     f"{math.degrees(TIP_MIN):.1f} (--tuck-legs is the designed fail)", 19),) + nothing
    if ba["coal_hits"]:
        return (fail(f"{ba['coal_hits']} coal pairs interpenetrate, need 0 "
                     "(--pile-coals is the designed fail)", 20),) + nothing
    if ba["coal_spread"] < COAL_SPREAD_MIN:
        return (fail(f"coal size spread {ba['coal_spread']:.3f} < {COAL_SPREAD_MIN} "
                     "(--uniform-coals is the designed fail)", 21),) + nothing
    return 0, low, high, mats, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])


def render_still(low, mats, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(mats[IRON_IDX], tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only.
    low.rotation_euler.z = math.radians(8.0)

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

    light("Key", "AREA", (-2.6, -3.4, 3.8), 300.0, 3.5, (1.0, 0.95, 0.88), (46, 0, -38))
    light("Fill", "AREA", (3.4, -2.6, 1.8), 40.0, 6.0, (0.74, 0.84, 1.0), (66, 0, 52))
    light("Rim", "AREA", (-1.6, 2.8, 2.4), 200.0, 3.0, (0.62, 0.78, 1.0), (-60, 0, 200))
    # The warm floor pool behind the piece: a spot aimed at a floor point.
    # This camera is low and close; the house area wedge put the pool on
    # the back wall, and an area lamp moved nearer lit the whole floor.
    ld = bpy.data.lights.new("Wedge", "SPOT")
    ld.energy, ld.color = 170.0, (1.0, 0.66, 0.34)
    ld.spot_size, ld.spot_blend, ld.shadow_soft_size = math.radians(44.0), 1.0, 0.3
    wedge = bpy.data.objects.new("Wedge", ld)
    wedge.location = (0.45, 1.55, 1.70)
    wedge.rotation_euler = (Vector((0.10, 0.30, 0.0)) - wedge.location).to_track_quat(
        "-Z", "Y").to_euler()
    scene.collection.objects.link(wedge)
    # Render-only: the fire's own light, well above the coals so the ash
    # is lit by it rather than burnt out.
    light("Fire", "POINT", (0.0, 0.0, 0.78), 9.0, 0.25, (1.0, 0.45, 0.14))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.10, -1.95, 1.30)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.31)
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
    p.add_argument("--float-foot", action="store_true")
    p.add_argument("--short-legs", action="store_true")
    p.add_argument("--float-coals", action="store_true")
    p.add_argument("--overfill", action="store_true")
    p.add_argument("--tuck-legs", action="store_true")
    p.add_argument("--pile-coals", action="store_true")
    p.add_argument("--uniform-coals", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, mats, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_foot=args.float_foot,
        short_legs=args.short_legs,
        float_coals=args.float_coals,
        overfill=args.overfill,
        tuck_legs=args.tuck_legs,
        pile_coals=args.pile_coals,
        uniform_coals=args.uniform_coals,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, mats, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("brazier OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
