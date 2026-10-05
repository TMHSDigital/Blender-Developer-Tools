# Go-kart

A showcase piece, not an example, and the eighth in the `vehicles`
category: things that move. It builds a rental/racing go-kart (generic, no
marks or text) parked on a patch of kart-track asphalt:

- the patch, 1.87 × 1.50 m and 60 mm thick, broken on three edges by a
  closed-form jitter that fades to nothing toward the fourth, which runs
  straight against a red and white kerb: a ramped, crowned kerb section
  lofted in six painted stripes, its foot tucked under the asphalt's
  chamfered edge;
- a chassis of 30 mm tube: the main loop (both rails, the front crossmember
  and the rear crossmember) is **one bar swept round every bend**; the seat
  and column cross tubes end on the rails' centre lines, with welded gussets
  in their corners; bearing hangers on the rear rails; C-brackets on the
  front corners (a web welded to the rail and two lugs square to the
  kingpin); an inverted-U column support with a bushing bracket; pedal
  pivot plates;
- steering: a three-spoke dished wheel on a 40°-raked column, in a lower
  bearing block and a bushing on the support; a steering plate at the
  column's foot and two tie rods (rod-end eyes, lock nuts, pins) to the
  spindles' arms; spindles (sleeve, stub axle, spacer, arm) on kingpin bolts
  with 14° caster;
- blue moulded bodywork: a nose cone on two bumper bars ahead of the front
  axle (a raised centre hump, lipped shoulders falling into a valley, a
  rounded chin); a front panel leaning back 40° from its foot sunk in the
  hump, bulged forward, its sides wrapped back and top corners rounded,
  carrying a plain white number plate pressed into its face; two side pods
  on chrome nerf bars (tapered in and down at the front, flared at the rear,
  a raised outer crest stepping down to a deck with seven grip ribs, a
  groove along the outer wall); a tubular rear bumper with plugged ends;
- ten flat strap brackets, each welded to a tube at one end and bolted flat
  to a moulding at the other: two from the column support's top bar bent
  down against the panel's back, two angle straps in the wedge behind the
  panel's foot (one leg on the panel, one on the hump), two from the front
  crossmember to the nose's back face, and one from each nerf bar to its
  pod's inner wall;
- a floor tray, a moulded seat on a cross tube with two stays to the hangers
  and two front brackets to the rails, a fuel tank strapped to the tray with
  its line to the carburettor, two pedals, and a three-plate lead ballast
  block bolted to the tray; a brake master cylinder (reservoir, boot,
  pushrod from the brake pedal) on a block bolted to the tray, its hose
  clipped along the left rail and up to the caliper; the throttle cable from
  the right pedal along the right rail, up inboard of the air-box and down
  onto the carburettor;
- a small four-stroke clamped to the right rail on a mount plate: finned
  cylinder and head leaning 25° forward, bearing cover, fan shroud and
  pull-start, air-box, carburettor, plug and lead, and an exhaust header to
  a silencer; a clutch drum carrying a 12-tooth sprocket and an 88-link
  3/8 in chain to a 60-tooth sprocket on the live rear axle, whose position
  is solved so the chain is a whole number of pitches; a 40 mm axle through
  two bearing carriers, with locking collars, a brake disc on a carrier and
  a caliper on a bracket from the rear crossmember;
- four slicks on split rims (split bolts, hub studs, valve stems): 10 in
  fronts 122 mm wide, 11 in rears 196 mm wide; the tyres are loaded, so the
  tread under the contact plane is flattened into a patch.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied inline, not imported).

Intended size: wheelbase 1.040 m, front track 1.100 m and rear track
1.200 m (tyre centre to tyre centre); overall 1.75 × 1.40 m, the seat back
0.47 m over the asphalt. The patch with its kerb is 1.90 × 1.77 m; the top
of the envelope is the seat back at 0.64 m. The origin is under the patch
centre at the slab's underside.

## Budgets

Every budget is declared as a named constant. Every gate **recomputes**
its value from the mesh, materials, UVs, evaluated LOD, collider, or
export file. Shells are found by a `part` face attribute; every measured
value is read from their vertices.

