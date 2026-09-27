"""A parametric gear built entirely with bmesh — a runnable example.

Witnesses the bmesh ownership contract from mesh-editing-and-bmesh and the
always-free-bmesh rule: every `bmesh.new()` is paired with `bm.free()` in a
`try`/`finally`, and because the construction is parametric the resulting
topology is exactly predictable. The check asserts the closed-form counts —
verts = 2 x (4 x teeth), faces = sides + 2 caps, edges = 3 x profile — and
that the mesh is watertight (every edge borders exactly 2 faces).

``--no-extrude`` skips the face-region extrude and still runs the closed-form
count check, so verts stay at one ring. That is the falsifier
(``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python bmesh_gear.py --                 # check only
    blender --background --python bmesh_gear.py -- --no-extrude    # must fail
    blender --background --python bmesh_gear.py -- --output g.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
from mathutils import Vector

# Shared Layer 1 framing measurement (render path only) — see gallery_framing.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
sys.dont_write_bytecode = True  # keep examples/__pycache__ out of the repo tree
import gallery_framing

TEETH = 14
R_ROOT = 1.0
R_TIP = 1.25
DEPTH = 0.6
# fraction of a tooth period spent at the tip vs the root
TOOTH_DUTY = 0.45

# render staging only (not part of the check)
CAP_RING_SCALE = 150.0  # lathe turning marks: finer than a pixel at gallery scale
CAP_ROUGH = (0.17, 0.21)  # faced caps: a narrow satin band, not a stripe pattern
CAP_BUMP = 0.05       # whisper of bump from the turning marks
FLANK_ROUGH = 0.55    # hobbed tooth flanks: rougher, so every facet catches light


def gear_profile():
    """Vertex ring for the gear silhouette: 4 verts per tooth (root-root-tip-tip)."""
    coords = []
    step = 2 * math.pi / TEETH
    for i in range(TEETH):
        a0 = i * step
        half = step * TOOTH_DUTY / 2
        flank = step * (0.5 - TOOTH_DUTY / 2) / 2
        mid = a0 + step / 2
        coords.append((a0 + flank, R_ROOT))
        coords.append((mid - half, R_TIP))
        coords.append((mid + half, R_TIP))
        coords.append((a0 + step - flank, R_ROOT))
    return [(r * math.cos(a), r * math.sin(a), 0.0) for a, r in coords]


def build_gear(no_extrude=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("Gear")
    bm = bmesh.new()
    try:
        verts = [bm.verts.new(co) for co in gear_profile()]
        face = bm.faces.new(verts)
        if not no_extrude:
            ext = bmesh.ops.extrude_face_region(bm, geom=[face])
            top_verts = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
            bmesh.ops.translate(bm, verts=top_verts, vec=(0.0, 0.0, DEPTH))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()  # the contract this example witnesses
    obj = bpy.data.objects.new("Gear", me)
    bpy.context.collection.objects.link(obj)
    return obj


def check(obj):
    me = obj.data
    profile = 4 * TEETH
    expect_v = 2 * profile          # bottom ring + extruded top ring
    expect_f = profile + 2          # side quads + two caps
    expect_e = 3 * profile          # two rings + verticals
    got = (len(me.vertices), len(me.edges), len(me.polygons))
    if got != (expect_v, expect_e, expect_f):
        print(f"ERROR: topology {got} != expected {(expect_v, expect_e, expect_f)}",
              file=sys.stderr)
        return 3

    # watertight: every edge borders exactly two faces
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        bad = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    finally:
        bm.free()
    if bad:
        print(f"ERROR: {bad} non-manifold edge(s) — gear is not watertight", file=sys.stderr)
        return 4

    print(f"teeth={TEETH} verts={got[0]} edges={got[1]} faces={got[2]} watertight=True")
    return 0


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def machined_brass():
    """Brass finished the way a gear blank is actually cut.

    The two caps are faced on a lathe: turning marks run concentric about the
    gear axis, far finer than a pixel at gallery scale, so they read only as
    a slight satin sheen and a whisper of bump, never as stripes. The tooth
    flanks are hobbed, a rougher milled finish that spreads the key and fill
    across each facet so every flank reads against the stage. Caps and flanks
    are told apart by the object-space face normal, so the finish follows
    the geometry wherever the gear is posed.
    """
    mat = bpy.data.materials.new("MachinedBrass")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.80, 0.47, 0.12, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0

    # turning marks: rings about the object Z axis (the gear axis), centred
    # on the gear's own origin — Generated coordinates would centre them on
    # the bounding-box corner and turn the face into off-axis arcs
    coords = nodes.new("ShaderNodeTexCoord")
    rings = nodes.new("ShaderNodeTexWave")
    rings.wave_type = 'RINGS'
    rings.rings_direction = 'Z'
    rings.inputs["Scale"].default_value = CAP_RING_SCALE
    rings.inputs["Distortion"].default_value = 0.0
    links.new(coords.outputs["Object"], rings.inputs["Vector"])

    # cap mask: 1 on the faced caps, 0 on the hobbed flanks
    geo = nodes.new("ShaderNodeNewGeometry")
    to_obj = nodes.new("ShaderNodeVectorTransform")
    to_obj.vector_type = 'NORMAL'
    to_obj.convert_from = 'WORLD'
    to_obj.convert_to = 'OBJECT'
    links.new(geo.outputs["Normal"], to_obj.inputs["Vector"])
    sep = nodes.new("ShaderNodeSeparateXYZ")
    links.new(to_obj.outputs["Vector"], sep.inputs["Vector"])
    absz = nodes.new("ShaderNodeMath")
    absz.operation = 'ABSOLUTE'
    links.new(sep.outputs["Z"], absz.inputs[0])
    cap = nodes.new("ShaderNodeMath")
    cap.operation = 'GREATER_THAN'
    cap.inputs[1].default_value = 0.5
    links.new(absz.outputs["Value"], cap.inputs[0])

    # narrow roughness band on the caps: a satin sheen, not a stripe pattern
    cap_rough = nodes.new("ShaderNodeMapRange")
    cap_rough.inputs["To Min"].default_value = CAP_ROUGH[0]
    cap_rough.inputs["To Max"].default_value = CAP_ROUGH[1]
    links.new(rings.outputs["Fac"], cap_rough.inputs["Value"])
    rough = nodes.new("ShaderNodeMapRange")  # cap mask 0..1 -> flank..cap
    rough.clamp = True
    links.new(cap.outputs["Value"], rough.inputs["Value"])
    rough.inputs["To Min"].default_value = FLANK_ROUGH
    links.new(cap_rough.outputs["Result"], rough.inputs["To Max"])
    links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])

    # a gentle bump from the same marks, caps only
    height = nodes.new("ShaderNodeMath")
    height.operation = 'MULTIPLY'
    links.new(rings.outputs["Fac"], height.inputs[0])
    links.new(cap.outputs["Value"], height.inputs[1])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = CAP_BUMP
    bump.inputs["Distance"].default_value = 0.002
    links.new(height.outputs["Value"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def ring_gear_mesh(name, teeth, r_root, r_tip, depth, duty=TOOTH_DUTY, bore=None):
    """Render-only companion gear: the same 4-verts-per-tooth profile as
    gear_profile(), optionally an annulus around a bore (outer profile ring
    bridged to an inner circle with the same vertex count), extruded to depth."""
    step = 2 * math.pi / teeth
    coords = []
    for i in range(teeth):
        a0 = i * step
        half = step * duty / 2
        flank = step * (0.5 - duty / 2) / 2
        mid = a0 + step / 2
        coords += [(a0 + flank, r_root), (mid - half, r_tip),
                   (mid + half, r_tip), (a0 + step - flank, r_root)]
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        outer = [bm.verts.new((r * math.cos(a), r * math.sin(a), 0.0)) for a, r in coords]
        if bore is None:
            base = [bm.faces.new(outer)]
        else:
            inner = [bm.verts.new((bore * math.cos(a), bore * math.sin(a), 0.0))
                     for a, _r in coords]
            n = len(outer)
            base = [bm.faces.new((outer[k], outer[(k + 1) % n], inner[(k + 1) % n], inner[k]))
                    for k in range(n)]
        ext = bmesh.ops.extrude_face_region(bm, geom=base)
        top = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=top, vec=(0.0, 0.0, depth))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def solid_mesh(name, build):
    """Small render-only solids (hubs, shafts, spokes) from one bmesh callback."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        build(bm)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def cylinder(bm, r, z0, z1, segs=40, at=(0.0, 0.0)):
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r,
                                depth=z1 - z0)
    for v in res["verts"]:
        v.co += Vector((at[0], at[1], (z0 + z1) / 2))
    return res["verts"]


