# Add a DECIMATE COLLAPSE modifier so evaluated triangles land at a budget.
# Triangle count is measured on the evaluated mesh (modifiers applied),
# not obj.data. ratio = target_tris / current, clamped to 1.0.
# Returns None when the object is already at or under budget.
#
# On 4.5 LTS and 5.x, Mesh.loop_triangles is computed lazily from the
# current topology, so calc_loop_triangles() is not required (a fresh cube,
# a to_mesh() result and a post-edit mesh all read correct counts without
# it). Calling it is harmless; kept for code that also runs on older builds.
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
