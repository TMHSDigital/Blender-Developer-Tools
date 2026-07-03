<!-- standards-version: 1.10.0 -->

# Roadmap

**Current:** v0.5.1

Themes are listed in order. Shipped themes note the release they landed in (for reference,
not a commitment); upcoming themes are intentionally **not** pinned to a version number, so
shipping another example or skill never forces a roadmap renumber. The release pipeline
derives the actual version from conventional-commit types.

| Theme | Skills | Rules | Templates | Snippets | Status |
| --- | --- | --- | --- | --- | --- |
| Foundation | 8 | 4 | 1 | 10 | Shipped (v0.1.0) |
| Materials, drivers, migration | 12 | 6 | 2 | 17 | Shipped (v0.2.0) |
| Examples and demos (smoke-gated) | 12 | 6 | 2 | 17 | Shipped (v0.3.0) |
| More examples (turntable, SDF remesh) | 12 | 6 | 2 | 17 | Shipped (v0.4.0) |
| 5.2 LTS sweep, modal operators, USD | — | — | — | — | Upcoming |
| Stable | — | — | — | — | Upcoming |

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

## Candidate pool (next content)

Not committed; target list for the next content version. (v0.3.0 shipped the smoke-gated `examples/` track.)

- **Fleet Pages facelift + examples support** (infra) -- ship as ONE coordinated change to the meta-repo `site-template/template.html.j2` + `build_site.py`, since both need a template edit and two fleet-wide pushes is worse than one. (a) examples discovery: load `examples/gallery.json` and render an Examples grid + a nav link to it (the nav link closes the landing->gallery cross-link gap, impossible today without a template edit); (b) landing facelift adopting the direction proven by this repo's gallery (shared light/dark tokens, fluid hero type scale, the card system, `:focus-visible`, reduced-motion). This repo's local gallery (`examples/gallery.json` + `docs/gallery/`, see `docs/gallery/DESIGN_NOTES.md`) is the **prototype and convergence target**: once the shared template reads the same `gallery.json` schema, the local generator (`scripts/build_gallery.py`) and page are retired -- a lift-and-shift, not a rewrite. The Option-2 cycle must read the full template-consumer set, account for floating-main consumption (every repo updates on next deploy), and prove backward compatibility (a repo with no `gallery.json` renders unchanged) before any meta-repo merge. No confirmed rendering bug today (the suspected Skills/Rules overlap was verified to be a normal collapsed accordion), so the cross-link discoverability gap is the main driver.
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
