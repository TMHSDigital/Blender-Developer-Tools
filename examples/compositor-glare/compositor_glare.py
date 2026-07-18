"""Bloom through the compositor across the 4.x -> 5.x boundary — a runnable example.

Witnesses the compositor-plumbing contract that AI-generated Blender code breaks
constantly:

- Blender 5.x removed `scene.node_tree` / `scene.use_nodes`: the scene compositor
  is now a node GROUP assigned to `scene.compositing_node_group`, with an
  `Image` output declared via `tree.interface.new_socket`. The old one-liner
  `scene.use_nodes = True` raises AttributeError on 5.x.
- The Glare node itself changed shape: on 4.x it is configured with legacy enum
  properties (`glare_type='FOG_GLOW'`, `quality='HIGH'`, `size=6`); on 5.x the
  same choices are menu/float INPUT sockets (`inputs['Type'].default_value =
  'Fog Glow'`). The legacy `threshold` property is a dead shim on 4.x — the real
  threshold lives in the `Threshold` input socket on BOTH versions.
- EEVEE has no `use_bloom` toggle on either version (removed in 4.2). Bloom is
  a compositor node, and the check proves it with pixels: a halo appears beyond
  the ring silhouette, falls off strictly with distance, and vanishes entirely
  when `scene.render.use_compositing` is off.

By default it runs only the correctness check (two 96x54 single-sample Cycles
renders, compositor on vs off) — the CI smoke check. Pass --output to also
render a still:

    blender --background --python compositor_glare.py --                 # check only
    blender --background --python compositor_glare.py -- --output n.png  # + render
"""
import bpy
import sys
import os
import math
import tempfile
import argparse
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

RING_MAJOR = 0.7
RING_MINOR = 0.12
RING_Z = 0.85                # ring center height; bottom edge grazes the floor
RING_SPECS = (               # three neon rings standing in the XZ plane (name, x, y, color, strength)
    ("RingViolet", -1.55, 0.55, (0.55, 0.15, 1.0, 1.0), 12.0),
    ("RingCyan",    0.0,  0.0,  (0.10, 0.90, 1.0, 1.0), 18.0),  # the ring the check samples
    ("RingAmber",   1.55, 0.45, (1.00, 0.45, 0.08, 1.0), 9.0),
)

CHECK_W, CHECK_H = 96, 54    # tiny, noise-free: 1-sample Cycles, pure emission


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def make_emissive(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    emis = nt.nodes.new('ShaderNodeEmission')
    emis.inputs['Color'].default_value = color
    emis.inputs['Strength'].default_value = strength
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(emis.outputs['Emission'], out.inputs['Surface'])
    return mat


def configure_fog_glow(glare):
    """Same Fog Glow on both sides of the 5.0 compositor rewrite.

    4.x: legacy enum properties; `size` is the old kernel int and the real
    threshold is the `Threshold` input socket (the `threshold` property is a
    dead shim — it always reads 0.0 on 4.5).
    5.x: `glare_type`/`quality`/`size` properties are gone; Type and Quality
    are menu sockets that take their DISPLAY names, Size is a 0..1 factor.
    """
    if bpy.app.version >= (5, 0, 0):
        glare.inputs['Type'].default_value = 'Fog Glow'
        glare.inputs['Quality'].default_value = 'High'
        glare.inputs['Size'].default_value = 0.85
    else:
        glare.glare_type = 'FOG_GLOW'
        glare.quality = 'HIGH'
        glare.size = 6
    glare.inputs['Threshold'].default_value = 1.0  # input socket on BOTH versions


def build_compositor(scene):
    """Wire Render Layers -> Glare (Fog Glow) -> output, cross-version.

    Returns (tree, glare_node). 5.x builds a compositor node group and assigns
    it to scene.compositing_node_group; 4.x uses the scene's own node tree.
    """
    if bpy.app.version >= (5, 0, 0):
        tree = bpy.data.node_groups.new("BloomComposite", 'CompositorNodeTree')
        tree.interface.new_socket(name="Image", in_out='INPUT', socket_type='NodeSocketColor')
        tree.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
        out_node = tree.nodes.new("NodeGroupOutput")
        scene.compositing_node_group = tree
    else:
        scene.use_nodes = True
        tree = scene.node_tree
        tree.nodes.clear()
        out_node = tree.nodes.new("CompositorNodeComposite")
    rl = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    configure_fog_glow(glare)
    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], out_node.inputs["Image"])
    return tree, glare


