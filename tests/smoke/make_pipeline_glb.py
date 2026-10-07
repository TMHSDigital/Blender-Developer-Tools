"""Write a fixture GLB for templates/ai-asset-pipeline-template/pipeline.py.

    blender --background --python make_pipeline_glb.py -- OUT.glb [--radius R] [--parented]

Default: one UV sphere of radius R (1.0). --radius 1000 is the out-of-range
units fixture (pipeline exit 8).

--parented: the shape glTF instancing and node trees import as (#462, #467).
A Root empty, rotated 90 deg about X and scaled 2x at z=3, parents a Body box
and two wheels, WheelL and WheelR, that share one mesh (users=2) and carry
different rotations. tests/smoke/check_pipeline_glb.py then asserts the
pipeline's lod0.glb keeps every part (world bbox == source) with its origin
on the world minimum Z.
"""
import argparse
import math
import sys

import bmesh
import bpy


def mesh_from(name, build):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        build(bm)
        bm.to_mesh(me)
    finally:
        bm.free()
    return me


def link(name, data, parent=None):
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    return obj


args = argparse.ArgumentParser()
args.add_argument("out")
args.add_argument("--radius", type=float, default=1.0)
args.add_argument("--parented", action="store_true")
args = args.parse_args(sys.argv[sys.argv.index("--") + 1:])

bpy.ops.wm.read_factory_settings(use_empty=True)
if args.parented:
    root = link("Root", None)
    root.location = (0.0, 0.0, 3.0)
    root.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    root.scale = (2.0, 2.0, 2.0)
    link("Body", mesh_from("BodyMesh", lambda bm: bmesh.ops.create_cube(bm, size=1.0)), root)
    wheel = mesh_from("WheelMesh", lambda bm: bmesh.ops.create_cone(
        bm, cap_ends=True, segments=12, radius1=0.3, radius2=0.3, depth=0.2))
    left = link("WheelL", wheel, root)
    left.location = (0.9, 0.0, -0.3)
    left.rotation_euler = (0.0, math.radians(90.0), 0.0)
    right = link("WheelR", wheel, root)
    right.location = (-0.9, 0.0, -0.3)
    right.rotation_euler = (0.0, math.radians(-90.0), 0.4)
    assert wheel.users == 2, wheel.users
else:
    link("Fixture", mesh_from("Fixture", lambda bm: bmesh.ops.create_uvsphere(
        bm, u_segments=48, v_segments=24, radius=args.radius)))

for obj in bpy.data.objects:
    obj.select_set(True)
path = args.out.replace("\\", "/")
bpy.ops.export_scene.gltf(
    filepath=path,
    export_format="GLB",
    use_selection=True,
    export_yup=True,
    export_apply=True,
    export_animations=False,
)
print(f"saved fixture {path}")
