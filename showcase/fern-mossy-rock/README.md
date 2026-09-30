# Fern and mossy rock

A showcase piece, not an example, and the ninth in the `nature` category.
It builds a procedural game-ready shaded woodland corner, about 2.29 × 1.90 m
across and 1.11 m high, on a soil bank that rises toward the back:

- a gritstone boulder, about 1.1 × 1.0 m in plan and standing about 0.75 m
  out of the bank, cut by twelve deep cleavage planes into broad flat
  fracture faces that meet at crisp arrises weathered only 16–20 mm round,
  with two stepped ledges broken out of its shoulders (the region beyond
  both of two planes removed) and seven small chipped facets, and split down
  its front and across its top by a crack: a V 124 mm wide at the surface
  and 220 mm deep that closes low on the flanks. The fracture faces keep a
  tenth of the ellipsoid's waves, so they read flat but not machined. It is
  sunk into the bank until, in every one of eight sectors round it, its
  most-buried flank vertex is 40 mm under the soil;
- a moss cushion over the larger block that drapes down its shaded front,
  three smaller cushions and nine satellite tufts round it. Each is a
  conforming shell, a lens laid on the stone as built, with a lobed outline
  of broad lobes and deep inlets. Its height over the stone, along the
  stone's own normal, is full in the middle and feathers to nothing over
  the outer 42% of its radius, deeper (up to 1.8×) in the stone's hollows,
  measured against the stone round each point; the last ring before the rim
  stands at most 7 mm proud, and the rim is tucked into the stone. Two bare
  patches in the main cushion dip under the stone so it shows through. The
  outline stops short of the soil and runs, on a ragged line, over the
  crack's lip and a little way down into it;
- the stone's shading: warm buff to grey mottling, a weathered grey rind in
  broad patches, quartz grit, pitting, rain streaks down the steep faces
  only, algae in the hollows, sage and orange lichen and dark crust spots on
  the upper faces, a green stain round every cushion (a `MossD` point
  attribute, each stone vertex's distance to the nearest moss), a dark damp
  band where the soil wicks up the foot (`SoilH`, height over the bank), and
  a black throat to the crack;
- a male fern (*Dryopteris filix-mas*) beside the boulder's front-right foot: a
  scaly rootstock bedded in the soil with seven old stipe bases round it,
  and a shuttlecock crown of eleven bipinnate fronds, 0.96–1.14 m long. Each
  frond is one tapering tube, a scaly brown stipe for its lower fifth and a
  green rachis above, rising steeply and arching out; on it fifteen pinnae a
  side alternate, longest a third of the way up the blade and tapering to
  the tip, each cut almost to its costa into up to five pinnules a side,
  themselves alternate and shortening toward the pinna's tip. Young fronds
  stand upright in the middle, old ones spread and droop outside. Three
  fiddleheads unroll at the crown's heart, each a stipe ending in a
  logarithmic spiral of 1.65 turns, beaded with the coiled pinnae;
- a smaller fern of four fronds, 0.44–0.56 m, growing out of the crack from
  a rootstock wedged down the cleft, in view of the hero camera;
- at the foot: 48 fallen beech leaves drifted against the boulder, 14
  pebbles, a fallen twig with a side shoot, and seven clumps of wood sorrel
  (25 trifoliate leaves on thin petioles).

Every seeded draw comes from `random.Random(SEED)` in `plan_scene()`, before
anything is built: the boulder's waves and chips, each frond's bearing, age,
length, arch and twist, each pinna's length, angle and rise, the
fiddleheads, the stipe bases and the ground cover. Per-pinnule and per-leaf
variety comes from a closed-form hash of indices. No flag draws from the
stream, so a falsifier changes only what it names.

A frond that would run into the boulder or the bank as planned is stood up
steeper and arched less, three degrees at a time, until it and its pinnae
clear both. That is why the fronds on the boulder's side are the upright
ones.

The pinnules are geometry. A pinna is one closed, thin shell: a costa from
the pinna's base (inside the rachis) to its apex, curving toward the
frond's tip, and on each side of it oblong lobes cut to within a few
millimetres of it, shared by a top and a bottom surface each fanned from
its own costa vertices, so every rim edge has one face above and one below.
Leaves this dense are a coplanar hazard: along one rachis the pinnae are
translated copies in one blade plane, and on the first build 216 pairs of
their faces shared a plane (211 of them within one frond). Each pinna is
therefore flat (its faces within a few degrees of its own plane, the costa
standing 0.12% of the pinna's length proud of the rim), its neighbours are
turned about their own axes in a three-step cycle (±0.20 rad), and the plan
turns each one further, in 0.04 rad steps, until its plane is 8° off the
plane of every pinna whose faces can come within the coplanar range of its
own. All 434 clear. The sorrel leaflets, which share a point at the top of
their petiole, are turned apart the same way (14°).

Everything is smooth-shaded, with every material boundary and every fold
sharper than its crease (38° on the stone, 55° on leaves, 62° elsewhere) a hard edge, so a
pinna's rim stays crisp while a stipe stays round. A
`Zone` face attribute marks a leaf's underside (paler, with rusty sori
beside the costa), a moss face's height in its hummocks, and the fresh
faces of the crack; a `Crack` point attribute darkens the cleft. The frond
and sorrel materials mix in a translucent lobe, so a shaded underside reads
green, not black. Ten materials: stone (the boulder and pebbles), moss,
frond, stipe, crozier, rootstock, soil, beech litter, twig, wood sorrel.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

The collider is the convex hull of the boulder alone, sampled coarsely,
because players walk through ferns. It is built from points only.

The piece is 86,740 triangles, 58% of them pinnae; the boulder's lattice
went from 28 to 36 cells a side (16,224 stone faces) so its arrises are
resolved at a 16–20 mm weathering radius instead of hidden in 40–110 mm
bevels. A fern is its pinnae, and the whole point of this one
is pinnule detail that holds up at hero size.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 86300–87200 | 86740 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 10 distinct; face floors stone ≥15600, moss ≥4360, frond ≥48400, stipe ≥1480, crozier ≥750, rootstock ≥290, soil ≥2350, litter ≥1660, twig ≥64, sorrel ≥2060 | 10 slots; 16224 / 4548 / 50428 / 1545 / 780 / 303 / 2446 / 1728 / 66 / 2150 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.2872, 1.9008, 1.1111) m ± 0.01 | (2.2872, 1.9008, 1.1111), zmin 0 |
| Collider tris (boulder hull) | ≤ 200 | 130 |
| Export | written, size > 0, removed after measuring | 10731436 bytes |

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. The plan is seeded and nothing else is random; two
default runs print identical measurements, and 4.5.11 and 5.1.2 print the
same measurements as 5.2.1 (the glTF differs by 12 bytes).

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

