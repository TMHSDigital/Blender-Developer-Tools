"""Game-ready rope bridge — a showcase piece, not an example.

Asserts budget conformance of a procedural rope footbridge: two log posts
and a sill at each end, twenty planks laid on two foot ropes that hang
between the sills, two hand ropes lashed to the posts, vertical ropes
tying hand rope to foot rope, and foot ropes run back over the sills to
ground stakes. Carried through UVs, two materials (timber, rope), a
high-to-low normal bake, an LOD chain, a compound box collider, and a
Unity glTF export.

The budget that matters here is the one a rope bridge can fail
invisibly: the deck must hang as a parabola between the sills — the
shape a uniformly loaded cable takes — recomputed by a least-squares fit
to the plank top faces rather than from the function the generator
used. Two straight ramps meeting at midspan have the same ends, the same
sag and the same bounding box; only the fit knows the difference.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-post`` the named
supports, ``--short-rails`` the rope-end joint bite, ``--float-planks``
the plank seat, ``--loose-lashings`` the lashing hoop,
``--float-suspenders`` the one-assembly contact graph, ``--lean-post``
plumb, ``--vee-deck`` the deck parabola, ``--drift-planks`` the plank
pitch, ``--slack-rails`` the rail height, ``--sharp-plank`` the edge
treatment, ``--low-bake`` the baked texels per UV cell.

Fixed seed 31 for plank lengths, post wobble and tone. DECIMATE
COLLAPSE triangle counts are not byte-identical across Blender versions
— the LOD gate is a ratio band, not an exact count.

    blender --background --python rope_bridge.py --
    blender --background --python rope_bridge.py -- --vee-deck
    blender --background --python rope_bridge.py -- --output bridge.png
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
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

# A 3.6 m span between post centres, 0.8 m planks: a garden or gorge
# footbridge module. X runs along the span, Y across it, Z up.
SPAN = 3.60
HALF = SPAN / 2.0
BRIDGE_SEED = 31

# Log posts, tapered and plumb, carrying the hand ropes.
POST_Y = 0.46
POST_H = 1.48
POST_R_BOT = 0.068
POST_R_TOP = 0.060
POST_SEG = 16
POST_WOBBLE = 0.03
# Sills: a squared beam across each end, through-tenoned to the post
# centres. The foot ropes ride over the top of it.
SILL_W = 0.10
SILL_H = 0.10
SILL_TOP = 0.50
# Ground stakes behind each end, where the foot ropes are tied off.
STAKE_OUT = 0.45
STAKE_R = 0.042
STAKE_H = 0.36
STAKE_SEG = 12
STAKE_TIE = 0.20

# Ropes are laid, not piped: a three-lobed section turned one vertex step
# per ring, so each lobe winds along the path as a strand.
ROPE_PIPE = 9
ROPE_LOBE = 0.20
THIN_PIPE = 6
THIN_LOBE = 0.15
FOOT_Y = 0.33
FOOT_R = 0.017
# The foot rope bites the sill top; below the lobe spread, so it never
# floats over a trough in the lay.
FOOT_BITE = 0.006
HAND_R = 0.016
HAND_Z = 1.30
HAND_SAG = 0.10
SUSP_R = 0.008
SUSP_RINGS = 6
# Suspenders tie every third plank gap, symmetric about midspan.
SUSP_EVERY = 3
LASH_R = 0.010
LASH_BITE = 0.0025
LASH_TURNS = 2
LASH_PITCH = 0.021
POST_LASH_SEG = 14
STAKE_LASH_SEG = 12
# A rope end finishes in a short blunt cone this fraction of its radius
# long, so every end is closed without a fan cap.
CONE = 0.5

# The deck: planks on the foot ropes, pitched evenly along the rope.
DECK_SAG = 0.22
PLANK_N = 20
PLANK_W = 0.13
PLANK_T = 0.030
PLANK_L = 0.80
PLANK_L_JITTER = 0.015
# The first and last plank centres, clear of the sill's inner face.
DECK_END = HALF - 0.20
# Each plank's underside is set from the rope's own reach at its station,
# so the bite is exact whatever the lay does under it.
PLANK_BITE = 0.004
CHAMFER = 0.005

# Parabola half-span: the foot rope reaches sill height at the sill's
# inner face and runs level over it.
DECK_HP = HALF - SILL_W / 2.0
FOOT_Z_END = SILL_TOP + FOOT_R - FOOT_BITE

BBOX_TOL = 0.020
OUTER_SIZE = (4.619, 1.073, 1.480)

BASE_TRIS_MIN = 8300
BASE_TRIS_MAX = 9200
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
TIMBER_FACES_MIN = 1100
ROPE_FACES_MIN = 2800
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 400
BAKE_RES = 512
LOW_BAKE_RES = 256
CAGE_EXTRUSION = 0.01
# A UV cell narrower than this many baked texels reads its neighbour's
# normals across the border under bilinear lookup.
TEXELS_PER_CELL_MIN = 12.0
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
RIGHT_ANGLE_TOL = math.radians(5.0)
LIFT_Z = 0.05

SUPPORTS = 8
SUPPORT_Z_MAX = 1e-3
FLOAT_POST_LIFT = 0.012
# Joint bites, as the deepest member vertex inside the host's surface.
RAIL_EMBED_MIN = 0.030
FOOT_EMBED_MIN = 0.020
SILL_EMBED_MIN = 0.010
SHORT_RAIL_GAP = 0.020
# Plank seat on each foot rope, measured against the plank's own underside.
PLANK_BITE_MIN = 0.002
PLANK_BITE_MAX = 0.008
FLOAT_PLANK_LIFT = 0.007
# Lashing hoop: how far each turn bites into its host.
LASH_BITE_MIN = 0.0005
LASH_BITE_MAX = 0.0050
LOOSE_LASH_BITE = -0.004
FLOAT_SUSP_PULL = 0.030
# Plumb: bottom-slab and top-slab centroids of each post and stake.
PLUMB_TOL = 0.004
LEAN_TOP = 0.020
# Deck parabola: every plank top centre within this of the fitted
# parabola, and the fitted sag within SAG_TOL of DECK_SAG.
CURVE_TOL = 0.006
SAG_TOL = 0.015
# Plank pitch: every gap between neighbouring plank tops within this of
# the mean. Feet find planks blind; spacing is function, not surface.
PITCH_TOL = 0.003
DRIFT_PLANK = 0.015
# Rail height: hand rope centre above the deck top at midspan.
RAIL_H_MIN = 0.80
RAIL_H_MAX = 1.00
SLACK_SAG = 0.40

TIMBER_IDX = 0
ROPE_IDX = 1
PLANK_TONE_JITTER = 0.26
WOOD_GRAIN_SCALE = 42.0


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


# --- curves -----------------------------------------------------------------


def deck_z(x, vee=False):
    """Foot-rope centre height over the deck: a parabola between the sills.

    A uniformly loaded cable hangs as a parabola. ``vee`` is the falsifier:
    two straight ramps with the same ends and the same sag.
    """
    u = min(1.0, abs(x) / DECK_HP)
    if vee:
        return FOOT_Z_END - DECK_SAG * (1.0 - u)
    return FOOT_Z_END - DECK_SAG * (1.0 - u * u)


def deck_slope(x, vee=False):
    if abs(x) >= DECK_HP:
        return 0.0
    if vee:
        return math.copysign(DECK_SAG / DECK_HP, x) if x else 0.0
    return 2.0 * DECK_SAG * x / (DECK_HP * DECK_HP)


def catenary_a(half, sag):
    """Catenary parameter whose sag over ``half`` is ``sag``, by bisection."""
    lo, hi = 0.05, 200.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if mid * (math.cosh(half / mid) - 1.0) > sag:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def hand_z(x, a, sag):
    """Hand-rope centre: a free catenary from post to post."""
    return HAND_Z - sag + a * (math.cosh(x / a) - 1.0)


def deck_stations(vee=False):
    """Plank centres, evenly pitched by arc length along the foot rope."""
    n = 4000
    xs = [-DECK_END + 2.0 * DECK_END * i / n for i in range(n + 1)]
    s = [0.0]
    for i in range(n):
        dz = deck_z(xs[i + 1], vee) - deck_z(xs[i], vee)
        s.append(s[-1] + math.hypot(xs[i + 1] - xs[i], dz))
    out = []
    j = 0
    for k in range(PLANK_N):
        target = s[-1] * k / (PLANK_N - 1)
        while j < n and s[j + 1] < target:
            j += 1
        seg = s[j + 1] - s[j] if j < n else 1.0
        f = (target - s[j]) / seg if seg > 0 else 0.0
        out.append(xs[j] + f * (xs[min(j + 1, n)] - xs[j]))
    out[0], out[-1] = -DECK_END, DECK_END
    return out


# --- construction -----------------------------------------------------------


def ring_offsets(t, side, r, n, lobe, idx, angle0=0.0):
    """Section offsets for ring ``idx``: a lobed circle, turned per ring.

    The frame's side vector is fixed to the path's plane, so the lay never
    jumps where the path turns. The lobe phase advances one vertex step per
    ring, which winds each lobe along the path as a strand.
    """
    s = side - t * side.dot(t)
    s.normalize()
    up = t.cross(s)
    out = []
    for k in range(n):
        a = 2.0 * math.pi * k / n + angle0
        rr = r
        if lobe:
            rr = r * (1.0 + lobe * math.cos(3.0 * a - 2.0 * math.pi * 3.0 * idx / n))
        out.append(s * (rr * math.cos(a)) + up * (rr * math.sin(a)))
    return out


def path_tangents(pts, closed=False):
    m = len(pts)
    out = []
    for i in range(m):
        if closed:
            d = pts[(i + 1) % m] - pts[(i - 1) % m]
        elif i == 0:
            d = pts[1] - pts[0]
        elif i == m - 1:
            d = pts[-1] - pts[-2]
        else:
            d = pts[i + 1] - pts[i - 1]
        out.append(d.normalized())
    return out


def sweep(bm, pts, r, n, lobe, side, mat_idx, strips, closed=False, angle0=0.0):
    """Loft a laid rope along ``pts``; open ends close in a blunt cone.

    Returns the shell's vertices. UVs are recorded per face in ``strips``
    as one strip island: arc length along, section angle around, so the
    faces of one rope never overlap each other in UV. ``angle0`` turns the
    section, so two turns of one lashing are not the same section stacked,
    whose outer faces would share planes.
    """
    pts = [Vector(p) for p in pts]
    tans = path_tangents(pts, closed)
    rings = []
    for i, (p, t) in enumerate(zip(pts, tans)):
        offs = ring_offsets(t, side, r, n, lobe, i, angle0)
        rings.append([bm.verts.new(p + o) for o in offs])
    s = [0.0]
    for i in range(1, len(pts)):
        s.append(s[-1] + (pts[i] - pts[i - 1]).length)
    if closed:
        s.append(s[-1] + (pts[0] - pts[-1]).length)
    island = len({v[0] for v in strips.values()})
    m = len(rings)
    spans = m if closed else m - 1
    for k in range(spans):
        a, b = rings[k], rings[(k + 1) % m]
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new((a[i], a[j], b[j], b[i]))
            f.material_index = mat_idx
            f.smooth = True
            strips[f] = (island, {
                a[i]: (s[k], i / n), a[j]: (s[k], (i + 1) / n),
                b[j]: (s[k + 1], (i + 1) / n), b[i]: (s[k + 1], i / n),
            })
    if not closed:
        for ring, p, t, sign, s_end in (
            (rings[0], pts[0], tans[0], -1.0, s[0]),
            (rings[-1], pts[-1], tans[-1], 1.0, s[len(pts) - 1]),
        ):
            pole = bm.verts.new(p + t * (sign * CONE * r))
            s_pole = s_end + sign * CONE * r
            for i in range(n):
                j = (i + 1) % n
                f = bm.faces.new((pole, ring[i], ring[j]))
                f.material_index = mat_idx
                f.smooth = True
                strips[f] = (island, {
                    pole: (s_pole, (i + 0.5) / n),
                    ring[i]: (s_end, i / n), ring[j]: (s_end, (i + 1) / n),
                })
    return [v for ring in rings for v in ring]


def lathe(bm, axis_at, profile, n, mat_idx, strips):
    """A turned log: ``profile`` is (z, r) bottom to top, r == 0 at the poles.

    ``axis_at(z)`` gives the axis's XY at height z, so a leaning post keeps
    every ring on its own axis. Smooth-shaded: a log is round, and equal
    flat facets would read as a coopered stave.
    """
    island = len({v[0] for v in strips.values()})
    s = [0.0]
    for (z0, r0), (z1, r1) in zip(profile, profile[1:]):
        s.append(s[-1] + math.hypot(z1 - z0, r1 - r0))
    rings = []
    for z, r in profile:
        cx, cy = axis_at(z)
        if r <= 0.0:
            rings.append(bm.verts.new((cx, cy, z)))
            continue
        rings.append([
            bm.verts.new((cx + r * math.cos(2.0 * math.pi * k / n),
                          cy + r * math.sin(2.0 * math.pi * k / n), z))
            for k in range(n)
        ])
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
            f.smooth = True
            strips[f] = (island, uv)


def profile_radius(profile, z):
    """The lathe's radius at height z, linear between rings as the mesh is."""
    body = [(pz, pr) for pz, pr in profile if pr > 0.0]
    for (z0, r0), (z1, r1) in zip(body, body[1:]):
        if z0 <= z <= z1 and z1 > z0:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return body[-1][1]


