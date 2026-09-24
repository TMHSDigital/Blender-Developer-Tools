# Fence kit

A showcase piece, not an example. A procedural post-and-rail fence section
(two posts, pyramidal caps, three rails, a kickboard, a board brace, iron
shoes and U-bands), then the shipped pipeline: unique-cell UVs, a Cycles
high-to-low normal bake, an LOD chain, a convex collider and a Unity glTF
export.

Posts, rails, kick, brace and bands share named stations (`POST_XS`,
`RAIL_ZS`, `SHOE_H`). The post stations come from the tile. The outer faces
of the iron bands sit `KIT_CLEAR` (2 mm) inside the tile edge, so copies
placed at the 1.60 m pitch meet band to band without interpenetrating or
sharing a plane. Each band is one shell, mitred at the corners. A rail band
is a U open toward the span, with its arms stopped inside the post's inner
face. The brace is a board with plumb-cut ends, face-nailed to the middle
rail and housed 12 mm into both posts. It clears the bottom rail at the left
post and the top rail at the right one. Rails and kick tenon into the post
volume.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check. This
piece does not re-witness the `modular-kit-snap` snap contract.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: 1.60 m tile, 1.14 m posts, 0.11 m post stock. Outer AABB
1.596 × 0.134 × 1.232 m.

## Budgets

Declared as named constants. Every gate **recomputes** its value from the
mesh, materials, UVs, evaluated LOD, collider or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 850–1200 | 1012 / 1012 / 1012 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2194 / 0.2194 / 0.2174 |
| Materials | exactly 2 distinct, ≥48 metal, ≥48 wood | 2 slots, 116 metal / 390 wood |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.596, 0.134, 1.232) m ± 0.015 | (1.5960, 0.1340, 1.2320), zmin 0 |
| Collider tris | ≤ 180 | 24 |
| Export | written, size > 0 | 75900 / 75900 / 75888 bytes |

Base triangles dropped from **1092 to 1012** in the second quality pass. Each
band became one mitred shell instead of three or four separate plates, and
the brace became a six-face board. The band was re-fitted around the
measurement and narrowed from 1000–1400.

DECIMATE COLLAPSE triangle counts are **not** identical across series:
5.2.1 is more aggressive on LOD2. The gate is a ratio band, not an exact
count. Bake pixels are stochastic; the gate is `has_data` plus operator
`FINISHED`, not byte-identity. Construction is closed-form and plank tones
are seeded, so repeated runs on one binary print identical measurements.
Export byte counts differ by 12 B on 5.2.1 (glTF serializer), not a gated
axis.

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

### Joint fit, bearing and tiling

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Brace-to-post BVH gap (both posts) | ≤ 0.008 m | 0.00531 |
| Rail-to-post BVH gap | ≤ 0.008 m | 0.00093 |
| Rail span vs `2·RAIL_HALF` | ± 0.04 m | 1.3620 vs 1.362 |
| Brace housing (exit 20): deepest brace vertex inside each post | ≥ 0.004 m | 0.01200 |
| Brace bearing (exit 20): brace back plane past the middle rail's front plane, where their heights overlap | ≥ 0.001 m | 0.00200 |
| Tile fit (exit 21): section width along the tiling axis | 1.590–1.600 m | 1.5960 |

The brace bearing is measured plane to plane. The brace and the middle rail
cross mid-span, and neither has a vertex there, so a vertex-depth metric
reports a false gap of 0.15 m.

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
| `--float-brace` | brace bearing on the middle rail (brace 6 mm forward; measured −0.00400) | 20 |
| `--wide-tile` | tile fit (the first build's post stations; measured 1.6240) | 21 |

`--short-shoes` lifts only the iron shoes. After recentring, a post or the
kick is the AABB `zmin`, so the AABB gate would still pass. The named-shoe
stations fail. `--short-brace` shortens the left end; `brace_gap` is the
maximum of the per-post minima, so a brace that still reaches the right post
cannot sneak through. `--long-rails` adds an extra spanning board, and the
tenoned rails stay put, so the gap budget still passes. `--wide-tile` moves
the posts out to where the first build had them and moves the rails with
them. It is checked before the AABB gate, which it would also fail.

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
blender --background --python fence_kit.py -- --float-brace
blender --background --python fence_kit.py -- --wide-tile
blender --background --python fence_kit.py -- --output fence.png
```

Smoke passes no flags.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20` and `21` are this piece's own.

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
| 20 | Brace not housed in both posts or not bearing on the middle rail (`--float-brace`) |
| 21 | Section does not fit its tile (`--wide-tile`) |
