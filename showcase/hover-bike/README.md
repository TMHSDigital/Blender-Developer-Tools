# Hover bike

A showcase piece, not an example, and the second in the `vehicles`
category. It builds a procedural sci-fi hover bike, parked on its landing
gear:

- a sculpted fuselage, lofted from superellipse sections along the bike's
  length: a muted teal livery canopy with twin pearl racing stripes above
  a shoulder parting line, a dark composite belly under it, a parting-line
  groove along both flanks and three transverse panel seams. A tank hump
  rises ahead of the rider, a tail cowl behind, and nose and tail run as
  necks into the two shrouds;
- on the fuselage's skin: intake grilles on the tank flanks, louvred
  vents on the tail flanks, a crown vent, gunmetal cooling fins under the
  rider's knee and a finned heat sink near the tail; access panels (each
  a livery panel proud of a dark gasket by an even 4 mm seam, hex
  fasteners at its corners), an alloy service plate on the belly, a decal
  plate (an anodised field on a dark board, no text), a charge-port door
  hinged along its top edge with an anodised latch, a pillion grab rail
  arching over the tail and a tail-light cluster (housing, red lamp,
  dividers) between the exhaust nozzles;
- a saddle draped over the crown: its underside follows the fuselage a
  bite inside it, and its top carries puffed pleats between six stitched
  seams;
- a cockpit: twin chrome fork stanchions in pleated rubber boots, through
  two sculpted triple clamps (bosses round both stanchions and the stem,
  pinch bolts) to anodised fork caps; a steering stem with its nut; clip-on
  clamps carrying the bars, with switch pods (two buttons each), lever
  perches, orange levers on chrome pivot bolts, ribbed grips and bar-end
  weights; an instrument cluster with an emissive screen on a bracket
  from the top clamp, a small tinted visor rising off its front edge, a
  low fly screen and a headlight pod on the tank's front slope;
- two exhaust nozzles leaving the tail flanks over the rear fan, each a
  cup with a scalloped lip, an orange band, a glowing core and a tail cone;
- two ducted fans on the centreline, 1.60 m apart. Each shroud is an
  airfoil-section ring (0.262 m throat, rounded inlet lip, livery outside
  and dark inside) with an orange band and a marker light, white on the
  front shroud and red on the rear. Inside, a motor can stands on four
  canted stator vanes, and a rotor hub, an orange spinner and seven
  twisted, cambered, lofted blades turn on it. The two rotors are handed;
- two aerofoil pylons from shroud to shroud, their chord vertical in the
  fans' downwash, flared into both shroud walls and tied into the belly by
  two fairing webs each, with a row of hex fasteners along the outer face,
  a conduit in P-clips along the crest and a ribbed foot peg; and
- landing gear at each end of each pylon: a twin-plate pressed link from a
  pylon lug to a skid lug, and an oleo shock (anodised barrel, dark
  preload collar, pleated boot, chrome rod) from a pylon clevis to the
  link's middle. Every one of the 16 joints is a headed pin with a nut
  through two bosses and one eye. The links carry two ski-section skid
  shoes (flat sole, domed crown, upturned tips) on replaceable wear
  strips, with bolted anodised end caps and a row of strip bolts, tied by
  two cross braces with collars.

The layout is solved from named constants. Every blade section is wrapped
onto its own cylinder about the fan axis, so the tip is exactly
`BLADE_TIP` from it and the clearance to the throat is a design number
(10 mm), not a side effect of a flat section's corners. Grilles, fins,
panels and plates are laid on the fuselage's closed-form surface along its
own normal. The hull's section parameter is symmetric about its crown, so
the hull is its own mirror image vertex for vertex. The gear's pins,
bushings, barrels, rods and wear strips carry a `part` face tag (role and
unit), so the joint, shock and ground audits read the parts they mean
rather than guessing them from shape.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 2.23 m long, 0.66 m across the bar ends, 1.11 m to the top
of the cluster's visor, with the saddle's top at 0.852 m. The shrouds set
the length, the bar-end weights the width and the visor the top. The
fuselage is 1.033 × 0.344 m. The origin is under the bike's centre, so it
lands on the soles of its wear strips.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 45000–46000 | 45796 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2197 |
| Materials | exactly 10 distinct; ≥3490 livery, ≥5365 composite, ≥5525 gunmetal, ≥1200 rubber, ≥1620 leather, ≥490 light, ≥460 glass, ≥2565 anodised, ≥1235 carbon, ≥1215 chrome faces | 10 slots; 3796 / 5832 / 6008 / 1304 / 1760 / 532 / 476 / 2788 / 1344 / 1320 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.234, 0.660, 1.112) m ± 0.01 | (2.2338, 0.6598, 1.1124), zmin 0 |
| Collider tris | ≤ 1990 | 1890 |
| Export | written, size > 0, removed after measuring | 3504016 bytes |

