---
name: custom-properties
description: Define and bind Blender custom properties via bpy.props using the type annotation form, with PropertyGroup for grouping, PointerProperty for binding, and the four storage location options for Scene/Object/WindowManager/AddonPreferences. Targets 5.1.
standards-version: 1.9.4
---

# Custom Properties

## Trigger

Use this skill when the user:

- Wants to attach data to objects, scenes, or other Blender datablocks that survives save and load
- Mentions `bpy.props`, `PropertyGroup`, `PointerProperty`, "custom properties"
- Is unsure where to store add-on settings
- Sees a deprecation warning about property assignment

## Required inputs

- **What you want to store**: a single number, a small struct, a list of items, or a complex hierarchy
- **Where it should live**: Scene (per-document), Object (per-object), WindowManager (session-only), AddonPreferences (per-user)
- **Whether it must persist** through save/load (almost always yes)

## The type annotation form (mandatory since 2.8)

```python
import bpy


class MY_ADDON_PG_settings(bpy.types.PropertyGroup):
    intensity: bpy.props.FloatProperty(
        name="Intensity",
        description="How strong the effect is",
        default=1.0,
        min=0.0,
        max=10.0,
    )
    use_smoothing: bpy.props.BoolProperty(name="Smooth", default=True)
    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ('FAST', "Fast", "Lower quality, faster"),
            ('GOOD', "Good", "Balanced"),
            ('BEST', "Best", "Best quality, slower"),
        ],
        default='GOOD',
    )
```

The properties are declared with `:` (PEP 526 annotations), not `=` (assignment). Blender's metaclass scans the annotation namespace and registers each `bpy.props.*` it finds.

The assignment form (`intensity = bpy.props.FloatProperty(...)`) is **deprecated 2.8+ syntax**. It silently does the wrong thing in some Blender versions and is rejected in others. Always use annotations.

See the rule `type-annotate-props-and-defend-context` for the rationale and the lint pattern.

## The `bpy.props` types

| Type | Stores |
| --- | --- |
| `BoolProperty` | One bool |
| `IntProperty` | One signed int |
| `FloatProperty` | One float |
| `StringProperty` | A unicode string, optionally a `subtype='FILE_PATH'` |
| `EnumProperty` | One choice from a fixed list, with optional `options={'ENUM_FLAG'}` for multi-select |
| `BoolVectorProperty` | A fixed-size array of bools (size up to 32) |
| `IntVectorProperty` | A fixed-size array of ints |
| `FloatVectorProperty` | A fixed-size array of floats, often with `subtype='COLOR'` or `subtype='TRANSLATION'` |
| `PointerProperty` | A reference to another `PropertyGroup` (or built-in datablock type) |
| `CollectionProperty` | An ordered, named list of `PropertyGroup` instances |

Use `subtype` to get UI semantics for free: `'COLOR'` opens a color picker, `'FILE_PATH'` opens a file dialog, `'TRANSLATION'`/`'XYZ'`/`'EULER'` get the right unit display.

## Where to store the data

Custom properties are bound to a Blender type as a class attribute:

```python
bpy.types.Scene.my_addon = bpy.props.PointerProperty(type=MY_ADDON_PG_settings)
```

This makes `bpy.data.scenes['Scene'].my_addon.intensity` work for every Scene in the file.

The four conventional storage locations and their tradeoffs:

| Location | Persistence | Scope | Use for |
| --- | --- | --- | --- |
| `bpy.types.Scene.x` | Saved with the .blend | Per-Scene (per-document) | Add-on state that should travel with the file (export settings, custom render passes, baked data references) |
| `bpy.types.Object.x` | Saved with the .blend | Per-Object | Per-object metadata (constraint config, custom rig data, asset tags) |
| `bpy.types.WindowManager.x` | Session-only, **not** saved | Global to the running Blender | Transient state (last used path, current modal step, temp UI flags) |
| `AddonPreferences` | Saved with the user preferences | Per-user, global | API keys, default paths, "always do X" preferences |

You can also bind to `bpy.types.Mesh`, `bpy.types.Material`, `bpy.types.Armature`, etc. for datablock-specific data.

### Picking storage

- **Will the user expect to save and reopen the file with these values?** Yes -> `Scene` or `Object`.
- **Per-document or per-object?** Per-document -> `Scene`. Per-object -> `Object`.
- **User-global, like an API key?** -> `AddonPreferences`.
- **Transient session state, like the current step of a wizard?** -> `WindowManager`.

## The `PropertyGroup` plus `PointerProperty` pattern

Group your add-on's settings into one `PropertyGroup` and bind that group via a single `PointerProperty`:

