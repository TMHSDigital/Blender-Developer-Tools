# Ordered LOD set from one source object via successive triangle budgets.
# Snippets are standalone and not a package; the evaluated-triangle-count
# and DECIMATE helper is duplicated from snippets/decimate_to_budget.py
# rather than imported across files.
#
# Each LOD is a new object (source datablock is not mutated). A DECIMATE
# COLLAPSE modifier is added only when that copy is over budget.
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


def make_lod_chain(obj, budgets):
    lods = []
    for i, budget in enumerate(budgets):
        mesh = obj.data.copy()
        lod = bpy.data.objects.new(f"{obj.name}_LOD{i}", mesh)
        lod.matrix_world = obj.matrix_world.copy()
        bpy.context.scene.collection.objects.link(lod)
        decimate_to_budget(lod, budget)
        lods.append(lod)
    return lods


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None and obj.type == "MESH":
        chain = make_lod_chain(obj, budgets=(8, 4))
        print(f"lods: {[o.name for o in chain]}")
