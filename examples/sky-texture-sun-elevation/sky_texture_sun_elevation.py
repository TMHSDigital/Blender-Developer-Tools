"""Nishita / multiple-scattering sky + sun_elevation — a runnable example.

Witnesses the world Sky Texture contract AI-generated lighting code most often
gets wrong across the 4.5 LTS → 5.1 window:

1. ``ShaderNodeTexSky`` must drive the World Background Color. A near-black
   Background Strength alone is not a sky.
2. ``sky_type`` renamed: ``NISHITA`` on 4.5 LTS, ``MULTIPLE_SCATTERING``
   (Nishita's successor) on 5.1 — assigning the legacy identifier on 5.1 fails.
3. ``dust_density`` exists only on 4.5; 5.1 raises AttributeError and exposes
   ``aerosol_density`` instead (AI still emits ``dust_density``).
4. ``sun_elevation`` is load-bearing: raising it brightens zenith luminance
   — proven with two tiny Cycles EXR probes (straight-up camera) in one check.

By default it runs the correctness check (tiny Cycles CPU renders, no gallery
still). Pass --output to also render a still:

    blender --background --python sky_texture_sun_elevation.py --
    blender --background --python sky_texture_sun_elevation.py -- --output s.png
"""
import bpy, bmesh, sys, os, math, argparse, tempfile, shutil

# Radians: low sun vs high sun for the A/B zenith luminance probe
ELEV_LOW = math.radians(8.0)
ELEV_HIGH = math.radians(55.0)
# Tiny probe resolution / samples — deterministic CPU Cycles
PXW, PXH = 48, 48
CYCLES_SAMPLES = 24
# Background Strength kept low so the probe stays unclipped under Standard
PROBE_STRENGTH = 0.05
# Zenith luminance (EXR, straight-up camera) must rise with sun_elevation
ZENITH_RISE_MIN = 1.25
# Absolute floor so a black / unlinked world cannot sneak through
HIGH_ZENITH_MIN = 0.05


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def sky_type_for_version():
    """4.5: NISHITA. 5.1: MULTIPLE_SCATTERING (Nishita successor; NISHITA gone)."""
    if bpy.app.version >= (5, 0, 0):
        return "MULTIPLE_SCATTERING"
    return "NISHITA"


def build_sky_world(elevation):
    """Create a World whose Background Color is driven by ShaderNodeTexSky."""
    world = bpy.data.worlds.new("SkyWorld")
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)

    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.name = "Sky"
    sky.location = (-300, 0)
    sky.sky_type = sky_type_for_version()
    sky.sun_elevation = elevation
    sky.sun_rotation = math.radians(-35.0)
    sky.sun_disc = True
    sky.sun_intensity = 1.0
    if bpy.app.version >= (5, 0, 0):
        sky.aerosol_density = 1.0
    else:
        sky.dust_density = 1.0
    sky.air_density = 1.0
    sky.ozone_density = 1.0

    bg = nt.nodes.new("ShaderNodeBackground")
    bg.name = "Background"
    bg.location = (0, 0)
    # Gallery still restores Strength=1.0 in render_still; probe uses PROBE_STRENGTH
    bg.inputs["Strength"].default_value = 1.0

    out = nt.nodes.new("ShaderNodeOutputWorld")
    out.name = "World Output"
    out.location = (250, 0)

    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return world, sky, bg


