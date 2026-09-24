# Market stall

A showcase piece, not an example. Procedural timber stall (corner posts
with wrap plinths, slatted counter and shelf, back-wall planks, side
braces that run post to post, striped awning with a front roller and
hanging valance) then the shipped pipeline: unique-cell UVs, Cycles
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

The old piece used capped foot cubes coplanar with the post bottoms and
counter-leg pads coplanar with the legs, which z-fought at Z=0. Wrap
plates stand off the post; counter legs go to Z=0 without a second
bottom face.

The side braces used to start at the back post and stop at mid-depth,
0.43 m short of the front post, nearly level and joined to nothing at
the front: in the side elevation they read as pegs hanging in the air.
The audit that should have caught it never did, because a level brace
fails its brace shape test and was never measured. Each brace now runs
from the front post, just above the counter, up to the back post under
the header, so the side bay is triangulated; the brace-in-post seat
below asserts both ends. Wood carries grain and a tone per piece
(`PlankTone` / `GrainDir` face attributes), and the awning is a matte
canvas with faint dirt, not two flat paints.

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
| Base triangles | 3900–5200 | 4324 / 4324 / 4324 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2197 / 0.2197 / 0.2197 |
| Materials | exactly 3 distinct; ≥16 faces per stripe slot | 3 slots; 34 / 34 stripe faces |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.389, 1.011, 1.740) m ± 0.01 | (1.3892, 1.0107, 1.7402), zmin 0 |
| Collider tris | ≤ 80 | 58 |
| Export | written, size > 0, removed after measuring | 312400 / 312400 / 312376 bytes |

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
| Named supports: 4 wrap feet | each `zmin` ≤ 1e-3 | 4, foot_z 0.00000 |
| Frame plan | 1.36 × 0.92 m ± 0.04 | 1.3600 × 0.9200 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Brace-vs-counter overlap | ≤ 1e-6 m³ | 0.000000 |
| Brace-in-post seat: 2 side braces, each end past the post's inner face | ≥ 0.020 m | 0.0418 |
| Header-post tenon engage | ≥ 0.4 × tenon | 0.0595 |
| Awning-on-header seat | −0.002–0.010 m | 0.00378 |
| Post plumb (XY drift) | ≤ 0.008 m | 0.00000 |

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. Bake pixels are
stochastic; the gate is `has_data` plus operator `FINISHED`, not
byte-identity. Construction uses no RNG; the per-piece wood tone is
drawn from a seeded `random.Random(TONE_SEED)`, the same every run. Export
byte counts differ by series (glTF serializer), not a gated axis.

### Falsifiers

Each violates one named budget. Every falsifier was run on 4.5.11,
5.1.2 and 5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-feet` | named wrap-foot supports at Z=0 | 16 |
| `--low-brace` | brace-vs-counter overlap | 17 |
| `--short-brace` | brace-in-post seat (front end stops at mid-depth, -0.4181 m) | 17 |
| `--float-awning` | awning-on-header seat | 18 |
| `--rake-posts` | post plumb | 19 |

## Run

```bash
blender --background --python market_stall.py --
blender --background --python market_stall.py -- --skip-decimate
blender --background --python market_stall.py -- --stray-vert
blender --background --python market_stall.py -- --lift-z
blender --background --python market_stall.py -- --short-feet
blender --background --python market_stall.py -- --low-brace
blender --background --python market_stall.py -- --short-brace
blender --background --python market_stall.py -- --float-awning
blender --background --python market_stall.py -- --rake-posts
blender --background --python market_stall.py -- --output stall.png
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
| 5 | Material count ≠ 3 distinct slots, or stripe faces missing |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Mesh hygiene: loose, non-manifold, zero-area, doubles, n-gons, z-fight |
| 16 | Not grounded: bounding box `zmin` off 0, or a named wrap foot floats |
| 17 | Joint fit: brace occupying the counter volume, or a side brace not seated in both posts |
| 18 | Seat: awning-on-header gap |
| 19 | Post plumb or frame plan off the stated real-world size |