def build_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    for name, x, y, color, strength in RING_SPECS:
        bpy.ops.mesh.primitive_torus_add(
            major_radius=RING_MAJOR, minor_radius=RING_MINOR,
            major_segments=64, minor_segments=16,
            location=(x, y, RING_Z), rotation=(math.radians(90), 0.0, 0.0))
        ring = bpy.context.active_object
        ring.name = name
        ring.data.materials.append(make_emissive(f"Neon{name[4:]}", color, strength))
        for poly in ring.data.polygons:
            poly.use_smooth = True

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    scene.world = world

    cam_data = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_data)
    # level, centered camera: the top silhouette of the middle ring is exactly
    # (0, 0, RING_Z + RING_MAJOR + RING_MINOR) with pure black world above it
    cam.location = (0.0, -6.0, RING_Z)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    tree, glare = build_compositor(scene)
    bpy.context.view_layer.update()
    return scene, tree, glare


def link_chain_ok(tree, glare, out_node):
    """Every hop Render Layers -> Glare -> output must be a real link."""
    rl = next((n for n in tree.nodes if n.bl_idname == "CompositorNodeRLayers"), None)
    if rl is None:
        return False
    hop1 = any(l.from_node == rl and l.to_node == glare for l in tree.links)
    hop2 = any(l.from_node == glare and l.to_node == out_node for l in tree.links)
    return hop1 and hop2


def check_structure(scene, tree, glare):
    is_5x = bpy.app.version >= (5, 0, 0)
    # the divergence itself: scene.node_tree exists only on 4.x
    if hasattr(scene, "node_tree") == is_5x:
        print(f"ERROR: scene.node_tree presence {hasattr(scene, 'node_tree')} "
              f"contradicts version {bpy.app.version_string}", file=sys.stderr)
        return 3
    if is_5x:
        if scene.compositing_node_group != tree:
            print("ERROR: compositing_node_group is not the tree we built", file=sys.stderr)
            return 3
        outs = [s for s in tree.interface.items_tree
                if getattr(s, "in_out", None) == 'OUTPUT' and s.name == "Image"]
        if not outs:
            print("ERROR: compositor group has no Image output socket", file=sys.stderr)
            return 3
        out_node = next(n for n in tree.nodes if n.bl_idname == "NodeGroupOutput")
        if glare.inputs['Type'].default_value != 'Fog Glow':
            print("ERROR: 5.x Glare Type menu is not 'Fog Glow'", file=sys.stderr)
            return 3
    else:
        out_node = next(n for n in tree.nodes if n.bl_idname == "CompositorNodeComposite")
        if not (glare.glare_type == 'FOG_GLOW' and glare.quality == 'HIGH' and glare.size == 6):
            print("ERROR: 4.x Glare legacy properties not as configured", file=sys.stderr)
            return 3
    if glare.inputs['Threshold'].default_value != 1.0:
        print("ERROR: Glare Threshold input != 1.0", file=sys.stderr)
        return 3
    if not link_chain_ok(tree, glare, out_node):
        print("ERROR: Render Layers -> Glare -> output link chain broken", file=sys.stderr)
        return 3
    # negative witness: bloom cannot come from EEVEE on either version
    if getattr(getattr(scene, "eevee", None), "use_bloom", None) is not None:
        print("ERROR: unexpected EEVEE use_bloom toggle — the example's premise is stale",
              file=sys.stderr)
        return 3
    return 0


def render_frame(scene, path, use_compositing):
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    scene.render.resolution_x = CHECK_W
    scene.render.resolution_y = CHECK_H
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.use_compositing = use_compositing
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def sample_column(scene, path):
    """Luminance (R+G+B) on the middle ring's tube, then marching up in image
    space from its top silhouette pixel: the halo profile of the bloom kernel."""
    img = bpy.data.images.load(path)
    w, h = img.size
    if (w, h) != (CHECK_W, CHECK_H):
        bpy.data.images.remove(img)
        raise RuntimeError(f"reloaded {path} at {(w, h)}, expected {(CHECK_W, CHECK_H)}")
    px = img.pixels[:]
    bpy.data.images.remove(img)

    def lum(x, y):
        x, y = max(0, min(w - 1, x)), max(0, min(h - 1, y))
        i = (y * w + x) * 4
        return px[i] + px[i + 1] + px[i + 2]

    def project(co):
        ndc = world_to_camera_view(scene, scene.camera, Vector(co))
        return int(ndc.x * w), int(ndc.y * h)

    on_x, on_y = project((0.0, 0.0, RING_Z + RING_MAJOR))            # on the tube
    sil_x, sil_y = project((0.0, 0.0, RING_Z + RING_MAJOR + RING_MINOR))  # silhouette
    return (lum(on_x, on_y), [lum(sil_x, sil_y + d) for d in (1, 2, 3)])


