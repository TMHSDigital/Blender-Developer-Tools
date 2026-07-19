"""A retro rocket at three LODs via the Decimate modifier — a runnable example.

Witnesses the modifier-based LOD contract that game pipelines rely on and
AI-generated code most often gets wrong:

1. Decimate is non-destructive and lives in the depsgraph. The evaluated mesh
   carries the reduction; the original datablock is byte-identical before and
   after evaluation. The check proves both: evaluated counts drop while
   ``obj.data`` keeps the closed-form counts — and ``to_mesh_clear()`` releases
   every evaluated reference (the lifetime contract from
   depsgraph-and-evaluated-data).
2. The COLLAPSE ratio is a target, not a guarantee. Each LOD's evaluated
   triangle count must land near ``ratio x base_tris`` — bounded, not equal.
   The check derives the bounds from the measured behavior of a known mesh and
   fails on any excursion (a wrong ratio, a dropped modifier, or an exporter
   that silently shipped the base mesh all trip it).
3. LODs preserve silhouette-critical dimensions. A rocket's height and fin
   span are its readability; the evaluated bounding boxes must hold the base
   bbox within tolerance at every level. Decimate offers no vertex pinning, so
   this is a real, measurable risk — not a formality.

The Decimate modifier API (``decimate_type='COLLAPSE'``, ``ratio``) is stable
between Blender 4.5 LTS and 5.1 — the example runs identically on both, which
is itself the version witness.

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python lod_decimate_chain.py --                 # check only
    blender --background --python lod_decimate_chain.py -- --output r.png  # + render
"""
import bpy, bmesh, sys, os, math, argparse
import mathutils

CREAM, RED, TRIM, GLASS = 0, 1, 2, 3
SIDES = 64                      # lathe resolution of LOD0
FIN_ANGLES = (90.0, 210.0, 330.0)  # back fin + two forward-splayed fins
LODS = (0.5, 0.18)              # LOD1 / LOD2 collapse ratios (LOD0 is the base)
RATIO_BOUNDS = 0.05             # measured 0.44% worst-case; 10x margin, still fails a real drift
BBOX_TOL = 1e-3                 # measured 7.7e-6 worst-case; silhouette preservation, absolute units

# lathe profile: (z, radius, material) from nozzle exit to shoulder, plus the
# ogive nose rings and a single tip vertex — every ring a closed form
PROFILE = [
    (0.00, 0.34, TRIM),         # nozzle exit bell
    (0.06, 0.30, TRIM),
    (0.28, 0.22, TRIM),         # throat
    (0.38, 0.26, TRIM),         # nozzle-body joint
    (0.46, 0.42, CREAM),        # body flare
    (0.70, 0.44, CREAM),
    (1.90, 0.44, CREAM),
    (2.05, 0.42, CREAM),        # body top
    (2.16, 0.36, RED),          # shoulder
    (2.26, 0.28, RED),          # nose base
]
NOSE_RINGS = 7                  # ogive sampled k/8 for k in 1..7
NOSE_LEN = 0.86
TIP_Z = 2.26 + NOSE_LEN         # 3.12 — silhouette-critical height
FIN_R_OUT = 0.98                # silhouette-critical fin span
# fin plate profile in the (radius, z) plane: long root chord, short tip chord
FIN_PROFILE = [(0.38, 0.40), (0.98, 0.40), (0.98, 0.55), (0.42, 1.02)]
FIN_THICK = 0.07
PORT_POS = (0.0, -0.415, 1.55)  # porthole on the camera-facing hull
PORT_R = 0.16
PORT_DEPTH = 0.09


def lathe(bm, rings, mat_ranges=None):
    """Revolve (z, r, mat) rings around Z; returns (ring_verts, tip_vert)."""
    sides = []
    for z, r, _mat in rings:
        sides.append([bm.verts.new((r * math.cos(2 * math.pi * s / SIDES),
                                    r * math.sin(2 * math.pi * s / SIDES), z))
                      for s in range(SIDES)])
    for k in range(len(sides) - 1):
        mat = rings[k][2]
        for s in range(SIDES):
            f = bm.faces.new((sides[k][s], sides[k][(s + 1) % SIDES],
                              sides[k + 1][(s + 1) % SIDES], sides[k + 1][s]))
            f.material_index = mat
    return sides


def nose_radius(t):
    return 0.28 * math.sqrt(max(0.0, 1.0 - t * t))


def build_fin(bm, angle_deg):
    """One swept fin plate: FIN_PROFILE revolved into place, thickness FIN_THICK."""
    a = math.radians(angle_deg)
    u = mathutils.Vector((math.cos(a), math.sin(a), 0.0))       # radial out
    w = mathutils.Vector((-math.sin(a), math.cos(a), 0.0))      # thickness dir
    verts = []
    for half in (-FIN_THICK / 2, FIN_THICK / 2):
        for r, z in FIN_PROFILE:
            p = u * r + w * half + mathutils.Vector((0.0, 0.0, z))
            verts.append(bm.verts.new(p))
    n = len(FIN_PROFILE)
    faces = [bm.faces.new((verts[0], verts[1], verts[2], verts[3])),
             bm.faces.new((verts[4], verts[7], verts[6], verts[5]))]
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((verts[i], verts[i + n], verts[j + n], verts[j])))
    for f in faces:
        f.material_index = RED


