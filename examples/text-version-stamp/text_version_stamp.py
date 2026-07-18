"""A beveled 3D stamp of the running Blender version — a runnable example.

Witnesses the TextCurve data-API contract: `bpy.data.curves.new(type='FONT')`
returns a Curve subclass whose `body` is plain assignable text, whose default
font ("Bfont Regular") is always loaded even headless, and whose `extrude` /
`bevel_depth` produce exactly predictable solid geometry — the evaluated mesh
z-extent equals 2 x (extrude + bevel_depth) and the round bevel widens the
glyph outline in-plane by 2 x bevel_depth. Because the body is the live
`bpy.app.version_string`, every render self-documents which Blender made it.

Version note: the string format itself diverges — plain "5.1.2" on 5.x but
"4.5.11 LTS" on 4.5 — so the check asserts the cross-version contract
(`version_string` starts with the dotted `bpy.app.version` tuple), not an
exact format. It also witnesses the depsgraph lifetime hazard: after
`to_mesh_clear()` the returned Mesh reference is dead and any access raises
ReferenceError.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python text_version_stamp.py --                 # check only
    blender --background --python text_version_stamp.py -- --output v.png  # + render
"""
import bpy, sys, os, math, argparse

EXTRUDE = 0.06
BEVEL = 0.02
TOL = 1e-4


def build_stamp():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    txt = bpy.data.curves.new("VersionStamp", type='FONT')
    txt.body = bpy.app.version_string  # the self-documenting payload
    txt.align_x = 'CENTER'
    txt.align_y = 'CENTER'
    obj = bpy.data.objects.new("VersionStamp", txt)
    bpy.context.collection.objects.link(obj)
    return obj


