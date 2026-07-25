"""Vertex-colour AO — cheap baked occlusion in a colour attribute.

Engines that read vertex colour get their contact shadows for free if the
asset ships with ambient occlusion baked into a colour attribute. The bake is
a hemisphere visibility integral, and unlike most bakes it has *analytic*
answers: for an unoccluded flat surface the integral is exactly 1, and for a
point on the floor a distance ``d`` from an infinitely wide wall of height
``H`` the cosine-weighted occluded fraction is

    A(k) = 0.5 * (1 - 1 / sqrt(1 + k^2)),    k = H / d
    AO   = 1 - A(k)

derived by integrating the cosine-weighted hemisphere measure over the
directions the wall blocks (the phi integral collapses to
``pi / sqrt(1 + k^2)``). Note AO(k) depends only on the *ratio* H/d, and
darkens monotonically as the point approaches the wall — so the bake can be
checked against a formula rather than against a previous run's numbers.

The asset is a stone village well. The same integrator that is validated
against the closed form above is run over its geometry, so what ships in the
attribute is the thing the check measured.

Two storage traps are asserted rather than described:

* ``FLOAT_COLOR`` round-trips a linear value exactly (1.4e-08 here).
* ``BYTE_COLOR`` does NOT store linear 8-bit — it stores **sRGB-encoded**
  8-bit. Writing 0.735 reads back 0.7379107, and the round-trip error peaks
  at 2.9e-03, an order of magnitude worse than a naive 1/255 = 3.9e-03
  uniform-quantisation model would predict *in the shadows* and much better
  in the darks. The check reproduces the readback with an independent
  sRGB encode/quantise/decode model. An exporter that hands raw bytes to an
  engine expecting linear occlusion ships wrong shadows.

Check (all closed form or independently re-derived, nothing captured):

1. Analytic AO (exit 3): the integrator matches ``1 - A(H/d)`` at six probe
   distances spanning two decades of H/d.
2. Unoccluded and monotone (exit 4): an isolated flat plate bakes to exactly
   1.0 everywhere; along the calibration ruler AO increases strictly with
   distance from the wall.
3. Range (exit 5): every baked value on the asset lies in [0, 1], and the
   asset actually uses its range (crevices darker than exposed faces by a
   measured margin — a bake that silently produced a constant would pass a
   bare range check).
4. Storage round-trip (exit 6): FLOAT_COLOR exact, BYTE_COLOR matching the
   independent sRGB quantisation model to within 1e-6.
5. Depsgraph survival (exit 7): both attributes read back off the evaluated
   mesh with deviation exactly 0, keeping data_type and domain.
6. Reuse hygiene (exit 8): identity scales, ``Well.Stone.*`` names, no
   default datablocks, the asset resting on z == 0.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python vertex_color_ao.py --                   # check
    blender --background --python vertex_color_ao.py -- --output well.png # + render
    blender --background --python vertex_color_ao.py -- --falsify flat.png
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

AO_ATTR = "AO"             # FLOAT_COLOR / POINT — the linear, exact channel
AO_BYTE_ATTR = "AOByte"    # BYTE_COLOR / POINT — the sRGB-quantised channel

# Bake sample counts. The calibration rig gets a heavy count because it is
# only six points and it is being held to a formula; the asset gets a cheap
# count because what is asserted there is range, spread and survival.
CAL_SAMPLES = 4096
ASSET_SAMPLES = 64

# Quasi-Monte-Carlo convergence on the calibration rig is ~1/sqrt(n): the
# measured worst error at 4096 samples is 6.8e-04, so 2.5e-03 is roughly a
# 3.5x margin. Tightening it below ~1e-3 would make the gate a sampling-noise
# detector rather than a correctness check.
CAL_TOL = 2.5e-03
WALL_H = 3.0               # calibration wall height, metres
WALL_HALF_W = 400.0        # half width: wide enough that truncation < 1e-4
CAL_DISTANCES = (0.05, 0.2, 0.5, 1.0, 2.0, 5.0)
RAY_EPS = 1e-5             # offset along the normal so a ray cannot self-hit
RAY_FAR = 1.0e4

FLOAT_TOL = 1e-6           # FLOAT_COLOR round-trip (measured 1.43e-08)
BYTE_MODEL_TOL = 1e-6      # agreement with the independent sRGB model
SPREAD_MIN = 0.25          # the asset must actually use its AO range
EXPECT_PARTS = 11          # asserted before any per-part loop runs (check 0)


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


# ---------------------------------------------------------------------------
# The AO integrator
# ---------------------------------------------------------------------------

def hemisphere_dirs(n):
    """Deterministic cosine-weighted hemisphere directions about +Z.

    A Fibonacci lattice on the unit disc lifted to the hemisphere: sampling
    the disc uniformly in area and projecting up gives exactly the cosine
    weighting the AO integral needs, with no RNG — the same n directions
    every run, on every machine, on both Blender versions.
    """
    golden = math.pi * (3.0 - math.sqrt(5.0))
    dirs = []
    for i in range(n):
        r = math.sqrt((i + 0.5) / n)
        phi = i * golden
        x, y = r * math.cos(phi), r * math.sin(phi)
        dirs.append(Vector((x, y, math.sqrt(max(0.0, 1.0 - r * r)))))
    return dirs


def frame_from_normal(nz):
    """An orthonormal frame with +Z along nz. Any tangent will do — the
    cosine-weighted set is rotationally symmetric about the normal."""
    nz = Vector(nz).normalized()
    ref = Vector((1.0, 0.0, 0.0)) if abs(nz.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    nx = (ref - nz * ref.dot(nz)).normalized()
    ny = nz.cross(nx)
    return Matrix((nx, ny, nz)).transposed()


def analytic_ao(height, dist):
    """Closed form for an infinitely wide wall of `height` at `dist`."""
    k = height / dist
    return 1.0 - 0.5 * (1.0 - 1.0 / math.sqrt(1.0 + k * k))


def bake_points(bvh, points, normals, n_samples):
    """AO at each (point, normal) against `bvh`. Returns a list of floats."""
    dirs = hemisphere_dirs(n_samples)
    inv_n = 1.0 / n_samples
    out = []
    for p, nrm in zip(points, normals):
        basis = frame_from_normal(nrm)
        origin = Vector(p) + Vector(nrm).normalized() * RAY_EPS
        blocked = 0
        for d in dirs:
            if bvh.ray_cast(origin, basis @ d, RAY_FAR)[0] is not None:
                blocked += 1
        out.append(1.0 - blocked * inv_n)
    return out


def world_bvh(objects):
    """One BVH over every object's world-space triangles."""
    bm = bmesh.new()
    try:
        for ob in objects:
            tmp = bm.__class__() if False else None  # keep one bmesh, transform in
            me = ob.data
            offset = len(bm.verts)
            bm.verts.ensure_lookup_table()
            new_verts = [bm.verts.new(ob.matrix_world @ v.co) for v in me.vertices]
            for poly in me.polygons:
                try:
                    bm.faces.new([new_verts[i] for i in poly.vertices])
                except ValueError:
                    pass          # duplicate face across overlapping parts
        bm.verts.ensure_lookup_table()
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        return BVHTree.FromBMesh(bm)
    finally:
        bm.free()


