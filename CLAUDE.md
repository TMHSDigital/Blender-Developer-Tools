<!-- standards-version: 1.10.0 -->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Division of labor:** this file carries repo-specific operational facts an agent needs at runtime — content inventory, Blender runtime discovery, git staging hazards, and the example-shipping quality gates. `AGENTS.md` carries fleet-standard governance and workflow rules — branching, commits, merge and CI-evidence policy, release automation, authoring standards. Read both; neither repeats the other.

## Project Overview

The **Blender Developer Tools** repository is at **v0.20.0**. It packages skills, rules, snippets, starter templates, and runnable smoke-gated examples for Blender Python development with Cursor and Claude Code. Coverage targets **Blender 5.1** (current stable) with **Blender 4.5 LTS** fallback. There is no MCP server; content is consumed directly by the AI when working in Blender add-on or scripting projects.

**Version:** 0.20.0
**License:** CC-BY-NC-ND-4.0
**Author:** TM Hospitality Strategies

## Repository Architecture

```
skills/<skill-name>/SKILL.md   - AI workflow definitions, 12 total
rules/<rule-name>.mdc          - Anti-pattern rules, 6 total
templates/<template-name>/     - Starter projects, 2 total
snippets/<snippet-name>.py     - Standalone code patterns, 17 total
examples/<name>/               - Runnable smoke-gated examples, 23 total (+ gallery.json)
scripts/build_gallery.py       - Regenerates docs/gallery/ from gallery.json (stdlib only)
scripts/site/                  - Vendored landing-page build (Jinja2)
docs/gallery/                  - Committed generated gallery pages + hero renders
VERSION                        - Source of truth for the repo version
```

## Skills (12)

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
| procedural-materials-and-shaders | Node tree construction for Principled BSDF, emissive, node groups, EEVEE Next vs Cycles |
| depsgraph-and-evaluated-data | `evaluated_get` / `to_mesh` / `to_mesh_clear` lifetime contract for exporters and measurement |
| drivers-and-app-handlers | Driver expressions, `driver_namespace`, application handlers including the new 5.1 `exit_pre` |
| bl-info-migration | Three-step migration from legacy `bl_info` to Extensions Platform, dual-format pattern |

## Rules (6)

| Rule | Scope | What it flags |
| --- | --- | --- |
| prefer-data-over-ops-in-loops | Always on | `bpy.ops.*` calls inside iteration over many objects |
| always-free-bmesh | `*.py` | `bmesh.new()` without paired `bm.free()` in a `try`/`finally` block |
| target-extensions-platform-format | Add-on roots | Legacy `bl_info` only add-ons missing `blender_manifest.toml` |
| type-annotate-props-and-defend-context | `*.py` | `bpy.props` defined as assignments, unguarded `context.active_object` |
| prefer-temp-override-over-context-copy | `*.py` | `bpy.context.copy()` passed to operators (deprecated 4.x, removed 5.x) |
| use-foreach-set-for-bulk-data | `*.py` | Python loops over `mesh.vertices` setting bulk attributes one at a time |

## Templates (2)

`templates/extension-addon-template/` is a copy-paste-ready Blender extension demonstrating:

- `blender_manifest.toml` with `blender_version_min = "4.5.0"`
- `register_classes_factory` registration pattern
- One Operator, one Panel, one PropertyGroup
- A `PointerProperty` bound to `bpy.types.Scene`
- Symmetric `register()` / `unregister()` with property cleanup before class unregister

`templates/headless-batch-script-template/` is a working starter for unattended Blender batch jobs:

- `argparse` parsing of args after the `--` separator
- Iteration over every mesh object via `bpy.data.objects`
- Modifier application via `bpy.context.temp_override` (not the deprecated context-dict form)
- glTF export via `bpy.ops.export_scene.gltf`
- Explicit exit codes for CI integration

## Snippets (17)

Small standalone `.py` files at `snippets/<name>.py`, each 5 to 50 lines.

v0.1.0: canonical object creation and deletion, depsgraph evaluated mesh, bmesh load-edit-free, temp_override context, foreach_set vertex bulk write, register_classes_factory, PointerProperty binding, cross-version property delete, and the `action_ensure_channelbag_for_slot` slotted-actions bridge.

v0.2.0: Principled BSDF material, driver-with-custom-function via `driver_namespace`, application handler registration, shader node group with cross-version `interface` API, `foreach_get` bulk vertex read, version-branch skeleton, and USD export with `evaluation_mode='RENDER'`.

## Examples (23)

