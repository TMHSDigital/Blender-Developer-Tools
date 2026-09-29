# Farm tractor

A showcase piece, not an example, and the ninth in the `vehicles` category:
things that move. It builds a mid-century utility farm tractor (generic, no
marks, text or maker's livery) standing in the ruts of a muddy farmyard:

- the patch, 3.4 × 2.0 m of mud on an 85 mm slab with a rolled skirt: two
  ruts pressed in along the rear track with a compacted, level floor (the
  tractor's z origin), berms of squeezed-out mud either side, and a dip in
  the right rut between the wheels holding a puddle whose rim is buried in
  the dip's walls; the rear tyres' chevron bars are printed in the rut
  floors, apex to the rear;
- a cast-iron backbone: rear axle centre housing with its cover plate and
  hydraulic lift cover, trumpet housings with flanges and brake drums,
  half-shafts and hubs; gearbox with its top cover and lever turret; bell
  housing, block, head, rocker cover, sump and timing cover; a steering box;
- a pivoting front axle: the front support (bolster) with two arms back to
  the block and two lugs, the **pivot pin** through them and through the
  beam's boss in two flanged bushings; the beam, kingpin bosses, thrust
  washers, knuckles, kingpins, spindles, hubs and caps; steering arms and a
  tie rod on vertical pins;
- rear wheels: 1.240 m tyres whose carcass carries **44 chevron bars** (two
  staggered halves of 22), each rooted in the carcass and running from its
  apex over the centre line back round the tyre to the shoulder; 28 in
  drop-centre rims, dished pressed discs on eight welded clamp lugs, wheel
  nuts, **two cast-iron half-moon weights** per wheel with bolts and a cast
  grip, valve stems; front wheels: 0.690 m three-rib tyres on 19 in rims and
  ribbed pressed discs;
- the grille shell with eleven bars, the radiator core, top tank and filler
  cap, headlamps on brackets; the bonnet with side louvres and a zinc crown
  strip; the fuel tank lapping the bonnet with its filler neck and bayonet
  cap; the dash with two gauges, switch and choke;
- a vertical exhaust stack from a four-port manifold through a collar in
  the bonnet, a silencer barrel and a **rain cap** hinged open with its
  counterweight; an oil-bath air cleaner feeding a **pre-cleaner bowl**
  (zinc base, glass bowl, cap and wing nut) on a pipe through the bonnet; a
  fan and water pump, a dynamo on brackets and the fan belt round three
  pulleys, a starter, an oil filter, the intake manifold and hose;
- a steering wheel on a column raked 45°, a pan seat on a two-leaf spring,
  a gear lever in a boot, clutch and brake pedals, footplates with bare
  anti-slip strips and turned-up lips;
- rear mudguards on stays with a tail lamp and a work lamp; a three-point
  linkage: lower links on pinned brackets, lift arms on the cross-shaft,
  lift rods (the right one with a levelling box), the top link stowed on
  the drawbar's cheeks, the drawbar through the lower links' eyes, and a
  splined PTO stub under its shield.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: wheelbase 1.780 m, rear track 1.320 m (52 in) and front
track 1.220 m (48 in), tyre centre to tyre centre; rear tyres 1.240 m over
the lugs (11.2-28 class), fronts 0.690 m (4.00-19 class); the rain cap
1.73 m over the slab's underside. The origin is under the patch at the
slab's underside.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file. Shells are found by a `part` face attribute; every measured
value is read from their vertices.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 121000–123600 | 122272 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2198 |
| Materials | exactly 12 distinct; ≥8080 body paint, ≥8590 wheel paint, ≥14290 rubber, ≥6890 cast iron, ≥10000 steel, ≥2350 zinc, ≥2660 black enamel, ≥790 glass, ≥1060 exhaust, ≥50 radiator core, ≥11660 soil, ≥128 water faces | 12 slots; 8792 / 9344 / 15536 / 7498 / 10876 / 2556 / 2900 / 868 / 1160 / 56 / 12676 / 140 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (3.5839, 2.0869, 1.7330) m ± 0.01, read off the vertices | (3.5839, 2.0869, 1.7330), zmin 0 |
| Collider tris | ≤ 1040 | 944 |
| Export | written, size > 0, removed after measuring | 9352088 bytes |

Every falsifier leaves the triangle count at 122272 and the envelope at
(3.5839, 2.0869, 1.7330): they move parts, never add or remove them.

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. Construction uses no RNG; two default runs print
identical measurements, and 4.5.11 and 5.1.2 print the same measurements
as 5.2.1 (LOD2 decimates to 26898 triangles there against 26874, ratio
0.2200 against 0.2198, and the export differs by 8 bytes).

### Hygiene and grounding

| Axis | Declared | Measured |
| --- | --- | --- |
| Non-manifold edges | 0 | 0 |
| Loose verts / edges | 0 / 0 | 0 / 0 |
| Doubles merged at 1e-5 | 0 | 0 |
| Zero-area faces | 0 | 0 |
| N-gons | 0 | 0 |
| Coplanar cross-shell face pairs (KD range 0.05 m, plane ε 1e-4) | 0 | 0 |
| Grounded: `zmin` | within 1e-4 of 0 | 0.0000 |
| Tyres: each tyre's deepest vertex (carcass and bars) under the mud, read by a ray down onto the soil shell | 4 tyres; 18–45 mm | 4; 28.9–30.1 mm |

The first draft measured 2471 coplanar pairs, none of them in a part:
eleven identical grille bars side by side shared their faces' planes (each
bar now steps back and down from the centre out, so neighbours differ and
mirrored bars still match); three equal louvres shared their long faces
(each now leans out at the top, so a level offset changes its plane, and
is a step longer than the last); clamp-lug bolt heads on the lugs' faces;
a weight bolt's head on the plane of the weight's cast grip; wheel nuts on
the hub's end cap; the head's front on the bell housing's flange; exhaust
port flanges of one size in a row; two spring bolts' undersides; a stalk's
end on its collar; the steering shaft's end on its hub's. Stepping the
bars to stop the pairs first broke the bonnet's mirror by 4.7 mm; the step
now counts from the centre out.

### Joints, seats, size, tread, stance and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Joint fit: each front hub against its spindle and each rear hub against its half-shaft (axis of revolution and centre against the host's principal axis); the pivot pin against both bushings | 4 hubs, 2 bushings; ≤ 0.3 mm off, ≤ 0.3° | 4, 2; 0.0 mm, 0.0° |
| Joint fit: every link eye on a pin (lower links, lift arms, lift rods, top link, tie rod): centre on the pin's axis, axis along it, the pin past both faces | 14 eyes; ≤ 0.5 mm, ≤ 1.0°, ≥ 2 mm past | 14; 0.0 mm, 0.0°, ≥ 8.5 mm |
| Tyre seat: per tyre, per angular segment, the bead vertices against the rim's bead seat (a ray toward the axis along each vertex's own radial) | 4 tyres, each on a rim; 0.4–2.0 mm | 0.683–0.962 mm |
| Lugs: each bar's deepest root vertex inside the carcass (a ray onto the carcass along the vertex's radial), its crown proud of it | 88 bars; 2.0–6.0 mm; ≥ 20 mm proud | 88; 3.932–3.997 mm; 28.311 mm |
| Mirror: every body-paint vertex against its partner across the centre plane between the half-shafts (KD-tree) | ≤ 0.5 mm | 0.0001 mm |
| Wheels: front and rear carcasses paired, centres and extents compared | ≤ 0.5 mm | 0.0001 mm |
| Size: wheelbase and both tracks from the carcasses' centres | 1.780 / 1.220 / 1.320 m ± 4 mm | 1.7800 / 1.2200 / 1.3200 |
| Size: each rear tyre's diameter, twice its farthest vertex from the rim's axis | 1.240 m ± 6 mm | 1.2400, 1.2400 |
| Tread pitch: per rear tyre and half, the bars' angles round the axle | every gap within 0.25° of 360/22 | 0.0000° |
| Handing: every rear bar's apex ahead of its shoulder end in forward rolling (about +Y, the same for both wheels) | ≥ 5° | 10.886° |
| Stance: mass centre (per-shell volume × a per-material density) inside the support **triangle**: the two rear contact patches and the front-axle pivot | ≥ 0.330 m (a quarter of the rear track) | 0.4151 m (1541 kg) |
| One connected assembly (union of shells whose BVH trees overlap, the patch included) | 1 component | 1 (505 shells) |

