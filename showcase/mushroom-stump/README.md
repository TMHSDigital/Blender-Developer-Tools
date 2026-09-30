# Mushroom stump

A showcase piece, not an example, and the seventh in the `nature` category.
It builds a procedural, game-ready tree stump on its patch of forest floor:

- the stump: one lathe about a plumb axis, sawn off 0.50 m above the soil
  and 0.62 m across the bark at the cut. The bole widens toward the soil
  and flares through five buttresses into the ground. Its bark is plated
  and cut by sixteen narrow V furrows that wander up the bole;
- two patches where the bark has peeled away. The sapwood is the trunk's
  own surface 26 mm under the plate crests, weathered grey-brown, streaked
  up the grain with fine checks and the winding galleries bark beetles cut
  under the bark. The torn bark round it curls up to 6 mm proud in a
  ragged lip that shows the rust-brown inner bark, and twelve bark flakes
  (seven and five) lift off the edge, their roots set in the bark, curling
  out over the wood;
- the felling on the top: the back cut carries growth rings round a dark
  heartwood and a pale sapwood band, weathered grey from the rim in, faint
  chainsaw streaks, and five radial drying checks, each a V groove that
  deepens toward the rim and notches the bark there. Beyond the hinge
  chord, 0.172 m from the axis toward the fall, the undercut floor lies a
  34 mm step lower, and the step face is its own strip of faces, cut into
  the top along both of its edges;
- the holding wood: a low band of torn fibres along the step's edge, over
  the middle two thirds of the chord — its back foot set into the back
  cut, its front face running down the step to below the undercut floor,
  the fibres up to 29 mm tall, leaning toward the fall, now and then a longer
  splinter. Past its ends the step is a clean sawn face;
- five surface roots, one out of each buttress, lying in the soil along
  their run and diving into it at the tip;
- moss: four thin cushions, one broad and one small on the shaded north
  flank and one in each of the two root crotches beside it. Each is a
  shell laid on the bark as built, plates and furrows and all, about 10 mm
  thick at its heart and thinning to a rim tucked 2 mm under the bark; the
  rim is lobed and runs out in tongues along the furrows, and 19 satellite
  tufts sit round the rims, so no patch ends on a hard slab edge;
- two tiers of turkey-tail brackets, six thin, lobed, wavy shelves with
  narrow brown, rust, tan and blue-grey bands, a cream margin and a cream
  pore surface, their back edges set into the bark;
- three fly agarics on the soil in front of it — a mature flat cap, a domed
  one and a button — each a red cap flecked with white warts on white
  pleated gills, on a white stipe with a bulbous, ringed volva and a hanging
  skirt;
- two clusters of honey fungus, seven out of a root and six out of the
  stump's foot: thin curved stipes with a ring, dark at the foot and cream
  at the top, under convex, umbonate honey-brown caps with dark scales on
  the crown and cream gills. Neighbours alternate tall and close in with
  short and leaning out, so the caps shingle;
- a soil disc 1.7 × 1.6 m rising toward the back, with 77 fallen leaves in
  drifts, two fern clumps either side of the stump, three forked twigs and
  four broken pebbles. The ferns are twelve bipinnate fronds, 0.40–0.64 m,
  grown by the frond builder of `fern-mossy-rock` (copied inline, not
  imported) at about half its size: young fronds stand up, old ones arch
  out and down; each carries 9–11 alternate pinnae a side, each pinna cut
  into up to three pairs of pinnules, with rusty sori on the underside.

Every draw comes from `random.Random(SEED)` in `plan_stump()`, before
anything is built: peel and moss outlines, flakes and tufts, shelf sizes
and swing, the roots' reach and meander, the hinge fibres, the mushrooms,
the fronds, twigs, pebbles and leaves; per-pinna and per-cap variety comes
from a closed-form hash of indices. No flag draws from the stream, so a falsifier
changes only what it names.

