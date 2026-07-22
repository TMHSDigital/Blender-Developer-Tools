"""Grease Pencil Line Art contours — a runnable example.

Witnesses the Line Art modifier contract AI-generated NPR code most often
gets wrong across the 4.5 LTS → 5.1 window:

1. Contours come from ``modifiers.new(..., 'LINEART')`` on a GPv3 object,
   not from freestyle or hand-drawn strokes.
2. ``source_type='OBJECT'`` + ``source_object`` is load-bearing — clearing
   the source yields zero evaluated strokes.
3. ``use_contour`` must be on for silhouette edges; with contour and crease
   both off the evaluator emits nothing.
4. Stroke width: 4.5 exposes both ``thickness`` (legacy px) and ``radius``;
   5.1 removes ``thickness`` (AttributeError) and keeps ``radius`` only.
5. GPv3 datablock address matches grease-pencil-rosette: ``grease_pencils_v3``
   on 4.5, ``grease_pencils`` on 5.x.

The check evaluates the modifier through the depsgraph (no bake required)
and asserts stroke/point lower bounds against the known failure modes above.

By default it runs the correctness check only. Pass --output to render:

    blender --background --python gp_lineart_contour.py --
    blender --background --python gp_lineart_contour.py -- --output l.png
"""
import bpy, bmesh, sys, os, math, argparse

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
from mathutils import Matrix

# Faceted crystal (octahedron-ish) — enough silhouette edges to read at thumbnail
CRYSTAL_SCALE = 1.15
STROKE_MIN = 1
POINT_MIN = 4
RADIUS = 0.028


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def gp_data_new(name):
    """Version-gated GPv3 datablock creation (same bridge as grease-pencil-rosette)."""
    if bpy.app.version >= (5, 0, 0):
        return bpy.data.grease_pencils.new(name)
    return bpy.data.grease_pencils_v3.new(name)


def check_gp_version_gate():
    if bpy.app.version >= (5, 0, 0):
        if not hasattr(bpy.data, "grease_pencils"):
            print("ERROR: grease_pencils missing on 5.x", file=sys.stderr)
            return 2
        if hasattr(bpy.data, "grease_pencils_v3"):
            print("ERROR: grease_pencils_v3 should be gone on 5.x", file=sys.stderr)
            return 2
        print("5.x contract: grease_pencils is GPv3; _v3 alias gone")
    else:
        if not hasattr(bpy.data, "grease_pencils_v3"):
            print("ERROR: grease_pencils_v3 missing on 4.5", file=sys.stderr)
            return 2
        legacy = bpy.data.grease_pencils.new("LegacyProbe")
        lframe = legacy.layers.new("L").frames.new(1)
        if hasattr(lframe, "drawing") or not hasattr(lframe, "strokes"):
            print("ERROR: 4.5 grease_pencils is not legacy GPencil", file=sys.stderr)
            return 2
        bpy.data.grease_pencils.remove(legacy)
        print("4.5 contract: grease_pencils is legacy; GPv3 lives at _v3")
    return 0


def build_crystal(sc):
    """A designed faceted crystal — not a raw cube."""
    me = bpy.data.meshes.new("Crystal")
    bm = bmesh.new()
    try:
        # Dual cone = octahedron-like crystal
        bmesh.ops.create_cone(
            bm, cap_ends=False, cap_tris=True,
            segments=6, radius1=0.85, radius2=0.0, depth=1.4,
        )
        # second tip downward
        geom = bmesh.ops.duplicate(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces))
        verts = [e for e in geom["geom"] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.rotate(
            bm, verts=verts, cent=(0, 0, 0),
            matrix=Matrix.Rotation(math.pi, 3, "X"),
        )
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bmesh.ops.scale(bm, vec=(CRYSTAL_SCALE,) * 3, verts=bm.verts)
        bm.to_mesh(me)
    finally:
        bm.free()
    for p in me.polygons:
        p.use_smooth = False
    mat = bpy.data.materials.new("CrystalMat")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.12, 0.38, 0.48, 1.0)
    b.inputs["Roughness"].default_value = 0.42
    b.inputs["Metallic"].default_value = 0.2
    emit = b.inputs.get("Emission Color") or b.inputs.get("Emission")
    if emit is not None:
        emit.default_value = (0.05, 0.2, 0.28, 1.0)
        b.inputs["Emission Strength"].default_value = 0.15
    me.materials.append(mat)
    ob = bpy.data.objects.new("Crystal", me)
    ob.location = (0.0, 0.0, 1.15)
    ob.rotation_euler = (math.radians(8), math.radians(12), math.radians(22))
    sc.collection.objects.link(ob)
    return ob


