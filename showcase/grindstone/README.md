# Grindstone

A showcase piece, not an example. A procedural grindstone: a sandstone
wheel, a timber A-frame trestle, iron shoes, axle, hubs and crank, and an
open trough. The piece then runs the shipped pipeline: unique-cell UVs, a
Cycles high-to-low normal bake, an LOD chain, a convex collider, and a
Unity glTF export.

Each A-frame is a king post with two diagonals tenoned 12 mm into its
faces and into a fatter sill. It is not two sticks meeting at a point. The
sills stand in iron shoes, cups one 6 mm reveal proud of the sill on every
side. The trough is one manifold basin seated into the sills and carried
on two end stretchers, which it bites by 4 mm. Every timber and iron edge
is chamfered. The stone is 48 smooth segments with hard chamfer rings, in
a mottled sandstone material. Stated size is a 0.50 m × 0.095 m stone in a
0.72 × 0.42 × 0.61 m frame.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1560–1780 | 1668 / 1668 / 1668 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2194 / 0.2194 / 0.2194 |
| Materials | exactly 3 distinct; ≥ 280 wood, ≥ 190 stone, ≥ 260 metal faces | 3 slots; 400 / 240 / 364 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.722, 0.419, 0.610) m ± 0.015 | (0.7220, 0.4185, 0.6100), zmin 0 |
| Collider tris | ≤ 320 | 304 |
| Bake texels | smallest UV cell ≥ 12 px at the baked resolution | 29.44 px at 1024 px |
| Export | written, size > 0 | 152272 / 152272 / 152260 bytes |

The collider ceiling moved from 240 to 320 with the stone. 48 segments
put more of its rim on the hull (198 → 304 triangles).

### Hygiene

Recomputed from the generated mesh, not asserted about the script.

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Non-manifold edges | 0 | 0 |
| Loose verts / edges | 0 / 0 | 0 / 0 |
| Doubles merged at 1e-5 | 0 | 0 |
| Zero-area faces | 0 | 0 |
| N-gons | 0 | 0 |
| Coplanar cross-shell face pairs | 0 | 0 |
| Grounded: `zmin` | within 1e-4 of 0 | 0.0000 |
| Named supports: 4 shoes | each `zmin` ≤ 1e-3 | 4, shoe_z 0.00000 |
| Stone size | 0.500 m dia × 0.095 m thick ± 0.02 / ± 0.015 | 0.5000 × 0.0950 |
| Edge treatment | manifold edges within 5° of 90° = 0 | 0 wood, 0 stone, 0 iron |

The coplanar budget counts pairs from different shells within 0.05 m,
using `hay-bale`'s constants. The first build matched only faces whose
centres fell within 0.1 mm of each other, and no real overlap ever does.
It reported 0 while the shoes shared three planes with every sill end,
seen as a lit slit in each foot close-up.

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Crank-axle gap | ≤ 0.008 m | 0.00376 |
| Shoe-wood BVH gap | ≤ 0.008 m (overlap is 0) | 0.00000 |
| Trough-sill per-side gap | ≤ 0.008 m (overlap is 0) | 0.00000 |
| Stone dip into trough | 0.015–0.045 m | 0.02416 |
| Trough floor zmin | ≥ 0.040 m | 0.05800 |
| Trough bearing | 2 end stretchers, each biting the trough floor 0.002–0.008 m | 2, [0.00400, 0.00400] |

DECIMATE COLLAPSE triangle counts can differ across series, so the gate is
a ratio band, not an exact count. Bake pixels are stochastic. The gate is
`has_data` plus operator `FINISHED` plus the texel floor, not
byte-identity. Per-member wood tone comes from `random.Random(TONE_SEED)`,
so it is identical run to run. Export byte counts differ by 12 B on 5.2.1
(glTF serializer), which is not a gated axis.

## Falsifiers

Each violates one named budget. All thirteen were run on 4.5.11, 5.1.2
and 5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--flush-shoes` | coplanar cross-shell pairs: shoes sized to the sill and flush with its end (0 → 4 pairs) | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-legs` | named shoe supports at Z=0 | 16 |
| `--float-crank` | crank-axle gap | 17 |
| `--float-legs` | shoe-wood join | 17 |
| `--narrow-trough` | trough-sill seat | 18 |
| `--no-dip` | stone dip band | 18 |
| `--low-stretchers` | trough bearing: stretchers back at sill height, 5.9 mm under the trough | 18 |
| `--sharp-handle` | edge treatment: the crank handle's rims left square (20 right-angle edges) | 20 |
| `--low-bake` | bake texel density: 256 px bake (7.36 px per cell) | 21 |

`--flush-shoes` moves the shoe envelope 12 mm inside `BBOX_TOL` (15 mm),
so the AABB gate cannot steal it. `--sharp-handle` leaves the triangle
count inside its band, so only the edge budget sees it.

## Run

```bash
blender --background --python grindstone.py --
blender --background --python grindstone.py -- --skip-decimate
blender --background --python grindstone.py -- --stray-vert
blender --background --python grindstone.py -- --flush-shoes
blender --background --python grindstone.py -- --lift-z
blender --background --python grindstone.py -- --short-legs
blender --background --python grindstone.py -- --float-crank
blender --background --python grindstone.py -- --float-legs
blender --background --python grindstone.py -- --narrow-trough
blender --background --python grindstone.py -- --no-dip
blender --background --python grindstone.py -- --low-stretchers
blender --background --python grindstone.py -- --sharp-handle
blender --background --python grindstone.py -- --low-bake
blender --background --python grindstone.py -- --output grindstone.png
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
| 5 | Material count ≠ 3 distinct slots, or a face-count floor missed |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Mesh hygiene: loose, non-manifold, zero-area, doubles, n-gons, coplanar cross-shell pairs |
| 16 | Not grounded: bounding box `zmin` off 0, or a named shoe floats |
| 17 | Joint fit: crank-axle gap, or shoe-wood join |
| 18 | Seat: trough-sill gap, stone dip band, trough on the dirt, or trough not bearing on its stretchers |
| 19 | Stone diameter or thickness off the stated real-world size |
| 20 | A right-angle edge survived the chamfer passes (`--sharp-handle` lands here) |
| 21 | Bake texel density below the floor (`--low-bake` lands here) |
