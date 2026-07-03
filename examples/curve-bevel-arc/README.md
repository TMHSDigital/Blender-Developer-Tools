# Curve Bevel Arc

A runnable example that builds a beveled Bezier semicircle entirely through the
curve data API — `splines.new('BEZIER')`, per-point `bezier_points`, and
`bevel_depth` — so the curve renders as a tube without a prior mesh conversion.

**What it witnesses:** renderable curve tubes are curve datablocks, not meshes.
The check asserts eight Bezier points, `bevel_depth == 0.12`, and that the
depsgraph-evaluated mesh has the deterministic topology (850 verts, 840 faces
for these resolution settings) with a Z span that rests on the floor
(`[≈0, 2 × bevel]`).

## Run

```bash
# Cheap correctness check (no render) — the CI check:
blender --background --python curve_bevel_arc.py --

# Also render a still (EEVEE on a GPU host; use --engine cycles on GPU-less hosts):
blender --background --python curve_bevel_arc.py -- --output arc.png
blender --background --python curve_bevel_arc.py -- --output arc.png --engine cycles
```

It exits non-zero on failure (wrong point count, bevel, topology, or Z span).
The `blender-smoke` workflow runs the check on Blender 4.5 LTS and 5.1.
