# Treasure chest

A showcase piece, not an example. Procedural iron-bound chest (slatted
hollow body, barrel-vault lid, U-wrap bands, corner irons, lock plate,
hinge barrels with lid knuckles, wooden feet) then the shipped pipeline:
unique-cell UVs, Cycles high-to-low normal bake, LOD chain, convex
collider, Unity glTF export.

The lid is one lofted vault slab, not stacked boxes. Hinge join is
measured from local lid knuckles over the barrels — a spanning stile
only has verts at the X ends, 8 cm from the knuckles, and reports a
false gap.

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
| Base triangles | 3600–4500 | 3852 / 3852 / 3852 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2196 / 0.2196 / 0.2129 |
| Materials | exactly 2 distinct; ≥200 wood, ≥80 metal faces | 2 slots; 1608 / 318 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.764, 0.542, 0.691) m ± 0.015 | (0.7640, 0.5423, 0.6907), zmin 0 |
| Collider tris | ≤ 200 | 176 |
| Export | written, size > 0 | 288196 / 288196 / 288184 bytes |

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
| Named supports: 4 feet | each `zmin` ≤ 1e-3 | 4, foot_z 0.00000 |
| Body plan | 0.74 × 0.46 m ± 0.04 | 0.7400 × 0.4600 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Lid-knuckle to hinge barrel | ≤ 0.020 m | 0.00700 |
| Band-wall BVH gap | ≤ 0.008 m | 0.00000 |

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. Bake pixels are
stochastic; the gate is `has_data` plus operator `FINISHED`, not
byte-identity. Construction uses no RNG. Export byte counts may differ
by a few bytes across series.

### Falsifiers

Each violates one named budget. All seven were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-legs` | named foot supports at Z=0 | 16 |
| `--float-hinge` | lid-knuckle to hinge barrel | 17 |
| `--narrow-bands` | band-wall seat | 18 |

## Run

```bash
blender --background --python treasure_chest.py --
blender --background --python treasure_chest.py -- --skip-decimate
blender --background --python treasure_chest.py -- --stray-vert
blender --background --python treasure_chest.py -- --lift-z
blender --background --python treasure_chest.py -- --short-legs
blender --background --python treasure_chest.py -- --float-hinge
blender --background --python treasure_chest.py -- --narrow-bands
blender --background --python treasure_chest.py -- --output chest.png
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
| 5 | Material count ≠ 2 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a named foot floats |
| 17 | Joint fit: lid-knuckle to hinge barrel |
| 18 | Seat: band-wall gap |
| 19 | Body plan off the stated real-world size |
