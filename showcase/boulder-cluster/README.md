# Boulder cluster

A showcase piece, not an example, and the third in the `nature` category.
It builds a procedural, game-ready cluster of glacial erratics on a patch
of ground:

- four boulders of clearly different sizes, each an ellipsoid cut by
  closed-form cleavage planes. The cuts are rounded off by a weathering
  bevel, a soft minimum in the radial field, so the flat faces meet in
  worn edges rather than knife edges. Seeded corner chips and a seeded sum
  of waves roughen them;
- a 1.7 m granite block, pale and speckled with black biotite and milky
  quartz crystals, its crevices darkened and its edges worn pale;
- a sandstone boulder split in two along a crack. The halves stand 75 mm
  apart. Both are cut from one field, so their crack faces match, and the
  bedding bands run straight across the gap. The crack faces are fresh
  rock, paler and unweathered. The bedding weathers out as shallow ledges
  on the flanks;
- a 0.95 m granite boulder in front, with a 0.6 m sandstone slab resting
  flat on its top: the slab's underside is a cleavage plane parallel to
  the granite's top face, dropped until its deepest vertex bites 10 mm in;
- 26 lichen crusts (sage, grey-green and orange Xanthoria) and 8 moss
  cushions on the tops and north faces;
- a soil mound with drifts banked against every boulder's foot, 32 grass
  tufts (one growing in the crack), 36 pebbles and 14 wildflowers (oxeye,
  buttercup, harebell) in the gaps and round the bases.

Every draw comes from `random.Random(SEED)` in `plan_cluster()`, before
anything is built: the boulders' waves and chips, the growth patches, and
the candidate spots for every tuft, pebble and flower. Which candidates
are used is decided against the default layout alone (`Layout`,
`finish_layout`). No flag draws from the stream or changes the layout, so
a falsifier changes only what it names.

Eight materials, one per substance: granite, sandstone, lichen, moss,
grass, soil (glacial till), gravel and flower. A `Cavity` point attribute,
computed from the finished rock mesh, darkens crevices and paler convex
edges. A `Strata` point attribute, the position along the bed normal in
the boulder's own frame, draws the sandstone bands; both halves share it,
so the bands match across the crack. A `Zone` face attribute marks the
crack faces, the rings of each crust and cushion, grass tips and the flower
parts; every boulder, crust, cushion, blade, pebble and flower has a seeded
`Tone`. Everything is smooth-shaded; every material boundary and every fold
sharper than 60° is a hard edge.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a mound 4.44 × 3.22 m, the granite block's top 1.37 m off
the ground. The outer AABB is 4.444 × 3.215 × 1.366 m. The soil sets X and
Y, a moss cushion on the block's crown the top. The soil's underside is
the ground. The collider is the convex hull of the five rocks alone,
coarse: players walk through grass.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 39600–40900 | 40244 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 8 distinct; ≥4000 granite, ≥3400 sandstone, ≥1960 lichen, ≥1580 moss, ≥4700 grass, ≥2460 soil, ≥1750 gravel, ≥1260 flower faces | 8 slots; 4440 / 3798 / 2184 / 1760 / 5251 / 2734 / 1944 / 1400 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (4.4442, 3.2153, 1.3657) m ± 0.01 | (4.4442, 3.2153, 1.3657), zmin 0 |
| Collider tris (rock hull) | ≤ 320 | 292 |
| Export | written, size > 0, removed after measuring | 3064548 bytes |

No falsifier changes the triangle count or the envelope: every falsifier
run measured 40244 tris and the default's outer AABB to the tenth of a
millimetre.

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. The plan is seeded and nothing else is random; the
geometry is pure Python math. Two default runs print identical
measurements.

### Hygiene

Recomputed from the generated mesh, not asserted about the script.

