<!-- standards-version: 1.9.1 -->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The **Blender Developer Tools** repository is at **v0.1.0**. It packages skills, rules, snippets, and a starter template for Blender Python development with Cursor and Claude Code. Coverage targets **Blender 5.1** (current stable) with **Blender 4.5 LTS** fallback. There is no MCP server in v0.1.0; content is consumed directly by the AI when working in Blender add-on or scripting projects.

**Version:** 0.1.0
**License:** MIT
**Author:** TMHSDigital

## Repository Architecture

```
skills/<skill-name>/SKILL.md   - AI workflow definitions, 8 total
rules/<rule-name>.mdc          - Anti-pattern rules, 4 total
templates/<template-name>/     - Starter projects, 1 total
snippets/<snippet-name>.py     - Standalone code patterns, 10 total
VERSION                        - Source of truth for the repo version
```

## Skills (8)

| Skill | Purpose |
| --- | --- |
| addon-scaffolding | Extensions Platform manifest, file layout, register/unregister symmetry |
| operators | `bpy.types.Operator` lifecycle, `bl_idname`, redo, defensive context handling |
| ui-panels | `bpy.types.Panel` declarative `draw()`, layout primitives, conditional UI |
| custom-properties | `bpy.props` annotations, PropertyGroup, PointerProperty, storage tradeoffs |
| mesh-editing-and-bmesh | When to use bpy.data vs bpy.ops vs bmesh, foreach_set, depsgraph eval |
| headless-batch-scripting | `blender --background --python`, temp_override, argparse after `--` |
| slotted-actions-animation | Blender 5.x Slotted Actions, channelbag, 4.5 LTS fallback bridge |
| geometry-nodes-python | Programmatic GN tree construction, interface sockets, NODES modifier |

## Rules (4)

| Rule | Scope | What it flags |
| --- | --- | --- |
| prefer-data-over-ops-in-loops | Always on | `bpy.ops.*` calls inside iteration over many objects |
| always-free-bmesh | `*.py` | `bmesh.new()` without paired `bm.free()` in a `try`/`finally` block |
| target-extensions-platform-format | Add-on roots | Legacy `bl_info` only add-ons missing `blender_manifest.toml` |
| type-annotate-props-and-defend-context | `*.py` | `bpy.props` defined as assignments, unguarded `context.active_object` |

## Templates (1)

`templates/extension-addon-template/` is a copy-paste-ready Blender extension demonstrating:

- `blender_manifest.toml` with `blender_version_min = "4.5.0"`
- `register_classes_factory` registration pattern
- One Operator, one Panel, one PropertyGroup
- A `PointerProperty` bound to `bpy.types.Scene`
- Symmetric `register()` / `unregister()` with property cleanup before class unregister

## Snippets (10)

Small standalone `.py` files at `snippets/<name>.py`, each 5 to 30 lines, covering: canonical object creation and deletion, depsgraph evaluated mesh, bmesh load-edit-free, temp_override context, foreach_set vertex bulk write, register_classes_factory, PointerProperty binding, cross-version property delete, and the `action_ensure_channelbag_for_slot` slotted-actions bridge.

## Development Workflow

This is a content repository, no build step. Edit `SKILL.md`, `.mdc`, `.py`, and `.toml` files directly.

The AI consumes content via:

- **Cursor**: rules under `rules/` apply when scope globs match. Skills are referenced by name in chat.
- **Claude Code**: copy `skills/` and `rules/` into the project workspace, or use this repo as a checkout that Claude Code references directly.

## Key Conventions

- **Blender versions**: 5.1 primary, 4.5 LTS fallback. Skills must show both code paths when 4.x and 5.x APIs diverge.
- **Properties as annotations**: `my_prop: bpy.props.FloatProperty(...)` (correct), not `my_prop = bpy.props.FloatProperty(...)` (deprecated).
- **bmesh memory**: every `bmesh.new()` must be paired with `bm.free()` in a `try`/`finally`.
- **No `bpy.ops` in tight loops**: use `bpy.data.*` and `bmesh` for bulk work.
- **Extensions over `bl_info`**: new add-ons ship as Extensions with `blender_manifest.toml`. `bl_info` may appear alongside as a fallback only.
- **Defensive context**: any code touching `context.active_object` must guard with `if obj is None: return`.

## Blender Documentation Quick Reference

| Area | URL |
| --- | --- |
| Python API (5.1) | https://docs.blender.org/api/current/ |
| Python API (4.5 LTS) | https://docs.blender.org/api/4.5/ |
| Extensions Platform | https://docs.blender.org/manual/en/latest/advanced/extensions/index.html |
| Release notes | https://developer.blender.org/ |

## Release Hygiene

The release pipeline is automated via `release.yml` on push to `main` for content-changing paths. The `release-doc-sync@v1` step rewrites CHANGELOG.md, this CLAUDE.md `**Version:**` line, and ROADMAP.md `**Current:**` line on each release. Never hand-edit those lines, the action owns them.

When adding content to a future version:

1. Add files under `skills/`, `rules/`, `snippets/`, or `templates/`.
2. Update README.md aggregate counts (the `validate-counts` job enforces correctness).
3. Update ROADMAP.md candidate pool entries.
4. Use `feat:` for new content, `fix:` for corrections.
5. Push. The release pipeline handles VERSION, tags, CHANGELOG, the `**Version:**` line here, and the `**Current:**` line in ROADMAP.md.
