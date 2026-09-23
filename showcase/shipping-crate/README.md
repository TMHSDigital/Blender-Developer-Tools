# Shipping crate

A showcase piece, not an example. Procedural crate (skids under the
posts, corner posts with tenoned slats and seeded width jitter, bottom
sills, nailed single-shell L-straps, filleted iron bail handles through
mounting plates seated on one end board each)
then the shipped pipeline: unique-cell UVs, Cycles high-to-low normal
bake, LOD chain, convex collider, Unity glTF export.

Skids sit under the posts so the outer corner is a mortise, not a cave.
Handle bails use quarter-circle corners so a 90-degree loft cannot sit
the bar on the plate.

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
| Base triangles | 2900–3900 | 3388 / 3388 / 3388 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2196 / 0.2196 / 0.2196 |
| Materials | exactly 2 distinct; ≥900 wood, ≥600 metal faces | 2 slots; 1170 / 904 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.146, 0.726, 0.612) m ± 0.015 | (1.1460, 0.7260, 0.6120), zmin 0 |
| Collider tris | ≤ 220 | 116 |
| Export | written, size > 0 | 273816 / 273816 / 273800 bytes |

Base triangles rose from **624 to 2508** in the quality pass: the old
beveled cube with glued-on slats became a post-and-slat crate with
tenons, sills, L-straps, and pipe handles. The second pass took them to
**3388**: single-shell chamfered straps, 24 nails, chamfered mounting
plates.

DECIMATE COLLAPSE triangle counts are **not** guaranteed identical across
series; on this mesh they happen to match (LOD2 744 on all three). The gate is a ratio band, not an exact count.
Bake pixels are stochastic; the gate is `has_data` plus operator
`FINISHED`, not byte-identity. Slat-width jitter uses fixed seed 17.
Export byte counts differ by 16 B on 5.2.1 (glTF serializer), not a
gated axis.

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
| Named supports: 3 skids | each `zmin` ≤ 1e-3 | 3, skid_z 0.00000 |
| Body plan | 1.056 × 0.716 m ± 0.05 | 1.0560 × 0.7160 |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Handle-end BVH gap | ≤ 0.008 m | 0.00000 |
| Slat-post BVH gap | ≤ 0.006 m | 0.00000 |
| Nail seat | 24 nails; bite 0.3–1.0 mm into the strap, head ≥ 1.0 mm proud | 24; 0.60 mm; 1.80 mm |
| Handle plates on one board | each plate inside a single end board with ≥ 4 mm clearance at both edges | 4 plates; 32.4 mm |

### Second pass (straps, nails, handle placement, surface)

The inspection sheet found the iron and the handles built the way
`crate-stack` used to build them:

- **Straps were two unbevelled boxes per corner.** That left a seam line
  down the outer corner, razor edges, and an inner face sitting flush on
  the post face. Each strap is now one L-section extrusion that bites
  `IRON_BITE` into the post. It is chamfered at `IRON_BEVEL` with
  `material=METAL_IDX`, since bevel otherwise hands chamfer faces slot 0.
  Code copied from `crate-stack`, not imported.
- **No fasteners.** Three nail stations per plate, 24 nails, placed from
  each plate's own outer face and normal. `nail_audit` asserts the seat
  band (exit 18, `--float-nails`).
- **The handle mounting plates straddled the gap between two end
  boards.** The handle sat at a fixed 52% of post height, which landed on
  a gap. It now snaps to the centre of the end board nearest that height,
  from the same `_span_layout` the boards come from. `plate_board_audit`
  asserts each plate sits inside one board with clearance at both edges
  (exit 20, `--straddle-handle`, which puts the handle on a gap and
  measures −26.9 mm).
- **Every plank was the same flat tone.** `PlankTone` / `GrainDir` face
  attributes drive a grain-along-the-board wood shader. The iron gets
  rust wear.
- The temp glTF export is removed after it is measured.

The right-angle-edge budget from `crate-stack` is not applied here: the
handle bail's pipe ends are square discs buried in the mounting plates,
so "every box is chamfered" does not hold for this piece.

### Falsifiers

Each violates one named budget. All nine were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-skids` | named skid supports at Z=0 | 16 |
| `--float-handle` | handle-end gap | 17 |
| `--omit-slats` | slat-post seat | 18 |
| `--float-nails` | nail seat band (heads lifted 1.5 mm off the straps) | 18 |
| `--straddle-handle` | handle plates on one end board | 20 |

## Run

```bash
blender --background --python shipping_crate.py --
blender --background --python shipping_crate.py -- --skip-decimate
blender --background --python shipping_crate.py -- --stray-vert
blender --background --python shipping_crate.py -- --lift-z
blender --background --python shipping_crate.py -- --short-skids
blender --background --python shipping_crate.py -- --float-handle
blender --background --python shipping_crate.py -- --omit-slats
blender --background --python shipping_crate.py -- --float-nails
blender --background --python shipping_crate.py -- --straddle-handle
blender --background --python shipping_crate.py -- --output crate.png
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
| 16 | Not grounded: bounding box `zmin` off 0, or a named skid floats |
| 17 | Joint fit: handle-end gap |
| 18 | Seat: slat-post gap, or a nail head off its strap seat band (`--float-nails`) |
| 19 | Body plan off the stated real-world size |
| 20 | A handle mounting plate not seated on a single end board (`--straddle-handle`) |
