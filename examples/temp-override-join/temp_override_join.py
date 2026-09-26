"""Join meshes via bpy.context.temp_override — a runnable example.

Witnesses the prefer-temp-override-over-context-copy contract: operators that
need a fabricated active/selection context must run under
`bpy.context.temp_override(**kwargs)`, not the deprecated
`bpy.ops.*(bpy.context.copy())` dict-pass form (removed in 5.x).

A hurricane lantern is modeled the way a prop artist blocks one out: seven
separate part objects (fount, glass globe, wire guard, side air tubes, cap,
bail with its wooden grip, brasswork), each with its own material and its own
object transform. One `object.join` under `temp_override` assembles them into
the single `Lantern` object an engine wants. The check asserts:

- exactly one mesh object remains, and it is the join target;
- every source object is gone;
- no geometry was lost (verts / faces equal the sum over the parts);
- material slots merged: the joined mesh carries exactly the five distinct
  part materials, once each, and every material still owns exactly the faces
  its parts brought in (so the glass is still glass, the grip still wood);
- the part transforms were applied: the joined mesh's local Z span runs from
  the fount's foot (0) to the top of the bail grip (closed form).

``--no-override`` calls ``object.join`` without ``temp_override``. If the
operator raises, that is caught and the existing object-count check still
runs. That is the falsifier (``--same-axis`` in export-preset-axis).

By default it runs only the correctness check (no render) — the CI smoke
check. Pass --output to also render a still:

    blender --background --python temp_override_join.py --                 # check only
    blender --background --python temp_override_join.py -- --no-override   # must fail
    blender --background --python temp_override_join.py -- --output j.png  # + render
"""
import argparse
import math
import os
import sys
from collections import Counter

import bmesh
import bpy
from mathutils import Vector

# Shared Layer 1 framing + asset-quality measurement (render path only) — see
# gallery_framing.py for the __file__-relative import shim this relies on.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
import gallery_framing  # noqa: E402
import gallery_asset_quality  # noqa: E402

SEGS = 32            # lathe segments; divisible by 4 so a vertex sits on +Z of the grip
WIRE_SIDES = 8

# Bail: a wire arc in the XZ plane from the side tubes up over the cap.
BAIL_X = 0.745
BAIL_Z0 = 1.25
BAIL_H = 1.0
# Wooden grip threaded on the top of the bail, axis along X.
GRIP_R = 0.065
GRIP_HALF = 0.17
GRIP_CZ = BAIL_Z0 + BAIL_H - 0.012
# Closed-form local Z span of the joined lantern: fount foot to grip top.
EXPECT_Z_LO = 0.0
EXPECT_Z_HI = GRIP_CZ + GRIP_R

# Camera yaw (degrees off the -Y front); the wick knob faces the camera.
CAM_YAW = 32.0

# (part object name, material key). The first entry is the join target.
PARTS = ("Fount", "Globe", "Guard", "Tubes", "Cap", "Bail", "Brasswork")
MATERIALS = ("Paint", "Glass", "Iron", "Brass", "Wood")


# ------------------------------------------------------------------ modeling

def lathe(bm, profile, segs=SEGS, closed_profile=False, mat=0):
    """Revolve an (r, z) profile about local Z. Points with r == 0 become
    poles. Profile order bottom -> out -> up -> in gives outward normals."""
    angles = [2.0 * math.pi * i / segs for i in range(segs)]
    rings = []
    for r, z in profile:
        if r < 1e-9:
            rings.append([bm.verts.new((0.0, 0.0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(a), r * math.sin(a), z))
                          for a in angles])
    pairs = list(zip(rings, rings[1:]))
    if closed_profile:
        pairs.append((rings[-1], rings[0]))
    faces = []
    for a, b in pairs:
        for i in range(segs):
            j = (i + 1) % segs
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                vs = (a[0], b[j], b[i])
            elif len(b) == 1:
                vs = (a[i], a[j], b[0])
            else:
                vs = (a[i], a[j], b[j], b[i])
            f = bm.faces.new(vs)
            f.material_index = mat
            f.smooth = True
            faces.append(f)
    return [v for ring in rings for v in ring]


