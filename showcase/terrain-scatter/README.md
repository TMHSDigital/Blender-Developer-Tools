# Terrain scatter

A showcase piece, not an example. Geometry Nodes sine-hill Mesh Grid
with an Index-jittered Instance-on-Points scatter, realized cubes
replaced by closed-form displaced icospheres seated on sampled dirt Z,
then the shipped pipeline: unique-cell UVs, Cycles high-to-low normal
bake, LOD chain, convex collider, Unity glTF export.

GN still builds the hill and the instance grid. After realize+slabify,
cube islands are deleted and each centroid is reseated: stone `zmin`
equals sampled dirt Z minus a named bite, then verts clamp above the
slab floor. That is why rocks sit on the hill instead of punching
through the slab as bevelled crates.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `geometry-nodes-python`, `mesh-editing-and-bmesh`,
`bake-high-to-low`, `depsgraph-and-evaluated-data`,
`engine-export-presets`, and snippets `bake_normal_high_to_low.py`,
`setup_bake_target_image.py`, `lod_chain.py` / `decimate_to_budget.py`,
`convex_hull_collider.py`, `export_preset_unity.py` (helpers copied, not
imported as a package). Hygiene combinatorics match
`examples/mesh-hygiene-audit` (copied, not imported).

Intended size: 1.80 m square hill tile, ~0.16 m sine amplitude, nine
seated stones; outer AABB 1.800 × 1.800 × 0.552 m.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1400–2800 | 1758 / 1758 / 1758 |
| LOD1 ratio | 0.32–0.62 of base | 0.4994 / 0.4994 / 0.4994 |
| LOD2 ratio | 0.10–0.35 of base | 0.2196 / 0.2196 / 0.2196 |
| Materials | exactly 2 distinct, ≥24 stone faces | 2 slots, 720 stone |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.800, 1.800, 0.552) m ± 0.015 | (1.8000, 1.8000, 0.5523), zmin 0 |
| Collider tris | ≤ 120 | 81 |
| Export | written, size > 0 | 158156 / 158156 / 158140 bytes |

Base triangles rose from **1194 to 1758** in the quality pass: 9-vert hill
became a 21-vert grid, and bevelled cubes became subdiv-2 icospheres.
Outer Z dropped from 0.655 m (crate corners swinging through the slab)
to 0.552 m of seated stone on the hill.

DECIMATE COLLAPSE triangle counts are **not** guaranteed identical across
series — the gate is a ratio band, not an exact count. This mesh matched
on 4.5.11 / 5.1.2 / 5.2.1. Bake pixels are stochastic; the gate is
`has_data` plus operator `FINISHED`, not byte-identity. Construction uses
no RNG. Export byte counts differ by 16 B on 5.2.1 (glTF serializer), not
a gated axis.

### Hygiene

Recomputed from the generated mesh, not asserted about the script.

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Non-manifold edges | 0 | 0 |
| Loose verts / edges | 0 / 0 | 0 / 0 |
| Doubles merged at 1e-5 | 0 | 0 |
| Zero-area faces | 0 | 0 |
| N-gons | 0 | 0 |
| Coplanar disjoint face pairs | 0 | 0 |
| Grounded: `zmin` | within 1e-4 of 0 | 0.0000 |
| Stone shells | 9 | 9 |
| Per-stone faces | ≥ 40 | 80 |
| Stone floor `zmin` | ≥ 0.012 m | 0.11334 |
| Seat offset (`zmin` − dirt Z) | ≤ 0.02 m | −0.03500 |

### Falsifiers

Each violates one named budget. All were run on 4.5.11, 5.1.2 and 5.2.1
and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--poke-rock` | stone floor `zmin` | 17 |
| `--float-rocks` | seat offset vs sampled dirt Z | 18 |
| `--box-rocks` | per-stone face floor | 19 |

## Run

```bash
blender --background --python terrain_scatter.py --
blender --background --python terrain_scatter.py -- --skip-decimate
blender --background --python terrain_scatter.py -- --stray-vert
blender --background --python terrain_scatter.py -- --lift-z
blender --background --python terrain_scatter.py -- --poke-rock
blender --background --python terrain_scatter.py -- --float-rocks
blender --background --python terrain_scatter.py -- --box-rocks
blender --background --python terrain_scatter.py -- --output terrain.png
```

Smoke passes no flags.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family.

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
| 15 | Hygiene (`--stray-vert` lands here) |
| 16 | Grounded zmin (`--lift-z`) |
| 17 | Stone floor poke (`--poke-rock`) |
| 18 | Float above host (`--float-rocks`) |
| 19 | Stone shell faces (`--box-rocks`) |
