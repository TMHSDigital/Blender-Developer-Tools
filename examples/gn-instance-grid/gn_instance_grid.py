"""Geometry Nodes Instance-on-Points grid — a runnable example.

Witnesses the geometry-nodes-python construction contract for instancing:
a generative GeometryNodeTree (Mesh Grid → Instance on Points → Realize
Instances → Transform) attached as a NODES modifier, with no Group Input
geometry. The check asserts the closed-form evaluated topology —
verts = grid_points × cube_verts — proving instances were realized, not
left as empty instance geometry, and that a corner instance sits at its
closed-form grid coordinate.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python gn_instance_grid.py --                 # check only
    blender --background --python gn_instance_grid.py -- --output g.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

GRID_X = 3
GRID_Y = 3
GRID_SIZE = 2.4
CUBE_SIZE = 0.42
CUBE_VERTS = 8
CUBE_FACES = 6
GRID_POINTS = GRID_X * GRID_Y
EXPECT_VERTS = GRID_POINTS * CUBE_VERTS
EXPECT_FACES = GRID_POINTS * CUBE_FACES
# Mesh Grid spans [-GRID_SIZE/2, +GRID_SIZE/2]; corner point at (+half, +half)
GRID_HALF = GRID_SIZE / 2
# after Transform lift, corner cube center is at (GRID_HALF, GRID_HALF, CUBE_SIZE/2)
CORNER_CENTER = (GRID_HALF, GRID_HALF, CUBE_SIZE / 2)


def build_instance_grid_tree(material=None):
    tree = bpy.data.node_groups.new("InstanceGrid", 'GeometryNodeTree')
    # generative: no Group Input — the tree owns the geometry
    tree.interface.new_socket(
        name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry',
    )
    go = tree.nodes.new('NodeGroupOutput')

    grid = tree.nodes.new('GeometryNodeMeshGrid')
    grid.inputs["Size X"].default_value = GRID_SIZE
    grid.inputs["Size Y"].default_value = GRID_SIZE
    grid.inputs["Vertices X"].default_value = GRID_X
    grid.inputs["Vertices Y"].default_value = GRID_Y

    cube = tree.nodes.new('GeometryNodeMeshCube')
    cube.inputs["Size"].default_value = (CUBE_SIZE, CUBE_SIZE, CUBE_SIZE)

    iop = tree.nodes.new('GeometryNodeInstanceOnPoints')
    realize = tree.nodes.new('GeometryNodeRealizeInstances')
    xform = tree.nodes.new('GeometryNodeTransform')
    # cubes are centered on grid points at z=0; lift so they rest on the floor
    xform.inputs["Translation"].default_value = (0.0, 0.0, CUBE_SIZE / 2)

    # crisp facets — matches the other studio examples
    shade = tree.nodes.new('GeometryNodeSetShadeSmooth')
    shade.inputs["Shade Smooth"].default_value = False

    tree.links.new(grid.outputs["Mesh"], iop.inputs["Points"])
    tree.links.new(cube.outputs["Mesh"], iop.inputs["Instance"])
    tree.links.new(iop.outputs["Instances"], realize.inputs["Geometry"])
    tree.links.new(realize.outputs["Geometry"], xform.inputs["Geometry"])
    tree.links.new(xform.outputs["Geometry"], shade.inputs["Geometry"])
    out_socket = shade.outputs["Geometry"]

    if material is not None:
        set_mat = tree.nodes.new('GeometryNodeSetMaterial')
        set_mat.inputs["Material"].default_value = material
        tree.links.new(out_socket, set_mat.inputs["Geometry"])
        out_socket = set_mat.outputs["Geometry"]

    tree.links.new(out_socket, go.inputs["Geometry"])
    return tree


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # carrier mesh is unused by the generative tree; one vertex is enough
    me = bpy.data.meshes.new("Carrier")
    me.vertices.add(1)
    obj = bpy.data.objects.new("InstanceGrid", me)
    bpy.context.collection.objects.link(obj)

    mat = bpy.data.materials.new("Lime")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.22, 0.95, 0.06, 1.0)  # lime
    bsdf.inputs["Roughness"].default_value = 0.22

    tree = build_instance_grid_tree(material=mat)
    mod = obj.modifiers.new("instance_grid", 'NODES')
    mod.node_group = tree
    return obj, mat


def check(obj):
    base = len(obj.data.vertices)
    if base != 1:
        print(f"ERROR: carrier should have 1 vertex, got {base}", file=sys.stderr)
        return 3

    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    em = ev.to_mesh()
    try:
        got_v = len(em.vertices)
        got_f = len(em.polygons)
        mat_names = [m.name for m in em.materials if m is not None]
        # corner instance: the 8 verts nearest CORNER_CENTER should average to it
        corner = [v.co for v in em.vertices
                  if (v.co.x > GRID_HALF - CUBE_SIZE and v.co.y > GRID_HALF - CUBE_SIZE)]
        if len(corner) != CUBE_VERTS:
            print(f"ERROR: corner instance has {len(corner)} verts, expected {CUBE_VERTS}",
                  file=sys.stderr)
            return 4
        cx = sum(c.x for c in corner) / CUBE_VERTS
        cy = sum(c.y for c in corner) / CUBE_VERTS
        cz = sum(c.z for c in corner) / CUBE_VERTS
    finally:
        ev.to_mesh_clear()

    if got_v != EXPECT_VERTS or got_f != EXPECT_FACES:
        print(f"ERROR: evaluated topology verts={got_v} faces={got_f} != "
              f"expected verts={EXPECT_VERTS} faces={EXPECT_FACES}",
              file=sys.stderr)
        return 5

    if "Lime" not in mat_names:
        print(f"ERROR: Set Material did not carry Lime onto evaluated mesh "
              f"(materials={mat_names})", file=sys.stderr)
        return 6

    for got, exp, axis in ((cx, CORNER_CENTER[0], 'x'),
                           (cy, CORNER_CENTER[1], 'y'),
                           (cz, CORNER_CENTER[2], 'z')):
        if abs(got - exp) > 1e-3:
            print(f"ERROR: corner center {axis}={got:.4f} != {exp:.4f}",
                  file=sys.stderr)
            return 7

    print(f"grid={GRID_X}x{GRID_Y} points={GRID_POINTS} "
          f"eval_verts={got_v} eval_faces={got_f} "
          f"corner=({cx:.2f},{cy:.2f},{cz:.2f}) material=Lime")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(obj, path, engine):
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

    # tip the grid so depth reads; cubes already rest on the floor via the tree
    obj.rotation_euler = (0.0, 0.0, math.radians(24))

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

    light("Key", (-3.5, -4.5, 5.5), 1500.0, 6.0, (1.0, 0.98, 0.94))
    light("Fill", (5.0, -3.5, 2.5), 340.0, 8.0, (0.8, 0.87, 1.0))
    light("Rim", (1.5, 4.5, 2.0), 480.0, 4.0, (1.0, 0.75, 0.45))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (4.6, -5.4, 3.4)
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

    obj, _mat = build()
    code = check(obj)
    if code:
        return code

    if args.output:
        if not render_still(obj, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 8
        print(f"rendered still {args.output}")

    print("gn-instance-grid OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
