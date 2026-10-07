"""Custom ID-property delete — a runnable example.

Witnesses the contract the snippet ``cross-version-property-delete`` teaches,
not the snippet's ``__main__`` (which keys off ``context.active_object`` and
is dark headless). Builds the ID through ``bpy.data.objects.new`` and asserts:

1. ``obj["accession"] = 42`` lands in ``obj.keys()``.
2. ``property_unset("accession")`` is a TypeError and does **not** remove
   the ID property — that RNA call resets a registered property to default.
3. ``del obj["accession"]`` removes it. Same on 4.5 LTS and 5.x; no version
   branch.
4. A *registered* ``bpy.props`` value is a different thing on 5.0+: it is no
   longer an ID property, so ``scene["name"]``, ``"name" in scene.keys()``,
   ``del scene["name"]`` and a driver path of ``'["name"]'`` all stop seeing
   it. Attribute access, ``property_unset()``, ``is_property_set()`` and the
   plain ``"name"`` path work on every version. ``--subscript-registered``
   reads it the 4.x way and exits 8 on 5.0+ (exit 0 on 4.5, where it still
   works).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python cross_version_property_delete.py --
    blender --background --python cross_version_property_delete.py -- --output lamps.png
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True
import gallery_framing

KEY = "accession"
VALUE = 42
REG = "bdt_counter"  # registered bpy.props IntProperty on Scene


def beveled_box(name, size, bevel, segments=2):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= size[0]
            v.co.y *= size[1]
            v.co.z *= size[2]
        bm.normal_update()
        bmesh.ops.bevel(
            bm, geom=list(bm.edges), offset=bevel, segments=segments,
            profile=0.5, affect="EDGES", clamp_overlap=True,
        )
        bm.to_mesh(me)
    finally:
        bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def cylinder(name, radius, depth, loc, segs=24):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=segs,
            radius1=radius, radius2=radius, depth=depth,
        )
        bm.to_mesh(me)
    finally:
        bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    bpy.context.collection.objects.link(ob)
    return ob


LAMP_X = 1.25          # lamps hang at x = -/+ LAMP_X from the stand's crossbar
PIVOT_Z = 1.80         # yoke pivot height (housing centre)
TILT_DEG = 30.0        # beam tipped from straight down toward the camera side


def lathe(name, profile, segs=48):
    """Revolve an (r, z) profile about local +Z; r == 0 makes a pole."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        rings = []
        for r, z in profile:
            if r == 0.0:
                rings.append([bm.verts.new((0.0, 0.0, z))])
            else:
                rings.append([bm.verts.new((r * math.cos(2 * math.pi * s / segs),
                                            r * math.sin(2 * math.pi * s / segs), z))
                              for s in range(segs)])
        for a, b in zip(rings, rings[1:]):
            for s in range(segs):
                t = (s + 1) % segs
                if len(a) == 1:
                    f = bm.faces.new((a[0], b[t], b[s]))
                elif len(b) == 1:
                    f = bm.faces.new((a[s], a[t], b[0]))
                else:
                    f = bm.faces.new((a[s], a[t], b[t], b[s]))
                f.smooth = True
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.set_sharp_from_angle(angle=math.radians(40.0))
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


# Stage-lamp can along local +Z (the beam axis): domed back cap, a finned
# body, a flared front rim. The lens sits just inside the rim.
LAMP_PROFILE = [(0.0, -0.36), (0.14, -0.35), (0.24, -0.31), (0.29, -0.24)]
for _k in range(5):                                   # five cooling fins
    _z = -0.20 + 0.075 * _k
    LAMP_PROFILE += [(0.29, _z), (0.335, _z + 0.012), (0.335, _z + 0.03), (0.29, _z + 0.042)]
LAMP_PROFILE += [(0.30, 0.20), (0.35, 0.24), (0.36, 0.30), (0.33, 0.31),
                 (0.30, 0.27), (0.0, 0.27)]


