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

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python parent_inverse_orrery.py --                   # check only
    blender --background --python parent_inverse_orrery.py -- --output o.png    # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector, Matrix

# (name, orbit radius, arm height, orbit angle deg, sphere radius, color RGBA)
PLANETS = [
    ("Lapis", 2.55, 1.02, 152.0, 0.34, (0.04, 0.10, 0.42, 1.0)),
    ("Terra", 1.85, 1.58, 336.0, 0.26, (0.48, 0.16, 0.07, 1.0)),
    ("Jade", 1.20, 2.12, 38.0, 0.20, (0.05, 0.33, 0.20, 1.0)),
]
MOON_HOST = "Lapis"           # the moon orbits the outer planet
MOON_OFFSET = 0.62            # distance from its planet, along local +X
MOON_ANGLE = 163.0            # moon-pivot spin, degrees
MOON_R = 0.12
PEDESTAL_TOP = 0.22
COLUMN_TOP = 2.45
SUN_Z = 2.62
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


def empty(name, location):
    obj = bpy.data.objects.new(name, None)  # object_data=None -> EMPTY
    obj.location = location
    bpy.context.collection.objects.link(obj)
    return obj


def parent_keep_world(child, parent):
    """The idiom this example witnesses: parent without moving the child."""
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


def build_orrery():
    """Author the whole hierarchy with bpy.data (no object-mode operators)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)

    pedestal = cylinder("Pedestal", 1.15, PEDESTAL_TOP, segments=48)
    pedestal.location = (0.0, 0.0, PEDESTAL_TOP / 2)
    column = cylinder("Column", 0.07, COLUMN_TOP - PEDESTAL_TOP, segments=24)
    column.location = (0.0, 0.0, (PEDESTAL_TOP + COLUMN_TOP) / 2)
    sun = sphere("Sun", 0.28)
    sun.location = (0.0, 0.0, SUN_Z)

    rig = {"sun": sun, "pedestal": pedestal, "planets": {}}
    for name, radius, height, angle, size, color in PLANETS:
        pivot = empty(f"Pivot.{name}", (0.0, 0.0, height))
        arm = cylinder(f"Arm.{name}", 0.035, radius, segments=12)
        arm.rotation_euler = (0.0, math.pi / 2, 0.0)
        arm.location = (radius / 2, 0.0, height)
        planet = sphere(name, size)
        planet.location = (radius, 0.0, height)
        # everything is placed at its theta=0 WORLD position first, then
        # parented with the keep-world idiom -- nothing may move here
        bpy.context.view_layer.update()
        parent_keep_world(arm, pivot)
        parent_keep_world(planet, pivot)
        rig["planets"][name] = {
            "pivot": pivot, "planet": planet, "angle": math.radians(angle),
            "p0": Vector((radius, 0.0, height)),
        }

    host = rig["planets"][MOON_HOST]
    pc0 = host["p0"].copy()
    moon_pivot = empty("Pivot.Moon", pc0)
    rod = cylinder("Arm.Moon", 0.02, MOON_OFFSET, segments=12)
    rod.rotation_euler = (0.0, math.pi / 2, 0.0)
    rod.location = pc0 + Vector((MOON_OFFSET / 2, 0.0, 0.0))
    moon = sphere("Moon", MOON_R)
    moon.location = pc0 + Vector((MOON_OFFSET, 0.0, 0.0))
    bpy.context.view_layer.update()
    parent_keep_world(moon_pivot, host["planet"])
    parent_keep_world(rod, moon_pivot)
    parent_keep_world(moon, moon_pivot)
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
    dark_bronze = principled("Bronze", (0.16, 0.11, 0.07, 1.0), 1.0, 0.45)
    sun_mat = principled("SunGlow", (1.0, 0.48, 0.10, 1.0), 0.0, 0.4, emission=3.2)
    moon_mat = principled("MoonSilver", (0.82, 0.84, 0.88, 1.0), 1.0, 0.25)

    rig["sun"].data.materials.append(sun_mat)
    rig["pedestal"].data.materials.append(dark_bronze)
    bpy.data.objects["Column"].data.materials.append(brass)
    rig["moon"]["moon"].data.materials.append(moon_mat)
    bpy.data.objects["Arm.Moon"].data.materials.append(brass)
    for name, radius, height, angle, size, color in PLANETS:
        bpy.data.objects[f"Arm.{name}"].data.materials.append(brass)
        planet = bpy.data.objects[name]
        planet.data.materials.append(principled(f"M.{name}", color, 0.0, 0.22))
        for poly in planet.data.polygons:
            poly.use_smooth = True
        orbit_ring(f"Ring.{name}", radius, height, brass)
    for obj_name in ("Sun", "Moon", "Pedestal", "Column"):
        for poly in bpy.data.objects[obj_name].data.polygons:
            poly.use_smooth = True

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = principled("Studio", (0.045, 0.05, 0.06, 1.0), 0.0, 0.42)
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

    light("Key", (-4.0, -4.5, 5.0), 1500.0, 6.5, (1.0, 0.94, 0.86), (46, 0, -40))
    light("Fill", (4.8, -3.8, 2.6), 500.0, 8.0, (0.75, 0.83, 1.0), (62, 0, 48))
    light("Rim", (1.0, 4.5, 3.4), 900.0, 4.0, (1.0, 0.68, 0.38), (-70, 0, 170))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 40.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -7.8, 2.7)
    cam.rotation_euler = (math.radians(81.0), 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 48
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    args = p.parse_args(argv)

    rig = build_orrery()
    code = check(rig)
    if code:
        return code

    if args.output:
        if not render_still(rig, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 8
        print(f"rendered still {args.output}")

    print("parent-inverse-orrery OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
