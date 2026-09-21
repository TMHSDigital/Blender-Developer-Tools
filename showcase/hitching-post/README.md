# Hitching post

A showcase piece, not an example. Procedural timber hitching post: a
125 mm square post seated in a closed iron shoe, one cross-rail through
the post, a pyramidal cap with eaves, and two rings hung through eyes
under the rail. Then the shipped pipeline: unique-cell UVs, Cycles
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

Intended size: post 0.125 m square and 1.16 m of timber, cap 0.096 m,
cross-rail 0.50 m. Outer AABB 0.500 × 0.149 × 1.246 m.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported). Coplanar-pair counting matches `showcase/signpost`.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1400–2400 | 1680 / 1680 / 1680 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2190 / 0.2190 / 0.2190 |
| Materials | exactly 2 distinct, ≥70 wood, ≥560 metal | 2 slots, 114 wood, 742 metal |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.500, 0.149, 1.246) m ± 0.01 | (0.5000, 0.1490, 1.2460) |
| Grounded zmin | within 1e-4 of 0 | 0 / 0 / 0 |
| Hygiene | loose/nonman/zero-area/doubles/n-gons/coplanar pairs = 0 | all 0 |
| Post seat | world zmin in (0.004, 0.014), XY centroid within 0.010 of origin, arm axis cos ≥ cos(0.5°) | 0.01000, 0, 1.000 |
| Hung ring | centerline error ≤ 0.008 m, ring–wood overlap 0, eye–wood overlap 0, shank–ring overlap 0, shank bites the eye | 0, 0, 0, 0, 40 |
| Shoe | each band overlaps the post, shoe overlaps the sole | band gap 0, sole–shoe 8 |
| Wood–metal gap | BVH surface < 0.008 m | 0.00075 |
| Collider tris | ≤ 280 | 80 |
| Export | written, size > 0 | 127428 / 127428 / 127412 bytes |

Base triangles rose from **1598 to 1680**. The old rings were faceted
tori clipped into the arm; the new eyes, shanks, and 24-segment hung
rings replace that mesh. Cylinder caps are triangulated so the n-gon
budget stays at 0.

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. On this mesh the three
binaries agreed. Bake pixels are stochastic; the gate is `has_data`
plus operator `FINISHED`, not byte-identity. Construction uses no RNG.
Export byte counts differ by 16 B on 5.2.1 (glTF serializer), not a
gated axis. Euler is 12 (six balls and seven tori) and is not gated to 2.

Each falsifier violates exactly one named budget. Proven on Blender
4.5.11 LTS, 5.1.2, and 5.2.1 LTS (the binaries' own `--version`):

| Falsifier | Budget violated | Exit | Measured failure |
| --- | --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 | ratio 1.0000 |
| `--stray-vert` | Mesh hygiene, loose verts | 15 | `loose_v=1` |
| `--twin-sole` | Coplanar face pairs | 15 | `zfight=6` |
| `--lift-z` | Grounded zmin | 16 | zmin 0.050000 |
| `--clip-ring` | Hung-ring centerline | 18 | ring_err 0.024, ring–wood overlap 32 |
| `--short-post` | Seated post | 19 | post zmin 0.030 |

Default exit is 0 on all three. `--clip-ring` also overlaps the rail;
the centerline gate is the one that fires.

## Run

```bash
blender --background --python hitching_post.py --
blender --background --python hitching_post.py -- --skip-decimate
blender --background --python hitching_post.py -- --stray-vert
blender --background --python hitching_post.py -- --twin-sole
blender --background --python hitching_post.py -- --lift-z
blender --background --python hitching_post.py -- --clip-ring
blender --background --python hitching_post.py -- --short-post
blender --background --python hitching_post.py -- --output preview.webp --engine cycles
```

Smoke does not pass `--output` or a falsifier.

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
| 15 | Hygiene, including coplanar pairs (`--stray-vert`, `--twin-sole`) |
| 16 | Grounded zmin (`--lift-z`) |
| 17 | Wood–metal BVH gap above 8 mm |
| 18 | Hung ring or shoe seat (`--clip-ring`) |
| 19 | Post plumb, origin, and cup seat (`--short-post`) |
