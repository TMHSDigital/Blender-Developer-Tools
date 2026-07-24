# Gallery Visual Style

The spec for every example render that ships in the gallery.

This document has two layers. **House identity** is mandatory for every render
without exception — a render that violates it is a defect. The **default stage**
is the presumption: use it unless the example's own API contract requires
otherwise, and when it does, state the reason in one line in the example README.
A stage deviation without a stated reason is a defect; a stage deviation with one
is normal.

The canonical contact-sheet calibration set lives in `CLAUDE.md` §&nbsp;Quality
Gates for Example Runs. Do not restate its membership here.

## The look in one sentence

A dark staged studio — near-black floor and back wall, one shaped warm key, a
warm light pool raking the backdrop — with a saturated hero subject filling
the frame.

---

# Layer 1 — House identity (mandatory)

These hold for every render in the gallery, including examples that deviate from
the default stage.

## Color management

- `scene.view_settings.view_transform = 'Standard'`, always, with a comment.
  AgX (the 4.x/5.x default) desaturates hero materials toward pastel and
  lifts the stage toward grey — the washed look of the pre-audit gallery
  traces to renders that never set a transform.
- Standard does not compress highlights: tune light energies so nothing
  clips. If a region reads pure white at full size, the key is too hot.
  (Exception: a subject whose contract *is* a blown or clamped value —
  see Deviations — must still confine the clipping to the witnessed region.)

## Materials

- Hero materials are designed, never Principled defaults: saturated base
  colors, roughness chosen (0.3–0.6 glossy, 0.7+ matte), optional faint
  emission (~0.1) when the subject carries color data that must read exactly.
- Surfaces that display flat color data (attribute fills, pixel buffers) go
  fully matte: `Specular IOR Level = 0`, otherwise the wall/floor horizon
  reflects as a line across the face.
- Nothing in frame may read as programmer art. Subjects are modeled with
  intent, not primitives with modifiers.

## Framing and camera

- The subject fills 70–90 % of the frame in at least one axis, measured —
  never eyeballed. Nothing that matters may touch or cross the frame edge.
