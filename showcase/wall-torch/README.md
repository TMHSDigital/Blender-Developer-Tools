# Wall torch

A showcase piece, not an example. Procedural wall-mounted torch sconce
(running-bond dressed stone plaque, iron plate and arm from named
stations, bowl cup, wooden haft, emissive flame) then the shipped
pipeline: unique-cell UVs, Cycles high-to-low normal bake, LOD chain,
convex collider, Unity glTF export.

The plaque back sits on the wall plane Y=0 with zmin at 0. The iron
arm is a tube from the plate station to the cup wall, not a pair of
square bars aimed at a funnel. The bowl opens upward and holds the
haft. Hygiene family 15–19: `--stray-vert`, `--lift-z`, `--float-arm`,
`--float-plate`, `--skinny-plaque`.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`,
`procedural-materials-and-shaders`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: 0.28 m plaque width, 0.40 m plaque height, bowl
projecting 0.24 m from the wall; outer AABB 0.304 × 0.293 × 0.424 m.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1400–1700 | 1528 / 1528 / 1528 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2199 / 0.2199 / 0.2199 |
| Materials | exactly 4 distinct, ≥24 stone, ≥24 metal, ≥8 flame | 4 slots, 540 stone, 228 metal, 78 flame |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.304, 0.293, 0.424) m ± 0.015 | (0.3040, 0.2930, 0.4240), zmin 0 |
| Collider tris | ≤ 180 | 60 |
| Export | written, size > 0 | 124608 / 124608 / 124584 bytes |

Base triangles rose from **848 to 1528** in the quality pass: one
mailbox slab became four courses of running-bond ashlar plus a round
arm and a triangulated bowl. Outer AABB tightened from 0.384 × 0.360 ×
0.670 m (and zmin 0.140) to 0.304 × 0.293 × 0.424 m at zmin 0.

DECIMATE COLLAPSE triangle counts are **not** identical across series.
The gate is a ratio band, not an exact count. Bake pixels are
stochastic; the gate is `has_data` plus operator `FINISHED`, not
byte-identity. Construction uses no RNG. Export byte counts differ by
24 B on 5.2.1 (glTF serializer), not a gated axis.

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

### Joint fit and plaque size

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Arm-to-cup BVH gap | ≤ 0.008 m | 0.00087 |
| Plate-to-plaque BVH gap | ≤ 0.008 m | 0.00400 |
| Plaque width vs `WALL_W` | ± 0.04 m | 0.2800 vs 0.280 |

### Falsifiers

Each violates one named budget. All were run on 4.5.11, 5.1.2 and 5.2.1
and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--float-arm` | arm-to-cup BVH gap | 17 |
| `--float-plate` | plate-to-plaque BVH gap | 18 |
| `--skinny-plaque` | plaque width vs `WALL_W` | 19 |

`--float-arm` shortens the tube to 55 % of the plate-to-cup station
vector; the cup stays put. `--float-plate` moves only the hang plate
off the plaque; the arm still reaches the cup so 17 still passes.
`--skinny-plaque` scales the back plaque and courses to 0.55 · `WALL_W`.

## Run

```bash
blender --background --python wall_torch.py --
blender --background --python wall_torch.py -- --skip-decimate
blender --background --python wall_torch.py -- --stray-vert
blender --background --python wall_torch.py -- --lift-z
blender --background --python wall_torch.py -- --float-arm
blender --background --python wall_torch.py -- --float-plate
blender --background --python wall_torch.py -- --skinny-plaque
blender --background --python wall_torch.py -- --output torch.png
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
| 5 | Material count ≠ 4 distinct slots, or stone/metal/flame faces missing |
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
| 17 | Arm-to-cup gap (`--float-arm`) |
| 18 | Plate-to-plaque gap (`--float-plate`) |
| 19 | Plaque width (`--skinny-plaque`) |