| Axis | Declared | Measured |
| --- | --- | --- |
| Non-manifold edges | 0 | 0 |
| Loose verts / edges | 0 / 0 | 0 / 0 |
| Doubles merged at 1e-5 | 0 | 0 |
| Zero-area faces | 0 | 0 |
| N-gons | 0 | 0 |
| Coplanar cross-shell face pairs (KD range 0.05 m, plane ε 1e-4) | 0 | 0 |
| Grounded: `zmin` | within 1e-4 of 0 | 0.0000 |

The coplanar budget did most of the work on this piece. The first draft
measured 14 pairs: lichen laid on the smooth radial field sat a fixed
height off it, but the shipped rock is chords of that field, up to 4 mm
inside it on the bevels. Every crust and cushion point is now snapped to
the built rock mesh. That left pairs on the sandstone, where the bedding
ledges are parallel terraces a few millimetres apart; the ledges now fade
out on bedding-plane tops, and growth on sandstone keeps to its tops. A
domed crust still met a rock face now and then, because a skin tilted
against the rock can land on the plane of a face on a nearby bevel. The
crusts are now even skins, parallel to the faces under them, which on a
convex patch of rock cannot reach the plane of any other face. Crust thicknesses and bites are staggered
0.5 mm apart, so two crusts pushed together by a falsifier cannot share a
plane either.

A ray onto a non-planar quad lands on whichever diagonal the tree picks,
and on the soil berms the two differ by centimetres: one grass blade was
rooted by one tree and measured 16 mm off the ground by the other. Each
soil cell is now split on its short diagonal where it is built.

### Embedding, the stacked slab, the split and the growth

These are the organic invariants. A boulder field has no joinery. What
makes it read as one is that every boulder is sunk into the ground rather
than set down on it, that the slab rests on the boulder under it and
would not topple, that the split halves were once one stone, and that
lichen and moss grow where the sun does not bake them.

