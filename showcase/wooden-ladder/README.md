# Wooden ladder

A showcase piece, not an example. Procedural timber ladder: two stiles
tapered from 64 mm to 50 mm, raked 12°, six turned rungs (22 mm tenon,
barrel thicker only in the clear span), iron ferrules at the top, and
level shoe plates under sleeves that follow the rake. Then the shipped
pipeline: unique-cell UVs, Cycles high-to-low normal bake, LOD chain,
convex collider, Unity glTF export.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

Intended size: stile length 1.50 m, overall about 0.49 × 0.38 × 1.49 m.
A household ladder, not a 3 m orchard ladder.

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
| Base triangles | 1800–2800 | 2536 / 2536 / 2536 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2192 / 0.2192 / 0.2192 |
| Materials | exactly 2 distinct, ≥280 wood, ≥180 metal | 2 slots, 612 wood, 736 metal |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.490, 0.376, 1.487) m ± 0.01 | (0.4897, 0.3760, 1.4870) |
| Grounded | `abs(zmin)` ≤ 1e-4, each sole at 0, rail end ≥ 0.012 m | zmin 0, sole 0, rail 0.02037 |
| Mesh hygiene | non-manifold, loose v/e, doubles at 1e-5, zero-area, n-gons, coplanar pairs all 0 | all 0 |
| Parts | 16 shells (2 stiles, 6 rungs, 2 sleeves, 2 cap sleeves, 2 plates, 2 soles) | 16 (2 / 6 / 2 / 2) |
| Rung depth clearance | ≥ 0.003 m inside the stile faces | 0.00800 |
| Tenon engagement | ≥ 0.008 m past the stile inner face | 0.01399 |
| Tenon breakout margin | ≥ 0.008 m short of the stile outer face | 0.03780 |
| Shoe bite / cover | bite ≥ 0.010 m, cover ≥ 0.016 m | 0.02000 / 0.03800 |
| Collider tris | ≤ 180 | 24 |
| Export | written, size > 0 | 187528 / 187528 / 187504 bytes |

Base triangles rose from **936 to 2536**. The previous mesh was two
boxes, six cloned dowels, and four chrome cubes. Turned rungs (tenon
and barrel in one shell) plus ferrule collars and chamfered soles added
the triangles. Nothing was removed as a hidden face.

The joint budgets are measured per rung against each stile, from vertex
positions in the un-raked construction frame, and the reported value is
the worst case. Clearance is the tenon, not the barrel: the barrel is
thicker only between the stiles.

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. On this mesh the three
binaries agreed. Bake pixels are stochastic; the gate is `has_data`
plus operator `FINISHED`, not byte-identity. Construction uses no RNG.
Export byte counts differ by 24 B on 5.2.1 (glTF serializer), not a
gated axis. Euler is 24 (multi-body) and is not gated to 2.

Each falsifier violates exactly one named budget. Proven on Blender
4.5.11 LTS, 5.1.2, and 5.2.1 LTS (the binaries' own `--version`):

| Falsifier | Budget violated | Exit | Measured failure |
| --- | --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 | ratio 1.0000 |
| `--stray-vert` | Mesh hygiene, loose verts | 15 | `loose_v=1` |
| `--twin-sole` | Coplanar face pairs | 15 | `zfight=6` |
| `--lift-z` | Grounded zmin | 16 | zmin 0.050000 |
| `--fat-rungs` | Rung depth clearance | 17 | clearance 0 |
| `--short-stile` | Shoe bite / cover | 18 | bite 0.070, cover −0.012 |

Default exit is 0 on all three.

## Run

```bash
blender --background --python wooden_ladder.py --
blender --background --python wooden_ladder.py -- --skip-decimate
blender --background --python wooden_ladder.py -- --stray-vert
blender --background --python wooden_ladder.py -- --twin-sole
blender --background --python wooden_ladder.py -- --lift-z
blender --background --python wooden_ladder.py -- --fat-rungs
blender --background --python wooden_ladder.py -- --short-stile
blender --background --python wooden_ladder.py -- --output preview.webp --engine cycles
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
| 15 | Mesh hygiene, including coplanar pairs (`--stray-vert`, `--twin-sole`) |
| 16 | Grounded zmin, or a rail end sitting in the tread (`--lift-z`) |
| 17 | Part count or rung-to-stile joint fit (`--fat-rungs`) |
| 18 | Shoe bite / cover (`--short-stile`) |
