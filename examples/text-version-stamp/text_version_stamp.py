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

``--wrong-body`` assigns a string that is not ``version_string`` and still
asserts the body is the live version. That is the falsifier (``--same-axis``
in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python text_version_stamp.py --                   # check only
    blender --background --python text_version_stamp.py -- --wrong-body      # must fail
    blender --background --python text_version_stamp.py -- --output v.png    # + render
"""
import bpy, sys, os, math, argparse

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

EXTRUDE = 0.06
BEVEL = 0.02
TOL = 1e-4


def build_stamp(wrong_body=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    txt = bpy.data.curves.new("VersionStamp", type='FONT')
    txt.body = "not-a-version" if wrong_body else bpy.app.version_string
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


def bundled_font(name):
    """Load a font Blender ships in datafiles/fonts (both 4.5 LTS and 5.x ship
    Inter.woff2 and DejaVuSansMono.woff2). None if the install lacks it."""
    base = bpy.utils.system_resource('DATAFILES')
    path = os.path.join(base, "fonts", name) if base else ""
    if not os.path.isfile(path):
        return None
    return bpy.data.fonts.load(path, check_existing=True)


def render_still(obj, path, engine):
    scene = bpy.context.scene
    txt = obj.data
    txt.size = 1.0
    txt.space_character = 1.05
    # Render only (the check above asserts the built-in Bfont): Bfont's "1"
    # is a bare stem that reads as a capital I ("5.2.I LTS"). Inter, shipped
    # with Blender, gives the numeral its flag.
    inter = bundled_font("Inter.woff2")
    if inter is None:
        print("ERROR: bundled datafiles/fonts/Inter.woff2 not found", file=sys.stderr)
        return 13
    txt.font = inter

    # polished gold stamp: warm base, low roughness with a faint brushed
    # variation so the long faces carry a gradient instead of a flat slab
    mat = bpy.data.materials.new("Gold")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.95, 0.66, 0.26, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 60.0
    noise.inputs["Detail"].default_value = 4.0
    rmap = nt.nodes.new("ShaderNodeMapRange")
    rmap.inputs["To Min"].default_value = 0.16
    rmap.inputs["To Max"].default_value = 0.30
    nt.links.new(noise.outputs["Fac"], rmap.inputs["Value"])
    nt.links.new(rmap.outputs["Result"], bsdf.inputs["Roughness"])
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
    s = 3.2 / width
    obj.scale = (s, s, s)
    obj.rotation_euler = (math.radians(90), 0.0, 0.0)
    # The stamp stands on a dark plinth, and the caption is set into the
    # plinth's front face. It used to float in the air above the stamp,
    # with a glowing bar along the bottom edge of the frame.
    # A two-tier plinth with 45-degree chamfers: a wide foot, and an upper
    # tier whose front face carries a brushed-steel nameplate with the
    # caption standing proud of it. The gold is reserved for the version; the
    # plinth is dark stone and the plate and caption are steel.
    import bmesh
    foot_h, top_h = 0.12, 0.30
    plinth_h = foot_h + top_h
    top_d = 0.62
    obj.location = (0.0, 0.0, plinth_h + s * height / 2 + 0.01)

    def chamfer_box(name, size, loc, mat, chamfer):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm, size=1.0)
            for v in bm.verts:
                v.co = (v.co.x * size[0], v.co.y * size[1], v.co.z * size[2])
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=chamfer, segments=1,
                            profile=0.5, affect="EDGES", clamp_overlap=True)
            bm.to_mesh(me)
        finally:
            bm.free()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        scene.collection.objects.link(ob)
        return ob

    pmat = bpy.data.materials.new("Stone")
    pmat.use_nodes = True
    pnt = pmat.node_tree
    pb = pnt.nodes["Principled BSDF"]
    pb.inputs["Roughness"].default_value = 0.62
    # honed dark stone: faint mottling, never a flat slot
    pn = pnt.nodes.new("ShaderNodeTexNoise")
    pn.inputs["Scale"].default_value = 9.0
    pn.inputs["Detail"].default_value = 8.0
    pr = pnt.nodes.new("ShaderNodeValToRGB")
    pr.color_ramp.elements[0].color = (0.011, 0.011, 0.013, 1.0)
    pr.color_ramp.elements[1].color = (0.028, 0.027, 0.029, 1.0)
    pnt.links.new(pn.outputs["Fac"], pr.inputs["Fac"])
    pnt.links.new(pr.outputs["Color"], pb.inputs["Base Color"])

    smat = bpy.data.materials.new("Steel")
    smat.use_nodes = True
    snt = smat.node_tree
    sb = snt.nodes["Principled BSDF"]
    sb.inputs["Base Color"].default_value = (0.70, 0.72, 0.76, 1.0)
    sb.inputs["Metallic"].default_value = 1.0
    # brushed along X: noise stretched hard in X drives the roughness
    stc = snt.nodes.new("ShaderNodeTexCoord")
    smap = snt.nodes.new("ShaderNodeMapping")
    smap.inputs["Scale"].default_value = (2.0, 120.0, 120.0)
    sn = snt.nodes.new("ShaderNodeTexNoise")
    sn.inputs["Detail"].default_value = 6.0
    sr = snt.nodes.new("ShaderNodeMapRange")
    sr.inputs["To Min"].default_value = 0.22
    sr.inputs["To Max"].default_value = 0.42
    snt.links.new(stc.outputs["Object"], smap.inputs["Vector"])
    snt.links.new(smap.outputs["Vector"], sn.inputs["Vector"])
    snt.links.new(sn.outputs["Fac"], sr.inputs["Value"])
    snt.links.new(sr.outputs["Result"], sb.inputs["Roughness"])

    foot = chamfer_box("PlinthFoot", (3.62, top_d + 0.20, foot_h), (0.0, 0.0, foot_h / 2),
                       pmat, 0.035)
    top = chamfer_box("PlinthTop", (3.42, top_d, top_h), (0.0, 0.0, foot_h + top_h / 2),
                      pmat, 0.045)
    plate = chamfer_box("Nameplate", (2.2, 0.03, 0.19),
                        (0.0, -top_d / 2 - 0.008, foot_h + top_h / 2), smat, 0.008)

    # dark inked caption on the steel plate, also a TextCurve
    cap = bpy.data.curves.new("Caption", type='FONT')
    cap.body = "B L E N D E R"
    cap.align_x = 'CENTER'; cap.align_y = 'CENTER'
    cap.size = 0.15; cap.extrude = 0.008; cap.bevel_depth = 0.003
    cap.font = inter
    cmat = bpy.data.materials.new("CaptionInk")
    cmat.use_nodes = True
    cb = cmat.node_tree.nodes["Principled BSDF"]
    cb.inputs["Base Color"].default_value = (0.03, 0.03, 0.035, 1.0)
    cb.inputs["Metallic"].default_value = 0.2
    cb.inputs["Roughness"].default_value = 0.35
    cap.materials.append(cmat)
    cap_obj = bpy.data.objects.new("Caption", cap)
    cap_obj.rotation_euler = (math.radians(90), 0.0, 0.0)
    cap_obj.location = (0.0, -top_d / 2 - 0.023 - cap.extrude + 0.002, foot_h + top_h / 2)
    scene.collection.objects.link(cap_obj)
    plinth = [foot, top, plate]

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
    fb.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
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
    light("Key", (-3.2, -4.8, 4.6), 700.0, 6.0, (1.0, 0.95, 0.86), (52, 0, -32))
    light("Fill", (4.6, -3.6, 2.4), 150.0, 8.0, (0.75, 0.84, 1.0), (66, 0, 48))
    light("Rim", (0.8, 4.2, 3.4), 520.0, 3.0, (1.0, 0.75, 0.45), (-65, 0, 170))
    # a broad card behind the camera facing the stamp: the gold's front faces
    # mirror it as a clean gradient instead of the dark studio
    light("Card", (0.9, -8.6, 1.9), 260.0, 4.0, (1.0, 0.9, 0.74), (84, 0, 6))
    # warm wedge raking the back wall (docs/VISUAL-STYLE.md)
    light("Wedge", (2.6, 5.0, 3.8), 260.0, 6.0, (1.0, 0.72, 0.45), (-70, 0, 195))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    # Reframed: the old (0,-8.5,1.15) fixed 86.5° pitch left the stamp at
    # 0.663 fill with a dead lower third; moved in with an aim on the stamp's
    # vertical center so text, caption, and underline bar balance the frame.
    cam.location = (1.15, -5.75, 1.75)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.12, 0.0, 0.66)
    scene.collection.objects.link(aim)
    con = cam.constraints.new('TRACK_TO')
    con.target = aim
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
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
    # AgX would dull the brass toward tan (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact. The hero
    # is the version stamp; caption and plinth count for margins.
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=[obj],
        elements=[obj, cap_obj, *plinth],
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 9
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--wrong-body", action="store_true",
                   help="falsifier: body is not version_string, still assert it is")
    args = p.parse_args(argv)

    obj = build_stamp(wrong_body=args.wrong_body)

    code = check(obj)
    if code:
        return code

    if args.output:
        rcode = render_still(obj, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("text-version-stamp OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
