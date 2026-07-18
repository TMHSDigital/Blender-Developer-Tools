"""A procedural broadcast test card written with one foreach_set — a runnable example.

Witnesses the `bpy.types.Image` pixel-buffer contract. `Image.pixels` is a flat,
row-major, bottom-left-origin float buffer that is ALWAYS RGBA: `channels == 4`
and `len(pixels) == width * height * 4` even when the image is created with
`alpha=False`, so RGB-stride writes raise. A byte image (the default) stores
8 bits per channel — every float written round-trips through quantization with
max error exactly <= 0.5/255 and strictly > 0 — while `float_buffer=True` stores
float32 and round-trips to ~1e-7. `Image.scale()` reallocates the buffer, so a
`foreach_get` into a stale-size list raises TypeError instead of silently
shearing rows.

The save lifecycle is the trap (identical on 4.5 LTS and 5.1): `Image.save()`
on a GENERATED image silently flips `source` to 'FILE' and drops the in-memory
buffer (`has_data` becomes False). Every later `pixels` read silently re-loads
from whatever sits at that path — the check proves it by overwriting the file
with a different image and reading the imposter's pixels back through the
original datablock. `save_render()` writes the same PNG but leaves
`source` == 'GENERATED' and the buffer intact and exact.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python image_pixels_testcard.py --                 # check only
    blender --background --python image_pixels_testcard.py -- --output t.png  # + render
"""
import bpy, sys, os, math, argparse, tempfile

W, H = 512, 288
BYTE_TOL = 0.5 / 255.0 + 1e-6   # 8-bit quantization: round(v*255)/255, worst case half a step
FLOAT_TOL = 1e-6                # float32 storage of float64 Python values

# Saturated neon take on the classic seven SMPTE bars.
BARS = [
    (0.92, 0.92, 0.92), (0.95, 0.82, 0.10), (0.10, 0.90, 0.85),
    (0.15, 0.85, 0.25), (0.90, 0.15, 0.80), (0.95, 0.20, 0.15),
    (0.15, 0.30, 0.95),
]


def pattern(x, y):
    """Closed-form test-card color at pixel (x, y), origin bottom-left.

    Values are deliberately off the 1/255 grid so byte quantization is
    measurable: a byte image that round-trips these exactly is a failure.
    """
    u, v = x / (W - 1), y / (H - 1)
    if v < 0.14:
        # bottom row: castellated PLUGE-style blocks, plus a bright white
        # origin marker in the bottom-left cell — if a consumer assumes a
        # top-down origin, the marker visibly jumps to the top of the frame
        cell = int(u * 9)
        if cell == 0:
            r = g = b = 0.92
        else:
            r = g = b = (0.04, 0.10)[cell % 2]
    elif v < 0.30:
        # luminance ramp: black -> white, shows 8-bit banding
        r = g = b = u * 0.97
    else:
        r, g, b = BARS[min(int(u * len(BARS)), len(BARS) - 1)]
        # center circle outline, the test-card signature
        d = math.hypot((u - 0.5) * (W / H), v - 0.64)
        if abs(d - 0.31) < 0.012:
            r, g, b = 0.03, 0.03, 0.03
    return r, g, b, 1.0


