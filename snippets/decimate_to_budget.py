# Add a DECIMATE COLLAPSE modifier so evaluated triangles land at a budget.
# Triangle count is measured on the evaluated mesh (modifiers applied),
# not obj.data. ratio = target_tris / current, clamped to 1.0.
# Returns None when the object is already at or under budget.
#
# Mesh.calc_loop_triangles() is required before reading loop_triangles on
# 4.5 LTS and on 5.x; tessellation is not implicit. Always call it.
# Do not use a hasattr guard.
#
# Reference:
#   https://docs.blender.org/api/5.1/bpy.types.Mesh.html#bpy.types.Mesh.calc_loop_triangles
#   https://docs.blender.org/api/current/bpy.types.DecimateModifier.html
#   https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.evaluated_get

import bpy


def evaluated_triangle_count(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    try:
        eval_mesh.calc_loop_triangles()
        return len(eval_mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()


def decimate_to_budget(obj, target_tris):
    current = evaluated_triangle_count(obj)
    if current == 0 or current <= target_tris:
        return None
    ratio = min(1.0, target_tris / current)
    mod = obj.modifiers.new("DecimateBudget", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = ratio
    return mod


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None and obj.type == "MESH":
        print(f"evaluated tris: {evaluated_triangle_count(obj)}")
        print(f"modifier: {decimate_to_budget(obj, target_tris=4)}")
