# Park bench

A showcase piece, not an example. Procedural wrought-iron park bench
(quarter-circle tube scroll feet tangent to the posts, slatted seat and
back, arm scrolls, wood arm caps) then the shipped pipeline: unique-cell
UVs, Cycles high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

Posts, feet, stretchers and arms share named stations (`hx`, `hy`,
`SEAT_Z`, `ARM_Z`, `SCROLL_R`). A foot is a 6-gon tube about
`(hy ± R, R)` so it is tangent to the post at `z=R` and plants at `z=0`.
The H-stretcher meets the posts at those stations; slats insert into the
post volume without sharing corner verts with the seat rails.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: 1.40 m sitting width, 0.50 m seat depth, 0.43 m seat
height, 0.64 m arm height; outer AABB 1.295 × 0.632 × 0.884 m.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 2200–4200 | 2520 / 2520 / 2520 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2198 / 0.2198 / 0.2198 |
| Materials | exactly 2 distinct, ≥48 metal, ≥24 wood | 2 slots, 540 metal / 756 wood |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.295, 0.632, 0.884) m ± 0.015 | (1.2945, 0.6314, 0.8840), zmin 0 |
| Collider tris | ≤ 180 | 82 |
| Export | written, size > 0 | 188164 / 188164 / 188148 bytes |

Base triangles rose from **2100 to 2520** in the quality pass: box-segment
scrolls became 6-gon tubes. Outer AABB widened from 1.080 × 0.566 × 0.853 m
to a 1.40 m sitting-width bench.

DECIMATE COLLAPSE triangle counts are **not** guaranteed identical across
series — the gate is a ratio band, not an exact count. This mesh matched
on 4.5.11 / 5.1.2 / 5.2.1. Bake pixels are stochastic; the gate is
`has_data` plus operator `FINISHED`, not byte-identity. Construction uses
no RNG. Export byte counts differ by 16 B on 5.2.1 (glTF serializer), not
a gated axis.

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
| Named toes | 4, each `zmin` ≤ 0.002 | 4, 0.00000 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Stretcher-to-post BVH gap | ≤ 0.008 m | 0.00120 |
| Slat-to-post BVH gap | ≤ 0.008 m | 0.00028 |
| Seat span vs `2·hx` | ± 0.08 m | 1.2720 vs 1.260 |

### Falsifiers

Each violates one named budget. All were run on 4.5.11, 5.1.2 and 5.2.1
and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-feet` | named toes plant at z=0 | 16 |
| `--float-stretcher` | stretcher-to-post BVH gap | 17 |
| `--gap-slats` | slat-to-post BVH gap | 18 |
| `--narrow-seat` | seat span vs `2·hx` | 19 |

`--short-feet` lifts only the outward toe verts. After recenter the post
join is the AABB `zmin`, so the AABB gate would still pass; the named-toe
stations fail.

## Run

```bash
blender --background --python park_bench.py --
blender --background --python park_bench.py -- --skip-decimate
blender --background --python park_bench.py -- --stray-vert
blender --background --python park_bench.py -- --lift-z
blender --background --python park_bench.py -- --short-feet
blender --background --python park_bench.py -- --float-stretcher
blender --background --python park_bench.py -- --gap-slats
blender --background --python park_bench.py -- --narrow-seat
blender --background --python park_bench.py -- --output bench.png
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
| 16 | Grounded zmin / named toes (`--lift-z`, `--short-feet`) |
| 17 | Stretcher-to-post gap (`--float-stretcher`) |
| 18 | Slat-to-post gap (`--gap-slats`) |
| 19 | Seat span (`--narrow-seat`) |
