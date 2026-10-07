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
for Blender Python development. The repo targets **Blender 5.2 LTS** (current
stable) with a **Blender 4.5 LTS** fallback. **Blender 5.1** is prior stable. There is no MCP server. It ships
a `.cursor-plugin/plugin.json` manifest so the ecosystem drift checker
classifies it as a `cursor-plugin`. This is content the AI loads when the user
asks Blender questions or works on Blender add-ons in Cursor or Claude Code.

The content base is 18 skills, 9 rules, 3 templates, 29 snippets, 66
examples, and 77 showcase pieces (counts are CI-enforced across README.md, the agent docs, ROADMAP.md,
`site.json` and the site templates). The full inventory tables and per-item purposes live in
`CLAUDE.md`. Example anatomy and authoring rules: copy `examples/bmesh-gear/`;
showcase conventions: `showcase/README.md`. The render look is specified
in `docs/VISUAL-STYLE.md`; the canonical run prompt is
`docs/new-example-prompt.md`.

## Repository structure

```
Blender-Developer-Tools/
  skills/<skill-name>/SKILL.md   # 18 skill files
  rules/<rule-name>.mdc          # 9 rule files
  templates/<template-name>/     # 3 starter templates
  snippets/<snippet-name>.py     # 29 standalone Python snippets
  examples/<name>/               # 66 runnable smoke-gated examples (+ gallery.json)
  examples/gallery_framing.py    # shared Layer 1 framing measurement (render path only)
  showcase/<name>/               # budget-conformance props (sibling of examples/)
  showcase/gallery.json          # this tree's gallery index; merged into docs/gallery/
  scripts/build_gallery.py       # generates docs/gallery/ (stdlib only)
  scripts/site/                  # vendored landing-page build (build_site.py + template)
  docs/gallery/                  # committed generated gallery pages + hero assets
  docs/new-example-prompt.md     # canonical example-creation prompt
  .github/workflows/             # validate, blender-smoke, drift-check, release, pages, label-sync, stale
  .github/dependabot.yml
  AGENTS.md, CLAUDE.md, README.md, ROADMAP.md, CHANGELOG.md
  CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md
  VERSION                        # source of truth for the repo version
  LICENSE                        # CC-BY-NC-ND-4.0 (snippets/ and templates/ carry their own MIT LICENSE)
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
  - Exception: if plugin content (`skills/`, `claude/`, `rules/`, `snippets/`, `templates/`)
    changed since the last tag, a patch release is cut whatever the commit types, so a
    `docs:` fix to a skill still reaches plugin users
    (`.github/scripts/plugin-content-changed.sh`).
  - The `plugin-dist` branch is republished only when the built plugin differs from the
    published one (`build_plugin_dist.py --fingerprint`, which ignores version strings). A
    release cut for the gallery or site leaves plugin users on their current version
    instead of offering an update with identical content.
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
- **Smoke runs on the PR head and again on `main`.** `blender-smoke.yml`
  triggers on `pull_request`, on `push` to `main` (both with the same
  `paths-ignore`: `**.md`, `docs/**`, `assets/**`), weekly, and on manual
  dispatch. The merge evidence for example changes is still both Blender smoke
  jobs (5.2 LTS and 4.5 LTS) passing on the PR head SHA that became the sole
  squash-merged commit, with the actual binary versions confirmed in the job
  logs. The push run is what `release-gate.sh` waits for on a direct push to
  `main`; for a PR merge the gate reads the PR's own checks.
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
  the manifest `"version"` in `.cursor-plugin/plugin.json`,
  `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. Generated gallery
  pages under `docs/gallery/` are regenerated via `scripts/build_gallery.py`,
  never hand-edited.
- **Evidence over assertion:** PR bodies must label what was proven by live
  run versus established by inspection only.

## Blender version targeting

- Primary: **Blender 5.2 LTS** (current stable). All examples assume 5.2
  unless otherwise stated.
- Prior stable: **Blender 5.1**. Skills document 5.1-only contracts where they
  still matter; weekly smoke keeps a 5.1 leg.
- Fallback: **Blender 4.5 LTS**. Skills and the extension template note 4.5
  compatibility where it matters (slotted actions bridge, property delete,
  manifest fields, NodesModifier dict inputs).

When a 4.x and 5.x API genuinely diverge, skills must show both code paths,
not just the 5.x one. The `slotted-actions-animation` skill is the load-bearing
example. Local binary discovery and version-reporting rules are in
`CLAUDE.md` § Blender runtime discovery.

## Skills

Each skill lives at `skills/<skill-name>/SKILL.md`. Frontmatter is YAML:

```yaml
---
name: <kebab-case-skill-name>
description: "<what it covers>. Use when <the situations, API names and error strings that should load it>."  # <= 1024 chars, enforced
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
alwaysApply: false
globs:
  - "**/*.py"