def build_lamp(name, x):
    """The ID under test: a stage-lamp housing. No ID property yet."""
    housing = lathe(f"{name}Lamp", LAMP_PROFILE)
    housing.location = (x, 0.0, PIVOT_Z)
    # beam axis (+Z) tipped down toward -Y (the camera side)
    housing.rotation_euler = (math.radians(180.0 - TILT_DEG), 0.0, 0.0)
    return housing


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    keep = build_lamp("Keep", -LAMP_X)
    clear = build_lamp("Clear", LAMP_X)
    return keep, clear


def remove_custom_property(id_block, key):
    if key not in id_block.keys():
        return False
    del id_block[key]
    return True


def check(keep_plate, clear_plate, skip_delete=False, unset_instead=False):
    if bpy.context.active_object is not None:
        print(
            "ERROR: expected no active_object after factory empty + data-API build; "
            "the snippet __main__ would have been dark for the same reason",
            file=sys.stderr,
        )
        return 9

    keep_plate[KEY] = VALUE
    clear_plate[KEY] = VALUE
    if KEY not in keep_plate.keys() or keep_plate[KEY] != VALUE:
        print(f"ERROR: ID property {KEY} did not land on Keep lamp", file=sys.stderr)
        return 3
    if KEY not in clear_plate.keys():
        print(f"ERROR: ID property {KEY} did not land on Clear lamp", file=sys.stderr)
        return 3

    try:
        keep_plate.property_unset(KEY)
        print("ERROR: property_unset on a custom ID key returned instead of TypeError",
              file=sys.stderr)
        return 4
    except TypeError as exc:
        print(f"property_unset TypeError={exc}")
    if KEY not in keep_plate.keys():
        print("ERROR: property_unset removed the ID property — it must not", file=sys.stderr)
        return 4

    if unset_instead:
        try:
            clear_plate.property_unset(KEY)
        except TypeError:
            pass
    elif not skip_delete:
        if not remove_custom_property(clear_plate, KEY):
            print("ERROR: del did not report removal", file=sys.stderr)
            return 5

    keep_has = KEY in keep_plate.keys()
    clear_has = KEY in clear_plate.keys()
    print(
        f"active_object=None keep_has={keep_has} clear_has={clear_has} "
        f"skip_delete={skip_delete} unset_instead={unset_instead}"
    )
    if not keep_has:
        print("ERROR: Keep lamp lost the ID property", file=sys.stderr)
        return 6
    if clear_has:
        print(
            "ERROR: Clear lamp still has the ID property — del did not run "
            "(property_unset is not a delete)",
            file=sys.stderr,
        )
        return 7
    return 0


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def principled(name, color, metallic, roughness, emission=None, strength=4.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission is not None:
        sock = bsdf.inputs.get("Emission Color") or bsdf.inputs["Emission"]
        sock.default_value = emission
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def assign(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


def label_font():
    """DejaVu Sans Mono ships in datafiles/fonts on 4.5 and 5.2 — code on the
    placards reads as code. system_resource resolves directories only."""
    fonts = bpy.utils.system_resource("DATAFILES", path="fonts")
    path = os.path.join(fonts, "DejaVuSansMono.woff2") if fonts else ""
    if path and os.path.exists(path):
        try:
            return bpy.data.fonts.load(path, check_existing=True)
        except RuntimeError:
            pass
    return None


def placard(name, text, x, mat_plate, mat_ink, scene):
    """A dark steel plate leaning on the floor under its lamp, code inlaid in brass."""
    plate = beveled_box(name, (2.05, 0.07, 0.42), 0.02)
    assign(plate, mat_plate)
    plate.location = (x, -1.05, 0.20)
    plate.rotation_euler = (math.radians(-40), 0.0, 0.0)
    cu = bpy.data.curves.new(f"{name}.Text", "FONT")
    cu.body = text
    cu.size = 0.15
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = 0.004
    font = label_font()
    if font is not None:
        cu.font = font
    cu.materials.append(mat_ink)
    t = bpy.data.objects.new(f"{name}.Text", cu)
    t.parent = plate
    t.location = (0.0, -0.04, 0.0)
    t.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(t)
    return [plate, t]


def render_still(keep, clear, path, engine):
    """Two stage lamps on one stand. Each lamp object is the ID the check
    ran against; the render reads its keys() and lights it only if the
    custom property is still there — an emissive lens and a real spot pool
    on the floor. Nothing here is staged from the expected outcome."""
    scene = bpy.context.scene
    powder = principled("PowderCoat", (0.028, 0.03, 0.034, 1.0), 0.35, 0.42)
    steel = principled("Steel", (0.20, 0.205, 0.22, 1.0), 1.0, 0.34)
    brass = principled("Brass", (0.86, 0.60, 0.26, 1.0), 1.0, 0.26)
    lens_on = principled("LensLit", (1.0, 0.86, 0.62, 1.0), 0.0, 0.1,
                         emission=(1.0, 0.72, 0.40, 1.0), strength=1.4)
    lens_off = principled("LensDark", (0.02, 0.022, 0.026, 1.0), 0.0, 0.06)
    plate_mat = principled("Placard", (0.035, 0.036, 0.04, 1.0), 0.7, 0.42)

    # stand: weighted base, post, crossbar, a drop stem per lamp
    parts = []
    base = lathe("StandBase", [(0.0, 0.0), (0.78, 0.0), (0.82, 0.03), (0.82, 0.09),
                               (0.74, 0.12), (0.16, 0.14), (0.0, 0.14)], segs=64)
    bar_z = PIVOT_Z + 0.57
    post = cylinder("StandPost", 0.06, bar_z - 0.10, (0.0, 0.0, 0.5 * (bar_z + 0.10)), segs=24)
    bar = cylinder("StandBar", 0.05, 2 * LAMP_X + 0.5, (0.0, 0.0, bar_z), segs=24)
    bar.rotation_euler = (0.0, math.pi / 2, 0.0)
    for ob in (base, post, bar):
        assign(ob, steel)
    parts += [base, post, bar]

    lit = []
    for lamp in (keep, clear):
        assign(lamp, powder)
        x = lamp.location.x
        stem = cylinder(f"{lamp.name}Stem", 0.035, 0.18, (x, 0.0, PIVOT_Z + 0.47), segs=16)
        # U-yoke: a top strap plus two cheeks bolted to the housing's sides
        strap = beveled_box(f"{lamp.name}Strap", (0.86, 0.10, 0.05), 0.012)
        strap.location = (x, 0.0, PIVOT_Z + 0.37)
        cheeks = []
        for sx in (-1.0, 1.0):
            ch = beveled_box(f"{lamp.name}Cheek", (0.05, 0.10, 0.40), 0.012)
            ch.location = (x + sx * 0.405, 0.0, PIVOT_Z + 0.18)
            knob = cylinder(f"{lamp.name}Knob", 0.06, 0.05, (x + sx * 0.45, 0.0, PIVOT_Z), segs=20)
            knob.rotation_euler = (0.0, math.pi / 2, 0.0)
            assign(knob, brass)
            cheeks += [ch, knob]
        for ob in (stem, strap) + tuple(c for c in cheeks if "Cheek" in c.name):
            assign(ob, steel)
        # lens and a brass bezel, parented to the housing along its +Z
        lens = cylinder(f"{lamp.name}Lens", 0.29, 0.02, (0.0, 0.0, 0.0), segs=48)
        lens.parent = lamp
        lens.location = (0.0, 0.0, 0.262)
        bezel = lathe(f"{lamp.name}Bezel", [(0.36, 0.30), (0.375, 0.315), (0.36, 0.33),
                                            (0.33, 0.33), (0.32, 0.31), (0.33, 0.30)],
                      segs=48)
        bezel.parent = lamp
        assign(bezel, brass)
        on = KEY in lamp.keys()
        assign(lens, lens_on if on else lens_off)
        parts += [stem, strap, lens, bezel] + cheeks
        if on:
            lit.append(lamp)

    bpy.context.view_layer.update()
    for lamp in lit:
        axis = (lamp.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
        sd = bpy.data.lights.new(f"{lamp.name}Beam", "SPOT")
        sd.energy = 1100.0
        sd.color = (1.0, 0.8, 0.52)
        sd.spot_size = math.radians(64.0)
        sd.spot_blend = 0.55
        sd.shadow_soft_size = 0.2
        beam = bpy.data.objects.new(f"{lamp.name}Beam", sd)
        beam.location = lamp.matrix_world.translation + axis * 0.36
        beam.rotation_euler = axis.to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(beam)

    labels = []
    labels += placard("KeepPlacard", f'obj["{KEY}"] = {VALUE}', keep.location.x,
                      plate_mat, brass, scene)
    labels += placard("ClearPlacard", f'del obj["{KEY}"]', clear.location.x,
                      plate_mat, brass, scene)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    floor_me.materials.append(principled("Studio", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7))
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.data.materials.clear()
    wall.data.materials.append(principled("Wall", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7))
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.pi / 2, 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", (-4.0, -5.0, 6.0), 380.0, 4.0, (1.0, 0.96, 0.9), (46, 0, -35))
    light("Fill", (5.0, -3.5, 3.0), 70.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.0, 3.5, 5.5), 220.0, 4.0, (0.62, 0.78, 1.0), (-42, 0, 180))
    light("Wedge", (2.5, 5.5, 4.0), 420.0, 6.0, (1.0, 0.72, 0.45), (-68, 0, 190))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, -0.3, 1.05)
    aim.hide_render = True
    scene.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 45.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.3, -7.2, 2.3)
    scene.collection.objects.link(cam)
    scene.camera = cam
    track = cam.constraints.new("TRACK_TO")
    track.target = aim
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 32
    else:
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    scene.view_settings.view_transform = "Standard"

    hero = [keep, clear] + parts
    fcode = gallery_framing.check_framing(
        scene, cam, hero=hero, elements=hero + labels, stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 12
    return 0


def check_registered(subscript=False):
    """Registered bpy.props vs ID properties: the 5.0 split (#354)."""
    split = bpy.app.version >= (5, 0, 0)
    bpy.types.Scene.bdt_counter = bpy.props.IntProperty(default=1)
    try:
        scene = bpy.context.scene
        scene.bdt_counter = 5
        if subscript:
            # The 4.x idiom: worked when registered values were ID properties.
            value = scene[REG]
        else:
            value = scene.bdt_counter
        in_keys = REG in scene.keys()
        sub_path = True
        try:
            scene.path_resolve(f'["{REG}"]')
        except ValueError:
            sub_path = False
        print(f"registered value={value} in_keys={in_keys} "
              f"subscript_path={sub_path} split={split}")
        if value != 5 or not scene.is_property_set(REG):
            print("ERROR: registered property did not read back by attribute",
                  file=sys.stderr)
            return 8
        if in_keys == split or sub_path == split:
            print(f"ERROR: expected registered props {'outside' if split else 'inside'} "
                  f"the ID-property group on {bpy.app.version_string}", file=sys.stderr)
            return 8
        if scene.path_resolve(REG) != 5:
            print("ERROR: plain data path did not resolve the registered prop",
                  file=sys.stderr)
            return 8
        scene.property_unset(REG)
        if scene.bdt_counter != 1 or scene.is_property_set(REG):
            print("ERROR: property_unset did not reset the registered prop",
                  file=sys.stderr)
            return 8
    except KeyError as exc:
        print(f"ERROR: KeyError {exc}: on 5.0+ a registered bpy.props value is "
              f"not an ID property; read it as scene.{REG}", file=sys.stderr)
        return 8
    finally:
        del bpy.types.Scene.bdt_counter
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument(
        "--skip-delete", action="store_true",
        help="falsification: leave the Clear lamp tagged",
    )
    p.add_argument(
        "--unset-instead", action="store_true",
        help="falsification: call property_unset instead of del",
    )
    p.add_argument(
        "--subscript-registered", action="store_true",
        help="falsification: read a registered prop as scene['name'] (exit 8 on 5.0+)",
    )
    args = p.parse_args(argv)

    keep, clear = build()
    code = check(
        keep, clear,
        skip_delete=args.skip_delete, unset_instead=args.unset_instead,
    )
    if code:
        return code
    code = check_registered(subscript=args.subscript_registered)
    if code:
        return code

    if args.output:
        rcode = render_still(keep, clear, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("cross-version-property-delete OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
