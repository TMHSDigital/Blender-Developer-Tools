"""Slotted-actions turntable -- a runnable BDT example.

Keyframes a Z-rotation turntable through the slotted-actions cross-version channelbag path
(`get_channelbag_for_slot`) and selects the engine with the version-branch EEVEE-id helper.
It witnesses the slotted-actions fix: on Blender 5.x the channelbag comes from
`action_ensure_channelbag_for_slot`; on 4.4/4.5 from `strip.channelbag(slot, ensure=True)`.

By default it runs only the cheap, frame-independent correctness check (no render): insert
the rotation keys, sample the object's Z rotation at frame 1 vs a later frame, and assert
they DIFFER -- proving the keys drive playback. Exits non-zero on failure. This is the check
the CI smoke gate runs on both builds.

``--no-keys`` skips inserting the rotation keys and still asserts they drive playback.
That is the falsifier (``--same-axis`` in export-preset-axis). The EEVEE-id
era check is untouched.

    blender --background --python turntable.py --                 # correctness check only
    blender --background --python turntable.py -- --no-keys       # must fail
    blender --background --python turntable.py -- --output t.png  # also render one still
    blender --background --python turntable.py -- --output t.png --engine cycles  # GPU-less
"""
import bpy, sys, os, math, argparse
from mathutils import Vector

# Shared Layer 1 framing measurement (render path only) — see
# gallery_framing.py for the __file__-relative import shim this relies on.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
import gallery_framing  # noqa: E402

FRAMES = 36

def get_eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'

def get_channelbag_for_slot(action, slot):
    if bpy.app.version >= (5, 0, 0):
        from bpy_extras.anim_utils import action_ensure_channelbag_for_slot
        return action_ensure_channelbag_for_slot(action, slot)
    layer = action.layers[0] if action.layers else action.layers.new("Layer")
    strip = layer.strips[0] if layer.strips else layer.strips.new(type='KEYFRAME')
    return strip.channelbag(slot, ensure=True)

def build(no_keys=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 1.0))
    obj = bpy.context.active_object
    obj.data.shade_smooth()
    mat = bpy.data.materials.new("M"); mat.use_nodes = True
    b = mat.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (0.85, 0.35, 0.10, 1)
    b.inputs['Metallic'].default_value = 0.7
    b.inputs['Roughness'].default_value = 0.25
    obj.data.materials.append(mat)
    # rotation keyframes via the slotted-actions channelbag path
    obj.animation_data_create()
    act = bpy.data.actions.new("Turn"); obj.animation_data.action = act
    slot = obj.animation_data.action_slot
    if slot is None:
        slot = act.slots.new(id_type='OBJECT', name=obj.name); obj.animation_data.action_slot = slot
    cbag = get_channelbag_for_slot(act, slot)
    fc = cbag.fcurves.new("rotation_euler", index=2)
    if not no_keys:
        fc.keyframe_points.insert(1, 0.0)
        fc.keyframe_points.insert(FRAMES, math.radians(360))
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
        fc.update()
    return obj

def correctness(obj):
    sc = bpy.context.scene; sc.frame_start = 1; sc.frame_end = FRAMES
    def rz(f):
        sc.frame_set(f); dg = bpy.context.evaluated_depsgraph_get()
        return round(obj.evaluated_get(dg).rotation_euler.z, 4)
    r1, rmid, rend = rz(1), rz(FRAMES // 2), rz(FRAMES)
    branch = '5.0+ ensure-helper' if bpy.app.version >= (5, 0, 0) else '4.4/4.5 strip.channelbag'
    drives = (r1 != rmid != rend) and abs(rend - r1) > 0.5
    print(f"branch={branch} rot_z f1={r1} fmid={rmid} fend={rend} drives={drives}")
    return drives

# Render-only display turntable, sized around the head (Suzanne spans ~2.7 x 1.7).
BASE_R = 1.32          # motor housing radius at its widest
BASE_H = 0.34          # housing top (platter bearing seat)
PLATTER_R = 1.18
PLATTER_Z0 = BASE_H + 0.02
PLATTER_H = 0.07
MAT_R = 1.06           # rubber mat inset into the platter
SEAT = 0.01
TICK_STEP_DEG = 360.0 / FRAMES   # one rim tick per keyed frame: the key span, made visible


def _lathe(bm, profile, segs=96):
    """Revolve an (r, z) profile about Z; r == 0 points become poles."""
    rings = []
    for r, z in profile:
        if r < 1e-9:
            rings.append([bm.verts.new((0.0, 0.0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / segs),
                                        r * math.sin(2 * math.pi * i / segs), z))
                          for i in range(segs)])
    for a, b in zip(rings, rings[1:]):
        for i in range(segs):
            j = (i + 1) % segs
            if len(a) == 1:
                bm.faces.new((a[0], b[j], b[i]))
            elif len(b) == 1:
                bm.faces.new((a[i], a[j], b[0]))
            else:
                bm.faces.new((a[i], a[j], b[j], b[i]))


