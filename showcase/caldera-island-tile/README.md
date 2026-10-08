# Caldera island tile

A showcase piece, not an example, in the `terrain` category. It builds a
procedural, game-ready strategy-game map tile: a disc 2.40 m across with a
volcanic island in the middle and the sea out to its rim on every side. The
island is a stratovolcano whose summit has collapsed into a caldera, with a
crater lake in it and a young cinder cone standing in the lake as an island.

- **The tile.** A triangle lattice stretched radially onto the disc carries
  the island, the seabed and the rim; a skirt drops straight from the outline
  to a flat base at Z = 0, the ground in section. The rim is a flat band
  40 mm wide, 18 mm over the water, its outer arris chamfered down to one
  canonical edge height (0.163 m) all the way round, so any neighbouring sea
  tile meets this one flush. The seabed shoals up to the rim over 70 mm.
- **The volcano.** A concave stratocone (its profile, before the gullies,
  falls about 37° under the rim and 26° on the lower flank), furrowed by fifteen barrancos and finer erosion
  rills in the loose ash under the rim. Its summit is gone: a caldera 0.72 m
  across (its rim wobbling round an ellipse, with chutes down its inner wall)
  holds a lake 0.22 m over the sea, the rim's lowest pass 73 mm over the
  water. The inner
  walls show the cone's stacked lava, scoria and tuff beds, with sulphur
  stains low down where the fumaroles were. Two parasitic cinder cones sit on
  the outer flanks.
