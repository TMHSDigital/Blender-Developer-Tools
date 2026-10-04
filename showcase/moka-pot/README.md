# moka-pot

![A brushed eight-sided aluminium moka pot pinched to an hourglass waist with a proud grip band at the joint, a V-beak spout, a faceted lid with a black bakelite knob and a hinge knuckle, a black bakelite D handle on a fin, and a brass safety valve on the boiler](preview.webp)

A three-cup Moka Express-pattern stovetop pot: an eight-flat boiler that
flares out to its foot, a collector that flares out to its rim, both
pinching to the screw joint where the collector's threaded skirt stands
proud as a grip band, a V beak pinched from the rim, a faceted lid on a
hinge knuckle under a bakelite knob, a bakelite D handle rooted in a
riveted fin, and a brass safety valve. **A showcase piece, not an
example** — it witnesses no API contract. It asserts that generated
geometry meets declared asset budgets, recomputed from the finished mesh.

## What it composes

| Shipped content | Used for |
| --- | --- |
| `skills/mesh-editing-and-bmesh` | eight-flat lathes, a swept handle, a prism beak and plates, all in one `bmesh`; bevel pinned to a material slot |
| `skills/procedural-materials-and-shaders` | brushed aluminium, glossy bakelite, brass |
| `skills/bake-high-to-low` | Cycles tangent-space normal bake, high onto low |
| `skills/engine-export-presets` | Unity glTF (`export_yup=True`) |
| `skills/depsgraph-and-evaluated-data` | evaluated triangle counts for the LOD ratios |
| `snippets/decimate_to_budget.py` | LOD1 / LOD2 COLLAPSE chain |
| `snippets/convex_hull_collider.py` | one hull for the body, spout and lid, one for the handle |
| `snippets/lod_chain.py` | LOD naming and ratio pattern |
| `examples/mesh-hygiene-audit` | hygiene combinatorics (copied, not imported) |

## The budget that matters

A moka pot is an octagon all the way up. Eight flats, every ring of the
boiler and of the collector the same size on all eight sides, every ring
centred on one vertical axis. Two ways to break that leave every other
budget green:

- one flat a couple of millimetres proud of its seven neighbours;
- the whole pot sheared a few millimetres sideways by the time it reaches
  the lid.

Neither moves the bounding box (the handle and spout set it), the
triangle band, the hygiene audit or a joint. So the piece measures both
off the generated vertices:

- **Eight-fold spread.** Each shell's vertices are bucketed by ring
  height. At each ring the outermost radius per 45° sector is taken about
  *that ring's own centroid* and the spread between sectors asserted
  ≤ 0.2 mm. Measured about the ring's own centroid so a sheared pot
  does not trip it: that is the plumb budget's job.
- **Plumb.** The XY centroid of the boiler's foot slab is compared with
  the collector's top slab, ≤ 0.8 mm.
- **Real-world size.** Across the foot (flats), across the collector
  (flats) and total height, each against the three-cup figures below,
  ± 3 mm. The outer AABB cannot do this: the handle and spout set it.

`--odd-facet` pushes one flat of the collector's mid ring 2.5 mm out and
exits 19 on the spread (1.97 mm measured, with the AABB unchanged).
`--lean-pot` shears the pot 4 mm over its height and exits 19 on the
plumb line (3.28 mm measured, spread untouched).

## Budgets

Declared in the script as named constants, recomputed from the generated
mesh. Measured values are from Blender 5.2.1; **4.5 and 5.1 were not
available locally and are unverified** (CI runs the check-only path on
both).

