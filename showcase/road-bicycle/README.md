# Road bicycle

A showcase piece, not an example, and the fifth in the `vehicles`
category. It builds a procedural 1970s lugged-steel road bicycle (no brand
names, badges with text or decals), standing on its side kickstand and
leaning 5° onto it:

- a 56 cm diamond frame of round tubes (top tube 25.4 mm, down and seat
  tubes 28.6 mm, head tube 31.7 mm) joined in chromed lugs: every socket is
  a sleeve round its tube, spear-pointed on both flanks so the points show
  in side view and feathered at the edge, at the head tube, the seat
  cluster and the bottom-bracket shell;
- tapered chain stays and seat stays with chromed tips, chrome caps where
  the seat stays meet the seat lug, a brake bridge and a chain-stay bridge;
  a seat-lug collar and binder bolt; a blank oval head badge curved round
  the head tube;
- a fork with a chromed sloping crown, chromed blade sockets and socks,
  blades raked forward to their dropouts; a headset with cups, washer and a
  knurled locknut;
- dropouts in each wheel's plane, each with an eye round the axle, the
  drive-side rear one with its derailleur hanger;
- two 700c wheels: box-section rims, 36 spokes each laced three-cross from
  both flanges of a small-flange hub (every spoke runs from a flange hole to
  a nipple through the rim's inner wall), a quick-release skewer with its
  cam lever and cone nut, and tyres with a black file-tread crown over tan
  gum sidewalls; the rear wheel is dished to centre its rim;
- a 52/42 crankset: five spider arms, chainring bolts, cotterless arms at 3
  and 9 o'clock, quill pedals with toothed cages, chrome toe clips and
  leather straps;
- a six-speed freewheel (14–24) and a roller chain of 112 individual links
  — rollers with pin heads through the outer plates, alternating inner and
  outer plate pairs — wrapped over the 52 and the 17, and through the rear
  derailleur's two jockey wheels in an S;
- a rear derailleur (hanger and cage-pivot knuckles, two parallelogram
  links, a slim cage) and a front derailleur (clamp, body, cage straddling
  the chain over the big ring); down-tube friction shifters with their
  cables run under the down tube and the shell;
- side-pull calipers front and rear, their pads standing 0.9 mm off the
  rims' braking faces; brake levers under tan gum hoods on cotton-taped
  drop bars (a helical wrap, black finishing tape, bar-end plugs); housings
  out of the hood tops, the rear brake cable bare along the top tube
  through three clips;
- a quill stem, a leather racing saddle on steel rails with a chrome nose
  piece, cantle plate and rivets, on an alloy seat post;
- a bottle in a chrome wire cage bolted to two bosses on the down tube;
- a side kickstand clamped behind the bottom bracket, its rubber foot on
  the ground.

The layout is solved from named constants: a 415 mm chain stay with a
70 mm bottom-bracket drop, a 73.5° seat tube, a 73° head tube with 45 mm
of fork offset, and a 560 mm top tube. The front axle is placed so the
steering axis passes one fork offset behind it, which gives the design
trail (55 mm). The chain's path is solved from the four circles it wraps
(ring, cog, and the two jockeys, each wrapped on its own side), and the
derailleur cage swings until the loop is a whole, even number of pitches.
The bike is built upright and leaned about the line through both tyres'
contacts; the kickstand is built after the lean, its sole on the plane the
tyres touch.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 1.67 m from tyre to tyre, a 1.000 m wheelbase, 0.44 m
across the bars and pedals, 1.00 m to the saddle's top. The seat tube is
0.580 m from the bottom-bracket centre to its top. The origin is under the
bike, so it lands on its tyres and stand.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 45600–46600 | 46092 |
| LOD1 ratio | 0.32–0.62 of base | 0.4995 |
| LOD2 ratio | 0.10–0.35 of base | 0.2198 |
| Materials | exactly 10 distinct; ≥940 paint, ≥5650 chrome, ≥6250 alloy, ≥7410 steel, ≥480 tread rubber, ≥850 gum, ≥320 leather, ≥970 tape, ≥1620 black, ≥158 bottle faces | 10 slots; 1048 / 6438 / 6950 / 8239 / 540 / 952 / 356 / 1080 / 1810 / 176 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.670, 0.438, 0.997) m ± 0.01 | (1.6698, 0.4376, 0.9969), zmin 0 |
| Collider tris | ≤ 970 | 880 |
| Export | written, size > 0, removed after measuring | 3598060 bytes |

