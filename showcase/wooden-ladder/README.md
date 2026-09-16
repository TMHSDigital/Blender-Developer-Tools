# Wooden ladder

A showcase piece, not an example. Procedural timber ladder (raked
stiles, six 26 mm dowel rungs tenoned into the stiles, iron shoes and
top caps) then the shipped pipeline: unique-cell UVs, Cycles
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

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
| Base triangles | 900–975 | 936 / 936 / 936 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2179 / 0.2179 / 0.2179 |
| Materials | exactly 2 distinct, ≥280 wood, ≥180 metal | 2 slots, 324 wood, 216 metal |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.472, 0.365, 1.460) m ± 0.01 | (0.4720, 0.3649, 1.4597) |
| Grounded | `abs(zmin)` ≤ 1e-4 | 0.0000 |
| Mesh hygiene | non-manifold, loose v/e, doubles at 1e-5, zero-area, n-gons all 0 | all 0 |
| Parts | exactly 12 shells (2 stiles, 6 rungs, 2 caps, 2 shoes) | 12 (2 / 6) |
| Rung depth clearance | ≥ 0.003 m inside the stile faces | 0.00361 |
| Tenon engagement | ≥ 0.006 m past the stile inner face | 0.01200 |
| Tenon breakout margin | ≥ 0.005 m short of the stile outer face | 0.04600 |
| Collider tris | ≤ 120 | 24 |
| Export | written, size > 0 | 75140 / 75140 / 75128 bytes |

Base triangles fell from **2184 to 936** in the quality pass: four iron
fittings per stile collapsed to one shoe and one top cap, and the
redundant top block came out. No hidden-face removal was involved.

The rung rims are capped and buried in the stile rather than left open.
That costs 144 tris nobody sees, but an open rim is a non-manifold
boundary and the hygiene budget forbids it.

The joint budgets are measured per rung against each stile, from vertex
positions in the un-raked construction frame, and the reported value is
the worst case over all twelve rung ends. `clearance` is how far the
widest dowel stays inside the stile's front and back faces; it must
exceed the 2.5 mm chamfer or the dowel erupts through it as a spike.

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. On this mesh the three
binaries agreed on LOD ratios. Bake pixels are stochastic; the gate is
`has_data` plus operator `FINISHED`, not byte-identity. Construction
uses no RNG. Export byte counts differ by 16 B on 5.2.1 (glTF
serializer), not a gated axis.

Each falsifier violates exactly one named budget, and each was proven to
fire on all three binaries:

| Falsifier | Budget violated | Exit | Measured failure |
| --- | --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 | ratio 1.0000 |
| `--stray-vert` | Mesh hygiene, loose verts | 15 | `loose_v=1` |
| `--lift-z` | Grounded zmin | 16 | zmin 0.050000 |
| `--fat-rungs` | Rung depth clearance | 17 | clearance −0.00051 |

`--fat-rungs` widens the dowels to the full 34 mm stile depth, which is
the proportion this piece shipped with before the quality pass.

## Run

```bash
blender --background --python wooden_ladder.py --
blender --background --python wooden_ladder.py -- --skip-decimate
blender --background --python wooden_ladder.py -- --stray-vert
blender --background --python wooden_ladder.py -- --lift-z
blender --background --python wooden_ladder.py -- --fat-rungs
blender --background --python wooden_ladder.py -- --output ladder.png
```

Smoke passes no flags: no `--output`, no falsifier.

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
| 15 | Mesh hygiene (`--stray-vert` lands here) |
| 16 | World AABB min Z off the floor (`--lift-z` lands here) |
| 17 | Part count or rung-to-stile joint fit (`--fat-rungs` lands here) |
