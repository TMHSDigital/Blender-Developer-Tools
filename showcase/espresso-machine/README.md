# Espresso machine

A showcase piece, not an example, and the fifth in the `household`
category. It builds a procedural prosumer E61 semi-automatic espresso
machine, generic and unbranded, on a short countertop section:

- a honed limestone countertop section 0.67 × 0.655 m with a bullnose front
  edge and eased cut ends;
- a black painted chassis box behind a brushed stainless front panel, a back
  panel, and two side panels folded round the front and back edges, each a
  single sheet with two banks of seven louvred vent slots cut through it;
- four adjustable feet: a rubber pad on the counter, a chrome stem up into
  the chassis and a hex lock nut;
- a pressed stainless warmer tray on top with a tubular rail bent from one
  bar (down into the tray at the front, round the sides and back) and two
  rear posts, carrying three upturned demitasses and a cappuccino cup;
- the E61 group: a cast neck and a thermosiphon pipe off the panel, a
  skirted bayonet ring with a rubber gasket in its bore, a waisted body under
  the mushroom cap, a chimney on top with two lug posts and bosses, and the
  lever's hub on a domed pin through them, its arm ending in a bakelite ball;
- a spouted portafilter locked into the group against the gasket: a chrome
  body with two bayonet ears, a shank into a turned walnut handle, a spout
  block and two spouts;
- steam (right) and hot-water (left) valves with fluted bakelite knobs and
  chrome caps, each wand hung from a ball joint under its valve and ending
  in a nozzle;
- twin pressure gauges side by side above the group: chrome bezels, dials
  printed with tick marks (every fourth one long) and a red band, needles
  on hubs, and domed glasses sat back inside the bezels' lips;
- a power toggle and an amber pilot lamp;
- a pressed drip tray tucked under the front panel, its grate one sheet
  with 31 slots cut through it, a shot cup of espresso on the grate under
  the spouts; and
- on the counter: a stainless knock box on a rubber base ring with a rubber
  bar across its rim and two spent pucks inside, a tamper with a walnut
  handle, and a milk pitcher with a pulled spout and a strap handle.

Every face carries a `part` tag (a face attribute written as each part is
built), and the audits classify shells by it. The measurements themselves
are read off the mesh.

The side panels and the grate are one helper, `add_sheet`: a sheet swept
along a plan path through a set of heights, where each cell of that grid is
metal or a slot, and every slot is walled round. Each is a single manifold
shell of quads. A side panel's path runs in from the front fold, round a
4 mm bend, down the side past the vent banks' stations, round the back bend
and in again, so the folds and the louvres are one piece of metal, as they
are on the machine.

Stainless and chrome carry a studio in their material. A metal on the
house's dark stage mirrors the dark stage and reads as grey paint (the
stand mixer's bowl did). Here the world-space reflection vector looks up a
ramp — a bright band of walls and softboxes around the horizon, a dim
ceiling, a dark floor straight down, the key's side brighter than the
other — added as emission, so the metal reads in the hero and on the asset
sheet's neutral stage alike. A vertical panel seen from above mirrors what
lies just below the horizon: the first ramp, bright only above it, left
every panel black. Steel gets a soft gradient down a panel; chrome a narrow
bright horizon, a dark gap and a softbox above.

Things the coplanar budget forced:

- The feet's stem caps sat on the drip tray's floor plane; the stems tuck
  a millimetre further into the chassis.
- The two lug posts are mirror images, so their chamfers shared planes.
  One is staggered 0.8 mm in y and 0.3 mm in z. Staggering both axes by
  similar amounts cancelled on the 45° chamfers and fixed nothing.
- The gauge glass had the dial's radius, so the two rims met on a plane
  wherever their facets lined up; the glass is 0.3 mm larger.
- Side by side, the two gauges' dials and bezels shared every plane facing
  the camera (26026 pairs); the right gauge sits 0.4 mm prouder.
- `--bunch-feet` packs two pads 47 mm apart, where their near-flat top rings
  met on one plane. The pad top is now a steep chamfer.
