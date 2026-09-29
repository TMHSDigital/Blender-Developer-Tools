# Pine tree

A showcase piece, not an example, and the first in the `nature` category.
It builds a procedural game-ready mature Scots pine, about 7.4 m tall with
a broad, rounded crown about 8.7 × 7.3 m across, standing on a small disc
of needle-litter soil:

- a trunk lathed in one piece from a five-lobed buttress flare, bedded in
  the soil mound, to a leader shoot. The tall bole is bare to about 3 m. It
  carries twelve deep vertical plate ridges that fade out between 1.9 m and
  3.0 m into thin upper bark;
- five surface roots, one running out of each flare lobe and diving into
  the soil;
- five broken dead stubs and two long dead lower limbs, each limb carrying
  three dead twigs, on the bare bole;
- eight whorls of heavy limbs above the bole, 3 to 5 limbs per whorl. Each
  limb is a crooked, tapered bar that starts inside the trunk. Lower limbs
  are long, run out nearly level and carry bigger pads. Upper limbs rise
  more steeply and are shorter, which flattens the top. The crown is
  broadest across the hero view;
- one to three side twigs alternating along the outer part of each limb.
  Every limb and twig ends inside a needle clump,
  and so does the leader: 113 needle brushes overlap into one crown;
- clusters of two or three cones hanging under limbs in the upper crown;
- on the soil, five fallen cones, two mossy stones and two dead sticks.

Every draw comes from `random.Random(SEED)` in `plan_tree()`, before
anything is built: whorl spacing, limb count, yaw, length, rise, droop,
crook, cone clusters and the ground cover. Per-clump and per-tuft variety
comes from a closed-form hash of indices. No flag draws from the stream,
so a falsifier changes only what it names.

