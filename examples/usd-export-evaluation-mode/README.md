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

The still is numeric-adjacent: left is viewport tessellation (flat-shaded
L1), right is render tessellation (smoothed L2). The USDA point counts are
the evidence; the two balls depict the two qualities the exporter chooses
between.

**What failure each check would catch:**

- exit 3 — VIEWPORT TESSELLATE did not write the L1 closed form
- exit 4 — RENDER TESSELLATE wrote viewport quality or the BEST_MATCH cage
  (`--evaluation-mode VIEWPORT` measured 26/24; `--subdivision BEST_MATCH`
  measured 8/6 `catmullClark`)
- exit 5 — BEST_MATCH stopped writing the cage
- exit 6 — RENDER and VIEWPORT files are identical

The still depicts viewport vs render tessellation of the same SUBSURF cube
(flat-shaded L1 vs smoothed L2). The USDA point counts are the evidence.

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
| 2 | argparse / usage; also base cube verts ≠ 8 |
| 3 | VIEWPORT TESSELLATE point/face count off closed form |
| 4 | RENDER TESSELLATE point/face count or scheme off closed form |
| 5 | BEST_MATCH cage point count or scheme off |
| 6 | RENDER and VIEWPORT USDA point counts are identical |
| 10 | Gallery framing violation |
| 12 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`, `--evaluation-mode`, or `--subdivision`.
