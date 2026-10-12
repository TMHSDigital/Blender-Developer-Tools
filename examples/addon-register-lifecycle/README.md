# Add-on register lifecycle

Check-only witness for the first things every add-on author writes: the
package layout, the `bl_info` → manifest migration, a Panel, and a
PropertyGroup on `Scene`, registered and unregistered symmetrically. It
builds a dual-format add-on in a temp directory, validates it with Blender's
own extension validator, registers it and unregisters it. There is no
gallery still, because the witness is registry state and the validator's
exit code (same class as
[`extension-package-lifecycle`](../extension-package-lifecycle/)).

Follows [`addon-scaffolding`](../../skills/addon-scaffolding/SKILL.md),
[`bl-info-migration`](../../skills/bl-info-migration/SKILL.md),
[`ui-panels`](../../skills/ui-panels/SKILL.md) and
[`custom-properties`](../../skills/custom-properties/SKILL.md).

**What it witnesses:**

- `blender --command extension validate` accepts a package with both
  `blender_manifest.toml` and a legacy `bl_info` (exit 0). Keeping `bl_info`
  for pre-4.2 Blender does not break the Extensions Platform path.
- The same `__init__.py` without a manifest is rejected (exit 1,
  `blender_manifest.toml not found`): adding the manifest is the migration.
- `register()` creates the Panel class, the PropertyGroup class and the
  `Scene.addon_probe` pointer, which reads its default (1.5).
- `unregister()` that deletes the pointer first, then unregisters the
  classes in reverse, leaves nothing behind. Unregistering the classes first
  leaves `Scene.addon_probe` registered and pointing at a type that no
  longer exists. In a probe, *reading* that dangling property returned an
  empty stub on 4.5.14 and **crashed Blender 5.2.1**
  (`EXCEPTION_ACCESS_VIOLATION`). This example only checks that the pointer
  survived, and never reads it.

Also measured, not checked (no falsifier can reach them through Blender
behaviour alone): a Panel `bl_idname` without `_PT_` only prints a warning
and still registers, while a Panel with no `bl_region_type` is rejected at
`register_class` with `AttributeError` (4.5.14 and 5.2.1).

**What failure each check would catch:**

- exit 3 — the dual-format package did not validate (`--drop-manifest` lands here)
- exit 4 — a package without a manifest validated (`--legacy-gets-manifest` lands here)
- exit 5 — `register()` did not create the panel, group and pointer, or the
  default did not read back (`--skip-pointer` lands here)
- exit 6 — `unregister()` left something behind (`--classes-first` lands here: the pointer)

## Re-verified

| Measurement | 4.5.14 | 5.2.1 |
| --- | --- | --- |
| validate dual-format / bl_info-only | 0 / 1 | 0 / 1 |
| after register: panel, group, pointer | all present | all present |
| after unregister (right order / classes first) | nothing / pointer left | nothing / pointer left |
| reading the dangling pointer (probe) | empty stub | crash |
| default exit | 0 | 0 |
| falsifier exits | 3 / 4 / 5 / 6 | 3 / 4 / 5 / 6 |

## API reference

- [Extensions: command line](https://docs.blender.org/manual/en/latest/advanced/command_line/extension_arguments.html)
- [`bpy.utils.register_class`](https://docs.blender.org/api/current/bpy.utils.html#bpy.utils.register_class),
  [`unregister_class`](https://docs.blender.org/api/current/bpy.utils.html#bpy.utils.unregister_class)
- [`bpy.props.PointerProperty`](https://docs.blender.org/api/current/bpy.props.html#bpy.props.PointerProperty)
- [`bpy.types.Panel`](https://docs.blender.org/api/current/bpy.types.Panel.html)

## Run

```bash
blender --background --python addon_register_lifecycle.py --
blender --background --python addon_register_lifecycle.py -- --drop-manifest
blender --background --python addon_register_lifecycle.py -- --legacy-gets-manifest
blender --background --python addon_register_lifecycle.py -- --skip-pointer
blender --background --python addon_register_lifecycle.py -- --classes-first
```

## Exit codes

Per-script sequential checks.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Dual-format package did not validate (`--drop-manifest`) |
| 4 | Package without a manifest validated (`--legacy-gets-manifest`) |
| 5 | `register()` missed the panel, group or pointer (`--skip-pointer`) |
| 6 | `unregister()` left something behind (`--classes-first`) |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke passes no extra flags on the happy path. Its catalog falsifiers are
`--drop-manifest` (exit 3), `--legacy-gets-manifest` (exit 4),
`--skip-pointer` (exit 5) and `--classes-first` (exit 6).