def tube(bm, pts, radius, sides=WIRE_SIDES, mat=0):
    """Sweep a round wire along a polyline (parallel-transport frames)."""
    pts = [Vector(p) for p in pts]
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append((b - a).normalized())
    ref = Vector((0, 0, 1)) if abs(tans[0].z) < 0.9 else Vector((1, 0, 0))
    n = (ref - tans[0] * ref.dot(tans[0])).normalized()
    rings = []
    for i, p in enumerate(pts):
        t = tans[i]
        n = (n - t * n.dot(t)).normalized()
        b = t.cross(n)
        rings.append([bm.verts.new(p + radius * (n * math.cos(2 * math.pi * k / sides)
                                                 + b * math.sin(2 * math.pi * k / sides)))
                      for k in range(sides)])
    for r0, r1 in zip(rings, rings[1:]):
        for k in range(sides):
            m = (k + 1) % sides
            f = bm.faces.new((r0[k], r0[m], r1[m], r1[k]))
            f.material_index = mat
            f.smooth = True


def torus(bm, r_major, r_minor, z, mat=0, segs=SEGS, sides=WIRE_SIDES):
    prof = [(r_major + r_minor * math.cos(math.radians(-90 + 360 * k / sides)),
             z + r_minor * math.sin(math.radians(-90 + 360 * k / sides)))
            for k in range(sides)]
    lathe(bm, prof, segs=segs, closed_profile=True, mat=mat)


def aligned(bm, verts, axis, origin):
    """Rotate verts built along +Z so +Z points along `axis`, then move to origin."""
    rot = Vector((0, 0, 1)).rotation_difference(Vector(axis).normalized()).to_matrix()
    for v in verts:
        v.co = rot @ v.co + Vector(origin)


def build_fount(bm):
    # squat painted fuel fount: foot ring, drum, domed shoulder, burner collar
    lathe(bm, [(0.0, 0.0), (0.56, 0.0), (0.60, 0.012), (0.62, 0.045), (0.60, 0.075),
               (0.58, 0.10), (0.62, 0.15), (0.655, 0.215), (0.685, 0.232), (0.685, 0.248),
               (0.662, 0.265), (0.67, 0.33), (0.64, 0.41),
               (0.55, 0.49), (0.43, 0.545), (0.35, 0.57), (0.345, 0.60),
               (0.36, 0.625), (0.36, 0.665), (0.0, 0.665)])


def build_globe(bm):
    # blown glass chimney, open at both ends where collar and cap clamp it
    lathe(bm, [(0.30, 0.655), (0.34, 0.70), (0.42, 0.80), (0.49, 0.92), (0.52, 1.06),
               (0.51, 1.18), (0.46, 1.30), (0.37, 1.40), (0.29, 1.47), (0.26, 1.52),
               (0.26, 1.56)])


def build_guard(bm):
    # four bowed guard wires plus a belt ring and a seat ring, all iron
    z0, z1 = 0.66, 1.55
    for k in range(4):
        a = math.radians(45 + 90 * k)
        pts = []
        for i in range(17):
            z = z0 + (z1 - z0) * i / 16
            r = 0.36 + 0.24 * math.sin(math.pi * (z - z0) / (z1 - z0))
            pts.append((r * math.cos(a), r * math.sin(a), z))
        tube(bm, pts, 0.02)
    torus(bm, 0.595, 0.018, 1.10)
    torus(bm, 0.37, 0.022, 0.655)


def build_tubes(bm):
    # the hurricane side air tubes: fount shoulder -> up past the globe -> cap
    for s in (-1.0, 1.0):
        pts = [(s * 0.66, 0.0, 0.26), (s * 0.70, 0.0, 0.36), (s * 0.705, 0.0, 0.50)]
        pts += [(s * 0.705, 0.0, 0.50 + 1.0 * i / 8) for i in range(1, 9)]
        for i in range(1, 7):
            t = math.radians(90 * i / 6)
            pts.append((s * (0.705 - 0.36 * math.sin(t)), 0.0,
                        1.50 + 0.12 * (1 - math.cos(t)) + 0.06 * math.sin(t)))
        pts.append((s * 0.28, 0.0, 1.69))
        tube(bm, pts, 0.042, sides=12)
        # pivot boss where the bail hooks in
        vs = lathe(bm, [(0.0, 0.0), (0.05, 0.0), (0.055, 0.02), (0.05, 0.05),
                        (0.03, 0.06), (0.0, 0.06)], segs=16)
        aligned(bm, vs, (s, 0.0, 0.0), (s * 0.70, 0.0, BAIL_Z0))


def build_cap(bm):
    # vented bell cap with a chimney stack and a rolled rim
    lathe(bm, [(0.0, 1.50), (0.30, 1.50), (0.36, 1.515), (0.375, 1.55), (0.35, 1.585),
               (0.30, 1.645), (0.23, 1.715), (0.16, 1.755), (0.14, 1.775),
               (0.14, 1.84), (0.185, 1.855), (0.20, 1.885), (0.18, 1.915),
               (0.0, 1.925)])


