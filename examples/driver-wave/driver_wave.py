"""Driver-namespace scale drivers, evaluated through the depsgraph — a runnable example.

Witnesses the drivers-and-app-handlers contract end to end: a custom function
is registered in `bpy.app.driver_namespace`, sixteen columns get a SCRIPTED
driver on Z scale calling it, and the check reads the driven values back
after a view-layer update — from the evaluated copy AND from the original
(the animation system flushes driven values back to the original datablock
for display, so both must agree). Asserts both against the closed-form
profile. Exits non-zero on failure.

``--flat-expr`` drives Z scale with ``1.0`` and still asserts ``wave_scale``.
That is the falsifier (``--same-axis`` in export-preset-axis).

Two more contracts ride along:

- A driver that calls a ``driver_namespace`` function is NOT a simple
  expression (``driver.is_simple_expression`` is False), so it only runs
  where Python auto-execution is allowed; in a GUI session with Auto Run
  Python Scripts off (the default) it goes dead. ``--simple-expr`` writes the
  same profile inline as ``1.4 + sin(i * 0.6)``: values still match, but the
  driver is now simple and the check exits 5.
- ``frame_change_pre`` and ``depsgraph_update_pre`` receive ``(scene, None)``;
  only the ``_post`` variants get a Depsgraph. ``--swap-handlers`` registers
  the pre probe on the post lists (and vice versa) and the check exits 7.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python driver_wave.py --                 # check only
    blender --background --python driver_wave.py -- --flat-expr      # must fail
    blender --background --python driver_wave.py -- --simple-expr    # must fail (5)
    blender --background --python driver_wave.py -- --swap-handlers  # must fail (7)
    blender --background --python driver_wave.py -- --output d.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

COUNT = 16
SPACING = 0.72
BASE = 0.28


def wave_scale(i):
    """The driver function: column height profile, 0.4..2.4."""
    return 1.4 + math.sin(i * 0.6)


# Organ-pipe body profile (r, z) in mesh units; BASE x/y scale makes the
# outer radius ~0.26. Bottom closed, open mouth at the top with a wall.
PIPE_PROFILE = [(0.0, 0.0), (0.92, 0.0), (0.92, 1.0), (0.80, 1.0), (0.80, 0.94), (0.0, 0.94)]


def lathe(bm, profile, segs=32):
    """Revolve an (r, z) profile about Z; r == 0 points become poles."""
    rings = []
    for r, z in profile:
        if r < 1e-9:
            rings.append([bm.verts.new((0.0, 0.0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * s / segs),
                                        r * math.sin(2 * math.pi * s / segs), z))
                          for s in range(segs)])
    for a, b in zip(rings, rings[1:]):
        for s in range(segs):
            t = (s + 1) % segs
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                bm.faces.new((a[0], b[t], b[s]))
            elif len(b) == 1:
                bm.faces.new((a[s], a[t], b[0]))
            else:
                bm.faces.new((a[s], a[t], b[t], b[s]))
    return rings


def build_columns(flat_expr=False, simple_expr=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # driver_namespace entries do not persist in .blend files; real add-ons
    # re-register them from a load_post handler. Headless, registering before
    # driver creation is enough.
    bpy.app.driver_namespace["wave_scale"] = wave_scale

    # one shared organ-pipe body: an open tube of unit height (z 0..1), so the
    # driven Z scale IS the speaking length; the rim annulus is horizontal and
    # stays crisp under any Z scale
    me = bpy.data.meshes.new("Column")
    bm = bmesh.new()
    try:
        lathe(bm, PIPE_PROFILE, segs=32)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.set_sharp_from_angle(angle=math.radians(50.0))

    objs = []
    x0 = -(COUNT - 1) * SPACING / 2
    for i in range(COUNT):
        obj = bpy.data.objects.new(f"Col.{i:02d}", me)
        obj.location = (x0 + i * SPACING, 0.0, 0.0)
        obj.scale = (BASE, BASE, 1.0)
        fcu = obj.driver_add("scale", 2)
        fcu.driver.type = 'SCRIPTED'
        if flat_expr:
            fcu.driver.expression = "1.0"
        elif simple_expr:
            fcu.driver.expression = f"1.4 + sin({i} * 0.6)"  # same profile, inline
        else:
            fcu.driver.expression = f"wave_scale({i})"
        bpy.context.collection.objects.link(obj)
        objs.append(obj)
    return objs


def check(objs):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    for i, obj in enumerate(objs):
        expect = wave_scale(i)
        driven = obj.evaluated_get(dg).scale[2]
        if abs(driven - expect) > 1e-4:
            print(f"ERROR: col {i} evaluated scale {driven:.4f} != wave_scale {expect:.4f}",
                  file=sys.stderr)
            return 3
        # drivers flush back to the original datablock for display — both agree
        if abs(obj.scale[2] - expect) > 1e-4:
            print(f"ERROR: col {i} original scale {obj.scale[2]:.4f} not flushed "
                  f"(expected {expect:.4f})", file=sys.stderr)
            return 4
    # a driver_namespace call is never a "simple expression": it needs Python
    # auto-execution, which a GUI session has off by default
    simple = [obj.animation_data.drivers[0].driver.is_simple_expression for obj in objs]
    if any(simple):
        print(f"ERROR: {sum(simple)}/{COUNT} drivers report is_simple_expression=True; "
              "the custom-function driver must not be a simple expression", file=sys.stderr)
        return 5
    lo = min(wave_scale(i) for i in range(COUNT))
    hi = max(wave_scale(i) for i in range(COUNT))
    print(f"columns={COUNT} driven_range={lo:.3f}..{hi:.3f} flushed_to_original=True "
          f"is_simple_expression=False")
    return 0


PRE_HANDLERS = ("frame_change_pre", "depsgraph_update_pre")
POST_HANDLERS = ("frame_change_post", "depsgraph_update_post")


def check_handler_args(objs, swap=False):
    """The pre handlers get (scene, None); the post handlers get (scene, Depsgraph)."""
    seen = {}

    def probe(name):
        def handler(scene, depsgraph=None):
            seen.setdefault(name, (type(scene).__name__, type(depsgraph).__name__))
        return handler

    registered = []
    for name in PRE_HANDLERS + POST_HANDLERS:
        # --swap-handlers hangs each probe on its opposite list
        target = name.replace("_pre", "_post") if name.endswith("_pre") else name.replace("_post", "_pre")
        handler_list = getattr(bpy.app.handlers, target if swap else name)
        h = probe(name)
        handler_list.append(h)
        registered.append((handler_list, h))
    try:
        scene = bpy.context.scene
        scene.frame_set(scene.frame_current + 1)
        objs[0].update_tag()  # a real edit, so the depsgraph_update pair fires too
        bpy.context.view_layer.update()
    finally:
        for handler_list, h in registered:
            handler_list.remove(h)
    want = {n: ("Scene", "NoneType") for n in PRE_HANDLERS}
    want.update({n: ("Scene", "Depsgraph") for n in POST_HANDLERS})
    if seen != want:
        print(f"ERROR: handler argument types {seen} != {want}", file=sys.stderr)
        return 7
    print("handler args: " + ", ".join(f"{n}={seen[n][1]}" for n in PRE_HANDLERS + POST_HANDLERS))
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(objs, path, engine):
    """A pipe-organ facade: the sixteen driven bodies are the speaking pipes.

    Everything added here is render-only staging around the driven objects:
    a walnut windchest, a brass foot cone and a mouth under each pipe. The
    pipe bodies keep their SCRIPTED drivers; their tops trace wave_scale.
    """
    scene = bpy.context.scene

    def principled(name, base, rough, metal=0.0, grain=None, noise=None):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*base, 1.0)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        coord = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
        if grain:
            # walnut: stretched noise bands along X, dark/light figure
            mapping = nt.nodes.new("ShaderNodeMapping")
            mapping.inputs["Scale"].default_value = (0.6, 14.0, 14.0)
            nt.links.new(coord, mapping.inputs["Vector"])
            tex = nt.nodes.new("ShaderNodeTexWave")
            tex.wave_type = "BANDS"
            tex.bands_direction = "Y"
            tex.inputs["Scale"].default_value = 0.35
            tex.inputs["Distortion"].default_value = 6.0
            tex.inputs["Detail"].default_value = 4.0
            nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].color = (*(c * 0.55 for c in base), 1.0)
            ramp.color_ramp.elements[1].color = (*(min(1.0, c * 1.45) for c in base), 1.0)
            nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
        if noise:
            # handling wear on the brass: mottled roughness, never a flat slot
            tex = nt.nodes.new("ShaderNodeTexNoise")
            tex.inputs["Scale"].default_value = noise
            tex.inputs["Detail"].default_value = 6.0
            nt.links.new(coord, tex.inputs["Vector"])
            mr = nt.nodes.new("ShaderNodeMapRange")
            mr.inputs["To Min"].default_value = rough - 0.08
            mr.inputs["To Max"].default_value = rough + 0.16
            nt.links.new(tex.outputs["Fac"], mr.inputs["Value"])
            nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
        return m

    brass = principled("Brass", (0.86, 0.62, 0.30), 0.24, metal=1.0, noise=9.0)
    walnut = principled("Walnut", (0.17, 0.075, 0.03), 0.48, grain=True)
    mouth_mat = principled("PipeMouth", (0.012, 0.010, 0.009), 0.7)
    objs[0].data.materials.append(brass)  # shared mesh -> all sixteen pipes

    def box(name, dims, loc, mat, bevel=0.02):
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        try:
            bmesh.ops.create_cube(bm, size=1.0)
            for v in bm.verts:
                v.co.x *= dims[0]; v.co.y *= dims[1]; v.co.z *= dims[2]
            if bevel:
                bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2,
                                profile=0.5, affect="EDGES", clamp_overlap=True)
            bm.to_mesh(me)
        finally:
            bm.free()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = loc
        scene.collection.objects.link(ob)
        return ob

    # the windchest: a walnut cabinet the pipe feet stand in
    span = (COUNT - 1) * SPACING
    chest_w, chest_d = span + 0.95, 1.1
    parts = [
        box("Chest.Plinth", (chest_w + 0.12, chest_d + 0.12, 0.14), (0, 0, 0.07), walnut),
        box("Chest.Body", (chest_w, chest_d, 0.78), (0, 0, 0.53), walnut, bevel=0.015),
        box("Chest.Rail", (chest_w + 0.10, chest_d + 0.10, 0.08), (0, 0, 0.96), walnut),
        box("Chest.Toe", (chest_w - 0.2, chest_d - 0.4, 0.06), (0, 0, 1.03), walnut),
    ]
    # raised front panels with brass pulls, one per four pipes
    for k in range(4):
        px = -span / 2 + span * (k + 0.5) / 4
        parts.append(box(f"Chest.Panel.{k}", (span / 4 - 0.32, 0.04, 0.5),
                         (px, -chest_d / 2 - 0.015, 0.53), walnut, bevel=0.012))
        parts.append(box(f"Chest.Pull.{k}", (0.22, 0.04, 0.04),
                         (px, -chest_d / 2 - 0.05, 0.53), brass, bevel=0.01))

    # the case back: a dark walnut screen behind the pipes, so the driven
    # tops trace their wave against wood rather than fading into the stage;
    # two side towers with brass finials close the facade
    dark_walnut = principled("WalnutDark", (0.07, 0.032, 0.014), 0.55, grain=True)
    parts.append(box("Case.Back", (chest_w - 0.2, 0.12, 3.05),
                     (0, 0.42, 1.06 + 1.525), dark_walnut, bevel=0.02))
    parts.append(box("Case.Cornice", (chest_w + 0.1, 0.36, 0.14),
                     (0, 0.40, 1.06 + 3.12), walnut, bevel=0.02))
    for sx in (-1.0, 1.0):
        tx = sx * (chest_w / 2 - 0.05)
        parts.append(box(f"Case.Tower.{'LR'[sx > 0]}", (0.34, 0.62, 3.3),
                         (tx, 0.18, 1.06 + 1.65), walnut, bevel=0.025))
        parts.append(box(f"Case.Cap.{'LR'[sx > 0]}", (0.44, 0.72, 0.1),
                         (tx, 0.18, 1.06 + 3.35), walnut, bevel=0.02))
        fin_me = bpy.data.meshes.new(f"Finial.{'LR'[sx > 0]}")
        bm = bmesh.new()
        try:
            lathe(bm, [(0.0, 0.0), (0.12, 0.0), (0.12, 0.05), (0.06, 0.09),
                       (0.10, 0.18), (0.07, 0.27), (0.02, 0.33), (0.0, 0.36)], segs=24)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(fin_me)
        finally:
            bm.free()
        fin_me.polygons.foreach_set("use_smooth", [True] * len(fin_me.polygons))
        fin_me.materials.append(brass)
        fin = bpy.data.objects.new(fin_me.name, fin_me)
        fin.location = (tx, 0.18, 1.06 + 3.40)
        scene.collection.objects.link(fin)
        parts.append(fin)

    # brass foot cone + mouth per pipe; the driven body starts above the foot
    foot_h = 0.50
    chest_top = 1.06
    foot_me = bpy.data.meshes.new("PipeFoot")
    bm = bmesh.new()
    try:
        lathe(bm, [(0.0, 0.0), (0.05, 0.0), (0.06, 0.03), (0.24, foot_h - 0.04), (0.258, foot_h),
                   (0.0, foot_h)], segs=32)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(foot_me)
    finally:
        bm.free()
    foot_me.polygons.foreach_set("use_smooth", [True] * len(foot_me.polygons))
    foot_me.materials.append(brass)
    dg = bpy.context.evaluated_depsgraph_get()
    for obj in objs:
        x = obj.location.x
        foot = bpy.data.objects.new(f"Foot.{obj.name[-2:]}", foot_me)
        foot.location = (x, 0.0, chest_top)
        scene.collection.objects.link(foot)
        parts.append(foot)
        # body stands on its foot; its height is the DRIVEN Z scale
        obj.location.z = chest_top + foot_h
        z0 = chest_top + foot_h
        parts.append(box(f"Mouth.{obj.name[-2:]}", (0.20, 0.04, 0.15),
                         (x, -0.238, z0 + 0.10), mouth_mat, bevel=0.008))
        parts.append(box(f"Lip.{obj.name[-2:]}", (0.23, 0.05, 0.035),
                         (x, -0.245, z0 + 0.19), brass, bevel=0.01))
    heights = [obj.evaluated_get(dg).scale[2] for obj in objs]

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    floor = bpy.data.objects.new("Floor", floor_me)
    fmat = bpy.data.materials.new("FloorMat")
    fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)  # dark staged studio
    fb.inputs["Roughness"].default_value = 0.7
    floor_me.materials.append(fmat)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 7.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, at):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(at) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(ob)

    # warm shaped key, faint cool fill, a broad soft card the brass can
    # mirror (bare metal in a dark studio otherwise reads black), a cool rim
    # on the pipe edges and a warm wedge pooling on the back wall
    light("Key", (-5.0, -6.5, 7.0), 900.0, 4.0, (1.0, 0.94, 0.86), (-0.5, 0.0, 2.0))
    light("Fill", (6.5, -5.0, 3.0), 160.0, 8.0, (0.75, 0.85, 1.0), (0.0, 0.0, 2.0))
    light("Card", (1.5, -9.0, 4.5), 260.0, 10.0, (1.0, 0.92, 0.80), (0.0, 0.0, 2.2))
    light("Rim", (-2.0, 4.5, 5.5), 420.0, 4.0, (0.62, 0.78, 1.0), (0.0, 0.0, 2.2))
    light("Wedge", (5.5, 1.5, 3.2), 650.0, 6.0, (1.0, 0.70, 0.42), (7.0, 7.0, 1.4))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 45.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-4.3, -18.2, 3.2)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (-0.35, 0.0, 2.25)
    scene.collection.objects.link(aim)
    con = cam.constraints.new('TRACK_TO')
    con.target = aim
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 48
    else:
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # AgX would wash the brass toward tan (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()
    print(f"pipe speaking lengths (driven) {min(heights):.3f}..{max(heights):.3f}")
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact.
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=list(objs) + parts,
        elements=list(objs) + parts,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 6
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--flat-expr", action="store_true",
                   help="drive Z scale with 1.0 (must fail)")
    p.add_argument("--simple-expr", action="store_true",
                   help="inline the profile as a simple expression (must fail, exit 5)")
    p.add_argument("--swap-handlers", action="store_true",
                   help="register the pre-handler probes on the post lists (must fail, exit 7)")
    args = p.parse_args(argv)

    objs = build_columns(flat_expr=args.flat_expr, simple_expr=args.simple_expr)
    code = check(objs)
    if code:
        return code
    code = check_handler_args(objs, swap=args.swap_handlers)
    if code:
        return code

    if args.output:
        rcode = render_still(objs, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("driver-wave OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
