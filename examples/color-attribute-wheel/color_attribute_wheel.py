"""HSV color-attribute wheel -- a runnable example.

Witnesses the modern color-attribute contract that AI-generated Blender code
routinely gets wrong: `Mesh.color_attributes.new()` (not the deprecated
`Mesh.vertex_colors.new()` alias), and the domain trap that comes with it --
a `CORNER`-domain attribute is sized to `len(mesh.loops)`, not
`len(mesh.vertices)`, so code that fills it with a per-vertex-sized buffer
either raises or silently miscolors every shared vertex. This example builds
a polar disc where every vertex carries one hue/saturation pair, expands that
per-vertex data across face corners with one `foreach_get` (loop ->
vertex_index) and one `foreach_set` (loop color), and marks the attribute
`active_color` so it is the one a renderer or exporter actually picks up. The
material wires the same attribute into a Shader `Attribute` node
(`attribute_type='GEOMETRY'`) feeding Base Color -- a step AI code frequently
skips, leaving the mesh gray even though the attribute data is correct.

By default it runs only the correctness check (no render) -- the CI smoke
check. Pass --output to also render a still:

    blender --background --python color_attribute_wheel.py --                 # check only
    blender --background --python color_attribute_wheel.py -- --output w.png  # + render
"""
import bpy, bmesh, sys, os, math, colorsys, argparse
from array import array

RINGS = 14
SEGMENTS = 72
R_OUTER = 1.6

N_VERTS = 1 + RINGS * SEGMENTS
N_FACES = SEGMENTS + (RINGS - 1) * SEGMENTS
N_LOOPS = 3 * SEGMENTS + 4 * (RINGS - 1) * SEGMENTS
ATTR_NAME = "Hue"


def vidx(r, s):
    """Vertex index for ring r (0 = center) and segment s, matching build order."""
    return 0 if r == 0 else 1 + (r - 1) * SEGMENTS + (s % SEGMENTS)


def wheel_geometry():
    """Vertex coords and per-vertex (h, s, v) in the same order as vidx()."""
    coords = [(0.0, 0.0, 0.0)]
    hsv = [(0.0, 0.0, 1.0)]  # center: fully desaturated, white
    # the hue origin is rotated off the picture horizontal: red is the
    # perceptually sharpest hue transition, and the 0/360-degree wrap reads
    # as a seam artifact when it lies level in frame
    angle0 = math.radians(-52.0)
    for r in range(1, RINGS + 1):
        radius = R_OUTER * r / RINGS
        sat = min(1.0, (r / RINGS) * 1.4)
        for s in range(SEGMENTS):
            angle = angle0 + 2.0 * math.pi * s / SEGMENTS
            coords.append((radius * math.cos(angle), radius * math.sin(angle), 0.0))
            hsv.append((s / SEGMENTS, sat, 1.0))
    return coords, hsv


def build_wheel():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    coords, hsv = wheel_geometry()
    me = bpy.data.meshes.new("ColorWheel")
    bm = bmesh.new()
    try:
        verts = [bm.verts.new(co) for co in coords]
        for s in range(SEGMENTS):
            bm.faces.new([verts[vidx(0, 0)], verts[vidx(1, s)], verts[vidx(1, s + 1)]])
        for r in range(1, RINGS):
            for s in range(SEGMENTS):
                bm.faces.new([
                    verts[vidx(r, s)], verts[vidx(r, s + 1)],
                    verts[vidx(r + 1, s + 1)], verts[vidx(r + 1, s)],
                ])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()  # the always-free-bmesh contract

    # The contract this example witnesses: a CORNER-domain color attribute,
    # created via color_attributes (not the deprecated vertex_colors alias),
    # sized to loops -- then filled by expanding per-vertex HSV across corners
    # with bulk foreach_get / foreach_set, never a per-loop Python assignment.
    attr = me.color_attributes.new(ATTR_NAME, type='FLOAT_COLOR', domain='CORNER')
    n_loops = len(me.loops)
    loop_vert = array('i', [0]) * n_loops
    me.loops.foreach_get("vertex_index", loop_vert)
    flat = array('f', [0.0]) * (n_loops * 4)
    for i, vi in enumerate(loop_vert):
        h, s, v = hsv[vi]
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        flat[i * 4], flat[i * 4 + 1], flat[i * 4 + 2], flat[i * 4 + 3] = r, g, b, 1.0
    attr.data.foreach_set("color", flat)
    me.color_attributes.active_color = attr  # the step AI code most often forgets

    obj = bpy.data.objects.new("ColorWheel", me)
    bpy.context.collection.objects.link(obj)
    return obj, hsv


