"""Prop origin transform — base-center origin + scale apply + MPI accessory.

Witnesses the object-level contract a prop pipeline relies on before engine
ingest: origin at the local base center, scale applied through the data API
to exactly (1,1,1), world bbox unchanged across the bake, and
`matrix_parent_inverse` so a parented accessory does not teleport. Extends
`parent-inverse-orrery` (MPI idiom + stale `matrix_world`) without retreading
orbits — subject is a street utility pedestal with a flanged conduit elbow.

``--skip-mpi`` parents the accessory without MPI and still asserts the restore.
That is the falsifier (``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render). Pass --output
to also render a still:

    blender --background --python prop_origin_transform.py --
    blender --background --python prop_origin_transform.py -- --skip-mpi
    blender --background --python prop_origin_transform.py -- --output o.png
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Matrix, Vector

# Shared Layer 1 measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

BBOX_EPS = 1e-6
WORLD_EPS = 1e-5
MPI_EPS = 1e-6
STALE_EPS = 1e-9
JUMP_MIN = 0.05

# The pedestal arrives the way an import often does: origin at the geometric
# centre and a non-uniform object scale compensating mesh data authored in
# the wrong units. The bake must land the mesh on exactly the designed shape.
PROP_SCALE = (1.15, 0.92, 1.08)

# Designed dimensions (metres, base-centre origin).
PAD = (1.04, 0.62, 0.10)            # precast concrete footing
BODY_XY = (0.46, 0.36)
BODY_Z = (0.125, 1.05)
MOUNT_Z = 0.45                       # conduit boss on the +X side face
MOUNT = Vector((BODY_XY[0] / 2 + 0.012, 0.0, MOUNT_Z))   # flange seat face
SLEEVE = Vector((0.41, 0.0, PAD[2]))  # pad sleeve the conduit drops into
SLEEVE_H = 0.05
SLAB_H = 0.20                       # render only: sidewalk slab under both copies

# Material slots
M_PAINT, M_GALV, M_CONCRETE, M_DARK, M_LABEL = range(5)
A_PVC, A_GALV = range(2)


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def make_material(name, rgb, rough=0.45, metallic=0.35, emit=None, estr=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    if emit is not None:
        sock = b.inputs.get("Emission Color") or b.inputs["Emission"]
        sock.default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = estr
    return mat


def pedestal_materials(tag=""):
    return [
        make_material(f"PedestalPaint{tag}", (0.05, 0.36, 0.20), rough=0.42, metallic=0.15),
        make_material(f"GalvSteel{tag}", (0.62, 0.64, 0.66), rough=0.32, metallic=0.85),
        make_material(f"Concrete{tag}", (0.36, 0.35, 0.33), rough=0.88, metallic=0.0),
        make_material(f"BlackRubber{tag}", (0.025, 0.026, 0.028), rough=0.55, metallic=0.0),
        make_material(f"HazardLabel{tag}", (0.95, 0.66, 0.02), rough=0.45, metallic=0.0),
    ]


def conduit_materials(tag=""):
    return [
        make_material(f"ConduitPVC{tag}", (0.92, 0.30, 0.03), rough=0.38, metallic=0.0),
        make_material(f"ConduitGalv{tag}", (0.62, 0.64, 0.66), rough=0.32, metallic=0.85),
    ]


# ---------------------------------------------------------------------------
# Modelling. Every part is built in one bmesh; each helper tags the faces it
# creates with a material slot and a shading mode.


class Part:
    """Context for one part: new verts/faces are the set difference."""

    def __init__(self, bm):
        self.bm = bm
        self.v0 = set(bm.verts)
        self.f0 = set(bm.faces)

    def verts(self):
        return [v for v in self.bm.verts if v not in self.v0]

    def finish(self, mat, smooth_axis=None):
        for f in self.bm.faces:
            if f in self.f0:
                continue
            f.material_index = mat
            if smooth_axis is None:
                f.smooth = False
            else:
                f.normal_update()
                f.smooth = abs(f.normal.dot(smooth_axis)) < 0.9


def box(bm, center, size, mat, bevel=0.0, rot=None):
    part = Part(bm)
    geom = bmesh.ops.create_cube(bm, size=1.0)
    for v in geom["verts"]:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    if bevel > 0.0:
        edges = list({e for v in geom["verts"] for e in v.link_edges})
        bmesh.ops.bevel(
            bm, geom=edges, offset=bevel, segments=2, profile=0.5, affect="EDGES",
            clamp_overlap=True,
        )
    m = Matrix.Translation(Vector(center))
    if rot is not None:
        m = m @ rot
    bmesh.ops.transform(bm, matrix=m, verts=part.verts())
    part.finish(mat)


def _axis_matrix(axis):
    """Rotation taking +Z onto *axis* (a unit Vector)."""
    return Vector((0.0, 0.0, 1.0)).rotation_difference(axis).to_matrix().to_4x4()


def cyl(bm, start, axis, length, r0, r1, mat, segs=24, smooth=True, bevel=0.0):
    """Frustum from *start* along unit *axis*, radius r0 -> r1."""
    part = Part(bm)
    axis = Vector(axis).normalized()
    geom = bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=segs,
        radius1=r0, radius2=r1, depth=length,
    )
    if bevel > 0.0:
        # Chamfer the two cap rims so machined parts catch a highlight.
        rims = [e for e in {e for v in geom["verts"] for e in v.link_edges}
                if abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-9]
        bmesh.ops.bevel(
            bm, geom=rims, offset=bevel, segments=2, profile=0.5, affect="EDGES",
            clamp_overlap=True,
        )
    mat4 = Matrix.Translation(Vector(start) + axis * (length * 0.5)) @ _axis_matrix(axis)
    bmesh.ops.transform(bm, matrix=mat4, verts=part.verts())
    part.finish(mat, axis if smooth else None)


def frustum_box(bm, z0, z1, lo, hi, mat):
    """Hip lid: rectangle *lo* (x,y) at z0 rising to rectangle *hi* at z1."""
    part = Part(bm)
    ring = []
    for (hx, hy), z in ((lo, z0), (hi, z1)):
        ring.append([bm.verts.new((sx * hx / 2, sy * hy / 2, z))
                     for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    a, b = ring
    for k in range(4):
        n = (k + 1) % 4
        bm.faces.new((a[k], a[n], b[n], b[k]))
    bm.faces.new((a[0], a[3], a[2], a[1]))
    bm.faces.new((b[0], b[1], b[2], b[3]))
    part.finish(mat)


def elbow(bm, start, radius, bend_r, mat, segs=20, steps=10):
    """Quarter bend from *start* heading +X, turning down to -Z (XZ plane)."""
    part = Part(bm)
    rings = []
    for i in range(steps + 1):
        a = (math.pi / 2) * i / steps
        c = Vector(start) + Vector((bend_r * math.sin(a), 0.0, -bend_r + bend_r * math.cos(a)))
        t = Vector((math.cos(a), 0.0, -math.sin(a)))
        n = t.cross(Vector((0.0, 1.0, 0.0))).normalized()  # in-plane normal
        b = Vector((0.0, 1.0, 0.0))
        rings.append([bm.verts.new(c + radius * (math.cos(2 * math.pi * k / segs) * n
                                                 + math.sin(2 * math.pi * k / segs) * b))
                      for k in range(segs)])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(segs):
            m = (k + 1) % segs
            f = bm.faces.new((r0[k], r0[m], r1[m], r1[k]))
    part.finish(mat)
    for f in bm.faces:
        if f not in part.f0:
            f.smooth = True


def build_pedestal_design(bm):
    """Street utility pedestal, designed shape, origin at the base centre."""
    up = (0.0, 0.0, 1.0)
    # Precast footing and the galvanised base plate with four anchor nuts.
    box(bm, (0, 0, PAD[2] / 2), PAD, M_CONCRETE, bevel=0.025)
    box(bm, (0, 0, PAD[2] + 0.0125), (0.58, 0.46, 0.025), M_GALV, bevel=0.006)
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = Vector((sx * 0.25, sy * 0.19, PAD[2] + 0.025))
            cyl(bm, c, up, 0.006, 0.026, 0.026, M_GALV, segs=16)
            cyl(bm, c + Vector((0, 0, 0.006)), up, 0.02, 0.019, 0.019, M_DARK,
                segs=6, smooth=False)
            cyl(bm, c + Vector((0, 0, 0.026)), up, 0.012, 0.008, 0.006, M_GALV, segs=10)
    # Cabinet body over a black kick skirt.
    zc = 0.5 * (BODY_Z[0] + BODY_Z[1])
    box(bm, (0, 0, zc), (BODY_XY[0], BODY_XY[1], BODY_Z[1] - BODY_Z[0]), M_PAINT,
        bevel=0.022)
    box(bm, (0, 0, BODY_Z[0] + 0.045), (BODY_XY[0] + 0.02, BODY_XY[1] + 0.02, 0.09),
        M_DARK, bevel=0.01)
    # Overhanging lid with a hipped cap.
    box(bm, (0, 0, BODY_Z[1] + 0.02), (0.52, 0.42, 0.04), M_PAINT, bevel=0.012)
    frustum_box(bm, BODY_Z[1] + 0.04, BODY_Z[1] + 0.11, (0.50, 0.40), (0.30, 0.20),
                M_PAINT)
    # Front access door: dark shadow gap, raised panel, hinges, T-handle lock.
    fy = -BODY_XY[1] / 2
    box(bm, (0, fy - 0.002, 0.60), (0.37, 0.006, 0.70), M_DARK, bevel=0.002)
    box(bm, (0, fy - 0.009, 0.60), (0.35, 0.012, 0.68), M_PAINT, bevel=0.005)
    for z in (0.36, 0.84):
        cyl(bm, (-0.182, fy - 0.012, z - 0.04), up, 0.08, 0.009, 0.009, M_GALV, segs=12)
    cyl(bm, (0.12, fy - 0.015, 0.62), (0, -1, 0), 0.014, 0.022, 0.022, M_GALV, segs=20,
        bevel=0.003)
    box(bm, (0.12, fy - 0.034, 0.62), (0.018, 0.012, 0.10), M_GALV, bevel=0.004)
    # Hazard plate high on the door: black border, yellow face, black mark.
    box(bm, (0, fy - 0.016, 0.87), (0.17, 0.003, 0.11), M_DARK, bevel=0.001)
    box(bm, (0, fy - 0.018, 0.87), (0.155, 0.003, 0.095), M_LABEL, bevel=0.001)
    cyl(bm, (0, fy - 0.0195, 0.862), (0, -1, 0), 0.002, 0.034, 0.034, M_DARK, segs=3,
        smooth=False)
    # Louvred vents high on both sides.
    for sx in (-1, 1):
        x = sx * BODY_XY[0] / 2
        box(bm, (x + sx * 0.002, 0, 0.87), (0.006, 0.24, 0.17), M_DARK, bevel=0.001)
        for i in range(5):
            box(bm, (x + sx * 0.012, 0, 0.805 + i * 0.032), (0.022, 0.23, 0.012), M_PAINT,
                bevel=0.003, rot=Matrix.Rotation(sx * math.radians(-35), 4, "Y"))
    # Conduit boss on the +X face (the accessory's seat) and the pad sleeve.
    cyl(bm, (BODY_XY[0] / 2, 0, MOUNT_Z), (1, 0, 0), MOUNT.x - BODY_XY[0] / 2, 0.108,
        0.108, M_GALV, segs=32, bevel=0.003)
    cyl(bm, SLEEVE, up, SLEEVE_H, 0.076, 0.076, M_GALV, segs=28, bevel=0.004)
    cyl(bm, SLEEVE + Vector((0, 0, SLEEVE_H)), up, 0.002, 0.06, 0.06, M_DARK, segs=28)


def build_pedestal_mesh(name="StreetPedestal"):
    """Pedestal mesh in its as-imported state (see PROP_SCALE)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        build_pedestal_design(bm)
        # Origin at the geometric centre, coordinates divided by the object
        # scale the import will carry.
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        c = Vector((0.5 * (min(xs) + max(xs)), 0.5 * (min(ys) + max(ys)),
                    0.5 * (min(zs) + max(zs))))
        for v in bm.verts:
            p = v.co - c
            v.co = Vector((p.x / PROP_SCALE[0], p.y / PROP_SCALE[1], p.z / PROP_SCALE[2]))
        bm.normal_update()
        bm.to_mesh(me)
    finally:
        bm.free()
    for m in pedestal_materials():
        me.materials.append(m)
    return me