The collider is the convex hull of the whole bike. Its count is carried by
the two 72-segment shroud lips, which are the hull's outline in plan.

Every falsifier leaves the triangle count at 45796: they move, scale or
bend parts, never add or remove them.

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
| Skids: each of the 2 wear strips has its own `zmin` | within 1e-4 of 0 | 0, 0 |

Coplanar pairs are kept at zero by staggering parts, not by widening the
band. The two bosses and the eye on a joint are turned to three different
phases, so their bores never share a face plane; the two plates of a link
and the two cheeks of a clevis differ by 0.4 mm; hex heads are turned 15°,
so a row or a column of them never shares a flat; skin, gasket and panel
faces sit at least 1 mm apart, front and back.

### Fans, symmetry, stance, joints and shocks

| Axis | Declared | Measured |
| --- | --- | --- |
| Fans coaxial: each rotor hub and motor can (vertex mean) on its shroud's axis (vertex mean of the lathe); shrouds level (PCA); fan axes 1.60 m apart on the centreline | hub and can within 1 mm of the axis; tilt ≤ 0.3°; pitch 1.600 ± 0.002 m, axes within 1 mm of y = 0 | 0.001 mm; 0°; 1.60000 m |
| Blade-tip clearance: from the shroud axis, a level ray through each outer blade vertex to the shroud's inner wall, minus the vertex's radius; every blade overlaps its hub | 0.006–0.014 m | 0.0098 m on both fans; 0 unseated |
| Hull mirror symmetry: every fuselage vertex against its nearest vertex at (x, −y, z) | ≤ 0.5 mm | 0.000 mm |
| Size: fuselage length and width, saddle top | 1.033 × 0.344 m, 0.852 m, each ± 0.004 | 1.0330 × 0.3437, 0.8520 |
| Blade spacing: blades per rotor, and the angular gaps between them about the rotor hub's own axis | 7 per rotor; each gap 360/7° ± 0.3° | 7 and 7; worst 0.0001° |
| Stance: mass centre (shell volumes × density per material) inside the convex polygon of both wear strips' soles | ≥ 0.200 m inside every edge | 0.2515 (148.5 kg, centre at x −0.019) |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (322 shells) |
| Joints: 16, each one pin through three bushings; every bushing's centre on its pin's axis (PCA of the turned part), its axis parallel, its centre inside the pin's span | offset ≤ 0.3 mm, tilt ≤ 0.3° | 16 joints; 0.000 mm, 0.000° |
| Shocks: 4, the rod on its barrel's axis; the rod's length out of the gland, and its length still inside the barrel | offset ≤ 0.3 mm, tilt ≤ 0.3°; exposed 0.100–0.140 m; engaged ≥ 0.045 m | 0.000 mm, 0.010°; 0.1233 m; 0.065 m |

