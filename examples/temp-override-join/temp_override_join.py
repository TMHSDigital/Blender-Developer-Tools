"""Join meshes via bpy.context.temp_override — a runnable example.

Witnesses the prefer-temp-override-over-context-copy contract: operators that
need a fabricated active/selection context must run under
`bpy.context.temp_override(**kwargs)`, not the deprecated
`bpy.ops.*(bpy.context.copy())` dict-pass form (removed in 5.x). Three unit
cubes are joined into one mesh; the check asserts the closed-form topology
and that only the target object remains.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python temp_override_join.py --                 # check only
    blender --background --python temp_override_join.py -- --output j.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

CUBE_SIZE = 1.0
# L-shape footprint: origin, +X, -Y — open corner faces the standard -Y camera
OFFSETS = ((0.0, 0.0), (CUBE_SIZE, 0.0), (0.0, -CUBE_SIZE))
EXPECT_VERTS = 8 * len(OFFSETS)
EXPECT_FACES = 6 * len(OFFSETS)


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
    for i, (x, y) in enumerate(OFFSETS):
        # each object needs its own mesh datablock so join keeps all geometry
        obj = bpy.data.objects.new(f"Block.{i}", me.copy())
        obj.location = (x, y, CUBE_SIZE / 2)
        bpy.context.collection.objects.link(obj)
        objs.append(obj)
    bpy.data.meshes.remove(me)  # template only
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

    # sources must be gone (join consumes them) — names captured before join
    still_alive = [n for n in source_names if n in bpy.data.objects]
    if still_alive:
        print(f"ERROR: source objects still present after join: {still_alive}",
              file=sys.stderr)
        return 6

    print(f"blocks={len(OFFSETS)} verts={got_v} faces={got_f} "
          f"mesh_objects=1 override=temp_override")
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
    bsdf.inputs["Base Color"].default_value = (0.98, 0.42, 0.02, 1.0)  # amber
    bsdf.inputs["Roughness"].default_value = 0.22
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    # L-shape rests on the floor; center the footprint on the origin
    obj.location = (-CUBE_SIZE / 2, CUBE_SIZE / 2, CUBE_SIZE / 2)

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
    aim.location = (0.0, 0.0, CUBE_SIZE / 2)
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

    light("Key", (-3.5, -4.5, 5.5), 1400.0, 6.0, (1.0, 0.98, 0.94))
    light("Fill", (5.0, -3.5, 2.5), 320.0, 8.0, (0.8, 0.87, 1.0))
    light("Rim", (1.5, 4.5, 2.0), 420.0, 4.0, (1.0, 0.75, 0.45))

    # look into the open corner of the L so both arms read
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.8, -3.6, 2.8)
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
            return 7
        print(f"rendered still {args.output}")

    print("temp-override-join OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