def build_lineart(sc, source):
    gp = gp_data_new("LineArtGP")
    ob = bpy.data.objects.new("LineArt", gp)
    sc.collection.objects.link(ob)

    layer = gp.layers.new("Contours")
    layer.frames.new(1)

    mat = bpy.data.materials.new("NeonContour")
    bpy.data.materials.create_gpencil_data(mat)
    # Neon cyan ink
    gp_set = mat.grease_pencil
    if hasattr(gp_set, "color"):
        gp_set.color = (0.05, 0.95, 1.0, 1.0)
    gp.materials.append(mat)

    mod = ob.modifiers.new("LineArt", "LINEART")
    mod.source_type = "OBJECT"
    mod.source_object = source
    mod.use_contour = True
    mod.use_crease = True
    if hasattr(mod, "use_material"):
        mod.use_material = False
    mod.target_layer = "Contours"
    mod.target_material = mat
    # Width: radius is portable; thickness is 4.5-only
    if hasattr(mod, "thickness"):
        mod.thickness = 45
    mod.radius = RADIUS

    # Disable lights on the GP layer so neon stays vivid
    if hasattr(layer, "use_lights"):
        layer.use_lights = False
    return ob, mod, gp


def setup_camera(sc):
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (3.95, -4.9, 2.62)
    sc.collection.objects.link(cam)
    sc.camera = cam
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 1.15)
    sc.collection.objects.link(aim)
    tr = cam.constraints.new("TRACK_TO")
    tr.target = aim
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    return cam


