"""PNG vs EXR alpha round-trip — a runnable example.

Witnesses that a `float_buffer=True` image saved via `Image.save()` to PNG
is written as **16-bit RGBA** and, critically, is **unpremultiplied as if
the buffer were associated-alpha** before storage. The normal `pixels` API
authors *straight* RGBA, so any channel where `c > a` blows up past 1.0 and
clamps to white on save — closed-form error reaches ~0.98 for authored
RGB≈0.02 at alpha 1/255. The same buffer saved as OpenEXR round-trips at
float precision. A byte image (`float_buffer=False`) writes **8-bit** PNG
with straight alpha and only pays ordinary quantization.

AI-generated Blender code commonly trusts `Image.save()` to PNG for float
RGBA scratch buffers (masks, ID mattes, AOVs). Pass --output to also render
a staged still of two framed verification displays: left is the PNG-mangled
reload, right is the EXR-clean reload.

    blender --background --python png_exr_alpha.py --
    blender --background --python png_exr_alpha.py -- --output alpha.png
"""
import bpy
import bmesh
import sys
import os
import math
import argparse
import tempfile
import struct

# Columns = alphas, rows = authored RGB triples chosen to stress the trap.
ALPHAS = [i / 255.0 for i in (1, 2, 8, 16, 32, 64, 128, 255)]
COLORS = [
    (0.02, 0.02, 0.02),  # ~0.98 err at a=1/255 after false unpremul+clamp
    (0.5, 0.5, 0.5),     # clamps to white for every a < 0.5
    (0.25, 0.25, 0.25),
    (1.0, 1.0, 1.0),     # survives (already at the clamp ceiling)
    (1.0, 0.0, 0.0),     # chromatic primary — survives visually
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
    (0.0, 1.0, 1.0),
]
W = len(ALPHAS)
H = len(COLORS)

PNG_ERR_FLOOR = 0.90          # float→PNG must hurt at least this much
PNG_MODEL_TOL = 2.0 / 65535.0 + 1e-6
BYTE_TOL = 0.5 / 255.0 + 1e-6
EXR_TOL = 1e-5


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def q16(x):
    """Quantize to 16-bit the way Blender's float→PNG writer does (half up)."""
    return int(max(0.0, min(1.0, x)) * 65535.0 + 0.5) / 65535.0


def q8(x):
    return int(max(0.0, min(1.0, x)) * 255.0 + 0.5) / 255.0


def expected_float_png_rgba(r, g, b, a):
    """Closed-form float→PNG→reload (Non-Color).

    Blender writes float images as 16-bit PNG and unpremultiplies each
    channel as if the buffer were associated-alpha (`c/a`, clamp to 1)
    before storage. Straight-authored pixels with `c > a` therefore reload
    as clamped white (or a boosted mid-tone).
    """
    a_q = q16(a)
    if a_q <= 0.0:
        return (0.0, 0.0, 0.0, 0.0)
    return (q16(min(1.0, r / a_q)), q16(min(1.0, g / a_q)),
            q16(min(1.0, b / a_q)), a_q)


def expected_byte_png_rgba(r, g, b, a):
    """Byte images store straight 8-bit RGBA — no false unpremul."""
    return (q8(r), q8(g), q8(b), q8(a))


def fill_pattern(img):
    buf = [0.0] * (W * H * 4)
    for y, rgb in enumerate(COLORS):
        r, g, b = rgb
        for x, a in enumerate(ALPHAS):
            i = (y * W + x) * 4
            buf[i : i + 4] = [r, g, b, a]
    img.pixels.foreach_set(buf)
    return buf


def max_channel_err(orig, got, channels=4):
    err = 0.0
    for i in range(0, len(orig), 4):
        for c in range(channels):
            err = max(err, abs(orig[i + c] - got[i + c]))
    return err


def max_model_err(got, expect_fn):
    err = 0.0
    worst = None
    for y, rgb in enumerate(COLORS):
        r, g, b = rgb
        for x, a in enumerate(ALPHAS):
            exp = expect_fn(r, g, b, a)
            i = (y * W + x) * 4
            for c in range(4):
                e = abs(got[i + c] - exp[c])
                if e > err:
                    err = e
                    worst = (x, y, a, rgb, exp, got[i : i + 4], e)
    return err, worst


