# Hex island tile

A showcase piece, not an example, and the first piece built for the
`terrain` category. It builds a procedural, game-ready strategy-game map
tile: a flat-topped hexagon 2.60 m corner to corner (2.25 m flat to flat)
with a mountain island in the middle and the sea out to its rim on every
side.

- **The tile.** A triangle lattice over the hexagon carries the island, the
  seabed and the rim; a skirt drops straight from the outline to a flat base
  at Z = 0, the ground in section. The rim is a flat band 40 mm wide, 18 mm
  over the water, its outer arris chamfered down to one canonical edge
  height (0.163 m) all the way round, so the six edges share one profile and
  any neighbouring sea tile meets this one flush. The seabed climbs to the
  rim over 70 mm.
- **The island.** A coastline 0.87 m out from its centre with a few lobes,
  sandy beaches with a gentle shore, and sea cliffs under the western peak.
  Two peaks (the higher 0.54 m over the sea), furrowed by radial gullies, with wandering
  spurs and ravines and finer ridges on the high ground; bare fractured rock
  on the steep faces and the summits, old snow in the highest hollows, and
  conifer forest on the upper slopes. Broadleaf trees, a few already turning,
  stand on the lowland.
- **The river.** From a tarn in a small cirque between the peaks it falls
  over a cascade and down a valley it has cut to a sandy estuary in the front
  cove. Its surface is read off the valley floor along its line and held
  falling the whole way; at the estuary's head it is 2 mm over the calm sea it
  runs out onto, and it slides under the sea by its end. The sea runs up the
  estuary to meet it. The water lightens to the sea's shallows over the mouth
  and breaks white where the river falls steeply.