def build_conduit_design(bm):
    """Flanged conduit elbow. Origin at the flange's mounting face, +X out of
    the pedestal, the drop leg ending in a coupling that seats in the sleeve."""
    xa = Vector((1, 0, 0))
    down = Vector((0, 0, -1))
    r = 0.05                         # conduit outside radius
    bend_r = 0.10
    leg_x = SLEEVE.x - MOUNT.x
    x_bend = leg_x - bend_r
    z_seat = SLEEVE.z + SLEEVE_H - MOUNT.z
    # Flange with four bolt heads.
    cyl(bm, (0, 0, 0), xa, 0.02, 0.095, 0.095, A_GALV, segs=32, bevel=0.004)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        cyl(bm, (0.02, 0.068 * math.cos(a), 0.068 * math.sin(a)), xa, 0.012, 0.014,
            0.014, A_GALV, segs=6, smooth=False)
    # Hub, horizontal run, bend, drop leg.
    cyl(bm, (0.02, 0, 0), xa, 0.03, r + 0.012, r + 0.012, A_PVC, segs=28, bevel=0.004)
    cyl(bm, (0.05, 0, 0), xa, x_bend - 0.05, r, r, A_PVC, segs=28)
    elbow(bm, (x_bend, 0, 0), r, bend_r, A_PVC, segs=28)
    leg_top = Vector((leg_x, 0, -bend_r))
    leg_len = (-bend_r) - (z_seat + 0.05)
    cyl(bm, leg_top, down, leg_len, r, r, A_PVC, segs=28)
    # Strap clamp mid-leg and the coupling that sits on the sleeve.
    cyl(bm, leg_top + down * (leg_len * 0.45), down, 0.022, r + 0.008, r + 0.008, A_GALV,
        segs=28, bevel=0.003)
    box(bm, leg_top + down * (leg_len * 0.45 + 0.011) + Vector((0, r + 0.014, 0)),
        (0.022, 0.024, 0.022), A_GALV, bevel=0.004)
    cyl(bm, Vector((leg_x, 0, z_seat + 0.05)), down, 0.05, r + 0.012, r + 0.012, A_GALV,
        segs=28, bevel=0.004)