Every falsifier leaves the triangle count at 46092: they move parts,
never add or remove them. `--lift-chain` keeps the default chain's link
count and lets the derailleur cage take up the longer loop. DECIMATE
COLLAPSE triangle counts are not identical across Blender series, so the
LOD gate is a ratio band, not an exact count. Bake pixels are stochastic,
so the bake gate is `has_data` plus operator `FINISHED`, not
byte-identity. Construction uses no RNG; two default runs print identical
measurements.

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
| Supports: each tyre and the stand foot has its own `zmin` | within 1e-4 of 0 | 0, 0; 0 |

The chain is where this budget is hardest: 112 links, 224 plates and 112
rollers within a hand's width of each other, every plate cap on a plane
parallel to every other. The first complete draft measured 7523 coplanar
cross-shell pairs. What fixed them, family by family:

- **Plate caps** are staggered in offset (0.12 mm steps, five levels) and
  in tilt about the plate's own axis (1.2° steps), chosen greedily so no
  two like plates within 75 mm share both.
- **A plate pair's edge faces** share their planes by construction (the
  two plates of a link are one outline at two depths), so the right-hand
  plate is 4.7 % shallower. Inner links taper forward and outer links back,
  so a straight run's edge faces never line up either.
- **Rollers** end in cones buried in the outer plates, each cone's height
  chosen so no roller within 60 mm has the same cone angle, and each
  roller turned a further step so their side faces never repeat.
- **Sprockets** (both rings, all six cogs, both jockeys) each carry a
  tiny draft of their own: the top face of each is scaled and turned a
  hair against the bottom, so every tooth wall leans out of the chain's
  plane by an angle no other part shares. Rollers are coned (the
  right-hand end 5 % narrower) and each plate family is inset across its
  thickness by its own amount for the same reason.
- **Mirrored hardware** — the two shifter bosses and knobs, the two brake
  shoes and pads, the derailleur's cage plates and links, the bottle cage's
  spine wires, the top tube's clips and cable stops, the saddle's rivets —
  was built as one shape at two positions, which puts their side faces on
  one plane. Each pair now differs a fraction of a millimetre.
- Faces that simply landed on another's plane: a derailleur hanger bolt's
  cap level with the axle end, the jockeys 0.1 mm off a cog's face, the
  big ring's face 0.1 mm off the chain's inner plates, the seat tube and
  down tube starting from one ring of vertices (they welded into one
  shell). Each was moved.

The remaining constants (the idle cogs' tooth phase, the roller phase
step, the plate tapers, the right-hand plate scale and the tilt step) were
chosen by a seeded search in a probe that counted pairs; the shipped
script has no RNG.

