# Tavern stool

A showcase piece, not an example. A procedural tavern stool: a lathed round
seat, turned splayed legs, tenoned stretchers at two heights, and iron
ferrules on level treads. Then the shipped pipeline: unique-cell UVs, a
Cycles high-to-low normal bake, an LOD chain, a convex collider and a Unity
glTF export.

Legs are one loft per leg, not stacked cones. Each foot is an iron ferrule
sleeve on the leg's own axis, its inner wall a named grip (1.2 mm) inside the
leg. The sleeve's raked bottom rim is buried in a level iron tread, and the
leg ends inside the sleeve, above the tread. The first build ended every leg
3 mm above a vertical ring on the floor, with a 1 mm air gap around the foot.
The front-back and side stretchers sit at different heights, so their tenons
do not meet inside the leg. Each member has its own wood tone and grain.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).

## Budgets

Declared as named constants. Every gate **recomputes** its value from the
mesh, materials, UVs, evaluated LOD, collider or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 2750–3350 | 3040 / 3040 / 3040 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2197 / 0.2197 / 0.2197 |
| Materials | exactly 2 distinct; ≥200 wood, ≥48 metal faces | 2 slots; 1168 / 576 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.341, 0.341, 0.470) m ± 0.015 | (0.3406, 0.3406, 0.4700), zmin 0 |
| Collider tris | ≤ 640 | 468 |
| Export | written, size > 0 | 259676 / 259676 / 259668 bytes |

Base triangles rose from **2528 to 3040** in the second quality pass, and the
band moved from 2300–3200 to 2750–3350. Each foot gained a tread, and the
sleeves are walled on both ends. The bake went from 256 px to 1024 px, and
its cage extrusion from 60 mm to 10 mm. See the bake texel budget below.

DECIMATE COLLAPSE triangle counts are **not** identical across series. The
gate is a ratio band, not an exact count. Bake pixels are stochastic; the
gate is `has_data` plus operator `FINISHED`, not byte-identity. Construction
is closed-form and member tones are seeded, so repeated runs on one binary
print identical measurements. Export byte counts may differ by a few bytes
across series.

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
| Named supports: 4 treads (plus 4 sleeves) | each `zmin` ≤ 1e-3 | 8, cup_z 0.00000 |
| Seat | 0.340 m dia × 0.470 m high ± 0.02 | 0.3400 × 0.4700 |

### Joint fit, feet and bake

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Stretcher-leg BVH gap | ≤ 0.008 m | 0.00000 |
| Ferrule grip (exit 18): leg radius where the sleeve wraps it, less the sleeve's inner radius, radially about the leg's own axis; 4 sleeves | 0.0006–0.0025 m | 0.00120 |
| Foot stack (exit 20): leg end above its tread's top / sleeve bottom buried below it; 4 legs, 4 treads | ≥ 0.0005 m / ≥ 0.001 m | 0.00113 / 0.00943 |
| Bake texel density (exit 21): smallest UV cell in baked texels | ≥ 12 px | 22.43 px (1024 px bake) |

At 256 px the bake gave each of the 1,744 UV cells about 6 px. The hero then
sampled the neighbouring cells' normals across cell borders, which showed as
dark slivers on the legs above the ferrules.

### Falsifiers

Each violates one named budget. All were run on 4.5.11, 5.1.2 and 5.2.1 and
returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-legs` | named ferrule supports at Z=0 | 16 |
| `--float-stretchers` | stretcher-leg join | 17 |
| `--pipe-ferrule` | ferrule grip (a pipe ring on the tread; measured −0.00011) | 18 |
| `--sink-legs` | foot stack (leg ends 10 mm into the tread; measured −0.00887) | 20 |
| `--low-bake` | bake texel density (256 px bake; measured 5.61 px) | 21 |

`--pipe-ferrule` keeps the treads, so the triangle band and the envelope
cannot steal its failure. `--sink-legs` keeps the leg inside its sleeve, so
the grip still passes.

## Run

```bash
blender --background --python tavern_stool.py --
blender --background --python tavern_stool.py -- --skip-decimate
blender --background --python tavern_stool.py -- --stray-vert
blender --background --python tavern_stool.py -- --lift-z
blender --background --python tavern_stool.py -- --short-legs
blender --background --python tavern_stool.py -- --float-stretchers
blender --background --python tavern_stool.py -- --pipe-ferrule
blender --background --python tavern_stool.py -- --sink-legs
blender --background --python tavern_stool.py -- --low-bake
blender --background --python tavern_stool.py -- --output stool.png
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
| 16 | Not grounded: bounding box `zmin` off 0, or a named ferrule support floats |
| 17 | Joint fit: stretcher-leg gap |
| 18 | Ferrule grip out of band, or a sleeve missing (`--pipe-ferrule`) |
| 19 | Seat diameter or height off the stated real-world size |
| 20 | Foot stack: leg end below its tread's top, or sleeve not buried (`--sink-legs`) |
| 21 | Bake texel density below floor (`--low-bake`) |
