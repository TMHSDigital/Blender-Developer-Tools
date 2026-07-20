"""A rigged mech scorpion round-tripped through glTF skins — a runnable example.

Witnesses the skinned-mesh export contract that gltf-export-roundtrip left
uncovered: bones, hierarchy, weights, and deformation must all survive the
format. (Pipeline arc: modeling/LOD in lod-decimate-chain, weighting in
vertex-weight-limit, export in gltf-export-roundtrip; the tangent frames
those maps need are in triangulate-tangents.)

1. The skeleton round-trips. ``skins[0].joints`` names every bone in order,
   and the re-imported armature carries the same bones, parent chain, and
   rest matrices within tolerance — the +Y-up conversion applies to bone
   nodes the same way it applies to meshes.
2. The weights round-trip. JOINTS_0/WEIGHTS_0 exist per primitive, per-vertex
   weights on disk sum to 1, and the re-imported vertex groups match the
   authored groups weight-for-weight within float tolerances (compared as
   sorted point sets, the same protocol as gltf-export-roundtrip).
3. The deformation round-trips. Posed identically, the re-imported rig's
   evaluated mesh matches the original's — linear blend skinning through
   the file format.
4. The mesh must be parented to the armature. The exporter warns "Armature
   must be the parent of skinned mesh" and picks an armature by name
   otherwise — with more than one rig in the file it can bind the wrong one.

The skins pipeline is stable between Blender 4.5 LTS and 5.1 (exporter RNA
is byte-identical, verified on both) — the example runs identically on both.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python gltf_skin_roundtrip.py --                 # check only
    blender --background --python gltf_skin_roundtrip.py -- --output s.png  # + render
"""
import bpy, bmesh, sys, os, math, json, struct, shutil, tempfile, argparse
import mathutils

GUNMETAL, ORANGE, RUBBER, GLOW = 0, 1, 2, 3
BONES = ("Root", "Thorax", "Abdomen", "Tail_1", "Tail_2", "Tail_3", "Stinger")
SPANS = {"Root": (0.0, 0.35), "Thorax": (0.35, 0.85), "Abdomen": (0.85, 1.25),
         "Tail_1": (1.25, 1.60), "Tail_2": (1.60, 1.90), "Tail_3": (1.90, 2.15),
         "Stinger": (2.15, 2.30)}
# tail curl: progressive pitch per joint; the pose is the deformation witness
POSE_DEG = {"Tail_1": -28.0, "Tail_2": -34.0, "Tail_3": -40.0, "Stinger": 25.0}
BLEND = 0.06                    # joint blend half-width (two bones per seam)
POS_TOL = 2e-5                  # float32 on disk vs float32 in Blender
NRM_TOL = 2e-4
W_TOL = 3e-4                    # weight round-trip tolerance
SUM_TOL = 3e-4                  # disk weight-sum tolerance
REST_TOL = 1e-5                 # rest-matrix round-trip tolerance
LBS_TOL = 5e-4
KEY_DIGITS = 4

EXPORT_KWARGS = dict(
    export_format='GLTF_SEPARATE',
    export_skins=True,
    export_yup=True,
    export_animations=False,
    export_image_format='NONE',
)


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


def lathe_part(bm, rings, mat, part_of, bone, sides=16):
    """Revolve (z, r) rings; tags `bone` for its verts."""
    n0f, n0v = len(bm.faces), len(bm.verts)
    out = []
    for z, r in rings:
        out.append([bm.verts.new((r * math.cos(2 * math.pi * s / sides),
                                  r * math.sin(2 * math.pi * s / sides), z))
                    for s in range(sides)])
    for k in range(len(out) - 1):
        for s in range(sides):
            f = bm.faces.new((out[k][s], out[k][(s + 1) % sides],
                              out[k + 1][(s + 1) % sides], out[k + 1][s]))
            f.material_index = mat
    part_of.extend([bone] * (len(bm.verts) - n0v))