| Axis | Declared | Measured |
| --- | --- | --- |
| Embedding: per boulder (the granite block, each half, the front boulder), per 45° sector about its plan centroid, the deepest flank vertex (at least 0.6 of the sector's reach from the centroid) under the soil straight above it (a ray down onto the soil shell alone); and the deepest vertex of all | every sector ≥ 0.030 m; deepest ≤ 0.30 m | shallowest sector 0.0686 m (the block); deepest 0.1488 m |
| Slab seat: the slab's deepest vertex inside the front boulder, straight down | 0.004–0.030 m | 0.0100 |
| Slab balance: the slab's volume centroid inside the plan hull of its footprint (every vertex within 12 mm of its lowest gap to the boulder under it) | ≥ 0.03 m inside | 0.1571 (263 footprint vertices) |
| Split: the crack faces of each half (faces within 0.15 m of the other half and facing it): the angle between their area-weighted normals, the gap between them along that normal, their slide across it, and their areas | ≤ 3.0°; gap 0.050–0.100 m; slide ≤ 0.05 m; each ≥ 0.25 m² | 1.00°; 0.0775 m; 0.0092 m; 0.747 / 0.729 m² |
| Growth: of the lichen and moss top faces (facing away from the rock under them), the area fraction whose normal faces up (z > 0.35) or north into the shade (y > 0.5) | 26 crusts, 8 cushions, ≥ 0.85 | 26, 8; 0.9614 |
| Ground cover rooted: soil, grass blades, pebbles, flower stems, leaves, discs and petals, unioned by BVH overlap | every shell joined to the soil | 497 shells; 0 loose |

Each boulder is bedded where it is laid out: the builder raises or sinks
it until its shallowest flank sector is 70 mm under the analytic soil,
and the split halves are bedded as one unit. The budget reads the bed
back off the shipped soil mesh by raycast. The slab is seated the same
way, against the front boulder as that run built it, so a falsifier that
moves the boulder carries the slab with it. The balance budget is the
tip-over check: a slab resting only on its edge has a footprint whose
hull misses its own centre of mass.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. None moves the envelope: every run measured the
same outer AABB and triangle count as the default, and every other budget
stayed green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--perch-boulder` | embedding (the front boulder raised 90 mm off its bed: shallowest sector −0.0151 m, deepest vertex 0.0086 m) | 17 |
| `--float-slab` | slab seat (the slab lifted 20 mm off the front boulder: deepest vertex −0.0100 m) | 18 |
| `--perch-slab` | slab balance (the slab slid 0.36 m south across the boulder's top and re-seated: centroid 0.1170 m outside its 41-vertex footprint) | 19 |
| `--skew-half` | split halves matching (the east half turned 6° about Z at its crack: faces 6.65° apart) | 20 |
| `--sunny-lichen` | growth on up- and shade-facing surfaces (every crust turned by one rotation onto south faces: 0.6243) | 21 |
| `--float-cover` | ground cover rooted (every blade, pebble and flower lifted 30 mm: 475 of 497 shells loose) | 22 |

`--perch-boulder` carries the slab with the boulder, so the slab still
seats 10 mm deep and balances; only the embedding fails. `--float-slab`
keeps the slab's footprint (read relative to its lowest gap), so balance
still passes. `--perch-slab` re-seats the slab at the same 10 mm bite, so
the seat passes and only the balance fails. `--skew-half` turns the half
about its crack's own centre, so the gap (0.0779 m) and slide (0.0102 m)
stay in band and the half stays bedded. `--sunny-lichen` moves the crusts
only: a moss cushion on the block's crown is the top of the envelope, and
moving it would move the box. It uses one rigid rotation for every crust,
so crusts that were apart stay apart. `--float-cover` leaves 22 of the
largest pebbles still touching, sunk deeper than 30 mm.

## Run

```bash
blender --background --python boulder_cluster.py --
blender --background --python boulder_cluster.py -- --skip-decimate
blender --background --python boulder_cluster.py -- --stray-vert
blender --background --python boulder_cluster.py -- --lift-z
blender --background --python boulder_cluster.py -- --perch-boulder
blender --background --python boulder_cluster.py -- --float-slab
blender --background --python boulder_cluster.py -- --perch-slab
blender --background --python boulder_cluster.py -- --skew-half
blender --background --python boulder_cluster.py -- --sunny-lichen
blender --background --python boulder_cluster.py -- --float-cover
blender --background --python boulder_cluster.py -- --output cluster.png
```

Smoke passes no flags.

The hero keeps the piece unturned (`HERO_YAW_DEG` 0°) and looks in from
the south-south-west, a little above the block's top. The granite block
stands on the left, the split boulder on the right with its crack running
straight away from the camera, so the gap reads as a dark slot, and the
front boulder and its slab sit between them. The fill is 0.797 × 0.800.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene, grounding, contact and balance family. `20`–`22` are file-local.
`23` is the asset-quality floor on the render path:
`check_asset_quality` returns 11, which this piece already spends on the
collider ceiling, so the call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or the boulder or soil shells not found |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 8 distinct slots, or a face-count floor missed |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Mesh hygiene: loose, non-manifold, zero-area, doubles, n-gons, coplanar cross-shell pairs |
| 16 | Not grounded: bounding box `zmin` off 0 (`--lift-z`) |
| 17 | Embedding: a boulder's flank sector under 0.030 m into the soil, or a vertex deeper than 0.30 m (`--perch-boulder`) |
| 18 | Slab seat: the slab's deepest vertex in the boulder under it outside 0.004–0.030 m (`--float-slab`) |
| 19 | Slab balance: the slab's mass centre less than 0.03 m inside its footprint (`--perch-slab`) |
| 20 | Split: crack faces more than 3° apart, gap outside 0.050–0.100 m, slide above 0.05 m, or a face under 0.25 m² (`--skew-half`) |
| 21 | Growth: not 26 crusts and 8 cushions, or under 0.85 of their top area facing up or north (`--sunny-lichen`) |
| 22 | Ground cover: a grass, pebble or flower shell not joined to the soil (`--float-cover`) |
| 23 | Asset-quality floor (render path only; remapped from 11) |
