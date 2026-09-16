# Shipping crate

A showcase piece, not an example. Procedural crate (skids under the
posts, corner posts with tenoned slats and seeded width jitter, bottom
sills, L-straps, filleted iron bail handles through mounting plates)
then the shipped pipeline: unique-cell UVs, Cycles high-to-low normal
bake, LOD chain, convex collider, Unity glTF export.

Skids sit under the posts so the outer corner is a mortise, not a cave.
Handle bails use quarter-circle corners so a 90-degree loft cannot sit
the bar on the plate.

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
| Base triangles | 1200–2800 | 2508 / 2508 / 2508 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2193 / 0.2193 / 0.2057 |
| Materials | exactly 2 distinct; ≥200 wood, ≥48 metal faces | 2 slots; 1170 / 280 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.146, 0.726, 0.612) m ± 0.015 | (1.1460, 0.7260, 0.6120), zmin 0 |
| Collider tris | ≤ 220 | 76 |
| Export | written, size > 0 | 197408 / 197408 / 197392 bytes |

Base triangles rose from **624 to 2508** in the quality pass: the old
beveled cube with glued-on slats became a post-and-slat crate with
tenons, sills, L-straps, and pipe handles.

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is leaner on LOD2. The gate is a ratio band, not an exact count.
Bake pixels are stochastic; the gate is `has_data` plus operator
`FINISHED`, not byte-identity. Slat-width jitter uses fixed seed 17.
Export byte counts differ by 16 B on 5.2.1 (glTF serializer), not a
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
| Named supports: 3 skids | each `zmin` ≤ 1e-3 | 3, skid_z 0.00000 |
| Body plan | 1.056 × 0.716 m ± 0.05 | 1.0560 × 0.7160 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Handle-end BVH gap | ≤ 0.008 m | 0.00000 |
| Slat-post BVH gap | ≤ 0.006 m | 0.00000 |

### Falsifiers

Each violates one named budget. All seven were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-skids` | named skid supports at Z=0 | 16 |
| `--float-handle` | handle-end gap | 17 |
| `--omit-slats` | slat-post seat | 18 |

## Run

```bash
blender --background --python shipping_crate.py --
blender --background --python shipping_crate.py -- --skip-decimate
blender --background --python shipping_crate.py -- --stray-vert
blender --background --python shipping_crate.py -- --lift-z
blender --background --python shipping_crate.py -- --short-skids
blender --background --python shipping_crate.py -- --float-handle
blender --background --python shipping_crate.py -- --omit-slats
blender --background --python shipping_crate.py -- --output crate.png
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
| 16 | Not grounded: bounding box `zmin` off 0, or a named skid floats |
| 17 | Joint fit: handle-end gap |
| 18 | Seat: slat-post gap |
| 19 | Body plan off the stated real-world size |
