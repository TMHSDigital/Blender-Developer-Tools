---
name: bl-info-migration
description: "Migrate a legacy bl_info add-on to the Extensions Platform in three steps, with a before/after diff and the dual-format pattern. Use when the user has a bl_info dictionary in __init__.py, asks whether bl_info is deprecated or still supported, wants to publish to extensions.blender.org or ship an extension .zip, or sees warnings about legacy add-ons at install time. Targets 5.2 LTS; manifests work from 4.2."
standards-version: 1.10.0
---

# bl_info Migration to the Extensions Platform

## Trigger

Use this skill when the user:

- Has an existing add-on with a `bl_info = {...}` dictionary at the top of `__init__.py`
- Wants to publish to extensions.blender.org or distribute as a `.zip` for the Extensions Platform
- Asks "is bl_info dead?" or "do I have to migrate?"
- Sees a deprecation warning at install time about legacy add-ons
- Mentions `blender_manifest.toml`, "Install legacy Add-on", or "the new extension system"

## Is bl_info still supported?

Yes, with caveats.

- **In 5.2 LTS (current stable; 5.1 is prior stable)**: `bl_info` is supported as a fallback for legacy add-ons. The Edit > Preferences > Add-ons panel still has "Install legacy Add-on" and recognizes `bl_info` dicts.
- **For the Extensions Platform** (extensions.blender.org and the new add-ons UI): you need a `blender_manifest.toml`. `bl_info` is ignored.
- **Dual format** is officially recognized: ship a `blender_manifest.toml` and keep the `bl_info` dict. The platform reads the manifest; legacy installers read `bl_info`. Both code paths work without conditional logic.

The Blender Foundation's stated direction is that the Extensions Platform is the future and `bl_info`-only add-ons will degrade in discoverability over time, but they are not announcing a removal date.

## The three migration steps

A migration from a `bl_info`-only add-on to the Extensions Platform takes three small mechanical changes.

### Step 1: Generate `blender_manifest.toml`

Create a new file `blender_manifest.toml` next to `__init__.py`. Translate the `bl_info` fields:

| `bl_info` key | Manifest key | Notes |
| --- | --- | --- |
| `"name"` | `name = "..."` | Same string |
| `"version": (1, 2, 3)` | `version = "1.2.3"` | Tuple becomes a string |
| `"blender": (4, 5, 0)` | `blender_version_min = "4.5.0"` | Renamed; semantics same |
| `"author"` | `maintainer = "Author <email>"` | Email recommended |
| `"description"` | `tagline = "..."` | Renamed |
| `"category"` | `tags = ["..."]` | Now a list of allowed tags |
| `"location"`, `"warning"` | (no equivalent) | Drop |
| (none) | `id = "..."` | New required field; a Python identifier such as `my_tool` (no dots, so not reverse-DNS; no `__`; no leading or trailing `_`) |
| (none) | `schema_version = "1.0.0"` | Required |
| (none) | `type = "add-on"` | Required |
| (none) | `license = ["SPDX:..."]` | Required SPDX expression |

Minimal manifest:

```toml
schema_version = "1.0.0"

id = "my_addon"
version = "1.2.3"
name = "My Addon"
tagline = "What it does in one sentence"
maintainer = "Author Name <author@example.com>"
type = "add-on"

blender_version_min = "4.5.0"

license = [
    "SPDX:GPL-3.0-or-later",
]

tags = ["3D View", "Mesh"]
```

The full schema and allowed tag list live in the Blender extensions documentation.

### Step 2: Delete `bl_info` (or keep both)

If you only want to support 5.x and the Extensions Platform: delete the `bl_info = {...}` block from `__init__.py`.

If you want to keep working with the 4.x "Install legacy Add-on" path while also publishing to the platform: leave `bl_info` in place. This is the dual-format pattern. The two metadata sources do not need to agree perfectly; the platform reads only the manifest, the legacy installer reads only `bl_info`.

### Step 3: Convert imports to relative or `__package__`

Legacy add-ons commonly use absolute imports:

```python
from my_addon import operators
from my_addon.ui import panels
```

These break under the Extensions Platform because the package name is no longer `my_addon` at runtime; it's a generated synthetic name like `bl_ext.user_default.my_addon`. Two fixes that work everywhere:

**Relative imports**:

```python
from . import operators
from .ui import panels
```

**`__package__` lookup** (when you need the full package name as a string):

```python
import importlib

operators = importlib.import_module(f"{__package__}.operators")
```

Both forms are stable across the legacy and Extensions Platform load paths.

### Step 4: Replace hard-coded add-on names with `__package__`

Imports are not the only place the old module name hides. Any string literal that names the add-on breaks the same way after migration, because the module is now `bl_ext.<repo>.<id>`:

```python
# Before: breaks once installed as an extension
prefs = context.preferences.addons["my_addon"].preferences  # KeyError

class MyAddonPrefs(bpy.types.AddonPreferences):
    bl_idname = __name__  # wrong when this class lives in a submodule
```

```python
# After: __package__ carries the full runtime name
prefs = context.preferences.addons[__package__].preferences

class MyAddonPrefs(bpy.types.AddonPreferences):
    bl_idname = __package__
```

Measured on 5.2.1 LTS with an installed test extension (`bl_ext.user_default.probe_good`):

