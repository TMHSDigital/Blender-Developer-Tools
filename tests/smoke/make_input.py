import bpy, bmesh, sys
out = sys.argv[sys.argv.index("--")+1:][0]
bpy.ops.wm.read_factory_settings(use_empty=True)
for name, loc in [("Cube",(0,0,0)), ("Sphere",(3,0,0))]:
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    if name == "Cube": bmesh.ops.create_cube(bm, size=2.0)
    else: bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
    bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc
    bpy.context.collection.objects.link(o)
# camera + sun + emissive world so a render is non-black
cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d)
bpy.context.collection.objects.link(cam); cam.location=(6,-6,6); cam.rotation_euler=(1.1,0,0.78)
bpy.context.scene.camera = cam
sd = bpy.data.lights.new("sun",'SUN'); s=bpy.data.objects.new("sun",sd); s.location=(0,0,8); bpy.context.collection.objects.link(s)
bpy.context.scene.world = bpy.data.worlds.new("W")
bpy.context.scene.world.use_nodes = True
bpy.context.scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.3,0.4,0.6,1.0)
bpy.ops.wm.save_as_mainfile(filepath=out)
print(f"saved input {out} with 2 meshes")
# also an empty blend for the exit-code-2 path
empty = out.replace("input.blend","empty.blend")
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.save_as_mainfile(filepath=empty)
print(f"saved empty {empty}")
