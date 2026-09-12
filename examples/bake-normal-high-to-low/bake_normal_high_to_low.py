"""High-to-low tangent normal bake — a runnable example.

Witnesses transferring high-poly surface detail onto a collapse-decimated LOD
via Cycles cage bake. Pixel buffers are stochastic: this example does **not**
assert byte-identity across 4.5 / 5.1 / 5.2. The contract is statistical.

1. A bake from a ribbed hatch plate produces a map whose pixels deviate
   from flat tangent-space ``(0.5, 0.5, 1.0)`` above a stated fraction and MAD.
2. The same bake from an undisplaced source does not.
3. ``--flat-source`` skips the ribs and rivets and still runs the *detail* gates, so the
   assertion fails. That is the falsifier (``--same-axis`` in export-preset-axis).

Operator RNA is ``type='NORMAL'``, not ``bake_type``. Identifiers match on
4.5.11, 5.1.2, and 5.2.1 — no shim.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python bake_normal_high_to_low.py --
    blender --background --python bake_normal_high_to_low.py -- --flat-source
    blender --background --python bake_normal_high_to_low.py -- --output p.png
"""
import argparse
import math
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True
import gallery_framing

BAKE_RES = 256
CAGE_EXTRUSION = 0.20
MARGIN = 16
THRESH = 0.04
DETAIL_FRAC_MIN = 0.40
DETAIL_MAD_MIN = 0.05
FLAT_FRAC_MAX = 0.05
FLAT_MAD_MAX = 0.03
MONO_FRAC_GAP = 0.30
GRID_SEGS = 40
HATCH_SIZE = 1.15
THICKNESS = 0.12
RIB_AMP = 0.10
RIVET_AMP = 0.05
TARGET_TRIS = 900
FLAT_RGB = (0.5, 0.5, 1.0)


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def duplicate_object(obj, name):
    dup = obj.copy()
    dup.data = obj.data.copy()
    dup.name = name
    bpy.context.scene.collection.objects.link(dup)
    return dup


def make_hatch(name):
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(
            bm, x_segments=GRID_SEGS, y_segments=GRID_SEGS, size=HATCH_SIZE
        )
        uv = bm.loops.layers.uv.new("UVMap")
        span = 2.0 * HATCH_SIZE
        for face in bm.faces:
            face.smooth = True
            for loop in face.loops:
                loop[uv].uv = (
                    (loop.vert.co.x + HATCH_SIZE) / span,
                    (loop.vert.co.y + HATCH_SIZE) / span,
                )
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def displace_hatch(obj):
    me = obj.data
    n = len(me.vertices)
    buf = [0.0] * (n * 3)
    me.vertices.foreach_get("co", buf)
    for i in range(n):
        x, y, z = buf[i * 3], buf[i * 3 + 1], buf[i * 3 + 2]
        rad = math.sqrt(x * x + y * y)
        theta = math.atan2(y, x)
        falloff = max(0.0, 1.0 - rad / HATCH_SIZE)
        rib = RIB_AMP * math.cos(6.0 * theta) * falloff
        rivet = 0.0
        for k in range(8):
            ang = k * math.pi / 4.0
            px = 0.70 * HATCH_SIZE * math.cos(ang)
            py = 0.70 * HATCH_SIZE * math.sin(ang)
            d2 = (x - px) ** 2 + (y - py) ** 2
            rivet += RIVET_AMP * math.exp(-d2 / 0.010)
        rim = 0.025 * math.exp(-((rad - 0.92 * HATCH_SIZE) ** 2) / 0.008)
        buf[i * 3 + 2] = z + rib + rivet + rim
    me.vertices.foreach_set("co", buf)
    me.update()


