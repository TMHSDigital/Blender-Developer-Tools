"""Geometry Nodes per-modifier input write — a runnable example.

Witnesses the 5.1→5.2 removal of dict assignment on a NODES modifier.
A shared GeometryNodeTree builds a spiral staircase from one exposed Float
"Height" socket: the tree derives the step count from the height, instances
the carrier mesh (one oak tread with its brass baluster) up a helix, and
adds a newel post and a helical handrail. Three carriers each get their own
modifier instance of that one tree. The check writes 1.0 / 2.0 / 3.0
through the version-appropriate path, reads the value back, and asserts
the evaluated Z-extent equals the written height (closed form: the newel
post runs from the floor at z=0 to exactly z=Height, and every other part
stays inside that span).

4.5 LTS and 5.1 write ``mod[identifier] = value``. 5.2+ removed ID
properties on NodesModifier — that assignment raises TypeError — and
the replacement is ``mod.properties.inputs.<identifier>.value``.
``--api dict`` / ``--api rna`` force one side of the 5.1/5.2 split — they
fail on the *other* series, not on every binary. ``--same-height`` writes
1.0 to every modifier and still asserts 1 / 2 / 3, so the second
staircase's readback fails on all three. That is the portable falsifier
(``--same-axis`` in export-preset-axis). ``--same-scale`` is kept as an
alias for the pre-staircase flag name.

    blender --background --python gn_modifier_inputs.py --
    blender --background --python gn_modifier_inputs.py -- --same-height
    blender --background --python gn_modifier_inputs.py -- --api dict
    blender --background --python gn_modifier_inputs.py -- --output s.png
"""
import argparse
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
)
import gallery_framing  # noqa: E402

HEIGHTS = (1.0, 2.0, 3.0)
# Stair footprint is ~1.3 m across (tread radius 0.62 + rail). 1.62 m
# centres leave ~0.3 m between neighbours. The check reads only Z extents,
# so the layout is free.
XS = (-1.62, 0.0, 1.62)
READBACK_EPS = 1e-6
EXTENT_EPS = 1e-4
INPUT_NAME = "Height"

# Staircase design constants (metres). The tree derives the step count
# from Height: n = round((Height - RAIL_H) / RISER), so 1 / 2 / 3 m give
# 7 / 17 / 27 treads at 22.5 degrees each (0.4 / 1.1 / 1.7 turns).
STEP_ANGLE = 2.0 * math.pi / 16.0
RISER = 0.1
RAIL_H = 0.3          # handrail centreline above each tread top, + RAIL_R
RAIL_R = 0.018        # handrail tube radius
TREAD_R = 0.62        # tread outer radius
TREAD_T = 0.045       # tread thickness
BALUSTER_R = TREAD_R - 0.07
POST_R = 0.065

# Render staging (render path only; the check never reads these).
CAM_LOC = (1.2, -8.6, 3.6)
CAM_AIM = (0.1, 0.0, 1.35)
KEY_LOC = (-6.5, -3.0, 5.0)
KEY_W = 560.0
KEY_SPREAD = 36.0
FILL_W = 45.0
RIM_W = 220.0
WEDGE_W = 520.0


def _api_choice(explicit):
    if explicit != "auto":
        return explicit
    return "rna" if bpy.app.version >= (5, 2, 0) else "dict"


def height_identifier(tree):
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


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def _bsdf(mat):
    mat.use_nodes = True
    return mat.node_tree.nodes["Principled BSDF"]


def make_oak():
    """Warm oak with a stretched-noise grain, so the treads are not flat fills."""
    mat = bpy.data.materials.new("Stair.Oak")
    bsdf = _bsdf(mat)
    nt = mat.node_tree
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (2.0, 2.0, 40.0)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    noise.inputs["Detail"].default_value = 6.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.3
    ramp.color_ramp.elements[0].color = (0.30, 0.11, 0.035, 1.0)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (0.58, 0.24, 0.06, 1.0)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    return mat


