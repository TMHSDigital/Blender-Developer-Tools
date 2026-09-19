# Fence kit

A showcase piece, not an example. Procedural post-and-rail fence
section (two posts, pyramidal caps, three rails, kickboard, a brace
from named post stations, iron shoes and U-wrap straps) then the
shipped pipeline: unique-cell UVs, Cycles high-to-low normal bake, LOD
chain, convex collider, Unity glTF export.

Posts, rails, kick, brace and collars share named stations
(`POST_XS`, `RAIL_ZS`, `Y_BRACE`, `SHOE_H`). The brace is an oriented
box from the left-post lower-rail station to the right-post upper-rail
station on the back face, not a hypot-length box rotated about its
centroid. Rails and kick tenon into the post volume; rail collars are
U-wraps so the span-facing plate is not coplanar with the rail end.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.
AABB X is the tile width so adjacent copies meet; this piece does not
re-witness the `modular-kit-snap` snap contract.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: 1.60 m bay, 1.14 m posts, 0.11 m post stock; outer AABB
1.624 × 0.134 × 1.232 m.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1000–1400 | 1092 / 1092 / 1092 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2198 / 0.2198 / 0.1832 |
| Materials | exactly 2 distinct, ≥48 metal, ≥24 wood | 2 slots, 156 metal / 390 wood |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.624, 0.134, 1.232) m ± 0.015 | (1.6240, 0.1340, 1.2320), zmin 0 |
| Collider tris | ≤ 180 | 32 |
| Export | written, size > 0 | 82216 / 82216 / 82208 bytes |

Base triangles dropped from **1212 to 1092** in the quality pass: rail
collars became U-wraps (no span-facing plate). Outer AABB tightened from
1.642 × 0.157 × 1.235 m.

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is more aggressive on LOD2. The gate is a ratio band, not an
exact count. Bake pixels are stochastic; the gate is `has_data` plus
operator `FINISHED`, not byte-identity. Construction uses no RNG.
Export byte counts differ by 8 B on 5.2.1 (glTF serializer), not a
gated axis.

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
| Named shoes | 2, each `zmin` ≤ 0.002 | 2, 0.00000 |

### Joint fit and span

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Brace-to-post BVH gap (both posts) | ≤ 0.008 m | 0.00240 |
| Rail-to-post BVH gap | ≤ 0.008 m | 0.00093 |
| Rail span vs `2·RAIL_HALF` | ± 0.04 m | 1.3900 vs 1.390 |

### Falsifiers

Each violates one named budget. All were run on 4.5.11, 5.1.2 and 5.2.1
and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-shoes` | named shoes plant at z=0 | 16 |
| `--short-brace` | brace-to-post BVH gap (both posts) | 17 |
| `--gap-rails` | rail-to-post BVH gap | 18 |
| `--long-rails` | rail span vs `2·RAIL_HALF` | 19 |

`--short-shoes` lifts only the iron shoes. After recenter a post or kick
is the AABB `zmin`, so the AABB gate would still pass; the named-shoe
stations fail. `--short-brace` shortens the left station; `brace_gap` is
the max of the per-post minima so a brace that still hits the right post
cannot sneak through. `--long-rails` adds an extra spanning board; the
tenoned rails stay put so the gap budget still passes.

## Run

```bash
blender --background --python fence_kit.py --
blender --background --python fence_kit.py -- --skip-decimate
blender --background --python fence_kit.py -- --stray-vert
blender --background --python fence_kit.py -- --lift-z
blender --background --python fence_kit.py -- --short-shoes
blender --background --python fence_kit.py -- --short-brace
blender --background --python fence_kit.py -- --gap-rails
blender --background --python fence_kit.py -- --long-rails
blender --background --python fence_kit.py -- --output fence.png
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
| 5 | Material count ≠ 2 distinct slots, or wood/metal faces missing |
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
| 16 | Grounded zmin / named shoes (`--lift-z`, `--short-shoes`) |
| 17 | Brace-to-post gap (`--short-brace`) |
| 18 | Rail-to-post gap (`--gap-rails`) |
| 19 | Rail span (`--long-rails`) |
