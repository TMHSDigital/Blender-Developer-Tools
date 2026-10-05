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
from mathutils import Matrix, Vector

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


# Gallery subject: a turned goblet whose coarse lathe cage (GOBLET_SEGS
# around) carries the same SUBSURF split as the check's cube. The render path
# exports it twice through the same exporter call the check proves, then
# re-imports both USDA files — the still shows the files, not the modifier.
GOBLET_SEGS = 8
# The goblet widens the gap the check proves on the cube (levels 1 vs 2): an
# 8-sided cage at viewport level 0 against render level 3, so the difference
# between the two files reads at thumbnail size.
GOBLET_VP = 0
GOBLET_RD = 3
GOBLET_PROFILE = [            # (r, z) bottom -> rim outside -> rim inside -> well
    (0.0, 0.0), (0.62, 0.0), (0.66, 0.06), (0.52, 0.14), (0.20, 0.26),
    (0.14, 0.52), (0.24, 0.64), (0.13, 0.76), (0.15, 1.02), (0.46, 1.16),
    (0.72, 1.46), (0.80, 1.86), (0.84, 2.14), (0.78, 2.16),
    (0.72, 1.88), (0.62, 1.52), (0.40, 1.30), (0.0, 1.24),
]


def build_goblet():
    me = bpy.data.meshes.new("Goblet")
    bm = bmesh.new()
    try:
        rings = []
        for r, z in GOBLET_PROFILE:
            if r == 0.0:
                rings.append([bm.verts.new((0.0, 0.0, z))])
            else:
                rings.append([bm.verts.new((r * math.cos(2 * math.pi * s / GOBLET_SEGS),
                                            r * math.sin(2 * math.pi * s / GOBLET_SEGS), z))
                              for s in range(GOBLET_SEGS)])
        for a, b in zip(rings, rings[1:]):
            for s in range(GOBLET_SEGS):
                t = (s + 1) % GOBLET_SEGS
                if len(a) == 1:
                    bm.faces.new((a[0], b[t], b[s]))
                elif len(b) == 1:
                    bm.faces.new((a[s], a[t], b[0]))
                else:
                    bm.faces.new((a[s], a[t], b[t], b[s]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    ob = bpy.data.objects.new("Goblet", me)
    bpy.context.collection.objects.link(ob)
    mod = ob.modifiers.new("Subsurf", "SUBSURF")
    mod.levels = GOBLET_VP
    mod.render_levels = GOBLET_RD
    return ob


def label_font():
    """DejaVu Sans Mono ships in datafiles/fonts on 4.5 and 5.2, and its 1 never
    reads as I. (Inter ships too, but it is a variable font whose overlapping
    contours render with holes on 4.5.)"""
    # system_resource resolves directories only; a file path returns ''
    fonts = bpy.utils.system_resource("DATAFILES", path="fonts")
    path = os.path.join(fonts, "DejaVuSansMono.woff2") if fonts else ""
    if path and os.path.exists(path):
        try:
            return bpy.data.fonts.load(path, check_existing=True)
        except RuntimeError:
            pass
    return None


def import_usda(path):
    before = set(bpy.data.objects)
    if bpy.ops.wm.usd_import(filepath=path) != {"FINISHED"}:
        raise RuntimeError(f"usd_import failed for {path}")
    meshes = [o for o in set(bpy.data.objects) - before if o.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"expected one mesh from {path}, got {len(meshes)}")
    ob = meshes[0]
    # bake whatever Xform chain the importer built into the mesh, so staging
    # below starts from identity like any other prop
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.data.transform(mw)
    ob.matrix_world = Matrix.Identity(4)
    return ob


def text_plate(name, lines, loc, mat_plate, mat_ink, scene):
    """A bevelled brass plate leaning back on the floor with engraved text."""
    pme = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 1.7
            v.co.y *= 0.06
            v.co.z *= 0.52
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.015, segments=2,
                        affect="EDGES", clamp_overlap=True)
        bm.to_mesh(pme)
    finally:
        bm.free()
    pme.materials.append(mat_plate)
    plate = bpy.data.objects.new(name, pme)
    plate.location = loc
    plate.rotation_euler = (math.radians(-14), 0.0, 0.0)
    scene.collection.objects.link(plate)
    objs = [plate]
    for i, (body, size) in enumerate(lines):
        cu = bpy.data.curves.new(f"{name}.T{i}", "FONT")
        cu.body = body
        cu.size = size
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.extrude = 0.004
        cu.materials.append(mat_ink)
        font = label_font()
        if font is not None:
            cu.font = font
        t = bpy.data.objects.new(f"{name}.T{i}", cu)
        t.parent = plate
        t.location = (0.0, -0.065, 0.10 if i == 0 else -0.14)
        t.rotation_euler = (math.radians(90), 0.0, 0.0)
        scene.collection.objects.link(t)
        objs.append(t)
    return objs


def render_still(obj, path, engine):
    """Left: the VIEWPORT USDA re-imported. Right: the RENDER USDA re-imported."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    goblet = build_goblet()
    out_dir = tempfile.mkdtemp(prefix="bdt_usd_goblet_")
    p_vp = os.path.join(out_dir, "goblet_viewport.usda")
    p_rd = os.path.join(out_dir, "goblet_render.usda")
    export_usda(p_vp, "VIEWPORT", "TESSELLATE")
    export_usda(p_rd, "RENDER", "TESSELLATE")
    bpy.data.objects.remove(goblet)
    left = import_usda(p_vp)
    right = import_usda(p_rd)
    n_vp, n_rd = len(left.data.vertices), len(right.data.vertices)
    print(f"goblet usda points viewport={n_vp} render={n_rd}")
    if n_rd <= n_vp:
        print("ERROR: re-imported RENDER goblet is not denser than VIEWPORT", file=sys.stderr)
        return 6

    pewter = principled("Brass", (0.92, 0.64, 0.30, 1.0), 1.0, 0.30)
    stone = principled("Plinth", (0.06, 0.062, 0.07, 1.0), 0.0, 0.34)
    plate_mat = principled("Plate", (0.035, 0.036, 0.04, 1.0), 0.7, 0.42)
    ink = principled("Inlay", (0.95, 0.70, 0.36, 1.0), 1.0, 0.32)

    # turned plinths: a stepped drum per goblet, the goblet seated on top
    PLINTH_H = 0.62
    plinths = []
    for x in (-1.75, 1.75):
        me = bpy.data.meshes.new("Plinth")
        bm = bmesh.new()
        try:
            prof = [(0.0, 0.0), (1.12, 0.0), (1.16, 0.04), (1.16, 0.16), (1.10, 0.20),
                    (1.02, 0.22), (1.02, PLINTH_H - 0.06), (1.06, PLINTH_H - 0.03),
                    (1.06, PLINTH_H), (0.0, PLINTH_H)]
            rings = []
            for r, z in prof:
                rings.append([bm.verts.new((0.0, 0.0, z))] if r == 0.0 else
                             [bm.verts.new((r * math.cos(2 * math.pi * s / 64),
                                            r * math.sin(2 * math.pi * s / 64), z))
                              for s in range(64)])
            for a, b in zip(rings, rings[1:]):
                for s in range(64):
                    t = (s + 1) % 64
                    if len(a) == 1:
                        f = bm.faces.new((a[0], b[t], b[s]))
                    elif len(b) == 1:
                        f = bm.faces.new((a[s], a[t], b[0]))
                    else:
                        f = bm.faces.new((a[s], a[t], b[t], b[s]))
                    f.smooth = True
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
        finally:
            bm.free()
        me.set_sharp_from_angle(angle=math.radians(40.0))
        me.materials.append(stone)
        pl = bpy.data.objects.new("Plinth", me)
        pl.location = (x, 0.0, 0.0)
        scene.collection.objects.link(pl)
        plinths.append(pl)

    # Both goblets are shaded identically (flat) — the only difference in the
    # picture is the geometry each USDA file carries.
    for ob, x in ((left, -1.75), (right, 1.75)):
        ob.data.materials.clear()
        ob.data.materials.append(pewter)
        ob.data.polygons.foreach_set("use_smooth", [False] * len(ob.data.polygons))
        ob.location = (x, 0.0, 0.0)
        ob.rotation_euler = (0.0, 0.0, math.radians(11.25))
        ob.scale = (1.0, 1.0, 1.0)
    # Subdivision pulls the surface inside the cage by a level-dependent
    # amount, so each goblet is seated on its plinth from its own verts.
    bpy.context.view_layer.update()
    for ob in (left, right):
        zmin = min((ob.matrix_world @ v.co).z for v in ob.data.vertices)
        ob.location.z += PLINTH_H - zmin

    labels = []
    labels += text_plate("PlacardVP", [("VIEWPORT", 0.30), (f"{n_vp} points", 0.17)],
                         (-1.75, -1.45, 0.30), plate_mat, ink, scene)
    labels += text_plate("PlacardRD", [("RENDER", 0.30), (f"{n_rd} points", 0.17)],
                         (1.75, -1.45, 0.30), plate_mat, ink, scene)

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

    light("Key", (-4.0, -5.0, 6.0), 520.0, 3.5, (1.0, 0.95, 0.88), (46, 0, -35))
    light("Fill", (5.0, -3.5, 3.0), 90.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.0, 4.0, 5.5), 260.0, 4.0, (0.62, 0.78, 1.0), (-42, 0, 180))
    light("Wedge", (2.5, 5.5, 4.0), 520.0, 6.0, (1.0, 0.72, 0.45), (-68, 0, 190))
    # a broad warm card low and front-left: polished brass mirrors its
    # surroundings, and on a near-black stage it otherwise reads olive-dark.
    # The card's reflection is also what draws each facet on the viewport cup.
    light("Card", (-3.2, -4.2, 2.0), 380.0, 5.0, (1.0, 0.82, 0.6), (72, 0, -38))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 1.25)
    aim.hide_render = True
    scene.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.05, -10.6, 3.7)
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
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    scene.view_settings.view_transform = "Standard"

    fcode = gallery_framing.check_framing(
        scene, cam, hero=[left, right] + plinths, elements=[left, right] + plinths + labels,
        stage=[floor, wall],
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