def _principled(name, rgb, rough, metallic=0.0, specular=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    # Specular IOR Level renamed across versions — set if present
    spec = b.inputs.get("Specular IOR Level") or b.inputs.get("Specular")
    if spec is not None and hasattr(spec, "default_value"):
        try:
            spec.default_value = specular
        except TypeError:
            pass
    return mat


def _mesh_obj(sc, name, build_bm, loc, mat, smooth=True):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        build_bm(bm)
        bm.to_mesh(me)
    finally:
        bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    sc.collection.objects.link(ob)
    return ob


def build_ceramic(sc):
    """A turned terracotta jar — saturated clay + pale glaze lid."""
    clay = _principled("Clay", (0.78, 0.22, 0.08), rough=0.52, metallic=0.0, specular=0.2)
    glaze = _principled("Glaze", (0.55, 0.18, 0.06), rough=0.28, metallic=0.0, specular=0.4)

    def body(bm):
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False,
            segments=64, radius1=0.62, radius2=0.42, depth=1.35,
        )
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0.0, 0.0, 0.68))

    vessel = _mesh_obj(sc, "Vessel", body, (0.0, 0.0, 0.0), clay)
    bev = vessel.modifiers.new("Bev", "BEVEL")
    bev.width = 0.025
    bev.segments = 3
    bev.limit_method = "ANGLE"

    def lid(bm):
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False,
            segments=48, radius1=0.40, radius2=0.10, depth=0.32,
        )

    knob = _mesh_obj(sc, "Lid", lid, (0.0, 0.0, 1.48), glaze)
    return vessel, knob


def build_floor(sc):
    mat = _principled("Floor", (0.025, 0.026, 0.030), rough=0.85, specular=0.05)

    def grid(bm):
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60.0)

    return _mesh_obj(sc, "Floor", grid, (0.0, 0.0, 0.0), mat, smooth=False)


def setup_probe_camera(sc):
    """Camera looking straight up (+Z) so the frame is pure zenith sky."""
    cam_data = bpy.data.cameras.new("ProbeCam")
    cam_data.lens = 24.0
    cam = bpy.data.objects.new("ProbeCam", cam_data)
    cam.location = (0.0, 0.0, 0.0)
    # Local -Z → world +Z
    cam.rotation_euler = (math.radians(-90.0), 0.0, 0.0)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return cam


def setup_probe_render(sc, w, h, samples):
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    # EXR keeps linear values; PNG+Standard clips bright sky toward 1.0
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "32"
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"


