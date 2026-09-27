# Pine tree

A showcase piece, not an example, and the first in the `nature` category.
It builds a procedural game-ready Scots pine, about 7.2 m tall:

- a trunk lathed in one piece from a five-lobed buttress flare at the
  ground to a leader bud at 7.05 m. It tapers, sways a few centimetres
  and carries ten vertical bark ridges;
- five surface roots, one running out of each flare lobe and diving into
  the ground;
- ten whorls of branches rising in tiers above a bare lower bole, with 4
  to 6 limbs per whorl. Each limb is a crooked, tapered bar that starts
  inside the trunk. Lower limbs run out nearly level and sag; upper limbs
  rise. Their tips turn up;
- side branches, alternating along each limb, and needled shoots on the
  outer part of every limb and side branch. The inner limbs are bare, as
  a pine's are, so the tiers read as branches and not as a stack of cones;
- a needled leader shoot at the top;
- four broken dead stubs and two dead lower branches, each with two dead
  twigs, on the lower bole;
- clusters of two or three cones hanging under limbs in the upper crown.

Every draw comes from `random.Random(SEED)` in `plan_tree()`, before
anything is built: whorl spacing, branch count, yaw, length, rise, droop,
crook and each shoot's tone. No flag draws from the stream, so a falsifier
changes only what it names.

A needled shoot is one closed shell. A thin four-sided core runs along the
shoot, and each quad of it is pulled out into a needle tuft that leans
forward along the shoot. A terminal tuft closes the tip. Tuft lengths
scatter by a closed-form hash. The shoots are flat-shaded, so each tuft
catches light as a facet. The last hand-width of each shoot takes a
lighter, yellower green (a `Tip` face attribute), which is this year's
growth. The first draft used a star-section brush instead, and it read as
holly leaves.

The bark follows Scots pine: thick grey-brown plates on the lower bole,
changing over 2.4 to 4.4 m into thin fox-red flaking bark. The plate noise
is squeezed round the girth and stretched up it, so the fissures run
vertically. Wood (trunk, limbs, roots, dead wood) is smooth-shaded, because
the ridges and taper carry the shape. Every material boundary is a hard
edge. Dead wood is barkless silver-grey, and it has its own slot.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 7.23 m tall, a crown about 4.8 × 5.3 m across at its
lowest whorl, and a 0.266 m trunk diameter at breast height (1.3 m). The
collider is the convex hull of the trunk alone, without ridges or roots,
because players walk under the branches.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 32500–36000 | 34210 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 4 distinct; ≥3900 bark, ≥20500 needle, ≥1400 cone, ≥150 deadwood faces | 4 slots; 4348 / 22800 / 1664 / 172 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (4.775, 5.261, 7.226) m ± 0.01 | (4.7754, 5.2605, 7.2262), zmin 0 |
| Collider tris (trunk hull) | ≤ 60 | 48 |
| Export | written, size > 0, removed after measuring | 3299868 bytes |

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

The coplanar budget caught a real fault on the first run. The two fork
shoots at a limb tip started at the same point in mirrored directions, and
their start fans lay in one plane: 28 pairs. The forks now leave the limb
at staggered stations.

### Branch seat, whorl tiers, plumb and assembly

These are the organic invariants. A tree has no joinery. What makes it
read as a pine is that its branches grow out of the trunk, in whorls at
regular spacing, on a trunk that stands straight under its crown.

The trunk axis is read off the mesh. Every lathe ring shares one height,
so the ring centroids give the axis and the ring radii give the girth.