def bake_object_ao(bvh, ob, n_samples):
    """AO per vertex of `ob`, evaluated in world space against `bvh`."""
    me = ob.data
    mw = ob.matrix_world
    nrm3 = mw.to_3x3().inverted().transposed()
    pts = [mw @ v.co for v in me.vertices]
    nrms = [(nrm3 @ Vector(me.vertex_normals[i].vector)).normalized()
            for i in range(len(me.vertices))]
    return bake_points(bvh, pts, nrms, n_samples)


def write_ao_attributes(me, values, invert=False):
    """Write AO into a FLOAT_COLOR and a BYTE_COLOR attribute on POINT.

    HAZARD: look attributes up by NAME. The enumeration order of
    `color_attributes` differs between 4.5.11 and 5.1.2 for the same mesh
    (measured: BYTE first on 4.5, FLOAT first on 5.1), so indexing into the
    collection is not portable.
    """
    for name, dtype in ((AO_ATTR, "FLOAT_COLOR"), (AO_BYTE_ATTR, "BYTE_COLOR")):
        if name in me.color_attributes:
            me.color_attributes.remove(me.color_attributes[name])
        attr = me.color_attributes.new(name=name, type=dtype, domain="POINT")
        for i, a in enumerate(values):
            v = (1.0 - a) if invert else a
            attr.data[i].color = (v, v, v, 1.0)
    me.color_attributes.active_color = me.color_attributes[AO_ATTR]
    me.attributes.default_color_name = AO_ATTR
    me.attributes.active_color_name = AO_ATTR


# --- the independent sRGB storage model, for check 4 ------------------------

def lin_to_srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055


def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def byte_color_model(v):
    """What a BYTE_COLOR attribute should hand back for a linear write of v."""
    return srgb_to_lin(round(lin_to_srgb(v) * 255.0) / 255.0)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

class Part:
    """A bmesh under construction with named material slots."""

    def __init__(self):
        self.bm = bmesh.new()
        self.slots = []

    def group(self, slot_name, fn):
        before = set(self.bm.faces)
        fn(self.bm)
        if slot_name not in self.slots:
            self.slots.append(slot_name)
        idx = self.slots.index(slot_name)
        for f in self.bm.faces:
            if f not in before:
                f.material_index = idx
        return self

    def finish(self, name):
        me = bpy.data.meshes.new(name)
        try:
            # normal_update() recomputes from the existing winding; it does not
            # repair a face built the wrong way round, and an inward-facing
            # shell would swallow every AO ray it should have blocked.
            bmesh.ops.recalc_face_normals(self.bm, faces=list(self.bm.faces))
            self.bm.normal_update()
            self.bm.to_mesh(me)
        finally:
            self.bm.free()
        me["slots"] = self.slots
        return me


