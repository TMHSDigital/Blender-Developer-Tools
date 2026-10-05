# Cargo loader

A showcase piece, not an example, and the fourth in the `vehicles`
category. It builds a procedural sci-fi industrial cargo loader: a bipedal
powered-lift exoframe with an open cockpit, standing on its two feet and
holding a cargo crate off the ground in its forks. It is a generic
warehouse and starport machine, not a copy of any film prop, and carries no
brand names or badges.

- two broad, flat feet: a rubber sole a hair wider than the foot, a cast
  foot with a sloped top, thirteen staggered grip cleats, a rubber toe
  bumper round the front and a heel block;
- two hydraulic legs, each a shin and a thigh lofted as tapered box
  sections, pinned at the ankle, knee and hip. The knee leads: the stance
  is a crouch, bent 42 degrees at the knee. A hazard-striped guard on each
  shin's front and a steel cover plate on each thigh's outer face;
- every joint is a clevis: two lug plates with bushings on one member (or
  on the foot, the pelvis or the shoulder yoke) straddle an eye bushing on
  the next, and a chrome pin runs through all three, its heads biting the
  outer bushings' faces. The pin shows in the gap between the eye and each
  lug;
- eight hydraulic rams: a hip ram in front of each thigh, a knee ram
  behind it, a shoulder ram behind each upper arm and an elbow ram in front
  of it. Each is a dark steel cylinder (a stem through its lug gap, a
  collared barrel and a gland) with a chromed rod, a pinned clevis bracket
  at each end, and a port boss with a rubber hose into the member it pushes
  from;
- a pelvis block with a hazard band across its front, steel side panels,
  a cleated footplate and a hydraulic tank slung beneath it between the
  hips;
- two arms hung outboard of the cockpit from shoulder yokes on towers,
  each tower with a louvred vent and a steel side panel; an upper arm with
  a steel cover plate, a forearm carrying two hydraulic lines along its
  outer face, and a wrist clevis into a fork carriage: a plate with a
  hazard-striped face and a forged L-tine, its shank up the plate and its
  blade forward under the crate;
- an open cockpit: a roll cage of two bent side frames, cross tubes, side
  rails and a grab bar on collars, a roof plate with an amber beacon in a
  wire guard, two work lights in bezels on brackets, a bucket seat with a
  headrest and a steel shell, a four-point harness over the backrest to a
  chrome buckle, and two armrest consoles with ribbed joystick grips;
- behind the seat, a power pack: a slatted rear grille, nine cooling fins
  and a hazard band down each side, two exhaust stacks with rain caps,
  carry handles, and rubber cable looms to both shoulder yokes and into the
  pelvis;
- a corrugated cargo crate (one loop of pressed ribs round all four
  sides) on a steel base, under a painted lid with lifting eyes, with steel
  corner posts and castings and a hazard label, resting on both tines.

The pose is solved from named joint stations in the side view (ankle,
knee, hip, shoulder, elbow, wrist), mirrored across the centreline. Every
member is lofted between two stations; every ram runs pin to pin between
two brackets whose standoff is read off the member's own section at that
station, and its gland sits at a fixed fraction of that length, so the
exposed rod is whatever the pose leaves.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 2.97 m to the top of the beacon, 1.69 m across the pin heads
of the arm joints, 2.83 m from the power pack's grille to the tine tips. The crate is 0.78 × 1.12 × 0.62 m, its base 1.00 m off the ground.
The origin is under the loader's centre, so it lands on its soles.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 44000–45000 | 44600 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2190 |
| Materials | exactly 10 distinct; ≥2550 paint, ≥560 hazard, ≥2900 chrome, ≥14300 steel, ≥2550 rubber, ≥440 seat vinyl, ≥590 harness webbing, ≥235 beacon, ≥140 work-light, ≥480 crate paint faces | 10 slots; 2736 / 608 / 3128 / 15328 / 2740 / 480 / 640 / 256 / 152 / 516 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.827, 1.689, 2.974) m ± 0.01 | (2.8272, 1.6890, 2.9740), zmin 0 |
| Collider tris | ≤ 760 | 532 |
| Export | written, size > 0, removed after measuring | 3450636 / 3450636 / 3450628 bytes (4.5.11 / 5.1.2 / 5.2.1) |

