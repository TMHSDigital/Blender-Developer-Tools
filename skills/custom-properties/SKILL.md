---
name: custom-properties
description: "Define and bind custom properties with bpy.props annotations, PropertyGroup and PointerProperty, and choose where to store them (Scene, Object, WindowManager, AddonPreferences). Use when the user attaches settings or data to datablocks so it survives save and load, is unsure where add-on settings belong, or writes a property as an assignment instead of an annotation and gets a deprecation warning or a _PropertyDeferred value. Targets 5.2 LTS."
standards-version: 1.10.0
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
    del bpy.types.Scene.my_addon
    bpy.utils.unregister_class(MY_ADDON_PG_settings)
```

Unbinding a type-level property is `del bpy.types.Scene.my_addon` on all Blender versions. See the snippet `cross-version-property-delete.py` for removing a custom ID property (also `del`, version-stable).

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
# WRONG: raises AttributeError: 'Scene' object has no attribute 'my_intensity'
bpy.context.scene.my_intensity = 1.5
```

Blender datablocks do not accept arbitrary Python attributes: the assignment fails immediately, on 4.5 LTS and 5.x alike. Only registered `bpy.props` (or ID properties set with `scene["key"] = value`) exist on a datablock and are saved into the `.blend` file.

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
   scene.my_data = {"items": [...]}  # AttributeError: not a registered property
   ```

   Ad-hoc ID properties (`scene["my_data"] = ...`) do save, but they are untyped and invisible to the UI; use a `PropertyGroup` for anything an add-on owns.

3. **Wrong unregister order** (unregister class before deleting binding) -> crash on save.

4. **Binding individual properties directly to Scene** instead of grouping into a `PropertyGroup`. Hard to unregister cleanly, pollutes the namespace.

5. **Storing per-document state in `AddonPreferences`** -> data leaks across files.

6. **Confusing `subtype='FILE_PATH'` and `'DIR_PATH'`**. `'FILE_PATH'` lets the user pick a file, `'DIR_PATH'` a directory.

7. **Reading a registered property as an ID property on 5.x**: `scene["my_prop"]`, `"my_prop" in scene.keys()`, `del scene["my_prop"]`, or a driver path of `'["my_prop"]'`. These worked on 4.x and raise `KeyError` / `ValueError` (or silently skip the prop) on 5.0+. Use `scene.my_prop`, `scene.property_unset("my_prop")`, `scene.is_property_set("my_prop")` and the plain `"my_prop"` path. See the compatibility section below.

## Compatibility paths (4.5 LTS vs 5.0+)

### Registered properties are not ID properties on 5.0+

On 4.x a value assigned to a registered `bpy.props` property was stored as an ID property, so dict-style access reached it. On 5.0+ it lives in a separate system-property group. Measured with `bpy.types.Scene.my_prop = IntProperty(default=1)` and `scene.my_prop = 5`:

| Access | 4.5 LTS | 5.0+ (5.1.2, 5.2.1) |
| --- | --- | --- |
| `scene.my_prop` | 5 | 5 |
| `scene["my_prop"]` | 5 | `KeyError` |
| `scene.get("my_prop")` | 5 | `None` |
| `"my_prop" in scene.keys()` | True | False |
| `del scene["my_prop"]` | resets to default | `KeyError` |
| `scene.path_resolve('["my_prop"]')` (driver / keyframe path) | 5 | `ValueError` |
| `scene.path_resolve("my_prop")` | 5 | 5 |
| `scene.property_unset("my_prop")`, `scene.is_property_set("my_prop")` | work | work |

So the cross-version code needs no branch: use attribute access to read and write, `property_unset()` to reset, `is_property_set()` to test, and the plain `"my_prop"` path for drivers and keyframes. `keys()` lists only user custom properties on 5.0+; the raw storage is `id.bl_system_properties_get()` (5.0+ only), which you should rarely need. A value saved by 4.5 still loads as the attribute on 5.2. Witness: [`examples/cross-version-property-delete/`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/cross-version-property-delete) (exit 8, falsifier `--subscript-registered`).

### Deleting

Two distinct operations, both version-stable via `del`:

- **Unbind a type-level property** (e.g. a `PointerProperty` bound to `bpy.types.Scene`): `del bpy.types.Scene.my_addon`. Same on 4.5 LTS and 5.0+.
- **Remove a custom ID property** (the dict-style `obj["key"]`): `del obj["key"]`. Same on 4.5 LTS and 5.0+. The snippet `cross-version-property-delete.py` shows this.

Do not reach for `property_unset()` here. It resets a registered RNA property to its default, which is neither unbinding a type property nor removing an ID property. Conversely, `del id["name"]` is not a way to reset a *registered* property: it raises `KeyError` on 5.0+.

## Related

- `addon-scaffolding` for the registration boilerplate that wraps property registration
- `ui-panels` for `layout.prop` reading these properties
- Rule `type-annotate-props-and-defend-context`

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`cross-version-property-delete`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/cross-version-property-delete): Custom ID properties are removed with del, not property_unset. Falsify: `--skip-delete` (exit 7).

<!-- examples:end -->

## References

- `bpy.props` reference: https://docs.blender.org/api/current/bpy.props.html
- `bpy.types.PropertyGroup`: https://docs.blender.org/api/current/bpy.types.PropertyGroup.html
- `bpy.types.AddonPreferences`: https://docs.blender.org/api/current/bpy.types.AddonPreferences.html
