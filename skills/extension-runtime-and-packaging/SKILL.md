---
name: extension-runtime-and-packaging
description: "Ship and run a Blender extension after its first install: bundled wheels, user data that survives upgrades via bpy.utils.extension_path_user, the network permission and bpy.app.online_access, bl_ext package names, and blender --command extension validate/build/server-generate in CI. Use when the user bundles third-party Python packages, pip-installs into Blender's Python, writes files next to __file__, needs a settings or cache directory, makes network calls from an add-on, or builds and publishes extension zips. Targets 5.2 LTS with 4.5 LTS fallback."
standards-version: 1.10.0
---

# Extension Runtime and Packaging

## Trigger

Use this skill when the user:

- Needs a third-party Python package inside an extension (`requests`, `numpy`, `Pillow`)
- Writes settings, caches or downloads from an add-on and asks where they should go
- Makes network calls from an add-on, or asks about the `network` permission
- Builds, validates or publishes extension zips, locally or in CI
- Hits `ValueError: The "package" does not name an extension`, or imports that work in a folder add-on but break once installed as an extension

`addon-scaffolding` covers the manifest fields, file layout and register symmetry. This skill covers what breaks after that: dependencies, data, network and packaging.

## Required inputs

- **Extension `id`** from `blender_manifest.toml` (the installed package is `bl_ext.<repo>.<id>`)
- **Target Blender versions**. The bundled Python differs: 3.11 on 4.5 LTS, 3.13 on 5.2 LTS (`sys.version_info` measured on 4.5.11 and 5.2.1)
- **Third-party packages** the code imports, and whether any ship compiled code
- **Whether the add-on touches the network**

## Where things live once installed

Measured with `blender --command extension install-file -r user_default` into a throwaway `BLENDER_USER_RESOURCES`, identical on 4.5.11, 5.1.2 and 5.2.1:

| What | Path under the user `extensions/` directory | Lifetime |
| --- | --- | --- |
| The package (`__file__`) | `user_default/<id>/` | Replaced on every upgrade |
| `extension_path_user(__package__)` | `.user/user_default/<id>/` | Survives upgrades; deleted by `extension remove` |
| Bundled wheels | `.local/lib/python3.X/site-packages/` | Outside every package directory, keyed by Python version |

The import name is `bl_ext.user_default.<id>`, not `<id>`, and `__package__` carries that full name.

## Bundling dependencies: wheels, never pip

Blender does not run `pip` for an extension, and an extension should not run it either: `pip install` into Blender's Python changes the interpreter every add-on shares and needs write access to the Blender install. The supported mechanism is wheels shipped inside the package. Per the manual, they must be bundled unmodified from PyPI and must include their own dependencies:

```toml
# blender_manifest.toml
wheels = [
  "./wheels/requests-2.32.3-py3-none-any.whl",
  "./wheels/charset_normalizer-3.4.0-cp311-cp311-win_amd64.whl",
]
```

Download them with pip on the build machine, matched to Blender's Python and each platform:

```bash
pip download requests --dest ./wheels --only-binary=:all: --python-version 3.11 --platform win_amd64
```

- A pure-Python wheel (`py3-none-any`) works everywhere. A compiled one needs a wheel per Python (`cp311` for 4.5 LTS, `cp313` for 5.2 LTS) and per platform.
- `build --split-platforms` writes one zip per platform listed in the manifest's `platforms` key, so a user downloads only their own wheels.
- `build` copies the listed wheels into the zip under `wheels/`. On install, Blender extracts them into the `site-packages` directory above, which is already on `sys.path`, so `import requests` works with no path code (measured with a hand-built wheel on 4.5.11 and 5.2.1).

## User data: `extension_path_user`, never `__file__`

```python
import os
import bpy

def settings_path():
    directory = bpy.utils.extension_path_user(__package__, path="", create=True)
    return os.path.join(directory, "settings.json")
```

- Installing a newer version replaces the whole install directory. A file written next to `__file__` is gone after the upgrade; `settings.json` in the user directory is still there (measured, 0.1.0 → 0.2.0).
- `extension remove` deletes the user directory too. If users must keep data across a reinstall, offer an explicit export.
- `extension_path_user("my_addon")` raises `ValueError: The "package" does not name an extension` for anything not shaped `bl_ext.<repo>.<id>`. A legacy folder add-on cannot use it, so code shared with a `bl_info` fallback needs its own path, such as `bpy.utils.user_resource('CONFIG', path=...)`.
- Use relative imports inside the package (`from . import ops`). The installed module is `bl_ext.user_default.my_addon`, and the repository part changes with where the user installs it, so a hardcoded absolute name is wrong somewhere.

## Network: the permission and `bpy.app.online_access`

Declaring the permission does not grant access, and code must check both:

```toml
[permissions]
network = "Downloads material presets from the project server"
```

```python
if not bpy.app.online_access:
    return None  # the user has not allowed online access; do nothing online
```

