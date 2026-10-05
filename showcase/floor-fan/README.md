# Floor fan

A showcase piece, not an example, and the third in the `household`
category. It builds a procedural 1950s oscillating pedestal fan:

- a round cast base in two tiers with a chrome bead at the step, hollow
  underneath (a 9 mm cast wall) and standing on a rubber gasket;
- a rotary speed switch on the base's sloped top (chrome escutcheon,
  ribbed bakelite knob with a pointer, three detent studs) and an oval
  maker's badge in a chrome bezel on the riser;
- a telescoping column: an enamelled lower tube in a chrome ferrule, a
  knurled height-lock collar with a bakelite thumb screw, a chrome upper
  tube and a neck fitting;
- a strap yoke bent into a U under the head, with round eyes on the tilt
  pivot, a pivot bolt, a knurled bakelite tilt knob on one side and a
  chrome cap nut on the other;
- a motor housing with a ring of cooling slots, a hooped chrome trim band,
  pivot bosses, and a gearbox on its tail carrying the oscillation knob;
- a two-half wire guard: 24 radial spokes and 4 concentric rings in front,
  24 spokes and 3 rings behind, each half welded to its own rim ring, the
  two rims overlapping and held by six clips, a cream badge in a chrome
  bezel at the front centre and a mount ring at the rear;
- four broad brass blades, pitched, cambered and swept forward toward a
  rounded tip, on a hub with a hex spinner nut, on the motor shaft; and
- a cord that leaves a grommet in the base's rear riser, curls round the
  base over the floor and ends in a two-pin plug.

The head is placed from a named frame (`hw()`): it turns 28° on the column
(it is oscillating) and tilts 7° up about the pivot, 155 mm behind the
guard's rim plane. The yoke turns with the head but does not tilt. Every
part of the head — guard, rotor, housing, bosses — is built in head-local
coordinates, so the tilt and the turn move it as one.

The guard's two domes are closed-form: the front is
`y = y_rim + 0.066 (1 − (ρ/R)^2.6)`, flat across the middle and rolling
down onto the rim; the rear is deeper (`0.095`, exponent 3) to clear the
blades' pitch. A spoke follows its dome from inside the badge bezel (or
the rear mount ring) out to its rim ring and ends on the ring's
centreline. A ring lies on the dome at its radius, so it crosses every
spoke of its half.

Two things the coplanar budget forced:

- Three detent studs on the switch plate are one lathe translated in a
  plane, so their caps and facets shared planes (192 pairs). Each stud
  now stands 0.3 mm prouder, sinks 0.3 mm deeper and is turned 0.21 rad
  from the last.
- Neighbouring spokes' facets met on common planes near the badge, where
  the dome is nearly flat. Each wire's section is turned by its own
  amount (`0.618 k` rad, modulo a facet).

The two rim rings are not copies either: the rear ring is 1 mm smaller in
major radius, 0.3 mm thinner and has its tube turned half a facet.

The cord is a Catmull-Rom spline clamped to rest on the floor. The plug's
chamfer pass set its sole 1.2 mm below the floor, which grounded the
whole piece on the plug and lifted the gasket; the plug is set back down
after the chamfer, so the gasket and plug both reach Z = 0.

Shading follows what each part is. Turned and swept stock is
smooth-shaded; the thin six-sided wire smooths across its facets (62°),
everything else stays crisp above 35° and at every material boundary. The
enamel is a muted sage under a clear coat, the brass and chrome rough
enough to catch the key rather than mirror a black stage.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a 0.40 m base, a guard 0.452 m across its rim, and 1.23 m
overall. The outer AABB is 0.761 × 0.704 × 1.229 m. The guard's rim sets
the top, the guard and the cord's loop set the plan. The origin is under
the base centre, so the fan drops onto a floor by its gasket.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 40600–41900 | 41460 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 6 distinct; ≥4350 enamel, ≥12800 chrome, ≥540 brass, ≥1120 rubber, ≥740 bakelite, ≥400 badge faces | 6 slots; 4732 / 13960 / 584 / 1216 / 810 / 440 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.761, 0.704, 1.230) m ± 0.01 | (0.7614, 0.7039, 1.2286), zmin 0 |
| Collider tris | ≤ 2200 | 1560 |
| Export | written, size > 0, removed after measuring | 3119064 / 3119064 / 3119060 bytes (4.5.11 / 5.1.2 / 5.2.1) |

No falsifier changes the topology, so every one of them measures the
default's 41460 triangles and the default's AABB.

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
| Grounded: `zmin`, and the gasket's own `zmin` | within 1e-4 of 0 | 0.0000 / 0.0000 |

### Guard, rotor, column, stance and assembly

The guard axis is read off the mesh: the centre and normal (smallest PCA
axis) of the front rim ring, the only chrome shells 0.4 m across being
the two rims. Every other head part is classified by its lateral radius
about that axis.

