# Motor scooter

A showcase piece, not an example, and the third in the `vehicles`
category. It builds a procedural 1960s Italian step-through motor scooter
(no brand names or badges), parked upright on its centre stand:

- a pressed-steel body: a central tail lofted from superellipse sections,
  its steep front face rising from the floorboard to the saddle, its crown
  flat under the saddle and its tail sloping down over the rear wheel to
  the tail lamp;
- two bulbous side cowls sunk into the tail, narrower on the inboard side
  so the rear tyre clears them, each with a chrome belt trim; the right
  (engine-side) cowl carries six graduated pressed louvres;
- a floorboard as wide as the leg shield's foot, with seven rubber runner
  strips and chrome edge trims, pressed up into the leg shield and into the
  tail's front face through two radiused fillets, so floor, shield and body
  read as one pressing;
- a leg shield pressed as one panel: convex in plan (its edges swept
  0.075 m behind the centre at the foot and 0.135 m at the top, round the
  rider's shins), bulged forward at mid-height, its top edge arched up
  into the headset round the column, its foot standing 32 mm deep in the
  floorboard, rimmed in a rolled chrome trim;
- a horn cast on the leg shield's front, enclosing the steering column
  from the fork crown up into the headset, with a chrome horn grille;
- a single-sided front end: the steering column raked 26 degrees, a fork
  crown, a fork leg down the left of the wheel and forward to the link
  pivot, a trailing link to the axle, and a coil spring on a damper rod;
  a front mudguard, domed across and curled at its edges, with a chrome
  crest on its crown;
- a headset lofted across the bars: a headlamp (chrome bezel, domed lens)
  on its nose, a speedometer on its crown facing the rider, a chrome collar
  where the column enters, ribbed grips with chrome bar-end caps, levers
  and two round mirrors on stalks;
- a two-tone dual saddle: its underside follows the tail's crown a bite
  inside it, a cream top panel over oxblood sides, piping round the panel
  and an oxblood grab strap across it;
- two 10-inch split rims, each two pressed-steel halves with five nuts and
  a domed hub cap on the open side and a finned brake drum on the arm side,
  in block-tread tyres (a continuous centre rib between staggered shoulder
  blocks);
- under the right cowl, an alloy engine case carrying the rear drum, with a
  finned cylinder, a header pipe to a black silencer and a chrome tailpipe,
  and a kick-start lever with a rubber pedal; a rear brake pedal on the
  floorboard;
- a chrome luggage rack over the tail, a tail lamp on the tail's rear slope
  along the body's normal, and a blank alloy number plate on a bracket;
- a centre stand: one bent bar from foot to foot over a pivot in the body
  and the engine case, a brace, and two rubber feet flat on the ground.

The layout is solved from named constants. The steering axis is a line
through the ground a design trail (75 mm) ahead of the front axle, raked
26 degrees: the column, crown, headset, collar and horn cast are all placed
on it. The tyre's rings are placed so a ring points straight down, so the
centre rib's lowest vertices are exactly one tyre radius below the axle and
both tyres ground at the same height as the stand's feet. The tail's
section parameter is symmetric about its crown, so the body is its own
mirror image vertex for vertex.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 1.79 m from the mudguard's nose to the number plate,
0.73 m across the bar-end caps, 1.24 m to the mirror tops, with the
saddle's top at 0.807 m and a 1.20 m wheelbase. The body's tail is
0.862 m long. The origin is under the scooter's centre, so it lands on its
tyres and stand.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 44400–45700 | 45060 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 9 distinct; ≥6440 paint, ≥4350 chrome, ≥3250 rubber, ≥1030 oxblood vinyl, ≥265 cream vinyl, ≥495 glass, ≥170 tail lens, ≥3620 alloy, ≥2060 black enamel faces | 9 slots; 7156 / 4638 / 3608 / 1147 / 297 / 550 / 188 / 4020 / 2292 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.790, 0.730, 1.244) m ± 0.01 | (1.7901, 0.7300, 1.2435), zmin 0 |
| Collider tris | ≤ 1850 | 1132 |
| Export | written, size > 0, removed after measuring | 3347780 / 3347780 / 3347776 bytes (4.5.11 / 5.1.2 / 5.2.1) |

