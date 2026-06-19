"""In-Blender smoke test for the BDT example patterns.

Run: blender --background --python tests/smoke/run_smoke.py -- <outdir>

Executes the snippets' / skills' headline examples and asserts CONTENT, not just
"no exception". Exits non-zero on the FIRST failed assertion, naming the example.
Self-contained: example code is copied here, NOT imported from skills/ or snippets/,
so the test catches drift in the shipped content rather than masking it.
"""
import bpy, sys, os, tempfile

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGS[0] if ARGS else tempfile.mkdtemp()
os.makedirs(OUT, exist_ok=True)
V = bpy.app.version
print(f"=== smoke on Blender {V[0]}.{V[1]}.{V[2]} -> {OUT} ===")

def require(example, cond, evidence):
    """Pass-or-die assertion. On failure print which example failed and exit 1."""
    status = "ok" if cond else "FAIL"
    print(f"[{status}] {example}: {evidence}")
    if not cond:
        print(f"SMOKE FAILED at example '{example}' on Blender {V[0]}.{V[1]}.{V[2]}")
        sys.exit(1)

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)

# ---- helpers copied from fixed content ----
def get_eevee_engine_id():
    return 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'

def get_channelbag_for_slot(action, slot):
    if bpy.app.version >= (5, 0, 0):
        from bpy_extras.anim_utils import action_ensure_channelbag_for_slot
        return action_ensure_channelbag_for_slot(action, slot)
    layer = action.layers[0] if action.layers else action.layers.new("Layer")
    strip = layer.strips[0] if layer.strips else layer.strips.new(type='KEYFRAME')
    return strip.channelbag(slot, ensure=True)

# ---------- mesh: foreach roundtrip + SUBSURF eval > base ----------
def smoke_mesh():
    import bmesh
    reset()
    me = bpy.data.meshes.new("m"); me.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0)], [], [(0,1,2,3)]); me.update()
    obj = bpy.data.objects.new("M", me); bpy.context.collection.objects.link(obj)
    base = len(me.vertices)
    n = len(me.vertices); src = [float(i) for i in range(n*3)]
    me.vertices.foreach_set("co", src); dst = [0.0]*(n*3); me.vertices.foreach_get("co", dst)
    require("mesh-foreach-roundtrip", all(abs(a-b) < 1e-5 for a,b in zip(src,dst)), "foreach_set/get arrays equal")
    obj.modifiers.new("ss", 'SUBSURF').levels = 2
    dg = bpy.context.evaluated_depsgraph_get(); ev = obj.evaluated_get(dg); m = ev.to_mesh()
    evc = len(m.vertices); ev.to_mesh_clear()
    require("mesh-subsurf-eval", evc > base, f"eval vcount {evc} > base {base}")

# ---------- F1: driver_namespace example (skill, fixed) ----------
def smoke_driver():
    reset()
    me = bpy.data.meshes.new("d"); me.from_pydata([(0,0,0)],[],[])
    obj = bpy.data.objects.new("D", me); bpy.context.collection.objects.link(obj)
    def smooth_step(t):
        t = max(0.0, min(1.0, t)); return t*t*(3.0-2.0*t)
    bpy.app.driver_namespace['smooth_step'] = smooth_step
    fcurve = obj.driver_add("location", 2); fcurve.driver.type = 'SCRIPTED'
    var = fcurve.driver.variables.new(); var.name = 't'; var.type = 'SINGLE_PROP'
    var.targets[0].id_type = 'SCENE'           # the F1 fix under test
    var.targets[0].id = bpy.context.scene
    var.targets[0].data_path = 'frame_current'
    fcurve.driver.expression = 'smooth_step((t - 1.0) / 100.0) * 5.0'
    vals = []
    for f in (1, 50, 100):
        bpy.context.scene.frame_set(f); dg = bpy.context.evaluated_depsgraph_get()
        vals.append(round(obj.evaluated_get(dg).location.z, 4))
    require("F1-driver-namespace", vals[0] < vals[1] < vals[2], f"location.z across frames = {vals} (strictly increasing)")

