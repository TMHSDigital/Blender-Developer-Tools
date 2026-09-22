"""Game-ready bound hay bale — a showcase piece, not an example.

Asserts budget conformance of a procedural straw bale after composing
shipped pipeline pieces: bmesh construction, UVs, two materials,
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

Budgets are declared below and recomputed from the generated result.
They are not API-contract witnesses. ``--skip-decimate`` skips the LOD
DECIMATE stage so the LOD-ratio budget fails. ``--lift-z`` raises the
mesh so the grounded-zmin hygiene budget fails.

No RNG. Construction is closed-form. DECIMATE COLLAPSE triangle counts
are not byte-identical across Blender versions — the LOD gate is a
ratio band, not an exact count.

    blender --background --python hay_bale.py --
    blender --background --python hay_bale.py -- --skip-decimate
    blender --background --python hay_bale.py -- --lift-z
    blender --background --python hay_bale.py -- --output bale.png
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

# Showcase lives at repo-root/showcase/, not under examples/. The framing
# helper is the repo's only shared import and lives next to the examples;
# resolve the repo root so we do not move gallery_framing.py.
_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir)
)
sys.path.insert(0, os.path.join(_REPO, "examples"))
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

BALE_X = 0.90
BALE_Y = 0.48
BALE_Z = 0.38
TWINE_T = 0.016
TWINE_W = 0.024
TWINE_EMBED = 0.004
BELT_XS = (-0.225, 0.225)
LOAF_CUTS = 8
# The high mesh carries the straw; the bake moves it onto the low mesh. A
# low mesh dense enough to model flakes directly would cost thousands of
# triangles for detail this piece already has a bake stage to deliver.
LOAF_CUTS_HIGH = 20
FLAKE_W = 0.075
FLAKE_AMP = 0.011
BULGE = 0.055
RIDGE_AMP = 0.014
BBOX_TOL = 0.01
# Fitted after locking geometry. Recomputed from bound_box.
OUTER_SIZE = (0.922, 0.530, 0.409)

# The belt follows the loaf's own cross-section, sampled by raycast, instead
# of being a constant rectangle: a rectangle stands proud at the middle of
# each face and is swallowed at the corners of a bulged loaf.
BELT_SEGS = 20
CINCH = 0.030          # fraction the loaf narrows under each belt
CINCH_SIGMA = 0.075    # metres; how far the waist spreads either side
NAP_AMP = 0.012        # end-grain bite, up from 0.010
BASE_FLATTEN = 0.90    # how much of the pillow bulge gravity removes at z=0

BASE_TRIS_MIN = 1700
BASE_TRIS_MAX = 2400
ZMIN_EPS = 1e-4
DOUBLES_EPS = 1e-5
AREA_EPS = 1e-10
GAP_MAX = 0.008
LIFT_Z = 0.05
LOD1_RATIO_MIN = 0.32
LOD1_RATIO_MAX = 0.62
LOD2_RATIO_MIN = 0.10
LOD2_RATIO_MAX = 0.35
LOD1_TARGET = 0.50
LOD2_TARGET = 0.22
MATERIAL_COUNT = 2
UV_EPS = 1e-4
UV_OVERLAP_MAX = 1e-5
COLLIDER_TRIS_MAX = 400
BAKE_RES = 256
CAGE_EXTRUSION = 0.04
HAY_FACES_MIN = 24
TWINE_FACES_MIN = 24

# --- hygiene family, 15..19 -------------------------------------------------
# Coplanar disjoint face pairs: count only faces that share NO vertex. The
# triangles of one flat cap are coplanar and close-centred by construction.
COPLANAR_NORMAL_EPS = 1e-4
COPLANAR_PLANE_EPS = 1e-4
COPLANAR_CENTRE_MAX = 0.05

# loaf + 2 belts + 2 hitch loops
SHELL_COUNT = 5

# Each belt is a closed loop that passes *under* the loaf. A belt that stops
# at the bottom edge leaves a visible notch while the loaf still grounds the
# AABB, so the AABB zmin gate cannot see it: assert per belt shell.
BELT_WRAP_ZMAX = 0.006

# Banded seat depth, sampled per angular station around the belt rather than
# as one global figure. A single figure passes while one side visibly gaps.
SEAT_MIN = 0.002
SEAT_MAX = 0.020
# How far past flush the bottom run is pressed, so the belt stays inside the
# Z=0 plane the bale is grounded on instead of poking through it.
BELT_UNDER_SINK = 0.0012
BELT_PRESS_H = 0.06

# The two belts are mirror images. The odd ridge term used to put them
# 5.4 mm out of step, which no budget could see.
MIRROR_EPS = 5e-4

# The cinch is what makes this a *bound* bale rather than a pillow, and it
# is the one feature no other budget here touches: measured as the loaf's
# half-width at a belt station against its half-width mid-span. Banded, so
# neither a straight flank nor a strangled one passes.
CINCH_MIN = 0.006
CINCH_MAX = 0.020
# Loaf length and height against the stated real-world bale. Y is left to
# the cinch budget above, since the pillow bulge dominates it.
LOAF_XZ = (0.922, 0.409)
LOAF_XZ_TOL = 0.02

FLOAT_BELT_Z = 0.02
SLACK_BELT = 0.010
SKEW_BELT_X = 0.004

HAY_IDX = 0
TWINE_IDX = 1


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


def add_rim(bm, loc, major, minor, mat_idx, euler=(0.0, 0.0, 0.0), n_major=12, n_minor=6):
    rings = []
    for i in range(n_major):
        u = i * (2.0 * math.pi / n_major)
        ring = []
        for j in range(n_minor):
            v = j * (2.0 * math.pi / n_minor)
            ring.append(bm.verts.new((
                (major + minor * math.cos(v)) * math.cos(u),
                (major + minor * math.cos(v)) * math.sin(u),
                minor * math.sin(v),
            )))
        rings.append(ring)
    bm.verts.ensure_lookup_table()
    for i in range(n_major):
        i2 = (i + 1) % n_major
        for j in range(n_minor):
            j2 = (j + 1) % n_minor
            face = bm.faces.new((rings[i][j], rings[i2][j], rings[i2][j2], rings[i][j2]))
            face.material_index = mat_idx
    verts = [v for ring in rings for v in ring]
    rot = Euler(euler).to_matrix()
    origin = Vector(loc)
    for v in verts:
        v.co = rot @ v.co + origin
    return verts


def loaf_profile(bvh, x, centre, segs):
    """Sample the loaf surface at station x, once per angular segment.

    Returns [(y, z)] in the YZ plane. Raycasting the built loaf — rather
    than evaluating the closed form — means the profile follows the bevel
    and any later change to the shaping function for free.
    """
    cy, cz = centre
    reach = max(BALE_X, BALE_Y, BALE_Z)
    pts = []
    for i in range(segs):
        a = i * (2.0 * math.pi / segs)
        d = Vector((0.0, math.cos(a), math.sin(a)))
        origin = Vector((x, cy, cz))
        # Cast inward from well outside: the outermost hit is the surface,
        # so a concave waist cannot return an interior face.
        far = origin + d * reach
        hit, _nrm, _idx, dist = bvh.ray_cast(far, -d, reach * 2.0)
        if hit is None:
            hit, _nrm, _idx, dist = bvh.ray_cast(origin, d, reach)
            if hit is None:
                raise RuntimeError(f"loaf profile miss at x={x} a={a}")
        pts.append((hit.y, hit.z))
    return pts


def add_belt_wrap(bm, x, profile, centre, t, w, embed, mat_idx):
    """Closed belt following `profile`, extruded along X. One manifold loop.

    The section is chamfered: a hard rectangle reads as masking tape at
    this scale, and every real edge catches a little light.
    """
    cy, cz = centre
    x0, x1 = x - w * 0.5, x + w * 0.5
    xm0, xm1 = x - w * 0.5 + t * 0.5, x + w * 0.5 - t * 0.5

    def offset(py, pz, d):
        vy, vz = py - cy, pz - cz
        n = math.hypot(vy, vz) or 1.0
        return (py + vy / n * d, pz + vz / n * d)

    def embed_at(_py, pz):
        """Deeper where the run passes near the ground.

        Keyed to the sampled point's own height, not to the ray angle: the
        loaf's whole bottom face sits at Z=0, so several stations either
        side of straight-down land on it, and an angle-keyed press leaves
        those poking a fraction of a millimetre through the floor.

        The load presses those runs flush and a little past flush, so the
        belt never breaks the Z=0 plane the bale is grounded on, while the
        top and side runs still stand proud enough to read.
        """
        press = max(0.0, 1.0 - pz / BELT_PRESS_H)
        return embed + (t + BELT_UNDER_SINK - embed) * press

    # inner surface sits `embed` inside the loaf; outer is `t` further out
    inner = [offset(py, pz, -embed_at(py, pz)) for py, pz in profile]
    outer = [offset(py, pz, -embed_at(py, pz) + t) for py, pz in profile]

    def ring(xc, pts):
        return [bm.verts.new((xc, p[0], p[1])) for p in pts]

    i0, i1 = ring(x0, inner), ring(x1, inner)
    o0, o1 = ring(xm0, outer), ring(xm1, outer)

    def quad(a, b, c, d):
        f = bm.faces.new((a, b, c, d))
        f.material_index = mat_idx
        return f

    n = len(profile)
    for k in range(n):
        m = (k + 1) % n
        quad(i0[k], i1[k], i1[m], i0[m])   # inner face, against the loaf
        quad(o0[k], o0[m], o1[m], o1[k])   # outer face
        quad(i0[k], i0[m], o0[m], o0[k])   # -X chamfer
        quad(i1[k], o1[k], o1[m], i1[m])   # +X chamfer


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
    zero_area = sum(1 for a in areas if a <= AREA_EPS)
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


def mesh_shells(me):
    """Vertex-index sets, one per edge-connected component.

    A multi-body prop is not one shell, so Euler characteristic 2 is the
    wrong contract for it; the shells are what the grounding, mirror and
    seat budgets below are each measured over.
    """
    adj = [[] for _ in range(len(me.vertices))]
    for e in me.edges:
        a, b = e.vertices
        adj[a].append(b)
        adj[b].append(a)
    seen, shells = set(), []
    for start in range(len(me.vertices)):
        if start in seen:
            continue
        stack, comp = [start], set()
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            stack.extend(n for n in adj[cur] if n not in comp)
        seen |= comp
        shells.append(comp)
    return shells


def shell_stats(me, comp):
    co = [me.vertices[i].co for i in comp]
    return {
        "n": len(comp),
        "xmin": min(c.x for c in co), "xmax": max(c.x for c in co),
        "ymin": min(c.y for c in co), "ymax": max(c.y for c in co),
        "zmin": min(c.z for c in co), "zmax": max(c.z for c in co),
    }


def coplanar_zfight_pairs(me, shells):
    """Coplanar face pairs from *different shells* — the z-fighting budget.

    Cross-shell, not merely share-no-vertex. Two quads two steps apart on
    one flat cap share no vertex and are coplanar and close-centred by
    construction; counting those makes the budget unsatisfiable rather
    than meaningful (96 pairs on this mesh, none of them a hazard).
    Z-fighting is two separate bodies landing on one plane, which is
    exactly a cross-shell pair.
    """
    owner = {}
    for si, comp in enumerate(shells):
        for vi in comp:
            owner[vi] = si
    faces = []
    for p in me.polygons:
        faces.append((p.normal.copy(), p.center.copy(),
                      owner.get(p.vertices[0], -1)))
    hits = 0
    for i in range(len(faces)):
        ni, ci, si = faces[i]
        for j in range(i + 1, len(faces)):
            nj, cj, sj = faces[j]
            if si == sj:
                continue
            if (ci - cj).length > COPLANAR_CENTRE_MAX:
                continue
            if abs(abs(ni.dot(nj)) - 1.0) > COPLANAR_NORMAL_EPS:
                continue
            if abs(ni.dot(cj - ci)) > COPLANAR_PLANE_EPS:
                continue
            hits += 1
    return hits


def belt_seat_depths(me, loaf_comp, belt_comp, station_x, segs):
    """Seat depth per angular station around one belt.

    Banded and per-station, not one global figure: a single number passes
    while one side of the wrap visibly gaps. The loaf surface is rebuilt
    from the loaf shell of the *generated* mesh, so nothing here restates
    a constant the builder set.
    """
    bm = bmesh.new()
    try:
        vmap = {}
        for i in loaf_comp:
            vmap[i] = bm.verts.new(me.vertices[i].co)
        bm.verts.ensure_lookup_table()
        for p in me.polygons:
            if all(vi in vmap for vi in p.vertices):
                try:
                    bm.faces.new([vmap[vi] for vi in p.vertices])
                except ValueError:
                    pass
        if not bm.faces:
            return []
        bvh = BVHTree.FromBMesh(bm)
    finally:
        pass
    zs = [me.vertices[i].co.z for i in loaf_comp]
    cz = 0.5 * (min(zs) + max(zs))
    buckets = {}
    for i in belt_comp:
        co = me.vertices[i].co
        a = math.atan2(co.z - cz, co.y)
        # Round to the NEAREST station, do not floor into a bin. A station
        # sitting on a bin boundary put its inner and outer rings in
        # different bins, and the inner-only bin then reported the wrap as
        # 12 mm outside the loaf — the outer ring's offset, exactly.
        k = int(round((a + math.pi) / (2.0 * math.pi) * segs)) % segs
        buckets.setdefault(k, []).append(co.copy())
    reach = max(BALE_X, BALE_Y, BALE_Z) * 2.0

    origin = Vector((station_x, 0.0, cz))

    def depth(co):
        """How far inside the station's own cross-section this point sits.

        Measured along the point's own direction from the station axis,
        NOT by nearest-surface distance. The belt lies in a concave waist,
        so the nearest loaf face to a belt vertex is often on the bulge
        shoulder 10 mm away at a neighbouring station, and the wrap then
        reads as sitting outside a loaf it is in fact hugging.
        """
        a = math.atan2(co.z - cz, co.y)
        d = Vector((0.0, math.cos(a), math.sin(a)))
        hit, _nrm, _idx, _dd = bvh.ray_cast(origin + d * reach, -d, reach * 2.0)
        if hit is None:
            return None
        return math.hypot(hit.y, hit.z - cz) - math.hypot(co.y, co.z - cz)

    depths = []
    for k in sorted(buckets):
        # Per station, the deepest-seated point of the wrap: the inner
        # ring. Picking the vertex nearest the belt axis instead looked
        # equivalent but is not — the rings are unevenly spaced in angle
        # once the bottom run is pressed in, so some buckets held only
        # outer-ring vertices and reported the belt 10 mm outside.
        vals = [d for d in (depth(co) for co in buckets[k]) if d is not None]
        if vals:
            depths.append(max(vals))
    bm.free()
    return depths


def min_mat_distance(me, ia, ib):
    """Closest surface distance between two material islands via BVH.

    Vert-vert distance is the wrong metric for a 4-corner strap: the inner
    face has no mid-edge verts, so a cinched belt still reports ~TWINE_W/2.
    """
    bm_a = bmesh.new()
    bm_b = bmesh.new()
    try:
        bm_a.from_mesh(me)
        bm_b.from_mesh(me)
        bm_a.faces.ensure_lookup_table()
        bm_b.faces.ensure_lookup_table()
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


def _cinch(x):
    """How much the loaf narrows at station x, from BELT_XS alone.

    Derived from the belt positions rather than hand-placed, so moving a
    belt moves its waist with it. A bound bale is defined by this waist;
    without it the belts lie on a straight flank and nothing reads as tied.
    """
    return CINCH * sum(
        math.exp(-((x - bx) / CINCH_SIGMA) ** 2) for bx in BELT_XS
    )


def _flake(x):
    """Deterministic per-band offset. A bale is stacked flakes, and the
    strata are what make it read as straw rather than as a carton.

    Keyed to abs(x) so the pattern is EVEN, like every other term here:
    an odd term puts the two belt stations on different surface heights.
    Closed-form hash, no RNG, identical on every binary.
    """
    band = math.floor(abs(x) / FLAKE_W)
    h = math.sin(band * 12.9898) * 43758.5453
    return (h - math.floor(h)) - 0.5


def _shape_loaf(verts, flake=False):
    hx = BALE_X * 0.5
    hy = BALE_Y * 0.5
    hz = BALE_Z * 0.5
    zc = BALE_Z * 0.5
    for v in verts:
        x, y, z = v.co.x, v.co.y, v.co.z
        nx = max(-1.0, min(1.0, x / hx))
        ny = max(-1.0, min(1.0, y / hy))
        nz = max(-1.0, min(1.0, (z - zc) / hz))
        # Pillow bulge, waisted under every belt station.
        pillow = (1.0 + BULGE * (1.0 - nx * nx)) * (1.0 - _cinch(x))
        # Gravity flattens the face the bale rests on: take the bulge out as
        # z falls to the base, so the bottom stays planar instead of doming
        # down and being clamped flat afterwards.
        grounded = 1.0 - BASE_FLATTEN * max(0.0, -nz) ** 2
        v.co.y = y * pillow
        v.co.z = zc + (z - zc) * (1.0 + (pillow - 1.0) * grounded)
        # Longitudinal straw ridges on the long faces. cos(), not sin(): the
        # term has to be EVEN in x or the two belt stations sample different
        # surface heights and the belts end up out of step.
        #
        # Faded out under each belt, because the twine compresses the straw
        # flat where it bites. Without this the ±14 mm ridge swamps the
        # waist: the cinch measured 2.2 mm and read as a crease rather than
        # as binding.
        press = 1.0 - _cinch(x) / CINCH
        v.co.y += RIDGE_AMP * math.cos(x * 24.0) * (0.35 + 0.65 * abs(ny)) * press
        v.co.z += (
            0.55 * RIDGE_AMP * math.cos(x * 19.0) * (0.35 + 0.65 * abs(nz))
            * grounded * press
        )
        if flake:
            f = _flake(x) * (0.35 + 0.65 * abs(ny))
            v.co.y += FLAKE_AMP * f
            v.co.z += FLAKE_AMP * 0.6 * _flake(x) * grounded
        # End-grain nap: bite the ±X faces instead of gluing on extra slabs.
        # Damped to nothing at the face border, because the bevel runs after
        # this: displacing the border verts turned the four corners into
        # flared spikes. The ripple is slow (7, not 14) — at 14 it aliased
        # against the subdivision grid and read as a checkerboard quilt.
        if abs(nx) > 0.82:
            # Strata in Z, not rings in r. A cut bale end shows the flake
            # layers edge-on; a concentric ripple is not what that looks
            # like, and at BAKE_RES it resolved into a pixelated bullseye
            # on the hero that read as a printed target.
            edge = 1.0 - min(1.0, max(abs(ny), abs(nz))) ** 3
            strata = math.sin((z / BALE_Z) * math.pi * 6.0)
            v.co.x += math.copysign(NAP_AMP * strata * edge, x)


def build_bale_mesh(name, bevel_offset, bevel_segments, cuts=LOAF_CUTS,
                    flake=False, slack_belt=False, float_belts=False,
                    skew_belt=False):
    bm = bmesh.new()
    hay_verts = []
    twine_faces = set()
    try:
        hay_verts.extend(
            add_box(
                bm,
                (0.0, 0.0, BALE_Z / 2.0),
                (BALE_X, BALE_Y, BALE_Z),
                HAY_IDX,
            )
        )
        bmesh.ops.subdivide_edges(
            bm,
            edges=list({e for v in hay_verts for e in v.link_edges}),
            cuts=cuts,
            use_grid_fill=True,
        )
        hay_verts = [v for v in bm.verts]
        _shape_loaf(hay_verts, flake=flake)
        if bevel_offset > 0.0:
            bm.edges.ensure_lookup_table()
            edges = []
            for e in bm.edges:
                if len(e.link_faces) != 2:
                    continue
                if e.calc_face_angle() > math.radians(50.0):
                    edges.append(e)
            if not edges:
                edges = list(bm.edges)
            bmesh.ops.bevel(
                bm,
                geom=edges,
                offset=bevel_offset,
                segments=bevel_segments,
                profile=0.45,
                affect="EDGES",
                clamp_overlap=True,
            )

        # Ground and centre the LOAF first, then hang the belts on the
        # finished surface. Placing them beforehand and shifting everything
        # afterwards left each belt a few millimetres off the floor by a
        # different amount, which is how they ended up out of step.
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zmin = min(v.co.z for v in bm.verts)
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        for v in bm.verts:
            v.co.x -= cx
            v.co.y -= cy
            v.co.z -= zmin

        # Sample the loaf's own cross-section at each belt station.
        loaf_bvh = BVHTree.FromBMesh(bm)
        zs = [v.co.z for v in bm.verts]
        centre = (0.0, 0.5 * (min(zs) + max(zs)))

        before = set(bm.faces)
        for x in BELT_XS:
            profile = loaf_profile(loaf_bvh, x, centre, BELT_SEGS)
            # --slack-belt backs one belt off the loaf so its seat depth
            # drops below SEAT_MIN on every station of that belt.
            embed = TWINE_EMBED - (SLACK_BELT if (slack_belt and x > 0) else 0.0)
            add_belt_wrap(
                bm, x, profile, centre, TWINE_T, TWINE_W, embed, TWINE_IDX,
            )
            # Hitch loop: the tail of the knot, lying flat on the bale top
            # alongside its belt. Standing it upright made a wire hoop that
            # broke the silhouette; laying it in XY reads as tied cord.
            top_z = max(pz for _py, pz in profile)
            add_rim(
                bm,
                # Offset outward from the centre, not along +X: a bare
                # `x + TWINE_W` put the two loops at -0.201 and +0.249.
                (x + math.copysign(TWINE_W, x), 0.052,
                 top_z - TWINE_EMBED + TWINE_T * 0.45),
                0.030,
                0.0062,
                TWINE_IDX,
                euler=(0.0, 0.0, 0.0),
                n_major=12,
                n_minor=6,
            )
        twine_faces.update(set(bm.faces) - before)

        if float_belts or skew_belt:
            # Move twine only. The loaf still grounds the AABB, so the
            # outer-zmin gate stays green and the per-shell gate has to
            # be the thing that fires.
            moved = {v for f in twine_faces for v in f.verts}
            for v in moved:
                if float_belts:
                    v.co.z += FLOAT_BELT_Z
                elif v.co.x > 0.0:
                    # Along X, not Z. A Z skew landed one belt face exactly
                    # coplanar with a loaf face and tripped the z-fight
                    # budget (exit 15) instead of the mirror budget it
                    # targets. An X shift leaves every other budget alone:
                    # the loaf profile barely changes over 4 mm, so the
                    # seat band still passes and only the mirror fires.
                    v.co.x += SKEW_BELT_X

        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=DOUBLES_EPS)

        pack_uvs(bm)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        # Shading is decided per part, not globally. Smooth-shading the
        # whole bale erased every ridge and nap in it and left a featureless
        # pillow that read as a bar of soap. Straw is a chunky matte mass:
        # the loaf is flat-shaded so its facets read as compressed flakes.
        # Twine is cord, so the belts and hitch loops stay smooth.
        live_twine = {f for f in twine_faces if f.is_valid}
        for face in bm.faces:
            face.smooth = face in live_twine
        for edge in bm.edges:
            edge.smooth = all(f in live_twine for f in edge.link_faces)
        for f in live_twine:
            f.material_index = TWINE_IDX
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


def assign_slots(obj, hay, twine):
    mats = obj.data.materials
    wanted = (hay, twine)
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
    img = bpy.data.images.new("HayBaleNrm", size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    nodes = target_mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    obj.active_material_index = HAY_IDX
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


def check(skip_decimate, lift_z=False, stray_vert=False, slack_belt=False,
          float_belts=False, skew_belt=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    low = build_bale_mesh(
        "BaleLow", bevel_offset=0.016, bevel_segments=2,
        slack_belt=slack_belt, float_belts=float_belts, skew_belt=skew_belt,
    )
    # The high mesh is where the straw lives: finer subdivision plus the
    # flake strata. bake_normal moves that detail onto the low mesh.
    high = build_bale_mesh(
        "BaleHigh", bevel_offset=0.016, bevel_segments=4,
        cuts=LOAF_CUTS_HIGH, flake=True,
    )
    hay = principled(
        "BaleHay",
        (0.66, 0.52, 0.18, 1.0),
        0.0,
        0.78,
        noise_scale=22.0,
        wear=(0.48, 0.36, 0.10, 1.0),
    )
    twine = principled(
        "BaleTwine",
        (0.22, 0.16, 0.08, 1.0),
        0.0,
        0.58,
        noise_scale=14.0,
        wear=(0.14, 0.10, 0.05, 1.0),
    )
    assign_slots(low, hay, twine)
    assign_slots(high, hay, twine)
    if lift_z:
        for v in low.data.vertices:
            v.co.z += LIFT_Z
        low.data.update()
    if stray_vert:
        bm = bmesh.new()
        bm.from_mesh(low.data)
        # Inside the existing AABB: a stray vertex parked above the bale
        # blew the bounding-box budget (exit 8) before the hygiene gate
        # could see it, so it proved nothing about hygiene.
        bm.verts.new((0.0, 0.0, BALE_Z * 0.5))
        bm.to_mesh(low.data)
        bm.free()
        low.data.update()

    if low.data is None or len(low.data.polygons) < 6:
        return fail("hay bale mesh did not build", 3), None, None, None, None, None

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

    img, tex = setup_bake_image(low, hay)
    if img is None:
        return fail("hay bale has no UV layer", 3), None, None, None, None, None
    bake_result = bake_normal(high, low)

    lod1 = make_lod(low, "BaleLOD1", LOD1_TARGET, skip_decimate)
    lod2 = make_lod(low, "BaleLOD2", LOD2_TARGET, skip_decimate)
    bpy.context.view_layer.update()
    lod1_tris = evaluated_triangle_count(lod1)
    lod2_tris = evaluated_triangle_count(lod2)
    r1 = lod1_tris / base_tris if base_tris else 0.0
    r2 = lod2_tris / base_tris if base_tris else 0.0

    collider_src = build_bale_mesh("BaleColSrc", bevel_offset=0.0, bevel_segments=1)
    collider = convex_hull_collider(collider_src, "BaleCollider")
    bpy.data.objects.remove(collider_src, do_unlink=True)
    col_tris = triangle_count(collider.data)

    export_path = os.path.join(
        tempfile.gettempdir(),
        f"bdt_hay_bale_{os.getpid()}.glb",
    )
    if os.path.exists(export_path):
        os.remove(export_path)
    export_unity(export_path, [low, collider])
    export_size = os.path.getsize(export_path) if os.path.isfile(export_path) else 0
    # Blender sets TMPDIR from its own preference, which resolves to the
    # working directory on a stock portable build — so gettempdir() is the
    # repo root under CI and every run left a .glb behind. The budget only
    # needs the byte count, so drop the file once it is measured.
    if os.path.isfile(export_path):
        try:
            os.remove(export_path)
        except OSError:
            pass

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
    hyg = hygiene_audit(low.data)
    zfight = 0  # recomputed below, once the shells are known
    gap = min_mat_distance(low.data, TWINE_IDX, HAY_IDX)

    # --- shells: loaf, two belts, two hitch loops ------------------------
    shells = mesh_shells(low.data)
    n_shells = len(shells)
    zfight = coplanar_zfight_pairs(low.data, shells)
    stats = [shell_stats(low.data, c) for c in shells]
    order = sorted(range(len(shells)), key=lambda i: stats[i]["n"])
    loaf_i = order[-1]
    loaf_comp = shells[loaf_i]
    core_x = stats[loaf_i]["xmax"] - stats[loaf_i]["xmin"]
    core_y = stats[loaf_i]["ymax"] - stats[loaf_i]["ymin"]
    core_z = stats[loaf_i]["zmax"] - stats[loaf_i]["zmin"]

    # A belt is a non-loaf shell that spans most of the loaf's height; a
    # hitch loop sits on the top run and spans almost none of it.
    belt_shells, loop_shells = [], []
    for i, st in enumerate(stats):
        if i == loaf_i:
            continue
        bx = 0.5 * (st["xmin"] + st["xmax"])
        span = st["zmax"] - st["zmin"]
        (belt_shells if span > core_z * 0.5 else loop_shells).append((bx, st))
    belt_shells.sort(key=lambda t: t[0])
    loop_shells.sort(key=lambda t: t[0])

    # --- mirror symmetry -------------------------------------------------
    # The two wraps are mirror images. An odd term in the shaping function
    # used to put them 5.4 mm out of step and no budget could see it.
    def mirror_error(pairs):
        if len(pairs) != 2:
            return float("inf")
        (xa, a), (xb, b) = pairs
        return max(
            abs(xa + xb),
            abs(a["zmin"] - b["zmin"]),
            abs(a["zmax"] - b["zmax"]),
            abs((a["ymax"] - a["ymin"]) - (b["ymax"] - b["ymin"])),
        )

    mirror_err = max(mirror_error(belt_shells), mirror_error(loop_shells))

    # --- banded seat depth, per angular station --------------------------
    seat_depths = []
    for bx, st in belt_shells:
        comp = next(
            c for i, c in enumerate(shells)
            if i != loaf_i and abs(0.5 * (stats[i]["xmin"] + stats[i]["xmax"]) - bx) < 1e-9
            and (stats[i]["zmax"] - stats[i]["zmin"]) > core_z * 0.5
        )
        seat_depths.append((bx, belt_seat_depths(
            low.data, loaf_comp, comp, bx, BELT_SEGS)))

    # --- cinch depth: the waist the belts pull into the loaf -------------
    def half_y_at(x0, half_window):
        ys = [
            abs(low.data.vertices[i].co.y)
            for i in loaf_comp
            if abs(low.data.vertices[i].co.x - x0) <= half_window
            and 0.30 * core_z <= low.data.vertices[i].co.z <= 0.70 * core_z
        ]
        return max(ys) if ys else 0.0

    win = 0.5 * (BALE_X / (LOAF_CUTS + 1))
    waist = min(half_y_at(bx, win) for bx in BELT_XS)
    midspan = half_y_at(0.0, win)
    cinch_depth = midspan - waist

    print(
        f"measured shells={n_shells} loaf=({core_x:.4f},{core_y:.4f},{core_z:.4f}) "
        f"mirror_err={mirror_err:.6f} zfight={zfight}"
    )
    print(
        f"measured cinch waist={waist:.5f} midspan={midspan:.5f} "
        f"depth={cinch_depth:.5f}"
    )
    for bx, st in belt_shells:
        print(f"measured belt x={bx:+.4f} zmin={st['zmin']:.6f}")
    for bx, d in seat_depths:
        if d:
            print(f"measured seat x={bx:+.4f} n={len(d)} "
                  f"min={min(d):.5f} max={max(d):.5f}")
    print(
        f"measured collider_tris={col_tris} bake={bake_result} "
        f"bake_has_data={img.has_data} export_bytes={export_size}"
    )
    print(
        f"measured hygiene loose_v={hyg['loose_v']} loose_e={hyg['loose_e']} "
        f"nonman={hyg['nonman']} zero_area={hyg['zero_area']} "
        f"doubles={hyg['doubles']} ngons={hyg['ngons']} euler={hyg['euler']}"
    )
    print(f"measured hay_twine_gap={gap:.5f} zmin={bb[2]:.6f}")

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
    if idx_counts.get(HAY_IDX, 0) < HAY_FACES_MIN:
        return fail(
            f"hay faces {idx_counts.get(HAY_IDX, 0)} < {HAY_FACES_MIN}",
            5,
        ), None, None, None, None, None
    if idx_counts.get(TWINE_IDX, 0) < TWINE_FACES_MIN:
        return fail(
            f"twine faces {idx_counts.get(TWINE_IDX, 0)} < {TWINE_FACES_MIN}",
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
    # The AABB gate above cannot see a belt that stops at the bottom edge:
    # the loaf still grounds the box. Assert each belt loop passes UNDER
    # the loaf, which is what a bound bale's twine does.
    for bx, st in belt_shells:
        if st["zmin"] > BELT_WRAP_ZMAX:
            return fail(
                f"belt at x={bx:+.3f} zmin {st['zmin']:.6f} > {BELT_WRAP_ZMAX} "
                "— the loop stops at the bottom edge instead of wrapping "
                "under (--float-belts is the designed fail)",
                16,
            ), None, None, None, None, None
    if n_shells != SHELL_COUNT:
        return fail(
            f"shell count {n_shells} != {SHELL_COUNT}",
            17,
        ), None, None, None, None, None
    if gap > GAP_MAX:
        return fail(
            f"hay-twine gap {gap:.5f} > {GAP_MAX} (twine must cinch the loaf)",
            17,
        ), None, None, None, None, None
    for bx, depths in seat_depths:
        if not depths:
            return fail(f"belt at x={bx:+.3f} sampled no seat station", 18), \
                None, None, None, None, None
        lo, hi = min(depths), max(depths)
        if lo < SEAT_MIN or hi > SEAT_MAX:
            return fail(
                f"belt at x={bx:+.3f} seat depth {lo:.5f}..{hi:.5f} outside "
                f"[{SEAT_MIN}, {SEAT_MAX}] over {len(depths)} stations "
                "(--slack-belt is the designed fail)",
                18,
            ), None, None, None, None, None
    if mirror_err > MIRROR_EPS:
        return fail(
            f"belts out of step by {mirror_err:.6f} > {MIRROR_EPS} — the two "
            "wraps are not mirror images (--skew-belt is the designed fail)",
            19,
        ), None, None, None, None, None
    if not (CINCH_MIN <= cinch_depth <= CINCH_MAX):
        return fail(
            f"cinch depth {cinch_depth:.5f} outside [{CINCH_MIN}, {CINCH_MAX}] "
            "— the belts lie on a straight flank, so nothing reads as bound",
            19,
        ), None, None, None, None, None
    if (
        abs(core_x - LOAF_XZ[0]) > LOAF_XZ_TOL
        or abs(core_z - LOAF_XZ[1]) > LOAF_XZ_TOL
    ):
        return fail(
            f"loaf ({core_x:.4f} x {core_z:.4f}) off the stated "
            f"{LOAF_XZ} m bale",
            19,
        ), None, None, None, None, None
    return 0, low, high, hay, tex, collider


def wire_normal(mat, tex):
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    nrm = nt.nodes.new("ShaderNodeNormalMap")
    nrm.inputs["Strength"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], nrm.inputs["Color"])
    nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def render_still(low, hay, tex, path, engine):
    scene = bpy.context.scene
    wire_normal(hay, tex)
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    # A bale is identified by its long ribbed flank and the two belts
    # crossing it, not by its end. -32 deg swung the end face at the lens
    # and it dominated the frame.
    low.rotation_euler.z = math.radians(-20.0)

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
    # Wedge brought in and down with the camera. Pulling the lens back to
    # 70 mm left the warm pool falling outside the frame, and the first
    # contact sheet showed a neutral grey stage against a calibration set
    # that all carry one.
    light("Wedge", (1.5, 2.6, 2.1), 900.0, 4.0, (1.0, 0.63, 0.32), (-62, 0, 205))

    cam_data = bpy.data.cameras.new("Cam")
    # 70 mm from further back rather than 50 mm up close: at 2.1 m a 50 mm
    # lens put enough perspective on a 0.92 m subject that the near end
    # read half again as large as the far one.
    cam_data.lens = 70.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.74, -2.28, 1.16)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.15)
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
        "--float-belts",
        action="store_true",
        help="falsification: lift the belts off the floor so the per-belt "
             "wrap budget fails while the loaf still grounds the AABB",
    )
    p.add_argument(
        "--slack-belt",
        action="store_true",
        help="falsification: back one belt off the loaf so its banded seat "
             "depth falls below the minimum",
    )
    p.add_argument(
        "--skew-belt",
        action="store_true",
        help="falsification: raise one belt so the two wraps stop being "
             "mirror images",
    )
    args = p.parse_args(argv)

    code, low, _high, hay, tex, _col = check(
        args.skip_decimate,
        lift_z=args.lift_z,
        stray_vert=args.stray_vert,
        float_belts=args.float_belts,
        slack_belt=args.slack_belt,
        skew_belt=args.skew_belt,
    )
    if code:
        return code
    if args.output:
        rcode = render_still(low, hay, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    print("hay-bale OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