```python
class MY_ADDON_PG_settings(bpy.types.PropertyGroup):
    intensity: bpy.props.FloatProperty(default=1.0)
    use_smoothing: bpy.props.BoolProperty(default=True)


def register():
    bpy.utils.register_class(MY_ADDON_PG_settings)
    bpy.types.Scene.my_addon = bpy.props.PointerProperty(type=MY_ADDON_PG_settings)


def unregister():
    del bpy.types.Scene.my_addon
    bpy.utils.unregister_class(MY_ADDON_PG_settings)
```

You then access:

```python
scene = context.scene
scene.my_addon.intensity = 2.0
```

This is far cleaner than binding individual `FloatProperty`s directly to `Scene`. It also gives you a clear unregister target.

### `del` first, then `unregister_class`

The order matters. The bound `PointerProperty` references the `PropertyGroup` class. If you unregister the class first, the binding becomes dangling and Blender crashes on next save. Always:

```python
def unregister():
    del bpy.types.Scene.my_addon  # or property_unset() on 5.0+
    bpy.utils.unregister_class(MY_ADDON_PG_settings)
```

See the snippet `cross-version-property-delete.py` for the 5.0+ `property_unset` shape and the 4.5 LTS `del` shape.

## CollectionProperty (lists)

```python
class MY_ADDON_PG_item(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    enabled: bpy.props.BoolProperty(default=True)


class MY_ADDON_PG_settings(bpy.types.PropertyGroup):
    items: bpy.props.CollectionProperty(type=MY_ADDON_PG_item)
    active_index: bpy.props.IntProperty(default=0)
```

Add an item:

```python
new_item = scene.my_addon.items.add()
new_item.name = "First"
```

Remove by index:

```python
scene.my_addon.items.remove(0)
```

`CollectionProperty` plus a paired `active_index: IntProperty` is the canonical pattern for `bpy.types.UIList` integration.

## AddonPreferences

For per-user, global data:

```python
class MY_ADDON_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__  # the add-on's package name

    api_key: bpy.props.StringProperty(name="API Key", subtype='PASSWORD')
    default_export_path: bpy.props.StringProperty(name="Default Export Path", subtype='DIR_PATH')

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "api_key")
        layout.prop(self, "default_export_path")
```

Access via:

```python
prefs = context.preferences.addons[__package__].preferences
api_key = prefs.api_key
```

`AddonPreferences` data persists in the user's preferences (`userpref.blend`), not the current document. Do not store per-document state here.

## Why "just use Python attributes" does not work

```python
# WRONG: this attribute does not survive save and load.
bpy.context.scene.my_intensity = 1.5
```

Properties attached as plain Python attributes to a Blender datablock are not serialized into the `.blend` file. The .blend file format only saves registered `bpy.props`. Reload the file and the value is gone.

This is a frequent AI mistake when generating quick scripts. Always wrap state in a `PropertyGroup` bound via `PointerProperty` if it must persist.

## Common AI mistakes

1. **Assignment form for properties**:

   ```python
   class Bad(bpy.types.PropertyGroup):
       intensity = bpy.props.FloatProperty(default=0.5)  # silently broken
   ```

   See the rule `type-annotate-props-and-defend-context`.

2. **Storing complex state on Python attributes**:

   ```python
   scene.my_data = {"items": [...]}  # gone after save and reload
   ```

3. **Wrong unregister order** (unregister class before deleting binding) -> crash on save.

4. **Binding individual properties directly to Scene** instead of grouping into a `PropertyGroup`. Hard to unregister cleanly, pollutes the namespace.

5. **Storing per-document state in `AddonPreferences`** -> data leaks across files.

6. **Confusing `subtype='FILE_PATH'` and `'DIR_PATH'`**. `'FILE_PATH'` lets the user pick a file, `'DIR_PATH'` a directory.

## Compatibility paths (4.5 LTS vs 5.0+)

In Blender 5.0+, `bpy.types.Scene.my_addon.property_unset(...)` is the preferred unbind for individual props. In 4.5 LTS, `del bpy.types.Scene.my_addon` is still required for `PointerProperty` bindings. The snippet `cross-version-property-delete.py` shows both.

## Related

- `addon-scaffolding` for the registration boilerplate that wraps property registration
- `ui-panels` for `layout.prop` reading these properties
- Rule `type-annotate-props-and-defend-context`

## References

- `bpy.props` reference: https://docs.blender.org/api/current/bpy.props.html
- `bpy.types.PropertyGroup`: https://docs.blender.org/api/current/bpy.types.PropertyGroup.html
- `bpy.types.AddonPreferences`: https://docs.blender.org/api/current/bpy.types.AddonPreferences.html
