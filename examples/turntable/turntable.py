"""Slotted-actions turntable -- a runnable BDT example.

Keyframes a Z-rotation turntable through the slotted-actions cross-version channelbag path
(`get_channelbag_for_slot`) and selects the engine with the version-branch EEVEE-id helper.
It witnesses the slotted-actions fix: on Blender 5.x the channelbag comes from
`action_ensure_channelbag_for_slot`; on 4.4/4.5 from `strip.channelbag(slot, ensure=True)`.

By default it runs only the cheap, frame-independent correctness check (no render): insert
the rotation keys, sample the object's Z rotation at frame 1 vs a later frame, and assert
they DIFFER -- proving the keys drive playback. Exits non-zero on failure. This is the check
the CI smoke gate runs on both builds.

    blender --background --python turntable.py --                 # correctness check only
    blender --background --python turntable.py -- --output t.png  # also render one still
    blender --background --python turntable.py -- --output t.png --engine cycles  # GPU-less
"""
import bpy, sys, os, math, argparse

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

def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 1.0))
    obj = bpy.context.active_object
    for p in obj.data.polygons:
        p.use_smooth = True
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

def render_still(obj, path, engine):
    import bmesh
    sc = bpy.context.scene
    fme = bpy.data.meshes.new("Floor"); bm = bmesh.new()
    try:
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0); bm.to_mesh(fme)
    finally:
        bm.free()
    floor = bpy.data.objects.new("Floor", fme); bpy.context.collection.objects.link(floor)
    w = bpy.data.worlds.new("W"); w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.04, 0.05, 0.07, 1); sc.world = w
    aim = bpy.data.objects.new("Aim", None); aim.location = (0, 0, 1.0); bpy.context.collection.objects.link(aim)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.location = (0, -7, 3.0)
    bpy.context.collection.objects.link(cam); sc.camera = cam
    c = cam.constraints.new('TRACK_TO'); c.target = aim; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
    for nm, loc, en in [("K", (-4, -5, 7), 900), ("F2", (5, -4, 2), 350)]:
        ld = bpy.data.lights.new(nm, 'AREA'); ld.energy = en; ld.size = 5.0
        lo = bpy.data.objects.new(nm, ld); lo.location = loc; bpy.context.collection.objects.link(lo)
        lc = lo.constraints.new('TRACK_TO'); lc.target = aim; lc.track_axis = 'TRACK_NEGATIVE_Z'; lc.up_axis = 'UP_Y'
    sc.render.engine = 'CYCLES' if engine == 'cycles' else get_eevee_engine_id()
    if sc.render.engine == 'CYCLES':
        try: sc.cycles.samples = 16
        except Exception: pass
    else:
        try: sc.eevee.taa_render_samples = 16
        except Exception: pass
    sc.frame_set(FRAMES // 4)
    sc.render.resolution_x = 1280; sc.render.resolution_y = 720
    sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return os.path.exists(path) and os.path.getsize(path) > 0

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None, help="optional: render one still to this PNG")
    p.add_argument("--engine", choices=["auto", "cycles"], default="auto")
    args = p.parse_args(argv)

    # the EEVEE-id mapping is asserted regardless of whether we render: the
    # OTHER era's id must be rejected by this build, the helper's accepted
    eid = get_eevee_engine_id()
    wrong = 'BLENDER_EEVEE_NEXT' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE'
    try:
        bpy.context.scene.render.engine = wrong
        print(f"ERROR: wrong-era EEVEE id '{wrong}' was accepted", file=sys.stderr); return 5
    except TypeError:
        pass  # correctly rejected
    bpy.context.scene.render.engine = eid  # raises TypeError if the helper's id is invalid

    obj = build()
    if not correctness(obj):
        print("ERROR: rotation keys do not drive playback", file=sys.stderr); return 3

    if args.output:
        if not render_still(obj, args.output, args.engine):
            print("ERROR: still render produced no file", file=sys.stderr); return 4
        print(f"rendered still {args.output} ({os.path.getsize(args.output)} bytes)")
    print("turntable OK")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        import traceback; traceback.print_exc()
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr); sys.exit(1)