def flat_pattern():
    """The whole card as one flat RGBA buffer in pixel-buffer order:
    row-major from the BOTTOM row up, 4 floats per pixel."""
    buf = [0.0] * (W * H * 4)
    i = 0
    for y in range(H):
        for x in range(W):
            buf[i:i + 4] = pattern(x, y)
            i += 4
    return buf


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def check():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    expected = flat_pattern()

    # -- buffer geometry: always RGBA, even with alpha=False ----------------
    img = bpy.data.images.new("TestCard", W, H, alpha=False)
    if img.channels != 4 or len(img.pixels) != W * H * 4:
        return fail(f"expected RGBA buffer ({W*H*4}), got channels={img.channels} "
                    f"len={len(img.pixels)}", 3)
    try:
        img.pixels.foreach_set([0.0] * (W * H * 3))  # RGB stride
        return fail("RGB-stride foreach_set was accepted — buffer is not always RGBA", 3)
    except TypeError:
        pass

    # -- byte image: one bulk write, quantized round-trip --------------------
    img.pixels.foreach_set(expected)
    got = [0.0] * (W * H * 4)
    img.pixels.foreach_get(got)
    byte_err = max(abs(a - b) for a, b in zip(expected, got))
    if byte_err > BYTE_TOL:
        return fail(f"byte round-trip error {byte_err:.7f} > {BYTE_TOL:.7f} "
                    f"(stride/orientation bug cannot hide at 512x288)", 4)
    if byte_err <= 0.0:
        return fail("byte image round-tripped exactly — storage is not 8-bit, "
                    "the quantization contract is broken", 4)

    # -- float image: same write, float32-exact round-trip -------------------
    fimg = bpy.data.images.new("TestCardF", W, H, alpha=True, float_buffer=True)
    if not fimg.is_float:
        return fail("float_buffer=True did not produce a float image", 5)
    fimg.pixels.foreach_set(expected)
    fgot = [0.0] * (W * H * 4)
    fimg.pixels.foreach_get(fgot)
    float_err = max(abs(a - b) for a, b in zip(expected, fgot))
    if float_err > FLOAT_TOL:
        return fail(f"float round-trip error {float_err:.2e} > {FLOAT_TOL:.0e}", 5)

    # -- scale() reallocates: stale-size bulk reads must raise ---------------
    half = bpy.data.images.new("Half", W, H, alpha=True)
    half.pixels.foreach_set(expected)
    stale = [0.0] * (W * H * 4)
    half.scale(W // 2, H // 2)
    if len(half.pixels) != (W // 2) * (H // 2) * 4:
        return fail(f"scale() did not reallocate: len={len(half.pixels)}", 6)
    try:
        half.pixels.foreach_get(stale)
        return fail("foreach_get accepted a stale-size buffer after scale()", 6)
    except TypeError:
        pass

    # -- the save() trap: source flips to FILE and pixels re-source from disk --
    tmpdir = tempfile.mkdtemp()
    trap = bpy.data.images.new("Trap", W, H, alpha=True, float_buffer=True)
    trap.pixels.foreach_set(expected)
    trap.filepath_raw = os.path.join(tmpdir, "trap.png")
    trap.file_format = 'PNG'
    trap.save()
    if trap.source != 'FILE' or trap.has_data:
        return fail(f"save() contract changed: source={trap.source} "
                    f"has_data={trap.has_data} (expected FILE / False)", 7)
    # overwrite the file with a mid-gray card BEFORE touching trap.pixels;
    # if the buffer were still in memory the read below would return the card
    imposter = bpy.data.images.new("Imposter", W, H, alpha=True)
    gray = 154.0 / 255.0  # exactly representable in 8-bit, no quantization noise
    imposter.pixels.foreach_set([gray] * (W * H * 4))
    imposter.filepath_raw = trap.filepath_raw
    imposter.file_format = 'PNG'
    imposter.save()
    tgot = [0.0] * (W * H * 4)
    trap.pixels.foreach_get(tgot)  # silently re-loaded from the PNG on disk
    trap_err = max(abs(v - gray) for v in tgot)
    if trap_err > BYTE_TOL:
        return fail(f"pixels did not re-source from disk after save() "
                    f"(max dev from imposter gray {trap_err:.4f}) — the buffer-drop "
                    "trap this example documents has vanished", 7)

    # -- save_render() is the non-destructive path ----------------------------
    keep = bpy.data.images.new("Keep", W, H, alpha=True, float_buffer=True)
    keep.pixels.foreach_set(expected)
    keep.save_render(os.path.join(tmpdir, "keep.png"))
    if keep.source != 'GENERATED':
        return fail(f"save_render() flipped source to {keep.source}", 8)
    kgot = [0.0] * (W * H * 4)
    keep.pixels.foreach_get(kgot)
    keep_err = max(abs(a - b) for a, b in zip(expected, kgot))
    if keep_err > FLOAT_TOL:
        return fail(f"save_render() disturbed the buffer (err {keep_err:.2e})", 8)

    # -- byte sRGB image: PNG save/reload round-trips at quantization --------
    disk = bpy.data.images.new("Disk", W, H, alpha=True)
    disk.pixels.foreach_set(expected)
    disk.filepath_raw = os.path.join(tmpdir, "disk.png")
    disk.file_format = 'PNG'
    disk.save()
    reloaded = bpy.data.images.load(disk.filepath_raw)
    rgot = [0.0] * (W * H * 4)
    reloaded.pixels.foreach_get(rgot)
    disk_err = max(abs(a - b) for a, b in zip(expected, rgot))
    if disk_err > BYTE_TOL:
        return fail(f"byte PNG save/reload error {disk_err:.7f} > {BYTE_TOL:.7f}", 9)

    print(f"byte round-trip max err {byte_err:.7f} (tol {BYTE_TOL:.7f}, must be > 0), "
          f"float {float_err:.2e} (tol {FLOAT_TOL:.0e}), post-save() imposter read "
          f"max dev {trap_err:.7f} (buffer really dropped), save_render() "
          f"{keep_err:.2e}, byte PNG reload {disk_err:.7f}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(path, engine):
    import bmesh
    scene = bpy.context.scene

    # the card itself: a byte sRGB image, written with the one bulk call
    card = bpy.data.images.new("TestCard", W, H, alpha=False)
    card.pixels.foreach_set(flat_pattern())

    # screen: emissive plane textured with the card (16:9, 3.2 wide)
    sw, sh = 3.2, 1.8
    screen_me = bpy.data.meshes.new("Screen")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        # a UV layer must exist explicitly — without UVs every fragment
        # samples texel (0,0) and the screen renders one flat color
        uv = bm.loops.layers.uv.new("UVMap")
        for face in bm.faces:
            for loop in face.loops:
                loop[uv].uv = (loop.vert.co.x + 0.5, loop.vert.co.y + 0.5)
        bm.to_mesh(screen_me)
    finally:
        bm.free()
    smat = bpy.data.materials.new("CardEmit")
    smat.use_nodes = True
    nodes, links = smat.node_tree.nodes, smat.node_tree.links
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = card
    tex.interpolation = 'Closest'   # keep the pixel grid honest up close
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.4
    links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.35  # hotter washes the bars pastel
    screen_me.materials.append(smat)
    screen = bpy.data.objects.new("Screen", screen_me)
    screen.scale = (sw, sh, 1.0)
    screen.rotation_euler = (math.radians(90), 0.0, math.radians(-16))
    screen.location = (0.0, 0.0, sh / 2 + 0.14)
    scene.collection.objects.link(screen)

    # bezel: a slightly larger dark slab just behind the screen
    bezel_me = bpy.data.meshes.new("Bezel")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(bezel_me)
    finally:
        bm.free()
    bmat = bpy.data.materials.new("Bezel")
    bmat.use_nodes = True
    bb = bmat.node_tree.nodes["Principled BSDF"]
    bb.inputs["Base Color"].default_value = (0.02, 0.022, 0.025, 1.0)
    bb.inputs["Roughness"].default_value = 0.28
    bb.inputs["Metallic"].default_value = 0.6
    bezel_me.materials.append(bmat)
    bezel = bpy.data.objects.new("Bezel", bezel_me)
    bezel.scale = (sw + 0.14, 0.09, sh + 0.14)
    bezel.rotation_euler = (0.0, 0.0, math.radians(-16))
    # offset along the yawed screen normal so the slab stays behind the plane
    bezel.location = (0.052 * math.sin(math.radians(16)),
                      0.052 * math.cos(math.radians(16)), sh / 2 + 0.14)
    scene.collection.objects.link(bezel)

    # plinth foot under the monitor
    foot = bpy.data.objects.new("Foot", bezel_me.copy())
    foot.data.materials.clear(); foot.data.materials.append(bmat)
    foot.scale = (1.1, 0.5, 0.14)
    foot.location = (0.0, 0.05, 0.07)
    scene.collection.objects.link(foot)

    # glossy dark floor + back wall
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
    fb.inputs["Base Color"].default_value = (0.045, 0.05, 0.06, 1.0)
    fb.inputs["Roughness"].default_value = 0.18
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.025, 0.03, 0.04, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # teal underglow bar tucked beneath the monitor, spilling onto the floor
    strip = bpy.data.objects.new("GlowStrip", bezel_me.copy())
    gmat = bpy.data.materials.new("Glow")
    gmat.use_nodes = True
    gb = gmat.node_tree.nodes["Principled BSDF"]
    gb.inputs["Emission Color"].default_value = (0.1, 0.9, 0.8, 1.0)
    gb.inputs["Emission Strength"].default_value = 12.0
    strip.data.materials.clear(); strip.data.materials.append(gmat)
    strip.scale = (2.7, 0.045, 0.015)
    strip.rotation_euler = (0.0, 0.0, math.radians(-16))
    strip.location = (0.0, -0.10, 0.015)
    scene.collection.objects.link(strip)

    # the card is its own key light; cool fill and a warm rim shape the bezel
    light("Fill", (-5.2, -3.0, 3.6), 80.0, 7.0, (0.7, 0.8, 1.0), (58, 0, -60))
    light("Rim", (4.2, 2.8, 2.2), 260.0, 2.5, (1.0, 0.72, 0.45), (-70, 0, 125))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 44.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-2.45, -5.7, 1.62)
    cam.rotation_euler = (math.radians(84.5), 0.0, math.radians(-23.0))
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

    code = check()
    if code:
        return code

    if args.output:
        if not render_still(os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 10
        print(f"rendered still {args.output}")

    print("image-pixels-testcard OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