The support is a triangle, not the four tyres' rectangle: the front axle
oscillates on its pin, so sideways the front wheels carry nothing until the
axle reaches its stop. That is the tractor's real stability story — a mass
centre that moves toward the narrow front of the triangle, or a pivot that
moves off the centre line, tips it.

A mirror image of a rear tyre across the tractor's centre plane does not
reverse its chevrons (the bars are symmetric about the tyre's own
mid-plane); what reverses them is building the tread about the wheel's own
outboard axis, which on the right-hand wheel turns the tyre round. Both
tyres are built about the world's +Y, the axis forward travel turns them
about, and the handing budget reads each bar's apex and shoulder angles
about that same axis. Densities are effective: castings, tanks and tyres
are modelled solid but are hollow.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1,
4.5.11 and 5.1.2 and exited its declared code, with the triangle count and
envelope unchanged and every budget checked before the target green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-tyre` | every tyre pressed into the mud (the left front lifted 40 mm: −9.889 mm) | 16 |
| `--cock-hub` | hubs coaxial (the left rear hub 1.5 mm off its half-shaft: 1.5 mm) | 17 |
| `--cant-pin` | pivot pin coaxial with its bushings (the pin turned 1.5° in plan: 1.894 mm, 1.5°) | 17 |
| `--unpin-link` | link eyes on their pins (the top link 8 mm short: its rear eye 8.0 mm off the stowage pin) | 17 |
| `--sink-tyre` | tyre bead seat (the right rear bead 3 mm into its seat: 2.762 mm) | 18 |
| `--float-lugs` | bars rooted in the carcass (the left rear bars lifted 7 mm: −3.068 mm) | 18 |
| `--skew-wheel` | rear wheels mirrored (the left rear wheel 6 mm aft of its hub: 6.000 mm) | 19 |
| `--wide-track` | rear track at its stated size (each rear wheel 4 mm out: 1.3280 m) | 19 |
| `--tall-lugs` | rear tyre diameter at its stated size (bars 8 mm taller: 1.256 m) | 19 |
| `--odd-fender` | body mirror symmetry (the left mudguard bowed 3 mm out: 3.000 mm) | 19 |
| `--bunch-lugs` | even bar pitch (every fourth bar of one right rear half turned 2°: 2.000°) | 20 |
| `--reverse-lugs` | chevron handing (the right rear tread built about its outboard axis: −10.886°) | 21 |
| `--offset-pivot` | stance (the pivot pin and bushings 0.30 m to the right: 0.3074 m) | 22 |
| `--loose-lamp` | one connected assembly (the tail lamp 4 mm off its mudguard: 2 components, 4 and 501 shells) | 23 |

`--float-tyre` lifts the carcass alone while the rest of the tractor and
the slab still ground the box. `--float-lugs` also makes the tyre 14 mm
taller, but the bars' roots are read (18) before the diameter (19);
`--tall-lugs` keeps the roots and changes only the crowns. `--skew-wheel`
and `--wide-track` move the wheel (tyre, bars, rim, disc, weights) and leave
the hub on its half-shaft, so the joint budget stays green. `--cant-pin`
first turned the bushings with the pin, which stayed coaxial and exited 0;
it now turns the pin alone. `--loose-lamp` first exited 0 because the
lamp's bezel rested on the skirt; the lamp now stands clear on its bracket,
which is its only contact.

## Run

```bash
blender --background --python farm_tractor.py --
blender --background --python farm_tractor.py -- --skip-decimate
blender --background --python farm_tractor.py -- --stray-vert
blender --background --python farm_tractor.py -- --lift-z
blender --background --python farm_tractor.py -- --float-tyre
blender --background --python farm_tractor.py -- --cock-hub
blender --background --python farm_tractor.py -- --cant-pin
blender --background --python farm_tractor.py -- --unpin-link
blender --background --python farm_tractor.py -- --sink-tyre
blender --background --python farm_tractor.py -- --float-lugs
blender --background --python farm_tractor.py -- --skew-wheel
blender --background --python farm_tractor.py -- --wide-track
blender --background --python farm_tractor.py -- --tall-lugs
blender --background --python farm_tractor.py -- --odd-fender
blender --background --python farm_tractor.py -- --bunch-lugs
blender --background --python farm_tractor.py -- --reverse-lugs
blender --background --python farm_tractor.py -- --offset-pivot
blender --background --python farm_tractor.py -- --loose-lamp
blender --background --python farm_tractor.py -- --output tractor.png
```

Smoke passes no flags.

The hero looks from the front right and above, so the grille, headlamp,
bonnet, exhaust stack and pre-cleaner lead, the engine's right side
(manifold, dynamo, starter, filter) shows under the bonnet, the right rear
wheel with its weights stands behind, and the puddle lies in the rut
between the wheels. The wall stands 6 m behind the patch and the warm wedge
pools on it. Default stage; no deviation.

## Shading

Tyres, lathed parts, sheet metal and the seat are smooth-shaded; chamfers,
bars, lugs and every material boundary stay crisp through sharp edges above
35°. Every part carries a `PartTone` face attribute, so the four tyres and
the two weight halves differ, and the lamp glass picks clear or red from
it. An `EdgeWear` point attribute is 1 on square edges (a sheet's rolled
rim, a plate's edge) and 0 on smooth surfaces and 45° chamfers; the paint
chips through to red-oxide primer and bare steel in patches along those
edges, and every part that carries wear has a vertex ring a few millimetres
in from its square edges, so the wear stays on the edge rather than being
interpolated across a face (the first draft's grille shell carried a rust
band a quarter of its length wide). The paint also fades where it faces the
sky, darkens with grime toward the ground, takes sparse scuffs and rust
streaks, and is splashed with mud rising from the rut. Cast iron is
near-black and rough, not chrome; zinc is kept to the caps, bezels, lamp
housings and the bonnet strip. The mud is wet and glossy only on the
up-facing rut floors.

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
| 5 | Material count ≠ 12 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0, a tyre out of its sink band, or not 4 tyres (`--lift-z`, `--float-tyre`) |
| 17 | Joint fit: a hub off its spindle or half-shaft, the pivot pin off its bushings, a link eye off its pin, or a part missing (`--cock-hub`, `--cant-pin`, `--unpin-link`) |
| 18 | Seat: a tyre bead out of its seat band, a bar's root out of its band or its crown not proud, or a part missing (`--sink-tyre`, `--float-lugs`) |
| 19 | Mirror and size: body or wheels not mirrored, wheelbase, a track or a rear tyre's diameter off (`--skew-wheel`, `--wide-track`, `--tall-lugs`, `--odd-fender`) |
| 20 | Tread pitch: a bar out of step round its tyre (`--bunch-lugs`) |
| 21 | Chevron handing: a bar's apex not ahead of its shoulder in forward rolling (`--reverse-lugs`) |
| 22 | Stance: the mass centre too near an edge of the support triangle (`--offset-pivot`) |
| 23 | Assembly splits into more than one connected component (`--loose-lamp`) |
| 24 | Asset-quality floor (render path only; remapped from 11) |
