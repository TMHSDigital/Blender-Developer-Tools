# Canyon and mesa tile

A showcase piece, not an example, and a `terrain` piece. It builds a
procedural, game-ready strategy-game map tile of Colorado Plateau character:
a square 2.40 m on a side with two mesas and a canyon between them at the
back, a butte and a slender spire in front, and a dry wash crossing the tile
from edge to edge.

- **The tile.** A square lattice carries the valley floor, the talus aprons
  and the wash's channel; a skirt drops straight from the outline to a flat
  base at Z = 0, the valley's red beds in section. The floor stands 0.10 m
  over the base, 10 mm higher at the back edge and lower at the front, with
  low drifts over all of it and a field of transverse dunes in the front
  corner (long stoss slopes, lee faces near the angle of repose).
- **The layer cake.** Every formation is cut from the same section, as in
  Monument Valley: an Organ Rock shale slope and talus apron up to the
  cliffs' foot, a cliff of De Chelly sandstone in five horizontal beds, a
  crumbling Moenkopi shale slope, and a Shinarump caprock on top, flat and
  overhanging the slope by 12 mm. The cliff is 0.28 m of the 0.483 m relief,
  the slope 0.055 m and the cap 0.028 m, the proportions of the real column
  (the cliff about two thirds of the relief, the cap a few percent). The beds
  run flush where they can; a ledge opens only where a strong bed sits on a
  weak one. Every bed stands as its own rounded band: its face rounds back
  over the outer fifth of its thickness into a parting 2.3–3.6 mm deep
  at each bedding plane, so the cliff reads in horizontal strata, the way the
  plateau's walls do. Each bed carries its own colour, level and continuous
  round every formation: maroon at the foot where it grades from the Organ
  Rock, then red-orange, salmon, a pale cream bed, deep red, orange, and a
  bleached top, each with a dark seam at its parting and a few thin pale
  laminae. Vertical joints cut into every face but open and close up it (their
  depth swings between 45% and 100% from height to height), so they never
  read as one unbroken flute. Desert varnish hangs from the rim and the
  ledges in a few thin dark streaks, densest high up and fading down the
  cliff. The Moenkopi slope is red-brown shale in thin beds, a few of them
  grey-green; the caprock's face is a dark, thinly bedded grey-brown ledge.
  The caps' tops are weathered slickrock: pale grey-buff where bare, red sand
  blown over the rest in soft-edged drifts, darker pans where rain stands.
- **The formations.** Two mesas at the back, a canyon between their walls;
  a butte in front, taller than it is wide; a spire that stands to the top
  of the cliff sandstone, its cap long gone, worn to a totem: its girth
  narrows fast off the talus (to 58% of its foot's at a fifth of its
  height), then slowly up a slender shaft, its hardest bed left as a
  swelling knob under a 34% top, and every parting cut into it. Each
  formation sits on its own apron and runs 35 mm into it.