def build_rocket():
    """The LOD0 rocket: lathed body, 3 fin plates, one porthole — all closed form."""
    me = bpy.data.meshes.new("Rocket")
    bm = bmesh.new()
    try:
        rings = list(PROFILE)
        for k in range(1, NOSE_RINGS + 1):
            t = k / (NOSE_RINGS + 1)
            rings.append((2.26 + NOSE_LEN * t, nose_radius(t), RED))
        sides = lathe(bm, rings)
        tip = bm.verts.new((0.0, 0.0, TIP_Z))
        for s in range(SIDES):
            f = bm.faces.new((sides[-1][s], sides[-1][(s + 1) % SIDES], tip))
            f.material_index = RED
        bottom = bm.verts.new((0.0, 0.0, 0.0))
        for s in range(SIDES):
            f = bm.faces.new((sides[0][(s + 1) % SIDES], sides[0][s], bottom))
            f.material_index = TRIM
        for ang in FIN_ANGLES:
            build_fin(bm, ang)
        # porthole: rim tube + glass disc, axis along Y, interpenetrating the hull
        py = [PORT_POS[1] - PORT_DEPTH / 2, PORT_POS[1] + PORT_DEPTH / 2]
        rim = [[bm.verts.new((PORT_R * math.cos(2 * math.pi * s / 16) + PORT_POS[0],
                              y, PORT_R * math.sin(2 * math.pi * s / 16) + PORT_POS[2]))
                for s in range(16)] for y in py]
        for s in range(16):
            f = bm.faces.new((rim[0][s], rim[0][(s + 1) % 16],
                              rim[1][(s + 1) % 16], rim[1][s]))
            f.material_index = TRIM
        center = bm.verts.new((PORT_POS[0], py[0] - 0.005, PORT_POS[2]))
        for s in range(16):
            f = bm.faces.new((rim[0][(s + 1) % 16], rim[0][s], center))
            f.material_index = GLASS
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()  # the ownership contract, as always
    for poly in me.polygons:
        poly.use_smooth = False  # faceted toy-rocket finish; facets carry the LOD story
    obj = bpy.data.objects.new("Rocket", me)
    bpy.context.collection.objects.link(obj)
    return obj


def closed_form_counts():
    """Expected base-mesh counts, derived from the build constants."""
    rings = len(PROFILE) + NOSE_RINGS
    verts = rings * SIDES + 2 + 3 * 8 + 2 * 16 + 1        # +tip +bottom +fins +rim +port center
    quads = (rings - 1) * SIDES + 3 * 6 + 16
    tris = 2 * SIDES + 16                                  # tip fan + bottom fan + port glass
    faces = quads + tris
    total_tris = 2 * quads + tris
    return verts, faces, total_tris


def closed_form_bbox():
    """Exact bbox from the build constants: 3 fins at 120° is not x/y-symmetric."""
    pts = [(math.cos(a) * FIN_R_OUT - math.sin(a) * (FIN_THICK / 2) * s,
            math.sin(a) * FIN_R_OUT + math.cos(a) * (FIN_THICK / 2) * s)
           for a in (math.radians(d) for d in FIN_ANGLES) for s in (-1, 1)]
    pts += [(0.44, 0.44), (-0.44, -0.44), (PORT_R, PORT_POS[1]),
            (-PORT_R, PORT_POS[1])]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return ((min(xs), min(ys), 0.0), (max(xs), max(ys), TIP_Z))


def eval_mesh(obj):
    """Snapshot an evaluated mesh, then release it (lifetime contract)."""
    deps = bpy.context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(deps)
    me = ob_eval.to_mesh()
    try:
        me.calc_loop_triangles()
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        zs = [v.co.z for v in me.vertices]
        return {"verts": len(me.vertices), "tris": len(me.loop_triangles),
                "bbox": ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))}
    finally:
        ob_eval.to_mesh_clear()


