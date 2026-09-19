# Hand pump

A showcase piece, not an example. Procedural cast-iron village hand
pump (stepped wooden plinth, two-diameter column, 6-gon gooseneck
tube from the lower-column radius, stuffing-box head, handle, wooden
grip) then the shipped pipeline: unique-cell UVs, Cycles high-to-low
normal bake, LOD chain, convex collider, Unity glTF export.

The column stays on the origin; only zmin is snapped. The gooseneck is
a tube about named stations on the lower-column radius, not a chain of
cylinders. The flange and the plinth cap bite their hosts so stacked
caps are not coplanar.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: ~1.05 m village pump, 0.34 m plinth, 0.76 m column;
outer AABB 0.610 × 0.382 × 1.052 m.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 900–2200 | 1064 / 1064 / 1064 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2199 / 0.2199 / 0.2162 |
| Materials | exactly 2 distinct, ≥48 metal, ≥24 wood | 2 slots, 564 metal / 144 wood |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.610, 0.382, 1.052) m ± 0.015 | (0.6100, 0.3820, 1.0520), zmin 0 |
| Collider tris | ≤ 220 | 114 |
| Export | written, size > 0 | 97304 / 97304 / 97296 bytes |

Base triangles dropped from **1164 to 1064** in the quality pass: seven
sausage cylinders became one gooseneck tube, and the wood grip is no
longer beveled with the plinth. Outer AABB is 0.610 × 0.382 × 1.052 m
(was 0.610 × 0.364 × 1.049 m).

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is slightly leaner on LOD2. The gate is a ratio band, not an
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
| Plinth `zmin` | within 1e-4 of 0 | 0.00000 |

### Joint fit and column

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Spout-to-column BVH gap | ≤ 0.008 m | 0.00272 |
| Flange-to-plinth BVH gap | ≤ 0.008 m | 0.00600 |
| Lower-column radius vs `COL_R_LO` | ± 0.008 m | 0.06200 |

### Falsifiers

Each violates one named budget. All were run on 4.5.11, 5.1.2 and 5.2.1
and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--float-spout` | spout-to-column BVH gap | 17 |
| `--float-flange` | flange-to-plinth BVH gap | 18 |
| `--skinny-col` | lower-column radius | 19 |

## Run

```bash
blender --background --python hand_pump.py --
blender --background --python hand_pump.py -- --skip-decimate
blender --background --python hand_pump.py -- --stray-vert
blender --background --python hand_pump.py -- --lift-z
blender --background --python hand_pump.py -- --float-spout
blender --background --python hand_pump.py -- --float-flange
blender --background --python hand_pump.py -- --skinny-col
blender --background --python hand_pump.py -- --output hand-pump.png
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
| 16 | Grounded zmin / plinth (`--lift-z`) |
| 17 | Spout-to-column gap (`--float-spout`) |
| 18 | Flange-to-plinth gap (`--float-flange`) |
| 19 | Column radius (`--skinny-col`) |
