"""Procedural-materials swatch grid -- a runnable BDT example.

Renders a 3x2 grid of spheres, one per material, demonstrating the
`procedural-materials-and-shaders` patterns end to end: Principled BSDF (metal +
dielectric), the emission pattern, the cross-version `set_specular` shim, string socket
lookups, and 4-tuple colors. It also doubles as a live proof of the EEVEE engine-id fix:
the version-branch helper resolves `BLENDER_EEVEE` on Blender 5.x and `BLENDER_EEVEE_NEXT`
on 4.2-4.5, and the chosen id is asserted against the build before rendering.

Run headless:
    blender --background --python swatch_grid.py -- --output swatch.png
    blender --background --python swatch_grid.py -- --output s.png --engine cycles --samples 8 --width 640

Dependency-light and deterministic (fixed camera/layout, no HDRI, no network). Exits
non-zero on any failure, including a render that comes out black or without the expected
number of distinct swatch regions.
"""
import bpy
import bmesh
import sys
import os
import math
import argparse
import numpy as np

GRID_COLS, GRID_ROWS = 3, 2
MATERIAL_COUNT = GRID_COLS * GRID_ROWS  # 6


# --- patterns copied from the procedural-materials-and-shaders skill ---
def get_eevee_engine_id():
    """EEVEE id: 'BLENDER_EEVEE' on 5.0+, 'BLENDER_EEVEE_NEXT' on 4.2-4.5."""
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def set_specular(bsdf, value):
    """'Specular' was renamed to 'Specular IOR Level' in Blender 4.0; support both."""
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = value
        return 'Specular IOR Level'
    if 'Specular' in bsdf.inputs:
        bsdf.inputs['Specular'].default_value = value
        return 'Specular'
    return None


def make_principled(name, base_color, metallic, roughness, specular=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = base_color
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    resolved = set_specular(bsdf, specular) if specular is not None else None
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat, resolved


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


def build_materials():
    """Return a list of (material, label) covering metal, dielectric, emissive, and the
    set_specular shim. The list order maps left-to-right, top-to-bottom across the grid."""
    mats, specular_socket = [], None
    m, specular_socket = make_principled("Gold", (1.00, 0.77, 0.34, 1), 1.0, 0.15)
    mats.append(m)
    m, _ = make_principled("Copper", (0.95, 0.64, 0.54, 1), 1.0, 0.28)
    mats.append(m)
    m, sr = make_principled("RedPlastic", (0.80, 0.05, 0.05, 1), 0.0, 0.40, specular=0.5)
    mats.append(m)
    specular_socket = specular_socket or sr
    m, _ = make_principled("BluePlastic", (0.05, 0.20, 0.80, 1), 0.0, 0.30, specular=0.5)
    mats.append(m)
    mats.append(make_emissive("EmissiveOrange", (1.0, 0.35, 0.05, 1), 6.0))
    m, _ = make_principled("WhiteRough", (0.90, 0.90, 0.92, 1), 0.0, 0.70, specular=0.3)
    mats.append(m)
    return mats, specular_socket


def build_scene(mats):
    xs = [-2.2, 0.0, 2.2]
    zs = [1.1, -1.1]
    i = 0
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            me = bpy.data.meshes.new(f"S{i}")
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=0.92)
            bm.to_mesh(me)
            bm.free()
            for poly in me.polygons:
                poly.use_smooth = True
            ob = bpy.data.objects.new(f"S{i}", me)
            ob.location = (xs[c], 0.0, zs[r])
            bpy.context.collection.objects.link(ob)
            ob.data.materials.append(mats[i])
            i += 1
    # ortho camera framed exactly on the grid cells
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = 'ORTHO'
    cam_d.ortho_scale = 6.6
    cam = bpy.data.objects.new("cam", cam_d)
    cam.location = (0.0, -10.0, 0.0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    aim = bpy.data.objects.new("Aim", None)
    bpy.context.collection.objects.link(aim)
    for lname, loc, energy in [("KeyL", (-5, -6, 4), 1500), ("FillL", (5, -6, -2), 700)]:
        ld = bpy.data.lights.new(lname, 'AREA')
        ld.energy = energy
        ld.size = 5.0
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        bpy.context.collection.objects.link(lo)
        con = lo.constraints.new('TRACK_TO')
        con.target = aim
        con.track_axis = 'TRACK_NEGATIVE_Z'
        con.up_axis = 'UP_Y'
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.03, 0.035, 1)
    bpy.context.scene.world = world


def verify_png(path):
    """Honest capture: not uniformly black AND distinct swatch regions == MATERIAL_COUNT."""
    img = bpy.data.images.load(path)
    w, h = img.size
    arr = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[..., :3]
    gmax = float(arr.max())
    cw, ch, ph = w // GRID_COLS, h // GRID_ROWS, 24
    means = []
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            cx, cy = c * cw + cw // 2, r * ch + ch // 2
            means.append(arr[cy - ph:cy + ph, cx - ph:cx + ph, :].reshape(-1, 3).mean(axis=0))
    kept = []
    for cm in means:
        if all(np.linalg.norm(cm - k) > 0.10 for k in kept):
            kept.append(cm)
    return gmax, len(kept)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description="Render a procedural-materials swatch grid.")
    p.add_argument("--output", required=True, help="Output PNG path")
    p.add_argument("--engine", choices=["auto", "eevee", "cycles"], default="auto",
                   help="auto/eevee use the version-correct EEVEE id; cycles for GPU-less hosts")
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--no-verify", action="store_true")
    args = p.parse_args(argv)

    # Empty the factory file FIRST so the materials we create below survive.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats, specular_socket = build_materials()
    build_scene(mats)

    sc = bpy.context.scene
    # EEVEE engine-id proof: frame-independent, must hold even when we render with Cycles.
    eid = get_eevee_engine_id()
    expected = 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'
    sc.render.engine = eid
    if sc.render.engine != expected:
        print(f"ERROR: EEVEE id helper returned '{eid}', engine is '{sc.render.engine}', "
              f"expected '{expected}'", file=sys.stderr)
        return 5
    print(f"eevee_engine_id={eid} (expected {expected}) OK; set_specular resolved '{specular_socket}'")

    render_engine = 'CYCLES' if args.engine == 'cycles' else eid
    sc.render.engine = render_engine
    if render_engine == 'CYCLES':
        sc.cycles.samples = args.samples
    else:
        sc.eevee.taa_render_samples = args.samples
    sc.render.resolution_x = args.width
    sc.render.resolution_y = int(args.width * 9 / 16)
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = args.output
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(args.output) and os.path.getsize(args.output) > 0):
        print("ERROR: no output written", file=sys.stderr)
        return 4
    print(f"rendered {args.output} with {render_engine} ({os.path.getsize(args.output)} bytes)")

    if not args.no_verify:
        gmax, regions = verify_png(args.output)
        non_black = gmax > 0.05
        regions_ok = regions == MATERIAL_COUNT
        print(f"verify: max_pixel={gmax:.3f} non_black={non_black} "
              f"distinct_regions={regions} materials={MATERIAL_COUNT} ok={regions_ok}")
        if not (non_black and regions_ok):
            print("ERROR: render failed verification (black or wrong region count)", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # blender exits 0 on an uncaught traceback; force non-zero
        import traceback
        traceback.print_exc()
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
