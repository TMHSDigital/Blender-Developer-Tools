# Traffic cones

A showcase piece, not an example, and the seventh in the `vehicles`
category: things that direct movement. It builds a roadworks set standing on
a cut-out patch of asphalt:

- the patch, 3.0 × 2.0 m and 60 mm thick, with a broken edge (a rounded
  rectangle pushed along its normal by a closed-form jitter), chamfered top
  and bottom rims, a worn white road line that runs to within 30 mm of the
  broken edge, and two sealed cracks: meandering tar strips with a squeezed,
  chamfered top;
- seven 28 in (720 mm) PVC traffic cones. Each body is a hollow frustum
  lathed from a closed profile: a moulded bead above the collar, a rolled
  lip round an open tip, and an inner wall. It is bonded into a 14 in
  square rubber base lofted from rings that share one angle list, so the
  chamfered-square rings keep their eight corners and the round rings follow
  them: a chamfered foot, a raked top rising to a collar, four moulded lugs
  toward the corners, and a recess underneath that takes the collar of the
  cone below it. Two retroreflective collars, 4 in and 6 in, are hooped on
  each body;
- three of the cones stand in a taper line, three are nested in a stack, and
  one has been knocked over. The fallen cone lies on the edge of its base and
  the lip of its tip: the roll at which both touch the slab is solved by
  bisection, so its open base and recess face the lens;
- a folding A-frame barricade: four 32 mm square steel legs hinged in pairs
  on pivot bolts (a washer between the pair, a hex head outside, a nut
  inside), each end spread by a strap pinned to the front leg and, through a
  spacer, to the back leg; each foot in a rubber pad; plastic caps on the leg
  tops; two 1.24 m boards on each face, split on 45° lines into orange and
  white retroreflective stripes 100 mm wide, each bolted to its two legs with
  four carriage bolts; and
- a warning lamp at the left end of the top front board: a bent steel
  bracket bolted to the board's face, a battery box, and a drum housing with
  an amber fresnel lens and a bezel on each face.

Everything that stands on the patch bears 1.5 mm into it: every base, the
fallen cone's base and body, and the barricade's pads. Boards bear 1.5 mm
into the legs they are bolted to; collars bear 0.6 mm into their bodies and
stand 1.4 mm proud of them.

The stack is the piece's own invariant. A cone's wall is thick enough, for
the slope of its body, that the next cone down seats on it one nesting pitch
lower: `WALL_H = BODY_SLOPE × STACK_PITCH + NEST_BITE`. So each upper cone's
inner wall bears 1 mm on the lower cone's outer wall along the whole overlap,
and the bases hang 36 mm apart with the lower collar inside the upper recess
(6 mm clear above it, 16 mm around it).

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: the patch is 3.04 × 2.04 m with its jittered edge; the lamp
housing sets the top at 1.335 m. A cone is 0.720 m tall on a base 0.356 m
across the flats; the barricade's hinges stand 1.0 m over the slab. The
origin is under the patch centre at the slab's underside.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 45300–46400 | 45816 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 11 distinct; ≥5560 cone PVC, ≥3760 reflective, ≥7440 rubber, ≥540 asphalt, ≥50 road paint, ≥450 tar, ≥58 orange sheeting, ≥350 board plastic, ≥2670 steel, ≥660 black plastic, ≥640 lens faces | 11 slots; 6048 / 4088 / 8096 / 596 / 56 / 496 / 64 / 384 / 2912 / 720 / 696 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (3.0365, 2.0374, 1.3354) m ± 0.01, read off the vertices | (3.0365, 2.0374, 1.3354), zmin 0 |
| Collider tris | ≤ 540 | 493 |
| Export | written, size > 0, removed after measuring | 3335792 bytes |

Every falsifier leaves the triangle count at 45816 and the envelope at
(3.0365, 2.0374, 1.3354): they move parts, never add or remove them.

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. Construction uses no RNG; two default runs print
identical measurements, and 4.5.11 and 5.1.2 print the same measurements
as 5.2.1 (the export differs by 28 bytes).

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
| Supports: every standing base, the stack's bottom base, the fallen cone's base and body, and the four pads, each against the slab top read off the asphalt | 10 supports; sink 0.8–3.0 mm | 10; 1.5 mm each |

The first draft measured 205 coplanar pairs, none of them in a part:

- The two bolts on the lamp bracket are 40 mm apart, so their flat base caps
  shared a plane inside the 50 mm range (196 pairs). The second bolt sits
  0.3 mm deeper.
- The stack was yawed 4°, −11° and 16°. Fifteen degrees apart, the collar
  walls of two stacked bases landed on the same vertical planes (8 pairs).
  The yaws are now 3.1°, −8.7° and 14.9°, never a multiple of the base's
  angle step apart.

