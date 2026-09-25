# Terrain scatter

A showcase piece, not an example. Geometry Nodes sine-hill Mesh Grid
with an Index-jittered Instance-on-Points scatter, realized cubes
replaced by closed-form cleaved, faceted stones seated on sampled dirt Z,
then the shipped pipeline: unique-cell UVs, Cycles high-to-low normal
bake, LOD chain, convex collider, Unity glTF export.

GN still builds the hill, with two closed-form micro-relief terms on top
of the sine, and the instance grid. After realize+slabify, whose rim is
bevelled into the walls, cube islands are deleted and each centroid is
reseated as a sized stone, sunk until the ground closes around it on
every side, then clamped above the slab floor.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `geometry-nodes-python`, `mesh-editing-and-bmesh`,
`bake-high-to-low`, `depsgraph-and-evaluated-data`,
`engine-export-presets`, and snippets `bake_normal_high_to_low.py`,
`setup_bake_target_image.py`, `lod_chain.py` / `decimate_to_budget.py`,
`convex_hull_collider.py`, `export_preset_unity.py` (helpers copied, not
imported as a package). Hygiene combinatorics match
`examples/mesh-hygiene-audit` (copied, not imported).

Intended size: 1.80 m square hill tile, ~0.16 m sine amplitude, nine
embedded stones from cobble to boulder; outer AABB 1.800 × 1.800 ×
0.570 m.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1400–2800 | 2398 / 2398 / 2398 |
| LOD1 ratio | 0.32–0.62 of base | 0.4996 / 0.4996 / 0.4996 |
| LOD2 ratio | 0.10–0.35 of base | 0.2193 / 0.2193 / 0.2193 |
| Materials | exactly 2 distinct, ≥24 stone faces | 2 slots, 720 stone |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.800, 1.800, 0.570) m ± 0.015 | (1.8000, 1.8008, 0.5700), zmin 0 |
| Collider tris | ≤ 120 | 36 |
| Export | written, size > 0 | 199496 / 199496 / 199480 bytes |

Base triangles rose from **1194 to 1758** in the first quality pass: 9-vert hill
became a 21-vert grid, and bevelled cubes became subdiv-2 icospheres.
Outer Z dropped from 0.655 m (crate corners swinging through the slab)
to 0.552 m of seated stone on the hill.

The second pass took them from **1758 to 2398**: the four-segment rim
bevel adds 640. The outer Z moved from 0.584 m to 0.570 m, because the
stones now sink into the ground rather than perch on it, and the
declared size was re-fitted to match. The collider fell from 72 to 36
triangles because it now hulls a coarse, unbevelled 9-vertex tile
(`COLLIDER_GRID`): the chamfer and micro-relief are visual, and on the
full-resolution tile they pushed the hull to 178, over its ceiling.

DECIMATE COLLAPSE triangle counts are **not** guaranteed identical across
series — the gate is a ratio band, not an exact count. This mesh matched
on 4.5.11 / 5.1.2 / 5.2.1. Bake pixels are stochastic; the gate is
`has_data` plus operator `FINISHED`, not byte-identity. Construction uses
no RNG: jitter, cleave planes and relaxation are all closed form or fixed
iteration. Export byte counts differ by 16 B on 5.2.1 (glTF serializer), not
a gated axis.

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
| Stone shells | 9 | 9 |
| Per-stone faces | ≥ 40 | 80 |
| Stone floor `zmin` | ≥ 0.012 m | 0.06946 |
| Seat offset (`zmin` − dirt Z) | ≤ 0.02 m | −0.03326 |
| Interpenetrating stone pairs (BVH overlap) | 0 | 0 |
| Sealed sectors per stone (buried vertex in each of 8) | 8 / 8 | 8 / 8 |
| Stone footprint ratio (largest / smallest) | ≥ 3.0 | 9.812 |
| Rim tilt step between adjacent dirt faces | ≤ 40° | 33.52° |

### Why the stones are cleaved, relaxed and faceted

The committed stones were smooth-shaded, near-white ellipsoids with a
gentle sine bump: eggs or marshmallows on a pale clay slab. Two pairs
also interpenetrated, because the GN scatter jitters by up to 0.22 m on a
0.575 m grid, and no budget compared stone to stone.

- **Cleaved.** Each ellipsoid is cut by `N_CLEAVES` planes whose normals
  and depths come from the stone's own centre, closed form. Every vertex
  beyond a plane is projected onto it, which leaves flat broken faces.
  Stones are shaded flat, because broken rock is faceted; smooth shading
  turned the cleaved stones back into eggs.
- **Scaled.** Cleaving takes about a third off each stone, and at the old
  size they read as pebbles, so every semi-axis is `ROCK_SCALE` = 1.35×.
