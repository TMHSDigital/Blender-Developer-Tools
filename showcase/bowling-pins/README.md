# Bowling pins

A showcase piece, not an example, and the fourth in the `sports` category.
It builds the pin deck end of a ten-pin bowling lane: a section of lane
with the ten pins racked on their spots and a ball resting on the approach.

- the lane, one laminated slab of 39 maple boards, 41.5 in across and
  2.75 in thick. Each board's top edges are chamfered into a V seam, so the
  boards read one by one, and every board takes its own tone and grain
  offset in the shader from its index across the lane. A joint crosses the
  lane where the approach meets the dark pin deck. The cut near end shows
  the boards' end grain;
- ten pin spots inlaid in the deck on a 12 in equilateral triangle, the head
  spot 34 3/16 in from the pit edge, as the rules place it;
- seven targeting arrows (a chevron on boards 5 to 35) and ten range dots
  inlaid at the near end;
- two gutters with a channel profile running the whole length, low cappings
  outside them on the approach, and two kickbacks beside the deck: a
  laminate panel with a sloped nose under a mitred aluminium cap and a
  phenolic kick plate on its inner face;
- a steel bullnose on the pit edge, and five sleepers under everything;
- ten pins, each lathe-turned from the regulation profile table in the
  script (15 in tall, 4.766 in at the belly, 1.797 in at the neck), glossy
  white with two red neck stripes and a crown band of red teeth, standing on
  its spot; and
- an 8.5 in ball in marbled violet resin, drilled by an exact Boolean with a
  1 in thumb hole 2.5 in deep and two 0.8 in finger holes 2 in deep, each
  countersunk at the rim. The fingers sit 1.05 in apart and 4.4 in from the
  thumb along the surface. They are drilled parallel to each other, as a
  real grip is: drilled toward the centre, two 2 in holes 14° apart meet
  inside the ball.

The layout is solved from named constants. A section of real lane is 60 ft
long; this one is 2.3 m, so the arrows and dots, which sit about 15 and
7 ft from the foul line on a real lane, are brought up to its near end.
Every pin's base sits 0.6 mm below the deck face, inside its spot, and the
ball's centre sits its radius less 0.6 mm above the lane. Inlays stand
0.25 mm proud of the lane and bite 0.5 mm into it. Neighbouring range dots
stand 0.13 mm apart in height, so no two share a plane.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: 1.64 m across the sleepers, 2.30 m from the lane's near end
to the kickbacks' aluminium caps behind the pit edge, 0.52 m to the top of
the caps. The origin is under the head spot at floor level.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 36400–37700 | 37078 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 11 distinct; ≥330 maple, ≥330 pin deck, ≥12800 pin white, ≥1190 pin red, ≥1450 ball, ≥480 bore, ≥235 gutter/kick plate, ≥130 kickback laminate, ≥160 aluminium/steel, ≥1110 inlay, ≥350 sleeper faces | 11 slots; 358 / 358 / 13720 / 1280 / 1649 / 562 / 254 / 142 / 176 / 1197 / 380 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.640, 2.301, 0.523) m ± 0.01, read off the vertices | (1.6400, 2.3014, 0.5234), zmin 0 |
| Collider tris | ≤ 300 | 277 |
| Export | written, size > 0, removed after measuring | 2730012 bytes |

Every falsifier leaves the triangle count at 37078 and the envelope at
(1.6400, 2.3014, 0.5234): they move or resize parts, never add or remove
geometry.

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. The ball's
Boolean may cut its sphere into a slightly different set of faces on
another series; the triangle band and the ball and bore floors leave room
for it. Bake pixels are stochastic, so the bake gate is `has_data` plus
operator `FINISHED`, not byte-identity. Construction uses no RNG; two
default runs print identical measurements.

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
| Supports: each of the 5 sleepers has its own `zmin` | within 1e-4 of 0 | all 0 |

