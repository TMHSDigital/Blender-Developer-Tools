"""Geometry Nodes Simulation Zone ballistic fountain — a runnable example.

Witnesses the Simulation Zone frame contract from
``skills/geometry-nodes-python``. A zone integrates state only when the
scene advances one frame at a time; the evaluated result at frame N is not a
function of N. AI code that sets ``scene.frame_set(N)`` and reads positions
gets a silently wrong answer.

Each jet's droplet is a point carrying a ``vel`` attribute. Per step the zone
applies the constant-gravity update that is exact for any ``dt``::

    p += v*dt - 0.5*g*dt^2 * z
    v -= g*dt * z

so at frame f every point must sit on the closed-form ballistic arc
``p0 + v0*t - 0.5*g*t^2*z`` with ``t = (f - frame_start) / fps``, and carry
``v0 - g*t*z``. The check recomputes both from the launch data.

Measured identically on 4.5.11 LTS, 5.1.2 and 5.2.1 LTS (the API has not
diverged across the three):

* At ``frame_start`` the zone body runs once with Delta Time 0 (state reset).
* Each consecutive ``frame_set(f + 1)`` runs one step with dt = 1/fps.
* A forward jump ``frame_set(start)`` -> ``frame_set(N)`` with no cache runs
  exactly ONE step with dt = 1/fps. Frame N shows the frame-2 state.
* ``bpy.ops.object.simulation_nodes_cache_calculate_to_frame`` fails its poll
  headless: it logs "Invalid operator call", returns ``{'PASS_THROUGH'}``
  without raising, and frames between the two cached endpoints then read as
  a linear interpolation of them — a second silent wrong answer.
* ``bpy.ops.object.simulation_nodes_cache_bake(selected=True)`` under
  ``temp_override`` bakes the frame range (PACKED, in memory, no directory)
  and random-access ``frame_set`` then returns the exact per-frame state.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python gn_sim_fountain.py --
    blender --background --python gn_sim_fountain.py -- --euler          # exit 4
    blender --background --python gn_sim_fountain.py -- --output f.png
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

G = 9.81
FPS = 24
FRAME_START = 1
STEPS = 24                       # 1.0 s of flight, frame 1 -> frame 25
FRAME_END = FRAME_START + STEPS
# float32 state accumulated over STEPS updates: measured worst 2e-6 m (see README)
TOL = 1e-4
# the jump trap must be unmistakable, not a rounding difference
TRAP_GAP_FLOOR = 0.25
# random-access order for the baked read: backwards, forwards, repeats
SCRAMBLED = (FRAME_END, 7, FRAME_START + 1, 19, 12, FRAME_END, 3)

# Jets: (count, launch radius, launch height, radial speed, vertical speed).
# The crown throws up and out; the rim jets arc inward.
CROWN = (8, 0.09, 1.52, 0.80, 3.55)
RIM = (12, 1.52, 0.50, -1.30, 2.95)
WATER_Z = 0.36                  # render only: droplets below the water are hidden


def jets():
    """Launch positions and velocities, crown first then rim."""
    out = []
    for count, radius, height, v_r, v_z in (CROWN, RIM):
        phase = 0.0 if count == CROWN[0] else math.pi / count
        for i in range(count):
            a = phase + 2 * math.pi * i / count
            d = Vector((math.cos(a), math.sin(a), 0.0))
            out.append((d * radius + Vector((0.0, 0.0, height)), d * v_r + Vector((0.0, 0.0, v_z))))
    return out


def closed_form(p0, v0, t):
    return (p0 + v0 * t + Vector((0.0, 0.0, -0.5 * G * t * t)),
            v0 + Vector((0.0, 0.0, -G * t)))


def build_tree(pair=True, euler=False):
    tree = bpy.data.node_groups.new("BallisticSim", "GeometryNodeTree")
    tree.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = tree.nodes, tree.links
    gi = nodes.new("NodeGroupInput")
    go = nodes.new("NodeGroupOutput")
    sin = nodes.new("GeometryNodeSimulationInput")
    sout = nodes.new("GeometryNodeSimulationOutput")
    if not pair:
        # Unpaired Simulation Input has no Geometry socket. Leave the output
        # empty so evaluation cannot silently pass the emitter through.
        return tree
    if not sin.pair_with_output(sout):
        raise RuntimeError("SimulationInput.pair_with_output failed")

    pos = nodes.new("GeometryNodeInputPosition")
    vel = nodes.new("GeometryNodeInputNamedAttribute")
    vel.data_type = "FLOAT_VECTOR"
    vel.inputs["Name"].default_value = "vel"
    dt = sin.outputs["Delta Time"]

    # p + v*dt (- 0.5*g*dt^2 on z unless --euler)
    v_dt = nodes.new("ShaderNodeVectorMath")
    v_dt.operation = "SCALE"
    links.new(vel.outputs["Attribute"], v_dt.inputs[0])
    links.new(dt, v_dt.inputs["Scale"])
    new_pos = nodes.new("ShaderNodeVectorMath")
    new_pos.operation = "ADD"
    links.new(pos.outputs["Position"], new_pos.inputs[0])
    links.new(v_dt.outputs["Vector"], new_pos.inputs[1])
    pos_out = new_pos.outputs["Vector"]
    if not euler:
        dt2 = nodes.new("ShaderNodeMath")
        dt2.operation = "MULTIPLY"
        links.new(dt, dt2.inputs[0])
        links.new(dt, dt2.inputs[1])
        half_g = nodes.new("ShaderNodeMath")
        half_g.operation = "MULTIPLY"
        half_g.inputs[1].default_value = -0.5 * G
        links.new(dt2.outputs["Value"], half_g.inputs[0])
        drop = nodes.new("ShaderNodeCombineXYZ")
        links.new(half_g.outputs["Value"], drop.inputs["Z"])
        with_drop = nodes.new("ShaderNodeVectorMath")
        with_drop.operation = "ADD"
        links.new(pos_out, with_drop.inputs[0])
        links.new(drop.outputs["Vector"], with_drop.inputs[1])
        pos_out = with_drop.outputs["Vector"]

    # v - g*dt on z
    g_dt = nodes.new("ShaderNodeMath")
    g_dt.operation = "MULTIPLY"
    g_dt.inputs[1].default_value = -G
    links.new(dt, g_dt.inputs[0])
    dv = nodes.new("ShaderNodeCombineXYZ")
    links.new(g_dt.outputs["Value"], dv.inputs["Z"])
    new_vel = nodes.new("ShaderNodeVectorMath")
    new_vel.operation = "ADD"
    links.new(vel.outputs["Attribute"], new_vel.inputs[0])
    links.new(dv.outputs["Vector"], new_vel.inputs[1])

    # Set Position first: its field reads the old vel. Storing vel first would
    # make the position update read the new one.
    setp = nodes.new("GeometryNodeSetPosition")
    links.new(sin.outputs["Geometry"], setp.inputs["Geometry"])
    links.new(pos_out, setp.inputs["Position"])
    store = nodes.new("GeometryNodeStoreNamedAttribute")
    store.data_type = "FLOAT_VECTOR"
    store.domain = "POINT"
    store.inputs["Name"].default_value = "vel"
    links.new(setp.outputs["Geometry"], store.inputs["Geometry"])
    links.new(new_vel.outputs["Vector"], store.inputs["Value"])

    links.new(gi.outputs["Geometry"], sin.inputs["Geometry"])
    links.new(store.outputs["Geometry"], sout.inputs["Geometry"])
    links.new(sout.outputs["Geometry"], go.inputs["Geometry"])
    return tree


def build(pair=True, euler=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.render.fps_base = 1.0
    sc.frame_start = FRAME_START
    sc.frame_end = FRAME_END

    launch = jets()
    me = bpy.data.meshes.new("Nozzles")
    me.vertices.add(len(launch))
    me.vertices.foreach_set("co", [c for p, _ in launch for c in p])
    attr = me.attributes.new("vel", "FLOAT_VECTOR", "POINT")
    attr.data.foreach_set("vector", [c for _, v in launch for c in v])
    ob = bpy.data.objects.new("Droplets", me)
    sc.collection.objects.link(ob)
    mod = ob.modifiers.new("Ballistic", "NODES")
    mod.node_group = build_tree(pair=pair, euler=euler)
    return ob, launch


def read_state(ob):
    """Evaluated (positions, velocities) of the simulated points."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        n = len(me.vertices)
        co = [0.0] * (3 * n)
        me.vertices.foreach_get("co", co)
        vel = [0.0] * (3 * n)
        a = me.attributes.get("vel")
        if a is not None and a.domain == "POINT" and n:
            a.data.foreach_get("vector", vel)
    finally:
        ev.to_mesh_clear()
    pts = [Vector(co[i:i + 3]) for i in range(0, 3 * n, 3)]
    vels = [Vector(vel[i:i + 3]) for i in range(0, 3 * n, 3)]
    return pts, vels