The collider is the convex hull of the whole scooter; the mudguard, the
mirrors and the tail carry its outline.

Every falsifier leaves the triangle count at 45060 and the outer AABB
unchanged: they move, turn or bend parts, never add or remove them.

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
| Supports: each of the 2 tyres and 2 stand feet has its own `zmin` | within 1e-4 of 0 | 0, 0; 0, 0 |

Parts laid out in a row share planes by construction. The first draft
measured 525 coplanar cross-shell pairs: the seven runner strips' tops and
end chamfers, the five rim nuts against each other and against the hub
cap, the rack's cross bars' end caps, and the louvres' outer faces. The
strips and nuts are now staggered 0.3 mm each (the strips grow in length
as they rise, so their 45° end chamfers cannot re-align), the hub cap's
base sits below every nut, the cross bars' ends are staggered 0.4 mm, and
the louvres are graduated in length and laid along the cowl's own
latitude, so each slat's face is tangent to a different part of the cowl.

### Wheels, steering, symmetry, stance and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Wheel alignment: each tyre's axle (its least-variance PCA axis) horizontal, and the two axles parallel in plan | camber ≤ 0.3° each; toe ≤ 0.3° | 0.000°, 0.000°; 0.000° |
| Steering: the column's axis (principal PCA axis) meets the ground ahead of the front tyre's contact patch (its lowest ring of vertices), on its line | trail 0.055–0.090 m; ≤ 2 mm across | 0.0750 m (rake 26.000°); 0.000 mm |
| Body mirror symmetry: every vertex of the body shells (tail, both cowls, floorboard, both floor fillets, leg shield, horn cast, mudguard, headset) against its nearest vertex at (x, −y, z) | ≤ 0.5 mm | 0.000 mm |
| Size: the tail's length, the saddle's top | 0.862 m, 0.807 m, each ± 0.004 | 0.8624, 0.8068 |
| Wheelbase: the two tyres' centres (vertex means) apart in plan | 1.200 ± 0.004 m | 1.20000 m |
| Stance: mass centre (shell volumes × density per material) inside the convex polygon of both tyres' contact rings and both stand feet's soles | ≥ 0.080 m inside every edge | 0.1284 (101.6 kg, centre at x −0.278, y −0.036) |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (105 shells) |
| Shield seam: the leg shield's foot (its lowest ring) below the floorboard's top, both read off the mesh | 0.020–0.040 m deep | 0.0320 m |

The mirror audit **excludes the engine side by construction**: it reads
only the body shells, all built symmetric, and not the louvres (the only
paint shells under 0.15 m), the engine case, cylinder, exhaust,
kick-start, brake pedal or the single-sided fork and link, which a
scooter carries on one side only. The louvres, pressed into the right
cowl alone, are separate shells for that reason.

The seam budget is the leg shield's joint with the floor. A shield that
stops on or above the floor's top stands apart from it as a plank with
daylight under its foot; one sunk too deep punches out of the floor's
underside. The fillet sheets make the joint read as one pressing, but they
would bridge a lifted shield just as well, so the budget reads the shield
itself.