def check_pixels(scene):
    tmp = tempfile.mkdtemp(prefix="compositor_glare_")
    try:
        on_path = os.path.join(tmp, "on.png")
        off_path = os.path.join(tmp, "off.png")
        if not render_frame(scene, on_path, True):
            print("ERROR: compositor-on check render produced no file", file=sys.stderr)
            return 4
        if not render_frame(scene, off_path, False):
            print("ERROR: compositor-off check render produced no file", file=sys.stderr)
            return 4
        tube_on, halo_on = sample_column(scene, on_path)
        tube_off, halo_off = sample_column(scene, off_path)

        if tube_on < 1.5 or tube_off < 1.5:
            print(f"ERROR: ring tube not bright (on={tube_on:.3f} off={tube_off:.3f})",
                  file=sys.stderr)
            return 4
        if halo_on[0] < 0.10:
            print(f"ERROR: no bloom halo beyond the silhouette (halo+1px={halo_on[0]:.3f})",
                  file=sys.stderr)
            return 4
        if not (halo_on[0] > halo_on[1] > halo_on[2]):
            print(f"ERROR: halo does not fall off strictly: "
                  f"{['%.3f' % v for v in halo_on]}", file=sys.stderr)
            return 4
        if max(halo_off) > 0.02:
            print(f"ERROR: halo present WITHOUT the compositor "
                  f"({['%.3f' % v for v in halo_off]}) — bloom is not from the Glare node",
                  file=sys.stderr)
            return 5
        print(f"pixels: tube={tube_on:.3f} halo(+1/+2/+3px)="
              f"{'/'.join('%.3f' % v for v in halo_on)} "
              f"compositor-off halo max={max(halo_off):.3f}")
        return 0
    finally:
        for f in ("on.png", "off.png"):
            p = os.path.join(tmp, f)
            if os.path.exists(p):
                os.remove(p)
        os.rmdir(tmp)


def render_still(scene, path, engine, samples, width):
    """Dark-studio beauty pass: the same rings, now grounded on a reflective
    floor — the glow and its reflection are the compositor's doing."""
    # glossy dark floor stays below the bloom threshold; only the rings bloom
    mesh = bpy.data.meshes.new("Floor")
    half = 30.0
    mesh.from_pydata([(-half, -half, 0.0), (half, -half, 0.0),
                      (half, half, 0.0), (-half, half, 0.0)], [], [(0, 1, 2, 3)])
    fmat = bpy.data.materials.new("Studio")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.04, 0.045, 0.055, 1.0)
    fb.inputs["Roughness"].default_value = 0.25
    fb.inputs["Metallic"].default_value = 0.6
    mesh.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", mesh)
    scene.collection.objects.link(floor)

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", (-4.5, -4.0, 5.5), 500.0, 6.0, (0.85, 0.9, 1.0), (50, 0, -30))
    light("Fill", (4.5, -3.0, 2.5), 300.0, 8.0, (1.0, 0.85, 0.7), (65, 0, 40))

    # a slightly elevated, centered camera for the still — all three rings in
    # frame with headroom for the glow, floor reflection anchoring the bottom
    cam = scene.camera
    cam.location = (0.0, -8.4, 2.0)
    cam.rotation_euler = (math.radians(79), 0.0, 0.0)

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
    else:
        try:
            scene.eevee.taa_render_samples = samples
            scene.eevee.use_raytracing = True
        except AttributeError:
            pass
    scene.render.resolution_x = width
    scene.render.resolution_y = int(width * 9 / 16)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'WEBP' if path.lower().endswith(".webp") else 'PNG'
    scene.render.use_compositing = True
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still here (.png or .webp)")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--samples", type=int, default=32, help="--output sample count")
    p.add_argument("--width", type=int, default=1280, help="--output width; height is width*9/16")
    args = p.parse_args(argv)

    scene, tree, glare = build_scene()
    code = check_structure(scene, tree, glare)
    if code:
        return code
    print(f"structure OK on {bpy.app.version_string}: "
          f"{'compositing_node_group' if bpy.app.version >= (5, 0, 0) else 'scene.node_tree'} "
          f"-> Glare(Fog Glow) -> output; no EEVEE use_bloom")

    code = check_pixels(scene)
    if code:
        return code

    if args.output:
        if not render_still(scene, os.path.abspath(args.output), args.engine, args.samples,
                            args.width):
            print("ERROR: render produced no file", file=sys.stderr)
            return 6
        print(f"rendered still {args.output}")

    print("compositor-glare OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
