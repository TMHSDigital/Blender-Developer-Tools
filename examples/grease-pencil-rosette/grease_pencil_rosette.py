"""A neon rose-curve set drawn with GPv3 strokes — a runnable example.

Witnesses the Grease Pencil v3 rewrite, the largest bpy API break in the
4.x-to-5.x window. GPv3 is present on both supported versions but lives at
DIFFERENT addresses:

- Blender 4.5 LTS: GPv3 is `bpy.data.grease_pencils_v3` (`GreasePencilv3`);
  `bpy.data.grease_pencils` still holds LEGACY GPencil datablocks whose frames
  carry `.strokes` directly — same collection name, incompatible API.
- Blender 5.x: legacy is gone, GPv3 took over the `bpy.data.grease_pencils`
  name (`GreasePencil`), and `grease_pencils_v3` / `GPencilStroke` no longer
  exist.

The shared GPv3 surface is attribute-based: layer -> frames.new(n).drawing ->
add_strokes([counts]) -> point.position/radius/opacity/vertex_color, where
stroke points are views over attribute layers that materialize lazily in
`drawing.attributes`. The check asserts the address divergence on each side,
the legacy trap on 4.5, the structural contract, lazy attribute
materialization, and a closed-form round-trip of every position through the
raw POINT attribute buffer.

``--open-strokes`` leaves every stroke non-cyclic and still asserts they
are cyclic. That is the falsifier (``--same-axis`` in export-preset-axis).
The GPv3 address shim is untouched.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python grease_pencil_rosette.py --                  # check only
    blender --background --python grease_pencil_rosette.py -- --open-strokes   # must fail
    blender --background --python grease_pencil_rosette.py -- --output r.png   # + render
"""
import bpy, sys, os, math, argparse, colorsys

# Shared Layer 1 framing measurement (render path only) -- see
# gallery_framing.py for the __file__-relative import shim this relies on.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
import gallery_framing  # noqa: E402

RINGS = 5           # nested rose curves, one stroke each
POINTS = 192        # samples per stroke
R_OUTER = 1.55      # radius of the outermost rose
BASE_RADIUS = 0.02  # base line half-width in world units
TOL = 1e-4


def rose_point(ring, i):
    """Closed-form sample i of ring's rose curve r = a*(0.72 + 0.28*cos(k*t)),
    laid out upright in the XZ plane. Single source of truth for build & check."""
    k = 3 + ring                          # petal frequency
    a = R_OUTER * (1.0 - ring / (RINGS + 1.5))
    phase = ring * math.pi / 7.0
    t = 2.0 * math.pi * i / POINTS
    r = a * (0.72 + 0.28 * math.cos(k * t))
    return (r * math.cos(t + phase), 0.0, r * math.sin(t + phase))


def point_radius(ring, i):
    """Calligraphic taper: width swells on the petal tips."""
    k = 3 + ring
    t = 2.0 * math.pi * i / POINTS
    return BASE_RADIUS * (0.55 + 1.45 * (0.5 + 0.5 * math.cos(k * t)))


def ring_color(ring, i):
    """Neon hue per ring, drifting slightly along the stroke."""
    h = (0.52 + ring / RINGS * 0.55 + 0.04 * math.sin(2 * math.pi * i / POINTS)) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.96, 1.0)
    return (r, g, b, 1.0)


def gp_data_new(name):
    """THE version gate this example exists for: GPv3 datablock creation."""
    if bpy.app.version >= (5, 0, 0):
        return bpy.data.grease_pencils.new(name)      # GPv3 owns the name in 5.x
    return bpy.data.grease_pencils_v3.new(name)       # 4.5 LTS: GPv3 lives at _v3


