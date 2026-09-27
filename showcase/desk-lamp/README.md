# Desk lamp

A showcase piece, not an example, and the first in the `household`
category. It builds a procedural balanced-arm architect's lamp in the
classic Anglepoise pattern:

- a three-tier cast base, lofted as one shell from rounded-square loops,
  with a maker's badge on the front riser;
- a swivel turret on a steel bearing washer, carrying a yoke;
- two parallelogram arm sections (0.32 m and 0.36 m pin to pin), each of
  two parallel rods ending in eye bosses;
- three knuckles (base, elbow, head) whose cheeks carry a cast boss at
  every pin station, seven through-pins, and knurled tension knobs on the
  base, elbow and shade pins;
- three close-wound extension springs, two on the lower section and one
  on the upper, each hung by a looped end on a cross bar at both ends;
- a domed enamel shade with a white reflector inside, a wired rolled rim,
  a chrome band over the cowl step and a push switch, hung from the head
  knuckle on a stem and eye;
- a lamp in a ribbed screw cap on a bakelite socket, with an emissive
  glass envelope;
- a flex that leaves a gland on the shade's back, drapes down rod B of
  each section and enters a grommet on the base's top tread; and a mains
  cable that leaves a grommet in the rear riser, crosses the desk and ends
  in a two-pin plug.

The linkage is solved from named stations (`arm_stations()`): the lower
and upper rods run at 72° and −10°, each section's second rod is offset
by the same 30 mm link vector, and the shade hangs on its own pin at 50°
below horizontal. Every pin, eye, bar and spring is placed from those
stations, so moving one angle moves the whole arm consistently.

Two things the coplanar budget forced:

- Stations on one knuckle are a few centimetres apart, so their flat
  faces must not share a plane. Each station's boss stands 0.3 mm prouder
  than the last, its pin head moves with it, and its eye is 0.3 mm
  narrower. Before this the first run measured 7987 coplanar cross-shell
  pairs, nearly all of them boss, eye and pin caps on shared planes.
- The two cheeks of a knuckle are not mirror copies. The far cheek's lugs
  are 0.4 mm smaller, or the pair's rims lie in the same planes. Coaxial
  parts of equal radius (a mirrored boss pair, the lower and upper eyes at
  the elbow) are turned half a facet apart for the same reason, and so is
  rod B relative to rod A.

The cable is a Catmull-Rom spline through floor points. Between points
the spline dipped 0.3 mm through the desk and grounded the whole piece on
the cable, so the base stood 0.3 mm in the air. The cable is now clamped
to rest on the desk, and the base and plug are what reach Z = 0.

Shading follows what each part is. Round stock (rods, springs, flex,
shade, lamp) is smooth-shaded. Treads, chamfers and knurls stay crisp
through sharp edges above 35° and at every material boundary. The enamel
is a deep glossy red with a clear coat. The springs, pins and knobs are
plated steel, rough enough to catch the key rather than mirror a black
stage.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: a 0.18 m square base, 0.32 m and 0.36 m arm sections, and
a shade 0.17 m across the rim. The outer AABB is 0.725 × 0.361 × 0.442 m.
The shade rim sets +X, the plug sets −X and −Y, and the elbow knuckle
sets the top. The origin is under the base centre, so the lamp drops onto
a desk by its base.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 29000–31500 | 30110 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 6 distinct; ≥3600 enamel, ≥8300 steel, ≥310 bulb, ≥1350 rubber, ≥560 reflector, ≥340 bakelite faces | 6 slots; 3972 / 9210 / 348 / 1508 / 622 / 384 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.725, 0.361, 0.442) m ± 0.01 | (0.7252, 0.3606, 0.4421), zmin 0 |
| Collider tris | ≤ 760 | 713 |
| Export | written, size > 0, removed after measuring | 2229360 bytes |

The triangle band is wide enough to hold `--hollow-base` (30974) and
`--unhook-spring` (29790), so those falsifiers exit on their own budgets
rather than on the triangle count.

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