A needle clump is one closed shell: a brush of 108 long, thin needle
strands. Its core is a small, dark, flattened cube-sphere (3 × 3 facets a
side, 0.24 of the pad's radius), tipped up to 14° off level and lumpy.
Every core facet is split in two, and each half is drawn out into one
tapered strand. Each strand is aimed along the core's outward direction
plus a hashed scatter, so the strands splay through the whole dome instead
of lying in a plane, and it reaches 0.78–1.18 of the pad's ellipsoid. The
core is small beside the strands' length, so every strand is a narrow
sliver about ten times as long as it is wide. The underside of the
ellipsoid is flatter than its dome. Strands are flat-shaded. A `Tip`
point attribute runs each strand from a shaded base to a lighter, greyer
point, and a second UV map (`NeedleUV`, not the baked `UVMap`) lays a
fine line down each strand. Each clump takes its own soft blue-green
tone: lighter outside and high, shaded in the crown's heart. Upward facets
carry a glaucous bloom.

The strands are stylised, not botanical. A real Scots pine needle is
1–2 mm wide and 40–70 mm long. At that size the crown would need tens of
thousands of strands, and the triangle budget holds about 12,000. Each
strand here stands for a spray of needles: about 0.4–0.8 m long and a few
centimetres wide at its base.

Two earlier passes were rejected. Lathed pads whose facets rose into
pyramids read as crystalline shingles. Pom-poms whose wide core facets
were drawn out into short points read as flat star rosettes, holly or
maple leaves at thumbnail size. The small core and scattered aim fix both,
at the cost of fewer, bigger clumps (113, down from 223).

The bark follows Scots pine: thick grey-brown plates on the lower bole,
changing over 1.9 to 3.4 m into thin fox-red flaking bark. The upper bole
and every limb are red. Wood, soil and stone are smooth-shaded, and every
material boundary is a hard edge. Dead wood is barkless silver-grey. The
soil is dark humus under crossing streaks of rust and grey needle litter,
and the stones carry moss on their upward faces.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

The collider is the convex hull of a 14-sided trunk alone, without ridges
or roots, because players walk under the branches. The side count is
chosen for the ceiling: a 20-sided hull measured 58 triangles and a
10-sided one 80, while 14 sides give 56.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 43500–46000 | 45852 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 6 distinct; face floors bark ≥2850, needle ≥35000, cone ≥950, deadwood ≥250, soil ≥820, stone ≥170 | 6 slots; 3026 / 36612 / 1024 / 274 / 878 / 192 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (9.284, 7.932, 7.659) m ± 0.01 | (9.2837, 7.9318, 7.6586), zmin 0 |
| Collider tris (trunk hull) | ≤ 60 | 56 |
| Export | written, size > 0, removed after measuring | 5703388 bytes |

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

The soil disc's flat underside is the only geometry at Z = 0. The trunk's
foot is bedded 0.10 m under the lowest soil round the flare instead of
standing on the floor plane, and nothing is clamped to Z = 0, so no other
face can land coplanar with it.

### Branch seat, whorl tiers, plumb, clumps, ground and assembly

These are the organic invariants. A tree has no joinery. What makes it
read as a pine is that its limbs grow out of the trunk in whorls, its
needles sit on the ends of its twigs, and it stands straight in the ground
under its crown.

The trunk axis is read off the mesh. Every lathe ring shares one height,
so the ring centroids give the axis and the ring radii give the girth.
Each face carries a `Part` tag (trunk, limb, twig, clump, cone, soil and
so on) so a shell can be named; every measurement is then made on the
shell's geometry.

| Axis | Declared | Measured |
| --- | --- | --- |
| Branch seat: for each of the 33 limbs and 7 seated dead members, the base ring's centre distance from the trunk axis at its height, over the trunk surface radius on the same bearing (raycast from the axis) | 0.25–0.75, and 33 limbs and 7 dead members found | 0.4259–0.4656, 33 / 7 |
| Whorl tiers: limb bases clustered by height (split at 0.18 m) | 8 whorls of 3–5 limbs, each whorl within 0.06 m, gaps between whorls 0.32–0.60 m | 8 whorls `[5, 5, 3, 5, 5, 3, 3, 4]`, spread ≤ 0.0350, gaps 0.4037–0.4479 |
| Trunk plumb: least-squares lean of the ring centroids from 0.8 m to 5.7 m | ≤ 1.0° | 0.489° |
| Crown balance: needle-area centroid off the trunk axis at 0.5 m, horizontally (the tip-over check) | ≤ 0.15 m | 0.0466 m (centroid at 4.93 m) |
| Diameter at breast height (ring nearest 1.3 m above the soil at the axis) | 0.377 m ± 0.020 | 0.3768 |
| Clump seat: for each clump, the signed depth of its own carrier's deepest vertex inside it (ray-parity inside test; the carrier is the limb, twig or leader tagged with the clump's id in a `Carry` face attribute) | ≥ 0.040 m, and 113 clumps found | 0.0592–0.1366 m, 113 |
| Ground cover: each fallen cone and stick's deepest vertex under the soil straight above it | 0.004–0.040 m | cones 0.0095–0.0102, sticks 0.0097–0.0100 |
| Ground cover: each stone's deepest vertex under the soil (the whole flat bed sits ≥ 0.025 m under) | 0.015–0.120 m | 0.0448–0.0451 |
| Roots and foot: each root's deepest vertex under the soil, and the trunk foot's depth | roots ≥ 0.030 m, foot ≥ 0.050 m, 9 cover pieces found | roots ≥ 0.0910, foot 0.1175, 9 |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (266 shells) |