| Budget | Band | Measured |
| --- | --- | --- |
| Base triangles | 1200–1400 | 1300 |
| LOD1 ratio | 0.32–0.62 | 0.5000 |
| LOD2 ratio | 0.10–0.35 | 0.2185 |
| Material slots | exactly 3, distinct | 3 |
| Aluminium / bakelite / brass faces | ≥ 160 / 280 / 100 | 197 / 388 / 124 |
| UV bounds | inside 0..1 | (0.0025, 0.0025)–(0.9975, 0.9975) |
| UV AABB overlap | ≤ 1e-5 | 0.000000 |
| Outer AABB | 0.1327 × 0.0832 × 0.1600 m ± 0.006 | 0.1327 × 0.0832 × 0.1600 |
| Collider triangles | ≤ 200 | 154 (two hulls) |
| Normal bake | `{'FINISHED'}` with image data | `{'FINISHED'}`, `has_data=True` |
| glTF export | file written, non-empty | ~78 kB |
| Hygiene | all zero | loose 0/0, non-manifold 0, zero-area 0, doubles 0, n-gons 0, coplanar cross-shell pairs 0 |
| Grounded AABB | \|zmin\| ≤ 1e-4, boiler zmin ≤ 1e-4 | 0.00000 |
| Shells | exactly 10, none unclassified | 10 |
| Collector seat on the boiler | 2.5–4.5 mm | 3.50 mm |
| Handle bite into the fin | 1.0–3.0 mm, each of the two roots | 2.50 mm, both roots |
| Knob bite into the lid | 1.0–3.0 mm | 1.80 mm |
| Lid seat on the collector | 1.0–3.0 mm | 1.80 mm |
| Spout bite and reach | base 0.9–3.0 mm into the wall; tip 10–15 mm beyond it | 1.50 mm; 12.41 mm |
| Fin bite | 0.9–3.0 mm into the wall | 1.50 mm |
| Hinge bite | 1.5–5.0 mm into the collector | 2.63 mm |
| Fasteners (valve, one rivet) | bite 0.8–2.5 mm, proud ≥ 1.2 mm | valve 1.60 / 4.60; rivet 1.20 / 1.80 |
| Real size: foot, collector, height | 83.2 / 80.2 / 160.0 mm ± 3 | 83.2 / 80.2 / 160.0 |
| Plumb | ≤ 0.8 mm | 0.000 mm |
| Eight-fold spread | ≤ 0.2 mm | 0.000 mm |

Real-world size: a three-cup Moka Express is listed at 16.0 cm tall and
9.0 cm across the base point to point, which is 83.2 mm across its
flats. The collector rim is read off product photos at 0.96 of the foot,
80.2 mm across its flats. The waist at the joint is 0.76 of the foot.
Spout tip to handle is about 133 mm.

## Construction

- **Body.** Boiler, collector and lid are eight-flat lathes from
  `(apothem, z)` profiles: the distance from the axis to the middle of a
  flat, which is what a ruler across the pot reads. Vertices every 45°
  offset by 22.5° put a flat square on each axis, so the fin and the
  spout each sit on a flat. The boiler flares from a 63.6 mm neck to an
  83.2 mm foot; the collector from a 65.2 mm waist to an 80.2 mm rim. Its
  bottom 9 mm is a vertical skirt 67.6 mm across, 2.0 mm proud of the
  boiler's neck and 1.2 mm proud of its own waist: the grip band. Every edge over 30°
  is chamfered 0.7 mm, which includes the 45° ridge between flats, so the
  ridges catch light.
- **Joints are tenoned, not stood.** The collector's floor sits 3.5 mm
  below the boiler's top plane (the boiler's neck runs up inside the
  skirt); the lid sits 1.8 mm below the collector's top plane; the knob
  is driven 1.8 mm into the lid. Nothing lands on a shared plane.
- **Spout.** A triangular prism on the −x flat: its base spans 30 mm of
  the flat and is driven 1.5 mm into the wall per vertex from the
  collector's own wall function; its apex is one vertical edge 12.4 mm
  out. The underside sweeps 21 mm down the wall to the base, and the lip
  rises 1.2 mm from the rim to the tip, so it reads as a V pinched out of
  the rim rather than a block stuck to it.
- **Fin.** A 22 mm plate on the +x flat built the same way, so it
  follows the collector's 7° flare from the waist almost to the rim. One
  brass rivet sits in the opening of the D.
- **Handle.** A bakelite D in the XZ plane: twenty-two rings of a
  twelve-point rounded rectangle along a superellipse half (exponent
  0.55, 34 mm out from the fin, 41 mm between roots), slim at the roots
  and fuller through the grip. Both roots leave the fin horizontally and
  each root cap is cut parallel to the fin's raked face, 2.5 mm inside
  it.
