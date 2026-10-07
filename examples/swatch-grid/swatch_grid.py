"""Procedural-materials swatch grid -- a runnable BDT example.

Renders a tiered 3x2 display of material spheres on plinths, one per material, demonstrating the
`procedural-materials-and-shaders` patterns end to end: Principled BSDF (metal +
dielectric), the emission pattern, the cross-version `set_specular` shim, string socket
lookups, and 4-tuple colors. It also doubles as a live proof of the EEVEE engine-id fix:
the version-branch helper resolves `BLENDER_EEVEE` on Blender 5.x and `BLENDER_EEVEE_NEXT`
on 4.2-4.5, and the chosen id is asserted against the build before rendering.

By default it runs only the correctness check (no render) — the CI smoke check.
Pass --output to also render and pixel-verify a still. ``--same-base`` writes
the same RGB to every swatch. That is the falsifier: with --output (as smoke
runs it) the rendered six-region check fails (exit 6) before any read-back of
the colors; without --output the material-value check is all there is (exit 3).
``--invert-engine-id`` (exit 5) and ``--no-specular-shim`` (exit 7) falsify the
engine-id and set_specular witnesses.

    blender --background --python swatch_grid.py --                       # check only
    blender --background --python swatch_grid.py -- --same-base            # must fail
    blender --background --python swatch_grid.py -- --output swatch.png
    blender --background --python swatch_grid.py -- --output s.png --engine cycles --samples 8 --width 640

Dependency-light and deterministic (fixed camera/layout, no HDRI, no network). Exits
non-zero on any failure, including a render that comes out black or without the expected
number of distinct swatch regions.
"""
import bpy
import bmesh

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), _os.pardir))
_sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
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


def naive_set_specular(bsdf, value):
    """The pre-4.0 habit ``--no-specular-shim`` models: write the legacy
    ``Specular`` socket when it exists, otherwise silently do nothing."""
    if 'Specular' in bsdf.inputs:
        bsdf.inputs['Specular'].default_value = value
        return 'Specular'
    return None


def make_principled(name, base_color, metallic, roughness, specular=None,
                    setter=set_specular):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = base_color
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    resolved = setter(bsdf, specular) if specular is not None else None
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat, resolved


def make_emissive(name, color, strength, shell_color=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    emis = nt.nodes.new('ShaderNodeEmission')
    emis.inputs['Color'].default_value = color
    emis.inputs['Strength'].default_value = strength
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    if shell_color is None:
        nt.links.new(emis.outputs['Emission'], out.inputs['Surface'])
        return mat
    # A glowing core inside a darker shell: the emission owns the face that
    # looks at the camera and hands over to a deep, matte dielectric toward
    # the silhouette. The sphere keeps a limb and a rim instead of rendering
    # as one flat disk of constant radiance, and nothing has to clip to glow.
    shell = nt.nodes.new('ShaderNodeBsdfPrincipled')
    shell.inputs['Base Color'].default_value = shell_color
    shell.inputs['Roughness'].default_value = 0.45
    set_specular(shell, 0.2)
    facing = nt.nodes.new('ShaderNodeLayerWeight')
    facing.inputs['Blend'].default_value = 0.8
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[1].position = 0.9
    nt.links.new(facing.outputs['Facing'], ramp.inputs['Fac'])
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(ramp.outputs['Color'], mix.inputs['Fac'])
    nt.links.new(emis.outputs['Emission'], mix.inputs[1])
    nt.links.new(shell.outputs['BSDF'], mix.inputs[2])
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])
    return mat


def build_materials(setter=set_specular):
    """Return a list of (material, label) covering metal, dielectric, emissive, and the
    set_specular shim. The list order maps left-to-right, top-to-bottom across the grid."""
    mats, specular_socket = [], None
    # polished vs brushed: the roughness gap is what separates the two metals
    # on the dark stage -- their sampled patch means must stay > 0.10 apart
    # for verify_png, and a mirror finish vs a broad soft highlight does it
    m, specular_socket = make_principled("Gold", (1.00, 0.77, 0.34, 1), 1.0, 0.08)
    mats.append(m)
    m, _ = make_principled("Copper", (0.92, 0.47, 0.36, 1), 1.0, 0.62)
    mats.append(m)
    m, sr = make_principled("RedPlastic", (0.80, 0.05, 0.05, 1), 0.0, 0.40, specular=0.5,
                            setter=setter)
    mats.append(m)
    specular_socket = specular_socket or sr
    m, _ = make_principled("BluePlastic", (0.05, 0.20, 0.80, 1), 0.0, 0.30, specular=0.5,
                           setter=setter)
    mats.append(m)
    # Standard does not compress highlights, so the core radiance stays under
    # 1.0 in every channel: at 1.4 the red channel clipped across the whole
    # face and the swatch read as a flat orange disk with no form
    mats.append(make_emissive("EmissiveOrange", (1.0, 0.35, 0.05, 1), 0.95,
                              shell_color=(0.22, 0.035, 0.006, 1)))
    m, _ = make_principled("WhiteRough", (0.90, 0.90, 0.92, 1), 0.0, 0.70, specular=0.3,
                           setter=setter)
    mats.append(m)
    return mats, specular_socket


