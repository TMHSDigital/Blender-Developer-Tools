"""EXACT Boolean volumes are closed-form and manifold, even on coplanar faces — a runnable example.

Witnesses the Boolean modifier contract with ``solver = 'EXACT'``. Operand A
is a 2 m cube and operand B a 2 x 1 x 1 m slab that overlaps A by a 1 m cube
and whose top face lies in A's top plane: the coplanar case. Both operands
sit in object matrices that are translated and turned about Z, so the
modifier has to bring B into A's space. For each of UNION, DIFFERENCE and
INTERSECT the evaluated mesh (``evaluated_get`` + ``to_mesh`` /
``to_mesh_clear``) is measured in world space:

- 3: its signed volume, by the divergence theorem over its own triangles,
  matches the closed form (V(A) + V(B) - V(A n B) = 9, V(A) - V(A n B) = 7,
  V(A n B) = 1 cubic metres) to 1e-6 relative; positive volume also means
  the normals point outward;
- 4: it is a closed 2-manifold: every edge borders exactly two faces, and
  there are no loose verts or edges;
- 5: it is not vacuous: each result's volume differs from V(A) by at least
  0.5 m^3, so the modifier really acted.

``--float-solver`` runs the same three operations on the floating-point
solver (``'FLOAT'`` on Blender 5.x, ``'FAST'`` on 4.5 LTS, the same solver
under its older name). On the coplanar top face it returns a wrong union
(7.708 m^3 against 9, measured identically on 4.5.11, 5.1.2 and 5.2.1), so
check 3 fails with the measured error. That is the falsifier, and the documented failure case
the EXACT solver exists to handle.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python boolean_exact_volume.py --                     # check only
    blender --background --python boolean_exact_volume.py -- --float-solver      # must fail
    blender --background --python boolean_exact_volume.py -- --output b.png      # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector, Matrix

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

# Operands in their shared local frame (metres). B's top face (z = 2) is
# coplanar with A's top face; the overlap A n B is [1,2] x [0.5,1.5] x [1,2].
A_LO, A_HI = (0.0, 0.0, 0.0), (2.0, 2.0, 2.0)
B_LO, B_HI = (1.0, 0.5, 1.0), (3.0, 1.5, 2.0)
OPS = ('UNION', 'DIFFERENCE', 'INTERSECT')
SPACING = 4.6           # world X between the three operation sets
TURN = math.radians(-18.0)  # every set's frame turns about Z


def box_volume(lo, hi):
    return (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])


def overlap(lo1, hi1, lo2, hi2):
    lo = tuple(max(lo1[k], lo2[k]) for k in range(3))
    hi = tuple(min(hi1[k], hi2[k]) for k in range(3))
    return lo, hi


V_A = box_volume(A_LO, A_HI)
V_B = box_volume(B_LO, B_HI)
V_AB = box_volume(*overlap(A_LO, A_HI, B_LO, B_HI))
EXPECTED = {'UNION': V_A + V_B - V_AB, 'DIFFERENCE': V_A - V_AB, 'INTERSECT': V_AB}
REL_TOL = 1e-6
MIN_CHANGE = 0.5        # m^3; check 5's floor against V(A)


def fast_solver_id():
    """The floating-point solver: 'FAST' through 4.5 LTS, renamed 'FLOAT' in 5.0."""
    return 'FLOAT' if bpy.app.version >= (5, 0, 0) else 'FAST'


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


def frame(i):
    """World matrix of operation set i: translated along X, turned about Z,
    with the operands' local frame centred on A's footprint."""
    centre = Matrix.Translation((-(A_HI[0] - A_LO[0]) / 2 - 0.5, -(A_HI[1] - A_LO[1]) / 2, 0.0))
    return (Matrix.Translation(((i - 1) * SPACING, 0.0, 0.0))
            @ Matrix.Rotation(TURN, 4, 'Z') @ centre)


def build_scene(float_solver=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    solver = fast_solver_id() if float_solver else 'EXACT'
    results = {}
    cutters = {}
    for i, op in enumerate(OPS):
        a = bpy.data.objects.new(f"{op.title()}Result", box_mesh(f"{op.title()}Result", A_LO, A_HI))
        b = bpy.data.objects.new(f"{op.title()}Cutter", box_mesh(f"{op.title()}Cutter", B_LO, B_HI))
        a.matrix_world = frame(i)
        b.matrix_world = frame(i)
        b.hide_render = True
        b.display_type = 'WIRE'
        scene.collection.objects.link(a)
        scene.collection.objects.link(b)
        mod = a.modifiers.new("Boolean", 'BOOLEAN')
        mod.operation = op
        mod.solver = solver
        mod.object = b
        results[op] = a
        cutters[op] = b
    return results, cutters, solver


def measure(obj):
    """World-space signed volume (divergence theorem over fan triangles of
    each polygon) plus manifold counts, from the evaluated mesh."""
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    me = ev.to_mesh()
    try:
        mw = ev.matrix_world
        co = [mw @ v.co for v in me.vertices]
        vol = 0.0
        for p in me.polygons:
            idx = list(p.vertices)
            v0 = co[idx[0]]
            for j in range(1, len(idx) - 1):
                vol += v0.dot(co[idx[j]].cross(co[idx[j + 1]])) / 6.0
        bm = bmesh.new()
        try:
            bm.from_mesh(me)
            bad_edges = sum(1 for e in bm.edges if len(e.link_faces) != 2)
            loose_verts = sum(1 for v in bm.verts if not v.link_faces)
            loose_edges = sum(1 for e in bm.edges if not e.link_faces)
        finally:
            bm.free()
        return vol, bad_edges, loose_verts, loose_edges, len(me.polygons)
    finally:
        ev.to_mesh_clear()


def check(results, solver):
    bpy.context.view_layer.update()
    m = {op: measure(results[op]) for op in OPS}

    # 3: volumes on the closed forms (positive => outward normals)
    for op in OPS:
        vol, exp = m[op][0], EXPECTED[op]
        if abs(vol - exp) > REL_TOL * exp:
            print(f"ERROR: {op} on solver {solver!r}: volume {vol:.6f} m^3, closed form "
                  f"{exp:.6f} (error {vol - exp:+.6f})", file=sys.stderr)
            return 3

    # 4: closed 2-manifold, no loose geometry
    for op in OPS:
        _, bad, lv, le, _ = m[op]
        if bad or lv or le:
            print(f"ERROR: {op} on solver {solver!r} is not a closed manifold: {bad} edges "
                  f"without exactly two faces, {lv} loose verts, {le} loose edges",
                  file=sys.stderr)
            return 4

    # 5: every result really differs from operand A
    for op in OPS:
        if abs(m[op][0] - V_A) < MIN_CHANGE:
            print(f"ERROR: {op} volume {m[op][0]:.4f} within {MIN_CHANGE} of V(A) = {V_A}",
                  file=sys.stderr)
            return 5

    parts = ", ".join(f"{op} {m[op][0]:.6f} (closed form {EXPECTED[op]:g}, {m[op][4]} faces)"
                      for op in OPS)
    print(f"solver {solver!r}, coplanar top face: {parts}; all closed 2-manifold, "
          f"0 loose verts/edges")
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


def tube_mesh(name, segments, radius, sides=10):
    """Render-only rods along line segments (the operand outlines)."""
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
    for p in me.polygons:
        p.use_smooth = True
    return me


def box_edges(lo, hi, mw):
    c = {(i, j, k): mw @ Vector((hi[0] if i else lo[0], hi[1] if j else lo[1], hi[2] if k else lo[2]))
         for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    edges = []
    for i in (0, 1):
        for j in (0, 1):
            edges.append((c[(i, j, 0)], c[(i, j, 1)]))
            edges.append((c[(i, 0, j)], c[(i, 1, j)]))
            edges.append((c[(0, i, j)], c[(1, i, j)]))
    return edges


def render_still(results, cutters, path, engine):
    scene = bpy.context.scene
    glazes = {
        'UNION': principled("UnionGlaze", (0.07, 0.30, 0.34), 0.28, coat=0.5),
        'DIFFERENCE': principled("DifferenceBrass", (0.86, 0.56, 0.26), 0.30, metal=1.0, noise=60.0),
        'INTERSECT': principled("IntersectOrange", (0.95, 0.36, 0.05), 0.32, coat=0.4),
    }
    steel = principled("OperandA", (0.62, 0.64, 0.68), 0.25, metal=1.0)
    cutter_mat = principled("OperandB", (1.0, 0.45, 0.06), 0.35,
                            emit=((1.0, 0.45, 0.06), 1.2))
    walnut = principled("Walnut", (0.13, 0.055, 0.025), 0.45, noise=40.0, coat=0.4)

    parts = []

    def add(name, me, mat):
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        scene.collection.objects.link(ob)
        parts.append(ob)
        return ob

    for i, op in enumerate(OPS):
        res = results[op]
        res.data.materials.append(glazes[op])
        mw = frame(i)
        # thin outlines of both operands: A in steel, the coplanar cutter B in orange
        add(f"{op.title()}OutlineA", tube_mesh(f"{op.title()}OutlineA",
                                               box_edges(A_LO, A_HI, mw), 0.016), steel)
        add(f"{op.title()}OutlineB", tube_mesh(f"{op.title()}OutlineB",
                                               box_edges(B_LO, B_HI, mw), 0.020), cutter_mat)

    half_x = SPACING + 2.2
    plinth = add("Plinth", bpy.data.meshes.new("Plinth"), walnut)
    bm = bmesh.new()
    try:
        res = bmesh.ops.create_cube(bm, size=1.0)
        lo, hi = (-half_x, -2.3, -0.16), (half_x, 2.3, -0.004)
        for vert in res["verts"]:
            vert.co = Vector(tuple(lo[k] + (vert.co[k] + 0.5) * (hi[k] - lo[k]) for k in range(3)))
        bm.to_mesh(plinth.data)
    finally:
        bm.free()
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
    floor.location = (0.0, 0.0, -0.16)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 8.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    centre = Vector((0.0, 0.0, 1.0))

    def light(name, loc, energy, size, col, aim):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(ob)

    light("Key", (-5.0, -6.0, 7.5), 700.0, 5.0, (1.0, 0.96, 0.9), centre)
    light("Fill", (7.0, -5.5, 3.0), 140.0, 8.0, (0.75, 0.85, 1.0), centre)
    light("Rim", (2.0, 5.0, 7.0), 420.0, 4.0, (0.6, 0.78, 1.0), centre)
    light("Wedge", (3.0, 5.0, 3.0), 480.0, 6.0, (1.0, 0.76, 0.5), (5.0, 8.0, 1.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (3.2, -20.9, 11.0)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.1))
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
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # AgX would wash the glazes and the orange cutter toward pastel (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact
    shown = list(results.values()) + parts
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=shown,
        elements=shown,
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
    p.add_argument("--float-solver", action="store_true",
                   help="use the floating-point solver (FLOAT / FAST) on the coplanar case (must fail)")
    args = p.parse_args(argv)

    results, cutters, solver = build_scene(float_solver=args.float_solver)
    code = check(results, solver)
    if code:
        return code

    if args.output:
        rcode = render_still(results, cutters, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("boolean-exact-volume OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
