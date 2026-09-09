"""Geometry Nodes zone pairing — a runnable example.

Witnesses Repeat Zone and For Each Element from
``skills/geometry-nodes-python``: ``pair_with_output`` is load-bearing, and
the evaluated mesh must match a closed form. Tree-structure checks are
vacuous — a For Each whose Group Output reads the *main* Geometry socket
passes "nodes exist and are linked" while shipping the unevaluated grid.

Closed forms (cube = 8 verts / 6 faces):

* Repeat: start with one cube, each iteration Joins another translated by
  ``(Iteration + 1) * STEP``. verts = 8 * (1 + N), unique X-centers at
  ``k * STEP`` for k = 0..N.
* For Each Element: one cube per POINT, offset in Z by ``Index * STEP``.
  verts = 8 * P, unique Z-centers at ``i * STEP`` for i = 0..P-1.

Count alone is not enough: Joining N+1 cubes at the origin hits the vert
count with one X-center. The center axis is the second witness.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python gn_zone_iterate.py --
    blender --background --python gn_zone_iterate.py -- --output z.png
"""
import bpy, bmesh, sys, os, math, argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True
import gallery_framing

CUBE_VERTS = 8
CUBE_FACES = 6

REPEAT_N = 3
REPEAT_STEP = 1.2
REPEAT_SIZE = 0.55
REPEAT_VERTS = CUBE_VERTS * (1 + REPEAT_N)
REPEAT_FACES = CUBE_FACES * (1 + REPEAT_N)
REPEAT_CENTERS_X = [k * REPEAT_STEP for k in range(REPEAT_N + 1)]

FOREACH_P = 6
FOREACH_STEP = 0.60
FOREACH_SIZE = 0.42
FOREACH_VERTS = CUBE_VERTS * FOREACH_P
FOREACH_FACES = CUBE_FACES * FOREACH_P
FOREACH_CENTERS_Z = [i * FOREACH_STEP + FOREACH_SIZE / 2 for i in range(FOREACH_P)]


def sock(node, collection, identifier):
    for s in getattr(node, collection):
        if s.identifier == identifier:
            return s
    raise RuntimeError(f"{node.bl_idname} has no {collection} {identifier!r}")


