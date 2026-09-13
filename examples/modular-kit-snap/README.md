# Modular Kit Snap

A runnable example building the asset a tiling modular kit lives or dies
by: a corridor segment whose open-end boundary vertices sit **exactly** on
the declared tile grid, so instances placed at 4 m multiples share boundary
positions with no gap and no overlap. Interior geometry is free-form
(beveled detail boxes); only the boundary is snapped — the snap is a
deliberate authoring pass, and the check is what catches you skipping it.

**The asset, for reuse:** a 4 × 3 × 3 m corridor segment (hollow-rectangle
shell plus twenty detail parts — frame rib, walkway plate, wall panel
assemblies (backing plate + inset panel + four bolt heads each), trim
rails, emissive light strips). Origin at the connection pivot
(floor-center of the start edge, so instance *n* places at `x = n·4`),
identity transforms by construction, datablocks under
`Kit.CorridorSeg.*`, manifold everywhere except the two intentional open
ends, and every detail part contained strictly inside the tile so it can
never break a joint. Drop the hierarchy into a scene and array it along X.

**Pipeline arc neighbors:** watertight parametric solids in
[`bmesh-gear`](../bmesh-gear/), topology gates in
[`mesh-hygiene-audit`](../mesh-hygiene-audit/), origin/pivot discipline in
[`prop-origin-transform`](../prop-origin-transform/), collision packaging in
[`collision-hull-proxy`](../collision-hull-proxy/).

**What it witnesses** (all closed form or independently re-derived):

- **Snap.** Exactly **16** boundary verts (8 per open end, from the
  hollow-rectangle profile), every one on its end plane `x ∈ {0, 4}` within
  **1e-6 m**; every boundary edge lies on an end plane.
- **Loop coincidence.** The two end rings, matched by nearest (y, z) key,
  agree within **1e-6** — opposing loops are coincident under the tile
  offset.
- **Tiling.** A linked duplicate offset by `(4, 0, 0)` places its start ring
  at world positions matching the original's end ring within **1e-6** — no
  gap, no overlap at the joint.
- **Bounding box.** The shell's local bbox equals the declared tile exactly
  (`0..4 × ±1.5 × 0..3`, all float32-exact values, deviation 0.0), and the
  whole-asset bbox matches it because detail is contained.
- **Manifold.** Every edge has exactly 2 link faces except the **16**
  boundary ring edges (1 face each) — the open ends are the only boundaries.
- **Reuse hygiene.** Identity scales, `Kit.CorridorSeg.*` names, all part
  origins at the pivot.

**What each check catches on failure** (probed with an unsnapped variant
built by the same code minus the snap pass — 3 mm end-ring skew, 2 mm
y-nudge on two verts): boundary verts off the end planes, worst **3.000e-03 m**
(exit 3); opposing rings displaced **2.000e-03** (exit 4); tiled joint
gap/overlap (exit 5); bbox off the declared tile by **3.000e-03** (exit 6);
boundary edges torn off the rim (exit 7); non-watertight detail (exit 8);
detail escaping the tile (exit 9); unapplied transforms, default names, or
wandering origins (exit 11).

**Version witness:** check output is byte-identical on Blender 4.5.11 LTS
and 5.1.2 — same counts, same zero measured deviations.

**Render as proof:** a four-segment run — the joints vanish. The
falsification variant (`--falsify`) accumulates a 120 mm gap, 50 mm lateral
jogs, and 40 mm floor steps at each joint: floor plates split with dark
seams and the trim rails visibly break. The check measures the same failure
class at 3 mm; the render exaggerates it to read at frame scale. The render
path also gates the asset through `examples/gallery_asset_quality.py`
(naming, material variation, edge treatment — exit 11). An earlier revision
shipped flat grey wall panels and was remodeled under that gate: each panel
is now an assembly (backing plate + inset panel + four bolt heads), the
palette shifted teal-slate so the card does not twin with
`lightmap-uv-channel`'s warm cart, and mean luminance was brought into the
calibration range (82.7 → 66.1, ceiling 77.7) — no luminance deviation
needed.

**Framing deviation:** the still is an interior corridor run — the envelope
surrounds the camera on five sides and the tiling joints are the proof, so
the subject reads as extending past the frame. The helper measures;
this example enforces a projection-space fill-over cap (`FRAME_DEV_MAX =
8.0`). Gallery camera scores ~5.06 (pass). `--close-camera` scores ~30.9
and exits 10. Silhouette saturates at fill 1.0, so the cap is measured
with `strategy="projection"`.

## Run

```bash
blender --background --python modular_kit_snap.py --
blender --background --python modular_kit_snap.py -- --output corridor.png
blender --background --python modular_kit_snap.py -- --falsify seams.png
blender --background --python modular_kit_snap.py -- --output close.png --close-camera
```

## Exit codes

Per-script sequential checks. `9` is a valid check code; there is no rule
against it. `10` is this example's framing-deviation cap (call site, not
the shared Layer 1 helper). `11` is the shared asset-quality helper.

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Uncaught exception (FATAL wrapper) |
| 2 | argparse / usage |
| 3 | Boundary vert count or end-plane membership |
| 4 | End rings do not partition evenly, or opposing loops differ |
| 5 | Tiled instances do not share boundary positions |
| 6 | Shell or whole-asset bbox off the declared tile |
| 7 | Boundary edge count, non-manifold edges, or rim off the end planes |
| 8 | Detail part not watertight |
| 9 | Detail part reaches a tile boundary; also `--output` produced no file |
| 10 | Framing deviation score exceeds cap (`--close-camera`) |
| 11 | Kit part count, unapplied scale, namespace, or origin; also gallery asset-quality violation |

The `blender-smoke` workflow runs the check on Blender 5.2 LTS and 4.5 LTS
(5.1 on the weekly cron, the `needs-5.1` PR label, or manual dispatch).
Smoke does not pass `--output`, `--falsify`, or `--close-camera`.