Runnable scripts at `examples/<name>/`, each asserting a real API contract with
deterministic checks (exit non-zero on failure) and optionally rendering a still via
`--output`. All twenty-three run headless on Blender 4.5 LTS and 5.1 in `blender-smoke.yml`;
their renders ship in the site gallery at `docs/gallery/`. `examples/gallery.json` is the
gallery's source of truth. When authoring a new one, copy the anatomy of
`examples/bmesh-gear/` (script structure, README shape, dark-studio render recipe) and
wire all of: gallery.json entry, `.cursor-plugin/plugin.json` examples array (CI-gated),
a `blender-smoke.yml` step, a README gallery row, hero webp (1280×720) in
`docs/gallery/assets/` + preview webp (1200×675), then run `python scripts/build_gallery.py`.
Renders must conform to the gallery look spec at `docs/VISUAL-STYLE.md`.

## Blender Runtime Discovery

- Local Blender binaries: check `.scratch/` at the repo root **first** — some machines have no system Blender install, and a prior agent run downloads official releases there (e.g. `.scratch/5.1/blender-5.1.x-.../blender[.exe]`). Then check system installs. Do not probe blindly; locate the binary, run it, and state the **exact binary path and the version the binary itself reports** in every report.
- **5.1 is the local check version. 4.5 LTS is exercised by CI when unavailable locally.** 4.4 is not a substitute for 4.5 and must never be reported as 4.5.
- If `.scratch/` lacks a needed version, download an official release from download.blender.org into it. `.scratch` is gitignored.
- In scripts, version-branch on the `bpy.app.version` tuple, never on `bpy.app.version_string` — it reads e.g. `"4.5.11 LTS"`, not bare semver.

## Git Staging

Stage with **explicit paths only** — never `git add -A` or `git add .`. Cursor agent sessions inject a local guidance block into the working-copy `CLAUDE.md`; a bulk add sweeps it into the commit. It manifests as a `CLAUDE.md` hunk in `git diff` that you did not author (the file can be dirty before you touch anything). Leave it unstaged, and never stage `CLAUDE.md` unless you deliberately edited it.

## Quality Gates for Example Runs

- `docs/VISUAL-STYLE.md` is the **binding** render standard; deviations are defects.
- **Contact-sheet gate:** composite the candidate hero beside the pinned calibration set — currently `armature-bend`, `damped-track-aim`, `bmesh-gear` — commit the composite under `docs/gallery/contact-sheets/`, link it in the PR body, and report per-criterion verdicts (stage darkness, wedge warmth, subject fill, saturation, thumbnail legibility) including mean luminance versus the calibration images. A claim without the committed composite is not acceptable evidence. **This list is the canonical home of the pinned set** — update it here when a new example outclasses a member; `docs/new-example-prompt.md` points here rather than naming members. The longer "calibration references" list in `docs/VISUAL-STYLE.md` is a style reference, not this contact-sheet set.
- **Falsification:** every check must be proven to fail once — break the contract, observe the non-zero exit, restore — with the probe and the measured error reported in the PR body. An assertion that cannot fail witnesses nothing.
- **After gallery regeneration** (`python scripts/build_gallery.py`), read the **generated HTML** character by character — the `<img alt>` text and witnesses callouts in `docs/gallery/index.html` and `docs/gallery/<name>/index.html` — not just `examples/gallery.json`. Precedent: the `teaches.split(".")[0]` bug truncated 14/21 card alts at dotted API paths like `bmesh.ops` while the source JSON looked fine (fixed in PR #68).

## Example-Run Process

- The canonical example-creation prompt lives at `docs/new-example-prompt.md`; keep it in agreement with this file and `AGENTS.md`.
- The `ROADMAP.md` "Candidate pool" section is the subject source for example runs: remove a subject when it ships, and restock with subjects identified but not built.
- PR bodies label what was proven by live run versus established by inspection only (see `AGENTS.md` § Merge policy and CI evidence for the merge and post-merge verification rules).

## Development Workflow

This is a content repository, no build step for skills/rules/snippets/templates — edit
`SKILL.md`, `.mdc`, `.py`, and `.toml` files directly. The website is generated:
`scripts/build_gallery.py` (stdlib) regenerates `docs/gallery/` and must be re-run after
touching `examples/`; the landing page builds from `scripts/site/` at deploy time.

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

1. Add files under `skills/`, `rules/`, `snippets/`, `templates/`, or `examples/`.
2. Update README.md aggregate counts (the `validate-counts` job enforces correctness).
3. Update ROADMAP.md candidate pool entries.
4. Use `feat:` for new content, `fix:` for corrections.
5. Push. The release pipeline handles VERSION, tags, CHANGELOG, the `**Version:**` line here, and the `**Current:**` line in ROADMAP.md.
