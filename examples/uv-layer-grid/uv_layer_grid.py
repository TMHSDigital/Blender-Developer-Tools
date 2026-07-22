"""UV-layer authoring hazard — a runnable example.

Witnesses that `bmesh.ops.create_grid(..., calc_uvs=True)` silently creates
*no* UV layer unless one already exists on the BMesh. AI-generated Blender
code commonly trusts `calc_uvs=True` and then wires an Image Texture; without
a UV layer every fragment samples texel (0, 0) and the mesh renders as one
flat color.

The check proves the silent no-op, then the pre-create + `calc_uvs=True`
repair path against a closed-form UV grid, and an explicit loop-assignment
fallback that does not depend on `calc_uvs` at all. Pass --output to also
render a still that stages the broken (flat) panel beside the repaired
(checker) panel — and then *witnesses the render itself*: the saved PNG is
read back and probed at each panel's projected center, asserting the broken
panel is one flat teal (texel (0,0)) while the repaired panel carries both
checker colors. If the UV contract failed, the pixels would say so:

    blender --background --python uv_layer_grid.py --
    blender --background --python uv_layer_grid.py -- --output uv.png
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

SEG = 8
SIZE = 1.0
UV_TOL = 1e-6


def expect_uv(co):
    """Closed-form UV for create_grid verts spanning [-SIZE, SIZE] in X/Y."""
    return ((co.x / SIZE) + 1.0) * 0.5, ((co.y / SIZE) + 1.0) * 0.5


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def max_uv_err(bm, uv_layer):
    err = 0.0
    for face in bm.faces:
        for loop in face.loops:
            ex, ey = expect_uv(loop.vert.co)
            got = loop[uv_layer].uv
            err = max(err, abs(got.x - ex), abs(got.y - ey))
    return err


def check():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # --- 1. The hazard: calc_uvs=True is a silent no-op without a UV layer ---
    me_bad = bpy.data.meshes.new("NoPreUV")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(
            bm, x_segments=SEG, y_segments=SEG, size=SIZE, calc_uvs=True,
        )
        n_layers = len(bm.loops.layers.uv)
        n_faces = len(bm.faces)
        n_verts = len(bm.verts)
        bm.to_mesh(me_bad)
    finally:
        bm.free()

    if n_layers != 0:
        return fail(
            f"calc_uvs=True without a pre-existing layer created {n_layers} "
            f"UV layer(s) — the silent-no-op hazard is gone (or changed)",
            3,
        )
    if len(me_bad.uv_layers) != 0:
        return fail(
            f"mesh gained {len(me_bad.uv_layers)} UV layer(s) after "
            f"calc_uvs=True with no pre-create",
            3,
        )
    expect_faces = SEG * SEG
    expect_verts = (SEG + 1) * (SEG + 1)
    if (n_faces, n_verts) != (expect_faces, expect_verts):
        return fail(
            f"grid topology {(n_verts, n_faces)} != "
            f"expected {(expect_verts, expect_faces)}",
            4,
        )

    # --- 2. Repair: pre-create the layer, then calc_uvs=True fills it -----
    me_ok = bpy.data.meshes.new("PreUV")
    bm = bmesh.new()
    try:
        bm.loops.layers.uv.new("UVMap")
        bmesh.ops.create_grid(
            bm, x_segments=SEG, y_segments=SEG, size=SIZE, calc_uvs=True,
        )
        if len(bm.loops.layers.uv) != 1:
            return fail(
                f"pre-create + calc_uvs left {len(bm.loops.layers.uv)} "
                f"layers (expected 1)",
                5,
            )
        uv = bm.loops.layers.uv.active
        calc_err = max_uv_err(bm, uv)
        bm.to_mesh(me_ok)
    finally:
        bm.free()

    if calc_err > UV_TOL:
        return fail(
            f"calc_uvs closed-form error {calc_err:.2e} > {UV_TOL:.0e}",
            6,
        )
    if len(me_ok.uv_layers) != 1 or me_ok.uv_layers.active is None:
        return fail("pre-create path did not persist a UV layer on the mesh", 5)

    # Mesh-side round-trip of the same closed form (loop data, not bmesh).
    mesh_err = 0.0
    uv_data = me_ok.uv_layers.active.data
    for poly in me_ok.polygons:
        for li in poly.loop_indices:
            vi = me_ok.loops[li].vertex_index
            ex, ey = expect_uv(me_ok.vertices[vi].co)
            got = uv_data[li].uv
            mesh_err = max(mesh_err, abs(got.x - ex), abs(got.y - ey))
    if mesh_err > UV_TOL:
        return fail(
            f"mesh UV round-trip error {mesh_err:.2e} > {UV_TOL:.0e}",
            7,
        )

    # --- 3. Explicit assignment fallback (does not rely on calc_uvs) -------
    me_ex = bpy.data.meshes.new("ExplicitUV")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(
            bm, x_segments=SEG, y_segments=SEG, size=SIZE, calc_uvs=False,
        )
        if len(bm.loops.layers.uv) != 0:
            return fail(
                "create_grid(calc_uvs=False) unexpectedly created a UV layer",
                8,
            )
        uv = bm.loops.layers.uv.new("UVMap")
        for face in bm.faces:
            for loop in face.loops:
                loop[uv].uv = expect_uv(loop.vert.co)
        explicit_err = max_uv_err(bm, uv)
        bm.to_mesh(me_ex)
    finally:
        bm.free()

    if explicit_err > UV_TOL:
        return fail(
            f"explicit UV assignment error {explicit_err:.2e} > {UV_TOL:.0e}",
            9,
        )

    print(
        f"hazard confirmed: calc_uvs=True alone → 0 UV layers "
        f"(grid {n_verts}v/{n_faces}f); "
        f"pre-create + calc_uvs max err {calc_err:.2e} "
        f"(mesh round-trip {mesh_err:.2e}); "
        f"explicit assign max err {explicit_err:.2e} "
        f"(tol {UV_TOL:.0e})"
    )
    return 0


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def make_uv_testcard(name, w=256, h=256):
    """Neon checker whose single texel (0,0) is a flat teal, so a missing UV
    layer reads as one solid color instead of a bright false-positive checker."""
    img = bpy.data.images.new(name, w, h, alpha=False)
    px = [0.0] * (w * h * 4)
    cell = w // 8
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 4
            cx, cy = x // cell, y // cell
            # bottom-left origin: (0,0) is the first pixel the shader samples
            # when no UV layer exists.
            if x == 0 and y == 0:
                # Distinct flat teal — readable as "wrong" at thumbnail scale,
                # still obviously not the checker.
                px[i:i + 4] = [0.04, 0.28, 0.38, 1.0]
                continue
            if (cx + cy) % 2 == 0:
                # warm magenta
                px[i:i + 4] = [0.95, 0.12, 0.55, 1.0]
            else:
                # electric cyan
                px[i:i + 4] = [0.08, 0.85, 0.95, 1.0]
            # saturation wash by U so the gradient is readable at thumbnail
            u = x / (w - 1)
            px[i] = min(1.0, px[i] * (0.55 + 0.45 * u))
            px[i + 2] = min(1.0, px[i + 2] * (0.55 + 0.45 * (1.0 - u)))
    img.pixels.foreach_set(px)
    return img


def specular_off(bsdf):
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.0


def textured_plane(name, image, with_uvs):
    """Unit grid plane (+/- SIZE). with_uvs=False leaves the hazard in place."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        if with_uvs:
            bm.loops.layers.uv.new("UVMap")
        bmesh.ops.create_grid(
            bm, x_segments=SEG, y_segments=SEG, size=SIZE, calc_uvs=with_uvs,
        )
        bm.to_mesh(me)
    finally:
        bm.free()

    mat = bpy.data.materials.new(name + "Mat")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.interpolation = "Closest"
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    specular_off(bsdf)
    # Emission so the checker reads as authored color, not lit albedo.
    links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.95
    me.materials.append(mat)

    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def render_still(path, engine):
    scene = bpy.context.scene
    card = make_uv_testcard("UVCard")

    # --- Staging materials: quiet and dark, the panel faces carry the color --
    def pbr(name, base, rough, metal=0.0):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*base, 1.0)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        return m

    frame_mat = pbr("Frame", (0.05, 0.053, 0.06), 0.32, 0.65)
    stand_mat = pbr("Stand", (0.032, 0.035, 0.042), 0.45, 0.4)
    led_mat = pbr("Led", (0.0, 0.0, 0.0), 0.6)
    led_b = led_mat.node_tree.nodes["Principled BSDF"]
    led_b.inputs["Emission Color"].default_value = (1.0, 0.45, 0.12, 1.0)
    led_b.inputs["Emission Strength"].default_value = 4.0

    def box(name, dims, loc, rot, mat, bevel=0.0):
        dx, dy, dz = (d * 0.5 for d in dims)
        verts = [
            (-dx, -dy, -dz), (dx, -dy, -dz), (dx, dy, -dz), (-dx, dy, -dz),
            (-dx, -dy, dz), (dx, -dy, dz), (dx, dy, dz), (-dx, dy, dz),
        ]
        faces = [
            (0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
            (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7),
        ]
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        ob.rotation_euler = rot
        scene.collection.objects.link(ob)
        if bevel > 0.0:
            mod = ob.modifiers.new("Edge", "BEVEL")
            mod.width = bevel
            mod.segments = 2
        return ob

    def bar_between(name, p1, p2, width, mat):
        a, b = Vector(p1), Vector(p2)
        d = b - a
        ob = box(name, (width, width, d.length), (a + b) * 0.5, (0, 0, 0), mat, 0.01)
        ob.rotation_mode = "QUATERNION"
        ob.rotation_quaternion = d.to_track_quat("Z", "Y")
        return ob

    # --- Two framed lightbox displays, each on a floor tray with a rear
    # kick leg. The face planes keep their origins at the face centers (the
    # pixel witness probes the projected centers), with a ~0.2-unit bezel
    # between the face edge and the frame so the probed patch stays on data.
    LEAN = math.radians(75.0)  # 15° back off vertical, easel-like

    def display(name, with_uvs, cx, cy, yaw_deg):
        yaw = math.radians(yaw_deg)
        asm = bpy.data.objects.new(name + "Asm", None)
        asm.rotation_euler = (LEAN, 0.0, yaw)
        rot = asm.rotation_euler.to_matrix()
        # Face-center height such that the frame's bottom edge rests in tray.
        contact = rot @ Vector((0.0, -1.17, 0.02))
        asm.location = (cx, cy, 0.07 - contact.z)
        scene.collection.objects.link(asm)

        # Left: the hazard — calc_uvs alone, no UV layer → flat teal of
        # texel (0,0). Right: the repair — pre-create, then calc_uvs fills.
        face = textured_plane(name, card, with_uvs)
        face.parent = asm
        face.location = (0.0, 0.0, 0.075)

        plate = box(name + "Back", (2.34, 2.34, 0.14), (0, 0, 0), (0, 0, 0),
                    frame_mat, 0.02)
        plate.parent = asm
        bezels = (
            ((2.34, 0.17, 0.20), (0.0, 1.085, 0.02)),
            ((2.34, 0.17, 0.20), (0.0, -1.085, 0.02)),
            ((0.17, 2.0, 0.20), (1.085, 0.0, 0.02)),
            ((0.17, 2.0, 0.20), (-1.085, 0.0, 0.02)),
        )
        for i, (dims, loc) in enumerate(bezels):
            bez = box(f"{name}Bez{i}", dims, loc, (0, 0, 0), frame_mat, 0.02)
            bez.parent = asm
        led = box(name + "Led", (0.06, 0.03, 0.035), (0.92, -1.085, 0.128),
                  (0, 0, 0), led_mat, 0.008)
        led.parent = asm

        base = asm.location
        box(name + "Tray", (2.0, 0.32, 0.10),
            (base.x + contact.x, base.y + contact.y, 0.05),
            (0, 0, yaw), stand_mat, 0.02)
        back = rot @ Vector((0.0, 0.0, -1.0))
        back.z = 0.0
        back.normalize()
        for side in (-0.75, 0.75):
            attach = base + rot @ Vector((side, 0.55, -0.12))
            foot = (base.x + contact.x + side * math.cos(yaw) + back.x * 0.85,
                    base.y + contact.y - side * math.sin(yaw) + back.y * 0.85,
                    0.02)
            bar_between(f"{name}Leg{side:+.2f}", attach, foot, 0.06, stand_mat)

    display("Broken", False, -1.38, 0.30, 6.0)
    display("Fixed", True, 1.45, -0.10, 9.0)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = bpy.data.materials.new("Studio")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 6.8, 0.0)
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

    # Aimed steeply down so its spill dies on the floor, not on the wall.
    light("Key", (-4.4, -4.2, 6.4), 340.0, 5.0, (1.0, 0.96, 0.9), (60, 0, -32))
    light("Fill", (4.8, -2.8, 1.6), 80.0, 9.0, (0.75, 0.85, 1.0), (72, 0, 52))
    light("Rim", (0.2, 4.6, 3.0), 250.0, 3.5, (0.6, 0.78, 1.0), (-42, 0, 178))
    # Uplight between the displays and the wall, raking UP the backdrop: the
    # visible wall band above the panel tops only spans z≈2.8–3.4, so the
    # warm pool is aimed to live there instead of hiding behind the panels.
    light("Wedge", (-2.2, 5.6, 2.3), 480.0, 3.0, (1.0, 0.76, 0.5), (-117, 0, 180))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.1, 0.05, 1.0)
    scene.collection.objects.link(aim)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 48.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (3.1, -8.35, 2.2)
    con = cam.constraints.new("TRACK_TO")
    con.target = aim
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    scene.collection.objects.link(cam)
    scene.camera = cam

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 64
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    # AgX desaturates the neon checker toward pastel — Standard keeps it honest.
    scene.view_settings.view_transform = "Standard"
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def patch_stats(px, w, h, cx, cy, half):
    """Mean RGB and per-channel min/max spread of a (2*half)^2 pixel patch."""
    sums = [0.0, 0.0, 0.0]
    lo = [1.0, 1.0, 1.0]
    hi = [0.0, 0.0, 0.0]
    n = 0
    for y in range(max(0, cy - half), min(h, cy + half)):
        for x in range(max(0, cx - half), min(w, cx + half)):
            i = (y * w + x) * 4
            for c in range(3):
                v = px[i + c]
                sums[c] += v
                lo[c] = min(lo[c], v)
                hi[c] = max(hi[c], v)
            n += 1
    mean = [s / n for s in sums]
    spread = max(hi[c] - lo[c] for c in range(3))
    return mean, spread