def build_accessory_mesh(name="ConduitElbow"):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        build_conduit_design(bm)
        bm.normal_update()
        bm.to_mesh(me)
    finally:
        bm.free()
    for m in conduit_materials():
        me.materials.append(m)
    return me


# ---------------------------------------------------------------------------
# Contract


def local_bbox(me):
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    return (
        Vector((min(xs), min(ys), min(zs))),
        Vector((max(xs), max(ys), max(zs))),
    )


def world_bbox(obj):
    """Axis-aligned world bbox from object bound_box (needs fresh depsgraph)."""
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return (
        Vector((min(xs), min(ys), min(zs))),
        Vector((max(xs), max(ys), max(zs))),
    )


def bbox_delta(a, b):
    (amin, amax), (bmin, bmax) = a, b
    return max(
        (amin - bmin).length,
        (amax - bmax).length,
        abs(amin.x - bmin.x), abs(amin.y - bmin.y), abs(amin.z - bmin.z),
        abs(amax.x - bmax.x), abs(amax.y - bmax.y), abs(amax.z - bmax.z),
    )


def apply_scale_data_api(obj):
    """Bake non-uniform scale into mesh verts; leave obj.scale == (1,1,1)."""
    sx, sy, sz = obj.scale
    for v in obj.data.vertices:
        v.co.x *= sx
        v.co.y *= sy
        v.co.z *= sz
    obj.scale = (1.0, 1.0, 1.0)
    obj.data.update()


