# Removing a custom ID property (the dict-style obj["my_key"] = value).
# ID-property removal is version-stable: `del id_block[key]` works on all
# Blender versions (4.5 LTS and 5.x alike). There is no version branch here.
#
# Do NOT use property_unset() for this. property_unset() RESETS a registered
# RNA property to its default value; it does not remove a custom ID property.
# That is a different operation.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.types.bpy_struct.html

import bpy


def remove_custom_property(id_block, key):
    if key not in id_block.keys():
        return False

    del id_block[key]
    return True


if __name__ == "__main__":
    obj = bpy.context.active_object
    if obj is not None:
        obj["temp_marker"] = 1.0
        removed = remove_custom_property(obj, "temp_marker")
        print(f"Removed temp_marker: {removed}")
