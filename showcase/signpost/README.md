# Signpost

A showcase piece, not an example. Procedural timber fingerboard
signpost (square post, pyramidal cap from the post half plus overhang,
three axis-aligned painted boards lettered with their destinations,
with wedges cut from the board section, iron shoe collar and U-wrap straps) then the shipped
pipeline: unique-cell UVs, Cycles high-to-low normal bake, LOD chain,
convex collider, Unity glTF export.

Boards are yaw 0. Finger tips are wedges whose base is the board's own
thickness×height, bitten into the board so the base face is inside it.
The cap is added after the post bevel. The post stays on the origin.
Hygiene family 15–19: `--stray-vert`, `--lift-z` / `--short-shoe`,
`--gap-board`, `--float-strap`, `--yaw-boards`.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: 1.48 m post, boards 0.62 m, 0.54 m and 0.46 m, 0.118 m post
stock; outer AABB 1.260 × 0.142 × 1.551 m.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 320–480 | 432 / 432 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.4537 |
| LOD2 ratio | 0.10–0.35 of base | 0.2176 / 0.1620 |
| Materials | exactly 3 distinct, ≥24 metal, ≥12 board, ≥12 wood | 3 slots, 126 metal, 33 board, 60 wood |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.260, 0.142, 1.551) m ± 0.015 | (1.2600, 0.1420, 1.5510), zmin 0 |
| Collider tris | ≤ 180 | 44 |
| Export | written, size > 0 | 38668 / 38740 / 38740 bytes (4.5.11 / 5.1.2 / 5.2.1) |

Base triangles dropped from **504 to 376** in the quality pass: glued
diamond cubes and a solid shoe block became wedges and a four-plate
collar. Outer AABB tightened from 1.368 × 0.201 × 1.566 m.

DECIMATE COLLAPSE triangle counts are **not** identical across series —
5.2.1 is leaner on LOD1 and LOD2. The gate is a ratio band, not an
exact count. Bake pixels are stochastic; the gate is `has_data` plus
operator `FINISHED`, not byte-identity. Construction is closed-form;
the only RNG is the seeded per-piece wood tone. Bevel inputs are sorted
by edge index, so the face order is the same on every run. Export byte
counts differ on 5.2.1 (glTF serializer), not a gated axis.

### Surface and stage

The quality pass found no geometric defect: the boards, straps, bands
and shoe seat as their budgets say. The defects were surface. The finger
boards were flat pale yellow; they are now cream paint worn through to
the wood by a noise mask, a shade apart per board. The iron read as
chrome (metallic 1.0, roughness 0.38) and is now rusted. The post has its
own tone and grain. The stage grid grew from 14 to 60 m, because the
wall's left edge showed in the corner of the hero. The temp `.glb` is
removed after its size is measured. With no new geometric defect, there
is no new budget.

The second pass added a third finger (FORD, 0.46 m, pointing back the
way of the first, below the other two) so the post reads as a crossroads,
and painted each board's destination and distance on its front face.
The lettering is surface: a 5×7 bitmap font painted into a small image
covering the boards in object space, cubic-filtered and thresholded so
the pixel glyphs round into brush strokes, masked to the front (−Y)
faces and worn through with the paint. The third board moved the
budgets it should: base triangles 376 → 432 (inside the declared
320–480), metal faces 108 → 126 for its collar, board faces 22 → 33,
collider 52 → 56 tris, and `boards` in the joint audit 2 → 3. The outer
AABB is unchanged: the new board is shorter than both the others and
sits between existing bands. Every falsifier still exits its code.

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
| Named shoe plates | ≥1, each `zmin` ≤ 0.002 | 4, 0.00000 |

### Joint fit and orthogonal boards

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Board-to-post BVH gap | ≤ 0.008 m | 0.00500 |
| Strap-to-post BVH gap | ≤ 0.008 m | 0.00300 |
| Board AABB Y (axis-aligned) | ≤ 0.055 m | 0.0280 |

### Falsifiers

Each violates one named budget. All were run on 4.5.11, 5.1.2 and 5.2.1
and returned the same code on each; after the second pass they were
re-run on 4.5.11 and 5.2.1 and still do.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-shoe` | named shoes plant at z=0 | 16 |
| `--gap-board` | board-to-post BVH gap | 17 |
| `--float-strap` | strap-to-post BVH gap | 18 |
| `--yaw-boards` | board AABB Y (orthogonal) | 19 |

`--short-shoe` lifts only the iron shoe plates. After zmin snap the
post is the AABB `zmin`, so the AABB gate would still pass; the named
shoe stations fail. `--gap-board` moves the board inner station outside
the post. `--float-strap` adds Y offset to the U-wrap so it no longer
bites. `--yaw-boards` restores a 0.12 rad yaw; the AABB secondary
extent exceeds the thickness bound.

## Run

```bash
blender --background --python signpost.py --
blender --background --python signpost.py -- --skip-decimate
blender --background --python signpost.py -- --stray-vert
blender --background --python signpost.py -- --lift-z
blender --background --python signpost.py -- --short-shoe
blender --background --python signpost.py -- --gap-board
blender --background --python signpost.py -- --float-strap
blender --background --python signpost.py -- --yaw-boards
blender --background --python signpost.py -- --output signpost.png
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
| 5 | Material count ≠ 3 distinct slots, or wood/board/metal faces missing |
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
| 16 | Grounded zmin / named shoes (`--lift-z`, `--short-shoe`) |
| 17 | Board-to-post gap (`--gap-board`) |
| 18 | Strap-to-post gap (`--float-strap`) |
| 19 | Board yaw / AABB Y (`--yaw-boards`) |
| 20 | Gallery asset-quality violation (render path; the floors' 11 is remapped here) |