| Axis | Declared | Measured |
| --- | --- | --- |
| Branch seat: for each of the 50 limbs and 6 seated dead members, the base ring's centre distance from the trunk axis at its height, over the trunk surface radius on the same bearing (raycast from the axis) | 0.25–0.75, and 50 limbs and 6 dead members found | 0.4268–0.4743, 50 / 6 |
| Whorl tiers: limb bases clustered by height (split at 0.18 m) | 10 whorls of 4–6 limbs, each whorl within 0.06 m, gaps between whorls 0.40–0.68 m | 10 whorls `[6, 5, 4, 4, 5, 5, 6, 6, 4, 5]`, spread ≤ 0.0312, gaps 0.4495–0.5742 |
| Trunk plumb: least-squares lean of the ring centroids from 0.8 m to 6.0 m | ≤ 1.0° | 0.355° |
| Crown balance: needle-area centroid off the trunk axis at 0.5 m, horizontally (the tip-over check) | ≤ 0.15 m | 0.0191 m (centroid at 3.45 m) |
| Diameter at breast height (ring nearest 1.3 m) | 0.266 m ± 0.020 | 0.2665 |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (671 shells) |

A shell counts as a limb when it comes within 0.08 m of the trunk surface.
Side branches start on their limb, out in the crown. The seat audit then
says whether each limb's base is actually inside the bark. Counting limbs
by "starts inside" instead would let a floating limb drop out of the count
and hide from the seat check.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. The envelope was unchanged in every run:
`--lean-crown` moves the X extent 0.3 mm against a 10 mm tolerance.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-branches` | branch seat (every limb's tube starts at 1.2 × the trunk radius, outside the bark: worst 1.2675) | 17 |
| `--lean-crown` | trunk plumb (axis bent `x += 0.0075 (z − 1)²`: lean 1.711°) | 19 |
| `--bunch-whorls` | whorl tier spacing (whorl 6 lifted 0.30 m: gaps 0.2258–0.7970 m) | 20 |
| `--drop-cones` | one connected assembly (cones lowered 50 mm off their limbs: 15 components) | 21 |

`--float-branches` keeps each limb's path, so the tip and everything hung
on it stay put. Only the tube's first ring moves out of the bark.
`--lean-crown` bends the whole trunk above 1 m and carries every limb with
it. The crown balance moves too, to 0.0711 m, but stays inside its band,
so the plumb budget is what fails. `--bunch-whorls` lifts one mid-crown
whorl, whose limbs are not the extremes of the envelope. `--drop-cones`
also leaves the rest of the tree whole: 14 cone clusters float free and
the tree is the 15th component. The other clusters still touch a needled
shoot below them, so the check counts components rather than cones.

## Run

```bash
blender --background --python pine_tree.py --
blender --background --python pine_tree.py -- --skip-decimate
blender --background --python pine_tree.py -- --stray-vert
blender --background --python pine_tree.py -- --lift-z
blender --background --python pine_tree.py -- --float-branches
blender --background --python pine_tree.py -- --lean-crown
blender --background --python pine_tree.py -- --bunch-whorls
blender --background --python pine_tree.py -- --drop-cones
blender --background --python pine_tree.py -- --output pine.png
```

Smoke passes no flags.

The hero turns the tree `HERO_YAW_DEG` (80°) about Z only. From there the
lowest whorls spread widest to both sides, and the upper tiers and the red
upper bole read through the gaps. The camera sits a little below the
crown's middle, so the skirt of lower limbs reads against the wall. A warm
wedge pools on the floor behind and to the right and washes the wall above it.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`17` and
`19` are the hygiene, joint-fit and plumb family. `18` is not used: no
budget here is a wrapper's seat. `20` and `21` are file-local. `22` is the
asset-quality floor on the render path: `check_asset_quality` returns 11,
which this piece already spends on the collider ceiling, so the call site
remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or no single trunk shell |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 4 distinct slots, or a face-count floor missed |
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
| 17 | Branch seat: a limb or dead member's base outside its band in the trunk, or not 50 limbs and 6 dead members (`--float-branches`) |
| 19 | Trunk plumb, crown balance or breast-height diameter out of band (`--lean-crown`) |
| 20 | Whorl tiers: not 10 whorls of 4–6 limbs, a whorl spread too wide, or a gap between whorls out of band (`--bunch-whorls`) |
| 21 | Tree splits into more than one connected component (`--drop-cones`) |
| 22 | Asset-quality floor (render path only; remapped from 11) |