def build_scorpion():
    """The mech scorpion: base plate, six rigid legs, thorax with claws,
    abdomen, three tail segments, and a stinger — every part closed form,
    every vertex tagged to its bone (or a two-bone blend ring at a seam)."""
    me = bpy.data.meshes.new("Scorpion")
    part_of = []
    bm = bmesh.new()
    try:
        # base plate (Root)
        box_part(bm, (0.9, 0.7, 0.10), (0.0, 0.0, 0.05), (0, 0, 0),
                 GUNMETAL, part_of, "Root")
        # thorax shell + head with eyes (Thorax)
        box_part(bm, (0.70, 0.55, 0.42), (0.0, -0.05, 0.60), (0, 0, 0),
                 ORANGE, part_of, "Thorax")
        box_part(bm, (0.40, 0.30, 0.22), (0.0, -0.38, 0.66), (8, 0, 0),
                 ORANGE, part_of, "Thorax")
        for sx in (-1, 1):  # glowing eyes
            box_part(bm, (0.06, 0.03, 0.06), (sx * 0.10, -0.545, 0.70),
                     (0, 0, 0), GLOW, part_of, "Thorax")
        # six legs in two rows, angled down (rigid to Thorax)
        for sx in (-1, 1):
            for k, z in ((0, 0.72), (1, 0.60), (2, 0.48)):
                box_part(bm, (0.34, 0.09, 0.07), (sx * 0.50, -0.02 + k * 0.16, z),
                         (0, 0, sx * 18), GUNMETAL, part_of, "Thorax")
                box_part(bm, (0.30, 0.06, 0.05), (sx * 0.76, -0.02 + k * 0.16, z - 0.13),
                         (0, 0, sx * 40), GUNMETAL, part_of, "Thorax")
        # claws: shoulder + forearm + pincer pair (rigid to Thorax)
        for sx in (-1, 1):
            box_part(bm, (0.18, 0.40, 0.18), (sx * 0.26, -0.58, 0.60),
                     (-15, 0, 0), GUNMETAL, part_of, "Thorax")
            box_part(bm, (0.16, 0.34, 0.16), (sx * 0.26, -0.85, 0.52),
                     (20, 0, 0), GUNMETAL, part_of, "Thorax")
            for dy in (-1, 1):
                box_part(bm, (0.07, 0.22, 0.12),
                         (sx * 0.26, -1.02, 0.52 + dy * 0.08), (0, 0, 0),
                         GUNMETAL, part_of, "Thorax")
        # abdomen: two tapering plates (Abdomen)
        box_part(bm, (0.56, 0.46, 0.30), (0.0, 0.12, 1.00), (4, 0, 0),
                 ORANGE, part_of, "Abdomen")
        box_part(bm, (0.44, 0.36, 0.26), (0.0, 0.16, 1.24), (6, 0, 0),
                 ORANGE, part_of, "Abdomen")
        # tail segments, lathed and tapering (their own bones)
        lathe_part(bm, [(1.25, 0.16), (1.42, 0.15), (1.60, 0.13)],
                   GUNMETAL, part_of, "Tail_1")
        lathe_part(bm, [(1.60, 0.13), (1.75, 0.115), (1.90, 0.10)],
                   GUNMETAL, part_of, "Tail_2")
        lathe_part(bm, [(1.90, 0.10), (2.02, 0.085), (2.15, 0.07)],
                   GUNMETAL, part_of, "Tail_3")
        # stinger: cone + barb with the glow tip (Stinger)
        lathe_part(bm, [(2.15, 0.07), (2.26, 0.045), (2.34, 0.012)],
                   GUNMETAL, part_of, "Stinger")
        lathe_part(bm, [(2.30, 0.030), (2.36, 0.030)], GLOW, part_of, "Stinger")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()  # the ownership contract, as always
    for poly in me.polygons:
        poly.use_smooth = False  # flat facets: one disk vertex per loop
    obj = bpy.data.objects.new("Scorpion", me)
    bpy.context.collection.objects.link(obj)
    return obj, part_of


def bone_of(z, bone):
    """Two-bone smooth blend across each joint seam; hard weight elsewhere."""
    order = list(SPANS)
    i = order.index(bone)
    if i == 0:
        return None
    prev = order[i - 1]
    seam = SPANS[bone][0]
    if abs(z - seam) <= BLEND:
        return prev
    return None