### Joint pins, springs, stance and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Joint pins: for each of the 7 pins (axis by PCA), the XZ offset from its axis to the axis of every eye and boss within 12 mm, taken at that eye's own station | ≤ 0.0003 m; 7 pins, 23 eyes and bosses, ≥ 3 per pin; each pin spans every one of them in Y; pin tilt ≤ 0.5° | 0.000000; 7 pins, 23 (3, 3, 4, 4, 3, 3, 3); 0 not through; 0.000° |
| Spring seat: for each of the 6 looped ends, distance from its centre to the axis of the nearest bar, within that bar's length; each coil's wire runs into exactly 2 loops | ≤ 0.0006 m; 3 coils, 6 loops, 4 bars | 0.000000; ends [2, 2, 2] |
| Stance: mass centre (shell volumes × density per material) inside the base footprint read off the mesh | ≥ 0.025 m inside every edge | 0.0396 (11.76 kg, centre at x 0.0504) |
| Base width | 0.180 m ± 0.003 each way | 0.1800 × 0.1800 |
| Arm sections, pin to pin (both rods of each) | 0.320 / 0.360 m ± 0.003 | 0.3200, 0.3200 / 0.3600, 0.3600 |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (78 shells) |

A balanced-arm lamp whose shade rim reaches nearly 0.6 m past its pivot stands only
because its base is heavy. The stance budget tests exactly that: the
densities are named constants (steel and cast iron 7850, bakelite 1400,
rubber 1200, and 300 for the lamp, whose glass is modelled solid but is
a hollow envelope), and the volumes come from the mesh.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. None moves the envelope: every run measured the
same outer AABB as the default.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--offset-pin` | joint pins coaxial (elbow pin moved 2.5 mm off its eyes: offset 0.00250 m) | 17 |
| `--unhook-spring` | spring seat (one loop 10 mm short of its bar: 0.01000 m) | 18 |
| `--hollow-base` | stance (base pressed from 1.5 mm steel: 3.22 kg, centre at x 0.184, margin −0.094 m) | 19 |
| `--unscrew-bulb` | one connected assembly (lamp backed 5 mm out of its socket: 2 components) | 20 |

`--offset-pin` still leaves the pin inside every eye it passes through,
and the arm lengths it moves (0.3208, 0.3575 m) stay inside their
tolerance, so only the coaxial budget sees it. `--unhook-spring` leaves
the spring hanging from its lower bar, so the assembly stays connected.
`--hollow-base` keeps the outer loft, so the envelope and footprint are
unchanged and only the mass moves.

## Run

```bash
blender --background --python desk_lamp.py --
blender --background --python desk_lamp.py -- --skip-decimate
blender --background --python desk_lamp.py -- --stray-vert
blender --background --python desk_lamp.py -- --lift-z
blender --background --python desk_lamp.py -- --offset-pin
blender --background --python desk_lamp.py -- --unhook-spring
blender --background --python desk_lamp.py -- --hollow-base
blender --background --python desk_lamp.py -- --unscrew-bulb
blender --background --python desk_lamp.py -- --output lamp.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (−95°). The reach then points to
the camera's right and toward it, so the parallelogram reads in depth and
the shade's mouth shows the lit lamp. A small point light just inside
the mouth stands in for the lamp's light and lights the reflector. It is
render-only, like the stage. The wall stands 2.6 m behind the lamp, and
the warm wedge pools on it behind the shade.

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
| 16 | Not grounded: bounding box `zmin` off 0 |
| 17 | Joint pins: a pin off the axis of an eye or boss it joins, not spanning one, tilted, or not 7 pins and 23 eyes (`--offset-pin`) |
| 18 | Spring seat: a looped end off its bar's axis or length, or a coil not running into two loops, or not 3 coils, 6 loops and 4 bars (`--unhook-spring`) |
| 19 | Stance and size: mass centre within 25 mm of the base's edge, base width, or an arm section's length (`--hollow-base`) |
| 20 | Assembly splits into more than one connected component (`--unscrew-bulb`) |
| 21 | Asset-quality floor (render path only; remapped from 11) |
