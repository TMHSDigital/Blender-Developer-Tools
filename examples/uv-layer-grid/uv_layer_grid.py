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
(checker) panel so the failure mode is visible at a glance:

    blender --background --python uv_layer_grid.py --
    blender --background --python uv_layer_grid.py -- --output uv.png
"""
import bpy, bmesh, sys, os, math, argparse

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
    """Neon checker + corner marker. Texel (0,0) is a flat teal so a missing UV
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

    # Left: the hazard — calc_uvs alone, no UV layer → flat teal of texel (0,0).
    broken = textured_plane("Broken", card, with_uvs=False)
    broken.location = (-1.22, 0.0, 1.18)
    broken.rotation_euler = (math.radians(62), 0.0, math.radians(10))
    broken.scale = (1.15, 1.15, 1.15)

    # Right: the repair — pre-create UV layer, then calc_uvs fills it.
    fixed = textured_plane("Fixed", card, with_uvs=True)
    fixed.location = (1.22, 0.0, 1.18)
    fixed.rotation_euler = (math.radians(62), 0.0, math.radians(-10))
    fixed.scale = (1.15, 1.15, 1.15)

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

    light("Key", (-3.8, -4.8, 5.8), 360.0, 4.5, (1.0, 0.96, 0.9), (52, 0, -32))
    light("Fill", (4.8, -2.8, 1.6), 70.0, 9.0, (0.75, 0.85, 1.0), (72, 0, 52))
    light("Rim", (0.2, 4.0, 2.8), 220.0, 3.2, (0.6, 0.78, 1.0), (-62, 0, 178))
    # Between the panels and the wall so it only rakes the backdrop.
    light("Wedge", (0.5, 5.2, 2.8), 520.0, 7.0, (1.0, 0.72, 0.42), (-78, 0, 180))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 1.1)
    scene.collection.objects.link(aim)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 45.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -5.4, 2.2)
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
        if not render_still(os.path.abspath(args.output), args.engine):
            return fail(f"render produced no file at {args.output}", 10)
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