# _bevel_normals_note
# HAZARD: bmesh.ops.bevel offsets along the CACHED face normals, and moving a
# vertex does not refresh them. Build a cube, transform its verts, bevel: while
# the stale normal is still within 90 degrees of the true one the offset merely
# skews, but past 90 degrees it flips sign and the bevel grows the solid
# outward instead of chamfering it inward. Measured while authoring this
# asset, on a ring of bevelled boxes placed around a circle: the boxes at
# 0/36/72 degrees bevelled correctly and the box at 108 degrees grew by
# exactly one offset (12 mm) in both z directions, putting geometry below the
# ground plane. The hygiene check (exit 8) is what caught it.
# t.normal_update() before every bevel is the fix, and it is why every _box
# and _prism here calls it.


def _emit(bm, build, cuts=0):
    """Build one sub-solid in a private bmesh, then copy it into `bm`.

    HAZARD, and the reason this indirection exists. The obvious way to add a
    bevelled primitive to a shared bmesh is to snapshot ``set(bm.verts)``,
    create the primitive, diff to find the new verts, and bevel only the edges
    whose verts are all new. That works for the first few primitives and then
    silently corrupts: ``bmesh.ops.bevel`` reallocates the vertex table, so
    Python BMVert wrappers captured in the snapshot can alias geometry created
    afterwards. Measured on this asset's ground apron, the fault appeared at
    the **4th** box — edges belonging to an already-finished neighbour were
    selected and bevelled, dropping vertices exactly one bevel offset (12 mm)
    below the ground plane. The hygiene check is what caught it.

    Building each primitive in its own bmesh removes the coupling: no op ever
    runs on the shared mesh while a snapshot of it is being held.
    """
    tmp = bmesh.new()
    try:
        build(tmp)
        if cuts:
            # Point-domain AO can only vary where there are vertices. An
            # 8-vertex slab bakes to one nearly-constant value per face and
            # the crevice gradient the bake exists to capture never appears
            # in the attribute (draft 3 rendered as flat pale stone).
            bmesh.ops.subdivide_edges(tmp, edges=list(tmp.edges), cuts=cuts,
                                      use_grid_fill=True)
        vmap = {v: bm.verts.new(v.co) for v in tmp.verts}
        for f in tmp.faces:
            try:
                bm.faces.new([vmap[v] for v in f.verts])
            except ValueError:
                pass                      # coincident face across sub-solids
    finally:
        tmp.free()


def _box(bm, dims, centre, bevel=0.0, segments=1, rot=None, cuts=0):
    def build(t):
        bmesh.ops.create_cube(t, size=1.0)
        for v in t.verts:
            c = Vector((v.co.x * dims[0], v.co.y * dims[1], v.co.z * dims[2]))
            if rot is not None:
                c = rot @ c
            v.co = c + Vector(centre)
        if bevel > 0.0:
            t.normal_update()      # see _bevel_normals_note
            bmesh.ops.bevel(t, geom=list(t.edges), offset=bevel,
                            segments=segments, profile=0.5, affect="EDGES",
                            clamp_overlap=True)
    _emit(bm, build, cuts=cuts)


def _prism(bm, sides, radius, half_h, centre, bevel=0.0, rot=None, taper=1.0,
           phase=0.0, cuts=0):
    def build(t):
        ring = []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides + phase
            ring.append((math.cos(a) * radius, math.sin(a) * radius))
        top = [t.verts.new((x * taper, y * taper, half_h)) for x, y in ring]
        bot = [t.verts.new((x, y, -half_h)) for x, y in ring]
        t.faces.new(top)
        t.faces.new(list(reversed(bot)))
        for i in range(sides):
            j = (i + 1) % sides
            t.faces.new((bot[i], bot[j], top[j], top[i]))
        for v in t.verts:
            c = Vector(v.co)
            if rot is not None:
                c = rot @ c
            v.co = c + Vector(centre)
        if bevel > 0.0:
            t.normal_update()      # see _bevel_normals_note
            bmesh.ops.bevel(t, geom=list(t.edges), offset=bevel, segments=1,
                            profile=0.6, affect="EDGES", clamp_overlap=True)
    _emit(bm, build, cuts=cuts)


def _plate(bm, verts_xy, z0, z1, cuts=2):
    """A prism from an explicit polygon footprint, subdivided for the bake."""
    def build(t):
        top = [t.verts.new((x, y, z1)) for x, y in verts_xy]
        bot = [t.verts.new((x, y, z0)) for x, y in verts_xy]
        t.faces.new(top)
        t.faces.new(list(reversed(bot)))
        n = len(verts_xy)
        for i in range(n):
            j = (i + 1) % n
            t.faces.new((bot[i], bot[j], top[j], top[i]))
    _emit(bm, build, cuts=cuts)


