---
name: operators
description: Author Blender operators with bpy.types.Operator, bl_idname conventions, the poll/invoke/execute/modal lifecycle, REGISTER and UNDO options, and defensive context handling. Targets 5.1 with 4.5 LTS compatibility.
standards-version: 1.9.4
---

# Operators

## Trigger

Use this skill when the user:

- Wants to create a new `bpy.types.Operator`
- Mentions `bl_idname`, `bl_label`, `bl_options`, "redo panel", "F6 panel", "operator props"
- Needs an action triggered from a button, menu, keymap, or chat command
- Asks why their operator's properties don't show up in the redo panel

## Required inputs

- **Action category**: the prefix of `bl_idname` (`mesh`, `object`, `scene`, `view3d`, etc.)
- **Operator name**: the suffix (`my_addon_action`)
- **Class name**: the conventional `CATEGORY_OT_name` (`MESH_OT_my_addon_action`)
- **Whether the action is undoable** (most are)

## Anatomy of a Blender operator

```python
import bpy


class MESH_OT_extrude_normal(bpy.types.Operator):
    bl_idname = "mesh.extrude_normal"
    bl_label = "Extrude Along Normal"
    bl_description = "Extrude active mesh by a fixed amount along its normal"
    bl_options = {'REGISTER', 'UNDO'}

    distance: bpy.props.FloatProperty(
        name="Distance",
        description="How far to extrude",
        default=0.5,
        min=-100.0,
        max=100.0,
        unit='LENGTH',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and obj.mode == 'OBJECT'

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}

        # Operate on bpy.data, not bpy.ops, in tight loops.
        # See the mesh-editing-and-bmesh skill for the full pattern.
        mesh = obj.data
        for v in mesh.vertices:
            v.co += v.normal * self.distance

        mesh.update()
        self.report({'INFO'}, f"Extruded {len(mesh.vertices)} vertices by {self.distance:.3f}")
        return {'FINISHED'}
```

## The lifecycle methods

| Method | Required | Called when | Returns |
| --- | --- | --- | --- |
| `poll(cls, context)` | Optional | Every UI redraw to decide if the operator is enabled. Must be cheap. | `True` to enable, `False` or falsy to disable |
| `invoke(self, context, event)` | Optional | The user triggers the operator interactively (button, menu, keymap). Default forwards to `execute`. | `{'FINISHED'}`, `{'CANCELLED'}`, `{'PASS_THROUGH'}`, `{'RUNNING_MODAL'}` |
| `execute(self, context)` | Yes | The operator runs, either after `invoke` or directly via `bpy.ops.mesh.extrude_normal()` | `{'FINISHED'}` or `{'CANCELLED'}` |
| `modal(self, context, event)` | Optional | After `invoke` returns `{'RUNNING_MODAL'}`. Called for each event until you return `{'FINISHED'}` or `{'CANCELLED'}`. | Standard return set |
| `draw(self, context)` | Optional | The redo panel after the operator runs. Defaults to drawing all properties. | None |

### `poll` must be fast

`poll` runs on every UI redraw. **Do not iterate the scene, scan meshes, or call modifiers there.** Restrict yourself to `context.active_object`, `obj.type`, `obj.mode`, and similar O(1) checks.

### `bl_options` you almost always want

- `'REGISTER'`: makes the operator show up in the redo panel and undo history. Without this, the operator is invisible to the user after running and properties cannot be tweaked.
- `'UNDO'`: hooks into the undo stack. Without this, your operator's effect cannot be undone with Ctrl-Z.
- `'INTERNAL'`: hides the operator from search and help. Use for operators called only by other operators or panels.
- `'BLOCKING'`: pauses other UI updates while running. Reserve for modal operators that need exclusive input.
- `'GRAB_CURSOR'` and `'GRAB_CURSOR_X'` / `'GRAB_CURSOR_Y'`: useful in modal operators to capture mouse motion.

## Defensive context handling

`context.active_object` returns `None` when the scene has no active object, which happens routinely:

- Headless scripts via `blender --background --python script.py` start with no active object.
- Empty selections after a deselect-all.
- Some context overrides set the active object to `None` deliberately.

**Always** guard before dereferencing:

