"""Relative shape-key blend via the data API — a runnable example.

Witnesses that shape keys are authored and driven on the mesh datablock
(`shape_key_add`, `key_blocks["Tall"].data`, `.value`), not through
operators, and that the depsgraph-evaluated mesh matches the closed-form
relative blend: co = basis + value * (key - basis). AI often keys the
wrong block, forgets Basis, or reads undeformed `mesh.vertices` instead of
the evaluated mesh.

The subject is a lathe-turned ceramic vase. Its Basis is a squat jar; the
Tall key lifts the rim (stretching the neck), flares the lip into a
trumpet, and slims the belly — a real morph, not a uniform scale. The
check pins the lift and the flare at the rim ring in closed form.

``--zero-blend`` sets Tall.value to 0 and still asserts the 0.5 closed form.
That is the falsifier (``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python shape_key_blend.py --                 # check only
    blender --background --python shape_key_blend.py -- --zero-blend    # must fail
    blender --background --python shape_key_blend.py -- --output s.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

SEGMENTS = 64      # lathe resolution around Z
H0 = 1.0           # Basis rim height (the lip's top ring)
R_LIP0 = 0.335     # Basis rim radius
WALL = 0.03        # ceramic wall thickness
LIFT = 1.5         # Tall key: rim rises by this much
FLARE = 0.38       # Tall key: rim radius grows by this much
SLIM = 0.28        # Tall key: belly narrows by up to this fraction
BLEND = 0.5
EXPECT_TOP_Z = H0 + BLEND * LIFT
EXPECT_BOT_Z = 0.0                      # the foot never moves
EXPECT_RIM_R = R_LIP0 + BLEND * FLARE   # radius of the rim ring

# Outer wall control points (radius, z) from the foot to the shoulder of the
# lip, Catmull-Rom interpolated. A squat, round-bellied jar.
_OUTER_CTRL = [(0.300, 0.080), (0.420, 0.160), (0.540, 0.270), (0.605, 0.370),
               (0.620, 0.450), (0.590, 0.540), (0.500, 0.640), (0.380, 0.720),
               (0.290, 0.790), (0.262, 0.850), (0.272, 0.910), (0.305, 0.955),
               (0.345, 0.985)]
BAND = (0.530, 0.600, 0.014)   # raised ochre band: z0, z1, relief
GHOST_RINGS = (0.22, 0.34, 0.45)  # Basis heights drawn as the ghost

# material slots
M_GLAZE, M_BISQUE, M_GILT, M_INNER = range(4)


def _smoothstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def _catmull(pts, per_span=8):
    out = []
    ext = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for s in range(per_span):
            t = s / per_span
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t
                                    + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3)
                             for k in range(2)))
    out.append(pts[-1])
    return out


def _radius_at(dense, z):
    for (r0, z0), (r1, z1) in zip(dense, dense[1:]):
        if z0 <= z <= z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return dense[-1][0] if z > dense[-1][1] else dense[0][0]


def vase_profile():
    """Closed lathe profile [(r, z, material)] from the underside pole, up the
    outer wall, over the lip, down the inner wall to the inner floor pole."""
    dense = _catmull(_OUTER_CTRL)
    prof = [(0.0, 0.0, M_BISQUE), (0.235, 0.0, M_BISQUE), (0.262, 0.008, M_BISQUE),
            (0.272, 0.030, M_BISQUE), (0.276, 0.060, M_BISQUE), (0.290, 0.075, M_GLAZE)]
    zs = [0.080 + i * 0.015 for i in range(int((0.970 - 0.080) / 0.015) + 1)]
    b0, b1, relief = BAND
    zs = sorted(set([z for z in zs if not (b0 - 0.012 < z < b1 + 0.012)]
                    + [b0 - 0.008, b0, b0 + 0.006, b1 - 0.006, b1, b1 + 0.008]))
    for z in zs:
        r = _radius_at(dense, z)
        mat = M_GLAZE
        if b0 <= z < b1:
            mat = M_GILT
        if b0 + 0.006 - 1e-9 <= z <= b1 - 0.006 + 1e-9:
            r += relief
        elif abs(z - b0) < 1e-9 or abs(z - b1) < 1e-9:
            r += relief * 0.55
        prof.append((r, z, mat))
    prof += [(0.345, 0.985, M_GLAZE), (R_LIP0, H0, M_INNER), (0.312, 0.990, M_INNER)]
    z = 0.975
    while z > 0.14:
        prof.append((_radius_at(dense, z) - WALL, z, M_INNER))
        z -= 0.018
    prof += [(_radius_at(dense, 0.135) - WALL - 0.03, 0.120, M_INNER), (0.0, 0.120, M_INNER)]
    return prof


def tall_offset(x, y, z):
    """The Tall key as a function of the Basis position: lift the neck, flare
    the lip, slim the belly. Zero at the foot; exactly (+FLARE, +LIFT) at the
    rim ring (u == 1)."""
    u = z / H0
    r = math.hypot(x, y)
    if r < 1e-9:
        return x, y, z + LIFT * _smoothstep(0.30, 1.0, u)
    w = 0.0
    if 0.08 < u < 0.75:
        w = math.sin(math.pi * (u - 0.08) / 0.67) ** 2
    nr = r * (1.0 - SLIM * w) + FLARE * _smoothstep(0.78, 1.0, u) ** 2
    return x / r * nr, y / r * nr, z + LIFT * _smoothstep(0.30, 1.0, u)


def build_vase_mesh(name):
    prof = vase_profile()
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        rings = []
        for r, z, _m in prof:
            if r == 0.0:
                rings.append([bm.verts.new((0.0, 0.0, z))])
            else:
                rings.append([bm.verts.new((r * math.cos(2 * math.pi * s / SEGMENTS),
                                            r * math.sin(2 * math.pi * s / SEGMENTS), z))
                              for s in range(SEGMENTS)])
        for i in range(len(rings) - 1):
            a, b, mat = rings[i], rings[i + 1], prof[i][2]
            for s in range(SEGMENTS):
                t = (s + 1) % SEGMENTS
                if len(a) == 1:
                    f = bm.faces.new((a[0], b[s], b[t]))
                elif len(b) == 1:
                    f = bm.faces.new((a[s], b[0], a[t]))
                else:
                    f = bm.faces.new((a[s], b[s], b[t], a[t]))
                f.material_index = mat
                f.smooth = True
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def build(zero_blend=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = build_vase_mesh("Vase")
    obj = bpy.data.objects.new("Vase", me)
    bpy.context.collection.objects.link(obj)

    # data-level shape keys — no bpy.ops.object.shape_key_*
    obj.shape_key_add(name="Basis")
    tall = obj.shape_key_add(name="Tall")
    n = len(me.vertices)
    co = [0.0] * (3 * n)
    tall.data.foreach_get("co", co)          # starts as a copy of Basis
    for i in range(n):
        co[3 * i:3 * i + 3] = tall_offset(*co[3 * i:3 * i + 3])
    tall.data.foreach_set("co", co)
    tall.value = 0.0 if zero_blend else BLEND
    return obj


def _coords(seq):
    flat = [0.0] * (3 * len(seq))
    seq.foreach_get("co", flat)
    return [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]


def _rim(coords):
    """(top z, max radius of the ring at the top z)."""
    top = max(c[2] for c in coords)
    return top, max(math.hypot(c[0], c[1]) for c in coords if c[2] > top - 1e-6)


def check(obj):
    keys = obj.data.shape_keys
    if keys is None:
        print("ERROR: no shape keys on mesh", file=sys.stderr)
        return 3
    names = [kb.name for kb in keys.key_blocks]
    if names != ["Basis", "Tall"]:
        print(f"ERROR: key names {names} != ['Basis', 'Tall']", file=sys.stderr)
        return 4
    basis = _coords(keys.key_blocks["Basis"].data)
    tall_kb = keys.key_blocks["Tall"]
    tall = _coords(tall_kb.data)
    if abs(tall_kb.value - BLEND) > 1e-6:
        print(f"ERROR: Tall.value {tall_kb.value} != {BLEND}", file=sys.stderr)
        return 5

    # undeformed mesh.vertices stay at Basis — the trap this example catches
    raw = _coords(obj.data.vertices)
    raw_top, raw_rim = _rim(raw)
    worst = max(math.dist(a, b) for a, b in zip(raw, basis))
    if worst > 1e-5 or abs(raw_top - H0) > 1e-4 or abs(raw_rim - R_LIP0) > 1e-4:
        print(f"ERROR: undeformed mesh not at Basis (off by {worst:.5f}, "
              f"rim z={raw_top:.4f} r={raw_rim:.4f}, expected {H0}, {R_LIP0})",
              file=sys.stderr)
        return 6

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    em = ev.to_mesh()
    try:
        evald = _coords(em.vertices)
    finally:
        ev.to_mesh_clear()

    # every evaluated vert must match the closed-form blend from key_blocks
    for i, (v, b, k) in enumerate(zip(evald, basis, tall)):
        expect = tuple(b[j] + BLEND * (k[j] - b[j]) for j in range(3))
        if math.dist(v, expect) > 1e-4:
            print(f"ERROR: vert {i} evaluated {v} != blend {expect}", file=sys.stderr)
            return 7
    top, rim = _rim(evald)
    bot = min(c[2] for c in evald)
    if abs(top - EXPECT_TOP_Z) > 1e-4 or abs(bot - EXPECT_BOT_Z) > 1e-4:
        print(f"ERROR: evaluated z [{bot:.4f}, {top:.4f}] != "
              f"[{EXPECT_BOT_Z:.4f}, {EXPECT_TOP_Z:.4f}]", file=sys.stderr)
        return 8
    if abs(rim - EXPECT_RIM_R) > 1e-4:
        print(f"ERROR: rim radius {rim:.4f} != {EXPECT_RIM_R:.4f}", file=sys.stderr)
        return 9

    print(f"keys={names} value={BLEND} verts={len(evald)} eval_z={bot:.3f}..{top:.3f} "
          f"rim_r={rim:.3f} undeformed_rim={raw_top:.3f}/{raw_rim:.3f}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def _principled(name, color, rough, metal=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return mat, b


def _vase_materials():
    # Reactive cobalt glaze: object-space noise mottles two blues so the
    # glaze pools darker and breaks lighter, like a real kiln glaze.
    glaze, gb = _principled("CobaltGlaze", (0.03, 0.12, 0.55), 0.22)
    nt = glaze.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 5.0
    noise.inputs["Detail"].default_value = 3.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.38
    ramp.color_ramp.elements[0].color = (0.02, 0.075, 0.40, 1.0)
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = (0.045, 0.17, 0.66, 1.0)
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], gb.inputs["Base Color"])
    bisque, _ = _principled("Bisque", (0.55, 0.30, 0.18), 0.85)
    gilt, _ = _principled("OchreBand", (0.95, 0.55, 0.12), 0.35)
    inner, _ = _principled("CreamGlaze", (0.80, 0.72, 0.55), 0.3)
    return [glaze, bisque, gilt, inner]


def _basis_ghost(src_obj, name, loc, mat):
    """Contour rings of the Basis, read from the Basis key block: the squat
    jar's belly drawn as three thin lines around the full key."""
    basis = _coords(src_obj.data.shape_keys.key_blocks["Basis"].data)
    prof = vase_profile()
    starts, idx = [], 0
    for r, _z, _m in prof:
        starts.append(idx)
        idx += SEGMENTS if r > 0.0 else 1
    apex = next(i for i, (_r, z, _m) in enumerate(prof) if z == H0)
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 0.006
    cu.bevel_resolution = 2
    for zt in GHOST_RINGS:
        i = min(range(1, apex), key=lambda k: abs(prof[k][1] - zt))
        sp = cu.splines.new('POLY')
        sp.points.add(SEGMENTS - 1)
        for s in range(SEGMENTS):
            sp.points[s].co = (*basis[starts[i] + s], 1.0)
        sp.use_cyclic_u = True
    cu.materials.append(mat)
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc
    bpy.context.collection.objects.link(ob)
    return ob