- **Relaxed.** Stone centres are pushed apart to
  `2 × STONE_R_BOUND + STONE_CLEAR` over a fixed number of symmetric
  passes, and clamped so each stone's bound stays on the tile.
  `STONE_R_BOUND` is derived from `ROCK_SCALE` and the largest semi-axis,
  bump and tilt, so scaling the stones widens the spacing with them. With
  today's numbers the unrelaxed scatter would also clear; the relaxation
  is what keeps that true when the scatter or the sizes change.
- **Materials.** Dark mottled soil and grey weathered stone, with
  roughness and a small bump from fine object-space noise.

### Why the stones are sunk, sized, and the rim is rounded

The second pass inspected the tile in clay, wire, six orthos and
ground-contact close-ups, and found the tile read as a slice of cake
with pebbles dropped on it.

- **Sealed.** Stones were seated by sampling the dirt once, at the
  stone's centre, and biting the lowest point 35 mm below it. On the
  hill's slopes that left daylight under the downhill side: measured
  around each stone in 8 azimuth sectors, no stone had a buried vertex in
  more than 6, two in only 4. Now every vertex samples the ground under
  itself (a ray down onto the dirt, captured before any stone is added),
  and each stone sinks until every sector's most-buried vertex is
  `EMBED_SINK` below it.
- **Sized.** All nine stones were within about 20% of one size, on a
  relaxed 3×3 grid, and the top view read as planted. `STONE_SIZES` gives
  each scatter point a factor from 0.55 to 1.45, boulders among cobbles,
  and the relaxation spaces each pair by the sum of their own bounds.
- **Rounded rim.** The hill met the vertical walls at a knife edge all
  round. The rim is bevelled in four segments, and the budget bounds the
  step in normal elevation between adjacent faces. Elevation, not
  dihedral: at the corners the chamfer strips meet at a right angle in
  plan, which is a rounded corner.
- **Ground, not a sine.** Two closed-form relief terms, 14 mm and 7 mm,
  ride on the hill in the same GN tree. The hill and rim are
  smooth-shaded, because flat shading printed the 21×21 grid on the
  ground; stones and walls stay flat.
- **Materials.** Stones are mid-grey (they were near-white where the key
  hit them), and the dirt darkens toward a subsoil colour below the slab
  lift, in object space, without adding a material.

`stone_overlap_audit` BVH-tests every stone pair. `--pile-rocks` skips
the relaxation and draws the scatter in to 40% so neighbours collide: 7
pairs interpenetrate, and the piece exits 20. Skipping the
relaxation alone would prove nothing, because the cleaved stones miss
each other unrelaxed.

### Falsifiers

Each violates one named budget. All were run on 4.5.11, 5.1.2 and 5.2.1
and returned the same code on each.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | loose vertex count is 0 | 15 |
| `--lift-z` | bounding box `zmin` is 0 | 16 |
| `--poke-rock` | stone floor `zmin` | 17 |
| `--float-rocks` | seat offset vs sampled dirt Z | 18 |
| `--box-rocks` | per-stone face floor | 19 |
| `--pile-rocks` | stone-to-stone interpenetration is 0 | 20 |
| `--perch-rocks` | every stone sealed in 8/8 sectors (measures 3/8) | 21 |
| `--uniform-rocks` | footprint ratio ≥ 3.0 (measures 1.851) | 22 |
| `--sharp-rim` | rim tilt step ≤ 40° (measures 88.50°) | 23 |

## Run

```bash
blender --background --python terrain_scatter.py --
blender --background --python terrain_scatter.py -- --skip-decimate
blender --background --python terrain_scatter.py -- --stray-vert
blender --background --python terrain_scatter.py -- --lift-z
blender --background --python terrain_scatter.py -- --poke-rock
blender --background --python terrain_scatter.py -- --float-rocks
blender --background --python terrain_scatter.py -- --box-rocks
blender --background --python terrain_scatter.py -- --pile-rocks
blender --background --python terrain_scatter.py -- --perch-rocks
blender --background --python terrain_scatter.py -- --uniform-rocks
blender --background --python terrain_scatter.py -- --sharp-rim
blender --background --python terrain_scatter.py -- --output terrain.png
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
| 5 | Material count ≠ 2 distinct slots, or stone faces missing |
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
| 17 | Stone floor poke (`--poke-rock`) |
| 18 | Float above host (`--float-rocks`) |
| 19 | Stone shell faces (`--box-rocks`) |
| 20 | Stone pairs interpenetrate (`--pile-rocks`) |
| 21 | A stone not sealed in every sector (`--perch-rocks`) |
| 22 | Stone footprint ratio below floor (`--uniform-rocks`) |
| 23 | Rim tilt step above ceiling (`--sharp-rim`) |
