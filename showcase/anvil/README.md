# Anvil

A showcase piece, not an example. Procedural London-pattern anvil on a
coopered timber stump (16 jittered staves, chord-lofted iron hoops, a
sawn head, spreading foot, pinched waist, one slotted face with hardy
and pritchel through-holes, oval-lofted horn) then the shipped
pipeline: unique-cell UVs, Cycles high-to-low normal bake, LOD chain,
convex collider, Unity glTF export.

The face is one `add_slotted_slab` so hardy/pritchel are real holes in
a single shell, not nubs glued onto stacked boxes. Hoops evaluate the
same `host_outer_r` chord as the stave flats. `--round-band` is the
falsifier: a circle of `radius_at(z)` instead of the chord.

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
| Base triangles | 2500–4500 | 2988 / 2988 / 2988 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2195 / 0.2195 / 0.2195 |
| Materials | exactly 2 distinct; ≥400 wood, ≥400 metal faces | 2 slots; 1040 / 822 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.621, 0.414, 0.489) m ± 0.015 | (0.6210, 0.4137, 0.4890), zmin 0 |
| Collider tris | ≤ 280 | 134 |
| Export | written, size > 0 | 244052 / 244052 / 244036 bytes |

Base triangles dropped from **6616 to 2988** in the quality pass:
overlapping face boxes and a beveled superellipse horn became one
slotted slab plus a circular oval loft. Hidden coincident faces were
the waste.

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
| Named supports: 16 staves | each `zmin` ≤ 0.001 | 16, stave_z 0.00000 |
| Body plan | 0.621 m long × 0.180 m high ± 0.05 | 0.6210 × 0.1800 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Foot-on-head BVH gap | ≤ 0.006 m | 0.00300 |
| Hoop bite (host r − inner hoop r) | 0.0012–0.008 m | 0.00300 |

### Falsifiers

Each violates one named budget. All six were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-staves` | named stave supports at Z=0 | 16 |
| `--float-anvil` | foot-on-head gap | 17 |
| `--round-band` | hoop bite band | 18 |

## Run

```bash
blender --background --python anvil.py --
blender --background --python anvil.py -- --skip-decimate
blender --background --python anvil.py -- --stray-vert
blender --background --python anvil.py -- --lift-z
blender --background --python anvil.py -- --short-staves
blender --background --python anvil.py -- --float-anvil
blender --background --python anvil.py -- --round-band
blender --background --python anvil.py -- --output anvil.png
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
| 17 | Joint fit: foot-on-head gap (`--float-anvil`) |
| 18 | Seat: hoop bite band (`--round-band`) |
| 19 | Body length or height off the stated real-world size |
