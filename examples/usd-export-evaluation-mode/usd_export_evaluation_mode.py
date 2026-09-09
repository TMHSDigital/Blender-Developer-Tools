"""USD evaluation_mode — a runnable example.

Witnesses ``bpy.ops.wm.usd_export`` ``evaluation_mode='RENDER'`` against
``VIEWPORT``, which the snippet names but does not prove. A SUBSURF cube
with ``levels=1`` / ``render_levels=2`` is tessellated into USDA:

* Catmull-Clark on a cube is closed form: verts = 2 + 6 × 4^n
  (n=1 → 26, n=2 → 98). TESSELLATE + VIEWPORT must write 26 points;
  TESSELLATE + RENDER must write 98.
* Default ``export_subdivision='BEST_MATCH'`` writes the 8-vert cage plus
  ``subdivisionScheme = catmullClark``. evaluation_mode is then silent —
  both files are the cage. TESSELLATE is what makes the mode observable.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python usd_export_evaluation_mode.py --
    blender --background --python usd_export_evaluation_mode.py -- --output u.png
"""
import bpy, bmesh, sys, os, math, argparse, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True
import gallery_framing

LEVEL_VP = 1
LEVEL_RD = 2


def cube_cc_verts(level):
    """Catmull-Clark vertex count for a cube after `level` subdivisions."""
    return 2 + 6 * (4 ** level)


def cube_cc_faces(level):
    return 6 * (4 ** level)


def usda_array_body(text, needle):
    """Return the contents of `needle = [ ... ]`, skipping the type's `[]`."""
    key = needle + " = ["
    i = text.find(key)
    if i < 0:
        return None
    i += len(key)
    depth = 1
    j = i
    while j < len(text) and depth:
        if text[j] == "[":
            depth += 1
        elif text[j] == "]":
            depth -= 1
        j += 1
    return text[i:j - 1]


def usda_point_count(text):
    body = usda_array_body(text, "point3f[] points")
    if body is None:
        return 0
    return body.count("(")


def usda_face_count(text):
    body = usda_array_body(text, "int[] faceVertexCounts")
    if body is None:
        return 0
    return body.count(",") + (1 if body.strip() else 0)


def usda_scheme(text):
    key = 'uniform token subdivisionScheme = "'
    i = text.find(key)
    if i < 0:
        return None
    i += len(key)
    return text[i:text.find('"', i)]


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("Ingot")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new("Ingot", me)
    bpy.context.collection.objects.link(obj)
    mod = obj.modifiers.new("Subsurf", "SUBSURF")
    mod.levels = LEVEL_VP
    mod.render_levels = LEVEL_RD
    return obj, mod


def export_usda(path, evaluation_mode, export_subdivision):
    if os.path.exists(path):
        os.remove(path)
    rna = bpy.ops.wm.usd_export.get_rna_type()
    have = {p.identifier for p in rna.properties}
    for key in ("filepath", "evaluation_mode", "export_subdivision"):
        if key not in have:
            raise RuntimeError(f"wm.usd_export missing RNA property {key}")
    result = bpy.ops.wm.usd_export(
        filepath=path,
        evaluation_mode=evaluation_mode,
        export_subdivision=export_subdivision,
        selected_objects_only=False,
        export_animation=False,
        export_hair=False,
        export_materials=False,
    )
    if result != {"FINISHED"}:
        raise RuntimeError(f"usd_export {result} for {path}")
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        raise RuntimeError(f"no USDA written to {path}")
    return open(path, encoding="utf-8").read()


