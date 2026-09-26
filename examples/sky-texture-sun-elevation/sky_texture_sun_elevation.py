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

``--unlink-sky`` drops the Sky → Background Color link and still asserts
the chain. That is the falsifier (``--same-axis`` in export-preset-axis).
The sky_type / dust_density version traps are untouched.

By default it runs the correctness check (tiny Cycles CPU renders, no gallery
still). Pass --output to also render the gallery still: a red-granite gnomon
obelisk on a paved plaza, lit only by the sky, as an 8 deg | 55 deg diptych.
The render path gates framing (exit 10, per panel) and clipped highlights
under Standard (exit 12):

    blender --background --python sky_texture_sun_elevation.py --
    blender --background --python sky_texture_sun_elevation.py -- --unlink-sky
    blender --background --python sky_texture_sun_elevation.py -- --output s.png
"""
import bpy, bmesh, sys, os, math, argparse, tempfile, shutil
from mathutils import Matrix

# Shared framing gate (render path only); see examples/gallery_framing.py.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

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
# Gallery still samples per panel (Cycles CPU, denoised)
STILL_SAMPLES = 96


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
    # The probe drops this to PROBE_STRENGTH; the still uses STILL_STRENGTH
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


# Gnomon-obelisk proportions (metres). The obelisk is a sundial gnomon: its
# shadow along the bronze meridian scale is how the still reads elevation.
STEP_SIZES = ((1.56, 0.16), (1.18, 0.15), (0.82, 0.16))  # (square side, height)
SHAFT_BASE = 0.40
SHAFT_TOP = 0.27
SHAFT_H = 2.35
PYRAMIDION_H = 0.24
# Horizontal direction the shadow falls, from +X counter-clockwise. The camera
# looks roughly along +Y, so -40 deg throws the shadow to the right and toward
# the lens: the sun sits behind the obelisk's left shoulder, far enough
# off-axis that its disc stays out of frame and only the dusk glow on the
# horizon enters the 8 deg panel.
SHADOW_AZIMUTH = math.radians(-40.0)
# Obelisk yaw: one visible face turned toward the sun, the other in shade.
HERO_YAW = math.radians(30.0)


def _box(bm, sx, sy, sz, z0=0.0, taper_top=None):
    """Axis-aligned box, base at z0. taper_top scales the top face (a frustum)."""
    geom = bmesh.ops.create_cube(bm, size=1.0)
    verts = [v for v in geom["verts"]]
    for v in verts:
        top = v.co.z > 0.0
        s = taper_top if (top and taper_top is not None) else 1.0
        v.co.x = v.co.x * sx * s
        v.co.y = v.co.y * sy * s
        v.co.z = (v.co.z + 0.5) * sz + z0
    return verts


def _bevel(ob, width, segments=2):
    mod = ob.modifiers.new("Chamfer", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    return mod


def _stone_material(name, dark, light, rough, scale):
    """Principled stone with a noise-mixed two-tone base, so it is not a flat fill."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = rough
    spec = b.inputs.get("Specular IOR Level") or b.inputs.get("Specular")
    if spec is not None:
        spec.default_value = 0.3
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 6.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return mat


def _paving_material():
    """Limestone pavers: a Brick texture with a soft mortar, object-space."""
    mat = bpy.data.materials.new("Paving")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.82
    spec = b.inputs.get("Specular IOR Level") or b.inputs.get("Specular")
    if spec is not None:
        spec.default_value = 0.2
    tc = nt.nodes.new("ShaderNodeTexCoord")
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.inputs["Scale"].default_value = 0.9
    brick.inputs["Mortar Size"].default_value = 0.012
    brick.inputs["Color1"].default_value = (0.46, 0.40, 0.32, 1.0)
    brick.inputs["Color2"].default_value = (0.39, 0.34, 0.27, 1.0)
    brick.inputs["Mortar"].default_value = (0.16, 0.14, 0.11, 1.0)
    brick.offset = 0.5
    brick.squash = 1.0
    nt.links.new(tc.outputs["Object"], brick.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], b.inputs["Base Color"])
    return mat