def build_bail(bm):
    # wire bail arc, pivoting on the tube bosses, plus the wooden grip
    pts = []
    for i in range(33):
        t = math.pi * i / 32
        pts.append((BAIL_X * math.cos(t), 0.0, BAIL_Z0 + BAIL_H * math.sin(t)))
    tube(bm, pts, 0.026)
    prof = [(0.0, -GRIP_HALF), (0.045, -GRIP_HALF), (0.058, -GRIP_HALF + 0.012),
            (0.063, -0.13), (GRIP_R, -0.10), (0.058, -0.075), (GRIP_R, -0.05),
            (GRIP_R, 0.05), (0.058, 0.075), (GRIP_R, 0.10), (0.063, 0.13),
            (0.058, GRIP_HALF - 0.012), (0.045, GRIP_HALF), (0.0, GRIP_HALF)]
    vs = lathe(bm, prof, segs=SEGS, mat=1)
    aligned(bm, vs, (1.0, 0.0, 0.0), (0.0, 0.0, GRIP_CZ))


def build_brasswork(bm):
    yaw = math.radians(-90 - CAM_YAW + 12)
    d = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    # wick-raiser knob on the burner collar, facing the camera
    knurl = [(0.0, 0.0), (0.024, 0.0), (0.024, 0.14), (0.05, 0.145), (0.07, 0.155)]
    knurl += [(0.075 if k % 2 == 0 else 0.068, 0.16 + 0.004 * k) for k in range(8)]
    knurl += [(0.07, 0.195), (0.05, 0.205), (0.0, 0.205)]
    vs = lathe(bm, knurl, segs=24)
    aligned(bm, vs, d, d * 0.30 + Vector((0.0, 0.0, 0.60)))
    # filler cap on the fount shoulder
    f = Vector((math.cos(yaw - 1.3), math.sin(yaw - 1.3), 0.0))
    vs = lathe(bm, [(0.0, -0.02), (0.085, -0.02), (0.09, 0.03), (0.08, 0.05),
                    (0.05, 0.06), (0.045, 0.085), (0.02, 0.095), (0.0, 0.095)], segs=24)
    aligned(bm, vs, (0, 0, 1), f * 0.50 + Vector((0.0, 0.0, 0.47)))


BUILDERS = {
    "Fount": (build_fount, ("Paint",)),
    "Globe": (build_globe, ("Glass",)),
    "Guard": (build_guard, ("Iron",)),
    "Tubes": (build_tubes, ("Paint",)),
    "Cap": (build_cap, ("Paint",)),
    "Bail": (build_bail, ("Iron", "Wood")),
    "Brasswork": (build_brasswork, ("Brass",)),
}


def make_material(key):
    spec = {
        "Paint": dict(base=(0.36, 0.022, 0.014), rough=0.40, noise=(9.0, 0.30)),
        "Glass": dict(base=(0.12, 0.04, 0.01), rough=0.06,
                      emit=(1.0, 0.31, 0.035), strength=(1.2, 0.06)),
        "Iron": dict(base=(0.075, 0.075, 0.08), rough=0.48, metal=0.85, noise=(22.0, 0.45)),
        "Brass": dict(base=(0.78, 0.52, 0.18), rough=0.30, metal=1.0, noise=(30.0, 0.20)),
        "Wood": dict(base=(0.34, 0.15, 0.06), rough=0.62, noise=(40.0, 0.40)),
    }[key]
    mat = bpy.data.materials.new(f"Lantern.{key}")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = spec["base"] + (1.0,)
    b.inputs["Roughness"].default_value = spec["rough"]
    b.inputs["Metallic"].default_value = spec.get("metal", 0.0)
    if "emit" in spec:
        b.inputs["Emission Color"].default_value = spec["emit"] + (1.0,)
        # hot where the globe faces the eye, cooling to deep amber at the
        # silhouette, so the glass reads as a lit volume, not a flat disc
        core, rim = spec["strength"]
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.20
        emap = nt.nodes.new("ShaderNodeMapRange")
        emap.inputs["To Min"].default_value = core
        emap.inputs["To Max"].default_value = rim
        emap.inputs["From Max"].default_value = 0.55
        nt.links.new(lw.outputs["Facing"], emap.inputs["Value"])
        nt.links.new(emap.outputs["Result"], b.inputs["Emission Strength"])
    if "noise" in spec:
        # wear: noise-mottled base color and roughness, never a flat slot
        scale, amount = spec["noise"]
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 6.0
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[1].position = 0.70
        base = spec["base"]
        ramp.color_ramp.elements[0].color = tuple(c * (1 - amount) for c in base) + (1.0,)
        ramp.color_ramp.elements[1].color = tuple(min(1.0, c * (1 + amount)) for c in base) + (1.0,)
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
        rmap = nt.nodes.new("ShaderNodeMapRange")
        rmap.inputs["To Min"].default_value = spec["rough"] - 0.10
        rmap.inputs["To Max"].default_value = spec["rough"] + 0.15
        nt.links.new(noise.outputs["Fac"], rmap.inputs["Value"])
        nt.links.new(rmap.outputs["Result"], b.inputs["Roughness"])
    return mat


