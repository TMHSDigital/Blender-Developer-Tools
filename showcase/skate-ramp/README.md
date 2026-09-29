# Skate ramp

A showcase piece, not an example, and the sixth in the `sports` category.
It builds a backyard quarter-pipe, 1.2 m high on a 1.8 m transition and
2.44 m wide (an 8 ft sheet), with a skateboard resting on its deck by the
coping.

- the frame: five transition templates cut from 18 mm plywood, each a
  curved band 220 mm deep with a solid toe and an arm running back under the
  deck, standing on 2×4 sills; three studs and a back post sistered to every
  template's inboard face, so the open side shows the framing; a lip joist
  behind the coping and a rim joist at the back, both 2×6;
- nine 2×4 stringers laid flat across the templates under the skin, their
  ends buried in the outer templates;
- the skin: two layers of 12 mm plywood in full-width sheets. The top layer
  joins at 0.84 and 1.84 m of arc, the inner layer at 1.24 m, so no joint
  runs through both layers, and every joint lands on a stringer. Each sheet
  takes its own tone and grain; the joints are chamfered V lines;
- 143 screws in eleven rows over the stringers (a row either side of every
  top joint), and 35 more along the templates' arms through the deck;
- a 60 mm steel coping pipe with open ends, standing 5 mm proud of the
  transition and 4 mm above the deck, with five bracket tabs welded to its
  back and bolted down through the deck with carriage bolts;
- a 6 mm steel kicker plate at the bottom, its top flush with the plywood
  and its toe ground to a 0.8 mm lip on the ground, on a timber toe block,
  with two rows of countersunk screws;
- an 18 mm plywood deck; a worn red stencilled roundel on the transition
  and wheel marks running up it (both in the plywood shader, on the top
  layer only); and
- a skateboard: a 7-ply maple deck (0.80 × 0.205 m) with 8 mm of concave
  and two 19° kicktails, under grip tape inset 2 mm from the rail; two
  trucks, each a baseplate, a kingpin raked 35° with two bushings, a cup
  washer and a nut, a hanger with its pivot arm in a pivot cup, an axle and
  axle nuts; four 54 mm urethane wheels, each on two bearings; eight
  mounting bolt heads through the grip.

The transition is a circle of radius R about a centre R above the toe, so it
is tangent to the ground. Every sheet, template and stringer is placed on
that circle from named radii: the inner layer bites the top layer 0.5 mm,
the stringers bite the inner layer 0.5 mm, each template's curved edge bites
it 0.9 mm, each template sits 2 mm into its sill. Neighbouring sheets' side
edges stand 0.6 mm apart, and neighbouring stringers' end cuts 0.3 mm, so no
two parts share a plane.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 2.53 m from the kicker plate's toe to the back of the deck,
2.44 m across, 1.34 m to the top of the skateboard's kicktail (the deck is
at 1.20 m). The origin is under the transition's toe at floor level.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 30600–31700 | 31164 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 9 distinct; ≥3100 plywood, ≥1400 framing, ≥1030 steel, ≥6940 hardware, ≥1045 maple, ≥855 grip, ≥1460 urethane, ≥850 alloy, ≥440 bushing faces | 9 slots; 3268 / 1479 / 1086 / 7304 / 1100 / 900 / 1536 / 892 / 464 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.529, 2.440, 1.339) m ± 0.01, read off the vertices | (2.5293, 2.4400, 1.3389), zmin 0 |
| Collider tris | ≤ 380 | 350 |
| Export | written, size > 0, removed after measuring | 2376604 bytes |

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. Construction uses no RNG; two default runs print
identical measurements.

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
| Supports: each of the 5 sills, the toe block and the kicker plate has its own `zmin` | within 1e-4 of 0 | all 0 |

