<!-- standards-version: 1.10.0 -->

# AGENTS.md

Guidance for AI coding agents working on the Blender Developer Tools repository.

**Division of labor:** this file carries fleet-standard governance and workflow
rules — branching, commits, merge and CI-evidence policy, release automation,
authoring standards. `CLAUDE.md` carries repo-specific operational facts an
agent needs at runtime — content inventory, Blender runtime discovery, git
staging hazards, and the example-shipping quality gates. Read both; neither
repeats the other.

## Repository overview

Skills, rules, snippets, starter templates, and runnable smoke-gated examples
for Blender Python development. The repo targets **Blender 5.1** (current
stable) with a **Blender 4.5 LTS** fallback. There is no MCP server. It ships
a `.cursor-plugin/plugin.json` manifest so the ecosystem drift checker
classifies it as a `cursor-plugin`. This is content the AI loads when the user
asks Blender questions or works on Blender add-ons in Cursor or Claude Code.

The content base is 12 skills, 6 rules, 2 templates, 17 snippets, and 23
examples (counts are CI-enforced against README.md and the manifest). The full
inventory tables and per-item purposes live in `CLAUDE.md`. Example anatomy
and authoring rules: copy `examples/bmesh-gear/`; the render look is specified
in `docs/VISUAL-STYLE.md`; the canonical run prompt is
`docs/new-example-prompt.md`.

## Repository structure

```
Blender-Developer-Tools/
  skills/<skill-name>/SKILL.md   # 12 skill files
  rules/<rule-name>.mdc          # 6 rule files
  templates/<template-name>/     # 2 starter templates
  snippets/<snippet-name>.py     # 17 standalone Python snippets
  examples/<name>/               # 23 runnable smoke-gated examples (+ gallery.json)
  examples/gallery_framing.py    # shared Layer 1 framing measurement (render path only)
  scripts/build_gallery.py       # generates docs/gallery/ (stdlib only)
  scripts/site/                  # vendored landing-page build (build_site.py + template)
  docs/gallery/                  # committed generated gallery pages + hero assets
  docs/new-example-prompt.md     # canonical example-creation prompt
  .github/workflows/             # validate, blender-smoke, drift-check, release, pages, label-sync, stale
  .github/dependabot.yml
  AGENTS.md, CLAUDE.md, README.md, ROADMAP.md, CHANGELOG.md
  CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md
  VERSION                        # source of truth for the repo version
  LICENSE                        # CC-BY-NC-ND-4.0
```

## Branching and commit model

- Single `main` branch. No develop or release branches. Work on a focused
  feature branch off an up-to-date `main`. Never force-push or bypass hooks.
- Conventional commits drive the auto-release workflow. It scans the commit subjects since
  the last tag and releases only when at least one is release-worthy:
  - `feat:` triggers a minor bump
  - `fix:` triggers a patch bump
  - `feat!:` / `fix!:` / `BREAKING CHANGE` triggers a major bump
  - Other types (`chore:`, `docs:`, `ci:`, `refactor:`, etc.) do **not** cut a release: the
    workflow runs, decides there is nothing to release, and exits without a tag or version
    bump. A mixed push still releases if any commit in range is a `feat:`/`fix:`.
  - `[skip ci]` in the head commit still bypasses the workflow entirely. With the commit-type
    gate above it is now an optional override, not a requirement for non-release commits.
- Commit messages should describe the why, not the what, and carry a DCO
  `Signed-off-by:` trailer matching the commit author (see CONTRIBUTING.md).
- Stage with explicit paths only — never `git add -A` or `git add .`. The
  reason is a repo-specific hazard documented in `CLAUDE.md` § Git staging.

## Merge policy and CI evidence

- **Squash-merge with branch deletion is the standard.** The PR becomes one
  commit on `main`; delete the remote feature branch after merge, then
  fast-forward local `main`.
- **Smoke jobs do not re-run on the merge SHA.** `blender-smoke.yml` triggers
  on `pull_request` (plus a weekly schedule and manual dispatch) — there is no
  `push` trigger. The correct post-merge evidence for example changes is:
  both Blender smoke jobs (4.5 LTS and 5.1) passed on the PR head SHA that
  became the sole squash-merged commit, with the actual binary versions
  confirmed in the job logs.
- **Post-merge, verify green on `main`:** Release (`release.yml`), Validate
  (`validate.yml`), Ecosystem drift check (`drift-check.yml`), and Deploy
  GitHub Pages (`pages.yml`; paths-filtered, so it does not trigger for every
  change).