def build_ground(sc):
    """Paved plaza on open ground that runs to the horizon: no void below it."""
    ground_mat = _stone_material(
        "Ground", (0.20, 0.15, 0.10), (0.30, 0.24, 0.17), rough=0.95, scale=0.8,
    )

    def plane(bm):
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=2500.0)

    ground = _mesh_obj(sc, "Ground", plane, (0.0, 0.0, 0.0), ground_mat, smooth=False)

    def disc(bm):
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False,
            segments=96, radius1=6.5, radius2=6.5, depth=0.04,
        )
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0.0, 0.0, 0.02))

    plaza = _mesh_obj(sc, "Plaza", disc, (0.0, 0.0, 0.0), _paving_material(), smooth=False)
    return ground, plaza


def build_gnomon(sc):
    """Red-granite obelisk on a stepped limestone plinth, matte-gilt pyramidion,
    and a bronze meridian scale inlaid in the paving along the shadow line.

    Returns (hero parts, meridian scale). The hero parts are what the
    framing matte measures; the scale is ground inlay (stage).
    """
    granite = _stone_material(
        "RedGranite", (0.34, 0.11, 0.07), (0.52, 0.22, 0.15), rough=0.58, scale=38.0,
    )
    limestone = _stone_material(
        "Limestone", (0.40, 0.36, 0.29), (0.50, 0.46, 0.37), rough=0.78, scale=6.0,
    )
    # Matte gilt, not metallic: a metallic cap Fresnel-glinted the 55 deg sun
    # to pure white at grazing, whatever its roughness.
    gilt = _principled("MatteGilt", (0.42, 0.28, 0.09), rough=0.6, metallic=0.0, specular=0.3)
    bronze = _principled("Bronze", (0.26, 0.17, 0.10), rough=0.7, metallic=0.85)

    parts = []
    z = 0.04  # plaza top
    for i, (side, h) in enumerate(STEP_SIZES):
        def step(bm, side=side, h=h, z=z):
            _box(bm, side, side, h, z0=z)
        ob = _mesh_obj(sc, f"PlinthStep{i + 1}", step, (0.0, 0.0, 0.0), limestone, smooth=False)
        _bevel(ob, 0.018)
        parts.append(ob)
        z += h

    # Dedication plaque on the die face that turns toward the camera.
    die_side, die_h = STEP_SIZES[-1]

    def plaque(bm, z=z):
        verts = _box(bm, 0.40, 0.014, 0.085, z0=z - die_h / 2.0 - 0.0425)
        for v in verts:
            v.co.y -= die_side / 2.0 + 0.007

    ob = _mesh_obj(sc, "DedicationPlaque", plaque, (0.0, 0.0, 0.0), bronze, smooth=False)
    _bevel(ob, 0.004, segments=1)
    parts.append(ob)

    def collar(bm, z=z):
        _box(bm, SHAFT_BASE + 0.07, SHAFT_BASE + 0.07, 0.07, z0=z)

    ob = _mesh_obj(sc, "BronzeCollar", collar, (0.0, 0.0, 0.0), bronze, smooth=False)
    _bevel(ob, 0.012)
    parts.append(ob)
    z += 0.07

    def shaft(bm, z=z):
        _box(bm, SHAFT_BASE, SHAFT_BASE, SHAFT_H, z0=z, taper_top=SHAFT_TOP / SHAFT_BASE)

    ob = _mesh_obj(sc, "ObeliskShaft", shaft, (0.0, 0.0, 0.0), granite, smooth=False)
    _bevel(ob, 0.010)
    parts.append(ob)
    z += SHAFT_H

    def pyramidion(bm, z=z):
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=4,
            radius1=SHAFT_TOP / math.sqrt(2.0), radius2=0.0, depth=PYRAMIDION_H,
        )
        bmesh.ops.rotate(
            bm, verts=bm.verts, cent=(0.0, 0.0, 0.0),
            matrix=Matrix.Rotation(math.radians(45.0), 3, "Z"),
        )
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0.0, 0.0, z + PYRAMIDION_H / 2.0))

    ob = _mesh_obj(sc, "Pyramidion", pyramidion, (0.0, 0.0, 0.0), gilt, smooth=False)
    parts.append(ob)
    for ob in parts:
        ob.rotation_euler.z = HERO_YAW

    # Meridian scale: a bronze strip from the plinth edge along the shadow
    # line, with a cross-tick every metre (one hour-line per tick).
    def scale_bm(bm):
        start, end = 0.95, 6.3
        length = end - start
        strip = _box(bm, length, 0.07, 0.012, z0=0.035)
        for v in strip:
            v.co.x += start + length / 2.0
        for m in range(1, 7):
            tick = _box(bm, 0.035, 0.30 if m % 2 == 0 else 0.20, 0.012, z0=0.035)
            for v in tick:
                v.co.x += float(m)
        rot = Matrix.Rotation(SHADOW_AZIMUTH, 3, "Z")
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0.0, 0.0, 0.0), matrix=rot)

    meridian = _mesh_obj(sc, "MeridianScale", scale_bm, (0.0, 0.0, 0.0), bronze, smooth=False)
    return parts, meridian


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