def render_still(obj, path, engine):
    # Shared Layer 1 gates (render path only) — see gallery_framing.py
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
    sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
    import gallery_framing
    import gallery_asset_quality

    scene = bpy.context.scene
    # No clear() first: the mesh has no slots yet, and Mesh.materials.clear()
    # drops the per-face material_index the lathe build assigned.
    for m in _vase_materials():
        obj.data.materials.append(m)

    # The still is the blend as a progression, left to right: Basis (0), the
    # checked object at BLEND, and the full key (1). Same mesh, same key —
    # only Tall.value differs, so a broken blend reads as three identical
    # jars. The two outer vases are render-only copies; the check already
    # ran on `obj`.
    vases = []
    for value, x in ((0.0, -1.85), (None, 0.0), (1.0, 1.95)):
        if value is None:
            ob = obj
        else:
            me = obj.data.copy()
            me.shape_keys.key_blocks["Tall"].value = value
            ob = bpy.data.objects.new("Vase.Basis" if value == 0.0 else "Vase.Full", me)
            bpy.context.collection.objects.link(ob)
        ob.location = (x, 0.0, 0.0)
        vases.append(ob)

    # A faint contour cage of the Basis around the full-key vase: the squat
    # jar it was blended from, so the lift, flare and slimmed belly read on
    # the one object.
    ghost_mat = bpy.data.materials.new("BasisGhost")
    ghost_mat.use_nodes = True
    gnt = ghost_mat.node_tree
    for n in list(gnt.nodes):
        if n.type != 'OUTPUT_MATERIAL':
            gnt.nodes.remove(n)
    em = gnt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 0.86, 0.62, 1.0)
    em.inputs["Strength"].default_value = 0.9
    gnt.links.new(em.outputs["Emission"],
                  next(n for n in gnt.nodes if n.type == 'OUTPUT_MATERIAL').inputs["Surface"])
    ghost = _basis_ghost(obj, "Vase.BasisGhost", vases[2].location, ghost_mat)

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

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.05, 0.0, 1.12)
    scene.collection.objects.link(aim)

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # default-stage rig per docs/VISUAL-STYLE.md
    light("Key", (-4.0, -5.0, 6.0), 480.0, 5.0, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5.0, -3.5, 2.5), 110.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Rim", (1.0, 4.5, 5.0), 340.0, 4.0, (0.6, 0.78, 1.0), (-55, 0, 175))
    light("Wedge", (1.5, 5.0, 4.0), 420.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    # A little above the rims so each mouth opens into an ellipse and the
    # cream interior reads.
    cam.location = (0.05, -8.2, 3.9)
    scene.collection.objects.link(cam)
    track = cam.constraints.new('TRACK_TO')  # data API, not bpy.ops
    track.target = aim
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'
    scene.camera = cam

    scene.render.engine = 'CYCLES' if engine == 'cycles' else eevee_engine_id()
    if engine == 'cycles':
        scene.cycles.samples = 64
    else:
        try:
            scene.eevee.taa_render_samples = 64
        except AttributeError:
            pass
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = path
    # AgX would wash the cobalt glaze toward slate (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()

    code = gallery_framing.check_framing(scene, cam, hero=vases, elements=vases + [ghost],
                                         stage=[floor, wall])
    if code:
        return code
    code = gallery_asset_quality.check_asset_quality(scene, cam, hero=[obj],
                                                     stage=[floor, wall])
    if code:
        return code
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 12
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--zero-blend", action="store_true",
                   help="set Tall.value to 0 (must fail)")
    args = p.parse_args(argv)

    obj = build(zero_blend=args.zero_blend)
    code = check(obj)
    if code:
        return code

    if args.output:
        code = render_still(obj, os.path.abspath(args.output), args.engine)
        if code:
            return code
        print(f"rendered still {args.output}")

    print("shape-key-blend OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