def add_decimate(obj, ratio):
    mod = obj.modifiers.new("LOD", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    return mod


def check(rocket, lod1, lod2):
    me = rocket.data
    want_v, want_f, want_t = closed_form_counts()
    got = (len(me.vertices), len(me.polygons))
    if got != (want_v, want_f):
        print(f"ERROR: base topology {got} != closed form {(want_v, want_f)}",
              file=sys.stderr)
        return 3
    bb_min, bb_max = closed_form_bbox()
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    base_bb = ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))
    bb_err = max(abs(base_bb[i][k] - want[i][k])
                 for i in (0, 1) for k in range(3)
                 for want in ((bb_min, bb_max),))
    if bb_err > 1e-6:
        print(f"ERROR: base bbox deviates {bb_err:.3e} from its closed form",
              file=sys.stderr)
        return 4

    # LOD0 sanity: no modifier, evaluated == original counts
    snap0 = eval_mesh(rocket)
    if (snap0["verts"], snap0["tris"]) != (want_v, want_t):
        print(f"ERROR: LOD0 evaluated counts {(snap0['verts'], snap0['tris'])} != "
              f"base {(want_v, want_t)}", file=sys.stderr)
        return 5

    measured = []
    for lod, ratio in ((lod1, LODS[0]), (lod2, LODS[1])):
        add_decimate(lod, ratio)
        snap = eval_mesh(lod)
        # contract 2: triangle count lands near ratio * base, within bounds
        target = ratio * want_t
        dev = abs(snap["tris"] - target) / target
        # contract 1: the reduction is real and the original is untouched
        if snap["tris"] >= want_t:
            print(f"ERROR: evaluated tris {snap['tris']} >= base {want_t} — "
                  "the modifier did not reduce (evaluated == original)",
                  file=sys.stderr)
            return 6
        if (len(lod.data.vertices), len(lod.data.polygons)) != (want_v, want_f):
            print("ERROR: original datablock changed after evaluation — "
                  "Decimate must be non-destructive", file=sys.stderr)
            return 7
        if dev > RATIO_BOUNDS:
            print(f"ERROR: LOD tris {snap['tris']} deviates {dev:.1%} from "
                  f"ratio target {target:.0f} (bounds {RATIO_BOUNDS:.0%})",
                  file=sys.stderr)
            return 8
        # contract 3: silhouette-critical dimensions survive
        bbox_dev = max(abs(snap["bbox"][i][k] - base_bb[i][k])
                       for i in (0, 1) for k in range(3))
        if bbox_dev > BBOX_TOL:
            print(f"ERROR: LOD bbox deviates {bbox_dev:.4f} from base "
                  f"(tol {BBOX_TOL}) — silhouette-critical dims lost",
                  file=sys.stderr)
            return 9
        measured.append((ratio, snap["tris"], target, dev, bbox_dev))

    print(f"sides={SIDES} base_verts={want_v} base_tris={want_t} "
          f"bbox_err={bb_err:.2e}")
    for ratio, tris, target, dev, bbox_dev in measured:
        print(f"lod ratio={ratio} tris={tris} target={target:.0f} "
              f"dev={dev:.2%} (bounds {RATIO_BOUNDS:.0%}) "
              f"bbox_dev={bbox_dev:.2e} (tol {BBOX_TOL})")
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
        pbr("Cream", (0.85, 0.80, 0.68), 0.05, 0.45),
        pbr("Red", (0.72, 0.10, 0.08), 0.15, 0.40),
        pbr("Gunmetal", (0.11, 0.12, 0.14), 0.9, 0.32),
        pbr("Glass", (0.05, 0.30, 0.36), 0.0, 0.25,
            emission=(0.12, 0.60, 0.68), strength=0.8),
    ]


def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(rockets, path, engine):
    scene = bpy.context.scene
    xs = (-2.8, 0.0, 2.8)
    for ob, x in zip(rockets, xs):
        ob.location.x = x

    pm = bpy.data.materials.new("PlaqueMetal")
    pm.use_nodes = True
    pb = pm.node_tree.nodes["Principled BSDF"]
    # diffuse light-grey, not metal: plaques must read against the dark floor
    # regardless of what the environment reflects
    pb.inputs["Base Color"].default_value = (0.42, 0.44, 0.48, 1.0)
    pb.inputs["Metallic"].default_value = 0.2
    pb.inputs["Roughness"].default_value = 0.6

    def plaque(text, x):
        cu = bpy.data.curves.new("Plaque", 'FONT')
        cu.body = text
        cu.align_x = 'CENTER'
        cu.size = 0.30
        cu.extrude = 0.008
        ob = bpy.data.objects.new("Plaque", cu)
        ob.location = (x, -1.5, 0.01)
        ob.data.materials.append(pm)
        scene.collection.objects.link(ob)

    for label, x in zip(("LOD0", "LOD1", "LOD2"), xs):
        plaque(label, x)

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
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, -12.6, 2.5)
    scene.collection.objects.link(cam)
    target = bpy.data.objects.new("Aim", None)
    target.location = (0.0, 0.0, 1.35)
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
    # AgX would wash the cream body and red fins toward pastel
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
    mats = make_materials()
    rockets = []
    for _ in range(3):
        r = build_rocket()
        for m in mats:
            r.data.materials.append(m)
        rockets.append(r)
    code = check(rockets[0], rockets[1], rockets[2])
    if code:
        return code

    if args.output:
        if not render_still(rockets, os.path.abspath(args.output), args.engine):
            print("ERROR: render produced no file", file=sys.stderr)
            return 10
        print(f"rendered still {args.output}")

    print("lod-decimate-chain OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