def verify_still(path):
    """Witness the render itself: the broken panel must be one flat teal, the
    repaired panel a high-contrast checker. Probes the saved PNG at each
    panel's projected center, so a failed UV contract cannot ship a still."""
    from bpy_extras.object_utils import world_to_camera_view

    scene = bpy.context.scene
    bpy.context.view_layer.update()
    img = bpy.data.images.load(path)
    try:
        w, h = img.size
        px = [0.0] * (w * h * 4)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)

    half = max(8, int(w * 0.055))  # ~70 px at 1280: spans >1 checker cell
    stats = {}
    for name in ("Broken", "Fixed"):
        obj = bpy.data.objects[name]
        ndc = world_to_camera_view(scene, scene.camera, obj.matrix_world.translation)
        cx, cy = int(ndc.x * w), int(ndc.y * h)
        stats[name] = patch_stats(px, w, h, cx, cy, half)

    (b_mean, b_spread), (f_mean, f_spread) = stats["Broken"], stats["Fixed"]
    print(
        f"pixel witness: broken mean rgb=({b_mean[0]:.3f},{b_mean[1]:.3f},"
        f"{b_mean[2]:.3f}) spread={b_spread:.4f}; fixed spread={f_spread:.4f}"
    )
    if b_spread > 0.02:
        return fail(
            f"broken panel is not flat (spread {b_spread:.4f} > 0.02) — "
            f"the hazard did not render as one color",
            11,
        )
    if not (b_mean[2] > b_mean[1] > b_mean[0]):
        return fail(
            f"broken panel is not the teal of texel (0,0) "
            f"(expected b>g>r, got rgb=({b_mean[0]:.3f},{b_mean[1]:.3f},{b_mean[2]:.3f}))",
            12,
        )
    if f_spread < 0.25:
        return fail(
            f"repaired panel is not a checker (spread {f_spread:.4f} < 0.25)",
            13,
        )
    if abs(f_mean[0] - b_mean[0]) < 0.1 and f_spread - b_spread < 0.2:
        return fail("broken and repaired panels render identically", 14)
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine", default="eevee", choices=("eevee", "cycles"),
        help="render engine for --output (cycles for GPU-less hosts)",
    )
    args = p.parse_args(argv)

    code = check()
    if code != 0:
        return code
    if args.output:
        # check() already emptied the scene; rebuild for the still.
        out = os.path.abspath(args.output)
        if not render_still(out, args.engine):
            return fail(f"render produced no file at {args.output}", 10)
        code = verify_still(out)
        if code != 0:
            return code
        print(f"wrote {args.output} (pixel witness passed)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