| Axis | Declared | Measured (5.2.1) |
| --- | --- | --- |
| Base triangles | 81000–82700 | 81854 |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2200 |
| Materials | exactly 14 distinct; ≥2910 frame paint, ≥6430 chrome, ≥7530 rubber, ≥3410 bodywork, ≥1420 seat, ≥11650 aluminium, ≥1760 engine casting, ≥3790 steel, ≥1550 black plastic, ≥158 fuel tank, ≥154 lead, ≥590 asphalt, ≥115 kerb paint, ≥114 number plate faces | 14 slots; 3168 / 6994 / 8188 / 3708 / 1548 / 12666 / 1920 / 4130 / 1686 / 172 / 168 / 646 / 126 / 124 |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (1.8950, 1.7738, 0.6397) m ± 0.01, read off the vertices | (1.8950, 1.7738, 0.6397), zmin 0 |
| Collider tris | ≤ 900 | 598 |
| Export | written, size > 0, removed after measuring | 6072672 / 6072672 / 6072664 bytes (4.5.11 / 5.1.2 / 5.2.1) |

Every falsifier leaves the triangle count at 81854 and the envelope at
(1.8950, 1.7738, 0.6397): they move parts, never add or remove them.

DECIMATE COLLAPSE triangle counts are not identical across Blender
series, so the LOD gate is a ratio band, not an exact count. Bake pixels
are stochastic, so the bake gate is `has_data` plus operator `FINISHED`,
not byte-identity. Construction uses no RNG; two default runs print
identical measurements, and 4.5.11 and 5.1.2 print the same measurements
as 5.2.1 (the export differs by 76 bytes).

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
| Tyres: each tyre's lowest vertex under the asphalt's top read off the slab, the four patches in one plane | 4 tyres; 0.8–3.0 mm; spread ≤ 0.1 mm | 4; 1.5 mm each; 0 |

The first draft measured 725 coplanar pairs, none of them in a part: hex
heads turned by the bolt circle's own angle step, so every head in a ring
put its flats on its neighbours' planes (each head is now turned a further,
non-commensurate step); the axle's end cap on the plane of the rear split
bolts' heads; equal 19.5 mm bores on the axle sharing facet planes (every
axle part is now turned a further step); stacked ballast plates of one
size; a brake carrier's face on the caliper's; gussets' edges on one plane
along their cross tube; a clamp face on a cross tube's end cap; and a
sprocket root flat on the plane of the chain's waist face. Mirrored rays
onto the bodywork also hit 2.3 mm apart until its lofts were triangulated
on their short diagonals: a fixed split is not mirror-symmetric, and a
fastener aimed at one triangulation floated over the other.

### Joints, seats, size, stance and assembly

| Axis | Declared | Measured |
| --- | --- | --- |
| Joint fit: each front hub against its stub axle and each rear hub and bearing against the axle (the part's axis of revolution and centre against the host's principal axis) | 4 hubs, 2 bearings; ≤ 0.3 mm off, ≤ 0.3° | 4, 2; 0.0 mm, 0.0° |
| Joint fit: each tie-rod eye on its pin (plan offset) and biting the plate under it (a ray down onto the steering arm or plate) | 4 eyes; ≤ 0.5 mm; bite 0.2–1.5 mm | 4; 0.0 mm; 0.3 / 0.5 mm |
| Tyre seat: per tyre, per angular segment, the bead vertices against the rim's bead seat (a ray toward the axis along each vertex's own radial) | 4 tyres, each on a rim; 0.4–2.0 mm | 0.864–1.000 mm |
| Chain seat: per sprocket, one bin per tooth over the middle half of the wrap, the tooth-root circle less the chain's inner edge; the chain's plane against the sprocket's | 2 sprockets; 0.8–3.0 mm; ≤ 0.5 mm | 1.911 and 1.943–1.946 mm; 0.005 / 0.006 mm |
| Mirror: every frame-paint and bodywork vertex (nose, panel, pods, grip ribs) against its partner across the loop's centre plane (KD-tree) | ≤ 0.5 mm | 0.043 mm |
| Wheels: front and rear tyres paired, centres and extents compared | ≤ 0.5 mm | 0.0001 mm |
| Size: wheelbase and both tracks from the tyres' own centres | 1.040 / 1.100 / 1.200 m ± 4 mm | 1.0400 / 1.1000 / 1.2000 |
| Caster: each kingpin sleeve's principal axis, tilt back in plan | 2 kingpins; 10–18° | 14.0°, 14.0° |
| Stance: mass centre (per-shell volume × a per-material density) inside the convex hull of the four contact patches | ≥ 0.312 m (30 % of the wheelbase) | 0.3735 m (88.6 kg) |
| One connected assembly (union of shells whose BVH trees overlap, the patch included) | 1 component | 1 (330 shells) |
| Bodywork brackets: per strap, its bite into every moulding or tube it meets (the deepest strap vertex inside that shell: nearest-face distance, signed by a three-ray parity vote); the two deepest are its two joints | 10 brackets; both joints 0.5–2.5 mm | 10; welded ends 0.90–1.99 mm, tabs 1.00–1.47 mm |

