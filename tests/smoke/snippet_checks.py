"""What tests/smoke/run_content.py asserts about each shipped snippet (#447).

One entry per file in snippets/. Each snippet is exec'd in place (its own
source, never a copy) in a fresh factory-startup scene: the default Cube is
active and selected, with a Camera and a Light. Then:

- ``setup``   runs before the snippet (optional)
- ``check``   runs in the snippet's namespace after it; it calls the snippet's
              functions and asserts one observable fact. Helpers in scope:
              ``bpy``, ``np``, ``tmp(name)`` (a path in a scratch dir) and
              ``glb_json(path)`` (the JSON chunk of a .glb as a dict).
- ``falsify`` (old, new): replace every ``old`` in the snippet source with
              ``new``, rerun, and require the check to FAIL. It is the
              per-snippet falsifier, same contract as the example catalog:
              an assertion that cannot fail witnesses nothing. Several of
              them reintroduce a bug the snippet once shipped with.

tests/check_content_catalog.py (Validate, no Blender) requires an entry for
every snippet and that each ``old`` string occurs in its snippet.
"""

GLB_CUBE_AT_Z2 = """
cube = bpy.data.objects["Cube"]
cube.location = (0.0, 0.0, 2.0)
for o in bpy.context.selected_objects:
    o.select_set(False)
cube.select_set(True)
bpy.context.view_layer.objects.active = cube
"""

GLB_Y_UP = """
node = next(n for n in doc["nodes"] if n.get("name") == "Cube")
t = node.get("translation", [0, 0, 0])
assert abs(t[0]) < 1e-4 and abs(t[1] - 2.0) < 1e-4 and abs(t[2]) < 1e-4, t
"""

