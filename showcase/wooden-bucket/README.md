# Wooden bucket

A showcase piece, not an example. Procedural coopered pail (16 staves
with seeded width jitter, a bottom of three boards seated in a croze
above a chime, iron hoops lofted on the stave faces, ear plates and
rings, a three-strand rope bail through the rings) then the shipped pipeline: unique-cell
UVs, Cycles high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

Hoops evaluate the same `host_outer_r` chord as the stave flats.
`--round-band` is the falsifier: a circle of `radius_at(z)` instead of
the chord. The floor follows the inner stave polygon. Ear plates sit on
the outer stave face below the rim; the bail is a semicircle whose ends
pass through the rings and run on below them. `--float-handle` shrinks
that semicircle and lifts it by what it lost, so the envelope stays put
and only the bail-ear gap fails; `--float-bottom` shrinks the floor out
of the croze.

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
| Base triangles | 4000–5800 | 5458 / 5458 / 5458 |
| LOD1 ratio | 0.32–0.62 of base | 0.4998 / 0.4998 / 0.4998 |
| LOD2 ratio | 0.10–0.35 of base | 0.2199 / 0.2199 / 0.2191 |
| Materials | exactly 3 distinct; ≥350 wood, ≥180 metal, ≥40 rope | 3 slots; 1448 / 1020 / 486 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.396, 0.346, 0.534) m ± 0.015 | (0.3957, 0.3462, 0.5338), zmin 0 |
| Collider tris | ≤ 420 | 276 |
| Export | written, size > 0 | 420984 / 420984 / 420976 bytes |

Base triangles rose from **4272 to 4872** in the quality pass: overlapping
identical staves, circular hoops, and a 12-box bail became 16 jittered
staves, chord-seated hoops, a polygonal croze floor, and a round bail
through the ear rings. The second pass took it to **5458**: the bail
became three-strand rope (48 segments of a nine-vertex lobed section,
running on through the rings) and the floor three boards.

DECIMATE COLLAPSE triangle counts are **not** identical across series,
so LOD2 ratios differ slightly between versions. The gate is a ratio band, not an exact
count. Bake pixels are stochastic; the gate is `has_data` plus operator
`FINISHED`, not byte-identity. Stave-width jitter uses fixed seed 17.
Export byte counts differ on 5.2.1 (glTF serializer), not a gated axis.

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
| Bail-ear BVH gap | ≤ 0.006 m | 0.00107 |
| Floor-croze rim BVH gap | ≤ 0.008 m | 0.00474 |
| Bottom boards | 3; every seam 0.0006–0.0025 m | 3; 0.00120 |
| Rope clears the ear plates | 2 plates; 0 rope vertices inside either | 2; 0 |
| Hoop bite (host r − inner hoop r) | 0.0010–0.007 m | 0.00250 |

### Falsifiers

Each violates one named budget. All nine were run on 4.5.11, 5.1.2 and
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
| `--one-piece-bottom` | bottom boards: 3 | 17 |
| `--sunk-rope` | rope clears the ear plates | 17 |

## Rope and ears

The bail was a smooth eight-sided tube in a rope material, and it read as
a plastic hose. It is now laid rope: a three-lobed section turned one
vertex step per ring, so the lobes wind along the bail as strands. The
section's frame is fixed to the bail's plane, so the lay does not jump
where the ends turn vertical.

The ring offset from the ear plate was `RING_MAJOR * 0.25`, which put the
rope's axis 3.25 mm off the plate and its body through it (hidden by the
ring in the old stills). The offset is now sized from the rope's lobes
plus 0.5 mm, and **Rope clears the ear plates** asserts it. `--sunk-rope`
restores the old offset and puts 19 rope vertices inside a plate. The
outer AABB was re-fitted to the honest envelope: 12.5 mm wider across the
ears and 6 mm taller.

## Surface

Every stave and board carries a seeded `PlankTone` and a `GrainDir` (its
own long axis) as face attributes, and `wood_material` stretches grain
along that axis. The hoops, plates and rings are dark rusted iron. The
temp `.glb` is removed once its size is measured.

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
blender --background --python wooden_bucket.py -- --one-piece-bottom
blender --background --python wooden_bucket.py -- --sunk-rope
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
| 17 | Joint fit: bail-ear gap, floor-croze gap, bottom boards and seams, or rope through an ear plate |
| 18 | Seat: hoop bite band (`--round-band`) |
| 19 | Body diameter or height off the stated real-world size |
