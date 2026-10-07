# USD export evaluation_mode

A SUBSURF cube exported through `wm.usd_export` that witnesses
`evaluation_mode='RENDER'` against `'VIEWPORT'` — the contract
[`usd-export-evaluation-mode.py`](../../snippets/usd-export-evaluation-mode.py)
names but does not prove.

Catmull-Clark on a cube is closed form: verts = `2 + 6 × 4^n` (n=1 → 26,
n=2 → 98). TESSELLATE + VIEWPORT writes 26 points / 24 quads; TESSELLATE +
RENDER writes 98 / 96. Default `export_subdivision='BEST_MATCH'` writes the
8-vert cage plus `subdivisionScheme = catmullClark`, so evaluation_mode is
silent — both files are the cage. TESSELLATE is what makes the mode
observable.

The still shows the exported files themselves. The `--output` path builds a
turned goblet on an 8-sided lathe cage with SUBSURF `levels=0` /
`render_levels=3`, exports it twice through the same `wm.usd_export` call
the check proves (TESSELLATE + VIEWPORT, TESSELLATE + RENDER), re-imports
both USDA files with `wm.usd_import`, and stages the two imported meshes.
Left is the VIEWPORT file (the raw 8-sided cage, 130 points), right the
RENDER file (8450 points). Both are flat-shaded with the same material, so
geometry is the only difference, and the point count on each placard is
read from the re-imported mesh at render time. The goblet widens the
cube's L1/L2 split to L0/L3 so the difference reads at thumbnail size. The
render path also asserts that the re-imported RENDER goblet is denser than
the VIEWPORT one (exit 6). Placards use the bundled DejaVu Sans Mono, whose
`1` cannot be misread as `I`.

**What failure each check would catch:**

- exit 3 — VIEWPORT TESSELLATE did not write the L1 closed form
- exit 4 — RENDER TESSELLATE wrote viewport quality or the BEST_MATCH cage
  (`--evaluation-mode VIEWPORT` measured 26/24; `--subdivision BEST_MATCH`
  measured 8/6 `catmullClark`)
- exit 5 — BEST_MATCH stopped writing the cage
- exit 6 — RENDER and VIEWPORT files are identical

Staging: Catmull-Clark pulls the surface inside the cage, and each level
shrinks it by a different amount, so each re-imported goblet is seated on
its plinth from its own vertices rather than from the cage's z.

Probed on the CI Linux portables **Blender 5.2.1 LTS** (`9e2066aef7ef`) and
**Blender 4.5.13 LTS** (`daeeeca98fb0`): `wm.usd_export` exists, `poll()` is
true in `--background`, `evaluation_mode` is `{RENDER, VIEWPORT}`. The
`--output` render path measures framing via `examples/gallery_framing.py`
(exit 10 on violation).

## Run

```bash
blender --background --python usd_export_evaluation_mode.py --
blender --background --python usd_export_evaluation_mode.py -- --output u.png
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | VIEWPORT TESSELLATE point/face count off closed form |
| 4 | RENDER TESSELLATE point/face count or scheme off closed form |
| 5 | BEST_MATCH cage point count or scheme off |
| 6 | RENDER and VIEWPORT USDA point counts are identical (check), or the re-imported RENDER goblet is not denser than the VIEWPORT one (`--output`) |
| 7 | Base cube verts ≠ 8 (checked first) |
| 10 | Gallery framing violation |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`. Its catalog falsifiers are `--subdivision BEST_MATCH` (expects exit 4) and `--evaluation-mode VIEWPORT` (expects exit 4).
