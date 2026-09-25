# Hay bale

A showcase piece, not an example. Procedural bound straw bale (cinched
pillow loaf, end-grain strata, two orange polypropylene belts that
wrap the loaf's own cross-section, a knot loop standing on each) then the shipped pipeline: unique-cell
UVs, Cycles high-to-low normal bake, LOD chain, convex collider, Unity
glTF export.

It asserts **budget conformance** of the generated result. It does not
witness an API contract. "It rendered without error" is not a check.

**Composes** skills `mesh-editing-and-bmesh`, `bake-high-to-low`,
`depsgraph-and-evaluated-data`, `engine-export-presets`, and snippets
`bake_normal_high_to_low.py`, `setup_bake_target_image.py`,
`lod_chain.py` / `decimate_to_budget.py`, `convex_hull_collider.py`,
`export_preset_unity.py` (helpers copied, not imported as a package).
Hygiene combinatorics match `examples/mesh-hygiene-audit` (copied, not
imported).

Intended size: 0.90 × 0.48 × 0.38 m nominal bale. The loaf measures
0.921 × 0.508 × 0.393 m with its pillow bulge, and the envelope is
0.921 × 0.508 × 0.417 m once the belts and knot loops are on it.

## How the belts are built

The belt is **not a constant rectangle**. The loaf's cross-section at a
belt station is rounded, bulged and waisted, so a rectangle stands proud
at the middle of each face and is swallowed at the corners — which is
exactly what the previous build did, leaving the wrap hanging 2.9–8.3 mm
above the floor with a visible notch at the bottom edge.

Instead the loaf is built, bevelled and **grounded first**, then each
belt raycasts the finished loaf at its own station (`loaf_profile`,
`BELT_SEGS` samples) and follows that profile at a named bite. Where the
run passes near the ground it is pressed flush and a little past flush
(`BELT_PRESS_H`, `BELT_UNDER_SINK`) so the loop closes underneath
without breaking the Z=0 plane the bale is grounded on.

Every closed-form term in the loaf shaping is **even in x**. An odd term
(`sin(x*24)`) put the two belt stations on different surface heights and
left the wraps 5.4 mm out of step, which no budget could see.

## Budgets

Declared as named constants; every gate **recomputes** from the mesh,
materials, UVs, evaluated LOD, collider, or export file. Measurements
below are identical on 4.5.11, 5.1.2 and 5.2.1 — construction uses no
RNG and no version-dependent operator.

| Axis | Declared | Measured (4.5.11 / 5.1.2 / 5.2.1) |
| --- | --- | --- |
| Base triangles | 1700–2400 | 2044 on all three |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2192 |
| Materials | exactly 2 distinct, ≥24 hay, ≥24 twine | 2 slots, 1436 hay, 304 twine |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.921, 0.508, 0.417) m ± 0.01 | (0.9208, 0.5075, 0.4165) |
| Grounded zmin | within 1e-4 of 0 | 0.000000 |
| Hygiene | loose/nonman/zero-area/doubles/n-gons/**z-fight** = 0 | all 0 |
| Shell count | exactly 5 (loaf, 2 belts, 2 loops) | 5 |
| **Belt wrap zmin** | each belt shell ≤ 0.006 m | 0.001460 both |
| **Belt seat depth** | every station in [0.002, 0.020] m | 0.00400..0.01114 over 20/20 stations, both belts |
| **Mirror symmetry** | belts and loops matched within 5e-4 m | 0.000000 |
| **Loaf mirror** | every loaf vertex has an X-mirror partner within 2e-4 m | 0.000093 |
| **Cinch depth** | mid-span minus waist in [0.006, 0.020] m | 0.01053 |
| Loaf X × Z | (0.921, 0.393) m ± 0.02 | (0.9208, 0.3931) |
| Hay–twine gap | BVH surface < 0.008 m | 0.00009 |
| Collider tris | ≤ 400 | 140 |
| Bake texels | smallest UV cell ≥ 12 px at the baked resolution | 22.43 px at 1024 px |
| Export | written, size > 0 | 203508 / 203508 / 203496 bytes |

DECIMATE COLLAPSE triangle counts are **not** guaranteed identical
across series — the gate is a ratio band, not an exact count. Bake
pixels are stochastic; the gate is `has_data` plus operator `FINISHED`,
not byte-identity, plus the texel floor. The bake was 256 px, which left
5.6 texels per UV cell and smeared neighbouring cells' normals into
streaks across the straw; at 1024 px with a 0.02 m cage (was 0.04, which
reached the twine standing proud of the loaf) every cell gets 22. Export
byte counts differ by 12 B on 5.2.1 (glTF
serializer), which is not a gated axis; every geometric figure above is
identical on all three binaries.

The export is deleted once its size is measured. Blender sets `TMPDIR`
from its own preference, which resolves to the working directory on a
stock portable build, so `tempfile.gettempdir()` is the repo root under
CI and every run used to leave a `.glb` behind.

### Why these budgets and not an AABB

`zmin` alone cannot see a belt that stops at the bottom edge: the loaf
still grounds the box. A single global hay-twine gap cannot see a wrap
that hugs one side and gaps the other. A bounding box cannot see two
belts 5.4 mm out of step, or a flank with no waist in it. Each of the
five budgets in bold above exists because a defect got past everything
else and had to be found by looking at a render.

The z-fight count is taken over **cross-shell** face pairs, not merely
over faces that share no vertex: two quads two steps apart on one flat
cap share no vertex and are coplanar by construction, and counting those
reported 96 pairs, none of them a hazard.

### Why the loaf is triangulated along its short diagonals

The twine used to be a 16 × 24 mm band, and it read as packing tape on a
parcel. Thinned to an 8 × 10 mm cord, the two belts came out 0.45 mm out
of step, right against the 0.5 mm mirror budget. The loaf's vertices
were mirror-symmetric to 71 um. The belt profile is raycast from the
loaf at each station, though, and the loaf's quads are not planar: split
along a fixed diagonal, the surface at -x and at +x differed by up to
5.6 mm on the same vertices. The old wide band happened to hide that.

The loaf is now triangulated with `quad_method="SHORT_EDGE"`. On
mirror-symmetric vertices the shorter diagonal is mirror-symmetric too,
and a tie only happens where a quad is planar, where either split is the
same surface. The belt mirror error went back to exactly 0 and the seats
to identical values at both stations. This is the surface an engine
renders, so it is fixed in the mesh, not only in the sampling. Averaging
the two stations' profiles was tried first and rejected: it put one belt
0.52 mm into the loaf, below the seat band, because neither station's
real surface is the mean.

The loaf's own symmetry is now asserted directly (**Loaf mirror**,
exit 19). Every loaf vertex needs a partner at `(-x, y, z)` within
`LOAF_MIRROR_EPS`. The belt budget only ever caught an odd shaping term
second-hand, through the belts' extents. `--odd-loaf` adds a 2 mm odd
`sin` displacement to the finished loaf and fails it. It is applied
after the bevel because, put into the shaping function, even 0.3 mm of
odd term flipped which edges cleared the bevel's 50-degree selection
and grew the envelope 16 mm, so the bounding box fired instead.

## Falsifiers

Each breaks one stage so a **named** budget fails and the piece exits
that code. All eight proven on 4.5.11, 5.1.2 and 5.2.1.

| Flag | Target budget | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | hygiene: loose vertices | 15 |
| `--lift-z` | grounded AABB zmin | 16 |
| `--float-belts` | per-belt wrap zmin | 16 |
| `--slack-belt` | banded belt seat depth | 18 |
| `--skew-belt` | belt mirror symmetry | 19 |
| `--odd-loaf` | loaf X-mirror symmetry | 19 |
| `--low-bake` | bake texel density: 256 px bake (under 12 px per cell) | 20 |

`--stray-vert` parks its loose vertex **inside** the bale: above it, the
bounding-box budget (exit 8) fired first and the run proved nothing
about hygiene. `--skew-belt` shifts one belt along **X** rather than Z
for the same reason — a Z skew landed a belt face coplanar with a loaf
face and tripped the z-fight budget (exit 15) instead of its target.
`--float-belts` moves twine only, so the loaf still grounds the AABB and
the per-belt gate has to be the thing that fires. With the ridge at 6 mm the
knot loops set the envelope top, so the two twine falsifiers are sized to
their own budgets and kept inside `BBOX_TOL`: `--float-belts` lifts 8 mm
(was 20) against a 6 mm wrap gate, and `--slack-belt` backs off 6 mm (was
10) against a 2 mm seat floor. At the old sizes both exited 8.

## Run

```bash
blender --background --python hay_bale.py --
blender --background --python hay_bale.py -- --skip-decimate
blender --background --python hay_bale.py -- --stray-vert
blender --background --python hay_bale.py -- --lift-z
blender --background --python hay_bale.py -- --float-belts
blender --background --python hay_bale.py -- --slack-belt
blender --background --python hay_bale.py -- --skew-belt
blender --background --python hay_bale.py -- --odd-loaf
blender --background --python hay_bale.py -- --low-bake
blender --background --python hay_bale.py -- --output bale.png
```

Smoke does not pass `--output` or any falsifier flag.

## Shading

Decided per part, not globally. The loaf is **flat**-shaded: straw is a
chunky matte mass and the facets read as compressed flakes. Smoothing
the whole bale erased every ridge and nap in it and left a featureless
pillow that read as a bar of soap. Twine is cord, so the belts and
hitch loops stay smooth.

The low mesh carries the form — bulge, waist, ridges, end strata — and
the **high mesh carries the straw**: `LOAF_CUTS_HIGH` subdivision plus
per-band flake offsets, moved onto the low mesh by the bake stage. A low
mesh dense enough to model flakes directly would cost thousands of
triangles for detail this piece already has a bake for.

## Surface

The bale used to read as a wrapped parcel: flat mustard hay, and a wide
dark band for twine. The hay is now `straw_material`:
- a dense fibre field stretched along the bale (noise with X compressed),
  and a weaker crossing field for the strands that lie the other way;
- colour pulled between pale straw and dark tan by the fibres, with a
  faint green cast from low-frequency noise;
- roughness and a bump from the same fibres, so every strand catches
  light.

The baked normal is chained under that bump (`wire_normal`). The twine
is a 10 × 14 mm orange polypropylene cord standing 6 mm proud. As an
8 × 10 mm dark brown cord it stood 4 mm proud of the waisted loaf and read
as a scored cut in every view. The longitudinal ridge dropped from 14 mm to
6 mm, because at 14 mm it crumpled the top edge in profile and the bale read
as a stuffed sack. Each knot is a tight loop, `KNOT_MAJOR` 13 mm, standing
in the belt's plane with its tube sized from `TWINE_T`. A 60 mm ring lying
flat on the top read as a printed symbol. The earlier note here, that the surface belonged to the
material and bake and not to more geometry, was right. The cord was the
other half of the parcel read.

## Exit codes

File-local. `9` is a valid check code. `10` is reserved for
`gallery_framing.check_framing` on the `--output` path.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Mesh did not build / no UV layer |
| 4 | Base triangle count outside range |
| 5 | Material count ≠ 2 distinct slots, or hay/twine faces missing |
| 6 | UVs outside 0..1 |
| 7 | UV AABB overlap above tolerance |
| 8 | World AABB off declared outer size |
| 9 | LOD ratio band (`--skip-decimate` lands here) |
| 10 | Framing gate (render path only) |
| 11 | Collider triangle count above ceiling |
| 12 | Bake did not finish or image has no data |
| 13 | Export file missing or empty |
| 14 | `--output` produced no file |
| 15 | Hygiene: loose, non-manifold, zero-area, doubles, n-gons, or cross-shell z-fight (`--stray-vert`) |
| 16 | Grounded: AABB zmin (`--lift-z`), or a belt that does not wrap under (`--float-belts`) |
| 17 | Shell count, or hay–twine BVH gap above 8 mm |
| 18 | Banded belt seat depth (`--slack-belt`) |
| 19 | Loaf X-mirror symmetry (`--odd-loaf`), belt mirror symmetry (`--skew-belt`), cinch depth, or loaf real-world size |
| 20 | Bake texel density below the floor (`--low-bake`) |