def evaluated_triangle_count(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        eval_mesh.calc_loop_triangles()
        return len(eval_mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()


def decimate_apply(obj, target_tris):
    current = evaluated_triangle_count(obj)
    if current == 0 or current <= target_tris:
        return current, current
    ratio = min(1.0, target_tris / current)
    mod = obj.modifiers.new("DecimateBudget", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = ratio
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    with bpy.context.temp_override(
        object=obj, active_object=obj, selected_objects=[obj]
    ):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.update()
    return current, evaluated_triangle_count(obj)


def setup_bake_target(obj, name, size=BAKE_RES):
    if not obj.data.uv_layers:
        return None, None, None
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    mat = bpy.data.materials.new(name + "Mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    nodes.active = tex
    tex.select = True
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return img, mat, tex


def configure_cycles_cpu():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False


def isolate_select(high, low):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    high.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low


def bake_normal(high, low):
    configure_cycles_cpu()
    isolate_select(high, low)
    return bpy.ops.object.bake(
        type="NORMAL",
        use_selected_to_active=True,
        cage_extrusion=CAGE_EXTRUSION,
        use_cage=False,
        normal_space="TANGENT",
        margin=MARGIN,
        margin_type="ADJACENT_FACES",
        use_clear=True,
        target="IMAGE_TEXTURES",
    )


def map_stats(image, thresh=THRESH):
    width, height = image.size
    n = width * height
    buf = [0.0] * (n * 4)
    image.pixels.foreach_get(buf)
    deviant = 0
    mad_acc = 0.0
    fr, fg, fb = FLAT_RGB
    for i in range(n):
        r, g, b = buf[i * 4], buf[i * 4 + 1], buf[i * 4 + 2]
        d = math.sqrt((r - fr) ** 2 + (g - fg) ** 2 + (b - fb) ** 2)
        mad_acc += d
        if d > thresh:
            deviant += 1
    return deviant / n, mad_acc / n


def paint_principled(mat, color, metallic, roughness):
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return bsdf


def wire_normal_map(mat, tex):
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = paint_principled(mat, (0.22, 0.13, 0.07, 1.0), 0.58, 0.44)
    nrm = nodes.new("ShaderNodeNormalMap")
    nrm.space = "TANGENT"
    links.new(tex.outputs["Color"], nrm.inputs["Color"])
    links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])


def new_image(name, size=BAKE_RES):
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    return img


def check(flat_source):
    base = make_hatch("BakeBase")
    if not base.data.uv_layers:
        return fail("base mesh has no UV layer", 3), None, None, None, None

    low = duplicate_object(base, "BakeLow")
    before, after = decimate_apply(low, TARGET_TRIS)
    print(f"lod_tris before={before} after={after} target={TARGET_TRIS}")
    if not low.data.uv_layers:
        return fail("decimated LOD lost its UV layer", 3), None, None, None, None

    high_detail = duplicate_object(base, "BakeHigh")
    if not flat_source:
        displace_hatch(high_detail)

    img_detail, mat, tex = setup_bake_target(low, "BakeNrmDetail")
    if img_detail is None:
        return fail("low mesh has no UV layer", 3), None, None, None, None

    result = bake_normal(high_detail, low)
    if result != {"FINISHED"}:
        return fail(f"detail bake returned {result}", 4), None, None, None, None
    if not img_detail.has_data:
        return fail("detail bake image has_data is False", 4), None, None, None, None

    detail_frac, detail_mad = map_stats(img_detail)
    src_label = "flat-source" if flat_source else "detail"
    print(
        f"bake_stats source={src_label} frac={detail_frac:.4f} mad={detail_mad:.5f} "
        f"thresh={THRESH} flat_rgb={FLAT_RGB}"
    )

    if detail_frac < DETAIL_FRAC_MIN:
        return (
            fail(
                f"detail frac {detail_frac:.4f} < {DETAIL_FRAC_MIN} "
                "(map is too close to flat tangent; --flat-source is the "
                "designed fail for this gate)",
                5,
            ),
            None,
            None,
            None,
            None,
        )
    if detail_mad < DETAIL_MAD_MIN:
        return (
            fail(
                f"detail MAD {detail_mad:.5f} < {DETAIL_MAD_MIN}",
                6,
            ),
            None,
            None,
            None,
            None,
        )

    if flat_source:
        return 0, high_detail, low, img_detail, mat

    img_flat = new_image("BakeNrmFlat")
    tex.image = img_flat
    mat.node_tree.nodes.active = tex
    result = bake_normal(base, low)
    if result != {"FINISHED"}:
        return fail(f"flat bake returned {result}", 4), None, None, None, None
    if not img_flat.has_data:
        return fail("flat bake image has_data is False", 4), None, None, None, None

    flat_frac, flat_mad = map_stats(img_flat)
    print(
        f"bake_stats source=flat frac={flat_frac:.4f} mad={flat_mad:.5f} "
        f"thresh={THRESH}"
    )

    if flat_frac > FLAT_FRAC_MAX or flat_mad > FLAT_MAD_MAX:
        return (
            fail(
                f"flat control not flat frac={flat_frac:.4f} "
                f"(max {FLAT_FRAC_MAX}) mad={flat_mad:.5f} (max {FLAT_MAD_MAX})",
                7,
            ),
            None,
            None,
            None,
            None,
        )
    if detail_frac - flat_frac < MONO_FRAC_GAP:
        return (
            fail(
                f"monotonic gap {detail_frac - flat_frac:.4f} < {MONO_FRAC_GAP} "
                f"(detail={detail_frac:.4f} flat={flat_frac:.4f})",
                8,
            ),
            None,
            None,
            None,
            None,
        )

    tex.image = img_detail
    mat.node_tree.nodes.active = tex
    return 0, high_detail, low, img_detail, mat


def make_map_card(image, name="BakeCard"):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.05)
        for vert in bm.verts:
            vert.co.x, vert.co.y, vert.co.z = vert.co.x, 0.0, vert.co.y
        uv = bm.loops.layers.uv.new("UVMap")
        for face in bm.faces:
            for loop in face.loops:
                loop[uv].uv = (
                    (loop.vert.co.x + 1.05) / 2.10,
                    (loop.vert.co.z + 1.05) / 2.10,
                )
        bm.to_mesh(me)
    finally:
        bm.free()
    mat = bpy.data.materials.new(name + "Mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 1.0
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(tex.outputs["Color"], emit.inputs["Color"])
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def render_still(low, mat, tex, path, engine):
    scene = bpy.context.scene
    for ob in list(scene.objects):
        if ob.type == "MESH" and ob != low:
            ob.hide_render = True
            ob.hide_viewport = True

    wire_normal_map(mat, tex)
    solid = low.modifiers.new("SolidifyDisplay", "SOLIDIFY")
    solid.thickness = THICKNESS
    solid.offset = 1.0
    low.rotation_euler.x = math.radians(72.0)
    low.location = (1.20, 0.0, 1.05)
    card = make_map_card(tex.image)
    card.location = (-1.50, 0.0, 1.05)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=12.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = bpy.data.materials.new("Floor")
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
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02,
        0.021,
        0.025,
        1.0,
    )
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

    light("Key", (-4.0, -5.0, 6.0), 600.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 110.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.5, 4.5, 5.0), 350.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 175))
    light("Wedge", (2.5, 3.5, 4.2), 480.0, 6.0, (1.0, 0.76, 0.5), (-72, 0, 195))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -8.4, 3.15)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 1.05)
    scene.collection.objects.link(aim)
    con = cam.constraints.new("TRACK_TO")
    con.target = aim
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    scene.camera = cam

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 32
        scene.cycles.device = "CPU"
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
        scene,
        cam,
        hero=[card, low],
        elements=[card, low],
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return fail("render produced no file", 9)
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine",
        default="eevee",
        choices=("eevee", "cycles"),
        help="render engine for --output (cycles for GPU-less hosts)",
    )
    p.add_argument(
        "--flat-source",
        action="store_true",
        help="bake from undisplaced high; detail gates must fail",
    )
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    code, high, low, img, mat = check(args.flat_source)
    if code:
        return code

    if args.output:
        tex = next(
            n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image == img
        )
        rcode = render_still(low, mat, tex, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("bake-normal-high-to-low OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