Twelve materials, one per substance: bark, wood (sapwood, the sawn end
grain and the torn holding wood), moss, turkey tail, fly-agaric cap,
honey-fungus cap, mushroom flesh (stipes and gills), soil, leaf litter,
fern, pebble and twig. A `Peel` point attribute is 0.5 exactly on each
patch's outline, so the bark shader cuts the torn edge between vertices;
a flake's underside (`Zone` 1) is inner bark. A `Notch` point attribute is
0 on the back cut and 1 on the undercut floor. Moss faces carry their
distance from the cushion's heart in `Zone`, which thins the colour
toward the rim. Fern pinnae carry a `LeafUV` map across and along each
pinna for the midrib and sori (the packed `UVMap` stays first and active).
The end grain draws its rings from a `Radial` point attribute and its
cracks from a `Check` point attribute that is 1 only on the floor of each
groove; the caps, gills, stipes and brackets take their zones from a
`Zone` face attribute; the fly agaric's warts are a Voronoi field thinning
toward the margin. Everything organic is smooth-shaded; the torn holding
wood and the pebbles are flat-shaded facets. Every material boundary is a
hard edge, so the sawn rim stays crisp against the bark.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a stump 0.62 m across the bark at the cut, sawn 0.50 m above
the soil at its axis, on a soil disc 1.7 × 1.6 m. The outer AABB is
1.935 × 1.628 × 0.689 m. Two fern fronds set X, the soil sets Y, and the
tallest hinge fibre the top. The soil's underside is the ground. The collider is the convex hull of
the stump alone, round and unfurrowed, down to the soil: players walk
through ferns and step over roots.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 56150–57250 | 56710 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 12 distinct; ≥4000 bark, ≥1530 wood, ≥2770 moss, ≥1440 bracket, ≥600 agaric, ≥1640 honey, ≥3640 flesh, ≥1580 soil, ≥1100 litter, ≥16100 fern, ≥345 stone, ≥190 twig faces | 12 slots; 4441 / 1702 / 3080 / 1596 / 672 / 1820 / 4050 / 1758 / 1232 / 17884 / 384 / 210 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.9351, 1.6283, 0.6888) m ± 0.01 | (1.9351, 1.6283, 0.6888), zmin 0 |
| Collider tris (stump hull) | ≤ 75 | 66 |
| Export | written, size > 0, removed after measuring | 5733424 bytes |

No falsifier changes the triangle count, and only `--tall-hinge` moves the
envelope, 7.2 mm up against the 10 mm tolerance: they move parts or
reshape the foot, never add or remove faces. The upper lathe carries a
fixed ring count, so moving the foot keeps the topology; the step's chord
scales with `--fat-stump`, so the cuts along it cross the same edges.

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. The plan is seeded and nothing else is random; two
default runs print identical measurements, and 4.5.11 and 5.1.2 print the
same measurements as 5.2.1 (the glTF differs by 16 bytes).

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

The coplanar budget caught three faults on the way. Two honey-fungus
clusters first grew their members at one height and one reach, so their
caps ran into each other and two gill fans met a crown in one plane; the
members now alternate tall and close in with short and leaning out. Leaves
closer than their own length overlapped, and two lay on one soil face in
one plane; they are now spaced by their half-lengths and each rolls a few
degrees about its midrib. Two fern fronds in one clump carried pinnae in
one plane; each frond now has its own twist phase. Later, `--perch-stump`
moved the second bracket tier's neighbour, a honey cap, onto a shelf's
underside plane; the tier went up the bole and the cluster round it.
The remodel met it three more times. Moss bases laid a fixed depth under
the curved bark met a tuft's base in one plane; each cushion's base now
bellies into the stump by its own depth and each tuft's base is one cone
from its rim. Two shingled honey caps shared a plane once the stump grew
finer; each cap now tips its own small hashed way. And pinnae are
turned about their own axes, as in `fern-mossy-rock`, until no two
within range share a plane.

### Organic invariants

A stump has no joinery. What makes it read as a stump is that it grows out
of the ground rather than standing on it, that its roots lie in the soil,
that the saw left it level and it is the size it says, that its fungi grow
out of it and out of the soil rather than resting on them, and that moss
grows where the sun does not reach.