A ducted fan is only as good as its tip gap: the thrust a duct adds comes
from the blade tips running close to the wall. Too wide and it is an open
propeller in a ring; the blade touches the wall if the gap is zero. The
clearance budget measures that gap along the ray the tip travels on. The
coaxiality budget is its precondition, since a rotor off its shroud's axis
closes the gap on one side. Blade spacing is the rotor's balance, measured
about the rotor's own hub, so a rotor shifted off the shroud axis fails
coaxiality alone. A pinned joint binds if its pin is off its bushings'
axis, and a shock tops out if its rod is not engaged in the barrel, so the
gear carries the same two checks as the loader's rams
(`showcase/cargo-loader`). The densities are named constants (composite
shells 1600 kg/m³, the fuselage as a hollow monocoque with its internals
250, aluminium 2700, rubber and lights 1200, leather and foam 300, glass
2500, carbon 1600, chrome-plated steel 7800), and the volumes come from the
mesh.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. None moves the envelope: every run measured the
same outer AABB and triangle count as the default, and every budget
checked before the target stayed green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-skid` | both skids on the ground (the y+ shoe, strip, caps and bolts 4 mm up: its `zmin` 0.004, the other 0) | 16 |
| `--offset-hub` | fans coaxial (rear rotor 2.5 mm off its shroud's axis: 0.00250 m) | 17 |
| `--long-blades` | blade-tip clearance band (rear blades 12 mm longer: clearance −0.0022 m) | 18 |
| `--odd-hull` | hull mirror symmetry (a 4 mm sideways bow, zero at both ends: deviation 0.00799 m) | 19 |
| `--skew-blade` | blade spacing (one rear blade turned 4°: worst gap error 4.000°) | 20 |
| `--narrow-skids` | stance (shoes drawn in to ±0.150 m: margin 0.1715 m) | 21 |
| `--pop-lens` | one connected assembly (headlight lens 20 mm out of its housing: 2 components) | 22 |
| `--offset-pin` | joints (the near front link's foot pin 1.5 mm along x: 0.001500 m off its bushings' axis) | 24 |
| `--skew-rod` | shocks (the near rear rod 1.5 mm across its axis: 0.001500 m off its barrel's) | 25 |
| `--short-rod` | shocks (the near rear rod's inner end drawn out 45 mm: engaged 0.020 m, floor 0.045) | 25 |

The rear fan is the one `--offset-hub`, `--long-blades` and
`--skew-blade` change, because nothing inside a shroud sets the envelope.
`--offset-hub` leaves the tip clearance inside its band and the blade gaps
exact, so only coaxiality sees it. `--long-blades` pushes the tips 2.2 mm
into the wall, and every blade still sits in its hub. `--odd-hull` bows
the fuselage by `cos(πx / 2·0.515)`, so both ends stay inside their shroud
walls, and it bows everything laid on the skin with it: when only the
hull bowed, a panel met a hull facet at a shared plane and the run stopped
at hygiene (15) instead. `--float-skid` lifts one skid's own parts while
the other grounds the box; its first draft lifted the skid lug's pin too,
which slid a pin face onto a boss's plane and also stopped at 15, so the
lug and its pin now stay with the gear. `--pop-lens` first stopped at 15
because the lens (36 segments) and its housing (32) had faces within 0.6°
of parallel; both are now 32 segments turned half a step apart.
`--narrow-skids` keeps both strips on the ground and the envelope
unchanged; only the contact polygon shrinks. `--offset-pin` moves a pin
and no bushing; `--skew-rod` and `--short-rod` move a rod and no pin, so
each fails its own budget alone.

## Run

```bash
blender --background --python hover_bike.py --
blender --background --python hover_bike.py -- --skip-decimate
blender --background --python hover_bike.py -- --stray-vert
blender --background --python hover_bike.py -- --lift-z
blender --background --python hover_bike.py -- --float-skid
blender --background --python hover_bike.py -- --offset-hub
blender --background --python hover_bike.py -- --long-blades
blender --background --python hover_bike.py -- --odd-hull
blender --background --python hover_bike.py -- --skew-blade
blender --background --python hover_bike.py -- --narrow-skids
blender --background --python hover_bike.py -- --pop-lens
blender --background --python hover_bike.py -- --offset-pin
blender --background --python hover_bike.py -- --skew-rod
blender --background --python hover_bike.py -- --short-rod
blender --background --python hover_bike.py -- --output bike.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (−62°), so the nose, headlight
and front fan come toward the lens on the right, and the near side's gear,
panels and decal face it. The camera stands high enough to look into both
shrouds, where the blades and spinners show. The wall stands 2.8 m behind
the bike, and the warm wedge pools on it. Gunmetal and chrome carry a
studio reflection term (after `showcase/road-bicycle`), so the gear reads
as metal on the dark stage.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20`–`25` are file-local. `23` is the
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
| 16 | Not grounded: bounding box `zmin` off 0, or a skid's wear strip off the ground, or not 2 skids (`--lift-z`, `--float-skid`) |
| 17 | Fans not coaxial: a rotor hub or motor can off its shroud's axis, a shroud tilted, the fan pitch off, or not 2 shrouds, hubs and cans (`--offset-hub`) |
| 18 | Blade-tip clearance outside its band, or a blade not in its hub (`--long-blades`) |
| 19 | Hull mirror symmetry, or fuselage length, width or saddle height off (`--odd-hull`) |
| 20 | Blade spacing: not 7 blades per rotor, or a gap off 360/7° (`--skew-blade`) |
| 21 | Stance: mass centre within 0.200 m of the skids' contact-polygon edge (`--narrow-skids`) |
| 22 | Assembly splits into more than one connected component (`--pop-lens`) |
| 23 | Asset-quality floor (render path only; remapped from 11) |
| 24 | Joints: not 16, a joint without one pin and three bushings, or a bushing off its pin's axis or span (`--offset-pin`) |
| 25 | Shocks: not 4, a rod off its barrel's axis, its exposed length outside 0.100–0.140 m, or engaged under 0.045 m (`--skew-rod`, `--short-rod`) |
