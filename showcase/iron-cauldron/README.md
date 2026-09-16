# Iron cauldron

A showcase piece, not an example. Procedural hanging cauldron (lathed
iron pot with a rolled rim, pipe bail through vertical ear rings, timber
tripod tenoned into a turned crown, iron ferrule cups coaxial with the
poles) then the shipped pipeline: unique-cell UVs, Cycles high-to-low
normal bake, LOD chain, convex collider, Unity glTF export.

Ferrules are lofted along the pole axis and shifted so the downhill rim
sits at Z=0. A world-Z bucket lets a leaning pole slice the lip.
`ferrule_bite` is measured in that same frame, and only samples wood
inside the cup's own axis span — a pole hovering above the well cannot
fake a seat.

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
| Base triangles | 2800–4200 | 3664 / 3664 / 3664 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 / 0.2200 / 0.2200 |
| Materials | exactly 2 distinct; ≥80 wood, ≥200 metal faces | 2 slots; 224 / 1768 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.987, 0.961, 0.860) m ± 0.015 | (0.9866, 0.9605, 0.8600), zmin 0 |
| Collider tris | ≤ 280 | 250 |
| Export | written, size > 0 | 287916 / 287916 / 287904 bytes |

Base triangles rose from **3388 to 3664** in the quality pass: coaxial
ferrule cups and a dual-wall lathe with a rolled rim replaced the old
cone-tripod / overlapping-torus construction.

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
| Named supports: 3 ferrules | each `zmin` ≤ 1e-3 | 3, cup_z 0.00000 |
| Pot size | 0.355 m dia × 0.334 m high ± 0.04 | 0.3545 × 0.3340 |
| Pot–leg clearance | ≥ 0.04 m | 0.0464 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Hook-bail BVH gap | ≤ 0.010 m | 0.00000 |
| Ferrule bite (pole r − inner wall, pole frame) | −0.006–0.000 m | −0.00185 |

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. Bake pixels are
stochastic; the gate is `has_data` plus operator `FINISHED`, not
byte-identity. Construction uses no RNG. Export byte counts differ by
12 B on 5.2.1 (glTF serializer), not a gated axis.

### Falsifiers

Each violates one named budget. All seven were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-legs` | named ferrule supports at Z=0 | 16 |
| `--float-hook` | hook-bail gap | 17 |
| `--pipe-ferrule` | ferrule bite (pole starts above the well) | 18 |

## Run

```bash
blender --background --python iron_cauldron.py --
blender --background --python iron_cauldron.py -- --skip-decimate
blender --background --python iron_cauldron.py -- --stray-vert
blender --background --python iron_cauldron.py -- --lift-z
blender --background --python iron_cauldron.py -- --short-legs
blender --background --python iron_cauldron.py -- --float-hook
blender --background --python iron_cauldron.py -- --pipe-ferrule
blender --background --python iron_cauldron.py -- --output cauldron.png
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
| 3 | Mesh did not build / no UV layer / pot clips tripod |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a named ferrule floats |
| 17 | Joint fit: hook-bail gap |
| 18 | Seat: ferrule bite band |
| 19 | Pot diameter or height off the stated real-world size |
