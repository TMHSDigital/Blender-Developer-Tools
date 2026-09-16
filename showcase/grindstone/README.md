# Grindstone

A showcase piece, not an example. Procedural grindstone (sandstone
wheel, timber A-frame trestle, iron shoes/axle/hubs/crank, open water
trough) then the shipped pipeline: unique-cell UVs, Cycles high-to-low
normal bake, LOD chain, convex collider, Unity glTF export.

The A-frame is a king post with diagonals tenoning into a fatter sill,
not two sticks meeting at a point. The trough is one manifold basin
seated into those sills. Iron shoes bury a short wood tenon so the
angled leg end-cap cannot pierce Z=0.

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
| Base triangles | 700–1000 | 928 / 928 / 928 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2198 / 0.2198 / 0.1897 |
| Materials | exactly 3 distinct; ≥80 wood, stone, metal faces | 3 slots; 216 / 160 / 180 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.710, 0.419, 0.610) m ± 0.015 | (0.7100, 0.4185, 0.6100), zmin 0 |
| Collider tris | ≤ 240 | 198 |
| Export | written, size > 0 | 89316 / 89316 / 89312 bytes |

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
| Named supports: 4 shoes | each `zmin` ≤ 1e-3 | 4, shoe_z 0.00000 |
| Stone size | 0.500 m dia × 0.095 m thick ± 0.02 / ± 0.015 | 0.5000 × 0.0950 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Crank-axle gap | ≤ 0.008 m | 0.00418 |
| Shoe-wood BVH gap | ≤ 0.008 m (overlap is 0) | 0.00000 |
| Trough-sill per-side gap | ≤ 0.008 m (overlap is 0) | 0.00000 |
| Stone dip into trough | 0.015–0.045 m | 0.02570 |
| Trough floor zmin | ≥ 0.040 m | 0.05800 |

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is leaner on LOD2. The gate is a ratio band, not an exact count.
Bake pixels are stochastic; the gate is `has_data` plus operator
`FINISHED`, not byte-identity. Construction uses no RNG. Export byte
counts differ by 4 B on 5.2.1 (glTF serializer), not a gated axis.

### Falsifiers

Each violates one named budget. All nine were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-legs` | named shoe supports at Z=0 | 16 |
| `--float-crank` | crank-axle gap | 17 |
| `--float-legs` | shoe-wood join | 17 |
| `--no-dip` | stone dip band | 18 |
| `--narrow-trough` | trough-sill seat | 18 |

## Run

```bash
blender --background --python grindstone.py --
blender --background --python grindstone.py -- --skip-decimate
blender --background --python grindstone.py -- --stray-vert
blender --background --python grindstone.py -- --lift-z
blender --background --python grindstone.py -- --short-legs
blender --background --python grindstone.py -- --float-crank
blender --background --python grindstone.py -- --float-legs
blender --background --python grindstone.py -- --no-dip
blender --background --python grindstone.py -- --narrow-trough
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
| 15 | Mesh hygiene: loose, non-manifold, zero-area, doubles, n-gons, z-fight |
| 16 | Not grounded: bounding box `zmin` off 0, or a named shoe floats |
| 17 | Joint fit: crank-axle gap, or shoe-wood join |
| 18 | Seat: trough-sill gap, stone dip band, or trough sitting on the dirt |
| 19 | Stone diameter or thickness off the stated real-world size |