# ---------------------------------------------------------------------------
# The asset: a stone village well
# ---------------------------------------------------------------------------

# Proportions: a squat, wide wellhead rather than a spindly one. Draft 4 gave
# the masonry a third of the frame and the timber frame the rest, so the joint
# occlusion the bake exists to show was sub-pixel. Widening the ring and
# dropping the frame puts the stonework where the eye lands.
SHAFT_R = 0.545           # inner bore radius
COURSES = (               # (z0, z1, outer radius, stone count, phase offset)
    (0.000, 0.200, 0.845, 15, 0.00),
    (0.200, 0.385, 0.822, 15, 0.50),
    (0.385, 0.560, 0.805, 15, 0.00),
)
COPING_Z0, COPING_Z1 = 0.560, 0.646
COPING_R = 0.925
POST_Y = 0.790
POST_TOP = 1.36
DRUM_Z = 1.030


def _course_stone(bm, z0, z1, r_out, idx, count, phase, jog):
    """One masonry block: a trapezoid footprint spanning an arc of the ring.

    Blocks are inset from each other by a small joint so the bake has real
    crevices to find — the mortar lines are geometry, not a texture.
    """
    joint = 0.078 / r_out                      # angular half-gap
    a0 = 2.0 * math.pi * (idx + phase) / count + joint
    a1 = 2.0 * math.pi * (idx + 1 + phase) / count - joint
    ro = r_out + jog
    ri = SHAFT_R
    pts = []
    for a in (a0, a1):
        pts.append((math.cos(a) * ro, math.sin(a) * ro))
    for a in (a1, a0):
        pts.append((math.cos(a) * ri, math.sin(a) * ri))
    _plate(bm, pts, z0 + 0.012, z1 - 0.012)