- **Socket Security checks** ("Socket Security: Project Report" and "Socket
  Security: Pull Request Alerts") run on PRs via the Socket GitHub App. No
  override policy has been decided: a pending or failing Socket check is
  unresolved — wait before merging.
- **Release-owned fields are never hand-edited:** `VERSION`, `CHANGELOG.md`,
  the CLAUDE.md `**Version:**` line, the ROADMAP.md `**Current:**` line, and
  the manifest `"version"` in `.cursor-plugin/plugin.json`. Generated gallery
  pages under `docs/gallery/` are regenerated via `scripts/build_gallery.py`,
  never hand-edited.
- **Evidence over assertion:** PR bodies must label what was proven by live
  run versus established by inspection only.

## Blender version targeting

- Primary: **Blender 5.1.x** (current stable). All examples assume 5.1
  unless otherwise stated.
- Fallback: **Blender 4.5 LTS**. Skills and the extension template note 4.5
  compatibility where it matters (slotted actions bridge, property delete,
  manifest fields).
- Future: a 5.2 LTS sweep is planned for July 2026 (see `ROADMAP.md`).

When a 4.x and 5.x API genuinely diverge, skills must show both code paths,
not just the 5.x one. The `slotted-actions-animation` skill is the load-bearing
example. Local binary discovery and version-reporting rules are in
`CLAUDE.md` § Blender runtime discovery.

## Skills

Each skill lives at `skills/<skill-name>/SKILL.md`. Frontmatter is YAML:

```yaml
---
name: <kebab-case-skill-name>
description: <one-line, under 200 chars>
standards-version: 1.10.0
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
standards-version: 1.10.0
---
```

Rules encode anti-patterns. Each rule should show the wrong way, the right
way, and a one-paragraph rationale. 30 to 80 lines is the right size.

## CI/CD workflows

- `validate.yml` runs file structure checks plus a `validate-counts` job that
  asserts the README aggregate counts (skills, rules, templates, snippets,
  and examples) match filesystem reality. The counts language in `README.md`
  is load-bearing: the job greps for it.
- `validate.yml` also runs a `validate-manifest` job that checks
  `.cursor-plugin/plugin.json` against reality: every listed path must exist,
  every skill, rule, snippet, template, and example on disk must be listed,
  and the manifest `version` must equal `VERSION`. The release pipeline owns
  the manifest `version` line (see `release.yml` below) — never hand-edit it.
- `blender-smoke.yml` executes every shipped example (check-only, no render)
  plus snippet/template smoke tests inside REAL headless Blender, on both
  4.5 LTS and 5.1, on every PR and a weekly schedule. A new example is not
  shipped until it has a step here.
- `drift-check.yml` consumes `Developer-Tools-Directory/.github/actions/
  drift-check@v1.15` to enforce ecosystem standards-version markers.
- `release.yml` auto-bumps the version, tags, force-updates floating tags
  `v0` and `v0.1`, and runs `release-doc-sync@v1` to rewrite CHANGELOG.md,
  CLAUDE.md `**Version:**`, and ROADMAP.md `**Current:**`. It also rewrites
  the `"version"` line in `.cursor-plugin/plugin.json` so the manifest tracks
  each release. Triggered on push to `main` for content-changing paths only.
- `label-sync.yml` self-heals labels via `gh label create --force` per
  label, then applies them to the PR.
- `pages.yml` builds the landing page from the **locally vendored** template
  at `scripts/site/` (originally scaffolded from Developer-Tools-Directory's
  site-template, now owned by this repo — the fleet template only scaffolds
  new tools) plus the examples gallery via `scripts/build_gallery.py`, then
  deploys `docs/`. `docs/index.html`, `docs/fonts/`, and `docs/assets/` are
  build outputs and gitignored; `docs/gallery/` is committed.

## Where to look for canonical references

- Blender 5.1 Python API: https://docs.blender.org/api/current/
- Blender 4.5 LTS Python API: https://docs.blender.org/api/4.5/
- Extensions Platform reference: https://docs.blender.org/manual/en/latest/advanced/extensions/index.html
- Release notes (`developer.blender.org`): https://developer.blender.org/
- Live MCP session vs headless harness policy: `CLAUDE.md` § "Live MCP vs Headless Harness" — headless is the only source of truth for evidence.

When information conflicts, prefer the docs over Stack Overflow or older
add-on source. The 2.x to 4.x to 5.x churn around Actions, Extensions, and
property handling has invalidated a lot of community content.

## License

CC-BY-NC-ND-4.0. See `LICENSE`.