The steering axis and its trail are what keep a scooter going straight:
the axis must meet the ground ahead of the tyre's contact, on the
wheel's line, by a few centimetres. Too little trail and it wanders; too
much and it will not turn. The wheel-alignment budget is its partner: the
axles must be level and parallel, or the wheels fight each other. The
densities are named constants (the pressed-steel body shells as hollow
panels with their contents 300 kg/m³, chrome parts 2500, tyres and rubber
700, vinyl and foam 250, glass 2500, lens 1200, alloy castings and rims
2200, black-enamel steel parts 2600), and the volumes come from the mesh.
The engine on the right puts the mass centre 36 mm right of the
centreline; the stand's feet carry it.

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
| `--float-tyre` | both tyres and both stand feet on the ground (rear wheel 4 mm up: its `zmin` 0.00400, the rest 0) | 16 |
| `--toe-wheel` | wheel alignment (front wheel steered 2.5° about its own vertical: toe 2.5000°) | 17 |
| `--steep-head` | steering trail (column turned 6° steeper about its crown: rake 20.000°, trail 0.01683 m) | 18 |
| `--odd-body` | body mirror symmetry (a 3.5 mm sideways bow in the tail, zero at both ends: deviation 0.00695 m) | 19 |
| `--short-wheelbase` | wheelbase band (rear wheel 15 mm forward: 1.18500 m) | 20 |
| `--narrow-stand` | stance (stand feet drawn in to ±0.060 m: margin 0.0424 m) | 21 |
| `--pop-speedo` | one connected assembly (speedometer 30 mm out of the headset: 2 components) | 22 |
| `--lift-shield` | shield seam (the shield's foot stood 4 mm above the floor's top: −0.00400 m) | 23 |

`--float-tyre` lifts the rear wheel while the front tyre and the stand
ground the box. `--toe-wheel` turns the front wheel about the vertical
through its axle, so its contact ring stays where it was and the trail
does not move; the rim, drum and nuts turn with the tyre and stay in the
link. `--steep-head` turns only the column, about its crown, so the
headset and horn cast stay put. `--odd-body` bows the tail by
`sin²(π s)` along its length, so both ends stay seated in the floorboard
and under the tail lamp; its first draft, a plain `sin` bow with the
luggage rack's rails riding past the tail's shoulder, laid one rail face
in the plane of a bowed tail face and exited 15. The rails now follow the
crown inside the shoulder, and the falsifier reaches 19. `--narrow-stand`
keeps both feet on the ground; the first draft drew them in to ±0.035 m,
where the two soles' faces came within the coplanar range of each other
and exited 15, so it stops at ±0.060 m. `--short-wheelbase` moves the rear
wheel inside the envelope; the plate and the mudguard still set the
length. `--pop-speedo` lifts a part held by one joint only: the
speedometer is seated in the headset and nothing else. Its first draft
moved it 15 mm, which left its base still inside the headset's crown; it
moves 30 mm. `--lift-shield` raises only the shield's foot, its top held,
so the fillets follow it and the assembly stays one piece; only the seam
budget sees the gap.

## Run

```bash
blender --background --python motor_scooter.py --
blender --background --python motor_scooter.py -- --skip-decimate
blender --background --python motor_scooter.py -- --stray-vert
blender --background --python motor_scooter.py -- --lift-z
blender --background --python motor_scooter.py -- --float-tyre
blender --background --python motor_scooter.py -- --toe-wheel
blender --background --python motor_scooter.py -- --steep-head
blender --background --python motor_scooter.py -- --odd-body
blender --background --python motor_scooter.py -- --short-wheelbase
blender --background --python motor_scooter.py -- --narrow-stand
blender --background --python motor_scooter.py -- --pop-speedo
blender --background --python motor_scooter.py -- --lift-shield
blender --background --python motor_scooter.py -- --output scooter.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (−58°), so the nose, the front
wheel's open face and the engine side come toward the lens: the louvres,
the silencer, the split rim's nuts and the fork. The wall stands 2.6 m
behind the scooter, and the warm wedge pools on it.

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
| 16 | Not grounded: bounding box `zmin` off 0, or a tyre or stand foot off the ground, or not 2 tyres and 2 feet (`--lift-z`, `--float-tyre`) |
| 17 | Wheel alignment: a tyre's axle tilted (camber) or the axles not parallel in plan (toe) (`--toe-wheel`) |
| 18 | Steering: not 1 column, trail outside its band, or the axis off the front contact's line (`--steep-head`) |
| 19 | Body mirror symmetry, or the tail's length or saddle height off (`--odd-body`) |
| 20 | Wheelbase outside its band (`--short-wheelbase`) |
| 21 | Stance: mass centre within 0.080 m of the support polygon's edge (`--narrow-stand`) |
| 22 | Assembly splits into more than one connected component (`--pop-speedo`) |
| 23 | Leg shield's foot outside its seat band in the floorboard (`--lift-shield`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