- **Hinge.** An aluminium knuckle on top of the fin, through the
  collector's rim and the lid's edge.
- **Fasteners.** The rivet and the valve are small turned heads aimed
  down the host's normal (the fin's rake, the boiler's taper). Their seat
  is read back as height above the host's own nearest face.
- **Shading.** Aluminium is flat-shaded, because the faceting is the
  object. Bakelite and brass are turned or swept and smooth-shaded with
  every edge over 35° hard.
- **Aluminium surface (#345).** Flat facets under a uniform grey read as
  plain planes, and the asset sheet judged the pot the least-designed
  object in its lineup. The material now carries vertical brushing (noise
  stretched along Z driving roughness 0.16–0.42 and a faint bump), a
  broad tone variation, and heat tint darkening the lowest 4.5 cm of the
  boiler, where a stovetop flame discolours a real pot. Render-only: no
  budget, face count or check changed.

## Findings the budgets forced

- **Spout floated the wrong way.** `--float-spout` first shifted the
  whole spout in +x, which is *into* the pot: the bite read 5.5 mm and
  the failure was a sunk spout, not a floating one. It now lifts the base
  outward by 4 mm and leaves the tip where it was, so only the bite fails
  and the reach stays in its band.
- **The first pass was not a Moka Express.** It was 152 mm tall with a
  100 mm foot, its waist pinched to only 0.81 of the foot, the handle a
  horn curving up off a bracket, and the spout a blunt block. Every
  budget passed. The quality pass took the size from retailer listings,
  pinched the waist to 0.76, added the grip band, and replaced the horn
  with a two-root D and the block with a V beak.
- **Two rivets on one fin are a coplanar pair.** The D's opening leaves
  room for rivets only 8.5 mm apart. On one raked plane with centres
  closer than the 20 mm window, their caps counted as 200 cross-shell
  coplanar pairs. The fin now carries one rivet, as the real one carries
  one screw.
- **The fin rakes further than it is thick.** Splitting the fin's
  vertices into inner and outer by world x put the outer face's low
  corners on the inner side, and its bite read −4.5 mm on a correct
  model. The split is now by signed distance off the collector's own
  surface.
- **A D handle has two roots.** Measuring the vertices nearest the
  pot in x saw only the lower root, because the wall flares out with
  height. Each half of the D is now read on its own, from the handle
  vertices inside the fin, and a root with none inside is a float.

## Conventions walked

Every convention in `showcase/README.md`, and whether it applies here.

| Convention | Applies | How |
| --- | --- | --- |
| Deterministic, budgets declared, assertions recompute | yes | no RNG; every value above is read off the mesh |
| Falsifier fails the budget it targets | yes | table below |
| Hygiene incl. cross-shell coplanar | yes | exit 15; `--flush-joint` is the coplanar falsifier |
| Named supports | no | one support (the boiler's foot) |
| Joint-fit budgets | yes | shell count, collector seat, both handle roots (exit 17) |
| Fasteners aimed down the host normal | yes | rivet and valve (`--float-valve`, exit 18) |
| Seat conformance | yes | knob, lid, spout, fin, hinge, fasteners (exit 18) |
| A member is tenoned into its seat, never stood on it | yes | collector, lid, knob, handle |
| Plumb and real-world size | yes | exit 19; plumb, three sizes in metres |
| Mirrored assemblies | no | nothing is paired |
| Even shaping terms | n/a | no shaping function; profiles are piecewise linear |
| Edge treatment: no right angles | yes | 0.7 mm chamfer on every aluminium edge over 30°; the asset-quality right-angle fraction is 0.044 |
| One substance, one slot | yes | aluminium, bakelite, brass |
| Shading is part of the model | yes | see Construction |
| Chamfer n-gon caps, then triangulate | yes | every cap |
| Sort bmesh operator inputs | yes | bevel edges sorted by index |
| Level on the stage; stage scaled | yes | turned about Z only; the 60 m stage and the rig are scaled by 0.2 with light power by 0.04 |
| Keep a falsifier's envelope still | yes | every falsifier moves less than `BBOX_TOL` (6 mm) |
| Rope, masonry, roofs, hung rings, scatter | no | none present |

## Falsifiers

Each breaks one pipeline stage so a **named** budget fails. All ten were
run on Blender 5.2.1 and exited the documented code; 4.5.11 and 5.1.2
were not available locally and are unverified.

| Flag | Target budget | Breaks | Exit |
| --- | --- | --- | --- |
| `--skip-decimate` | LOD1 ratio | drops the DECIMATE modifiers, LOD1 ratio goes to 1.0000 | 9 |
| `--stray-vert` | mesh hygiene | adds one loose vertex on the axis | 15 |
| `--flush-joint` | coplanar cross-shell pairs | drops the boiler's top plane onto the collector's floor plane; 6 pairs | 15 |
| `--lift-z` | grounded zmin | lifts the whole mesh 20 mm | 16 |
| `--short-handle` | handle bite | stops both handle roots 3 mm outside the fin; no root vertex inside it | 17 |
| `--float-knob` | knob bite | lifts the knob 4 mm; −2.2 mm | 18 |
| `--float-spout` | spout bite | lifts the spout's base 4 mm off the wall, tip fixed; −2.5 mm | 18 |
| `--float-valve` | fastener seat | lifts the valve 3 mm off its flat; −1.4 mm | 18 |
| `--lean-pot` | plumb | shears the pot 4 mm over its height; 3.28 mm drift | 19 |
| `--odd-facet` | eight-fold spread | pushes one mid-ring flat 2.5 mm out; 1.97 mm spread | 19 |

## Exit codes

File-local and sequential. `9` is a valid check code. `1` is the FATAL
wrapper — a crash, never a named check. `10` is the framing gate and `21`
the asset-quality gate (the helper's own code, `11`, is spent here on the
collider ceiling), both on the render path only.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, or has no UV layer |
| 4 | Base triangle count outside band |
| 5 | Material slots, or a material's face floor |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | Outer AABB off declared size |
| 9 | LOD1 or LOD2 ratio outside band (`--skip-decimate`) |
| 10 | Framing gate (`examples/gallery_framing.py`, render path only) |
| 11 | Collider triangles above ceiling |
| 12 | Normal bake failed or produced no image data |
| 13 | glTF export missing or empty |
| 14 | `--output` produced no file |
| 15 | Mesh hygiene (`--stray-vert`, `--flush-joint`) |
| 16 | Grounded zmin (`--lift-z`) |
| 17 | Shell count, collector seat, or handle bite (`--short-handle`) |
| 18 | Knob, lid, spout, fin, hinge or fastener seat (`--float-knob`, `--float-spout`, `--float-valve`) |
| 19 | Real-world size, plumb, or eight-fold spread (`--lean-pot`, `--odd-facet`) |
| 21 | Asset-quality gate (`examples/gallery_asset_quality.py`, render path only) |

## Run it

```bash
# Budget check, no render. ~1 s on a warm 5.2.
blender --background --python moka_pot.py --

# Falsifier: the pot leans at the lid. Must exit 19.
blender --background --python moka_pot.py -- --lean-pot

# Falsifier: one flat out of line with the other seven. Must exit 19.
blender --background --python moka_pot.py -- --odd-facet

# Render the gallery still (EEVEE; --engine cycles on a GPU-less host).
blender --background --python moka_pot.py -- --output moka_pot.webp
```

Smoke runs the check-only path. It does not pass `--output` or any falsifier.

## Cross-version measurements

Measured on 5.2.1 only. 4.5 and 5.1 are unverified locally.

| Value | 5.2.1 |
| --- | --- |
| Base triangles | 1300 |
| LOD1 / LOD2 tris | 650 / 284 |
| Face counts (aluminium / bakelite / brass) | 197 / 388 / 124 |
| Outer AABB | 0.1327 × 0.0832 × 0.1600 |
| Collider tris | 154 |
| glTF bytes | 77860 |