| Axis | Declared | Measured |
| --- | --- | --- |
| Stump sealed: azimuth sectors round the stump's centroid holding a stump vertex at least 5 mm under the soil straight above it (a ray down onto the soil shell alone) | 8 of 8 | 8 of 8 |
| Caps seated: for each cap, the deepest vertex of its own stipe inside it (signed distance by ray parity) | 16 caps on 16 stipes, each 0.003–0.030 m | 16; 0.0052–0.0137 |
| Cut level: plane fit on the back cut's end grain (the check grooves and the undercut floor, `Notch` > 0, left out) | tilt ≤ 1.0° | 0.0894° |
| Real-world size: diameter across the bark 5–50 mm under the fit plane (mean of the X and Y extents); the fit plane's height at its centre above the soil | 0.62 ± 0.015 m and 0.50 ± 0.015 m | 0.6210 and 0.4966 |
| Roots bedded: each root's vertices outside the stump, binned at 0.05 m from the stump's axis; every bin's most-buried vertex under the soil (bins where the root leaves the buttress are sealed by the stump and skipped) | 5 roots, every station ≥ 0.006 m under | 5; shallowest 0.0547 over 14 stations |
| Mushrooms rooted: each stipe's deepest vertex in its host — under the soil straight above it for a fly agaric, inside the root or the stump for honey fungus | 16 stipes, each 0.008–0.070 m | 16; 0.0248–0.0382 |
| Brackets rooted: each shelf's deepest vertex inside the stump shell (signed distance to the nearest bark face along its normal) | 6 shelves, each 0.006–0.050 m | 6; 0.0183–0.0211 |
| Moss facing: of the moss top faces (facing away from the bark under them), the area fraction whose normal faces up (z > 0.25) or north into the shade (y > 0.5) | 23 cushions and tufts, ≥ 0.85 | 23; 0.9460 |
| Ground cover joined: soil, leaves, fern rachises and pinnae, twigs and pebbles, unioned by BVH overlap | 339 shells, all joined to the soil | 339; 0 loose |
| Felling: the undercut floor's mean depth under the back-cut plane (its end-grain vertices, `Notch` 1, checks left out); the torn hinge band's tallest vertex over that plane | step 0.028–0.041 m; hinge 0.018–0.034 m | 0.0346 over 189 vertices; 0.0286 |
| Peel: round each peel, from the stump's own vertices about its axis (the pith), the median radius of the torn lip (`Peel` 0.2–0.5) less that of the exposed sapwood (`Peel` > 0.5); each bark flake's deepest vertex inside the stump | 2 peels, each 0.020–0.034 m; 12 flakes, each 0.002–0.020 m | 0.0268 and 0.0249; 12, 0.0042–0.0150 |
| Moss conforms: the greatest height of any moss top vertex (`Zone` < 1.5) over the bark, along the normal of the nearest stump face | 0.006–0.016 m | 0.0104 |

The stump's foot follows the soil: its four lowest rings sit a fixed
offset above (and the lowest 45 mm under) the soil straight under each
vertex, read back by raycast off the built soil, and the ground rises
toward the back. A stump sunk by the soil at its axis alone, the rule
`terrain-scatter`'s stones first shipped with, leaves daylight under its
downhill side.