- **The aprons.** Talus at the angle of repose: 35.0° at the cliff's foot
  easing to 31.0° at the toe, the concave profile scree takes (measured
  talus steepens upslope from 31–34° to 35–37°:
  [Wikipedia, Scree](https://en.wikipedia.org/wiki/Scree);
  [angle of repose](https://en.wikipedia.org/wiki/Angle_of_repose)),
  then easing into the floor. Scree in the cliffs' own colours: angular
  fragments of every bed packed with dark gaps between them, coarser pieces
  among the fine, a few grey caprock chips, chutes of paler debris, and the
  Organ Rock's banded red-brown shale showing through just under the bench.
- **The wash.** It enters at the back edge, runs down the canyon between
  the mesas and out across the valley between the butte and the spire, and
  leaves by the front edge, falling 22.5 mm the whole way and never rising.
  Its bed is read off the floor along its line, held falling, and cut 8 mm
  under it; a ribbon of buff sand lies on it, rippled across the flow, with
  gravel bars and cracked mud, its edges run under the banks. On a map, the
  wash carries on into the next tile.
- **Scatter.** 60 fallen blocks on the aprons and at their toes, cut
  angular by bedding and joint planes and hard-edged, the biggest rolled
  furthest out, sealed into the talus and held apart. Utah junipers and
  pinyon as low, broad, lopsided crowns of five dense clumps on short
  leaning stems, sweeping nearly to the sand; 118 low scrub cushions, big
  sagebrush silver grey-green with about one in three on the floor rubber
  rabbitbrush going olive-gold; six cottonwoods turning gold on the wash's
  banks.

The tile's colour reads the way a map does: red sand, darker hardpan and
pale blown sheets and broad swings from deep terracotta to apricot on the
floor, black desert pavement in patches, the aprons scree in the wall's
colours, the cliffs banded and lightly varnished, the caps weathered grey
slickrock under red sand.

Every seeded draw comes from `random.Random(SEED)` in `plan_scene()`, before
anything is built: where each block and plant stands and its size, tone and
turn. Each formation's joints and erosion come from its own seeded stream.
The ground is closed-form in plan position. No flag draws from the stream,
so a falsifier changes only what it names.

A formation is one closed loft: rings round its outline bottom to top, two
rings at one height making a ledge, a flat top in concentric rings, a fan
underneath. Its outline is a turned superellipse with a few harmonics; the
apron is a closed-form function of the distance from that outline, so its
slope is the profile's own. Blocks, trunks, crowns and scrub landing in
another shell's plane turn 3° about their lowest point and sink 0.3 mm
(one shell of each pair only: moving both alike would keep them coplanar);
each scrub cushion also sinks up to 0.8 mm more than the last, so two on
the level caprock never share their buried plane.

Ground is smooth-shaded with a 50° crease, the cliffs with 40° and the
fallen blocks with 24°, so the ledges, the cap's overhang, the blocks'
broken faces and the skirt stay crisp. Eight materials: desert
ground (sand, hardpan, pavement, aprons), cliff sandstone (De Chelly and the
Moenkopi slope), caprock, wash sand, fallen blocks, bark, foliage (juniper,
sage and cottonwood), tile plinth.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

The collider is five convex hulls joined in one mesh, built from points
only: the tile's slab up to the floor, and each formation from its apron's
toe to its top. Units walk the floor and climb the aprons; the cliffs stop
them.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 127100–128300 | 127676 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 8 distinct; face floors ground ≥49660, sandstone ≥33880, caprock ≥10300, wash ≥4280, blocks ≥6280, bark ≥850, foliage ≥16200, plinth ≥1240 | 8 slots; 51200 / 34932 / 10620 / 4420 / 6480 / 884 / 16704 / 1280 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.4000, 2.4000, 0.6221) m ± 0.01 | (2.4000, 2.4000, 0.6221), zmin 0 |
| Collider tris (five hulls) | ≤ 280 | 242 |
| Export | written, size > 0, removed after measuring | 13487784 bytes |

The triangle band, the sandstone, block and foliage floors and the height
were re-fitted when the formations and scatter were remodelled for
legibility, not widened to pass: each bed gained a ring on every
formation (its face now rounds into a parting top and bottom), the fallen blocks went from 34 to 60, the floor's scrub from
56 to 84 cushions and each juniper's crown from four clumps to five; the
junipers became low bushes, which dropped the tile's top (set by the
mesa-top junipers) from 0.6416 to 0.6221 m. The band keeps its old width
round the new count, the floors their old 97% of it.

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

A map tile has no joinery. What makes this read as a plateau country is that
every formation is cut from one horizontal layer cake, that the caprocks lie
level, that the aprons stand at the angle loose rock rests at, that the wash
runs downhill all the way across, and that the blocks and plants stand in
the ground. Each face carries `Part`, `Ident`, `Cap` and `Zone` tags, each
vertex `Bed`, `Talus`, `Ring` and `Lane`, so a bedding plane, an apron's
straight run, a wash row and a trunk's foot can be named; every measurement
is then made on the shell's geometry.

| Axis | Declared | Measured |
| --- | --- | --- |
| Formations sealed: every formation's foot (its bottom fan's rim) under the tile straight above it | ≥ 0.010 m, 4 formations | 0.0336–0.0340 |
| Strata: per bedding plane, the heights of every formation's rings on it, spread across all formations; both canyon walls (the two mesas) carry every plane | ≤ 0.0005 m; 7 planes | 0.0000 m; planes at 0.172, 0.236, 0.290, 0.346, 0.400 (on all four), 0.455, 0.483 (on the three capped) |
| Caprock flat: each cap's top, the spread of its heights and its faces' tilt | ≤ 0.0005 m, ≤ 0.2°; 3 tops | 0.0000 m, 0.000° |
| Talus: every tile face whose corners lie in an apron's straight run, its slope | 30–37° (angle of repose); ≥ 1500 faces | 30.78–36.19°, median 32.86° (7006 faces) |
| Wash: along its centre lane, the largest rise from one row to the next; its whole fall; its ends in from the back and front edges; the banks over its side lanes | rise ≤ 1e-6 m, falls; ends ≤ 0.010 m; banks ≥ 0.003 m | rise 0.0000, fall 0.0225 m over 316 rows; ends 0.0040 / 0.0078 m; banks 0.0033 m |
| Blocks sealed: per block, in each sector holding a vertex, its most-buried vertex under the ground | ≥ 0.003 m, 60 blocks | worst 0.0040 |
| Blocks apart: pairs of blocks whose BVH trees overlap | 0 | 0 |
| Plants rooted: every trunk's foot (its bottom cap) under the ground or the cap straight above each corner; every scrub cushion, per sector, its most-buried vertex | trunks 0.004–0.050 m, 46 trunks; scrub ≥ 0.003 m, 118 cushions | 0.0090–0.0101; worst 0.0040 |

