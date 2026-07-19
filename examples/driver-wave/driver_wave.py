"""Driver-namespace scale drivers, evaluated through the depsgraph — a runnable example.

Witnesses the drivers-and-app-handlers contract end to end: a custom function
is registered in `bpy.app.driver_namespace`, sixteen columns get a SCRIPTED
driver on Z scale calling it, and the check reads the driven values back
after a view-layer update — from the evaluated copy AND from the original
(the animation system flushes driven values back to the original datablock
for display, so both must agree). Asserts both against the closed-form
profile. Exits non-zero on failure.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python driver_wave.py --                 # check only
    blender --background --python driver_wave.py -- --output d.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

COUNT = 16
SPACING = 0.72
BASE = 0.28


def wave_scale(i):
    """The driver function: column height profile, 0.4..2.4."""
    return 1.4 + math.sin(i * 0.6)


def build_columns():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # driver_namespace entries do not persist in .blend files; real add-ons
    # re-register them from a load_post handler. Headless, registering before
    # driver creation is enough.
    bpy.app.driver_namespace["wave_scale"] = wave_scale

    me = bpy.data.meshes.new("Column")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
    finally:
        bm.free()

    objs = []
    x0 = -(COUNT - 1) * SPACING / 2
    for i in range(COUNT):
        obj = bpy.data.objects.new(f"Col.{i:02d}", me)
        obj.location = (x0 + i * SPACING, 0.0, 0.0)
        obj.scale = (BASE, BASE, 1.0)
        fcu = obj.driver_add("scale", 2)
        fcu.driver.type = 'SCRIPTED'
        fcu.driver.expression = f"wave_scale({i})"
        bpy.context.collection.objects.link(obj)
        objs.append(obj)
    return objs


def check(objs):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    for i, obj in enumerate(objs):
        expect = wave_scale(i)
        driven = obj.evaluated_get(dg).scale[2]
        if abs(driven - expect) > 1e-4:
            print(f"ERROR: col {i} evaluated scale {driven:.4f} != wave_scale {expect:.4f}",
                  file=sys.stderr)
            return 3
        # drivers flush back to the original datablock for display — both agree
        if abs(obj.scale[2] - expect) > 1e-4:
            print(f"ERROR: col {i} original scale {obj.scale[2]:.4f} not flushed "
                  f"(expected {expect:.4f})", file=sys.stderr)
            return 4
    lo = min(wave_scale(i) for i in range(COUNT))
    hi = max(wave_scale(i) for i in range(COUNT))
    print(f"columns={COUNT} driven_range={lo:.3f}..{hi:.3f} flushed_to_original=True")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(objs, path, engine):
    scene = bpy.context.scene
    mat = bpy.data.materials.new("ColMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (1.0, 0.26, 0.012, 1.0)  # selection orange
    bsdf.inputs["Roughness"].default_value = 0.32
    objs[0].data.materials.append(mat)  # shared mesh -> all columns

    # columns stand on the floor: lift each by its DRIVEN half-height
    dg = bpy.context.evaluated_depsgraph_get()
    for obj in objs:
        obj.location.z = obj.evaluated_get(dg).scale[2] / 2

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    floor = bpy.data.objects.new("Floor", floor_me)
    fmat = bpy.data.materials.new("FloorMat")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)  # dark staged studio
    fb.inputs["Roughness"].default_value = 0.7
    floor_me.materials.append(fmat)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    # warm shaped key, faint cool fill, warm wedge pooling on the back wall
    # (docs/VISUAL-STYLE.md)
    key = bpy.data.lights.new("Key", 'AREA'); key.energy = 650.0; key.size = 4.5
    key.color = (1.0, 0.96, 0.9)
    key_ob = bpy.data.objects.new("Key", key)
    key_ob.location = (-4.5, -5.5, 6.5)
    key_ob.rotation_euler = (math.radians(46), 0.0, math.radians(-33))
    scene.collection.objects.link(key_ob)
    fill = bpy.data.lights.new("Fill", 'AREA'); fill.energy = 110.0; fill.size = 8.0
    fill.color = (0.75, 0.85, 1.0)
    fill_ob = bpy.data.objects.new("Fill", fill)
    fill_ob.location = (5.5, -4.0, 3.5)
    fill_ob.rotation_euler = (math.radians(62), 0.0, math.radians(48))
    scene.collection.objects.link(fill_ob)
    wedge = bpy.data.lights.new("Wedge", 'AREA'); wedge.energy = 380.0; wedge.size = 6.0
    wedge.color = (1.0, 0.76, 0.5)
    wedge_ob = bpy.data.objects.new("Wedge", wedge)
    wedge_ob.location = (2.5, 6.0, 4.0)
    wedge_ob.rotation_euler = (math.radians(-68), 0.0, math.radians(190))
    scene.collection.objects.link(wedge_ob)

    # lens/distance chosen so all sixteen columns (span 11.1 units) sit inside
    # the frame with a small margin -- the skyline must not clip
    cam_data = bpy.data.cameras.new("Cam"); cam_data.lens = 42.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -13.5, 2.0)
    cam.rotation_euler = (math.radians(86), 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 32
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # AgX would wash the orange columns toward tan (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    args = p.parse_args(argv)

    objs = build_columns()
    code = check(objs)
    if code:
        return code

    if args.output:
        if not render_still(objs, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 6
        print(f"rendered still {args.output}")

    print("driver-wave OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
