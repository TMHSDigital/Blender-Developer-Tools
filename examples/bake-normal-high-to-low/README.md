# Bake Normal High to Low

A runnable example that cage-bakes a ribbed bronze hatch plate onto a
`DECIMATE COLLAPSE` LOD and asserts the tangent-space normal map carries
measurable surface detail — following
[`bake-high-to-low`](../../skills/bake-high-to-low/SKILL.md).

**What it witnesses:** Cycles selected-to-active normal bake is a statistical
process, not a byte-identical one. A high-poly source produces a map that
deviates from flat tangent `(0.5, 0.5, 1.0)`; the same bake from an
undisplaced source does not.

Byte-identity across 4.5 / 5.1 / 5.2 is **not** the contract. Tile order and
float accumulation differ even at one CPU sample. The gates are fraction of
pixels beyond Euclidean `0.04` from flat, mean absolute deviation, and a
monotonic gap versus a flat control. Tolerances sit well inside the measured
gap (detail frac 0.7211 vs flat 0.0000) so they are not
tuned-until-green.

- **Detail bake is not flat.** `frac >= 0.40` and `MAD >= 0.05` (measured
  0.7211 / 0.09356 on 4.5.11, 5.1.2, and 5.2.1). Catches an inactive Image
  Texture node, reversed selection, or EEVEE/GPU mis-setup that writes a
  blank map. MAD floor is half the measured hatch value, still ~30× a
  flat bake.
- **Flat control is flat.** `frac <= 0.05` and `MAD <= 0.03` (measured
  0.0000 / 0.00277). Catches a noisy or wrongly-typed bake that would also
  satisfy the detail gates.
- **Monotonic gap.** `detail_frac - flat_frac >= 0.30`. The two maps must
  separate; a tolerance wide enough to pass both would have no discriminating
  power.
- **`--flat-source` is the falsifier.** Skips the ribs and still runs the
  detail gates. Must exit 5. Analogous to `--same-axis` in
  [`export-preset-axis`](../export-preset-axis/).

Neighbor of [`lod-decimate-chain`](../lod-decimate-chain/) (the LOD is the
cage target; collapse keeps UVs) and [`image-pixels-testcard`](../image-pixels-testcard/)
(`save_render`, not `Image.save()`, if you persist the datablock). UV transfer
and atlas packing are out of scope.

The still stages the baked map as an unlit card beside the LOD wearing it.
If the bake were flat, the card would be uniform `(128, 128, 255)` periwinkle
and the plate would shade like the undisplaced cage.

Operator RNA (`type='NORMAL'`, `use_selected_to_active`, `cage_extrusion`,
`cage_object` as a string, `normal_space='TANGENT'`, `margin_type`) is
identical on 4.5.11, 5.1.2, and 5.2.1 — no shim.

## Run

```bash
# Cheap correctness check (no render) - the CI check:
blender --background --python bake_normal_high_to_low.py --

# Falsifier: undisplaced high. Must exit non-zero (detail frac gate).
blender --background --python bake_normal_high_to_low.py -- --flat-source

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python bake_normal_high_to_low.py -- --output hatch.png
blender --background --python bake_normal_high_to_low.py -- --output hatch.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Missing UV layer on the target |
| 4 | Bake did not `FINISHED` or image `has_data` is false |
| 5 | Detail deviant-pixel fraction below 0.40 (`--flat-source` lands here) |
| 6 | Detail MAD below 0.05 |
| 7 | Flat control above 0.05 frac / 0.03 MAD |
| 8 | Monotonic gap below 0.30 |
| 9 | `--output` produced no file |
| 10 | Gallery framing violation |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`.
