# bpy.context.temp_override: run an operator with a fabricated context.
# Useful in headless scripts and modal cases where the operator needs a
# specific window, area, region, or active object that the current
# context doesn't provide.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.Context.html#bpy.types.Context.temp_override

import bpy


def join_meshes_with_override(target, sources):
    target.select_set(True)
    for src in sources:
        src.select_set(True)

    view_layer = bpy.context.view_layer
    view_layer.objects.active = target

    with bpy.context.temp_override(
        active_object=target,
        selected_objects=[target, *sources],
        selected_editable_objects=[target, *sources],
    ):
        bpy.ops.object.join()


if __name__ == "__main__":
    objs = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if len(objs) >= 2:
        join_meshes_with_override(objs[0], objs[1:])