- `bpy.app.online_access` is `False` in a fresh factory-startup Blender and `True` under `blender --online-mode` (measured on all three versions). Users turn it on with **Preferences → System → Network → Allow Online Access**.
- The manifest validator accepts only `files`, `network`, `clipboard`, `camera` and `microphone` as permission keys. The permission is a declaration shown to users, not a sandbox.

## Validate is not a release gate: build in CI

`blender --command extension validate DIR` parses the manifest. It rejects a missing `id`, a non-semver `version`, an unknown `type`, an unknown permission key and a malformed `blender_version_min`. It does **not** open the files the manifest names, and does not check every value:

| Manifest defect | `validate` | `build` |
| --- | --- | --- |
| `wheels` entry whose file does not exist | exit 0 | exit 1, no zip |
| `platforms = ["win64"]` (not a platform name) | exit 0 | — |
| `schema_version = "9.9.9"` | exit 0 | — |
| missing `id` | exit 1 | exit 1 |

All four rows were measured on 4.5.11 and 5.2.1; "—" means not measured. Gate CI on `build`, which fails on what validate lets through:

```bash
blender --factory-startup --command extension validate ./my_addon
blender --factory-startup --command extension build --source-dir ./my_addon --output-dir ./dist
blender --factory-startup --command extension server-generate --repo-dir ./dist   # writes dist/index.json
```

`server-generate` writes the `index.json` listing a static extension repository needs. Each entry carries the package `id` and an `archive_url` relative to the listing (`./my_addon-0.1.0.zip`). Host `dist/` anywhere that serves files and add it as a remote repository in Blender.

To smoke-test an installed build without touching a real profile, point `BLENDER_USER_RESOURCES` at a temporary directory, then run `extension install-file -r user_default -e dist/<zip>` and a `--background --python-expr` import of `bl_ext.user_default.<id>`.

## Common AI mistakes

1. **`subprocess.run([sys.executable, "-m", "pip", "install", ...])` from `register()`**. It mutates the interpreter every add-on shares and fails without write access to the install. Bundle wheels.
2. **Writing caches or settings next to `__file__`**. The next upgrade deletes them. Use `extension_path_user(__package__, create=True)`.
3. **Calling `extension_path_user("my_addon")`** with the bare id. It raises `ValueError`; pass `__package__`.
4. **Absolute self-imports** (`import my_addon.utils`). The installed package is `bl_ext.<repo>.my_addon`, with a repository part that varies; use relative imports.
5. **Network calls gated only on the manifest permission**. Check `bpy.app.online_access` at call time; it is `False` until the user allows online access.
6. **A CI job that runs only `extension validate`**. A missing wheel passes it; run `extension build` and fail on its exit code.
7. **Compiled wheels for one Python only**. A `cp311` wheel does not import on 5.2's Python 3.13. Ship one per supported Python and platform.

## Compatibility paths

The `--command extension` subcommands, `extension_path_user`, `online_access`, the `.user` and `.local/lib/pythonX.Y/site-packages` layout, and the upgrade and remove behaviour above are the same on 4.5 LTS, 5.1 and 5.2 LTS (all measured). What changes between them is the bundled Python (3.11 → 3.13), which decides the wheel tags. Branch on `bpy.app.version` only for API differences, never for these paths.

## Related

- `addon-scaffolding`: the manifest fields, file layout and `register_classes_factory`
- `headless-batch-scripting`: running Blender unattended, which is how the CI commands above run
- The `extension-addon-template` template under [`templates/`](${CLAUDE_PLUGIN_ROOT}/templates), which the example below builds, installs and upgrades
- Snippet: [`snippets/extension-user-data.py`](${CLAUDE_PLUGIN_ROOT}/snippets/extension-user-data.py)

<!-- examples:begin (generated by scripts/build_examples_index.py from examples/skills.json; do not edit) -->
## Runnable examples

Each example runs headless, asserts the contract, and exits non-zero when it breaks. Run one with `blender --background --python <script> --`; pass a falsifier flag to watch the check fail.

- [`extension-package-lifecycle`](https://github.com/TMHSDigital/Blender-Developer-Tools/tree/v0.148.0/examples/extension-package-lifecycle): Takes templates/extension-addon-template through what an extension meets after its first run. Falsify: `--ship-wheel` (exit 4).

<!-- examples:end -->

## References

- `bpy.utils.extension_path_user`: https://docs.blender.org/api/current/bpy.utils.html#bpy.utils.extension_path_user
- `bpy.app.online_access`: https://docs.blender.org/api/current/bpy.app.html#bpy.app.online_access
- Extensions: Python wheels: https://docs.blender.org/manual/en/latest/advanced/extensions/python_wheels.html
- Extensions command line: https://docs.blender.org/manual/en/latest/advanced/command_line/extension_arguments.html
- 4.5 LTS reference: https://docs.blender.org/api/4.5/bpy.utils.html#bpy.utils.extension_path_user
