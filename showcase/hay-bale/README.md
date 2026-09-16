# Hay bale

A showcase piece, not an example. Procedural bound straw bale (cinched
pillow loaf, end nap, two square-torus sisal belts with hitch loops)
then the shipped pipeline: unique-cell UVs, Cycles high-to-low normal
bake, LOD chain, convex collider, Unity glTF export.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: 0.90 × 0.48 × 0.38 m core loaf; outer AABB includes
cinch bulge and belts.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 750–1100 | 852 / 852 / 852 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2183 / 0.2183 / 0.2183 |
| Materials | exactly 2 distinct, ≥24 hay, ≥24 twine | 2 slots, 294 hay, 132 twine |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.920, 0.517, 0.426) m ± 0.01 | (0.9199, 0.5170, 0.4257) |
| Grounded zmin | within 1e-4 of 0 | 0 / 0 / 0 |
| Hygiene | loose/nonman/zero-area/doubles/ngons = 0 | 0 / 0 / 0 |
| Hay–twine gap | BVH surface < 0.008 m | 0.00007 / 0.00007 / 0.00007 |
| Collider tris | ≤ 400 | 78 |
| Export | written, size > 0 | 70720 / 70720 / 70712 bytes |

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. Bake pixels are
stochastic; the gate is `has_data` plus operator `FINISHED`, not
byte-identity. Construction uses no RNG. Export byte counts differ by
8 B on 5.2.1 (glTF serializer), not a gated axis.

`--skip-decimate` skips the LOD DECIMATE stage so LOD1 ratio is 1.0 and
exit 9 fires. `--lift-z` raises the mesh 5 cm so the grounded-zmin
hygiene budget fails and exit 16 fires.

## Run

```bash
blender --background --python hay_bale.py --
blender --background --python hay_bale.py -- --skip-decimate
blender --background --python hay_bale.py -- --lift-z
blender --background --python hay_bale.py -- --output bale.png
```

Smoke does not pass `--output`, `--skip-decimate`, or `--lift-z`.

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
| 5 | Material count ≠ 2 distinct slots, or hay/twine faces missing |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Hygiene: loose verts/edges, non-manifold, zero-area, doubles, or n-gons |
| 16 | Grounded zmin (`--lift-z` lands here) |
| 17 | Hay–twine BVH gap above 8 mm |
