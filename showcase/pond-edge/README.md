# Pond edge

A showcase piece, not an example, and the fourth in the `nature` category.
It builds a procedural, game-ready pond margin on a raised soil disc:

- a soil disc 3.2 × 2.6 m whose rim rolls down to the floor. The bank
  stands higher at the back than at the front, and slopes from a turfed
  top through a band of wet mud into a shallow basin. The disc's cut edge
  shows its soil horizons: dark humus under the turf, brown subsoil, pale
  clay with stones at the foot;
- the water: its own mesh, a sheet at a declared level of 0.115 m, rippled
  in low rings that spread from the cattail clump, from each cattail stem,
  from the branch where it goes in and from two of the stones. The rings
  die out round everything floating. The sheet's rim does not stop at the
  shoreline: it runs 50 mm on under the bank, so no edge of the water ever
  shows. The water is tinted by its depth over the mud, olive-brown in the
  shallows and near black in the middle, with a faint film drifted into
  the edges;
- a clump of cattails standing in the shallows: 34 strap leaves arching
  out of one base, diamond in section, with pale sheathing bases and
  withered tips, and five stems leaning out of the stand. Each stem is
  threaded through a brown velvet seed head, and runs on above it as the
  bare spike;
- nine rush tufts on the bank and sixteen short turf tufts, every blade a
  V-section strap that leaves the ground leaning its own way;
- five lily pads floating on the water, each notched to its centre, with
  radial veins, a bronze rim and a maroon underside; two water lilies,
  each four sepals and three rings of petals round a yellow stamen crown;
  three fallen leaves floating;
- five smooth stones on the shoreline, dark where they are wet, with a
  green line at the water's edge; a dead branch running from the bank into
  the water, its bark furrowed and its ends broken; pebbles and fallen
  leaves on the bank.

Every draw comes from `random.Random(SEED)` in `plan_pond()`, before
anything is built. Which scatter candidates are used is decided once
against the default build (`Layout`), which also refuses a layout whose
floating parts crowd each other or the shore. No flag draws from the
stream or changes the layout, so a falsifier changes only what it names.

Nine materials, one per substance: water, bank mud, reed (cattail leaves
and stems, rushes), seed head (with the bare spike), lily pad, lily
flower, stone (stones and pebbles), wood (the branch) and leaf litter.
Point attributes carry what the shaders need: `Depth` (water over the
mud), `Wet` (the mud band, the wet part of each stone and of the branch),
`Turf`, `Skirt`, `Along` (the run along a leaf, blade, stem or petal) and
`PadAng` / `PadR` (the pad veins and rim). A `Tone` face attribute is
seeded per part. Everything is smooth-shaded; every material boundary and
every fold sharper than 60° is a hard edge.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a disc 3.20 × 2.63 m with its bank 0.17–0.25 m high, the
tallest cattail spike 1.51 m off the floor. The outer AABB is 3.204 ×
2.634 × 1.507 m, read off the vertices. The soil sets X and Y, a cattail
spike the top; the soil's underside is the ground. The collider is the
convex hull of the soil disc alone, coarse: the water is a trigger volume,
and players walk through reeds.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 36900–38300 | 37602 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 9 distinct; ≥5240 water, ≥5050 soil, ≥7340 reed, ≥1260 seed head, ≥1250 pad, ≥1290 flower, ≥1840 stone, ≥210 wood, ≥360 litter faces | 9 slots; 5824 / 5614 / 8162 / 1400 / 1390 / 1440 / 2046 / 234 / 400 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (3.2040, 2.6342, 1.5071) m ± 0.01 | (3.2040, 2.6342, 1.5071), zmin 0 |
| Collider tris (soil hull) | ≤ 120 | 96 |
| Export | written, size > 0, removed after measuring | 3140712 / 3140712 / 3140704 bytes (4.5.11 / 5.1.2 / 5.2.1) |

No falsifier changes the triangle count or the envelope: every falsifier
run measured 37602 tris and the default's outer AABB to the tenth of a
millimetre.

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

The coplanar budget caught four kinds of fault on the way. Petals and
sepals rooted on one point of the flower's axis put planes through that
axis, and a mirror-symmetric petal turned about it lands a face on a
neighbour's plane: seven pairs. Every petal now roots at its own radius
and height, and its two halves differ by a few percent. Two cattail stems
built with the same starting ring frame laid facets on shared planes
where they ran parallel; each tube now starts its facets at its own angle.
Two rush blades rooted at one height had flat root caps on one plane, and
a fallen leaf laid along the soil normal lay on the plane of the face
under it; blades now leave the ground already leaning their own way, and
bank leaves are tipped a few degrees off the ground. A V-section blade
pair with opposite yaws and equal lean was parallel by chance; a per-blade
roll broke it.

### Rooted reeds, floating pads, the water, threaded heads, the enclosed water and the cover

These are the organic invariants. A pond margin has no joinery. What makes
it read as a pond is that its reeds grow out of the mud rather than stand
on it, that its pads float on the water rather than sink or hover, that
the water lies level with a living surface, that the seed heads grow on
their stems, that the bank holds the water on every side, and that
nothing on the bank floats.