### Wheels, steering, chain, stance and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Hubs coaxial with their dropouts: each hub's axle (principal PCA axis of its body) against both dropout eyes' centres | ≤ 0.5 mm | 0.000 mm (front and rear, 2 eyes each) |
| Spoke seats: every spoke's hub end below its flange's rim (read off the hub's own radius at that station), and its rim end on its nipple's axis and inside it | flange depth 2.0–4.0 mm; ≤ 0.3 mm off axis; ≥ 2.0 mm inside the nipple | 3.00 mm; 0.000 mm; 4.50 mm (36 + 36 spokes, 36 + 36 nipples) |
| Wheels in the frame's centre plane: each rim's centre (PCA) against the plane of the main triangle's four tubes, and its axis against the plane's normal; frame size and wheelbase | ≤ 1.0 mm; ≤ 0.3°; seat tube 0.580 ± 0.004 m; wheelbase 1.000 ± 0.005 m | 0.000, 0.000 mm; 0.000°; 0.5800 m; 0.99982 m |
| Steering trail: the head tube's axis (principal PCA axis) meets the ground ahead of the front tyre's contact, on its line | 0.045–0.065 m; ≤ 3 mm across | 0.05536 m (axis 17.70° from vertical, 73° head angle plus the lean); 0.000 mm |
| Lacing: 36 spokes a wheel, 18 from each flange, rim ends equally pitched, each hub end three crosses round from its rim end | pitch within 0.3° of 10°; cross angle 58–62° | 36, 36; 18/18, 18/18; 0.000°; 60.000° |
| Chain seated: every roller that engages the big ring or the driven cog (its body straddles the sprocket's plane and cuts its teeth), counted and seated between root and tip | ≥ 20 on the ring, ≥ 6 on the cog; 0.5–6.5 mm above the root circle read off the sprocket | 30, 10; 1.20–3.40 mm |
| Chain line: every roller and the driven cog against the big ring's mid-plane | ≤ 1.0 mm | 0.000 mm; 0.000 mm |
| Stance: mass centre (shell volumes × density per material) inside the triangle of both tyres' contact rings and the stand foot's sole | ≥ 0.020 m inside every edge | 0.0393 m (11.80 kg, centre at x 0.076, y 0.039, z 0.498) |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (685 shells) |

A seated roller sits 1.2 mm above the root circle (its centre is on the
pitch circle); the rollers entering and leaving each wrap sit higher, up
to 3.4 mm, which is what the band's width allows for. The densities are
named constants (frame tubes and rims as hollow sections, tyres round an
air chamber, solid steel for chrome and chain parts), and the volumes come
from the mesh. The lean puts the mass centre 39 mm onto the stand's side
of the tyres' line; upright, it would sit just right of it (the drivetrain
is on the right) and the bike would fall away from its stand, which is what
`--tuck-stand` shows.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code, with every budget checked before it green and
the triangle count unchanged.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-tyre` | both tyres and the stand foot on the ground (rear tyre 3 mm up: its `zmin` 0.00300, the rest 0) | 16 |
| `--slip-wheel` | hubs coaxial with their dropouts (front wheel 2 mm forward in its dropouts: 0.00200 m) | 17 |
| `--short-spoke` | spoke seats (one front spoke 9 mm short at the rim: its end 1.5 mm outside its nipple, −0.00150 m) | 18 |
| `--dish-wheel` | wheels in the frame's plane (rear rim, tyre and nipples 3 mm to the drive side, spokes re-aimed from their flanges: 0.00299 m) | 19 |
| `--steep-head` | steering trail (head tube turned 6° steeper about its middle: trail −0.02926 m) | 20 |
| `--bunch-spokes` | lacing (one front spoke and nipple turned 4° about the axle: pitch off by 4.000°) | 21 |
| `--lift-chain` | chain seated (the chain wrapped 5 mm high on ring and cog: seated up to 8.11 mm above the root) | 22 |
| `--shift-rollers` | chain line (every roller pushed 1.5 mm inboard along its pin: 0.00150 m) | 23 |
| `--tuck-stand` | stance (the stand's foot drawn in to 40 mm off the tyres' line: margin −0.0062 m) | 24 |
| `--pop-bottle` | one connected assembly (the bottle lifted 80 mm straight off the tube, clear of its cage: 2 components, bottle and cap) | 25 |

`--float-tyre` lifts only the rear tyre, so the rim, spokes and chain stay
seated and only the support budget sees it. `--slip-wheel` moves the whole
front wheel (tyre, rim, spokes, nipples, hub, skewer) along its dropouts,
so every spoke still seats and the trail stays in band (53.4 mm); only the
hub-to-eye distance sees it. Its first draft moved it 3 mm, which set a
hub face on a dropout eye's plane and exited 15. `--short-spoke` pulls one
spoke's rim end back along the spoke, which barely turns it about the axle,
so the lacing still passes. `--dish-wheel` moves the rim horizontally in
world space rather than along the leaned axle, which would have lifted
the rear tyre off the ground and exited 16. `--steep-head` turns only the
head tube, in the frame's plane, so the frame-plane budget before it is
unchanged. `--shift-rollers` replaced a first draft that bent the chain's
rear half inboard: a gradient of 2 mm over the chain stay moved each plate
0.12 mm per two links, exactly one stagger level, and 4528 plate faces
landed on each other's planes (exit 15). Moving the rollers along their
own pins leaves every plate face where it was. The chain audit counts a
roller as engaged only when its body straddles the sprocket's plane; with
contact alone the shifted rollers' pin tips touched the 19 and the audit
chose it as the driven cog (exit 22). `--pop-bottle` lifts a part held
by one joint only, and it caught a real defect: its first draft moved the
bottle 30 mm sideways and split off seven shells, not two — the wire cage
had been hanging on the bottle, its spines never reaching the bosses. The
cage now has a crossbar and bolt at each boss, and the bottle, lifted
80 mm clear of the hoops, comes away alone with its cap. `--float-tyre`'s
first draft lifted the tyre 4 mm and set a face on a brake pad's plane
(exit 15); it lifts 3 mm.

## Run

```bash
blender --background --python road_bicycle.py --
blender --background --python road_bicycle.py -- --skip-decimate
blender --background --python road_bicycle.py -- --stray-vert
blender --background --python road_bicycle.py -- --lift-z
blender --background --python road_bicycle.py -- --float-tyre
blender --background --python road_bicycle.py -- --slip-wheel
blender --background --python road_bicycle.py -- --short-spoke
blender --background --python road_bicycle.py -- --dish-wheel
blender --background --python road_bicycle.py -- --steep-head
blender --background --python road_bicycle.py -- --bunch-spokes
blender --background --python road_bicycle.py -- --lift-chain
blender --background --python road_bicycle.py -- --shift-rollers
blender --background --python road_bicycle.py -- --tuck-stand
blender --background --python road_bicycle.py -- --pop-bottle
blender --background --python road_bicycle.py -- --output bicycle.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (−50°): a shallow three-quarter
from the drive side, front wheel to the right, so the crankset, chain and
derailleurs face the lens and the bike leans away onto its stand. The
wall stands 2.6 m behind the bicycle, and the warm wedge pools on it.
Chrome, alloy and steel carry the reflection-vector studio from
`espresso-machine` so they read as metal on the dark stage.

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
| 15 | Mesh hygiene: loose, non-manifold, zero-area, doubles, n-gons, coplanar cross-shell pairs (`--stray-vert`) |
| 16 | Not grounded: bounding box `zmin` off 0, or a tyre or the stand foot off the ground (`--lift-z`, `--float-tyre`) |
| 17 | A hub's axle off a dropout eye's centre (`--slip-wheel`) |
| 18 | Spoke seats: a hub end outside its flange band, or a rim end off its nipple's axis or not inside it (`--short-spoke`) |
| 19 | A rim off the frame's centre plane or tilted to it, or the seat tube or wheelbase off size (`--dish-wheel`) |
| 20 | Steering trail outside its band, or the axis off the front contact's line (`--steep-head`) |
| 21 | Lacing: spoke or flange counts, rim-end pitch, or cross angle (`--bunch-spokes`) |
| 22 | Chain seat: too few rollers engaged on ring or cog, or one seated outside its band (`--lift-chain`) |
| 23 | Chain line: a roller or the driven cog off the big ring's plane (`--shift-rollers`) |
| 24 | Stance: mass centre within 0.020 m of the support triangle's edge (`--tuck-stand`) |
| 25 | Assembly splits into more than one connected component (`--pop-bottle`) |
| 26 | Asset-quality floor (render path only; remapped from 11) |
