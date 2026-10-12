# Canonical object creation: mesh + object + collection link.
# Avoids bpy.ops.mesh.primitive_*, which forces a depsgraph evaluation
# and a UI redraw per call.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.Mesh.html
#   https://docs.blender.org/api/current/bpy.types.Object.html
#   https://docs.blender.org/api/current/bpy.types.Collection.html

import bpy


def create_empty_mesh_object(name="MyObject", collection=None):
    mesh = bpy.data.meshes.new(name=f"{name}_Mesh")
    obj = bpy.data.objects.new(name=name, object_data=mesh)

    target = collection if collection is not None else bpy.context.scene.collection
    target.objects.link(obj)

    return obj


if __name__ == "__main__":
    create_empty_mesh_object("Generated")
