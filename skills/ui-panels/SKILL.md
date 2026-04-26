---
name: ui-panels
description: Author Blender UI panels with bpy.types.Panel, declarative draw(), bl_space_type and bl_region_type, layout primitives like row/column/split, and conditional UI via .enabled. Targets 5.1.
standards-version: 1.9.4
---

# UI Panels

## Trigger

Use this skill when the user:

- Wants a sidebar tab in the 3D viewport, properties editor, or any other space
- Mentions `bpy.types.Panel`, `bl_space_type`, `bl_region_type`, "N panel", "sidebar"
- Needs to expose properties or operators in a custom UI
- Asks why a property is showing without a label or in the wrong column

## Required inputs

- **Where the panel lives**: the editor (3D viewport, Properties, etc.) and the region (sidebar, header, tools)
- **Tab name** if it lives in a sidebar (`bl_category`)
- **Class name** convention: `EDITOR_PT_name` (`VIEW3D_PT_my_addon`)

## The minimum viable panel

```python
import bpy


class VIEW3D_PT_my_addon(bpy.types.Panel):
    bl_label = "My Addon"
    bl_idname = "VIEW3D_PT_my_addon"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "My Addon"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Hello from the N panel")
```

After registering the class, the panel appears in the 3D viewport's sidebar (press `N`) under a "My Addon" tab.

## The bl_* fields that decide where it lives

| Field | Common values | Effect |
| --- | --- | --- |
| `bl_space_type` | `'VIEW_3D'`, `'PROPERTIES'`, `'NODE_EDITOR'`, `'IMAGE_EDITOR'`, `'TEXT_EDITOR'`, `'OUTLINER'`, `'SEQUENCE_EDITOR'` | Which editor the panel appears in |
| `bl_region_type` | `'UI'` (sidebar), `'TOOLS'` (toolbar, deprecated for new add-ons), `'WINDOW'` (main, used in PROPERTIES), `'HEADER'` | Which region within the editor |
| `bl_category` | Any string | Tab name in `'UI'` regions |
| `bl_label` | Any string | Visible header on the panel |
| `bl_idname` | Conventional `EDITOR_PT_name` | Internal, also used as the parent for sub-panels |
| `bl_context` | `'objectmode'`, `'mesh_edit'`, `'render'`, etc. | Restrict to a context (mainly Properties editor) |
| `bl_parent_id` | Another panel's `bl_idname` | Makes this a sub-panel under that parent |
| `bl_options` | `{'DEFAULT_CLOSED'}`, `{'HIDE_HEADER'}` | UI options |

The class name convention `EDITOR_PT_name` is enforced by Blender (the `_PT_` infix) and the editor prefix maps to `bl_space_type`.

## The declarative `draw` method

`draw` runs every redraw. It must be cheap and idempotent. **Do not** mutate scene state from inside `draw`. Use `layout.prop`, `layout.operator`, `layout.label`, and the layout container methods.

```python
def draw(self, context):
    layout = self.layout
    settings = context.scene.my_addon

    layout.prop(settings, "intensity")
    layout.prop(settings, "use_smoothing")

    row = layout.row()
    row.prop(settings, "min_value")
    row.prop(settings, "max_value")

    layout.operator("mesh.my_addon_action")
```

`layout.prop` reads the property metadata (label, description, range, subtype) from the `bpy.props` definition. **You do not pass the label**. If you want to override:

```python
layout.prop(settings, "intensity", text="Strength")
```

`layout.prop(..., text="")` removes the label entirely, useful inside aligned columns.

## Layout primitives

| Method | Use for |
| --- | --- |
| `layout.row()` | Horizontal arrangement |
| `layout.row(align=True)` | Horizontal with no gap, like a button group |
| `layout.column()` | Vertical (default for `layout` itself) |
| `layout.column(align=True)` | Vertical with no gap, useful for aligned `prop` rows |
| `layout.split(factor=0.5)` | Two-column split with explicit ratio |
| `layout.box()` | Bordered group |
| `layout.separator()` | Vertical spacer |
| `layout.separator(factor=2.0)` | Larger vertical spacer |

### Aligned property rows

```python
col = layout.column(align=True)
col.prop(settings, "min_value")
col.prop(settings, "max_value")
```

