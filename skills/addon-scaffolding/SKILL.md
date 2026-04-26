---
name: addon-scaffolding
description: Scaffold a Blender add-on against the Extensions Platform format with blender_manifest.toml, modular file layout, and the register_classes_factory pattern. Targets Blender 5.1 with 4.5 LTS fallback.
standards-version: 1.9.4
---

# Addon Scaffolding (Extensions Platform)

## Trigger

Use this skill when the user:

- Wants to start a new Blender add-on
- Mentions `bl_info`, `blender_manifest.toml`, "extension", "register_classes_factory"
- Is migrating an existing add-on from the legacy `bl_info` format to the Extensions Platform
- Is unsure which file layout or registration pattern to use for Blender 4.5+ or 5.x

## Required inputs

- **Add-on name and short id** (snake_case for the manifest `id`, human-readable `name`)
- **Target Blender versions** (defaults to `blender_version_min = "4.5.0"` so the add-on works on 4.5 LTS and 5.1)
- **Maintainer string** (`Name <email@example.com>` form)
- **License SPDX identifier** (`SPDX:MIT`, `SPDX:GPL-2.0-or-later`, etc.)

## The Extensions Platform format (5.x default)

Since 4.2 and required in 5.x for new submissions to the official extensions site, add-ons ship as Extensions. An Extension is a directory containing a `blender_manifest.toml` plus Python modules.

### `blender_manifest.toml` required fields

```toml
schema_version = "1.0.0"

id = "my_addon"
version = "0.1.0"
name = "My Add-on"
tagline = "Short description, max 64 chars, no trailing period"
maintainer = "TMHSDigital <contact@example.com>"
type = "add-on"

blender_version_min = "4.5.0"

license = ["SPDX:MIT"]
copyright = ["2026 TMHSDigital"]
```

Field rules that AIs commonly get wrong:

- `tagline` is hard-capped at 64 characters and **must not end with a period**. Blender's manifest validator rejects both.
- `id` must be a valid Python identifier (`[A-Za-z_][A-Za-z0-9_]*`). The directory name does not need to match the `id` but conventionally does.
- `license` and `copyright` are **arrays of strings**, not bare strings.
- `blender_version_min` is the floor. Setting it to `"4.5.0"` lets the same code run on 4.5 LTS and any 5.x. Setting it to `"5.0.0"` cuts off LTS users with no warning.
- `schema_version` is `"1.0.0"` for the current manifest schema. Do not bump it.

Optional but commonly wanted:

```toml
website = "https://github.com/TMHSDigital/your-repo"
tags = ["Mesh", "Geometry Nodes"]
permissions = { network = "Optional, only used to fetch updates" }
```

`tags` must come from Blender's known tag list. `permissions` is a dict of granted-permission to human-readable reason; if omitted, the extension is sandboxed against network, files, clipboard, and camera.

## File layout

The conventional layout for a non-trivial add-on:

```
my_addon/
  blender_manifest.toml
  __init__.py            # registration entry point only
  operators.py           # Operator subclasses
  panels.py              # Panel subclasses
  properties.py          # PropertyGroup subclasses, PointerProperty bindings
  utils.py               # Pure helpers, no bpy imports beyond types
```

Keep `__init__.py` small. It registers and unregisters classes; everything else lives in submodules.

## The `register_classes_factory` pattern

This is the canonical 5.x registration pattern. It eliminates the loop boilerplate that AIs frequently bug.

```python
import bpy
from bpy.utils import register_classes_factory

from . import operators, panels, properties

classes = (
    properties.MyAddonProperties,
    operators.MESH_OT_my_addon_action,
    panels.VIEW3D_PT_my_addon,
)

_register_classes, _unregister_classes = register_classes_factory(classes)


def register():
    _register_classes()
    bpy.types.Scene.my_addon = bpy.props.PointerProperty(type=properties.MyAddonProperties)


def unregister():
    del bpy.types.Scene.my_addon
    _unregister_classes()
```

Why this pattern:

- `register_classes_factory` returns a `(register, unregister)` pair that loops over `classes` in the right direction (forward for register, reverse for unregister) and skips the wrong-order foot-gun.
- Properties bound to types (`bpy.types.Scene.my_addon = ...`) **must be deleted before** the corresponding `PropertyGroup` class is unregistered. Hence `del bpy.types.Scene.my_addon` precedes `_unregister_classes()`.
- Class registration order matters: `PropertyGroup` subclasses must come before any class that references them via `PointerProperty`.

## Working example: minimal __init__.py

```python
import bpy
from bpy.utils import register_classes_factory


class MY_ADDON_PG_settings(bpy.types.PropertyGroup):
    intensity: bpy.props.FloatProperty(name="Intensity", default=1.0, min=0.0, max=10.0)


class MESH_OT_my_addon_action(bpy.types.Operator):
    bl_idname = "mesh.my_addon_action"
    bl_label = "My Addon Action"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.my_addon
        self.report({'INFO'}, f"Ran on {obj.name} with intensity {settings.intensity:.2f}")
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
        layout.operator("mesh.my_addon_action")


classes = (
    MY_ADDON_PG_settings,
    MESH_OT_my_addon_action,
    VIEW3D_PT_my_addon,
)

_register_classes, _unregister_classes = register_classes_factory(classes)


def register():
    _register_classes()
    bpy.types.Scene.my_addon = bpy.props.PointerProperty(type=MY_ADDON_PG_settings)


def unregister():
    del bpy.types.Scene.my_addon
    _unregister_classes()
```

## Common AI mistakes

1. **Emitting only `bl_info` and skipping `blender_manifest.toml`**. New add-ons must ship as Extensions for the official extensions platform. `bl_info` may appear alongside the manifest as a fallback for backward compatibility, but the manifest is the source of truth.

2. **Manual register/unregister loops with the wrong direction**:

   ```python
   # WRONG: same direction in unregister, classes referencing each other will fail
   for cls in classes:
       bpy.utils.register_class(cls)

   def unregister():
       for cls in classes:
           bpy.utils.unregister_class(cls)  # missing reversed()
   ```

   Use `register_classes_factory` and let it own the order.

3. **Forgetting to delete bound properties before unregister**. Trying to unregister `MY_ADDON_PG_settings` while `bpy.types.Scene.my_addon` still points to it will hard-fail on Blender restart and leak.

4. **Overlong tagline or trailing period in tagline**. The validator rejects both.

5. **Hardcoding `blender_version_min = "5.0.0"` without reason**. Cuts off the LTS user base. Default to `"4.5.0"` unless you genuinely require a 5.x-only API.

## Compatibility paths

For libraries you want to be installable on both 4.5 LTS and 5.1, also keep `bl_info` for 4.5 fallback even though new submissions to the extensions platform require the manifest. Blender prefers the manifest when both are present.

```python
bl_info = {
    "name": "My Addon",
    "blender": (4, 5, 0),
    "version": (0, 1, 0),
    "category": "Mesh",
}
```

## Related

- See the `extension-addon-template` template under `templates/` for a ready-to-copy version of this layout.
- See the `operators`, `ui-panels`, and `custom-properties` skills for the contents of each submodule.
- See rules `target-extensions-platform-format` and `type-annotate-props-and-defend-context`.

## References

- Extensions Platform manual: https://docs.blender.org/manual/en/latest/advanced/extensions/index.html
- `bpy.utils.register_classes_factory`: https://docs.blender.org/api/current/bpy.utils.html
- Manifest reference: https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html
