# Extension Addon Template

A minimal Blender Extensions Platform add-on, ready to copy and rename.
Targets Blender 4.5 LTS and 5.x.

## What's in here

- `blender_manifest.toml` -- the Extensions Platform manifest. Source of
  truth for id, version, name, tagline, maintainer, license, copyright,
  and minimum Blender version.
- `__init__.py` -- a working add-on with one PropertyGroup, one Operator,
  one Panel, a Scene-bound PointerProperty, and symmetric register and
  unregister.

## Use the template

1. Copy the directory to your add-on path under a new name. Pick an
   `id` (Python identifier, no hyphens) that is unique in your namespace.
2. Edit `blender_manifest.toml`:
   - Change `id`, `name`, `tagline` (max 64 characters, no trailing
     period), `maintainer`, `version`, and `website`.
   - Adjust `tags` to match your add-on's category. Allowed values come
     from the Extensions Platform tag list.
   - Set `blender_version_min` to the lowest Blender you actually
     support.
3. Edit `__init__.py`:
   - Rename the class prefix from `EXAMPLE_` to a 2 to 6 letter prefix
     unique to your add-on (Blender's RNA convention).
   - Update `bl_idname` on the operator and panel.
   - Update the `bpy.types.Scene.example_addon` attribute name.
   - Update `bl_info` (kept for legacy fallback) to match the manifest.

## Install for development

From inside Blender:

1. Edit > Preferences > Add-ons > Install from Disk.
2. Select the directory (or zip it first).
3. Enable the add-on.

The panel appears under `View3D > N-panel > Example` (rename when you
edit `bl_category`).

## Package for distribution

Use the Blender CLI to build a valid extension zip:

```powershell
blender --command extension build --source-dir .\my_addon --output-dir .\dist
```

The resulting zip is the artifact to upload to the Extensions Platform
or distribute directly.

## Conventions to keep

- Properties on classes use type-annotation form (`factor: bpy.props.X(...)`)
  not assignment form.
- `bl_options = {'REGISTER', 'UNDO'}` on operators that mutate scene
  state, so undo and operator redo work.
- `register()` adds the `PointerProperty` after `_register()` runs.
  `unregister()` deletes the `PointerProperty` before `_unregister()`
  invalidates the PropertyGroup type.
- `poll(cls, context)` filters operators out of menus when the
  precondition fails.

## Reference

- Extensions Platform manual:
  https://docs.blender.org/manual/en/latest/advanced/extensions/index.html
- Add-on tutorial:
  https://docs.blender.org/manual/en/latest/advanced/scripting/addon_tutorial.html
- Skill `addon-scaffolding` in this repo for the why behind these
  conventions.
- Rule `target-extensions-platform-format` for the migration story from
  legacy `bl_info`-only add-ons.