def check(obj, mod, out_dir, force_mode=None, force_subdiv=None):
    expect_vp = cube_cc_verts(LEVEL_VP)
    expect_rd = cube_cc_verts(LEVEL_RD)
    expect_f_vp = cube_cc_faces(LEVEL_VP)
    expect_f_rd = cube_cc_faces(LEVEL_RD)
    base = len(obj.data.vertices)
    if base != 8:
        print(f"ERROR: base cube verts {base} != 8", file=sys.stderr)
        return 2

    mode = force_mode or "RENDER"
    subdiv = force_subdiv or "TESSELLATE"
    path_rd = os.path.join(out_dir, "render.usda")
    path_vp = os.path.join(out_dir, "viewport.usda")
    path_cage = os.path.join(out_dir, "cage.usda")

    text_rd = export_usda(path_rd, mode, subdiv)
    text_vp = export_usda(path_vp, "VIEWPORT", "TESSELLATE")
    text_cage = export_usda(path_cage, "RENDER", "BEST_MATCH")

    pts_rd = usda_point_count(text_rd)
    pts_vp = usda_point_count(text_vp)
    pts_cage = usda_point_count(text_cage)
    faces_rd = usda_face_count(text_rd)
    faces_vp = usda_face_count(text_vp)
    scheme_rd = usda_scheme(text_rd)
    scheme_cage = usda_scheme(text_cage)

    print(
        f"base={base} usda_vp={pts_vp}/{faces_vp} usda_rd={pts_rd}/{faces_rd} "
        f"usda_cage={pts_cage} scheme_rd={scheme_rd} scheme_cage={scheme_cage} "
        f"mode={mode} subdiv={subdiv}"
    )
    print(
        f"closed_form vp_verts={expect_vp} rd_verts={expect_rd} "
        f"vp_faces={expect_f_vp} rd_faces={expect_f_rd}"
    )

    if pts_vp != expect_vp or faces_vp != expect_f_vp:
        print(
            f"ERROR: VIEWPORT TESSELLATE wrote {pts_vp} points / {faces_vp} faces, "
            f"expected {expect_vp}/{expect_f_vp}",
            file=sys.stderr,
        )
        return 3
    if pts_rd != expect_rd or faces_rd != expect_f_rd or scheme_rd != "none":
        print(
            f"ERROR: RENDER TESSELLATE wrote {pts_rd} points / {faces_rd} faces "
            f"scheme={scheme_rd}, expected {expect_rd}/{expect_f_rd} scheme=none "
            "(VIEWPORT quality or BEST_MATCH cage would not match)",
            file=sys.stderr,
        )
        return 4
    if pts_cage != base or scheme_cage != "catmullClark":
        print(
            f"ERROR: BEST_MATCH should write the cage ({base} points, catmullClark), "
            f"got {pts_cage} scheme={scheme_cage}",
            file=sys.stderr,
        )
        return 5
    if pts_rd == pts_vp:
        print("ERROR: RENDER and VIEWPORT USDA point counts are identical", file=sys.stderr)
        return 6
    return 0


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def principled(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def render_still(obj, path, engine):
    """Left: viewport tessellation (levels=1). Right: render tessellation (levels=2)."""
    scene = bpy.context.scene
    steel = principled("Steel", (0.55, 0.57, 0.60, 1.0), 1.0, 0.58)

    left = obj
    left.location = (-1.55, 0.0, 1.0)
    left.rotation_euler = (0.0, 0.0, math.radians(28))
    left.data.materials.append(steel)
    left.modifiers["Subsurf"].levels = LEVEL_VP
    for poly in left.data.polygons:
        poly.use_smooth = False

    right_me = left.data.copy()
    right = bpy.data.objects.new("IngotRender", right_me)
    right.location = (1.55, 0.0, 1.0)
    right.rotation_euler = (0.0, 0.0, math.radians(28))
    right.data.materials.append(steel)
    bpy.context.collection.objects.link(right)
    rm = right.modifiers.new("Subsurf", "SUBSURF")
    rm.levels = LEVEL_RD
    rm.render_levels = LEVEL_RD
    for poly in right.data.polygons:
        poly.use_smooth = True

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    floor_me.materials.append(principled("Studio", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7))
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.data.materials.clear()
    wall.data.materials.append(principled("Wall", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7))
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.pi / 2, 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", (-4.0, -5.0, 6.0), 200.0, 7.0, (1.0, 0.96, 0.9), (46, 0, -35))
    light("Fill", (5.0, -3.5, 3.0), 180.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Wedge", (2.5, 5.5, 4.0), 360.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 1.0)
    aim.hide_render = True
    scene.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (4.16, -5.85, 3.00)
    scene.collection.objects.link(cam)
    scene.camera = cam
    track = cam.constraints.new("TRACK_TO")
    track.target = aim
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 32
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(
        scene, cam, hero=[left, right], elements=[left, right], stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 12
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument(
        "--evaluation-mode", default="RENDER", choices=("RENDER", "VIEWPORT"),
        help="falsification: VIEWPORT fails the RENDER closed form",
    )
    p.add_argument(
        "--subdivision", default="TESSELLATE",
        choices=("TESSELLATE", "BEST_MATCH", "IGNORE"),
        help="falsification: BEST_MATCH writes the cage",
    )
    args = p.parse_args(argv)

    obj, mod = build()
    out_dir = tempfile.mkdtemp(prefix="bdt_usd_")
    code = check(
        obj, mod, out_dir,
        force_mode=args.evaluation_mode, force_subdiv=args.subdivision,
    )
    if code:
        return code

    if args.output:
        rcode = render_still(obj, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("usd-export-evaluation-mode OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
