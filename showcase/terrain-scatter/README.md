# Terrain scatter

A showcase piece, not an example. Geometry Nodes sine-hill Mesh Grid
with an Index-jittered Instance-on-Points scatter, realized cubes
replaced by bevelled masonry, then the shipped pipeline: unique-cell
UVs, Cycles high-to-low normal bake, LOD chain, convex collider,
Unity glTF export.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `geometry-nodes-python`, `mesh-editing-and-bmesh`,
`bake-high-to-low`, `depsgraph-and-evaluated-data`,
`engine-export-presets`, and snippets `bake_normal_high_to_low.py`,
`setup_bake_target_image.py`, `lod_chain.py` / `decimate_to_budget.py`,
`convex_hull_collider.py`, `export_preset_unity.py` (helpers copied,
not imported as a package).

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1150–1250 | 1194 / 1194 / 1194 |
| LOD1 ratio | 0.32–0.62 of base | 0.4992 / 0.4992 / 0.4992 |
| LOD2 ratio | 0.10–0.35 of base | 0.2194 / 0.2194 / 0.2194 |
| Materials | exactly 2 distinct, ≥24 stone faces | 2 slots, 486 stone |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.800, 1.800, 0.655) m ± 0.01 | (1.8000, 1.8000, 0.6554), zmin 0 |
| Collider tris | ≤ 80 | 52 |
| Export | written, size > 0 | 90704 / 90704 / 90696 bytes |

DECIMATE COLLAPSE triangle counts are **not** guaranteed identical across
series — the gate is a ratio band, not an exact count. This mesh happened
to match on 4.5.11 / 5.1.2 / 5.2.1. Bake pixels are stochastic; the gate
is `has_data` plus operator `FINISHED`, not byte-identity. Construction
uses no RNG. glTF byte size may differ by a few bytes across series.

`--skip-decimate` skips the LOD DECIMATE stage so LOD1 ratio is 1.0 and
exit 9 fires. That is the named budget the falsifier violates.

## Run

```bash
blender --background --python terrain_scatter.py --
blender --background --python terrain_scatter.py -- --skip-decimate
blender --background --python terrain_scatter.py -- --output terrain.png
```

Smoke does not pass `--output` or `--skip-decimate`.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 2 distinct slots, or stone faces missing |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
