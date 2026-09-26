"""Beveled Bezier arc via the curve data API — a runnable example.

Witnesses that renderable tubes are authored on `bpy.types.Curve` directly
(`splines.new('BEZIER')`, `bezier_points`, `bevel_depth`, `use_fill_caps`) —
not by meshing first or calling curve operators. The check asserts the
closed-form point count and bevel depth, the closed-form Z span (tube
centerline at `z = bevel_depth`, resting on the floor) and X span, plus the
evaluated vert/face counts as a MEASURED regression gate — curve tessellation
has no simple closed form, so those two constants pin today's behavior (see
EXPECT_VERTS below for how to re-measure if a future Blender retessellates).

``--no-caps`` leaves ``use_fill_caps`` False and still asserts the ends are
capped. That is the falsifier (``--same-axis`` in export-preset-axis).

The still stages the checked curve as a round-bar horseshoe magnet: its two
filled caps are the ground-steel pole faces, turned to the camera, with
Bezier-wire paper clips (also beveled curves) and iron filings on the field
lines between the poles. The object transform changes only for the render;
the check reads object-space evaluated geometry and runs first.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python curve_bevel_arc.py --                 # check only
    blender --background --python curve_bevel_arc.py -- --no-caps       # must fail
    blender --background --python curve_bevel_arc.py -- --output c.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse

# Shared Layer 1 framing and asset-quality measurement (render path only) —
# see gallery_framing.py and gallery_asset_quality.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing
import gallery_asset_quality

N_POINTS = 8
RADIUS = 1.5
BEVEL = 0.15
BEVEL_RES = 4
RES_U = 12
# MEASURED regression constants, not closed-form: curve-to-mesh tessellation
# (rings x bevel segments + cap fans) has no simple formula. Verified identical
# on 4.4, 4.5 LTS, and 5.1. If a future Blender changes tessellation, re-measure
# by printing len(em.vertices)/len(em.polygons) in check() and update these.
EXPECT_VERTS = 1044
EXPECT_FACES = 1028


def build(no_caps=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    curve = bpy.data.curves.new("Magnet", 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = BEVEL
    curve.bevel_resolution = BEVEL_RES
    curve.resolution_u = RES_U
    curve.use_fill_caps = not no_caps  # solid ends — not a hollow pipe


    spline = curve.splines.new('BEZIER')
    spline.bezier_points.add(N_POINTS - 1)  # one point exists already
    for i, bp in enumerate(spline.bezier_points):
        a = i / (N_POINTS - 1) * math.pi  # semicircle in XY
        # centerline at z=BEVEL so the tube rests on the floor
        bp.co = (RADIUS * math.cos(a), RADIUS * math.sin(a), BEVEL)
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'

    obj = bpy.data.objects.new("Magnet", curve)
    bpy.context.collection.objects.link(obj)
    return obj


def check(obj):
    curve = obj.data
    if curve.splines[0].type != 'BEZIER':
        print(f"ERROR: spline type {curve.splines[0].type} != BEZIER", file=sys.stderr)
        return 3
    n = len(curve.splines[0].bezier_points)
    if n != N_POINTS:
        print(f"ERROR: bezier points {n} != {N_POINTS}", file=sys.stderr)
        return 4
    if abs(curve.bevel_depth - BEVEL) > 1e-6:
        print(f"ERROR: bevel_depth {curve.bevel_depth} != {BEVEL}", file=sys.stderr)
        return 5
    if not curve.use_fill_caps:
        print("ERROR: use_fill_caps is False — ends should be capped", file=sys.stderr)
        return 6

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    em = ev.to_mesh()
    try:
        got_v = len(em.vertices)
        got_f = len(em.polygons)
        zs = [v.co.z for v in em.vertices]
        z_lo, z_hi = min(zs), max(zs)
        # arc spans x in [-RADIUS, +RADIUS] at the endpoints
        xs = [v.co.x for v in em.vertices]
        x_span = max(xs) - min(xs)
    finally:
        ev.to_mesh_clear()

    if got_v != EXPECT_VERTS or got_f != EXPECT_FACES:
        print(f"ERROR: evaluated topology verts={got_v} faces={got_f} != "
              f"expected verts={EXPECT_VERTS} faces={EXPECT_FACES}",
              file=sys.stderr)
        return 7

    # tube diameter = 2 * bevel; centerline at z=BEVEL → span [0, 2*BEVEL]
    if abs(z_lo) > 1e-4:
        print(f"ERROR: tube does not rest on floor (z_lo={z_lo:.6f})", file=sys.stderr)
        return 8
    if abs(z_hi - 2 * BEVEL) > 1e-4:
        print(f"ERROR: tube height {z_hi:.4f} != 2*bevel={2 * BEVEL:.4f}",
              file=sys.stderr)
        return 9
    # diameter adds 2*BEVEL to the arc's 2*RADIUS span
    expect_x_span = 2 * RADIUS + 2 * BEVEL
    if abs(x_span - expect_x_span) > 0.05:
        print(f"ERROR: x span {x_span:.4f} != {expect_x_span:.4f}", file=sys.stderr)
        return 10

    print(f"points={n} bevel={BEVEL} caps=True eval_verts={got_v} "
          f"eval_faces={got_f} z={z_lo:.3f}..{z_hi:.3f} x_span={x_span:.3f}")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


# --- render-path presentation: a horseshoe magnet ------------------------
# The checked curve is staged as what a capped, beveled Bezier semicircle
# actually is in the world: a round-bar horseshoe magnet. The two filled
# caps (use_fill_caps, the witness) are the magnet's ground pole faces, so
# they face the camera; an uncapped build would show two hollow pipe ends
# exactly where the steel faces are. The paper clips are beveled Bezier
# curves too (explicit FREE handles, straight legs + quarter-circle bends),
# so every tube in frame is authored on bpy.types.Curve, never meshed.

POLE_Y = 0.42          # object-space y below which the bar is bare pole steel
KAPPA = 4.0 / 3.0 * math.tan(math.pi / 8.0)  # quarter-circle Bezier handle factor

# Gem paper clip centerline, unit length along +X, tip (outer bend) at x=0.
# ('L', end) is a straight leg; ('A', center, radius, ccw) a 180-degree bend
# split into two quarter arcs (ccw=True turns left).
GEM_START = (0.60, 0.15)
GEM_PATH = (
    ('L', (0.15, 0.15)),
    ('A', (0.15, 0.00), 0.15, True),
    ('L', (0.85, -0.15)),
    ('A', (0.85, -0.04), 0.11, True),
    ('L', (0.30, 0.07)),
    ('A', (0.30, 0.00), 0.07, True),
    ('L', (0.72, -0.07)),
)


def bezier_path_nodes(start, path, scale):
    """[(co, handle_left, handle_right)] for a line/arc path in the XY plane.

    Lines get handles at thirds (exactly straight); each 180-degree bend is two
    quarter arcs with the KAPPA handle length (circle to within 0.03 %)."""
    from mathutils import Vector
    nodes = [[Vector((start[0], start[1], 0.0)) * scale, None, None]]
    for seg in path:
        p = nodes[-1][0]
        if seg[0] == 'L':
            q = Vector((seg[1][0], seg[1][1], 0.0)) * scale
            nodes[-1][2] = p + (q - p) / 3.0
            nodes.append([q, q - (q - p) / 3.0, None])
            continue
        _, c, r, ccw = seg
        c = Vector((c[0], c[1], 0.0)) * scale
        r *= scale
        a0 = math.atan2(p.y - c.y, p.x - c.x)
        sgn = 1.0 if ccw else -1.0
        for k in (1, 2):
            a_prev = a0 + sgn * (k - 1) * math.pi / 2.0
            a_next = a0 + sgn * k * math.pi / 2.0
            t_prev = Vector((-math.sin(a_prev), math.cos(a_prev), 0.0)) * sgn
            t_next = Vector((-math.sin(a_next), math.cos(a_next), 0.0)) * sgn
            q = c + Vector((math.cos(a_next), math.sin(a_next), 0.0)) * r
            nodes[-1][2] = nodes[-1][0] + t_prev * KAPPA * r
            nodes.append([q, q - t_next * KAPPA * r, None])
    # free end handles continue the end segments
    first, last = nodes[0], nodes[-1]
    first[1] = first[0] - (first[2] - first[0])
    last[2] = last[0] + (last[0] - last[1])
    return nodes


def make_wire(name, nodes, bevel, mat, parent, loc, rot_z):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = bevel
    cu.bevel_resolution = 3
    cu.resolution_u = 10
    cu.use_fill_caps = True
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(nodes) - 1)
    for bp, (co, hl, hr) in zip(sp.bezier_points, nodes):
        bp.handle_left_type = 'FREE'
        bp.handle_right_type = 'FREE'
        bp.co = co
        bp.handle_left = hl
        bp.handle_right = hr
    cu.materials.append(mat)
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    ob.location = (loc[0], loc[1], bevel)  # wire rests on the floor
    ob.rotation_euler = (0.0, 0.0, math.radians(rot_z))
    return ob


def principled(name, color, rough, metal=0.0, spec=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if spec is not None:
        key = "Specular IOR Level" if "Specular IOR Level" in b.inputs else "Specular"
        b.inputs[key].default_value = spec
    return m


def magnet_material():
    """Red enamel bar with ground-steel pole ends, split in object space.

    The bar ends sit at object y=0 with the tube running along +y there, so
    a y threshold cuts a clean band square to the bar near each pole."""
    m = bpy.data.materials.new("MagnetEnamelAndPoles")
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    paint = nodes["Principled BSDF"]
    paint.inputs["Base Color"].default_value = (0.72, 0.035, 0.03, 1.0)
    paint.inputs["Roughness"].default_value = 0.3
    out = nodes["Material Output"]
    steel = nodes.new("ShaderNodeBsdfPrincipled")
    steel.inputs["Base Color"].default_value = (0.82, 0.82, 0.85, 1.0)
    steel.inputs["Metallic"].default_value = 0.7
    steel.inputs["Roughness"].default_value = 0.32
    groove = nodes.new("ShaderNodeBsdfPrincipled")
    groove.inputs["Base Color"].default_value = (0.02, 0.02, 0.022, 1.0)
    groove.inputs["Roughness"].default_value = 0.6
    tc = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(tc.outputs["Object"], sep.inputs[0])
    is_pole = nodes.new("ShaderNodeMath")
    is_pole.operation = 'LESS_THAN'
    is_pole.inputs[1].default_value = POLE_Y
    links.new(sep.outputs["Y"], is_pole.inputs[0])
    in_groove = nodes.new("ShaderNodeMath")
    in_groove.operation = 'COMPARE'
    in_groove.inputs[1].default_value = POLE_Y + 0.012
    in_groove.inputs[2].default_value = 0.012
    links.new(sep.outputs["Y"], in_groove.inputs[0])
    mix1 = nodes.new("ShaderNodeMixShader")
    links.new(is_pole.outputs[0], mix1.inputs[0])
    links.new(paint.outputs[0], mix1.inputs[1])
    links.new(steel.outputs[0], mix1.inputs[2])
    mix2 = nodes.new("ShaderNodeMixShader")
    links.new(in_groove.outputs[0], mix2.inputs[0])
    links.new(mix1.outputs[0], mix2.inputs[1])
    links.new(groove.outputs[0], mix2.inputs[2])
    links.new(mix2.outputs[0], out.inputs["Surface"])
    return m


def make_bearings(parent, mat):
    """Steel balls pulled onto the right pole face (object-space placement)."""
    me = bpy.data.meshes.new("PoleBearings")
    r = 0.075
    centers = [
        (1.66, -r, r),                           # on the face's outer rim
        (1.70, -r - 0.148, r),                   # chained off the first
        (1.60, -r - 0.22, r * 0.8),              # a smaller one pulled in
    ]
    bm = bmesh.new()
    try:
        for c in centers:
            geom = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=r)
            bmesh.ops.translate(bm, verts=geom["verts"], vec=c)
        for f in bm.faces:
            f.smooth = True
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new("PoleBearings", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    return ob


# Field-line circle centres (object y). The field of two opposite parallel
# line poles is exact circles through both poles, centre on the bisector,
# so each filing line is a circular arc from pole face to pole face.
FIELD_CENTRES = (5.0, 3.2, 2.2, 1.55, 1.1, 0.75, 0.45, 0.2)


def field_lines(half=1.5):
    """Arcs (object XY, y < 0) from the left pole face to the right one."""
    from mathutils import Vector
    lines = []
    for c in FIELD_CENTRES:
        r = math.hypot(half, c)
        a0 = math.atan2(-c, -half)            # angle of the left pole seen from the centre
        a1 = math.atan2(-c, half)              # right pole ...
        if a1 < a0:                            # ... reached the low way round
            a1 += 2 * math.pi
        n = max(8, int(abs(a1 - a0) * r / 0.02))
        pts = []
        for k in range(n + 1):
            a = a0 + (a1 - a0) * k / n
            p = Vector((r * math.cos(a), c + r * math.sin(a)))
            if p.y < -0.02:
                pts.append(p)
        lines.append(pts)
    return lines


def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
    return (a + ab * t - p).length


def make_filings(parent, mat, avoid=(), seed=7):
    """Iron filings strewn along the field lines: small tilted steel slivers
    in one mesh, jittered off each arc and skipped under the clips. Scene
    dressing, not the asset: its boxes would read as the asset's right-angle
    edges in gallery_asset_quality."""
    import random
    from mathutils import Matrix, Vector
    rnd = random.Random(seed)
    me = bpy.data.meshes.new("IronFilings")
    bm = bmesh.new()
    try:
        for pts in field_lines():
            acc = 0.0
            for a, b in zip(pts, pts[1:]):
                acc += (b - a).length
                if acc < 0.045:
                    continue
                acc = 0.0
                d = (b - a).normalized()
                nrm = Vector((-d.y, d.x))
                c = a + nrm * rnd.uniform(-0.03, 0.03) + d * rnd.uniform(-0.02, 0.02)
                if any(_seg_dist(c, s0, s1) < 0.07 for s0, s1 in avoid):
                    continue
                ln = rnd.uniform(0.045, 0.08)
                geom = bmesh.ops.create_cube(bm, size=1.0)
                vs = geom["verts"]
                bmesh.ops.scale(bm, verts=vs, vec=(ln, 0.014, 0.009))
                yaw = math.atan2(d.y, d.x) + rnd.uniform(-0.22, 0.22)
                rot = Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(rnd.uniform(-0.6, 0.6), 4, 'X')
                bmesh.ops.transform(bm, verts=vs, matrix=rot)
                bmesh.ops.translate(bm, verts=vs, vec=(c.x, c.y, 0.006))
        bm.to_mesh(me)
    finally:
        bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new("IronFilings", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    return ob


def clip_segments(nodes, loc, rot_z):
    """The clip's node polyline in the magnet's object XY (for filings)."""
    from mathutils import Matrix, Vector
    m = Matrix.Rotation(math.radians(rot_z), 2)
    pts = [m @ Vector((co.x, co.y)) + Vector(loc) for co, _, _ in nodes]
    return list(zip(pts, pts[1:]))


def render_still(obj, path, engine):
    scene = bpy.context.scene
    obj.data.materials.append(magnet_material())
    # the open end (both capped pole faces) points at the camera on -Y
    obj.rotation_euler = (0.0, 0.0, math.radians(-8))
    bpy.context.view_layer.update()

    teal = principled("ClipVinylTeal", (0.0, 0.34, 0.40), 0.35)
    amber = principled("ClipVinylAmber", (0.95, 0.52, 0.02), 0.35)
    chrome = principled("BearingChrome", (0.9, 0.9, 0.92), 0.18, metal=0.85)

    clip_len = 0.85
    gem = bezier_path_nodes(GEM_START, GEM_PATH, clip_len)
    bevel_w = 0.02
    # each clip's tip touches a pole face (object y=0) at the floor and the
    # clip lies along the field line leaving that pole, as a real one would
    placements = (("ClipTeal", teal, (-1.5, -bevel_w), -46.0),
                  ("ClipAmber", amber, (1.5, -bevel_w), -134.0))
    clips, avoid = [], []
    for name, mat, loc, ang in placements:
        clips.append(make_wire(name, gem, bevel_w, mat, obj, loc, ang))
        avoid += clip_segments(gem, loc, ang)
    bearings = make_bearings(obj, chrome)
    make_filings(obj, principled("FilingSteel", (0.55, 0.56, 0.6), 0.3, metal=0.9),
                 avoid=avoid)
    parts = [obj, *clips, bearings]

    floor_me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
        bm.to_mesh(floor_me)
    finally:
        bm.free()
    fmat = principled("Studio", (0.03, 0.032, 0.037), 0.7)
    floor_me.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", floor_me)
    scene.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", floor_me.copy())
    wall.location = (0.0, 7.0, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, -0.3, 0.1)
    scene.collection.objects.link(aim)

    def light(name, loc, energy, size, col):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        scene.collection.objects.link(ob)
        lc = ob.constraints.new('TRACK_TO')
        lc.target = aim
        lc.track_axis = 'TRACK_NEGATIVE_Z'
        lc.up_axis = 'UP_Y'

    # warm shaped key, faint cool fill, cool rim, warm wedge on the back wall
    # (docs/VISUAL-STYLE.md)
    light("Key", (-3.5, -3.0, 6.5), 330.0, 4.0, (1.0, 0.96, 0.9))
    light("Fill", (5.0, -3.5, 2.5), 70.0, 9.0, (0.75, 0.85, 1.0))
    light("Rim", (0.5, 4.2, 4.5), 160.0, 3.0, (0.6, 0.78, 1.0))
    # the wedge sits between the magnet and the wall and aims at the wall,
    # so its pool lands on the backdrop, not across the floor
    wall_spot = bpy.data.objects.new("WedgeTarget", None)
    wall_spot.location = (1.2, 7.0, 1.4)
    scene.collection.objects.link(wall_spot)
    wedge = bpy.data.lights.new("Wedge", 'AREA')
    wedge.energy = 300.0
    wedge.size = 5.0
    wedge.color = (1.0, 0.76, 0.5)
    wob = bpy.data.objects.new("Wedge", wedge)
    wob.location = (-0.5, 4.5, 3.4)
    scene.collection.objects.link(wob)
    wc = wob.constraints.new('TRACK_TO')
    wc.target = wall_spot
    wc.track_axis = 'TRACK_NEGATIVE_Z'
    wc.up_axis = 'UP_Y'

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.55, -4.9, 3.3)
    scene.collection.objects.link(cam)
    scene.camera = cam
    track = cam.constraints.new('TRACK_TO')
    track.target = aim
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'

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
    # AgX would wash the red enamel toward salmon (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    # Layer 1 gates, before the beauty render so a defective composition
    # ships no artifact: framing (silhouette matte, exit 10) on the magnet,
    # margins on everything that matters; asset quality (exit 11).
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=[obj],
        elements=parts,
        stage=[floor, wall],
    )
    if fcode:
        return fcode
    qcode = gallery_asset_quality.check_asset_quality(
        scene, cam, hero=parts, stage=[floor, wall])
    if qcode:
        return qcode
    bpy.ops.render.render(write_still=True)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        print("ERROR: render produced no file", file=sys.stderr)
        return 11
    return 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--no-caps", action="store_true",
                   help="falsifier: use_fill_caps=False, still assert caps")
    args = p.parse_args(argv)

    obj = build(no_caps=args.no_caps)

    code = check(obj)
    if code:
        return code

    if args.output:
        rcode = render_still(obj, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("curve-bevel-arc OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
