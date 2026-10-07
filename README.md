<h1 align="center">Blender Developer Tools</h1>

---

<p align="center">
  <strong>Teach Cursor and Claude Code the Blender Python that actually runs on Blender 5.2 LTS and 4.5 LTS.</strong>
</p>

<p align="center">
  Skills and rules that stop AI agents writing the <code>bpy</code> that breaks: <code>bpy.context.copy()</code> operator overrides (removed in 4.0), <code>action.fcurves</code> on 5.x Slotted Actions, glTF exports that land on their back in every engine. Each contract is backed by a headless example that is smoke-tested on both LTS versions.
</p>

<p align="center">
  <code>/plugin marketplace add TMHSDigital/Blender-Developer-Tools@plugin-dist</code><br />
  <code>/plugin install blender-developer-tools@blender-developer-tools</code><br />
  <sub>Claude Code. Cursor and other agents: <a href="#quick-start">Quick start</a>.</sub>
</p>

<p align="center">
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/releases"><img src="https://img.shields.io/github/v/release/TMHSDigital/Blender-Developer-Tools?style=flat-square&color=e87d0d&label=release" alt="Release" /></a>
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/actions/workflows/blender-smoke.yml"><img src="https://img.shields.io/github/actions/workflow/status/TMHSDigital/Blender-Developer-Tools/blender-smoke.yml?branch=main&style=flat-square&label=blender%204.5%20%2B%205.2%20smoke" alt="Blender smoke tests" /></a>
  <a href="https://github.com/TMHSDigital/Blender-Developer-Tools/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/TMHSDigital/Blender-Developer-Tools/validate.yml?branch=main&style=flat-square&label=validate" alt="Validate" /></a>
  <a href="#license"><img src="https://img.shields.io/badge/license-CC%20BY--NC--ND%204.0%20%2B%20MIT%20code-384d54?style=flat-square" alt="License: CC BY-NC-ND 4.0, with snippets and templates under MIT" /></a>
  <a href="https://github.com/sponsors/TMHSDigital"><img src="https://img.shields.io/badge/sponsor-%E2%99%A5-ea4aaa?style=flat-square&logo=githubsponsors&logoColor=white" alt="Sponsor TMHSDigital on GitHub Sponsors" /></a>
</p>

<p align="center">
  <strong>18 skills</strong> &nbsp;&bull;&nbsp; <strong>9 rules</strong> &nbsp;&bull;&nbsp; <strong>3 templates</strong> &nbsp;&bull;&nbsp; <strong>29 snippets</strong> &nbsp;&bull;&nbsp; <strong>66 examples</strong> &nbsp;&bull;&nbsp; <strong>76 showcase pieces</strong>
</p>

<p align="center">
  <a href="https://tmhsdigital.github.io/Blender-Developer-Tools/gallery/">Examples Gallery</a>
  &nbsp;&bull;&nbsp; <a href="#quick-start">Quick start</a>
  &nbsp;&bull;&nbsp; <a href="#examples-and-showcase">Examples</a>
  &nbsp;&bull;&nbsp; <a href="showcase/">Showcase</a>
  &nbsp;&bull;&nbsp; <a href="skills/">Skills</a>
  &nbsp;&bull;&nbsp; <a href="rules/">Rules</a>
  &nbsp;&bull;&nbsp; <a href="templates/">Templates</a>
  &nbsp;&bull;&nbsp; <a href="snippets/">Snippets</a>
  &nbsp;&bull;&nbsp; <a href="ROADMAP.md">Roadmap</a>
</p>

---

## Overview

This repository ships **18 skills, 9 rules, 3 templates, 29 snippets, 66 examples, and 76 showcase pieces** for Blender Python development targeting Blender 5.2 LTS (current stable) with Blender 4.5 LTS fallback support. Blender 5.1 is prior stable.

