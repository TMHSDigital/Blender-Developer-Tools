# River delta tile

A showcase piece, not an example, in the `terrain` category. It builds a
procedural, game-ready strategy-game map tile: a square 2.40 m on a side,
low and flat, where a river comes in through the back edge and splits twice
into four distributaries that fan out across a delta plain to the sea at the
front. The sea fills the tile out to its rim on the front and both sides.

- **The tile.** A square lattice carries the delta, the seabed and the rim;
  a skirt drops straight from the outline to a flat base at Z = 0, the ground
  in section. The rim is a flat slate band 34 mm over the sea, its outer
  arris chamfered 5 mm, cut only where the river comes in through the back
  edge; there the channel and its water are cut in section like the ground.
- **The channels.** One trunk, 104 mm wide, forks at about 73° into two,
  and each of those forks again: three bifurcations, four mouths. The angle
  is the one natural deltas grow toward — 70.4° ± 2.6° over 197
  bifurcations in ten deltas
  ([Coffey and Shaw](https://thesedimentaryrecord.scholasticahq.com/article/124824-ancient-channel-mouth-bifurcation-angles-on-earth-and-mars)).
  Each child takes a share of its parent's discharge and a width by
  hydraulic geometry, w ∝ Q^0.5, so the children's widths squared sum to the
  parent's and the children together are wider than their parent, as
  measured deltas show
  ([Edmonds and Slingerland](https://ftp.ems.psu.edu/data/pub/geosc/sling/PUBLICATIONS_SLINGERLAND/2001-2010/Edmondsetal2008.pdf)).
  The mouths flare as they reach the coast, and each channel runs on under
  the sea as a scour fading out past its mouth.
- **The water.** Every channel's surface is one function of distance from
  the delta's apex behind the back edge: 16 mm over the sea where the river
  comes in, falling to the sea's level 1.85 m out, and level with the sea
  from there through the backwater reach to every mouth. So it falls along
  every channel, is continuous through every fork, and meets the sea at
  every mouth.
- **The plain.** Natural levees line every bank — wedges highest at the
  channel's margin, sloping down into the floodbasin behind
  ([Smith et al.](https://ftp.ems.psu.edu/pub/geosc/sling/PUBLICATIONS_SLINGERLAND/2001-2010/Smithetal2009.pdf)) —
  their crests a few millimetres over the water and over the marsh. The
  older upper plain behind stands 5 mm higher and is farmed in a patchwork
  of fields on a slanting grid, parted by dark dikes, given out field by
  field toward the lower plain. The lower plain is wild: marsh in drifts of
  rush, sedge and rusty patches, salt marsh near the sea, dark wet mud at
  every water's edge, an oxbow lake and two ponds in the floodbasins. The
  fan's coast is lobed out at each mouth and draws back along the flanks,
  so the sea wraps both sides.
- **Bars and plumes.** Middle-ground bars stand off three mouths: sandy
  round their margins, their crowns grown over with marsh and reeds. Each
  mouth's silt fans out into the sea in a tan plume that swirls and fades
  into the turquoise shallows, which deepen to blue toward the front.
- **Life on it.** Reed beds — dense clumps of 11 to 18 blades — fringe the
  lower channels, the shore, the marsh and the bars. Weeping willows, each a
  lofted bell of foliage with a ragged hem of shoots, stand on the levees
  and the upper plain, and a row of poplars lines the trunk's levee. Drift
  logs float in the sea and the river or lie stranded on the bars and the
  beaches. In the bay between the two middle mouths a fisherman's hut stands
  on six stilts at the end of a jetty, with a thatched roof, a dark doorway
  and a window, a boat moored beside it, and a fish weir of stakes in the
  shallows nearby.

Every seeded draw comes from `random.Random(SEED)` in `plan_scene()`, before
anything is built: where each tree, reed clump, log and the hut stand and
their size, tone and turn, and the ripple's phases. The ground and the water
are closed-form in plan position. No flag draws from the stream, so a
falsifier changes only what it names.

All the water — the sea, every channel and each pond — is one slab on the
tile's own lattice: a cell holds water when any corner lies under its level,
so the sheet's rim runs under the banks, the shore and the rim. Ground never
lies within 0.9 mm of the water over it, so the two sheets that share the
lattice share no vertex and no plane.

Seven materials: delta ground (marsh, meadow, fields, mud, sand, seabed),
water (sea, channels, plumes, ponds), reed (the reeds and the hut's thatch),
timber (the hut, jetty, posts, stakes, logs and boat), bark, foliage
(willows and poplars), tile plinth (the slate rim and the skirt's section).

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

The collider is eight convex hulls joined in one mesh, built from points
only: the plinth up to the water, and the delta's plain in seven fans from
the apex, each from where it comes in over the back edge out to the coast or
a side. Boats sail the water; units walk the land.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 138000–142500 | 140150 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 7 distinct; face floors ground ≥51900, water ≥45300, reed ≥16880, timber ≥955, bark ≥627, foliage ≥5257, plinth ≥9560 | 7 slots; 53503 / 46711 / 17418 / 986 / 646 / 5420 / 9855 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.4000, 2.4000, 0.2960) m ± 0.01 | (2.4000, 2.4000, 0.2960), zmin 0 |
| Collider tris (eight hulls) | ≤ 360 | 174 |
| Export | written, size > 0, removed after measuring | 14562248 bytes |

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

### Delta invariants

A delta has no joinery. What makes this read as a delta is that its water
runs downhill down every channel to the sea, that its forks split the way
real ones do, that its levees hold the channels above the marsh, that its
islands stand out of the water, and that the reeds, trees, posts and logs
are rooted in it or float on it. Each face carries `Part`, `Ident` and
`Cap` tags so a shell's role and its foot can be named; every measurement
is then made on the shipped mesh by rays straight down onto the water's top
and onto the ground, along and across the channels' courses.

| Axis | Declared | Measured |
| --- | --- | --- |
| Water falls: along every mouth's course from the back edge through its forks, the water's surface every 4 mm, the largest rise from one sample to the next | ≤ 1e-6 m | 2e-7 m over 2863 samples |
| Width rule: at each fork, the wetted width across the parent 100 mm upstream and across each child 150 mm downstream, (sum of the children's widths squared) / the parent's squared | 0.88–1.12 | 0.960, 1.008, 0.991 |
| Fork angle: the angle between the two children's courses, each found from the wetted span's middle at 70 and 190 mm | 58–82° | 73.3°, 73.6°, 74.0° |
| Mouths reach the sea: along every course, water over the ground at every sample; the water at its end against the sea's level | no gap, ≥ 0.001 m deep; ≤ 0.002 m | no gap, 0.0034 m shallowest; −0.00004 m at all four |
| Levees: every 25 mm along every channel, each bank's crest (the highest ground out to three crest-distances) over the water at the channel's middle, and over the marsh behind it | ≥ 0.004 m; ≥ 0.0018 m | 0.0078; 0.0021 (228 stations) |
| Islands: the lowest ground over each island's core against the water round it — the sea for the three bars, the higher of the two channels either side for the three islands between forks | ≥ 0.0025 m | 0.0037–0.0050 |
| Water level: the open sea's top, median and largest excursion; each pond's top | level 0.150 ± 0.0015 m; ripple 0.001–0.006 m; ponds flat within 0.0004 m | 0.15004; 0.00244; 0.0000 |
| Water contained: the ground over every rim vertex and rim-edge midpoint of every water sheet (save the river's cut in the back edge) | ≥ 0.0015 m | 0.0025 over 2703 points; 19 at the cut |
| Reeds rooted: every blade's foot (its bottom cap) under the ground | 0.002–0.030 m, 4351 blades | 0.0036–0.0059 |
| Afloat: every floating log and the boat, the share of its height under the water; every stranded log sealed in the ground in each sector | 0.25–0.75; ≥ 0.0025 m | 0.33–0.55 (4); 0.0075–0.0095 (4) |
| Posts: every stilt, jetty post and weir stake, its foot under the bed and its top over the water | foot 0.004–0.050 m, top ≥ 0.003 m over | 0.0099–0.0155 (28); 0.0082 |
| Trees rooted: every trunk's foot under the ground | 0.004–0.050 m, 35 trunks | 0.0094–0.0114 |

## Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--uphill-channel` | water falls (a 12 mm swell raised mid-course on one channel: rises 0.00046 m between samples) | 17 |
| `--choke-branch` | width rule (one channel narrowed to 0.62 of its width: 0.767 at its fork) | 18 |
| `--splay-fork` | fork angle (one channel swung out 30° about its fork: 104.3°) | 19 |
| `--plug-mouth` | mouths reach the sea (a mouth dammed 6 mm over its water: 5 dry samples along its course) | 20 |
| `--breach-levee` | levees (a crevasse cut in one bank: a crest 0.0015 m under the water) | 21 |
| `--drown-islet` | islands (one bar's crest lowered 10 mm: 0.0059 m under the sea) | 22 |
| `--flat-sea` | water level (the sheet laid flat: ripple 0.00000 m) | 23 |
| `--short-sea` | water contained (the sheet's shoreward rim drawn 50 mm out to sea: −0.0020 m) | 24 |
| `--float-reeds` | reeds rooted (every reed raised 30 mm: feet −0.0264 m) | 25 |
| `--sink-logs` | afloat (the floating logs and the boat sunk 30 mm: 2.7–3.2 of their height under) | 26 |
| `--lift-hut` | posts (the hut, the jetty and the weir raised 30 mm: feet −0.0201 m) | 27 |
| `--float-trees` | trees rooted (the willows raised 40 mm: feet −0.0306 m) | 28 |

`--uphill-channel` raises the water alone, after the sheet's cells are
chosen, so the triangle count holds. `--choke-branch`, `--splay-fork`,
`--plug-mouth`, `--breach-levee` and `--drown-islet` reshape the ground,
so the water covers a few more or fewer cells; the triangle band is wide
enough that each reaches its own check. `--float-trees` lifts the willows
only: the poplars stand tallest and would carry the envelope with them.

## Run

```bash
blender --background --python river_delta_tile.py --
blender --background --python river_delta_tile.py -- --skip-decimate
blender --background --python river_delta_tile.py -- --stray-vert
blender --background --python river_delta_tile.py -- --lift-z
blender --background --python river_delta_tile.py -- --uphill-channel
blender --background --python river_delta_tile.py -- --choke-branch
blender --background --python river_delta_tile.py -- --splay-fork
blender --background --python river_delta_tile.py -- --plug-mouth
blender --background --python river_delta_tile.py -- --breach-levee
blender --background --python river_delta_tile.py -- --drown-islet
blender --background --python river_delta_tile.py -- --flat-sea
blender --background --python river_delta_tile.py -- --short-sea
blender --background --python river_delta_tile.py -- --float-reeds
blender --background --python river_delta_tile.py -- --sink-logs
blender --background --python river_delta_tile.py -- --lift-hut
blender --background --python river_delta_tile.py -- --float-trees
blender --background --python river_delta_tile.py -- --output delta.png
```

Smoke passes no flags.

The hero does not turn the piece (`HERO_YAW_DEG` 0) and looks down on the
tile from the front, 12° to the left and about 40° over it, the way a map
tile is seen on a game board: the river comes in at the back, the forks
fan out toward the camera, and the sea, the plumes and the bars lie in
front. Seen from this high, the floor behind the tile is the backdrop, so
the warm wedge drops its pool on the floor off to the left, where it
reaches no water to glare off, rather than on the back wall. Framing
measures fill x 0.700, y 0.878, margins left 0.181, right 0.119, bottom
0.061, top 0.061; the asset-quality floors pass.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` and `11` for
`gallery_asset_quality.check_asset_quality`, both on the `--output` path.
`15`–`16` are the hygiene and grounded family; `17`–`29` are file-local.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or not one tile and its water |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 7 distinct slots, or a face-count floor missed |
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
| 17 | Water rising somewhere along a channel's course (`--uphill-channel`) |
| 18 | Width rule: a fork's children's widths squared off their parent's (`--choke-branch`) |
| 19 | Fork angle: two children's courses outside the band (`--splay-fork`) |
| 20 | Mouths: a course dry somewhere, or its end off the sea's level (`--plug-mouth`) |
| 21 | Levees: a crest not over the water, or not over the marsh behind it (`--breach-levee`) |
| 22 | Islands: an island's core not standing out of the water round it (`--drown-islet`) |
| 23 | Water: the sea off its level or its ripple outside the band, or a pond not flat (`--flat-sea`) |
| 24 | Water contained: a sheet's rim not under the ground (`--short-sea`) |
| 25 | Reeds: a blade's foot out of its band under the ground (`--float-reeds`) |
| 26 | Afloat: a floating log or the boat out of its draft band, or a stranded log not sealed (`--sink-logs`) |
| 27 | Posts: a stilt, jetty post or stake's foot out of its band, or its top not over the water (`--lift-hut`) |
| 28 | Trees: a trunk's foot out of its band under the ground (`--float-trees`) |
| 29 | Collider triangle count above ceiling |