- `--narrow-body` put a valve flange into the side panel's bend, where a
  flange facet and a bend facet met on one plane. The narrow body is 1.5 mm
  wider, so the flange clears the bend.

Shading follows what each part is. Lathed parts, sweeps and cups are
smooth-shaded; chamfers, slots, knurls and folds stay crisp above 35° and at
every material boundary. The walnut is oiled (a thin coat) with its grain
noise stretched along one axis; the porcelain carries a glaze coat.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`,
`procedural-materials-and-shaders`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a machine 0.300 m wide and 0.391 m to its warmer tray on a
0.03 m counter, 0.376 m deep plus a 0.12 m drip tray, with a 0.064 m
cappuccino cup setting the top. The outer AABB is 0.670 × 0.655 × 0.4755 m:
the counter sets the plan and the cup the top. The origin is under the
counter.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 43000–44300 | 43636 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 14 distinct; face floors ≥4400 stainless, ≥6700 chrome, ≥870 bakelite, ≥580 wood, ≥5330 ceramic, ≥1140 rubber, ≥580 glass, ≥1510 dial, ≥58 ink, ≥32 needle, ≥84 stone, ≥24 paint, ≥415 coffee, ≥106 lamp | 14 slots; 4788 / 7284 / 948 / 632 / 5800 / 1244 / 632 / 1642 / 64 / 36 / 91 / 26 / 452 / 116 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.670, 0.655, 0.4755) m ± 0.01 | (0.6700, 0.6550, 0.4755), zmin 0 |
| Collider tris | ≤ 520 | 447 |
| Export | written, size > 0, removed after measuring | 3229536 bytes |

No falsifier changes the topology, so every one of them measures the
default's 43636 triangles. Every one keeps the default's AABB except
`--sink-cup`, which sinks the cup that sets the top 3 mm and measures
0.4725 m, inside the 10 mm tolerance.

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
| Feet: each of the 4 rubber pads sunk into the counter top read off the mesh | 0.0001–0.0008 m | 0.00025, 0.00040, 0.00055, 0.00070 |

### Lever, cups, size, portafilter, gauges, tray, stance and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Lever pin: the pin's PCA axis against the axis of each of the 2 bosses and the lever's hub; the pin spans each in x; tilt off X | ≤ 0.0003 m; 2 + 1; 0 not through; ≤ 0.5° | 0.000000; 2 + 1; 0; 0.0000° |
| Cups seated: each of the 5 cups' lowest ring against its host's top, read by rays down onto the host alone (the warmer tray for the four upturned cups, the grate for the shot cup) | 0.0001–0.0009 m | 0.00020, 0.00038, 0.00056, 0.00074; 0.00035 |
| Size: width across the side panels; warmer-tray top above the counter | 0.300 ± 0.004 m; 0.3907 ± 0.004 m | 0.30000; 0.39070 |
| Portafilter coaxial: the portafilter body's and the gasket's axes (lathe centroids) against the group's | ≤ 0.0003 m | 0.000000; 0.000000 |
| Portafilter seat: the basket rim's top pressed into the gasket's face | 0.0001–0.0008 m | 0.00040 |
| Gauge faces: each glass's front behind its bezel's front lip | 0.0015–0.0050 m; 2 + 2 | 0.0034, 0.0034 |
| Drip tray: inside the side panels on both sides; its back tucked behind the front panel's face | margin ≥ 0.010 m; tuck ≥ 0.005 m | 0.0250; 0.0170 |
| Stance: mass centre (shell volumes × densities, counter and props excluded) inside the convex polygon of the pads' contact faces | ≥ 0.060 m | 0.1064 (39.83 kg) |
| One connected assembly (union of shells whose BVH trees overlap; faceless shells are hygiene's) | 1 component | 1 (94 shells) |

A heat-exchanger E61 carries its group, portafilter and drip tray well in
front of the chassis, and stands because its feet are spread under it. The
stance budget measures that. The densities are named constants (stainless
and paint steel 7900/7800, chrome-plated brass 8500, bakelite 1400,
walnut 700, porcelain 2300, rubber 1200, glass 2500), with the chassis box
overridden at 350: it is solid in the mesh, a frame round a boiler and air
in the machine.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code, and every other budget in its run stayed green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-foot` | feet on the counter (one pad 3 mm up: seat −0.00230 m) | 16 |
| `--offset-pin` | lever pin coaxial through its bosses and hub (pin 1.5 mm up: 0.001500 m) | 17 |
| `--sink-cup` | cups seated on their host (the cappuccino cup 3 mm into the tray: 0.00356 m) | 18 |
| `--narrow-body` | size (side panels drawn in: width 0.28300 m) | 19 |
| `--offset-pf` | portafilter coaxial with the group (slid 1.2 mm: 0.001200 m) | 20 |
| `--drop-pf` | portafilter seated to the gasket (2 mm low: seat −0.00160 m) | 21 |
| `--proud-gauge` | gauge faces behind their bezels (glass, dial and needle 4.5 mm out: recess −0.0011 m) | 22 |
| `--shift-tray` | drip tray inside the body's footprint (30 mm right: margin −0.0050 m) | 23 |
| `--bunch-feet` | stance (feet under the back: margin −0.1613 m) | 24 |
| `--loose-knob` | one connected assembly (steam knob 5 mm off its valve: 2 components) | 25 |

