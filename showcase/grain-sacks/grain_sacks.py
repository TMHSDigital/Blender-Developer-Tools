"""Game-ready grain sacks — a showcase piece, not an example.

Asserts budget conformance of a procedural pile of three burlap grain
sacks: two standing, one lying slumped against them, each gathered at the
neck under a two-turn twine tie. Carried through UVs, two materials
(burlap, twine), a high-to-low normal bake, an LOD chain, a compound
convex collider, and a Unity glTF export.

The budget that matters here is the one a sack can fail invisibly: a
sack full of grain settles, so it rests on a flat contact patch, not on
a point. An egg-bottomed sack still touches the floor, so the grounded
zmin gate passes it; only the patch area, summed from the faces that lie
flat on the floor, knows the difference.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. Each falsifier violates one named
budget: ``--skip-decimate`` the LOD-ratio band, ``--stray-vert`` mesh
hygiene, ``--lift-z`` grounded zmin, ``--float-sack`` the named
supports, ``--slip-tie`` the tie-at-waist fit, ``--loose-tie`` the tie
seat, ``--part-sacks`` the press between sacks, ``--round-bottom`` the
contact patch, ``--high-belly`` the settled belly.

No randomness: every lump, pleat and tone is a closed-form term of the
sack's own parameters. DECIMATE COLLAPSE triangle counts are not
byte-identical across Blender versions — the LOD gate is a ratio band.

    blender --background --python grain_sacks.py --
    blender --background --python grain_sacks.py -- --round-bottom
    blender --background --python grain_sacks.py -- --output sacks.png
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

# Three sacks: two stood up, one laid down in front. Heights are the
# unsettled body length; W is the belly half-width, D the depth ratio of
# the flattened sack section (two sewn panels, not a tube).
SACKS = (
    {"name": "A", "at": (-0.24, 0.10), "yaw": 16.0, "H": 0.80, "W": 0.235,
     "D": 0.70, "lying": False, "stripe": 1, "front": 0.75, "phase": 0.0, "tone": 0.56},
    {"name": "B", "at": (0.30, 0.16), "yaw": -28.0, "H": 0.68, "W": 0.250,
     "D": 0.74, "lying": False, "stripe": 0, "front": 0.75, "phase": 0.9, "tone": 0.44},
    {"name": "C", "at": (0.04, -0.52), "yaw": 72.0, "H": 0.82, "W": 0.235,
     "D": 0.66, "lying": True, "stripe": 2, "front": 0.25, "phase": 2.1, "tone": 0.50},
)
# Order in which sacks are slid into contact: each one presses the sack
# named here, along the line between their starting centres.
PRESS_INTO = {"B": "A", "C": "A"}

SEG = 32
# Body profile: (height fraction, radius fraction). Round bottom, belly
# low where the grain settles, a shoulder, the gathered neck under the
# tie, and the pleated crown above it closing to a pole.
PROFILE = (
    (0.000, 0.00), (0.020, 0.52), (0.060, 0.80), (0.140, 0.96), (0.260, 1.00),
    (0.400, 0.97), (0.520, 0.88), (0.610, 0.68), (0.680, 0.36), (0.720, 0.19),
    (0.750, 0.21), (0.800, 0.33), (0.840, 0.30), (0.870, 0.00),
)
# --high-belly: same widths, the widest ring moved up to 0.52 of the body.
HIGH_BELLY_PROFILE = (
    (0.000, 0.00), (0.020, 0.50), (0.060, 0.72), (0.140, 0.82), (0.260, 0.90),
    (0.400, 0.97), (0.520, 1.00), (0.610, 0.78), (0.680, 0.36), (0.720, 0.19),
    (0.750, 0.21), (0.800, 0.33), (0.840, 0.30), (0.870, 0.00),
)
BODY_RINGS = 30
NECK_T = 0.720
# Pleats gather where the tie cinches: none on the belly, deep on the
# crown, shallow under the tie itself so the tie has a round seat.
PLEATS = 11
PLEAT_SHOULDER = 0.09
PLEAT_TIE = 0.025
PLEAT_CROWN = 0.20
LUMP = 0.035

# Twine tie: two turns hooped onto the neck, the second half a vertex
# step round from the first so the two are not one section stacked.
TIE_R = 0.0065
TIE_PIPE = 6
TIE_LOBE = 0.12
TIE_BITE = 0.003
TIE_PITCH = 0.012
LOOSE_TIE_BITE = -0.003
SLIP_TIE = 0.050

# Settling: the body is sunk SINK below the floor and everything under
# SETTLE_C is folded up onto it, flat where the grain presses, and pushed
# outward so the squashed base bulges.
SINK = 0.060
SETTLE_C = 0.030
SPREAD = 0.55
LYING_SQUASH = 0.84
# Sacks press into each other by this much, found by sliding each one in
# along the line between centres until its deepest vertex inside the
# other reaches it.
PRESS = 0.012
PART_GAP = -0.004

BBOX_TOL = 0.020
OUTER_SIZE = (0.914, 0.905, 0.636)

BASE_TRIS_MIN = 8000
BASE_TRIS_MAX = 9300
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
CLOTH_FACES_MIN = 2600
TWINE_FACES_MIN = 900
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 450
COLLIDER_STRIDE = 3
BAKE_RES = 256
CAGE_EXTRUSION = 0.01
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05
LIFT_Z = 0.05
FLOAT_SACK = 0.012
SUPPORT_Z_MAX = 1e-3
# Tie at the waist: the host under the tie is narrower than the host
# WAIST_PROBE above and below it, by at least WAIST_MARGIN. A tie that is
# not in a waist slides off.
WAIST_PROBE = 0.040
WAIST_BAND = 0.012
WAIST_MARGIN = 0.008
# Tie seat: deepest twine vertex inside the cloth, per turn.
TIE_SEAT_MIN = 0.0010
TIE_SEAT_MAX = 0.0060
# Press: each slid sack's deepest vertex inside the sack it leans on.
PRESS_MIN = 0.006
PRESS_MAX = 0.020
# Contact patch: flat-on-floor area under each sack.
PATCH_MIN = 0.012
# Settled belly: the widest station in the lower part of the body.
BELLY_MAX = 0.42

CLOTH_IDX = 0
# Weave period on the cloth. 6 mm aliased into moire at hero distance.
WEAVE = 0.012
TWINE_IDX = 1


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


# --- profile ----------------------------------------------------------------


def pchip(knots, t):
    """Monotone cubic (Fritsch-Carlson) through ``knots`` at ``t``.

    Smooth through the knots without the overshoot a Catmull-Rom spline
    puts into the neck, which would pinch the cloth below the tie.
    """
    xs = [k[0] for k in knots]
    ys = [k[1] for k in knots]
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0.0:
            m[i] = 0.0
        else:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    t = min(max(t, xs[0]), xs[-1])
    i = min(n - 2, max(0, next((j for j in range(n - 1) if t <= xs[j + 1]), n - 2)))
    s = (t - xs[i]) / h[i]
    h00 = (1 + 2 * s) * (1 - s) ** 2
    h10 = s * (1 - s) ** 2
    h01 = s * s * (3 - 2 * s)
    h11 = s * s * (s - 1)
    return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]


def pleat_amp(t):
    """Pleat depth along the body: nothing on the belly, gathered at the neck."""
    if t < 0.52:
        return 0.0
    if t < 0.68:
        return PLEAT_SHOULDER * (t - 0.52) / 0.16
    if t < NECK_T:
        return PLEAT_SHOULDER + (PLEAT_TIE - PLEAT_SHOULDER) * (t - 0.68) / (NECK_T - 0.68)
    if t < 0.78:
        return PLEAT_TIE + (PLEAT_CROWN - PLEAT_TIE) * (t - NECK_T) / (0.78 - NECK_T)
    return PLEAT_CROWN


def section_point(sack, prof, t, a):
    """Body surface at height fraction ``t`` and section angle ``a``, local frame."""
    f = pchip(prof, t)
    ratio = sack["D"] + (1.0 - sack["D"]) * (1.0 - min(1.0, f))
    m = 1.0 + pleat_amp(t) * math.cos(PLEATS * a + sack["phase"])
    # Grain lumps: low-order, closed-form, fading out toward the neck.
    m += LUMP * max(0.0, 1.0 - t / 0.6) * math.cos(2.0 * a + 3.0 * t + sack["phase"])
    r = sack["W"] * f * m
    return Vector((r * math.cos(a), r * ratio * math.sin(a), t * sack["H"]))


# --- parts ------------------------------------------------------------------


class Part:
    """Loose geometry for one shell: verts, faces, per-corner UVs, metadata."""

    def __init__(self, kind, sack, mat):
        self.kind = kind
        self.sack = sack
        self.mat = mat
        self.verts = []
        self.faces = []
        self.uvs = []
        self.cloth = []

    def add(self, co):
        self.verts.append(Vector(co))
        return len(self.verts) - 1


def grid_faces(part, rings, s_vals, n, poles=None, closed=False):
    """Quads between consecutive rings (and pole fans), with strip UVs.

    ``poles`` maps 'start'/'end' to (vertex index, s) for a fan to a pole;
    the pole's UV sits half a column over, so every fan triangle has its
    own UV rectangle and nothing overlaps.
    """
    m = len(rings)
    spans = m if closed else m - 1
    for k in range(spans):
        a, b = rings[k], rings[(k + 1) % m]
        s0, s1 = s_vals[k], s_vals[k + 1]
        for i in range(n):
            j = (i + 1) % n
            part.faces.append((a[i], a[j], b[j], b[i]))
            part.uvs.append(((s0, i / n), (s0, (i + 1) / n), (s1, (i + 1) / n), (s1, i / n)))
    for key, ring, s_ring in (("start", rings[0], s_vals[0]), ("end", rings[-1], s_vals[m - 1])):
        if not poles or key not in poles:
            continue
        pole, s_pole = poles[key]
        for i in range(n):
            j = (i + 1) % n
            # Wound outward: the base fan runs the other way round from the crown's.
            if key == "start":
                part.faces.append((pole, ring[j], ring[i]))
                part.uvs.append(((s_pole, (i + 0.5) / n), (s_ring, (i + 1) / n), (s_ring, i / n)))
            else:
                part.faces.append((pole, ring[i], ring[j]))
                part.uvs.append(((s_pole, (i + 0.5) / n), (s_ring, i / n), (s_ring, (i + 1) / n)))


def body_part(sack, prof):
    """The sack body: a lofted, pleated, lumpy bag closed at both poles."""
    part = Part("body", sack["name"], CLOTH_IDX)
    top = prof[-1][0]
    ts = [0.012 + (top - 0.024) * k / (BODY_RINGS - 1) for k in range(BODY_RINGS)]
    ts += [NECK_T + d * TIE_PITCH / sack["H"] for d in (-0.5, 0.0, 0.5)]
    ts = sorted(set(round(t, 6) for t in ts))
    rings = []
    for t in ts:
        rings.append([part.add(section_point(sack, prof, t, 2.0 * math.pi * i / SEG))
                      for i in range(SEG)])
    bottom = part.add((0.0, 0.0, 0.0))
    crown = part.add((0.0, 0.0, top * sack["H"]))
    s = [t * sack["H"] for t in ts]
    grid_faces(part, rings, s, SEG, poles={"start": (bottom, 0.0),
                                           "end": (crown, top * sack["H"])})
    # Cloth coordinates for the weave and stripes: metres round the sack
    # and metres up it, read by the shader so the weave follows the cloth
    # whatever way up the sack lies.
    # Round the sack is measured from its front (the broad face a viewer
    # sees: -Y stood up, +Y laid down), so stripes centre on it.
    circ = 2.0 * math.pi * sack["W"] * (1.0 + sack["D"]) / 2.0

    def around(v):
        return ((v - sack["front"] + 0.5) % 1.0 - 0.5) * circ

    part.cloth = []
    for corner_uvs in part.uvs:
        vs = [v for _u, v in corner_uvs]
        # A face straddling the back seam keeps its corners on one side.
        ref = around(vs[0])
        row = []
        for u, v in corner_uvs:
            a = around(v)
            if abs(a - ref) > 0.5 * circ:
                a += circ if a < ref else -circ
            row.append((a, u))
        part.cloth.append(tuple(row))
    return part


def ring_offsets(t, side, r, n, lobe, idx, angle0=0.0):
    """Section offsets for ring ``idx``: a lobed circle, turned per ring."""
    s = side - t * side.dot(t)
    s.normalize()
    up = t.cross(s)
    out = []
    for k in range(n):
        a = 2.0 * math.pi * k / n + angle0
        rr = r * (1.0 + lobe * math.cos(3.0 * a - 2.0 * math.pi * 3.0 * idx / n))
        out.append(s * (rr * math.cos(a)) + up * (rr * math.sin(a)))
    return out


def tie_part(sack, prof, t_station, bite, angle0):
    """One twine turn hooped onto the neck at ``t_station``.

    The centreline follows the host's own section at that station — every
    body vertex of that ring, pushed out along its radial by the twine
    radius less the bite — so the turn hugs the pleats rather than a
    circle that stands proud of the valleys and sinks into the crests.
    """
    part = Part("tie", sack["name"], TWINE_IDX)
    pts = []
    for i in range(SEG):
        p = section_point(sack, prof, t_station, 2.0 * math.pi * i / SEG)
        radial = Vector((p.x, p.y, 0.0))
        pts.append(p + radial.normalized() * (TIE_R - bite))
    m = len(pts)
    tans = [(pts[(i + 1) % m] - pts[(i - 1) % m]).normalized() for i in range(m)]
    side = Vector((0.0, 0.0, 1.0))
    rings = []
    for i, (p, t) in enumerate(zip(pts, tans)):
        rings.append([part.add(p + o) for o in ring_offsets(
            t, side, TIE_R, TIE_PIPE, TIE_LOBE, i, angle0)])
    s = [0.0]
    for i in range(1, m + 1):
        s.append(s[-1] + (pts[i % m] - pts[i - 1]).length)
    grid_faces(part, rings, s, TIE_PIPE, closed=True)
    part.cloth = [tuple((0.0, 0.0) for _ in uv) for uv in part.uvs]
    return part


def orient(parts, sack):
    """Stand or lay the sack, turn it by its yaw; returns its axis in world."""
    rot = Matrix.Identity(3)
    if sack["lying"]:
        # Lay it on its flat side: the section's narrow axis becomes Z.
        rot = Matrix.Rotation(math.radians(90.0), 3, "X") @ rot
        squash = Matrix.Diagonal((1.0, 1.0, LYING_SQUASH))
        rot = squash @ rot
    rot = Matrix.Rotation(math.radians(sack["yaw"]), 3, "Z") @ rot
    for part in parts:
        part.verts = [rot @ v for v in part.verts]
    axis = (rot @ Vector((0.0, 0.0, 1.0))).normalized()
    return axis


def settle(parts, axis, round_bottom=False):
    """Sink the sack SINK into the floor and fold everything under SETTLE_C up.

    Below SETTLE_C the height is remapped by g(u) = ((u + 1) / 2)^2 on
    u = z / SETTLE_C, clamped to 0 below u = -1: C1 at the fold, and
    exactly flat where the grain presses the floor. The squashed height
    goes outward, away from the sack's axis, so the base bulges.

    ``round_bottom`` is the falsifier: the same sink and the same fold
    height, but a linear squash that keeps the base round, touching the
    floor at one point.
    """
    zmin = min(v.z for p in parts for v in p.verts)
    shift = -zmin - SINK
    centre = sum((v for v in parts[0].verts), Vector()) / len(parts[0].verts)
    for part in parts:
        out = []
        for v in part.verts:
            z = v.z + shift
            if z >= SETTLE_C:
                out.append(Vector((v.x, v.y, z)))
                continue
            if round_bottom:
                z2 = (z + SINK) * SETTLE_C / (SETTLE_C + SINK)
                out.append(Vector((v.x, v.y, z2)))
                continue
            u = z / SETTLE_C
            z2 = 0.0 if u <= -1.0 else SETTLE_C * ((u + 1.0) / 2.0) ** 2
            w = Vector((v.x, v.y, z)) - centre
            w = w - axis * w.dot(axis)
            w.z = 0.0
            if w.length > 1e-9:
                w.normalize()
            out.append(Vector((v.x, v.y, z2)) + w * (SPREAD * (z2 - z)))
        part.verts = out


def translate(parts, d):
    for part in parts:
        part.verts = [v + d for v in part.verts]


def body_tree(part):
    return BVHTree.FromPolygons(part.verts, part.faces)


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


def slide_into(moving, fixed, target):
    """Slide ``moving`` along the line to ``fixed`` until it presses ``target``.

    Bisection on the offset, measuring the deepest vertex of the moving body
    inside the fixed one after each move. The press is then exact whatever
    the lumps and pleats do where the two meet.
    """
    body_m, body_f = moving[0], fixed[0]
    cm = sum(body_m.verts, Vector()) / len(body_m.verts)
    cf = sum(body_f.verts, Vector()) / len(body_f.verts)
    d = Vector((cf.x - cm.x, cf.y - cm.y, 0.0)).normalized()
    tree = body_tree(body_f)
    base = [v.copy() for v in body_m.verts]

    def depth(off):
        pts = [v + d * off for v in base]
        return inside_depth(tree, pts)

    lo, hi = -0.40, 0.60
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if depth(mid) > target:
            hi = mid
        else:
            lo = mid
    translate(moving, d * (0.5 * (lo + hi)))


def build_parts(
    slip_tie=False,
    loose_tie=False,
    part_sacks=False,
    round_bottom=False,
    high_belly=False,
    float_sack=False,
):
    """Every shell of the pile, placed, settled and pressed together."""
    bite = LOOSE_TIE_BITE if loose_tie else TIE_BITE
    prof = HIGH_BELLY_PROFILE if high_belly else PROFILE
    groups = {}
    axes = {}
    for sack in SACKS:
        parts = [body_part(sack, prof)]
        t0 = NECK_T + (SLIP_TIE / sack["H"] if slip_tie else 0.0)
        for k, dt in enumerate((-0.5, 0.5)):
            # A quarter step off the body's columns, and each turn half a
            # step off the other: a twine face parallel to the cloth face it
            # hugs, one column over, shared its plane.
            parts.append(tie_part(sack, prof, t0 + dt * TIE_PITCH / sack["H"], bite,
                                  (0.5 + k) * math.pi / TIE_PIPE))
        axis = orient(parts, sack)
        settle(parts, axis, round_bottom=round_bottom)
        body = parts[0]
        c = sum(body.verts, Vector()) / len(body.verts)
        translate(parts, Vector((sack["at"][0] - c.x, sack["at"][1] - c.y, 0.0)))
        groups[sack["name"]] = parts
        axes[sack["name"]] = axis
    for name, onto in PRESS_INTO.items():
        target = PART_GAP if (part_sacks and name == "C") else PRESS
        slide_into(groups[name], groups[onto], target)
    if float_sack:
        translate(groups["C"], Vector((0.0, 0.0, FLOAT_SACK)))
    return groups, axes


def pack_uvs(bm, islands, margin=0.08):
    """One grid cell per UV island; each island normalised into its cell."""
    uv = bm.loops.layers.uv.active
    cols = max(1, math.ceil(math.sqrt(len(islands))))
    rows = max(1, math.ceil(len(islands) / cols))
    cell_w, cell_h = 1.0 / cols, 1.0 / rows
    pad_u, pad_v = margin * cell_w * 0.5, margin * cell_h * 0.5
    for idx, faces in enumerate(islands):
        coords = [c for f in faces for c in (loop[uv].uv.copy() for loop in f.loops)]
        minx = min(c.x for c in coords)
        maxx = max(c.x for c in coords)
        miny = min(c.y for c in coords)
        maxy = max(c.y for c in coords)
        dx, dy = max(maxx - minx, 1e-8), max(maxy - miny, 1e-8)
        ou = (idx % cols) * cell_w + pad_u
        ov = (idx // cols) * cell_h + pad_v
        for f in faces:
            for loop in f.loops:
                c = loop[uv].uv
                loop[uv].uv = (ou + (c.x - minx) / dx * (cell_w - 2 * pad_u),
                               ov + (c.y - miny) / dy * (cell_h - 2 * pad_v))


def build_sacks_mesh(name, stray_vert=False, **flags):
    groups, _axes = build_parts(**flags)
    bm = bmesh.new()
    try:
        uv = bm.loops.layers.uv.new("UVMap")
        cloth = bm.loops.layers.uv.new("ClothCo")
        islands = []
        for sack in SACKS:
            for part in groups[sack["name"]]:
                vs = [bm.verts.new(v) for v in part.verts]
                faces = []
                for f, uvs, cls in zip(part.faces, part.uvs, part.cloth):
                    face = bm.faces.new([vs[i] for i in f])
                    face.material_index = part.mat
                    face.smooth = True
                    for loop, u, c in zip(face.loops, uvs, cls):
                        loop[uv].uv = u
                        loop[cloth].uv = c
                    faces.append(face)
                islands.append(faces)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        pack_uvs(bm, islands)
        if stray_vert:
            bm.verts.new((0.0, 0.0, 0.3))
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        me.update()
    finally:
        bm.free()
    uvl = me.uv_layers.get("UVMap")
    if uvl is not None:
        me.uv_layers.active = uvl
    paint_sacks(me)
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def paint_sacks(me):
    """``SackTone`` and ``Stripe`` face attributes from each sack's parameters."""
    tone = [0.5] * len(me.polygons)
    stripe = [0.0] * len(me.polygons)
    owner = {}
    # Each body takes the parameters of the sack placed nearest its centre;
    # a tie keeps the neutral values, which the twine shader ignores.
    for g in shells(me):
        if len(g) <= 400:
            continue
        c = sum((me.vertices[i].co for i in g), Vector()) / len(g)
        sack = min(SACKS, key=lambda s: (s["at"][0] - c.x) ** 2 + (s["at"][1] - c.y) ** 2)
        for i in g:
            owner[i] = (sack["tone"], float(sack["stripe"]))
    for p in me.polygons:
        t, s = owner.get(p.vertices[0], (0.5, 0.0))
        tone[p.index] = t
        stripe[p.index] = s
    a = me.attributes.new("SackTone", "FLOAT", "FACE")
    a.data.foreach_set("value", tone)
    b = me.attributes.new("Stripe", "FLOAT", "FACE")
    b.data.foreach_set("value", stripe)


