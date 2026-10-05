# Weight rack

A showcase piece, not an example, and the third in the `sports` category.
It builds a procedural home-gym strength set: a half rack holding a loaded
Olympic barbell, with plates on its storage horns and two hex dumbbells on
the floor.

- two floor feet, each a rectangular tube on two rubber pads with plastic
  end caps sleeved over both ends, tied at the back by a floor crossmember;
- four 3 in square uprights (2.08 m) standing on base plates with four
  washered hex bolts each, capped at the top. Their front faces carry a row
  of 23 punched holes on a 2 in pitch, each a pocket into the dark tube
  interior. The front uprights are punched front and back, and their front
  faces number every hole with raised white numerals;
- two side rails on bolted flanges, a rear top crossmember and a zinc
  pull-up bar with welded collars;
- two J-hooks: a J-section plate on the upright's face, its saddle lined
  with an off-white UHMW liner, held by a pull pin with a knob seated in
  hole 17;
- two spotter arms on hole 7: a mount plate, a rectangular tube with a
  gusset, a UHMW strip along its top and a rubber end cap, on the same pull
  pins;
- the barbell as one turned body, 2.20 m: a 28 mm shaft with a centre
  knurl, two knurl zones split by ring marks, two collars, and two 50 mm
  sleeves with a snap-ring groove and a recessed end cap;
- on each sleeve a 20 kg blue bumper, a 15 kg yellow bumper and a 5 kg
  cast-iron change plate, closed by a coiled spring clip with rubber grips.
  Every bumper has a steel hub insert proud of its rubber face and a raised
  rim; the outermost bumper of each stack carries its kilogram rating on top
  and its pound rating below, in raised numerals;
- four plate-storage horns on the rear uprights' outer faces, each on a
  bolted weld plate with a backstop flange: 20 + 10 kg and 10 kg bumpers
  low, 5 + 2.5 kg and 2.5 kg iron plates high; and
- two hex dumbbells lying on a flat of each rubber head, with knurled
  chrome handles.

The layout is solved from named constants. The bar rests where the two
saddles put it: its axis is set from each liner's top plus the shaft radius,
less a 0.2 mm bite. Every plate hangs on its sleeve, its bore resting on the
sleeve's top, so its centre sits 0.8 mm below the axis. Each hub bites
0.5 mm into the plate or collar inside it, and the clip bites the last
plate. Neighbouring bores are turned a third of a segment apart, so no bore
facet shares a plane with the sleeve or with the next plate.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 2.20 m across the bar, 1.64 m from the dumbbells to the rear
foot caps, 2.09 m to the top of the upright caps. The bar sets the width,
the dumbbells and the rear feet the depth, and the caps the height. The
origin is under the rack, so it lands on its pads.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 43500–45000 | 44264 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2197 |
| Materials | exactly 12 distinct; ≥4420 powder coat, ≥2820 bore, ≥3900 zinc, ≥3110 chrome, ≥235 knurl, ≥1230 rubber, ≥96 UHMW, ≥2890 numeral, ≥800 blue, ≥530 yellow, ≥530 green, ≥2080 cast-iron faces | 12 slots; 4758 / 3036 / 4196 / 3348 / 256 / 1328 / 104 / 3112 / 864 / 576 / 576 / 2240 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (2.200, 1.636, 2.092) m ± 0.01 | (2.2000, 1.6364, 2.0920), zmin 0 |
| Collider tris | ≤ 640 | 472 |
| Export | written, size > 0, removed after measuring | 3295024 / 3295024 / 3295016 bytes (4.5.11 / 5.1.2 / 5.2.1) |

The collider is the convex hull of the whole set. Its count is carried by
the plates' rims and the dumbbell heads, which are the hull's outline.

Every falsifier leaves the triangle count at 44264: they move parts or
swap a plate for one of the same topology, never add or remove geometry.

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
| Supports: each of the 4 rubber pads and each of the 4 dumbbell heads has its own `zmin` | within 1e-4 of 0 | all 0 |

The first draft measured 264 coplanar pairs. The plates on one sleeve all
hung with the same bore cylinder, in the same phase as the sleeve, so their
bore facets shared planes with the sleeve and with each other. A bumper
numeral's top landed on the plane of the iron plate's face, and one hole
numeral's wall landed on the J-hook's side. The fixes changed the model:
bores are turned a third of a segment apart, the numerals stand 0.8 mm
proud instead of 1.2, and the J-hook is 1 mm narrower. Each digit and each
neighbouring numeral also sits on its own plane (0.13 mm steps), alternate
hole numbers are offset 0.3 mm across the face, and bolts in a group are
staggered along their axes.