def build_well_meshes():
    meshes = {}
    # deterministic per-stone jog so the courses are not machine-perfect
    def jog(i, c):
        return 0.014 * math.sin(i * 2.399963 + c * 1.107)

    for ci, (z0, z1, r_out, count, phase) in enumerate(COURSES):
        part = Part()
        part.group("Stone", lambda bm, z0=z0, z1=z1, r=r_out, c=count,
                   ph=phase, ci=ci: [
                       _course_stone(bm, z0, z1, r, i, c, ph, jog(i, ci))
                       for i in range(c)])
        meshes[f"Course.{ci}"] = part.finish(f"Well.Stone.Course.{ci}")

    # coping: 11 flat slabs, a wider ring that overhangs and casts the
    # strongest contact darkening onto the top course
    cop = Part()
    def slabs(bm):
        n = 15
        for i in range(n):
            joint = 0.028 / COPING_R
            a0 = 2.0 * math.pi * i / n + joint
            a1 = 2.0 * math.pi * (i + 1) / n - joint
            pts = [(math.cos(a) * COPING_R, math.sin(a) * COPING_R)
                   for a in (a0, a1)]
            pts += [(math.cos(a) * (SHAFT_R - 0.02),
                     math.sin(a) * (SHAFT_R - 0.02)) for a in (a1, a0)]
            _plate(bm, pts, COPING_Z0, COPING_Z1 + 0.006 * math.sin(i * 1.7))
    cop.group("Coping", slabs)
    meshes["Coping"] = cop.finish("Well.Stone.Coping")

    # inner bore sleeve: darkens to near-zero down the shaft
    bore = Part()
    # the sleeve stops at z == 0 so the asset rests on the ground plane; an
    # earlier revision ran it to -0.02 and the hygiene check caught it
    bore.group("Bore", lambda bm: _prism(bm, 26, SHAFT_R - 0.028, 0.298,
                                         (0.0, 0.0, 0.298), cuts=3))
    meshes["Bore"] = bore.finish("Well.Stone.Bore")

    # ground apron: flagstones the well sits on, so the base has a floor to
    # occlude against
    ap = Part()
    def apron(bm):
        # a paved collar butted against the base course: the tighter the ring
        # sits, the deeper the contact darkening the bake has to find
        n = 16
        for i in range(n):
            joint = 0.032 / 1.05
            a0 = 2.0 * math.pi * i / n + joint
            a1 = 2.0 * math.pi * (i + 1) / n - joint
            r0, r1 = 0.870, 1.235 + 0.045 * math.sin(i * 2.1)
            pts = [(math.cos(a) * r1, math.sin(a) * r1) for a in (a0, a1)]
            pts += [(math.cos(a) * r0, math.sin(a) * r0) for a in (a1, a0)]
            _plate(bm, pts, 0.0, 0.048 + 0.008 * math.sin(i * 1.3), cuts=2)
    ap.group("Flag", apron)
    meshes["Apron"] = ap.finish("Well.Stone.Apron")

    # timber frame
    for side, sy in (("L", 1.0), ("R", -1.0)):
        fr = Part()
        fr.group("Timber", lambda bm, s=sy: _box(
            bm, (0.12, 0.12, POST_TOP - 0.30),
            (0.0, s * POST_Y, 0.30 + (POST_TOP - 0.30) / 2), bevel=0.012, cuts=3))
        fr.group("Iron", lambda bm, s=sy: _box(
            bm, (0.16, 0.16, 0.040), (0.0, s * POST_Y, 0.70), bevel=0.006))
        fr.group("Brace", lambda bm, s=sy: _box(
            bm, (0.08, 0.08, 0.42), (0.0, s * (POST_Y - 0.15), 0.90), bevel=0.010,
            rot=Matrix.Rotation(math.radians(22.0) * s, 3, "X")))
        meshes[f"Post.{side}"] = fr.finish(f"Well.Stone.Post.{side}")

    beam = Part()
    beam.group("Timber", lambda bm: _box(bm, (0.12, 2 * POST_Y + 0.22, 0.13),
                                         (0.0, 0.0, POST_TOP - 0.065), bevel=0.014,
                                         cuts=3))
    def caps(bm):
        # Post caps, not a roof. Two revisions of a gable were tried: fanned
        # boards read as detached planks, and solid slopes big enough to look
        # like a roof covered the masonry that carries the AO story. A
        # roofless windlass well is the more honest prop and the better
        # subject for this bake.
        for s in (1.0, -1.0):
            _box(bm, (0.18, 0.18, 0.05), (0.0, s * POST_Y, POST_TOP + 0.025),
                 bevel=0.010, cuts=1)
        _box(bm, (0.16, 2 * POST_Y - 0.30, 0.05),
             (0.0, 0.0, POST_TOP - 0.155), bevel=0.010, cuts=2)
    beam.group("Shingle", caps)
    meshes["Beam"] = beam.finish("Well.Stone.Beam")

    # windlass: drum along Y with a crank, plus the rope and bucket
    wl = Part()
    rotY = Matrix.Rotation(math.radians(90.0), 3, "X")
    wl.group("Drum", lambda bm: _prism(bm, 14, 0.085, POST_Y - 0.03,
                                       (0.0, 0.0, DRUM_Z), rot=rotY, cuts=2))
    def collars(bm):
        for s in (1.0, -1.0):
            _prism(bm, 14, 0.098, 0.022, (0.0, s * (POST_Y - 0.045), DRUM_Z),
                   rot=rotY)
    wl.group("Iron", collars)
    def crank(bm):
        _prism(bm, 10, 0.020, 0.10, (0.0, POST_Y + 0.06, DRUM_Z), rot=rotY)
        _box(bm, (0.030, 0.030, 0.20), (0.0, POST_Y + 0.10, DRUM_Z - 0.09),
             bevel=0.006, rot=Matrix.Rotation(math.radians(90.0), 3, "Y"))
        _prism(bm, 10, 0.026, 0.062, (0.14, POST_Y + 0.10, DRUM_Z - 0.09),
               rot=Matrix.Rotation(math.radians(90.0), 3, "X"))
    wl.group("Iron", crank)
    meshes["Windlass"] = wl.finish("Well.Stone.Windlass")

    bk = Part()
    bk.group("Rope", lambda bm: _prism(bm, 7, 0.020, 0.105,
                                       (0.10, -0.20, DRUM_Z - 0.020), cuts=2))
    bk.group("Stave", lambda bm: _prism(bm, 16, 0.150, 0.130,
                                        (0.10, -0.20, 0.845), taper=0.86, cuts=2))
    def bands(bm):
        for z in (0.740, 0.953):
            _prism(bm, 16, 0.158, 0.016, (0.10, -0.20, z))
    bk.group("Iron", bands)
    bk.group("Iron", lambda bm: _box(bm, (0.30, 0.022, 0.022),
                                     (0.10, -0.20, 0.983), bevel=0.005))
    meshes["Bucket"] = bk.finish("Well.Stone.Bucket")
    return meshes


def build_asset(sc):
    """Link the well into `sc`. Returns (root, parts)."""
    root = bpy.data.objects.new("Well.Stone", None)
    root.empty_display_type = "PLAIN_AXES"
    sc.collection.objects.link(root)
    parts = []
    for suffix, me in build_well_meshes().items():
        ob = bpy.data.objects.new(me.name, me)
        sc.collection.objects.link(ob)
        ob.parent = root
        parts.append(ob)
    bpy.context.view_layer.update()
    return root, parts


def bake_asset(parts, n_samples=ASSET_SAMPLES, invert=False):
    """Bake AO for every part against the whole assembly. Returns all values."""
    bvh = world_bvh(parts)
    every = []
    for ob in parts:
        vals = bake_object_ao(bvh, ob, n_samples)
        write_ao_attributes(ob.data, vals, invert=invert)
        every.extend(vals)
    return every


# ---------------------------------------------------------------------------
# Calibration rig
# ---------------------------------------------------------------------------

