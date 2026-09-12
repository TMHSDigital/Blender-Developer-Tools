## Summary

<!-- One or two sentences on why, not what. -->

## Type

- [ ] `feat` — new skill / rule / snippet / template / example (minor bump)
- [ ] `fix` — correction to existing content or a broken contract (patch bump)
- [ ] `docs` / `chore` / `ci` / `refactor` — no release; `release.yml` still runs and should exit without a tag

Squash-merge subject is what the release workflow scans. Keep it conventional.

## Evidence

Label every claim.

- **live-run-proven:** exact binary path + the version that binary printed (`blender --version`). Headless harness only. Live MCP does not count.
- **inspection-only:** read the skill / diff / RNA docs; no process ran.

`blender-smoke.yml` has no `push` trigger. Post-merge smoke evidence is the PR-head 5.2 + 4.5 jobs (state the versions from those logs). Apply `needs-5.1` when 5.1 must be CI-proven on the PR; default matrix does not include it.

## Release-owned fields — do not hand-edit

`VERSION`, `CHANGELOG.md`, CLAUDE.md `**Version:**`, ROADMAP.md `**Current:**`, `.cursor-plugin/plugin.json` `"version"`. The release pipeline rewrites those. Do not bump `standards-version` unless the fleet stamp actually moved.

## Checklist

- [ ] Explicit paths only (`git add` never `-A` / `.`). Leave unstaged Cursor-injected `CLAUDE.md` hunks.
- [ ] Counts in `README.md` match disk if content was added or removed (`validate-counts`).
- [ ] Manifest arrays list every new skill / rule / snippet / template / example (`validate-manifest`). Do not touch the `"version"` line.
- [ ] New example: `gallery.json`, smoke step, README row, hero/preview webp, `python scripts/build_gallery.py`, framing / contact-sheet gates as in `CLAUDE.md`.
- [ ] Every new check was falsified once (break it, non-zero exit, restore) — or this PR has no new check.
- [ ] DCO `Signed-off-by:` on every commit ([CONTRIBUTING.md](CONTRIBUTING.md)).
- [ ] No credentials, business emails, or local filesystem paths.

## Test plan

<!-- What you ran, on which Blender binary, exit codes. -->

## Linked issues

<!-- Closes #123 -->
