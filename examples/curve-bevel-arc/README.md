# Curve Bevel Arc

A runnable example that builds a beveled Bezier semicircle entirely through the
curve data API — `splines.new('BEZIER')`, per-point `bezier_points`,
`bevel_depth`, and `use_fill_caps` — so the curve renders as a solid tube without
a prior mesh conversion.

**What it witnesses:** renderable curve tubes are curve datablocks, not meshes.
The check asserts eight Bezier points, `bevel_depth == 0.15`, `use_fill_caps`,
and that the depsgraph-evaluated mesh has the deterministic topology (1044 verts,
1028 faces for these resolution settings) with a Z span that rests on the floor
(`[0, 2 × bevel]`) and an X span of `2 × radius + 2 × bevel`.

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python curve_bevel_arc.py --

# Falsifier: uncapped tube. Must exit non-zero (use_fill_caps).
blender --background --python curve_bevel_arc.py -- --no-caps

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python curve_bevel_arc.py -- --output arc.png
blender --background --python curve_bevel_arc.py -- --output arc.png --engine cycles
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is also the shared framing helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Spline type is not BEZIER |
| 4 | Bezier point count ≠ 8 |
| 5 | `bevel_depth` ≠ 0.15 |
| 6 | `use_fill_caps` is False (`--no-caps` lands here) |
| 7 | Evaluated vert/face count off measured tessellation |
| 8 | Tube does not rest on the floor |
| 9 | Tube height ≠ 2 × bevel |
| 10 | X span off closed form; also gallery framing violation |
| 11 | `--output` produced no file |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output` or `--no-caps`.
