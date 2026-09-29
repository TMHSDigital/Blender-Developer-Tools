# Broadleaf oak

A showcase piece, not an example, and the eighth in the `nature` category.
It builds a procedural game-ready mature, open-grown English oak (*Quercus
robur*), about 8.0 m tall with a broad, domed crown about 11.3 × 9.3 m
across, standing on a grassy soil disc that rises toward the back:

- a trunk lathed in one piece from a six-lobed buttress flare, bedded in the
  soil, to a dome over a low fork at 2.3 m. The short bole is 0.73 m across
  at breast height. Seven broad flutes and twelve bark ridges run up it;
- six surface roots, one out of each buttress, lying in the soil (wider than
  they are deep) and diving into it;
- five heavy, crooked scaffold limbs that start inside the trunk under the
  fork, the low ones long and near level, the high ones steep. Each divides
  three more times (3, 4 and 3 children per branch): 260 branches in all,
  every one a tapered tube whose base lies inside its parent. A parent
  narrows past each junction by the area of the child it gives off
  (da Vinci's rule), so a branch's area is shared among its children and its
  own tip;
- clusters of lobed oak leaves on every live twig tip (three along the
  twig's outer half, three at its end) and on the tip of every branch: 1370
  leaves on 255 carriers build the crown. Five of the lowest twigs are dead,
  barkless and bare, with broken ends;
- seven stalks of hanging acorns, two or three on each, under the lower
  crown; each acorn is a scaly cup with a glossy nut seated in it;
- on the soil: twenty grass tufts, thirty-four curled fallen leaves, ten
  fallen acorns and two dead sticks.

Every branching draw comes from `random.Random(SEED)` in `plan_tree()`,
before anything is built: root bearings and reach, scaffold bearing,
elevation and area share, which segments give off children, each child's
share, azimuth and spread, the dead twigs, the acorn clusters and the ground
cover. Per-leaf variety (size, lobe widths, roll, fold, droop, tone) comes
from a closed-form hash of indices. No flag draws from the stream, so a
falsifier changes only what it names.

Branch lengths are fitted to a crown envelope: a scaffold reaches 0.52–0.66
of the way from its base to a squat ellipsoid (5.6 × 5.1 m, 3.0 m above and
2.45 m below its centre), a first-order branch 0.66–0.84 and a second-order
branch 0.70–0.92 of the way from its junction; twigs are 0.38–0.62 m. Low
branches spread outward and high ones climb, so the leaf clusters build a
dome rather than five radial arms.

A leaf is one closed, thin shell of 32 triangles: an outline of auricles,
three rounded lobes a side and an apex, shared by a top and a bottom surface
each zipped to its own midrib vertex, so every rim edge has one face above
and one below. The blade folds up from its midrib and droops toward its
apex. Leaves are 0.54–0.70 m long: stylised, like `pine-tree`'s needle
strands. A real oak leaf is 8–12 cm and the crown would need about thirty
times as many. Each leaf turns its face out of the crown and a little up,
so the crown shows leaf faces from every side; its petiole sits inside its
twig. Leaves are flat-shaded; a `Tone` face attribute makes outer and
higher leaves lighter, and a second UV map (`LeafUV`, not the baked
`UVMap`) draws a pale midrib and lateral veins.

The bark is grey-brown, cut by deep fissures into long plates, with moss on
the shaded (north, +Y) side of the foot. The pattern follows each tube: a
`Grain` point attribute holds the tube's own tangent (straight up the
trunk), and the shader squeezes object coordinates along it, so fissures run
along every limb instead of across it. Wood, soil and acorns are
smooth-shaded; leaves and grass stay faceted; every material boundary is a
hard edge. Eight materials: bark, leaf, deadwood, nut, cup, soil (turf),
grass, litter.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

The collider is the convex hull of the bole alone: a 14-sided frustum from
under the soil to the fork and a point over the dome, without flutes,
buttresses or roots, because players walk under the crown. The hull is
built from points only. A first draft handed it the lathe's faces as well,
and the hull kept them alongside its own (94 triangles against 54).

The piece is heavier than `pine-tree` (68,350 against 45,852 triangles):
64% of it is leaves. A broadleaf crown has to show leaf faces, where a
conifer's can be strands.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 67700–69000 | 68350 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 8 distinct; face floors bark ≥7070, leaf ≥41600, deadwood ≥120, nut ≥1280, cup ≥1040, soil ≥1820, grass ≥2730, litter ≥1030 | 8 slots; 7447 / 43840 / 132 / 1350 / 1100 / 1918 / 2880 / 1088 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (11.282, 9.306, 7.999) m ± 0.01 | (11.2821, 9.3063, 7.9994), zmin 0 |
| Collider tris (bole hull) | ≤ 60 | 54 |
| Export | written, size > 0, removed after measuring | 8201952 bytes |

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

The soil disc's flat underside is the only geometry at Z = 0. Nothing is
clamped to the floor plane. Ground cover is kept well inside the disc's
rim: in a draft, cover scattered out to the rim roll-off overhung it, the
ray under the overhanging vertices found no soil and read 0, and settling
took the piece 5–8 mm under Z = 0.

### Organic invariants

A tree has no joinery. What makes it read as an oak is that each branch
grows out of its parent and is thinner than it, that its leaves are on its
twigs, that it stands straight in the ground under its crown, and that its
acorns hang on stalks and lie in the grass. Each face carries `Part`,
`Ident` and `Parent` tags and each tube vertex a `Ring` tag, so a shell can
be named and a tube's rings found; every measurement is then made on the
shell's geometry.

| Axis | Declared | Measured |
| --- | --- | --- |
| Branch seat: for each branch, the shallowest vertex of its base cap inside its parent (ray-parity signed depth), over the parent's local radius (the trunk's ring at that height, or the thinner ring of the parent segment its axis meets) | ≥ 0.06, and 260 branches found | 0.0923–0.6055, 260 |
| Taper (da Vinci): at every junction, (parent ring after² + child base²) / parent ring before², with the junction found where the child's first two ring centres meet the parent's axis | 0.90–1.05 | 0.9586–0.9872, 255 junctions |
| Taper: every child's base radius over its parent's ring before the junction | ≤ 0.80 | ≤ 0.6691 |
| Taper at the fork: the five scaffolds' summed base area over the trunk's last ring under them | 0.80–1.05 | 0.8939 |
| Nut seat: each nut's deepest vertex inside its own cup (hanging and fallen) | 0.006–0.020 m, 25 nuts | 0.0112–0.0113 |
| Trunk plumb: least-squares lean of the level ring centroids from 0.35 m to 2.2 m above the soil | ≤ 1.0° | 0.554° |
| Crown balance: leaf-area centroid off the trunk axis at 0.4 m, horizontally | ≤ 0.45 m | 0.2969 m (centroid at 4.98 m) |
| Diameter at breast height (ring nearest 1.3 m above the soil at the axis) | 0.731 m ± 0.020 | 0.7313 |
| Trunk sealed: sectors round its foot (8) holding a trunk vertex ≥ 5 mm under the soil straight above it | 8 of 8 | 8 |
| Roots bedded: each root's vertices outside the trunk binned every 0.25 m by distance from the axis; each bin's most-buried vertex under the soil | ≥ 0.010 m, 6 roots | ≥ 0.0293 |
| Leaf clusters: each leaf's petiole (its `Tip` = 0 vertex) inside its own carrier (the twig or branch tagged as its `Parent`) | ≥ 0.0015 m, 1370 leaves on 255 carriers | 0.0025–0.0465 |
| Hanging acorns: each stalk's deepest vertex inside its branch; each pedicel's inside its stalk and inside its cup | stalk ≥ 0.004, pedicel in stalk ≥ 0.002, in cup ≥ 0.006 m; 7 stalks, 15 pedicels | 0.0080 / 0.0036 / 0.0134 |
| Ground cover: most-buried vertex under the soil straight above it, per piece (a fallen cup and nut together) | tufts 0.040–0.090 m, leaves, acorns and sticks 0.003–0.030 m; 66 pieces | tufts 0.0603–0.0645, others 0.0080 |
| Ground cover joined to the soil (union of shells whose BVH trees overlap) | every cover shell in the soil's component | 76 of 76 |

