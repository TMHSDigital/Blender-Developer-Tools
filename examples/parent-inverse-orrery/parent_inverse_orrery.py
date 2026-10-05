"""A brass orrery parented through the data API — a runnable example.

Witnesses the object-parenting contract that generated code gets wrong most
often. Assigning `child.parent = pivot` alone re-interprets the child's local
matrix in the pivot's space, so the child visibly teleports; keeping the world
transform requires the two-line idiom:

    child.parent = pivot
    child.matrix_parent_inverse = pivot.matrix_world.inverted()

The check demonstrates the trap on a probe (it really does jump), proves the
idiom restores the world position exactly, and asserts the second contract AI
code trips over: `matrix_world` is the *last-evaluated* matrix — after any
transform edit it is stale until `bpy.context.view_layer.update()`. Finally
every planet and the moon must land on the closed-form orbit position
(rotation about the column axis, composed per hierarchy level).

``--skip-mpi`` parents without ``matrix_parent_inverse`` and still asserts
closed-form orbits. That is the falsifier (``--same-axis`` in
export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python parent_inverse_orrery.py --                   # check only
    blender --background --python parent_inverse_orrery.py -- --skip-mpi        # must fail
    blender --background --python parent_inverse_orrery.py -- --output o.png    # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector, Matrix

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

# (name, orbit radius, arm height, orbit angle deg, sphere radius, color RGBA)
PLANETS = [
    ("Lapis", 2.55, 1.02, 152.0, 0.34, (0.04, 0.10, 0.42, 1.0)),
    ("Terra", 1.85, 1.58, 336.0, 0.26, (0.48, 0.16, 0.07, 1.0)),
    ("Jade", 1.20, 2.12, 38.0, 0.20, (0.05, 0.33, 0.20, 1.0)),
]
MOON_HOST = "Lapis"           # the moon orbits the outer planet
MOON_OFFSET = 0.62            # distance from its planet, along local +X
# moon-pivot spin, degrees: with Lapis at 152 the moon lands at 210 world,
# out past the planet's flank instead of in front of the arm feeding it
MOON_ANGLE = 58.0
MOON_R = 0.12
PEDESTAL_TOP = 0.22
COLUMN_TOP = 2.45
SUN_Z = 2.62
RISER_GAP = 0.16              # arm runs this far below the planet's underside
EPS = 1e-5


def new_mesh_obj(name, build):
    """Mesh object via bmesh with bm.free() in try/finally (always-free-bmesh)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        build(bm)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def cylinder(name, radius, depth, segments=24):
    return new_mesh_obj(name, lambda bm: bmesh.ops.create_cone(
        bm, cap_ends=True, segments=segments,
        radius1=radius, radius2=radius, depth=depth))


def sphere(name, radius):
    return new_mesh_obj(name, lambda bm: bmesh.ops.create_uvsphere(
        bm, u_segments=32, v_segments=16, radius=radius))


def lathe(name, profile, segments=64):
    """Turned part: spin an (r, z) profile about Z, welding the axis seam."""
    def build(bm):
        vs = [bm.verts.new((r, 0.0, z)) for r, z in profile]
        edges = [bm.edges.new((a, b)) for a, b in zip(vs, vs[1:])]
        bmesh.ops.spin(bm, geom=vs + edges, cent=(0, 0, 0), axis=(0, 0, 1),
                       angle=2 * math.pi, steps=segments, use_merge=True)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_mesh_obj(name, build)


def empty(name, location):
    obj = bpy.data.objects.new(name, None)  # object_data=None -> EMPTY
    obj.location = location
    bpy.context.collection.objects.link(obj)
    return obj


def parent_keep_world(child, parent, skip_mpi=False):
    """The idiom this example witnesses: parent without moving the child."""
    child.parent = parent
    if not skip_mpi:
        child.matrix_parent_inverse = parent.matrix_world.inverted()


