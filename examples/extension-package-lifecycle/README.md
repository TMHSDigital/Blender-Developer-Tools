# Extension package lifecycle

Takes [`templates/extension-addon-template`](../../templates/extension-addon-template/)
through what an extension meets after its first run: validate, build, a
repository listing, install, an upgrade over the top, removal, and the
online-access gate. Every step runs a child Blender against a throwaway user
directory (`BLENDER_USER_RESOURCES`), so the real install is never touched.
Check-only: the witnesses are exit codes, zip members and paths, so a render
would look the same whether the contract held or broke.

Follows [`extension-runtime-and-packaging`](../../skills/extension-runtime-and-packaging/SKILL.md),
whose snippet is [`extension-user-data.py`](../../snippets/extension-user-data.py).
Scaffolding matches [`eval-mesh-datablock-name`](../eval-mesh-datablock-name/)
(`check()` steps return codes, argparse falsifier flags, FATAL wrapper).

**What it witnesses:**

- `blender --command extension validate` and `build` accept the template, and
  the zip carries `blender_manifest.toml` and `__init__.py` at its root.
- **`validate` is not a release gate.** With `wheels = ["./wheels/not_shipped-1.0-py3-none-any.whl"]`
  appended and no such file, `validate` exits 0 and `build` exits 1 with no
  zip. Only the build opens the files the manifest names.
- `extension server-generate --repo-dir` writes `index.json` listing the
  package with `archive_url` `./example_addon-0.1.0.zip`.
- Installed with `extension install-file -r user_default`, the add-on imports
  as `bl_ext.user_default.example_addon`, and
  `bpy.utils.extension_path_user(__package__)` names
  `extensions/.user/user_default/example_addon`, beside the install tree
  `extensions/user_default/example_addon`, not inside it.
- Installing 0.2.0 over 0.1.0 replaces the install tree (a file written
  beside `__file__` is gone) and keeps the user directory (`settings.json`
  survives). `extension remove` deletes the user directory too.
- `bpy.app.online_access` is `False` in a factory-startup child and `True`
  under `--online-mode`.

**What failure each check would catch:**

- exit 3 — the template stopped validating or building, or the zip lost its manifest
- exit 4 — `build` accepted the package whose manifest names a wheel it does
  not ship, so nothing between `validate` and a release would catch it
  (`--ship-wheel` lands here: it creates the named wheel, so `build` exits 0
  and writes a zip, proving the rejection comes from the missing file); also
  exit 4 if `validate` starts rejecting the package, because the trap this
  example names would then be gone
- exit 5 — `server-generate` wrote no listing, or the listing does not name the package
- exit 6 — install, import, upgrade or remove failed, or `__package__` is not
  `bl_ext.user_default.example_addon`
- exit 7 — user data lives inside the install tree, did not survive the
  upgrade, or survived removal (`--data-next-to-file` lands here: it stores
  data beside `__file__`)
- exit 8 — `online_access` is not `False` by default and `True` under `--online-mode`

## Re-verified

| Measurement | 4.5.11 | 5.1.2 | 5.2.1 |
| --- | --- | --- | --- |
| validate / build, template | 0 / 0 | 0 / 0 | 0 / 0 |
| validate / build, missing wheel | 0 / 1 | 0 / 1 | 0 / 1 |
| `__package__` | `bl_ext.user_default.example_addon` | same | same |
| user data kept by 0.2.0 upgrade | yes | yes | yes |
| file beside `__file__` kept by upgrade | no | no | no |
| user data after `remove` | deleted | deleted | deleted |
| `online_access` default / `--online-mode` | False / True | False / True | False / True |
| default exit | 0 | 0 | 0 |
| `--ship-wheel` / `--data-next-to-file` exit | 4 / 7 | not re-run / 7 | 4 / 7 |
| validate / build, wheel shipped (`--ship-wheel`) | 0 / 0, zip written | not re-run | 0 / 0, zip written |

## API reference

- [`bpy.utils.extension_path_user`](https://docs.blender.org/api/current/bpy.utils.html#bpy.utils.extension_path_user)
  ([4.5 LTS](https://docs.blender.org/api/4.5/bpy.utils.html#bpy.utils.extension_path_user))
- [`bpy.app.online_access`](https://docs.blender.org/api/current/bpy.app.html#bpy.app.online_access)
- [Extensions command line arguments](https://docs.blender.org/manual/en/latest/advanced/command_line/extension_arguments.html)

## Run

```bash
blender --background --python extension_package_lifecycle.py --
blender --background --python extension_package_lifecycle.py -- --ship-wheel
blender --background --python extension_package_lifecycle.py -- --data-next-to-file
```

The script starts about a dozen child Blender processes, so it takes longer
than most examples.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Template does not validate or build, or the zip lacks its manifest |
| 4 | `build` accepted the missing-wheel package, or `validate` rejected it (`--ship-wheel` lands here) |
| 5 | `server-generate` listing missing or wrong |
| 6 | Install, import, upgrade or remove failed, or `__package__` wrong |
| 7 | User data inside the install tree, lost on upgrade, or kept after removal (`--data-next-to-file` lands here) |
| 8 | `online_access` default or `--online-mode` value wrong |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke passes no extra flags on the happy path. Its catalog falsifiers are
`--ship-wheel` (expects exit 4) and `--data-next-to-file` (expects exit 7).