- **The terraces.** A hill on the right cut into seven level fields on its
  contours, 30 mm a step (real paddy risers are 0.8–1.5 m, their treads
  2–6 m: [FAO](https://www.fao.org/4/ad083e/ad083e07.htm)). Each field its own
  crop, sown in rows: young rice, ripening grain, a flooded paddy that takes
  the sky, barley gold. Every riser is a dry-stone retaining wall traced along
  its own contour, its face stone, its coping turfed over just above the
  field it holds up. The steps soften into the natural slope at the hill's
  edge.
- **The sea.** A rippled sheet at a declared level of 0.150 m over every
  lattice triangle that holds water, from under the shore out to under the
  rim, calm over the river's mouth, darkening from turquoise shallows to deep
  water. A foam line lies at the waterline round the coast, from one bank of
  the mouth round to the other, its land edge tucked under the beach.
- **Rocks.** Nine fractured crags on the high flanks of the two peaks and
  twelve boulders on the beaches and the lowland, sealed all round and held
  apart.

The tile's colour reads the way a map does: sand, meadow, forest, rock and
snow by height and slope; the fields by their crop; the sea by its depth.

Every seeded draw comes from `random.Random(SEED)` in `plan_scene()`, before
anything is built: where each tree and rock stands and its size, tone and
turn, the ripple and the foam's phases. The ground is closed-form in plan
position. No flag draws from the stream, so a falsifier changes only what it
names.

The coast is where the shore's rise starts from the sea's level, so the
ground meets the water exactly there. The river is a five-lane ribbon flat
across each row; the tarn a flat disc over its basin; the sea one slab over
the lattice triangles that hold water, a low hollow cut off from the sea left
dry. The foam rises to a crest at the waterline and falls to its sea edge
under the calm water more steeply than any ripple, so no face of it can lie
in the sea's plane; rocks, trunks and crowns landing in another shell's plane
turn 3° about their lowest point.

Ground and fields are smooth-shaded with a 55° and 32° crease, so the
terrace walls and the rim stay crisp. Nine materials: island ground (sand,
meadow, forest floor, rock, snow), terrace fields (crops, flooded paddy,
stone walls), sea water, foam, river water (the river and the tarn), granite
(the crags and boulders), bark, foliage (conifer and broadleaf), tile plinth
(the slate rim and the skirt's section).

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
| Base triangles | 103400–104500 | 103936 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 9 distinct; face floors ground ≥51700, fields ≥5490, sea ≥15500, foam ≥2040, river ≥2330, granite ≥2200, bark ≥690, foliage ≥5830, plinth ≥9160 | 9 slots; 53344 / 5666 / 15981 / 2101 / 2404 / 2268 / 718 / 6018 / 9452 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.6000, 2.2517, 0.7025) m ± 0.01 | (2.6000, 2.2517, 0.7025), zmin 0 |
| Collider tris (seven hulls) | ≤ 360 | 320 |
| Export | written, size > 0, removed after measuring | 10565216 bytes |

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. The plan is seeded and nothing else is random; two
default runs print identical measurements.

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

A map tile has no joinery. What makes this read as a map tile and as land is
that its edges are a hexagon with one profile all round, that the river runs
downhill all the way to the sea, that the fields are level, that the sea lies
level and is held by the shore and the rim with its foam at the waterline,
and that the rocks and trees stand in the ground. Each face carries `Part`,
`Ident` and `Cap` tags, each vertex `Ring`, `Lane`, `Tread` and `FoamX`, so
the rim, a river row, a terrace's tread and a trunk's foot can be named;
every measurement is then made on the shell's geometry.

| Axis | Declared | Measured |
| --- | --- | --- |
| Edge: every vertex on the skirt's top, its distance off the hexagon's outline; its height against the canonical edge height; per edge the heights in order along it against every other edge | ≤ 0.0005 m each; 104 vertices on every edge | 0.0000 / 0.0000 / 0.0000; 104 × 6 |
| River drains: along its centre lane, the largest rise from one row to the next; its last row against the sea's level; its first row under the tarn's top | rise ≤ 1e-6 m; mouth within 0.004 m; source ≤ 0 | rise 0.0000, mouth −0.0029, source −0.0030 (134 rows, 0.089 m fall) |
| Terraces level: every tile face whose corners lie on one tread, its tilt; per terrace the spread of its tread's heights; the rise from each terrace to the next | ≥ 5 consecutive levels; tilt ≤ 0.5°, spread ≤ 0.0015 m, risers 0.0285–0.0315 m | 7 levels (1398 faces); 0.044°, 0.00001 m, 0.030 m each |
| Water: the sea top's median height and largest excursion from it; the tarn's top flat | level 0.150 ± 0.0015 m; ripple 0.001–0.006 m; tarn ≤ 0.0005 m | 0.15000; 0.00239; 0.0000 |
| Water contained: the ground over every rim vertex and rim-edge midpoint of the sea's and the tarn's top (where the river runs over the sea's end in its mouth, or falls out from under the tarn at its outlet, that water instead), and over the river's side lanes | sea and tarn ≥ 0.005 m, river ≥ 0.003 m; 1404 points | sea 0.0084, tarn 0.0050, river 0.0034; 36 points under the other water |
| Foam seated: every foam vertex off the water's level; its land edge's top under the shore | ≤ 0.006 m; ≥ 0.003 m | 0.0043; 0.0046 |
| Rocks sealed: per crag and boulder, in each sector holding a vertex, its most-buried vertex under the ground | ≥ 0.003 m, 21 rocks | worst 0.0050 |
| Rocks apart: pairs of rocks whose BVH trees overlap | 0 | 0 |
| Trees rooted: every trunk's foot (its bottom cap) under the ground straight above each corner | 0.004–0.050 m, 44 trunks | 0.0102–0.0129 |

The terraces are traced, not modelled: each riser's middle is found ray by
ray out from the hill's centre on the unterraced ground, and the wall laid
along it covers the riser's band, so the lattice's stair-stepping across a
riser never shows. The crown of the hill is levelled at the seventh step.

## Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. The envelope and the triangle count were unchanged
in every run.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--warp-edge` | edge (the middle third of one edge pushed 15 mm out and 10 mm up: 0.0150 m off the hexagon, 0.0100 m off the canonical height and the other edges) | 17 |
| `--uphill-river` | river drains (a 40 mm swell raised mid-course: rises 0.00338 m between rows) | 18 |
| `--tilt-terrace` | terraces level (every tread's vertices sloped 0.06 m per metre across the hill, the risers and walls left: 3.447°, spread 0.0244 m) | 19 |
| `--flat-sea` | water level and ripple (the sheet laid flat at its level: ripple 0.00000 m) | 20 |
| `--short-sea` | water contained (the sheet's shoreward rim drawn 60 mm out to sea: −0.0417 m) | 21 |
| `--lift-foam` | foam seated (the foam raised 20 mm: 0.02430 m off the water, land edge −0.01543 m) | 22 |
| `--perch-rock` | rocks sealed (each rock seated against the ground at its centre alone: −0.0337 m) | 23 |
| `--pile-rocks` | rocks apart (three rocks drawn together: 2 pairs overlap) | 24 |
| `--float-trees` | trees rooted (every tree raised 40 mm: feet −0.0298 m) | 25 |

`--tilt-terrace` moves the treads alone, after the tile is built, so the
risers and the walls (which are traced on the unterraced ground) stay where
they were and the flag changes nothing but the fields. `--short-sea` moves
the sheet's rim vertices, keeping its triangles, so the count does not
steal the exit.

## Run

```bash
blender --background --python hex_island_tile.py --
blender --background --python hex_island_tile.py -- --skip-decimate
blender --background --python hex_island_tile.py -- --stray-vert
blender --background --python hex_island_tile.py -- --lift-z
blender --background --python hex_island_tile.py -- --warp-edge
blender --background --python hex_island_tile.py -- --uphill-river
blender --background --python hex_island_tile.py -- --tilt-terrace
blender --background --python hex_island_tile.py -- --flat-sea
blender --background --python hex_island_tile.py -- --short-sea
blender --background --python hex_island_tile.py -- --lift-foam
blender --background --python hex_island_tile.py -- --perch-rock
blender --background --python hex_island_tile.py -- --pile-rocks
blender --background --python hex_island_tile.py -- --float-trees
blender --background --python hex_island_tile.py -- --output island.png
```

Smoke passes no flags.

The hero does not turn the piece (`HERO_YAW_DEG` 0) and looks down on the
tile from the front, 12° to the left and 33° over it, the way a map
tile is seen on a game board: the river runs straight at the camera, the
peaks stand behind it and the terraces catch the key on the right. Seen
from this high, the floor behind the tile is the backdrop, so the warm wedge
drops its pool on the floor off to the left, where it reaches no water to
glare off, rather than on the back wall. Framing
measures fill x 0.731, y 0.850, margins left 0.109, right 0.159, bottom
0.067, top 0.083; the asset-quality floors pass.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` and `11` for
`gallery_asset_quality.check_asset_quality`, both on the `--output` path.
`15`–`16` are the hygiene and grounded family; `17`–`26` are file-local.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or not one tile, sea, tarn, river and foam line |
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
| 17 | Edge: the rim off the hexagon, off the canonical edge height, or one edge's profile unlike the others (`--warp-edge`) |
| 18 | River: its surface rising anywhere along it, its mouth off the sea's level, or its source over the tarn (`--uphill-river`) |
| 19 | Terraces: too few or not consecutive, a tread tilted or spread, or a riser out of band (`--tilt-terrace`) |
| 20 | Water: the sea off its level or its ripple outside the band, or the tarn not flat (`--flat-sea`) |
| 21 | Water contained: a sheet's rim not under the ground, or the river's side not under its bank (`--short-sea`) |
| 22 | Foam: off the waterline, or its land edge not under the shore (`--lift-foam`) |
| 23 | Rocks: a sector of a crag or boulder not bedded in the ground (`--perch-rock`) |
| 24 | Rocks: two overlap (`--pile-rocks`) |
| 25 | Trees: a trunk's foot out of its band under the ground (`--float-trees`) |
| 26 | Collider triangle count above ceiling |