The talus check excludes where one apron's straight run is not alone: where
two aprons meet in the canyon, where the floor or the dunes rise to meet the
toe, and beside the wash's channel. The spire's apron is the tightest cone
on the tile and sets its maximum: a flat lattice triangle chords a cone a
little steeper than the cone itself.

## Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. The envelope's size was unchanged in every run
but `--dome-cap` (0.6312 m tall, its domed caps now above the mesa-top
junipers; inside the 0.01 m tolerance, so exit 8 never fires first), and the
triangle count in every run but `--perch-butte` (127420: the butte loses a
ring).

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--perch-butte` | formations sealed (the butte's foot stood 8 mm over its bench instead of run into it: −0.0092 m) | 17 |
| `--tilt-beds` | strata (the east mesa dipped 0.04 m per metre: plane 1 spread 0.02596 m across the formations) | 18 |
| `--dome-cap` | caprock flat (the caps' middles raised 12 mm: spread 0.01200 m, tilt 10.007°) | 19 |
| `--steep-talus` | talus (the aprons piled at 46°–42°: 42.09–47.29°) | 20 |
| `--uphill-wash` | wash (a 20 mm swell raised mid-course: rises 0.00171 m between rows, its edges out of the banks) | 21 |
| `--perch-rock` | blocks sealed (each block seated against the ground at its centre alone: −0.0245 m) | 22 |
| `--pile-rocks` | blocks apart (two blocks dropped against the one lying furthest out: 5 pairs overlap) | 23 |
| `--float-plants` | plants rooted (the floor's plants raised 30 mm: feet −0.0210 m, scrub −0.0260 m) | 24 |

`--perch-butte` replaces the butte's two lowest rings with one standing on
the bench, so the cliff and everything over it stay where they were.
`--float-plants` lifts the plants on the floor only: the mesa tops' plants
set the tile's height, and lifting them would steal the exit at the
envelope.

## Run

```bash
blender --background --python canyon_mesa_tile.py --
blender --background --python canyon_mesa_tile.py -- --skip-decimate
blender --background --python canyon_mesa_tile.py -- --stray-vert
blender --background --python canyon_mesa_tile.py -- --lift-z
blender --background --python canyon_mesa_tile.py -- --perch-butte
blender --background --python canyon_mesa_tile.py -- --tilt-beds
blender --background --python canyon_mesa_tile.py -- --dome-cap
blender --background --python canyon_mesa_tile.py -- --steep-talus
blender --background --python canyon_mesa_tile.py -- --uphill-wash
blender --background --python canyon_mesa_tile.py -- --perch-rock
blender --background --python canyon_mesa_tile.py -- --pile-rocks
blender --background --python canyon_mesa_tile.py -- --float-plants
blender --background --python canyon_mesa_tile.py -- --output canyon.png
```

Smoke passes no flags.

The hero does not turn the piece (`HERO_YAW_DEG` 0) and looks down on the
tile from the front, 12° to the left and 33° over it, the way a map tile is
seen on a game board: the wash runs at the camera, the mesas stand behind
it with the canyon between them, their strata reading level and unbroken
across it, the butte and the banded totem spire in front on their scree
aprons. A low, warm key from the left, late in the
day, lights the cliffs on that side and throws each formation's shadow
across the floor; the warm wedge drops its pool on the floor off to the
left. Framing measures fill x 0.700, y 0.817, margins left 0.194, right
0.106, bottom 0.033, top 0.150; the asset-quality floors pass. The tile is a
red desert filling most of the frame, so its saturation (0.36) runs above
the calibration set's (0.15–0.24); its stage (0.234) sits inside theirs.

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
| 3 | Mesh did not build, no UV layer, or not one tile, four formations and one wash |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 8 distinct slots, or a face-count floor missed |
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
| 17 | Formations: a foot not under its apron (`--perch-butte`) |
| 18 | Strata: a bedding plane at different heights on different formations, or a canyon wall missing one (`--tilt-beds`) |
| 19 | Caprock: a top not level (`--dome-cap`) |
| 20 | Talus: too few apron faces, or one outside the angle-of-repose band (`--steep-talus`) |
| 21 | Wash: rising anywhere along it, not falling, not crossing edge to edge, or its edges out of the banks (`--uphill-wash`) |
| 22 | Blocks: a sector of a block not bedded in the ground (`--perch-rock`) |
| 23 | Blocks: two overlap (`--pile-rocks`) |
| 24 | Plants: a trunk's foot out of its band or a scrub cushion not bedded (`--float-plants`) |
| 26 | Collider triangle count above ceiling |
