# Palm tree

A showcase piece, not an example, and the sixth in the `nature` category.
It builds a procedural, game-ready coconut palm on a raised disc of beach
sand:

- a sand disc 3.1 × 2.8 m, heaped a little round the palm's foot and rolled
  down to the floor at its rim. The sand carries wind ripples, shell grit
  and dark mineral grains, and its cut edge shows damp darker sand under the
  dry crust;
- a trunk 4.47 m from the sand to its top, 4.60 m along its curved axis. It
  rises out of a swollen, seven-lobed bole, leans away along a curve that is
  steepest just above the bole and comes back upright under the crown, so
  the crown stands 0.81 m off the foot in plan. The bole is 0.54 m across at
  the sand; the trunk is 0.29 m across a metre up and tapers to 0.26 m
  under the crown, a little out of round, swelling once just below it. Twenty-five leaf-scar rings circle it at an even
  0.145 m pitch, each a low rim a few millimetres proud of the bark and a
  little out of square with the axis. Twenty-four roots leave the bole at
  different heights, drop onto the sand and run out along it half buried,
  snaking a little, before diving under it; they reach furthest on the side
  the palm leans toward;
- a crown: a fibrous boss of leaf bases on the trunk's top carrying eighteen
  pinnate fronds in a golden-angle spiral, youngest high on the boss and
  rising, oldest low and hanging. Each frond is a rachis 2.5–3.4 m long,
  thick at its clasping base and tapering to a point, that arches out and
  droops toward its tip, with 36 pairs of leaflets from a fifth of the way
  out: folded V-section blades that leave the rachis angled toward its tip,
  hang below it in a V and bend further down along their length, longest at
  mid-frond, twisted a little each, with yellowed tips. Two dead brown fronds
  with leaflets missing hang against the trunk on the camera's side, and two
  unopened spear leaves stand upright at the centre;
- twelve coconuts in four bunches on the boss under the frond bases, placed
  in the widest gaps between the old fronds, green and ripening, each an egg
  with three blunt ridges drawn to a point, its stem end seated in the boss;
- two fallen coconuts resting in the sand (one fresh and ripening, one old
  and dry), a fallen dead frond lying with its leaflets splayed flat on the
  sand, a bleached driftwood branch with a snapped stub, four scallop shells
  and two augers, and five tufts of sea grass.

Every seeded draw comes from `random.Random(SEED)` in `plan_beach()`, before
anything is built. Per-leaflet variety (droop, forward angle, length, bend,
twist, tone, which dead leaflets are missing) comes from a closed-form hash
of the leaflet's indices, so no flag can shift it.

Eight materials, one per substance: sand, palm bark (trunk, rings, roots and
the boss of leaf bases, told apart by a face zone), live frond (leaflets,
rachis and spears), dead frond (the hanging and fallen fronds), coconut husk
(green, ripening and dry), seashell, driftwood and sea grass. A point
attribute `Along` carries the run along the trunk, a rachis, a leaflet, a
root or a nut, and `Skirt` marks the disc's cut edge; a `Tone` face attribute
is seeded per part. Everything is smooth-shaded; every material boundary and
every fold sharper than 62° is a hard edge, so a leaflet's edges and a
shell's rim stay crisp while a six-sided rachis stays round, and 30° on the
coconuts, so the husk's three ridges read as facets.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a disc 3.1 × 2.8 m, the palm 6.03 m to the tip of its
highest frond. The outer AABB is 5.2645 × 5.1503 × 6.0258 m, read off the
vertices: the fronds set X, Y and the top; the sand's underside is the
ground. The collider is the convex hull of the lower 2.4 m of the trunk,
coarse: players walk the sand and brush through the fronds, but not through
the bole.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 44600–45800 | 45196 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 8 distinct; ≥3400 sand, ≥4370 bark, ≥13640 frond, ≥1140 dead frond, ≥1230 husk, ≥780 shell, ≥134 driftwood, ≥1030 grass faces | 8 slots; 3694 / 4752 / 14828 / 1243 / 1344 / 846 / 146 / 1118 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (5.2645, 5.1503, 6.0258) m ± 0.01 | (5.2645, 5.1503, 6.0258), zmin 0 |
| Collider tris (lower trunk hull) | ≤ 60 | 44 |
| Export | written, size > 0, removed after measuring | 3518264 / 3518264 / 3518252 bytes (4.5.11 / 5.1.2 / 5.2.1) |

No falsifier changes the triangle count: every falsifier run measured
45196 tris. None moves the envelope by more than 0.1 mm.

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

The fallen frond's leaflets lie flat on the sand and overlap their
neighbours, and on the first build two of them shared a plane. They are
staggered in height by a millimetre in a four-step cycle, and spaced so a
leaflet clears the next one on its side of the rachis, rather than widening
any band.

### Fronds, coconuts, the trunk, the rings, the bedding and the cover

These are the organic invariants. A palm has no joinery, but it is jointed
all the same: every frond grows out of the crown and every coconut hangs
from it. The trunk leans, but the crown's mass has to stand over what holds
it; the leaf scars come at the pitch the palm grew at; and the palm and
what the sea left stand in the sand, not on it.