| Axis | Declared | Measured |
| --- | --- | --- |
| Rooted reeds: every cattail leaf and stem, its lowest vertex under the soil straight above it (a ray down onto the soil shell alone) | 39 of 39, each 0.020–0.070 m | 39; 0.0397–0.0445 m |
| Floating pads: for each pad, its mean height over the water surface under its centroid (a ray down onto the water shell alone), how far its lowest vertex draws under that surface, and the tilt of the plane fitted through it | 5 pads; freeboard −0.0005–0.0040 m, draft 0.0005–0.0040 m, tilt ≤ 3° | 5; freeboard 0.00149 m, draft 0.00150 m, tilt ≤ 0.011° |
| Water: the median height of the water's top sheet, and its largest excursion from that median | level 0.115 ± 0.0015 m; ripple 0.0015–0.0090 m | 0.11500 m; 0.00439 m |
| Threaded heads: each seed head's axis from its own vertices (principal axis); the stem whose vertices inside the head's middle run lie closest to it, and their centroid's distance off the axis; how far that stem runs on above the head | 5 heads on 5 distinct stems; off-axis ≤ 0.002 m; spike ≥ 0.06 m | 5 on 5; ≤ 0.00008 m; 0.093–0.136 m |
| Enclosed water: the bank over every rim vertex and rim-edge midpoint of the water's top sheet (a ray down onto the soil shell alone) | ≥ 0.008 m everywhere | 0.01366 m (208 rim edges) |
| Cover joined: every shell unioned with the soil through BVH overlaps (floating parts through the water) | every shell joined | 598 shells; 0 loose |

The shoreline is found per bearing by bisection on the analytic bank, and
the water's rim is laid 50 mm past it; the enclosure budget reads the bank
back off the shipped soil mesh by raycast, so it sees the soil that was
built. Each leaf and stem root is set 40 mm (staggered) under the soil
mesh as built. The pads sit a 3 mm slab with its underside 1.5 mm under
the water, and the ripples die out round each pad, so a pad rests on calm
water.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. None moves the envelope: every run measured the
same outer AABB and triangle count as the default, and every other
piece-specific budget stayed green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-reeds` | rooted reeds (every leaf and stem base raised 70 mm, fading to 0 at the tip: lowest vertex −0.0303 to −0.0255 m, above the mud) | 17 |
| `--sink-pad` | floating pads (the first pad pushed 4 mm under, its rim still awash: freeboard −0.00251 m, draft 0.00550 m) | 18 |
| `--flat-water` | water level and ripple band (the sheet laid flat: ripple 0.00000 m) | 19 |
| `--slip-heads` | threaded heads (every head slid 8 mm off its stem's axis, still pierced by it: 0.0079–0.0080 m off) | 20 |
| `--short-water` | enclosed water (the rim stopped 60 mm short of the shoreline: the bank 0.03736 m below it) | 21 |
| `--float-cover` | cover joined (every rush blade, pebble and bank leaf lifted 30 mm: 108 of 598 shells loose) | 22 |

`--float-reeds` holds each tip where it was, so the envelope, set by a
spike tip, does not move; the heads stay threaded (1.0 mm off-axis). The
stems and leaves still cross the water, so the cover budget still joins
them. `--sink-pad` pushes the pad 4 mm, not more: pushed 12 mm it drowned
whole and came loose from the water, which the cover budget saw too.
`--slip-heads` slides 8 mm for the same reason: at 25 mm the heads left
their stems and came loose. `--flat-water` changes no draw, so the pads
float exactly as before. `--short-water` changes only the water; the
ripples, the pads and the cover are unchanged. `--stray-vert` and
`--lift-z` necessarily move the loose-shell count and the water's
absolute level with them; they exit on their own, earlier codes.

## Run

```bash
blender --background --python pond_edge.py --
blender --background --python pond_edge.py -- --skip-decimate
blender --background --python pond_edge.py -- --stray-vert
blender --background --python pond_edge.py -- --lift-z
blender --background --python pond_edge.py -- --float-reeds
blender --background --python pond_edge.py -- --sink-pad
blender --background --python pond_edge.py -- --flat-water
blender --background --python pond_edge.py -- --slip-heads
blender --background --python pond_edge.py -- --short-water
blender --background --python pond_edge.py -- --float-cover
blender --background --python pond_edge.py -- --output pond.png
```

Smoke passes no flags.

The hero keeps the piece unturned (`HERO_YAW_DEG` 0°) and looks in from
the south-south-west, a little above the bank, so the water shows as a
dark sheet between the near bank and the far one. EEVEE's traced
reflections put the cattails and the back wall into the water. The
cattails stand at the back left against the wall, the rushes along the
far bank, the branch on the right. The fill is 0.688 × 0.872.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene, grounding, rooting, floating and level family. `20`–`22` are
file-local. `23` is the asset-quality floor on the render path:
`check_asset_quality` returns 11, which this piece already spends on the
collider ceiling, so the call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or no soil or water shell |
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
| 16 | Not grounded: bounding box `zmin` off 0 (`--lift-z`) |
| 17 | Rooted reeds: not 39 leaves and stems, or one's lowest vertex outside 0.020–0.070 m under the mud (`--float-reeds`) |
| 18 | Floating pads: not 5 pads, or a pad's freeboard outside −0.0005–0.0040 m, its draft outside 0.0005–0.0040 m, or its tilt above 3° (`--sink-pad`) |
| 19 | Water: its level more than 0.0015 m off 0.115 m, or its ripple outside 0.0015–0.0090 m (`--flat-water`) |
| 20 | Threaded heads: not 5 heads on 5 stems, a head more than 0.002 m off its stem's axis, or a spike under 0.06 m (`--slip-heads`) |
| 21 | Enclosed water: the bank less than 0.008 m over the water's rim anywhere (`--short-water`) |
| 22 | Cover: a shell not joined to the soil (`--float-cover`) |
| 23 | Asset-quality floor (render path only; remapped from 11) |
