# Wheelbarrow

A showcase piece, not an example. Procedural wooden wheelbarrow (two
shafts that are the handles, each one timber from grip to axle; a
flared hopper tray with overlapping floor slats and walls of stacked
boards; iron straps; a single flat-tread spoked wheel; rear legs) then
the shipped pipeline: unique-cell UVs, Cycles high-to-low normal bake,
LOD chain, convex collider, Unity glTF export.

The tray walls seat into the floor rather than sitting on top of it, so
a wood bevel cannot open daylight at the joint. The tyre is a flat
felloe wrap, not a torus.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).

Intended size: a 1.56 m long barrow, 0.59 m across the tray top, 0.58 m
to the top of the raked front board; the tray is 0.94 m long at its top
edge and 0.22 m deep.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 2300–2800 | 2440 / 2440 / 2440 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2197 / 0.2197 / 0.2057 |
| Materials | exactly 2 distinct; ≥700 wood, ≥180 metal faces | 2 slots; 1085 / 214 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.563, 0.594, 0.577) m ± 0.015 | (1.5630, 0.5938, 0.5773), zmin 0 |
| Collider tris | ≤ 220 | 80 |
| Export | written, size > 0 | 185652 / 185652 / 185636 bytes |

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
| Tray size | (0.939, 0.578, 0.225) m ± 0.02 | (0.9393, 0.5783, 0.2247) |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Spoke clearance (hub − spoke) | ≥ 0.010 m | 0.05210 |
| Wall-floor seat (inner bottom edge, lowest board of each wall) | ≥ 0.005 m | 0.00800 |
| Metal-wood BVH gap | ≤ 0.010 m | 0.00000 |
| Tread aspect (tyre width / radial) | ≥ 2.5 | 5.111 |
| **Wall boards** | 2 boards per side wall and in the front wall; every seam 0.001–0.004 m, measured up the wall's own plane | 2 / 2 / 2; 0.00207–0.00231 |

### Form

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| **Shaft runs**: wood shells unbroken from behind the tray to past its front | exactly 2 | 2 |
| **Tray flare / rake**, from the boards' own faces | side ≥ 10°, front ≥ 20° | 15.00° / 30.00° |

DECIMATE COLLAPSE triangle counts are **not** identical across series,
so LOD2 ratios differ slightly. The gate is a ratio band, not an exact
count. Bake pixels are stochastic; the gate is `has_data` plus operator
`FINISHED`, not byte-identity. Construction is closed-form; the only RNG
is the seeded per-board wood tone. Bevel inputs are
sorted by edge index, so the face order is the same on every run; a
Python set of edges handed to the bevel had made it vary. Export byte counts differ on 5.2.1
(glTF serializer), not a gated axis.

### Why the frame is two timbers and the tray a hopper

The second pass found the barrow read as a crate on legs. The frame was
three boxes per side: a handle that stopped at the tray's rear corner, a
level run hidden exactly under the side wall (both at 0.255 m from the
centreline), and a fork that started at the front corner and turned
in a 50° V to the hub. From outside, the tray carried everything. The
tray itself was a square box, and a spreader between the forks stood
inside the wheel, touching neither fork. The iron straps ran 12 mm above
the wall tops.

- **Shafts.** Each shaft is one mitred sweep through the grip, the tray's
  rear, its front and the axle. It narrows in plan the whole way (0.27 m
  at the grips, 0.19 and 0.15 m under the tray, 0.038 m at the hub), so
  it shows under the tray and reads as one piece of wood. The legs and a
  stretcher hang from it, and a bearer under the tray front, its ends
  buried in the shafts, replaces the spreader.
- **Hopper.** The tray is built from a bottom outline and a top outline:
  sides flared 15°, the front raked 30° out over the wheel for tipping,
  the low rear leaning back 12°. Each wall is the planar band between
  its bottom and top edges; the end boards are housed half a board into
  the sides, and the sides run past the ends' outer faces.
- **Measured in the wall's plane.** A leaning board's outer face sits
  lower than its inner one, so AABB tests lie: a Z seam reads negative
  and a zmin seat reads deep. Seams are measured along each wall's own
  up direction, and the seat on each wall's lowest board's inner face,
  both taken from the boards' own faces.
- **Straps** follow the flared wall and stop 10 mm below its top.

`WALL_SEAT` went from 12 mm to 8 mm: a raked board's outer bottom edge
sits `WALL_T·sin(RAKE)` below its inner one, and at 12 mm it would have
broken through the underside of the 22 mm floor. The handle-join budget
is gone, because the handle no longer joins anything: it is the shaft.
The shaft-run budget replaces it. Base triangles went from 2536 to 2440,
and the collider from 90 to 80.

### Walls, wood and iron

Side and front walls are two boards stacked with a 2 mm seam, held by
the straps; the low rear wall stays one board. **Wall boards** asserts
the count and the seam; `--wide-seams` opens the seams to 8 mm (same
boards, same triangles) and exits 17. Faces nobody sees get no bevel:
wall bottoms buried in the floor and slat undersides. Wood has a tone
and grain per board and shaft; the iron is dark and rusted. The temp
`.glb` is removed after its size is measured.

### Falsifiers

Each violates one named budget. All eleven were run on 4.5.11, 5.1.2
and 5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-legs` | named shoe supports at Z=0 | 16 |
| `--fat-spokes` | spoke clearance inside the hub | 17 |
| `--float-walls` | wall-floor seat (measures −0.00691 m) | 17 |
| `--pipe-rim` | tread aspect (torus on a flat felloe) | 18 |
| `--wide-seams` | wall boards (seam band) | 17 |
| `--split-shafts` | two unbroken shaft runs (measures 0) | 20 |
| `--box-tray` | tray flare / rake (measures 0° / 0°) | 21 |

`--box-tray` stands every wall vertical on the flared tray's top
outline, so the envelope and the tray-size budget stay put and only the
flare gate can fail.

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
blender --background --python wheelbarrow.py -- --split-shafts
blender --background --python wheelbarrow.py -- --box-tray
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
| 17 | Joint fit: spoke clearance, wall-floor seat, metal-wood gap, or wall boards and seams |
| 18 | Seat: tread aspect of the tyre |
| 19 | Tray size off the stated real-world dimensions |
| 20 | A shaft is not one timber from grip to axle (`--split-shafts`) |
| 21 | Tray flare or front rake under its floor (`--box-tray`) |
