# Contributing to Blender Developer Tools

Thanks for helping improve this repository. This document describes how to set up locally, extend skills, rules, snippets, templates, examples, and showcase pieces, and submit changes.

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork:

   ```bash
   git clone https://github.com/<your-username>/Blender-Developer-Tools.git
   cd Blender-Developer-Tools
   ```

3. **Create a branch** for your work:

   ```bash
   git checkout -b your-feature-name
   ```

## Repository Structure

This repo is a content collection (skills, rules, snippets, templates, examples, and showcase pieces) for Blender Python development. There is no runtime and no MCP server. Headless checks run through `tests/smoke/run_example.py`; CI validates frontmatter, syntax, and aggregate counts.

```text
skills/
  <skill-name-kebab>/
    SKILL.md
rules/
  <rule-name>.mdc
snippets/
  <snippet-name>.py
templates/
  <template-name>/
    blender_manifest.toml
    __init__.py
    README.md
examples/
  gallery.json
  <example-name>/
    README.md
showcase/
  README.md
  gallery.json
  <piece-name>/
    README.md
```

- **`skills/`** - one directory per skill, each containing `SKILL.md` with YAML frontmatter (`name`, `description`, `standards-version`).
- **`rules/`** - Cursor-style rules as `.mdc` files with YAML frontmatter (`description`, `alwaysApply`, `globs`, `standards-version`).
- **`snippets/`** - small standalone `.py` files (5 to 50 lines) demonstrating a single canonical pattern.
- **`templates/`** - copy-paste starting points; one directory per template.
- **`showcase/`** - budget-conformance props, sibling of `examples/`. Not API
  contracts. Conventions: [`showcase/README.md`](showcase/README.md).

## Adding a Skill

1. Add a **kebab-case** directory under `skills/`, e.g. `skills/procedural-materials-and-shaders/`.
2. Create **`SKILL.md`** with YAML frontmatter:

   ```yaml
   ---
   name: procedural-materials-and-shaders
   description: One-line description, under 200 chars.
   standards-version: <current meta-repo STANDARDS_VERSION>
   ---
   ```

3. Aim for 150 to 350 lines covering the canonical pattern, common AI mistakes, version-correctness notes, and one or two worked code examples. Cite Blender API doc URLs where relevant. Avoid encyclopedic API tours.
4. The skill `name` in frontmatter must match the directory name exactly (CI enforces this).

## Adding a Rule

1. Add a **`.mdc`** file under `rules/`, e.g. `rules/use-foreach-set-for-bulk-data.mdc`.
2. Start with YAML **frontmatter**:

   ```yaml
   ---
   description: One-line summary for humans and tooling.
   alwaysApply: false
   globs:
     - "**/*.py"
   standards-version: <current meta-repo STANDARDS_VERSION>
   ---
   ```

   `alwaysApply: false` is deliberate and is what makes `globs` load-bearing:
   the rule enters context only when a file it matches does. `alwaysApply:
   true` would apply the rule in every context and make `globs` decorative, so
   the two must never both be set as if they compose. Pick globs that cover
   every file the rule is meant to guard before setting this — a glob that is
   too narrow means the rule silently stops firing, which is worse than
   over-applying. Record the scope in the `CLAUDE.md` rules table to match.

3. Write 30 to 80 lines: the anti-pattern, a code example showing it wrong, a code example showing it right, and a short "Why it matters" section.

## Adding a Snippet

1. Add a `.py` file under `snippets/`, e.g. `snippets/depsgraph-evaluated-mesh.py`.
2. Keep it 5 to 50 lines, fully working code, with a header comment naming the snippet and citing the relevant Blender doc URL or research section.
3. Snippets are validated for Python syntax in CI.

## Adding a Template

1. Add a directory under `templates/`, e.g. `templates/headless-batch-script-template/`.
2. Include all files needed for an immediate copy-paste starting point. For add-on templates, include `blender_manifest.toml`, `__init__.py`, and a brief `README.md`.

## Adding a Showcase Piece

Read [`showcase/README.md`](showcase/README.md) first. Showcase asserts
budget conformance, never an API contract.

1. Add `showcase/<kebab-name>/` with a script, a README that includes an
   exit-code table, and a falsifier that breaks one pipeline stage so a
   **named** budget fails.
2. List the directory in `.cursor-plugin/plugin.json` `"showcase"` and add a
   `tests/smoke/catalog.json` row. The runner takes opaque script paths.
