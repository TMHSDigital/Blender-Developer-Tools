# Canonical registration via bpy.utils.register_classes_factory.
# Returns a (register, unregister) pair that loops over the tuple in
# the right direction for each, so subclasses register before being
# referenced and unregister in reverse order.
#
# Reference:
#   https://docs.blender.org/api/current/bpy.utils.html#bpy.utils.register_classes_factory

import bpy


class EXAMPLE_OT_hello(bpy.types.Operator):
    bl_idname = "example.hello"
    bl_label = "Say Hello"
    bl_options = {'REGISTER'}

    def execute(self, context):
        self.report({'INFO'}, "Hello from the example add-on")
        return {'FINISHED'}


classes = (
    EXAMPLE_OT_hello,
)

register, unregister = bpy.utils.register_classes_factory(classes)


if __name__ == "__main__":
    register()