def check(sc, world, sky, bg, unlink_sky=False):
    if unlink_sky:
        nt = world.node_tree
        for link in list(nt.links):
            if link.from_node == sky and link.to_node.name == "Background":
                nt.links.remove(link)
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


# Still: one Background Strength for both panels, so the only variable
# between them is sun_elevation. Tuned so the brightest pixel in either
# panel stays below clipping under Standard (which does not compress).
STILL_STRENGTH = 0.035
PANEL_W, PANEL_H = 640, 720
GUTTER = 12  # px; a deliberate dark rule between the two panels
GUTTER_RGB = (0.02, 0.021, 0.025)
# Clip gate: fraction of pixels allowed at 8-bit full scale in any channel.
CLIP_LEVEL = 254.5 / 255.0
CLIP_MAX_FRACTION = 0.0005
EXIT_CLIPPED = 12


def _sun_rotation_for_shadow(shadow_azimuth):
    """Sky sun_rotation that puts the sun opposite the given shadow azimuth.

    sun_rotation is a compass bearing: measured clockwise from +Y, so the
    sun's horizontal angle from +X (counter-clockwise) is 90 deg - rotation.
    Measured, not assumed: the first draft used rotation + 90 deg and threw
    the shadow to the wrong side of the obelisk.
    """
    sun_azimuth = shadow_azimuth + math.pi
    return math.pi / 2.0 - sun_azimuth


def _stage_for_still(sc, world, sky, elevation):
    """Shared staging; sun_elevation is the only thing that differs per panel.

    The sky is the only light: its sun disc is the key (hard shadow from
    the gnomon) and its dome is the fill. No studio lights, so a
    sun_elevation that did not take would render two identical panels.
    """
    sky.sun_elevation = elevation
    sky.sun_rotation = _sun_rotation_for_shadow(SHADOW_AZIMUTH)
    sky.sun_intensity = 1.0
    sky.sun_disc = True  # the disc is the key light; it stays off-frame
    sky.air_density = 1.0
    sky.ozone_density = 1.0
    if bpy.app.version >= (5, 0, 0):
        sky.aerosol_density = 1.0
    else:
        sky.dust_density = 1.0
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = STILL_STRENGTH
    sc.world = world

    cam = sc.objects.get("Cam")
    if cam is not None:
        return cam
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.5, 0.0, 1.6)
    sc.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 35.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.42, -4.2, 1.0)
    sc.collection.objects.link(cam)
    sc.camera = cam
    tr = cam.constraints.new("TRACK_TO")
    tr.target = aim
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    return cam


def _render_panel(sc, path, engine, samples):
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
    sc.render.resolution_x = PANEL_W
    sc.render.resolution_y = PANEL_H
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.filepath = path
    # Standard, not AgX: AgX desaturates the granite and the sky toward
    # pastel. Standard does not compress, hence the clip gate below.
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    bpy.ops.render.render(write_still=True)