def check(obj, hsv):
    me = obj.data
    got = (len(me.vertices), len(me.polygons), len(me.loops))
    expect = (N_VERTS, N_FACES, N_LOOPS)
    if got != expect:
        print(f"ERROR: topology (verts,faces,loops)={got} != expected {expect}", file=sys.stderr)
        return 3

    attr = me.color_attributes.get(ATTR_NAME)
    if attr is None:
        print(f"ERROR: color attribute '{ATTR_NAME}' missing", file=sys.stderr)
        return 4
    if attr.domain != 'CORNER' or attr.data_type != 'FLOAT_COLOR':
        print(f"ERROR: attribute domain/type = {attr.domain}/{attr.data_type}, "
              f"expected CORNER/FLOAT_COLOR", file=sys.stderr)
        return 5
    if len(attr.data) != len(me.loops) or len(attr.data) == len(me.vertices):
        print(f"ERROR: attribute is sized {len(attr.data)}, expected loop count "
              f"{len(me.loops)} and distinct from vertex count {len(me.vertices)} "
              f"-- CORNER domain must not be POINT-sized", file=sys.stderr)
        return 6

    active = me.color_attributes.active_color
    if active is None or active.name != attr.name:
        print(f"ERROR: active_color is "
              f"{active.name if active else None!r}, expected {ATTR_NAME!r}", file=sys.stderr)
        return 7

    n_loops = len(me.loops)
    loop_vert = array('i', [0]) * n_loops
    me.loops.foreach_get("vertex_index", loop_vert)
    colors = array('f', [0.0]) * (n_loops * 4)
    attr.data.foreach_get("color", colors)
    probes = sorted({0, SEGMENTS + 1, n_loops // 2, n_loops - 1})
    for li in probes:
        vi = loop_vert[li]
        h, s, v = hsv[vi]
        er, eg, eb = colorsys.hsv_to_rgb(h, s, v)
        gr, gg, gb, ga = colors[li * 4:li * 4 + 4]
        if max(abs(gr - er), abs(gg - eg), abs(gb - eb), abs(ga - 1.0)) > 1e-5:
            print(f"ERROR: loop {li} (vertex {vi}) color {(gr, gg, gb, ga)} != "
                  f"expected {(er, eg, eb, 1.0)}", file=sys.stderr)
            return 8

    print(f"verts={got[0]} faces={got[1]} loops={got[2]} attribute='{attr.name}' "
          f"domain={attr.domain} active=True probes_ok={len(probes)}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def build_material():
    mat = bpy.data.materials.new("Wheel")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr_node = nt.nodes.new('ShaderNodeAttribute')
    attr_node.attribute_type = 'GEOMETRY'
    attr_node.attribute_name = ATTR_NAME
    nt.links.new(attr_node.outputs["Color"], bsdf.inputs["Base Color"])
    if "Emission Color" in bsdf.inputs:  # Principled gained built-in emission in 4.x+
        nt.links.new(attr_node.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 0.12
    # fully matte: any specular component reflects the wall/floor horizon as
    # a hard line across the disc face
    bsdf.inputs["Roughness"].default_value = 0.85
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0

    # The step AI code most often skips: the attribute must actually be wired
    # into the shader, not just present on the mesh.
    wired = any(
        link.from_node.name == attr_node.name
        and link.from_socket.name == "Color"
        and link.to_socket == bsdf.inputs["Base Color"]
        for link in nt.links
    )
    if not wired:
        print("ERROR: Attribute node is not linked to Base Color", file=sys.stderr)
        return None
    return mat


def render_still(obj, path, engine):
    scene = bpy.context.scene
    for poly in obj.data.polygons:
        poly.use_smooth = True

    mat = build_material()
    if mat is None:
        return False
    obj.data.materials.append(mat)
    # stand the disc up toward the camera like an easel: the wheel is the
    # subject, so it should present nearly face-on and fill the frame instead
    # of lying foreshortened on the floor.
    obj.location = (0.0, 0.0, 1.34)
    obj.rotation_euler = (math.radians(52), 0.0, math.radians(10))

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
    wall.location = (0.0, 7.0, 0.0)
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

    # a bright soft key from above reads the hue ring clearly; a low cool fill
    # keeps the shadow side legible; a faint warm rim separates the disc edge
    # from the dark backdrop without washing out the attribute colors.
    light("Key", (-2.0, -3.0, 5.5), 320.0, 8.0, (1.0, 0.98, 0.96), (58, 0, -28))
    light("Fill", (4.5, -2.5, 1.6), 90.0, 9.0, (0.78, 0.86, 1.0), (68, 0, 55))
    light("Rim", (0.5, 3.6, 2.2), 170.0, 4.0, (1.0, 0.78, 0.55), (-70, 0, 175))
    # a warm wedge raking the back wall — the falloff pool behind the subject
    # the rest of the gallery stages against.
    # placed between the disc and the back wall so it can only rake the wall:
    # from any position in front, its grazing terminator draws a hard line
    # across the flat disc face.
    light("Wedge", (2.0, 5.2, 3.6), 220.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = obj.location
    scene.collection.objects.link(aim)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -8.0, 2.4)
    con = cam.constraints.new('TRACK_TO')
    con.target = aim
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    scene.collection.objects.link(cam)
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 64
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # AgX (the 4.x/5.x default) compresses bright regions toward white, which
    # would hide exactly the saturation gradient this example is showing off.
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

    obj, hsv = build_wheel()
    code = check(obj, hsv)
    if code:
        return code

    if args.output:
        if not render_still(obj, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 9
        print(f"rendered still {args.output}")

    print("color-attribute-wheel OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
