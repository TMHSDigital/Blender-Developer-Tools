# Park bench

A showcase piece, not an example. A procedural wrought-iron park bench
(round-bar legs bent in one piece from scroll toe to post, with the rear pair
bending again into a reclined back; a slatted seat and back; armrests on
quarter-round brackets), then the shipped pipeline: unique-cell UVs, a Cycles
high-to-low normal bake, an LOD chain, a convex collider and a Unity glTF
export.

Every leg is one bar swept along one path: a quarter-circle toe about
`(hy ± R, R)`, tangent to the post where it meets it, then the post, and at
the back a 12° bend into the upright that carries the back slats. The seat
slats bear on the side rails, the back slats on the uprights, and each
armrest on its arm bar and the front leg's tenon, each by a named bite. The
H-stretcher meets the legs at the shared stations (`HX`, `HY`, `SEAT_Z`,
`ARM_Z`, `SCROLL_R`, `BACK_TOP`).

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
height, 0.64 m arm height, back reclined 12°. Outer AABB
1.295 × 0.632 × 0.887 m.

## Budgets

Declared as named constants. Every gate **recomputes** its value from the
mesh, materials, UVs, evaluated LOD, collider or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 2900–3700 | 3272 / 3272 / 3272 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2194 / 0.2194 / 0.2194 |
| Materials | exactly 2 distinct, ≥48 metal, ≥24 wood | 2 slots, 1008 metal / 756 wood |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.295, 0.632, 0.887) m ± 0.015 | (1.2945, 0.6316, 0.8870), zmin 0 |
| Collider tris | ≤ 180 | 64 |
| Export | written, size > 0 | 245620 / 245620 / 245604 bytes |

Base triangles rose from **2520 to 3272** in the second quality pass. The
square posts and 6-gon scroll tubes became 8-gon round bar swept along each
leg, the back gained its bend, and armrest brackets were added. The band was
re-fitted around the measurement and narrowed from 2200–4200.

DECIMATE COLLAPSE triangle counts are **not** guaranteed identical across
series — the gate is a ratio band, not an exact count. This mesh matched on
4.5.11 / 5.1.2 / 5.2.1. Bake pixels are stochastic; the gate is `has_data`
plus operator `FINISHED`, not byte-identity. Slat widths are closed-form and
plank tones are seeded, so repeated runs on one binary print identical
measurements. Export byte counts differ by 16 B on 5.2.1 (glTF serializer),
not a gated axis.

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

### Joint fit, bearing and form

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Stretcher-to-leg BVH gap | ≤ 0.008 m | 0.00111 |
| Slat-to-leg BVH gap | ≤ 0.008 m | 0.00016 |
| Seat span vs `2·hx` | ± 0.08 m | 1.2720 vs 1.260 |
| Bearing bite (exit 20): 7 seat slats × 2 side rails, 5 back slats × 2 uprights, 2 armrests × (front leg + arm bar), overlap depth either way round | 28 bites, each ≥ 0.0015 m | 28, min 0.00201 |
| Legs in one piece (exit 21): the shell under each toe station is a leg reaching the seat | 4 | 4 |
| Back recline (exit 19): each upright, from a low and a high slab centroid | 9°–16° | 12.00° / 12.00° |

The bearing bite takes the overlap either way round. A round rail has
vertices only at its end rings, so under a mid-span slat it is the slat's
corner that sits in the rail, not a rail vertex in the slat.

### Falsifiers

Each violates one named budget. All were run on 4.5.11, 5.1.2 and 5.2.1
and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-feet` | named toes plant at z=0 | 16 |
| `--float-stretcher` | stretcher-to-leg BVH gap | 17 |
| `--gap-slats` | slat-to-leg BVH gap | 18 |
| `--narrow-seat` | seat span vs `2·hx` | 19 |
| `--upright-back` | back recline band (measured 0.00°) | 19 |
| `--float-slats` | bearing bite (seat slats 6 mm up; measured −0.00354) | 20 |
| `--split-feet` | legs in one piece (measured 0 of 4) | 21 |

`--short-feet` lifts only the outward toe verts. After recentring, the
bottom of the scroll is the AABB `zmin`, so the AABB gate would still pass.
The named-toe stations fail. `--split-feet` restores the first build: each
foot is an arc stopped short of its post, and each post starts at the arc's
top. The toes still ground and every gap budget still passes. Only the
one-piece budget sees the 14 mm of daylight. `--upright-back` keeps the back
top where it was, so the envelope does not move.

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
blender --background --python park_bench.py -- --upright-back
blender --background --python park_bench.py -- --float-slats
blender --background --python park_bench.py -- --split-feet
blender --background --python park_bench.py -- --output bench.png
```

Smoke passes no flags.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20` and `21` are this piece's own.

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
| 17 | Stretcher-to-leg gap (`--float-stretcher`) |
| 18 | Slat-to-leg gap (`--gap-slats`) |
| 19 | Seat span (`--narrow-seat`) or back recline (`--upright-back`) |
| 20 | Bearing bite on slats and armrests (`--float-slats`) |
| 21 | Legs not bent in one piece from toe to seat (`--split-feet`) |
