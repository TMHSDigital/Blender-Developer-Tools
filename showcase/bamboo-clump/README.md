# Bamboo clump

A showcase piece, not an example, and a `nature` piece. It builds a
procedural, game-ready clump of clumping bamboo on a low mound of leaf-litter
soil:

- a soil disc 2.2 × 2.0 m, heaped to 85 mm at its centre, with a collar of
  soil heaped round every culm's foot, rolled down to the floor at its rim;
- seven culms, 2.75 to 4.53 m tall above the soil and 3.3 to 5.8 cm across
  at the first node. Each is buried 45 mm in the soil, flares at the foot,
  rises straight, then leans away from the clump and arches, swaying a
  little about its bearing, and tapers to 0.57–0.60 of its foot radius at
  the last node before a closed, pointed tip. Culm sections are ten-sided;
- 99 nodes, 11 to 18 a culm. A node is a raised ring (a six-point profile
  revolved about the culm: crest 3.5 mm proud of the wall, inner wall 3 mm
  inside it) with a pale wax bloom and a dark scar line painted either side.
  Internodes are close at the foot, long through the middle and close again
  toward the tip: mean pitch 0.249–0.257 m a culm, the middle third 0.079 to
  0.106 m longer than the first;
- 63 leafy branches, one to a node from 30% of the way up and turning round
  the culm by the golden angle, each a six-sided slender stem that springs
  up at 46–66° from the culm and arches over and droops, 0.42–0.82 m long.
  Each carries nine slim, pointed, drooping leaves (567 in all) along its
  last 60%, a diamond-section blade with a pale midrib and strawy tip;
- three young shoots in overlapping sheaths pushing out of the soil beside
  the culms (0.27–0.62 m), their husks stepping out at each sheath edge and
  greening at the tip;
- 36 dry leaves and five fallen culm sheaths lying in the litter. Each is a
  thick lens with its belly 1–2.5 mm under the soil and its flanks leaning
  11–15° (sheaths 10–14°), steeper than the mound's slope (about 9° at most,
  away from the culm collars), so no flank can lie in the soil's own plane.

Every seeded draw comes from `random.Random(SEED)` in `plan_clump()`, before
anything is built, and only places the litter. Everything on the culms comes
from a closed-form hash of the node's indices, so no flag can shift it.

Five materials, one per substance: soil, bamboo culm (culm, node rings and
branches, told apart by a face zone), leaf, culm sheath (the shoots and the
fallen sheaths) and dry leaf. Point attributes `Along` (the run along a
culm, branch, leaf or shoot), `Nd` (the distance to the nearest node, which
paints the bloom and the scar) and `Side` (across a leaf, for the midrib),
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

Intended size: a clump 3.43 × 3.57 m across its leaves and 4.64 m to the
highest leaf. The outer AABB is 3.4296 × 3.5679 × 4.6432 m, read off the
vertices: the leaning culms and their branches set X and Y, a leaf on a
tall culm's last branch sets the top; the soil's underside is the ground. The
collider is the convex hull of the lower 1.25 m of the clump, coarse: a
player walks the litter and brushes through the leaves, but not through the
culms.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 51500–53500 | 52490 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 5 distinct; ≥2680 soil, ≥13040 culm, ≥11670 leaf, ≥450 sheath, ≥740 dry-leaf faces | 5 slots; 2734 / 13308 / 11907 / 459 / 756 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (3.4296, 3.5679, 4.6432) m ± 0.01 | (3.4296, 3.5679, 4.6432), zmin 0 |
| Collider tris (lower 1.25 m hull) | ≤ 80 | 78 |
| Export | written, size > 0, removed after measuring | 3872292 bytes |

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

These are the organic invariants. The 781 shells are told apart by a `Part`
face attribute that names a shell and never measures it; every number below
is read off the generated vertices.

