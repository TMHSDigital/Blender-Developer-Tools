# Sea stack and arch

A showcase piece, not an example, and the tenth in the `nature` category.
It builds a procedural game-ready coastal diorama tile, about 2.54 × 1.92 m
across and 1.62 m high: a fragment of a bedded sandstone headland on a
wave-cut rock platform, with a natural arch through it and a sea stack in
the bay beside it.

- **The beds.** Sixteen layers of sandstone, hard beds of uneven thickness
  (42–168 mm) alternating with thin soft ones (20–56 mm), at the same
  heights in every column, so the strata run on from the arch into the
  stack. The soft beds are undercut behind the hard beds either side, so
  every hard bed projects as a ledge; the undercut comes and goes along a
  face, deep in places and all but flush in others, and is deepest at the
  foot of each leg (the wave-cut notch).
- **Joints and blocks.** The fin's outline is cut by vertical joint faces
  (twelve planes: the front and back faces, both ends and their corners)
  shared by both legs and the lintel, so a face runs on up through every
  bed. Each bed sets each face back by its own amount, drifting coherently
  with height, so a face leans and bellies; now and then a bed has broken
  back further. Vertical joints cross the fin and split every bed into
  blocks that stand back by their own amounts, the joint opened as a narrow
  V, and here and there a block has fallen out of a hard bed and left a
  gap. Corners are chipped by fracture planes.
- **The arch.** Two legs of stepped beds: each hard bed of a leg reaches a
  little further into the opening than the one below (0.50 m wide at the
  foot, 0.26 m under the roof), and a lintel of four hard beds spans them,
  its lowest bed whole but for the crown joint over the opening. The
  lintel's upper beds step down toward the sea.
- **The stack.** A smaller column of the same beds (twelve layers, 1.10 m)
  on its own low island in the bay, cut by eight joint faces.
- **The platform.** A wave-cut shelf 70 mm over the water, crossed by the
  same two joint sets as faint cracks, with a bay, a channel that runs
  through the arch into a pocket behind it, the stack's island and two tide
  pools. Its rim rolls down to a flat base, the beds shown in section.
- **The sea.** A rippled sheet at a declared level of 0.105 m, its rim run
  50 mm under the platform all round, calm near the shore; each tide pool is
  a flat sheet 12 mm under the lowest point of its rim. A foam line, a thin
  closed band, lies at the waterline round the bay and round the island,
  its land edge tucked 30 mm in under the rock.
- **Loose rock.** Five fallen blocks (bed fragments cut by fracture planes)
  and eight rounded boulders on the platform, sealed into it all round and
  held apart.
- **The tops.** A turf mat over the fin's top bed and the stack's, with
  tufts of sea grass and cushions of sea thrift (narrow leaves and pink
  heads on stalks).

The littoral bands are in the materials: green weed at the waterline, a
barnacle crust over it, a black lichen band above, then orange and grey
lichen and bird lime high up; overhangs stay dark and damp.

Every seeded draw comes from `random.Random(SEED)` in `plan_scene()`, before
anything is built: each face's drift and set-backs, each bed's blocks,
joints, chips and undercut, the loose rock and the cover. Per-point variety
comes from closed-form functions of position. No flag draws from the
stream, so a falsifier changes only what it names.

Every column is sampled on one fixed set of rays from its centre (the first
hard bed's outline, evenly along its length), and a bed's outline on a ray
is where the ray leaves the intersection of its half-planes, each set in by
the bed's set-back. A soft bed on a ray lies inside both hard beds either
side by construction, so the bites and undercuts are exact. The piece is a
stack of flat beds and planar faces, which is a coplanar hazard: each bed's
walls batter by their own degree or two, arrises carry a sub-millimetre
wear ray by ray, and a final pass draws any soft-bed facet that still lands
in another bed's plane 1.5 mm further in, and turns any blade, stalk or
head that lands in another shell's plane 3° about its root.

Rock is smooth-shaded with a 18° crease, so the arrises and joints stay
crisp and a face stays flat; grass and heads smooth. Eight materials:
sandstone (the beds and fallen blocks), wave-cut shelf, sea water, foam,
cobble, turf, grass (sea grass and thrift leaves and stalks), sea thrift.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

The collider is five convex hulls joined in one mesh, built from points
only: each leg, the lintel, the stack and the platform, so a player can
pass under the arch.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 77600–78800 | 78182 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 8 distinct; face floors sandstone ≥43000, shelf ≥10300, water ≥4600, foam ≥1430, cobble ≥830, turf ≥3800, grass ≥4990, thrift ≥1200 | 8 slots; 44404 / 10654 / 4778 / 1480 / 864 / 3932 / 5147 / 1248 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.5440, 1.9225, 1.6184) m ± 0.01 | (2.5440, 1.9225, 1.6184), zmin 0 |
| Collider tris (five hulls) | ≤ 380 | 342 |
| Export | written, size > 0, removed after measuring | 7906368 bytes |

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. The plan is seeded and nothing else is random; two
default runs print identical measurements, and 4.5.11 and 5.1.2 print the
same measurements as 5.2.1.

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

