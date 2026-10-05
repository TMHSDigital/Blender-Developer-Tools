"""Lattice deform with linear interpolation is exact trilinear interpolation — a runnable example.

Witnesses the Lattice modifier contract on a 2x2x2 lattice (``points_u``,
``points_v`` and ``points_w`` all 2). With ``interpolation_type_u/v/w`` set
to ``'KEY_LINEAR'`` a mesh vertex inside the lattice moves to the trilinear
interpolation of the eight *deformed* control points (``LatticePoint.co_deform``)
at the vertex's normalized rest coordinates (u, v, w) in lattice space.
The check computes that closed form independently in Python for every
evaluated vertex (``evaluated_get`` + ``to_mesh`` / ``to_mesh_clear``) and
requires agreement to 1e-5 in world space, through a lattice object that is
itself translated and non-uniformly scaled.

Three checks, in run order:

- 3: with no control point moved, the modifier is the identity;
- 4: with two top corners moved, every vertex lands on the trilinear point;
- 5: the deformation is not trivially small (the witness cannot pass vacuously).

``--bspline`` leaves the lattice on its default ``'KEY_BSPLINE'``
interpolation, which smooths over the control points instead of
interpolating them, so the evaluated mesh no longer matches the trilinear
closed form and check 4 fails with the measured error. That is the
falsifier — and the trap: a script that sets ``co_deform`` and expects the
corner to "pull" the mesh linearly gets a softer, smaller motion.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python lattice_deform.py --                 # check only
    blender --background --python lattice_deform.py -- --bspline       # must fail
    blender --background --python lattice_deform.py -- --output l.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

# The lattice: a box in world space, as a translated, non-uniformly scaled
# 2x2x2 lattice object (its points sit at +-0.5 in lattice-local space).
LAT_LOC = Vector((0.0, 0.0, 1.30))
LAT_SCALE = Vector((1.70, 1.70, 2.40))
# The deformed column, inside the lattice on every axis (lattice-local units);
# its base lies on the lattice's bottom face (w = 0), so it sits on the plinth
COLUMN_HALF = (0.40, 0.40, 0.50)
COLUMN_CUTS = 9          # subdivisions per cube edge
# Two top corners moved (lattice-local offsets): (u, v, w) index -> offset
MOVES = {
    (1, 1, 1): Vector((0.30, 0.18, 0.12)),
    (0, 0, 1): Vector((-0.10, -0.26, -0.08)),
}
TOL = 1e-5
MIN_DISPLACEMENT = 0.05  # world units; check 5's floor
TWIN_GAP = 2.9           # render only: the undeformed twin's offset to the left


def corner_index(u, v, w, n=2):
    """LatticePoint order: u fastest, then v, then w."""
    return u + n * (v + n * w)


def build_scene(bspline=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    lat = bpy.data.lattices.new("Cage")
    lat.points_u = lat.points_v = lat.points_w = 2
    if not bspline:
        lat.interpolation_type_u = 'KEY_LINEAR'
        lat.interpolation_type_v = 'KEY_LINEAR'
        lat.interpolation_type_w = 'KEY_LINEAR'
    lat_obj = bpy.data.objects.new("Cage", lat)
    lat_obj.location = LAT_LOC
    lat_obj.scale = LAT_SCALE
    scene.collection.objects.link(lat_obj)

    me = bpy.data.meshes.new("Column")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=COLUMN_CUTS, use_grid_fill=True)
        # cube [-0.5, 0.5]^3 -> the column's box in lattice-local units -> world
        for vert in bm.verts:
            local = Vector(tuple(vert.co[k] * 2.0 * COLUMN_HALF[k] for k in range(3)))
            vert.co = LAT_LOC + Vector(tuple(local[k] * LAT_SCALE[k] for k in range(3)))
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new("Column", me)
    scene.collection.objects.link(obj)
    mod = obj.modifiers.new("Lattice", 'LATTICE')
    mod.object = lat_obj
    return obj, lat_obj


def evaluated_world_coords(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        mw = ev.matrix_world
        return [mw @ v.co for v in me.vertices]
    finally:
        ev.to_mesh_clear()


def trilinear(lat_obj, corners, world_rest):
    """Closed form, independent of Blender's deform code: normalized rest
    coordinates in lattice space, then the trilinear blend of the deformed
    corners, mapped back to world."""
    local = lat_obj.matrix_world.inverted() @ world_rest
    u, v, w = (local[k] + 0.5 for k in range(3))
    out = Vector((0.0, 0.0, 0.0))
    for (i, j, k), co in corners.items():
        weight = (u if i else 1 - u) * (v if j else 1 - v) * (w if k else 1 - w)
        out += weight * co
    return lat_obj.matrix_world @ out


def check(obj, lat_obj):
    bpy.context.view_layer.update()
    rest = [obj.matrix_world @ v.co for v in obj.data.vertices]

    # 3: an undeformed lattice is the identity
    ident = evaluated_world_coords(obj)
    err0 = max((a - b).length for a, b in zip(ident, rest))
    if err0 > TOL:
        print(f"ERROR: undeformed lattice moved the mesh (max {err0:.3e} > {TOL:.0e})",
              file=sys.stderr)
        return 3

    lat = lat_obj.data
    for (i, j, k), off in MOVES.items():
        pt = lat.points[corner_index(i, j, k)]
        pt.co_deform = Vector(pt.co) + off
    corners = {(i, j, k): Vector(lat.points[corner_index(i, j, k)].co_deform)
               for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    lat.update_tag()
    obj.update_tag()
    bpy.context.view_layer.update()

    # 4: every vertex on the trilinear closed form
    got = evaluated_world_coords(obj)
    if len(got) != len(rest):
        print(f"ERROR: vertex count changed {len(rest)} -> {len(got)}", file=sys.stderr)
        return 4
    errs = [(g - trilinear(lat_obj, corners, r)).length for g, r in zip(got, rest)]
    worst = max(range(len(errs)), key=errs.__getitem__)
    interp = (lat.interpolation_type_u, lat.interpolation_type_v, lat.interpolation_type_w)
    if errs[worst] > TOL:
        print(f"ERROR: {sum(e > TOL for e in errs)}/{len(errs)} verts off the trilinear "
              f"closed form; max {errs[worst]:.4f} at vert {worst} (interpolation {interp})",
              file=sys.stderr)
        return 4

    # 5: the witness moved the mesh by a real amount
    disp = max((g - r).length for g, r in zip(got, rest))
    if disp < MIN_DISPLACEMENT:
        print(f"ERROR: max displacement {disp:.4f} < {MIN_DISPLACEMENT}", file=sys.stderr)
        return 5

    print(f"lattice 2x2x2 {interp}: identity max {err0:.2e}; {len(errs)} verts on the "
          f"trilinear closed form, max err {errs[worst]:.2e}; max displacement {disp:.4f}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


# ---------------------------------------------------------------------------
# Render staging only (runs after the check; never part of it)
# ---------------------------------------------------------------------------

def principled(name, base, rough, metal=0.0, noise=None, coat=0.0, emit=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    if emit:
        b.inputs["Emission Color"].default_value = (*emit[0], 1.0)
        b.inputs["Emission Strength"].default_value = emit[1]
    if noise:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = noise
        tex.inputs["Detail"].default_value = 8.0
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = max(rough - 0.08, 0.0)
        mr.inputs["To Max"].default_value = rough + 0.14
        nt.links.new(tex.outputs["Fac"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    return mat


def checker_ceramic():
    """A glazed two-tone checker on the column, in Generated (rest) coordinates:
    the squares are square before the lattice acts, so their shear and
    stretch in the still is the deformation itself."""
    mat = bpy.data.materials.new("CheckerGlaze")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.32
    b.inputs["Coat Weight"].default_value = 0.5
    tc = nt.nodes.new("ShaderNodeTexCoord")
    chk = nt.nodes.new("ShaderNodeTexChecker")
    chk.inputs["Scale"].default_value = float(COLUMN_CUTS + 1)
    chk.inputs["Color1"].default_value = (0.60, 0.56, 0.49, 1.0)
    chk.inputs["Color2"].default_value = (0.10, 0.22, 0.30, 1.0)
    nt.links.new(tc.outputs["Generated"], chk.inputs["Vector"])
    nt.links.new(chk.outputs["Color"], b.inputs["Base Color"])
    return mat


def tube_mesh(name, segments, radius, sides=10):
    """Render-only rods along line segments (lattices do not render)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for a, b in segments:
            axis = b - a
            res = bmesh.ops.create_cone(bm, cap_ends=True, segments=sides,
                                        radius1=radius, radius2=radius, depth=axis.length)
            rot = Vector((0, 0, 1)).rotation_difference(axis.normalized()).to_matrix()
            mid = (a + b) / 2
            for vert in res["verts"]:
                vert.co = rot @ vert.co + mid
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    return me