The first draft measured 1531 coplanar pairs. Every sheet in a layer had
its side edge on one plane, so each joint put two sheets' side faces on it
(the edges now alternate 0.6 mm); neighbouring stringers' end cuts shared
the plane of the joists' ends; the two carriage bolts on each tab sat at one
height; and the skateboard's concave faded out through the kicktails, which
twisted the deck until 28 grip faces shared planes with deck faces. The
concave now runs through the kicks, a translational surface, and the grip's
outline is the deck's outline offset along its normal, with the round ends
kept concentric.

### Transition, coping, plate, frame, skin and skateboard

| Axis | Declared | Measured |
| --- | --- | --- |
| Transition: a circle fitted (algebraic fit, then refit) to the top layer's riding face, clear of every sheet's chamfered ends and sides; its radius, the largest radial deviation of any sample, its lowest point (tangent to the ground), the deck's height | R 1.800 ± 5 mm; ≤ 1.0 mm; 0 ± 2 mm; 1.200 ± 5 mm | 1.80000 (98 samples); 0.000 mm; 0.000 mm; 1.20000 |
| Templates: count; each seated on its sill (the sill's top above the template's bottom); each curved edge inside the inner layer's underside (a circle fitted to it), per 0.01 rad bin across the layer's span | 5; 1–6 mm; 0.3–2.5 mm | 5; 2.00 mm; 0.90–0.91 mm |
| Coping: station centres of the pipe's outer face; straight (off their line); parallel to the ramp's width; its reveal, standing proud of the fitted transition; its top above the deck | ≤ 0.5 mm; ≤ 0.2°; 2–8 mm; 0–8 mm | 0.000 mm; 0.000°; 5.00 mm; 3.86 mm |
| Kicker plate: its top at its upper end against the first top sheet's top at its lower end, radially; the height of its toe | step ≤ 0.6 mm; toe ≤ 1.2 mm | 0.01 mm; 0.80 mm |
| Seams: the gaps between consecutive sheets of each layer, as arc length; every top seam from every inner seam; every seam over a stringer (clearance to its nearer edge); 9 stringers | stagger ≥ 0.30 m; ≥ 15 mm | top 0.84, 1.84, inner 1.24; 0.400 m; 43.9 mm |
| Screws: every skin screw's head over a stringer (clearance to its nearer edge, along the arc) and inside one top sheet | ≥ 8 mm; ≥ 5 mm | 143 screws; 17.4 mm; 17.0 mm |
| Wheels on the deck: count; each wheel's lowest point below the deck's top | 4; 0.2–1.2 mm | 4; 0.50 mm |
| Trucks: each wheel's centre off its axle's line; its axis against the axle's; wheels per axle | ≤ 0.3 mm; ≤ 0.5°; 2 and 2 | 0.000 mm; 0.014°; 2 and 2 |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (309 shells) |