def make_brass():
    mat = bpy.data.materials.new("Stair.Brass")
    bsdf = _bsdf(mat)
    bsdf.inputs["Base Color"].default_value = (0.86, 0.58, 0.22, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.3
    return mat


def make_enamel():
    mat = bpy.data.materials.new("Stair.TealEnamel")
    bsdf = _bsdf(mat)
    bsdf.inputs["Base Color"].default_value = (0.02, 0.24, 0.26, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.25
    bsdf.inputs["Roughness"].default_value = 0.35
    return mat


# --------------------------------------------------------------------------
# Carrier mesh: one tread + its baluster, in the tread's local frame
# (tread top at z=0, centred on +X). The tree instances it up the helix.
# --------------------------------------------------------------------------

def make_tread_mesh(name, oak, brass):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        span = STEP_ANGLE * 0.94
        arc = 8
        verts = [bm.verts.new((0.03, 0.0, 0.0))]
        for k in range(arc + 1):
            a = -span / 2 + span * k / arc
            verts.append(bm.verts.new((TREAD_R * math.cos(a),
                                       TREAD_R * math.sin(a), 0.0)))
        top = bm.faces.new(verts)
        ext = bmesh.ops.extrude_face_region(bm, geom=[top])
        down = [v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=down, vec=(0.0, 0.0, -TREAD_T))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        # Round the walking edges: a chamfered tread, not a slab.
        outer = [e for e in bm.edges
                 if all(v.co.xy.length > 0.2 for v in e.verts)]
        bmesh.ops.bevel(bm, geom=outer, offset=0.008, segments=2,
                        profile=0.5, affect="EDGES", clamp_overlap=True)
        for f in bm.faces:
            f.material_index = 0

        bal_len = RAIL_H - RAIL_R
        before = set(bm.faces)
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=12,
            radius1=0.012, radius2=0.012, depth=bal_len,
            matrix=Matrix.Translation((BALUSTER_R, 0.0, bal_len / 2)),
        )
        for f in bm.faces:
            if f not in before:
                f.material_index = 1
                f.smooth = True
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(oak)
    me.materials.append(brass)
    return me


# --------------------------------------------------------------------------
# The shared tree: Height -> step count -> spiral staircase
# --------------------------------------------------------------------------

def _math(tree, op, a=None, b=None):
    n = tree.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            tree.links.new(v, n.inputs[i])
    return n.outputs[0]


def _vec(tree, x=0.0, y=0.0, z=None):
    n = tree.nodes.new("ShaderNodeCombineXYZ")
    n.inputs["X"].default_value = x
    n.inputs["Y"].default_value = y
    if z is not None and not isinstance(z, (int, float)):
        tree.links.new(z, n.inputs["Z"])
    elif z is not None:
        n.inputs["Z"].default_value = z
    return n.outputs["Vector"]


def _translate(tree, geo, vec):
    xf = tree.nodes.new("GeometryNodeTransform")
    tree.links.new(geo, xf.inputs["Geometry"])
    tree.links.new(vec, xf.inputs["Translation"])
    return xf.outputs["Geometry"]


def _set_mat(tree, geo, mat, smooth=False):
    sm = tree.nodes.new("GeometryNodeSetMaterial")
    sm.inputs["Material"].default_value = mat
    tree.links.new(geo, sm.inputs["Geometry"])
    out = sm.outputs["Geometry"]
    if smooth:
        ss = tree.nodes.new("GeometryNodeSetShadeSmooth")
        tree.links.new(out, ss.inputs["Geometry"])
        out = ss.outputs["Geometry"]
    return out


def _cylinder(tree, radius, depth, verts=32):
    cyl = tree.nodes.new("GeometryNodeMeshCylinder")
    cyl.inputs["Vertices"].default_value = verts
    cyl.inputs["Radius"].default_value = radius
    if isinstance(depth, (int, float)):
        cyl.inputs["Depth"].default_value = depth
    else:
        tree.links.new(depth, cyl.inputs["Depth"])
    return cyl.outputs["Mesh"]


def build_stair_tree(enamel, brass):
    tree = bpy.data.node_groups.new("SpiralStair", "GeometryNodeTree")
    tree.interface.new_socket(
        name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
    )
    h_sock = tree.interface.new_socket(
        name=INPUT_NAME, in_out="INPUT", socket_type="NodeSocketFloat"
    )
    h_sock.default_value = 1.0
    tree.interface.new_socket(
        name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
    )
    gi = tree.nodes.new("NodeGroupInput")
    go = tree.nodes.new("NodeGroupOutput")
    height = gi.outputs[INPUT_NAME]

    # Step count and the exact riser that lands the top tread on
    # Height - RAIL_H, so the handrail tops out at Height.
    climb = _math(tree, "SUBTRACT", height, RAIL_H)
    steps = _math(tree, "MAXIMUM",
                  _math(tree, "ROUND", _math(tree, "DIVIDE", climb, RISER)),
                  1.0)
    riser = _math(tree, "DIVIDE", climb, steps)

    # Treads: one point per step up the axis, each instance turned by
    # index * STEP_ANGLE.
    line = tree.nodes.new("GeometryNodeMeshLine")
    tree.links.new(steps, line.inputs["Count"])
    tree.links.new(_vec(tree, z=riser), line.inputs["Start Location"])
    tree.links.new(_vec(tree, z=riser), line.inputs["Offset"])
    index = tree.nodes.new("GeometryNodeInputIndex")
    turn = _math(tree, "MULTIPLY", index.outputs["Index"], STEP_ANGLE)
    iop = tree.nodes.new("GeometryNodeInstanceOnPoints")
    tree.links.new(line.outputs["Mesh"], iop.inputs["Points"])
    tree.links.new(gi.outputs["Geometry"], iop.inputs["Instance"])
    tree.links.new(_vec(tree, z=turn), iop.inputs["Rotation"])
    realize = tree.nodes.new("GeometryNodeRealizeInstances")
    tree.links.new(iop.outputs["Instances"], realize.inputs["Geometry"])
    treads = realize.outputs["Geometry"]

    # Newel post, floor to exactly Height, with a base plate and top collar.
    post = _translate(tree, _cylinder(tree, POST_R, height),
                      _vec(tree, z=_math(tree, "MULTIPLY", height, 0.5)))
    plate = _translate(tree, _cylinder(tree, 0.2, 0.03), _vec(tree, z=0.015))
    collar = _translate(tree, _cylinder(tree, POST_R + 0.02, 0.05),
                        _vec(tree, z=_math(tree, "SUBTRACT", height, 0.025)))
    post_join = tree.nodes.new("GeometryNodeJoinGeometry")
    for g in (collar, plate, post):
        tree.links.new(g, post_join.inputs["Geometry"])
    post_geo = _set_mat(tree, post_join.outputs["Geometry"], enamel, smooth=True)

    # Handrail: a helix through the baluster tops, one turn per 16 steps.
    spiral = tree.nodes.new("GeometryNodeCurveSpiral")
    spiral.inputs["Resolution"].default_value = 96
    spiral.inputs["Start Radius"].default_value = BALUSTER_R
    spiral.inputs["End Radius"].default_value = BALUSTER_R
    # The Spiral node winds clockwise by default; the treads climb
    # counter-clockwise (positive Z rotation), so reverse it.
    spiral.inputs["Reverse"].default_value = True
    last = _math(tree, "SUBTRACT", steps, 1.0)
    tree.links.new(_math(tree, "MULTIPLY", last, STEP_ANGLE / (2 * math.pi)),
                   spiral.inputs["Rotations"])
    tree.links.new(_math(tree, "MULTIPLY", last, riser),
                   spiral.inputs["Height"])
    profile = tree.nodes.new("GeometryNodeCurvePrimitiveCircle")
    profile.inputs["Resolution"].default_value = 12
    profile.inputs["Radius"].default_value = RAIL_R
    c2m = tree.nodes.new("GeometryNodeCurveToMesh")
    tree.links.new(spiral.outputs["Curve"], c2m.inputs["Curve"])
    tree.links.new(profile.outputs["Curve"], c2m.inputs["Profile Curve"])
    if "Fill Caps" in c2m.inputs:
        c2m.inputs["Fill Caps"].default_value = True
    rail_lift = _math(tree, "ADD", riser, RAIL_H - RAIL_R)
    rail = _set_mat(tree, _translate(tree, c2m.outputs["Mesh"],
                                     _vec(tree, z=rail_lift)),
                    brass, smooth=True)

    join = tree.nodes.new("GeometryNodeJoinGeometry")
    for g in (rail, post_geo, treads):
        tree.links.new(g, join.inputs["Geometry"])
    tree.links.new(join.outputs["Geometry"], go.inputs["Geometry"])
    return tree


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    oak, brass, enamel = make_oak(), make_brass(), make_enamel()
    tree = build_stair_tree(enamel, brass)
    objs = []
    mods = []
    for i, (x, h) in enumerate(zip(XS, HEIGHTS)):
        me = make_tread_mesh(f"Stair.Tread{i}", oak, brass)
        obj = bpy.data.objects.new(f"SpiralStair.H{int(h)}", me)
        obj.location = (x, 0.0, 0.0)
        bpy.context.collection.objects.link(obj)
        mod = obj.modifiers.new("stair_height", "NODES")
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


def check(tree, objs, mods, api, same_height=False):
    ident = height_identifier(tree)
    if not ident:
        print("ERROR: Height input identifier missing on the tree interface",
              file=sys.stderr)
        return 3
    print(f"api={api} blender={bpy.app.version} identifier={ident}")

    if len({mod.node_group for mod in mods}) != 1:
        print("ERROR: modifiers do not share one node_group", file=sys.stderr)
        return 4

    for obj, mod, height in zip(objs, mods, HEIGHTS):
        written = HEIGHTS[0] if same_height else height
        try:
            set_mod_input(mod, ident, written, api)
        except Exception as e:
            print(
                f"ERROR: {api} write of {height} on {obj.name} raised "
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
        if abs(got - height) > READBACK_EPS:
            print(
                f"ERROR: readback {got} != written {height} on {obj.name}",
                file=sys.stderr,
            )
            return 7

        zmin, zmax, nverts = evaluated_z_extent(obj)
        extent = zmax - zmin
        if abs(extent - height) > EXTENT_EPS:
            print(
                f"ERROR: evaluated Z-extent {extent:.6f} != height {height} "
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
            f"{obj.name} height={height} readback={got:.6f} "
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
    wall.location = (0.0, 8.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.02, 0.021, 0.025, 1.0
    )
    scene.world = world

    aim = bpy.data.objects.new("Aim", None)
    aim.location = CAM_AIM
    scene.collection.objects.link(aim)

    def light(name, loc, energy, size, col, spread=None):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        if spread is not None:
            # A shaped key: the spread keeps the pool on the stairs and
            # lets the floor fall off to the near-black stage.
            ld.spread = math.radians(spread)
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        scene.collection.objects.link(ob)
        lc = ob.constraints.new("TRACK_TO")
        lc.target = aim
        lc.track_axis = "TRACK_NEGATIVE_Z"
        lc.up_axis = "UP_Y"

    light("Key", KEY_LOC, KEY_W, 2.5, (1.0, 0.96, 0.9), KEY_SPREAD)
    light("Fill", (5.5, -4.0, 2.2), FILL_W, 9.0, (0.75, 0.85, 1.0))
    light("Rim", (0.5, 6.0, 6.5), RIM_W, 3.0, (0.6, 0.78, 1.0), 30.0)
    wedge = bpy.data.lights.new("Wedge", "AREA")
    wedge.energy = WEDGE_W
    wedge.size = 6.0
    wedge.color = (1.0, 0.76, 0.5)
    wob = bpy.data.objects.new("Wedge", wedge)
    wob.location = (1.8, 4.6, 4.6)
    wob.rotation_euler = (math.radians(-62), 0.0, math.radians(195))
    scene.collection.objects.link(wob)

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = CAM_LOC
    scene.collection.objects.link(cam)
    scene.camera = cam
    track = cam.constraints.new("TRACK_TO")
    track.target = aim
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    scene.render.engine = "CYCLES" if engine == "cycles" else eevee_engine_id()
    if engine == "cycles":
        scene.cycles.samples = 64
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    # Standard, not AgX: AgX pastels the oak and brass and greys the stage.
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
    p.add_argument(
        "--same-height", "--same-scale", dest="same_height", action="store_true",
        help="write 1.0 to every modifier (must fail)",
    )
    args = p.parse_args(argv)

    tree, objs, mods = build()
    api = _api_choice(args.api)
    code = check(tree, objs, mods, api, same_height=args.same_height)
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
