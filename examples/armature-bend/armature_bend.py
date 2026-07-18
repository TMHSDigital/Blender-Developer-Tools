"""An armature bending a weighted tube, checked against closed-form skinning.

Witnesses the three contracts AI-generated rigging code most often gets wrong:

1. `edit_bones` only exists in edit mode. Outside `mode_set(mode='EDIT')` the
   collection is empty — reads silently return nothing, writes are lost. The
   check asserts it is empty in object mode and holds the full chain in edit
   mode, with heads/tails at their closed-form positions.
2. Vertex groups bind by *name*. The armature modifier matches group names to
   bone names; a typo deforms nothing without erroring. Here every group name
   is the bone name and the deform proves the binding.
3. The armature modifier is exactly linear blend skinning. For every vertex,
   evaluated_position == sum_i( w_i * (pose_bone_i.matrix @
   bone_i.matrix_local.inverted()) @ rest_position ). The check re-implements
   LBS from the pose matrices and compares all vertices of the
   depsgraph-evaluated mesh against it. A straight (undeformed) tube is a
   failure: the tip must deflect while the root ring stays fixed.

The same API works unchanged on Blender 4.5 LTS and 5.1 — no version gate is
needed, which this example demonstrates by running identically on both.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python armature_bend.py --                 # check only
    blender --background --python armature_bend.py -- --output b.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

BONES = 4
BONE_LEN = 1.0
HEIGHT = BONES * BONE_LEN
SIDES = 24
RINGS = 41                      # vertex rings along the tube, tip cap included
R_BASE = 0.34
R_TIP = 0.16
BLEND = 0.3                     # half-width of the weight blend zone at each joint
CURL_DEG = 34.0                 # per-joint bend for the full pose
LBS_TOL = 5e-4                  # float32 mesh coords vs double pose matrices
# one tint per bone so the render shows the weight bands the check asserts
PALETTE = [(0.02, 0.28, 0.38), (0.0, 0.55, 0.55), (0.95, 0.52, 0.12), (0.85, 0.16, 0.18)]

BONE_NAMES = [f"Seg_{i}" for i in range(BONES)]


def bone_weights(t):
    """Normalized per-bone weights at parametric height t in [0, BONES]."""
    for j in range(1, BONES):                       # smoothstep across each joint
        if abs(t - j) <= BLEND:
            a = (t - (j - BLEND)) / (2 * BLEND)
            s = a * a * (3.0 - 2.0 * a)
            w = [0.0] * BONES
            w[j - 1], w[j] = 1.0 - s, s
            return w
    w = [0.0] * BONES
    w[min(BONES - 1, int(t))] = 1.0
    return w


def build_tube():
    me = bpy.data.meshes.new("Tube")
    bm = bmesh.new()
    try:
        rings = []
        for k in range(RINGS):
            f = k / (RINGS - 1)
            z, r = HEIGHT * f, R_BASE + (R_TIP - R_BASE) * f
            rings.append([bm.verts.new((r * math.cos(a), r * math.sin(a), z))
                          for a in (2 * math.pi * s / SIDES for s in range(SIDES))])
        for k in range(RINGS - 1):
            for s in range(SIDES):
                bm.faces.new((rings[k][s], rings[k][(s + 1) % SIDES],
                              rings[k + 1][(s + 1) % SIDES], rings[k + 1][s]))
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new("Tube", me)
    bpy.context.collection.objects.link(obj)
    return obj


def build_rig(curl_deg):
    """A weighted tube plus a posed 4-bone chain, both at the origin."""
    tube = build_tube()

    # vertex groups named after the bones — the name IS the binding
    groups = [tube.vertex_groups.new(name=n) for n in BONE_NAMES]
    for idx, v in enumerate(tube.data.vertices):
        for i, wi in enumerate(bone_weights(v.co.z / BONE_LEN)):
            if wi > 0.0:
                groups[i].add([idx], wi, 'REPLACE')

    # create the color attribute only AFTER all group writes: the first
    # VertexGroup.add() allocates the deform layer, which reallocates the
    # mesh's CustomData and dangles any attribute reference held across it
    # (crashes 4.5 LTS; 5.1 merely survives by luck)
    col = tube.data.color_attributes.new("BoneTint", 'FLOAT_COLOR', 'POINT')
    for idx, v in enumerate(tube.data.vertices):
        w = bone_weights(v.co.z / BONE_LEN)
        rgb = [sum(w[i] * PALETTE[i][c] for i in range(BONES)) for c in range(3)]
        col.data[idx].color = (*rgb, 1.0)

    arm_data = bpy.data.armatures.new("Chain")
    arm = bpy.data.objects.new("Chain", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm

    # edit_bones is only populated between these two mode_set calls
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for i, name in enumerate(BONE_NAMES):
        eb = arm_data.edit_bones.new(name)
        eb.head = (0.0, 0.0, i * BONE_LEN)
        eb.tail = (0.0, 0.0, (i + 1) * BONE_LEN)
        if prev is not None:
            eb.parent = prev
            eb.use_connect = True
        prev = eb
    bpy.ops.object.mode_set(mode='OBJECT')

    mod = tube.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    mod.use_vertex_groups = True
    mod.use_bone_envelopes = False

    for name in BONE_NAMES[1:]:                     # root stays upright
        pb = arm.pose.bones[name]
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler.x = -math.radians(curl_deg)
    return tube, arm


def check(tube, arm):
    # contract 1: edit_bones is empty outside edit mode, full inside
    if len(arm.data.edit_bones) != 0:
        print("ERROR: edit_bones populated in object mode", file=sys.stderr)
        return 3
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = arm.data.edit_bones
    ok = len(ebs) == BONES and all(
        (ebs[n].head - ebs[n].tail).length > 0 and
        abs(ebs[n].head.z - i * BONE_LEN) < 1e-6 and
        abs(ebs[n].tail.z - (i + 1) * BONE_LEN) < 1e-6
        for i, n in enumerate(BONE_NAMES))
    bpy.ops.object.mode_set(mode='OBJECT')
    if not ok:
        print("ERROR: edit-mode bone chain does not match its closed form", file=sys.stderr)
        return 4

    deps = bpy.context.evaluated_depsgraph_get()
    ob_eval = tube.evaluated_get(deps)
    me_eval = ob_eval.to_mesh()
    try:
        # contract 3: the armature modifier is exactly linear blend skinning
        mats = [arm.pose.bones[n].matrix @ arm.data.bones[n].matrix_local.inverted()
                for n in BONE_NAMES]
        rest = tube.data.vertices
        if len(me_eval.vertices) != len(rest):
            print("ERROR: evaluated mesh vertex count changed", file=sys.stderr)
            return 5
        worst = 0.0
        for idx, v in enumerate(rest):
            w = bone_weights(v.co.z / BONE_LEN)
            predicted = sum((wi * (m @ v.co) for wi, m in zip(w, mats) if wi > 0.0),
                            start=v.co * 0.0)
            worst = max(worst, (me_eval.vertices[idx].co - predicted).length)
        if worst > LBS_TOL:
            print(f"ERROR: evaluated mesh deviates from closed-form LBS by {worst:.6f}",
                  file=sys.stderr)
            return 6

        # root ring pinned, tip deflected — a straight tube is a failure
        base_move = max((me_eval.vertices[i].co - rest[i].co).length
                        for i in range(SIDES))
        tip_move = (me_eval.vertices[len(rest) - 1].co - rest[len(rest) - 1].co).length
        if base_move > 1e-5:
            print(f"ERROR: root ring moved {base_move:.6f} (root bone is unposed)",
                  file=sys.stderr)
            return 7
        if tip_move < 0.8:
            print(f"ERROR: tip only moved {tip_move:.4f} — armature did not deform "
                  "the tube", file=sys.stderr)
            return 8
    finally:
        ob_eval.to_mesh_clear()

    print(f"bones={BONES} verts={len(tube.data.vertices)} lbs_max_err={worst:.2e} "
          f"tip_deflection={tip_move:.3f}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(rigs, path, engine):
    scene = bpy.context.scene

    mat = bpy.data.materials.new("WeightBands")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "BoneTint"
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.32

    # rest -> half curl -> full curl, left to right; the rigs are rotated so
    # the curl sweeps across the picture plane instead of away from camera
    for (tube, arm), x in zip(rigs, (-3.1, -0.6, 2.4)):
        for ob in (tube, arm):
            ob.location.x = x
            ob.rotation_euler.z = math.radians(90.0)
        tube.data.materials.append(mat)

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
    fb.inputs["Base Color"].default_value = (0.05, 0.055, 0.065, 1.0)
    fb.inputs["Roughness"].default_value = 0.55
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 9.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.03, 0.033, 0.04, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    light("Key", (-4.0, -5.0, 6.0), 1500.0, 7.0, (1.0, 0.97, 0.92), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 500.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.5, 4.5, 5.0), 900.0, 5.0, (0.55, 0.75, 1.0), (-55, 0, 175))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 45.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-0.3, -10.5, 2.4)
    cam.rotation_euler = (math.radians(87), 0.0, 0.0)
    scene.collection.objects.link(cam)
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
    tube, arm = build_rig(CURL_DEG)
    code = check(tube, arm)
    if code:
        return code

    if args.output:
        rigs = [build_rig(0.0), build_rig(CURL_DEG / 2), (tube, arm)]
        if not render_still(rigs, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 9
        print(f"rendered still {args.output}")

    print("armature-bend OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
