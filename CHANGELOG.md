# Changelog

All notable changes to this project will be documented in this file.

## [0.1.2] - 2026-04-26

See [release notes](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.1.2) for details.

## [0.1.1] - 2026-04-26

See [release notes](https://github.com/TMHSDigital/Blender-Developer-Tools/releases/tag/v0.1.1) for details.

## [0.1.0] - 2026-04-26

Initial release. 8 skills, 4 rules, 1 template, and 10 snippets covering Blender 5.1 Python development with 4.5 LTS fallback support.

### Added

- 8 skills: `addon-scaffolding`, `operators`, `ui-panels`, `custom-properties`, `mesh-editing-and-bmesh`, `headless-batch-scripting`, `slotted-actions-animation`, `geometry-nodes-python`
- 4 rules: `prefer-data-over-ops-in-loops`, `always-free-bmesh`, `target-extensions-platform-format`, `type-annotate-props-and-defend-context`
- 1 template: `extension-addon-template` demonstrating Extensions Platform format with `register_classes_factory`, a `PointerProperty` binding, and symmetric `register`/`unregister`
- 10 snippets covering canonical object creation and deletion, depsgraph evaluated mesh, bmesh load-edit-free, `temp_override` context, `foreach_set` vertex bulk write, `register_classes_factory`, `PointerProperty` binding, cross-version property delete, and the `action_ensure_channelbag_for_slot` slotted-actions bridge
- CI/CD: `validate.yml` (with `validate-counts`), `drift-check.yml` (consuming `drift-check@v1.9`), `release.yml` (consuming `release-doc-sync@v1`), `label-sync.yml` (self-healing per-label `gh label create --force`)
- `dependabot.yml` covering the `github-actions` ecosystem
- Standards-version markers at `1.9.1` throughout
