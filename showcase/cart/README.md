# Cart

A showcase piece, not an example. A procedural two-wheel handcart built
on two rails that run on past the bed as shafts, with a pull bar through
their tips and two prop legs under them. It has a planked floor, board
walls with iron corner straps, and spoked wheels on long naves with iron
bands, tyres and washers. The piece then runs the shipped pipeline:
unique-cell UVs, a Cycles high-to-low normal bake, an LOD chain, a convex
collider, and a Unity glTF export.

The chassis is stacked from the axle up, and every member bites the one
below it by a named depth: axle, bolster, rails, floor planks, walls. The
cart stands level on four named supports: two tyres and two legs.
Stated size is 1.58 m long, 0.84 m across the axle ends and 0.64 m tall.
The wheels are 0.64 m in diameter and the bed is 0.92 × 0.50 m.

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
| Base triangles | 5160–5410 | 5284 / 5284 / 5284 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2199 / 0.2199 / 0.2146 |
| Materials | exactly 2 distinct, metal ≥ 800, wood ≥ 1200 faces | 2 slots; 1196 metal, 1694 wood |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.580, 0.842, 0.640) m ± 0.01 | (1.5800, 0.8420, 0.6400) |
| Collider tris | ≤ 360 | 192 |
| Bake texels | smallest UV cell ≥ 12 px at the baked resolution | 17.45 px at 1024 px |
| Export | written, size > 0, removed after measuring | 403176 / 403176 / 403160 bytes |

### Hygiene, supports and joints

Recomputed from the generated mesh on all three binaries, identical on
each.

| Axis | Declared | Measured |
| --- | --- | --- |
| Loose V/E, non-manifold, zero-area, doubles @1e-5, n-gons | all 0 | all 0 |
| Z-fighting | coplanar cross-shell face pairs = 0 | 0 |
| Grounded | bbox min Z within 1e-4 of 0 | 0.0000 |
| Named supports | 2 legs found; each tyre and leg zmin within 1e-4 of the floor | 2 legs; all four 0.000000 |
| Material-island gap | metal↔wood min distance ≤ 0.008 m | 0.00023 |
| Wall boards | 2 boards per side wall, seams 0.0015–0.005 m | (2, 2), seams 0.00300 |
| Tyre seat | 0.0030–0.0055 m interference, per angular station | [0.00400, 0.00400] over 48 stations |
| One assembly | the shells' BVH-overlap graph is 1 component | 1 component, 59 shells |
| Wheel mirror | the two wheels match in X, Z and extent within 5e-5 m | 0.00000 mm |
| Edge treatment | manifold edges within 5° of 90° = 0 | 0 wood, 0 iron |

DECIMATE COLLAPSE triangle counts are **not** identical across series.
5.2.1 is more aggressive on LOD2, so the gate is a ratio band, not an
exact count. Bake pixels are stochastic; the gate is `has_data` plus
operator `FINISHED` plus the texel floor, not byte-identity. Per-board
tone comes from `random.Random(TONE_SEED)`, so it is identical run to run.
Export byte counts differ by a few bytes across series (glTF
serializer). The gate is "written and non-empty", not a byte count, and
the file is removed once measured.

The bake cage is 0.01 m: it only has to cover the chamfer difference
between the 3-segment high and the 1-segment low. At 0.08 m it reached
past the 74 mm between a side wall and its wheel, so rays from the wall
hit the high-poly felloe. The wheel's rim baked onto the board as a black
staircase.

## Falsifiers

Each flag breaks one stage so a **named** budget fails and the piece
exits *that* code. Magnitudes are sized so no earlier gate can steal the
failure. The wheel, leg and bed moves stay inside `BBOX_TOL`, so the AABB
gate (exit 8) still passes, and no flag changes the triangle count by
more than the band allows.

| Flag | Target budget | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (ratio becomes 1.0) | 9 |
| `--flush-tyre` | Coplanar cross-shell pairs: sets the tyre's inner radius equal to the felloe's outer radius, which is the construction bug this piece was rebuilt to remove (0 → 144 pairs) | 15 |
| `--lift-z` | AABB grounded zmin (whole mesh up 0.05 m) | 16 |
| `--float-wheel` | Named supports: lifts one wheel 3 mm while the other still grounds the AABB | 16 |
| `--short-props` | Named supports: stops both prop legs 3 mm above the floor while the tyres still ground the AABB | 16 |
| `--wide-seams` | Wall board seams: opens every seam to 10 mm, same triangle count | 17 |
| `--sink-tyre` | Tyre seat band: buries the hoop 9 mm into the felloe so it reads as one body | 18 |
| `--lift-bed` | One assembly: raises the box (planks, walls, straps) 7 mm off its rails, so the contact graph splits in two | 18 |
| `--skew-wheel` | Wheel mirror: pushes one wheel 6 mm out along the track | 19 |
| `--sharp-bar` | Edge treatment: leaves the pull bar's rims unchamfered (24 right-angle edges, 48 triangles short) | 20 |
| `--low-bake` | Bake texel density: bakes at 256 px (4.36 px per cell) | 21 |

`--lift-z`, `--float-wheel` and `--short-props` share exit 16 and fail
different budgets. `--lift-z` fails the AABB gate, which fires first. The
other two leave the AABB grounded, so only the per-support check can catch
them. `--sharp-bar` replaced a flag that skipped the whole iron chamfer
pass. That flag dropped 1200 triangles and tripped the triangle floor
(exit 4) instead of the edge budget.

## Run

```bash
blender --background --python cart.py --
blender --background --python cart.py -- --skip-decimate
blender --background --python cart.py -- --flush-tyre
blender --background --python cart.py -- --lift-z
blender --background --python cart.py -- --float-wheel
blender --background --python cart.py -- --short-props
blender --background --python cart.py -- --wide-seams
blender --background --python cart.py -- --sink-tyre
blender --background --python cart.py -- --lift-bed
blender --background --python cart.py -- --skew-wheel
blender --background --python cart.py -- --sharp-bar
blender --background --python cart.py -- --low-bake
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
| 3 | Mesh did not build / no UV layer / wheels not found |
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
| 15 | Hygiene: loose geometry, non-manifold, zero-area, doubles, n-gons, or coplanar cross-shell face pairs (`--flush-tyre` lands here) |
| 16 | Bbox min Z not grounded (`--lift-z`), or a named support off the floor (`--float-wheel`, `--short-props`) |
| 17 | Material-island gap above tolerance, or wall boards miscounted or their seams out of band (`--wide-seams`) |
| 18 | Tyre seat depth outside its band (`--sink-tyre`), or the shells not one connected assembly (`--lift-bed`) |
| 19 | Wheel mirror deviation above epsilon (`--skew-wheel` lands here) |
| 20 | A right-angle edge survived the chamfer passes (`--sharp-bar` lands here) |
| 21 | Bake texel density below the floor (`--low-bake` lands here) |
