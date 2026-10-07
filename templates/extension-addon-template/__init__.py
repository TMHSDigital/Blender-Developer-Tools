# Example Blender Extension add-on.
#
# Demonstrates the load-bearing conventions for Extensions Platform add-ons:
#   - Properties declared with type-annotation form (factor: bpy.props.X(...)),
#     not assignment form. The assignment form is deprecated since 2.80.
#   - Operators with bl_options including 'REGISTER' and 'UNDO' so redo and
#     undo work as expected.
#   - PropertyGroup bound to bpy.types.Scene via PointerProperty for state
#     that should survive save/load.
#   - register_classes_factory for symmetric class registration.
#   - Unregister tears down PointerProperty bindings BEFORE unregister_class,
#     because the unregister_class call invalidates the type the binding
#     points at.
#
# bl_info is kept alongside the manifest for backward compatibility with
# Blender versions before manifests were honored. The manifest is the
# source of truth.

bl_info = {
    "name": "Example Addon",
    "blender": (4, 5, 0),
    "version": (0, 1, 0),
    "category": "Object",
}

import bpy


class EXAMPLE_PG_settings(bpy.types.PropertyGroup):
    factor: bpy.props.FloatProperty(
        name="Factor",
        description="Scalar applied by the operator to the active object's Z location",
        default=1.0,
        min=-10.0,
        max=10.0,
    )

    enabled: bpy.props.BoolProperty(
        name="Enabled",
        default=True,
    )


class EXAMPLE_OT_nudge_active(bpy.types.Operator):
    bl_idname = "example.nudge_active"
    bl_label = "Nudge Active Object"
    bl_options = {'REGISTER', 'UNDO'}

    factor: bpy.props.FloatProperty(
        name="Factor",
        default=1.0,
        min=-10.0,
        max=10.0,
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        scene_settings = context.scene.example_addon
        self.factor = scene_settings.factor
        return self.execute(context)

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}

        obj.location.z += self.factor
        self.report({'INFO'}, f"Moved {obj.name} by {self.factor:.3f} on Z")
        return {'FINISHED'}


class EXAMPLE_PT_panel(bpy.types.Panel):
    bl_idname = "VIEW3D_PT_example_addon"
    bl_label = "Example Addon"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Example"

    def draw(self, context):
        layout = self.layout
        scene_settings = context.scene.example_addon

        col = layout.column(align=True)
        col.prop(scene_settings, "enabled")

        sub = col.column(align=True)
        sub.enabled = scene_settings.enabled
        sub.prop(scene_settings, "factor")

        op_row = layout.row()
        op_row.enabled = scene_settings.enabled and context.active_object is not None
        op_row.operator(EXAMPLE_OT_nudge_active.bl_idname, icon='TRIA_UP')


classes = (
    EXAMPLE_PG_settings,
    EXAMPLE_OT_nudge_active,
    EXAMPLE_PT_panel,
)

_register, _unregister = bpy.utils.register_classes_factory(classes)


def register():
    _register()
    bpy.types.Scene.example_addon = bpy.props.PointerProperty(type=EXAMPLE_PG_settings)


def unregister():
    del bpy.types.Scene.example_addon
    _unregister()


if __name__ == "__main__":
    register()
