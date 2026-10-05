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
    blender --background --python color_attribute_wheel.py -- --point-domain   # must fail
    blender --background --python color_attribute_wheel.py -- --output w.png  # + render
"""
import bpy, bmesh, sys, os, math, colorsys, argparse
from array import array
from mathutils import Vector

# Shared Layer 1 framing measurement (render path only) — see
# gallery_framing.py for the __file__-relative import shim this relies on.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
import gallery_framing  # noqa: E402

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


def build_wheel(point_domain=False):
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
    domain = 'POINT' if point_domain else 'CORNER'
    attr = me.color_attributes.new(ATTR_NAME, type='FLOAT_COLOR', domain=domain)
    if not point_domain:
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
    # glazed ceramic: a satin base under a thin clear coat. The plate is domed
    # (render path), so the coat's reflection is a soft curved sheen, never
    # the hard horizon line a flat mirror-glaze would draw across the face.
    bsdf.inputs["Roughness"].default_value = 0.42
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.25
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.35
        bsdf.inputs["Coat Roughness"].default_value = 0.18
    if "Emission Color" in bsdf.inputs:  # a faint self-glow keeps the far hues from sinking
        nt.links.new(attr_node.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 0.10

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


BEZEL_OUT = R_OUTER + 0.20     # brass bezel outer radius (render path)
DOME = 0.11                     # plate dome height at the centre (render path)
TILT = math.radians(76)         # plate leans back 14 degrees on the easel


def _lathe(bm, profile, segs=96):
    """Revolve an (r, z) profile about local Z (bottom -> out -> up -> in)."""
    rings = [[bm.verts.new((r * math.cos(2 * math.pi * i / segs),
                            r * math.sin(2 * math.pi * i / segs), z)) for i in range(segs)]
             for r, z in profile]
    for a, b in zip(rings, rings[1:] + rings[:1]):
        for i in range(segs):
            j = (i + 1) % segs
            f = bm.faces.new((a[i], a[j], b[j], b[i]))
            f.smooth = True


def _beam(bm, p0, p1, w, d):
    """A w x d rectangular beam from p0 to p1 (world space)."""
    p0, p1 = Vector(p0), Vector(p1)
    axis = p1 - p0
    res = bmesh.ops.create_cube(bm, size=1.0)
    rot = Vector((0, 0, 1)).rotation_difference(axis.normalized()).to_matrix()
    for v in res["verts"]:
        v.co = rot @ Vector((v.co.x * w, v.co.y * d, v.co.z * axis.length)) + (p0 + p1) / 2


def _mat(name, base, rough, metal=0.0, noise=None, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat and "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
    if noise:
        # grain/handling wear: noise-mottled colour and roughness, never flat
        scale, amount, stretch = noise
        coord = nt.nodes.new("ShaderNodeTexCoord")
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = stretch
        nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = 8.0
        nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(c * (1 - amount) for c in base) + (1.0,)
        ramp.color_ramp.elements[1].color = tuple(min(1.0, c * (1 + amount)) for c in base) + (1.0,)
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
        rmap = nt.nodes.new("ShaderNodeMapRange")
        rmap.inputs["To Min"].default_value = rough - 0.08
        rmap.inputs["To Max"].default_value = rough + 0.12
        nt.links.new(tex.outputs["Fac"], rmap.inputs["Value"])
        nt.links.new(rmap.outputs["Result"], b.inputs["Roughness"])
    return m


def render_still(obj, path, engine):
    scene = bpy.context.scene
    me = obj.data
    for poly in me.polygons:
        poly.use_smooth = True

    mat = build_material()
    if mat is None:
        return 9
    me.materials.append(mat)

    # render-only: dome the checked flat disc into a shallow glazed plate.
    # Only positions move; the CORNER attribute rides the same loops, so the
    # colours the check verified are the colours on the plate.
    co = array('f', [0.0]) * (len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    for i in range(len(me.vertices)):
        x, y = co[3 * i], co[3 * i + 1]
        co[3 * i + 2] = DOME * (1.0 - (x * x + y * y) / (R_OUTER * R_OUTER))
    me.vertices.foreach_set("co", co)
    me.update()
    solid = obj.modifiers.new("Body", 'SOLIDIFY')
    solid.thickness = 0.06
    solid.offset = -1.0

    brass = _mat("Brass", (0.92, 0.66, 0.30), 0.32, metal=1.0, noise=(40.0, 0.07, (1, 1, 1)))
    wood = _mat("Walnut", (0.20, 0.095, 0.045), 0.5, noise=(6.0, 0.45, (1.0, 1.0, 14.0)),
                coat=0.2)
    backing = _mat("Backing", (0.03, 0.03, 0.035), 0.55)

    # brass bezel and a dark backing plate, built in plate space
    bezel_me = bpy.data.meshes.new("Bezel")
    bm = bmesh.new()
    try:
        # rolled lip over the plate edge, a flat band, a turned-down skirt
        _lathe(bm, [(R_OUTER - 0.02, -0.10), (BEZEL_OUT, -0.10), (BEZEL_OUT + 0.01, -0.06),
                    (BEZEL_OUT, 0.02), (BEZEL_OUT - 0.04, 0.05), (R_OUTER + 0.03, 0.055),
                    (R_OUTER - 0.03, 0.035), (R_OUTER - 0.05, 0.005)])
        bm.to_mesh(bezel_me)
    finally:
        bm.free()
    bezel_me.materials.append(brass)
    bezel = bpy.data.objects.new("Bezel", bezel_me)
    scene.collection.objects.link(bezel)
    back_me = bpy.data.meshes.new("Backing")
    bm = bmesh.new()
    try:
        bmesh.ops.create_circle(bm, cap_ends=True, segments=96, radius=BEZEL_OUT - 0.02)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0.0, 0.0, -0.105))
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
        bm.to_mesh(back_me)
    finally:
        bm.free()
    back_me.materials.append(backing)
    back = bpy.data.objects.new("Backing", back_me)
    scene.collection.objects.link(back)

    # the plate stands on a walnut easel, leaning back against its front legs
    ledge_z = 0.55
    zc = ledge_z + 0.06 + BEZEL_OUT * math.sin(TILT)
    for ob in (obj, bezel, back):
        ob.location = (0.0, 0.0, zc)
        ob.rotation_euler = (TILT, 0.0, 0.0)
    bpy.context.view_layer.update()
    # the plate's mid-plane: y = cot(TILT) * (z - zc); the back sits behind it
    cot = math.cos(TILT) / math.sin(TILT)

    def plane_y(z):
        return cot * (z - zc)

    easel_me = bpy.data.meshes.new("Easel")
    bm = bmesh.new()
    try:
        top = zc + BEZEL_OUT * math.sin(TILT) + 0.12
        for sx in (-1.0, 1.0):
            _beam(bm, (sx * 1.05, plane_y(0.0) + 0.22, 0.0),
                  (sx * 0.22, plane_y(top) + 0.22, top), 0.11, 0.07)
        _beam(bm, (0.0, 1.9, 0.0), (0.0, plane_y(top - 0.3) + 0.32, top - 0.3), 0.10, 0.07)
        # ledge the plate rests on, with a front lip, and a cross rail
        ly = plane_y(ledge_z) - 0.02
        _beam(bm, (-1.15, ly, ledge_z), (1.15, ly, ledge_z), 0.30, 0.07)
        _beam(bm, (-1.15, ly - 0.14, ledge_z + 0.035), (1.15, ly - 0.14, ledge_z + 0.035), 0.03, 0.10)
        _beam(bm, (-0.95, plane_y(0.28) + 0.23, 0.28), (0.95, plane_y(0.28) + 0.23, 0.28), 0.07, 0.06)
        bm.to_mesh(easel_me)
    finally:
        bm.free()
    easel_me.materials.append(wood)
    easel = bpy.data.objects.new("Easel", easel_me)
    scene.collection.objects.link(easel)

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
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, at):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(at) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(ob)

    centre = (0.0, 0.0, zc)
    # soft key high left, sized so the glaze sheen is a broad soft highlight;
    # a cool low fill; a warm rim on the brass; the wedge rakes the back wall
    light("Key", (-4.2, -3.6, 6.0), 230.0, 3.0, (1.0, 0.96, 0.9), centre)
    light("Fill", (4.5, -3.0, 1.8), 70.0, 9.0, (0.78, 0.86, 1.0), centre)
    light("Rim", (3.4, 2.4, 5.2), 420.0, 2.5, (1.0, 0.82, 0.6), (0.0, 0.0, zc + 1.2))
    light("Wedge", (0.5, 5.2, 5.5), 650.0, 8.0, (1.0, 0.70, 0.42), (1.5, 9.0, 1.5))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, zc - 0.30)
    scene.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 57.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-3.0, -13.2, 3.3)
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
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # AgX (the 4.x/5.x default) compresses bright regions toward white, which
    # would hide exactly the saturation gradient this example is showing off.
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()
    # Layer 1 framing gate before the beauty render (exit 10 on violation)
    fcode = gallery_framing.check_framing(scene, cam, hero=[obj, bezel],
                                          elements=[obj, bezel, back, easel],
                                          stage=[floor, wall])
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    return 0 if os.path.exists(path) and os.path.getsize(path) > 0 else 9


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--point-domain", action="store_true",
                   help="create a POINT-domain color attribute (must fail)")
    args = p.parse_args(argv)

    obj, hsv = build_wheel(point_domain=args.point_domain)
    code = check(obj, hsv)
    if code:
        return code

    if args.output:
        rcode = render_still(obj, os.path.abspath(args.output), args.engine)
        if rcode:
            if rcode == 9:
                print("ERROR: render produced no file", file=sys.stderr)
            return rcode
        print(f"rendered still {args.output}")

    print("color-attribute-wheel OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
