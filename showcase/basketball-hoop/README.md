# Basketball hoop

A showcase piece, not an example, and the first in the `sports` category.
It builds a procedural in-ground basketball goal standing on a patch of
driveway court:

- a two-pour concrete pad, 5.2 × 6.6 m and 100 mm thick, split by an
  expansion joint with a sunk sealant strip; the second pour sits 1.5 mm
  under the first;
- a painted court in faded, worn paint: a baseline, a filled key with lane
  lines, a block and three ticks each side, a free-throw line and circle,
  and part of a three-point arc cut off by the pad's edges;
- two pebbled size-7 basketballs with black seams, one on the court and
  one by the pole's foot, each resting on the concrete;
- a base plate sunk into the slab with four gussets and four anchor bolts
  set through it into the concrete, each with a washer and a hex nut;
- a 6 in square steel pole swept in one piece from inside the plate,
  through an S-shaped gooseneck with a welded gusset web inside each bend,
  up into the mast behind the board;
- a square navy pad on the pole, split into three panels by seam grooves,
  with a hook-and-loop flap closing it up one corner;
- a collar carrying two diagonal support braces up to the board's lower
  back rail;
- two bolted clamp sleeves and standoffs carrying the board on a
  rail-and-stile back frame;
- a backboard in a 50 mm satin aluminium frame, with a navy edge pad
  along its bottom, a painted red border and a painted shooter's square;
- a regulation orange rim on a breakaway mount: a tapered bracket, a hinge
  barrel across its heel and a spring housing on top, bolted through a
  flange plate, two struts and twelve welded net hooks;
- a white cord net: twelve loops hung on the hooks, 24 strands that cross
  in a tapered diamond mesh, and a knot at each of the 72 crossings.

The pole, gooseneck and mast are one sweep of a rounded-square section,
because a bent bar is one bar. The straight run of the gooseneck is solved
from the mast's offset (`gooseneck_path()`), so the mast always lands
behind the standoffs. Each bend web is outlined from the bend's own inner
arc (`bend_webs()`), a bite inside the tube. Each brace is a tube between
two named stations. Its foot sits in the middle of the collar wall and its
head sits inside the lower rail. Pad, collar, clamps and cap are the pole
section grown by an offset, so every sleeve is a true parallel of it.

The rim follows regulation: the top of the ring is 3.05 m above the court
surface, its inside diameter is 0.457 m, and its inner edge sits 0.151 m
off the board face. The bottom line of the shooter's square has its top
edge level with the rim. Each net loop is a torus threaded across the hook
eye. Its cord passes through the eye and bears 1.5 mm into the hook's
lower inside, so the loop hangs *on* the hook rather than floating near it.

The court markings are a driveway layout, not regulation: a 2.7 m lane,
the free-throw line 2.98 m off the board face, a 4.2 m arc about the
basket centre. They are scaled to the pad, so the key, circle and arc all
fit on it.

Every paint line is a strip sunk into its own slab and standing proud of
it. Groups that overlap never share a plane: each has its own top and
sink (baseline 2.2 / 2.6 mm, lane lines 1.8 / 2.0, free-throw line
2.2 / 2.6, key fill 1.0 / 1.4, lane marks and circle 1.4 / 3.0, arc
1.8 / 2.0). Lines stop 8 mm short of the joint gap, and the free-throw
circle is 6 mm wider than the lane so its ends are clear of the lane
lines' side faces. The base plate is sunk 4 mm into the slab rather than
laid on it, so its underside never lands on the slab top. Each ball is a
UV sphere bearing 2 mm into the slab; its four seams are tori just under
its surface, turned so none runs through the contact point.

Paint on the board is thin annuli sunk 1 mm into the board. They stand
proud by different amounts (border 0.8 mm, square 1.2 mm), and the
border is 44 mm wide so its inner edge clears the square's bottom line.
The two bolt heads on each clamp face stand 1 mm apart so their caps
never share a plane.

Bevels run once per material with `material=` set. On the first run,
without it, the board's chamfer faces took slot 0 and the board shell
classified as steel.

Shading follows what each part is. Round stock (ring, cord, balls,
braces) is smooth-shaded. Chamfers, material boundaries and bends over
35° stay sharp, and so does a flat face meeting a much narrower facet, so
the pole's flats read flat and its corner fillets read round. The steel
is near-black satin powder coat and the frame satin aluminium, each with
a studio reflection term in the material (after `espresso-machine`), so
neither reads as grey plastic on the dark stage.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 5.2 × 6.6 m court pad; 1.83 × 1.05 m board with its bottom
2.90 m above the court; pole axis 1.22 m behind the board face. The outer
AABB is 5.200 × 6.600 × 4.050 m; the pad sets the footprint, and the pole
cap on the 100 mm slab sets the height. The convex collider wraps the pad
and the hoop together (44 tris).

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 18500–20500 | 19564 |
| LOD1 ratio | 0.32–0.62 of base | 0.4984 |
| LOD2 ratio | 0.10–0.35 of base | 0.2183 |
| Materials | exactly 12 distinct; face floors ≥2200 steel, ≥45 board, ≥28 board paint, ≥850 rim, ≥2400 net, ≥330 pad, ≥120 aluminium, ≥90 concrete, ≥440 court line, ≥12 key, ≥900 ball, ≥2000 seam | 12 slots; 2546 / 54 / 32 / 970 / 2784 / 382 / 144 / 108 / 504 / 12 / 1024 / 2310 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (5.200, 6.600, 4.050) m ± 0.01 | (5.2000, 6.6000, 4.0500), zmin 0 |
| Collider tris | ≤ 220 | 44 |
| Export | written, size > 0, removed after measuring | 1454192 / 1454192 / 1454180 bytes (4.5.11 / 5.1.2 / 5.2.1) |

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. Construction uses no RNG; two default runs print
identical measurements.

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