def eval_mesh(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        coords = [(v.co.x, v.co.y, v.co.z) for v in me.vertices]
        faces = len(me.polygons)
    finally:
        ev.to_mesh_clear()
    return coords, faces


def centers_ok(coords, centers, half, axis):
    """Every vert on `axis` sits in exactly one center ± half; each center has 8 verts."""
    counts = [0] * len(centers)
    worst = 0.0
    for co in coords:
        val = co[axis]
        dists = [abs(val - c) for c in centers]
        i = min(range(len(centers)), key=lambda k: dists[k])
        worst = max(worst, dists[i])
        if dists[i] > half + 1e-3:
            return False, counts, dists[i]
        counts[i] += 1
    return all(c == CUBE_VERTS for c in counts), counts, worst


def build_repeat_tree(n, pair=True, offset=True, material=None):
    tree = bpy.data.node_groups.new("RepeatZone", "GeometryNodeTree")
    tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    go = tree.nodes.new("NodeGroupOutput")
    cube0 = tree.nodes.new("GeometryNodeMeshCube")
    cube0.inputs["Size"].default_value = (REPEAT_SIZE, REPEAT_SIZE, REPEAT_SIZE)
    rin = tree.nodes.new("GeometryNodeRepeatInput")
    rout = tree.nodes.new("GeometryNodeRepeatOutput")
    if pair:
        if not rin.pair_with_output(rout):
            raise RuntimeError("RepeatInput.pair_with_output failed")
    rin.inputs["Iterations"].default_value = n

    cube1 = tree.nodes.new("GeometryNodeMeshCube")
    cube1.inputs["Size"].default_value = (REPEAT_SIZE, REPEAT_SIZE, REPEAT_SIZE)
    join = tree.nodes.new("GeometryNodeJoinGeometry")
    shade = tree.nodes.new("GeometryNodeSetShadeSmooth")
    shade.inputs["Shade Smooth"].default_value = False

    added = cube1.outputs["Mesh"]
    if offset and pair:
        add = tree.nodes.new("ShaderNodeMath")
        add.operation = "ADD"
        add.inputs[1].default_value = 1.0
        mul = tree.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = REPEAT_STEP
        comb = tree.nodes.new("ShaderNodeCombineXYZ")
        xf = tree.nodes.new("GeometryNodeTransform")
        tree.links.new(rin.outputs["Iteration"], add.inputs[0])
        tree.links.new(add.outputs["Value"], mul.inputs[0])
        tree.links.new(mul.outputs["Value"], comb.inputs["X"])
        tree.links.new(cube1.outputs["Mesh"], xf.inputs["Geometry"])
        tree.links.new(comb.outputs["Vector"], xf.inputs["Translation"])
        added = xf.outputs["Geometry"]

    lift = tree.nodes.new("GeometryNodeTransform")
    lift.inputs["Translation"].default_value = (0.0, 0.0, REPEAT_SIZE / 2)

    if pair:
        tree.links.new(cube0.outputs["Mesh"], rin.inputs["Geometry"])
        tree.links.new(rin.outputs["Geometry"], join.inputs[0])
        tree.links.new(added, join.inputs[0])
        tree.links.new(join.outputs["Geometry"], rout.inputs["Geometry"])
        tree.links.new(rout.outputs["Geometry"], lift.inputs["Geometry"])
    else:
        # Unpaired Repeat Input has no Geometry sockets. Leave the output empty
        # so evaluation cannot silently pass the start cube through.
        pass

    tree.links.new(lift.outputs["Geometry"], shade.inputs["Geometry"])
    out = shade.outputs["Geometry"]
    if material is not None:
        sm = tree.nodes.new("GeometryNodeSetMaterial")
        sm.inputs["Material"].default_value = material
        tree.links.new(out, sm.inputs["Geometry"])
        out = sm.outputs["Geometry"]
    tree.links.new(out, go.inputs["Geometry"])
    return tree


def build_foreach_tree(count, pair=True, use_generation=True, material=None):
    tree = bpy.data.node_groups.new("ForEachZone", "GeometryNodeTree")
    tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    go = tree.nodes.new("NodeGroupOutput")
    line = tree.nodes.new("GeometryNodeMeshLine")
    line.inputs["Count"].default_value = count
    # degenerate line — elements exist; Index, not position, places the cubes
    line.inputs["Offset"].default_value = (0.0, 0.0, 0.0)

    fin = tree.nodes.new("GeometryNodeForeachGeometryElementInput")
    fout = tree.nodes.new("GeometryNodeForeachGeometryElementOutput")
    if pair:
        if not fin.pair_with_output(fout):
            raise RuntimeError("ForeachInput.pair_with_output failed")
    fout.domain = "POINT"

    cube = tree.nodes.new("GeometryNodeMeshCube")
    cube.inputs["Size"].default_value = (FOREACH_SIZE, FOREACH_SIZE, FOREACH_SIZE)
    mul = tree.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = FOREACH_STEP
    comb = tree.nodes.new("ShaderNodeCombineXYZ")
    sp = tree.nodes.new("GeometryNodeSetPosition")
    shade = tree.nodes.new("GeometryNodeSetShadeSmooth")
    shade.inputs["Shade Smooth"].default_value = False
    lift = tree.nodes.new("GeometryNodeTransform")
    lift.inputs["Translation"].default_value = (0.0, 0.0, FOREACH_SIZE / 2)

    tree.links.new(line.outputs["Mesh"], fin.inputs["Geometry"])
    tree.links.new(fin.outputs["Index"], mul.inputs[0])
    tree.links.new(mul.outputs["Value"], comb.inputs["Z"])
    tree.links.new(cube.outputs["Mesh"], sp.inputs["Geometry"])
    tree.links.new(comb.outputs["Vector"], sp.inputs["Offset"])

    if pair:
        gen_in = sock(fout, "inputs", "Generation_0")
        tree.links.new(sp.outputs["Geometry"], gen_in)
        if use_generation:
            body = sock(fout, "outputs", "Generation_0")
        else:
            body = fout.outputs["Geometry"]
        tree.links.new(body, lift.inputs["Geometry"])
    tree.links.new(lift.outputs["Geometry"], shade.inputs["Geometry"])
    out = shade.outputs["Geometry"]
    if material is not None:
        sm = tree.nodes.new("GeometryNodeSetMaterial")
        sm.inputs["Material"].default_value = material
        tree.links.new(out, sm.inputs["Geometry"])
        out = sm.outputs["Geometry"]
    tree.links.new(out, go.inputs["Geometry"])
    return tree


def principled(name, color, metallic, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def carrier(name):
    me = bpy.data.meshes.new(name)
    me.vertices.add(1)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def attach(obj, tree):
    mod = obj.modifiers.new("GN", "NODES")
    mod.node_group = tree
    return mod


def build(repeat_n, foreach_p, pair_repeat, pair_foreach, offset_repeat, foreach_generation):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    brass = principled("Brass", (0.86, 0.55, 0.16, 1.0), 0.85, 0.34)
    teal = principled("Teal", (0.08, 0.55, 0.58, 1.0), 0.15, 0.32)
    rpt = carrier("RepeatRow")
    fee = carrier("ForEachTower")
    rpt.location = (-2.80, 0.0, 0.0)
    fee.location = (2.20, 0.0, 0.0)
    attach(rpt, build_repeat_tree(repeat_n, pair=pair_repeat, offset=offset_repeat, material=brass))
    attach(fee, build_foreach_tree(
        foreach_p, pair=pair_foreach, use_generation=foreach_generation, material=teal,
    ))
    bpy.context.view_layer.update()
    return rpt, fee


def check(rpt, fee, expect_n, expect_p):
    if len(rpt.data.vertices) != 1 or len(fee.data.vertices) != 1:
        print("ERROR: carrier mesh was rewritten; zones must not apply in-place", file=sys.stderr)
        return 2

    r_coords, r_faces = eval_mesh(rpt)
    f_coords, f_faces = eval_mesh(fee)
    r_exp_v = CUBE_VERTS * (1 + expect_n)
    r_exp_f = CUBE_FACES * (1 + expect_n)
    f_exp_v = CUBE_VERTS * expect_p
    f_exp_f = CUBE_FACES * expect_p
    r_centers = [k * REPEAT_STEP for k in range(expect_n + 1)]
    f_centers = [i * FOREACH_STEP + FOREACH_SIZE / 2 for i in range(expect_p)]

    print(
        f"repeat verts={len(r_coords)} faces={r_faces} "
        f"foreach verts={len(f_coords)} faces={f_faces} "
        f"expect repeat={r_exp_v}/{r_exp_f} foreach={f_exp_v}/{f_exp_f}"
    )

    if len(r_coords) != r_exp_v or r_faces != r_exp_f:
        print(
            f"ERROR: Repeat evaluated {len(r_coords)}/{r_faces}, "
            f"closed form 8*(1+N)={r_exp_v}/{r_exp_f} with N={expect_n}",
            file=sys.stderr,
        )
        return 3
    ok, counts, worst = centers_ok(r_coords, r_centers, REPEAT_SIZE / 2, 0)
    if not ok:
        print(
            f"ERROR: Repeat X-centers {counts} worst={worst:.4f} "
            f"expected {CUBE_VERTS} verts at {r_centers}",
            file=sys.stderr,
        )
        return 4

    if len(f_coords) != f_exp_v or f_faces != f_exp_f:
        print(
            f"ERROR: For Each evaluated {len(f_coords)}/{f_faces}, "
            f"closed form 8*P={f_exp_v}/{f_exp_f} with P={expect_p}",
            file=sys.stderr,
        )
        return 5
    ok, counts, worst = centers_ok(f_coords, f_centers, FOREACH_SIZE / 2, 2)
    if not ok:
        print(
            f"ERROR: For Each Z-centers {counts} worst={worst:.4f} "
            f"expected {CUBE_VERTS} verts at {f_centers}",
            file=sys.stderr,
        )
        return 6

    print(
        f"repeat_N={expect_n} foreach_P={expect_p} "
        f"x_centers={r_centers} z_centers={f_centers} pairing=ok"
    )
    return 0


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def render_still(rpt, fee, path, engine):
    scene = bpy.context.scene

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    studio = principled("Studio", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7)
    floor_me.materials.append(studio)
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
    light("Fill", (5.0, -3.5, 3.0), 160.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Wedge", (2.5, 5.5, 4.0), 360.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))
    light("Glint", (0.4, -5.2, 5.5), 700.0, 0.9, (1.0, 0.92, 0.75), (42, 0, 8))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 1.50)
    aim.hide_render = True
    scene.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (6.6, -9.3, 3.55)
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

    hero = [rpt, fee]
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
    p.add_argument("--unpair-repeat", action="store_true")
    p.add_argument("--unpair-foreach", action="store_true")
    p.add_argument("--repeat-iterations", type=int, default=REPEAT_N)
    p.add_argument("--foreach-count", type=int, default=FOREACH_P)
    p.add_argument("--foreach-main", action="store_true",
                   help="falsification: Group Output reads For Each main Geometry")
    p.add_argument("--no-offset", action="store_true",
                   help="falsification: Repeat Join without Iteration translation")
    args = p.parse_args(argv)

    rpt, fee = build(
        args.repeat_iterations, args.foreach_count,
        pair_repeat=not args.unpair_repeat,
        pair_foreach=not args.unpair_foreach,
        offset_repeat=not args.no_offset,
        foreach_generation=not args.foreach_main,
    )
    code = check(rpt, fee, REPEAT_N, FOREACH_P)
    if code:
        return code

    if args.output:
        rcode = render_still(rpt, fee, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("gn-zone-iterate OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