def build_parts(prefix="Lantern", mats=None, collection=None):
    """Seven part objects, each with its own mesh, materials and transform.

    Geometry is authored in lantern space and then re-centred on the part's
    own pivot (its bounds centre), so the join has real transforms to apply.
    """
    if mats is None:
        mats = {k: make_material(k) for k in MATERIALS}
    collection = collection or bpy.context.collection
    objs = []
    for name in PARTS:
        fn, keys = BUILDERS[name]
        me = bpy.data.meshes.new(f"{prefix}.{name}")
        bm = bmesh.new()
        try:
            fn(bm)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
            lo = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
            hi = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
            pivot = (lo + hi) / 2
            if name == PARTS[0]:
                pivot = Vector((0.0, 0.0, 0.0))  # the target keeps the floor origin
            bmesh.ops.translate(bm, vec=-pivot, verts=bm.verts)
            # machined profile corners stay crisp under smooth shading
            bm.normal_update()
            for e in bm.edges:
                if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(32):
                    e.smooth = False
            bm.to_mesh(me)
        finally:
            bm.free()
        for k in keys:
            me.materials.append(mats[k])
        # target is named for what it becomes; sources for what they are
        obj = bpy.data.objects.new(prefix if name == PARTS[0] else f"{prefix}.{name}", me)
        obj.location = pivot
        collection.objects.link(obj)
        objs.append(obj)
    return objs


def material_faces(objs):
    """Faces owned by each material name, across the given mesh objects."""
    c = Counter()
    for o in objs:
        slots = o.data.materials
        for p in o.data.polygons:
            c[slots[p.material_index].name] += 1
    return c


# ------------------------------------------------------------------ contract

def join_with_temp_override(target, sources):
    """The contract this example witnesses: temp_override, not context.copy().

    The override alone fabricates the whole operator context — no select_set,
    no view_layer.objects.active. That is the point: the scene's real
    selection state stays untouched."""
    with bpy.context.temp_override(
        active_object=target,
        selected_objects=[target, *sources],
        selected_editable_objects=[target, *sources],
    ):
        bpy.ops.object.join()
    return target


def check(joined, source_names, expect):
    mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH']
    if len(mesh_objs) != 1:
        print(f"ERROR: expected 1 mesh object after join, got {len(mesh_objs)}",
              file=sys.stderr)
        return 3
    if mesh_objs[0] is not joined:
        print("ERROR: joined target is not the sole remaining mesh object",
              file=sys.stderr)
        return 4

    got_v = len(joined.data.vertices)
    got_f = len(joined.data.polygons)
    if got_v != expect["verts"] or got_f != expect["faces"]:
        print(f"ERROR: topology verts={got_v} faces={got_f} != "
              f"sum over parts verts={expect['verts']} faces={expect['faces']}",
              file=sys.stderr)
        return 5

    still_alive = [n for n in source_names if n in bpy.data.objects]
    if still_alive:
        print(f"ERROR: source objects still present after join: {still_alive}",
              file=sys.stderr)
        return 6

    # Z span proves the part transforms were applied: the target alone stops
    # at the collar, and an unapplied pivot would drop the grip to the floor
    zs = [v.co.z for v in joined.data.vertices]
    z_lo, z_hi = min(zs), max(zs)
    if abs(z_lo - EXPECT_Z_LO) > 1e-4 or abs(z_hi - EXPECT_Z_HI) > 1e-4:
        print(f"ERROR: local z [{z_lo:.4f}, {z_hi:.4f}] != "
              f"[{EXPECT_Z_LO:.4f}, {EXPECT_Z_HI:.4f}] — join did not place every part",
              file=sys.stderr)
        return 7

    # slots merged: each distinct part material exactly once, nothing else
    slots = [m.name if m else None for m in joined.data.materials]
    want = sorted(f"Lantern.{k}" for k in MATERIALS)
    if sorted(slots) != want:
        print(f"ERROR: joined material slots {slots} != one slot per part "
              f"material {want}", file=sys.stderr)
        return 8

    # ... and every material still owns exactly the faces its parts brought
    got_mf = material_faces([joined])
    if got_mf != expect["mat_faces"]:
        print(f"ERROR: faces per material {dict(got_mf)} != "
              f"{dict(expect['mat_faces'])} — slot indices were not remapped",
              file=sys.stderr)
        return 9

    print(f"parts={len(PARTS)} verts={got_v} faces={got_f} "
          f"z={z_lo:.3f}..{z_hi:.3f} slots={len(slots)} "
          f"faces/material={dict(sorted(got_mf.items()))} override=temp_override")
    return 0


