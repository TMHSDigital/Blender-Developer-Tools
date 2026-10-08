# Terrain scatter

A showcase piece, not an example. Geometry Nodes sine-hill Mesh Grid
with an Index-jittered Instance-on-Points scatter, realized cubes
replaced by closed-form, glacier-worn boulders seated on sampled dirt Z,
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
0.609 m.

**Hero.** The render path dresses the tile as a hand-made meadow diorama.
None of it is part of the asset, its budgets or its export; the dressing
is drawn with a fixed seed, parented to the tile, and the asset sheet
judges `TerrainLow` alone.

- **Soil section.** Render-only point attributes give each dirt vertex
  its depth below the hill surface over it (exact on the vertical walls,
  which are single quads). The cut sides layer down from the hill's own
  top: a turf lip, dark humus with roots, then level horizons in object
  Z on wobbled boundaries: banded ochre clay under a paler loam with the
  odd stone, a cobble bed, and jointed grey bedrock at the foot.
- **Boulders.** Weathered granite: a grey per stone, three scales of
  noise, feldspar and mica speckle, rain streaks on the flanks, crustose
  lichen blotches (grey-green and sulphur, sparse orange) on the
  up-facing stone, moss and a soil stain where it meets the ground, read
  from a render-only height-above-ground attribute.
- **Ground cover.** About 37 000 curved, tapering blades in clumps of
  varied height and hue (a few dry straw blades among the greens); taller
  grass and seed stalks ring each stone, where grazing and mowing miss in
  a real field; a turf lip is combed out and down over the cut edge;
  drifts of ox-eye daisy, buttercup, knapweed and clover; three shrubs
  (juniper, hazel, flowering gorse) placed where they clear the stones,
  the path and each other.
- **Worn path.** A bare-earth foot path with grit meanders across the
  hill. Its closed-form centre line is chosen at render time from a fixed
  candidate set as the one that threads furthest from every stone; the
  soil shader and the dressing share it, so no blade grows on it and the
  pebbles gather along it.
- **Light.** A warm late-afternoon key from camera-left throws the
  boulders' and the grass's shadows across the slope, a cool fill keeps
  every stone face off black, a back rim lifts the grass tips and the
  lip, and the warm wedge lands on the backdrop.

### Why the stones are worn boulders now

The third pass found the stones read as placeholders at 100%: faceted
grey icosphere blobs, one with a pure-black flat face. Glacial erratics,
the boulders strewn across upland meadows, are sub-rounded to
sub-angular blocks of granite or gneiss, rounded by transport in the ice
with a few flat fracture and abrasion faces, lichen on their tops and
moss where they meet the turf.

- **Shape.** Each stone is a quad cube-sphere (4 segments a side for the
  boulders, size factor ≥ 0.9; 3 for the cobbles) pushed out to a
  superellipsoid of exponent `BLOCK_EXP` = 2.6, which squares the
  shoulders into a block, with two closed-form low-frequency lumps of up
  to `LUMP_AMP` = 13% and four shallow cleaves (`CLEAVE_DEPTH` 0.68).
  `STONE_R_BOUND` grows by the superellipsoid's plan bulge and the lump
  amplitude, so the relaxation still spaces the stones by their real
  reach.
- **Shading.** Smooth over the worn body, with edges folding more than
  `STONE_SHARP_DEG` = 48° kept sharp, so the fracture faces keep a crisp
  arris. Flat-shaded, the same stones read as low-poly placeholders.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 2000–3800 | 2986 / 2986 / 2986 |
| LOD1 ratio | 0.32–0.62 of base | 0.4997 / 0.4997 / 0.4997 |
| LOD2 ratio | 0.10–0.35 of base | 0.2197 / 0.2197 / 0.2197 |
| Materials | exactly 2 distinct, ≥24 stone faces | 2 slots, 654 stone |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.800, 1.800, 0.609) m ± 0.015 | (1.8000, 1.8008, 0.6085), zmin 0 |
| Collider tris | ≤ 120 | 54 |
| Export | written, size > 0 | 218868 / 218868 / 218860 bytes (4.5.11 / 5.1.2 / 5.2.1) |

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

The third pass took them from **2398 to 2986**, and the declared band
was re-fitted from 1400–2800 to 2000–3800 around the new count, the same
relative width. The 80-triangle icosphere stones became quad
cube-spheres: 192 triangles for each of the four boulders, 108 for each
of the five cobbles (1308 for the stones, against 720). At 80
triangles a 0.4 m boulder's silhouette showed its facets, and smooth
shading cannot hide a polygonal outline. The outer Z rose from 0.570 m
to 0.609 m: the blocky superellipsoid keeps more of its height than the
cleaved ellipsoid did, and the declared size was re-centred on the
measured 0.6085 m (the ± 0.015 tolerance is unchanged). The collider
rose from 36 to 54 triangles, still under its ceiling of 120, because
the rounder stones put a few more vertices on the hull.

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
| Per-stone faces | ≥ 40 | 54 (cobbles) / 96 (boulders) |
| Stone floor `zmin` | ≥ 0.012 m | 0.08305 |
| Seat offset (`zmin` − dirt Z) | ≤ 0.02 m | −0.03775 |
| Interpenetrating stone pairs (BVH overlap) | 0 | 0 |
| Sealed sectors per stone (buried vertex in each of 8) | 8 / 8 | 8 / 8 |
| Stone footprint ratio (largest / smallest) | ≥ 3.0 | 9.757 |
| Rim tilt step between adjacent dirt faces | ≤ 40° | 33.52° |

### Why the stones are cleaved, relaxed and faceted

The committed stones were smooth-shaded, near-white ellipsoids with a
gentle sine bump: eggs or marshmallows on a pale clay slab. Two pairs
also interpenetrated, because the GN scatter jitters by up to 0.22 m on a
0.575 m grid, and no budget compared stone to stone.

- **Cleaved.** Each ellipsoid is cut by `N_CLEAVES` planes whose normals
  and depths come from the stone's own centre, closed form. Every vertex
  beyond a plane is projected onto it, which leaves flat broken faces.
  The first pass shaded them flat, because smooth shading turned the
  cleaved ellipsoids back into eggs; the third pass replaced them with
  blocky superellipsoids that hold their shape smooth-shaded (above).
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
  ground; the walls stay flat (the stones were flat until the third pass).
- **Materials.** Stones are mid-grey (they were near-white where the key
  hit them), and the dirt darkens toward a subsoil colour below the slab
  lift, in object space, without adding a material.

`stone_overlap_audit` BVH-tests every stone pair. `--pile-rocks` skips
the relaxation and draws the scatter in to 40% so neighbours collide: 8
pairs interpenetrate (7 with the second pass's stones), and the piece
exits 20. Skipping the relaxation alone proved nothing in the second
pass, because the cleaved stones missed each other unrelaxed.

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
| `--perch-rocks` | every stone sealed in 8/8 sectors (measures 4/8) | 21 |
| `--uniform-rocks` | footprint ratio ≥ 3.0 (measures 2.317) | 22 |
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
| 26 | Gallery asset-quality violation (render path; the floors' 11 is remapped here) |
