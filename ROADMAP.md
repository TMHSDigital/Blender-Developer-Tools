<!-- standards-version: 1.9.1 -->

# Roadmap

**Current:** 0.1.0

| Version | Theme | Skills | Rules | Templates | Snippets | Status |
| --- | --- | --- | --- | --- | --- | --- |
| v0.1.0 (current) | Foundation | 8 | 4 | 1 | 10 | **Current** |
| v0.2.0 | Materials, drivers, migration | +3 | 0 | +1 | +5 | Planned |
| v0.3.0 | 5.2 LTS sweep | TBD | TBD | TBD | TBD | Planned |
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

## v0.2.0 (candidate pool)

Not committed; target list while v0.1.0 is the current shipping version.

- `procedural-materials` skill -- programmatic node group creation for shaders, principled BSDF wiring, baking
- `depsgraph-queries` skill -- iterating evaluated objects, depsgraph updates, modifier-applied geometry traversal
- `drivers` skill -- Python expressions in drivers, `bpy.app.driver_namespace`, security caveats
- `bl-info-to-manifest-migration` skill -- step-by-step migration from legacy `bl_info` add-ons to Extensions Platform manifests
- `headless-batch-script-template` template -- a `blender --background --python` runner with argparse, logging, and exit codes
- 5 additional snippets (driver registration, node group instancing, depsgraph update handler, EXR baking, multi-file extension)

## v0.3.0 (deferred)

- Blender 5.2 LTS sweep planned for July 2026 (after the 5.2 LTS release).
- Audit every skill for 5.2 API drift.
- Refresh the `slotted-actions-animation` skill against any 5.2 changes.
- Bump `blender_version_min` in the template if 5.2 APIs are used.

## Future (uncommitted)

- Asset library and asset browser scripting skill
- USD export pipeline skill
- Cycles vs EEVEE Next render API skill
- A second template for headless batch processing
