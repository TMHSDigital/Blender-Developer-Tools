<!-- standards-version: 1.9.4 -->

# AGENTS.md

Guidance for AI coding agents working on the Blender Developer Tools repository.

## Repository overview

Skills, rules, snippets, and a starter template for Blender Python development.
The repo targets **Blender 5.1** (current stable) with a **Blender 4.5 LTS**
fallback. There is no MCP server and no `.cursor-plugin/plugin.json`. This is
content the AI loads when the user asks Blender questions or works on Blender
add-ons in Cursor or Claude Code.

The content base as of v0.2.0:

- 12 skills covering scaffolding, operators, panels, properties, mesh and
  bmesh, headless batch scripts, slotted-actions animation (5.x), programmatic
  geometry nodes, procedural materials and shaders, depsgraph and evaluated
  data, drivers and application handlers, and `bl_info` to Extensions
  Platform migration.
- 6 rules encoding the most common AI anti-patterns when writing Blender
  Python (ops-in-loops, bmesh leaks, legacy `bl_info`-only, prop assignment,
  deprecated context-copy override, per-element loops over bulk mesh data).
- 2 templates: `extension-addon-template` for Extensions Platform add-ons,
  and `headless-batch-script-template` for unattended batch jobs.
- 17 snippets covering canonical patterns.

## Repository structure

```
Blender-Developer-Tools/
  skills/<skill-name>/SKILL.md   # 12 skill files
  rules/<rule-name>.mdc          # 6 rule files
  templates/<template-name>/     # 2 starter templates
  snippets/<snippet-name>.py     # 17 standalone Python snippets
  .github/workflows/             # validate, drift-check, release, label-sync
  .github/dependabot.yml
  AGENTS.md, CLAUDE.md, README.md, ROADMAP.md, CHANGELOG.md
  CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md
  VERSION                        # source of truth for the repo version
  LICENSE                        # CC-BY-NC-ND-4.0
```

## Branching and commit model

- Single `main` branch. No develop or release branches.
- Conventional commits drive the auto-release workflow:
  - `feat:` triggers a minor bump
  - `fix:` triggers a patch bump
  - `feat!:` or `BREAKING CHANGE` triggers a major bump
  - Other types (`chore:`, `docs:`, etc.) skip the release path entirely
    when only those non-content paths change.
- Commit messages should describe the why, not the what.

## Blender version targeting

- Primary: **Blender 5.1.x** (current stable). All examples assume 5.1
  unless otherwise stated.
- Fallback: **Blender 4.5 LTS**. Skills and the extension template note 4.5
  compatibility where it matters (slotted actions bridge, property delete,
  manifest fields).
- Future: a 5.2 LTS sweep is planned for July 2026 (see `ROADMAP.md`).

When a 4.x and 5.x API genuinely diverge, skills must show both code paths,
not just the 5.x one. The `slotted-actions-animation` skill is the load-bearing
example.

## Skills

Each skill lives at `skills/<skill-name>/SKILL.md`. Frontmatter is YAML:

```yaml
---
name: <kebab-case-skill-name>
description: <one-line, under 200 chars>
standards-version: 1.9.4
---
```

`name` must match the directory name. `description` is what the AI sees when
deciding whether to load the skill.

Skills should cite Blender API doc URLs where they reference specific RNA
classes, operators, or modules. Avoid encyclopedic API tours; the goal is the
canonical pattern plus the common AI mistakes.

## Rules

Rules are `.mdc` files in `rules/`. Frontmatter:

```yaml
---
description: <one-line>
alwaysApply: true
standards-version: 1.9.4
---
```

Rules encode anti-patterns. Each rule should show the wrong way, the right
way, and a one-paragraph rationale. 30 to 80 lines is the right size.

## CI/CD workflows

- `validate.yml` runs file structure checks plus a `validate-counts` job that
  asserts the README aggregate counts (12 skills, 6 rules, 2 templates, 17
  snippets) match filesystem reality. The counts language in `README.md` is
  load-bearing: the job greps for it.
- `drift-check.yml` consumes `Developer-Tools-Directory/.github/actions/
  drift-check@v1.9` to enforce ecosystem standards-version markers.
- `release.yml` auto-bumps the version, tags, force-updates floating tags
  `v0` and `v0.1`, and runs `release-doc-sync@v1` to rewrite CHANGELOG.md,
  CLAUDE.md `**Version:**`, and ROADMAP.md `**Current:**`. Triggered on
  push to `main` for content-changing paths only.
- `label-sync.yml` self-heals labels via `gh label create --force` per
  label, then applies them to the PR.

## Where to look for canonical references

- Blender 5.1 Python API: https://docs.blender.org/api/current/
- Blender 4.5 LTS Python API: https://docs.blender.org/api/4.5/
- Extensions Platform reference: https://docs.blender.org/manual/en/latest/advanced/extensions/index.html
- Release notes (`developer.blender.org`): https://developer.blender.org/

When information conflicts, prefer the docs over Stack Overflow or older
add-on source. The 2.x to 4.x to 5.x churn around Actions, Extensions, and
property handling has invalidated a lot of community content.

## License

CC-BY-NC-ND-4.0. See `LICENSE`.
