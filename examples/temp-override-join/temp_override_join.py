"""Join meshes via bpy.context.temp_override — a runnable example.

Witnesses the prefer-temp-override-over-context-copy contract: operators that
need a fabricated active/selection context must run under
`bpy.context.temp_override(**kwargs)`, not the deprecated
`bpy.ops.*(bpy.context.copy())` dict-pass form (removed in 5.x). Three unit
cubes are joined into a staircase; the check asserts closed-form topology,
that only the target remains, and that the local Z span spans all three steps
(proving every source contributed geometry).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python temp_override_join.py --                 # check only
    blender --background --python temp_override_join.py -- --output j.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

CUBE_SIZE = 1.0
HALF = CUBE_SIZE / 2
STEPS = 3
# staircase along +X: step i sits on the previous, center at (i, 0, i+0.5) * CUBE_SIZE
EXPECT_VERTS = 8 * STEPS
EXPECT_FACES = 6 * STEPS
# target origin is step 0; joined local Z spans [-HALF, (STEPS-1)*CUBE_SIZE + HALF]
EXPECT_Z_LO = -HALF
EXPECT_Z_HI = (STEPS - 1) * CUBE_SIZE + HALF


def build_cubes():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("Block")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=CUBE_SIZE)
        bm.to_mesh(me)
    finally:
        bm.free()

    objs = []
    for i in range(STEPS):
        obj = bpy.data.objects.new(f"Block.{i}", me.copy())
        obj.location = (i * CUBE_SIZE, 0.0, (i + 0.5) * CUBE_SIZE)
        bpy.context.collection.objects.link(obj)
        objs.append(obj)
    bpy.data.meshes.remove(me)
    return objs


def join_with_temp_override(target, sources):
    """The contract this example witnesses: temp_override, not context.copy()."""
    view_layer = bpy.context.view_layer
    for obj in bpy.data.objects:
        obj.select_set(False)
    target.select_set(True)
    for src in sources:
        src.select_set(True)
    view_layer.objects.active = target

    with bpy.context.temp_override(
        active_object=target,
        selected_objects=[target, *sources],
        selected_editable_objects=[target, *sources],
    ):
        bpy.ops.object.join()
    return target


def check(joined, source_names):
    mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH']
    if len(mesh_objs) != 1:
        print(f"ERROR: expected 1 mesh object after join, got {len(mesh_objs)}",
              file=sys.stderr)
        return 3
    if mesh_objs[0] is not joined:
        print("ERROR: joined target is not the sole remaining mesh object",
              file=sys.stderr)
        return 4

    got_v = len(joined.data.vertices)
    got_f = len(joined.data.polygons)
    if got_v != EXPECT_VERTS or got_f != EXPECT_FACES:
        print(f"ERROR: topology verts={got_v} faces={got_f} != "
              f"expected verts={EXPECT_VERTS} faces={EXPECT_FACES}",
              file=sys.stderr)
        return 5

    still_alive = [n for n in source_names if n in bpy.data.objects]
    if still_alive:
        print(f"ERROR: source objects still present after join: {still_alive}",
              file=sys.stderr)
        return 6

    # Z span proves every step contributed — a no-op override leaves only step 0
    zs = [v.co.z for v in joined.data.vertices]
    z_lo, z_hi = min(zs), max(zs)
    if abs(z_lo - EXPECT_Z_LO) > 1e-4 or abs(z_hi - EXPECT_Z_HI) > 1e-4:
        print(f"ERROR: local z [{z_lo:.4f}, {z_hi:.4f}] != "
              f"[{EXPECT_Z_LO:.4f}, {EXPECT_Z_HI:.4f}] — join did not merge all steps",
              file=sys.stderr)
        return 7

    print(f"steps={STEPS} verts={got_v} faces={got_f} "
          f"z={z_lo:.3f}..{z_hi:.3f} override=temp_override")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(obj, path, engine):
    scene = bpy.context.scene
    for poly in obj.data.polygons:
        poly.use_smooth = False
    mat = bpy.data.materials.new("Amber")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.98, 0.38, 0.02, 1.0)  # amber
    bsdf.inputs["Roughness"].default_value = 0.20
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    # center the staircase footprint; origin is step-0 center
    obj.location = (-(STEPS - 1) * CUBE_SIZE / 2, 0.0, HALF)

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
    fb.inputs["Base Color"].default_value = (0.055, 0.06, 0.07, 1.0)
    fb.inputs["Roughness"].default_value = 0.5
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.008, 0.009, 0.012, 1.0)
    scene.world = world

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, STEPS * CUBE_SIZE / 2)
    scene.collection.objects.link(aim)

    def light(name, loc, energy, size, col):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        scene.collection.objects.link(ob)
        lc = ob.constraints.new('TRACK_TO')
        lc.target = aim
        lc.track_axis = 'TRACK_NEGATIVE_Z'
        lc.up_axis = 'UP_Y'

    light("Key", (-4.0, -5.0, 6.0), 1500.0, 6.0, (1.0, 0.98, 0.94))
    light("Fill", (5.0, -3.5, 3.0), 340.0, 8.0, (0.8, 0.87, 1.0))
    light("Rim", (1.5, 5.0, 2.5), 480.0, 4.0, (1.0, 0.75, 0.45))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (4.2, -5.2, 4.0)
    scene.collection.objects.link(cam)
    scene.camera = cam
    track = cam.constraints.new('TRACK_TO')
    track.target = aim
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'

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
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    args = p.parse_args(argv)

    objs = build_cubes()
    target, sources = objs[0], objs[1:]
    source_names = [s.name for s in sources]
    joined = join_with_temp_override(target, sources)
    code = check(joined, source_names)
    if code:
        return code

    if args.output:
        if not render_still(joined, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 8
        print(f"rendered still {args.output}")

    print("temp-override-join OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