def assign_weights(obj, part_of):
    """Hard weights per part plus 50/50 blend rings at each bone seam."""
    groups = {b: obj.vertex_groups.new(name=b) for b in BONES}
    for idx, v in enumerate(obj.data.vertices):
        bone = part_of[idx]
        prev = bone_of(v.co.z, bone)
        if prev is not None:
            t = (v.co.z - (SPANS[bone][0] - BLEND)) / (2 * BLEND)
            groups[prev].add([idx], 1.0 - t, 'REPLACE')
            groups[bone].add([idx], t, 'REPLACE')
        else:
            groups[bone].add([idx], 1.0, 'REPLACE')
    return groups


def build_rig(obj):
    arm_data = bpy.data.armatures.new("ScorpRig")
    arm = bpy.data.objects.new("ScorpRig", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    prev = None
    for name in BONES:
        eb = arm_data.edit_bones.new(name)
        z0, z1 = SPANS[name]
        eb.head = (0.0, 0.0, z0)
        eb.tail = (0.0, 0.0, z1)
        if prev is not None:
            eb.parent = prev
            eb.use_connect = True
        prev = eb
    bpy.ops.object.mode_set(mode='OBJECT')
    # the exporter warns and picks by name otherwise — with two rigs in the
    # file it can bind the WRONG one; parent explicitly
    obj.parent = arm
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
    deps = bpy.context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(deps)
    me = ob_eval.to_mesh()
    try:
        return [tuple(v.co) for v in me.vertices]
    finally:
        ob_eval.to_mesh_clear()


def key_of(p):
    return tuple(round(c, KEY_DIGITS) for c in p)


def read_gltf(path):
    g = json.load(open(path))
    blob = open(os.path.join(os.path.dirname(path),
                             g["buffers"][0]["uri"]), "rb").read()

    def accessor_floats(idx, ncomp):
        acc = g["accessors"][idx]
        bv = g["bufferViews"][acc["bufferView"]]
        off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = bv.get("byteStride", 4 * ncomp)
        return [struct.unpack_from(f"<{ncomp}f", blob, off + stride * i)
                for i in range(acc["count"])]

    def accessor_uints(idx, ncomp, ctype):
        acc = g["accessors"][idx]
        bv = g["bufferViews"][acc["bufferView"]]
        off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = bv.get("byteStride", {5121: 1, 5123: 2, 5125: 4}[ctype] * ncomp)
        fmt = {5121: "B", 5123: "H", 5125: "I"}[ctype]
        return [struct.unpack_from(f"<{ncomp}{fmt}", blob, off + stride * i)
                for i in range(acc["count"])]

    return g, accessor_floats, accessor_uints


def check(obj, arm, part_of):
    me = obj.data
    exp_props = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    missing = [k for k in EXPORT_KWARGS if k not in exp_props]
    if missing:
        print(f"ERROR: exporter RNA drifted, missing {missing}", file=sys.stderr)
        return 3

    base_verts = len(me.vertices)
    ngroups = len(obj.vertex_groups)
    if ngroups != len(BONES):
        print(f"ERROR: {ngroups} vertex groups != {len(BONES)} bones", file=sys.stderr)
        return 4

    deps = bpy.context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(deps)
    me_eval = ob_eval.to_mesh()
    try:
        eval_loops = len(me_eval.loops)
        pose_orig = [tuple(v.co) for v in me_eval.vertices]
    finally:
        ob_eval.to_mesh_clear()

    rest_orig = [tuple(v.co) for v in me.vertices]
    # snapshot everything the export/import wipe would free: the original
    # datablocks DIE at read_factory_settings (the crate's freed-mesh hazard)
    bone_info = {name: (arm.data.bones[name].parent.name
                        if arm.data.bones[name].parent else None,
                        tuple(tuple(arm.data.bones[name].matrix_local[r][c]
                                    for c in range(4)) for r in range(4)))
                 for name in BONES}

    def weight_map(o):
        names = [g.name for g in o.vertex_groups]
        return {key_of(v.co): tuple(sorted(
            (names[g.group], round(g.weight, 5)) for g in v.groups))
            for v in o.data.vertices}

    want_w = weight_map(obj)

    tmp = tempfile.mkdtemp(prefix="gltf_skin_")
    try:
        path = os.path.join(tmp, "scorp.gltf").replace("\\", "/")
        bpy.ops.export_scene.gltf(filepath=path, **EXPORT_KWARGS)

        # contract 1 (on disk): the skin carries every bone, joints named
        g, acc_f, acc_u = read_gltf(path)
        skins = g.get("skins", [])
        if len(skins) != 1:
            print(f"ERROR: {len(skins)} skins on disk, expected 1", file=sys.stderr)
            return 5
        joints = skins[0]["joints"]
        node_names = [g["nodes"][j].get("name", "") for j in joints]
        if len(joints) != len(BONES) or sorted(node_names) != sorted(BONES):
            print(f"ERROR: skin joints {node_names} != bones {sorted(BONES)}",
                  file=sys.stderr)
            return 6
        prim = g["meshes"][0]["primitives"]
        if not all("JOINTS_0" in p["attributes"] and "WEIGHTS_0" in p["attributes"]
                   for p in prim):
            print("ERROR: primitives lack JOINTS_0/WEIGHTS_0", file=sys.stderr)
            return 7
        # contract 2a (on disk): per-vertex weights sum to 1
        disk_verts = 0
        sum_err = 0.0
        for p in prim:
            a = p["attributes"]
            w = acc_f(a["WEIGHTS_0"], 4)
            j = acc_u(a["JOINTS_0"], 4, g["accessors"][a["JOINTS_0"]]["componentType"])
            disk_verts += len(w)
            for ws, js in zip(w, j):
                total = sum(x for x, ji in zip(ws, js) if ji < len(BONES))
                sum_err = max(sum_err, abs(total - 1.0) if total > 1e-9 else 0.0)
        if sum_err > SUM_TOL:
            print(f"ERROR: disk weight sums deviate {sum_err:.3e} from 1.0",
                  file=sys.stderr)
            return 8
        if disk_verts > eval_loops:
            print(f"ERROR: disk verts {disk_verts} exceed evaluated loops "
                  f"{eval_loops} — the exporter invented vertices",
                  file=sys.stderr)
            return 9

        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # contract 1b: the skeleton round-trips
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    if len(arms) != 1:
        print(f"ERROR: {len(arms)} armatures after import, expected 1",
              file=sys.stderr)
        return 10
    ri_arm = arms[0]
    if len(ri_arm.data.bones) != len(BONES):
        print(f"ERROR: {len(ri_arm.data.bones)} bones != {len(BONES)}",
              file=sys.stderr)
        return 11
    rest_err = 0.0
    for name in BONES:
        b1 = ri_arm.data.bones.get(name)
        if b1 is None:
            print(f"ERROR: bone {name} lost in round-trip", file=sys.stderr)
            return 12
        p0, m0 = bone_info[name]
        p1 = b1.parent.name if b1.parent else None
        if p0 != p1:
            print(f"ERROR: {name} parent {p1} != {p0}", file=sys.stderr)
            return 13
        rest_err = max(rest_err,
                       max(abs(m0[r][c] - b1.matrix_local[r][c])
                           for r in range(4) for c in range(4)))
    if rest_err > REST_TOL:
        print(f"ERROR: rest matrices deviate {rest_err:.3e} on round-trip",
              file=sys.stderr)
        return 14

    # contract 2b: the weights round-trip (sorted point sets, crate protocol)
    ri = [o for o in bpy.data.objects
          if o.type == 'MESH' and o.vertex_groups and o.find_armature()]
    if len(ri) != 1:
        print(f"ERROR: {len(ri)} skinned meshes after import, expected 1",
              file=sys.stderr)
        return 15
    ri = ri[0]
    rme = ri.data
    if len(rme.vertices) != disk_verts:
        print(f"ERROR: re-import has {len(rme.vertices)} verts, expected the "
              f"{disk_verts} on disk (the import must be 1:1 with the file)",
              file=sys.stderr)
        return 16
    if sorted(g.name for g in ri.vertex_groups) != sorted(BONES):
        print("ERROR: vertex group names drifted", file=sys.stderr)
        return 17

    # per-vertex weight vectors, compared at sorted positions
    names_ri = [g.name for g in ri.vertex_groups]
    got_w = {key_of(v.co): tuple(sorted(
        (names_ri[g.group], round(g.weight, 5)) for g in v.groups))
        for v in rme.vertices}
    w_err = 0.0
    step = 10 ** -KEY_DIGITS
    for p, want in want_w.items():
        got = None
        for dx in (-step, 0.0, step):
            for dy in (-step, 0.0, step):
                for dz in (-step, 0.0, step):
                    k = (p[0] + dx, p[1] + dy, p[2] + dz)
                    if k in got_w:
                        got = got_w[k]
                        break
        if got != want:
            w_err = max(w_err, 1.0 if got is None else
                        max(abs(dict(want).get(n, 0.0) - dict(got).get(n, 0.0))
                            for n in set(dict(want)) | set(dict(got))))
    if w_err > W_TOL:
        print(f"ERROR: weight round-trip deviates {w_err:.3e} (tol {W_TOL})",
              file=sys.stderr)
        return 18

    # contract 3: the deformation round-trips (pose the re-imported rig the
    # same way, compare posed positions BY REST-KEY — sorted multisets
    # misalign because the exporter welds duplicate loops)
    for name, deg in POSE_DEG.items():
        pb = ri_arm.pose.bones[name]
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler.x = math.radians(deg)
    bpy.context.view_layer.update()
    pose_ri = eval_positions(ri)
    orig_map = {}
    for r, p in zip(rest_orig, pose_orig):
        orig_map.setdefault(key_of(r), []).append(p)
    step = 10 ** -KEY_DIGITS
    pos_err = 0.0
    for j, rv in enumerate(rme.vertices):
        k0 = key_of(rv.co)
        cands = []
        for dx in (-step, 0.0, step):
            for dy in (-step, 0.0, step):
                for dz in (-step, 0.0, step):
                    cands += orig_map.get((k0[0] + dx, k0[1] + dy, k0[2] + dz), [])
        best = min((max(abs(pose_ri[j][c] - p[c]) for c in range(3))
                    for p in cands), default=1e30)
        pos_err = max(pos_err, best)
    if pos_err > POS_TOL:
        print(f"ERROR: deformation round-trip deviates {pos_err:.3e} "
              f"(tol {POS_TOL})", file=sys.stderr)
        return 19

    print(f"bones={len(BONES)} verts={base_verts} eval_loops={eval_loops} "
          f"disk_verts={disk_verts} (welded {eval_loops - disk_verts}) "
          f"sum_err={sum_err:.2e}")
    print(f"rest_err={rest_err:.2e} w_err={w_err:.2e} (tol {W_TOL}) "
          f"pos_err={pos_err:.2e} (tol {POS_TOL})")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


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
        pbr("HazardOrange", (0.80, 0.28, 0.07), 0.10, 0.45),
        pbr("FlexRubber", (0.05, 0.05, 0.06), 0.0, 0.85),
        pbr("TealGlow", (0.03, 0.22, 0.26), 0.0, 0.35,
            emission=(0.10, 0.70, 0.78), strength=2.5),
    ]


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
    light("Key", (-4.0, -5.0, 6.0), 560.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -38))
    light("Fill", (5.0, -4.0, 3.0), 100.0, 9.0, (0.75, 0.85, 1.0), (62, 0, 50))
    light("Rim", (0.5, 4.5, 5.0), 340.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 175))
    light("Wedge", (2.5, 3.5, 4.2), 460.0, 6.0, (1.0, 0.76, 0.5), (-72, 0, 195))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 52.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (1.5, -6.6, 2.7)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.0, 0.0, 0.8)
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
    # AgX would wash the hazard orange and teal glow (docs/VISUAL-STYLE.md)
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
    obj, part_of = build_scorpion()
    for m in make_materials():
        obj.data.materials.append(m)
    assign_weights(obj, part_of)
    arm = build_rig(obj)
    bpy.context.view_layer.update()
    code = check(obj, arm, part_of)
    if code:
        return code

    if args.output:
        # the re-imported rig is still in the file after the check; rebuild
        # the authored pair beside it for the still
        roundtrip_mesh = [o for o in bpy.data.objects
                          if o.type == 'MESH' and o.vertex_groups][0]
        roundtrip_arm = [o for o in bpy.data.objects if o.type == 'ARMATURE'][0]
        authored, part_of2 = build_scorpion()
        for m in make_materials():
            authored.data.materials.append(m)
        assign_weights(authored, part_of2)
        authored_arm = build_rig(authored)
        # move the ARMATURES; the skinned meshes follow as children
        authored_arm.location.x = -1.1
        roundtrip_arm.location.x = 1.1
        if not render_still(authored, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 20
        print(f"rendered still {args.output}")

    print("gltf-skin-roundtrip OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
