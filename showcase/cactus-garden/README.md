# Cactus garden

A showcase piece, not an example, and the fifth in the `nature` category.
It builds a procedural, game-ready Sonoran cactus garden on a raised
sand-and-gravel disc:

- a sand disc 3.0 × 2.6 m, a low mound drifted up round the plants' feet,
  its rim rolled down to the floor. The sand carries wind ripples, a lag of
  dark basalt and rusty grains, and its cut edge shows red-brown sand over
  a pale caliche band over gravel;
- a saguaro 2.20 m over the sand at its foot: a column of fourteen pleated
  ribs, rounded on the crests and creased in the valleys, a little
  narrower at the foot, pinched once where a drought year slowed it, and
  domed at the crown. Three arms leave the trunk at 0.80, 1.06 and 1.28 m
  through a smooth collar, the ribs opening out of it; each runs out, turns
  up through a wide elbow and domes at its tip. A row of felt areoles runs
  down every rib crest, each a cushion with a radiating cluster of three
  spines, one near the centre and two splayed. A corky boot at the foot and
  two scars higher up follow the ribs, a few millimetres proud of the skin.
  Three cream flowers sit on the crown and one on the right arm's tip,
  each a green floral tube sunk in the skin, a cup of eight petals and a
  yellow stamen cushion;
- a fishhook barrel cactus, 0.48 m tall and 0.43 m across, eighteen ribs on
  a round-shouldered profile with a woolly crown. Every areole carries
  three pale radials and a red hooked central spine that curls down at its
  tip; a ring of seven yellow fruit stands round the crown;
- a prickly pear of twelve broad paddles in four tiers: three rooted in
  the sand, the rest grown pad on pad, each pad's narrow base fused into
  its parent's rim by a short constricted joint, with no stalk between
  them, and turned a little off its parent's plane so the clump fans out.
  Each pad is 0.22–0.30 m long, a superellipse with broad shoulders, thick
  almost to its rim and swollen at the centre (26 mm), sage blue-green,
  flushed purple at the rim, dotted on both faces with glochid tufts on a
  diagonal lattice; five of the outer pads carry magenta fruit on their
  top rims;
- a blue agave rosette of thirteen leaves in a golden-angle spiral, each
  keeled underneath and hollowed on top, with a brown terminal spine;
- five weathered sandstone rocks, each a lump cleaved by three planes and
  sunk into the sand, banded with bedding and patched with desert varnish;
  a sun-bleached mesquite branch with two twigs and two fallen saguaro ribs
  lying half-buried; six tufts of dry bunchgrass; gravel pebbles.

Every seeded draw comes from `random.Random(SEED)` in `plan_garden()`,
before anything is built. Per-areole variety (spin, spine tilts and
lengths) comes from a closed-form hash of the areole's indices, so no flag
can shift it. Which pebble candidates are used is decided once against the
default layout (`Layout`), which also refuses a pad that grows downward or
a tuft off the disc.

Ten materials, one per substance: sand, cactus skin (saguaro, barrel and
pads, told apart by a face zone), spine (spines, areole felt, hooked
centrals and glochids), fruit, flower, agave, rock, gravel, dry wood (the
branch, the fallen ribs and the saguaro's boot and scars) and dry grass.
Point attributes carry what the shaders need: `Rib` (1 on a rib crest, 0 in
a valley), `Along` (height up the saguaro, the run along a leaf, spine,
petal or blade, a pad's radius) and `Skirt` (the disc's cut edge). A `Tone`
face attribute is seeded per part. Gravel is flat-shaded, as chips;
everything else is smooth-shaded, and every material boundary and every
fold sharper than 60° (32° on the rocks, so each cleavage plane stays a
broken face) is a hard edge.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a disc 3.00 × 2.61 m, its mound 0.14 m high, the saguaro's
crown flowers 2.38 m off the floor. The outer AABB is 2.9950 × 2.6077 ×
2.3754 m, read off the vertices. The sand sets X and Y, a crown flower the
top; the sand's underside is the ground. The collider is the convex hull
of the sand disc alone, coarse: players brush through the plants.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 44700–46000 | 45364 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 10 distinct; ≥3400 sand, ≥8400 skin, ≥12100 spine, ≥420 fruit, ≥900 flower, ≥440 agave, ≥990 rock, ≥550 gravel, ≥610 wood, ≥1120 grass faces | 10 slots; 3694 / 9332 / 13254 / 432 / 976 / 481 / 1080 / 600 / 666 / 1222 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.9950, 2.6077, 2.3754) m ± 0.01 | (2.9950, 2.6077, 2.3754), zmin 0 |
| Collider tris (sand hull) | ≤ 120 | 112 |
| Export | written, size > 0, removed after measuring | 3772220 bytes |

