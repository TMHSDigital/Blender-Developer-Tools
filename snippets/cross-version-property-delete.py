# Cross-version property deletion: property_unset (5.0+) vs del (4.5 LTS).
# Custom ID properties (the dict-style obj["my_key"] = value) are removed
# differently across Blender versions. property_unset is the cleaner
# 5.x-and-up form; del obj["key"] still works on 4.5 LTS.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.bpy_struct.html

import bpy


def remove_custom_property(id_block, key):
    if key not in id_block.keys():
        return False

    if bpy.app.version >= (5, 0, 0):
        id_block.property_unset(key)
    else:
        del id_block[key]

    return True


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None:
        obj["temp_marker"] = 1.0
        removed = remove_custom_property(obj, "temp_marker")
        print(f"Removed temp_marker: {removed}")
