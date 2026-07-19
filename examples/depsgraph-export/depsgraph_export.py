"""Depsgraph-evaluated export — a runnable example.

Witnesses the depsgraph lifetime contract AND that modifiers actually ship in
exports. Builds a cube with a SUBSURF modifier, measures the evaluated mesh via
evaluated_get().to_mesh() (paired with to_mesh_clear()), exports through
wm.obj_export, and asserts the exported vertex count equals the EVALUATED
(modifier-applied) count and is strictly greater than the base.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python depsgraph_export.py --                 # check only
    blender --background --python depsgraph_export.py -- --output d.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse, tempfile


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("Cube")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new("Cube", me)
    bpy.context.collection.objects.link(obj)
    obj.modifiers.new("ss", 'SUBSURF').levels = 2
    return obj


def check(obj, obj_path):
    base = len(obj.data.vertices)

    # depsgraph lifetime contract: evaluate, read, then release with to_mesh_clear
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    em = ev.to_mesh()
    eval_vcount = len(em.vertices)
    ev.to_mesh_clear()  # must be paired; releases the temporary mesh

    out = obj_path or os.path.join(tempfile.gettempdir(), "depsgraph_export.obj")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    # obj_export writes the evaluated (modifier-applied) geometry by default
    bpy.ops.wm.obj_export(filepath=out, export_selected_objects=False)
    if not (os.path.exists(out) and os.path.getsize(out) > 0):
        print("ERROR: no OBJ written", file=sys.stderr)
        return 4
    exported = 0
    with open(out) as f:
        for line in f:
            if line.startswith("v "):
                exported += 1

    print(f"base_vcount={base} eval_vcount={eval_vcount} exported_vcount={exported}")
    if not (eval_vcount > base):
        print("ERROR: evaluated mesh did not apply the modifier", file=sys.stderr)
        return 3
    if exported != eval_vcount:
        print(f"ERROR: export ({exported}) != evaluated ({eval_vcount}); modifier did not ship",
              file=sys.stderr)
        return 5
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def principled(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def render_still(obj, path, engine):
    """Base cube beside its evaluated form — the two counts the check compares."""
    scene = bpy.context.scene

    # left: the base mesh, modifier-free (a plain copy of the datablock)
    base_obj = bpy.data.objects.new("Base", obj.data.copy())
    base_obj.location = (-1.7, 0.0, 1.0)
    base_obj.data.materials.append(
        principled("Graphite", (0.09, 0.10, 0.12, 1.0), 0.0, 0.55))
    bpy.context.collection.objects.link(base_obj)

    # right: the SUBSURF object — what the depsgraph evaluates and the OBJ ships.
    # Rest it on the floor by measuring its own EVALUATED bounds (the subsurf
    # limit surface shrinks, so the base-mesh -1.0 is not where it ends).
    dg = bpy.context.evaluated_depsgraph_get()
    em = obj.evaluated_get(dg).to_mesh()
    bottom = min(v.co.z for v in em.vertices)
    obj.evaluated_get(dg).to_mesh_clear()
    obj.location = (1.8, 0.0, -bottom)
    obj.data.materials.append(
        principled("EvalGreen", (0.03, 0.32, 0.10, 1.0), 0.0, 0.15))
    for poly in obj.data.polygons:
        poly.use_smooth = True

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    floor_me.materials.append(principled("Studio", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7))
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.data.materials.clear()
    wall.data.materials.append(principled("Wall", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7))
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.pi / 2, 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = \
        (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # warm shaped key, faint cool fill, warm wedge on the back wall
    # (docs/VISUAL-STYLE.md)
    light("Key", (-4.0, -5.0, 6.0), 650.0, 5.0, (1.0, 0.96, 0.9), (46, 0, -35))
    light("Fill", (5.0, -3.5, 3.0), 120.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Wedge", (2.5, 5.5, 4.0), 380.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 46.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -8.2, 2.7)
    cam.rotation_euler = (math.radians(78), 0.0, 0.0)
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
    # AgX would flatten the graphite-vs-green contrast this still hinges on
    # (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--obj", default=None,
                   help="optional: write the exported OBJ here (else a temp path)")
    args = p.parse_args(argv)

    obj = build()
    code = check(obj, args.obj)
    if code:
        return code

    if args.output:
        if not render_still(obj, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 6
        print(f"rendered still {args.output}")

    print("depsgraph-export OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