def eval_extents(obj, deps):
    """(vert count, face count, x extent, z extent) of the evaluated mesh."""
    deps.update()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    xs = [v.co.x for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    out = (len(me.vertices), len(me.polygons),
           max(xs) - min(xs) if xs else 0.0,
           max(zs) - min(zs) if zs else 0.0)
    ev.to_mesh_clear()
    return out, me  # me is now DEAD — returned only to witness that


def check(obj):
    txt = obj.data

    # TextCurve is a Curve; a FONT object; the built-in font is always loaded
    if not isinstance(txt, bpy.types.TextCurve) or not isinstance(txt, bpy.types.Curve):
        print("ERROR: curves.new(type='FONT') did not return a TextCurve/Curve",
              file=sys.stderr)
        return 3
    if obj.type != 'FONT' or txt.font is None or "Bfont" not in txt.font.name:
        print(f"ERROR: expected a FONT object with the built-in Bfont, got "
              f"type={obj.type} font={txt.font}", file=sys.stderr)
        return 3

    # body is the live version string, and version_string starts with the
    # dotted version tuple on every supported release ("5.1.2", "4.5.11 LTS")
    dotted = "%d.%d.%d" % bpy.app.version
    if txt.body != bpy.app.version_string or not bpy.app.version_string.startswith(dotted):
        print(f"ERROR: body={txt.body!r} version_string={bpy.app.version_string!r} "
              f"tuple={bpy.app.version}", file=sys.stderr)
        return 4

    deps = bpy.context.evaluated_depsgraph_get()

    # flat text: glyph outlines are filled (faces exist) but strictly planar
    (nv, nf, x_flat, z_flat), _ = eval_extents(obj, deps)
    if nf == 0 or z_flat > TOL:
        print(f"ERROR: flat text expected filled planar mesh, got faces={nf} "
              f"z-extent={z_flat}", file=sys.stderr)
        return 5

    # solidify: z-extent is exactly 2*(extrude+bevel), bevel widens x by 2*bevel
    txt.extrude = EXTRUDE
    txt.bevel_depth = BEVEL
    txt.bevel_resolution = 3
    (nv, nf, x_solid, z_solid), dead = eval_extents(obj, deps)
    want_z = 2.0 * (EXTRUDE + BEVEL)
    want_x = x_flat + 2.0 * BEVEL
    if abs(z_solid - want_z) > TOL or abs(x_solid - want_x) > TOL:
        print(f"ERROR: extrude/bevel closed form failed: z {z_solid:.5f} != "
              f"{want_z:.5f} or x {x_solid:.5f} != {want_x:.5f}", file=sys.stderr)
        return 6

    # editing body regenerates geometry: more characters -> strictly wider
    txt.body = txt.body + " WWW"
    (_, _, x_long, _), _ = eval_extents(obj, deps)
    txt.body = bpy.app.version_string
    if x_long <= x_solid:
        print(f"ERROR: appending characters did not widen the text "
              f"({x_long:.5f} <= {x_solid:.5f})", file=sys.stderr)
        return 7

    # lifetime hazard: after to_mesh_clear() the Mesh reference is dead
    try:
        len(dead.vertices)
        print("ERROR: Mesh survived to_mesh_clear() — lifetime contract broken",
              file=sys.stderr)
        return 8
    except ReferenceError:
        pass

    print(f"body={txt.body!r} flat x-extent={x_flat:.4f} solid z-extent={z_solid:.4f} "
          f"(= 2*(extrude+bevel)) faces={nf}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(obj, path, engine):
    scene = bpy.context.scene
    txt = obj.data
    txt.size = 1.0
    txt.space_character = 1.05

    # brass stamp
    mat = bpy.data.materials.new("Brass")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.85, 0.62, 0.28, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.32
    txt.materials.append(mat)

    # stand the text upright, feet on the floor, scaled to a constant width
    # so the frame works for any version-string length ("5.1.2", "4.5.11 LTS")
    deps = bpy.context.evaluated_depsgraph_get()
    deps.update()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    width = max(v.co.x for v in me.vertices) - min(v.co.x for v in me.vertices)
    height = max(v.co.y for v in me.vertices) - min(v.co.y for v in me.vertices)
    ev.to_mesh_clear()
    s = 3.1 / width
    obj.scale = (s, s, s)
    obj.rotation_euler = (math.radians(90), 0.0, 0.0)
    obj.location = (0.0, 0.0, s * height / 2 + 0.02)

    # small steel caption above, also a TextCurve
    cap = bpy.data.curves.new("Caption", type='FONT')
    cap.body = "B L E N D E R"
    cap.align_x = 'CENTER'; cap.align_y = 'CENTER'
    cap.size = 0.34; cap.extrude = 0.012; cap.bevel_depth = 0.004
    cmat = bpy.data.materials.new("Steel")
    cmat.use_nodes = True
    cb = cmat.node_tree.nodes["Principled BSDF"]
    cb.inputs["Base Color"].default_value = (0.62, 0.66, 0.72, 1.0)
    cb.inputs["Metallic"].default_value = 1.0
    cb.inputs["Roughness"].default_value = 0.4
    cap.materials.append(cmat)
    cap_obj = bpy.data.objects.new("Caption", cap)
    cap_obj.rotation_euler = (math.radians(90), 0.0, 0.0)
    cap_obj.location = (0.0, 0.0, s * height + 0.62)
    scene.collection.objects.link(cap_obj)

    # teal emissive underline bar grounding the stamp
    import bmesh
    bar_me = bpy.data.meshes.new("Bar")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(bar_me)
    finally:
        bm.free()
    bmat = bpy.data.materials.new("Glow")
    bmat.use_nodes = True
    bb = bmat.node_tree.nodes["Principled BSDF"]
    bb.inputs["Emission Color"].default_value = (0.1, 0.9, 0.8, 1.0)
    bb.inputs["Emission Strength"].default_value = 14.0
    bar_me.materials.append(bmat)
    bar = bpy.data.objects.new("Bar", bar_me)
    bar.scale = (3.9, 0.06, 0.02)
    bar.location = (0.0, -0.35, 0.02)
    scene.collection.objects.link(bar)

    # dark studio: floor + back wall
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
    fb.inputs["Base Color"].default_value = (0.05, 0.055, 0.065, 1.0)
    fb.inputs["Roughness"].default_value = 0.35
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 11.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.03, 0.035, 0.045, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # brass reads on reflections: warm key, broad cool fill, hard warm rim
    light("Key", (-3.2, -4.8, 4.6), 850.0, 6.0, (1.0, 0.95, 0.86), (52, 0, -32))
    light("Fill", (4.6, -3.6, 2.4), 320.0, 8.0, (0.75, 0.84, 1.0), (66, 0, 48))
    light("Rim", (0.8, 4.2, 3.4), 900.0, 3.0, (1.0, 0.75, 0.45), (-65, 0, 170))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -8.5, 1.15)
    cam.rotation_euler = (math.radians(86.5), 0.0, 0.0)
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

    obj = build_stamp()
    code = check(obj)
    if code:
        return code

    if args.output:
        if not render_still(obj, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 9
        print(f"rendered still {args.output}")

    print("text-version-stamp OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