- **The cinder cone.** Built to Porter's (1972) cinder-cone ratios: height
  0.18 and crater 0.40 of the base width, so its flanks stand at 31°, inside
  the 30–33° that loose scoria rests at ([Porter's
  ratios](https://mssanz.org.au/MODSIM07/papers/21_s46/StudyOfVolcanic_s46_Parrot_.pdf)).
  It is 0.27 m across at the waterline, its crater on its axis, and wooded
  with small conifers, like Wizard Island in Crater Lake, which stands 233 m
  over a lake in a 10 km caldera with a crater 90 m across ([Crater
  Lake](https://en.wikipedia.org/wiki/Crater_Lake)).
- **The lava flow.** From a breached spatter cone on the front flank a
  channelled aa flow runs down to the sea between two levees, 72–128 mm wide
  down the flank (a channel about a third of the flow's width, as in a
  channelled flow on Etna: a 16 m channel in a 52 m flow, levees 7 m high,
  [Etna channel study](https://www.earth-prints.org/handle/2122/5726?mode=full)). Its surface is
  read off the ground along its line and held falling the whole way; it fans
  out over the small delta it has built and runs on under the sea. The
  channel is still incandescent in a few thin, broken cracks near the vent
  and black before the sea. A black-sand beach lies either side of the delta.
- **Zoning.** The flanks are zoned by height the way a wet volcanic island
  is: forest and meadow on the lowland, conifers above, heath, then bare ash
  to the rim, ochre on the spurs and red-brown scoria down the gullies.
- **The sea.** A rippled sheet at a declared level of 0.150 m over every
  lattice triangle that holds water, from under the shore out to under the
  rim, turquoise over the shelf round the island and deep blue to the rim,
  steep off the sea cliffs under the back-left flank and off the delta's
  front. A foam line lies at the waterline round the coast, from one side of
  the delta round to the other, its land edge tucked under the beach.
- **Rocks.** Seven fractured crags on the caldera's rim, eight volcanic bombs
  on the ash and fourteen boulders on the shore, half of them on the black
  beach, sealed all round and held apart.

Every seeded draw comes from `random.Random(SEED)` in `plan_scene()`, before
anything is built: where each tree and rock stands and its size, tone and
turn, the ripple and the foam's phases. The ground is closed-form in plan
position. No flag draws from the stream, so a falsifier changes only what it
names.

The volcano rises out of the shore's plateau rather than on top of it, so the
coast is where the shore's rise starts from the sea's level and the ground
meets the water exactly there. The caldera is the smooth minimum of the
cone's flank and an inner wall that steepens from the floor's edge to the
rim; the cinder cone is the smooth minimum of its straight flank and its
crater's bowl. The flow is a nine-lane ribbon, levee crests over a channel,
its top edges dropping to a foot 1.4 half-widths out sunk in the ground
beside it; the ground under its top is held under its surface. The lake is a
flat slab over the caldera's lattice triangles that hold water; the sea one
slab over the tile's, running in under the lava where it enters until the
bed carved under the flow closes its rim. The foam rises to a crest at the
waterline over every ripple by more than a face tilts across the coplanarity
range, and its land edge leans inland, so no face of it can lie in the sea's
plane or stand parallel to the sea's walls. Rocks and trees landing in
another shell's plane turn 3° about their lowest point and sink half a
millimetre (two trees on one contour carry level caps a turn leaves level),
one shell of a pair at a time.

Ground is smooth-shaded with a 55° crease, the lava with 40°. Nine
materials: volcanic ground (sand and black sand, forest, meadow, heath, ash,
scoria, the caldera's beds, sulphur), basalt flow, sea water, foam, crater
lake, basalt (the crags, bombs and boulders), bark, foliage (conifer and
broadleaf), tile plinth (the slate rim and the skirt's section).

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

The collider is seven convex hulls joined in one mesh, built from points
only: the plinth up to the water, and the island in six sectors round its
centre, from the shore to the ground over it; neighbouring sectors share
their edge rays, so the hulls close round the island. Ships sail the sea;
units walk the land.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 111500–114000 | 112874 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 9 distinct; face floors ground ≥51800, lava ≥1500, sea ≥15100, foam ≥1890, lake ≥7200, basalt ≥2810, bark ≥940, foliage ≥7750, plinth ≥7660 | 9 slots; 57624 / 2438 / 16834 / 2101 / 8523 / 3132 / 1050 / 8622 / 8518 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.4000, 2.4000, 0.5500) m ± 0.01 | (2.4000, 2.4000, 0.5491), zmin 0 |
| Collider tris (seven hulls) | ≤ 360 | 344 |
| Export | written, size > 0, removed after measuring | 11629048 bytes |

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. The plan is seeded and nothing else is random; two
default runs print identical measurements. The triangle band is wide enough
for the falsifiers that change geometry (`--short-flow` 112082,
`--breach-rim` 113046, `--steep-cone` 112758) to reach their own checks, and
the lava's floor sits under `--short-flow`'s 1646 faces for the same reason.

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

The tile's flat base is the only geometry at Z = 0.

### Terrain invariants

A map tile has no joinery. What makes this read as a volcano and as a map
tile is that its edge is one profile all round, that the caldera holds its
lake, that the cinder cone is a cinder cone, that the lava ran downhill
between its levees into the sea, that the sea lies level and is held by the
shore and the rim with its foam at the waterline, and that the rocks and
trees stand in the ground. Each face carries `Part`, `Ident` and `Cap` tags,
each vertex `Ring`, `Lane` and `FoamX`, so the rim, a flow row and lane, and
a trunk's foot can be named; every measurement is then made on the shipped
geometry.

| Axis | Declared | Measured |
| --- | --- | --- |
| Edge: every vertex on the skirt's top, its distance off the tile's circle and its height against the canonical edge height | ≤ 0.0005 m each | 0.0000 / 0.0000 (624 vertices) |
| Caldera holds its lake: on each of 180 bearings out from the caldera's centre, the highest ground on the shipped tile; the lowest of those crests (the pass the lake would spill through) against the lake's top | ≥ 0.040 m | 0.0733 m (at 106°) |
| Lake flat: its top's spread, and its median against the declared level | ≤ 0.0005 m; 0.370 ± 0.0015 m | 0.00000; 0.37000 |
| Cinder cone coaxial: on 36 bearings off the shipped ground, the crater's crest (highest point) and the base (where the flank meets the lake); the distance between the two rings' centres | ≤ 0.004 m | 0.00067 |
| Cinder cone at repose: on each bearing, the flank's slope from a quarter to seven eighths of the way from the crest to the base | every bearing 29–34° | 30.87–31.78° |
| Lava drains: along its centre lane, the largest rise from one row to the next | ≤ 1e-6 m | −0.00025 (111 rows, 0.303 m fall) |
| Lava in its levees: per row, the lower levee crest over the channel's centre | ≥ 0.002 m | 0.0028 |
| Lava into the sea: its toe against the sea's level | ≤ −0.010 m | −0.0538 |
| Sea level: the top's median height and largest excursion from it | level 0.150 ± 0.0015 m; ripple 0.001–0.006 m | 0.15000; 0.00238 |
| Water contained, lava seated: the ground over every rim vertex and rim-edge midpoint of the sea's and the lake's top; the ground over every corner of the flow's foot | sea and lake ≥ 0.005 m; lava ≥ 0.003 m; 1804 points | sea 0.0090, lake 0.0095, lava 0.0038 |
| Foam seated: every foam vertex off the water's level; its land edge's top under the shore | ≤ 0.007 m; ≥ 0.003 m | 0.0058; 0.0035 |
| Rocks sealed: per crag, bomb and boulder, in each sector holding a vertex, its most-buried vertex under the ground | ≥ 0.003 m, 29 rocks | worst 0.0050 |
| Rocks apart: pairs of rocks whose BVH trees overlap | 0 | 0 |
| Trees rooted: every trunk's foot (its bottom cap) under the ground straight above each corner | 0.004–0.050 m, 66 trunks | 0.0089–0.0158 |

The caldera and the cinder cone are measured off the shipped tile by rays
straight down, not read back from the closed form that built them, so the
lattice's sampling of the wall and the cone is what the gates see.

## Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. The envelope was unchanged in every run but
`--warp-edge` (y 2.3960) and `--perch-rock` (z 0.5502), both inside the
tolerance; the triangle count changed only where the flag changes geometry
(above).

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--warp-edge` | edge (an arc of the rim pulled 4 mm in and lifted 4 mm: 0.0040 m off the circle and the canonical height) | 17 |
| `--breach-rim` | caldera holds its lake (a notch 0.24 m deep cut through the back rim: lowest pass −0.0097 m) | 18 |
| `--tilt-lake` | lake flat (the lake's top sloped 0.03 m per metre: spread 0.0197 m) | 19 |
| `--skew-crater` | cinder cone coaxial (its crater moved 30 mm off the base's axis: 0.0093 m) | 20 |
| `--steep-cone` | cinder cone at repose (the cone raised 1.45 times: 40.9–41.6°) | 21 |
| `--uphill-flow` | lava drains (a 30 mm hump mid-course, steeper than the flow falls: rises 0.00480 m between rows) | 22 |
| `--breach-levee` | lava in its levees (one crest dropped under the channel over a stretch: −0.0027 m) | 23 |
| `--short-flow` | lava into the sea (the flow stopped 60 mm short of the coast: toe +0.0173 m) | 24 |
| `--flat-sea` | sea level and ripple (the sheet laid flat at its level: ripple 0.00000 m) | 25 |
| `--short-sea` | water contained (the sheet's shoreward rim drawn 60 mm out to sea: −0.0424 m) | 26 |
| `--lift-foam` | foam seated (the foam raised 20 mm: 0.0258 m off the water, land edge −0.0165 m) | 27 |
| `--perch-rock` | rocks sealed (each rock seated against the ground at its centre alone: −0.0214 m) | 28 |
| `--pile-rocks` | rocks apart (two crags dropped against the first: 2 pairs overlap) | 29 |
| `--float-trees` | trees rooted (the lowland broadleaves raised 40 mm: feet −0.0292 m) | 30 |

`--float-trees` lifts only the lowland broadleaves, whose tops stay under the
island's top, so the envelope does not steal the exit. `--uphill-flow`'s hump
is 20 mm wide: the flow falls about 0.78 m per metre on the flank, and a
gentler swell would be swallowed by that fall.

## Run

```bash
blender --background --python caldera_island_tile.py --
blender --background --python caldera_island_tile.py -- --skip-decimate
blender --background --python caldera_island_tile.py -- --stray-vert
blender --background --python caldera_island_tile.py -- --lift-z
blender --background --python caldera_island_tile.py -- --warp-edge
blender --background --python caldera_island_tile.py -- --breach-rim
blender --background --python caldera_island_tile.py -- --tilt-lake
blender --background --python caldera_island_tile.py -- --skew-crater
blender --background --python caldera_island_tile.py -- --steep-cone
blender --background --python caldera_island_tile.py -- --uphill-flow
blender --background --python caldera_island_tile.py -- --breach-levee
blender --background --python caldera_island_tile.py -- --short-flow
blender --background --python caldera_island_tile.py -- --flat-sea
blender --background --python caldera_island_tile.py -- --short-sea
blender --background --python caldera_island_tile.py -- --lift-foam
blender --background --python caldera_island_tile.py -- --perch-rock
blender --background --python caldera_island_tile.py -- --pile-rocks
blender --background --python caldera_island_tile.py -- --float-trees
blender --background --python caldera_island_tile.py -- --output caldera.png
```

Smoke passes no flags.

The hero does not turn the piece (`HERO_YAW_DEG` 0) and looks down on the
tile from the front, 12° to the left and 32° over it, the way a map tile is
seen on a game board: the caldera and its lake open behind the cone's front
flank, the lava runs down the right toward the camera and the key from the
left throws the barrancos into relief. Seen from this high, the floor behind
the tile is the backdrop, so the warm wedge drops its pool on the floor off
to the left, where it reaches no water to glare off, rather than on the back
wall. Framing measures fill x 0.709, y 0.800, margins left 0.138, right
0.153, bottom 0.117, top 0.083; the asset-quality floors pass.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` and `11` for
`gallery_asset_quality.check_asset_quality`, both on the `--output` path.
`15`–`16` are the hygiene and grounded family; `17`–`31` are file-local.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or not one tile, sea, lake, lava flow and foam line |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 9 distinct slots, or a face-count floor missed |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Asset-quality floor (render path only) |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Mesh hygiene: loose, non-manifold, zero-area, doubles, n-gons, coplanar cross-shell pairs |
| 16 | Not grounded: bounding box `zmin` off 0 |
| 17 | Edge: the rim off the circle or off the canonical edge height (`--warp-edge`) |
| 18 | Caldera: its rim's lowest pass under the declared freeboard over the lake (`--breach-rim`) |
| 19 | Lake: its top not flat or off its level (`--tilt-lake`) |
| 20 | Cinder cone: its crater's crest off its base's axis (`--skew-crater`) |
| 21 | Cinder cone: a flank outside the repose band (`--steep-cone`) |
| 22 | Lava: its surface rising anywhere along it (`--uphill-flow`) |
| 23 | Lava: a levee crest not over the channel by the declared margin (`--breach-levee`) |
| 24 | Lava: its toe not under the sea (`--short-flow`) |
| 25 | Sea: off its level or its ripple outside the band (`--flat-sea`) |
| 26 | Water contained, lava seated: a sheet's rim not under the ground, or the flow's foot not under it (`--short-sea`) |
| 27 | Foam: off the waterline, or its land edge not under the shore (`--lift-foam`) |
| 28 | Rocks: a sector of a crag, bomb or boulder not bedded in the ground (`--perch-rock`) |
| 29 | Rocks: two overlap (`--pile-rocks`) |
| 30 | Trees: a trunk's foot out of its band under the ground (`--float-trees`) |
| 31 | Collider triangle count above ceiling |