The soil disc's flat underside is the only geometry at Z = 0. The
boulder's buried underside is cut flat 40 mm above it, inside the soil; a
first draft sank the boulder 0.28 m through the bottom of the disc. The
coplanar budget caught more than the pinnae on the way: a beech leaf lying
in the plane of a soil face (every leaf is now rolled 0.20–0.32 rad about
its midrib, one edge bedded and the other lifted), sorrel leaflets of
neighbouring leaves in one plane, a rachis face in the plane of a pinna and
of a fiddlehead, and, under a first `--sunny-moss` that turned every
cushion rigidly round the boulder, two cushions overlapping, so it exited 15
instead of 21. It now moves the main cushion alone.

### Organic invariants

A fern and a boulder have no joinery. What makes this read as a woodland
corner is that the fern grows out of its rootstock and the rootstock out of
the soil, that the moss lies on the stone and grows where the stone is
shaded, that the boulder is sunk into the bank rather than set on it, that
the small fern grows in the crack, that a fern frond is built the way ferns
are (alternate pinnae, longest low on the blade, a pointed tip) and unrolls
as a spiral, and that the leaves and stones at its foot lie in the soil.
Each face carries `Part`, `Ident` and `Parent` tags and each vertex a `Ring`
and a `Tip`, so a shell can be named, a tube's rings found and a pinna's
base and apex told apart; every measurement is then made on the shell's
geometry.