def build_calibration(sc):
    """A wide wall plus a floor strip whose vertices sit at CAL_DISTANCES.

    Returns (wall_ob, floor_ob, probe_indices) — the floor vertices whose AO
    is held to the closed form.
    """
    wm = bpy.data.meshes.new("Cal.Wall")
    bm = bmesh.new()
    try:
        v = [bm.verts.new(p) for p in ((0, -WALL_HALF_W, 0), (0, WALL_HALF_W, 0),
                                       (0, WALL_HALF_W, WALL_H),
                                       (0, -WALL_HALF_W, WALL_H))]
        bm.faces.new(v)
        bm.to_mesh(wm)
    finally:
        bm.free()
    wall = bpy.data.objects.new("Cal.Wall", wm)
    sc.collection.objects.link(wall)

    fm = bpy.data.meshes.new("Cal.Floor")
    bm = bmesh.new()
    try:
        rows = []
        for d in CAL_DISTANCES:
            rows.append([bm.verts.new((d, y, 0.0)) for y in (-6.0, 6.0)])
        for a, b in zip(rows, rows[1:]):
            bm.faces.new((a[0], a[1], b[1], b[0]))
        bm.normal_update()
        bm.to_mesh(fm)
    finally:
        bm.free()
    floor = bpy.data.objects.new("Cal.Floor", fm)
    sc.collection.objects.link(floor)
    bpy.context.view_layer.update()
    return wall, floor


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def check():
    sc = bpy.context.scene
    fails = []

    def fail(code, msg):
        print(f"ERROR ({code}): {msg}", file=sys.stderr)
        fails.append(code)

    # --- 1. analytic AO against the closed form -----------------------------
    wall, floor = build_calibration(sc)
    bvh = world_bvh([wall])
    up = Vector((0.0, 0.0, 1.0))
    measured, expected = [], []
    for d in CAL_DISTANCES:
        got = bake_points(bvh, [Vector((d, 0.0, 0.0))], [up], CAL_SAMPLES)[0]
        want = analytic_ao(WALL_H, d)
        measured.append(got)
        expected.append(want)
        if abs(got - want) > CAL_TOL:
            fail(3, f"AO at d={d} is {got:.6f}, closed form {want:.6f} "
                    f"(err {abs(got - want):.3e} > {CAL_TOL:.1e}) — the "
                    f"integrator does not integrate the hemisphere it claims to")
    worst_cal = max(abs(g - w) for g, w in zip(measured, expected))
    print("analytic_ao samples=%d H=%.1f" % (CAL_SAMPLES, WALL_H))
    for d, g, w in zip(CAL_DISTANCES, measured, expected):
        print(f"  d={d:<5} k={WALL_H / d:<7.2f} ao={g:.6f} closed_form={w:.6f} "
              f"err={abs(g - w):.3e}")
    print(f"analytic_ao worst_err={worst_cal:.3e} tol={CAL_TOL:.1e}")

    # --- 2. unoccluded == 1 exactly, and strict monotonicity ----------------
    free = bake_points(world_bvh([floor]), [Vector((3.0, 0.0, 0.0))], [up],
                       CAL_SAMPLES)[0]
    print(f"unoccluded_plate ao={free:.9f} (closed form 1.0)")
    if abs(free - 1.0) > 0.0:
        fail(4, f"an unoccluded flat plate bakes to {free:.9f}, not exactly 1.0 "
                f"— rays are self-hitting the surface they start on")
    strictly_up = all(b > a for a, b in zip(measured, measured[1:]))
    print(f"monotonic increasing_with_distance={strictly_up} "
          f"range={measured[0]:.6f}..{measured[-1]:.6f}")
    if not strictly_up:
        fail(4, "AO does not increase strictly with distance from the wall — "
                "the corner does not darken monotonically with depth")

    # --- 3. asset bake: in range, and actually using the range --------------
    root, parts = build_asset(sc)
    # A loop over nothing asserts nothing: pin the population before the
    # per-part and per-vertex checks below iterate over it.
    if len(parts) != EXPECT_PARTS:
        fail(8, f"asset built {len(parts)} parts, expected {EXPECT_PARTS} - "
                f"the checks below would iterate over the wrong set")
        return fails[0]
    values = bake_asset(parts)
    if not values:
        fail(5, "the bake produced no values at all")
        return fails[0]
    lo, hi = min(values), max(values)
    print(f"asset_bake parts={len(parts)} verts={len(values)} "
          f"samples={ASSET_SAMPLES} min={lo:.6f} max={hi:.6f} spread={hi - lo:.6f}")
    if lo < 0.0 or hi > 1.0:
        fail(5, f"baked AO out of range [{lo:.6f}, {hi:.6f}] — a colour "
                f"attribute an engine reads must stay in [0,1]")
    if hi - lo < SPREAD_MIN:
        fail(5, f"AO spread {hi - lo:.6f} < {SPREAD_MIN} — the bake is nearly "
                f"constant, so it is not describing this geometry")

    # --- 4. storage round-trip: FLOAT exact, BYTE sRGB-quantised ------------
    probe_me = parts[0].data
    fa = probe_me.color_attributes[AO_ATTR]
    ba = probe_me.color_attributes[AO_BYTE_ATTR]
    written = values[:len(fa.data)]
    float_err = max(abs(fa.data[i].color[0] - v) for i, v in enumerate(written))
    byte_err = max(abs(ba.data[i].color[0] - v) for i, v in enumerate(written))
    model_err = max(abs(ba.data[i].color[0] - byte_color_model(v))
                    for i, v in enumerate(written))
    print(f"storage float_roundtrip_err={float_err:.3e} "
          f"byte_roundtrip_err={byte_err:.3e} byte_vs_srgb_model={model_err:.3e}")
    if float_err > FLOAT_TOL:
        fail(6, f"FLOAT_COLOR round-trip error {float_err:.3e} > {FLOAT_TOL:.0e}")
    if model_err > BYTE_MODEL_TOL:
        fail(6, f"BYTE_COLOR readback deviates {model_err:.3e} from the "
                f"independent sRGB encode/quantise/decode model — the storage "
                f"encoding is not what the README documents")
    if byte_err <= float_err:
        fail(6, "BYTE_COLOR round-trips as tightly as FLOAT_COLOR — the "
                "documented 8-bit sRGB quantisation has stopped happening, so "
                "the exporter warning is now wrong")

    # --- 5. depsgraph survival ----------------------------------------------
    dg = bpy.context.evaluated_depsgraph_get()
    worst_ev = 0.0
    for ob in parts:
        ev = ob.evaluated_get(dg).data
        for name in (AO_ATTR, AO_BYTE_ATTR):
            eva = ev.color_attributes.get(name)
            if eva is None:
                fail(7, f"{ob.name}: {name} missing from the evaluated mesh")
                continue
            src = ob.data.color_attributes[name]
            if eva.data_type != src.data_type or eva.domain != src.domain:
                fail(7, f"{ob.name}: {name} changed to "
                        f"{eva.data_type}/{eva.domain} under evaluation")
            # Compare lengths BEFORE zipping. zip() stops at the shorter
            # sequence, so a modifier that resamples the attribute onto a
            # different element count would slip through as a clean 0.0
            # deviation — the probe that added a Subdiv modifier exited 0
            # until this guard was added.
            if len(eva.data) != len(src.data):
                fail(7, f"{ob.name}: {name} has {len(eva.data)} evaluated "
                        f"elements vs {len(src.data)} authored — a modifier "
                        f"resampled the attribute, so what renders is not "
                        f"what was baked")
                continue
            worst_ev = max(worst_ev, max(
                abs(a.color[0] - b.color[0]) for a, b in zip(src.data, eva.data)))
    print(f"depsgraph_survival parts={len(parts)} max_dev={worst_ev:.3e}")
    if worst_ev > 0.0:
        fail(7, f"colour attributes drift {worst_ev:.3e} under depsgraph "
                f"evaluation — the baked data is not what renders")

    # --- 6. reuse hygiene ----------------------------------------------------
    default_names = {"Cube", "Sphere", "Torus", "Suzanne", "Plane", "Circle",
                     "Cylinder", "Cone", "Grid", "Icosphere", "Empty"}
    for ob in parts:
        if max(abs(s - 1.0) for s in ob.scale) > 0.0:
            fail(8, f"{ob.name} scale {tuple(ob.scale)} not applied")
        if not ob.name.startswith("Well.Stone."):
            fail(8, f"part {ob.name!r} outside the asset namespace")
        if ob.data.name.split(".")[0] in default_names:
            fail(8, f"{ob.name} carries a default datablock name")
        if ob.data.attributes.default_color_name != AO_ATTR:
            fail(8, f"{ob.name} render colour attribute is "
                    f"{ob.data.attributes.default_color_name!r}, not {AO_ATTR!r} "
                    f"— an engine would read the wrong channel")
    ground = min(min(v.co.z for v in ob.data.vertices) for ob in parts)
    if abs(ground) > 1e-4:
        fail(8, f"asset rests at z={ground:.5f}, not on the ground plane")
    print(f"hygiene parts={len(parts)} ground_z={ground:.2e} "
          f"render_attr={AO_ATTR}")

    if fails:
        return fails[0]
    print(f"vertex-color-ao OK cal_err={worst_cal:.3e} unoccluded={free:.6f} "
          f"asset_range={lo:.4f}..{hi:.4f} float_err={float_err:.3e} "
          f"byte_model_err={model_err:.3e} evaluated_dev={worst_ev:.3e}")
    return 0


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def make_ao_material(name, rgb, rough, metallic=0.0, ao_strength=1.0):
    """Principled with the AO colour attribute multiplied into base colour."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    col = nt.nodes.new("ShaderNodeVertexColor")
    col.layer_name = AO_ATTR
    col.location = (-700, 100)
    # lift so full occlusion does not go to pure black
    lift = nt.nodes.new("ShaderNodeMixRGB")
    lift.blend_type = "MIX"
    lift.inputs["Fac"].default_value = ao_strength
    lift.inputs["Color1"].default_value = (1.0, 1.0, 1.0, 1.0)
    lift.location = (-500, 100)
    nt.links.new(col.outputs["Color"], lift.inputs["Color2"])
    tint = nt.nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs["Fac"].default_value = 1.0
    tint.inputs["Color1"].default_value = (*rgb, 1.0)
    tint.location = (-300, 100)
    nt.links.new(lift.outputs["Color"], tint.inputs["Color2"])
    nt.links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


SLOT_MATS = {
    "Stone":   ((0.086, 0.079, 0.069), 0.86, 0.0),
    "Coping":  ((0.118, 0.108, 0.094), 0.80, 0.0),
    "Bore":    ((0.038, 0.035, 0.032), 0.92, 0.0),
    "Flag":    ((0.066, 0.061, 0.055), 0.89, 0.0),
    "Timber":  ((0.148, 0.078, 0.030), 0.74, 0.0),
    "Brace":   ((0.120, 0.064, 0.026), 0.76, 0.0),
    "Shingle": ((0.092, 0.056, 0.028), 0.82, 0.0),
    "Drum":    ((0.170, 0.098, 0.040), 0.72, 0.0),
    "Stave":   ((0.205, 0.118, 0.048), 0.70, 0.0),
    "Rope":    ((0.255, 0.208, 0.122), 0.88, 0.0),
    "Iron":    ((0.075, 0.078, 0.084), 0.44, 0.85),
}

_mat_cache = {}


def bind_materials(ob, ao_strength=1.0):
    me = ob.data
    if me.materials:
        return
    for slot in me.get("slots", []):
        key = (slot, ao_strength)
        if key not in _mat_cache:
            rgb, rough, metal = SLOT_MATS[slot]
            _mat_cache[key] = make_ao_material(slot, rgb, rough, metal,
                                               ao_strength)
        me.materials.append(_mat_cache[key])


def build_studio(sc):
    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = bpy.data.materials.new("Studio")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.030, 0.032, 0.037, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    sc.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 7.5, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.020, 0.021, 0.025, 1.0)
    sc.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.size, ld.color = energy, size, col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        sc.collection.objects.link(ob)

    # VISUAL-STYLE Layer 2 rig, energies scaled to a ~1.9 m subject
    light("Key", (-2.3, -2.4, 3.6), 430.0, 3.0, (1.0, 0.96, 0.9), (40, 0, -42))
    light("Fill", (3.0, -2.0, 1.2), 78.0, 5.0, (0.75, 0.85, 1.0), (70, 0, 54))
    light("Rim", (-0.9, 3.0, 2.6), 240.0, 2.0, (0.6, 0.78, 1.0), (-54, 0, 196))
    light("Wedge", (0.3, 5.0, 0.7), 300.0, 5.0, (1.0, 0.76, 0.5), (-86, 0, 182))
    return floor, wall


def render_still(path, engine, falsify=False):
    """The well with its baked AO driving base colour.

    Falsified: the same bake written INVERTED, so the crevices between the
    masonry courses and the inside of the shaft read bright while the exposed,
    sky-facing stone goes dark — occlusion turned inside out.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mat_cache.clear()
    sc = bpy.context.scene

    root, parts = build_asset(sc)
    bake_asset(parts, n_samples=192, invert=falsify)
    for ob in parts:
        bind_materials(ob)
    floor, wall = build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (3.62, -4.78, 3.42)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.49)
    sc.collection.objects.link(aim)
    tr = cam.constraints.new("TRACK_TO")
    tr.target = aim
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    sc.camera = cam

    sc.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        sc.cycles.device = "CPU"
        sc.cycles.samples = 64
        sc.cycles.use_denoising = True
    else:
        try:
            sc.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    # Standard, always — AgX would lift the stage toward grey (VISUAL-STYLE)
    sc.view_settings.view_transform = "Standard"
    bpy.context.view_layer.update()

    fcode = gallery_framing.check_framing(sc, cam, hero=parts, elements=parts,
                                          stage=[floor, wall])
    if fcode:
        return fcode
    aqcode = gallery_asset_quality.check_asset_quality(sc, cam, hero=parts,
                                                       stage=[floor, wall])
    if aqcode:
        return aqcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 9
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--falsify", default=None,
                   help="optional: render the inverted-AO variant here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    code = check()
    if code:
        return code
    if args.output:
        rcode = render_still(os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")
    if args.falsify:
        rcode = render_still(os.path.abspath(args.falsify), args.engine,
                             falsify=True)
        if rcode:
            return rcode
        print(f"rendered falsified variant {args.falsify}")

    print("vertex-color-ao OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