standards-version: 1.10.0
---
```

`alwaysApply: false` plus `globs` is the scoping contract: the rule loads only
when a matching file is in context. Setting `alwaysApply: true` makes `globs`
decorative and applies the rule everywhere, so the documented scope stops
describing behavior. Choose globs that cover every file the rule guards.

Rules encode anti-patterns. Each rule should show the wrong way, the right
way, and a one-paragraph rationale. 30 to 80 lines is the right size.

## CI/CD workflows

- `validate.yml` runs file structure checks plus a `validate-counts` job that
  asserts the README aggregate counts (skills, rules, templates, snippets,
  examples, and showcase pieces) match filesystem reality. The counts language in `README.md`
  is load-bearing: the job greps for it.
- `validate.yml` also runs a `validate-manifest` job that checks
  `.cursor-plugin/plugin.json` against Cursor's plugin schema (no keys outside
  it; Cursor rejects unknown ones) and against reality: every listed skill
  and rule exists and every one on disk is listed, `marketplace.json` lists
  this plugin, and the manifest `version` must equal `VERSION`. The release pipeline owns
  the manifest `version` line (see `release.yml` below) — never hand-edit it.
  `tests/check_manifest_meta.py` (same job) keeps the Cursor and Claude Code
  manifests in step: one description, the site as `homepage`, one license
  string (also the gallery footer's), the same keywords, and a Cursor `logo`
  that the plugin-dist build ships.
- `blender-smoke.yml` executes every shipped example (check-only, no render)
  plus snippet/template smoke tests inside REAL headless Blender, on
  5.2 LTS and 4.5 LTS for every PR. 5.1 is weekly cron, the opt-in
  `needs-5.1` PR label (`pull_request` types include `labeled`), or
  `workflow_dispatch` with a `series` input. Auto-label does not apply
  `needs-5.1`. It also runs on `push` to `main` (same `paths-ignore`), which
  is what the release gate waits for on a direct push. Contributor-facing
  notes for the smoke lever, Pages path filters, and the three-role exit-code
  convention live in CONTRIBUTING.md. Examples run
  through `tests/smoke/run_example.py` (catalog: `tests/smoke/catalog.json`).
  SKIP is exit 77 plus a `SMOKE_SKIP:` reason, and only when `--min-version`
  is above this Blender; exit 0 with that marker is a vacuous pass and fails.
  Post-exit sidecars are opt-in (`--expect-sidecar`). A leg with zero PASSes
  is red. A new example is not shipped until it has a catalog row.
- `drift-check.yml` consumes `Developer-Tools-Directory/.github/actions/
  drift-check`, pinned by SHA (the pin's comment names the tag), to enforce
  ecosystem standards-version markers.
- `release.yml` runs on every push to `main` (no path filter). It releases
  only when a commit subject in range is `feat:`/`fix:`/breaking, and only
  after `.github/scripts/release-gate.sh` sees green CI for the SHA. It then
  bumps the version, tags `vX.Y.Z`, force-updates the floating tags
  `v<major>` and `v<major>.<minor>` (currently `v0` and `v0.143`), runs
  `release-doc-sync` to rewrite CHANGELOG.md, CLAUDE.md `**Version:**`, and
  ROADMAP.md `**Current:**`, rewrites the `"version"` in
  `.cursor-plugin/plugin.json`, `.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json`, and force-pushes the slim plugin build
  to the `plugin-dist` branch.
- **Release notes and the commit-type policy.** `.github/scripts/release_notes.py`
  writes the GitHub release body and the CHANGELOG entry in two parts: **For
  agents and users** lists the commits that touched what the plugin ships
  (`skills/`, `rules/`, `snippets/`, `templates/`, `claude/`), grouped
  Features / Fixes / Other, and leads; everything else (CI, tests, the site
  and gallery, examples, showcase, docs) goes in a collapsed **Maintenance**
  `<details>` block. A release with no plugin change says so in one line above
  that block. Every release emails watchers, so pick the commit type by who
  receives the change: use `feat:`/`fix:` for changes to plugin content or
  to what a user runs; use `ci:`, `test:`, `docs:`, `style:` or `chore:` (not
  `fix(ci)`, `fix(tests)` or `fix(site)`) for maintenance, so it does not cut
  a release on its own. Pages still deploys from those commits (`pages.yml`
  runs on its own path filter), and the next release lists them under
  Maintenance. `tests/test_release_notes.py` covers the split.
- `label-sync.yml` creates any missing label and applies path-based labels
  to same-repo PRs.
- `pages.yml` builds the landing page from the **locally vendored** template
  at `scripts/site/` (originally scaffolded from Developer-Tools-Directory's
  site-template, now owned by this repo — the fleet template only scaffolds
  new tools) plus the examples gallery via `scripts/build_gallery.py`, then
  deploys `docs/`. `docs/index.html`, `docs/fonts/`, and `docs/assets/` are
  build outputs and gitignored; `docs/gallery/` is committed.

## Where to look for canonical references

- Blender 5.2 LTS Python API: https://docs.blender.org/api/current/
- Blender 5.1 Python API: https://docs.blender.org/api/5.1/
- Blender 4.5 LTS Python API: https://docs.blender.org/api/4.5/
- Extensions Platform reference: https://docs.blender.org/manual/en/latest/advanced/extensions/index.html
- Release notes (`developer.blender.org`): https://developer.blender.org/
- Live MCP session vs headless harness policy: `CLAUDE.md` § "Live MCP vs Headless Harness" — headless is the only source of truth for evidence.

When information conflicts, prefer the docs over Stack Overflow or older
add-on source. The 2.x to 4.x to 5.x churn around Actions, Extensions, and
property handling has invalidated a lot of community content.

## Branch protection on `main`

`main` carries the repository ruleset **`main-integrity`** (branch target
`~DEFAULT_BRANCH`, enforcement `active`, **no bypass actors**). Three rules:

- `deletion` — the branch cannot be deleted
- `non_fast_forward` — force-push is refused for every actor, owner included
- `required_linear_history` — merge commits are refused, matching the
  squash-merge convention

Verify with `gh api repos/TMHSDigital/Blender-Developer-Tools/rules/branches/main`.
The classic `/branches/main/protection` endpoint returns 404 by design: this
is a ruleset, not classic branch protection, and the two are separate APIs.

**Required status checks are deliberately absent, and a pull request is not
required.** A PR whose smoke jobs are red can still be merged. Merge-on-green
is convention here, not enforcement — see
[#192](https://github.com/TMHSDigital/Blender-Developer-Tools/issues/192).

The reason is structural. A required-status-check rule blocks *direct pushes*
to the branch for any actor without a bypass, not only PR merges.
`release.yml` pushes its version-bump commit straight to `main` as
`github-actions[bot]` using `secrets.GITHUB_TOKEN`, so the rule would break
every release. On a user-owned repository GitHub rejects the only bypass
actor that would cover it:

```
422 Validation Failed
"Actor GitHub Actions integration must be part of the ruleset source or owner organization"
```

A role-based bypass does not substitute: `RepositoryRole:Write` covers the
repository owner (admin inherits write) and never covers the bot — backwards
from what is needed, and it would re-open admin merges of red PRs, which is
the hole the protection exists to close.

The three rules that *are* active were chosen because a fast-forward,
single-parent push does not violate any of them, so `release.yml` keeps
working untouched: the bump commit lands, the tag push proceeds (a branch
ruleset does not target tags), the GitHub release is cut, and the
`gh workflow run pages.yml --ref main` dispatch fires.

### If required checks become enforceable

Should the repository move to an organization, or `release.yml` stop pushing
to `main`, these are the checks that run unconditionally on every PR and are
therefore the required-check set:

- `Blender 4.5 smoke`
- `Blender 5.2 smoke`
- `Ecosystem drift check`
- `Validate content counts`
- `Validate plugin manifest`
- `Validate smoke harness protocol`
- `Validate structure and frontmatter`

Three checks that appear on PRs are deliberately **excluded**:

- **`Blender 5.1 smoke` is label-gated.** It only runs when `needs-5.1` is
  applied. As a required check it would block every unlabeled PR forever on
  a job that never reports.
- **`Auto-label by path`** — `label-sync.yml` triggers on `opened` and
  `synchronize` only. A reopened PR with no new push never reports it.
- **`Resolve smoke matrix`** — skipped on label events other than
  `needs-5.1`, and it is plumbing rather than a gate; its failure already
  blocks the two smoke jobs that depend on it.

The two `Socket Security` checks come from a third-party GitHub App. An
outage or an uninstall would deadlock merges, so they are advisory.

## License

CC-BY-NC-ND-4.0 (see `LICENSE`), except `snippets/` and `templates/`, which are MIT (see the `LICENSE` file in each directory) so the documented copy-and-adapt use is lawful.