No falsifier changes the triangle count: every falsifier run measured
45364 tris. Only `--lean-saguaro` moves the envelope, by 6.5 mm in Z
against a 10 mm tolerance, because it tips the flowers that set the top.

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

Nearly nine hundred spine clusters sit on straight vertical ribs, and a
cluster translated straight up a rib keeps every face whose plane holds the
vertical on the same plane. Each cluster is therefore turned about its own
normal by a hashed spin, and each spine's tilt and length are hashed too,
so no two clusters share a plane.

### Arms, pads, the column, the ribs, the spines, the bedding and the cover

These are the organic invariants. A cactus garden has no joinery, but a
cactus is jointed all the same: a saguaro's arms grow out of its trunk, a
prickly pear's pads grow out of each other, and every spine grows out of an
areole in the skin. A saguaro stands plumb, its ribs stand at even
stations round the column, and every plant stands in the sand, not on it.

| Axis | Declared | Measured |
| --- | --- | --- |
| Arm joints: each arm's deepest vertex inside the trunk, measured radially from the trunk's axis at the vertex's own height (a ray out onto the trunk shell alone) | 3 arms, each 0.080–0.160 m | 3; 0.1154–0.1222 m |
| Pad joints: each pad's joint, the extreme vertex down its long axis (principal axis). A root pad's joint lies under the sand; a child's lies inside another pad (ray parity), and its seat is how far the child's axis runs on inside that pad before it leaves | 9 child pads, each 0.022–0.040 m | 9; 0.0297–0.0313 m |
| Saguaro: the trunk's axis through a low and a high slab's centroids, its lean; the mass centre of trunk and arms off the low slab's centroid in plan; the height from the sand at the foot to the crown; the crest diameter 1 m up | lean ≤ 1°; mass ≤ 0.050 m off; height 2.20 ± 0.05 m; diameter 0.30–0.37 m | 0.000°; 0.0012 m; 2.2004 m; 0.3376 m |
| Ribs: the ring nearest 1 m up the trunk (measured in the trunk's own frame, turned upright about its axis) and the barrel's mid ring; the crests as local maxima of radius about the ring's centroid; the spread of the angular gaps between crests | 14 trunk and 18 barrel crests; spread ≤ 2° | 14 and 18; 0.000° and 0.000° |
| Spines: every spine cluster, hooked central and glochid tuft, its deepest vertex inside the skin of the cactus whose surface is nearest its centre (ray parity, distance to the nearest face) | 0.0030–0.0080 m | 898 clusters; 0.00363–0.00602 m |
| Bedding: the saguaro and the barrel, each body's most-buried vertex in each of eight sectors round its foot, under the sand straight above it, the shallowest sector; each root pad's joint under the sand; each agave leaf's lowest vertex under the sand | bodies and root pads 0.025–0.150 m; 13 leaves, each 0.020–0.100 m | saguaro 0.0829, barrel 0.0550, root pads 0.0498–0.0499 m; leaves 0.0424–0.0531 m |
| Cover joined: every shell unioned with the sand through BVH overlaps | every shell joined | 1118 shells; 0 loose |

Two measurements needed care. A nearest face's normal is no witness of
inside and outside near a thin pad's rim, where the nearest face can stand
edge-on to the point: a joint vertex read 0.11 m "inside" a pad it was
nowhere near. Every inside test is ray parity. And a leaning trunk's rings
are cut obliquely by a horizontal slab, which biases the slab centroids a
fifth of a degree; the rib budget groups a ring by gaps in height rather
than by one exact height, so the tipped trunk, turned back upright, still
shows whole rings.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code, and every other piece-specific budget stayed
green on that run.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--short-arm` | arm joints (every arm drawn 70 mm out along its bearing, its collar still in the trunk: 0.0465–0.0545 m) | 17 |
| `--shallow-pad` | pad joints (the top right pad slid 22 mm out of its parent's rim, still inside it: seat 0.0093 m) | 18 |
| `--lean-saguaro` | saguaro plumb and mass over its foot (the whole saguaro tipped 3.5° about its foot: lean 3.702°, mass centre 0.0606 m off) | 19 |
| `--skew-ribs` | ribs at equal stations (one trunk rib turned 7° off its station: spread 13.908°) | 20 |
| `--float-spines` | spines rooted (every cluster, hook and glochid lifted 3 mm off the skin, still touching it: 0.00096 m) | 21 |
| `--perch-barrel` | bedding (the barrel raised 35 mm, its foot still in the sand: shallowest sector 0.0200 m) | 22 |
| `--float-cover` | cover joined (every pebble, grass blade, branch and fallen rib lifted 50 mm: 109 of 1118 shells loose) | 23 |

Each falsifier moves only what its budget measures, and none is sized
past the point where a second budget would see it. `--short-arm` moves each
arm rigidly, so its spines stay rooted, and its areoles are chosen by arc
length along the arm, not by distance from the trunk, so the count does not
change. `--shallow-pad` slides a pad that carries no pad, so no other seat
moves. The lifts in `--float-spines` and `--perch-barrel` leave every part
still touching its host, so the cover stays joined. `--lean-saguaro`
passes the rib budget because that budget measures in the trunk's own frame.

## Run

```bash
blender --background --python cactus_garden.py --
blender --background --python cactus_garden.py -- --skip-decimate
blender --background --python cactus_garden.py -- --stray-vert
blender --background --python cactus_garden.py -- --lift-z
blender --background --python cactus_garden.py -- --short-arm
blender --background --python cactus_garden.py -- --shallow-pad
blender --background --python cactus_garden.py -- --lean-saguaro
blender --background --python cactus_garden.py -- --skew-ribs
blender --background --python cactus_garden.py -- --float-spines
blender --background --python cactus_garden.py -- --perch-barrel
blender --background --python cactus_garden.py -- --float-cover
blender --background --python cactus_garden.py -- --output cactus.png
```

Smoke passes no flags.

The hero keeps the piece unturned (`HERO_YAW_DEG` 0°) and looks in from
the south-south-west, a little above the disc, so the saguaro stands at
the back with an arm to each side, the barrel in front of it on the left,
the pear clump behind the agave on the right. The fill is 0.506 × 0.883.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene, grounding, joint, seat and plumb family. `20`–`23` are
file-local. `24` is the asset-quality floor on the render path:
`check_asset_quality` returns 11, which this piece already spends on the
collider ceiling, so the call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or no sand, trunk or barrel shell |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 10 distinct slots, or a face-count floor missed |
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
| 17 | Arm joints: not 3 arms, or an arm's deepest vertex inside the trunk outside 0.080–0.160 m (`--short-arm`) |
| 18 | Pad joints: not 9 child and 3 root pads, or a child's seat outside 0.022–0.040 m (`--shallow-pad`) |
| 19 | Saguaro: lean above 1°, mass centre more than 0.050 m off its foot, height off 2.20 ± 0.05 m, or crest diameter outside 0.30–0.37 m (`--lean-saguaro`) |
| 20 | Ribs: not 14 trunk or 18 barrel crests, or a crest-gap spread above 2° (`--skew-ribs`) |
| 21 | Spines: a cluster's deepest vertex under the skin outside 0.0030–0.0080 m (`--float-spines`) |
| 22 | Bedding: the saguaro, the barrel or a root pad outside 0.025–0.150 m under the sand, or an agave leaf outside 0.020–0.100 m (`--perch-barrel`) |
| 23 | Cover: a shell not joined to the sand (`--float-cover`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
