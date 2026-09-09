"""Geometry Nodes per-modifier input write — a runnable example.

Witnesses the 5.1→5.2 removal of dict assignment on a NODES modifier.
A shared GeometryNodeTree exposes a Float "Scale" socket. Three carrier
cubes each get their own modifier instance of that tree. The check writes
1.0 / 2.0 / 3.0 through the version-appropriate path, reads the value
back, and asserts the evaluated Z-extent equals the written scale
(closed form: a 1 m cube scaled by S and lifted by S/2 spans [0, S]).

4.5 LTS and 5.1 write ``mod[identifier] = value``. 5.2+ removed ID
properties on NodesModifier — that assignment raises TypeError — and
the replacement is ``mod.properties.inputs.<identifier>.value``.
``--api dict`` / ``--api rna`` force one side so the witness can fail
on purpose.

    blender --background --python gn_modifier_inputs.py --
    blender --background --python gn_modifier_inputs.py -- --api dict
    blender --background --python gn_modifier_inputs.py -- --output s.png
"""
import argparse
import math
import os
import sys

import bmesh
import bpy

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
)
import gallery_framing  # noqa: E402

CUBE_SIZE = 1.0
SCALES = (1.0, 2.0, 3.0)
# Half-widths 0.5 / 1.0 / 1.5; keep a clear gap, keep the 3 m cube off the right edge.
XS = (-2.2, 0.15, 2.45)
COLORS = (
    (0.05, 0.62, 0.58, 1.0),  # teal
    (0.82, 0.38, 0.08, 1.0),  # copper
    (0.86, 0.18, 0.22, 1.0),  # coral
)
READBACK_EPS = 1e-6
EXTENT_EPS = 1e-4
INPUT_NAME = "Scale"


def _api_choice(explicit):
    if explicit != "auto":
        return explicit
    return "rna" if bpy.app.version >= (5, 2, 0) else "dict"


def scale_identifier(tree):
    for item in tree.interface.items_tree:
        if getattr(item, "item_type", "SOCKET") not in ("SOCKET",):
            continue
        if getattr(item, "in_out", None) == "INPUT" and item.name == INPUT_NAME:
            return item.identifier
    return None


def set_mod_input(mod, ident, value, api):
    if api == "dict":
        mod[ident] = value
        return
    sock = getattr(mod.properties.inputs, ident)
    sock.value = value


def get_mod_input(mod, ident, api):
    if api == "dict":
        return float(mod[ident])
    sock = getattr(mod.properties.inputs, ident)
    return float(sock.value)


def make_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.28
    bsdf.inputs["Metallic"].default_value = 0.35
    return mat


def make_cube_mesh(name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=CUBE_SIZE)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def build_scale_tree(material=None):
    tree = bpy.data.node_groups.new("ModifierScale", "GeometryNodeTree")
    tree.interface.new_socket(
        name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
    )
    scale_sock = tree.interface.new_socket(
        name=INPUT_NAME, in_out="INPUT", socket_type="NodeSocketFloat"
    )
    scale_sock.default_value = 1.0
    tree.interface.new_socket(
        name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
    )
    gi = tree.nodes.new("NodeGroupInput")
    go = tree.nodes.new("NodeGroupOutput")
    combine = tree.nodes.new("ShaderNodeCombineXYZ")
    xform = tree.nodes.new("GeometryNodeTransform")
    shade = tree.nodes.new("GeometryNodeSetShadeSmooth")
    shade.inputs["Shade Smooth"].default_value = False

    tree.links.new(gi.outputs[INPUT_NAME], combine.inputs["X"])
    tree.links.new(gi.outputs[INPUT_NAME], combine.inputs["Y"])
    tree.links.new(gi.outputs[INPUT_NAME], combine.inputs["Z"])
    tree.links.new(gi.outputs["Geometry"], xform.inputs["Geometry"])
    tree.links.new(combine.outputs["Vector"], xform.inputs["Scale"])
    # Lift by S/2 so a cube of extent S sits on z=0.
    # Translation is a vector; drive Z from the same Scale socket via Combine.
    lift = tree.nodes.new("ShaderNodeCombineXYZ")
    scale_half = tree.nodes.new("ShaderNodeMath")
    scale_half.operation = "MULTIPLY"
    scale_half.inputs[1].default_value = 0.5
    tree.links.new(gi.outputs[INPUT_NAME], scale_half.inputs[0])
    tree.links.new(scale_half.outputs[0], lift.inputs["Z"])
    tree.links.new(lift.outputs["Vector"], xform.inputs["Translation"])

    tree.links.new(xform.outputs["Geometry"], shade.inputs["Geometry"])
    out_socket = shade.outputs["Geometry"]
    if material is not None:
        set_mat = tree.nodes.new("GeometryNodeSetMaterial")
        set_mat.inputs["Material"].default_value = material
        tree.links.new(out_socket, set_mat.inputs["Geometry"])
        out_socket = set_mat.outputs["Geometry"]
    tree.links.new(out_socket, go.inputs["Geometry"])
    return tree


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = [
        make_material("TealScale", COLORS[0]),
        make_material("CopperScale", COLORS[1]),
        make_material("CoralScale", COLORS[2]),
    ]
    # One shared tree; Set Material is applied per-object via the mesh slot
    # rather than inside the group so the group stays parameter-only.
    tree = build_scale_tree(material=None)
    objs = []
    mods = []
    for i, (x, mat) in enumerate(zip(XS, mats)):
        me = make_cube_mesh(f"Carrier{i}")
        me.materials.append(mat)
        obj = bpy.data.objects.new(f"Scale{int(SCALES[i])}", me)
        obj.location = (x, 0.0, 0.0)
        bpy.context.collection.objects.link(obj)
        mod = obj.modifiers.new("scale_input", "NODES")
        mod.node_group = tree
        objs.append(obj)
        mods.append(mod)
    return tree, objs, mods