The first draft measured 206 coplanar pairs: the range dots on boards 3 and
5 (and their mirrors) are 54 mm apart, and their triangulated caps shared a
plane within the 50 mm range. The dots now alternate 0.13 mm in height. It
also had one zero-area face, a sliver the Boolean left where cut vertices
fell in a line; the ball's faces are triangulated and its slivers dissolved
before it joins the deck.

The lane is one shell, so its boards cannot z-fight each other; the seams
are V-grooves in that shell. The Boolean does not carry material indices the
same way on every version, so the ball's faces are classified afterwards by
geometry: a face that lies on the sphere and faces straight out is shell,
everything else is bore.

### Pins, spots, ball, boards and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Pins on spots: each pin's base centre (centroid of its bottom cap) against the nearest spot centre, in plan | 10 pins, 10 spots; ≤ 0.5 mm | 0.000 mm on all ten |
| Pins seated: base centre below the deck face under it (a ray onto the lane) | 0.3–1.0 mm | 0.6 mm on all ten |
| Plumb and size: axis (bottom cap to top cap) against vertical; height; belly (twice the largest radius) | tilt ≤ 0.05°; 0.381 m and 0.12106 m, ± 0.5 mm | 0.000°; 0.3810; 0.12106 |
| Spot lattice: nearest-neighbour edges (pairs under 1.2 pitches), rows across the lane, row pitch, head spot on the lane's centre line (read off the lane shell) | 18 edges at 12 in; rows 1, 2, 3, 4, each level; pitch 12·√3/2 in; all ± 0.5 mm | 18 at 0.000 mm off; 0.000 mm; 0.26396 m; 0.000 mm |
| Turned profile: each pin's radius at every one of the 15 table stations, from the vertices on that station | ± 0.2 mm | 0.000 mm |
| Ball resting: sphere fit to the ball's shell; its centre above the lane under it (a ray onto the lane), less its radius; its diameter | rest −0.9 to −0.3 mm; 0.2159 m ± 0.3 mm | −0.60 mm; 0.21590 |
| Finger holes: each hole's axis from its flat drilled bottom (the normal and centre of its bottom cap); depth from the bottom to where the axis leaves the sphere; bore from its straight run; span and bridge as arcs between the holes' entry points | 3 holes; thumb 58–68 mm, fingers 46–56 mm deep; bores 1.0 and 0.8 in ± 0.3 mm; span 4.4 in ± 2 mm; bridge 1.05 in ± 1 mm | 63.5, 50.8, 50.8 mm; 25.40, 20.32, 20.32 mm; 112.2 mm; 26.67 mm |
| Boards: flat board tops clustered across the lane; count; every top at one height; each board's edges straight down the lane; pitch between interior boards | 39; spread ≤ 0.2 mm; ≤ 0.1 mm; 41.5/39 in ± 0.1 mm | 39; 0.000; 0.000; 0.000 |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (55 shells) |