- Measure with the shared helper `examples/gallery_framing.py`, called on the
  render path only (import shim and full contract in its docstring):
  `gallery_framing.check_framing(sc, cam, hero=..., elements=..., stage=...)`
  prints the numbers and exits 10 on violation. **Fill** is measured on the
  hero subject only and must land in the 0.70–0.90 band in at least one axis,
  neither axis above 0.90. **Margin** is measured on the union of every
  element that matters — hero, placards, labels, comparison props, overlay
  markers — and must clear all four edges by ≥ 2 % of the frame dimension.
  Default strategy is the silhouette alpha matte; projection is the cheap
  bbox alternative for boxy subjects (tradeoff in the helper's docstring).
- **Framing deviations.** The band and the margin floor are the presumption.
  A composition may deviate when the bleed or the scale is the design:
  radiating subjects that read as extending past the frame, edge-to-edge
  fields where the fill is the point, and subjects whose contract is the
  world or the atmosphere rather than an object on a stage. A deviation
  requires one line in the example README under a `Framing deviation`
  heading — what the composition requires and why, exactly as stage
  deviations do. An undocumented deviation is a defect. Under a documented
  deviation the helper reports rather than enforces: call
  `check_framing(..., deviation="reason")`, which prints the numbers with
  the reason; an empty reason raises, so no deviation is taken silently.
- Camera: a chosen angle, not the default — typically a 45–55 mm lens,
  slightly above subject height, aimed with a `TRACK_TO` constraint at an
  empty on the subject. Flat subjects present toward the camera (lean or
  tilt them); progressions read left to right.
- No visible helper objects, light shapes, tracking empties, or backdrop
  seams crossing the subject.

## The render is the proof

- The image must read in under a second at thumbnail scale.
- The image must witness the API: if the contract failed, the render should
  visibly break. If the render would look the same whether the code worked or
  not, the scene design is wrong, not merely unpolished.
- **Numeric-only contracts are a narrow, declared exception.** Some contracts
  have no visual signature: the broken state renders pixel-identical because
  the evidence is a count, a cap, or a buffer invariant, not a shape. Then
  the example says so in its README, the render's job is to depict the
  subject and its setup legibly — so the reader can see what the numbers
  describe — and the falsification pass is satisfied by naming why no visual
  difference exists. Precedents: `vertex-weight-limit` (the prune preserves
  the pose by design, so the 4-influence cap is numeric) and
  `triangulate-tangents` (the ring sweep is UV/bump-driven, so a
  tangent-field break does not move pixels). This is for contracts that
  genuinely cannot be seen, not for scenes that were not designed hard
  enough: where a visual witness is possible, it is required.
- Presentation may be staged; evidence may not. When the witnessed artifact
  is itself an image (a sequencer frame, a pixel buffer, a baked texture),
  the authentic pixels must appear unaltered — mount them in the scene
  (`vse-cut-list` on a monitor, `image-pixels-testcard` on a TV) rather than
  recreating them.

## Asset quality (measured gate)

"Modeled with intent" is measured, not a vibe. Three parts: measurable
floors, a named reference bar, and the asset sheet. The floors are the
cheap filter that catches the obvious failures; the asset sheet is what
actually decides. Applies to asset-type examples (game props, kits) —
not to world, field, art, or media subjects.

### Floors

Computed by `examples/gallery_asset_quality.py` (render path only, same
call pattern as `gallery_framing`; prints measured values; exit 11 on
violation; never imported by a check-only path):

- **Naming** — no default datablock names on hero parts (Cube, Sphere,
  Torus, Suzanne, …). A designed asset names its parts.
- **Material variation** — a hero assembled from ≥ 2 parts carries ≥ 2
  distinct materials. A single flat Principled slot across an entire prop
  is this gallery's most reliable placeholder predictor. Single-part
  subjects are exempt: one honest material is their truth (a brass gear).
- **Edge treatment** — at most **75 %** of a hero's manifold edges may be
  right angles (90° ± 2°). Unbroken 90° corners across the board means no
  bevel, no chamfer, no shading break. Honest machined teeth pass
  (`bmesh-gear` measures 0.667); raw boxes (1.0) fail.

Calibrated empirically against the gallery's own assets, exactly as the
0.02 margin floor was:

| asset | parts | materials | edge90 | compactness (info only) |
| --- | --- | --- | --- | --- |
| collision-hull-proxy (reference) | 16 | 6 | 0.044 | 65.9 |
| custom-normals-shade (reference) | 39 | 2 | 0.288 | 31.0 |
| vertex-weight-limit (reference) | 1 | 4 | 0.150 | 34.8 |
| lod-decimate-chain (reference) | 3 | 4 | 0.019 | 79.1 |
| depsgraph-export (weak) | 2 | 1 | 1.000 | 23.9 |
| text-version-stamp (weak) | 1 | 1 | 1.000 | 405.3 |
| bmesh-gear (simple, honest) | 1 | 1 | 0.667 | 18.3 |
| soccer-ball-goldberg (simple, honest) | 1 | 2 | 0.000 | 10.0 |

Dropped floors, with the evidence that killed them — a floor that cannot
be set without failing a genuinely good asset is not a floor, and a floor
hand-tuned to pass everything is not one either:

- **Part count** — `vertex-weight-limit`'s mech arm is a single skinned
  mesh and is reference-quality. Skinned deform meshes are one mesh by
  design. The naming half survives.
- **Silhouette compactness** — `soccer-ball-goldberg` scores 10.0,
  `bmesh-gear` 18.3, `turntable` 19.1: genuinely good simple subjects
  with low-complexity silhouettes. Measured and printed as information.
- **Dominant-material share** — `custom-normals-shade`'s jerry can and
  `lod-decimate-chain`'s rocket carry their accents in per-face
  assignment, invisible to a per-part share (both measure 1.0 dominant).
  Printed as information only.

### The Goodhart warning

These floors are necessary, not sufficient. Bolting meaningless greebles
onto a box to raise silhouette complexity satisfies every number above
and still fails. Detail must serve the object's plausibility: fixtures
where fixtures belong, wear where contact happens, structure where
structure carries load. The asset sheet exists because metrics can be
gamed; a lineup of peers cannot.

### Reference bar

The asset-quality reference set is pinned in `CLAUDE.md` § Quality Gates
for Example Runs — canonical membership lives there, not here.

### Asset sheet gate

For every new asset-type example: render the hero alone — neutral
three-quarter view, plain studio lighting, no staging tricks, no labels,
no comparison props — composite it beside the reference assets rendered
the same way, commit under `docs/gallery/asset-sheets/`, and link it in
the PR body with a verdict. The asset ships only if it is not
identifiable as the least-designed object in that lineup. Isolating the
asset from its staging is the point: a strong scene can carry a weak
model, and this gate removes the scene.

## Output

- Render 1280×720 PNG (`taa_render_samples`/`cycles.samples` 32–64).
- Gallery assets: hero webp 1280×720 and preview webp 1200×675, quality 85
  (load the PNG in Blender, `save(filepath=..., quality=85)`, `scale()` for
  the preview — this preserves pixels without re-applying color management).
- After touching any example: `python scripts/build_gallery.py`, and update
  the README gallery-row alt text if the composition changed.

---

# Layer 2 — Default stage (the presumption)

Use this unless the contract requires otherwise. It is what makes the gallery
read as one body of work, and the great majority of examples should use it
unmodified.

## Stage

- Floor: 30-unit `create_grid` plane. Wall: a copy at `y ≈ 7–9`, rotated 90°
  about X. Both share one Principled material:
  `Base Color (0.03, 0.032, 0.037)`, `Roughness 0.7`.
- World background: `(0.02, 0.021, 0.025)`.
- The floor/wall seam is acceptable only where it falls into shadow; never
  let it cross the subject.

## Lighting (all AREA lights)

- **Key** — warm white `(1.0, 0.96, 0.9)`, upper left, ~`(-4, -5, 6)`,
  size 4–6, 300–700 W depending on subject albedo. It must shape: visible
  falloff across the subject, a readable cast shadow.
- **Fill** — cool `(0.75, 0.85, 1.0)`, low right, size ~9, ~100 W. Just
  enough that shadow sides stay legible; if the image looks flat, the fill
  is too strong.
- **Rim** — cool `(0.6, 0.78, 1.0)`, behind, 200–400 W, to lift silhouettes
  off the backdrop.
- **Wedge** — the signature: warm `(1.0, 0.76, 0.5)`, 200–500 W, size 5–7,
  raking the back wall so a soft pool of light sits behind the subject.
  Place it **between the subject and the wall**. A grazing area light draws
  a hard terminator line across any flat surface it skims — if a stray
  bright band crosses the subject, a light is grazing it.

---

# Deviations

Some contracts cannot be witnessed on the default stage. The stage is a
presumption, not a cage: when the subject of the example *is* the lighting, the
world, the atmosphere, or the camera itself, the default stage would hide the
very thing being proven.

**When a deviation is legitimate.** The contract requires it. Examples:

- **Lighting contracts** (light linking, shadow-catcher, light groups) — the
  arrangement of lights is the evidence; the fixed four-light rig pre-empts it.
- **World / sky contracts** (sky texture, sun elevation, HDRI mapping, world
  node trees) — the near-black world value is the thing under test.
- **Volumetric contracts** (scatter density, god rays, absorption) — a
  near-black stage swallows the phenomenon.
- **Camera contracts** (depth of field, focus distance, motion blur, sensor
  fit) — these need depth and background content the default framing avoids.
- **Non-photoreal contracts** (Freestyle, line art, flat NPR shading) — a
  raking key fights the flat readable field the technique produces.
- **Clamping / exposure contracts** — where a blown or clamped value is
  precisely what the check asserts.

**What a deviation must still satisfy.** Everything in Layer 1, without
exception: Standard view transform, designed materials, chosen camera,
70–90 % subject fill, no visible helpers, thumbnail legibility, render-as-proof,
authentic evidence, and the output pipeline. Deviate from the stage, never from
the identity.

**What a deviation must not be.** A deviation is not permission to skip staging
effort. "The default stage did not suit this" is not a reason; "this example
witnesses sun elevation, so the world background carries a sky texture" is.
Lighting a deviating scene is *more* work than using the rig, not less — the
scene still needs a designed key, deliberate falloff, and a background that was
chosen rather than defaulted.

**Documenting it.** One line in the example README under a `Stage deviation`
heading: what changed, and which contract required it. One line in the PR body.
That is the whole ceremony.

**The contact-sheet gate under deviation.** The gate still applies and the
composite is still committed. The pass condition is unchanged in substance —
the candidate must not be sortable as belonging to a *different gallery* — but
judge it on materials, framing, finish, view transform, and thumbnail legibility
rather than backdrop match. Report mean luminance against the calibration set as
*information*, not as a pass/fail criterion, and say in the verdict that the
example deviates and why. A bright sky-texture render can hold the lineup; a
carelessly lit one cannot, and the sheet is how you tell them apart.