def box(bm, lo, hi):
    res = bmesh.ops.create_cube(bm, size=1.0)
    for v in res["verts"]:
        v.co = Vector(tuple(lo[k] + (v.co[k] + 0.5) * (hi[k] - lo[k]) for k in range(3)))
    return res["verts"]


def principled(name, base, rough, metal=0.0, noise=None, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    if noise:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = noise
        tex.inputs["Detail"].default_value = 8.0
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = rough - 0.08
        mr.inputs["To Max"].default_value = rough + 0.14
        nt.links.new(tex.outputs["Fac"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], b.inputs["Roughness"])
    return mat


def chamfer(ob, width):
    """Render-only edge chamfer: machined gears never have razor edges."""
    mod = ob.modifiers.new("Chamfer", 'BEVEL')
    mod.width = width
    mod.segments = 2
    mod.limit_method = 'ANGLE'
    mod.angle_limit = math.radians(35)
    mod.harden_normals = False


# Gear train, pitched to the checked gear: pitch radius sits midway between
# root and tip, so every companion shares the checked gear's circular pitch
PITCH_R = (R_ROOT + R_TIP) / 2
CIRC_PITCH = 2 * math.pi * PITCH_R / TEETH
ADDENDUM = (R_TIP - R_ROOT) / 2
HERO_C = (0.0, 3.15)          # checked gear centre in the train plane (x, height)
PINION_TEETH, PINION_DIR = 8, math.radians(28)
WHEEL_TEETH, WHEEL_DIR = 22, math.radians(208)


def companion_pitch_r(teeth):
    return teeth * CIRC_PITCH / (2 * math.pi)


def render_still(obj, path, engine):
    scene = bpy.context.scene
    for poly in obj.data.polygons:
        poly.use_smooth = False  # crisp machined facets
    brass = machined_brass()
    obj.data.materials.append(brass)
    blued = principled("BluedSteel", (0.07, 0.11, 0.22), 0.26, metal=1.0, noise=3.0)
    gunmetal = principled("Gunmetal", (0.34, 0.345, 0.36), 0.30, metal=1.0, noise=3.0)
    plate_paint = principled("PlatePaint", (0.010, 0.014, 0.013), 0.55, metal=0.2,
                             noise=6.0, coat=0.2)
    walnut = principled("Walnut", (0.13, 0.055, 0.025), 0.45, noise=40.0, coat=0.4)
    steel = principled("Shaft", (0.62, 0.62, 0.64), 0.18, metal=1.0)

    # every gear axis runs toward the camera: the train is authored in its own
    # plane (x across, y up, z toward the viewer) under one parent empty
    train = bpy.data.objects.new("Train", None)
    train.rotation_euler = (math.radians(90), 0.0, 0.0)
    train.location = (0.0, 0.0, 0.0)
    scene.collection.objects.link(train)

    def place(ob, cx, cy, spin=0.0, z=0.0):
        # the parent's +90 X turn sends local +Z (the front cap) toward the camera
        ob.parent = train
        ob.location = (cx, cy, z)
        ob.rotation_euler = (0.0, 0.0, spin)

    # the checked gear, posed so one tooth points at each partner (the 14-tooth
    # blank has teeth 180 degrees apart, so both contacts land on a tooth)
    step = 2 * math.pi / TEETH
    place(obj, *HERO_C, spin=PINION_DIR - step / 2)
    chamfer(obj, 0.018)
    gears = [obj]
    parts = []

    def partner(name, teeth, direction, mat, depth, bore=None):
        pr = companion_pitch_r(teeth)
        dist = PITCH_R + pr
        cx = HERO_C[0] + dist * math.cos(direction)
        cy = HERO_C[1] + dist * math.sin(direction)
        me = ring_gear_mesh(name, teeth, pr - ADDENDUM, pr + ADDENDUM, depth, bore=bore)
        me.materials.append(mat)
        for p in me.polygons:
            p.use_smooth = False
        ob = bpy.data.objects.new(name, me)
        scene.collection.objects.link(ob)
        # a gap centred on the line of centres, facing the checked gear's tooth
        place(ob, cx, cy, spin=direction + math.pi, z=(DEPTH - depth) / 2)
        chamfer(ob, 0.014)
        gears.append(ob)
        return ob, cx, cy, pr

    pin, px, py, _ = partner("Pinion", PINION_TEETH, PINION_DIR, blued, 0.5)
    wpr = companion_pitch_r(WHEEL_TEETH)
    wheel, wx, wy, _ = partner("Wheel", WHEEL_TEETH, WHEEL_DIR, gunmetal, 0.42,
                               bore=wpr - ADDENDUM - 0.24)

    # the wheel's web: a hub and five spokes inside its rim
    def web(bm):
        cylinder(bm, 0.42, 0.0, 0.5)
        rim = wpr - ADDENDUM - 0.24
        for k in range(5):
            a = 2 * math.pi * k / 5 + 0.3
            vs = box(bm, (0.30, -0.1, 0.1), (rim + 0.04, 0.1, 0.36))
            for v in vs:
                x, y = v.co.x, v.co.y
                v.co.x = x * math.cos(a) - y * math.sin(a)
                v.co.y = x * math.sin(a) + y * math.cos(a)
    webm = solid_mesh("WheelWeb", web)
    webm.materials.append(gunmetal)
    webo = bpy.data.objects.new("WheelWeb", webm)
    scene.collection.objects.link(webo)
    place(webo, wx, wy, z=(DEPTH - 0.42) / 2 - 0.04)
    chamfer(webo, 0.012)
    parts.append(webo)

    # every arbor: a hub boss in its gear's own metal, then a steel shaft,
    # washer and hex nut clamping the gear to the plate
    def add(name, build, mat, cx, cy, smooth=False, bevel=0.01):
        me = solid_mesh(name, build)
        me.materials.append(mat)
        for p in me.polygons:
            p.use_smooth = smooth
        ob = bpy.data.objects.new(name, me)
        scene.collection.objects.link(ob)
        place(ob, cx, cy)
        chamfer(ob, bevel)
        parts.append(ob)
        return ob

    for (cx, cy), boss_r, depth, mat in ((HERO_C, 0.42, DEPTH, brass),
                                         ((px, py), 0.28, 0.5, blued),
                                         ((wx, wy), 0.50, 0.5, gunmetal)):
        front = DEPTH if depth == DEPTH else (DEPTH + depth) / 2
        add("Boss", lambda bm, r=boss_r, f=front: cylinder(bm, r, 0.0, f + 0.10, segs=48),
            mat, cx, cy, bevel=0.02)

        def fastener(bm, f=front):
            cylinder(bm, 0.11, -0.35, f + 0.30, segs=24)        # shaft into the plate
            cylinder(bm, 0.22, f + 0.10, f + 0.14, segs=32)     # washer
            cylinder(bm, 0.19, f + 0.14, f + 0.27, segs=6)      # hex nut
        add("Fastener", fastener, steel, cx, cy, bevel=0.008)


    # a painted steel backplate the arbors run into (four socket screws,
    # one per corner), on a walnut plinth
    lo_x = min(HERO_C[0] - R_TIP, px - 1.0, wx - wpr - ADDENDUM) - 0.35
    hi_x = max(HERO_C[0] + R_TIP, px + 1.0) + 0.35
    top_z = max(HERO_C[1] + R_TIP, py + 1.0) + 0.3

    def plate(bm):
        box(bm, (lo_x, 0.35, 0.0), (hi_x, 0.55, top_z))
    pm = solid_mesh("Backplate", plate)

    def screws(bm):
        for sx in (lo_x + 0.3, hi_x - 0.3):
            for sz in (0.3, top_z - 0.3):
                vs = cylinder(bm, 0.13, 0.0, 0.07, segs=24)
                for v in vs:   # authored along Z, turned to face the camera (-Y)
                    x, y, z = v.co
                    v.co = Vector((sx + x, 0.35 - z, sz + y))
    sm = solid_mesh("PlateScrews", screws)
    sm.materials.append(steel)
    so = bpy.data.objects.new("PlateScrews", sm)
    scene.collection.objects.link(so)
    so.location.z = 0.32
    pm.materials.append(plate_paint)
    po = bpy.data.objects.new("Backplate", pm)
    scene.collection.objects.link(po)
    chamfer(po, 0.03)

    def plinth(bm):
        box(bm, (lo_x - 0.35, -1.25, -0.32), (hi_x + 0.35, 0.95, 0.0))
    bm_ = solid_mesh("Plinth", plinth)
    bm_.materials.append(walnut)
    plo = bpy.data.objects.new("Plinth", bm_)
    scene.collection.objects.link(plo)
    chamfer(plo, 0.05)
    plo.location.z = 0.32
    po.location.z = 0.32
    train.location.z = 0.32

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
    # metals reflect the environment: keep a faint cool ambient so flanks never go black
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.022, 0.028, 1.0)
    scene.world = world

    centre = Vector(((lo_x + hi_x) / 2, 0.0, 0.32 + top_z / 2))

    def light(name, loc, energy, size, col, aim):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(ob)

    # metals live on reflections: a big soft warm key high left, a cool fill,
    # a warm softbox the brass face can mirror, and the warm wedge on the wall
    light("Key", (-6.0, -6.5, 8.0), 850.0, 5.0, (1.0, 0.95, 0.88), centre)
    light("Fill", (7.0, -5.0, 3.0), 150.0, 9.0, (0.75, 0.85, 1.0), centre)
    # the brass face is a mirror: this softbox sits above and left of the
    # camera so its reflection lands on the checked gear as one warm highlight
    hero_w = Vector((HERO_C[0], -DEPTH, 0.32 + HERO_C[1]))
    light("Card", (centre.x + 1.0, -15.0, centre.z + 7.5), 2200.0, 9.0, (1.0, 0.9, 0.72),
          hero_w)
    light("Rim", (-1.0, 5.0, 8.0), 500.0, 4.0, (0.7, 0.82, 1.0), centre)
    light("Wedge", (3.0, 4.0, 4.0), 900.0, 6.0, (1.0, 0.72, 0.45),
          (5.5, 7.5, 1.5))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (centre.x + 4.6, -17.0, centre.z + 3.6)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = centre + Vector((0.0, 0.0, -0.45))
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
    # AgX would flatten the steel toward chalk (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()
    # Layer 1 framing gate (silhouette matte) — exit 10 on violation, before
    # the beauty render so a defective composition ships no artifact
    fcode = gallery_framing.check_framing(
        scene, cam,
        hero=gears + parts + [po, plo],
        elements=gears + parts + [po, plo],
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
    p.add_argument("--no-extrude", action="store_true",
                   help="skip the face-region extrude (must fail)")
    args = p.parse_args(argv)

    obj = build_gear(no_extrude=args.no_extrude)
    code = check(obj)
    if code:
        return code

    if args.output:
        rcode = render_still(obj, os.path.abspath(args.output), args.engine)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("bmesh-gear OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