The span measures 112.2 mm against 4.4 in (111.8 mm): each finger's entry
is turned half a bridge off the pair's mid-line, so the arc to it is a
little longer than the arc to the mid-line.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
exited its declared code, with the triangle count and envelope unchanged
and every budget checked before the target green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-sleeper` | every sleeper on the floor (the middle sleeper 3 mm up: its `zmin` 0.00300, the rest 0) | 16 |
| `--offset-pin` | every pin centred on its spot (pin 5 moved 6 mm across the lane: 0.006 m off) | 17 |
| `--float-pin` | every pin seated on the deck (pin 3 lifted 3 mm: base 2.4 mm above the deck face) | 18 |
| `--lean-pin` | every pin plumb (pin 6 tipped 1.5° about its base centre: tilt 1.396°) | 19 |
| `--wide-rack` | spots on the exact 12 in lattice (spots and pins spread 3% about the head spot: edges 9.1 mm long, rows 7.9 mm apart) | 20 |
| `--fat-neck` | turned profile (the neck station 1.5 mm fatter: 1.5 mm off the table on every pin) | 21 |
| `--float-ball` | ball resting on the lane (lifted 4 mm: rest +3.4 mm) | 22 |
| `--shallow-holes` | finger holes (both fingers drilled 30 mm: depth 0.030 against 46–56 mm; bores, span and bridge unchanged) | 23 |
| `--proud-board` | boards flush and parallel (board 18 raised 1.2 mm along its length: tops spread 1.2 mm) | 24 |
| `--lift-arrows` | one connected assembly (the seven arrows lifted 1 mm off the lane: 8 components) | 25 |

`--offset-pin`, `--float-pin` and `--lean-pin` each move one pin and leave
its spot, so the lattice holds. `--lean-pin` tips the pin about the centre
of its base, so the base centre stays on its spot and at its seat; the tilt
alone fails. The pin measures 1.396° rather than 1.5° because its axis runs
from the bottom cap's centroid to the top cap's, and the top cap is a small
flat, not a point. `--wide-rack` moves pins with their spots, so every pin
stays centred and seated; the back row, 24 mm further back, is still on the
deck. `--fat-neck` changes the neck only, so height and belly hold.
`--proud-board` raises a board that carries no pin, spot, arrow, dot or the
ball; pins read the deck face under themselves, not the lane's highest
board, so their seat holds. `--float-ball` also splits the assembly, but the
rest (22) is checked first.

Before the audits were settled, `--lift-z` exited 16 on the sleepers, not
on the bounding box: `bound_box` is a cached copy that an in-place vertex
edit does not refresh, so the AABB gate now reads the vertices. The first
hole audit took each hole's axis from its vertices by principal components;
a 30 mm hole is barely longer than it is wide, so the axis wandered and
`--shallow-holes` also moved the bore and bridge. The axis now comes from
the drilled bottom, and the flag moves the depth alone.

## Run

```bash
blender --background --python bowling_pins.py --
blender --background --python bowling_pins.py -- --skip-decimate
blender --background --python bowling_pins.py -- --stray-vert
blender --background --python bowling_pins.py -- --lift-z
blender --background --python bowling_pins.py -- --float-sleeper
blender --background --python bowling_pins.py -- --offset-pin
blender --background --python bowling_pins.py -- --float-pin
blender --background --python bowling_pins.py -- --lean-pin
blender --background --python bowling_pins.py -- --wide-rack
blender --background --python bowling_pins.py -- --fat-neck
blender --background --python bowling_pins.py -- --float-ball
blender --background --python bowling_pins.py -- --shallow-holes
blender --background --python bowling_pins.py -- --proud-board
blender --background --python bowling_pins.py -- --lift-arrows
blender --background --python bowling_pins.py -- --output pins.png
```

Smoke passes no flags.

The hero looks down the lane from behind the approach, 15° off its axis.
That falls between the rack's 0° and 30° lines, so no pin hides behind
another and the triangle reads whole. The ball rests to the left of the
head pin's line with its grip turned to the lens. The wall stands 2.2 m
behind the lane's centre, and the warm wedge pools on it. EEVEE ray tracing
is on, so the lacquered deck reflects the pins.

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
| 5 | Material count ≠ 11 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a sleeper off the floor, or not 5 sleepers (`--lift-z`, `--float-sleeper`) |
| 17 | Pins on spots: not 10 pins and 10 spots, or a pin's base off its spot (`--offset-pin`) |
| 18 | A pin's base outside its seat band below the deck face (`--float-pin`) |
| 19 | A pin not plumb, or its height or belly off (`--lean-pin`) |
| 20 | Spots off the 12 in lattice: edges, rows, row pitch or head spot off the centre line (`--wide-rack`) |
| 21 | A pin's radius off the profile table at a station (`--fat-neck`) |
| 22 | Ball not resting on the lane at its radius, or its diameter off (`--float-ball`) |
| 23 | Finger holes: not 3, or a depth, bore, span or bridge outside its band (`--shallow-holes`) |
| 24 | Boards: not 39, tops not flush, edges not straight, or pitch off (`--proud-board`) |
| 25 | Assembly splits into more than one connected component (`--lift-arrows`) |
| 26 | Asset-quality floor (render path only; remapped from 11) |