def add_box(bm, centre, ax, ay, az, size, mat_idx):
    """A box on explicit axes; ``size`` is the full extent along each."""
    geo = bmesh.ops.create_cube(bm, size=1.0)
    for v in geo["verts"]:
        c = v.co.copy()
        v.co = centre + ax * (c.x * size[0]) + ay * (c.y * size[1]) + az * (c.z * size[2])
    for f in {f for v in geo["verts"] for f in v.link_faces}:
        f.material_index = mat_idx
        f.smooth = False
    return geo["verts"]


def pack_uvs(bm, strips, margin=0.08):
    """One grid cell per UV island.

    A rope, post or stake is one strip island (arc length by section
    angle), recorded in ``strips`` as it was built; every other face is
    its own planar island. Cells are sized from the island count, which is
    what the baked-texel budget reads back.
    """
    uv = bm.loops.layers.uv.new("UVMap")
    bm.faces.index_update()
    islands = {}
    order = []
    for face in bm.faces:
        key = ("s", strips[face][0]) if face in strips else ("f", face.index)
        if key not in islands:
            islands[key] = []
            order.append(key)
        islands[key].append(face)
    cols = max(1, math.ceil(math.sqrt(len(order))))
    rows = max(1, math.ceil(len(order) / cols))
    cell_w, cell_h = 1.0 / cols, 1.0 / rows
    pad_u, pad_v = margin * cell_w * 0.5, margin * cell_h * 0.5
    usable_w, usable_h = cell_w - 2.0 * pad_u, cell_h - 2.0 * pad_v
    for idx, key in enumerate(order):
        faces = islands[key]
        coords = {}
        for face in faces:
            if face in strips:
                m = strips[face][1]
                coords[face] = [m[loop.vert] for loop in face.loops]
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
            coords[face] = pts
        allc = [c for cs in coords.values() for c in cs]
        minx = min(c[0] for c in allc)
        maxx = max(c[0] for c in allc)
        miny = min(c[1] for c in allc)
        maxy = max(c[1] for c in allc)
        dx = max(maxx - minx, 1e-8)
        dy = max(maxy - miny, 1e-8)
        ou = (idx % cols) * cell_w + pad_u
        ov = (idx // cols) * cell_h + pad_v
        for face in faces:
            for loop, (x, y) in zip(face.loops, coords[face]):
                loop[uv].uv = (
                    ou + (x - minx) / dx * usable_w,
                    ov + (y - miny) / dy * usable_h,
                )


def build_bridge_mesh(
    name,
    vee_deck=False,
    float_post=False,
    short_rails=False,
    float_planks=False,
    loose_lashings=False,
    float_suspenders=False,
    lean_post=False,
    drift_planks=False,
    slack_rails=False,
    sharp_plank=False,
    boxes=None,
):
    """The whole bridge in one bmesh. ``boxes`` collects collider boxes."""
    rng = random.Random(BRIDGE_SEED)
    hand_sag = SLACK_SAG if slack_rails else HAND_SAG
    cat_a = catenary_a(HALF, hand_sag)
    stations = deck_stations(vee_deck)
    gaps = [0.5 * (a + b) for a, b in zip(stations, stations[1:])]
    susp_x = [g for j, g in enumerate(gaps) if j % SUSP_EVERY == 0]
    strips = {}
    Y = Vector((0.0, 1.0, 0.0))
    X = Vector((1.0, 0.0, 0.0))
    Z = Vector((0.0, 0.0, 1.0))

    # Foot-rope path, -X to +X: stake, down-line, over the sill's outer
    # arris, level across the sill, the deck parabola, and back out.
    deck_x = sorted(set(
        [round(x, 9) for x in stations + gaps]
        + [-DECK_HP, DECK_HP, -0.5 * (DECK_HP + DECK_END), 0.5 * (DECK_HP + DECK_END)]
    ))

    def tail(sign):
        corner = (sign * (HALF + SILL_W / 2.0), SILL_TOP)
        stake = (sign * (HALF + STAKE_OUT), STAKE_TIE)
        rho = FOOT_R - FOOT_BITE
        dx, dz = stake[0] - corner[0], stake[1] - corner[1]
        dist = math.hypot(dx, dz)
        # The down-line leaves the arris on a tangent to the rope's bend.
        base = math.atan2(dz, dx)
        phi = base + sign * math.acos(rho / dist)
        start = math.pi / 2.0
        # Turn the short way round the arris, not through the sill.
        while phi - start > math.pi:
            phi -= 2.0 * math.pi
        while phi - start < -math.pi:
            phi += 2.0 * math.pi
        # One mitred ring on the bisector. The bend radius is smaller than
        # the rope, so a ring per few degrees of arc folds the section
        # through itself and leaves right-angle creases on the outside.
        half_turn = 0.5 * abs(phi - start)
        mid_ang = 0.5 * (start + phi)
        reach = rho / math.cos(half_turn)
        pts = [(corner[0] + reach * math.cos(mid_ang), corner[1] + reach * math.sin(mid_ang))]
        tx = corner[0] + rho * math.cos(phi)
        tz = corner[1] + rho * math.sin(phi)
        for k in (1, 2, 3):
            f = k / 4.0
            pts.append((tx + (stake[0] - tx) * f, tz + (stake[1] - tz) * f))
        pts.append(stake)
        return pts

    right = tail(1.0)
    left = [p for p in reversed(tail(-1.0))]
    mid = [(x, deck_z(x, vee_deck)) for x in deck_x]
    foot_xz = left + mid + right
    foot_idx = {round(x, 9): len(left) + k for k, x in enumerate(deck_x)}
    foot_pts = [Vector((x, 0.0, z)) for x, z in foot_xz]
    foot_tans = path_tangents(foot_pts)

    # Planks: each one's underside set from the rope's own reach along the
    # plank normal at its station, less the bite.
    planks = []
    for i, x in enumerate(stations):
        k = foot_idx[round(x, 9)]
        t = foot_tans[k]
        nrm = t.cross(Y).normalized()
        if nrm.z < 0.0:
            nrm = -nrm
        reach = max(o.dot(nrm) for o in ring_offsets(t, Y, FOOT_R, ROPE_PIPE, ROPE_LOBE, k))
        lift = reach - PLANK_BITE + PLANK_T / 2.0
        if float_planks:
            lift += FLOAT_PLANK_LIFT
        centre = foot_pts[k] + nrm * lift
        if drift_planks:
            centre = centre + t * (DRIFT_PLANK if i % 2 else -DRIFT_PLANK)
        length = PLANK_L + rng.uniform(-PLANK_L_JITTER, PLANK_L_JITTER)
        planks.append((centre, t, nrm, length))

    bm = bmesh.new()
    try:
        bevel_edges = []
        for i, (centre, t, nrm, length) in enumerate(planks):
            vs = add_box(bm, centre, t, Y, nrm, (PLANK_W, length, PLANK_T), TIMBER_IDX)
            if boxes is not None:
                boxes.append((centre, t, Y, nrm, (PLANK_W, length, PLANK_T)))
            if not (sharp_plank and i == PLANK_N // 2):
                bevel_edges.extend({e for v in vs for e in v.link_edges})
        for sign in (-1.0, 1.0):
            c = Vector((sign * HALF, 0.0, SILL_TOP - SILL_H / 2.0))
            vs = add_box(bm, c, X, Y, Z, (SILL_W, 2.0 * POST_Y, SILL_H), TIMBER_IDX)
            if boxes is not None:
                boxes.append((c, X, Y, Z, (SILL_W, 2.0 * POST_Y, SILL_H)))
            bevel_edges.extend({e for v in vs for e in v.link_edges})
        bm.edges.index_update()
        bevel_edges = sorted(set(bevel_edges), key=lambda e: e.index)
        if bevel_edges:
            bmesh.ops.bevel(
                bm,
                geom=bevel_edges,
                offset=CHAMFER,
                segments=1,
                profile=0.5,
                affect="EDGES",
                clamp_overlap=True,
                material=TIMBER_IDX,
            )
        for f in bm.faces:
            f.smooth = False

        # Posts and stakes: tapered, faintly wobbled logs, plumb unless the
        # falsifier leans one. Every ring sits on the post's own axis.
        posts = []
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                cx, cy = sx * HALF, sy * POST_Y
                lift = FLOAT_POST_LIFT if (float_post and sx < 0 and sy < 0) else 0.0
                lean = LEAN_TOP if (lean_post and sx > 0 and sy < 0) else 0.0
                w = 1.0 + rng.uniform(-POST_WOBBLE, POST_WOBBLE)

                def r_at(z):
                    return POST_R_BOT + (POST_R_TOP - POST_R_BOT) * z / POST_H

                prof = [
                    (0.0, 0.0), (0.0, 0.86 * r_at(0.0)), (0.014, r_at(0.014)),
                    (0.5 * POST_H, r_at(0.5 * POST_H) * w),
                    (POST_H - 0.044, r_at(POST_H - 0.044)),
                    # A two-step round-over: one ring left the dome faceted.
                    (POST_H - 0.018, 0.90 * r_at(POST_H)),
                    (POST_H - 0.004, 0.56 * r_at(POST_H)), (POST_H, 0.0),
                ]
                prof = [(z + lift, r) for z, r in prof]

                def axis_at(z, cx=cx, cy=cy, lean=lean):
                    return cx + lean * z / POST_H, cy

                lathe(bm, axis_at, prof, POST_SEG, TIMBER_IDX, strips)
                posts.append((sx, sy, axis_at, prof))
                if boxes is not None:
                    r0 = POST_R_BOT
                    boxes.append((Vector((cx, cy, lift + POST_H / 2.0)), X, Y, Z,
                                  (2.0 * r0, 2.0 * r0, POST_H)))
        stakes = []
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                cx, cy = sx * (HALF + STAKE_OUT), sy * FOOT_Y
                w = 1.0 + rng.uniform(-POST_WOBBLE, POST_WOBBLE)
                prof = [
                    (0.0, 0.0), (0.0, 0.88 * STAKE_R), (0.012, STAKE_R),
                    (0.5 * STAKE_H, STAKE_R * w), (STAKE_H - 0.030, STAKE_R),
                    (STAKE_H - 0.012, 0.88 * STAKE_R),
                    (STAKE_H - 0.003, 0.54 * STAKE_R), (STAKE_H, 0.0),
                ]

                def axis_at(z, cx=cx, cy=cy):
                    return cx, cy

                lathe(bm, axis_at, prof, STAKE_SEG, TIMBER_IDX, strips)
                stakes.append((sx, sy, axis_at, prof))
                if boxes is not None:
                    boxes.append((Vector((cx, cy, STAKE_H / 2.0)), X, Y, Z,
                                  (2.0 * STAKE_R, 2.0 * STAKE_R, STAKE_H)))

        # Foot ropes, both sides, on the one path.
        for sy in (-1.0, 1.0):
            pts = [Vector((p.x, sy * FOOT_Y, p.z)) for p in foot_pts]
            sweep(bm, pts, FOOT_R, ROPE_PIPE, ROPE_LOBE, Y, ROPE_IDX, strips)

        # Hand ropes: post centre to post centre, a free catenary. The
        # falsifier stops each end short of the post's surface.
        hx = sorted(set([round(x, 9) for x in deck_x] + [-HALF, HALF]))
        if short_rails:
            end = HALF - POST_R_BOT - SHORT_RAIL_GAP
            hx = [x for x in hx if abs(x) < end] + [-end, end]
            hx = sorted(hx)
        for sy in (-1.0, 1.0):
            pts = [Vector((x, sy * POST_Y, hand_z(x, cat_a, hand_sag))) for x in hx]
            sweep(bm, pts, HAND_R, ROPE_PIPE, ROPE_LOBE, Y, ROPE_IDX, strips)

        # Suspenders: foot-rope centre to hand-rope centre at every third
        # plank gap, so each end is buried in the rope it ties.
        pull = FLOAT_SUSP_PULL if float_suspenders else 0.0
        for sy in (-1.0, 1.0):
            for x in susp_x:
                a = Vector((x, sy * FOOT_Y, deck_z(x, vee_deck)))
                b = Vector((x, sy * POST_Y, hand_z(x, cat_a, hand_sag)))
                d = (b - a).normalized()
                a, b = a + d * pull, b - d * pull
                pts = [a + (b - a) * (k / (SUSP_RINGS - 1)) for k in range(SUSP_RINGS)]
                sweep(bm, pts, SUSP_R, THIN_PIPE, THIN_LOBE, X, ROPE_IDX, strips)

        # Lashings: turns hooped onto the host, the inner radius a named
        # bite inside the host's own radius at that height.
        bite = LOOSE_LASH_BITE if loose_lashings else LASH_BITE

        def lash(axis_at, prof, z, seg, angle0=0.0):
            cx, cy = axis_at(z)
            rm = profile_radius(prof, z) - bite + LASH_R
            pts = [
                Vector((cx + rm * math.cos(2.0 * math.pi * k / seg),
                        cy + rm * math.sin(2.0 * math.pi * k / seg), z))
                for k in range(seg)
            ]
            sweep(bm, pts, LASH_R, THIN_PIPE, THIN_LOBE, Z, ROPE_IDX, strips,
                  closed=True, angle0=angle0)

        for _sx, _sy, axis_at, prof in posts:
            z0 = HAND_Z - 0.5 * (LASH_TURNS - 1) * LASH_PITCH
            for k in range(LASH_TURNS):
                # Each turn's section half a vertex step round from the last.
                lash(axis_at, prof, z0 + k * LASH_PITCH, POST_LASH_SEG,
                     angle0=k * math.pi / THIN_PIPE)
        for _sx, _sy, axis_at, prof in stakes:
            lash(axis_at, prof, STAKE_TIE, STAKE_LASH_SEG)

        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        pack_uvs(bm, strips)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    paint_planks(me)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


# --- surface ----------------------------------------------------------------


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
    """Per-shell ``PlankTone`` and ``GrainDir`` face attributes.

    Twenty planks cut from one material are one plank repeated. Each shell
    gets a seeded tone and grain along its own long axis: across the deck
    on a plank, up a post.
    """
    tone = [0.5] * len(me.polygons)
    grain = [(0.0, 0.0, 1.0)] * len(me.polygons)
    owner = {}
    rng = random.Random(BRIDGE_SEED * 17)
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
    ramp.color_ramp.elements[0].color = (0.11, 0.060, 0.030, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.34, 0.20, 0.100, 1.0)
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
    rough.inputs["To Min"].default_value = 0.74
    rough.inputs["To Max"].default_value = 0.56
    nt.links.new(noise.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def rope_material(name):
    """Hemp: pale fibre, darker in the lay, matte, with a fine fibre bump."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = 0.0
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 70.0
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.6
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.26, 0.19, 0.10, 1.0)
    ramp.color_ramp.elements[1].position = 0.68
    ramp.color_ramp.elements[1].color = (0.56, 0.45, 0.28, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.35
    bmp.inputs["Distance"].default_value = 0.002
    nt.links.new(noise.outputs["Fac"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def bridge_materials():
    """(timber, rope): shared by the check, the render and inspection."""
    return wood_material("BridgeTimber"), rope_material("BridgeRope")


def assign_slots(obj, timber, rope):
    mats = obj.data.materials
    for i, mat in enumerate((timber, rope)):
        if i < len(mats):
            mats[i] = mat
        else:
            mats.append(mat)


# --- measurement ------------------------------------------------------------


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
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
    span = max(
        1e-6,
        max((a[2] - a[0]) for a in aabbs),
        max((a[3] - a[1]) for a in aabbs),
    )
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
                    0.0, min(a[3], b[3]) - max(a[1], b[1])
                )
    return min(us), min(vs), max(us), max(vs), overlap, len(aabbs)


def uv_island_texels(mesh, res):
    """Smallest UV island extent in baked texels, islands found from the UVs.

    Two faces are one island when they share a vertex at the same UV. The
    cell size is read back from the mesh and the image, not from the grid
    the packer used.
    """
    uv = mesh.uv_layers.active
    if uv is None:
        return 0.0, 0
    parent = list(range(len(mesh.polygons)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first = {}
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            u, v = uv.data[li].uv
            key = (mesh.loops[li].vertex_index, round(u, 6), round(v, 6))
            if key in first:
                a, b = find(first[key]), find(poly.index)
                if a != b:
                    parent[a] = b
            else:
                first[key] = poly.index
    boxes = {}
    for poly in mesh.polygons:
        root = find(poly.index)
        for li in poly.loop_indices:
            u, v = uv.data[li].uv
            b = boxes.setdefault(root, [u, v, u, v])
            b[0], b[1] = min(b[0], u), min(b[1], v)
            b[2], b[3] = max(b[2], u), max(b[3], v)
    ext = min(min(b[2] - b[0], b[3] - b[1]) for b in boxes.values())
    return ext * res, len(boxes)


def face_area(me, poly):
    idxs = poly.vertices
    if len(idxs) < 3:
        return 0.0
    v0 = me.vertices[idxs[0]].co
    area = 0.0
    for i in range(1, len(idxs) - 1):
        a = me.vertices[idxs[i]].co
        b = me.vertices[idxs[i + 1]].co
        area += (a - v0).cross(b - v0).length * 0.5
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
        "nv": nv, "ne": ne, "nf": nf, "ngons": ngons, "loose_v": loose_v,
        "loose_e": loose_e, "nonman": nonman, "zero_area": zero_area,
        "doubles": doubles,
    }


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
    """Coplanar face pairs from *different shells* — the z-fighting budget.

    Cross-shell, not merely share-no-vertex: two faces of one post's flat
    bottom fan are coplanar by construction. Z-fighting is two separate
    bodies landing on one plane. Candidate pairs come from a KD-tree range
    query at COPLANAR_CENTRE_MAX (copied from showcase/grindstone; do not
    import across pieces).
    """
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


def right_angle_edges(me):
    """Manifold edges whose two faces meet at 90 degrees.

    Every plank and sill is chamfered, the logs are lathed with a chamfer
    ring at each end, and a rope section turns 40 or 60 degrees per edge.
    An edge still at 90 is a bevel pass that was skipped.
    """
    n = 0
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        for e in bm.edges:
            if len(e.link_faces) != 2:
                continue
            if abs(e.calc_face_angle(0.0) - math.pi / 2.0) <= RIGHT_ANGLE_TOL:
                n += 1
    finally:
        bm.free()
    return n


def shell_tree(me, group):
    """A BVH for one shell."""
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        member = set(group)
        drop = [f for f in bm.faces if not all(v.index in member for v in f.verts)]
        if drop:
            bmesh.ops.delete(bm, geom=drop, context="FACES")
        if not bm.faces:
            return None
        return BVHTree.FromBMesh(bm)
    finally:
        bm.free()


def classify(me):
    """Name every shell from its material and its own extent.

    Timber: a plank or sill is long across the deck (sills sit at the post
    stations), a post is tall, a stake is short and grounded. Rope: a main
    rope runs the span (foot if it reaches down to a stake, else hand), a
    suspender is tall and thin, a lashing is a flat loop.
    """
    out = {k: [] for k in (
        "plank", "sill", "post", "stake", "foot", "hand", "susp", "lash", "other")}
    face_mat = {}
    for p in me.polygons:
        for i in p.vertices:
            face_mat.setdefault(i, p.material_index)
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        xs, ys, zs = [p.x for p in pts], [p.y for p in pts], [p.z for p in pts]
        a = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
        ex, ey, ez = a[3] - a[0], a[4] - a[1], a[5] - a[2]
        c = Vector(((a[0] + a[3]) / 2, (a[1] + a[4]) / 2, (a[2] + a[5]) / 2))
        rec = {"g": g, "pts": pts, "aabb": a, "c": c}
        mat = face_mat.get(g[0], -1)
        if mat == TIMBER_IDX:
            if ey > 0.5 and ez < 0.2:
                out["sill" if abs(c.x) > HALF - 0.1 else "plank"].append(rec)
            elif ez > 1.0:
                out["post"].append(rec)
            elif ez > 0.2 and max(ex, ey) < 0.2:
                out["stake"].append(rec)
            else:
                out["other"].append(rec)
        elif mat == ROPE_IDX:
            if ex > 2.0:
                out["foot" if a[2] < STAKE_H else "hand"].append(rec)
            elif ez > 0.3:
                out["susp"].append(rec)
            elif ez < 0.06:
                out["lash"].append(rec)
            else:
                out["other"].append(rec)
        else:
            out["other"].append(rec)
    out["plank"].sort(key=lambda r: r["c"].x)
    return out


def inside_depth(tree, pts):
    """Deepest point of ``pts`` inside the (convex) shell ``tree``.

    Signed by the nearest face's normal: positive inside. Negative means
    every point is outside, by at least that much.
    """
    best = -99.0
    for p in pts:
        loc, nrm, _i, dist = tree.find_nearest(p)
        if loc is None:
            continue
        d = dist if (p - loc).dot(nrm) < 0.0 else -dist
        best = max(best, d)
    return best


def nearest(recs, p):
    return min(recs, key=lambda r: (Vector((r["c"].x, r["c"].y, 0.0))
                                    - Vector((p.x, p.y, 0.0))).length)


def bridge_audit(me):
    """Supports, joint bites, seats, contact graph, plumb and the deck."""
    parts = classify(me)
    trees = {}

    def tree(rec):
        key = id(rec)
        if key not in trees:
            trees[key] = shell_tree(me, rec["g"])
        return trees[key]

    out = {
        "n": {k: len(v) for k, v in parts.items()},
        "support_worst": max(
            (r["aabb"][2] for r in parts["post"] + parts["stake"]), default=99.0),
        "n_support": len(parts["post"]) + len(parts["stake"]),
    }

    # Joint bites: every rope end and sill end deepest inside its host.
    rail = []
    for rope in parts["hand"]:
        for end in (min, max):
            x_end = end(p.x for p in rope["pts"])
            tip = [p for p in rope["pts"] if abs(p.x - x_end) < 0.10]
            post = nearest(parts["post"], Vector((x_end, rope["c"].y, 0.0)))
            rail.append(inside_depth(tree(post), tip))
    foot = []
    for rope in parts["foot"]:
        for end in (min, max):
            x_end = end(p.x for p in rope["pts"])
            tip = [p for p in rope["pts"] if abs(p.x - x_end) < 0.10]
            stake = nearest(parts["stake"], Vector((x_end, rope["c"].y, 0.0)))
            foot.append(inside_depth(tree(stake), tip))
    sill = []
    for s in parts["sill"]:
        for sy in (-1.0, 1.0):
            post = nearest(parts["post"], Vector((s["c"].x, sy * POST_Y, 0.0)))
            end = [p for p in s["pts"] if p.y * sy > 0.0]
            sill.append(inside_depth(tree(post), end))
    out["rail_embed"] = min(rail, default=-99.0)
    out["foot_embed"] = min(foot, default=-99.0)
    out["sill_embed"] = min(sill, default=-99.0)

    # Plank seats: how far each foot rope stands into the plank's
    # underside, measured in the plank's own frame at its own station.
    bites = []
    for plank in parts["plank"]:
        members = set(plank["g"])
        faces = [p for p in me.polygons if p.vertices[0] in members]
        top = max(faces, key=lambda p: (p.normal.z > 0.9, p.area))
        n = top.normal.copy()
        t = n.cross(Vector((0.0, 1.0, 0.0))).normalized()
        base = min(p.dot(n) for p in plank["pts"])
        half_w = max(abs((p - plank["c"]).dot(t)) for p in plank["pts"])
        plank["top"] = top.center.copy()
        for rope in parts["foot"]:
            under = [
                p for p in rope["pts"]
                if abs((p - plank["c"]).dot(t)) <= half_w
            ]
            bites.append(max((p.dot(n) for p in under), default=-99.0) - base)
    out["plank_bite_min"] = min(bites, default=-99.0)
    out["plank_bite_max"] = max(bites, default=99.0)

    # Lashing hoop: each turn bites its host (a post or a stake).
    hosts = parts["post"] + parts["stake"]
    lash = []
    for rec in parts["lash"]:
        host = nearest(hosts, rec["c"])
        lash.append(inside_depth(tree(host), rec["pts"]))
    out["lash_min"] = min(lash, default=-99.0)
    out["lash_max"] = max(lash, default=99.0)

    # One connected assembly: union every pair of shells whose surfaces
    # cross. Per-part budgets pass a rope resting a hair off its host.
    recs = [r for k in parts for r in parts[k]]
    parent = list(range(len(recs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(recs)):
        ai = recs[i]["aabb"]
        for j in range(i + 1, len(recs)):
            aj = recs[j]["aabb"]
            if any(ai[k] > aj[k + 3] + 1e-4 or aj[k] > ai[k + 3] + 1e-4 for k in range(3)):
                continue
            ti, tj = tree(recs[i]), tree(recs[j])
            if ti is not None and tj is not None and ti.overlap(tj):
                a, b = find(i), find(j)
                if a != b:
                    parent[a] = b
    out["components"] = len({find(i) for i in range(len(recs))})

    # Plumb: bottom-slab against top-slab centroid, per post and stake.
    plumb = 0.0
    for rec in parts["post"] + parts["stake"]:
        z0, z1 = rec["aabb"][2], rec["aabb"][5]
        h = z1 - z0
        lo = [p for p in rec["pts"] if z0 + 0.01 < p.z < z0 + 0.25 * h]
        hi = [p for p in rec["pts"] if z1 - 0.30 * h < p.z < z1 - 0.01]
        if not lo or not hi:
            plumb = 99.0
            continue
        cl = sum(lo, Vector()) / len(lo)
        ch = sum(hi, Vector()) / len(hi)
        plumb = max(plumb, math.hypot(ch.x - cl.x, ch.y - cl.y))
    out["plumb"] = plumb

    # The deck: least-squares parabola through the plank top centres.
    tops = [p["top"] for p in parts["plank"] if "top" in p]
    fit_dev, fit_sag, apex = 99.0, 0.0, 0.0
    if len(tops) >= 3:
        s = [0.0] * 5
        r = [0.0] * 3
        for p in tops:
            xp = 1.0
            for k in range(5):
                s[k] += xp
                if k < 3:
                    r[k] += xp * p.z
                xp *= p.x
        m = Matrix(((s[0], s[1], s[2]), (s[1], s[2], s[3]), (s[2], s[3], s[4])))
        c0, c1, c2 = m.inverted() @ Vector(r)
        fit_dev = max(abs(c0 + c1 * p.x + c2 * p.x * p.x - p.z) for p in tops)
        fit_sag = c2 * DECK_HP * DECK_HP
        apex = c0
    out["fit_dev"] = fit_dev
    out["fit_sag"] = fit_sag
    gaps = [(b - a).length for a, b in zip(tops, tops[1:])]
    mean = sum(gaps) / len(gaps) if gaps else 0.0
    out["pitch_mean"] = mean
    out["pitch_dev"] = max((abs(g - mean) for g in gaps), default=99.0)
    mids = [p.z for rope in parts["hand"] for p in rope["pts"] if abs(p.x) < 0.03]
    out["rail_h"] = (sum(mids) / len(mids) - apex) if mids else 0.0
    return out


def add_stray_vert(me):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bm.verts.new((0.0, 0.0, 0.9))
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


def box_collider(boxes, name):
    """Compound collider: one box per timber member.

    One convex hull over a sagging deck is a lens whose top is the chord
    between the sills, so a walker would float 0.22 m over midspan. A box
    per plank follows the sag; ropes are left out, as thin rope is not
    something a character collides with.
    """
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for centre, ax, ay, az, size in boxes:
            add_box(bm, centre, ax, ay, az, size, 0)
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    collider = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(collider)
    return collider


def setup_bake_image(obj, target_mat, size):
    if not obj.data.uv_layers:
        return None, None
    img = bpy.data.images.new("BridgeNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = TIMBER_IDX
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


def check(skip_decimate, lift_z=False, stray_vert=False, low_bake=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    boxes = []
    low = build_bridge_mesh("BridgeLow", boxes=boxes, **flags)
    high = build_bridge_mesh("BridgeHigh", **flags)
    timber, rope = bridge_materials()
    assign_slots(low, timber, rope)
    assign_slots(high, timber, rope)
    if stray_vert:
        add_stray_vert(low.data)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()

    if low.data is None or len(low.data.polygons) < 6:
        return (fail("bridge mesh did not build", 3),) + nothing

    base_tris = triangle_count(low.data)
    mats = [s for s in low.data.materials if s is not None]
    nmat = len(mats)
    distinct = len({id(s) for s in mats})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    res = LOW_BAKE_RES if low_bake else BAKE_RES
    img, tex = setup_bake_image(low, timber, res)
    if img is None:
        return (fail("bridge has no UV layer", 3),) + nothing
    bake_result = bake_normal(high, low)
    texels, n_islands = uv_island_texels(low.data, img.size[0])

    lod1 = make_lod(low, "BridgeLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BridgeLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = box_collider(boxes, "BridgeCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(), f"bdt_rope_bridge_{os.getpid()}.glb"
    )
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
    e90 = right_angle_edges(low.data)
    br = bridge_audit(low.data)

    print(f"blender={tuple(bpy.app.version)} skip_decimate={skip_decimate}")
    print(f"measured mat_index_counts={dict(sorted(idx_counts.items()))}")
    print(
        f"measured base_tris={base_tris} lod1_tris={lod1_tris} "
        f"lod2_tris={lod2_tris} r1={r1:.4f} r2={r2:.4f}"
    )
    print(
        f"measured nmat={nmat} uv=({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f}) "
        f"overlap={overlap:.6f} nfaces={nfaces} islands={n_islands} "
        f"texels_per_cell={texels:.2f} bake_res={img.size[0]}"
    )
    print(
        f"measured bbox=({size_x:.4f},{size_y:.4f},{size_z:.4f}) "
        f"outer={OUTER_SIZE} zmin={bb[2]:.5f}"
    )
    print(
        f"measured collider_tris={col_tris} bake={bake_result} "
        f"bake_has_data={img.has_data} export_bytes={export_size}"
    )
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf} edge90={e90}"
    )
    print(f"measured parts {br['n']}")
    print(
        f"measured joints supports={br['n_support']} support_worst={br['support_worst']:.5f} "
        f"rail_embed={br['rail_embed']:.5f} foot_embed={br['foot_embed']:.5f} "
        f"sill_embed={br['sill_embed']:.5f}"
    )
    print(
        f"measured seats plank_bite=({br['plank_bite_min']:.5f},{br['plank_bite_max']:.5f}) "
        f"lash=({br['lash_min']:.5f},{br['lash_max']:.5f}) components={br['components']}"
    )
    print(
        f"measured deck plumb={br['plumb']:.5f} fit_dev={br['fit_dev']:.5f} "
        f"fit_sag={br['fit_sag']:.5f} pitch_mean={br['pitch_mean']:.5f} "
        f"pitch_dev={br['pitch_dev']:.5f} rail_h={br['rail_h']:.5f}"
    )

    n = br["n"]
    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(
            f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4
        ),) + nothing
    if nmat != MATERIAL_COUNT or distinct != MATERIAL_COUNT:
        return (fail(
            f"material slots {nmat} distinct {distinct} != {MATERIAL_COUNT}", 5
        ),) + nothing
    if idx_counts.get(TIMBER_IDX, 0) < TIMBER_FACES_MIN:
        return (fail(
            f"timber faces {idx_counts.get(TIMBER_IDX, 0)} < {TIMBER_FACES_MIN}", 5
        ),) + nothing
    if idx_counts.get(ROPE_IDX, 0) < ROPE_FACES_MIN:
        return (fail(
            f"rope faces {idx_counts.get(ROPE_IDX, 0)} < {ROPE_FACES_MIN}", 5
        ),) + nothing
    if u0 < -UV_EPS or v0 < -UV_EPS or u1 > 1.0 + UV_EPS or v1 > 1.0 + UV_EPS:
        return (fail(
            f"UVs outside 0..1: ({u0:.4f},{v0:.4f})-({u1:.4f},{v1:.4f})", 6
        ),) + nothing
    if overlap > UV_OVERLAP_MAX:
        return (fail(f"UV AABB overlap {overlap:.6f} > {UV_OVERLAP_MAX}", 7),) + nothing
    if (
        abs(size_x - OUTER_SIZE[0]) > BBOX_TOL
        or abs(size_y - OUTER_SIZE[1]) > BBOX_TOL
        or abs(size_z - OUTER_SIZE[2]) > BBOX_TOL
    ):
        return (fail(
            f"bbox ({size_x:.4f},{size_y:.4f},{size_z:.4f}) off outer {OUTER_SIZE}", 8
        ),) + nothing
    if not (LOD1_RATIO_MIN <= r1 <= LOD1_RATIO_MAX):
        return (fail(
            f"LOD1 ratio {r1:.4f} not in [{LOD1_RATIO_MIN}, {LOD1_RATIO_MAX}] "
            "(--skip-decimate is the designed fail)", 9
        ),) + nothing
    if not (LOD2_RATIO_MIN <= r2 <= LOD2_RATIO_MAX):
        return (fail(
            f"LOD2 ratio {r2:.4f} not in [{LOD2_RATIO_MIN}, {LOD2_RATIO_MAX}]", 9
        ),) + nothing
    if col_tris > COLLIDER_TRIS_MAX:
        return (fail(f"collider tris {col_tris} > {COLLIDER_TRIS_MAX}", 11),) + nothing
    if bake_result != {"FINISHED"} or not img.has_data:
        return (fail(
            f"bake failed result={bake_result} has_data={img.has_data}", 12
        ),) + nothing
    if export_size <= 0:
        return (fail("export file missing or empty", 13),) + nothing
    if (
        hyg["loose_v"] or hyg["loose_e"] or hyg["nonman"] or hyg["zero_area"]
        or hyg["doubles"] or hyg["ngons"] or zf
    ):
        return (fail(
            f"hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
            f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
            f"doubles={hyg['doubles']} ngons={hyg['ngons']} zfight={zf} "
            "(--stray-vert is the designed fail)", 15
        ),) + nothing
    if abs(bb[2]) > ZMIN_EPS:
        return (fail(
            f"zmin {bb[2]:.6f} not within {ZMIN_EPS} of 0 "
            "(--lift-z is the designed fail)", 16
        ),) + nothing
    if br["n_support"] != SUPPORTS or br["support_worst"] > SUPPORT_Z_MAX:
        return (fail(
            f"supports {br['n_support']} of {SUPPORTS}, worst base z="
            f"{br['support_worst']:.5f} > {SUPPORT_Z_MAX} "
            "(--float-post is the designed fail)", 16
        ),) + nothing
    if (
        n["hand"] != 2 or n["foot"] != 2 or n["sill"] != 2
        or br["rail_embed"] < RAIL_EMBED_MIN
        or br["foot_embed"] < FOOT_EMBED_MIN
        or br["sill_embed"] < SILL_EMBED_MIN
    ):
        return (fail(
            f"joint bites: hand-rope ends {br['rail_embed']:.5f} < {RAIL_EMBED_MIN}, "
            f"foot-rope ends {br['foot_embed']:.5f} < {FOOT_EMBED_MIN} or sill "
            f"tenons {br['sill_embed']:.5f} < {SILL_EMBED_MIN} "
            f"(hand {n['hand']}, foot {n['foot']}, sill {n['sill']}) "
            "(--short-rails is the designed fail)", 17
        ),) + nothing
    if (
        n["plank"] != PLANK_N
        or br["plank_bite_min"] < PLANK_BITE_MIN
        or br["plank_bite_max"] > PLANK_BITE_MAX
    ):
        return (fail(
            f"plank seats: {n['plank']} of {PLANK_N} planks, bite "
            f"({br['plank_bite_min']:.5f}, {br['plank_bite_max']:.5f}) outside "
            f"[{PLANK_BITE_MIN}, {PLANK_BITE_MAX}] "
            "(--float-planks is the designed fail)", 18
        ),) + nothing
    n_lash = 4 * LASH_TURNS + 4
    if (
        n["lash"] != n_lash
        or br["lash_min"] < LASH_BITE_MIN
        or br["lash_max"] > LASH_BITE_MAX
    ):
        return (fail(
            f"lashings: {n['lash']} of {n_lash}, bite ({br['lash_min']:.5f}, "
            f"{br['lash_max']:.5f}) outside [{LASH_BITE_MIN}, {LASH_BITE_MAX}] "
            "(--loose-lashings is the designed fail)", 18
        ),) + nothing
    if br["components"] != 1:
        return (fail(
            f"contact graph has {br['components']} components, need 1 "
            "(--float-suspenders is the designed fail)", 18
        ),) + nothing
    if br["plumb"] > PLUMB_TOL:
        return (fail(
            f"a post or stake is {br['plumb']:.5f} off plumb > {PLUMB_TOL} "
            "(--lean-post is the designed fail)", 19
        ),) + nothing
    if br["fit_dev"] > CURVE_TOL or abs(br["fit_sag"] - DECK_SAG) > SAG_TOL:
        return (fail(
            f"deck off its parabola by {br['fit_dev']:.5f} > {CURVE_TOL} or fitted "
            f"sag {br['fit_sag']:.5f} off {DECK_SAG} by more than {SAG_TOL} "
            "(--vee-deck is the designed fail)", 19
        ),) + nothing
    if br["pitch_dev"] > PITCH_TOL:
        return (fail(
            f"plank pitch off its mean by {br['pitch_dev']:.5f} > {PITCH_TOL} "
            "(--drift-planks is the designed fail)", 19
        ),) + nothing
    if not (RAIL_H_MIN <= br["rail_h"] <= RAIL_H_MAX):
        return (fail(
            f"rail height {br['rail_h']:.5f} not in [{RAIL_H_MIN}, {RAIL_H_MAX}] "
            "(--slack-rails is the designed fail)", 19
        ),) + nothing
    if e90:
        return (fail(
            f"{e90} right-angle edges, need 0 (--sharp-plank is the designed fail)", 20
        ),) + nothing
    if texels < TEXELS_PER_CELL_MIN:
        return (fail(
            f"smallest UV island {texels:.2f} baked texels < {TEXELS_PER_CELL_MIN} "
            "(--low-bake is the designed fail)", 21
        ),) + nothing
    return 0, low, high, timber, tex, collider


def wire_normal(mat, tex):
    """Baked normal map into the timber BSDF."""
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, timber, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(timber, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    # Level on the floor: turned about Z only.
    low.rotation_euler.z = math.radians(-14.0)

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
    wall.location = (0.0, 9.0, 0.0)
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

    light("Key", (-4.2, -5.4, 6.2), 660.0, 5.0, (1.0, 0.95, 0.88), (46, 0, -38))
    light("Fill", (5.4, -4.0, 2.6), 90.0, 9.0, (0.74, 0.84, 1.0), (66, 0, 52))
    light("Rim", (-2.6, 4.2, 3.6), 420.0, 4.0, (0.62, 0.78, 1.0), (-60, 0, 200))
    light("Wedge", (1.6, 4.6, 2.5), 760.0, 6.5, (1.0, 0.70, 0.38), (-94, 0, 194))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.2, -6.6, 2.5)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.15, 0.0, 0.56)
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
    p.add_argument("--stray-vert", action="store_true")
    p.add_argument("--lift-z", action="store_true")
    p.add_argument("--float-post", action="store_true")
    p.add_argument("--short-rails", action="store_true")
    p.add_argument("--float-planks", action="store_true")
    p.add_argument("--loose-lashings", action="store_true")
    p.add_argument("--float-suspenders", action="store_true")
    p.add_argument("--lean-post", action="store_true")
    p.add_argument("--vee-deck", action="store_true")
    p.add_argument("--drift-planks", action="store_true")
    p.add_argument("--slack-rails", action="store_true")
    p.add_argument("--sharp-plank", action="store_true")
    p.add_argument("--low-bake", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, timber, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        low_bake=args.low_bake,
        vee_deck=args.vee_deck,
        float_post=args.float_post,
        short_rails=args.short_rails,
        float_planks=args.float_planks,
        loose_lashings=args.loose_lashings,
        float_suspenders=args.float_suspenders,
        lean_post=args.lean_post,
        drift_planks=args.drift_planks,
        slack_rails=args.slack_rails,
        sharp_plank=args.sharp_plank,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, timber, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("rope-bridge OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