def mean_center_luma(img, half=2):
    w, h = img.size
    px = img.pixels
    acc = 0.0
    n = 0
    for y in range(h // 2 - half, h // 2 + half + 1):
        for x in range(w // 2 - half, w // 2 + half + 1):
            i = (y * w + x) * 4
            acc += 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]
            n += 1
    return acc / max(n, 1)


def render_zenith_luma(sc, world, sky, elevation, tmp, name):
    sky.sun_elevation = elevation
    sky.sun_disc = False  # disc would dominate the center sample
    sc.world = world
    path = os.path.join(tmp, name)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    luma = mean_center_luma(img)
    bpy.data.images.remove(img)
    return luma


def check_api(sky):
    """RNA surface + version traps."""
    expected = sky_type_for_version()
    if sky.sky_type != expected:
        print(
            f"ERROR: sky_type {sky.sky_type!r} != expected {expected!r}",
            file=sys.stderr,
        )
        return 3

    sky.sun_elevation = ELEV_HIGH
    if abs(sky.sun_elevation - ELEV_HIGH) > 1e-5:
        print(
            f"ERROR: sun_elevation round-trip {sky.sun_elevation} != {ELEV_HIGH}",
            file=sys.stderr,
        )
        return 4

    if bpy.app.version >= (5, 0, 0):
        if hasattr(sky, "dust_density"):
            print(
                "ERROR: dust_density still present on 5.x — expected AttributeError trap",
                file=sys.stderr,
            )
            return 5
        try:
            _ = sky.dust_density
            print("ERROR: dust_density read did not raise on 5.x", file=sys.stderr)
            return 5
        except AttributeError:
            pass
        if not hasattr(sky, "aerosol_density"):
            print("ERROR: aerosol_density missing on 5.x", file=sys.stderr)
            return 5
        ids = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
        if "NISHITA" in ids:
            print("ERROR: legacy NISHITA still in 5.x sky_type enum", file=sys.stderr)
            return 5
        if "MULTIPLE_SCATTERING" not in ids:
            print(
                f"ERROR: MULTIPLE_SCATTERING missing from 5.x enum {ids}",
                file=sys.stderr,
            )
            return 5
        print(
            f"5.x contract: sky_type={sky.sky_type} aerosol_density={sky.aerosol_density} "
            f"dust_density=AttributeError NISHITA=gone"
        )
    else:
        if not hasattr(sky, "dust_density"):
            print("ERROR: dust_density missing on 4.5", file=sys.stderr)
            return 5
        ids = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
        if "NISHITA" not in ids:
            print(f"ERROR: NISHITA missing from 4.5 sky_type enum {ids}", file=sys.stderr)
            return 5
        if "MULTIPLE_SCATTERING" in ids:
            print(
                "ERROR: MULTIPLE_SCATTERING unexpectedly present on 4.5",
                file=sys.stderr,
            )
            return 5
        print(
            f"4.5 contract: sky_type={sky.sky_type} dust_density={sky.dust_density} "
            f"aerosol_density={hasattr(sky, 'aerosol_density')}"
        )
    return 0


def check_links(world):
    nt = world.node_tree
    sky = nt.nodes.get("Sky")
    bg = nt.nodes.get("Background")
    out = nt.nodes.get("World Output")
    if sky is None or bg is None or out is None:
        print("ERROR: Sky / Background / World Output nodes missing", file=sys.stderr)
        return 6
    ok_sky = any(
        l.from_node == sky and l.from_socket.name == "Color"
        and l.to_node == bg and l.to_socket.name == "Color"
        for l in nt.links
    )
    ok_bg = any(
        l.from_node == bg and l.to_node == out and l.to_socket.name == "Surface"
        for l in nt.links
    )
    if not ok_sky or not ok_bg:
        print(
            f"ERROR: world links broken (sky→bg={ok_sky}, bg→out={ok_bg})",
            file=sys.stderr,
        )
        return 6
    return 0


def check(sc, world, sky, bg):
    code = check_links(world)
    if code:
        return code
    code = check_api(sky)
    if code:
        return code

    for ob in sc.objects:
        if ob.type == "MESH":
            ob.hide_render = True

    setup_probe_camera(sc)
    setup_probe_render(sc, PXW, PXH, CYCLES_SAMPLES)
    bg.inputs["Strength"].default_value = PROBE_STRENGTH

    tmp = tempfile.mkdtemp(prefix="sky_elev_")
    try:
        z_lo = render_zenith_luma(sc, world, sky, ELEV_LOW, tmp, "low.exr")
        z_hi = render_zenith_luma(sc, world, sky, ELEV_HIGH, tmp, "high.exr")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for ob in sc.objects:
        if ob.type == "MESH":
            ob.hide_render = False
    bg.inputs["Strength"].default_value = 1.0
    sky.sun_disc = True

    if z_hi < HIGH_ZENITH_MIN:
        print(
            f"ERROR: high-elevation zenith luma {z_hi:.4f} < {HIGH_ZENITH_MIN} "
            f"(world is not a working sky)",
            file=sys.stderr,
        )
        return 7

    rise = z_hi / max(z_lo, 1e-6)
    if rise < ZENITH_RISE_MIN:
        print(
            f"ERROR: zenith luma did not rise with elevation: "
            f"low={z_lo:.4f} high={z_hi:.4f} rise={rise:.4f} < {ZENITH_RISE_MIN}",
            file=sys.stderr,
        )
        return 8

    print(
        f"sun_elevation low={math.degrees(ELEV_LOW):.1f}deg zenith_L={z_lo:.4f}"
    )
    print(
        f"sun_elevation high={math.degrees(ELEV_HIGH):.1f}deg zenith_L={z_hi:.4f}"
    )
    print(
        f"zenith_rise={rise:.4f} (gate>={ZENITH_RISE_MIN}) "
        f"probe_strength={PROBE_STRENGTH} samples={CYCLES_SAMPLES} "
        f"sky_type={sky.sky_type} fmt=OPEN_EXR"
    )
    return 0


def _stage_for_still(sc, world, sky, elevation):
    """Shared beauty staging; elevation is the variable under test."""
    sky.sun_elevation = elevation
    sky.sun_rotation = math.radians(-45.0)
    sky.sun_intensity = 1.0
    sky.sun_disc = False
    sky.ozone_density = 5.0
    sky.air_density = 1.0
    if bpy.app.version >= (5, 0, 0):
        sky.aerosol_density = 0.45
    else:
        sky.dust_density = 0.45
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.08
    sc.world = world

    # Remove prior still lights / cams from earlier calls
    for ob in list(sc.objects):
        if ob.name.startswith(("Key", "Fill", "Rim", "Cam", "Aim", "ProbeCam", "Label")):
            bpy.data.objects.remove(ob, do_unlink=True)
    for cam in list(bpy.data.cameras):
        if cam.users == 0:
            bpy.data.cameras.remove(cam)
    for ld in list(bpy.data.lights):
        if ld.users == 0:
            bpy.data.lights.remove(ld)

    def area(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        sc.collection.objects.link(ob)

    area("Key", (-3.0, -3.5, 4.0), 420.0, 4.0, (1.0, 0.95, 0.88), (50, 0, -32))
    area("Fill", (3.5, -2.2, 1.8), 55.0, 8.0, (0.7, 0.82, 1.0), (70, 0, 42))
    area("Rim", (-0.5, 3.8, 2.5), 120.0, 3.5, (0.55, 0.72, 1.0), (-55, 0, 185))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.8)
    sc.collection.objects.link(aim)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 40.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (2.15, -3.55, 1.2)
    sc.collection.objects.link(cam)
    sc.camera = cam
    tr = cam.constraints.new("TRACK_TO")
    tr.target = aim
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"


def _render_panel(sc, path, engine, samples=64):
    sc.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        sc.cycles.device = "CPU"
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
    else:
        try:
            sc.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    sc.render.resolution_x = 640
    sc.render.resolution_y = 720
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    sc.view_settings.view_transform = "Standard"
    bpy.ops.render.render(write_still=True)


def _diptych(left_path, right_path, out_path):
    """Pack two 640x720 panels into a 1280x720 gallery still."""
    left = bpy.data.images.load(left_path)
    right = bpy.data.images.load(right_path)
    w, h = 1280, 720
    canvas = bpy.data.images.new("Diptych", width=w, height=h, alpha=False)
    lp = list(left.pixels)
    rp = list(right.pixels)
    out = [0.0] * (w * h * 4)
    pw = 640
    for y in range(h):
        for x in range(pw):
            si = (y * pw + x) * 4
            di_l = (y * w + x) * 4
            di_r = (y * w + (x + pw)) * 4
            out[di_l:di_l + 4] = lp[si:si + 4]
            out[di_r:di_r + 4] = rp[si:si + 4]
    canvas.pixels = out
    canvas.filepath_raw = out_path
    canvas.file_format = "PNG"
    canvas.save()
    bpy.data.images.remove(left)
    bpy.data.images.remove(right)
    bpy.data.images.remove(canvas)


def render_still(sc, world, sky, path, engine):
    """Gallery still: low vs high sun_elevation diptych — the contract at a glance."""
    tmp = tempfile.mkdtemp(prefix="sky_still_")
    try:
        left = os.path.join(tmp, "low.png")
        right = os.path.join(tmp, "high.png")
        _stage_for_still(sc, world, sky, ELEV_LOW)
        _render_panel(sc, left, engine, samples=72)
        _stage_for_still(sc, world, sky, ELEV_HIGH)
        _render_panel(sc, right, engine, samples=72)
        _diptych(left, right, path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    world, sky, bg = build_sky_world(ELEV_LOW)
    sc.world = world
    build_floor(sc)
    build_ceramic(sc)
    return sc, world, sky, bg


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine",
        default="cycles",
        choices=("eevee", "cycles"),
        help="render engine for --output (cycles default: sky is a Cycles strength)",
    )
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    sc, world, sky, bg = build_scene()
    code = check(sc, world, sky, bg)
    if code:
        return code

    if args.output:
        if not render_still(sc, world, sky, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 9
        print(f"rendered still {args.output}")

    print("sky-texture-sun-elevation OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