def evaluated_z_extent(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    em = ev.to_mesh()
    try:
        zs = [v.co.z for v in em.vertices]
        if not zs:
            return 0.0, 0.0, 0
        return min(zs), max(zs), len(em.vertices)
    finally:
        ev.to_mesh_clear()


def check(tree, objs, mods, api):
    ident = scale_identifier(tree)
    if not ident:
        print("ERROR: Scale input identifier missing on the tree interface",
              file=sys.stderr)
        return 3
    print(f"api={api} blender={bpy.app.version} identifier={ident}")

    if len({mod.node_group for mod in mods}) != 1:
        print("ERROR: modifiers do not share one node_group", file=sys.stderr)
        return 4

    for obj, mod, scale in zip(objs, mods, SCALES):
        try:
            set_mod_input(mod, ident, scale, api)
        except Exception as e:
            print(
                f"ERROR: {api} write of {scale} on {obj.name} raised "
                f"{type(e).__name__}: {e}",
                file=sys.stderr,
            )
            return 5
        obj.update_tag()
        bpy.context.view_layer.update()
        try:
            got = get_mod_input(mod, ident, api)
        except Exception as e:
            print(
                f"ERROR: {api} read of {obj.name} raised "
                f"{type(e).__name__}: {e}",
                file=sys.stderr,
            )
            return 6
        if abs(got - scale) > READBACK_EPS:
            print(
                f"ERROR: readback {got} != written {scale} on {obj.name}",
                file=sys.stderr,
            )
            return 7

        zmin, zmax, nverts = evaluated_z_extent(obj)
        extent = zmax - zmin
        if abs(extent - scale) > EXTENT_EPS:
            print(
                f"ERROR: evaluated Z-extent {extent:.6f} != scale {scale} "
                f"on {obj.name} (z=[{zmin:.4f},{zmax:.4f}] verts={nverts})",
                file=sys.stderr,
            )
            return 8
        if abs(zmin) > EXTENT_EPS:
            print(
                f"ERROR: evaluated mesh not sitting on z=0 "
                f"({obj.name} zmin={zmin:.4f})",
                file=sys.stderr,
            )
            return 9
        print(
            f"{obj.name} scale={scale} readback={got:.6f} "
            f"z_extent={extent:.6f} zmin={zmin:.6f} verts={nverts}"
        )

    extents = []
    for obj in objs:
        zmin, zmax, _ = evaluated_z_extent(obj)
        extents.append(zmax - zmin)
    if len(set(round(e, 4) for e in extents)) != 3:
        print(
            f"ERROR: evaluated extents not distinct {extents} — "
            "per-modifier copies did not land",
            file=sys.stderr,
        )
        return 11
    return 0


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def render_still(objs, path, engine):
    scene = bpy.context.scene

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
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02, 0.021, 0.025, 1.0
    )
    scene.world = world

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.35, 0.0, 1.25)
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

    light("Key", (-3.8, -5.0, 6.2), 560.0, 5.0, (1.0, 0.96, 0.9))
    light("Fill", (5.4, -3.2, 2.4), 110.0, 8.0, (0.75, 0.85, 1.0))
    light("Rim", (0.4, 6.4, 3.8), 280.0, 3.5, (0.6, 0.78, 1.0))
    wedge = bpy.data.lights.new("Wedge", "AREA")
    wedge.energy = 420.0
    wedge.size = 6.0
    wedge.color = (1.0, 0.76, 0.5)
    wob = bpy.data.objects.new("Wedge", wedge)
    wob.location = (2.4, 5.6, 4.2)
    wob.rotation_euler = (math.radians(-68), 0.0, math.radians(190))
    scene.collection.objects.link(wob)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (8.1, -10.8, 5.05)
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

    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=list(objs),
        elements=list(objs),
        stage=[floor, wall],
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
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument(
        "--engine", default="eevee", choices=("eevee", "cycles"),
        help="render engine for --output (cycles for GPU-less hosts)",
    )
    p.add_argument(
        "--api", default="auto", choices=("auto", "dict", "rna"),
        help="force the 5.1 dict path, the 5.2 RNA path, or pick from bpy.app.version",
    )
    args = p.parse_args(argv)

    tree, objs, mods = build()
    api = _api_choice(args.api)
    code = check(tree, objs, mods, api)
    if code:
        return code

    if args.output:
        rcode = render_still(objs, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("gn-modifier-inputs OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