Densities are effective: tubes, rims and tyres are modelled solid but are
hollow, so each material carries a density that makes its mass plausible.

The bracket bite is signed by ray parity, not by the nearest face's normal:
beside the panel's 4 mm rim the nearest face is the rim strip, and its
normal read the tab's back face, 2 mm behind the panel, as 1.96 mm inside.
Each panel tab's width follows the panel's own across-direction: laid along
world Y, the wrapped sides tipped one edge of the tab off the panel.
Measuring it also found the nose inside out: `recalc_face_normals` had
turned it, so every closed island is now oriented by its signed volume
before shipping.

### Falsifiers

Each falsifier violates one named budget. Every one was run on 5.2.1,
4.5.11 and 5.1.2 and exited its declared code, with the triangle count and
envelope unchanged and every budget checked before the target green.

| Flag | Budget violated | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band (measured 1.0000) | 9 |
| `--stray-vert` | loose vertex count is 0 (measured 1, placed inside the envelope) | 15 |
| `--lift-z` | bounding box `zmin` is 0 (measured 0.05000) | 16 |
| `--float-tyre` | every tyre pressed into the asphalt in one plane (the left front lifted 4 mm: −2.5 mm, the rest 1.5 mm) | 16 |
| `--cock-hub` | hubs coaxial (the left rear hub 1.5 mm off the axle: 1.5 mm) | 17 |
| `--drop-bearing` | axle through both bearings (the right bearing and carrier 2 mm low: 2.0 mm) | 17 |
| `--short-tierod` | tie-rod eyes on their pins (the left rod 6 mm short: 6.0 mm) | 17 |
| `--sink-tyre` | tyre bead seat (the right rear bead 3 mm into its seat: 3.000 mm) | 18 |
| `--lift-chain` | chain seated on its sprockets (the chain 4 mm off both: −2.089 and −2.060 mm) | 18 |
| `--toe-wheel` | wheels mirrored (the left front corner turned 1.5°: 4.539 mm) | 19 |
| `--wide-track` | rear track at its stated size (each rear wheel 4 mm out: 1.2080 m) | 19 |
| `--odd-frame` | chassis mirror symmetry (the left rail bowed 3 mm out: 1.819 mm) | 19 |
| `--no-caster` | caster band (kingpins vertical: 0.0°) | 19 |
| `--aft-ballast` | stance (the 8 kg ballast moved behind the axle: 0.2887 m) | 20 |
| `--loose-ballast` | one connected assembly (the ballast lifted 3 mm off the tray: 2 components, 5 and 325 shells) | 21 |
| `--float-nose` | bodywork brackets (the nose and its bolts slid 3 mm forward: both nose brackets' tabs −2.0 mm) | 23 |

`--float-tyre` lifts the tyre alone, after the patch is flattened, while the
slab still grounds the box. `--toe-wheel` turns the whole corner (spindle,
hub, rim and tyre) about the vertical through the kingpin, and the tie rod
is rebuilt to the moved arm, so the hubs stay coaxial and the eye stays on
its pin; a turn about the raked kingpin itself would have dropped the patch
out of its band first. `--lift-chain` moves the chain alone, keeping the
tooth phase of the seated chain: phasing the teeth to the lifted pins, and
lifts of 1.7, 2.0, 2.5, 3.0 and 3.5 mm, each put a chain face within 0.1 mm
of a tooth flat's plane and exited 15. The assembly falsifier first lifted
a side pod, which broke the bodywork's mirror and exited 19; the ballast
stack is measured by nothing else. `--float-nose` moves the nose along X
only, so the mirror holds, the nose stays on its bumper bars and on the
panel's foot (one assembly), and the slab still sets the envelope.

## Run

```bash
blender --background --python go_kart.py --
blender --background --python go_kart.py -- --skip-decimate
blender --background --python go_kart.py -- --stray-vert
blender --background --python go_kart.py -- --lift-z
blender --background --python go_kart.py -- --float-tyre
blender --background --python go_kart.py -- --cock-hub
blender --background --python go_kart.py -- --drop-bearing
blender --background --python go_kart.py -- --short-tierod
blender --background --python go_kart.py -- --sink-tyre
blender --background --python go_kart.py -- --lift-chain
blender --background --python go_kart.py -- --toe-wheel
blender --background --python go_kart.py -- --wide-track
blender --background --python go_kart.py -- --odd-frame
blender --background --python go_kart.py -- --no-caster
blender --background --python go_kart.py -- --aft-ballast
blender --background --python go_kart.py -- --loose-ballast
blender --background --python go_kart.py -- --float-nose
blender --background --python go_kart.py -- --output kart.png
```

Smoke passes no flags.

The hero looks from the front right and above, so the nose, the front
panel with its plate and the right-hand wheels lead, the engine, chain and silencer show
over the right pod, and the kerb runs behind. The wall stands 5 m behind
the patch and the warm wedge pools on it behind the kart. Default stage; no
deviation.

## Shading

Lathed parts, tubes, tyres, the seat and the bodywork are smooth-shaded;
chamfers, fins, teeth and every material boundary stay crisp through sharp
edges above 35°. Every part carries a `PartTone` face attribute that moves
it between two tones, so the four tyres and the ballast plates differ, and
the kerb's stripes are the same attribute picking red or white. Grime rises
from the asphalt on every part and scuffs are sparse. Chrome, aluminium,
steel and the casting carry a studio reflection term so they do not read as
grey plastic on a dark stage; the track asphalt is streaked darker along
the racing line. The bodywork's lower half carries dark tyre-rubber streaks
and light scratches, both stretched fore and aft; the frame is scratched
through to steel low down; the frame, casting, aluminium, steel and chrome
darken with oily grime toward the engine.

The livery is blue with a white number plate, so the warm notes are the
red frame and the kerb. The yellow livery the piece first shipped with
filled the lower half of the hero and measured a wedge warmth of +0.288,
out of the calibration band (−0.144 to +0.105); blue measures −0.094.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path. `15`–`19` are the
hygiene and joint-fit family. `20`, `21` and `23` are file-local. `22` is the
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
| 5 | Material count ≠ 14 distinct slots, or a face-count floor missed |
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
| 16 | Not grounded: bounding box `zmin` off 0, or a tyre outside its band, the patches out of one plane, or not 4 tyres (`--lift-z`, `--float-tyre`) |
| 17 | Joint fit: a hub or bearing off its axle, a tie-rod eye off its pin or out of its bite band, or a part missing (`--cock-hub`, `--drop-bearing`, `--short-tierod`) |
| 18 | Seat: a tyre bead out of its seat band, the chain off its sprockets' roots or out of line, or a part missing (`--sink-tyre`, `--lift-chain`) |
| 19 | Mirror, size and angle: frame or bodywork not mirrored, wheels not mirrored, wheelbase or a track off, caster out of band (`--toe-wheel`, `--wide-track`, `--odd-frame`, `--no-caster`) |
| 20 | Stance: the mass centre too near an edge of the support polygon (`--aft-ballast`) |
| 21 | Assembly splits into more than one connected component (`--loose-ballast`) |
| 22 | Asset-quality floor (render path only; remapped from 11) |
| 23 | Bodywork brackets: not 10 straps, or a strap's weld or tab out of its bite band (`--float-nose`) |
