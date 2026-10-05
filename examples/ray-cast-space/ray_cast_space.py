"""Object.ray_cast is object-local, Scene.ray_cast is world space — a runnable example.

Witnesses the coordinate-space contract of the two ray casts, the one AI code
gets wrong most often: ``Scene.ray_cast(depsgraph, origin, direction)`` takes
and returns WORLD space, while ``Object.ray_cast(origin, direction)`` takes
and returns the object's LOCAL space. A target block carries a non-trivial
transform (translation, a turn about Z, non-uniform scale). Five rays aimed at
closed-form points on three of its faces are cast both ways:

- ``Scene.ray_cast`` must hit each closed-form world point, with the face's
  world normal (inverse-transpose of the object matrix) and the target object;
- ``Object.ray_cast``, fed the origin through ``matrix_world.inverted()`` and
  the direction through its 3x3 part only (directions do not translate), must
  hit the same polygon, and its local hit point mapped back by
  ``matrix_world`` (normal by the inverse-transpose) must land on the same
  world point and normal;
- the trap: the same WORLD origin/direction handed straight to
  ``Object.ray_cast`` must NOT reproduce the hit — every such cast misses or
  lands at least ``TRAP_MIN`` away, so the check proves the transform matters
  on this setup rather than passing by coincidence.

``--world-to-object`` feeds world coordinates to ``Object.ray_cast`` in the
checked path (the bug); the local-hit check catches it (exit 4) and prints
the measured error.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python ray_cast_space.py --                       # check only
    blender --background --python ray_cast_space.py -- --world-to-object     # must fail
    blender --background --python ray_cast_space.py -- --output r.png        # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector, Matrix

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

# The target: a unit-half-size cube (local coords in [-1, 1]^3) under a
# transform with every ingredient that separates local from world space.
TARGET_LOC = (0.35, 0.25, 0.80)
TARGET_ROT_Z = math.radians(32.0)
TARGET_SCALE = (1.55, 0.62, 0.62)

# Closed-form hit points, authored in LOCAL face coordinates, plus a tangent
# tilt so the rays arrive obliquely rather than straight down each normal.
# (face axis, face sign, local point on that face, tilt in local tangent space)
RAYS = (
    ("y", -1, (0.55, -1.0, 0.35), (0.35, 0.0, 0.25)),
    ("y", -1, (-0.45, -1.0, -0.30), (-0.30, 0.0, 0.20)),
    ("z", +1, (0.40, 0.30, 1.0), (0.25, -0.35, 0.0)),
    ("z", +1, (-0.60, -0.40, 1.0), (-0.20, -0.30, 0.0)),
    ("x", -1, (-1.0, -0.35, 0.30), (0.0, -0.30, 0.25)),
)
RAY_LEN = 1.7        # world distance from each ray origin to its hit
POS_TOL = 1e-4       # world-space hit tolerance
NRM_TOL = 1e-4       # 1 - dot(normal, expected)
TRAP_MIN = 0.25      # a world-coord Object.ray_cast must miss or land this far off


def build_target():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("TargetBlock")
    bm = bmesh.new()
    try:
        bmesh.ops.create_cube(bm, size=2.0)
        bm.to_mesh(me)
    finally:
        bm.free()
    obj = bpy.data.objects.new("TargetBlock", me)
    bpy.context.collection.objects.link(obj)
    obj.location = TARGET_LOC
    obj.rotation_euler = (0.0, 0.0, TARGET_ROT_Z)
    obj.scale = TARGET_SCALE
    bpy.context.view_layer.update()
    return obj


def world_rays(obj):
    """Closed-form world rays: (origin, direction, hit point, face normal).

    The hit point is the local face point through matrix_world; the world
    normal is the local face normal through the inverse-transpose 3x3. The
    origin sits RAY_LEN back along the (tilted) incoming direction, in the
    face's outer half-space, so on this convex block the first surface the
    ray meets is that face at that point.
    """
    mw = obj.matrix_world
    n_mat = mw.to_3x3().inverted().transposed()
    out = []
    for axis, sign, p_local, tilt in RAYS:
        n_local = Vector((0.0, 0.0, 0.0))
        n_local["xyz".index(axis)] = sign
        p = mw @ Vector(p_local)
        n = (n_mat @ n_local).normalized()
        incoming = (n_local + Vector(tilt))       # outward-ish, in local space
        d = -(mw.to_3x3() @ incoming).normalized()
        if d.dot(n) >= 0.0:
            raise ValueError(f"ray at {p_local} does not approach its face from outside")
        out.append((p - RAY_LEN * d, d, p, n))
    return out


def object_space(obj, origin, direction):
    """World ray -> the object's local space: the origin through the full
    inverse matrix, the direction through its 3x3 only (no translation)."""
    inv = obj.matrix_world.inverted()
    return inv @ origin, (inv.to_3x3() @ direction).normalized()


def check(obj, world_to_object=False):
    dg = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    mw = obj.matrix_world
    n_mat = mw.to_3x3().inverted().transposed()
    rays = world_rays(obj)

    # 1. Scene.ray_cast: world in, world out
    scene_hits = []
    for k, (o, d, p, n) in enumerate(rays):
        ok, loc, nrm, idx, hit_ob, _m = scene.ray_cast(dg, o, d)
        if not ok or hit_ob is None or hit_ob.name != obj.name:
            print(f"ERROR: Scene.ray_cast ray {k} missed the target", file=sys.stderr)
            return 3
        err, nerr = (loc - p).length, 1.0 - nrm.normalized().dot(n)
        if err > POS_TOL or nerr > NRM_TOL:
            print(f"ERROR: Scene.ray_cast ray {k} hit {tuple(round(c, 5) for c in loc)} "
                  f"(error {err:.6f} m, normal error {nerr:.6f}) vs closed form "
                  f"{tuple(round(c, 5) for c in p)}", file=sys.stderr)
            return 3
        scene_hits.append(idx)

    # 2. Object.ray_cast: local in, local out — map both ways
    worst = 0.0
    for k, (o, d, p, n) in enumerate(rays):
        if world_to_object:
            lo, ld = o, d                      # the bug: world coords as if local
        else:
            lo, ld = object_space(obj, o, d)
        ok, loc, nrm, idx = obj.ray_cast(lo, ld, depsgraph=dg)
        if not ok:
            print(f"ERROR: Object.ray_cast ray {k} missed (origin/direction not in "
                  f"object space?)", file=sys.stderr)
            return 4
        p_back = mw @ loc
        n_back = (n_mat @ nrm).normalized()
        err, nerr = (p_back - p).length, 1.0 - n_back.dot(n)
        worst = max(worst, err)
        if err > POS_TOL or nerr > NRM_TOL or idx != scene_hits[k]:
            print(f"ERROR: Object.ray_cast ray {k} mapped back to "
                  f"{tuple(round(c, 5) for c in p_back)}, error {err:.4f} m "
                  f"(normal error {nerr:.4f}, polygon {idx} vs Scene {scene_hits[k]})",
                  file=sys.stderr)
            return 4

    # 3. The trap must actually bite on this setup
    trap_min = math.inf
    for k, (o, d, p, n) in enumerate(rays):
        ok, loc, _nrm, _idx = obj.ray_cast(o, d, depsgraph=dg)
        dev = (mw @ loc - p).length if ok else math.inf
        trap_min = min(trap_min, dev)
    if trap_min < TRAP_MIN:
        print(f"ERROR: world coords fed to Object.ray_cast landed only {trap_min:.4f} m "
              f"from a true hit (< {TRAP_MIN}); the transform does not separate the "
              f"spaces", file=sys.stderr)
        return 5

    trap_txt = "all miss" if trap_min == math.inf else f"closest {trap_min:.3f} m off"
    print(f"rays={len(rays)} scene_hits=exact object_local_hits=exact "
          f"max_mapped_error={worst:.2e} m world_coords_trap={trap_txt}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


# --------------------------------------------------------------------------
# Render staging only (not part of the check)
# --------------------------------------------------------------------------

def principled(name, base, rough, metal=0.0, emit=None, strength=0.0, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit is not None:
        b.inputs["Emission Color"].default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = strength
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        try:
            mat.surface_render_method = 'BLENDED'
        except AttributeError:
            pass
    return mat


def block_material():
    """Glazed teal ceramic with an OBJECT-space checker: the cells are square
    in local space, so the non-uniform scale stretches them into the
    rectangles the eye reads as 'this object has its own coordinates'. Teal
    sits opposite the orange rays, so every hit marker reads at thumbnail size."""
    mat = bpy.data.materials.new("LocalSpaceCeramic")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.32
    b.inputs["Coat Weight"].default_value = 0.35
    coords = nt.nodes.new("ShaderNodeTexCoord")
    chk = nt.nodes.new("ShaderNodeTexChecker")
    chk.inputs["Scale"].default_value = 4.0
    chk.inputs["Color1"].default_value = (0.09, 0.36, 0.40, 1.0)
    chk.inputs["Color2"].default_value = (0.035, 0.15, 0.18, 1.0)
    # Object coords span -1..1; shift to 0..2 so cells line up with face edges
    add = nt.nodes.new("ShaderNodeVectorMath")
    add.operation = 'ADD'
    add.inputs[1].default_value = (1.0, 1.0, 1.0)
    nt.links.new(coords.outputs["Object"], add.inputs[0])
    nt.links.new(add.outputs["Vector"], chk.inputs["Vector"])
    nt.links.new(chk.outputs["Color"], b.inputs["Base Color"])
    return mat


def rod(name, a, b, radius, mat, segs=16):
    """A thin cylinder from a to b (render-only ray segment)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        length = (b - a).length
        bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=radius,
                              radius2=radius, depth=length)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(mat)
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (a + b) / 2
    ob.rotation_euler = (b - a).to_track_quat('Z', 'Y').to_euler()
    return ob