### Stance, joints, collars, size and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Boards into legs: each board's back face against the front face of each leg it is bolted to, both planes read off the faces and compared along the board's normal | 4 boards, 8 joints; bite 0.8–3.0 mm | 4, 8; 1.5 mm each |
| Collar seat: per collar, per angular segment, the innermost vertex against the host body's outer wall (a ray toward the axis along the vertex's own radial), and the outermost vertex's stand-off | 14 collars, each on a host; seat 0.2–1.5 mm; proud ≥ 1.0 mm | 14; 0.600 mm; 1.400 mm |
| Plumb and size: each upright body's bottom-slab against top-slab centroid; its top over its base's bottom; the base's width across the flats (support function about the axis) | 6 upright cones; tilt ≤ 0.2°; 0.720 m and 0.356 m ± 3 mm | 6; 0.0000°; 0.720; 0.356 |
| Mirror: the barricade's four legs paired across the boards' centre, extents compared | 4 legs; ≤ 1 mm | 4; 0.0001 mm |
| Nesting: coaxial upright bodies form stacks; per pair, the pitch between body bottoms and, by rays at 40 mm stations and 16 angles along the overlap, the lower's outer wall less the upper's inner wall | 1 stack of 3; pitch 0.030–0.042 m; bite 0.4–2.0 mm | 1 of 3; 0.036, 0.036; 0.847–0.949 and 1.034–1.105 mm |
| One connected assembly (union of shells whose BVH trees overlap) | 1 component | 1 (125 shells) |

The nesting bite varies round each pair because the stacked cones are yawed
differently, so a lower facet meets an upper facet off its middle; the chord
sag of a 48-segment body is 0.29 mm at the bottom.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1 and
4.5.11 and exited its declared code, with the triangle count and envelope
unchanged and every budget checked before the target green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-cone` | every support bedded in the slab (the right-hand standing cone lifted 4 mm: sink −2.5 mm, the rest 1.5 mm) | 16 |
| `--gap-board` | boards bite their legs (the lower front board 3 mm off its legs: −1.5 mm at both) | 17 |
| `--float-band` | collar seat (the left cone's 6 in collar 2 mm out: seat −1.4 mm) | 18 |
| `--lean-cone` | plumb (the middle standing cone's body tipped 1.5° in its base: tilt 1.431°) | 19 |
| `--skew-leg` | leg mirror symmetry (the right front leg 2.5 mm toward the centre: 2.500 mm) | 19 |
| `--loose-stack` | nesting (the top cone lifted 10 mm: pitch 0.046, bite −0.576 to −0.505 mm) | 20 |
| `--loose-lamp` | one connected assembly (the lamp 3 mm off its board: 2 components, 9 and 116 shells) | 21 |

`--float-cone` lifts a whole cone while the slab still grounds the box.
`--lean-cone` tips the body and its collars about the collar top and leaves
the base flat, so the supports hold; its measured tilt is a little under
1.5° because the slabs it compares are cut level through a leaning body.
`--skew-leg` moves the front leg inward, into the 3 mm gap its washer
fills, so it stays clear of its strap and its board's bite is unchanged.
`--loose-stack` first lifted the top cone 12 mm, which put its base bottom
on the middle cone's collar-top plane and exited 15 on 192 coplanar pairs;
10 mm keeps every horizontal plane of the two cones at least 2 mm apart.
`--loose-lamp` pulls the lamp level off the board rather than along the
board's normal, which had lifted the envelope's top 0.8 mm.

## Run

```bash
blender --background --python traffic_cones.py --
blender --background --python traffic_cones.py -- --skip-decimate
blender --background --python traffic_cones.py -- --stray-vert
blender --background --python traffic_cones.py -- --lift-z
blender --background --python traffic_cones.py -- --float-cone
blender --background --python traffic_cones.py -- --gap-board
blender --background --python traffic_cones.py -- --float-band
blender --background --python traffic_cones.py -- --lean-cone
blender --background --python traffic_cones.py -- --skew-leg
blender --background --python traffic_cones.py -- --loose-stack
blender --background --python traffic_cones.py -- --loose-lamp
blender --background --python traffic_cones.py -- --output cones.png
```

Smoke passes no flags.

The hero looks from the front left and above, so the taper line of cones
reads in front of the barricade, the stack's three bases show at the left
and the fallen cone's open base and recess face the lens. The wall stands
6 m behind the patch, and the warm wedge pools on it to the right. Default
stage; no deviation.

## Shading

The cone bodies, bases, lens, housing and every lathe are smooth-shaded;
chamfers, the patch's rims and every material boundary stay crisp through
sharp edges above 35°. The stripes are cut into the board's own faces, so
their boundaries are hard edges on a flat face and cannot z-fight. Every
cone, board and leg carries a `PartTone` face attribute that the shaders
read to move each part between two tones, so no two cones are the same
orange. Grime rises from the slab on every part; scuffs are sparse and
small. The cone PVC and its collars also carry level rub marks, black on
the orange and grey on the sheeting: a noise squashed sixteen-fold in
height, so each mark runs round the cone like a tyre or boot rub rather
than up it. The steel is galvanised, grey and rough, with a studio reflection
term so it does not read as plastic on a dark stage.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20` and `21` are file-local. `22` is the
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
| 16 | Not grounded: bounding box `zmin` off 0, or a support outside its sink band, or not 10 supports (`--lift-z`, `--float-cone`) |
| 17 | A board's bite into a leg outside its band, or not 4 boards and 8 joints (`--gap-board`) |
| 18 | A collar's seat or stand-off outside its band, or a collar with no host, or not 14 collars (`--float-band`) |
| 19 | A cone not plumb, its height or base width off, or the legs not mirror-symmetric, or not 6 upright cones and 4 legs (`--lean-cone`, `--skew-leg`) |
| 20 | Nesting: not one stack of 3, or a pitch or wall bite outside its band (`--loose-stack`) |
| 21 | Assembly splits into more than one connected component (`--loose-lamp`) |
| 22 | Asset-quality floor (render path only; remapped from 11) |
