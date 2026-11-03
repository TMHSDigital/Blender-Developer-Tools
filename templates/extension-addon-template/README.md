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
- `tests/check_register.py` -- a headless register/unregister round-trip
  that finds your classes and ID properties itself, so it keeps working as
  the add-on grows.
- `.github/workflows/blender.yml` -- CI on Blender 4.5 LTS and 5.2 LTS:
  builds the package and runs the round-trip (see Continuous integration).

## Use the template

1. Copy the directory to your add-on path under a new name. Pick an
   `id` (Python identifier, no hyphens) that is unique in your namespace.
2. Edit `blender_manifest.toml`:
   - Change `id`, `name`, `tagline` (max 64 characters, no trailing
     period), `maintainer`, `version`, `website`, and `copyright` (it
     ships as the template author's; put your own name and year).
   - Review `license`: the template ships `SPDX:GPL-3.0-or-later`; the
     Extensions Platform hosts add-ons only under GPL-compatible licenses.
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

1. From a shell, build a package from the template directory (it holds
   `blender_manifest.toml`):
   `blender --command extension build --source-dir . --output-dir dist`
2. In Blender: Edit > Preferences > Get Extensions > the drop-down menu > Install from
   Disk, and pick the `.zip` in `dist/`. "Install from Disk" takes a `.zip`
   (or a `.py`), not a directory.
3. Enable the add-on.

For live editing without re-zipping, link the template directory into a
local extensions repository instead (Preferences > Get Extensions >
Repositories, add a "Local" repository, and place or symlink the directory
in that repository's folder).

The panel appears under `View3D > N-panel > Example` (rename when you
edit `bl_category`).

## Package for distribution

Use the Blender CLI to build a valid extension zip:

```powershell
blender --command extension build --source-dir .\my_addon --output-dir .\dist
```

The resulting zip is the artifact to upload to the Extensions Platform
or distribute directly. The manifest's `[build] paths_exclude_pattern` keeps
`tests/`, `.github/` and earlier builds out of it.

## Continuous integration

Put this directory at the root of your add-on's repository and
`.github/workflows/blender.yml` runs on every push and pull request. For each
of Blender 4.5 LTS and 5.2 LTS it resolves the newest point release, checks
the download against blender.org's published sha256, caches it, then:

1. `blender --command extension build`: build, not just validate, because
   build also checks the files it packs;
2. `tests/check_register.py`: register, check every class and ID property
   landed, unregister, check every one is gone, then register and unregister
   again. Exit 3 means register failed or is not repeatable; exit 4 names what
   survived unregister.

Run the round-trip locally the same way:

```bash
blender --background --factory-startup --python-exit-code 1 --python tests/check_register.py
# Falsifier: skip unregister; must exit 4
blender --background --factory-startup --python-exit-code 1 --python tests/check_register.py -- --skip-unregister
```

If you raise `blender_version_min`, drop the matrix series below it.

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
