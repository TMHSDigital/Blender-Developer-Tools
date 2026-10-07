---
name: operators
description: "Author bpy.types.Operator classes: bl_idname naming, poll / invoke / execute / modal lifecycle, bl_options (REGISTER, UNDO, INTERNAL, BLOCKING), operator properties and defensive context handling. Use when the user creates an operator for a button, menu, keymap or script, asks why its properties are missing from the Adjust Last Operation (redo) panel or why Ctrl-Z ignores it, or gets poll failures or None context objects. Targets 5.2 LTS with 4.5 LTS compatibility."
standards-version: 1.10.0
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


class MESH_OT_offset_along_normals(bpy.types.Operator):
    bl_idname = "mesh.offset_along_normals"
    bl_label = "Offset Along Normals"
    bl_description = "Move every vertex of the active mesh a fixed distance along its normal"
    bl_options = {'REGISTER', 'UNDO'}

    distance: bpy.props.FloatProperty(
        name="Distance",
        description="How far to move each vertex",
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

        # Operate on bpy.data, not bpy.ops, and in bulk: one foreach_get /
        # foreach_set pair instead of a Python loop over mesh.vertices (rule
        # use-foreach-set-for-bulk-data). See the mesh-editing-and-bmesh skill.
        mesh = obj.data
        n = len(mesh.vertices)
        co = [0.0] * (n * 3)
        nor = [0.0] * (n * 3)
        mesh.vertices.foreach_get("co", co)
        mesh.vertices.foreach_get("normal", nor)
        d = self.distance
        mesh.vertices.foreach_set("co", [c + k * d for c, k in zip(co, nor)])

        mesh.update()
        self.report({'INFO'}, f"Offset {n} vertices by {d:.3f}")
        return {'FINISHED'}
```

## The lifecycle methods

| Method | Required | Called when | Returns |
| --- | --- | --- | --- |
| `poll(cls, context)` | Optional | Every UI redraw to decide if the operator is enabled. Must be cheap. | `True` to enable, `False` or falsy to disable |
| `invoke(self, context, event)` | Optional | The user triggers the operator interactively (button, menu, keymap). Default forwards to `execute`. | `{'FINISHED'}`, `{'CANCELLED'}`, `{'PASS_THROUGH'}`, `{'RUNNING_MODAL'}` |
| `execute(self, context)` | Yes | The operator runs, either after `invoke` or directly via `bpy.ops.mesh.offset_along_normals()` | `{'FINISHED'}` or `{'CANCELLED'}` |
| `modal(self, context, event)` | Optional | After `invoke` returns `{'RUNNING_MODAL'}`. Called for each event until you return `{'FINISHED'}` or `{'CANCELLED'}`. | Standard return set |
| `draw(self, context)` | Optional | The redo panel after the operator runs. Defaults to drawing all properties. | None |

### `poll` must be fast

`poll` runs on every UI redraw. **Do not iterate the scene, scan meshes, or call modifiers there.** Restrict yourself to `context.active_object`, `obj.type`, `obj.mode`, and similar O(1) checks.

### `bl_options` you almost always want

- `'REGISTER'`: reports the operator in the Info editor and enables the Adjust Last Operation (redo) panel. Without it, properties cannot be tweaked after running. It does not add an undo step; that is `'UNDO'`.
- `'UNDO'`: hooks into the undo stack. Without this, your operator's effect cannot be undone with Ctrl-Z.
- `'INTERNAL'`: hides the operator from operator search. Use for operators called only by other operators or panels. It still runs from Python and buttons.
- `'BLOCKING'`: blocks anything else from using the cursor while the operator runs. Reserve for modal operators that need exclusive mouse input.
- `'GRAB_CURSOR'` and `'GRAB_CURSOR_X'` / `'GRAB_CURSOR_Y'`: useful in modal operators to capture mouse motion.

## Defensive context handling

`context.active_object` returns `None` only when there is no active object:

- An empty scene, such as after `read_factory_settings(use_empty=True)`, or a file whose view layer never had one.
- The active object was deleted.
- A context override sets `active_object=None` deliberately.

It is **not** `None` just because nothing is selected, and not just because Blender runs headless. Measured on 4.5.11 and 5.2.1 (`--background --factory-startup`): the startup scene's active object is `Cube`, and after `bpy.ops.object.select_all(action='DESELECT')` it is still `Cube`, with `selected_objects == []` and `Cube.select_get() == False`.

**Active and selected are independent.** That is the real pitfall: an active object that is not selected, hidden, or not editable. A `None` guard does not catch it. Operators that act on the selection then run on nothing, or on the wrong set, without raising. Measured: `bpy.ops.object.delete()` with the Cube active but deselected returns `{'CANCELLED'}` and the Cube survives. When the operation needs selection, check `obj.select_get()` or work from `context.selected_objects`. Check `obj.visible_get()` before acting on what the user sees. Check `obj.library is None` (and `obj.override_library` if you edit overrides) before writing to linked data.

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
    if not obj.select_get():  # active is not selected after a deselect-all
        self.report({'ERROR'}, f"{obj.name} is active but not selected")
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
from mathutils import Vector


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
            # Column-normalize the basis so object scale does not distort the
            # local-axis direction; to_3x3() alone carries scale into the result.
            basis = obj.matrix_world.to_3x3().normalized()
            obj.location += basis @ Vector(offset)
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

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`prop-origin-transform`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/prop-origin-transform): Street pedestal origin-to-base-center + data-API scale apply + matrix_parent_inverse for a flanged conduit elbow. Falsify: `--skip-mpi` (exit 8).
- [`temp-override-join`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/temp-override-join): Join seven lantern parts into one object under bpy.context.temp_override — the supported replacement for the removed context.copy() dict-pass form. Falsify: `--no-override` (exit 3).
- [`timers-modal-threading`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/main/examples/timers-modal-threading): Proves the event-loop contracts behind long-running add-on work. Falsify: `--windowed-background-child` (exit 3).

<!-- examples:end -->

## References

- `bpy.types.Operator`: https://docs.blender.org/api/current/bpy.types.Operator.html
- Operator example in the API docs: https://docs.blender.org/api/current/info_quickstart.html
