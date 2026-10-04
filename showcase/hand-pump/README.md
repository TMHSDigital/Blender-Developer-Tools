# Hand pump

A showcase piece, not an example. Procedural cast-iron village hand
pump (stepped wooden plinth, a turned lower barrel with a moulded foot and
a cast spout boss, a fluted upper barrel socketed through a moulded
collar, 6-gon gooseneck tube from the lower-column radius, a stuffing-box
head under a domed cap and ball finial, a handle whose tail runs past the
fulcrum to a counterweight ball, a turned wooden grip, and a coopered
bucket with two iron hoops on the ground under the spout) then the
shipped pipeline: unique-cell UVs, Cycles high-to-low
normal bake, LOD chain, convex collider, Unity glTF export.

The column stays on the origin; only zmin is snapped. The gooseneck is
a tube about named stations on the lower-column radius, not a chain of
cylinders. The flange and the plinth cap bite their hosts so stacked
caps are not coplanar.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: ~1.05 m village pump, 0.34 m plinth, 0.76 m column,
0.15 m bucket; outer AABB 0.610 × 0.521 × 1.055 m.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.2.1; 5.1.2 not re-run after the model pass) |
| --- | --- | --- |
| Base triangles | 900–2600 | 2412 / 2412 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2197 / 0.2181 |
| Materials | exactly 2 distinct, ≥48 metal, ≥24 wood | 2 slots, 1134 metal / 332 wood |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.610, 0.521, 1.055) m ± 0.015 | (0.6100, 0.5210, 1.0545), zmin 0 |
| Collider tris | ≤ 220 (source turns the bucket at 8 staves, no hoops) | 205 |
| Export | written, size > 0 | 202576 bytes (5.2.1) |

The model pass took the pump from **1064 to 2412** triangles and raised
the ceiling **2200 → 2600**. Two lighting-and-paint passes had left it the
plainest object in its asset sheet: a smooth two-step column on a box. It
now carries the cast detail a village pump has: a turned lower barrel with
a moulded foot and a spout boss, eight flutes on the upper barrel, a
moulded collar at the socket, a domed cap and ball finial on the head, a
rolled drip lip on the nozzle, a counterweighted tail on the handle, and a
turned grip. A coopered bucket with two iron hoops stands under the spout,
clear of the plinth. The spout's reach grew 0.13 → 0.17 m (`SPOUT_R`) so
the nozzle clears the plinth and falls inside the bucket mouth. The outer
AABB grew in y (0.382 → 0.521 m) for the bucket and in z (1.052 → 1.055 m)
for the finial. The collider stays under its 220 ceiling because its
source turns the bucket at 8 staves without hoops (`BUCKET_PROXY_SEGS`); at
16 staves the hull ran to 267, past Unity's 255 convex-collider limit. The
foot (0.068 m) and spout boss (0.067 m) stay within `COL_R_TOL` of
`COL_R_LO`, so the column-radius budget still reads the barrel. The flange
classifier now also requires a shell centred on the column axis: the
bucket's lower hoop is as wide and as low as the flange, and would
otherwise mask `--float-flange`. The new **bucket** budget gets its own
falsifier, `--shift-bucket` (exit 20).

Earlier, base triangles dropped from **1164 to 1064** in the quality pass: seven
sausage cylinders became one gooseneck tube, and the wood grip is no
longer beveled with the plinth. Outer AABB is 0.610 × 0.382 × 1.052 m
(was 0.610 × 0.364 × 1.049 m).

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is slightly leaner on LOD2. The gate is a ratio band, not an
exact count. Bake pixels are stochastic; the gate is `has_data` plus
operator `FINISHED`, not byte-identity. Construction is closed-form;
the only RNG is the seeded per-piece wood tone. Bevel inputs are sorted by edge index, so the face order is the same on
every run; a Python set of edges handed to the bevel had made it vary.
Export byte counts differ on 5.2.1 (glTF serializer), not a gated axis.

### Surface and stage

The quality pass found no geometric defect: every joint checked in the
inspection sheet (spout root, flange bolts, head and handle pivot,
column step, plinth) seats as the joint budgets say. The defects were
on the surface. The iron was polished metal (metallic 1.0, roughness
0.38) and read as chrome; the next pass painted it near-black, which
vanished into the dark stage. It is now dark green enamelled cast iron
with rust in the pores and at the edges, and a cool rim light aimed at the
column lifts its silhouette off the backdrop. The plinth slabs and the handle grip carry their
own wood tone and grain. The stage grid grew from 14 to 60 m, because
the wall's left edge showed in the corner of the hero. The temp `.glb`
is removed after its size is measured. With no new geometric defect,
there is no new budget.

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
| Plinth `zmin` | within 1e-4 of 0 | 0.00000 |

### Joint fit and column

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Spout-to-column BVH gap | ≤ 0.008 m | 0.00239 |
| Flange-to-plinth BVH gap | ≤ 0.008 m | 0.00600 |
| Lower-column radius vs `COL_R_LO` | ± 0.008 m (widest barrel shell, the moulded foot) | 0.06800 |
| **Bucket under the spout** | one bucket; nozzle (axis + lip radius) inside the mouth by ≥ 0.015 m; bucket zmin within 1e-4 of 0; ≥ 0.004 m clear of the plinth | catch 0.01900; zmin 0; clear 0.02200 |

### Falsifiers

Each violates one named budget. All were run on 4.5.11 and 5.2.1 after the
model pass and returned the same code on each (5.1.2 not re-run).

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--float-spout` | spout-to-column BVH gap | 17 |
| `--float-flange` | flange-to-plinth BVH gap | 18 |
| `--skinny-col` | lower-column radius | 19 |
| `--shift-bucket` | bucket under the spout | 20 |

## Run

```bash
blender --background --python hand_pump.py --
blender --background --python hand_pump.py -- --skip-decimate
blender --background --python hand_pump.py -- --stray-vert
blender --background --python hand_pump.py -- --lift-z
blender --background --python hand_pump.py -- --float-spout
blender --background --python hand_pump.py -- --float-flange
blender --background --python hand_pump.py -- --skinny-col
blender --background --python hand_pump.py -- --shift-bucket
blender --background --python hand_pump.py -- --output hand-pump.png
```

Smoke passes no flags.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`20` are the
hygiene and joint-fit family.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 2 distinct slots, or wood/metal faces missing |
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
| 16 | Grounded zmin / plinth (`--lift-z`) |
| 17 | Spout-to-column gap (`--float-spout`) |
| 18 | Flange-to-plinth gap (`--float-flange`) |
| 19 | Column radius (`--skinny-col`) |
| 20 | Bucket under the spout (`--shift-bucket`) |
| 21 | Gallery asset-quality violation (render path; the floors' 11 is remapped here) |
