"""Damped Track spotlight heads aiming at a glowing orb — a runnable example.

Witnesses that aim constraints are authored on the data API
(`Object.constraints.new('DAMPED_TRACK')`, `target`, `track_axis`) — not via
`bpy.ops.object.constraint_add` (which needs an active object and breaks in
headless loops). Damped Track is the twist-stable replacement for Track To
when you only need an axis to point at a target.

Twelve spotlight heads stand in an open ring around a glowing target orb, at
alternating low and high stand heights. Each head is modeled with its lens on
local +Z and created with an identity rotation, so the constraint alone must
swing every lens onto the orb. The check asserts every head carries exactly
one DAMPED_TRACK aimed at the orb on TRACK_Z, then samples the evaluated
depsgraph: local +Z must align with the world vector toward the orb within a
tight angular epsilon. If the constraint is missing, muted, mistyped as
TRACK_TO, or the axis is flipped, the dot product fails.

``--mute`` mutes every DAMPED_TRACK and still asserts unmute. That is the
falsifier (``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python damped_track_aim.py --                 # check only
    blender --background --python damped_track_aim.py -- --mute           # must fail
    blender --background --python damped_track_aim.py -- --output aim.png
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

# Shared Layer 1 framing measurement (render path only) — see
# gallery_framing.py for the __file__-relative import shim this relies on.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
import gallery_framing  # noqa: E402

N_LAMPS = 12
RING_RADIUS = 2.45
ORB_RADIUS = 0.36
LIFT = 1.55                     # orb centre height
LOW_Z, HIGH_Z = 0.72, 2.55      # alternating stand heights: lamps aim up, then down
# The ring opens toward the camera (-Y) so no head hides the orb: the lamps
# span ARC_DEG centred on +Y.
ARC_DEG = 210.0
# Local +Z must face the orb; 0.998 = cos(3.6°) — leave a little room for
# float noise while still catching a flipped axis.
MIN_AIM_DOT = 0.998
SEGS = 40

# Spotlight head, lathed about local Z with the lens on +Z and the pivot at the
# origin: (r, z, material) rings back to front. Materials: 0 enamel body,
# 1 brass bezel, 2 lens, 3 steel cooling fins.
HEAD_PROFILE = [
    (0.0, -0.27, 3), (0.11, -0.27, 3), (0.15, -0.255, 3),
    (0.205, -0.245, 3), (0.205, -0.225, 3), (0.165, -0.215, 3), (0.165, -0.2, 3),
    (0.205, -0.19, 3), (0.205, -0.17, 3), (0.165, -0.16, 3), (0.165, -0.145, 3),
    (0.205, -0.135, 3), (0.205, -0.115, 3), (0.18, -0.105, 3),
    (0.19, -0.09, 0), (0.195, -0.07, 0), (0.195, 0.10, 0), (0.205, 0.12, 0),
    (0.228, 0.13, 1), (0.238, 0.15, 1), (0.238, 0.21, 1), (0.225, 0.225, 1),
    (0.182, 0.228, 1), (0.172, 0.22, 2), (0.12, 0.232, 2), (0.0, 0.238, 2),
]


def lamp_positions():
    """Open ring of stand-top pivots, heights alternating low / high."""
    pts = []
    start = 90.0 - ARC_DEG / 2.0
    for i in range(N_LAMPS):
        a = math.radians(start + ARC_DEG * i / (N_LAMPS - 1))
        z = LOW_Z if i % 2 == 0 else HIGH_Z
        pts.append(Vector((RING_RADIUS * math.cos(a), RING_RADIUS * math.sin(a), z)))
    return pts


def lathe(bm, profile, segs=SEGS):
    """Revolve (r, z, mat) rings about local Z; r == 0 rings become poles.
    A band takes the material of its upper ring."""
    rings = []
    for r, z, _m in profile:
        if r < 1e-9:
            rings.append([bm.verts.new((0.0, 0.0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * s / segs),
                                        r * math.sin(2 * math.pi * s / segs), z))
                          for s in range(segs)])
    for k, (a, b) in enumerate(zip(rings, rings[1:])):
        mat = profile[k + 1][2]
        for s in range(segs):
            t = (s + 1) % segs
            if len(a) == 1:
                vs = (a[0], b[t], b[s])
            elif len(b) == 1:
                vs = (a[s], a[t], b[0])
            else:
                vs = (a[s], a[t], b[t], b[s])
            f = bm.faces.new(vs)
            f.material_index = mat
            f.smooth = True
    return [v for ring in rings for v in ring]


def finish(bm, me, sharp_deg=40.0):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    me.set_sharp_from_angle(angle=math.radians(sharp_deg))
    return me


def make_head_mesh():
    """Spotlight can with its lens on +Z — TRACK_Z swings the lens onto the orb."""
    me = bpy.data.meshes.new("LampHead")
    bm = bmesh.new()
    try:
        lathe(bm, HEAD_PROFILE)
        # tilt-lock knobs on both flanks, where a yoke would pin the can
        for side in (-1.0, 1.0):
            vs = lathe(bm, [(0.0, 0.0, 1), (0.045, 0.0, 1), (0.05, 0.02, 1),
                            (0.05, 0.05, 1), (0.03, 0.065, 1), (0.0, 0.065, 1)], segs=16)
            for v in vs:
                v.co = Vector((side * (0.195 + v.co.z), v.co.x, v.co.y - 0.02))
        finish(bm, me)
    finally:
        bm.free()
    return me


def make_orb_mesh():
    me = bpy.data.meshes.new("Orb")
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=ORB_RADIUS)
        for f in bm.faces:
            f.smooth = True
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def set_specular(bsdf, value):
    """4.x Specular → 5.x Specular IOR Level."""
    socks = bsdf.inputs
    if "Specular IOR Level" in socks:
        socks["Specular IOR Level"].default_value = value
    elif "Specular" in socks:
        socks["Specular"].default_value = value


def make_material(name, color, roughness, metallic=0.0, noise=None, emit=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    set_specular(bsdf, 0.5)
    if noise:
        # handling wear: noise-mottled roughness, never a flat slot
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = noise
        tex.inputs["Detail"].default_value = 6.0
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = max(0.0, roughness - 0.08)
        mr.inputs["To Max"].default_value = roughness + 0.14
        nt.links.new(tex.outputs["Fac"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])
    if emit:
        col, core, rim = emit
        key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        bsdf.inputs[key].default_value = (*col, 1.0)
        # hot where the surface faces the eye, cooling at the silhouette, so a
        # glowing sphere keeps its form instead of clipping to a flat disc
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.25
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = core
        mr.inputs["To Max"].default_value = rim
        mr.inputs["From Max"].default_value = 0.6
        nt.links.new(lw.outputs["Facing"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], bsdf.inputs["Emission Strength"])
    return mat


def build(mute=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    col = bpy.context.collection

    orb = bpy.data.objects.new("Orb", make_orb_mesh())
    orb.data.materials.append(make_material(
        "OrbGlow", (0.06, 0.025, 0.01), 0.16, emit=((1.0, 0.28, 0.03), 0.98, 0.3)))
    orb.location = (0.0, 0.0, LIFT)
    col.objects.link(orb)

    head_me = make_head_mesh()
    head_me.materials.append(make_material("Enamel", (0.34, 0.035, 0.03), 0.3, noise=14.0))
    head_me.materials.append(make_material("Brass", (0.8, 0.56, 0.24), 0.24,
                                           metallic=1.0, noise=30.0))
    head_me.materials.append(make_material("Lens", (0.9, 0.75, 0.5), 0.08,
                                           emit=((1.0, 0.72, 0.38), 0.7, 0.4)))
    head_me.materials.append(make_material("Fins", (0.09, 0.09, 0.1), 0.42,
                                           metallic=0.9, noise=22.0))

    lamps = []
    for i, loc in enumerate(lamp_positions()):
        ob = bpy.data.objects.new(f"Lamp_{i:02d}", head_me)
        ob.location = loc
        # Deliberate identity rotation — the constraint alone must do the aiming.
        ob.rotation_euler = (0.0, 0.0, 0.0)
        col.objects.link(ob)
        con = ob.constraints.new("DAMPED_TRACK")
        con.name = "AimOrb"
        con.target = orb
        con.track_axis = "TRACK_Z"
        if mute:
            con.mute = True
        lamps.append(ob)

    bpy.context.view_layer.update()
    return orb, lamps


def check(orb, lamps):
    if len(lamps) != N_LAMPS:
        print(f"ERROR: lamp count {len(lamps)} != {N_LAMPS}", file=sys.stderr)
        return 3

    for ob in lamps:
        damped = [c for c in ob.constraints if c.type == "DAMPED_TRACK"]
        if len(damped) != 1:
            print(
                f"ERROR: {ob.name} has {len(damped)} DAMPED_TRACK constraints "
                f"(total constraints={len(ob.constraints)})",
                file=sys.stderr,
            )
            return 4
        con = damped[0]
        if con.target != orb:
            print(f"ERROR: {ob.name} target is {con.target!r}, want Orb", file=sys.stderr)
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
    orb_loc = orb.evaluated_get(dg).matrix_world.translation
    worst = 2.0
    worst_name = lamps[0].name
    for ob in lamps:
        ev = ob.evaluated_get(dg)
        mw = ev.matrix_world
        lens_dir = (mw.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
        to_orb = (orb_loc - mw.translation).normalized()
        dot = lens_dir.dot(to_orb)
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
        f"OK: {N_LAMPS} DAMPED_TRACK lamp heads → Orb on TRACK_Z; "
        f"worst aim dot={worst:.6f} ({worst_name})"
    )
    return 0


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def build_stands(lamps):
    """Render-only: a floor foot, a steel post and a ball pivot under every head,
    plus the turned pedestal the orb sits in."""
    me = bpy.data.meshes.new("Stands")
    bm = bmesh.new()
    try:
        for ob in lamps:
            top = ob.location.z
            vs = lathe(bm, [(0.0, 0.0, 0), (0.26, 0.0, 0), (0.27, 0.02, 0),
                            (0.25, 0.05, 0), (0.08, 0.07, 0), (0.05, 0.1, 0),
                            (0.028, 0.12, 0), (0.028, top - 0.13, 0),
                            (0.045, top - 0.12, 1), (0.045, top - 0.07, 1),
                            (0.07, top - 0.05, 1), (0.075, top, 1),
                            (0.05, top + 0.05, 1), (0.0, top + 0.06, 1)], segs=24)
            for v in vs:
                v.co.x += ob.location.x
                v.co.y += ob.location.y
        base = LIFT - ORB_RADIUS
        lathe(bm, [(0.0, 0.0, 0), (0.5, 0.0, 0), (0.52, 0.03, 0), (0.5, 0.08, 0),
                   (0.3, 0.12, 1), (0.1, 0.18, 1), (0.06, 0.24, 1), (0.05, base - 0.2, 1),
                   (0.08, base - 0.14, 1), (0.2, base - 0.02, 1), (0.23, base + 0.06, 1),
                   (0.21, base + 0.07, 1), (0.0, base + 0.02, 1)], segs=48)
        finish(bm, me)
    finally:
        bm.free()
    me.materials.append(make_material("StandSteel", (0.06, 0.062, 0.07), 0.36,
                                      metallic=0.85, noise=18.0))
    me.materials.append(make_material("StandBrass", (0.8, 0.56, 0.24), 0.26,
                                      metallic=1.0, noise=30.0))
    ob = bpy.data.objects.new("Stands", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def render_still(orb, lamps, path, engine):
    scene = bpy.context.scene
    stands = build_stands(lamps)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    floor_me.materials.append(make_material("StudioFloor", (0.03, 0.032, 0.037), 0.55))
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.data.materials.clear()
    wall.data.materials.append(make_material("StudioWall", (0.03, 0.032, 0.037), 0.7))
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, kind, loc, energy, col, at=(0.0, 0.0, LIFT), size=1.0):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = col
        if kind == "AREA":
            ld.size = size
        else:
            ld.shadow_soft_size = size
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(at) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        ob.visible_camera = False
        scene.collection.objects.link(ob)
        return ld

    # shaped warm key, faint cool fill, cool rim on the far heads, warm wedge
    # raking the back wall (docs/VISUAL-STYLE.md); the orb itself is a point
    # glow, so it throws warm light onto every lens and bezel aimed at it
    light("Key", "AREA", (-4.5, -5.0, 6.0), 520.0, (1.0, 0.95, 0.88), size=4.0)
    light("Fill", "AREA", (5.5, -4.0, 3.0), 80.0, (0.75, 0.85, 1.0), size=9.0)
    light("Rim", "AREA", (0.5, 5.5, 5.5), 260.0, (0.6, 0.78, 1.0), size=3.5)
    light("Wedge", "AREA", (2.6, 5.0, 4.2), 700.0, (1.0, 0.7, 0.42),
          at=(3.5, 9.0, 0.6), size=6.0)
    glow = light("OrbGlow", "POINT", (0.0, 0.0, LIFT), 90.0, (1.0, 0.55, 0.22), size=0.3)
    glow.use_shadow = False

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.8, -10.8, 4.0)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 1.3)
    scene.collection.objects.link(aim)
    track = cam.constraints.new("TRACK_TO")
    track.target = aim
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    scene.camera = cam

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 64
        scene.cycles.use_denoising = True
    else:
        try:
            scene.eevee.taa_render_samples = 96
        except AttributeError:
            pass

    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.film_transparent = False
    # Standard, not AgX/Filmic: the enamel and the amber glow stay saturated
    # (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    # Blender resolves a relative filepath against the blend-file directory, which
    # for a --background run with no .blend is the drive root, not the cwd.
    path = os.path.abspath(path)
    scene.render.filepath = path
    bpy.context.view_layer.update()
    # Layer 1 framing gate before the beauty render (exit 10 on violation)
    hero = [orb, stands] + lamps
    fcode = gallery_framing.check_framing(scene, cam, hero=hero, elements=hero,
                                          stage=[floor, wall])
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    return 0 if os.path.exists(path) and os.path.getsize(path) > 0 else 12


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
    p.add_argument("--mute", action="store_true",
                   help="mute every DAMPED_TRACK (must fail)")
    args = p.parse_args(argv)

    orb, lamps = build(mute=args.mute)
    code = check(orb, lamps)
    if code != 0:
        return code

    if args.output:
        rcode = render_still(orb, lamps, args.output, args.engine)
        if rcode:
            if rcode == 12:
                print(f"ERROR: render failed to write {args.output}", file=sys.stderr)
            return rcode
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