def _material(name, base, rough, metal=0.0, emit=None, strength=0.0, noise=None):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    nt = mat.node_tree
    pb = nt.nodes['Principled BSDF']
    pb.inputs['Base Color'].default_value = (*base, 1.0)
    pb.inputs['Metallic'].default_value = metal
    pb.inputs['Roughness'].default_value = rough
    if emit is not None:
        pb.inputs['Emission Color'].default_value = (*emit, 1.0)
        pb.inputs['Emission Strength'].default_value = strength
    if noise:
        # brushed / worn: noise-modulated roughness, never a flat slot
        tex = nt.nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = noise
        tex.inputs['Detail'].default_value = 8.0
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['To Min'].default_value = rough - 0.08
        mr.inputs['To Max'].default_value = rough + 0.12
        nt.links.new(tex.outputs['Fac'], mr.inputs['Value'])
        nt.links.new(mr.outputs['Result'], pb.inputs['Roughness'])
    return mat


def _mesh_object(name, build, mats, smooth_angle=35.0):
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        build(bm)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
    finally:
        bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def stage_turntable(obj):
    """Render-only staging, after the check has run: a display turntable.

    A lathed motor housing (stepped foot, vented drum, front status lamp)
    carries a steel platter with an inset rubber mat. Its rim carries one tick
    per keyed frame (FRAMES ticks, 10 degrees apart, a longer tick every 90),
    so the keyed 0..360 span over frames 1..FRAMES reads as a dial, and an
    amber arc arrow on the mat sweeps the direction of the keyed turn. The
    head is smoothed by a subdivision modifier and seated SEAT into the mat.
    Rotation keys and the correctness samples are untouched; only location
    and a modifier change on the checked object.
    """
    import bmesh
    sub = obj.modifiers.new("Smooth", 'SUBSURF')
    sub.levels = 2
    sub.render_levels = 2
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        zmin = min((ev.matrix_world @ v.co).z for v in me.vertices)
    finally:
        ev.to_mesh_clear()
    top = PLATTER_Z0 + PLATTER_H
    obj.location.z += (top - SEAT) - zmin
    b = obj.active_material.node_tree.nodes['Principled BSDF']
    # 0.25 blew every brow and ear edge out to white under the key
    b.inputs['Roughness'].default_value = 0.34
    b.inputs['Base Color'].default_value = (0.80, 0.33, 0.12, 1.0)

    housing = _material("Housing", (0.028, 0.030, 0.034), 0.42, metal=0.6, noise=40.0)
    steel = _material("Steel", (0.34, 0.34, 0.36), 0.40, metal=1.0, noise=90.0)
    rubber = _material("Rubber", (0.012, 0.012, 0.013), 0.78)
    brass = _material("Brass", (0.80, 0.56, 0.24), 0.26, metal=1.0, noise=60.0)
    lamp = _material("Lamp", (0.1, 0.03, 0.0), 0.3, emit=(1.0, 0.45, 0.10), strength=6.0)
    arrow = _material("Arrow", (0.9, 0.45, 0.1), 0.4, emit=(1.0, 0.50, 0.14), strength=2.2)

    def build_housing(bm):
        _lathe(bm, [(0.0, 0.0), (BASE_R, 0.0), (BASE_R, 0.05), (BASE_R - 0.03, 0.07),
                    (BASE_R - 0.08, 0.08), (BASE_R - 0.08, 0.10),
                    # vented drum: shallow grooves around the waist
                    *[(BASE_R - 0.10 - (0.012 if k % 2 else 0.0), 0.12 + 0.02 * k)
                      for k in range(9)],
                    (BASE_R - 0.10, 0.30), (BASE_R - 0.13, 0.33), (0.62, BASE_H),
                    (0.60, BASE_H + 0.02), (0.0, BASE_H + 0.02)])
    housing_ob = _mesh_object("Housing", build_housing, [housing])

    def build_platter(bm):
        z0, z1 = PLATTER_Z0, PLATTER_Z0 + PLATTER_H
        _lathe(bm, [(0.0, z0), (PLATTER_R - 0.02, z0), (PLATTER_R, z0 + 0.015),
                    (PLATTER_R, z1 - 0.015), (PLATTER_R - 0.015, z1),
                    (MAT_R + 0.01, z1), (MAT_R, z1 - 0.006), (0.0, z1 - 0.006)])
    platter_ob = _mesh_object("Platter", build_platter, [steel])

    def build_mat(bm):
        _lathe(bm, [(0.0, top - 0.006), (MAT_R - 0.004, top - 0.006),
                    (MAT_R - 0.004, top), (0.0, top)], segs=96)
    mat_ob = _mesh_object("Mat", build_mat, [rubber])

    def build_ticks(bm):
        for k in range(FRAMES):
            a = math.radians(k * TICK_STEP_DEG)
            major = k % (FRAMES // 4) == 0
            h = 0.058 if major else 0.036
            res = bmesh.ops.create_cube(bm, size=1.0)
            for v in res['verts']:
                v.co.x *= 0.016
                v.co.y *= 0.026 if major else 0.013
                v.co.z *= h
                v.co.x += PLATTER_R + 0.006
                v.co.z += PLATTER_Z0 + PLATTER_H / 2.0
                x, y = v.co.x, v.co.y
                v.co.x = x * math.cos(a) - y * math.sin(a)
                v.co.y = x * math.sin(a) + y * math.cos(a)
    ticks_ob = _mesh_object("Ticks", build_ticks, [brass], smooth_angle=10.0)

    def build_arrow(bm):
        # a quarter-turn arc on the mat edge, counter-clockwise (+Z rotation),
        # ending in a flat arrowhead: the keyed direction of travel
        r, w, z = MAT_R - 0.07, 0.022, top + 0.002
        a0, a1, n = math.radians(-150), math.radians(-75), 24
        prev = None
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            ring = [bm.verts.new(((r + s * w) * math.cos(a), (r + s * w) * math.sin(a), z + dz))
                    for s, dz in ((-1, 0.0), (1, 0.0), (1, 0.008), (-1, 0.008))]
            if prev:
                for k in range(4):
                    bm.faces.new((prev[k], prev[(k + 1) % 4], ring[(k + 1) % 4], ring[k]))
            prev = ring
        tip = a1 + math.radians(9)
        head = [bm.verts.new(((r + s) * math.cos(a1), (r + s) * math.sin(a1), z + dz))
                for s, dz in ((-0.06, 0.0), (0.06, 0.0), (0.06, 0.008), (-0.06, 0.008))]
        pt = [bm.verts.new((r * math.cos(tip), r * math.sin(tip), z)),
              bm.verts.new((r * math.cos(tip), r * math.sin(tip), z + 0.008))]
        bm.faces.new((head[0], head[1], pt[0]))
        bm.faces.new((head[3], pt[1], head[2]))
        bm.faces.new((head[1], head[2], pt[1], pt[0]))
        bm.faces.new((head[0], pt[0], pt[1], head[3]))
        bm.faces.new((head[0], head[3], head[2], head[1]))
    arrow_ob = _mesh_object("Arrow", build_arrow, [arrow], smooth_angle=10.0)

    def build_lamp(bm):
        # a status lamp on the housing front, facing the camera (-Y)
        res = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=0.035)
        for v in res['verts']:
            v.co.y *= 0.6
            v.co += Vector((0.0, -(BASE_R - 0.105), 0.21))
    lamp_ob = _mesh_object("Lamp", build_lamp, [lamp])
    return [housing_ob, platter_ob, mat_ob, ticks_ob, arrow_ob, lamp_ob]


