# garden-gate

![A ledged and braced garden gate of six weathered oak boards with a bow top, standing ajar on two black strap hinges between square oak posts on sandstone flags, a ring pull on its face](preview.webp)

A 900 mm ledged-and-braced garden gate: six vertical oak boards under a
bow top, nailed to three back ledges with two diagonal braces between
them, hung from a squared hinge post on two hook-and-band hinges and
closing against a latch post. A barrel bolt sits on the back, a keeper
staple on the latch post, a ring pull on the front, and both posts stand
in sandstone flags. **A showcase piece, not an example** — it witnesses
no API contract. It asserts that generated geometry meets declared asset
budgets, recomputed from the finished mesh.

## What it composes

| Shipped content | Used for |
| --- | --- |
| `skills/mesh-editing-and-bmesh` | prisms, revolved knuckles, pins, domes and nail heads, a torus ring, all in one `bmesh`, chamfered with `bmesh.ops.bevel` |
| `skills/custom-properties` | face attributes: `Part` (what each shell is), `GrainDir` (vertical or horizontal fibre) and `WoodTone` (one tone per board or flag) |
| `skills/procedural-materials-and-shaders` | weathered oak with grain along each member, a tone per board and grime toward the ground; black forged iron rusting in patches; sandstone flags |
| `skills/bake-high-to-low` | Cycles tangent-space normal bake, a 24-segment high onto the 12-segment low |
| `skills/engine-export-presets` | Unity glTF (`export_yup=True`) |
| `skills/depsgraph-and-evaluated-data` | evaluated triangle counts for the LOD ratios |
| `snippets/decimate_to_budget.py` | LOD1 / LOD2 COLLAPSE chain |
| `snippets/convex_hull_collider.py` | a hull per post, one over the gate's timber, one over the paving |
| `snippets/lod_chain.py` | LOD naming and ratio pattern |
| `examples/mesh-hygiene-audit` | hygiene combinatorics (copied, not imported) |

## The budget that matters

A hook-and-band hinge is a rolled eye (the knuckle) on the end of an
iron strap, dropped over an upright pin on a hook driven into the post.
It can fail without looking wrong:

- **Each knuckle must be coaxial with its pin**, with a running
  clearance between them. A millimetre off and the eye still sits on the
  hook in every picture, but the pin is not inside the bore.
- **Both pins must stand plumb on one shared axis.** Lean one and the two
  hinges no longer agree on an axis, so the gate binds instead of turning.
- **Each knuckle must rest on its hook**, a seat, not a float.
- **The gate must clear the latch post as it swings.** A closed gate shows
  nothing; only the swing circle does.

The piece measures all four off the finished mesh. Every shell carries a
`Part` face attribute written at build time, so the audit finds the two
knuckles, the two pins, the two hooks, every member that hangs on the
hinges and the latch post with its keeper, without guessing from shape.

- **Knuckle on pin.** A knuckle's axis is the plan centroid of its own
  vertices (a revolved tube is symmetric about its axis); its bore is the
  nearest of them to that axis. A pin's axis is the line through the
  centroids of its end rings, read at the knuckle's mid-height; its
  radius is the farthest bottom-ring vertex from that ring's centroid.
  Coaxial within 0.3 mm; radial clearance (bore − pin − offset) in
  0.3–1.0 mm. Measured 0.000 mm and 0.600 mm.
- **Seat.** The knuckle's bottom against the hook's top: −1.0 to −0.2 mm
  (it rests 0.5 mm into the hook's shoulder, so no two faces are one
  plane). Measured −0.500 mm.
- **Plumb, one axis.** Each pin's top-ring centroid within 0.2 mm of its
  bottom-ring centroid in plan, and the two pins' feet within 0.3 mm of
  each other. Measured 0.000 and 0.000 mm.
