<h1 align="center">Blender Developer Tools</h1>

<p align="center">
  <strong>Skills, rules, snippets, and a starter template for Blender Python development</strong>
</p>

<p align="center">
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/releases"><img src="https://img.shields.io/badge/version-0.2.0-e87d0d?style=flat-square" alt="Version" /></a>
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/releases"><img src="https://img.shields.io/github/v/release/TMHSDigital/Blender-Developer-Tools?style=flat-square&color=e87d0d&label=release" alt="Release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-CC--BY--NC--ND--4.0-384d54?style=flat-square" alt="License" /></a>
</p>

<p align="center">
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/TMHSDigital/Blender-Developer-Tools/validate.yml?branch=main&style=flat-square&label=validate" alt="Validate" /></a>
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/actions/workflows/drift-check.yml"><img src="https://img.shields.io/github/actions/workflow/status/TMHSDigital/Blender-Developer-Tools/drift-check.yml?branch=main&style=flat-square&label=drift-check" alt="Drift check" /></a>
</p>

<p align="center">
  <strong>12 skills</strong> &nbsp;&bull;&nbsp; <strong>6 rules</strong> &nbsp;&bull;&nbsp; <strong>2 templates</strong> &nbsp;&bull;&nbsp; <strong>17 snippets</strong>
</p>

---

## Overview

This repository ships **12 skills, 6 rules, 2 templates, and 17 snippets** for Blender Python development targeting Blender 5.1 (current stable) with Blender 4.5 LTS fallback support.

The content is consumed by AI coding agents (Cursor, Claude Code, any MCP-capable client) when working on Blender add-ons, geometry nodes scripts, batch pipelines, or animation tooling. There is no build step. Edit the markdown and Python files directly.

| Layer | Role |
| --- | --- |
| **Skills** | Guided workflows: scaffolding, operators, panels, properties, mesh and bmesh, headless batch, slotted actions, geometry nodes, procedural materials, depsgraph queries, drivers and handlers, `bl_info` migration |
| **Rules** | Guardrails for the most common AI mistakes: ops-in-loops, bmesh leaks, legacy `bl_info` only, prop assignments, deprecated context-copy override, per-element loops over bulk mesh data |
| **Templates** | A working Extensions Platform add-on starter and a headless batch script starter |
| **Snippets** | 17 small standalone Python files demonstrating canonical patterns |

## Supported Blender versions

| Version | Status |
| --- | --- |
| Blender 5.1.x | Primary target (all examples assume 5.1) |
| Blender 4.5 LTS | Fallback supported (skills show both code paths where 4.x and 5.x APIs diverge) |
| Blender 5.2 LTS | Sweep planned for July 2026 (see [ROADMAP.md](ROADMAP.md)) |

## How content is organized

```
skills/<name>/SKILL.md   - 12 skill files, YAML frontmatter, one canonical pattern each
rules/<name>.mdc         - 6 rule files, anti-pattern + correction
templates/<name>/        - 2 template directories (extension-addon-template, headless-batch-script-template)
snippets/<name>.py       - 17 standalone Python snippets, 5 to 50 lines each
```

## Using rules in Cursor

The `.mdc` files in `rules/` apply automatically when Cursor opens a Blender Python project, scoped by the `globs` in each rule's frontmatter. The six rules are:

- `prefer-data-over-ops-in-loops`: flags `bpy.ops.*` calls inside object iteration
- `always-free-bmesh`: flags `bmesh.new()` without paired `bm.free()` in `try`/`finally`
- `target-extensions-platform-format`: flags add-ons missing `blender_manifest.toml`
- `type-annotate-props-and-defend-context`: flags `bpy.props` assignment form and unguarded `context.active_object`
- `prefer-temp-override-over-context-copy`: flags `bpy.context.copy()` passed to operators (deprecated 4.x, removed 5.x)
- `use-foreach-set-for-bulk-data`: flags Python loops over `mesh.vertices` setting `co`, normals, or other per-element bulk data

Symlink or clone this repo, then point Cursor at it as a skills/rules source.

## Using the templates

`templates/extension-addon-template/` is a working Blender extension. Copy the directory, edit `blender_manifest.toml` (id, version, name, maintainer), and install via Edit > Preferences > Get Extensions > Install From Disk. The template registers an Operator, a Panel, and a PropertyGroup, and demonstrates the `register_classes_factory` pattern with symmetric `register()` and `unregister()`.

`templates/headless-batch-script-template/` is a working starter for unattended Blender batch jobs. It opens a `.blend`, optionally adds and applies a modifier to every mesh, and exports to glTF, with explicit exit codes for CI integration. Run with `blender --background <input.blend> --python script.py -- --output ...`.

## Snippets

Each snippet is a standalone Python file under `snippets/`. They are not loaded as a package. Open one, copy the relevant lines into your script, and adapt the names. Each file's header comment cites the Blender doc URL or research section the pattern came from.

## Canonical references

| Resource | Use it for |
| --- | --- |
| [Blender 5.1 Python API](https://docs.blender.org/api/current/) | Authoritative reference for current stable APIs |
| [Blender 4.5 LTS Python API](https://docs.blender.org/api/4.5/) | LTS reference when targeting 4.5 |
| [Extensions Platform manual](https://docs.blender.org/manual/en/latest/advanced/extensions/index.html) | `blender_manifest.toml` schema, hosting, install flow |
| [developer.blender.org](https://developer.blender.org/) | Release notes, breaking change tracking, design docs |

When community content (Stack Overflow, older add-on source) conflicts with the official docs, prefer the docs. The 2.x to 4.x to 5.x churn around Actions, Extensions, and property handling has invalidated a lot of older material.

## Roadmap

See [ROADMAP.md](ROADMAP.md). v0.2.0 shipped procedural materials, depsgraph queries, drivers and app handlers, `bl_info` to manifest migration, two new rules, and the headless batch script template. v0.3.0 candidates include modal operators, USD pipelines, and `mathutils` patterns.

## License

Copyright (c) 2026 TM Hospitality Strategies. Licensed under [CC-BY-NC-ND-4.0](LICENSE).