The felling budget is why the step is measured, not assumed: a real
felled stump has a flat back cut and, on the fall side, the undercut a
few centimetres lower, with the hinge's holding wood torn along the edge
between them. The first draft stood a comb of splinters, 13 cm tall, in
the middle of a level cut. The peel budget holds the exposed wood as the
trunk's own surface a bark's thickness under the torn bark; the first
draft's patch read as a plank pasted on. The moss budget caps the moss's
height over the bark: the first draft's 26 mm dome over the plate crests
filled the furrows and read as a slab.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
4.5.11 and exited its declared code. Every run measured the default's
triangle count, and every one but `--tall-hinge` its outer AABB.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--perch-stump` | stump sealed all round (the foot set from the soil at the axis alone: sealed in 6/8 sectors) | 17 |
| `--float-caps` | caps seated on their stipes (every cap moved 24 mm up its axis: stipe bite −0.0156 to −0.0100 m) | 18 |
| `--tilt-cut` | saw cut level (the cut plane turned 5° about the hinge chord: measured 4.9584°) | 19 |
| `--fat-stump` | stated size (every stump radius × 1.08: 0.6706 m across) | 19 |
| `--arch-roots` | roots bedded along their run (each root's middle raised 120 mm: shallowest station −0.0524 m) | 20 |
| `--float-mushrooms` | stipes rooted in their host (every mushroom moved 50 mm off its host: −0.0249 to −0.0032 m) | 21 |
| `--float-brackets` | brackets rooted in the bark (every shelf moved 35 mm off the bark: −0.0164 to −0.0131 m) | 22 |
| `--sunny-moss` | moss on up- and shade-facing surfaces (every cushion and tuft turned half round the stump: 0.4270) | 23 |
| `--float-cover` | ground cover joined (every leaf lifted 25 mm off the soil: 77 of 339 shells loose) | 24 |
| `--flat-felling` | felling step (the undercut floor sawn level with the back cut: step 0.0006 m) | 25 |
| `--tall-hinge` | felling hinge band low (every torn fibre × 1.25: tallest 0.0358 m; the AABB's top rises 7.2 mm, inside its 10 mm tolerance) | 25 |
| `--flush-peel` | torn bark over the sapwood (no bark thickness and no lip: −0.0015 and −0.0011 m) | 26 |
| `--float-flakes` | flakes rooted in the bark (every flake moved 20 mm off the bark along its normal: −0.0108 to 0.0011 m) | 26 |
| `--slab-moss` | moss conforms (every cushion the old 26 mm dome over the plate crests: 0.0360 m) | 27 |

`--tilt-cut` turns the cut about the hinge chord, so the holding wood and
the stump's height at its axis stay put and only the tilt fails.
`--fat-stump` scales the stump and leaves the soil, the roots and the
holding wood's height alone, so only the diameter fails. `--float-caps`
at 30 mm put one honey cap's crown on a neighbour's gill plane and exited
15; 24 mm keeps it on 18. `--float-mushrooms` moves soil- and root-grown
mushrooms straight up and stump-grown ones out along the bark's normal:
lifted, those would have stayed inside the flaring foot. `--tall-hinge` is
sized to the tolerance: the tallest fibre sets the top of the envelope,
and × 1.25 clears the 0.034 m band by 1.8 mm while the top moves 7.2 mm of
its 10 mm. `--arch-roots` went from 90 to 120 mm when the roots were
shortened for the smaller disc and bedded deeper: at 90 mm the shallowest
station still lay 3.4 mm under the soil, a fail by only 2.6 mm.

## Run

```bash
blender --background --python mushroom_stump.py --
blender --background --python mushroom_stump.py -- --skip-decimate
blender --background --python mushroom_stump.py -- --stray-vert
blender --background --python mushroom_stump.py -- --lift-z
blender --background --python mushroom_stump.py -- --perch-stump
blender --background --python mushroom_stump.py -- --float-caps
blender --background --python mushroom_stump.py -- --tilt-cut
blender --background --python mushroom_stump.py -- --fat-stump
blender --background --python mushroom_stump.py -- --arch-roots
blender --background --python mushroom_stump.py -- --float-mushrooms
blender --background --python mushroom_stump.py -- --float-brackets
blender --background --python mushroom_stump.py -- --sunny-moss
blender --background --python mushroom_stump.py -- --float-cover
blender --background --python mushroom_stump.py -- --flat-felling
blender --background --python mushroom_stump.py -- --tall-hinge
blender --background --python mushroom_stump.py -- --flush-peel
blender --background --python mushroom_stump.py -- --float-flakes
blender --background --python mushroom_stump.py -- --slab-moss
blender --background --python mushroom_stump.py -- --output stump.png
```

Smoke passes no flags.

The hero turns the piece half round (`HERO_YAW_DEG` 180°, about Z only),
so the shaded north flank with its moss faces the camera, and raises the
camera over the south-west corner so the cut face, its rings, checks and
the felling step read from above; the tree fell to the camera's right, so
the step and its torn band are seen three-quarter on. The fly agarics
stand in the foreground, the brackets stand out in profile on both flanks
and a fern clump stands either side of the stump: fill 0.709 × 0.833.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene, grounding, sealing, seating and size family. `20`–`27` are
file-local. `28` is the asset-quality floor on the render path:
`check_asset_quality` returns 11, which this piece already spends on the
collider ceiling, so the call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or no stump or soil shell |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 12 distinct slots, or a face-count floor missed |
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
| 17 | Stump not sealed in the soil in all 8 sectors (`--perch-stump`) |
| 18 | Caps seated: not 16 caps on 16 stipes, or a stipe's bite in its cap outside its band (`--float-caps`) |
| 19 | Saw cut tilted over 1°, or the stump off its stated 0.62 m diameter or 0.50 m height (`--tilt-cut`, `--fat-stump`) |
| 20 | Roots bedded: not 5 roots, or a station along a root not under the soil (`--arch-roots`) |
| 21 | Mushrooms rooted: not 16 stipes, or a stipe's depth in its host outside its band (`--float-mushrooms`) |
| 22 | Brackets rooted: not 6 shelves, or a shelf's deepest vertex in the bark outside its band (`--float-brackets`) |
| 23 | Moss: not 23 cushions and tufts, or under 0.85 of the moss top area facing up or north (`--sunny-moss`) |
| 24 | Ground cover: not 339 shells, or a leaf, frond part, twig or pebble not joined to the soil (`--float-cover`) |
| 25 | Felling: not one hinge band, the undercut floor off its step under the back cut, or the tallest hinge fibre outside its band (`--flat-felling`, `--tall-hinge`) |
| 26 | Peel: the torn bark's stand over the sapwood outside its band at either peel, not 12 flakes, or a flake's root in the bark outside its band (`--flush-peel`, `--float-flakes`) |
| 27 | Moss conforms: the moss's greatest height over the bark outside its band (`--slab-moss`) |
| 28 | Asset-quality floor (render path only; remapped from 11) |
