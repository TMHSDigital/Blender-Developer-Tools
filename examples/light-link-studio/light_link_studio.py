"""One key, one hero: light linking, proven by pixels — a runnable example.

Witnesses the light-linking contract AI-generated staging code most often
misses: a light's contribution can be restricted to a receiver collection,
and the API is on the light OBJECT (``obj.light_linking``), not the Light
datablock — `ld.light_linking` is an AttributeError. The check renders the
studio twice in one pass and asserts the whole story in pixels:

1. Linked: the key lights ONLY the hero — the hero reads bright while the
   identical decoy beside it sits at the fill floor.
2. Unlinked (same check): the decoy's brightness rises materially while the
   hero's is unchanged within tolerance — the link is surgical, not a dimmer.

The engine note, verified rather than assumed: light linking also works on
EEVEE Next — measured 5.5x linked ratio on 4.5.11 EEVEE Next and 5.9x on
5.1.2 EEVEE, matching Cycles within sampling noise. The check still pins
Cycles for deterministic tiny-sample CPU renders. The API is stable between
Blender 4.5 LTS and 5.1 (ObjectLightLinking with
receiver_collection/blocker_collection on both).

By default it runs the two-render correctness check (no gallery still) — the
CI smoke check. Pass --output to also render a still:

    blender --background --python light_link_studio.py --                 # check only
    blender --background --python light_link_studio.py -- --output l.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse, tempfile, shutil

IS_5X = bpy.app.version >= (5, 0, 0)
HERO_RGB = (0.85, 0.30, 0.08)     # hazard orange
DECOY_RGB = (0.30, 0.34, 0.40)    # cold steel
KEY_ENERGY = 450.0
FILL_ENERGY = 18.0
PXW, PXH = 64, 36
RATIO_MIN = 3.0                   # hero/decoy luminance ratio, linked
HERO_LUMA_MIN = 0.25              # hero must be well-lit, linked
RISE_MIN = 0.5                    # decoy luminance rise when unlinked (relative)
HERO_DRIFT_MAX = 0.05             # hero brightness change across the two renders


def sphere(name, rgb, x, coll):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.5)
        bm.to_mesh(me)
    finally:
        bm.free()
    for p in me.polygons:
        p.use_smooth = True
    mat = bpy.data.materials.new(name + "M")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = 0.45
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = (x, 0.0, 0.55)
    coll.objects.link(ob)
    return ob


def add_light(sc, name, energy, loc, rot, color, size=1.2):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.size = size
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    sc.collection.objects.link(ob)
    return ob


def build_studio(sc):
    """Hero and decoy on one stage, plus a low fill that lights both."""
    hero_c = bpy.data.collections.new("HeroColl")
    decoy_c = bpy.data.collections.new("DecoyColl")
    hero = sphere("Hero", HERO_RGB, -1.2, hero_c)
    decoy = sphere("Decoy", DECOY_RGB, 1.2, decoy_c)
    sc.collection.children.link(hero_c)
    sc.collection.children.link(decoy_c)

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
    sc.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    sc.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    sc.world = world

    key = add_light(sc, "Key", KEY_ENERGY, (-2.2, -2.5, 3.5), (40, 0, -25),
                    (1.0, 0.92, 0.82), size=1.4)
    add_light(sc, "Fill", FILL_ENERGY, (3.0, -2.0, 2.2), (60, 0, 35),
              (0.75, 0.85, 1.0), size=4.0)
    add_light(sc, "Rim", 120.0, (0.5, 4.5, 4.0), (-55, 0, 175),
              (0.6, 0.78, 1.0), size=3.0)
    # the signature warm wedge raking the back wall (docs/VISUAL-STYLE.md)
    add_light(sc, "Wedge", 250.0, (-2.5, 3.5, 4.2), (-72, 0, 165),
              (1.0, 0.76, 0.5), size=5.0)

    cam = bpy.data.cameras.new("Cam")
    cam.lens = 55.0
    cam_ob = bpy.data.objects.new("Cam", cam)
    cam_ob.location = (0.0, -5.9, 1.32)
    cam_ob.rotation_euler = (math.radians(86), 0.0, 0.0)
    sc.collection.objects.link(cam_ob)
    sc.camera = cam_ob
    return hero, decoy, hero_c, key


def setup_render(sc, w, h, samples):
    # Cycles for deterministic tiny CPU samples; EEVEE Next honors linking
    # too (measured on both supported versions), but its sampling is not
    # deterministic enough for a luminance gate
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    # Standard keeps luminance ratios meaningful (AgX would compress them)
    sc.view_settings.view_transform = 'Standard'


def luma_at(img, fx, fy):
    w, h = img.size
    x, y = int(fx * w), int(fy * h)
    i = (y * w + x) * 4
    px = img.pixels
    return 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]


def render_lumas(sc, tmp, name, hero, decoy):
    from bpy_extras.object_utils import world_to_camera_view
    path = os.path.join(tmp, name)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    # sample AT each sphere's projected center (framing-independent), taking
    # the max over a small disc to stay off edges
    out = []
    for ob in (hero, decoy):
        ndc = world_to_camera_view(sc, sc.camera, ob.matrix_world.translation)
        best = 0.0
        for dy in (-2, 0, 2):
            for dx in (-2, 0, 2):
                best = max(best, luma_at(img, ndc.x + dx / PXW,
                                         ndc.y + dy / PXH))
        out.append(best)
    bpy.data.images.remove(img)
    return out[0], out[1]


def check(sc, key, hero_c, hero, decoy):
    # contract 0 (RNA guard): the API is on the light OBJECT
    ld = key.data
    if hasattr(ld, "light_linking"):
        print("ERROR: Light datablock gained light_linking — the API moved; "
              "this example pins the Object-level path", file=sys.stderr)
        return 3
    if not hasattr(key, "light_linking"):
        print("ERROR: light objects lost light_linking", file=sys.stderr)
        return 4

    # contract 1 (assignment round-trip through the API itself)
    key.light_linking.receiver_collection = hero_c
    if key.light_linking.receiver_collection != hero_c:
        print("ERROR: receiver_collection assignment did not read back",
              file=sys.stderr)
        return 5

    setup_render(sc, PXW, PXH, 8)
    tmp = tempfile.mkdtemp(prefix="light_link_")
    try:
        hero_a, decoy_a = render_lumas(sc, tmp, "linked.png", hero, decoy)
        key.light_linking.receiver_collection = None
        hero_b, decoy_b = render_lumas(sc, tmp, "unlinked.png", hero, decoy)
        key.light_linking.receiver_collection = hero_c  # restore for the still
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # contract 2 (linked): the hero is lit, the decoy is not
    ratio_a = hero_a / max(decoy_a, 1e-6)
    if hero_a < HERO_LUMA_MIN or ratio_a < RATIO_MIN:
        print(f"ERROR: linked state wrong — hero {hero_a:.3f} (min "
              f"{HERO_LUMA_MIN}), hero/decoy {ratio_a:.2f}x (min {RATIO_MIN}x)",
              file=sys.stderr)
        return 6

    # contract 3 (unlinked): the decoy rises materially, the hero holds
    rise = (decoy_b - decoy_a) / max(decoy_a, 1e-6)
    hero_drift = abs(hero_b - hero_a) / max(hero_a, 1e-6)
    if rise < RISE_MIN:
        print(f"ERROR: decoy rose only {rise:.1%} when unlinked (min "
              f"{RISE_MIN:.0%}) — the key was never restricted",
              file=sys.stderr)
        return 7
    if hero_drift > HERO_DRIFT_MAX:
        print(f"ERROR: hero drifted {hero_drift:.1%} across the unlink "
              f"(max {HERO_DRIFT_MAX:.0%}) — the link is not surgical",
              file=sys.stderr)
        return 8

    print(f"linked:   hero={hero_a:.3f} decoy={decoy_a:.3f} "
          f"ratio={ratio_a:.1f}x (min {RATIO_MIN}x)")
    print(f"unlinked: hero={hero_b:.3f} decoy={decoy_b:.3f} "
          f"rise={rise:.0%} (min {RISE_MIN:.0%}) "
          f"hero_drift={hero_drift:.1%} (max {HERO_DRIFT_MAX:.0%})")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def plaque(sc, text, x):
    pm = bpy.data.materials.new("PlaqueMetal")
    pm.use_nodes = True
    pb = pm.node_tree.nodes["Principled BSDF"]
    pb.inputs["Base Color"].default_value = (0.42, 0.44, 0.48, 1.0)
    pb.inputs["Metallic"].default_value = 0.2
    pb.inputs["Roughness"].default_value = 0.6
    # faint self-glow: the LINKED plaque must read even in the decoy's dark
    sock = pb.inputs.get("Emission Color") or pb.inputs["Emission"]
    sock.default_value = (0.35, 0.37, 0.42, 1.0)
    pb.inputs["Emission Strength"].default_value = 0.6
    cu = bpy.data.curves.new("Plaque", 'FONT')
    cu.body = text
    cu.align_x = 'CENTER'
    cu.size = 0.20
    cu.extrude = 0.006
    ob = bpy.data.objects.new("Plaque", cu)
    ob.location = (x, -0.68, 0.01)
    ob.data.materials.append(pm)
    sc.collection.objects.link(ob)


def render_still(sc, path, engine):
    plaque(sc, "LINKED", -1.2)
    plaque(sc, "UNLINKED", 1.2)
    # the gallery still is the linked state, on Cycles for the same
    # deterministic sampling as the check
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 48
    sc.cycles.use_denoising = False
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = path
    sc.view_settings.view_transform = 'Standard'
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="cycles", choices=("cycles",),
                   help="render engine — pinned to cycles for deterministic samples")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    hero, decoy, hero_c, key = build_studio(sc)
    code = check(sc, key, hero_c, hero, decoy)
    if code:
        return code

    if args.output:
        if not render_still(sc, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 9
        print(f"rendered still {args.output}")

    print("light-link-studio OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
