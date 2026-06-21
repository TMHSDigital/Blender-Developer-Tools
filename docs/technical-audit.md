# Blender Developer Tools — Technical Audit & Roadmap

_Audit date: 2026-06-20 · Repo @ v0.5.0 · Auditor: Principal Eng review_

## 0. Important reframing

The audit brief assumed a runnable add-on (operators, UI panels, a socket/file-watcher
execution model). **That is not what this repo is.** This is a **content / knowledge-pack
repository** — an AI "skill pack" of `SKILL.md` workflows, `.mdc` anti-pattern rules, copy-paste
`snippets/`, starter `templates/`, and self-verifying `examples/` consumed by Cursor and Claude
Code. The only executable code is (a) the templates/examples/snippets, which are *teaching
artifacts*, and (b) the CI tooling (`tests/smoke/`, `scripts/build_gallery.py`).

So "core operator logic" and "UI panels" exist only as *demonstration* code in
`templates/extension-addon-template/__init__.py` and the example scripts. The architectural
gaps that matter are about **content correctness, validation coverage, and distribution**, not
runtime robustness of a live tool.

## 1. Architecture map

| Layer | What it is | Notable detail |
| --- | --- | --- |
| `skills/` (12) | Markdown workflows w/ YAML frontmatter | `name` must match dir; `standards-version` gated in CI |
| `rules/` (6) | `.mdc` anti-pattern rules | `alwaysApply` / scope globs for Cursor |
| `snippets/` (17) | Standalone `.py` patterns | `py_compile`-checked only |
| `templates/` (2) | extension add-on + headless batch | real, registerable add-on code |
| `examples/` (4) | self-verifying demo scripts | run inside real Blender in CI, exit non-zero on failure |
| `tests/smoke/` | headless Blender harness | **already exists** — runs on 5.1 + 4.5 matrix |
| `scripts/build_gallery.py` | stdlib HTML generator | builds `docs/gallery/` Pages site |
| `.github/workflows/` | 8 workflows | validate, blender-smoke, drift-check, release, pages, label-sync, stale, dependabot |
| `.cursor-plugin/plugin.json` | distribution manifest | **stale: v0.2.3, missing arrays** |

**Architectural style:** static content pack + automated content-integrity CI. Distribution is
"copy `skills/`+`rules/` into the workspace" or reference the checkout directly. **No MCP server**
(explicitly noted in CLAUDE.md/AGENTS.md).

**Genuine strengths** (the brief assumed these were missing — they are not):
- A real **headless Blender testing harness** already exists. `tests/smoke/run_smoke.py` asserts
  *content*, not just "no exception" (e.g. EEVEE engine-id polarity, slotted-actions boundary,
  driver `id_type` fix, SDF `GridToMesh` link validity, render-non-black). It deliberately
  **copies** content rather than importing it, to catch drift in shipped files.
- `blender-smoke.yml` runs that harness on both the current stable and active LTS, plus runs the
  shipped templates and examples end-to-end (glTF magic-bytes check, exit-code-2 no-mesh path).
- Conventional-commit-driven release automation with doc-sync; count-integrity gate in CI.

## 2. Gap analysis

### G1 — Distribution manifest drift (concrete bug)
`.cursor-plugin/plugin.json` is frozen at `version: 0.2.3`, enumerates only `skills` (12) and
`rules` (6), and has **no `snippets`, `templates`, or `examples` arrays**. Nothing in
`validate.yml` checks the manifest against the filesystem, so it rotted silently while the repo
reached v0.5.0. Consumers reading the manifest see a v0.2.0-era subset.

### G2 — Validation coverage holes
`validate.yml` enforces structure, frontmatter, name=dir, `py_compile`, and README counts. It does
**not**: (a) lint/run snippets beyond byte-compilation (no Blender import, no `ruff`); (b) verify
every snippet/skill/template is referenced from README/ROADMAP/manifest (orphan detection);
(c) check internal/external doc links; (d) validate `gallery.json` against the on-disk examples.
The smoke harness covers a hand-picked subset, so a *new* snippet can ship un-exercised.