3. Add a `showcase/gallery.json` `pieces[]` entry, render a still, and run
   `python scripts/build_gallery.py`. Do not hand-edit `docs/gallery/` HTML.
4. Update the README showcase-piece count. `validate-counts` checks it
   separately from the example total.

## Blender Version Targeting

Content targets **Blender 5.2 LTS** as primary, **Blender 5.1** as prior stable, and **Blender 4.5 LTS** as fallback. When the API differs, branch on `bpy.app.version` and document both paths. Example:

```python
if bpy.app.version >= (5, 0, 0):
    # 5.x path
    ...
else:
    # 4.5 LTS path
    ...
```

## Blender smoke on pull requests

Default PR smoke is Blender 5.2 and 4.5 (`.github/workflows/blender-smoke.yml`).
5.1 is not in that matrix.

- Apply the `needs-5.1` label when the change can diverge on 5.1 (bake, UV
  RNA, version-branched API). That starts a 5.1 smoke job. Auto-label will
  not apply this; it is opt-in.
- Run any series on demand: Actions > Blender Smoke Test > Run workflow,
  pick the branch and the `series` input.
- Monday 07:00 UTC cron still runs 5.2, 5.1, and 4.5. Do not treat cron as
  PR evidence.
- **There is deliberately no `push` trigger on `blender-smoke.yml`.**
  Squash-merging a green PR makes `main` identical to the content already
  smoke-tested, so a push job would re-prove the same tree at double the
  CI cost. Absence of post-merge smoke is not a coverage gap.