def render_still(obj, path, engine):
    import bmesh
    sc = bpy.context.scene
    parts = stage_turntable(obj)
    fme = bpy.data.meshes.new("Floor"); bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0); bm.to_mesh(fme)
    finally:
        bm.free()
    # dark staged studio: shared floor/wall material, warm shaped key, faint
    # cool fill, cool rim, warm wedge on the back wall (docs/VISUAL-STYLE.md)
    fmat = bpy.data.materials.new("Studio"); fmat.use_nodes = True
    fb = fmat.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.03, 0.032, 0.037, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
    fme.materials.append(fmat)
    floor = bpy.data.objects.new("Floor", fme); bpy.context.collection.objects.link(floor)
    wall = bpy.data.objects.new("Wall", fme.copy()); wall.location = (0, 9.0, 0)
    wall.rotation_euler = (math.radians(90), 0, 0); bpy.context.collection.objects.link(wall)
    w = bpy.data.worlds.new("W"); w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.021, 0.025, 1); sc.world = w
    aim = bpy.data.objects.new("Aim", None); aim.location = (0, 0, 1.05); bpy.context.collection.objects.link(aim)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.location = (0.6, -8.2, 3.2)
    bpy.context.collection.objects.link(cam); sc.camera = cam
    c = cam.constraints.new('TRACK_TO'); c.target = aim; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
    for nm, loc, en, size, col in [("K", (-4, -5, 7), 620, 5.0, (1.0, 0.96, 0.9)),
                                   ("F2", (5, -4, 2), 130, 8.0, (0.75, 0.85, 1.0)),
                                   ("R", (0.5, 4.5, 4.0), 300, 4.0, (0.6, 0.78, 1.0))]:
        ld = bpy.data.lights.new(nm, 'AREA'); ld.energy = en; ld.size = size; ld.color = col
        lo = bpy.data.objects.new(nm, ld); lo.location = loc; bpy.context.collection.objects.link(lo)
        lc = lo.constraints.new('TRACK_TO'); lc.target = aim; lc.track_axis = 'TRACK_NEGATIVE_Z'; lc.up_axis = 'UP_Y'
    wd = bpy.data.lights.new("Wedge", 'AREA'); wd.energy = 380; wd.size = 6.0; wd.color = (1.0, 0.76, 0.5)
    wo = bpy.data.objects.new("Wedge", wd); wo.location = (2.5, 5.5, 4.0)
    wo.rotation_euler = (math.radians(-68), 0, math.radians(190)); bpy.context.collection.objects.link(wo)
    sc.render.engine = 'CYCLES' if engine == 'cycles' else get_eevee_engine_id()
    if sc.render.engine == 'CYCLES':
        try: sc.cycles.samples = 48
        except Exception: pass
    else:
        try: sc.eevee.taa_render_samples = 64
        except Exception: pass
    # pin the still to a deliberate pose: frame 4 is ~31 degrees of turn, a
    # three-quarter view where ears and brow read instantly as Suzanne. An
    # arbitrary turntable frame can land face-away and read as broken geometry.
    sc.frame_set(4)
    sc.render.resolution_x = 1280; sc.render.resolution_y = 720
    # Blender resolves a relative filepath against the blend-file directory, which
    # for a --background run with no .blend is the drive root, not the cwd.
    path = os.path.abspath(path)
    sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = path
    # AgX would wash the copper toward beige (docs/VISUAL-STYLE.md)
    sc.view_settings.view_transform = 'Standard'
    bpy.context.view_layer.update()
    # Layer 1 framing gate before the beauty render (exit 10 on violation)
    fcode = gallery_framing.check_framing(sc, cam, hero=[obj] + parts,
                                          elements=[obj] + parts, stage=[floor, wall])
    if fcode:
        return fcode
    bpy.ops.render.render(write_still=True)
    return 0 if os.path.exists(path) and os.path.getsize(path) > 0 else 4

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render one still to this PNG")
    p.add_argument("--engine", choices=["auto", "cycles"], default="auto")
    p.add_argument("--no-keys", action="store_true",
                   help="falsifier: skip rotation keys, still assert they drive playback")
    args = p.parse_args(argv)

    # the EEVEE-id mapping is asserted regardless of whether we render: the
    # OTHER era's id must be rejected by this build, the helper's accepted
    eid = get_eevee_engine_id()
    wrong = 'BLENDER_EEVEE_NEXT' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE'  # engine-id-exempt: the wrong-era id this example asserts is rejected
    try:
        bpy.context.scene.render.engine = wrong
        print(f"ERROR: wrong-era EEVEE id '{wrong}' was accepted", file=sys.stderr); return 5
    except TypeError:
        pass  # correctly rejected
    bpy.context.scene.render.engine = eid  # raises TypeError if the helper's id is invalid

    obj = build(no_keys=args.no_keys)
    if not correctness(obj):
        print("ERROR: rotation keys do not drive playback", file=sys.stderr); return 3

    if args.output:
        rcode = render_still(obj, args.output, args.engine)
        if rcode:
            if rcode == 4:
                print("ERROR: still render produced no file", file=sys.stderr)
            return rcode
        print(f"rendered still {args.output} ({os.path.getsize(args.output)} bytes)")
    print("turntable OK")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        import traceback; traceback.print_exc()
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr); sys.exit(1)
