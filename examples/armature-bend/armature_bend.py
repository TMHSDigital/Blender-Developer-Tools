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

``--zero-curl`` leaves every pose bone at rest and still asserts the tip
deflects. That is the falsifier (``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python armature_bend.py --                 # check only
    blender --background --python armature_bend.py -- --zero-curl      # must fail
    blender --background --python armature_bend.py -- --output b.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

# Shared Layer 1 framing measurement (render path only) — see
# gallery_framing.py for the __file__-relative import shim this relies on.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
import gallery_framing  # noqa: E402

BONES = 4
BONE_LEN = 1.0
HEIGHT = BONES * BONE_LEN
SIDES = 32
BLEND = 0.3                     # half-width of the weight blend zone at each joint
CURL_DEG = 34.0                 # per-joint bend for the full pose
LBS_TOL = 5e-4                  # float32 mesh coords vs double pose matrices
# one tint per bone so the render shows the weight bands the check asserts
PALETTE = [(0.02, 0.28, 0.38), (0.0, 0.55, 0.55), (0.95, 0.52, 0.12), (0.85, 0.16, 0.18)]

# The tube is a ribbed bellows hose between two brass collars, lathed from an
# (r, z, part) profile: part 0 is brass, part 1 the ribbed hose. Every weight
# is still a function of z alone, so the closed-form LBS check is unchanged;
# the ribs just make the deformation legible (they fan open on the outside of
# each bend and crowd together on the inside).
HOSE_Z0, HOSE_Z1 = 0.44, 3.58   # ribbed section; the collars sit inside bone 0 / bone 3
HOSE_R0, HOSE_R1 = 0.31, 0.19   # hose valley radius, root -> tip
RIB_AMP = 0.045                 # crest height above the valley
RIB_PERIOD = 0.13
RIB_SAMPLES = 8                 # profile rings per rib


def hose_profile():
    """(r, z, part, crest) rings bottom to top; crest in [0, 1] (1 on a rib crest)."""
    prof = [(0.45, 0.00, 0, 0.0), (0.47, 0.02, 0, 0.0), (0.47, 0.15, 0, 0.0),
            (0.45, 0.17, 0, 0.0), (0.39, 0.17, 0, 0.0), (0.39, 0.29, 0, 0.0),
            (0.41, 0.31, 0, 0.0), (0.41, 0.40, 0, 0.0), (0.38, 0.42, 0, 0.0),
            (HOSE_R0, HOSE_Z0, 1, 0.0)]
    ribs = max(1, round((HOSE_Z1 - HOSE_Z0) / RIB_PERIOD))
    n = ribs * RIB_SAMPLES
    for k in range(1, n + 1):
        f = k / n
        z = HOSE_Z0 + (HOSE_Z1 - HOSE_Z0) * f
        crest = abs(math.sin(math.pi * ribs * f)) ** 0.6   # rounded crests, pinched valleys
        r = HOSE_R0 + (HOSE_R1 - HOSE_R0) * f + RIB_AMP * crest
        prof.append((r, z, 1, crest))
    prof += [(0.24, 3.61, 0, 0.0), (0.27, 3.63, 0, 0.0), (0.27, 3.80, 0, 0.0),
             (0.25, 3.82, 0, 0.0), (0.20, 3.82, 0, 0.0), (0.20, 3.97, 0, 0.0),
             (0.18, HEIGHT, 0, 0.0)]
    return prof


PROFILE = hose_profile()
RINGS = len(PROFILE)            # vertex rings along the tube, tip cap included

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
        for r, z, _part, _crest in PROFILE:
            rings.append([bm.verts.new((r * math.cos(a), r * math.sin(a), z))
                          for a in (2 * math.pi * s / SIDES for s in range(SIDES))])
        for k in range(RINGS - 1):
            # a band is brass only when both of its rings are brass
            part = 1 if (PROFILE[k][2] or PROFILE[k + 1][2]) else 0
            for s in range(SIDES):
                f = bm.faces.new((rings[k][s], rings[k][(s + 1) % SIDES],
                                  rings[k + 1][(s + 1) % SIDES], rings[k + 1][s]))
                f.material_index = part
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    for poly in me.polygons:
        poly.use_smooth = True
    # collars keep crisp machined steps; the rubber ribs stay smooth
    me.set_sharp_from_angle(angle=math.radians(50.0))
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
    # rib crests catch the bone tint, valleys fall to dark rubber (render only)
    crest = tube.data.attributes.new("Crest", 'FLOAT', 'POINT')
    crest.data.foreach_set("value", [PROFILE[i // SIDES][3]
                                     for i in range(len(tube.data.vertices))])

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

    def principled(name, base, rough, metal=0.0, noise=None):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*base, 1.0)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        if noise:
            # machining/handling wear: a noise-mottled roughness, never a flat slot
            nt = m.node_tree
            tex = nt.nodes.new("ShaderNodeTexNoise")
            tex.inputs["Scale"].default_value = noise
            tex.inputs["Detail"].default_value = 6.0
            mr = nt.nodes.new("ShaderNodeMapRange")
            mr.inputs["To Min"].default_value = rough - 0.08
            mr.inputs["To Max"].default_value = rough + 0.14
            nt.links.new(tex.outputs["Fac"], mr.inputs["Value"])
            nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
        return m

    brass = principled("Brass", (0.80, 0.56, 0.24), 0.26, metal=1.0, noise=28.0)
    steel = principled("Steel", (0.20, 0.205, 0.22), 0.34, metal=0.9, noise=18.0)

    # the hose: bone tint on the rib crests, dark rubber down in the valleys,
    # so the weight bands the LBS check asserts still read as colour
    hose = bpy.data.materials.new("WeightBands")
    hose.use_nodes = True
    nt = hose.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tint = nt.nodes.new("ShaderNodeAttribute")
    tint.attribute_name = "BoneTint"
    crest = nt.nodes.new("ShaderNodeAttribute")
    crest.attribute_name = "Crest"
    fac = nt.nodes.new("ShaderNodeMapRange")
    fac.inputs["To Min"].default_value = 0.10
    nt.links.new(crest.outputs["Fac"], fac.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.inputs[6].default_value = (0.012, 0.012, 0.014, 1.0)     # A: valley rubber
    nt.links.new(fac.outputs["Result"], mix.inputs[0])
    nt.links.new(tint.outputs["Color"], mix.inputs[7])           # B: bone tint
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.46
    bsdf.inputs["Specular IOR Level"].default_value = 0.3

    # a machined steel foot flange per hose, six brass bolt heads on its rim
    def flange(x):
        me = bpy.data.meshes.new("Flange")
        bm = bmesh.new()
        try:
            prof = [(0.0, 0.0), (0.74, 0.0), (0.78, 0.03), (0.78, 0.09), (0.74, 0.12),
                    (0.50, 0.12), (0.48, 0.15), (0.0, 0.15)]
            rings = []
            for r, z in prof:
                if r == 0.0:
                    rings.append([bm.verts.new((0.0, 0.0, z))])
                else:
                    rings.append([bm.verts.new((r * math.cos(2 * math.pi * s / 48),
                                                r * math.sin(2 * math.pi * s / 48), z))
                                  for s in range(48)])
            for a, b in zip(rings, rings[1:]):
                for s in range(48):
                    t = (s + 1) % 48
                    if len(a) == 1:
                        f = bm.faces.new((a[0], b[t], b[s]))
                    elif len(b) == 1:
                        f = bm.faces.new((a[s], a[t], b[0]))
                    else:
                        f = bm.faces.new((a[s], a[t], b[t], b[s]))
                    f.smooth = True
            for k in range(6):
                ang = 2 * math.pi * (k + 0.5) / 6
                res = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.055,
                                            radius2=0.055, depth=0.05)
                for v in res["verts"]:
                    v.co += Vector((0.62 * math.cos(ang), 0.62 * math.sin(ang), 0.145))
                for f in {f for v in res["verts"] for f in v.link_faces}:
                    f.material_index = 1
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
        finally:
            bm.free()
        me.set_sharp_from_angle(angle=math.radians(40.0))
        me.materials.append(steel)
        me.materials.append(brass)
        ob = bpy.data.objects.new("Flange", me)
        ob.location = (x, 0.0, 0.0)
        scene.collection.objects.link(ob)
        return ob

    # rest -> half curl -> full curl, left to right; the rigs are rotated so
    # the curl sweeps across the picture plane instead of away from camera.
    # Each rig stands on its flange (lifted by the flange's 0.15 height).
    tubes, flanges = [], []
    for (tube, arm), x in zip(rigs, (-3.1, -0.6, 2.4)):
        for ob in (tube, arm):
            ob.location = (x, 0.0, 0.15)
            ob.rotation_euler.z = math.radians(90.0)
        tube.data.materials.append(brass)       # material index 0: collars
        tube.data.materials.append(hose)        # material index 1: ribbed hose
        tubes.append(tube)
        flanges.append(flange(x))

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

    # a shaped warm key from the upper left, a faint cool fill so the shadow
    # side of each tube stays legible, a cool rim to lift the silhouettes off
    # the backdrop, and a warm wedge raking the back wall — the falloff pool
    # behind the subjects that the rest of the gallery stages against.
    light("Key", (-4.0, -5.0, 6.0), 480.0, 3.5, (1.0, 0.95, 0.88), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 70.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.5, 3.0, 5.5), 160.0, 3.0, (0.6, 0.78, 1.0), (-40, 0, 180))
    light("Wedge", (3.0, 5.0, 4.0), 760.0, 6.0, (1.0, 0.70, 0.42), (-68, 0, 192))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 45.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (-0.2, -11.6, 2.75)
    cam.rotation_euler = (math.radians(86), 0.0, 0.0)
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
    # AgX (the 4.x/5.x default) desaturates the BoneTint bands toward pastel,
    # hiding exactly the weight boundaries the LBS check asserts.
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()
    # Layer 1 framing gate before the beauty render (exit 10 on violation)
    fcode = gallery_framing.check_framing(scene, cam, hero=tubes,
                                          elements=tubes + flanges, stage=[floor, wall])
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    return 0 if os.path.exists(path) and os.path.getsize(path) > 0 else 9


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--zero-curl", action="store_true",
                   help="leave pose bones at rest (must fail)")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    curl = 0.0 if args.zero_curl else CURL_DEG
    tube, arm = build_rig(curl)
    code = check(tube, arm)
    if code:
        return code

    if args.output:
        rigs = [build_rig(0.0), build_rig(CURL_DEG / 2), (tube, arm)]
        rcode = render_still(rigs, os.path.abspath(args.output), args.engine)
        if rcode:
            if rcode == 9:
                print("ERROR: render produced no file", file=sys.stderr)
            return rcode
        print(f"rendered still {args.output}")

    print("armature-bend OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