The clump seat is measured per clump against its own carrier, not against
any bark nearby. The crown is dense enough that limbs pass through their
neighbours' clumps, so "some bark is inside" would pass a clump whose own
twig stops short of it.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. The envelope was unchanged in every run.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-branches` | branch seat (every limb's tube starts at 1.2 × the trunk radius, outside the bark: worst 1.2447) | 17 |
| `--lean-crown` | trunk plumb (bole bent `x += 0.030 (z − 1)²` up to 2.95 m, the crown carried over rigidly: lean 1.205°) | 19 |
| `--bunch-whorls` | whorl tier spacing (whorl 5 lifted 0.24 m into whorl 6: 7 tiers, gaps up to 0.7121 m) | 20 |
| `--short-twigs` | clump seat (every carrier stops where it has entered 0.36 of the way into its pad's ellipsoid, short of the core: shallowest −0.1955 m) | 22 |
| `--float-litter` | ground cover bedded in the soil (cones, stones and sticks lifted 0.08 m: cones −0.0705, stones −0.0352, sticks −0.0703) | 23 |
| `--drop-cones` | one connected assembly (hanging cones lowered 50 mm off their limbs: 10 components) | 21 |

`--float-branches` keeps each limb's path, so the tip and everything hung
on it stay put. Only the tube's first ring moves out of the bark.
`--lean-crown` bends only the bole under the lowest whorl and carries the
crown over rigidly, so the envelope keeps its size to the tenth of a
millimetre and the plumb budget is what fails. An earlier draft bent the
whole axis quadratically, which grew the X extent 17.7 mm and exited 8 on
the envelope instead; the bend was moved, the band was not widened.
`--bunch-whorls` lifts one mid-crown whorl, whose limbs are not the
extremes of the envelope. `--short-twigs` keeps the point count of every
carrier, so the face budgets hold; it also splits the tree into 2
components, but the clump seat is checked first and names the cause.
`--float-litter` likewise detaches the lifted pieces (9 components), and
the bedding budget is checked before the component count. `--drop-cones`
leaves the rest of the tree whole: 9 cones float free and the tree is
the 10th component.

## Run

```bash
blender --background --python pine_tree.py --
blender --background --python pine_tree.py -- --skip-decimate
blender --background --python pine_tree.py -- --stray-vert
blender --background --python pine_tree.py -- --lift-z
blender --background --python pine_tree.py -- --float-branches
blender --background --python pine_tree.py -- --lean-crown
blender --background --python pine_tree.py -- --bunch-whorls
blender --background --python pine_tree.py -- --short-twigs
blender --background --python pine_tree.py -- --float-litter
blender --background --python pine_tree.py -- --drop-cones
blender --background --python pine_tree.py -- --output pine.png
```

Smoke passes no flags.

The hero keeps the tree at `HERO_YAW_DEG` (0°) and looks at it from the
front left, across the crown's broad axis. The camera sits a little below
the crown's middle, so the skirt of heavy lower limbs reads against the
wall with the red limbs showing through, and the bare bole, dead limbs and
soil disc read below it. Framing measures fill x 0.509, y 0.794. A warm
wedge pools on the floor behind and to the right and washes the wall above
it.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`17` and
`19` are the hygiene, joint-fit and plumb family. `18` is not used: no
budget here is a wrapper's seat. `20`–`23` are file-local; `22` and `23`
are checked before `21`, so a falsifier that also detaches parts still
names its own budget. `24` is the asset-quality floor on the render path:
`check_asset_quality` returns 11, which this piece already spends on the
collider ceiling, so the call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or not one trunk and one soil shell |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 6 distinct slots, or a face-count floor missed |
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
| 17 | Branch seat: a limb or dead member's base outside its band in the trunk, or not 33 limbs and 7 dead members (`--float-branches`) |
| 19 | Trunk plumb, crown balance or breast-height diameter out of band (`--lean-crown`) |
| 20 | Whorl tiers: not 8 whorls of 3–5 limbs, a whorl spread too wide, or a gap between whorls out of band (`--bunch-whorls`) |
| 21 | Tree splits into more than one connected component (`--drop-cones`) |
| 22 | Clump seat: a carrier ends too shallow inside its clump, or not 113 clumps (`--short-twigs`) |
| 23 | Ground bedding: a cone, stick or stone out of its depth band under the soil, a root or the trunk foot too shallow, or not 9 cover pieces (`--float-litter`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