def eval_stroke_counts(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    eob = ob.evaluated_get(dg)
    layer = eob.data.layers[0]
    frame = layer.frames[0]
    drawing = frame.drawing
    strokes = list(drawing.strokes)
    n_strokes = len(strokes)
    n_points = sum(len(s.points) for s in strokes)
    return n_strokes, n_points


def check_thickness_trap(mod):
    if bpy.app.version >= (5, 0, 0):
        if hasattr(mod, "thickness"):
            print("ERROR: thickness still present on 5.x LINEART", file=sys.stderr)
            return 3
        try:
            _ = mod.thickness
            print("ERROR: thickness read did not raise on 5.x", file=sys.stderr)
            return 3
        except AttributeError:
            pass
        if not hasattr(mod, "radius"):
            print("ERROR: radius missing on 5.x LINEART", file=sys.stderr)
            return 3
        print(f"5.x contract: LINEART.radius={mod.radius} thickness=AttributeError")
    else:
        if not hasattr(mod, "thickness"):
            print("ERROR: thickness missing on 4.5 LINEART", file=sys.stderr)
            return 3
        if not hasattr(mod, "radius"):
            print("ERROR: radius missing on 4.5 LINEART", file=sys.stderr)
            return 3
        print(
            f"4.5 contract: LINEART.thickness={mod.thickness} radius={mod.radius}"
        )
    return 0


def check(sc, source, la_ob, mod):
    code = check_gp_version_gate()
    if code:
        return code
    code = check_thickness_trap(mod)
    if code:
        return code

    if mod.type != "LINEART":
        print(f"ERROR: modifier type {mod.type!r} != 'LINEART'", file=sys.stderr)
        return 4
    if mod.source_type != "OBJECT":
        print(f"ERROR: source_type {mod.source_type!r} != 'OBJECT'", file=sys.stderr)
        return 4
    if mod.source_object != source:
        print("ERROR: source_object round-trip failed", file=sys.stderr)
        return 4
    if not mod.use_contour:
        print("ERROR: use_contour should be True", file=sys.stderr)
        return 4

    # Happy path: contours present
    n_s, n_p = eval_stroke_counts(la_ob)
    if n_s < STROKE_MIN or n_p < POINT_MIN:
        print(
            f"ERROR: evaluated Line Art too thin: strokes={n_s} points={n_p} "
            f"(need >= {STROKE_MIN} strokes, >= {POINT_MIN} points)",
            file=sys.stderr,
        )
        return 5
    print(f"contour_ok strokes={n_s} points={n_p} (gates>={STROKE_MIN},>={POINT_MIN})")

    # Failure mode A: clear source_object → zero strokes
    saved = mod.source_object
    mod.source_object = None
    z_s, z_p = eval_stroke_counts(la_ob)
    mod.source_object = saved
    if z_s != 0 or z_p != 0:
        print(
            f"ERROR: cleared source_object still produced strokes={z_s} points={z_p}",
            file=sys.stderr,
        )
        return 6
    print("nosource_ok strokes=0 points=0")

    # Failure mode B: rebuild modifier with contour+crease off → zero strokes
    while la_ob.modifiers:
        la_ob.modifiers.remove(la_ob.modifiers[0])
    mod_off = la_ob.modifiers.new("LineArtOff", "LINEART")
    mod_off.source_type = "OBJECT"
    mod_off.source_object = source
    mod_off.use_contour = False
    mod_off.use_crease = False
    if hasattr(mod_off, "use_loose"):
        mod_off.use_loose = False
    if hasattr(mod_off, "use_intersection"):
        mod_off.use_intersection = False
    if hasattr(mod_off, "use_material"):
        mod_off.use_material = False
    if hasattr(mod_off, "use_edge_mark"):
        mod_off.use_edge_mark = False
    mod_off.target_layer = "Contours"
    gp_mat = la_ob.data.materials[0]
    mod_off.target_material = gp_mat
    mod_off.radius = RADIUS
    z_s, z_p = eval_stroke_counts(la_ob)
    if z_s != 0 or z_p != 0:
        print(
            f"ERROR: contour+crease off still produced strokes={z_s} points={z_p}",
            file=sys.stderr,
        )
        return 7
    print("noflags_ok strokes=0 points=0")

    # Restore working Line Art modifier for optional still
    while la_ob.modifiers:
        la_ob.modifiers.remove(la_ob.modifiers[0])
    mod_on = la_ob.modifiers.new("LineArt", "LINEART")
    mod_on.source_type = "OBJECT"
    mod_on.source_object = source
    mod_on.use_contour = True
    mod_on.use_crease = True
    mod_on.target_layer = "Contours"
    mod_on.target_material = gp_mat
    if hasattr(mod_on, "thickness"):
        mod_on.thickness = 45
    mod_on.radius = RADIUS
    n_s2, n_p2 = eval_stroke_counts(la_ob)
    if n_s2 < STROKE_MIN or n_p2 < POINT_MIN:
        print(
            f"ERROR: contours did not recover after restore: "
            f"strokes={n_s2} points={n_p2}",
            file=sys.stderr,
        )
        return 7
    print(
        f"restored_ok strokes={n_s2} points={n_p2} radius={mod_on.radius}"
    )
    return 0


def build_studio(sc):
    # Default-stage-ish dark floor + wall — Line Art neon is the proof
    def plane(name, size, loc, rot):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size)
            bm.to_mesh(me)
        finally:
            bm.free()
        mat = bpy.data.materials.new(name + "M")
        mat.use_nodes = True
        b = mat.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)
        b.inputs["Roughness"].default_value = 0.7
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        ob.rotation_euler = rot
        sc.collection.objects.link(ob)
        return ob

    plane("Floor", 30.0, (0, 0, 0), (0, 0, 0))
    plane("Wall", 30.0, (0, 9, 0), (math.radians(90), 0, 0))

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02, 0.021, 0.025, 1.0,
    )
    sc.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        sc.collection.objects.link(ob)

    light("Key", (-4, -5, 6), 420.0, 5.0, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5, -3.5, 2.5), 90.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Wedge", (2.5, 5.5, 4.0), 280.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))


def render_still(sc, path, engine):
    sc.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        sc.cycles.device = "CPU"
        sc.cycles.samples = 64
        sc.cycles.use_denoising = True
    else:
        try:
            sc.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    sc.view_settings.view_transform = "Standard"
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact. The two
    # renderable subjects are the crystal source mesh and the GP stroke object.
    stage = [o for o in sc.objects if o.name in {"Floor", "Wall"}]
    hero = [
        o for o in sc.objects
        if o.type in {"MESH", "GREASEPENCIL"} and o not in stage
    ]
    fcode = gallery_framing.check_framing(
        sc, sc.camera,
        hero=hero,
        elements=hero,
        stage=stage,
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 8
    return 0


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    build_studio(sc)
    crystal = build_crystal(sc)
    la_ob, mod, gp = build_lineart(sc, crystal)
    setup_camera(sc)
    return sc, crystal, la_ob, mod


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine",
        default="eevee",
        choices=("eevee", "cycles"),
        help="render engine for --output",
    )
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    sc, crystal, la_ob, mod = build_scene()
    code = check(sc, crystal, la_ob, mod)
    if code:
        return code

    if args.output:
        rcode = render_still(sc, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("gp-lineart-contour OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
