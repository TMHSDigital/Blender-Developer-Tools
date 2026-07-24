# Modular Kit Snap

A runnable example building the asset a tiling modular kit lives or dies
by: a corridor segment whose open-end boundary vertices sit **exactly** on
the declared tile grid, so instances placed at 4 m multiples share boundary
positions with no gap and no overlap. Interior geometry is free-form
(beveled detail boxes); only the boundary is snapped — the snap is a
deliberate authoring pass, and the check is what catches you skipping it.

**The asset, for reuse:** a 4 × 3 × 3 m corridor segment (hollow-rectangle
shell plus twelve detail parts — frame rib, walkway plate, wall panels,
trim rails, emissive light strips). Origin at the connection pivot
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
class at 3 mm; the render exaggerates it to read at frame scale.

**Framing deviation:** the still is an interior corridor run — the envelope
surrounds the camera on five sides and the tiling joints are the proof, so
the subject reads as extending past the frame (the radiating-architecture
class of VISUAL-STYLE Layer 1). `check_framing` measures and reports
(fill 1.000/1.000, all-edge bleed) without enforcing, with the reason
string at the call site.

## Run

```bash
blender --background --python modular_kit_snap.py --
blender --background --python modular_kit_snap.py -- --output corridor.png
blender --background --python modular_kit_snap.py -- --falsify seams.png
```

Exits non-zero on failure. The `blender-smoke` workflow runs the check on
Blender 4.5 LTS and 5.1. The `--output` render path additionally measures
framing against the Layer 1 band via `examples/gallery_framing.py` (reported
under the documented deviation above) before writing the still.
