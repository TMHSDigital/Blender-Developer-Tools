# Get the modifier-applied mesh of an object via the depsgraph.
# obj.data is the unevaluated mesh; modifiers, geometry nodes, shape
# keys, and constraints are not applied. evaluated_get(depsgraph) gives
# the evaluated copy, and to_mesh() materializes it as a real Mesh.
#
# Always pair to_mesh() with to_mesh_clear() to release the temp data.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.Depsgraph.html
#   https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.evaluated_get

import bpy


def get_evaluated_vertex_count(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        return len(eval_mesh.vertices)
    finally:
        eval_obj.to_mesh_clear()


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None and obj.type == 'MESH':
        print(f"Evaluated vertex count: {get_evaluated_vertex_count(obj)}")