| Axis | Declared | Measured |
| --- | --- | --- |
| Fronds seated: every rachis, dead frond and spear, its deepest vertex inside the boss of leaf bases (ray parity by majority of three directions, distance to the nearest face) | 22 fronds, each 0.060–0.160 m | 22; 0.0871–0.1217 m |
| Coconuts attached: every nut on the crown, its deepest vertex inside the boss, and its centre below the boss's centre | 12 nuts, each 0.012–0.045 m, each below | 12; 0.0229–0.0297 m; 0.117–0.183 m below |
| Trunk: its height from the sand at its foot to its top; the crown's offset, a top slab's centroid off a slab's 0.55–0.75 m over the sand; the tip-over margin: the volume centroid of every closed shell of trunk and crown (uniform density) inside the root plate, the hull in plan of where each root enters the sand, by at least a margin | height 4.47 ± 0.05 m; offset 0.60–1.00 m; 24 roots; margin ≥ 0.080 m | 4.4735 m; 0.8056 m; mass centre 0.5555 m off the foot, 0.2081 m inside a plate reaching 0.3846–0.8047 m |
| Rings: the 25 leaf-scar ring shells, the distance between consecutive ring centroids up the trunk | 25 rings; mean pitch 0.135–0.155 m; spread ≤ 0.006 m | 25; 0.14498 m; 0.00136 m |
| Bedding: the trunk's most-buried vertex in each of eight sectors round its foot, under the sand straight above it, the shallowest sector; every root's deepest point under the sand | trunk 0.030–0.200 m; roots 0.020–0.100 m | 0.0990 m; 0.0644–0.0716 m |
| Resting: each fallen coconut's lowest vertex under the sand straight above it | 2 nuts, each 0.010–0.050 m | 0.0198–0.0207 m |
| Cover joined: every shell unioned with the sand through BVH overlaps | every shell joined | 1566 shells; 0 loose |

Two measurements needed care. A nut hung from the boss leans out and down,
and the boss curves away under it, so seating the stem end a fixed depth
along the nut's axis buried the nut's shoulder 0.107 m deep. Each nut is
slid out along its own axis until its deepest point is the design bite. And
one parity ray grazing an edge of the boss counted it twice, which put a
vertex 0.108 m outside the boss "inside" it; every inside test is now a
majority of three rays in different directions.

The tip-over budget is what makes the lean honest. The crown stands 0.81 m
off the foot, and the trunk's own volume leans with it, so the mass centre
sits 0.56 m off the foot, well outside the bole. The palm stands because
its roots reach furthest on the side it leans toward.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code, and the `budget_fails` line it prints names only
its own budget.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--short-petioles` | fronds seated (every rachis and spear starts 80 mm nearer the boss's skin, still inside it: 0.0175–0.0422 m) | 17 |
| `--drop-coconut` | coconuts attached (one nut slid out along its axis until 6 mm of it is in the boss, still touching: 0.0037 m) | 18 |
| `--short-roots` | tip-over margin (every root dives in 0.26 m from the axis: the plate reaches 0.2059–0.3502 m and the mass centre is 0.3507 m outside it) | 19 |
| `--bunch-rings` | rings at an even pitch (three rings slid 45 mm down the trunk, still on the bark: spread 0.08992 m) | 20 |
| `--perch-trunk` | bedding (the trunk's foot 12 mm under the sand, the roots unchanged: shallowest sector 0.0123 m) | 21 |
| `--float-nuts` | resting (the fallen coconuts raised 16 mm, still touching the sand: 0.0038–0.0047 m) | 22 |
| `--float-cover` | cover joined (shells, driftwood, sea grass and the fallen frond lifted 50 mm: 120 of 1566 shells loose) | 23 |

Each falsifier moves only what its budget measures, and none is sized
past the point where a second budget would see it. `--short-petioles` trims
each rachis at its base and leaves the rest of the frond where it was, so
the envelope and the leaflets do not move. `--drop-coconut` leaves the nut
touching the boss and `--float-nuts` leaves the nuts touching the sand, so
the cover stays joined. `--short-roots` keeps every root seated in the bole
and bedded at its tip. `--perch-trunk` raises only the bottom of the bole:
the axis above the sand, the rings, the roots and the crown do not move.

## Run

```bash
blender --background --python palm_tree.py --
blender --background --python palm_tree.py -- --skip-decimate
blender --background --python palm_tree.py -- --stray-vert
blender --background --python palm_tree.py -- --lift-z
blender --background --python palm_tree.py -- --short-petioles
blender --background --python palm_tree.py -- --drop-coconut
blender --background --python palm_tree.py -- --short-roots
blender --background --python palm_tree.py -- --bunch-rings
blender --background --python palm_tree.py -- --perch-trunk
blender --background --python palm_tree.py -- --float-nuts
blender --background --python palm_tree.py -- --float-cover
blender --background --python palm_tree.py -- --output palm.png
```

Smoke passes no flags.

The hero keeps the piece unturned (`HERO_YAW_DEG` 0°) and looks in from
the south-south-west, a little above the disc, so the trunk leans to the
right across the frame and the crown's fronds spread both ways. The fill is
0.394 × 0.867.

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
| 3 | Mesh did not build, no UV layer, or no sand, trunk or boss shell |
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
| 17 | Fronds: not 22 rachises and spears, or one's deepest vertex inside the boss outside 0.060–0.160 m (`--short-petioles`) |
| 18 | Coconuts: not 12 on the crown, a nut's deepest vertex inside the boss outside 0.012–0.045 m, or a nut not below the boss's centre (`--drop-coconut`) |
| 19 | Trunk: height off 4.47 ± 0.05 m, crown offset outside 0.60–1.00 m, not 24 roots, or the mass centre less than 0.080 m inside the root plate (`--short-roots`) |
| 20 | Rings: not 25, mean pitch outside 0.135–0.155 m, or a spread above 0.006 m (`--bunch-rings`) |
| 21 | Bedding: the trunk's shallowest sector outside 0.030–0.200 m under the sand, or a root tip outside 0.020–0.100 m (`--perch-trunk`) |
| 22 | Resting: a fallen coconut's lowest point outside 0.010–0.050 m under the sand (`--float-nuts`) |
| 23 | Cover: a shell not joined to the sand (`--float-cover`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