def sphere_mesh(name, centers, radius):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for c in centers:
            res = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=14, radius=radius)
            for vert in res["verts"]:
                vert.co += c
        bm.to_mesh(me)
    finally:
        bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    return me


def box_mesh(name, lo, hi):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        res = bmesh.ops.create_cube(bm, size=1.0)
        for vert in res["verts"]:
            vert.co = Vector(tuple(lo[k] + (vert.co[k] + 0.5) * (hi[k] - lo[k]) for k in range(3)))
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def cage_edges(points):
    """The 12 edges of a 2x2x2 cage given corner positions keyed (i, j, k)."""
    edges = []
    for i in (0, 1):
        for j in (0, 1):
            edges.append((points[(i, j, 0)], points[(i, j, 1)]))
            edges.append((points[(i, 0, j)], points[(i, 1, j)]))
            edges.append((points[(0, i, j)], points[(1, i, j)]))
    return edges


def render_still(obj, lat_obj, path, engine):
    scene = bpy.context.scene
    mw = lat_obj.matrix_world
    lat = lat_obj.data
    rest = {(i, j, k): mw @ Vector(lat.points[corner_index(i, j, k)].co)
            for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    moved = {(i, j, k): mw @ Vector(lat.points[corner_index(i, j, k)].co_deform)
             for i in (0, 1) for j in (0, 1) for k in (0, 1)}

    obj.data.materials.append(checker_ceramic())
    obj.data.polygons.foreach_set("use_smooth", [False] * len(obj.data.polygons))

    steel = principled("CageSteel", (0.58, 0.60, 0.64), 0.22, metal=1.0)
    ghost = principled("RestCage", (0.16, 0.17, 0.19), 0.6, metal=0.3)
    orange = principled("MovedCorner", (1.0, 0.42, 0.04), 0.3,
                        emit=((1.0, 0.45, 0.06), 1.5))
    joint = principled("CageJoint", (0.30, 0.31, 0.34), 0.3, metal=1.0)
    walnut = principled("Walnut", (0.13, 0.055, 0.025), 0.45, noise=40.0, coat=0.4)

    parts = []

    def add(name, me, mat):
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        scene.collection.objects.link(ob)
        parts.append(ob)
        return ob

    add("DeformedCage", tube_mesh("DeformedCage", cage_edges(moved), 0.022), steel)
    # the rest cage, thin and dark: what the two corners were moved away from
    rest_only = [(a, b) for a, b in cage_edges(rest)]
    add("RestCage", tube_mesh("RestCage", rest_only, 0.009), ghost)
    still = [moved[key] for key in moved if key not in MOVES]
    add("CageJoints", sphere_mesh("CageJoints", still, 0.05), joint)
    add("MovedCorners", sphere_mesh("MovedCorners", [moved[key] for key in MOVES], 0.075),
        orange)
    # a travel rod from each moved corner back to its rest position
    add("Travel", tube_mesh("Travel", [(rest[key], moved[key]) for key in MOVES], 0.012),
        orange)

    # Render-only "before" twin: the same column, unmodified, in its rest cage,
    # one cage-width to the left, so the still reads rest -> deformed.
    shift = Vector((-TWIN_GAP, 0.0, 0.0))
    twin_me = obj.data.copy()
    twin = bpy.data.objects.new("RestColumn", twin_me)
    twin.location = shift
    scene.collection.objects.link(twin)
    parts.append(twin)
    rest_twin = {key: co + shift for key, co in rest.items()}
    add("TwinCage", tube_mesh("TwinCage", cage_edges(rest_twin), 0.022), steel)
    add("TwinJoints", sphere_mesh("TwinJoints", list(rest_twin.values()), 0.05), joint)

    lo_z = LAT_LOC.z - LAT_SCALE.z / 2
    half_x = LAT_SCALE.x / 2 + 0.45
    plinth = add("Plinth", box_mesh("Plinth", (-TWIN_GAP - half_x, -1.3, 0.0),
                                    (half_x, 1.3, lo_z - 0.002)), walnut)
    bev = plinth.modifiers.new("Chamfer", 'BEVEL')
    bev.width = 0.03
    bev.segments = 2

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
    wall.location = (0.0, 7.5, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    centre = Vector((-TWIN_GAP / 2, 0.0, LAT_LOC.z))

    def light(name, loc, energy, size, col, aim):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(ob)

    light("Key", (-4.5, -5.0, 6.5), 520.0, 4.0, (1.0, 0.96, 0.9), centre)
    light("Fill", (5.5, -4.5, 2.5), 110.0, 7.0, (0.75, 0.85, 1.0), centre)
    light("Rim", (1.5, 4.0, 6.0), 380.0, 3.0, (0.6, 0.78, 1.0), centre)
    light("Wedge", (2.5, 4.5, 3.0), 420.0, 5.0, (1.0, 0.76, 0.5), (4.5, 7.5, 1.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (centre.x + 3.6, -9.6, 3.9)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.05, 0.0, -0.15))
    scene.collection.objects.link(aim)
    tr = cam.constraints.new('TRACK_TO')
    tr.target = aim
    tr.track_axis = 'TRACK_NEGATIVE_Z'
    tr.up_axis = 'UP_Y'
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
    # AgX would wash the glaze and the orange accent toward pastel (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=[obj] + parts,
        elements=[obj] + parts,
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
    p.add_argument("--bspline", action="store_true",
                   help="keep the default KEY_BSPLINE interpolation (must fail)")
    args = p.parse_args(argv)

    obj, lat_obj = build_scene(bspline=args.bspline)
    code = check(obj, lat_obj)
    if code:
        return code

    if args.output:
        rcode = render_still(obj, lat_obj, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("lattice-deform OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
