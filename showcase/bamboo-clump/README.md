# Bamboo clump

A showcase piece, not an example, and a `nature` piece. It builds a
procedural, game-ready clump of clumping bamboo on a low mound of leaf-litter
soil:

- a soil disc 2.2 × 2.0 m: a gentle litter heap of 60 mm, a lobed rhizome
  hummock heaving 120 mm more under the clump (gaussian radius 0.36 m), and a
  collar of soil heaped round every culm's foot, rolled down to the floor at
  its rim;
- five rhizome knuckles breaking the soil: short, fat, jointed sausages, 1.15
  times their culm's foot radius, each running in to an outer culm's foot,
  their axis sunk 0.32 of their radius under the soil the whole way so they
  are bedded along their length;
- seven culms rising from a rhizome mass about 0.6 m across, 2.71 to 4.55 m
  tall above the soil and 4.6 to 7.4 cm across at the first node. Each outer
  culm leaves the soil already leaning 7° out from the clump's centre, then
  leans further and arches, swaying a little about its bearing. A culm is
  buried 45 mm in the soil, flares at the foot, tapers to 0.57–0.60 of its
  foot radius at the last node, and above it thins fast into a fine whip.
  Culm sections are ten-sided. Tone runs from a fresh, deep-green culm
  heavily powdered with white wax just under every node to an old one gone
  yellow;
- 99 nodes, 11 to 18 a culm. A node is a raised ring (a six-point profile
  revolved about the culm: crest 3.5 mm proud of the wall, inner wall 3 mm
  inside it), a collar darker than its culm with a pale sheath scar on its
  crest. Internodes are close at the foot, long through the middle and close
  again toward the tip: mean pitch 0.249–0.257 m a culm, the middle third
  0.079 to 0.106 m longer than the first;
- 21 papery culm sheaths still clasping the lowest three nodes of each culm:
  a sleeve wrapped from just above the node's ridge, its inner wall bitten
  1.5 mm into the culm, thinning from 2.6 mm proud at its foot to a ragged,
  diagonal top whose lip curls off the culm;
- 107 leafy branches. Every node from 30% of the way up carries a first
  branch, turning round the culm by the golden angle; above 42% a second,
  shorter and flatter one often joins it, and above 62% nearly always. Each
  is a six-sided slender stem that springs up at 44–78° and arches over by
  its own sag, so some ride high and some hang. The top node's branch rises
  nearly upright and plumes the whip. Leaves number 6–12 on a first branch
  and 4–7 on a second, more toward the crown, and each branch's leaves share
  a length and a droop, so tufts differ from each other more than leaves in
  a tuft do: 815 slim, pointed blades in all, diamond-section with a pale
  midrib and strawy tip;
- three young shoots in overlapping sheaths pushing out of the soil beside
  the clump (0.27–0.62 m), their husks stepping out at each sheath edge and
  greening at the tip;
