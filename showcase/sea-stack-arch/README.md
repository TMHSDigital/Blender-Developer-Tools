# Sea stack and arch

A showcase piece, not an example, in the `terrain` category.
It builds a procedural game-ready coastal diorama tile, 2.84 × 1.96 m across
and 1.46 m high: a fragment of a bedded sandstone headland at the sea's edge,
with a natural arch through it and a sea stack standing in the water beside
it.

- **The tile.** A rounded square. The sea fills the right of it out to the
  edge, where the tile's rim stands 16 mm over the water and holds it, and
  runs through the arch to the back edge. The left is a wave-cut rock
  platform: the headland's own beds planed off, their edges outcropping as
  low dark-lipped steps between buff and rust treads, crossed by wandering
  joint cracks, with puddles, algal film, two tide pools, and weed and
  barnacles toward the water. In front is a sandy cove, dark and wet at
  the water and drying paler up the shore, with a bank of grey and buff
  shingle at its head. Along the landward edge a low clifftop bank rises
  70 mm over the platform on a raw soil-and-rock riser, turfed on top. The
  seabed falls away from the shore, so the water deepens from pale
  turquoise in the shallows to a deep blue-green. The tile's skirt drops
  straight to a flat base: the beds in section, uneven buff, rust and grey
  bands parted by thin dark shaly ones, pebbly in places, with soil and turf
  over the bank.
- **One eroded mass.** Eighteen level beds, hard sandstone beds of uneven
  thickness (65–132 mm) over thin soft ones (18–35 mm), at one set of heights
  in every column, so the strata run on from the legs into the roof and the
  stack. Every bed's outline is the headland's jointed faces (fourteen
  planes turning the corners round the fin), each leaning back with height,
  battered out below 0.64 m and flared at the foot, then set back by the
  bed's own retreat. On that, one weathering field in space, read on the
  weathered face itself, so the swells and hollows of a face run on through
  the beds and from the legs into the roof whichever column a face belongs
  to. Each hard bed stands proud or sits back by its own amount, has blocks
  fallen out of it and, here and there, an open joint; its top arris is
  worn round and its foot chamfered. The soft beds are undercut behind the
  hard beds either side, deeply in places and all but flush in others, and
  deepest at the foot of each leg and the stack, the wave-cut notch.
- **The arch.** Two legs, the seaward one standing in the water, whose inner
  faces curve in on a flattened ellipse from 0.55 m apart at the springing
  and meet at the crown under the roof, their arrises cut back where the sea
  has rounded them. The roof's lowest bed runs on from the legs' top bed
  face for face and bears on both; its upper beds step down toward the sea,
  so the skyline falls away seaward.
- **The stack.** A rugged, tapering pillar of the same beds (fourteen
  layers, 1.10 m) standing in the sea on a flared foot, its upper beds
  broken back on different sides so its top is ragged.
- **The sea.** A rippled sheet at a declared level of 0.105 m, its rim run
  under the shore and under the tile's rim, calm at the shore, the rim and
  round the feet. A foam line lies at the waterline along the shore, rim to
  rim, and round each foot in the water, its land edge tucked under the
  shore or into the rock.
- **Loose rock.** Five fallen blocks (bed fragments broken on fracture
  planes cut well in, a corner or two knocked off, their top and foot at
  their own slants, so none reads as a sawn box),
  six rounded boulders and 46 pebbles on the shingle, sealed all round and
  held apart, and clear of the feet and the pools.
- **The tops.** A turf mat over the roof's top bed and the stack's, draped
  over the edge as an overhanging lip (stopping short where it has eroded
  back) and tucked into the stone, with tufts of sea grass and cushions of
  sea thrift (a mound of leaves, pink heads on short stalks).

The littoral bands are in the materials: olive wrack and green-black weed
at the waterline over darkened wet stone, a pale barnacle crust over it, a
black tar-lichen band above fraying out upward, then orange and grey lichen
high up, bird lime splashed on the high ledges and streaked down the
seaward faces. Each bed has its own cast (grey-green grit, pale cream,
rust-red, buff, a dark iron-rich band) and grain, with pebbly lenses in the
coarse beds, and the soft beds are dark plum-brown shale, so the strata band
strongly across the rock; overhangs stay dark and damp. The beds stand
proud or sit back from the face by a spread set-back (`PROUD_GAIN`, the
seeded draws unchanged), so some form ledges and others shadowed bands,
and the soft beds are cut back 34 mm (`NOTCH`) behind the hard ones.