# --- surface ----------------------------------------------------------------


def _sock(sockets, identifier):
    return next(sk for sk in sockets if sk.identifier == identifier)


def burlap_material(name):
    """Hessian: a weave on the cloth's own coordinates, stripes, dust at the base."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    co = nt.nodes.new("ShaderNodeUVMap")
    co.uv_map = "ClothCo"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(co.outputs["UV"], sep.inputs["Vector"])
    # Weave: two perpendicular sine gratings on the cloth coordinates.
    weave = []
    for axis in ("X", "Y"):
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = 2.0 * math.pi / WEAVE
        nt.links.new(sep.outputs[axis], mul.inputs[0])
        sn = nt.nodes.new("ShaderNodeMath")
        sn.operation = "SINE"
        nt.links.new(mul.outputs["Value"], sn.inputs[0])
        weave.append(sn)
    prod = nt.nodes.new("ShaderNodeMath")
    prod.operation = "MULTIPLY"
    nt.links.new(weave[0].outputs["Value"], prod.inputs[0])
    nt.links.new(weave[1].outputs["Value"], prod.inputs[1])
    wv = nt.nodes.new("ShaderNodeMapRange")
    wv.inputs["From Min"].default_value = -1.0
    wv.inputs["To Min"].default_value = 0.90
    wv.inputs["To Max"].default_value = 1.04
    nt.links.new(prod.outputs["Value"], wv.inputs["Value"])
    # Fibre mottling in object space.
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 9.0
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.30, 0.22, 0.13, 1.0)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.52, 0.41, 0.26, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    # Stripes down the front: Stripe 1 is one broad blue band, 2 is three
    # thin red ones, 0 is plain. Centred on the cloth's front (u = 1/4 turn).
    stripe = nt.nodes.new("ShaderNodeAttribute")
    stripe.attribute_type = "GEOMETRY"
    stripe.attribute_name = "Stripe"
    circ_u = nt.nodes.new("ShaderNodeMath")
    circ_u.operation = "PINGPONG"
    circ_u.inputs[1].default_value = 0.09
    shifted = nt.nodes.new("ShaderNodeMath")
    shifted.operation = "SUBTRACT"
    shifted.inputs[1].default_value = 0.0
    nt.links.new(sep.outputs["X"], shifted.inputs[0])
    absu = nt.nodes.new("ShaderNodeMath")
    absu.operation = "ABSOLUTE"
    nt.links.new(shifted.outputs["Value"], absu.inputs[0])
    nt.links.new(absu.outputs["Value"], circ_u.inputs[0])
    broad = nt.nodes.new("ShaderNodeMath")
    broad.operation = "LESS_THAN"
    broad.inputs[1].default_value = 0.028
    nt.links.new(absu.outputs["Value"], broad.inputs[0])
    thin = nt.nodes.new("ShaderNodeMath")
    thin.operation = "LESS_THAN"
    thin.inputs[1].default_value = 0.010
    rep = nt.nodes.new("ShaderNodeMath")
    rep.operation = "PINGPONG"
    rep.inputs[1].default_value = 0.025
    nt.links.new(absu.outputs["Value"], rep.inputs[0])
    nt.links.new(rep.outputs["Value"], thin.inputs[0])
    within = nt.nodes.new("ShaderNodeMath")
    within.operation = "LESS_THAN"
    within.inputs[1].default_value = 0.07
    nt.links.new(absu.outputs["Value"], within.inputs[0])
    thin_m = nt.nodes.new("ShaderNodeMath")
    thin_m.operation = "MULTIPLY"
    nt.links.new(thin.outputs["Value"], thin_m.inputs[0])
    nt.links.new(within.outputs["Value"], thin_m.inputs[1])
    is1 = nt.nodes.new("ShaderNodeMath")
    is1.operation = "COMPARE"
    is1.inputs[1].default_value = 1.0
    is1.inputs[2].default_value = 0.1
    nt.links.new(stripe.outputs["Fac"], is1.inputs[0])
    is2 = nt.nodes.new("ShaderNodeMath")
    is2.operation = "COMPARE"
    is2.inputs[1].default_value = 2.0
    is2.inputs[2].default_value = 0.1
    nt.links.new(stripe.outputs["Fac"], is2.inputs[0])
    m1 = nt.nodes.new("ShaderNodeMath")
    m1.operation = "MULTIPLY"
    nt.links.new(is1.outputs["Value"], m1.inputs[0])
    nt.links.new(broad.outputs["Value"], m1.inputs[1])
    m2 = nt.nodes.new("ShaderNodeMath")
    m2.operation = "MULTIPLY"
    nt.links.new(is2.outputs["Value"], m2.inputs[0])
    nt.links.new(thin_m.outputs["Value"], m2.inputs[1])
    # Stripes stop short of the neck and of the settled base.
    band_lo = nt.nodes.new("ShaderNodeMath")
    band_lo.operation = "GREATER_THAN"
    band_lo.inputs[1].default_value = 0.10
    nt.links.new(sep.outputs["Y"], band_lo.inputs[0])
    band_hi = nt.nodes.new("ShaderNodeMath")
    band_hi.operation = "LESS_THAN"
    band_hi.inputs[1].default_value = 0.44
    nt.links.new(sep.outputs["Y"], band_hi.inputs[0])
    band = nt.nodes.new("ShaderNodeMath")
    band.operation = "MULTIPLY"
    nt.links.new(band_lo.outputs["Value"], band.inputs[0])
    nt.links.new(band_hi.outputs["Value"], band.inputs[1])
    col1 = nt.nodes.new("ShaderNodeMix")
    col1.data_type = "RGBA"
    nt.links.new(ramp.outputs["Color"], _sock(col1.inputs, "A_Color"))
    _sock(col1.inputs, "B_Color").default_value = (0.07, 0.12, 0.26, 1.0)
    f1 = nt.nodes.new("ShaderNodeMath")
    f1.operation = "MULTIPLY"
    nt.links.new(m1.outputs["Value"], f1.inputs[0])
    nt.links.new(band.outputs["Value"], f1.inputs[1])
    nt.links.new(f1.outputs["Value"], _sock(col1.inputs, "Factor_Float"))
    col2 = nt.nodes.new("ShaderNodeMix")
    col2.data_type = "RGBA"
    nt.links.new(_sock(col1.outputs, "Result_Color"), _sock(col2.inputs, "A_Color"))
    _sock(col2.inputs, "B_Color").default_value = (0.30, 0.06, 0.04, 1.0)
    f2 = nt.nodes.new("ShaderNodeMath")
    f2.operation = "MULTIPLY"
    nt.links.new(m2.outputs["Value"], f2.inputs[0])
    nt.links.new(band.outputs["Value"], f2.inputs[1])
    nt.links.new(f2.outputs["Value"], _sock(col2.inputs, "Factor_Float"))
    # Per-sack tone and the weave.
    tone = nt.nodes.new("ShaderNodeAttribute")
    tone.attribute_type = "GEOMETRY"
    tone.attribute_name = "SackTone"
    gain = nt.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 0.8
    gain.inputs[2].default_value = 0.6
    nt.links.new(tone.outputs["Fac"], gain.inputs[0])
    g2 = nt.nodes.new("ShaderNodeMath")
    g2.operation = "MULTIPLY"
    nt.links.new(gain.outputs["Value"], g2.inputs[0])
    nt.links.new(wv.outputs["Result"], g2.inputs[1])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    _sock(mix.inputs, "Factor_Float").default_value = 1.0
    nt.links.new(_sock(col2.outputs, "Result_Color"), _sock(mix.inputs, "A_Color"))
    nt.links.new(g2.outputs["Value"], _sock(mix.inputs, "B_Color"))
    nt.links.new(_sock(mix.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.92
    bmp = nt.nodes.new("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = 0.15
    bmp.inputs["Distance"].default_value = 0.0015
    nt.links.new(prod.outputs["Value"], bmp.inputs["Height"])
    nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def twine_material(name):
    """Sisal twine: paler and yellower than the hessian, matte."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 120.0
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.40, 0.33, 0.18, 1.0)
    ramp.color_ramp.elements[1].color = (0.70, 0.60, 0.38, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    return mat


def sack_materials():
    return burlap_material("SackBurlap"), twine_material("SackTwine")


def assign_slots(obj, cloth, twine):
    mats = obj.data.materials
    for i, mat in enumerate((cloth, twine)):
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
    uv = mesh.uv_layers.get("UVMap")
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
    """Coplanar face pairs from *different shells* (copied from showcase/grindstone).

    Every sack lays a flat patch on the floor, so the budget is what keeps
    two sacks' patches from meeting on one plane side by side.
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


def shell_tree(me, group):
    member = set(group)
    polys = [list(p.vertices) for p in me.polygons if p.vertices[0] in member]
    remap = {v: k for k, v in enumerate(group)}
    return BVHTree.FromPolygons(
        [me.vertices[i].co.copy() for i in group],
        [[remap[i] for i in p] for p in polys],
    )


def _long_axis(pts):
    c = sum(pts, Vector()) / len(pts)
    cov = [[0.0] * 3 for _ in range(3)]
    for p in pts:
        d = p - c
        for i in range(3):
            for j in range(3):
                cov[i][j] += d[i] * d[j]
    v = Vector((0.3, 0.2, 1.0))
    for _ in range(60):
        w = Vector([sum(cov[i][j] * v[j] for j in range(3)) for i in range(3)])
        if w.length < 1e-12:
            break
        v = w.normalized()
    return c, v


def classify(me):
    """Bodies are the big cloth shells; each tie turn joins its nearest body."""
    mats = {}
    for p in me.polygons:
        for i in p.vertices:
            mats.setdefault(i, p.material_index)
    bodies, ties, other = [], [], []
    for g in shells(me):
        pts = [me.vertices[i].co.copy() for i in g]
        rec = {"g": g, "pts": pts, "c": sum(pts, Vector()) / len(pts)}
        m = mats.get(g[0], -1)
        if m == CLOTH_IDX and len(g) > 400:
            bodies.append(rec)
        elif m == TWINE_IDX:
            ties.append(rec)
        else:
            other.append(rec)
    for t in ties:
        t["body"] = min(range(len(bodies)),
                        key=lambda k: min((p - t["c"]).length for p in bodies[k]["pts"]))
    return bodies, ties, other


def sack_audit(me):
    """Supports, tie waist and seat, press, contact patch and belly, per sack."""
    bodies, ties, other = classify(me)
    trees = [shell_tree(me, b["g"]) for b in bodies]
    out = {"n_body": len(bodies), "n_tie": len(ties), "n_other": len(other)}
    out["support_worst"] = max((min(p.z for p in b["pts"]) for b in bodies), default=99.0)

    # Contact patch: faces lying flat on the floor under each body.
    patch = []
    for b in bodies:
        member = set(b["g"])
        area = 0.0
        for p in me.polygons:
            if p.vertices[0] in member and all(me.vertices[i].co.z <= 1e-6 for i in p.vertices):
                area += face_area(me, p)
        patch.append(area)
    out["patch"] = [round(a, 5) for a in patch]
    out["patch_min"] = min(patch, default=0.0)

    # Each body's axis, oriented from its base to its tie.
    waist, belly = [], []
    for k, b in enumerate(bodies):
        c, axis = _long_axis(b["pts"])
        own = [t for t in ties if t["body"] == k]
        if not own:
            waist.append(-99.0)
            continue
        tc = sum((t["c"] for t in own), Vector()) / len(own)
        if (tc - c).dot(axis) < 0.0:
            axis = -axis
        proj = [(p - c).dot(axis) for p in b["pts"]]
        lo, hi = min(proj), max(proj)
        bins = {}
        for p, s in zip(b["pts"], proj):
            r = ((p - c) - axis * s).length
            bins.setdefault(round(s / 0.004), []).append(r)
        stations = sorted((key * 0.004, sum(v) / len(v)) for key, v in bins.items() if len(v) >= 8)
        widest = max(stations, key=lambda x: x[1])
        belly.append((widest[0] - lo) / (hi - lo))
        # Waist: host radius at the tie's station against the host radius
        # WAIST_PROBE along the axis either side of it.
        st = (tc - c).dot(axis)

        def radius_at(s0):
            rs = [((p - c) - axis * s).length for p, s in zip(b["pts"], proj)
                  if abs(s - s0) <= WAIST_BAND]
            return sum(rs) / len(rs) if rs else 0.0

        waist.append(min(radius_at(st - WAIST_PROBE), radius_at(st + WAIST_PROBE))
                     - radius_at(st))
    out["waist"] = [round(x, 5) for x in waist]
    out["waist_min"] = min(waist, default=-99.0)
    out["belly_max"] = max(belly, default=99.0)
    out["belly"] = [round(x, 3) for x in belly]

    # Tie seat: deepest twine vertex inside its body, per turn.
    seats = [inside_depth(trees[t["body"]], t["pts"]) for t in ties]
    out["tie_min"] = min(seats, default=-99.0)
    out["tie_max"] = max(seats, default=99.0)

    # Press: each body's deepest vertex inside any other body.
    press = []
    for k, b in enumerate(bodies):
        best = max((inside_depth(trees[j], b["pts"]) for j in range(len(bodies)) if j != k),
                   default=-99.0)
        press.append(best)
    out["press"] = [round(x, 5) for x in press]
    out["press_min"] = min(press, default=-99.0)
    out["press_max"] = max(press, default=99.0)
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
    """Compound collider: one convex hull per sack body, every third ring, fourth column.

    One hull over the pile would fill the wedge between the lying sack and
    the standing ones; a hull per sack keeps it. Striding the rings keeps
    each hull's triangle count down without leaving the silhouette.
    """
    me = obj.data
    bodies, _ties, _other = classify(me)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for b in bodies:
            # Body vertices in build order are ring after ring of SEG, so
            # stride rings and columns alike.
            order = sorted(b["g"])
            pts = [me.vertices[v].co.copy() for k, v in enumerate(order)
                   if (k // SEG) % COLLIDER_STRIDE == 0 and (k % SEG) % 4 == 0]
            tmp = bmesh.new()
            try:
                vs = [tmp.verts.new(p) for p in pts]
                bmesh.ops.convex_hull(tmp, input=vs)
                # Only the hull's own vertices: interior points have no face.
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
    img = bpy.data.images.new("SackNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = CLOTH_IDX
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
        uv_layer="UVMap",
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


def check(skip_decimate, lift_z=False, stray_vert=False, **flags):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    nothing = (None,) * 5
    low = build_sacks_mesh("SacksLow", stray_vert=stray_vert, **flags)
    high = build_sacks_mesh("SacksHigh", **flags)
    cloth, twine = sack_materials()
    assign_slots(low, cloth, twine)
    assign_slots(high, cloth, twine)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
        bpy.context.view_layer.update()
    if len(low.data.polygons) < 6 or low.data.uv_layers.get("UVMap") is None:
        return (fail("sack mesh did not build, or has no UV layer", 3),) + nothing

    base_tris = triangle_count(low.data)
    mats = [s for s in low.data.materials if s is not None]
    nmat, distinct = len(mats), len({id(s) for s in mats})
    idx_counts = {}
    for poly in low.data.polygons:
        idx_counts[poly.material_index] = idx_counts.get(poly.material_index, 0) + 1
    u0, v0, u1, v1, overlap, nfaces = uv_stats(low.data)
    bb = world_bbox(low)
    size_x, size_y, size_z = bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]

    img, tex = setup_bake_image(low, cloth, BAKE_RES)
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "SacksLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "SacksLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider = hull_collider(high, "SacksCollider")
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(tempfile.gettempdir(), f"bdt_grain_sacks_{os.getpid()}.glb")
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
    sa = sack_audit(low.data)

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
    print(f"measured sacks bodies={sa['n_body']} ties={sa['n_tie']} other={sa['n_other']} "
          f"support_worst={sa['support_worst']:.5f} waist={sa['waist']} "
          f"tie=({sa['tie_min']:.5f},{sa['tie_max']:.5f}) press={sa['press']} "
          f"patch={sa['patch']} belly={sa['belly']}")

    if not (BASE_TRIS_MIN <= base_tris <= BASE_TRIS_MAX):
        return (fail(f"base tris {base_tris} not in [{BASE_TRIS_MIN}, {BASE_TRIS_MAX}]", 4),) + nothing
    if nmat != MATERIAL_COUNT or distinct != MATERIAL_COUNT:
        return (fail(f"material slots {nmat} distinct {distinct} != {MATERIAL_COUNT}", 5),) + nothing
    if idx_counts.get(CLOTH_IDX, 0) < CLOTH_FACES_MIN:
        return (fail(f"cloth faces {idx_counts.get(CLOTH_IDX, 0)} < {CLOTH_FACES_MIN}", 5),) + nothing
    if idx_counts.get(TWINE_IDX, 0) < TWINE_FACES_MIN:
        return (fail(f"twine faces {idx_counts.get(TWINE_IDX, 0)} < {TWINE_FACES_MIN}", 5),) + nothing
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
    if sa["n_body"] != len(SACKS) or sa["support_worst"] > SUPPORT_Z_MAX:
        return (fail(f"supports: {sa['n_body']} of {len(SACKS)} sacks, worst base z="
                     f"{sa['support_worst']:.5f} > {SUPPORT_Z_MAX} "
                     "(--float-sack is the designed fail)", 16),) + nothing
    if sa["n_tie"] != 2 * len(SACKS) or sa["waist_min"] < WAIST_MARGIN:
        return (fail(f"ties: {sa['n_tie']} turns; host under the tie narrower than "
                     f"{WAIST_PROBE} m either side by {sa['waist']}, need >= {WAIST_MARGIN} "
                     "(--slip-tie is the designed fail)", 17),) + nothing
    if sa["tie_min"] < TIE_SEAT_MIN or sa["tie_max"] > TIE_SEAT_MAX:
        return (fail(f"tie seat ({sa['tie_min']:.5f}, {sa['tie_max']:.5f}) outside "
                     f"[{TIE_SEAT_MIN}, {TIE_SEAT_MAX}] (--loose-tie is the designed fail)", 18),) + nothing
    if sa["press_min"] < PRESS_MIN or sa["press_max"] > PRESS_MAX:
        return (fail(f"press between sacks {sa['press']} outside [{PRESS_MIN}, {PRESS_MAX}] "
                     "(--part-sacks is the designed fail)", 18),) + nothing
    if sa["patch_min"] < PATCH_MIN:
        return (fail(f"contact patch {sa['patch']} m^2, smallest < {PATCH_MIN} "
                     "(--round-bottom is the designed fail)", 19),) + nothing
    if sa["belly_max"] > BELLY_MAX:
        return (fail(f"widest station at {sa['belly']} of the body > {BELLY_MAX} "
                     "(--high-belly is the designed fail)", 19),) + nothing
    return 0, low, high, cloth, tex, collider


def wire_normal(mat, tex):
    """Baked normal map under the weave bump."""
    nt = mat.node_tree
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    bump = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBump")
    nt.links.new(nrm.outputs["Normal"], bump.inputs["Normal"])


def render_still(low, cloth, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(cloth, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True
    # Level on the floor: turned about Z only.
    low.rotation_euler.z = math.radians(-10.0)

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

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", (-3.2, -4.2, 4.8), 480.0, 4.0, (1.0, 0.95, 0.88), (46, 0, -38))
    light("Fill", (4.2, -3.2, 2.2), 60.0, 8.0, (0.74, 0.84, 1.0), (66, 0, 52))
    light("Rim", (-2.0, 3.4, 2.8), 260.0, 3.0, (0.62, 0.78, 1.0), (-60, 0, 200))
    light("Wedge", (1.4, 3.8, 2.0), 520.0, 5.0, (1.0, 0.70, 0.38), (-94, 0, 194))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.22, -2.30, 1.18)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.02, -0.08, 0.30)
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
    p.add_argument("--float-sack", action="store_true")
    p.add_argument("--slip-tie", action="store_true")
    p.add_argument("--loose-tie", action="store_true")
    p.add_argument("--part-sacks", action="store_true")
    p.add_argument("--round-bottom", action="store_true")
    p.add_argument("--high-belly", action="store_true")
    args = p.parse_args(argv)

    code, low, _high, cloth, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_sack=args.float_sack,
        slip_tie=args.slip_tie,
        loose_tie=args.loose_tie,
        part_sacks=args.part_sacks,
        round_bottom=args.round_bottom,
        high_belly=args.high_belly,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, cloth, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("grain-sacks OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
