"""One shader node group, two materials — a runnable example.

Witnesses the node-group socket workflow from procedural-materials-and-shaders:
group sockets are declared through `tree.interface.new_socket` (the 4.x/5.x
API that replaced `tree.inputs`/`tree.outputs`), and per-material parameters
live on the GROUP NODE instance, not inside the group. The check asserts the
interface carries the declared sockets, both materials share the same group
datablock (users == 2), and their instance-level Tint values differ — the
whole point of grouping.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python shader_node_group.py --                 # check only
    blender --background --python shader_node_group.py -- --output s.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

TINTS = {
    "SphereA": (0.012, 0.32, 0.30, 1.0),   # teal
    "SphereB": (0.42, 0.02, 0.20, 1.0),    # magenta
}


def build_group():
    """A reusable 'TintedGloss' shader group: Tint + Roughness in, Shader out."""
    tree = bpy.data.node_groups.new("TintedGloss", 'ShaderNodeTree')
    tree.interface.new_socket(name="Tint", in_out='INPUT', socket_type='NodeSocketColor')
    rough = tree.interface.new_socket(name="Roughness", in_out='INPUT',
                                      socket_type='NodeSocketFloat')
    rough.default_value = 0.2
    tree.interface.new_socket(name="Shader", in_out='OUTPUT', socket_type='NodeSocketShader')

    gi = tree.nodes.new('NodeGroupInput')
    go = tree.nodes.new('NodeGroupOutput')
    bsdf = tree.nodes.new('ShaderNodeBsdfPrincipled')
    tree.links.new(gi.outputs["Tint"], bsdf.inputs["Base Color"])
    tree.links.new(gi.outputs["Roughness"], bsdf.inputs["Roughness"])
    tree.links.new(bsdf.outputs["BSDF"], go.inputs["Shader"])
    return tree


def material_from_group(name, tree, tint):
    """Instance the group in a fresh material; parameters set on the instance."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    group = nt.nodes.new('ShaderNodeGroup')
    group.node_tree = tree
    group.inputs["Tint"].default_value = tint
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(group.outputs["Shader"], out.inputs["Surface"])
    return mat


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    tree = build_group()
    objs = []
    for i, (name, tint) in enumerate(TINTS.items()):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
            bm.to_mesh(me)
        finally:
            bm.free()
        obj = bpy.data.objects.new(name, me)
        obj.location = (-1.35 + i * 2.7, 0.0, 1.0)
        for poly in me.polygons:
            poly.use_smooth = True
        me.materials.append(material_from_group(f"Mat.{name}", tree, tint))
        bpy.context.collection.objects.link(obj)
        objs.append(obj)
    return tree, objs


def check(tree, objs):
    # sockets declared through the interface API actually exist on the interface
    names = {(s.name, s.in_out) for s in tree.interface.items_tree
             if getattr(s, "item_type", "SOCKET") == 'SOCKET'}
    expect = {("Tint", 'INPUT'), ("Roughness", 'INPUT'), ("Shader", 'OUTPUT')}
    if not expect <= names:
        print(f"ERROR: interface sockets {names} missing {expect - names}", file=sys.stderr)
        return 3

    # one shared group datablock, instanced by both materials
    if tree.users != 2:
        print(f"ERROR: group users {tree.users} != 2 (not shared)", file=sys.stderr)
        return 4

    # per-instance parameters live on the group NODE, and they differ
    tints = []
    for obj in objs:
        node = next(n for n in obj.data.materials[0].node_tree.nodes
                    if n.type == 'GROUP')
        if node.node_tree is not tree:
            print(f"ERROR: {obj.name} instance points at a different tree", file=sys.stderr)
            return 5
        tints.append(tuple(round(c, 3) for c in node.inputs["Tint"].default_value))
    if tints[0] == tints[1]:
        print("ERROR: instance Tint values are identical — parameters leaked into "
              "the group instead of the instance", file=sys.stderr)
        return 6

    print(f"group=TintedGloss users={tree.users} instance_tints={tints[0]} vs {tints[1]}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(objs, path, engine):
    scene = bpy.context.scene
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

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", (-4.0, -5.0, 6.5), 1400.0, 5.5, (1.0, 0.98, 0.94), (46, 0, -35))
    light("Fill", (5.5, -4.0, 3.0), 280.0, 8.0, (0.82, 0.88, 1.0), (63, 0, 48))
    light("Rim", (0.5, 6.0, 4.0), 900.0, 3.5, (1.0, 0.74, 0.46), (-62, 0, 175))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 58.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -7.8, 2.6)
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
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    args = p.parse_args(argv)

    tree, objs = build_scene()
    code = check(tree, objs)
    if code:
        return code

    if args.output:
        if not render_still(objs, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 7
        print(f"rendered still {args.output}")

    print("shader-node-group OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
