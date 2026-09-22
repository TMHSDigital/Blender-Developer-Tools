# Cart

A showcase piece, not an example. Procedural two-wheel wooden cart
(slatted bed, side walls, shafts, spoked wheels, iron hubs and axle)
then the shipped pipeline: unique-cell UVs, Cycles high-to-low normal
bake, LOD chain, convex collider, Unity glTF export.

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
| Base triangles | 2760–2960 | 2856 / 2856 / 2856 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2199 / 0.2199 / 0.2157 |
| Materials | exactly 2 distinct, metal ≥ 24, wood ≥ 800 faces | 2 slots, floors met |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.539, 0.749, 0.640) m ± 0.01 | (1.5393, 0.7486, 0.6400) |
| Grounded | bbox min Z within 1e-4 of 0 | 0.0000 / 0.0000 / 0.0000 |
| Named supports | each tyre's own zmin within 1e-4 of the floor | +Y 0.000000, −Y 0.000000 |
| Hygiene | loose V/E, non-manifold, zero-area, doubles @1e-5, n-gons: all 0 | 0 / 0 / 0 on every axis |
| Z-fighting | coplanar cross-shell face pairs = 0 | 0 / 0 / 0 |
| Tyre seat | 0.0030–0.0055 m interference, per angular station | [0.00400, 0.00400] over 48 stations |
| Wheel mirror | the two wheels match in X, Z and extent within 5e-5 m | 0.00000 mm |
| Material-island gap | metal↔wood min distance ≤ 0.008 m | 0.00000 / 0.00000 / 0.00000 |
| Collider tris | ≤ 360 | 154 |
| Export | written, size > 0, removed after measuring | 221960 bytes on 5.2.1 |

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is more aggressive on LOD2. The gate is a ratio band, not an
exact count. Bake pixels are stochastic; the gate is `has_data` plus
operator `FINISHED`, not byte-identity. Construction uses no RNG.
Export byte counts differ by a few bytes across series (glTF
serializer); the gate is "written and non-empty", not a byte count, and
the file is removed once measured.

## Falsifiers

Each flag breaks one stage so a **named** budget fails and the piece
exits *that* code. Magnitudes are sized so no earlier gate can steal the
failure: the two wheel moves stay inside `BBOX_TOL`, so the AABB gate
(exit 8) still passes.

| Flag | Target budget | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (ratio becomes 1.0) | 9 |
| `--lift-z` | AABB grounded zmin (whole mesh up 0.05 m) | 16 |
| `--flush-tyre` | Coplanar cross-shell pairs — sets the tyre's inner radius equal to the felloe's outer radius, which is the construction bug this piece was rebuilt to remove (0 → 48 pairs) | 15 |
| `--sink-tyre` | Tyre seat band — buries the hoop 9 mm into the felloe so it reads as one body | 18 |
| `--float-wheel` | Named supports — lifts one wheel 3 mm while the other still grounds the AABB | 16 |
| `--skew-wheel` | Wheel mirror — pushes one wheel 6 mm out along the track | 19 |

`--lift-z` and `--float-wheel` share exit 16 and fail different budgets:
`--lift-z` fails the AABB gate, which fires first; `--float-wheel` leaves
the AABB grounded, so only the per-tyre support check can catch it.

## Run

```bash
blender --background --python cart.py --
blender --background --python cart.py -- --skip-decimate
blender --background --python cart.py -- --lift-z
blender --background --python cart.py -- --flush-tyre
blender --background --python cart.py -- --sink-tyre
blender --background --python cart.py -- --float-wheel
blender --background --python cart.py -- --skew-wheel
blender --background --python cart.py -- --output cart.png
```

Smoke passes none of the falsifier flags and no `--output`.

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
| 5 | Material count ≠ 2 distinct slots, or metal faces missing |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Hygiene: loose geometry, non-manifold, zero-area, doubles, n-gons, or coplanar cross-shell face pairs (`--flush-tyre` lands here) |
| 16 | Bbox min Z not grounded (`--lift-z`), or a named support off the floor (`--float-wheel`) |
| 17 | Material-island gap above tolerance (parts meant to touch) |
| 18 | Tyre seat depth outside its band (`--sink-tyre` lands here) |
| 19 | Wheel mirror deviation above epsilon (`--skew-wheel` lands here) |
