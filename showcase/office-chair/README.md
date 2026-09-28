# Office chair

A showcase piece, not an example, and the second in the `household`
category. It builds a procedural ergonomic task chair:

- a polished aluminium five-star base: five lofted spokes, each a crowned
  section with two channels and a centre rib on its underside, running
  from a moulded nylon hub out to a socket boss;
- five twin-wheel casters, one under each boss on a plumb chrome swivel
  stem: a bearing washer, a nylon web and hood, a chrome axle and two
  crowned wheels (nylon hub, grey polyurethane tread) trailing the stem by
  30 mm, each caster swivelled its own way as a chair left after being
  rolled about;
- a chrome gas-lift column rising out of the hub through a two-stage
  telescoping cover into the conical socket of a graphite tilt mechanism,
  which carries a tilt-spring housing, a knurled tension knob and two
  lever paddles;
- a moulded seat pan under a contoured upholstered cushion whose plan
  tapers toward the back and bows out at the sides: a dished seating area, side bolsters, a waterfall front, a panel seam round the
  seating area and a piped welt along the top edge;
- an aluminium spine that sweeps out of the mechanism's rear, down under
  the back and up behind it into a hub plate on a cross bar;
- a reclined mesh back: a warm-white moulded frame round a sheer woven
  panel, wrapped round the sitter and bulged forward at the lumbar, with an
  arched top rail, a sliding lumbar pad on straps, and an upholstered
  headrest on its own aluminium stem;
- two height-adjustable T-arms: aluminium brackets bolted under the pan,
  posts with a chrome release button, pad plates and soft leatherette
  pads.

Everything is placed from named stations. The casters hang on
`caster_frame(k)`: a stem on the 0.305 m swivel circle at the spoke's own
bearing, the axle 30 mm behind it along the caster's yaw. The back is one
surface function, `back_point(u, v, off)`, that the frame, panel, lumbar
pad, straps, cross bar, hub plate, spine and headrest stem all read, so a
change of recline or wrap moves every part of the back together.

Three things the coplanar budget shaped before it could fire:

- The two wheels of one caster are mirror images on one axle. A tread
  segment of constant radius would lie in the same plane as its twin's,
  facet for facet, 35 mm away. The tread is crowned instead, and no wheel
  profile segment keeps its radius, so no twin faces share a plane.
- The welt is a cord laid on the seam between two cushion rings, its
  centre offset outward along the profile's own normal so it bites the
  cushion by 1.6 mm rather than lying on it.
- The headrest stem starts 14 mm above the spine's end inside the same
  hub plate, so the two sweeps' end caps are not stacked on one plane.

Shading follows what each part is. Moulded, turned and upholstered
surfaces are smooth-shaded; the mechanism's chamfers, the knob's knurl,
the seat's seam and every material boundary stay crisp through sharp
edges. The upholstery is a tangerine heather with a fine nap, not wave
bands, which read as wood grain at hero scale. The mesh panel lets part of
the light through, so the spine and headrest stem show behind it.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: seat 0.49 m high, a 0.66 m star, armrests 0.20 m over
the seat, headrest top 1.28 m. The outer AABB is 0.678 × 0.693 × 1.279 m.
The casters set ±X, the cushion's front sets −Y, and the headrest sets
+Y and the top. The origin is under the hub, so the chair
drops onto a floor by its wheels.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file. Parts are told apart by a `part` face attribute written at
build time; every position, depth, angle and mass is read off the mesh.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 35200–36800 | 35992 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 9 distinct; ≥2000 fabric, ≥1350 mesh, ≥2050 shell, ≥3950 nylon, ≥4100 aluminium, ≥1240 chrome, ≥1820 rubber, ≥1540 leatherette, ≥510 steel faces | 9 slots; 2110 / 1424 / 2168 / 4178 / 4307 / 1308 / 1920 / 1624 / 538 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.678, 0.693, 1.279) m ± 0.01 | (0.6781, 0.6928, 1.2788), zmin 0 |
| Collider tris | ≤ 1040 | 995 |
| Export | written, size > 0, removed after measuring | 2708432 bytes |

No falsifier changes the triangle count, so the band is narrow and
centred on the measurement. DECIMATE COLLAPSE triangle counts are not
identical across Blender series, so the LOD gate is a ratio band, not an
exact count. Bake pixels are stochastic, so the bake gate is `has_data`
plus operator `FINISHED`, not byte-identity. Construction uses no RNG;
two default runs print identical measurements.

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