CASES = {
    "action-ensure-channelbag-for-slot.py": dict(
        check="""
obj = bpy.context.active_object
add_z_keyframe(obj, frame=1, value=0.0)
add_z_keyframe(obj, frame=24, value=2.0)
scene = bpy.context.scene
scene.frame_set(24)
assert abs(obj.location.z - 2.0) < 1e-4, obj.location.z
scene.frame_set(1)
assert abs(obj.location.z) < 1e-4, obj.location.z
""",
        # #385: keys that never play back
        falsify=("index=2", "index=1"),
    ),
    "app-handler-registration.py": dict(
        check="""
register()
register()
assert bpy.app.handlers.save_pre.count(on_save_pre) == 1
scene = bpy.context.scene
scene["my_addon_cache"] = 1
bpy.ops.wm.save_as_mainfile(filepath=tmp("handler.blend"), copy=True)
assert "my_addon_cache" not in scene
unregister()
assert on_save_pre not in bpy.app.handlers.save_pre
""",
        falsify=("del scene['my_addon_cache']", "pass"),
    ),
    "bake_normal_high_to_low.py": dict(
        check="""
low = bpy.data.objects["Cube"]
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.15, segments=32, ring_count=16)
high = bpy.context.active_object
img = bpy.data.images.new("BakeNrm", 32, 32, alpha=True, float_buffer=False)
img.colorspace_settings.name = "Non-Color"
mat = bpy.data.materials.new("BakeMat")
if bpy.app.version < (5, 0, 0):
    mat.use_nodes = True
tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
tex.image = img
mat.node_tree.nodes.active = tex
tex.select = True
low.data.materials.append(mat)
bake_normal_high_to_low(high, low, margin=2)
px = np.empty(32 * 32 * 4, dtype=np.float32)
img.pixels.foreach_get(px)
blue = px.reshape(-1, 4)[:, 2].mean()
assert blue > 0.5, blue  # tangent-space normals point mostly +Z (blue)
""",
        falsify=('type="NORMAL"', 'type="EMIT"'),
    ),
    "bmesh-load-edit-free.py": dict(
        check="""
me = bpy.context.active_object.data
z0 = [v.co.z for v in me.vertices]
raise_z_on_mesh(me, amount=0.5)
assert all(abs(v.co.z - z - 0.5) < 1e-6 for v, z in zip(me.vertices, z0))
""",
        falsify=("bm.to_mesh(mesh)", "pass"),
    ),
    "canonical-object-creation.py": dict(
        check="""
obj = create_empty_mesh_object("Generated")
assert obj.name in bpy.context.scene.collection.objects
assert obj.data.name == "Generated_Mesh"
""",
        falsify=("target.objects.link(obj)", "pass"),
    ),
    "canonical-object-deletion.py": dict(
        check="""
for i in range(3):
    bpy.context.scene.collection.objects.link(bpy.data.objects.new(f"Temp_{i}", None))
assert delete_objects_by_prefix("Temp_") == 3
assert not any(o.name.startswith("Temp_") for o in bpy.data.objects)
assert "Cube" in bpy.data.objects
""",
        falsify=("bpy.data.objects.remove(obj, do_unlink=True)", "pass"),
    ),
    "convex_hull_collider.py": dict(
        check="""
import bmesh
bpy.ops.mesh.primitive_monkey_add()
hull = convex_hull_collider(bpy.context.active_object)
bm = bmesh.new()
try:
    bm.from_mesh(hull.data)
    assert all(v.link_faces for v in bm.verts), "loose vertices"
    assert all(e.is_manifold for e in bm.edges), "non-manifold edges"
finally:
    bm.free()
""",
        # #386: the hull kept interior vertices and was not manifold
        falsify=("if loose:", "if False:"),
    ),
    "cross-version-property-delete.py": dict(
        check="""
obj = bpy.context.active_object
obj["temp_marker"] = 1.0
assert remove_custom_property(obj, "temp_marker") is True
assert "temp_marker" not in obj
assert remove_custom_property(obj, "temp_marker") is False
""",
        falsify=("del id_block[key]", "pass"),
    ),
    "decimate_to_budget.py": dict(
        check="""
bpy.ops.mesh.primitive_monkey_add()
obj = bpy.context.active_object
before = evaluated_triangle_count(obj)
assert decimate_to_budget(obj, before // 4) is not None
after = evaluated_triangle_count(obj)
assert after <= before // 4 + 8, (before, after)
assert decimate_to_budget(obj, 10 ** 6) is None
""",
        falsify=("mod.ratio = ratio", "pass"),
    ),
    "depsgraph-evaluated-mesh.py": dict(
        check="""
obj = bpy.context.active_object
obj.modifiers.new("Subsurf", "SUBSURF").levels = 1
assert get_evaluated_vertex_count(obj) == 26
""",
        falsify=("len(eval_mesh.vertices)", "len(obj.data.vertices)"),
    ),
    "driver-with-custom-function.py": dict(
        check="""
register()
obj = bpy.context.active_object
attach_smoothstep_driver(obj, frame_start=1, frame_end=101, peak=5.0)
scene = bpy.context.scene
scene.frame_set(51)
assert abs(obj.location.z - 2.5) < 1e-3, obj.location.z
scene.frame_set(101)
assert abs(obj.location.z - 5.0) < 1e-3, obj.location.z
unregister()
assert "smooth_step" not in bpy.app.driver_namespace
""",
        falsify=("3.0 - 2.0 * t", "3.0 - 1.0 * t"),
    ),
    "export_preset_godot.py": dict(
        setup=GLB_CUBE_AT_Z2,
        check="""
path = tmp("godot.glb")
export_preset_godot(path)
doc = glb_json(path)
""" + GLB_Y_UP,
        # #346: the Godot preset exported Z-up
        falsify=("export_yup=True", "export_yup=False"),
    ),
    "export_preset_unity.py": dict(
        setup=GLB_CUBE_AT_Z2,
        check="""
path = tmp("unity.glb")
export_preset_unity(path)
doc = glb_json(path)
""" + GLB_Y_UP,
        falsify=("export_yup=True", "export_yup=False"),
    ),
    "export_preset_unreal.py": dict(
        setup=GLB_CUBE_AT_Z2,
        check="""
path = tmp("unreal.glb")
export_preset_unreal_gltf(path)
doc = glb_json(path)
""" + GLB_Y_UP + """
fbx = tmp("unreal.fbx")
export_preset_unreal_fbx(fbx)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
bpy.ops.import_scene.fbx(filepath=fbx)
cube = next(o for o in bpy.data.objects if o.type == "MESH")
# #297: locations scale with the mesh (2 m up becomes 200 units)
assert abs(max(abs(c) for c in cube.location) - 200.0) < 1e-2, tuple(cube.location)
assert abs(max(cube.dimensions) - 200.0) < 1e-2, tuple(cube.dimensions)
""",
        falsify=("global_scale=100.0", "global_scale=1.0"),
    ),
    "extension-user-data.py": dict(
        check="""
__package__ = "legacy_addon"  # a bl_info add-on folder, not bl_ext.<repo>.<id>
try:
    settings_path()
except ValueError:
    pass  # the documented failure for a non-extension package
else:
    raise AssertionError("extension_path_user accepted a non-extension package")
assert not bpy.app.online_access
assert fetch_if_allowed("http://127.0.0.1:9/") is None
settings_path = lambda filename="settings.json": tmp(filename)
save_settings({"size": 3})
assert load_settings() == {"size": 3}
""",
        falsify=("if not bpy.app.online_access:", "if False:"),
    ),
    "foreach-get-vertices.py": dict(
        check="""
me = bpy.context.active_object.data
co = read_vertex_coords(me)
assert co.shape == (8, 3)
assert np.allclose(co, [tuple(v.co) for v in me.vertices])
nrm = read_vertex_normals(me)
assert np.allclose(np.linalg.norm(nrm, axis=1), 1.0, atol=1e-5)
""",
        falsify=('foreach_get("co", flat)', 'foreach_get("normal", flat)'),
    ),
    "foreach-set-vertices.py": dict(
        check="""
import math
me = build_grid_mesh(size=10).data
assert len(me.vertices) == 100
want = (2.0, 3.0, math.sin(0.2) * math.cos(0.3))
assert all(abs(a - b) < 1e-5 for a, b in zip(me.vertices[23].co, want)), tuple(me.vertices[23].co)
""",
        falsify=("np.cos(ys.ravel() * 0.1)", "np.cos(ys.ravel() * 0.2)"),
    ),
    "gltf_draco_export.py": dict(
        setup=GLB_CUBE_AT_Z2,
        check="""
path = tmp("draco.glb")
export_gltf_draco(path)
doc = glb_json(path)
assert "KHR_draco_mesh_compression" in doc.get("extensionsRequired", []), doc.get("extensionsRequired")
""" + GLB_Y_UP,
        falsify=("export_draco_mesh_compression_enable=True", "export_draco_mesh_compression_enable=False"),
    ),
    "gpu-draw-handler.py": dict(
        check="""
register()
first = _handle
register()
assert _handle is first and _handle is not None
unregister()
assert _handle is None
""",
        falsify=("        _handle = None", "        pass"),
    ),
    "lod_chain.py": dict(
        check="""
bpy.ops.mesh.primitive_monkey_add()
obj = bpy.context.active_object
full = evaluated_triangle_count(obj)
lods = make_lod_chain(obj, budgets=(full // 2, full // 8))
tris = [evaluated_triangle_count(o) for o in lods]
assert [o.name for o in lods] == [f"{obj.name}_LOD0", f"{obj.name}_LOD1"]
assert tris[0] <= full // 2 + 8 and tris[1] <= full // 8 + 8 and tris[1] < tris[0], (full, tris)
""",
        falsify=("mod.ratio = ratio", "pass"),
    ),
    "pointerproperty-binding.py": dict(
        check="""
register()
obj = bpy.context.active_object
obj.example_data.score = 2.5
obj.example_data.label = "hero"
assert obj.example_data.score == 2.5 and obj.example_data.label == "hero"
unregister()
assert not hasattr(bpy.types.Object, "example_data")
""",
        falsify=("del bpy.types.Object.example_data", "pass"),
    ),
    "principled-bsdf-material.py": dict(
        check="""
mat = make_principled_material("Red", base_color=(0.8, 0.1, 0.1, 1.0), metallic=0.3, roughness=0.4)
out = next(n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL")
links = out.inputs["Surface"].links
assert links and links[0].from_node.type == "BSDF_PRINCIPLED"
bsdf = links[0].from_node
assert all(abs(a - b) < 1e-6 for a, b in zip(bsdf.inputs["Base Color"].default_value, (0.8, 0.1, 0.1, 1.0)))
assert abs(bsdf.inputs["Metallic"].default_value - 0.3) < 1e-6
""",
        falsify=("links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])", "pass"),
    ),
    "register-classes-factory.py": dict(
        check="""
register()
assert bpy.ops.example.hello() == {"FINISHED"}
unregister()
assert not hasattr(bpy.types, "EXAMPLE_OT_hello")
""",
        falsify=("return {'FINISHED'}", "return {'CANCELLED'}"),
    ),
    "save_baked_image.py": dict(
        check="""
img = bpy.data.images.new("Baked", 4, 4)
settings = bpy.context.scene.render.image_settings
settings.file_format = "JPEG"
path = save_baked_image(img, tmp("baked.png"), file_format="PNG")
with open(path, "rb") as fh:
    assert fh.read(8) == b"\\x89PNG\\r\\n\\x1a\\n", "not a PNG"
assert settings.file_format == "JPEG"
""",
        # #332: setting the image's format, which save_render ignores
        falsify=("settings.file_format = file_format", "image.file_format = file_format"),
    ),
    "set-sharp-from-angle.py": dict(
        setup="""
bpy.ops.mesh.primitive_cylinder_add(vertices=16)
""",
        check="""
me = bpy.context.active_object.data
assert len(normals) == len(me.loops) == 96
assert all(p.use_smooth for p in me.polygons)
sharp = me.attributes.get("sharp_edge")
assert sharp is not None and sum(d.value for d in sharp.data) == 32
""",
        falsify=("math.radians(degrees)", "math.radians(degrees + 70)"),
    ),
    "setup_bake_target_image.py": dict(
        check="""
cube = bpy.data.objects["Cube"]
img, mat, tex = setup_bake_target_image(cube)
assert mat.node_tree.nodes.active == tex and tex.image == img
assert img.colorspace_settings.name == "Non-Color"
assert cube.data.materials[0] == mat
bare = bpy.data.objects.new("NoUV", bpy.data.meshes.new("NoUV"))
try:
    setup_bake_target_image(bare)
except ValueError:
    pass
else:
    raise AssertionError("no ValueError for a mesh without UVs")
""",
        falsify=("nodes.active = tex", "pass"),
    ),
    "shader-node-group.py": dict(
        check="""
group = make_tint_group()
names = {(s.in_out, s.name) for s in group.interface.items_tree if s.item_type == "SOCKET"}
assert names == {("INPUT", "Color"), ("INPUT", "Strength"), ("OUTPUT", "Result")}, names
mix = next(n for n in group.nodes if n.type == "MIX")
assert mix.inputs[6].links and mix.inputs[6].links[0].from_socket.name == "Color"
out = next(n for n in group.nodes if n.type == "GROUP_OUTPUT")
assert out.inputs["Result"].links[0].from_node == mix
""",
        falsify=("mix.inputs[6]", "mix.inputs[4]"),
    ),
    "temp-override-context.py": dict(
        check="""
cube = bpy.data.objects["Cube"]
others = []
for x in (3.0, 6.0):
    o = bpy.data.objects.new(f"Part{x}", cube.data.copy())
    o.location.x = x
    bpy.context.scene.collection.objects.link(o)
    others.append(o)
join_meshes_with_override(cube, others)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
assert meshes == [cube] and len(cube.data.vertices) == 24, (meshes, len(cube.data.vertices))
""",
        falsify=("        bpy.ops.object.join()", "        pass"),
    ),
    "thread-queue-timer.py": dict(
        # timers never fire in --background, so the check drives _drain itself
        check="""
import time
register()
target = bpy.data.objects.new("Target", None)
bpy.context.scene.collection.objects.link(target)
run_in_background(lambda: 42)
run_in_background(lambda: 1 / 0)
deadline = time.time() + 10
while _results.qsize() < 2 and time.time() < deadline:
    time.sleep(0.05)
assert _results.qsize() == 2
assert _drain() is None  # every job is in: the timer unregisters
assert target["result"] == 42
unregister()
""",
        falsify=("        _pending -= 1", "        pass"),
    ),
    "usd-export-evaluation-mode.py": dict(
        check="""
# Not subsurf: the USD exporter writes the last Subdivision Surface out as a
# USD subdivision scheme instead of applying it, at either evaluation mode.
cube = bpy.data.objects["Cube"]
mod = cube.modifiers.new("RenderOnly", "ARRAY")
mod.count, mod.show_viewport, mod.show_render = 2, False, True
path = tmp("render.usda")
export_usd_with_render_evaluation(path)
before = set(bpy.data.meshes)
bpy.ops.wm.usd_import(filepath=path)
counts = [len(m.vertices) for m in bpy.data.meshes if m not in before]
assert 16 in counts, counts  # the render-only array, not the 8-vertex viewport cube
""",
        falsify=("evaluation_mode='RENDER'", "evaluation_mode='VIEWPORT'"),
    ),
    "version-branch-skeleton.py": dict(
        check="""
obj = bpy.context.active_object
obj["k"] = 1
assert clear_property(obj, "k") is True and clear_property(obj, "k") is False
scene = bpy.context.scene
scene.render.engine = get_eevee_engine_id()
assert scene.render.engine == get_eevee_engine_id()
""",
        falsify=(">= (5, 0, 0)", "< (5, 0, 0)"),
    ),
}