| Axis | Declared | Measured |
| --- | --- | --- |
| Coaxial: the rear rim's normal against the front's, and the centre of the rear rim, hub, spinner, shaft, badge bezel, rear mount and motor housing off the guard axis | ≤ 0.2°; ≤ 0.0005 m; 7 parts found | 0.0078°; 0.000001 m; 7 |
| Guard wires seated: each spoke's nearest vertex to its own rim ring's centreline circle; each concentric ring crossing (BVH) every spoke of its half; each spoke's inner end in the badge bezel or rear mount | ≤ 0.0026 m; 24 + 24 spokes, 7 rings, 6 clips; 0 loose | 0.000743 m; 24 per ring on all 7; 0 |
| Column plumb: both tubes' PCA axes against Z, and each axis through the base's centre at the boss top | ≤ 0.2°; ≤ 0.001 m | 0.0000°; 0.000000 m |
| Size: guard rim and base diameters | 0.452 / 0.400 m ± 0.004 | 0.4522 / 0.4000 |
| Blade clearance: rim rings' inner face minus the farthest blade vertex, about the guard axis; nearest blade vertex to any guard wire | 0.012–0.030 m; ≥ 0.006 m; 4 blades, each seated in the hub | 0.01945 m; 0.01403 m; 4, 0 unseated |
| Blade spacing: angles of the blades about the hub's own axis | every gap 90° ± 0.3° | worst 0.0002° |
| Stance: the steepest incline the fan stands on before its mass centre (shell volumes × densities) passes the gasket's edge | ≥ 16° | 19.06° (28.43 kg; base 12.66 kg; centre 0.510 m up, 0.176 m inside the edge) |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (109 shells) |

A fan on a pole is a real tip risk: its head is a third of its mass and
sits a metre up. The stance budget measures exactly that. The densities
are named constants — cast iron and steel 7850, brass 8500, rubber 1200,
bakelite 1400, the badges 2500 — with two per-shell overrides where the
mesh is solid but the part is not: the motor housing (700, a pressed
shell round windings and air) and the two column tubes (1100, drawn tube
rather than bar).

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. None moves the envelope: every run measured the
same triangle count and outer AABB as the default, and every budget
checked before its own stayed green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--offset-hub` | rotor coaxial with the guard (hub, spinner and blades moved 3 mm off the axis: 0.003000 m) | 17 |
| `--short-spoke` | guard wires seated (one front spoke stopped 12 mm short of its rim ring: 0.014906 m) | 18 |
| `--lean-column` | column plumb and coaxial (lower tube leaning 1° on its foot: 1.0000°, 0.001501 m off the base's axis) | 19 |
| `--long-blades` | blade-tip clearance band (tips 12 mm longer: 0.00745 m) | 20 |
| `--skew-blade` | equal blade spacing (one blade turned 5°: 4.9998°) | 21 |
| `--hollow-base` | stance (base pressed from 1.2 mm sheet: 18.64 kg, base 2.87 kg, centre 0.752 m up: 12.39°) | 22 |
| `--loose-spinner` | one connected assembly (spinner nut backed 6 mm off the hub: 2 components) | 23 |

`--offset-hub` leaves the tip clearance in band (0.01648 m) and the blades
evenly spaced about their own hub, so only the coaxial budget sees it.
`--long-blades` still leaves every tip 7.4 mm clear of the nearest wire,
so the band's floor is what fails. `--lean-column` tilts only the lower
tube; the upper tube, the collar and the head stay put, and the tube stays
inside the base's boss. `--hollow-base` keeps the outer casting, so the
envelope and footprint are unchanged and only the mass moves.

## Run

```bash
blender --background --python floor_fan.py --
blender --background --python floor_fan.py -- --skip-decimate
blender --background --python floor_fan.py -- --stray-vert
blender --background --python floor_fan.py -- --lift-z
blender --background --python floor_fan.py -- --offset-hub
blender --background --python floor_fan.py -- --short-spoke
blender --background --python floor_fan.py -- --lean-column
blender --background --python floor_fan.py -- --long-blades
blender --background --python floor_fan.py -- --skew-blade
blender --background --python floor_fan.py -- --hollow-base
blender --background --python floor_fan.py -- --loose-spinner
blender --background --python floor_fan.py -- --output fan.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (164°). The base's switch and
badge then face the camera, while the head, turned 28° on the column,
shows the guard three-quarter with the motor housing, yoke and tilt knob
in profile. The cord's loop lies in the foreground. The wall stands 3 m
behind the fan and the warm wedge pools on it behind the head.

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
| 5 | Material count ≠ 6 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin`, or the gasket's, off 0 |
| 17 | Coaxial: a turned head part off the guard axis, or the rims not parallel (`--offset-hub`) |
| 18 | Guard wires: a spoke's end off its rim ring, a ring not crossing every spoke of its half, a spoke loose at its inner end, or not 24 + 24 spokes, 7 rings and 6 clips (`--short-spoke`) |
| 19 | Column plumb and size: a tube tilted or off the base's axis, or the guard or base diameter off (`--lean-column`) |
| 20 | Blade clearance: tip clearance outside its band, a blade too near a wire, a blade not seated in the hub, or not 4 blades (`--long-blades`) |
| 21 | Blade spacing: a gap off 90° (`--skew-blade`) |
| 22 | Stance: the fan tips on an incline under 16° (`--hollow-base`) |
| 23 | Assembly splits into more than one connected component (`--loose-spinner`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