def _diptych(left_path, right_path):
    """Two PANEL_W x PANEL_H panels side by side with a dark gutter rule."""
    left = bpy.data.images.load(left_path, check_existing=False)
    right = bpy.data.images.load(right_path, check_existing=False)
    try:
        lp = left.pixels[:]
        rp = right.pixels[:]
    finally:
        bpy.data.images.remove(left)
        bpy.data.images.remove(right)
    w, h, pw = PANEL_W * 2, PANEL_H, PANEL_W
    out = [0.0] * (w * h * 4)
    row = pw * 4
    for y in range(h):
        s = y * row
        d = y * w * 4
        out[d:d + row] = lp[s:s + row]
        out[d + row:d + 2 * row] = rp[s:s + row]
    g0 = pw - GUTTER // 2
    for y in range(h):
        for x in range(g0, g0 + GUTTER):
            i = (y * w + x) * 4
            out[i:i + 4] = (*GUTTER_RGB, 1.0)
    return w, h, out, lp, rp


def clip_fraction(pixels):
    """Fraction of pixels with any RGB channel at 8-bit full scale."""
    n = len(pixels) // 4
    hot = 0
    for i in range(0, len(pixels), 4):
        if max(pixels[i], pixels[i + 1], pixels[i + 2]) >= CLIP_LEVEL:
            hot += 1
    return hot / max(n, 1)


def mean_luma(pixels):
    n = len(pixels) // 4
    acc = 0.0
    for i in range(0, len(pixels), 4):
        acc += 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2]
    return acc / max(n, 1)


def render_still(sc, world, sky, path, engine, hero, stage):
    """Gallery still: 8 deg | 55 deg diptych of the gnomon under the sky.

    Returns an exit code: 0, 10 (framing), 12 (clipped highlights), 9 (no file).
    """
    import gallery_framing

    cam = _stage_for_still(sc, world, sky, ELEV_LOW)
    sc.render.resolution_x, sc.render.resolution_y = PANEL_W, PANEL_H
    sc.render.resolution_percentage = 100
    # Each panel is its own frame: the gnomon must fill it and clear its edges.
    code = gallery_framing.check_framing(sc, cam, hero=hero, elements=hero, stage=stage)
    if code:
        return code

    tmp = tempfile.mkdtemp(prefix="sky_still_")
    try:
        left = os.path.join(tmp, "low.png")
        right = os.path.join(tmp, "high.png")
        _render_panel(sc, left, engine, samples=STILL_SAMPLES)
        _stage_for_still(sc, world, sky, ELEV_HIGH)
        _render_panel(sc, right, engine, samples=STILL_SAMPLES)
        w, h, px, left_px, right_px = _diptych(left, right)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for label, p in (("8deg", left_px), ("55deg", right_px)):
        print(f"panel {label}: mean_luma={mean_luma(p):.3f} clip={clip_fraction(p):.6f}")
    clipped = clip_fraction(px)
    print(f"clip_fraction={clipped:.6f} (gate<={CLIP_MAX_FRACTION}) strength={STILL_STRENGTH}")
    if clipped > CLIP_MAX_FRACTION:
        print(
            f"ERROR: {clipped:.4%} of the still clips to white under Standard — "
            f"lower the sky Background Strength",
            file=sys.stderr,
        )
        return EXIT_CLIPPED

    canvas = bpy.data.images.new("Diptych", width=w, height=h, alpha=False)
    try:
        canvas.pixels = px
        canvas.filepath_raw = path
        canvas.file_format = "PNG"
        canvas.save()
    finally:
        bpy.data.images.remove(canvas)
    return 0 if os.path.exists(path) and os.path.getsize(path) > 0 else 9


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    world, sky, bg = build_sky_world(ELEV_LOW)
    sc.world = world
    ground, plaza = build_ground(sc)
    hero, meridian = build_gnomon(sc)
    stage = [ground, plaza, meridian]
    return sc, world, sky, bg, hero, stage


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
    p.add_argument(
        "--unlink-sky",
        action="store_true",
        help="falsifier: drop Sky→Background link, still assert the chain",
    )
    args = p.parse_args(argv)

    print(f"binary version: {bpy.app.version} ({bpy.app.version_string})")
    sc, world, sky, bg, hero, stage = build_scene()
    code = check(sc, world, sky, bg, unlink_sky=args.unlink_sky)
    if code:
        return code

    if args.output:
        code = render_still(
            sc, world, sky, os.path.abspath(args.output), args.engine, hero, stage,
        )
        if code == 9:
            print("ERROR: render produced no file", file=sys.stderr)
        if code:
            return code
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
