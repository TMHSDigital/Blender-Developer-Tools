# Tavern stool

A showcase piece, not an example. Procedural tavern stool (lathed round
seat, turned splayed legs, tenoned stretchers, iron ferrule cups) then
the shipped pipeline: unique-cell UVs, Cycles high-to-low normal bake,
LOD chain, convex collider, Unity glTF export.

Legs are one loft per leg, not stacked cones. Ferrules are vertical cups
the foot drops into; wood ends above the cup so a splayed cone does not
sawtooth through the wall. Stretchers are classified as compact rails,
not the seat disc.

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
| Base triangles | 2300–3200 | 2528 / 2528 / 2528 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2199 / 0.2199 / 0.2199 |
| Materials | exactly 2 distinct; ≥200 wood, ≥48 metal faces | 2 slots; 1168 / 256 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.341, 0.341, 0.470) m ± 0.015 | (0.3400, 0.3400, 0.4700), zmin 0 |
| Collider tris | ≤ 640 | 396 |
| Export | written, size > 0 | 215912 / 215912 / 215900 bytes |

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
| Named supports: 4 ferrule cups | each `zmin` ≤ 1e-3 | 4, cup_z 0.00000 |
| Seat | 0.340 m dia × 0.470 m high ± 0.02 | 0.3400 × 0.4700 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Stretcher-leg BVH gap | ≤ 0.008 m | 0.00000 |
| Ferrule inner clearance (`r_wood − r_in`) | −0.005 .. 0.000 m | −0.00125 |

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. Bake pixels are
stochastic; the gate is `has_data` plus operator `FINISHED`, not
byte-identity. Construction uses no RNG. Export byte counts may differ
by a few bytes across series.

### Falsifiers

Each violates one named budget. All seven were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-legs` | named ferrule cups at Z=0 | 16 |
| `--float-stretchers` | stretcher-leg join | 17 |
| `--pipe-ferrule` | ferrule inner-clearance band | 18 |

## Run

```bash
blender --background --python tavern_stool.py --
blender --background --python tavern_stool.py -- --skip-decimate
blender --background --python tavern_stool.py -- --stray-vert
blender --background --python tavern_stool.py -- --lift-z
blender --background --python tavern_stool.py -- --short-legs
blender --background --python tavern_stool.py -- --float-stretchers
blender --background --python tavern_stool.py -- --pipe-ferrule
blender --background --python tavern_stool.py -- --output stool.png
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
| 16 | Not grounded: bounding box `zmin` off 0, or a named ferrule cup floats |
| 17 | Joint fit: stretcher-leg gap |
| 18 | Seat: ferrule inner-clearance band |
| 19 | Seat diameter or height off the stated real-world size |