The coping stands 3.86 mm above the deck rather than the 4 mm it was built
to: its 32-sided section is turned half a facet, so no vertex sits on its
crown. The arc fit reads the riding face alone: a face's vertices sit on the
circle, while the chamfers' vertices on the end and side faces sit 1.5 mm
behind it, so the fit keeps clear of both.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code with the triangle count at 31164, the envelope at
(2.5293, 2.4400, 1.3389) (`--lift-grip` raises its top 1 mm, inside the
tolerance) and every budget checked before the target green. The script
prints `budget_fails` after every run, listing each piece budget that
fails; each of the ten piece falsifiers lists its own budget and nothing
else.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-sill` | every sill on the floor (the middle sill 3 mm up: its `zmin` 0.003, the rest 0) | 16 |
| `--short-rib` | every template seated under the skin (the middle template's curved edge 4 mm short: bite −3.10 mm) | 17 |
| `--small-wheel` | every wheel on the deck (one wheel 2 mm smaller: bite −1.50 mm) | 18 |
| `--sag-skin` | transition on its circle (the middle top sheet 4 mm down mid-span: radius 1.77073, deviation 1.55 mm, lowest point 5.65 mm) | 19 |
| `--sink-coping` | coping reveal (the pipe 6 mm deeper into the ramp: reveal −1.00 mm) | 20 |
| `--proud-plate` | kicker plate flush (its top 3 mm proud at the joint, ramped to 0 at the toe: step 2.99 mm, toe still 0.80 mm) | 21 |
| `--stack-seams` | seams staggered (the inner joint moved 10 mm from a top joint: stagger 0.010 m, still over its stringer) | 22 |
| `--miss-screws` | screws over stringers (the row at 1.44 m moved 60 mm along the arc: 20.6 mm past a stringer's edge) | 23 |
| `--skew-wheel` | wheels coaxial (one wheel 2 mm along the deck: 2.00 mm off its axle) | 24 |
| `--lift-grip` | one connected assembly (grip tape and its eight bolt heads lifted 1 mm: 2 components) | 25 |

`--stray-vert` also leaves the stray vertex as a second component and
`--lift-z` also moves the fitted arc and the plate's toe off the ground;
both fail their target first. `--float-sill` lifts only the sill: its
template, still standing where it was, sits 5 mm into it, inside the seat
band. `--sag-skin` sags the sheet as sin², level with its neighbours at both
joints; the screws follow the sheet they hold down, so they stay seated.
`--stack-seams` moves the inner joint rather than a top one: moving a top
joint moved sheet corners onto the collider's side faces and tripped its
ceiling (exit 11) first. `--small-wheel` shrinks one wheel's tread and
keeps its bore, so it stays on its bearings and coaxial; `--skew-wheel`
slides one along the deck and keeps its lowest point, so it stays on the
deck.

## Run

```bash
blender --background --python skate_ramp.py --
blender --background --python skate_ramp.py -- --skip-decimate
blender --background --python skate_ramp.py -- --stray-vert
blender --background --python skate_ramp.py -- --lift-z
blender --background --python skate_ramp.py -- --float-sill
blender --background --python skate_ramp.py -- --short-rib
blender --background --python skate_ramp.py -- --small-wheel
blender --background --python skate_ramp.py -- --sag-skin
blender --background --python skate_ramp.py -- --sink-coping
blender --background --python skate_ramp.py -- --proud-plate
blender --background --python skate_ramp.py -- --stack-seams
blender --background --python skate_ramp.py -- --miss-screws
blender --background --python skate_ramp.py -- --skew-wheel
blender --background --python skate_ramp.py -- --lift-grip
blender --background --python skate_ramp.py -- --output ramp.png
```

Smoke passes no flags.

The hero looks up the transition from in front and to the left of its toe,
from 1.85 m above the ramp's centre, so the riding face, the coping and the
deck with the skateboard all show, and the open side shows its templates,
studs and sills against the back wall. The key comes from the front left;
the warm wedge pools on the wall to the right of the deck.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20`–`25` are file-local. `26` is the
asset-quality floor on the render path: `check_asset_quality` returns 11,
which this piece already spends on the collider ceiling, so the call site
remaps it.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a sill, the toe block or the plate off the floor (`--lift-z`, `--float-sill`) |
| 17 | Templates: not 5, one off its sill's seat band, or its curved edge outside its band under the skin (`--short-rib`) |
| 18 | Wheels: not 4, or one outside its bite band on the deck (`--small-wheel`) |
| 19 | Transition off its circle: radius, deviation, not tangent to the ground, or the deck off its height (`--sag-skin`) |
| 20 | Coping: not straight, not parallel to the width, reveal or height above the deck outside its band (`--sink-coping`) |
| 21 | Kicker plate: step to the skin or toe height too large (`--proud-plate`) |
| 22 | Seams: a top seam too near an inner seam, a seam off its stringer, or not 9 stringers (`--stack-seams`) |
| 23 | Screws: a head off its stringer or across a sheet joint (`--miss-screws`) |
| 24 | Trucks: a wheel off its axle's line or axis, or not two wheels per axle (`--skew-wheel`) |
| 25 | Assembly splits into more than one connected component (`--lift-grip`) |
| 26 | Asset-quality floor (render path only; remapped from 11) |
