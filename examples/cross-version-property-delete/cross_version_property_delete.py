"""Custom ID-property delete — a runnable example.

Witnesses the contract the snippet ``cross-version-property-delete`` teaches,
not the snippet's ``__main__`` (which keys off ``context.active_object`` and
is dark headless). Builds the ID through ``bpy.data.objects.new`` and asserts:

1. ``obj["accession"] = 42`` lands in ``obj.keys()``.
2. ``property_unset("accession")`` is a TypeError and does **not** remove
   the ID property — that RNA call resets a registered property to default.
3. ``del obj["accession"]`` removes it. Same on 4.5 LTS and 5.x; no version
   branch.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python cross_version_property_delete.py --
    blender --background --python cross_version_property_delete.py -- --output t.png
"""
import bpy, bmesh, sys, os, math, argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True
import gallery_framing

KEY = "accession"
VALUE = 42


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


def build_tag(name, x, yaw):
    """Machined specimen tag: plate, pocket, hanging ring. No ID property yet."""
    plate = beveled_box(f"{name}Plate", (1.70, 0.10, 1.05), 0.035)
    plate.location = (x, 0.0, 1.15)
    plate.rotation_euler = (0.0, 0.0, yaw)
    pocket = beveled_box(f"{name}Pocket", (0.92, 0.04, 0.48), 0.02)
    pocket.parent = plate
    pocket.location = (0.18, -0.05, -0.03)
    ring = cylinder(f"{name}Ring", 0.11, 0.05, (0.0, 0.0, 0.0), segs=20)
    ring.parent = plate
    ring.location = (-0.68, 0.0, 0.33)
    ring.rotation_euler = (math.pi / 2, 0.0, 0.0)
    return plate, pocket, ring


def add_inlay(name, plate):
    """Emissive enamel only when the ID property is still on the plate."""
    inlay = beveled_box(f"{name}Inlay", (0.82, 0.03, 0.40), 0.015)
    inlay.parent = plate
    inlay.location = (0.18, -0.07, -0.03)
    return inlay


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    keep_parts = build_tag("Keep", -1.15, 0.0)
    clear_parts = build_tag("Clear", 1.15, 0.0)
    post = cylinder("StandPost", 0.07, 1.55, (0.0, 0.22, 0.78))
    base = beveled_box("StandBase", (3.4, 0.9, 0.12), 0.04)
    base.location = (0.0, 0.15, 0.06)
    bar = beveled_box("StandBar", (2.6, 0.08, 0.08), 0.02)
    bar.location = (0.0, 0.22, 1.52)
    return keep_parts, clear_parts, [post, base, bar]


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
        return 2

    keep_plate[KEY] = VALUE
    clear_plate[KEY] = VALUE
    if KEY not in keep_plate.keys() or keep_plate[KEY] != VALUE:
        print(f"ERROR: ID property {KEY} did not land on Keep plate", file=sys.stderr)
        return 3
    if KEY not in clear_plate.keys():
        print(f"ERROR: ID property {KEY} did not land on Clear plate", file=sys.stderr)
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
        print("ERROR: Keep plate lost the ID property", file=sys.stderr)
        return 6
    if clear_has:
        print(
            "ERROR: Clear plate still has the ID property — del did not run "
            "(property_unset is not a delete)",
            file=sys.stderr,
        )
        return 7
    return 0


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def principled(name, color, metallic, roughness, emission=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission is not None:
        sock = bsdf.inputs.get("Emission Color") or bsdf.inputs["Emission"]
        sock.default_value = emission
        bsdf.inputs["Emission Strength"].default_value = 4.5
    return mat


def assign(ob, mat):
    ob.data.materials.clear()
    ob.data.materials.append(mat)


def render_still(keep_parts, clear_parts, stand, path, engine):
    scene = bpy.context.scene
    brass = principled("Brass", (0.78, 0.50, 0.18, 1.0), 1.0, 0.22)
    pocket = principled("Pocket", (0.04, 0.042, 0.05, 1.0), 0.2, 0.55)
    enamel = principled(
        "Enamel", (0.02, 0.35, 0.55, 1.0), 0.0, 0.35,
        emission=(0.05, 0.55, 0.85, 1.0),
    )
    steel = principled("Steel", (0.18, 0.19, 0.21, 1.0), 1.0, 0.38)

    keep_plate, keep_pocket, keep_ring = keep_parts
    clear_plate, clear_pocket, clear_ring = clear_parts
    for ob in (keep_plate, keep_ring, clear_plate, clear_ring):
        assign(ob, brass)
    assign(keep_pocket, pocket)
    assign(clear_pocket, pocket)
    for ob in stand:
        assign(ob, steel)

    inlay = None
    if KEY in keep_plate.keys():
        inlay = add_inlay("Keep", keep_plate)
        assign(inlay, enamel)
    if KEY in clear_plate.keys():
        ghost = add_inlay("Clear", clear_plate)
        assign(ghost, enamel)

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

    light("Key", (-4.0, -5.0, 6.0), 520.0, 5.0, (1.0, 0.96, 0.9), (46, 0, -35))
    light("Fill", (5.0, -3.5, 3.0), 110.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Wedge", (2.5, 5.5, 4.0), 380.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))
    light("Glint", (1.6, -5.0, 6.0), 850.0, 0.9, (1.0, 0.9, 0.7), (40, 0, 18))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 1.15)
    aim.hide_render = True
    scene.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (3.55, -6.59, 3.30)
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
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    scene.view_settings.view_transform = "Standard"

    hero = [keep_plate, clear_plate, keep_ring, clear_ring] + list(stand)
    if inlay is not None:
        hero.append(inlay)
    fcode = gallery_framing.check_framing(
        scene, cam, hero=hero, elements=hero, stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 12
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument(
        "--skip-delete", action="store_true",
        help="falsification: leave the Clear plate tagged",
    )
    p.add_argument(
        "--unset-instead", action="store_true",
        help="falsification: call property_unset instead of del",
    )
    args = p.parse_args(argv)

    keep_parts, clear_parts, stand = build()
    code = check(
        keep_parts[0], clear_parts[0],
        skip_delete=args.skip_delete, unset_instead=args.unset_instead,
    )
    if code:
        return code

    if args.output:
        rcode = render_still(
            keep_parts, clear_parts, stand,
            os.path.abspath(args.output), args.engine,
        )
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