def origin_to_base_center(obj):
    """Shift mesh so local min Z == 0 and XY centered; keep world geometry."""
    mn, mx = local_bbox(obj.data)
    ox = 0.5 * (mn.x + mx.x)
    oy = 0.5 * (mn.y + mx.y)
    oz = mn.z
    offset = Vector((ox, oy, oz))
    for v in obj.data.vertices:
        v.co -= offset
    obj.data.update()
    # World translation that compensates the mesh shift under current transform
    bpy.context.view_layer.update()
    offset_world = obj.matrix_world.to_3x3() @ offset
    obj.location = obj.location + offset_world


def parent_keep_world(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    prop = bpy.data.objects.new("StreetPedestal", build_pedestal_mesh())
    # Intentionally wrong for ingest: non-uniform scale, origin at geometry center
    prop.scale = PROP_SCALE
    prop.location = (0.0, 0.0, 0.0)
    sc.collection.objects.link(prop)

    acc = bpy.data.objects.new("ConduitElbow", build_accessory_mesh())
    # World pose before parenting — bolted to the front face mid-height
    acc.location = (0.0, -0.55, 0.15)
    acc.rotation_euler = (0.0, 0.0, 0.0)
    sc.collection.objects.link(acc)

    bpy.context.view_layer.update()
    return sc, prop, acc


def bake_prop(prop):
    """Apply scale then origin-to-base-center; return world bbox before/after."""
    bpy.context.view_layer.update()
    before = world_bbox(prop)
    apply_scale_data_api(prop)
    bpy.context.view_layer.update()
    origin_to_base_center(prop)
    bpy.context.view_layer.update()
    after = world_bbox(prop)
    return before, after


def check(prop, acc, skip_mpi=False):
    """Assert origin/scale bake + MPI accessory contract. Exit 3–8 on failure."""
    view_layer = bpy.context.view_layer

    # --- 0. Stale matrix_world without update (orrery half of the contract) ---
    # Nudge location; matrix_world must stay stale until update().
    view_layer.update()
    before = prop.matrix_world.translation.copy()
    prop.location.x += 0.25
    stale = (prop.matrix_world.translation - before).length
    if stale > STALE_EPS:
        print(
            f"ERROR: matrix_world updated without view_layer.update() "
            f"(delta={stale:.3e}) — cannot witness the stale-matrix trap",
            file=sys.stderr,
        )
        return 3
    view_layer.update()
    fresh = (prop.matrix_world.translation - before).length
    if abs(fresh - 0.25) > WORLD_EPS:
        print(
            f"ERROR: after update, location delta {fresh:.6f} != 0.25",
            file=sys.stderr,
        )
        return 3
    prop.location.x -= 0.25
    view_layer.update()
    print(f"stale_matrix_ok stale={stale:.3e} fresh={fresh:.6f}")

    # --- 1. Bake scale + origin; world bbox must hold ---
    before_bb, after_bb = bake_prop(prop)
    delta = bbox_delta(before_bb, after_bb)
    print(
        f"world_bbox_delta={delta:.3e} "
        f"before_min={tuple(round(c, 6) for c in before_bb[0])} "
        f"after_min={tuple(round(c, 6) for c in after_bb[0])}"
    )
    if delta > WORLD_EPS:
        print(
            f"ERROR: world bbox moved across bake (delta={delta:.3e} > {WORLD_EPS})",
            file=sys.stderr,
        )
        return 4

    sx, sy, sz = prop.scale
    if abs(sx - 1.0) > 0 or abs(sy - 1.0) > 0 or abs(sz - 1.0) > 0:
        print(f"ERROR: scale after bake is {(sx, sy, sz)}, want (1,1,1)", file=sys.stderr)
        return 5
    print(f"scale_ok scale={(sx, sy, sz)}")

    mn, mx = local_bbox(prop.data)
    print(f"local_bbox min={tuple(round(c, 6) for c in mn)} max={tuple(round(c, 6) for c in mx)}")
    if abs(mn.z) > BBOX_EPS:
        print(f"ERROR: local min.z={mn.z:.6f} != 0 (origin not at base)", file=sys.stderr)
        return 6
    if abs(0.5 * (mn.x + mx.x)) > BBOX_EPS or abs(0.5 * (mn.y + mx.y)) > BBOX_EPS:
        print(
            f"ERROR: local XY center not at origin "
            f"(cx={0.5*(mn.x+mx.x):.6f} cy={0.5*(mn.y+mx.y):.6f})",
            file=sys.stderr,
        )
        return 6
    print(f"origin_base_ok min_z={mn.z:.3e}")

    # --- 2. Bare-parent trap on the accessory, then MPI fix ---
    view_layer.update()
    w0 = acc.matrix_world.translation.copy()
    # Move parent so bare parenting has something to fight against
    prop.location.z += 0.4
    prop.rotation_euler.z = math.radians(25)
    view_layer.update()

    acc.parent = prop  # bare — must jump
    view_layer.update()
    jumped = (acc.matrix_world.translation - w0).length
    print(f"bare_parent_jump={jumped:.6f}")
    if jumped < JUMP_MIN:
        print(
            f"ERROR: bare parenting moved accessory only {jumped:.6f} "
            f"(expected jump >= {JUMP_MIN}) — trap not witnessed",
            file=sys.stderr,
        )
        return 7

    if not skip_mpi:
        acc.matrix_parent_inverse = prop.matrix_world.inverted()
        view_layer.update()
    err = (acc.matrix_world.translation - w0).length
    print(f"mpi_restore_err={err:.3e}")
    if err > MPI_EPS:
        print(
            f"ERROR: matrix_parent_inverse failed to restore world location "
            f"(err={err:.3e} > {MPI_EPS})",
            file=sys.stderr,
        )
        return 8

    print(
        f"prop-origin-transform OK scale=(1,1,1) min_z={mn.z:.3e} "
        f"world_bbox_delta={delta:.3e} bare_jump={jumped:.6f} mpi_err={err:.3e}"
    )
    return 0


# ---------------------------------------------------------------------------
# Render


def ghost_of(sc, src, name, mat):
    """Glowing wire outline of *src* at its current world pose: where the
    accessory belongs. A Wireframe modifier on a copy, every slot the ghost
    material."""
    me = src.data.copy()
    me.name = name
    for i in range(len(me.materials)):
        me.materials[i] = mat
    ob = bpy.data.objects.new(name, me)
    ob.matrix_world = src.matrix_world.copy()
    sc.collection.objects.link(ob)
    wf = ob.modifiers.new("Outline", "WIREFRAME")
    wf.thickness = 0.005
    wf.use_replace = True
    wf.use_even_offset = True
    return ob


def pivot_marker(sc, name, origin, rot_z, mats, reach):
    """Floor pivot target centred on the object origin: a thin ring around
    the footing with crosshair notches on the object's X and Y axes. The
    origin itself is under the base, so the marker frames it."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        up = Vector((0, 0, 1))
        part = Part(bm)
        bmesh.ops.create_circle(bm, cap_ends=False, segments=96, radius=reach)
        ring_edges = [e for e in bm.edges]
        ext = bmesh.ops.extrude_edge_only(bm, edges=ring_edges)
        nv = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.scale(bm, vec=(1 + 0.018 / reach, 1 + 0.018 / reach, 1), verts=nv)
        bmesh.ops.translate(bm, vec=(0, 0, 0.003), verts=part.verts())
        part.finish(2)
        # Crosshair notches on the object's own X (red) and Y (green) axes:
        # the lines they sight along cross at the origin, under the base.
        for k in range(4):
            a = k * math.pi / 2
            d = Vector((math.cos(a), math.sin(a), 0.0))
            mid = d * (reach - 0.05) + up * 0.006
            box(bm, mid, (0.17, 0.028, 0.008), k % 2,
                bevel=0.003, rot=Matrix.Rotation(a, 4, "Z"))
        bm.to_mesh(me)
    finally:
        bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    ob.location = origin
    ob.rotation_euler.z = rot_z
    sc.collection.objects.link(ob)
    return ob


def build_studio(sc):
    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = make_material("Studio", (0.03, 0.032, 0.037), rough=0.7, metallic=0.0)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    sc.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 7.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02, 0.021, 0.025, 1.0,
    )
    sc.world = world

    def light(name, loc, energy, size, col, target):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(ob)

    light("Key", (-3.0, -4.0, 5.0), 340.0, 3.0, (1.0, 0.86, 0.68), (0.2, 0, 0.6))
    light("Fill", (4.5, -4.0, 2.2), 45.0, 8.0, (0.75, 0.85, 1.0), (0.2, 0, 0.6))
    light("Rim", (1.0, 3.0, 4.2), 150.0, 2.5, (0.6, 0.78, 1.0), (0.2, 0, 1.0))
    light("Wedge", (2.0, 4.0, 3.5), 380.0, 6.0, (1.0, 0.68, 0.36), (0.5, 7.0, 0.7))
    return floor, wall


def render_still(path, engine):
    """Two baked pedestals. Left: the conduit parented with MPI stays seated.
    Right: bare `child.parent = parent` double-applies the parent transform
    and the elbow is left hanging off its mount, a glowing outline marking
    the seat it left."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    def make_prop(name, loc, rot_z):
        ob = bpy.data.objects.new(name, build_pedestal_mesh(name))
        ob.scale = PROP_SCALE
        ob.location = loc
        sc.collection.objects.link(ob)
        bake_prop(ob)
        # Sit the baked base on the floor and turn it to its placement.
        ob.location = loc
        ob.rotation_euler.z = rot_z
        bpy.context.view_layer.update()
        return ob

    def seat_conduit(name, prop):
        ob = bpy.data.objects.new(name, build_accessory_mesh(name))
        ob.matrix_world = prop.matrix_world @ Matrix.Translation(MOUNT)
        sc.collection.objects.link(ob)
        bpy.context.view_layer.update()
        return ob

    # Both stand on a kerbed sidewalk slab, so their origins sit SLAB_H above
    # the studio floor: the bare parent's doubled translation lifts the
    # stranded elbow off the slab instead of sliding it along the floor.
    slab_me = bpy.data.meshes.new("Sidewalk")
    bm = bmesh.new()
    try:
        box(bm, (-0.2, 0.15, SLAB_H / 2), (3.3, 1.8, SLAB_H), 0, bevel=0.02)
        bm.to_mesh(slab_me)
    finally:
        bm.free()
    slab_me.materials.append(make_material("Paving", (0.035, 0.035, 0.038), rough=0.9,
                                           metallic=0.0))
    slab = bpy.data.objects.new("Sidewalk", slab_me)
    sc.collection.objects.link(slab)

    keep = make_prop("Pedestal.Keep", Vector((-0.95, 0.35, SLAB_H)), math.radians(-18))
    trap = make_prop("Pedestal.Trap", Vector((0.62, 0.05, SLAB_H)), math.radians(-12))

    keep_acc = seat_conduit("Conduit.Keep", keep)
    parent_keep_world(keep_acc, keep)
    bpy.context.view_layer.update()

    trap_acc = seat_conduit("Conduit.Trap", trap)
    seat_world = trap_acc.matrix_world.copy()
    trap_acc.parent = trap  # bare — the trap
    bpy.context.view_layer.update()
    jumped_world = trap_acc.matrix_world.copy()
    jumped = (jumped_world.translation - seat_world.translation).length
    # Freeze the teleported pose so the still does not depend on the parent.
    trap_acc.parent = None
    trap_acc.matrix_world = jumped_world
    bpy.context.view_layer.update()
    print(f"render_trap_jump={jumped:.4f} "
          f"seat={tuple(round(c, 3) for c in seat_world.translation)} "
          f"landed={tuple(round(c, 3) for c in jumped_world.translation)}")

    ghost_m = make_material("SeatGhost", (0.2, 0.75, 1.0), rough=0.5, metallic=0.0,
                            emit=(0.25, 0.8, 1.0), estr=3.0)
    ghost = bpy.data.objects.new("Conduit.Trap.Seat", trap_acc.data)
    ghost.matrix_world = seat_world
    sc.collection.objects.link(ghost)
    ghost = ghost_of(sc, ghost, "SeatOutline", ghost_m)
    bpy.data.objects.remove(bpy.data.objects["Conduit.Trap.Seat"])

    pmats = [
        make_material("PivotX", (0.9, 0.08, 0.06), rough=0.4, metallic=0.0,
                      emit=(0.9, 0.08, 0.06), estr=0.4),
        make_material("PivotY", (0.25, 0.85, 0.08), rough=0.4, metallic=0.0,
                      emit=(0.25, 0.85, 0.08), estr=0.4),
        make_material("PivotRing", (0.6, 0.5, 0.36), rough=0.5, metallic=0.0,
                      emit=(1.0, 0.78, 0.5), estr=0.12),
    ]
    markers = [
        pivot_marker(sc, "Pivot.Keep", keep.matrix_world.translation, keep.rotation_euler.z,
                     pmats, 0.72),
        pivot_marker(sc, "Pivot.Trap", trap.matrix_world.translation, trap.rotation_euler.z,
                     pmats, 0.72),
    ]

    floor, wall = build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 56.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.1, -5.6, 2.05)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.2, 0.1, 0.66)
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
    # Standard, not AgX: AgX pales the paint and conduit and lifts the stage.
    sc.view_settings.view_transform = "Standard"
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact.
    hero = [keep, trap, keep_acc, trap_acc]
    fcode = gallery_framing.check_framing(
        sc, cam,
        hero=hero,
        elements=hero + [ghost] + markers,
        stage=[floor, wall, slab],
    )
    if fcode:
        return fcode
    aqcode = gallery_asset_quality.check_asset_quality(
        sc, cam, hero=[keep, keep_acc], stage=[floor, wall, slab])
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
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--skip-mpi", action="store_true",
                   help="parent the accessory without MPI (must fail)")
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    sc, prop, acc = build_scene()
    code = check(prop, acc, skip_mpi=args.skip_mpi)
    if code:
        return code

    if args.output:
        rcode = render_still(os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("prop-origin-transform OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