def new_float_image(name):
    img = bpy.data.images.new(name, W, H, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    return img


def new_byte_image(name):
    img = bpy.data.images.new(name, W, H, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    return img


def save_and_reload(img, fmt, ext):
    """Persist via Image.save() and return pixels from a fresh load.

    save() (not save_render) avoids scene color-management baking into the
    file. Non-Color keeps the buffer linear so the unpremul trap is isolated.
    """
    td = tempfile.mkdtemp(prefix="png_exr_alpha_")
    path = os.path.join(td, f"probe.{ext}")
    img.filepath_raw = path
    img.file_format = fmt
    img.save()
    loaded = bpy.data.images.load(path)
    loaded.colorspace_settings.name = "Non-Color"
    got = [0.0] * (W * H * 4)
    loaded.pixels.foreach_get(got)
    return got, path


def png_bit_depth(path):
    """Return (bit_depth, color_type) from a PNG IHDR."""
    with open(path, "rb") as f:
        data = f.read()
    i = 8
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        ctype = data[i + 4:i + 8]
        chunk = data[i + 8:i + 8 + length]
        if ctype == b"IHDR":
            _w, _h, bit, color, _comp, _filt, _inter = struct.unpack(
                ">IIBBBBB", chunk,
            )
            return bit, color
        i = i + 12 + length
    return None, None


def check():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # --- Closed-form worst case on this palette (independent of Blender) ---
    model_worst = 0.0
    for rgb in COLORS:
        for a in ALPHAS:
            exp = expected_float_png_rgba(*rgb, a)
            model_worst = max(
                model_worst,
                abs(exp[0] - rgb[0]),
                abs(exp[1] - rgb[1]),
                abs(exp[2] - rgb[2]),
            )
    if model_worst < PNG_ERR_FLOOR:
        return fail(
            f"closed-form palette worst {model_worst:.7f} < floor "
            f"{PNG_ERR_FLOOR} — probe colors no longer stress false unpremul",
            2,
        )
    print(
        f"closed-form float→PNG worst RGB err {model_worst:.7f} "
        f"(floor {PNG_ERR_FLOOR})"
    )

    # --- 1. float_buffer → PNG: 16-bit + false associated unpremul ---------
    img_f = new_float_image("FloatSrc")
    if not img_f.is_float:
        return fail("float_buffer=True image reports is_float=False", 3)
    orig = fill_pattern(img_f)
    png_got, png_path = save_and_reload(img_f, "PNG", "png")

    bit, color = png_bit_depth(png_path)
    if bit != 16 or color != 6:
        return fail(
            f"float→PNG IHDR bit/color = {bit}/{color}, expected 16/6 (RGBA16) "
            f"— bit-depth contract changed",
            4,
        )
    print(f"float→PNG IHDR bit_depth={bit} color_type={color} (RGBA16)")

    png_vs_orig = max_channel_err(orig, png_got, channels=3)
    if png_vs_orig < PNG_ERR_FLOOR:
        return fail(
            f"float→PNG max RGB err {png_vs_orig:.7f} < floor {PNG_ERR_FLOOR} "
            f"— false-unpremul damage missing (falsify: expecting a "
            f"straight-alpha float PNG path)",
            5,
        )

    model_err, worst = max_model_err(png_got, expected_float_png_rgba)
    if model_err > PNG_MODEL_TOL:
        return fail(
            f"float→PNG disagrees with closed-form false-unpremul model by "
            f"{model_err:.7f} (tol {PNG_MODEL_TOL:.7f}); worst={worst}",
            6,
        )
    print(
        f"float→PNG max RGB err vs authored {png_vs_orig:.7f} "
        f"(must be >= {PNG_ERR_FLOOR}); model residual {model_err:.7f} "
        f"(tol {PNG_MODEL_TOL:.7f})"
    )

    # --- 2. Same float buffer → OpenEXR: float-precision round-trip --------
    img_f2 = new_float_image("FloatExrSrc")
    fill_pattern(img_f2)
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_mode = "RGBA"
    try:
        scene.render.image_settings.color_depth = "32"
    except TypeError:
        pass

    td = tempfile.mkdtemp(prefix="png_exr_alpha_exr_")
    exr_path = os.path.join(td, "probe.exr")
    img_f2.filepath_raw = exr_path
    img_f2.file_format = "OPEN_EXR"
    img_f2.save()
    exr_loaded = bpy.data.images.load(exr_path)
    exr_loaded.colorspace_settings.name = "Non-Color"
    exr_got = [0.0] * (W * H * 4)
    exr_loaded.pixels.foreach_get(exr_got)

    exr_err = max_channel_err(orig, exr_got, channels=4)
    if exr_err > EXR_TOL:
        return fail(
            f"float→EXR max err {exr_err:.7e} > tol {EXR_TOL:.7e} "
            f"— EXR no longer preserves float RGBA",
            7,
        )
    print(f"float→EXR max err {exr_err:.7e} (tol {EXR_TOL:.7e})")

    # --- 3. byte image → PNG: 8-bit straight alpha -------------------------
    img_b = new_byte_image("ByteSrc")
    if img_b.is_float:
        return fail("float_buffer=False image reports is_float=True", 8)
    fill_pattern(img_b)
    byte_got, byte_path = save_and_reload(img_b, "PNG", "png")
    bit_b, color_b = png_bit_depth(byte_path)
    if bit_b != 8 or color_b != 6:
        return fail(
            f"byte→PNG IHDR bit/color = {bit_b}/{color_b}, expected 8/6 "
            f"(RGBA8) — byte bit-depth contract changed",
            9,
        )
    byte_model_err, byte_worst = max_model_err(byte_got, expected_byte_png_rgba)
    if byte_model_err > BYTE_TOL:
        return fail(
            f"byte→PNG disagrees with straight-alpha 8-bit model by "
            f"{byte_model_err:.7f} (tol {BYTE_TOL:.7f}); worst={byte_worst}",
            10,
        )
    # Stress cell: authored (0.02,0.02,0.02,a=1/255). False unpremul → ~1.0;
    # byte straight path must stay near 0.02.
    stress = byte_got[0:4]
    if stress[0] > 0.1:
        return fail(
            f"byte→PNG stress cell RGB=({stress[0]:.5f},{stress[1]:.5f},"
            f"{stress[2]:.5f}) looks false-unpremul-mangled (expected ~0.02) "
            f"— byte/float storage contract flipped",
            11,
        )
    print(
        f"byte→PNG IHDR bit_depth={bit_b}; model residual {byte_model_err:.7f} "
        f"(tol {BYTE_TOL:.7f}); stress cell stays near 0.02 "
        f"({stress[0]:.5f}), not clamped white"
    )

    # --- 4. OPEN_EXR color_mode='RGB' drops alpha --------------------------
    img_f3 = new_float_image("FloatExrRgb")
    fill_pattern(img_f3)
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_mode = "RGB"
    td3 = tempfile.mkdtemp(prefix="png_exr_alpha_rgb_")
    rgb_path = os.path.join(td3, "probe_rgb.exr")
    img_f3.save_render(filepath=rgb_path, scene=scene)
    rgb_loaded = bpy.data.images.load(rgb_path)
    rgb_loaded.colorspace_settings.name = "Non-Color"
    rgb_got = [0.0] * (W * H * 4)
    rgb_loaded.pixels.foreach_get(rgb_got)
    a00 = rgb_got[3]
    if abs(a00 - ALPHAS[0]) < 1e-3:
        return fail(
            f"EXR color_mode=RGB still preserved alpha={a00:.7f} — "
            f"the alpha-drop trap is gone (or save_render ignores color_mode)",
            12,
        )
    if abs(a00 - 1.0) > 1e-3:
        return fail(
            f"EXR color_mode=RGB alpha at (0,0) is {a00:.7f}, expected ~1.0 "
            f"(alpha channel dropped / filled opaque)",
            12,
        )
    print(
        f"EXR color_mode=RGB drops alpha (a00={a00:.7f} ≈ 1.0; authored was "
        f"{ALPHAS[0]:.7f})"
    )

    print("png-exr-alpha: OK")
    return 0


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def make_gallery_card(name, mangled):
    """Visual card of the false-unpremul contract for the staged still.

    Columns = rising alpha; top rows = dark mid-tones that PNG clamps to
    white; lower rows = primaries that survive. Left panel bakes the
    closed-form mangling; right panel shows authored straight RGBA.

    A dark trim is painted into the texture edge so the emissive face reads
    as a recessed screen inside its physical bezel (render-only — checks
    use fill_pattern).
    """
    gw, gh = 256, 192
    border = 10
    img = bpy.data.images.new(name, gw, gh, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    px = [0.0] * (gw * gh * 4)
    n_cols = 6
    row_colors = [
        (0.02, 0.02, 0.02),  # false-unpremul → white for every a < 1
        (0.5, 0.5, 0.5),     # → white for every a < 0.5
        (0.25, 0.25, 0.25),
        (1.0, 0.0, 0.0),     # pure primaries survive (c <= 1 already at ceiling)
        (0.0, 1.0, 0.0),
        (0.2, 0.35, 1.0),    # blue-leaning; G/B still clamp at low a → wash
    ]
    alphas = [1 / 255, 8 / 255, 32 / 255, 64 / 255, 128 / 255, 1.0]
    iw, ih = gw - 2 * border, gh - 2 * border
    col_w = max(1, iw // n_cols)
    row_h = max(1, ih // len(row_colors))
    bezel = (0.04, 0.042, 0.048)
    for y in range(gh):
        for x in range(gw):
            i = (y * gw + x) * 4
            if x < border or y < border or x >= gw - border or y >= gh - border:
                px[i : i + 4] = [bezel[0], bezel[1], bezel[2], 1.0]
                continue
            xi, yi = x - border, y - border
            ri = min(yi // row_h, len(row_colors) - 1)
            ci = min(xi // col_w, n_cols - 1)
            rgb = row_colors[ri]
            a = alphas[ci]
            if mangled:
                r, g, b, _a = expected_float_png_rgba(*rgb, a)
            else:
                r, g, b = rgb
            px[i : i + 4] = [r, g, b, 1.0]
    img.pixels.foreach_set(px)
    return img


def fixture_mats():
    """Designed non-data surfaces: dark polymer bezels, rail-steel struts,
    machined nameplates, plinth — no Principled defaults."""
    def mat_principled(name, color, metallic, rough):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = rough
        return mat

    return {
        "bezel": mat_principled("BezelPolymer", (0.045, 0.048, 0.055), 0.1, 0.5),
        "rail": mat_principled("RailSteel", (0.075, 0.08, 0.09), 0.6, 0.45),
        "plinth": mat_principled("PlinthSteel", (0.10, 0.11, 0.12), 0.6, 0.5),
        "plate": mat_principled("PlateSteel", (0.14, 0.15, 0.17), 0.7, 0.4),
    }


def box_obj(name, dims, loc, mat, rot_x=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.scale = dims
    ob.location = loc
    ob.rotation_euler = (rot_x, 0.0, 0.0)
    bpy.context.collection.objects.link(ob)
    return ob


def face_mesh(name):
    """UV-mapped unit plane (create_grid lies in XY facing +Z; the display
    unit rotates it vertical)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bm.loops.layers.uv.new("UVMap")
        bmesh.ops.create_grid(
            bm, x_segments=1, y_segments=1, size=1.0, calc_uvs=True,
        )
        uv = bm.loops.layers.uv.active
        for face in bm.faces:
            for loop in face.loops:
                u, v = loop[uv].uv
                loop[uv].uv = (u, 1.0 - v)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def face_mat(name, image):
    """Data faces stay pure emission: exact card values, no specular, no
    shading — the panel is a backlit data display."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.interpolation = "Closest"
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    em.inputs["Strength"].default_value = 1.0
    return mat


def caption_mat():
    mat = bpy.data.materials.new("CaptionGrey")
    mat.use_nodes = True
    cb = mat.node_tree.nodes["Principled BSDF"]
    cb.inputs["Base Color"].default_value = (0.42, 0.44, 0.48, 1.0)
    cb.inputs["Metallic"].default_value = 0.2
    cb.inputs["Roughness"].default_value = 0.6
    sock = cb.inputs.get("Emission Color") or cb.inputs["Emission"]
    sock.default_value = (0.38, 0.40, 0.45, 1.0)
    cb.inputs["Emission Strength"].default_value = 0.5
    return mat


def display_unit(name, image, caption, x, mats, capmat):
    """One verification display: the emissive data face seated proud of a
    thick dark bezel, carried by a rear strut and foot, with a machined
    nameplate under the bezel — a physical instrument standing on the
    shared plinth, not a floating texture."""
    root = bpy.data.objects.new(name, None)
    root.location = (x, 0.0, 0.0)
    bpy.context.collection.objects.link(root)

    def adopt(ob):
        ob.parent = root
        return ob

    # bezel with real thickness; the face sits proud of its front surface
    adopt(box_obj(name + "Bezel", (2.64, 0.16, 2.04), (0.0, 0.0, 1.80),
                  mats["bezel"]))
    face = bpy.data.objects.new(name + "Face", face_mesh(name + "Face"))
    bpy.context.collection.objects.link(face)
    face.data.materials.append(face_mat(name + "FaceMat", image))
    face.location = (0.0, -0.085, 1.80)
    face.rotation_euler = (math.radians(90), 0.0, 0.0)
    face.scale = (1.20, 0.90, 1.0)
    adopt(face)
    # rear strut leaning onto the bezel back, foot on the plinth top
    adopt(box_obj(name + "Strut", (0.26, 0.30, 1.30), (0.0, 0.42, 1.10),
                  mats["rail"], rot_x=math.radians(18)))
    adopt(box_obj(name + "Foot", (0.60, 0.80, 0.10), (0.0, 0.72, 0.50),
                  mats["rail"]))
    # nameplate bridging bezel bottom and plinth top
    adopt(box_obj(name + "Plate", (1.60, 0.06, 0.26), (0.0, -0.03, 0.63),
                  mats["plate"]))
    cu = bpy.data.curves.new(name + "Caption", "FONT")
    cu.body = caption
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.size = 0.15
    cu.extrude = 0.004
    cu.materials.append(capmat)
    cap = bpy.data.objects.new(name + "Caption", cu)
    cap.location = (0.0, -0.065, 0.63)
    cap.rotation_euler = (math.radians(90), 0.0, 0.0)
    bpy.context.collection.objects.link(cap)
    adopt(cap)
    return root


def render_still(path, engine):
    import mathutils

    scene = bpy.context.scene

    png_card = make_gallery_card("PngMangled", mangled=True)
    exr_card = make_gallery_card("ExrClean", mangled=False)

    # The verification station: two framed displays on a shared plinth —
    # left bakes the closed-form PNG mangling, right is EXR-clean.
    mats = fixture_mats()
    capmat = caption_mat()
    display_unit("PngDisplay", png_card, "FLOAT → PNG", -1.45, mats, capmat)
    display_unit("ExrDisplay", exr_card, "FLOAT → EXR", 1.45, mats, capmat)
    box_obj("Plinth", (6.10, 1.80, 0.45), (0.0, 0.35, 0.225), mats["plinth"])

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
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02, 0.021, 0.025, 1.0,
    )
    scene.world = world

    def light(name, loc, energy, size, col, target):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        d = mathutils.Vector(target) - ob.location
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(ob)

    # Shaped warm key, faint cool fill, cool rim, and the signature warm
    # wedge between station and wall aimed at the wall point behind the
    # subject — every light has an explicit target so nothing grazes a
    # flat surface (grazing area lights draw stray bands).
    light("Key", (-4.0, -4.5, 7.0), 460.0, 4.5, (1.0, 0.96, 0.9),
          (0.0, 0.2, 1.8))
    light("Fill", (6.0, -3.0, 3.0), 90.0, 9.0, (0.75, 0.85, 1.0),
          (0.5, 0.0, 1.8))
    light("Rim", (0.5, 4.5, 7.0), 320.0, 4.0, (0.6, 0.78, 1.0),
          (0.0, 0.3, 2.0))
    light("Wedge", (-0.5, 5.5, 6.0), 520.0, 4.5, (1.0, 0.76, 0.5),
          (0.0, 9.0, 2.6))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (-0.10, 0.2, 1.65)
    scene.collection.objects.link(aim)

    # Gentle 3/4 from the right: both faces stay fully readable while the
    # bezels, struts, and plinth show their thickness.
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (3.9, -9.3, 3.05)
    con = cam.constraints.new("TRACK_TO")
    con.target = aim
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    scene.collection.objects.link(cam)
    scene.camera = cam

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 64
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    # AgX desaturates the card toward pastel — Standard keeps the clamp visible.
    scene.view_settings.view_transform = "Standard"
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine", default="eevee", choices=("eevee", "cycles"),
        help="render engine for --output (cycles for GPU-less hosts)",
    )
    args = p.parse_args(argv)

    code = check()
    if code != 0:
        return code
    if args.output:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if not render_still(os.path.abspath(args.output), args.engine):
            return fail(f"render produced no file at {args.output}", 13)
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