### G3 — Smoke harness selectivity (silent coverage cap)
The harness exercises ~6 headline behaviors and 4 examples. 17 snippets + 12 skills are largely
un-run. There is no manifest of "what is covered vs. not," so coverage erosion is invisible — a
classic silent-truncation smell. No per-snippet smoke and no coverage report.

### G4 — No MCP / programmatic surface
The brief's strongest forward-looking point. Today content is human/AI-read-only. There is no
Model Context Protocol server exposing skills/rules/snippets as retrievable resources or tools
(e.g. `get_skill`, `search_patterns`, `lint_blender_py`). This is the natural next-gen evolution
and the cleanest way to make the pack first-class in MCP-aware clients beyond Cursor/Claude Code.

### G5 — Performance/dense-data guidance is pattern-level only
Rules flag `bpy.ops`-in-loops and per-element loops, and snippets show `foreach_set/get`. But
there is no skill on **profiling / scaling to dense meshes** (e.g. numpy buffer interop,
`foreach_get` into preallocated numpy arrays, attribute-domain bulk ops, depsgraph cost). For a
tool whose whole pitch is "do bulk work the fast way," this is a content gap.

### G6 — LTS/version sweep is manual and unpinned
5.2 LTS lands ~mid-2026. The smoke matrix hard-codes `5.1`/`4.5`. There is no scheduled job to
detect a new stable/LTS series and open a sweep issue, so the "5.2 sweep" depends on a human
remembering.

## 3. Roadmap

### Stage 1 — Short-term / Quick Wins (days)
- **Fix + gate the Cursor manifest** (G1). Regenerate `plugin.json` from the filesystem and add a
  CI check so it can't drift again.
- **Orphan + link audit job** (G2). Fail CI if any snippet/skill/template/example is unreferenced
  by README/ROADMAP/manifest, or if a markdown link 404s.
- **`gallery.json` ↔ disk validator** (G2). Assert every example dir + hero image referenced
  exists and vice-versa.
- **Coverage manifest for smoke** (G3). Emit a printed "covered / not covered" table so gaps are
  visible in the CI log.

### Stage 2 — Mid-term / Core Enhancements (weeks)
- **Per-snippet smoke harness** (G3): a generic runner that imports/execs each snippet in headless
  Blender behind a small `# smoke: skip` opt-out, closing the un-run-content gap.
- **`ruff` + import-time lint** of all Python content with a Blender-aware config.
- **New skill: `performance-and-dense-data`** (G5) — numpy `foreach_get`/`foreach_set` buffers,
  attribute domains, when bmesh beats data API, profiling with `time`/`cProfile` headless.
- **New skills from the committed pool**: `modal-operators`, `mathutils-patterns`, `usd-pipelines`.
- **Automated LTS-series watcher** (G6): scheduled job that diffs `download.blender.org` series
  against the matrix and opens a sweep issue.

### Stage 3 — Long-term / Next-Gen Capabilities (quarters)
- **MCP server** (G4) exposing the pack as MCP resources + tools: `list_skills`, `get_skill`,
  `search_patterns`, and a `lint_blender_python` tool wrapping the `.mdc` rules as executable
  checks. Ships as an optional adjacent package so the content repo stays a pure pack.
- **Rules-as-linter**: compile the 6 `.mdc` anti-patterns into an actual AST linter
  (`libcst`/`ast`) that runs in CI and is reusable by the MCP `lint` tool and by consumers.
- **5.2 LTS parity sweep** once released; bump templates' `blender_version_min` where 5.2 APIs are
  used.
- **Fleet Pages examples support** (already in ROADMAP) — lift `gallery.json` into the shared
  template, retire the local generator.

---

## 4. GitHub Issues (copy-paste ready)

### Issue 1 — Fix and CI-gate the stale `.cursor-plugin/plugin.json` manifest

**Labels:** `bug`, `ci`, `distribution`

**Context / Problem Statement**
`.cursor-plugin/plugin.json` is pinned at `"version": "0.2.3"` while the repo is at v0.5.0
(`VERSION`). It lists only the `skills` (12) and `rules` (6) arrays and omits `snippets`,
`templates`, and `examples` entirely. No job in `.github/workflows/validate.yml` checks the
manifest against the filesystem, so it has drifted silently. Consumers that read the manifest see a
v0.2.0-era view of the pack.

