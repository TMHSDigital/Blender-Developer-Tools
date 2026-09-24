# Wall torch

A showcase piece, not an example. A procedural wall-mounted torch sconce: a
running-bond dressed-stone plaque with dark mortar joints, an iron wall
plate bolted to the stones, a level iron arm, an open iron cup, a leaning
wooden haft with a pitch wrap, and upright emissive flames. Then the shipped
pipeline: unique-cell UVs, a Cycles high-to-low normal bake, an LOD chain, a
convex collider and a Unity glTF export.

The plaque back sits on the wall plane Y=0 with zmin at 0. The plate's seat
comes from the face of the facing stones (`stone_face_y()`), a named bite
into it. The cup's mid-height is the arm's height, so the arm is level by
construction. It runs from inside the plate into the cup's wall. The cup
sits on the haft's axis, which leans 15° out from the wall. The haft stands
on the cup's floor and runs up into the wrap. The flames stand upright from
the wrap, whatever the haft does.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`,
`procedural-materials-and-shaders`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: a 0.28 m wide, 0.40 m tall plaque; the cup centre 0.24 m out
from the wall; the flame tip 0.48 m above the floor. Outer AABB
0.304 × 0.322 × 0.485 m.

## Budgets

Declared as named constants. Every gate **recomputes** its value from the
mesh, materials, UVs, evaluated LOD, collider or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1800–2250 | 2004 / 2004 / 2004 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2196 / 0.2196 / 0.2196 |
| Materials | exactly 5 distinct; ≥24 stone, ≥24 metal, ≥8 flame, ≥10 pitch | 5 slots; 540 stone, 318 metal, 50 wood, 180 flame, 60 pitch |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.304, 0.322, 0.485) m ± 0.015 | (0.3040, 0.3218, 0.4845), zmin 0 |
| Collider tris | ≤ 180 | 116 |
| Export | written, size > 0 | 164408 / 164408 / 164384 bytes |

Base triangles rose from **1528 to 2004** in the second quality pass, and the
band moved from 1400–1700 to 1800–2250. The solid cup became an open, walled
cup with a drip boss. The 26 mm haft stub became a 0.20 m haft with a wrap.
The three flame cones became lathed teardrops. The envelope grew from
0.293 m to 0.322 m in depth and from 0.424 m to 0.485 m in height, because
the torch now stands up out of its cup.

DECIMATE COLLAPSE triangle counts are **not** identical across series. The
gate is a ratio band, not an exact count. Bake pixels are stochastic; the
gate is `has_data` plus operator `FINISHED`, not byte-identity. Construction
is closed-form and stone tones are seeded, so repeated runs on one binary
print identical measurements. Export byte counts differ by 24 B on 5.2.1
(glTF serializer), not a gated axis.

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

### Joint fit, seat and bake

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Arm-to-cup BVH gap | ≤ 0.008 m | 0.00007 |
| Plate-to-stone BVH gap | ≤ 0.008 m | 0.00057 |
| Plaque width vs `WALL_W` | ± 0.04 m | 0.2800 vs 0.280 |
| Arm level (exit 20): the arm shell's long axis against horizontal | ≤ 1.0° | 0.000° |
| Plate seat (exit 21): plate front proud of the facing stones / plate back into their face | ≥ 0.008 m / 0.001–0.005 m | 0.01300 / 0.00300 |
| Bake texel density (exit 22): smallest UV cell in baked texels | ≥ 12 px | 27.71 px (1024 px bake) |

The plate-to-stone gap is measured to any stone shell. The plate is bolted to
the face of the stones, not to the backing slab behind them, as it was in the
first build.

### Falsifiers

Each violates one named budget. All were run on 4.5.11, 5.1.2 and 5.2.1 and
returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--float-arm` | arm-to-cup BVH gap | 17 |
| `--float-plate` | plate-to-stone BVH gap (measured 0.07700) | 18 |
| `--skinny-plaque` | plaque width vs `WALL_W` | 19 |
| `--droop-arm` | arm level (the old 20 mm drop; measured 9.580°) | 20 |
| `--sink-plate` | plate seat (the first build's seat; measured proud −0.00400, seat 0.02000) | 21 |
| `--low-bake` | bake texel density (256 px bake; measured 6.93 px) | 22 |

`--float-arm` shortens the tube to 55 % of the plate-to-cup station vector,
and the cup stays put. `--float-plate` moves only the plate off the stones;
the arm root stays at the seated plate, so 17 still passes.
`--skinny-plaque` scales the back plaque and courses to 0.55 · `WALL_W`.

## Run

```bash
blender --background --python wall_torch.py --
blender --background --python wall_torch.py -- --skip-decimate
blender --background --python wall_torch.py -- --stray-vert
blender --background --python wall_torch.py -- --lift-z
blender --background --python wall_torch.py -- --float-arm
blender --background --python wall_torch.py -- --float-plate
blender --background --python wall_torch.py -- --skinny-plaque
blender --background --python wall_torch.py -- --droop-arm
blender --background --python wall_torch.py -- --sink-plate
blender --background --python wall_torch.py -- --low-bake
blender --background --python wall_torch.py -- --output torch.png
```

Smoke passes no flags.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20`–`22` are this piece's own.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 5 distinct slots, or stone/metal/flame/pitch faces missing |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Hygiene (`--stray-vert` lands here) |
| 16 | Grounded zmin (`--lift-z`) |
| 17 | Arm-to-cup gap (`--float-arm`) |
| 18 | Plate-to-stone gap (`--float-plate`) |
| 19 | Plaque width (`--skinny-plaque`) |
| 20 | Arm not level (`--droop-arm`) |
| 21 | Plate not seated on the stone face (`--sink-plate`) |
| 22 | Bake texel density below floor (`--low-bake`) |
