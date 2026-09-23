# Wooden barrel

A showcase piece, not an example. Procedural wine-cask (20 staves with
seeded width jitter, heads of four boards seated in a croze below a
chime, iron hoops lofted on the stave faces, a bung) then the shipped pipeline: unique-cell
UVs, Cycles high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

Hoops evaluate the same `host_outer_r` chord as the stave flats.
`--round-band` is the falsifier: a circle of `radius_at(z)` instead of
the chord, which is what made the old capped cylinder float off every
face. Heads follow the inner stave polygon, not a circle, so they fill
the croze instead of leaving triangular slots at every joint. Each head
is that outline cut across into four boards with a 1.5 mm seam, so the
seat is unchanged and the head no longer reads as a lid.

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
| Base triangles | 6000–8500 | 7312 / 7312 / 7312 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2199 / 0.2199 / 0.2199 |
| Materials | exactly 2 distinct; ≥400 wood, ≥200 metal faces | 2 slots; 2584 / 1440 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.722, 0.714, 0.880) m ± 0.015 | (0.7220, 0.7142, 0.8800), zmin 0 |
| Collider tris | ≤ 400 | 238 |
| Export | written, size > 0 | 552456 / 552456 / 552440 bytes |

Base triangles rose from **4312 to 7216** in the quality pass: 12 identical
staves with 5 mm daylight and circular hoops became 20 jittered staves,
8-ring bulge, chord-seated hoops, polygonal croze heads, and a bung.
Cutting each head into four boards added 96 more (7312).

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. Bake pixels are
stochastic; the gate is `has_data` plus operator `FINISHED`, not
byte-identity. Stave-width jitter uses fixed seed 17. Export byte counts
differ by 16 B on 5.2.1 (glTF serializer), not a gated axis.

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
| Named supports: 20 staves | each `zmin` ≤ 0.001 | 20, stave_z 0.00000 |
| Body plan | 0.714 m dia × 0.880 m high ± 0.04 | 0.7142 × 0.8800 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Head-croze rim BVH gap | ≤ 0.010 m | 0.00710 |
| Head boards | 4 per head; every seam 0.0008–0.003 m | 4 + 4; 0.00150 |
| Hoop bite (host r − inner hoop r) | 0.0012–0.008 m | 0.00300 |

### Falsifiers

Each violates one named budget. All seven were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-staves` | named stave supports at Z=0 | 16 |
| `--float-head` | head-croze gap | 17 |
| `--round-band` | hoop bite band | 18 |
| `--one-piece-head` | head boards: 4 per head | 17 |

## Surface

The staves were one flat tone and the hoops bright polished steel. Each
stave and each head board now carries a seeded `PlankTone` and a
`GrainDir` (its own long axis) as face attributes. `wood_material`
stretches grain along that axis, so it runs up the curved staves and
across the head boards. The hoops are dark rusted iron, the same recipe as
`shipping-crate`. The temp `.glb` is removed once its size is measured.

## Run

```bash
blender --background --python wooden_barrel.py --
blender --background --python wooden_barrel.py -- --skip-decimate
blender --background --python wooden_barrel.py -- --stray-vert
blender --background --python wooden_barrel.py -- --lift-z
blender --background --python wooden_barrel.py -- --short-staves
blender --background --python wooden_barrel.py -- --float-head
blender --background --python wooden_barrel.py -- --round-band
blender --background --python wooden_barrel.py -- --one-piece-head
blender --background --python wooden_barrel.py -- --output barrel.png
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
| 15 | Mesh hygiene: loose, non-manifold, zero-area, doubles, n-gons, z-fight |
| 16 | Not grounded: bounding box `zmin` off 0, or a named stave floats |
| 17 | Joint fit: head-croze gap (`--float-head`), or head boards and seams (`--one-piece-head`) |
| 18 | Seat: hoop bite band (`--round-band`) |
| 19 | Body diameter or height off the stated real-world size |