def build_rosette(open_strokes=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    gp = gp_data_new("Rosette")
    layer = gp.layers.new("Ink")
    frame = layer.frames.new(1)
    drawing = frame.drawing

    drawing.add_strokes([POINTS] * RINGS)
    for ring, stroke in enumerate(drawing.strokes):
        stroke.cyclic = not open_strokes
        for i, pt in enumerate(stroke.points):

            pt.position = rose_point(ring, i)
            pt.radius = point_radius(ring, i)
            pt.opacity = 1.0
            pt.vertex_color = ring_color(ring, i)

    mat = bpy.data.materials.new("Neon Ink")
    bpy.data.materials.create_gpencil_data(mat)       # same helper on 4.5 and 5.x
    mat.grease_pencil.color = (1.0, 1.0, 1.0, 1.0)    # vertex colors carry the hue
    gp.materials.append(mat)

    obj = bpy.data.objects.new("Rosette", gp)
    bpy.context.collection.objects.link(obj)
    return obj


def check_version_gate():
    """Assert the API break each side actually exposes."""
    if bpy.app.version >= (5, 0, 0):
        if hasattr(bpy.data, "grease_pencils_v3") or hasattr(bpy.types, "GPencilStroke"):
            print("ERROR: 5.x still exposes legacy GP names — gate is wrong", file=sys.stderr)
            return 3
        print("5.x contract: grease_pencils is GPv3; _v3 alias and GPencilStroke are gone")
    else:
        if not hasattr(bpy.data, "grease_pencils_v3") or not hasattr(bpy.types, "GPencilStroke"):
            print("ERROR: 4.5 is missing grease_pencils_v3 or legacy GPencilStroke", file=sys.stderr)
            return 3
        # The trap: on 4.5 `bpy.data.grease_pencils` is LEGACY GPencil. Its frames
        # carry `.strokes` directly and have no `.drawing` — code written for one
        # API fails on the other despite the identical collection name.
        legacy = bpy.data.grease_pencils.new("_legacy_probe")
        try:
            lframe = legacy.layers.new("L").frames.new(1)
            if hasattr(lframe, "drawing") or not hasattr(lframe, "strokes"):
                print("ERROR: 4.5 grease_pencils did not behave as legacy GPencil", file=sys.stderr)
                return 3
        finally:
            bpy.data.grease_pencils.remove(legacy)
        print("4.5 contract: grease_pencils is legacy (frame.strokes); GPv3 lives at _v3")
    return 0


def check(obj):
    code = check_version_gate()
    if code:
        return code

    if obj.type != 'GREASEPENCIL':
        print(f"ERROR: object type {obj.type!r} != 'GREASEPENCIL'", file=sys.stderr)
        return 4

    gp = obj.data
    if len(gp.layers) != 1:
        print(f"ERROR: {len(gp.layers)} layers != 1", file=sys.stderr)
        return 4
    frame = gp.layers[0].frames[0]
    if frame.frame_number != 1:
        print(f"ERROR: frame_number {frame.frame_number} != 1", file=sys.stderr)
        return 4
    drawing = frame.drawing

    strokes = drawing.strokes
    if len(strokes) != RINGS or any(len(s.points) != POINTS for s in strokes):
        print(f"ERROR: stroke topology != {RINGS} x {POINTS}", file=sys.stderr)
        return 5
    if not all(s.cyclic for s in strokes):
        print("ERROR: not every stroke is cyclic", file=sys.stderr)
        return 5

    # Lazy materialization: writing through the point view must have created
    # these attribute layers on the drawing (they are absent on a fresh drawing).
    attrs = {a.name: (a.domain, a.data_type) for a in drawing.attributes}
    expected = {
        "position": ('POINT', 'FLOAT_VECTOR'),
        "radius": ('POINT', 'FLOAT'),
        "opacity": ('POINT', 'FLOAT'),
        "vertex_color": ('POINT', 'FLOAT_COLOR'),
        "cyclic": ('CURVE', 'BOOLEAN'),
    }
    for name, sig in expected.items():
        if attrs.get(name) != sig:
            print(f"ERROR: attribute {name!r} is {attrs.get(name)} != {sig}", file=sys.stderr)
            return 6

    # Round-trip: the raw POINT attribute buffer must hold every closed-form
    # position — stroke points are views over this buffer, not copies.
    pos = drawing.attributes["position"]
    n = len(pos.data)
    if n != RINGS * POINTS:
        print(f"ERROR: position buffer {n} points != {RINGS * POINTS}", file=sys.stderr)
        return 7
    buf = [0.0] * (3 * n)
    pos.data.foreach_get("vector", buf)
    worst = 0.0
    for ring in range(RINGS):
        for i in range(POINTS):
            j = 3 * (ring * POINTS + i)
            ex, ey, ez = rose_point(ring, i)
            worst = max(worst, abs(buf[j] - ex), abs(buf[j + 1] - ey), abs(buf[j + 2] - ez))
    if worst > TOL:
        print(f"ERROR: attribute buffer deviates {worst} > {TOL} from closed form", file=sys.stderr)
        return 7

    if len(gp.materials) != 1 or gp.materials[0].grease_pencil is None:
        print("ERROR: grease pencil material missing its gpencil settings", file=sys.stderr)
        return 8

    print(f"rings={RINGS} points/stroke={POINTS} attrs=lazy-materialized "
          f"round-trip worst={worst:.2e} object=GREASEPENCIL")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def _box(name, dims, loc, mat, bevel=0.0, segments=3):
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= dims[0]; v.co.y *= dims[1]; v.co.z *= dims[2]
        if bevel > 0.0:
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=segments,
                            profile=0.5, affect='EDGES', clamp_overlap=True)
        bm.to_mesh(me)
    finally:
        bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _mat(name, rgb, rough, metal=0.0, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    return m


def render_still(obj, path, engine):
    """The rosette as a neon sign: the unlit GPv3 strokes are the tubes,
    mounted a few centimetres proud of a black-lacquer backboard in a brass
    frame, hung on the studio wall. Coloured area lights just in front of the
    board stand in for the spill real neon throws on its backing."""
    scene = bpy.context.scene
    obj.data.layers[0].use_lights = False   # neon ink stays unlit and vivid
    SIGN_Z = 2.25
    obj.location = (0.0, -0.06, SIGN_Z)
    # unlit saturated ink wants the graphic transform, not AgX's filmic desaturation
    scene.view_settings.view_transform = 'Standard'

    import bmesh
    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = _mat("Studio", (0.03, 0.032, 0.037), 0.7)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 0.32, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.012, 0.012, 0.016, 1.0)
    scene.world = world

    # sign: black lacquer board, brass frame, four brass standoff caps
    lacquer = _mat("Lacquer", (0.02, 0.02, 0.024), 0.55, coat=0.15)
    brass = _mat("Brass", (0.78, 0.55, 0.24), 0.28, metal=1.0)
    BW, BH = 4.0, 3.7
    board = _box("SignBoard", (BW, 0.06, BH), (0.0, 0.26, SIGN_Z), lacquer, bevel=0.015)
    fw = 0.09
    frame = [
        _box("FrameTop", (BW + 2 * fw, 0.1, fw), (0.0, 0.24, SIGN_Z + BH / 2 + fw / 2), brass, 0.02),
        _box("FrameBot", (BW + 2 * fw, 0.1, fw), (0.0, 0.24, SIGN_Z - BH / 2 - fw / 2), brass, 0.02),
        _box("FrameL", (fw, 0.1, BH), (-(BW + fw) / 2, 0.24, SIGN_Z), brass, 0.02),
        _box("FrameR", (fw, 0.1, BH), ((BW + fw) / 2, 0.24, SIGN_Z), brass, 0.02),
    ]
    caps = []
    for sx in (-1, 1):
        for sz in (-1, 1):
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.07, depth=0.1,
                                                location=(sx * (BW / 2 - 0.25), 0.18,
                                                          SIGN_Z + sz * (BH / 2 - 0.25)),
                                                rotation=(math.radians(90), 0, 0))
            cap = bpy.context.active_object
            cap.data.materials.append(brass)
            caps.append(cap)
    # a brass plate under the tubes, a mains cable dropping to the floor
    plate = _box("MakerPlate", (0.9, 0.03, 0.16), (0.0, 0.215, SIGN_Z - BH / 2 + 0.22), brass, 0.01)
    cable_mat = _mat("Cable", (0.02, 0.02, 0.02), 0.45)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.018, depth=SIGN_Z - BH / 2 - fw,
                                        location=(1.35, 0.28, (SIGN_Z - BH / 2 - fw) / 2))
    cable = bpy.context.active_object
    cable.data.materials.append(cable_mat)
    sign = [board, plate, cable] + frame + caps

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)
        return ld

    # neon spill: one small shadowless disk per ring, set just in front of
    # the board on that ring's rose and tinted with its colour, so each tube
    # washes the satin lacquer behind it the way real neon does
    for ring in range(RINGS):
        for i in range(0, POINTS, POINTS // 16):
            x, _y, z = rose_point(ring, i)
            ld = bpy.data.lights.new(f"Spill{ring}_{i}", 'AREA')
            ld.shape = 'DISK'
            ld.size = 0.6
            ld.energy = 0.9
            ld.color = ring_color(ring, i)[:3]
            ld.use_shadow = False
            lo = bpy.data.objects.new(ld.name, ld)
            lo.location = (x, 0.05, SIGN_Z + z)
            lo.rotation_euler = (math.radians(90), 0.0, 0.0)  # emit along +Y, onto the board
            scene.collection.objects.link(lo)
    # warm key grazing the brass frame, cool fill, warm wedge on the wall
    light("Key", (-4.5, -5.0, 5.5), 200.0, 3.0, (1.0, 0.93, 0.85), (48, 0, -40))
    light("Fill", (5.0, -4.0, 2.5), 50.0, 8.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Wedge", (3.2, -1.6, 4.6), 380.0, 4.0, (1.0, 0.70, 0.42), (40, 0, 60))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 41.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-2.6, -9.2, 2.3)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.2, SIGN_Z - 0.05)
    scene.collection.objects.link(aim)
    tr = cam.constraints.new('TRACK_TO')
    tr.target = aim
    tr.track_axis = 'TRACK_NEGATIVE_Z'
    tr.up_axis = 'UP_Y'
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 32
    else:
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    bpy.context.view_layer.update()
    # Layer 1 framing gate before the beauty render (exit 10 on violation)
    fcode = gallery_framing.check_framing(scene, cam, hero=[board] + frame,
                                          elements=[obj, board, plate] + frame + caps, stage=[floor, wall])
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
    p.add_argument("--open-strokes", action="store_true",
                   help="falsifier: strokes not cyclic, still assert cyclic")
    args = p.parse_args(argv)

    obj = build_rosette(open_strokes=args.open_strokes)

    code = check(obj)
    if code:
        return code

    if args.output:
        rcode = render_still(obj, os.path.abspath(args.output), args.engine)
        if rcode:
            if rcode == 9:
                print("ERROR: render produced no file", file=sys.stderr)
            return rcode
        print(f"rendered still {args.output}")

    print("grease-pencil-rosette OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