Every seeded draw comes from `random.Random(SEED)` in `plan_scene()`, before
anything is built: each face's drift and set-backs, the weathering fields,
each bed's relief, fallen-out blocks, joints and undercut, the loose rock and
the cover. Per-point variety comes from closed-form functions of position.
No flag draws from the stream, so a falsifier changes only what it names.

Every column is sampled on one fixed set of rays from its centre, and a
bed's outline on a ray is where the ray leaves the intersection of its
half-planes, each set in by the bed's set-back. A soft bed on a ray is the
hard face either side, read with that bed's own set-back, less its undercut,
so the bites are exact; a leg's top soft bed is also cast against the roof's
lowest bed from the leg's own centre. The piece is a stack of flat beds, a
coplanar hazard: each bed's walls batter by their own degree or two, arrises
carry a sub-millimetre wear ray by ray, a pass draws any soft-bed facet still
in another bed's plane, or in the plane of the turf and cover draped over
the top bed, 1.5 mm toward its own centroid, and blades, stalks,
heads and cushions landing in another shell's plane turn 3° about their root.

Rock is smooth-shaded with an 18° crease, so the arrises and fallen-out
blocks stay crisp; grass and heads smooth. Eight materials: sandstone (the
beds and fallen blocks), wave-cut shelf (platform, beach, clifftop bank,
seabed, skirt),
sea water, foam, cobble (boulders and pebbles), turf, grass (sea grass,
thrift leaves and stalks), sea thrift.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

The collider is five convex hulls joined in one mesh, built from points
only: each leg, the roof, the stack and the tile, so a player can pass under
the arch.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 89900–90900 | 90422 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 8 distinct; face floors sandstone ≥45000, shelf ≥13000, water ≥5380, foam ≥1900, cobble ≥2770, turf ≥5370, grass ≥5170, thrift ≥3440 | 8 slots; 46448 / 13438 / 5546 / 1966 / 2856 / 5540 / 5331 / 3552 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.8400, 1.9600, 1.4649) m ± 0.01 | (2.8400, 1.9600, 1.4649), zmin 0 |
| Collider tris (five hulls) | ≤ 270 | 252 |
| Export | written, size > 0, removed after measuring | 9158708 bytes |

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. The plan is seeded and nothing else is random; two
default runs print identical measurements, and 4.5.11 and 5.1.2 print the
same measurements as 5.2.1 (the glTF's size aside: 9158716 bytes there, a
few bytes of exporter metadata).

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

### Organic invariants

A headland has no joinery. What makes this read as a sea arch is that the
beds lie level and run on from column to column, that the soft beds are
cut back under the hard ones, that the roof rests on both legs and the
legs and the stack stand in the ground, that there is a clear hole through
it, that the stack stands over its own foot, that the sea lies level and is
held by the shore and the tile's rim with its foam at the waterline, that
the loose rock rests on the ground, that the turf and flowers grow out of
the tops, and that the rock is ragged rather than squared. Each face carries
`Part`, `Ident` (column and layer), `Layer`, `Hard` and `Cap` tags and each
vertex a `Ring`, so a bed, its end rings and its top can be named; every
measurement is then made on the shell's geometry.

