# Water trough

A showcase piece, not an example. Procedural staved water trough on a
timber stand (watertight U-hull, U end-caps, contained water, iron
straps, trestle legs) then the shipped pipeline: unique-cell UVs, Cycles
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

The hull, ends, straps and water all sample the same YZ arc. End caps
are U-boards the staves tenon into, not a bounding-box slab around the
U. Straps sit at `STRAP_X`, offset from `LEG_X`, so the trestle does not
punch through the iron. Stretchers span the inner faces of the legs.
`--round-band` is not used; `--float-strap` is the seat falsifier.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: 1.08 m tray length, 0.44 m across the U, 0.50 m overall
height; outer AABB 1.093 × 0.552 × 0.504 m.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 3300–4000 | 3700 / 3700 / 3700 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 / 0.2200 / 0.2200 |
| Materials | exactly 3 distinct; ≥24 wood, ≥24 metal, ≥6 water | 3 slots; 1674 / 156 / 29 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.093, 0.552, 0.504) m ± 0.01 | (1.0932, 0.5520, 0.5040), zmin 0 |
| Collider tris | ≤ 80 | 64 |
| Export | written, size > 0 | 268840 / 268840 / 268824 bytes |

Base triangles rose from **2484 to 3700** in the quality pass: box end
slabs and a single extruded U became ten jittered staves, U end-caps,
continuous straps offset from the legs, and stretchers that meet the
inner faces.

DECIMATE COLLAPSE triangle counts are **not** identical across series —
the gate is a ratio band, not an exact count. Bake pixels are
stochastic; the gate is `has_data` plus operator `FINISHED`, not
byte-identity. Stave-width jitter uses closed-form `sin(i)`, no RNG.
Export byte counts differ by 16 B on 5.2.1 (glTF serializer), not a
gated axis.

The hull-size budget (exit 19) runs **before** the outer AABB budget
(exit 8) so `--narrow-hull` is not swallowed by a moved bounding box.

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
| Named supports: 4 shoes | each `zmin` ≤ 0.001 | 4, shoe_z 0.00000 |
| Hull plan | 1.08 m × 0.44 m ± 0.08 | 1.0448 × 0.4661 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| End-cap rim Z-span | ≤ 0.080 m | 0.0050 |
| Strap-to-hull BVH gap | ≤ 0.008 m | 0.00000 |
| Water-to-hull BVH gap | ≤ 0.008 m | 0.00260 |

### Falsifiers

Each violates one named budget. All seven were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-legs` | named shoe supports at Z=0 | 16 |
| `--box-ends` | end-cap rim span | 17 |
| `--float-strap` | strap-to-hull gap | 18 |
| `--narrow-hull` | hull plan vs stated size | 19 |

`--short-legs` lifts the shoes only, so AABB `zmin` stays 0 (the legs
still plant) and the named-support gate is what fires.

## Run

```bash
blender --background --python water_trough.py --
blender --background --python water_trough.py -- --skip-decimate
blender --background --python water_trough.py -- --stray-vert
blender --background --python water_trough.py -- --lift-z
blender --background --python water_trough.py -- --short-legs
blender --background --python water_trough.py -- --box-ends
blender --background --python water_trough.py -- --float-strap
blender --background --python water_trough.py -- --narrow-hull
blender --background --python water_trough.py -- --output trough.png
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
| 16 | Not grounded: bounding box `zmin` off 0, or a named shoe floats |
| 17 | Joint fit: end-cap U-rim span (`--box-ends`) |
| 18 | Seat: strap or water BVH gap (`--float-strap`) |
| 19 | Hull length or width off the stated real-world size (`--narrow-hull`) |