The trunk's two foot rings follow the soil read back by a ray under each
vertex, the lowest 45 mm under it; the level rings above start 0.17 m over
the soil at the axis and keep a fixed count, so a falsifier that moves the
foot keeps the topology. The seal test runs sector by sector because the
bank slopes 85 mm per metre: a foot set from the soil at the axis alone is
bedded uphill and open downhill.

The branch seat is normalised by the parent's own radius, so a 0.3 m trunk
and a 9 mm twig tip are held to the same fraction. The taper junction is
found from the child's axis line, not from its base cap: a first draft
projected the base cap onto the parent, so `--float-branches` moved the
junction it measured along with the cap and exited 20 on the taper instead
of 17 on the seat. The axis line is the same whether the tube starts inside
its parent or outside it.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
4.5.11 and exited its declared code. The envelope and the triangle count
were unchanged in every run.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-branches` | branch seat (every tube starts 1.3 parent radii plus its own radius along its path, or 0.85 of its first segment: shallowest −1.8098) | 17 |
| `--pop-nuts` | nut seat (hanging nuts pushed 35 mm out along the cup's axis: −0.0228 m) | 18 |
| `--lean-crown` | trunk plumb (bole bent `x += 0.040 (z − 0.55)²` up to 2.05 m above the soil, the crown carried over rigidly: lean 3.146°) | 19 |
| `--fat-twigs` | taper (every twig 1.8× thicker: junction ratio up to 1.9704, a child 1.2044 of its parent) | 20 |
| `--perch-trunk` | trunk sealed (foot rings set from the soil at the axis alone: 6 of 8 sectors) | 21 |
| `--arch-roots` | roots bedded (each root's middle lifted clear of the soil: shallowest station −0.0628 m) | 21 |
| `--orphan-clump` | leaf clusters (the leaves of the live twig nearest the crown's centre dropped 0.30 m off it: −0.0479 m) | 22 |
| `--drop-acorns` | hanging acorns (cups and nuts lowered 60 mm off their pedicels: pedicel in cup −0.0461 m) | 23 |
| `--float-cover` | ground cover (tufts, fallen leaves, fallen acorns and sticks lifted 60 mm: 45 shells not joined, tufts 0.0017–0.0034 m) | 24 |

`--float-branches` keeps each branch's path, so its tip and everything
carried on it stay put; only the tube's first ring moves. `--fat-twigs` also
bursts twigs out of their parents, so the taper (20) is checked before the
seat (17) and names the cause. `--lean-crown` bends only the bole under the
fork and carries the crown over rigidly, so the envelope keeps its size.
`--pop-nuts` and `--drop-acorns` move the hanging acorns only, never past the
crown's underside. `--orphan-clump` moves one interior cluster, so no leaf
at the envelope moves.

## Run

```bash
blender --background --python broadleaf_oak.py --
blender --background --python broadleaf_oak.py -- --skip-decimate
blender --background --python broadleaf_oak.py -- --stray-vert
blender --background --python broadleaf_oak.py -- --lift-z
blender --background --python broadleaf_oak.py -- --float-branches
blender --background --python broadleaf_oak.py -- --pop-nuts
blender --background --python broadleaf_oak.py -- --lean-crown
blender --background --python broadleaf_oak.py -- --fat-twigs
blender --background --python broadleaf_oak.py -- --perch-trunk
blender --background --python broadleaf_oak.py -- --arch-roots
blender --background --python broadleaf_oak.py -- --orphan-clump
blender --background --python broadleaf_oak.py -- --drop-acorns
blender --background --python broadleaf_oak.py -- --float-cover
blender --background --python broadleaf_oak.py -- --output oak.png
```

Smoke passes no flags.

The hero keeps the tree at `HERO_YAW_DEG` (0°) and looks at it from the
front left, a little below the crown's middle, so the heavy low limbs and
the fork read under the dome with the limbs showing through the gaps, and
the short bole, buttresses and soil disc read below it. Framing measures
fill x 0.616, y 0.856. A warm wedge pools on the floor behind and to the
right and washes the wall above it.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene, grounded, joint-fit (branch seat), seat-conformance (nut in cup)
and plumb family. `20`–`24` are file-local; `20` is checked before `17`.
`25` is the asset-quality floor on the render path: `check_asset_quality`
returns 11, which this piece already spends on the collider ceiling, so the
call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or not one trunk and one soil shell |
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
| 17 | Branch seat: a branch's base cap not inside its parent, or not 260 branches (`--float-branches`) |
| 18 | Nut seat: a nut out of its depth band in its cup, or not 25 nuts (`--pop-nuts`) |
| 19 | Trunk plumb, crown balance or breast-height diameter out of band (`--lean-crown`) |
| 20 | Taper: a junction's area ratio out of band, a child too wide for its parent, or the fork's area ratio out of band (`--fat-twigs`) |
| 21 | Sealed: the trunk open in a sector round its foot, or a root station not bedded (`--perch-trunk`, `--arch-roots`) |
| 22 | Leaf clusters: a petiole not inside its twig, or not 1370 leaves on 255 carriers (`--orphan-clump`) |
| 23 | Hanging acorns: a stalk not in its branch, a pedicel not in its stalk or its cup (`--drop-acorns`) |
| 24 | Ground cover: a piece out of its depth band under the soil or not joined to it, or not 66 pieces (`--float-cover`) |
| 25 | Asset-quality floor (render path only; remapped from 11) |