SPHERE_R = 0.5
COL_X = (-1.62, 0.0, 1.62)
# (y, plinth height) per row: the back row stands on tall plinths so every
# sphere clears the one in front of it -- a tiered library display, read
# left to right, back row first
ROWS = ((1.25, 1.02), (-0.35, 0.34))


def make_cylinder(name, radius, height, bevel, segments=64):
    """A capped cylinder standing on z=0 with bevelled rims: flat caps,
    smooth walls, sharp cap seams, so it reads machined, not primitive."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                              radius1=radius, radius2=radius, depth=height)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0.0, 0.0, height / 2))
        bm.normal_update()
        rims = [e for e in bm.edges if not e.is_boundary and len(e.link_faces) == 2
                and abs(e.link_faces[0].normal.z) != abs(e.link_faces[1].normal.z)]
        bmesh.ops.bevel(bm, geom=rims, offset=bevel, segments=4, profile=0.5,
                        affect='EDGES')
        bm.normal_update()
        for f in bm.faces:
            f.smooth = abs(f.normal.z) < 0.999
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.link_faces[0].smooth != e.link_faces[1].smooth:
                e.smooth = False
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


LABELS = ("GOLD", "COPPER", "RED PLASTIC", "BLUE PLASTIC", "EMISSIVE", "WHITE ROUGH")
TIER_DEPTH = 1.30      # front-to-back depth of each riser tier
TIER_HALF_W = 2.28     # half-width of the riser, past the outer spheres


def make_block(name, sx, sy, sz, bevel):
    """A bevelled box standing on z=0, centred on x/y."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= sx
            v.co.y *= sy
            v.co.z = (v.co.z + 0.5) * sz
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=3, profile=0.5,
                        affect='EDGES', clamp_overlap=True)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.set_sharp_from_angle(angle=math.radians(40.0))
    return me


def make_walnut():
    """Oiled walnut: a stretched wave-texture grain over a noise-warped base."""
    mat = bpy.data.materials.new("Walnut")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.42
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.25, 1.0, 1.0)  # stretched: grain runs along X
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 3.0
    wave.bands_direction = 'Z'
    wave.inputs["Distortion"].default_value = 1.6
    wave.inputs["Detail"].default_value = 4.0
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.075, 0.037, 0.018, 1)
    ramp.color_ramp.elements[1].color = (0.13, 0.068, 0.034, 1)
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return mat


def make_plaque(name, text, loc, brass, ink):
    """A brass plaque tilted toward the camera with the material's name set
    into it: a bevelled plate plus an extruded text object riding its face."""
    import mathutils
    tilt = math.radians(58.0)                 # plate leans back, face up-and-forward
    plate = bpy.data.objects.new(name, make_block(name, 0.86, 0.20, 0.022, 0.006))
    plate.location = loc
    plate.rotation_euler = (tilt, 0.0, 0.0)
    plate.data.materials.append(brass)
    cu = bpy.data.curves.new(name + "Text", type='FONT')
    cu.body = text
    cu.size = 0.085
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.extrude = 0.0025
    cu.space_character = 1.12
    txt = bpy.data.objects.new(name + "Text", cu)
    txt.data.materials.append(ink)
    # ride the plate's top face: parent, then sit just proud of it
    txt.parent = plate
    txt.location = (0.0, 0.0, 0.0245)
    return plate, txt