The collider is the convex hull of the whole loader; the power pack, the
beacon, the shoulder pins and the tine tips carry its outline.

Every falsifier leaves the triangle count at 44600 and the outer AABB
unchanged: they move, turn or reweigh parts, never add or remove them.

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
| Supports: each of the 2 soles has its own `zmin` | within 1e-4 of 0 | 0, 0 |

Parts set out in a row share planes by construction. The first draft
measured 1185 coplanar cross-shell pairs: the foot cleats' buried bottom
caps (all on one plane inside the foot), the beacon's top cap standing on
the lens's top, and the crate's corner posts starting on the wall loft's
bottom cap. Later drafts found the cage collars' bottoms on the tubes' end
caps, the pack fins' buried inner faces on one plane, and each crate post
against its lower corner casting (two faces per post; the casting moved
0.6 mm). Every one was fixed by
staggering the part (0.3–0.6 mm steps, or a bite past the host's cap),
never by widening a band.

### Joints, rams, crate, soles, stance and assembly

Each part the audits read is found by a face attribute (`Role`, `Unit`)
stamped at build time: pin, bushing, ram cylinder, ram rod, sole, tine,
crate base. The tag only says which shell is which; every value below is
read off that shell's vertices or faces.

| Axis | Declared | Measured |
| --- | --- | --- |
| Clevis joints: every pin's axis (a turned part's axis is the eigenvector whose eigenvalue stands apart from its equal radial pair) through each of its three bushings' centres, and parallel to theirs; each bushing inside the pin's span | 28 joints × 1 pin + 3 bushings; offset ≤ 0.3 mm, tilt ≤ 0.3° | 28; 0.000 mm, 0.000° |
| Crate on the tines: each tine's blade top against the crate base's underside, a ray down onto the tine and a ray up into the base at stations every 10 mm along the tine's centre line (20 mm off the base's chamfered rim) | 2 tines, every station's bite 0.0010–0.0040 m; each tine under the base for ≥ 0.50 m | 0.0020–0.0020 m both; 0.74 m both |
| Soles level: each sole's bottom faces (normal z < −0.9) | height spread ≤ 0.5 mm, plane tilt ≤ 0.2° | 0.000 mm, 0.000° both |
| Rams coaxial: each rod's axis on its cylinder's axis | 8 rams; rod centre ≤ 0.3 mm off, tilt ≤ 0.3° | 8; 0.000 mm, 0.0096° |
| Ram stroke: each rod's length past the gland face, and still inside the barrel, along the cylinder's axis | exposed 0.080–0.340 m; engaged ≥ 0.040 m | 0.1591–0.2858 m; 0.060 m |
| Stance: mass centre of loader and crate together (shell volumes × density per material) inside the convex polygon of both soles' contact rings | ≥ 0.200 m inside every edge | 0.4473 (2380.6 kg, 457.3 kg of it cargo; centre at x 0.252, y 0.000, z 1.515) |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (414 shells) |

The crate budget reads the faces, not the corners. The blade has vertices
only at its root and tip, and its tip now stands past the crate's front, so
a test that took the highest tine vertex under the base would find none or
the root's corner. The stations sample the tine's top face and the base's
underside where they meet, and the chamfered rim is left out because the
base's underside rises into it. The band's floor is a bite, not a touch: a
crate resting a hair above its tines passes a gap test and hovers.

