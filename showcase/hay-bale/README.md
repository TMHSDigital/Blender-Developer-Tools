# Hay bale

A showcase piece, not an example. Procedural bound straw bale (cinched
pillow loaf, end-grain strata, two sisal belts that wrap the loaf's own
cross-section, tied hitch loops) then the shipped pipeline: unique-cell
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

Intended size: 0.90 × 0.48 × 0.38 m nominal bale; the loaf measures
0.922 × 0.530 × 0.409 m once the pillow bulge, the belts and the hitch
loops are on it.

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
| Base triangles | 1700–2400 | 2012 on all three |
| LOD1 ratio | 0.32–0.62 of base | 0.5000 |
| LOD2 ratio | 0.10–0.35 of base | 0.2197 |
| Materials | exactly 2 distinct, ≥24 hay, ≥24 twine | 2 slots, 712 hay, 304 twine |
| UVs | in `0..1`, AABB overlap ≤ 1e-5 | in range, overlap 0 |
| Outer AABB | (0.922, 0.530, 0.409) m ± 0.01 | (0.9208, 0.5295, 0.4087) |
| Grounded zmin | within 1e-4 of 0 | 0.000000 |
| Hygiene | loose/nonman/zero-area/doubles/n-gons/**z-fight** = 0 | all 0 |
| Shell count | exactly 5 (loaf, 2 belts, 2 loops) | 5 |
| **Belt wrap zmin** | each belt shell ≤ 0.006 m | 0.002628 both |
| **Belt seat depth** | every station in [0.002, 0.020] m | 0.00400..0.01676 over 20/20 stations, both belts |
| **Mirror symmetry** | belts and loops matched within 5e-4 m | 0.000000 |
| **Cinch depth** | mid-span minus waist in [0.006, 0.020] m | 0.01420 |
| Loaf X × Z | (0.922, 0.409) m ± 0.02 | (0.9208, 0.4087) |
| Hay–twine gap | BVH surface < 0.008 m | 0.00002 |
| Collider tris | ≤ 400 | 156 |
| Export | written, size > 0 | 156664 / 156664 / 156656 bytes |

DECIMATE COLLAPSE triangle counts are **not** guaranteed identical
across series — the gate is a ratio band, not an exact count. Bake
pixels are stochastic; the gate is `has_data` plus operator `FINISHED`,
not byte-identity. Export byte counts differ by 8 B on 5.2.1 (glTF
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

## Falsifiers

Each breaks one stage so a **named** budget fails and the piece exits
that code. All six proven on 4.5.11, 5.1.2 and 5.2.1.

| Flag | Target budget | Exit |
| --- | --- | --- |
| `--skip-decimate` | LOD1 ratio band | 9 |
| `--stray-vert` | hygiene: loose vertices | 15 |
| `--lift-z` | grounded AABB zmin | 16 |
| `--float-belts` | per-belt wrap zmin | 16 |
| `--slack-belt` | banded belt seat depth | 18 |
| `--skew-belt` | belt mirror symmetry | 19 |

`--stray-vert` parks its loose vertex **inside** the bale: above it, the
bounding-box budget (exit 8) fired first and the run proved nothing
about hygiene. `--skew-belt` shifts one belt along **X** rather than Z
for the same reason — a Z skew landed a belt face coplanar with a loaf
face and tripped the z-fight budget (exit 15) instead of its target.
`--float-belts` moves twine only, so the loaf still grounds the AABB and
the per-belt gate has to be the thing that fires.

## Run

```bash
blender --background --python hay_bale.py --
blender --background --python hay_bale.py -- --skip-decimate
blender --background --python hay_bale.py -- --stray-vert
blender --background --python hay_bale.py -- --lift-z
blender --background --python hay_bale.py -- --float-belts
blender --background --python hay_bale.py -- --slack-belt
blender --background --python hay_bale.py -- --skew-belt
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

## Known gap

At hero scale the piece still reads as a wrapped parcel rather than as
straw. The form, the binding and the hygiene are right; the surface is
not. The next pass on this piece belongs in the **material and bake**
— straw needs directional fibre and colour break-up that a 256 px
tangent-space normal off a smooth high mesh cannot deliver — not in more
geometry. Recorded here so the next run does not re-litigate the
silhouette.

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
| 19 | Belt mirror symmetry (`--skew-belt`), cinch depth, or loaf real-world size |
