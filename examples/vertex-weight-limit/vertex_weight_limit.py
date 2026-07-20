"""A rigged mech arm pruned to the 4-influence game-engine limit — a runnable example.

Witnesses the skinning constraint every game engine enforces and AI-generated
rigging code most often violates silently: **no more than four bone influences
per vertex, weights summing to one**.

1. The limit is enforced through the data API, not the context-heavy
   ``bpy.ops.object.vertex_group_limit_total`` path: read each vertex's groups,
   keep the top four by weight, ``VertexGroup.remove`` the rest, then
   renormalize the survivors to sum 1. Dropping without renormalizing leaves
   sums < 1 and the mesh shrinks toward the origin under load.
2. The armature modifier is still exactly linear blend skinning (the
   armature-bend precedent — built on, not duplicated): after limiting, every
   depsgraph-evaluated vertex equals sum_i w_i (pose.matrix @
   rest_local.inverted()) @ rest with the weights **read back from the mesh's
   own deform layer** (``v.groups``), not from the authoring function. The
   weights on the mesh are the contract, not the weights you meant to write.
3. Pruning must not damage the pose: evaluated positions before and after the
   limit are compared and held within tolerance. The root stays pinned — the
   pedestal mount never moves.

The vertex-group API (``v.groups``, ``VertexGroup.add``/``remove``) is stable
between Blender 4.5 LTS and 5.1 — the example runs identically on both, which
is itself the version witness.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python vertex_weight_limit.py --                 # check only
    blender --background --python vertex_weight_limit.py -- --output a.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
import mathutils

SIDES = 32
MAX_INFLUENCES = 4              # the engine constraint being witnessed
BUMP_R = 1.8                    # flex-cuff blend support; guarantees 5 pre-limit
LBS_TOL = 5e-4                  # float32 mesh coords vs double pose matrices
SUM_TOL = 1e-5                  # per-vertex weight sum after renormalize
POSE_TOL = 0.05                 # pruning must not move the pose beyond this
BONES = ("Root", "Shoulder", "Elbow", "Wrist", "Claw")
BONE_SPANS = {"Root": (-0.35, 0.10), "Shoulder": (0.10, 1.35),
              "Elbow": (1.35, 2.55), "Wrist": (2.55, 2.90), "Claw": (2.90, 3.35)}
BONE_CENTERS = {b: (s[0] + s[1]) / 2 for b, s in BONE_SPANS.items()}
POSE_DEG = {"Shoulder": -8.0, "Elbow": -35.0, "Wrist": -14.0, "Claw": 6.0}

# armor palette slots
GUNMETAL, ORANGE, RUBBER, ACCENT = 0, 1, 2, 3


def bump(z, center, radius=BUMP_R):
    """Smooth, compactly-supported influence: (1 - (d/r)^2)^2 inside r, else 0."""
    d = abs(z - center) / radius
    return (1.0 - d * d) ** 2 if d < 1.0 else 0.0


def flex_weights(z):
    """Rich pre-limit weights over all five bones — cuffs blend broadly."""
    w = [bump(z, BONE_CENTERS[b]) for b in BONES]
    total = sum(w)
    return [x / total for x in w]


def lathe_part(bm, rings, mat):
    """Revolve (z, r) rings around Z; returns the ring vertex lists."""
    out = []
    for z, r in rings:
        out.append([bm.verts.new((r * math.cos(2 * math.pi * s / SIDES),
                                  r * math.sin(2 * math.pi * s / SIDES), z))
                    for s in range(SIDES)])
    for k in range(len(out) - 1):
        for s in range(SIDES):
            f = bm.faces.new((out[k][s], out[k][(s + 1) % SIDES],
                              out[k + 1][(s + 1) % SIDES], out[k + 1][s]))
            f.material_index = mat
    return out


def box_part(bm, size, loc, rot, mat, part_of, bone):
    """One box shell (rot in degrees XYZ); tags `bone` for its verts."""
    n0f, n0v = len(bm.faces), len(bm.verts)
    m = (mathutils.Matrix.Translation(loc)
         @ mathutils.Euler(tuple(math.radians(a) for a in rot)).to_matrix().to_4x4()
         @ mathutils.Matrix.Diagonal((*size, 1.0)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    for f in bm.faces[n0f:]:
        f.material_index = mat
    part_of.extend([bone] * (len(bm.verts) - n0v))


def cone_part(bm, r1, r2, depth, loc, rot, mat, part_of, bone, segments=24):
    """One cylinder/cone shell along a rotated axis; tags `bone` for its verts."""
    n0f, n0v = len(bm.faces), len(bm.verts)
    m = (mathutils.Matrix.Translation(loc)
         @ mathutils.Euler(tuple(math.radians(a) for a in rot)).to_matrix().to_4x4())
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=r1, radius2=r2, depth=depth, matrix=m)
    for f in bm.faces[n0f:]:
        f.material_index = mat
    part_of.extend([bone] * (len(bm.verts) - n0v))


def build_arm():
    """The mech arm, built as a machine: bolted pedestal and shoulder fairing
    (Root), a shoulder hub and upper arm ending in clevis cheeks (Shoulder),
    the elbow hinge pin inside a ribbed flex bellows (the >4-influence zone),
    a long plated forearm (Elbow), wrist bellows and collar (Wrist), and a
    palm with three two-segment fingers (Claw). Every part is closed form;
    the flex bellows keep the z ranges the five-bone bumps are tuned for."""
    me = bpy.data.meshes.new("MechArm")
    part_of = []   # creation-order bone name (or 'FLEX') per mesh vertex
    bm = bmesh.new()
    try:
        def tag(rings_verts, bone):
            for ring in rings_verts:
                for v in ring:
                    part_of.append(bone)

        # bolted pedestal + shoulder fairing on a wide flange (rigid on Root)
        tag(lathe_part(bm, [(-0.35, 0.38), (-0.05, 0.38), (0.0, 0.44),
                            (0.06, 0.46)], GUNMETAL), "Root")
        tag(lathe_part(bm, [(0.02, 0.44), (0.10, 0.48), (0.22, 0.37),
                            (0.30, 0.19), (0.34, 0.08)], GUNMETAL), "Root")
        tag(lathe_part(bm, [(-0.02, 0.50), (0.05, 0.50)], GUNMETAL), "Root")
        for k in range(8):  # hex bolts around the flange rim
            a = 2 * math.pi * k / 8
            cone_part(bm, 0.055, 0.055, 0.07,
                      (0.43 * math.cos(a), 0.43 * math.sin(a), 0.06),
                      (0, 0, 0), GUNMETAL, part_of, "Root", segments=6)
        # upper arm shell rooted deep inside the fairing — no gap at the
        # shoulder when the joint articulates (rigid on Shoulder)
        tag(lathe_part(bm, [(0.10, 0.16), (0.30, 0.22), (0.45, 0.22),
                            (0.60, 0.26), (0.80, 0.26), (1.00, 0.25),
                            (1.20, 0.24)], ORANGE), "Shoulder")
        # panel-seam groove on the upper arm (plate separation line)
        tag(lathe_part(bm, [(0.90, 0.262), (0.94, 0.262)], GUNMETAL), "Shoulder")
        # clevis cheek plates flanking the joint (rigid on Shoulder)
        for sy in (-1, 1):
            box_part(bm, (0.12, 0.07, 0.50), (0.0, sy * 0.19, 1.30),
                     (0, 0, 0), ORANGE, part_of, "Shoulder")
        # elbow flex cuff behind the hinge: the five-influence zone the
        # limit prunes (every ring inside the five-bump z window)
        tag(lathe_part(bm, [(1.33, 0.19), (1.38, 0.21), (1.43, 0.19),
                            (1.49, 0.21), (1.55, 0.20)], RUBBER), "FLEX")
        # the hinge pin stays with the clevis (Shoulder): the forearm's
        # knuckle barrel (Elbow) rotates around it — pin caps must not tilt
        cone_part(bm, 0.15, 0.15, 0.50, (0.0, 0.0, 1.35), (90, 0, 0),
                  GUNMETAL, part_of, "Shoulder")
        cone_part(bm, 0.185, 0.185, 0.28, (0.0, 0.0, 1.35), (90, 0, 0),
                  GUNMETAL, part_of, "Elbow")
        # hex bolt heads flush on the cheeks — fasteners, not buttons
        for sy in (-1, 1):
            cone_part(bm, 0.15, 0.15, 0.06, (0.0, sy * 0.255, 1.35),
                      (90, 0, 0), GUNMETAL, part_of, "Shoulder", segments=6)
        # bright seal hoop on the cuff — the accent marking the primary
        # pruned-weight zone
        tag(lathe_part(bm, [(1.42, 0.22), (1.46, 0.22)], ACCENT), "Elbow")
        # long plated forearm with panel-seam grooves (rigid on Elbow)
        tag(lathe_part(bm, [(1.55, 0.22), (1.75, 0.24), (1.86, 0.25),
                            (2.05, 0.23), (2.24, 0.23), (2.45, 0.21)],
                       ORANGE), "Elbow")
        tag(lathe_part(bm, [(1.88, 0.262), (1.92, 0.262)], GUNMETAL), "Elbow")
        tag(lathe_part(bm, [(2.26, 0.242), (2.30, 0.242)], GUNMETAL), "Elbow")
        # armor blade along the forearm's back (rigid on Elbow)
        box_part(bm, (0.12, 0.06, 0.60), (0.0, 0.26, 2.02),
                 (0, 0, 0), ORANGE, part_of, "Elbow")
        # wrist flex bellows (second blend zone) + collar
        tag(lathe_part(bm, [(2.45, 0.20), (2.51, 0.22), (2.57, 0.18),
                            (2.64, 0.21), (2.70, 0.18), (2.75, 0.19)],
                       RUBBER), "FLEX")
        tag(lathe_part(bm, [(2.75, 0.18), (2.85, 0.195), (2.90, 0.18)],
                       GUNMETAL), "Wrist")
        # palm block (rigid on Wrist)
        box_part(bm, (0.34, 0.25, 0.26), (0.0, 0.0, 2.98),
                 (0, 0, 0), GUNMETAL, part_of, "Wrist")
        # three two-segment fingers, splayed (rigid on Claw)
        for a_deg in (90.0, 210.0, 330.0):
            a = math.radians(a_deg)
            for pos, tilt, size in (((0.09, 3.08), 12.0, (0.095, 0.14, 0.22)),
                                    ((0.16, 3.26), 26.0, (0.08, 0.12, 0.18))):
                off, z = pos
                m = (mathutils.Matrix.Translation((0.0, 0.0, z))
                     @ mathutils.Matrix.Rotation(a, 4, 'Z')
                     @ mathutils.Matrix.Translation((off, 0.0, 0.0))
                     @ mathutils.Matrix.Rotation(math.radians(tilt), 4, 'Y')
                     @ mathutils.Matrix.Diagonal((*size, 1.0)))
                n0f, n0v = len(bm.faces), len(bm.verts)
                bmesh.ops.create_cube(bm, size=1.0, matrix=m)
                for f in bm.faces[n0f:]:
                    f.material_index = GUNMETAL
                part_of.extend(["Claw"] * (len(bm.verts) - n0v))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()  # the ownership contract, as always
    for poly in me.polygons:
        poly.use_smooth = False
    obj = bpy.data.objects.new("MechArm", me)
    bpy.context.collection.objects.link(obj)
    return obj, part_of


def assign_weights(obj, part_of):
    """Author the rich pre-limit weights: hard single-bone on armor, broad
    five-bone bumps in the flex cuffs."""
    groups = {b: obj.vertex_groups.new(name=b) for b in BONES}
    if len(part_of) != len(obj.data.vertices):
        raise RuntimeError(f"part tag count {len(part_of)} != vert count "
                           f"{len(obj.data.vertices)}")
    for idx, v in enumerate(obj.data.vertices):
        bone = part_of[idx]
        if bone == "FLEX":
            for b, w in zip(BONES, flex_weights(v.co.z)):
                if w > 0.0:
                    groups[b].add([idx], w, 'REPLACE')
        else:
            groups[bone].add([idx], 1.0, 'REPLACE')
    return groups


def build_rig(obj):
    arm_data = bpy.data.armatures.new("ArmRig")
    arm = bpy.data.objects.new("ArmRig", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for name in BONES:
        eb = arm_data.edit_bones.new(name)
        z0, z1 = BONE_SPANS[name]
        eb.head = (0.0, 0.0, z0)
        eb.tail = (0.0, 0.0, z1)
        if prev is not None:
            eb.parent = prev
            eb.use_connect = True
        prev = eb
    bpy.ops.object.mode_set(mode='OBJECT')
    mod = obj.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    mod.use_vertex_groups = True
    mod.use_bone_envelopes = False
    for name, deg in POSE_DEG.items():
        pb = arm.pose.bones[name]
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler.x = math.radians(deg)
    return arm


def eval_positions(obj):
    """Evaluated vertex positions via the depsgraph; reference released by contract."""
    deps = bpy.context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(deps)
    me = ob_eval.to_mesh()
    try:
        return [tuple(v.co) for v in me.vertices]
    finally:
        ob_eval.to_mesh_clear()


def check(obj, arm, groups, pose_before):
    me = obj.data

    # pre-limit witness: the flex cuffs really carry five influences
    pre_max = max(len(v.groups) for v in me.vertices)
    if pre_max != 5:
        print(f"ERROR: pre-limit max influences {pre_max} != 5 — the rich "
              "authoring drifted; the witness is vacuous", file=sys.stderr)
        return 3

    # the limit, through the data API: keep top-4, drop the rest, renormalize
    changed = 0
    for v in me.vertices:
        gs = sorted(v.groups, key=lambda g: -g.weight)
        if len(gs) > MAX_INFLUENCES:
            changed += 1
        for g in gs[MAX_INFLUENCES:]:
            groups[BONES[g.group]].remove([v.index])
        kept = [g for g in v.groups]
        total = sum(g.weight for g in kept)
        for g in kept:
            groups[BONES[g.group]].add([v.index], g.weight / total, 'REPLACE')

    # contract 1: no vertex exceeds the engine limit
    post_max = max(len(v.groups) for v in me.vertices)
    if post_max > MAX_INFLUENCES:
        print(f"ERROR: vertex carries {post_max} groups after the limit — "
              f"engines cap at {MAX_INFLUENCES}", file=sys.stderr)
        return 4
    if changed == 0:
        print("ERROR: the limit changed nothing — no vertex exceeded the cap, "
              "the witness is vacuous", file=sys.stderr)
        return 5

    # contract 2: every vertex's weights sum to 1 (or the vertex is unskinned)
    sum_err = 0.0
    for v in me.vertices:
        if v.groups:
            sum_err = max(sum_err, abs(sum(g.weight for g in v.groups) - 1.0))
    if sum_err > SUM_TOL:
        print(f"ERROR: weight sums deviate {sum_err:.3e} from 1.0 after "
              "renormalize (dropped groups were not re-balanced)", file=sys.stderr)
        return 6

    bpy.context.view_layer.update()
    pose_after = eval_positions(obj)

    # contract 3: pruning did not damage the pose
    pose_dev = max((mathutils.Vector(a) - mathutils.Vector(b)).length
                   for a, b in zip(pose_before, pose_after))
    if pose_dev > POSE_TOL:
        print(f"ERROR: limiting moved the pose by {pose_dev:.4f} "
              f"(tol {POSE_TOL}) — pruning damaged deformation", file=sys.stderr)
        return 7

    # contract 4: the modifier is still exactly LBS, with the weights read
    # back from the mesh's own deform layer (armature-bend's math, built on)
    mats = {n: arm.pose.bones[n].matrix @ arm.data.bones[n].matrix_local.inverted()
            for n in BONES}
    lbs_err = 0.0
    for v in me.vertices:
        predicted = sum((g.weight * (mats[BONES[g.group]] @ v.co)
                         for g in v.groups),
                        start=mathutils.Vector((0.0, 0.0, 0.0)))
        lbs_err = max(lbs_err, (mathutils.Vector(pose_after[v.index])
                                - predicted).length)
    if lbs_err > LBS_TOL:
        print(f"ERROR: evaluated mesh deviates {lbs_err:.6f} from LBS over the "
              f"limited weights (tol {LBS_TOL})", file=sys.stderr)
        return 8

    # the pedestal mount is rigid on Root and must not move
    root_move = max((mathutils.Vector(pose_after[i]) - v.co).length
                    for i, v in enumerate(me.vertices)
                    if len(v.groups) == 1 and v.groups[0].weight > 0.99
                    and BONES[v.groups[0].group] == "Root")
    if root_move > 1e-5:
        print(f"ERROR: Root-weighted mount moved {root_move:.6f} (Root is unposed)",
              file=sys.stderr)
        return 9

    print(f"verts={len(me.vertices)} pre_max={pre_max} post_max={post_max} "
          f"limited_verts={changed}")
    print(f"sum_err={sum_err:.2e} (tol {SUM_TOL}) pose_dev={pose_dev:.2e} "
          f"(tol {POSE_TOL}) lbs_err={lbs_err:.2e} (tol {LBS_TOL}) "
          f"root_move={root_move:.2e}")
    return 0


def make_materials():
    def pbr(name, base, metallic, roughness, emission=None, strength=0.0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        b = mat.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*base, 1.0)
        b.inputs["Metallic"].default_value = metallic
        b.inputs["Roughness"].default_value = roughness
        if emission is not None:
            sock = b.inputs.get("Emission Color") or b.inputs["Emission"]
            sock.default_value = (*emission, 1.0)
            b.inputs["Emission Strength"].default_value = strength
        return mat
    return [
        pbr("Gunmetal", (0.11, 0.12, 0.14), 0.9, 0.32),
        pbr("HazardOrange", (0.82, 0.30, 0.08), 0.10, 0.45),
        pbr("FlexRubber", (0.04, 0.13, 0.17), 0.0, 0.80,
            emission=(0.06, 0.30, 0.34), strength=0.38),
        pbr("TealAccent", (0.03, 0.22, 0.26), 0.0, 0.35,
            emission=(0.10, 0.65, 0.72), strength=2.2),
    ]


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(obj, path, engine):
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
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # shaped warm key, faint cool fill, cool rim, warm wedge on the back wall
    # (docs/VISUAL-STYLE.md)
    light("Key", (-4.0, -5.0, 6.0), 600.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 110.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.5, 4.5, 5.0), 350.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 175))
    light("Wedge", (2.5, 3.5, 4.2), 480.0, 6.0, (1.0, 0.76, 0.5), (-72, 0, 195))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 52.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (5.8, -6.9, 2.2)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.45, 0.0, 1.5)
    scene.collection.objects.link(target)
    con = cam.constraints.new('TRACK_TO')
    con.target = target
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 32
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # AgX would wash the hazard orange and teal accent toward pastel
    # (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj, part_of = build_arm()
    for m in make_materials():
        obj.data.materials.append(m)
    groups = assign_weights(obj, part_of)
    arm = build_rig(obj)
    bpy.context.view_layer.update()
    pose_before = eval_positions(obj)
    code = check(obj, arm, groups, pose_before)
    if code:
        return code

    if args.output:
        if not render_still(obj, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 10
        print(f"rendered still {args.output}")

    print("vertex-weight-limit OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