- **`pages.yml` is path-filtered.** A workflow-or-docs-only merge does not
  deploy Pages. Observed on `13ea521` (`ci:` #137): Validate, drift-check,
  and Release ran; Pages did not. Intentional, not a failed job.

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

## Falsifiers must fail the budget they target

Every falsifier declares the budget it aims at, and it must fail **that**
budget. A falsifier that exits non-zero on some earlier check proves
nothing about its target: the run is red for the wrong reason, and the
budget it was built for was never reached.

Fix a collision by changing the model or the falsifier. **Never widen a
band so an ill-aimed falsifier lands.**

Worked example. `showcase/stone-archway`'s arch falsifier began as
`--flat-arch`, laying the voussoirs as a flat lintel. A lintel is 0.62 m
shorter than the arch, so it tripped the bounding-box budget (exit 8) and
never reached the intrados circle fit (exit 19) it existed to break.
Widening the bbox tolerance to let it through would have destroyed a real
budget to rescue a bad falsifier. It was replaced by `--off-circle`, which
keeps the angles, joints, materials, triangle count and envelope identical
and wanders only the intrados radius. Four other falsifiers in the same run
needed the same treatment: a stray vertex moved inside the silhouette, a
`--short-skids` that floats one runner of three instead of all of them, a
`--same-seed` split into design and placement RNG streams, and a
`--sink-keystone` that no longer changes the Y envelope.

`tests/check_falsifier_targets.py` enforces the declaration. Its default
static mode reads each showcase piece's falsifier table and asserts the
flags are real argparse flags, the declared exit codes appear in that
piece's exit-code table, and every falsifier names a target budget. Its
`--run BLENDER` mode executes each falsifier and asserts the **observed**
exit equals the declared one — the mode that catches an ill-aimed
falsifier. Runtime costs one Blender launch per falsifier, so it is an
authoring and cron tool, not a per-PR smoke step.

## Exit codes

Three roles, not one global table. Do not copy a code from one script into
another and assume it means the same thing. `9` is a valid sequential-check
code; there is no rule against it.

**Per-script exits** (examples and headless templates). `0` success. `2`
argument or usage error, matching argparse. `3` and above for that script's
own sequential check failures, in the order the checks run. These codes are
file-local and are not portable. `no-mesh` is `2` in
`templates/headless-batch-script-template/` and `5` in
`templates/ai-asset-pipeline-template/`; both are correct. Copy a template's
own table from that template, not from this paragraph.

**FATAL wrapper.** `sys.exit(1)` on an uncaught exception in the `__main__`
guard. Uniform across the examples. `1` means crashed, never a named check.

**Smoke protocol.** Owned by `tests/` and the runner, not by product check
tables. `0` pass, `1` fail (`tests/smoke/run_example.py`,
`tests/check_import_export_rules.py`), `77` skip (`tests/smoke/canary_skip.py`,
and the product scripts that self-skip: `examples/gn-bundle-roundtrip/`,
`examples/exit-pre-sidecar/`). A script under test prints `SMOKE_SKIP:` and
exits 77; the runner records SKIP and returns 0 so the YAML step stays green.

**Version-gated falsifiers.** A falsifier for a cross-version removal or
rename is version-gated by nature. It exits its documented code on versions
where the API changed and exits 0 on versions where the old API still works.
That is the correct witness: the naive script is still valid on the older
binaries. It differs from every other falsifier in the tree (for example
`--same-axis`), which is red on all three versions.

Do not "fix" these flags to fail unconditionally. The examples that behave
this way:

- `examples/vse-linear-modifiers/` (`--assume-present`)
- `examples/gn-socket-rename/` (`--legacy-ids`)
- `examples/eval-mesh-datablock-name/` (`--assume-distinct-names`)
- `examples/mesh-automasking-settings/` (`--assume-brush-attrs`)

## Standards-version Markers

Files that participate in ecosystem drift checking must carry a `standards-version` marker matching the current meta-repo `STANDARDS_VERSION` (which is decoupled from this repo's `VERSION`):

- `AGENTS.md`, `CLAUDE.md`, `ROADMAP.md`: HTML comment first line, e.g. `<!-- standards-version: <STANDARDS_VERSION> -->`.
- `skills/*/SKILL.md`, `rules/*.mdc`: YAML frontmatter field `standards-version: <STANDARDS_VERSION>`.

The drift-check workflow enforces these on every push and PR.

## Aggregate Counts

`README.md` declares aggregate counts (e.g. "16 skills, 9 rules, 3 templates, 27 snippets, 59 examples, and 26 showcase pieces"). The `validate-counts` job in `.github/workflows/validate.yml` enforces these substrings against the filesystem on every push and PR. Showcase pieces are counted separately from examples. When you add or remove content, update the README counts in the same commit.

## Pull Request Process

1. **Update docs** if you change skill or rule lists, content counts, or versioning (`README.md`, `CLAUDE.md`, `ROADMAP.md` as appropriate). The release workflow rewrites `CHANGELOG.md`, `CLAUDE.md` `**Version:**` line, and `ROADMAP.md` `**Current:**` line automatically when a `feat:` or `fix:` commit lands on `main`, so only edit those files for content beyond the version markers.
2. **Open a PR** against `main` with a clear title and summary of changes.
3. **Use Conventional Commits** for the PR title (and the squash-merge subject, which is what the release workflow scans). Prefixes: `feat:` (minor bump), `fix:` (patch bump), `feat!:` / `fix!:` / `BREAKING CHANGE` (major bump), `chore:` / `docs:` / `ci:` / `refactor:` (no release — the workflow runs and exits without tagging). A mixed range still releases if any commit since the last tag is a `feat:`/`fix:`. `[skip ci]` remains an optional override and is no longer required to avoid a release for non-release commits.
4. **Respond to review** feedback; CI must pass before merge. Documentation-only and chore changes do not trigger a release.

## Developer Certificate of Origin and Inbound License Grant

This project uses CC-BY-NC-ND-4.0 as its outbound license, which forbids derivatives. Every pull request is a derivative. Contributions are accepted inbound under a broader grant via the Developer Certificate of Origin (DCO), which resolves the conflict so the project can accept and redistribute contributions.

### Required grant

By submitting a contribution to this repository, you certify that you have the right to do so under the Developer Certificate of Origin (DCO) 1.1, and you grant TMHSDigital a perpetual, worldwide, non-exclusive, royalty-free, irrevocable license to use, reproduce, prepare derivative works of, publicly display, publicly perform, sublicense, and distribute your contribution under the project's current license (CC-BY-NC-ND-4.0) or any successor license chosen by the project.

### DCO sign-off

Every commit in a pull request must have a `Signed-off-by:` trailer matching the commit author:

```
Signed-off-by: Jane Developer <jane@example.com>
```

Signing is done at commit time:

```bash
git commit -s -m "feat: add new skill"
```

The GitHub DCO App enforces this on every PR.

For the full inbound/outbound model and rationale, see [`standards/licensing.md`](https://github.com/TMHSDigital/Developer-Tools-Directory/blob/main/standards/licensing.md) in the Developer-Tools-Directory meta-repo.

## Code of Conduct

This project follows the guidelines in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). By participating, you agree to uphold them.