### Joint fit, net seat, rim, court and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Brace bite: deepest vertex of each of the 2 braces inside the collar / inside the lower rail (signed distance to the host shell) | ≥ 0.006 m each, exactly 2 braces | 0.00950 / 0.02098 |
| Net seat: for each of the 12 hooks, distance from the eye centre to the nearest net loop's cord circle (both fitted from the mesh by PCA) | ≤ 0.009 m (the eye's clear radius), 12 hooks, 12 loops | worst 0.00700 (24 strands, 72 knots) |
| Rim top over the court (ring shell `max z` minus the top of the slab under it) | 3.05 m ± 0.010 | 3.0500 |
| Rim inside diameter (min in-plane radius × 2) | 0.457 m ± 0.004 | 0.4570 |
| Rim inner edge to board face | 0.151 m ± 0.005 | 0.1510 |
| Rim tilt (fitted ring axis vs vertical) | ≤ 0.5° | 0.000° |
| Ball seat: each of the 2 balls' fitted radius, and its lowest vertex below the top of the slab under its centre | radius 0.1194 m ± 0.002; sink 0.0005–0.004 m | 0.1194 / 0.00200, 0.1194 / 0.00200 |
| Anchor bolts: each of the 4 bolts' foot below the top of the slab it stands in, and its head above the plate | ≥ 0.050 m embedded, ≥ 0.030 m proud | worst 0.0700 / 0.0620 |
| Court paint: each of the 18 paint shells against the slab under its centre — top above the slab, bottom below it | top 0.0005–0.003 m, sink 0.001–0.004 m | top 0.00100–0.00220, sink 0.00140–0.00300 |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (209 shells) |

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--short-brace` | brace bite (braces stop 60 mm short of the rail: −0.02150 m) | 17 |
| `--drop-net` | net seat (net lowered 25 mm: worst eye-to-loop 0.03200 m) | 18 |
| `--tilt-rim` | rim level (rim assembly tilted 3° about the flange: 3.000°) | 19 |
| `--float-ball` | ball seat (both balls lifted 20 mm: sink −0.01800 m, 3 components) | 21 |
| `--short-bolts` | anchor bolts through the plate into the slab (feet stop in the plate: embed −0.0125 m) | 22 |
| `--float-paint` | court paint set into the slab (paint lifted 6 mm: sink −0.00460 to −0.00300 m, top 0.00700–0.00820 m) | 23 |
| `--loose-pad` | one connected assembly (pad bore 6 mm clear of the pole: 2 components) | 20 |

`--drop-net` and `--tilt-rim` move whole sub-assemblies. The net drops
without its hooks, and the rim tilts with its hooks and net about the
flange, so only the budget each one targets can see the change.
`--drop-net`, `--float-ball` and `--float-paint` also split the assembly,
so the net-seat, ball-seat and paint checks all run before the component
check (20). `--short-bolts` keeps each bolt in the plate, so it stays
connected and only the embedment fails. `--loose-pad` needs a part held by
one joint only: the pad (with its flap) touches nothing but the pole.

## Run

```bash
blender --background --python basketball_hoop.py --
blender --background --python basketball_hoop.py -- --skip-decimate
blender --background --python basketball_hoop.py -- --stray-vert
blender --background --python basketball_hoop.py -- --lift-z
blender --background --python basketball_hoop.py -- --short-brace
blender --background --python basketball_hoop.py -- --drop-net
blender --background --python basketball_hoop.py -- --tilt-rim
blender --background --python basketball_hoop.py -- --float-ball
blender --background --python basketball_hoop.py -- --short-bolts
blender --background --python basketball_hoop.py -- --float-paint
blender --background --python basketball_hoop.py -- --loose-pad
blender --background --python basketball_hoop.py -- --output hoop.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (−172°) and shoots it with a
70 mm lens from 20 m, a little above the board, so the court runs toward
the camera and the key, circle and arc read at thumbnail size while the
board and net read face-on. The long lens keeps the near corner of the pad
from swelling. The key light's spread keeps it on the hoop and court
instead of the near floor, and a warm wedge washes the back wall on the
right.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20`–`23` are file-local. `24` is the
asset-quality floor on the render path: `check_asset_quality` returns 11,
which this piece already spends on the collider ceiling, so the call site
remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
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
| 16 | Not grounded: bounding box `zmin` off 0 |
| 17 | Brace bite: a brace end not inside the collar or the lower rail, or not exactly two braces (`--short-brace`) |
| 18 | Net seat: a hook with no net loop threaded through its eye, or not 12 hooks and 12 loops (`--drop-net`) |
| 19 | Rim off regulation: height over the court, inside diameter, board gap or level (`--tilt-rim`) |
| 20 | Assembly splits into more than one connected component (`--loose-pad`) |
| 21 | Ball seat: not 2 balls, a radius off size 7, or a ball not bearing 0.5–4 mm into its slab (`--float-ball`) |
| 22 | Anchor bolts: not 4, a foot less than 50 mm into the slab, or a head less than 30 mm over the plate (`--short-bolts`) |
| 23 | Court paint: not 18 shells, or a shell's top or sink outside its band against its slab (`--float-paint`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