The platform's flat underside is the only geometry at Z = 0.

### Organic invariants

A headland has no joinery. What makes this read as a sea arch is that the
beds lie level and run on from column to column, that the soft beds are
cut back under the hard ones, that the lintel rests on both legs and the
legs and the stack stand in the platform, that there is a clear hole
through it, that the stack stands over its own foot, that the sea lies
level in a basin of rock with its foam at the waterline, that the fallen
blocks rest on the platform, and that the turf and flowers grow out of the
tops. Each face carries `Part`, `Ident` (column and layer), `Layer`, `Hard`
and `Cap` tags and each vertex a `Ring`, so a bed, its end rings and its
top can be named; every measurement is then made on the shell's geometry.

| Axis | Declared | Measured |
| --- | --- | --- |
| Beds bite: every soft bed's end ring, shallowest vertex inside the hard bed it runs into (ray-parity signed depth), the lintel's lowest bed over each leg included | 0.002–0.040 m, 35 joints | 0.0026–0.0142; lintel on the legs 0.0120, 0.0120 |
| Stack plumb: the volume centroid of all its beds inside the convex footprint of its narrowest section (the foot notch's middle ring) | ≥ 0.050 m | 0.1220 |
| Feet sealed: for each leg and the stack, in each of 8 sectors round the lowest bed, its most-buried vertex under the platform straight above it | ≥ 0.020 m in 8 of 8 | worst 0.0373, 8 of 8 each |
| Aperture: rays along +Y past every bed; clear height up the opening's centre line from the water, and the narrowest clear width over the 0.60 m above the water | width ≥ 0.20 m, height ≥ 0.60 m | width 0.3680, height 0.7370 |
| Bedding level: a least-squares plane through every hard bed's top-cap vertices; its tilt, and per layer the spread of the fitted heights across the columns | tilt ≤ 0.8°, spread ≤ 0.004 m, 18 bed tops | tilt 0.0000°, spread 0.00000 |
| Undercut: per soft bed, the median over its middle ring of how far the hard beds either side stand out past it, cast along its own outward normal at their mid-height | 0.008–0.090 m, 19 soft beds | 0.0133–0.0290 |
| Water: the median height of the sea's top sheet and its largest excursion from it; each pool's top flat | level 0.105 ± 0.0015 m; ripple 0.0015–0.0090 m; pools ≤ 0.0005 m | 0.10500; 0.00238; 0.0, 0.0 |
| Water contained: the platform over every rim vertex and rim-edge midpoint of the sea's and each pool's top (a ray down onto the platform) | ≥ 0.008 m, 512 points | 0.01226 |
| Foam seated: every foam vertex off the water's level; its land edge's top under the platform | ≤ 0.006 m; ≥ 0.004 m, 2 loops | 0.00430; 0.01403 |
| Loose rock sealed: per block and boulder, in each of 8 sectors, its most-buried vertex under the platform | ≥ 0.003 m, 13 pieces | worst 0.0050 |
| Loose rock apart: pairs of blocks and boulders whose BVH trees overlap | 0 | 0 |
| Cover rooted: every blade's and stalk's base cap inside the turf or the top bed under it (the deeper of the two); every blade, stalk and head joined to its top | 0.004–0.060 m, 289 roots; none loose | 0.0078–0.0189; none loose |

The feet are bedded against the platform as built: each lowest bed's foot
is set 30 mm under the lowest platform point beneath its widest ring, and
kept off the sea sheet's two planes. The pools' levels are read off the
built platform too: taken from the analytic surface, a pool's rim sat only
4 mm over its water where the grid cut the rim's ramp.

## Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
4.5.11 and exited its declared code. The envelope and the triangle count
were unchanged in every run.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--gap-lintel` | beds bite (the left leg's top bed stopped 15 mm under the lintel: −0.0150 m) | 17 |
| `--lean-stack` | stack plumb (the stack sheared 0.30 m per metre of height toward the sea: 0.0048 m) | 19 |
| `--cut-pillar` | feet sealed (the right leg's foot stopped 20 mm over the platform: worst sector −0.0269 m, 0 of 8) | 20 |
| `--close-arch` | aperture (the right leg brought 0.22 m into the opening: width 0.0000 m, height 0.4490 m) | 21 |
| `--tilt-beds` | bedding level (the interior bed boundaries turned 2.5° about a line across the fin: 2.536°) | 22 |
| `--flush-beds` | undercut (every soft bed's middle rings 5.5 mm behind the hard beds, its bites unchanged: 0.0061–0.0068 m) | 23 |
| `--flat-sea` | water level and ripple (the sheet laid flat: ripple 0.00000 m) | 24 |
| `--short-sea` | water contained (the rim stopped 50 mm short of the shoreline: −0.05304 m) | 25 |
| `--lift-foam` | foam seated (the foam raised 20 mm: 0.02430 m off the water, land edge −0.00597 m) | 26 |
| `--perch-talus` | loose rock sealed (each piece seated against the platform at its centre alone: −0.0393 m) | 27 |
| `--pile-talus` | loose rock apart (three blocks drawn together unrelaxed: 3 pairs overlap) | 28 |
| `--float-cover` | cover rooted (every blade and stalk base raised 50 mm, its tip held: −0.0173 m, 315 pieces loose) | 29 |

The fin's grass and thrift are the top of the envelope, so `--float-cover`
holds every tip where it was and moves the bases alone. `--lean-stack`
shears the stack horizontally about its foot, which keeps each bed's
footprint over the one below at every height, so the bites do not steal
it; `--close-arch` moves only the right leg's inner face; `--tilt-beds`
turns the interior boundaries only, leaving the foot and the fin's top.

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
blender --background --python sea_stack_arch.py -- --output arch.png
```

Smoke passes no flags.

The hero does not turn the piece (`HERO_YAW_DEG` 0) and looks at the fin
from the front, 13° to the left of the arch's axis and a little above the
lintel's underside, so the opening reads against the warm wedge on the
wall behind it and the stack stands clear to its right. Framing measures fill x 0.625, y 0.861, margins left 0.172, right
0.203, bottom 0.028, top 0.111; the asset-quality floors pass (8
materials, edge90 0.033).

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`17` and `19`
are the hygiene, grounded, joint-fit (beds bite) and plumb (stack) family;
`18` is not used. `20`–`29` are file-local. `30` is the asset-quality
floor on the render path: `check_asset_quality` returns 11, which this
piece already spends on the collider ceiling, so the call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or not one platform, one sea and 37 bed shells |
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
| 17 | Beds bite: a soft bed's end ring not inside the hard bed it runs into, the lintel's lowest bed on a leg included (`--gap-lintel`) |
| 19 | Stack plumb: its mass centre not inside its footprint (`--lean-stack`) |
| 20 | Feet sealed: a sector round a leg's or the stack's foot not bedded in the platform (`--cut-pillar`) |
| 21 | Aperture: the opening's clear width or height under its minimum (`--close-arch`) |
| 22 | Bedding: a bed top tilted, or a layer's height not continuous across the columns (`--tilt-beds`) |
| 23 | Undercut: a soft bed recessed outside its band (`--flush-beds`) |
| 24 | Water: the sea off its level or its ripple outside the band, or a pool not flat (`--flat-sea`) |
| 25 | Water contained: a sheet's rim not under the platform (`--short-sea`) |
| 26 | Foam: off the waterline, or its land edge not under the rock (`--lift-foam`) |
| 27 | Loose rock: a sector of a block or boulder not bedded in the platform (`--perch-talus`) |
| 28 | Loose rock: two pieces overlap (`--pile-talus`) |
| 29 | Cover: a root out of its band in the turf, or a piece not joined to its top (`--float-cover`) |
| 30 | Asset-quality floor (render path only; remapped from 11) |