### Pins, bar, plates, balance and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Pins coaxial: each of the 4 pull pins (vertex mean of the lathe) against the nearest punched hole's centre (vertex mean of its pocket floor), and its depth past the face | 4 pins; ≤ 0.5 mm off the axis; depth 4–9.5 mm | 0.000 mm on all four; 7.0 mm |
| Bar seated: from the bar axis over each J-hook liner, a ray down to the liner minus the same ray to the bar's own underside | −0.8 to +0.3 mm on both | −0.20 mm, −0.20 mm |
| Level and size: the bar axis (PCA) against horizontal; bar length along it; upright height; every bumper's diameter | tilt ≤ 0.05°; 2.200, 2.080, 0.450 m, each ± 0.003 | 0.0000°; 2.2000, 2.0800, 0.450 |
| Plates seated: each plate assigned to the nearest sleeve axis (bar sides by collar face, horns by backstop face read off the mesh); its offset from that axis; along the axis the gap from the stop face to the first plate, plate to plate, and last plate to the clip | counts 3, 3, 2, 1, 2, 1; offset ≤ 1 mm; every gap −0.8 to −0.2 mm | as declared; 0.80 mm; 14 gaps all −0.50 mm |
| Load balance: the loaded bar's mass centre (shell volumes × density: bumpers 1800 kg/m³, cast iron 7200, steel 7850) along its axis from its midpoint | ≤ 2 mm | 0.002 mm (96.4 kg; 37.86 kg each side) |
| One connected rack (union of shells whose BVH trees overlap), plus the two loose dumbbells | 3 components | 3 (222 shells) |

A barbell on J-hooks is only safe if the hooks are pinned through the
upright and the bar sits in both saddles. The pin budget reads the hole
from the mesh, not from the constant that placed it. The bar is set level
by construction, so the level budget is what catches a hook hung one hole
high. A plate that is not seated walks along the sleeve. An unequal load
tips the bar off the hooks. The pound rating is measured nowhere; it is
printed where real bumpers print it.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code. None moves the envelope beyond 0.2 mm or the
triangle count, and every budget checked before the target stayed green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-foot` | every pad and dumbbell head on the floor (left front pad 3 mm up: its `zmin` 0.00300, the rest 0) | 16 |
| `--offset-pin` | pins coaxial with their holes (left spotter and its pin 12 mm up: 0.012 m off the hole axis) | 17 |
| `--float-bar` | bar seated in both saddles (bar, plates and clips 5 mm up: shaft-to-liner +0.0048 m on both) | 18 |
| `--hook-high` | bar level (right J-hook one hole higher, bar resting across both saddles: tilt 2.644°) | 19 |
| `--gap-plate` | plates seated (right iron plate and clip 8 mm out along the sleeve: gap +0.0075 m) | 20 |
| `--odd-load` | load balance (left 5 kg iron plate swapped for 2.5 kg: mass centre 0.0226 m off the midpoint) | 21 |
| `--loose-horn` | one connected rack (upper-left horn with its weld plate, bolts and plates 10 mm off the upright: 4 components) | 22 |

`--offset-pin` moves the spotter, not a J-hook, so the bar stays seated
and level. `--float-bar` also splits the assembly, but seating (18) is
checked first. `--hook-high` keeps every pin in a hole (the J-hook moves one
full pitch) and both saddle gaps inside their band (−0.215 mm); the bar end
moves 0.2 mm in x, inside the bounding-box tolerance. `--gap-plate` moves
the load's mass centre 0.4 mm, inside the balance tolerance. `--odd-load`
keeps every plate seated, since the clip moves in against the thinner plate.

## Run

```bash
blender --background --python weight_rack.py --
blender --background --python weight_rack.py -- --skip-decimate
blender --background --python weight_rack.py -- --stray-vert
blender --background --python weight_rack.py -- --lift-z
blender --background --python weight_rack.py -- --float-foot
blender --background --python weight_rack.py -- --offset-pin
blender --background --python weight_rack.py -- --float-bar
blender --background --python weight_rack.py -- --hook-high
blender --background --python weight_rack.py -- --gap-plate
blender --background --python weight_rack.py -- --odd-load
blender --background --python weight_rack.py -- --loose-horn
blender --background --python weight_rack.py -- --output rack.png
```

Smoke passes no flags.

The hero turns the piece `HERO_YAW_DEG` (28°), so the loaded left sleeve,
the left horns and the spotter arms come toward the lens, and the rear
uprights stand clear of the front ones. The wall stands 3.2 m behind the
rack, and the warm wedge pools on it.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20`–`22` are file-local. `23` is the
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
| 16 | Not grounded: bounding box `zmin` off 0, or a pad or dumbbell head off the floor, or not 4 of each (`--lift-z`, `--float-foot`) |
| 17 | Pins: not 4, one off its hole's axis, or inserted outside its depth band (`--offset-pin`) |
| 18 | Bar not seated in both J-hook saddles (`--float-bar`) |
| 19 | Bar tilted, or bar length, upright height or a bumper diameter off (`--hook-high`) |
| 20 | Plates: wrong count on a sleeve, one off every sleeve axis, or a gap along a sleeve outside its band (`--gap-plate`) |
| 21 | Load balance: the loaded bar's mass centre off its midpoint (`--odd-load`) |
| 22 | Assembly: not one connected rack plus two dumbbells (`--loose-horn`) |
| 23 | Asset-quality floor (render path only; remapped from 11) |