- **Swing.** The hinge axis is the mean of the two measured knuckle
  axes. Every vertex that hangs on the hinges (boards, ledges, braces,
  straps, knuckles, bolts, nails, the barrel bolt and the ring) gives the
  swing circle's radius; every vertex of the latch post and its keeper
  gives the nearest obstacle. Clearance 8–30 mm; measured 14.87 mm
  (radius 0.9153 m, keeper at 0.9301 m).

`--offset-knuckle` moves the upper knuckle 1.5 mm off its pin and leaves
everything else where it was: exit 17. `--tilt-pintle` leans the upper pin
about the knuckle's mid-height, so its axis still passes through the
knuckle and the coaxial budget holds; only plumb fails, exit 19.
`--tight-post` sets the latch post 14 mm closer; the paving defines the
envelope, so the AABB does not move, and the swing clearance drops to
0.89 mm: exit 20.

## Budgets

Declared in the script as named constants, recomputed from the generated
mesh. Measured values below are from Blender 5.2.1; see the
cross-version table for 4.5.11 and 5.1.2.

| Budget | Band | Measured |
| --- | --- | --- |
| Base triangles | 3100–3550 | 3320 |
| LOD1 ratio | 0.32–0.62 | 0.5000 |
| LOD2 ratio | 0.10–0.35 | 0.2193 |
| Material slots | exactly 3, distinct | 3 |
| Timber / iron / ground faces | ≥ 330 / 1400 / 140 | 370 / 1534 / 156 |
| UV bounds | inside 0..1 | (0.0009, 0.0009)–(0.9991, 0.9991) |
| UV AABB overlap | ≤ 1e-5 | 0.000000 |
| Outer AABB | 1.560 × 0.560 × 1.245 m ± 0.020 | 1.5600 × 0.5600 × 1.2450 |
| Collider triangles | ≤ 400 | 344 (four hulls) |
| Normal bake | `{'FINISHED'}` with image data | `{'FINISHED'}`, `has_data=True` |
| glTF export | file written, non-empty | ~281 kB |
| Hygiene | all zero | loose 0/0, non-manifold 0, zero-area 0, doubles 0, n-gons 0, coplanar cross-shell pairs 0 |
| Grounded AABB | \|zmin\| ≤ 1e-4 | 0.00000 |
| Parts | 6 flags, 2 posts, 6 boards, 3 ledges, 2 braces, 2 straps, 2 knuckles, 2 pins, 2 hooks, 6 bolt heads, 26 nails, 5 bolt pieces, 1 keeper, 3 ring pieces | as stated |
| Knuckle on pin | coaxial ≤ 0.3 mm, clearance 0.3–1.0 mm | 0.000 mm, 0.600 mm (both hinges) |
| Knuckle seat | −1.0 to −0.2 mm on the hook | −0.500 mm (both) |
| Plumb shared axis | each pin ≤ 0.2 mm, pins ≤ 0.3 mm apart | 0.000 mm, 0.000 mm |
| Swing clearance | 8–30 mm past the latch post and keeper | 14.87 mm |
| Real-world size | gate 0.900 ± 0.003 × 0.960 ± 0.005, post 1.205 ± 0.005 above its flag, strap 0.400 ± 0.005, pin Ø 12 ± 0.5 mm | 0.9000 × 0.9599, 1.2050, 0.3995, 12.000 mm |

Real-world size: hook-and-band hinges are usually sized at a third of the
gate's width, so a 900 mm gate takes 400 × 38 mm straps on 12 mm pins.
The gate stands 100 mm clear of the paving, the bow top rising 60 mm
from the stiles to the middle board, between 100 mm square posts 1.2 m
above the flags.

## Construction

- **Boards.** Six 145 × 22 mm prisms with 6 mm joints, each outline cut
  to the parabolic bow top, every near-right-angle edge chamfered 2.5 mm.
