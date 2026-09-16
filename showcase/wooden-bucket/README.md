# Wooden bucket

A showcase piece, not an example. Procedural coopered pail (16 staves
with seeded width jitter, a bottom seated in a croze above a chime,
iron hoops lofted on the stave faces, ear plates and rings, a round
rope bail through the rings) then the shipped pipeline: unique-cell
UVs, Cycles high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

Hoops evaluate the same `host_outer_r` chord as the stave flats.
`--round-band` is the falsifier: a circle of `radius_at(z)` instead of
the chord. The floor follows the inner stave polygon. Ear plates sit on
the outer stave face below the rim; the bail is a semicircle whose ends
pass through the rings. `--float-handle` shrinks that semicircle so the
bar sits on the ring; `--float-bottom` shrinks the floor out of the croze.

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
| Base triangles | 4000–5800 | 4872 / 4872 / 4872 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2196 / 0.2196 / 0.2188 |
| Materials | exactly 3 distinct; ≥350 wood, ≥180 metal, ≥40 rope | 3 slots; 1424 / 1020 / 208 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.383, 0.346, 0.527) m ± 0.015 | (0.3832, 0.3462, 0.5271), zmin 0 |
| Collider tris | ≤ 420 | 302 |
| Export | written, size > 0 | 378296 / 378296 / 378276 bytes |

Base triangles rose from **4272 to 4872** in the quality pass: overlapping
identical staves, circular hoops, and a 12-box bail became 16 jittered
staves, chord-seated hoops, a polygonal croze floor, and a round bail
through the ear rings.

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is 4 tris leaner on LOD2. The gate is a ratio band, not an exact
count. Bake pixels are stochastic; the gate is `has_data` plus operator
`FINISHED`, not byte-identity. Stave-width jitter uses fixed seed 17.
Export byte counts differ by 20 B on 5.2.1 (glTF serializer), not a
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
| Named supports: 16 staves | each `zmin` ≤ 0.001 | 16, stave_z 0.00000 |
| Body plan | 0.335 m dia × 0.360 m high ± 0.04 | 0.3349 × 0.3600 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Bail-ear BVH gap | ≤ 0.006 m | 0.00125 |
| Floor-croze rim BVH gap | ≤ 0.008 m | 0.00458 |
| Hoop bite (host r − inner hoop r) | 0.0010–0.007 m | 0.00250 |

### Falsifiers

Each violates one named budget. All seven were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-staves` | named stave supports at Z=0 | 16 |
| `--float-handle` | bail-ear gap | 17 |
| `--float-bottom` | floor-croze gap | 17 |
| `--round-band` | hoop bite band | 18 |

## Run

```bash
blender --background --python wooden_bucket.py --
blender --background --python wooden_bucket.py -- --skip-decimate
blender --background --python wooden_bucket.py -- --stray-vert
blender --background --python wooden_bucket.py -- --lift-z
blender --background --python wooden_bucket.py -- --short-staves
blender --background --python wooden_bucket.py -- --float-handle
blender --background --python wooden_bucket.py -- --float-bottom
blender --background --python wooden_bucket.py -- --round-band
blender --background --python wooden_bucket.py -- --output bucket.png
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
| 5 | Material count ≠ 3 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a named stave floats |
| 17 | Joint fit: bail-ear gap or floor-croze gap |
| 18 | Seat: hoop bite band (`--round-band`) |
| 19 | Body diameter or height off the stated real-world size |