| Axis | Declared | Measured |
| --- | --- | --- |
| Shells | 1 soil, 7 culms, 3 shoots, 36 litter leaves, 5 sheaths, and as many node rings, branches and leaves as were built | 1 / 7 / 3 / 36 / 5 / 99 / 63 / 567 |
| Grounded, per support: each culm's and shoot's lowest vertex under the soil straight above it | 0.020–0.075 m (each of 10 supports) | 0.0255–0.0421 m |
| Nodes seated: for each ring, a ray from its centre (on the culm's axis) to each ring vertex meets the host culm's own surface at that angle. The crest is outside it, the inner wall inside it | crest 0.0025–0.0048 m, inner wall 0.0020–0.0060 m, all 99 rings | 0.0035–0.0036 m; 0.0031–0.0039 m |
| Branches sprung from nodes: the first ring's centre inside its host culm (ray parity, three directions, distance to the nearest face), and its distance from the nearest node ring centre less the culm radius there | depth 0.004–0.010 m; ≤ 0.010 m off its node; all 63 | 0.0058–0.0067 m; −0.0065 to −0.0057 m |
| Leaves seated: each leaf's first ring centre inside its branch | 0.0010–0.0052 m; all 567 | 0.0020–0.0039 m |
| Size: each culm's height from the soil under its lowest vertex to its highest; its diameter at the lowest node (twice the distance from the ring's centre to the culm's surface) | height 2.6–4.7 m with a spread of at least 1.0 m; diameter 0.030–0.062 m | 2.7546–4.5338 m; 0.0334–0.0575 m |
| Taper: the radius at each node going up each culm never rises; the last node over the first | rise ≤ 0.0004 m; ratio 0.54–0.66 | −0.00033 m (it falls at every node); 0.5727–0.6036 |
| Pitch: the distance between consecutive ring centres up each culm, its mean per culm, and the middle third's mean minus the first third's | at least 10 nodes a culm; gap 0.12–0.38 m; mean 0.23–0.28 m; middle longer by ≥ 0.06 m | 11–18; 0.1516–0.3304 m; 0.2487–0.2566 m; 0.0794–0.1064 m |
| Clump: BVH overlap between every pair of culms, and the closest vertex-to-surface approach | 0 intersecting pairs; ≥ 0.020 m | 0; 0.0574 m |
| Litter resting: each blade's deepest vertex under the soil straight above it | 41 blades, each 0.0005–0.006 m | 0.0011–0.0026 m |

Three measurements needed care. A ring's host is the culm its centre lies
inside, by ray parity, not the nearest surface: with two culms overlapping,
a centre can be nearer its neighbour's skin than its own. A litter blade's
*lowest* vertex is often a flank on a slope, so the litter is measured by its
*deepest* vertex. And a node ring is revolved about the axis, so its centroid
is the axis point, which makes the radius, the pitch and the host all one
measurement.

The taper budget is what keeps the culm honest: it is a cone that only
narrows, nothing swells at a node, and the rings follow the wall rather than
carry the shape.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code, and the `budget_fails` line it prints names only
its own budget. Blender 4.5 and 5.1 were not available locally.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-culm` | each support bedded in the soil (culm 5 raised 70 mm: its foot 0.0311 m above the soil), while the soil still grounds the AABB | 16 |
| `--sunk-nodes` | nodes seated (every ring's crest 0.6 mm outside the wall: 0.0016–0.0018 m) | 17 |
| `--stray-branches` | branches sprung from nodes (culm 0's lowest branch 90 mm up its culm, still inside it: 0.0666 m off the nearest node) | 18 |
| `--swell-culm` | taper (culm 2 swells 35% about 45% up, its rings following: radius rises 0.00486 m between nodes) | 19 |
| `--bunch-nodes` | pitch (culm 0's seventh node slid to 70 mm under the next: gaps 0.0700–0.4805 m) | 20 |
| `--crowd-culms` | clump (culm 0 stood 70 × 60 mm nearer culm 1: 22 intersecting triangle pairs, closest approach 0.0001 m) | 21 |
| `--float-litter` | litter resting (every blade lifted 25 mm: deepest vertex 0.0239–0.0224 m above the soil) | 22 |
| `--lift-leaves` | leaves seated (every leaf's base lifted 8 mm out of its branch: −0.0054 to −0.0014 m) | 23 |

Each falsifier moves only what its budget measures. `--stray-branches`
moves one branch, `--crowd-culms` one culm and `--float-culm` one culm
straight up, so the envelope does not move: each stays inside `BBOX_TOL`.
`--swell-culm` scales the radius and the rings that follow it, `--bunch-nodes`
moves one ring and the branch on it, and `--sunk-nodes` moves only the
crest of every ring. The first `--stray-branches` shifted every branch and
grew the box 0.09 m, exit 8; the first `--crowd-culms` moved culm 4, which
set the box's Y, exit 8 again.

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
blender --background --python bamboo_clump.py -- --output bamboo.png
```

Smoke passes no flags.

The hero keeps the piece unturned (`HERO_YAW_DEG` 0°) and looks in from
the south-south-west, a little above the soil, so the clump fans across the
frame and the lit leaves stand out of the dark wall. The fill is
0.309 × 0.861.

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
| 16 | Not grounded: bounding box `zmin` off 0 (`--lift-z`), or a culm or shoot not bedded 0.020–0.075 m in the soil (`--float-culm`) |
| 17 | Nodes: a ring's crest outside 0.0025–0.0048 m or its inner wall outside 0.0020–0.0060 m (`--sunk-nodes`) |
| 18 | Branches: a first ring outside 0.004–0.010 m inside its culm, or more than 0.010 m off a node (`--stray-branches`) |
| 19 | Size and taper: a culm's height or diameter off its band, heights less than 1.0 m apart, a radius that rises up a culm, or a taper ratio off 0.54–0.66 (`--swell-culm`) |
| 20 | Pitch: fewer than 10 nodes on a culm, a gap outside 0.12–0.38 m, a mean outside 0.23–0.28 m, or a middle third less than 0.06 m longer than the first (`--bunch-nodes`) |
| 21 | Clump: two culms intersect, or come closer than 0.020 m (`--crowd-culms`) |
| 22 | Litter: a blade's deepest vertex outside 0.0005–0.006 m under the soil (`--float-litter`) |
| 23 | Leaves: a leaf's base not 0.0010–0.0052 m inside its branch (`--lift-leaves`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
