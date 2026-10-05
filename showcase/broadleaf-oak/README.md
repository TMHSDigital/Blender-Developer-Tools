# Broadleaf oak

A showcase piece, not an example, and the eighth in the `nature` category.
It builds a procedural game-ready mature, open-grown English oak (*Quercus
robur*), about 9.0 m tall with a broad, domed crown about 11.5 × 11.7 m
across, standing on a grassy mound:

- a massive trunk lathed in one piece from a seven-lobed buttress flare,
  bedded in the soil, to a dome over a low fork at 2.15 m. The short bole is
  1.11 m across at breast height. Eight broad flutes run up it, and 21 bark
  plates with broad flat tops and narrow, deep furrows that wander and fork
  up the bole; a `Furrow` point attribute darkens the furrows in the shader;
- seven surface roots, one out of each buttress, lying half out of the soil
  (wider than they are deep) and diving into it;
- five heavy scaffold limbs that start inside the trunk under the fork, each
  kinking the other way at every segment (the oak's zig-zag). The two
  lowest reach out sideways nearly level and dip; steep ones alternate with
  them round the bole, so the crown stands balanced. Each divides three more
  times (3, 3 and 2 children per branch): 155 branches in all, every one a
  tapered tube whose base lies inside its parent. A parent narrows past each
  junction by the area of the child it gives off (da Vinci's rule); twigs
  take 0.7 of the share a larger branch's children would, so they stay thin;
- a crown of 295 cushions. Each is a small jittered-cube core that holds its
  carrier (every live branch end, and rings along the outer part of every
  branch that carries twigs), with two to eleven faceted leaf clusters
  (jittered icosahedra of radius 0.21–0.43 m) set round it, each centred inside the
  core: 2075 clusters. The outer clusters carry 618 small lobed oak leaves.
  Five of the lowest twigs are dead, barkless and bare, with broken ends;
- six stalks of hanging acorns, two or three on each, under the lower
  crown; each acorn is a scaly cup with a glossy nut seated in it;
- on the mound: twenty grass tufts, seventy curled fallen leaves, twelve
  fallen acorns and four dead sticks, two of them forked. Last year's leaves
  drift thick in the turf shader round the bole.

Every branching draw comes from `random.Random(SEED)` in `plan_tree()`,
before anything is built: root bearings and reach, scaffold area shares,
which segments give off children, each child's share, azimuth and spread,
the dead twigs, the acorn clusters and the ground cover. Scaffold bearings
start at `SCAFFOLD_YAW0` and elevations alternate low and steep round the
bole. Per-cushion and per-leaf variety (sizes, jitter, roll, fold, droop,
tone) comes from a closed-form hash of indices. No flag draws from the
stream, so a falsifier changes only what it names.

Branch lengths are fitted to a crown envelope: a scaffold reaches 0.52–0.66
of the way from its base to an ellipsoid (6.3 × 5.7 m, 3.8 m above and
3.5 m below its centre), a first-order branch 0.66–0.84 and a second-order
branch 0.70–0.92 of the way from its junction; twigs are 0.38–0.62 m. Low
branches spread outward and high ones climb, so the cushions build a dome
rather than five radial arms.

### Foliage: why cushions, not only leaves

A real oak leaf is 8–12 cm; a closed lobed leaf costs 24 triangles, so the
whole budget buys about 2500 of them, and a crown of 2500 leaves reads as a
sapling (a first draft here did). The crown is built the way a painter
builds one instead: lumpy leaf masses, lit on top and dark underneath, with
gaps that show the limbs. Clusters are ten times as much canopy per
triangle as leaves.

- A cluster is one closed, 20-triangle jittered icosahedron. Its material
  (`OakCanopy`) breaks it into leaf-sized Voronoi cells, each its own green
  and each tilting the shading normal its own way, with dark gaps between,
  so at hero distance a cluster reads as a spray of small leaves.
- Clusters shade as part of their cushion, not as balls: every canopy corner
  takes a custom normal pointing out of the cushion's centre (0.6) and out
  of the crown (0.4). The normals are exported with the glTF.
- A leaf is one closed, thin shell of 24 triangles: a rim of petiole, three
  lobes a side and the terminal lobe, fanned to a top and a bottom centre
  over the same point of the blade, so the two surfaces never cross. The
  rim is star-shaped from that centre for every hashed lobe width
  (`LEAF_WOB`). Leaves are 0.24–0.32 m long (about 2.5× real), set on the
  outer clusters, rising out of them and turned out of them, and give the
  cushions a leafy fringe and sunlit flecks. A second UV map (`LeafUV`, not
  the baked `UVMap`) draws a pale midrib and lateral veins.
- Up close the clusters are plainly faceted: this is a game-distance
  crown, not a hero-close one.

69% of the triangles are foliage (45,040 in clusters and cores, 14,832 in
leaves). The piece is heavier than `pine-tree` (86,700 against 45,852): a
broadleaf crown is a closed dome of leaf mass, where a conifer's is open
tiers of strands.

The bark is grey-brown, cut by long fissures into plates, with moss on the
shaded (north, +Y) side of the foot. The pattern follows each tube: a
`Grain` point attribute holds the tube's own tangent, and the shader
squeezes object coordinates along it. Wood, soil, acorns and cluster
cushions are smooth-shaded; leaves and grass stay faceted; every material
boundary is a hard edge. Nine materials: bark, leaf, deadwood, nut, cup,
soil (turf), grass, litter, canopy.

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
built from points only; handed faces as well, it keeps them alongside its
own.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 86250–87150 | 86700 |
| LOD1 ratio | 0.32–0.62 of base | 0.4995 |
| LOD2 ratio | 0.10–0.35 of base | 0.2167 |
| Materials | exactly 9 distinct; face floors bark ≥7110, leaf ≥14090, deadwood ≥240, nut ≥1480, cup ≥1210, soil ≥2600, grass ≥2730, litter ≥1590, canopy ≥41100 | 9 slots; 7481 / 14832 / 256 / 1566 / 1276 / 2734 / 2880 / 1680 / 43270 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (11.529, 11.716, 8.958) m ± 0.01 | (11.5288, 11.7164, 8.9575), zmin 0 |
| Collider tris (bole hull) | ≤ 60 | 54 |
| Export | written, size > 0, removed after measuring | 10351900 / 10351900 / 10351880 bytes (4.5.11 / 5.1.2 / 5.2.1) |

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count (4.5.11 and
5.1.2 decimate to 0.5000 / 0.2200). Bake pixels are stochastic, so the bake
gate is `has_data` plus operator `FINISHED`, not byte-identity. The plan is
seeded and nothing else is random; two default runs print identical
measurements, and 4.5.11 and 5.1.2 print the same measurements as 5.2.1
apart from the LOD counts (the glTF differs by 20 bytes).

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
rim, so no settled piece overhangs the roll-off.

### Organic invariants

A tree has no joinery. What makes it read as an oak is that each branch
grows out of its parent and is thinner than it, that its foliage is on its
branches, that it stands straight in the ground under its crown, and that
its acorns hang on stalks and lie in the grass. Each face carries `Part`,
`Ident` and `Parent` tags and each tube vertex a `Ring` tag, so a shell can
be named and a tube's rings found; every measurement is then made on the
shell's geometry.

| Axis | Declared | Measured |
| --- | --- | --- |
| Branch seat: for each branch, the shallowest vertex of its base cap inside its parent (ray-parity signed depth), over the parent's local radius (the trunk's ring at that height, or the thinner ring of the parent segment its axis meets) | ≥ 0.10, and 155 branches found | 0.1926–0.5438, 155 |
| Taper (da Vinci): at every junction, (parent ring after² + child base²) / parent ring before², with the junction found where the child's first two ring centres meet the parent's axis | 0.94–1.02 | 0.9697–0.9898, 150 junctions |
| Taper: every child's base radius over its parent's ring before the junction | ≤ 0.72 | ≤ 0.6560 |
| Taper at the fork: the five scaffolds' summed base area over the trunk's last ring under them | 0.78–0.90 | 0.8347 |
| Nut seat: each nut's deepest vertex inside its own cup (hanging and fallen) | 0.005–0.013 m, 29 nuts | 0.0090 |
| Trunk plumb: least-squares lean of the level ring centroids from 0.35 m to 2.05 m above the soil | ≤ 1.0° | 0.570° |
| Crown balance: area centroid of the leaves and clusters off the trunk axis at 0.4 m, horizontally | ≤ 0.30 m | 0.2148 m (centroid at 5.32 m) |
| Diameter at breast height (ring nearest 1.3 m above the soil at the axis) | 1.110 m ± 0.020 | 1.1100 |
| Trunk sealed: sectors round its foot (8) holding a trunk vertex ≥ 5 mm under the soil straight above it | 8 of 8 | 8 |
| Roots bedded: each root's vertices outside the trunk binned every 0.25 m by distance from the axis; each bin's most-buried vertex under the soil | ≥ 0.020 m, 7 roots | ≥ 0.0437 |
| Cushion on its carrier: each core's carrier (the branch tagged as its `Parent`), its deepest vertex inside the core | ≥ 0.040 m, 295 cores on 150 carriers | 0.0543–0.1807 |
| Cluster in its cushion: each cluster's centroid (the mean of its points) under its core's skin | ≥ 0.010 m, 2075 clusters | 0.0176–0.1292 |
| Leaf in its cluster: each leaf's petiole (its `Tip` = 0 vertex) inside its own cluster | ≥ 0.010 m, 618 leaves | 0.0195–0.0300 |
| Hanging acorns: each stalk's deepest vertex inside its branch; each pedicel's inside its stalk and inside its cup | stalk ≥ 0.010, pedicel in stalk ≥ 0.002, in cup ≥ 0.006 m; 6 stalks, 17 pedicels | 0.0204 / 0.0037 / 0.0106 |
| Ground cover: most-buried vertex under the soil straight above it, per piece (a fallen cup and nut together) | tufts 0.045–0.080 m, leaves, acorns and sticks 0.003–0.030 m; 108 pieces | tufts 0.0588–0.0647, others 0.0080 |
| Ground cover joined to the soil (union of shells whose BVH trees overlap) | every cover shell in the soil's component | 120 of 120 |

The trunk's two foot rings follow the soil read back by a ray under each
vertex, the lowest 45 mm under it; the level rings above start 0.17 m over
the soil at the axis and keep a fixed count, so a falsifier that moves the
foot keeps the topology. Soil is heaped 0.12 m over the root flare, so a
foot set flat from the soil at the axis is open all round.

The plan places every leaf and cluster against the built skin of its host,
read by a ray from the host's centre over both splits of each quad, so a
jittered lump never leaves a petiole outside it. A first measure of the
cluster seat took the deepest vertex of either lump inside the other, and
read −0.09 m for clusters that plainly overlapped their flattened core
(a thin plate through a ball, neither's vertices inside the other); the
centroid depth replaced it.

The branch seat is normalised by the parent's own radius, so a 0.5 m trunk
and a 9 mm twig tip are held to the same fraction. With two twigs per
second-order branch the share rule first made twigs as wide as their parent
(seat −0.048); twigs now take 0.7 of the share.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
4.5.11 and exited its declared code. The envelope and the triangle count
were unchanged in every run.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-branches` | branch seat (every tube starts 1.3 parent radii plus its own radius along its path, or 0.85 of its first segment: shallowest −1.5494) | 17 |
| `--pop-nuts` | nut seat (hanging nuts pushed 35 mm out along the cup's axis: −0.0248 m) | 18 |
| `--lean-crown` | trunk plumb (bole bent `x += 0.040 (z − 0.55)²` up to 1.95 m above the soil, the crown carried over rigidly: lean 2.908°) | 19 |
| `--fat-twigs` | taper (every twig 1.8× thicker: junction ratio up to 1.7240, a child 1.0413 of its parent) | 20 |
| `--perch-trunk` | trunk sealed (foot rings set from the soil at the axis alone: 0 of 8 sectors) | 21 |
| `--arch-roots` | roots bedded (each root's middle lifted clear of the soil: shallowest station −0.1555 m) | 21 |
| `--orphan-clump` | cushion on its carrier (the cushion on the live twig nearest the crown's centre dropped 0.55 m off it: −0.1063 m) | 22 |
| `--scatter-clusters` | cluster in its cushion (the clusters of cushions inside crown_q 0.70 pushed 0.25 m out along their bearing: −0.1894 m) | 22 |
| `--shed-leaves` | leaf in its cluster (leaves inside crown_q 0.85 slid 0.9 m in toward the crown's centre: −0.8680 m) | 22 |
| `--drop-acorns` | hanging acorns (cups and nuts lowered 60 mm off their pedicels: pedicel in cup −0.0491 m) | 23 |
| `--float-cover` | ground cover (tufts, fallen leaves, fallen acorns and sticks lifted 60 mm: 100 shells not joined, tufts 0.0010–0.0047 m) | 24 |

`--float-branches` keeps each branch's path, so its tip and everything
carried on it stay put; only the tube's first ring moves. `--fat-twigs` also
bursts twigs out of their parents, so the taper (20) is checked before the
seat (17) and names the cause. `--lean-crown` bends only the bole under the
fork and carries the crown over rigidly, so the envelope keeps its size.
The three foliage falsifiers move only interior cushions, clusters or
leaves (and carry what hangs on them), so nothing at the envelope moves;
`--shed-leaves` slides leaves inward because pushed outward the outermost
ones grew the envelope 0.11 m and would have exited 8.

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
blender --background --python broadleaf_oak.py -- --scatter-clusters
blender --background --python broadleaf_oak.py -- --shed-leaves
blender --background --python broadleaf_oak.py -- --drop-acorns
blender --background --python broadleaf_oak.py -- --float-cover
blender --background --python broadleaf_oak.py -- --output oak.png
```

Smoke passes no flags.

The hero keeps the tree at `HERO_YAW_DEG` (0°) and looks at it from the
front left, a little below the crown's middle, so the low limbs reach out
to both sides under the dome, the fork and the crooked limbs show through
the gaps, and the short massive bole, buttresses, roots and mound read
below. Framing measures fill x 0.534, y 0.850. A warm wedge pools on the
floor behind and to the right and washes the wall above it.

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
| 5 | Material count ≠ 9 distinct slots, or a face-count floor missed |
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
| 17 | Branch seat: a branch's base cap not inside its parent, or not 155 branches (`--float-branches`) |
| 18 | Nut seat: a nut out of its depth band in its cup, or not 29 nuts (`--pop-nuts`) |
| 19 | Trunk plumb, crown balance or breast-height diameter out of band (`--lean-crown`) |
| 20 | Taper: a junction's area ratio out of band, a child too wide for its parent, or the fork's area ratio out of band (`--fat-twigs`) |
| 21 | Sealed: the trunk open in a sector round its foot, or a root station not bedded (`--perch-trunk`, `--arch-roots`) |
| 22 | Leaf clumps: a cushion's carrier not inside its core, a cluster not centred in its core, or a leaf's petiole not inside its cluster; or not 295 cores, 2075 clusters and 618 leaves (`--orphan-clump`, `--scatter-clusters`, `--shed-leaves`) |
| 23 | Hanging acorns: a stalk not in its branch, a pedicel not in its stalk or its cup (`--drop-acorns`) |
| 24 | Ground cover: a piece out of its depth band under the soil or not joined to it, or not 108 pieces (`--float-cover`) |
| 25 | Asset-quality floor (render path only; remapped from 11) |
