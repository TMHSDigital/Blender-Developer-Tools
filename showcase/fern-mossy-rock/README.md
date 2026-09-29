# Fern and mossy rock

A showcase piece, not an example, and the ninth in the `nature` category.
It builds a procedural game-ready shaded woodland corner, about 2.29 × 2.22 m
across and 0.86 m high, on a soil bank that rises toward the back:

- a large gritstone boulder, 1.2 × 1.0 m in plan and standing about 0.5 m
  out of the bank at its centre, cleaved by ten planes into
  broken faces whose meeting edges are weathered to bevels, with seven small
  chipped facets, and split across its top by a crack: a V 124 mm wide at
  the surface and 220 mm deep that closes on the low flanks, so the rock is
  one block with a cleft, not two. It is sunk into the bank until, in every
  one of eight sectors round it, its most-buried flank vertex is 40 mm under
  the soil; uphill it is buried to its shoulder;
- a thick moss cushion over the larger block's crown that drapes down its
  shaded front, and three smaller cushions (on the far block's crown and low
  on the front flank). Each cushion is a conforming shell, a lens laid on
  the stone as built: hummocks up to 58 mm deep over the stone along the
  stone's own normal, a scalloped rim tucked 5 mm into it, and an underside
  inside it. Its outline stops short of the soil and, along a ragged line,
  of the crack's lip;
- a male fern (*Dryopteris filix-mas*) at the boulder's downhill foot: a
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
  a rootstock wedged down the cleft;
- at the foot: 56 fallen beech leaves drifted against the boulder, 16
  pebbles, a fallen twig with a side shoot, and eight clumps of wood sorrel
  (28 trifoliate leaves on thin petioles).

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
cleavage edge and a pinna's rim stay crisp while a stipe stays round. A
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

