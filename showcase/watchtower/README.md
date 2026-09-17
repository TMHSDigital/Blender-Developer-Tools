# Watchtower

A showcase piece, not an example. Procedural timber lookout (corner
posts through a plank platform, lower-bay X-braces, hatch and ladder
whose stiles plant at Z=0, coursed shake roof over a solid cone,
mitered iron collars and shoes) then the shipped pipeline: unique-cell
UVs, Cycles high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

The old roof was a wood U with incomplete shake coverage; rails showed
through the eave. The cone plus non-overlapping courses close the
pyramid. Shoes are added after the zmin snap so a bevel undershoot
cannot lift them.

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
| Base triangles | 6200–8200 | 6408 / 6408 / 6408 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2197 / 0.2197 / 0.2185 |
| Materials | exactly 3 distinct; ≥80 metal, ≥40 roof faces | 3 slots; 300 metal, 126 roof |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.594, 1.594, 2.973) m ± 0.01 | (1.5940, 1.5940, 2.9731), zmin 0 |
| Collider tris | ≤ 180 | 150 |
| Export | written, size > 0 | 464572 / 464572 / 464560 bytes |

Base triangles rose from **5220 to 6408** in the quality pass: a taller
eave-true roof and coursed shakes, not hidden interior faces.

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
| Named supports: 4 iron shoes | each `zmin` ≤ 1e-3 | 4, shoe_z 0.00000 |
| Plan | 1.56 m eave × 2.97 m height ± 0.08 / ± 0.28 | 1.5940 × 2.9731 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Rail-to-post engage | ≥ 0.012 m | 0.0180 |
| Girt-collar standoff | ≤ 0.010 m | 0.00200 |
| Post plumb (XY drift) | ≤ 0.010 m | 0.00000 |

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is leaner on LOD2. The gate is a ratio band, not an exact count.
Bake pixels are stochastic; the gate is `has_data` plus operator
`FINISHED`, not byte-identity. Construction uses no RNG. Export byte
counts differ by 12 B on 5.2.1 (glTF serializer), not a gated axis.

### Falsifiers

Each violates one named budget. All eight were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-shoes` | named shoe supports at Z=0 | 16 |
| `--short-rails` | rail-to-post joint fit | 17 |
| `--float-band` | iron-collar seat | 18 |
| `--rake-posts` | post plumb | 19 |

## Run

```bash
blender --background --python watchtower.py --
blender --background --python watchtower.py -- --skip-decimate
blender --background --python watchtower.py -- --stray-vert
blender --background --python watchtower.py -- --lift-z
blender --background --python watchtower.py -- --short-shoes
blender --background --python watchtower.py -- --short-rails
blender --background --python watchtower.py -- --float-band
blender --background --python watchtower.py -- --rake-posts
blender --background --python watchtower.py -- --output tower.png
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
| 5 | Material count ≠ 3 distinct slots, or metal/roof faces missing |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a named shoe floats |
| 17 | Joint fit: rail-to-post engage |
| 18 | Seat: girt-collar standoff |
| 19 | Post plumb or plan off the stated real-world size |