- `context.preferences.addons["probe_good"]` raises `KeyError`. The add-on is listed only under `bl_ext.user_default.probe_good`.
- In a submodule `prefs.py`, `__name__` is `bl_ext.user_default.probe_good.prefs` and `__package__` is `bl_ext.user_default.probe_good`.
- An `AddonPreferences` subclass with `bl_idname = __name__` in that submodule still registers without an error, but `addons[pkg].preferences` is `None`. The preferences silently disappear. With `bl_idname = __package__` it returns the class instance.

`__package__` names the root only one level down. In a deeper module such as `ui/panels.py` it is `bl_ext.<repo>.<id>.ui`. Take the root name from the top-level `__init__.py` (where `__package__ == __name__`) and pass it down, rather than slicing strings. Grep the add-on for its old name in quotes (`"my_addon"`, `'my_addon'`) and for `bl_idname = __name__`. The [`custom-properties`](${CLAUDE_PLUGIN_ROOT}/skills/custom-properties/SKILL.md) skill shows the `AddonPreferences` pattern with `__package__`.

## Worked example: before and after

### Before (legacy, single file `__init__.py`)

```python
bl_info = {
    "name": "Cube Tools",
    "author": "Acme <acme@example.com>",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Cube",
    "description": "Quick cube operations",
    "category": "Object",
}

import bpy
from cube_tools import operators
from cube_tools.ui import panels


def register():
    operators.register()
    panels.register()


def unregister():
    panels.unregister()
    operators.unregister()
```

### After (Extensions Platform)

`blender_manifest.toml`:

```toml
schema_version = "1.0.0"

id = "cube_tools"
version = "1.0.0"
name = "Cube Tools"
tagline = "Quick cube operations"
maintainer = "Acme <acme@example.com>"
type = "add-on"

blender_version_min = "4.5.0"

license = [
    "SPDX:GPL-3.0-or-later",
]

tags = ["Object"]
```

`__init__.py`:

```python
import bpy

from . import operators
from .ui import panels


def register():
    operators.register()
    panels.register()


def unregister():
    panels.unregister()
    operators.unregister()
```

The `bl_info` dict is gone; the imports are now relative; everything else is identical.

### After (dual format, supports both load paths)

Same `blender_manifest.toml` as above, plus keeping a slimmed `bl_info` for 4.x legacy users:

```python
bl_info = {
    "name": "Cube Tools",
    "author": "Acme",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "category": "Object",
}

import bpy
from . import operators
from .ui import panels
```

Note: the imports are still relative. Relative imports work in both load paths; absolute imports only work in the legacy path.

## Packaging for distribution

Once the manifest exists, build the Extension `.zip`:

```powershell
blender --command extension build --source-dir .\cube_tools --output-dir .\dist
```

This produces a `.zip` in `dist\` that the user installs via Edit > Preferences > Add-ons > Install... or that you upload to extensions.blender.org.

## Common AI mistakes

- **Forgetting `id` in the manifest.** `id` is required and must be a stable slug; changing it later is a breaking change that disconnects users from updates.
- **Using a tuple for `version` in the manifest.** `bl_info` uses tuples, the manifest uses a string. Dot-separated semver, e.g., `"1.2.3"`.
- **Keeping absolute imports during dual-format migration.** They break at runtime under the Extensions Platform load path. Convert to relative.
- **Skipping SPDX in `license`.** The platform rejects manifests without a license expression. `["SPDX:GPL-3.0-or-later"]` matches typical Blender add-on practice; commercial add-ons use other SPDX strings.
- **Misnaming the file.** It must be exactly `blender_manifest.toml`, lowercase, in the package root.
- **Mixing `permissions` defaults**. The manifest has a `permissions` key for network, file IO, etc. Default to declaring nothing if you don't need elevated permissions; over-declaration triggers user warnings.

## Version correctness

| Topic | 4.5 LTS | 5.1 / 5.2 LTS |
| --- | --- | --- |
| `bl_info` recognized | Yes (legacy; Extensions is the primary path since 4.2) | Yes (legacy fallback only) |
| `blender_manifest.toml` recognized | Yes (Extensions Platform was added in 4.2) | Yes |
| Synthetic package name | `bl_ext.<repo>.<id>` | Same |
| `extension build` command | Available | Available |
| Schema version | `1.0.0` | `1.0.0` |

The Extensions Platform shipped in Blender 4.2. Migrations done now will work on 4.2+ and 5.x without further changes. Code targeting 4.1 or earlier still needs the `bl_info` path.

## See also

- Skill `addon-scaffolding`: scaffolding a new Extensions Platform add-on from scratch.
- Rule `target-extensions-platform-format`: encodes the policy that new add-ons should be Extensions-first.
- Template `extension-addon-template`: a working starter to compare your migration against.

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

No runnable example proves this skill yet (tracked in [#378](https://github.com/TMHSDigital/Blender-Developer-Tools/issues/378)).

<!-- examples:end -->

## References

- Blender Extensions documentation: https://developer.blender.org/docs/handbook/extensions/
- `blender_manifest.toml` schema: https://developer.blender.org/docs/handbook/extensions/schema/
- Blender 4.2 release notes (Extensions Platform launch): https://developer.blender.org/docs/release_notes/4.2/extensions/
- SPDX license expression list: https://spdx.org/licenses/
