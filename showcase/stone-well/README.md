# Stone well

A showcase piece, not an example. Procedural round stone well (running-bond
bricks, curb, four posts, shingled pyramid roof, windlass, rope, bucket)
then the shipped pipeline: unique-cell UVs, Cycles high-to-low normal bake,
LOD chain, convex collider, Unity glTF export.

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
| Base triangles | 8280–9500 | 9380 / 9380 / 9380 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2198 / 0.2198 / 0.2198 |
| Materials | exactly 3 distinct | 3 |
| Material faces | stone ≥ 3000, wood ≥ 600, metal ≥ 100 | all above |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.312, 1.312, 1.761) m ± 0.01 | (1.3120, 1.3120, 1.7606) |
| Grounded | bbox min Z within 1e-4 of 0 | 0.0000 / 0.0000 / 0.0000 |
| Named supports | all 12 bottom-course stones on the floor within 1e-4 | 12/12, worst 0.000000 |
| Hygiene | loose V/E, non-manifold, zero-area, doubles @1e-5, n-gons: all 0 | 0 / 0 / 0 on every axis |
| Z-fighting | coplanar cross-shell face pairs = 0 | 0 / 0 / 0 |
| Post tenon | each post seats 0.015–0.022 m into the measured coping top | 0.01800 / 0.01800 / 0.01800 |
| Post placement | each post within 0.02 rad, in plan, of a roof hip corner recomputed from the mesh | 0.00000 |
| Bucket clearance | hangs 0.085–0.115 m clear of the measured coping top | 0.10000 |
| Material-island gap | stone↔wood and metal↔wood min distance ≤ 0.008 m | 0.00000 / 0.00000 / 0.00000 |
| Collider tris | ≤ 380 | 346 |
| Export | written, size > 0, removed after measuring | 690092 bytes on 5.2.1 |

DECIMATE COLLAPSE triangle counts are **not** guaranteed identical across
series — the gate is a ratio band, not an exact count. This mesh happened
to match on 4.5.11 / 5.1.2 / 5.2.1. Bake pixels are stochastic; the gate
is `has_data` plus operator `FINISHED`, not byte-identity. Construction
uses no RNG. glTF byte size differs by a few hundred bytes across
series; the gate is "written and non-empty", not a byte count, and the
file is removed once measured.

## Falsifiers

Each flag breaks one stage so a **named** budget fails and the piece
exits *that* code.

| Flag | Target budget | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (ratio becomes 1.0) | 9 |
| `--lift-z` | AABB grounded zmin (whole mesh up 0.05 m) | 16 |
| `--stand-posts` | Coplanar cross-shell pairs — puts the posts back on the axis *and* stands them on the coping, which is the pair of choices the shipped piece made (0 → 4 pairs) | 15 |
| `--float-stone` | Named supports — lifts one bottom-course stone 4 mm while the other eleven still ground the AABB | 16 |
| `--shallow-tenon` | Post tenon band — seats the posts only 4 mm, too shallow to be a joint but not flush, so no faces share a plane | 18 |
| `--drop-bucket` | Bucket clearance — lowers the bucket 0.26 m back down the shaft | 18 |
| `--turn-posts` | Post placement — rotates the post ring one curb facet off the roof's hip corners | 19 |

Two of these had to be re-aimed, which is the point of declaring the
target:

- `--stand-posts` seats the posts flush **and** returns them to the
  axis. Flush alone, at the corrected 45°, leaves no coping top face
  within `COPLANAR_CENTRE_MAX` of a foot, so it fell through to the
  tenon band (18) and witnessed nothing about z-fighting.
- `--turn-posts` rotates by exactly one curb facet (30°). Any other
  angle sets the feet down on a different part of the 12-gon coping and
  the stone-wood gap gate (17) steals the failure; a full 45° also
  swings the crank grip past the eave and fails the AABB gate (8) —
  the same trap `stone-archway`'s `--flat-arch` fell into. One facet is
  the only rotation whose local seat geometry is identical by symmetry.

## Run

```bash
blender --background --python stone_well.py --
blender --background --python stone_well.py -- --skip-decimate
blender --background --python stone_well.py -- --lift-z
blender --background --python stone_well.py -- --stand-posts
blender --background --python stone_well.py -- --shallow-tenon
blender --background --python stone_well.py -- --turn-posts
blender --background --python stone_well.py -- --float-stone
blender --background --python stone_well.py -- --drop-bucket
blender --background --python stone_well.py -- --output well.png
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
| 5 | Material count ≠ 3 distinct slots, or a material face floor missed |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Hygiene: loose geometry, non-manifold, zero-area, doubles, n-gons, or coplanar cross-shell face pairs (`--stand-posts` lands here) |
| 16 | Bbox min Z not grounded (`--lift-z`), or a named support off the floor (`--float-stone`) |
| 17 | Material-island gap above tolerance (parts meant to touch) |
| 18 | Post tenon depth outside its band (`--shallow-tenon`), or bucket clearance outside its band (`--drop-bucket`) |
| 19 | A post not under a roof hip corner in plan (`--turn-posts` lands here) |
