"""Prop origin transform — base-center origin + scale apply + MPI accessory.

Witnesses the object-level contract a prop pipeline relies on before engine
ingest: origin at the local base center, scale applied through the data API
to exactly (1,1,1), world bbox unchanged across the bake, and
`matrix_parent_inverse` so a parented accessory does not teleport. Extends
`parent-inverse-orrery` (MPI idiom + stale `matrix_world`) without retreading
orbits — subject is a street utility pedestal with a bolted conduit accessory.

By default it runs only the correctness check (no render). Pass --output
to also render a still:

    blender --background --python prop_origin_transform.py --
    blender --background --python prop_origin_transform.py -- --output o.png
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Matrix, Vector

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

BBOX_EPS = 1e-6
WORLD_EPS = 1e-5
MPI_EPS = 1e-6
STALE_EPS = 1e-9
JUMP_MIN = 0.05


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


def build_pedestal_mesh():
    """Stepped street pedestal mesh in local space (origin roughly at center)."""
    rings = [
        (0.55, 0.45, -0.70),
        (0.55, 0.45, -0.52),
        (0.42, 0.34, -0.52),
        (0.42, 0.34, 0.55),
        (0.48, 0.38, 0.55),
        (0.48, 0.38, 0.70),
    ]
    me = bpy.data.meshes.new("Pedestal")
    bm = bmesh.new()
    try:
        ring_verts = []
        for hx, hy, z in rings:
            ring_verts.append([
                bm.verts.new((-hx, -hy, z)),
                bm.verts.new((hx, -hy, z)),
                bm.verts.new((hx, hy, z)),
                bm.verts.new((-hx, hy, z)),
            ])
        for i in range(len(ring_verts) - 1):
            a, b = ring_verts[i], ring_verts[i + 1]
            for k in range(4):
                n = (k + 1) % 4
                bm.faces.new((a[k], a[n], b[n], b[k]))
        bot, top = ring_verts[0], ring_verts[-1]
        bm.faces.new((bot[0], bot[3], bot[2], bot[1]))
        bm.faces.new((top[0], top[1], top[2], top[3]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def build_accessory_mesh():
    """Flanged conduit stub — short pipe + mounting flange + bolt heads."""
    me = bpy.data.meshes.new("Conduit")
    bm = bmesh.new()
    try:
        # Barrel along +Y (away from prop face when mounted); origin at flange face
        barrel = bmesh.ops.create_cone(
            bm, cap_ends=True, segments=16, radius1=0.09, radius2=0.08, depth=0.48,
        )
        bmesh.ops.rotate(
            bm, verts=barrel["verts"], cent=(0, 0, 0),
            matrix=Matrix.Rotation(math.radians(90), 4, "X"),
        )
        bmesh.ops.translate(bm, vec=(0.0, -0.24, 0.0), verts=barrel["verts"])
        # Thick mounting flange at the prop-facing (+Y local before rotate → y≈0)
        flange = bmesh.ops.create_cone(
            bm, cap_ends=True, segments=20, radius1=0.20, radius2=0.20, depth=0.06,
        )
        bmesh.ops.rotate(
            bm, verts=flange["verts"], cent=(0, 0, 0),
            matrix=Matrix.Rotation(math.radians(90), 4, "X"),
        )
        bmesh.ops.translate(bm, vec=(0.0, 0.03, 0.0), verts=flange["verts"])
        # Four bolt heads on the flange face (camera-visible when seated)
        for ang in (45, 135, 225, 315):
            rad = math.radians(ang)
            bx, bz = 0.14 * math.cos(rad), 0.14 * math.sin(rad)
            br = bmesh.ops.create_cone(
                bm, cap_ends=True, segments=8, radius1=0.032, radius2=0.032, depth=0.04,
            )
            bmesh.ops.rotate(
                bm, verts=br["verts"], cent=(0, 0, 0),
                matrix=Matrix.Rotation(math.radians(90), 4, "X"),
            )
            bmesh.ops.translate(bm, vec=(bx, 0.07, bz), verts=br["verts"])
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def build_socket_mesh():
    """Deep mount well — shadowed interior reads as the vacated seat."""
    me = bpy.data.meshes.new("Socket")
    bm = bmesh.new()
    try:
        # Outer collar (matches flange OD)
        bmesh.ops.create_cone(
            bm, cap_ends=True, segments=24, radius1=0.24, radius2=0.24, depth=0.07,
        )
        # Deep dark well — into the prop after rotate
        well = bmesh.ops.create_cone(
            bm, cap_ends=True, segments=20, radius1=0.13, radius2=0.11, depth=0.18,
        )
        bmesh.ops.translate(bm, vec=(0.0, 0.0, -0.06), verts=well["verts"])
        # Backstop disk (shadowed pocket floor)
        floor = bmesh.ops.create_cone(
            bm, cap_ends=True, segments=16, radius1=0.10, radius2=0.10, depth=0.025,
        )
        bmesh.ops.translate(bm, vec=(0.0, 0.0, -0.16), verts=floor["verts"])
        bmesh.ops.rotate(
            bm, verts=bm.verts, cent=(0, 0, 0),
            matrix=Matrix.Rotation(math.radians(90), 4, "X"),
        )
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


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

    body_m = make_material("Body", (0.20, 0.38, 0.34), rough=0.42, metallic=0.55)
    acc_m = make_material("Conduit", (0.45, 0.42, 0.28), rough=0.4, metallic=0.7)

    me = build_pedestal_mesh()
    me.materials.append(body_m)
    for p in me.polygons:
        p.use_smooth = False
    prop = bpy.data.objects.new("StreetPedestal", me)
    # Intentionally wrong for ingest: non-uniform scale, origin at geometry center
    prop.scale = (1.15, 0.92, 1.08)
    prop.location = (0.0, 0.0, 0.0)
    sc.collection.objects.link(prop)

    ame = build_accessory_mesh()
    ame.materials.append(acc_m)
    acc = bpy.data.objects.new("Accessory", ame)
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


def check(prop, acc):
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


def origin_marker(sc, loc):
    """Small emissive triad at the object origin — scene evidence, not a light."""
    mat = make_material(
        "OriginMark", (1.0, 0.55, 0.1), rough=0.35, metallic=0.0,
        emit=(1.0, 0.6, 0.1), estr=2.2,
    )
    me = bpy.data.meshes.new("OriginBead")
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=8, radius=0.09)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new("OriginBead", me)
    ob.location = loc
    sc.collection.objects.link(ob)
    # Axis stubs
    for axis, rgb, rot in (
        ("X", (1.0, 0.2, 0.15), (0, math.radians(90), 0)),
        ("Y", (0.2, 1.0, 0.25), (math.radians(-90), 0, 0)),
        ("Z", (0.25, 0.45, 1.0), (0, 0, 0)),
    ):
        ame = bpy.data.meshes.new(f"Axis{axis}")
        abm = bmesh.new()
        try:
            bmesh.ops.create_cone(
                abm, cap_ends=True, segments=8, radius1=0.015, radius2=0.015, depth=0.28,
            )
            bmesh.ops.translate(abm, vec=(0, 0, 0.14), verts=abm.verts)
            abm.to_mesh(ame)
        finally:
            abm.free()
        am = make_material(
            f"Axis{axis}", rgb, rough=0.4, metallic=0.0, emit=rgb, estr=1.5,
        )
        ame.materials.append(am)
        aob = bpy.data.objects.new(f"Axis{axis}", ame)
        aob.location = loc
        aob.rotation_euler = rot
        sc.collection.objects.link(aob)


def placard(sc, text, loc, size=0.18):
    cu = bpy.data.curves.new(text, "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new(text, cu)
    ob.location = loc
    sc.collection.objects.link(ob)
    mat = make_material("Label", (0.92, 0.92, 0.94), rough=0.6, metallic=0.0)
    ob.data.materials.append(mat)
    return ob


def build_studio(sc):
    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = make_material("Studio", (0.03, 0.032, 0.037), rough=0.7, metallic=0.0)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    sc.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02, 0.021, 0.025, 1.0,
    )
    sc.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        sc.collection.objects.link(ob)

    light("Key", (-3.5, -4.5, 5.5), 480.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5.0, -3.5, 2.5), 120.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Rim", (1.5, 4.5, 3.5), 280.0, 3.0, (0.6, 0.78, 1.0), (-55, 0, 170))
    light("Wedge", (2.5, 5.5, 4.0), 400.0, 6.0, (1.0, 0.72, 0.42), (-68, 0, 190))
    return floor, wall


def render_still(path, engine):
    """Dual panel: bare-parent TRAP (left) vs MPI KEEP (right) + origin at base."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    # Teal pedestal — accessory shares metal fitting in the same family (no
    # primary-color emission blobs). Empty socket is a dark recessed well.
    body_m = make_material("BodyR", (0.14, 0.48, 0.42), rough=0.4, metallic=0.55)
    acc_m = make_material("AccR", (0.42, 0.44, 0.40), rough=0.32, metallic=0.88)
    sock_m = make_material("Socket", (0.06, 0.07, 0.08), rough=0.7, metallic=0.2)
    sock_empty_m = make_material(
        "SocketEmpty", (0.015, 0.018, 0.02), rough=0.95, metallic=0.0,
    )

    def make_prop(name, loc, rot_z=0.0):
        me = build_pedestal_mesh()
        me.materials.append(body_m)
        for p in me.polygons:
            p.use_smooth = False
        ob = bpy.data.objects.new(name, me)
        ob.scale = (1.15, 0.92, 1.08)
        ob.location = loc
        sc.collection.objects.link(ob)
        bpy.context.view_layer.update()
        apply_scale_data_api(ob)
        bpy.context.view_layer.update()
        origin_to_base_center(ob)
        bpy.context.view_layer.update()
        wb = world_bbox(ob)
        ob.location.z -= wb[0].z
        ob.rotation_euler.z = rot_z
        bpy.context.view_layer.update()
        return ob

    def make_acc(name, world_loc, mat):
        me = build_accessory_mesh()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = world_loc
        sc.collection.objects.link(ob)
        return ob

    def make_socket(name, world_loc, mat, parent=None):
        me = build_socket_mesh()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = world_loc
        sc.collection.objects.link(ob)
        bpy.context.view_layer.update()
        if parent is not None:
            parent_keep_world(ob, parent)
            bpy.context.view_layer.update()
        return ob

    left = make_prop("TrapProp", (0.0, 0.0, 0.0), rot_z=math.radians(55))
    right = make_prop("KeepProp", (2.2, 0.0, 0.0), rot_z=math.radians(-10))

    bpy.context.view_layer.update()
    left_front = left.matrix_world @ Vector((0.0, -0.52, 0.78))
    right_front = right.matrix_world @ Vector((0.0, -0.52, 0.78))

    trap_sock = make_socket("TrapSocket", left_front, sock_empty_m, parent=left)
    keep_sock = make_socket("KeepSocket", right_front, sock_m, parent=right)

    trap_acc = make_acc("TrapAcc", left_front + Vector((0.0, -0.05, 0.0)), acc_m)
    keep_acc = make_acc("KeepAcc", right_front + Vector((0.0, -0.05, 0.0)), acc_m)
    trap_acc.scale = (1.55, 1.55, 1.55)
    keep_acc.scale = (1.55, 1.55, 1.55)
    bpy.context.view_layer.update()

    w_before = trap_acc.matrix_world.translation.copy()
    trap_acc.parent = left
    bpy.context.view_layer.update()
    jumped = (trap_acc.matrix_world.translation - w_before).length
    jumped_world = trap_acc.matrix_world.copy()
    trap_acc.parent = None
    bpy.context.view_layer.update()
    trap_acc.matrix_world = jumped_world
    bpy.context.view_layer.update()
    print(
        f"render_trap_jump={jumped:.4f} "
        f"acc_at={tuple(round(c, 3) for c in trap_acc.matrix_world.translation)} "
        f"sock_at={tuple(round(c, 3) for c in left_front)} "
        f"sep={(trap_acc.matrix_world.translation - left_front).length:.4f}"
    )

    parent_keep_world(keep_acc, right)
    bpy.context.view_layer.update()

    origin_marker(sc, Vector(left.matrix_world.translation))
    origin_marker(sc, Vector(right.matrix_world.translation))

    p_trap = placard(sc, "TRAP", (0.15, -1.25, 0.02), size=0.11)
    p_keep = placard(sc, "MPI KEEP", (2.1, -1.25, 0.02), size=0.11)

    floor, wall = build_studio(sc)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 48.0
    cam = bpy.data.objects.new("Cam", cam_data)
    # Pulled back until the framing gate's margins clear — not further.
    cam.location = (1.15, -5.9, 1.55)
    sc.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (1.1, 0.0, 0.72)
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
    sc.view_settings.view_transform = "Standard"
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact.
    hero = [left, right, trap_acc, keep_acc, trap_sock, keep_sock]
    markers = [o for o in sc.objects if o.name.startswith(("OriginBead", "Axis"))]
    fcode = gallery_framing.check_framing(
        sc, cam,
        hero=hero,
        elements=hero + [p_trap, p_keep] + markers,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
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
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    sc, prop, acc = build_scene()
    code = check(prop, acc)
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
