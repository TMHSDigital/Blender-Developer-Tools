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

TEETH = 14
R_ROOT = 1.0
R_TIP = 1.25
DEPTH = 0.6
# fraction of a tooth period spent at the tip vs the root
TOOTH_DUTY = 0.45

# render staging only (not part of the check)
STAGE_BITE = 0.003    # contact depth into the floor and into the gear's back
WEDGE_SLOPE = 1.55    # display wedge slope length, up the gear's back face
WEDGE_WIDTH = 1.8     # display wedge width across the gear


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


def render_still(obj, path, engine):
    scene = bpy.context.scene
    for poly in obj.data.polygons:
        poly.use_smooth = False  # crisp machined facets
    # machined brass: a flat metal face lit by area lights renders as one
    # featureless gradient, so the finish carries the design — concentric
    # turning marks (a RINGS wave driving roughness) break the face into
    # rings that each catch the key at a different angle
    mat = bpy.data.materials.new("MachinedBrass")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.72, 0.44, 0.16, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    rings = nt.nodes.new("ShaderNodeTexWave")
    rings.wave_type = 'RINGS'
    rings.rings_direction = 'SPHERICAL'  # concentric from center, not X-axis bands
    rings.inputs["Scale"].default_value = 16.0
    rings.inputs["Distortion"].default_value = 0.5
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["From Min"].default_value = 0.0
    rough.inputs["From Max"].default_value = 1.0
    rough.inputs["To Min"].default_value = 0.14
    rough.inputs["To Max"].default_value = 0.36
    nt.links.new(rings.outputs["Fac"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    obj.data.materials.append(mat)
    # the gear leans back on an inclined display wedge. Both contacts are
    # derived from the posed mesh: the lowest back-cap vertex bites into
    # the floor, and the wedge's slope lies in the back-cap plane, sunk into
    # the gear, so the lean is carried rather than hung in the air
    obj.rotation_euler = (math.radians(46), 0.0, math.radians(22))
    obj.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    obj.location.z = -min((obj.matrix_world @ v.co).z for v in obj.data.vertices) - STAGE_BITE
    bpy.context.view_layer.update()
    mw = obj.matrix_world
    rot = mw.to_3x3()
    side = (rot @ Vector((1.0, 0.0, 0.0))).normalized()
    up = (rot @ Vector((0.0, 1.0, 0.0))).normalized()
    into = (rot @ Vector((0.0, 0.0, 1.0))).normalized()
    low = min((mw @ v.co for v in obj.data.vertices), key=lambda p: p.z)
    centre = mw @ Vector((0.0, 0.0, 0.0))
    foot = low + side * (centre - low).dot(side) + into * STAGE_BITE
    top = foot + up * WEDGE_SLOPE
    back = Vector((top.x, top.y, -STAGE_BITE))
    front = Vector((foot.x, foot.y, -STAGE_BITE))
    wedge_me = bpy.data.meshes.new("Wedge")
    bm = bmesh.new()
    try:
        half = side * (WEDGE_WIDTH / 2)
        ring = [[bm.verts.new(p + sgn * half) for p in (front, foot, top, back)]
                for sgn in (-1.0, 1.0)]
        a, b = ring
        bm.faces.new(a)
        bm.faces.new(b[::-1])
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a[i], a[j], b[j], b[i]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(wedge_me)
    finally:
        bm.free()
    wmat = bpy.data.materials.new("DisplayStand")
    wmat.use_nodes = True
    wb = wmat.node_tree.nodes["Principled BSDF"]
    # matte and dark: the slope faces the key square-on, and at the floor's
    # finish its specular sheen alone (~45/255, measured) reads as paper
    wb.inputs["Base Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    wb.inputs["Roughness"].default_value = 0.9
    spec = wb.inputs.get("Specular IOR Level") or wb.inputs.get("Specular")
    spec.default_value = 0.1
    wedge_me.materials.append(wmat)
    scene.collection.objects.link(bpy.data.objects.new("Wedge", wedge_me))

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
    # metals reflect the environment: keep a faint cool ambient so flanks never go black
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.022, 0.028, 1.0)
    scene.world = world

    def light(name, loc, energy, size, col, rot):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy; ld.size = size; ld.color = col
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        scene.collection.objects.link(ob)

    # metals live on reflections: soft warm key, restrained cool fill, and the
    # warm wedge raking the back wall (docs/VISUAL-STYLE.md)
    light("Key", (-3.5, -4.5, 5.5), 550.0, 4.5, (1.0, 0.96, 0.9), (48, 0, -35))
    light("Fill", (5.0, -3.5, 2.5), 130.0, 9.0, (0.75, 0.85, 1.0), (65, 0, 50))
    light("Wedge", (2.5, 5.5, 4.0), 380.0, 6.0, (1.0, 0.76, 0.5), (-68, 0, 190))
    # a small hot glint: brass needs one crisp specular streak to read machined
    light("Glint", (1.8, -5.2, 6.2), 900.0, 0.9, (1.0, 0.9, 0.7), (40, 0, 18))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 55.0
    cam = bpy.data.objects.new("Cam", cam_data)
    # the camera rides with the gear's derived seat height (it was posed for
    # a gear hung at z=0.85), so the composition is unchanged
    cam.location = (0.0, -7.6, 4.2 + obj.location.z - 0.85)
    cam.rotation_euler = (math.radians(66), 0.0, 0.0)
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
    # AgX would flatten the steel toward chalk (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0


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
        if not render_still(obj, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 6
        print(f"rendered still {args.output}")

    print("bmesh-gear OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