**Proposed Solution / Implementation Steps**
1. Decide the manifest schema for `snippets`/`templates`/`examples` (mirror the existing
   relative-path-array style used for `skills`/`rules`). If the upstream `cursor-plugin` schema
   only supports skills+rules, document that and instead just fix `version` + add the gate.
2. Update `.cursor-plugin/plugin.json`: bump `version` to match `VERSION`, and add the missing
   arrays enumerating files under `snippets/`, `templates/`, `examples/`.
3. Add a `validate-manifest` job to `validate.yml` (a `python3` heredoc like the existing
   `validate-counts` job) that:
   - loads `plugin.json`,
   - asserts every path in each array exists on disk,
   - asserts every `skills/*/SKILL.md` and `rules/*.mdc` on disk is present in the manifest,
   - asserts `plugin.json` `version` equals `VERSION` (or is intentionally decoupled — pick one and
     enforce it).
4. If `version` should track releases, add it to the `release-doc-sync` owned-lines list so the
   release pipeline rewrites it; otherwise document why it is independent in `AGENTS.md`.

**Definition of Done**
- [ ] `plugin.json` enumerates all current skills, rules, snippets, templates, examples.
- [ ] `plugin.json` `version` reconciled with `VERSION` (synced or documented as independent).
- [ ] New CI job fails on any manifest↔filesystem mismatch (proven by a deliberately broken commit).
- [ ] `AGENTS.md` "CI/CD workflows" section documents the new job.

---

### Issue 2 — Add orphan-content and dead-link validation to CI

**Labels:** `ci`, `content-integrity`

**Context / Problem Statement**
`validate.yml` checks structure, frontmatter, name=dir, `py_compile`, and README aggregate counts,
but nothing detects a snippet/skill/template/example that ships **without being referenced** by
`README.md`, `ROADMAP.md`, or the manifest, nor does anything catch broken markdown links. New
content can land orphaned (discoverable only by directory listing), and doc links can rot.

**Proposed Solution / Implementation Steps**
1. Add an `orphan-check` job to `validate.yml`: enumerate files under `snippets/`, `skills/`,
   `templates/`, `examples/`; for each, grep `README.md` + `ROADMAP.md` for its name; fail listing
   any unreferenced item.
2. Add a lightweight link check: collect markdown links from `*.md`, validate that relative targets
   exist on disk; optionally check external `https://` links with a `--allow-fail` soft mode to
   avoid flakiness (or gate external checks behind the weekly `schedule`, not PRs).
3. Keep it stdlib-only (consistent with `build_gallery.py`) so no new CI deps are needed.

**Definition of Done**
- [ ] CI fails when a snippet/skill/template/example is unreferenced in README/ROADMAP.
- [ ] CI fails on a broken **relative** markdown link.
- [ ] External link checks run on the weekly schedule, not on every PR (no PR flakiness).
- [ ] A deliberately orphaned test file proves the gate fires, then is removed.

---

### Issue 3 — Generalize the smoke harness to per-snippet coverage + emit a coverage table

**Labels:** `testing`, `enhancement`

**Context / Problem Statement**
`tests/smoke/run_smoke.py` is excellent but exercises only ~6 hand-picked headline behaviors and
`blender-smoke.yml` runs 4 examples. The 17 snippets and 12 skills are largely **un-run** in real
Blender, and there is no record of what is covered. A new snippet can ship having only passed
`py_compile`, and coverage can erode invisibly (silent-truncation risk).

**Proposed Solution / Implementation Steps**
1. Add `tests/smoke/run_snippets.py`: iterate `snippets/*.py`, `exec` each inside a `reset()`
   factory-empty scene in headless Blender, treating any raised exception as failure (mirror the
   try/except wrapper already in `run_smoke.py`).
2. Support a `# smoke: skip <reason>` first-line pragma for snippets that need scene state they
   can't self-provide; **print the skipped list** so skips are visible, never silent.
3. Emit a coverage table at the end: `N snippets run, M skipped (reasons), K skills with a smoke
   check`. Print it to the CI log.