```python
def execute(self, context):
    obj = context.active_object
    if obj is None:
        self.report({'ERROR'}, "No active object")
        return {'CANCELLED'}
    if obj.type != 'MESH':
        self.report({'ERROR'}, f"{obj.name} is a {obj.type}, expected MESH")
        return {'CANCELLED'}
    # ...
```

Even if `poll` already filtered, `execute` must re-check, because `execute` is also reachable from `bpy.ops` calls in scripts that bypass the UI.

## Reporting back to the user

Use `self.report({level}, message)` rather than `print()`:

| Level | UI behavior |
| --- | --- |
| `'DEBUG'` | Visible only in developer mode |
| `'INFO'` | Status bar, info window |
| `'WARNING'` | Status bar with yellow tint, info window |
| `'ERROR'` | Status bar with red tint, info window |
| `'ERROR_INVALID_INPUT'` | Same as ERROR but signals input was the cause |

Pair `report({'ERROR'}, ...)` with `return {'CANCELLED'}` so the operator does not appear successful.

## Worked example: a redo-friendly operator with a redo panel

```python
import bpy


class OBJECT_OT_offset_active(bpy.types.Operator):
    bl_idname = "object.offset_active"
    bl_label = "Offset Active Object"
    bl_options = {'REGISTER', 'UNDO'}

    offset_x: bpy.props.FloatProperty(name="X", default=0.0, unit='LENGTH')
    offset_y: bpy.props.FloatProperty(name="Y", default=0.0, unit='LENGTH')
    offset_z: bpy.props.FloatProperty(name="Z", default=1.0, unit='LENGTH')
    use_local: bpy.props.BoolProperty(
        name="Local Axes",
        description="Offset along object's local axes instead of world axes",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            return {'CANCELLED'}

        offset = (self.offset_x, self.offset_y, self.offset_z)

        if self.use_local:
            obj.location += obj.matrix_world.to_3x3() @ bpy.types.Vector(offset)
        else:
            obj.location.x += self.offset_x
            obj.location.y += self.offset_y
            obj.location.z += self.offset_z

        return {'FINISHED'}
```

After running this operator from the menu, the user gets a redo panel in the bottom-left of the 3D viewport with sliders for `offset_x/y/z` and a `use_local` toggle. Adjusting them re-runs `execute`. This works only because `'REGISTER'` is in `bl_options` and the properties are declared as **annotations**, not assignments (see the `custom-properties` skill).

## Common AI mistakes

1. **Returning `True` / `False` from `execute`**. The required return is the set `{'FINISHED'}` or `{'CANCELLED'}`. Returning a bool will raise.

2. **Forgetting `'UNDO'` in `bl_options`**. The operator runs but the user cannot reverse it.

3. **Slow `poll`** that walks the scene, evaluates the depsgraph, or imports modules. Causes UI lag.

4. **Properties as assignments**:

   ```python
   # WRONG: the property is class-level data, not a typed annotation
   class Bad(bpy.types.Operator):
       distance = bpy.props.FloatProperty(default=0.5)

   # RIGHT: annotation form, what 2.8+ requires
   class Good(bpy.types.Operator):
       distance: bpy.props.FloatProperty(default=0.5)
   ```

   The assignment form silently does not register the property in some Blender versions and breaks the redo panel in all of them.

5. **No `bl_idname`** or a `bl_idname` without a category prefix (`my_action` instead of `mesh.my_action`). Blender requires the `category.name` shape.

6. **Calling `bpy.ops.<other>` from `execute` for bulk work**. Each `bpy.ops` call triggers a depsgraph evaluation. Operate directly on `bpy.data` or via `bmesh` instead. See the `prefer-data-over-ops-in-loops` rule.

## Related

- `addon-scaffolding` for the registration pattern around your operator class
- `custom-properties` for the annotation form
- `mesh-editing-and-bmesh` for what to do inside `execute` for mesh work
- Rule `prefer-data-over-ops-in-loops`
- Rule `type-annotate-props-and-defend-context`

## References

- `bpy.types.Operator`: https://docs.blender.org/api/current/bpy.types.Operator.html
- Operator example in the API docs: https://docs.blender.org/api/current/info_quickstart.html