The piece is heavier than `broadleaf-oak` (77,176 against 68,350 triangles):
65% of it is pinnae. A fern is its pinnae, and the whole point of this one
is pinnule detail that holds up at hero size.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 76800–77600 | 77176 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 10 distinct; face floors stone ≥9800, moss ≥2200, frond ≥48400, stipe ≥1480, crozier ≥750, rootstock ≥290, soil ≥2350, litter ≥1940, twig ≥64, sorrel ≥2230 | 10 slots; 10176 / 2288 / 50428 / 1545 / 780 / 303 / 2446 / 2016 / 66 / 2408 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.2896, 2.2209, 0.8601) m ± 0.01 | (2.2896, 2.2209, 0.8601), zmin 0 |
| Collider tris (boulder hull) | ≤ 200 | 128 |
| Export | written, size > 0, removed after measuring | 9670400 bytes |

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. The plan is seeded and nothing else is random; two
default runs print identical measurements, and 4.5.11 and 5.1.2 print the
same measurements as 5.2.1 (the glTF differs by 8 bytes).

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
| Rooted: the crown's rootstock sealed in the soil: in each of 8 sectors round it, its most-buried flank vertex (≥ 0.90 of the sector's reach) under the soil straight above it | ≥ 0.010 m in 8 of 8 | worst 0.0322, 8 of 8 |
| Moss seat: every moss top vertex inside the rim, its height over the stone along the normal of the stone's nearest face | 0.006–0.080 m, 4 cushions | 0.0111–0.0568 |
| Moss seat: every rim and underside vertex inside the stone, by the same measure | ≥ 0.001 m | ≥ 0.0040 |
| Boulder sealed: in each of 8 sectors round it, its most-buried flank vertex under the soil straight above it | ≥ 0.020 m in 8 of 8 | worst 0.0399, 8 of 8 |
| Moss facing: area share of cushion top faces whose stone (the normal of its nearest face) faces up (z ≥ 0.55) or into the shade (−y ≥ 0.45) | ≥ 0.85 | 0.8982 |
| Crack fern: its rootstock's deepest vertex inside the stone (wedged against the crack walls); its centre outside the stone with stone within reach on two opposite sides of 12 horizontal rays | bite ≥ 0.004 m, walls ≤ 0.060 m | bite 0.0192, in the cleft, walls 0.0100 |
| Pinnae alternate: per frond, pinnae sorted by station along the rachis (base projected on the rachis's ring centroids) lie on alternate sides, and each gap to the next over the same-side spacing | every pair alternate, gaps 0.25–0.75, 15 fronds | all alternate, 0.442–0.575 |
| Pinnae taper: per frond, where the longest pinna stands on the blade; the pinnae in its top fifth over the longest; the two lowest over the longest | peak 0.10–0.60, tip ≤ 0.40, base ≤ 0.88 | peak 0.223–0.468, tip ≤ 0.326, base ≤ 0.647 |
| Fiddleheads: per crozier, the centreline from its ring centroids; the coil's turning from where it first bends 30° to its tip, and the mean curvature of its inner third over its outer third, by arc length | ≥ 1.20 turns, ratio ≥ 1.80, 3 fiddleheads | 1.697–1.722 turns, ratio ≥ 2.901 |
| Ground cover: most-buried vertex under the soil straight above it, per piece | leaves, pebbles, twig 0.003–0.030 m, sorrel petioles 0.015–0.060 m; 102 pieces | 0.0040, sorrel 0.0301–0.0308 |
| Ground cover joined to the soil (union of shells whose BVH trees overlap, the sorrel leaflets included) | every cover shell in the soil's component | 186 of 186 |

The boulder is bedded on the lattice it ships with, sector by sector: the
bank rises 190 mm per metre, so a boulder bedded against the soil height at
its centre alone is buried uphill and open downhill. The rootstock is
audited the same way. The moss's thickness is measured on the shipped stone,
not the field that shaped it: the seat audit found a draft cushion whose
spokes aimed at the crack had been floored at a quarter of their length,
which put top vertices down the V and 27 mm inside the far block's wall.
The outline now shrinks every spoke until each ring on it clears the lip.

## Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
4.5.11 and exited its declared code. The envelope and the triangle count
were unchanged in every run.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-fronds` | rooted (every frond's stipe starts 60 mm out along its path, which is otherwise unchanged: shallowest base −0.0484 m) | 17 |
| `--lift-crown` | rooted (the rootstock alone raised 50 mm: worst sector −0.0178 m) | 17 |
| `--float-moss` | moss seat (every cushion lifted 40 mm along the stone's normal: top up to 0.0967 m, rim −0.0360 m) | 18 |
| `--perch-rock` | boulder sealed (bedded against the soil height at its centre alone: worst sector −0.0166 m, 7 of 8) | 20 |
| `--sunny-moss` | moss facing (the main cushion laid on the boulder's sunny back face: 0.4250) | 21 |
| `--perch-crack-fern` | crack fern (slid 100 mm sideways out of the cleft into the wall: centre not in the cleft, walls 0.1557 m) | 22 |
| `--flat-taper` | pinnae taper (one frond's pinnae all 0.80 of its longest: tip 0.996) | 23 |
| `--opposite-pinnae` | pinnae alternate (one frond's lower-side pinnae moved level with the upper side's: gaps 0.0026–0.9976) | 23 |
| `--open-crozier` | fiddleheads (each coil a circular arc of the spiral's length: 0.932 turns, ratio 1.128) | 24 |
| `--float-cover` | ground cover (leaves, pebbles, twig and sorrel lifted 50 mm: −0.046 m, 186 shells loose) | 25 |

The crack fern is the top of the envelope, 80 mm over the moss on the
boulder's crown, so `--float-moss` and `--perch-rock` (which lifts the
boulder 55 mm with its moss) cannot move the box: in a draft the moss was
the top and both exited 8. `--flat-taper` and `--opposite-pinnae` reshape
only the crown frond held furthest inside the envelope. `--perch-crack-fern`
moves the small fern level, never up. `--lift-crown` moves the rootstock
alone; the stalks stay inside it.

## Run

```bash
blender --background --python fern_mossy_rock.py --
blender --background --python fern_mossy_rock.py -- --skip-decimate
blender --background --python fern_mossy_rock.py -- --stray-vert
blender --background --python fern_mossy_rock.py -- --lift-z
blender --background --python fern_mossy_rock.py -- --float-fronds
blender --background --python fern_mossy_rock.py -- --lift-crown
blender --background --python fern_mossy_rock.py -- --float-moss
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

The hero turns the piece −50° about Z only (`HERO_YAW_DEG`), so the fern
stands in front of the mossy face with the boulder's shaded, draped front
and the crack turned toward the camera, and looks at it from the front left,
a little above the boulder's crown. Framing measures fill x 0.766, y 0.728.
A warm wedge pools on the floor and wall behind the right of the bank.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`18` are the
hygiene, grounded, joint-fit (rooted) and seat-conformance (moss seat)
family; `19` is not used, since nothing here is plumb or dressed to a
stated size. `20`–`25` are file-local. `26` is the asset-quality floor on
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
| 18 | Moss seat: a cushion's top out of its band over the stone, or its rim or underside not inside it (`--float-moss`) |
| 20 | Boulder sealed: a sector round it not bedded in the soil (`--perch-rock`) |
| 21 | Moss facing: too little of the moss on stone that faces up or into the shade (`--sunny-moss`) |
| 22 | Crack fern: its rootstock not wedged in the cleft (`--perch-crack-fern`) |
| 23 | Pinnae: a frond's pinnae not alternate, or not tapering (`--flat-taper`, `--opposite-pinnae`) |
| 24 | Fiddleheads: a coil short of its turns, or its curvature not rising toward the centre (`--open-crozier`) |
| 25 | Ground cover: a piece out of its depth band under the soil or not joined to it, or not 102 pieces (`--float-cover`) |
| 26 | Asset-quality floor (render path only; remapped from 11) |
