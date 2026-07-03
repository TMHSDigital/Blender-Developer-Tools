"""Bulk vertex displacement via foreach_get / foreach_set — a runnable example.

Witnesses the use-foreach-set rule at real scale: a 96x96 grid (9409 verts) is
displaced into a standing wave by reading every coordinate with one
`foreach_get`, rewriting Z in Python, and writing back with one `foreach_set`
— no per-vertex `mesh.vertices[i].co` access. Asserts the vertex count is
unchanged, the flat grid gained the expected Z span, and a probe vertex
matches the closed-form wave. Exits non-zero on failure.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python wave_displace.py --                 # check only
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
    buf = array("f", [0.0]) * (n * 3)
    me.vertices.foreach_get("co", buf)          # ONE bulk read
    for i in range(n):
        x, y = buf[i * 3], buf[i * 3 + 1]
        buf[i * 3 + 2] = wave_z(x, y)
    me.vertices.foreach_set("co", buf)          # ONE bulk write
    me.update()
    return n


def check(obj, n_before):
    me = obj.data
    if len(me.vertices) != n_before:
        print(f"ERROR: vertex count changed ({n_before} -> {len(me.vertices)})", file=sys.stderr)
        return 3
    zs = [v.co.z for v in me.vertices]
    span = max(zs) - min(zs)
    if not (1.6 * AMP < span <= 2.0 * AMP + 1e-4):
        print(f"ERROR: z-span {span:.4f} not in ({1.6 * AMP:.4f}, {2 * AMP:.4f}]", file=sys.stderr)
        return 4
    probe = me.vertices[0].co
    expect = wave_z(probe.x, probe.y)
    if abs(probe.z - expect) > 1e-5:
        print(f"ERROR: probe z {probe.z:.6f} != wave {expect:.6f}", file=sys.stderr)
        return 5
    print(f"verts={n_before} z_span={span:.4f} probe_ok=True")
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

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.008, 0.009, 0.012, 1.0)
    scene.world = world

    # grazing cool key picks out the crests; warm rim from behind
    key = bpy.data.lights.new("Key", 'AREA'); key.energy = 2000.0; key.size = 6.0
    key.color = (0.9, 0.95, 1.0)
    key_ob = bpy.data.objects.new("Key", key)
    key_ob.location = (-6.5, -5.0, 3.2)
    key_ob.rotation_euler = (math.radians(65), 0.0, math.radians(-50))
    scene.collection.objects.link(key_ob)
    rim = bpy.data.lights.new("Rim", 'AREA'); rim.energy = 1300.0; rim.size = 4.0
    rim.color = (1.0, 0.68, 0.38)
    rim_ob = bpy.data.objects.new("Rim", rim)
    rim_ob.location = (4.5, 6.5, 2.6)
    rim_ob.rotation_euler = (math.radians(-68), 0.0, math.radians(148))
    scene.collection.objects.link(rim_ob)

    cam_data = bpy.data.cameras.new("Cam"); cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -8.6, 4.6)
    cam.rotation_euler = (math.radians(62), 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 32
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

    obj = build_grid()
    n = displace(obj.data)
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
