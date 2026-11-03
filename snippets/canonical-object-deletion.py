# Canonical object deletion: bpy.data.objects.remove with do_unlink=True.
# Removes the object from every collection it's linked to and frees it,
# without going through bpy.ops.object.delete (which depends on UI
# context and selection state).
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.BlendDataObjects.html#bpy.types.BlendDataObjects.remove

import bpy


def delete_objects_by_prefix(prefix):
    targets = [obj for obj in bpy.data.objects if obj.name.startswith(prefix)]
    for obj in targets:
        bpy.data.objects.remove(obj, do_unlink=True)
    return len(targets)


if __name__ == "__main__":
    removed = delete_objects_by_prefix("Temp_")
    print(f"Removed {removed} objects")
