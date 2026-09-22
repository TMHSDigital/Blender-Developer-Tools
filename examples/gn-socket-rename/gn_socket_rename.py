"""GN Compare / Random Value socket identifier rename — a runnable example.

Witnesses the 5.2 collapse of typed sockets onto reused identifiers.
``FunctionNodeRandomValue`` FLOAT used ``Min_001`` / ``Max_001`` / ``Value_001``
on 4.5 LTS and 5.1; those identifiers are gone on 5.2 (``Min`` / ``Max`` /
``Value``). ``FunctionNodeCompare`` INT used ``A_INT`` / ``B_INT``; 5.2 reuses
``A`` / ``B``. Identifier-agnostic lookup (the unique *enabled* socket of a
given name) wires on all three. Hard-coding the pre-5.2 identifiers fails
on 5.2.

The tree is a jo-block: a plinth plus a column gated by Compare INT 7>2.
Random Value FLOAT (min=max=HEIGHT, so the value is a closed form, not an
RNG draw) is stored as POINT ``gauge_h`` on the column. Vert count is the
Compare axis (16 vs 8). ``gauge_h == HEIGHT`` on exactly eight verts is the
Random axis — count-only is green with Random unwired (the Store default
is 0). Random Value is a field; wiring it as a constant Size source
evaluates to 0, which is why the Store is the witness.

    blender --background --python gn_socket_rename.py --
    blender --background --python gn_socket_rename.py -- --legacy-ids
    blender --background --python gn_socket_rename.py -- --output g.png
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
sys.dont_write_bytecode = True
import gallery_framing  # noqa: E402

RENAMED_AT = (5, 2, 0)
HEIGHT = 1.80
COLUMN_XY = 0.55
PLINTH_SIZE = (1.35, 1.35, 0.14)
CMP_A = 7
CMP_B = 2
ZMAX_OK = PLINTH_SIZE[2] + HEIGHT  # 1.94
VERTS_OK = 16
VERTS_NO_COLUMN = 8
ATTR_NAME = "gauge_h"
ATTR_EPS = 1e-5
EXTENT_EPS = 1e-4

LEGACY_RV_MIN = "Min_001"
LEGACY_RV_MAX = "Max_001"
LEGACY_RV_OUT = "Value_001"
LEGACY_CMP_A = "A_INT"
LEGACY_CMP_B = "B_INT"


def fail(msg, code):
    print(f"ERROR: {msg}", file=sys.stderr)
    return code


def ident_sock(node, collection, identifier):
    for s in getattr(node, collection):
        if s.identifier == identifier:
            return s
    raise LookupError(
        f"{node.bl_idname} has no {collection} identifier {identifier!r}"
    )


def enabled_sock(node, collection, name):
    found = [
        s for s in getattr(node, collection)
        if s.name == name and s.enabled
    ]
    if len(found) != 1:
        raise LookupError(
            f"{node.bl_idname} {collection} enabled name={name!r} "
            f"count={len(found)}"
        )
    return found[0]


def identifiers(node, collection):
    return {s.identifier for s in getattr(node, collection)}


def eval_mesh(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        coords = [(v.co.x, v.co.y, v.co.z) for v in me.vertices]
        nfaces = len(me.polygons)
        attr = me.attributes.get(ATTR_NAME)
        if attr is None:
            attr_vals = []
        else:
            attr_vals = [0.0] * len(me.vertices)
            attr.data.foreach_get("value", attr_vals)
    finally:
        ev.to_mesh_clear()
    return coords, nfaces, attr_vals


def sock_pair(node, collection, name, legacy_id, legacy):
    if legacy:
        return ident_sock(node, collection, legacy_id)
    return enabled_sock(node, collection, name)


def build_tree(material_plinth, material_column, legacy_ids):
    tree = bpy.data.node_groups.new("SocketRenameGauge", "GeometryNodeTree")
    tree.interface.new_socket(
        name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry",
    )
    go = tree.nodes.new("NodeGroupOutput")

    plinth = tree.nodes.new("GeometryNodeMeshCube")
    plinth.inputs["Size"].default_value = PLINTH_SIZE
    plinth_xf = tree.nodes.new("GeometryNodeTransform")
    plinth_xf.inputs["Translation"].default_value = (
        0.0, 0.0, PLINTH_SIZE[2] / 2.0,
    )
    tree.links.new(plinth.outputs["Mesh"], plinth_xf.inputs["Geometry"])
    sm_p = tree.nodes.new("GeometryNodeSetMaterial")
    sm_p.inputs["Material"].default_value = material_plinth
    tree.links.new(plinth_xf.outputs["Geometry"], sm_p.inputs["Geometry"])

    column = tree.nodes.new("GeometryNodeMeshCube")
    column.inputs["Size"].default_value = (COLUMN_XY, COLUMN_XY, HEIGHT)
    rv = tree.nodes.new("FunctionNodeRandomValue")
    rv.data_type = "FLOAT"
    cmp = tree.nodes.new("FunctionNodeCompare")
    cmp.data_type = "INT"
    cmp.operation = "GREATER_THAN"

    smin = sock_pair(rv, "inputs", "Min", LEGACY_RV_MIN, legacy_ids)
    smax = sock_pair(rv, "inputs", "Max", LEGACY_RV_MAX, legacy_ids)
    sout = sock_pair(rv, "outputs", "Value", LEGACY_RV_OUT, legacy_ids)
    smin.default_value = HEIGHT
    smax.default_value = HEIGHT

    sa = sock_pair(cmp, "inputs", "A", LEGACY_CMP_A, legacy_ids)
    sb = sock_pair(cmp, "inputs", "B", LEGACY_CMP_B, legacy_ids)
    sa.default_value = CMP_A
    sb.default_value = CMP_B
    cmp_out = enabled_sock(cmp, "outputs", "Result")

    col_xf = tree.nodes.new("GeometryNodeTransform")
    col_xf.inputs["Translation"].default_value = (
        0.0, 0.0, PLINTH_SIZE[2] + HEIGHT / 2.0,
    )
    tree.links.new(column.outputs["Mesh"], col_xf.inputs["Geometry"])
    store = tree.nodes.new("GeometryNodeStoreNamedAttribute")
    store.data_type = "FLOAT"
    store.domain = "POINT"
    store.inputs["Name"].default_value = ATTR_NAME
    tree.links.new(col_xf.outputs["Geometry"], store.inputs["Geometry"])
    tree.links.new(sout, store.inputs["Value"])
    sm_c = tree.nodes.new("GeometryNodeSetMaterial")
    sm_c.inputs["Material"].default_value = material_column
    tree.links.new(store.outputs["Geometry"], sm_c.inputs["Geometry"])

    sw = tree.nodes.new("GeometryNodeSwitch")
    sw.input_type = "GEOMETRY"
    tree.links.new(cmp_out, enabled_sock(sw, "inputs", "Switch"))
    tree.links.new(sm_c.outputs["Geometry"], enabled_sock(sw, "inputs", "True"))

    join = tree.nodes.new("GeometryNodeJoinGeometry")
    tree.links.new(sm_p.outputs["Geometry"], join.inputs[0])
    tree.links.new(enabled_sock(sw, "outputs", "Output"), join.inputs[0])

    shade = tree.nodes.new("GeometryNodeSetShadeSmooth")
    shade.inputs["Shade Smooth"].default_value = False
    tree.links.new(join.outputs["Geometry"], shade.inputs["Geometry"])
    tree.links.new(shade.outputs["Geometry"], go.inputs["Geometry"])
    return tree, rv, cmp


def check_inventory(rv, cmp):
    ver = bpy.app.version
    legacy = ver < RENAMED_AT
    rv_in = identifiers(rv, "inputs")
    rv_out = identifiers(rv, "outputs")
    cmp_in = identifiers(cmp, "inputs")
    print(
        f"blender={ver} legacy_ids_present_expected={legacy} "
        f"rv_in={sorted(rv_in)} rv_out={sorted(rv_out)} "
        f"cmp_in={sorted(cmp_in)}"
    )
    old_rv = {LEGACY_RV_MIN, LEGACY_RV_MAX} <= rv_in and LEGACY_RV_OUT in rv_out
    old_cmp = {LEGACY_CMP_A, LEGACY_CMP_B} <= cmp_in
    print(f"old_random_ids={old_rv} old_compare_ids={old_cmp}")
    if legacy:
        if not old_rv:
            return fail("pre-5.2 Random Value identifiers missing", 4)
        if not old_cmp:
            return fail("pre-5.2 Compare INT identifiers missing", 4)
    else:
        if old_rv:
            return fail("pre-5.2 Random Value identifiers still present on 5.2+", 4)
        if old_cmp:
            return fail("pre-5.2 Compare INT identifiers still present on 5.2+", 4)
    return 0


def check(obj, rv, cmp, legacy_ids):
    code = check_inventory(rv, cmp)
    if code:
        return code

    bpy.context.view_layer.update()
    coords, nfaces, attr_vals = eval_mesh(obj)
    nverts = len(coords)
    zmax = max(c[2] for c in coords) if coords else float("-inf")
    n_hi = sum(1 for v in attr_vals if abs(v - HEIGHT) <= ATTR_EPS)
    n_lo = sum(1 for v in attr_vals if abs(v) <= ATTR_EPS)
    print(
        f"legacy_ids={legacy_ids} verts={nverts} faces={nfaces} "
        f"zmax={zmax:.6f} zmax_ok={ZMAX_OK:.6f} "
        f"gauge_h_hi={n_hi} gauge_h_lo={n_lo} attr_n={len(attr_vals)}"
    )
    if nverts != VERTS_OK:
        return fail(
            f"evaluated verts {nverts} != {VERTS_OK} "
            f"(Compare did not switch the column in; no-column={VERTS_NO_COLUMN})",
            7,
        )
    if abs(zmax - ZMAX_OK) > EXTENT_EPS:
        return fail(
            f"evaluated zmax {zmax:.6f} != {ZMAX_OK:.6f}",
            8,
        )
    if n_hi != 8 or n_lo != 8:
        return fail(
            f"POINT {ATTR_NAME} hi={n_hi} lo={n_lo} (want 8/8 at {HEIGHT}); "
            "Random Value did not land on the column",
            9,
        )
    return 0


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
        bsdf.inputs["Emission Strength"].default_value = 0.12
    return mat


def build(legacy_ids):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    steel = principled("PlinthSteel", (0.22, 0.23, 0.26, 1.0), 1.0, 0.32)
    copper = principled(
        "ColumnCopper", (0.93, 0.42, 0.08, 1.0), 1.0, 0.22,
        emission=(0.93, 0.42, 0.08, 1.0),
    )
    try:
        tree, rv, cmp = build_tree(steel, copper, legacy_ids)
    except LookupError as exc:
        return None, None, None, fail(str(exc), 5 if legacy_ids else 6)
    me = bpy.data.meshes.new("Gauge")
    obj = bpy.data.objects.new("Gauge", me)
    bpy.context.collection.objects.link(obj)
    mod = obj.modifiers.new("GN", "NODES")
    mod.node_group = tree
    obj.rotation_euler = (0.0, 0.0, math.radians(38))
    return obj, rv, cmp, 0


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


# Render path only. Graduations are engraved every TICK_MINOR up the column
# and heavier every TICK_MAJOR, measured from the plinth top.
TICK_MINOR = 0.1
TICK_MAJOR = 0.5
TICK_MINOR_HALF = 0.004
TICK_MAJOR_HALF = 0.009
# Ticks run in from each vertical corner, like the graduations on a gauge
# column. Full-width lines stacked the column into planks.
TICK_MINOR_LEN = 0.07
TICK_MAJOR_LEN = 0.16


def shader_math(nt, op, *inputs):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    for i, value in enumerate(inputs):
        if isinstance(value, (int, float)):
            node.inputs[i].default_value = value
        else:
            nt.links.new(value, node.inputs[i])
    return node.outputs[0]


def tick_mask(nt, height, spacing, half_width):
    """1 within half_width of a multiple of spacing, else 0."""
    frac = shader_math(nt, "FRACT", shader_math(nt, "DIVIDE", height, spacing))
    near = shader_math(nt, "MINIMUM", frac, shader_math(nt, "SUBTRACT", 1.0, frac))
    return shader_math(
        nt, "LESS_THAN", shader_math(nt, "MULTIPLY", near, spacing), half_width
    )


def dress_gauge(copper, steel):
    """Turn the jo-block into a height gauge, drawn from the witness.

    The graduations read the evaluated POINT ``gauge_h`` attribute, so the
    render witnesses the Random Value axis as well as the Compare axis: with
    Random unwired, the Store default leaves ``gauge_h`` at 0 on the column
    and the column renders blank. Nothing here feeds back into ``check``.
    """
    nt = copper.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = ATTR_NAME
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])

    height = shader_math(nt, "SUBTRACT", sep.outputs["Z"], PLINTH_SIZE[2])
    # Distance in from the nearest vertical corner, from the object-space
    # normal: on a side face one of |nx|, |ny| is 1 and the other 0.
    onrm = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Normal"], onrm.inputs["Vector"])
    across = shader_math(
        nt,
        "ADD",
        shader_math(
            nt,
            "MULTIPLY",
            shader_math(nt, "ABSOLUTE", sep.outputs["X"]),
            shader_math(nt, "ABSOLUTE", onrm.outputs["Y"]),
        ),
        shader_math(
            nt,
            "MULTIPLY",
            shader_math(nt, "ABSOLUTE", sep.outputs["Y"]),
            shader_math(nt, "ABSOLUTE", onrm.outputs["X"]),
        ),
    )
    inset = shader_math(nt, "SUBTRACT", COLUMN_XY / 2.0, across)
    lines = shader_math(
        nt,
        "MAXIMUM",
        shader_math(
            nt,
            "MULTIPLY",
            tick_mask(nt, height, TICK_MINOR, TICK_MINOR_HALF),
            shader_math(nt, "LESS_THAN", inset, TICK_MINOR_LEN),
        ),
        shader_math(
            nt,
            "MULTIPLY",
            tick_mask(nt, height, TICK_MAJOR, TICK_MAJOR_HALF),
            shader_math(nt, "LESS_THAN", inset, TICK_MAJOR_LEN),
        ),
    )
    # Side faces only (the top face sits on a tick by construction), and
    # only up to the stored gauge height.
    side = shader_math(
        nt, "LESS_THAN", shader_math(nt, "ABSOLUTE", onrm.outputs["Z"]), 0.5
    )
    stored = attr.outputs["Fac"]
    within = shader_math(
        nt, "LESS_THAN", height, shader_math(nt, "ADD", stored, 0.001)
    )
    engraved = shader_math(
        nt,
        "MULTIPLY",
        shader_math(nt, "MULTIPLY", lines, side),
        shader_math(nt, "MULTIPLY", within, shader_math(nt, "GREATER_THAN", stored, 0.5)),
    )

    # Brushed along the column: noise squeezed across it, stretched up it.
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (60.0, 60.0, 1.5)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    brush = nt.nodes.new("ShaderNodeTexNoise")
    brush.inputs["Scale"].default_value = 4.0
    brush.inputs["Detail"].default_value = 6.0
    nt.links.new(mapping.outputs["Vector"], brush.inputs["Vector"])
    rough = shader_math(
        nt,
        "MULTIPLY_ADD",
        engraved,
        0.45,
        shader_math(nt, "MULTIPLY_ADD", brush.outputs["Fac"], 0.10, 0.20),
    )
    nt.links.new(rough, bsdf.inputs["Roughness"])

    base = nt.nodes.new("ShaderNodeMix")
    base.data_type = "RGBA"
    nt.links.new(engraved, enabled_sock(base, "inputs", "Factor"))
    enabled_sock(base, "inputs", "A").default_value = (0.93, 0.42, 0.08, 1.0)
    enabled_sock(base, "inputs", "B").default_value = (0.05, 0.018, 0.006, 1.0)
    nt.links.new(enabled_sock(base, "outputs", "Result"), bsdf.inputs["Base Color"])
    emit = bsdf.inputs.get("Emission Color") or bsdf.inputs["Emission"]
    nt.links.new(enabled_sock(base, "outputs", "Result"), emit)
    # Brushed, the copper reflects less of the key and went brown at
    # thumbnail size; a little more of its own colour keeps it copper.
    bsdf.inputs["Emission Strength"].default_value = 0.24

    # Ground steel: lift it off the stage and give it a machined finish.
    sb = steel.node_tree.nodes["Principled BSDF"]
    # Fully metallic at 0.32 it mirrored the dark studio and read as a void.
    sb.inputs["Base Color"].default_value = (0.27, 0.28, 0.31, 1.0)
    sb.inputs["Metallic"].default_value = 0.8
    sb.inputs["Roughness"].default_value = 0.42


def render_still(obj, path, engine):
    scene = bpy.context.scene
    dress_gauge(bpy.data.materials["ColumnCopper"], bpy.data.materials["PlinthSteel"])
    # Presentation turn. At 38 degrees one column face sat square to the
    # camera and the gauge read as a flat card; at 18 two faces show and the
    # corner graduations wrap the edge. check() reads object-space vertices,
    # so the turn cannot reach an assertion.
    obj.rotation_euler = (0.0, 0.0, math.radians(18))

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = principled("Studio", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7)
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
        0.02, 0.021, 0.025, 1.0,
    )
    scene.world = world

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, ZMAX_OK * 0.45)
    aim.hide_render = True
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

    light("Key", (-3.4, -4.6, 5.4), 680.0, 4.2, (1.0, 0.96, 0.9))
    light("Fill", (4.8, -3.0, 2.2), 140.0, 8.0, (0.75, 0.85, 1.0))
    # At 300 W the rim's glossy reflection off the floor lifted the stage
    # right of the column to mid grey-blue (patch mean 104 against 62 with
    # the rim off); the column edge still separates at this level.
    light("Rim", (0.2, 5.8, 3.4), 120.0, 3.2, (0.6, 0.78, 1.0))
    light("Glint", (1.8, -4.8, 5.6), 900.0, 0.85, (1.0, 0.90, 0.70))
    wedge = bpy.data.lights.new("Wedge", "AREA")
    wedge.energy = 480.0
    wedge.size = 6.0
    wedge.color = (1.0, 0.72, 0.42)
    wob = bpy.data.objects.new("Wedge", wedge)
    wob.location = (2.2, 5.2, 3.8)
    wob.rotation_euler = (math.radians(-68), 0.0, math.radians(190))
    scene.collection.objects.link(wob)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (4.15, -5.85, 2.55)
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
        hero=[obj],
        elements=[obj],
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
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument(
        "--legacy-ids",
        action="store_true",
        help="falsification: wire Compare/Random Value by pre-5.2 identifiers",
    )
    args = p.parse_args(argv)

    obj, rv, cmp, code = build(args.legacy_ids)
    if code:
        return code

    code = check(obj, rv, cmp, args.legacy_ids)
    if code:
        return code

    if args.output:
        rcode = render_still(obj, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("gn-socket-rename OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
