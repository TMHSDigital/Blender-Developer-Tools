"""Beveled Bezier arc via the curve data API — a runnable example.

Witnesses that renderable tubes are authored on `bpy.types.Curve` directly
(`splines.new('BEZIER')`, `bezier_points`, `bevel_depth`, `use_fill_caps`) —
not by meshing first or calling curve operators. The check asserts the
closed-form point count and bevel depth, the closed-form Z span (tube
centerline at `z = bevel_depth`, resting on the floor) and X span, plus the
evaluated vert/face counts as a MEASURED regression gate — curve tessellation
has no simple closed form, so those two constants pin today's behavior (see
EXPECT_VERTS below for how to re-measure if a future Blender retessellates).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python curve_bevel_arc.py --                 # check only
    blender --background --python curve_bevel_arc.py -- --output c.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

N_POINTS = 8
RADIUS = 1.5
BEVEL = 0.15
BEVEL_RES = 4
RES_U = 12
# MEASURED regression constants, not closed-form: curve-to-mesh tessellation
# (rings x bevel segments + cap fans) has no simple formula. Verified identical
# on 4.4, 4.5 LTS, and 5.1. If a future Blender changes tessellation, re-measure
# by printing len(em.vertices)/len(em.polygons) in check() and update these.
EXPECT_VERTS = 1044
EXPECT_FACES = 1028


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    curve = bpy.data.curves.new("Arc", 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = BEVEL
    curve.bevel_resolution = BEVEL_RES
    curve.resolution_u = RES_U
    curve.use_fill_caps = True  # solid ends — not a hollow pipe

    spline = curve.splines.new('BEZIER')
    spline.bezier_points.add(N_POINTS - 1)  # one point exists already
    for i, bp in enumerate(spline.bezier_points):
        a = i / (N_POINTS - 1) * math.pi  # semicircle in XY
        # centerline at z=BEVEL so the tube rests on the floor
        bp.co = (RADIUS * math.cos(a), RADIUS * math.sin(a), BEVEL)
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'

    obj = bpy.data.objects.new("Arc", curve)
    bpy.context.collection.objects.link(obj)
    return obj


def check(obj):
    curve = obj.data
    if curve.splines[0].type != 'BEZIER':
        print(f"ERROR: spline type {curve.splines[0].type} != BEZIER", file=sys.stderr)
        return 3
    n = len(curve.splines[0].bezier_points)
    if n != N_POINTS:
        print(f"ERROR: bezier points {n} != {N_POINTS}", file=sys.stderr)
        return 4
    if abs(curve.bevel_depth - BEVEL) > 1e-6:
        print(f"ERROR: bevel_depth {curve.bevel_depth} != {BEVEL}", file=sys.stderr)
        return 5
    if not curve.use_fill_caps:
        print("ERROR: use_fill_caps is False — ends should be capped", file=sys.stderr)
        return 6

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    em = ev.to_mesh()
    try:
        got_v = len(em.vertices)
        got_f = len(em.polygons)
        zs = [v.co.z for v in em.vertices]
        z_lo, z_hi = min(zs), max(zs)
        # arc spans x in [-RADIUS, +RADIUS] at the endpoints
        xs = [v.co.x for v in em.vertices]
        x_span = max(xs) - min(xs)
    finally:
        ev.to_mesh_clear()

    if got_v != EXPECT_VERTS or got_f != EXPECT_FACES:
        print(f"ERROR: evaluated topology verts={got_v} faces={got_f} != "
              f"expected verts={EXPECT_VERTS} faces={EXPECT_FACES}",
              file=sys.stderr)
        return 7

    # tube diameter = 2 * bevel; centerline at z=BEVEL → span [0, 2*BEVEL]
    if abs(z_lo) > 1e-4:
        print(f"ERROR: tube does not rest on floor (z_lo={z_lo:.6f})", file=sys.stderr)
        return 8
    if abs(z_hi - 2 * BEVEL) > 1e-4:
        print(f"ERROR: tube height {z_hi:.4f} != 2*bevel={2 * BEVEL:.4f}",
              file=sys.stderr)
        return 9
    # diameter adds 2*BEVEL to the arc's 2*RADIUS span
    expect_x_span = 2 * RADIUS + 2 * BEVEL
    if abs(x_span - expect_x_span) > 0.05:
        print(f"ERROR: x span {x_span:.4f} != {expect_x_span:.4f}", file=sys.stderr)
        return 10

    print(f"points={n} bevel={BEVEL} caps=True eval_verts={got_v} "
          f"eval_faces={got_f} z={z_lo:.3f}..{z_hi:.3f} x_span={x_span:.3f}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(obj, path, engine):
    scene = bpy.context.scene
    mat = bpy.data.materials.new("Rose")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.95, 0.10, 0.38, 1.0)  # rose
    bsdf.inputs["Roughness"].default_value = 0.24
    obj.data.materials.append(mat)
    obj.rotation_euler = (0.0, 0.0, math.radians(-18))

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

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.35, BEVEL)
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

    # warm shaped key, faint cool fill, warm wedge on the back wall
    # (docs/VISUAL-STYLE.md)
    light("Key", (-3.5, -4.5, 5.5), 550.0, 4.5, (1.0, 0.96, 0.9))
    light("Fill", (5.0, -3.5, 2.5), 110.0, 8.0, (0.75, 0.85, 1.0))
    wedge = bpy.data.lights.new("Wedge", 'AREA')
    wedge.energy = 380.0
    wedge.size = 6.0
    wedge.color = (1.0, 0.76, 0.5)
    wob = bpy.data.objects.new("Wedge", wedge)
    wob.location = (2.5, 5.5, 4.0)
    wob.rotation_euler = (math.radians(-68), 0.0, math.radians(190))
    scene.collection.objects.link(wob)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.55, -3.62, 1.78)
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
    # AgX would wash the rose tube toward salmon (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact.
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=[obj],
        elements=[obj],
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 11
    return 0


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
        rcode = render_still(obj, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("curve-bevel-arc OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