4. Wire a new step into `blender-smoke.yml` after the existing smoke driver, on the same 5.1/4.5
   matrix, `xvfb-run`-wrapped.

**Definition of Done**
- [ ] Every snippet is either executed in headless Blender or explicitly `# smoke: skip`-ged with a
      reason.
- [ ] CI log prints a run/skip/coverage summary table.
- [ ] A snippet that raises in Blender fails the job (proven once).
- [ ] Runs green on both 5.1 and 4.5 matrix legs.

---

### Issue 4 — New skill: `performance-and-dense-data` (numpy buffer interop + profiling)

**Labels:** `content`, `skill`

**Context / Problem Statement**
The pack's core thesis is "do bulk Blender work the fast way," and rules
(`prefer-data-over-ops-in-loops`, `use-foreach-set-for-bulk-data`) plus the `foreach-*` snippets
point that direction. But there is **no skill** that teaches scaling to dense meshes: numpy
buffer interop with `foreach_get`/`foreach_set`, attribute-domain bulk operations, the
bmesh-vs-data-API decision under load, and how to profile headless. AI agents currently get the
"don't do it slow" rules without a positive "here is the fast, measured pattern" skill.

**Proposed Solution / Implementation Steps**
1. Create `skills/performance-and-dense-data/SKILL.md` with the standard YAML frontmatter
   (`name: performance-and-dense-data`, one-line `description`, `standards-version: 1.10.0`).
2. Cover: preallocated `numpy` arrays with `foreach_get`/`foreach_set` (`np.empty(n*3)`), reshaping
   conventions, attribute API bulk read/write across domains, when bmesh wins, and a headless
   `cProfile`/`time.perf_counter` measurement pattern. Show 5.1 and 4.5 paths where they diverge.
3. Add 1–2 supporting snippets (e.g. `numpy-foreach-vertices.py`) and a self-verifying assertion in
   the smoke harness (roundtrip equality + a coarse timing sanity check).
4. Update `README.md` aggregate counts, `ROADMAP.md` candidate pool, `AGENTS.md`, and
   `plugin.json`; commit with `feat:`.

**Definition of Done**
- [ ] New skill passes frontmatter + name=dir CI checks.
- [ ] Shows numpy buffer interop and at least one profiling pattern, with 4.5/5.1 branches where
      relevant.
- [ ] Supporting snippet(s) added and smoke-exercised.
- [ ] README counts, ROADMAP, AGENTS, and manifest updated (counts gate green).

---

### Issue 5 — Prototype an MCP server exposing the pack as resources + a Blender-Python lint tool

**Labels:** `enhancement`, `mcp`, `next-gen`

**Context / Problem Statement**
CLAUDE.md and AGENTS.md both note "there is no MCP server." Today the content is consumable only by
clients that natively read `skills/`+`rules/` (Cursor, Claude Code). An MCP server would make the
pack first-class in any MCP-aware client and turn the 6 `.mdc` anti-pattern rules into an
executable lint tool — a far stronger guarantee than prose rules.

**Proposed Solution / Implementation Steps**
1. Add an **optional adjacent** package (e.g. `mcp-server/`) so the content repo stays a pure pack;
   the server reads `skills/`, `rules/`, `snippets/` from the repo at runtime.
2. Expose MCP **resources**: `list_skills`, `get_skill(name)`, `list_snippets`, `get_snippet(name)`,
   `search_patterns(query)`.
3. Expose an MCP **tool** `lint_blender_python(source)` implementing the rules as AST checks:
   `bpy.ops.*` inside loops, `bmesh.new()` without paired `free()`, prop assignment vs annotation,
   `bpy.context.copy()` override, per-element bulk loops. Reuse this checker in CI (see the
   rules-as-linter long-term item).
4. Document install/usage in a `mcp-server/README.md`; keep it out of the count/validate gates
   (it's tooling, not pack content) but add its own minimal test job.

**Definition of Done**
- [ ] MCP server lists and serves skills/rules/snippets as resources.
- [ ] `lint_blender_python` flags all 6 anti-patterns on a fixture file and passes clean code.
- [ ] Server runs against the live repo checkout with documented setup.
- [ ] CI runs the server's own tests without touching the content-count gates.