def build_orrery(skip_mpi=False):
    """Author the whole hierarchy with bpy.data (no object-mode operators)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # stepped, moulded foot turned in one profile; top face at PEDESTAL_TOP
    pedestal = lathe("Pedestal", [
        (0.0, 0.0), (1.22, 0.0), (1.24, 0.02), (1.24, 0.07), (1.20, 0.085),
        (1.06, 0.09), (1.02, 0.11), (1.02, 0.15), (0.96, 0.17), (0.60, 0.19),
        (0.30, 0.205), (0.16, PEDESTAL_TOP), (0.0, PEDESTAL_TOP)])
    column = cylinder("Column", 0.07, COLUMN_TOP - PEDESTAL_TOP, segments=24)
    column.location = (0.0, 0.0, (PEDESTAL_TOP + COLUMN_TOP) / 2)
    sun = sphere("Sun", 0.28)
    sun.location = (0.0, 0.0, SUN_Z)

    rig = {"sun": sun, "pedestal": pedestal, "planets": {}}
    for name, radius, height, angle, size, color in PLANETS:
        pivot = empty(f"Pivot.{name}", (0.0, 0.0, height))
        # the arm runs under the planet and a riser post carries it up, so the
        # orbit ring drawn at arm height passes beneath the sphere, not through
        drop = size + RISER_GAP
        arm = cylinder(f"Arm.{name}", 0.035, radius, segments=12)
        arm.rotation_euler = (0.0, math.pi / 2, 0.0)
        arm.location = (radius / 2, 0.0, height - drop)
        riser = cylinder(f"Riser.{name}", 0.026, drop, segments=12)
        riser.location = (radius, 0.0, height - drop / 2)
        cup = lathe(f"Cup.{name}", [(0.0, -0.05), (0.05, -0.05), (0.075, 0.0),
                                    (0.0, 0.0)], segments=24)
        cup.location = (radius, 0.0, height - size * 0.94)
        planet = sphere(name, size)
        planet.location = (radius, 0.0, height)
        # everything is placed at its theta=0 WORLD position first, then
        # parented with the keep-world idiom -- nothing may move here
        bpy.context.view_layer.update()
        for part in (arm, riser, cup, planet):
            parent_keep_world(part, pivot, skip_mpi=skip_mpi)
        rig["planets"][name] = {
            "pivot": pivot, "planet": planet, "angle": math.radians(angle),
            "p0": Vector((radius, 0.0, height)),
        }

    host = rig["planets"][MOON_HOST]
    pc0 = host["p0"].copy()
    moon_pivot = empty("Pivot.Moon", pc0)
    rod = cylinder("Arm.Moon", 0.026, MOON_OFFSET, segments=12)
    rod.rotation_euler = (0.0, math.pi / 2, 0.0)
    rod.location = pc0 + Vector((MOON_OFFSET / 2, 0.0, 0.0))
    moon = sphere("Moon", MOON_R)
    moon.location = pc0 + Vector((MOON_OFFSET, 0.0, 0.0))
    bpy.context.view_layer.update()
    parent_keep_world(moon_pivot, host["planet"], skip_mpi=skip_mpi)
    parent_keep_world(rod, moon_pivot, skip_mpi=skip_mpi)
    parent_keep_world(moon, moon_pivot, skip_mpi=skip_mpi)
    rig["moon"] = {"pivot": moon_pivot, "moon": moon,
                   "angle": math.radians(MOON_ANGLE), "pc0": pc0,
                   "m0": pc0 + Vector((MOON_OFFSET, 0.0, 0.0))}

    # spin every orbit to its display angle -- the parenting must carry
    # arms, planets, and the moon assembly along
    for entry in rig["planets"].values():
        entry["pivot"].rotation_euler = (0.0, 0.0, entry["angle"])
    rig["moon"]["pivot"].rotation_euler = (0.0, 0.0, rig["moon"]["angle"])
    bpy.context.view_layer.update()
    return rig


def rot_z(theta, v):
    """Closed form: rotate v about the column (Z) axis, z untouched."""
    c, s = math.cos(theta), math.sin(theta)
    return Vector((c * v.x - s * v.y, s * v.x + c * v.y, v.z))


def check(rig):
    view_layer = bpy.context.view_layer
    outer = rig["planets"][MOON_HOST]

    # --- 1. the trap is real: bare `.parent =` teleports the child ---------
    probe = empty("Probe", (1.618, 0.0, 1.0))
    view_layer.update()
    w0 = probe.matrix_world.translation.copy()
    probe.parent = outer["pivot"]  # pivot has a rotation + Z offset
    view_layer.update()
    jumped = (probe.matrix_world.translation - w0).length
    if jumped < 0.5:
        print(f"ERROR: bare parenting moved the probe only {jumped:.6f} — "
              "expected a visible jump", file=sys.stderr)
        return 3

    # --- 2. the fix: matrix_parent_inverse restores the world transform ----
    probe.matrix_parent_inverse = outer["pivot"].matrix_world.inverted()
    view_layer.update()
    err = (probe.matrix_world.translation - w0).length
    if err > EPS:
        print(f"ERROR: keep-world idiom off by {err:.8f}", file=sys.stderr)
        return 4

    # --- 3. matrix_world is stale until view_layer.update() ----------------
    before = probe.matrix_world.translation.copy()
    probe.location.x += 1.0
    stale = (probe.matrix_world.translation - before).length
    view_layer.update()
    fresh = (probe.matrix_world.translation - before).length
    if stale > EPS or fresh < 0.5:
        print(f"ERROR: stale-matrix contract broken (stale moved {stale:.8f}, "
              f"updated moved {fresh:.6f})", file=sys.stderr)
        return 5
    bpy.data.objects.remove(probe)
    view_layer.update()

    # --- 4. every orbit lands on its closed form ----------------------------
    for name, entry in rig["planets"].items():
        expect = rot_z(entry["angle"], entry["p0"])
        got = entry["planet"].matrix_world.translation
        if (got - expect).length > EPS:
            print(f"ERROR: {name} at {tuple(got)}, closed form {tuple(expect)}",
                  file=sys.stderr)
            return 6

    # moon: rotation about the column, then about its planet
    m = rig["moon"]
    theta1 = outer["angle"]
    pc = rot_z(theta1, m["pc0"])
    expect = pc + rot_z(theta1 + m["angle"], m["m0"] - m["pc0"])
    got = m["moon"].matrix_world.translation
    if (got - expect).length > EPS:
        print(f"ERROR: Moon at {tuple(got)}, closed form {tuple(expect)}",
              file=sys.stderr)
        return 7

    print(f"planets={len(rig['planets'])} moon=1 keep-world err={err:.2e} "
          f"orbit closed-form OK")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def principled(name, color, metallic, roughness, emission=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def mottled(name, color, roughness, scale, emission=0.0, hi=None):
    """Principled whose base colour wanders between a darker shade of `color`
    and `hi` on object-space noise, with a matching faint bump — a planet
    that reads as a mineral, not a billiard ball. Emission (the sun) takes
    the same mottle."""
    mat = principled(name, color, 0.0, roughness, emission=emission)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    lo = tuple(c * 0.6 for c in color[:3]) + (1.0,)
    hi = hi or tuple(min(1.0, c * 1.3) for c in color[:3]) + (1.0,)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = lo
    ramp.color_ramp.elements[1].position = 0.68
    ramp.color_ramp.elements[1].color = hi
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if emission:
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Emission Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def orbit_ring(name, radius, height, mat):
    """Decorative brass orbit line: a bevelled circle curve (data API)."""
    cu = bpy.data.curves.new(name, type='CURVE')
    cu.dimensions = '3D'
    spline = cu.splines.new('POLY')
    spline.points.add(63)
    for i, pt in enumerate(spline.points):
        a = i * 2 * math.pi / 64
        pt.co = (radius * math.cos(a), radius * math.sin(a), 0.0, 1.0)
    spline.use_cyclic_u = True
    cu.bevel_depth = 0.012
    cu.materials.append(mat)
    obj = bpy.data.objects.new(name, cu)
    obj.location = (0.0, 0.0, height)
    bpy.context.collection.objects.link(obj)
    return obj


def render_still(rig, path, engine):
    scene = bpy.context.scene
    brass = principled("Brass", (0.62, 0.40, 0.16, 1.0), 1.0, 0.32)
    # lacquered walnut foot: a metal base mirrored the black stage and vanished
    dark_bronze = principled("Walnut", (0.075, 0.034, 0.016, 1.0), 0.0, 0.2)
    # At emission 3.2 the sun clipped to a peach-white bulb and read as a
    # lamp; a lower strength keeps it an orange star against the brass.
    # Granulated orange-to-gold star: the mottle keeps it a sun, not a bulb.
    sun_mat = mottled("SunGlow", (1.0, 0.42, 0.06, 1.0), 0.4, 9.0, emission=1.3,
                      hi=(1.0, 0.72, 0.18, 1.0))
    moon_mat = principled("MoonSilver", (0.82, 0.84, 0.88, 1.0), 1.0, 0.25)

    rig["sun"].data.materials.append(sun_mat)
    rig["pedestal"].data.materials.append(dark_bronze)
    bpy.data.objects["Column"].data.materials.append(brass)
    rig["moon"]["moon"].data.materials.append(moon_mat)
    bpy.data.objects["Arm.Moon"].data.materials.append(brass)
    for name, radius, height, angle, size, color in PLANETS:
        for part in ("Arm", "Riser", "Cup"):
            bpy.data.objects[f"{part}.{name}"].data.materials.append(brass)
        planet = bpy.data.objects[name]
        planet.data.materials.append(mottled(f"M.{name}", color, 0.3, 4.5 / size))
        # ring at arm height, so it runs under the planet into the riser foot
        drop = size + RISER_GAP
        orbit_ring(f"Ring.{name}", radius, height - drop, brass)
        # column collar where the arm's pivot sleeve rides
        collar = lathe(f"Collar.{name}", [(0.0, -0.06), (0.10, -0.06), (0.12, -0.03),
                                          (0.12, 0.03), (0.10, 0.06), (0.0, 0.06)])
        collar.location = (0.0, 0.0, height - drop)
        collar.data.materials.append(brass)
    # finial under the sun and a foot collar where the column meets the base
    for obj_name, z, prof in (
            ("Finial", COLUMN_TOP - 0.1, [(0.0, -0.1), (0.08, -0.1), (0.14, 0.02),
                                          (0.11, 0.1), (0.0, 0.1)]),
            ("Foot", PEDESTAL_TOP, [(0.0, 0.0), (0.2, 0.0), (0.16, 0.05),
                                    (0.10, 0.09), (0.0, 0.09)])):
        part = lathe(obj_name, prof)
        part.location = (0.0, 0.0, z)
        part.data.materials.append(brass)
    for ob in scene.objects:
        if ob.type == 'MESH':
            # smooth, but keep the turned profiles' steps crisp (4.1+ mesh API)
            ob.data.shade_smooth()
            ob.data.set_sharp_from_angle(angle=math.radians(40))

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = principled("Studio", (0.03, 0.032, 0.037, 1.0), 0.0, 0.7)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.pi / 2, 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    # brass lives on reflections: faint warm ambient so flanks never go black
    world.node_tree.nodes["Background"].inputs["Color"].default_value = \
        (0.030, 0.026, 0.022, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # House recipe (docs/VISUAL-STYLE.md): shaped warm key, faint cool fill,
    # rim, warm wedge on the back wall. The old rig (key 1500, fill 500) lit
    # the stage to mean luma 0.33, above the calibration set's band.
    light("Key", (-4.0, -4.5, 5.0), 620.0, 4.5, (1.0, 0.94, 0.86), (46, 0, -40))
    light("Fill", (4.8, -3.8, 2.6), 120.0, 8.0, (0.75, 0.83, 1.0), (62, 0, 48))
    light("Rim", (1.0, 4.5, 3.4), 420.0, 4.0, (1.0, 0.68, 0.38), (-70, 0, 170))
    light("Wedge", (2.5, 3.5, 4.2), 420.0, 5.5, (1.0, 0.76, 0.5), (-72, 0, 195))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 40.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -7.8, 2.7)
    cam.rotation_euler = (math.radians(80.2), 0.0, 0.0)
    scene.collection.objects.link(cam)
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
    # AgX washes the orange sun and the planet colours toward pastel
    # (docs/VISUAL-STYLE.md); the sun read as a peach bulb under it.
    scene.view_settings.view_transform = 'Standard'
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact.
    orrery = [o for o in scene.objects
              if o.type in {'MESH', 'CURVE'} and o.name not in {"Floor", "Wall"}]
    fcode = gallery_framing.check_framing(
        scene, cam, hero=orrery, elements=orrery, stage=[floor, wall],
    )
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    return 0 if os.path.exists(path) and os.path.getsize(path) > 0 else 8


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--skip-mpi", action="store_true",
                   help="parent without matrix_parent_inverse (must fail)")
    args = p.parse_args(argv)

    rig = build_orrery(skip_mpi=args.skip_mpi)
    code = check(rig)
    if code:
        return code

    if args.output:
        rcode = render_still(rig, os.path.abspath(args.output), args.engine)
        if rcode == 8:
            print("ERROR: render produced no file", file=sys.stderr)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("parent-inverse-orrery OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