- 36 dry leaves and five fallen culm sheaths lying in the litter, off the
  hummock. Each is a thick lens with its belly 1–2.5 mm under the soil and
  its flanks leaning 11–15° (sheaths 10–14°), steeper than the soil's slope
  where litter is laid (outside 0.44 of the disc's radius), so no flank can
  lie in the soil's own plane.

**Proportion, stated.** Real clumping bamboo is slenderer than this: a
*Bambusa textilis* or *B. tuldoides* culm stands 100–200 diameters tall.
These stand about 60–75. The culms are thickened on purpose so each still
reads as a cane rather than a wire at gallery size; the node pitch, the
taper and the clump's 0.6 m footprint are kept to life.

Every seeded draw comes from `random.Random(SEED)` in `plan_clump()`, before
anything is built, and only places the litter. Everything on the culms comes
from a closed-form hash of the node's indices, so no flag can shift it.

Five materials, one per substance: soil, bamboo culm (culm, node rings,
branches and rhizome knuckles, told apart by a face zone), leaf, culm sheath
(the shoots, the sheaths still on the culms and the fallen ones) and dry
leaf. Point attributes `Along` (the run along a culm, branch, leaf or
shoot), `Nd` (the *signed* distance to the nearest node: the wax band lies
only below a node, the scar line either side) and `Side` (across a leaf for
its midrib, and up a node ring to mark its crest),
a `Skirt` attribute for the soil's cut edge, and a seeded `Tone` face
attribute carry the variation. Everything is smooth-shaded; every material
boundary and every fold sharper than 62° is a hard edge, so a leaf's edge
and a node ring's shoulders stay crisp while a ten-sided culm stays round.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a clump 3.82 × 3.55 m across its leaves and 4.83 m to the
highest leaf. The outer AABB is 3.8168 × 3.5512 × 4.8254 m, read off the
vertices: the leaning culms and their branches set X and Y, a leaf on the
tallest culm's top plume sets the top; the soil's underside is the ground.
The collider is the convex hull of the lower 1.25 m of the clump, coarse: a
player walks the litter and brushes through the leaves, but not through the
culms.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 72800–74800 | 73804 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 5 distinct; ≥2680 soil, ≥16600 culm, ≥16770 leaf, ≥2920 sheath, ≥740 dry-leaf faces | 5 slots; 2734 / 16944 / 17115 / 2979 / 756 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (3.8168, 3.5512, 4.8254) m ± 0.01 | (3.8168, 3.5512, 4.8254), zmin 0 |
| Collider tris (lower 1.25 m hull) | ≤ 96 | 88 |
| Export | written, size > 0, removed after measuring | 5606968 bytes |

The quality pass re-fitted four of these around the new measurements, each
for a stated reason. The triangle band moved from 51500–53500 to 72800–74800,
paying for a fuller crown (815 leaves on 107 branches against 567 on 63), 21
culm sheaths, five knuckles and a wax-band row under every node. The face
floors follow the same counts. The collider ceiling went from 80 to 96: the
culms now rise from a 0.6 m footprint and splay from the soil, so the hull of
the lower 1.25 m has more facets (88). The AABB is a new shape.

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

The first builds had cross-shell pairs: litter flanks lying in the soil's
plane (five, then two), and later one pair of tip leaves sharing a base
point. The litter's flanks now lean steeper than the mound can tilt and the
two tip leaves start 4% of the branch apart, rather than widening any band.

### Culms, nodes, branches, the clump and the litter

These are the organic invariants. The 1099 shells are told apart by a `Part`
face attribute that names a shell and never measures it; every number below
is read off the generated vertices.

| Axis | Declared | Measured |
| --- | --- | --- |
| Shells | 1 soil, 7 culms, 3 shoots, 36 litter leaves, 5 fallen sheaths, 5 knuckles, and as many node rings, branches, leaves and culm sheaths as were built | 1 / 7 / 3 / 36 / 5 / 5 / 99 / 107 / 815 / 21 |
| Grounded, per support: each culm's, shoot's and knuckle's lowest vertex under the soil straight above it | 0.020–0.075 m (each of 15 supports) | 0.0256–0.0479 m |
| Nodes seated: for each ring, a ray from its centre (on the culm's axis) to each ring vertex meets the host culm's own surface at that angle. The crest is outside it, the inner wall inside it | crest 0.0025–0.0048 m, inner wall 0.0020–0.0060 m, all 99 rings | 0.0035–0.0036 m; 0.0031–0.0034 m |
| Branches sprung from nodes: the first ring's centre inside its host culm (ray parity, three directions, distance to the nearest face), and its distance from the nearest node ring centre less the culm radius there | depth 0.004–0.010 m; ≤ 0.010 m off its node; all 107 | 0.0055–0.0067 m; −0.0063 to −0.0053 m |
| Leaves seated: each leaf's first ring centre inside its branch | 0.0010–0.0052 m; all 815 | 0.0020–0.0040 m |
| Size: each culm's height from the soil under its lowest vertex to its highest; its diameter at the lowest node (twice the distance from the ring's centre to the culm's surface) | height 2.6–4.7 m with a spread of at least 1.0 m; diameter 0.042–0.080 m | 2.7117–4.5463 m; 0.0458–0.0738 m |
| Taper: the radius at each node going up each culm never rises; the last node over the first | rise ≤ 0.0004 m; ratio 0.54–0.66 | −0.00044 m (it falls at every node); 0.5728–0.6036 |
| Pitch: the distance between consecutive ring centres up each culm, its mean per culm, and the middle third's mean minus the first third's | at least 10 nodes a culm; gap 0.12–0.38 m; mean 0.23–0.28 m; middle longer by ≥ 0.06 m | 11–18; 0.1516–0.3305 m; 0.2487–0.2566 m; 0.0794–0.1064 m |
| Clump: BVH overlap between every pair of culms, and the closest vertex-to-surface approach | 0 intersecting pairs; ≥ 0.020 m | 0; 0.0831 m |
| Litter resting: each blade's deepest vertex under the soil straight above it | 41 blades, each 0.0005–0.006 m | 0.0011–0.0027 m |
| Culm sheaths seated: per sheath, against the culm its centroid lies in, the deepest vertex inside the culm, the proudest outside it, and the share of its vertices inside (the inner wall is half of them) | inside 0.0008–0.0030 m, proud 0.0020–0.0065 m, share ≥ 0.45; all 21 | 0.0014–0.0016 m; 0.0036–0.0037 m; 0.50 |

Three measurements needed care. A ring's host is the culm its centre lies
inside, by ray parity, not the nearest surface: with two culms overlapping,
a centre can be nearer its neighbour's skin than its own. A litter blade's
*lowest* vertex is often a flank on a slope, so the litter is measured by its
*deepest* vertex. And a node ring is revolved about the axis, so its centroid
is the axis point, which makes the radius, the pitch and the host all one
measurement.

The taper budget is what keeps the culm honest: it is a cone that only
narrows, nothing swells at a node, and the rings follow the wall rather than
carry the shape. The whip above the last node is outside its reach by
design: no ring stands there, so the fast final thinning cannot flatter the
ratio measured between the first and last rings.

A culm sheath's columns stand on the culm's own ten vertex bearings. Set
half a step round, its inner wall would cut the culm's flat facets at their
middles, where the facet lies 4.9% of the radius inside the vertex circle,
and a 1.5 mm bite would read as a gap on every culm thicker than 3 cm.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code, and the `budget_fails` line it prints names only
its own budget. Blender 4.5 and 5.1 were not available locally.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-culm` | each support bedded in the soil (culm 5 raised 70 mm: its foot 0.0410 m above the soil), while the soil still grounds the AABB | 16 |
| `--sunk-nodes` | nodes seated (every ring's crest 0.6 mm outside the wall: 0.0016–0.0018 m) | 17 |
| `--stray-branches` | branches sprung from nodes (culm 0's lowest branch 90 mm up its culm, still inside it: 0.0613 m off the nearest node) | 18 |
| `--swell-culm` | taper (culm 2 swells 35% about 45% up, its rings following: radius rises 0.00623 m between nodes) | 19 |
| `--bunch-nodes` | pitch (culm 0's seventh node slid to 70 mm under the next: gaps 0.0700–0.4805 m) | 20 |
| `--crowd-culms` | clump (culm 3's foot stood against culm 6's and re-bedded there: 18 intersecting triangle pairs, closest approach 0.0004 m) | 21 |
| `--float-litter` | litter resting (every blade lifted 25 mm: deepest vertex 0.0223–0.0239 m above the soil) | 22 |
| `--lift-leaves` | leaves seated (every leaf's base lifted 8 mm out of its branch: −0.0059 to 0.0016 m) | 23 |
| `--loose-sheaths` | culm sheaths seated (every sheath's inner wall 3 mm outside its culm: −0.0030 to −0.0028 m, no vertex inside) | 25 |

Each falsifier moves only what its budget measures. `--stray-branches`
moves one branch, `--crowd-culms` one culm and `--float-culm` one culm
straight up, so the envelope does not move: each stays inside `BBOX_TOL`.
`--swell-culm` scales the radius and the rings that follow it, `--bunch-nodes`
moves one ring and the branch on it, `--sunk-nodes` moves only the crest of
every ring, and `--loose-sheaths` moves only the sheaths. The first
`--stray-branches` shifted every branch and grew the box 0.09 m, exit 8; the
first `--crowd-culms` moved culm 4, which set the box's Y, exit 8 again.

In the quality pass `--crowd-culms` was re-aimed twice. Moving culm 0 (the
tallest, which sets the top) toward culm 4 and holding its foot's height so
the top stayed put left the foot 14 mm above the soil, because the rhizome
hummock falls away from the centre: exit 16, not 21. Re-bedding it instead
would have dropped the top. Every culm-and-neighbour pair was then tried
against the envelope, and culm 3 stood against culm 6 is one of the few
that moves no extreme: the envelope changes by 0.0000 m and only the clump
budget fails.

## Run

```bash
blender --background --python bamboo_clump.py --
blender --background --python bamboo_clump.py -- --skip-decimate
blender --background --python bamboo_clump.py -- --stray-vert
blender --background --python bamboo_clump.py -- --lift-z
blender --background --python bamboo_clump.py -- --float-culm
blender --background --python bamboo_clump.py -- --sunk-nodes
blender --background --python bamboo_clump.py -- --stray-branches
blender --background --python bamboo_clump.py -- --swell-culm
blender --background --python bamboo_clump.py -- --bunch-nodes
blender --background --python bamboo_clump.py -- --crowd-culms
blender --background --python bamboo_clump.py -- --float-litter
blender --background --python bamboo_clump.py -- --lift-leaves
blender --background --python bamboo_clump.py -- --loose-sheaths
blender --background --python bamboo_clump.py -- --output bamboo.png
```

Smoke passes no flags.

The hero keeps the piece unturned (`HERO_YAW_DEG` 0°) and looks in from
the south-south-west, 1.8 m above the clump's mid-height, so the clump fans
across the frame, the lit leaves stand out of the dark wall and the eye falls
a little onto the hummock. The fill is 0.303 × 0.833.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene, grounding, joint, seat and plumb family. `20`–`23` and `25`
are file-local. `24` is the asset-quality floor on the render path:
`check_asset_quality` returns 11, which this piece already spends on the
collider ceiling, so the call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or a shell count off the plan |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 5 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0 (`--lift-z`), or a culm, shoot or rhizome knuckle not bedded 0.020–0.075 m in the soil (`--float-culm`) |
| 17 | Nodes: a ring's crest outside 0.0025–0.0048 m or its inner wall outside 0.0020–0.0060 m (`--sunk-nodes`) |
| 18 | Branches: a first ring outside 0.004–0.010 m inside its culm, or more than 0.010 m off a node (`--stray-branches`) |
| 19 | Size and taper: a culm's height or diameter (0.042–0.080 m) off its band, heights less than 1.0 m apart, a radius that rises up a culm, or a taper ratio off 0.54–0.66 (`--swell-culm`) |
| 20 | Pitch: fewer than 10 nodes on a culm, a gap outside 0.12–0.38 m, a mean outside 0.23–0.28 m, or a middle third less than 0.06 m longer than the first (`--bunch-nodes`) |
| 21 | Clump: two culms intersect, or come closer than 0.020 m (`--crowd-culms`) |
| 22 | Litter: a blade's deepest vertex outside 0.0005–0.006 m under the soil (`--float-litter`) |
| 23 | Leaves: a leaf's base not 0.0010–0.0052 m inside its branch (`--lift-leaves`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
| 25 | Culm sheaths: a sheath's inner wall not 0.0008–0.0030 m inside its culm, its outer wall not 0.0020–0.0065 m proud, or fewer than 45% of its vertices inside (`--loose-sheaths`) |