def sphere(name, at, radius, mat):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=radius)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(mat)
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = at
    return ob


def ring(name, at, normal, r_out, r_in, mat):
    """A flat hit-marker annulus lying on the surface, facing out along normal."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        segs = 32
        outer = [bm.verts.new((r_out * math.cos(2 * math.pi * i / segs),
                               r_out * math.sin(2 * math.pi * i / segs), 0.0))
                 for i in range(segs)]
        inner = [bm.verts.new((r_in * math.cos(2 * math.pi * i / segs),
                               r_in * math.sin(2 * math.pi * i / segs), 0.0))
                 for i in range(segs)]
        for i in range(segs):
            j = (i + 1) % segs
            bm.faces.new((outer[i], outer[j], inner[j], inner[i]))
        ext = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
        top = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=top, vec=(0.0, 0.0, 0.006))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = at + normal * 0.002
    ob.rotation_euler = normal.to_track_quat('Z', 'Y').to_euler()
    return ob


def render_still(obj, path, engine):
    scene = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    rays = world_rays(obj)
    # one ghosted trap ray: the first front-face ray's WORLD origin/direction
    # read by Object.ray_cast as if local. In the world that is the ray
    # matrix_world @ o along matrix_world.to_3x3() @ d; cast it before any
    # render-only modifier changes the evaluated mesh.
    mw = obj.matrix_world
    o, d, p, n = rays[0]
    t_o = mw @ o
    t_d = (mw.to_3x3() @ d).normalized()
    t_ok, t_loc, _n, _i = obj.ray_cast(o, d, depsgraph=dg)
    t_end = (mw @ t_loc) if t_ok else (t_o + 3.0 * t_d)
    obj.data.materials.append(block_material())
    bev = obj.modifiers.new("Chamfer", 'BEVEL')   # render-only, after the check
    bev.width = 0.025
    bev.segments = 3
    bev.affect = 'EDGES'

    # emission kept under clipping in Standard view, so the beams stay orange
    beam = principled("RayBeam", (1.0, 0.26, 0.02), 0.3, emit=(1.0, 0.26, 0.02), strength=1.4)
    hit_mat = principled("HitMarker", (1.0, 0.36, 0.04), 0.25, emit=(1.0, 0.36, 0.04),
                         strength=1.8)
    emitter = principled("RayEmitter", (0.85, 0.58, 0.24), 0.38, metal=1.0)
    trap_beam = principled("TrapBeam", (0.9, 0.12, 0.18), 0.4, emit=(1.0, 0.1, 0.16),
                           strength=1.2)
    trap_end = principled("TrapEnd", (0.9, 0.12, 0.18), 0.35, emit=(1.0, 0.1, 0.16),
                          strength=1.5)
    plinth_mat = principled("PlinthWalnut", (0.13, 0.055, 0.025), 0.45)

    shown = [obj]
    for k, (o, d, p, n) in enumerate(rays):
        shown.append(rod(f"Ray{k}", o, p, 0.022, beam))
        shown.append(sphere(f"Emitter{k}", o, 0.07, emitter))
        shown.append(ring(f"Hit{k}", p, n, 0.10, 0.045, hit_mat))

    trap = [rod("TrapRay", t_o, t_end, 0.016, trap_beam),
            sphere("TrapEmitter", t_o, 0.06, trap_end)]
    if not t_ok:
        trap.append(sphere("TrapMissEnd", t_end, 0.03, trap_end))

    # a low walnut plinth the block stands on (block bottom at z = loc - scale)
    base_z = TARGET_LOC[2] - TARGET_SCALE[2]
    pme = bpy.data.meshes.new("Plinth")
    bm = bmesh.new()
    try:
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=64, radius1=1.9,
                                    radius2=1.9, depth=base_z)
        for v in res["verts"]:
            v.co.z += base_z / 2
        bm.to_mesh(pme)
    finally:
        bm.free()
    pme.materials.append(plinth_mat)
    for poly in pme.polygons:
        poly.use_smooth = True
    plinth = bpy.data.objects.new("Plinth", pme)
    scene.collection.objects.link(plinth)
    plinth.location = (TARGET_LOC[0], TARGET_LOC[1], 0.0)
    pb = plinth.modifiers.new("Chamfer", 'BEVEL')
    pb.width = 0.02
    pb.segments = 3
    pb.limit_method = 'ANGLE'

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

    centre = Vector((TARGET_LOC[0], TARGET_LOC[1], 1.05))

    def light(name, loc, energy, size, col, aim):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(ob)

    light("Key", (-4.0, -5.0, 6.0), 520.0, 4.0, (1.0, 0.96, 0.9), centre)
    light("Fill", (5.5, -4.0, 2.5), 110.0, 6.0, (0.75, 0.85, 1.0), centre)
    light("Rim", (-1.0, 5.0, 6.0), 320.0, 3.0, (0.6, 0.78, 1.0), centre)
    light("Wedge", (2.5, 4.0, 3.0), 420.0, 5.0, (1.0, 0.76, 0.5), (4.0, 7.5, 1.0))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = centre + 1.15 * Vector((-5.2, -8.6, 4.4))
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre
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
    # AgX would wash the emissive orange rays toward pastel (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=shown + [plinth],
        elements=shown + trap + [plinth],
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
    p.add_argument("--world-to-object", action="store_true",
                   help="feed world coords to Object.ray_cast in the checked path (must fail)")
    args = p.parse_args(argv)

    obj = build_target()
    code = check(obj, world_to_object=args.world_to_object)
    if code:
        return code

    if args.output:
        rcode = render_still(obj, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("ray-cast-space OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
