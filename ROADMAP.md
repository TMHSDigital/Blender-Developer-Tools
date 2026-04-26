<!-- standards-version: 1.9.4 -->

# Roadmap

**Current:** v0.2.0

| Version | Theme | Skills | Rules | Templates | Snippets | Status |
| --- | --- | --- | --- | --- | --- | --- |
| v0.1.0 | Foundation | 8 | 4 | 1 | 10 | Shipped |
| v0.2.0 | Materials, drivers, migration | 12 | 6 | 2 | 17 | **Current** |
| v0.3.0 | 5.2 LTS sweep, modal operators, USD | TBD | TBD | TBD | TBD | Planned |
| v1.0.0 | Stable | TBD | TBD | TBD | TBD | Planned |

## v0.1.0 - Foundation

The 8 skills:

- `addon-scaffolding` -- Extensions Platform manifest, file layout, register/unregister symmetry
- `operators` -- `bpy.types.Operator` lifecycle, `bl_idname`, redo, defensive context handling
- `ui-panels` -- `bpy.types.Panel` declarative `draw()`, layout primitives, conditional UI
- `custom-properties` -- `bpy.props` annotations, PropertyGroup, PointerProperty, storage tradeoffs
- `mesh-editing-and-bmesh` -- when to use bpy.data vs bpy.ops vs bmesh, foreach_set, depsgraph eval
- `headless-batch-scripting` -- `blender --background --python`, temp_override, argparse after `--`
- `slotted-actions-animation` -- Blender 5.x Slotted Actions, channelbag, 4.5 LTS fallback bridge
- `geometry-nodes-python` -- programmatic GN tree construction, interface sockets, NODES modifier

The 4 rules:

- `prefer-data-over-ops-in-loops`
- `always-free-bmesh`
- `target-extensions-platform-format`
- `type-annotate-props-and-defend-context`

The 1 template:

- `extension-addon-template` -- Extensions Platform format, register_classes_factory, PointerProperty binding, symmetric register/unregister

The 10 snippets:

- `canonical-object-creation.py`
- `canonical-object-deletion.py`
- `depsgraph-evaluated-mesh.py`
- `bmesh-load-edit-free.py`
- `temp-override-context.py`
- `foreach-set-vertices.py`
- `register-classes-factory.py`
- `pointerproperty-binding.py`
- `cross-version-property-delete.py`
- `action-ensure-channelbag-for-slot.py`

## v0.2.0 - Materials, drivers, migration

The 4 new skills:

- `procedural-materials-and-shaders` -- node tree construction for Principled BSDF, emissive, node groups; cross-version socket-name handling for `Specular IOR Level`
- `depsgraph-and-evaluated-data` -- `evaluated_get` plus `to_mesh` plus `to_mesh_clear` lifetime contract, OBJ-style exporter worked example
- `drivers-and-app-handlers` -- driver expressions, `bpy.app.driver_namespace` escape hatch, application handler pattern with `@persistent`, the new 5.1 `exit_pre` handler
- `bl-info-migration` -- three-step migration from legacy `bl_info` to Extensions Platform, before-and-after diff, dual-format pattern

The 2 new rules:

- `prefer-temp-override-over-context-copy` -- `bpy.context.copy()` deprecation in 4.x, removal in 5.x, `temp_override` replacement
- `use-foreach-set-for-bulk-data` -- per-element Python loops over mesh data versus `foreach_set` and `foreach_get`

The 1 new template:

- `headless-batch-script-template` -- argparse after `--`, mesh iteration, modifier apply via temp_override, glTF export, explicit exit codes

The 7 new snippets:

- `principled-bsdf-material.py`
- `driver-with-custom-function.py`
- `app-handler-registration.py`
- `shader-node-group.py` (cross-version `interface` vs `inputs`/`outputs`)
- `foreach-get-vertices.py`
- `version-branch-skeleton.py`
- `usd-export-evaluation-mode.py`

Audit pass on v0.1.0 content: standards-version markers bumped from `1.9.1` to `1.9.4` across all skills, rules, AGENTS.md, CLAUDE.md, and ROADMAP.md. Verified the `bpy_extras.anim_utils.action_ensure_channelbag_for_slot` import path against the current Blender 5.1 API reference and removed the stale "verify before production" caveat in `slotted-actions-animation/SKILL.md`.

## v0.3.0 (candidate pool)

Not committed; target list while v0.2.0 is the current shipping version.

- `modal-operators` skill -- `invoke` returning `RUNNING_MODAL`, the `modal()` event handler, modal cancellation patterns
- `usd-pipelines` skill -- USD export options, `evaluation_mode`, instancing, the USD vs glTF tradeoffs
- `mathutils-patterns` skill -- `mathutils.Vector`, `Matrix`, `Quaternion`, common transforms, the `@` operator
- Blender 5.2 LTS sweep (after the 5.2 LTS release in mid-2026)
- Refresh the `slotted-actions-animation` skill against any 5.2 changes
- Bump `blender_version_min` in the templates if 5.2 APIs are used
- Additional snippets for asset library scripting, EXR baking, multi-file extensions

## Future (uncommitted)

- Asset library and asset browser scripting skill
- Cycles vs EEVEE Next render API skill
- Geometry Nodes 5.x feature parity (volumes, fields)
- Animation rigging from Python (constraints, drivers across bones)
