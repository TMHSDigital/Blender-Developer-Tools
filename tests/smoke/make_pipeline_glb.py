import bmesh
import bpy
import sys

out = sys.argv[sys.argv.index("--") + 1 :][0]
bpy.ops.wm.read_factory_settings(use_empty=True)
me = bpy.data.meshes.new("Fixture")
bm = bmesh.new()
try:
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
    bm.to_mesh(me)
finally:
    bm.free()
obj = bpy.data.objects.new("Fixture", me)
bpy.context.collection.objects.link(obj)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
path = out.replace("\\", "/")
bpy.ops.export_scene.gltf(
    filepath=path,
    export_format="GLB",
    use_selection=True,
    export_yup=True,
    export_apply=True,
    export_animations=False,
)
print(f"saved fixture {path}")
