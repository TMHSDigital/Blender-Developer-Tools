# Wheelbarrow

A showcase piece, not an example. Procedural wooden wheelbarrow (two
chassis shafts that are the handles, box tray with overlapping floor
slats and walls of stacked boards, iron straps, single flat-tread spoked wheel, rear legs) then the
shipped pipeline: unique-cell UVs, Cycles high-to-low normal bake, LOD
chain, convex collider, Unity glTF export.

The tray walls seat into the floor rather than sitting on top of it, so
a wood bevel cannot open daylight at the joint. Handles are thinner in
Y than the chassis they tenon into. The tyre is a flat felloe wrap, not
a torus.

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
| Base triangles | 2300–2800 | 2536 / 2536 / 2536 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2192 / 0.2192 / 0.2098 |
| Materials | exactly 2 distinct; ≥700 wood, ≥180 metal faces | 2 slots; 1157 / 190 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.558, 0.630, 0.574) m ± 0.015 | (1.5556, 0.6300, 0.5720), zmin 0 |
| Collider tris | ≤ 220 | 90 |
| Export | written, size > 0 | 193036 / 193036 / 193020 bytes |

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
| Named supports: 2 shoes + tyre | each `zmin` ≤ 1e-3 | shoe_z 0.00000, tyre_z 0.00000 |
| Tray size | (0.720, 0.532, 0.220) m ± 0.02 | (0.7200, 0.5320, 0.2200) |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Spoke clearance (hub − spoke) | ≥ 0.010 m | 0.04000 |
| Handle-tray overlap | gap ≤ 0.020 m | −0.07062 |
| Wall-floor seat | ≥ 0.005 m | 0.01200 |
| Metal-wood BVH gap | ≤ 0.010 m | 0.00000 |
| Tread aspect (tyre width / radial) | ≥ 2.5 | 5.111 |
| **Wall boards** | 2 boards per side wall and in the front wall; every seam 0.001–0.004 m | 2 / 2 / 2; 0.00200 |

DECIMATE COLLAPSE triangle counts are **not** identical across series,
so LOD2 ratios differ slightly. The gate is a ratio band, not an exact
count. Bake pixels are stochastic; the gate is `has_data` plus operator
`FINISHED`, not byte-identity. Construction is closed-form; the only RNG
is the seeded per-board wood tone. Bevel inputs are
sorted by edge index, so the face order is the same on every run; a
Python set of edges handed to the bevel had made it vary. Export byte counts differ on 5.2.1
(glTF serializer), not a gated axis.

### Walls, wood and iron

Each tray wall was one plain slab beside a floor of planks, and every
piece was one flat tone. Side and front walls are now two boards
stacked with a 2 mm seam, held by the existing straps; the low rear
wall stays one board. `tray_size` and `wall_floor_seat` now take a side
wall as the union of its boards. **Wall boards** asserts the count and
the seam; `--wide-seams` opens the seams to 8 mm (same boards, same
triangles) and exits 17.

The extra boards cost 324 triangles, which would have broken the
2800 ceiling. They are paid for with faces nobody sees: wall bottoms
buried in the floor and slat undersides no longer get a bevel (faces
beveled on some edges come out n-gons and are split, at the same
triangle count). Base triangles went from 2500 to 2536. Wood has a tone
and grain per board and shaft; the iron is dark and rusted instead of
glossy black. The temp `.glb` is removed after its size is measured.

### Falsifiers

Each violates one named budget. All nine were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-legs` | named shoe supports at Z=0 | 16 |
| `--fat-spokes` | spoke clearance inside the hub | 17 |
| `--float-walls` | wall-floor seat | 17 |
| `--pipe-rim` | tread aspect (torus on a flat felloe) | 18 |
| `--wide-seams` | wall boards (seam band) | 17 |

## Run

```bash
blender --background --python wheelbarrow.py --
blender --background --python wheelbarrow.py -- --skip-decimate
blender --background --python wheelbarrow.py -- --stray-vert
blender --background --python wheelbarrow.py -- --lift-z
blender --background --python wheelbarrow.py -- --short-legs
blender --background --python wheelbarrow.py -- --fat-spokes
blender --background --python wheelbarrow.py -- --float-walls
blender --background --python wheelbarrow.py -- --pipe-rim
blender --background --python wheelbarrow.py -- --wide-seams
blender --background --python wheelbarrow.py -- --output barrow.png
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
| 16 | Not grounded: bounding box `zmin` off 0, or a named shoe/tyre floats |
| 17 | Joint fit: spoke clearance, handle join, wall-floor seat, metal-wood gap, or wall boards and seams |
| 18 | Seat: tread aspect of the tyre |
| 19 | Tray size off the stated real-world dimensions |