- **Ledges and braces.** Three 95 × 23 mm ledges on the back, 1 mm into
  the boards so their front is not the boards' back plane. The two braces
  rise from the hinge side to the latch side (the strut that carries the
  free edge's weight back down into the bottom hinge); their ends are
  bitten 2 mm into the ledges and their faces sit off the ledges' planes.
- **Hinges.** The strap is a tapered prism 0.5 mm into the boards, with
  three domed carriage-bolt heads. The knuckle is a revolved tube 6.6 mm
  bore, 11.2 mm outside, 40 mm tall, 2 mm taller than the strap so their
  ends are not one plane. The hook is a 14 mm square shank driven 70 mm
  into the hinge post and a 12 mm pin rising through it, chamfered at the
  top.
- **Nails.** Rose-headed nails, two per board at every ledge, except where
  a strap's bolts already hold the board. Each head is sunk 0.7 mm: at
  0.5 mm they shared the strap's back plane.
- **Latch.** A barrel bolt on the middle ledge (backplate, two guides, a
  rod drawn back inside the gate's edge and its knob), a keeper staple
  bitten 6 mm into the latch post, and a ring pull on a round rose that
  hangs from its staple and leans out at the bottom.
- **Posts and paving.** Square posts with chamfered arrises and a
  pyramid weathering, sunk 20 mm into the flags. A pad flag under each
  post and four flags across the opening, 12 mm joints, the opening's
  flags 4–6 mm proud or shy of the pads so no two flag tops are one plane.
- **Collider.** One hull per post, one over the gate's timber, one over
  the paving. The ironwork is left out: millimetres of strap and bolt on
  faces the gate's hull already covers.
- **The still.** The gate is swung 24° open about the measured hinge axis
  for the render only, so the knuckles are seen turning on their pins and
  the keeper shows on the latch post. Every budget is asserted on the
  closed gate.

## Findings the budgets forced

- **Coplanar cross-shell.** The first run reported eight pairs: the nail
  heads near each strap's tip were sunk 0.5 mm, onto the strap's own back
  plane. They are sunk 0.7 mm now.
- **Pole in the ring.** The pin's radius was first read as the mean
  distance of its bottom ring from its centroid, and the pole vertex at
  that height pulled it 0.5 mm low. It is the farthest vertex now.
- **A falsifier that would land early.** A wider gate was the obvious way
  to break the swing, but it moves the gate's width before the swing is
  read, so it would fail the real-world size first. `--tight-post` moves
  the latch post instead.
- **The swing has a limit the other way.** Swung inward the gate's
  hinge-side back corner meets the hinge post at about 35°; the still
  uses 24°.

## Conventions walked

Every convention in `showcase/README.md`, and whether it applies here.

| Convention | Applies | How |
| --- | --- | --- |
| Deterministic, budgets declared, assertions recompute | yes | no RNG; every value above is read off the mesh |
| Falsifier fails the budget it targets | yes | table below |
| Hygiene incl. cross-shell coplanar | yes | exit 15 |
| Plumb and real-world size | yes | both pins plumb on one axis (`--tilt-pintle`), gate, post, strap and pin sizes; exit 19 |
| A member is tenoned into its seat | yes | posts into the flags, ledges and straps into the boards, braces into the ledges, the keeper into the post, the hook into the post |
| Seat conformance (a band: minimum so it cannot float) | yes | each knuckle on its hook (`--lift-gate`), exit 18 |
| Mirrored assemblies | no | a gate is handed; nothing is mirrored |
| Material face floors | yes | timber 330, iron 1400, ground 140 |
| One substance, one slot | yes | oak, forged iron, sandstone |
| Shading is part of the model | yes | timber and flags faceted; knuckles, pins, domes, rod and ring smooth, every edge over 35° hard |
| Edge treatment | yes | every prism chamfered; no separate budget, removing the chamfers moves the triangle band first |
| Sort bmesh operator inputs | yes | the bevel's edge list is sorted by index |
| The bake cage is narrower than the nearest neighbour | yes | `CAGE_EXTRUSION` 0.01 m |
| Level on the stage; stage 60 m | yes | turned about Z only; 60 m floor and wall |
| Keep a falsifier's envelope still | yes | no falsifier moves the AABB; `--tight-post` moves a post inside the paving |
| Named supports, wrappers, rope, roofs, vessels, scatter, fasteners | partly | fasteners: nails and bolt heads are counted as parts |

## Falsifiers

Each breaks one pipeline stage so a **named** budget fails. All seven
were run on Blender 4.5.11, 5.1.2 and 5.2.1 and exited the declared code.

| Flag | Target budget | Breaks | Exit |
| --- | --- | --- | --- |
| `--skip-decimate` | LOD1 ratio | drops the DECIMATE modifiers, LOD1 ratio goes to 1.0000 | 9 |
| `--stray-vert` | mesh hygiene | adds one loose vertex inside the hinge post | 15 |
| `--lift-z` | grounded zmin | lifts the whole mesh 50 mm | 16 |
| `--offset-knuckle` | knuckle on pin | moves the upper knuckle 1.5 mm along the gate; clearance −0.90 mm | 17 |
| `--lift-gate` | knuckle seat | lifts everything that hangs 3 mm off the hooks; seat +2.50 mm | 18 |
| `--tilt-pintle` | plumb shared axis | leans the upper pin 3.4° about the knuckle's mid-height; top 3.96 mm off its foot | 19 |
| `--tight-post` | swing clearance | sets the latch post 14 mm closer; clearance 0.89 mm | 20 |

## Exit codes

File-local and sequential. `9` is a valid check code. `1` is the FATAL
wrapper — a crash, never a named check.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build, has no UV layer, or a part count is wrong |
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
| 15 | Mesh hygiene (`--stray-vert`) |
| 16 | Grounded zmin (`--lift-z`) |
| 17 | Knuckle off its pin or bore clearance out of band (`--offset-knuckle`) |
| 18 | Knuckle seat on its hook (`--lift-gate`) |
| 19 | Pin plumb, shared hinge axis or real-world size (`--tilt-pintle`) |
| 20 | Swing clearance at the latch post (`--tight-post`) |
| 24 | Asset-quality floors (`examples/gallery_asset_quality.py`, render path only) |

## Run it

```bash
# Budget check, no render. A few seconds warm.
blender --background --python garden_gate.py --

# Falsifier: the latch post 14 mm closer. Must exit 20.
blender --background --python garden_gate.py -- --tight-post

# Falsifier: the upper knuckle 1.5 mm off its pin. Must exit 17.
blender --background --python garden_gate.py -- --offset-knuckle

# Render the gallery still (EEVEE; --engine cycles on a GPU-less host).
blender --background --python garden_gate.py -- --output garden_gate.webp
```

Smoke runs the check-only path. It does not pass `--output` or any falsifier.

## Cross-version measurements

Every default run and every falsifier was run on all three binaries
(`.scratch/blender-<ver>-windows-x64/blender.exe`, reporting 4.5.11 LTS,
5.1.2 and 5.2.1 LTS). Only the DECIMATE counts differ, which is why the LOD
gate is a ratio band; every hinge, swing and size value is identical.

| Value | 4.5.11 | 5.1.2 | 5.2.1 |
| --- | --- | --- | --- |
| Base triangles | 3320 | 3320 | 3320 |
| LOD1 / LOD2 triangles | 1660 / 730 | 1660 / 730 | 1660 / 728 |
| LOD2 ratio | 0.2199 | 0.2199 | 0.2193 |
| Faces timber / iron / ground | 370 / 1534 / 156 | 370 / 1534 / 156 | 370 / 1534 / 156 |
| Collider triangles | 344 | 344 | 344 |
| Coaxial, clearance, seat | 0.000 / 0.600 / −0.500 mm | same | same |
| Swing clearance | 14.869 mm | 14.869 mm | 14.869 mm |
| Falsifier exits 9 / 15 / 16 / 17 / 18 / 19 / 20 | all as declared | all as declared | all as declared |