def build_scene(mats):
    sc = bpy.context.scene
    coll = bpy.context.collection
    walnut = make_walnut()
    collar_mat, _ = make_principled("CollarGunmetal", (0.30, 0.30, 0.32, 1), 1.0, 0.32)
    brass, _ = make_principled("PlaqueBrass", (0.80, 0.58, 0.28, 1), 1.0, 0.30)
    ink, _ = make_principled("PlaqueInk", (0.02, 0.018, 0.016, 1), 0.0, 0.6)
    swatches, stands = [], []
    # a two-tier walnut riser: each row of spheres stands on its own tier, so
    # the back row clears the front one (tier tops at the old plinth heights)
    for r, (y, h) in enumerate(ROWS):
        tier = bpy.data.objects.new(f"Tier{r}", make_block(f"Tier{r}", 2 * TIER_HALF_W,
                                                             TIER_DEPTH, h, 0.03))
        tier.location = (0.0, y + (0.12 if r == 0 else 0.0), 0.0)
        tier.data.materials.append(walnut)
        coll.objects.link(tier)
        stands.append(tier)
    i = 0
    for r, (y, h) in enumerate(ROWS):
        for c, x in enumerate(COL_X):
            plaque, txt = make_plaque(f"Plaque{i}", LABELS[i],
                                      (x, y - 0.52, h + 0.06), brass, ink)
            coll.objects.link(plaque)
            coll.objects.link(txt)
            stands += [plaque, txt]
            collar = bpy.data.objects.new(f"Collar{i}", make_cylinder(f"Collar{i}", 0.30, 0.07, 0.02))
            collar.location = (x, y, h)
            collar.data.materials.append(collar_mat)
            me = bpy.data.meshes.new(f"Swatch{i}")
            bm = bmesh.new()
            try:
                bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=SPHERE_R)
                bm.to_mesh(me)
            finally:
                bm.free()
            me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
            ob = bpy.data.objects.new(f"Swatch{i}", me)
            # seated in the collar: the sphere rests on its rim, 0.4 in from
            # the equator, so it reads as mounted rather than balanced
            seat = h + 0.07 + math.sqrt(SPHERE_R ** 2 - 0.26 ** 2)
            ob.location = (x, y, seat)
            ob.data.materials.append(mats[i])
            for o in (collar, ob):
                coll.objects.link(o)
            swatches.append(ob)
            stands.append(collar)
            i += 1

    # default stage: floor + back wall share the studio material
    stage_me = bpy.data.meshes.new("Stage")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(stage_me)
    finally:
        bm.free()
    smat, _ = make_principled("Studio", (0.03, 0.032, 0.037, 1), 0.0, 0.7)
    stage_me.materials.append(smat)
    floor = bpy.data.objects.new("Floor", stage_me)
    coll.objects.link(floor)
    wall = bpy.data.objects.new("Wall", stage_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    coll.objects.link(wall)

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.45, 1.05)
    coll.objects.link(aim)
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 50.0
    cam = bpy.data.objects.new("cam", cam_d)
    cam.location = (0.0, -7.7, 4.5)
    coll.objects.link(cam)
    con = cam.constraints.new('TRACK_TO')
    con.target = aim
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    sc.camera = cam

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = col
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = tuple(math.radians(a) for a in rot)
        coll.objects.link(lo)

    # warm shaped key upper left, faint cool fill low right, cool rim behind,
    # and the warm wedge pooling on the back wall (docs/VISUAL-STYLE.md)
    light("Key", (-4.2, -4.6, 5.6), 330.0, 5.5, (1.0, 0.96, 0.9), (48, 0, -40))
    light("Fill", (5.0, -4.0, 2.2), 70.0, 9.0, (0.75, 0.85, 1.0), (70, 0, 52))
    light("Rim", (1.5, 4.5, 4.2), 110.0, 4.0, (0.6, 0.78, 1.0), (-52, 0, 172))
    light("Wedge", (1.0, 7.6, 3.4), 320.0, 5.0, (1.0, 0.76, 0.5), (0, 0, 0))
    # the camera looks down on the display, so the backdrop it sees is mostly
    # floor: the wedge pools there, just behind the back row, and stays off
    # the swatches themselves
    pool = bpy.data.objects.new("WedgePool", None)
    pool.location = (0.3, 4.9, 0.0)
    coll.objects.link(pool)
    wcon = bpy.data.objects["Wedge"].constraints.new('TRACK_TO')
    wcon.target = pool
    wcon.track_axis = 'TRACK_NEGATIVE_Z'
    wcon.up_axis = 'UP_Y'

    # The emissive swatch is a lamp, so it lights its own collar, plinth and
    # the floor around it. A shadowless point at its center stands in for
    # that spill (the shell is lit from inside only on back faces, so the
    # asserted emission is still the only thing the camera sees on the ball).
    for ob in swatches:
        if any(n.type == 'EMISSION' for n in ob.data.materials[0].node_tree.nodes):
            gd = bpy.data.lights.new("GlowSpill", 'POINT')
            gd.energy = 45.0
            gd.shadow_soft_size = 0.45
            gd.color = (1.0, 0.45, 0.12)
            gd.use_shadow = False
            gd.specular_factor = 0.15
            glow = bpy.data.objects.new("GlowSpill", gd)
            glow.location = ob.location
            coll.objects.link(glow)

    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    bg.inputs[0].default_value = (0.02, 0.021, 0.025, 1)
    # A reflection-only sky: glossy rays see a warm overhead gradient over a
    # dark horizon, every other ray the dark stage. The mirror-finish gold
    # otherwise reflected the near-black world and rendered as a black ball
    # with two light-card glints. Diffuse and camera rays are unchanged, so
    # the stage stays dark.
    path = nt.nodes.new("ShaderNodeLightPath")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Generated"], sep.inputs[0])
    sky = nt.nodes.new("ShaderNodeValToRGB")
    sky.color_ramp.elements[0].position = 0.0
    sky.color_ramp.elements[0].color = (0.02, 0.021, 0.025, 1)
    sky.color_ramp.elements[1].position = 0.7
    sky.color_ramp.elements[1].color = (0.50, 0.45, 0.39, 1)
    nt.links.new(sep.outputs["Z"], sky.inputs["Fac"])
    pick = nt.nodes.new("ShaderNodeMixRGB")
    pick.inputs[1].default_value = (0.02, 0.021, 0.025, 1)
    nt.links.new(sky.outputs["Color"], pick.inputs[2])
    nt.links.new(path.outputs["Is Glossy Ray"], pick.inputs[0])
    nt.links.new(pick.outputs[0], bg.inputs[0])
    sc.world = world
    return swatches, stands, [floor, wall]