The ram budget is two readings along one axis. The exposed rod is how far
the rod reaches past the gland face; below the floor the rod eye is
crushed against the gland (the ram has bottomed out), above the ceiling
the piston is near the end of its travel. The engaged length is how much
rod is still in the barrel, so a rod cannot be drawn out of its cylinder.
Densities are named constants (painted frame, pack and pelvis as hollow
panels with their contents 900 kg/m³, chrome 7800, gunmetal steel 4500,
rubber 1100, seat foam 150, webbing 300, lenses 1200 and 1500, the loaded
crate 450), and the volumes come from the mesh. The crate's centre is held
1.42 m ahead of the ankles; the power pack behind the seat counterweighs
it.

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
| `--float-foot` | both soles on the ground (left sole 5 mm up into its foot: `zmin` 0.00500, the right 0) | 16 |
| `--offset-pin` | clevis pins coaxial with their bushings (left knee pin 2.5 mm forward: 0.002500 m off) | 17 |
| `--lift-crate` | crate resting on both tines (crate 6 mm up: bites −0.0040 m on both) | 18 |
| `--tilt-sole` | soles level (left sole turned 0.6° about its toe edge: spread 0.012545 m, tilt 0.600°) | 19 |
| `--skew-rod` | rams coaxial (left hip ram's rod turned 1° about its eye: tilt 1.0000°, 0.002184 m off) | 20 |
| `--bottom-ram` | ram stroke (left knee ram's barrel run up to 40 mm short of the rod eye: exposed 0.0440 m) | 21 |
| `--overload` | stance (the crate 14 times as dense: 6401.9 kg of cargo, margin −0.3853 m) | 22 |
| `--loose-light` | one connected assembly (left work light 60 mm out along its aim, off its bracket: 2 components) | 23 |

`--float-foot` lifts only the left sole, into its foot, so the foot stays
on its sole and the right sole grounds the box. `--tilt-sole` turns the
sole about its own front bottom edge, so the toe stays on the ground and
only the heel lifts; its contact shrinks to that edge, which drops the
stance margin to 0.2097, but the level budget is checked first.
`--offset-pin` moves one pin across its three bushings, inside them, and
leaves them where they are. `--lift-crate` moves the whole crate, so every
station along both tines sees the same gap; the crate also loses contact
with the assembly, which is why the contact budget is checked before
connectivity. `--skew-rod` turns the rod about its own eye, so the eye end
stays pinned and only the barrel end wanders. `--bottom-ram` lengthens one
barrel, not the ram: both pins, the rod and the envelope stay put.
`--overload` changes a density,
not the mesh, which is the point: the machine that stands with 457 kg in
its forks tips with 6.4 t. `--loose-light` moves the lamp head 60 mm, well
clear of the bracket's end, and the head is held by that one bracket only.

## Run

```bash
blender --background --python cargo_loader.py --
blender --background --python cargo_loader.py -- --skip-decimate
blender --background --python cargo_loader.py -- --stray-vert
blender --background --python cargo_loader.py -- --lift-z
blender --background --python cargo_loader.py -- --float-foot
blender --background --python cargo_loader.py -- --offset-pin
blender --background --python cargo_loader.py -- --lift-crate
blender --background --python cargo_loader.py -- --tilt-sole
blender --background --python cargo_loader.py -- --skew-rod
blender --background --python cargo_loader.py -- --bottom-ram
blender --background --python cargo_loader.py -- --overload
blender --background --python cargo_loader.py -- --loose-light
blender --background --python cargo_loader.py -- --output loader.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (−62°), so the front and the right
side come toward the lens: the crate in its forks, the right leg's rams and
clevises, the shoulder yoke and vent, the cockpit through the cage, and the
power pack's fins and hazard band. The wall stands 5 m behind the loader,
and the warm wedge pools on it.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20`–`23` are file-local. `24` is the
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
| 16 | Not grounded: bounding box `zmin` off 0, or a sole off the ground, or not 2 soles (`--lift-z`, `--float-foot`) |
| 17 | Clevis joints: not 28 joints of one pin and three bushings, a bushing off its pin's axis or tilted to it, or outside its span (`--offset-pin`) |
| 18 | Crate on the tines: a station's bite outside its band, or a tine under the base for too short a run (`--lift-crate`) |
| 19 | Soles not level: a sole's bottom spread in height or its plane tilted (`--tilt-sole`) |
| 20 | Rams: not 8, or a rod off its cylinder's axis or tilted to it (`--skew-rod`) |
| 21 | Ram stroke: a rod's exposed length outside its band, or too little of it left in the barrel (`--bottom-ram`) |
| 22 | Stance: mass centre within 0.200 m of the soles' support polygon's edge (`--overload`) |
| 23 | Assembly splits into more than one connected component (`--loose-light`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