| Axis | Declared | Measured |
| --- | --- | --- |
| Rooted: every stipe, fiddlehead and old stipe base's shallowest base-cap vertex inside its rootstock (ray-parity signed depth) | ≥ 0.004 m, 25 stalks | ≥ 0.0085 |
| Rooted: every pinna's base (its `Tip` 0 vertex) inside the rachis tagged as its `Parent` | ≥ 0.0004 m, 434 pinnae on 15 fronds | ≥ 0.0013 |
| Rooted: the crown's rootstock sealed in the soil: in each of 8 sectors round it, its most-buried flank vertex (≥ 0.90 of the sector's reach) under the soil straight above it | ≥ 0.010 m in 8 of 8 | worst 0.0320, 8 of 8 |
| Moss seat: every moss top vertex inside the rim (bare-patch vertices excepted, see below), its height over the stone along the normal of the stone's nearest face | 0.001–0.055 m, 13 cushions and tufts | 0.0016–0.0463 |
| Moss seat: every rim, underside and bare-patch vertex inside the stone, by the same measure | ≥ 0.001 m | ≥ 0.0020 |
| Moss rim feathers: every cushion's last ring before its tucked rim, its height over the stone by the same measure | ≤ 0.010 m | ≤ 0.0069 |
| Boulder sealed: in each of 8 sectors round it, its most-buried flank vertex under the soil straight above it | ≥ 0.020 m in 8 of 8 | worst 0.0399, 8 of 8 |
| Moss facing: area share of cushion top faces whose stone (the normal of its nearest face) faces up (z ≥ 0.55) or into the shade (−y ≥ 0.45) | ≥ 0.85 | 0.8918 |
| Cleaved: of the turning between neighbouring stone faces more than 20 mm over the soil (dihedral angle × edge length, the crack left out), the share taken in arrises sharper than 20° | ≥ 0.42 | 0.4856 (turning 15.24) |
| Crack fern: its rootstock's deepest vertex inside the stone (wedged against the crack walls); its centre outside the stone with stone within reach on two opposite sides of 12 horizontal rays | bite ≥ 0.004 m, walls ≤ 0.060 m | bite 0.0159, in the cleft, walls 0.0126 |
| Pinnae alternate: per frond, pinnae sorted by station along the rachis (base projected on the rachis's ring centroids) lie on alternate sides, and each gap to the next over the same-side spacing | every pair alternate, gaps 0.25–0.75, 15 fronds | all alternate, 0.442–0.575 |
| Pinnae taper: per frond, where the longest pinna stands on the blade; the pinnae in its top fifth over the longest; the two lowest over the longest | peak 0.10–0.60, tip ≤ 0.40, base ≤ 0.88 | peak 0.223–0.468, tip ≤ 0.326, base ≤ 0.647 |
| Fiddleheads: per crozier, the centreline from its ring centroids; the coil's turning from where it first bends 30° to its tip, and the mean curvature of its inner third over its outer third, by arc length | ≥ 1.20 turns, ratio ≥ 1.80, 3 fiddleheads | 1.697–1.722 turns, ratio ≥ 2.901 |
| Ground cover: most-buried vertex under the soil straight above it, per piece | leaves, pebbles, twig 0.003–0.030 m, sorrel petioles 0.015–0.060 m; 89 pieces | 0.0040, sorrel 0.0302–0.0308 |
| Ground cover joined to the soil (union of shells whose BVH trees overlap, the sorrel leaflets included) | every cover shell in the soil's component | 164 of 164 |

The boulder is bedded on the lattice it ships with, sector by sector: the
bank rises 190 mm per metre, so a boulder bedded against the soil height at
its centre alone is buried uphill and open downhill. The rootstock is
audited the same way. The moss's thickness is measured on the shipped stone,
not the field that shaped it: the seat audit found a draft cushion whose
spokes aimed at the crack had been floored at a quarter of their length,
which put top vertices down the V and 27 mm inside the far block's wall.
The outline now shrinks every spoke until each ring on it clears the lip.

The first release of this piece shipped a boulder that read as a smooth grey
lump (ten cuts at 0.64–0.72 of the ellipsoid through 35–110 mm bevels, the
waves at 40% on every face) under a moss slab whose front edge was a hard
vertical wall: its height held near full to the last ring before the rim, so
it dropped 20–30 mm in one ring spacing. Both are now budgets. The rim
budget reads the height of each cushion's last ring before the rim; a bare
patch's vertices are tagged in the `Ring` layer at build time and are
measured with the rim and underside, inside the stone, not with the top.
The cleavage budget needs no tags: it is the share of the stone's turning
concentrated in sharp arrises. A count of flat regions did not separate the
two recipes (the old lump, whose waves are long and low, had as many 0.03 m²
planar regions as the new stone); where the turning happens did (0.49
against 0.29). Two tufts that landed on the same flat fracture face as a
cushion's rim put two faces in one plane; each shell is now tucked to its
own depth (5 mm plus 0.5 mm per shell).

## Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
4.5.11 and exited its declared code. The envelope and the triangle count
were unchanged in every run.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--smooth-rock` | cleaved (the shipped recipe: shallow cuts through broad bevels, full waves on the faces, the ellipsoid drawn 0.90 smaller to keep its size: 0.2892 of the turning in sharp arrises) | 27 |
| `--float-fronds` | rooted (every frond's stipe starts 60 mm out along its path, which is otherwise unchanged: shallowest base −0.0503 m) | 17 |
| `--lift-crown` | rooted (the rootstock alone raised 50 mm: worst sector −0.0180 m, 1 of 8) | 17 |
| `--float-moss` | moss seat (every cushion lifted 40 mm along the stone's normal: top up to 0.0858 m, rim −0.0380 m) | 18 |
| `--slab-moss` | moss rim feathers (the shipped profile, near full height to the last ring: 0.0189 m) | 28 |
| `--perch-rock` | boulder sealed (bedded against the soil height at its centre alone: worst sector −0.0321 m, 7 of 8) | 20 |
| `--sunny-moss` | moss facing (the main cushion laid on the boulder's sunny back face: 0.5986) | 21 |
| `--perch-crack-fern` | crack fern (slid 100 mm sideways out of the cleft into the wall: centre not in the cleft, walls 0.1576 m) | 22 |
| `--flat-taper` | pinnae taper (one frond's pinnae all 0.80 of its longest: tip 0.996) | 23 |
| `--opposite-pinnae` | pinnae alternate (one frond's lower-side pinnae moved level with the upper side's: gaps 0.0013–0.9987) | 23 |
| `--open-crozier` | fiddleheads (each coil a circular arc of the spiral's length: 0.932 turns, ratio 1.128) | 24 |
| `--float-cover` | ground cover (leaves, pebbles, twig and sorrel lifted 50 mm: −0.046 m, 164 shells loose) | 25 |

The crack fern is the top of the envelope, so `--float-moss` and
`--perch-rock` (which lifts the boulder with its moss) cannot move the box;
the soil disc sets the left and back, frond tips the right and front, so
`--smooth-rock` (a different stone, re-bedded, cutting its own flat foot)
leaves it too. `--slab-moss` keeps every cushion's outline, thickness and
windows' places and changes only the height profile. `--flat-taper` and
`--opposite-pinnae` reshape only the crown frond held furthest inside the
envelope. `--perch-crack-fern` moves the small fern level, never up.
`--lift-crown` moves the rootstock alone; the stalks stay inside it.

## Run

```bash
blender --background --python fern_mossy_rock.py --
blender --background --python fern_mossy_rock.py -- --skip-decimate
blender --background --python fern_mossy_rock.py -- --stray-vert
blender --background --python fern_mossy_rock.py -- --lift-z
blender --background --python fern_mossy_rock.py -- --smooth-rock
blender --background --python fern_mossy_rock.py -- --float-fronds
blender --background --python fern_mossy_rock.py -- --lift-crown
blender --background --python fern_mossy_rock.py -- --float-moss
blender --background --python fern_mossy_rock.py -- --slab-moss
blender --background --python fern_mossy_rock.py -- --perch-rock
blender --background --python fern_mossy_rock.py -- --sunny-moss
blender --background --python fern_mossy_rock.py -- --perch-crack-fern
blender --background --python fern_mossy_rock.py -- --flat-taper
blender --background --python fern_mossy_rock.py -- --opposite-pinnae
blender --background --python fern_mossy_rock.py -- --open-crozier
blender --background --python fern_mossy_rock.py -- --float-cover
blender --background --python fern_mossy_rock.py -- --output fern.png
```

Smoke passes no flags.

The hero turns the piece −50° about Z only (`HERO_YAW_DEG`), so the
boulder's draped front and the crack, with the small fern growing out of it,
face the camera left of the main fern, and looks at it from the front left,
a little above the boulder's crown, from 3.55 m. Framing measures fill x
0.822, y 0.878. A warm wedge pools on the floor and wall behind the right of
the bank.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`18` are the
hygiene, grounded, joint-fit (rooted) and seat-conformance (moss seat)
family; `19` is not used, since nothing here is plumb or dressed to a
stated size. `20`–`25`, `27` and `28` are file-local. `26` is the asset-quality floor on
the render path: `check_asset_quality` returns 11, which this piece already
spends on the collider ceiling, so the call site remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, no UV layer, or not one boulder, soil and rootstock shell |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 10 distinct slots, or a face-count floor missed |
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
| 17 | Rooted: a stalk not in its rootstock, a pinna not in its rachis, or the rootstock not sealed in the soil (`--float-fronds`, `--lift-crown`) |
| 18 | Moss seat: a cushion's top out of its band over the stone, or its rim, underside or bare patches not inside it (`--float-moss`) |
| 20 | Boulder sealed: a sector round it not bedded in the soil (`--perch-rock`) |
| 21 | Moss facing: too little of the moss on stone that faces up or into the shade (`--sunny-moss`) |
| 22 | Crack fern: its rootstock not wedged in the cleft (`--perch-crack-fern`) |
| 23 | Pinnae: a frond's pinnae not alternate, or not tapering (`--flat-taper`, `--opposite-pinnae`) |
| 24 | Fiddleheads: a coil short of its turns, or its curvature not rising toward the centre (`--open-crozier`) |
| 25 | Ground cover: a piece out of its depth band under the soil or not joined to it, or not 89 pieces (`--float-cover`) |
| 26 | Asset-quality floor (render path only; remapped from 11) |
| 27 | Cleaved: too little of the stone's turning in sharp arrises — a rounded lump (`--smooth-rock`) |
| 28 | Moss rim: a cushion's last ring before its rim stands too high over the stone — a slab edge (`--slab-moss`) |