# ------------------------------------------------------------------ render

def eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'


def render_still(lantern, path, engine):
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
    wall.location = (0.0, 7.5, 0.0)
    wall.rotation_euler = (math.radians(90), 0.0, 0.0)
    scene.collection.objects.link(wall)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.021, 0.025, 1.0)
    scene.world = world

    def light(name, kind, loc, energy, col, at=(0.0, 0.0, 1.1), size=1.0):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = col
        if kind == 'AREA':
            ld.size = size
        else:
            ld.shadow_soft_size = size
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = (Vector(at) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(ob)
        return ld

    # shaped warm key, faint cool fill, cool rim, warm wedge raking the back
    # wall right behind the lantern as the camera sees it (docs/VISUAL-STYLE.md)
    light("Key", 'AREA', (-4.0, -5.0, 6.0), 480.0, (1.0, 0.96, 0.9), size=4.5)
    light("Fill", 'AREA', (5.0, -4.0, 3.0), 90.0, (0.75, 0.85, 1.0), size=9.0)
    light("Rim", 'AREA', (-1.6, 3.4, 6.0), 260.0, (0.6, 0.78, 1.0), at=(0.0, 0.0, 1.9), size=4.0)
    light("Wedge", 'AREA', (-1.2, 4.8, 4.4), 420.0, (1.0, 0.76, 0.5),
          at=(-4.2, 7.5, 1.6), size=6.0)
    # the lit wick: a shadowless warm point inside the globe, so the flame
    # throws its glow onto the fount, the guard wires and the floor
    flame = light("Flame", 'POINT', (0.0, 0.0, 1.0), 60.0, (1.0, 0.55, 0.2), size=0.08)
    flame.use_shadow = False

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    yaw = math.radians(CAM_YAW)
    dist = 7.3
    cam.location = (dist * math.sin(yaw), -dist * math.cos(yaw), 2.7)
    scene.collection.objects.link(cam)
    aim = bpy.data.objects.new("Aim", None)
    aim.location = (0.0, 0.0, 1.13)
    scene.collection.objects.link(aim)
    con = cam.constraints.new('TRACK_TO')
    con.target = aim
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
    # AgX would wash the red enamel and the amber glass toward pastel
    # (docs/VISUAL-STYLE.md)
    scene.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()
    # Layer 1 gates before the beauty render, so a defective composition
    # ships no artifact: framing (exit 10) and asset-quality floors (exit 11)
    fcode = gallery_framing.check_framing(scene, cam, hero=[lantern],
                                          elements=[lantern], stage=[floor, wall])
    if fcode:
        return fcode
    qcode = gallery_asset_quality.check_asset_quality(scene, cam, hero=[lantern],
                                                      stage=[floor, wall])
    if qcode:
        return qcode
    bpy.ops.render.render(write_still=True)
    return 0 if os.path.exists(path) and os.path.getsize(path) > 0 else 12


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render a still PNG here")
    p.add_argument("--engine", default="eevee", choices=("eevee", "cycles"),
                   help="render engine for --output (cycles for GPU-less hosts)")
    p.add_argument("--no-override", action="store_true",
                   help="join without temp_override (must fail)")
    args = p.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    objs = build_parts()
    target, sources = objs[0], objs[1:]
    source_names = [s.name for s in sources]
    expect = {
        "verts": sum(len(o.data.vertices) for o in objs),
        "faces": sum(len(o.data.polygons) for o in objs),
        "mat_faces": material_faces(objs),
    }
    if args.no_override:
        try:
            bpy.ops.object.join()
        except RuntimeError as exc:
            print(f"join without override: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
        joined = target
    else:
        joined = join_with_temp_override(target, sources)
    code = check(joined, source_names, expect)
    if code:
        return code

    if args.output:
        rcode = render_still(joined, os.path.abspath(args.output), args.engine)
        if rcode == 12:
            print("ERROR: render produced no file", file=sys.stderr)
        if rcode:
            return rcode
        print(f"rendered still {args.output}")

    print("temp-override-join OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); print(f"FATAL: {e}", file=sys.stderr); sys.exit(1)
