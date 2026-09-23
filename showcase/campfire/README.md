# Campfire

A showcase piece, not an example. Procedural campfire (two-course
running-bond ring of 14 rounded fieldstones per course, pit-floor
cobbles, ash with embers,
a kissing log tripod that overshoots a shared apex ring, floor logs,
and charcoal) then the shipped pipeline: unique-cell UVs, Cycles
high-to-low normal bake, LOD chain, convex collider, Unity glTF export.

Courses share a Z plane; `--gap-courses` is the falsifier. Teepee axes
aim at a ring of radius `(STICK_R * 0.55) / sin(π/N)` and overshoot so
the caps cross; `--float-logs` inflates that ring.

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
| Base triangles | 1400–3600 | 2760 / 2760 / 2760 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 / 0.5000 / 0.4993 |
| LOD2 ratio | 0.10–0.35 of base | 0.2196 / 0.2196 / 0.2196 |
| Materials | exactly 3 distinct; ≥80 wood, ≥24 ash, ≥200 stone | 3 slots; 216 / 48 / 1416 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.807, 0.808, 0.404) m ± 0.015 | (0.8024, 0.8022, 0.4037), zmin 0 |
| Collider tris | ≤ 360 | 162 |
| Export | written, size > 0 | 231952 / 231952 / 231944 bytes |

Base triangles dropped from **3616 to 2200** in the quality pass: the
old piece stacked identical boxes with a mortar gap and a teepee that
met at one point. The rebuild is two seated courses plus crossing
sticks; hidden overlapping volume went away. The second pass took it to
**2760**: each stone is now a lofted, chamfered lump instead of a
four-sided wedge.

DECIMATE COLLAPSE triangle counts are **not** guaranteed identical across
series — the gate is a ratio band, not an exact count. Bake pixels are
stochastic; the gate is `has_data` plus operator `FINISHED`, not
byte-identity. Stone-width jitter uses fixed seed 17; each stone's
shape draws from its own seeded generator. glTF byte size differs on
5.2.1.

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
| Named supports: 14 bottom stones | each `zmin` ≤ 0.001 | 14, stone_z 0.00000 |
| Ring plan | 0.807 m dia × 0.176 m high ± 0.04 | 0.8023 × 0.1759 |
| **Stone variation** (exit 20) | per course, spread of stone outer radius, and of crown height on the top course, each ≥ 0.006 m | 0.01269 (smallest spread) |

### Joint fit and seat

| Axis | Declared | Measured (all three) |
| --- | --- | --- |
| Teepee kiss (BVH nearest at caps) | ≤ 0.008 m | 0.00034 |
| Course seat (upper zmin − lower zmax) | abs ≤ 0.004 m | 0.00000 |

### Stones, wood and ash

The ring was 28 identical curved bricks: flat tops, flat faces, one
height, one grey. It read as a concrete kerb. Each stone is now a
chamfered octagon section lofted along its span, swelling to a seeded
belly mid-stone and pinched and capped at the ends, with a seeded
radial offset and outer-face wobble. Top-course stones get a seeded
domed crown. The beds stay flat, and the bottom course's crown stays at
the bed height, so the upper course still seats (course seat 0.00000).
The stated ring height rose from 0.156 to 0.176 m for the crowns.

**Stone variation** asserts the ring is not one stone repeated.
`--uniform-stones` gives every stone the same draw — each jitter at its
upper bound, so the ring keeps the envelope of its widest seeded stone
and only this budget fails (exit 20, spread 0.00000).

Stone is isotropic mottling, speckle and pitting with a seeded tone per
stone (`stone-archway`'s recipe, reading `PieceTone`); sticks and logs
carry their own tone and grain along their axis; the ash has sparse
ember glow. The temp `.glb` is removed after its size is measured.

### Falsifiers

Each violates one named budget. All seven were run on 4.5.11, 5.1.2 and
5.2.1 and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--short-stones` | named bottom-course supports at Z=0 | 16 |
| `--float-logs` | teepee kiss | 17 |
| `--gap-courses` | course seat | 18 |
| `--uniform-stones` | stone variation | 20 |

## Run

```bash
blender --background --python campfire.py --
blender --background --python campfire.py -- --skip-decimate
blender --background --python campfire.py -- --stray-vert
blender --background --python campfire.py -- --lift-z
blender --background --python campfire.py -- --short-stones
blender --background --python campfire.py -- --float-logs
blender --background --python campfire.py -- --gap-courses
blender --background --python campfire.py -- --uniform-stones
blender --background --python campfire.py -- --output campfire.png
```

Smoke passes no flags.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family; `20` is file-local.

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
| 16 | Not grounded: bounding box `zmin` off 0, or a named bottom stone floats |
| 17 | Joint fit: teepee kiss (`--float-logs`) |
| 18 | Seat: course gap (`--gap-courses`) |
| 19 | Ring diameter or height off the stated real-world size |
| 20 | Stone variation: the ring stones are identical (`--uniform-stones`) |