def worst_error(state, launch, t):
    pts, vels = state
    wp = wv = 0.0
    for (p0, v0), p, v in zip(launch, pts, vels):
        ep, ev = closed_form(p0, v0, t)
        wp = max(wp, (p - ep).length)
        wv = max(wv, (v - ev).length)
    return wp, wv


def t_of(frame):
    return (frame - FRAME_START) / FPS


def select_override(ob):
    return bpy.context.temp_override(
        active_object=ob, object=ob, selected_objects=[ob], selected_editable_objects=[ob],
    )


def fill_cache(ob, use_calc_to_frame=False):
    """Bake the simulation range so any frame reads the stepped state."""
    sc = bpy.context.scene
    with select_override(ob):
        if use_calc_to_frame:
            # The tempting operator. Its poll fails headless; it returns
            # PASS_THROUGH without raising and computes nothing.
            sc.frame_set(FRAME_END)
            return bpy.ops.object.simulation_nodes_cache_calculate_to_frame(selected=True)
        return bpy.ops.object.simulation_nodes_cache_bake(selected=True)


def delete_cache(ob):
    with select_override(ob):
        bpy.ops.object.simulation_nodes_cache_delete(selected=True)


def check(ob, launch, prebake_trap=False, calc_to_frame=False):
    sc = bpy.context.scene
    n = len(launch)

    # 3 — the paired zone evaluates one point per jet, at rest on the nozzles
    sc.frame_set(FRAME_START)
    state = read_state(ob)
    if len(state[0]) != n:
        print(f"ERROR: zone evaluated {len(state[0])} points at frame_start, expected {n} "
              f"(one per jet); an unpaired zone outputs nothing", file=sys.stderr)
        return 3
    wp, wv = worst_error(state, launch, 0.0)
    if wp > TOL or wv > TOL:
        print(f"ERROR: frame_start state off the launch data by {wp:.2e} m, {wv:.2e} m/s",
              file=sys.stderr)
        return 3
    print(f"frame_start: {n} points on the nozzles (err {wp:.1e} m)")

    # 4 — stepping one frame at a time lands on the closed-form arc every frame
    trail = [state[0]]
    worst_p = worst_v = 0.0
    for f in range(FRAME_START + 1, FRAME_END + 1):
        sc.frame_set(f)
        state = read_state(ob)
        if len(state[0]) != n:
            print(f"ERROR: frame {f} evaluated {len(state[0])} points, expected {n}", file=sys.stderr)
            return 4
        wp, wv = worst_error(state, launch, t_of(f))
        worst_p, worst_v = max(worst_p, wp), max(worst_v, wv)
        trail.append(state[0])
    if worst_p > TOL or worst_v > TOL:
        print(f"ERROR: stepped frames {FRAME_START}..{FRAME_END} miss p0 + v0 t - g t^2/2 by up to "
              f"{worst_p:.4f} m and v0 - g t by {worst_v:.4f} m/s (tol {TOL})", file=sys.stderr)
        return 4
    print(f"stepped {STEPS} frames: worst position err {worst_p:.2e} m, "
          f"velocity err {worst_v:.2e} m/s (tol {TOL})")

    # 5 — the trap: a direct jump with no cache runs exactly one step
    delete_cache(ob)
    sc.frame_set(FRAME_START)
    if prebake_trap:
        fill_cache(ob)
    sc.frame_set(FRAME_END)
    state = read_state(ob)
    one_step_p, _ = worst_error(state, launch, 1.0 / FPS)
    true_p, _ = worst_error(state, launch, t_of(FRAME_END))
    gap = min((p - closed_form(p0, v0, t_of(FRAME_END))[0]).length
              for (p0, v0), p in zip(launch, state[0])) if state[0] else 0.0
    label = "prebaked" if prebake_trap else "unbaked"
    print(f"jump {FRAME_START}->{FRAME_END} {label}: off the one-step state by {one_step_p:.2e} m, "
          f"off the frame-{FRAME_END} arc by {gap:.3f}..{true_p:.3f} m")
    if one_step_p > TOL or gap < TRAP_GAP_FLOOR:
        print(f"ERROR: jump did not reproduce the one-step trap (one-step err {one_step_p:.2e} m, "
              f"min gap to the true arc {gap:.4f} m < {TRAP_GAP_FLOOR})", file=sys.stderr)
        return 5

    # 6 — the remedy: bake, then any frame in any order reads the stepped state
    delete_cache(ob)
    sc.frame_set(FRAME_START)
    result = fill_cache(ob, use_calc_to_frame=calc_to_frame)
    print(f"cache fill -> {sorted(result)}")
    worst_p = worst_v = 0.0
    for f in SCRAMBLED:
        sc.frame_set(f)
        wp, wv = worst_error(read_state(ob), launch, t_of(f))
        worst_p, worst_v = max(worst_p, wp), max(worst_v, wv)
    if result != {"FINISHED"} or worst_p > TOL or worst_v > TOL:
        print(f"ERROR: after cache fill {sorted(result)}, frames {list(SCRAMBLED)} miss the arc by "
              f"up to {worst_p:.4f} m / {worst_v:.4f} m/s (tol {TOL})", file=sys.stderr)
        return 6
    print(f"baked random access {list(SCRAMBLED)}: worst err {worst_p:.2e} m, {worst_v:.2e} m/s")
    return 0, trail


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"))
    p.add_argument("--unpair", action="store_true",
                   help="falsification: Simulation Input never paired with its Output (exit 3)")
    p.add_argument("--euler", action="store_true",
                   help="falsification: naive p += v*dt drops the g*dt^2/2 term (exit 4)")
    p.add_argument("--prebake-trap", action="store_true",
                   help="falsification: bake before the jump, so the trap cannot show (exit 5)")
    p.add_argument("--calc-to-frame", action="store_true",
                   help="falsification: fill the cache with calculate_to_frame, not bake (exit 6)")
    args = p.parse_args(argv)

    ob, launch = build(pair=not args.unpair, euler=args.euler)
    result = check(ob, launch, prebake_trap=args.prebake_trap, calc_to_frame=args.calc_to_frame)
    if isinstance(result, int):
        return result
    _, trail = result

    if args.output:
        rcode = render_still(ob, launch, trail, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("gn-sim-fountain OK")
    return 0


# ---------------------------------------------------------------- render only
# (r, z) lathe profiles, outside in. Nothing below is read by the check.
BASIN_PROFILE = [
    (0.0, 0.0), (2.04, 0.0), (2.04, 0.06), (1.99, 0.085), (1.93, 0.09), (1.91, 0.12),
    (1.94, 0.15), (1.95, 0.19), (1.92, 0.22), (1.87, 0.23), (1.85, 0.27), (1.84, 0.44),
    (1.88, 0.47), (1.90, 0.52), (1.87, 0.57), (1.78, 0.59), (1.67, 0.58), (1.61, 0.55),
    (1.59, 0.50), (1.58, 0.16), (0.0, 0.16),
]
PEDESTAL_PROFILE = [
    (0.0, 0.16), (0.46, 0.16), (0.46, 0.30), (0.40, 0.34), (0.30, 0.40), (0.22, 0.52),
    (0.18, 0.70), (0.17, 0.95), (0.21, 1.03), (0.24, 1.08), (0.20, 1.12), (0.36, 1.18),
    (0.56, 1.25), (0.66, 1.30), (0.68, 1.35), (0.64, 1.38), (0.58, 1.37), (0.20, 1.29),
    (0.0, 1.28),
]
SPIRE_PROFILE = [
    (0.0, 1.28), (0.10, 1.28), (0.10, 1.31), (0.06, 1.36), (0.05, 1.44), (0.075, 1.47),
    (0.075, 1.50), (0.045, 1.53), (0.0, 1.535),
]
BOWL_WATER = (0.60, 1.33)        # radius, height of the upper bowl's water
DROP_R = 0.030
ARC_R = 0.0055


def lathe(name, profile, steps=96):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        verts = [bm.verts.new((r, 0.0, z)) for r, z in profile]
        edges = [bm.edges.new((a, b)) for a, b in zip(verts, verts[1:])]
        bmesh.ops.spin(bm, geom=verts + edges, cent=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0),
                       angle=2 * math.pi, steps=steps, use_merge=True)
        bmesh.ops.remove_doubles(bm, verts=sorted(bm.verts, key=lambda v: v.index), dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(me)
    finally:
        bm.free()
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def disc(name, radius, z, segments=96):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        bmesh.ops.create_circle(bm, cap_ends=True, segments=segments, radius=radius)
        bmesh.ops.translate(bm, verts=list(bm.verts), vec=(0.0, 0.0, z))
        bm.to_mesh(me)
    finally:
        bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def droplet_mesh(name, points):
    """One icosphere per simulated droplet position above the water."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for p in points:
            bmesh.ops.create_icosphere(bm, subdivisions=2, radius=DROP_R,
                                       matrix=Matrix.Translation(p))
        bm.to_mesh(me)
    finally:
        bm.free()
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def arc_curves(name, launch):
    """The closed-form arcs, drawn from the launch data, not from the sim."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = ARC_R
    cu.bevel_resolution = 2
    for p0, v0 in launch:
        pts = []
        t = 0.0
        while True:
            p, _ = closed_form(p0, v0, t)
            if p.z < WATER_Z:
                break
            pts.append(p)
            t += 0.01
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        sp.points.foreach_set("co", [c for p in pts for c in (p.x, p.y, p.z, 1.0)])
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def nozzles(name, launch):
    """Bronze spouts at each rim jet, pointing along its launch velocity."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        for p0, v0 in launch[CROWN[0]:]:
            d = v0.normalized()
            rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
            m = Matrix.Translation(p0 - d * 0.075) @ rot
            bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.034,
                                  radius2=0.020, depth=0.15, matrix=m)
        bm.to_mesh(me)
    finally:
        bm.free()
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def material(name, color, roughness, metallic=0.0, emission=None, strength=0.0,
             noise_tint=None, bump=0.0, joints=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = emission
        bsdf.inputs["Emission Strength"].default_value = strength
    if noise_tint is not None:
        # dressed-stone variation: low-frequency tint plus a fine tooling bump
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 4.5
        noise.inputs["Detail"].default_value = 6.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = noise_tint
        ramp.color_ramp.elements[1].color = color
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[1].position = 0.70
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        height = None
        if bump:
            fine = nt.nodes.new("ShaderNodeTexNoise")
            fine.inputs["Scale"].default_value = 60.0
            height = fine.outputs["Fac"]
        if joints:
            # radial block joints: angle about Z, JOINTS blocks per turn, a thin
            # mortar line where the block fraction wraps
            coord = nt.nodes.new("ShaderNodeTexCoord")
            xyz = nt.nodes.new("ShaderNodeSeparateXYZ")
            nt.links.new(coord.outputs["Object"], xyz.inputs["Vector"])
            ang = nt.nodes.new("ShaderNodeMath")
            ang.operation = "ARCTAN2"
            nt.links.new(xyz.outputs["Y"], ang.inputs[0])
            nt.links.new(xyz.outputs["X"], ang.inputs[1])
            per = nt.nodes.new("ShaderNodeMath")
            per.operation = "MULTIPLY"
            per.inputs[1].default_value = joints / (2 * math.pi)
            nt.links.new(ang.outputs["Value"], per.inputs[0])
            frac = nt.nodes.new("ShaderNodeMath")
            frac.operation = "PINGPONG"          # 0 at a joint, 0.5 mid-block
            frac.inputs[1].default_value = 0.5
            nt.links.new(per.outputs["Value"], frac.inputs[0])
            line = nt.nodes.new("ShaderNodeMath")
            line.operation = "LESS_THAN"
            line.inputs[1].default_value = 0.022
            nt.links.new(frac.outputs["Value"], line.inputs[0])
            mortar = nt.nodes.new("ShaderNodeMix")
            mortar.data_type = "RGBA"
            mortar.inputs["B"].default_value = (0.16, 0.10, 0.06, 1.0)
            nt.links.new(line.outputs["Value"], mortar.inputs["Factor"])
            nt.links.new(ramp.outputs["Color"], mortar.inputs["A"])
            nt.links.new(mortar.outputs["Result"], bsdf.inputs["Base Color"])
            if height is not None:
                recess = nt.nodes.new("ShaderNodeMath")
                recess.operation = "MULTIPLY_ADD"
                recess.inputs[1].default_value = -0.6
                nt.links.new(line.outputs["Value"], recess.inputs[0])
                nt.links.new(height, recess.inputs[2])
                height = recess.outputs["Value"]
        if height is not None:
            bmp = nt.nodes.new("ShaderNodeBump")
            bmp.inputs["Strength"].default_value = bump
            nt.links.new(height, bmp.inputs["Height"])
            nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def eevee_engine_id():
    return "BLENDER_EEVEE" if bpy.app.version >= (5, 0, 0) else "BLENDER_EEVEE_NEXT"


def render_still(ob, launch, trail, path, engine):
    scene = bpy.context.scene
    scene.frame_set(FRAME_START)
    ob.hide_render = True        # the live points; the still shows the recorded trail

    stone = material("Sandstone", (0.70, 0.46, 0.27, 1.0), 0.8,
                     noise_tint=(0.47, 0.29, 0.16, 1.0), bump=0.22, joints=28)
    turned = material("TurnedStone", (0.70, 0.46, 0.27, 1.0), 0.72,
                      noise_tint=(0.47, 0.29, 0.16, 1.0), bump=0.15)
    bronze = material("Bronze", (0.62, 0.36, 0.15, 1.0), 0.34, metallic=0.9)
    water = material("Pool", (0.02, 0.16, 0.20, 1.0), 0.32)
    # a mirror-flat pool reflects the rim light as a pale sheet over the water
    water.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.25
    drop = material("Droplet", (0.45, 0.82, 1.0, 1.0), 0.12,
                    emission=(0.35, 0.78, 1.0, 1.0), strength=0.9)
    arc = material("Arc", (0.8, 0.92, 1.0, 1.0), 0.3,
                   emission=(0.7, 0.88, 1.0, 1.0), strength=0.35)

    basin = lathe("Basin", BASIN_PROFILE)
    pedestal = lathe("Pedestal", PEDESTAL_PROFILE)
    basin.data.materials.append(stone)
    pedestal.data.materials.append(turned)
    spire = lathe("Spire", SPIRE_PROFILE, steps=48)
    spire.data.materials.append(bronze)
    spouts = nozzles("Spouts", launch)
    spouts.data.materials.append(bronze)
    pool = disc("Pool", 1.585, WATER_Z)
    bowl = disc("BowlPool", BOWL_WATER[0], BOWL_WATER[1])
    for o in (pool, bowl):
        o.data.materials.append(water)
    above = [p for frame in trail for p in frame if p.z > WATER_Z + DROP_R * 0.5]
    drops = droplet_mesh("DropletTrail", above)
    drops.data.materials.append(drop)
    arcs = arc_curves("Arcs", launch)
    arcs.data.materials.append(arc)

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    studio = material("Studio", (0.03, 0.032, 0.037, 1.0), 0.7)
    floor_me.materials.append(studio)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 8.0, 0.0)
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
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(lo)

    light("Key", (-4.0, -5.0, 6.0), 560.0, 5.0, (1.0, 0.96, 0.9), (46, 0, -35))
    light("Fill", (5.0, -3.5, 3.0), 70.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Wedge", (1.2, 5.2, 3.6), 420.0, 6.0, (1.0, 0.76, 0.5), (100, 0, 10))
    light("Rim", (-1.8, 4.6, 5.6), 240.0, 4.0, (0.6, 0.78, 1.0), (42, 0, 180))

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 0.74)
    scene.collection.objects.link(aim)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (4.0, -7.95, 4.75)
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
        scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    # Standard, not AgX: AgX washes the droplet cyan and lifts the stage to grey
    scene.view_settings.view_transform = "Standard"

    hero = [basin, pedestal, spire, spouts, drops, arcs]
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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
