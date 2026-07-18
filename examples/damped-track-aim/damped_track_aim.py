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
ORBIT_RADIUS = 2.05
CORE_RADIUS = 0.38
NEEDLE_DEPTH = 1.15
NEEDLE_RADIUS = 0.09
# Local +Z must face the core; cos(3°) ≈ 0.9986 — leave a little room for
# cone tessellation / float noise while still catching a flipped axis.
MIN_AIM_DOT = 0.998


def orbit_positions(n, radius):
    """Ring in XY plus two polar needles — every tip reads clearly in a 3/4 view."""
    pts = []
    ring = n - 2
    for i in range(ring):
        a = 2.0 * math.pi * i / ring
        pts.append(Vector((radius * math.cos(a), radius * math.sin(a), 0.0)))
    pts.append(Vector((0.0, 0.0, radius)))
    pts.append(Vector((0.0, 0.0, -radius)))
    return pts


def make_needle_mesh():
    """Unit cone along +Z (tip at +Z) — TRACK_Z then aims the tip at the core."""
    me = bpy.data.meshes.new("Needle")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            segments=10,
            radius1=NEEDLE_RADIUS,
            radius2=0.0,
            depth=NEEDLE_DEPTH,
        )
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def make_core_mesh():
    me = bpy.data.meshes.new("Core")
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=CORE_RADIUS)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def make_metal(name, color, roughness=0.28, metallic=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def make_emissive(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*color, 1.0)
    emit.inputs["Strength"].default_value = strength
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    col = bpy.context.collection

    # Lift the whole constellation so the south polar needle clears the floor.
    lift = ORBIT_RADIUS + 0.25

    core = bpy.data.objects.new("Core", make_core_mesh())
    # Modest emission so the cyan reads as colour, not a white clip.
    core.data.materials.append(make_emissive("CoreEmit", (0.25, 0.75, 1.0), 4.5))
    core.location = (0.0, 0.0, lift)
    col.objects.link(core)

    needle_me = make_needle_mesh()
    metal = make_metal("NeedleMetal", (0.82, 0.78, 0.70), roughness=0.18)
    needle_me.materials.append(metal)

    needles = []
    for i, loc in enumerate(orbit_positions(N_NEEDLES, ORBIT_RADIUS)):
        ob = bpy.data.objects.new(f"Needle_{i:02d}", needle_me)
        ob.location = (loc.x, loc.y, loc.z + lift)
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

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = make_metal("StudioFloor", (0.045, 0.05, 0.055), roughness=0.42, metallic=0.35)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.006, 0.007, 0.01, 1.0)
    scene.world = world

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, ORBIT_RADIUS + 0.25)
    scene.collection.objects.link(aim)

    def light(name, loc, energy, size, col):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        scene.collection.objects.link(ob)
        lc = ob.constraints.new("TRACK_TO")
        lc.target = aim
        lc.track_axis = "TRACK_NEGATIVE_Z"
        lc.up_axis = "UP_Y"

    light("Key", (-4.0, -4.5, 6.5), 900.0, 6.0, (1.0, 0.97, 0.92))
    light("Fill", (5.0, -3.0, 3.8), 220.0, 8.0, (0.75, 0.85, 1.0))
    light("Rim", (1.2, 5.0, 3.2), 380.0, 4.0, (1.0, 0.7, 0.4))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (5.2, -5.6, 4.4)
    scene.collection.objects.link(cam)
    scene.camera = cam
    track = cam.constraints.new("TRACK_TO")
    track.target = aim
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    # Keep references live for the renderer (needles share one mesh).
    _ = (core, needles)

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 48
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
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
