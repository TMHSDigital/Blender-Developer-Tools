"""Relative shape-key blend via the data API — a runnable example.

Witnesses that shape keys are authored and driven on the mesh datablock
(`shape_key_add`, `key_blocks["Name"].data[i].co`, `.value`), not through
operators, and that the depsgraph-evaluated mesh matches the closed-form
relative blend: co = basis + value * (key - basis). AI often keys the
wrong block, forgets Basis, or reads undeformed `mesh.vertices` instead of
the evaluated mesh.

The Tall key both lifts and flares the top face, so the silhouette is a
truncated pyramid — clearly a blend, not a uniformly scaled box.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python shape_key_blend.py --                 # check only
    blender --background --python shape_key_blend.py -- --output s.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

CUBE_SIZE = 1.0
LIFT = 2.0
FLARE = 0.45  # extra half-extent on top face in XY at full key
BLEND = 0.5
HALF = CUBE_SIZE / 2
EXPECT_TOP_Z = HALF + BLEND * LIFT
EXPECT_BOT_Z = -HALF
EXPECT_TOP_HALF = HALF + BLEND * FLARE  # |x| and |y| of top verts


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("Block")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=CUBE_SIZE)
        bm.to_mesh(me)
    finally:
        bm.free()

    obj = bpy.data.objects.new("ShapeBlock", me)
    bpy.context.collection.objects.link(obj)

    # data-level shape keys — no bpy.ops.object.shape_key_*
    obj.shape_key_add(name="Basis")
    tall = obj.shape_key_add(name="Tall")
    for i, _v in enumerate(me.vertices):
        co = tall.data[i].co
        if co.z > 0.0:
            co.z += LIFT
            # flare top face outward so the blend reads as a taper, not a box
            co.x = math.copysign(HALF + FLARE, co.x)
            co.y = math.copysign(HALF + FLARE, co.y)
    tall.value = BLEND
    return obj


def blended_co(basis_kb, key_kb, i, value):
    b = basis_kb.data[i].co
    k = key_kb.data[i].co
    return b + value * (k - b)


def check(obj):
    keys = obj.data.shape_keys
    if keys is None:
        print("ERROR: no shape keys on mesh", file=sys.stderr)
        return 3
    names = [kb.name for kb in keys.key_blocks]
    if names != ["Basis", "Tall"]:
        print(f"ERROR: key names {names} != ['Basis', 'Tall']", file=sys.stderr)
        return 4
    basis = keys.key_blocks["Basis"]
    tall = keys.key_blocks["Tall"]
    if abs(tall.value - BLEND) > 1e-6:
        print(f"ERROR: Tall.value {tall.value} != {BLEND}", file=sys.stderr)
        return 5

    # undeformed mesh.vertices stay at Basis — the trap this example catches
    raw_top = max(v.co.z for v in obj.data.vertices)
    raw_xy = max(max(abs(v.co.x), abs(v.co.y)) for v in obj.data.vertices)
    if abs(raw_top - HALF) > 1e-4 or abs(raw_xy - HALF) > 1e-4:
        print(f"ERROR: undeformed mesh not at Basis "
              f"(top_z={raw_top}, xy={raw_xy}, expected half={HALF})",
              file=sys.stderr)
        return 6

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    em = ev.to_mesh()
    try:
        # every evaluated vert must match the closed-form blend from key_blocks
        for i, v in enumerate(em.vertices):
            expect = blended_co(basis, tall, i, BLEND)
            if (v.co - expect).length > 1e-4:
                print(f"ERROR: vert {i} evaluated {tuple(v.co)} != "
                      f"blend {tuple(expect)}", file=sys.stderr)
                return 7
        zs = [v.co.z for v in em.vertices]
        top_xy = [max(abs(v.co.x), abs(v.co.y)) for v in em.vertices if v.co.z > 0.0]
        top = max(zs)
        bot = min(zs)
        flare = max(top_xy)
    finally:
        ev.to_mesh_clear()

    if abs(top - EXPECT_TOP_Z) > 1e-4 or abs(bot - EXPECT_BOT_Z) > 1e-4:
        print(f"ERROR: evaluated z [{bot:.4f}, {top:.4f}] != "
              f"[{EXPECT_BOT_Z:.4f}, {EXPECT_TOP_Z:.4f}]", file=sys.stderr)
        return 8
    if abs(flare - EXPECT_TOP_HALF) > 1e-4:
        print(f"ERROR: top flare {flare:.4f} != {EXPECT_TOP_HALF:.4f}",
              file=sys.stderr)
        return 9

    print(f"keys={names} value={BLEND} eval_z={bot:.3f}..{top:.3f} "
          f"top_half={flare:.3f} undeformed_top={raw_top:.3f}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(obj, path, engine):
    scene = bpy.context.scene
    for poly in obj.data.polygons:
        poly.use_smooth = False
    mat = bpy.data.materials.new("Violet")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.52, 0.06, 0.98, 1.0)  # violet
    bsdf.inputs["Roughness"].default_value = 0.22
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    # bottom verts stay at -HALF; lift so the block rests on the floor
    obj.location = (0.0, 0.0, HALF)
    obj.rotation_euler = (0.0, 0.0, math.radians(28))

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

    world_top = HALF + EXPECT_TOP_Z
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, world_top / 2)
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

    light("Key", (-3.5, -4.5, 5.5), 1500.0, 6.0, (1.0, 0.98, 0.94))
    light("Fill", (5.0, -3.5, 2.5), 340.0, 8.0, (0.8, 0.87, 1.0))
    light("Rim", (1.5, 4.5, 2.0), 480.0, 4.0, (1.0, 0.75, 0.45))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (3.6, -4.8, 2.4)
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

    obj = build()
    code = check(obj)
    if code:
        return code

    if args.output:
        if not render_still(obj, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 10
        print(f"rendered still {args.output}")

    print("shape-key-blend OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