The content is consumed by AI coding agents, installed as a plugin or read from a checkout — **there is no MCP server in this repository, and none is required**. Cursor and Claude Code both install it as a plugin (see [Quick start](#quick-start)): Cursor loads the skills and applies `rules/*.mdc` wherever their scope globs match; Claude Code loads the skills and gets the rules through a generated `blender-rules` skill, since it does not read Cursor `.mdc` files. An agent picks a skill up when its description matches the task. Any agent that can read files in a workspace can use it the same way. There is no build step for the content — edit the Markdown and Python files directly.

| Layer | Role |
| --- | --- |
| **Skills** | Guided workflows: scaffolding, operators, panels, properties, mesh and bmesh, headless batch, slotted actions, geometry nodes, procedural materials, depsgraph queries, drivers and handlers, `bl_info` migration, video sequencer, imported-mesh cleanup, high-to-low baking, engine export presets, extension runtime and packaging, timers, modal operators and threading |
| **Rules** | Guardrails for the most common AI mistakes: ops-in-loops, bmesh leaks, legacy `bl_info` only, prop assignments, deprecated context-copy override, per-element loops over bulk mesh data, import without scale check, export without evaluated geometry, mixed glTF/FBX axis RNA |
| **Templates** | A working Extensions Platform add-on starter, a headless batch script starter, and a GLB-in engine-ready asset pipeline |
| **Snippets** | 29 small standalone Python files demonstrating canonical patterns, 5 to 75 lines each |
| **Examples** | Runnable headless scripts under [`examples/`](examples/). Each asserts an API contract and exits non-zero on failure. |
| **Showcase** | Proof that the skills compose: each piece under [`showcase/`](showcase/) is one headless Python script that builds a game prop and runs the whole asset pipeline (cleanup, high-to-low bake, LODs, convex collider, engine export), asserting measured budgets on every LTS. Not API examples. Conventions: [`showcase/README.md`](showcase/README.md) |

## Quick start

Neither agent needs a clone of `main`: both install the slim `plugin-dist` build. Clone the full repository only to [run the examples or contribute](#run-the-examples-or-contribute).

- **Cursor** — install it as a local plugin from the slim `plugin-dist` branch, then run **Developer: Reload Window**. **Customize** lists the 18 skills and 9 rules; the rules apply by glob scope and the agent loads a skill when its description matches the task.

  ```bash
  git clone --branch plugin-dist --single-branch https://github.com/TMHSDigital/Blender-Developer-Tools.git ~/.cursor/plugins/local/blender-developer-tools
  ```

  (On Windows the folder is `%USERPROFILE%\.cursor\plugins\local\`. Cursor skips symlinks that point outside that folder, so clone or copy rather than link.) Teams can import the repository as a team marketplace instead; it carries `.cursor-plugin/marketplace.json`. The plugin already applies the rules, so there is nothing to copy. Only to scope the pack to one project without the plugin, copy `skills/*` into that project's `.cursor/skills/` and `rules/*.mdc` into `.cursor/rules/` from a checkout; copying only the rules gives you no skills.
- **Claude Code** — install as a plugin, then run `/skills` to see all 18 skills plus `blender-rules`:

  ```text
  /plugin marketplace add TMHSDigital/Blender-Developer-Tools@plugin-dist
  /plugin install blender-developer-tools@blender-developer-tools
  ```

  `@plugin-dist` is a generated branch holding only what the plugin loads (about 0.3 MB, rebuilt on every release), so the add does not clone the gallery renders, showcase props and history on `main`. Adding the repo without `@plugin-dist` still works; the plugin itself installs from `plugin-dist` either way.

  Claude Code does not read Cursor `.mdc` rules, so the plugin ships them as the `blender-rules` skill (generated from `rules/`), which Claude loads when it writes or reviews bpy code. No second clone is needed. To keep the rules in context all the time instead, add `@/path/to/Blender-Developer-Tools/claude/blender-rules.md` to your project's `CLAUDE.md` from a checkout. Without the plugin, copy `skills/*` and `claude/skills/*` into your project's `.claude/skills/`.

### Run the examples or contribute

The examples, the showcase and the gallery live on `main` (about 30 MB with the renders), so clone it only to run them or to send a change:

```bash
git clone https://github.com/TMHSDigital/Blender-Developer-Tools.git
```

- **Get Blender** — download **5.2 LTS** (primary target) or **4.5 LTS** (supported fallback) from [blender.org/download/lts](https://www.blender.org/download/lts/); current stable lives at [blender.org/download](https://www.blender.org/download/). The `blender` command below is that binary — on macOS it is inside the app bundle at `/Applications/Blender.app/Contents/MacOS/Blender`.
- **Run an example** — every example is a self-checking headless script (exit non-zero on failure, no GPU needed for the check):

```bash
blender --background --python examples/bmesh-gear/bmesh_gear.py --
```

### Updating and uninstalling

Releases ship often; [CHANGELOG.md](CHANGELOG.md) lists what each one changed.

- **Claude Code plugin** — `/plugin marketplace update blender-developer-tools` refreshes the marketplace and its plugins (from a shell: `claude plugin update blender-developer-tools@blender-developer-tools`). Remove it with `/plugin uninstall blender-developer-tools`, then `/plugin marketplace remove blender-developer-tools`.
- **Cursor local plugin** — `git pull` in `~/.cursor/plugins/local/blender-developer-tools`, then reload the window. Remove that folder to uninstall.
- **Checkout** (per-project Cursor copies, the optional always-on Claude rules import, examples) — `git pull` in the clone. Copied `.mdc` files do not update themselves: symlink `rules/*.mdc` into `.cursor/rules/` instead of copying, or re-copy after each pull. To uninstall, delete the copied or linked rules and the `@.../blender-rules.md` line from your `CLAUDE.md`.

## Supported Blender versions

| Version | Status |
| --- | --- |
| Blender 5.2 LTS | Primary target (current stable; all examples assume 5.2 unless a 4.5 path is shown) |
| Blender 5.1 | Prior stable (weekly cron; PR via `needs-5.1` or manual dispatch) |
| Blender 4.5 LTS | Fallback supported (skills show both code paths where 4.x and 5.x APIs diverge) |

## Falsifiers

Every one of the 66 examples carries a **falsifier**: a flag that changes the
input so a real assertion fails. It never disables the assertion, skips the
check, or short-circuits to an error — it feeds the script something the
contract says must not pass, and the same check that guards the happy path
catches it.

```bash
# The contract holds: exit 0
blender --background --python examples/bmesh-gear/bmesh_gear.py --

# The falsifier: skip the extrude, so the topology no longer matches the
# closed form. The topology check fires and the script exits 3.
blender --background --python examples/bmesh-gear/bmesh_gear.py -- --no-extrude
```

This is what makes a green run mean something. An assertion that has only
ever passed witnesses nothing — it could be comparing a constant to itself.
Proving each one fails once, on demand, is the difference between a test
suite and a set of scripts that print "OK". Shipping an example requires
demonstrating the falsifier's non-zero exit and reporting the measured error.

`--api`, `--check-pixels`, and `--output` are not falsifiers; they select a
code path rather than break a contract. Full conventions, including the
per-script exit-code model, are in
[`CONTRIBUTING.md`](CONTRIBUTING.md#exit-codes).

## Examples and showcase

**66 examples** in [`examples/`](examples/) are runnable, self-checking scripts: each asserts one API contract, carries a falsifier, and runs headless on Blender 5.2 LTS and 4.5 LTS in the `blender-smoke` workflow (5.1 on the weekly cron or by manual dispatch). Those whose contract is visible also render a still. **76 showcase pieces** in [`showcase/`](showcase/) exist to show the skills working together at production scale: each is a single headless script that models a game prop, then runs it through the same cleanup, bake, LOD, collider and export steps the skills teach, and fails if a measured budget (triangle counts, colliders, materials, real-world size) is missed. They are not API examples. Conventions: [`showcase/README.md`](showcase/README.md).

Browse both, with filters, full-size renders and each script's README, in the **[gallery](https://tmhsdigital.github.io/Blender-Developer-Tools/gallery/)**.

<p align="center">
  <a href="examples/grease-pencil-rosette/"><img src="examples/grease-pencil-rosette/preview.webp" width="24%" alt="Grease pencil rosette: five nested neon rose curves mounted as a sign on a brass-framed black lacquer board" /></a>
  <a href="examples/parent-inverse-orrery/"><img src="examples/parent-inverse-orrery/preview.webp" width="24%" alt="Parent inverse orrery: a brass tabletop orrery on a turned walnut base with a glowing gold sun and three mottled planets on riser posts" /></a>
  <a href="examples/compositor-glare/"><img src="examples/compositor-glare/preview.webp" width="24%" alt="Compositor glare: three neon rings with colored bloom halos" /></a>
  <a href="examples/image-pixels-testcard/"><img src="examples/image-pixels-testcard/preview.webp" width="24%" alt="Image pixels testcard: a studio monitor showing a procedural broadcast test card" /></a>
  <a href="showcase/apothecary-shelf/"><img src="showcase/apothecary-shelf/preview.webp" width="24%" alt="Apothecary shelf: a stained wooden shelf unit with an arched crest, gallery rails and three drawers, stocked with labelled glass bottles, flasks and glazed jars, on a dark studio floor" /></a>
  <a href="showcase/espresso-machine/"><img src="showcase/espresso-machine/preview.webp" width="24%" alt="Espresso machine: a brushed stainless E61 espresso machine with twin gauges, a chrome group head and a walnut-handled portafilter over a shot cup, cups on its warmer tray, beside a tamper, milk pitcher and knock box on a stone counter" /></a>
  <a href="showcase/wheelbarrow/"><img src="showcase/wheelbarrow/preview.webp" width="24%" alt="Wheelbarrow: a wooden tray with walls of stacked boards and iron straps, a spoked wheel, rear legs, and handles on a dark studio floor" /></a>
  <a href="showcase/farm-tractor/"><img src="showcase/farm-tractor/preview.webp" width="24%" alt="Farm tractor: green farm tractor in muddy ruts beside a puddle: long bonnet, barred grille, rusty exhaust stack, big rear tyres with mud-packed chevron lugs on cream rims with weights, small ribbed fronts." /></a>
</p>

## How content is organized

```
skills/<name>/SKILL.md   - 18 skill files, YAML frontmatter, one canonical pattern each
rules/<name>.mdc         - 9 rule files, anti-pattern + correction
templates/<name>/        - 3 template directories (extension-addon-template, headless-batch-script-template, ai-asset-pipeline-template)
snippets/<name>.py       - 29 standalone Python snippets, 5 to 75 lines each
examples/<name>/         - 66 example directories: script, README with exit codes and falsifier
showcase/<name>/         - 76 showcase pieces: budget-gated game props, script and README
claude/                  - generated Claude Code copies of the rules (blender-rules skill + import file)
```

## Using rules in Cursor

With the Cursor plugin installed, the `.mdc` files in `rules/` apply automatically when Cursor opens a Blender Python project, scoped by the `globs` in each rule's frontmatter. The nine rules are:

- `prefer-data-over-ops-in-loops`: flags `bpy.ops.*` calls inside object iteration
- `always-free-bmesh`: flags `bmesh.new()` without paired `bm.free()` in `try`/`finally`
- `target-extensions-platform-format`: flags add-ons missing `blender_manifest.toml`
- `type-annotate-props-and-defend-context`: flags `bpy.props` assignment form and unguarded `context.active_object`
- `prefer-temp-override-over-context-copy`: flags `bpy.context.copy()` passed to operators (deprecated 3.2, removed 4.0)
- `use-foreach-set-for-bulk-data`: flags Python loops over `mesh.vertices` setting `co`, normals, or other per-element bulk data
- `validate-imported-mesh-scale`: flags glTF/FBX import then mesh work with no `transform_apply` and no unit-scale check
- `no-unapplied-modifiers-on-export`: flags export of objects with live modifiers when the export does not request evaluated geometry
- `use-correct-axis-rna-per-exporter`: flags `export_scene.gltf` calls that pass FBX `axis_forward` / `axis_up`, and `export_scene.fbx` calls that pass glTF `export_yup`

Cursor: the plugin covers the rules (see [Quick start](#quick-start)); copying `rules/*.mdc` into a project's `.cursor/rules/` is only the per-project alternative without the plugin. Claude Code: the plugin ships the rules as the `blender-rules` skill.

## Using the templates

`templates/extension-addon-template/` is a working Blender extension. Copy the directory, edit `blender_manifest.toml` (id, version, name, maintainer, and `copyright`, which ships as the template author's), and install via Edit > Preferences > Get Extensions > Install From Disk. The template registers an Operator, a Panel, and a PropertyGroup, and demonstrates the `register_classes_factory` pattern with symmetric `register()` and `unregister()`.

`templates/headless-batch-script-template/` is a working starter for unattended Blender batch jobs. It opens a `.blend`, optionally adds and applies a modifier to every mesh, and exports to glTF, with explicit exit codes for CI integration. Run with `blender --background <input.blend> --python script.py -- --output ...`.

`templates/ai-asset-pipeline-template/` is a working starter for a headless GLB-in / engine-ready-out job. It imports a GLB, runs the `ai-mesh-cleanup` order, emits an LOD chain and optional collider, and exports under a Unity, Godot, or Unreal glTF preset. Run with `blender --background --python pipeline.py -- --input ... --outdir ... --preset unity`.

## Snippets

Each snippet is a standalone Python file under `snippets/`. They are not loaded as a package. Open one, copy the relevant lines into your script, and adapt the names. Each file's header comment cites the Blender doc URL or research section the pattern came from.

## Canonical references

| Resource | Use it for |
| --- | --- |
| [Blender 5.2 LTS Python API](https://docs.blender.org/api/current/) | Authoritative reference for current stable APIs |
| [Blender 5.1 Python API](https://docs.blender.org/api/5.1/) | Prior stable |
| [Blender 4.5 LTS Python API](https://docs.blender.org/api/4.5/) | LTS reference when targeting 4.5 |
| [Extensions Platform manual](https://docs.blender.org/manual/en/latest/advanced/extensions/index.html) | `blender_manifest.toml` schema, hosting, install flow |
| [developer.blender.org](https://developer.blender.org/) | Release notes, breaking change tracking, design docs |

When community content (Stack Overflow, older add-on source) conflicts with the official docs, prefer the docs. The 2.x to 4.x to 5.x churn around Actions, Extensions, and property handling has invalidated a lot of older material.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the candidate pool and what ships next. Releases are cut automatically from
conventional commits; the full history lives in [CHANGELOG.md](CHANGELOG.md).

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the
workflow, [SECURITY.md](SECURITY.md) for reporting vulnerabilities, and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards. New examples must
follow the anatomy of [`examples/bmesh-gear/`](examples/bmesh-gear/) and the render
look in [`docs/VISUAL-STYLE.md`](docs/VISUAL-STYLE.md).

## License

Copyright (c) 2026 TM Hospitality Strategies.

- **Code you copy and adapt is MIT:** [`snippets/`](snippets/LICENSE) and [`templates/`](templates/LICENSE). Copy lines or whole files into your own projects, modify them, and ship the result commercially; keep the copyright notice with substantial copies.
- **Everything else is [CC-BY-NC-ND-4.0](LICENSE):** skills, rules, examples, showcase pieces, docs and the site. The license covers this material itself: do not redistribute modified copies of it, and do not sell or commercially republish it.

A `LICENSE` file inside a directory governs that directory.

### Can I use this to build a commercial or GPL add-on?

**Yes.** Using the skills and rules while you (or your AI agent) write your own add-on, script or pipeline, including paid and client work, is the intended use. The code you write with their guidance is yours, under whatever license you choose. Blender extensions must be GPL-compatible, and that is fine too: the add-on template ships with `license = ["SPDX:GPL-3.0-or-later"]` in its manifest, and its MIT license lets you relicense your copy under the GPL.

What the NC-ND terms restrict is redistributing this pack: republishing modified copies of the skills, rules, examples or showcase pieces, or selling them (for example, bundling them into a paid course or a paid skill pack). Code copied out of `snippets/` and `templates/` is MIT and carries no such limit; keep the copyright notice with substantial copies.