### Wheels, star, gas lift, stance and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Named supports: every wheel shell's lowest vertex on the floor | 10 wheels, each ≤ 1e-4 | 10; 0.00000–0.00000 |
| Five-star geometry: spoke bearings and boss bearings (shell centroids) round the hub | 72° apart ± 0.25° | 0.00003° worst gap error |
| Bosses and swivel stems on one circle | radius spread ≤ 1 mm each | 0.305 / 0.305 m, spread 0 |
| Stems plumb (bottom- and top-slab centroids), coaxial with their bosses, seated in them | tilt ≤ 0.2°; axis ≤ 0.3 mm off the boss's; seat 25–40 mm | 0.000°; 0.0000 mm; 34 mm each |
| Gas lift: the column's axis through the hub's and the socket's axes | ≤ 0.3 mm at each; tilt ≤ 0.2° | 0.0000 / 0.0000 mm; 0.000° |
| Column inserted into the hub / the socket | 40–65 mm / 20–40 mm | 52 / 28 mm |
| Armrests: bracket, post, button, pad plate and pad paired left to right, mirrored in X and level in Y and Z | ≤ 0.5 mm, 5 pairs | 0.0000 mm |
| Seat height (cushion top), armrest height over the seat | 0.44–0.50 m, 0.17–0.26 m | 0.4904, 0.1966 m |
| Star diameter (outer boss reach ×2) | 0.660 m ± 0.005 | 0.6599 |
| Stance: mass centre (shell volumes × density per material) inside the hull of the ten wheels' floor contacts | ≥ 0.12 m inside every edge | 0.2154 (29.18 kg, centre at y 0.035) |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (80 shells) |

The densities are named constants: 50 for seat foam, 300 for the
leatherette pads, 400 for the mesh, 1150 for nylon, 1200 for the treads,
2700 for aluminium, 7850 for chrome steel, and an effective 3000 for the
mechanism, a pressed-steel housing modelled solid. The five spokes are
measured by bearing, not by index: rotating any one breaks two of the
five gaps.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code with every earlier budget green. None moves the
envelope or the triangle count: every run measured the default's outer
AABB and 35992 triangles.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-caster` | every wheel on the floor (caster 3's body lifted 5 mm up its stem: highest wheel bottom 0.00500 m, the other eight wheels still ground the AABB) | 16 |
| `--skew-spoke` | five-star geometry (spoke 0 and its caster turned 3°: worst gap off 72° by 3.000°) | 17 |
| `--offset-column` | gas lift coaxial (column moved 3 mm in X: 0.00300 m off both the hub's and the socket's axes) | 18 |
| `--uneven-arms` | armrests mirrored and level (right post, button, plate and pad raised 10 mm on the bracket: 0.01000 m) | 19 |
| `--loose-wheel` | one connected assembly (caster 0's outer wheel slid 24 mm off its axle end: 2 components) | 20 |

`--float-caster` lifts the caster body, not the stem, so the stem only
rides deeper into the web and the star budget still passes.
`--offset-column` leaves the column seated 52 mm and 28 mm deep and
plumb, so only the coaxial budget sees it. `--uneven-arms` slides the
arm up its own bracket, as the height adjuster does, so the assembly
stays connected and the envelope holds; the seat and armrest heights stay
in band. `--loose-wheel` slides a wheel along its own axle, so it still
stands on the floor and the named-supports budget passes; it is attached
by one joint, the axle, which is why it is the part that splits.

## Run

```bash
blender --background --python office_chair.py --
blender --background --python office_chair.py -- --skip-decimate
blender --background --python office_chair.py -- --stray-vert
blender --background --python office_chair.py -- --lift-z
blender --background --python office_chair.py -- --float-caster
blender --background --python office_chair.py -- --skew-spoke
blender --background --python office_chair.py -- --offset-column
blender --background --python office_chair.py -- --uneven-arms
blender --background --python office_chair.py -- --loose-wheel
blender --background --python office_chair.py -- --output chair.png
```

Smoke passes no flags.

The hero turns the chair `HERO_YAW_DEG` (18°), so the seat and arms face
the camera's right and the back shows its wrap and lumbar in three
quarters. The camera stands high enough to see into the seat. The chair
is tall and narrow, so it fills the frame's height (0.85) and not its
width (0.28); the framing band is met on Y.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20` is file-local. `21` is the asset-quality
floor on the render path: `check_asset_quality` returns 11, which this
piece already spends on the collider ceiling, so the call site remaps it.

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
| 16 | Not grounded: bounding box `zmin` off 0, or a wheel off the floor, or not 10 wheels (`--lift-z`, `--float-caster`) |
| 17 | Five-star geometry: spokes or bosses off 72° spacing, bosses or stems off one circle, a stem tilted, off its boss's axis or outside its seat band (`--skew-spoke`) |
| 18 | Gas lift: column off the hub's or the socket's axis, tilted, or inserted outside its bands (`--offset-column`) |
| 19 | Stance and size: armrests not mirrored and level, seat or armrest height, star diameter, or the mass centre within 0.12 m of the caster contact hull's edge (`--uneven-arms`) |
| 20 | Assembly splits into more than one connected component (`--loose-wheel`) |
| 21 | Asset-quality floor (render path only; remapped from 11) |