def swatch_rgb(mat):
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            c = node.inputs["Base Color"].default_value
            return (round(c[0], 4), round(c[1], 4), round(c[2], 4))
        if node.type == "EMISSION":
            c = node.inputs["Color"].default_value
            return (round(c[0], 4), round(c[1], 4), round(c[2], 4))
    return None


def flatten_swatch_colors(mats):
    gray = (0.5, 0.5, 0.5, 1.0)
    for mat in mats:
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                node.inputs["Base Color"].default_value = gray
            elif node.type == "EMISSION":
                node.inputs["Color"].default_value = gray


SPECULAR_SOCKET = 'Specular IOR Level'   # the 4.0+ name; 4.5 LTS is the floor
WHITE_SPECULAR = 0.3                     # off the socket default (0.5)


def check_specular(mats, specular_socket):
    """The set_specular shim resolved the 4.0+ socket, and the value landed on
    it: WhiteRough's 0.3 differs from the socket default, so a shim that wrote
    nothing (``--no-specular-shim``) is caught on the material itself."""
    white = next(m for m in mats if m.name == "WhiteRough")
    bsdf = next(n for n in white.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    got = bsdf.inputs[SPECULAR_SOCKET].default_value
    if specular_socket != SPECULAR_SOCKET or abs(got - WHITE_SPECULAR) > 1e-6:
        print(f"ERROR: set_specular resolved {specular_socket!r} (want "
              f"{SPECULAR_SOCKET!r}); WhiteRough {SPECULAR_SOCKET}={got:.3f} "
              f"(want {WHITE_SPECULAR})", file=sys.stderr)
        return 7
    return 0


def check_distinct_swatches(mats):
    colors = [swatch_rgb(m) for m in mats]
    if len(set(colors)) != MATERIAL_COUNT:
        print(
            f"ERROR: distinct swatch colors {len(set(colors))} != "
            f"{MATERIAL_COUNT} (got {colors})",
            file=sys.stderr,
        )
        return 3
    return 0


def verify_png(path, scene, swatches):
    """Honest capture: not uniformly black AND distinct swatch regions == MATERIAL_COUNT.

    Each swatch is sampled where the camera actually sees it: its center is
    projected through the render camera, so the check follows the layout
    rather than assuming a flat grid of image cells."""
    from bpy_extras.object_utils import world_to_camera_view
    img = bpy.data.images.load(path)
    w, h = img.size
    arr = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[..., :3]
    gmax = float(arr.max())
    ph = max(4, round(w * 0.012))  # half-size of the sampled patch, in pixels
    means = []
    for ob in swatches:
        # rows are bottom-up in bpy image pixels, as in camera-view y
        v = world_to_camera_view(scene, scene.camera, ob.matrix_world.translation)
        cx, cy = int(v.x * w), int(v.y * h)
        means.append(arr[cy - ph:cy + ph, cx - ph:cx + ph, :].reshape(-1, 3).mean(axis=0))
    print("swatch patch means: " + "  ".join(
        f"{ob.name}=({m[0]:.2f},{m[1]:.2f},{m[2]:.2f})" for ob, m in zip(swatches, means)))
    closest = min(float(np.linalg.norm(a - b)) for i, a in enumerate(means) for b in means[i + 1:])
    print(f"swatch closest pair distance={closest:.3f} (distinct needs > 0.10)")
    kept = []
    for cm in means:
        if all(np.linalg.norm(cm - k) > 0.10 for k in kept):
            kept.append(cm)
    return gmax, len(kept)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description="Render a procedural-materials swatch grid.")
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", choices=["auto", "eevee", "cycles"], default="auto",
                   help="auto/eevee use the version-correct EEVEE id; cycles for GPU-less hosts")
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--same-base", action="store_true",
                   help="write the same RGB to every swatch (must fail)")
    p.add_argument("--invert-engine-id", action="store_true",
                   help="falsifier: swap the version branch, so the 'wrong-era' id "
                        "under test is this build's real one (must fail, exit 5)")
    p.add_argument("--no-specular-shim", action="store_true",
                   help="falsifier: write only the legacy 'Specular' socket (must fail, exit 7)")
    args = p.parse_args(argv)

    # Empty the factory file FIRST so the materials we create below survive.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats, specular_socket = build_materials(
        naive_set_specular if args.no_specular_shim else set_specular)
    scode = check_specular(mats, specular_socket)
    if scode:
        return scode
    if args.same_base:
        flatten_swatch_colors(mats)
    swatches, stands, stage = build_scene(mats)

    sc = bpy.context.scene
    # EEVEE engine-id proof: frame-independent, must hold even when we render with
    # Cycles. Witness the inversion for real: the OTHER era's id must be rejected
    # by this build, and the helper's id must be accepted.
    eid = get_eevee_engine_id()
    wrong = 'BLENDER_EEVEE_NEXT' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE'  # engine-id-exempt: the wrong-era id this example asserts is rejected
    if args.invert_engine_id:
        eid, wrong = wrong, eid
    try:
        sc.render.engine = wrong
        print(f"ERROR: wrong-era EEVEE id '{wrong}' was accepted by this build — "
              "the engine-id inversion this example witnesses is gone", file=sys.stderr)
        return 5
    except TypeError:
        pass  # correctly rejected
    sc.render.engine = eid  # the helper's id must exist (raises TypeError if not)
    print(f"eevee_engine_id={eid} accepted, '{wrong}' rejected OK; "
          f"set_specular resolved '{specular_socket}'")

    if not args.output:
        # No render to measure: the material values are all there is.
        dcode = check_distinct_swatches(mats)
        if dcode:
            return dcode
        print("swatch-grid OK")
        return 0

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
    # AgX would desaturate the swatches toward pastel -- exactly the material
    # colors this example exists to show (docs/VISUAL-STYLE.md)
    sc.view_settings.view_transform = 'Standard'
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact.
    # the hero is the whole display: every swatch and the plinth it stands on
    display = swatches + stands
    fcode = gallery_framing.check_framing(
        sc, sc.camera,
        hero=display,
        elements=display,
        stage=stage,
    )
    if fcode:
        return fcode
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(args.output) and os.path.getsize(args.output) > 0):
        print("ERROR: no output written", file=sys.stderr)
        return 4
    print(f"rendered {args.output} with {render_engine} ({os.path.getsize(args.output)} bytes)")

    gmax, regions = verify_png(args.output, sc, swatches)
    non_black = gmax > 0.05
    regions_ok = regions == MATERIAL_COUNT
    print(f"verify: max_pixel={gmax:.3f} non_black={non_black} "
          f"distinct_regions={regions} materials={MATERIAL_COUNT} ok={regions_ok}")
    if not (non_black and regions_ok):
        print("ERROR: render failed verification (black or wrong region count)", file=sys.stderr)
        return 6
    # Diagnostic after the pixels: `--same-base` lands on the rendered regions
    # above (exit 6), not on this read-back of the colors it wrote (#469).
    dcode = check_distinct_swatches(mats)
    if dcode:
        return dcode
    print("swatch-grid OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # blender exits 0 on an uncaught traceback; force non-zero
        import traceback
        traceback.print_exc()
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
