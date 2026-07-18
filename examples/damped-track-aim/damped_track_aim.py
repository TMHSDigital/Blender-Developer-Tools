"""Damped Track needles aiming at an emissive core — a runnable example.

Witnesses that aim constraints are authored on the data API
(`Object.constraints.new('DAMPED_TRACK')`, `target`, `track_axis`) — not via
`bpy.ops.object.constraint_add` (which needs an active object and breaks in
headless loops). Damped Track is the twist-stable replacement for Track To
when you only need an axis to point at a target.

The check asserts every needle carries exactly one DAMPED_TRACK aimed at the
core on TRACK_Z, then samples the evaluated depsgraph: local +Z must align
with the world vector toward the core within a tight angular epsilon. If the
constraint is missing, muted, mistyped as TRACK_TO, or the axis is flipped,
the dot product fails.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python damped_track_aim.py --                 # check only
    blender --background --python damped_track_aim.py -- --output aim.png
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

N_NEEDLES = 12
ORBIT_RADIUS = 1.85
CORE_RADIUS = 0.32
NEEDLE_DEPTH = 1.05
NEEDLE_RADIUS = 0.055
# Local +Z must face the core; cos(3°) ≈ 0.9986 — leave a little room for
# cone tessellation / float noise while still catching a flipped axis.
MIN_AIM_DOT = 0.998
LIFT = 1.55


def orbit_positions(n, radius):
    """Tilted equatorial ring + poles — readable as a cage, not a flat wreath."""
    pts = []
    ring = n - 2
    tilt = math.radians(18.0)
    for i in range(ring):
        a = 2.0 * math.pi * i / ring + math.radians(9.0)
        x = radius * math.cos(a)
        y = radius * math.sin(a) * math.cos(tilt)
        z = radius * math.sin(a) * math.sin(tilt)
        pts.append(Vector((x, y, z)))
    pts.append(Vector((0.0, 0.0, radius * 0.92)))
    pts.append(Vector((0.0, 0.0, -radius * 0.92)))
    return pts


def make_needle_mesh():
    """Long tapered spike with tip on +Z — TRACK_Z aims the tip at the core."""
    me = bpy.data.meshes.new("Needle")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            segments=48,
            radius1=NEEDLE_RADIUS,
            radius2=0.0,
            depth=NEEDLE_DEPTH,
        )
        # Slight belly toward the base so it reads as turned metal, not a pencil.
        for v in bm.verts:
            # Map z from [-d/2, +d/2] → t in [0,1] (base→tip).
            t = (v.co.z + NEEDLE_DEPTH * 0.5) / NEEDLE_DEPTH
            flare = 1.0 + 0.55 * ((1.0 - t) ** 2)
            v.co.x *= flare
            v.co.y *= flare
        bm.normal_update()
        bm.to_mesh(me)
    finally:
        bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    return me


def make_core_mesh():
    me = bpy.data.meshes.new("Core")
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=CORE_RADIUS)
        bm.to_mesh(me)
    finally:
        bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    return me


def make_plinth_mesh():
    me = bpy.data.meshes.new("Plinth")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            segments=64,
            radius1=1.55,
            radius2=1.35,
            depth=0.12,
        )
        bm.to_mesh(me)
    finally:
        bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    return me


def set_specular(bsdf, value):
    """4.x Specular → 5.x Specular IOR Level."""
    socks = bsdf.inputs
    if "Specular IOR Level" in socks:
        socks["Specular IOR Level"].default_value = value
    elif "Specular" in socks:
        socks["Specular"].default_value = value


def make_metal(name, color, roughness=0.22, metallic=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    set_specular(bsdf, 0.5)
    return mat


def make_core_material():
    """Dark shell + ember emission so the core has form, not a clipped white blob."""
    mat = bpy.data.materials.new("CoreEmber")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.02, 0.01, 0.015, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.18
    bsdf.inputs["Metallic"].default_value = 0.85
    set_specular(bsdf, 0.6)
    # Principled emission — present on both 4.5 and 5.x.
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.22, 0.04, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 6.5
    elif "Emission" in bsdf.inputs:
        bsdf.inputs["Emission"].default_value = (1.0, 0.22, 0.04, 1.0)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 6.5
    return mat


def make_dielectric(name, color, roughness=0.35):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    set_specular(bsdf, 0.45)
    return mat


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    col = bpy.context.collection

    core = bpy.data.objects.new("Core", make_core_mesh())
    core.data.materials.append(make_core_material())
    core.location = (0.0, 0.0, LIFT)
    col.objects.link(core)

    needle_me = make_needle_mesh()
    # Warm brass — rim light + ember core will ping reflections hard.
    metal = make_metal("NeedleMetal", (0.78, 0.55, 0.28), roughness=0.16)
    needle_me.materials.append(metal)

    needles = []
    for i, loc in enumerate(orbit_positions(N_NEEDLES, ORBIT_RADIUS)):
        ob = bpy.data.objects.new(f"Needle_{i:02d}", needle_me)
        ob.location = (loc.x, loc.y, loc.z + LIFT)
        # Deliberate identity rotation — the constraint alone must do the aiming.
        ob.rotation_euler = (0.0, 0.0, 0.0)
        col.objects.link(ob)
        con = ob.constraints.new("DAMPED_TRACK")
        con.name = "AimCore"
        con.target = core
        con.track_axis = "TRACK_Z"
        needles.append(ob)

    bpy.context.view_layer.update()
    return core, needles


def check(core, needles):
    if len(needles) != N_NEEDLES:
        print(f"ERROR: needle count {len(needles)} != {N_NEEDLES}", file=sys.stderr)
        return 3

    for ob in needles:
        damped = [c for c in ob.constraints if c.type == "DAMPED_TRACK"]
        if len(damped) != 1:
            print(
                f"ERROR: {ob.name} has {len(damped)} DAMPED_TRACK constraints "
                f"(total constraints={len(ob.constraints)})",
                file=sys.stderr,
            )
            return 4
        con = damped[0]
        if con.target != core:
            print(f"ERROR: {ob.name} target is {con.target!r}, want Core", file=sys.stderr)
            return 5
        if con.track_axis != "TRACK_Z":
            print(
                f"ERROR: {ob.name} track_axis={con.track_axis!r}, want TRACK_Z",
                file=sys.stderr,
            )
            return 6
        if con.mute or con.influence < 0.999:
            print(
                f"ERROR: {ob.name} mute={con.mute} influence={con.influence}",
                file=sys.stderr,
            )
            return 7
        if any(c.type == "TRACK_TO" for c in ob.constraints):
            print(
                f"ERROR: {ob.name} still has TRACK_TO — use DAMPED_TRACK for aim",
                file=sys.stderr,
            )
            return 8

    dg = bpy.context.evaluated_depsgraph_get()
    core_loc = core.evaluated_get(dg).matrix_world.translation
    worst = 2.0
    worst_name = needles[0].name
    for ob in needles:
        ev = ob.evaluated_get(dg)
        mw = ev.matrix_world
        tip_dir = (mw.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
        to_core = (core_loc - mw.translation).normalized()
        dot = tip_dir.dot(to_core)
        if dot < worst:
            worst = dot
            worst_name = ob.name
        if dot < MIN_AIM_DOT:
            angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
            print(
                f"ERROR: {ob.name} aim dot={dot:.6f} ({angle:.2f}°) "
                f"< {MIN_AIM_DOT} — constraint not evaluated or axis flipped",
                file=sys.stderr,
            )
            return 9

    print(
        f"OK: {N_NEEDLES} DAMPED_TRACK needles → Core on TRACK_Z; "
        f"worst aim dot={worst:.6f} ({worst_name})"
    )
    return 0


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def render_still(core, needles, path, engine):
    scene = bpy.context.scene

    # Soft cyclorama — one curved-feeling backdrop via oversized floor + back plane.
    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = make_dielectric("StudioFloor", (0.035, 0.037, 0.042), roughness=0.22)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)

    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.data = floor_me.copy()
    wall.data.materials.clear()
    wall.data.materials.append(
        make_dielectric("StudioWall", (0.012, 0.013, 0.016), roughness=0.55)
    )
    wall.location = (0.0, 11.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    plinth = bpy.data.objects.new("Plinth", make_plinth_mesh())
    plinth.data.materials.append(
        make_metal("PlinthMetal", (0.06, 0.065, 0.07), roughness=0.38)
    )
    plinth.location = (0.0, 0.0, 0.06)
    scene.collection.objects.link(plinth)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.004, 0.0045, 0.006, 1.0)
    bg.inputs["Strength"].default_value = 0.35
    scene.world = world

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, LIFT)
    scene.collection.objects.link(aim)

    def light(name, loc, energy, size, col):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        # Illuminate without drawing the area-light quad into the beauty pass.
        ob.visible_camera = False
        scene.collection.objects.link(ob)
        lc = ob.constraints.new("TRACK_TO")
        lc.target = aim
        lc.track_axis = "TRACK_NEGATIVE_Z"
        lc.up_axis = "UP_Y"
        return ob

    # Product lighting: soft warm key, cool fill, hot rim that skims the spikes.
    light("Key", (-3.8, -5.2, LIFT + 3.2), 1100.0, 5.5, (1.0, 0.95, 0.9))
    light("Fill", (5.2, -2.8, LIFT + 1.4), 320.0, 9.0, (0.6, 0.75, 1.0))
    light("Rim", (1.0, 4.5, LIFT + 1.8), 1200.0, 2.8, (1.0, 0.42, 0.15))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 65.0
    cam_data.dof.use_dof = False
    cam = bpy.data.objects.new("Cam", cam_data)
    # Offset three-quarter — full cage in frame, plinth reflection, not dead-center.
    cam.location = (5.1, -5.6, LIFT + 1.15)
    scene.collection.objects.link(cam)
    scene.camera = cam
    track = cam.constraints.new("TRACK_TO")
    # Bias look-at slightly down so the floor reflection earns space.
    aim.location = (0.15, 0.0, LIFT - 0.12)
    track.target = aim
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    _ = (core, needles)

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 64
        scene.cycles.use_denoising = True
    else:
        try:
            scene.eevee.taa_render_samples = 128
        except AttributeError:
            pass
        # Bloom helps the ember core read without a compositor tree.
        for attr, val in (
            ("use_bloom", True),
            ("bloom_intensity", 0.12),
            ("bloom_threshold", 0.85),
            ("bloom_radius", 4.5),
        ):
            if hasattr(scene.eevee, attr):
                try:
                    setattr(scene.eevee, attr, val)
                except Exception:
                    pass

    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine",
        default="eevee",
        choices=("eevee", "cycles"),
        help="render engine when --output is set",
    )
    args = p.parse_args(argv)

    core, needles = build()
    code = check(core, needles)
    if code != 0:
        return code

    if args.output:
        ok = render_still(core, needles, args.output, args.engine)
        if not ok:
            print(f"ERROR: render failed to write {args.output}", file=sys.stderr)
            return 10
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