Without `align=True` you get a small gap between rows. With it the boxes touch, which is the conventional look for paired min/max controls.

### Split for label + control

```python
split = layout.split(factor=0.4)
split.label(text="Mode")
split.prop(settings, "mode", text="")
```

This lays out a left-aligned label that takes 40% of the width with the dropdown filling the rest.

## Conditional UI: `.enabled`, not show/hide

Showing and hiding individual controls based on state causes the panel to "jump" as the user works. The Blender convention is to keep the layout stable and gray out controls that don't apply:

```python
def draw(self, context):
    layout = self.layout
    settings = context.scene.my_addon

    layout.prop(settings, "use_smoothing")

    sub = layout.column()
    sub.enabled = settings.use_smoothing
    sub.prop(settings, "smoothing_passes")
    sub.prop(settings, "smoothing_strength")
```

`sub.enabled = False` grays out the controls but keeps them in place. Users instinctively read this as "available but not active right now."

For genuinely dependent UI (the entire concept disappears in the other state), use a sub-panel with `bl_parent_id` and toggle the parent's `poll` instead.

## Worked example: panel calling an operator on a Scene-bound property

```python
import bpy


class MY_ADDON_PG_settings(bpy.types.PropertyGroup):
    intensity: bpy.props.FloatProperty(name="Intensity", default=1.0, min=0.0, max=10.0)
    use_smoothing: bpy.props.BoolProperty(name="Smooth Result", default=True)
    smoothing_passes: bpy.props.IntProperty(name="Passes", default=2, min=1, max=10)


class MESH_OT_apply_my_addon(bpy.types.Operator):
    bl_idname = "mesh.apply_my_addon"
    bl_label = "Apply"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            return {'CANCELLED'}
        settings = context.scene.my_addon
        self.report({'INFO'}, f"Apply at intensity={settings.intensity:.2f}")
        return {'FINISHED'}


class VIEW3D_PT_my_addon(bpy.types.Panel):
    bl_label = "My Addon"
    bl_idname = "VIEW3D_PT_my_addon"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "My Addon"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.my_addon

        layout.prop(settings, "intensity")
        layout.prop(settings, "use_smoothing")

        sub = layout.column()
        sub.enabled = settings.use_smoothing
        sub.prop(settings, "smoothing_passes")

        layout.separator()
        layout.operator("mesh.apply_my_addon", icon='PLAY')


classes = (
    MY_ADDON_PG_settings,
    MESH_OT_apply_my_addon,
    VIEW3D_PT_my_addon,
)

_register_classes, _unregister_classes = bpy.utils.register_classes_factory(classes)


def register():
    _register_classes()
    bpy.types.Scene.my_addon = bpy.props.PointerProperty(type=MY_ADDON_PG_settings)


def unregister():
    del bpy.types.Scene.my_addon
    _unregister_classes()
```

## Common AI mistakes

1. **Mutating state from `draw`**. `draw` runs on every redraw, dozens of times per second. If you create or delete data there, you will leak, crash, or block the UI.

2. **Hardcoding the label twice**:

   ```python
   layout.prop(settings, "intensity", text="Intensity")  # redundant
   ```

   The label comes from the property definition. Pass `text=` only to override or to suppress with `text=""`.

3. **Mixing `bl_region_type='UI'` with no `bl_category`**. Blender will silently default it, hiding your panel under "View" or similar. Always set `bl_category`.

4. **Using `bl_region_type='TOOLS'` for new add-ons**. The tools region was deprecated in 2.8 in favor of the UI region for sidebar panels. Stick to `'UI'`.

5. **Show/hide instead of `.enabled`**. The panel jumps and confuses the user. Gray out unless the entire concept is gone.

6. **`bl_idname` not matching the convention**. The `_PT_` infix is required, and the editor prefix should match `bl_space_type`.

## Related

- `operators` for the operator that the panel button calls
- `custom-properties` for the property definitions the panel reads
- `addon-scaffolding` for class registration

## References

- `bpy.types.Panel`: https://docs.blender.org/api/current/bpy.types.Panel.html
- UI layout reference: https://docs.blender.org/api/current/bpy.types.UILayout.html
- Panel example in API docs: https://docs.blender.org/api/current/info_quickstart.html
