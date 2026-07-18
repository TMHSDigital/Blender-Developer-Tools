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

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python grease_pencil_rosette.py --                # check only
    blender --background --python grease_pencil_rosette.py -- --output r.png # + render
"""
import bpy, sys, os, math, argparse, colorsys

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


def build_rosette():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    gp = gp_data_new("Rosette")
    layer = gp.layers.new("Ink")
    frame = layer.frames.new(1)
    drawing = frame.drawing

    drawing.add_strokes([POINTS] * RINGS)
    for ring, stroke in enumerate(drawing.strokes):
        stroke.cyclic = True
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


def render_still(obj, path, engine):
    scene = bpy.context.scene
    obj.data.layers[0].use_lights = False   # neon ink stays unlit and vivid
    obj.location = (0.0, 0.0, 1.9)
    obj.rotation_euler = (math.radians(4), 0.0, 0.0)
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
    fmat = bpy.data.materials.new("Studio")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.045, 0.05, 0.065, 1.0)
    fb.inputs["Roughness"].default_value = 0.35
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 6.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.01, 0.012, 0.02, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # the strokes are unlit; this only paints a soft halo on the wall behind them
    light("Halo", (0.0, 3.2, 1.9), 260.0, 7.0, (0.4, 0.45, 1.0), (90, 0, 0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -9.5, 1.9)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
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

    obj = build_rosette()
    code = check(obj)
    if code:
        return code

    if args.output:
        if not render_still(obj, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 9
        print(f"rendered still {args.output}")

    print("grease-pencil-rosette OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