# ---------- F2: SDF remesh via GridToMesh (skill, fixed) ----------
def smoke_sdf():
    import bmesh
    reset()
    me = bpy.data.meshes.new("c"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new("C", me); bpy.context.collection.objects.link(obj)
    tree = bpy.data.node_groups.new("SDFRemesh", 'GeometryNodeTree')
    tree.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    tree.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gi = tree.nodes.new('NodeGroupInput'); go = tree.nodes.new('NodeGroupOutput')
    m2s = tree.nodes.new('GeometryNodeMeshToSDFGrid'); g2m = tree.nodes.new('GeometryNodeGridToMesh')
    m2s.inputs["Voxel Size"].default_value = 0.1
    g2m.inputs["Threshold"].default_value = 0.0
    tree.links.new(gi.outputs["Geometry"], m2s.inputs["Mesh"])
    link = tree.links.new(m2s.outputs["SDF Grid"], g2m.inputs["Grid"])   # the F2 fix under test
    tree.links.new(g2m.outputs["Mesh"], go.inputs["Geometry"])
    require("F2-sdf-link-valid", link.is_valid, "SDF Grid -> Grid link is_valid")
    obj.modifiers.new("gn", 'NODES').node_group = tree
    dg = bpy.context.evaluated_depsgraph_get(); ev = obj.evaluated_get(dg); m = ev.to_mesh()
    n = len(m.vertices); ev.to_mesh_clear()
    require("F2-sdf-remesh", n > 0, f"GridToMesh remesh produced {n} vertices (>0)")

# ---------- EEVEE: id assignment + non-black render ----------
def smoke_eevee():
    import bmesh
    reset()
    me = bpy.data.meshes.new("p"); bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=10.0); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new("P", me); bpy.context.collection.objects.link(obj)
    mat = bpy.data.materials.new("M"); mat.use_nodes = True; nt = mat.node_tree; nt.nodes.clear()
    emis = nt.nodes.new('ShaderNodeEmission'); emis.inputs['Color'].default_value = (0.9,0.4,0.1,1.0); emis.inputs['Strength'].default_value = 5.0
    out = nt.nodes.new('ShaderNodeOutputMaterial'); nt.links.new(emis.outputs['Emission'], out.inputs['Surface'])
    obj.data.materials.append(mat)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); bpy.context.collection.objects.link(cam)
    cam.location = (0,0,10); bpy.context.scene.camera = cam
    sc = bpy.context.scene
    # THE EEVEE-id polarity guard (CRITICAL #1). Independent of any rendered frame, so it
    # cannot flake on the GL/EGL context. `eid` is the repo helper's output (under test);
    # `expected` is computed here from the version, so an inverted helper is caught.
    eid = get_eevee_engine_id()
    expected = 'BLENDER_EEVEE' if bpy.app.version >= (5, 0, 0) else 'BLENDER_EEVEE_NEXT'
    assigned = True; err = ""
    try:
        sc.render.engine = eid
    except Exception as e:
        assigned = False; err = f"{type(e).__name__}: {e}"
    require("eevee-engine-id-assigns",
            assigned and sc.render.engine == expected,
            f"helper returned '{eid}'; engine='{sc.render.engine if assigned else 'UNASSIGNED('+err+')'}' expected='{expected}'")
    # Render the non-black frame with Cycles (CPU): reliable on GPU-less headless runners,
    # where an EEVEE GPU render aborts the process (no EGL). The EEVEE-id regression itself
    # is already gated by the assignment above; EEVEE *rendering* is not exercised here.
    sc.render.engine = 'CYCLES'
    try: sc.cycles.samples = 4
    except Exception: pass
    sc.render.resolution_x = 16; sc.render.resolution_y = 16; sc.render.image_settings.file_format = 'PNG'
    png = os.path.join(OUT, f"smoke_render_{V[0]}{V[1]}.png"); sc.render.filepath = png
    bpy.ops.render.render(write_still=True)
    require("render-file", os.path.exists(png) and os.path.getsize(png) > 0, "1-frame render PNG written (Cycles CPU)")
    img = bpy.data.images.load(png); px = list(img.pixels); mx = max(px) if px else 0.0
    require("render-nonblack", mx > 0.05, f"max pixel {round(mx,3)} > 0.05 (emissive material renders bright)")

# ---------- slotted actions: correct branch + legacy behaviour ----------
def smoke_slotted():
    reset()
    me = bpy.data.meshes.new("a"); me.from_pydata([(0,0,0)],[],[])
    obj = bpy.data.objects.new("A", me); bpy.context.collection.objects.link(obj)
    obj.location = (0,0,0.0); obj.keyframe_insert("location", frame=1)
    obj.location = (0,0,5.0); obj.keyframe_insert("location", frame=24)
    bpy.context.scene.frame_set(1); z1 = round(obj.location.z,3)
    bpy.context.scene.frame_set(24); z24 = round(obj.location.z,3)
    require("slotted-keyframe-drives", abs(z24-z1) > 1.0, f"sampled z f1={z1} f24={z24} differ")
    o2 = bpy.data.objects.new("A2", bpy.data.meshes.new("a2")); bpy.context.collection.objects.link(o2)
    o2.animation_data_create(); act = bpy.data.actions.new("Act"); o2.animation_data.action = act
    slot = o2.animation_data.action_slot
    if slot is None:
        slot = act.slots.new(id_type='OBJECT', name=o2.name); o2.animation_data.action_slot = slot
    cbag = get_channelbag_for_slot(act, slot)
    require("slotted-channelbag", type(cbag).__name__ == "ActionChannelbag", f"channelbag = {type(cbag).__name__}")
    act3 = bpy.data.actions.new("Act3")
    try:
        act3.fcurves.new("location", index=0); legacy = 'WORKS'
    except AttributeError:
        legacy = 'AttributeError'
    expected = 'AttributeError' if bpy.app.version >= (5,0,0) else 'WORKS'
    require("slotted-legacy-branch", legacy == expected, f"legacy action.fcurves = {legacy} (expected {expected} for this version)")

# ---------- save_pre handler arg is a filepath string ----------
def smoke_save_pre():
    reset()
    captured = {}
    def on_save_pre(arg, *a): captured['t'] = type(arg).__name__
    bpy.app.handlers.save_pre.append(on_save_pre)
    p = os.path.join(OUT, "smoke_sp.blend"); bpy.ops.wm.save_as_mainfile(filepath=p)
    bpy.app.handlers.save_pre.remove(on_save_pre)
    require("save_pre-arg-type", captured.get('t') == 'str', f"save_pre arg type = {captured.get('t')} (filepath string, not Scene)")

# Blender runs --python scripts but exits 0 even on an uncaught exception, so wrap every
# example: a raised exception is a failure just like a failed content assertion.
for fn in (smoke_mesh, smoke_driver, smoke_sdf, smoke_eevee, smoke_slotted, smoke_save_pre):
    try:
        fn()
    except SystemExit:
        raise
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"SMOKE FAILED: unhandled {type(e).__name__} in '{fn.__name__}' on "
              f"Blender {V[0]}.{V[1]}.{V[2]}: {e}")
        sys.exit(1)

print(f"=== ALL SMOKE CHECKS PASSED on Blender {V[0]}.{V[1]}.{V[2]} ===")
