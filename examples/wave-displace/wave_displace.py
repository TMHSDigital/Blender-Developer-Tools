"""Bulk vertex displacement via foreach_get / foreach_set — a runnable example.

Witnesses the use-foreach-set rule at real scale: a 96x96 grid (9409 verts) is
displaced into a standing wave by reading every coordinate with one
`foreach_get`, rewriting Z in Python, and writing back with one `foreach_set`
— no per-vertex `mesh.vertices[i].co` access. Asserts the flat grid gained
the expected Z span and that EVERY vertex matches the closed-form wave (a
stride or interleave bug in the flat buffer cannot hide). Exits non-zero on
failure.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python wave_displace.py --                 # check only
    blender --background --python wave_displace.py -- --flat          # must fail
    blender --background --python wave_displace.py -- --output w.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
from array import array

GRID = 96          # segments per side -> (GRID+1)^2 verts
SIZE = 6.0
AMP = 0.55
FREQ = 1.6


def wave_z(x, y):
    return AMP * math.sin(FREQ * x) * math.cos(FREQ * y)


def build_grid():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("Wave")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=GRID, y_segments=GRID, size=SIZE / 2)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new("Wave", me)
    bpy.context.collection.objects.link(obj)
    return obj


def displace(me):
    n = len(me.vertices)
    buf = array("f", [0.0] * (n * 3))
    me.vertices.foreach_get("co", buf)          # ONE bulk read
    for i in range(n):
        x, y = buf[i * 3], buf[i * 3 + 1]
        buf[i * 3 + 2] = wave_z(x, y)
    me.vertices.foreach_set("co", buf)          # ONE bulk write
    me.update()
    return n


def check(obj, n_before):
    me = obj.data
    zs = [v.co.z for v in me.vertices]
    span = max(zs) - min(zs)
    if not (1.6 * AMP < span <= 2.0 * AMP + 1e-4):
        print(f"ERROR: z-span {span:.4f} not in ({1.6 * AMP:.4f}, {2 * AMP:.4f}]", file=sys.stderr)
        return 4
    # every vertex must match the closed form, read back per-vertex — a stride
    # or interleave bug in the flat foreach buffer cannot hide behind one probe
    worst = max(abs(v.co.z - wave_z(v.co.x, v.co.y)) for v in me.vertices)
    if worst > 1e-5:
        print(f"ERROR: worst vertex is {worst:.6f} off the closed-form wave", file=sys.stderr)
        return 5
    print(f"verts={n_before} z_span={span:.4f} max_err={worst:.2e}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(obj, path, engine):
    scene = bpy.context.scene
    for poly in obj.data.polygons:
        poly.use_smooth = True
    mat = bpy.data.materials.new("WaveMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.012, 0.09, 0.38, 1.0)  # deep sapphire
    bsdf.inputs["Roughness"].default_value = 0.18
    obj.data.materials.append(mat)

    # render-only staging: the displaced grid is the contract and stays as
    # checked. A copy of it gets a skirt, its boundary extruded straight
    # down to a flat base, so the wave reads as the top of a cast tile
    # standing on the studio floor instead of a sheet bleeding off the frame.
    base = 0.30  # base sits this far below the deepest trough
    tile_me = obj.data.copy()
    bm = bmesh.new()
    try:
        bm.from_mesh(tile_me)
        rim = [e for e in bm.edges if e.is_boundary]
        ret = bmesh.ops.extrude_edge_only(bm, edges=rim)
        skirt = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMFace)]
        for g in ret["geom"]:
            if isinstance(g, bmesh.types.BMVert):
                g.co.z = -AMP - base
        bottom = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMEdge) and g.is_boundary]
        bmesh.ops.holes_fill(bm, edges=bottom, sides=0)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        for f in skirt:
            f.smooth = False
        bm.to_mesh(tile_me)
    finally:
        bm.free()
    tile = bpy.data.objects.new("WaveTile", tile_me)
    tile.location.z = AMP + base
    scene.collection.objects.link(tile)
    obj.hide_render = True

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60.0)
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
    wall.location = (0.0, 14.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # grazing cool key picks out the crests; warm rim from behind; a warm
    # wedge rakes the back wall like the rest of the gallery stages
    light("Key", (-8.0, -7.0, 6.5), 2400.0, 7.0, (0.9, 0.95, 1.0), (55, 0, -48))
    light("Fill", (9.0, -6.0, 3.0), 120.0, 10.0, (0.78, 0.86, 1.0), (70, 0, 55))
    light("Rim", (5.0, 7.5, 4.0), 1800.0, 5.0, (1.0, 0.68, 0.38), (-62, 0, 148))
    light("Wedge", (4.0, 10.5, 7.0), 1500.0, 9.0, (1.0, 0.76, 0.5), (-65, 0, 190))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, -0.4, 0.05)
    scene.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam"); cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (7.2, -11.8, 7.4)
    con = cam.constraints.new('TRACK_TO')
    con.target = aim
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.view_settings.view_transform = 'Standard'

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
    p.add_argument("--flat", action="store_true",
                   help="skip the foreach_set displacement (must fail)")
    args = p.parse_args(argv)

    obj = build_grid()
    n = len(obj.data.vertices) if args.flat else displace(obj.data)
    code = check(obj, n)
    if code:
        return code

    if args.output:
        if not render_still(obj, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 6
        print(f"rendered still {args.output}")

    print("wave-displace OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