`--float-foot` leaves the pad's stem still inside it, so the assembly holds.
`--drop-pf` and `--offset-pf` leave the portafilter inside the group's
skirt, so it stays joined and only the seat or the axis moves. `--sink-cup`
sinks, rather than floats, the cup, so the cup stays joined to the tray.
`--proud-gauge` leaves the glass and dial inside the bezel's bore.
`--shift-tray` keeps the tray tucked into the chassis, and the shot cup on
the grate. `--bunch-feet` keeps every pad on the counter and under the
chassis, so only the mass centre leaves the support polygon.

## Run

```bash
blender --background --python espresso_machine.py --
blender --background --python espresso_machine.py -- --skip-decimate
blender --background --python espresso_machine.py -- --stray-vert
blender --background --python espresso_machine.py -- --lift-z
blender --background --python espresso_machine.py -- --float-foot
blender --background --python espresso_machine.py -- --offset-pin
blender --background --python espresso_machine.py -- --sink-cup
blender --background --python espresso_machine.py -- --narrow-body
blender --background --python espresso_machine.py -- --offset-pf
blender --background --python espresso_machine.py -- --drop-pf
blender --background --python espresso_machine.py -- --proud-gauge
blender --background --python espresso_machine.py -- --shift-tray
blender --background --python espresso_machine.py -- --bunch-feet
blender --background --python espresso_machine.py -- --loose-knob
blender --background --python espresso_machine.py -- --output espresso.png
```

Smoke passes no flags.

The camera looks along (−0.55, 0.83), so the hero shows the machine's
front — gauges, knobs, group, portafilter handle in profile, shot cup on
the grate — and its right side panel with the vent banks, with the tamper
and pitcher in the left foreground and the knock box to the right. The
wall behind the machine in frame lies 1.6 m to its −X, so the warm wedge is
aimed there rather than at the wall straight behind the piece.

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
| 5 | Material count ≠ 14 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a pad off the counter or not 4 pads (`--lift-z`, `--float-foot`) |
| 17 | Lever pin off a boss's or the hub's axis, not spanning one, tilted, or not 2 + 1 (`--offset-pin`) |
| 18 | A cup's seat on its host outside its band, or not 5 cups (`--sink-cup`) |
| 19 | Size: body width or warmer-tray height off (`--narrow-body`) |
| 20 | Portafilter or gasket off the group's axis (`--offset-pf`) |
| 21 | Portafilter rim's seat in the gasket outside its band (`--drop-pf`) |
| 22 | A gauge glass not recessed in its bezel by the band, or not 2 + 2 (`--proud-gauge`) |
| 23 | Drip tray outside the side panels' margin or not tucked behind the front panel (`--shift-tray`) |
| 24 | Stance: mass centre within 60 mm of the pads' support polygon's edge (`--bunch-feet`) |
| 25 | Assembly splits into more than one connected component (`--loose-knob`) |
| 26 | Asset-quality floor (render path only; remapped from 11) |
