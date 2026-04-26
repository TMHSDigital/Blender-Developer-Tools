# Contributing to Blender Developer Tools

Thanks for helping improve this repository. This document describes how to set up locally, extend skills, rules, snippets, and the template, and submit changes.

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

This repo is a content collection (skills, rules, snippets, and one template) for Blender Python development. There is no runtime, no MCP server, and no test runner; CI validates frontmatter, syntax, and aggregate counts.

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
```

- **`skills/`** - one directory per skill, each containing `SKILL.md` with YAML frontmatter (`name`, `description`, `standards-version`).
- **`rules/`** - Cursor-style rules as `.mdc` files with YAML frontmatter (`description`, `alwaysApply`, `globs`, `standards-version`).
- **`snippets/`** - small standalone `.py` files (5 to 30 lines) demonstrating a single canonical pattern.
- **`templates/`** - copy-paste starting points; one directory per template.

## Adding a Skill

1. Add a **kebab-case** directory under `skills/`, e.g. `skills/procedural-materials/`.
2. Create **`SKILL.md`** with YAML frontmatter:

   ```yaml
   ---
   name: procedural-materials
   description: One-line description, under 200 chars.
   standards-version: <current meta-repo VERSION>
   ---
   ```

3. Aim for 150 to 350 lines covering the canonical pattern, common AI mistakes, version-correctness notes, and one or two worked code examples. Cite Blender API doc URLs where relevant. Avoid encyclopedic API tours.
4. The skill `name` in frontmatter must match the directory name exactly (CI enforces this).

## Adding a Rule

1. Add a **`.mdc`** file under `rules/`, e.g. `rules/avoid-python-loops-on-vertices.mdc`.
2. Start with YAML **frontmatter**:

   ```yaml
   ---
   description: One-line summary for humans and tooling.
   alwaysApply: true
   globs:
     - "**/*.py"
   standards-version: <current meta-repo VERSION>
   ---
   ```

3. Write 30 to 80 lines: the anti-pattern, a code example showing it wrong, a code example showing it right, and a short "Why it matters" section.

## Adding a Snippet

1. Add a `.py` file under `snippets/`, e.g. `snippets/depsgraph-evaluated-mesh.py`.
2. Keep it 5 to 30 lines, fully working code, with a header comment naming the snippet and citing the relevant Blender doc URL or research section.
3. Snippets are validated for Python syntax in CI.

## Adding a Template

1. Add a directory under `templates/`, e.g. `templates/headless-batch-script-template/`.
2. Include all files needed for an immediate copy-paste starting point. For add-on templates, include `blender_manifest.toml`, `__init__.py`, and a brief `README.md`.

## Blender Version Targeting

Content targets **Blender 5.1** as primary, with **Blender 4.5 LTS** as fallback. When the API differs, branch on `bpy.app.version` and document both paths. Example:

```python
if bpy.app.version >= (5, 0, 0):
    # 5.x path
    ...
else:
    # 4.5 LTS path
    ...
```

## Standards-version Markers

Files that participate in ecosystem drift checking must carry a `standards-version` marker matching the current meta-repo `VERSION`:

- `AGENTS.md`, `CLAUDE.md`, `ROADMAP.md`: HTML comment first line, e.g. `<!-- standards-version: 1.9.1 -->`.
- `skills/*/SKILL.md`, `rules/*.mdc`: YAML frontmatter field `standards-version: 1.9.1`.

The drift-check workflow enforces these on every push and PR.

## Aggregate Counts

`README.md` declares aggregate counts (e.g. "8 skills, 4 rules, 1 template, and 10 snippets"). The `validate-counts` job in `.github/workflows/validate.yml` enforces these substrings against the filesystem on every push and PR. When you add or remove content, update the README counts in the same commit.

## Pull Request Process

1. **Update docs** if you change skill or rule lists, content counts, or versioning (`README.md`, `CLAUDE.md`, `ROADMAP.md` as appropriate). The release workflow rewrites `CHANGELOG.md`, `CLAUDE.md` `**Version:**` line, and `ROADMAP.md` `**Current:**` line automatically when a `feat:` or `fix:` commit lands on `main`, so only edit those files for content beyond the version markers.
2. **Open a PR** against `main` with a clear title and summary of changes.
3. **Use Conventional Commits** for the PR title (and ideally the merge commit). Prefixes: `feat:` (minor bump), `fix:` (patch bump), `feat!:` or `BREAKING CHANGE` (major bump), `chore:` / `docs:` / `refactor:` (no release).
4. **Respond to review** feedback; CI must pass before merge.

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