| Axis | Declared | Measured |
| --- | --- | --- |
| Beds bite: every soft bed's end ring, shallowest vertex inside the hard bed it runs into (ray-parity signed depth, majority of seven rays), the roof's lowest bed over each leg included | 0.001–0.030 m, 41 joints | 0.0019–0.0163; roof on the legs 0.0149, 0.0156 |
| Stack plumb: the volume centroid of all its beds inside the convex footprint of its narrowest section (the foot notch's middle ring) | ≥ 0.100 m | 0.1279 |
| Feet sealed: for each leg and the stack, in each of 8 sectors round the lowest bed, its most-buried vertex under the ground straight above it | ≥ 0.020 m in 8 of 8 | worst 0.0307, 8 of 8 each |
| Aperture: rays along +Y past every bed; clear height up the opening's centre line from the water, and the narrowest clear width over the 0.60 m above the water | width ≥ 0.22 m, height ≥ 0.68 m | width 0.2720, height 0.7570 |
| Bedding level: a least-squares plane through every hard bed's top-cap vertices; its tilt, and per layer the spread of the fitted heights across the columns | tilt ≤ 0.8°, spread ≤ 0.004 m, 21 bed tops | tilt 0.0000°, spread 0.00000 |
| Undercut: per soft bed, the median over its middle ring of how far the hard beds either side stand out past it, cast along its own outward normal at each host's face ring nearest it | 0.008–0.085 m, 22 soft beds | 0.0158–0.0789 |
| Water: the median height of the sea's top sheet and its largest excursion from it; each pool's top flat | level 0.105 ± 0.0015 m; ripple 0.0015–0.0090 m; pools ≤ 0.0005 m | 0.10500; 0.00240; 0.0, 0.0 |
| Water contained: the ground (the shore or the tile's rim) over every rim vertex and rim-edge midpoint of the sea's and each pool's top | ≥ 0.008 m, 544 points | 0.01007 |
| Foam seated: every foam vertex off the water's level; its land edge's top under the ground or inside a foot | ≤ 0.006 m; ≥ 0.004 m, 3 lines | 0.00430; 0.00535 |
| Loose rock sealed: per block, boulder and pebble, in each sector holding a vertex, its most-buried vertex under the ground | ≥ 0.003 m, 57 pieces | worst 0.0050 |
| Loose rock apart: pairs of pieces whose BVH trees overlap | 0 | 0 |
| Cover rooted: every blade's and stalk's base cap and every cushion's underside inside the turf or the top bed under it (the deeper of the two); every blade, stalk, head and cushion joined to its top | 0.004–0.050 m, 324 roots; none loose | 0.0075–0.0395; none loose |
| Ragged: the share of the rock's walls (faces within 20° of vertical, by area) whose plan normal lies within 5° of its column's own axes | ≤ 0.25 | 0.1763 |

The feet are bedded against the ground as built: each lowest bed's foot is
set 30 mm under the lowest ground point beneath its widest ring, and kept
off the sea sheet's two planes. The pools' levels are read off the built
platform. The bite is the distance to the host's nearest face, so it is
smallest beside a fallen-out block, where the host's face turns in within
a few millimetres of the soft bed's ring.

## Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code (after the visual pass that added the clifftop bank,
the broken blocks, the spread set-backs and the deeper soft-bed recess; the
pass before it also ran them all on 4.5.11). The triangle count was
unchanged in every run and the envelope stayed inside its 0.01 m tolerance
(`--tidy-rock` lowers the top 6 mm). The measured values below are 5.2.1's.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--gap-lintel` | beds bite (the left leg's top bed stopped 15 mm under the roof: −0.0150 m) | 17 |
| `--lean-stack` | stack plumb (the stack sheared 0.50 m per metre of height toward the sea: 0.0595 m) | 19 |
| `--cut-pillar` | feet sealed (the right leg's foot stopped 20 mm over the seabed: worst sector −0.0406 m, 0 of 8) | 20 |
| `--close-arch` | aperture (the right leg's side of the opening narrowed to a tenth: width 0.2160 m) | 21 |
| `--tilt-beds` | bedding level (the interior bed boundaries turned 2.5° about a line across the fin: 2.530°) | 22 |
| `--flush-beds` | undercut (every soft bed's middle rings 2 mm behind the hard beds, its bites unchanged: 0.0014–0.0064 m on the failing beds) | 23 |
| `--flat-sea` | water level and ripple (the sheet laid flat: ripple 0.00000 m) | 24 |
| `--short-sea` | water contained (the rim stopped 50 mm short of the shoreline: −0.01925 m) | 25 |
| `--lift-foam` | foam seated (the foam raised 20 mm: 0.02430 m off the water, land edge −0.01465 m) | 26 |
| `--perch-talus` | loose rock sealed (each piece seated against the ground at its centre alone: −0.0307 m) | 27 |
| `--pile-talus` | loose rock apart (three blocks drawn together after the relaxation: 1 pair overlaps) | 28 |
| `--float-cover` | cover rooted (every blade, stalk and cushion base raised 50 mm, its tip held: −0.0335 m, all 398 pieces loose) | 29 |
| `--tidy-rock` | ragged (every bed squared to a box on its column's axes, leaning and battered as before but without weathering, fallen blocks, joints or the curved arch: 0.8239) | 31 |

The roof's grass and thrift are the top of the envelope, so `--float-cover`
holds every tip where it was and moves the bases alone. `--lean-stack`
shears the stack horizontally about its foot, which keeps each bed's
footprint over the one below at every height, so the bites do not steal it;
`--close-arch` narrows only the right leg's side of the hole, so the legs'
faces never come to share a plane; `--tilt-beds` turns the interior
boundaries only, leaving the foot and the top. `--tidy-rock` keeps the
triangle count (every ring keeps its rays) and spreads the cover over the
weathered top's outline, so it changes the rock alone.

## Run

```bash
blender --background --python sea_stack_arch.py --
blender --background --python sea_stack_arch.py -- --skip-decimate
blender --background --python sea_stack_arch.py -- --stray-vert
blender --background --python sea_stack_arch.py -- --lift-z
blender --background --python sea_stack_arch.py -- --gap-lintel
blender --background --python sea_stack_arch.py -- --lean-stack
blender --background --python sea_stack_arch.py -- --cut-pillar
blender --background --python sea_stack_arch.py -- --close-arch
blender --background --python sea_stack_arch.py -- --tilt-beds
blender --background --python sea_stack_arch.py -- --flush-beds
blender --background --python sea_stack_arch.py -- --flat-sea
blender --background --python sea_stack_arch.py -- --short-sea
blender --background --python sea_stack_arch.py -- --lift-foam
blender --background --python sea_stack_arch.py -- --perch-talus
blender --background --python sea_stack_arch.py -- --pile-talus
blender --background --python sea_stack_arch.py -- --float-cover
blender --background --python sea_stack_arch.py -- --tidy-rock
blender --background --python sea_stack_arch.py -- --output arch.png
```

Smoke passes no flags.

The hero does not turn the piece (`HERO_YAW_DEG` 0) and looks down on it
as on a game board, like its terrain siblings: from the front, 13° to the
left of the arch's axis and about 28° down (`CAM_DIST` 5.5 m back,
`CAM_RISE` 2.65 m up), so the sea shows through the opening, the stack
stands clear to its right, and the floor is the whole backdrop: the default
stage's wall (pushed back to `WALL_Y` 8 m) never enters the frame, and the
warm wedge pools on the floor behind the arch's landward side. The floor
takes the terrain siblings' darker `(0.013, 0.014, 0.017)`. Framing measures
fill x 0.684, y 0.872, margins left 0.172, right 0.144, bottom 0.078, top
0.050; the asset-quality floors pass.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`17` and `19`
are the hygiene, grounded, joint-fit (beds bite) and plumb (stack) family;
`18` is not used. `20`–`29` and `31` are file-local. `30` is the
asset-quality floor on the render path: `check_asset_quality` returns 11,
which this piece already spends on the collider ceiling, so the call site
remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or not one tile, one sea and 43 bed shells |
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
| 16 | Not grounded: bounding box `zmin` off 0 |
| 17 | Beds bite: a soft bed's end ring not inside the hard bed it runs into, the roof's lowest bed on a leg included (`--gap-lintel`) |
| 19 | Stack plumb: its mass centre not inside its footprint (`--lean-stack`) |
| 20 | Feet sealed: a sector round a leg's or the stack's foot not bedded in the ground (`--cut-pillar`) |
| 21 | Aperture: the opening's clear width or height under its minimum (`--close-arch`) |
| 22 | Bedding: a bed top tilted, or a layer's height not continuous across the columns (`--tilt-beds`) |
| 23 | Undercut: a soft bed recessed outside its band (`--flush-beds`) |
| 24 | Water: the sea off its level or its ripple outside the band, or a pool not flat (`--flat-sea`) |
| 25 | Water contained: a sheet's rim not under the ground (`--short-sea`) |
| 26 | Foam: off the waterline, or its land edge not under the ground or in the rock (`--lift-foam`) |
| 27 | Loose rock: a sector of a block, boulder or pebble not bedded in the ground (`--perch-talus`) |
| 28 | Loose rock: two pieces overlap (`--pile-talus`) |
| 29 | Cover: a root out of its band in the turf, or a piece not joined to its top (`--float-cover`) |
| 30 | Asset-quality floor (render path only; remapped from 11) |
| 31 | Ragged: too much of the rock's walls squared to its axes (`--tidy-rock`) |
