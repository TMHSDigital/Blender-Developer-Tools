# Bind a PropertyGroup to an ID type via PointerProperty so its data
# survives save/load. Plain Python attributes set on bpy.types.Object
# do not persist across .blend reload.
#
# Unregister deletes the binding BEFORE unregister_class invalidates
# the PropertyGroup type.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.props.html#bpy.props.PointerProperty

import bpy


class EXAMPLE_PG_object_data(bpy.types.PropertyGroup):
    label: bpy.props.StringProperty(name="Label", default="")
    score: bpy.props.FloatProperty(name="Score", default=0.0)


def register():
    bpy.utils.register_class(EXAMPLE_PG_object_data)
    bpy.types.Object.example_data = bpy.props.PointerProperty(type=EXAMPLE_PG_object_data)


def unregister():
    del bpy.types.Object.example_data
    bpy.utils.unregister_class(EXAMPLE_PG_object_data)


if __name__ == "__main__":
    register()
